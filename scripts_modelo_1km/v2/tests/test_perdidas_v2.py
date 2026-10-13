"""Pruebas de ``perdidas_v2``: gradientes de Huber y del cuantil, δ de Huber (MAD y Friedman) y su registro,
parámetros por variante, salvaguarda de ``min_child_weight`` (Enmienda 1, punto 1.2), cobertura nominal de los
cuantiles en un caso simulado (LightGBM y XGBoost), reordenamiento de los cuantiles y calibración conformal
agrupada (CQR) con los demás grupos y la misma exclusión (Enmienda 1, punto 9). Todo con datos simulados."""
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

    def test_delta_friedman_y_deltas_honestos(self):
        r = np.arange(-50.0, 51.0)                                            # |r| = 0 … 50
        self.assertAlmostEqual(pv.delta_friedman(r), float(np.quantile(np.abs(r), 0.9)))
        d = pv.deltas_honestos(np.append(r, np.nan))
        self.assertAlmostEqual(d["mad"], pv.delta_huber(r))
        self.assertAlmostEqual(d["friedman"], pv.delta_friedman(r))
        self.assertEqual(d["residuos"], len(r))
        self.assertAlmostEqual(d["mad_normalizado"] * pv.FACTOR_HUBER, d["mad"])
        with self.assertRaises(ValueError):
            pv.delta_friedman(np.zeros(5))

    def test_registro_huber(self):
        y = np.array([0.0, 1.0, 2.0, 10.0])
        pred = np.array([0.5, 1.0, 5.0, 2.0])                                 # |r| = 0,5; 0; 3; 8
        reg = pv.registro_huber(y, pred, delta=2.0)
        self.assertEqual(reg["filas"], 4)
        self.assertAlmostEqual(reg["fraccion_recortada"], 0.5)
        self.assertAlmostEqual(reg["perdida_final"], float(np.mean(pv.huber_perdida(pred, y, 2.0))))

    def test_variantes(self):
        v = pv.variante_de_etiqueta("q05")
        self.assertEqual((v.nombre, v.tau, v.etiqueta, v.escala), ("pinball", 0.05, "q05", "original"))
        self.assertEqual(pv.Variante("l2_log_smearing").escala, "log")
        with self.assertRaises(ValueError) as ctx:                             # Enmienda 1, punto 2: renombrada
            pv.Variante("l2_log_duan")
        self.assertIn("l2_log_smearing", str(ctx.exception))
        self.assertEqual(pv.Variante("huber").con_delta(3.0).delta, 3.0)
        h = pv.variante_de_etiqueta("huber")
        f = pv.variante_de_etiqueta("huber_friedman")
        self.assertEqual((h.regla, h.etiqueta, f.regla, f.etiqueta), ("mad", "huber", "friedman", "huber_friedman"))
        self.assertEqual(f.con_delta(4.0).regla, "friedman")
        self.assertEqual(f.con_delta(4.0).descripcion()["regla_delta"], "friedman")
        self.assertFalse(h.estima_la_media)
        self.assertFalse(pv.variante_de_etiqueta("q50").estima_la_media)
        self.assertTrue(pv.Variante("l2_original").estima_la_media)
        with self.assertRaises(ValueError):
            pv.Variante("huber", regla="otra")
        with self.assertRaises(ValueError):
            pv.Variante("l2_original", regla="mad")
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
        np.testing.assert_allclose(pv.transformar_blanco([0.0, np.e - 1], pv.Variante("l2_log_smearing")), [0.0, 1.0])

    def test_salvaguarda_de_min_child_weight(self):
        """Enmienda 1, punto 1.2: min_child_weight = 50 es la equivalencia con hessiana 1; no se combina con un
        objetivo de hessiana no constante."""
        base = {"min_child_weight": 50.0, "max_bin": 255}
        for etiqueta in ("l2_log_smearing", "l2_original", "q05", "q50", "q95"):
            pv.parametros_xgboost(base, pv.variante_de_etiqueta(etiqueta), np.arange(10.0))   # hessiana 1: pasa
        pv.parametros_xgboost(base, pv.Variante("huber", delta=2.0), np.arange(10.0))
        for objetivo in ("reg:pseudohubererror", "count:poisson", "reg:gamma", "reg:tweedie", "reg:squaredlogerror"):
            with self.subTest(objetivo=objetivo), self.assertRaises(ValueError):
                pv.verificar_hessiana_xgboost({**base, "objective": objetivo})

        def propio(pred, dtrain):
            return pred, pred                                                 # hessiana no declarada constante

        with self.assertRaises(ValueError):
            pv.verificar_hessiana_xgboost(base, propio)
        pv.verificar_hessiana_xgboost(base, pv.objetivo_xgb_huber(1.0))
        pv.verificar_hessiana_xgboost({**base, "objective": "reg:pseudohubererror"}, exigir=False)
        pv.verificar_hessiana_xgboost({"min_child_weight": 0.0, "objective": "count:poisson"})
        self.assertTrue(pv.hessiana_constante_xgboost("reg:quantileerror"))
        self.assertFalse(pv.hessiana_constante_xgboost("reg:pseudohubererror"))

    def test_recorte_en_cero_de_la_escala_original(self):
        np.testing.assert_array_equal(pv.a_escala_original([-1.0, 0.0, 2.5], pv.Variante("huber", delta=1.0)),
                                      np.array([0.0, 0.0, 2.5], dtype="float32"))
        with self.assertRaises(ValueError):
            pv.a_escala_original([1.0], pv.Variante("l2_log_smearing"))

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


class ReordenamientoTests(unittest.TestCase):
    def test_ordena_por_fila_y_cuenta_los_cruces(self):
        q05 = np.array([1.0, 5.0, 2.0, np.nan, 3.0])
        q50 = np.array([2.0, 4.0, 1.0, 1.0, 3.0])
        q95 = np.array([3.0, 6.0, 0.5, 2.0, 3.0])
        a, b, c, reg = pv.reordenar_cuantiles(q05, q50, q95)
        np.testing.assert_array_equal(a[[0, 1, 2, 4]], [1.0, 4.0, 0.5, 3.0])
        np.testing.assert_array_equal(b[[0, 1, 2, 4]], [2.0, 5.0, 1.0, 3.0])
        np.testing.assert_array_equal(c[[0, 1, 2, 4]], [3.0, 6.0, 2.0, 3.0])
        self.assertTrue(np.isnan(a[3]))                                       # con un no finito queda como estaba
        self.assertEqual((reg["filas"], reg["filas_con_cruce"]), (4, 2))
        self.assertEqual((reg["q05_mayor_que_q50"], reg["q50_mayor_que_q95"], reg["q05_mayor_que_q95"]), (2, 1, 1))
        self.assertTrue(((a <= b) & (b <= c))[[0, 1, 2, 4]].all())
        self.assertEqual(a.dtype, np.float32)

    def test_cuantil_conformal(self):
        self.assertEqual(pv.rango_conformal(9, 0.9), 9)
        self.assertEqual(pv.rango_conformal(99, 0.9), 90)
        self.assertEqual(pv.rango_conformal(100, 0.9), 91)
        e = np.arange(1.0, 100.0)                                             # 99 puntajes: el 90.º es 90
        self.assertEqual(pv.cuantil_conformal(e, 0.9), 90.0)
        self.assertEqual(pv.cuantil_conformal(np.arange(5.0), 0.9), float("inf"))     # posición 6 > n = 5
        np.testing.assert_array_equal(pv.puntaje_cqr([5.0, 0.0, 12.0], [1.0, 1.0, 1.0], [10.0, 10.0, 10.0]),
                                      [-4.0, 1.0, 2.0])


def datos_cqr(semilla=0, grupos=6, por_grupo=5, horas=400, estrechez=0.6):
    """Estaciones en grupos (pliegues) con conglomerados de dos estaciones, tres macrozonas y un intervalo base
    demasiado estrecho (``estrechez`` × el ancho verdadero)."""
    rng = np.random.default_rng(semilla)
    S = grupos * por_grupo
    est = np.repeat(np.arange(S), horas)
    pliegue = est // por_grupo
    congl_est = np.arange(S) // 2
    mz = (est % 3).astype("int64")
    hora = np.tile(np.arange(horas) % 24, S)
    fr = ((hora >= 8) & (hora <= 18)).astype("int64")
    escala = 5.0 + 3.0 * mz
    y = 40.0 + escala * rng.normal(size=len(est))
    lo = 40.0 - estrechez * 1.645 * escala
    hi = 40.0 + estrechez * 1.645 * escala
    return {"y": y, "lo": lo, "hi": hi, "est": est, "mz": mz, "fr": fr, "pliegue": pliegue, "congl": congl_est}


class CQRTests(unittest.TestCase):
    def cqr(self, d, excluidas=None, temporal=False, **kw):
        excl = excluidas if excluidas is not None else {
            int(k): np.unique(d["est"][d["pliegue"] == k]) for k in np.unique(d["pliegue"])}
        return pv.cqr_fuera_de_pliegue(d["y"], d["lo"], d["hi"], d["est"], d["mz"], d["fr"], d["pliegue"], excl,
                                       temporal, d["congl"], **kw)

    def test_cobertura_calibrada(self):
        d = datos_cqr()
        lo, hi, Q, nivel, reg, res = self.cqr(d)
        crudo = pv.cobertura(d["y"], d["lo"], d["hi"])
        cal = pv.cobertura(d["y"], lo, hi)
        self.assertLess(crudo, 0.8)
        self.assertAlmostEqual(cal, 0.9, delta=0.02)
        self.assertTrue((Q > 0).all())                                         # el intervalo base era estrecho
        self.assertEqual(res["filas_por_nivel"]["macrozona_franja"], len(d["y"]))
        self.assertEqual(len(reg), 6 * 3 * 2)                                  # pliegue × macrozona × franja
        self.assertEqual(set(r["nivel"] for r in reg), {"macrozona_franja"})
        np.testing.assert_allclose(lo, np.maximum(d["lo"] - Q, 0.0).astype("float32"), rtol=1e-6)

    def test_no_usa_el_propio_grupo_ni_los_excluidos(self):
        d = datos_cqr(semilla=1)
        excl = {int(k): np.unique(d["est"][d["pliegue"] == k]) for k in range(6)}
        excl[0] = np.append(excl[0], [5])                                      # el pliegue 0 excluye además a la 5
        _, _, Q0, _, _, _ = self.cqr(d, excl)
        k0 = d["pliegue"] == 0
        for perturbadas in (k0, d["est"] == 5):                                # el propio grupo y una excluida
            d2 = {**d, "y": np.where(perturbadas, d["y"] + 1000.0, d["y"])}
            _, _, Q2, _, _, _ = self.cqr(d2, excl)
            np.testing.assert_array_equal(Q0[k0], Q2[k0])
        d3 = {**d, "y": np.where(d["est"] == 6, d["y"] + 1000.0, d["y"])}       # una estación permitida sí cuenta
        _, _, Q3, _, _, _ = self.cqr(d3, excl)
        self.assertFalse(np.array_equal(Q0[k0], Q3[k0]))
        with self.assertRaises(ValueError):                                    # la prueba fuera del excluido
            self.cqr(d, {**excl, 0: np.array([0])})

    def test_respaldo_honesto(self):
        d = datos_cqr(semilla=2, grupos=4, por_grupo=4, horas=60)
        mz = d["mz"].copy()
        mz[np.isin(d["est"], [0, 1, 4, 5])] = 7                                # macrozona 7: 2 conglomerados
        d = {**d, "mz": mz}
        _, _, _, nivel, reg, res = self.cqr(d)
        del nivel
        clave7 = [r for r in reg if r["clave"].startswith("7|") and r["k"] in (0, 1)]
        self.assertTrue(clave7)
        for r in clave7:                                                       # en los demás sólo queda 1 conglomerado
            self.assertEqual(r["nivel"], "franja")
            self.assertLess(r["conglomerados_clave"], 3)
        _, _, Qb, nivel_b, reg_b, _ = self.cqr(d, minimo_filas=10_000)         # ni la franja ni el global alcanzan
        self.assertEqual(set(r["nivel"] for r in reg_b), {"sin_calibracion"})
        self.assertTrue((Qb == 0).all())
        self.assertTrue((nivel_b == pv.NIVELES_CQR.index("sin_calibracion")).all())
        _, _, _, _, reg_g, _ = self.cqr(d, minimo_conglomerados=10 ** 6, minimo_filas=200)
        self.assertIn("franja", {r["nivel"] for r in reg_g})
        _, _, _, _, reg_gl, _ = self.cqr(d, minimo_conglomerados=10 ** 6, minimo_filas=700)
        self.assertEqual({r["nivel"] for r in reg_gl}, {"global"})
        self.assertEqual(sum(res["filas_por_nivel"].values()), len(d["y"]))

    def test_lpo_excluye_solo_el_propio_cuatrienio(self):
        d = datos_cqr(semilla=3)
        periodo = np.tile(np.arange(400) // 100, 30)                           # cuatro «cuatrienios» por estación
        d = {**d, "pliegue": periodo}
        lo, hi, Q, _, reg, _ = self.cqr(d, excluidas={}, temporal=True)
        self.assertAlmostEqual(pv.cobertura(d["y"], lo, hi), 0.9, delta=0.02)
        k0 = periodo == 0
        d2 = {**d, "y": np.where(k0, d["y"] + 1000.0, d["y"])}
        _, _, Q2, _, _, _ = self.cqr(d2, excluidas={}, temporal=True)
        np.testing.assert_array_equal(Q[k0], Q2[k0])
        self.assertFalse(np.array_equal(Q[~k0], Q2[~k0]))


if __name__ == "__main__":
    unittest.main()
