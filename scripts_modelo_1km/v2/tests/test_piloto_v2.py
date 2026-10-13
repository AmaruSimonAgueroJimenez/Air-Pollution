"""Pruebas del piloto de tiempos (``piloto_v2``, §10) con datos sintéticos pequeños y raíces temporales:

* el medidor registra pared, CPU, memoria y contención de cada fase, también si la fase falla;
* el alcance: dos pliegues por protocolo por filas de entrenamiento, curvas en el pliegue de LRO de más
  entrenamiento y calibración en el de más prueba, con las mismas tareas de ``plan_protocolo``;
* el piloto no guarda predicciones ni puntos de control, y ninguna fila de medición lleva una métrica de desempeño;
* reanuda sin repetir lo medido; Huber arrastra a su ajuste cuadrático;
* la contabilidad de la extrapolación (fase por fase, con la caché de matrices, la fase de validación de la MLP y el
  δ honesto de Huber: Complemento, punto 8) y el orden de los cuatro recortes de la Enmienda 1, punto 12;
* la máquina libre (carga media < 2 al empezar; Complemento, punto 8);
* el plan y su bitácora, sin rutas absolutas, y el evento del recorte en la bitácora del manifiesto, una sola vez;
* respaldos: antes de sobrescribir las mediciones o el plan queda una copia con los mismos bytes, citada con su
  sha256 en la sesión o en el plan nuevo;
* sesiones por huella del código de ajuste: las fases sensibles al código (validación y ajuste de la MLP, δ de
  Huber) medidas con otro código se vuelven a medir y no entran en la extrapolación, aunque tengan menos contención.
"""
from __future__ import annotations

import hashlib
import json
import sys
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
        self.assertEqual(len(cal), 4 + 12 + 1 + 3)                 # 12 pérdidas: con huber_friedman (Enmienda 1, punto 9)
        # sin calibrar, el pliegue de calibración mide igual el δ honesto de Huber (su costo nuevo; Complemento, punto 8)
        sin = pv.tareas_piloto(RECETAS, "LRO", k_cal, k_cur, k_cal, calibrar=False)
        self.assertEqual([t.id for t in sin], [*mv.MOTORES_EJE_A, cr.TAREA_DELTA_HUBER])
        completo = {(t.id, t.replica): t for t in cr.plan_protocolo(RECETAS, "LRO", cr.Opciones(), False)["tareas"]}
        for t in curvas + cal:
            self.assertEqual(completo[(t.id, t.replica)], t)      # las mismas definiciones que la corrida completa

    def test_huber_arrastra_a_su_ajuste_cuadratico(self):
        cal = pv.tareas_piloto(RECETAS, "LRO", 1, 0, 1, calibrar=True)
        hechas = {("pm25", "LRO", 1, t.id, t.replica) for t in cal if t.id != "xgboost_huber"}
        # Enmienda 1, punto 9: el δ es común a los dos motores y sale de lightgbm_l2_original
        self.assertEqual(sorted(t.id for t in pv.pendientes(cal, hechas, "pm25", "LRO", 1)),
                         ["lightgbm_l2_original", "xgboost_huber"])


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
                     "ajuste_prediccion", "pliegue", "vecindario_validacion", "matriz_validacion"):
            self.assertIn(fase, fases)
        sesion = self.reg.doc["sesiones"][0]
        self.assertEqual(set(sesion["maquina_libre"]) >= {"carga_1min_al_empezar", "umbral", "libre"}, True)
        # sin la fase de validación de la MLP o sin el δ, el alcance está incompleto (Complemento, punto 8)
        sin_val = self.df[~self.df["fase"].isin(pv.FASES_VALIDACION_MLP)]
        self.assertTrue(any("validación de la MLP" in x for x in
                            pv.faltantes(sin_val, MANIFIESTO, RECETAS, "entrenamiento", ["pm25"])))
        sin_delta = self.df[self.df["fase"] != "delta_huber"]
        self.assertTrue(any("δ honesto" in x for x in
                            pv.faltantes(sin_delta, MANIFIESTO, RECETAS, "entrenamiento", ["pm25"])))
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
        ruta = self.r.raiz_v2 / pv.CARPETA / pv.NOMBRE_MEDICIONES
        previo = ruta.read_bytes()
        antes = len(self.reg.mediciones)
        reg2 = medir(self.r, calibrar=True)
        self.assertEqual(len(reg2.mediciones), antes)                       # nada que medir
        self.assertEqual(len(reg2.doc["sesiones"]), 2)
        for clave in ("git", "codigo", "insumos", "bibliotecas", "hilos", "semillas"):
            self.assertIn(clave, reg2.doc["sesiones"][0]["traza"])
        # antes de sobrescribirlo, el archivo que había quedó respaldado (mismos bytes) y la sesión lo cita
        respaldos = sorted(ruta.parent.glob("mediciones_respaldo_*.json"))
        self.assertEqual(len(respaldos), 1)
        self.assertEqual(respaldos[0].read_bytes(), previo)
        self.assertIsNone(reg2.doc["sesiones"][0]["respaldo_previo"])        # la primera no tenía nada que respaldar
        self.assertEqual(reg2.doc["sesiones"][1]["respaldo_previo"]["sha256"], hashlib.sha256(previo).hexdigest())
        self.assertEqual(reg2.doc["sesiones"][1]["respaldo_previo"]["ruta"], f"{pv.CARPETA}/{respaldos[0].name}")
        # las sesiones registran la huella del código de ajuste con que midieron (Complemento, punto 8)
        self.assertEqual({s["codigo_ajuste"]["huella"] for s in reg2.doc["sesiones"]},
                         {cr.codigo_ajuste_actual()["huella"]})


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
                if m == "mlp":                                    # fase de validación: vecindario 0,5 s y su matriz
                    filas += [{**e, "fase": "vecindario_validacion", "segundos_pared": 0.5},
                              {**e, "fase": "matriz_validacion", "segundos_pared": 1e-5 * n}]
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
        validacion = 0.5 + 1e-5 * ne                                          # la fase de validación de la MLP
        esperado = (1.0 + 1e-6 * disp + 1e-5 * te + 4 * 1e-7 * ne + 1e-5 * ne + (10 + 20 + 30 + 40) + 4 * 1e-4 * te
                    + validacion)
        c = pv.costo_pliegue(M, "LOSO-D", f, plan, 2)
        self.assertAlmostEqual(sum(c.values()), esperado, places=6)
        self.assertTrue(M.validacion_mlp_medida)
        self.assertAlmostEqual(M.validacion_mlp("LOSO-D", ne), validacion, places=9)
        # sin medir la fase de validación se supone como un vecindario y una matriz del pliegue, y queda declarado
        S = pv.ModeloTiempos(pv.anadir_menos_contencion(df[~df["fase"].isin(pv.FASES_VALIDACION_MLP)]), "pm25",
                             RECETAS, "segundos_pared", k_cur, None)
        self.assertFalse(S.validacion_mlp_medida)
        self.assertAlmostEqual(S.validacion_mlp("LOSO-D", ne), 1.0 + 1e-5 * ne, places=9)
        self.assertIn("validacion_mlp", S.supuestos_usados)
        # curva lineal: con todas las filas, el ajuste escala con N; la MLP, proporcional (sin curva medida)
        self.assertAlmostEqual(M.ajuste("LRO", "lightgbm", disp), 10.0 * disp / ne, places=6)
        self.assertAlmostEqual(M.ajuste("LOSO-D", "mlp", 2 * ne), 80.0, places=6)
        # pliegues internos: n = 2, cada uno con (n − 1)/n del N común para entrenar
        s = M.internos("LRO", disp, 2, list(mv.MOTORES_EJE_A))
        e = (1e-6 * disp + 1e-7 * ne + 2 * (1.0 + 1e-5 * ne / 2 + 1e-5 * ne / 2) + 2 * (100 * 0.5 + 4 * 1e-4 * ne / 2)
             + 2 * (0.5 + 1e-5 * ne / 2))                                      # la validación de la MLP interna
        self.assertAlmostEqual(s, e, places=6)

    def test_recortes_bajan_y_menos_contencion(self):
        df, k_cur, k_cal = fabricar()
        # contención en los ajustes de LOSO-D y LBO-10: pared doble con la misma CPU (paralelismo 2 en vez de 4); el
        # p90 del paralelismo de cada motor sigue en 4, porque la mayoría de sus ajustes no tuvo contención
        con = (df["fase"] == "ajuste") & df["protocolo"].isin(["LOSO-D", "LBO-10"])
        df.loc[con, "segundos_pared"] *= 2.0
        df.loc[con, "paralelismo"] = 2.0
        est = pv.extrapolar(df, MANIFIESTO, RECETAS, {"pm25": False}, {"pm25": k_cur}, {"pm25": k_cal}, ["pm25"])
        self.assertEqual(set(est["por_recorte"]), {"0", "1", "2", "3", "4"})
        horas = [est["por_recorte"][str(rc)]["horas"] for rc in range(5)]
        self.assertTrue(all(a >= b for a, b in zip(horas, horas[1:])))
        self.assertGreater(horas[0], horas[4])
        self.assertEqual(horas[2], horas[3])                               # el recorte 3 no quita nada (§8)
        for rc in range(5):
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
        """Los cuatro recortes de la Enmienda 1, punto 12, en su orden y sin elección a mano (Complemento, punto 8)."""
        orden = CFG["presupuesto"]["orden_de_recortes"]

        def est(h, hm, hg=None):
            hg = h if hg is None else hg
            return {"por_recorte": {str(i): {"horas": a, "horas_menos_contencion": b, "horas_media_global": c,
                                             "horas_sin_contencion_fuerte": a, "horas_cpu": 8 * a}
                                    for i, (a, b, c) in enumerate(zip(h, hm, hg))}}
        d = pv.decidir_recortes(est([200, 180, 110, 110, 100], [150, 130, 90, 90, 80]), 120.0, orden)
        self.assertEqual((d["recorte"], d["excede_tras_recortes"], len(d["bitacora"])), (2, False, 3))
        self.assertEqual(d["aplicados"], ["curvas de aprendizaje fuera de LRO", "MLP fuera de LRO y BLQ-75"])
        self.assertEqual(d["recorte_con_menos_contencion"], 2)
        d = pv.decidir_recortes(est([300, 290, 280, 280, 125], [200, 190, 125, 125, 100]), 120.0, orden)
        self.assertEqual((d["recorte"], d["excede_tras_recortes"], len(d["bitacora"])), (4, True, 5))
        self.assertEqual(d["aplicados"], [x["recorte"] for x in orden])
        self.assertIn("enmienda", d["bitacora"][-1]["accion"])
        self.assertIn("4 recortes", d["bitacora"][-1]["accion"])
        self.assertEqual((d["recorte_con_menos_contencion"], d["excede_con_menos_contencion"]), (4, False))
        d = pv.decidir_recortes(est([200, 190, 150, 150, 110], [200, 190, 150, 150, 110]), 120.0, orden)
        self.assertEqual((d["recorte"], d["excede_tras_recortes"]), (4, False))     # el recorte 4: pérdidas
        self.assertEqual(d["aplicados"][-1], "pérdidas del §6 fuera de LRO, BLQ-75 y LOSO-D")
        d = pv.decidir_recortes(est([100, 90, 80, 80, 70], [90, 80, 70, 70, 60]), 120.0, orden)
        self.assertEqual((d["recorte"], d["aplicados"], len(d["bitacora"])), (0, [], 1))
        d = pv.decidir_recortes(est([125, 119, 110, 110, 100], [110, 100, 90, 90, 80], [130, 125, 121, 121, 118]),
                                120.0, orden)
        self.assertEqual(d["recorte"], 1)                                  # la principal decide
        self.assertEqual(d["sensibilidad"]["horas_media_global"]["recorte"], 4)
        self.assertEqual(d["sensibilidad"]["horas_menos_contencion"]["recorte"], 0)
        with self.assertRaises(ValueError):
            pv.decidir_recortes(est([1, 1, 1], [1, 1, 1]), 120.0, [orden[0], orden[2]])   # órdenes con huecos

    def test_maquina_libre(self):
        """Complemento, punto 8: el piloto se vuelve a medir con la carga media del último minuto por debajo de 2."""
        self.assertTrue(pv.maquina_libre(CFG, carga=1.99)["libre"])
        self.assertFalse(pv.maquina_libre(CFG, carga=2.0)["libre"])
        self.assertEqual(pv.maquina_libre(CFG, carga=0.5)["umbral"], 2.0)
        import unittest.mock as um
        with sx.raices_temporales() as r, um.patch.object(pv.os, "getloadavg", lambda: (9.0, 9.0, 9.0)):
            with self.assertRaises(SystemExit) as e:
                medir(r, exigir_maquina_libre=True)
            self.assertIn("no está libre", str(e.exception))
            self.assertFalse((r.raiz_v2 / pv.CARPETA / pv.NOMBRE_MEDICIONES).exists())   # no midió nada


class PlanTests(unittest.TestCase):
    def test_plan_bitacora_y_manifiesto(self):
        with sx.raices_temporales() as r:
            with rv.candado_escritura("pliegues", rutas=r):
                rv.publicar_json(MANIFIESTO, r.manifiesto_pliegues, r)
            medir(r)
            cfg = json.loads(json.dumps(CFG))
            cfg["presupuesto"]["umbral_horas_maquina"] = 1e-9                # fuerza los cuatro recortes
            pv.estimar_y_publicar(r, cfg, 2, contaminantes=["pm25"])
            plan_1 = (r.raiz_v2 / pv.NOMBRE_PLAN).read_bytes()
            plan = json.loads(plan_1.decode("utf-8"))
            self.assertIsNone(plan["respaldo_del_plan_anterior"])            # no había plan que respaldar
            self.assertEqual(list(r.raiz_v2.glob("plan_corrida_v2_reemplazado_*.json")), [])
            self.assertEqual(plan["contrato"]["sha256"], CFG["contrato"]["sha256"])   # sin archivo: el declarado
            vig = plan["piloto"]["mediciones"]["vigencia_por_codigo"]
            self.assertEqual((vig["filas_descartadas"], vig["huella_codigo_ajuste"]),
                             (0, cr.codigo_ajuste_actual()["huella"]))
            self.assertTrue(all(s["fases_sensibles_vigentes"] for s in plan["piloto"]["mediciones"]["sesiones"]))
            self.assertEqual(plan["piloto"]["mediciones"]["filas_vigentes"], plan["piloto"]["mediciones"]["filas"])
            self.assertEqual((plan["recorte_aplicado"], plan["excede_tras_recortes"]), (4, True))
            self.assertEqual([p["paso"] for p in plan["bitacora_de_recortes"]], [0, 1, 2, 3, 4])
            self.assertIn("pendiente_del_autor", plan)
            self.assertIn("4 recortes", plan["pendiente_del_autor"])
            self.assertTrue(plan["bitacora_manifiesto"]["estado"].startswith("se anota"))
            self.assertEqual(set(plan["estimacion"]), {"0", "1", "2", "3", "4"})
            self.assertIn("todas_las_sesiones_libres", plan["piloto"]["maquina_libre"])
            self.assertTrue(plan["modelo_de_extrapolacion"]["modelos"]["pm25"]["validacion_mlp"]["medida"])
            self.assertEqual(set(plan["sensibilidad"]) - {"nota"}, set(pv.SENSIBILIDADES))
            self.assertEqual(len(plan["piloto"]["mediciones"]["sesiones"]), 1)
            self.assertIn("hash_codigo", plan["piloto"]["mediciones"]["sesiones"][0])
            pr = plan["plan_resultante"]["por_contaminante"]["pm25"]
            self.assertNotIn("mlp", pr["LOSO-D"]["tareas"])                    # recorte 2: MLP sólo en LRO y BLQ-75
            self.assertIn("mlp", pr["BLQ-75"]["tareas"])
            self.assertTrue(any("@r" in t for t in pr["BLQ-75"]["tareas"]))   # las semillas de BLQ-75 se conservan
            self.assertFalse(any("_n" in t for t in pr["BLQ-75"]["tareas"]))  # recorte 1: curvas sólo en LRO
            self.assertTrue(any("_n" in t for t in pr["LRO"]["tareas"]))
            self.assertFalse(any(t.startswith("lightgbm_") for t in pr["LBO-10"]["tareas"]))   # recorte 4
            self.assertIn("lightgbm_huber", pr["LOSO-D"]["tareas"])
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
            self.assertEqual(eventos[0]["recorte"], 4)
            self.assertEqual(eventos[0]["aplicados"], [x["recorte"] for x in CFG["presupuesto"]["orden_de_recortes"]])
            self.assertEqual(m["huella_pliegues"], plv.huella_pliegues(m))   # la bitácora no toca la huella
            pv.estimar_y_publicar(r, cfg, 2, contaminantes=["pm25"])          # otra vez: no se repite el evento
            plan = json.loads((r.raiz_v2 / pv.NOMBRE_PLAN).read_text(encoding="utf-8"))
            self.assertEqual(plan["bitacora_manifiesto"]["estado"], "ya anotado (misma decisión)")
            # el plan anterior quedó respaldado antes de sobrescribirlo, con los mismos bytes, y el nuevo lo cita
            respaldos = list(r.raiz_v2.glob("plan_corrida_v2_reemplazado_*.json"))
            self.assertEqual(len(respaldos), 1)
            self.assertEqual(respaldos[0].read_bytes(), plan_1)
            self.assertEqual(plan["respaldo_del_plan_anterior"]["sha256"], hashlib.sha256(plan_1).hexdigest())
            self.assertEqual(plan["respaldo_del_plan_anterior"]["ruta"], respaldos[0].name)
            self.assertEqual(rv.candado_de(respaldos[0], r), pv.CANDADO_PLAN)
            m = json.loads(r.manifiesto_pliegues.read_text(encoding="utf-8"))
            self.assertEqual(len([e for e in m["bitacora"] if e.get("evento") == "recorte_presupuesto"]), 1)
            with rv.candado_escritura("x", rutas=r):
                cr.anotar_recorte(r, 4, cr.ETIQUETA)                          # correr_v2 lo reconoce
            m = json.loads(r.manifiesto_pliegues.read_text(encoding="utf-8"))
            self.assertEqual(len([e for e in m["bitacora"] if e.get("evento") == "recorte_presupuesto"]), 1)
            cfg["presupuesto"]["umbral_horas_maquina"] = 1e9                 # reestimación sin recorte: lo reemplaza
            pv.estimar_y_publicar(r, cfg, 2, contaminantes=["pm25"])
            m = json.loads(r.manifiesto_pliegues.read_text(encoding="utf-8"))
            eventos = [e for e in m["bitacora"] if e.get("evento") == "recorte_presupuesto"]
            self.assertEqual([e["recorte"] for e in eventos], [4, 0])
            self.assertEqual(eventos[-1]["reemplaza"]["recorte"], 4)
            self.assertEqual(m["huella_pliegues"], plv.huella_pliegues(m))
            self.assertEqual(len(list(r.raiz_v2.glob("plan_corrida_v2_reemplazado_*.json"))), 2)   # un respaldo por vez

    def test_incompleto_no_escribe_plan(self):
        with sx.raices_temporales() as r:
            pv.medir(r, CFG, ["pm25"], ["LRO", "LPO"], 2, crear_contexto=lambda pol: contexto(r), manifiesto=MANIFIESTO)
            pv.estimar_y_publicar(r, CFG, 2, manifiesto=MANIFIESTO, contaminantes=["pm25"])
            self.assertFalse((r.raiz_v2 / pv.NOMBRE_PLAN).exists())


class SesionesPorCodigoTests(unittest.TestCase):
    """Complemento, punto 8: las sesiones se distinguen por la huella del código de ajuste; las fases que cambiaron
    con él (validación y ajuste —con el reajuste— de la MLP, y el δ honesto de Huber) medidas con otro código no se
    reutilizan: se vuelven a medir y no entran en la extrapolación. Las demás fases sí se reutilizan."""

    def test_sensibles_al_codigo(self):
        sensible = pv.fase_sensible_al_codigo
        self.assertTrue(sensible({"fase": "ajuste", "motor": "mlp"}))
        self.assertTrue(sensible({"fase": "vecindario_validacion", "motor": "mlp"}))
        self.assertTrue(sensible({"fase": "matriz_validacion", "motor": "mlp"}))
        self.assertTrue(sensible({"fase": "delta_huber", "motor": "lightgbm"}))
        for fila in ({"fase": "prediccion", "motor": "mlp"}, {"fase": "ajuste", "motor": "lightgbm"},
                     {"fase": "vecindario"}, {"fase": "matriz_entrenamiento", "motor": "mlp"}):
            self.assertFalse(sensible(fila), fila)
        # una sesión sin huella (como las del piloto congelado por la Enmienda 1) no vale para las fases sensibles
        doc = {"sesiones": [{"sesion": 0}, {"sesion": 1, "codigo_ajuste": {"huella": "h"}}],
               "mediciones": [{"sesion": 0, "fase": "ajuste", "motor": "mlp"}, {"sesion": 0, "fase": "ajuste", "motor": "rf"},
                              {"sesion": 1, "fase": "ajuste", "motor": "mlp"}, {"sesion": 0, "fase": "delta_huber"}]}
        banderas, resumen = pv.vigencia_por_codigo(doc, "h")
        self.assertEqual(banderas, [False, True, True, False])
        self.assertEqual((resumen["sesiones_con_esta_huella"], resumen["sesiones_con_otra_huella"]), ([1], [0]))
        self.assertEqual(resumen["descartadas_por_fase"], [{"fase": "ajuste (mlp)", "filas": 1},
                                                           {"fase": "delta_huber", "filas": 1}])
        # el δ común sólo cuenta como medido con su fase delta_huber
        base = {"contaminante": "pm25", "protocolo": "LRO", "k": 1, "familia": "perdidas", "replica": 0}
        filas = [{**base, "tarea": cr.TAREA_DELTA_HUBER, "fase": f} for f in ("ajuste", "prediccion")]
        self.assertEqual(pv.tareas_medidas(filas), set())
        self.assertEqual(pv.tareas_medidas(filas + [{**base, "tarea": cr.TAREA_DELTA_HUBER, "fase": "delta_huber"}]),
                         {("pm25", "LRO", 1, cr.TAREA_DELTA_HUBER, 0)})

    def test_remide_y_no_reutiliza_lo_medido_con_otro_codigo(self):
        with sx.raices_temporales() as r:
            reg = medir(r)
            n0 = len(reg.mediciones)
            vigentes, info = pv.mediciones_vigentes(reg.doc)
            self.assertEqual((len(vigentes), info["filas_descartadas"]), (n0, 0))
            self.assertEqual(len(medir(r).mediciones), n0)                  # el mismo código: nada que medir
            otro = {**cr.codigo_ajuste_actual(), "huella": "0" * 64}      # otro código de ajuste
            with mock.patch.object(cr, "codigo_ajuste_actual", lambda: otro):
                doc = json.loads((r.raiz_v2 / pv.CARPETA / pv.NOMBRE_MEDICIONES).read_text(encoding="utf-8"))
                vigentes, info = pv.mediciones_vigentes(doc)
                self.assertFalse(any(pv.fase_sensible_al_codigo(m) for m in vigentes))
                self.assertEqual({x["fase"] for x in info["descartadas_por_fase"]},
                                 {"ajuste (mlp)", "vecindario_validacion", "matriz_validacion", "delta_huber"})
                df_vig = pd.DataFrame(vigentes)
                df_vig["error"] = None
                falta = pv.faltantes(df_vig, MANIFIESTO, RECETAS, "entrenamiento", ["pm25"])
                self.assertTrue(any(x.endswith(": mlp") for x in falta))
                self.assertTrue(any("δ honesto" in x for x in falta))
                reg2 = medir(r)
            nuevas = reg2.mediciones[n0:]
            # sólo se vuelve a medir lo que cambió: la MLP (validación, ajuste con reajuste) y el δ de Huber
            self.assertEqual({m["tarea"] for m in nuevas if m["fase"] in ("ajuste", "prediccion")},
                             {"mlp", cr.TAREA_DELTA_HUBER})
            self.assertTrue({"delta_huber", *pv.FASES_VALIDACION_MLP} <= {m["fase"] for m in nuevas})
            sesion = reg2.doc["sesiones"][-1]
            self.assertEqual(sesion["codigo_ajuste"]["huella"], "0" * 64)
            self.assertEqual(sesion["argumentos"]["no_vigentes_por_codigo"]["filas"], info["filas_descartadas"])
            with mock.patch.object(cr, "codigo_ajuste_actual", lambda: otro):
                banderas, _ = pv.vigencia_por_codigo(reg2.doc)
                df_ok = pd.DataFrame(pv.mediciones_vigentes(reg2.doc)[0])
                df_ok["error"] = None
                self.assertEqual(pv.faltantes(df_ok, MANIFIESTO, RECETAS, "entrenamiento", ["pm25"]), [])
            # La extrapolación no usa las mediciones sensibles del código anterior, aunque tengan menos contención.
            df = pd.DataFrame(reg2.doc["mediciones"])
            df["vigente_codigo"], df["error"] = banderas, None
            viejas = (df.index < n0) & (df["fase"] == "ajuste") & (df["motor"] == "mlp")
            df.loc[viejas, "segundos_pared"] = 999.0
            df.loc[viejas, "fraccion_maquina_otros"] = 0.0
            df.loc[df.index >= n0, "fraccion_maquina_otros"] = 0.5
            k_cur, _ = pv.pliegues_lro(pv.seleccion(MANIFIESTO, "pm25", ["LRO"])["LRO"])
            M = pv.ModeloTiempos(pv.anadir_menos_contencion(df), "pm25", RECETAS, "segundos_pared", k_cur, None)
            mlp = [v for (_, mo), v in M.fit_n.items() if mo == "mlp"]
            self.assertEqual(len(mlp), len(plv.PROTOCOLOS))
            self.assertTrue(all(v < 999.0 for v in mlp))
            sin = pv.ModeloTiempos(pv.anadir_menos_contencion(df.drop(columns="vigente_codigo")), "pm25", RECETAS,
                                   "segundos_pared", k_cur, None)
            self.assertTrue(all(v == 999.0 for (_, mo), v in sin.fit_n.items() if mo == "mlp"))   # sin la regla


if __name__ == "__main__":
    unittest.main()
