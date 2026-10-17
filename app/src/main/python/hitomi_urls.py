"""Cálculo de URLs de imágenes de hitomi.la.

ACTUALIZADO al dominio actual de hitomi: los medios ya NO se sirven desde *.hitomi.la (aa./ba.hitomi.la no resuelven),
sino desde *.gold-usergeneratedcontent.net. Fórmula contrastada con lanyeeee/hitomi-downloader (Rust, funciona hoy):
  imagen    https://w<1+gg.m(g)>.gold-usergeneratedcontent.net/<gg.b><gg.s(hash)>/<hash>.webp   (avif: prefijo 'a')
  gg.js     https://ltn.gold-usergeneratedcontent.net/gg.js
  galería   https://ltn.gold-usergeneratedcontent.net/galleries/<id>.js
  Referer   https://hitomi.la/
La versión anterior (port de libpupil/PupilSources, 'aa.hitomi.la/webp/...') quedó obsoleta.

Solo funciones PURAS: no hacen red. La red (descargar gallery .js y gg.js) la hace el recolector seguro del navegador.
Verificado en tests/test_hitomi_urls.py (valores a mano + paridad con un port independiente del Rust de referencia).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MEDIA_DOMAIN = "gold-usergeneratedcontent.net"
LTN_HOST = f"ltn.{MEDIA_DOMAIN}"
IMAGE_REFERER = "https://hitomi.la/"     # el que usa el downloader de referencia para las imágenes
_HOST_RE = re.compile(r"//..?\.(?:gold-usergeneratedcontent\.net|hitomi\.la)/")


@dataclass
class GG:
    """Estado de gg.js: subdominio por galería (mapping), valor por defecto y ruta base."""
    default: int = 0
    mapping: dict = field(default_factory=dict)
    b: str = ""


def parse_gg(js: str) -> GG:
    """Extrae los datos de gg.js (mismas expresiones regulares que la versión Kotlin)."""
    md, mo, mb = re.search(r"var o = (\d)", js), re.search(r"o = (\d); break;", js), re.search(r"b: '(.+)'", js)
    if not md or not mb:
        raise ValueError("gg.js con formato desconocido (falta 'var o = N' o 'b: ...'): hitomi pudo cambiarlo otra vez")
    o = int(mo.group(1)) if mo else int(md.group(1))
    mapping = {int(c): o for c in re.findall(r"case (\d+):", js)}
    return GG(default=int(md.group(1)), mapping=mapping, b=mb.group(1))


def m(gg: GG, g: int) -> int:
    return gg.mapping.get(g, gg.default)


def s(h: str) -> str:
    """Número decimal de la carpeta: los 3 últimos caracteres del hash (último + dos anteriores, en hex)."""
    return str(int(h[-1] + h[-3:-1], 16))


def real_full_path(h: str) -> str:
    """Ruta sin gg.js (miniaturas): «último/dos_siguientes/hash»."""
    return f"{h[-1]}/{h[-3:-1]}/{h}"


def full_path(h: str, gg: GG) -> str:
    return f"{gg.b}{s(h)}/{h}"


def subdomain(url: str, gg: GG, base: str | None = None, dir: str | None = None) -> str:
    """Subdominio según el hash de la URL (common.js: subdomain_from_url).
    Sin `base`: 'w'+(1+m) para webp, 'a'+(1+m) para avif. Con `base` (p. ej. 'tn'): letra(97+m)+base."""
    retval = ""
    if not base:
        retval = {"webp": "w", "avif": "a"}.get(dir or "", "")
    mt = re.search(r"/[0-9a-f]{61}([0-9a-f]{2})([0-9a-f])", url)
    if mt is None:
        return retval
    g = int(mt.group(2) + mt.group(1), 16)
    if not base:
        return f"{retval}{1 + m(gg, g)}"
    return chr(97 + m(gg, g)) + base


def url_from_url(url: str, gg: GG, base: str | None = None, dir: str | None = None) -> str:
    sub = subdomain(url, gg, base, dir)
    return _HOST_RE.sub(f"//{sub}.{MEDIA_DOMAIN}/", url, count=1)


def image_url(h: str, gg: GG, ext: str = "webp") -> str:
    """URL de la imagen original (la que usa el lector). ext: 'webp' (por defecto) o 'avif'. Sin carpeta 'webp/'."""
    raw = f"https://a.{MEDIA_DOMAIN}/{full_path(h, gg)}.{ext}"
    return url_from_url(raw, gg, None, ext)


def thumbnail_url(h: str, gg: GG) -> str:
    raw = f"https://a.{MEDIA_DOMAIN}/webpbigtn/{real_full_path(h)}.webp"
    return url_from_url(raw, gg, base="tn")


def gallery_js_url(gallery_id: int) -> str:
    return f"https://{LTN_HOST}/galleries/{gallery_id}.js"


def gg_js_url() -> str:
    return f"https://{LTN_HOST}/gg.js"


def reader_referer(gallery_id: int) -> str:
    """Referer del lector (válido, pero para descargar imágenes se usa IMAGE_REFERER como el downloader de referencia)."""
    return f"https://hitomi.la/reader/{gallery_id}.html"
