"""Puerta de seguridad: bloquea toda estimulación si una viñeta indica personajes menores.

Copia pura (sin cv2 ni onnxruntime) de la lógica de safety.py + tagger.MINOR_TAGS.
tests_python/test_seguridad.py comprueba que los conjuntos coinciden con tagger.py: si alguien
cambia uno, la prueba falla. No es desactivable.
"""
import re

MINOR_TAGS = {"child", "female_child", "male_child", "toddler", "infant", "baby",
              "loli", "shota", "aged_down"}
GALLERY_MINOR_TERMS = {"lolicon", "shotacon", "loli", "shota", "child", "children", "toddler", "infant", "baby",
                       "underage", "aged_down", "female_child", "male_child"}
_ALL = {t.lower() for t in MINOR_TAGS} | GALLERY_MINOR_TERMS


def norm(tag):
    tag = str(tag).strip().lower()
    tag = tag.split(":")[-1]                      # "female:lolicon" -> "lolicon"
    return re.sub(r"[\s\-]+", "_", tag)


def minor_hits(tags):
    """Términos de `tags` que indican personajes menores."""
    return sorted({norm(t) for t in tags if norm(t) in _ALL})


def block_panel(p):
    p.update(blocked=True, rest=True, suction=False, climax=False, intensity=0.0)
    p["motion"] = False
    return p


def apply_gate(panels, gallery_tags=()):
    """Bloquea paneles por etiquetas de galería (todos) o propias del panel. Devuelve cuántos bloqueó."""
    gallery_hit = bool(minor_hits(gallery_tags))
    n = 0
    for p in panels:
        own = minor_hits([t[0] if isinstance(t, (tuple, list)) else t for t in p.get("tags", [])])
        if gallery_hit or own or p.get("blocked"):
            block_panel(p)
            n += 1
    return n
