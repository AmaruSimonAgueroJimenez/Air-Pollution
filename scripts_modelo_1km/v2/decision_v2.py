"""Regla de decisión del producto v2 (``DISENO_AMBIENTAL_V2.md`` §9, cerrada por la Enmienda 1, punto 11, con su
Complemento, puntos 1, 2, 3 y 6).

La decisión no se toma a mano: ``decidir_motor`` aplica la regla completa, por contaminante, a la **evidencia** de
LRO y de BLQ-75 que deja la consolidación (``evidencia_protocolo``). La evidencia son sumas suficientes por bloque
(``bootstrap_v2.SumasBloques``) del nivel diario civil sobre los pares de la decisión: no lleva predicciones, y todo
lo que sigue se recalcula a partir de ella, de forma determinista con las semillas declaradas.

**Candidatos.** XGBoost, RF, MLP y el promedio simple (``promedio`` en la consolidación). El apilado es sólo
descriptivo y no se despliega; Huber, q50, el eje B y las alertas no compiten. Si ningún candidato cumple la regla,
se mantiene LightGBM.

**Pares de la decisión** (``pares_de_la_decision``): la intersección de las predicciones finitas **sólo** entre
LightGBM y los candidatos, con sus réplicas (0, 1 y 2) y las dos formas de retransformación, para que todos los Δ_r
usen los mismos pares. Se informa cuántos pares quitaría cada familia del resto (eje B, pérdidas, cuantiles,
alertas, variantes de calidad, curvas de aprendizaje, apilado y sensibilidades).

**Estadístico.** ΔR² = R²(candidato) − R²(LightGBM), diario (día civil de America/Santiago), ponderado con los
pesos fijos por estación (punto 4), sobre E1, con la retransformación primaria ``smearing_duan``; estimación
puntual Δ̄, la media de las 3 réplicas (punto 3).

**Condiciones** (``evaluar_protocolo``), en LRO y en BLQ-75, todas a la vez:

1. **superioridad**: el IC percentil del 95 % de Δ̄* (B = 1.999 réplicas), ajustado por Holm sobre los 4 candidatos
   (``p = 2·mín(fracción de Δ̄* ≤ 0, fracción ≥ 0)``, escalonado), excluye 0 a favor del candidato, y la segunda
   prueba, con su propio Holm sobre los 4 candidatos, también declara a su favor. La segunda prueba que decide es el
   **cambio de signo del bootstrap salvaje por bloque** sobre los totales T_g de w·(e_c² − e_LightGBM²), con la nula
   impuesta y el t de varianza CV1 (Webb y 9.999 sorteos si G < 12; Rademacher con la enumeración completa si
   12 ≤ G ≤ 16; Rademacher con 9.999 sorteos si G > 16; semilla ``[42, 3000, p]``); el jackknife CV3 con t de G − 1
   gl **sólo informa** (Complemento, punto 1). La decisión usa **el intervalo escalonado publicado** (el IC al nivel
   de Holm de cada candidato) junto con la cadena de Holm; con B = 1.999 coincide siempre con el p (Complemento,
   punto 2). Una declaración cuenta sólo si favorece al candidato;
2. **ruido de la diferencia**: ``|Δ̄| > rango(Δ_r)`` con **las 3 réplicas comunes**; con menos, «no evaluada», que no
   basta para reemplazar (Complemento, punto 6);
3. **consistencia con E2**: el Δ̄ sobre los pares de la decisión que están en E2 tiene el signo del de E1; si E2
   no es evaluable en el protocolo (≥ 50 % del peso de E1 y ≥ 5 grupos con pares E2, en el nivel diario civil), no
   bloquea y se informa «sin confirmación con datos validados»;
4. **influencia**: la condición 1 completa (los 4 candidatos, los dos Holm y la segunda prueba) se rehace sin el
   bloque más influyente (la RM en LRO y E004N083 en BLQ-75); si no sobrevive, la superioridad es «no robusta». Si
   el bloque no tiene pares de la decisión, quitarlo no cambia nada y se registra así;
5. **signo sin ponderar y en log**: el signo de Δ̄ se repite sin ponderar y con las métricas en log (ẑ frente a
   log1p(y), promediados en log en el día civil, ponderados);
6. **misma decisión con ½·σ²**: la regla completa (condiciones 1–5 y 7, factibilidad y desempate) se aplica
   también con ``lognormal_medio_sigma2``; el reemplazo vale sólo si las dos correcciones eligen el mismo motor
   (regla previa del punto 2). En la tabla, la columna de la condición 6 de un candidato dice si cumple las demás
   condiciones con la otra corrección en ese protocolo;
7. **no inferioridad en sesgo**: ``|NMB_c| ≤ |NMB_LightGBM| + 1`` punto porcentual, con el NMB en porcentaje, el
   mismo nivel, ponderación, conjunto, pares y retransformación, como media de las 3 réplicas.

**Factibilidad** (Complemento, punto 3, irrevisable; reemplaza la del punto 11): se mide antes de cualquier ajuste
comparativo el tiempo de predecir un día completo de superficies con cada motor (predictores de producción:
LightGBM compilado con lleaves, XGBoost y RF con treelite / tl2cgen, la MLP en float32 por lotes), con 12 hilos, en
3 días reales por contaminante. La producción 2000–2026 de un motor cuesta, por contaminante, la media de sus 3
días por los 9.862 días del calendario, y se suman los dos contaminantes; el promedio simple cuesta la suma de sus
cuatro miembros. Un candidato es factible si cuesta ≤ 5 veces lo que LightGBM compilado y ≤ 21 días de máquina; si
no, queda fuera de la decisión, con registro. LightGBM es la referencia: la regla no lo excluye. Sin la medición
(de los dos contaminantes y de LightGBM), ``decidir_motor`` se detiene.

**Desempate**: si varios candidatos pasan, gana la mayor media simple de sus dos R² (LRO y BLQ-75), cada uno la
media de sus réplicas. Los candidatos cuya diferencia con el primero no supera el ruido (el rango de esa diferencia
entre las 3 réplicas, punto 3) empatan con él; entre ellos se prefiere un motor único al promedio simple y después
el más barato de producir (el menor costo de la factibilidad). El desempate exige las 3 réplicas comunes: con menos
queda «no evaluado» y no da a ningún candidato el reemplazo de LightGBM (Complemento, punto 6).

**Evidencia parcial** (ratificada por el Complemento, punto 4.7): un candidato que cumple las siete condiciones en
un protocolo y en el otro tiene un IC percentil del 95 % sin ajustar del mismo ΔR² que no excluye 0 en su contra se
informa como «evidencia parcial»; no reemplaza a LightGBM y, si es factible, sus superficies pasan a ser
sensibilidad de exposición (etapa 10).

``decidir_motor`` devuelve una tabla (una fila por candidato × protocolo × forma, con cada condición y sus
estadísticos) y un registro JSON trazado (decisión, motivo, desempate, factibilidad, evidencia parcial, pares de la
decisión y lo que quita cada familia, evaluabilidad de E2, influencia y Δ̄ sin cada bloque, la regla, las semillas,
el sha256 de cada evidencia y la traza que pase la consolidación).
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

import bootstrap_v2 as bs
import metricas_v2 as mt
import retransformacion_v2 as rt

SCHEMA_EVIDENCIA = "airpollution.modelo-1km-v2.decision-evidencia.v2"   # v2: semilla [42, 3000, p] (Complemento)
SCHEMA_DECISION = "airpollution.modelo-1km-v2.decision.v2"               # v2: Complemento, puntos 1, 2, 3 y 6

REFERENCIA = "lightgbm"
CANDIDATOS = ("xgboost", "random_forest", "mlp", "promedio_simple")
PREDICCION = {"promedio_simple": "promedio"}              # nombre de la predicción en la consolidación
PROTOCOLOS_DECISION = ("LRO", "BLQ-75")
ORDEN_PROTOCOLOS = ("LOSO-D", "LBO-10", "BLQ-75", "LRO", "LPO")      # protocolos.orden: semilla [42, 2000, p]
NIVEL_DECISION = "diario_civil"
ALFA = 0.05
M_HOLM = 4
MARGEN_NMB_PP = 1.0
BLOQUE_MAS_INFLUYENTE = {"LRO": "RM", "BLQ-75": "E004N083"}
UMBRAL_DIAS_MAQUINA = 21.0               # Complemento, punto 3 (antes 7, por contaminante)
FACTOR_MAXIMO_LIGHTGBM = 5.0             # Complemento, punto 3: ≤ 5 veces la producción de LightGBM compilado
CONTAMINANTES_FACTIBILIDAD = ("pm25", "no2")    # se suman los dos contaminantes
HILOS_FACTIBILIDAD = 12
MIEMBROS_PROMEDIO = ("lightgbm", "xgboost", "random_forest", "mlp")   # el promedio simple cuesta su suma
PERIODO_PRODUCCION = (2000, 2026)
SEGUNDOS_POR_DIA = 86_400.0
UNICO_FRENTE_A = "promedio_simple"        # «se prefiere un motor único al promedio simple»
EJE_B = ("gp", "lme", "gwr", "rk", "idw")
FORMAS = {rt.SMEARING: rt.SUFIJO_FORMA[rt.SMEARING], rt.LOGNORMAL: rt.SUFIJO_FORMA[rt.LOGNORMAL]}
FORMA_PRIMARIA, FORMA_FIJA = rt.SMEARING, rt.LOGNORMAL
CONDICIONES = ("superioridad", "ruido_de_la_diferencia", "consistencia_con_E2", "influencia",
               "signo_sin_ponderar_y_en_log", "misma_decision_con_lognormal", "no_inferioridad_en_sesgo")
COLUMNA_CONDICION = {c: f"c{i + 1}_{c}" for i, c in enumerate(CONDICIONES)}
V_E1, V_E1_SIN, V_E1_LOG, V_E2 = ("E1|poblacion|original", "E1|ninguna|original", "E1|poblacion|log",
                                  "E2|poblacion|original")
SIN_BANDERA = "sin bandera de calidad (calidad_v2): no hay E2"


def dias_del_periodo(desde: int, hasta: int) -> int:
    """Días del calendario de ``desde``-01-01 a ``hasta``-12-31 (2000–2026: 9.862)."""
    return (_dt.date(int(hasta), 12, 31) - _dt.date(int(desde), 1, 1)).days + 1


DIAS_PRODUCCION = dias_del_periodo(*PERIODO_PRODUCCION)


@dataclass(frozen=True)
class ReglaDecision:
    """Parámetros de la regla (por omisión, los del contrato; ``regla_de_config`` los lee de la configuración)."""

    referencia: str = REFERENCIA
    candidatos: tuple = CANDIDATOS
    protocolos: tuple = PROTOCOLOS_DECISION
    nivel: str = NIVEL_DECISION
    alfa: float = ALFA
    m_holm: int = M_HOLM
    margen_nmb_pp: float = MARGEN_NMB_PP
    bloque_mas_influyente: dict = field(default_factory=lambda: dict(BLOQUE_MAS_INFLUYENTE))
    umbral_dias_maquina: float = UMBRAL_DIAS_MAQUINA
    factor_maximo_frente_a_lightgbm: float = FACTOR_MAXIMO_LIGHTGBM
    contaminantes_factibilidad: tuple = CONTAMINANTES_FACTIBILIDAD
    hilos_factibilidad: int = HILOS_FACTIBILIDAD
    miembros_promedio: tuple = MIEMBROS_PROMEDIO
    dias_produccion: int = DIAS_PRODUCCION
    replicas_bootstrap: int = bs.REPLICAS
    nivel_intervalo: float = bs.NIVEL
    replicas_salvaje: int = bs.REPLICAS_SALVAJE
    replicas_exigidas: int = bs.REPLICAS_EXIGIDAS

    def como_dict(self) -> dict:
        return {**asdict(self), "candidatos": list(self.candidatos), "protocolos": list(self.protocolos),
                "contaminantes_factibilidad": list(self.contaminantes_factibilidad),
                "miembros_promedio": list(self.miembros_promedio),
                "segunda_prueba": {"prueba_que_decide": bs.PRUEBA_QUE_DECIDE, "sorteos": self.replicas_salvaje,
                                   "G_minimo_rademacher": bs.G_MINIMO_RADEMACHER,
                                   "G_maximo_enumeracion_completa": bs.G_MAXIMO_ENUMERACION,
                                   "semilla": [bs.SEMILLA_BASE, bs.SEMILLA_SALVAJE, "p"],
                                   "jackknife_cv3": "sólo informa"},
                "semilla_bootstrap": [bs.SEMILLA_BASE, bs.SEMILLA_BOOTSTRAP, "p"]}


def _segunda_prueba_de_config(inf: dict) -> dict:
    """La segunda prueba de ``inferencia_diferencias.segunda_prueba.metodo`` (Complemento, punto 1), comprobada contra
    lo que implementa ``bootstrap_v2``: decide el cambio de signo del bootstrap salvaje, con sus umbrales de G, sus
    sorteos y su semilla ``[42, 3000, p]``."""
    v = rt.valor_config(inf["segunda_prueba"]["metodo"], "inferencia_diferencias.segunda_prueba.metodo")
    if not isinstance(v, dict) or v.get("prueba_que_decide") != bs.PRUEBA_QUE_DECIDE:
        raise ValueError(f"la segunda prueba que decide debe ser {bs.PRUEBA_QUE_DECIDE} (Complemento, punto 1)")
    c = v[bs.PRUEBA_QUE_DECIDE]
    if (int(c["G_minimo_rademacher"]), int(c["G_maximo_enumeracion_completa"])) != (bs.G_MINIMO_RADEMACHER,
                                                                                   bs.G_MAXIMO_ENUMERACION):
        raise ValueError(f"umbrales de G de la segunda prueba distintos de los de bootstrap_v2: {c}")
    if list(c["semilla"][:2]) != [bs.SEMILLA_BASE, bs.SEMILLA_SALVAJE] or str(c["semilla"][2]) != "p":
        raise ValueError(f"semilla de la segunda prueba distinta de [42, 3000, p]: {c['semilla']}")
    return {"sorteos": int(c["sorteos"])}


def _replicas_exigidas_de_config(cfg: dict) -> int:
    """Réplicas comunes que exigen la condición 2 y el desempate (Complemento, punto 6), iguales en los tres lugares
    de la configuración y a las del ruido de ``bootstrap_v2``."""
    d = cfg["decision"]
    cond = {c["id"]: c for c in d["condiciones"]}
    valores = {int(cfg["ruido"]["replicas_exigidas_en_la_decision"]["valor"]),
               int(cond["ruido_de_la_diferencia"]["replicas_exigidas"]), int(d["desempate"]["replicas_exigidas"])}
    if valores != {bs.REPLICAS_EXIGIDAS}:
        raise ValueError(f"las réplicas exigidas en la decisión deben ser {bs.REPLICAS_EXIGIDAS}: {sorted(valores)}")
    return bs.REPLICAS_EXIGIDAS


def regla_de_config(cfg: dict) -> ReglaDecision:
    """La regla tal como la traduce ``config_v2.json`` (``decision``, ``inferencia_diferencias`` y ``ruido``), con
    las comprobaciones de lo que el código da por fijo (estadístico, conjunto, forma primaria, segunda prueba, B y
    réplicas exigidas) y la factibilidad del Complemento (punto 3)."""
    d = cfg["decision"]
    e = d["estadistico"]
    if (e["nivel"], e["conjunto"], e["retransformacion"]) != (NIVEL_DECISION, mt.E1, FORMA_PRIMARIA):
        raise ValueError(f"decision.estadistico no es el del contrato: {e}")
    if not str(d["por_omision"]).startswith(REFERENCIA):
        raise ValueError("decision.por_omision debe ser LightGBM")
    cond = {c["id"]: c for c in d["condiciones"]}
    if tuple(cond) != CONDICIONES:
        raise ValueError(f"las condiciones de la configuración no son las siete del contrato: {list(cond)}")
    holm = cond["superioridad"]["holm"]
    if int(holm["m"]) != len(d["candidatos"]):
        raise ValueError("Holm debe ser sobre los candidatos declarados")
    inf = cfg["inferencia_diferencias"]
    sp = _segunda_prueba_de_config(inf)
    f = d["factibilidad"]
    if tuple(f["contaminantes"]) != CONTAMINANTES_FACTIBILIDAD:
        raise ValueError(f"la factibilidad suma los dos contaminantes {CONTAMINANTES_FACTIBILIDAD}: {f['contaminantes']}")
    return ReglaDecision(candidatos=tuple(d["candidatos"]), protocolos=tuple(d["protocolos"]), nivel=e["nivel"],
                         alfa=float(holm["alfa_de_la_familia"]), m_holm=int(holm["m"]),
                         margen_nmb_pp=float(cond["no_inferioridad_en_sesgo"]["margen_puntos_porcentuales"]),
                         bloque_mas_influyente=dict(inf["influencia"]["bloque_mas_influyente"]),
                         umbral_dias_maquina=float(f["umbral_dias_de_maquina"]),
                         factor_maximo_frente_a_lightgbm=float(f["factor_maximo_frente_a_lightgbm"]),
                         contaminantes_factibilidad=tuple(f["contaminantes"]), hilos_factibilidad=int(f["hilos"]),
                         dias_produccion=dias_del_periodo(*f["periodo"]),
                         replicas_bootstrap=int(inf["bootstrap"]["replicas"]),
                         nivel_intervalo=float(inf["regla_de_superioridad"]["nivel_del_intervalo"]),
                         replicas_salvaje=sp["sorteos"], replicas_exigidas=_replicas_exigidas_de_config(cfg))


REGLA = ReglaDecision()


# ---------------------------------------------------------------------------
# Nombres
# ---------------------------------------------------------------------------
def prediccion(candidato: str) -> str:
    """Nombre de la predicción de un candidato en la consolidación (``promedio_simple`` → ``promedio``)."""
    return PREDICCION.get(candidato, candidato)


def con_forma(nombre: str, sufijo: str) -> str:
    """Inserta el sufijo de la forma antes del de la réplica: ``xgboost@r1`` → ``xgboost~lognormal@r1``."""
    base, r = bs.separar_replica(nombre)
    return bs.nombre_replica(base + sufijo, r)


def nombres_de_la_decision(nombres: Sequence[str], regla: ReglaDecision = REGLA) -> list[str]:
    """LightGBM y los candidatos, con sus réplicas y las dos formas, que están entre ``nombres``."""
    disponibles = set(nombres)
    out = []
    for base in [regla.referencia, *(prediccion(c) for c in regla.candidatos)]:
        for sufijo in FORMAS.values():
            for r in bs.REPLICAS_DEL_RUIDO:
                nm = bs.nombre_replica(base + sufijo, r)
                if nm in disponibles:
                    out.append(nm)
    return out


def familia_de(nombre: str) -> str:
    """Familia de una predicción que no es de la decisión (para contar los pares que quitaría)."""
    base = bs.separar_replica(nombre)[0]
    if rt.SUFIJO_INTERNA in base:
        return "sensibilidad_oof_interno"
    nucleo = base.replace(rt.SUFIJO_FORMA[rt.LOGNORMAL], "")
    if nucleo in EJE_B:
        return "eje_B"
    if nucleo.startswith("alertas"):
        return "alertas"
    if "_cal_" in nucleo:
        return "variantes_de_calidad"
    if nucleo.endswith(("_q05", "_q95")):
        return "cuantiles"
    if nucleo.endswith(("_l2_original", "_huber", "_huber_friedman", "_q50")):
        return "perdidas"
    if re.search(r"_n(\d+|todas)$", nucleo):
        return "curvas_de_aprendizaje"
    if nucleo == "apilado":
        return "apilado"
    if nucleo in (REFERENCIA, *(prediccion(c) for c in CANDIDATOS)):
        return "decision_otras_replicas"
    return "otros"


def pares_de_la_decision(obs, pred: Mapping[str, np.ndarray], regla: ReglaDecision = REGLA) -> tuple[np.ndarray, dict]:
    """Máscara de los pares de la decisión (intersección sólo entre LightGBM y los candidatos, con sus réplicas y
    las dos formas) y el registro, con lo que quitaría cada familia del resto (``metricas_v2.pares_comunes``)."""
    nombres = nombres_de_la_decision(list(pred), regla)
    if regla.referencia not in nombres:
        raise ValueError("sin predicciones de LightGBM no hay pares de la decisión")
    familias: dict[str, list[str]] = {}
    for nm in pred:
        if nm not in nombres:
            familias.setdefault(familia_de(nm), []).append(nm)
    m, info = mt.pares_comunes(obs, pred, motores=nombres, familias=familias)
    info["familias"] = {k: sorted(v) for k, v in sorted(familias.items())}
    return m, info


# ---------------------------------------------------------------------------
# Evidencia de un protocolo (la escribe la consolidación)
# ---------------------------------------------------------------------------
def etiquetas_de_bloque(nv: mt.Nivel) -> np.ndarray:
    """Etiqueta del bloque de inferencia de cada par de un nivel (``Nivel.etiquetas["bloque"]`` si existe)."""
    b = np.asarray(nv.bloque)
    etq = nv.etiquetas.get("bloque") if nv.etiquetas else None
    if etq is not None:
        return np.asarray(etq, dtype=object)[b.astype("int64")].astype(str)
    return b.astype(str)


def sumas_de_nivel(nv: mt.Nivel, motores: Sequence[str], ponderacion: str = "poblacion",
                   escala: str = "original") -> bs.SumasBloques:
    """Sumas por bloque de un nivel: ``ponderacion`` «poblacion» (pesos fijos por estación) o «ninguna»;
    ``escala`` «original» (µg/m³ o ppb) o «log» (ẑ frente a log1p(y), promediados en log)."""
    if ponderacion not in ("poblacion", "ninguna") or escala not in ("original", "log"):
        raise ValueError(f"ponderación o escala desconocida: {ponderacion}, {escala}")
    w = None if ponderacion == "ninguna" else np.asarray(nv.poblacion, dtype="float64")
    obs = nv.obs if escala == "original" else nv.log_obs
    fuente = nv.pred if escala == "original" else nv.log
    return bs.SumasBloques.desde_pares(etiquetas_de_bloque(nv), obs, {m: fuente[m] for m in motores}, w)


def evidencia_protocolo(protocolo: str, nivel_e1: mt.Nivel, nivel_e2: mt.Nivel | None = None, *,
                        pares: Mapping | None = None, evaluabilidad: Mapping | None = None,
                        contaminante: str | None = None, regla: ReglaDecision = REGLA,
                        posicion_protocolo: int | None = None, minimo_fraccion: float = mt.MINIMO_FRACCION_PESO_E2,
                        minimo_grupos: int = mt.MINIMO_GRUPOS_E2) -> dict:
    """Evidencia de la decisión en un protocolo, a partir del nivel diario civil de E1 y de E2 sobre los pares de
    la decisión: sumas por bloque de E1 ponderado (original y log) y sin ponderar, y de E2 ponderado, más la
    evaluabilidad de E2, los pares y las semillas. Es JSON y no lleva predicciones."""
    if nivel_e1.nombre != regla.nivel:
        raise ValueError(f"la evidencia es del nivel {regla.nivel}, no de {nivel_e1.nombre}")
    nombres = nombres_de_la_decision(list(nivel_e1.pred), regla)
    if regla.referencia not in nombres:
        raise ValueError("la evidencia necesita las predicciones de LightGBM")
    vistas = {V_E1: sumas_de_nivel(nivel_e1, nombres, "poblacion", "original"),
              V_E1_SIN: sumas_de_nivel(nivel_e1, nombres, "ninguna", "original"),
              V_E1_LOG: sumas_de_nivel(nivel_e1, nombres, "poblacion", "log")}
    if nivel_e2 is not None and len(nivel_e2.obs):
        vistas[V_E2] = sumas_de_nivel(nivel_e2, nombres, "poblacion", "original")
    if evaluabilidad is None:
        if nivel_e2 is None:
            evaluabilidad = {"evaluable": False, "estado": mt.SIN_CONFIRMACION, "motivo": [SIN_BANDERA]}
        else:
            evaluabilidad = mt.evaluabilidad_e2(nivel_e1, nivel_e2, minimo_fraccion, minimo_grupos)
    p = ORDEN_PROTOCOLOS.index(protocolo) if posicion_protocolo is None else int(posicion_protocolo)
    S = vistas[V_E1]
    return {"schema": SCHEMA_EVIDENCIA, "contaminante": contaminante, "protocolo": protocolo, "nivel": regla.nivel,
            "referencia": regla.referencia, "candidatos": {c: prediccion(c) for c in regla.candidatos},
            "formas": dict(FORMAS), "motores": nombres,
            "candidatos_ausentes": [c for c in regla.candidatos if prediccion(c) not in nombres],
            "semilla_bootstrap": bs.semilla_bootstrap(p), "semilla_salvaje": bs.semilla_salvaje(p),
            "bloque_mas_influyente": regla.bloque_mas_influyente.get(protocolo),
            "pares_diarios": {"E1": int(len(nivel_e1.obs)), "E2": int(len(nivel_e2.obs)) if nivel_e2 is not None else 0},
            "G": S.G, "G_efectivo": S.G_efectivo, "evaluabilidad_E2": dict(evaluabilidad),
            "pares": dict(pares) if pares is not None else None,
            "vistas": {k: v.a_dict() for k, v in vistas.items()}}


def huella_evidencia(ev: Mapping) -> str:
    texto = json.dumps(ev, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Condiciones en un protocolo y una forma
# ---------------------------------------------------------------------------
def _signo(x) -> int:
    return int(np.sign(x)) if x is not None and np.isfinite(x) else 0


def _mismo_signo(x, ref) -> bool:
    return _signo(ref) != 0 and _signo(x) == _signo(ref)


def _nmb_pct(S: bs.SumasBloques, nombre: str, replicas: Sequence[int]) -> float:
    return float(np.mean([100.0 * bs.metricas_de(S, bs.nombre_replica(nombre, r))["nmb"] for r in replicas]))


def _r2_por_replica(S: bs.SumasBloques, nombre: str, replicas: Sequence[int]) -> dict:
    return {int(r): bs.metricas_de(S, bs.nombre_replica(nombre, r))["r2"] for r in replicas}


def _superioridad(S: bs.SumasBloques, nombres: Mapping[str, str], ref: str, regla: ReglaDecision, B: int, semilla,
                  semilla_salvaje) -> dict:
    """Condición 1 para los candidatos (la familia de Holm es la de los ``regla.candidatos``): bootstrap percentil
    de Δ̄* con los mismos sorteos para todos y segunda prueba (el cambio de signo del bootstrap salvaje; el jackknife
    CV3 sólo informa), cada una con su Holm. La parte percentil se decide con el **intervalo escalonado publicado**
    (el IC al nivel de Holm de cada candidato excluye 0 a su favor) dentro de la cadena escalonada; se registra si
    coincide con la declaración por el p (con B = 1.999 siempre coincide: Complemento, punto 2)."""
    C = bs.conteos_bootstrap(len(S.bloques), B, semilla)
    filas, p_boot, p_sv = {}, {}, {}
    for c in regla.candidatos:
        nm = nombres[c]
        if nm not in S.motor or ref not in S.motor:
            p_boot[c] = p_sv[c] = float("nan")
            filas[c] = {"presente": False}
            continue
        dist = bs.distribucion_delta(S, nm, ref, C, "delta_r2")
        fin = dist[np.isfinite(dist)]
        sp = bs.segunda_prueba(S, nm, ref, semilla_salvaje=semilla_salvaje, replicas_salvaje=regla.replicas_salvaje)
        sv, jk = sp["salvaje"], sp["jackknife"]
        lo, hi = bs._percentiles(fin, regla.nivel_intervalo) if len(fin) else (np.nan, np.nan)
        p_boot[c] = bs.p_bootstrap(fin)
        p_sv[c] = sv["p"]
        filas[c] = {"presente": True, "ic_inf_95": lo, "ic_sup_95": hi, "p_bootstrap": p_boot[c],
                    "a_favor_bootstrap": bool(len(fin) and np.mean(fin <= 0) < np.mean(fin >= 0)),
                    "replicas_validas_bootstrap": int(len(fin)),
                    "segunda_prueba": sp["prueba_que_decide"], "theta_segunda_prueba": sp["theta"],
                    "p_salvaje": sv["p"], "t_salvaje": sv["t"], "G_salvaje": sv["G"],
                    "distribucion_salvaje": sv["distribucion"], "sorteos_salvaje": str(sv["sorteos"]),
                    "a_favor_salvaje": sp["a_favor_de_a"],
                    "t_jackknife": jk["t"], "gl_jackknife": jk["gl"], "p_jackknife": jk["p"],
                    "_dist": fin}
    hb = bs.holm(p_boot, regla.alfa, regla.m_holm)
    hs = bs.holm(p_sv, regla.alfa, regla.m_holm)
    # Cadena escalonada con el intervalo publicado: por p creciente, el j-ésimo se declara si su IC al nivel
    # 1 − α/(m − j + 1) excluye 0 y se declararon los anteriores (como Holm, en cualquier dirección); la superioridad
    # pide además que lo excluya a favor del candidato.
    orden = sorted(regla.candidatos, key=lambda c: (hb[c]["rango"], regla.candidatos.index(c)))
    seguir, por_intervalo = True, {}
    for c in orden:
        f = filas[c]
        if f["presente"]:
            fin = f.pop("_dist")
            f["ic_inf_holm"], f["ic_sup_holm"] = (bs._percentiles(fin, 1.0 - hb[c]["alfa_holm"]) if len(fin)
                                                  else (np.nan, np.nan))
            lo, hi = f["ic_inf_holm"], f["ic_sup_holm"]
            excluye = bool(np.isfinite(lo) and np.isfinite(hi) and (lo > 0 or hi < 0))
            f["intervalo_holm_excluye_0_a_favor"] = bool(np.isfinite(lo) and lo > 0)
        else:
            excluye = False
            f["intervalo_holm_excluye_0_a_favor"] = False
        seguir = bool(seguir and excluye)
        por_intervalo[c] = seguir
    out = {}
    for c in regla.candidatos:
        f = filas[c]
        f.update({"alfa_holm_bootstrap": hb[c]["alfa_holm"], "declarada_bootstrap": hb[c]["declarada"],
                  "declarada_intervalo_holm": por_intervalo[c],
                  "coinciden_p_e_intervalo": bool(por_intervalo[c] == hb[c]["declarada"]),
                  "alfa_holm_salvaje": hs[c]["alfa_holm"], "declarada_salvaje": hs[c]["declarada"]})
        if f["presente"]:
            f["superioridad"] = bool(por_intervalo[c] and f["intervalo_holm_excluye_0_a_favor"]
                                     and f["declarada_bootstrap"] and f["a_favor_bootstrap"]
                                     and f["declarada_salvaje"] and f["a_favor_salvaje"])
        else:
            f["superioridad"] = False
        out[c] = f
    return out


def evaluar_protocolo(ev: Mapping, forma: str = FORMA_PRIMARIA, *, regla: ReglaDecision = REGLA,
                      replicas: int | None = None) -> dict:
    """Condiciones 1–5 y 7 de cada candidato en un protocolo con una forma de retransformación (la 6 compara las
    dos formas y la aplica ``decidir_motor``). Devuelve, por candidato, cada condición y sus estadísticos."""
    if forma not in FORMAS:
        raise ValueError(f"forma desconocida: {forma!r}")
    sufijo = FORMAS[forma]
    vistas = {k: bs.SumasBloques.desde_dict(v) for k, v in ev["vistas"].items()}
    S = vistas[V_E1]
    ref = con_forma(regla.referencia, sufijo)
    nombres = {c: con_forma(prediccion(c), sufijo) for c in regla.candidatos}
    B = int(replicas or regla.replicas_bootstrap)
    semilla, semilla_sv = ev["semilla_bootstrap"], ev["semilla_salvaje"]
    sup = _superioridad(S, nombres, ref, regla, B, semilla, semilla_sv)
    prot = ev["protocolo"]
    bloque = regla.bloque_mas_influyente.get(prot)
    if bloque is not None and S.tiene_bloque(bloque) and len(S.bloques) > 2:
        S_sin = S.quitar([bloque])
        sup_sin = _superioridad(S_sin, nombres, ref, regla, B, semilla, semilla_sv)
        estado_infl = f"sin el bloque {bloque}"
    else:
        S_sin, sup_sin = None, sup
        estado_infl = (f"el bloque {bloque} no tiene pares de la decisión: quitarlo no cambia nada"
                       if bloque is not None else "el protocolo no nombra un bloque más influyente")
    ev_e2 = ev.get("evaluabilidad_E2") or {"evaluable": False, "estado": mt.SIN_CONFIRMACION, "motivo": [SIN_BANDERA]}
    S2 = vistas.get(V_E2)
    e2_evaluable = bool(ev_e2.get("evaluable")) and S2 is not None
    out = {}
    for c in regla.candidatos:
        nm = nombres[c]
        base = {"candidato": c, "motor": nm, "referencia": ref, "forma": forma, "protocolo": prot,
                "bloque_influyente": bloque, "estado_influencia": estado_infl, "estado_E2": ev_e2.get("estado"),
                **{k: v for k, v in sup[c].items()}}
        if not sup[c]["presente"]:
            out[c] = {**base, **{k: False for k in CONDICIONES if k != "misma_decision_con_lognormal"},
                      "pasa_sin_c6": False, "motivo": "sin predicciones del candidato en la evidencia"}
            continue
        R = bs.replicas_comunes(S.motores(), nm, ref)
        d = bs.deltas_por_replica(S, nm, ref, "delta_r2")
        dbar = float(np.mean(list(d.values())))
        completas = bs.replicas_completas(d)                     # exige las 3 réplicas comunes (Complemento, punto 6)
        ruido = bs.ruido_de_las_replicas(d)
        c2 = bs.supera_ruido(dbar, ruido) if completas else None
        d_e2 = bs.delta_medio(S2, nm, ref) if S2 is not None and nm in S2.motor and ref in S2.motor else float("nan")
        c3 = _mismo_signo(d_e2, dbar) if e2_evaluable else True
        d_sin = bs.delta_medio(vistas[V_E1_SIN], nm, ref)
        d_log = bs.delta_medio(vistas[V_E1_LOG], nm, ref)
        c5 = _mismo_signo(d_sin, dbar) and _mismo_signo(d_log, dbar)
        nmb_c, nmb_ref = _nmb_pct(S, nm, R), _nmb_pct(S, ref, R)
        c7 = bool(np.isfinite(nmb_c) and np.isfinite(nmb_ref) and abs(nmb_c) <= abs(nmb_ref) + regla.margen_nmb_pp)
        r2_c, r2_ref = _r2_por_replica(S, nm, R), _r2_por_replica(S, ref, R)
        fila = {**base, "replicas": R, "replicas_completas": completas, "delta_r2": dbar,
                **{f"delta_r2_r{r}": d.get(r, np.nan) for r in bs.REPLICAS_DEL_RUIDO},
                "ruido": ruido, "delta_r2_E2": d_e2, "e2_evaluable": e2_evaluable,
                "delta_r2_sin_bloque_influyente": (bs.delta_medio(S_sin, nm, ref) if S_sin is not None else dbar),
                "delta_r2_sin_ponderar": d_sin, "delta_r2_log": d_log, "nmb_candidato_pct": nmb_c,
                "nmb_referencia_pct": nmb_ref, "r2_candidato": float(np.mean(list(r2_c.values()))),
                "r2_referencia": float(np.mean(list(r2_ref.values()))), "r2_candidato_por_replica": r2_c,
                "superioridad": sup[c]["superioridad"], "ruido_de_la_diferencia": c2,
                "consistencia_con_E2": c3, "influencia": bool(sup_sin[c]["superioridad"]),
                "signo_sin_ponderar_y_en_log": c5, "no_inferioridad_en_sesgo": c7}
        fila["pasa_sin_c6"] = bool(fila["superioridad"] and c2 is True and c3 and fila["influencia"] and c5 and c7)
        fila["motivo"] = _motivo(fila)
        out[c] = fila
    return {"protocolo": prot, "forma": forma, "G": S.G, "G_efectivo": S.G_efectivo, "bloques": [str(x) for x in S.bloques],
            "estado_influencia": estado_infl, "evaluabilidad_E2": ev_e2, "candidatos": out}


def _motivo(f: Mapping) -> str:
    """Las condiciones que no cumple (texto para el registro)."""
    faltan = []
    if not f["superioridad"]:
        faltan.append("1 (superioridad con Holm, el intervalo escalonado y el cambio de signo)")
    if f["ruido_de_la_diferencia"] is None:
        faltan.append(f"2 (ruido no evaluado: exige las {bs.REPLICAS_EXIGIDAS} réplicas comunes y hay "
                      f"{len(f.get('replicas', []))})")
    elif not f["ruido_de_la_diferencia"]:
        faltan.append("2 (|Δ̄| no supera el ruido de la diferencia)")
    if not f["consistencia_con_E2"]:
        faltan.append("3 (E2 con otro signo)")
    if not f["influencia"]:
        faltan.append("4 (sin superioridad al quitar el bloque más influyente: no robusta)" if f["superioridad"]
                      else "4 (sin superioridad al quitar el bloque más influyente)")
    if not f["signo_sin_ponderar_y_en_log"]:
        faltan.append("5 (el signo no se repite sin ponderar o en log)")
    if not f["no_inferioridad_en_sesgo"]:
        faltan.append("7 (|NMB| supera al de LightGBM en más de 1 punto porcentual)")
    return "cumple 1–5 y 7" if not faltan else "no cumple " + "; ".join(faltan)


# ---------------------------------------------------------------------------
# Factibilidad, desempate y decisión
# ---------------------------------------------------------------------------
def _segundos_por_contaminante(motor: str, v, regla: ReglaDecision) -> tuple[dict, dict]:
    """Segundos por día de superficies de un motor en cada contaminante (la media de los días medidos si viene una
    lista) y lo que traiga además la fuente. Acepta ``{pol: s}`` o ``{"segundos_por_dia": {pol: s}, …}``."""
    extra = {}
    if isinstance(v, Mapping) and "segundos_por_dia" in v:
        extra = {k: x for k, x in v.items() if k != "segundos_por_dia"}
        v = v["segundos_por_dia"]
    if not isinstance(v, Mapping):
        raise ValueError(f"factibilidad de {motor}: hacen falta los segundos por día de cada contaminante "
                         f"{list(regla.contaminantes_factibilidad)} (Complemento, punto 3: se suman los dos)")
    out = {}
    for pol in regla.contaminantes_factibilidad:
        x = v.get(pol)
        if x is None:
            raise ValueError(f"falta el tiempo medido de predecir un día de superficies de {pol} con {motor} "
                             f"(factibilidad, Complemento, punto 3)")
        dias = np.atleast_1d(np.asarray(x, dtype="float64"))
        if len(dias) == 0 or not np.isfinite(dias).all() or (dias < 0).any():
            raise ValueError(f"factibilidad de {motor} en {pol}: tiempos inválidos {x!r}")
        out[pol] = float(dias.mean())                     # la media de los 3 días medidos
    return out, extra


def evaluar_factibilidad(factibilidad: Mapping | None, regla: ReglaDecision = REGLA) -> dict:
    """Factibilidad de producción de cada candidato (Complemento de la Enmienda 1, punto 3; reemplaza la del punto
    11; irrevisable).

    ``factibilidad``: ``{motor: {pol: segundos por día de superficies}}`` (o ``{motor: {"segundos_por_dia": {pol:
    s}, …}}``; cada valor puede ser la lista de los 3 días medidos) para LightGBM y los motores únicos candidatos,
    medidos antes de cualquier ajuste comparativo con los predictores de producción. Por contaminante, la producción
    2000–2026 cuesta los segundos por día × los días del calendario; se suman los dos contaminantes. El promedio
    simple cuesta la suma de sus miembros (un valor propio del promedio, si viene, sólo se registra). Un candidato
    es factible si cuesta ≤ ``factor_maximo_frente_a_lightgbm`` veces lo que LightGBM y ≤ ``umbral_dias_maquina``
    días de máquina; LightGBM es la referencia y la regla no lo excluye. Sin la medición, error."""
    if factibilidad is None:
        raise ValueError("falta la factibilidad: el tiempo de predecir un día completo de superficies con cada "
                         "candidato y con LightGBM compilado se mide antes de cualquier ajuste comparativo "
                         "(Complemento de la Enmienda 1, punto 3)")
    unicos = [c for c in regla.candidatos if c != UNICO_FRENTE_A]
    motores = list(dict.fromkeys([regla.referencia, *unicos, *regla.miembros_promedio]))
    medido, fuentes = {}, {}
    for m in motores:
        if m not in factibilidad:
            raise ValueError(f"falta el tiempo medido de predecir un día de superficies con {m} (factibilidad)")
        medido[m], fuentes[m] = _segundos_por_contaminante(m, factibilidad[m], regla)
    dias = float(regla.dias_produccion)

    def costo(segundos: Mapping[str, float]) -> float:            # segundos de máquina, 2000–2026, los dos contaminantes
        return float(sum(segundos[pol] * dias for pol in regla.contaminantes_factibilidad))

    ref_s = costo(medido[regla.referencia])
    out = {"_referencia": {"motor": regla.referencia, "segundos_por_dia": medido[regla.referencia],
                           "segundos_produccion": ref_s, "dias_de_maquina": ref_s / SEGUNDOS_POR_DIA,
                           "nota": "LightGBM es la referencia: la regla no lo excluye"}}
    for c in regla.candidatos:
        if c == UNICO_FRENTE_A:
            seg = {pol: float(sum(medido[m][pol] for m in regla.miembros_promedio))
                   for pol in regla.contaminantes_factibilidad}
            extra = {"miembros": list(regla.miembros_promedio),
                     "regla": "cuesta la suma de sus miembros (Complemento, punto 3)"}
            if c in factibilidad:
                extra["informado"] = _limpio(factibilidad[c])
        else:
            seg, extra = medido[c], fuentes[c]
        s = costo(seg)
        dias_m = s / SEGUNDOS_POR_DIA
        cociente = s / ref_s if ref_s > 0 else float("inf")
        motivos = []
        if not cociente <= regla.factor_maximo_frente_a_lightgbm:
            motivos.append(f"cuesta {cociente:.2f} veces lo que LightGBM compilado "
                           f"(> {regla.factor_maximo_frente_a_lightgbm:g})")
        if not dias_m <= regla.umbral_dias_maquina:
            motivos.append(f"la producción 2000–2026 de los dos contaminantes tomaría {dias_m:.2f} días de máquina "
                           f"(> {regla.umbral_dias_maquina:g})")
        factible = not motivos
        out[c] = {"segundos_por_dia": seg, "dias_de_produccion": int(regla.dias_produccion),
                  "contaminantes": list(regla.contaminantes_factibilidad), "segundos_produccion": s,
                  "dias_de_maquina": dias_m, "cociente_frente_a_lightgbm": cociente,
                  "factor_maximo_frente_a_lightgbm": float(regla.factor_maximo_frente_a_lightgbm),
                  "umbral_dias_de_maquina": float(regla.umbral_dias_maquina),
                  "hilos": int(regla.hilos_factibilidad), "factible": factible,
                  "motivo": "" if factible else "; ".join(motivos) + ": fuera de la decisión"}
        if extra:
            out[c]["fuente"] = _limpio(extra)
            marca = (extra.get("factibilidad_v2") or {}).get("fuera_de_la_decision") if isinstance(extra, Mapping) else None
            if marca is not None:                    # la marca de factibilidad_v2 frente a la de aquí
                out[c]["coincide_con_factibilidad_v2"] = bool(marca) == (not factible)
    return out


def _desempate(elegibles: Sequence[str], por_prot: Mapping[str, Mapping], fac: Mapping[str, Mapping],
               regla: ReglaDecision) -> dict:
    """Mayor media simple de los dos R²; empatan con el primero los que no superan el ruido de la diferencia (el
    rango entre las 3 réplicas comunes); entre ellos, un motor único antes que el promedio simple y después el más
    barato de producir. Con menos de 3 réplicas comunes el desempate queda «no evaluado» y no da el reemplazo
    (Complemento, punto 6)."""
    if not elegibles:
        return {"elegido": regla.referencia, "elegibles": [], "motivo": "ningún candidato cumple la regla: se mantiene LightGBM"}
    puntaje, por_replica = {}, {}
    for c in elegibles:
        filas = [por_prot[p]["candidatos"][c] for p in regla.protocolos]
        puntaje[c] = float(np.mean([f["r2_candidato"] for f in filas]))
        comunes = sorted(set.intersection(*(set(f["r2_candidato_por_replica"]) for f in filas)))
        por_replica[c] = {r: float(np.mean([f["r2_candidato_por_replica"][r] for f in filas])) for r in comunes}
    orden = sorted(elegibles, key=lambda c: (-puntaje[c], regla.candidatos.index(c)))
    primero = orden[0]
    if len(orden) == 1:
        return {"elegido": primero, "elegibles": list(elegibles), "puntaje_media_de_los_dos_r2": puntaje,
                "primero_por_puntaje": primero, "diferencias_con_el_primero": {}, "empatados": [primero],
                "desempate_evaluado": True, "motivo": "único candidato que cumple la regla"}
    empates, diferencias, sin_replicas = [primero], {}, []
    for c in orden[1:]:
        comunes = sorted(set(por_replica[primero]) & set(por_replica[c]))
        d_r = {r: por_replica[primero][r] - por_replica[c][r] for r in comunes}
        dbar = float(np.mean(list(d_r.values()))) if d_r else float("nan")
        completas = bs.replicas_completas(d_r)
        ruido = bs.ruido_de_las_replicas(d_r)
        empata = bool(completas and np.isfinite(ruido) and np.isfinite(dbar) and not abs(dbar) > ruido)
        diferencias[c] = {"diferencia_media": dbar, "por_replica": [d_r[r] for r in comunes], "replicas": comunes,
                          "ruido": ruido, "empata_con_el_primero": empata if completas else None}
        if not completas:
            sin_replicas.append(c)
        elif empata:
            empates.append(c)
    base = {"elegibles": list(elegibles), "puntaje_media_de_los_dos_r2": puntaje, "primero_por_puntaje": primero,
            "diferencias_con_el_primero": diferencias}
    if sin_replicas:
        return {**base, "elegido": regla.referencia, "empatados": [], "desempate_evaluado": False,
                "motivo": (f"desempate no evaluado: {', '.join(sin_replicas)} no tiene las {regla.replicas_exigidas} "
                           f"réplicas comunes con {primero}; no da el reemplazo y se mantiene LightGBM "
                           f"(Complemento, punto 6)")}
    if len(empates) == 1:
        elegido, motivo = primero, "mayor media simple de los dos R²"
    else:
        unicos = [c for c in empates if c != UNICO_FRENTE_A] or list(empates)
        elegido = min(unicos, key=lambda c: (fac[c]["segundos_produccion"], -puntaje[c], regla.candidatos.index(c)))
        motivo = ("diferencias menores que el ruido: motor único antes que el promedio simple y después el más "
                  "barato de producir")
    return {**base, "elegido": elegido, "empatados": empates, "desempate_evaluado": True, "motivo": motivo}


def _limpio(o):
    """Convierte a tipos de JSON (numpy, NaN → None, claves a texto)."""
    if isinstance(o, Mapping):
        return {str(k): _limpio(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_limpio(v) for v in o]
    if isinstance(o, np.ndarray):
        return [_limpio(v) for v in o.tolist()]
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return float(o) if np.isfinite(o) else None
    return o


COLUMNAS_TABLA = (
    "contaminante", "protocolo", "forma", "candidato", "motor", "referencia", "presente", "factible", "G", "G_efectivo",
    "delta_r2", "delta_r2_r0", "delta_r2_r1", "delta_r2_r2", "replicas_completas", "ruido", "ic_inf_95", "ic_sup_95",
    "p_bootstrap", "alfa_holm_bootstrap", "ic_inf_holm", "ic_sup_holm", "declarada_bootstrap", "a_favor_bootstrap",
    "intervalo_holm_excluye_0_a_favor", "declarada_intervalo_holm", "coinciden_p_e_intervalo",
    "segunda_prueba", "theta_segunda_prueba", "p_salvaje", "t_salvaje", "G_salvaje", "distribucion_salvaje",
    "sorteos_salvaje", "alfa_holm_salvaje", "declarada_salvaje", "a_favor_salvaje",
    "t_jackknife", "gl_jackknife", "p_jackknife",
    "delta_r2_E2", "e2_evaluable", "estado_E2",
    "bloque_influyente", "estado_influencia", "delta_r2_sin_bloque_influyente", "delta_r2_sin_ponderar",
    "delta_r2_log", "nmb_candidato_pct", "nmb_referencia_pct", "r2_candidato", "r2_referencia",
    *COLUMNA_CONDICION.values(), "pasa_sin_c6", "pasa", "motivo")


def decidir_motor(evidencias: Mapping[str, Mapping], factibilidad: Mapping | None, *,
                  regla: ReglaDecision | None = None, replicas: int | None = None, traza: Mapping | None = None,
                  contaminante: str | None = None) -> tuple[pd.DataFrame, dict]:
    """Aplica la regla cerrada del punto 11 (con su Complemento) a la evidencia de LRO y BLQ-75 de un contaminante.
    ``factibilidad`` es la de los dos contaminantes (``evaluar_factibilidad``): la misma para las dos decisiones.
    Devuelve la tabla (candidato × protocolo × forma) y el registro JSON trazado; el motor elegido está en
    ``registro["decision"]["motor"]``."""
    regla = regla or REGLA
    faltan = [p for p in regla.protocolos if p not in evidencias]
    if faltan:
        raise ValueError(f"falta la evidencia de {faltan}: consolida antes esos protocolos")
    pols = {evidencias[p].get("contaminante") for p in regla.protocolos} - {None}
    if len(pols) > 1:
        raise ValueError(f"la evidencia mezcla contaminantes: {sorted(pols)}")
    contaminante = contaminante or (pols.pop() if pols else None)
    for p in regla.protocolos:
        ev = evidencias[p]
        if ev.get("schema") != SCHEMA_EVIDENCIA or ev.get("protocolo") != p or ev.get("nivel") != regla.nivel:
            raise ValueError(f"evidencia de {p} inválida (schema, protocolo o nivel); reconsolida el protocolo")
        pos = ORDEN_PROTOCOLOS.index(p)
        if (list(ev.get("semilla_bootstrap") or []) != bs.semilla_bootstrap(pos)
                or list(ev.get("semilla_salvaje") or []) != bs.semilla_salvaje(pos)):
            raise ValueError(f"evidencia de {p} con otras semillas ({ev.get('semilla_bootstrap')}, "
                             f"{ev.get('semilla_salvaje')}): la decisión usa [42, 2000, p] y [42, 3000, p]")
    fac = evaluar_factibilidad(factibilidad, regla)
    res = {f: {p: evaluar_protocolo(evidencias[p], f, regla=regla, replicas=replicas) for p in regla.protocolos}
           for f in FORMAS}
    otra = {FORMA_PRIMARIA: FORMA_FIJA, FORMA_FIJA: FORMA_PRIMARIA}
    # --- Elegibles y elección con cada forma (condición 6: las dos deben elegir el mismo motor) ---
    eleccion = {}
    for f in FORMAS:
        elegibles = [c for c in regla.candidatos if fac[c]["factible"]
                     and all(res[f][p]["candidatos"][c]["pasa_sin_c6"] for p in regla.protocolos)]
        eleccion[f] = _desempate(elegibles, res[f], fac, regla)
    coinciden = eleccion[FORMA_PRIMARIA]["elegido"] == eleccion[FORMA_FIJA]["elegido"]
    motor = eleccion[FORMA_PRIMARIA]["elegido"] if coinciden else regla.referencia
    sin_desempate = [f for f in FORMAS if eleccion[f].get("desempate_evaluado") is False]
    if motor != regla.referencia:
        motivo = (f"{motor} cumple las siete condiciones en {' y '.join(regla.protocolos)} y las dos correcciones "
                  f"lo eligen ({eleccion[FORMA_PRIMARIA]['motivo']})")
    elif sin_desempate:
        motivo = (f"varios candidatos cumplen la regla pero el desempate no se pudo evaluar con {', '.join(sin_desempate)} "
                  f"({eleccion[sin_desempate[0]]['motivo']})")
    elif not coinciden:
        motivo = (f"las dos correcciones no eligen el mismo motor ({FORMA_PRIMARIA}: "
                  f"{eleccion[FORMA_PRIMARIA]['elegido']}; {FORMA_FIJA}: {eleccion[FORMA_FIJA]['elegido']}): se "
                  f"mantiene LightGBM (condición 6, regla previa del punto 2)")
    else:
        motivo = "ningún candidato cumple la regla en los dos protocolos con las dos correcciones: se mantiene LightGBM"
    candidato_elegido = next((c for c in regla.candidatos if c == motor), None)
    # --- Por candidato: condición 6, evidencia parcial y estado ---
    resumen, parciales, filas = {}, [], []
    for c in regla.candidatos:
        pasa = {p: {f: bool(res[f][p]["candidatos"][c]["pasa_sin_c6"] and res[otra[f]][p]["candidatos"][c]["pasa_sin_c6"])
                    for f in FORMAS} for p in regla.protocolos}
        superior = [p for p in regla.protocolos if pasa[p][FORMA_PRIMARIA]]
        no_inferior = [p for p in regla.protocolos
                       if res[FORMA_PRIMARIA][p]["candidatos"][c].get("presente")
                       and np.isfinite(res[FORMA_PRIMARIA][p]["candidatos"][c]["ic_sup_95"])
                       and res[FORMA_PRIMARIA][p]["candidatos"][c]["ic_sup_95"] >= 0]
        parcial = bool(len(superior) == 1 and any(p in no_inferior for p in regla.protocolos if p not in superior))
        if parcial:
            parciales.append(c)
        presente = all(res[FORMA_PRIMARIA][p]["candidatos"][c].get("presente") for p in regla.protocolos)
        if c == candidato_elegido:
            estado = "reemplaza a LightGBM"
        elif not presente:
            estado = "sin evidencia en algún protocolo"
        elif not fac[c]["factible"]:
            estado = "fuera de la decisión por factibilidad"
        elif len(superior) == len(regla.protocolos):
            if sin_desempate and motor == regla.referencia:
                estado = "cumple la regla, pero el desempate no se pudo evaluar (faltan réplicas comunes)"
            elif coinciden or motor != regla.referencia:
                estado = "cumple la regla pero pierde el desempate"
            else:
                estado = "cumple la regla, pero las dos correcciones no eligen el mismo motor"
        elif parcial:
            estado = "evidencia parcial"
        else:
            estado = "no cumple la regla"
        resumen[c] = {"prediccion": prediccion(c), "factibilidad": fac[c], "pasa_las_siete": pasa,
                      "superior_en": superior, "no_inferior_en": no_inferior, "evidencia_parcial": parcial,
                      "sensibilidad_de_exposicion": bool(parcial and fac[c]["factible"]), "estado": estado,
                      "motivo_por_protocolo": {p: {f: res[f][p]["candidatos"][c]["motivo"] for f in FORMAS}
                                               for p in regla.protocolos}}
        for f in FORMAS:
            for p in regla.protocolos:
                x = res[f][p]["candidatos"][c]
                fila = {"contaminante": contaminante, "protocolo": p, "forma": f, "candidato": c,
                        "factible": fac[c]["factible"], "G": res[f][p]["G"], "G_efectivo": res[f][p]["G_efectivo"],
                        **{k: v for k, v in x.items() if k in COLUMNAS_TABLA}}
                for cond, col in COLUMNA_CONDICION.items():
                    if cond == "misma_decision_con_lognormal":
                        fila[col] = bool(res[otra[f]][p]["candidatos"][c]["pasa_sin_c6"])
                    else:
                        v = x.get(cond)
                        fila[col] = v if v is None else bool(v)
                fila["pasa"] = pasa[p][f]
                filas.append(fila)
    tabla = pd.DataFrame(filas)
    for col in COLUMNAS_TABLA:
        if col not in tabla.columns:
            tabla[col] = np.nan
    tabla = tabla[list(COLUMNAS_TABLA)]
    # --- Informes por protocolo: pares, E2, influencia y Δ̄ sin cada bloque ---
    protocolos = {}
    for p in regla.protocolos:
        ev = evidencias[p]
        S = bs.SumasBloques.desde_dict(ev["vistas"][V_E1])
        sin_cada = {}
        for c in regla.candidatos:
            nm, ref = prediccion(c), regla.referencia
            if nm in S.motor and ref in S.motor:
                t = bs.delta_sin_cada_bloque(S, nm, ref, "delta_r2")
                sin_cada[c] = t.to_dict(orient="records")
        protocolos[p] = {"G": S.G, "G_efectivo": S.G_efectivo, "bloques": [str(x) for x in S.bloques],
                         "pares_diarios": ev.get("pares_diarios"), "pares_de_la_decision": ev.get("pares"),
                         "evaluabilidad_E2": ev.get("evaluabilidad_E2"),
                         "influencia": {"bloque": regla.bloque_mas_influyente.get(p),
                                        "estado": res[FORMA_PRIMARIA][p]["estado_influencia"]},
                         "delta_r2_sin_cada_bloque": sin_cada,
                         "semillas": {"bootstrap": ev["semilla_bootstrap"], "salvaje": ev["semilla_salvaje"]},
                         "evidencia": {"schema": ev.get("schema"), "sha256": huella_evidencia(ev)}}
    registro = {"schema": SCHEMA_DECISION, "contaminante": contaminante,
                "decision": {"motor": motor, "candidato": candidato_elegido,
                             "reemplaza_a_lightgbm": motor != regla.referencia, "motivo": motivo,
                             "coinciden_las_formas": coinciden, "por_forma": eleccion},
                "candidatos": resumen, "evidencia_parcial": parciales, "protocolos": protocolos,
                "factibilidad": {"referencia": fac["_referencia"],
                                 "regla": (f"factible si la producción 2000–2026 de {' y '.join(regla.contaminantes_factibilidad)} "
                                           f"cuesta ≤ {regla.factor_maximo_frente_a_lightgbm:g} veces la de LightGBM "
                                           f"compilado y ≤ {regla.umbral_dias_maquina:g} días de máquina con "
                                           f"{regla.hilos_factibilidad} hilos; el promedio simple cuesta la suma de sus "
                                           f"miembros (Complemento, punto 3; irrevisable)")},
                "regla": {**regla.como_dict(), "condiciones": list(CONDICIONES),
                          "estadistico": "ΔR² diario civil, ponderado con los pesos fijos por estación, sobre E1, "
                                         "smearing_duan; Δ̄ = media de las réplicas",
                          "segunda_prueba": ("cambio de signo del bootstrap salvaje por bloque (decide: Webb y 9.999 "
                                             "sorteos con G < 12, Rademacher con enumeración completa con 12 ≤ G ≤ 16 y "
                                             "con 9.999 sorteos con G > 16; semilla [42, 3000, p]); jackknife CV3 con t "
                                             "de G − 1 gl (sólo informa) (Complemento, punto 1)"),
                          "holm": ("escalonado sobre los 4 candidatos, por contaminante y protocolo, aparte para cada "
                                   "prueba; la parte percentil decide con el intervalo escalonado publicado (B = 1.999: "
                                   "coincide con el p; Complemento, punto 2)"),
                          "replicas": (f"la condición 2 y el desempate exigen las {regla.replicas_exigidas} réplicas "
                                       f"comunes; con menos, «no evaluada» y sin reemplazo (Complemento, punto 6)"),
                          "evidencia_parcial": "superior (siete condiciones) en un protocolo y, en el otro, IC del 95 % "
                                               "sin ajustar que no excluye 0 en contra del candidato (Complemento, 4.7)"},
                "replicas_bootstrap": int(replicas or regla.replicas_bootstrap),
                "traza": dict(traza or {})}
    return tabla, _limpio(registro)
