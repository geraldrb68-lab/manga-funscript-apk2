import os
import re
import sys
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "app", "src", "main", "python"))
import seguridad as SG  # noqa: E402



class TestSeguridad(unittest.TestCase):
    def test_bloquea_menor_por_etiqueta_de_viñeta(self):
        self.assertEqual(SG.minor_hits(["1girl", "loli"]), ["loli"])

    def test_bloquea_menor_por_etiqueta_de_galeria_con_prefijo(self):
        self.assertEqual(SG.minor_hits(["female:lolicon"]), ["lolicon"])

    def test_normaliza_espacios_y_guiones(self):
        self.assertEqual(SG.minor_hits(["aged down"]), ["aged_down"])

    def test_adulto_no_bloquea(self):
        self.assertEqual(SG.minor_hits(["1girl", "sex", "fellatio"]), [])

    def test_apply_gate_bloquea_todo_si_galeria_tiene_menor(self):
        panels = [{"tags": [], "motion": True}, {"tags": ["sex"], "motion": True}]
        n = SG.apply_gate(panels, gallery_tags=["shota"])
        self.assertEqual(n, 2)
        self.assertTrue(all(p["blocked"] and not p["motion"] for p in panels))

    def test_apply_gate_sin_menores_no_toca_nada(self):
        panels = [{"tags": ["sex"], "motion": True}]
        self.assertEqual(SG.apply_gate(panels), 0)
        self.assertTrue(panels[0]["motion"])

    def test_listas_coinciden_con_tagger(self):
        """Si cambian MINOR_TAGS en tagger.py y no aquí, esta prueba falla."""
        path = os.environ.get("TAGGER_SRC")
        if not path or not os.path.isfile(path):
            self.skipTest("Define TAGGER_SRC apuntando a tagger.py del proyecto para comprobar la sincronía.")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        m = re.search(r"MINOR_TAGS\s*=\s*\{([^}]*)\}", src, re.S)
        found = set(re.findall(r'"([^"]+)"', m.group(1)))
        self.assertEqual(found, SG.MINOR_TAGS)


if __name__ == "__main__":
    unittest.main()
