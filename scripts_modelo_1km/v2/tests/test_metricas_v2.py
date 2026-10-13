"""Pruebas de ``metricas_v2`` con datos sintéticos: fórmulas (con y sin pesos), pares comunes y de la decisión, día
civil con horario de verano frente a UTC−4, mínimos de horas, días y meses contra una referencia en pandas,
desagregaciones (cinco regímenes, régimen fila a fila y períodos de LPO con 2024 aparte), pesos fijos por estación y
de desagrupamiento, números efectivos (Kish y G), conjuntos de evaluación E1, E2, E2-SINCA y E1′ (E1′ separa la
composición de la calidad), evaluabilidad de E2 y cuantiles."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))
import metricas_v2 as mt  # noqa: E402

CFG = json.loads((V2 / "config_v2.json").read_text(encoding="utf-8"))


def directas(o, p, w=None):
    o, p = np.asarray(o, float), np.asarray(p, float)
    w = np.ones_like(o) if w is None else np.asarray(w, float)
    mo = np.sum(w * o) / w.sum()
    mp = np.sum(w * p) / w.sum()
    sse = np.sum(w * (p - o) ** 2)
    sst = np.sum(w * (o - mo) ** 2)
    cov = np.sum(w * (o - mo) * (p - mp)) / w.sum()
    return {"r2": 1 - sse / sst, "rmse": np.sqrt(sse / w.sum()), "mae": np.sum(w * np.abs(p - o)) / w.sum(),
            "nmb": np.sum(w * (p - o)) / np.sum(w * o), "sesgo": np.sum(w * (p - o)) / w.sum(),
            "r": cov / np.sqrt((np.sum(w * (o - mo) ** 2) / w.sum()) * (np.sum(w * (p - mp) ** 2) / w.sum())),
            "media_obs": mo, "media_pred": mp}


def kish(ids, w):
    t = pd.Series(np.asarray(w, float)).groupby(np.asarray(ids)).sum().to_numpy()
    t = t[t > 0]
    return t.sum() ** 2 / (t ** 2).sum()


def base_simple(n=3000, semilla=2, **kw):
    """Nivel horario sintético: tres estaciones (dos macrozonas), años 2018 y 2020, pob_dens fija por estación."""
    rng = np.random.default_rng(semilla)
    o = rng.gamma(2, 10, n)
    p = {"a": o * np.exp(rng.normal(0, .3, n)), "b": o + rng.normal(0, 5, n)}
    z = {"a": np.log1p(o) + rng.normal(0, .3, n), "b": None}
    est = rng.integers(0, 3, n)
    d = dict(o=o, p=p, z=z, est=est, mz=np.where(est < 2, 2, 3), anio=np.where(np.arange(n) < 1000, 2018, 2020),
             pv=rng.uniform(0, 5, n), dist=np.choose(est, [1.0, 10.0, 30.0]), pob=np.choose(est, [100.0, 2000.0, 50.0]))
    d["base"] = mt.nivel_horario(d["o"], d["p"], d["z"], d["est"], d["mz"], d["anio"], d["pv"], d["dist"], d["pob"],
                                 np.zeros(n, dtype=int), **kw)
    return d


class FormulasTests(unittest.TestCase):
    def test_metricas_igual_a_las_formulas(self):
        rng = np.random.default_rng(0)
        o = rng.gamma(2, 10, 5000)
        p = o * np.exp(rng.normal(0, 0.3, 5000)) + 2
        w = rng.uniform(0, 5, 5000)
        for pesos in (None, w):
            d, ref = mt.metricas(o, p, pesos), directas(o, p, pesos)
            for k, v in ref.items():
                self.assertAlmostEqual(d[k], v, places=9, msg=k)
        self.assertEqual(mt.metricas(o, p)["n"], 5000)

    def test_casos_borde(self):
        self.assertTrue(np.isnan(mt.metricas([1.0, 2.0], [1.0, 2.0])["r2"]))           # n < 3
        self.assertTrue(np.isnan(mt.metricas([3.0, 3.0, 3.0], [1.0, 2.0, 3.0])["r2"]))  # SST = 0
        d = mt.metricas([1.0, np.nan, 3.0, 4.0], [1.0, 2.0, np.nan, 5.0])
        self.assertEqual(d["n"], 2)

    def test_pares_comunes(self):
        obs = np.array([1.0, 2.0, np.nan, 4.0, 5.0])
        preds = {"a": np.array([1.0, np.nan, 3.0, 4.0, 5.0]), "b": np.array([1.0, 2.0, 3.0, np.inf, 5.0])}
        m, info = mt.pares_comunes(obs, preds)
        np.testing.assert_array_equal(m, [True, False, False, False, True])
        self.assertEqual(info["no_finitas_por_motor"], {"a": 1, "b": 1})
        self.assertEqual((info["obs_no_finita"], info["pares_comunes"]), (1, 2))
        with self.assertRaises(ValueError):
            mt.pares_comunes(obs, {"c": np.ones(3)})

    def test_pares_de_la_decision_y_lo_que_quita_cada_familia(self):
        obs = np.arange(1.0, 9.0)
        nan = np.nan
        preds = {"lightgbm": np.array([1, 1, 1, 1, 1, 1, 1, nan]), "xgboost": np.ones(8),
                 "gp": np.array([nan, 1, 1, 1, 1, 1, 1, 1]), "idw": np.array([1, nan, nan, 1, 1, 1, 1, 1]),
                 "huber": np.array([1, 1, 1, nan, 1, 1, 1, 1])}
        m, info = mt.pares_comunes(obs, preds, motores=["lightgbm", "xgboost"],
                                   familias={"eje_B": ["gp", "idw"], "perdidas": ["huber"]})
        np.testing.assert_array_equal(m, [True] * 7 + [False])
        self.assertEqual(info["pares_comunes"], 7)
        self.assertEqual(info["quita_por_familia"], {"eje_B": 3, "perdidas": 1})
        _, info = mt.pares_comunes(obs, preds, motores=["lightgbm", "xgboost"])
        self.assertEqual(info["quita_por_familia"], {"gp": 1, "idw": 2, "huber": 1})
        with self.assertRaises(ValueError):
            mt.pares_comunes(obs, preds, motores=["mlp"])


class DiasTests(unittest.TestCase):
    def test_dia_civil_con_horario_de_verano_y_utc4(self):
        ts = pd.to_datetime(["2020-01-15 03:00:00", "2020-07-15 03:00:00", "2020-01-15 02:59:59"],
                            format="ISO8601").to_numpy("datetime64[ns]")
        civil = pd.to_datetime(mt.dia_civil(ts) * mt.NS_DIA)
        utc4 = pd.to_datetime(mt.dia_utc4(ts) * mt.NS_DIA)
        # enero (verano, UTC−3): 03:00 UTC es 00:00 del 15 en Santiago y 23:00 del 14 en UTC−4
        self.assertEqual(str(civil[0].date()), "2020-01-15")
        self.assertEqual(str(utc4[0].date()), "2020-01-14")
        # julio (invierno, UTC−4): los dos relojes coinciden
        self.assertEqual(str(civil[1].date()), "2020-07-14")
        self.assertEqual(str(utc4[1].date()), "2020-07-14")
        self.assertEqual(str(civil[2].date()), "2020-01-14")

    def test_dias_civiles_de_23_y_25_horas(self):
        horas = pd.date_range("2020-03-20", "2020-09-20", freq="h").to_numpy("datetime64[ns]")
        civil = pd.Series(mt.dia_civil(horas)).value_counts()
        zona = ZoneInfo("America/Santiago")
        ref = pd.Series([pd.Timestamp(h).tz_localize("UTC").tz_convert(zona).date() for h in horas]).value_counts()
        ref.index = [(pd.Timestamp(d) - pd.Timestamp("1970-01-01")).days for d in ref.index]
        comunes = sorted(set(civil.index) & set(ref.index))[1:-1]                        # sin los extremos parciales
        self.assertTrue(all(civil[c] == ref[c] for c in comunes))
        self.assertEqual(sorted(set(civil[comunes].tolist())), [23, 24, 25])             # los dos cambios de hora


def referencia_niveles(df: pd.DataFrame, minimo_h=18, minimo_d=20, minimo_m=9):
    """Referencia directa con pandas y zoneinfo: día civil, ≥ 18 h; mes del día civil, ≥ 20 días; año, ≥ 9 meses."""
    d = df.copy()
    loc = d["ts"].dt.tz_localize("UTC").dt.tz_convert(ZoneInfo("America/Santiago"))
    d["dia"] = loc.dt.tz_localize(None).dt.normalize()
    dia = d.groupby(["est", "dia"]).agg(o=("o", "mean"), p=("p", "mean"), n=("o", "size")).reset_index()
    dia = dia[dia["n"] >= minimo_h]
    dia["mes"] = dia["dia"].dt.to_period("M")
    mes = dia.groupby(["est", "mes"]).agg(o=("o", "mean"), p=("p", "mean"), n=("o", "size")).reset_index()
    mes = mes[mes["n"] >= minimo_d]
    mes["anio"] = mes["mes"].dt.year
    anio = mes.groupby(["est", "anio"]).agg(o=("o", "mean"), p=("p", "mean"), n=("o", "size")).reset_index()
    anio = anio[anio["n"] >= minimo_m]
    return dia, mes, anio


class NivelesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng = np.random.default_rng(1)
        ts = pd.date_range("2019-01-01 04:00", "2020-02-01 03:00", freq="h")
        filas = []
        for est in (0, 1, 2):
            o = rng.gamma(3, 8, len(ts))
            keep = rng.random(len(ts)) > 0.12                       # huecos al azar: días con < 18 h
            if est == 1:
                local = ts - pd.Timedelta(hours=4)
                keep &= ~((local.month == 4) & (local.day <= 12))   # abril con < 20 días válidos
            if est == 2:
                local = ts - pd.Timedelta(hours=4)
                keep &= local.month.isin([1, 2, 3, 5, 6, 7, 8, 9, 10]) | (local.year == 2020)
                keep &= ~((local.month == 5) & (local.day <= 15))   # mayo cae: 8 meses en 2019 → año fuera
            filas.append(pd.DataFrame({"est": est, "ts": ts[keep], "o": o[keep],
                                       "p": o[keep] * np.exp(rng.normal(0, 0.2, keep.sum()))}))
        cls.df = pd.concat(filas, ignore_index=True)
        d = cls.df
        n = len(d)
        anio = (d["ts"] - pd.Timedelta(hours=4)).dt.year.to_numpy()
        cls.pob = np.where(anio == 2019, 10.0, 30.0) * (1 + d["est"].to_numpy())     # cambia con el año (ráster)
        cls.regimen = d["ts"].dt.hour.to_numpy() % 2              # estrato horario: con los huecos, cambia de día en día
        base = mt.nivel_horario(d["o"].to_numpy(), {"m": d["p"].to_numpy()}, {"m": None}, d["est"].to_numpy(),
                                np.full(n, 2), anio, np.ones(n), np.ones(n), cls.pob, np.zeros(n, dtype=int),
                                bloque=np.where(d["est"].to_numpy() == 2, "E1", "E0"),
                                pesos_extra={"desagrupamiento": np.choose(d["est"].to_numpy(), [5.0, 6.0, 7.0])},
                                estratos={"regimen_fila_a_fila": (cls.regimen, ["x", "y"])})
        cls.nvs = mt.niveles(base, d["ts"].to_numpy("datetime64[ns]"))

    def test_diario_mensual_y_anual_contra_la_referencia(self):
        dia, mes, anio = referencia_niveles(self.df)
        for nombre, ref in (("diario_civil", dia), ("mensual", mes), ("anual", anio)):
            nv = self.nvs[nombre]
            with self.subTest(nivel=nombre):
                self.assertEqual(len(nv.obs), len(ref))
                np.testing.assert_allclose(np.sort(nv.obs), np.sort(ref["o"].to_numpy()), rtol=1e-12)
                np.testing.assert_allclose(np.sort(nv.pred["m"]), np.sort(ref["p"].to_numpy()), rtol=1e-12)
        self.assertFalse(((mes["est"] == 1) & (mes["mes"].astype(str) == "2019-04")).any())
        self.assertFalse(((anio["est"] == 2) & (anio["anio"] == 2019)).any())
        self.assertTrue(((anio["est"] == 0) & (anio["anio"] == 2019)).any())

    def test_diario_utc4_es_la_fecha_local_de_la_v1(self):
        d = self.df.copy()
        d["dia"] = (d["ts"] - pd.Timedelta(hours=4)).dt.normalize()
        g = d.groupby(["est", "dia"]).agg(o=("o", "mean"), n=("o", "size"))
        g = g[g["n"] >= 18]
        np.testing.assert_allclose(np.sort(self.nvs["diario_utc4"].obs), np.sort(g["o"].to_numpy()), rtol=1e-12)
        self.assertNotEqual(len(self.nvs["diario_utc4"].obs), 0)

    def test_unidades_y_grupo_mayoritario(self):
        self.assertTrue((self.nvs["diario_civil"].unidades >= 18).all())
        self.assertTrue((self.nvs["mensual"].unidades >= 20).all())
        self.assertTrue((self.nvs["anual"].unidades >= 9).all())
        agg = np.array([0, 0, 0, 1, 1, 2])
        grupo = np.array([3, 1, 3, 2, 5, 4])
        np.testing.assert_array_equal(mt._grupo_mayoritario(agg, grupo, 3), [3, 2, 4])   # empate 2–5: el menor

    def test_los_niveles_agregados_heredan_el_peso_fijo_el_bloque_y_los_estratos(self):
        # peso fijo: mediana de los años de la estación (2019 y 2020) = 20·(1 + est), igual en todos los niveles
        for nombre, nv in self.nvs.items():
            with self.subTest(nivel=nombre):
                np.testing.assert_array_equal(nv.poblacion, 20.0 * (1 + nv.estacion))
                np.testing.assert_array_equal(nv.pesos_extra["desagrupamiento"], np.choose(nv.estacion, [5.0, 6.0, 7.0]))
                np.testing.assert_array_equal(nv.bloque, (nv.estacion == 2).astype(int))
                self.assertEqual(nv.etiquetas["bloque"], ["E0", "E1"])
                self.assertEqual(nv.etiquetas["regimen_fila_a_fila"], ["x", "y"])
        # estrato del día civil: el más frecuente entre sus horas (empate: el menor)
        d = self.df.copy()
        d["dia"] = d["ts"].dt.tz_localize("UTC").dt.tz_convert("America/Santiago").dt.tz_localize(None).dt.normalize()
        d["r"] = self.regimen
        g = d.groupby(["est", "dia"]).agg(n=("o", "size"), r0=("r", lambda x: int((x == 0).sum())),
                                          r1=("r", lambda x: int((x == 1).sum())))
        g = g[g["n"] >= 18]
        esperado = np.where(g["r1"] > g["r0"], 1, 0)
        nv = self.nvs["diario_civil"]                                       # los dos, en el orden (estación, día)
        np.testing.assert_array_equal(nv.estratos["regimen_fila_a_fila"], esperado)
        self.assertTrue(0 < esperado.sum() < len(esperado))                 # hay días de los dos estratos


class TablaTests(unittest.TestCase):
    def setUp(self):
        self.d = base_simple()
        self.cortes = {"peso_vec": mt.cortes_cuartiles(self.d["pv"]), "dist_est_km": mt.cortes_cuartiles(self.d["dist"])}
        self.t = mt.tabla_metricas({"horario": self.d["base"]}, self.cortes, etiqueta_estacion=lambda c: f"E{c}",
                                   retransformacion={"a": "smearing_duan"})

    def fila(self, motor, desag, estrato, pond="ninguna", escala="original"):
        t = self.t
        return t[(t.motor == motor) & (t.desagregacion == desag) & (t.estrato == estrato) & (t.ponderacion == pond)
                 & (t.escala == escala)].iloc[0]

    def test_total_macrozona_estacion(self):
        d = self.d
        for m in ("a", "b"):
            self.assertAlmostEqual(self.fila(m, "total", "total")["r2"], directas(d["o"], d["p"][m])["r2"], places=10)
            s = d["mz"] == 3
            self.assertAlmostEqual(self.fila(m, "macrozona", "sur")["rmse"], directas(d["o"][s], d["p"][m][s])["rmse"],
                                   places=10)
            s = d["est"] == 1
            self.assertAlmostEqual(self.fila(m, "estacion", "E1")["nmb"], directas(d["o"][s], d["p"][m][s])["nmb"],
                                   places=10)

    def test_poblacion_y_escala_log(self):
        d = self.d
        self.assertAlmostEqual(self.fila("b", "total", "total", "poblacion")["r2"],
                               directas(d["o"], d["p"]["b"], d["pob"])["r2"], places=10)
        self.assertAlmostEqual(self.fila("a", "total", "total", escala="log")["r2"],
                               directas(np.log1p(d["o"]), d["z"]["a"])["r2"], places=10)
        self.assertAlmostEqual(self.fila("b", "total", "total", escala="log")["rmse"],
                               directas(np.log1p(d["o"]), np.log1p(np.clip(d["p"]["b"], 0, None)))["rmse"], places=10)
        self.assertFalse(((self.t.desagregacion == "estacion") & (self.t.ponderacion == "poblacion")).any())

    def test_estratos_de_soporte(self):
        e = mt.estrato_cuartil(self.d["pv"], self.cortes["peso_vec"])
        filas = self.t[(self.t.motor == "a") & (self.t.desagregacion == "soporte_peso_vec") & (self.t.escala == "original")]
        self.assertEqual(sorted(filas["n"].tolist()), sorted(np.bincount(e).tolist()))
        self.assertEqual(int(filas["n"].sum()), len(self.d["o"]))
        np.testing.assert_array_equal(mt.estrato_cuartil([np.nan, -1.0, 99.0], [0, 1, 2]), [-1, 0, 3])

    def test_retransformacion_en_la_tabla(self):
        self.assertEqual(set(self.t.loc[self.t.motor == "a", "retransformacion"]), {"smearing_duan"})
        self.assertEqual(set(self.t.loc[self.t.motor == "b", "retransformacion"]), {""})
        t = mt.tabla_metricas({"horario": self.d["base"]}, self.cortes)
        self.assertNotIn("retransformacion", t.columns)
        with self.assertRaises(ValueError):
            mt.tabla_metricas({"horario": self.d["base"]}, self.cortes, desagregaciones=("periodo_lpo",))


class RegimenesTests(unittest.TestCase):
    def test_cinco_regimenes_iguales_a_la_configuracion(self):
        self.assertEqual(mt.regimenes_de_config(CFG), mt._normalizar_regimenes(mt.REGIMENES))
        self.assertEqual([r["id"] for r in mt.REGIMENES], ["2000-2002", "2003-2018", "2019-2024", "2025", "2026"])
        anios = np.arange(1999, 2028)
        esperado = [-1, 0, 0, 0, *([1] * 16), *([2] * 6), 3, 4, -1]
        np.testing.assert_array_equal(mt.regimen_de_anio(anios), esperado)
        self.assertTrue(mt.etiquetas_regimen()[3].startswith("2025: sin GEOS-CF ni TROPOMI"))
        with self.assertRaisesRegex(ValueError, "cinco regímenes"):
            mt.regimen_de_anio([2020], (2019, 2024))
        with self.assertRaises(ValueError):
            mt._normalizar_regimenes([{"id": "a", "anios": [2000, 2010]}, {"id": "b", "anios": [2010, 2012]}])

    def test_tabla_por_regimen_ponderada(self):
        rng = np.random.default_rng(7)
        n = 2700
        anio = np.repeat(np.arange(2000, 2027), 100)
        est = rng.integers(0, 4, n)
        o = rng.gamma(2, 10, n)
        p = {"a": o + rng.normal(0, 4, n)}
        base = mt.nivel_horario(o, p, {"a": None}, est, np.full(n, 2), anio, np.ones(n), np.ones(n),
                                np.choose(est, [1.0, 2.0, 3.0, 4.0]), est)
        t = mt.tabla_metricas({"horario": base}, {"peso_vec": [0, 1, 2], "dist_est_km": [0, 1, 2]},
                              desagregaciones=("regimen",))
        t0 = t[(t.ponderacion == "ninguna") & (t.escala == "original")]
        self.assertEqual(t0["n"].tolist(), [300, 1600, 600, 100, 100])
        self.assertEqual(t0["estrato"].tolist(), mt.etiquetas_regimen())
        self.assertEqual(set(t.ponderacion), {"ninguna", "poblacion"})
        s = (anio >= 2019) & (anio <= 2024)
        fila = t[(t.ponderacion == "poblacion") & (t.escala == "original") & t.estrato.str.startswith("2019-2024")].iloc[0]
        w = np.choose(est, [1.0, 2.0, 3.0, 4.0])
        self.assertAlmostEqual(fila["r2"], directas(o[s], p["a"][s], w[s])["r2"], places=10)


class FilaAFilaYLPOTests(unittest.TestCase):
    def test_disponibilidad_fila_a_fila(self):
        nan = np.nan
        cols = {"cams_pm25": np.array([nan, nan, 1, 1, 1, 1]), "cams_no2": np.array([nan, 2, nan, nan, nan, nan]),
                "gcf_pm25": np.array([nan, nan, nan, 5, 5, nan]), "acag_clim": np.array([0, 0, 0, 0, 1, 1.0])}
        familias = {"cams": ["cams_no2", "cams_pm25"], "geos_cf": ["gcf_pm25", "gcf_no2"], "tropomi": ["no2_trop"],
                    "acag_climatologico": ["acag_clim"]}
        cod, etq, info = mt.disponibilidad_fila_a_fila(cols, familias)
        nombres = [etq[c] for c in cod]
        self.assertEqual(nombres, ["ninguna", "cams", "cams", "cams+geos_cf", "cams+geos_cf+acag_climatologico",
                                   "cams+acag_climatologico"])
        self.assertEqual(info["columnas_ausentes"], {"geos_cf": ["gcf_no2"], "tropomi": ["no2_trop"]})
        self.assertEqual(info["filas_con_familia"], {"cams": 5, "geos_cf": 2, "tropomi": 0, "acag_climatologico": 2})
        self.assertEqual(sum(info["filas_por_regimen"].values()), 6)
        with self.assertRaises(ValueError):
            mt.disponibilidad_fila_a_fila({"a": np.ones(2), "b": np.ones(3)}, {"x": ["a", "b"]})

    def test_familias_de_la_configuracion(self):
        f = mt.familias_de_config(CFG)
        self.assertEqual(list(f), ["cams", "geos_cf", "tropomi", "merra2", "blh", "acag_climatologico"])
        self.assertIn("gcf_pm25", f["geos_cf"])
        self.assertEqual(f["acag_climatologico"], ["acag_clim"])
        self.assertEqual(mt.FAMILIAS_INDICADORAS, ("acag_climatologico",))

    def test_periodos_lpo_con_2024_aparte(self):
        p = mt.periodos_lpo()
        self.assertEqual([x[0] for x in p], ["2000–2003", "2004–2007", "2008–2011", "2012–2015", "2016–2019",
                                             "2020–2023", "2024", "2025–2026"])
        self.assertEqual(mt.periodos_lpo_de_config(CFG), p)
        self.assertEqual(mt.periodos_lpo(2000, 2010, 4, aparte=2005)[1:4], (("2004", 2004, 2004), ("2005", 2005, 2005),
                                                                            ("2006–2007", 2006, 2007)))
        np.testing.assert_array_equal(mt.periodo_de_anio([2003, 2024, 2025, 2026, 2027], p), [0, 6, 7, 7, -1])
        n = 2700
        anio = np.repeat(np.arange(2000, 2027), 100)
        o = np.random.default_rng(3).gamma(2, 10, n)
        base = mt.nivel_horario(o, {"a": o * 1.1}, {"a": None}, np.zeros(n, dtype=int), np.full(n, 2), anio, np.ones(n),
                                np.ones(n), np.ones(n), np.zeros(n, dtype=int))
        t = mt.tabla_metricas({"horario": base}, {"peso_vec": [0, 1, 2], "dist_est_km": [0, 1, 2]}, periodos_lpo=p)
        t = t[(t.desagregacion == "periodo_lpo") & (t.ponderacion == "ninguna") & (t.escala == "original")]
        self.assertEqual(dict(zip(t.estrato, t.n)), {"2000–2003": 400, "2004–2007": 400, "2008–2011": 400,
                                                     "2012–2015": 400, "2016–2019": 400, "2020–2023": 400,
                                                     "2024": 100, "2025–2026": 200})

    def test_regimen_fila_a_fila_en_la_tabla(self):
        n = 400
        cod = np.repeat([0, 1, 2, 1], 100)
        o = np.random.default_rng(5).gamma(2, 10, n)
        base = mt.nivel_horario(o, {"a": o + 1}, {"a": None}, np.zeros(n, dtype=int), np.full(n, 2), np.full(n, 2020),
                                np.ones(n), np.ones(n), np.ones(n), np.zeros(n, dtype=int),
                                estratos={"regimen_fila_a_fila": (cod, ["ninguna", "cams", "cams+geos_cf"])})
        t = mt.tabla_metricas({"horario": base}, {"peso_vec": [0, 1, 2], "dist_est_km": [0, 1, 2]})
        t = t[(t.desagregacion == "regimen_fila_a_fila") & (t.escala == "original")]
        self.assertEqual(dict(zip(t[t.ponderacion == "ninguna"].estrato, t[t.ponderacion == "ninguna"].n)),
                         {"ninguna": 100, "cams": 200, "cams+geos_cf": 100})
        self.assertIn("poblacion", set(t.ponderacion))
        with self.assertRaises(ValueError):
            mt.nivel_horario(o, {"a": o}, {"a": None}, np.zeros(n, dtype=int), np.full(n, 2), np.full(n, 2020),
                             np.ones(n), np.ones(n), np.ones(n), np.zeros(n, dtype=int),
                             estratos={"x": (np.full(n, -1), ["a"])})


class PesosTests(unittest.TestCase):
    def test_peso_fijo_es_la_mediana_de_los_anios_no_de_las_filas(self):
        est = np.array([0] * 1000 + [0] * 10 + [0] * 10 + [1] * 6)
        anio = np.array([2015] * 1000 + [2017] * 10 + [2022] * 10 + [2015, 2015, 2015, 2016, 2016, 2016])
        pob = np.array([10.0] * 1000 + [20.0] * 10 + [1000.0] * 10 + [1.0, 2.0, 9.0, 4.0, 4.0, 4.0])
        w = mt.peso_fijo_por_estacion(est, anio, pob)
        self.assertEqual(w[0], 20.0)                                # mediana de {10, 20, 1000}; la de filas sería 10
        self.assertEqual(w[1], 3.0)                                 # mediana de {mediana(1, 2, 9) = 2, 4}
        w = mt.peso_fijo_por_estacion(np.array([0, 0, 2]), np.array([2020, 2021, 2020]), np.array([np.nan, 5.0, np.nan]))
        self.assertEqual(w[0], 5.0)
        self.assertTrue(np.isnan(w[1]) and np.isnan(w[2]))

    def test_nivel_horario_fija_el_peso_con_todas_las_filas(self):
        """El peso de la estación sale de todas sus filas (todos sus años), aunque la máscara deje sólo un año, y la
        métrica ponderada usa ese peso."""
        rng = np.random.default_rng(9)
        n = 4000
        est = rng.integers(0, 4, n)
        anio = rng.choice([2016, 2018, 2023], n)
        salto = {2016: 1.0, 2018: 3.0, 2023: 50.0}
        pob = np.choose(est, [100.0, 200.0, 300.0, 400.0]) * np.vectorize(salto.get)(anio)
        o = rng.gamma(2, 10, n)
        p = o + rng.normal(0, 5, n)
        mascara = anio != 2018                                              # dos años, con pob_dens distinta
        base = mt.nivel_horario(o, {"a": p}, {"a": None}, est, np.full(n, 2), anio, np.ones(n), np.ones(n), pob,
                                np.zeros(n, dtype=int), mascara)
        fijo = np.choose(est, [100.0, 200.0, 300.0, 400.0]) * 3.0              # mediana de {1, 3, 50}
        np.testing.assert_array_equal(base.poblacion, fijo[mascara])
        t = mt.tabla_metricas({"horario": base}, {"peso_vec": [0, 1, 2], "dist_est_km": [0, 1, 2]},
                              desagregaciones=("total",))
        fila = t[(t.ponderacion == "poblacion") & (t.escala == "original")].iloc[0]
        self.assertAlmostEqual(fila["r2"], directas(o[mascara], p[mascara], fijo[mascara])["r2"], places=10)
        self.assertNotAlmostEqual(fila["r2"], directas(o[mascara], p[mascara], pob[mascara])["r2"], places=6)

    def test_pesos_invalidos(self):
        n = 6
        args = (np.ones(n), {"a": np.ones(n)}, {"a": None}, np.array([0, 0, 0, 1, 1, 1]), np.full(n, 2),
                np.full(n, 2020), np.ones(n), np.ones(n))
        with self.assertRaisesRegex(ValueError, "pob_dens"):
            mt.nivel_horario(*args, np.array([1.0, 1, 1, np.nan, np.nan, np.nan]), np.zeros(n, dtype=int))
        with self.assertRaisesRegex(ValueError, "fijo por estación"):
            mt.nivel_horario(*args, np.ones(n), np.zeros(n, dtype=int),
                             pesos_extra={"desagrupamiento": np.array([1.0, 2, 1, 3, 3, 3])})
        with self.assertRaises(ValueError):
            mt.nivel_horario(*args, np.ones(n), np.zeros(n, dtype=int),
                             pesos_extra={"desagrupamiento": np.array([1.0, 1, 1, 3, 3, np.nan])})

    def test_peso_de_desagrupamiento(self):
        pob = pd.DataFrame({"cod_comuna": [13101] * 3 + [13102] * 3 + [5101] * 3, "anio": [2002, 2003, 2004] * 3,
                            "poblacion": [1000.0, 1100.0, 1300.0, 500.0, 600.0, 700.0, 80.0, 90.0, 100.0]})
        # estaciones 0 y 1 en 13101; 2 en 13102; 3 en 5101; 4 sin filas (no cuenta en su comuna 13101)
        comuna = np.array([13101, 13101, 13102, 5101, 13101])
        est = np.array([0, 0, 0, 1, 2, 2, 3])
        anio = np.array([2000, 2001, 2004, 2003, 2002, 2003, 2010])
        w, tabla = mt.peso_desagrupamiento(est, anio, comuna, pob, nombres_estacion=np.array(list("ABCDE")))
        # 0: años 2000→2002, 2001→2002, 2004: mediana(1000, 1000, 1300) = 1000; dos estaciones en la comuna
        self.assertEqual(w[0], 500.0)
        self.assertEqual(w[1], 1100.0 / 2)
        self.assertEqual(w[2], 550.0)                                  # mediana(500, 600), una estación
        self.assertEqual(w[3], 100.0)                                  # 2010 → 2004 (el más cercano)
        self.assertTrue(np.isnan(w[4]))
        self.assertEqual(tabla["estacion"].tolist(), ["A", "B", "C", "D"])
        self.assertEqual(tabla["estaciones_en_la_comuna"].tolist(), [2, 2, 1, 1])
        self.assertEqual(tabla["anios_sustituidos"].tolist(), ["2000→2002, 2001→2002", "", "", "2010→2004"])
        with self.assertRaisesRegex(ValueError, "sin comuna"):
            mt.peso_desagrupamiento(est, anio, np.array([13101, -1, 13102, 5101, 1]), pob)
        with self.assertRaisesRegex(ValueError, "9999"):
            mt.peso_desagrupamiento(est, anio, np.array([9999, 13101, 13102, 5101, 1]), pob)
        # empate entre dos años INE igual de cercanos: el anterior
        hueco = pd.DataFrame({"cod_comuna": [1, 1], "anio": [2002, 2004], "poblacion": [10.0, 30.0]})
        w, _ = mt.peso_desagrupamiento(np.array([0]), np.array([2003]), np.array([1]), hueco)
        self.assertEqual(w[0], 10.0)

    def test_leer_poblacion_comunal_suma_edades_y_sexos(self):
        df = pd.DataFrame({"cut_region": 13.0, "cut_comuna": [13101.0, 13101.0, 13101.0, 5101.0],
                           "edad": [0.0, 1.0, 0.0, 0.0], "año": [2002.0, 2002.0, 2003.0, 2002.0],
                           "población": [10.0, 5.0, 7.0, 3.0], "género": ["femenino", "masculino", "femenino", "masculino"]})
        with tempfile.TemporaryDirectory() as d:
            ruta = mt.ruta_poblacion_comunal(d)
            self.assertEqual(ruta.name, "censo_proyecciones_ano_edad_genero.parquet")
            df.to_parquet(ruta)
            antes = os.stat(ruta).st_mtime_ns
            p = mt.leer_poblacion_comunal(ruta)
            self.assertEqual(os.stat(ruta).st_mtime_ns, antes)
        self.assertEqual(p.to_dict("list"), {"cod_comuna": [5101, 13101, 13101], "anio": [2002, 2002, 2003],
                                             "poblacion": [3.0, 15.0, 7.0]})
        self.assertEqual(str(p["cod_comuna"].dtype), "int64")
        self.assertIn("covariables_estaticas.py:121-126", mt.CITA_POBLACION_COMUNAL)

    def test_comunas_de_manifiesto(self):
        man = {"estaciones": [{"estacion": "A", "cod_comuna": 13101}, {"estacion": "B", "cod_comuna": None}]}
        np.testing.assert_array_equal(mt.comunas_de_manifiesto(man, ["B", "A", "C"]), [-1, 13101, -1])

    def test_insumo_ine_real_cubre_las_comunas_del_manifiesto(self):
        """Si el insumo INE y el manifiesto están en esta máquina: cada estación tiene comuna y cada comuna tiene
        población en 2002-2035 (descriptivo, en sólo lectura)."""
        import _rutas_v2 as rv
        r = rv.RutasV2.desde_entorno()
        ruta = mt.ruta_poblacion_comunal(r.datos)
        if not (ruta.exists() and r.manifiesto_pliegues.exists()):
            self.skipTest("no están el insumo INE o el manifiesto de pliegues en esta máquina")
        pob = mt.leer_poblacion_comunal(ruta)
        man = json.loads(r.manifiesto_pliegues.read_text(encoding="utf-8"))
        com = mt.comunas_de_manifiesto(man, [e["estacion"] for e in man["estaciones"]])
        self.assertTrue((com > 0).all())
        anios = pob.groupby("cod_comuna")["anio"].agg(["min", "max", "size"])
        self.assertTrue(set(com.tolist()) <= set(anios.index))
        self.assertTrue(((anios.loc[sorted(set(com.tolist()))]) == [2002, 2035, 34]).all().all())


class EfectivosTests(unittest.TestCase):
    def test_kish_y_g_efectivo_junto_a_cada_metrica(self):
        rng = np.random.default_rng(11)
        n = 5000
        est = rng.integers(0, 6, n)
        bloque = np.array(["RM", "RM", "RV", "RV", "RVIII", "RX"])[est]
        o = rng.gamma(2, 10, n)
        pob = np.choose(est, [900.0, 700.0, 50.0, 40.0, 30.0, 10.0])
        des = np.choose(est, [3.0, 3.0, 1.0, 1.0, 1.0, 2.0])
        base = mt.nivel_horario(o, {"a": o + 1}, {"a": None}, est, np.where(est < 2, 2, 3), np.full(n, 2020),
                                np.ones(n), np.ones(n), pob, np.zeros(n, dtype=int), bloque=bloque,
                                pesos_extra={"desagrupamiento": des})
        t = mt.tabla_metricas({"horario": base}, {"peso_vec": [0, 1, 2], "dist_est_km": [0, 1, 2]},
                              desagregaciones=("total", "macrozona", "estacion"))
        self.assertTrue(set(mt.COLUMNAS_EFECTIVOS) <= set(t.columns))
        for pond, w in (("ninguna", np.ones(n)), ("poblacion", pob), ("desagrupamiento", des)):
            f = t[(t.desagregacion == "total") & (t.ponderacion == pond) & (t.escala == "original")].iloc[0]
            self.assertEqual((f["estaciones"], f["G"]), (6, 4))
            self.assertAlmostEqual(f["estaciones_kish"], kish(est, w), places=10)
            self.assertAlmostEqual(f["G_efectivo"], kish(bloque, w), places=10)
            self.assertAlmostEqual(f["estaciones_kish"], mt.n_efectivo(pd.Series(w).groupby(est).sum()), places=10)
        s = est >= 2
        f = t[(t.desagregacion == "macrozona") & (t.estrato == "sur") & (t.ponderacion == "poblacion")
              & (t.escala == "log")].iloc[0]
        self.assertEqual((f["estaciones"], f["G"]), (4, 3))
        self.assertAlmostEqual(f["G_efectivo"], kish(bloque[s], pob[s]), places=10)
        self.assertLess(f["G_efectivo"], 3.0)
        f = t[(t.desagregacion == "estacion") & (t.estrato == "0")].iloc[0]
        self.assertEqual((f["estaciones"], f["estaciones_kish"], f["G"], f["G_efectivo"]), (1, 1.0, 1, 1.0))
        self.assertTrue(np.isnan(mt.n_efectivo([0.0, np.nan])))


class ConjuntosTests(unittest.TestCase):
    def test_mascaras_y_registro(self):
        est = np.array([0, 0, 0, 1, 1, 2, 2, 3, 3])
        pliegue = np.array([0, 0, 0, 0, 0, 1, 1, 2, 2])
        q = np.array(["validado", "no_validado", None, "preliminar", "no_validado", "usable_native",
                      "solo_numeric_usable", "validado", "validado"], dtype=object)
        comunes = np.array([1, 1, 1, 1, 1, 1, 1, 1, 0], dtype=bool)
        c = mt.conjuntos_evaluacion(comunes, q, est)
        self.assertEqual(list(c), list(mt.CONJUNTOS))
        np.testing.assert_array_equal(c[mt.E1], comunes)
        np.testing.assert_array_equal(c[mt.E2], [1, 0, 0, 0, 0, 1, 0, 1, 0])
        np.testing.assert_array_equal(c[mt.E2_SINCA], [1, 0, 0, 0, 0, 0, 0, 1, 0])
        np.testing.assert_array_equal(c[mt.E1_PRIMA], [1, 1, 1, 0, 0, 1, 1, 1, 0])
        r = mt.registro_conjuntos(c, est, pliegue, nombres_estacion=np.array(["A", "B", "C", "D"]))
        self.assertEqual(r["estaciones_sin_E2"], ["B"])
        self.assertEqual(r["estaciones_sin_E2-SINCA"], ["B", "C"])
        self.assertEqual(r["pliegues_sin_E2"], [])
        self.assertEqual(r["pliegues_sin_E2-SINCA"], [1])
        self.assertEqual(r["pares"], {"E1": 8, "E2": 3, "E2-SINCA": 2, "E1′": 6})
        self.assertEqual(r["estaciones"]["E1′"], 3)
        r = mt.registro_conjuntos(c, est, pliegue)
        self.assertEqual(r["estaciones_sin_E2"], [1])
        self.assertEqual(json.loads(json.dumps(r))["pliegues_sin_E2-SINCA"], [1])        # serializable tal cual
        with self.assertRaisesRegex(ValueError, "bandera"):
            mt.conjuntos_evaluacion(comunes, None, est)

    def test_codigos_y_umbrales_de_la_configuracion(self):
        self.assertEqual(mt.codigos_evaluacion_de_config(CFG), {mt.E2: mt.CODIGOS_E2, mt.E2_SINCA: mt.CODIGOS_E2_SINCA})
        self.assertEqual(mt.evaluabilidad_de_config(CFG), {"minimo_fraccion": mt.MINIMO_FRACCION_PESO_E2,
                                                           "minimo_grupos": mt.MINIMO_GRUPOS_E2})
        self.assertEqual(sorted(CFG["calidad_blanco"]["evaluacion"]["conjuntos"]), sorted(mt.CONJUNTOS))
        self.assertIn(mt.SIN_CONFIRMACION, CFG["calidad_blanco"]["evaluacion"]["evaluabilidad"]["si_no_es_evaluable"])

    def test_e1_prima_separa_la_composicion_de_la_calidad(self):
        """La estación A tiene la mitad de sus horas validadas, con exactamente los mismos pares que las no
        validadas; B no tiene ninguna validada y errores mucho mayores. Entonces E1′ = E2 (la calidad no cambia
        nada) y E1 se aparta sólo por la composición. Si además las horas no validadas de A tienen más error, E1′
        se aparta de E2 (calidad) y E1 de E1′ (composición)."""
        rng = np.random.default_rng(13)
        m = 500
        o = rng.gamma(2, 10, m)
        p = o + rng.normal(0, 2, m)
        ob = rng.gamma(2, 10, 300)
        obs = np.concatenate([o, o, ob])
        pred = np.concatenate([p, p, ob + rng.normal(0, 15, 300)])
        est = np.repeat([0, 0, 1], [m, m, 300])
        q = np.repeat(np.array(["validado", "no_validado", "no_validado"], dtype=object), [m, m, 300])
        c = mt.conjuntos_evaluacion(np.ones(len(obs), dtype=bool), q, est)
        r = {k: mt.metricas(obs[v], pred[v]) for k, v in c.items()}
        for x in ("r2", "rmse", "nmb", "mae"):
            self.assertAlmostEqual(r[mt.E1_PRIMA][x], r[mt.E2][x], places=10)
        self.assertGreater(r[mt.E1]["rmse"], 2 * r[mt.E1_PRIMA]["rmse"])
        pred2 = pred.copy()
        pred2[m:2 * m] += rng.normal(0, 8, m)                         # A no validada, peor
        r2 = {k: mt.metricas(obs[v], pred2[v]) for k, v in c.items()}
        self.assertGreater(r2[mt.E1_PRIMA]["rmse"], 1.5 * r2[mt.E2]["rmse"])
        self.assertGreater(r2[mt.E1]["rmse"], r2[mt.E1_PRIMA]["rmse"])

    def niveles_e(self, frac_validada, grupos_con_e2):
        """Nivel diario civil de E1 y E2 con 8 grupos (una estación por grupo) y pesos fijos por estación."""
        ts = pd.date_range("2020-07-01 04:00", periods=24 * 30, freq="h").to_numpy("datetime64[ns]")
        n_est = 8
        est = np.repeat(np.arange(n_est), len(ts))
        tt = np.tile(ts, n_est)
        o = np.random.default_rng(1).gamma(2, 10, len(est))
        pob = np.choose(est, [400.0, 300.0, 100.0, 80.0, 60.0, 40.0, 15.0, 5.0])
        q = np.full(len(est), "no_validado", dtype=object)
        for e in range(grupos_con_e2):
            q[(est == e) & (np.tile(np.arange(len(ts)), n_est) < frac_validada * len(ts))] = "validado"
        anio = np.full(len(est), 2020)
        c = mt.conjuntos_evaluacion(np.ones(len(est), dtype=bool), q, est)
        out = {}
        for k in (mt.E1, mt.E2):
            b = mt.nivel_horario(o, {"a": o}, {"a": None}, est, np.full(len(est), 2), anio, np.ones(len(est)),
                                 np.ones(len(est)), pob, est, c[k])
            out[k] = mt.niveles(b, tt[c[k]])["diario_civil"]
        return out, pob

    def test_evaluabilidad_de_e2(self):
        nv, _ = self.niveles_e(1.0, 5)                         # grupos 0–4: 940 de 1.000 del peso
        e = mt.evaluabilidad_e2(nv[mt.E1], nv[mt.E2])
        self.assertTrue(e["evaluable"])
        self.assertEqual((e["estado"], e["grupos_E1"], e["grupos_con_E2"], e["nivel"]), ("evaluable", 8, 5, "diario_civil"))
        self.assertAlmostEqual(e["fraccion_del_peso"], 940 / 1000, places=12)
        nv, _ = self.niveles_e(1.0, 4)                         # cuatro grupos: no evaluable aunque pese 88 %
        e = mt.evaluabilidad_e2(nv[mt.E1], nv[mt.E2])
        self.assertFalse(e["evaluable"])
        self.assertEqual(e["estado"], mt.SIN_CONFIRMACION)
        self.assertIn("4 grupos", e["motivo"][0])
        nv, _ = self.niveles_e(0.4, 8)                         # 40 % de los días validados en todos los grupos
        e = mt.evaluabilidad_e2(nv[mt.E1], nv[mt.E2])
        self.assertFalse(e["evaluable"])
        self.assertAlmostEqual(e["fraccion_del_peso"], 12 / 30, places=12)
        self.assertIn("del peso de E1", e["motivo"][0])
        e = mt.evaluabilidad_e2(nv[mt.E1], nv[mt.E2], minimo_fraccion=0.3)
        self.assertTrue(e["evaluable"])
        self.assertEqual(json.loads(json.dumps(e))["estado"], "evaluable")


class CuantilesTests(unittest.TestCase):
    def test_metricas_cuantiles(self):
        y = np.array([1.0, 5.0, 10.0, 3.0] * 5)
        q05 = np.array([0.0, 6.0, 2.0, 4.0] * 5)
        q50 = np.array([1.0, 6.5, 6.0, 3.0] * 5)
        q95 = np.array([2.0, 8.0, 9.0, 2.0] * 5)
        t = mt.metricas_cuantiles(y, q05, q50, q95, np.array([2, 2, 3, 3] * 5), np.array([3, 12, 3, 12] * 5))
        tot = t[t.agrupacion == "total"].iloc[0]
        self.assertAlmostEqual(tot["cobertura_90"], 0.25)
        self.assertAlmostEqual(tot["cruces"], 0.25)
        self.assertAlmostEqual(tot["tasa_q50"], 0.75)
        self.assertAlmostEqual(tot["puntaje_intervalo"], np.mean([2.0, 22.0, 27.0, 38.0]))
        self.assertEqual(sorted(t.agrupacion.unique()), ["decil_prediccion", "franja", "macrozona", "total"])
        a = mt.metricas_alerta(y, q95, np.array([2, 2, 3, 3] * 5), np.array([3, 12, 3, 12] * 5))
        self.assertAlmostEqual(a[a.agrupacion == "total"].iloc[0]["tasa_bajo_cuantil"], 0.5)


if __name__ == "__main__":
    unittest.main()
