"""Utilidades de texto: idioma de un fragmento (por escritura y palabras) y limpieza del OCR.

Sirve para dos cosas:
  - que cada viñeta se lea con la voz del idioma que realmente tiene el texto (no todo en inglés);
  - descartar la basura que el OCR "lee" en el dibujo, para que la voz no diga cosas sin sentido.
"""
import re

RE_HANGUL = re.compile(r"[\uac00-\ud7af\u1100-\u11ff]")
RE_KANA = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff]")
RE_HAN = re.compile(r"[\u4e00-\u9fff]")
RE_CJK_ANY = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff\u4e00-\u9fff\uac00-\ud7af]")

STOP = {
    "es": {"el", "la", "los", "las", "de", "del", "que", "y", "en", "un", "una", "por", "con", "no", "se", "para",
           "es", "lo", "mi", "tu", "te", "me", "su", "al", "pero", "como", "más", "mas", "está", "esta", "estoy",
           "eres", "soy", "muy", "ya", "qué", "quién", "cómo", "aquí", "ahora", "todo", "nada", "algo", "yo",
           "él", "ella", "nos", "les", "le", "si", "sí", "hay", "tengo", "quiero", "puedo", "vamos", "porque",
           "cuando", "donde", "dónde", "también", "tan", "bien", "tú", "usted", "esto", "eso", "ese", "esa"},
    "en": {"the", "and", "you", "to", "of", "is", "in", "it", "that", "i", "a", "for", "on", "are", "this", "with",
           "my", "me", "your", "what", "not", "but", "was", "be", "have", "do", "don't", "it's", "i'm", "he", "she",
           "we", "they", "can", "will", "just", "so", "if", "no", "yes", "how", "why", "here", "now", "all", "oh",
           "please", "like", "want", "know", "going", "get", "there", "from", "at", "up", "out"},
    "fr": {"le", "la", "les", "des", "est", "et", "un", "une", "je", "tu", "il", "elle", "nous", "vous", "pas",
           "que", "qui", "dans", "pour", "avec", "sur", "ce", "mais", "ne", "suis", "très"},
    "pt": {"o", "os", "as", "um", "uma", "não", "que", "de", "do", "da", "em", "para", "com", "eu", "você", "é",
           "está", "mais", "mas", "muito", "isso", "ele", "ela", "nós"},
    "it": {"il", "lo", "gli", "di", "che", "è", "un", "una", "non", "per", "con", "io", "tu", "sono", "ma", "più",
           "questo", "molto", "ciao"},
    "de": {"der", "die", "das", "und", "ist", "nicht", "ich", "du", "sie", "ein", "eine", "mit", "für", "auf",
           "aber", "zu", "den", "dem", "wir"},
}
SPECIAL = {"es": "ñ¿¡áéíóú", "fr": "çàèùâêîôûëïœ", "pt": "ãõçâêô", "it": "àèìòù", "de": "äöüß"}
_WORD = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?", re.UNICODE)


def detect_text_lang(text, default=None):
    """Idioma del texto: 'ko', 'ja', 'zh', 'es', 'en'... o `default` si no hay datos suficientes."""
    text = text or ""
    from ocr_langs import script_lang          # alfabetos que deciden solos: ruso, árabe, hebreo, griego, tailandés, hindi…
    sl = script_lang(text)
    if sl:
        return sl
    hangul = len(RE_HANGUL.findall(text))
    kana = len(RE_KANA.findall(text))
    han = len(RE_HAN.findall(text))
    if hangul >= 1 and hangul >= kana:
        return "ko"
    if kana >= 1:
        return "ja"
    if han >= 2:
        return "zh"
    low = text.lower()
    words = _WORD.findall(low)
    if not words:
        return default
    score = {}
    for lang, stops in STOP.items():
        s = sum(1 for w in words if len(w) >= 2 and w in stops)
        s += 2 * sum(low.count(c) for c in SPECIAL.get(lang, "") if lang in ("es",))
        score[lang] = s
    # Letras especiales de otros idiomas latinos (pesan menos que las palabras)
    for lang in ("fr", "pt", "it", "de"):
        score[lang] += sum(low.count(c) for c in SPECIAL[lang]) * 0.5
    best = max(score, key=score.get)
    if score[best] <= 0:
        return default
    # Empate español/inglés: manda el idioma de la obra
    if default in score and score[default] >= score[best]:
        return default
    return best


# ------------------------------------------------------------------ limpieza
_KEEP = re.compile(r"[^\w\s.,;:!?¡¿'\"“”‘’()\-—–…~%&/+*\u3000-\u303f\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af\uff01-\uff5e\u0300-\u036f\u0590-\u06ff\u0900-\u09ff\u0b80-\u0bff\u0e00-\u0e7f]",
                   re.UNICODE)
_VOWELS = set("aeiouyáéíóúüàèìòùâêîôûãõäöæœ")
_ONE_LETTER_OK = {"a", "y", "o", "e", "u", "i", "à", "é", "è", "ô", "à"}


def _wordlike(tok, lang_stops):
    t = tok.lower()
    if t in lang_stops:
        return True
    letters = [c for c in t if c.isalpha()]
    if len(letters) < 2:
        return False
    v = sum(c in _VOWELS for c in letters)
    ratio = v / len(letters)
    return 0.15 <= ratio <= 0.85


def clean_ocr(text):
    """Limpia texto de OCR: quita símbolos raros, guiones de corte y fragmentos sueltos."""
    if not text:
        return ""
    text = text.replace("\u00ad", "")
    text = re.sub(r"-\s*\n\s*", "", text)          # palabra cortada con guion al final de línea
    lines = []
    for ln in text.splitlines():
        ln = _KEEP.sub(" ", ln)
        ln = re.sub(r"\s+", " ", ln).strip(" -—–_~*+/&")
        if not ln:
            continue
        compact = ln.replace(" ", "")
        alnum = sum(c.isalnum() for c in compact)
        if alnum < 1 or alnum / max(1, len(compact)) < 0.55:
            continue
        lines.append(ln)
    out = " ".join(lines)
    out = re.sub(r"(?<=[\u3040-\u30ff\u4e00-\u9fff])\s+(?=[\u3040-\u30ff\u4e00-\u9fff])", "", out)   # sin espacios entre kana/kanji
    out = re.sub(r"\s+([,.;:!?…])", r"\1", out)
    out = re.sub(r"([¡¿])\s+", r"\1", out)
    return out.strip()


def readable(text, default_lang="es"):
    """True si el texto parece lenguaje real y no basura del OCR."""
    if not text:
        return False
    cjk = len(RE_CJK_ANY.findall(text))
    if cjk:
        return cjk >= 2 or len(text.strip()) >= 3
    from ocr_langs import script_of
    sc = script_of(text)
    if sc and sc != "latin":                       # ruso, árabe, hebreo, griego, tailandés, hindi…: sin el filtro de vocales latinas
        letters = sum(c.isalpha() for c in text)
        return letters >= 2 and letters / max(1, len(text.replace(" ", ""))) >= 0.5
    toks = _WORD.findall(text)
    if not toks:
        return False
    stops = set().union(*STOP.values())
    good = [t for t in toks if _wordlike(t, stops)]
    if not good:
        return False
    # al menos la mitad de las palabras deben parecer palabras; una sola palabra debe ser razonable
    if len(toks) == 1:
        return len(toks[0]) >= 2 and good[0] == toks[0]
    return len(good) / len(toks) >= 0.5 and sum(len(g) for g in good) >= 4


def drop_stray_tokens(text):
    """Quita letras sueltas que el OCR inventa (una 'x', una 'l'...), salvo palabras de una letra válidas."""
    from ocr_langs import script_of
    if script_of(text) not in (None, "latin"):    # en ruso/griego/árabe… hay palabras válidas de una letra (я, в, и, α…)
        return text
    out = []
    for tok in text.split(" "):
        core = re.sub(r"^\W+|\W+$", "", tok)
        if len(core) == 1 and core.isalpha() and core.lower() not in _ONE_LETTER_OK and not RE_CJK_ANY.match(core):
            continue
        out.append(tok)
    return " ".join(out)


def tts_ready(text):
    """Prepara el texto para la voz: sin símbolos que se leen mal ni gritos en MAYÚSCULAS deletreadas."""
    text = text or ""
    text = re.sub(r"[♡♥❤☆★♪♫♬→←↑↓•●○◆◇■□▲△▼▽※]", " ", text)
    text = re.sub(r"[~*_#^|\\<>{}\[\]]", " ", text)
    text = re.sub(r"([!?！？])\1{2,}", r"\1\1", text)
    text = re.sub(r"\.{4,}", "...", text)

    def soften(m):
        w = m.group(0)
        return w.capitalize() if len(w) > 3 else w
    text = re.sub(r"\b[A-ZÁÉÍÓÚÑÜ]{4,}\b", soften, text)
    text = re.sub(r"\s+", " ", text).strip()
    return text if sum(c.isalpha() for c in text) >= 2 else ""


def fix_english(text):
    """Arregla confusiones típicas del OCR en texto inglés de cómic (casi siempre en MAYÚSCULAS)."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return text
    caps = sum(c.isupper() for c in letters) / len(letters)
    out = text
    if caps >= 0.7:
        out = re.sub(r"(?<=[A-Z])0(?=[A-Z])", "O", out)           # D0N'T -> DON'T
        out = re.sub(r"(?<=[A-Z])1(?=[A-Z])", "I", out)           # 1T -> IT
        out = re.sub(r"\b1(?=['’][A-Z]|\s[A-Z])", "I", out)       # 1'M -> I'M
        out = re.sub(r"\bl(?=['’][A-Z]|\s[A-Z])", "I", out)       # l'M -> I'M
        out = re.sub(r"(?<=[A-Z])l(?=[A-Z])", "I", out)           # HELLl -> HELLI (mejor que minúscula suelta)
    out = re.sub(r"\bl\b", "I", out) if caps >= 0.7 else out
    out = re.sub(r"\s*\|\s*", " I ", out) if "|" in out and caps >= 0.7 else out
    return re.sub(r"\s+", " ", out).strip()
