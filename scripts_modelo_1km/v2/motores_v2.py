"""Motores de la comparación v2 (``DISENO_AMBIENTAL_V2.md`` §3 y §4, con la Enmienda 1), con recetas fijas y sin
búsqueda.

**Filas de entrenamiento (§4).** Una sola permutación por pliegue, ``numpy.random.default_rng(semilla)
.permutation`` sobre los índices disponibles en orden ascendente del panel, con semilla ``[42, k]`` (réplica 0) o
``[42, k, r]`` (réplicas de ruido r = 1, 2). Cada tope es un prefijo y las filas se ordenan antes de ajustar, de
modo que los topes quedan anidados (GP ⊂ LME ⊂ eje A ⊂ curvas) y todos los motores con el mismo tope ven
exactamente las mismas filas. Con menos filas disponibles que el tope se usan todas y se registra el N efectivo.

**Eje A** (mismos 70/69 predictores, blanco log1p y retransformación primaria):

* LightGBM: receta v1 (``qmd:2187-2197``) con ``deterministic=True``, ``force_col_wise=True`` e hilos fijos.
* XGBoost: receta equivalente (``hist``, ``lossguide``, 127 hojas, η 0,03, 800 rondas, subsample y
  colsample_bytree 0,8, λ 1, ``min_child_weight`` 50, ``max_bin`` 255, ``max_depth`` 0); hilos y semilla fijos.
  ``min_child_weight`` = 50 es la «equivalencia con hessiana 1» de ``min_data_in_leaf`` (Enmienda 1, punto 1.2):
  ``perdidas_v2.parametros_xgboost`` impide usarlo con un objetivo de hessiana no constante.
* Random Forest: receta v1 (``qmd:3146`` y ``3218-3221``): 300 árboles, √p, hojas ≥ 20, NaN nativos,
  ``random_state = 42 + k``.
* MLP: receta v1 (``qmd:3155-3157`` y ``3225-3242``) con **parada temprana agrupada** (Enmienda 1, punto 6). La
  validación se sortea por **conglomerados LOSO-D** (``sortear_conglomerados_validacion``); en LRO y BLQ-75, por
  **grupos completos del protocolo** hasta ~10 % de las filas, estratificado por macrozona
  (``seleccionar_grupos_validacion``). El vecindario de esa fase se recalcula **sin las estaciones de
  validación** (lo hace ``correr_v2``, que entrega la matriz en ``ValidacionMLP``). En BLQ-75 tampoco entrenan en
  esa fase las estaciones a ≤ 10 km de las de validación (**amortiguador interno**, Complemento de la Enmienda 1,
  punto 5; ``ValidacionMLP.fuera`` y ``estaciones_a_radio``). Se entrena época a época (``partial_fit``) sin las
  filas de validación ni las del amortiguador, se mide el R² en log en las de validación y se detiene tras más de
  10 épocas sin mejorar en 1e-4; después la red se **reajusta desde cero**, con la misma semilla, con todas las
  estaciones del pliegue y su vecindario durante la época elegida, que queda registrada. Imputación por mediana y
  escalado con todo el entrenamiento del pliegue (en cada fase, con su vecindario); entradas de prueba acotadas al
  rango del entrenamiento; salida log recortada a sus cuantiles 0,005–0,99.
* Promedio simple de los cuatro, en log, lo arma la consolidación.

**Huber (Enmienda 1, punto 9).** ``particion_honesta`` reparte en dos mitades los conglomerados LOSO-D de las filas
con tope; ``correr_v2`` predice cada mitad con el ``l2_original`` de LightGBM ajustado en la otra (en BLQ-75, sin las
estaciones a ≤ 10 km de la mitad que se predice: Complemento, punto 5) y saca de esos residuos honestos el δ común a
LightGBM y XGBoost (``perdidas_v2.deltas_honestos``).

**Alertas**: LightGBM cuantílico τ = 0,80 sobre log1p (receta v1, ``qmd:3214-3217``, con determinismo e hilos
fijos), vuelta con ``máx(expm1(ẑ), 0)``; se juzga aparte.

**Eje B** (diseño restringido; todo el preprocesamiento —selección por cobertura ≥ 5 %, medianas, indicadoras de
faltante > 5 % y escala— se ajusta con el entrenamiento del pliegue):

* GP: receta v1 (``qmd:3243-3254``): Constante × Matérn(ν = 1,5) + Blanco, 17/16 predictores, 3.000 filas
  (prefijo de la permutación común: deja de estratificar por estación × franja para quedar anidado).
* LME: receta v1 (``qmd:3255-3275``): MixedLM REML, intercepto y pendiente aleatorios por hora local sobre
  ``m2_pm25`` o ``cams_no2``, concentraciones en log1p, 300.000 filas; se registran las advertencias de
  convergencia y el respaldo por mínimos cuadrados.
* GWR, RK e IDW: receta v1 (``qmd:2914-3001`` y ``3089-3124``) por estadísticos suficientes por unidad
  estación × cuatrienio, con todas las filas de entrenamiento y en escala original truncada en 0. A diferencia
  de la v1, el diseño (medianas, indicadoras, media y desviación) se aprende en el pliegue: el diseño es lineal
  en la base ``[1, x·(1−I), I, …]``, así que ``X'X`` del pliegue es ``Tᵀ (B'B) T``, exacto.

**Apilado anidado** (sólo LRO y BLQ-75): predicciones de nivel 2 de pliegues internos agrupados dentro del
entrenamiento del pliegue externo (en BLQ-75 con el amortiguador interno de 10 km); pesos no negativos que suman 1,
por mínimos cuadrados en log resueltos de forma exacta (enumeración de caras del símplex).

**Recortes del presupuesto** (Enmienda 1, punto 12; Complemento, punto 8): ``recetas_de`` lleva el orden de recortes
de la configuración (``recortes_de``) para que ``correr_v2.plan_protocolo`` los aplique sin elección a mano.

Los valores que el contrato no fijaba se leen de ``config_v2.json`` con ``valor_vigente`` (los ratificados por la
Enmienda 1 y, donde siguen pendientes, sus provisionales). Este módulo no lee ni escribe archivos: ``correr_v2`` le
entrega las matrices del pliegue.
"""
from __future__ import annotations

import contextlib
import itertools
import time
import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from _rutas_v2 import valor_vigente
from perdidas_v2 import (
    CUANTIL_FRIEDMAN, FACTOR_HUBER, Variante, parametros_lightgbm, parametros_xgboost, transformar_blanco,
)

MOTORES_EJE_A = ("lightgbm", "xgboost", "random_forest", "mlp")
MOTORES_EJE_B = ("gp", "lme", "gwr", "rk", "idw")
MOTORES_LINEALES = ("gwr", "rk", "idw")
MOTORES_PERDIDAS = ("lightgbm", "xgboost")
VARIANTE_REFERENCIA = "l2_log_smearing"   # cuadrática en log (Enmienda 1, punto 2: antes «l2_log_duan»)
SEMILLA_BASE = 42
PASO_SEMILLA_REPLICA = 1000          # semilla del motor en la réplica r: la de la receta + 1000·r (ruido.valores)
SEMILLA_INTERNOS = 1000              # pliegues internos: default_rng([42, k, 1000]) (apilado_anidado.pliegues_internos)
SEMILLA_PARTICION_HONESTA = 1001     # δ de Huber: default_rng([42, k, 1001]) (perdidas.variantes[2].delta.particion_honesta)
PROTOCOLOS_VALIDACION_POR_GRUPOS = ("LRO", "BLQ-75")    # MLP: validación con grupos completos (Enmienda 1, punto 6)
PROTOCOLOS_AMORTIGUADOR_INTERNO = ("BLQ-75",)            # Complemento, punto 5
ELEMENTOS_RECORTE = ("curvas_de_aprendizaje", "mlp", "semillas", "perdidas")   # Enmienda 1, punto 12
COBERTURA_MIN = 0.05                 # _features.py:564 (columnas_modelo)
FALTANTE_INDICADORA = 0.05           # qmd:2935 y 3191: indicadora si falta más del 5 %

# --- Recetas v1 del eje B que el contrato remite a la v1 (config: recetas_v1_de_referencia) ---------------------
FISICO_LINEAL = {"pm25": ["gcf_pm25", "cams_pm25", "m2_pm25"], "no2": ["gcf_no2", "cams_no2"]}          # qmd:2913
K_VECINOS_GWR = 12                                                                                        # qmd:2914
RIDGE_LINEAL = 1e-6                                                                                       # qmd:2915
GP_PREDICTORES = {                                                                                        # qmd:3165-3168
    "pm25": ["gcf_pm25", "cams_pm25", "m2_pm25", "acag_pm25", "m2_aod_pblh", "obs_vec", "el_t2m", "el_rh", "el_wind",
             "inv_blh", "hora_sin", "hora_cos", "doy_sin", "doy_cos", "lat", "lon", "elev_m"],
    "no2": ["gcf_no2", "cams_no2", "obs_vec", "el_t2m", "el_rh", "el_wind", "inv_blh", "vias_km_km2", "pob_dens",
            "hora_sin", "hora_cos", "doy_sin", "doy_cos", "lat", "lon", "elev_m"],
}
GP_RECETA = {"nu": 1.5, "noise_level": 0.5, "normalize_y": True, "alpha": 1e-6, "bloque_prediccion": 50_000}  # qmd:3163
LME_RECETA = {"grupos": "hora_local", "pendiente_aleatoria": {"pm25": "m2_pm25", "no2": "cams_no2"},       # qmd:3171-3172
              "maxiter": 200, "metodo": "lbfgs", "reml": True}
CALENDARIO = ("hora_sin", "hora_cos", "doy_sin", "doy_cos")


# ---------------------------------------------------------------------------
# Recetas desde la configuración
# ---------------------------------------------------------------------------
def recetas_de(cfg: dict, hilos: int | None = None) -> dict:
    """Recetas efectivas de todos los motores: lo fijado por el contrato, lo que la Enmienda 1 ratificó y, donde sigue
    pendiente, el provisional de ``config_v2.json``. ``hilos`` (≤ ``operacion.hilos_maximos``) reemplaza a los hilos
    de las recetas."""
    m = cfg["motores"]
    a = m["eje_A"]
    tope_hilos = int(cfg["operacion"]["hilos_maximos"])
    h = tope_hilos if hilos is None else int(hilos)
    if not 1 <= h <= tope_hilos:
        raise ValueError(f"hilos fuera de rango: {h} (máximo {tope_hilos})")

    g = a["lightgbm"]
    lgbm = {"params": {"objective": g["objective"], "learning_rate": float(g["learning_rate"]),
                       "num_leaves": int(g["num_leaves"]), "min_data_in_leaf": int(g["min_data_in_leaf"]),
                       "bagging_fraction": float(g["bagging_fraction"]), "bagging_freq": int(g["bagging_freq"]),
                       "feature_fraction": float(g["feature_fraction"]), "lambda_l2": float(g["lambda_l2"]),
                       "deterministic": bool(g["deterministic"]), "force_col_wise": bool(g["force_col_wise"]),
                       "num_threads": h, "seed": int(g["seed"]), "verbose": -1},
            "num_boost_round": int(g["num_boost_round"])}

    x = a["xgboost"]
    variante_col = valor_vigente(x["colsample"]["variante"], "motores.eje_A.xgboost.colsample.variante")
    mcw = x["min_child_weight"]
    xgbr = {"params": {"tree_method": x["tree_method"], "max_leaves": int(x["max_leaves"]),
                       "grow_policy": x["grow_policy"], "eta": float(x["eta"]), "subsample": float(x["subsample"]),
                       variante_col: float(x["colsample"]["valor"]), "lambda": float(x["lambda"]),
                       "min_child_weight": float(valor_vigente(mcw, "motores.eje_A.xgboost.min_child_weight")),
                       "max_depth": int(valor_vigente(x["max_depth"], "motores.eje_A.xgboost.max_depth")),
                       "max_bin": int(valor_vigente(x["max_bin"], "motores.eje_A.xgboost.max_bin")),
                       "nthread": h, "seed": int(valor_vigente(x["seed"], "motores.eje_A.xgboost.seed")),
                       "verbosity": 0},
            "num_boost_round": int(x["num_boost_round"]),
            # Enmienda 1, punto 1.2: el valor es la equivalencia de min_data_in_leaf con hessiana 1; la salvaguarda
            # rige salvo que la configuración declare otra equivalencia.
            "min_child_weight_equivalencia": ("hessiana_1" if not isinstance(mcw, dict) or "hessiana 1"
                                              in str(mcw.get("equivalencia", "hessiana 1")) else str(mcw["equivalencia"])),
            "determinismo": valor_vigente(x["determinismo"], "motores.eje_A.xgboost.determinismo")}
    valor_vigente(x["nthread"], "motores.eje_A.xgboost.nthread")          # que exista el valor

    f = a["random_forest"]
    valor_vigente(f["n_jobs"], "motores.eje_A.random_forest.n_jobs")
    rf = {"params": {"n_estimators": int(f["n_estimators"]), "max_features": f["max_features"],
                     "min_samples_leaf": int(f["min_samples_leaf"]), "n_jobs": h}, "semilla": "42 + k"}

    n = a["mlp"]
    pt = n["parada_temprana"]
    criterio = valor_vigente(pt["criterio"], "motores.eje_A.mlp.parada_temprana.criterio")
    tol = float(criterio.get("tol", 1e-4)) if isinstance(criterio, dict) else 1e-4
    sin_mejora = int(criterio.get("n_iter_no_change", n["n_iter_no_change"])) if isinstance(criterio, dict) else int(n["n_iter_no_change"])
    if sin_mejora != int(n["n_iter_no_change"]):
        raise ValueError("motores.eje_A.mlp: n_iter_no_change difiere entre la receta y el criterio de parada")
    mlp = {"params": {"hidden_layer_sizes": tuple(int(v) for v in n["hidden_layer_sizes"]), "activation": n["activation"],
                      "solver": n["solver"], "alpha": float(n["alpha"]), "batch_size": int(n["batch_size"]),
                      "learning_rate_init": float(n["learning_rate_init"])},
           "max_iter": int(n["max_iter"]), "n_iter_no_change": int(n["n_iter_no_change"]),
           "recorte_salida_log": [float(v) for v in n["recorte_salida_log"]],
           "acotar_entradas": bool(n["acotar_entradas_al_rango_del_entrenamiento"]),
           "fraccion_validacion": float(valor_vigente(pt["fraccion"], "motores.eje_A.mlp.parada_temprana.fraccion")),
           "criterio": criterio,
           "validacion": {"conglomerados": "conglomerados LOSO-D presentes en el entrenamiento: máx(1, round(f·n)), nunca todos",
                          "grupos_en": list(PROTOCOLOS_VALIDACION_POR_GRUPOS),
                          "seleccion_grupos": valor_vigente(pt["seleccion_en_LRO_y_BLQ-75"],
                                                            "motores.eje_A.mlp.parada_temprana.seleccion_en_LRO_y_BLQ-75")
                          if "seleccion_en_LRO_y_BLQ-75" in pt else None,
                          "vecindario": "recalculado sin las estaciones de validación",
                          "reajuste": "desde cero, misma semilla, todas las estaciones del pliegue, épocas elegidas"},
           "tol": tol, "hilos": h}

    prom = valor_vigente(a["promedio_simple"]["escala"], "motores.eje_A.promedio_simple.escala")

    alr = dict(valor_vigente(m["alertas"]["receta"], "motores.alertas.receta"))
    alertas = {"params": {"objective": "quantile", "alpha": float(m["alertas"]["cuantil"]),
                          "learning_rate": float(alr["learning_rate"]), "num_leaves": int(alr["num_leaves"]),
                          "min_data_in_leaf": int(alr["min_data_in_leaf"]), "feature_fraction": float(alr["feature_fraction"]),
                          "deterministic": True, "force_col_wise": True, "num_threads": h, "seed": int(alr["seed"]),
                          "verbose": -1},
               "num_boost_round": int(alr["num_boost_round"]), "filas": alr["filas"]}
    if alr.get("bagging"):
        raise ValueError("la receta de alertas de la v1 no usa bagging (qmd:3214-3217)")

    topes_b = valor_vigente(m["eje_B"]["topes_de_filas"], "motores.eje_B.topes_de_filas")
    ap = m["apilado_anidado"]
    apilado = {"protocolos": list(ap["protocolos"]),
               "bases": list(valor_vigente(ap["bases"], "motores.apilado_anidado.bases")),
               "pliegues_internos": int(valor_vigente(ap["pliegues_internos"], "motores.apilado_anidado.pliegues_internos")["n"]),
               "escala": valor_vigente(ap["escala"], "motores.apilado_anidado.escala")}
    fe = cfg["filas_entrenamiento"]
    valor_vigente(fe["permutacion"]["generador"], "filas_entrenamiento.permutacion.generador")
    valor_vigente(fe["disponibles_menos_que_el_tope"], "filas_entrenamiento.disponibles_menos_que_el_tope")
    return {"lightgbm": lgbm, "xgboost": xgbr, "random_forest": rf, "mlp": mlp, "promedio_escala": prom,
            "alertas": alertas, "gp": {**GP_RECETA, "tope": _tope(topes_b["gp"])},
            "lme": {**LME_RECETA, "tope": _tope(topes_b["lme"])},
            "lineales": {"tope": _tope(topes_b["gwr"]), "k_vecinos": K_VECINOS_GWR, "ridge": RIDGE_LINEAL},
            "apilado": apilado, "huber": receta_huber(cfg), "N_comun": int(fe["N_comun_eje_A"]),
            "curvas": {k: [_tope(v) for v in fe["curvas_de_aprendizaje"][k]] for k in ("lightgbm", "xgboost", "random_forest")},
            "protocolos_curvas": list(fe["curvas_de_aprendizaje"]["protocolos"]),
            "amortiguador_interno": amortiguador_interno_de(cfg), "recortes": recortes_de(cfg), "hilos": h}


def amortiguador_interno_de(cfg: dict) -> dict:
    """Amortiguador de las particiones internas de BLQ-75 (Complemento de la Enmienda 1, punto 5;
    ``protocolos.BLQ-75.exclusion_adicional.particiones_internas``): radio (km, haversine), comparación «<=» y dónde
    se aplica. Se mide desde las estaciones del conjunto interno de validación que tienen filas en el entrenamiento
    del pliegue (las que validan; ``correr_v2.amortiguador_interno``)."""
    ex = cfg["protocolos"]["BLQ-75"]["exclusion_adicional"]
    pi = ex.get("particiones_internas") if isinstance(ex, dict) else None
    if not isinstance(pi, dict) or "radio_km" not in pi:
        raise ValueError("falta protocolos.BLQ-75.exclusion_adicional.particiones_internas (Complemento, punto 5)")
    if pi.get("comparacion", "<=") != "<=":
        raise ValueError("el amortiguador interno de BLQ-75 se mide con <=, como el externo")
    return {"protocolos": list(PROTOCOLOS_AMORTIGUADOR_INTERNO), "radio_km": float(pi["radio_km"]), "comparacion": "<=",
            "distancia": "haversine",
            "medida_desde": ("cualquier estación del conjunto interno de validación con filas en el entrenamiento del "
                             "pliegue (correr_v2.amortiguador_interno)"),
            "se_aplica_en": list(pi.get("se_aplica_en", []))}


def recortes_de(cfg: dict) -> list[dict]:
    """Orden de recortes del presupuesto (``presupuesto.orden_de_recortes``; Enmienda 1, punto 12, con el recorte 4
    del Complemento, punto 8): por orden, el elemento que se recorta y los protocolos donde se conserva. Exige los
    cuatro elementos de la enmienda, en órdenes consecutivos desde 1."""
    orden = sorted(cfg["presupuesto"]["orden_de_recortes"], key=lambda x: int(x["orden"]))
    out = [{"orden": int(x["orden"]), "elemento": str(x["elemento"]), "recorte": str(x["recorte"]),
            "se_conserva_en": list(x["se_conserva_en"])} for x in orden]
    if [x["orden"] for x in out] != list(range(1, len(out) + 1)):
        raise ValueError(f"presupuesto.orden_de_recortes: órdenes no consecutivos desde 1: {[x['orden'] for x in out]}")
    if sorted(x["elemento"] for x in out) != sorted(ELEMENTOS_RECORTE):
        raise ValueError(f"presupuesto.orden_de_recortes: los elementos deben ser {ELEMENTOS_RECORTE}: "
                         f"{[x['elemento'] for x in out]}")
    return out


def receta_huber(cfg: dict) -> dict:
    """Regla del δ de Huber (Enmienda 1, punto 9) tal como la fija la configuración: factor sobre el MAD normalizado
    de residuos honestos del ``l2_original`` de LightGBM, común a los dos motores, y la sensibilidad de Friedman."""
    v = next(x for x in cfg["perdidas"]["variantes"] if x["id"] == "huber")
    d = v["delta"]
    if float(d["factor"]) != FACTOR_HUBER:
        raise ValueError(f"perdidas.variantes[huber].delta.factor = {d['factor']} no es {FACTOR_HUBER}")
    ajuste = valor_vigente(d["ajuste_cuadratico"], "perdidas.variantes[2].delta.ajuste_cuadratico")
    if isinstance(ajuste, dict) and ajuste.get("motor", "lightgbm") != "lightgbm":
        raise ValueError("el δ común de Huber sale del l2_original de LightGBM (Enmienda 1, punto 9)")
    return {"factor": FACTOR_HUBER, "mad": valor_vigente(d["mad"], "perdidas.variantes[2].delta.mad"),
            "ajuste_cuadratico": ajuste, "comun_a_los_dos_motores": bool(d.get("comun_a_los_dos_motores", True)),
            "particion_honesta": valor_vigente(d["particion_honesta"], "perdidas.variantes[2].delta.particion_honesta")
            if "particion_honesta" in d else None,
            "sensibilidad": {"regla": "friedman", "cuantil_de_abs_r": CUANTIL_FRIEDMAN},
            "semilla_particion": [SEMILLA_BASE, "k", SEMILLA_PARTICION_HONESTA]}


def _tope(v):
    """Tope de filas: entero o None («todas»)."""
    return None if v in ("todas", None) else int(v)


# ---------------------------------------------------------------------------
# Filas: permutación común y topes anidados
# ---------------------------------------------------------------------------
def semilla_permutacion(k: int, replica: int = 0) -> list[int]:
    """``[42, k]`` en la réplica 0 (§4); ``[42, k, r]`` en las réplicas de ruido (``ruido.valores``, ratificado)."""
    return [SEMILLA_BASE, int(k)] + ([int(replica)] if replica else [])


def semilla_motor(base: int, replica: int = 0) -> int:
    return int(base) + PASO_SEMILLA_REPLICA * int(replica)


def permutacion(disponibles: np.ndarray, semilla) -> np.ndarray:
    """Índices disponibles (ordenados ascendentemente) en el orden de la permutación común del pliegue."""
    d = np.asarray(disponibles, dtype="int64")
    if len(d) > 1 and not (np.diff(d) > 0).all():
        raise ValueError("los índices disponibles deben venir en orden ascendente y sin repetir")
    return d[np.random.default_rng(semilla).permutation(len(d))]


def filas_tope(orden: np.ndarray, tope: int | None, mascara=None) -> np.ndarray:
    """Las primeras ``tope`` filas de la permutación (todas si es None), ordenadas. ``mascara`` (booleana sobre
    las filas del panel) filtra la permutación antes de cortar: las variantes de calidad comparten la misma."""
    o = np.asarray(orden, dtype="int64")
    if mascara is not None:
        o = o[np.asarray(mascara, dtype=bool)[o]]
    if tope is not None:
        o = o[:int(tope)]
    return np.sort(o)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def limitar_hilos(n: int | None):
    if not n:
        return contextlib.nullcontext()
    try:
        from threadpoolctl import threadpool_limits
    except ImportError:
        return contextlib.nullcontext()
    return threadpool_limits(limits=int(n))


def r2_simple(y, p) -> float:
    y, p = np.asarray(y, dtype="float64"), np.asarray(p, dtype="float64")
    sst = float(np.sum((y - y.mean()) ** 2))
    return float(1.0 - np.sum((y - p) ** 2) / sst) if sst > 0 else float("nan")


@dataclass
class Resultado:
    """Salida de un motor sobre las filas de prueba: ``salida`` en su escala («log» u «original»)."""

    salida: np.ndarray
    escala: str
    info: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Eje A, pérdidas y alertas
# ---------------------------------------------------------------------------
class ModeloLightGBM:
    """LightGBM nativo (``lgb.train``) sobre el blanco de la variante."""

    def __init__(self, receta: dict, variante: Variante, semilla: int, num_boost_round: int | None = None,
                 objetivo_de_la_receta: bool = False):
        self.receta, self.variante = receta, variante
        base = {**receta["params"], "seed": int(semilla)}
        # ``objetivo_de_la_receta``: el objetivo ya viene en la receta (alertas: cuantílico τ = 0,80 sobre log1p)
        self.params = base if objetivo_de_la_receta else parametros_lightgbm(base, variante)
        self.rondas = int(num_boost_round or receta["num_boost_round"])
        self.escala = variante.escala
        self.modelo = None
        self.info: dict = {}

    def ajustar(self, X, y, estaciones=None) -> "ModeloLightGBM":
        import lightgbm as lgb
        yb = transformar_blanco(y, self.variante)
        t0 = time.perf_counter()
        self.modelo = lgb.train(self.params, lgb.Dataset(X, label=yb, free_raw_data=True), num_boost_round=self.rondas)
        self.info.update({"params": {k: v for k, v in self.params.items() if k != "verbose"}, "rondas": self.rondas,
                          "segundos_ajuste": round(time.perf_counter() - t0, 3), "filas": int(len(yb))})
        return self

    def predecir(self, X) -> np.ndarray:
        return self.modelo.predict(X, num_threads=int(self.params["num_threads"])).astype("float64")


class ModeloXGBoost:
    """XGBoost ``hist`` sobre el blanco de la variante (Huber con el objetivo propio de ``perdidas_v2``). Con la
    receta v2, ``min_child_weight`` es la «equivalencia con hessiana 1» y no se combina con un objetivo de hessiana
    no constante (Enmienda 1, punto 1.2)."""

    def __init__(self, receta: dict, variante: Variante, semilla: int, num_boost_round: int | None = None):
        self.receta, self.variante, self.semilla = receta, variante, int(semilla)
        self.rondas = int(num_boost_round or receta["num_boost_round"])
        self.escala = variante.escala
        self.modelo = None
        self.info: dict = {}

    def ajustar(self, X, y, estaciones=None) -> "ModeloXGBoost":
        import xgboost as xgb
        yb = transformar_blanco(y, self.variante)
        exigir = self.receta.get("min_child_weight_equivalencia", "hessiana_1") == "hessiana_1"
        params, obj = parametros_xgboost({**self.receta["params"], "seed": self.semilla}, self.variante, yb,
                                         exigir_hessiana_constante=exigir)
        t0 = time.perf_counter()
        dtrain = xgb.QuantileDMatrix(X, label=yb, max_bin=int(params["max_bin"]), nthread=int(params["nthread"]))
        self.modelo = xgb.train(params, dtrain, num_boost_round=self.rondas, obj=obj)
        self.info.update({"params": {k: v for k, v in params.items() if k != "verbosity"}, "rondas": self.rondas,
                          "objetivo_propio": None if obj is None else obj.__name__,
                          "min_child_weight_equivalencia": self.receta.get("min_child_weight_equivalencia"),
                          "segundos_ajuste": round(time.perf_counter() - t0, 3), "filas": int(len(yb))})
        return self

    def predecir(self, X) -> np.ndarray:
        return np.asarray(self.modelo.inplace_predict(np.asarray(X, dtype="float32")), dtype="float64")


class ModeloRF:
    """Random Forest de scikit-learn sobre log1p(y), NaN nativos (receta v1)."""

    escala = "log"

    def __init__(self, receta: dict, semilla: int):
        self.receta, self.semilla = receta, int(semilla)
        self.modelo = None
        self.info: dict = {}

    def ajustar(self, X, y, estaciones=None) -> "ModeloRF":
        from sklearn.ensemble import RandomForestRegressor
        ylog = transformar_blanco(y, Variante(VARIANTE_REFERENCIA))
        t0 = time.perf_counter()
        self.modelo = RandomForestRegressor(**self.receta["params"], random_state=self.semilla).fit(X, ylog)
        self.info.update({"params": dict(self.receta["params"]), "random_state": self.semilla,
                          "segundos_ajuste": round(time.perf_counter() - t0, 3), "filas": int(len(ylog))})
        return self

    def predecir(self, X) -> np.ndarray:
        """Predicción determinista bit a bit. Con ``n_jobs > 1``, scikit-learn suma los árboles en hilos en el orden
        en que terminan, y el resultado cambia en el último bit entre llamadas (los árboles sí son idénticos). Aquí
        cada trozo de filas suma los árboles en su orden (``n_jobs=1``) y los trozos corren en paralelo en hilos
        (la predicción de un árbol libera el GIL)."""
        from joblib import Parallel, delayed
        X = np.asarray(X, dtype="float32")
        n = len(X)
        if n == 0:
            return np.zeros(0)
        h = int(self.receta["params"]["n_jobs"])
        trozos = np.array_split(np.arange(n), max(1, min(4 * h, -(-n // 20_000))))
        self.modelo.set_params(n_jobs=1)
        try:
            partes = Parallel(n_jobs=h, prefer="threads")(delayed(self.modelo.predict)(X[t]) for t in trozos)
        finally:
            self.modelo.set_params(n_jobs=h)
        return np.concatenate(partes).astype("float64")


# ---------------------------------------------------------------------------
# MLP: validación agrupada de la parada temprana (Enmienda 1, punto 6)
# ---------------------------------------------------------------------------
@dataclass
class ValidacionMLP:
    """Validación de la parada temprana de una MLP.

    ``filas``: máscara booleana sobre las filas de entrenamiento (las de validación). ``X``: las mismas filas de
    entrenamiento, en el mismo orden, con el vecindario recalculado **sin las estaciones de validación** (``None``
    reutiliza la matriz del ajuste, sólo para usos aislados y pruebas). ``fuera``: máscara de las filas que tampoco
    entrenan en la fase de validación (en BLQ-75, las de las estaciones a ≤ 10 km de las de validación: el
    amortiguador interno del Complemento, punto 5); ``None`` = ninguna. ``registro``: unidad del sorteo, unidades
    elegidas, estaciones, macrozonas, amortiguador, fracción de filas y huella del vecindario."""

    filas: np.ndarray
    X: np.ndarray | None = None
    registro: dict = field(default_factory=dict)
    fuera: np.ndarray | None = None

    def entrenan(self) -> np.ndarray:
        """Filas que entrenan en la fase de validación: ni de validación ni del amortiguador."""
        f = np.asarray(self.filas, dtype=bool)
        return ~f if self.fuera is None else ~f & ~np.asarray(self.fuera, dtype=bool)

    @property
    def agrupada(self) -> bool:
        f = np.asarray(self.filas, dtype=bool)
        return bool(f.any() and self.entrenan().any())


def estaciones_a_radio(D: np.ndarray, internas, fuera_de_juego, radio_km: float) -> np.ndarray:
    """Máscara (por estación) de las estaciones a ``<= radio_km`` de alguna estación de ``internas`` (índices), que
    no son de ``internas`` ni de ``fuera_de_juego`` (índices ya excluidos). ``D``: distancias haversine entre las
    estaciones (km). Es el amortiguador de una partición interna de BLQ-75 (Complemento, punto 5)."""
    D = np.asarray(D, dtype="float64")
    internas = np.asarray(internas, dtype="int64")
    out = np.zeros(D.shape[0], dtype=bool)
    if len(internas) == 0:
        return out
    out = (D[internas] <= float(radio_km)).any(axis=0)
    out[internas] = False
    out[np.asarray(fuera_de_juego, dtype="int64")] = False
    return out


def sortear_conglomerados_validacion(conglomerados_presentes, semilla, fraccion: float) -> list[str]:
    """Conglomerados LOSO-D de validación (LOSO-D, LBO-10 y LPO): ``máx(1, round(fraccion·n))`` de los n presentes
    en el entrenamiento, nunca todos, sorteados con ``default_rng(semilla)`` sobre las etiquetas ordenadas."""
    u = np.array(sorted({str(x) for x in conglomerados_presentes}))
    n_val = max(1, int(round(float(fraccion) * len(u))))
    if len(u) < 2 or n_val >= len(u):
        return []
    return sorted(str(x) for x in np.random.default_rng(semilla).choice(u, n_val, replace=False))


def seleccionar_grupos_validacion(grupo_de_fila, macrozona_de_fila, semilla, fraccion: float) -> tuple[list[str], dict]:
    """Grupos completos del protocolo para validar la MLP en LRO y BLQ-75 (ratificado por el Complemento, punto 4.1:
    ``motores.eje_A.mlp.parada_temprana.seleccion_en_LRO_y_BLQ-75``): (1) se permutan con ``default_rng(semilla)``
    las etiquetas ordenadas de los grupos presentes en el entrenamiento; (2) se recorren en ese orden y un grupo
    entra si su macrozona (la de la mayoría de sus filas) todavía no aporta ninguno y si con él las filas de
    validación no pasan de ``fraccion`` de las filas de entrenamiento; (3) si ninguno cabe, entra el grupo con menos
    filas (desempate: etiqueta); nunca entran todos. Devuelve los grupos y su registro."""
    g = np.asarray(grupo_de_fila).astype(str)
    mz = np.asarray(macrozona_de_fila, dtype="int64")
    total = len(g)
    tope = float(fraccion) * total
    etiquetas, inv, filas = np.unique(g, return_inverse=True, return_counts=True)
    inv = inv.ravel()
    mayoria = {}
    for i, e in enumerate(etiquetas):
        valores, cuentas = np.unique(mz[inv == i], return_counts=True)
        mayoria[str(e)] = int(valores[int(np.argmax(cuentas))])           # empate: la macrozona de código menor
    registro = {"unidad": "grupos completos del protocolo", "grupos_presentes": int(len(etiquetas)),
                "filas_entrenamiento": int(total), "tope_filas": tope, "estratificado_por": "macrozona"}
    if len(etiquetas) < 2:
        return [], {**registro, "motivo": "menos de dos grupos en el entrenamiento: sin validación agrupada"}
    elegidos, usadas, n_val = [], set(), 0
    for i in np.random.default_rng(semilla).permutation(len(etiquetas)):
        e, n = str(etiquetas[i]), int(filas[i])
        if mayoria[e] in usadas or n_val + n > tope or len(elegidos) + 1 >= len(etiquetas):
            continue
        elegidos.append(e)
        usadas.add(mayoria[e])
        n_val += n
    respaldo = not elegidos
    if respaldo:
        i = min(range(len(etiquetas)), key=lambda j: (int(filas[j]), str(etiquetas[j])))
        elegidos, n_val = [str(etiquetas[i])], int(filas[i])
    elegidos = sorted(elegidos)
    registro.update({"grupos": elegidos, "macrozonas": {e: mayoria[e] for e in elegidos}, "filas_validacion": int(n_val),
                     "fraccion_filas": n_val / total if total else float("nan"), "respaldo_grupo_con_menos_filas": respaldo})
    return elegidos, registro


class ModeloMLP:
    """MLP de la v1 con parada temprana agrupada (Enmienda 1, punto 6): fase de validación con el vecindario sin las
    estaciones de validación y reajuste desde cero con todas las estaciones durante la época elegida."""

    escala = "log"

    def __init__(self, receta: dict, semilla: int):
        self.receta, self.semilla = receta, int(semilla)
        self.info: dict = {}

    def _red(self):
        from sklearn.neural_network import MLPRegressor
        rc = self.receta
        return MLPRegressor(**rc["params"], max_iter=1, shuffle=True, early_stopping=False, tol=rc["tol"],
                            n_iter_no_change=rc["n_iter_no_change"], random_state=np.random.RandomState(self.semilla))

    @staticmethod
    def _escalar(X):
        from sklearn.impute import SimpleImputer
        from sklearn.preprocessing import StandardScaler
        imp = SimpleImputer(strategy="median", keep_empty_features=True).fit(X)
        Xi = imp.transform(X)
        esc = StandardScaler().fit(Xi)
        return imp, esc, esc.transform(Xi).astype("float32")

    def ajustar(self, X, y, estaciones=None, validacion: ValidacionMLP | None = None) -> "ModeloMLP":
        from sklearn.metrics import r2_score
        if validacion is None:
            raise ValueError("la MLP necesita su validación agrupada (ValidacionMLP; Enmienda 1, punto 6)")
        rc = self.receta
        X = np.asarray(X, dtype="float32")
        ylog = transformar_blanco(y, Variante(VARIANTE_REFERENCIA))
        val = np.asarray(validacion.filas, dtype=bool)
        if val.shape != (len(ylog),):
            raise ValueError("la máscara de validación debe tener una entrada por fila de entrenamiento")
        if validacion.fuera is not None and np.asarray(validacion.fuera).shape != (len(ylog),):
            raise ValueError("la máscara del amortiguador debe tener una entrada por fila de entrenamiento")
        entrenan = validacion.entrenan()
        t0 = time.perf_counter()
        self.vacias = np.isnan(X).all(axis=0)                     # sin dato en el entrenamiento (qmd:3230-3232)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            self.bajo, self.alto = np.nanmin(X, axis=0), np.nanmax(X, axis=0)
        self.lo, self.hi = (float(v) for v in np.quantile(ylog, rc["recorte_salida_log"]))
        agrupada = validacion.agrupada
        mejor, mejor_epoca, epocas_validacion, motivo = -np.inf, 0, 0, None
        with limitar_hilos(rc["hilos"]), warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Got `batch_size` less than 1 or larger than sample size")
            if agrupada:
                Xv = X if validacion.X is None else np.asarray(validacion.X, dtype="float32")
                if Xv.shape != X.shape:
                    raise ValueError("la matriz de validación no tiene la forma de la de entrenamiento")
                _, _, Xs_v = self._escalar(Xv)                          # imputación y escala: todo el entrenamiento
                red_v, sin_mejora = self._red(), 0
                for epoca in range(1, rc["max_iter"] + 1):
                    red_v.partial_fit(Xs_v[entrenan], ylog[entrenan])  # sin validación ni amortiguador
                    s = float(r2_score(ylog[val], red_v.predict(Xs_v[val])))
                    if not np.isfinite(s):
                        s = -np.inf
                    sin_mejora = sin_mejora + 1 if s < mejor + rc["tol"] else 0      # MLPRegressor (_update_no_improvement_count)
                    if s > mejor:
                        mejor, mejor_epoca = s, epoca
                    epocas_validacion = epoca
                    if sin_mejora > rc["n_iter_no_change"]:
                        break
                del red_v, Xs_v
                epocas = mejor_epoca if mejor_epoca >= 1 else epocas_validacion
                if mejor_epoca < 1:
                    motivo = "el R² de validación nunca fue finito: se reajusta con las épocas recorridas"
            else:
                epocas = int(rc["max_iter"])
                motivo = validacion.registro.get("motivo", "sin unidades de validación: sin parada temprana")
            # Reajuste desde cero, con la misma semilla y todas las estaciones del pliegue (y su vecindario).
            self.imp, self.esc, Xs = self._escalar(X)
            red = self._red()
            for _ in range(int(epocas)):
                red.partial_fit(Xs, ylog)
        self.modelo = red
        self.info.update({"params": {k: (list(v) if isinstance(v, tuple) else v) for k, v in rc["params"].items()},
                          "random_state": self.semilla, "validacion_agrupada": agrupada,
                          "validacion": validacion.registro, "filas_validacion": int(val.sum()),
                          "filas_amortiguador": 0 if validacion.fuera is None else int(np.asarray(validacion.fuera).sum()),
                          "filas_entrenamiento_validacion": int(entrenan.sum()),
                          "vecindario_validacion_recalculado": validacion.X is not None,
                          "epocas_validacion": int(epocas_validacion), "mejor_epoca": int(mejor_epoca),
                          "epocas_reajuste": int(epocas), "motivo": motivo,
                          "mejor_r2_log_validacion": None if not np.isfinite(mejor) else float(mejor),
                          "reajuste": "desde cero, con la misma semilla y todas las estaciones del pliegue",
                          "recorte_salida_log": [self.lo, self.hi], "columnas_vacias": int(self.vacias.sum()),
                          "lote_recortado": int(len(ylog)) < int(rc["params"]["batch_size"]),
                          "segundos_ajuste": round(time.perf_counter() - t0, 3), "filas": int(len(ylog))})
        return self

    def predecir(self, X) -> np.ndarray:
        X = np.array(X, dtype="float32", copy=True)
        if self.vacias.any():
            X[:, self.vacias] = np.nan
        if self.receta["acotar_entradas"]:
            X = np.where(np.isnan(X), np.nan, np.clip(X, np.nan_to_num(self.bajo, nan=-np.inf),
                                                       np.nan_to_num(self.alto, nan=np.inf)))
        with limitar_hilos(self.receta["hilos"]):
            Xs = self.esc.transform(self.imp.transform(X)).astype("float32")
            return np.clip(self.modelo.predict(Xs), self.lo, self.hi).astype("float64")


def validacion_por_unidades(unidad_de_fila, semilla, fraccion: float, X_validacion=None) -> ValidacionMLP:
    """Validación por unidades sorteadas (``sortear_conglomerados_validacion``) para un uso aislado de la MLP; en la
    comparación, ``correr_v2`` arma la validación con el vecindario recalculado sin las estaciones de validación."""
    u = np.asarray(unidad_de_fila).astype(str)
    elegidas = sortear_conglomerados_validacion(np.unique(u), semilla, fraccion)
    filas = np.isin(u, elegidas)
    return ValidacionMLP(filas=filas, X=X_validacion,
                         registro={"unidad": "unidades dadas", "unidades": elegidas, "filas_validacion": int(filas.sum())})


def crear_modelo(motor: str, recetas: dict, variante: Variante, semilla_recipe: int, replica: int = 0, k: int = 0):
    """Modelo del eje A, de las pérdidas o de alertas, con la semilla de la réplica."""
    if motor == "lightgbm":
        return ModeloLightGBM(recetas["lightgbm"], variante, semilla_motor(recetas["lightgbm"]["params"]["seed"], replica))
    if motor == "xgboost":
        return ModeloXGBoost(recetas["xgboost"], variante, semilla_motor(recetas["xgboost"]["params"]["seed"], replica))
    if variante.nombre != VARIANTE_REFERENCIA:
        raise ValueError(f"{motor} sólo usa la pérdida de referencia (las de §6 son de LightGBM y XGBoost)")
    if motor == "random_forest":
        return ModeloRF(recetas["random_forest"], semilla_motor(SEMILLA_BASE + int(k), replica))
    if motor == "mlp":
        return ModeloMLP(recetas["mlp"], semilla_motor(SEMILLA_BASE + int(k), replica))
    if motor == "alertas":
        r = recetas["alertas"]
        return ModeloLightGBM({"params": r["params"], "num_boost_round": r["num_boost_round"]},
                              Variante(VARIANTE_REFERENCIA), semilla_motor(r["params"]["seed"], replica),
                              objetivo_de_la_receta=True)
    raise ValueError(f"motor desconocido: {motor}")


def salida_alertas(z) -> np.ndarray:
    """Un cuantil conmuta con la transformación monótona: ``máx(expm1(ẑ), 0)`` sin corrección (qmd:3430-3432)."""
    return np.clip(np.expm1(np.asarray(z, dtype="float64")), 0.0, None).astype("float32")


def particion_honesta(conglomerado_de_fila, k: int) -> tuple[np.ndarray, dict]:
    """Partición agrupada en dos de las filas con tope de un pliegue, para los residuos honestos del δ de Huber
    (Enmienda 1, punto 9; ratificada por el Complemento, punto 4.2: ``perdidas.variantes[2].delta.particion_honesta``):
    las etiquetas ordenadas de los conglomerados LOSO-D presentes, permutadas con ``default_rng([42, k, 1001])`` y
    repartidas en turnos. Devuelve la máscara de la mitad 1 (la mitad 0 es el resto) y su definición."""
    c = np.asarray(conglomerado_de_fila).astype(str)
    etiquetas = sorted({str(x) for x in np.unique(c)})
    if len(etiquetas) < 2:
        raise ValueError("la partición honesta del δ de Huber necesita al menos dos conglomerados en el entrenamiento")
    semilla = [SEMILLA_BASE, int(k), SEMILLA_PARTICION_HONESTA]
    orden = np.random.default_rng(semilla).permutation(len(etiquetas))
    mitades: list[list[str]] = [[], []]
    for pos, i in enumerate(orden):
        mitades[pos % 2].append(etiquetas[i])
    mitades = [sorted(m) for m in mitades]
    en_1 = np.isin(c, mitades[1])
    return en_1, {"semilla": semilla, "conglomerados": mitades, "filas": [int((~en_1).sum()), int(en_1.sum())]}


# ---------------------------------------------------------------------------
# Eje B: diseño lineal dentro del pliegue (LME) y GP
# ---------------------------------------------------------------------------
def columnas_base_lineal(pol: str, en_log: bool) -> list[str]:
    """Columnas del diseño de la v1 (``qmd:2925-2956`` y ``3174-3204``), antes de indicadoras y escala."""
    return [*FISICO_LINEAL[pol], *(["acag_pm25"] if pol == "pm25" else []), "obs_vec", "inv_blh", "t2m", "wind"]


def base_lineal(d: pd.DataFrame, pol: str, en_log: bool) -> pd.DataFrame:
    """Réplica de la parte determinista de ``_diseno_par``/``diseno_lineal``: concentraciones (en log1p si
    ``en_log``), 1/BLH, temperatura (ERA5-Land con respaldo MERRA-2) y viento (con respaldo MERRA-2)."""
    out = pd.DataFrame(index=d.index)
    for c in [*FISICO_LINEAL[pol], *(["acag_pm25"] if pol == "pm25" else []), "obs_vec"]:
        if c in d.columns:
            v = d[c].astype("float64")
            out[c] = np.log1p(v.clip(lower=0)) if en_log else v
    if "inv_blh" in d.columns:
        out["inv_blh"] = d["inv_blh"].astype("float64")
    if "el_t2m" in d.columns:
        out["t2m"] = d["el_t2m"].astype("float64")
        if "m2_t2m" in d.columns:
            out["t2m"] = out["t2m"].fillna(d["m2_t2m"].astype("float64"))
    if "el_wind" in d.columns:
        out["wind"] = d["el_wind"].astype("float64")
        if {"m2_u10m", "m2_v10m"}.issubset(d.columns):
            out["wind"] = out["wind"].fillna(np.sqrt(d["m2_u10m"].astype("float64") ** 2
                                                     + d["m2_v10m"].astype("float64") ** 2))
    return out


class DisenoLineal:
    """Diseño del LME con todo el preprocesamiento aprendido en el entrenamiento del pliegue: selección por
    cobertura (≥ 5 %), medianas, indicadoras (> 5 % faltante), columnas con varianza y estandarización (media y
    desviación con ddof = 1, como pandas en la v1, ``qmd:3202-3203``)."""

    def __init__(self, pol: str, en_log: bool = True):
        self.pol, self.en_log = pol, en_log

    def ajustar(self, dtr: pd.DataFrame) -> "DisenoLineal":
        a = base_lineal(dtr, self.pol, self.en_log)
        self.descartadas = [c for c in a.columns if a[c].notna().mean() < COBERTURA_MIN]
        a = a.drop(columns=self.descartadas)
        self.medianas, self.indicadoras = {}, []
        for c in list(a.columns):
            self.medianas[c] = float(a[c].median()) if a[c].notna().any() else 0.0
            if a[c].isna().mean() > FALTANTE_INDICADORA:
                self.indicadoras.append(c)
        A = self._completar(a, dtr)
        self.columnas = [c for c in A.columns if A[c].std() > 0]
        self.mu, self.sd = A[self.columnas].mean(), A[self.columnas].std()
        return self

    def _completar(self, a: pd.DataFrame, d: pd.DataFrame) -> pd.DataFrame:
        a = a.copy()
        for c in self.indicadoras:
            a[f"{c}_falta"] = a[c].isna().astype("float64")
        for c in self.medianas:
            a[c] = a[c].fillna(self.medianas[c])
        for c in CALENDARIO:
            a[c] = d[c].astype("float64")
        return a

    def transformar(self, d: pd.DataFrame) -> np.ndarray:
        a = base_lineal(d, self.pol, self.en_log).drop(columns=self.descartadas, errors="ignore")
        A = self._completar(a, d)
        return ((A[self.columnas] - self.mu) / self.sd).to_numpy("float64")

    def resumen(self) -> dict:
        return {"descartadas_por_cobertura": self.descartadas, "indicadoras": self.indicadoras,
                "columnas": self.columnas, "medianas": self.medianas}


class ModeloLME:
    """MixedLM de la v1 (``qmd:3255-3275``) con el diseño aprendido en el pliegue."""

    escala = "log"

    def __init__(self, receta: dict, pol: str, feats: list[str]):
        self.receta, self.pol, self.feats = receta, pol, list(feats)
        self.info: dict = {}

    def ajustar(self, X, y, estaciones=None) -> "ModeloLME":
        import statsmodels.api as sm
        t0 = time.perf_counter()
        dtr = pd.DataFrame(np.asarray(X, dtype="float64"), columns=self.feats)
        ylog = transformar_blanco(y, Variante(VARIANTE_REFERENCIA))
        self.diseno = DisenoLineal(self.pol, en_log=True).ajustar(dtr)
        A = np.column_stack([np.ones(len(dtr)), self.diseno.transformar(dtr)])
        pend = self.receta["pendiente_aleatoria"][self.pol]
        self.j = 1 + self.diseno.columnas.index(pend) if pend in self.diseno.columnas else None
        h = dtr[self.receta["grupos"]].to_numpy().astype(int)
        re = np.column_stack([np.ones(len(A)), A[:, self.j]]) if self.j is not None else np.ones((len(A), 1))
        self.respaldo, avisos = False, []
        try:
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                fit = sm.MixedLM(ylog, A, groups=h, exog_re=re).fit(method=self.receta["metodo"],
                                                                     maxiter=self.receta["maxiter"],
                                                                     reml=self.receta["reml"])
            avisos = sorted({f"{type(x.message).__name__}: {str(x.message)[:160]}" for x in w})
            self.fe = np.asarray(fit.fe_params, dtype="float64")
            self.efectos = {int(g): np.asarray(v, dtype="float64") for g, v in fit.random_effects.items()}
            convergio = bool(getattr(fit, "converged", True))
        except Exception as exc:                                     # MixedLM no ajustó: parte fija por MCO
            self.fe = np.linalg.lstsq(A, ylog, rcond=None)[0]
            self.efectos, self.respaldo, convergio = {}, True, False
            avisos.append(f"{type(exc).__name__}: {str(exc)[:160]}")
        self.lo, self.hi = float(ylog.min()), float(ylog.max())
        self.info.update({"diseno": self.diseno.resumen(), "respaldo_mco": self.respaldo, "convergio": convergio,
                          "advertencias": avisos, "pendiente_aleatoria": pend if self.j is not None else None,
                          "segundos_ajuste": round(time.perf_counter() - t0, 3), "filas": int(len(ylog))})
        return self

    def predecir(self, X) -> np.ndarray:
        d = pd.DataFrame(np.asarray(X, dtype="float64"), columns=self.feats)
        B = np.column_stack([np.ones(len(d)), self.diseno.transformar(d)])
        z = B @ self.fe
        h = d[self.receta["grupos"]].to_numpy().astype(int)
        for g, v in self.efectos.items():                          # el efecto de la hora se conoce al predecir
            s = h == g
            z[s] += v[0] + (v[1] * B[s, self.j] if self.j is not None and len(v) > 1 else 0.0)
        return np.clip(z, self.lo, self.hi)


class ModeloGP:
    """Proceso gaussiano de la v1 (``qmd:3243-3254``) con selección por cobertura en el pliegue."""

    escala = "log"

    def __init__(self, receta: dict, pol: str, feats: list[str], semilla: int, hilos: int):
        self.receta, self.pol, self.feats, self.semilla, self.hilos = receta, pol, list(feats), int(semilla), int(hilos)
        self.info: dict = {}

    def ajustar(self, X, y, estaciones=None) -> "ModeloGP":
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
        from sklearn.impute import SimpleImputer
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
        t0 = time.perf_counter()
        X = np.asarray(X, dtype="float64")
        ylog = transformar_blanco(y, Variante(VARIANTE_REFERENCIA))
        candidatas = [self.feats.index(c) for c in GP_PREDICTORES[self.pol] if c in self.feats]
        self.cols = [i for i in candidatas if np.isfinite(X[:, i]).mean() >= COBERTURA_MIN]
        rc = self.receta
        nucleo = (ConstantKernel(1.0, (1e-3, 1e3)) * Matern(length_scale=1.0, length_scale_bounds=(1e-1, 1e2), nu=rc["nu"])
                  + WhiteKernel(noise_level=rc["noise_level"], noise_level_bounds=(1e-4, 1e1)))
        with limitar_hilos(self.hilos):
            self.modelo = Pipeline([("imp", SimpleImputer(strategy="median", keep_empty_features=True)),
                                    ("esc", StandardScaler()),
                                    ("gpr", GaussianProcessRegressor(kernel=nucleo, normalize_y=rc["normalize_y"],
                                                                     alpha=rc["alpha"], n_restarts_optimizer=0,
                                                                     random_state=self.semilla))]).fit(X[:, self.cols], ylog)
        self.info.update({"predictores": [self.feats[i] for i in self.cols],
                          "descartados_por_cobertura": [self.feats[i] for i in candidatas if i not in self.cols],
                          "nucleo_ajustado": str(self.modelo.named_steps["gpr"].kernel_), "random_state": self.semilla,
                          "segundos_ajuste": round(time.perf_counter() - t0, 3), "filas": int(len(ylog))})
        return self

    def predecir(self, X) -> np.ndarray:
        X = np.asarray(X, dtype="float64")
        b = int(self.receta["bloque_prediccion"])
        with limitar_hilos(self.hilos):
            partes = [self.modelo.predict(X[i:i + b][:, self.cols]) for i in range(0, len(X), b)]
        return np.concatenate(partes).astype("float64") if partes else np.zeros(0)


# ---------------------------------------------------------------------------
# Eje B: GWR, RK e IDW por estadísticos suficientes (diseño aprendido en el pliegue)
# ---------------------------------------------------------------------------
def resolver_normales(A: np.ndarray, b: np.ndarray, sx: np.ndarray, n: float, fijos: dict | None = None,
                      ridge: float = RIDGE_LINEAL) -> np.ndarray:
    """Réplica de ``_resolver`` (``qmd:2981-3001``): columnas sin variación desactivadas, coeficientes ``fijos``
    (las indicadoras en GWR) sin reestimar y cresta 1e-6."""
    p = len(b)
    beta = np.zeros(p)
    fijos = fijos or {}
    activa = (np.diag(A) - sx ** 2 / max(n, 1e-12)) > 1e-8 * max(n, 1.0)
    activa[0] = True
    libres = np.array([j for j in range(p) if activa[j] and j not in fijos], dtype=int)
    for j, v in fijos.items():
        beta[j] = v
    if len(fijos):
        jf = np.array(list(fijos), dtype=int)
        b = b - A[:, jf] @ beta[jf]
    Al = A[np.ix_(libres, libres)] + ridge * np.eye(len(libres))
    try:
        beta[libres] = np.linalg.solve(Al, b[libres])
    except np.linalg.LinAlgError:
        beta[libres] = np.linalg.lstsq(Al, b[libres], rcond=None)[0]
    return beta


def variograma_exponencial(dist: np.ndarray, gamma: np.ndarray) -> np.ndarray:
    """Réplica de ``_variograma_exponencial`` (``qmd:2958-2979``): γ(h) = c0 + c1·(1 − e^(−h/a)) ajustado a 15
    clases por cuantiles hasta la mitad de la distancia máxima, con residuos relativos y alcance acotado."""
    from scipy.optimize import least_squares
    ok = np.isfinite(dist) & np.isfinite(gamma)
    dist, gamma = dist[ok], gamma[ok]
    if len(dist) < 10:
        return np.array([max(float(np.nanmean(gamma)) if len(gamma) else 1.0, 1e-9), 1e-9, 1.0])
    max_lag = 0.5 * float(dist.max())
    cerca = dist <= max_lag
    clases = np.unique(np.quantile(dist[cerca], np.linspace(0, 1, 16)))
    k = np.clip(np.searchsorted(clases, dist[cerca], side="right") - 1, 0, max(len(clases) - 2, 0))
    hb = np.array([dist[cerca][k == c].mean() for c in np.unique(k)])
    gb = np.array([gamma[cerca][k == c].mean() for c in np.unique(k)])
    x0 = [max(float(gb.min()), 1e-9), max(float(gb.max() - gb.min()), 1e-9), min(max(float(np.median(hb)), 1.0), max_lag)]
    try:
        sol = least_squares(lambda t: ((t[0] + t[1] * (1 - np.exp(-hb / t[2]))) - gb) / np.maximum(gb, 1e-9), x0=x0,
                            bounds=([0, 1e-12, 1e-3], [np.inf, np.inf, max(max_lag, 1.0)]))
        return sol.x
    except Exception:  # noqa: BLE001
        return np.array(x0)


class LinealesPorUnidades:
    """GWR, RK e IDW de un contaminante con estadísticos suficientes por unidad estación × cuatrienio.

    Base por fila ``B = [1, x̃₁, I₁, …, x̃ₘ, Iₘ, calendario]`` (x̃ = valor con 0 donde falta, I = indicadora de
    faltante) para las columnas del diseño de la v1 salvo ``obs_vec``, cuyas dos columnas se agregan en cada
    pliegue con el vecindario recalculado. El diseño del pliegue es ``X = B T``: imputación con la mediana del
    entrenamiento (``x̃ + m·I``), indicadora si falta más del 5 % en el entrenamiento, selección por cobertura
    ≥ 5 % y estandarización con media y desviación poblacional del entrenamiento (como ``diseno_lineal``). Así
    ``X'X`` por unidad es ``Tᵀ (B'B) T``: exacto, sin rehacer las sumas sobre 9,7 M filas."""

    def __init__(self, pol: str, feats: list[str], X: np.ndarray, y: np.ndarray, estacion_cod: np.ndarray,
                 ventana_cod: np.ndarray, D_estaciones: np.ndarray, receta: dict | None = None):
        t0 = time.perf_counter()
        self.pol = pol
        self.receta = receta or {"k_vecinos": K_VECINOS_GWR, "ridge": RIDGE_LINEAL}
        d = pd.DataFrame({c: X[:, feats.index(c)] for c in self._columnas_crudas(feats)})
        base = base_lineal(d, pol, en_log=False)
        self.candidatas = [c for c in columnas_base_lineal(pol, False) if c in base.columns and c != "obs_vec"]
        self.crudas = {c: base[c].to_numpy("float64") for c in self.candidatas}
        cal = np.column_stack([X[:, feats.index(c)].astype("float64") for c in CALENDARIO])
        self.y = np.asarray(y, dtype="float64")
        self.n = len(self.y)
        est, ven = np.asarray(estacion_cod, dtype="int64"), np.asarray(ventana_cod, dtype="int64")
        unidad = est * 1000 + ven
        self.orden = np.argsort(unidad, kind="stable")
        claves, self.inicio, self.cuenta = np.unique(unidad[self.orden], return_index=True, return_counts=True)
        self.u_est, self.u_ven = claves // 1000, claves % 1000
        self.U = len(claves)
        self.D = np.asarray(D_estaciones, dtype="float64")
        # Base sin obs_vec, en el orden de las unidades: [1, x̃₁, I₁, …, cal]
        cols = [np.ones(self.n)]
        self.nombres_base = ["constante"]
        for c in self.candidatas:
            v = self.crudas[c]
            falta = ~np.isfinite(v)
            cols += [np.where(falta, 0.0, v), falta.astype("float64")]
            self.nombres_base += [f"{c}~x", f"{c}~I"]
        for j, c in enumerate(CALENDARIO):
            cols.append(cal[:, j])
            self.nombres_base.append(c)
        self.Bs = np.column_stack(cols)[self.orden]             # n × q0, ordenada por unidad
        self.ys = self.y[self.orden]
        self.q0 = self.Bs.shape[1]
        self.BtB0 = np.stack([self.Bs[i:i + c].T @ self.Bs[i:i + c] for i, c in zip(self.inicio, self.cuenta)])
        self.Bty0 = np.stack([self.Bs[i:i + c].T @ self.ys[i:i + c] for i, c in zip(self.inicio, self.cuenta)])
        self.Sy = np.add.reduceat(self.ys, self.inicio) if self.n else np.zeros(0)
        self.segundos_construccion = round(time.perf_counter() - t0, 3)

    @staticmethod
    def _columnas_crudas(feats) -> list[str]:
        quiero = {*FISICO_LINEAL["pm25"], *FISICO_LINEAL["no2"], "acag_pm25", "inv_blh", "el_t2m", "m2_t2m", "el_wind",
                  "m2_u10m", "m2_v10m"}
        return [c for c in feats if c in quiero]

    def unidades_de(self, filas_mascara: np.ndarray) -> np.ndarray:
        """Unidades (booleana U) cuyas filas están todas en la máscara; error si alguna queda partida."""
        m = np.asarray(filas_mascara, dtype=bool)[self.orden]
        dentro = np.add.reduceat(m.astype("int64"), self.inicio)
        if ((dentro > 0) & (dentro < self.cuenta)).any():
            raise ValueError("una unidad estación × cuatrienio queda partida entre entrenamiento y prueba")
        return dentro == self.cuenta

    def ajustar_predecir(self, obs_vec: np.ndarray, entrenamiento: np.ndarray, prueba: np.ndarray) -> tuple[dict, dict]:
        """GWR, RK e IDW de las filas de ``prueba`` (máscaras sobre el panel) con ``obs_vec`` recalculado sin el
        conjunto excluido en todas las filas. Devuelve ``({motor: predicción de las filas de prueba en orden
        ascendente}, info)``."""
        t0 = time.perf_counter()
        ent_u, pru_u = self.unidades_de(entrenamiento), self.unidades_de(prueba)
        if not ent_u.any():
            raise ValueError("pliegue sin unidades de entrenamiento")
        ov = np.asarray(obs_vec, dtype="float64")
        ov_s = ov[self.orden]
        I_ov = ~np.isfinite(ov_s)
        x_ov = np.where(I_ov, 0.0, ov_s)
        V = np.column_stack([x_ov, I_ov.astype("float64")])
        q = self.q0 + 2
        BtB = np.zeros((self.U, q, q))
        BtB[:, :self.q0, :self.q0] = self.BtB0
        Bty = np.zeros((self.U, q))
        Bty[:, :self.q0] = self.Bty0
        for u, (i, c) in enumerate(zip(self.inicio, self.cuenta)):
            cruz = self.Bs[i:i + c].T @ V[i:i + c]
            BtB[u, :self.q0, self.q0:] = cruz
            BtB[u, self.q0:, :self.q0] = cruz.T
            BtB[u, self.q0:, self.q0:] = V[i:i + c].T @ V[i:i + c]
            Bty[u, self.q0:] = V[i:i + c].T @ self.ys[i:i + c]
        nombres = self.nombres_base + ["obs_vec~x", "obs_vec~I"]
        idx = {nm: j for j, nm in enumerate(nombres)}
        # --- Preprocesamiento del pliegue (sólo entrenamiento) ---
        Stot = BtB[ent_u].sum(axis=0)
        n_tr = float(Stot[0, 0])
        ent_filas = np.asarray(entrenamiento, dtype=bool)
        # Orden de la v1 (qmd:2925-2956): productos, ACAG, vecindario, 1/BLH, temperatura y viento; luego las
        # indicadoras y al final el calendario.
        columnas_lineales = [c for c in columnas_base_lineal(self.pol, False) if c == "obs_vec" or c in self.candidatas]
        diseno, medianas, indicadoras, descartadas = [], {}, [], []
        for c in columnas_lineales:
            jx, jI = idx[f"{c}~x"], idx[f"{c}~I"]
            faltan = float(Stot[0, jI])
            cobertura = 1.0 - faltan / n_tr
            if cobertura < COBERTURA_MIN:
                descartadas.append(c)
                continue
            v = ov[ent_filas] if c == "obs_vec" else self.crudas[c][ent_filas]
            m = float(np.nanmedian(v)) if cobertura > 0 else 0.0
            medianas[c] = m
            diseno.append(("imputada", c, jx, jI, m))
            if faltan / n_tr > FALTANTE_INDICADORA:
                indicadoras.append(c)
        for c in indicadoras:
            diseno.append(("indicadora", c, None, idx[f"{c}~I"], None))
        for c in CALENDARIO:
            diseno.append(("calendario", c, idx[c], None, None))
        T = np.zeros((q, 1 + len(diseno)))
        T[0, 0] = 1.0
        nombres_d = ["constante"]
        for d_i, (tipo, c, jx, jI, m) in enumerate(diseno, start=1):
            a = np.zeros(q)
            if tipo == "imputada":
                a[jx], a[jI] = 1.0, m
            elif tipo == "indicadora":
                a[jI] = 1.0
            else:
                a[jx] = 1.0
            s1 = float(a @ Stot[0])                                 # Σ (B a) sobre el entrenamiento
            s2 = float(a @ Stot @ a)                                # Σ (B a)²
            mu = s1 / n_tr
            var = max(s2 / n_tr - mu * mu, 0.0)
            sd = np.sqrt(var) if var > 0 else 1.0                   # qmd:2952 (sd 0 → 1)
            col = a.copy()
            col[0] -= mu
            T[:, d_i] = col / sd
            nombres_d.append(f"{c}_falta" if tipo == "indicadora" else c)
        XtX = np.einsum("qi,uqr,rj->uij", T, BtB, T)
        Xty = np.einsum("qi,uq->ui", T, Bty)
        Sx = np.einsum("qi,uq->ui", T, BtB[:, :, 0])
        cuenta = self.cuenta.astype("float64")
        entrena = np.flatnonzero(ent_u)
        # --- RK: tendencia global + kriging ordinario del residuo medio por estación (qmd:3082-3100) ---
        beta = resolver_normales(XtX[entrena].sum(axis=0), Xty[entrena].sum(axis=0), Sx[entrena].sum(axis=0), n_tr,
                                 ridge=self.receta["ridge"])
        S = self.D.shape[0]
        n_e = np.bincount(self.u_est[entrena], weights=cuenta[entrena], minlength=S)
        r_e = np.bincount(self.u_est[entrena], weights=self.Sy[entrena] - Sx[entrena] @ beta, minlength=S)
        con = np.flatnonzero(n_e > 0)
        r_med = r_e[con] / n_e[con]
        Dt = self.D[np.ix_(con, con)]
        iu = np.triu_indices(len(con), k=1)
        if len(con) > 2:
            c0, c1, a_rango = variograma_exponencial(Dt[iu], 0.5 * (r_med[iu[0]] - r_med[iu[1]]) ** 2)
        else:
            c0, c1, a_rango = 1.0, 1e-9, 1.0
        K = np.zeros((len(con) + 1, len(con) + 1))
        K[:-1, :-1] = c1 * np.exp(-Dt / a_rango) + np.eye(len(con)) * (c0 + 1e-9)
        K[-1, :-1] = K[:-1, -1] = 1.0
        indic_d = [j for j, nm in enumerate(nombres_d) if nm.endswith("_falta")]
        fijos = {j: float(beta[j]) for j in indic_d}               # las indicadoras no se reestiman localmente
        media_tr = float(self.Sy[entrena].sum()) / max(n_tr, 1.0)
        filas_prueba = np.flatnonzero(np.asarray(prueba, dtype=bool))
        pos = np.full(self.n, -1, dtype="int64")
        pos[filas_prueba] = np.arange(len(filas_prueba))
        pred = {m: np.full(len(filas_prueba), np.nan, dtype="float32") for m in MOTORES_LINEALES}
        prueba_u = np.flatnonzero(pru_u)
        kv = int(self.receta["k_vecinos"])
        for s in np.unique(self.u_est[prueba_u]):
            try:
                lam = np.linalg.solve(K, np.append(c1 * np.exp(-self.D[s, con] / a_rango), 1.0))[:-1]
            except np.linalg.LinAlgError:
                lam = np.full(len(con), 1.0 / len(con))
            delta = float(lam @ r_med)
            d_est = self.D[s, con]
            h = np.sort(d_est)[min(kv, len(d_est)) - 1] + 1e-9
            w = np.exp(-(self.D[s, self.u_est[entrena]] / h) ** 2)
            beta_s = resolver_normales(np.tensordot(w, XtX[entrena], axes=1), w @ Xty[entrena], w @ Sx[entrena],
                                       float(w @ cuenta[entrena]), fijos, ridge=self.receta["ridge"])
            for u in prueba_u[self.u_est[prueba_u] == s]:
                i, c = self.inicio[u], self.cuenta[u]
                Bf = np.column_stack([self.Bs[i:i + c], V[i:i + c]])
                Xf = Bf @ T
                filas = self.orden[i:i + c]
                p_ = pos[filas]
                pred["gwr"][p_] = np.clip(Xf @ beta_s, 0, None)
                pred["rk"][p_] = np.clip(Xf @ beta + delta, 0, None)
                pred["idw"][p_] = np.where(np.isfinite(ov[filas]), ov[filas], media_tr)
        info = {"columnas_diseno": nombres_d, "descartadas_por_cobertura": descartadas, "indicadoras": indicadoras,
                "medianas": medianas, "filas_entrenamiento": int(n_tr), "unidades_entrenamiento": int(ent_u.sum()),
                "unidades_prueba": int(pru_u.sum()), "variograma": {"c0": float(c0), "c1": float(c1), "a": float(a_rango)},
                "estaciones_kriging": int(len(con)), "media_entrenamiento": media_tr, "k_vecinos": kv,
                "ridge": self.receta["ridge"], "segundos": round(time.perf_counter() - t0, 3)}
        return pred, info


# ---------------------------------------------------------------------------
# Apilado anidado y pliegues internos
# ---------------------------------------------------------------------------
def pliegues_internos(grupos_entrenamiento, k: int, n_internos: int) -> list[list[str]]:
    """Reparte las etiquetas de grupo del entrenamiento (regiones en LRO, bloques en BLQ-75) en ``n_internos``
    pliegues internos agrupados: permutación ``default_rng([42, k, 1000])`` de las etiquetas ordenadas, en
    turnos. Con menos grupos que pliegues, un grupo por pliegue."""
    g = sorted({str(x) for x in grupos_entrenamiento})
    if len(g) < 2:
        raise ValueError("el apilado anidado necesita al menos dos grupos en el entrenamiento")
    n = min(int(n_internos), len(g))
    orden = np.random.default_rng([SEMILLA_BASE, int(k), SEMILLA_INTERNOS]).permutation(len(g))
    salida = [[] for _ in range(n)]
    for pos, i in enumerate(orden):
        salida[pos % n].append(g[i])
    return [sorted(s) for s in salida]


def pesos_simplex(Z: np.ndarray, y: np.ndarray, tol: float = 1e-12) -> np.ndarray:
    """Pesos ``w ≥ 0`` con ``Σw = 1`` que minimizan ``‖y − Z w‖²``, de forma exacta: el óptimo de un problema
    cuadrático convexo sobre el símplex es el óptimo con igualdad de alguna cara; se resuelven todas las caras
    (2^p − 1, con p ≤ 8 motores) y se elige la factible de menor pérdida. Determinista, sin tolerancias de un
    optimizador."""
    Z, y = np.asarray(Z, dtype="float64"), np.asarray(y, dtype="float64")
    ok = np.isfinite(y) & np.isfinite(Z).all(axis=1)
    Z, y = Z[ok], y[ok]
    p = Z.shape[1]
    if p > 8:
        raise ValueError("pesos_simplex enumera caras: hasta 8 motores")
    G, c, yy = Z.T @ Z, Z.T @ y, float(y @ y)
    mejor, mejor_w = np.inf, None
    for tam in range(1, p + 1):
        for S in itertools.combinations(range(p), tam):
            S = list(S)
            KKT = np.zeros((tam + 1, tam + 1))
            KKT[:tam, :tam] = 2.0 * G[np.ix_(S, S)]
            KKT[:tam, tam] = KKT[tam, :tam] = 1.0
            rhs = np.append(2.0 * c[S], 1.0)
            try:
                sol = np.linalg.solve(KKT, rhs)
            except np.linalg.LinAlgError:
                sol = np.linalg.lstsq(KKT, rhs, rcond=None)[0]
            wS = sol[:tam]
            if (wS < -1e-10).any() or abs(wS.sum() - 1.0) > 1e-8:
                continue
            w = np.zeros(p)
            w[S] = np.clip(wS, 0.0, None)
            w /= w.sum()
            perdida = yy - 2.0 * w @ c + w @ G @ w
            if perdida < mejor - tol * max(1.0, abs(mejor) if np.isfinite(mejor) else 1.0):
                mejor, mejor_w = perdida, w
    if mejor_w is None:
        raise ValueError("sin solución factible en el símplex")
    return mejor_w
