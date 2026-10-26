"""Pruebas de ``pliegues_v2``: geometría, agrupamientos, protocolos y el ciclo completo del manifiesto.

Los casos sintéticos ponen estaciones sobre un meridiano, donde la distancia haversine es exacta en
kilómetros, y usan los parámetros reales de ``config_v2.json``. El ciclo completo corre sobre carpetas
temporales con un catálogo, una red SNIFA, una grilla y paneles de juguete: no lee ni escribe datos reales.
"""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))
import _rutas_v2 as rv  # noqa: E402
import pliegues_v2 as pv  # noqa: E402

CFG = json.loads((V2 / "config_v2.json").read_text(encoding="utf-8"))
KM_POR_GRADO = pv.RADIO_TIERRA_KM * np.pi / 180.0
LAT0, LON0 = -33.0, -70.5


def lat_a(km: float) -> float:
    """Latitud a ``km`` kilómetros al norte de LAT0 sobre el meridiano LON0."""
    return LAT0 + km / KM_POR_GRADO


# Estaciones sintéticas: (código, km al norte, celda, región, en el panel).
#   A1–A2 a 0,5 km (conglomerado); B1–B2–B3 en cadena de 1,5 km (diámetro 3 km, un solo conglomerado);
#   C1–C2 a 3 km pero en la misma celda (se unen por la celda); D a 9 km de A1 (sale en LBO-10 de A);
#   E a 12,5 km de A1 (no sale); F fuera del panel a 1 km de C2 (no une nada, pero cuenta en el radio de LBO);
#   G1–G2 a 3 km con H fuera del panel en medio, a 1,5 km de cada una (H no las une).
ESTACIONES = [
    ("A1", 0.0, 101, "RM", True), ("A2", 0.5, 102, "RM", True),
    ("B1", 30.0, 201, "RV", True), ("B2", 31.5, 202, "RV", True), ("B3", 33.0, 203, "RV", True),
    ("C1", 60.0, 301, "RXVI", True), ("C2", 63.0, 301, "RXVI", True),
    ("D", -9.0, 401, "RM", True), ("E", -12.5, 501, "RM", True),
    ("F", 64.0, 601, "RXVI", False),
    ("G1", 100.0, 701, "RVIII", True), ("G2", 103.0, 702, "RVIII", True), ("H", 101.5, 801, "RVIII", False),
]
ANIOS = {"A1": {2000: 10, 2010: 20}, "A2": {2026: 5}, "B1": {2004: 7}, "B2": {2004: 3, 2005: 1}, "B3": {2012: 2},
         "C1": {2019: 4}, "C2": {2020: 6}, "D": {2001: 1}, "E": {2024: 9}, "G1": {2008: 2}, "G2": {2011: 8}}


def universo_sintetico() -> pd.DataFrame:
    est = pd.DataFrame([{"estacion": c, "nombre": f"Estación {c}", "red": "sinca", "region_sinca": reg,
                         "lat": lat_a(km), "lon": LON0, "cod_comuna": pd.NA, "celda": celda}
                        for c, km, celda, reg, _ in ESTACIONES])
    est["cod_comuna"] = est["cod_comuna"].astype("Int64")
    return pv.completar_universo(est, CFG)


def panel_sintetico() -> tuple[pd.DataFrame, pd.DataFrame]:
    filas = {c: sum(a.values()) for c, a in ANIOS.items()}
    datos = [{"estacion": c, "celda": celda, "region_sinca": reg, "lat_est": np.float32(lat_a(km)),
              "lon_est": np.float32(LON0), "filas": filas[c]}
             for c, km, celda, reg, en_panel in ESTACIONES if en_panel]
    por_est = pd.DataFrame(datos).set_index("estacion")
    conteos = pd.DataFrame([{"estacion": c, "anio": a, "filas": n} for c, por in ANIOS.items() for a, n in por.items()])
    return por_est, conteos


def contaminante_sintetico() -> dict:
    por_est, conteos = panel_sintetico()
    info = {"raiz": "raiz_v1", "ruta": "paneles/panel_x.parquet", "sha256": "0" * 64, "filas": int(por_est["filas"].sum())}
    return pv.construir_contaminante("pm25", universo_sintetico(), por_est, conteos, CFG, info)


class GeometriaTests(unittest.TestCase):
    def test_haversine_igual_a_la_v1(self):
        self.assertAlmostEqual(float(pv.haversine_km(0.0, 0.0, 1.0, 0.0)), KM_POR_GRADO, places=9)
        self.assertAlmostEqual(float(pv.haversine_km(lat_a(0), LON0, lat_a(9), LON0)), 9.0, places=9)

    def test_proyeccion_utm_19s(self):
        e, n = pv.proyectar([-69.0, -69.0], [0.0, -33.45], "EPSG:32719")
        self.assertAlmostEqual(e[0], 500000.0, places=6)
        self.assertAlmostEqual(n[0], 10000000.0, places=6)
        self.assertAlmostEqual(e[1], 500000.0, places=6)
        lon, lat = pv.a_lonlat(e, n, "EPSG:32719")
        np.testing.assert_allclose(lon, [-69.0, -69.0], atol=1e-9)
        np.testing.assert_allclose(lat, [0.0, -33.45], atol=1e-9)

    def test_bloques_de_la_rejilla_fija(self):
        ix, iy = pv.indices_bloque([74999.999, 75000.0, 150000.0], [0.0, 74999.0, 75000.0], (0.0, 0.0), 75000.0)
        np.testing.assert_array_equal(ix, [0, 1, 2])
        np.testing.assert_array_equal(iy, [0, 0, 1])
        self.assertEqual(pv.etiqueta_bloque(4, 83), "E004N083")
        self.assertEqual(pv.limites_bloque(4, 83, (0.0, 0.0), 75000.0),
                         {"este_min_m": 300000.0, "norte_min_m": 6225000.0, "este_max_m": 375000.0, "norte_max_m": 6300000.0})
        with self.assertRaises(ValueError):
            pv.etiqueta_bloque(-1, 5)

    def test_ventanas_de_la_v1(self):
        self.assertEqual(list(pv.ventana_de([2000, 2003, 2004, 2023, 2024, 2026], 2000, 2026)),
                         ["2000–2003", "2000–2003", "2004–2007", "2020–2023", "2024–2026", "2024–2026"])


class AgrupamientoTests(unittest.TestCase):
    def test_umbral_inclusivo_y_celda_compartida(self):
        D = np.array([[0.0, 2.0, 9.0], [2.0, 0.0, 9.0], [9.0, 9.0, 0.0]])
        self.assertEqual(pv.conglomerados(["a", "b", "c"], D, [1, 2, 3], 2.0), [("a", "b"), ("c",)])
        D[0, 1] = D[1, 0] = np.nextafter(2.0, 3.0)
        self.assertEqual(pv.conglomerados(["a", "b", "c"], D, [1, 2, 3], 2.0), [("a",), ("b",), ("c",)])
        self.assertEqual(pv.conglomerados(["a", "b", "c"], D, [1, 1, 3], 2.0), [("a", "b"), ("c",)])

    def test_componentes_conexas_por_cadena(self):
        D = np.array([[0.0, 1.5, 3.0], [1.5, 0.0, 1.5], [3.0, 1.5, 0.0]])
        self.assertEqual(pv.conglomerados(["x3", "x1", "x2"], D, [1, 2, 3], 2.0), [("x1", "x2", "x3")])

    def test_radio_de_lbo_inclusivo(self):
        D = np.array([[10.0, np.nextafter(10.0, 11.0), 0.0]])
        self.assertEqual(pv.excluidas_por_radio(D, ["b", "c", "a"], 10.0), ["a", "b"])


class ProtocolosTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = contaminante_sintetico()
        cls.prot = cls.d["protocolos"]
        cls.por_est, cls.conteos = panel_sintetico()
        cls.total = int(cls.por_est["filas"].sum())

    def grupos(self, prot: str) -> list[str]:
        return [f["grupo"] for f in self.prot[prot]["pliegues"]]

    def pliegue(self, prot: str, grupo: str) -> dict:
        return next(f for f in self.prot[prot]["pliegues"] if f["grupo"] == grupo)

    def test_loso_d(self):
        self.assertEqual(self.grupos("LOSO-D"), ["A1+A2", "B1+B2+B3", "C1+C2", "D", "E", "G1", "G2"])
        self.assertEqual([c["grupo"] for c in self.d["conglomerados_loso_d"]], ["A1+A2", "B1+B2+B3", "C1+C2"])
        c = next(x for x in self.d["conglomerados_loso_d"] if x["grupo"] == "C1+C2")
        self.assertEqual(c["aristas"], [{"a": "C1", "b": "C2", "km": 3.0, "misma_celda": True}])

    def test_semillas_y_k(self):
        for prot in pv.PROTOCOLOS:
            pl = self.prot[prot]["pliegues"]
            self.assertEqual([f["k"] for f in pl], list(range(len(pl))))
            self.assertEqual([f["semilla"] for f in pl], [[42, k] for k in range(len(pl))])
            self.assertEqual(self.grupos(prot), sorted(self.grupos(prot)))

    def test_particion_y_filas(self):
        for prot in ("LOSO-D", "BLQ-75", "LRO"):
            pl = self.prot[prot]["pliegues"]
            prueba = [s for f in pl for s in f["estaciones_prueba"]]
            self.assertEqual(sorted(prueba), sorted(self.por_est.index))
            self.assertEqual(sum(f["filas_prueba"] for f in pl), self.total)
            for f in pl:
                fuera = sorted(set(f["excluidas"]) - set(f["estaciones_prueba"]))
                if prot != "BLQ-75":                                         # BLQ-75 lleva el amortiguador
                    self.assertEqual(fuera, [])
                filas_fuera = int(self.por_est.loc[fuera, "filas"].sum()) if fuera else 0
                self.assertTrue(set(f["estaciones_prueba"]) <= set(f["excluidas"]))
                self.assertEqual(f["filas_fuera_del_pliegue"], filas_fuera)
                self.assertEqual(f["filas_entrenamiento_disponibles"], self.total - f["filas_prueba"] - filas_fuera)

    def test_blq_75_con_amortiguador(self):
        """Enmienda 1, punto 8: el bloque de prueba excluye además toda estación a <= 10 km de alguna suya."""
        u = universo_sintetico().set_index("estacion")
        km = {c: k for c, k, *_ in ESTACIONES}
        en_panel = set(self.por_est.index)
        for f in self.prot["BLQ-75"]["pliegues"]:
            miembros = f["estaciones_prueba"]
            cerca = sorted(s for s in en_panel if any(abs(km[s] - km[m]) <= 10.0 for m in miembros))
            fuera_panel = sorted(s for s in u.index if s not in en_panel and any(abs(km[s] - km[m]) <= 10.0 for m in miembros))
            with self.subTest(bloque=f["grupo"]):
                self.assertEqual(f["excluidas"], sorted(set(miembros) | set(cerca)))
                self.assertEqual(f["amortiguador"]["excluidas_por_amortiguador"], sorted(set(cerca) - set(miembros)))
                self.assertEqual(f["amortiguador"]["radio_incluye_fuera_del_panel"], fuera_panel)
                self.assertEqual(f["amortiguador"]["radio_km"], 10.0)
                entrena = [s for s in en_panel if s not in f["excluidas"]]
                otras = [s for s in en_panel if s not in miembros]
                self.assertAlmostEqual(f["distancia_minima_entrenamiento_km"],
                                       min(abs(km[s] - km[m]) for s in entrena for m in miembros), places=4)
                self.assertAlmostEqual(f["distancia_minima_sin_amortiguador_km"],
                                       min(abs(km[s] - km[m]) for s in otras for m in miembros), places=4)
                self.assertGreater(f["distancia_minima_entrenamiento_km"], 10.0)
        # G1 y G2 (a 3 km) quedan en bloques distintos: cada una sale del entrenamiento del bloque de la otra, y H
        # (fuera del panel, a 1,5 km) sólo se registra.
        g1 = next(f for f in self.prot["BLQ-75"]["pliegues"] if "G1" in f["estaciones_prueba"])
        g2 = next(f for f in self.prot["BLQ-75"]["pliegues"] if "G2" in f["estaciones_prueba"])
        self.assertNotEqual(g1["grupo"], g2["grupo"])
        self.assertIn("G2", g1["amortiguador"]["excluidas_por_amortiguador"])
        self.assertIn("G1", g2["amortiguador"]["excluidas_por_amortiguador"])
        self.assertEqual(g2["amortiguador"]["radio_incluye_fuera_del_panel"], ["H"])
        self.assertAlmostEqual(g2["distancia_minima_sin_amortiguador_km"], 3.0, places=4)
        reg = {b["grupo"]: b for b in self.d["bloques_blq75"]}
        self.assertEqual(reg[g2["grupo"]]["excluidas_por_amortiguador"], g2["amortiguador"]["excluidas_por_amortiguador"])
        self.assertEqual(reg[g2["grupo"]]["distancia_minima_entrenamiento_km"], g2["distancia_minima_entrenamiento_km"])

    def test_distancia_minima_en_los_protocolos_espaciales(self):
        km = {c: k for c, k, *_ in ESTACIONES}
        en_panel = set(self.por_est.index)
        for prot in ("LOSO-D", "LBO-10", "LRO"):
            for f in self.prot[prot]["pliegues"]:
                entrena = [s for s in en_panel if s not in f["excluidas"]]
                esperada = min(abs(km[s] - km[m]) for s in entrena for m in f["estaciones_prueba"])
                self.assertAlmostEqual(f["distancia_minima_entrenamiento_km"], esperada, places=4, msg=f"{prot} {f['grupo']}")
            umbral = {"LOSO-D": 2.0, "LBO-10": 10.0, "LRO": 0.0}[prot]           # por construcción de cada protocolo
            self.assertTrue(all(f["distancia_minima_entrenamiento_km"] > umbral for f in self.prot[prot]["pliegues"]))
        self.assertTrue(all("distancia_minima_entrenamiento_km" not in f for f in self.prot["LPO"]["pliegues"]))

    def test_parametros_de_la_enmienda(self):
        parametros, valores = pv.parametros_de(CFG)
        self.assertEqual(parametros["BLQ-75"]["amortiguador"]["radio_km"], 10.0)
        self.assertEqual(parametros["BLQ-75"]["amortiguador"]["comparacion"], "<=")
        self.assertEqual(parametros["BLQ-75"]["origen_m"], [0.0, 0.0])
        self.assertEqual(parametros["distancias"], {"formula": "haversine", "radio_tierra_km": 6371.0})
        self.assertEqual({v["campo"]: v["estado"] for v in valores},
                         {"protocolos.BLQ-75.origen_m": "ratificado", "protocolos.semilla.k": "ratificado"})
        sin = copy.deepcopy(CFG)
        sin["protocolos"]["BLQ-75"]["exclusion_adicional"] = "ninguna"            # la especificación original
        self.assertNotIn("amortiguador", pv.parametros_de(sin)[0]["BLQ-75"])
        self.assertIsNone(pv.radio_amortiguador_blq(sin))
        d = pv.construir_contaminante("pm25", universo_sintetico(), self.por_est, self.conteos, sin,
                                      {"sha256": "0" * 64})
        for f in d["protocolos"]["BLQ-75"]["pliegues"]:
            self.assertEqual(f["excluidas"], f["estaciones_prueba"])

    def test_lbo_10(self):
        self.assertEqual(self.grupos("LBO-10"), self.grupos("LOSO-D"))
        a = self.pliegue("LBO-10", "A1+A2")
        self.assertEqual(a["excluidas"], ["A1", "A2", "D"])                # D a 9 km sale; E a 12,5 km no
        self.assertEqual(a["filas_fuera_del_pliegue"], self.por_est.loc["D", "filas"])
        self.assertEqual(a["filas_entrenamiento_disponibles"],
                         self.total - int(self.por_est.loc[["A1", "A2", "D"], "filas"].sum()))
        c = self.pliegue("LBO-10", "C1+C2")
        self.assertEqual(c["excluidas"], ["C1", "C2"])
        self.assertEqual(c["radio_incluye_fuera_del_panel"], ["F"])
        for f in self.prot["LBO-10"]["pliegues"]:
            self.assertTrue(set(f["estaciones_prueba"]) <= set(f["excluidas"]))

    def test_las_estaciones_fuera_del_panel_no_unen_conglomerados(self):
        self.assertIn("G1", self.grupos("LOSO-D"))
        self.assertIn("G2", self.grupos("LOSO-D"))
        self.assertEqual(self.pliegue("LBO-10", "G1")["excluidas"], ["G1", "G2"])
        self.assertEqual(self.pliegue("LBO-10", "G1")["radio_incluye_fuera_del_panel"], ["H"])

    def test_blq_75(self):
        u = universo_sintetico().set_index("estacion")
        for f in self.prot["BLQ-75"]["pliegues"]:
            b = f["bloque"]
            self.assertEqual(f["grupo"], pv.etiqueta_bloque(b["ix"], b["iy"]))
            for s in f["estaciones_prueba"]:
                self.assertTrue(b["este_min_m"] <= u.loc[s, "este_m"] < b["este_max_m"])
                self.assertTrue(b["norte_min_m"] <= u.loc[s, "norte_m"] < b["norte_max_m"])

    def test_lro_con_nuble_como_rviii(self):
        self.assertEqual(self.grupos("LRO"), ["RM", "RV", "RVIII"])
        self.assertEqual(self.pliegue("LRO", "RVIII")["estaciones_prueba"], ["C1", "C2", "G1", "G2"])

    def test_lpo(self):
        self.assertEqual(self.grupos("LPO"), ["2000–2003", "2004–2007", "2008–2011", "2012–2015", "2016–2019",
                                              "2020–2023", "2024–2026"])
        pl = self.prot["LPO"]["pliegues"]
        self.assertEqual(sum(f["filas_prueba"] for f in pl), self.total)
        p0 = pl[0]
        self.assertEqual(p0["estaciones_prueba"], ["A1", "D"])
        self.assertEqual(p0["excluidas"], [])
        self.assertEqual(p0["exclusion_temporal"], {"anio_desde": 2000, "anio_hasta": 2003})
        self.assertEqual(p0["filas_prueba"], 11)
        self.assertEqual(p0["filas_entrenamiento_disponibles"], self.total - 11)
        self.assertFalse(self.prot["LPO"]["recalcula_vecindario"])

    def test_diagnosticos(self):
        dg = self.d["diagnosticos"]
        self.assertEqual(dg["pliegues_loso_v1_por_celda"], 10)            # 11 estaciones, C1 y C2 en una celda
        self.assertIn("lbo10_pliegues_iguales_a_loso_d", dg)
        self.assertLess(dg["coordenadas_panel_vs_modelo_dif_max_grados"], pv.TOLERANCIA_COORD_GRADOS)
        # Enmienda 1, punto 13: los conglomerados con diámetro mayor que 2 km quedan listados (B1–B2–B3 en cadena,
        # C1–C2 unidos por la celda).
        self.assertEqual([c["grupo"] for c in dg["conglomerados_encadenados"]], ["B1+B2+B3", "C1+C2"])
        self.assertEqual(dg["conglomerados_encadenados"][0], {"grupo": "B1+B2+B3", "diametro_km": 3.0, "arista_max_km": 1.5})
        self.assertEqual([c["encadenado"] for c in self.d["conglomerados_loso_d"]], [False, True, True])
        am = dg["blq75_amortiguador"]
        self.assertEqual(am["radio_km"], 10.0)
        self.assertEqual(am["bloques_con_exclusion_adicional"],
                         sum(1 for f in self.prot["BLQ-75"]["pliegues"] if len(f["excluidas"]) > len(f["estaciones_prueba"])))
        self.assertTrue(am["bloques_con_entrenamiento_a_radio_o_menos_sin_amortiguador"])
        self.assertGreater(am["distancia_minima_tras_amortiguador_km"], 10.0)

    def test_determinista_ante_el_orden_de_entrada(self):
        por_est, conteos = panel_sintetico()
        info = {"raiz": "raiz_v1", "ruta": "paneles/panel_x.parquet", "sha256": "0" * 64, "filas": int(por_est["filas"].sum())}
        u = universo_sintetico().sample(frac=1.0, random_state=3)
        d2 = pv.construir_contaminante("pm25", u, por_est.sample(frac=1.0, random_state=5),
                                       conteos.sample(frac=1.0, random_state=7), CFG, info)
        self.assertEqual(pv.sha256_json(d2), pv.sha256_json(self.d))

    def test_rechaza_coordenadas_que_no_calzan(self):
        por_est, conteos = panel_sintetico()
        por_est.loc["A1", "lat_est"] = np.float32(lat_a(0.5))
        with self.assertRaises(SystemExit):
            pv.construir_contaminante("pm25", universo_sintetico(), por_est, conteos, CFG, {})


class CicloCompletoTests(unittest.TestCase):
    """De punta a punta sobre archivos temporales: fijar, verificar, rechazar, reemplazar y anotar."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="pliegues-v2-")
        b = Path(self._tmp.name).resolve()
        self.base = b
        self.repo = b / "repo"
        scripts = self.repo / "scripts_modelo_1km" / "v2"
        scripts.mkdir(parents=True)
        shutil.copy2(V2 / rv.NOMBRE_CONTRATO, scripts / rv.NOMBRE_CONTRATO)
        shutil.copy2(V2 / rv.NOMBRE_CONFIG, scripts / rv.NOMBRE_CONFIG)
        # la red original (Enmienda 2): panel v1 y pliegues_v2.json
        self.r = rv.RutasRedOriginal(raiz_v2=b / "v2", raiz_v1=b / "v1", datos=b / "datos", repo=self.repo,
                                     scripts_v2=scripts)
        # Catálogo SINCA: cinco estaciones usables y una que no.
        sinca = [("RM", "S1", 0.0, 13101), ("RM", "S2", 1.2, 13101), ("RM", "S3", 20.0, 13102),
                 ("RV", "S4", 200.0, 5101), ("RV", "S5", 205.0, 5101), ("RV", "S9", 210.0, 5101)]
        cat = pd.DataFrame([{"region_sinca": reg, "estacion": c, "nombre": f"Sitio {c}", "lat": lat_a(km), "lon": LON0,
                             "cod_comuna_geografica": cod, "usable_geoespacial": c != "S9"} for reg, c, km, cod in sinca])
        (self.r.datos / "sinca").mkdir(parents=True)
        cat.to_csv(self.r.catalogo_sinca, index=False)
        # Red SNIFA: Charrúa con un primer registro no utilizable (otras coordenadas) y luego los buenos.
        self.r.snifa.parent.mkdir(parents=True)
        pd.DataFrame({"station_id": ["charrua", "charrua", "charrua", "quinel"],
                      "numeric_usable": [False, True, True, True],
                      "latitude": [lat_a(50.0), lat_a(5.0), lat_a(5.0), lat_a(7.0)],
                      "longitude": [LON0, LON0, LON0, LON0]}).to_parquet(self.r.snifa, index=False)
        # Grilla v1: una celda por estación (la SNIFA cae en una comuna de la RM).
        g = self.r.grilla_v1
        g.mkdir(parents=True)
        celdas = pd.DataFrame({"celda": [11, 12, 13, 14, 15, 16], "lat": [lat_a(k) for k in (0.0, 1.2, 20.0, 200.0, 205.0, 5.0)],
                               "lon": [LON0] * 6, "cod_comuna": [13101, 13101, 13102, 5101, 5101, 13103]})
        celdas.to_parquet(g / "celdas.parquet", index=False)
        pd.DataFrame({"estacion": ["S1", "S2", "S3", "S4", "S5", "S9"], "celda": [11, 12, 13, 14, 15, -1]}).to_parquet(
            g / "estaciones_enlaces.parquet", index=False)
        pd.DataFrame({"estacion": ["SNIFA-CHARRUA"], "celda": [16]}).to_parquet(g / "estaciones_enlaces_adicional.parquet", index=False)
        self.coords = {"S1": 0.0, "S2": 1.2, "S3": 20.0, "S4": 200.0, "S5": 205.0, "SNIFA-CHARRUA": 5.0}
        self.celdas = {"S1": 11, "S2": 12, "S3": 13, "S4": 14, "S5": 15, "SNIFA-CHARRUA": 16}
        self.regiones = {"S1": "RM", "S2": "RM", "S3": "RM", "S4": "RV", "S5": "RV", "SNIFA-CHARRUA": "RM"}
        self.escribir_panel("pm25", {"S1": {2000: 3, 2010: 2}, "S2": {2005: 4}, "S3": {2024: 1}, "S4": {2015: 2}, "S5": {2016: 5}})
        self.escribir_panel("no2", {"S1": {2019: 2}, "S4": {2020: 3}, "SNIFA-CHARRUA": {2021: 4}})

    def tearDown(self):
        self._tmp.cleanup()

    def escribir_panel(self, pol: str, anios: dict, sha_declarado: str | None = None) -> None:
        filas = [{"estacion": e, "celda": self.celdas[e], "region_sinca": self.regiones[e],
                  "lat_est": np.float32(lat_a(self.coords[e])), "lon_est": np.float32(LON0), "anio": np.int16(a), "obs": 1.0}
                 for e, por in anios.items() for a, n in por.items() for _ in range(n)]
        ruta = self.r.panel(pol)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(filas).to_parquet(ruta, index=False)
        sha = hashlib.sha256(ruta.read_bytes()).hexdigest()
        meta = {"sha256": sha_declarado or sha, "redes": ["sinca", "snifa"], "codigo": "prueba"}
        self.r.panel_meta(pol).write_text(json.dumps(meta), encoding="utf-8")

    def ejecutar(self, **kw):
        cfg = rv.cargar_config(self.r)
        cfg.pop("red_de_monitores", None)          # los pliegues de la red original (Enmienda 2: ver la prueba siguiente)
        return pv.ejecutar(self.r, cfg, **kw)

    def test_con_la_red_ampliada_no_corre(self):
        """Enmienda 2, R13: los pliegues de la red 2 los fija pliegues_red2_v2 (única fuente); este programa se
        detiene, también sin escribir y al volver a fijar."""
        cfg = rv.cargar_config(self.r)
        cfg.setdefault("red_de_monitores", {})
        for kw in ({}, {"escribir": False}, {"refijar": True}):
            with self.subTest(**kw), self.assertRaises(SystemExit) as e:
                pv.ejecutar(self.r, cfg, **kw)
            self.assertIn("pliegues_red2_v2", str(e.exception))
        self.assertFalse(self.r.raiz_v2.exists())

    def test_ciclo(self):
        m, estado = self.ejecutar()
        self.assertEqual(estado, "fijado")
        en_disco = rv.leer_json(self.r.manifiesto_pliegues)
        self.assertEqual(en_disco["huella_pliegues"], pv.huella_pliegues(en_disco))
        conteos = en_disco["conteos"]["pm25"]
        self.assertEqual({k: v for k, v in conteos.items() if k != "BLQ-75"}, {"LOSO-D": 4, "LBO-10": 4, "LRO": 2, "LPO": 6})
        self.assertGreaterEqual(conteos["BLQ-75"], 2)                 # la RM y la RV quedan a 200 km
        # S9 no es usable; la SNIFA toma las coordenadas de su primer registro utilizable y su región de la grilla.
        est = {e["estacion"]: e for e in en_disco["estaciones"]}
        self.assertEqual(sorted(est), ["S1", "S2", "S3", "S4", "S5", "SNIFA-CHARRUA"])
        self.assertAlmostEqual(est["SNIFA-CHARRUA"]["lat"], lat_a(5.0), places=12)
        self.assertEqual(est["SNIFA-CHARRUA"]["region_sinca"], "RM")
        self.assertEqual(est["SNIFA-CHARRUA"]["filas_panel"], {"pm25": 0, "no2": 4})
        loso = en_disco["contaminantes"]["pm25"]["protocolos"]["LOSO-D"]["pliegues"]
        self.assertEqual([f["grupo"] for f in loso], ["S1+S2", "S3", "S4", "S5"])
        # LBO-10 de S1+S2 mide el radio también sobre la SNIFA, que no está en el panel de PM2,5.
        lbo = en_disco["contaminantes"]["pm25"]["protocolos"]["LBO-10"]["pliegues"][0]
        self.assertEqual(lbo["radio_incluye_fuera_del_panel"], ["SNIFA-CHARRUA"])
        for nombre in ("pliegues_v2_resumen.csv", "pliegues_v2_pliegues.csv", "pliegues_v2_conglomerados_loso_d.csv",
                       "pliegues_v2_bloques_blq75.csv"):
            self.assertTrue((self.r.salidas_v2 / nombre).exists(), nombre)
        lateral = rv.leer_json(self.r.salidas_v2 / pv.NOMBRE_LATERAL)
        self.assertEqual(lateral["huella_pliegues"], en_disco["huella_pliegues"])
        self.assertEqual(lateral["traza"]["insumos"]["manifiesto_pliegues"]["ruta"], "pliegues_v2.json")
        self.assertEqual(sorted(lateral["tablas"]), sorted(p.name for p in self.r.salidas_v2.glob("*.csv")))
        texto = self.r.manifiesto_pliegues.read_text(encoding="utf-8")
        self.assertNotIn(str(self.base), texto)                     # sin rutas absolutas
        self.assertNotIn(str(self.base), (self.r.salidas_v2 / pv.NOMBRE_LATERAL).read_text(encoding="utf-8"))
        self.assertEqual(en_disco["traza"]["insumos"]["panel_pm25"]["raiz"], "raiz_v1")
        huellas_tablas = {p.name: p.stat().st_mtime_ns for p in self.r.salidas_v2.iterdir()}

        # Otra vez con lo mismo: no se toca nada, tampoco las tablas.
        m2, estado2 = self.ejecutar()
        self.assertEqual(estado2, "sin_cambios")
        self.assertEqual(m2["fijado_utc"], en_disco["fijado_utc"])
        self.assertEqual({p.name: p.stat().st_mtime_ns for p in self.r.salidas_v2.iterdir()}, huellas_tablas)

        # Una anotación de la bitácora no cambia la huella.
        pv.anotar_bitacora({"evento": "recorte", "nota": "semillas sólo en LRO"}, self.r)
        anotado = rv.leer_json(self.r.manifiesto_pliegues)
        self.assertEqual(anotado["bitacora"][-1]["evento"], "recorte")
        self.assertEqual(pv.huella_pliegues(anotado), en_disco["huella_pliegues"])

        # Si cambia el panel, la huella cambia y no se reemplaza en silencio.
        self.escribir_panel("pm25", {"S1": {2000: 3}, "S2": {2005: 4}, "S3": {2024: 1}, "S4": {2015: 2}, "S5": {2016: 5}})
        with self.assertRaises(SystemExit):
            self.ejecutar()
        self.assertEqual(rv.leer_json(self.r.manifiesto_pliegues)["huella_pliegues"], en_disco["huella_pliegues"])
        sha_anterior = hashlib.sha256(self.r.manifiesto_pliegues.read_bytes()).hexdigest()
        m3, estado3 = self.ejecutar(reemplazar=True, motivo="Enmienda 1, punto 8")
        self.assertEqual(estado3, "reemplazado")
        # La bitácora nueva empieza con el reemplazo, que guarda la anterior entera; el respaldo conserva los bytes.
        self.assertEqual([e["evento"] for e in m3["bitacora"]], ["reemplazo", "fijado"])
        reemplazo = m3["bitacora"][0]
        self.assertEqual([e["evento"] for e in reemplazo["bitacora_anterior"]], ["fijado", "recorte"])
        self.assertEqual((reemplazo["huella_anterior"], reemplazo["motivo"]), (en_disco["huella_pliegues"], "Enmienda 1, punto 8"))
        respaldos = list(self.r.raiz_v2.glob("pliegues_v2_reemplazado_*.json"))
        self.assertEqual(len(respaldos), 1)
        self.assertEqual(rv.leer_json(respaldos[0])["huella_pliegues"], en_disco["huella_pliegues"])
        self.assertEqual(hashlib.sha256(respaldos[0].read_bytes()).hexdigest(), sha_anterior)
        self.assertEqual(reemplazo["respaldo"], {"raiz": "raiz_v2", "ruta": respaldos[0].name, "sha256": sha_anterior})
        self.assertEqual(m3["bitacora"][-1]["huella_pliegues"], m3["huella_pliegues"])

    def test_refijar_bajo_otro_contrato_sin_cambiar_los_pliegues(self):
        """--refijar: con la misma huella, el manifiesto se vuelve a fijar bajo el contrato vigente; el anterior queda
        como respaldo (mismos bytes y fechas) y la bitácora sigue, con los recortes anotados antes, y termina en un
        «fijado» que cita los dos contratos. Si los pliegues cambian, --refijar se niega."""
        import os
        with self.assertRaises(SystemExit):                              # no hay manifiesto que volver a fijar
            self.ejecutar(refijar=True)
        m1, _ = self.ejecutar()
        pv.anotar_bitacora({"evento": "recorte_presupuesto", "recorte": 2, "etiqueta": "principal",
                            "aplicados": ["a", "b"]}, self.r)
        antes = self.r.manifiesto_pliegues.read_bytes()
        mtime_antes = self.r.manifiesto_pliegues.stat().st_mtime_ns
        con_recorte = rv.leer_json(self.r.manifiesto_pliegues)
        # una enmienda cambia el contrato (y la configuración declara su sha256), no los pliegues
        contrato = self.r.contrato
        contrato.write_text(contrato.read_text(encoding="utf-8") + "\n### Enmienda de prueba\n", encoding="utf-8")
        sha_nuevo = hashlib.sha256(contrato.read_bytes()).hexdigest()
        cfg = json.loads(self.r.config.read_text(encoding="utf-8"))
        cfg["contrato"]["sha256"] = sha_nuevo
        self.r.config.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(SystemExit):
            self.ejecutar(reemplazar=True, refijar=True)
        m2, estado = self.ejecutar(refijar=True, motivo="contrato vigente")
        self.assertEqual(estado, "refijado")
        self.assertEqual(m2["huella_pliegues"], m1["huella_pliegues"])
        self.assertEqual(pv.huella_pliegues(m2), m1["huella_pliegues"])
        self.assertEqual([e["evento"] for e in m2["bitacora"]], ["fijado", "recorte_presupuesto", "fijado"])
        self.assertEqual(m2["bitacora"][:2], con_recorte["bitacora"])
        ev = m2["bitacora"][-1]
        self.assertEqual((ev["huella_pliegues"], ev["motivo"]), (m1["huella_pliegues"], "contrato vigente"))
        self.assertEqual(ev["refijado"]["contrato"], {"anterior": m1["traza"]["contrato"]["sha256"], "vigente": sha_nuevo})
        self.assertNotEqual(ev["refijado"]["contrato"]["anterior"], sha_nuevo)
        self.assertEqual(m2["traza"]["contrato"]["sha256"], sha_nuevo)
        self.assertEqual(m2["fijado_utc"], m1["fijado_utc"])
        self.assertIn("refijado_utc", m2)
        respaldo = self.r.raiz_v2 / ev["refijado"]["respaldo"]["ruta"]
        self.assertTrue(respaldo.name.startswith("pliegues_v2_reemplazado_"))
        self.assertEqual(respaldo.read_bytes(), antes)                   # el anterior, intacto
        self.assertEqual(ev["refijado"]["respaldo"]["sha256"], hashlib.sha256(antes).hexdigest())
        self.assertEqual(os.stat(respaldo).st_mtime_ns, mtime_antes)     # con sus fechas (como cp -p)
        self.assertEqual(rv.leer_json(self.r.manifiesto_pliegues), m2)
        # si los pliegues cambian, volver a fijar no sirve: hay que reemplazar (enmienda)
        self.escribir_panel("pm25", {"S1": {2000: 3}, "S2": {2005: 4}, "S3": {2024: 1}, "S4": {2015: 2}, "S5": {2016: 5}})
        en_disco = self.r.manifiesto_pliegues.read_bytes()
        with self.assertRaises(SystemExit):
            self.ejecutar(refijar=True)
        self.assertEqual(self.r.manifiesto_pliegues.read_bytes(), en_disco)
        self.assertEqual(len(list(self.r.raiz_v2.glob("pliegues_v2_reemplazado_*.json"))), 1)

    def test_no_escribir_no_crea_nada(self):
        m, estado = self.ejecutar(escribir=False)
        self.assertEqual(estado, "sin_escribir")
        self.assertFalse(self.r.raiz_v2.exists())
        self.assertFalse(self.r.salidas_v2.exists())

    def test_rechaza_un_panel_distinto_del_publicado(self):
        self.escribir_panel("no2", {"S1": {2019: 2}}, sha_declarado="f" * 64)
        with self.assertRaises(SystemExit):
            self.ejecutar(escribir=False)

    def test_rechaza_un_manifiesto_editado_a_mano(self):
        self.ejecutar()
        m = rv.leer_json(self.r.manifiesto_pliegues)
        editado = copy.deepcopy(m)
        editado["contaminantes"]["pm25"]["protocolos"]["LOSO-D"]["pliegues"][0]["excluidas"] = []
        self.r.manifiesto_pliegues.write_text(json.dumps(editado, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(SystemExit):
            self.ejecutar()
        with self.assertRaises(SystemExit):
            pv.anotar_bitacora({"evento": "x"}, self.r)

    def test_un_solo_contaminante_no_se_fija(self):
        with self.assertRaises(SystemExit):
            self.ejecutar(contaminantes=("pm25",))
        m, estado = self.ejecutar(escribir=False, contaminantes=("pm25",))
        self.assertEqual(list(m["contaminantes"]), ["pm25"])


if __name__ == "__main__":
    unittest.main()
