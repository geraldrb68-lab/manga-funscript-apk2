"""Exporta una galería de hitomi como MANGA LOCAL de manga_funscript.

Resultado en disco (carpeta de la biblioteca, p. ej. <datos del navegador>/biblioteca_hitomi/):
    <id>_<título>/0001.webp 0002.webp …      páginas (nombres que ordenan bien)
    <id>_<título>/metadata.json                título, etiquetas «female:xxx», artistas…  (lo lee pupil_bridge.parse_metadata)
    <id>_<título>/galleryinfo.json             copia íntegra de lo que dio la página
    <id>_<título>.cbz  (opcional)              con ComicInfo.xml, para otros lectores
Descarga en paralelo (4 hilos), con reintentos, a una carpeta .part que se renombra al terminar (nunca queda una galería
a medias con aspecto de completa) y reanuda: lo ya bajado no se vuelve a pedir. Sin Qt ni Tk: se prueba con un `fetch` falso.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from xml.sax.saxutils import escape

IMG_EXT = (".webp", ".avif", ".jpg", ".jpeg", ".png", ".gif", ".bmp")
WORKERS = 4
RETRIES = 3
RETRY_SLEEP_S = 1.0
MIN_IMAGE_BYTES = 64


def safe_name(s, limit=60):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", str(s or "")).strip(" .")
    s = re.sub(r"\s+", " ", s)
    return (s[:limit].strip(" .")) or "galeria"


def _names(items):
    out = []
    for it in items or []:
        if isinstance(it, str):
            out.append(it)
        elif isinstance(it, dict):
            for k in ("artist", "group", "parody", "character", "name"):
                if it.get(k):
                    out.append(str(it[k]))
                    break
    return out


def flatten_tags(tags):
    """[{tag:'x', female:'1'}, ...] -> ['female:x', ...] (sin descartar ninguna)."""
    out = []
    for t in tags or []:
        if isinstance(t, str):
            out.append(t)
        elif isinstance(t, dict) and t.get("tag"):
            ns = "female" if str(t.get("female")) in ("1", "True", "true") else \
                 "male" if str(t.get("male")) in ("1", "True", "true") else ""
            out.append(f"{ns}:{t['tag']}" if ns else str(t["tag"]))
    return out


def build_metadata(info, page_url="", names=None):
    """Metadatos compatibles con pupil_bridge.parse_metadata (tags TAL CUAL; artistas aparte para no contaminar las etiquetas)."""
    info = info or {}
    files = info.get("files") or []
    pages = []
    for i, f in enumerate(files):
        pages.append({"name": (names[i] if names and i < len(names) else f"{i + 1:04d}.webp"),
                      "width": f.get("width"), "height": f.get("height"), "hash": f.get("hash")})
    lang = info.get("language_localname") or info.get("language") or ""
    return {
        "title": info.get("title") or info.get("japanese_title") or f"hitomi_{info.get('id', '')}",
        "japanese_title": info.get("japanese_title") or "",
        "source": page_url or (f"https://hitomi.la/galleries/{info.get('id')}.html" if info.get("id") else ""),
        "gallery_id": info.get("id"),
        "type": info.get("type") or "",
        "language": lang,
        "date": info.get("date") or "",
        "artists": _names(info.get("artists")),
        "groups": _names(info.get("groups")),
        "parodies": _names(info.get("parodys") or info.get("parodies")),
        "characters": _names(info.get("characters")),
        "tags": flatten_tags(info.get("tags")),
        "pages": pages,
    }


def _ext_from_url(url):
    m = re.search(r"\.([A-Za-z0-9]{3,4})(?:[?#]|$)", url or "")
    e = ("." + m.group(1).lower()) if m else ".webp"
    return e if e in IMG_EXT else ".webp"


def _fetch_retry(fetch, url, cancel):
    last = None
    for attempt in range(RETRIES):
        if cancel is not None and cancel.is_set():
            raise InterruptedError("cancelado")
        try:
            data = fetch(url)
            if not data or len(data) < MIN_IMAGE_BYTES:
                raise ValueError("respuesta vacía o demasiado corta")
            return data
        except InterruptedError:
            raise
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt < RETRIES - 1:
                time.sleep(RETRY_SLEEP_S * (attempt + 1))
    raise last


def write_cbz(folder, cbz_path, meta):
    tmp = cbz_path + ".part"
    imgs = sorted(f for f in os.listdir(folder) if f.lower().endswith(IMG_EXT))
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as z:
        for f in imgs:
            z.write(os.path.join(folder, f), f)
        tags = ", ".join(meta.get("tags", []))
        xml = ('<?xml version="1.0" encoding="utf-8"?>\n<ComicInfo>\n'
               f'  <Title>{escape(str(meta.get("title", "")))}</Title>\n'
               f'  <Writer>{escape(", ".join(meta.get("artists", [])))}</Writer>\n'
               f'  <Tags>{escape(tags)}</Tags>\n'
               f'  <LanguageISO>{escape(str(meta.get("language", "")))}</LanguageISO>\n'
               f'  <PageCount>{len(imgs)}</PageCount>\n'
               f'  <Web>{escape(str(meta.get("source", "")))}</Web>\n</ComicInfo>\n')
        z.writestr("ComicInfo.xml", xml)
    os.replace(tmp, cbz_path)
    return cbz_path


def export_gallery(urls, info, page_url, library_root, fetch, progress=None, cancel=None, make_cbz=False,
                   workers=WORKERS, log=print):
    """Descarga y organiza la galería. `fetch(url) -> bytes` (con Referer, SSRF, etc. lo pone quien llama).
    Devuelve {ok, folder, meta_file, cbz, pages, failed:[...], reused:bool, meta:dict}."""
    urls = [u for u in urls if isinstance(u, str) and u.startswith(("http://", "https://"))]
    if not urls:
        return {"ok": False, "error": "La galería no tiene páginas descargables.", "failed": []}
    gid = (info or {}).get("id") or "x"
    base = safe_name(f"{gid}_{(info or {}).get('title') or 'hitomi'}")
    os.makedirs(library_root, exist_ok=True)
    final = os.path.join(library_root, base)
    part = final + ".part"
    names = [f"{i + 1:04d}{_ext_from_url(u)}" for i, u in enumerate(urls)]
    meta = build_metadata(info, page_url, names)

    def done_result(reused, failed=()):
        mf = os.path.join(final, "metadata.json")
        cbz = None
        if make_cbz:
            cbz = write_cbz(final, final + ".cbz", meta)
        return {"ok": True, "folder": final, "meta_file": mf, "cbz": cbz, "pages": len(names) - len(failed),
                "failed": list(failed), "reused": reused, "meta": meta}

    if os.path.isdir(final) and all(os.path.isfile(os.path.join(final, n)) and
                                    os.path.getsize(os.path.join(final, n)) >= MIN_IMAGE_BYTES for n in names) \
            and os.path.isfile(os.path.join(final, "metadata.json")):
        if progress:
            progress(1.0, "Esa galería ya estaba exportada: la reutilizo.")
        return done_result(True)

    os.makedirs(part, exist_ok=True)
    total, counter, lock, failed = len(names), [0], threading.Lock(), []

    def work(i):
        name = names[i]
        dest = os.path.join(part, name)
        if os.path.isfile(dest) and os.path.getsize(dest) >= MIN_IMAGE_BYTES:
            data_ok = True                                  # reanudar: ya estaba
        else:
            try:
                data = _fetch_retry(fetch, urls[i], cancel)
                tmp = dest + ".tmp"
                with open(tmp, "wb") as f:
                    f.write(data)
                os.replace(tmp, dest)
                data_ok = True
            except InterruptedError:
                return
            except Exception as exc:  # noqa: BLE001
                data_ok = False
                with lock:
                    failed.append(f"{name}: {type(exc).__name__}: {exc}")
                log(f"hitomi: fallo en {name}: {exc}")
        with lock:
            counter[0] += 1
            n = counter[0]
        if progress:
            progress(n / total, f"Descargando página {n} de {total}…")
        return data_ok

    with ThreadPoolExecutor(max_workers=max(1, min(int(workers), 8))) as ex:
        list(ex.map(work, range(total)))

    if cancel is not None and cancel.is_set():
        return {"ok": False, "error": "Cancelado. Lo bajado queda para reanudar.", "failed": failed}
    got = [n for n in names if os.path.isfile(os.path.join(part, n))]
    if not got:
        return {"ok": False, "error": "No se pudo descargar ninguna página. " + "; ".join(failed[:2]), "failed": failed}
    if failed:
        # con páginas que faltan NO se finaliza como completa: se deja el .part para reintentar solo lo que falta
        meta["pages"] = [p for p in meta["pages"] if p["name"] in got]
    with open(os.path.join(part, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    with open(os.path.join(part, "galleryinfo.json"), "w", encoding="utf-8") as f:
        json.dump(info or {}, f, ensure_ascii=False)
    if failed:
        out_dir = final + "_incompleta"
        if os.path.isdir(out_dir):
            shutil.rmtree(out_dir, ignore_errors=True)
        shutil.copytree(part, out_dir)                      # usable ya; el .part conserva lo bajado para reanudar
        res = {"ok": True, "folder": out_dir, "meta_file": os.path.join(out_dir, "metadata.json"), "cbz": None,
               "pages": len(got), "failed": failed, "reused": False, "meta": meta, "incomplete": True}
        return res
    if os.path.isdir(final):
        shutil.rmtree(final, ignore_errors=True)
    os.replace(part, final)
    return done_result(False)
