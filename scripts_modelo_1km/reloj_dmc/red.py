"""Controles de red A1 a A7, calibración de E3t, G-dup, cambio del portal y descripción de la red
(§5.4, §4.3.3, §5.3.6). Ninguna muestra mira veredictos.

- A1, A2: antes de leer la DMC; si fallan, la corrida no lee ningún artefacto (lo hace cumplir el
  ejecutable; aquí sólo se juzga).
- A3, A5 y calibración de E3t (``controles_red``, fase 5 de §5.2): con los estados y métricas de la fase
  4; arman tipos.ConsecuenciasRed sin A4.
- A4 (fase 7): fracción de T-P que falla entre los estación-años en que se evalúa; ``fijar_a4`` completa
  las consecuencias.
- A6: D1 contrarios del registro documental (con E5 inactiva antes de C4, no hace nada).
- A7: lo detecta politica.verificar_politica; aquí sólo se resume (``a7``).
- G-dup, cambio del portal, descripción de la red y predicciones de §1.13: sólo describen.
Los esquemas de las muestras de A3 y A5, de la calibración y de G-dup viven en tipos desde la ola 4b; los
nombres de aquí son alias de los mismos objetos.
Depende de: tipos, numerico, umbrales, constantes, tablas, lineas_fisicas (e3p_anual) y lineas_registro
(clase de E2, id de evento y resultado de E1b, para §1.13).

Lecturas propias de este módulo (van al addendum de C1):
- RED-1. A3 con menos de A3_MIN_REGIMENES años-régimen, en el país o en una macrozona, no se evalúa y
  no falla. Con la otra lectura, Magallanes (sin muestra, porque |lat| > A3_LAT_MAX) perdería E4p
  siempre, contra §6 («F(0) puede confirmarse con E3p y E4p»). En E3t no cambia nada: una macrozona
  con menos de CAL_E3T_MIN estación-años queda restringida igual.
- RED-2. «E3p filtrada evaluable» (A3 y A5) = año-régimen de QFE con ĉ^f_cont definido, ≥
  E3_PARES_REGIMEN pares y máx r^f ≥ E3_RMAX (R-41). «E4p evaluable» = la fila de E4p del año-régimen
  no es «sin información» para alguna H (compatible, incompatible o dudosa; LF-11) y ψ2 es finito.
  En A3, ĉ^f_cont, ĉS2_cont = ψ2 − E4P_S2_FASE_H y D se envuelven a [−6, 6) (período 12 h).
- RED-3. A5: m = media circular de período 1 h, llevada a [−0,5; 0,5). Si la resultante es nula, m
  queda indefinida y no hay alto (se informa).
- RED-4. Calibración de E3t:
  - entran los años-régimen de Ts con ≥ E3_PARES_REGIMEN pares, filtro aprobado y ĉt_cont definido
    (sin ĉt_cont no hay δt; como R-46 en T-P). No se exige máx r ≥ E3_RMAX, porque el texto no lo pide;
  - «E3p y E4p compatibles con una misma H»: H de P con E3p anual compatible (lineas_fisicas.e3p_anual,
    con la fina apagada donde falla A3 o donde la estación la apagó, como en decision) y E4p anual
    compatible. Si hay varias H y difieren en c_H(R) en algún año-régimen usado, el estación-año queda
    fuera («H ambigua») y se informa;
  - δt = mediana de ĉt_cont − c_H(R), sin envolver (como δt_R de T-P);
  - el criterio usa todos los estación-años de la muestra; la tabla publicada trae el estado de T-P
    bajo H (falla > pasa > no_evaluable) y el resumen da también las cuentas sin las que fallan T-P.
  - c_H(R) sale de ``evidencia.clases`` (año → ClaseH) si la interfaz común lo agrega; si no, de
    tablas.regimenes_del_anio con el calendario que se pasa (o el de tablas.cargar_tablas()).
- RED-5. A4: «en que se evalúa» = DecisionAnio.guardas["T-P"] ∈ {pasa, falla}; decision deja
  «no_evaluable» cuando no se cumplen las condiciones de año (K = {H} y E3p compatible). Sin
  estación-años evaluados, A4 no restringe.
- RED-6. A6: cuenta una línea del registro con ``nivel = "D1"``, ``estado`` distinto de «pendiente» y
  cita literal. Declara un reloj (``reloj_declarado``, id de hipótesis) y un alcance (``alcance``:
  ``estaciones`` [códigos] y ``anio_desde``/``anio_hasta``; lo que falte no limita). Contradice a un
  estación-año confirmado si su clase no contiene ese reloj. Un D1 sin cita literal o sin reloj
  declarado es un registro mal formado y lanza error (§4.5: «sin cita literal no se asigna nivel»).
- RED-7. G-dup: cada aparición del mensaje en una copia es un caso. La estación y el mes salen de la
  primera URL «…/hojaMensualDatos/<código>/<año>/<mes>» (REPORT_PATH del descargador) que sigue al
  mensaje en la misma línea; sin URL, el caso se lista sin estación ni mes. «Atraso de alguna zona de
  Zs» = un cambio de tipo atraso cuya etiqueta repetida cae en ese mes; sin las Zs de la estación, se
  miran todas las zonas del Anexo A. Las copias se leen sólo fuera de /Volumes y en la tabla va sólo el
  nombre del archivo (§7.4, privacidad).
- RED-8. Cambio del portal (§5.3.6, R-26): un cambio es el paso entre dos rachas consecutivas de una
  estación cuya intersección de clases es vacía (aceptadas o no); su mes es el primer mes con datos del
  primer año de la racha posterior. El denominador son las estaciones con datos en ese mes.
- RED-9. Descripción de la red (§5.4):
  - «con datos» = algún mes con artefacto evaluado (``meses.entra``) o algún año con veredicto distinto
    de «sin_datos»;
  - las proporciones de estación-horas de cada categoría son las horas de las estaciones de esa
    categoría sobre el total de N; las categorías se solapan;
  - «inestable» = alguna decisión o racha con motivo «inestable», o ≥ INESTABLE_ANIOS años discrepantes
    (sin los de reglas vencidas) que son más del INESTABLE_PCT de sus años con datos (§5.3.1; así cuenta
    también una estación inestable sin años confirmados);
  - «estación-horas en tramos F(0)» = horas de los meses con regla de clase F(0)
    (``meses_con_regla``, de decision.rachas). Sin ``meses_con_regla`` la primera condición no se
    cumple y no hay afirmación;
  - «estación-años evaluados» = los de veredicto distinto de «sin_datos».
- RED-10. Predicciones de §1.13 (``predicciones``; descriptivas, nunca desviación). Sólo N y sólo los
  estación-años con veredicto distinto de «sin_datos»; cada bloque (F(0), F(−4), C(Santiago)) se mide con lo
  que ese reloj predice, y c_H(R) sale como en RED-4. Los porcentajes son constantes del cuerpo
  (constantes.PRED_*); la clase de E2 y el ĉ esperados se derivan del reloj (j* = c_H(R) mód 3, ĉ = c_H(R)).
  - E1a «presente»: adelantos reales de todas las zonas de Zs, presentes / evaluables (presente o ausente);
  - E2: partes informativas con j* definido; la de C(Santiago) se informa por desfase (verano −3, invierno −4);
  - E3p con ĉ: un estación-año entra si E3p (QFE, regla gruesa) tiene ĉ definido en algún año-régimen, y
    cumple si ĉ = c_H(R) en todos ésos; para F(0), además E4p anual compatible con F(0);
  - E1b: «aeródromo de operación civil» = estación con algún cambio real evaluado con |δ| = 1 (δ = 0 no
    informa, §4.1.2); cumple si todos sus δ informativos son −1;
  - guardas: las de §5.1 y G-versión precalculadas bajo H o «*»; un estación-año entra si alguna pasa o falla
    y cuenta si alguna falla. A3 y A5 salen de las consecuencias (sin ellas, «sin_datos»);
  - patrón civil de E1a (zona de C(Santiago)): estaciones con algún adelanto real evaluable; hay patrón si un
    evento ausente deja a C(Z) compatible en E1a, que sólo pasa con el patrón (§4.1.1), sin copiar su regla.
    «Placebos ≤ 10 %» = placebos ausentes / placebos evaluables de esas estaciones, juntos. Los eventos de
    regla vencida (clase «regla_vencida», Enmienda 3, E3-2) no son placebos del patrón civil: los placebos son
    los del mismo día de la semana y los del A2, como en lineas_registro (lectura 9);
  - regla fina: años-régimen finos con ĉ^f definido, donde la fina rige (A3 y apagado de estación);
  - sin porcentaje en el texto (E1b, la E2 civil y la fina), la predicción es universal: se cumple si la
    cumplen todas las unidades evaluables. Sin unidades evaluables queda «sin_datos», sin juicio.
"""
from __future__ import annotations

import functools
import re
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from reloj_dmc import constantes, lineas_fisicas, lineas_registro, numerico, tipos
from reloj_dmc import tablas as mod_tablas
from reloj_dmc.tipos import (ESQUEMA_HORAS, ESQUEMA_METRICAS_E3, ESQUEMA_METRICAS_E4, ESQUEMA_RACHAS, ZONAS, ClaseH,
                             Conjunto, ConsecuenciasRed, DecisionAnio, Estado, EvidenciaEstacion, Hipotesis, Linea,
                             ModoE3t, MotivoAnio, MotivoSinInfo, Nivel, Regla, ResultadoGuarda, Veredicto,
                             interseccion_de_clases, tabla_vacia, validar_esquema)
from reloj_dmc.umbrales import Umbrales

H_TODAS = "*"                                   # guarda o marca que no depende de H (como decision)
SEPARADOR_CLASE = "|"
F0 = Hipotesis("F", 0, None).id                 # «F(0)»
MENSAJE_GDUP = "Filas DMC duplicadas con valores contradictorios"     # §5.4 y descargador :296
_URL_HOJA = re.compile(r"(?P<url>https?://[^\s;\"'<>]*?/hojaMensualDatos/(?P<codigo>\d+)/(?P<anio>\d{4})/"
                       r"(?P<mes>\d{1,2}))(?!\d)")
_INFORMATIVOS_E4P = (str(Estado.COMPATIBLE), str(Estado.INCOMPATIBLE), str(Estado.DUDOSA))
SIN_DATO = "sin_dato"                           # tipo, propietario o región que el catálogo no trae

# Los esquemas propios viven en tipos desde la ola 4b (§2 del diseño); estos alias son los mismos objetos.
ESQUEMA_MUESTRA_A3 = tipos.ESQUEMA_MUESTRA_A3
ESQUEMA_MUESTRA_A5 = tipos.ESQUEMA_MUESTRA_A5
ESQUEMA_CALIBRACION = tipos.ESQUEMA_CALIBRACION
ESQUEMA_GDUP = tipos.ESQUEMA_GDUP
MOTIVO_H_AMBIGUA = "H ambigua"

CATEGORIAS_RED = ("confirmadas_solo_F0", "confirmadas_en_otro_reloj", "con_algun_anio_discrepante",
                  "inestables", "sin_ningun_anio_confirmado")


@dataclass(frozen=True)
class ResultadoControl:
    control: str            # "A1" … "A7", "G-dup"
    pasa: bool
    detalle: Mapping[str, object]


# ---------------------------------------------------------------------------------------------
# Utilidades
def _num(x) -> float | None:
    """Número para el JSON del informe (allow_nan=False): NaN o nulo → None."""
    if x is None or x is pd.NA:
        return None
    x = float(x)
    return x if np.isfinite(x) else None


def _finito(v) -> bool:
    if v is None or v is pd.NA:
        return False
    try:
        return bool(np.isfinite(float(v)))
    except (TypeError, ValueError):
        return False


def _max_r(r) -> float:
    if r is None or r is pd.NA:
        return float("nan")
    a = np.asarray(r, dtype=np.float64).ravel()
    return float(np.nanmax(a)) if np.isfinite(a).any() else float("nan")


def _tabla(filas: list[dict], esquema: Mapping[str, str]) -> pd.DataFrame:
    if not filas:
        return tabla_vacia(esquema)
    return pd.DataFrame(filas, columns=list(esquema)).astype(esquema)


def _texto(v) -> str:
    return SIN_DATO if v is None or v is pd.NA or (isinstance(v, float) and not np.isfinite(v)) else str(v)


def _orden_canonico(ids) -> tuple[str, ...]:
    return tuple(sorted(ids, key=lambda h: Hipotesis.desde_id(h).orden()))


def _ids_miembros(clase: str) -> tuple[str, ...]:
    return tuple(str(clase).split(SEPARADOR_CLASE))


def _texto_mes(anio: int, mes: int) -> str:
    return f"{int(anio):04d}-{int(mes):02d}"


def _regimenes(metricas: pd.DataFrame | None, variable: str, esquema: Mapping[str, str]) -> pd.DataFrame:
    """Filas de año-régimen de una variable (ESQUEMA_METRICAS_E3 o _E4)."""
    if metricas is None or not len(metricas):
        return tabla_vacia(esquema)
    return metricas[(metricas["nivel"] == str(Nivel.REGIMEN)) & (metricas["variable"] == variable)]


def _lat_en(info, lat_max: float) -> bool:
    return info.lat is not None and _finito(info.lat) and abs(float(info.lat)) <= lat_max


def _e3p_filtrada_evaluable(n_pares, c_f_cont, r_f, umbrales: Umbrales) -> bool:
    """RED-2: ĉ^f_cont definido, ≥ E3_PARES_REGIMEN pares y máx r^f ≥ E3_RMAX."""
    if not _finito(c_f_cont) or not _finito(n_pares) or int(n_pares) < umbrales.f("E3_PARES_REGIMEN"):
        return False
    m = _max_r(r_f)
    return bool(np.isfinite(m) and m >= umbrales.a("E3_RMAX"))


@functools.lru_cache(maxsize=1)
def _calendario_por_omision():
    return mod_tablas.cargar_tablas()


def fijar_a4(consecuencias: ConsecuenciasRed, a4_restringe: bool) -> ConsecuenciasRed:
    """Consecuencias de la fase 5 con A4 ya calculado (fase 7 de §5.2)."""
    if consecuencias.a4_restringe is not None:
        raise ValueError("A4 ya estaba fijado en las consecuencias")
    return replace(consecuencias, a4_restringe=bool(a4_restringe))


# ---------------------------------------------------------------------------------------------
# A1 y A2: antes de leer la DMC
def _campo(control, nombre: str):
    return control[nombre] if isinstance(control, Mapping) else getattr(control, nombre)


def a1(c2_ok: bool, controles_era5: Mapping[str, object]) -> ResultadoControl:
    """C2 no cumplida, eje de ERA5-Land anómalo o unidades fuera de rango en algún mes (§3.4, §5.4).

    ``controles_era5``: AAAAMM → extraccion.ControlMesEra5 (o su forma JSON). Las unidades se juzgan
    otra vez desde las medianas, con los rangos de §3.4; una marca ``unidades_ok`` que no calza con su
    mediana también falla. Sin ningún mes controlado, A1 falla.
    """
    (t_min, t_max), (sp_min, sp_max) = constantes.valor("ERA5_T2M_K"), constantes.valor("ERA5_SP_PA")
    eje_anomalo, fuera_de_rango, inconsistentes = [], [], []
    for yyyymm in sorted(controles_era5):
        c = controles_era5[yyyymm]
        if not bool(_campo(c, "eje_ok")):
            eje_anomalo.append(yyyymm)
        med_t, med_sp = _campo(c, "mediana_t2m_K"), _campo(c, "mediana_sp_Pa")
        en_rango = (_finito(med_t) and _finito(med_sp) and t_min <= float(med_t) <= t_max
                    and sp_min <= float(med_sp) <= sp_max)
        if not en_rango:
            fuera_de_rango.append(yyyymm)
        if bool(_campo(c, "unidades_ok")) != en_rango:
            inconsistentes.append(yyyymm)
    sin_meses = not controles_era5
    pasa = bool(c2_ok) and not sin_meses and not (eje_anomalo or fuera_de_rango or inconsistentes)
    return ResultadoControl("A1", pasa, {
        "c2_cumplida": bool(c2_ok), "meses_controlados": len(controles_era5), "sin_meses": sin_meses,
        "eje_anomalo": eje_anomalo, "unidades_fuera_de_rango": fuera_de_rango,
        "unidades_marca_inconsistente": inconsistentes,
        "rangos": {"t2m_K": [t_min, t_max], "sp_Pa": [sp_min, sp_max]}})


def a2(sha_anexo_a_calculado: str, sha_anexo_a2_calculado: str, sha_anexo_a3_calculado: str) -> ResultadoControl:
    """La tabla de cambios no reproduce 8ea58b78…, la de reglas anteriores no reproduce b0727bee…, o la de
    eventos de regla vencida no reproduce el Anexo A3 (Enmienda 3, E3-2: «su huella va al anclaje»).

    Las huellas calculadas salen de tablas.TablasCalendario (``sha256_anexo_a``, ``sha256_anexo_a2`` y
    ``sha256_anexo_a3``)."""
    ok_a = sha_anexo_a_calculado == mod_tablas.SHA_ANEXO_A
    ok_a2 = sha_anexo_a2_calculado == mod_tablas.SHA_ANEXO_A2
    ok_a3 = sha_anexo_a3_calculado == mod_tablas.SHA_ANEXO_A3
    return ResultadoControl("A2", bool(ok_a and ok_a2 and ok_a3), {
        "anexo_a": {"calculada": sha_anexo_a_calculado, "anclada": mod_tablas.SHA_ANEXO_A, "reproduce": ok_a},
        "anexo_a2": {"calculada": sha_anexo_a2_calculado, "anclada": mod_tablas.SHA_ANEXO_A2, "reproduce": ok_a2},
        "anexo_a3": {"calculada": sha_anexo_a3_calculado, "anclada": mod_tablas.SHA_ANEXO_A3, "reproduce": ok_a3}})


# ---------------------------------------------------------------------------------------------
# A3: acuerdo entre E3p y E4p
def _e4p_evaluable(evidencia: EvidenciaEstacion) -> dict[tuple[int, str], float]:
    """(año, año-régimen) → ψ2, para los años-régimen con E4p evaluable (RED-2)."""
    e = evidencia.estados
    filas = e[(e["linea"] == str(Linea.E4P)) & (e["nivel"] == str(Nivel.REGIMEN))
              & e["estado"].isin(_INFORMATIVOS_E4P)]
    evaluables = {(int(a), str(u)) for a, u in zip(filas["anio"], filas["unidad"])}
    m = _regimenes(evidencia.metricas_e4, "QFE", ESQUEMA_METRICAS_E4)
    salida = {}
    for a, u, psi2 in zip(m["anio"], m["unidad"], m["psi2"]):
        clave = (int(a), str(u))
        if clave in evaluables and _finito(psi2):
            salida[clave] = float(psi2)
    return salida


def muestra_a3(evidencias: Iterable[EvidenciaEstacion], umbrales: Umbrales) -> pd.DataFrame:
    """Años-régimen con |lat| ≤ A3_LAT_MAX y E3p filtrada evaluable (ĉ^f_cont definido, ≥ 1.000 pares,
    máx r^f ≥ E3_RMAX) y E4p evaluable (RED-2). Columnas de ESQUEMA_MUESTRA_A3. D = ĉ^f_cont − (ψ2 −
    9,75 h); los tres envueltos a [−6, 6). No mira veredictos."""
    U = umbrales
    lo, hi = constantes.valor("A3_ENVOLVER")
    periodo = hi - lo
    fase_s2 = U.f("E4P_S2_FASE_H")
    filas = []
    for ev in evidencias:
        info = ev.info
        if not _lat_en(info, U.f("A3_LAT_MAX")):
            continue
        psi2 = _e4p_evaluable(ev)
        if not psi2:
            continue
        m = _regimenes(ev.metricas_e3, "QFE", ESQUEMA_METRICAS_E3)
        for a, u, n, cf, rf in zip(m["anio"], m["unidad"], m["n_pares"], m["c_hat_f_cont"], m["r_f"]):
            clave = (int(a), str(u))
            if clave not in psi2 or not _e3p_filtrada_evaluable(n, cf, rf, U):
                continue
            c_f = float(numerico.envolver(float(cf), lo, periodo))
            c_s2 = float(numerico.envolver(psi2[clave] - fase_s2, lo, periodo))
            filas.append({"codigo": info.codigo, "anio": clave[0], "regimen": clave[1], "macrozona": info.macrozona,
                          "c_f_cont": c_f, "c_s2_cont": c_s2,
                          "D": float(numerico.envolver(c_f - c_s2, lo, periodo))})
    return _tabla(filas, ESQUEMA_MUESTRA_A3)


def _acuerdo(D: np.ndarray, frac_min: float, umbrales: Umbrales) -> dict:
    """Acuerdo en un ámbito: |D| ≤ A3_D_MAX_H en ≥ frac_min y |mediana de D| ≤ A3_MEDIANA_MAX_H, con
    ≥ A3_MIN_REGIMENES años-régimen; con menos, no se evalúa y no falla (RED-1)."""
    U = umbrales
    D = np.asarray(D, dtype=np.float64)
    n = int(D.size)
    evaluado = n >= U.f("A3_MIN_REGIMENES")
    dentro = float(np.mean(np.abs(D) <= U.f("A3_D_MAX_H"))) if n else float("nan")
    mediana = float(np.median(D)) if n else float("nan")
    falla = bool(evaluado and not (dentro >= frac_min and abs(mediana) <= U.f("A3_MEDIANA_MAX_H")))
    return {"n": n, "evaluado": bool(evaluado), "frac_dentro": _num(dentro), "mediana_D": _num(mediana),
            "frac_minima": frac_min, "falla": falla}


def a3(muestra: pd.DataFrame, umbrales: Umbrales) -> tuple[bool, frozenset[str], dict]:
    """(falla en el país, macrozonas que fallan, detalle). D = ĉ^f_cont − (ψ2 − 9,75), envuelto a [−6, 6).

    País: A3_FRAC_PAIS; macrozona: A3_FRAC_MACRO; ambos con |mediana| ≤ A3_MEDIANA_MAX_H y
    ≥ A3_MIN_REGIMENES años-régimen."""
    validar_esquema(muestra, ESQUEMA_MUESTRA_A3, nombre="muestra_a3")
    U = umbrales
    pais = _acuerdo(muestra["D"].to_numpy(np.float64), U.f("A3_FRAC_PAIS"), U)
    por_macro = {str(mz): _acuerdo(g["D"].to_numpy(np.float64), U.f("A3_FRAC_MACRO"), U)
                 for mz, g in muestra.groupby("macrozona", sort=True)}
    fallan = frozenset(mz for mz, d in por_macro.items() if d["falla"])
    detalle = {"pais": pais, "macrozonas": por_macro,
               "umbrales": {"d_max_h": U.f("A3_D_MAX_H"), "mediana_max_h": U.f("A3_MEDIANA_MAX_H"),
                            "min_regimenes": U.f("A3_MIN_REGIMENES"), "lat_max": U.f("A3_LAT_MAX")},
               "falla_pais": pais["falla"], "fallan_macrozonas": sorted(fallan)}
    return pais["falla"], fallan, detalle


# ---------------------------------------------------------------------------------------------
# A5: semántica de la red
def muestra_a5(evidencias: Iterable[EvidenciaEstacion], umbrales: Umbrales) -> pd.DataFrame:
    """Años-régimen con |lat| ≤ 50°, E3p filtrada evaluable, ≥ 1.000 pares y ĉ^f_cont definido (RED-2).
    Columnas de ESQUEMA_MUESTRA_A5 (con tipo y propietario de la estación, para el informe)."""
    U = umbrales
    filas = []
    for ev in evidencias:
        info = ev.info
        if not _lat_en(info, constantes.valor("A5_LAT_MAX")):
            continue
        m = _regimenes(ev.metricas_e3, "QFE", ESQUEMA_METRICAS_E3)
        for a, u, n, cf, rf in zip(m["anio"], m["unidad"], m["n_pares"], m["c_hat_f_cont"], m["r_f"]):
            if _e3p_filtrada_evaluable(n, cf, rf, U):
                filas.append({"codigo": info.codigo, "anio": int(a), "regimen": str(u), "macrozona": info.macrozona,
                              "tipo": _texto(info.tipo), "propietario": _texto(info.propietario),
                              "c_f_cont": float(cf)})
    return _tabla(filas, ESQUEMA_MUESTRA_A5)


def _m_circular(x) -> float:
    """m de A5: media circular de período 1 h llevada a [−0,5; 0,5) (RED-3); la misma función que ρ de §4.3.5
    con la Enmienda 3 (B6; lineas_fisicas.diagnostico_subhorario)."""
    return numerico.media_circular_en(np.asarray(x, dtype=np.float64), constantes.valor("A5_ENVOLVER"))


def a5(muestra: pd.DataFrame, umbrales: Umbrales) -> tuple[bool, dict]:
    """(alto, detalle con m nacional, por tipo y por propietario). m = media circular de período 1 h.
    Alto si |m| > A5_M_MAX_H con ≥ A5_MIN_REGIMENES años-régimen; con alto, la corrida termina el informe
    pero no escribe la política (lo hace cumplir orquestacion)."""
    validar_esquema(muestra, ESQUEMA_MUESTRA_A5, nombre="muestra_a5")
    U = umbrales
    n = len(muestra)
    m = _m_circular(muestra["c_f_cont"]) if n else float("nan")
    alto = bool(n >= U.f("A5_MIN_REGIMENES") and np.isfinite(m) and abs(m) > U.f("A5_M_MAX_H"))

    def por(columna: str) -> dict:
        return {str(k): {"n": len(g), "m": _num(_m_circular(g["c_f_cont"]))}
                for k, g in muestra.groupby(columna, sort=True)}

    return alto, {"n": n, "m": _num(m), "m_indefinida": bool(n and not np.isfinite(m)), "alto": alto,
                  "umbrales": {"m_max_h": U.f("A5_M_MAX_H"), "min_regimenes": U.f("A5_MIN_REGIMENES")},
                  "por_tipo": por("tipo"), "por_propietario": por("propietario")}


# ---------------------------------------------------------------------------------------------
# Calibración de E3t (§4.3.3)
def _desfases_por_regimen(evidencia: EvidenciaEstacion, anio: int, calendario) -> dict[str, dict[str, int]]:
    """Año-régimen → (id de H → c_H(R)). Desde ``evidencia.clases`` si existe (RED-4); si no, desde el
    calendario."""
    por_anio = getattr(evidencia, "clases", None)
    if por_anio is not None and anio in por_anio:
        salida: dict[str, dict[str, int]] = {}
        for clase in por_anio[anio]:
            if not isinstance(clase, ClaseH):
                raise ValueError("evidencia.clases debe traer tipos.ClaseH por año")
            for r, c in clase.desfases.items():
                for h in clase.miembros:
                    salida.setdefault(str(r), {})[h.id] = int(c)
        return salida
    info = evidencia.info
    calendario = calendario if calendario is not None else _calendario_por_omision()
    salida = {}
    for reg in mod_tablas.regimenes_del_anio(info.zs, anio, calendario):
        salida[reg.id] = {h.id: mod_tablas.desfase(h, reg, info.zs) for h in info.P if h.tipo != "Cv"}
    return salida


def _e3p_anual_estacion(estados_: pd.DataFrame, anios: Sequence[int], ids_P: Sequence[str],
                        fina_red: bool) -> dict[tuple[int, str], str]:
    """(año, H) → estado anual de E3p con lineas_fisicas.e3p_anual (§4.3.4), con la fina activa sólo
    donde A3 no falla y la estación no la apagó (como decision)."""
    e = estados_
    e3p = e[(e["linea"] == str(Linea.E3P)) & e["H"].isin([*ids_P, H_TODAS])]
    gruesa = e3p[(e3p["regla"] == str(Regla.GRUESA)) & e3p["anio"].isin(list(anios))]
    fina = e3p[(e3p["regla"] == str(Regla.FINA))
               & (e3p["anio"].isin(list(anios)) | (e3p["nivel"] == str(Nivel.ESTACION)))]
    if gruesa.empty:
        return {}
    apagada = bool(((fina["nivel"] == str(Nivel.ESTACION))
                    & (fina["motivo"] == str(MotivoSinInfo.APAGADA)).fillna(False)).any())
    salida = lineas_fisicas.e3p_anual(gruesa.reset_index(drop=True), fina.reset_index(drop=True),
                                      bool(fina_red) and not apagada)
    anual = salida[(salida["nivel"] == str(Nivel.ANIO)) & (salida["linea"] == str(Linea.E3P))]
    return {(int(a), str(h)): str(est) for a, h, est in zip(anual["anio"], anual["H"], anual["estado"])}


def _estado_tp(guardas: pd.DataFrame, anio: int, ids_h: Sequence[str]) -> str:
    """T-P del año bajo H (falla > pasa > no_evaluable), sólo para la tabla de la calibración."""
    g = guardas[(guardas["guarda"] == str(Linea.TP)) & (guardas["anio"] == anio)
                & guardas["H"].isin([*ids_h, H_TODAS])]
    vistos = set(g["resultado"])
    for r in (ResultadoGuarda.FALLA, ResultadoGuarda.PASA):
        if str(r) in vistos:
            return str(r)
    return str(ResultadoGuarda.NO_EVALUABLE)


def muestra_calibracion_e3t(evidencias: Iterable[EvidenciaEstacion], a3_pais: bool, a3_macro: frozenset[str],
                            umbrales: Umbrales, *, calendario=None) -> pd.DataFrame:
    """Estación-años con ≥ 1.000 pares de Ts por año-régimen que pasan el filtro y con E3p y E4p
    compatibles con una misma H en el año (E3p anual ya con las consecuencias de A3). δt por estación-año
    (RED-4). Columnas de ESQUEMA_CALIBRACION; los «H ambigua» llevan δt NaN y su motivo.
    ``calendario``: tablas.TablasCalendario para c_H(R) cuando la evidencia no trae ``clases``."""
    U = umbrales
    filas = []
    for ev in evidencias:
        info = ev.info
        ids_P = tuple(h.id for h in info.P)
        m = _regimenes(ev.metricas_e3, "Ts", ESQUEMA_METRICAS_E3)
        if not len(m):
            continue
        sel = [bool(f) and _finito(n) and int(n) >= U.f("E3_PARES_REGIMEN") and _finito(c)
               for f, n, c in zip(m["filtro_e3t"], m["n_pares"], m["c_hat_cont"])]
        ts = m[pd.Series(sel, index=m.index, dtype=bool)]
        if not len(ts):
            continue
        anios = sorted({int(a) for a in ts["anio"]})
        fina_red = not (a3_pais or info.macrozona in a3_macro)
        e3p = _e3p_anual_estacion(ev.estados, anios, ids_P, fina_red)
        e = ev.estados
        e4 = e[(e["linea"] == str(Linea.E4P)) & (e["nivel"] == str(Nivel.ANIO))]
        e4p = {(int(a), str(h)): str(est) for a, h, est in zip(e4["anio"], e4["H"], e4["estado"])}
        comp = str(Estado.COMPATIBLE)
        for anio in anios:
            hs = _orden_canonico(h for h in ids_P if e3p.get((anio, h)) == comp and e4p.get((anio, h)) == comp)
            if not hs:
                continue
            del_anio = ts[ts["anio"] == anio].sort_values("unidad")
            desfases = _desfases_por_regimen(ev, anio, calendario)
            vectores = set()
            for h in hs:
                try:
                    vectores.add(tuple(desfases[str(r)][h] for r in del_anio["unidad"]))
                except KeyError as falta:
                    raise ValueError(f"{info.codigo} {anio}: sin c_H(R) para {falta} en {sorted(desfases)}") from None
            fila = {"codigo": info.codigo, "anio": anio, "macrozona": info.macrozona,
                    "H": SEPARADOR_CLASE.join(hs), "n_regimenes": len(del_anio),
                    "tp": _estado_tp(ev.guardas, anio, hs), "motivo": None}
            if len(vectores) != 1:
                fila.update(delta_t=np.nan, deltas_R=None, motivo=MOTIVO_H_AMBIGUA)
            else:
                (c_h,) = vectores
                deltas = [float(c) - ch for c, ch in zip(del_anio["c_hat_cont"], c_h)]
                fila.update(delta_t=float(np.median(deltas)), deltas_R=deltas)
            filas.append(fila)
    return _tabla(filas, ESQUEMA_CALIBRACION)


def _resumen_delta(d: np.ndarray, umbrales: Umbrales) -> dict:
    d = d[np.isfinite(d)]
    n = int(d.size)
    fuera = int(np.sum(np.abs(d) > umbrales.f("CAL_E3T_DELTA_H")))
    return {"n": n, "n_fuera": fuera, "frac_fuera": _num(fuera / n) if n else None}


def _calibracion(muestra: pd.DataFrame, a3_pais: bool, a3_macro: frozenset[str], macrozonas: Sequence[str],
                 umbrales: Umbrales) -> tuple[dict[str, ModoE3t], dict]:
    validar_esquema(muestra, ESQUEMA_CALIBRACION, nombre="muestra_calibracion_e3t")
    U = umbrales
    todas = sorted({str(z) for z in macrozonas} | {str(z) for z in muestra["macrozona"]})
    modos, resumen = {}, {}
    for mz in todas:
        sub = muestra[muestra["macrozona"] == mz]
        d = sub["delta_t"].to_numpy(np.float64)
        r = _resumen_delta(d, U)
        sin_tp = _resumen_delta(sub.loc[sub["tp"] != str(ResultadoGuarda.FALLA), "delta_t"].to_numpy(np.float64), U)
        if a3_pais or mz in a3_macro:
            modo, motivo = ModoE3t.RESTRINGIDO, "falla A3"
        elif r["n"] < U.f("CAL_E3T_MIN"):
            modo, motivo = ModoE3t.RESTRINGIDO, "menos estación-años que el mínimo"
        elif r["n_fuera"] / r["n"] <= U.frac("CAL_E3T_PCT"):
            modo, motivo = ModoE3t.COMPLETO, None
        else:
            modo, motivo = ModoE3t.RESTRINGIDO, "fracción con |δt| sobre el umbral"
        modos[mz] = modo
        resumen[mz] = {**r, "sin_falla_tp": sin_tp, "h_ambigua": int((sub["motivo"] == MOTIVO_H_AMBIGUA).sum()),
                       "modo": str(modo), "motivo": motivo}
    return modos, resumen


def calibrar_e3t(muestra: pd.DataFrame, a3_pais: bool, a3_macro: frozenset[str], macrozonas: Sequence[str],
                 umbrales: Umbrales) -> tuple[dict[str, str], pd.DataFrame]:
    """(modo por macrozona, distribución de δt para calibracion_e3t.csv). Completo si ≥ 30 estación-años y
    |δt| > 1,0 h en ≤ 1 %; restringido si < 30 o si falla A3 ahí. No hereda la calibración nacional.
    La distribución es la muestra completa con la columna ``fuera`` (|δt| > CAL_E3T_DELTA_H)."""
    modos, _ = _calibracion(muestra, a3_pais, a3_macro, macrozonas, umbrales)
    distribucion = muestra.copy()
    d = distribucion["delta_t"].to_numpy(np.float64)
    fuera = pd.array([bool(abs(x) > umbrales.f("CAL_E3T_DELTA_H")) if np.isfinite(x) else pd.NA for x in d],
                     dtype="boolean")
    distribucion["fuera"] = fuera
    return modos, distribucion


def controles_red(evidencias: Sequence[EvidenciaEstacion], macrozonas: Sequence[str],
                  umbrales: Umbrales, *, calendario=None) -> tuple[ConsecuenciasRed, dict]:
    """Nombre de §9: A3, A5 y calibración de E3t, en ese orden; devuelve las consecuencias (sin A4) y el
    detalle. ``detalle["tablas"]`` trae las muestras de A3 y A5 y la distribución de δt (DataFrames,
    para calibracion_e3t.csv); el resto es JSON para controles_red.json."""
    evidencias = list(evidencias)
    m3 = muestra_a3(evidencias, umbrales)
    falla_pais, fallan, det3 = a3(m3, umbrales)
    m5 = muestra_a5(evidencias, umbrales)
    alto, det5 = a5(m5, umbrales)
    todas = sorted({str(z) for z in macrozonas} | {e.info.macrozona for e in evidencias})
    mc = muestra_calibracion_e3t(evidencias, falla_pais, fallan, umbrales, calendario=calendario)
    modos, resumen = _calibracion(mc, falla_pais, fallan, todas, umbrales)
    _, distribucion = calibrar_e3t(mc, falla_pais, fallan, todas, umbrales)
    consecuencias = ConsecuenciasRed(a3_falla_pais=falla_pais, a3_fallan_macrozonas=fallan, a5_alto=alto,
                                     modo_e3t=modos, a4_restringe=None)
    detalle = {"A3": det3, "A5": det5,
               "calibracion_e3t": {"modos": {mz: str(m) for mz, m in modos.items()}, "por_macrozona": resumen,
                                   "umbrales": {"min_estacion_anios": umbrales.f("CAL_E3T_MIN"),
                                                "delta_h": umbrales.f("CAL_E3T_DELTA_H"),
                                                "frac_max": umbrales.frac("CAL_E3T_PCT")}},
               "tablas": {"muestra_a3": m3, "muestra_a5": m5, "calibracion_e3t": distribucion}}
    return consecuencias, detalle


# ---------------------------------------------------------------------------------------------
# A4, A6 y A7
def a4(decisiones_parciales: Sequence[DecisionAnio], umbrales: Umbrales) -> tuple[bool, dict]:
    """E3t restringida en todo el país si fallan T-P más del 10 % de los estación-años en que se evalúa
    (RED-5: T-P «pasa» o «falla» en DecisionAnio.guardas; «no_evaluable» no cuenta)."""
    evaluadas = fallan = 0
    for d in decisiones_parciales:
        r = d.guardas.get(str(Linea.TP))
        if r in (str(ResultadoGuarda.PASA), str(ResultadoGuarda.FALLA)):
            evaluadas += 1
            fallan += r == str(ResultadoGuarda.FALLA)
    frac = fallan / evaluadas if evaluadas else float("nan")
    restringe = bool(evaluadas and frac > umbrales.frac("A4_PCT"))
    return restringe, {"evaluados": evaluadas, "fallan": int(fallan), "frac_fallan": _num(frac),
                       "frac_max": umbrales.frac("A4_PCT"), "restringe_e3t": restringe}


def _anio_de(v) -> int | None:
    if v is None:
        return None
    if isinstance(v, int) and not isinstance(v, bool):
        return v
    m = re.fullmatch(r"(\d{4})(?:-\d{2}(?:-\d{2})?)?", str(v).strip())
    if m is None:
        raise ValueError(f"año de alcance no interpretable: {v!r}")
    return int(m.group(1))


def a6(registro_documental: Sequence[Mapping], decisiones: Sequence[DecisionAnio]) -> list[tuple[str, int]]:
    """Estación-años confirmados que contradice un D1, dentro de su alcance (§4.5; RED-6). Con E5
    inactiva el registro sigue «pendiente» y no hay ninguno."""
    contrarios: set[tuple[str, int]] = set()
    for entrada in registro_documental:
        if entrada.get("nivel") != "D1" or entrada.get("estado") == "pendiente":
            continue
        cita = entrada.get("cita_literal")
        reloj = entrada.get("reloj_declarado")
        if not (isinstance(cita, str) and cita.strip()):
            raise ValueError(f"{entrada.get('id')}: un D1 sin cita literal (§4.5)")
        if not reloj:
            raise ValueError(f"{entrada.get('id')}: un D1 sin reloj declarado")
        reloj = Hipotesis.desde_id(str(reloj)).id
        alcance = entrada.get("alcance") or {}
        estaciones = alcance.get("estaciones")
        estaciones = None if estaciones is None else {str(c) for c in estaciones}
        desde, hasta = _anio_de(alcance.get("anio_desde")), _anio_de(alcance.get("anio_hasta"))
        for d in decisiones:
            if d.veredicto != Veredicto.CONFIRMADO or not d.clase_confirmada:
                continue
            if estaciones is not None and d.codigo not in estaciones:
                continue
            if (desde is not None and d.anio < desde) or (hasta is not None and d.anio > hasta):
                continue
            if reloj not in _ids_miembros(d.clase_confirmada):
                contrarios.add((d.codigo, int(d.anio)))
    return sorted(contrarios)


def a7(fallas: Sequence[str]) -> ResultadoControl:
    """Resumen de A7: las fallas de politica.verificar_politica (§7.3) sobre la política releída. Con
    alguna, no se publica y se trata como errata (§10)."""
    fallas = [str(f) for f in fallas]
    return ResultadoControl("A7", not fallas, {"fallas": fallas, "n": len(fallas)})


# ---------------------------------------------------------------------------------------------
# G-dup (sólo describe)
def _bajo_volumes(ruta: Path) -> bool:
    """True si la ruta, léxica o resuelta, está bajo /Volumes (sin distinguir mayúsculas). Primero la léxica,
    sin tocar el disco: una ruta bajo /Volumes se rechaza sin consultarla (§8, prueba 27). Sólo si la léxica
    no lo está se resuelve, para atrapar un enlace que lleve allí (como entorno.prohibido_volumes)."""
    def en_volumes(p: Path) -> bool:
        return len(p.parts) >= 2 and p.parts[0] == "/" and p.parts[1].casefold() == "volumes"

    return en_volumes(Path(ruta).expanduser().absolute()) or en_volumes(Path(ruta).expanduser().resolve())


def _zonas_con_atraso(calendario, zs: Sequence[str], anio: int, mes: int) -> tuple[str, ...]:
    salida = []
    for z in zs:
        if any(c.tipo == "atraso" and c.etiqueta.month == mes for c in calendario.cambios(z, anio)):
            salida.append(z)
    return tuple(salida)


def g_dup(copias_c2: Sequence[Path], tablas: object, *,
          zs_de: Mapping[str, Sequence[str]] | None = None) -> pd.DataFrame:
    """Casos de «Filas DMC duplicadas con valores contradictorios» en progreso.json y bitácoras copiadas
    en C2: estación y mes sacados de la URL, y si el mes contiene un atraso de alguna zona de Zs (RED-7).
    ``tablas`` es el tablas.TablasCalendario; ``zs_de`` da las Zs por código. No cambia ningún veredicto."""
    filas = []
    zonas_todas = tuple(getattr(tablas, "zonas", ZONAS))
    for ruta in copias_c2:
        ruta = Path(ruta)
        if _bajo_volumes(ruta):
            raise PermissionError("G-dup lee sólo las copias de C2, nunca bajo /Volumes (§9)")
        texto = ruta.read_bytes().decode("utf-8", errors="replace")
        for linea in texto.splitlines():
            inicio = 0
            while (i := linea.find(MENSAJE_GDUP, inicio)) >= 0:
                fin = linea.find(MENSAJE_GDUP, i + len(MENSAJE_GDUP))
                tramo = linea[i:fin if fin >= 0 else len(linea)]
                url = _URL_HOJA.search(tramo)
                fila = {"archivo": ruta.name, "codigo": None, "mes": None, "url": None, "atraso_en_zs": pd.NA,
                        "zonas_con_atraso": None}
                if url is not None:
                    codigo, anio, mes = url.group("codigo"), int(url.group("anio")), int(url.group("mes"))
                    zs = tuple(zs_de[codigo]) if zs_de is not None and codigo in zs_de else zonas_todas
                    con_atraso = _zonas_con_atraso(tablas, zs, anio, mes)
                    fila.update(codigo=codigo, mes=_texto_mes(anio, mes), url=url.group("url"),
                                atraso_en_zs=bool(con_atraso), zonas_con_atraso=",".join(con_atraso))
                filas.append(fila)
                inicio = i + len(MENSAJE_GDUP)
    return _tabla(filas, ESQUEMA_GDUP)


# ---------------------------------------------------------------------------------------------
# §5.3.6: cambio del portal (sólo se informa)
def cambios_del_portal(rachas: pd.DataFrame, meses_con_datos: Mapping[str, Sequence[str]],
                       umbrales: Umbrales) -> list[dict]:
    """§5.3.6: meses en que ≥ 20 % de las estaciones con datos cambian de reloj (mes = primer mes con datos
    de la racha posterior; R-26; RED-8). Sólo se informa."""
    validar_esquema(rachas, ESQUEMA_RACHAS, nombre="rachas")
    meses_de = {str(c): sorted({str(m) for m in ms}) for c, ms in meses_con_datos.items()}
    cambian: dict[str, set[str]] = {}
    for codigo, de_estacion in rachas.groupby("codigo", sort=True):
        lista = de_estacion.sort_values("racha")
        clases = [frozenset(_ids_miembros(c)) for c in lista["clase"]]
        desde = [int(a) for a in lista["anio_desde"]]
        for i in range(1, len(clases)):
            if interseccion_de_clases(clases[i - 1], clases[i]):
                continue
            meses = [m for m in meses_de.get(str(codigo), ()) if m >= _texto_mes(desde[i], 1)]
            if not meses:
                raise ValueError(f"{codigo}: la racha que empieza en {desde[i]} no tiene meses con datos")
            cambian.setdefault(meses[0], set()).add(str(codigo))
    salida = []
    for mes in sorted(cambian):
        con_datos = sorted(c for c, ms in meses_de.items() if mes in ms)
        n = len(con_datos)
        frac = len(cambian[mes]) / n if n else float("nan")
        if n and frac >= umbrales.frac("PORTAL_PCT"):
            salida.append({"mes": mes, "estaciones_que_cambian": sorted(cambian[mes]), "n_cambian": len(cambian[mes]),
                           "n_con_datos": n, "fraccion": frac})
    return salida


# ---------------------------------------------------------------------------------------------
# §5.4: descripción de la red (sólo N)
def _con_datos(evidencia: EvidenciaEstacion, decisiones: Sequence[DecisionAnio]) -> bool:
    meses = evidencia.meses
    if len(meses) and bool(meses["entra"].fillna(False).astype(bool).any()):
        return True
    return any(d.veredicto != Veredicto.SIN_DATOS for d in decisiones)


def _inestable(codigo: str, decisiones: Sequence[DecisionAnio], rachas: pd.DataFrame, umbrales: Umbrales) -> bool:
    if any(d.motivo == MotivoAnio.INESTABLE for d in decisiones):
        return True
    r = rachas[rachas["codigo"] == codigo]
    if bool((r["motivo"] == str(MotivoAnio.INESTABLE)).fillna(False).any()):
        return True
    con_datos = [d for d in decisiones if d.veredicto != Veredicto.SIN_DATOS]
    disc = [d for d in decisiones if d.veredicto == Veredicto.DISCREPANTE and not d.reglas_vencidas]
    return bool(con_datos and len(disc) >= umbrales.f("INESTABLE_ANIOS")
                and len(disc) / len(con_datos) > umbrales.frac("INESTABLE_PCT"))


def _proporciones(estaciones: Sequence[dict]) -> dict:
    n = len(estaciones)
    horas = int(sum(e["horas"] for e in estaciones))
    salida: dict[str, Any] = {"n_estaciones": n, "estacion_horas": horas}
    for cat in CATEGORIAS_RED:
        sel = [e for e in estaciones if e[cat]]
        h = int(sum(e["horas"] for e in sel))
        salida[cat] = {"estaciones": len(sel), "prop_estaciones": _num(len(sel) / n) if n else None,
                       "estacion_horas": h, "prop_estacion_horas": _num(h / horas) if horas else None}
    return salida


def describir_red(decisiones: Sequence[DecisionAnio], rachas: pd.DataFrame, evidencias: Sequence[EvidenciaEstacion],
                  umbrales: Umbrales, *, meses_con_regla: Mapping[str, Mapping[str, str]] | None = None,
                  sensibilidades_bateria: Mapping | None = None) -> dict:
    """§5.4: sólo N y sólo con ≥ 30 estaciones con datos; proporciones de estaciones y estación-horas,
    por propietario, tipo, región y macrozona; «red en UTC» si se cumplen las tres condiciones (RED-9).

    ``decisiones`` son las finales (después de §5.3); ``rachas`` es ESQUEMA_RACHAS de todas las
    estaciones; ``meses_con_regla``: código → («AAAA-MM» → clase), como decision.ResultadoRachas;
    ``sensibilidades_bateria``: las sensibilidades por reloj de §8.D, que se copian tal cual."""
    U = umbrales
    validar_esquema(rachas, ESQUEMA_RACHAS, nombre="rachas")
    por_codigo: dict[str, list[DecisionAnio]] = {}
    for d in decisiones:
        por_codigo.setdefault(d.codigo, []).append(d)
    estaciones = []
    for ev in evidencias:
        info = ev.info
        if info.conjunto != Conjunto.N:
            continue
        dec = sorted(por_codigo.get(info.codigo, []), key=lambda d: d.anio)
        if not _con_datos(ev, dec):
            continue
        validar_esquema(ev.horas, ESQUEMA_HORAS, nombre=f"horas de {info.codigo}")
        h = ev.horas
        horas_mes = {_texto_mes(a, m): int(n) for a, m, n in zip(h["anio"], h["mes"], h["horas_ts_o_qfe"])}
        confirmados = [d for d in dec if d.veredicto == Veredicto.CONFIRMADO]
        regla = (meses_con_regla or {}).get(info.codigo, {})
        estaciones.append({
            "codigo": info.codigo, "horas": sum(horas_mes.values()),
            "horas_tramos_F0": sum(n for mes, n in horas_mes.items() if regla.get(mes) == F0),
            "evaluados": sum(1 for d in dec if d.veredicto != Veredicto.SIN_DATOS),
            "discrepantes": sum(1 for d in dec if d.veredicto == Veredicto.DISCREPANTE),
            "confirmadas_solo_F0": bool(confirmados) and all(d.clase_confirmada == F0 for d in confirmados),
            "confirmadas_en_otro_reloj": any(d.clase_confirmada != F0 for d in confirmados),
            "con_algun_anio_discrepante": any(d.veredicto == Veredicto.DISCREPANTE for d in dec),
            "inestables": _inestable(info.codigo, dec, rachas, U),
            "sin_ningun_anio_confirmado": not confirmados,
            "propietario": _texto(info.propietario), "tipo": _texto(info.tipo),
            "region": _texto(info.region), "macrozona": info.macrozona})
    n = len(estaciones)
    minimo = U.f("RED_MIN_ESTACIONES")
    if n < minimo:
        return {"aplica": False, "conjunto": str(Conjunto.N), "n_estaciones_con_datos": n,
                "motivo": f"N tiene {n} estaciones con datos; la descripción exige ≥ {minimo}",
                "red_en_utc": False}

    def por(clave: str) -> dict:
        grupos: dict[str, list[dict]] = {}
        for e in estaciones:
            grupos.setdefault(e[clave], []).append(e)
        return {k: _proporciones(v) for k, v in sorted(grupos.items())}

    horas = sum(e["horas"] for e in estaciones)
    horas_f0 = sum(e["horas_tramos_F0"] for e in estaciones)
    evaluados = sum(e["evaluados"] for e in estaciones)
    discrepantes = sum(e["discrepantes"] for e in estaciones)
    frac_f0 = horas_f0 / horas if horas else float("nan")
    frac_disc = discrepantes / evaluados if evaluados else float("nan")
    en_otro = sorted(e["codigo"] for e in estaciones if e["confirmadas_en_otro_reloj"])
    condiciones = {
        "horas_en_tramos_F0": {"valor": _num(frac_f0), "umbral_min": U.frac("RED_UTC_HORAS_PCT"),
                               "con_meses_con_regla": meses_con_regla is not None,
                               "cumple": bool(meses_con_regla is not None and horas
                                              and frac_f0 >= U.frac("RED_UTC_HORAS_PCT"))},
        "ninguna_en_otro_reloj": {"estaciones": len(en_otro), "cumple": not en_otro},
        "discrepantes": {"valor": _num(frac_disc), "umbral_max": U.frac("RED_UTC_DISCREP_PCT"),
                         "discrepantes": discrepantes, "evaluados": evaluados,
                         "cumple": bool(evaluados and frac_disc <= U.frac("RED_UTC_DISCREP_PCT"))},
    }
    return {"aplica": True, "conjunto": str(Conjunto.N), "n_estaciones_con_datos": n,
            "denominadores": {"estaciones": n, "estacion_horas": int(horas), "estacion_anios_evaluados": evaluados},
            "red": _proporciones(estaciones),
            "por_propietario": por("propietario"), "por_tipo": por("tipo"), "por_region": por("region"),
            "por_macrozona": por("macrozona"),
            "red_en_utc": all(c["cumple"] for c in condiciones.values()), "condiciones_red_en_utc": condiciones,
            "sensibilidades_bateria": None if sensibilidades_bateria is None else dict(sensibilidades_bateria)}


# ---------------------------------------------------------------------------------------------
# §1.13: predicciones registradas para N (descriptivas; RED-10)
PREDICCION_CUMPLIDA = "cumplida"
PREDICCION_NO_CUMPLIDA = "predicción no cumplida"      # §1.13, tal cual
PREDICCION_SIN_DATOS = "sin_datos"                     # ninguna unidad evaluable: no se juzga
NOTA_PREDICCIONES = ("§1.13: son descriptivas, no umbrales; un incumplimiento se informa como «predicción no "
                     "cumplida», no como desviación")
PORCENTAJE = 100                # no-umbral: de porcentaje a fracción
DELTA_E1B_FIJAS = -1            # no-umbral: §4.1.2, «δ = −1 indica etiquetas fijas con operación en hora civil»
F_MENOS4 = Hipotesis.desde_id("F(-4)").id             # «Si está en F(−4)» (§1.13)
C_SANTIAGO = Hipotesis.desde_id("C(Santiago)").id      # «Si está en C(Santiago)» (§1.13)
RELOJES_PREDICCIONES = (F0, F_MENOS4, C_SANTIAGO)      # los tres bloques de §1.13, en su orden
_GUARDAS_PREDICCION = (*(str(g) for g in tipos.GUARDAS_DE_DECISION), str(Linea.G_VERSION))
_EVALUABLES_E1A = (str(tipos.ResultadoEvento.PRESENTE), str(tipos.ResultadoEvento.AUSENTE))
_REAL = str(tipos.ClaseEvento.REAL)
_REGLA_VENCIDA = str(tipos.ClaseEvento.REGLA_VENCIDA)   # Enmienda 3, E3-2: no es placebo del patrón civil (RED-10)


def _pct(nombre: str, i: int | None = None) -> float:
    v = constantes.valor(nombre)
    return (v if i is None else v[i]) / PORCENTAJE


def _prediccion(ident: str, lectura: str, k: int, n: int, *, minimo: float | None = None,
                maximo: float | None = None, **extra) -> dict:
    """k de n unidades cumplen; con ``minimo`` o ``maximo`` se juzga la fracción, y sin ellos la predicción es
    universal (§1.13 no da porcentaje: todas las unidades evaluables; RED-10)."""
    if not n:
        resultado = PREDICCION_SIN_DATOS
    elif minimo is not None:
        resultado = PREDICCION_CUMPLIDA if k / n >= minimo else PREDICCION_NO_CUMPLIDA
    elif maximo is not None:
        resultado = PREDICCION_CUMPLIDA if k / n <= maximo else PREDICCION_NO_CUMPLIDA
    else:
        resultado = PREDICCION_CUMPLIDA if k == n else PREDICCION_NO_CUMPLIDA
    return {"id": ident, "lectura": lectura, "k": int(k), "n": int(n), "fraccion": _num(k / n) if n else None,
            "minimo": minimo, "maximo": maximo, "resultado": resultado, **extra}


def _desfases_de(ev: EvidenciaEstacion, anio: int, h: str, calendario, memoria: dict) -> dict[str, int]:
    """Año-régimen → c_H(R) de la estación, o {} si H no está en su P (RED-4: clases o calendario)."""
    clave = (ev.info.codigo, anio)
    if clave not in memoria:
        memoria[clave] = _desfases_por_regimen(ev, anio, calendario)
    return {r: por_h[h] for r, por_h in memoria[clave].items() if h in por_h}


def _e1a_presentes(evs: Sequence[EvidenciaEstacion], anios: set[tuple[str, int]]) -> tuple[int, int]:
    """Adelantos reales de E1a: (presentes, evaluables = presentes o ausentes)."""
    k = n = 0
    for ev in evs:
        e = ev.eventos
        e = e[(e["linea"] == str(Linea.E1A)) & (e["clase_evento"] == _REAL) & e["resultado"].isin(_EVALUABLES_E1A)]
        for a, r in zip(e["anio"], e["resultado"]):
            if (ev.info.codigo, int(a)) in anios:
                n += 1
                k += r == str(tipos.ResultadoEvento.PRESENTE)
    return k, n


def _e2_en_clase(evs, anios, h: str, calendario, memoria) -> dict[int, list[int]]:
    """Partes informativas de E2 con j* definido: c_H(R) → [con j* = c_H(R) mód 3, total]."""
    salida: dict[int, list[int]] = {}
    for ev in evs:
        m = ev.metricas_e2
        m = m[(m["nivel"] == str(Nivel.PARTE)) & m["informativa"].astype(bool) & m["j_estrella"].notna()
              & m["regimen"].notna()]
        for a, r, j in zip(m["anio"], m["regimen"], m["j_estrella"]):
            if (ev.info.codigo, int(a)) not in anios:
                continue
            c = _desfases_de(ev, int(a), h, calendario, memoria).get(str(r))
            if c is None:
                continue
            cuenta = salida.setdefault(int(c), [0, 0])
            cuenta[0] += int(j) == lineas_registro.clase_mod3(int(c))
            cuenta[1] += 1
    return salida


def _e3p_anios(evs, anios, h: str, calendario, memoria, *, con_e4p: bool) -> tuple[int, int]:
    """Estación-años con ĉ de E3p (QFE, regla gruesa) definido en algún año-régimen: (los que tienen ĉ = c_H(R)
    en todos esos años-régimen y, con ``con_e4p``, E4p anual compatible con H; total)."""
    k = n = 0
    for ev in evs:
        m = _regimenes(ev.metricas_e3, "QFE", ESQUEMA_METRICAS_E3)
        m = m[m["c_hat"].notna()]
        e = ev.estados
        e4 = e[(e["linea"] == str(Linea.E4P)) & (e["nivel"] == str(Nivel.ANIO)) & (e["H"] == h)]
        e4p = {int(a): str(est) for a, est in zip(e4["anio"], e4["estado"])}
        for a, g in m.groupby("anio", sort=True):
            a = int(a)
            if (ev.info.codigo, a) not in anios:
                continue
            c = _desfases_de(ev, a, h, calendario, memoria)
            if not c:
                continue
            n += 1
            bien = all(str(r) in c and int(ch) == c[str(r)] for r, ch in zip(g["unidad"], g["c_hat"]))
            k += bien and (not con_e4p or e4p.get(a) == str(Estado.COMPATIBLE))
    return k, n


def _fina(evs, anios, h: str, calendario, memoria, consecuencias) -> dict[int, list[int]]:
    """Años-régimen finos con ĉ^f definido, donde la regla fina rige (A3 y apagado de estación, como
    decision): c_H(R) → [con ĉ^f = c_H(R), total]."""
    salida: dict[int, list[int]] = {}
    for ev in evs:
        if consecuencias is not None and not consecuencias.fina_activa(ev.info.macrozona):
            continue
        e = ev.estados
        if bool(((e["linea"] == str(Linea.E3P)) & (e["regla"] == str(Regla.FINA)) & (e["nivel"] == str(Nivel.ESTACION))
                 & (e["motivo"] == str(MotivoSinInfo.APAGADA)).fillna(False)).any()):
            continue
        m = _regimenes(ev.metricas_e3, "QFE", ESQUEMA_METRICAS_E3)
        m = m[m["fino"].astype(bool) & m["c_hat_f"].notna()]
        for a, r, cf in zip(m["anio"], m["unidad"], m["c_hat_f"]):
            if (ev.info.codigo, int(a)) not in anios:
                continue
            c = _desfases_de(ev, int(a), h, calendario, memoria).get(str(r))
            if c is None:
                continue
            cuenta = salida.setdefault(int(c), [0, 0])
            cuenta[0] += int(cf) == int(c)
            cuenta[1] += 1
    return salida


def _e1b_aerodromos(evs, anios) -> tuple[int, int, dict[str, int]]:
    """Aeródromos de operación civil = estaciones con algún cambio real de E1b evaluado con |δ| = 1 (δ = 0 no
    informa, §4.1.2): (los que tienen δ = −1 en todos esos cambios, total, conteo de δ)."""
    k = n = 0
    deltas: Counter = Counter()
    for ev in evs:
        e = ev.eventos
        e = e[(e["linea"] == str(Linea.E1B)) & (e["clase_evento"] == _REAL)
              & (e["resultado"] == lineas_registro.E1B_EVALUADO) & e["delta"].notna()]
        propios = [int(d) for a, d in zip(e["anio"], e["delta"]) if (ev.info.codigo, int(a)) in anios and abs(int(d)) == 1]
        if propios:
            n += 1
            k += all(d == DELTA_E1B_FIJAS for d in propios)
            deltas.update(str(d) for d in propios)
    return k, n, dict(sorted(deltas.items()))


def _guardas_con_fallas(evs, anios, h: str) -> tuple[int, int]:
    """Estación-años con alguna guarda de §5.1 o G-versión evaluada (pasa o falla) bajo H o «*»: (con
    alguna falla, total). Son las precalculadas para toda H de P (fase 4)."""
    k = n = 0
    evaluadas = (str(ResultadoGuarda.PASA), str(ResultadoGuarda.FALLA))
    for ev in evs:
        g = ev.guardas
        g = g[g["guarda"].isin(_GUARDAS_PREDICCION) & g["H"].isin([h, H_TODAS]) & g["resultado"].isin(evaluadas)]
        for a, sub in g.groupby("anio", sort=True):
            if (ev.info.codigo, int(a)) not in anios:
                continue
            n += 1
            k += bool((sub["resultado"] == str(ResultadoGuarda.FALLA)).any())
    return k, n


def _patron_civil_e1a(evs, zona: str, h: str) -> tuple[int, int, int, int]:
    """Estaciones con algún adelanto real de E1a evaluable en ``zona``: (con patrón civil(Z), total,
    placebos ausentes, placebos evaluables). Hay patrón civil si un evento ausente deja a C(Z) compatible,
    que en lineas_registro.e1a sólo ocurre con el patrón (§4.1.1); así la regla no se copia aquí. Los
    placebos son los del mismo día de la semana y los del A2; los eventos «regla_vencida» de la Enmienda 3
    (E3-2) no cuentan (RED-10)."""
    k = n = pl_aus = pl = 0
    for ev in evs:
        e = ev.eventos
        e = e[(e["linea"] == str(Linea.E1A)) & (e["zona"] == zona) & e["resultado"].isin(_EVALUABLES_E1A)]
        reales = e[e["clase_evento"] == _REAL]
        if not len(reales):
            continue
        n += 1
        placebos = e[~e["clase_evento"].isin([_REAL, _REGLA_VENCIDA])]
        pl += len(placebos)
        pl_aus += int((placebos["resultado"] == str(tipos.ResultadoEvento.AUSENTE)).sum())
        ausentes = reales[reales["resultado"] == str(tipos.ResultadoEvento.AUSENTE)]
        ids = {lineas_registro.id_evento(zona, date.fromisoformat(str(f)), str(t), _REAL)
               for f, t in zip(ausentes["fecha_D"], ausentes["tipo"])}
        est = ev.estados
        compat = est[(est["linea"] == str(Linea.E1A)) & (est["nivel"] == str(Nivel.EVENTO)) & (est["H"] == h)
                     & (est["estado"] == str(Estado.COMPATIBLE)) & est["unidad"].isin(sorted(ids))]
        k += bool(len(compat))
    return k, n, pl_aus, pl


def _sumar(cuentas: Mapping[int, Sequence[int]]) -> tuple[int, int]:
    return sum(v[0] for v in cuentas.values()), sum(v[1] for v in cuentas.values())


def _por_desfase(cuentas: Mapping[int, Sequence[int]]) -> dict[str, dict]:
    return {f"{c:+d}" if c else "0": {"k": int(v[0]), "n": int(v[1])} for c, v in sorted(cuentas.items(), reverse=True)}


def predicciones(evidencias: Sequence[EvidenciaEstacion], decisiones: Sequence[DecisionAnio], *,
                 consecuencias: ConsecuenciasRed | None = None, calendario=None) -> dict:
    """§1.13 para N: cada predicción con lo observado (k de n) y «cumplida», «predicción no cumplida» o
    «sin_datos» si no hay unidades evaluables. Nunca es una desviación. Lecturas en RED-10.

    ``decisiones`` dan los estación-años con datos (veredicto distinto de «sin_datos»), los únicos que
    entran; ``consecuencias`` (fase 7), A3 y A5 y dónde rige la regla fina (sin ellas, esa predicción queda
    «sin_datos» y la fina se mira en todas las macrozonas); ``calendario``, c_H(R) cuando la evidencia no
    trae ``clases`` (RED-4)."""
    evs = [ev for ev in evidencias if ev.info.conjunto == Conjunto.N]
    codigos = {ev.info.codigo for ev in evs}
    anios = {(d.codigo, int(d.anio)) for d in decisiones if d.codigo in codigos and d.veredicto != Veredicto.SIN_DATOS}
    memoria: dict = {}
    pres = _e1a_presentes(evs, anios)
    bloques: dict[str, list[dict]] = {}

    # Si la red está en UTC, F(0).
    e2 = _sumar(_e2_en_clase(evs, anios, F0, calendario, memoria))
    a3_a5, k_a, n_a = None, 0, 0
    if consecuencias is not None:
        alto = bool(consecuencias.a3_falla_pais or consecuencias.a3_fallan_macrozonas or consecuencias.a5_alto)
        a3_a5 = {"a3_falla_pais": bool(consecuencias.a3_falla_pais),
                 "a3_fallan_macrozonas": sorted(consecuencias.a3_fallan_macrozonas), "a5_alto": bool(consecuencias.a5_alto)}
        k_a, n_a = int(not alto), 1
    k_b, n_b, deltas = _e1b_aerodromos(evs, anios)
    bloques[F0] = [
        _prediccion("E1a_presente", "adelantos reales de E1a: presentes / evaluables (presente o ausente)", *pres,
                    minimo=_pct("PRED_E1A_PRESENTE_PCT")),
        _prediccion("E2_clase", "partes informativas de E2 con j* = c_H mód 3", *e2, minimo=_pct("PRED_E2_CLASE_PCT")),
        _prediccion("E3p_E4p", "estación-años con ĉ de E3p definido: ĉ = c_H(R) en todos sus años-régimen y E4p "
                    "anual compatible con H", *_e3p_anios(evs, anios, F0, calendario, memoria, con_e4p=True),
                    minimo=_pct("PRED_E3P_E4P_ANIOS_PCT")),
        _prediccion("E1b_delta", "aeródromos con algún cambio real de E1b evaluado con |δ| = 1: δ = −1 en todos",
                    k_b, n_b, deltas=deltas),
        _prediccion("guardas", "estación-años con alguna guarda evaluada bajo H o «*»: con alguna falla",
                    *_guardas_con_fallas(evs, anios, F0), maximo=_pct("PRED_GUARDAS_FALLAS_PCT")),
        _prediccion("A3_A5_sin_alto", "A3 sin falla en el país ni en las macrozonas y A5 sin alto",
                    k_a, n_a, controles=a3_a5),
    ]

    # Si está en F(−4).
    e2_f4 = _sumar(_e2_en_clase(evs, anios, F_MENOS4, calendario, memoria))
    bloques[F_MENOS4] = [
        _prediccion("E1a_presente", "adelantos reales de E1a: presentes / evaluables (presente o ausente)", *pres,
                    minimo=_pct("PRED_F_MENOS4_PCT", 0)),
        _prediccion("E2_clase", "partes informativas de E2 con j* = c_H mód 3", *e2_f4,
                    minimo=_pct("PRED_F_MENOS4_PCT", 1)),
        _prediccion("E3p", "estación-años con ĉ de E3p definido: ĉ = c_H(R) en todos sus años-régimen",
                    *_e3p_anios(evs, anios, F_MENOS4, calendario, memoria, con_e4p=False),
                    minimo=_pct("PRED_F_MENOS4_PCT", 2)),
    ]

    # Si está en C(Santiago).
    zona = Hipotesis.desde_id(C_SANTIAGO).zona
    k_p, n_p, pl_aus, pl = _patron_civil_e1a(evs, zona, C_SANTIAGO)
    e2_civil = _e2_en_clase(evs, anios, C_SANTIAGO, calendario, memoria)
    fina = _fina(evs, anios, C_SANTIAGO, calendario, memoria, consecuencias)
    bloques[C_SANTIAGO] = [
        _prediccion("E1a_patron_civil", f"estaciones con algún adelanto real de E1a evaluable en {zona}: con "
                    "patrón civil", k_p, n_p, minimo=_pct("PRED_CIVIL_E1A_PCT")),
        _prediccion("E1a_placebos", f"placebos de E1a evaluables en {zona} (de esas estaciones): ausentes",
                    pl_aus, pl, maximo=_pct("PRED_CIVIL_PLACEBOS_PCT")),
        _prediccion("E2_clase", "partes informativas de E2 con j* = c_H(R) mód 3 (verano −3 → 0; invierno −4 → 2)",
                    *_sumar(e2_civil), por_desfase=_por_desfase(e2_civil)),
        _prediccion("E3p_fina", "años-régimen finos con ĉ^f definido, donde rige la regla fina: ĉ^f = c_H(R) "
                    "(verano −3, invierno −4)", *_sumar(fina), por_desfase=_por_desfase(fina)),
    ]
    por_reloj = {}
    for reloj, lista in bloques.items():
        resultados = Counter(p["resultado"] for p in lista)
        por_reloj[reloj] = {"predicciones": lista,
                            "cumplidas": resultados[PREDICCION_CUMPLIDA],
                            "no_cumplidas": resultados[PREDICCION_NO_CUMPLIDA],
                            "sin_datos": resultados[PREDICCION_SIN_DATOS]}
    return {"conjunto": str(Conjunto.N), "nota": NOTA_PREDICCIONES, "n_estaciones": len(evs),
            "n_estacion_anios": len(anios), "por_reloj": por_reloj}
