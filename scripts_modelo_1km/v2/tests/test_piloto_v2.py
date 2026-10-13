"""Pruebas del piloto de tiempos (``piloto_v2``, §10) con datos sintéticos pequeños y raíces temporales:

* el medidor registra pared, CPU, memoria y contención de cada fase, también si la fase falla;
* el alcance: dos pliegues por protocolo por filas de entrenamiento, curvas en el pliegue de LRO de más
  entrenamiento y calibración en el de más prueba, con las mismas tareas de ``plan_protocolo``;
* el piloto no guarda predicciones ni puntos de control, y ninguna fila de medición lleva una métrica de desempeño;
* reanuda sin repetir lo medido; Huber arrastra a su ajuste cuadrático;
* la contabilidad de la extrapolación (fase por fase, con la caché de matrices) y el orden de los recortes de §10;
* el plan y su bitácora, sin rutas absolutas, y el evento del recorte en la bitácora del manifiesto, una sola vez.
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
import piloto_v2 as pv  # noqa: E402
import pliegues_v2 as plv  # noqa: E402

pv.VENTANA_PROCESOS_S = 0.0
CFG = sx.config_pequena()
RECETAS = mv.recetas_de(CFG, 2)
PANEL = sx.panel_sintetico()
MANIFIESTO = sx.manifiesto_sintetico(PANEL)

# Claves que puede llevar una fila de medición: etiquetas de la fase y medidas de tiempo, CPU y memoria. Nada más.
CLAVES_PERMITIDAS = {
    "sesion", "contaminante", "protocolo", "k", "tarea", "fase", "motor", "familia", "variante", "tope", "replica",
    "calidad", "filas_disponibles", "filas_prueba", "filas_entrenamiento", "n_excluidas", "interno", "filas_panel",
    "con_calidad", "n_tareas", "inicio_utc", "segundos_pared", "segundos_cpu", "paralelismo", "cpu_otros_s",
    "fraccion_maquina_otros", "carga_1min_inicio", "carga_1min_max", "rss_inicio_mb", "rss_fin_mb", "rss_pico_mb",
    "maxrss_proceso_mb", "nuevo_maximo_proceso", "muestras_memoria", "error"}


def contexto(r):
    calidad = np.where(np.arange(len(PANEL)) % 5 == 0, "preliminar", "validado").astype(object)
    return cr.Contexto.desde_tablas("pm25", PANEL, MANIFIESTO, CFG, r, hilos=2, calidad=calidad)


def medir(r, **kw):
    return pv.medir(r, CFG, ["pm25"], plv.PROTOCOLOS, 2, crear_contexto=lambda pol: contexto(r),
                    manifiesto=MANIFIESTO, **kw)


class MedidorTests(unittest.TestCase):
    def test_mide_pared_cpu_y_memoria(self):
        cerradas = []
        with pv.Medidor(intervalo_s=0.02, al_cerrar=cerradas.append) as med:
            with med.fase(tarea="prueba", fase="ajuste") as reg:
                a = np.ones(40_000_000)                  # 320 MB residentes
                s = 0.0
                for _ in range(20):
                    s += float(np.sqrt(a[: 5_000_000]).sum())
                reg["filas_entrenamiento"] = 7
                del a
        self.assertEqual(len(cerradas), 1)
        f = cerradas[0]
        self.assertEqual((f["tarea"], f["fase"], f["filas_entrenamiento"]), ("prueba", "ajuste", 7))
        self.assertGreater(f["segundos_pared"], 0)
        self.assertGreater(f["segundos_cpu"], 0)
        self.assertGreaterEqual(f["rss_pico_mb"] - f["rss_inicio_mb"], 200)
        self.assertGreaterEqual(f["maxrss_proceso_mb"], f["rss_pico_mb"] * 0.9)
        self.assertGreaterEqual(f["cpu_otros_s"], 0)
        self.assertNotIn("error", f)
        self.assertTrue(set(f) <= CLAVES_PERMITIDAS)

    def test_error_queda_registrado_y_se_propaga(self):
        med = pv.Medidor(intervalo_s=0.05)
        with med, self.assertRaises(ZeroDivisionError):
            with med.fase(tarea="x", fase="ajuste"):
                1 / 0
        self.assertIn("ZeroDivisionError", med.filas[0]["error"])

    def test_fases_anidadas(self):
        with pv.Medidor(intervalo_s=0.05) as med:
            with med.fase(tarea="pliegue", fase="pliegue"):
                with med.fase(tarea="a", fase="ajuste"):
                    np.linalg.svd(np.random.default_rng(0).normal(size=(300, 300)))
        self.assertEqual([f["fase"] for f in med.filas], ["ajuste", "pliegue"])
        self.assertGreaterEqual(med.filas[1]["segundos_pared"], med.filas[0]["segundos_pared"])


class AlcanceTests(unittest.TestCase):
    def test_dos_pliegues_por_filas_de_entrenamiento(self):
        for prot in plv.PROTOCOLOS:
            pl = MANIFIESTO["contaminantes"]["pm25"]["protocolos"][prot]["pliegues"]
            eleg = cr.pliegues_piloto(pl)
            tr = [f["filas_entrenamiento_disponibles"] for f in pl]
            with self.subTest(prot=prot):
                self.assertEqual(len(eleg), 2)
                self.assertEqual(eleg[0]["filas_entrenamiento_disponibles"], max(tr))
                self.assertEqual(eleg[1]["filas_entrenamiento_disponibles"], min(tr))
                if prot != "LBO-10":                     # sin exclusión adicional: el mismo par que por prueba
                    self.assertEqual({f["k"] for f in eleg}, {f["k"] for f in cr.pliegues_piloto(pl, "prueba")})

    def test_curvas_y_calibracion_en_lro(self):
        eleg = pv.seleccion(MANIFIESTO, "pm25", ["LRO"])["LRO"]
        k_cur, k_cal = pv.pliegues_lro(eleg)
        por_k = {f["k"]: f for f in eleg}
        self.assertEqual(por_k[k_cur]["filas_entrenamiento_disponibles"],
                         max(f["filas_entrenamiento_disponibles"] for f in eleg))
        self.assertEqual(por_k[k_cal]["filas_prueba"], max(f["filas_prueba"] for f in eleg))
        self.assertEqual(pv.topes_curva_piloto(RECETAS), {"lightgbm": [500, 2400, None], "xgboost": [500, 2400, None],
                                                          "random_forest": [2400]})
        base = pv.tareas_piloto(RECETAS, "LOSO-D", 0, k_cur, k_cal, calibrar=True)
        self.assertEqual([t.id for t in base], list(mv.MOTORES_EJE_A))
        curvas = pv.tareas_piloto(RECETAS, "LRO", k_cur, k_cur, k_cal, calibrar=True)
        self.assertEqual(sorted(t.id for t in curvas if t.familia == "curva"),
                         ["lightgbm_n2400", "lightgbm_n500", "lightgbm_ntodas", "random_forest_n2400",
                          "xgboost_n2400", "xgboost_n500", "xgboost_ntodas"])
        cal = pv.tareas_piloto(RECETAS, "LRO", k_cal, k_cur, k_cal, calibrar=True)
        self.assertEqual(len(cal), 4 + 10 + 1 + 3)
        self.assertEqual(len(pv.tareas_piloto(RECETAS, "LRO", k_cal, k_cur, k_cal, calibrar=False)), 4)
        completo = {(t.id, t.replica): t for t in cr.plan_protocolo(RECETAS, "LRO", cr.Opciones(), False)["tareas"]}
        for t in curvas + cal:
            self.assertEqual(completo[(t.id, t.replica)], t)      # las mismas definiciones que la corrida completa

    def test_huber_arrastra_a_su_ajuste_cuadratico(self):
        cal = pv.tareas_piloto(RECETAS, "LRO", 1, 0, 1, calibrar=True)
        hechas = {("pm25", "LRO", 1, t.id, t.replica) for t in cal if t.id != "xgboost_huber"}
        self.assertEqual(sorted(t.id for t in pv.pendientes(cal, hechas, "pm25", "LRO", 1)),
                         ["xgboost_huber", "xgboost_l2_original"])


class MedicionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._raices = sx.raices_temporales()
        cls.r = cls._raices.__enter__()
        cls.reg = medir(cls.r, calibrar=True)
        cls.df = pd.DataFrame(cls.reg.mediciones)

    @classmethod
    def tearDownClass(cls):
        cls._raices.__exit__(None, None, None)

    def test_sin_predicciones_ni_metricas(self):
        self.assertFalse((self.r.raiz_v2 / cr.CARPETA).exists())         # ningún punto de control
        self.assertEqual(list(self.r.raiz_v2.rglob("*.npz")), [])
        for fila in self.reg.mediciones:
            self.assertTrue(set(fila) <= CLAVES_PERMITIDAS, sorted(set(fila) - CLAVES_PERMITIDAS))
        texto = (self.r.raiz_v2 / pv.CARPETA / pv.NOMBRE_MEDICIONES).read_text(encoding="utf-8")
        for palabra in ("r2", "rmse", "mejor_", "delta_huber\":", "nmb"):
            self.assertNotIn(palabra, texto)

    def test_cubre_el_alcance(self):
        self.assertEqual(pv.faltantes(self.df, MANIFIESTO, RECETAS, "entrenamiento", ["pm25"]), [])
        fases = set(self.df["fase"])
        for fase in ("contexto", "mascara_calidad", "vecindario", "permutacion", "filas", "matriz_entrenamiento",
                     "matriz_prueba", "ajuste", "prediccion", "delta_huber", "construccion_lineales",
                     "ajuste_prediccion", "pliegue"):
            self.assertIn(fase, fases)
        aj = self.df[self.df["fase"] == "ajuste"]
        self.assertEqual(int((aj["familia"] == "eje_A").sum()), 5 * 2 * 4)  # 5 protocolos × 2 pliegues × 4 motores
        self.assertEqual(int((aj["familia"] == "curva").sum()), 7)
        self.assertTrue({"lightgbm_q95", "xgboost_huber", "alertas_q80", "gp", "lme"} <= set(aj["tarea"]))
        self.assertTrue((self.df["segundos_cpu"] >= 0).all() and (self.df["segundos_pared"] >= 0).all())
        self.assertFalse(self.df.get("error", pd.Series(dtype=object)).notna().any())

    def test_remide_lo_contaminado_y_usa_la_medicion_con_menos_contencion(self):
        with sx.raices_temporales() as r:
            reg = medir(r)
            # máquina tranquila salvo en el ajuste de la MLP del primer pliegue de LPO (la contención real de la
            # máquina donde corren las pruebas no debe influir)
            for m in reg.mediciones:
                m["fraccion_maquina_otros"] = 0.0
            fila = next(m for m in reg.mediciones if m["fase"] == "ajuste" and m["tarea"] == "mlp"
                        and m["protocolo"] == "LPO")
            fila.update(segundos_pared=999.0, fraccion_maquina_otros=0.9)
            with rv.candado_escritura(pv.CANDADO_MEDIR, rutas=r):
                reg.guardar()
            clave = ("pm25", "LPO", int(fila["k"]), "mlp", 0)
            self.assertEqual(pv.tareas_contaminadas(reg.mediciones, 0.5, minimo_s=0.0), {clave})
            antes = len(reg.mediciones)
            reg2 = medir(r, remedir_si_otros=0.5)
            nuevas = reg2.mediciones[antes:]
            self.assertEqual({(m["tarea"], m["fase"]) for m in nuevas if m["fase"] in ("ajuste", "prediccion")},
                             {("mlp", "ajuste"), ("mlp", "prediccion")})
            self.assertEqual(reg2.doc["sesiones"][-1]["argumentos"]["tareas_a_remedir"],
                             [f"pm25/LPO/{clave[2]}/mlp/0"])
            df = pd.DataFrame(reg2.mediciones)
            df.loc[antes:, "fraccion_maquina_otros"] = 0.1                       # la remedición, más tranquila
            d = pv.menos_contaminada(df)
            aj = d[(d["fase"] == "ajuste") & (d["tarea"] == "mlp") & (d["protocolo"] == "LPO") & (d["k"] == clave[2])]
            self.assertEqual(len(aj), 1)
            self.assertLess(float(aj["segundos_pared"].iloc[0]), 999.0)          # gana la medición limpia
            self.assertEqual(len(d), len(d[list(pv.CLAVE_FASE)].astype(str).drop_duplicates()))

    def test_reanuda_sin_repetir(self):
        antes = len(self.reg.mediciones)
        reg2 = medir(self.r, calibrar=True)
        self.assertEqual(len(reg2.mediciones), antes)                       # nada que medir
        self.assertEqual(len(reg2.doc["sesiones"]), 2)
        for clave in ("git", "codigo", "insumos", "bibliotecas", "hilos", "semillas"):
            self.assertIn(clave, reg2.doc["sesiones"][0]["traza"])


def fabricar(pol="pm25", cpu=4.0):
    """Mediciones con costos conocidos: vecindario 1 s; permutación 1e-6 s/fila; filas 1e-7; matrices 1e-5;
    ajuste del eje A 10/20/30/40 s con el N común (lineal en N en las curvas); predicción 1e-4 s/fila."""
    filas = [{"sesion": 0, "contaminante": pol, "tarea": "contexto", "fase": "contexto", "segundos_pared": 10.0}]
    eleg = pv.seleccion(MANIFIESTO, pol, plv.PROTOCOLOS)
    k_cur, k_cal = pv.pliegues_lro(eleg["LRO"])
    N = RECETAS["N_comun"]
    aj = {"lightgbm": 10.0, "xgboost": 20.0, "random_forest": 30.0, "mlp": 40.0}
    for prot, pl in eleg.items():
        for f in pl:
            k, disp, te = int(f["k"]), int(f["filas_entrenamiento_disponibles"]), int(f["filas_prueba"])
            b = {"sesion": 0, "contaminante": pol, "protocolo": prot, "k": k}
            ne = min(N, disp)
            filas += [{**b, "tarea": "vecindario", "fase": "vecindario", "segundos_pared": 1.0},
                      {**b, "tarea": "permutacion_r0", "fase": "permutacion", "filas_disponibles": disp,
                       "segundos_pared": 1e-6 * disp},
                      {**b, "tarea": "matriz_prueba", "fase": "matriz_prueba", "filas_prueba": te,
                       "segundos_pared": 1e-5 * te}]
            tareas = [(m, "eje_A", "N", ne) for m in aj]
            if prot == "LRO" and k == k_cur:
                for m, topes in pv.topes_curva_piloto(RECETAS).items():
                    tareas += [(m, "curva", t, disp if t is None else min(t, disp)) for t in topes]
            for m, fam, tope, n in tareas:
                tid = m if fam == "eje_A" else f"{m}_n{'todas' if tope is None else tope}"
                e = {**b, "tarea": tid, "motor": m, "familia": fam, "tope": tope, "replica": 0, "calidad": "todo",
                     "filas_entrenamiento": n, "filas_prueba": te, "filas_disponibles": disp}
                filas += [{**e, "fase": "filas", "segundos_pared": 1e-7 * n},
                          {**e, "fase": "matriz_entrenamiento", "segundos_pared": 1e-5 * n},
                          {**e, "fase": "ajuste", "segundos_pared": aj[m] * n / ne},
                          {**e, "fase": "prediccion", "segundos_pared": 1e-4 * te}]
    df = pd.DataFrame(filas)
    df["segundos_cpu"] = df["segundos_pared"] * cpu
    df["paralelismo"] = cpu
    df["fraccion_maquina_otros"] = 0.0
    df["carga_1min_max"] = 1.0
    df["maxrss_proceso_mb"] = 100.0
    df["error"] = None
    return df, k_cur, k_cal


class ExtrapolacionTests(unittest.TestCase):
    def test_lineal_y_curva(self):
        f = pv.Lineal([1, 2, 3], [2.0, 3.0, 4.0])
        self.assertAlmostEqual(f(10), 11.0)
        self.assertEqual((pv.Lineal([1, 2], [3.0, 1.0]).a, pv.Lineal([1, 2], [3.0, 1.0]).b), (2.0, 0.0))
        c = pv.CurvaLogLog({100: 1.0, 1000: 10.0, 10000: 200.0})
        self.assertAlmostEqual(c(316.227766), 3.16227766, places=5)
        self.assertAlmostEqual(c(100000), 4000.0, places=3)                # pendiente del último tramo
        self.assertAlmostEqual(pv.CurvaLogLog({100: 2.0})(400), 8.0)       # un punto: proporcional a N

    def test_media_global(self):
        df, k_cur, _ = fabricar()
        df.loc[(df["fase"] == "ajuste") & (df["protocolo"] == "LPO") & (df["motor"] == "mlp"), "segundos_pared"] = 140.0
        d = pv.anadir_menos_contencion(df)
        M = pv.ModeloTiempos(d, "pm25", RECETAS, "segundos_pared", k_cur, None)
        G = pv.ModeloTiempos(d, "pm25", RECETAS, "segundos_pared", k_cur, None, media_global=True)
        N = RECETAS["N_comun"]
        self.assertAlmostEqual(M.ajuste("LPO", "mlp", N), 140.0)
        self.assertAlmostEqual(M.ajuste("LOSO-D", "mlp", N), 40.0)
        self.assertAlmostEqual(G.ajuste("LOSO-D", "mlp", N), G.ajuste("LPO", "mlp", N))
        self.assertAlmostEqual(G.ajuste("LOSO-D", "mlp", N), (8 * 40.0 + 2 * 140.0) / 10)

    def test_contabilidad_de_un_pliegue(self):
        df, k_cur, _ = fabricar()
        M = pv.ModeloTiempos(pv.anadir_menos_contencion(df), "pm25", RECETAS, "segundos_pared", k_cur, None)
        self.assertEqual(M.sobrecosto, 0.0)
        plan = {"tareas": [t for t in cr.plan_protocolo(RECETAS, "LOSO-D", cr.Opciones(), False)["tareas"]
                           if t.familia == "eje_A"], "interno": []}
        f = MANIFIESTO["contaminantes"]["pm25"]["protocolos"]["LOSO-D"]["pliegues"][3]
        disp, te = f["filas_entrenamiento_disponibles"], f["filas_prueba"]
        ne = min(RECETAS["N_comun"], disp)
        esperado = 1.0 + 1e-6 * disp + 1e-5 * te + 4 * 1e-7 * ne + 1e-5 * ne + (10 + 20 + 30 + 40) + 4 * 1e-4 * te
        c = pv.costo_pliegue(M, "LOSO-D", f, plan, 2)
        self.assertAlmostEqual(sum(c.values()), esperado, places=6)
        # curva lineal: con todas las filas, el ajuste escala con N; la MLP, proporcional (sin curva medida)
        self.assertAlmostEqual(M.ajuste("LRO", "lightgbm", disp), 10.0 * disp / ne, places=6)
        self.assertAlmostEqual(M.ajuste("LOSO-D", "mlp", 2 * ne), 80.0, places=6)
        # pliegues internos: n = 2, cada uno con (n − 1)/n del N común para entrenar
        s = M.internos("LRO", disp, 2, list(mv.MOTORES_EJE_A))
        e = 1e-6 * disp + 1e-7 * ne + 2 * (1.0 + 1e-5 * ne / 2 + 1e-5 * ne / 2) + 2 * (100 * 0.5 + 4 * 1e-4 * ne / 2)
        self.assertAlmostEqual(s, e, places=6)

    def test_recortes_bajan_y_menos_contencion(self):
        df, k_cur, k_cal = fabricar()
        # contención en los ajustes de LOSO-D y LBO-10: pared doble con la misma CPU (paralelismo 2 en vez de 4); el
        # p90 del paralelismo de cada motor sigue en 4, porque la mayoría de sus ajustes no tuvo contención
        con = (df["fase"] == "ajuste") & df["protocolo"].isin(["LOSO-D", "LBO-10"])
        df.loc[con, "segundos_pared"] *= 2.0
        df.loc[con, "paralelismo"] = 2.0
        est = pv.extrapolar(df, MANIFIESTO, RECETAS, {"pm25": False}, {"pm25": k_cur}, {"pm25": k_cal}, ["pm25"])
        horas = [est["por_recorte"][str(rc)]["horas"] for rc in range(4)]
        self.assertTrue(all(a >= b for a, b in zip(horas, horas[1:])))
        self.assertGreater(horas[0], horas[3])
        for rc in range(4):
            e = est["por_recorte"][str(rc)]
            self.assertLess(e["horas_menos_contencion"], e["horas"])
            fijo = (10 + pv.SUPUESTOS["lineales"]["construccion_s"]) / 3600     # contexto y construcción de lineales
            self.assertAlmostEqual(sum(v["horas"] for v in e["detalle"].values()) + fijo, e["horas"], delta=0.03)
        d = pv.anadir_menos_contencion(df)
        x = d[con & (df["motor"] == "lightgbm")]
        np.testing.assert_allclose(x["segundos_pared_menos_contencion"], x["segundos_pared"] / 2.0)
        np.testing.assert_allclose(x["segundos_pared_sin_contencion_fuerte"], x["segundos_pared"])   # sin otros
        df.loc[con, "fraccion_maquina_otros"] = 0.6
        x = pv.anadir_menos_contencion(df)[con & (df["motor"] == "lightgbm")]
        largos = x["segundos_pared"] >= pv.CONTENCION_MIN_SEGUNDOS
        np.testing.assert_allclose(x.loc[largos, "segundos_pared_sin_contencion_fuerte"],
                                   x.loc[largos, "segundos_pared"] / 2.0)
        self.assertIn("perdidas.q05", est["modelos"]["pm25"]["supuestos_usados"])   # sin calibración: supuesto

    def test_decision_de_recortes(self):
        orden = CFG["presupuesto"]["orden_de_recortes"]

        def est(h, hm, hg=None):
            hg = h if hg is None else hg
            return {"por_recorte": {str(i): {"horas": a, "horas_menos_contencion": b, "horas_media_global": c,
                                             "horas_sin_contencion_fuerte": a, "horas_cpu": 8 * a}
                                    for i, (a, b, c) in enumerate(zip(h, hm, hg))}}
        d = pv.decidir_recortes(est([200, 180, 110, 100], [150, 130, 90, 80]), 120.0, orden)
        self.assertEqual((d["recorte"], d["excede_tras_recortes"], len(d["bitacora"])), (2, False, 3))
        self.assertEqual(d["aplicados"], ["semillas sólo en LRO", "curvas de aprendizaje sólo en LRO"])
        self.assertEqual(d["recorte_con_menos_contencion"], 2)
        d = pv.decidir_recortes(est([300, 290, 280, 250], [200, 190, 119, 100]), 120.0, orden)
        self.assertEqual((d["recorte"], d["excede_tras_recortes"], len(d["bitacora"])), (3, True, 4))
        self.assertIn("enmienda", d["bitacora"][-1]["accion"])
        self.assertEqual((d["recorte_con_menos_contencion"], d["excede_con_menos_contencion"]), (2, False))
        d = pv.decidir_recortes(est([100, 90, 80, 70], [90, 80, 70, 60]), 120.0, orden)
        self.assertEqual((d["recorte"], d["aplicados"], len(d["bitacora"])), (0, [], 1))
        d = pv.decidir_recortes(est([125, 119, 110, 100], [110, 100, 90, 80], [130, 125, 121, 118]), 120.0, orden)
        self.assertEqual(d["recorte"], 1)                                  # la principal decide
        self.assertEqual(d["sensibilidad"]["horas_media_global"]["recorte"], 3)
        self.assertEqual(d["sensibilidad"]["horas_menos_contencion"]["recorte"], 0)


class PlanTests(unittest.TestCase):
    def test_plan_bitacora_y_manifiesto(self):
        with sx.raices_temporales() as r:
            with rv.candado_escritura("pliegues", rutas=r):
                rv.publicar_json(MANIFIESTO, r.manifiesto_pliegues, r)
            medir(r)
            cfg = json.loads(json.dumps(CFG))
            cfg["presupuesto"]["umbral_horas_maquina"] = 1e-9                # fuerza los tres recortes
            pv.estimar_y_publicar(r, cfg, 2, contaminantes=["pm25"])
            plan = json.loads((r.raiz_v2 / pv.NOMBRE_PLAN).read_text(encoding="utf-8"))
            self.assertEqual((plan["recorte_aplicado"], plan["excede_tras_recortes"]), (3, True))
            self.assertEqual([p["paso"] for p in plan["bitacora_de_recortes"]], [0, 1, 2, 3])
            self.assertIn("pendiente_del_autor", plan)
            self.assertTrue(plan["bitacora_manifiesto"]["estado"].startswith("se anota"))
            self.assertEqual(set(plan["estimacion"]), {"0", "1", "2", "3"})
            self.assertEqual(set(plan["sensibilidad"]) - {"nota"}, set(pv.SENSIBILIDADES))
            self.assertEqual(len(plan["piloto"]["mediciones"]["sesiones"]), 1)
            self.assertIn("hash_codigo", plan["piloto"]["mediciones"]["sesiones"][0])
            pr = plan["plan_resultante"]["por_contaminante"]["pm25"]
            self.assertNotIn("mlp", pr["LOSO-D"]["tareas"])                    # recorte 3
            self.assertIn("mlp", pr["BLQ-75"]["tareas"])
            self.assertFalse(any("@r" in t for t in pr["BLQ-75"]["tareas"]))  # recorte 1
            for clave in ("git", "codigo", "insumos", "bibliotecas", "hilos", "semillas"):
                self.assertIn(clave, plan["traza"])
            for archivo in (r.raiz_v2 / pv.NOMBRE_PLAN, r.salidas_v2 / pv.TABLA_JSON, r.salidas_v2 / pv.TABLA_CSV):
                texto = archivo.read_text(encoding="utf-8")
                self.assertNotIn(str(r.raiz_v2.parent), texto)
                self.assertNotIn("/Users/", texto)
                self.assertNotIn("NaN", texto)
            m = json.loads(r.manifiesto_pliegues.read_text(encoding="utf-8"))
            eventos = [e for e in m["bitacora"] if e.get("evento") == "recorte_presupuesto"]
            self.assertEqual(len(eventos), 1)
            self.assertEqual(eventos[0]["recorte"], 3)
            self.assertEqual(m["huella_pliegues"], plv.huella_pliegues(m))   # la bitácora no toca la huella
            pv.estimar_y_publicar(r, cfg, 2, contaminantes=["pm25"])          # otra vez: no se repite el evento
            plan = json.loads((r.raiz_v2 / pv.NOMBRE_PLAN).read_text(encoding="utf-8"))
            self.assertEqual(plan["bitacora_manifiesto"]["estado"], "ya anotado (misma decisión)")
            m = json.loads(r.manifiesto_pliegues.read_text(encoding="utf-8"))
            self.assertEqual(len([e for e in m["bitacora"] if e.get("evento") == "recorte_presupuesto"]), 1)
            with rv.candado_escritura("x", rutas=r):
                cr.anotar_recorte(r, 3, cr.ETIQUETA)                          # correr_v2 lo reconoce
            m = json.loads(r.manifiesto_pliegues.read_text(encoding="utf-8"))
            self.assertEqual(len([e for e in m["bitacora"] if e.get("evento") == "recorte_presupuesto"]), 1)
            cfg["presupuesto"]["umbral_horas_maquina"] = 1e9                 # reestimación sin recorte: lo reemplaza
            pv.estimar_y_publicar(r, cfg, 2, contaminantes=["pm25"])
            m = json.loads(r.manifiesto_pliegues.read_text(encoding="utf-8"))
            eventos = [e for e in m["bitacora"] if e.get("evento") == "recorte_presupuesto"]
            self.assertEqual([e["recorte"] for e in eventos], [3, 0])
            self.assertEqual(eventos[-1]["reemplaza"]["recorte"], 3)
            self.assertEqual(m["huella_pliegues"], plv.huella_pliegues(m))

    def test_incompleto_no_escribe_plan(self):
        with sx.raices_temporales() as r:
            pv.medir(r, CFG, ["pm25"], ["LRO", "LPO"], 2, crear_contexto=lambda pol: contexto(r), manifiesto=MANIFIESTO)
            pv.estimar_y_publicar(r, CFG, 2, manifiesto=MANIFIESTO, contaminantes=["pm25"])
            self.assertFalse((r.raiz_v2 / pv.NOMBRE_PLAN).exists())


if __name__ == "__main__":
    unittest.main()
