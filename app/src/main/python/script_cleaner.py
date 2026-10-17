"""Post-procesado del .funscript: suavizado Savitzky-Golay / B-spline, simplificación y normalización del rango.

Nunca eleva el movimiento de paneles bloqueados: tras limpiar se vuelven a poner a 0 (ver `rezero`).
"""
import numpy as np

try:
    from scipy.interpolate import UnivariateSpline
except Exception:          # scipy es opcional
    UnivariateSpline = None


def _arr(actions):
    a = np.array(actions, dtype=float).reshape(-1, 2)
    return a[np.argsort(a[:, 0])] if len(a) else a


def savgol_coeffs(window, poly):
    """Coeficientes de suavizado (derivada 0) sin necesitar scipy."""
    window = max(poly + 2, window | 1)                 # impar y mayor que el grado
    half = window // 2
    x = np.arange(-half, half + 1, dtype=float)
    A = np.vander(x, poly + 1, increasing=True)
    return np.linalg.pinv(A)[0]


def savgol(actions, window_ms=300, poly=3, step_ms=40):
    """Remuestrea a paso fijo y aplica Savitzky-Golay. Conserva el inicio y el final."""
    a = _arr(actions)
    if len(a) < 4:
        return [tuple(map(int, x)) for x in a]
    t = np.arange(a[0, 0], a[-1, 0] + 1, step_ms)
    y = np.interp(t, a[:, 0], a[:, 1])
    c = savgol_coeffs(int(round(window_ms / step_ms)), poly)
    h = len(c) // 2
    yp = np.pad(y, (h, h), mode="edge")
    ys = np.convolve(yp, c[::-1], mode="valid")
    return [(int(tt), int(round(min(100, max(0, v))))) for tt, v in zip(t, ys)]


def bspline(actions, smoothing=0.5, step_ms=40):
    """Suavizado por spline (requiere scipy; si no está, devuelve las acciones tal cual)."""
    a = _arr(actions)
    if UnivariateSpline is None or len(a) < 6:
        return [tuple(map(int, x)) for x in a]
    keep = np.concatenate(([True], np.diff(a[:, 0]) > 0))
    a = a[keep]
    spl = UnivariateSpline(a[:, 0], a[:, 1], k=3, s=len(a) * float(smoothing) ** 2 * 25)
    t = np.arange(a[0, 0], a[-1, 0] + 1, step_ms)
    return [(int(tt), int(round(min(100, max(0, v))))) for tt, v in zip(t, spl(t))]


def normalize_range(actions, lo=5, hi=95):
    """Expande/comprime el rango dinámico de pos para ocupar [lo, hi] (por percentiles 2-98, sin tocar los ceros)."""
    a = _arr(actions)
    if len(a) < 3:
        return [tuple(map(int, x)) for x in a]
    live = a[:, 1][a[:, 1] > 0]
    if len(live) < 3:
        return [tuple(map(int, x)) for x in a]
    p_lo, p_hi = np.percentile(live, 2), np.percentile(live, 98)
    if p_hi - p_lo < 5:
        return [tuple(map(int, x)) for x in a]
    out = np.where(a[:, 1] > 0, lo + (a[:, 1] - p_lo) * (hi - lo) / (p_hi - p_lo), 0.0)
    out = np.clip(out, 0, 100)
    return [(int(t), int(round(v))) for t, v in zip(a[:, 0], out)]


def simplify(actions, tol=1.5, min_gap_ms=40):
    """Quita puntos redundantes (casi colineales) y los demasiado juntos."""
    a = _arr(actions)
    if len(a) < 3:
        return [tuple(map(int, x)) for x in a]
    out = [a[0]]
    for i in range(1, len(a) - 1):
        p0, p1, p2 = out[-1], a[i], a[i + 1]
        if p1[0] - p0[0] < min_gap_ms:
            continue
        frac = (p1[0] - p0[0]) / max(1.0, p2[0] - p0[0])
        if abs(p0[1] + (p2[1] - p0[1]) * frac - p1[1]) > tol:
            out.append(p1)
    out.append(a[-1])
    return [(int(t), int(round(v))) for t, v in out]


def rezero(actions, panels):
    """Fuerza 0 en los intervalos de paneles bloqueados (la limpieza nunca debe reactivarlos)."""
    ranges = [(p["start"], p["start"] + p["duration"]) for p in panels if p.get("blocked")]
    if not ranges:
        return list(actions)
    out = []
    for t, v in actions:
        out.append((t, 0 if any(a <= t <= b for a, b in ranges) else v))
    return out


def clean(actions, panels=(), window_ms=300, poly=3, rng=(5, 95), use_spline=False):
    out = bspline(actions) if use_spline else savgol(actions, window_ms, poly)
    out = normalize_range(out, *rng)
    out = simplify(out)
    return rezero(out, panels)


def clean_page(page, cfg):
    """Limpia el canal principal de una página (dict con 'panels', 'main')."""
    page["main"] = clean(page["main"], page["panels"], cfg.cleaner_window_ms, cfg.cleaner_poly, cfg.cleaner_range)
    return page
