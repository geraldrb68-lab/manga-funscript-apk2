"""Compara cada equivalente de cvcompat con OpenCV (solo se ejecuta si cv2 está instalado en el entorno de pruebas)."""
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "app", "src", "main", "python"))
try:
    import cv2
except ImportError:
    cv2 = None
import cvcompat as CC  # noqa: E402


def _page(seed=1, h=300, w=260):
    rng = np.random.default_rng(seed)
    img = np.full((h, w, 3), 230, np.uint8)
    cv2.ellipse(img, (130, 90), (90, 50), 0, 0, 360, (255, 255, 255), -1)
    cv2.ellipse(img, (130, 90), (90, 50), 0, 0, 360, (0, 0, 0), 2)
    cv2.putText(img, "AB", (60, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
    for y in range(0, h, 9):
        for x in range(0, w, 9):
            if (x // 9 + y // 9) % 2 == 0:
                cv2.circle(img, (x + 2, y), 1, (60, 60, 60), -1)
    return np.clip(img.astype(np.int16) + rng.integers(-6, 7, img.shape), 0, 255).astype(np.uint8)


@unittest.skipIf(cv2 is None, "requiere cv2 en el entorno de pruebas")
class TestCvCompat(unittest.TestCase):
    def setUp(self):
        self.im = _page()
        self.g = cv2.cvtColor(self.im, cv2.COLOR_BGR2GRAY)

    def test_gris_casi_igual(self):
        d = np.abs(cv2.cvtColor(self.im, cv2.COLOR_BGR2GRAY).astype(int) - CC.gray(self.im).astype(int))
        self.assertLessEqual(d.max(), 1)

    def test_lab_diferencia_pequena(self):
        ref = cv2.cvtColor(self.im, cv2.COLOR_BGR2LAB).astype(int)
        self.assertLessEqual(np.abs(ref - CC.lab(self.im).astype(int)).max(), 2)

    def test_gauss3_casi_igual(self):
        d = np.abs(cv2.GaussianBlur(self.g, (3, 3), 0).astype(int) - CC.gaussian_blur(self.g, 3).astype(int))
        self.assertLessEqual(d.max(), 1)

    def test_umbral_adaptativo_identico(self):
        ref = cv2.adaptiveThreshold(self.g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 14)
        mine = CC.adaptive_threshold(self.g, 31, 14, invert=True)
        self.assertTrue(np.array_equal(ref, mine))

    def test_componentes_identicas(self):
        bw = (self.g < 100).astype(np.uint8)
        for conn in (4, 8):
            n1, l1, s1, _ = cv2.connectedComponentsWithStats(bw, connectivity=conn)
            n2, l2, s2 = CC.connected(bw.astype(bool), conn)
            self.assertEqual(n1, n2)
            self.assertTrue(np.array_equal(s1[1:], s2[1:]))
            self.assertTrue(np.array_equal(l1, l2))

    def test_apertura_elipse_identica(self):
        ink = cv2.adaptiveThreshold(self.g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 14)
        for r in (3, 5):
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
            ref = cv2.morphologyEx(ink, cv2.MORPH_OPEN, k)
            mine = (CC.open_(ink > 0, CC.struct("ellipse", 2 * r + 1)) * 255).astype(np.uint8)
            self.assertTrue(np.array_equal(ref, mine))

    def test_dilatacion_par_e_impar_identicas(self):
        bw = (self.g < 100).astype(np.uint8)
        for sz in (2, 3):
            ref = cv2.dilate(bw, np.ones((sz, sz), np.uint8)).astype(bool)
            self.assertTrue(np.array_equal(ref, CC.dilate(bw > 0, CC.struct("square", sz))))

    def test_mediana_y_gradiente_identicos(self):
        self.assertTrue(np.array_equal(cv2.medianBlur(self.g, 3), CC.median_blur3(self.g)))
        self.assertTrue(np.array_equal(
            cv2.morphologyEx(self.g, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)), CC.morph_gradient3(self.g)))

    def test_ampliacion_cubica_identica(self):
        for sc in (1.5, 2.0, 3.2):
            ref = cv2.resize(self.g, None, fx=sc, fy=sc, interpolation=cv2.INTER_CUBIC)
            self.assertLessEqual(np.abs(ref.astype(int) - CC.resize(self.g, sc).astype(int)).max(), 1)

    def test_reduccion_entera_identica(self):
        ref = cv2.resize(self.g, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
        self.assertLessEqual(np.abs(ref.astype(int) - CC.resize(self.g, 0.5).astype(int)).max(), 1)

    def test_propiedades_de_contorno(self):
        n, lab, st, _ = cv2.connectedComponentsWithStats((self.g < 100).astype(np.uint8), connectivity=8)
        i = max(range(1, n), key=lambda k: st[k, 4])
        comp = lab == i
        cnts, _ = cv2.findContours(comp.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        c = max(cnts, key=cv2.contourArea)
        filled = np.zeros(self.g.shape, np.uint8)
        cv2.drawContours(filled, [c], -1, 1, -1)
        a_f, a_p, a_h, bb = CC.region_props(comp)
        self.assertEqual(int(filled.sum()), a_f)
        self.assertAlmostEqual(cv2.contourArea(cv2.convexHull(c)), a_h, delta=1.0)
        self.assertEqual(cv2.boundingRect(c), bb)
        # OpenCV mide el polígono con píxeles de contorno; aquí se aproxima. Tolerancia relativa del 0,02 %.
        self.assertAlmostEqual(cv2.contourArea(c), a_p, delta=0.0002 * a_p + 1)


if __name__ == "__main__":
    unittest.main()
