"""Pruebas de punta a punta de ``correr_v2`` con datos sintéticos pequeños (``_sintetico_v2``), en raíces temporales:

* mismas filas entre motores (permutación común, topes anidados) y mismos pares de evaluación para todos;
* determinismo: dos corridas completas idénticas bit a bit (puntos de control, OOF y métricas);
* la regla única de exclusión en los cuatro lugares: filas de entrenamiento, vecindario de entrenamiento y de
  prueba (multiplicar por 3 las observaciones de las estaciones excluidas no cambia ni un bit del pliegue) y
  residuos de la retransformación (el entorno de LBO-10 no entra en la corrección del pliegue);
* reanudación por firma, consolidación que exige todos los pliegues, piloto sin predicciones, plan con los
  recortes de §10 y traza sin rutas absolutas;
* Enmienda 1: la firma lleva la lista de predictores, la pérdida, la variante de calidad y los sha256 del contrato
  y de la configuración (cambiar los predictores invalida los puntos de control, punto 14); el candado es el del
  pliegue (punto 14); el δ de Huber es común y honesto (punto 9); la validación de la MLP es por conglomerados o
  grupos completos, con el vecindario sin las estaciones de validación (punto 6); y el sellado en git (punto 14);
* consolidación de la Enmienda 1: las dos formas de la retransformación y la sensibilidad con OOF interno (punto 2),
  los bloques de inferencia (punto 5: el bloque de 75 km en LBO-10, no el conglomerado), Δ_r, Δ̄ y el ruido de la
  diferencia cotejados con la tabla de métricas (punto 3), la segunda prueba, LPO descriptivo, las métricas por
  conjunto de evaluación con la corrección registrada (puntos 7 y 10), la evidencia de la decisión y ``decidir``
  de punta a punta (punto 11);
* Complemento de la Enmienda 1: el orden de recortes en el plan, coherente con el piloto y la bitácora (punto 8);
  la segunda prueba que decide es el cambio de signo, con B = 1.999 (puntos 1 y 2); el amortiguador de 10 km en
  las particiones internas de BLQ-75 —validación de la MLP, pliegues internos y partición honesta del δ de Huber—
  (punto 5), medido sólo desde las estaciones del conjunto interno de validación con filas en el entrenamiento; la
  firma con el hash del código de las funciones de ajuste, ``_semillas`` incluida, y con las semillas efectivas
  (cambiarlas vence los puntos; punto 7); el candado normalizado (punto 10); la factibilidad de los dos
  contaminantes (punto 3) y el régimen fila a fila con las columnas de las familias leídas del panel;
* guardas de la consola: el recorte sale del plan del piloto (otro, o un plan que no sirve, sólo con
  --forzar-recorte, que queda en la bitácora; punto 8) y B = 1.999 en consolidar y decidir (otro sólo con --forzar,
  que queda registrado; punto 2).
"""
from __future__ import annotations

import contextlib
import copy
import dataclasses
import importlib.util
import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))
sys.path.insert(0, str(V2 / "tests"))
import _rutas_v2 as rv  # noqa: E402
import _sintetico_v2 as sx  # noqa: E402
import bootstrap_v2 as bs  # noqa: E402
import correr_v2 as cr  # noqa: E402
import decision_v2 as dc  # noqa: E402
import metricas_v2 as mt  # noqa: E402
import motores_v2 as mv  # noqa: E402
import perdidas_v2 as pv  # noqa: E402
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
    for f in ctx.pliegues(prot):
        if pliegues is None or int(f["k"]) in pliegues:
            # el candado del artefacto: el del pliegue (Enmienda 1, punto 14), como en main
            with rv.candado_escritura(cr.nombre_candado_pliegue(ctx.etiqueta, ctx.pol, prot, f["k"]), rutas=ctx.rutas):
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
        claves = ["conjunto", "nivel", "desagregacion", "estrato", "ponderacion", "escala"]
        n_por_motor = m.groupby(claves)["n"].nunique()
        self.assertTrue((n_por_motor == 1).all())                             # el mismo n para todos los motores
        self.assertEqual(self.res["consolidado"]["pares"]["pares_comunes"], int(self.res["comunes"].sum()))
        motores = set(m["motor"])
        for esperado in ("lightgbm", "xgboost", "random_forest", "mlp", "promedio", "apilado", "gp", "lme", "gwr", "rk",
                         "idw", "lightgbm_huber", "xgboost_huber_friedman", "xgboost_q50", "lightgbm@r2", "lightgbm~sens",
                         "lightgbm_ntodas", "lightgbm_cal_solo_validado", "lightgbm~lognormal", "xgboost~lognormal@r1",
                         "lightgbm~sens~lognormal", "gp~lognormal", "apilado~lognormal"):
            self.assertIn(esperado, motores)
        self.assertNotIn("alertas_q80", motores)                              # las alertas se juzgan aparte
        self.assertEqual(set(m["conjunto"]), {mt.E1, mt.E2, mt.E2_SINCA, mt.E1_PRIMA})     # punto 7
        apilado = self.res["consolidado"]["apilado"]["pesos_por_pliegue"]
        for w in apilado.values():
            self.assertAlmostEqual(sum(w.values()), 1.0, places=12)
            self.assertTrue(all(v >= 0 for v in w.values()))

    def test_cuantiles_reordenados_y_calibrados(self):
        """Enmienda 1, punto 9: los cuantiles llegan reordenados y con el intervalo CQR, que no es una predicción
        puntual ni entra en las métricas comunes."""
        c = self.res["cuantiles"]
        self.assertTrue({"lightgbm", "lightgbm_cqr", "xgboost", "xgboost_cqr"} <= set(c["motor"]))
        self.assertEqual(sorted(self.res["consolidado"]["cuantiles"]), ["lightgbm", "xgboost"])
        p = self.res["pred"]
        for m in mv.MOTORES_PERDIDAS:
            ok = np.isfinite(p[f"{m}_q05"]) & np.isfinite(p[f"{m}_q50"]) & np.isfinite(p[f"{m}_q95"])
            self.assertTrue((p[f"{m}_q05"][ok] <= p[f"{m}_q50"][ok]).all())
            self.assertTrue((p[f"{m}_q50"][ok] <= p[f"{m}_q95"][ok]).all())
            self.assertNotIn(f"{m}_cqr_q05", set(self.res["metricas"]["motor"]))

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
        # LRO: 3 pliegues × (36 tareas + 2 de calidad + vecindario) + 3 × 2 internos × 4 bases; LBO-10: 8 × (20 + 1)
        # (las pérdidas incluyen la sensibilidad huber_friedman de la Enmienda 1, punto 9)
        self.assertEqual(len(a["puntos"]), 3 * 39 + 3 * 2 * 4 + 8 * 21)
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
            kw = {"conglomerado_de_estacion": ctx.conglomerado_de_estacion()}      # respaldo honesto (punto 2)
            _, adj, _, _ = rt.duan_fuera_de_pliegue(z, *args, **kw)
            np.testing.assert_allclose(res["pred"]["lightgbm"], rt.retransformar(z, adj), rtol=1e-6)
            est = ctx.vec.estaciones[ctx.vec.js]
            z2 = z.copy()
            z2[est == "B"] += 1.5
            _, adj2, _, _ = rt.duan_fuera_de_pliegue(z2, *args, **kw)
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
            with rv.candado_artefactos([ruta], rutas=r):
                cr.guardar_punto(ruta, arr, meta, r)
            _, t3 = correr_protocolo(ctx, "LOSO-D", op, pliegues=[0])
            self.assertEqual(sorted(t["tarea"] for t in t3), ["vecindario", "xgboost"])
            with self.assertRaises(cr.Incompleto):                           # faltan los demás pliegues
                cr.consolidar(ctx, "LOSO-D", plan, escribir=False)
            with self.assertRaises(rv.EscrituraNoPermitida):                  # sin candado no se escribe
                cr.correr_pliegue(ctx, "LOSO-D", ctx.pliegues("LOSO-D")[1], plan)
            otro = cr.nombre_candado_pliegue(ctx.etiqueta, ctx.pol, "LOSO-D", 0)
            with rv.candado_escritura(otro, rutas=r), self.assertRaises(rv.EscrituraNoPermitida):
                cr.correr_pliegue(ctx, "LOSO-D", ctx.pliegues("LOSO-D")[1], plan)   # el candado de otro pliegue no basta

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
        self.assertEqual(len(ids("LOSO-D")[0]), 4 + 12 + 1 + 3 + 2)         # 12 pérdidas: con huber_friedman
        self.assertEqual(cr.niveles_de_recorte(rec), (0, 1, 2, 3, 4))

    def test_orden_de_recortes_del_punto_12(self):
        """Enmienda 1, punto 12, en el código (Complemento, punto 8): 1 curvas fuera de LRO; 2 MLP fuera de LRO y
        BLQ-75; 3 semillas fuera de LRO y BLQ-75 (con el §8 no quita nada); 4 pérdidas fuera de LRO, BLQ-75 y
        LOSO-D. Cada recorte incluye a los anteriores y el plan sale de la configuración."""
        rec = mv.recetas_de(CFG, 2)

        def tareas(prot, rc):
            return {(t.id, t.replica) for t in cr.plan_protocolo(rec, prot, cr.Opciones(recorte=rc), True)["tareas"]}

        curva, mlp, semilla, perdida = ("lightgbm_ntodas", 0), ("mlp", 0), ("xgboost", 1), ("lightgbm_huber", 0)
        # recorte 1: curvas sólo en LRO (BLQ-75 las pierde); nada más cambia
        self.assertIn(curva, tareas("BLQ-75", 0))
        self.assertNotIn(curva, tareas("BLQ-75", 1))
        self.assertIn(curva, tareas("LRO", 4))
        self.assertIn(semilla, tareas("BLQ-75", 1))                          # las semillas de BLQ-75 se conservan
        # recorte 2: MLP sólo en LRO y BLQ-75
        for prot in ("LOSO-D", "LBO-10", "LPO"):
            self.assertIn(mlp, tareas(prot, 1))
            self.assertNotIn(mlp, tareas(prot, 2))
        for prot in ("LRO", "BLQ-75"):
            self.assertIn(mlp, tareas(prot, 4))
        # recorte 3: semillas fuera de LRO y BLQ-75: leído con el §8 no quita nada (se traduce tal cual)
        for prot in cr.PROTOCOLOS:
            self.assertEqual(tareas(prot, 2), tareas(prot, 3), prot)
        self.assertIn(semilla, tareas("LRO", 4))
        self.assertIn(semilla, tareas("BLQ-75", 4))
        # recorte 4: pérdidas del §6 fuera de LRO, BLQ-75 y LOSO-D
        for prot in ("LBO-10", "LPO"):
            self.assertIn(perdida, tareas(prot, 3))
            self.assertFalse(any(i.startswith(("lightgbm_", "xgboost_")) and "_n" not in i and "_cal_" not in i
                                 for i, _ in tareas(prot, 4)), prot)
        for prot in ("LRO", "BLQ-75", "LOSO-D"):
            self.assertIn(perdida, tareas(prot, 4))
            self.assertIn((cr.TAREA_DELTA_HUBER, 0), tareas(prot, 4))
        # los recortes sólo quitan, y son los de la configuración, en su orden
        for prot in cr.PROTOCOLOS:
            previo = tareas(prot, 0)
            for rc in range(1, 5):
                actual = tareas(prot, rc)
                self.assertLessEqual(actual, previo, (prot, rc))
                previo = actual
        p4 = cr.plan_protocolo(rec, "LBO-10", cr.Opciones(recorte=4), True)
        self.assertEqual(p4["recortes_aplicados"], [x["recorte"] for x in CFG["presupuesto"]["orden_de_recortes"]])
        self.assertFalse(p4["perdidas"] or p4["mlp"] or p4["curvas"])
        self.assertEqual([x["elemento"] for x in rec["recortes"]], ["curvas_de_aprendizaje", "mlp", "semillas", "perdidas"])
        with self.assertRaises(ValueError):
            cr.plan_protocolo(rec, "LRO", cr.Opciones(recorte=5), True)
        # coherente con el piloto: decidir_recortes recorre los mismos 0 … 4 y anota los textos de la configuración
        import piloto_v2 as plt
        est = {"por_recorte": {str(i): {"horas": h, "horas_menos_contencion": h, "horas_media_global": h,
                                        "horas_sin_contencion_fuerte": h, "horas_cpu": h}
                               for i, h in enumerate([200, 190, 150, 150, 100])}}
        d = plt.decidir_recortes(est, 120.0, CFG["presupuesto"]["orden_de_recortes"])
        self.assertEqual(d["recorte"], 4)
        self.assertEqual(d["aplicados"], p4["recortes_aplicados"])
        # y con la bitácora: anotar_recorte deja los mismos textos en el manifiesto
        with sx.raices_temporales() as r:
            with rv.candado_escritura("pliegues", rutas=r):
                rv.publicar_json(sx.manifiesto_sintetico(sx.panel_sintetico(dias=10)), r.manifiesto_pliegues, r)
            with mock.patch.object(cr, "cargar_config", lambda rutas=None, verificar_contrato=True: CFG):
                cr.anotar_recorte(r, 4, cr.ETIQUETA)
                cr.anotar_recorte(r, 4, cr.ETIQUETA)                        # una sola vez
            ev = [e for e in json.loads(r.manifiesto_pliegues.read_text(encoding="utf-8"))["bitacora"]
                  if e.get("evento") == "recorte_presupuesto"]
            self.assertEqual(len(ev), 1)
            self.assertEqual(ev[0]["aplicados"], p4["recortes_aplicados"])


SOLO_EJE_A = dict(perdidas=False, alertas=False, eje_b=False, curvas=False, semillas=False, apilado=False, calidad=False)


def filas_con_tope(ctx, prot, pliegue):
    ent, _, _ = ctx.vec.mascaras(pliegue, prot)
    return mv.filas_tope(mv.permutacion(np.flatnonzero(ent), mv.semilla_permutacion(int(pliegue["k"]), 0)),
                         ctx.recetas["N_comun"])


class FirmaTests(unittest.TestCase):
    """Enmienda 1, punto 14: la firma lleva la lista ordenada de predictores, la receta, la pérdida, la variante de
    calidad y los sha256 del contrato y de la configuración."""

    def test_cambiar_los_predictores_invalida_los_puntos(self):
        with sx.raices_temporales() as r:
            panel = sx.panel_sintetico()
            ctx = contexto(r, panel, con_calidad=False)
            op = cr.Opciones(motores=("lightgbm", "random_forest"), **SOLO_EJE_A)
            plan, _ = correr_protocolo(ctx, "LOSO-D", op, pliegues=[0])
            f = ctx.pliegues("LOSO-D")[0]
            cfg2 = copy.deepcopy(CFG)
            preds = cfg2["motores"]["eje_A"]["predictores"]["pm25"]
            cfg2["motores"]["eje_A"]["predictores"]["pm25"] = [preds[1], preds[0], *preds[2:]]   # los mismos, otro orden
            ctx2 = cr.Contexto.desde_tablas("pm25", panel, sx.manifiesto_sintetico(panel), cfg2, r, hilos=2)
            self.assertNotEqual(ctx.huellas_firma()["predictores"], ctx2.huellas_firma()["predictores"])
            self.assertEqual(ctx2.huellas_firma()["predictores"]["n"], len(preds))
            rec = ctx.vec.para_pliegue(f, "LOSO-D", registrar=False)
            filas = filas_con_tope(ctx, "LOSO-D", f)
            for t in plan["tareas"]:
                with self.subTest(tarea=t.id):
                    self.assertNotEqual(cr.firma_tarea(ctx, "LOSO-D", f, t, rec.registro["sha256"], filas),
                                        cr.firma_tarea(ctx2, "LOSO-D", f, t, rec.registro["sha256"], filas))
                    with self.assertRaises(cr.Incompleto):                    # el punto viejo queda vencido
                        cr._leer_vigente(ctx2, "LOSO-D", f, t, rec.registro["sha256"], filas)
            _, t2 = correr_protocolo(ctx2, "LOSO-D", op, pliegues=[0])        # y se rehace todo
            self.assertEqual(sorted(x["tarea"] for x in t2), sorted(["vecindario", *(t.id for t in plan["tareas"])]))
            meta = cr.leer_punto(cr.ruta_punto(ctx2, "LOSO-D", 0, "r0", "lightgbm"))[1]
            self.assertEqual(meta["firma_componentes"]["predictores"], ctx2.huellas_firma()["predictores"])

    def test_contrato_configuracion_perdida_y_calidad_entran_en_la_firma(self):
        with sx.raices_temporales() as r:
            panel = sx.panel_sintetico()
            ctx = contexto(r, panel)
            f = ctx.pliegues("LRO")[0]
            huella = {"x": "y"}
            filas = filas_con_tope(ctx, "LRO", f)
            t = cr.Tarea("lightgbm", "lightgbm", "eje_A")
            base = cr.firma_tarea(ctx, "LRO", f, t, huella, filas)
            cfg3 = copy.deepcopy(CFG)
            cfg3["operacion"]["nota"] = "otra nota"                           # cualquier cambio de la configuración
            ctx3 = cr.Contexto.desde_tablas("pm25", panel, sx.manifiesto_sintetico(panel), cfg3, r, hilos=2,
                                            calidad=calidad_sintetica(panel))
            self.assertNotEqual(base, cr.firma_tarea(ctx3, "LRO", f, t, huella, filas))
            self.assertEqual(ctx.huellas_firma()["contrato"], CFG["contrato"]["sha256"])     # sin archivo: el declarado
            r.contrato.write_text("otro contrato\n", encoding="utf-8")
            ctx4 = cr.Contexto.desde_tablas("pm25", panel, sx.manifiesto_sintetico(panel), CFG, r, hilos=2,
                                            calidad=calidad_sintetica(panel))
            self.assertNotEqual(ctx4.huellas_firma()["contrato"], CFG["contrato"]["sha256"])
            self.assertNotEqual(base, cr.firma_tarea(ctx4, "LRO", f, t, huella, filas))
            t_cal = cr.Tarea("lightgbm_cal_solo_validado", "lightgbm", "calidad", calidad="solo_validado")
            self.assertEqual(cr.variante_calidad_de(ctx, t_cal)["codigos"], ctx.codigos_qc("solo_validado"))
            self.assertEqual(cr.perdida_de(ctx, cr.Tarea("x", "xgboost", "perdidas", variante="huber_friedman"))["regla_delta"],
                             "friedman")
            self.assertEqual(cr.perdida_de(ctx, t)["variante"], "l2_log_smearing")


class HuberCorrerTests(unittest.TestCase):
    """Enmienda 1, punto 9: δ común a LightGBM y XGBoost, de residuos honestos del l2_original de LightGBM."""

    @classmethod
    def setUpClass(cls):
        cls._raices = sx.raices_temporales()
        cls.r = cls._raices.__enter__()
        cls.ctx = contexto(cls.r, con_calidad=False)
        op = cr.Opciones(motores=("lightgbm", "xgboost"), alertas=False, eje_b=False, curvas=False, semillas=False,
                         apilado=False, calidad=False)
        cls.plan, _ = correr_protocolo(cls.ctx, "LOSO-D", op, pliegues=[0])
        cls.f = cls.ctx.pliegues("LOSO-D")[0]
        cls.filas = filas_con_tope(cls.ctx, "LOSO-D", cls.f)

    @classmethod
    def tearDownClass(cls):
        cls._raices.__exit__(None, None, None)

    def meta(self, tarea_id):
        return cr.leer_punto(cr.ruta_punto(self.ctx, "LOSO-D", 0, "r0", tarea_id))[1]

    def test_delta_comun_registrado(self):
        info = self.meta("lightgbm_l2_original")["info"]
        d, d_f = info["delta_huber"], info["delta_huber_friedman"]
        self.assertTrue(d > 0 and d_f > 0)
        ph = info["particion_honesta"]
        self.assertEqual(ph["semilla"], [42, 0, 1001])
        self.assertEqual(sum(ph["filas"]), len(self.filas))
        self.assertTrue(ph["conglomerados"][0] and ph["conglomerados"][1])
        self.assertNotIn("delta_huber", self.meta("xgboost_l2_original")["info"])     # el δ sale sólo de LightGBM
        for motor in mv.MOTORES_PERDIDAS:
            with self.subTest(motor=motor):
                m, mf = self.meta(f"{motor}_huber"), self.meta(f"{motor}_huber_friedman")
                self.assertEqual(m["extra_firma"], {"delta_huber": d, "regla_delta": "mad"})
                self.assertEqual(mf["extra_firma"], {"delta_huber": d_f, "regla_delta": "friedman"})
                reg = m["info"]["registro_huber"]
                self.assertEqual((reg["delta"], reg["filas"]), (d, len(self.filas)))
                self.assertTrue(0.0 <= reg["fraccion_recortada"] <= 1.0)
                self.assertTrue(np.isfinite(reg["perdida_final"]))
                self.assertIn("no estima la media", m["info"]["declaracion"])
        self.assertEqual(cr.delta_huber_honesto(self.ctx, "LOSO-D", self.f, self.filas)["delta_huber"], d)

    def test_residuos_honestos(self):
        """Cada mitad se predice con el modelo ajustado en la otra: sumar c a las observaciones de la mitad 1 corre
        sus residuos exactamente en c, y cambia los de la mitad 0 (cuyo modelo sí vio a la mitad 1)."""
        _, r0, en_1 = cr.delta_huber_honesto(self.ctx, "LOSO-D", self.f, self.filas, devolver_residuos=True)
        y2 = self.ctx.y.copy()
        y2[self.filas[en_1]] += 7.0
        _, r2, _ = cr.delta_huber_honesto(dataclasses.replace(self.ctx, y=y2), "LOSO-D", self.f, self.filas,
                                          devolver_residuos=True)
        np.testing.assert_allclose(r2[en_1] - r0[en_1], 7.0, rtol=0, atol=1e-9)
        self.assertFalse(np.allclose(r2[~en_1], r0[~en_1]))

    def test_huber_sin_el_delta_comun_falla(self):
        with sx.raices_temporales() as r:
            ctx = contexto(r, con_calidad=False)
            op = cr.Opciones(motores=("xgboost",), alertas=False, eje_b=False, curvas=False, semillas=False,
                             apilado=False, calidad=False)
            with self.assertRaises(RuntimeError) as e:
                correr_protocolo(ctx, "LOSO-D", op, pliegues=[0])
            self.assertIn("lightgbm_l2_original", str(e.exception))


class ValidacionMLPCorrerTests(unittest.TestCase):
    """Enmienda 1, punto 6: validación por conglomerados LOSO-D o por grupos completos, con el vecindario recalculado
    sin las estaciones de validación."""

    def test_lro_valida_con_regiones_completas(self):
        with sx.raices_temporales() as r:
            ctx = contexto(r, con_calidad=False)
            f = next(p for p in ctx.pliegues("LRO") if p["grupo"] == "RC")       # entrenan RA y RB
            filas = filas_con_tope(ctx, "LRO", f)
            val = cr.validacion_mlp(ctx, "LRO", filas, f["excluidas"], 43, {"protocolo": "LRO", "k": f["k"]})
            reg = val.registro
            self.assertEqual(reg["unidad"], "grupos completos del protocolo")
            self.assertEqual(len(reg["grupos"]), 1)
            g_est = ctx.grupo_de_estacion("LRO")
            estaciones = sorted(str(s) for s in ctx.vec.estaciones[np.isin(g_est, reg["grupos"])])
            self.assertEqual(reg["estaciones"], estaciones)
            est_filas = ctx.estaciones_de(filas)
            np.testing.assert_array_equal(val.filas, np.isin(est_filas, estaciones))      # la región entera
            rec = ctx.vec.recalcular(sorted(set(f["excluidas"]) | set(estaciones)), registrar=False)
            np.testing.assert_array_equal(val.X, ctx.matriz(filas, rec))       # vecindario sin las de validación
            self.assertFalse(np.array_equal(val.X, ctx.matriz(filas, ctx.vec.para_pliegue(f, "LRO", registrar=False))))

    def test_loso_valida_con_conglomerados_enteros(self):
        with sx.raices_temporales() as r:
            ctx = contexto(r, con_calidad=False)
            f = next(p for p in ctx.pliegues("LOSO-D") if p["grupo"] == "H")
            filas = filas_con_tope(ctx, "LOSO-D", f)
            vistos = set()
            for semilla in range(40):
                val = cr.validacion_mlp(ctx, "LOSO-D", filas, f["excluidas"], semilla)
                self.assertEqual(val.registro["unidad"], "conglomerados LOSO-D")
                self.assertEqual(len(val.registro["conglomerados"]), 1)        # round(0,1 × 8) = 1
                vistos.update(val.registro["conglomerados"])
                if val.registro["conglomerados"] == ["A1+A2"]:
                    self.assertEqual(val.registro["estaciones"], ["A1", "A2"])     # el conglomerado entero
            self.assertIn("A1+A2", vistos)

    def test_el_punto_de_la_mlp_registra_su_validacion(self):
        with sx.raices_temporales() as r:
            ctx = contexto(r, con_calidad=False)
            correr_protocolo(ctx, "BLQ-75", cr.Opciones(motores=("mlp",), **SOLO_EJE_A), pliegues=[0])
            info = cr.leer_punto(cr.ruta_punto(ctx, "BLQ-75", 0, "r0", "mlp"))[1]["info"]
            self.assertEqual(info["validacion"]["unidad"], "grupos completos del protocolo")
            self.assertTrue(info["validacion_agrupada"])
            self.assertTrue(info["vecindario_validacion_recalculado"])
            self.assertEqual(info["epocas_reajuste"], info["mejor_epoca"])
            self.assertIn("sha256", info["validacion"]["vecindario"])


class CuantilesConsolidacionTests(unittest.TestCase):
    """Enmienda 1, punto 9: al consolidar, los cuantiles se reordenan y el intervalo se calibra con CQR agrupado."""

    def test_calibrar_cuantiles(self):
        with sx.raices_temporales() as r:
            ctx = contexto(r, con_calidad=False)
            prot = "LRO"
            pdf = np.full(ctx.n, -1, dtype="int64")
            excl = {}
            for f in ctx.pliegues(prot):
                _, prueba, _ = ctx.vec.mascaras(f, prot)
                pdf[prueba] = int(f["k"])
                excl[int(f["k"])] = ctx.vec.indices(f["excluidas"])
            q50 = (ctx.y * 0.9 + 1.0).astype("float32")
            q05, q95 = (q50 * 0.98).astype("float32"), (q50 * 1.02).astype("float32")   # demasiado estrecho
            q05[:50], q95[:50] = q95[:50].copy(), q05[:50].copy()                   # 50 filas cruzadas
            pred = {"lightgbm_q05": q05, "lightgbm_q50": q50, "lightgbm_q95": q95, "lightgbm": q50.copy()}
            reg = cr.calibrar_cuantiles(ctx, prot, pred, pdf, excl, False)
            self.assertEqual(list(reg), ["lightgbm"])                              # sin cuantiles de XGBoost
            self.assertEqual(reg["lightgbm"]["reordenamiento"]["filas_con_cruce"], 50)
            self.assertTrue((pred["lightgbm_q05"] <= pred["lightgbm_q50"]).all())
            self.assertTrue((pred["lightgbm_q50"] <= pred["lightgbm_q95"]).all())
            for nombre in ("lightgbm_cqr_q05", "lightgbm_cqr_q95"):
                self.assertEqual(pred[nombre].shape, (ctx.n,))
                self.assertTrue(np.isfinite(pred[nombre]).all())
            cqr = reg["lightgbm"]["cqr"]
            self.assertEqual(sum(cqr["filas_por_nivel"].values()), ctx.n)
            self.assertEqual(cqr["nivel"], 0.9)
            # en LRO sintético cada región tiene macrozonas propias: la clave cae a la franja de los demás
            self.assertIn("franja", {x["nivel"] for x in cqr["por_pliegue_y_clave"]})
            self.assertTrue(all(x["Q"] > 0 for x in cqr["por_pliegue_y_clave"]))          # el intervalo base era estrecho
            self.assertGreater(pv_cobertura(ctx.y, pred["lightgbm_cqr_q05"], pred["lightgbm_cqr_q95"]),
                               pv_cobertura(ctx.y, pred["lightgbm_q05"], pred["lightgbm_q95"]))


def pv_cobertura(y, lo, hi):
    import perdidas_v2 as pv
    return pv.cobertura(y, lo, hi)


class SelladoTests(unittest.TestCase):
    def test_sellado_antes_de_correr(self):
        with sx.raices_temporales() as r:
            with self.assertRaises(SystemExit):
                cr.verificar_sellado(r, git={"commit": "abc", "v2_sin_commit": ["scripts_modelo_1km/v2/correr_v2.py"]})
            with self.assertRaises(SystemExit):
                cr.verificar_sellado(r, git={"commit": "desconocido"})
            with self.assertRaises(SystemExit):
                cr.verificar_sellado(r)                                         # sin git: no hay sellado
            self.assertTrue(cr.verificar_sellado(r, git={"commit": "abc", "v2_sin_commit": []})["sellado"])
            sin = cr.verificar_sellado(r, permitir_sin_sellar=True, git={"commit": "abc", "v2_sin_commit": ["x"]})
            self.assertFalse(sin["sellado"])


class ConsolidacionEnmiendaTests(unittest.TestCase):
    """Enmienda 1 en la consolidación (puntos 2, 3, 5, 7, 10 y 11) y ``decidir``, con datos sintéticos."""

    OP = cr.Opciones(perdidas=False, alertas=False, eje_b=False, curvas=False)
    OP_LPO = cr.Opciones(motores=("lightgbm", "xgboost"), perdidas=False, alertas=False, eje_b=False, curvas=False,
                         semillas=False, apilado=False)
    # segundos por día de superficies de cada motor en los dos contaminantes (Complemento, punto 3)
    FAC = {"lightgbm": {"pm25": 10.0, "no2": 8.0}, "xgboost": {"pm25": 12.0, "no2": 10.0},
           "random_forest": {"pm25": 20.0, "no2": 16.0}, "mlp": {"pm25": 6.0, "no2": 5.0}}

    @classmethod
    def setUpClass(cls):
        cls._raices = sx.raices_temporales()
        cls.r = cls._raices.__enter__()
        cls.ctx = contexto(cls.r)
        cls.res, cls.planes = {}, {}
        for prot, op in (("LRO", cls.OP), ("BLQ-75", cls.OP), ("LBO-10", cls.OP), ("LPO", cls.OP_LPO)):
            cls.planes[prot], _ = correr_protocolo(cls.ctx, prot, op)
            cls.res[prot] = cr.consolidar(cls.ctx, prot, cls.planes[prot], escribir=True, replicas_bootstrap=200)

    @classmethod
    def tearDownClass(cls):
        cls._raices.__exit__(None, None, None)

    def _boot(self, prot, a, b, est="delta_r2", nivel="diario_civil", pond=mt.PESO_FIJO, conjunto=mt.E1):
        tb = self.res[prot]["bootstrap"]
        x = tb[(tb["conjunto"] == conjunto) & (tb["nivel"] == nivel) & (tb["ponderacion"] == pond) & (tb["motor_a"] == a)
               & (tb["motor_b"] == b) & (tb["estadistico"] == est)]
        self.assertEqual(len(x), 1, f"{prot} {a} {b} {est}")
        return x.iloc[0]

    def test_formas_y_sensibilidad_interna(self):
        """Punto 2: primaria y ½·σ² en una pasada, con el respaldo honesto; OOF interno con las dos formas."""
        ctx, res = self.ctx, self.res["LRO"]
        pred, z, pdf = res["pred"], res["z"], res["pliegue_de_fila"]
        for nm in ("lightgbm~lognormal", "lightgbm~lognormal@r1", "promedio~lognormal@r2", "apilado~lognormal",
                   "lightgbm~sens", "lightgbm~sens~lognormal", "promedio~sens"):
            self.assertIn(nm, pred)
        excl = {int(f["k"]): ctx.vec.indices(f["excluidas"]) for f in ctx.pliegues("LRO")}
        congl = ctx.conglomerado_de_estacion()
        regla = rt.regla_de_config(CFG)
        R = rt.fuera_de_pliegue(z["lightgbm"], ctx.y, ctx.vec.js, ctx.macrozona, ctx.hora_local, pdf, excl, False,
                                conglomerado_de_estacion=congl, regla=regla)
        np.testing.assert_array_equal(pred["lightgbm"], R.pred[rt.SMEARING])
        np.testing.assert_array_equal(pred["lightgbm~lognormal"], R.pred[rt.LOGNORMAL])
        c = res["consolidado"]["retransformacion"]
        self.assertEqual(c["formas"], {"primaria": rt.SMEARING, "sensibilidad_fija": rt.LOGNORMAL, "sensibilidad": rt.SMEARING})
        self.assertEqual(c["forma_por_prediccion"]["xgboost@r1"], rt.SMEARING)
        self.assertEqual(c["forma_por_prediccion"]["xgboost~lognormal@r1"], rt.LOGNORMAL)
        self.assertEqual(c["forma_por_prediccion"]["lightgbm~sens"], f"{rt.SMEARING} (OOF interno)")
        reg = c["primaria_y_fija"]["lightgbm"]["por_pliegue_y_clave"]
        nombres = {str(s) for s in ctx.vec.estaciones}
        self.assertTrue(all(set(x["ajuste"]) == set(rt.FORMAS) and set(x["estaciones"]) <= nombres for x in reg))
        # OOF interno del pliegue 0: residuos de sus pliegues internos, grupo = pliegue externo de cada fila
        Rr = cr.reunir(ctx, "LRO", self.planes["LRO"])
        I = Rr["internos"][0]
        f = I["filas"]
        tabla = rt.tabla_interna(I["z"]["lightgbm"], ctx.y[f], ctx.macrozona[f], ctx.hora_local[f], estacion=ctx.vec.js[f],
                                 grupo=pdf[f], conglomerado_de_estacion=congl, regla=regla, retirado=0, excluidas=excl[0])
        te = pdf == 0
        ap = rt.aplicar_tabla(z["lightgbm"][te], ctx.macrozona[te], ctx.hora_local[te], tabla)
        np.testing.assert_array_equal(pred["lightgbm~sens"][te], ap.pred[rt.SMEARING])
        np.testing.assert_array_equal(pred["lightgbm~sens~lognormal"][te], ap.pred[rt.LOGNORMAL])
        self.assertNotIn("lightgbm~sens", self.res["LBO-10"]["pred"])        # sólo LRO y BLQ-75

    def test_bloques_de_inferencia(self):
        """Punto 5: región en LRO, bloque de 75 km en BLQ-75 y en LBO-10 (no el conglomerado), cuatrienio en LPO."""
        b = {p: self.res[p]["consolidado"]["bloques_de_inferencia"] for p in self.res}
        bloques_75 = sorted({v[2] for v in sx.ESTACIONES.values()})
        self.assertEqual((b["LRO"]["unidad"], b["LRO"]["bloques"]), ("region", ["RA", "RB", "RC"]))
        self.assertEqual(b["BLQ-75"]["bloques"], bloques_75)
        self.assertEqual((b["LBO-10"]["unidad"], b["LBO-10"]["bloques"]), ("bloque", bloques_75))
        self.assertEqual(b["LPO"]["bloques"], sorted({f["grupo"] for f in self.ctx.pliegues("LPO")}))
        # el bloque que rige: el de la configuración (Enmienda 1: RM y E004N083; después del anexo de la Enmienda 2, el
        # calculado, R16)
        bloque = dc.regla_de_config(CFG).bloque_mas_influyente
        self.assertEqual((b["LRO"]["bloque_mas_influyente"], b["BLQ-75"]["bloque_mas_influyente"]),
                         (bloque["LRO"], bloque["BLQ-75"]))
        tb = self.res["LBO-10"]["bootstrap"]
        self.assertEqual(set(tb[tb["conjunto"] == mt.E1]["bloques"]), {len(bloques_75)})   # 4 bloques, no 8 conglomerados
        self.assertEqual(len(self.ctx.pliegues("LBO-10")), 8)
        oof = pd.read_parquet(self.ctx.raiz() / "LBO-10" / "oof.parquet", columns=["estacion", "bloque_inferencia"])
        de = {s: v[2] for s, v in sx.ESTACIONES.items()}
        self.assertTrue((oof["bloque_inferencia"].astype(str) == oof["estacion"].astype(str).map(de)).all())

    def test_ruido_de_la_diferencia_cotejado_con_las_metricas(self):
        """Punto 3: Δ_r de cada réplica = diferencia de los R² de la tabla de métricas (mismos pares, nivel y
        ponderación); Δ̄ = media; ruido = rango; el apilado usa sus bases; sin réplicas, «no evaluada»."""
        m = self.res["LRO"]["metricas"]

        def r2(motor):
            x = m[(m["conjunto"] == mt.E1) & (m["nivel"] == "diario_civil") & (m["desagregacion"] == "total")
                  & (m["ponderacion"] == mt.PESO_FIJO) & (m["escala"] == "original") & (m["motor"] == motor)]
            return float(x["r2"].iloc[0])

        f = self._boot("LRO", "xgboost", "lightgbm")
        directos = [r2(bs.nombre_replica("xgboost", k)) - r2(bs.nombre_replica("lightgbm", k)) for k in range(3)]
        np.testing.assert_allclose([f["delta_r0"], f["delta_r1"], f["delta_r2"]], directos, rtol=0, atol=1e-12)
        self.assertAlmostEqual(f["delta"], float(np.mean(directos)), places=12)
        self.assertAlmostEqual(f["ruido"], float(np.ptp(directos)), places=12)
        self.assertEqual((f["origen_ruido"], f["supera_ruido"]), ("replicas", bool(abs(np.mean(directos)) > np.ptp(directos))))
        self.assertEqual((f["G"], f["gl_jackknife"], f["distribucion_salvaje"]), (3, 2, "webb"))
        self.assertEqual((f["segunda_prueba"], f["sorteos_salvaje"], f["G_salvaje"]), ("cambio_de_signo_salvaje", "9999", 3))
        self.assertTrue(np.isfinite(f["p_jackknife"]))                       # el CV3 sólo informa
        self.assertEqual(f["replicas"], 200)                                  # las de la prueba (por omisión, 1.999)
        self.assertEqual(self.res["LRO"]["consolidado"]["traza"]["semillas"]["bootstrap_salvaje"], [42, 3000, 3])
        self.assertEqual(f["bloque_influyente"], dc.regla_de_config(CFG).bloque_mas_influyente["LRO"])   # R16
        self.assertTrue(pd.isna(f["robusta_sin_bloque"]))                     # el LRO sintético no tiene ese bloque
        ap = self._boot("LRO", "apilado", "lightgbm")
        self.assertEqual((ap["origen_ruido"], ap["replicas_del_par"]), ("maximo_de_las_bases", 1))
        self.assertEqual(self._boot("LRO", "xgboost~lognormal", "lightgbm~lognormal")["origen_ruido"], "replicas")
        corr = self._boot("LRO", "xgboost~lognormal", "xgboost")
        self.assertEqual(corr["replicas_del_par"], 3)
        self.assertEqual((corr["retransformacion_a"], corr["retransformacion_b"]), (rt.LOGNORMAL, rt.SMEARING))
        tb = self.res["LBO-10"]["bootstrap"]
        x = tb[(tb["motor_a"] == "xgboost") & (tb["motor_b"] == "lightgbm")]
        self.assertTrue(x["ruido"].isna().all() and (x["origen_ruido"] == "sin_replicas").all())
        self.assertTrue(x["supera_ruido"].isna().all())
        self.assertTrue(x["a_supera_b"].map(lambda v: v is not True).all())   # sin ruido medido no se declara

    def test_lpo_descriptivo(self):
        tb = self.res["LPO"]["bootstrap"]
        self.assertGreater(len(tb), 0)
        self.assertTrue(tb["a_supera_b"].isna().all())
        self.assertTrue((tb["regla"] == "descriptivo").all())
        self.assertTrue(self.res["LPO"]["consolidado"]["bloques_de_inferencia"]["descriptivo"])
        self.assertIsNone(self.res["LPO"]["evidencia_decision"])

    def test_metricas_por_conjunto_y_retransformacion(self):
        m = self.res["LRO"]["metricas"]
        self.assertEqual(set(m["conjunto"]), {mt.E1, mt.E2, mt.E2_SINCA, mt.E1_PRIMA})
        forma = lambda motor: m[m["motor"] == motor]["retransformacion"].iloc[0]  # noqa: E731
        self.assertEqual((forma("lightgbm"), forma("lightgbm~lognormal")), (rt.SMEARING, rt.LOGNORMAL))
        self.assertEqual(forma("lightgbm~sens"), f"{rt.SMEARING} (OOF interno)")
        self.assertIn("regimen_fila_a_fila", set(m["desagregacion"]))
        ids = {x["id"] for x in mt.regimenes_de_config(CFG)}                 # los que rigen (R17, Enmienda 2)
        self.assertTrue(all(e.split(":")[0] in ids for e in m[m["desagregacion"] == "regimen"]["estrato"].unique()))
        self.assertTrue({"G", "G_efectivo", "estaciones_kish"} <= set(m.columns))
        c = self.res["LRO"]["consolidado"]
        self.assertEqual(c["conjuntos"]["evaluabilidad_E2"]["estado"], mt.SIN_CONFIRMACION)    # 3 regiones < 5
        self.assertIn("estaciones_sin_E2", c["conjuntos"]["registro"])
        self.assertIn("no calculado", c["ponderacion"]["sensibilidades"][mt.DESAGRUPAMIENTO])   # sin INE en la raíz

    def test_evidencia_de_la_decision(self):
        """Punto 11: sumas por bloque del nivel diario civil sobre los pares de la decisión, sin predicciones."""
        res = self.res["LRO"]
        ev = res["evidencia_decision"]
        self.assertIsNone(self.res["LBO-10"]["evidencia_decision"])
        self.assertEqual((ev["schema"], ev["protocolo"], ev["contaminante"]), (dc.SCHEMA_EVIDENCIA, "LRO", "pm25"))
        self.assertEqual(set(ev["vistas"]), {dc.V_E1, dc.V_E1_SIN, dc.V_E1_LOG, dc.V_E2})
        for v in ev["vistas"].values():
            self.assertEqual(set(v), {"bloques", "n", "sw", "swo", "swoo", "motores"})
            self.assertTrue(all(set(s) == {"se", "se2"} and len(s["se"]) == 3 for s in v["motores"].values()))
        self.assertTrue({"xgboost~lognormal@r2", "promedio@r1", "lightgbm"} <= set(ev["motores"]))
        self.assertEqual(ev["candidatos_ausentes"], [])
        self.assertGreaterEqual(ev["pares"]["pares_comunes"], res["consolidado"]["pares"]["pares_comunes"])
        self.assertTrue({"sensibilidad_oof_interno", "apilado", "variantes_de_calidad"} <= set(ev["pares"]["quita_por_familia"]))
        disco = json.loads((self.ctx.raiz() / "LRO" / cr.NOMBRE_EVIDENCIA).read_text(encoding="utf-8"))
        self.assertEqual(disco, json.loads(json.dumps(ev)))
        self.assertIn(cr.NOMBRE_EVIDENCIA, res["consolidado"]["archivos"])
        self.assertEqual(res["consolidado"]["decision"]["evidencia"], cr.NOMBRE_EVIDENCIA)

    def test_tablas_pequenas_en_output_files(self):
        """Las tablas del repositorio son un resumen (E1 y E2, pares principales); lo completo queda en la raíz v2."""
        b = pd.read_csv(self.r.salidas_v2 / "comparacion_principal_pm25_LRO_bootstrap.csv")
        self.assertEqual(set(b["conjunto"]), {mt.E1, mt.E2})
        pares = set(zip(b["motor_a"], b["motor_b"]))
        for par in (("xgboost", "lightgbm"), ("promedio", "lightgbm"), ("apilado", "lightgbm"),
                    ("xgboost~lognormal", "lightgbm~lognormal"), ("lightgbm~lognormal", "lightgbm")):
            self.assertIn(par, pares)
        self.assertFalse({("lightgbm~sens", "lightgbm"), ("lightgbm_cal_solo_validado", "lightgbm")} & pares)
        self.assertLess(len(b), len(self.res["LRO"]["bootstrap"]))
        completo = pd.read_parquet(self.ctx.raiz() / "LRO" / "bootstrap.parquet")
        self.assertEqual(len(completo), len(self.res["LRO"]["bootstrap"]))
        m = pd.read_csv(self.r.salidas_v2 / "comparacion_principal_pm25_LRO_metricas.csv")
        self.assertEqual(set(m["conjunto"]), {mt.E1, mt.E2})
        self.assertFalse(m["motor"].str.contains("@r", regex=False).any())
        self.assertFalse(set(m["desagregacion"]) & {"estacion", "regimen_fila_a_fila"})
        self.assertIn("xgboost~lognormal", set(m["motor"]))
        lateral = json.loads((self.r.salidas_v2 / "comparacion_principal_pm25_LRO.json").read_text(encoding="utf-8"))
        self.assertEqual(lateral["schema"], cr.SCHEMA_TABLAS)
        self.assertEqual(set(lateral["resumen"]), {"metricas", "bootstrap"})
        self.assertIn(cr.NOMBRE_EVIDENCIA, lateral["fuente"])

    def test_decidir_de_punta_a_punta(self):
        d = cr.decidir(self.r, CFG, "pm25", factibilidad=self.FAC, fuente_factibilidad={"archivo": "prueba"}, replicas=200)
        reg = d["registro"]
        self.assertEqual(len(d["tabla"]), 4 * 2 * 2)
        self.assertEqual(reg["contaminante"], "pm25")
        self.assertIn(reg["decision"]["motor"], ("lightgbm", *dc.CANDIDATOS))
        disco = json.loads((self.ctx.raiz() / "decision.json").read_text(encoding="utf-8"))
        self.assertEqual(disco["decision"], reg["decision"])
        self.assertEqual(set(reg["traza"]["insumos"]), {"evidencia_LRO", "evidencia_BLQ-75"})
        for nombre in ("comparacion_principal_pm25_decision.csv", "comparacion_principal_pm25_decision.json"):
            texto = (self.r.salidas_v2 / nombre).read_text(encoding="utf-8")
            self.assertNotIn("/Users/", texto)
            self.assertNotIn(str(self.r.raiz_v2.parent), texto)
        with self.assertRaises(ValueError):
            cr.decidir(self.r, CFG, "pm25", factibilidad=None, escribir=False, replicas=50)
        with self.assertRaises(cr.Incompleto):
            cr.decidir(self.r, CFG, "pm25", etiqueta="otra", factibilidad=self.FAC, escribir=False)
        self.assertEqual(reg["regla"]["replicas_exigidas"], 3)
        self.assertIn("cambio de signo", reg["regla"]["segunda_prueba"])
        self.assertEqual(reg["factibilidad"]["referencia"]["motor"], "lightgbm")
        self.assertNotIn("replicas_bootstrap_forzadas", reg)
        # un B forzado desde la consola (--forzar) queda registrado en la decisión
        B, forzado = cr.resolver_replicas_bootstrap(CFG, 200, "prueba rápida", "decidir")
        d_f = cr.decidir(self.r, CFG, "pm25", factibilidad=self.FAC, fuente_factibilidad={"archivo": "prueba"},
                         replicas=B, forzado=forzado, escribir=True)
        self.assertEqual(d_f["registro"]["replicas_bootstrap"], 200)
        self.assertEqual(d_f["registro"]["replicas_bootstrap_forzadas"], forzado)
        disco = json.loads((self.ctx.raiz() / "decision.json").read_text(encoding="utf-8"))
        self.assertEqual(disco["replicas_bootstrap_forzadas"]["motivo"], "prueba rápida")
        # la consolidación registra su B (y lo forzado, si lo hubo)
        c = self.res["LRO"]["consolidado"]
        self.assertEqual((c["replicas_bootstrap"], c["forzado"]), ({"B": 200, "del_contrato": 1999}, None))
        # el resumen de factibilidad_v2 sirve de fuente: sus segundos por día de los dos contaminantes; la regla la
        # aplica decision_v2 (Complemento, punto 3)
        ruta = self.r.datos / "factibilidad_produccion.json"

        def resumen(regla=None):
            d = {"schema": "airpollution.modelo-1km-v2.factibilidad-produccion.v2",
                 "contaminantes": {pol: {"produccion": {m: {"segundos_por_dia": v[pol], "marca_robusta": True}
                                                        for m, v in self.FAC.items()},
                                         "candidatos": {c: {"fuera_de_la_decision": False}
                                                        for c in ("xgboost", "random_forest", "mlp")}}
                                   for pol in ("pm25", "no2")}}
            if regla is not None:
                d["regla"] = regla
            return d

        ruta.write_text(json.dumps(resumen()), encoding="utf-8")
        fac, fuente = cr.factibilidad_de_los_dos(ruta, CFG)
        self.assertEqual({m: v["segundos_por_dia"] for m, v in fac.items()}, self.FAC)
        self.assertEqual(fuente["archivo"], "factibilidad_produccion.json")
        self.assertEqual(fuente["contaminantes"], ["pm25", "no2"])
        self.assertFalse(fac["xgboost"]["factibilidad_v2"]["fuera_de_la_decision"])
        uno, _ = cr.factibilidad_de_archivo(ruta, "no2")                     # la lectura de un contaminante sigue
        self.assertEqual(uno["xgboost"]["segundos_por_dia"], self.FAC["xgboost"]["no2"])
        d2 = cr.decidir(self.r, CFG, "pm25", factibilidad=fac, fuente_factibilidad=fuente, escribir=False, replicas=200)
        self.assertEqual(d2["registro"]["decision"], reg["decision"])
        self.assertEqual(d2["registro"]["traza"]["factibilidad"]["archivo"], "factibilidad_produccion.json")
        self.assertTrue(d2["registro"]["candidatos"]["xgboost"]["factibilidad"]["coincide_con_factibilidad_v2"])
        # el veredicto conjunto de factibilidad_v2 (factibilidad.candidatos[c].factible) manda sobre las marcas
        con_veredicto = resumen()
        con_veredicto["factibilidad"] = {"candidatos": {"mlp": {"factible": False}}}
        ruta.write_text(json.dumps(con_veredicto), encoding="utf-8")
        fac_v, _ = cr.factibilidad_de_los_dos(ruta, CFG)
        self.assertTrue(fac_v["mlp"]["factibilidad_v2"]["fuera_de_la_decision"])
        d3 = cr.decidir(self.r, CFG, "pm25", factibilidad=fac_v, fuente_factibilidad=fuente, escribir=False, replicas=200)
        self.assertFalse(d3["registro"]["candidatos"]["mlp"]["factibilidad"]["coincide_con_factibilidad_v2"])
        # el mapa simple {pol: {motor: s}} también sirve
        ruta.write_text(json.dumps({pol: {m: v[pol] for m, v in self.FAC.items()} for pol in ("pm25", "no2")}),
                        encoding="utf-8")
        self.assertEqual({m: v["segundos_por_dia"] for m, v in cr.factibilidad_de_los_dos(ruta, CFG)[0].items()}, self.FAC)
        # sin no2 no se puede aplicar la regla (se suman los dos contaminantes)
        sin_no2 = resumen()
        del sin_no2["contaminantes"]["no2"]
        ruta.write_text(json.dumps(sin_no2), encoding="utf-8")
        with self.assertRaises(SystemExit):
            cr.factibilidad_de_los_dos(ruta, CFG)
        # un resumen medido con la regla anterior al Complemento (7 días por contaminante) no sirve para decidir
        ruta.write_text(json.dumps(resumen({"umbral_dias_de_maquina": 7.0})), encoding="utf-8")
        with self.assertRaises(SystemExit):
            cr.factibilidad_de_los_dos(ruta, CFG)
        ruta.write_text(json.dumps(resumen({"umbral_dias_de_maquina": 21, "factor_maximo_frente_a_lightgbm": 4.0})),
                        encoding="utf-8")
        with self.assertRaises(SystemExit):
            cr.factibilidad_de_los_dos(ruta, CFG)
        ruta.write_text(json.dumps(resumen({"umbral_dias_de_maquina": 21, "factor_maximo_frente_a_lightgbm": 5.0})),
                        encoding="utf-8")
        self.assertIn("lightgbm", cr.factibilidad_de_los_dos(ruta, CFG)[0])


class FirmaCodigoTests(unittest.TestCase):
    """Complemento, punto 7: la firma lleva el hash del código de las funciones de ajuste (la validación de la MLP,
    el δ honesto de Huber y las demás que definen filas o vecindario), sin versión a mano."""

    def test_funciones_de_ajuste_en_la_firma(self):
        nombres = {f.__qualname__ for f in cr.FUNCIONES_AJUSTE}
        for esperado in ("validacion_mlp", "delta_huber_honesto", "amortiguador_interno", "definicion_internos",
                         "correr_internos", "correr_pliegue", "Contexto.matriz", "Contexto.mascara_calidad",
                         "_semillas", "estaciones_con_filas", "_crear", "Contexto.grupo_de_estacion"):
            self.assertIn(esperado, nombres)
        self.assertFalse(hasattr(cr, "VERSION_AJUSTE"))                       # sin versión a mano
        with sx.raices_temporales() as r:
            ctx = contexto(r, con_calidad=False)
            codigo = ctx.codigo_ajuste()
            self.assertEqual(set(codigo) - {"funciones"}, set(cr.CODIGO_AJUSTE))
            self.assertEqual(set(codigo["funciones"]) - {"conjunto"}, nombres)
            f = ctx.pliegues("LRO")[0]
            filas = filas_con_tope(ctx, "LRO", f)
            t_mlp = cr.Tarea("mlp", "mlp", "eje_A")
            base = cr.firma_tarea(ctx, "LRO", f, t_mlp, {"x": "y"}, filas)
            otra = {**cr.huella_funciones_ajuste(), "validacion_mlp": "0" * 64}
            with mock.patch.object(cr, "huella_funciones_ajuste", lambda: otra):
                self.assertNotEqual(cr.firma_tarea(ctx, "LRO", f, t_mlp, {"x": "y"}, filas), base)
                self.assertEqual(cr.componentes_firma(ctx, t_mlp)["codigo_ajuste"]["funciones"]["validacion_mlp"], "0" * 64)
            self.assertEqual(cr.firma_tarea(ctx, "LRO", f, t_mlp, {"x": "y"}, filas), base)

    def test_el_hash_cambia_con_el_codigo_y_no_con_la_documentacion(self):
        """El hash es del árbol sintáctico sin docstrings: cambiar el código lo cambia; cambiar un comentario o el
        docstring, no."""
        fuentes = {
            "base": '''
                def f(x):
                    """Doc."""
                    return x + 1
            ''',
            "doc": '''
                def f(x):
                    """Otra documentación, más larga."""
                    # un comentario nuevo
                    return x + 1   # y otro
            ''',
            "codigo": '''
                def f(x):
                    """Doc."""
                    return x + 2
            ''',
        }
        huellas = {}
        with tempfile.TemporaryDirectory() as tmp:
            for nombre, fuente in fuentes.items():
                ruta = Path(tmp) / f"mod_{nombre}.py"
                ruta.write_text(textwrap.dedent(fuente), encoding="utf-8")
                spec = importlib.util.spec_from_file_location(f"mod_{nombre}", ruta)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                huellas[nombre] = cr.huella_de_funcion(mod.f)
        self.assertEqual(huellas["base"], huellas["doc"])
        self.assertNotEqual(huellas["base"], huellas["codigo"])
        self.assertEqual(cr.huella_de_funcion(cr.validacion_mlp), cr.huella_funciones_ajuste()["validacion_mlp"])
        self.assertEqual(cr.huella_de_funcion(cr._semillas), cr.huella_funciones_ajuste()["_semillas"])

    def test_cambiar_las_semillas_invalida_los_puntos(self):
        """Las semillas efectivas (``_semillas``) entran en la firma y ``_semillas`` está en FUNCIONES_AJUSTE: si
        cambian las semillas que entrega, quedan vencidos los puntos de las tareas cuyas semillas cambian (y se
        rehacen); si cambia su código, todos."""
        with sx.raices_temporales() as r:
            ctx = contexto(r, con_calidad=False)
            op = cr.Opciones(motores=("lightgbm", "mlp"), **SOLO_EJE_A)
            plan, _ = correr_protocolo(ctx, "LRO", op, pliegues=[0])
            f = ctx.pliegues("LRO")[0]
            filas = filas_con_tope(ctx, "LRO", f)
            huella = cr.leer_punto(cr.ruta_punto(ctx, "LRO", 0, "vecindario", "vecindario"))[1]["huella_vecindario"]
            tareas = {t.id: t for t in plan["tareas"]}
            self.assertEqual(set(tareas), {"lightgbm", "mlp"})
            for t in tareas.values():                       # las semillas del punto son las de la firma
                meta = cr.leer_punto(cr.ruta_punto(ctx, "LRO", 0, "r0", t.id))[1]
                self.assertEqual(meta["semillas"], cr._semillas(ctx, t, 0))
                self.assertEqual(meta["firma"], cr.firma_tarea(ctx, "LRO", f, t, huella, filas, hilos=meta["hilos_firma"]))
            s_mlp = cr._semillas(ctx, tareas["mlp"], 0)
            self.assertEqual(s_mlp["validacion"], s_mlp["motor"])
            self.assertEqual(cr.leer_punto(cr.ruta_punto(ctx, "LRO", 0, "r0", "mlp"))[1]["info"]["validacion"]["semilla"],
                             s_mlp["validacion"])            # la semilla del sorteo de la validación, la de la firma
            self.assertEqual(cr._semillas(ctx, cr.Tarea("interno_mlp_j0", "mlp", "interno"), 3)["internos"],
                             [42, 3, mv.SEMILLA_INTERNOS])
            self.assertEqual(cr._semillas(ctx, cr.Tarea(cr.TAREA_DELTA_HUBER, "lightgbm", "perdidas",
                                                        variante="l2_original"), 3)["particion_honesta"],
                             [42, 3, mv.SEMILLA_PARTICION_HONESTA])
            _, t2 = correr_protocolo(ctx, "LRO", op, pliegues=[0])
            self.assertEqual([x["tarea"] for x in t2], ["vecindario"])        # todo vigente
            original = cr._semillas

            def otra_semilla_de_validacion(ctx_, tarea, k):
                s = original(ctx_, tarea, k)
                return {**s, "validacion": s["validacion"] + 7} if "validacion" in s else s

            with mock.patch.object(cr, "_semillas", otra_semilla_de_validacion):
                self.assertFalse(cr.firma_vigente(cr.ruta_punto(ctx, "LRO", 0, "r0", "mlp"),
                                                  cr.firma_tarea(ctx, "LRO", f, tareas["mlp"], huella, filas)))
                with self.assertRaises(cr.Incompleto):                       # el punto de la MLP quedó vencido
                    cr._leer_vigente(ctx, "LRO", f, tareas["mlp"], huella, filas)
                cr._leer_vigente(ctx, "LRO", f, tareas["lightgbm"], huella, filas)   # sus semillas no cambiaron
                _, t3 = correr_protocolo(ctx, "LRO", op, pliegues=[0])
            self.assertEqual(sorted(x["tarea"] for x in t3), ["mlp", "vecindario"])   # se rehace sólo la MLP
            meta = cr.leer_punto(cr.ruta_punto(ctx, "LRO", 0, "r0", "mlp"))[1]
            self.assertEqual(meta["semillas"]["validacion"], s_mlp["validacion"] + 7)
            self.assertEqual(meta["info"]["validacion"]["semilla"], s_mlp["validacion"] + 7)   # y se usó
            # cambiar el código de _semillas (su huella en el código de ajuste) vence todos los puntos
            otra = {**cr.huella_funciones_ajuste(), "_semillas": "0" * 64}
            with mock.patch.object(cr, "huella_funciones_ajuste", lambda: otra):
                for t in tareas.values():
                    with self.subTest(tarea=t.id), self.assertRaises(cr.Incompleto):
                        cr._leer_vigente(ctx, "LRO", f, t, huella, filas)


class CandadoNormalizadoTests(unittest.TestCase):
    def test_candado_del_pliegue_es_el_de_sus_rutas(self):
        """Complemento, punto 10: el candado de un pliegue es el nombre normalizado que deriva candado_de de sus
        puntos de control."""
        with sx.raices_temporales() as r:
            ctx = contexto(r, con_calidad=False)
            nombre = cr.nombre_candado_pliegue(ctx.etiqueta, "pm25", "BLQ-75", 3)
            self.assertEqual(nombre, "comparacion.principal.pm25.blq-75.k003")
            self.assertEqual(rv.candado_de(cr.ruta_punto(ctx, "BLQ-75", 3, "r1", "mlp"), r), nombre)
            ruta = cr.ruta_punto(ctx, "BLQ-75", 3, "r0", "x")
            with rv.candado_escritura("COMPARACION.principal.PM25.BLQ-75.K003", rutas=r):
                cr.guardar_punto(ruta, {"a": np.zeros(2)}, {"firma": "f"}, r)
            self.assertTrue(cr.firma_vigente(ruta, "f"))


ORDEN_ANTES_DE_LA_ENMIENDA = [{"orden": 1, "recorte": "semillas sólo en LRO"},
                              {"orden": 2, "recorte": "curvas de aprendizaje sólo en LRO"},
                              {"orden": 3, "recorte": "MLP sólo en LRO y BLQ-75"}]   # el del plan congelado


class GuardasConsolaTests(unittest.TestCase):
    """Complemento, puntos 2 y 8: correr y consolidar toman el recorte de plan_corrida_v2.json y rechazan otro (o un
    plan que no sirve) salvo --forzar-recorte, que queda en la bitácora del manifiesto; consolidar y decidir sólo
    aceptan B = 1.999 salvo --forzar, que queda registrado."""

    @staticmethod
    def publicar_plan(r, recorte=2, orden=None, contrato="vigente", schema=None):
        import piloto_v2 as plt
        plan = {"schema": schema or plt.SCHEMA_PLAN, "recorte_aplicado": recorte,
                "contrato": {"orden_de_recortes": CFG["presupuesto"]["orden_de_recortes"] if orden is None else orden,
                             "sha256": cr.sha256_contrato(r, CFG) if contrato == "vigente" else contrato}}
        with rv.candado_escritura(plt.CANDADO_PLAN, rutas=r):
            rv.publicar_json(plan, r.raiz_v2 / plt.NOMBRE_PLAN, r)

    def test_recorte_del_plan(self):
        with sx.raices_temporales() as r:
            with self.assertRaises(SystemExit) as e:                      # sin plan, correr no elige el recorte
                cr.resolver_recorte(r, CFG, None, None)
            self.assertIn("falta plan_corrida_v2.json", str(e.exception))
            self.assertEqual(cr.resolver_recorte(r, CFG, None, None, estricto=False)[0], 0)   # plan y estado: muestran
            self.publicar_plan(r, 2)
            rc, origen = cr.resolver_recorte(r, CFG, None, None)
            self.assertEqual((rc, origen["origen"], origen["recorte_del_plan"], origen["problemas_del_plan"]),
                             (2, "plan", 2, []))
            self.assertEqual(cr.resolver_recorte(r, CFG, 2, None)[0], 2)      # el mismo, explícito
            with self.assertRaises(SystemExit) as e:                      # otro, a mano: no
                cr.resolver_recorte(r, CFG, 1, None)
            self.assertIn("--forzar-recorte", str(e.exception))
            rc, origen = cr.resolver_recorte(r, CFG, 1, "prueba de humo")
            self.assertEqual((rc, origen["origen"], origen["motivo"], origen["recorte_del_plan"]),
                             (1, "forzado", "prueba de humo", 2))
            self.assertEqual(cr.resolver_recorte(r, CFG, 2, "innecesario")[1]["origen"], "plan")
            for pedido, motivo in ((None, "sin --recorte"), (1, "   ")):      # forzar exige el recorte y un motivo
                with self.assertRaises(SystemExit):
                    cr.resolver_recorte(r, CFG, pedido, motivo)
            with self.assertRaises(SystemExit):
                cr.resolver_recorte(r, CFG, 1, "motivo", estricto=False)
            self.assertEqual(cr.resolver_recorte(r, CFG, 3, None, estricto=False)[0], 3)   # mostrar otro, sí
            # un plan con el orden de recortes de antes de la Enmienda 1 (como el congelado) no sirve, ni con el
            # mismo número: su recorte 2 quitaba otras cosas
            self.publicar_plan(r, 2, orden=ORDEN_ANTES_DE_LA_ENMIENDA)
            for pedido in (None, 2):
                with self.assertRaises(SystemExit) as e:
                    cr.resolver_recorte(r, CFG, pedido, None)
                self.assertIn("orden de recortes", str(e.exception))
            rc, origen = cr.resolver_recorte(r, CFG, 2, "plan viejo, con registro")
            self.assertEqual((rc, origen["origen"], origen["recorte_del_plan"]), (2, "forzado", None))
            self.assertTrue(origen["problemas_del_plan"] and origen["plan_sha256"])
            for kw, texto in (({"contrato": "f" * 64}, "otro contrato"), ({"schema": "otro"}, "esquema"),
                              ({"recorte": 9}, "recorte_aplicado"), ({"recorte": True}, "recorte_aplicado")):
                with self.subTest(**{k: str(v) for k, v in kw.items()}):
                    self.publicar_plan(r, **kw)
                    with self.assertRaises(SystemExit) as e:
                        cr.resolver_recorte(r, CFG, None, None)
                    self.assertIn(texto, str(e.exception))

    def test_recorte_forzado_queda_en_la_bitacora(self):
        import piloto_v2 as plt
        with sx.raices_temporales() as r:
            with rv.candado_escritura("pliegues", rutas=r):
                rv.publicar_json(sx.manifiesto_sintetico(sx.panel_sintetico(dias=10)), r.manifiesto_pliegues, r)
            self.publicar_plan(r, 2)
            rc, origen = cr.resolver_recorte(r, CFG, 0, "comparación sin recortes")
            with mock.patch.object(cr, "cargar_config", lambda rutas=None, verificar_contrato=True: CFG):
                cr.anotar_recorte(r, rc, cr.ETIQUETA, forzado=origen)
                cr.anotar_recorte(r, rc, cr.ETIQUETA, forzado=origen)       # uno idéntico no se repite
                cr.anotar_recorte(r, 2, cr.ETIQUETA)                        # el del plan, aparte
                cr.anotar_recorte(r, 2, cr.ETIQUETA)
            m = rv.leer_json(r.manifiesto_pliegues)
            ev = [e for e in m["bitacora"] if e["evento"] == "recorte_presupuesto"]
            self.assertEqual([(e["recorte"], bool(e.get("forzado"))) for e in ev], [(0, True), (2, False)])
            self.assertEqual((ev[0]["forzado"]["motivo"], ev[0]["forzado"]["recorte_del_plan"], ev[0]["aplicados"]),
                             ("comparación sin recortes", 2, []))
            self.assertIn("--forzar-recorte", ev[0]["fuente"])
            self.assertEqual([e["recorte"] for e in plt.eventos_del_plan(m)], [2])   # el piloto no cuenta los forzados

    def test_replicas_bootstrap(self):
        self.assertEqual(cr.resolver_replicas_bootstrap(CFG, None, None), (1999, None))
        self.assertEqual(cr.resolver_replicas_bootstrap(CFG, 1999, "innecesario"), (1999, None))
        for B in (2000, 200):
            with self.subTest(B=B), self.assertRaises(SystemExit) as e:
                cr.resolver_replicas_bootstrap(CFG, B, None, "decidir")
            self.assertIn("--forzar", str(e.exception))
        B, f = cr.resolver_replicas_bootstrap(CFG, 200, "prueba rápida", "decidir")
        self.assertEqual((B, f["replicas_bootstrap"], f["replicas_del_contrato"], f["motivo"]),
                         (200, 200, 1999, "prueba rápida"))
        with self.assertRaises(SystemExit):
            cr.resolver_replicas_bootstrap(CFG, 0, "cero")

    def test_consola(self):
        """Las guardas actúan en la consola antes del sellado y de cargar nada."""
        import logging
        raiz_log = logging.getLogger()
        nivel, manejadores = raiz_log.level, list(raiz_log.handlers)
        try:
            with sx.raices_temporales() as r, mock.patch.object(cr, "rutas_v2", lambda: r), \
                    mock.patch.object(cr, "cargar_config", lambda rutas=None, verificar_contrato=True: CFG), \
                    mock.patch.object(cr, "commit_git", lambda repo: {"commit": "desconocido"}):
                self.publicar_plan(r, 2)
                for argv, texto in ((["correr", "--recorte", "1"], "--forzar-recorte"),
                                    (["consolidar", "--recorte", "3"], "--forzar-recorte"),
                                    (["decidir", "--replicas-bootstrap", "2000"], "--forzar"),
                                    (["consolidar", "--replicas-bootstrap", "500"], "--forzar"),
                                    (["correr", "--forzar", "x"], "--forzar sólo sirve"),
                                    (["estado", "--recorte", "1", "--forzar-recorte", "x"], "sólo sirve con correr"),
                                    (["decidir", "--forzar-recorte", "x"], "sólo sirve con correr")):
                    with self.subTest(argv=argv), self.assertRaises(SystemExit) as e:
                        cr.main([*argv, "--contaminantes", "pm25"])
                    self.assertIn(texto, str(e.exception))
                # con el recorte del plan, o el forzado con motivo, y con B = 1.999, las guardas dejan pasar: la
                # corrida se detiene recién en el sellado (en esta raíz de prueba no hay commit)
                for argv in (["correr"], ["correr", "--recorte", "2"],
                             ["consolidar", "--recorte", "4", "--forzar-recorte", "prueba"],
                             ["decidir", "--replicas-bootstrap", "1999"],
                             ["decidir", "--replicas-bootstrap", "300", "--forzar", "prueba"]):
                    with self.subTest(argv=argv), self.assertRaises(SystemExit) as e:
                        cr.main([*argv, "--contaminantes", "pm25"])
                    self.assertIn("sellado pendiente", str(e.exception))
        finally:
            raiz_log.handlers[:] = manejadores
            raiz_log.setLevel(nivel)


@contextlib.contextmanager
def c_a_12_km():
    """C a 12 km del origen (4 km de B) sin cambiar su región ni su bloque (E000N001): en BLQ-75 queda a ≤ 10 km de
    una estación de otro bloque (B, de E000N000), como pasa en Gran Santiago con la rejilla de origen (0, 0)."""
    km, region, bloque, mz, nivel = sx.ESTACIONES["C"]
    with mock.patch.dict(sx.ESTACIONES, {"C": (12.0, region, bloque, mz, nivel)}):
        yield


class AmortiguadorInternoTests(unittest.TestCase):
    """Complemento, punto 5: en las particiones internas de BLQ-75 salen del entrenamiento interno, y de su
    vecindario, las estaciones a ≤ 10 km de las de su conjunto interno de validación."""

    @classmethod
    def setUpClass(cls):
        cls._raices = sx.raices_temporales()
        cls.r = cls._raices.__enter__()
        with c_a_12_km():
            cls.panel = sx.panel_sintetico()
            cls.man = sx.manifiesto_sintetico(cls.panel)
        cls.cfg = sx.config_pequena(internos=3)
        cls.ctx = cr.Contexto.desde_tablas("pm25", cls.panel, cls.man, cls.cfg, cls.r, hilos=2)

    @classmethod
    def tearDownClass(cls):
        cls._raices.__exit__(None, None, None)

    def pliegue(self, grupo):
        return next(f for f in self.ctx.pliegues("BLQ-75") if f["grupo"] == grupo)

    def test_estaciones_a_10_km_y_solo_en_blq75(self):
        ctx = self.ctx
        self.assertAlmostEqual(float(ctx.vec.D[ctx.vec.indices(["B"])[0], ctx.vec.indices(["C"])[0]]), 4.0, places=6)
        nombres, reg = cr.amortiguador_interno(ctx, "BLQ-75", ["C", "D"])
        self.assertEqual(nombres, ["B"])                                     # A1 (12 km) y A2 (11,9 km) quedan
        self.assertEqual((reg["radio_km"], reg["comparacion"], reg["distancia"]), (10.0, "<=", "haversine"))
        self.assertAlmostEqual(reg["distancia_minima_km"]["B"], 4.0, places=3)
        self.assertEqual(cr.amortiguador_interno(ctx, "BLQ-75", ["B"])[0], ["A1", "A2", "C"])
        self.assertEqual(cr.amortiguador_interno(ctx, "BLQ-75", ["B"], excluidas=["A1", "C"])[0], ["A2"])
        self.assertEqual(cr.amortiguador_interno(ctx, "BLQ-75", ["G"])[0], [])
        for prot in ("LRO", "LOSO-D", "LBO-10", "LPO"):
            self.assertEqual(cr.amortiguador_interno(ctx, prot, ["C", "D"]), ([], {"aplica": False, "protocolo": prot}))
        # la comparación es <=: una estación justo a 10 km entra
        D = np.array([[0.0, 10.0, 10.0001], [10.0, 0.0, 1.0], [10.0001, 1.0, 0.0]])
        np.testing.assert_array_equal(mv.estaciones_a_radio(D, [0], [], 10.0), [False, True, False])
        np.testing.assert_array_equal(mv.estaciones_a_radio(D, [0], [1], 10.0), [False, False, False])

    def test_validacion_de_la_mlp(self):
        """La fase de validación no entrena con las estaciones del amortiguador y su vecindario las excluye."""
        ctx = self.ctx
        hallado = None
        for f in ctx.pliegues("BLQ-75"):
            filas = filas_con_tope(ctx, "BLQ-75", f)
            for semilla in range(10):
                val = cr.validacion_mlp(ctx, "BLQ-75", filas, f["excluidas"], semilla)
                if val.fuera is not None:
                    hallado = (f, filas, val)
                    break
            if hallado:
                break
        self.assertIsNotNone(hallado, "ningún pliegue de BLQ-75 valida junto a otro bloque a ≤ 10 km")
        f, filas, val = hallado
        reg = val.registro
        amort = reg["amortiguador_interno"]["estaciones"]
        self.assertTrue(amort)
        est_filas = ctx.estaciones_de(filas)
        np.testing.assert_array_equal(val.fuera, np.isin(est_filas, amort))
        self.assertEqual(reg["filas_amortiguador"], int(val.fuera.sum()))
        self.assertFalse((val.fuera & val.filas).any())
        np.testing.assert_array_equal(val.entrenan(), ~val.filas & ~val.fuera)
        excl = sorted(set(f["excluidas"]) | set(reg["estaciones"]) | set(amort))
        rec = ctx.vec.recalcular(excl, registrar=False)
        np.testing.assert_array_equal(val.X, ctx.matriz(filas, rec))        # vecindario sin validación ni amortiguador
        m = mv.crear_modelo("mlp", ctx.recetas, pv.Variante(mv.VARIANTE_REFERENCIA), 0, k=int(f["k"]))
        m.ajustar(ctx.matriz(filas, ctx.vec.para_pliegue(f, "BLQ-75", registrar=False)), ctx.y[filas],
                  est_filas, validacion=val)
        self.assertEqual(m.info["filas_amortiguador"], int(val.fuera.sum()))
        self.assertEqual(m.info["filas_entrenamiento_validacion"], int((~val.filas & ~val.fuera).sum()))
        # fuera de BLQ-75 no hay amortiguador interno
        f_lro = ctx.pliegues("LRO")[0]
        v_lro = cr.validacion_mlp(ctx, "LRO", filas_con_tope(ctx, "LRO", f_lro), f_lro["excluidas"], 1)
        self.assertIsNone(v_lro.fuera)
        self.assertFalse(v_lro.registro["amortiguador_interno"]["aplica"])

    def test_pliegues_internos(self):
        """Los pliegues internos del apilado y de la retransformación con OOF interno sacan del entrenamiento interno
        las estaciones a ≤ 10 km del pliegue interno; sus filas de prueba no cambian."""
        ctx = self.ctx
        vistos = 0
        for f in ctx.pliegues("BLQ-75"):
            ent, _, _ = ctx.vec.mascaras(f, "BLQ-75")
            D = cr.definicion_internos(ctx, "BLQ-75", f, np.flatnonzero(ent))
            g_est = ctx.grupo_de_estacion("BLQ-75")
            for parte in D["partes"]:
                internas = sorted(str(s) for s in ctx.vec.estaciones[np.isin(g_est, parte["definicion"]["grupos"])])
                esperado, _ = cr.amortiguador_interno(ctx, "BLQ-75", internas, f["excluidas"], filas=D["filas"])
                reg = parte["definicion"]["amortiguador_interno"]
                self.assertEqual(reg["estaciones"], esperado)
                est_tr = set(ctx.estaciones_de(parte["tr"]).tolist())
                self.assertFalse(est_tr & set(esperado))                     # no entrenan
                self.assertFalse(est_tr & set(internas))
                self.assertTrue(set(esperado) <= set(parte["excluidas"]))    # ni entran al vecindario
                self.assertEqual(set(ctx.estaciones_de(parte["te"]).tolist()) - set(internas), set())
                en_j = np.isin(ctx.estaciones_de(D["filas"]), internas)
                np.testing.assert_array_equal(parte["te"], D["filas"][en_j])   # la prueba interna no cambia
                vistos += bool(esperado)
        self.assertGreater(vistos, 0)
        # LRO: sin amortiguador interno
        f = ctx.pliegues("LRO")[0]
        ent, _, _ = ctx.vec.mascaras(f, "LRO")
        for parte in cr.definicion_internos(ctx, "LRO", f, np.flatnonzero(ent))["partes"]:
            self.assertNotIn("amortiguador_interno", parte["definicion"])

    def test_particion_honesta_del_delta(self):
        """El ajuste que predice una mitad no ve a las estaciones a ≤ 10 km de ella: multiplicar sus observaciones no
        cambia ni un bit los residuos de esa mitad. En LOSO-D (sin amortiguador interno) sí los cambia."""
        ctx = self.ctx
        caso = None
        for f in ctx.pliegues("BLQ-75"):
            filas = filas_con_tope(ctx, "BLQ-75", f)
            try:
                info, r0, en_1 = cr.delta_huber_honesto(ctx, "BLQ-75", f, filas, devolver_residuos=True)
            except ValueError:
                continue
            for mitad, reg in enumerate(info["particion_honesta"]["amortiguador_interno"]):
                if reg["estaciones"]:
                    caso = (f, filas, info, r0, en_1, mitad, reg["estaciones"])
                    break
            if caso:
                break
        self.assertIsNotNone(caso, "ninguna partición honesta de BLQ-75 deja estaciones a ≤ 10 km en mitades distintas")
        f, filas, info, r0, en_1, mitad, amort = caso
        pred = en_1 if mitad == 1 else ~en_1
        self.assertFalse(np.isin(ctx.estaciones_de(filas[pred]), amort).any())    # el amortiguador es de la otra mitad
        y2 = ctx.y.copy()
        y2[np.isin(ctx.estaciones_de(np.arange(ctx.n)), amort)] *= 3.0
        _, r2, _ = cr.delta_huber_honesto(dataclasses.replace(ctx, y=y2), "BLQ-75", f, filas, devolver_residuos=True)
        np.testing.assert_array_equal(r2[pred], r0[pred])
        self.assertEqual(info["particion_honesta"]["amortiguador_interno"][mitad]["filas_fuera_del_ajuste"],
                         int(np.isin(ctx.estaciones_de(filas), amort).sum()))
        # control: en LOSO-D no hay amortiguador interno y la misma perturbación sí llega a la otra mitad
        f_l = next(p for p in ctx.pliegues("LOSO-D") if p["grupo"] == "H")
        filas_l = filas_con_tope(ctx, "LOSO-D", f_l)
        info_l, rl0, en_1l = cr.delta_huber_honesto(ctx, "LOSO-D", f_l, filas_l, devolver_residuos=True)
        self.assertTrue(all(not x["aplica"] for x in info_l["particion_honesta"]["amortiguador_interno"]))
        _, rl2, _ = cr.delta_huber_honesto(dataclasses.replace(ctx, y=y2), "LOSO-D", f_l, filas_l, devolver_residuos=True)
        en_amort = np.isin(ctx.estaciones_de(filas_l), amort)
        self.assertTrue(en_amort.any())
        self.assertFalse(np.array_equal(rl2[~en_amort], rl0[~en_amort]))     # las filas de las demás estaciones cambian

    def test_medido_solo_desde_las_estaciones_con_filas(self):
        """El amortiguador se mide sólo desde las estaciones del conjunto interno de validación con filas en el
        entrenamiento del pliegue. Caso: C (a 4 km de B, en el bloque E000N001 con D) sin filas en el entrenamiento,
        como una estación que el conjunto excluido externo dejó sin filas. Medido desde C y D, el amortiguador sacaría
        a B; medido sólo desde D (a 250 km), no saca a nadie y B entrena."""
        ctx = self.ctx
        f = self.pliegue("E000N002")                                  # entrenan A1, A2, B, C, D, G y H
        sin = lambda filas, s: filas[ctx.estaciones_de(filas) != s]  # noqa: E731
        self.assertEqual(cr.amortiguador_interno(ctx, "BLQ-75", ["C", "D"], f["excluidas"])[0], ["B"])   # desde todas
        filas = sin(filas_con_tope(ctx, "BLQ-75", f), "C")
        self.assertNotIn("C", cr.estaciones_con_filas(ctx, filas))
        nombres, reg = cr.amortiguador_interno(ctx, "BLQ-75", ["C", "D"], f["excluidas"], filas=filas)
        self.assertEqual((nombres, reg["internas_sin_filas"], reg["internas"]), ([], ["C"], 1))
        self.assertIn("con filas en el entrenamiento", reg["medida_desde"])
        # una estación sin filas cerca de una que sí valida no entra al amortiguador (no entrenaba de todos modos)
        self.assertEqual(cr.amortiguador_interno(ctx, "BLQ-75", ["B", "C"], f["excluidas"], filas=filas)[0], ["A1", "A2"])
        # 1) validación de la MLP: el grupo E000N001 (sólo D tiene filas) valida; B no sale de esa fase
        val = cr.validacion_mlp(ctx, "BLQ-75", filas, f["excluidas"], 0)
        self.assertEqual(val.registro["grupos"], ["E000N001"])
        self.assertEqual(val.registro["estaciones"], ["C", "D"])         # el vecindario sigue sin las dos
        self.assertEqual(val.registro["amortiguador_interno"]["internas_sin_filas"], ["C"])
        self.assertEqual(val.registro["amortiguador_interno"]["estaciones"], [])
        self.assertIsNone(val.fuera)
        self.assertTrue(np.isin(ctx.estaciones_de(filas)[val.entrenan()], ["B"]).any())
        # 2) pliegues internos (apilado y OOF interno): el de E000N001 no saca a B de su entrenamiento
        ent, _, _ = ctx.vec.mascaras(f, "BLQ-75")
        disp = sin(np.flatnonzero(ent), "C")
        D = cr.definicion_internos(ctx, "BLQ-75", f, disp)
        parte = next(p for p in D["partes"] if p["definicion"]["grupos"] == ["E000N001"])
        reg = parte["definicion"]["amortiguador_interno"]
        self.assertEqual((reg["estaciones"], reg["internas_sin_filas"]), ([], ["C"]))
        self.assertIn("B", set(ctx.estaciones_de(parte["tr"]).tolist()))
        self.assertTrue({"C", "D"} <= set(parte["excluidas"]))
        # 3) partición honesta del δ: sin filas de A2, su conglomerado A1+A2 se mide sólo desde A1
        filas_a2 = sin(filas_con_tope(ctx, "BLQ-75", f), "A2")
        info = cr.delta_huber_honesto(ctx, "BLQ-75", f, filas_a2)
        regs = info["particion_honesta"]["amortiguador_interno"]
        con_a2 = [m for m, est in enumerate(info["particion_honesta"]["estaciones"]) if "A2" in est]
        self.assertEqual(len(con_a2), 1)
        m = con_a2[0]
        self.assertEqual(regs[m]["internas_sin_filas"], ["A2"])
        medidas = [s for s in info["particion_honesta"]["estaciones"][m] if s != "A2"]
        self.assertEqual(regs[m]["estaciones"],
                         cr.amortiguador_interno(ctx, "BLQ-75", medidas, [*f["excluidas"], "A2"])[0])
        self.assertNotIn("A2", regs[m]["estaciones"])
        self.assertEqual(regs[1 - m]["internas_sin_filas"], [])

    def test_punto_de_la_mlp_registra_el_amortiguador(self):
        with sx.raices_temporales() as r:
            ctx = cr.Contexto.desde_tablas("pm25", self.panel, self.man, self.cfg, r, hilos=2)
            correr_protocolo(ctx, "BLQ-75", cr.Opciones(motores=("mlp",), **SOLO_EJE_A))
            regs = [cr.leer_punto(cr.ruta_punto(ctx, "BLQ-75", int(f["k"]), "r0", "mlp"))[1]["info"]["validacion"]
                    for f in ctx.pliegues("BLQ-75")]
            self.assertTrue(all(x["amortiguador_interno"]["aplica"] for x in regs))
            self.assertTrue(all("filas_amortiguador" in x for x in regs))


class RegimenDelPanelTests(unittest.TestCase):
    """Punto 10 (sensibilidad fila a fila, Complemento 4.4): las familias se leen del panel en sólo lectura, sean o
    no predictores del motor."""

    def test_familias_leidas_del_panel(self):
        panel = sx.panel_sintetico()
        rng = np.random.default_rng(4)
        panel["no2_trop"] = np.where(rng.random(len(panel)) < 0.3, 1.5, np.nan).astype("float32")   # no es predictor
        self.assertNotIn("no2_trop", CFG["motores"]["eje_A"]["predictores"]["pm25"])
        antes = panel.copy()
        with sx.raices_temporales() as r:
            ctx = cr.Contexto.desde_tablas("pm25", panel, sx.manifiesto_sintetico(panel), CFG, r, hilos=2)
        pd.testing.assert_frame_equal(panel, antes)                          # el panel no se toca
        cod, etiquetas, info = ctx.regimen_fila_a_fila
        self.assertIn("no2_trop", info["columnas_leidas"])
        self.assertEqual(info["filas_con_familia"]["tropomi"], int(np.isfinite(panel["no2_trop"]).sum()))
        self.assertIn("acag_clim", info["columnas_ausentes"]["acag_climatologico"])
        con_tropomi = np.array(["tropomi" in etiquetas[c].split("+") for c in cod])
        np.testing.assert_array_equal(con_tropomi, np.isfinite(panel["no2_trop"].to_numpy()))
        estratos, reg = cr.estratos_fila_a_fila(ctx)
        np.testing.assert_array_equal(estratos["regimen_fila_a_fila"][0], cod)
        self.assertEqual(set(cr.columnas_de_familias(CFG)) >= {"no2_trop", "gcf_pm25", "cams_pm25", "acag_clim"}, True)
        # sin ninguna columna de las familias en el panel, no hay estrato y queda registrado
        quitar = [c for c in cr.columnas_de_familias(CFG) if c in panel.columns]
        self.assertIsNone(cr.regimen_de_panel(panel.drop(columns=quitar), CFG))

    def test_conglomerados_de_retransformacion(self):
        with sx.raices_temporales() as r:
            ctx = contexto(r, con_calidad=False)
            np.testing.assert_array_equal(ctx.conglomerado_de_estacion(),
                                          rt.conglomerados_loso_d(ctx.manifiesto_pol, [str(s) for s in ctx.vec.estaciones]))
            k = {f["grupo"]: int(f["k"]) for f in ctx.pliegues("LOSO-D")}
            c = dict(zip((str(s) for s in ctx.vec.estaciones), ctx.conglomerado_de_estacion()))
            self.assertEqual(c["A1"], c["A2"])
            self.assertEqual(c["A1"], k["A1+A2"])


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


class EstratoPropietarioTests(unittest.TestCase):
    """Enmienda 2, R10: el propietario de la estación de cada fila entra como estrato descriptivo de las métricas."""

    def test_con_y_sin_la_red_ampliada(self):
        from types import SimpleNamespace
        import panel_red2_v2 as pr
        with sx.raices_temporales("v2-estrato-") as r:
            (r.raiz_v2 / "paneles").mkdir(parents=True)
            ruta = r.raiz_v2 / "paneles" / pr.NOMBRE_ESTACIONES
            pd.DataFrame({"estacion": ["A", "B"], "tipo_propietario": ["pública", "empresa"]}).to_parquet(ruta, index=False)
            meta = r.raiz_v2 / "paneles" / pr.NOMBRE_PANEL.format(pol="no2").replace(".parquet", ".json")
            meta.write_text(json.dumps({"estaciones": {"sha256": pr.sha256_de(ruta)}}), encoding="utf-8")
            vec = SimpleNamespace(estaciones=np.array(["A", "B"]), js=np.array([0, 1, 1]))
            ctx = SimpleNamespace(cfg={}, rutas=r, pol="no2", vec=vec, regimen_fila_a_fila=None)
            self.assertEqual(cr.estratos_fila_a_fila(ctx)[0], {})                       # sin el nodo, como antes
            estratos, info = cr.estratos_fila_a_fila(SimpleNamespace(**{**vars(ctx), "cfg": {"red_de_monitores": {}}}))
            cod, etiquetas = estratos["propietario"]
            self.assertEqual((cod.tolist(), etiquetas[:2]), ([0, 1, 1], ["pública", "empresa"]))
            self.assertIn("propietario", info)


class RedAmpliadaTests(unittest.TestCase):
    """Enmienda 2: con el nodo red_de_monitores, Contexto.desde_disco exige el registro del anexo (R22, paso 4) y la
    bandera de calidad; decidir exige el anexo y que el bloque de cada evidencia sea el de la configuración (R16); la
    consola no admite --sin-calidad."""
    CFG_RED2 = {**CFG, "red_de_monitores": {}}

    def test_desde_disco_exige_el_anexo_y_la_bandera(self):
        import hashlib
        import calidad_v2
        import pliegues_red2_v2
        import pliegues_v2
        with sx.raices_temporales("v2-red2-disco-") as r:
            panel = sx.panel_sintetico()
            r.panel("pm25").parent.mkdir(parents=True, exist_ok=True)
            panel.to_parquet(r.panel("pm25"), index=False)
            man = sx.manifiesto_sintetico(panel)
            # el manifiesto calza con el panel en disco: la falta del registro del anexo es la única causa de la parada
            man["contaminantes"]["pm25"]["panel"]["sha256"] = hashlib.sha256(r.panel("pm25").read_bytes()).hexdigest()
            man["huella_pliegues"] = pliegues_v2.huella_pliegues(man)
            r.manifiesto_pliegues.write_text(json.dumps(man), encoding="utf-8")
            with self.assertRaises(SystemExit) as e:                         # sin el registro del anexo
                cr.Contexto.desde_disco("pm25", r, self.CFG_RED2, hilos=1)
            self.assertIn("anexo", str(e.exception))
            visto = {}

            def desde_tablas(pol, panel_, man_, cfg_, r_, etiqueta, h, calidad=None, vec=None, identidad_panel=None,
                             insumos=None):
                visto.update(calidad=calidad, insumos=insumos)
                return "contexto"
            with mock.patch.object(pliegues_red2_v2, "exigir_registro", lambda r_, cfg_, ruta=None: man), \
                    mock.patch.object(cr.Vecindario, "desde_panel", lambda *a, **k: "vecindario"), \
                    mock.patch.object(cr.Contexto, "desde_tablas", desde_tablas):
                with self.assertRaises(SystemExit):                          # con el registro, sin la bandera
                    cr.Contexto.desde_disco("pm25", r, self.CFG_RED2, hilos=1)
                with self.assertRaises(SystemExit):                          # sin calidad, tampoco
                    cr.Contexto.desde_disco("pm25", r, self.CFG_RED2, hilos=1, con_calidad=False)
                pd.DataFrame({"estacion": panel["estacion"], "ts_utc": panel["ts_utc"], "qc": "validado",
                              "fuente": "sinca"}).to_parquet(calidad_v2.ruta_calidad(r, "pm25"), index=False)
                bandera = lambda pol, claves, r_: pd.DataFrame({"qc": ["validado"] * len(claves)})   # noqa: E731
                with mock.patch.object(calidad_v2, "cargar_bandera", bandera):
                    self.assertEqual(cr.Contexto.desde_disco("pm25", r, self.CFG_RED2, hilos=1), "contexto")
                self.assertIn("calidad_pm25", visto["insumos"])
                self.assertEqual(len(visto["calidad"]), len(panel))

    def test_decidir_exige_el_anexo_y_el_bloque(self):
        import pliegues_red2_v2
        with sx.raices_temporales("v2-red2-decidir-") as r:
            with self.assertRaises(SystemExit):                              # sin el registro del anexo
                cr.decidir(r, self.CFG_RED2, "pm25", factibilidad={}, escribir=False)
            regla = dc.regla_de_config(self.CFG_RED2)
            for prot in regla.protocolos:
                ruta = cr.ruta_evidencia(r, cr.ETIQUETA, "pm25", prot)
                ruta.parent.mkdir(parents=True, exist_ok=True)
                ruta.write_text(json.dumps({"bloque_mas_influyente": "otro"}), encoding="utf-8")
            with mock.patch.object(pliegues_red2_v2, "exigir_registro", lambda r_, cfg_, ruta=None: {}):
                with self.assertRaises(SystemExit) as e:                     # evidencia con otro bloque (R16)
                    cr.decidir(r, self.CFG_RED2, "pm25", factibilidad={}, escribir=False)
                self.assertIn("R16", str(e.exception))

    def test_decidir_usa_la_evaluabilidad_registrada_de_e2(self):
        """Enmienda 2, R15 («se calcula sobre el panel de R11, con los mismos umbrales, antes de cualquier ajuste»): en
        decidir rige la evaluabilidad de E2 registrada en pliegues_v2_red2.json. Con la evidencia en «no evaluable»
        (0,49) y la registrada en «evaluable» (0,51), decision_v2 recibe la registrada (la condición 3 se exige) y la de
        la evidencia queda sólo en el registro de decision.json, con la huella de la evidencia consolidada; con la
        registrada evaluable y una evidencia sin pares E2, decidir se detiene (defecto de la corrida)."""
        import pliegues_red2_v2
        regla = dc.regla_de_config(self.CFG_RED2)
        registrada = {"evaluable": True, "fraccion_del_peso": 0.51, "grupos_con_E2": 5, "peso_E1": 10.0, "peso_E2": 5.1}
        man = {"pesos": {"pm25": {"evaluabilidad_e2": {"por_protocolo": {p: dict(registrada) for p in regla.protocolos}}}}}
        de_la_evidencia = {**registrada, "evaluable": False, "fraccion_del_peso": 0.49}

        def evidencias(r, vistas):
            for prot in regla.protocolos:
                ruta = cr.ruta_evidencia(r, cr.ETIQUETA, "pm25", prot)
                ruta.parent.mkdir(parents=True, exist_ok=True)
                ruta.write_text(json.dumps({"bloque_mas_influyente": regla.bloque_mas_influyente.get(prot),
                                            "semilla_bootstrap": 1, "semilla_salvaje": 2, "vistas": vistas,
                                            "evaluabilidad_E2": de_la_evidencia}), encoding="utf-8")
        recibidas = {}

        def decidir_motor(ev, f, **k):
            recibidas.update(ev)
            return pd.DataFrame(), {"decision": "prueba"}
        with sx.raices_temporales("v2-red2-decidir-e2-") as r, \
                mock.patch.object(pliegues_red2_v2, "exigir_registro", lambda r_, cfg_, ruta=None: man):
            evidencias(r, {})                                                # sin pares E2
            with self.assertRaises(SystemExit) as e:
                cr.decidir(r, self.CFG_RED2, "pm25", factibilidad={}, escribir=False)
            self.assertIn("R15", str(e.exception))
            self.assertIn("defecto de la corrida", str(e.exception))
            evidencias(r, {dc.V_E2: {}})                                     # con pares E2
            with mock.patch.object(dc, "decidir_motor", decidir_motor):
                res = cr.decidir(r, self.CFG_RED2, "pm25", factibilidad={}, escribir=False)
        self.assertEqual(sorted(recibidas), sorted(regla.protocolos))
        e2 = res["registro"]["evaluabilidad_E2_red2"]
        self.assertEqual(sorted(e2), sorted(regla.protocolos))
        for prot in regla.protocolos:
            self.assertTrue(recibidas[prot]["evaluabilidad_E2"]["evaluable"])       # la registrada, no la de la evidencia
            self.assertEqual(recibidas[prot]["evaluabilidad_E2"]["fraccion_del_peso"], 0.51)
            self.assertEqual((e2[prot]["rige"], e2[prot]["coinciden"]), (registrada, False))
            self.assertEqual(e2[prot]["de_la_decision"]["fraccion_del_peso"], 0.49)
            self.assertRegex(e2[prot]["evidencia_consolidada_sha256"], r"^[0-9a-f]{64}$")

    def test_la_consola_no_admite_sin_calidad(self):
        with sx.raices_temporales() as r, mock.patch.object(cr, "rutas_v2", lambda: r), \
                mock.patch.object(cr, "cargar_config", lambda r_: self.CFG_RED2):
            for accion in ("piloto", "correr", "consolidar"):
                with self.subTest(accion), self.assertRaises(SystemExit) as e:
                    cr.main([accion, "--sin-calidad"])
                self.assertIn("--sin-calidad", str(e.exception))


if __name__ == "__main__":
    unittest.main()
