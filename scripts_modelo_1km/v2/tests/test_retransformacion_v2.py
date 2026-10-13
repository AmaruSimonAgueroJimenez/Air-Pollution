"""Pruebas de ``retransformacion_v2``: forma de Duan de la v1, respaldo honesto (franja y luego global de los demás,
nunca el propio grupo), la misma exclusión del protocolo en los residuos (también el entorno de LBO-10), LPO y la
sensibilidad con OOF interno."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))
import retransformacion_v2 as rt  # noqa: E402


def adj_directo(res: np.ndarray) -> float:
    return 0.5 * float(np.var(res))                        # ddof = 0, como produccion.py:153 (smear_de)


def tabla_filas(semilla=0):
    """Tres pliegues espaciales con estaciones propias. El pliegue 0 es la única fuente de la macrozona 9."""
    rng = np.random.default_rng(semilla)
    filas = []
    #            estación, pliegue, macrozona, n por franja
    for est, k, mz, n in ((0, 0, 9, 300), (1, 1, 1, 400), (2, 1, 2, 300), (3, 2, 1, 500), (4, 2, 2, 350)):
        for fr_hora in (3, 12):                             # nocturna y diurna
            filas.append((np.full(n, est), np.full(n, k), np.full(n, mz), np.full(n, fr_hora),
                          rng.normal(0.1 * est, 0.2 + 0.1 * est, n)))
    est, k, mz, hora, res = (np.concatenate(c) for c in zip(*filas))
    y = np.expm1(np.full(len(res), 3.0))
    z = np.log1p(y) - res                                   # residuo log exacto = res
    return dict(est=est, k=k, mz=mz, hora=hora, y=y, z=z, res=np.log1p(y) - z)


class FormaTests(unittest.TestCase):
    def test_franja_de_la_v1(self):
        np.testing.assert_array_equal(rt.franja([0, 7, 8, 12, 18, 19, 23]), [0, 0, 1, 1, 1, 0, 0])
        self.assertEqual(rt.clave(2, 1), "2|diurna")

    def test_duan_y_smearing_desde_sumas(self):
        r = np.random.default_rng(1).normal(0.2, 0.5, 1000)
        self.assertAlmostEqual(float(rt.ajuste_desde_sumas(len(r), r.sum(), (r * r).sum(), np.exp(r).sum())), adj_directo(r))
        self.assertAlmostEqual(float(rt.ajuste_desde_sumas(len(r), r.sum(), (r * r).sum(), np.exp(r).sum(), "smearing")),
                               float(np.log(np.mean(np.exp(r)))))
        np.testing.assert_allclose(rt.retransformar([1.0], [0.5]), np.array([np.expm1(1.5)], dtype="float32"))


class RespaldoHonestoTests(unittest.TestCase):
    def setUp(self):
        self.d = tabla_filas()
        self.excl = {0: [0], 1: [1, 2], 2: [3, 4]}

    def correr(self, d=None, excl=None, minimo=100, temporal=False):
        d = d or self.d
        pred, adj, nivel, reg = rt.duan_fuera_de_pliegue(d["z"], d["y"], d["est"], d["mz"], d["hora"], d["k"],
                                                         excl or self.excl, temporal, minimo=minimo)
        self.assertEqual(nivel.dtype, np.int8)                              # código del nivel por fila
        return pred, adj, rt.nombre_nivel(nivel), reg

    def test_macrozona_ausente_cae_a_la_franja_de_los_demas(self):
        pred, adj, nivel, reg = self.correr()
        d = self.d
        cero = d["k"] == 0
        self.assertTrue(np.all(nivel[cero] == "franja"))
        for hora in (3, 12):
            sel = cero & (d["hora"] == hora)
            otros = (d["k"] != 0) & (rt.franja(d["hora"]) == rt.franja([hora])[0])
            self.assertAlmostEqual(float(adj[sel][0]), adj_directo(d["res"][otros]), places=12)
        # los pliegues 1 y 2 tienen macrozonas que existen en el otro: nivel macrozona_franja con los demás
        for k, otro in ((1, 2), (2, 1)):
            for mz in (1, 2):
                for hora in (3, 12):
                    sel = (d["k"] == k) & (d["mz"] == mz) & (d["hora"] == hora)
                    ref = (d["k"] == otro) & (d["mz"] == mz) & (d["hora"] == hora)
                    self.assertTrue(np.all(nivel[sel] == "macrozona_franja"))
                    self.assertAlmostEqual(float(adj[sel][0]), adj_directo(d["res"][ref]), places=12)
        np.testing.assert_allclose(pred, np.expm1(d["z"] + adj).astype("float32"))

    def test_nunca_usa_al_propio_grupo(self):
        # Con mínimo 1.000, las claves de los pliegues 1 y 2 caen a la franja de los demás, que incluye al 0.
        _, adj, _, _ = self.correr(minimo=1000)
        d2 = {**self.d, "z": self.d["z"].copy()}
        cero = self.d["k"] == 0
        d2["z"][cero] += np.random.default_rng(5).normal(0, 3, cero.sum())        # residuos propios muy distintos
        _, adj2, _, _ = self.correr(d2, minimo=1000)
        np.testing.assert_array_equal(adj[cero], adj2[cero])                      # el pliegue 0 no se usa a sí mismo
        self.assertFalse(np.array_equal(adj[~cero], adj2[~cero]))                 # pero sí entra en los demás

    def test_franja_de_los_demas_con_menos_de_100_cae_al_global(self):
        _, adj, nivel, _ = self.correr(minimo=2000)            # franja de los demás: 1.550 filas; global: 3.100
        d = self.d
        cero = d["k"] == 0
        self.assertTrue(np.all(nivel[cero] == "global"))
        self.assertAlmostEqual(float(adj[cero][0]), adj_directo(d["res"][d["k"] != 0]), places=12)

    def test_global_de_los_demas_insuficiente_queda_sin_correccion(self):
        _, adj, nivel, reg = self.correr(minimo=10**6)
        self.assertTrue(np.all(nivel == "sin_correccion"))
        self.assertTrue(np.all(adj == 0.0))
        self.assertTrue(all(r["nivel"] == "sin_correccion" for r in reg))

    def test_la_misma_exclusion_del_protocolo_en_los_residuos(self):
        """LBO-10: el pliegue 1 excluye además a la estación 3 (de otro grupo, su entorno de 10 km). Sus residuos no
        pueden entrar en la corrección del pliegue 1, aunque sean fuera de pliegue."""
        excl = {0: [0], 1: [1, 2, 3], 2: [3, 4]}
        _, adj, nivel, _ = self.correr(excl=excl)
        d = self.d
        uno = d["k"] == 1
        for mz in (1, 2):
            for hora in (3, 12):
                sel = uno & (d["mz"] == mz) & (d["hora"] == hora)
                ref = (d["est"] == 4) & (d["mz"] == mz) & (d["hora"] == hora)          # sólo la 4 queda en mz 2
                if mz == 2:
                    self.assertAlmostEqual(float(adj[sel][0]), adj_directo(d["res"][ref]), places=12)
        d2 = {**d, "z": d["z"].copy()}
        tres = d["est"] == 3
        d2["z"][tres] += 2.0
        _, adj2, _, _ = rt.duan_fuera_de_pliegue(d2["z"], d2["y"], d2["est"], d2["mz"], d2["hora"], d2["k"], excl, False)
        np.testing.assert_array_equal(adj[uno], adj2[uno])                        # la 3 no entra en el pliegue 1
        self.assertFalse(np.array_equal(adj[d["k"] == 0], adj2[d["k"] == 0]))     # sí en el 0, que no la excluye

    def test_filas_de_prueba_fuera_del_conjunto_excluido(self):
        with self.assertRaises(ValueError):
            self.correr(excl={0: [], 1: [1, 2], 2: [3, 4]})

    def test_lpo_excluye_el_cuatrienio_y_no_las_estaciones(self):
        """En LPO la misma estación está en entrenamiento con otros cuatrienios: se usan sus residuos de los
        demás cuatrienios y nunca los del propio."""
        rng = np.random.default_rng(3)
        n = 2000
        est = rng.integers(0, 4, n)
        k = (np.arange(n) >= 1000).astype(int)
        mz = np.ones(n, dtype=int)
        hora = rng.integers(0, 24, n)
        res = rng.normal(0, np.where(k == 0, 0.3, 0.9))
        y = np.full(n, np.expm1(2.0))
        z = np.log1p(y) - res
        _, adj, nivel, _ = rt.duan_fuera_de_pliegue(z, y, est, mz, hora, k, {}, temporal=True)
        self.assertEqual(set(rt.nombre_nivel(nivel)), {"macrozona_franja"})   # una sola macrozona
        fr = rt.franja(hora)
        for kk in (0, 1):
            for f in (0, 1):
                sel = (k == kk) & (fr == f)
                ref = (k != kk) & (fr == f)
                self.assertAlmostEqual(float(adj[sel][0]), adj_directo(res[ref]), places=12)

    def test_sumas_por_unidad_igual_al_calculo_directo(self):
        rng = np.random.default_rng(11)
        n = 6000
        est = rng.integers(0, 12, n)
        k = est // 3                                                               # 4 pliegues de 3 estaciones
        mz = est % 4
        hora = rng.integers(0, 24, n)
        res = rng.normal(0, 0.5, n)
        y = np.full(n, np.expm1(1.0))
        z = np.log1p(y) - res
        excl = {kk: list(range(3 * kk, 3 * kk + 3)) for kk in range(4)}
        _, adj, nivel, _ = rt.duan_fuera_de_pliegue(z, y, est, mz, hora, k, excl, False, minimo=50)
        fr = rt.franja(hora)
        for kk in range(4):
            for m in np.unique(mz[k == kk]):
                for f in (0, 1):
                    sel = (k == kk) & (mz == m) & (fr == f)
                    if not sel.any():
                        continue
                    ref = (k != kk) & (mz == m) & (fr == f)
                    esperado = adj_directo(res[ref]) if ref.sum() >= 50 else adj_directo(res[(k != kk) & (fr == f)])
                    self.assertAlmostEqual(float(adj[sel][0]), esperado, places=11)


class SensibilidadInternaTests(unittest.TestCase):
    def test_tabla_interna_y_aplicacion(self):
        rng = np.random.default_rng(4)
        n = 1500
        mz = np.where(np.arange(n) < 1000, 2, 3)
        hora = rng.integers(0, 24, n)
        res = rng.normal(0, np.where(mz == 2, 0.3, 0.6))
        y = np.full(n, np.expm1(2.0))
        z = np.log1p(y) - res
        tabla = rt.tabla_interna(z, y, mz, hora)
        z_prueba = np.array([1.0, 1.0, 1.0, 1.0])
        mz_prueba = np.array([2, 2, 3, 7])
        h_prueba = np.array([3, 12, 12, 12])
        pred, adj, codigos, reg = rt.duan_interno(z_prueba, mz_prueba, h_prueba, tabla)
        nivel = rt.nombre_nivel(codigos)
        fr = rt.franja(hora)
        self.assertEqual(list(nivel[:2]), ["macrozona_franja", "macrozona_franja"])
        self.assertAlmostEqual(adj[0], adj_directo(res[(mz == 2) & (fr == 0)]), places=12)
        self.assertAlmostEqual(adj[1], adj_directo(res[(mz == 2) & (fr == 1)]), places=12)
        self.assertEqual(nivel[3], "franja")                                       # macrozona 7: sin datos internos
        self.assertAlmostEqual(adj[3], adj_directo(res[fr == 1]), places=12)
        np.testing.assert_allclose(pred, rt.retransformar(z_prueba, adj))
        self.assertEqual(rt.resumen_niveles(codigos), {"macrozona_franja": 3, "franja": 1, "global": 0, "sin_correccion": 0})


if __name__ == "__main__":
    unittest.main()
