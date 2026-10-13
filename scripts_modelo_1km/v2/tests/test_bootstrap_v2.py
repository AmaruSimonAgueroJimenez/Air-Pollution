"""Pruebas de ``bootstrap_v2`` (§8; Enmienda 1, puntos 3 y 5; Complemento, puntos 1, 2 y 6), con datos simulados:

* Δ puntual, réplicas que reproducen el remuestreo por bloques, motores iguales, determinismo, semillas
  ([42, 2000, p] con B = 1.999 y [42, 3000, p] para el cambio de signo) y cobertura;
* ruido de la diferencia: Δ_r por réplica con los mismos pares, Δ̄, rango y su tasa de paso por azar (8,1 %); exige
  las 3 réplicas comunes (con 2, «no evaluada»); el apilado sin réplicas usa el máximo del ruido de sus bases; Δ̄*
  con los mismos bloques en las tres réplicas;
* segunda prueba: decide el cambio de signo del bootstrap salvaje (Webb y 9.999 sorteos con G < 12, Rademacher con
  la enumeración completa con 12 ≤ G ≤ 16, exacta contra la fuerza bruta, y Rademacher con 9.999 sorteos con
  G > 16; calibrado bajo la nula, potente con un efecto real); el jackknife CV3, contra la fórmula «deja un bloque
  fuera», sólo informa; regresión del motivo del Complemento (punto 1): con G = 15 y un bloque con el 44 % del peso,
  el cambio de signo mantiene el tamaño (≤ 6 %) y el CV3 lo excede, en simulación con semilla fija y error de Monte
  Carlo;
* Holm escalonado y su equivalencia con los intervalos percentiles escalonados (con B = 1.999, sin empates);
* influencia (quitar un bloque), Δ̄ sin cada bloque, la regla descriptiva y la serialización exacta de las sumas.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

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


def con_replicas(semilla=0, n=3000, bloques=10, efecto=0.0, ruido_replica=0.5):
    """Dos motores con tres réplicas cada uno: «a» tiene error N(0, 4 − efecto) y «c», N(0, 4); cada réplica
    agrega ruido propio de la semilla."""
    rng = np.random.default_rng(semilla)
    b = rng.integers(0, bloques, n)
    o = rng.gamma(3, 8, n) + 2 * b
    ea, ec = rng.normal(0, 4 - efecto, n), rng.normal(0, 4, n)
    p = {}
    for r in range(3):
        p[bs.nombre_replica("a", r)] = o + ea + rng.normal(0, ruido_replica, n)
        p[bs.nombre_replica("c", r)] = o + ec + rng.normal(0, ruido_replica, n)
    return b, o, p, rng.uniform(0.5, 3, n)


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
            self.assertTrue((t["replicas_del_par"] == 1).all())
            self.assertTrue(t["ruido"].isna().all())                      # una sola réplica: ruido no evaluado
            self.assertTrue(t["supera_ruido"].isna().all())

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
        self.assertTrue((t["p_bootstrap"] == 1.0).all())

    def test_determinista_con_la_semilla(self):
        b, o, p, _ = datos()
        S = bs.SumasBloques.desde_pares(b, o, p)
        t1 = bs.bootstrap_diferencias(S, [("a", "c")], replicas=300, semilla=bs.semilla_bootstrap(3))
        t2 = bs.bootstrap_diferencias(S, [("a", "c")], replicas=300, semilla=bs.semilla_bootstrap(3))
        t3 = bs.bootstrap_diferencias(S, [("a", "c")], replicas=300, semilla=bs.semilla_bootstrap(4))
        self.assertTrue(t1.equals(t2))
        self.assertFalse(t1.equals(t3))
        self.assertEqual(bs.semilla_bootstrap(3), [42, 2000, 3])           # ratificada: no cambia con B = 1.999
        self.assertEqual(bs.semilla_salvaje(3), [42, 3000, 3])             # Complemento, punto 1
        self.assertEqual((bs.REPLICAS, bs.REPLICAS_SALVAJE), (1999, 9999))
        with self.assertRaises(ValueError):
            bs.bootstrap_diferencias(S, [("a", "c")], replicas=10)
        with self.assertRaises(ValueError):
            bs.SumasBloques.desde_pares(b, o, {"x": np.where(b == 0, np.nan, o)})
        with self.assertRaises(KeyError):
            bs.bootstrap_diferencias(S, [("a", "z")], replicas=10, semilla=[1])

    def test_intervalo_cubre_la_diferencia_verdadera(self):
        """Con muchos bloques, el intervalo percentil del ΔRMSE contiene al Δ puntual y excluye 0 cuando un motor es
        claramente mejor; el p bootstrap es pequeño."""
        b, o, p, _ = datos(n=20000, bloques=60)
        p["a"] = o * np.exp(np.random.default_rng(8).normal(0, 0.1, len(o)))          # «a», claramente mejor
        S = bs.SumasBloques.desde_pares(b, o, p)
        t = bs.bootstrap_diferencias(S, [("a", "c")], replicas=2000, semilla=[5]).set_index("estadistico")
        f = t.loc["delta_rmse"]
        self.assertLess(f["ic_inf"], f["delta"])
        self.assertGreater(f["ic_sup"], f["delta"])
        self.assertTrue(bs.excluye_cero_a_favor("delta_rmse", f["ic_inf"], f["ic_sup"]))
        self.assertLess(f["p_bootstrap"], 0.01)
        self.assertEqual((f["G"], f["bloques"]), (60, 60))


class RuidoDeLaDiferenciaTests(unittest.TestCase):
    """Punto 3: Δ_r por réplica con los mismos pares, Δ̄ = media y ruido = rango de los Δ_r."""

    def test_delta_por_replica_media_y_rango(self):
        b, o, p, w = con_replicas(efecto=1.0)
        S = bs.SumasBloques.desde_pares(b, o, p, w)
        t = bs.bootstrap_diferencias(S, [("a", "c")], replicas=200, semilla=[3]).set_index("estadistico")
        for est, m in (("delta_r2", "r2"), ("delta_rmse", "rmse"), ("delta_nmb", "nmb")):
            directos = [mt.metricas(o, p[bs.nombre_replica("a", r)], w)[m] - mt.metricas(o, p[bs.nombre_replica("c", r)], w)[m]
                        for r in range(3)]
            f = t.loc[est]
            np.testing.assert_allclose([f["delta_r0"], f["delta_r1"], f["delta_r2"]], directos, rtol=0, atol=1e-10)
            self.assertAlmostEqual(f["delta"], float(np.mean(directos)), places=12)
            self.assertAlmostEqual(f["ruido"], max(directos) - min(directos), places=12)
            self.assertEqual(f["origen_ruido"], "replicas")
            self.assertEqual(f["supera_ruido"], abs(np.mean(directos)) > max(directos) - min(directos))
        self.assertEqual(int(t.loc["delta_r2", "replicas_del_par"]), 3)
        self.assertTrue(t.loc["delta_r2", "supera_ruido"])                 # efecto grande frente al ruido de semilla

    def test_ruido_exige_las_tres_replicas(self):
        """Complemento, punto 6: con dos réplicas comunes, Δ̄ es su media pero el ruido queda «no evaluado»."""
        b, o, p, w = con_replicas(semilla=14, efecto=1.0)
        del p[bs.nombre_replica("c", 2)]
        S = bs.SumasBloques.desde_pares(b, o, p, w)
        t = bs.bootstrap_diferencias(S, [("a", "c")], replicas=100, semilla=[3], estadisticos=("delta_r2",))
        f = t.iloc[0]
        self.assertEqual(int(f["replicas_del_par"]), 2)
        self.assertAlmostEqual(f["delta"], np.mean([f["delta_r0"], f["delta_r1"]]), places=12)
        self.assertTrue(np.isnan(f["delta_r2"]))
        self.assertTrue(np.isnan(f["ruido"]))
        self.assertEqual(f["origen_ruido"], "replicas_incompletas")
        self.assertIsNone(f["supera_ruido"])
        self.assertTrue(np.isnan(bs.ruido_de_las_replicas({0: 0.1, 1: 0.2})))
        self.assertAlmostEqual(bs.ruido_de_las_replicas({0: 0.1, 1: 0.25, 2: 0.2}), 0.15, places=12)
        self.assertEqual(bs.REPLICAS_EXIGIDAS, 3)

    def test_replicas_comunes(self):
        nombres = ["a", "a@r1", "a@r2", "c", "c@r2", "x~lognormal", "x~lognormal@r1"]
        self.assertEqual(bs.replicas_de(nombres, "a"), [0, 1, 2])
        self.assertEqual(bs.replicas_comunes(nombres, "a", "c"), [0, 2])
        self.assertEqual(bs.replicas_de(nombres, "x~lognormal"), [0, 1])
        self.assertEqual(bs.separar_replica("x~lognormal@r1"), ("x~lognormal", 1))
        self.assertEqual(bs.nombre_replica("x~lognormal", 2), "x~lognormal@r2")

    def test_bootstrap_de_la_media_de_las_replicas(self):
        """Δ̄* = media de los Δ*_r con los mismos bloques sorteados en las tres réplicas."""
        b, o, p, w = con_replicas(semilla=4, efecto=0.3)
        S = bs.SumasBloques.desde_pares(b, o, p, w)
        C = bs.conteos_bootstrap(len(S.bloques), 400, [7])
        d = bs.distribucion_delta(S, "a", "c", C, "delta_r2")
        manual = np.mean([bs._metricas(C, S, bs.nombre_replica("a", r))[0] - bs._metricas(C, S, bs.nombre_replica("c", r))[0]
                          for r in range(3)], axis=0)
        np.testing.assert_array_equal(d, manual)
        t = bs.bootstrap_diferencias(S, [("a", "c")], replicas=400, semilla=[7], estadisticos=("delta_r2",))
        lo, hi = np.quantile(manual, [0.025, 0.975], method="inverted_cdf")
        self.assertEqual((t.loc[0, "ic_inf"], t.loc[0, "ic_sup"]), (lo, hi))
        self.assertAlmostEqual(t.loc[0, "p_bootstrap"], min(1.0, 2 * min(np.mean(manual <= 0), np.mean(manual >= 0))))

    def test_apilado_usa_el_maximo_del_ruido_de_sus_bases(self):
        b, o, p, w = con_replicas(semilla=5, efecto=0.5)
        rng = np.random.default_rng(1)
        for r in range(3):
            p[bs.nombre_replica("lightgbm", r)] = o + rng.normal(0, 4, len(o))
        p["apilado"] = 0.5 * (p["a"] + p["c"])                         # sin réplicas
        S = bs.SumasBloques.desde_pares(b, o, p, w)
        bases = {"apilado": ["a", "c", "lightgbm"]}
        t = bs.bootstrap_diferencias(S, [("apilado", "lightgbm"), ("lightgbm", "apilado")], replicas=100, semilla=[1],
                                     estadisticos=("delta_r2",), bases_sin_replicas=bases)
        ruidos = [bs.rango(bs.deltas_por_replica(S, x, "lightgbm").values()) for x in ("a", "c")]
        for i in range(2):
            self.assertEqual(t.loc[i, "origen_ruido"], "maximo_de_las_bases")
            self.assertAlmostEqual(t.loc[i, "ruido"], max(ruidos), places=12)   # sin la base que es el rival
            self.assertEqual(t.loc[i, "replicas_del_par"], 1)
        sin = bs.bootstrap_diferencias(S, [("apilado", "lightgbm")], replicas=100, semilla=[1], estadisticos=("delta_r2",))
        self.assertEqual(sin.loc[0, "origen_ruido"], "sin_replicas")
        self.assertIsNone(sin.loc[0, "supera_ruido"])

    def test_tasa_de_paso_por_azar(self):
        """Sin diferencia real, |Δ̄| > rango(Δ_r) con 3 réplicas pasa ≈ 8,1 % de las veces (simulación)."""
        rng = np.random.default_rng(11)
        d = rng.standard_normal((100_000, 3)) * 0.01
        pasa = np.array([bs.supera_ruido(float(x.mean()), bs.rango(x)) for x in d])
        self.assertAlmostEqual(float(pasa.mean()), 0.081, delta=0.004)
        self.assertIsNone(bs.supera_ruido(0.02, float("nan")))
        self.assertTrue(np.isnan(bs.rango([0.4])))


class SegundaPruebaTests(unittest.TestCase):
    """Punto 5 y Complemento, punto 1: totales por bloque de w·(e_A² − e_B²); decide el cambio de signo del bootstrap
    salvaje y el jackknife CV3 sólo informa."""

    def test_jackknife_cv3_contra_la_formula(self):
        from scipy import stats

        b, o, p, w = con_replicas(semilla=6, bloques=9, efecto=0.4)
        S = bs.SumasBloques.desde_pares(b, o, p, w)
        sp = bs.segunda_prueba(S, "a", "c", semilla_salvaje=bs.semilla_salvaje(3))
        self.assertEqual(sp["prueba_que_decide"], "cambio_de_signo_salvaje")
        self.assertEqual((sp["salvaje"]["distribucion"], sp["salvaje"]["sorteos"]), ("webb", 9999))   # G = 9 < 12
        self.assertEqual(sp["salvaje"]["semilla"], [42, 3000, 3])
        jk = sp["jackknife"]
        self.assertAlmostEqual(sp["theta"], jk["theta"], places=14)
        d = np.mean([(p[bs.nombre_replica("a", r)] - o) ** 2 - (p[bs.nombre_replica("c", r)] - o) ** 2 for r in range(3)], axis=0)
        G = len(np.unique(b))
        theta = float(np.sum(w * d) / np.sum(w))
        loo = np.array([np.sum((w * d)[b != g]) / np.sum(w[b != g]) for g in np.unique(b)])
        var = (G - 1) / G * np.sum((loo - loo.mean()) ** 2)
        t = theta / np.sqrt(var)
        self.assertAlmostEqual(jk["theta"], theta, places=10)
        np.testing.assert_allclose(jk["theta_sin_bloque"], loo, rtol=1e-10)
        self.assertAlmostEqual(jk["ee"], float(np.sqrt(var)), places=10)
        self.assertAlmostEqual(jk["t"], t, places=8)
        self.assertEqual((jk["gl"], jk["G"]), (G - 1, G))
        self.assertAlmostEqual(jk["p"], float(2 * stats.t.sf(abs(t), G - 1)), places=10)
        self.assertTrue(theta < 0 and sp["a_favor_de_a"])                 # «a» tiene menos error
        # el signo de θ̂ es el opuesto del de ΔR² (SST común)
        self.assertLess(theta * bs.delta_medio(S, "a", "c", "delta_r2"), 0)
        self.assertTrue(np.isnan(bs.jackknife_cv3([1.0], [2.0])["p"]))
        self.assertEqual(bs.jackknife_cv3([0.0, 0.0, 0.0], [1.0, 2.0, 3.0])["p"], 1.0)

    def test_salvaje_webb_enumeracion_y_rademacher(self):
        """Pesos y sorteos según G (Complemento, punto 1): Webb y sorteos con G < 12; Rademacher con la enumeración
        completa con 12 ≤ G ≤ 16 (no usa la semilla); Rademacher y sorteos con G > 16. Los bloques sin peso no
        cuentan en G."""
        rng = np.random.default_rng(12)
        esperado = {8: ("webb", 999, 999), 11: ("webb", 999, 999), 12: ("rademacher", "enumeracion_completa", 2 ** 12),
                    16: ("rademacher", "enumeracion_completa", 2 ** 16), 17: ("rademacher", 999, 999),
                    25: ("rademacher", 999, 999)}
        for G, (dist, sorteos, vectores) in esperado.items():
            with self.subTest(G=G):
                W = rng.uniform(1, 5, G)
                T = rng.normal(0, 1, G) * W
                r = bs.cambio_de_signo_salvaje(T, W, replicas=999, semilla=[1])
                self.assertEqual((r["G"], r["distribucion"], r["sorteos"], r["vectores"]), (G, dist, sorteos, vectores))
                otra = bs.cambio_de_signo_salvaje(T, W, replicas=999, semilla=[2])
                if sorteos == "enumeracion_completa":
                    self.assertEqual(r["p"], otra["p"])                        # exacta: la semilla no entra
                    self.assertIsNone(r["semilla"])
                    self.assertEqual(r["p"], bs.cambio_de_signo_salvaje(T, W)["p"])     # ni hace falta
                else:
                    self.assertEqual(r["semilla"], [1])
                    with self.assertRaises(ValueError):                        # los sorteos exigen la semilla
                        bs.cambio_de_signo_salvaje(T, W, replicas=999)
                    self.assertEqual(r["p"], bs.cambio_de_signo_salvaje(T, W, replicas=999, semilla=[1])["p"])
        W = np.r_[rng.uniform(1, 5, 12), 0.0, 0.0]                             # dos bloques sin peso: G = 12
        self.assertEqual(bs.cambio_de_signo_salvaje(rng.normal(0, 1, 14) * W, W)["G"], 12)
        self.assertEqual(bs.esquema_salvaje(11)["distribucion"], "webb")
        self.assertTrue(bs.esquema_salvaje(12)["enumeracion_completa"] and bs.esquema_salvaje(16)["enumeracion_completa"])
        self.assertFalse(bs.esquema_salvaje(17)["enumeracion_completa"])
        with self.assertRaises(ValueError):
            bs.signos_rademacher_completos(17)

    def test_enumeracion_completa_exacta(self):
        """Con 12 ≤ G ≤ 16 el p es la fracción exacta de los 2^G vectores de signos con |t*| ≥ |t| (fuerza bruta)."""
        import itertools

        rng = np.random.default_rng(31)
        G = 12
        W = rng.uniform(1, 4, G)
        T = (rng.normal(0, 1, G) - 0.6) * W
        r = bs.cambio_de_signo_salvaje(T, W)

        def t_cv1(Tg):
            th = Tg.sum() / W.sum()
            u = Tg - th * W
            return th / np.sqrt(G / (G - 1) * (u * u).sum() / W.sum() ** 2)

        t0 = t_cv1(T)
        cuenta = sum(abs(t_cv1(np.array(e) * T)) >= abs(t0) - 1e-12 * max(1.0, abs(t0))
                     for e in itertools.product((-1.0, 1.0), repeat=G))
        self.assertAlmostEqual(r["t"], t0, places=10)
        self.assertEqual(r["p"], cuenta / 2 ** G)
        self.assertGreaterEqual(r["p"], 2 / 2 ** G)                            # la identidad y su negación cuentan
        E = bs.signos_rademacher_completos(3)
        self.assertEqual(E.shape, (8, 3))
        self.assertEqual(len({tuple(x) for x in E}), 8)
    def test_salvaje_calibrado_bajo_la_nula_y_potente(self):
        # bajo la nula (totales simétricos), p ≈ uniforme; con un efecto real, p pequeño
        rng = np.random.default_rng(13)
        ps = []
        for i in range(300):
            g = rng.integers(8, 20)
            Wg = rng.uniform(1, 5, g)
            ps.append(bs.cambio_de_signo_salvaje(rng.normal(0, 1, g) * Wg, Wg, replicas=399, semilla=[i])["p"])
        ps = np.array(ps)
        self.assertLess(abs(float(np.mean(ps <= 0.05)) - 0.05), 0.04)
        self.assertLess(abs(float(np.mean(ps)) - 0.5), 0.06)
        for G in (10, 14, 20):                                                 # Webb, enumeración y Rademacher
            Wg = rng.uniform(1, 5, G)
            fuerte = bs.cambio_de_signo_salvaje((rng.normal(0, 1, G) - 3.0) * Wg, Wg, replicas=999, semilla=[2])
            self.assertLess(fuerte["p"], 0.01, G)

    def test_decide_el_cambio_de_signo_y_no_el_jackknife(self):
        """La regla descriptiva usa el p del cambio de signo: un caso con el peso concentrado (la mitad en un bloque)
        en que el jackknife CV3 rechaza y el cambio de signo no, no se declara; el CV3 queda sólo como información."""
        G = 12
        rng = np.random.default_rng(65)
        W = np.exp(rng.normal(0, 1.5, G))
        T = rng.normal(0, 1, G) * np.sqrt(W) - 0.3 * W
        self.assertGreater(W.max() / W.sum(), 0.5)
        jk, sv = bs.jackknife_cv3(T, W), bs.cambio_de_signo_salvaje(T, W)
        self.assertLess(jk["p"], 0.05)
        self.assertGreater(sv["p"], 0.05)
        sp = {"prueba_que_decide": "cambio_de_signo_salvaje", "theta": float(T.sum() / W.sum()),
              "a_favor_de_a": True, "salvaje": sv, "jackknife": jk}
        self.assertFalse(bs.segunda_prueba_coincide(sp))
        self.assertTrue(bs.segunda_prueba_coincide({**sp, "salvaje": {**sv, "p": 0.01}}))
        self.assertFalse(bs.segunda_prueba_coincide({**sp, "salvaje": {**sv, "p": 0.01}, "a_favor_de_a": False}))
        self.assertIsNone(bs.segunda_prueba_coincide(None))

    def test_regresion_complemento_1_tamano_con_un_bloque_del_44(self):
        """Prueba de regresión del Complemento, punto 1 (el motivo de que decida el cambio de signo): con G = 15
        bloques y uno con el 44 % del peso (como la RM en LRO), bajo la nula el cambio de signo mantiene el tamaño
        (≤ 6 %) y el jackknife CV3 con t de G − 1 lo excede, más allá del error de Monte Carlo.

        Simulación con semilla fija ([42, 15, 44]) y R = 2.000 conjuntos de totales por bloque bajo la nula, con
        dependencia fuerte dentro del bloque: T_g = W_g·u_g, u_g ~ N(0, 1) independientes (la media de cada bloque no
        depende de su tamaño). Pesos: 44 % en un bloque y el resto en proporción a la población regional aproximada
        de las otras 14 regiones. Con 12 ≤ G ≤ 16 el cambio de signo enumera los 2^15 vectores: exacto, sin semilla.
        El umbral de 6 % es el 5 % nominal más dos errores de Monte Carlo con R = 2.000; el CV3 debe superarlo aun
        restándole dos de los suyos, y rechazar más que el cambio de signo sobre los mismos datos (diferencia
        pareada mayor que dos errores)."""
        G, R, ALFA, TOPE = 15, 2000, 0.05, 0.06
        resto = np.array([10.3, 12.0, 5.9, 5.4, 5.2, 4.7, 4.3, 3.4, 2.2, 1.9, 1.6, 1.3, 0.9, 0.6])
        W = np.r_[44.0, 56.0 * resto / resto.sum()]
        self.assertEqual(len(W), G)
        self.assertAlmostEqual(float(W.max() / W.sum()), 0.44, places=12)
        self.assertTrue(bs.esquema_salvaje(G)["enumeracion_completa"])
        U = np.random.default_rng([42, 15, 44]).standard_normal((R, G))
        rechaza_signo, rechaza_cv3 = np.zeros(R, dtype=bool), np.zeros(R, dtype=bool)
        for i in range(R):
            T = W * U[i]
            rechaza_signo[i] = bs.cambio_de_signo_salvaje(T, W)["p"] <= ALFA
            rechaza_cv3[i] = bs.jackknife_cv3(T, W)["p"] <= ALFA

        def error_mc(p):
            return float(np.sqrt(p * (1.0 - p) / R))

        tam_signo, tam_cv3 = float(rechaza_signo.mean()), float(rechaza_cv3.mean())
        self.assertLessEqual(ALFA + 2 * error_mc(ALFA), TOPE)                # el margen cubre el error de Monte Carlo
        self.assertLessEqual(tam_signo, TOPE, f"cambio de signo: tamaño {tam_signo:.4f} ± {error_mc(tam_signo):.4f}")
        self.assertGreater(tam_cv3 - 2 * error_mc(tam_cv3), TOPE,
                           f"CV3: tamaño {tam_cv3:.4f} ± {error_mc(tam_cv3):.4f}")
        d = rechaza_cv3.astype(float) - rechaza_signo.astype(float)
        self.assertGreater(float(d.mean()), 2 * float(d.std(ddof=1)) / np.sqrt(R))


class HolmTests(unittest.TestCase):
    def test_escalonado(self):
        h = bs.holm({"x": 0.001, "y": 0.04, "z": 0.013, "w": 0.2}, alfa=0.05)
        self.assertEqual([h[k]["declarada"] for k in "xzyw"], [True, True, False, False])
        self.assertEqual([h[k]["rango"] for k in "xzyw"], [1, 2, 3, 4])
        np.testing.assert_allclose([h[k]["alfa_holm"] for k in "xzyw"], [0.0125, 0.05 / 3, 0.025, 0.05])
        h = bs.holm({"x": 0.011, "y": float("nan")}, alfa=0.05, m=4)       # la familia es de 4 aunque falten
        self.assertTrue(h["x"]["declarada"])
        self.assertFalse(h["y"]["declarada"])
        self.assertEqual(h["y"]["rango"], 2)
        h = bs.holm({"x": 0.02, "y": 0.001}, alfa=0.05, m=4)               # 0,02 > 0,05/3: se detiene
        self.assertEqual((h["y"]["declarada"], h["x"]["declarada"]), (True, False))
        with self.assertRaises(ValueError):
            bs.holm({"a": 0.1, "b": 0.2}, m=1)

    def test_con_1999_replicas_ningun_umbral_empata(self):
        """Complemento, punto 2: con B = 1.999 ningún (α_j/2)·B es entero (α_j = 0,05/(4 − j + 1)); con 2.000, dos
        sí, y en ellos el p y el intervalo escalonado pueden discrepar."""
        alfas = [0.05 / (4 - j) for j in range(4)]
        self.assertFalse(any(abs(a / 2 * bs.REPLICAS - round(a / 2 * bs.REPLICAS)) < 1e-9 for a in alfas))
        enteros = [a for a in alfas if abs(a / 2 * 2000 - round(a / 2 * 2000)) < 1e-9]
        self.assertEqual(len(enteros), 2)                                      # 0,025 y 0,05
        # el empate con 2.000: exactamente 25 réplicas ≤ 0 (α = 0,025): p = 0,025 ≤ α, pero el IC al 97,5 % no excluye 0
        draws = np.r_[-np.ones(25), np.ones(1975)]
        self.assertLessEqual(bs.p_bootstrap(draws), 0.025)
        lo, _ = bs._percentiles(draws, 1 - 0.025)
        self.assertLessEqual(lo, 0)

    def test_equivale_a_intervalos_escalonados(self):
        """Holm sobre los p bootstrap = intervalos percentiles (``inverted_cdf``) con los niveles escalonados de
        Holm (1.999 réplicas: ningún umbral cae en un empate)."""
        rng = np.random.default_rng(7)
        for _ in range(200):
            draws = rng.normal(rng.normal(0, 2.5, 4)[:, None], 1.0, (4, 1999))
            p = {i: bs.p_bootstrap(draws[i]) for i in range(4)}
            h = bs.holm(p, 0.05, 4)
            por_ic, seguir = {}, True
            for j, i in enumerate(sorted(range(4), key=lambda k: (p[k], k))):
                lo, hi = bs._percentiles(draws[i], 1 - 0.05 / (4 - j))
                seguir = seguir and (lo > 0 or hi < 0)
                por_ic[i] = seguir
            self.assertEqual({i: h[i]["declarada"] for i in range(4)}, por_ic)


class InfluenciaYReglaTests(unittest.TestCase):
    def test_quitar_bloque_y_delta_sin_cada_bloque(self):
        b, o, p, w = con_replicas(semilla=8, bloques=6, efecto=0.6)
        etiquetas = np.array(["RM", "RV", "RVI", "RVII", "RVIII", "RIX"])[b]
        S = bs.SumasBloques.desde_pares(etiquetas, o, p, w)
        self.assertTrue(S.tiene_bloque("RM"))
        S2 = S.quitar(["RM"])
        self.assertFalse(S2.tiene_bloque("RM"))
        self.assertEqual(len(S2.bloques), 5)
        sin = bs.delta_sin_cada_bloque(S, "a", "c", "delta_r2").set_index("bloque")
        for g in np.unique(etiquetas):
            k = etiquetas != g
            directo = np.mean([mt.metricas(o[k], p[bs.nombre_replica("a", r)][k], w[k])["r2"]
                               - mt.metricas(o[k], p[bs.nombre_replica("c", r)][k], w[k])["r2"] for r in range(3)])
            self.assertAlmostEqual(sin.loc[g, "delta_sin_bloque"], directo, places=10)
        self.assertAlmostEqual(sin["fraccion_del_peso"].sum(), 1.0, places=12)
        self.assertAlmostEqual(bs.delta_medio(S2, "a", "c"), sin.loc["RM", "delta_sin_bloque"], places=12)
        self.assertAlmostEqual(S.G_efectivo, float(S.sw.sum() ** 2 / (S.sw ** 2).sum()), places=12)

    def test_regla_descriptiva_robustez_y_lpo(self):
        b, o, p, w = con_replicas(semilla=9, n=6000, bloques=14, efecto=1.5)
        etiquetas = np.array([f"B{i:02d}" for i in range(14)])[b]
        S = bs.SumasBloques.desde_pares(etiquetas, o, p, w)
        t = bs.comparar(S, [("a", "c")], replicas=400, semilla=[1], bloque_influyente="B03", semilla_salvaje=[2],
                        replicas_salvaje=499).set_index("estadistico")
        f = t.loc["delta_r2"]
        self.assertTrue(f["excluye_cero_a_favor"] and f["segunda_prueba_coincide"] and f["supera_ruido"])
        self.assertTrue(f["a_supera_b"])
        self.assertTrue(f["robusta_sin_bloque"])
        self.assertEqual(f["regla"], "superioridad_95")
        self.assertIsNone(t.loc["delta_nmb", "segunda_prueba_coincide"])     # la segunda prueba no aplica
        self.assertFalse(t.loc["delta_nmb", "a_supera_b"])                    # ΔNMB con signo no tiene dirección buena
        lpo = bs.comparar(S, [("a", "c")], replicas=100, semilla=[1], descriptivo=True)
        self.assertTrue(lpo["a_supera_b"].isna().all())
        self.assertTrue((lpo["regla"] == "descriptivo").all())
        sin_bloque = bs.comparar(S, [("a", "c")], replicas=100, semilla=[1], bloque_influyente="NO_EXISTE")
        self.assertTrue(sin_bloque["robusta_sin_bloque"].isna().all())

    def test_superioridad_de_un_solo_bloque_no_es_robusta(self):
        """Si la ventaja de «a» está sólo en un bloque muy pesado, el cambio de signo no la declara o, si la regla la
        declarara, no sobreviviría sin ese bloque."""
        rng = np.random.default_rng(10)
        n_b, por_b = 12, 300
        b = np.repeat(np.arange(n_b), por_b)
        o = rng.gamma(3, 8, len(b))
        ec = rng.normal(0, 4, len(b))
        p = {}
        for r in range(3):
            ea = ec + rng.normal(0, 0.3, len(b))
            ea[b == 0] = 0.2 * ec[b == 0]                                  # «a» mejor sólo en el bloque 0
            p[bs.nombre_replica("a", r)] = o + ea
            p[bs.nombre_replica("c", r)] = o + ec + rng.normal(0, 0.3, len(b))
        w = np.where(b == 0, 30.0, 1.0)                                     # el bloque 0 pesa mucho
        S = bs.SumasBloques.desde_pares(np.where(b == 0, "RM", b.astype(str)), o, p, w)
        t = bs.comparar(S, [("a", "c")], replicas=400, semilla=[1], bloque_influyente="RM", semilla_salvaje=[2],
                        replicas_salvaje=499, estadisticos=("delta_r2",))
        self.assertGreater(t.loc[0, "delta"], 0)
        # nunca «superior y robusta»: o no se declara (el cambio de signo protege) o no sobrevive sin la RM
        self.assertNotEqual(t.loc[0, "robusta_sin_bloque"], True)
        self.assertLess(t.loc[0, "delta_sin_bloque_influyente"], 0.25 * t.loc[0, "delta"])


class SerializacionTests(unittest.TestCase):
    def test_sumas_ida_y_vuelta_exactas(self):
        b, o, p, w = con_replicas(semilla=13)
        etiquetas = np.array([f"E{i:03d}N0{i}" for i in range(10)])[b]
        S = bs.SumasBloques.desde_pares(etiquetas, o, p, w)
        S2 = bs.SumasBloques.desde_dict(json.loads(json.dumps(S.a_dict())))
        t1 = bs.bootstrap_diferencias(S, [("a", "c")], replicas=300, semilla=[4])
        t2 = bs.bootstrap_diferencias(S2, [("a", "c")], replicas=300, semilla=[4])
        pd.testing.assert_frame_equal(t1, t2)
        self.assertEqual(list(S2.bloques), sorted(set(etiquetas)))
        d = S.a_dict()
        d["n"] = d["n"][:-1]
        with self.assertRaises(ValueError):
            bs.SumasBloques.desde_dict(d)
        self.assertEqual(S.seleccionar(["a"]).motores(), ["a"])
        with self.assertRaises(KeyError):
            S.seleccionar(["z"])


if __name__ == "__main__":
    unittest.main()
