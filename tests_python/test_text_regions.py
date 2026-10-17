"""Equivalencia del port de text_regions (numpy/scipy) con el original (OpenCV) en páginas sintéticas tipo manga.

Requiere cv2 y el text_regions.py original del proyecto (ruta en la variable TR_ORIG_DIR). Sin ellos, se omite.
Mide: mismos bloques, mismo tipo y polaridad, mismas onomatopeyas, y diferencia de la imagen limpia.
"""
import importlib.util
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(__file__)
PORT_DIR = os.path.join(HERE, "..", "app", "src", "main", "python")
ORIG_DIR = os.environ.get("TR_ORIG_DIR", "")
sys.path.insert(0, PORT_DIR)
try:
    import cv2
except ImportError:
    cv2 = None


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def make_page(seed, h=520, w=400):
    rng = np.random.default_rng(seed)
    img = np.full((h, w, 3), rng.integers(200, 245), np.uint8)
    for y in range(0, h, 7):
        for x in range(0, w, 7):
            if rng.random() < 0.35:
                cv2.circle(img, (x, y), 1, (90, 90, 90), -1)
    for _ in range(12):
        x0, y0 = rng.integers(0, w), rng.integers(0, h)
        cv2.line(img, (x0, y0), (x0 + rng.integers(-60, 60), y0 + rng.integers(-60, 60)), (60, 60, 60), 1)
    for _ in range(rng.integers(1, 3)):
        cx, cy = rng.integers(90, w - 90), rng.integers(60, h - 60)
        cv2.ellipse(img, (cx, cy), (80, 45), 0, 0, 360, (255, 255, 255), -1)
        cv2.ellipse(img, (cx, cy), (80, 45), 0, 0, 360, (0, 0, 0), 2)
        cv2.putText(img, "HELLO THERE", (cx - 60, cy + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
    cv2.ellipse(img, (110, 380), (70, 40), 0, 0, 360, (80, 230, 255), -1)
    cv2.putText(img, "WHAT?", (80, 386), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    cv2.rectangle(img, (220, 440), (380, 500), (235, 235, 235), -1)
    cv2.rectangle(img, (220, 440), (380, 500), (0, 0, 0), 1)
    cv2.putText(img, "Night fell.", (230, 475), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    if seed % 2 == 0:
        cv2.putText(img, "SLAP!", (240, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 0, 0), 5)
    return np.clip(img.astype(np.int16) + rng.integers(-4, 5, img.shape), 0, 255).astype(np.uint8)


def _iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    return inter / max(1, aw * ah + bw * bh - inter)


@unittest.skipIf(cv2 is None or not ORIG_DIR, "requiere cv2 y TR_ORIG_DIR apuntando al proyecto original")
class TestTextRegionsEquivalence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.O = _load(os.path.join(ORIG_DIR, "text_regions.py"), "tr_orig")
        cls.P = _load(os.path.join(PORT_DIR, "text_regions.py"), "tr_port")

    def test_bloques_y_onomatopeyas_coinciden(self):
        total_o = total_p = 0
        for seed in range(12):
            img = make_page(seed)
            bo, bp = self.O.find_text_blocks(img), self.P.find_text_blocks(img)
            self.assertEqual(len(bo), len(bp), f"semilla {seed}")
            total_o += len(bo)
            total_p += len(bp)
            so, sp = self.O.find_sfx_blocks(img), self.P.find_sfx_blocks(img)
            self.assertEqual(len(so), len(sp), f"sfx semilla {seed}")
        self.assertGreater(total_o, 0)

    def test_tipo_y_polaridad_coinciden(self):
        for seed in range(12):
            img = make_page(seed)
            bo, bp = self.O.find_text_blocks(img), self.P.find_text_blocks(img)
            used = set()
            for a in bo:
                j = max(range(len(bp)), key=lambda k: _iou(a.box, bp[k].box))
                self.assertGreaterEqual(_iou(a.box, bp[j].box), 0.7)
                self.assertNotIn(j, used)
                used.add(j)
                self.assertEqual(a.kind, bp[j].kind)
                self.assertEqual(a.polarity, bp[j].polarity)

    def test_imagen_limpia_casi_igual(self):
        worst_p20 = 0.0
        for seed in range(12):
            img = make_page(seed)
            g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            bo, bp = self.O.find_text_blocks(img), self.P.find_text_blocks(img)
            for a in bo:
                j = max(range(len(bp)), key=lambda k: _iou(a.box, bp[k].box))
                ga, _ = self.O.clean_crop(g, a)
                gb, _ = self.P.clean_crop(g, bp[j])
                self.assertEqual(ga.shape, gb.shape)
                d = np.abs(ga.astype(int) - gb.astype(int))
                worst_p20 = max(worst_p20, (d > 20).mean() * 100)
        # Medido: ampliación exacta; reducción con no-enteros difiere en bordes de letra (ver docs).
        self.assertLess(worst_p20, 5.0)


if __name__ == "__main__":
    unittest.main()
