"""Equivalentes de las operaciones de OpenCV que usa text_regions, SOLO con numpy.

Sin scipy: Chaquopy no tiene una versión precompilada de scipy para esta combinación, y no es necesaria.
Cada función replica el comportamiento de la llamada de OpenCV que sustituye. tests_python/test_cvcompat.py
compara todas contra OpenCV.
"""
import math

import numpy as np

from _ellipse_table import ELLIPSE_TABLE


# ---------------------------------------------------------------- color
def gray(bgr):
    """cv2.cvtColor(BGR2GRAY): misma fórmula de punto fijo de OpenCV."""
    b = bgr[..., 0].astype(np.int32)
    g = bgr[..., 1].astype(np.int32)
    r = bgr[..., 2].astype(np.int32)
    return ((r * 4899 + g * 9617 + b * 1868 + (1 << 13)) >> 14).astype(np.uint8)


def _srgb_to_lin(c):
    c = c / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lab(bgr):
    """cv2.cvtColor(BGR2LAB) para uint8 de 8 bits (escala de OpenCV, L, a, b en 0-255)."""
    bgr = np.asarray(bgr, dtype=np.uint8)
    shape = bgr.shape
    px = bgr.reshape(-1, 3)
    r = _srgb_to_lin(px[:, 2].astype(np.float64))
    g = _srgb_to_lin(px[:, 1].astype(np.float64))
    b = _srgb_to_lin(px[:, 0].astype(np.float64))
    X = (0.412453 * r + 0.357580 * g + 0.180423 * b) / 0.950456
    Y = 0.212671 * r + 0.715160 * g + 0.072169 * b
    Z = (0.019334 * r + 0.119193 * g + 0.950227 * b) / 1.088754

    def f(t):
        return np.where(t > 0.008856, np.cbrt(t), 7.787 * t + 16.0 / 116.0)

    fx, fy, fz = f(X), f(Y), f(Z)
    L = np.where(Y > 0.008856, 116.0 * fy - 16.0, 903.3 * Y)
    a = 500.0 * (fx - fy)
    bb = 200.0 * (fy - fz)
    out = np.stack([L * 255.0 / 100.0, a + 128.0, bb + 128.0], axis=1)
    return np.clip(np.rint(out), 0, 255).astype(np.uint8).reshape(shape)


# ---------------------------------------------------------------- filtros
def gaussian_kernel(ksize, sigma=0.0):
    """cv2.getGaussianKernel (sigma automático si sigma <= 0; 3x3 con kernel fijo de OpenCV)."""
    if sigma <= 0 and ksize == 3:
        return np.array([0.25, 0.5, 0.25])
    if sigma <= 0:
        sigma = 0.3 * ((ksize - 1) * 0.5 - 1) + 0.8
    x = np.arange(ksize, dtype=np.float64) - (ksize - 1) / 2.0
    k = np.exp(-(x * x) / (2.0 * sigma * sigma))
    return k / k.sum()


def _correlate1d(arr, k, axis, mode):
    """Correlación 1D simétrica. mode 'mirror' = REFLECT_101 (OpenCV por defecto); 'nearest' = replicar borde."""
    r = len(k) // 2
    pad_mode = "reflect" if mode == "mirror" else "edge"
    pads = [(0, 0)] * arr.ndim
    pads[axis] = (r, r)
    p = np.pad(arr, pads, mode=pad_mode)
    n = arr.shape[axis]
    out = np.zeros(arr.shape, dtype=np.float64)
    for i, w in enumerate(k):
        sl = [slice(None)] * arr.ndim
        sl[axis] = slice(i, i + n)
        out += w * p[tuple(sl)]
    return out


def gaussian_blur(img, ksize, sigma=0.0, border="mirror"):
    """cv2.GaussianBlur para imagen 2D uint8."""
    k = gaussian_kernel(ksize, sigma)
    f = img.astype(np.float64)
    f = _correlate1d(f, k, 0, border)
    f = _correlate1d(f, k, 1, border)
    return np.clip(np.rint(f), 0, 255).astype(np.uint8)


def _shifts3(img, mode="edge"):
    """Las 9 versiones desplazadas de la imagen (vecindad 3x3), con borde replicado."""
    p = np.pad(img, 1, mode=mode)
    H, W = img.shape
    out = []
    for dy in range(3):
        for dx in range(3):
            out.append(p[dy:dy + H, dx:dx + W])
    return out


def median_blur3(img):
    """cv2.medianBlur(img, 3)."""
    st = np.stack(_shifts3(img))
    return np.sort(st, axis=0)[4].astype(np.uint8)


def adaptive_threshold(img, block, C, invert):
    """cv2.adaptiveThreshold GAUSSIAN_C. invert=True -> THRESH_BINARY_INV; False -> THRESH_BINARY."""
    mean = gaussian_blur(img, block, 0.0, border="nearest").astype(np.int32)
    T = mean - int(C)
    src = img.astype(np.int32)
    if invert:
        return np.where(src > T, 0, 255).astype(np.uint8)
    return np.where(src > T, 255, 0).astype(np.uint8)


# ---------------------------------------------------------------- morfología
def struct(kind, size):
    """cv2.getStructuringElement para MORPH_RECT (ones) o MORPH_ELLIPSE (tabla)."""
    if kind == "ellipse":
        rows = ELLIPSE_TABLE[size]
        return np.array([[c == "1" for c in r] for r in rows], dtype=bool)
    return np.ones((size, size), dtype=bool)


def _morph(mask, st, dilate, border_value):
    """Erosión / dilatación binaria con la convención de OpenCV (ancla en tamaño // 2).

    Cada fila del kernel es un tramo continuo (cuadrado o elipse), así que se resuelve con sumas acumuladas
    por fila: pocas operaciones aunque el kernel tenga cientos de píxeles."""
    mask = mask.astype(bool)
    h, w = st.shape
    ay, ax = h // 2, w // 2
    H, W = mask.shape
    pad = max(h, w) + 1
    P = np.pad(mask, pad, mode="constant", constant_values=bool(border_value)).astype(np.int32)
    C = np.zeros((P.shape[0], P.shape[1] + 1), dtype=np.int32)
    np.cumsum(P, axis=1, out=C[:, 1:])
    xs_idx = np.arange(W)
    out = np.zeros((H, W), dtype=bool) if dilate else np.ones((H, W), dtype=bool)
    for ky in range(h):
        cols = np.nonzero(st[ky])[0]
        if cols.size == 0:
            continue
        a, b = int(cols[0]) - ax, int(cols[-1]) - ax
        if cols.size != b - a + 1:                      # fila no contigua: caso general (no ocurre con cuadrado/elipse)
            for kx in cols.tolist():
                sl = P[pad + (ky - ay):pad + (ky - ay) + H, pad + (kx - ax):pad + (kx - ax) + W].astype(bool)
                out = (out | sl) if dilate else (out & sl)
            continue
        count = b - a + 1
        r0 = pad + (ky - ay)
        rows = slice(r0, r0 + H)
        hi = C[rows][:, pad + xs_idx + b + 1]
        lo = C[rows][:, pad + xs_idx + a]
        seg = hi - lo
        out = (out | (seg > 0)) if dilate else (out & (seg == count))
    return out

def erode(mask, st):
    """Erosión binaria: el exterior no erosiona (como OpenCV)."""
    return _morph(mask, st, dilate=False, border_value=1)


def dilate(mask, st):
    """Dilatación binaria: el exterior no añade nada (como OpenCV)."""
    return _morph(mask, st, dilate=True, border_value=0)


def open_(mask, st):
    return dilate(erode(mask, st), st)


def morph_gradient3(img):
    """cv2.morphologyEx(MORPH_GRADIENT, 3x3) para gris uint8."""
    st = _shifts3(img)
    dil = np.max(np.stack(st), axis=0)
    ero = np.min(np.stack(st), axis=0)
    return (dil.astype(np.int16) - ero.astype(np.int16)).astype(np.uint8)


# ---------------------------------------------------------------- componentes conectados
_OFF4 = [(-1, 0), (0, -1)]
_OFF8 = [(-1, 0), (0, -1), (-1, -1), (-1, 1)]


def _label(mask, connectivity):
    """Etiquetado de componentes por TRAMOS horizontales + union-find sobre tramos.

    Cada fila se divide en tramos continuos (mucho menos que píxeles en máscaras grandes). Las etiquetas se numeran
    en orden de primera aparición (barrido por filas), igual que OpenCV.
    Devuelve (etiquetas int32 con 0 de fondo, nº de componentes)."""
    H, W = mask.shape
    lab = np.zeros((H, W), dtype=np.int32)
    if not mask.any():
        return lab, 0
    m = np.zeros((H, W + 2), dtype=np.int8)
    m[:, 1:-1] = mask
    d = np.diff(m, axis=1)
    sy, sx = np.nonzero(d == 1)      # inicio de tramo (columna original = índice)
    _ey, ex = np.nonzero(d == -1)    # fin exclusivo de tramo
    R = len(sx)
    S = sx.tolist()
    E = ex.tolist()
    row_start = np.searchsorted(sy, np.arange(H + 1)).tolist()
    parent = list(range(R))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    diag = 1 if connectivity == 8 else 0
    for y in range(H - 1):
        a0, a1 = row_start[y], row_start[y + 1]
        b0, b1 = row_start[y + 1], row_start[y + 2]
        i, j = a0, b0
        while i < a1 and j < b1:
            if S[i] < E[j] + diag and S[j] < E[i] + diag:
                ra, rb = find(i), find(j)
                if ra != rb:
                    parent[ra] = rb
            if E[i] < E[j]:
                i += 1
            else:
                j += 1
    roots = [find(k) for k in range(R)]
    remap = {}
    run_labels = np.empty(R, dtype=np.int32)
    for k, r in enumerate(roots):
        if r not in remap:
            remap[r] = len(remap) + 1
        run_labels[k] = remap[r]
    lengths = (np.array(E, dtype=np.int64) - np.array(S, dtype=np.int64))
    ys, xs = np.nonzero(mask)
    lab[ys, xs] = np.repeat(run_labels, lengths)
    return lab, len(remap)

def connected(mask, connectivity):
    """cv2.connectedComponentsWithStats: (n incluido fondo, etiquetas, stats Nx5 [x,y,w,h,area])."""
    mask = mask.astype(bool)
    lab, count = _label(mask, connectivity)
    n = count + 1
    H, W = mask.shape
    stats = np.zeros((n, 5), dtype=np.int64)
    stats[0] = [0, 0, W, H, int((~mask).sum())]
    if count:
        ys, xs = np.nonzero(lab)
        ls = lab[ys, xs]
        area = np.bincount(ls, minlength=n)
        x0 = np.full(n, W, dtype=np.int64)
        y0 = np.full(n, H, dtype=np.int64)
        x1 = np.full(n, -1, dtype=np.int64)
        y1 = np.full(n, -1, dtype=np.int64)
        np.minimum.at(x0, ls, xs)
        np.minimum.at(y0, ls, ys)
        np.maximum.at(x1, ls, xs)
        np.maximum.at(y1, ls, ys)
        for i in range(1, n):
            stats[i] = [x0[i], y0[i], x1[i] - x0[i] + 1, y1[i] - y0[i] + 1, area[i]]
    return n, lab, stats


def fill_holes(comp):
    """Relleno de un contorno externo: equivalente a drawContours(..., thickness=-1)."""
    comp = comp.astype(bool)
    bg_lab, _bg_n = _label(~comp, 4)
    border = set(np.unique(np.concatenate([bg_lab[0], bg_lab[-1], bg_lab[:, 0], bg_lab[:, -1]])).tolist())
    border.discard(0)
    outside = np.isin(bg_lab, list(border))
    return comp | ((~comp) & ~outside)


def _hull_area(points):
    """Área del casco convexo (monótona cadena). 0 si los puntos son colineales o pocos."""
    pts = sorted(set(points))
    if len(pts) < 3:
        return 0.0

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    if len(hull) < 3:
        return 0.0
    s = 0.0
    for i in range(len(hull)):
        x1, y1 = hull[i]
        x2, y2 = hull[(i + 1) % len(hull)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def region_props(comp):
    """Propiedades de UN contorno externo (equivalente a findContours+contourArea+convexHull+boundingRect).

    Devuelve (area_relleno, area_poligono, area_envolvente, bbox(x,y,w,h)).
    """
    comp = comp.astype(bool)
    filled = fill_holes(comp)
    a_fill = int(filled.sum())
    cross = np.array([[False, True, False], [True, True, True], [False, True, False]])
    edge = filled & ~erode(filled, cross)
    perim = int(edge.sum())
    area_poly = max(0.0, a_fill - 0.5 * perim)
    ys, xs = np.nonzero(edge)
    hull_a = _hull_area(list(zip(xs.tolist(), ys.tolist())))
    ys2, xs2 = np.nonzero(comp)
    if len(xs2):
        x0, x1 = int(xs2.min()), int(xs2.max())
        y0, y1 = int(ys2.min()), int(ys2.max())
        bb = (x0, y0, x1 - x0 + 1, y1 - y0 + 1)
    else:
        bb = (0, 0, 0, 0)
    return a_fill, area_poly, hull_a, bb


# ---------------------------------------------------------------- remuestreo y bordes
def _cubic(t, a=-0.75):
    t = np.abs(t)
    out = np.zeros_like(t)
    m1 = t <= 1
    m2 = (t > 1) & (t < 2)
    out[m1] = ((a + 2) * t[m1] - (a + 3)) * t[m1] * t[m1] + 1
    out[m2] = (((t[m2] - 5) * t[m2] + 8) * t[m2] - 4) * a
    return out


def _weights_cubic(n_src, n_dst, inv):
    M = np.zeros((n_dst, n_src))
    for d in range(n_dst):
        s = (d + 0.5) * inv - 0.5
        x0 = int(math.floor(s))
        fx = s - x0
        for off in (-1, 0, 1, 2):
            idx = min(max(x0 + off, 0), n_src - 1)
            M[d, idx] += _cubic(np.array([fx - off]))[0]
    return M


def _weights_area(n_src, n_dst, inv):
    """INTER_AREA de OpenCV (resizeArea): tabla de pesos igual a la del original.

    `inv` = 1/fx (escala pedida). El primer píxel parcial con ceil, los completos entre medias,
    y el último parcial con floor acotado al último píxel de la fuente."""
    scale_x = inv
    inv_scale_x = 1.0 / inv
    M = np.zeros((n_dst, n_src))
    for dx in range(n_dst):
        fsx1 = dx * scale_x
        fsx2 = fsx1 + scale_x
        sx1 = int(math.ceil(fsx1))
        sx2 = int(math.floor(fsx2))
        sx2 = min(sx2, n_src - 1)
        sx1 = min(sx1, sx2)
        if sx1 - fsx1 > 1e-3:
            M[dx, sx1 - 1] += (sx1 - fsx1) * inv_scale_x
        for sx in range(sx1, sx2):
            M[dx, sx] += inv_scale_x
        if fsx2 - sx2 > 1e-3:
            M[dx, sx2] += min(min(fsx2 - sx2, 1.0), scale_x) * inv_scale_x
    return M


def resize(img, scale):
    """cv2.resize(img, None, fx=scale, fy=scale): cúbico si amplía, área si reduce (uint8, 2D)."""
    H, W = img.shape
    W2, H2 = int(round(W * scale)), int(round(H * scale))
    inv = 1.0 / scale
    if scale > 1:
        Mx = _weights_cubic(W, W2, inv)
        My = _weights_cubic(H, H2, inv)
    else:
        Mx = _weights_area(W, W2, inv)
        My = _weights_area(H, H2, inv)
    out = My @ img.astype(np.float64) @ Mx.T
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)


def copy_make_border_const(img, pad, value=255):
    """cv2.copyMakeBorder(BORDER_CONSTANT)."""
    return np.pad(img, pad, mode="constant", constant_values=value)
