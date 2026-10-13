"""Pruebas de ``bootstrap_v2``: Δ puntual, réplicas que reproducen el remuestreo por bloques de los pares, motores
iguales, determinismo con la semilla, pesos y la regla de superioridad con el ruido de semillas."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))
import bootstrap_v2 as bs  # noqa: E402
import metricas_v2 as mt  # noqa: E402


def datos(semilla=0, n=4000, bloques=12):
    rng = np.random.default_rng(semilla)
    b = rng.integers(0, bloques, n)
    o = rng.gamma(2, 10, n) + b
    a = o * np.exp(rng.normal(0, 0.25, n))
    c = o + rng.normal(0, 6, n) + 0.3 * b
    w = rng.uniform(0.5, 3, n)
    return b, o, {"a": a, "c": c}, w


class BootstrapTests(unittest.TestCase):
    def test_delta_puntual_igual_al_directo(self):
        b, o, p, w = datos()
        for pesos in (None, w):
            S = bs.SumasBloques.desde_pares(b, o, p, pesos)
            t = bs.bootstrap_diferencias(S, [("a", "c")], replicas=50, semilla=[1])
            ma, mc = mt.metricas(o, p["a"], pesos), mt.metricas(o, p["c"], pesos)
            d = t.set_index("estadistico")["delta"]
            self.assertAlmostEqual(d["delta_r2"], ma["r2"] - mc["r2"], places=10)
            self.assertAlmostEqual(d["delta_rmse"], ma["rmse"] - mc["rmse"], places=10)
            self.assertAlmostEqual(d["delta_nmb"], ma["nmb"] - mc["nmb"], places=10)
            self.assertAlmostEqual(d["delta_abs_nmb"], abs(ma["nmb"]) - abs(mc["nmb"]), places=10)

    def test_una_replica_es_el_remuestreo_de_los_bloques(self):
        b, o, p, w = datos(semilla=3, bloques=7)
        S = bs.SumasBloques.desde_pares(b, o, p, w)
        C = bs.conteos_bootstrap(len(S.bloques), 5, [9])
        self.assertTrue(np.all(C.sum(axis=1) == len(S.bloques)))
        for fila in C:
            idx = np.concatenate([np.flatnonzero(b == S.bloques[j]) for j in range(len(S.bloques)) for _ in range(int(fila[j]))])
            r2, rmse, nmb = bs._metricas(fila[None, :], S, "a")
            ref = mt.metricas(o[idx], p["a"][idx], w[idx])
            self.assertAlmostEqual(float(r2[0]), ref["r2"], places=9)
            self.assertAlmostEqual(float(rmse[0]), ref["rmse"], places=9)
            self.assertAlmostEqual(float(nmb[0]), ref["nmb"], places=9)

    def test_motores_iguales_dan_cero(self):
        b, o, p, _ = datos()
        S = bs.SumasBloques.desde_pares(b, o, {"a": p["a"], "a2": p["a"].copy()})
        t = bs.bootstrap_diferencias(S, [("a", "a2")], replicas=200, semilla=[2])
        self.assertTrue(np.allclose(t[["delta", "ic_inf", "ic_sup"]].to_numpy(), 0.0))

    def test_determinista_con_la_semilla(self):
        b, o, p, _ = datos()
        S = bs.SumasBloques.desde_pares(b, o, p)
        t1 = bs.bootstrap_diferencias(S, [("a", "c")], replicas=300, semilla=bs.semilla_bootstrap(3))
        t2 = bs.bootstrap_diferencias(S, [("a", "c")], replicas=300, semilla=bs.semilla_bootstrap(3))
        t3 = bs.bootstrap_diferencias(S, [("a", "c")], replicas=300, semilla=bs.semilla_bootstrap(4))
        self.assertTrue(t1.equals(t2))
        self.assertFalse(t1.equals(t3))
        self.assertEqual(bs.semilla_bootstrap(3), [42, 2000, 3])
        with self.assertRaises(ValueError):
            bs.bootstrap_diferencias(S, [("a", "c")], replicas=10)
        with self.assertRaises(ValueError):
            bs.SumasBloques.desde_pares(b, o, {"x": np.where(b == 0, np.nan, o)})

    def test_intervalo_cubre_la_diferencia_verdadera(self):
        """Con muchos bloques, el intervalo percentil del ΔRMSE contiene al Δ puntual y excluye 0 cuando un motor es
        claramente mejor."""
        b, o, p, _ = datos(n=20000, bloques=60)
        p["a"] = o * np.exp(np.random.default_rng(8).normal(0, 0.1, len(o)))          # «a», claramente mejor
        S = bs.SumasBloques.desde_pares(b, o, p)
        t = bs.bootstrap_diferencias(S, [("a", "c")], replicas=2000, semilla=[5]).set_index("estadistico")
        f = t.loc["delta_rmse"]
        self.assertLess(f["ic_inf"], f["delta"])
        self.assertGreater(f["ic_sup"], f["delta"])
        self.assertTrue(bs.excluye_cero_a_favor("delta_rmse", f["ic_inf"], f["ic_sup"]))


class ReglaTests(unittest.TestCase):
    def test_direcciones_y_ruido(self):
        self.assertTrue(bs.excluye_cero_a_favor("delta_r2", 0.01, 0.03))
        self.assertFalse(bs.excluye_cero_a_favor("delta_r2", -0.01, 0.03))
        self.assertTrue(bs.excluye_cero_a_favor("delta_rmse", -0.5, -0.1))
        self.assertFalse(bs.excluye_cero_a_favor("delta_nmb", 0.1, 0.2))
        self.assertEqual(bs.ruido_semillas([0.40, 0.43, 0.41]), 0.43 - 0.40)
        self.assertTrue(np.isnan(bs.ruido_semillas([0.4])))
        self.assertIsNone(bs.supera_ruido(0.02, np.nan, None))
        self.assertTrue(bs.supera_ruido(0.02, 0.01, 0.015))
        self.assertFalse(bs.supera_ruido(0.012, 0.01, 0.015))

    def test_aplicar_regla(self):
        import pandas as pd
        t = pd.DataFrame([{"motor_a": "x", "motor_b": "lightgbm", "estadistico": "delta_r2", "delta": 0.02,
                           "ic_inf": 0.01, "ic_sup": 0.03},
                          {"motor_a": "y", "motor_b": "lightgbm", "estadistico": "delta_r2", "delta": 0.02,
                           "ic_inf": 0.01, "ic_sup": 0.03},
                          {"motor_a": "z", "motor_b": "lightgbm", "estadistico": "delta_r2", "delta": 0.02,
                           "ic_inf": -0.01, "ic_sup": 0.03}])
        r = bs.aplicar_regla(t, {("x", "r2"): 0.005, ("lightgbm", "r2"): 0.01, ("z", "r2"): 0.001})
        self.assertEqual(r["a_supera_b"].tolist(), [True, True, False])
        r = bs.aplicar_regla(t, {})
        self.assertEqual(r["a_supera_b"].tolist(), [None, None, False])      # sin ruido medido: no evaluada


if __name__ == "__main__":
    unittest.main()
