import copy
import unittest
from datetime import date, datetime, timezone

from actualizar_riesgo_pais import aplicar, registro


def ejemplo():
    return {
        "generado": "2026-10-23T18:22:00-03:00",
        "argentina": {
            "serie": [["2026-10-21", 674], ["2026-10-22", 704]],
            "ultimo": {"fecha": "2026-10-22", "valor": 704},
            "intradiario": {"fecha": "2026-10-23", "valor": 707},
        },
        "region": {"corte": "2026-09-30"},
        "editorial": {"corte": "2026-10-23"},
    }


class ActualizadorTest(unittest.TestCase):
    def setUp(self):
        self.hoy = date(2026, 11, 2)
        self.instante = datetime(2026, 11, 2, 16, 0, tzinfo=timezone.utc)

    def test_backfill_sin_tocar_otros_apartados(self):
        d = ejemplo()
        cambio, n = aplicar(
            d,
            [
                {"fecha": "2026-10-22", "valor": 704},
                {"fecha": "2026-10-23", "valor": 707},
                {"fecha": "2026-10-30", "valor": 787},
            ],
            self.hoy,
            self.instante,
        )
        self.assertTrue(cambio)
        self.assertEqual(n, 2)
        self.assertEqual(d["argentina"]["serie"][-1], ["2026-10-30", 787])
        self.assertEqual(d["argentina"]["ultimo"], {"fecha": "2026-10-30", "valor": 787})
        self.assertIsNone(d["argentina"]["intradiario"])
        self.assertEqual(d["editorial"], {"corte": "2026-10-23"})
        self.assertEqual(d["region"], {"corte": "2026-09-30"})
        self.assertEqual(d["generado"], "2026-11-02T13:00:00-03:00")

    def test_no_reescribe_cuando_no_hay_cambio(self):
        d = ejemplo()
        d["argentina"]["intradiario"] = None
        antes = copy.deepcopy(d)
        cambio, n = aplicar(d, [{"fecha": "2026-10-22", "valor": 704}], self.hoy, self.instante)
        self.assertFalse(cambio)
        self.assertEqual(n, 0)
        self.assertEqual(d, antes)

    def test_descarta_fechas_futuras_e_invalidos(self):
        d = ejemplo()
        cambio, n = aplicar(
            d,
            [
                {"fecha": "2026-10-22", "valor": 704},
                {"fecha": "2026-11-05", "valor": 900},
                {"fecha": "2026-11-02", "valor": True},
                {"fecha": "2026-11-02", "valor": -3},
                {"fecha": "2026-11-02", "valor": float("nan")},
                {"fecha": "2026/11/02", "valor": 800},
                "basura",
            ],
            self.hoy,
            self.instante,
        )
        self.assertEqual(n, 0)
        self.assertEqual(d["argentina"]["ultimo"]["fecha"], "2026-10-22")

    def test_corrige_ultimo_cierre(self):
        d = ejemplo()
        d["argentina"]["intradiario"] = None
        cambio, n = aplicar(d, [{"fecha": "2026-10-22", "valor": 705}], self.hoy, self.instante)
        self.assertTrue(cambio)
        self.assertEqual(n, 0)
        self.assertEqual(d["argentina"]["ultimo"]["valor"], 705)
        self.assertEqual(d["argentina"]["serie"][-1], ["2026-10-22", 705])

    def test_conserva_intradiario_de_hoy(self):
        d = ejemplo()
        d["argentina"]["intradiario"] = {"fecha": "2026-11-02", "hora": "12:30", "valor": 790}
        cambio, n = aplicar(d, [{"fecha": "2026-10-30", "valor": 787}], self.hoy, self.instante)
        self.assertEqual(n, 1)
        self.assertEqual(d["argentina"]["intradiario"]["valor"], 790)

    def test_conserva_intradiario_de_un_dia_sin_cierre_oficial_todavia(self):
        # El lunes 2/11 quedó una lectura provisoria; el martes la fuente aún no
        # publicó el cierre del lunes: la lectura se mantiene hasta que llegue.
        d = ejemplo()
        d["argentina"]["serie"].append(["2026-10-30", 787])
        d["argentina"]["ultimo"] = {"fecha": "2026-10-30", "valor": 787}
        d["argentina"]["intradiario"] = {"fecha": "2026-11-02", "valor": 805, "fuente": "El Cronista"}
        cambio, n = aplicar(d, [{"fecha": "2026-10-30", "valor": 787}], date(2026, 11, 3), self.instante)
        self.assertFalse(cambio)
        self.assertEqual(d["argentina"]["intradiario"]["valor"], 805)
        # Cuando la fuente publica el cierre del 2/11, la lectura provisoria se retira.
        cambio, n = aplicar(d, [{"fecha": "2026-11-02", "valor": 805}], date(2026, 11, 3), self.instante)
        self.assertEqual(n, 1)
        self.assertIsNone(d["argentina"]["intradiario"])

    def test_descarta_intradiario_futuro_o_con_valor_invalido(self):
        d = ejemplo()
        d["argentina"]["intradiario"] = {"fecha": "2026-11-09", "valor": 790}
        aplicar(d, [{"fecha": "2026-10-22", "valor": 704}], self.hoy, self.instante)
        self.assertIsNone(d["argentina"]["intradiario"])
        d = ejemplo()
        d["argentina"]["intradiario"] = {"fecha": "2026-11-02", "valor": "805"}
        aplicar(d, [{"fecha": "2026-10-22", "valor": 704}], self.hoy, self.instante)
        self.assertIsNone(d["argentina"]["intradiario"])

    def test_borra_intradiario_si_ya_hay_cierre_de_ese_dia(self):
        d = ejemplo()
        d["argentina"]["intradiario"] = {"fecha": "2026-11-02", "hora": "12:30", "valor": 790}
        cambio, n = aplicar(d, [{"fecha": "2026-11-02", "valor": 795}], self.hoy, self.instante)
        self.assertEqual(n, 1)
        self.assertIsNone(d["argentina"]["intradiario"])

    def test_intradiario_malformado_no_rompe(self):
        d = ejemplo()
        d["argentina"]["intradiario"] = {"valor": 790}
        cambio, n = aplicar(d, [{"fecha": "2026-10-22", "valor": 704}], self.hoy, self.instante)
        self.assertTrue(cambio)
        self.assertIsNone(d["argentina"]["intradiario"])

    def test_falla_si_la_fuente_no_trae_nada_comparable(self):
        d = ejemplo()
        with self.assertRaises(ValueError):
            aplicar(d, [{"fecha": "2026-10-10", "valor": 600}], self.hoy, self.instante)

    def test_registro_redondea_a_entero(self):
        self.assertEqual(registro({"fecha": "2026-10-30", "valor": 786.6}, self.hoy), ("2026-10-30", 787))
        self.assertIsNone(registro({"fecha": "2026-10-30", "valor": 0}, self.hoy))
        self.assertIsNone(registro({"fecha": "2026-11-03", "valor": 700}, self.hoy))


if __name__ == "__main__":
    unittest.main()
