"""Candidatos (§4.2-§4.9): núcleo, A, B, AB, C y C_est, selección anidada y predicción en las estaciones de prueba.

R es la corrección del candidato: nunca se guarda ni se informa (§0.4.3). Este módulo es puro: recibe tablas, matrices y
los umbrales (un objeto con ``.a`` y ``.frac``) y devuelve arreglos, tablas y diccionarios en memoria; no lee ni escribe
archivos. Las sumas van en float64; los residuos guardados en float32 (``ESQUEMA_RESIDUOS``) se leen como float64.

Dueño: I13 (ola 3; CAN-18 en la ola 4 y CAN-19 en la ola 6).
Lecturas propias (CAN-n), para el addendum de M1:
- CAN-1. **Distancia y vecinos (§4.2).** d_ef = √(d_h² + (λ·|z_x − z_s|/1.000)²), con d_h por haversine (R = 6.371 km,
  ``numerico.haversine_km``) y z en m. El corte «d_ef ≤ 3L» es inclusivo (``NUC_CORTE``·L). Los vecinos de un punto
  son, entre las estaciones de entrenamiento del pliegue, las ``NUC_VECINOS`` más cercanas en d_ef dentro del corte,
  con los empates por el menor código (MC-60; orden estable sobre los códigos ordenados). La lista es fija por punto y
  la disponibilidad se aplica hora a hora (literal de §4.2): una estación de entrenamiento sin ningún q definido para
  la variable o el candidato (sin la variable, δ NaN, nunca calificada en A) ocupa igual su lugar en la lista y nunca
  está disponible. Es la lectura literal y rige mientras la pregunta P-CAN-1 siga abierta.
- CAN-2. **Pesos de grupo (§2.5, «cada miembro disponible pesa 1/(miembros disponibles a esa hora)»).** Los miembros
  disponibles se cuentan entre todas las estaciones de entrenamiento del grupo con q definido a esa hora, no sólo
  entre las que están en la lista de vecinos del punto: el peso es de la estación y la hora, igual para todos los
  puntos. El peso va en el numerador y en el denominador de Φ (§3 del diseño: «van dentro de q y de la
  disponibilidad»); el Σk que se devuelve es Σ k·w, que es 0 si y sólo si Σk sobre las disponibles es 0.
- CAN-3. **Campo (§4.2).** Φ = Σ k·w·q / (κ + Σ k·w), con k = exp(−½(d_ef/L)²) (``NUCLEO_MEDIO``). ``sumas_nucleo`` da
  los dos productos dispersos (una matriz CSR punto × estación con los índices ordenados, en float64) y κ se aplica
  al final, así que las cuatro κ cuestan una pasada por (L, λ). Con κ > 0 nunca hay NaN: sin soporte, Φ = 0.
- CAN-4. **Climatología de A (§4.3).** Sobre r (sin homogeneizar, MC-65), en las horas observadas válidas de los meses
  m − ``A_VENTANA_MESES`` … m + ``A_VENTANA_MESES`` (cíclicos) de todos los años. Requisitos: ≥ ``A_MIN_N`` valores;
  ≥ ``A_MIN_ANIOS`` años UTC distintos entre esos valores (el año calendario de cada hora); y hueco circular de las
  horas UTC distintas ≤ ``A_HUECO_H`` (MC-27). Armónicos k = 1, 2, y 3 con ≥ ``A_HORAS_K3`` horas UTC distintas; los
  períodos ``A_P1_H``, ``A_P2_H`` y ``A_P3_H`` deben ser 24/k. Recorte ``U.frac("A_RECORTE_PCT")`` por cola y un
  segundo ajuste (``numerico.armonico_recortado``); r̄_s(m, h) es el ajuste en las 24 horas UTC. **D19:** si el
  segundo ajuste no tiene rango completo (``DisenoDeficiente``), la estación no entra en A ese mes, igual que sin los
  requisitos: ``califica`` = False y ``rbar`` = NaN en sus 24 horas (y por §4.5 tampoco entra a Φ′ ese mes).
- CAN-5. **A en el tiempo (MC-41).** A(x, m, h) es Φ con q_s = r̄_s(m, h) sobre las estaciones calificadas en m (los
  pesos de grupo cuentan las calificadas). En una hora u, A se interpola linealmente entre los centros de los dos
  meses calendario que la rodean (el centro es el punto medio entre la primera y la última hora UTC del mes), con la
  hora UTC de u en los dos meses; la interpolación sigue el calendario, así que diciembre se une con el enero
  siguiente. El soporte (Σk) se interpola con los mismos pesos.
- CAN-6. **B (§4.4) y las horas no observadas.** r̃ es ``rt_T``/``rt_Td`` de la tabla de residuos (homogeneizado; con
  δ NaN, D40, r̃ queda NaN y la estación nunca está disponible en B ni en AB); u, v y p no se segmentan y r̃ = r. Una
  hora sin reporte se interpola linealmente si los reportes que la rodean (las filas observadas vecinas de la tabla,
  válidas o no) son los dos válidos y están a ≤ ``B_INTERP_H`` h: un reporte inválido en medio corta la
  interpolación (la lectura estricta de «reportes válidos consecutivos»). ``candidatos`` rehace siempre esa
  interpolación desde las filas observadas guardadas (float32), en float64, y no usa los valores interpolados de la
  tabla: así la corrida que lee del disco y la que trae la tabla en memoria dan lo mismo.
- CAN-7. **AB (§4.5, MC-42).** a_s(u) = r̃_s(u) − r̄_s(m, h), con m el mes de u y h su hora UTC, sin interpolar; es NaN
  donde la estación no califica en A ese mes («Sólo entran a Φ′ las estaciones que entran en A»). En las horas no
  observadas se interpola la anomalía a con la regla de CAN-6 («interpolada en horas no observadas como en B», literal).
  R_AB = A (con los hiperparámetros de A) + Φ′ (con los suyos, sobre a).
- CAN-8. **Tabla de residuos (``residuos_estacion``).** Una fila por hora con reporte (``observada``) y una por hora
  sin reporte que alguna variable puede interpolar (``interpolable``, con r_* NaN). Los residuos se redondean a
  float32 antes de todo (es lo que se guarda); los tramos y δ de §4.8 salen de ``homogeneidad`` sobre esos valores en
  T y Td; g es el tramo del mes2000 de la hora (−1 fuera de los tramos); r̃ = r − δ(g), redondeado a float32.
- CAN-9. **Diseño de C (§4.6).** Predictores base (31): los 14 estáticos z y Δz (km), log(1 + distancia a la costa)
  (``log_dist_costa``), TPI a 1 y a 5 km, pendiente, las 7 fracciones ``lulc_*`` y la latitud de la celda; las 5
  indicadoras de macrozona (D22 (a): ``tipos.indicadoras_macrozona`` del ``macrozona_cod`` de la celda, todas 0 con
  «sin_region» o «insular»); los 4 armónicos horarios (seno y coseno de 2πh/24 y 4πh/24, h = hora UTC) y los 4
  anuales (seno y coseno de 2π·doy/365,25 y 4π·doy/365,25, doy = día del año 1…366 de la fecha UTC); y el estado
  T_F, T_F − Td_F, rapidez √(u_F² + v_F²) y ``amp_TF``. Interacciones (124): cada uno de los 14 estáticos por los 4
  horarios y los 2 anuales de primer orden; las 5 indicadoras por los 4 horarios (por eso «cada estático» no incluye
  las indicadoras: tienen su propia línea); Δz por la rapidez y por T_F − Td_F; TPI (1 y 5 km) por la rapidez; y TPI
  por los 4 horarios por los 2 anuales de primer orden (seno y coseno: «el armónico anual de primer orden» es el par).
  Con la constante son 156 columnas. z es ``z_media`` de la celda y Δz = (``z_media`` − ``z_e5l``)/1.000, con
  ``z_e5l`` la altitud del fondo en la celda (Σ w_i z_E5L,i del operador de la celda): son estáticos de la celda, los
  mismos en todos los usos (pregunta P-CAN-3; la columna ``z_e5l`` es el pedido PED-2).
- CAN-10. **El estado.** En C, el de ``puntos_e5l`` en la hora (A1: los float32 guardados, en float64), sin recortar
  de nuevo T_F − Td_F (Td_F ya es mín(Td_F, T_F), §4.1). En C_est, ``clima_estado`` en el mes y la hora UTC de cada h
  (A14; D29: T − Td ya viene recortado hora a hora). Sin estado finito no hay fila.
- CAN-11. **Estandarización (§4.6, §4.9, MC-45, D33).** Cada predictor base se estandariza con la media y el desvío
  ponderados (desvío poblacional) de las filas de entrenamiento, con los pesos de las filas; las interacciones son
  productos de predictores base estandarizados y no se estandarizan otra vez. El TPI truncado no entra a la media ni
  al desvío y vale 0 después (la fórmula de ``estaticas_nasadem.estandarizar_tpi``, copiada con su prueba de
  paridad mientras rija PED-1). Un predictor constante en el entrenamiento (varianza ≤ √ε·E[x²]) vale 0. Todo se
  deriva de las sumas por estación: el diseño en bruto son los monomios de las variables base (y de 1 − t y
  (1 − t)·TPI, con t el truncado) que aparecen al expandir los productos, y el diseño estandarizado es su
  transformación lineal (``diseno_estandarizado``), así que X'WX y X'Wy de cada pliegue salen de las sumas de sus
  estaciones de entrenamiento sin volver a las filas.
- CAN-12. **Ridge (NUM-9).** Sólo la constante va sin penalizar (``sin_penalizar`` = 1). Respuesta r de la variable
  (u y v por separado; r_p en la presión).
- CAN-13. **Filas de C (§4.6, MC-05, MC-44).** Por estación y variable, las horas observadas con r finito y diseño
  finito; hasta ``C_FILAS`` sin reposición con ``numerico.generador(SEMILLA, "C", código, variable)``, la misma
  etiqueta para C y C_est (con el mismo conjunto de horas válidas, las mismas filas: «C ajustado de nuevo con el mismo
  diseño»); peso mín(``C_FILAS``/n_s; ``C_PESO_MAX``) con n_s = filas de s en la muestra (MC-05). **D34:** una
  estación que entra sin celda (fuera de la grilla, ``_fuera_de_la_grilla``) no tiene estáticos: no aporta filas a C
  ni a C_est y su predicción de C y C_est es NaN, pero entrena A, B y AB (está en la lista de vecinos). D34 es sólo
  eso: una estación que entra con celda y cuya celda falta en los estáticos (§4.6: «Los estáticos de una estación son
  los de su celda»), o a la que le falta su fondo en ``puntos_e5l`` (C) o su clima en ``clima_estado`` (C_est, A14),
  es un insumo incompleto y da ``ErrorCandidatos`` en las filas, la selección y la predicción, en vez de esconderse
  como «sin soporte» de C. Una estación excluida no entra a nada (PAR-1) y se salta.
- CAN-14. **Selección anidada (§4.9).** Pliegues internos de ``particiones.pliegues_internos`` (los de P2 con su
  amortiguador). Para cada estación de prueba interna, las horas observadas con r válido de los días de selección
  (``particiones.dias_de_seleccion``; ``recorte`` lo fija el addendum de M1) en que el objetivo está definido: r̄
  (A, en el mes y la hora UTC de la hora, sin interpolar, como MC-42), r̃ (B), a (AB) o r (C y C_est). El
  entrenamiento usa todos sus datos (las climatologías y las filas de C son de todo el registro; en B y AB, sus
  valores en esas mismas horas). Se acumulan por estación la suma de cuadrados y el número de horas, una vez por
  combinación, y el objetivo (los pesos del uso de §5.3 en el pliegue interno) lo calcula la función ``objetivo`` de
  quien llama (PED-3): este módulo no puede importar ``validacion``. Gana el menor valor finito; con un empate exacto
  (MC-63), el primero en el orden del texto (L, λ, κ o α). Viento: u y v eligen juntos sus hiperparámetros con el error
  vectorial (Δu² + Δv², en las horas con las dos; MC-43); en C y C_est también α (por analogía con MC-43: el grupo
  (u, v) tiene un solo ganador). AB elige Φ′ sobre a con A fijado: los hiperparámetros de A no entran al error de a.
  **D34 en la selección:** una estación de prueba interna fuera de la grilla no entra al objetivo de ningún candidato
  («Sale de la evaluación de todos los candidatos»), aunque sigue entrenando A, B y AB (pregunta P-CAN-5).
- CAN-15. **Predicción en las estaciones de prueba.** En todas sus horas observadas (filas ``observada``), con los
  hiperparámetros dados y el entrenamiento del pliegue externo; por lotes de un mes UTC (MC-37: cada hora se calcula
  sola, así que el lote no cambia ningún valor). Soporte: en el núcleo Σk > 0 (A con el Σk interpolado de CAN-5; AB si
  A o Φ′ lo tienen); en C y C_est, predicción finita. C_est es sólo de lo crónico (§4.7, «Candidato C_est (sólo lo
  crónico)»): ``predecir_prueba`` lo rechaza en otro uso con la misma guarda que ``seleccionar``.
- CAN-16. **Errores.** Una entrada mal formada o incompleta (también la de CAN-13) es ``ErrorCandidatos`` (un
  ValueError); una selección sin ningún objetivo finito es ``SinSeleccion``: no se inventa un ganador.
- CAN-17. **Área de aplicabilidad (§4.6).** ``fuera_de_rango_c`` marca las celdas con algún estático en bruto (los 14
  y las 5 indicadoras) fuera del rango [mín, máx] de las celdas de las estaciones de entrenamiento; un TPI truncado
  (que vale 0 tras estandarizar) no cuenta ni en el rango ni en la celda. La fracción de población la calcula quien
  llama (``validacion`` o ``producto``) con los pesos de 2020.
- CAN-18. **Costo del diseño de C (ola 4; no cambia ningún bit ni ningún error).** Las indicadoras de macrozona se
  calculan con ``tipos.indicadoras_macrozona`` una vez por código distinto, en el orden en que aparecen (el primer
  código desconocido da el mismo error que fila a fila), y se reparten con el índice inverso; un ``macrozona_cod`` que
  no es entero de numpy sigue fila a fila. El diseño en bruto se arma por bloques de ``_BLOQUE_FILAS`` filas y cada
  prefijo de un monomio se calcula una vez: cada valor sale de las mismas multiplicaciones, en el mismo orden
  (((1·a₁)·a₂)·a₃, con los átomos del monomio en su orden); B se apila con las mismas columnas. Ninguna suma cambia de
  orden: el producto de matrices de ``diseno_estandarizado`` y ``predecir_c``, lo que más cuesta ahora, es el de
  siempre. ``test_candidatos`` (``PruebasCan18``) compara bit a bit con una copia literal de la versión de la ola 3.
- CAN-19. **Memoria de la selección (ola 6; no cambia ningún bit ni ningún error).** (1) La caché por
  ``DatosCompetencia`` (``_CACHE``) ya no guarda series: por estación, sólo la referencia a su tabla de residuos
  validada una vez (``_Tabla``: sin copia ni arreglos propios) con dos datos (si las horas de sus filas van crecientes y
  sin repetir, y cuántas son observadas), y r̄ por estación y variable (12 × 24). No crece con las horas: ≈ 7 MB con la
  red entera (antes ≈ 316 B por estación-hora observada, ≈ 16 GB). (2) «r» y «rt» se leen de la tabla en cada uso
  (float32 a float64, exacto). ``_matriz_en_horas`` busca cada hora pedida entre las filas de la tabla: una observada da
  su r o r̃ (en «a», menos r̄, la misma resta valor a valor); en «b» y «a», una hora que no es observada se interpola en
  ese momento entre las dos filas observadas que la rodean, con las condiciones de CAN-6 (las dos válidas, a
  ≤ ``B_INTERP_H`` h, un reporte inválido en medio corta) y la misma cuenta que ``interpolar_no_observadas``
  (t = paso/hueco entre enteros; (1 − t)·v₀ + t·v₁): cada hora es su propia cuenta. ``B_INTERP_H`` y r̄ se leen donde
  los leía la serie armada, así que los errores son los mismos y en el mismo orden. Una tabla cuyas horas no van
  crecientes se busca como antes, en la serie armada en el momento (``_serie``). (3) ``_sse_c`` arma el diseño de cada
  estación de prueba interna dos veces con los mismos argumentos (para las filas finitas y para predecir) y lo suelta
  al terminar con ella, en vez de retener el de todas; los modelos de cada α se resuelven antes, en el mismo orden, y
  cada suma de cuadrados se acumula en el orden de siempre. (4) ``sumas_nucleo`` va por bloques de ``_BLOQUE_HORAS``
  horas (sólo memoria, como ``_BLOQUE_FILAS``; cada hora es su propia cuenta, MC-37). (5) El fondo de C sólo se lee en
  las horas pedidas: en la selección, las de los días de selección de cada estación de prueba interna; en la
  predicción, todas las observadas de las estaciones de prueba del externo (PED-10: recortado a eso, las salidas son
  las mismas). Medido (mundo sintético de ``costo``, 579 estaciones, 4 años, un pliegue de P2, las 26 selecciones):
  el pico de la selección sobre la ``DatosCompetencia`` baja de 7.278 MB a 85 MB, con los mismos 26 hiperparámetros y
  las mismas 30 predicciones. ``test_candidatos`` (``PruebasCan19``) compara bit a bit con una copia literal de la ola 4.
Depende de: tipos, constantes, numerico, particiones y homogeneidad. Los umbrales llegan como objeto; la tabla de §1
del diseño permite además ``umbrales``, que no hace falta importar.
"""
from __future__ import annotations

import math
import weakref
from dataclasses import dataclass
from itertools import product
from typing import Any, Callable, Mapping

import numpy as np
import pandas as pd
from scipy import sparse

from meteo_combinada import constantes, homogeneidad, numerico, particiones, tipos
from meteo_combinada.tipos import Candidato, DisenoC, Hiper, ModeloC, Pliegue, Uso, Variable

HORAS_DIA = 24
MESES_ANIO = 12
M_POR_KM = 1000
SIN_VECINO = -1
_LOTE_PUNTOS = 4096                              # puntos por lote al buscar vecinos (sólo memoria)
_BLOQUE_HORAS = 1024                             # horas por bloque en sumas_nucleo (sólo memoria; CAN-19)
_EPOCA_H = np.datetime64("2000-01-01T00", "h")   # h = 0 (tipos.EPOCA_H)
_EPOCA_M = np.datetime64("2000-01", "M")
_NUCLEO_MEDIO = float(constantes.valor("NUCLEO_MEDIO"))          # el ½ de exp(−½ (d_ef/L)²)
_TOL_VARIANZA = float(np.sqrt(np.finfo(np.float64).eps))          # CAN-11: predictor constante

VARIABLES = tuple(v.value for v in Variable)                       # T, Td, u, v, p
VIENTO = (Variable.U.value, Variable.V.value)
UV = tipos.VariableMetrica.UV.value                                 # «uv»: u y v juntos (MC-43)
SEGMENTADAS = (Variable.T.value, Variable.TD.value)                 # §4.8: «Viento y presión no se segmentan»
COLUMNA_R = {v: f"r_{v}" for v in VARIABLES}
COLUMNA_RT = {v: f"rt_{v}" for v in SEGMENTADAS}
COLUMNA_G = {v: f"g_{v}" for v in SEGMENTADAS}
DE_C = (Candidato.C, Candidato.C_EST)
COLUMNA_Z_C = "z_media"                     # CAN-9 (P-CAN-3): z de la celda en C, igual en todos los usos
COLUMNA_Z_E5L = "z_e5l"                     # CAN-9 (PED-2): altitud del fondo en la celda, en m
COLUMNAS_PREDICCION = {"codigo": "string", "h": "int32", "correccion": "float64", "soporte": "bool"}   # PED-4


class ErrorCandidatos(ValueError):
    """Entrada mal formada para un candidato (CAN-16)."""


class SinSeleccion(ErrorCandidatos):
    """Ninguna combinación de hiperparámetros dio un objetivo finito (CAN-16)."""


# ---------------------------------------------------------------------------
# Utilidades de tiempo y de umbrales
# ---------------------------------------------------------------------------
def _horas(h, nombre: str = "h") -> np.ndarray:
    arr = np.asarray(h)
    if arr.ndim != 1:
        raise ErrorCandidatos(f"{nombre} debe ser de una dimensión")
    if arr.dtype == bool or not np.issubdtype(arr.dtype, np.integer):
        raise ErrorCandidatos(f"{nombre} debe ser entero (horas desde 2000-01-01T00Z), no {arr.dtype}")
    return arr.astype(np.int64)


def _crecientes(h: np.ndarray, nombre: str) -> None:
    if h.size > 1 and not bool(np.all(np.diff(h) > 0)):
        raise ErrorCandidatos(f"{nombre}: las horas deben ir crecientes y sin repetir")


def _entero(U, ident: str) -> int:
    v = U.a(ident)
    if isinstance(v, bool) or not isinstance(v, (int, np.integer)):
        raise ErrorCandidatos(f"{ident} debe ser entero: {v!r}")
    return int(v)


def _mes_y_hora(h: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(mes2000, mes 1-12, hora UTC) de cada hora."""
    m2000 = homogeneidad.mes2000(h)
    return m2000, np.mod(m2000, MESES_ANIO) + 1, np.mod(h, HORAS_DIA)


def _anio(h: np.ndarray) -> np.ndarray:
    return homogeneidad.mes2000(h) // MESES_ANIO


def _dia_del_anio(h: np.ndarray) -> np.ndarray:
    """Día del año (1…366) de la fecha UTC de cada hora (CAN-9)."""
    dias = (_EPOCA_H + h.astype("timedelta64[h]")).astype("datetime64[D]")
    inicio = dias.astype("datetime64[Y]").astype("datetime64[D]")
    return (dias - inicio).astype(np.int64) + 1


def _inicio_mes_h(m2000: np.ndarray) -> np.ndarray:
    """Hora (desde 2000-01-01T00Z) de la primera hora de cada mes2000."""
    meses = _EPOCA_M + np.asarray(m2000, dtype=np.int64).astype("timedelta64[M]")
    return (meses.astype("datetime64[h]") - _EPOCA_H).astype(np.int64)


def _centro_mes(m2000: np.ndarray) -> np.ndarray:
    """MC-41: el punto medio entre la primera y la última hora UTC del mes."""
    return (_inicio_mes_h(m2000) + _inicio_mes_h(np.asarray(m2000) + 1) - 1) / 2


def _interpolacion_mensual(h: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """CAN-5: índices de mes (0-11) de los dos centros que rodean cada hora y el peso t del segundo."""
    m = homogeneidad.mes2000(h)
    antes = h < _centro_mes(m)
    m_a = np.where(antes, m - 1, m)
    c_a, c_b = _centro_mes(m_a), _centro_mes(m_a + 1)
    t = (h - c_a) / (c_b - c_a)
    return np.mod(m_a, MESES_ANIO), np.mod(m_a + 1, MESES_ANIO), t


# ---------------------------------------------------------------------------
# Puntos y estaciones
# ---------------------------------------------------------------------------
def puntos_de_estaciones(infos: Mapping[str, Any], codigos=None) -> dict:
    """{ids, lat, lon, z} de las estaciones (z = z_s), en el orden de ``codigos`` (por omisión, los códigos
    ordenados). Es la forma de «puntos» que aceptan ``distancia_efectiva`` y ``vecinos``."""
    codigos = tuple(sorted(infos)) if codigos is None else tuple(codigos)
    return {"ids": np.array(codigos, dtype=object),
            "lat": np.array([float(infos[c].lat) for c in codigos], dtype=np.float64),
            "lon": np.array([float(infos[c].lon) for c in codigos], dtype=np.float64),
            "z": np.array([float(infos[c].z_s) for c in codigos], dtype=np.float64)}


def _puntos(obj) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(ids, lat, lon, z): de un dict o DataFrame con «lat», «lon» y «z» (e «ids» opcional), o de un mapa
    código → InfoEstacion (z = z_s)."""
    if isinstance(obj, pd.DataFrame) or (isinstance(obj, Mapping) and "lat" in obj):
        faltan = [c for c in ("lat", "lon", "z") if c not in obj]
        if faltan:
            raise ErrorCandidatos(f"a los puntos les faltan {faltan}")
        lat, lon, z = (np.asarray(obj[c], dtype=np.float64).ravel() for c in ("lat", "lon", "z"))
        ids = np.asarray(obj["ids"]).ravel() if "ids" in obj else np.arange(lat.size)
    elif isinstance(obj, Mapping):
        return _puntos(puntos_de_estaciones(obj))
    else:
        raise ErrorCandidatos(f"puntos no reconocidos: {type(obj).__name__}")
    if not (lat.shape == lon.shape == z.shape == ids.shape):
        raise ErrorCandidatos("lat, lon, z e ids de los puntos deben tener el mismo largo")
    return ids, lat, lon, z


def distancia_efectiva(puntos, estaciones, lam: float) -> np.ndarray:
    """d_ef (km) punto × estación: √(d_h² + (λ·|z_x − z_s|/1.000)²) (§4.2, CAN-1)."""
    lam = float(lam)
    if not (math.isfinite(lam) and lam >= 0):
        raise ErrorCandidatos(f"λ debe ser finito y ≥ 0: {lam!r}")
    _, la_p, lo_p, z_p = _puntos(puntos)
    _, la_e, lo_e, z_e = _puntos(estaciones)
    dh = numerico.haversine_km(la_p[:, None], lo_p[:, None], la_e[None, :], lo_e[None, :])
    dv = lam * np.abs(z_p[:, None] - z_e[None, :]) / M_POR_KM
    return np.sqrt(dh * dh + dv * dv)


@dataclass(frozen=True, eq=False)
class VecinosEntrenamiento(tipos.VecinosNucleo):
    """``tipos.VecinosNucleo`` con lo que hace falta para los pesos de grupo (CAN-2): los códigos de entrenamiento en
    el orden de los índices de ``est``, los ids de grupo en el orden de ``grupo_de`` y el grupo de cada estación de
    entrenamiento (PED-1 pide pasar estos tres campos a ``tipos``)."""
    codigos: tuple[str, ...]
    grupos: tuple[str, ...]
    grupo_est: np.ndarray


def _hiper(hiper) -> tuple[float, float, float]:
    if not isinstance(hiper, Hiper):
        raise ErrorCandidatos(f"hiper debe ser tipos.Hiper, no {type(hiper).__name__}")
    L, lam, kappa = float(hiper.L_km), float(hiper.lam), float(hiper.kappa)
    if not (math.isfinite(L) and L > 0 and math.isfinite(lam) and lam >= 0 and math.isfinite(kappa) and kappa > 0):
        raise ErrorCandidatos(f"hiperparámetros inválidos: {hiper!r}")
    return L, lam, kappa


def vecinos(puntos, entrenamiento, hiper, umbrales) -> VecinosEntrenamiento:
    """Lista fija de vecinos de cada punto entre las estaciones de entrenamiento (§4.2, CAN-1): ``entrenamiento`` es
    un mapa código → InfoEstacion (``lat``, ``lon``, ``z_s`` y ``grupo``)."""
    L, lam, _ = _hiper(hiper)
    codigos = tuple(sorted(entrenamiento))
    est_pts = puntos_de_estaciones(entrenamiento, codigos)
    if not (np.isfinite(est_pts["lat"]).all() and np.isfinite(est_pts["lon"]).all() and np.isfinite(est_pts["z"]).all()):
        raise ErrorCandidatos("una estación de entrenamiento sin lat, lon o z_s finitos")
    grupo_de_codigo = [entrenamiento[c].grupo for c in codigos]
    if not all(isinstance(g, str) and tipos.PATRON_GRUPO.fullmatch(g) for g in grupo_de_codigo):
        raise ErrorCandidatos("cada estación de entrenamiento necesita su grupo «G<código>» (PAR-1)")
    grupos = tuple(sorted(set(grupo_de_codigo)))
    indice = {g: i for i, g in enumerate(grupos)}
    grupo_est = np.array([indice[g] for g in grupo_de_codigo], dtype=np.int32)
    ids, la, lo, z = _puntos(puntos)
    n_v = _entero(umbrales, "NUC_VECINOS")
    corte = float(umbrales.a("NUC_CORTE")) * L
    n = la.size
    est = np.full((n, n_v), SIN_VECINO, dtype=np.int32)
    d_ef = np.full((n, n_v), np.nan)
    if codigos:
        for i0 in range(0, n, _LOTE_PUNTOS):
            sl = slice(i0, min(n, i0 + _LOTE_PUNTOS))
            D = distancia_efectiva({"lat": la[sl], "lon": lo[sl], "z": z[sl]}, est_pts, lam)
            D = np.where(D <= corte, D, np.inf)                       # NaN (z no finita) también queda fuera
            orden = np.argsort(D, axis=1, kind="stable")[:, :n_v]      # empates: el menor código (MC-60)
            dd = np.take_along_axis(D, orden, axis=1)
            ok = np.isfinite(dd)
            k = orden.shape[1]
            est[sl, :k] = np.where(ok, orden, SIN_VECINO)
            d_ef[sl, :k] = np.where(ok, dd, np.nan)
    grupo_de = np.where(est >= 0, grupo_est[np.maximum(est, 0)] if codigos else SIN_VECINO, SIN_VECINO)
    return VecinosEntrenamiento(puntos=ids, est=est, d_ef=d_ef, grupo_de=grupo_de.astype(np.int32), hiper=hiper,
                                codigos=codigos, grupos=grupos, grupo_est=grupo_est)


def _comprobar_vecinos(vec) -> None:
    if not isinstance(vec, VecinosEntrenamiento):
        raise ErrorCandidatos("vec debe salir de candidatos.vecinos (VecinosEntrenamiento)")


def _matriz_nucleo(vec: VecinosEntrenamiento) -> sparse.csr_matrix:
    """k(x, s) punto × estación de entrenamiento, CSR con los índices ordenados (CAN-3)."""
    L, _, _ = _hiper(vec.hiper)
    n, n_v = vec.est.shape
    ok = (vec.est >= 0).ravel()
    filas = np.repeat(np.arange(n, dtype=np.int64), n_v)[ok]
    cols = vec.est.ravel()[ok].astype(np.int64)
    k = np.exp(-_NUCLEO_MEDIO * (vec.d_ef.ravel()[ok] / L) ** 2)
    K = sparse.csr_matrix((k, (filas, cols)), shape=(n, len(vec.codigos)))
    K.sort_indices()
    return K


def _pesos_grupo(ok: np.ndarray, grupo_est: np.ndarray, n_grupos: int) -> np.ndarray:
    """CAN-2: 1/(miembros disponibles del grupo a esa hora) donde la estación está disponible; 0 si no."""
    n_t = grupo_est.size
    G = sparse.csr_matrix((np.ones(n_t), (np.arange(n_t), grupo_est.astype(np.int64))), shape=(n_t, n_grupos))
    cuenta = np.asarray(G.T.dot(ok.astype(np.float64).T)).T             # hora × grupo, enteros exactos
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(ok, 1.0 / cuenta[:, grupo_est], 0.0)


def sumas_nucleo(vec, q, disponible) -> tuple[np.ndarray, np.ndarray]:
    """Σ k·w·q y Σ k·w (hora × punto), con w los pesos de grupo (CAN-2, CAN-3). ``q`` y ``disponible`` son
    hora × estación de entrenamiento (en el orden de ``vec.codigos``)."""
    _comprobar_vecinos(vec)
    n_t, n_p = len(vec.codigos), vec.est.shape[0]
    q = np.asarray(q, dtype=np.float64)
    disponible = np.asarray(disponible)
    if q.ndim != 2 or q.shape[1] != n_t or disponible.shape != q.shape:
        raise ErrorCandidatos(f"q y disponible deben ser hora × {n_t} estaciones de entrenamiento")
    if disponible.dtype != bool:
        raise ErrorCandidatos("disponible debe ser booleano")
    if n_t == 0 or q.shape[0] == 0:
        ceros = np.zeros((q.shape[0], n_p))
        return ceros, ceros.copy()
    K = _matriz_nucleo(vec)
    num, den = np.empty((q.shape[0], n_p)), np.empty((q.shape[0], n_p))
    for h0 in range(0, q.shape[0], _BLOQUE_HORAS):   # CAN-19: cada hora es su propia cuenta, como en MC-37
        sl = slice(h0, min(q.shape[0], h0 + _BLOQUE_HORAS))
        ok = disponible[sl] & np.isfinite(q[sl])
        w = _pesos_grupo(ok, vec.grupo_est, len(vec.grupos))
        qw = np.where(ok, w * np.where(ok, q[sl], 0.0), 0.0)
        num[sl] = np.asarray(K.dot(qw.T)).T
        den[sl] = np.asarray(K.dot(w.T)).T
    return num, den


def campo(vec, q, disponible) -> tuple[np.ndarray, np.ndarray]:
    """Φ y Σk (hora × punto): Φ = Σ k·w·q/(κ + Σ k·w), con κ de ``vec.hiper`` (§4.2, CAN-3)."""
    num, den = sumas_nucleo(vec, q, disponible)
    _, _, kappa = _hiper(vec.hiper)
    return num / (kappa + den), den


# ---------------------------------------------------------------------------
# Horas no observadas (§4.4, CAN-6) y tabla de residuos (CAN-8)
# ---------------------------------------------------------------------------
def interpolar_no_observadas(h, rt, umbrales) -> tuple[np.ndarray, np.ndarray]:
    """(horas, valores) sin reporte que se interpolan linealmente entre dos reportes consecutivos válidos a
    ≤ ``B_INTERP_H`` h (§4.4, CAN-6). ``h`` son las horas con reporte, crecientes; ``rt`` NaN donde no es válido."""
    h = _horas(h)
    _crecientes(h, "interpolar_no_observadas")
    v = np.asarray(rt, dtype=np.float64)
    if v.shape != h.shape:
        raise ErrorCandidatos("interpolar_no_observadas: rt y h deben tener el mismo largo")
    if h.size < 2:
        return np.empty(0, dtype=np.int64), np.empty(0)
    hueco = np.diff(h)
    par = (hueco >= 2) & (hueco <= _entero(umbrales, "B_INTERP_H")) & np.isfinite(v[:-1]) & np.isfinite(v[1:])
    i = np.flatnonzero(par)
    if i.size == 0:
        return np.empty(0, dtype=np.int64), np.empty(0)
    cuantas = hueco[i] - 1
    base = np.repeat(i, cuantas)
    paso = np.arange(cuantas.sum()) - np.repeat(np.cumsum(cuantas) - cuantas, cuantas) + 1
    t = paso / hueco[base]
    return h[base] + paso, (1.0 - t) * v[base] + t * v[base + 1]


def _tramo_de(meses: np.ndarray, tramos) -> np.ndarray:
    g = np.full(meses.shape, SIN_VECINO, dtype=np.int64)
    for k, (a, b) in enumerate(tramos):
        g[(meses >= a) & (meses <= b)] = k
    return g


def residuos_estacion(codigo: str, h, r: Mapping, umbrales) -> tuple[pd.DataFrame, pd.DataFrame]:
    """La tabla de residuos de una estación (``ESQUEMA_RESIDUOS``) y sus tramos homogéneos
    (``ESQUEMA_TRAMOS_HOMOGENEOS``) desde las horas con reporte ``h`` y los residuos ``r`` {T, Td, u, v, p} (NaN donde
    la hora no es válida; §4.1, §4.4, §4.8; CAN-8)."""
    if not isinstance(codigo, str) or not tipos.PATRON_CODIGO.fullmatch(codigo):
        raise ErrorCandidatos(f"código inválido: {codigo!r}")
    h = _horas(h)
    _crecientes(h, "residuos_estacion")
    if h.size and (h.min() < np.iinfo(np.int32).min or h.max() > np.iinfo(np.int32).max):
        raise ErrorCandidatos("residuos_estacion: horas fuera de int32")
    faltan = [v for v in VARIABLES if v not in r]
    if faltan:
        raise ErrorCandidatos(f"residuos_estacion: faltan {faltan}")
    r64 = {}
    for v in VARIABLES:
        x = np.asarray(r[v], dtype=np.float64)
        if x.shape != h.shape:
            raise ErrorCandidatos(f"residuos_estacion: r[{v!r}] y h deben tener el mismo largo")
        r64[v] = x.astype(np.float32).astype(np.float64)            # CAN-8: lo que se guarda
    meses = homogeneidad.mes2000(h) if h.size else np.empty(0, dtype=np.int64)
    fuentes, g, tramos_de, filas_tramos = dict(r64), {}, {}, []
    for v in SEGMENTADAS:
        tramos = homogeneidad.tramos_homogeneos(h, r64[v], v, umbrales) if h.size else []
        deltas = homogeneidad.desplazamientos(h, r64[v], tramos, umbrales) if tramos else {}
        gi = _tramo_de(meses, tramos)
        rt = np.full(h.shape, np.nan)
        en = gi >= 0
        if en.any():
            d = np.array([deltas[k] for k in range(len(tramos))], dtype=np.float64)
            rt[en] = r64[v][en] - d[gi[en]]
        fuentes[v] = rt.astype(np.float32).astype(np.float64)
        g[v], tramos_de[v] = gi, tramos
        filas_tramos += [{"codigo": codigo, "variable": v, "g": k, "desde_mes": int(a), "hasta_mes": int(b),
                          "delta": float(deltas[k])} for k, (a, b) in enumerate(tramos)]
    interp = {v: interpolar_no_observadas(h, fuentes[v], umbrales) for v in VARIABLES}
    h_nuevas = np.unique(np.concatenate([interp[v][0] for v in VARIABLES])) if h.size else np.empty(0, np.int64)
    meses_n = homogeneidad.mes2000(h_nuevas) if h_nuevas.size else np.empty(0, dtype=np.int64)
    columnas: dict[str, Any] = {"h": np.concatenate([h, h_nuevas])}
    for v in VARIABLES:
        columnas[COLUMNA_R[v]] = np.concatenate([r64[v], np.full(h_nuevas.shape, np.nan)])
    for v in SEGMENTADAS:
        nuevos = np.full(h_nuevas.shape, np.nan)
        hi, vi = interp[v]
        nuevos[np.searchsorted(h_nuevas, hi)] = vi
        columnas[COLUMNA_RT[v]] = np.concatenate([fuentes[v], nuevos])
    for v in SEGMENTADAS:
        columnas[COLUMNA_G[v]] = np.concatenate([g[v], _tramo_de(meses_n, tramos_de[v])])
    columnas["observada"] = np.concatenate([np.ones(h.shape, bool), np.zeros(h_nuevas.shape, bool)])
    columnas["interpolable"] = ~columnas["observada"]
    orden = np.argsort(columnas["h"], kind="stable")
    esquema = tipos.ESQUEMA_RESIDUOS
    df = pd.DataFrame({c: np.asarray(columnas[c])[orden] for c in esquema}).astype(dict(esquema))
    tipos.validar_esquema(df, esquema, nombre=f"residuos {codigo}")
    df.attrs["esquema"] = esquema.version
    et = tipos.ESQUEMA_TRAMOS_HOMOGENEOS
    tr = (pd.DataFrame(filas_tramos, columns=list(et)).astype(dict(et)) if filas_tramos else tipos.tabla_vacia(et))
    tipos.validar_esquema(tr, et, nombre=f"tramos {codigo}")
    tr.attrs["esquema"] = et.version
    return df, tr


# ---------------------------------------------------------------------------
# Candidato A (§4.3, CAN-4, CAN-5)
# ---------------------------------------------------------------------------
def _armonicos_a(umbrales) -> tuple[int, int]:
    """(k sin la condición de horas, k con ≥ A_HORAS_K3 horas): los períodos A_P*_H son 24/k (CAN-4)."""
    periodos = [umbrales.a(i) for i in ("A_P1_H", "A_P2_H", "A_P3_H")]
    ks = constantes.valor("A_ARMONICOS_K")
    if tuple(HORAS_DIA / p for p in periodos) != tuple(float(k) for k in ks):
        raise ErrorCandidatos(f"los períodos de A {periodos} no son 24/k con k = {ks} (§4.3)")
    return int(ks[-2]), int(ks[-1])


def climatologia_a(h, r, umbrales, *, codigo: str, variable: str) -> pd.DataFrame:
    """r̄_s(m, h) de una estación y variable (``ESQUEMA_CLIMA_A``, 12 × 24 filas en orden de mes y hora; §4.3,
    CAN-4, D19). ``h`` son las horas observadas y ``r`` el residuo (NaN donde no es válido)."""
    if not isinstance(codigo, str) or not tipos.PATRON_CODIGO.fullmatch(codigo):
        raise ErrorCandidatos(f"código inválido: {codigo!r}")
    variable = Variable(variable).value
    h = _horas(h)
    r = np.asarray(r, dtype=np.float64)
    if r.shape != h.shape:
        raise ErrorCandidatos("climatologia_a: r y h deben tener el mismo largo")
    ok = np.isfinite(r)
    hv, rv = h[ok], r[ok]
    _, mes, hora = _mes_y_hora(hv) if hv.size else (None, np.empty(0, np.int64), np.empty(0, np.int64))
    anio = _anio(hv) if hv.size else np.empty(0, np.int64)
    k_base, k_max = _armonicos_a(umbrales)
    ventana = _entero(umbrales, "A_VENTANA_MESES")
    recorte = umbrales.frac("A_RECORTE_PCT")
    horas_dia = np.arange(HORAS_DIA)
    rbar = np.full((MESES_ANIO, HORAS_DIA), np.nan)
    califica = np.zeros(MESES_ANIO, dtype=bool)
    for m in range(1, MESES_ANIO + 1):
        meses = {(m - 1 + d) % MESES_ANIO + 1 for d in range(-ventana, ventana + 1)}
        sel = np.isin(mes, list(meses))
        if sel.sum() < umbrales.a("A_MIN_N") or np.unique(anio[sel]).size < umbrales.a("A_MIN_ANIOS"):
            continue
        hs = hora[sel]
        if numerico.hueco_circular_max(hs, HORAS_DIA) > umbrales.a("A_HUECO_H"):
            continue
        k = k_max if np.unique(hs).size >= umbrales.a("A_HORAS_K3") else k_base
        try:
            coefs = numerico.armonico_recortado(hs, rv[sel], k, recorte)
        except numerico.DisenoDeficiente:                              # D19: no entra en A ese mes
            continue
        rbar[m - 1] = numerico.valor_armonico(coefs, horas_dia)
        califica[m - 1] = True
    esquema = tipos.ESQUEMA_CLIMA_A
    df = pd.DataFrame({"codigo": codigo, "variable": variable,
                       "mes": np.repeat(np.arange(1, MESES_ANIO + 1), HORAS_DIA),
                       "hora": np.tile(horas_dia, MESES_ANIO), "rbar": rbar.ravel(),
                       "califica": np.repeat(califica, HORAS_DIA)}).astype(dict(esquema))
    tipos.validar_esquema(df, esquema, nombre=f"clima_a {codigo} {variable}")
    df.attrs["esquema"] = esquema.version
    return df


def _observadas(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    mascara = df["observada"].to_numpy(dtype=bool)
    return df["h"].to_numpy()[mascara].astype(np.int64), mascara


def climatologias_a(residuos: Mapping[str, pd.DataFrame], umbrales) -> pd.DataFrame:
    """``ESQUEMA_CLIMA_A`` de todas las estaciones y variables (§4.3), en orden de código y variable. Se calcula
    una vez por estación (MC-45)."""
    partes = []
    for codigo in sorted(residuos):
        df = residuos[codigo]
        tipos.validar_esquema(df, tipos.ESQUEMA_RESIDUOS, nombre=f"residuos {codigo}")
        h, mascara = _observadas(df)
        for v in VARIABLES:
            r = df[COLUMNA_R[v]].to_numpy(dtype=np.float32)[mascara].astype(np.float64)
            partes.append(climatologia_a(h, r, umbrales, codigo=codigo, variable=v))
    if not partes:
        return tipos.tabla_vacia(tipos.ESQUEMA_CLIMA_A)
    salida = pd.concat(partes, ignore_index=True)
    salida.attrs["esquema"] = tipos.ESQUEMA_CLIMA_A.version
    return salida


def _rbar_matrices(clima: pd.DataFrame, codigos, variable: str) -> np.ndarray:
    """r̄ mes × hora × estación (NaN donde no califica o falta la estación)."""
    tipos.validar_esquema(clima, tipos.ESQUEMA_CLIMA_A, nombre="clima_a")
    sub = clima[clima["variable"] == variable]
    salida = np.full((MESES_ANIO, HORAS_DIA, len(codigos)), np.nan)
    if not len(sub) or not len(codigos):
        return salida
    j = pd.Index(list(codigos)).get_indexer(sub["codigo"].astype(object))
    en = j >= 0
    mes = sub["mes"].to_numpy(np.int64)[en] - 1
    hora = sub["hora"].to_numpy(np.int64)[en]
    if ((mes < 0) | (mes >= MESES_ANIO) | (hora < 0) | (hora >= HORAS_DIA)).any():
        raise ErrorCandidatos("clima_a: mes 1-12 y hora 0-23")
    valor = np.where(sub["califica"].to_numpy(bool)[en], sub["rbar"].to_numpy(np.float64)[en], np.nan)
    salida[mes, hora, j[en]] = valor
    return salida


def _variable_de_clima(clima: pd.DataFrame, codigos) -> str:
    sub = clima[clima["codigo"].isin(list(codigos))] if len(codigos) else clima
    variables = sorted(set(sub["variable"].astype(object)))
    if len(variables) != 1:
        raise ErrorCandidatos(f"la climatología debe ser de una sola variable, no {variables}")
    return Variable(variables[0]).value


def _sumas_a(vec, rbar12: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Σ k·w·r̄ y Σ k·w por mes y hora (12 × 24 × punto), con las estaciones calificadas (CAN-5)."""
    n_t = len(vec.codigos)
    q = rbar12.reshape(MESES_ANIO * HORAS_DIA, n_t)
    num, den = sumas_nucleo(vec, q, np.isfinite(q))
    forma = (MESES_ANIO, HORAS_DIA, num.shape[1])
    return num.reshape(forma), den.reshape(forma)


def _a_en_horas(num12, den12, kappa: float, h: np.ndarray, columna=None) -> tuple[np.ndarray, np.ndarray]:
    """A y su Σk interpolados entre los centros de mes (CAN-5): hora × punto, o un valor por hora con ``columna``."""
    i_a, i_b, t = _interpolacion_mensual(h)
    hora = np.mod(h, HORAS_DIA)
    phi12 = num12 / (kappa + den12)
    if columna is None:
        t2 = t[:, None]
        return ((1.0 - t2) * phi12[i_a, hora] + t2 * phi12[i_b, hora],
                (1.0 - t2) * den12[i_a, hora] + t2 * den12[i_b, hora])
    return ((1.0 - t) * phi12[i_a, hora, columna] + t * phi12[i_b, hora, columna],
            (1.0 - t) * den12[i_a, hora, columna] + t * den12[i_b, hora, columna])


def correccion_a(vec, clima, h) -> np.ndarray:
    """A(x, u) en las horas ``h`` (hora × punto): Φ con q = r̄_s(m, h) de las calificadas en m, interpolado entre los
    centros de mes (§4.3, MC-41, CAN-5). ``clima`` es ``ESQUEMA_CLIMA_A`` de una variable."""
    _comprobar_vecinos(vec)
    h = _horas(h)
    variable = _variable_de_clima(clima, vec.codigos)
    num12, den12 = _sumas_a(vec, _rbar_matrices(clima, vec.codigos, variable))
    _, _, kappa = _hiper(vec.hiper)
    return _a_en_horas(num12, den12, kappa, h)[0]


def correccion_b(vec, rt, disponible) -> np.ndarray:
    """R_B (hora × punto): Φ con q = r̃ (§4.4). ``rt`` y ``disponible`` son hora × estación de entrenamiento."""
    return campo(vec, rt, disponible)[0]


def correccion_ab(vec_a, vec_ab, clima, anomalias, disponible, h) -> np.ndarray:
    """R_AB = A (``vec_a``) + Φ′ (``vec_ab``) con q = a (§4.5, CAN-7); las dos listas son del mismo entrenamiento."""
    _comprobar_vecinos(vec_a)
    _comprobar_vecinos(vec_ab)
    if vec_a.codigos != vec_ab.codigos or vec_a.est.shape[0] != vec_ab.est.shape[0]:
        raise ErrorCandidatos("A y Φ′ de AB deben tener los mismos puntos y estaciones de entrenamiento")
    return correccion_a(vec_a, clima, h) + campo(vec_ab, anomalias, disponible)[0]


# ---------------------------------------------------------------------------
# Candidatos C y C_est (§4.6, §4.7; CAN-9 a CAN-13)
# ---------------------------------------------------------------------------
def _armonicos_c() -> tuple[tuple, tuple, tuple]:
    """(horarios, anuales, anuales de primer orden): (nombre, función, orden, período) de ``C_PERIODOS``."""
    horarios, anuales = [], []
    for orden, periodo in constantes.valor("C_PERIODOS"):
        es_horario = periodo == HORAS_DIA
        for funcion in ("sen", "cos"):
            (horarios if es_horario else anuales).append(
                (f"{funcion}_{'h' if es_horario else 'a'}{orden}", funcion, int(orden), float(periodo)))
    primer_orden = tuple(a for a in anuales if a[2] == 1)
    n_h, n_a = constantes.valor("C_INTERACCIONES")
    if len(horarios) != n_h or len(primer_orden) != n_a:
        raise ErrorCandidatos("C_PERIODOS no da los 4 armónicos horarios y los 2 anuales de primer orden de §4.6")
    return tuple(horarios), tuple(anuales), primer_orden


_HORARIOS, _ANUALES, _ANUALES_1 = _armonicos_c()
HORARIOS_C = tuple(a[0] for a in _HORARIOS)
ANUALES_C = tuple(a[0] for a in _ANUALES)
TPI_C = ("tpi1", "tpi5")
TRUNCADO_C = {"tpi1": "tpi1_truncado", "tpi5": "tpi5_truncado"}
ESTATICOS_C = ("z_km", "dz_km", "log_dist_costa", *TPI_C, "pendiente_deg", *tipos.LULC, "lat")
MACRO_C = tuple(f"mz_{m}" for m in tipos.MACROZONAS)
ESTADO_C = tipos.VARIABLES_CLIMA_ESTADO          # T, T_menos_Td, rapidez, amp (TIP-17)
BASES_C = ESTATICOS_C + MACRO_C + HORARIOS_C + ANUALES_C + ESTADO_C


def _columnas_c() -> tuple[tuple[str, ...], ...]:
    """Columnas del diseño estandarizado (CAN-9): cada una es el producto de sus predictores base."""
    anual_1 = tuple(a[0] for a in _ANUALES_1)
    rapidez, t_menos_td = ESTADO_C[2], ESTADO_C[1]
    columnas = [()] + [(b,) for b in BASES_C]
    columnas += [(s, t) for s in ESTATICOS_C for t in HORARIOS_C + anual_1]
    columnas += [(m, t) for m in MACRO_C for t in HORARIOS_C]
    columnas += [("dz_km", rapidez), ("dz_km", t_menos_td)]
    columnas += [(k, rapidez) for k in TPI_C]
    columnas += [(k, t, a) for k in TPI_C for t in HORARIOS_C for a in anual_1]
    return tuple(columnas)


COLUMNAS_C = _columnas_c()


def _atomos(base: str) -> tuple[str, str]:
    """(átomo de la escala, átomo del desplazamiento) de un predictor base: f = escala·[b] + desplazamiento·[1], o
    con el TPI f = escala·[(1 − t)·TPI] + desplazamiento·[1 − t] (CAN-11)."""
    return (f"u1:{base}", f"u0:{base}") if base in TPI_C else (base, "1")


def _monomios() -> tuple[tuple[tuple[str, ...], ...], tuple]:
    """Monomios del diseño en bruto (la constante primero) y la expansión de cada columna estandarizada."""
    indice: dict[tuple[str, ...], int] = {(): 0}
    expansion = []
    for j, factores in enumerate(COLUMNAS_C):
        for eleccion in product((0, 1), repeat=len(factores)):
            atomos = [_atomos(b)[e] for b, e in zip(factores, eleccion)]
            mono = tuple(sorted(a for a in atomos if a != "1"))
            if mono not in indice:
                indice[mono] = len(indice)
            expansion.append((j, indice[mono], tuple((BASES_C.index(b), e) for b, e in zip(factores, eleccion))))
    return tuple(indice), tuple(expansion)


MONOMIOS_C, _EXPANSION = _monomios()
_INDICE_MONOMIO = {m: i for i, m in enumerate(MONOMIOS_C)}
_BLOQUE_FILAS = 8192                             # filas por bloque del diseño en bruto (sólo memoria y caché; CAN-18)


def _plan_monomios() -> tuple[int, tuple[tuple[int, int, str], ...]]:
    """CAN-18: (prefijos que no son monomios, pasos). Cada paso (destino, prefijo, átomo) hace destino = prefijo ·
    átomo, con las ranuras 0…187 los ``MONOMIOS_C`` y las siguientes los prefijos que faltan; los pasos van por grado,
    así que cada monomio sale con las mismas multiplicaciones y en el mismo orden que ((1·a₁)·a₂)·a₃ de sus átomos en
    orden."""
    ranuras = dict(_INDICE_MONOMIO)
    for mono in MONOMIOS_C:
        for k in range(1, len(mono)):
            ranuras.setdefault(mono[:k], len(ranuras))
    pasos = tuple((ranuras[m], ranuras[m[:-1]], m[-1]) for m in sorted(ranuras, key=len) if m)
    return len(ranuras) - len(MONOMIOS_C), pasos


_N_PREFIJOS, _PASOS_MONOMIOS = _plan_monomios()


@dataclass(frozen=True, eq=False)
class SumasC:
    """Muestra fija de una estación y sus sumas ponderadas sobre el diseño en bruto (§4.6, MC-05, MC-45)."""
    codigo: str
    variable: str
    diseno: DisenoC
    xtx: np.ndarray                 # monomio × monomio, Σ w x xᵀ
    xty: np.ndarray                 # Σ w x y
    yty: float                      # Σ w y²
    n_filas: int                    # n_s (MC-05)
    peso: float                     # mín(C_FILAS/n_s; C_PESO_MAX)
    horas: np.ndarray               # horas de la muestra (int64, crecientes)


def _insumos_c(codigo: str, info, estaticos: pd.DataFrame, estados: Mapping, climatologico: bool):
    """(fila de estáticos, estado) de una estación para C o C_est (CAN-13). None sólo si está excluida (PAR-1) o fuera
    de la grilla (D34); una estación que entra con celda y sin su fila de estáticos, o sin su fondo (C) o su clima del
    estado (C_est), es un insumo incompleto: ``ErrorCandidatos``."""
    if info.excluida or _fuera_de_la_grilla(info):
        return None
    fila = estaticos[estaticos["celda"] == int(info.celda)]
    if len(fila) > 1:
        raise ErrorCandidatos(f"celda {info.celda} repetida en los estáticos")
    if not len(fila):
        raise ErrorCandidatos(f"{codigo}: su celda {info.celda} no está en los estáticos de C (D34 es sólo la estación "
                              "sin celda; CAN-13)")
    if codigo not in estados:
        fuente = "clima_estado (C_est)" if climatologico else "puntos_e5l (C)"
        raise ErrorCandidatos(f"{codigo}: falta su estado en {fuente} (A14; D34 es sólo la estación sin celda; CAN-13)")
    return fila, estados[codigo]


def _estaticos_validos(estaticos) -> pd.DataFrame:
    if isinstance(estaticos, pd.Series):
        estaticos = estaticos.to_frame().T
    if not isinstance(estaticos, pd.DataFrame):
        raise ErrorCandidatos("los estáticos de C son un DataFrame con las columnas de ESQUEMA_ESTATICAS_CELDA")
    faltan = [c for c in (*tipos.ESQUEMA_ESTATICAS_CELDA, COLUMNA_Z_E5L) if c not in estaticos.columns]
    if faltan:
        raise ErrorCandidatos(f"a los estáticos de C les faltan {faltan} (CAN-9; «{COLUMNA_Z_E5L}» es PED-2)")
    return estaticos


def estado_c(F_estacion: pd.DataFrame, h) -> dict[str, np.ndarray]:
    """El estado del fondo de C en las horas ``h`` (CAN-10): {T, T_menos_Td, rapidez, amp} desde
    ``ESQUEMA_PUNTOS_E5L``, en float64 (los float32 guardados, A1); NaN donde la tabla no tiene la hora."""
    tipos.validar_esquema(F_estacion, tipos.ESQUEMA_PUNTOS_E5L, nombre="fondo en la estación")
    h = _horas(h)
    ht = F_estacion["h"].to_numpy().astype(np.int64)
    _crecientes(ht, "fondo en la estación")
    pos = np.searchsorted(ht, h)
    pos_c = np.clip(pos, 0, max(ht.size - 1, 0))
    ok = (pos < ht.size) & (ht[pos_c] == h) if ht.size else np.zeros(h.shape, bool)

    def col(c):
        x = np.full(h.shape, np.nan)
        x[ok] = F_estacion[c].to_numpy(np.float32)[pos_c[ok]].astype(np.float64)
        return x
    T, Td, u, v, amp = (col(c) for c in ("T_F", "Td_F", "u_F", "v_F", "amp_TF"))
    return dict(zip(ESTADO_C, (T, T - Td, np.hypot(u, v), amp)))


def estado_c_est(clima_estacion: Mapping[str, np.ndarray], h) -> dict[str, np.ndarray]:
    """El estado climatológico de C_est en las horas ``h`` (CAN-10; A14, TIP-17): cada variable de
    ``VARIABLES_CLIMA_ESTADO`` (12 × 24, mes 0 = enero, columna = hora UTC) en el mes y la hora UTC de cada h."""
    h = _horas(h)
    _, mes, hora = _mes_y_hora(h) if h.size else (None, np.empty(0, np.int64), np.empty(0, np.int64))
    salida = {}
    for v in ESTADO_C:
        if v not in clima_estacion:
            raise ErrorCandidatos(f"clima_estado: falta {v}")
        x = np.asarray(clima_estacion[v], dtype=np.float64)
        if x.shape != (MESES_ANIO, HORAS_DIA):
            raise ErrorCandidatos(f"clima_estado: {v} es {MESES_ANIO} × {HORAS_DIA}")
        salida[v] = x[mes - 1, hora]
    return salida


def _indicadoras_macrozona(cod: np.ndarray) -> np.ndarray:
    """Las 5 indicadoras de cada fila (fila × 5, float64; D22 (a), CAN-18). Con códigos enteros de numpy,
    ``tipos.indicadoras_macrozona`` una vez por código distinto, en el orden en que aparecen (así el primer código
    desconocido da el mismo error que fila a fila), repartidas con el índice inverso; con otro tipo o sin filas, fila a
    fila como siempre."""
    if cod.size and cod.dtype.kind in "iu":
        distintos, primera, inverso = np.unique(cod, return_index=True, return_inverse=True)
        tabla = np.empty((distintos.size, len(MACRO_C)), dtype=np.float64)
        for k in np.argsort(primera, kind="stable"):
            tabla[k] = tipos.indicadoras_macrozona(int(distintos[k]))
        return tabla[inverso.reshape(-1)]
    return np.array([tipos.indicadoras_macrozona(int(c)) for c in cod], dtype=np.float64)


def _bases(estaticos: pd.DataFrame, h: np.ndarray, estado: Mapping[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """Predictores base en bruto (fila × 31) y truncado del TPI (fila × 2) (CAN-9)."""
    n = h.size
    if len(estaticos) not in (1, n):
        raise ErrorCandidatos("los estáticos de C son una fila (se repite) o una por hora")

    def est(c, dtype=np.float64):
        x = estaticos[c].to_numpy(dtype=dtype)
        return np.repeat(x, n) if x.size == 1 else x
    z = est(COLUMNA_Z_C)
    columnas = {"z_km": z / M_POR_KM, "dz_km": (z - est(COLUMNA_Z_E5L)) / M_POR_KM,
                "log_dist_costa": est("log_dist_costa"), "tpi1": est("tpi1"), "tpi5": est("tpi5"),
                "pendiente_deg": est("pendiente_deg"), **{c: est(c) for c in tipos.LULC}, "lat": est("lat")}
    cod = estaticos["macrozona_cod"].to_numpy()
    ind = _indicadoras_macrozona(cod)                                                        # D22 (a)
    ind = np.repeat(ind, n, axis=0) if len(cod) == 1 else ind
    columnas.update({m: ind[:, i] for i, m in enumerate(MACRO_C)})
    hora = np.mod(h, HORAS_DIA).astype(np.float64)
    doy = _dia_del_anio(h).astype(np.float64) if n else np.empty(0)
    for nombre, funcion, orden, periodo in _HORARIOS + _ANUALES:
        x = hora if periodo == HORAS_DIA else doy
        angulo = 2 * np.pi * orden * x / periodo
        columnas[nombre] = np.sin(angulo) if funcion == "sen" else np.cos(angulo)
    for v in ESTADO_C:
        x = np.asarray(estado[v], dtype=np.float64)
        if x.shape != h.shape:
            raise ErrorCandidatos(f"estado de C: {v} debe tener una fila por hora")
        columnas[v] = x
    # Las mismas columnas que con column_stack (fila × 31, C-contigua); apiladas por filas y traspuestas, más barato.
    B = np.ascontiguousarray(np.stack([columnas[b] for b in BASES_C]).T) if n else np.empty((0, len(BASES_C)))
    trunc = np.column_stack([est(TRUNCADO_C[k], dtype=bool) for k in TPI_C]) if n else np.empty((0, len(TPI_C)), bool)
    return B, trunc


def _diseno_bruto(B: np.ndarray, trunc: np.ndarray) -> np.ndarray:
    """Valores de los monomios (fila × monomio) desde los predictores base (CAN-11). Por bloques de filas y con cada
    prefijo calculado una vez (``_PASOS_MONOMIOS``): las mismas multiplicaciones, en el mismo orden (CAN-18)."""
    atomos = {"1": np.ones(B.shape[0])}
    for i, b in enumerate(BASES_C):
        if b in TPI_C:
            t = trunc[:, TPI_C.index(b)]
            atomos[f"u1:{b}"] = np.where(t, 0.0, B[:, i])
            atomos[f"u0:{b}"] = np.where(t, 0.0, 1.0)
        else:
            atomos[b] = B[:, i]
    n, n_mono = B.shape[0], len(MONOMIOS_C)
    X = np.empty((n, n_mono))
    prefijos = np.empty((_N_PREFIJOS, min(n, _BLOQUE_FILAS)))
    for r0 in range(0, n, _BLOQUE_FILAS):
        r1 = min(r0 + _BLOQUE_FILAS, n)
        Xb = X[r0:r1]
        ranuras = [Xb[:, j] for j in range(n_mono)] + list(prefijos[:, :r1 - r0])
        ranuras[0][...] = atomos["1"][r0:r1]
        for destino, prefijo, atomo in _PASOS_MONOMIOS:
            np.multiply(ranuras[prefijo], atomos[atomo][r0:r1], out=ranuras[destino])
    return X


def _estado_de(estado, h: np.ndarray, climatologico: bool) -> Mapping[str, np.ndarray]:
    if climatologico:
        return estado_c_est(estado, h)
    if isinstance(estado, pd.DataFrame):
        return estado_c(estado, h)
    if isinstance(estado, Mapping) and all(v in estado for v in ESTADO_C):
        return {v: np.asarray(estado[v], dtype=np.float64) for v in ESTADO_C}
    raise ErrorCandidatos("el estado de C es ESQUEMA_PUNTOS_E5L o {T, T_menos_Td, rapidez, amp} por hora")


def diseno_c(estaticos, h, estado, umbrales=None, *, climatologico: bool = False) -> np.ndarray:
    """Diseño en bruto de C (fila × monomio, ``MONOMIOS_C``; CAN-9, CAN-11): ``estaticos`` es la fila de la celda
    (``ESQUEMA_ESTATICAS_CELDA`` más ``z_e5l``) o una por hora; ``estado`` es ``ESQUEMA_PUNTOS_E5L`` (C) o el clima de
    la estación (C_est, ``climatologico``). ``umbrales`` no se usa: el diseño es fijo (§4.6)."""
    h = _horas(h)
    B, trunc = _bases(_estaticos_validos(estaticos), h, _estado_de(estado, h, climatologico))
    return _diseno_bruto(B, trunc)


def _momentos(xtx: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Media y desvío ponderados de cada predictor base desde X'WX en bruto (CAN-11, D33)."""
    sw = xtx[0, 0]
    if not sw > 0:
        raise ErrorCandidatos("C sin filas de entrenamiento")
    media, desvio = np.zeros(len(BASES_C)), np.zeros(len(BASES_C))
    for i, b in enumerate(BASES_C):
        if b in TPI_C:
            i0, i1 = _INDICE_MONOMIO[(f"u0:{b}",)], _INDICE_MONOMIO[(f"u1:{b}",)]
            peso = xtx[0, i0]
        else:
            i0, i1 = 0, _INDICE_MONOMIO[(b,)]
            peso = sw
        if not peso > 0:                     # todo truncado: el TPI vale 0 (D33)
            continue
        mu = xtx[0, i1] / peso
        segundo = xtx[i1, i1] / peso
        var = segundo - mu * mu
        media[i] = mu
        desvio[i] = math.sqrt(var) if var > _TOL_VARIANZA * max(segundo, np.finfo(np.float64).tiny) else 0.0
    return media, desvio


def _transformacion(media: np.ndarray, desvio: np.ndarray) -> np.ndarray:
    """T (monomio × columna): diseño estandarizado = diseño en bruto · T (CAN-11)."""
    media = np.asarray(media, dtype=np.float64)
    desvio = np.asarray(desvio, dtype=np.float64)
    if media.shape != (len(BASES_C),) or desvio.shape != (len(BASES_C),):
        raise ErrorCandidatos(f"media y desvío de C son {len(BASES_C)} valores")
    con = desvio > 0
    escala = np.where(con, 1.0 / np.where(con, desvio, 1.0), 0.0)
    desplazamiento = np.where(con, -media * escala, 0.0)
    partes = (escala, desplazamiento)
    T = np.zeros((len(MONOMIOS_C), len(COLUMNAS_C)))
    for j, i_mono, factores in _EXPANSION:
        coef = 1.0
        for i_base, e in factores:
            coef *= partes[e][i_base]
        T[i_mono, j] += coef
    return T


def diseno_estandarizado(X_bruto, modelo: ModeloC) -> np.ndarray:
    """El diseño estandarizado (fila × ``COLUMNAS_C``) con la media y el desvío de ``modelo`` (CAN-11)."""
    X = np.asarray(X_bruto, dtype=np.float64)
    if X.ndim != 2 or X.shape[1] != len(MONOMIOS_C):
        raise ErrorCandidatos(f"el diseño en bruto de C tiene {len(MONOMIOS_C)} columnas")
    return np.matmul(X, _transformacion(modelo.media, modelo.desvio))


def filas_c(residuos, estaticos, estados, umbrales, *, infos, climatologico: bool = False) -> dict:
    """Muestra fija y sumas por estación (MC-45, CAN-13): {variable: {código: SumasC}}. ``estados``: código →
    ``ESQUEMA_PUNTOS_E5L`` (C) o código → clima de la estación (C_est, ``climatologico``)."""
    estaticos = _estaticos_validos(estaticos)
    diseno = DisenoC.CLIMATOLOGICO if climatologico else DisenoC.ESTADO
    semilla = _entero(umbrales, "SEMILLA")
    n_max = _entero(umbrales, "C_FILAS")
    peso_max = float(umbrales.a("C_PESO_MAX"))
    salida: dict[str, dict[str, SumasC]] = {v: {} for v in VARIABLES}
    for codigo in sorted(residuos):
        if codigo not in infos:
            raise ErrorCandidatos(f"{codigo}: sin InfoEstacion en infos")
        insumos = _insumos_c(codigo, infos[codigo], estaticos, estados, climatologico)
        if insumos is None:                                     # D34: sin celda no hay estáticos ni filas
            continue
        fila, estado = insumos
        df = residuos[codigo]
        tipos.validar_esquema(df, tipos.ESQUEMA_RESIDUOS, nombre=f"residuos {codigo}")
        h, mascara = _observadas(df)
        B, trunc = _bases(fila, h, _estado_de(estado, h, climatologico))
        valida = _filas_finitas(B, trunc)
        for v in VARIABLES:
            y = df[COLUMNA_R[v]].to_numpy(dtype=np.float32)[mascara].astype(np.float64)
            pool = np.flatnonzero(np.isfinite(y) & valida)
            if pool.size == 0:
                continue
            if pool.size > n_max:
                rng = numerico.generador(semilla, Candidato.C.value, codigo, v)
                pool = np.sort(rng.choice(pool, size=n_max, replace=False))
            X = _diseno_bruto(B[pool], trunc[pool])
            w = min(n_max / pool.size, peso_max)
            yv = y[pool]
            salida[v][codigo] = SumasC(codigo=codigo, variable=v, diseno=diseno, xtx=w * np.matmul(X.T, X),
                                       xty=w * np.matmul(X.T, yv), yty=float(w * np.dot(yv, yv)),
                                       n_filas=int(pool.size), peso=float(w), horas=h[pool])
    return salida


def _filas_finitas(B: np.ndarray, trunc: np.ndarray) -> np.ndarray:
    """Filas con todos los predictores base finitos; el TPI truncado cuenta como finito (vale 0, CAN-11)."""
    ok = np.isfinite(B)
    for k, b in enumerate(TPI_C):
        ok[:, BASES_C.index(b)] |= trunc[:, k]
    return ok.all(axis=1)


@dataclass(frozen=True, eq=False)
class _AjusteC:
    """Lo que no depende de α en un ajuste de C: diseño, media, desvío, T, T'X'WXT y T'X'Wy (CAN-11)."""
    diseno: DisenoC
    media: np.ndarray
    desvio: np.ndarray
    T: np.ndarray
    A: np.ndarray
    b: np.ndarray


def _ajuste_c(sumas_por_estacion: Mapping[str, SumasC], entrenamiento) -> _AjusteC:
    """Suma las de las estaciones de entrenamiento en orden de código y deriva la estandarización (CAN-11)."""
    codigos = [c for c in sorted(set(entrenamiento)) if c in sumas_por_estacion]
    if not codigos:
        raise ErrorCandidatos("C sin estaciones de entrenamiento con filas")
    disenos = {sumas_por_estacion[c].diseno for c in codigos}
    variables = {sumas_por_estacion[c].variable for c in codigos}
    if len(disenos) != 1 or len(variables) != 1:
        raise ErrorCandidatos("las sumas de C deben ser de un solo diseño y una sola variable")
    xtx = np.zeros((len(MONOMIOS_C), len(MONOMIOS_C)))
    xty = np.zeros(len(MONOMIOS_C))
    for c in codigos:
        xtx = xtx + sumas_por_estacion[c].xtx
        xty = xty + sumas_por_estacion[c].xty
    media, desvio = _momentos(xtx)
    T = _transformacion(media, desvio)
    return _AjusteC(diseno=disenos.pop(), media=media, desvio=desvio, T=T,
                    A=np.matmul(np.matmul(T.T, xtx), T), b=np.matmul(T.T, xty))


def _resolver_c(ajuste: _AjusteC, alfa: float) -> ModeloC:
    alfa = float(alfa)
    if not (math.isfinite(alfa) and alfa > 0):
        raise ErrorCandidatos(f"α debe ser finito y > 0: {alfa!r}")
    coef = numerico.ridge_ponderado(ajuste.A, ajuste.b, alfa, sin_penalizar=1)          # CAN-12
    return ModeloC(coef=coef, media=ajuste.media, desvio=ajuste.desvio, alfa=alfa, diseno=ajuste.diseno)


def ajustar_c(sumas_por_estacion, entrenamiento, alfa: float) -> ModeloC:
    """C o C_est (``tipos.ModeloC``): ridge con la constante sin penalizar sobre el diseño estandarizado con las
    estaciones de ``entrenamiento`` (§4.6, MC-45; CAN-11, CAN-12)."""
    return _resolver_c(_ajuste_c(sumas_por_estacion, entrenamiento), alfa)


def predecir_c(modelo, estaticos, h, estado) -> np.ndarray:
    """R_C (o R_C_est) en las horas ``h`` de un punto (§4.6, §4.7); NaN donde el diseño no es finito."""
    if not isinstance(modelo, ModeloC):
        raise ErrorCandidatos("modelo debe ser tipos.ModeloC")
    X = diseno_c(estaticos, h, estado, climatologico=modelo.diseno is DisenoC.CLIMATOLOGICO)
    return np.matmul(diseno_estandarizado(X, modelo), modelo.coef)


# ---------------------------------------------------------------------------
# Series por estación (en memoria; caché por DatosCompetencia que no crece con las horas, CAN-19)
# ---------------------------------------------------------------------------
_CACHE: "weakref.WeakKeyDictionary[Any, dict]" = weakref.WeakKeyDictionary()
_CLASES = ("r", "rt", "b", "a")
_INTERPOLADAS = ("b", "a")


def _cache(datos) -> dict:
    try:
        return _CACHE.setdefault(datos, {})
    except TypeError:
        return {}


def _tabla(datos, codigo: str) -> pd.DataFrame | None:
    df = datos.residuos.get(codigo)
    if df is not None:
        tipos.validar_esquema(df, tipos.ESQUEMA_RESIDUOS, nombre=f"residuos {codigo}")
    return df


_VACIA = (np.empty(0, dtype=np.int64), np.empty(0))
_INT32 = np.iinfo(np.int32)


class _Tabla:
    """CAN-19: la tabla de residuos de una estación, validada una vez por DatosCompetencia: la referencia a la tabla
    (no una copia; ``costo._bytes_cache`` no la cuenta, ya la cuenta en los residuos), si las horas de todas sus filas
    van crecientes y sin repetir (las de ``residuos_estacion``) y cuántas filas observadas tiene. Las columnas se toman
    en cada uso como vistas, sin copiar: la caché no retiene ningún arreglo de la tabla."""
    __slots__ = ("df", "creciente", "n_observadas")

    def __init__(self, df: pd.DataFrame):
        h = df["h"].to_numpy()
        self.df = df
        self.creciente = bool(np.all(h[1:] > h[:-1]))
        self.n_observadas = int(np.count_nonzero(df["observada"].to_numpy(dtype=bool)))

    def h(self) -> np.ndarray:
        return self.df["h"].to_numpy()

    def observada(self) -> np.ndarray:
        return self.df["observada"].to_numpy(dtype=bool)

    def columna(self, nombre: str) -> np.ndarray:
        return self.df[nombre].to_numpy(np.float32)

    def horas_observadas(self) -> np.ndarray:
        return self.h()[self.observada()].astype(np.int64)


def _tabla_estacion(datos, codigo: str) -> _Tabla | None:
    """La tabla de una estación (None si no tiene), validada una vez por DatosCompetencia (CAN-19)."""
    clave = ("tabla", codigo)
    cache = _cache(datos)
    if clave in cache:
        return cache[clave]
    df = _tabla(datos, codigo)
    salida = None if df is None else _Tabla(df)
    cache[clave] = salida
    return salida


def _columna_de(clase: str, variable: str) -> str:
    """La columna de la tabla de cada clase: r en «r»; r̃ (``rt_*``, o r en u, v y p) en «rt», «b» y «a»."""
    if clase not in _CLASES:
        raise ErrorCandidatos(f"clase de serie desconocida: {clase!r}")
    if clase == "r":
        return COLUMNA_R[variable]
    return COLUMNA_RT.get(variable, COLUMNA_R[variable])


def _rbar_estacion(datos, codigo: str, variable: str) -> np.ndarray:
    clave = ("rbar", codigo, variable)
    cache = _cache(datos)
    if clave not in cache:
        cache[clave] = _rbar_matrices(datos.climatologias, (codigo,), variable)[:, :, 0]
    return cache[clave]


def _menos_rbar(datos, codigo: str, variable: str, h: np.ndarray, v: np.ndarray) -> np.ndarray:
    """a = r̃ − r̄(m, h) en las horas ``h`` (int64; CAN-7): la misma resta, valor a valor, en todas las horas
    observadas o en algunas."""
    rbar = _rbar_estacion(datos, codigo, variable)
    if not h.size:
        return v
    _, mes, hora = _mes_y_hora(h)
    return v - rbar[mes - 1, hora]


def _serie(datos, codigo: str, clase: str, variable: str, umbrales) -> tuple[np.ndarray, np.ndarray]:
    """(horas, valores) de una estación: «r» y «rt» en las horas observadas; «b» (r̃) y «a» (anomalía de AB) con
    las horas no observadas interpoladas (CAN-6, CAN-7). Se arma en cada llamada desde la tabla, en float64 desde los
    float32 guardados, y no queda en la caché (CAN-19)."""
    t = _tabla_estacion(datos, codigo)
    if t is None:
        return _VACIA
    columna = _columna_de(clase, variable)
    h = t.horas_observadas()
    v = t.columna(columna)[t.observada()].astype(np.float64)
    if clase not in _INTERPOLADAS:
        return h, v
    if clase == "a":
        v = _menos_rbar(datos, codigo, variable, h, v)
    hi, vi = interpolar_no_observadas(h, v, umbrales)
    hh = np.concatenate([h, hi])
    vv = np.concatenate([v, vi])
    orden = np.argsort(hh, kind="stable")
    return hh[orden], vv[orden]


def _horas_de_estacion(datos, codigo: str) -> np.ndarray:
    """Las horas observadas de una estación (las de ``_serie(…, «r», …)``), sin armar sus valores."""
    t = _tabla_estacion(datos, codigo)
    return _VACIA[0] if t is None else t.horas_observadas()


def _llenar_desde_serie(M: np.ndarray, j: int, hs: np.ndarray, vs: np.ndarray, horas: np.ndarray) -> None:
    """La búsqueda de siempre en una serie armada: la de una tabla cuyas horas no van crecientes (CAN-19)."""
    if hs.size == 0 or horas.size == 0:
        return
    pos = np.searchsorted(hs, horas)
    pos_c = np.clip(pos, 0, hs.size - 1)
    ok = (pos < hs.size) & (hs[pos_c] == horas)
    M[ok, j] = vs[pos_c[ok]]


def _observada_vecina(observada: np.ndarray, inicio: np.ndarray, sentido: int, tope: int) -> np.ndarray:
    """CAN-19: la fila observada más cercana desde ``inicio`` (incluida) en el ``sentido`` (−1 o +1), o −1 si no la
    hay a ≤ tope − 2 filas: entre una hora y la observada vecina de un par a ≤ ``tope`` h caben a lo sumo tope − 2
    filas (horas distintas), así que más lejos el par no se interpola."""
    salida = np.full(inicio.size, -1, dtype=np.intp)
    for k in range(tope - 1):
        i = inicio + sentido * k
        libre = (salida < 0) & (i >= 0) & (i < observada.size)
        libre[libre] = observada[i[libre]]
        salida[libre] = i[libre]
    return salida


def _matriz_en_horas(datos, codigos, clase: str, variable: str, horas: np.ndarray, umbrales) -> np.ndarray:
    """Valores de la serie de cada estación en ``horas`` (hora × estación), NaN donde no tiene. CAN-19: sin armar la
    serie. Cada hora pedida se busca entre las filas de la tabla: si es observada, su r o r̃ (float32, que pasa exacto a
    float64; en «a», menos r̄ con la misma resta); en «b» y «a», si no lo es, se interpola en ese momento entre las dos
    filas observadas que la rodean, con las mismas condiciones y la misma cuenta que ``interpolar_no_observadas``
    (CAN-6: cada hora es su propia cuenta). Una tabla cuyas horas no van crecientes se busca como antes, en la serie
    armada."""
    M = np.full((horas.size, len(codigos)), np.nan)
    tope = None                    # B_INTERP_H: se lee en la primera estación que lo usa, donde lo leía la serie
    mes_hora = None                # (mes − 1, hora UTC) de las horas pedidas, para «a»: una vez por llamada
    x = valida = None              # las horas pedidas en int32 (el tipo de «h» en ESQUEMA_RESIDUOS), una vez
    for j, c in enumerate(codigos):
        t = _tabla_estacion(datos, c)
        if t is None:
            continue
        columna = _columna_de(clase, variable)
        if not t.creciente:
            _llenar_desde_serie(M, j, *_serie(datos, c, clase, variable, umbrales), horas)
            continue
        rbar = _rbar_estacion(datos, c, variable) if clase == "a" else None     # sus errores, como la serie
        interpola = clase in _INTERPOLADAS and t.n_observadas >= 2
        if interpola and tope is None:
            tope = _entero(umbrales, "B_INTERP_H")
        h = t.h()
        if horas.size == 0 or h.size == 0:
            continue
        if x is None:
            valida = (horas >= _INT32.min) & (horas <= _INT32.max)
            x = np.where(valida, horas, 0).astype(np.int32)                    # exacto donde es válida
            valida = None if valida.all() else valida
        pos = np.searchsorted(h, x)
        pos_c = np.minimum(pos, h.size - 1)                                    # pos = n: h[n − 1] < x, no está
        en_tabla = h[pos_c] == x
        if valida is not None:
            en_tabla &= valida
        observada = t.observada()
        fila = en_tabla & observada[pos_c]
        col = t.columna(columna)
        if fila.any():
            v = col[pos_c[fila]]
            if rbar is not None:
                if mes_hora is None:
                    _, mes, hora = _mes_y_hora(horas)
                    mes_hora = (mes - 1, hora)
                v = v.astype(np.float64) - rbar[mes_hora[0][fila], mes_hora[1][fila]]
            M[fila, j] = v
        if not interpola or tope < 2 or fila.all():
            continue
        k = np.flatnonzero(~fila)
        dentro = (pos[k] > 0) & (pos[k] < h.size)                              # con filas antes y después
        if valida is not None:
            dentro &= valida[k]
        k = k[dentro]
        if not k.size:
            continue
        previa = _observada_vecina(observada, pos[k] - 1, -1, tope)
        siguiente = _observada_vecina(observada, np.where(en_tabla[k], pos[k] + 1, pos[k]), 1, tope)
        par = (previa >= 0) & (siguiente >= 0)
        k, previa, siguiente = k[par], previa[par], siguiente[par]
        hp, hs = h[previa].astype(np.int64), h[siguiente].astype(np.int64)
        cerca = hs - hp <= tope                                                # ≥ 2: la hora queda entre las dos
        k, previa, siguiente, hp, hs = (z[cerca] for z in (k, previa, siguiente, hp, hs))
        if not k.size:
            continue
        ambas = col[np.concatenate([previa, siguiente])].astype(np.float64)
        if rbar is not None:
            _, mes, hora = _mes_y_hora(np.concatenate([hp, hs]))
            ambas = ambas - rbar[mes - 1, hora]
        vp, vs = ambas[:k.size], ambas[k.size:]
        validos = np.isfinite(vp) & np.isfinite(vs)
        k, hp, hs, vp, vs = (z[validos] for z in (k, hp, hs, vp, vs))
        tt = (horas[k] - hp) / (hs - hp)
        M[k, j] = (1.0 - tt) * vp + tt * vs
    return M


def matriz_q(datos, codigos, candidato, variable, horas, umbrales) -> np.ndarray:
    """q de B (r̃) o de Φ′ de AB (a) de las estaciones ``codigos`` en las ``horas`` (hora × estación, NaN donde no
    hay valor), con las horas no observadas interpoladas (CAN-6, CAN-7). Es la entrada de ``campo`` para el producto,
    las tablas laterales y la TF (I15, I16 e I19)."""
    cand = Candidato(candidato)
    if cand not in (Candidato.B, Candidato.AB):
        raise ErrorCandidatos("matriz_q es de B y AB; A usa las climatologías y C sus filas")
    horas = _horas(horas, "horas")
    return _matriz_en_horas(datos, tuple(codigos), "b" if cand is Candidato.B else "a", Variable(variable).value,
                            horas, umbrales)


def fuera_de_rango_c(estaticos_celdas, estaticos_entrenamiento) -> np.ndarray:
    """§4.6, «Área de aplicabilidad»: True en las celdas con algún estático (CAN-9: los 14 y las 5 indicadoras, en
    bruto) fuera del rango [mín, máx] de las celdas de las estaciones de entrenamiento (CAN-17). La fracción de
    población la calcula quien llama, con los pesos de 2020."""
    def estaticos(df):
        df = _estaticos_validos(df)
        h = np.zeros(1, dtype=np.int64)
        estado = {v: np.zeros(1) for v in ESTADO_C}
        filas = [_bases(df.iloc[[i]], h, estado) for i in range(len(df))]
        if not filas:
            return np.empty((0, len(ESTATICOS_C) + len(MACRO_C))), np.empty((0, len(TPI_C)), bool)
        B = np.vstack([f[0] for f in filas])[:, :len(ESTATICOS_C) + len(MACRO_C)]
        return B, np.vstack([f[1] for f in filas])
    Bc, tc = estaticos(estaticos_celdas)
    Be, te = estaticos(estaticos_entrenamiento)
    if not len(Be):
        raise ErrorCandidatos("fuera_de_rango_c: sin celdas de entrenamiento")
    truncado_e = np.zeros(Be.shape, bool)
    truncado_c = np.zeros(Bc.shape, bool)
    for k, b in enumerate(TPI_C):                                   # el TPI truncado vale 0 tras estandarizar
        truncado_e[:, BASES_C.index(b)] = te[:, k]
        truncado_c[:, BASES_C.index(b)] = tc[:, k]
    con_dato = np.where(truncado_e | ~np.isfinite(Be), np.nan, Be)
    with np.errstate(invalid="ignore"):
        bajo, alto = np.nanmin(con_dato, axis=0), np.nanmax(con_dato, axis=0)
        fuera = ((Bc < bajo) | (Bc > alto)) & ~truncado_c
    return fuera.any(axis=1)


def _fuera_de_la_grilla(info) -> bool:
    """D34 (NAS-17, ``estaticas_nasadem.fuera_de_la_grilla``): entra y no tiene celda (PED-1 pide el predicado en
    ``tipos``; ``test_candidatos`` vigila la paridad)."""
    return not info.excluida and info.celda is None


def _objetivo_estacion(datos, codigo: str, cand: Candidato, variable: str, umbrales, recorte: bool) \
        -> tuple[np.ndarray, np.ndarray]:
    """(horas, objetivo) de una estación de prueba interna en los días de selección (CAN-14)."""
    h, r = _serie(datos, codigo, "r", variable, umbrales)
    if h.size == 0:
        return _VACIA
    sel = np.isfinite(r) & particiones.dias_de_seleccion(h, umbrales, recorte=recorte)
    hs = h[sel]
    if cand is Candidato.A:
        _, mes, hora = _mes_y_hora(hs) if hs.size else (None, np.empty(0, np.int64), np.empty(0, np.int64))
        y = _rbar_estacion(datos, codigo, variable)[mes - 1, hora]
    elif cand in (Candidato.B, Candidato.AB):
        # r̃ o a en las horas hs, que son observadas: las interpoladas de «a» (horas no observadas) nunca coinciden con
        # ellas, así que buscarlas entre todas es lo mismo que entre las observadas (CAN-19)
        y = _matriz_en_horas(datos, (codigo,), "rt" if cand is Candidato.B else "a", variable, hs, umbrales)[:, 0]
    else:
        y = r[sel]
    ok = np.isfinite(y)
    return hs[ok], y[ok]


def _variables(variable) -> tuple[str, ...]:
    """MC-43: u, v y «uv» eligen juntos; las demás, solas."""
    v = str(variable)
    if v in VIENTO or v == UV or v == tipos.Grupo.U_V.value:
        return VIENTO
    return (Variable(v).value,)


def _comunes(objetivos: Mapping[str, tuple[np.ndarray, np.ndarray]], variables) -> tuple[np.ndarray, dict]:
    """Horas en que todas las variables tienen objetivo (MC-43) y el objetivo de cada una en ellas."""
    horas = None
    for v in variables:
        horas = objetivos[v][0] if horas is None else np.intersect1d(horas, objetivos[v][0], assume_unique=True)
    valores = {v: objetivos[v][1][np.searchsorted(objetivos[v][0], horas)] for v in variables}
    return horas, valores


def _grupos(infos) -> dict[str, str]:
    return {c: infos[c].grupo for c in sorted(infos) if not infos[c].excluida}


def _comprobar_datos(datos, externo) -> None:
    if not isinstance(datos, tipos.DatosCompetencia):
        raise ErrorCandidatos("datos debe ser tipos.DatosCompetencia")
    if not isinstance(externo, Pliegue):
        raise ErrorCandidatos("externo debe ser tipos.Pliegue")


def _grilla_nucleo(umbrales) -> list[tuple[float, float]]:
    return [(float(L), float(lam)) for L, lam in product(umbrales.a("NUC_L"), umbrales.a("NUC_LAMBDA"))]


# ---------------------------------------------------------------------------
# Selección anidada (§4.9, CAN-14)
# ---------------------------------------------------------------------------
def _sse_nucleo(cand: Candidato, variables, interno: Pliegue, datos, umbrales, recorte: bool) -> dict:
    """{(L, λ, κ): {código: (sse, n)}} de un pliegue interno para A, B o Φ′ de AB."""
    infos = datos.estaciones
    entrenamiento = {c: infos[c] for c in interno.entrenamiento}
    objetivos, prueba = {}, []
    for c in interno.prueba:
        if _fuera_de_la_grilla(infos[c]):            # D34: sin evaluación en ningún candidato (CAN-14)
            continue
        por_var = {v: _objetivo_estacion(datos, c, cand, v, umbrales, recorte) for v in variables}
        horas, valores = _comunes(por_var, variables)
        if horas.size:
            objetivos[c] = (horas, valores)
            prueba.append(c)
    kappas = [float(k) for k in umbrales.a("NUC_KAPPA")]
    salida: dict = {}
    if not prueba:
        for L, lam in _grilla_nucleo(umbrales):
            for kappa in kappas:
                salida[(L, lam, kappa)] = {}
        return salida
    pts = puntos_de_estaciones(infos, prueba)
    codigos_t = tuple(sorted(entrenamiento))
    if cand is Candidato.A:
        rbar = {v: _rbar_matrices(datos.climatologias, codigos_t, v) for v in variables}
    else:
        clase = "b" if cand is Candidato.B else "a"
        union = np.unique(np.concatenate([objetivos[c][0] for c in prueba]))
        Q = {v: _matriz_en_horas(datos, codigos_t, clase, v, union, umbrales) for v in variables}
        posiciones = {c: np.searchsorted(union, objetivos[c][0]) for c in prueba}
    for L, lam in _grilla_nucleo(umbrales):
        vec = vecinos(pts, entrenamiento, Hiper(L, lam, kappas[0]), umbrales)
        if cand is Candidato.A:
            sumas = {v: _sumas_a(vec, rbar[v]) for v in variables}
        else:
            sumas = {v: sumas_nucleo(vec, Q[v], np.isfinite(Q[v])) for v in variables}
        for kappa in kappas:
            por_estacion = {}
            for i, c in enumerate(prueba):
                horas, valores = objetivos[c]
                sse = 0.0
                for v in variables:
                    num, den = sumas[v]
                    if cand is Candidato.A:
                        pred = _a_en_horas(num, den, kappa, horas, columna=i)[0]
                    else:
                        p = posiciones[c]
                        pred = num[p, i] / (kappa + den[p, i])
                    e = pred - valores[v]
                    sse += float(np.dot(e, e))
                por_estacion[c] = (sse, int(horas.size))
            salida[(L, lam, kappa)] = por_estacion
    return salida


def _datos_c_estacion(datos, codigo: str, cand: Candidato):
    """(fila de estáticos, estado) de una estación para C o C_est; None sólo fuera de la grilla (D34) y
    ``ErrorCandidatos`` si le falta un insumo (CAN-13)."""
    fuente = datos.puntos_e5l if cand is Candidato.C else datos.clima_estado
    return _insumos_c(codigo, datos.estaciones[codigo], _estaticos_validos(datos.estaticos), fuente,
                      cand is Candidato.C_EST)


def _filas_de(datos, cand: Candidato, variable: str) -> Mapping[str, SumasC]:
    try:
        return datos.filas_c[cand.value][variable]
    except KeyError:
        raise ErrorCandidatos(f"datos.filas_c no trae {cand.value}/{variable}") from None


def _sse_c(cand: Candidato, variables, interno: Pliegue, datos, umbrales, recorte: bool) -> dict:
    """{α: {código: (sse, n)}} de un pliegue interno para C o C_est. CAN-19: el diseño de una estación de prueba se
    arma dos veces (una para saber qué filas son finitas, otra para predecir) y vive sólo mientras se usa; los ajustes
    y los modelos de cada α se calculan antes, y cada suma se acumula en el mismo orden que antes."""
    climatologico = cand is Candidato.C_EST
    prueba = {}
    for c in interno.prueba:
        dc = _datos_c_estacion(datos, c, cand)
        if dc is None:
            continue
        por_var = {v: _objetivo_estacion(datos, c, cand, v, umbrales, recorte) for v in variables}
        horas, valores = _comunes(por_var, variables)
        X = diseno_c(dc[0], horas, dc[1], climatologico=climatologico)
        finita = np.isfinite(X).all(axis=1)                 # sin diseño finito C no predice (CAN-10)
        del X
        if finita.any():
            prueba[c] = (horas, finita, {v: valores[v][finita] for v in variables}, dc)
    alfas = [float(a) for a in umbrales.a("C_ALFAS")]
    salida = {a: {} for a in alfas}
    if not prueba:
        return salida
    ajustes = {v: _ajuste_c(_filas_de(datos, cand, v), interno.entrenamiento) for v in variables}
    modelos = {alfa: {v: _resolver_c(ajustes[v], alfa) for v in variables} for alfa in alfas}
    for c, (horas, finita, valores, dc) in prueba.items():
        X = diseno_c(dc[0], horas, dc[1], climatologico=climatologico)[finita]      # el mismo cálculo, otra vez
        sse = dict.fromkeys(modelos, 0.0)               # una suma por α distinto, como antes (un α repetido, igual)
        for v in variables:
            estandar = np.matmul(X, ajustes[v].T)
            for alfa in sse:
                e = np.matmul(estandar, modelos[alfa][v].coef) - valores[v]
                sse[alfa] += float(np.dot(e, e))
            del estandar
        del X
        n = int(np.count_nonzero(finita))
        for alfa in sse:
            salida[alfa][c] = (sse[alfa], n)
    return salida


def _uso_del_candidato(cand: Candidato, uso) -> Uso:
    """El uso, con la guarda de §4.7 («Candidato C_est (sólo lo crónico)»), común a la selección y la predicción."""
    uso = Uso(uso)
    if cand is Candidato.C_EST and uso is not Uso.CRONICO:
        raise ErrorCandidatos("C_est es sólo de lo crónico (§4.7)")
    return uso


def seleccionar(candidato, variable, uso, externo, datos, umbrales, *, objetivo: Callable, recorte: bool,
                hiper_a: Hiper | None = None) -> object:
    """Hiperparámetros de un candidato, variable y uso por selección anidada dentro del pliegue ``externo`` (§4.9,
    CAN-14): ``tipos.Hiper`` en A y B; (Hiper de A, Hiper de Φ′) en AB; α en C y C_est. ``objetivo(internos, sumas,
    *, candidato, variable, uso)`` recibe {pliegue interno: {código: (sse, n)}} y da el valor a minimizar (los pesos
    del uso de §5.3, PED-3). ``recorte``: mód ``SEL_MOD_RECORTE`` en vez de ``SEL_MOD`` (lo fija el addendum de M1)."""
    cand = Candidato(candidato)
    uso = _uso_del_candidato(cand, uso)
    _comprobar_datos(datos, externo)
    if not isinstance(recorte, bool):
        raise ErrorCandidatos("recorte es True o False (lo fija el addendum de M1)")
    variables = _variables(variable)
    etiqueta = UV if variables == VIENTO else variables[0]
    internos = tuple(particiones.pliegues_internos(externo, datos.estaciones, _grupos(datos.estaciones), umbrales))
    if not internos:
        raise SinSeleccion(f"{externo.id}: sin pliegues internos")
    hiper_de_a = None
    if cand is Candidato.AB:
        hiper_de_a = hiper_a if hiper_a is not None else seleccionar(
            Candidato.A, variable, uso, externo, datos, umbrales, objetivo=objetivo, recorte=recorte)
        _hiper(hiper_de_a)
    calcular = _sse_c if cand in DE_C else _sse_nucleo
    por_interno = {p.id: calcular(cand, variables, p, datos, umbrales, recorte) for p in internos}
    mejor, valor_mejor = None, None
    for theta in por_interno[internos[0].id]:                     # orden del texto (CAN-14)
        sumas = {p.id: por_interno[p.id][theta] for p in internos}
        valor = float(objetivo(internos, sumas, candidato=cand, variable=etiqueta, uso=uso))
        if math.isfinite(valor) and (valor_mejor is None or valor < valor_mejor):
            mejor, valor_mejor = theta, valor
    if mejor is None:
        raise SinSeleccion(f"{externo.id}: ningún objetivo finito para {cand.value} en {etiqueta} ({uso.value})")
    if cand in DE_C:
        return float(mejor)
    elegido = Hiper(*mejor)
    return (hiper_de_a, elegido) if cand is Candidato.AB else elegido


# ---------------------------------------------------------------------------
# Predicción en las estaciones de prueba (CAN-15)
# ---------------------------------------------------------------------------
def _lotes_mensuales(horas: np.ndarray):
    if horas.size == 0:
        return
    meses = homogeneidad.mes2000(horas)
    cortes = np.flatnonzero(np.diff(meses)) + 1
    yield from np.split(np.arange(horas.size), cortes)


def _prediccion_nucleo(cand: Candidato, variable: str, hiper, externo: Pliegue, datos, umbrales,
                       horas_de: Mapping[str, np.ndarray]) -> dict:
    infos = datos.estaciones
    prueba = [c for c in externo.prueba if horas_de[c].size]
    salida = {c: (np.full(horas_de[c].shape, np.nan), np.zeros(horas_de[c].shape, bool)) for c in externo.prueba}
    if not prueba:
        return salida
    entrenamiento = {c: infos[c] for c in externo.entrenamiento}
    codigos_t = tuple(sorted(entrenamiento))
    pts = puntos_de_estaciones(infos, prueba)
    hiper_a, hiper_q = (hiper if cand is Candidato.AB else (hiper, hiper))
    if cand in (Candidato.A, Candidato.AB):
        vec_a = vecinos(pts, entrenamiento, hiper_a, umbrales)
        num12, den12 = _sumas_a(vec_a, _rbar_matrices(datos.climatologias, codigos_t, variable))
        _, _, kappa_a = _hiper(hiper_a)
        for i, c in enumerate(prueba):
            salida[c] = _a_en_horas(num12, den12, kappa_a, horas_de[c], columna=i)
        if cand is Candidato.A:
            return {c: (v, s > 0) for c, (v, s) in salida.items()}
    vec_q = vecinos(pts, entrenamiento, hiper_q, umbrales)
    _, _, kappa_q = _hiper(hiper_q)
    clase = "b" if cand is Candidato.B else "a"
    union = np.unique(np.concatenate([horas_de[c] for c in prueba]))
    phi, sk = np.full((union.size, len(prueba)), np.nan), np.zeros((union.size, len(prueba)))
    for lote in _lotes_mensuales(union):
        Q = _matriz_en_horas(datos, codigos_t, clase, variable, union[lote], umbrales)
        num, den = sumas_nucleo(vec_q, Q, np.isfinite(Q))
        phi[lote], sk[lote] = num / (kappa_q + den), den
    final = {}
    for i, c in enumerate(prueba):
        p = np.searchsorted(union, horas_de[c])
        if cand is Candidato.B:
            final[c] = (phi[p, i], sk[p, i] > 0)
        else:
            a_val, a_sk = salida[c]
            final[c] = (a_val + phi[p, i], (a_sk > 0) | (sk[p, i] > 0))
    for c in externo.prueba:
        final.setdefault(c, salida[c])
    return final


def _prediccion_c(cand: Candidato, variable: str, alfa, externo: Pliegue, datos, horas_de) -> dict:
    modelo = None
    salida = {}
    for c in externo.prueba:
        h = horas_de[c]
        valores = np.full(h.shape, np.nan)
        dc = _datos_c_estacion(datos, c, cand)                      # un insumo que falta es error (CAN-13)
        if dc is not None and h.size:
            if modelo is None:
                modelo = ajustar_c(_filas_de(datos, cand, variable), externo.entrenamiento, alfa)
            for lote in _lotes_mensuales(h):
                valores[lote] = predecir_c(modelo, dc[0], h[lote], dc[1])
        salida[c] = (valores, np.isfinite(valores))
    return salida


def predecir_prueba(candidato, variable, uso, hiper, externo, datos, *, umbrales) -> pd.DataFrame:
    """La corrección del candidato en todas las horas observadas de las estaciones de prueba de ``externo``, con los
    hiperparámetros ``hiper`` (los de ``seleccionar``) y su entrenamiento (CAN-15). Columnas ``codigo``, ``h``,
    ``correccion`` y ``soporte`` (``COLUMNAS_PREDICCION``, PED-4), en orden de código y hora. En memoria: R nunca se
    guarda ni se informa (§0.4.3)."""
    cand = Candidato(candidato)
    _uso_del_candidato(cand, uso)                                    # C_est sólo en lo crónico (§4.7, CAN-15)
    _comprobar_datos(datos, externo)
    variable = Variable(variable).value
    horas_de = {c: _horas_de_estacion(datos, c) for c in externo.prueba}          # las de _serie(…, «r», …)
    if cand in DE_C:
        if isinstance(hiper, bool) or not isinstance(hiper, (int, float)):
            raise ErrorCandidatos(f"el hiperparámetro de {cand.value} es α (float), no {hiper!r}")
        por_estacion = _prediccion_c(cand, variable, float(hiper), externo, datos, horas_de)
    else:
        if cand is Candidato.AB:
            if not (isinstance(hiper, tuple) and len(hiper) == 2):
                raise ErrorCandidatos("los hiperparámetros de AB son (Hiper de A, Hiper de Φ′)")
            _hiper(hiper[0])
            _hiper(hiper[1])
        else:
            _hiper(hiper)
        por_estacion = _prediccion_nucleo(cand, variable, hiper, externo, datos, umbrales, horas_de)
    codigos, horas, valores, soporte = [], [], [], []
    for c in sorted(externo.prueba):
        v, s = por_estacion[c]
        codigos += [c] * horas_de[c].size
        horas.append(horas_de[c])
        valores.append(v)
        soporte.append(s)
    df = pd.DataFrame({"codigo": codigos,
                       "h": np.concatenate(horas) if horas else np.empty(0, np.int64),
                       "correccion": np.concatenate(valores) if valores else np.empty(0),
                       "soporte": np.concatenate(soporte) if soporte else np.empty(0, bool)})
    df = df.astype(COLUMNAS_PREDICCION)
    df.attrs.update({"candidato": cand.value, "variable": variable, "pliegue": externo.id})
    return df


__all__ = (
    "BASES_C", "COLUMNAS_C", "COLUMNAS_PREDICCION", "ErrorCandidatos", "MONOMIOS_C", "SinSeleccion", "SumasC",
    "VecinosEntrenamiento", "ajustar_c", "campo", "climatologia_a", "climatologias_a", "correccion_a",
    "correccion_ab", "correccion_b", "diseno_c", "diseno_estandarizado", "distancia_efectiva", "estado_c",
    "estado_c_est", "filas_c", "fuera_de_rango_c", "interpolar_no_observadas", "matriz_q", "predecir_c",
    "predecir_prueba", "puntos_de_estaciones",
    "residuos_estacion", "seleccionar", "sumas_nucleo", "vecinos",
)
