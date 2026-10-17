"""Localiza el TEXTO de una viñeta antes de leerlo («primero el texto»).

Port a numpy del text_regions.py original (que usaba OpenCV). Mismo algoritmo y mismos nombres;
las llamadas a OpenCV se sustituyen por cvcompat, validado operación por operación contra cv2.

Por qué existe (el problema que el original resolvió): el OCR «leía cosas que no están»: rayas, tramas y sombreado
parecían globos llenos de letras. Esta detección solo deja pasar bloques con geometría de texto.

Cómo funciona:
  1. Se separan los trazos (tinta) con un umbral local, en los dos sentidos (oscuro sobre claro y claro sobre oscuro).
  2. Se descartan trazos que no pueden ser letras: líneas finas y largas, motas diminutas (tramas), manchas enormes.
  3. Los trazos vecinos se agrupan en bloques. Un bloque solo cuenta como texto si sus trazos son del mismo tamaño,
     están alineados en filas o columnas y tienen formas variadas.
  4. De cada bloque se extrae una imagen «limpia» (solo sus letras, el resto en el color del fondo).
  5. Se mide el color de fondo alrededor (globo / caja / texto suelto) y su planitud: tipo de bloque y color del globo.

Nada aquí usa red ni modelos: es geometría.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

import cvcompat as CC

MAX_COMPONENTS = 6000           # más trazos que esto = textura (trama, hierba, tela): no es texto
MIN_SCORE = 0.55                # puntuación mínima de un bloque para considerarlo texto


@dataclass
class Block:
    box: tuple                  # (x, y, w, h) en coordenadas del recorte analizado
    score: float                # 0-1: cuánto se parece a texto (geometría)
    n: int                      # nº de trazos
    line_h: float               # altura típica de una letra (px)
    polarity: str               # 'dark' (tinta oscura) | 'light' (tinta clara sobre fondo oscuro)
    mask: np.ndarray            # máscara (bool, tamaño del recorte) de los trazos del bloque, algo engrosada
    kind: str = "free"          # 'bubble' | 'box' | 'free'
    bg_lab: tuple = (0.0, 0.0, 0.0)   # color de fondo (Lab, escala de OpenCV) alrededor del texto
    bg_bgr: tuple = (255, 255, 255)
    flat: float = 0.0           # 0-1: lo plano que es el fondo (globo/caja ≈ 1, dibujo ≈ 0)
    vertical: bool = False      # columnas de texto (japonés vertical, etc.)
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------------------------------------- trazos
def _ink(gray: np.ndarray, polarity: str) -> np.ndarray:
    h, w = gray.shape
    bs = int(max(25, min(h, w) / 8)) | 1
    g = CC.gaussian_blur(gray, 3) if min(h, w) > 200 else gray
    if polarity == "dark":
        return CC.adaptive_threshold(g, bs, 14, invert=True)
    return CC.adaptive_threshold(g, bs, -14, invert=False)


def _components(ink: np.ndarray):
    """Trazos que PUEDEN ser letras: (stats Nx5 [x,y,w,h,area], etiquetas, índices). None si es una textura."""
    H, W = ink.shape
    ref = min(H, W)
    n, lab, st = CC.connected(ink > 0, 8)
    if n - 1 > MAX_COMPONENTS * 4:
        return None
    x, y, w, h, a = st[:, 0], st[:, 1], st[:, 2], st[:, 3], st[:, 4]
    big = np.maximum(w, h)
    small = np.minimum(w, h)
    fill = a / np.maximum(1, w * h)
    min_side = max(6, int(0.012 * ref))                      # motas de trama (2-5 px) fuera
    ok = (np.arange(n) > 0) & (h >= min_side) & (a >= 8)
    ok &= big <= 0.45 * ref                                  # manchas / bordes enormes
    ok &= fill >= 0.13                                       # líneas diagonales finas (sombreado)
    ok &= ~((big / np.maximum(1, small) > 10) & (big > 0.05 * ref))        # líneas largas y finas
    idx = np.flatnonzero(ok)
    if len(idx) > MAX_COMPONENTS:
        return None
    return st, lab, idx


# ---------------------------------------------------------------------------------------------------------- agrupar
class _UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.p[a] = b


def _cluster(st, idx):
    """Agrupa trazos vecinos (distancia pequeña respecto a su tamaño). Devuelve listas de índices de `idx`."""
    k = len(idx)
    if k == 0:
        return []
    x0 = st[idx, 0].astype(np.float32)
    y0 = st[idx, 1].astype(np.float32)
    x1 = x0 + st[idx, 2]
    y1 = y0 + st[idx, 3]
    sz = np.maximum(st[idx, 2], st[idx, 3]).astype(np.float32)
    order = np.argsort(x0)
    uf = _UF(k)
    maxsz = float(sz.max()) if k else 0.0
    for ii in range(k):
        i = order[ii]
        reach = x1[i] + 1.0 * max(sz[i], 1.0) * 1.1 + 2
        for jj in range(ii + 1, k):
            j = order[jj]
            if x0[j] > reach + maxsz:
                break
            gx = max(0.0, max(x0[i], x0[j]) - min(x1[i], x1[j]))
            gy = max(0.0, max(y0[i], y0[j]) - min(y1[i], y1[j]))
            s = max(sz[i], sz[j])
            if s > 4.5 * min(sz[i], sz[j]) and not (gx <= 0.5 * s and gy <= 0.5 * s):
                continue                                      # una letra y una mancha 4× mayor solo se unen si están pegadas
            if gx <= 0.75 * s and gy <= 0.5 * s:
                uf.union(i, j)
            elif gy <= 0.75 * s and gx <= 0.35 * s:           # columnas (texto vertical)
                uf.union(i, j)
    groups = {}
    for i in range(k):
        groups.setdefault(uf.find(i), []).append(i)
    return list(groups.values())


def _rows_cols(cx, cy, hm, wm):
    """Fracción de trazos que comparten fila / columna con otro (1D: se agrupan por cercanía)."""
    def frac(v, tol):
        o = np.sort(v)
        if len(o) < 2:
            return 0.0
        grp, cur = [], [o[0]]
        for a in o[1:]:
            if a - cur[-1] <= tol:
                cur.append(a)
            else:
                grp.append(cur)
                cur = [a]
        grp.append(cur)
        return sum(len(g) for g in grp if len(g) >= 2) / len(o)
    return frac(cy, 0.55 * hm), frac(cx, 0.55 * wm)


def _score(st, idx, members):
    """(puntuación 0-1, altura de letra, vertical?) de un grupo de trazos."""
    m = idx[members]
    w = st[m, 2].astype(np.float32)
    h = st[m, 3].astype(np.float32)
    a = st[m, 4].astype(np.float32)
    n = len(m)
    if n < 2:
        return 0.0, 0.0, False
    hm = float(np.median(h))
    wm = float(np.median(w))
    big = np.maximum(h, w)
    sm = float(np.median(big))
    homog = float(np.mean((big >= 0.45 * sm) & (big <= 1.9 * sm)))           # letras de tamaño parecido
    cx = st[m, 0] + w / 2
    cy = st[m, 1] + h / 2
    rows, cols = _rows_cols(cx, cy, max(hm, 1.0), max(wm, 1.0))
    align = max(rows, cols)
    x0, y0 = float(st[m, 0].min()), float(st[m, 1].min())
    x1, y1 = float((st[m, 0] + w).max()), float((st[m, 1] + h).max())
    box_a = max(1.0, (x1 - x0) * (y1 - y0))
    dens = float(a.sum()) / box_a
    dens_ok = 1.0 if 0.04 <= dens <= 0.6 else 0.4 if 0.02 <= dens <= 0.75 else 0.0
    fill = a / np.maximum(1.0, w * h)
    asp = np.round(np.log2(np.maximum(w, 1) / np.maximum(h, 1)) * 2) / 2
    variety = len({(float(p), round(float(q), 1)) for p, q in zip(asp, fill)})
    var_ok = 1.0 if variety >= min(4, max(2, n // 2)) else 0.3                # una trama de puntos/rayas iguales: no
    cnt = min(1.0, n / 4.0)
    s = (0.30 * homog + 0.30 * align + 0.15 * dens_ok + 0.15 * var_ok + 0.10 * cnt) * (1.0 if n >= 3 else 0.7)
    return s, sm, cols > rows + 0.15


# ---------------------------------------------------------------------------------------------------------- fondo
def _lab(bgr):
    return CC.lab(np.uint8([[bgr]]))[0, 0]


def _background(img_bgr, gray, mask, box, line_h):
    """(Lab, BGR, planitud 0-1, tipo) del fondo que rodea al texto: anillo alrededor de la caja sin contar la tinta."""
    H, W = gray.shape
    x, y, w, h = box
    p1 = int(max(3, 0.35 * line_h))
    p2 = p1 + int(max(4, 0.8 * line_h))
    X0, Y0, X1, Y1 = max(0, x - p2), max(0, y - p2), min(W, x + w + p2), min(H, y + h + p2)
    sub = np.zeros((Y1 - Y0, X1 - X0), bool)
    sub[:] = True
    ix0, iy0, ix1, iy1 = max(0, x - p1) - X0, max(0, y - p1) - Y0, min(W, x + w + p1) - X0, min(H, y + h + p1) - Y0
    sub[iy0:iy1, ix0:ix1] = False
    ring = sub
    ink_near = CC.dilate(mask[Y0:Y1, X0:X1], CC.struct("square", 3))
    c = img_bgr[Y0:Y1, X0:X1]
    sel = ring & ~ink_near
    if sel.sum() < 12:
        return (255, 128, 128), (255, 255, 255), 0.0, "free"
    px = c[sel]
    med = np.median(px, axis=0).astype(np.uint8)
    lab_all = CC.lab(px.reshape(-1, 1, 3)).reshape(-1, 3)
    lab_med = np.median(lab_all, axis=0)
    spread = float(np.mean(np.abs(lab_all[:, 0].astype(np.float32) - lab_med[0])))
    near = float(np.mean(np.abs(lab_all[:, 0].astype(np.float32) - lab_med[0]) <= 14))
    flat = max(0.0, min(1.0, near * (1.0 - min(1.0, spread / 40.0)) ** 0.5))
    return tuple(int(v) for v in lab_med), tuple(int(v) for v in med), flat, ""


def _container(gray, bg_bgr, box, flat, line_h):
    """'bubble' | 'box' | 'free' según la región plana que rodea al texto (globo ovalado, caja rectangular o fondo del dibujo)."""
    if flat < 0.72:
        return "free"
    H, W = gray.shape
    bg_gray = int(CC.gray(np.uint8([[bg_bgr]]))[0, 0])
    same = (np.abs(gray.astype(np.int16) - bg_gray) <= 16)
    x, y, w, h = box
    pad = max(3, int(0.5 * line_h))
    n, lab, st = CC.connected(same, 4)
    ring = np.zeros((H, W), bool)
    ring[max(0, y - pad):min(H, y + h + pad), max(0, x - pad):min(W, x + w + pad)] = True
    ring[y:y + h, x:x + w] = False
    labs = lab[ring]
    labs = labs[labs > 0]
    if labs.size == 0:
        return "free"
    best = int(np.bincount(labs).argmax())
    comp = (lab == best)
    _a_fill, area, _hull, (bx, by, bw, bh) = CC.region_props(comp)   # área con los huecos (las letras) incluidos
    if area > 0.55 * H * W:
        return "free"                                          # es el fondo de toda la viñeta, no un globo
    return "box" if area / max(1, bw * bh) >= 0.9 else "bubble"


# ---------------------------------------------------------------------------------------------------------- API
def _blocks_for(img_bgr, gray, polarity, min_score):
    ink = _ink(gray, polarity)
    comp = _components(ink)
    if comp is None:
        return []
    st, lab, idx = comp
    if len(idx) < 2:
        return []
    out = []
    for members in _cluster(st, idx):
        if len(members) < 2:
            continue
        sc, sm, vertical = _score(st, idx, np.asarray(members))
        if sc < min_score:
            continue
        m = idx[members]
        x0, y0 = int(st[m, 0].min()), int(st[m, 1].min())
        x1, y1 = int((st[m, 0] + st[m, 2]).max()), int((st[m, 1] + st[m, 3]).max())
        w, h = x1 - x0, y1 - y0
        if len(members) < 3 and max(w, h) < 3.0 * sm:
            continue                                           # dos manchas sueltas
        keepmap = np.zeros(int(lab.max()) + 1, bool)
        keepmap[m] = True
        mask = keepmap[lab]
        grow = 2 if sm < 40 else 3
        mask = CC.dilate(mask, CC.struct("square", grow))
        out.append(Block(box=(x0, y0, w, h), score=float(sc), n=len(members), line_h=float(sm), polarity=polarity,
                         mask=mask, vertical=bool(vertical)))
    return out


def _iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    return inter / max(1, aw * ah + bw * bh - inter), inter / max(1, min(aw * ah, bw * bh))


def _flat_mask(gray):
    g = CC.median_blur3(gray)
    grad = CC.morph_gradient3(g)
    flat = grad <= 18
    return CC.open_(flat, CC.struct("square", 3))


def _container_blocks(img_bgr, gray, min_score):
    """Globos y cajas: regiones PLANAS (de cualquier color) con letras dentro. Devuelve (bloques, máscara de lo ocupado)."""
    H, W = gray.shape
    flat = _flat_mask(gray)
    n, lab, st = CC.connected(flat, 4)
    taken = np.zeros((H, W), bool)
    out = []
    amin, amax = 0.0025 * H * W, 0.50 * H * W
    for i in range(1, n):
        x, y, w, h, area = st[i]
        if area < amin * 0.4 or w < 28 or h < 18 or w * h > amax * 1.6:
            continue
        comp = (lab == i)
        filled = CC.fill_holes(comp)
        a_f = int(filled.sum())
        if a_f < amin or a_f > amax:
            continue
        _af, _ap, hull_a, (bx, by, bw, bh) = CC.region_props(comp)
        if hull_a <= 0 or a_f / hull_a < 0.8:
            continue                                            # forma retorcida: un trozo de dibujo, no un globo
        if a_f / max(1, bw * bh) < 0.5:
            continue
        inner = CC.erode(filled, CC.struct("square", 5))
        bgv = gray[comp]
        if bgv.size < 30:
            continue
        bg_gray = int(np.median(bgv))
        ink = (np.abs(gray.astype(np.int16) - bg_gray) >= 45) & inner
        comp_i = _components(ink)
        if comp_i is None:
            continue
        st2, lab2, idx = comp_i
        if len(idx) < 2:
            continue
        keep, tot, best = [], 0, 0.0
        sm_all = []
        for members in _cluster(st2, idx):
            if len(members) < 2:
                continue
            sc, sm, _v = _score(st2, idx, np.asarray(members))
            if sc >= min_score:
                keep += members
                tot += len(members)
                best = max(best, sc)
                sm_all.append(sm)
        if tot < 3 and not (tot == 2 and best >= 0.7):
            continue
        m = idx[keep]
        x0, y0 = int(st2[m, 0].min()), int(st2[m, 1].min())
        x1, y1 = int((st2[m, 0] + st2[m, 2]).max()), int((st2[m, 1] + st2[m, 3]).max())
        keepmap = np.zeros(int(lab2.max()) + 1, bool)
        keepmap[m] = True
        sm = float(np.median(sm_all)) if sm_all else 10.0
        grow = 2 if sm < 40 else 3
        mask = CC.dilate(keepmap[lab2], CC.struct("square", grow))
        _s, _sm, vertical = _score(st2, idx, np.asarray(keep))
        px = img_bgr[comp]
        bgr = tuple(int(v) for v in np.median(px, axis=0))
        lab_c = tuple(int(v) for v in np.median(CC.lab(px.reshape(-1, 1, 3)).reshape(-1, 3), axis=0))
        light = float(np.median(gray[mask])) > bg_gray + 20
        out.append(Block(box=(x0, y0, x1 - x0, y1 - y0), score=float(best), n=int(tot), line_h=sm,
                         polarity="light" if light else "dark", mask=mask, vertical=bool(vertical),
                         kind="box" if a_f / max(1, bw * bh) >= 0.9 else "bubble", bg_lab=lab_c, bg_bgr=bgr, flat=1.0,
                         extra={"container": (int(bx), int(by), int(bw), int(bh)), "container_area": a_f / float(H * W)}))
        taken |= filled
    return out, taken


def find_text_blocks(img_bgr: np.ndarray, min_score: float = MIN_SCORE) -> list[Block]:
    """Bloques de texto de un recorte (viñeta). Cada bloque trae su máscara de letras, tipo y color de fondo.

    Primero se buscan globos/cajas (regiones planas con letras); después texto suelto fuera de ellos, con exigencias mayores
    (el texto sobre el dibujo es donde más letras «inventadas» aparecen)."""
    if img_bgr is None or img_bgr.size == 0:
        return []
    H, W = img_bgr.shape[:2]
    if min(H, W) < 40:
        return []
    gray = CC.gray(img_bgr)
    blocks, taken = _container_blocks(img_bgr, gray, min_score)
    # --- texto suelto: sin los globos ya encontrados
    work = gray.copy()
    if taken.any():
        fill = int(np.median(gray[~taken])) if (~taken).any() else 255
        work[CC.dilate(taken, CC.struct("square", 5))] = fill
    free = _blocks_for(img_bgr, work, "dark", max(min_score, 0.75))
    for b in _blocks_for(img_bgr, work, "light", 0.85):
        b.extra["inv"] = True
        free.append(b)
    for b in sorted(free, key=lambda b: -(b.score * (b.n ** 0.5))):
        x, y, w, h = b.box
        if w * h > 0.35 * H * W or b.n < 4:
            continue                                            # un «bloque» que ocupa media viñeta es dibujo, no una nota
        if any(max(_iou(b.box, o.box)) > 0.5 for o in blocks):
            continue
        lab, bgr, flat, _k = _background(img_bgr, work, b.mask, b.box, b.line_h)
        b.bg_lab, b.bg_bgr, b.flat = lab, bgr, flat
        if b.polarity == "light" and not (lab[0] < 110 and flat >= 0.7):
            continue
        b.kind = "free"
        blocks.append(b)
    return blocks


def find_sfx_blocks(img_bgr: np.ndarray, taken: np.ndarray | None = None, min_score: float = 0.62) -> list[Block]:
    """Letras GRANDES y gruesas fuera de los globos (onomatopeyas), aunque estén sobre el dibujo.

    Las rayas del sombreado miden 1-3 px de grosor y las letras de una onomatopeya 8-30 px: una apertura morfológica deja solo
    los trazos gruesos. Con ellos se agrupan las letras y se construye una máscara limpia (sin sombreado) para el OCR."""
    if img_bgr is None or img_bgr.size == 0:
        return []
    H, W = img_bgr.shape[:2]
    if min(H, W) < 60:
        return []
    gray = CC.gray(img_bgr)
    work = gray
    if taken is not None and taken.any():
        work = gray.copy()
        work[CC.dilate(taken, CC.struct("square", 5))] = int(np.median(gray[~taken])) if (~taken).any() else 255
    ref = min(H, W)
    out: list[Block] = []
    for polarity in ("dark", "light"):
        ink = _ink(work, polarity)
        for r in (3, 5, 8, 12):
            if 2 * r + 1 > 0.2 * ref:
                break
            k = CC.struct("ellipse", 2 * r + 1)
            opened = CC.open_(ink > 0, k)
            if not opened.any():
                continue
            n, lab, st = CC.connected(opened, 8)
            if n - 1 > 800:
                continue
            w_, h_, a_ = st[:, 2], st[:, 3], st[:, 4]
            big = np.maximum(w_, h_)
            ok = (np.arange(n) > 0) & (h_ >= 6 * r) & (big <= 0.7 * ref) & (a_ >= 20 * r)
            ok &= (a_ / np.maximum(1, w_ * h_)) >= 0.16
            idx = np.flatnonzero(ok)
            if len(idx) < 2:
                continue
            for members in _cluster(st, idx):
                if len(members) < 2:
                    continue
                sc, sm, vertical = _score(st, idx, np.asarray(members))
                if sc < min_score:
                    continue
                m = idx[members]
                x0, y0 = int(st[m, 0].min()), int(st[m, 1].min())
                x1, y1 = int((st[m, 0] + st[m, 2]).max()), int((st[m, 1] + st[m, 3]).max())
                if (x1 - x0) * (y1 - y0) > 0.4 * H * W:
                    continue
                keepmap = np.zeros(n, bool)
                keepmap[m] = True
                core = keepmap[lab]
                grow = CC.struct("ellipse", 2 * r + 3)
                mask = CC.dilate(core, grow) & (ink > 0)
                mask |= core
                out.append(Block(box=(x0, y0, x1 - x0, y1 - y0), score=float(sc), n=len(members), line_h=float(sm),
                                 polarity=polarity, mask=mask, vertical=bool(vertical), kind="sfx",
                                 extra={"stroke": 2 * r}))
    final: list[Block] = []
    for b in sorted(out, key=lambda b: -(b.score * (b.n ** 0.5) * (1 + b.box[2] * b.box[3] / float(H * W)))):
        if any(max(_iou(b.box, o.box)) > 0.85 for o in final):
            continue                                     # mismo bloque a otro grosor: solo se descartan los casi idénticos
        lab, bgr, flat, _k = _background(img_bgr, work, b.mask, b.box, b.line_h)
        b.bg_lab, b.bg_bgr, b.flat = lab, bgr, flat
        final.append(b)
    return final[:12]                                    # candidatos: el OCR decide cuál grosor se lee mejor


def _punct_extra(gray, block, win):
    """Trazos pequeños (puntuación, acentos) dentro de la caja del bloque ampliada que no están ya en la máscara."""
    X0, Y0, X1, Y1 = win
    x, y, w, h = block.box
    lh = max(8.0, float(block.line_h))
    ex, ey = int(0.6 * lh), int(0.35 * lh)
    ax0, ay0, ax1, ay1 = max(X0, x - ex), max(Y0, y - ey), min(X1, x + w + ex), min(Y1, y + h + ey)
    out = np.zeros((Y1 - Y0, X1 - X0), bool)
    if ax1 <= ax0 or ay1 <= ay0:
        return out
    sub = gray[ay0:ay1, ax0:ax1]
    ink = _ink(sub, block.polarity)
    n, lab, st = CC.connected(ink > 0, 8)
    if n <= 1:
        return out
    keep = np.zeros(n, bool)
    for i in range(1, n):
        cw, ch, ca = st[i, 2], st[i, 3], st[i, 4]
        if ch <= 1.7 * lh and cw <= 1.7 * lh and ca >= 3 and st[i, 0] > 0 and st[i, 1] > 0 \
                and st[i, 0] + cw < ink.shape[1] and st[i, 1] + ch < ink.shape[0]:
            keep[i] = True
    comp = keep[lab]
    out[ay0 - Y0:ay1 - Y0, ax0 - X0:ax1 - X0] = comp
    return out


def clean_crop(gray: np.ndarray, block: Block, pad: int | None = None):
    """Imagen en gris SOLO con las letras del bloque (tinta oscura sobre blanco), escalada para que la letra mida ~32 px."""
    x, y, w, h = block.box
    pad = pad if pad is not None else max(6, int(0.35 * block.line_h))
    H, W = gray.shape
    X0, Y0, X1, Y1 = max(0, x - pad), max(0, y - pad), min(W, x + w + pad), min(H, y + h + pad)
    g = gray[Y0:Y1, X0:X1].astype(np.uint8)
    m = block.mask[Y0:Y1, X0:X1].copy()
    if block.kind in ("bubble", "box"):
        m |= _punct_extra(gray, block, (X0, Y0, X1, Y1))      # apóstrofos, «!», puntos, tildes
    if block.polarity == "light":
        g = 255 - g                                            # tinta clara → tinta oscura
    bg = int(np.clip(np.percentile(g[~m], 70) if (~m).any() else 255, 0, 255))
    out = np.where(m, g, 255).astype(np.uint8)
    if bg < 235:                                               # fondo de color: llevar el fondo a blanco manteniendo el contraste
        lo = int(np.percentile(g[m], 5)) if m.any() else 0
        span = max(30, bg - lo)
        out = np.where(m, np.clip((g.astype(np.float32) - lo) * 255.0 / span, 0, 255), 255).astype(np.uint8)
    scale = float(np.clip(32.0 / max(8.0, block.line_h), 0.5, 4.0))
    if abs(scale - 1.0) > 0.08:
        out = CC.resize(out, scale)
    return CC.copy_make_border_const(out, 14, 255), scale


def order_blocks(blocks, rtl):
    """Orden de lectura (filas de arriba abajo; dentro de una fila de derecha a izquierda si rtl)."""
    items = sorted(blocks, key=lambda b: b.box[1])
    rows = []
    for b in items:
        x, y, w, h = b.box
        for row in rows:
            top = min(r.box[1] for r in row)
            bottom = max(r.box[1] + r.box[3] for r in row)
            if min(bottom, y + h) - max(top, y) > 0.4 * min(h, bottom - top):
                row.append(b)
                break
        else:
            rows.append([b])
    rows.sort(key=lambda r: min(b.box[1] for b in r))
    out = []
    for row in rows:
        row.sort(key=lambda b: b.box[0], reverse=rtl)
        out.extend(row)
    return out
