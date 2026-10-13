"""Pruebas de la factibilidad con predictores compilados (``factibilidad_v2``, Complemento de la Enmienda 1, punto 3),
con datos sintéticos pequeños y raíces temporales:

* las fechas se fijan por regla de calendario (2022-01-15, 2022-04-15 y 2022-07-15: verano, transición e invierno del
  año central del régimen 2019-2024) y el calendario 2000-2026 tiene 9.862 días;
* la regla: por contaminante, la media de los 3 días (cada uno, la mediana de sus repeticiones) × 9.862 días; se suman
  los dos contaminantes; factible si cuesta ≤ 5 veces LightGBM y ≤ 21 días de máquina (inclusivos); el promedio
  simple es la suma de sus miembros; LightGBM no es candidato; la marca es la misma en los dos contaminantes y el
  resumen se lee con ``correr_v2.factibilidad_de_archivo``;
* los predictores compilados reproducen a su motor con faltantes (lleaves; treelite → tl2cgen con el ``default_left``
  del RF tomado de ``missing_go_to_left``, que el importador de treelite ignora; la MLP en float32 por lotes) y se
  recargan desde sus archivos; la verificación de equivalencia detecta diferencias;
* el armado de las matrices con un módulo «produccion» falso: el capturador reemplaza al ``Modelo``, la ventana
  satelital se reinicia y se calienta con los 15 días previos de cada fecha, se detectan los predictores que la v1
  rellenaría con NaN y el módulo queda como estaba;
* la guardia de escritura del subproceso v1 (en un proceso aparte: el gancho de auditoría no se puede quitar);
* la medición registra sólo tiempos y rota el orden de los motores; la espera de la máquina libre;
* de punta a punta (sin la v1, con matrices sintéticas y la medición en su subproceso): sólo se escriben
  ``mediciones.json`` y ``factibilidad_produccion.json`` (con el candado ``factibilidad``), los artefactos del punto 11
  se respaldan con sufijo, el temporal desaparece y no hay métricas ni rutas absolutas.
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))
sys.path.insert(0, str(V2 / "tests"))
import _rutas_v2 as rv  # noqa: E402
import _sintetico_v2 as sx  # noqa: E402
import factibilidad_v2 as fv  # noqa: E402
import piloto_v2 as pl  # noqa: E402

pl.VENTANA_PROCESOS_S = 0.0
CFG_REAL = json.loads((V2 / rv.NOMBRE_CONFIG).read_text(encoding="utf-8"))
FEATS = list(sx.PREDICTORES)
FECHAS = {"verano": date(2022, 1, 15), "transicion": date(2022, 4, 15), "invierno": date(2022, 7, 15)}


def config_pequena(n_prod: int = 1500) -> dict:
    cfg = sx.config_pequena()
    cfg["decision"]["N_de_produccion"] = n_prod
    cfg["motores"]["eje_A"]["predictores"]["no2"] = list(FEATS)
    return cfg


PANEL = sx.panel_sintetico(dias=40)


def datos_con_faltantes(n: int = 3000, p: int = 8, semilla: int = 0):
    """Matriz con faltantes (y una columna vacía) y un blanco positivo."""
    rng = np.random.default_rng(semilla)
    X = rng.normal(size=(n, p)).astype("float32")
    X[rng.random((n, p)) < 0.25] = np.nan
    X[:, 3] = np.nan
    y = np.expm1(np.clip(2 + np.nan_to_num(X[:, 0]) + 0.8 * np.isnan(X[:, 1]) + rng.normal(0, 0.3, n), 0, 6))
    return X, y


# ---------------------------------------------------------------------------
# Fechas y calendario
# ---------------------------------------------------------------------------
class FechasTests(unittest.TestCase):
    def test_fechas_fijadas_por_calendario(self):
        self.assertEqual(fv.fechas_de_medicion(CFG_REAL), FECHAS)
        for nombre, f in FECHAS.items():
            self.assertEqual(fv.estacion_del_anio(f), nombre)

    def test_estaciones_del_hemisferio_sur(self):
        esperado = {1: "verano", 2: "verano", 3: "transicion", 4: "transicion", 5: "transicion", 6: "invierno",
                    7: "invierno", 8: "invierno", 9: "transicion", 10: "transicion", 11: "transicion", 12: "verano"}
        self.assertEqual({m: fv.estacion_del_anio(date(2022, m, 1)) for m in range(1, 13)}, esperado)

    def test_calendario(self):
        self.assertEqual(fv.dias_calendario(CFG_REAL["decision"]["factibilidad"]["periodo"]), 9862)
        self.assertEqual(fv.dias_entre(date(2024, 2, 28), date(2024, 3, 1)), 3)
        self.assertEqual(fv.fecha_central(date(2019, 1, 1), date(2024, 12, 31)), date(2022, 1, 1))
        with self.assertRaises(ValueError):
            fv.dias_entre(date(2020, 1, 2), date(2020, 1, 1))

    def test_sin_el_regimen_2019_2024(self):
        cfg = copy.deepcopy(CFG_REAL)
        crit = cfg["metricas"]["desagregaciones"]["regimen_de_predictores"]["criterio"]
        clave = "valor" if rv.estado_vigente(crit) == "ratificado" else "provisional"
        crit[clave] = [r for r in crit[clave] if r["id"] != "2019-2024"]
        with self.assertRaises(ValueError):
            fv.fechas_de_medicion(cfg)

    def test_nombre_de_la_matriz(self):
        self.assertEqual(fv.nombre_matriz("no2", date(2022, 4, 15)), "X_no2_20220415.npy")


# ---------------------------------------------------------------------------
# La regla
# ---------------------------------------------------------------------------
def fila(tarea, fase, s, rep=0, **extra):
    return {"tarea": tarea, "fase": fase, "segundos_pared": s, "segundos_cpu": 10 * s, "paralelismo": 10.0,
            "fraccion_maquina_otros": 0.05, "carga_1min_max": 3.0, "rss_pico_mb": 100.0, "repeticion": rep, **extra}


def entrada_sintetica(segundos: dict, factores_fecha=None) -> dict:
    """Mediciones inventadas: por motor y fecha, tres repeticiones (× 1,0, 1,1 y 0,9; la mediana es la central)."""
    factores_fecha = factores_fecha or {f: 1.0 for f in FECHAS}
    filas = []
    for motor, s in segundos.items():
        for fid, ff in factores_fecha.items():
            for rep, f in enumerate((1.0, 1.1, 0.9)):
                filas.append(fila(motor, "dia", s * ff * f, rep, fecha=fid, segundos_por_bloque=[s * ff * f / 24] * 24))
        filas.append(fila(motor, "ajuste", 10.0))
    return {"parametros": {"fechas": {k: v.isoformat() for k, v in FECHAS.items()}, "celdas": 838430, "horas": 24,
                           "N_de_produccion": 750000, "semilla_filas": [42], "epocas_mlp": 2, "repeticiones": 3,
                           "hilos_prediccion": 12, "hilos_ajuste": 8},
            "maquina_inicio": {"carga_media_1_5_15": [1, 1, 1]}, "maquina_fin": {}, "filas": filas}


def doc_sintetico(pm25: dict, no2: dict) -> dict:
    return {"schema": fv.SCHEMA_MEDICIONES, "contaminantes": {"pm25": entrada_sintetica(pm25), "no2": entrada_sintetica(no2)},
            "fechas": {"valores": {k: v.isoformat() for k, v in FECHAS.items()}}}


class ReglaTests(unittest.TestCase):
    def test_mediana_por_dia_y_media_de_los_dias(self):
        seg = {"lightgbm": 10.0, "xgboost": 20.0, "random_forest": 60.0, "mlp": 2.0}
        t = fv.tiempos_de(entrada_sintetica(seg, {"verano": 1.0, "transicion": 2.0, "invierno": 3.0}))
        self.assertAlmostEqual(t["xgboost"]["por_fecha_s"]["transicion"], 40.0)
        self.assertAlmostEqual(t["xgboost"]["segundos_por_dia"], 40.0)           # (20 + 40 + 60) / 3
        self.assertEqual(t["xgboost"]["repeticiones_s"]["verano"], [20.0, 22.0, 18.0])
        with self.assertRaises(ValueError):                                      # falta una fecha
            e = entrada_sintetica(seg)
            e["filas"] = [f for f in e["filas"] if not (f["tarea"] == "mlp" and f.get("fecha") == "invierno")]
            fv.tiempos_de(e)

    def test_suma_de_contaminantes_cociente_y_dias(self):
        pm = {"lightgbm": 10.0, "xgboost": 20.0, "random_forest": 60.0, "mlp": 2.0}
        no = {"lightgbm": 10.0, "xgboost": 20.0, "random_forest": 50.0, "mlp": 2.0}
        r = fv.aplicar_regla({"pm25": fv.tiempos_de(entrada_sintetica(pm)), "no2": fv.tiempos_de(entrada_sintetica(no))},
                             CFG_REAL)
        self.assertEqual(r["dias_calendario"], 9862)
        p = r["produccion"]
        self.assertAlmostEqual(p["lightgbm"]["segundos_2000_2026"], 20.0 * 9862)
        self.assertAlmostEqual(p["random_forest"]["cociente_frente_a_lightgbm"], 5.5)
        self.assertAlmostEqual(p["xgboost"]["dias_de_maquina"], round(40.0 * 9862 / 86400, 4))
        self.assertAlmostEqual(p[fv.PROMEDIO]["segundos_2000_2026"], (92.0 + 82.0) * 9862, places=1)   # suma de miembros
        self.assertAlmostEqual(p[fv.PROMEDIO]["cociente_frente_a_lightgbm"], 8.7)
        c = r["candidatos"]
        self.assertNotIn("lightgbm", c)                                          # la referencia no es candidato
        self.assertEqual({k: v["factible"] for k, v in c.items()},
                         {"xgboost": True, "random_forest": False, "mlp": True, fv.PROMEDIO: False})
        self.assertFalse(c["random_forest"]["cumple_factor"])
        self.assertTrue(c["random_forest"]["cumple_dias"])                       # 110 s × 9.862 días = 12,6 días
        self.assertIn("5.50 veces", c["random_forest"]["registro"])
        self.assertEqual(r["orden_por_costo"], ["mlp", "xgboost", "random_forest", fv.PROMEDIO])

    def test_umbral_de_dias(self):
        # un candidato barato frente a LightGBM pero caro en días: 130 s por día y contaminante → 29,7 días
        pm = {"lightgbm": 100.0, "xgboost": 130.0, "random_forest": 50.0, "mlp": 1.0}
        r = fv.aplicar_regla({"pm25": fv.tiempos_de(entrada_sintetica(pm)), "no2": fv.tiempos_de(entrada_sintetica(pm))},
                             CFG_REAL)
        x = r["candidatos"]["xgboost"]
        self.assertTrue(x["cumple_factor"])
        self.assertFalse(x["cumple_dias"])
        self.assertFalse(x["factible"])
        self.assertTrue(r["referencia_lightgbm"]["excede_el_umbral_de_dias"])    # 22,8 días: la regla no la excluye

    def test_umbrales_inclusivos(self):
        cfg = copy.deepcopy(CFG_REAL)
        s = 7.0
        cfg["decision"]["factibilidad"]["umbral_dias_de_maquina"] = (5 * s * 9862 + 5 * s * 9862) / 86400.0
        t = {"lightgbm": s, "xgboost": 5 * s, "random_forest": 5 * s + 0.001, "mlp": s}
        r = fv.aplicar_regla({"pm25": fv.tiempos_de(entrada_sintetica(t)), "no2": fv.tiempos_de(entrada_sintetica(t))}, cfg)
        self.assertTrue(r["candidatos"]["xgboost"]["factible"])                 # exactamente 5 veces y el umbral
        self.assertEqual(r["candidatos"]["xgboost"]["cociente_frente_a_lightgbm"], 5.0)
        self.assertFalse(r["candidatos"]["random_forest"]["factible"])          # apenas por encima

    def test_la_regla_exige_los_dos_contaminantes(self):
        pm = {"lightgbm": 10.0, "xgboost": 20.0, "random_forest": 60.0, "mlp": 2.0}
        with self.assertRaises(ValueError):
            fv.aplicar_regla({"pm25": fv.tiempos_de(entrada_sintetica(pm))}, CFG_REAL)

    def test_resumen_y_lectura_de_correr_v2(self):
        import correr_v2 as cr
        pm = {"lightgbm": 10.0, "xgboost": 20.0, "random_forest": 60.0, "mlp": 2.0}
        no = {"lightgbm": 12.0, "xgboost": 22.0, "random_forest": 70.0, "mlp": 2.5}
        res = fv.resumir(doc_sintetico(pm, no), CFG_REAL)
        self.assertEqual(fv.claves_prohibidas(res), [])
        self.assertEqual(res["resumen"]["no_factibles"], ["random_forest", fv.PROMEDIO])
        for p in ("pm25", "no2"):                                               # la marca es la de los dos juntos
            self.assertEqual({c: v["fuera_de_la_decision"] for c, v in res["contaminantes"][p]["candidatos"].items()},
                             {c: not v["factible"] for c, v in res["factibilidad"]["candidatos"].items()})
            self.assertEqual(res["contaminantes"][p]["dias_produccion"], 9862)
        self.assertAlmostEqual(res["contaminantes"]["no2"]["segundos_por_dia"][fv.PROMEDIO], 106.5)
        # lo que lee la decisión: la regla declarada (la del Complemento) y el veredicto conjunto por candidato
        self.assertEqual((res["regla"]["umbral_dias_de_maquina"], res["regla"]["factor_maximo_frente_a_lightgbm"],
                          res["regla"]["hilos"]), (21.0, 5.0, 12))
        self.assertEqual({c: v["factible"] for c, v in res["factibilidad"]["candidatos"].items()},
                         {"xgboost": True, "random_forest": False, "mlp": True, fv.PROMEDIO: False})
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / fv.NOMBRE_RESUMEN
            ruta.write_text(json.dumps(pl.sin_nan(res), ensure_ascii=False), encoding="utf-8")
            tiempos, fuente = cr.factibilidad_de_archivo(ruta, "pm25")
        self.assertAlmostEqual(tiempos["xgboost"]["segundos_por_dia"], 20.0)
        self.assertTrue(tiempos["random_forest"]["factibilidad_v2"]["fuera_de_la_decision"])
        self.assertEqual(fuente["schema"], fv.SCHEMA_RESUMEN)

    def test_avisos_de_carga_y_paralelismo(self):
        pm = {"lightgbm": 10.0, "xgboost": 20.0, "random_forest": 60.0, "mlp": 2.0}
        doc = doc_sintetico(pm, pm)
        for f in doc["contaminantes"]["no2"]["filas"]:
            if f["tarea"] == "mlp" and f["fase"] == "dia":
                f["paralelismo"] = 14.0
        doc["contaminantes"]["no2"]["espera_maquina_libre"] = {"libre": False, "umbral_carga_1min": 2.0, "espera_s": 1200.0,
                                                               "carga_1min": 5.4}
        res = fv.resumir(doc, CFG_REAL)
        self.assertEqual(res["contaminantes"]["no2"]["maquina"]["fraccion_maquina_otros_mediana"], 0.05)
        avisos = " | ".join(res["advertencias"])
        self.assertIn("no2: la carga media de 1 minuto no bajó de 2.0", avisos)
        self.assertIn("mediana de 5% de la máquina", avisos)
        self.assertIn("no2: mlp usó un paralelismo mediano de 14.0", avisos)
        self.assertNotIn("pm25: mlp", avisos)

    def test_claves_prohibidas(self):
        self.assertEqual(fv.claves_prohibidas({"a": {"r2": 1, "rmse_log": 2}, "b": [{"nmb": 3}], "maquina": 1}),
                         ["/a/r2", "/a/rmse_log", "/b[0]/nmb"])


# ---------------------------------------------------------------------------
# Predictores compilados
# ---------------------------------------------------------------------------
class CompiladosTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="factibilidad-compilados-")
        cls.carpeta = Path(cls.tmp.name).resolve() / "modelos"
        cls.cfg = config_pequena()
        cls.rec = fv.recetas_factibilidad(cls.cfg, 2, epocas_mlp=2)
        cls.X, cls.y = datos_con_faltantes()
        cls.modelos = {m: fv.ajustar_motor(fv.crear_motor(m, cls.rec), m, cls.X, cls.y) for m in fv.MOTORES}
        cls.compilados, cls.info = fv.compilar_motores(cls.modelos, cls.carpeta, 2, 2)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_equivalencia_con_faltantes(self):
        eq = fv.verificar_equivalencia(self.modelos, self.compilados, self.X, n=4000)
        self.assertEqual(eq["equivalentes"], {m: True for m in fv.MOTORES}, eq["dif_max_log1p"])
        self.assertLessEqual(eq["dif_max_log1p"]["lightgbm"], 1e-9)
        self.assertLessEqual(eq["dif_max_log1p"]["random_forest"], 1e-9)
        self.assertEqual(fv.claves_prohibidas(eq), [])

    def test_rf_con_la_rama_de_los_faltantes(self):
        """El importador de treelite deja default_left = 1; con missing_go_to_left el bosque compilado es el de
        scikit-learn también en las filas con NaN."""
        import treelite
        rf = self.modelos["random_forest"].modelo
        Z = fv.filas_sinteticas(self.X, 3000, semilla=[5], fraccion_nan=0.3)
        ref = rf.predict(Z)
        crudo = treelite.gtil.predict(treelite.sklearn.import_model(rf), Z.astype(np.float64)).reshape(-1)
        self.assertGreater(float(np.max(np.abs(crudo - ref))), 1e-6)            # sin corregir, difiere
        tm, extra = fv.treelite_de_rf(rf)
        self.assertGreater(extra["default_left_corregidos"], 0)
        np.testing.assert_allclose(treelite.gtil.predict(tm, Z.astype(np.float64)).reshape(-1), ref, rtol=0, atol=1e-9)
        np.testing.assert_allclose(self.compilados["random_forest"].predict(Z), ref, rtol=0, atol=1e-9)
        self.assertEqual(self.info["random_forest"]["default_left_corregidos"], extra["default_left_corregidos"])

    def test_mlp_float32_por_lotes(self):
        m = self.modelos["mlp"]
        Z = fv.filas_sinteticas(self.X, 501, semilla=[9])
        Z[:20] *= 1e4                                                            # fuera del rango: se recorta
        ref = m.predecir(Z)
        a = fv.MLPCompilada(fv.MLPCompilada.arreglos_de(m), hilos=1, lote=7)
        b = fv.MLPCompilada(fv.MLPCompilada.arreglos_de(m), hilos=3, lote=64)
        np.testing.assert_allclose(a.predict(Z), ref, rtol=0, atol=1e-4)
        np.testing.assert_allclose(b.predict(Z), ref, rtol=0, atol=1e-4)
        self.assertEqual(a.predict(Z).dtype, np.float32)
        self.assertTrue(np.asarray(fv.MLPCompilada.arreglos_de(m)["vacias"])[3])   # la columna vacía

    def test_recarga_desde_los_archivos(self):
        cargados = fv.cargar_compilados(self.carpeta, self.info, 2)
        Z = fv.filas_sinteticas(self.X, 800, semilla=[3])
        for motor in fv.MOTORES:
            with self.subTest(motor=motor):
                np.testing.assert_array_equal(np.asarray(cargados[motor].predict(Z)),
                                              np.asarray(self.compilados[motor].predict(Z)))
        self.assertEqual(self.info["lightgbm"]["biblioteca"], "lleaves")
        self.assertEqual(self.info["xgboost"]["umbral"], "float32")
        self.assertEqual(self.info["random_forest"]["umbral"], "float64")
        self.assertTrue((self.carpeta / self.info["xgboost"]["archivo"]).exists())
        self.assertFalse(any(self.carpeta.glob("*_c")))                         # el código C se borra

    def test_la_verificacion_detecta_diferencias(self):
        class Corrido:
            def __init__(self, base, delta):
                self.base, self.delta = base, delta

            def predict(self, X):
                return np.asarray(self.base.predict(X), dtype="float64") + self.delta

        class ConNaN(Corrido):
            def predict(self, X):
                z = super().predict(X)
                z[0] = np.nan
                return z

        malos = dict(self.compilados)
        malos["lightgbm"] = Corrido(self.compilados["lightgbm"], 1e-6)
        malos["mlp"] = ConNaN(self.compilados["mlp"], 0.0)
        eq = fv.verificar_equivalencia(self.modelos, malos, self.X, n=500)
        self.assertFalse(eq["equivalentes"]["lightgbm"])
        self.assertEqual(eq["dif_max_log1p"]["mlp"], float("inf"))
        self.assertTrue(eq["equivalentes"]["xgboost"])

    def test_filas_sinteticas(self):
        Z = fv.filas_sinteticas(self.X, 1000, semilla=[1], fraccion_nan=0.0)
        self.assertEqual(Z.shape, (1000, self.X.shape[1]))
        np.testing.assert_array_equal(Z, fv.filas_sinteticas(self.X, 1000, semilla=[1], fraccion_nan=0.0))
        filas_reales = {tuple(np.nan_to_num(x, nan=-9e9)) for x in self.X}
        self.assertLess(sum(tuple(np.nan_to_num(z, nan=-9e9)) in filas_reales for z in Z), 50)   # no son filas reales

    def test_unidades_de_compilacion(self):
        self.assertEqual(fv.unidades_de_compilacion(300, 11_000_000, 8), 300)    # un árbol hondo por unidad
        self.assertEqual(fv.unidades_de_compilacion(800, 200_000, 8), 10)
        self.assertEqual(fv.unidades_de_compilacion(800, 100_000, 8), 8)         # al menos una por hilo
        self.assertEqual(fv.unidades_de_compilacion(5, 10, 8), 5)
        self.assertEqual(fv.unidades_de_compilacion(1, 10, 1), 1)


# ---------------------------------------------------------------------------
# Armado de las matrices con un módulo «produccion» falso
# ---------------------------------------------------------------------------
CODIGO_PRODUCCION_FALSA = '''
import numpy as np, pandas as pd
from datetime import date
from types import SimpleNamespace

class Modelo:
    def __init__(self, pol, entorno):
        raise AssertionError("no se debe usar el Modelo de la v1")

def derivadas_horarias(df):
    df["deriv"] = (df["a"] * 2).astype("float32")
    return df

def hash_codigo():
    return "falso"

def entorno_desde_disco(sufijo=None):
    celdas = pd.DataFrame({"celda": np.arange(N_CELDAS), "macrozona_cod": np.zeros(N_CELDAS, "int8")})
    return SimpleNamespace(celdas=celdas, superficies_dir=None, modelos_dir=None, enlaces_sha256="e")

class Satelites:
    def __init__(self):
        self.pedidos, self.ultimo = [], None
        self.dias_sin_maiac, self.dias_sin_no2 = [], []
    def dia(self, fecha):
        if self.ultimo is not None and fecha <= self.ultimo:
            raise ValueError("los días deben pedirse en orden cronológico")
        self.ultimo = fecha
        self.pedidos.append(fecha)

class ContextoPrediccion:
    def __init__(self, pol, celdas, entorno):
        self.modelo = Modelo(pol, entorno)
        self.n, self.lat_e = len(celdas), np.zeros(3)
        self.satelites = Satelites()
        self.fuentes = SimpleNamespace(faltantes={("cams", "202201")})
        self.mz = celdas["macrozona_cod"].to_numpy()
        self.reinicios = 0
        REGISTRO.append(self)
    def reiniciar_ventana_satelital(self):
        self.reinicios += 1
        self.satelites = Satelites()
    def dia(self, fecha, forzar=False):
        self.satelites.dia(fecha)
        for h in range(HORAS_FALSAS):
            df = pd.DataFrame({"a": (np.arange(self.n) + 100 * h + fecha.toordinal() % 1000).astype("float32")})
            df = derivadas_horarias(df)
            df["hora_local"] = np.int8(h)
            df["obs_vec"], df["peso_vec"] = np.float32(1.0), np.float32(2.0)
            for c in self.modelo.features:
                if c not in df.columns:
                    df[c] = np.nan
            self.modelo.predecir(df[self.modelo.features].to_numpy(np.float32), np.full(self.n, h), self.mz)
        return None, True
'''


def produccion_falsa(n_celdas: int = 6, horas: int = 24):
    m = types.ModuleType("produccion_falsa")
    m.N_CELDAS, m.HORAS_FALSAS, m.REGISTRO = n_celdas, horas, []
    exec(CODIGO_PRODUCCION_FALSA, m.__dict__)
    return m


class ArmadoTests(unittest.TestCase):
    def encargo(self, tmp: Path, predictores=("a", "deriv", "hora_local", "obs_vec")) -> dict:
        return {"temporal": str(tmp), "contaminantes": ["pm25", "no2"], "fechas": {k: v.isoformat() for k, v in FECHAS.items()},
                "predictores": {"pm25": list(predictores), "no2": list(predictores)}, "calentamiento_dias": 15}

    def test_captura_calentamiento_y_restauracion(self):
        P = produccion_falsa()
        modelo, deriv = P.Modelo, P.derivadas_horarias
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            doc = fv.armar_matrices(P, tmp, self.encargo(tmp))
            self.assertIs(P.Modelo, modelo)                                      # el módulo queda como estaba
            self.assertIs(P.derivadas_horarias, deriv)
            self.assertEqual(set(doc["contaminantes"]), {"pm25", "no2"})
            ctx = P.REGISTRO[0]
            self.assertEqual(ctx.reinicios, 3)
            # cada fecha: los 15 días previos en orden y la fecha (la última ventana es la de invierno)
            f = FECHAS["invierno"]
            self.assertEqual(ctx.satelites.pedidos, [f - timedelta(days=k) for k in range(15, 0, -1)] + [f])
            for fid, fecha in FECHAS.items():
                info = doc["contaminantes"]["pm25"]["fechas"][fid]
                X = np.load(tmp / info["archivo"])
                self.assertEqual(X.shape, (24, 6, 4))
                self.assertEqual(info["forma"], [24, 6, 4])
                h = 7
                a = (np.arange(6) + 100 * h + fecha.toordinal() % 1000).astype("float32")
                np.testing.assert_array_equal(X[h, :, 0], a)
                np.testing.assert_array_equal(X[h, :, 1], 2 * a)
                np.testing.assert_array_equal(X[h, :, 2], np.float32(h))
                self.assertEqual(info["columnas_rellenadas_con_nan_por_la_v1"], [])
                self.assertEqual(info["meses_sin_fuente"], ["cams:202201"])
            self.assertEqual(doc["contaminantes"]["no2"]["celdas"], 6)

    def test_predictor_que_la_v1_rellena_con_nan(self):
        P = produccion_falsa()
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            doc = fv.armar_matrices(P, tmp, self.encargo(tmp, ("a", "no_existe", "peso_vec")))
            info = doc["contaminantes"]["pm25"]["fechas"]["verano"]
            self.assertEqual(info["columnas_rellenadas_con_nan_por_la_v1"], ["no_existe"])
            self.assertEqual(info["columnas_sin_dato"], ["no_existe"])
            self.assertEqual(info["fraccion_nan_por_columna"]["a"], 0.0)

    def test_reutilizar_matrices_ya_armadas(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            self.assertIsNone(fv.matrices_existentes(base, ["pm25"], FECHAS))
            doc = armar_sintetico(None, config_pequena(), ["pm25"], FECHAS, base, 2, n_celdas=3)
            (base / fv.NOMBRE_MATRICES).write_text(json.dumps(doc), encoding="utf-8")
            self.assertTrue(fv.matrices_existentes(base, ["pm25"], FECHAS)["reutilizadas"])
            self.assertIsNone(fv.matrices_existentes(base, ["pm25", "no2"], FECHAS))      # falta un contaminante
            self.assertIsNone(fv.matrices_existentes(base, ["pm25"], dict(FECHAS, verano=date(2022, 1, 16))))
            (base / fv.nombre_matriz("pm25", FECHAS["verano"])).unlink()
            self.assertIsNone(fv.matrices_existentes(base, ["pm25"], FECHAS))             # falta un archivo

    def test_horas_incompletas(self):
        P = produccion_falsa(horas=23)
        modelo = P.Modelo
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):
                fv.armar_matrices(P, Path(d), self.encargo(Path(d)))
        self.assertIs(P.Modelo, modelo)


# ---------------------------------------------------------------------------
# Guardia de escritura del subproceso v1
# ---------------------------------------------------------------------------
PRUEBA_GUARDIA = r'''
import json, os, subprocess, sys
sys.path.insert(0, sys.argv[1])
import factibilidad_v2 as fv
permitida, prohibida = sys.argv[2], sys.argv[3]
fv.instalar_guardia_escritura([permitida])
out = {}
def intento(nombre, f):
    try:
        f()
        out[nombre] = "ok"
    except PermissionError:
        out[nombre] = "rechazado"
intento("escribir_dentro", lambda: open(os.path.join(permitida, "a.txt"), "w").write("x"))
intento("escribir_fuera", lambda: open(os.path.join(prohibida, "a.txt"), "w").write("x"))
intento("abrir_os_fuera", lambda: os.close(os.open(os.path.join(prohibida, "b.bin"), os.O_WRONLY | os.O_CREAT)))
intento("mkdir_fuera", lambda: os.mkdir(os.path.join(prohibida, "sub")))
intento("replace_hacia_fuera", lambda: os.replace(os.path.join(permitida, "a.txt"), os.path.join(prohibida, "c.txt")))
intento("leer_fuera", lambda: open(os.path.join(prohibida, "leer.txt")).read())
intento("relativa_con_punto_punto", lambda: open(os.path.join(permitida, "..", "prohibida", "d.txt"), "w"))
intento("proceso", lambda: subprocess.run(["true"]))
intento("devnull", lambda: open(os.devnull, "w").write("x"))
print(json.dumps(out))
'''


class GuardiaTests(unittest.TestCase):
    def test_guardia_en_un_proceso_aparte(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d).resolve()
            (base / "permitida").mkdir()
            (base / "prohibida").mkdir()
            (base / "prohibida" / "leer.txt").write_text("hola", encoding="utf-8")
            res = subprocess.run([sys.executable, "-B", "-c", PRUEBA_GUARDIA, str(V2), str(base / "permitida"),
                                  str(base / "prohibida")], capture_output=True, text=True, timeout=300,
                                 env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            self.assertEqual(res.returncode, 0, res.stderr[-2000:])
            out = json.loads(res.stdout.strip().splitlines()[-1])
            self.assertEqual(out, {"escribir_dentro": "ok", "escribir_fuera": "rechazado", "abrir_os_fuera": "rechazado",
                                   "mkdir_fuera": "rechazado", "replace_hacia_fuera": "rechazado", "leer_fuera": "ok",
                                   "relativa_con_punto_punto": "rechazado", "proceso": "rechazado", "devnull": "ok"})
            self.assertEqual(sorted(p.name for p in (base / "prohibida").iterdir()), ["leer.txt"])

    def test_ruta_permitida(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = os.path.realpath(d)
            self.assertTrue(fv.ruta_permitida(os.path.join(raiz, "x", "y.npy"), (raiz,)))
            self.assertFalse(fv.ruta_permitida(raiz + "_otro/x", (raiz,)))         # prefijo de texto, otra carpeta
            self.assertTrue(fv.ruta_permitida(5, (raiz,)))                         # descriptor ya abierto
            self.assertFalse(fv.ruta_permitida("relativa.txt", (raiz,), dir_fd=3))
            self.assertTrue(fv.ruta_permitida(os.devnull, (raiz,)))
            self.assertTrue(fv.ruta_permitida(os.fsencode(os.path.join(raiz, "b")), (raiz,)))


# ---------------------------------------------------------------------------
# Medición
# ---------------------------------------------------------------------------
class FalsoPredictor:
    def __init__(self, nombre, registro):
        self.nombre, self.registro = nombre, registro

    def predict(self, X):
        self.registro.append(self.nombre)
        return np.zeros(len(X))


class MedicionTests(unittest.TestCase):
    def test_dia_rota_el_orden_y_solo_registra_tiempos(self):
        llamadas = []
        pred = {m: FalsoPredictor(m, llamadas) for m in fv.MOTORES}
        bloques = np.zeros((5, 7, 3), np.float32)
        with pl.Medidor(intervalo_s=0.05) as med:
            fv.medir_dia(pred, bloques, med, "pm25", "verano", 3, 12)
        dia = [f for f in med.filas if f["fase"] == "dia"]
        self.assertEqual(len(dia), 12)
        self.assertEqual([f["tarea"] for f in dia[:4]], list(fv.MOTORES))
        self.assertEqual([f["tarea"] for f in dia[4:8]], fv.rotar(fv.MOTORES, 1))
        self.assertTrue(all(len(f["segundos_por_bloque"]) == 5 and f["filas"] == 35 and f["hilos"] == 12
                            and f["fecha"] == "verano" for f in dia))
        self.assertEqual(len(llamadas), 3 * 4 * 5)
        for f in med.filas:
            self.assertEqual(fv.claves_prohibidas(f), [])
            self.assertIn("carga_1min_max", f)
            self.assertIn("fraccion_maquina_otros", f)

    def test_predecir_comprueba_el_largo(self):
        class Malo:
            def predict(self, X):
                return np.zeros(len(X) - 1)
        with self.assertRaises(RuntimeError):
            fv.predecir_comprobando(Malo(), np.zeros((5, 2), np.float32))

    def test_espera_de_la_maquina_libre(self):
        cargas, reloj = iter([5.0, 3.0, 1.5]), {"t": 0.0}

        def dormir(s):
            reloj["t"] += s
        r = fv.esperar_maquina_libre(2.0, 600, 30, carga=lambda: (next(cargas), 0, 0), reloj=lambda: reloj["t"],
                                     dormir=dormir)
        self.assertEqual((r["libre"], r["espera_s"], r["muestras"]), (True, 60.0, 3))
        reloj["t"] = 0.0
        r = fv.esperar_maquina_libre(2.0, 60, 30, carga=lambda: (5.0, 0, 0), reloj=lambda: reloj["t"], dormir=dormir)
        self.assertEqual((r["libre"], r["muestras"]), (False, 3))
        self.assertIn("se midió igual", r["nota"])

    def test_cargar_matriz(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "X.npy"
            np.save(ruta, np.zeros((24, 5, 3), np.float32))
            self.assertEqual(fv.cargar_matriz(ruta, [24, 5, 3]).shape, (24, 5, 3))
            with self.assertRaises(RuntimeError):
                fv.cargar_matriz(ruta, [24, 5, 4])


# ---------------------------------------------------------------------------
# De punta a punta
# ---------------------------------------------------------------------------
def armar_sintetico(r, cfg, contaminantes, fechas, temporal, hilos, n_celdas: int = 40):
    """Sustituto del subproceso v1: matrices sintéticas con la forma real del encargo (24 × celdas × predictores)."""
    salida = {"schema": fv.SCHEMA_MATRICES, "creado_utc": "2026-10-13T00:00:00Z", "contaminantes": {},
              "guardia": {"escritura_permitida": ["temporal"]}, "entorno_v1": {"AIR_POLLUTION_MODELO_1KM_ROOT": "raiz_v1"}}
    for k, pol in enumerate(contaminantes):
        feats = cfg["motores"]["eje_A"]["predictores"][pol]
        X = PANEL[feats].to_numpy(np.float32)
        por = {"celdas": n_celdas, "estaciones": 9, "contexto_s": 0.1, "fechas": {}}
        for j, (fid, f) in enumerate(sorted(fechas.items(), key=lambda kv: kv[1])):
            Z = fv.filas_sinteticas(X, 24 * n_celdas, semilla=[k, j]).reshape(24, n_celdas, len(feats))
            np.save(temporal / fv.nombre_matriz(pol, f), Z)
            por["fechas"][fid] = {"archivo": fv.nombre_matriz(pol, f), "forma": list(Z.shape), "fecha": f.isoformat(),
                                  "fraccion_nan_por_columna": {c: 0.05 for c in feats}, "columnas_sin_dato": [],
                                  "columnas_rellenadas_con_nan_por_la_v1": [], "infinitos": 0}
        salida["contaminantes"][pol] = por
    return salida


class PuntaAPuntaTests(unittest.TestCase):
    def test_mide_publica_respalda_y_no_deja_nada(self):
        import correr_v2 as cr
        import sklearn.metrics
        cfg = config_pequena()
        with sx.raices_temporales() as r, tempfile.TemporaryDirectory(prefix="factibilidad-temporal-") as d:
            (r.raiz_v1 / "paneles").mkdir(parents=True, exist_ok=True)
            for pol in ("pm25", "no2"):
                PANEL.to_parquet(r.panel(pol), index=False)
            with rv.candado_escritura(fv.CANDADO, r):                          # artefactos de la medición del punto 11
                rv.publicar_json({"schema": fv.SCHEMAS_PUNTO_11[0], "contaminantes": {}}, fv.ruta_mediciones(r), r)
                rv.publicar_json({"schema": fv.SCHEMAS_PUNTO_11[1]}, fv.ruta_resumen(r), r)
            base = Path(r.raiz_v1).parent
            antes = {p for p in base.rglob("*") if p.is_file()}
            temporal = Path(d) / "medicion"
            prohibido = mock.Mock(side_effect=AssertionError("se calculó un R²"))
            with mock.patch.object(sklearn.metrics, "r2_score", prohibido):
                doc = fv.medir(r, cfg, ["pm25", "no2"], hilos_ajuste=2, hilos_prediccion=2, repeticiones=2,
                               temporal=temporal, armar=armar_sintetico, esperar=False, medir_en_subproceso=True,
                               epocas_mlp=1)
            prohibido.assert_not_called()
            self.assertFalse(temporal.exists())                                 # modelos y matrices descartados
            e = doc["contaminantes"]["pm25"]
            self.assertEqual(e["parametros"]["fechas"], {k: v.isoformat() for k, v in FECHAS.items()})
            self.assertEqual(e["subproceso_prediccion"]["orden"], "medir-prediccion")
            self.assertTrue(all(e["equivalencia"]["equivalentes"].values()))
            f = pd.DataFrame(e["filas"])
            self.assertEqual(len(f[f["fase"] == "ajuste"]), 4)
            self.assertEqual(len(f[f["fase"] == "compilacion"]), 4)
            self.assertEqual(len(f[f["fase"] == "dia"]), 4 * 3 * 2)
            self.assertTrue((f[f["fase"] == "dia"]["hilos"] == 2).all())
            self.assertEqual(fv.claves_prohibidas(doc), [])
            res = fv.publicar(r, cfg)
            self.assertEqual(set(res["factibilidad"]["candidatos"]), set(cfg["decision"]["candidatos"]))
            self.assertEqual(res["publicacion"]["mediciones"]["sha256"], rv._sha256_archivo(fv.ruta_mediciones(r)))
            self.assertIn("respaldo_punto_11", res["publicacion"])
            tiempos, _ = cr.factibilidad_de_archivo(fv.ruta_resumen(r), "no2")
            self.assertEqual(set(tiempos), {*fv.MOTORES, fv.PROMEDIO})
            # los nombres vigentes ya existían (los del punto 11); lo único nuevo son sus dos respaldos
            despues = {p for p in base.rglob("*") if p.is_file()}
            nuevos = sorted(despues - antes)
            self.assertEqual(sorted(antes - despues), [])
            self.assertEqual(sorted(p.parent.name for p in nuevos), ["factibilidad", "modelo_1km_v2"])
            self.assertTrue(all(p.name.startswith(("mediciones_reemplazado_", "factibilidad_produccion_reemplazado_"))
                                for p in nuevos), nuevos)
            self.assertEqual(sorted(rv.leer_json(p)["schema"] for p in nuevos), sorted(fv.SCHEMAS_PUNTO_11))
            self.assertTrue(fv.ruta_mediciones(r).exists() and fv.ruta_resumen(r).exists())
            self.assertEqual(rv.leer_json(fv.ruta_resumen(r))["schema"], fv.SCHEMA_RESUMEN)
            self.assertEqual(rv.leer_json(fv.ruta_mediciones(r))["schema"], fv.SCHEMA_MEDICIONES)
            for p in despues:
                self.assertFalse(p.suffix in (".dylib", ".o", ".npy", ".npz", ".c"), p)
            for ruta in (fv.ruta_mediciones(r), fv.ruta_resumen(r)):
                texto = ruta.read_text(encoding="utf-8")
                self.assertNotIn(str(base), texto)                              # sin rutas absolutas
                self.assertNotIn(str(Path(d).resolve()), texto)
                self.assertNotIn(str(Path.home()), texto)
                self.assertEqual(fv.claves_prohibidas(json.loads(texto)), [])

    def test_artefactos_con_el_candado_de_factibilidad(self):
        with sx.raices_temporales() as r:
            for ruta in (fv.ruta_mediciones(r), fv.ruta_resumen(r),
                         fv.ruta_resumen(r).with_name("factibilidad_produccion_reemplazado_20261013T000000Z.json"),
                         fv.ruta_mediciones(r).with_name("mediciones_reemplazado_20261013T000000Z.json")):
                self.assertEqual(rv.candado_de(ruta, r), "factibilidad")
            with self.assertRaises(rv.EscrituraNoPermitida):                    # sin el candado no se escribe
                rv.publicar_json({}, fv.ruta_resumen(r), r)

    def test_publicar_rechaza_un_resumen_con_metricas(self):
        with sx.raices_temporales() as r:
            with mock.patch.object(fv, "leer_mediciones", return_value={}), \
                    mock.patch.object(fv, "resumir", return_value={"contaminantes": {"pm25": {"r2": 0.5}}}):
                with self.assertRaises(RuntimeError):
                    fv.publicar(r, CFG_REAL)
            self.assertFalse(fv.ruta_resumen(r).exists())

    def test_mediciones_del_punto_11_y_esquema_desconocido(self):
        with sx.raices_temporales() as r:
            with rv.candado_escritura(fv.CANDADO, r):
                rv.publicar_json({"schema": fv.SCHEMAS_PUNTO_11[0], "contaminantes": {"pm25": {}}}, fv.ruta_mediciones(r), r)
            self.assertEqual(fv.leer_mediciones(r)["contaminantes"], {})        # no cuentan para la regla nueva
            with rv.candado_escritura(fv.CANDADO, r):
                rv.publicar_json({"schema": "otro"}, fv.ruta_mediciones(r), r)
            with self.assertRaises(SystemExit):
                fv.leer_mediciones(r)


if __name__ == "__main__":
    unittest.main()
