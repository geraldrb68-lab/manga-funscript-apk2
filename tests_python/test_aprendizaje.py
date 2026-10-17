import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "app", "src", "main", "python"))
import aprendizaje as AP  # noqa: E402
from seguridad import MINOR_TAGS  # noqa: E402


class TestAprendizaje(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "aprendizaje.json")

    def test_falta_sube_el_ajuste_de_sus_etiquetas(self):
        a = AP.Aprendizaje(self.path)
        a.registrar("g1", 3, ["sex"], "falta")
        self.assertGreater(a.ajuste(["sex"]), 0)

    def test_sobra_baja_el_ajuste(self):
        a = AP.Aprendizaje(self.path)
        a.registrar("g1", 3, ["sex"], "sobra")
        self.assertLess(a.ajuste(["sex"]), 0)

    def test_intensidad_usa_el_delta(self):
        a = AP.Aprendizaje(self.path)
        a.registrar("g1", 1, ["handjob"], "intensidad", delta=-0.5)
        self.assertLess(a.ajuste(["handjob"]), 0)

    def test_ajuste_acotado_aunque_se_corrija_muchas_veces(self):
        a = AP.Aprendizaje(self.path)
        for _ in range(1000):
            a.registrar("g1", 1, ["sex"], "falta")
        self.assertLessEqual(a.ajuste(["sex"]), AP.MAX_BIAS + 1e-9)
        self.assertLessEqual(a.ajustar(0.9, ["sex"]), 1.0)
        self.assertGreaterEqual(a.ajustar(0.05, ["sex"]), 0.0)

    def test_menores_se_rechazan_sin_cambiar_nada(self):
        a = AP.Aprendizaje(self.path)
        for tag in MINOR_TAGS:
            with self.assertRaises(AP.RechazadoError):
                a.registrar("g1", 1, ["1girl", tag], "falta")
        self.assertEqual(a.bias, {})
        self.assertEqual(a.records, [])

    def test_menor_por_etiqueta_de_galeria_tambien_se_rechaza(self):
        a = AP.Aprendizaje(self.path)
        with self.assertRaises(AP.RechazadoError):
            a.registrar("g1", 1, ["female:lolicon", "sex"], "falta")

    def test_tipo_desconocido_falla(self):
        a = AP.Aprendizaje(self.path)
        with self.assertRaises(ValueError):
            a.registrar("g1", 1, ["sex"], "otra_cosa")

    def test_intensidad_sin_delta_falla(self):
        a = AP.Aprendizaje(self.path)
        with self.assertRaises(ValueError):
            a.registrar("g1", 1, ["sex"], "intensidad")

    def test_persistencia_entre_sesiones(self):
        a = AP.Aprendizaje(self.path)
        a.registrar("g1", 2, ["sex", "fingering"], "falta")
        b = AP.Aprendizaje(self.path)
        self.assertEqual(b.bias, a.bias)
        self.assertEqual(len(b.records), 1)

    def test_archivo_corrupto_se_respalda_y_arranca_vacio(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{esto no es json")
        a = AP.Aprendizaje(self.path)
        self.assertEqual(a.bias, {})
        self.assertTrue(os.path.exists(self.path + ".corrupto"))

    def test_historial_acotado(self):
        a = AP.Aprendizaje(self.path)
        for i in range(AP.MAX_RECORDS + 20):
            a.registrar("g1", i, ["sex"], "falta")
        self.assertEqual(len(a.records), AP.MAX_RECORDS)

    def test_decide_respeta_el_ajuste_aprendido(self):
        a = AP.Aprendizaje(self.path)
        self.assertFalse(a.decide(0.30, ["sex"], umbral=0.35))
        for _ in range(10):
            a.registrar("g1", 1, ["sex"], "falta")
        self.assertTrue(a.decide(0.30, ["sex"], umbral=0.35))

    def test_archivo_guardado_es_json_valido(self):
        a = AP.Aprendizaje(self.path)
        a.registrar("g1", 1, ["sex"], "falta")
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["version"], 1)
        self.assertIn("sex", data["bias"])


if __name__ == "__main__":
    unittest.main()
