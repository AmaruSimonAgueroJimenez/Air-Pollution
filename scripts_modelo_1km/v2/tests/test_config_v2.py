"""Pruebas de ``config_v2.json``: que traduzca el contrato vigente, cifra por cifra, y marque lo que falta."""
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))
import _rutas_v2 as rv  # noqa: E402

TEXTO = (V2 / rv.NOMBRE_CONFIG).read_text(encoding="utf-8")
CFG = json.loads(TEXTO)
CONTRATO = (V2 / rv.NOMBRE_CONTRATO).read_text(encoding="utf-8")


# Cada provisional es una decisión que no es contrato (se ratifica o corrige por enmienda): se enumeran a mano para
# que ninguno entre sin querer. Los de la pieza de pliegues y los de motores, pérdidas y métricas.
PROVISIONALES_PLIEGUES = ["protocolos.BLQ-75.origen_m", "protocolos.semilla.k"]
PROVISIONALES_MOTORES = [
    "calidad_blanco.codigos_qc", "calidad_blanco.snifa.cruce_con_variantes_sinca",
    "filas_entrenamiento.disponibles_menos_que_el_tope", "filas_entrenamiento.permutacion.generador",
    "inferencia_diferencias.bootstrap.metodo_del_intervalo", "inferencia_diferencias.bootstrap.nivel_de_agregacion",
    "inferencia_diferencias.bootstrap.semilla", "inferencia_diferencias.regla_de_superioridad.medida_del_ruido",
    "metricas.desagregaciones.estrato_de_soporte.distribucion_de_referencia",
    "metricas.desagregaciones.ponderado_por_poblacion.poblacion",
    "metricas.desagregaciones.regimen_de_predictores.criterio", "metricas.niveles.anual.minimo_meses",
    "metricas.niveles.mensual.minimo_dias", "motores.alertas.receta", "motores.apilado_anidado.bases",
    "motores.apilado_anidado.escala", "motores.apilado_anidado.pliegues_internos",
    "motores.eje_A.mlp.parada_temprana.criterio", "motores.eje_A.mlp.parada_temprana.fraccion",
    "motores.eje_A.promedio_simple.escala", "motores.eje_A.random_forest.n_jobs",
    "motores.eje_A.xgboost.colsample.variante", "motores.eje_A.xgboost.determinismo", "motores.eje_A.xgboost.max_bin",
    "motores.eje_A.xgboost.max_depth", "motores.eje_A.xgboost.min_child_weight", "motores.eje_A.xgboost.nthread",
    "motores.eje_A.xgboost.seed", "motores.eje_B.topes_de_filas", "perdidas.hiperparametros_por_perdida",
    "perdidas.variantes[2].delta.ajuste_cuadratico", "perdidas.variantes[2].delta.mad",
    "perdidas.variantes[2].implementacion_xgboost", "presupuesto.piloto.eleccion_de_los_pliegues",
    "retransformacion.primaria.global_de_los_demas_con_menos_de_100_filas",
    "retransformacion.sensibilidad.pliegues_internos", "ruido.valores",
]


def pendientes(nodo, ruta=""):
    """Recorre la configuración y devuelve (ruta, valor) de cada campo pendiente."""
    if isinstance(nodo, dict):
        if nodo.get("estado") == "pendiente":
            yield ruta, nodo
            return
        for k, v in nodo.items():
            yield from pendientes(v, f"{ruta}.{k}" if ruta else k)
    elif isinstance(nodo, list):
        for i, v in enumerate(nodo):
            yield from pendientes(v, f"{ruta}[{i}]")
    elif nodo == "pendiente":
        yield ruta, nodo


class ContratoTests(unittest.TestCase):
    def test_traduce_el_contrato_vigente(self):
        sha = hashlib.sha256((V2 / rv.NOMBRE_CONTRATO).read_bytes()).hexdigest()
        self.assertEqual(CFG["contrato"]["sha256"], sha)
        self.assertEqual(CFG["contrato"]["enmiendas"], [])
        self.assertIn("## Enmiendas\n\n(ninguna)", CONTRATO)

    def test_sin_rutas_absolutas_de_la_cuenta(self):
        for prohibido in ("/Users/", "GoogleDrive", "CloudStorage", "@gmail"):
            self.assertNotIn(prohibido, TEXTO)

    def test_pendientes_bien_formados(self):
        lista = list(pendientes(CFG))
        self.assertGreater(len(lista), 20)
        for ruta, valor in lista:
            if isinstance(valor, dict):
                self.assertTrue(valor.get("nota"), f"{ruta}: un pendiente con objeto lleva nota")
        con_provisional = sorted(r for r, v in lista if isinstance(v, dict) and "provisional" in v)
        self.assertEqual(con_provisional, sorted(PROVISIONALES_PLIEGUES + PROVISIONALES_MOTORES))
        sin_provisional = sorted(r for r, v in lista if not (isinstance(v, dict) and "provisional" in v))
        self.assertEqual(sin_provisional, ["decision.combinacion_de_protocolos"])


class ProtocolosTests(unittest.TestCase):
    p = CFG["protocolos"]

    def test_los_cinco_protocolos(self):
        self.assertEqual(self.p["orden"], ["LOSO-D", "LBO-10", "BLQ-75", "LRO", "LPO"])
        self.assertEqual(self.p["manifiesto"]["archivo"], "pliegues_v2.json")

    def test_loso_d(self):
        d = self.p["LOSO-D"]
        self.assertEqual((d["umbral_km"], d["comparacion"], d["metodo"]), (2.0, "<=", "componentes conexas"))
        self.assertTrue(d["une_celdas_compartidas"])
        self.assertEqual(d["retira_juntos_ejemplos"], [["309", "310", "330", "333"], ["B03", "B04"], ["503", "548"]])
        self.assertEqual((d["distancia"]["formula"], d["distancia"]["radio_tierra_km"]), ("haversine", 6371.0))
        self.assertEqual(d["exclusion_adicional"], "ninguna")

    def test_lbo_blq_lro_lpo(self):
        b = self.p["LBO-10"]["exclusion_adicional"]
        self.assertEqual((b["radio_km"], b["comparacion"]), (10.0, "<="))
        q = self.p["BLQ-75"]
        self.assertEqual((q["lado_m"], q["crs"], q["exclusion_adicional"]), (75000.0, "EPSG:32719", "ninguna"))
        self.assertEqual(q["origen_m"]["provisional"], [0.0, 0.0])
        self.assertEqual(self.p["LRO"]["grupo_prueba"], "region_sinca")
        self.assertEqual(self.p["LRO"]["equivalencias"], {"RXVI": "RVIII"})
        v = self.p["LPO"]["ventanas"]
        self.assertEqual((v["anio_desde"], v["anio_hasta"], v["largo_anios"]), (2000, 2026, 4))
        self.assertEqual(self.p["semilla"]["regla"], [42, "k"])

    def test_regla_unica_de_exclusion_y_vecindario(self):
        self.assertEqual(CFG["regla_exclusion"]["se_aplica_a"],
                         ["filas de entrenamiento", "vecindario de entrenamiento", "vecindario de prueba",
                          "residuos de la retransformación"])
        v = CFG["vecindario"]
        self.assertEqual(v["recalculo"]["protocolos"], ["LOSO-D", "LBO-10", "BLQ-75", "LRO"])
        self.assertFalse(v["recalculo"]["atajo_para_conjuntos_de_una_estacion"])
        self.assertEqual(v["implementacion"]["ancho_km"], 150.0)


class MotoresTests(unittest.TestCase):
    m = CFG["motores"]

    def test_lightgbm_receta_v1_determinista(self):
        g = self.m["eje_A"]["lightgbm"]
        esperado = {"num_boost_round": 800, "learning_rate": 0.03, "num_leaves": 127, "min_data_in_leaf": 50,
                    "bagging_fraction": 0.8, "bagging_freq": 1, "feature_fraction": 0.8, "lambda_l2": 1.0,
                    "deterministic": True, "force_col_wise": True, "num_threads": 12, "objective": "regression"}
        self.assertEqual({k: g[k] for k in esperado}, esperado)

    def test_xgboost_equivalente(self):
        x = self.m["eje_A"]["xgboost"]
        esperado = {"tree_method": "hist", "max_leaves": 127, "grow_policy": "lossguide", "eta": 0.03,
                    "num_boost_round": 800, "subsample": 0.8, "lambda": 1.0}
        self.assertEqual({k: x[k] for k in esperado}, esperado)
        self.assertEqual(x["colsample"]["valor"], 0.8)
        self.assertEqual(x["min_child_weight"]["estado"], "pendiente")

    def test_rf_mlp_y_promedio(self):
        rf = self.m["eje_A"]["random_forest"]
        self.assertEqual((rf["n_estimators"], rf["max_features"], rf["min_samples_leaf"]), (300, "sqrt", 20))
        mlp = self.m["eje_A"]["mlp"]
        self.assertEqual(mlp["parada_temprana"]["validacion"], "agrupada por estación, no al azar")
        self.assertEqual(mlp["hidden_layer_sizes"], [128, 64])
        self.assertEqual(self.m["eje_A"]["promedio_simple"]["motores"], ["lightgbm", "xgboost", "random_forest", "mlp"])

    def test_predictores_de_la_v1(self):
        pm, no = self.m["eje_A"]["predictores"]["pm25"], self.m["eje_A"]["predictores"]["no2"]
        self.assertEqual((len(pm), len(no)), (70, 69))
        self.assertEqual([c for c in pm if c != "dist_costa_km"], no)
        self.assertEqual(len(set(pm)), 70)

    def test_eje_b_alertas_hiperparametros_apilado(self):
        self.assertEqual(self.m["eje_B"]["motores"], ["gp", "lme", "gwr", "rk", "idw"])
        self.assertEqual(self.m["eje_B"]["preprocesamiento_dentro_del_pliegue"],
                         ["medianas", "indicadoras", "escala", "selección por cobertura"])
        self.assertEqual(self.m["alertas"]["cuantil"], 0.8)
        self.assertFalse(self.m["hiperparametros"]["busqueda"])
        a = self.m["apilado_anidado"]
        self.assertEqual(a["protocolos"], ["LRO", "BLQ-75"])
        self.assertEqual(a["pesos"], {"no_negativos": True, "suman_1": True})
        self.assertFalse(a["compite_fuera_de_esos_protocolos"])


class FilasRetransformacionPerdidasTests(unittest.TestCase):
    def test_filas(self):
        f = CFG["filas_entrenamiento"]
        self.assertEqual(f["permutacion"]["semilla"], [42, "k"])
        self.assertEqual(f["N_comun_eje_A"], 750000)
        c = f["curvas_de_aprendizaje"]
        self.assertEqual(c["protocolos"], ["LRO", "BLQ-75"])
        self.assertEqual(c["lightgbm"], [300000, 750000, 1500000, "todas"])
        self.assertEqual(c["xgboost"], [300000, 750000, 1500000, "todas"])
        self.assertEqual(c["random_forest"], [300000, 750000, 1500000])

    def test_retransformacion(self):
        r = CFG["retransformacion"]
        p = r["primaria"]
        self.assertEqual((p["clave"], p["franja_diurna_horas_locales"], p["minimo_filas"]), ("macrozona|franja", [8, 18], 100))
        self.assertEqual(p["respaldo"], ["franja de los demás grupos", "global de los demás grupos"])
        self.assertEqual(r["sensibilidad"]["protocolos"], ["LRO", "BLQ-75"])
        self.assertTrue(r["metricas_en_log"])

    def test_perdidas(self):
        p = CFG["perdidas"]
        self.assertEqual(p["motores"], ["lightgbm", "xgboost"])
        self.assertEqual([v["id"] for v in p["variantes"]], ["l2_log_duan", "l2_original", "huber", "pinball"])
        huber = p["variantes"][2]
        self.assertEqual(huber["delta"]["factor"], 1.345)
        self.assertEqual(p["variantes"][3]["taus"], [0.05, 0.5, 0.95])
        self.assertEqual(p["metricas_comunes_escala_original"], ["R2", "RMSE", "MAE", "NMB"])
        self.assertEqual(p["metricas_cuantiles"]["cobertura_del_intervalo"], 0.9)


class CalidadMetricasDecisionTests(unittest.TestCase):
    def test_calidad(self):
        c = CFG["calidad_blanco"]
        self.assertEqual([v["id"] for v in c["variantes_entrenamiento"]], ["todo", "validado_y_preliminar", "solo_validado"])
        self.assertEqual(c["snifa"]["variantes"], ["numeric_usable", "usable_native"])
        self.assertEqual(c["comparacion_de_variantes"], {"motor": "lightgbm", "eje": "A", "protocolos": ["LOSO-D", "LRO"]})

    def test_metricas_ruido_inferencia(self):
        m = CFG["metricas"]
        self.assertEqual(m["niveles"]["diario"], {"dias": ["civil America/Santiago", "UTC−4"], "minimo_horas": 18})
        self.assertEqual(set(m["desagregaciones"]), {"macrozona", "estacion", "regimen_de_predictores",
                                                     "estrato_de_soporte", "ponderado_por_poblacion"})
        self.assertEqual(m["desagregaciones"]["estrato_de_soporte"]["variables"], ["peso_vec", "dist_est_km"])
        r = CFG["ruido"]
        self.assertEqual((r["semillas"], r["protocolos_con_3_semillas"], r["semillas_en_los_demas_protocolos"]),
                         (3, ["LRO", "BLQ-75"], 1))
        b = CFG["inferencia_diferencias"]["bootstrap"]
        self.assertEqual(b["replicas"], 2000)
        self.assertEqual(b["unidad"], {"LOSO-D": "conglomerado", "LBO-10": "conglomerado", "BLQ-75": "bloque",
                                       "LRO": "region", "LPO": "cuatrienio"})
        self.assertEqual(CFG["inferencia_diferencias"]["regla_de_superioridad"]["nivel_del_intervalo"], 0.95)

    def test_decision_y_presupuesto(self):
        d = CFG["decision"]
        self.assertEqual(d["protocolos"], ["LRO", "BLQ-75"])
        self.assertTrue(d["por_omision"].startswith("lightgbm"))
        p = CFG["presupuesto"]
        self.assertEqual((p["piloto"]["pliegues_por_protocolo_y_motor"], p["umbral_horas_maquina"]), (2, 120))
        self.assertEqual([x["recorte"] for x in p["orden_de_recortes"]],
                         ["semillas sólo en LRO", "curvas de aprendizaje sólo en LRO", "MLP sólo en LRO y BLQ-75"])
        self.assertIn("bitácora", p["registro_de_recortes"])
        self.assertEqual(len(CFG["fuera_del_contrato"]["descargas_nuevas"]), 3)


if __name__ == "__main__":
    unittest.main()
