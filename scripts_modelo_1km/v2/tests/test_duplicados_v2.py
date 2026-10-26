"""Pruebas de ``duplicados_v2`` (R9): una copia por hora en las series duplicadas. Datos sintéticos."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))
import duplicados_v2 as dv  # noqa: E402

KM = dv.RADIO_TIERRA_KM * np.pi / 180.0
LAT0, LON0 = -33.0, -70.6
T0 = pd.Timestamp("2024-01-01 03:00")


def lat(km: float) -> float:
    return LAT0 + km / KM


def serie(est: str, horas: range, valores) -> pd.DataFrame:
    ts = T0 + pd.to_timedelta(list(horas), unit="h")
    return pd.DataFrame({"estacion": est, "ts_utc": ts, "obs": np.asarray(valores, dtype="float64")})


class DuplicadosTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(7)
        base = np.round(rng.lognormal(2.5, 0.6, 2000), 1)
        b = base.copy()
        b[::40] += 1.0                                                     # 2,5 % de horas distintas
        e = base.copy()
        e[::8] += 1.0                                                      # 12,5 % distintas
        self.obs = pd.concat([
            serie("A", range(0, 2000), base),                              # la de más horas
            serie("B", range(0, 1500), b[:1500]),                          # misma serie, a 1 km de A
            serie("C", range(1300, 2000), base[1300:2000]),                # 700 horas comunes con A: no basta
            serie("D", range(0, 2000), base),                              # idéntica, pero a 4 km
            serie("E", range(0, 2000), e),                                 # a 1 km, con 87,5 % iguales
        ], ignore_index=True)
        self.coords = pd.DataFrame({"estacion": list("ABCDE"),
                                    "lat": [lat(0), lat(1.0), lat(-1.0), lat(4.0), lat(0.5)], "lon": LON0})

    def test_pares(self):
        p = dv.pares_duplicados(self.obs, self.coords).set_index(["a", "b"])
        self.assertTrue(p.loc[("A", "B"), "duplicado"])
        self.assertEqual(p.loc[("A", "B"), "conserva"], "A")
        self.assertEqual(p.loc[("A", "B"), "horas_comunes"], 1500)
        self.assertFalse(p.loc[("A", "C"), "duplicado"])                   # < 720 horas comunes
        self.assertFalse(p.loc[("A", "E"), "duplicado"])                   # < 95 % iguales
        self.assertNotIn(("A", "D"), p.index)                              # a más de 2 km
        self.assertGreaterEqual(p.loc[("A", "B"), "fraccion_iguales"], 0.95)

    def test_una_copia_por_hora(self):
        p = dv.pares_duplicados(self.obs, self.coords)
        sin, reg = dv.quitar_copias(self.obs, p)
        self.assertEqual(int((sin["estacion"] == "B").sum()), 0)             # B sólo tenía horas comunes
        self.assertEqual(int((sin["estacion"] == "A").sum()), 2000)
        self.assertEqual(len(reg), 1)
        self.assertEqual(reg[0]["filas_quitadas"], {"A": 0, "B": 1500})
        self.assertFalse(sin.duplicated(["estacion", "ts_utc"]).any())

    def test_conserva_las_horas_propias_de_la_copia(self):
        o = pd.concat([serie("A", range(0, 1000), np.arange(1000.0)),
                       serie("B", range(200, 1500), np.arange(200.0, 1500.0))], ignore_index=True)
        c = pd.DataFrame({"estacion": ["A", "B"], "lat": [lat(0), lat(0.5)], "lon": LON0})
        p = dv.pares_duplicados(o, c)
        self.assertEqual(p.iloc[0]["conserva"], "B")                       # B tiene más horas
        sin, _ = dv.quitar_copias(o, p)
        self.assertEqual(int((sin["estacion"] == "A").sum()), 200)          # A queda sólo con sus 200 horas propias
        horas = sin.groupby("ts_utc").size()
        self.assertTrue((horas == 1).all())

    def test_grupo_de_tres(self):
        v = np.arange(2000.0)
        o = pd.concat([serie("X", range(0, 2000), v), serie("Y", range(0, 1800), v[:1800]),
                       serie("Z", range(0, 900), v[:900])], ignore_index=True)
        c = pd.DataFrame({"estacion": ["X", "Y", "Z"], "lat": [lat(0), lat(1.5), lat(3.0)], "lon": LON0})
        p = dv.pares_duplicados(o, c)                                       # X~Y y Y~Z (X-Z a 3 km)
        self.assertEqual(int(p["duplicado"].sum()), 2)
        sin, reg = dv.quitar_copias(o, p)
        self.assertEqual(reg[0]["grupo"], ["X", "Y", "Z"])
        self.assertEqual(sorted(sin["estacion"].unique()), ["X"])
        self.assertEqual(len(sin), 2000)

    def test_empate_por_codigo(self):
        """R9 y T1(2): en el empate de horas conserva el código menor, en el registro (``conserva``) y en lo que queda
        (``quitar_copias``): las dos usan la misma regla (``orden_de_conservacion``; ronda 4, menor 21)."""
        o = pd.concat([serie("Q2", range(0, 800), np.ones(800)), serie("Q1", range(0, 800), np.ones(800))],
                      ignore_index=True)
        c = pd.DataFrame({"estacion": ["Q1", "Q2"], "lat": [lat(0), lat(0.2)], "lon": LON0})
        p = dv.pares_duplicados(o, c)
        self.assertEqual(p.iloc[0]["conserva"], "Q1")
        sin, reg = dv.quitar_copias(o, p)
        self.assertEqual(sorted(sin["estacion"].unique()), ["Q1"])          # quedan sólo las filas de Q1
        self.assertEqual(len(sin), 800)
        self.assertEqual(reg[0]["orden_por_horas"][0], p.iloc[0]["conserva"])     # el registro dice lo que pasó
        self.assertEqual(reg[0]["filas_quitadas"], {"Q1": 0, "Q2": 800})

    def test_sin_pares(self):
        sin, reg = dv.quitar_copias(self.obs, dv.pares_duplicados(self.obs.iloc[:0], self.coords))
        self.assertEqual(len(sin), len(self.obs))
        self.assertEqual(reg, [])


if __name__ == "__main__":
    unittest.main()
