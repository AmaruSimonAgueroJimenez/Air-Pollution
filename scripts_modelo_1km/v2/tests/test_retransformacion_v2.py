"""Pruebas de ``retransformacion_v2`` (§5 y Enmienda 1, punto 2), con datos sintéticos:

* las formas: el smearing es log(Σeʳ/n) por clave; ½·σ² es la sensibilidad fija; los nombres viejos se rechazan;
* el respaldo honesto por unidades independientes cae como se especifica: la clave macrozona × franja exige
  3 conglomerados LOSO-D (las gemelas cuentan una vez), 2 grupos del protocolo y 100 filas; luego la franja y el
  global de los demás (100 filas) y, al final, sin corrección;
* nunca el propio grupo, la misma exclusión del protocolo (también en el conteo) y LPO;
* el registro por pliegue (nivel, estaciones que aportan, conglomerados, grupos, motivo y factor);
* la sensibilidad con OOF interno (smearing, que informa también ½·σ²) y la tabla de producción;
* una referencia directa, escrita aparte, contra la implementación por sumas.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))
import retransformacion_v2 as rt  # noqa: E402

CFG = json.loads((V2 / "config_v2.json").read_text(encoding="utf-8"))
S, L = rt.SMEARING, rt.LOGNORMAL


def smearing(r) -> float:
    return float(np.log(np.mean(np.exp(np.asarray(r, dtype="float64")))))


def lognormal(r) -> float:
    return 0.5 * float(np.var(np.asarray(r, dtype="float64")))          # ddof = 0, como produccion.py:153


# Estación: (pliegue = grupo del protocolo, macrozona, conglomerado LOSO-D). 2–3 y 5–6 son gemelas.
ESTACIONES = {0: (0, 1, 0), 1: (0, 1, 1), 2: (1, 1, 2), 3: (1, 1, 2), 4: (2, 1, 3),
              5: (3, 2, 4), 6: (3, 2, 4), 7: (3, 2, 5), 11: (3, 2, 9), 8: (4, 2, 6), 9: (5, 3, 7)}
NOMBRES = np.array([f"S{i}" for i in range(12)], dtype=object)


def protocolo(semilla=0, filas=150):
    """Protocolo espacial tipo LRO: cada estación tiene ``filas`` filas nocturnas (03 h) y otras tantas diurnas
    (12 h), con residuos log de media y dispersión propias (el smearing y ½·σ² difieren)."""
    rng = np.random.default_rng(semilla)
    partes = []
    for e, (k, mz, _) in ESTACIONES.items():
        for hora in (3, 12):
            r = rng.normal(0.05 * e - 0.2, 0.15 + 0.05 * (e % 4), filas)
            partes.append((np.full(filas, e), np.full(filas, k), np.full(filas, mz), np.full(filas, hora), r))
    est, k, mz, hora, r = (np.concatenate(c) for c in zip(*partes))
    y = np.expm1(np.full(len(r), 3.0))
    z = np.log1p(y) - r
    congl = np.full(12, -1, dtype="int64")
    for e, (_, _, c) in ESTACIONES.items():
        congl[e] = c
    excl = {kk: sorted(e for e, (k2, _, _) in ESTACIONES.items() if k2 == kk) for kk in range(6)}
    return dict(est=est, k=k, mz=mz, hora=hora, y=y, z=z, res=np.log1p(y) - z, congl=congl, excl=excl)


def correr(d, excl=None, regla=None, temporal=False, formas=rt.FORMAS, nombres=None):
    return rt.fuera_de_pliegue(d["z"], d["y"], d["est"], d["mz"], d["hora"], d["k"], excl or d["excl"], temporal,
                               conglomerado_de_estacion=d["congl"], formas=formas, regla=regla,
                               nombres_estacion=nombres)


def referencia(d, excl, temporal, regla: rt.ReglaRespaldo):
    """Referencia directa (sin unidades ni sumas): nivel y ajuste de cada forma por fila."""
    res, est, k, mz, congl = d["res"], d["est"], d["k"], d["mz"], d["congl"]
    fr = rt.franja(d["hora"])
    nivel = np.empty(len(res), dtype=object)
    adj = {S: np.full(len(res), np.nan), L: np.full(len(res), np.nan)}
    for kk in np.unique(k):
        otros = k != kk
        if not temporal:
            otros &= ~np.isin(est, excl.get(int(kk), []))
        for m in np.unique(mz[k == kk]):
            for f in (0, 1):
                sel = (k == kk) & (mz == m) & (fr == f)
                if not sel.any():
                    continue
                clave = otros & (mz == m) & (fr == f)
                ok_clave = (clave.sum() >= regla.minimo_filas_clave
                            and len(np.unique(congl[est[clave]])) >= regla.minimo_conglomerados
                            and len(np.unique(k[clave])) >= regla.minimo_grupos)
                if ok_clave:
                    usado, nv = clave, "macrozona_franja"
                elif (otros & (fr == f)).sum() >= regla.minimo_filas:
                    usado, nv = otros & (fr == f), "franja"
                elif otros.sum() >= regla.minimo_filas:
                    usado, nv = otros, "global"
                else:
                    usado, nv = None, "sin_correccion"
                nivel[sel] = nv
                adj[S][sel] = 0.0 if usado is None else smearing(res[usado])
                adj[L][sel] = 0.0 if usado is None else lognormal(res[usado])
    return nivel, adj


class FormasTests(unittest.TestCase):
    def test_franja_y_clave_de_la_v1(self):
        np.testing.assert_array_equal(rt.franja([0, 7, 8, 12, 18, 19, 23]), [0, 0, 1, 1, 1, 0, 0])
        self.assertEqual(rt.clave(2, 1), "2|diurna")

    def test_smearing_es_log_de_la_media_de_e_a_la_r_y_lognormal_medio_sigma2(self):
        r = np.random.default_rng(1).normal(0.2, 0.5, 1000)
        sumas = (len(r), r.sum(), (r * r).sum(), np.exp(r).sum())
        self.assertAlmostEqual(float(rt.ajuste_desde_sumas(*sumas, S)), float(np.log(np.exp(r).sum() / len(r))), places=12)
        self.assertAlmostEqual(float(rt.ajuste_desde_sumas(*sumas)), smearing(r), places=12)      # primaria por omisión
        self.assertAlmostEqual(float(rt.ajuste_desde_sumas(*sumas, L)), lognormal(r), places=12)
        np.testing.assert_allclose(rt.retransformar([1.0], [0.5]), np.array([np.expm1(1.5)], dtype="float32"))
        self.assertAlmostEqual(float(rt.factor(0.25)), float(np.exp(0.25)))

    def test_el_smearing_corrige_ademas_el_sesgo_medio(self):
        r = np.random.default_rng(2).normal(0.0, 0.4, 5000)
        sumas = lambda x: (len(x), x.sum(), (x * x).sum(), np.exp(x).sum())          # noqa: E731
        d_s = float(rt.ajuste_desde_sumas(*sumas(r + 0.3), S) - rt.ajuste_desde_sumas(*sumas(r), S))
        d_l = float(rt.ajuste_desde_sumas(*sumas(r + 0.3), L) - rt.ajuste_desde_sumas(*sumas(r), L))
        self.assertAlmostEqual(d_s, 0.3, places=9)
        self.assertAlmostEqual(d_l, 0.0, places=9)

    def test_nombres_retirados_y_desconocidos(self):
        for viejo, nuevo in (("duan", L), ("smearing", S)):
            with self.assertRaisesRegex(ValueError, nuevo):
                rt.validar_forma(viejo)
            with self.assertRaises(ValueError):
                rt.ajuste_desde_sumas(10, 1.0, 1.0, 10.0, viejo)
        with self.assertRaises(ValueError):
            rt.validar_forma("lognormal")

    def test_formas_y_regla_iguales_a_la_configuracion(self):
        self.assertEqual(rt.formas_de_config(CFG), {"primaria": S, "sensibilidad_fija": L, "sensibilidad": S})
        self.assertEqual((rt.FORMA_PRIMARIA, rt.FORMA_SENSIBILIDAD_FIJA, rt.FORMA_SENSIBILIDAD_INTERNA), (S, L, S))
        self.assertEqual(rt.regla_de_config(CFG), rt.ReglaRespaldo(100, 3, 2, 100))
        self.assertEqual(rt.regla_de_config(CFG), rt.ReglaRespaldo())
        anteriores = CFG["retransformacion"]["formas"]["nombres_anteriores"]
        self.assertEqual({k: anteriores[k] for k in rt.NOMBRES_RETIRADOS}, rt.NOMBRES_RETIRADOS)
        self.assertEqual(set(rt.FORMAS), {k for k in CFG["retransformacion"]["formas"] if k in (S, L)})

    def test_valor_config(self):
        self.assertEqual(rt.valor_config({"estado": "ratificado (Enmienda 1)", "valor": 3}), 3)
        self.assertEqual(rt.valor_config({"estado": "pendiente", "provisional": 4}), 4)
        self.assertEqual(rt.valor_config(5), 5)
        with self.assertRaises(ValueError):
            rt.valor_config({"estado": "pendiente"})
        with self.assertRaises(ValueError):
            rt.valor_config("pendiente")


class RespaldoHonestoTests(unittest.TestCase):
    def setUp(self):
        self.d = protocolo()

    def adj_esperado(self, k, mz, hora, nivel, excl=None):
        d = self.d
        fr = rt.franja(d["hora"])
        f = int(rt.franja([hora])[0])
        otros = (d["k"] != k) & ~np.isin(d["est"], (excl or d["excl"])[k])
        usado = {"macrozona_franja": otros & (d["mz"] == mz) & (fr == f), "franja": otros & (fr == f),
                 "global": otros}[nivel]
        return smearing(d["res"][usado]), lognormal(d["res"][usado])

    def test_primaria_y_sensibilidad_fija_comparten_nivel_y_respaldo(self):
        r = correr(self.d)
        self.assertEqual(r.formas, (S, L))
        self.assertEqual(r.nivel.dtype, np.int8)
        d = self.d
        nivel = rt.nombre_nivel(r.nivel)
        casos = {1: "macrozona_franja", 2: "macrozona_franja",       # 3 conglomerados de 2 grupos
                 0: "franja",                                       # las gemelas 2–3 cuentan una vez: 2 conglomerados
                 3: "franja",                                       # los demás de mz 2: un solo conglomerado
                 4: "franja",                                       # 3 conglomerados, pero de un solo grupo
                 5: "franja"}                                       # la macrozona 3 no tiene a nadie más
        for k, esperado in casos.items():
            for hora in (3, 12):
                sel = (d["k"] == k) & (d["hora"] == hora)
                self.assertTrue(np.all(nivel[sel] == esperado), (k, hora))
                mz = int(d["mz"][sel][0])
                a_s, a_l = self.adj_esperado(k, mz, hora, esperado)
                self.assertAlmostEqual(float(r.adj[S][sel][0]), a_s, places=11)
                self.assertAlmostEqual(float(r.adj[L][sel][0]), a_l, places=11)
        for f in (S, L):
            np.testing.assert_allclose(r.pred[f], np.expm1(d["z"] + r.adj[f]).astype("float32"))
        self.assertFalse(np.allclose(r.adj[S], r.adj[L]))

    def test_registro_por_pliegue(self):
        r = correr(self.d, nombres=NOMBRES)
        reg = {(x["k"], x["clave"]): x for x in r.registro}
        self.assertEqual(len(reg), 12)                                          # 6 pliegues × 2 franjas
        x = reg[(1, "1|nocturna")]
        self.assertEqual((x["nivel"], x["estaciones"], x["conglomerados"], x["grupos"]),
                         ("macrozona_franja", ["S0", "S1", "S4"], 3, 2))
        self.assertEqual((x["filas_usadas"], x["filas_prueba"], x["motivo"]), (450, 300, []))
        for f in (S, L):
            self.assertAlmostEqual(x["factor"][f], float(np.exp(x["ajuste"][f])), places=12)
        x = reg[(0, "1|diurna")]
        self.assertEqual(x["nivel"], "franja")
        self.assertIn("conglomerados LOSO-D 2 < 3", x["motivo"][0])
        self.assertEqual(x["estaciones"], [f"S{e}" for e in sorted(ESTACIONES) if ESTACIONES[e][0] != 0])
        self.assertIn("grupos del protocolo 1 < 2", reg[(4, "2|nocturna")]["motivo"][0])
        self.assertNotIn("conglomerados", reg[(4, "2|nocturna")]["motivo"][0])
        self.assertIn("sin residuos de los demás", reg[(5, "3|diurna")]["motivo"][0])
        self.assertEqual(r.resumen()["niveles"], {"macrozona_franja": 900, "franja": 2400, "global": 0, "sin_correccion": 0})
        self.assertEqual(r.resumen()["forma_primaria"], S)
        self.assertEqual(json.loads(json.dumps(r.registro))[0]["factor"].keys(), {S, L})    # va tal cual a consolidado.json
        json.dumps(r.resumen())
        json.dumps(correr(self.d).registro)                                     # también con códigos de estación

    def test_piso_de_filas_de_la_clave(self):
        r = correr(self.d, regla=rt.ReglaRespaldo(minimo_filas_clave=451))
        nivel = rt.nombre_nivel(r.nivel)
        self.assertTrue(np.all(nivel[self.d["k"] == 1] == "franja"))            # 450 filas < 451
        self.assertTrue(np.all(nivel[self.d["k"] == 2] == "macrozona_franja"))  # 4 estaciones: 600 filas

    def test_franja_insuficiente_cae_al_global_y_luego_sin_correccion(self):
        d = self.d
        r = correr(d, regla=rt.ReglaRespaldo(minimo_filas_clave=10**6, minimo_filas=2000))
        nivel = rt.nombre_nivel(r.nivel)
        # franja de los demás: (11 − |pliegue|)·150 filas ≤ 1.500 < 2.000; global: el doble (≥ 2.100)
        self.assertTrue(np.all(nivel == "global"))
        for k in range(6):
            a_s, a_l = self.adj_esperado(k, 0, 3, "global")
            self.assertAlmostEqual(float(r.adj[S][d["k"] == k][0]), a_s, places=11)
            self.assertAlmostEqual(float(r.adj[L][d["k"] == k][0]), a_l, places=11)
        r = correr(d, regla=rt.ReglaRespaldo(minimo_filas_clave=10**6, minimo_filas=10**6))
        self.assertTrue(np.all(rt.nombre_nivel(r.nivel) == "sin_correccion"))
        self.assertTrue(all(np.all(r.adj[f] == 0.0) for f in (S, L)))
        self.assertTrue(all(x["nivel"] == "sin_correccion" and x["factor"] == {S: 1.0, L: 1.0} and x["estaciones"] == []
                            for x in r.registro))
        np.testing.assert_allclose(r.pred[S], np.expm1(d["z"]).astype("float32"))

    def test_nunca_usa_al_propio_grupo(self):
        d = self.d
        r = correr(d)
        d2 = {**d, "z": d["z"].copy()}
        uno = d["k"] == 1
        d2["z"][uno] += np.random.default_rng(5).normal(0, 3, uno.sum())        # residuos propios muy distintos
        d2["res"] = np.log1p(d2["y"]) - d2["z"]
        r2 = correr(d2)
        for f in (S, L):
            np.testing.assert_array_equal(r.adj[f][uno], r2.adj[f][uno])        # el pliegue 1 no se usa a sí mismo
            self.assertFalse(np.array_equal(r.adj[f][d["k"] == 2], r2.adj[f][d["k"] == 2]))   # pero sí en el 2

    def test_la_misma_exclusion_en_los_residuos_y_en_el_conteo(self):
        """LBO-10: el pliegue 1 excluye además a la estación 4 (de otro grupo, en su entorno de 10 km). Sus residuos no
        entran en la corrección del pliegue 1 y su conglomerado no cuenta: la clave cae a la franja."""
        d = self.d
        excl = {**d["excl"], 1: [2, 3, 4]}
        r = correr(d, excl=excl)
        nivel = rt.nombre_nivel(r.nivel)
        uno = d["k"] == 1
        self.assertTrue(np.all(nivel[uno] == "franja"))                          # quedan 2 conglomerados de 1 grupo
        for hora in (3, 12):
            sel = uno & (d["hora"] == hora)
            a_s, _ = self.adj_esperado(1, 1, hora, "franja", excl)
            self.assertAlmostEqual(float(r.adj[S][sel][0]), a_s, places=11)
        reg = next(x for x in r.registro if x["k"] == 1)
        self.assertNotIn(4, reg["estaciones"])
        d2 = {**d, "z": d["z"].copy()}
        d2["z"][d["est"] == 4] += 2.0
        r2 = correr(d2, excl=excl)
        np.testing.assert_array_equal(r.adj[S][uno], r2.adj[S][uno])            # la 4 no entra en el pliegue 1
        self.assertFalse(np.array_equal(r.adj[S][d["k"] == 0], r2.adj[S][d["k"] == 0]))   # sí en el 0

    def test_filas_de_prueba_fuera_del_conjunto_excluido(self):
        with self.assertRaises(ValueError):
            correr(self.d, excl={**self.d["excl"], 0: [0]})

    def test_conglomerados_obligatorios_y_completos(self):
        d = self.d
        args = (d["z"], d["y"], d["est"], d["mz"], d["hora"], d["k"], d["excl"], False)
        with self.assertRaisesRegex(ValueError, "conglomerado"):
            rt.duan_fuera_de_pliegue(*args)
        congl = d["congl"].copy()
        congl[4] = -1
        with self.assertRaisesRegex(ValueError, r"\[4\]"):
            rt.fuera_de_pliegue(*args, conglomerado_de_estacion=congl)
        with self.assertRaises(ValueError):
            rt.fuera_de_pliegue(*args, conglomerado_de_estacion=congl[:5])

    def test_duan_fuera_de_pliegue_es_la_primaria_por_omision(self):
        d = self.d
        args = (d["z"], d["y"], d["est"], d["mz"], d["hora"], d["k"], d["excl"], False)
        r = correr(d)
        pred, adj, nivel, reg = rt.duan_fuera_de_pliegue(*args, conglomerado_de_estacion=d["congl"])
        np.testing.assert_array_equal(adj, r.adj[S])
        np.testing.assert_array_equal(pred, r.pred[S])
        np.testing.assert_array_equal(nivel, r.nivel)
        self.assertTrue(all(x["forma"] == S and x["adj"] == x["ajuste"][S] for x in reg))
        _, adj_l, _, _ = rt.duan_fuera_de_pliegue(*args, forma=L, conglomerado_de_estacion=d["congl"])
        np.testing.assert_array_equal(adj_l, r.adj[L])
        _, _, nivel_m, _ = rt.duan_fuera_de_pliegue(*args, minimo=10**6, conglomerado_de_estacion=d["congl"])
        self.assertTrue(np.all(rt.nombre_nivel(nivel_m) == "sin_correccion"))

    def test_filas_sin_pliegue_o_sin_prediccion(self):
        d = {**protocolo(), }
        d["z"] = d["z"].copy()
        d["z"][:10] = np.nan
        d["k"] = d["k"].copy()
        d["k"][-5:] = -1
        r = correr(d)
        self.assertTrue(np.all(np.isnan(r.pred[S][:10])) and np.all(np.isnan(r.pred[S][-5:])))
        self.assertTrue(np.all(r.nivel[-5:] == rt.SIN_NIVEL))
        self.assertTrue(np.all(np.isfinite(r.pred[S][10:-5])))


class LPOTests(unittest.TestCase):
    def test_lpo_excluye_el_cuatrienio_y_cuenta_conglomerados_entre_cuatrienios(self):
        """LPO: las mismas estaciones en todos los cuatrienios. En la macrozona 1 las gemelas 0–1 son un solo
        conglomerado (2 en total): cae a la franja; en la 2 hay 3 conglomerados de los otros 2 cuatrienios."""
        rng = np.random.default_rng(3)
        n = 6000
        est = rng.integers(0, 6, n)
        k = np.arange(n) * 3 // n
        mz = np.where(est < 3, 1, 2)
        hora = rng.integers(0, 24, n)
        res = rng.normal(0.1 * k, np.where(k == 0, 0.3, 0.9))
        y = np.full(n, np.expm1(2.0))
        z = np.log1p(y) - res
        congl = np.array([0, 0, 1, 2, 3, 4])
        r = rt.fuera_de_pliegue(z, y, est, mz, hora, k, {}, True, conglomerado_de_estacion=congl)
        nivel = rt.nombre_nivel(r.nivel)
        fr = rt.franja(hora)
        self.assertTrue(np.all(nivel[mz == 1] == "franja"))
        self.assertTrue(np.all(nivel[mz == 2] == "macrozona_franja"))
        for kk in range(3):
            for f in (0, 1):
                sel = (k == kk) & (fr == f)
                ref = (k != kk) & (fr == f)
                self.assertAlmostEqual(float(r.adj[S][sel & (mz == 1)][0]), smearing(res[ref]), places=11)
                self.assertAlmostEqual(float(r.adj[S][sel & (mz == 2)][0]), smearing(res[ref & (mz == 2)]), places=11)
        x = next(x for x in r.registro if x["k"] == 0 and x["clave"] == "2|diurna")
        self.assertEqual((x["conglomerados"], x["grupos"], x["estaciones"]), (3, 2, [3, 4, 5]))
        # el propio cuatrienio nunca entra
        z2 = z.copy()
        z2[k == 0] += 1.0
        r2 = rt.fuera_de_pliegue(z2, y, est, mz, hora, k, {}, True, conglomerado_de_estacion=congl)
        np.testing.assert_array_equal(r.adj[S][k == 0], r2.adj[S][k == 0])


class ReferenciaTests(unittest.TestCase):
    def test_sumas_por_unidad_igual_a_la_referencia_directa(self):
        """Datos al azar (estaciones, conglomerados, pliegues, macrozonas y horas) en un protocolo espacial con
        entorno excluido, y en uno temporal: nivel y ajuste de las dos formas, fila a fila."""
        vistos = set()
        for semilla, temporal in ((11, False), (12, False), (13, True)):
            rng = np.random.default_rng(semilla)
            n_est = 18
            k_est = rng.integers(0, 5, n_est)
            congl = rng.integers(0, 12, n_est)
            mz_est = rng.integers(0, 3, n_est)
            n = 9000
            est = rng.integers(0, n_est, n)
            k = rng.integers(0, 4, n) if temporal else k_est[est]
            mz = mz_est[est]
            hora = rng.integers(0, 24, n)
            res = rng.normal(rng.normal(0, 0.2, n_est)[est], 0.5)
            y = np.full(n, np.expm1(1.0))
            z = np.log1p(y) - res
            excl = {int(kk): sorted({*np.flatnonzero(k_est == kk).tolist(), int((kk * 7) % n_est)})
                    for kk in np.unique(k)}
            d = dict(est=est, k=k, mz=mz, hora=hora, y=y, z=z, res=res, congl=congl, excl=excl)
            for regla in (rt.ReglaRespaldo(), rt.ReglaRespaldo(300, 4, 3, 250), rt.ReglaRespaldo(300, 4, 3, 3500),
                          rt.ReglaRespaldo(10**6, 3, 2, 10**5)):
                with self.subTest(semilla=semilla, regla=regla):
                    r = correr(d, regla=regla, temporal=temporal)
                    nivel_ref, adj_ref = referencia(d, excl, temporal, regla)
                    con = r.nivel >= 0
                    np.testing.assert_array_equal(rt.nombre_nivel(r.nivel)[con], nivel_ref[con])
                    for f in (S, L):
                        np.testing.assert_allclose(r.adj[f][con], adj_ref[f][con], rtol=0, atol=1e-11)
                    vistos |= set(nivel_ref[con])
        self.assertEqual(vistos, set(rt.NIVELES))                   # la prueba recorre los cuatro niveles


class SensibilidadInternaTests(unittest.TestCase):
    def datos(self):
        """Entrenamiento de un pliegue externo retirado (el 9): grupos externos 0 … 2, con gemelas."""
        rng = np.random.default_rng(4)
        n = 3000
        est = rng.integers(0, 6, n)
        grupo = np.array([0, 0, 1, 1, 2, 2])[est]
        mz = np.where(est < 4, 2, 3)
        hora = rng.integers(0, 24, n)
        res = rng.normal(0.1, np.where(mz == 2, 0.3, 0.6))
        y = np.full(n, np.expm1(2.0))
        z = np.log1p(y) - res
        congl = np.array([0, 1, 2, 2, 3, 4, -1, -1])           # 2–3 gemelas; 6 y 7 no tienen filas
        return est, grupo, mz, hora, res, y, z, congl

    def test_tabla_interna_con_el_mismo_respaldo_y_las_dos_formas(self):
        est, grupo, mz, hora, res, y, z, congl = self.datos()
        tabla = rt.tabla_interna(z, y, mz, hora, estacion=est, grupo=grupo, conglomerado_de_estacion=congl, retirado=9,
                                 excluidas=[6, 7])
        self.assertEqual(tabla["forma"], S)
        zp = np.ones(4)
        mzp = np.array([2, 2, 3, 7])
        hp = np.array([3, 12, 12, 12])
        r = rt.aplicar_tabla(zp, mzp, hp, tabla)
        nivel = rt.nombre_nivel(r.nivel)
        fr = rt.franja(hora)
        # mz 2: estaciones 0–3, conglomerados {0, 1, 2} de los grupos {0, 1}: se usa la clave
        self.assertEqual(list(nivel[:2]), ["macrozona_franja", "macrozona_franja"])
        self.assertAlmostEqual(r.adj[S][0], smearing(res[(mz == 2) & (fr == 0)]), places=11)
        self.assertAlmostEqual(r.adj[L][1], lognormal(res[(mz == 2) & (fr == 1)]), places=11)
        # mz 3: estaciones 4–5, dos conglomerados de un grupo: cae a la franja; mz 7: sin datos internos
        self.assertEqual(list(nivel[2:]), ["franja", "franja"])
        self.assertAlmostEqual(r.adj[S][3], smearing(res[fr == 1]), places=11)
        self.assertIn("conglomerados LOSO-D 2 < 3", r.registro[2]["motivo"][0])
        np.testing.assert_allclose(r.pred[S], rt.retransformar(zp, r.adj[S]))
        self.assertEqual(rt.resumen_niveles(r.nivel), {"macrozona_franja": 2, "franja": 2, "global": 0, "sin_correccion": 0})
        p, a, codigos, reg = rt.duan_interno(zp, mzp, hp, tabla)                      # la forma de la tabla
        np.testing.assert_array_equal(a, r.adj[S])
        self.assertTrue(all(x["forma"] == S for x in reg))
        _, a_l, _, _ = rt.duan_interno(zp, mzp, hp, tabla, forma=L)
        np.testing.assert_array_equal(a_l, r.adj[L])

    def test_guardas_de_la_tabla_interna(self):
        est, grupo, mz, hora, res, y, z, congl = self.datos()
        with self.assertRaises(TypeError):
            rt.tabla_interna(z, y, mz, hora)                       # sin estaciones ni grupos no hay respaldo honesto
        with self.assertRaises(AssertionError):
            rt.tabla_interna(z, y, mz, hora, estacion=est, grupo=grupo, conglomerado_de_estacion=congl, retirado=1)
        with self.assertRaises(AssertionError):
            rt.tabla_interna(z, y, mz, hora, estacion=est, grupo=grupo, conglomerado_de_estacion=congl, excluidas=[5])
        with self.assertRaises(ValueError):
            rt.tabla_interna(z, y, mz, hora, estacion=est, grupo=np.where(est == 0, -1, grupo),
                             conglomerado_de_estacion=congl)

    def test_tabla_de_produccion_usa_todas_las_filas(self):
        d = protocolo()
        tabla = rt.tabla_de_produccion(d["z"], d["y"], d["mz"], d["hora"], estacion=d["est"], grupo=d["k"],
                                       conglomerado_de_estacion=d["congl"])
        self.assertEqual(tabla["forma"], S)
        r = rt.aplicar_tabla(np.zeros(2), np.array([1, 3]), np.array([12, 12]), tabla, formas=(S,))
        fr = rt.franja(d["hora"])
        # mz 1: 5 estaciones, 4 conglomerados, 3 grupos (nadie retirado); mz 3: un conglomerado, cae a la franja
        self.assertEqual(list(rt.nombre_nivel(r.nivel)), ["macrozona_franja", "franja"])
        self.assertAlmostEqual(r.adj[S][0], smearing(d["res"][(d["mz"] == 1) & (fr == 1)]), places=11)
        self.assertAlmostEqual(r.adj[S][1], smearing(d["res"][fr == 1]), places=11)
        self.assertEqual(set(r.adj), {S})


class ManifiestoTests(unittest.TestCase):
    def test_conglomerados_loso_d(self):
        man = {"protocolos": {"LOSO-D": {"pliegues": [{"k": 0, "estaciones_prueba": ["A1", "A2"]},
                                                      {"k": 1, "estaciones_prueba": ["B"]},
                                                      {"k": 2, "estaciones_prueba": ["C"]}]}}}
        np.testing.assert_array_equal(rt.conglomerados_loso_d(man, ["B", "A2", "C", "A1"]), [1, 0, 2, 0])
        with self.assertRaisesRegex(ValueError, "D"):
            rt.conglomerados_loso_d(man, ["A1", "D"])
        man["protocolos"]["LOSO-D"]["pliegues"].append({"k": 3, "estaciones_prueba": ["C"]})
        with self.assertRaises(ValueError):
            rt.conglomerados_loso_d(man, ["C"])

    def test_manifiesto_real_cubre_todas_las_estaciones(self):
        """Con el manifiesto fijado (si está en esta máquina): cada estación del panel tiene un solo conglomerado y
        los conglomerados de varias estaciones son los del registro del manifiesto. Sólo lee la lista de pliegues."""
        import _rutas_v2 as rv
        ruta = rv.RutasV2.desde_entorno().manifiesto_pliegues
        if not ruta.exists():
            self.skipTest("no está el manifiesto de pliegues en esta máquina")
        man = json.loads(ruta.read_text(encoding="utf-8"))
        for pol, d in man["contaminantes"].items():
            congl = rt.conglomerados_loso_d(d, d["estaciones"])
            self.assertEqual(len(congl), len(d["estaciones"]))
            de = dict(zip(d["estaciones"], congl))
            for c in d["conglomerados_loso_d"]:
                self.assertEqual(len({de[s] for s in c["estaciones"]}), 1, (pol, c["grupo"]))


if __name__ == "__main__":
    unittest.main()
