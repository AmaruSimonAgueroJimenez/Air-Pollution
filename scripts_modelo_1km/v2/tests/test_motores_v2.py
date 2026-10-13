"""Pruebas de ``motores_v2``: recetas desde la configuración, permutación común con topes anidados, determinismo de
cada motor del eje A, validación agrupada de la MLP, diseño del LME aprendido en el pliegue, GWR/RK/IDW por
estadísticos suficientes contra una implementación directa, pesos del apilado en el símplex y pliegues internos."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))
sys.path.insert(0, str(V2 / "tests"))
import _sintetico_v2 as sx  # noqa: E402
import motores_v2 as mv  # noqa: E402
import perdidas_v2 as pv  # noqa: E402
from vecindario_v2 import Vecindario  # noqa: E402


class RecetasTests(unittest.TestCase):
    def test_recetas_del_contrato_y_provisionales(self):
        import json
        cfg = json.loads((V2 / "config_v2.json").read_text(encoding="utf-8"))
        r = mv.recetas_de(cfg)
        g = r["lightgbm"]["params"]
        self.assertEqual((g["deterministic"], g["force_col_wise"], g["num_threads"], g["num_leaves"]), (True, True, 12, 127))
        self.assertEqual(r["lightgbm"]["num_boost_round"], 800)
        x = r["xgboost"]["params"]
        self.assertEqual((x["colsample_bytree"], x["min_child_weight"], x["max_depth"], x["max_bin"], x["nthread"],
                          x["seed"], x["tree_method"], x["grow_policy"]), (0.8, 50.0, 0, 255, 12, 42, "hist", "lossguide"))
        self.assertEqual(r["random_forest"]["params"]["n_jobs"], 12)
        self.assertEqual((r["mlp"]["fraccion_validacion"], r["mlp"]["n_iter_no_change"]), (0.1, 10))
        self.assertEqual((r["gp"]["tope"], r["lme"]["tope"], r["lineales"]["tope"], r["N_comun"]), (3000, 300000, None, 750000))
        self.assertEqual(r["alertas"]["params"]["alpha"], 0.8)
        self.assertNotIn("bagging_fraction", r["alertas"]["params"])
        self.assertEqual(r["apilado"]["bases"], list(mv.MOTORES_EJE_A))
        self.assertEqual(r["curvas"]["lightgbm"], [300000, 750000, 1500000, None])
        r6 = mv.recetas_de(cfg, hilos=6)
        self.assertEqual((r6["lightgbm"]["params"]["num_threads"], r6["xgboost"]["params"]["nthread"]), (6, 6))
        with self.assertRaises(ValueError):
            mv.recetas_de(cfg, hilos=13)


class FilasTests(unittest.TestCase):
    def test_permutacion_comun_y_topes_anidados(self):
        disp = np.flatnonzero(np.random.default_rng(0).random(10000) < 0.7)
        orden = mv.permutacion(disp, mv.semilla_permutacion(3))
        self.assertEqual(mv.semilla_permutacion(3), [42, 3])
        self.assertEqual(mv.semilla_permutacion(3, 2), [42, 3, 2])
        np.testing.assert_array_equal(np.sort(orden), disp)
        topes = [100, 500, 2000, None]
        filas = [mv.filas_tope(orden, t) for t in topes]
        for chico, grande in zip(filas, filas[1:]):
            self.assertTrue(np.isin(chico, grande).all())                  # anidados
        self.assertTrue(all((np.diff(f) > 0).all() for f in filas))       # ordenados y sin repetir
        np.testing.assert_array_equal(filas[-1], disp)
        np.testing.assert_array_equal(mv.filas_tope(orden, 10 ** 9), disp)  # menos disponibles que el tope: todas
        np.testing.assert_array_equal(mv.filas_tope(mv.permutacion(disp, [42, 3]), 500), filas[1])   # la misma
        self.assertFalse(np.array_equal(mv.filas_tope(mv.permutacion(disp, [42, 4]), 500), filas[1]))
        mascara = np.zeros(10000, dtype=bool)
        mascara[::2] = True
        con = mv.filas_tope(orden, 300, mascara)
        self.assertTrue(mascara[con].all())
        self.assertTrue(np.array_equal(con, np.sort(orden[mascara[orden]][:300])))  # la misma permutación, filtrada
        with self.assertRaises(ValueError):
            mv.permutacion(disp[::-1], [42, 0])
        self.assertEqual(mv.semilla_motor(42, 2), 2042)


def datos_eje_a(n=3000, semilla=0):
    rng = np.random.default_rng(semilla)
    X = rng.normal(size=(n, 6)).astype("float32")
    X[rng.random((n, 6)) < 0.05] = np.nan
    y = np.exp(2 + 0.5 * np.nan_to_num(X[:, 0]) + rng.normal(0, 0.3, n))
    est = np.repeat(np.array([f"S{i}" for i in range(10)]), n // 10)
    return X, y, est


class EjeATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recetas = mv.recetas_de(sx.config_pequena(), hilos=2)
        cls.X, cls.y, cls.est = datos_eje_a()

    def test_cada_motor_es_determinista(self):
        for motor in (*mv.MOTORES_EJE_A, "alertas"):
            with self.subTest(motor=motor):
                p = [mv.crear_modelo(motor, self.recetas, pv.Variante("l2_log_duan"), 0, k=3)
                     .ajustar(self.X, self.y, self.est).predecir(self.X[:500]) for _ in range(2)]
                self.assertTrue(np.array_equal(p[0], p[1]))
                self.assertTrue(np.isfinite(p[0]).all())
        for etiqueta in ("l2_original", "q05", "q95"):
            for motor in mv.MOTORES_PERDIDAS:
                v = pv.variante_de_etiqueta(etiqueta)
                p = [mv.crear_modelo(motor, self.recetas, v, 0).ajustar(self.X, self.y).predecir(self.X[:300]) for _ in range(2)]
                self.assertTrue(np.array_equal(p[0], p[1]), f"{motor} {etiqueta}")

    def test_replicas_cambian_la_semilla_del_motor(self):
        m0 = mv.crear_modelo("lightgbm", self.recetas, pv.Variante("l2_log_duan"), 0, replica=0)
        m1 = mv.crear_modelo("lightgbm", self.recetas, pv.Variante("l2_log_duan"), 0, replica=1)
        self.assertEqual((m0.params["seed"], m1.params["seed"]), (42, 1042))
        rf = mv.crear_modelo("random_forest", self.recetas, pv.Variante("l2_log_duan"), 0, replica=2, k=5)
        self.assertEqual(rf.semilla, 42 + 5 + 2000)
        with self.assertRaises(ValueError):
            mv.crear_modelo("random_forest", self.recetas, pv.Variante("l2_original"), 0)

    def test_huber_toma_delta_del_ajuste_cuadratico(self):
        m = mv.crear_modelo("lightgbm", self.recetas, pv.Variante("l2_original"), 0).ajustar(self.X, self.y)
        d, info = mv.delta_desde_ajuste(m, self.X, self.y)
        res = self.y - m.predecir(self.X)
        self.assertAlmostEqual(d, pv.delta_huber(res))
        self.assertEqual(info["residuos_in_sample"], len(self.y))
        h = mv.crear_modelo("xgboost", self.recetas, pv.Variante("huber", delta=d), 0).ajustar(self.X, self.y)
        self.assertTrue(h.info["objetivo_propio"].startswith("huber_lightgbm"))

    def test_mlp_valida_agrupado_por_estacion(self):
        m = mv.crear_modelo("mlp", self.recetas, pv.Variante("l2_log_duan"), 0, k=1).ajustar(self.X, self.y, self.est)
        i = m.info
        self.assertTrue(i["validacion_agrupada"])
        self.assertEqual(len(i["estaciones_validacion"]), 1)                  # 10 % de 10 estaciones
        self.assertEqual(i["filas_validacion"], int(np.isin(self.est, i["estaciones_validacion"]).sum()))
        self.assertGreaterEqual(i["mejor_epoca"], 1)
        una = mv.crear_modelo("mlp", self.recetas, pv.Variante("l2_log_duan"), 0).ajustar(self.X, self.y,
                                                                                          np.full(len(self.y), "S"))
        self.assertFalse(una.info["validacion_agrupada"])                     # una sola estación: sin validación
        z = m.predecir(self.X[:50])
        self.assertTrue(((z >= m.lo) & (z <= m.hi)).all())                   # salida recortada a q0,005–q0,99

    def test_salida_de_alertas(self):
        np.testing.assert_allclose(mv.salida_alertas([-1.0, 0.0, 1.0]), np.array([0.0, 0.0, np.e - 1], dtype="float32"),
                                   rtol=1e-6)


class EjeBTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.panel = sx.panel_sintetico(dias=75)                       # cruza a 2020: GEOS-CF con 19 % de cobertura
        cls.feats = list(sx.PREDICTORES)
        cls.X = cls.panel[cls.feats].to_numpy("float32")
        cls.y = cls.panel["obs"].to_numpy("float64")
        cls.recetas = mv.recetas_de(sx.config_pequena(), hilos=2)

    def test_diseno_del_lme_se_aprende_en_el_entrenamiento(self):
        d = pd.DataFrame(self.X, columns=self.feats)
        al_azar = np.random.default_rng(0).random(len(d)) < 0.5                # el entrenamiento incluye 2020
        tr, te = d[al_azar], d[~al_azar]
        dl = mv.DisenoLineal("pm25").ajustar(tr)
        base = mv.base_lineal(tr, "pm25", True)
        self.assertAlmostEqual(dl.medianas["cams_pm25"], float(base["cams_pm25"].median()))
        self.assertIn("gcf_pm25", dl.indicadoras)                             # GEOS-CF falta en 2019
        A = dl.transformar(tr)
        np.testing.assert_allclose(A.mean(axis=0), 0, atol=1e-9)
        np.testing.assert_allclose(A.std(axis=0, ddof=1), 1, atol=1e-9)
        B = dl.transformar(te)                                                # la prueba usa lo del entrenamiento
        self.assertEqual(B.shape[1], A.shape[1])
        tr2 = tr.copy()
        tr2["cams_pm25"] = np.nan                                             # sin cobertura en el entrenamiento
        self.assertIn("cams_pm25", mv.DisenoLineal("pm25").ajustar(tr2).descartadas)

    def test_gp_y_lme(self):
        filas = np.arange(0, len(self.y), 7)[:400]
        gp = mv.ModeloGP(self.recetas["gp"], "pm25", self.feats, 42, 2).ajustar(self.X[filas], self.y[filas])
        self.assertTrue(np.isfinite(gp.predecir(self.X[:1000])).all())
        self.assertIn("m2_pm25", gp.info["predictores"])
        lme = mv.ModeloLME(self.recetas["lme"], "pm25", self.feats).ajustar(self.X[:3000], self.y[:3000])
        z = lme.predecir(self.X[3000:4000])
        self.assertTrue(np.isfinite(z).all())
        self.assertEqual(lme.info["pendiente_aleatoria"], "m2_pm25")
        self.assertIsInstance(lme.info["advertencias"], list)


def lineales_directos(pol, feats, X, y, est, ven, D, ov, ent, pru, k_vec=12, ridge=1e-6):
    """Implementación directa, fila a fila, de GWR/RK/IDW de la v1 con el diseño aprendido en el entrenamiento del
    pliegue (medianas, indicadoras > 5 %, cobertura ≥ 5 %, media y desviación poblacional)."""
    d = pd.DataFrame({c: X[:, feats.index(c)] for c in feats})
    base = mv.base_lineal(d, pol, en_log=False)
    base["obs_vec"] = np.asarray(ov, dtype="float64")
    cols, ind = [], []
    for c in mv.columnas_base_lineal(pol, False):
        v = base[c].to_numpy()
        falta = np.isnan(v[ent])
        if 1 - falta.mean() < mv.COBERTURA_MIN:
            continue
        m = float(np.nanmedian(v[ent]))
        cols.append(np.where(np.isnan(v), m, v))
        if falta.mean() > mv.FALTANTE_INDICADORA:
            ind.append(np.isnan(v).astype("float64"))
    nombres_ind = len(ind)
    M = np.column_stack(cols + ind + [X[:, feats.index(c)].astype("float64") for c in mv.CALENDARIO])
    mu, sd = M[ent].mean(axis=0), M[ent].std(axis=0)
    sd = np.where(sd > 0, sd, 1.0)
    Xd = np.column_stack([np.ones(len(M)), (M - mu) / sd])
    indic = list(range(1 + len(cols), 1 + len(cols) + nombres_ind))
    unidad = est.astype("int64") * 1000 + ven
    U = np.unique(unidad)
    sums = {u: (Xd[unidad == u].T @ Xd[unidad == u], Xd[unidad == u].T @ y[unidad == u], Xd[unidad == u].sum(axis=0),
                float((unidad == u).sum()), float(y[unidad == u].sum())) for u in U}
    ent_u = [u for u in U if ent[unidad == u].all()]
    pru_u = [u for u in U if pru[unidad == u].all()]
    A = sum(sums[u][0] for u in ent_u)
    b = sum(sums[u][1] for u in ent_u)
    sx_ = sum(sums[u][2] for u in ent_u)
    n_tr = sum(sums[u][3] for u in ent_u)
    beta = mv.resolver_normales(A, b, sx_, n_tr, ridge=ridge)
    S = D.shape[0]
    n_e, r_e = np.zeros(S), np.zeros(S)
    for u in ent_u:
        n_e[u // 1000] += sums[u][3]
        r_e[u // 1000] += sums[u][4] - sums[u][2] @ beta
    con = np.flatnonzero(n_e > 0)
    r_med = r_e[con] / n_e[con]
    Dt = D[np.ix_(con, con)]
    iu = np.triu_indices(len(con), k=1)
    c0, c1, a = mv.variograma_exponencial(Dt[iu], 0.5 * (r_med[iu[0]] - r_med[iu[1]]) ** 2) if len(con) > 2 else (1.0, 1e-9, 1.0)
    K = np.zeros((len(con) + 1, len(con) + 1))
    K[:-1, :-1] = c1 * np.exp(-Dt / a) + np.eye(len(con)) * (c0 + 1e-9)
    K[-1, :-1] = K[:-1, -1] = 1.0
    fijos = {j: float(beta[j]) for j in indic}
    media_tr = sum(sums[u][4] for u in ent_u) / n_tr
    out = {m: np.full(len(y), np.nan) for m in ("gwr", "rk", "idw")}
    for s in np.unique([u // 1000 for u in pru_u]):
        lam = np.linalg.solve(K, np.append(c1 * np.exp(-D[s, con] / a), 1.0))[:-1]
        delta = float(lam @ r_med)
        h = np.sort(D[s, con])[min(k_vec, len(con)) - 1] + 1e-9
        w = {u: np.exp(-(D[s, u // 1000] / h) ** 2) for u in ent_u}
        beta_s = mv.resolver_normales(sum(w[u] * sums[u][0] for u in ent_u), sum(w[u] * sums[u][1] for u in ent_u),
                                      sum(w[u] * sums[u][2] for u in ent_u), sum(w[u] * sums[u][3] for u in ent_u),
                                      fijos, ridge=ridge)
        for u in pru_u:
            if u // 1000 != s:
                continue
            f = unidad == u
            out["gwr"][f] = np.clip(Xd[f] @ beta_s, 0, None)
            out["rk"][f] = np.clip(Xd[f] @ beta + delta, 0, None)
            out["idw"][f] = np.where(np.isfinite(ov[f]), ov[f], media_tr)
    return out


class LinealesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        panel = sx.panel_sintetico(dias=75)
        cls.panel = panel
        cls.feats = list(sx.PREDICTORES)
        cls.X = panel[cls.feats].to_numpy("float32")
        cls.y = panel["obs"].to_numpy("float64")
        cls.vec = Vecindario("pm25", panel["estacion"], panel["ts_utc"].to_numpy(), panel["obs"].to_numpy(),
                             sx.coordenadas(), anio=panel["anio"].to_numpy(), hilos=1)
        cls.ven = (panel["anio"].to_numpy() - 2000) // 4
        cls.lin = mv.LinealesPorUnidades("pm25", cls.feats, cls.X, cls.y, cls.vec.js, cls.ven, cls.vec.D)

    def comparar(self, pliegue, prot):
        rec = self.vec.para_pliegue(pliegue, prot, registrar=False)
        pred, info = self.lin.ajustar_predecir(rec.obs_vec, rec.entrenamiento, rec.prueba)
        ref = lineales_directos("pm25", self.feats, self.X, self.y, self.vec.js, self.ven, self.vec.D,
                                rec.obs_vec.astype("float64"), rec.entrenamiento, rec.prueba)
        prueba = np.flatnonzero(rec.prueba)
        for m in mv.MOTORES_LINEALES:
            # float32 en la salida: la diferencia con el cálculo directo es sólo de redondeo
            np.testing.assert_allclose(pred[m], ref[m][prueba].astype("float32"), rtol=1e-6, atol=1e-5,
                                       err_msg=f"{prot} {m}")
        return info

    def test_igual_a_la_implementacion_directa(self):
        man = sx.manifiesto_sintetico(self.panel)["contaminantes"]["pm25"]["protocolos"]
        for prot, k in (("LOSO-D", 0), ("LBO-10", 0), ("LRO", 1), ("LPO", 0), ("LPO", 1)):
            with self.subTest(prot=prot, k=k):
                info = self.comparar(man[prot]["pliegues"][k], prot)
                self.assertEqual(info["columnas_diseno"][0], "constante")
                if prot == "LPO" and k == 1:                                   # entrena sólo con 2019: sin GEOS-CF
                    self.assertIn("gcf_pm25", info["descartadas_por_cobertura"])
                elif prot == "LPO":                                            # entrena sólo con 2020: completos
                    self.assertEqual(info["indicadoras"], [])
                else:
                    self.assertIn("gcf_pm25", info["indicadoras"])

    def test_unidades_partidas_son_un_error(self):
        ent = np.zeros(len(self.y), dtype=bool)
        ent[: len(ent) // 2] = True
        with self.assertRaises(ValueError):
            self.lin.ajustar_predecir(self.panel["obs_vec"].to_numpy(), ent, ~ent)


class ApiladoTests(unittest.TestCase):
    def test_pesos_en_el_simplex_exactos(self):
        rng = np.random.default_rng(0)
        Z = rng.normal(size=(2000, 3))
        y = Z @ np.array([0.2, 0.5, 0.3])
        np.testing.assert_allclose(mv.pesos_simplex(Z, y), [0.2, 0.5, 0.3], atol=1e-10)
        y2 = Z @ np.array([1.5, -0.3, -0.2]) + rng.normal(0, 0.1, 2000)          # el óptimo libre sale del símplex
        w = mv.pesos_simplex(Z, y2)
        self.assertTrue((w >= 0).all())
        self.assertAlmostEqual(float(w.sum()), 1.0, places=12)
        malla = [(a, b, 1 - a - b) for a in np.linspace(0, 1, 201) for b in np.linspace(0, 1, 201) if a + b <= 1 + 1e-12]
        mejor = min(malla, key=lambda v: np.sum((y2 - Z @ np.array(v)) ** 2))
        self.assertLessEqual(np.sum((y2 - Z @ w) ** 2), np.sum((y2 - Z @ np.array(mejor)) ** 2) + 1e-9)

    def test_pliegues_internos(self):
        g = ["RX", "RI", "RV", "RM", "RII", "RIII", "RIV"]
        a = mv.pliegues_internos(g, 4, 5)
        self.assertEqual(a, mv.pliegues_internos(list(reversed(g)), 4, 5))     # no depende del orden de entrada
        self.assertEqual(sorted(x for p in a for x in p), sorted(g))
        self.assertEqual(len(a), 5)
        self.assertEqual(len(mv.pliegues_internos(["A", "B"], 0, 5)), 2)
        self.assertNotEqual(a, mv.pliegues_internos(g, 5, 5))
        with self.assertRaises(ValueError):
            mv.pliegues_internos(["A"], 0, 5)


if __name__ == "__main__":
    unittest.main()
