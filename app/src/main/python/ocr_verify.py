"""Verificador de coherencia del OCR (rápido, sin red ni modelos): ¿esto es lenguaje real o letras inventadas?

Qué hace con cada texto leído por el OCR (cada globo / caja / texto suelto):
  1. LIMPIA: quita letras y «palabras» sueltas que el OCR inventa en las rayas y tramas (una «x», «hy», «Xs», un «4»…).
  2. CORRIGE: arregla confusiones típicas del OCR (0↔O, 1↔I, rn↔m, cl↔d, acentos perdidos), pega palabras partidas («WH AT»),
     separa palabras pegadas («ILOVEYOU») y usa los nombres y palabras que ya aparecieron en el manga para corregir los que
     faltan en el diccionario (un personaje que se llama «Haruka» no se «corrige» a otra cosa).
  3. PUNTÚA: devuelve 0-1 según cuántas palabras son reales, qué tan buena fue la confianza del OCR y si el alfabeto encaja
     con el resto de la obra. Con eso el programa decide si lo lee en voz alta o lo descarta.
Idiomas: español e inglés con vocabulario propio; japonés, coreano y chino con comprobaciones de caracteres y estructura;
el resto de idiomas latinos con comprobación de ortografía básica (sin descartar de más).
Velocidad: unos 0,2-2 ms por globo (el vocabulario se carga una vez, ~0,3 s). No hay ninguna llamada a internet.
"""
from __future__ import annotations

import gzip
import os
import re
import threading
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))

_LANG_ALIASES = {"eng": "en", "spa": "es", "jpn": "ja", "jpn_vert": "ja", "kor": "ko", "chi_sim": "zh", "chi_tra": "zh",
                 "fra": "fr", "por": "pt", "ita": "it", "deu": "de", "en": "en", "es": "es", "ja": "ja", "ko": "ko",
                 "zh": "zh", "zh-tw": "zh", "ja-vert": "ja"}


def norm_lang(lang: str | None, default: str = "en") -> str:
    """'eng+spa' → 'en'; 'jpn_vert' → 'ja'; 'es-MX' → 'es'. Devuelve el idioma principal."""
    if not lang:
        return default
    first = str(lang).split("+")[0].strip()
    return _LANG_ALIASES.get(first, _LANG_ALIASES.get(first.split("-")[0], first.split("-")[0][:2] or default))


# --------------------------------------------------------------------------------------------------------- vocabularios
_LOCK = threading.Lock()


def strip_accents(w: str) -> str:
    out = []
    for ch in unicodedata.normalize("NFD", w):
        if unicodedata.category(ch) == "Mn" and ch != "̃":
            continue
        out.append(ch)
    return unicodedata.normalize("NFC", "".join(out))


_EN_COMMON = set("""the be to of and a in that have i it for not on with he as you do at this but his by from they we say her she or an will
my one all would there their what so up out if about who get which go me when make can like time no just him know take people into year
your good some could them see other than then now look only come its over think also back after use two how our work first well way
even new want because any these give day most us is are was were been has had did does am dont don't im i'm ive i've ill i'll id i'd
youre you're thats that's whats what's lets let's cant can't wont won't isnt isn't arent aren't wasnt wasn't didnt didn't doesnt
doesn't hes he's shes she's theyre they're hello hi hey oh ah um uh yes yeah ok okay please sorry thanks thank sir mr mrs ms miss
san kun chan sama senpai sensei""".split())

_EN_INTERJ = re.compile(r"^(?:a+h+|a+w+|a+r+g+h*|a+h+a+|o+h+|o+o+h+|o+w+|o+o+p+s+|o+p+s+|e+h+|e+w+|e+k+|e+e+k+|u+h+|u+m+|u+g+h+|u+r+g+h*|"
                        r"h+m+|h+m+p+h*|m+m+|m+m+h+|m+p+h+|n+g+h+|n+n+g+h*|h+u+h+|h+a+h*|h+a+(?:h+a+)+h*|h+e+(?:h+e+)+|h+i+(?:h+i+)+|"
                        r"w+o+w+|y+a+y+|y+i+k+e+s+|g+a+s+p+|s+i+g+h+|p+s+s+t+|s+h+h+|s+h+|t+s+k+|t+c+h+|b+l+e+h+|y+a+h+|n+o+|n+a+h+|"
                        r"h+u+f+f*|p+h+e+w+|t+h+u+d+|b+a+m+|b+o+o+m+|w+h+a+t+|h+e+y+|y+o+|y+a+|y+u+p+|n+o+p+e+)$", re.I)
_ES_INTERJ = re.compile(r"^(?:a+h+|a+y+|a+j+|a+j+a+|o+h+|o+j+o+|e+h+|e+y+|u+f+|u+y+|u+h+|h+m+|m+m+|m+m+h+|h+u+m+|h+a+(?:h*a+)*|"
                        r"j+a+(?:j*a+)+|j+e+(?:j*e+)+|j+i+(?:j*i+)+|j+o+(?:j*o+)+|a+u+|u+g+h+|n+g+h+|h+u+y+|b+a+h+|p+u+f+|p+s+s+t+|"
                        r"s+h+|c+h+i+s+t+|e+a+|e+p+a+|o+l+e+|u+a+u+|g+u+a+u+|u+p+s+|a+h+a+|o+o+|a+a+)$", re.I)

_EN_BAD_PAIRS = set("""bq bx cj cv cx dx fq fv fx gq gx hx jb jc jd jf jg jh jk jl jm jn jp jq jr js jt jv jw jx jz kq kx kz mq mx pq px
qb qc qd qf qg qh qj qk ql qm qn qp qq qr qs qt qv qw qx qy qz sx tq tx vb vc vd vf vg vh vj vk vl vm vn vp vq vs vt vw vx vz wq wx
xb xd xg xj xk xq xv xz zb zd zf zg zj zk zq zs zv zx""".split())
_ES_OK_PAIRS = set("""bl br cl cr dr fl fr gl gr pl pr tr ch ll rr qu gu ns nt nd nc ng nf nq nv nm nj ls lt ld lc lg lm lp lv lb rs rt
rd rc rg rm rn rp rb rf rl rv rz rj st sp sc sm sn sb sd sg sl sf sq sv bs bt bj ct cc cn cs pt ps pn gn gm mp mb mn tl tm xp xc xt xh
dm dv dj zg zc cq kr kl sk""".split())
_CONSONANTS = set("bcdfghjklmnñpqrstvwxz")
_VOWELS = set("aeiouyáéíóúüàèìòùâêîôûãõäöæœ")

_CONFUSE = [  # (lo que leyó el OCR, lo que probablemente era)
    ("0", "o"), ("1", "i"), ("1", "l"), ("|", "i"), ("5", "s"), ("8", "b"), ("6", "g"), ("2", "z"), ("l", "i"), ("i", "l"),
    ("rn", "m"), ("m", "rn"), ("vv", "w"), ("cl", "d"), ("d", "cl"), ("c", "e"), ("e", "c"), ("u", "v"), ("v", "u"), ("n", "h"),
    ("h", "n"), ("a", "o"), ("o", "a"), ("q", "g"), ("g", "q"), ("ii", "u"), ("t", "f"), ("f", "t"), ("b", "h"), ("h", "b"),
    ("1", "t"), ("l", "t"), ("t", "l"), ("s", "z"), ("z", "s"), ("n", "r"), ("r", "n"), ("e", "o"), ("o", "e"), ("u", "o"),
    ("a", "e"), ("e", "a"), ("i", "t"), ("i", "j"), ("j", "i"), ("y", "v"), ("v", "y"),
]

_SHORT_OK = {"en": set("a i o ok oh ah eh uh um hm mm no so we he me my by us up to do go is it in on at an as be if of or ya yo hi aw ow".split()),
             "es": set("a y o e u no si sí me te se le lo la el un en es de da di do mi tu su yo ya ay ah oh eh uf ok va ve ha he hi ir ido al ni".split())}
_cache: dict = {}


class Lexicon:
    def __init__(self, lang: str, words: set[str], common: set[str] = frozenset()):
        self.lang = lang
        self.words = words
        self.common = set(common) & words | set(common)
        self.noacc: dict[str, str] = {}
        if lang == "es":
            for w in words:
                k = strip_accents(w)
                if k != w:
                    self.noacc.setdefault(k, w)
        self.alpha = "abcdefghijklmnopqrstuvwxyz" + ("áéíóúüñ" if lang == "es" else "'")

    def has(self, w: str) -> bool:
        return w in self.words

    def canon(self, w: str):
        """Palabra del vocabulario equivalente a `w` (acentos opcionales) o None."""
        if w in self.words:
            return w
        if self.lang == "es":
            return self.noacc.get(strip_accents(w))
        return None


def _load_en() -> Lexicon:
    words = set()
    p = os.path.join(HERE, "lexicon", "en.txt.gz")
    if os.path.isfile(p):
        with gzip.open(p, "rt", encoding="utf-8") as f:
            words.update(f.read().split("\n"))
    words.update(_EN_COMMON)
    for w in list(words):                                              # dont, cant, im, youre… (el OCR pierde el apóstrofo)
        if "'" in w and len(w) <= 12:
            words.add(w.replace("'", ""))
    words.update({"ok", "okay", "yeah", "yep", "nope", "gonna", "wanna", "gotta", "kinda", "sorta", "lemme", "gimme", "dunno",
                  "ya", "yo", "huh", "hmm", "uh", "um", "ugh", "aw", "ow", "eww", "wow", "whoa", "yay", "oops", "hah", "haha"})
    words.discard("")
    return Lexicon("en", words, _EN_COMMON)


def _load_es() -> Lexicon:
    import lexdata_es
    words = lexdata_es.build()
    words.update({"ok", "okay", "vale", "hmm", "ugh", "wow", "guau"})
    return Lexicon("es", words, set(lexdata_es.FUNC))


def lexicon(lang: str) -> Lexicon | None:
    lang = norm_lang(lang)
    if lang not in ("en", "es"):
        return None
    with _LOCK:
        lx = _cache.get(lang)
        if lx is None:
            lx = _cache[lang] = _load_en() if lang == "en" else _load_es()
    return lx


def warm_up(langs=("en", "es")) -> None:
    """Carga los vocabularios (llámalo en un hilo al abrir una obra: tarda ~0,3 s la primera vez)."""
    for lg in langs:
        lexicon(lg)


# --------------------------------------------------------------------------------------------------------- contexto de la obra
@dataclass
class WorkContext:
    """Memoria de UNA obra: nombres y palabras repetidas, alfabetos vistos y color de los globos de cada hablante."""
    vocab: Counter = field(default_factory=Counter)
    scripts: Counter = field(default_factory=Counter)
    lang_hint: str = ""
    speakers: list = field(default_factory=list)          # [{'id': 'S1', 'lab': (L,a,b), 'n': int}]
    accepted: int = 0
    rejected: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def known(self, tok: str) -> bool:
        return self.vocab.get(tok, 0) >= 2

    def observe(self, tokens, script: str, quality: float) -> None:
        with self._lock:
            self.accepted += 1
            self.scripts[script] += 1
            if quality >= 0.7:
                for t in tokens:
                    if len(t) >= 3:
                        self.vocab[t] += 1

    def script_share(self, script: str) -> float:
        tot = sum(self.scripts.values())
        return self.scripts.get(script, 0) / tot if tot else 1.0

    def speaker_for(self, lab, chroma_min: float = 14.0, tol: float = 13.0):
        """Id de hablante según el color del globo (Lab de OpenCV). None si el globo es blanco/gris (sin color propio)."""
        L, a, b = [float(v) for v in lab]
        chroma = ((a - 128.0) ** 2 + (b - 128.0) ** 2) ** 0.5
        with self._lock:
            best, bd = None, 1e9
            for s in self.speakers:
                d = ((s["lab"][1] - a) ** 2 + (s["lab"][2] - b) ** 2) ** 0.5 + 0.25 * abs(s["lab"][0] - L)
                if d < bd:
                    best, bd = s, d
            if best is not None and bd <= tol:
                best["n"] += 1
                n = best["n"]
                best["lab"] = tuple((o * (n - 1) + v) / n for o, v in zip(best["lab"], (L, a, b)))
                return best["id"]
            neutral = chroma < chroma_min
            if neutral and best is None and not self.speakers:
                pass
            sid = f"S{len(self.speakers) + 1}"
            self.speakers.append({"id": sid, "lab": (L, a, b), "n": 1, "neutral": neutral})
            return sid

    def reset(self) -> None:
        with self._lock:
            self.vocab.clear()
            self.scripts.clear()
            self.speakers.clear()
            self.accepted = self.rejected = 0


WORK = WorkContext()


def reset_work() -> None:
    """Llamar al abrir otra obra: borra la memoria de nombres, alfabetos y hablantes."""
    WORK.reset()


# --------------------------------------------------------------------------------------------------------- resultado
@dataclass
class Verdict:
    text: str                                   # texto limpio y corregido ('' si se descarta)
    orig: str
    score: float                                # 0-1 (calidad global)
    lex: float                                  # 0-1 (solo palabras reales)
    ok: bool
    lang: str = ""
    changes: list = field(default_factory=list)  # [(antes, después)]
    flags: list = field(default_factory=list)
    reason: str = ""


# --------------------------------------------------------------------------------------------------------- latín
_TOK = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*|\d+|[^\w\s]|\s+|_", re.UNICODE)
_WORDRE = re.compile(r"^[^\W\d_]+(?:['’][^\W\d_]+)*$", re.UNICODE)
_DIGIT_FIX = {"0": "o", "1": "i", "5": "s", "8": "b", "6": "g", "2": "z", "4": "a", "3": "e", "7": "t"}


_DIG_IN_WORD = re.compile(r"(?<=[^\W\d_])[0-9|](?=[^\W\d_'’])|(?<=[^\W\d_'’])[0-9|](?=[^\W\d_])")


def _fix_digits(t: str) -> str:
    """«D0N'T» → «DON'T»: un dígito pegado a letras es casi siempre una letra mal leída."""
    def one(m):
        r = _DIGIT_FIX.get(m.group(0), "i" if m.group(0) == "|" else m.group(0))
        a, b = m.string[max(0, m.start() - 1)], m.string[m.end():m.end() + 1]
        return r.upper() if (a.isupper() or b.isupper()) else r
    return " ".join(_DIG_IN_WORD.sub(one, c) if sum(x.isalpha() for x in c) >= 2 else c for c in re.split(r"(?<=\s)|(?=\s)", t))


def ortho_ok(w: str, lang: str) -> bool:
    """¿Se puede pronunciar como palabra de `lang` (es/en/otros latinos)? Descarta «xkqt», «hy», «Xs»…"""
    w = w.lower().replace("’", "'")
    letters = [c for c in w if c.isalpha()]
    n = len(letters)
    if n == 0:
        return False
    if n == 1:
        return letters[0] in ("a", "y", "o", "e", "u", "i") if lang != "en" else letters[0] in ("a", "i", "o")
    vow = sum(c in _VOWELS for c in letters)
    if vow == 0:
        return False
    if n >= 4 and not 0.18 <= vow / n <= 0.85:
        return False
    if re.search(r"(.)\1\1", w) and not re.search(r"(?:a|o|e|u|h|m|s|z)\1\1", w):
        return False
    run = 0
    cons = []
    for c in letters + [" "]:
        if c in _CONSONANTS:
            cons.append(c)
        else:
            if len(cons) >= 2:
                if lang == "es":
                    if len(cons) > 3 or any((cons[i] + cons[i + 1]) not in _ES_OK_PAIRS and cons[i] != cons[i + 1] or
                                            (cons[i] == cons[i + 1] and cons[i] not in "lrcn") for i in range(len(cons) - 1)):
                        return False
                else:
                    if len(cons) > 4 or any((cons[i] + cons[i + 1]) in _EN_BAD_PAIRS for i in range(len(cons) - 1)):
                        return False
            cons = []
    if "q" in w and re.search(r"q(?!u)", w) and lang in ("es", "en") and w not in ("qi", "qat", "faq"):
        return False
    return True


def _case_like(src: str, new: str) -> str:
    if src.isupper() and len(src) > 1:
        return new.upper()
    if src[:1].isupper():
        return new[:1].upper() + new[1:]
    return new


def _edits1(w: str, alpha: str):
    sp = [(w[:i], w[i:]) for i in range(len(w) + 1)]
    for a, b in sp:
        if b:
            yield a + b[1:]
        if len(b) > 1:
            yield a + b[1] + b[0] + b[2:]
        if b:
            for c in alpha:
                yield a + c + b[1:]
        for c in alpha:
            yield a + c + b


def _confusions(w: str):
    for old, new in _CONFUSE:
        start = 0
        while True:
            i = w.find(old, start)
            if i < 0:
                break
            yield w[:i] + new + w[i + len(old):]
            start = i + 1


def _known(lx: Lexicon, ctx: WorkContext, low: str):
    """(forma canónica, fuente) con fuente 'lex'|'ctx'|'inter' o (None, '')."""
    if low in lx.words:
        return low, "lex"
    c = lx.canon(low)
    if c:
        return c, "lex"
    if "'" in low:
        b = low.replace("’", "'")
        if b in lx.words:
            return b, "lex"
        if b.endswith("'s") and b[:-2] in lx.words:
            return b, "lex"
    if lx.lang == "es":
        import lexdata_es
        base = lexdata_es.strip_clitics(low, lx.words)
        if base:
            return low, "lex"
        for suf, rep in (("mente", ""), ("ito", "o"), ("ita", "a"), ("itos", "os"), ("itas", "as"), ("illo", "o"), ("illa", "a"),
                         ("ísimo", "o"), ("ísima", "a"), ("ón", "")):
            if low.endswith(suf) and len(low) > len(suf) + 2 and (low[:-len(suf)] + rep) in lx.words:
                return low, "lex"
    else:
        for suf in ("ness", "less", "ful", "ish", "like", "y", "er", "ers", "ly"):
            if low.endswith(suf) and len(low) > len(suf) + 2 and low[:-len(suf)] in lx.words:
                return low, "lex"
    if ctx.known(low):
        return low, "ctx"
    if lx.lang == "en" and _EN_INTERJ.match(low) or lx.lang == "es" and _ES_INTERJ.match(low):
        return low, "inter"
    sq = re.sub(r"(.)\1{2,}", r"\1\1", low)                           # «noooo», «helloooo»
    if sq != low:
        k, src = _known(lx, ctx, sq)
        if k:
            return low, src
        sq1 = re.sub(r"(.)\1+", r"\1", low)
        if sq1 in lx.words:
            return low, "lex"
    return None, ""


def _best_candidate(lx: Lexicon, ctx: WorkContext, low: str, conf: float):
    """Corrección más probable de una palabra desconocida. Devuelve (palabra, coste) o (None, 0)."""
    n = len(low)
    best, bc = None, 99.0
    pool = {}
    for c in _confusions(low):                                         # el OCR confundió letras parecidas: coste bajo
        pool[c] = 0.6
    for c in set(_edits1(low, lx.alpha)):
        pool.setdefault(c, 1.0)
    if n >= 7:
        for c1 in list(pool)[:80]:
            for c2 in _confusions(c1):
                pool.setdefault(c2, 1.4)
    for c, cost in pool.items():
        if not c or c == low:
            continue
        k, src = _known(lx, ctx, c)
        if not k or src == "inter" and n < 4:
            continue
        cc = cost + (0.0 if src == "ctx" else 0.0) - (0.25 if c in lx.common else 0.0) - (0.3 if src == "ctx" else 0.0)
        if len(c) < 2 or (len(c) == 2 and c not in lx.common):
            cc += 1.0
        if cc < bc:
            best, bc = c, cc
    if best is None:
        return None, 0.0
    maxcost = 0.9 if n <= 3 else 1.1 if n <= 5 else 1.5
    if conf and conf >= 88:
        maxcost -= 0.3                                                # el OCR estaba seguro: solo arreglos muy baratos
    return (best, bc) if bc <= maxcost else (None, 0.0)


def _segment(lx: Lexicon, ctx: WorkContext, low: str):
    """Separa una palabra larga desconocida en 2-3 palabras reales («iloveyou» → i love you). None si no se puede."""
    n = len(low)
    if n < 5 or n > 24:
        return None
    best = {0: (0.0, [])}
    for i in range(1, n + 1):
        cand = None
        for j in range(max(0, i - 14), i):
            if j not in best:
                continue
            piece = low[j:i]
            k, src = _known(lx, ctx, piece)
            if not k or (len(piece) == 1 and piece not in ("a", "i", "y", "o", "e", "u")) or len(piece) == 2 and piece not in lx.common:
                continue
            cost = best[j][0] + 1.0 - min(len(piece), 8) * 0.05 + (0.0 if piece in lx.common else 0.4)
            if cand is None or cost < cand[0]:
                cand = (cost, best[j][1] + [piece])
        if cand:
            best[i] = cand
    if n in best and 2 <= len(best[n][1]) <= 3:
        return best[n][1]
    return None


_THRESH = {"suave": 0.0, "normal": 0.1, "estricto": 0.2}


def _verify_latin(text: str, lang: str, conf: float | None, kind: str, ctx: WorkContext, strict: str) -> Verdict:
    lx = lexicon(lang)
    text = _fix_digits(text)
    if lang == "en":                                                  # «1 AM HOME» → «I AM HOME» (la I inicial se lee como 1 o |)
        text = re.sub(r"(^|[.!?…]\s+)[1|l](?=\s+[A-Za-z]{2,})", lambda m: m.group(1) + "I", text)
    toks = _TOK.findall(text)
    conf_v = float(conf) if conf is not None else 80.0
    changes, flags = [], []
    if lx is not None:                                               # «WH AT» → «WHAT» antes de corregir cada trozo
        j = 0
        while j < len(toks) - 2:
            a, sp, b = toks[j], toks[j + 1], toks[j + 2]
            if (_WORDRE.match(a) and _WORDRE.match(b) and sp.isspace() and len(a) + len(b) >= 3
                    and not _known(lx, ctx, a.lower())[0] and (len(b) <= 3 or not _known(lx, ctx, b.lower())[0])
                    and _known(lx, ctx, (a + b).lower())[0]):
                changes.append((a + " " + b, a + b))
                toks[j:j + 3] = [a + b]
                continue
            j += 1
    items = []                                                        # [kind, texto, peso_letras, válido(0-1), forma]
    # --- 1) palabras: reparar cada una
    for t in toks:
        if not _WORDRE.match(t):
            items.append(["x", t, 0, 0.0])
            continue
        raw = t.replace("’", "'")
        low = raw.lower()
        if lx is None:                                                # otros idiomas latinos: solo ortografía básica
            from textproc import STOP
            stops = set().union(*STOP.values())
            valid = 1.0 if low in stops else (0.6 if ortho_ok(low, "x") and len(low) >= 3 else 0.25 if ortho_ok(low, "x") else 0.0)
            items.append(["w", raw, len(low), valid])
            continue
        k, src = _known(lx, ctx, low)
        if k:
            short_bad = len(low) <= 2 and low not in lx.common and src != "ctx" and low not in _SHORT_OK[lang if lang in _SHORT_OK else "en"]
            items.append(["w", raw, len(low), 0.15 if short_bad else 1.0 if src != "inter" else 0.85])
            continue
        # palabra desconocida
        if (raw[:1].isupper() and not raw.isupper() and len(low) >= 4 and conf_v >= 75 and ortho_ok(low, lang)):
            ctx.vocab[low] += 1                                       # nombre propio (Haruka, Tanaka…): se conserva y se aprende
            items.append(["w", raw, len(low), 0.75])
            continue
        if len(low) >= 2:
            cand, cost = _best_candidate(lx, ctx, low, conf_v)
            seg = None if cand else _segment(lx, ctx, low)
            if cand:
                new = _case_like(raw, cand)
                changes.append((raw, new))
                items.append(["w", new, len(cand), 0.9])
                continue
            if seg:
                new = " ".join(seg)
                if raw.isupper():
                    new = new.upper()
                elif raw[:1].isupper():
                    new = new[:1].upper() + new[1:]
                changes.append((raw, new))
                for s, sc in zip(seg, new.split(" ")):
                    items.append(["w", sc, len(s), 0.9])
                    items.append(["x", " ", 0, 0.0])
                items.pop()
                continue
        ok_o = ortho_ok(low, lang)
        L = len(low)
        if L == 1:
            valid = 0.0
        elif not ok_o:
            valid = 0.0
        elif L == 2:
            valid = 0.12
        elif L == 3:
            valid = 0.3
        else:
            valid = 0.5 if (raw[:1].isupper()) else 0.4
        items.append(["w", raw, L, valid])
    # --- 2) palabras partidas por el OCR: «WH AT» → «WHAT»
    i = 0
    while lx is not None and i < len(items) - 2:
        a, sp, b = items[i], items[i + 1], items[i + 2]
        if (a[0] == "w" and b[0] == "w" and sp[0] == "x" and sp[1].isspace() and a[3] < 0.5 and b[3] < 0.5
                and len(a[1]) + len(b[1]) >= 3):
            joined = (a[1] + b[1]).lower()
            k, src = _known(lx, ctx, joined)
            if k:
                changes.append((a[1] + " " + b[1], _case_like(a[1], joined)))
                items[i:i + 3] = [["w", _case_like(a[1] if a[1].isupper() else a[1], joined) if not a[1].isupper() else joined.upper(),
                                   len(joined), 1.0]]
                continue
        i += 1
    # --- 3) dígitos sueltos dentro de palabras («D0N'T») ya llegan como palabra+dígitos: se arreglan aquí
    # --- 4) puntuación de calidad
    words = [it for it in items if it[0] == "w"]
    tot = sum(min(w[2], 8) for w in words)
    lexs = sum(min(w[2], 8) * w[3] for w in words) / tot if tot else 0.0
    # --- 5) quitar lo inventado: palabras con validez 0 (y dígitos sueltos si hay frase real)
    good_words = [w for w in words if w[3] >= 0.4]
    out_parts = []
    dropped = []
    for it in items:
        if it[0] == "w" and it[3] < (0.3 if strict == "suave" else 0.35 if strict == "normal" else 0.45) and len(words) > 1:
            if not (conf_v >= 93 and len(it[1]) >= 4 and it[3] > 0):
                dropped.append(it[1])
                out_parts.append(None)
                continue
        if it[0] == "x" and re.fullmatch(r"\d+", it[1] or "") and good_words and len(words) > 1:
            out_parts.append(None)
            continue
        out_parts.append(it[1])
    # reconstruir quitando huecos dobles
    s = ""
    for p in out_parts:
        if p is None:
            continue
        s += p
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^[^\w¿¡\"“'(]+|[\s~*_|\\/<>^]+$", "", s)
    s = re.sub(r"\s+([,.;:!?…])", r"\1", s)
    s = re.sub(r"(?<=[¿¡])\s+", "", s)
    if dropped:
        changes.extend((d, "") for d in dropped)
    kept = [w for w, p in zip(items, out_parts) if w[0] == "w" and p is not None]
    letters_kept = sum(len(w[1]) for w in kept)
    # --- 6) puntuación final y decisión
    q = lexs * (0.72 if conf is not None else 1.0) + (conf_v / 100.0) * (0.28 if conf is not None else 0.0)
    n_words = len(kept)
    if n_words == 1 and kept[0][3] < 0.85:
        q = min(q, 0.55)                                              # una sola palabra desconocida: dudosa
    t = _THRESH.get(strict, 0.1)
    if kind == "free":
        need_q, need_lex = 0.72 + t * 0.4, 0.62 + t * 0.4
    elif kind == "sfx":
        need_q, need_lex = 0.0, 0.0
    else:
        need_q, need_lex = 0.46 + t * 0.5, 0.36 + t * 0.5
    ok = bool(s) and letters_kept >= 2 and q >= need_q and lexs >= need_lex
    if ok and kind == "free" and n_words < 2 and letters_kept < 6 and conf_v < 90:
        ok = False                                                    # una palabra corta suelta sobre el dibujo: casi seguro trazos
    if ok and conf is not None and conf_v < 35 and lexs < 0.9:
        ok = False
    reason = "" if ok else f"coherencia baja (léxico {lexs:.2f}, global {q:.2f})"
    return Verdict(s if ok else "", text, round(float(q), 3), round(float(lexs), 3), ok, lang, changes, flags, reason)


# --------------------------------------------------------------------------------------------------------- CJK
_COMMON_JA = set("""一二三四五六七八九十百千万円年月日時分秒人男女子母父兄弟姉妹友私僕俺君彼誰何事物所今前後上下中外内大小高低長短新古好悪早遅多少強弱明
暗白黒赤青手足目口耳顔頭心体声力気愛恋死生命魂夢神魔王様先学校家国町村山川海空雨風火水木金土天地東西南北左右出入行来見聞言話思知分考感使作持待立座開閉始終会合戦争勝負助守殺救
逃追走歩飛泳食飲寝起買売読書歌踊笑泣怒恐驚楽苦痛病薬銭店駅車電音色花草犬猫鳥魚肉米茶酒本紙字名朝昼夜春夏秋冬同違当方的度回番号理由意味問題答間最初全部緒自世界場仕事輩部屋道路橋門
窓階段椅机達貴御殿能可不無有在成変化受取与得失勝敗信頼約束秘密嘘本気真実現過去未来運命宿敵味方仲間家族兄姉先輩後輩先生生徒教室授業試験宿題休憩昼食夕方今朝今夜毎日毎晩一度二度三度
初体験恥辱欲望快感刺激責任許謝感情嬉悲怖怒憎恨羨妬寂孤独幸福平和希望絶対必要重要特別普通危険安全注意準備開始終了続終止進退入退席立座寝顔姿形様子状態関係理解説明確認報告連絡相談""")
_COMMON_ZH = set("""的一是不了人我在有他这为之大来以个中上们到说国和地也子时道出而要于就下得可你年生自会那后能对着事其里所去行过家十用发天如然作方成者多日都三小军二无同么经法当起与好
看学进种将还分此心前面又定见只主没公从样想吗呢吧啊哦嗯啦哈呀哇哎唉爱恨死活命魂梦神魔王爷姐妹哥弟爸妈父母儿女孩男朋友老师同学学校教室工作公司钱家门窗路桥城村山河海空雨风火水木金土东
西南北左右前后里外开关始终走跑飞坐站躺睡醒吃喝买卖读写唱跳笑哭怒怕惊乐苦痛病药店车电话音色花草狗猫鸟鱼肉米茶酒书纸字名早午晚春夏秋冬同样别真假对错问题答案时间最初全部一起自己世界地方
事情东西什么怎么为什么因为所以但是如果虽然已经现在以前以后今天明天昨天永远一定可能应该必须需要重要特别普通危险安全注意准备开始结束继续停止进入退出关系理解说明确认报告联系相谈谢对不起
没关系请谢谢再见你好喂快慢高低长短新旧好坏强弱明暗白黑红蓝绿黄手脚眼口耳脸头心体声力气""")
_COMMON_KO = set("""이가는은을를에의도로와과하고지다나요서어아야그저것수있없한대사인게해때말기자리보오우시여정내들일분제주소거마미비부세전동위국중만안며겠습니까네예죠잖응
왜뭐누구디언제떻진짜너무조금많제발미안워랑좋싫배파졸려프무섭괜찮같런면문물밥집학교선생님친형누언니오빠동생엄빠할머니아버지어머니남녀자신체몸마음눈코입귀손발머리얼굴목소리힘
돈일직장회사시간오늘내일어제지금방금곧항상절대결코혹시아마분명확실히정말진심거짓말비밀약속사랑행복슬픔기쁨화분노두려움무서워죽살생명운명꿈희망미래과거현재""")

_RE_HANGUL = re.compile(r"[가-힯]")
_RE_JAMO = re.compile(r"[㄰-㆏ᄀ-ᇿ]")
_RE_KANA = re.compile(r"[぀-ヿㇰ-ㇿ]")
_RE_HAN = re.compile(r"[一-鿿]")
_RE_HAN_RARE = re.compile(r"[㐀-䶿 0-⩭f豈-﫿⺀-⿟]")
_CJK_NEUTRAL = set("。、！？!?…・～~〜ー—―「」『』（）()[]【】《》〈〉“”‘’\"' .,;:·♡♥♪☆★")
_SMALL_KANA = set("ゃゅょっぁぃぅぇぉャュョッァィゥェォ")


def _verify_cjk(text: str, lang: str, conf: float | None, kind: str, ctx: WorkContext, strict: str) -> Verdict:
    conf_v = float(conf) if conf is not None else 75.0
    s = re.sub(r"\s+", "" if lang in ("ja", "zh") else " ", text).strip()
    changes = []
    # texto «de otro mundo»: letras latinas o símbolos sueltos mezclados con el CJK
    clean = []
    for i, ch in enumerate(s):
        if ch.isspace() or ch in _CJK_NEUTRAL or _RE_HAN.match(ch) or _RE_KANA.match(ch) or _RE_HANGUL.match(ch) or _RE_JAMO.match(ch):
            clean.append(ch)
        elif ch.isdigit() or (ch.isascii() and ch.isalpha()):
            clean.append(ch)
        else:
            changes.append((ch, ""))
    s = "".join(clean).strip()
    if lang in ("ja", "zh"):
        s = re.sub(r"(?<=[぀-ヿ一-鿿])[A-Za-z]{1,2}(?=[぀-ヿ一-鿿])", "", s)     # «ab» entre kanji/kana
        if lang == "zh":
            s = _RE_KANA.sub("", s)
    chars = [c for c in s if c not in _CJK_NEUTRAL and not c.isspace()]
    if not chars:
        return Verdict("", text, 0.0, 0.0, False, lang, changes, [], "sin caracteres")
    tot = 0.0
    for c in chars:
        if lang == "ja":
            if _RE_KANA.match(c):
                w = 1.0
            elif _RE_HAN.match(c):
                w = 1.0 if c in _COMMON_JA else 0.55
            elif _RE_HANGUL.match(c):
                w = 0.1
            elif c.isdigit():
                w = 0.6
            else:
                w = 0.35
        elif lang == "zh":
            if _RE_HAN.match(c):
                w = 1.0 if c in _COMMON_ZH else 0.6
            elif _RE_KANA.match(c) or _RE_HANGUL.match(c):
                w = 0.1
            elif c.isdigit():
                w = 0.6
            else:
                w = 0.35
        else:
            if _RE_HANGUL.match(c):
                w = 1.0 if c in _COMMON_KO else 0.6
            elif _RE_JAMO.match(c):
                w = 0.9
            elif _RE_HAN.match(c):
                w = 0.35
            elif _RE_KANA.match(c):
                w = 0.1
            elif c.isdigit():
                w = 0.6
            else:
                w = 0.35
        if _RE_HAN_RARE.match(c):
            w = min(w, 0.1)
        tot += w
    lexs = tot / len(chars)
    if lang == "ja" and s and (s[0] in _SMALL_KANA or s[0] == "ー"):
        lexs *= 0.7
        s = s.lstrip("".join(_SMALL_KANA) + "ー")
    if re.search(r"(.)\1{5,}", s) and not re.search(r"([ー～~〜…・.!?！？ㅋㅎㅠㅜ])\1{5,}", s):
        lexs *= 0.5
    q = lexs * 0.65 + (conf_v / 100.0) * 0.35
    t = _THRESH.get(strict, 0.1)
    if kind == "free":
        need_q, need_lex = 0.7 + t * 0.4, 0.62 + t * 0.4
        min_chars = 3
    elif kind == "sfx":
        need_q, need_lex, min_chars = 0.0, 0.0, 1
    else:
        need_q, need_lex = 0.5 + t * 0.4, 0.45 + t * 0.4
        min_chars = 1 if lang in ("ja", "zh") else 2
    ok = len(chars) >= min_chars and q >= need_q and lexs >= need_lex
    # el alfabeto debe encajar con la obra (un globo en cirílico en una obra japonesa es casi seguro basura)
    return Verdict(s if ok else "", text, round(float(q), 3), round(float(lexs), 3), ok, lang, changes, [],
                   "" if ok else f"coherencia baja (caracteres {lexs:.2f}, global {q:.2f})")


# --------------------------------------------------------------------------------------------------------- API
def _script_key(text: str) -> str:
    try:
        from ocr_langs import script_of
        s = script_of(text) or "latin"
    except Exception:  # noqa: BLE001
        s = "latin"
    return {"kana": "cjk", "han": "cjk", "hangul": "hangul"}.get(s, s)


def verify(text: str, lang: str = "es", conf: float | None = None, kind: str = "bubble", ctx: WorkContext | None = None,
           strict: str = "normal") -> Verdict:
    """Comprueba y corrige `text`. `lang`: idioma esperado ('es','en','ja','ko','zh' o código de Tesseract).
    kind: 'bubble' | 'box' | 'free' (texto sobre el dibujo: más exigente) | 'sfx' (no se descarta, solo se limpia).
    conf: confianza media del OCR (0-100) si se conoce. strict: 'suave' | 'normal' | 'estricto'."""
    ctx = ctx if ctx is not None else WORK
    orig = text or ""
    t = unicodedata.normalize("NFC", orig).replace("­", "")
    t = re.sub(r"[ \t]*\n[ \t]*", " ", t).strip()
    if not t:
        return Verdict("", orig, 0.0, 0.0, False, norm_lang(lang), [], [], "vacío")
    lg = norm_lang(lang)
    script = _script_key(t)
    # el idioma real del texto manda sobre el pedido cuando el alfabeto lo decide
    if re.search(r"[가-힯]", t) and not _RE_KANA.search(t):
        lg = "ko"
    elif _RE_KANA.search(t):
        lg = "ja"
    elif _RE_HAN.search(t) and not re.search(r"[A-Za-z]{3,}", t):
        lg = lg if lg in ("ja", "zh") else ("zh" if lg not in ("ja",) else "ja")
    if lg in ("ja", "zh", "ko"):
        v = _verify_cjk(t, lg, conf, kind, ctx, strict)
    else:
        if lg not in ("en", "es"):
            lg = lg or "en"
        if script not in ("latin", "cjk", "hangul"):                  # ruso, árabe, hebreo, griego…: solo estructura
            letters = sum(c.isalpha() for c in t)
            ok = letters >= 2 and (conf is None or conf >= 55)
            return Verdict(t if ok else "", orig, 0.6 if ok else 0.1, 0.6 if ok else 0.1, ok, lg, [], [], "")
        v = _verify_latin(t, lg, conf, kind, ctx, strict)
    # coherencia con la obra: un alfabeto que casi no aparece en el resto de la obra es sospechoso
    if v.ok and ctx.accepted >= 12 and ctx.script_share(script) < 0.04 and (conf is None or conf < 92) and kind != "sfx":
        v.ok = False
        v.text = ""
        v.reason = "alfabeto que no aparece en el resto de la obra"
        v.flags.append("alfabeto-raro")
    if v.ok:
        toks = [w.lower() for w in re.findall(r"[^\W\d_]{3,}", v.text)]
        ctx.observe(toks, script, v.score)
    else:
        ctx.rejected += 1
    return v


def clean_for_sfx(text: str) -> str:
    """Texto suelto de onomatopeyas: sin símbolos raros (no se corrige ni se descarta: lo decide el catálogo)."""
    t = unicodedata.normalize("NFC", text or "")
    t = re.sub(r"[^\w\s!?…~ー・぀-ヿ一-鿿가-힯㄰-㆏'’.-]", " ", t)
    return re.sub(r"\s+", " ", t).strip()
