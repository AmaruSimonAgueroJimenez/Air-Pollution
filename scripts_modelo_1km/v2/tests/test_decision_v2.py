"""Pruebas de ``decision_v2`` (§9; Enmienda 1, punto 11; Complemento, puntos 1, 2, 3 y 6) con evidencia sintética
(datos simulados, nunca la comparación v2):

* un candidato verdaderamente superior en LRO y BLQ-75 reemplaza a LightGBM, con el intervalo escalonado publicado
  y el cambio de signo del bootstrap salvaje (la segunda prueba que decide; el jackknife CV3 sólo informa);
* candidatos nulos no pasan la condición 1 más de lo esperado (Holm sobre 4 al 5 %) y casi nunca reemplazan;
* una superioridad que depende de un solo bloque (la RM) se marca no robusta y queda como «evidencia parcial»;
* un caso que cambia con ½·σ² (``lognormal_medio_sigma2``) no reemplaza;
* las demás condiciones (ruido de la diferencia con las 3 réplicas, E2, signo sin ponderar y en log, sesgo), la
  factibilidad del Complemento (≤ 5 veces LightGBM compilado y ≤ 21 días con los dos contaminantes; el promedio
  cuesta la suma de sus miembros), el desempate (que exige las 3 réplicas), los pares de la decisión con lo que
  quita cada familia, las semillas de la evidencia, la regla leída de la configuración y el determinismo de la
  evidencia en JSON.
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
import _rutas_v2 as rv  # noqa: E402
import bootstrap_v2 as bs  # noqa: E402
import decision_v2 as dc  # noqa: E402
import metricas_v2 as mt  # noqa: E402
import retransformacion_v2 as rt  # noqa: E402

CFG = json.loads((V2 / rv.NOMBRE_CONFIG).read_text(encoding="utf-8"))
MOTORES = ("lightgbm", "xgboost", "random_forest", "mlp", "promedio")
LN = rt.SUFIJO_FORMA[rt.LOGNORMAL]
BLOQUES = {"LRO": ["RI", "RII", "RIII", "RIV", "RIX", "RM", "RV", "RVI", "RVII", "RVIII", "RX", "RXI", "RXII", "RXIV", "RXV"],
           "BLQ-75": [f"E00{i % 7}N0{60 + i}" for i in range(17)] + ["E004N083"]}
# segundos por día de superficies, por contaminante (Complemento, punto 3): LightGBM compilado es la referencia
FAC = {"lightgbm": {"pm25": 10.0, "no2": 8.0}, "xgboost": {"pm25": 12.0, "no2": 10.0},
       "random_forest": {"pm25": 20.0, "no2": 16.0}, "mlp": {"pm25": 6.0, "no2": 5.0}}


def fac_con(**motores) -> dict:
    """FAC con los motores dados reemplazados: ``random_forest=(pm25, no2)``."""
    return {**FAC, **{m: {"pm25": float(v[0]), "no2": float(v[1])} for m, v in motores.items()}}


def niveles_sinteticos(prot: str, *, semilla: int = 0, efectos: dict | None = None, por_bloque: dict | None = None,
                       estaciones_por_bloque: int = 2, dias: int = 90, rho: float = 0.9, tau: float = 0.0,
                       ruido_replica: float = 0.25, replicas: int = 3, peso_bloque: dict | None = None,
                       sesgo_lognormal: dict | None = None, sesgo: dict | None = None, frac_e2: float = 0.8,
                       bloques_e2: int | None = None, efecto_e2: dict | None = None,
                       iguales: dict | None = None) -> tuple[mt.Nivel, mt.Nivel]:
    """Nivel diario civil de E1 y E2 sobre los pares de la decisión. El error de LightGBM es N(0, 5); el de cada
    candidato, ρ·e_LightGBM + √(1 − ρ²)·ξ con la misma varianza (nulo), multiplicado por √(1 − δ) si el candidato
    reduce la varianza del error en una fracción δ (``efectos``: candidato → δ en todos los bloques;
    ``por_bloque``: candidato → {bloque: δ}). ``tau`` agrega heterogeneidad nula entre bloques. Cada réplica suma
    su propio ruido de semilla. ``sesgo_lognormal`` multiplica la predicción de ½·σ² del motor (por omisión, la
    misma de smearing por 1,002). ``efecto_e2``: candidato → δ en los pares de E2 (negativo: peor que LightGBM).
    ``iguales``: candidato → candidato cuyas predicciones copia, réplicas incluidas (para forzar un empate)."""
    rng = np.random.default_rng(semilla)
    efectos, por_bloque = dict(efectos or {}), dict(por_bloque or {})
    etiquetas = BLOQUES[prot]
    G = len(etiquetas)
    n_est = G * estaciones_por_bloque
    est = np.repeat(np.arange(n_est), dias)
    blq = est // estaciones_por_bloque
    n = len(est)
    pob_est = np.exp(rng.normal(7.0, 0.8, n_est))
    for etq, w in (peso_bloque or {}).items():
        pob_est[np.repeat(np.arange(G) == etiquetas.index(etq), estaciones_por_bloque)] = w
    obs = rng.gamma(4.0, 6.0, n) + 3.0 * (blq % 4)
    e_l = rng.normal(0.0, 5.0, n)
    het = {m: np.sqrt(np.clip(1.0 + rng.normal(0.0, tau, G), 0.05, None))[blq] for m in MOTORES[1:]}
    dias_e2 = rng.random(n) < frac_e2
    con_e2 = np.arange(G) < (G if bloques_e2 is None else bloques_e2)
    e2 = dias_e2 & con_e2[blq]
    pred, log = {}, {}
    for m in MOTORES:
        cand = {"promedio": "promedio_simple"}.get(m, m)
        if cand in (iguales or {}):
            fuente = dc.prediccion(iguales[cand])
            for r in range(replicas):
                for suf in ("", LN):
                    pred[dc.con_forma(bs.nombre_replica(m, r), suf)] = pred[dc.con_forma(bs.nombre_replica(fuente, r), suf)].copy()
            continue
        if m == "lightgbm":
            base = e_l
        else:
            base = (rho * e_l + np.sqrt(1 - rho ** 2) * rng.normal(0.0, 5.0, n)) * het[m]
            delta = np.full(G, float(efectos.get(cand, 0.0)))
            for etq, d in por_bloque.get(cand, {}).items():
                delta[etiquetas.index(etq)] = d
            factor = np.sqrt(1.0 - delta)[blq]
            if cand in (efecto_e2 or {}):
                factor = np.where(e2, np.sqrt(1.0 - float(efecto_e2[cand])), factor)
            base = base * factor
        for r in range(replicas):
            p = obs + base + rng.normal(0.0, ruido_replica, n) + (sesgo or {}).get(cand, 0.0)
            p = np.clip(p, 0.0, None)
            nombre = bs.nombre_replica(m, r)
            pred[nombre] = p
            pred[dc.con_forma(nombre, LN)] = p * (1.002 + (sesgo_lognormal or {}).get(cand, 0.0))
    for k, v in pred.items():
        log[k] = np.log1p(np.clip(v, 0.0, None))

    def nivel(mask):
        return mt.Nivel(nombre="diario_civil", obs=obs[mask], log_obs=np.log1p(obs[mask]),
                        pred={k: v[mask] for k, v in pred.items()}, log={k: v[mask] for k, v in log.items()},
                        estacion=est[mask], macrozona=np.full(int(mask.sum()), 2), anio=np.full(int(mask.sum()), 2015),
                        peso_vec=np.ones(int(mask.sum())), dist_est_km=np.ones(int(mask.sum())),
                        poblacion=pob_est[est][mask], grupo=blq[mask], unidades=np.full(int(mask.sum()), 24),
                        bloque=blq[mask], etiquetas={"bloque": list(etiquetas)})

    return nivel(np.ones(n, dtype=bool)), nivel(e2)


def evidencia(prot: str, **kw) -> dict:
    nv1, nv2 = niveles_sinteticos(prot, **kw)
    return json.loads(json.dumps(dc.evidencia_protocolo(prot, nv1, nv2, contaminante="pm25")))


def evidencias(lro: dict | None = None, blq: dict | None = None, **comun) -> dict:
    return {"LRO": evidencia("LRO", **{**comun, **(lro or {})}),
            "BLQ-75": evidencia("BLQ-75", **{**comun, "semilla": comun.get("semilla", 0) + 1, **(blq or {})})}


REGLA_RAPIDA = dc.ReglaDecision(replicas_bootstrap=999, replicas_salvaje=199)


def fila(tabla: pd.DataFrame, candidato: str, protocolo: str, forma: str = rt.SMEARING) -> pd.Series:
    t = tabla[(tabla["candidato"] == candidato) & (tabla["protocolo"] == protocolo) & (tabla["forma"] == forma)]
    assert len(t) == 1
    return t.iloc[0]


class ReglaYNombresTests(unittest.TestCase):
    def test_regla_de_la_configuracion(self):
        regla = dc.regla_de_config(CFG)
        import dataclasses
        sys.path.insert(0, str(V2 / "tests"))
        from _sintetico_v2 import anexo_de_la_red
        anexo = anexo_de_la_red(CFG)            # Enmienda 2, R16: después del anexo rige el bloque calculado
        bloque = {"LRO": "RM", "BLQ-75": "E004N083"} if anexo is None else anexo["bloque"]
        self.assertEqual(regla, dataclasses.replace(dc.ReglaDecision(), bloque_mas_influyente=bloque))
        self.assertEqual(dc.DIAS_PRODUCCION, 9862)
        self.assertEqual(list(dc.ORDEN_PROTOCOLOS), CFG["protocolos"]["orden"])
        self.assertEqual(regla.candidatos, tuple(CFG["decision"]["candidatos"]))
        self.assertEqual(regla.bloque_mas_influyente, bloque)
        self.assertEqual((regla.alfa, regla.m_holm, regla.margen_nmb_pp), (0.05, 4, 1.0))
        # Complemento, punto 3: ≤ 5 veces LightGBM compilado y ≤ 21 días con 12 hilos, sumando pm25 y no2
        self.assertEqual((regla.umbral_dias_maquina, regla.factor_maximo_frente_a_lightgbm, regla.hilos_factibilidad,
                          regla.contaminantes_factibilidad), (21.0, 5.0, 12, ("pm25", "no2")))
        # Complemento, puntos 1, 2 y 6: B = 1.999, 9.999 sorteos del cambio de signo, 3 réplicas exigidas
        self.assertEqual((regla.replicas_bootstrap, regla.replicas_salvaje, regla.replicas_exigidas), (1999, 9999, 3))
        import motores_v2 as mv
        self.assertEqual(dc.EJE_B, mv.MOTORES_EJE_B)
        malos = []
        m = json.loads(json.dumps(CFG))
        m["decision"]["estadistico"]["conjunto"] = "E2"
        malos.append(m)
        m = json.loads(json.dumps(CFG))
        m["inferencia_diferencias"]["segunda_prueba"]["metodo"]["valor"]["prueba_que_decide"] = "jackknife_cv3"
        malos.append(m)
        m = json.loads(json.dumps(CFG))
        m["inferencia_diferencias"]["segunda_prueba"]["metodo"]["valor"]["cambio_de_signo_salvaje"]["semilla"] = [42, 9999, "p"]
        malos.append(m)
        m = json.loads(json.dumps(CFG))
        m["decision"]["desempate"]["replicas_exigidas"] = 2
        malos.append(m)
        m = json.loads(json.dumps(CFG))
        m["decision"]["factibilidad"]["contaminantes"] = ["pm25"]
        malos.append(m)
        for i, malo in enumerate(malos):
            with self.subTest(caso=i), self.assertRaises(ValueError):
                dc.regla_de_config(malo)

    def test_nombres_y_familias(self):
        self.assertEqual(dc.prediccion("promedio_simple"), "promedio")
        self.assertEqual(dc.con_forma("xgboost@r2", LN), "xgboost~lognormal@r2")
        nombres = ["lightgbm", "lightgbm@r1", "lightgbm~lognormal", "promedio", "promedio~lognormal@r2", "gp", "apilado",
                   "xgboost_huber", "lightgbm_q05", "lightgbm_cqr_q95", "alertas_q80", "lightgbm_cal_solo_validado",
                   "lightgbm_ntodas", "xgboost_n300000~lognormal", "lightgbm~sens", "mlp~sens~lognormal", "idw"]
        self.assertEqual(dc.nombres_de_la_decision(nombres),
                         ["lightgbm", "lightgbm@r1", "lightgbm~lognormal", "promedio", "promedio~lognormal@r2"])
        fam = {nm: dc.familia_de(nm) for nm in nombres[5:]}
        self.assertEqual(fam, {"gp": "eje_B", "apilado": "apilado", "xgboost_huber": "perdidas",
                               "lightgbm_q05": "cuantiles", "lightgbm_cqr_q95": "cuantiles", "alertas_q80": "alertas",
                               "lightgbm_cal_solo_validado": "variantes_de_calidad",
                               "lightgbm_ntodas": "curvas_de_aprendizaje",
                               "xgboost_n300000~lognormal": "curvas_de_aprendizaje",
                               "lightgbm~sens": "sensibilidad_oof_interno", "mlp~sens~lognormal": "sensibilidad_oof_interno",
                               "idw": "eje_B"})

    def test_pares_de_la_decision_y_lo_que_quita_cada_familia(self):
        obs = np.arange(1.0, 11.0)
        uno, nan = np.ones(10), np.nan
        pred = {m: uno.copy() for m in ("lightgbm", "lightgbm@r1", "xgboost", "random_forest", "mlp", "promedio")}
        pred["lightgbm~lognormal"] = uno.copy()
        pred["mlp"][9] = nan                                                # la decisión pierde el par 9
        pred["gp"] = np.array([nan, 1, 1, 1, 1, 1, 1, 1, 1, 1])             # el eje B no quita pares de la decisión
        pred["idw"] = np.array([1, nan, nan, 1, 1, 1, 1, 1, 1, 1])
        pred["xgboost_huber"] = np.array([1, 1, 1, nan, 1, 1, 1, 1, 1, nan])
        pred["lightgbm~sens"] = np.array([1, 1, 1, 1, nan, 1, 1, 1, 1, 1])
        m, info = dc.pares_de_la_decision(obs, pred)
        np.testing.assert_array_equal(m, [True] * 9 + [False])
        self.assertEqual(info["pares_comunes"], 9)
        self.assertEqual(info["quita_por_familia"], {"eje_B": 3, "perdidas": 1, "sensibilidad_oof_interno": 1})
        self.assertEqual(info["familias"]["eje_B"], ["gp", "idw"])
        self.assertIn("mlp", info["motores_de_la_interseccion"])
        comunes, _ = mt.pares_comunes(obs, pred)
        self.assertEqual(int(comunes.sum()), 4)                             # la de todos los motores es más chica
        with self.assertRaises(ValueError):
            dc.pares_de_la_decision(obs, {"xgboost": uno})


class EvidenciaTests(unittest.TestCase):
    def test_evidencia_sin_predicciones_y_determinista(self):
        nv1, nv2 = niveles_sinteticos("LRO", semilla=3, efectos={"xgboost": 0.3})
        ev = dc.evidencia_protocolo("LRO", nv1, nv2, contaminante="pm25")
        texto = json.dumps(ev)
        self.assertEqual(set(ev["vistas"]), {dc.V_E1, dc.V_E1_SIN, dc.V_E1_LOG, dc.V_E2})
        for v in ev["vistas"].values():
            self.assertEqual(set(v), {"bloques", "n", "sw", "swo", "swoo", "motores"})
            self.assertEqual(len(v["n"]), len(BLOQUES["LRO"]))
        self.assertEqual(ev["semilla_bootstrap"], [42, 2000, 3])            # LRO es el 4.º de protocolos.orden
        self.assertEqual(ev["semilla_salvaje"], [42, 3000, 3])              # Complemento, punto 1
        self.assertEqual(ev["bloque_mas_influyente"], "RM")
        self.assertEqual(len(ev["motores"]), 5 * 3 * 2)                     # 5 motores × 3 réplicas × 2 formas
        self.assertEqual(ev, json.loads(texto))
        ev2 = dc.evidencia_protocolo("LRO", *niveles_sinteticos("LRO", semilla=3, efectos={"xgboost": 0.3}),
                                     contaminante="pm25")
        self.assertEqual(dc.huella_evidencia(ev), dc.huella_evidencia(ev2))
        evs = {"LRO": json.loads(texto), "BLQ-75": evidencia("BLQ-75", semilla=4)}
        t1, r1 = dc.decidir_motor(evs, FAC, regla=REGLA_RAPIDA)
        t2, r2 = dc.decidir_motor(json.loads(json.dumps(evs)), FAC, regla=REGLA_RAPIDA)
        pd.testing.assert_frame_equal(t1, t2)
        self.assertEqual(r1, r2)
        json.dumps(r1)                                                      # el registro es JSON puro
        self.assertEqual(len(t1), 4 * 2 * 2)
        self.assertEqual(list(t1.columns), list(dc.COLUMNAS_TABLA))
        with self.assertRaises(ValueError):
            dc.evidencia_protocolo("LRO", mt.Nivel(**{**nv1.__dict__, "nombre": "horario"}))
        with self.assertRaises(ValueError):
            dc.decidir_motor({"LRO": evs["LRO"]}, FAC)
        otro = dict(evs["BLQ-75"], contaminante="no2")
        with self.assertRaises(ValueError):
            dc.decidir_motor({"LRO": evs["LRO"], "BLQ-75": otro}, FAC)
        # la decisión usa las semillas declaradas: una evidencia con la semilla vieja del bootstrap salvaje se rechaza
        vieja = dict(evs["BLQ-75"], semilla_salvaje=[42, 9999, 2])
        with self.assertRaises(ValueError) as e:
            dc.decidir_motor({"LRO": evs["LRO"], "BLQ-75": vieja}, FAC, regla=REGLA_RAPIDA)
        self.assertIn("semillas", str(e.exception))
        with self.assertRaises(ValueError):
            dc.decidir_motor({"LRO": evs["LRO"], "BLQ-75": dict(evs["BLQ-75"], schema="x.v1")}, FAC, regla=REGLA_RAPIDA)


class DecisionTests(unittest.TestCase):
    def test_candidato_verdaderamente_superior_reemplaza(self):
        evs = evidencias(semilla=10, efectos={"xgboost": 0.35})
        tabla, reg = dc.decidir_motor(evs, FAC, regla=REGLA_RAPIDA)
        self.assertEqual(reg["decision"]["motor"], "xgboost")
        self.assertTrue(reg["decision"]["reemplaza_a_lightgbm"])
        self.assertTrue(reg["decision"]["coinciden_las_formas"])
        self.assertEqual(reg["candidatos"]["xgboost"]["estado"], "reemplaza a LightGBM")
        for p in ("LRO", "BLQ-75"):
            for f in (rt.SMEARING, rt.LOGNORMAL):
                x = fila(tabla, "xgboost", p, f)
                for col in dc.COLUMNA_CONDICION.values():
                    self.assertTrue(bool(x[col]), f"{p} {f} {col}")
                self.assertTrue(x["pasa"])
                self.assertGreater(x["delta_r2"], 0)
                self.assertLess(x["p_bootstrap"], x["alfa_holm_bootstrap"])
                self.assertGreater(x["ic_inf_holm"], 0)                       # el intervalo escalonado publicado
                self.assertTrue(x["declarada_intervalo_holm"] and x["coinciden_p_e_intervalo"])
                self.assertEqual(x["segunda_prueba"], "cambio_de_signo_salvaje")
                self.assertLess(x["p_salvaje"], x["alfa_holm_salvaje"])
                self.assertTrue(x["declarada_salvaje"] and x["a_favor_salvaje"])
                self.assertTrue(np.isfinite(x["p_jackknife"]))                 # el CV3 se informa
            self.assertEqual(fila(tabla, "xgboost", p)["sorteos_salvaje"],
                             "enumeracion_completa" if p == "LRO" else "199")   # LRO: G = 15; BLQ-75: G = 18
            for c in ("random_forest", "mlp", "promedio_simple"):
                self.assertFalse(fila(tabla, c, p)["pasa"])
        self.assertEqual(reg["protocolos"]["LRO"]["influencia"]["bloque"], "RM")
        self.assertEqual(len(reg["protocolos"]["BLQ-75"]["delta_r2_sin_cada_bloque"]["xgboost"]), len(BLOQUES["BLQ-75"]))

    def test_candidatos_nulos_no_pasan_mas_de_lo_esperado(self):
        """Con los cuatro candidatos nulos (heterogeneidad entre bloques incluida), la condición 1 declara algún
        candidato a lo sumo con la tasa familiar de Holm (5 %, más el error de Monte Carlo) y la regla completa casi
        nunca reemplaza."""
        regla = dc.ReglaDecision(replicas_bootstrap=499, replicas_salvaje=99)
        n_sim, reemplazos = 120, 0
        c1 = {"LRO": 0, "BLQ-75": 0}
        for i in range(n_sim):
            evs = evidencias(semilla=1000 + 7 * i, tau=0.15, estaciones_por_bloque=1, dias=60)
            tabla, reg = dc.decidir_motor(evs, FAC, regla=regla)
            for p in c1:
                prim = tabla[(tabla["forma"] == rt.SMEARING) & (tabla["protocolo"] == p)]
                c1[p] += int(prim["c1_superioridad"].astype(bool).any())
            reemplazos += int(reg["decision"]["reemplaza_a_lightgbm"])
        cota = 0.05 + 3 * np.sqrt(0.05 * 0.95 / n_sim)
        for p, k in c1.items():
            self.assertLessEqual(k / n_sim, cota, p)
        self.assertLessEqual(reemplazos / n_sim, 0.02)

    def test_superioridad_que_depende_de_un_bloque_no_es_robusta(self):
        """En LRO la RM concentra ≈ 64 % del peso y la ventaja de XGBoost es firme allí (δ = 0,2), mientras que en
        los demás bloques es menor y muy heterogénea (δ = 0,12 con τ = 0,35): la condición 1 se cumple con todos los
        bloques (el cambio de signo, con la enumeración completa de G = 15, da p ≈ 0,009 < 0,0125) y no sin la RM
        (G = 14, p ≈ 0,018 > α de Holm): condición 4. En BLQ-75 XGBoost es superior. No reemplaza a LightGBM: queda
        como «evidencia parcial»."""
        lro = {"por_bloque": {"xgboost": {"RM": 0.2}}, "efectos": {"xgboost": 0.12}, "peso_bloque": {"RM": 40000.0},
               "estaciones_por_bloque": 2, "semilla": 25, "tau": 0.35}
        evs = evidencias(lro=lro, blq={"efectos": {"xgboost": 0.35}}, semilla=20)
        tabla, reg = dc.decidir_motor(evs, FAC, regla=REGLA_RAPIDA)
        x = fila(tabla, "xgboost", "LRO")
        self.assertTrue(x["c1_superioridad"])
        self.assertFalse(x["c4_influencia"])
        self.assertEqual(x["estado_influencia"], "sin el bloque RM")
        self.assertLess(x["delta_r2_sin_bloque_influyente"], x["delta_r2"])
        self.assertFalse(x["pasa"])
        self.assertTrue(fila(tabla, "xgboost", "BLQ-75")["pasa"])
        self.assertEqual(reg["decision"]["motor"], "lightgbm")
        cand = reg["candidatos"]["xgboost"]
        self.assertIn("no robusta", cand["motivo_por_protocolo"]["LRO"][rt.SMEARING])
        self.assertEqual(cand["superior_en"], ["BLQ-75"])
        self.assertTrue(cand["evidencia_parcial"])
        self.assertTrue(cand["sensibilidad_de_exposicion"])
        self.assertEqual(cand["estado"], "evidencia parcial")
        self.assertEqual(reg["evidencia_parcial"], ["xgboost"])

    def test_cambia_con_lognormal_no_reemplaza(self):
        """XGBoost cumple todo con smearing, pero con ½·σ² su sesgo sube 15 % (condición 7): las dos correcciones no
        eligen el mismo motor y se mantiene LightGBM (condición 6)."""
        evs = evidencias(semilla=30, efectos={"xgboost": 0.35}, sesgo_lognormal={"xgboost": 0.15})
        tabla, reg = dc.decidir_motor(evs, FAC, regla=REGLA_RAPIDA)
        for p in ("LRO", "BLQ-75"):
            s, l_ = fila(tabla, "xgboost", p, rt.SMEARING), fila(tabla, "xgboost", p, rt.LOGNORMAL)
            self.assertTrue(s["pasa_sin_c6"])
            self.assertFalse(l_["c7_no_inferioridad_en_sesgo"])
            self.assertFalse(s["c6_misma_decision_con_lognormal"])
            self.assertFalse(s["pasa"])
        self.assertEqual(reg["decision"]["motor"], "lightgbm")
        self.assertFalse(reg["decision"]["reemplaza_a_lightgbm"])
        self.assertFalse(reg["decision"]["coinciden_las_formas"])
        self.assertEqual(reg["decision"]["por_forma"][rt.SMEARING]["elegido"], "xgboost")
        self.assertEqual(reg["decision"]["por_forma"][rt.LOGNORMAL]["elegido"], "lightgbm")
        self.assertIn("condición 6", reg["decision"]["motivo"])
        self.assertEqual(reg["candidatos"]["xgboost"]["estado"], "no cumple la regla")

    def test_e2_con_otro_signo_bloquea_y_no_evaluable_no_bloquea(self):
        # fuera de E2 XGBoost es mucho mejor (δ = 0,5); en E2 (60 % de las filas), algo peor (δ = −0,1): E1 sigue a su
        # favor y E2 tiene el signo contrario
        evs = evidencias(semilla=40, efectos={"xgboost": 0.5}, efecto_e2={"xgboost": -0.1}, frac_e2=0.6)
        tabla, reg = dc.decidir_motor(evs, FAC, regla=REGLA_RAPIDA)
        x = fila(tabla, "xgboost", "LRO")
        self.assertTrue(x["c1_superioridad"])
        self.assertGreater(x["delta_r2"], 0)
        self.assertTrue(x["e2_evaluable"])
        self.assertLess(x["delta_r2_E2"], 0)
        self.assertFalse(x["c3_consistencia_con_E2"])
        self.assertEqual(reg["decision"]["motor"], "lightgbm")
        # con E2 en sólo 4 bloques, E2 no es evaluable: no bloquea y se informa
        evs = evidencias(semilla=40, efectos={"xgboost": 0.5}, efecto_e2={"xgboost": -0.1}, frac_e2=0.6, bloques_e2=4)
        tabla, reg = dc.decidir_motor(evs, FAC, regla=REGLA_RAPIDA)
        x = fila(tabla, "xgboost", "LRO")
        self.assertFalse(x["e2_evaluable"])
        self.assertEqual(x["estado_E2"], mt.SIN_CONFIRMACION)
        self.assertTrue(x["c3_consistencia_con_E2"])
        self.assertEqual(reg["decision"]["motor"], "xgboost")
        self.assertIn("4 grupos", " ".join(reg["protocolos"]["LRO"]["evaluabilidad_E2"]["motivo"]))

    def test_ruido_signo_y_sesgo(self):
        # sin réplicas, el ruido de la diferencia queda no evaluado y no basta para reemplazar
        evs = evidencias(semilla=50, efectos={"xgboost": 0.35}, replicas=1)
        tabla, reg = dc.decidir_motor(evs, FAC, regla=REGLA_RAPIDA)
        x = fila(tabla, "xgboost", "LRO")
        self.assertTrue(x["c1_superioridad"])
        self.assertTrue(pd.isna(x["c2_ruido_de_la_diferencia"]))
        self.assertEqual(reg["decision"]["motor"], "lightgbm")
        self.assertIn("ruido no evaluado", reg["candidatos"]["xgboost"]["motivo_por_protocolo"]["LRO"][rt.SMEARING])
        # con 2 réplicas tampoco: la condición 2 exige las 3 réplicas comunes (Complemento, punto 6)
        evs = evidencias(semilla=50, efectos={"xgboost": 0.35}, replicas=2)
        tabla, reg = dc.decidir_motor(evs, FAC, regla=REGLA_RAPIDA)
        x = fila(tabla, "xgboost", "LRO")
        self.assertTrue(x["c1_superioridad"])
        self.assertFalse(x["replicas_completas"])
        self.assertTrue(np.isfinite(x["delta_r2_r1"]) and np.isnan(x["delta_r2_r2"]))
        self.assertTrue(pd.isna(x["c2_ruido_de_la_diferencia"]) and np.isnan(x["ruido"]))
        self.assertFalse(x["pasa"])
        self.assertEqual(reg["decision"]["motor"], "lightgbm")
        self.assertIn("exige las 3 réplicas", reg["candidatos"]["xgboost"]["motivo_por_protocolo"]["LRO"][rt.SMEARING])
        # un ruido de semilla enorme frente al efecto: |Δ̄| no supera el rango de los Δ_r
        evs = evidencias(semilla=51, efectos={"xgboost": 0.04}, ruido_replica=6.0)
        tabla, _ = dc.decidir_motor(evs, FAC, regla=REGLA_RAPIDA)
        x = fila(tabla, "xgboost", "LRO")
        self.assertEqual(bool(x["c2_ruido_de_la_diferencia"]), abs(x["delta_r2"]) > x["ruido"])
        self.assertAlmostEqual(x["ruido"], np.ptp([x["delta_r2_r0"], x["delta_r2_r1"], x["delta_r2_r2"]]), places=12)
        # un sesgo de +3 unidades (≈ 10 %) rompe la no inferioridad en sesgo aunque el error baje
        evs = evidencias(semilla=52, efectos={"xgboost": 0.35}, sesgo={"xgboost": 3.0})
        tabla, reg = dc.decidir_motor(evs, FAC, regla=REGLA_RAPIDA)
        x = fila(tabla, "xgboost", "LRO")
        self.assertFalse(x["c7_no_inferioridad_en_sesgo"])
        self.assertGreater(abs(x["nmb_candidato_pct"]), abs(x["nmb_referencia_pct"]) + 1.0)
        self.assertEqual(reg["decision"]["motor"], "lightgbm")
        # el signo sin ponderar y en log se calcula con su vista
        nv1, nv2 = niveles_sinteticos("LRO", semilla=53, efectos={"xgboost": 0.35})
        ev = dc.evidencia_protocolo("LRO", nv1, nv2)
        S_sin = bs.SumasBloques.desde_dict(ev["vistas"][dc.V_E1_SIN])
        r = dc.evaluar_protocolo(ev, regla=REGLA_RAPIDA)["candidatos"]["xgboost"]
        self.assertAlmostEqual(r["delta_r2_sin_ponderar"], bs.delta_medio(S_sin, "xgboost", "lightgbm"), places=12)
        directo = np.mean([mt.metricas(nv1.log_obs, nv1.log[bs.nombre_replica("xgboost", k)], nv1.poblacion)["r2"]
                           - mt.metricas(nv1.log_obs, nv1.log[bs.nombre_replica("lightgbm", k)], nv1.poblacion)["r2"]
                           for k in range(3)])
        self.assertAlmostEqual(r["delta_r2_log"], directo, places=10)
        self.assertTrue(r["signo_sin_ponderar_y_en_log"])

    def test_factibilidad_y_desempate(self):
        # RF y el promedio repiten las predicciones de XGBoost (réplicas incluidas): los tres pasan y sus diferencias
        # (nulas) no superan el ruido, así que empatan; se prefiere un motor único al promedio y, entre los únicos,
        # el más barato de producir
        evs = evidencias(semilla=60, efectos={"xgboost": 0.33},
                         iguales={"random_forest": "xgboost", "promedio_simple": "xgboost"})
        _, reg = dc.decidir_motor(evs, fac_con(random_forest=(9.0, 7.0)), regla=REGLA_RAPIDA)
        d = reg["decision"]["por_forma"][rt.SMEARING]
        self.assertEqual(set(d["elegibles"]), {"xgboost", "random_forest", "promedio_simple"})
        self.assertEqual(set(d["empatados"]), {"xgboost", "random_forest", "promedio_simple"})
        self.assertTrue(d["desempate_evaluado"])
        self.assertEqual(d["elegido"], "random_forest")
        self.assertIn("motor único", d["motivo"])
        self.assertEqual(reg["decision"]["motor"], "random_forest")
        self.assertEqual(reg["candidatos"]["xgboost"]["estado"], "cumple la regla pero pierde el desempate")
        _, reg = dc.decidir_motor(evs, fac_con(xgboost=(5.0, 4.0)), regla=REGLA_RAPIDA)
        self.assertEqual(reg["decision"]["motor"], "xgboost")
        # RF seis veces más caro que LightGBM compilado (aunque en 12,6 días < 21): queda fuera por el factor
        _, reg = dc.decidir_motor(evs, fac_con(random_forest=(60.0, 48.0)), regla=REGLA_RAPIDA)
        rf = reg["candidatos"]["random_forest"]
        self.assertFalse(rf["factibilidad"]["factible"])
        self.assertAlmostEqual(rf["factibilidad"]["cociente_frente_a_lightgbm"], 108.0 / 18.0, places=12)
        self.assertAlmostEqual(rf["factibilidad"]["dias_de_maquina"], 108.0 * 9862 / 86400, places=9)
        self.assertIn("veces lo que LightGBM", rf["factibilidad"]["motivo"])
        self.assertEqual(rf["estado"], "fuera de la decisión por factibilidad")
        self.assertNotIn("random_forest", reg["decision"]["por_forma"][rt.SMEARING]["elegibles"])
        self.assertIn("referencia", reg["factibilidad"])
        with self.assertRaises(ValueError):
            dc.decidir_motor(evs, None, regla=REGLA_RAPIDA)
        with self.assertRaises(ValueError):
            dc.decidir_motor(evs, {"xgboost": {"pm25": 1.0, "no2": 1.0}}, regla=REGLA_RAPIDA)   # sin LightGBM

    def test_regla_de_factibilidad_del_complemento(self):
        """Complemento, punto 3: por contaminante, segundos por día × 9.862 días; se suman pm25 y no2; factible si
        cuesta ≤ 5 veces LightGBM compilado y ≤ 21 días de máquina; el promedio cuesta la suma de sus miembros;
        LightGBM es la referencia y no se excluye; los 3 días medidos se promedian."""
        f = dc.evaluar_factibilidad(FAC)
        dias = lambda s: s * 9862 / 86400                                      # noqa: E731
        self.assertAlmostEqual(f["_referencia"]["dias_de_maquina"], dias(18.0), places=12)
        prom = f["promedio_simple"]
        self.assertEqual(prom["segundos_por_dia"], {"pm25": 48.0, "no2": 39.0})     # la suma de los cuatro
        self.assertAlmostEqual(prom["cociente_frente_a_lightgbm"], 87.0 / 18.0, places=12)
        self.assertTrue(prom["factible"])
        self.assertTrue(all(f[c]["factible"] for c in dc.CANDIDATOS))
        # el factor: justo 5 veces es factible; un poco más, no
        borde = dc.evaluar_factibilidad(fac_con(mlp=(50.0, 40.0)))["mlp"]         # 90 = 5 × 18
        self.assertEqual(borde["cociente_frente_a_lightgbm"], 5.0)
        self.assertTrue(borde["factible"])
        self.assertFalse(dc.evaluar_factibilidad(fac_con(mlp=(50.0, 40.01)))["mlp"]["factible"])
        # los días: con un LightGBM lento (25 días, no se excluye) un candidato 1,1 veces más caro pasa de 21 días
        lento = dc.evaluar_factibilidad(fac_con(lightgbm=(110.0, 109.0), xgboost=(120.0, 120.0)))
        self.assertGreater(lento["_referencia"]["dias_de_maquina"], 21.0)
        self.assertLess(lento["xgboost"]["cociente_frente_a_lightgbm"], 5.0)
        self.assertFalse(lento["xgboost"]["factible"])
        self.assertIn("días de máquina", lento["xgboost"]["motivo"])
        # 21 días exactos son factibles: 21 × 86.400 / 9.862 = 183,98 s por día entre los dos contaminantes
        s21 = 21 * 86400 / 9862
        justo = dc.evaluar_factibilidad(fac_con(lightgbm=(s21 / 2, s21 / 2), xgboost=(s21 / 2, s21 / 2)))["xgboost"]
        self.assertAlmostEqual(justo["dias_de_maquina"], 21.0, places=9)
        self.assertTrue(justo["factible"])
        # los 3 días medidos se promedian; un valor propio del promedio sólo se registra
        tres = dc.evaluar_factibilidad({**FAC, "xgboost": {"segundos_por_dia": {"pm25": [10.0, 12.0, 14.0], "no2": 10.0},
                                                            "fuente": "prueba"},
                                        "promedio_simple": {"pm25": 1.0, "no2": 1.0}})
        self.assertEqual(tres["xgboost"]["segundos_por_dia"]["pm25"], 12.0)
        self.assertEqual(tres["xgboost"]["fuente"], {"fuente": "prueba"})
        self.assertEqual(tres["promedio_simple"]["segundos_por_dia"], {"pm25": 48.0, "no2": 39.0})
        self.assertIn("informado", tres["promedio_simple"]["fuente"])
        for malo in ({**FAC, "mlp": {"pm25": 6.0}}, {k: v for k, v in FAC.items() if k != "lightgbm"},
                     {**FAC, "xgboost": 22.0}, {**FAC, "mlp": {"pm25": -1.0, "no2": 5.0}}):
            with self.assertRaises(ValueError):
                dc.evaluar_factibilidad(malo)

    def test_desempate_con_diferencia_mayor_que_el_ruido(self):
        evs = evidencias(semilla=70, efectos={"xgboost": 0.45, "random_forest": 0.25}, ruido_replica=0.05)
        _, reg = dc.decidir_motor(evs, fac_con(random_forest=(1.0, 1.0)), regla=REGLA_RAPIDA)
        d = reg["decision"]["por_forma"][rt.SMEARING]
        self.assertEqual(set(d["elegibles"]), {"xgboost", "random_forest"})
        self.assertEqual(d["primero_por_puntaje"], "xgboost")
        self.assertFalse(d["diferencias_con_el_primero"]["random_forest"]["empata_con_el_primero"])
        self.assertEqual(reg["decision"]["motor"], "xgboost")              # más caro, pero claramente mejor
        self.assertEqual(reg["candidatos"]["random_forest"]["estado"], "cumple la regla pero pierde el desempate")

    def test_desempate_exige_las_tres_replicas(self):
        """Complemento, punto 6: si dos candidatos que pasan no tienen las 3 réplicas comunes, el desempate queda
        «no evaluado» y no da el reemplazo."""
        fac = dc.evaluar_factibilidad(FAC)

        def por_prot(r2_por_replica):
            return {p: {"candidatos": {c: {"r2_candidato": float(np.mean(list(v.values()))), "r2_candidato_por_replica": v}
                                       for c, v in r2_por_replica.items()}} for p in ("LRO", "BLQ-75")}

        completo = por_prot({"xgboost": {0: 0.50, 1: 0.51, 2: 0.49}, "random_forest": {0: 0.40, 1: 0.41, 2: 0.39}})
        d = dc._desempate(["xgboost", "random_forest"], completo, fac, dc.REGLA)
        self.assertTrue(d["desempate_evaluado"])
        self.assertEqual(d["elegido"], "xgboost")
        incompleto = por_prot({"xgboost": {0: 0.50, 1: 0.51}, "random_forest": {0: 0.40, 1: 0.41, 2: 0.39}})
        d = dc._desempate(["xgboost", "random_forest"], incompleto, fac, dc.REGLA)
        self.assertFalse(d["desempate_evaluado"])
        self.assertEqual(d["elegido"], "lightgbm")
        self.assertIn("no evaluado", d["motivo"])
        self.assertIsNone(d["diferencias_con_el_primero"]["random_forest"]["empata_con_el_primero"])
        uno = dc._desempate(["xgboost"], incompleto, fac, dc.REGLA)          # sin desempate que hacer
        self.assertEqual(uno["elegido"], "xgboost")

    def test_decide_el_cambio_de_signo_y_no_el_jackknife(self):
        """Complemento, punto 1: la segunda prueba que decide es el cambio de signo del bootstrap salvaje. Si su p
        no declara, la condición 1 falla aunque todo lo demás pase; el jackknife CV3 no cambia la decisión."""
        from unittest import mock

        evs = evidencias(semilla=10, efectos={"xgboost": 0.35})
        base_t, base_r = dc.decidir_motor(evs, FAC, regla=REGLA_RAPIDA)
        self.assertEqual(base_r["decision"]["motor"], "xgboost")
        original = bs.cambio_de_signo_salvaje
        with mock.patch.object(bs, "cambio_de_signo_salvaje", lambda *a, **k: {**original(*a, **k), "p": 1.0}):
            t2, r2 = dc.decidir_motor(evs, FAC, regla=REGLA_RAPIDA)
        x = fila(t2, "xgboost", "LRO")
        self.assertTrue(x["declarada_bootstrap"] and x["declarada_intervalo_holm"])
        self.assertFalse(x["declarada_salvaje"])
        self.assertFalse(x["c1_superioridad"])
        self.assertEqual(r2["decision"]["motor"], "lightgbm")
        jk = bs.jackknife_cv3
        with mock.patch.object(bs, "jackknife_cv3", lambda T, W: {**jk(T, W), "p": 1.0}):
            t3, r3 = dc.decidir_motor(evs, FAC, regla=REGLA_RAPIDA)
        self.assertEqual(r3["decision"], base_r["decision"])                  # el CV3 sólo informa
        pd.testing.assert_series_equal(t3["c1_superioridad"], base_t["c1_superioridad"])
        self.assertTrue((t3["p_jackknife"] == 1.0).all())


if __name__ == "__main__":
    unittest.main()
