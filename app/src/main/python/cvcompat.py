"""Equivalentes de las operaciones de OpenCV que usa text_regions, con numpy + scipy (disponibles en Chaquopy).

Cada función replica el comportamiento de la llamada de OpenCV que sustituye. Las diferencias numéricas
(redondeo de punto fijo de OpenCV, p. ej.) están medidas en tests_python/test_cvcompat.py.
"""
import math

import numpy as np
from scipy import ndimage
from scipy.spatial import ConvexHull, QhullError

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
    """cv2.cvtColor(BGR2LAB) para uint8 de 8 bits: Lab con la escala de OpenCV (L, a, b en 0-255)."""
    bgr = np.asarray(bgr, dtype=np.uint8)
    shape = bgr.shape
    px = bgr.reshape(-1, 3)
    r = _srgb_to_lin(px[:, 2].astype(np.float64))
    g = _srgb_to_lin(px[:, 1].astype(np.float64))
    b = _srgb_to_lin(px[:, 0].astype(np.float64))
    X = 0.412453 * r + 0.357580 * g + 0.180423 * b
    Y = 0.212671 * r + 0.715160 * g + 0.072169 * b
    Z = 0.019334 * r + 0.119193 * g + 0.950227 * b
    X /= 0.950456
    Z /= 1.088754

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
    """cv2.getGaussianKernel (sigma automático si sigma <= 0)."""
    if sigma <= 0 and ksize == 3:
        return np.array([0.25, 0.5, 0.25])          # kernel fijo de OpenCV para 3x3 automático
    if sigma <= 0:
        sigma = 0.3 * ((ksize - 1) * 0.5 - 1) + 0.8
    x = np.arange(ksize, dtype=np.float64) - (ksize - 1) / 2.0
    k = np.exp(-(x * x) / (2.0 * sigma * sigma))
    return k / k.sum()


def gaussian_blur(img, ksize, sigma=0.0, border="mirror"):
    """cv2.GaussianBlur para imagen 2D uint8. border 'mirror' = REFLECT_101 (por defecto en OpenCV)."""
    k = gaussian_kernel(ksize, sigma)
    f = img.astype(np.float64)
    f = ndimage.correlate1d(f, k, axis=0, mode=border)
    f = ndimage.correlate1d(f, k, axis=1, mode=border)
    return np.clip(np.rint(f), 0, 255).astype(np.uint8)


def median_blur3(img):
    """cv2.medianBlur(img, 3)."""
    return ndimage.median_filter(img, size=3, mode="nearest")


def adaptive_threshold(img, block, C, invert):
    """cv2.adaptiveThreshold GAUSSIAN_C. invert=True -> THRESH_BINARY_INV; False -> THRESH_BINARY."""
    mean = gaussian_blur(img, block, 0.0, border="nearest").astype(np.int32)
    T = mean - int(C)
    src = img.astype(np.int32)
    if invert:
        return np.where(src > T, 0, 255).astype(np.uint8)
    return np.where(src > T, 255, 0).astype(np.uint8)


# ---------------------------------------------------------------- morfología
def _struct_square(k):
    return np.ones((k, k), dtype=bool)


def _struct_ellipse(size):
    rows = ELLIPSE_TABLE[size]
    return np.array([[c == "1" for c in r] for r in rows], dtype=bool)


def struct(kind, size):
    """cv2.getStructuringElement para MORPH_RECT (ones) o MORPH_ELLIPSE (tabla)."""
    return _struct_ellipse(size) if kind == "ellipse" else _struct_square(size)


def _origin(st):
    """OpenCV ancla el kernel en (tamaño//2): en tamaños pares el ancla queda un píxel más arriba que en scipy."""
    return tuple(-1 if (n % 2 == 0) else 0 for n in st.shape)


def erode(mask, st):
    """Erosión binaria: el exterior no erosiona (como OpenCV)."""
    return ndimage.binary_erosion(mask, structure=st, border_value=1, origin=_origin(st))


def dilate(mask, st):
    """Dilatación binaria: el exterior no añade nada (como OpenCV)."""
    return ndimage.binary_dilation(mask, structure=st, border_value=0, origin=_origin(st))


def open_(mask, st):
    return dilate(erode(mask, st), st)


def morph_gradient3(img):
    """cv2.morphologyEx(MORPH_GRADIENT, 3x3) para gris uint8."""
    st = _struct_square(3)
    dil = ndimage.grey_dilation(img, footprint=st, mode="nearest")
    ero = ndimage.grey_erosion(img, footprint=st, mode="nearest")
    return (dil.astype(np.int16) - ero.astype(np.int16)).astype(np.uint8)


# ---------------------------------------------------------------- componentes y contornos
def connected(mask, connectivity):
    """cv2.connectedComponentsWithStats: (n incluido fondo, etiquetas, stats Nx5 [x,y,w,h,area])."""
    st = ndimage.generate_binary_structure(2, 1 if connectivity == 4 else 2)
    lab, count = ndimage.label(mask, structure=st)
    n = count + 1
    sizes = np.bincount(lab.ravel(), minlength=n)
    stats = np.zeros((n, 5), dtype=np.int64)
    stats[0] = [0, 0, mask.shape[1], mask.shape[0], int(sizes[0])]
    for i, sl in enumerate(ndimage.find_objects(lab), start=1):
        if sl is None:
            continue
        ys, xs = sl
        stats[i] = [xs.start, ys.start, xs.stop - xs.start, ys.stop - ys.start, int(sizes[i])]
    return n, lab, stats


def region_props(comp):
    """Propiedades de UN contorno externo (equivalente a findContours+contourArea+convexHull+boundingRect).

    Devuelve (area_relleno, area_poligono, area_envolvente, bbox(x,y,w,h)):
      area_relleno  -> píxeles dentro del contorno incluidos huecos (= drawContours relleno)
      area_poligono -> contourArea del contorno externo (≈ relleno menos la mitad del perímetro)
      area_envolvente -> contourArea(convexHull(contorno))
    """
    filled = ndimage.binary_fill_holes(comp)
    a_fill = int(filled.sum())
    edge = filled & ~ndimage.binary_erosion(filled, structure=ndimage.generate_binary_structure(2, 1), border_value=0)
    perim = int(edge.sum())
    area_poly = max(0.0, a_fill - 0.5 * perim)
    ys, xs = np.nonzero(edge)
    hull_a = 0.0
    if len(xs) >= 3:
        try:
            hull_a = float(ConvexHull(np.column_stack([xs, ys]).astype(np.float64)).volume)
        except QhullError:
            hull_a = 0.0
    sl = ndimage.find_objects(comp.astype(np.int32))
    if sl and sl[0] is not None:
        y0, x0 = sl[0][0].start, sl[0][1].start
        bw, bh = sl[0][1].stop - x0, sl[0][0].stop - y0
    else:
        x0 = y0 = bw = bh = 0
    return a_fill, area_poly, hull_a, (x0, y0, bw, bh)


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
        x0 = int(np.floor(s))
        fx = s - x0
        for k, off in enumerate((-1, 0, 1, 2)):
            idx = min(max(x0 + off, 0), n_src - 1)
            M[d, idx] += _cubic(np.array([fx - off]))[0]
    return M


def _weights_area(n_src, n_dst, inv):
    """INTER_AREA de OpenCV (resizeArea): tabla de pesos igual a la del original.

    `inv` = 1/fx (escala pedida, no W2/W). Como OpenCV: el primer píxel parcial se toma con ceil, los completos
    entre medias, y el último parcial con floor acotado al último píxel de la fuente."""
    scale_x = inv                      # = 1 / inv_scale_x de OpenCV
    inv_scale_x = 1.0 / inv            # = fx
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


def fill_holes(comp):
    """Relleno de un contorno externo: equivalente a drawContours(..., thickness=-1)."""
    return ndimage.binary_fill_holes(comp)


def copy_make_border_const(img, pad, value=255):
    """cv2.copyMakeBorder(BORDER_CONSTANT)."""
    return np.pad(img, pad, mode="constant", constant_values=value)
