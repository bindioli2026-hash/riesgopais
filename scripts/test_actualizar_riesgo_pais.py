import copy
import unittest
from datetime import date, datetime, timezone

from actualizar_riesgo_pais import (
    aplicar,
    fecha_iso,
    filas_ambito_historico,
    numero,
    registro,
    rueda_ambito,
    rueda_rava,
    rueda_valida,
)


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


class CierresTest(unittest.TestCase):
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

    def test_mezcla_fuentes_con_formato_de_ambito(self):
        d = ejemplo()
        filas = [{"fecha": "2026-10-22", "valor": 704}] + filas_ambito_historico(
            [["Fecha", "Puntos"], ["30-10-2026", "787,00"], ["29-10-2026", "741,00"]]
        )
        cambio, n = aplicar(d, filas, self.hoy, self.instante)
        self.assertEqual(n, 2)
        self.assertEqual(d["argentina"]["serie"][-2:], [["2026-10-29", 741], ["2026-10-30", 787]])

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
                {"fecha": "02-11-2026", "valor": "abc"},
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

    def test_falla_si_la_fuente_no_trae_nada_comparable(self):
        d = ejemplo()
        with self.assertRaises(ValueError):
            aplicar(d, [{"fecha": "2026-10-10", "valor": 600}], self.hoy, self.instante)

    def test_parseo(self):
        self.assertEqual(numero("805,00"), 805.0)
        self.assertEqual(numero("1.234,5"), 1234.5)
        self.assertEqual(numero(831), 831.0)
        self.assertIsNone(numero("abc"))
        self.assertIsNone(numero(True))
        self.assertEqual(fecha_iso("03-11-2026"), "2026-11-03")
        self.assertEqual(fecha_iso("03/11/2026"), "2026-11-03")
        self.assertEqual(fecha_iso("2026-11-03"), "2026-11-03")
        self.assertIsNone(fecha_iso("3 de noviembre"))
        self.assertEqual(registro({"fecha": "2026-10-30", "valor": 786.6}, self.hoy), ("2026-10-30", 787))
        self.assertIsNone(registro({"fecha": "2026-10-30", "valor": 0}, self.hoy))
        self.assertIsNone(registro({"fecha": "2026-11-03", "valor": 700}, self.hoy))


class RuedaTest(unittest.TestCase):
    def setUp(self):
        self.hoy = date(2026, 11, 3)
        self.instante = datetime(2026, 11, 3, 20, 23, tzinfo=timezone.utc)  # 17:23 en Buenos Aires

    def base(self):
        d = ejemplo()
        d["argentina"]["serie"] += [["2026-10-30", 787], ["2026-11-02", 805]]
        d["argentina"]["ultimo"] = {"fecha": "2026-11-02", "valor": 805}
        d["argentina"]["intradiario"] = None
        return d

    def test_lectura_de_ambito(self):
        lectura = rueda_ambito({"ultimo": "831", "fecha": "03-11-2026", "variacion": "3,23%", "class-variacion": "up-red"})
        d = self.base()
        cambio, n = aplicar(d, [{"fecha": "2026-11-02", "valor": 805}], self.hoy, self.instante, lectura)
        self.assertTrue(cambio)
        self.assertEqual(n, 0)
        self.assertEqual(
            d["argentina"]["intradiario"],
            {
                "fecha": "2026-11-03",
                "valor": 831,
                "fuente": "Ámbito Financiero",
                "url": "https://www.ambito.com/contenidos/riesgo-pais.html",
                "hora": "17:23",
            },
        )
        self.assertEqual(d["argentina"]["ultimo"], {"fecha": "2026-11-02", "valor": 805})
        self.assertEqual(d["editorial"], {"corte": "2026-10-23"})

    def test_misma_lectura_no_genera_cambio(self):
        d = self.base()
        d["argentina"]["intradiario"] = {"fecha": "2026-11-03", "valor": 831, "fuente": "Ámbito Financiero", "url": "x", "hora": "16:23"}
        antes = copy.deepcopy(d)
        cambio, n = aplicar(d, [{"fecha": "2026-11-02", "valor": 805}], self.hoy, self.instante, {"fecha": "03-11-2026", "valor": "831"})
        self.assertFalse(cambio)
        self.assertEqual(d, antes)

    def test_lectura_nueva_reemplaza_valor_y_hora(self):
        d = self.base()
        d["argentina"]["intradiario"] = {"fecha": "2026-11-03", "valor": 826, "fuente": "Ámbito Financiero", "url": "x", "hora": "16:23"}
        cambio, n = aplicar(d, [{"fecha": "2026-11-02", "valor": 805}], self.hoy, self.instante, {"fecha": "03-11-2026", "valor": "831", "fuente": "Ámbito Financiero", "url": "x"})
        self.assertTrue(cambio)
        self.assertEqual(d["argentina"]["intradiario"]["valor"], 831)
        self.assertEqual(d["argentina"]["intradiario"]["hora"], "17:23")

    def test_el_cierre_oficial_del_dia_retira_la_lectura(self):
        d = self.base()
        d["argentina"]["intradiario"] = {"fecha": "2026-11-03", "valor": 831, "fuente": "Ámbito Financiero", "url": "x", "hora": "17:23"}
        filas = [{"fecha": "2026-11-02", "valor": 805}, {"fecha": "03-11-2026", "valor": "831,00"}]
        cambio, n = aplicar(d, filas, self.hoy, self.instante, {"fecha": "03-11-2026", "valor": "831"})
        self.assertEqual(n, 1)
        self.assertEqual(d["argentina"]["ultimo"], {"fecha": "2026-11-03", "valor": 831})
        self.assertIsNone(d["argentina"]["intradiario"])

    def test_lectura_de_un_dia_ya_cerrado_se_ignora(self):
        # Fin de semana o feriado: Ámbito sigue mostrando el valor del último día hábil.
        d = self.base()
        cambio, n = aplicar(d, [{"fecha": "2026-11-02", "valor": 805}], date(2026, 11, 7), self.instante, {"fecha": "02-11-2026", "valor": "805"})
        self.assertFalse(cambio)
        self.assertIsNone(d["argentina"]["intradiario"])

    def test_lectura_implausible_o_futura_se_descarta(self):
        ultimo = ["2026-11-02", 805]
        self.assertIsNone(rueda_valida({"fecha": "03-11-2026", "valor": "1200"}, ultimo, self.hoy))
        self.assertIsNone(rueda_valida({"fecha": "04-11-2026", "valor": "830"}, ultimo, self.hoy))
        self.assertIsNone(rueda_valida({"fecha": "03-11-2026", "valor": "n/d"}, ultimo, self.hoy))
        self.assertIsNone(rueda_valida(None, ultimo, self.hoy))
        self.assertEqual(rueda_valida({"fecha": "03-11-2026", "valor": "831"}, ultimo, self.hoy)["valor"], 831)

    def test_sin_fuente_conserva_la_lectura_vigente(self):
        d = self.base()
        d["argentina"]["intradiario"] = {"fecha": "2026-11-03", "valor": 831, "fuente": "Ámbito Financiero", "url": "x", "hora": "17:23"}
        antes = copy.deepcopy(d)
        cambio, n = aplicar(d, [{"fecha": "2026-11-02", "valor": 805}], date(2026, 11, 4), self.instante, None)
        self.assertFalse(cambio)
        self.assertEqual(d, antes)

    def test_sin_fuente_retira_lectura_alcanzada_o_malformada(self):
        d = self.base()
        d["argentina"]["intradiario"] = {"fecha": "2026-11-02", "valor": 800}
        cambio, n = aplicar(d, [{"fecha": "2026-11-02", "valor": 805}], self.hoy, self.instante, None)
        self.assertTrue(cambio)
        self.assertIsNone(d["argentina"]["intradiario"])
        d = self.base()
        d["argentina"]["intradiario"] = {"fecha": "2026-11-03", "valor": "831"}
        aplicar(d, [{"fecha": "2026-11-02", "valor": 805}], self.hoy, self.instante, None)
        self.assertIsNone(d["argentina"]["intradiario"])

    def test_parseo_de_rava(self):
        pagina = """
        <table><tr><th>Fecha</th><th>Cierre</th><th>Variación</th><th>Máximo</th><th>Mínimo</th></tr>
        <tr><td>03/11/2026</td><td>831</td><td>-</td><td>834</td><td>804</td></tr>
        <tr><td>02/11/2026</td><td>805</td><td>-</td><td>805</td><td>779</td></tr></table>
        """
        lectura = rueda_rava(pagina)
        self.assertEqual((lectura["fecha"], lectura["valor"], lectura["fuente"]), ("2026-11-03", "831", "Rava Bursátil"))
        with self.assertRaises(ValueError):
            rueda_rava("<html><body>sin tabla</body></html>")


if __name__ == "__main__":
    unittest.main()
