"""Pruebas de ``metricas_v2``: fórmulas (con y sin pesos), pares comunes, día civil con horario de verano frente
a UTC−4, mínimos de horas, días y meses contra una referencia en pandas, desagregaciones y cuantiles."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))
import metricas_v2 as mt  # noqa: E402


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
        base = mt.nivel_horario(d["o"].to_numpy(), {"m": d["p"].to_numpy()}, {"m": None}, d["est"].to_numpy(),
                                np.full(n, 2), (d["ts"] - pd.Timedelta(hours=4)).dt.year.to_numpy(), np.ones(n),
                                np.ones(n), np.full(n, 10.0), np.zeros(n, dtype=int))
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


class TablaTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(2)
        n = 3000
        self.o = rng.gamma(2, 10, n)
        self.p = {"a": self.o * np.exp(rng.normal(0, .3, n)), "b": self.o + rng.normal(0, 5, n)}
        self.z = {"a": np.log1p(self.o) + rng.normal(0, .3, n), "b": None}
        self.est = rng.integers(0, 3, n)
        self.mz = np.where(self.est < 2, 2, 3)
        self.anio = np.where(np.arange(n) < 1000, 2018, 2020)
        self.pv = rng.uniform(0, 5, n)
        self.dist = np.choose(self.est, [1.0, 10.0, 30.0])
        self.pob = np.choose(self.est, [100.0, 2000.0, 50.0])
        self.base = mt.nivel_horario(self.o, self.p, self.z, self.est, self.mz, self.anio, self.pv, self.dist, self.pob,
                                     np.zeros(n, dtype=int))
        self.cortes = {"peso_vec": mt.cortes_cuartiles(self.pv), "dist_est_km": mt.cortes_cuartiles(self.dist)}
        self.t = mt.tabla_metricas({"horario": self.base}, self.cortes, etiqueta_estacion=lambda c: f"E{c}")

    def fila(self, motor, desag, estrato, pond="ninguna", escala="original"):
        t = self.t
        return t[(t.motor == motor) & (t.desagregacion == desag) & (t.estrato == estrato) & (t.ponderacion == pond)
                 & (t.escala == escala)].iloc[0]

    def test_total_macrozona_estacion_regimen(self):
        for m in ("a", "b"):
            self.assertAlmostEqual(self.fila(m, "total", "total")["r2"], directas(self.o, self.p[m])["r2"], places=10)
            s = self.mz == 3
            self.assertAlmostEqual(self.fila(m, "macrozona", "sur")["rmse"], directas(self.o[s], self.p[m][s])["rmse"], places=10)
            s = self.est == 1
            self.assertAlmostEqual(self.fila(m, "estacion", "E1")["nmb"], directas(self.o[s], self.p[m][s])["nmb"], places=10)
            s = self.anio == 2020
            fila = self.t[(self.t.motor == m) & (self.t.desagregacion == "regimen") & self.t.estrato.str.startswith("con")
                          & (self.t.ponderacion == "ninguna") & (self.t.escala == "original")].iloc[0]
            self.assertEqual(int(fila["n"]), int(s.sum()))

    def test_poblacion_y_escala_log(self):
        self.assertAlmostEqual(self.fila("b", "total", "total", "poblacion")["r2"],
                               directas(self.o, self.p["b"], self.pob)["r2"], places=10)
        self.assertAlmostEqual(self.fila("a", "total", "total", escala="log")["r2"],
                               directas(np.log1p(self.o), self.z["a"])["r2"], places=10)
        self.assertAlmostEqual(self.fila("b", "total", "total", escala="log")["rmse"],
                               directas(np.log1p(self.o), np.log1p(np.clip(self.p["b"], 0, None)))["rmse"], places=10)
        self.assertFalse(((self.t.desagregacion == "estacion") & (self.t.ponderacion == "poblacion")).any())

    def test_estratos_de_soporte(self):
        e = mt.estrato_cuartil(self.pv, self.cortes["peso_vec"])
        filas = self.t[(self.t.motor == "a") & (self.t.desagregacion == "soporte_peso_vec") & (self.t.escala == "original")]
        self.assertEqual(sorted(filas["n"].tolist()), sorted(np.bincount(e).tolist()))
        self.assertEqual(int(filas["n"].sum()), len(self.o))
        np.testing.assert_array_equal(mt.estrato_cuartil([np.nan, -1.0, 99.0], [0, 1, 2]), [-1, 0, 3])


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
