"""Descarga COMPLETA de una galería de hitomi.la (port de PupilSources/libpupil a Python).

Flujo: galleries/{id}.js → lista de imágenes (hash) → gg.js (subdominios) → URL de cada página → descarga con
Referer del lector (sin él el CDN devuelve 403). Todas las descargas pasan por el SafeFetcher del navegador
(SSRF, tamaño máximo, robots desactivado solo para el CDN de imágenes como en GalleryBridge).
"""
from __future__ import annotations

import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import hitomi_urls as H

GALLERY_PREFIX = "var galleryinfo = "
GG_TTL_S = 60.0
MAX_JS_BYTES = 4 * 1024 * 1024
MAX_IMAGE_BYTES = 40 * 1024 * 1024
RETRIES = 3            # intentos por imagen (el downloader de referencia reintenta con espera exponencial)
RETRY_SLEEP_S = 1.0    # espera base: 1 s, 2 s, ...
WORKERS = 4            # páginas en paralelo (el downloader de referencia usa 4 por cómic)

_REF_RE = re.compile(r"^https?://(?:www\.)?hitomi\.la/(?:reader|galleries)/(\d+)\.html", re.IGNORECASE)


def gallery_id_from_url(url: str) -> int | None:
    """ID de galería si la URL es de hitomi (lector o ficha). None en cualquier otro caso."""
    m = _REF_RE.match((url or "").strip())
    return int(m.group(1)) if m else None


def parse_gallery_js(text: str) -> dict:
    """Quita el prefijo «var galleryinfo = » y devuelve el JSON de la galería."""
    body = text.strip()
    if body.startswith(GALLERY_PREFIX):
        body = body[len(GALLERY_PREFIX):]
    return json.loads(body)


class GGCache:
    """gg.js cacheado 60 s (como en libpupil/PupilSources)."""

    def __init__(self, fetcher):
        self.fetcher = fetcher
        self._gg: H.GG | None = None
        self._at = 0.0

    def get(self) -> H.GG:
        if self._gg is None or time.monotonic() - self._at > GG_TTL_S:
            res = self.fetcher.get(H.gg_js_url(), MAX_JS_BYTES, accept="*/*", check_robots=False)
            self._gg = H.parse_gg(res.content.decode("utf-8", "replace"))
            self._at = time.monotonic()
        return self._gg


def fetch_gallery_info(fetcher, gallery_id: int) -> dict:
    res = fetcher.get(H.gallery_js_url(gallery_id), MAX_JS_BYTES, accept="*/*", check_robots=False)
    return parse_gallery_js(res.content.decode("utf-8", "replace"))


def image_urls(files: list[dict], gg: H.GG) -> list[tuple[str, str]]:
    """[(url, nombre_de_archivo)] de cada página, en el orden de la galería (webp, la forma que usa el lector)."""
    out = []
    for i, f in enumerate(files, start=1):
        h = f.get("hash", "")
        if len(h) != 64:
            continue
        out.append((H.image_url(h, gg, "webp"), f"{i:03d}.webp"))
    return out


def _fetch_image(fetcher, url: str, referer: str) -> bytes:
    """Descarga una imagen con reintentos y espera creciente; relanza el último error si todos fallan."""
    last = None
    for attempt in range(RETRIES):
        try:
            return fetcher.get(url, MAX_IMAGE_BYTES, accept="image/*", check_robots=False,
                               headers={"Referer": referer}).content
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt < RETRIES - 1:
                time.sleep(RETRY_SLEEP_S * (attempt + 1))
    raise last


def _download_pages(fetcher, pages, referer, dest, progress, cancel, log, workers=WORKERS):
    """pages = [(url, nombre)]. Descarga en paralelo, reanuda (omite lo ya bajado) y conserva el orden de `saved`."""
    dest.mkdir(parents=True, exist_ok=True)
    total, results, lock, counter = len(pages), {}, threading.Lock(), [0]

    def work(i):
        url, name = pages[i]
        if cancel is not None and cancel.is_set():
            return
        target = dest / name
        try:
            if target.is_file() and target.stat().st_size > 0:
                results[i] = (True, str(target))
            else:
                data = _fetch_image(fetcher, url, referer)
                tmp = target.with_name(name + ".tmp")
                tmp.write_bytes(data)
                tmp.replace(target)
                results[i] = (True, str(target))
        except Exception as exc:  # noqa: BLE001 — una página rota no tumba la galería
            results[i] = (False, f"{name}: {type(exc).__name__}: {exc}")
            log(f"hitomi: fallo en {name}: {exc}")
        with lock:
            counter[0] += 1
            n = counter[0]
        if progress:
            progress(n / total, f"Descargando página {n} de {total}…")

    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as ex:
        list(ex.map(work, range(total)))
    saved = [results[i][1] for i in range(total) if i in results and results[i][0]]
    failed = [results[i][1] for i in range(total) if i in results and not results[i][0]]
    return saved, failed


def download_gallery(fetcher, gallery_id: int, dest: Path, progress=None, cancel=None, log=print) -> dict:
    """Descarga todas las páginas de la galería a `dest`. Devuelve {title, paginas, archivos, fallos}."""
    info = fetch_gallery_info(fetcher, gallery_id)
    files = info.get("files") or []
    if not files:
        raise ValueError("La galería no tiene páginas.")
    gg = GGCache(fetcher).get()
    pages = image_urls(files, gg)
    saved, failed = _download_pages(fetcher, pages, H.IMAGE_REFERER, dest, progress, cancel, log)
    return {"title": info.get("title") or f"hitomi_{gallery_id}", "paginas": len(pages),
            "archivos": saved, "fallos": failed}


def reader_referer_for(gallery_id) -> str:
    return H.IMAGE_REFERER


def download_urls(fetcher, urls: list, referer: str, dest: Path, progress=None, cancel=None, log=print) -> dict:
    """Descarga una lista de URLs de página (ya calculadas) con el Referer de la galería (en paralelo, con reanudación)."""
    pages = [(u, f"{n:03d}.webp") for n, u in enumerate(urls, start=1)]
    saved, failed = _download_pages(fetcher, pages, referer, dest, progress, cancel, log)
    return {"archivos": saved, "fallos": failed}
