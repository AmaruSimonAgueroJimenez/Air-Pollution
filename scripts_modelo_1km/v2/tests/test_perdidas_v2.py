"""Pruebas de ``perdidas_v2``: gradientes de Huber y del cuantil, δ de Huber, parámetros por variante y cobertura
nominal de los cuantiles en un caso simulado (LightGBM y XGBoost)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))
import perdidas_v2 as pv  # noqa: E402

BASE_LGBM = {"learning_rate": 0.1, "num_leaves": 15, "min_data_in_leaf": 20, "verbose": -1, "num_threads": 2,
             "deterministic": True, "force_col_wise": True, "seed": 42}


def datos(n=4000, semilla=1):
    rng = np.random.default_rng(semilla)
    X = rng.normal(size=(n, 4)).astype("float32")
    y = np.exp(rng.normal(2.0, 0.8, size=n)) + 3.0 * np.abs(X[:, 0]) + 2.0 * (X[:, 1] > 0)
    return X, y


class GradientesTests(unittest.TestCase):
    def test_huber_es_la_derivada_de_su_perdida(self):
        rng = np.random.default_rng(0)
        y = rng.normal(10, 5, 2000)
        pred = y + rng.normal(0, 4, 2000)
        d, h = 2.5, 1e-6
        g, hess = pv.huber_gradiente(pred, y, d)
        num = (pv.huber_perdida(pred + h, y, d) - pv.huber_perdida(pred - h, y, d)) / (2 * h)
        lejos = np.abs(np.abs(pred - y) - d) > 1e-3                       # fuera del quiebre en ±δ
        np.testing.assert_allclose(g[lejos], num[lejos], atol=1e-5)
        self.assertTrue(np.all(hess == 1.0))
        self.assertEqual(float(np.abs(g).max()), d)                        # recortado en ±δ

    def test_huber_igual_al_de_lightgbm(self):
        """El gradiente propio reproduce el objetivo ``huber`` de LightGBM (sin bagging, que con objetivos propios
        sortea distinto): mismas predicciones a la precisión de float32."""
        import lightgbm as lgb
        X, y = datos()
        d = 2.5
        m1 = lgb.train({**BASE_LGBM, "objective": "huber", "alpha": d}, lgb.Dataset(X, label=y), num_boost_round=40)

        def fobj(pred, ds):
            return pv.huber_gradiente(pred, ds.get_label(), d)

        mu = float(np.mean(y))
        m2 = lgb.train({**BASE_LGBM, "objective": fobj}, lgb.Dataset(X, label=y, init_score=np.full(len(y), mu)),
                       num_boost_round=40)
        np.testing.assert_allclose(m1.predict(X), m2.predict(X) + mu, rtol=0, atol=1e-6)

    def test_huber_xgboost_con_delta_enorme_es_cuadratico(self):
        """Con δ → ∞ el objetivo propio de XGBoost (gradiente r, hessiana 1) es exactamente reg:squarederror."""
        import xgboost as xgb
        X, y = datos()
        base = {"tree_method": "hist", "max_leaves": 15, "grow_policy": "lossguide", "eta": 0.1, "max_depth": 0,
                "max_bin": 255, "nthread": 2, "seed": 42, "subsample": 0.8, "colsample_bytree": 0.8,
                "min_child_weight": 20, "lambda": 1.0, "verbosity": 0}
        p_h, obj = pv.parametros_xgboost(base, pv.Variante("huber", delta=1e12), y)
        p_l2, obj_l2 = pv.parametros_xgboost(base, pv.Variante("l2_original"), y)
        self.assertIsNone(obj_l2)
        self.assertEqual(p_h["base_score"], p_l2["base_score"])
        self.assertAlmostEqual(p_h["base_score"], float(np.mean(y)))
        b1 = xgb.train(p_h, xgb.QuantileDMatrix(X, label=y, max_bin=255), num_boost_round=30, obj=obj)
        b2 = xgb.train(p_l2, xgb.QuantileDMatrix(X, label=y, max_bin=255), num_boost_round=30)
        np.testing.assert_allclose(b1.inplace_predict(X), b2.inplace_predict(X), rtol=0, atol=1e-4)

    def test_objetivo_xgb_huber_entrega_el_gradiente_de_lightgbm(self):
        class D:
            def __init__(self, y):
                self.y = y

            def get_label(self):
                return self.y

        y = np.array([0.0, 1.0, 5.0, 10.0])
        pred = np.array([3.0, 1.5, -2.0, 10.0])
        g, h = pv.objetivo_xgb_huber(2.0)(pred, D(y))
        np.testing.assert_array_equal(g, [2.0, 0.5, -2.0, 0.0])
        np.testing.assert_array_equal(h, [1.0, 1.0, 1.0, 1.0])

    def test_pinball_es_el_subgradiente_y_su_minimo_es_el_cuantil(self):
        rng = np.random.default_rng(2)
        y = rng.gamma(2.0, 10.0, 3000)
        for tau in pv.TAUS:
            q = y + rng.normal(0, 3, len(y))
            g, hess = pv.pinball_gradiente(q, y, tau)
            h = 1e-6
            num = (pv.pinball_perdida(y, q + h, tau) - pv.pinball_perdida(y, q - h, tau)) / (2 * h)
            lejos = np.abs(q - y) > 1e-3
            np.testing.assert_allclose(g[lejos], num[lejos], atol=1e-6)
            self.assertTrue(np.all(hess == 1.0))
            self.assertTrue(np.all(np.isin(g, [1.0 - tau, -tau])))
            malla = np.linspace(np.quantile(y, tau) - 2, np.quantile(y, tau) + 2, 4001)
            perdida = [pv.pinball_perdida(y, c, tau).mean() for c in malla]
            self.assertLess(abs(malla[int(np.argmin(perdida))] - np.quantile(y, tau)), 0.05)

    def test_pinball_igual_al_inicio_de_lightgbm(self):
        """El objetivo ``quantile`` de LightGBM parte del cuantil τ del blanco, como ``inicio_xgboost``."""
        import lightgbm as lgb
        X, y = datos()
        for tau in pv.TAUS:
            p = pv.parametros_lightgbm({**BASE_LGBM, "learning_rate": 1e-12}, pv.Variante("pinball", tau=tau))
            m = lgb.train(p, lgb.Dataset(X, label=y), num_boost_round=1)
            self.assertAlmostEqual(float(m.predict(X[:1])[0]), pv.inicio_xgboost(y, pv.Variante("pinball", tau=tau)),
                                   delta=1e-3 * float(np.std(y)))


class DeltaYVariantesTests(unittest.TestCase):
    def test_delta_huber_con_mad_normalizado(self):
        r = np.array([-3.0, -1.0, 0.0, 1.0, 2.0, 50.0])
        mad_crudo = float(np.median(np.abs(r - np.median(r))))
        self.assertAlmostEqual(pv.mad(r, normalizada=False), mad_crudo)
        self.assertAlmostEqual(pv.delta_huber(r), 1.345 * 1.482602218505602 * mad_crudo)
        with self.assertRaises(ValueError):
            pv.delta_huber(np.zeros(10))

    def test_variantes(self):
        v = pv.variante_de_etiqueta("q05")
        self.assertEqual((v.nombre, v.tau, v.etiqueta, v.escala), ("pinball", 0.05, "q05", "original"))
        self.assertEqual(pv.Variante("l2_log_duan").escala, "log")
        self.assertEqual(pv.Variante("huber").con_delta(3.0).delta, 3.0)
        with self.assertRaises(ValueError):
            pv.Variante("pinball")
        with self.assertRaises(ValueError):
            pv.Variante("l2_original", tau=0.5)
        with self.assertRaises(ValueError):
            pv.parametros_lightgbm({}, pv.Variante("huber"))
        p = pv.parametros_lightgbm({"seed": 1}, pv.Variante("pinball", tau=0.95))
        self.assertEqual((p["objective"], p["alpha"]), ("quantile", 0.95))
        p = pv.parametros_lightgbm({}, pv.Variante("huber", delta=2.0))
        self.assertEqual((p["objective"], p["alpha"]), ("huber", 2.0))
        px, obj = pv.parametros_xgboost({}, pv.Variante("pinball", tau=0.05), np.arange(101.0))
        self.assertEqual((px["objective"], px["quantile_alpha"], px["base_score"], obj), ("reg:quantileerror", 0.05, 5.0, None))
        np.testing.assert_allclose(pv.transformar_blanco([0.0, np.e - 1], pv.Variante("l2_log_duan")), [0.0, 1.0])

    def test_recorte_en_cero_de_la_escala_original(self):
        np.testing.assert_array_equal(pv.a_escala_original([-1.0, 0.0, 2.5], pv.Variante("huber", delta=1.0)),
                                      np.array([0.0, 0.0, 2.5], dtype="float32"))
        with self.assertRaises(ValueError):
            pv.a_escala_original([1.0], pv.Variante("l2_log_duan"))

    def test_cobertura_y_puntaje_de_intervalo(self):
        y = np.array([1.0, 5.0, 10.0, 3.0])
        lo = np.array([0.0, 6.0, 2.0, 4.0])
        hi = np.array([2.0, 8.0, 9.0, 2.0])                                  # la última cruzada: no cubre
        self.assertEqual(pv.cobertura(y, lo, hi), 0.25)
        pi = pv.puntaje_intervalo(y, lo, hi, alfa=0.1)
        np.testing.assert_allclose(pi, [2.0, 2.0 + 20 * 1.0, 7.0 + 20 * 1.0, -2.0 + 20 * 1.0 + 20 * 1.0])


class CoberturaNominalTests(unittest.TestCase):
    """Datos heterocedásticos simulados: el intervalo [q05, q95] de cada motor cubre ~90 % de una muestra nueva."""

    @classmethod
    def setUpClass(cls):
        rng = np.random.default_rng(7)

        def simular(n):
            X = rng.uniform(-2, 2, size=(n, 3)).astype("float32")
            escala = 0.3 + 0.6 * np.abs(X[:, 1])
            y = 20 + 6 * X[:, 0] + escala * 5 * rng.normal(size=n)
            return X, y

        cls.Xtr, cls.ytr = simular(12000)
        cls.Xte, cls.yte = simular(12000)

    def _cuantiles(self, motor):
        import lightgbm as lgb
        import xgboost as xgb
        out = {}
        for tau in (0.05, 0.95):
            v = pv.Variante("pinball", tau=tau)
            if motor == "lightgbm":
                p = pv.parametros_lightgbm({**BASE_LGBM, "learning_rate": 0.05, "min_data_in_leaf": 50}, v)
                out[tau] = lgb.train(p, lgb.Dataset(self.Xtr, label=self.ytr), num_boost_round=300).predict(self.Xte)
            else:
                base = {"tree_method": "hist", "max_leaves": 15, "grow_policy": "lossguide", "eta": 0.05, "max_depth": 0,
                        "max_bin": 255, "nthread": 2, "seed": 42, "min_child_weight": 50, "lambda": 1.0, "verbosity": 0}
                p, obj = pv.parametros_xgboost(base, v, self.ytr)
                b = xgb.train(p, xgb.QuantileDMatrix(self.Xtr, label=self.ytr, max_bin=255), num_boost_round=300, obj=obj)
                out[tau] = b.inplace_predict(self.Xte)
        return out

    def test_cobertura_nominal_lightgbm_y_xgboost(self):
        for motor in ("lightgbm", "xgboost"):
            q = self._cuantiles(motor)
            with self.subTest(motor=motor):
                cob = pv.cobertura(self.yte, q[0.05], q[0.95])
                self.assertGreater(cob, 0.86)
                self.assertLess(cob, 0.94)
                self.assertAlmostEqual(float(np.mean(self.yte <= q[0.05])), 0.05, delta=0.025)
                self.assertAlmostEqual(float(np.mean(self.yte <= q[0.95])), 0.95, delta=0.025)
                # el intervalo se adapta a la heterocedasticidad: más ancho donde |x1| es grande
                ancho = q[0.95] - q[0.05]
                self.assertGreater(ancho[np.abs(self.Xte[:, 1]) > 1.5].mean(), 1.5 * ancho[np.abs(self.Xte[:, 1]) < 0.5].mean())


if __name__ == "__main__":
    unittest.main()
