import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "app", "src", "main", "python"))
import script_cleaner as SC  # noqa: E402


class TestScriptCleaner(unittest.TestCase):
    def setUp(self):
        t = np.arange(0, 3000, 50)
        pos = 50 + 45 * np.sin(t / 300.0) + np.random.default_rng(0).normal(0, 4, t.size)
        self.actions = [[float(a), float(b)] for a, b in zip(t, pos)]

    def test_salida_en_rango_y_ordenada(self):
        out = np.asarray(SC.clean(self.actions))
        self.assertEqual(out.shape[1], 2)
        self.assertTrue(np.all(out[:, 1] >= 0) and np.all(out[:, 1] <= 100))
        self.assertTrue(np.all(np.diff(out[:, 0]) >= 0))

    def test_panel_bloqueado_queda_en_reposo(self):
        panels = [{"blocked": True, "start": 0, "duration": 3000}]
        out = np.asarray(SC.clean(self.actions, panels=panels))
        self.assertTrue(np.all(out[:, 1] == 0) or np.all(out[:, 1] <= 5))

    def test_lista_vacia_no_falla(self):
        out = SC.clean([])
        self.assertEqual(len(out), 0)


if __name__ == "__main__":
    unittest.main()
