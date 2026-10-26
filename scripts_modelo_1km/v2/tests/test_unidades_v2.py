"""Pruebas de ``unidades_v2`` (R6): factores a 25 °C y 1 atm, regla del contraste y del rótulo, y rótulos de ficha.

Casi todo es sintético. Dos pruebas leen datos reales, sólo columnas de rótulo y de decisión (ningún valor de
concentración ni métrica): los manifiestos de la ampliación y la primera corrida del contraste. Se saltan si no están.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))
import _rutas_v2 as rv  # noqa: E402
import red_ampliada_v2 as ra  # noqa: E402
import unidades_v2 as uv  # noqa: E402

CONTRASTE_PRIMERA = Path(os.environ.get(
    "AIR_POLLUTION_CONTRASTE_UNIDADES",
    V2.parents[2] / "Air-Pollution-Health-Chile" / "auditoria" / "20261024" / "sinca_al_modelo" /
    "contraste_unidades_cams.csv"))


class FactoresTests(unittest.TestCase):
    def test_25_grados(self):
        self.assertAlmostEqual(uv.ug_m3n_por_ppb("no2"), 1.880, places=3)        # decreto NO2 e informe SMA
        self.assertAlmostEqual(41.60 / round(uv.ug_m3n_por_ppb("no2"), 3), 22.13, places=2)
        self.assertAlmostEqual(uv.ug_m3n_por_ppb("o3"), 1.962, places=3)
        self.assertAlmostEqual(uv.ug_m3n_por_ppb("so2"), 2.619, places=3)
        self.assertAlmostEqual(uv.PPB_POR_UG_M3N_NO2, 0.5318, places=4)

    def test_masas_molares_literales_de_r6(self):
        """T12 (corrección, [delegada]): la conversión usa las masas molares literales de R6 (NO2 46,0055; O3 47,998;
        SO2 64,064), no el 47,9982 del programa del contraste; CO, que R6 no da, la del programa. El contraste de la
        segunda corrida usa las mismas: T12 no hace excepción para él (ronda 4, menor 9)."""
        import contraste_unidades_v2 as cu
        self.assertEqual(uv.MASA_MOLAR, {"no2": 46.0055, "o3": 47.998, "so2": 64.064, "co": 28.0101})
        self.assertAlmostEqual(uv.factor_a_ppb("o3"), 24.4654 / 47.998, places=15)
        self.assertEqual(cu.M, uv.MASA_MOLAR)                                # el contraste y la conversión, la misma
        for g in ("no2", "o3", "so2"):
            self.assertAlmostEqual(cu.CANDIDATOS[g]["µg/m³N"], 1 / uv.factor_a_ppb(g), places=15)
        bloque = V2.parents[2] / "Air-Pollution-Health-Chile" / "auditoria" / "20261024" / "sinca_al_modelo" / \
            "ENMIENDA_2_BLOQUE_RED_AMPLIADA.md"
        if bloque.exists():                                              # el texto anclado (repositorio de salud)
            self.assertIn("M: NO2 46,0055; O3 47,998; SO2 64,064 g/mol.", bloque.read_text(encoding="utf-8"))

    def test_snifa(self):
        f = uv.factores_snifa()
        self.assertEqual(f["charrua"], 1.0)
        self.assertEqual(f["progreso"], 1.0)
        self.assertAlmostEqual(f["el_penon"], 0.5318, places=4)
        self.assertGreater(f["el_penon"] / (22.414 / 46.0055), 1.09)            # 9,2 % más que a 0 °C (v1)

    def test_a_ppb(self):
        np.testing.assert_allclose(uv.a_ppb([18.80, 0.0], "no2"), [18.80 * 24.4654 / 46.0055, 0.0])


class ReglaTests(unittest.TestCase):
    def test_referencia_ppb(self):
        d = uv.decidir_unidad("no2", "ppb", "indeterminada")
        self.assertEqual((d["entra"], d["factor"]), (True, 1.0))

    def test_rotulo_confirmado_se_convierte(self):
        d = uv.decidir_unidad("o3", "μg/m3N", "µg/m³N")
        self.assertTrue(d["entra"])
        self.assertAlmostEqual(d["factor"], uv.factor_a_ppb("o3"))

    def test_rotulo_contradicho_entra_en_ppb(self):
        d = uv.decidir_unidad("o3", "µg/m³N", "ppb")
        self.assertEqual((d["entra"], d["factor"], d["unidad_valores"]), (True, 1.0, "ppb"))

    def test_indeterminado_decide_el_rotulo(self):
        d = uv.decidir_unidad("no2", "µg/m³N", "indeterminada")
        self.assertTrue(d["entra"])
        self.assertAlmostEqual(d["factor"], uv.PPB_POR_UG_M3N_NO2)
        self.assertIn("(I)", d["regla"])

    def test_sin_unidad_fuera_salvo_que_el_contraste_la_ubique(self):
        self.assertFalse(uv.decidir_unidad("no2", None, "indeterminada")["entra"])
        d = uv.decidir_unidad("o3", float("nan"), "ppb")                         # caso 609 y 517 de O3
        self.assertEqual((d["entra"], d["factor"]), (True, 1.0))
        d = uv.decidir_unidad("o3", "", "µg/m³N")
        self.assertAlmostEqual(d["factor"], uv.factor_a_ppb("o3"))

    def test_pm25_sin_contraste(self):
        for rot in ("µg/m3", None, "μg/m3"):
            d = uv.decidir_unidad("pm25", rot, None)
            self.assertEqual((d["entra"], d["factor"], d["unidad_valores"]), (True, 1.0, "µg/m³"))

    def test_unidad_no_prevista_falla(self):
        with self.assertRaises(ValueError):
            uv.decidir_unidad("no2", "µg/m³N", "ppm o mg/m³N")


class RotulosTests(unittest.TestCase):
    def manifiestos(self, diaria="μg/m3N", horaria="μg/m3N"):
        actuales = pd.DataFrame({"estacion": ["801", "801", "802"], "contaminante": ["no2", "pm25", "o3"],
                                 "resolucion": "horario"})
        otras = pd.DataFrame({"estacion": ["801", "802", "999"], "contaminante": ["no2", "o3", "no2"],
                              "resolucion": ["diario", "diario", "diario"], "grupo": ["configurada"] * 3,
                              "unidad_ficha": [diaria, "ppb", "ppb"]})
        act = pd.DataFrame({"estacion": ["801"], "contaminante": ["no2"], "resolucion": ["horario"],
                            "unidad_ficha": [horaria]})
        nuevas = pd.DataFrame({"estacion": ["N1", "N2"], "contaminante": ["no2", "o3"], "resolucion": "horario",
                               "unidad_ficha": ["ppb", None]})
        return nuevas, act, otras, actuales

    def test_rotulos(self):
        r = uv.rotulos_de_ficha(*self.manifiestos()).set_index(["estacion", "contaminante"])
        self.assertEqual(r.loc[("801", "no2"), "rotulo"], "µg/m³N")
        self.assertEqual(r.loc[("801", "no2"), "fuente_rotulo"], "otras_series_diaria")
        self.assertEqual(r.loc[("801", "pm25"), "rotulo"], "(sin unidad)")
        self.assertEqual(r.loc[("N2", "o3"), "rotulo"], "(sin unidad)")
        self.assertEqual(r.loc[("N1", "no2"), "grupo"], "nueva")

    def test_la_actualizacion_debe_coincidir_con_la_diaria(self):
        with self.assertRaises(ValueError):
            uv.rotulos_de_ficha(*self.manifiestos(horaria="ppb"))

    def test_unidades_de_series_falla_cerrado(self):
        rot = uv.rotulos_de_ficha(*self.manifiestos())
        con = pd.DataFrame({"estacion": ["801", "802", "N1", "N2"], "contaminante": ["no2", "o3", "no2", "o3"],
                            "grupo": "x", "rotulo": ["µg/m³N", "ppb", "ppb", "(sin unidad)"],
                            "unidad_que_indica": ["indeterminada", "ppb", "indeterminada", "ppb"]})
        t = uv.unidades_de_series(rot, con).set_index(["estacion", "contaminante"])
        self.assertAlmostEqual(t.loc[("801", "no2"), "factor"], uv.PPB_POR_UG_M3N_NO2)
        self.assertTrue(t.loc[("N2", "o3"), "entra"])
        with self.assertRaises(ValueError):
            uv.unidades_de_series(rot, con[con["estacion"] != "N1"])           # falta en el contraste
        con2 = con.copy()
        con2.loc[0, "rotulo"] = "ppb"
        with self.assertRaises(ValueError):
            uv.unidades_de_series(rot, con2)                                   # el contraste usó otro rótulo


class SinCoordenadaTests(unittest.TestCase):
    """B1: una serie sin coordenada usable en R8 (la 518) no se deriva ni está en la segunda corrida del contraste;
    sale antes de la regla de unidades, que si no detendría el armado."""

    def setUp(self):
        self.rot = pd.DataFrame({"estacion": ["801", "Z9", "Z9"], "contaminante": ["no2", "no2", "o3"],
                                 "grupo": ["actual", "nueva", "nueva"], "rotulo": ["ppb", "µg/m³N", "µg/m³N"],
                                 "fuente_rotulo": "x"})
        self.segunda = pd.DataFrame({"estacion": ["801"], "contaminante": ["no2"], "grupo": ["actual"],
                                     "rotulo": ["ppb"], "unidad_que_indica": ["indeterminada"]})

    def test_la_regla_sola_se_detiene(self):
        with self.assertRaises(ValueError):                              # lo que pasaba antes del arreglo
            uv.unidades_de_series(self.rot, self.segunda)

    def test_sale_antes_y_queda_registrada(self):
        tabla, fuera = uv.unidades_desde(self.rot, self.segunda, {"801"})
        self.assertEqual(list(tabla["estacion"]), ["801"])
        self.assertEqual(sorted(zip(fuera["estacion"], fuera["contaminante"])), [("Z9", "no2"), ("Z9", "o3")])
        self.assertTrue(fuera["regla"].str.contains("R8").all())

    def test_la_huella_del_contraste_es_obligatoria(self):
        with self.assertRaises(SystemExit):
            uv.unidades_red2(Path("no_existe"), Path("no_existe.csv"), None)

    def test_el_armado_rechaza_la_primera_corrida(self):
        """Menor 24: rige la segunda corrida (R6); el armado pide rechazar la huella de la primera, antes de leer."""
        with self.assertRaises(SystemExit) as e:
            uv.unidades_red2(Path("no_existe"), Path("no_existe.csv"), uv.SHA_CONTRASTE_PRIMERA, con_coordenada=set(),
                             rechazar_primera=True)
        self.assertIn("segunda corrida", str(e.exception))
        self.assertIn("rige la segunda corrida (R6)", uv.__doc__)


class DatosRealesTests(unittest.TestCase):
    """Sólo rótulos, decisiones y conteos."""

    def setUp(self):
        self.datos = rv.RutasV2.desde_entorno().datos
        if not (self.datos / ra.MANIFIESTO_NUEVAS).exists():
            self.skipTest("sin el disco de datos")
        if not CONTRASTE_PRIMERA.exists():
            self.skipTest("sin la primera corrida del contraste (repositorio de salud)")

    def test_la_regla_reproduce_las_listas_del_bloque(self):
        t, info = uv.unidades_red2(self.datos, CONTRASTE_PRIMERA, uv.SHA_CONTRASTE_PRIMERA)
        no2, o3 = t[t["contaminante"] == "no2"], t[t["contaminante"] == "o3"]
        self.assertEqual(sorted(no2.loc[~no2["entra"], "estacion"]),
                         sorted(ra.ACTUALES_FUERA_SIN_UNIDAD["no2"] + ra.NUEVAS["no2"]["sin"]))
        self.assertEqual(sorted(o3.loc[~o3["entra"], "estacion"]),
                         sorted(ra.ACTUALES_FUERA_SIN_UNIDAD["o3"] + ("A02", "A03")))
        conv_no2 = set(no2.loc[no2["entra"] & (no2["factor"] != 1.0), "estacion"])
        self.assertEqual(conv_no2, {"514", "515", "802", "826", "827", "830", "841", "854", "870"} |
                         (set(ra.NUEVAS["no2"]["µg/m³N"]) - {"518"}))
        conv_o3 = set(o3.loc[o3["entra"] & (o3["factor"] != 1.0), "estacion"])
        self.assertEqual(conv_o3, {"826", "221", "329", "614", "830", "207", "216", "876", "E01"})
        self.assertEqual(sorted({(f["estacion"], f["contaminante"]) for f in info["fuera_por_coordenadas"]}),
                         [("518", "no2"), ("518", "o3")])
        ppb_o3 = set(o3.loc[o3["entra"] & (o3["factor"] == 1.0) & (o3["rotulo"] != "ppb"), "estacion"])
        self.assertEqual(ppb_o3, {"547", "841", "870", "215", "519", "533", "534", "609", "517"})
        self.assertTrue(t.loc[t["contaminante"] == "pm25", "entra"].all())
        self.assertEqual(int((t["contaminante"] == "pm25").sum()), 109)


    def test_segunda_corrida_sin_la_518(self):
        """Como c6 de la revisión: una segunda corrida sólo trae series derivables (sin la 518); la regla no se detiene.
        Sólo columnas de rótulo y de decisión."""
        import json
        import tempfile
        geo = {f["properties"]["estacion"] for rel in (ra.GEOJSON_NUEVAS, ra.GEOJSON_ACTUALES)
               for f in json.loads((self.datos / rel).read_text(encoding="utf-8"))["features"]}
        primera = pd.read_csv(CONTRASTE_PRIMERA, dtype=str)
        segunda = primera[primera["estacion"].isin(geo) & primera["contaminante"].isin(["no2", "o3"])]
        self.assertNotIn("518", set(segunda["estacion"]))
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "segunda.csv"
            segunda.to_csv(ruta, index=False)
            t, info = uv.unidades_red2(self.datos, ruta, uv.sha256_archivo(ruta))
        self.assertNotIn("518", set(t["estacion"]))
        self.assertEqual(len(info["fuera_por_coordenadas"]), 2)


if __name__ == "__main__":
    unittest.main()