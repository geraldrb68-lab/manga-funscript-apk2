"""Puente Python -> Kotlin (Chaquopy). Fase 2: importación de galerías de Hitomi.

Reutiliza hitomi_gallery.py / hitomi_urls.py / hitomi_export.py del proyecto original
sin cambiar su lógica. Solo se sustituye el 'fetcher' por uno basado en requests.
"""
import json
import shutil
import threading
import time
import traceback
from pathlib import Path

import requests

import hitomi_export as HE
import hitomi_gallery as HG
import intiface as IF
import aprendizaje as AP

TIMEOUT_S = 30
UA = "Mozilla/5.0 (Linux; Android 10) MangaFunscript/0.2"


class _Resp:
    def __init__(self, content):
        self.content = content


class RequestsFetcher:
    """Mismo contrato que SafeFetcher.get(url, max_bytes, accept=, check_robots=, headers=)."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = UA

    def get(self, url, max_bytes, accept="*/*", check_robots=False, headers=None):
        h = {"Accept": accept}
        if headers:
            h.update(headers)
        with self.session.get(url, headers=h, timeout=TIMEOUT_S, stream=True) as r:
            r.raise_for_status()
            chunks, total = [], 0
            for chunk in r.iter_content(64 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("respuesta demasiado grande")
                chunks.append(chunk)
        return _Resp(b"".join(chunks))


def _err(msg):
    return json.dumps({"ok": False, "message": msg}, ensure_ascii=False)


def import_gallery(gallery_url, library_dir):
    """Descarga la galería a <library_dir>/<id>/ y devuelve JSON: {ok, id, title, folder, paginas} o {ok:false, message}.

    Descarga en una carpeta <id>.part y la renombra al terminar, para que nunca quede una galería a medias.
    Si ya existe, no vuelve a descargarla. Si fallan páginas, deja el .part para reanudar luego.
    """
    try:
        gid = HG.gallery_id_from_url(gallery_url)
        if gid is None:
            return _err("La dirección no es una galería de hitomi.")

        lib = Path(library_dir)
        lib.mkdir(parents=True, exist_ok=True)
        final = lib / str(gid)
        if final.is_dir() and any(final.glob("*.webp")):
            meta = json.loads((final / "metadata.json").read_text(encoding="utf-8"))
            return json.dumps({"ok": True, "id": gid, "title": meta.get("title", ""),
                               "folder": str(final), "paginas": meta.get("paginas", 0)}, ensure_ascii=False)

        part = lib / f"{gid}.part"
        part.mkdir(parents=True, exist_ok=True)
        fetcher = RequestsFetcher()

        info = HG.fetch_gallery_info(fetcher, gid)
        (part / "galleryinfo.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")

        res = HG.download_gallery(fetcher, gid, part, log=lambda m: None)
        if res["fallos"] or len(res["archivos"]) < res["paginas"]:
            n = len(res["fallos"])
            return _err(f"Faltan {n} páginas de la galería {gid}. Vuelve a intentarlo para reanudar.")

        meta = HE.build_metadata(info, page_url=gallery_url)
        meta.update({"id": gid, "paginas": res["paginas"]})
        (part / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        if final.exists():
            shutil.rmtree(final)
        part.rename(final)
        return json.dumps({"ok": True, "id": gid, "title": res["title"],
                           "folder": str(final), "paginas": res["paginas"]}, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001 — siempre devolver un mensaje legible a la app
        traceback.print_exc()
        return _err(f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Intiface (Intiface Central corre en el mismo teléfono; se conecta por websocket)
# ---------------------------------------------------------------------------
_client = None          # instancia de intiface.Intiface (lazy)
_channel = None         # canal elegido para el funscript (preferencia: lineal)
_stop_evt = None        # evento de parada del bucle actual
_last_log = ""


def _log(msg):
    global _last_log
    _last_log = str(msg)


def _get_client():
    global _client
    if _client is None:
        _client = IF.Intiface(log=_log)
    return _client


def intiface_connect(url):
    _get_client().connect(url)
    return json.dumps({"ok": True})


def intiface_status():
    """Estado para la app: conectado, etiquetas de canales y último mensaje del cliente."""
    global _channel
    c = _get_client()
    labels, selected = [], ""
    if c.connected:
        chans = c.channels()
        labels = [label for label, _ in chans]
        if chans:
            pick = next((i for i, (_, ch) in enumerate(chans) if ch["kind"] == "linear"), 0)
            _channel = chans[pick][1]
            selected = chans[pick][0]
    return json.dumps({"connected": bool(c.connected), "channels": labels,
                       "selected": selected, "log": _last_log}, ensure_ascii=False)


def intiface_disconnect():
    stop_play(send_stop=True)
    if _client is not None:
        _client.disconnect()
    return json.dumps({"ok": True})


def _load_actions(path):
    """Lee un .funscript estándar: {"actions": [{"at": ms, "pos": 0-100}, ...]}."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []
    for a in data.get("actions", []):
        try:
            out.append((int(a["at"]), max(0.0, min(100.0, float(a["pos"])))))
        except (KeyError, TypeError, ValueError):
            continue
    out.sort(key=lambda x: x[0])
    return out


def _loop(client, channel, actions, evt):
    """Reproduce las acciones en bucle hasta que se pida parar (evt)."""
    while not evt.is_set():
        t0 = time.monotonic()
        for i, (at, pos) in enumerate(actions):
            if evt.is_set():
                return
            wait = t0 + at / 1000.0 - time.monotonic()
            if wait > 0 and evt.wait(wait):
                return
            nxt = actions[i + 1][0] if i + 1 < len(actions) else at + 100
            client.send_value(channel, pos / 100.0, max(20, nxt - at))
        evt.wait(0.2)   # pausa corta antes de repetir el ciclo


def stop_play(send_stop=True):
    global _stop_evt
    if _stop_evt is not None:
        _stop_evt.set()
        _stop_evt = None
    if send_stop and _client is not None and _client.connected:
        _client.stop_all()
    return json.dumps({"ok": True})


def play_page(path):
    """Reproduce en bucle el funscript de la página. Al cambiar de página se llama otra vez y sustituye al anterior."""
    global _stop_evt
    p = Path(path)
    if not p.is_file():
        stop_play(send_stop=True)
        return _err("Esta página no tiene funscript.")
    if _client is None or not _client.connected or _channel is None:
        return _err("Intiface no conectado o sin dispositivo seleccionado.")
    actions = _load_actions(p)
    if not actions:
        stop_play(send_stop=True)
        return _err("Funscript vacío.")
    stop_play(send_stop=False)
    evt = threading.Event()
    _stop_evt = evt
    threading.Thread(target=_loop, args=(_client, _channel, actions, evt), daemon=True).start()
    return json.dumps({"ok": True, "acciones": len(actions)})


# ---------------------------------------------------------------------------
# Sistema de aprendizaje: correcciones del usuario ("falta" / "sobra" funscript)
# El historial se guarda junto a la biblioteca, en <biblioteca>/aprendizaje.json.
# Fase 4: las etiquetas son las de la galería (metadata.json). Por viñeta llegarán con el etiquetador.
# ---------------------------------------------------------------------------
def correccion(folder, page, kind):
    try:
        folder = Path(folder)
        meta_path = folder / "metadata.json"
        tags = []
        if meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            tags = list(meta.get("tags", []))
        ap = AP.Aprendizaje(str(folder.parent / "aprendizaje.json"))
        valor = ap.registrar(folder.name, page, tags, kind)
        return json.dumps({"ok": True, "valor": valor, "etiquetas": len(tags)}, ensure_ascii=False)
    except AP.RechazadoError as exc:
        return _err(str(exc))
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return _err(f"{type(exc).__name__}: {exc}")
