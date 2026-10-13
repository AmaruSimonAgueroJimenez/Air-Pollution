"""Pruebas de punta a punta de ``correr_v2`` con datos sintéticos pequeños (``_sintetico_v2``), en raíces temporales:

* mismas filas entre motores (permutación común, topes anidados) y mismos pares de evaluación para todos;
* determinismo: dos corridas completas idénticas bit a bit (puntos de control, OOF y métricas);
* la regla única de exclusión en los cuatro lugares: filas de entrenamiento, vecindario de entrenamiento y de
  prueba (multiplicar por 3 las observaciones de las estaciones excluidas no cambia ni un bit del pliegue) y
  residuos de la retransformación (el entorno de LBO-10 no entra en la corrección del pliegue);
* reanudación por firma, consolidación que exige todos los pliegues, piloto sin predicciones, plan con los
  recortes de §10 y traza sin rutas absolutas.
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
sys.path.insert(0, str(V2 / "tests"))
import _rutas_v2 as rv  # noqa: E402
import _sintetico_v2 as sx  # noqa: E402
import correr_v2 as cr  # noqa: E402
import motores_v2 as mv  # noqa: E402
import retransformacion_v2 as rt  # noqa: E402

CFG = sx.config_pequena()


def calidad_sintetica(panel: pd.DataFrame) -> np.ndarray:
    rng = np.random.default_rng(9)
    return rng.choice(np.array(["validado", "preliminar", "no_validado"], dtype=object), size=len(panel), p=[0.6, 0.25, 0.15])


def contexto(r, panel=None, con_calidad=True):
    panel = sx.panel_sintetico() if panel is None else panel
    return cr.Contexto.desde_tablas("pm25", panel, sx.manifiesto_sintetico(panel), CFG, r, hilos=2,
                                    calidad=calidad_sintetica(panel) if con_calidad else None)


def correr_protocolo(ctx, prot, opciones=None, pliegues=None):
    plan = cr.plan_protocolo(ctx.recetas, prot, opciones or cr.Opciones(), calidad_disponible=ctx.calidad is not None)
    tiempos = []
    with rv.candado_escritura("prueba", rutas=ctx.rutas):
        for f in ctx.pliegues(prot):
            if pliegues is None or int(f["k"]) in pliegues:
                tiempos += cr.correr_pliegue(ctx, prot, f, plan)
    return plan, tiempos


def predicciones_pliegue(ctx, prot, k, plan):
    out = {}
    for t in plan["tareas"]:
        arr, meta = cr.leer_punto(cr.ruta_punto(ctx, prot, k, f"r{t.replica}", t.id))
        for base, nombre in zip(t.salidas or (t.id,), t.nombres()):
            out[nombre] = arr[base]
    return out


class MismasFilasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._raices = sx.raices_temporales()
        cls.r = cls._raices.__enter__()
        cls.ctx = contexto(cls.r)
        cls.plan, _ = correr_protocolo(cls.ctx, "LRO")
        cls.res = cr.consolidar(cls.ctx, "LRO", cls.plan, escribir=True, replicas_bootstrap=100)

    @classmethod
    def tearDownClass(cls):
        cls._raices.__exit__(None, None, None)

    def test_mismas_filas_y_topes_anidados(self):
        ctx = self.ctx
        for f in ctx.pliegues("LRO"):
            k = int(f["k"])
            metas = {}
            for t in self.plan["tareas"]:
                metas[(t.id, t.replica)] = cr.leer_punto(cr.ruta_punto(ctx, "LRO", k, f"r{t.replica}", t.id))[1]
            ent, _, _ = ctx.vec.mascaras(f, "LRO")
            disp = np.flatnonzero(ent)
            for r in (0, 1, 2):
                orden = mv.permutacion(disp, mv.semilla_permutacion(k, r))
                comunes = {t.id for t in self.plan["tareas"] if t.replica == r and t.tope == "N" and t.calidad == "todo"}
                shas = {metas[(i, r)]["filas_entrenamiento"]["sha256"] for i in comunes}
                with self.subTest(k=k, replica=r):
                    self.assertGreaterEqual(len(comunes), 4 if r else 15)
                    self.assertEqual(len(shas), 1)                              # todos los motores, las mismas filas
                    self.assertEqual(shas, {cr._sha(mv.filas_tope(orden, ctx.recetas["N_comun"]))})
            orden0 = mv.permutacion(disp, mv.semilla_permutacion(k, 0))
            conjuntos = [set(mv.filas_tope(orden0, t).tolist()) for t in (120, 1200, 1500, 2400, None)]
            self.assertTrue(all(a <= b for a, b in zip(conjuntos, conjuntos[1:])))   # GP ⊂ N ⊂ LME ⊂ curvas ⊂ todas
            self.assertNotEqual(metas[("lightgbm", 0)]["filas_entrenamiento"]["sha256"],
                                metas[("lightgbm", 1)]["filas_entrenamiento"]["sha256"])
            self.assertEqual(metas[("gp", 0)]["filas_entrenamiento"]["sha256"], cr._sha(mv.filas_tope(orden0, 120)))
            cal = metas[("lightgbm_cal_solo_validado", 0)]["filas_entrenamiento"]
            mascara = ctx.mascara_calidad("solo_validado")
            self.assertEqual(cal["sha256"], cr._sha(mv.filas_tope(orden0, ctx.recetas["N_comun"], mascara)))

    def test_mismos_pares_para_todos_los_motores(self):
        m = self.res["metricas"]
        claves = ["subconjunto", "nivel", "desagregacion", "estrato", "ponderacion", "escala"]
        n_por_motor = m.groupby(claves)["n"].nunique()
        self.assertTrue((n_por_motor == 1).all())                             # el mismo n para todos los motores
        self.assertEqual(self.res["consolidado"]["pares"]["pares_comunes"], int(self.res["comunes"].sum()))
        motores = set(m["motor"])
        for esperado in ("lightgbm", "xgboost", "random_forest", "mlp", "promedio", "apilado", "gp", "lme", "gwr", "rk",
                         "idw", "lightgbm_huber", "xgboost_q50", "lightgbm@r2", "lightgbm~sens", "lightgbm_ntodas",
                         "lightgbm_cal_solo_validado"):
            self.assertIn(esperado, motores)
        self.assertNotIn("alertas_q80", motores)                              # las alertas se juzgan aparte
        self.assertEqual(set(m["subconjunto"]), {"todas", "validadas"})
        apilado = self.res["consolidado"]["apilado"]["pesos_por_pliegue"]
        for w in apilado.values():
            self.assertAlmostEqual(sum(w.values()), 1.0, places=12)
            self.assertTrue(all(v >= 0 for v in w.values()))

    def test_tablas_y_traza_sin_rutas_absolutas(self):
        base = str(self.r.raiz_v2.parent)
        for archivo in self.r.salidas_v2.iterdir():
            texto = archivo.read_text(encoding="utf-8")
            self.assertNotIn(base, texto, archivo.name)
            self.assertNotIn("/Users/", texto, archivo.name)
        lateral = json.loads((self.r.salidas_v2 / "comparacion_principal_pm25_LRO.json").read_text(encoding="utf-8"))
        for clave in ("git", "codigo", "insumos", "bibliotecas", "hilos", "semillas"):
            self.assertIn(clave, lateral["traza"])
        meta = cr.leer_punto(cr.ruta_punto(self.ctx, "LRO", 0, "r0", "xgboost"))[1]
        self.assertEqual(meta["traza"]["semillas"], {"permutacion": [42, 0], "motor": 42})
        self.assertEqual(meta["hilos_firma"], 2)
        self.assertIsNone(cr.leer_punto(cr.ruta_punto(self.ctx, "LRO", 0, "r0", "lightgbm"))[1]["hilos_firma"])


class DeterminismoTests(unittest.TestCase):
    def corrida(self):
        with sx.raices_temporales() as r:
            ctx = contexto(r)
            salida = {"puntos": {}, "oof": {}, "metricas": {}}
            for prot in ("LRO", "LBO-10"):
                plan, _ = correr_protocolo(ctx, prot)
                res = cr.consolidar(ctx, prot, plan, escribir=True, replicas_bootstrap=100)
                salida["metricas"][prot] = res["metricas"].sort_values(list(res["metricas"].columns[:9])).reset_index(drop=True)
                salida["oof"][prot] = pd.read_parquet(ctx.raiz() / prot / "oof.parquet")
                salida["bootstrap"] = res["bootstrap"]
            for ruta in sorted((ctx.raiz()).rglob("*.npz")):
                arr, meta = cr.leer_punto(ruta)
                salida["puntos"][str(ruta.relative_to(ctx.raiz()))] = (arr, meta["firma"])
            return salida

    def test_dos_corridas_identicas_bit_a_bit(self):
        a, b = self.corrida(), self.corrida()
        self.assertEqual(sorted(a["puntos"]), sorted(b["puntos"]))
        # LRO: 3 pliegues × (34 tareas + 2 de calidad + vecindario) + 3 × 2 internos × 4 bases; LBO-10: 8 × (18 + 1)
        self.assertEqual(len(a["puntos"]), 3 * 37 + 3 * 2 * 4 + 8 * 19)
        for nombre, (arr_a, firma_a) in a["puntos"].items():
            arr_b, firma_b = b["puntos"][nombre]
            self.assertEqual(firma_a, firma_b, nombre)
            for k in arr_a:
                self.assertTrue(np.array_equal(arr_a[k], arr_b[k], equal_nan=True), f"{nombre}:{k}")
        for prot in ("LRO", "LBO-10"):
            oa, ob = a["oof"][prot], b["oof"][prot]
            self.assertEqual(list(oa.columns), list(ob.columns))
            for c in oa.columns:
                self.assertTrue(oa[c].equals(ob[c]), f"{prot} {c}")
            self.assertTrue(a["metricas"][prot].equals(b["metricas"][prot]))
        self.assertTrue(a["bootstrap"].equals(b["bootstrap"]))


class ExclusionTests(unittest.TestCase):
    """LBO-10, pliegue «A1+A2»: excluye A1, A2 (prueba) y B (entorno de 10 km)."""

    PROT, K = "LBO-10", 0

    def pliegue(self, perturbar):
        panel = sx.panel_sintetico(perturbar=perturbar)
        with sx.raices_temporales() as r:
            ctx = contexto(r, panel, con_calidad=False)
            f = ctx.pliegues(self.PROT)[self.K]
            plan, _ = correr_protocolo(ctx, self.PROT, pliegues=[self.K])
            rec = ctx.vec.para_pliegue(f, self.PROT, registrar=False)
            return predicciones_pliegue(ctx, self.PROT, self.K, plan), rec, f, ctx

    def test_filas_y_vecindario_de_entrenamiento_y_prueba(self):
        base, rec, f, ctx = self.pliegue(None)
        self.assertEqual(f["excluidas"], ["A1", "A2", "B"])
        est = ctx.vec.estaciones[ctx.vec.js]
        # 1. filas de entrenamiento: ninguna de una estación excluida (tampoco del entorno)
        self.assertFalse(np.isin(est[rec.entrenamiento], f["excluidas"]).any())
        self.assertFalse((rec.entrenamiento | rec.prueba)[est == "B"].any())
        # 2 y 3. multiplicar por 3 lo observado en las excluidas no cambia ni un bit: ni etiquetas ni vecindario
        pert, rec_p, _, _ = self.pliegue({"A1": 3.0, "A2": 3.0, "B": 3.0})
        usadas = rec.entrenamiento | rec.prueba
        for c in ("obs_vec", "peso_vec", "dist_est_km"):
            self.assertTrue(np.array_equal(getattr(rec, c)[usadas], getattr(rec_p, c)[usadas], equal_nan=True), c)
        self.assertEqual(sorted(base), sorted(pert))
        for nombre in base:
            self.assertTrue(np.array_equal(base[nombre], pert[nombre]), nombre)
        # control: perturbar una estación que sí entra cambia el pliegue (la prueba tiene poder)
        ctrl, _, _, _ = self.pliegue({"D": 3.0})
        cambian = [n for n in base if not np.array_equal(base[n], ctrl[n])]
        self.assertGreaterEqual(len(cambian), len(base) - 1)

    def test_residuos_de_la_retransformacion(self):
        """4. Los residuos de B (de otro grupo, en el entorno del pliegue) no entran en la corrección del pliegue."""
        with sx.raices_temporales() as r:
            ctx = contexto(r, con_calidad=False)
            plan, _ = correr_protocolo(ctx, self.PROT, cr.Opciones(motores=("lightgbm",), perdidas=False, alertas=False,
                                                                   eje_b=False, curvas=False, semillas=False))
            res = cr.consolidar(ctx, self.PROT, plan, escribir=False, replicas_bootstrap=50)
            z = res["z"]["lightgbm"].astype("float64")
            pdf = res["pliegue_de_fila"]
            excl = {int(f["k"]): ctx.vec.indices(f["excluidas"]) for f in ctx.pliegues(self.PROT)}
            args = (ctx.y, ctx.vec.js, ctx.macrozona, ctx.hora_local, pdf, excl, False)
            _, adj, _, _ = rt.duan_fuera_de_pliegue(z, *args)
            np.testing.assert_allclose(res["pred"]["lightgbm"], rt.retransformar(z, adj), rtol=1e-6)
            est = ctx.vec.estaciones[ctx.vec.js]
            z2 = z.copy()
            z2[est == "B"] += 1.5
            _, adj2, _, _ = rt.duan_fuera_de_pliegue(z2, *args)
            cero = pdf == self.K
            np.testing.assert_array_equal(adj[cero], adj2[cero])               # el pliegue A1+A2 no usa a B
            k_c = next(int(f["k"]) for f in ctx.pliegues(self.PROT) if f["grupo"] == "C")
            self.assertFalse(np.array_equal(adj[pdf == k_c], adj2[pdf == k_c]))   # C sí (no excluye a B)


class ReanudacionPilotoPlanTests(unittest.TestCase):
    def test_reanuda_por_firma_y_rehace_lo_vencido(self):
        with sx.raices_temporales() as r:
            ctx = contexto(r, con_calidad=False)
            op = cr.Opciones(eje_b=False, curvas=False, semillas=False, apilado=False)
            plan, t1 = correr_protocolo(ctx, "LOSO-D", op, pliegues=[0])
            self.assertEqual(len(t1), 1 + len(plan["tareas"]))
            _, t2 = correr_protocolo(ctx, "LOSO-D", op, pliegues=[0])
            self.assertEqual([t["tarea"] for t in t2], ["vecindario"])        # nada que reajustar
            ruta = cr.ruta_punto(ctx, "LOSO-D", 0, "r0", "xgboost")
            arr, meta = cr.leer_punto(ruta)
            meta["firma"] = "vencida"
            with rv.candado_escritura("prueba", rutas=r):
                cr.guardar_punto(ruta, arr, meta, r)
            _, t3 = correr_protocolo(ctx, "LOSO-D", op, pliegues=[0])
            self.assertEqual(sorted(t["tarea"] for t in t3), ["vecindario", "xgboost"])
            with self.assertRaises(cr.Incompleto):                           # faltan los demás pliegues
                cr.consolidar(ctx, "LOSO-D", plan, escribir=False)
            with self.assertRaises(rv.EscrituraNoPermitida):                  # sin candado no se escribe
                cr.correr_pliegue(ctx, "LOSO-D", ctx.pliegues("LOSO-D")[1], plan)

    def test_piloto_mide_tiempos_sin_guardar_predicciones(self):
        with sx.raices_temporales() as r:
            ctx = contexto(r, con_calidad=False)
            plan = cr.plan_protocolo(ctx.recetas, "BLQ-75", cr.Opciones(), False)
            elegidos = cr.pliegues_piloto(ctx.pliegues("BLQ-75"))
            self.assertEqual(len(elegidos), 2)
            filas = [f["filas_prueba"] for f in ctx.pliegues("BLQ-75")]
            self.assertEqual({f["filas_prueba"] for f in elegidos}, {max(filas), min(filas)})
            tiempos = []
            for f in elegidos:
                tiempos += cr.correr_pliegue(ctx, "BLQ-75", f, plan, piloto=True)  # sin candado: no escribe nada
            self.assertFalse((r.raiz_v2 / cr.CARPETA).exists())
            t = pd.DataFrame(tiempos)
            self.assertTrue({"vecindario", "lightgbm", "lineales", "interno_mlp"} <= set(t["tarea"]))
            planes = {rc: {"pm25": {"BLQ-75": cr.plan_protocolo(ctx.recetas, "BLQ-75", cr.Opciones(recorte=rc), False)}}
                      for rc in (0, 1, 2, 3)}
            est = cr.estimar_presupuesto(t, planes, {"pm25": {"BLQ-75": 4}}, 120.0)
            horas = [est["por_recorte"][str(rc)]["horas"] for rc in (0, 1, 2, 3)]
            self.assertTrue(all(a >= b for a, b in zip(horas, horas[1:])))
            self.assertEqual(est["recorte_sugerido"], 0)

    def test_plan_y_recortes(self):
        rec = mv.recetas_de(CFG, 2)

        def ids(prot, rc=0, calidad=True):
            p = cr.plan_protocolo(rec, prot, cr.Opciones(recorte=rc), calidad)
            return {(t.id, t.replica) for t in p["tareas"]}, p

        lro, p_lro = ids("LRO")
        self.assertIn(("mlp", 2), lro)
        self.assertIn(("lightgbm_ntodas", 0), lro)
        self.assertIn(("lightgbm_cal_solo_validado", 0), lro)
        self.assertEqual(p_lro["interno"], list(mv.MOTORES_EJE_A))
        lpo, p_lpo = ids("LPO")
        self.assertFalse(any(r for _, r in lpo))
        self.assertFalse(any("_n" in i for i, _ in lpo))
        self.assertEqual(p_lpo["interno"], [])
        self.assertNotIn(("lightgbm_cal_solo_validado", 0), ids("BLQ-75")[0])
        self.assertNotIn(("lightgbm_cal_solo_validado", 0), ids("LRO", calidad=False)[0])
        self.assertFalse(any(r for _, r in ids("BLQ-75", 1)[0]))             # 1: semillas sólo en LRO
        self.assertTrue(any(r for _, r in ids("LRO", 1)[0]))
        self.assertFalse(any("_n" in i for i, _ in ids("BLQ-75", 2)[0]))     # 2: curvas sólo en LRO
        self.assertNotIn(("mlp", 0), ids("LOSO-D", 3)[0])                    # 3: MLP sólo en LRO y BLQ-75
        self.assertIn(("mlp", 0), ids("BLQ-75", 3)[0])
        self.assertEqual(len(ids("LOSO-D")[0]), 4 + 10 + 1 + 3 + 2)


R_REAL = rv.RutasV2.desde_entorno()


@unittest.skipUnless(R_REAL.manifiesto_pliegues.exists(), "falta el manifiesto de pliegues real")
class ConsolaTests(unittest.TestCase):
    def test_plan_real_no_escribe(self):
        import contextlib
        import io
        import logging
        antes = sorted(p.name for p in R_REAL.raiz_v2.iterdir())
        raiz_log = logging.getLogger()
        nivel, manejadores = raiz_log.level, list(raiz_log.handlers)
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                cr.main(["plan", "--contaminantes", "pm25", "--protocolos", "LRO", "LPO"])
        finally:                                                           # main configura el registro en INFO
            raiz_log.handlers[:] = manejadores
            raiz_log.setLevel(nivel)
        texto = buf.getvalue()
        self.assertIn("pm25 LRO: 15 pliegues", texto)
        self.assertIn("internos lightgbm/xgboost/random_forest/mlp", texto)
        self.assertEqual(antes, sorted(p.name for p in R_REAL.raiz_v2.iterdir()))


if __name__ == "__main__":
    unittest.main()
