"""Fondo ERA5-Land reescalado (§4.1): lector mensual propio, z_E5L, operador, campos, residuos y lluvia (§2.6, §3).

Es un insumo común, no un candidato. Nunca se resume ni se compara con observaciones fuera de la memoria (§0.4.2):
este módulo no escribe nada y no calcula ninguna estadística del residuo (ni mediana, ni MAD, ni sesgo). Los residuos
salen sólo en memoria, para quien los pide (A3 de ``COORDINACION_M1.md``).

Qué hace cada función (y para qué compuerta):
- ``leer_mes`` (``MesE5L``, con ``completo_hasta``) y ``comprobar_unidades``: el lector mensual propio y la regla de
  unidades por rango (M2a, M3-4, M5; S12 y S13). ``pixeles_validos``: la regla de los tres meses (§4.1).
- ``leer_geopotencial``, ``z_e5l`` y ``comprobar_alineacion``: la altitud de cada píxel y su alineación con el parquet
  derivado (M2a, pasos 4; S13). La tabla NASADEM por píxel llega de ``estaticas_nasadem.nasadem_en_pixeles`` (A9).
- ``operador``, ``operador_pixeles``, ``columnas_operador`` y ``operador_desde_columnas``: el operador del fondo
  (bilineal con vecino a ≤ 16 km) para estaciones y celdas, y el de los centros de los píxeles (A8, A10).
- ``campos_fondo``: T_F, Td_F, p_F, u_F y v_F de un mes en los puntos de un operador. ``tabla_puntos`` y ``en_horas``:
  el fondo en las estaciones (``ESQUEMA_PUNTOS_E5L``) y su alineación con la tabla ancha (A1, A2).
- ``residuos`` y ``producto_desde``: r = obs − F (r_p = ln(QFE/p_F)) y el producto F + R (A3).
- ``incrementos_tp`` y ``sumas_rr06``: la lluvia horaria sobre la serie continua y las sumas de 6 h para RR06 (§2.6).
  ``pixel_de_lluvia`` y ``lluvia_rr06``: el píxel de la lluvia de cada estación y su suma de 6 h por reporte (D27).
- ``acumulador_estado``, ``climatologias_estado``, ``tabla_clima_estado`` y ``sp_medio_hpa``: las climatologías del
  estado por píxel, mes y hora UTC de 2000-2025 (C_est, §4.7) y sp̄ de la altitud hipsométrica, en una sola pasada.
  ``clima_en_puntos`` y ``clima_en_horas``: el operador del fondo aplicado a esas climatologías (§4.7, D29).
- ``amplitud_dia_utc``: la amplitud diaria de T en el día UTC (estado de C, §4.6).

Dueño: I7 (ola 2; D27-D29 en la ola 3).
Lecturas propias (FON-n), para el addendum de M1:
- FON-1. **Lector propio** (``leer_mes``). Lee los bytes una sola vez: la sha256 es la de esos bytes (si se da una,
  debe coincidir) y netCDF4 los abre en memoria, como el lector del reloj. Exige el eje «<seconds|minutes|hours> since
  <fecha> [hora] [UTC]» (la hora del origen cuenta) con calendario gregoriano o proleptic_gregorian (o sin
  calendario) y valores enteros; **toda hora debe ser HH:00 exacta** (una 01:30 se rechaza: ``MesNativo.indice_tiempo``
  la redondearía hacia abajo, S12), las horas van estrictamente crecientes y todas en el mismo mes UTC; ``pixel_id``
  sin repetir ni enmascarado; t2m, d2m, sp, u10, v10 y tp con dimensiones (time, pixel), en float32 y NaN donde el
  archivo enmascara o no es finito. Las unidades no se convierten aquí. ``tiempos`` es ``h`` (int32, horas desde
  2000-01-01T00Z). Un hueco de horas no se rechaza al leer (el producto no interpola en el tiempo, §3).
  ``MesE5L.completo_hasta(h_ultima)`` dice si el mes trae todas sus horas, de 1 h en 1 h, desde su primera hora hasta
  mín(su última hora, ``h_ultima``) y ninguna después, con ``h_ultima`` la última hora con dato de los manifiestos de
  ERA5-Land: el producto va «del 2000-01-01 a su último dato (hoy 2026-09-15 23:00 UTC)» (§3), así que el último mes
  es parcial y está completo si llega a esa hora. Esa hora no es una constante (``constantes`` la tiene como
  descripción): la da quien llama, como ``reloj_dmc.extraccion._limites_mes`` con ``mín(fin, ULTIMA_HORA_ERA5)``. Es
  más estricto que el reloj, que acepta horas después de esa: aquí una hora después de ``h_ultima`` contradice al
  manifiesto y el mes no está completo. La orquestación lo exige en cada mes; no hay una completitud por mes
  calendario.
- FON-2. **Unidades por rango** (§4.1, como RELOJ §3.4). Mediana de todos los píxeles y horas del mes, sin los NaN:
  t2m y d2m en [200, 330] K y sp en [40.000, 110.000] Pa (bordes incluidos); |mediana| de u10 y v10 < 30 m/s. Un mes
  sin ningún valor finito de esas variables también aborta. tp no tiene regla en el texto: su paso de m a mm es de
  ``incrementos_tp``. Los rangos son del A2 (``constantes``): ``umbrales`` no se usa. **Todo error de este módulo es
  un ``ErrorFondo``** (``RuntimeError``): los de ERA5-Land, el geopotencial o el catálogo, y también los de una tabla
  o un arreglo mal armado o desalineado que recibe (``residuos``, ``en_horas``, ``tabla_puntos``, ``producto_desde``,
  ``operador``…), aunque nazca como ``ValueError`` o ``TypeError`` en numpy, pandas o ``tipos``: toda función pública
  pasa por ``_errores_de_fondo``. Así un error de código detiene la corrida y nunca cuenta como «no normalizable» si
  quien llama lo hace dentro de la captura de ``ValueError`` y ``TypeError`` del paso 1 de §2.1 (Q3, MC-57).
- FON-3. **Píxeles válidos** (§4.1, MC-39). Las claves de ``meses_referencia`` deben ser exactamente 200001, 201307 y
  202507 (texto o entero) y cada mes debe ser el de su clave; t2m y sp con algún valor finito en cada uno; la
  intersección, en orden de ``pixel_id``.
- FON-4. **z_E5L** (§4.1). El geopotencial se ubica en la grilla global de 0,1° por índices, i = (90 − lat)/0,1 y
  j = (lon mód 360)/0,1. Si el eje crudo es float32, se exige igualdad exacta con el float32 del centro de 0,1° y
  sólo entonces se lo decodifica al centro en float64, antes de normalizar la longitud (errata 2, 2026-11-01).
  Los demás ejes conservan la holgura ≤ 10⁻⁵°; no se los convierte a float32 para aceptarlos. La holgura anterior
  aplicada al crudo float32 rechazaba centros válidos de longitudes 0..360; no se aumenta esa tolerancia.
  z = z_geo/9,80665 en float64 desde el float32 del archivo: la misma cuenta que el parquet derivado. Caso 2: la media
  NASADEM de la huella del píxel con ``frac_nasadem`` ≥ ``U.frac("ZE5L_NASADEM_PCT")`` y finita (tabla de A9). Caso 3:
  la hipsométrica desde sp̄ en hPa (``sp_medio_hpa``, 2000-2025). ``z_hipso`` se calcula en todo píxel con sp̄, para el
  aviso ``dif_mayor_50m`` = |z_NASADEM − z_hipso| > 50 m (con los dos finitos; si no, False). ``valido`` es la regla
  de los tres meses. Un píxel válido sin ningún caso detiene M2a (``ErrorFondo``); uno no válido queda con z NaN y
  caso nulo.
- FON-5. **Alineación** (MC-38). Mismo conjunto de ``pixel_id`` en los dos, sin repetir, y |z_E5L − z_m| ≤ 0,001 m en
  todos; un NaN en cualquiera de los dos cuenta como diferencia. Si no, ``ErrorAlineacion`` con el número de píxeles
  que difieren (sin valores). La detención de M2a la hace la orquestación (I20).
- FON-6. **Operador** (§4.1, MC-39, MC-60). Bilineal en índices de malla: índice fraccionario (90 − lat)/0,1 y
  (lon mód 360)/0,1, llevado al entero si dista < 10⁻⁹ (redondeo de la división, no una regla: en latitudes norte como
  64,1° la cuenta en float64 no da el entero exacto), y los 4 centros que lo rodean en orden fijo (NO, NE, SO, SE),
  con pesos (1−di)(1−dj), (1−di)dj, di(1−dj) y di·dj. Un vecino cuenta sólo si su peso es > 0, está en el catálogo y
  es válido (los demás son «vecinos sin dato»); los que quedan se renormalizan. Si no queda ninguno: el centro válido
  más cercano por haversine (R = 6.371 km) a ≤ ``VECINO_KM`` (16 km, borde incluido; el mismo para estaciones, celdas
  y píxeles, no los 15 km con que RELOJ elige su píxel), empate por menor ``pixel_id``, con peso 1 y ``respaldo`` =
  True. Si tampoco hay, el punto queda sin fondo (``pix`` = −1 en las cuatro casillas). Las casillas sin vecino
  llevan ``pix`` −1, ``w`` 0 y ``dz`` NaN. Un píxel válido sin z_E5L finita detiene la construcción. Un punto sin
  latitud o longitud finitas queda sin fondo; uno sin z finita tiene u_F y v_F pero no T_F, Td_F ni p_F (dependen de
  z_x − z_i). **En los píxeles** (A10) el operador es ``operador_pixeles``, por ``pixel_id`` y no por coordenadas:
  cada píxel válido es su único vecino, con peso 1, z = z_E5L y dz = 0, así que «allí el fondo es ERA5-Land tal cual»
  (§3), bit a bit. Las coordenadas del catálogo pueden estar hasta a 10⁻⁵° del centro (FON-4), y con ellas el
  bilineal daría varios vecinos de peso casi nulo y una T_F distinta de t2m − 273,15. Un píxel no válido o fuera del
  catálogo no tiene producto (§3: los píxeles válidos) y detiene la construcción.
- FON-7. **Campos** (§4.1). Todo en float64 desde el float32 del archivo, sumando las casillas en su orden fijo. T_i =
  t2m − 273,15; T_i′ = T_i + Γ·(z_x − z_i)/1000, con Γ = ``U.a("GAMMA_K_KM")``; T̄_i = (T_i + T_i′)/2 + 273,15 (K);
  p′_i = (sp_i/100)·exp(−9,80665·(z_x − z_i)/(287,05·T̄_i)); Td′_i por conservación de q (e_i = e_s(Td_i), q_i =
  0,622·e_i/(sp_i − 0,378·e_i), e′_i = q_i·p′_i/(0,622 + 0,378·q_i), Td′_i = Magnus⁻¹(e′_i)); con z_x = z_i se usa la
  identidad Td′_i = Td_i (es la misma cuenta sin su error de redondeo). **Renormalización por hora** (MC-39): cada campo
  usa los vecinos con sus entradas finitas en esa hora (T: t2m; p: sp y t2m; Td: d2m, sp y t2m; u: u10; v: v10) y
  divide por la suma de sus pesos; ``renormalizada`` marca los punto-hora en que algún campo perdió un vecino con dato
  (la orquestación los cuenta para el registro). Sin ningún vecino con dato, NaN. Después, Td_F := mín(Td_F, T_F);
  ``recortar_td=False`` existe sólo para la regresión S14, que pide el fondo «sin el recorte Td ≤ T».
- FON-8. **float32** (A1 y A3). ``residuos`` redondea a float32 el fondo **y la observación** antes de restar en
  float64: la tabla ancha guarda las observaciones en float32 (``ESQUEMA_QC_ESTACION``) y el fondo en las estaciones
  también (``ESQUEMA_PUNTOS_E5L``), así que la corrida que lee del disco y la que trae todo en memoria dan lo mismo, bit a bit
  (S9). ``producto_desde`` no redondea: sirve para celdas y píxeles, cuyo fondo no se guarda, y la regresión S14 (1e-9)
  no admitiría el redondeo; el fondo de una estación le llega ya en float32 desde ``en_horas``.
- FON-9. **Fondo en las estaciones** (A1). ``tabla_puntos`` arma ``ESQUEMA_PUNTOS_E5L`` con ``h`` estrictamente
  creciente, ``amp_TF`` desde T_F en float64 y todo en float32. Como un día UTC nunca cruza un archivo mensual, armarla
  mes a mes y concatenar da la misma tabla. ``en_horas`` da las columnas en float64 en las horas pedidas, NaN donde la
  tabla no tiene la hora (A2).
- FON-10. **Amplitud diaria** (§4.6). Máximo menos mínimo de T en las 24 horas del día UTC, asignada a cada hora de ese
  día; NaN si al día le falta alguna hora o trae un NaN.
- FON-11. **Lluvia horaria** (§2.6, «como en ``meteo_civil_v3``», ``lluvia_horaria``, 483f63a6…): la diferencia del
  acumulado tp con la hora previa sólo si ésta es exactamente h − 1 en la serie continua de los meses dados; a las 01
  UTC el acumulado ya es la hora; por 1000 (m → mm) y recortada en 0, como ese código. Sin la hora previa, NaN (el
  primer incremento de un mes leído solo, S13).
- FON-12. **RR06** (§2.6). La suma de los 6 incrementos que terminan en la hora UTC del rótulo (u − 5, …, u), en orden
  cronológico; NaN si falta alguno (no hay sumas parciales). **El punto de la lluvia de una estación** (D27, P16): el
  píxel que ``enlaces_productos.parquet`` enlaza a su celda (``era5land_pixel``), sin pesos bilineales ni Γ; es la
  lluvia que da el producto en esa celda (tp sin cambios, §3; MC-13). ``pixel_de_lluvia`` lo busca y ``lluvia_rr06``
  suma en él con la misma cuenta y el mismo orden que ``sumas_rr06`` (bit a bit). Sin enlace (una estación sin celda,
  D34, o una celda con ``era5land_pixel`` = −1, la «sin_enlace» de ``construir_grilla``) el reporte no se compara: suma
  NaN y ``sin_enlace`` = True, que quien llama cuenta aparte de los NaN por falta de tp (una ventana incompleta no es
  «sin enlace»). Lecturas estrictas donde D27 calla: la tabla de enlaces trae ``celda`` sin repetir y
  ``era5land_pixel`` entero, sin nulos y ≥ −1; si trae ``era5land_enlace``, «sin_enlace» va con −1 y sólo con −1, sin
  nulos. Una celda de estación que no está en la tabla, o un píxel enlazado que no está en los meses ERA5-Land leídos,
  contradice a los insumos fijados: es un ``ErrorFondo``, no un «sin enlace».
- FON-13. **Climatologías del estado** (§4.7). Por píxel, mes (1-12, de la hora UTC) y hora UTC, la media de todas las
  horas con valor finito de los meses 2000-2025: T (°C), T − Td (K), rapidez √(u10² + v10²) y la amplitud diaria de T
  (FON-10) de cada hora. **T − Td lleva el recorte hora a hora** (D29, P18): máx(t2m − d2m, 0) en cada hora, antes de
  promediar, que es lo que C ve en T_F − Td_F en un píxel (Td_F := mín(Td_F, T_F), §4.1). Una hora sin t2m o sin d2m
  no suma (NaN, no 0). Es la climatología de cada variable de estado tal como entra en C (§4.6), así que la de la
  amplitud es la media de las amplitudes diarias (D28, P17). Los meses fuera de 2000-2025 no suman; un mes dado dos
  veces es un error. Sin mínimo de valores (el texto no lo pide). En la misma pasada se acumula sp̄ (2000-2025, la
  media de sp de todas las horas con dato, en hPa) para el caso 3 de z_E5L. Las sumas son float64 en el orden en que
  llegan los meses (MC-37).
- FON-14. **El operador sobre las climatologías** (§4.7, D29, P18). ``clima_en_puntos`` aplica a la tabla de FON-13
  (``ESQUEMA_CLIMA_ESTADO``: sus float32, en float64) el operador de FON-6 de los puntos (estaciones, celdas o
  píxeles), en cada mes y hora UTC: T con los pesos bilineales y Γ, Σ w_i [T_i + Γ·(z_x − z_i)/1000]; T − Td, rapidez y
  amplitud con los pesos bilineales solos, Σ w_i X_i, sin ajuste por altura (no dependen de z_x: sin z finita sólo T
  queda NaN, como T_F). Los vecinos sin valor finito en ese mes y hora se descartan y se renormaliza, como hora a hora
  en FON-7 (MC-39); ``renormalizada`` marca los punto-mes-hora en que alguna variable perdió un vecino; sin ninguno,
  NaN.
  Las casillas se suman en su orden fijo y no hay recorte después (la media ponderada de valores ≥ 0 es ≥ 0). Con
  ``operador_pixeles`` da la tabla tal cual (peso 1, dz = 0), bit a bit, y por lotes de puntos da lo mismo. Lecturas
  estrictas donde D29 calla: cada píxel de la tabla trae sus 12 × 24 filas exactas (mes 1-12, hora 0-23) sin repetir, y
  todo vecino del operador está en la tabla; si no, ``ErrorFondo``. ``clima_en_horas`` lleva el resultado a las horas h
  (el mes y la hora UTC de cada h, como en FON-13). ``candidatos`` no puede importar este módulo (§1 del diseño): lo
  llama quien arma los datos de C_est (``orquestacion``) y le pasa el resultado.
Depende de: tipos, constantes, numerico, entorno (sha256).
"""
from __future__ import annotations

import functools
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from meteo_combinada import constantes, entorno, numerico, tipos

# ---------------------------------------------------------------------------
# Nombres y constantes
# ---------------------------------------------------------------------------
VARIABLES_E5L = ("t2m", "d2m", "sp", "u10", "v10", "tp")
CAMPOS_F = ("T_F", "Td_F", "p_F", "u_F", "v_F")
CLAVES_OBS = ("T", "Td", "u", "v", "QFE")          # A3: Ts, td_final, u_final, v_final y QFE
CLAVES_R = ("R_T", "R_Td", "R_u", "R_v", "R_p")
CLAVES_PRODUCTO = ("T", "Td", "u", "v", "p")
CLAVES_RESIDUOS = ("r_T", "r_Td", "r_u", "r_v", "r_p")
COLUMNAS_PUNTOS = tuple(tipos.ESQUEMA_PUNTOS_E5L)   # h, T_F, Td_F, p_F, u_F, v_F, amp_TF
VARIABLES_CLIMA = ("T", "T_menos_Td", "rapidez", "amp")      # ESQUEMA_CLIMA_ESTADO, en este orden
COLUMNAS_OPERADOR = ("pix0", "pix1", "pix2", "pix3", "w0", "w1", "w2", "w3", "respaldo_16km", "sin_fondo")

EPOCA_H = np.datetime64("2000-01-01T00", "h")       # h = 0 (tipos.EPOCA_H)
_EPOCA_S = np.datetime64("2000-01-01T00:00:00", "s")
_UNIX_S = np.datetime64("1970-01-01T00:00:00", "s")

_KELVIN = constantes.valor("KELVIN")
_G = constantes.valor("GRAVEDAD")
_R_SECO = constantes.valor("R_SECO")
_EPS_Q, _COMP_Q = constantes.valor("Q_ESPECIFICA")              # 0,622 y 0,378 (§4.1)
_RES = constantes.valor("PRODUCTO_01_GRADOS")                   # 0,1°
_N_VECINOS = constantes.valor("FONDO_VECINOS")                  # 4
_HORAS_RR06 = constantes.valor("RR06_HORAS")                    # 6
_T_K = constantes.valor("E5L_T_K")
_SP_PA = constantes.valor("E5L_SP_PA")
_UV_MS = constantes.valor("E5L_UV_MS")
_MESES_VALIDEZ = tuple(int(m) for m in constantes.valor("PIXEL_MESES_VALIDEZ"))
_PERIODO_CLIMA = constantes.valor("C_EST_PERIODO")              # 2000-2025 (§4.7)
_PERIODO_SP = constantes.valor("ZE5L_SP_PERIODO")               # 2000-2025 (§4.1)
_DIF_AVISO_M = constantes.valor("ZE5L_DIF_INFORME_M")           # 50 m (§4.1)
_R_TIERRA_KM = constantes.valor("R_TIERRA_KM")

_PA_POR_HPA = 100.0
_MM_POR_M = 1000.0
_M_POR_KM = 1000.0
_SEGUNDOS_H = 3600
_HORAS_DIA = 24
_MESES_ANIO = 12
_LAT_POLO = 90.0             # no-umbral: latitud del polo norte, origen de los índices globales de ERA5-Land
_GRADOS_VUELTA = 360.0       # no-umbral: grados de una vuelta (lon mód 360)
_MEDIA_VUELTA = 180.0        # no-umbral: longitud en −180..180
_CELDAS_POR_GRADO = int(round(1 / _RES))                          # 10 centros por grado (índices exactos)
_COLUMNAS_GLOBALES = int(round(_GRADOS_VUELTA)) * _CELDAS_POR_GRADO   # 3.600 columnas de 0,1°
_TOL_INDICE = 1e-9           # no-umbral: holgura de redondeo al llevar una coordenada a índice de malla (FON-6)
_TOL_GRILLA_GRADOS = 1e-5    # coordenadas float32 de un centro de 0,1° (FON-4)
_HOLGURA_ARBOL = 1e-7        # holgura relativa de la búsqueda en el árbol; decide haversine (FON-6)
TOL_ALINEACION_M = 1e-3      # MC-38: |z_E5L − z_parquet| ≤ 0,001 m
# Enlaces celda–píxel de ``grilla_1km/enlaces_productos.parquet`` (``construir_grilla.enlazar_pixel_valido``): sin
# enlace, ``era5land_pixel`` = −1 y ``era5land_enlace`` = «sin_enlace» (FON-12, D27).
COLUMNAS_ENLACE = ("celda", "era5land_pixel")
_COLUMNA_TIPO_ENLACE = "era5land_enlace"
SIN_ENLACE = "sin_enlace"
_SIN_PIXEL = -1

# Eje de tiempo del NetCDF (FON-1), como el lector del reloj.
_UNIDADES_TIEMPO = re.compile(r"(?P<unidad>seconds|minutes|hours) since (?P<fecha>\d{4}-\d{2}-\d{2})"
                              r"(?:[ T](?P<hora>\d{2}:\d{2}(?::\d{2})?))?\s*(?:UTC|Z|\+00:00|\+0000)?")
_FACTOR_TIEMPO = {"seconds": 1, "minutes": 60, "hours": _SEGUNDOS_H}
_CALENDARIOS = (None, "standard", "gregorian", "proleptic_gregorian")
# Unidades del geopotencial que acepta el descargador (descargar_era5land_geopotencial.UNIDADES_ACEPTADAS).
UNIDADES_GEOPOTENCIAL = frozenset({"m**2 s**-2", "m2 s-2", "m^2 s^-2", "m2/s2", "m**2/s**2"})


class ErrorFondo(RuntimeError):
    """ERA5-Land, el geopotencial o el catálogo con estructura o contenido inesperado, o una entrada mal armada o
    desalineada: se detiene (FON-2). No es un ``ValueError`` ni un ``TypeError`` (MC-57)."""


class ErrorUnidades(ErrorFondo):
    """Las medianas de un mes caen fuera de los rangos de unidades de §4.1 (S13)."""


class ErrorAlineacion(ErrorFondo):
    """z_E5L no coincide píxel a píxel con el parquet derivado (§4.1, MC-38, S13)."""


def _errores_de_fondo(funcion):
    """FON-2: un ``ValueError`` o un ``TypeError`` de una función pública (propio o de numpy, pandas o ``tipos``) sale
    como ``ErrorFondo``, con el original como causa; nunca como un «no normalizable» (§2.1, MC-57)."""
    @functools.wraps(funcion)
    def envoltorio(*args, **kwargs):
        try:
            return funcion(*args, **kwargs)
        except (ValueError, TypeError) as error:
            raise ErrorFondo(f"{funcion.__name__}: {error}") from error
    return envoltorio


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def _netcdf4() -> ModuleType:
    """netCDF4 del entorno fijado, sólo al leer. Su aviso conocido de ABI con numpy 2 se silencia (como el reloj)."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="numpy.ndarray size changed", category=RuntimeWarning)
        import netCDF4
    return netCDF4


def _horas(h, *, nombre: str = "h", crecientes: bool = True) -> np.ndarray:
    """``h`` como int64; enteros y, si se pide, estrictamente crecientes."""
    a = np.asarray(h)
    if a.ndim != 1:
        raise ErrorFondo(f"{nombre}: se espera un arreglo de una dimensión")
    if a.dtype == bool or not np.issubdtype(a.dtype, np.integer):
        raise ErrorFondo(f"{nombre}: las horas son enteros (horas desde 2000-01-01T00Z)")
    a = a.astype(np.int64)
    if crecientes and a.size > 1 and not (np.diff(a) > 0).all():
        raise ErrorFondo(f"{nombre}: las horas deben ir estrictamente crecientes y sin repetir")
    return a


def _f8(x) -> np.ndarray:
    return np.asarray(x, dtype=np.float64)


def _f4(x) -> np.ndarray:
    """El float32 de x, de vuelta en float64 (FON-8)."""
    return np.asarray(x, dtype=np.float64).astype(np.float32).astype(np.float64)


def _mes_de(h: np.ndarray) -> np.ndarray:
    """datetime64[M] de cada hora UTC."""
    return (EPOCA_H + h).astype("datetime64[M]")


def _numero_de_mes(m: np.datetime64) -> int:
    """AAAAMM de un datetime64[M]."""
    return int(str(m).replace("-", ""))


def _en_periodo(m: np.datetime64, periodo) -> bool:
    desde, hasta = (int(a) for a in periodo)
    return np.datetime64(f"{desde:04d}-01", "M") <= m <= np.datetime64(f"{hasta:04d}-12", "M")


def _lon180(lon) -> np.ndarray:
    """Longitud en [−180, 180); los valores que ya están en ese rango no se tocan (sin perder decimales)."""
    lon = _f8(lon)
    dentro = (lon >= -_MEDIA_VUELTA) & (lon < _MEDIA_VUELTA)
    return np.where(dentro, lon, np.mod(lon + _MEDIA_VUELTA, _GRADOS_VUELTA) - _MEDIA_VUELTA)


def _sha_exigida(datos: bytes, sha256: str | None, nombre: str) -> str:
    sha = entorno.sha256_bytes(datos)
    if sha256 is not None and sha != sha256:
        raise ErrorFondo(f"{nombre}: la sha256 no es la esperada ({sha256[:8]}…)")   # no-umbral: abreviatura
    return sha


def _indice_ordenado(claves, buscadas) -> np.ndarray:
    """Posición de cada buscada en ``claves`` (únicas), −1 si no está."""
    claves = np.asarray(claves, dtype=np.int64)
    buscadas = np.asarray(buscadas, dtype=np.int64)
    salida = np.full(buscadas.shape, -1, dtype=np.int64)
    if claves.size == 0 or buscadas.size == 0:
        return salida
    orden = np.argsort(claves, kind="stable")
    ordenadas = claves[orden]
    pos = np.minimum(np.searchsorted(ordenadas, buscadas), len(ordenadas) - 1)
    ok = ordenadas[pos] == buscadas
    salida[ok] = orden[pos[ok]]
    return salida


# ---------------------------------------------------------------------------
# Lector mensual (FON-1, FON-2, FON-3)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, eq=False)
class MesE5L:
    """Un mes ERA5-Land leído: horas HH:00 (``tiempos`` = h, int32), ``pixel_id`` (int64), campos por nombre
    (float32 tiempo × píxel, unidades nativas: K, Pa, m/s y m) y sha256 del archivo."""
    tiempos: Any
    pixel_id: Any
    datos: dict
    sha256: str

    @property
    def yyyymm(self) -> int:
        return _numero_de_mes(_mes_de(np.asarray(self.tiempos[:1], dtype=np.int64))[0])

    @_errores_de_fondo
    def completo_hasta(self, h_ultima) -> bool:
        """Todas las horas del mes, de 1 h en 1 h, desde su primera hora hasta mín(su última hora, ``h_ultima``), y
        ninguna después (FON-1). ``h_ultima`` (int, h): la última hora con dato de los manifiestos de ERA5-Land; el
        último mes llega sólo hasta ella (§3, «a su último dato»). Un mes posterior a ``h_ultima`` no está completo."""
        if isinstance(h_ultima, (bool, np.bool_)) or not isinstance(h_ultima, (int, np.integer)):
            raise ErrorFondo("h_ultima: una hora entera (horas desde 2000-01-01T00Z)")
        h = np.asarray(self.tiempos, dtype=np.int64)
        m = _mes_de(h[:1])[0]
        inicio = int((m.astype("datetime64[h]") - EPOCA_H).astype(np.int64))
        siguiente = int(((m + 1).astype("datetime64[h]") - EPOCA_H).astype(np.int64))
        hasta = min(siguiente - 1, int(h_ultima))          # la última hora esperada del mes
        if hasta < inicio:
            return False
        return bool(h.size == hasta - inicio + 1 and h[0] == inicio and h[-1] == hasta and (np.diff(h) == 1).all())


def _segundos_unix(variable) -> np.ndarray:
    unidades = getattr(variable, "units", None)
    calendario = getattr(variable, "calendar", None)
    m = _UNIDADES_TIEMPO.fullmatch(unidades.strip()) if isinstance(unidades, str) else None
    if m is None or calendario not in _CALENDARIOS:
        raise ErrorFondo(f"eje de tiempo con unidades o calendario inesperados ({unidades!r}, {calendario!r})")
    crudos = variable[:]
    if np.ma.getmaskarray(crudos).any():
        raise ErrorFondo("eje de tiempo con valores enmascarados")
    valores = np.asarray(crudos)
    if valores.dtype.kind == "f":
        if not np.isfinite(valores).all() or (valores != np.round(valores)).any():
            raise ErrorFondo("eje de tiempo con valores no enteros")
        valores = valores.astype(np.int64)
    elif valores.dtype.kind not in "iu":
        raise ErrorFondo("eje de tiempo de un tipo inesperado")
    origen = np.datetime64(f"{m['fecha']}T{m['hora'] or '00:00'}", "s")
    base = int((origen - _UNIX_S).astype(np.int64))
    return base + valores.astype(np.int64) * _FACTOR_TIEMPO[m["unidad"]]


def _decodificar_mes(datos: bytes, sha: str, nombre: str) -> MesE5L:
    netCDF4 = _netcdf4()
    ds = netCDF4.Dataset(nombre, mode="r", memory=datos)
    try:
        return _mes_del_conjunto(ds, sha, nombre)
    finally:
        ds.close()


def _mes_del_conjunto(ds, sha: str, nombre: str) -> MesE5L:
    """El mes desde un conjunto abierto (``ds.variables``: dimensiones, atributos y valores), con las reglas de
    FON-1."""
    faltan = [v for v in ("time", "pixel_id", *VARIABLES_E5L) if v not in ds.variables]
    if faltan:
        raise ErrorFondo(f"{nombre}: faltan las variables {faltan}")
    segundos = _segundos_unix(ds.variables["time"])
    pid = np.asarray(np.ma.filled(ds.variables["pixel_id"][:], -1)).astype(np.int64)
    valores = {}
    for var in VARIABLES_E5L:
        v = ds.variables[var]
        if tuple(v.dimensions) != ("time", "pixel"):
            raise ErrorFondo(f"{nombre}: {var} no tiene dimensiones (time, pixel)")
        x = np.ma.filled(np.ma.asarray(v[:]).astype(np.float32), np.nan)
        if x.shape != (len(segundos), len(pid)):
            raise ErrorFondo(f"{nombre}: {var} con forma {x.shape}")
        x[~np.isfinite(x)] = np.nan
        valores[var] = x
    if len(np.unique(pid)) != len(pid) or (pid < 0).any():
        raise ErrorFondo(f"{nombre}: pixel_id repetido o inválido")
    if len(segundos) == 0:
        raise ErrorFondo(f"{nombre}: el mes no trae horas")
    desde_2000 = segundos - int((_EPOCA_S - _UNIX_S).astype(np.int64))
    if (desde_2000 % _SEGUNDOS_H != 0).any():
        raise ErrorFondo(f"{nombre}: hay horas que no son HH:00 (S12; el lector nativo las redondearía hacia abajo)")
    h = desde_2000 // _SEGUNDOS_H
    if h.size > 1 and not (np.diff(h) > 0).all():
        raise ErrorFondo(f"{nombre}: horas repetidas o desordenadas")
    if len(np.unique(_mes_de(h))) != 1:
        raise ErrorFondo(f"{nombre}: las horas no son de un solo mes UTC")
    if h.min() < np.iinfo(np.int32).min or h.max() > np.iinfo(np.int32).max:
        raise ErrorFondo(f"{nombre}: horas fuera de int32")
    return MesE5L(tiempos=h.astype(np.int32), pixel_id=pid, datos=valores, sha256=sha)


@_errores_de_fondo
def leer_mes(ruta, *, sha256: str | None = None) -> MesE5L:
    """Un archivo mensual ERA5-Land (FON-1). Rechaza horas que no son HH:00 (S12)."""
    datos = Path(ruta).read_bytes()
    return _decodificar_mes(datos, _sha_exigida(datos, sha256, Path(ruta).name), Path(ruta).name)


def _mediana(x: np.ndarray) -> float:
    finitos = x[np.isfinite(x)]
    return float(np.median(finitos.astype(np.float64))) if finitos.size else float("nan")


@_errores_de_fondo
def comprobar_unidades(mes: MesE5L, umbrales=None) -> None:
    """Unidades por rango (§4.1, FON-2); ``ErrorUnidades`` si no (S13)."""
    (t_min, t_max), (sp_min, sp_max) = _T_K, _SP_PA
    malas = []
    for var in ("t2m", "d2m"):
        med = _mediana(mes.datos[var])
        if not t_min <= med <= t_max:
            malas.append(var)
    if not sp_min <= _mediana(mes.datos["sp"]) <= sp_max:
        malas.append("sp")
    for var in ("u10", "v10"):
        if not abs(_mediana(mes.datos[var])) < _UV_MS:
            malas.append(var)
    if malas:
        raise ErrorUnidades(f"mes {mes.yyyymm}: unidades fuera de los rangos de §4.1 en {malas}")


@_errores_de_fondo
def pixeles_validos(meses_referencia: Mapping) -> np.ndarray:
    """t2m y sp con algún valor finito en cada uno de los meses 200001, 201307 y 202507 (§4.1, FON-3)."""
    claves: dict[int, MesE5L] = {}
    for k, mes in meses_referencia.items():
        if isinstance(k, bool):
            raise ErrorFondo("las claves son meses AAAAMM")
        kk = int(k)
        if kk in claves:
            raise ErrorFondo(f"mes repetido: {kk}")
        claves[kk] = mes
    if sorted(claves) != sorted(_MESES_VALIDEZ):
        raise ErrorFondo(f"se esperan exactamente los meses {_MESES_VALIDEZ}, no {sorted(claves)}")
    validos: set[int] | None = None
    for ym in _MESES_VALIDEZ:
        mes = claves[ym]
        if mes.yyyymm != ym:
            raise ErrorFondo(f"el mes de la clave {ym} trae horas de {mes.yyyymm}")
        ok = np.isfinite(mes.datos["t2m"]).any(axis=0) & np.isfinite(mes.datos["sp"]).any(axis=0)
        del_mes = {int(p) for p in np.asarray(mes.pixel_id)[ok]}
        validos = del_mes if validos is None else validos & del_mes
    return np.array(sorted(validos or ()), dtype=np.int64)


# ---------------------------------------------------------------------------
# Catálogo de píxeles y altitud (FON-4, FON-5)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, eq=False)
class _Catalogo:
    pixel_id: np.ndarray      # int64, en orden creciente
    i: np.ndarray
    j: np.ndarray
    lat: np.ndarray
    lon: np.ndarray
    clave_ordenada: np.ndarray      # i·3.600 + j, ordenadas
    pid_de_clave: np.ndarray        # pixel_id de cada clave ordenada


def _catalogo(catalogo) -> _Catalogo:
    faltan = [c for c in ("pixel_id", "latitude", "longitude", "lat_index_global", "lon_index_global")
              if c not in catalogo.columns]
    if faltan:
        raise ErrorFondo(f"al catálogo de píxeles le faltan {faltan}")
    cat = catalogo.sort_values("pixel_id", kind="mergesort")
    pid = cat["pixel_id"].to_numpy(np.int64)
    if len(np.unique(pid)) != len(pid):
        raise ErrorFondo("pixel_id repetido en el catálogo")
    i = cat["lat_index_global"].to_numpy(np.int64)
    j = cat["lon_index_global"].to_numpy(np.int64)
    lat = cat["latitude"].to_numpy(np.float64)
    lon = _lon180(cat["longitude"].to_numpy(np.float64))
    d_lat = np.abs(_LAT_POLO - i / _CELDAS_POR_GRADO - lat)
    d_lon = np.abs(_lon180(j / _CELDAS_POR_GRADO - lon))
    if (d_lat > _TOL_GRILLA_GRADOS).any() or (d_lon > _TOL_GRILLA_GRADOS).any():
        raise ErrorFondo("el catálogo no sigue la grilla global de 0,1° (índices y coordenadas no calzan)")
    clave = i * _COLUMNAS_GLOBALES + np.mod(j, _COLUMNAS_GLOBALES)
    if len(np.unique(clave)) != len(clave):
        raise ErrorFondo("índices de malla repetidos en el catálogo")
    orden = np.argsort(clave, kind="stable")
    return _Catalogo(pid, i, j, lat, lon, clave[orden], pid[orden])


def _pid_de(cat: _Catalogo, i: np.ndarray, j: np.ndarray) -> np.ndarray:
    clave = i * _COLUMNAS_GLOBALES + np.mod(j, _COLUMNAS_GLOBALES)
    pos = np.searchsorted(cat.clave_ordenada, clave)
    pos_c = np.clip(pos, 0, len(cat.clave_ordenada) - 1)
    ok = (pos < len(cat.clave_ordenada)) & (cat.clave_ordenada[pos_c] == clave)
    return np.where(ok, cat.pid_de_clave[pos_c], -1)


@dataclass(frozen=True, eq=False)
class Geopotencial:
    """El geopotencial invariante (m² s⁻²) en su rejilla: ``lat`` y ``lon`` (−180..180) en grados, ``z`` lat × lon."""
    lat: Any
    lon: Any
    z: Any
    sha256: str


@_errores_de_fondo
def leer_geopotencial(ruta, *, sha256: str | None = None) -> Geopotencial:
    """El NetCDF crudo del geopotencial (bec3c995… en la corrida real): ``z`` con dimensiones (…, latitude,
    longitude) o (…, longitude, latitude), las demás de largo 1, en m² s⁻²; NaN donde enmascara."""
    nombre = Path(ruta).name
    datos = Path(ruta).read_bytes()
    sha = _sha_exigida(datos, sha256, nombre)
    netCDF4 = _netcdf4()
    ds = netCDF4.Dataset(nombre, mode="r", memory=datos)
    try:
        lat, lon, z = _geopotencial_del_conjunto(ds, nombre)
    finally:
        ds.close()
    return Geopotencial(lat=lat, lon=lon, z=z, sha256=sha)


def _coordenada_geopotencial(crudo, etiqueta: str) -> np.ndarray:
    """Decodifica sólo los centros exactos en la precisión float32 original, como el productor del derivado."""
    valores = np.ma.asarray(crudo)
    if valores.ndim != 1 or not valores.size or np.ma.getmaskarray(valores).any():
        raise ErrorFondo(f"el geopotencial tiene un eje inválido o enmascarado ({etiqueta})")
    eje = np.asarray(valores, dtype=np.float64)
    if not np.isfinite(eje).all():
        raise ErrorFondo(f"el geopotencial tiene coordenadas no finitas ({etiqueta})")
    if valores.dtype.newbyteorder("=") == np.dtype(np.float32):
        centros = np.rint(eje * _CELDAS_POR_GRADO) / _CELDAS_POR_GRADO
        if not np.array_equal(centros.astype(valores.dtype), valores):
            raise ErrorFondo(f"el geopotencial no representa centros exactos de 0,1° en float32 ({etiqueta})")
        return centros
    return eje


def _geopotencial_del_conjunto(ds, nombre: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(lat, lon en −180..180, z lat × lon en float64) desde un conjunto abierto (``ds.variables``)."""
    if "z" not in ds.variables:
        raise ErrorFondo(f"{nombre}: no trae la variable z")
    nombres_lat = [n for n in ("latitude", "lat") if n in ds.variables]
    nombres_lon = [n for n in ("longitude", "lon") if n in ds.variables]
    if not nombres_lat or not nombres_lon:
        raise ErrorFondo(f"{nombre}: faltan las coordenadas de latitud o longitud")
    n_lat, n_lon = nombres_lat[0], nombres_lon[0]
    var = ds.variables["z"]
    unidades = str(getattr(var, "units", "")).strip()
    if unidades not in UNIDADES_GEOPOTENCIAL:
        raise ErrorFondo(f"{nombre}: unidades del geopotencial inesperadas: {unidades!r}")
    dims = tuple(var.dimensions)
    if n_lat not in dims or n_lon not in dims:
        raise ErrorFondo(f"{nombre}: z no tiene las dimensiones de latitud y longitud")
    z = np.ma.filled(np.ma.asarray(var[:]).astype(np.float32), np.nan).astype(np.float64)
    extras = [k for k, d in enumerate(dims) if d not in (n_lat, n_lon)]
    if any(z.shape[k] != 1 for k in extras):
        raise ErrorFondo(f"{nombre}: z tiene más de un paso en una dimensión extra")
    z = z.reshape([s for k, s in enumerate(z.shape) if k not in extras])
    if [d for d in dims if d in (n_lat, n_lon)] == [n_lon, n_lat]:
        z = z.T
    lat = _coordenada_geopotencial(ds.variables[n_lat][:], "latitud")
    lon = _lon180(_coordenada_geopotencial(ds.variables[n_lon][:], "longitud"))
    if z.shape != (len(lat), len(lon)):
        raise ErrorFondo(f"{nombre}: z con forma {z.shape}; se espera (latitud, longitud) = {(len(lat), len(lon))}")
    z[~np.isfinite(z)] = np.nan
    return lat, lon, z


def _ejes_de_grilla(indices: np.ndarray, desvio: np.ndarray, etiqueta: str) -> None:
    if not np.isfinite(desvio).all() or (np.abs(desvio) > _TOL_GRILLA_GRADOS).any():
        raise ErrorFondo(f"el geopotencial no está en los centros de 0,1° ({etiqueta})")
    if len(np.unique(indices)) != len(indices):
        raise ErrorFondo(f"el geopotencial repite centros de {etiqueta}")


def _z_geopotencial(geo: Geopotencial, cat: _Catalogo) -> np.ndarray:
    lat, lon = _f8(geo.lat), _f8(geo.lon)
    i_geo = np.rint((_LAT_POLO - lat) * _CELDAS_POR_GRADO).astype(np.int64)
    j_geo = np.mod(np.rint(np.mod(lon, _GRADOS_VUELTA) * _CELDAS_POR_GRADO).astype(np.int64), _COLUMNAS_GLOBALES)
    _ejes_de_grilla(i_geo, _LAT_POLO - i_geo / _CELDAS_POR_GRADO - lat, "latitud")
    _ejes_de_grilla(j_geo, _lon180(j_geo / _CELDAS_POR_GRADO - lon), "longitud")
    fila = _indice_ordenado(i_geo, cat.i)
    columna = _indice_ordenado(j_geo, np.mod(cat.j, _COLUMNAS_GLOBALES))
    z = np.full(len(cat.pixel_id), np.nan)
    ok = (fila >= 0) & (columna >= 0)
    z[ok] = _f8(geo.z)[fila[ok], columna[ok]] / _G
    return z


def _por_pixel(tabla, columnas: Sequence[str], pid: np.ndarray) -> list[np.ndarray]:
    """Columnas de una tabla con ``pixel_id`` alineadas a ``pid`` (NaN donde falta)."""
    if "pixel_id" not in tabla.columns or any(c not in tabla.columns for c in columnas):
        raise ErrorFondo(f"la tabla por píxel debe traer pixel_id y {list(columnas)}")
    ids = tabla["pixel_id"].to_numpy(np.int64)
    if len(np.unique(ids)) != len(ids):
        raise ErrorFondo("pixel_id repetido en una tabla por píxel")
    pos = _indice_ordenado(ids, pid)
    salida = []
    for c in columnas:
        x = np.full(len(pid), np.nan)
        x[pos >= 0] = tabla[c].to_numpy(np.float64)[pos[pos >= 0]]
        salida.append(x)
    return salida


def _serie_por_pixel(serie, pid: np.ndarray) -> np.ndarray:
    if isinstance(serie, pd.Series):
        tabla = pd.DataFrame({"pixel_id": serie.index.to_numpy(np.int64), "v": serie.to_numpy(np.float64)})
    elif isinstance(serie, Mapping):
        tabla = pd.DataFrame({"pixel_id": np.array(list(serie), dtype=np.int64),
                              "v": np.array(list(serie.values()), dtype=np.float64)})
    else:
        raise ErrorFondo("sp_medio: una serie (o un mapeo) pixel_id → sp̄ en hPa")
    return _por_pixel(tabla, ("v",), pid)[0]


@_errores_de_fondo
def z_e5l(geopotencial: Geopotencial, catalogo, nasadem, sp_medio, umbrales, *, validos) -> pd.DataFrame:
    """Altitud de cada píxel del catálogo (§4.1, FON-4), en ``ESQUEMA_ZE5L``, en orden de ``pixel_id``.

    ``nasadem``: ``estaticas_nasadem.nasadem_en_pixeles`` (``pixel_id``, ``z_nasadem``, ``frac_nasadem``; A9).
    ``sp_medio``: sp̄ 2000-2025 en hPa por píxel (``sp_medio_hpa``). ``validos``: ``pixeles_validos``."""
    cat = _catalogo(catalogo)
    pid = cat.pixel_id
    z_geo = _z_geopotencial(geopotencial, cat)
    z_nas, frac = _por_pixel(nasadem, ("z_nasadem", "frac_nasadem"), pid)
    frac = np.where(np.isfinite(frac), frac, 0.0)
    sp = _serie_por_pixel(sp_medio, pid)
    with np.errstate(invalid="ignore"):
        z_hip = numerico.z_hipsometrica(sp)
    z_hip = np.where(np.isfinite(z_hip), z_hip, np.nan)
    caso = np.full(len(pid), None, dtype=object)
    z = np.full(len(pid), np.nan)
    geo = np.isfinite(z_geo)
    z[geo], caso[geo] = z_geo[geo], tipos.CasoZE5L.GEOPOTENCIAL.value
    nas = ~geo & np.isfinite(z_nas) & (frac >= umbrales.frac("ZE5L_NASADEM_PCT"))
    z[nas], caso[nas] = z_nas[nas], tipos.CasoZE5L.NASADEM.value
    hip = ~geo & ~nas & np.isfinite(z_hip)
    z[hip], caso[hip] = z_hip[hip], tipos.CasoZE5L.HIPSOMETRICA.value
    validos = np.unique(np.asarray(validos, dtype=np.int64))
    if not np.isin(validos, pid).all():
        raise ErrorFondo("hay píxeles válidos que no están en el catálogo")
    valido = np.isin(pid, validos)
    sin_z = valido & ~np.isfinite(z)
    if sin_z.any():
        raise ErrorFondo(f"{int(sin_z.sum())} píxeles válidos sin z_E5L en ninguno de los tres casos")
    ambos = np.isfinite(z_nas) & np.isfinite(z_hip)
    dif = np.zeros(len(pid), dtype=bool)
    dif[ambos] = np.abs(z_nas[ambos] - z_hip[ambos]) > _DIF_AVISO_M
    tabla = pd.DataFrame({"pixel_id": pid, "valido": valido, "z_e5l": z, "caso": pd.array(caso, dtype="string"),
                          "z_nasadem": z_nas, "frac_nasadem": frac, "z_hipso": z_hip, "dif_mayor_50m": dif})
    tabla = tabla.astype(dict(tipos.ESQUEMA_ZE5L))
    tipos.validar_esquema(tabla, tipos.ESQUEMA_ZE5L, nombre="z_e5l")
    tabla.attrs["esquema"] = tipos.ESQUEMA_ZE5L.version
    return tabla


@_errores_de_fondo
def comprobar_alineacion(z, parquet_altitud) -> None:
    """z_E5L del NetCDF crudo frente a ``era5land_altitud_modelo_pixeles.parquet`` (MC-38, FON-5); si difiere,
    ``ErrorAlineacion`` y M2a se detiene (S13)."""
    for tabla, columna, nombre in ((z, "z_e5l", "z_E5L"), (parquet_altitud, "z_m", "parquet de altitud")):
        if "pixel_id" not in tabla.columns or columna not in tabla.columns:
            raise ErrorAlineacion(f"{nombre}: faltan pixel_id o {columna}")
        if tabla["pixel_id"].duplicated().any():
            raise ErrorAlineacion(f"{nombre}: pixel_id repetido")
    a = z.set_index("pixel_id")["z_e5l"].astype(np.float64).sort_index()
    b = parquet_altitud.set_index("pixel_id")["z_m"].astype(np.float64).sort_index()
    if not np.array_equal(a.index.to_numpy(np.int64), b.index.to_numpy(np.int64)):
        raise ErrorAlineacion("z_E5L y el parquet de altitud no tienen los mismos pixel_id")
    va, vb = a.to_numpy(), b.to_numpy()
    iguales = np.isfinite(va) & np.isfinite(vb) & (np.abs(va - vb) <= TOL_ALINEACION_M)
    if not iguales.all():
        raise ErrorAlineacion(f"z_E5L no coincide con el parquet de altitud en {int((~iguales).sum())} píxeles "
                              f"de {len(iguales)} (MC-38)")


# ---------------------------------------------------------------------------
# Operador (FON-6)
# ---------------------------------------------------------------------------
def _z_por_pixel(z_pix) -> tuple[np.ndarray, np.ndarray]:
    if isinstance(z_pix, pd.DataFrame):
        if "pixel_id" not in z_pix.columns or "z_e5l" not in z_pix.columns:
            raise ErrorFondo("z_pix debe traer pixel_id y z_e5l (ESQUEMA_ZE5L)")
        ids, z = z_pix["pixel_id"].to_numpy(np.int64), z_pix["z_e5l"].to_numpy(np.float64)
    elif isinstance(z_pix, pd.Series):
        ids, z = z_pix.index.to_numpy(np.int64), z_pix.to_numpy(np.float64)
    elif isinstance(z_pix, Mapping):
        ids, z = np.array(list(z_pix), dtype=np.int64), np.array(list(z_pix.values()), dtype=np.float64)
    else:
        raise ErrorFondo("z_pix: la tabla de z_e5l, una serie o un mapeo pixel_id → z_E5L (m)")
    if len(np.unique(ids)) != len(ids):
        raise ErrorFondo("pixel_id repetido en z_pix")
    return ids, z


def _z_de(ids_z: np.ndarray, z: np.ndarray, pix: np.ndarray) -> np.ndarray:
    pos = _indice_ordenado(ids_z, pix)
    salida = np.full(pix.shape, np.nan)
    salida[pos >= 0] = z[pos[pos >= 0]]
    return salida


def _unitarios(lat, lon) -> np.ndarray:
    la, lo = np.radians(_f8(lat)), np.radians(_f8(lon))
    return np.column_stack((np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)))


def _respaldo(lat: np.ndarray, lon: np.ndarray, pid_v: np.ndarray, lat_v: np.ndarray, lon_v: np.ndarray,
              radio_km: float) -> np.ndarray:
    """El centro válido más cercano a ≤ radio (haversine; empate, menor pixel_id), o −1 (FON-6, MC-60)."""
    from scipy.spatial import cKDTree

    salida = np.full(len(lat), -1, dtype=np.int64)
    if len(lat) == 0 or len(pid_v) == 0:
        return salida
    arbol = cKDTree(_unitarios(lat_v, lon_v))
    cuerda = 2 * np.sin(radio_km / (2 * _R_TIERRA_KM)) * (1 + _HOLGURA_ARBOL)
    candidatos = arbol.query_ball_point(_unitarios(lat, lon), r=cuerda)
    for k, lista in enumerate(candidatos):
        if not lista:
            continue
        c = np.asarray(lista, dtype=np.int64)
        d = numerico.haversine_km(lat[k], lon[k], lat_v[c], lon_v[c])
        cerca = d <= radio_km
        if not cerca.any():
            continue
        c, d = c[cerca], d[cerca]
        orden = np.lexsort((pid_v[c], d))
        salida[k] = pid_v[c[orden[0]]]
    return salida


@_errores_de_fondo
def operador(lat, lon, z, catalogo, validos, z_pix, umbrales, *, ids=None) -> tipos.OperadorPuntos:
    """``tipos.OperadorPuntos``: bilineal en índices de malla con vecino a ≤ ``VECINO_KM`` (§4.1, FON-6).

    ``z`` en m (z_s en estaciones; ``z_media`` o ``z_poblada`` en celdas; z_E5L en píxeles; A10). ``ids``: los
    identificadores de los puntos (códigos, celdas o píxeles); por omisión, 0…n−1."""
    lat, lon, z = _f8(lat).ravel(), _f8(lon).ravel(), _f8(z).ravel()
    n = len(lat)
    if len(lon) != n or len(z) != n:
        raise ErrorFondo("operador: lat, lon y z con el mismo largo")
    ids = np.arange(n) if ids is None else np.asarray(ids)
    if len(ids) != n:
        raise ErrorFondo("operador: un id por punto")
    cat = _catalogo(catalogo)
    validos = np.unique(np.asarray(validos, dtype=np.int64))
    if not np.isin(validos, cat.pixel_id).all():
        raise ErrorFondo("hay píxeles válidos que no están en el catálogo")
    ids_z, z_tabla = _z_por_pixel(z_pix)
    z_validos = _z_de(ids_z, z_tabla, validos)
    if not np.isfinite(z_validos).all():
        raise ErrorFondo(f"{int((~np.isfinite(z_validos)).sum())} píxeles válidos sin z_E5L finita")
    radio = float(umbrales.a("VECINO_KM"))

    finitos = np.isfinite(lat) & np.isfinite(lon)
    with np.errstate(invalid="ignore"):
        fi = np.where(finitos, (_LAT_POLO - lat) * _CELDAS_POR_GRADO, 0.0)
        fj = np.where(finitos, np.mod(lon, _GRADOS_VUELTA) * _CELDAS_POR_GRADO, 0.0)
    fi = np.where(np.abs(fi - np.rint(fi)) < _TOL_INDICE, np.rint(fi), fi)
    fj = np.where(np.abs(fj - np.rint(fj)) < _TOL_INDICE, np.rint(fj), fj)
    i0, j0 = np.floor(fi).astype(np.int64), np.floor(fj).astype(np.int64)
    di, dj = fi - i0, fj - j0
    esquinas = ((0, 0, (1 - di) * (1 - dj)), (0, 1, (1 - di) * dj), (1, 0, di * (1 - dj)), (1, 1, di * dj))
    pix = np.full((n, _N_VECINOS), -1, dtype=np.int64)
    w = np.zeros((n, _N_VECINOS))
    for k, (a, b, peso) in enumerate(esquinas):
        p = _pid_de(cat, i0 + a, j0 + b)
        usable = finitos & (p >= 0) & np.isin(p, validos) & (peso > 0)
        pix[usable, k] = p[usable]
        w[usable, k] = peso[usable]
    suma = np.zeros(n)
    for k in range(_N_VECINOS):
        suma = suma + w[:, k]
    con_vecinos = suma > 0
    w[con_vecinos] = w[con_vecinos] / suma[con_vecinos, None]

    respaldo = np.zeros(n, dtype=bool)
    faltan = np.flatnonzero(finitos & ~con_vecinos)
    if faltan.size:
        pos = _indice_ordenado(cat.pixel_id, validos)
        cercano = _respaldo(lat[faltan], lon[faltan], validos, cat.lat[pos], cat.lon[pos], radio)
        hay = cercano >= 0
        filas = faltan[hay]
        pix[filas, 0], w[filas, 0], respaldo[filas] = cercano[hay], 1.0, True

    dz = np.full((n, _N_VECINOS), np.nan)
    con = pix >= 0
    dz[con] = np.broadcast_to(z[:, None], pix.shape)[con] - _z_de(validos, z_validos, pix[con])
    return tipos.OperadorPuntos(ids=ids, z=z, pix=pix.astype(np.int32), w=w, dz=dz, respaldo=respaldo)


@_errores_de_fondo
def operador_pixeles(pixel_ids, catalogo, validos, z_pix) -> tipos.OperadorPuntos:
    """El operador en los centros de los píxeles válidos (A10, FON-6): cada píxel es su único vecino, con peso 1,
    z = z_E5L y dz = 0, por ``pixel_id`` (no por las coordenadas del catálogo). Allí el fondo es ERA5-Land tal cual
    (§3). ``ids`` son los ``pixel_id``. Un píxel no válido, fuera del catálogo o sin z_E5L finita es un
    ``ErrorFondo``."""
    pid = np.asarray(pixel_ids)
    if pid.ndim != 1 or pid.dtype == bool or not np.issubdtype(pid.dtype, np.integer):
        raise ErrorFondo("operador_pixeles: los pixel_id son enteros, en un arreglo de una dimensión")
    pid = pid.astype(np.int64)
    cat = _catalogo(catalogo)
    validos = np.unique(np.asarray(validos, dtype=np.int64))
    if not np.isin(validos, cat.pixel_id).all():
        raise ErrorFondo("hay píxeles válidos que no están en el catálogo")
    if not np.isin(pid, validos).all():
        raise ErrorFondo(f"operador_pixeles: {int((~np.isin(pid, validos)).sum())} píxeles no son válidos o no están "
                         "en el catálogo (§3: el producto de 0,1° va en los píxeles válidos)")
    ids_z, z_tabla = _z_por_pixel(z_pix)
    z = _z_de(ids_z, z_tabla, pid)
    if not np.isfinite(z).all():
        raise ErrorFondo(f"operador_pixeles: {int((~np.isfinite(z)).sum())} píxeles sin z_E5L finita")
    n = len(pid)
    pix = np.full((n, _N_VECINOS), -1, dtype=np.int64)
    w = np.zeros((n, _N_VECINOS))
    dz = np.full((n, _N_VECINOS), np.nan)
    pix[:, 0], w[:, 0], dz[:, 0] = pid, 1.0, 0.0
    return tipos.OperadorPuntos(ids=pid, z=z, pix=pix.astype(np.int32), w=w, dz=dz, respaldo=np.zeros(n, dtype=bool))


@_errores_de_fondo
def columnas_operador(op: tipos.OperadorPuntos) -> pd.DataFrame:
    """Las columnas del operador en ``ESQUEMA_ESTACIONES_MC`` (``pix0``…``pix3``, ``w0``…``w3``, ``respaldo_16km`` y
    ``sin_fondo``), una fila por punto, con ``id`` primero (A8)."""
    pix, w = np.asarray(op.pix), np.asarray(op.w, dtype=np.float64)
    datos: dict[str, Any] = {"id": np.asarray(op.ids)}
    for k in range(_N_VECINOS):
        datos[f"pix{k}"] = pix[:, k].astype(np.int32)
    for k in range(_N_VECINOS):
        datos[f"w{k}"] = w[:, k]
    datos["respaldo_16km"] = np.asarray(op.respaldo, dtype=bool)
    datos["sin_fondo"] = (pix < 0).all(axis=1)
    return pd.DataFrame(datos)


@_errores_de_fondo
def operador_desde_columnas(ids, z, tabla, z_pix) -> tipos.OperadorPuntos:
    """El operador desde las columnas guardadas (``columnas_operador`` o ``estaticas/estaciones.parquet``) y la z de
    los puntos; dz se rehace con z_E5L. Así M3-4 usa el mismo operador que M2a."""
    z = _f8(z).ravel()
    pix = np.column_stack([tabla[f"pix{k}"].to_numpy(np.int64) for k in range(_N_VECINOS)])
    w = np.column_stack([tabla[f"w{k}"].to_numpy(np.float64) for k in range(_N_VECINOS)])
    if pix.shape[0] != len(z):
        raise ErrorFondo("operador_desde_columnas: una fila por punto")
    w = np.where(pix >= 0, np.nan_to_num(w, nan=0.0), 0.0)
    ids_z, z_tabla = _z_por_pixel(z_pix)
    dz = np.full(pix.shape, np.nan)
    con = pix >= 0
    z_i = _z_de(ids_z, z_tabla, pix[con])
    if not np.isfinite(z_i).all():
        raise ErrorFondo("un vecino del operador no tiene z_E5L finita")
    dz[con] = np.broadcast_to(z[:, None], pix.shape)[con] - z_i
    return tipos.OperadorPuntos(ids=np.asarray(ids), z=z, pix=pix.astype(np.int32), w=w, dz=dz,
                                respaldo=tabla["respaldo_16km"].to_numpy(bool))


# ---------------------------------------------------------------------------
# Campos del fondo (FON-7)
# ---------------------------------------------------------------------------
def _columnas_del_mes(mes: MesE5L, pix: np.ndarray) -> np.ndarray:
    col = np.full(pix.shape, -1, dtype=np.int64)
    con = pix >= 0
    pos = _indice_ordenado(np.asarray(mes.pixel_id, dtype=np.int64), pix[con].astype(np.int64))
    if (pos < 0).any():
        raise ErrorFondo(f"mes {mes.yyyymm}: le faltan píxeles del operador")
    col[con] = pos
    return col


@_errores_de_fondo
def campos_fondo(mes: MesE5L, op: tipos.OperadorPuntos, umbrales, *, recortar_td: bool = True) -> dict:
    """T_F (°C), Td_F (°C), p_F (hPa), u_F y v_F (m/s, «hacia») en float64, tiempo × punto (§4.1, FON-7), y
    ``renormalizada`` (bool): los punto-hora en que algún campo perdió un vecino con dato (MC-39)."""
    gamma = float(umbrales.a("GAMMA_K_KM"))
    pix, w, dz = np.asarray(op.pix), np.asarray(op.w, dtype=np.float64), np.asarray(op.dz, dtype=np.float64)
    n, nt = pix.shape[0], len(mes.tiempos)
    col = _columnas_del_mes(mes, pix)
    suma = {c: np.zeros((nt, n)) for c in CAMPOS_F}
    peso = {c: np.zeros((nt, n)) for c in CAMPOS_F}
    estatico = np.zeros(n)
    for k in range(_N_VECINOS):
        filas = np.flatnonzero(col[:, k] >= 0)
        if filas.size == 0:
            continue
        estatico[filas] = estatico[filas] + w[filas, k]
        c = col[filas, k]
        wk, dzk = w[filas, k][None, :], dz[filas, k][None, :]
        t2m, d2m = _f8(mes.datos["t2m"][:, c]), _f8(mes.datos["d2m"][:, c])
        sp = _f8(mes.datos["sp"][:, c]) / _PA_POR_HPA
        u10, v10 = _f8(mes.datos["u10"][:, c]), _f8(mes.datos["v10"][:, c])
        with np.errstate(invalid="ignore", divide="ignore", over="ignore"):
            t_i = t2m - _KELVIN
            t_x = t_i + gamma * dzk / _M_POR_KM
            t_media = (t_i + t_x) / 2 + _KELVIN
            p_x = numerico.presion_a_altitud(sp, t_media, dzk)
            td_i = d2m - _KELVIN
            e_i = numerico.magnus_agua(td_i)
            q_i = _EPS_Q * e_i / (sp - _COMP_Q * e_i)
            e_x = q_i * p_x / (_EPS_Q + _COMP_Q * q_i)
            td_x = numerico.td_desde_e(e_x)
            identidad = (dzk == 0) & np.isfinite(p_x) & np.isfinite(td_i)
            td_x = np.where(identidad, td_i, td_x)
        for nombre, valor in (("T_F", t_x), ("Td_F", td_x), ("p_F", p_x), ("u_F", u10), ("v_F", v10)):
            ok = np.isfinite(valor)
            suma[nombre][:, filas] += np.where(ok, wk * valor, 0.0)
            peso[nombre][:, filas] += np.where(ok, wk, 0.0)
    salida: dict[str, np.ndarray] = {}
    renormalizada = np.zeros((nt, n), dtype=bool)
    for nombre in CAMPOS_F:
        con_dato = peso[nombre] > 0
        with np.errstate(invalid="ignore", divide="ignore"):
            salida[nombre] = np.where(con_dato, suma[nombre] / np.where(con_dato, peso[nombre], 1.0), np.nan)
        renormalizada |= con_dato & (peso[nombre] < estatico[None, :])
    if recortar_td:
        salida["Td_F"] = np.minimum(salida["Td_F"], salida["T_F"])
    salida["renormalizada"] = renormalizada
    return salida


@_errores_de_fondo
def producto_desde(F: Mapping, R: Mapping) -> dict:
    """T = T_F + R_T; Td = mín(Td_F + R_Td, T); u = u_F + R_u; v = v_F + R_v; p = p_F·exp(R_p) (§4.1). Sin
    redondeos (FON-8). R es la corrección del candidato: nunca se guarda ni se informa (§0.4.3)."""
    faltan = [c for c in CAMPOS_F if c not in F] + [c for c in CLAVES_R if c not in R]
    if faltan:
        raise ErrorFondo(f"producto_desde: faltan {faltan}")
    f = {c: _f8(F[c]) for c in CAMPOS_F}
    r = {c: _f8(R[c]) for c in CLAVES_R}
    formas = {x.shape for x in (*f.values(), *r.values())}
    if len(formas) != 1:
        raise ErrorFondo(f"producto_desde: formas distintas {sorted(formas)}")
    T = f["T_F"] + r["R_T"]
    return {"T": T, "Td": np.minimum(f["Td_F"] + r["R_Td"], T), "u": f["u_F"] + r["R_u"], "v": f["v_F"] + r["R_v"],
            "p": f["p_F"] * np.exp(r["R_p"])}


@_errores_de_fondo
def residuos(obs: Mapping, F: Mapping) -> dict:
    """r_T, r_Td, r_u, r_v = obs − F y r_p = ln(QFE/p_F), en float64, NaN donde falta la observación o el fondo (A3).

    ``obs``: «T» (Ts, °C), «Td» (``td_final``), «u» y «v» (``u_final`` y ``v_final``, m/s) y «QFE» (hPa), alineados
    con ``F`` (las columnas de A1). No mira la validez: quien llama pone NaN donde la hora no es válida. Redondea los
    dos a float32 antes de restar (FON-8). Es la única fuente de r_p; la diferencia QFE − p_F en hPa no es r_p."""
    claves = set(obs)
    if claves != set(CLAVES_OBS):
        raise ErrorFondo(f"residuos: obs trae {sorted(claves)}; se esperan {list(CLAVES_OBS)}")
    faltan = [c for c in ("T_F", "Td_F", "u_F", "v_F", "p_F") if c not in F]
    if faltan:
        raise ErrorFondo(f"residuos: al fondo le faltan {faltan}")
    o = {c: _f4(obs[c]) for c in CLAVES_OBS}
    f = {c: _f4(F[c]) for c in ("T_F", "Td_F", "u_F", "v_F", "p_F")}
    formas = {x.shape for x in (*o.values(), *f.values())}
    if len(formas) != 1:
        raise ErrorFondo(f"residuos: obs y fondo con formas distintas {sorted(formas)}")
    with np.errstate(invalid="ignore", divide="ignore"):
        r_p = np.where((o["QFE"] > 0) & (f["p_F"] > 0), np.log(o["QFE"] / f["p_F"]), np.nan)
    return {"r_T": o["T"] - f["T_F"], "r_Td": o["Td"] - f["Td_F"], "r_u": o["u"] - f["u_F"],
            "r_v": o["v"] - f["v_F"], "r_p": r_p}


# ---------------------------------------------------------------------------
# Fondo en las estaciones (FON-9, FON-10; A1, A2)
# ---------------------------------------------------------------------------
@_errores_de_fondo
def amplitud_dia_utc(T, h) -> np.ndarray:
    """Máximo menos mínimo de T en su día UTC, en cada hora (FON-10); NaN en días incompletos o con NaN."""
    T = _f8(T)
    h = _horas(h)
    if T.shape[:1] != h.shape:
        raise ErrorFondo("amplitud_dia_utc: una fila de T por hora")
    if h.size == 0:
        return np.empty_like(T)
    dia = np.floor_divide(h, _HORAS_DIA)
    inicio = np.flatnonzero(np.r_[True, dia[1:] != dia[:-1]])
    largo = np.diff(np.r_[inicio, h.size])
    amp = np.maximum.reduceat(T, inicio, axis=0) - np.minimum.reduceat(T, inicio, axis=0)
    amp[largo != _HORAS_DIA] = np.nan
    return np.repeat(amp, largo, axis=0)


@_errores_de_fondo
def tabla_puntos(h, F: Mapping) -> pd.DataFrame:
    """El fondo en una estación (``ESQUEMA_PUNTOS_E5L``; A1, FON-9): ``h`` estrictamente creciente, los cinco campos
    (1-D) y ``amp_TF``, en float32."""
    h = _horas(h)
    if h.size and (h.min() < np.iinfo(np.int32).min or h.max() > np.iinfo(np.int32).max):
        raise ErrorFondo("tabla_puntos: horas fuera de int32")
    faltan = [c for c in CAMPOS_F if c not in F]
    if faltan:
        raise ErrorFondo(f"tabla_puntos: faltan {faltan}")
    campos = {c: _f8(F[c]) for c in CAMPOS_F}
    if any(x.shape != h.shape for x in campos.values()):
        raise ErrorFondo("tabla_puntos: cada campo es una serie (1-D) con un valor por hora")
    datos = {"h": h.astype(np.int32), **{c: campos[c].astype(np.float32) for c in CAMPOS_F},
             "amp_TF": amplitud_dia_utc(campos["T_F"], h).astype(np.float32)}
    tabla = pd.DataFrame(datos, columns=list(COLUMNAS_PUNTOS))
    tipos.validar_esquema(tabla, tipos.ESQUEMA_PUNTOS_E5L, nombre="tabla_puntos")
    tabla.attrs["esquema"] = tipos.ESQUEMA_PUNTOS_E5L.version
    return tabla


@_errores_de_fondo
def en_horas(F_estacion: pd.DataFrame, h) -> dict:
    """Las columnas del fondo de una estación en las horas ``h`` (int), en float64, NaN donde la tabla no tiene esa
    hora (A2). Es la única forma de alinear la tabla ancha con el fondo."""
    tipos.validar_esquema(F_estacion, tipos.ESQUEMA_PUNTOS_E5L, nombre="fondo en la estación")
    ht = _horas(F_estacion["h"].to_numpy(), nombre="h del fondo")
    q = _horas(h, crecientes=False)
    pos = np.searchsorted(ht, q)
    pos_c = np.clip(pos, 0, max(len(ht) - 1, 0))
    ok = (pos < len(ht)) & (ht[pos_c] == q) if len(ht) else np.zeros(q.shape, dtype=bool)
    salida = {}
    for c in COLUMNAS_PUNTOS[1:]:
        x = np.full(q.shape, np.nan)
        x[ok] = F_estacion[c].to_numpy(np.float32)[pos_c[ok]].astype(np.float64)
        salida[c] = x
    return salida


# ---------------------------------------------------------------------------
# Lluvia (FON-11, FON-12; §2.6)
# ---------------------------------------------------------------------------
@_errores_de_fondo
def horas_de(meses: Sequence[MesE5L]) -> np.ndarray:
    """Las horas de la serie continua de los meses dados (las de ``incrementos_tp``)."""
    if not meses:
        raise ErrorFondo("se necesita al menos un mes")
    h = np.concatenate([np.asarray(m.tiempos, dtype=np.int64) for m in meses])
    if h.size > 1 and not (np.diff(h) > 0).all():
        raise ErrorFondo("los meses deben ir en orden y sin solaparse")
    return h


@_errores_de_fondo
def incrementos_tp(meses: Sequence[MesE5L]) -> np.ndarray:
    """Lluvia horaria (mm) de la hora que termina en cada sello, sobre la serie continua de ``meses`` (en orden), como
    ``meteo_civil_v3.lluvia_horaria`` (FON-11). Horas × píxeles, alineada con ``horas_de(meses)``; NaN sin la hora
    previa."""
    h = horas_de(meses)
    pid = np.asarray(meses[0].pixel_id, dtype=np.int64)
    if any(not np.array_equal(np.asarray(m.pixel_id, dtype=np.int64), pid) for m in meses[1:]):
        raise ErrorFondo("los meses deben traer los mismos píxeles en el mismo orden")
    tp = np.concatenate([_f8(m.datos["tp"]) for m in meses], axis=0)
    dif = np.full_like(tp, np.nan)
    seguidas = np.diff(h) == 1
    dif[1:][seguidas] = tp[1:][seguidas] - tp[:-1][seguidas]
    a_la_una = np.mod(h, _HORAS_DIA) == 1
    dif[a_la_una] = tp[a_la_una]
    return np.clip(dif * _MM_POR_M, 0, None)


def _sumas_6h(tp: np.ndarray, h: np.ndarray, fin: np.ndarray, columna: np.ndarray | None = None) -> np.ndarray:
    """Las sumas de FON-12: desde 0, los incrementos de u − 5, …, u en orden cronológico; NaN si falta alguno. Con
    ``columna`` (una por fin; −1 = ninguna), sólo esa columna de ``tp`` en cada fin. Es la única cuenta de RR06."""
    forma = (len(fin),) + (tp.shape[1:] if columna is None else ())
    total = np.zeros(forma)
    for atras in range(_HORAS_RR06 - 1, -1, -1):
        hh = fin - atras
        pos = np.searchsorted(h, hh)
        pos_c = np.clip(pos, 0, max(len(h) - 1, 0))
        ok = (pos < len(h)) & (h[pos_c] == hh) if len(h) else np.zeros(hh.shape, dtype=bool)
        valores = np.full(forma, np.nan)
        if columna is None:
            valores[ok] = tp[pos_c[ok]]
        else:
            ok = ok & (columna >= 0)
            valores[ok] = tp[pos_c[ok], columna[ok]]
        total = total + valores
    return total


@_errores_de_fondo
def sumas_rr06(tp_horario, h_fin, *, h) -> np.ndarray:
    """La suma de los 6 incrementos horarios que terminan en cada hora UTC ``h_fin`` (u − 5, …, u), con la serie
    ``tp_horario`` en las horas ``h`` (FON-12); NaN si falta alguna hora o es NaN."""
    tp = _f8(tp_horario)
    h = _horas(h)
    if tp.shape[:1] != h.shape:
        raise ErrorFondo("sumas_rr06: una fila de tp por hora")
    fin = _horas(h_fin, nombre="h_fin", crecientes=False)
    return _sumas_6h(tp, h, fin)


def _enteros(x, nombre: str) -> np.ndarray:
    """Un arreglo de una dimensión de enteros (no bool), como int64."""
    a = np.asarray(x)
    if a.ndim != 1 or a.dtype == bool or not np.issubdtype(a.dtype, np.integer):
        raise ErrorFondo(f"{nombre}: enteros, en un arreglo de una dimensión")
    return a.astype(np.int64)


@_errores_de_fondo
def pixel_de_lluvia(celdas, enlaces: pd.DataFrame) -> np.ndarray:
    """El píxel ERA5-Land de la lluvia de cada estación en RR06 (§2.6; D27, FON-12): el que
    ``enlaces_productos.parquet`` (``enlaces``) enlaza a su celda (``celdas``, una por estación: la ``celda`` de
    ``ESQUEMA_ESTACIONES_MC``, nula si la estación no tiene celda). int64, −1 sin enlace (sin celda, D34, o
    ``era5land_pixel`` = −1). Una celda que no está en la tabla, o una tabla mal armada, es un ``ErrorFondo``."""
    faltan = [c for c in COLUMNAS_ENLACE if c not in enlaces.columns]
    if faltan:
        raise ErrorFondo(f"enlaces_productos: faltan las columnas {faltan}")
    celda_e, pixel_e = enlaces["celda"], enlaces["era5land_pixel"]
    for nombre, serie in (("celda", celda_e), ("era5land_pixel", pixel_e)):
        if serie.isna().any() or not pd.api.types.is_integer_dtype(serie) or pd.api.types.is_bool_dtype(serie):
            raise ErrorFondo(f"enlaces_productos: {nombre} debe ser entero y sin nulos")
    ce, pe = celda_e.to_numpy(np.int64), pixel_e.to_numpy(np.int64)
    if len(np.unique(ce)) != len(ce):
        raise ErrorFondo("enlaces_productos: celda repetida")
    if (pe < _SIN_PIXEL).any():
        raise ErrorFondo(f"enlaces_productos: era5land_pixel menor que {_SIN_PIXEL}")
    if _COLUMNA_TIPO_ENLACE in enlaces.columns:
        tipo = enlaces[_COLUMNA_TIPO_ENLACE].astype("string")
        if tipo.isna().any():
            raise ErrorFondo(f"enlaces_productos: {_COLUMNA_TIPO_ENLACE} con nulos")
        if not np.array_equal((tipo == SIN_ENLACE).to_numpy(bool), pe == _SIN_PIXEL):
            raise ErrorFondo(f"enlaces_productos: «{SIN_ENLACE}» no va con era5land_pixel = {_SIN_PIXEL} en todas las "
                             "filas")
    q = pd.array(celdas, dtype="Int64")
    falta = np.asarray(q.isna(), dtype=bool)
    buscadas = q[~falta].to_numpy(dtype=np.int64)
    pos = _indice_ordenado(ce, buscadas)
    if (pos < 0).any():
        raise ErrorFondo(f"{int((pos < 0).sum())} celdas de estaciones no están en enlaces_productos")
    salida = np.full(len(q), _SIN_PIXEL, dtype=np.int64)
    salida[~falta] = pe[pos]
    return salida


@_errores_de_fondo
def lluvia_rr06(tp_horario, h_fin, pixel, *, h, pixel_ids) -> tuple[np.ndarray, np.ndarray]:
    """La suma de 6 h ERA5-Land de cada reporte RR06 (§2.6; D27, FON-12), rotulado en la hora UTC ``h_fin``, en el
    píxel ``pixel`` de su estación (``pixel_de_lluvia``), con la serie ``tp_horario`` (horas ``h`` × ``pixel_ids``, la
    de ``incrementos_tp``). Devuelve (suma en mm, float64; ``sin_enlace``, bool), uno por reporte. Sin enlace
    (``pixel`` = −1) la suma es NaN y el reporte no se compara: quien llama lo cuenta. La cuenta es la de
    ``sumas_rr06``, bit a bit; NaN si falta alguna de las 6 horas. Un píxel que no está en ``pixel_ids`` es un
    ``ErrorFondo``."""
    tp = _f8(tp_horario)
    h = _horas(h)
    ids = _enteros(pixel_ids, "pixel_ids")
    if len(np.unique(ids)) != len(ids):
        raise ErrorFondo("lluvia_rr06: pixel_ids repetidos")
    if tp.shape != (len(h), len(ids)):
        raise ErrorFondo("lluvia_rr06: tp es horas × píxeles, una fila por hora y una columna por pixel_id")
    fin = _horas(h_fin, nombre="h_fin", crecientes=False)
    p = _enteros(pixel, "pixel")
    if p.shape != fin.shape:
        raise ErrorFondo("lluvia_rr06: un píxel por reporte")
    if (p < _SIN_PIXEL).any():
        raise ErrorFondo(f"lluvia_rr06: píxel menor que {_SIN_PIXEL}")
    sin_enlace = p == _SIN_PIXEL
    columna = np.full(fin.shape, _SIN_PIXEL, dtype=np.int64)
    pos = _indice_ordenado(ids, p[~sin_enlace])
    if (pos < 0).any():
        raise ErrorFondo(f"lluvia_rr06: {int((pos < 0).sum())} reportes con un píxel enlazado que no está en los meses "
                         "ERA5-Land leídos")
    columna[~sin_enlace] = pos
    suma = _sumas_6h(tp, h, fin, columna)
    suma[sin_enlace] = np.nan
    return suma, sin_enlace


# ---------------------------------------------------------------------------
# Climatologías del estado y sp̄ (FON-13; §4.7, §4.1)
# ---------------------------------------------------------------------------
@dataclass(eq=False)
class AcumuladorEstado:
    """Sumas por píxel × mes × hora UTC × variable (``VARIABLES_CLIMA``) y de sp por píxel, en float64."""
    pixel_id: np.ndarray
    suma: np.ndarray
    n: np.ndarray
    suma_sp: np.ndarray
    n_sp: np.ndarray
    meses: set = field(default_factory=set)


@_errores_de_fondo
def acumulador_estado(pixel_id) -> AcumuladorEstado:
    """Un acumulador vacío para esos píxeles (en orden de ``pixel_id``)."""
    pid = np.unique(np.asarray(pixel_id, dtype=np.int64))
    forma = (len(pid), _MESES_ANIO, _HORAS_DIA, len(VARIABLES_CLIMA))
    return AcumuladorEstado(pixel_id=pid, suma=np.zeros(forma), n=np.zeros(forma, dtype=np.int64),
                            suma_sp=np.zeros(len(pid)), n_sp=np.zeros(len(pid), dtype=np.int64))


@_errores_de_fondo
def climatologias_estado(acumulador: AcumuladorEstado, mes: MesE5L) -> None:
    """Suma un mes al acumulador (FON-13): T, T − Td, rapidez y amplitud diaria por mes y hora UTC si el mes es de
    2000-2025, y sp si es del período de sp̄. Un mes ya sumado es un error."""
    ym = mes.yyyymm
    if ym in acumulador.meses:
        raise ErrorFondo(f"el mes {ym} ya se sumó al acumulador")
    m = _mes_de(np.asarray(mes.tiempos[:1], dtype=np.int64))[0]
    en_clima, en_sp = _en_periodo(m, _PERIODO_CLIMA), _en_periodo(m, _PERIODO_SP)
    if not (en_clima or en_sp):
        return
    col = _indice_ordenado(np.asarray(mes.pixel_id, dtype=np.int64), acumulador.pixel_id)
    if (col < 0).any():
        raise ErrorFondo(f"mes {ym}: le faltan píxeles del acumulador")
    h = np.asarray(mes.tiempos, dtype=np.int64)
    if en_clima:
        t2m = _f8(mes.datos["t2m"][:, col])
        T = t2m - _KELVIN
        with np.errstate(invalid="ignore"):
            t_menos_td = np.maximum(t2m - _f8(mes.datos["d2m"][:, col]), 0.0)    # D29: hora a hora; NaN sigue NaN
        valores = (T, t_menos_td, np.hypot(_f8(mes.datos["u10"][:, col]), _f8(mes.datos["v10"][:, col])),
                   amplitud_dia_utc(T, h))
        i_mes = int(m.astype(np.int64) % _MESES_ANIO)
        horas = np.mod(h, _HORAS_DIA)
        for hora in range(_HORAS_DIA):
            filas = horas == hora
            if not filas.any():
                continue
            for k, x in enumerate(valores):
                xs = x[filas]
                ok = np.isfinite(xs)
                acumulador.suma[:, i_mes, hora, k] += np.where(ok, xs, 0.0).sum(axis=0)
                acumulador.n[:, i_mes, hora, k] += ok.sum(axis=0)
    if en_sp:
        sp = _f8(mes.datos["sp"][:, col])
        ok = np.isfinite(sp)
        acumulador.suma_sp += np.where(ok, sp, 0.0).sum(axis=0)
        acumulador.n_sp += ok.sum(axis=0)
    acumulador.meses.add(ym)


@_errores_de_fondo
def tabla_clima_estado(acumulador: AcumuladorEstado) -> pd.DataFrame:
    """``ESQUEMA_CLIMA_ESTADO``: una fila por píxel × mes (1-12) × hora UTC, con las medias en float32 (NaN sin
    valores)."""
    P = len(acumulador.pixel_id)
    with np.errstate(invalid="ignore", divide="ignore"):
        media = np.where(acumulador.n > 0, acumulador.suma / np.where(acumulador.n > 0, acumulador.n, 1), np.nan)
    datos = {"pixel_id": np.repeat(acumulador.pixel_id, _MESES_ANIO * _HORAS_DIA),
             "mes": np.tile(np.repeat(np.arange(1, _MESES_ANIO + 1), _HORAS_DIA), P).astype(np.int8),
             "hora": np.tile(np.arange(_HORAS_DIA), P * _MESES_ANIO).astype(np.int8)}
    for k, nombre in enumerate(VARIABLES_CLIMA):
        datos[nombre] = media[..., k].reshape(-1).astype(np.float32)
    tabla = pd.DataFrame(datos, columns=list(tipos.ESQUEMA_CLIMA_ESTADO)).astype(dict(tipos.ESQUEMA_CLIMA_ESTADO))
    tipos.validar_esquema(tabla, tipos.ESQUEMA_CLIMA_ESTADO, nombre="clima_estado")
    tabla.attrs["esquema"] = tipos.ESQUEMA_CLIMA_ESTADO.version
    return tabla


def _cubo_clima(clima: pd.DataFrame) -> tuple[np.ndarray, dict]:
    """(pixel_id en orden creciente, {variable: píxel × mes × hora en float64 desde float32}) de una tabla
    ``ESQUEMA_CLIMA_ESTADO`` con las 12 × 24 filas exactas de cada píxel (FON-14)."""
    tipos.validar_esquema(clima, tipos.ESQUEMA_CLIMA_ESTADO, nombre="clima_estado")
    pid = clima["pixel_id"].to_numpy(np.int64)
    mes = clima["mes"].to_numpy(np.int64)
    hora = clima["hora"].to_numpy(np.int64)
    if ((mes < 1) | (mes > _MESES_ANIO) | (hora < 0) | (hora >= _HORAS_DIA)).any():
        raise ErrorFondo("clima_estado: mes fuera de 1-12 u hora fuera de 0-23")
    pixeles, cuantas = np.unique(pid, return_counts=True)
    clave = (np.searchsorted(pixeles, pid) * _MESES_ANIO + (mes - 1)) * _HORAS_DIA + hora
    if len(np.unique(clave)) != len(clave):
        raise ErrorFondo("clima_estado: filas repetidas (píxel, mes y hora)")
    if (cuantas != _MESES_ANIO * _HORAS_DIA).any():
        raise ErrorFondo(f"clima_estado: {int((cuantas != _MESES_ANIO * _HORAS_DIA).sum())} píxeles sin sus "
                         f"{_MESES_ANIO} × {_HORAS_DIA} filas")
    orden = np.argsort(clave, kind="stable")
    forma = (len(pixeles), _MESES_ANIO, _HORAS_DIA)
    cubo = {v: clima[v].to_numpy(np.float32)[orden].astype(np.float64).reshape(forma) for v in VARIABLES_CLIMA}
    return pixeles, cubo


@_errores_de_fondo
def clima_en_puntos(clima: pd.DataFrame, op: tipos.OperadorPuntos, umbrales) -> dict:
    """El operador del fondo aplicado a las climatologías del estado (§4.7; D29, FON-14): para cada punto de ``op``,
    mes (1-12) y hora UTC, T (°C) con los pesos bilineales y Γ; T − Td (K), rapidez (m/s) y amplitud (K) con los pesos
    bilineales solos. ``clima``: ``ESQUEMA_CLIMA_ESTADO`` (``tabla_clima_estado``). Devuelve {variable de
    ``VARIABLES_CLIMA``: punto × 12 × 24 en float64} y ``renormalizada`` (bool, igual forma). La posición 0 del eje del
    mes es enero."""
    gamma = float(umbrales.a("GAMMA_K_KM"))
    pixeles, cubo = _cubo_clima(clima)
    pix = np.asarray(op.pix).astype(np.int64)
    w, dz = np.asarray(op.w, dtype=np.float64), np.asarray(op.dz, dtype=np.float64)
    if pix.ndim != 2 or pix.shape[1] != _N_VECINOS or w.shape != pix.shape or dz.shape != pix.shape:
        raise ErrorFondo(f"clima_en_puntos: el operador trae {_N_VECINOS} casillas por punto")
    n = pix.shape[0]
    fila = np.full(pix.shape, _SIN_PIXEL, dtype=np.int64)
    con = pix >= 0
    pos = _indice_ordenado(pixeles, pix[con])
    if (pos < 0).any():
        raise ErrorFondo(f"clima_en_puntos: {len(np.unique(pix[con][pos < 0]))} píxeles del operador no están en la "
                         "tabla de climatologías")
    fila[con] = pos
    forma = (n, _MESES_ANIO, _HORAS_DIA)
    suma = {v: np.zeros(forma) for v in VARIABLES_CLIMA}
    peso = {v: np.zeros(forma) for v in VARIABLES_CLIMA}
    estatico = np.zeros(n)
    for k in range(_N_VECINOS):
        filas = np.flatnonzero(fila[:, k] >= 0)
        if filas.size == 0:
            continue
        estatico[filas] = estatico[filas] + w[filas, k]
        wk, dzk = w[filas, k][:, None, None], dz[filas, k][:, None, None]
        for v in VARIABLES_CLIMA:
            x = cubo[v][fila[filas, k]]
            if v == "T":
                with np.errstate(invalid="ignore"):
                    x = x + gamma * dzk / _M_POR_KM
            ok = np.isfinite(x)
            suma[v][filas] += np.where(ok, wk * x, 0.0)
            peso[v][filas] += np.where(ok, wk, 0.0)
    salida: dict[str, np.ndarray] = {}
    renormalizada = np.zeros(forma, dtype=bool)
    for v in VARIABLES_CLIMA:
        con_dato = peso[v] > 0
        with np.errstate(invalid="ignore", divide="ignore"):
            salida[v] = np.where(con_dato, suma[v] / np.where(con_dato, peso[v], 1.0), np.nan)
        renormalizada |= con_dato & (peso[v] < estatico[:, None, None])
    salida["renormalizada"] = renormalizada
    return salida


@_errores_de_fondo
def clima_en_horas(clima_puntos: Mapping, h) -> dict:
    """Las climatologías en los puntos (``clima_en_puntos``) en las horas ``h`` (int): las del mes (1-12) y la hora
    UTC de cada h (FON-13, FON-14). {variable de ``VARIABLES_CLIMA``: horas × puntos en float64}."""
    h = _horas(h, crecientes=False)
    i_mes = np.mod(_mes_de(h).astype(np.int64), _MESES_ANIO)
    hora = np.mod(h, _HORAS_DIA)
    salida = {}
    for v in VARIABLES_CLIMA:
        if v not in clima_puntos:
            raise ErrorFondo(f"clima_en_horas: falta {v}")
        x = _f8(clima_puntos[v])
        if x.shape[1:] != (_MESES_ANIO, _HORAS_DIA):            # punto × mes × hora (implica los tres ejes)
            raise ErrorFondo(f"clima_en_horas: {v} es punto × {_MESES_ANIO} × {_HORAS_DIA}")
        salida[v] = x[:, i_mes, hora].T
    return salida


@_errores_de_fondo
def sp_medio_hpa(acumulador: AcumuladorEstado) -> pd.Series:
    """sp̄ por píxel en hPa (la media de sp de todas las horas con dato del período; NaN sin ninguna)."""
    with np.errstate(invalid="ignore", divide="ignore"):
        media = np.where(acumulador.n_sp > 0, acumulador.suma_sp / np.where(acumulador.n_sp > 0, acumulador.n_sp, 1),
                         np.nan) / _PA_POR_HPA
    return pd.Series(media, index=pd.Index(acumulador.pixel_id, name="pixel_id"), name="sp_medio_hpa")
