"""Campos del producto (§3, §4.1, §6.2, §8): T, Td, u, v, p, HR, rapidez y dirección; NetCDF de 0,1° en int16.

Este módulo es puro: recibe arreglos, tablas, ``DatosCompetencia`` y los umbrales, y devuelve diccionarios o bytes. No lee
ni escribe archivos (§0, regla 8 del diseño): el NetCDF mensual de 0,1° se arma en memoria y sólo ``salidas`` escribe sus
bytes (A19). R, la corrección del candidato, vive sólo en memoria: nunca se guarda ni se informa (§0.4.3).

Qué hace cada función:
- ``correccion``: R_T, R_Td, R_u, R_v y R_p de un candidato en un conjunto de puntos (celdas, píxeles o estaciones) y un
  lote de horas de un mes UTC, por lotes de puntos (PED-6), con las funciones de ``candidatos``.
- ``campos``: el producto con ``fondo_era5l.producto_desde`` más HR, rapidez y dirección.
- ``producto_mes``: el fondo de un mes en los puntos de un operador y el producto con el ganador de cada grupo del uso.
- ``codificar_int16`` y ``decodificar_int16``: el formato de §8 (fila «Formato» del Anexo A).
- ``mes_01deg``: los bytes del NetCDF mensual de los píxeles válidos (MC-08, A19).
- ``hay_fondo``, ``conteo_finito``, ``fraccion_finita``, ``conteo_finito_c`` y ``pasa_e0``: la finitud de E0 (MC-51,
  A21), sumable entre lotes; la de C y C_est, también sin calcular R.

Dueño: I16 (ola 4).
Lecturas propias (PRO-n), para el addendum de M1:
- PRO-1. **El lote de horas** (MC-37). ``correccion``, ``conteo_finito_c`` y ``mes_01deg`` exigen horas enteras (h,
  horas desde 2000-01-01T00Z) dentro de int32, **consecutivas desde la primera hora de un mes UTC** y dentro de ese mes:
  «El tamaño del lote de horas es fijo (un mes UTC) en todo M3-4 y M5» (§3 del diseño). El lote sólo puede quedar corto
  al final (el último mes, hasta el último dato de ERA5-Land), como ``MesE5L.completo_hasta``: un hueco en el medio o un
  comienzo a mitad de mes es un error (con huecos, la amplitud diaria de C daría NaN sin aviso, FON-10). Un lote vacío
  también.
- PRO-2. **El lote de puntos** (PED-6). Los puntos se recorren en su orden, por lotes de ``LOTE_PUNTOS_NUCLEO`` en A, B y
  AB y de ``LOTE_PUNTOS_C`` en C y C_est (sólo memoria; ``lote_puntos`` lo cambia). Cada (hora, punto) del núcleo y de A
  se calcula solo (productos dispersos por fila de ``candidatos``), y en C la cuenta de cada fila no depende de las demás
  en el entorno fijado (``test_producto`` lo comprueba bit a bit con lotes de 1, 3 y el de omisión): el lote no cambia
  ningún bit, así que ``orquestacion`` puede partir los puntos en unidades de cualquier tamaño (S9). La salida ocupa
  8·n_horas·n_puntos bytes por variable: quien llama elige cuántos puntos pasa (un mes en las 838.430 celdas son
  ≈ 5 GB por variable).
- PRO-3. **Los hiperparámetros** (§4.2, §4.9). ``hiper`` es {variable: θ} con θ = ``tipos.Hiper`` en A y B, (Hiper de
  A, Hiper de Φ′) en AB y α en C y C_est, como ``candidatos.predecir_prueba``. Se calculan las variables de ``hiper``
  (un candidato puede ganar sólo un grupo), pero los grupos van enteros: T con Td, y u con v con el mismo θ (MC-43 en el
  núcleo; P66 en el α de C, «un solo ganador» por grupo, §6.1). Una variable o un θ de otro tipo es un error.
- PRO-4. **El entrenamiento de producción** (§4.9, «Producción: … sobre todas las estaciones»). Por omisión, todas las
  estaciones de ``datos.estaciones`` que no están excluidas, en orden de código; las que están fuera de la grilla
  entrenan A, B y AB y no tienen filas de C (D34, CAN-13). ``entrenamiento`` lo cambia (por ejemplo, el de un pliegue
  externo, para comparar con ``candidatos.predecir_prueba``).
- PRO-5. **Cómo se calcula cada candidato** (sin copiar fórmulas de ``candidatos``). A: ``candidatos.correccion_a``
  con la climatología de A de la variable (``datos.climatologias``). B: ``candidatos.matriz_q`` (r̃, con las horas no
  observadas interpoladas) y ``candidatos.correccion_b`` con disponible = q finito, como ``predecir_prueba`` (CAN-15).
  AB: ``candidatos.correccion_ab`` con los vecinos de A y los de Φ′ del mismo entrenamiento. C y C_est:
  ``candidatos.ajustar_c`` sobre ``datos.filas_c`` del entrenamiento y ``candidatos.predecir_c`` fila a fila
  (punto × hora). Lejos de las estaciones el núcleo da 0, no NaN (§4.2: «vuelve al fondo»).
- PRO-6. **El estado de C en los puntos** (§4.6, A14). T_F, T_F − Td_F, √(u_F² + v_F²) y la amplitud diaria de T_F en el
  día UTC, desde el fondo de los puntos en el lote (``fondo``: T_F, Td_F, u_F y v_F, hora × punto; ``amp_TF`` si viene,
  si no ``fondo_era5l.amplitud_dia_utc`` sobre el lote, que en un mes UTC tiene días enteros: FON-9). Sin redondear a
  float32: el fondo de las celdas y los píxeles no se guarda (FON-8); el de una estación llega ya en float32 (A1) si
  quien llama lo trae de ``ESQUEMA_PUNTOS_E5L``. La fórmula es la de ``candidatos.estado_c``, copiada para arreglos
  hora × punto con su prueba de paridad (pedido PED-7 de I16). El fondo debe traer Td_F ≤ T_F (el recorte de §4.1; sin
  él, ``ErrorProducto``): C no recorta de nuevo T_F − Td_F (CAN-10).
- PRO-7. **El estado de C_est en los puntos** (§4.7, A14, D29). ``clima`` es la salida de ``fondo_era5l.clima_en_puntos``
  con el operador de los puntos (punto × 12 × 24); ``fondo_era5l.clima_en_horas`` lo lleva al mes y la hora UTC de cada
  h. ``candidatos.predecir_c`` sólo acepta en C_est el clima 12 × 24 de un punto; para pasarle el estado ya llevado a
  las horas de muchos puntos se usa el mismo modelo con ``diseno`` = «estado», que sólo cambia de dónde sale el estado
  (§4.7: «el mismo diseño»). Los números son los mismos: la prueba de paridad con ``predecir_prueba`` es bit a bit
  (pedido PED-8 de I16). ``producto_mes`` recibe la tabla ``ESQUEMA_CLIMA_ESTADO`` y calcula él el clima con el
  operador de los puntos, para que el clima no se desalinee de los puntos.
- PRO-8. **Los estáticos de C en los puntos y el cotejo por identidad** (§4.6, TIP-22). ``estaticos`` es
  ``ESQUEMA_ESTATICAS_CELDA_C`` con una fila por punto (esquema exacto), y su columna ``celda`` debe ser, en orden, la
  celda de cada punto (``celdas``; por omisión, los ids de los puntos, que en las celdas son su ``celda``): no se
  cotejan por posición. En una estación, la de su celda. En un centro de píxel (0,1°), la de la celda que lo contiene,
  como en una estación («Los estáticos de una estación son los de su celda»; el fondo se evalúa en el punto), con el
  z_media y el z_e5l de esa celda: lo decide quien arma las filas, y queda como la pregunta P-PRO-1. Una fila con
  estáticos NaN da R NaN (C no predice sin diseño finito, CAN-10). ``producto_mes`` coteja además los ids de los puntos
  con los del operador (y su z, A10).
- PRO-9. **Los candidatos de cada uso** (§6.1, §4.7, §6.4). Ambiental y agudo: A, B, AB y C; crónico: A, B, AB y C_est.
  C_est fuera de lo crónico y C en lo crónico («Nada crónico usa … C con variables de estado», §6.4) son un
  ``ErrorProducto``. Los grupos que decide cada uso son los de §6.1: los tres en lo ambiental y sólo (T, Td) en lo agudo y
  lo crónico; ``producto_mes`` deja NaN las variables de los grupos que el uso no decide (§6.4: «Su temperatura y su
  humedad salen de su propio ganador»).
- PRO-10. **Los campos** (§3, §4.1). ``fondo_era5l.producto_desde`` (T = T_F + R_T; Td = mín(Td_F + R_Td, T); u y v
  sumados; p = p_F·exp(R_p); sin redondeos, FON-8). R debe traer exactamente las cinco claves. HR = 100·e(Td)/e_s(T) con
  Magnus sobre agua (``numerico.hr_desde``), recortada en ``HR_PRODUCTO_RECORTE`` = [0, 100]. Rapidez = √(u² + v²).
  **Dirección** (MC-28): el ángulo ``arctan2(u, v)`` de ``el_*`` y de ``mc_wdir_*``, en grados de [0, 360), medido desde el
  norte en sentido horario y en la convención «hacia» de u10 y v10 (90 = hacia el este; la DMC informa «desde»). En calma
  (u = v = 0) vale 0, como ``arctan2(0, 0)`` en ``_features.py``; NaN si u o v no es finito. **Nota para I18 (S14):**
  ``campos`` (por ``producto_desde``) vuelve a aplicar Td = mín(·, T); S14 pide el fondo «sin el recorte Td ≤ T», así que
  la regresión no debe pasar por ``campos``: usa ``campos_fondo(…, recortar_td=False)`` directamente.
- PRO-11. **int16** (§8, Anexo A, «Formato»). Entero = rint((x − desplazamiento)/escala), con redondeo al par; T y Td con
  ``FMT_ESC_T``, u y v con ``FMT_ESC_UV``, p con ``FMT_ESC_P`` y ``FMT_DESP_P``; desplazamiento 0 en T, Td, u y v (la fila
  sólo da el de p). NaN → ``FMT_RELLENO``. Un valor infinito, uno que desborda int16 o uno que caería en el relleno es un
  ``DesbordeInt16`` (§8: «la presión desbordaría sin aviso»), con el conteo y el rango representable, sin los valores.
  Con el relleno en −32768 el rango es [−32.767; 32.767] por escala: p de 145 a 1.455 hPa (§8), T y Td de ±327,67 °C, u
  y v de ±327,67 m/s. Al decodificar: entero·escala + desplazamiento en float64, y el relleno vuelve a NaN. El error de ida
  y vuelta es ≤ media escala (S15). Se codifican sólo T, Td, u, v y p: HR, rapidez y dirección se derivan al leer; una
  clave que no es del producto (por ejemplo, una R) es un error.
- PRO-12. **El NetCDF de 0,1°** (§8, MC-08, A19). En memoria (``netCDF4.Dataset(…, memory=…)``), NETCDF4 sin compresión
  (≈ 19,2 GB en §8 es el int16 sin comprimir). Dimensiones ``time`` × ``pixel``; ``time`` en int32 («hours since
  2000-01-01 00:00:00», proleptic_gregorian, la forma que acepta el lector de ERA5-Land, FON-1); ``pixel_id`` en int64,
  estrictamente creciente (el orden de ``pixeles_validos``); T, Td, u, v y p en int16 con ``scale_factor``,
  ``add_offset`` y ``_FillValue``. Atributos globales: el esquema, el mes, el uso, el ganador de cada grupo, la convención
  del viento y las huellas. **Bytes deterministas** (S9): sin fechas ni rutas, y con la etiqueta del conjunto fija; con
  netCDF4 1.7.4, netcdf-c 4.10.1 y HDF5 1.14.6 dos corridas dan el mismo sha256 (la etiqueta no entra en los bytes). Los
  bytes dependen de las versiones de esas bibliotecas, que van al recibo (``micromamba list``, §8).
- PRO-13. **El uso y el ganador del NetCDF** (MC-08). Sólo el ambiental: otro uso es un ``ErrorProducto``. ``ganador`` es
  {grupo: candidato} con los tres grupos de lo ambiental y candidatos de ese uso (A, B, AB o C).
- PRO-14. **Las huellas** (§8, «Cadena de huellas»). Al menos una, {nombre: sha256 en hexadecimal minúsculo}; los
  nombres son textos sin rutas absolutas, sin «~», sin barra invertida, sin arroba, sin la carpeta de usuario en ninguna
  posición y sin segmentos «..» (las rutas van por alias, como en ``ceguera``). Van como JSON canónico (claves
  ordenadas) en el atributo ``huellas``: el orden en que llegan no cambia los bytes.
- PRO-15. **La finitud de E0** (§6.2, paso 1; MC-51, A21). Cuenta los puntos-hora con fondo (``con_fondo``: hora × punto,
  o un valor por punto que vale para todas las horas) y, entre ellos, los que tienen finitas todas las variables del
  grupo. Las variables se dan siempre (``variables`` o ``grupo``, uno de los dos, sin omisión: E0 es por uso y grupo).
  ``hay_fondo`` da ``con_fondo`` desde el fondo: los campos de F de **todas** las variables del grupo finitos (T_F y
  Td_F en (T, Td)). Los conteos son enteros y se suman entre lotes (``ConteoFinito``); la fracción es NaN sin
  puntos-hora con fondo. «≥ 99 %» (``E0_FINITO_PCT``, inclusive) se compara en enteros (100·finitos ≥ 99·con fondo);
  sin ningún punto-hora con fondo no hay decisión posible y ``pasa`` es un error. **Celdas y estaciones por separado**
  (pregunta N1, rige la más estricta): MC-51 nombra las celdas pobladas y las estaciones de validación; ``pasa_e0``
  recibe un conteo por conjunto y exige ≥ 99 % en cada uno. **Estaciones de D34** (pregunta N2): una estación fuera de
  la grilla sale de la evaluación de todos los candidatos (D34) y C y C_est dan NaN allí por construcción, así que no
  entra al conteo de estaciones de E0; lo arma quien elige los puntos (I20).
- PRO-16. **Vocabulario** (S7). Las claves que este módulo devuelve para publicar (``ConteoFinito.como_dict``) y los
  atributos que elige para el NetCDF no llevan el vocabulario prohibido; el NetCDF es «insumo» (D14) y R sólo sale de
  ``correccion``, en memoria.
- PRO-17. **Errores.** Los de este módulo son ``ErrorProducto`` (un ``RuntimeError``, como FON-2): un insumo mal armado
  detiene la corrida y nunca se confunde con un «no normalizable» (MC-57). Los de ``candidatos`` y ``fondo_era5l`` salen
  como son.
- PRO-18. **La finitud de C y C_est sin calcular R** (pedido H2 del revisor). ``conteo_finito_c`` cuenta como finito un
  punto-hora con fondo si los estáticos del punto son finitos (con ``candidatos.diseno_c`` sobre una fila por punto y un
  estado neutro: el TPI truncado vale 0 y cuenta como finito, como ``candidatos._filas_finitas``) y si su estado lo es
  (C: el de PRO-6; C_est: el de PRO-7). Los armónicos del tiempo siempre son finitos, así que es exactamente lo que decide
  si ``predecir_c`` da un valor finito; con ``con_fondo`` del grupo, si el producto es finito (T = T_F + R_T, Td =
  mín(·, T), p = p_F·exp(R_p)). ``test_producto`` lo compara con ``correccion`` + ``campos`` + ``conteo_finito``. Así I20
  no tiene que calcular R de C en todas las celdas pobladas y horas sólo para contar.
Depende de: tipos, constantes, umbrales, numerico, fondo_era5l, candidatos. Los umbrales llegan como objeto (``.a``),
así que ``umbrales`` no hace falta importarlo.
"""
from __future__ import annotations

import dataclasses
import json
import math
import re
import warnings
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Mapping

import numpy as np
import pandas as pd

from meteo_combinada import candidatos, constantes, fondo_era5l, numerico, tipos
from meteo_combinada.tipos import Candidato, DisenoC, Grupo, Hiper, Uso, Variable

# ---------------------------------------------------------------------------
# Nombres y constantes
# ---------------------------------------------------------------------------
VARIABLES = tuple(v.value for v in Variable)                          # T, Td, u, v, p
DERIVADAS = tuple(d.value for d in tipos.Derivada)                    # HR, rapidez, direccion
CLAVE_R = dict(zip(fondo_era5l.CLAVES_PRODUCTO, fondo_era5l.CLAVES_R))   # T → R_T, …
CAMPO_F = {v: f"{v}_F" for v in fondo_era5l.CLAVES_PRODUCTO}                # T → T_F, … (CAMPOS_F va en otro orden)
if set(CAMPO_F.values()) != set(fondo_era5l.CAMPOS_F) or set(CLAVE_R) != set(VARIABLES):
    raise ImportError("los nombres del fondo y de R no calzan con fondo_era5l")
VARIABLES_DE_GRUPO = {Grupo.T_TD: (Variable.T.value, Variable.TD.value),
                      Grupo.U_V: (Variable.U.value, Variable.V.value),
                      Grupo.P: (Variable.P.value,)}
# §6.1: los candidatos y los grupos de cada uso (PRO-9).
CANDIDATOS_DEL_USO = {Uso.AMBIENTAL: (Candidato.A, Candidato.B, Candidato.AB, Candidato.C),
                      Uso.AGUDO: (Candidato.A, Candidato.B, Candidato.AB, Candidato.C),
                      Uso.CRONICO: (Candidato.A, Candidato.B, Candidato.AB, Candidato.C_EST)}
GRUPOS_DEL_USO = {Uso.AMBIENTAL: (Grupo.T_TD, Grupo.U_V, Grupo.P),
                  Uso.AGUDO: (Grupo.T_TD,),
                  Uso.CRONICO: (Grupo.T_TD,)}
USO_01DEG = Uso.AMBIENTAL                                             # MC-08
DE_C = (Candidato.C, Candidato.C_EST)
ESTADO_C = candidatos.ESTADO_C                                        # T, T_menos_Td, rapidez, amp (TIP-17)

LOTE_PUNTOS_NUCLEO = 2048        # PRO-2: puntos por lote en A, B y AB (sólo memoria)
LOTE_PUNTOS_C = 32               # PRO-2: puntos por lote en C y C_est (filas = puntos × horas del mes)

_EPOCA_H = np.datetime64("2000-01-01T00", "h")                         # h = 0 (tipos.EPOCA_H)
_INT32 = np.iinfo(np.int32)
_INT16 = np.iinfo(np.int16)
_VUELTA_GRADOS = 360.0           # no-umbral: grados de una vuelta (dirección en [0, 360))
_HR_RECORTE = tuple(float(x) for x in constantes.valor("HR_PRODUCTO_RECORTE"))   # [0, 100] (§3)
_E0_PCT = constantes.valor("E0_FINITO_PCT")                           # 99 (§6.2, paso 1)
_PORCENTAJE = 100

# PRO-11: escala y desplazamiento de cada variable (ids de la fila «Formato» del Anexo A; None = sin desplazamiento).
FORMATO_IDS = {Variable.T.value: ("FMT_ESC_T", None), Variable.TD.value: ("FMT_ESC_T", None),
               Variable.U.value: ("FMT_ESC_UV", None), Variable.V.value: ("FMT_ESC_UV", None),
               Variable.P.value: ("FMT_ESC_P", "FMT_DESP_P")}
RELLENO_ID = "FMT_RELLENO"

# PRO-12: el NetCDF de 0,1°.
ESQUEMA_01DEG = "meteo-combinada-01deg/1"
UNIDADES_TIEMPO = "hours since 2000-01-01 00:00:00"
CALENDARIO = "proleptic_gregorian"
UNIDADES = {Variable.T.value: "degC", Variable.TD.value: "degC", Variable.U.value: "m s-1",
            Variable.V.value: "m s-1", Variable.P.value: "hPa"}
NOMBRES_LARGOS = {Variable.T.value: "temperatura a 2 m",
                  Variable.TD.value: "punto de rocío a 2 m (Td ≤ T)",
                  Variable.U.value: "viento a 10 m, componente hacia el este",
                  Variable.V.value: "viento a 10 m, componente hacia el norte",
                  Variable.P.value: "presión en superficie a la altitud del píxel"}
CONVENCION_VIENTO = "hacia: u > 0 sopla hacia el este y v > 0 hacia el norte"
_ETIQUETA_NC = "meteo_01deg.nc"  # la etiqueta del conjunto en memoria (no entra en los bytes; PRO-12)
_HOLGURA_NC = 65536              # bytes de holgura del tamaño inicial en memoria (netCDF4 lo agranda si falta)
_SHA256 = re.compile(r"[0-9a-f]{64}")
_CARPETA_USUARIOS = "/" + "Users" + "/"   # se arma aquí para que el archivo no la traiga literal (AP es público)


class ErrorProducto(RuntimeError):
    """Una entrada mal armada o fuera de las reglas del producto (PRO-17): se detiene; no es un ValueError (MC-57)."""


class DesbordeInt16(ErrorProducto):
    """Un valor que el int16 de §8 no puede representar (desborda o caería en el relleno; PRO-11)."""


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def _netcdf4() -> ModuleType:
    """netCDF4 del entorno fijado; su aviso conocido de ABI con numpy 2 se silencia (como ``fondo_era5l``)."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="numpy.ndarray size changed", category=RuntimeWarning)
        import netCDF4
    return netCDF4


def _f8(x) -> np.ndarray:
    return np.asarray(x, dtype=np.float64)


def _lote_de_horas(lote_h) -> np.ndarray:
    """PRO-1: horas enteras en int32, consecutivas desde la primera hora de un mes UTC y dentro de ese mes; el lote sólo
    puede quedar corto al final (el último mes, como ``MesE5L.completo_hasta``)."""
    h = np.asarray(lote_h)
    if h.ndim != 1 or h.size == 0:
        raise ErrorProducto("el lote de horas es un arreglo de una dimensión y no vacío (PRO-1)")
    if h.dtype == bool or not np.issubdtype(h.dtype, np.integer):
        raise ErrorProducto(f"las horas son enteros (horas desde 2000-01-01T00Z), no {h.dtype}")
    h = h.astype(np.int64)
    if h.size > 1 and not bool(np.all(np.diff(h) > 0)):
        raise ErrorProducto("las horas del lote deben ir estrictamente crecientes y sin repetir")
    if h.min() < _INT32.min or h.max() > _INT32.max:
        raise ErrorProducto("horas fuera de int32")
    meses = (_EPOCA_H + h[[0, -1]].astype("timedelta64[h]")).astype("datetime64[M]")
    if meses[0] != meses[1]:
        raise ErrorProducto("el lote de horas es un solo mes UTC (MC-37, PRO-1)")
    inicio = int((meses[0].astype("datetime64[h]") - _EPOCA_H).astype(np.int64))
    if h[0] != inicio or (h.size > 1 and not bool(np.all(np.diff(h) == 1))):
        raise ErrorProducto("el lote son las horas consecutivas de un mes UTC desde su primera hora, y sólo puede quedar "
                            "corto al final (como MesE5L.completo_hasta; una amplitud diaria con huecos daría NaN; "
                            "PRO-1)")
    return h


def _mes_aaaamm(h: np.ndarray) -> str:
    mes = (_EPOCA_H + h[:1].astype("timedelta64[h]")).astype("datetime64[M]")[0]
    return str(mes).replace("-", "")


def _puntos(puntos) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(ids, lat, lon, z) de un dict o DataFrame con «lat», «lon» y «z» (e «ids» opcional): la forma de
    ``candidatos.vecinos``. z en m (A10: z_media o z_poblada en celdas, z_E5L en píxeles, z_s en estaciones)."""
    if not isinstance(puntos, (pd.DataFrame, Mapping)):
        raise ErrorProducto(f"puntos: un dict o DataFrame con lat, lon y z, no {type(puntos).__name__}")
    faltan = [c for c in ("lat", "lon", "z") if c not in puntos]
    if faltan:
        raise ErrorProducto(f"a los puntos les faltan {faltan}")
    lat, lon, z = (np.asarray(puntos[c], dtype=np.float64).ravel() for c in ("lat", "lon", "z"))
    ids = np.asarray(puntos["ids"]).ravel() if "ids" in puntos else np.arange(lat.size)
    if not (lat.shape == lon.shape == z.shape == ids.shape):
        raise ErrorProducto("lat, lon, z e ids de los puntos deben tener el mismo largo")
    return ids, lat, lon, z


def _enumerado(clase, valor):
    """El valor del enumerado, o ``ErrorProducto`` (PRO-17)."""
    try:
        return clase(valor)
    except ValueError:
        raise ErrorProducto(f"{clase.__name__} desconocido: {valor!r}") from None


def _uso(cand: Candidato, uso) -> Uso:
    """PRO-9: el candidato debe ser del uso (§6.1)."""
    uso = _enumerado(Uso, uso)
    if cand not in CANDIDATOS_DEL_USO[uso]:
        raise ErrorProducto(f"{cand.value} no es candidato de lo {uso.value} (§6.1, §4.7, §6.4)")
    return uso


def _theta(cand: Candidato, variable: str, theta):
    """El hiperparámetro de una variable con el tipo del candidato (PRO-3)."""
    if cand in DE_C:
        if isinstance(theta, (bool, np.bool_)) or not isinstance(theta, (int, float, np.integer, np.floating)) \
                or not math.isfinite(float(theta)) or float(theta) <= 0:
            raise ErrorProducto(f"{cand.value}/{variable}: el hiperparámetro es α (finito y > 0), no {theta!r}")
        return float(theta)
    if cand is Candidato.AB:
        if not (isinstance(theta, tuple) and len(theta) == 2 and all(isinstance(t, Hiper) for t in theta)):
            raise ErrorProducto(f"AB/{variable}: los hiperparámetros son (Hiper de A, Hiper de Φ′)")
        return theta
    if not isinstance(theta, Hiper):
        raise ErrorProducto(f"{cand.value}/{variable}: el hiperparámetro es tipos.Hiper, no {type(theta).__name__}")
    return theta


def _hiperparametros(cand: Candidato, hiper) -> dict[str, Any]:
    """{variable: θ} en el orden de ``VARIABLES``, con los grupos enteros y u y v con el mismo θ (PRO-3)."""
    if not isinstance(hiper, Mapping) or not hiper:
        raise ErrorProducto("hiper es {variable: hiperparámetros}, con al menos una variable")
    por_variable = {}
    for clave, theta in hiper.items():
        try:
            v = Variable(clave).value
        except ValueError:
            raise ErrorProducto(f"variable desconocida en hiper: {clave!r}") from None
        if v in por_variable:
            raise ErrorProducto(f"variable repetida en hiper: {v!r}")
        por_variable[v] = _theta(cand, v, theta)
    for grupo, variables in VARIABLES_DE_GRUPO.items():
        presentes = [v for v in variables if v in por_variable]
        if presentes and len(presentes) != len(variables):
            raise ErrorProducto(f"el grupo {grupo.value} va entero: {list(variables)} (§6.1, un ganador por grupo)")
    u, v = Variable.U.value, Variable.V.value
    if u in por_variable and por_variable[u] != por_variable[v]:
        raise ErrorProducto("u y v comparten sus hiperparámetros (MC-43; P66 en C)")
    return {v: por_variable[v] for v in VARIABLES if v in por_variable}


def _entrenamiento(datos, entrenamiento) -> tuple[str, ...]:
    """PRO-4: los códigos de entrenamiento, ordenados; por omisión, todas las estaciones que no están excluidas."""
    infos = datos.estaciones
    if entrenamiento is None:
        codigos = sorted(c for c, info in infos.items() if not info.excluida)
    else:
        if isinstance(entrenamiento, str):
            raise ErrorProducto("entrenamiento es una secuencia de códigos, no un texto")
        codigos = list(entrenamiento)
        if len(set(codigos)) != len(codigos):
            raise ErrorProducto("entrenamiento repite códigos")
        ajenos = [c for c in codigos if c not in infos]
        if ajenos:
            raise ErrorProducto(f"entrenamiento con códigos sin InfoEstacion: {sorted(map(str, ajenos))}")
        excluidas = [c for c in codigos if infos[c].excluida]
        if excluidas:
            raise ErrorProducto(f"una estación excluida no entrena (PAR-1): {sorted(excluidas)}")
        codigos = sorted(codigos)
    if not codigos:
        raise ErrorProducto("sin estaciones de entrenamiento")
    return tuple(codigos)


def _tamano_lote(cand: Candidato, lote_puntos) -> int:
    if lote_puntos is None:
        return LOTE_PUNTOS_C if cand in DE_C else LOTE_PUNTOS_NUCLEO
    if isinstance(lote_puntos, (bool, np.bool_)) or not isinstance(lote_puntos, (int, np.integer)) or lote_puntos < 1:
        raise ErrorProducto(f"lote_puntos es un entero ≥ 1, no {lote_puntos!r}")
    return int(lote_puntos)


def _matriz(x, forma: tuple[int, int], nombre: str) -> np.ndarray:
    a = _f8(x)
    if a.shape != forma:
        raise ErrorProducto(f"{nombre}: forma {a.shape}; se espera hora × punto {forma}")
    return a


# ---------------------------------------------------------------------------
# El estado de C y C_est en los puntos (PRO-6, PRO-7)
# ---------------------------------------------------------------------------
def estado_c_puntos(T_F, Td_F, u_F, v_F, amp) -> dict[str, np.ndarray]:
    """El estado del fondo de C (§4.6, CAN-10) desde arreglos de igual forma (hora × punto): T_F, T_F − Td_F,
    √(u_F² + v_F²) y la amplitud diaria. Es la fórmula de ``candidatos.estado_c``, copiada para arreglos de dos
    dimensiones mientras rija PED-7 (``test_producto`` vigila la paridad)."""
    T, Td, u, v, a = (_f8(x) for x in (T_F, Td_F, u_F, v_F, amp))
    if not (T.shape == Td.shape == u.shape == v.shape == a.shape):
        raise ErrorProducto("el estado de C: T_F, Td_F, u_F, v_F y la amplitud con la misma forma")
    return dict(zip(ESTADO_C, (T, T - Td, np.hypot(u, v), a)))


def _estado_c_lote(fondo: Mapping, h: np.ndarray, columnas: slice) -> dict[str, np.ndarray]:
    T = fondo["T_F"][:, columnas]
    Td = fondo["Td_F"][:, columnas]
    with np.errstate(invalid="ignore"):
        if bool(np.any(Td > T)):
            raise ErrorProducto("el fondo de C trae Td_F > T_F: falta el recorte Td_F := mín(Td_F, T_F) de §4.1 (PRO-6)")
    amp = fondo["amp_TF"][:, columnas] if "amp_TF" in fondo else fondo_era5l.amplitud_dia_utc(T, h)
    return estado_c_puntos(T, Td, fondo["u_F"][:, columnas], fondo["v_F"][:, columnas], amp)


def _fondo_de_c(fondo, n_h: int, n: int) -> dict[str, np.ndarray]:
    if not isinstance(fondo, Mapping):
        raise ErrorProducto("C necesita el fondo de los puntos (T_F, Td_F, u_F y v_F, hora × punto; PRO-6)")
    claves = ("T_F", "Td_F", "u_F", "v_F") + (("amp_TF",) if "amp_TF" in fondo else ())
    faltan = [c for c in claves if c not in fondo]
    if faltan:
        raise ErrorProducto(f"al fondo de C le faltan {faltan}")
    return {c: _matriz(fondo[c], (n_h, n), f"fondo[{c!r}]") for c in claves}


def _clima_de_c_est(clima, n: int) -> dict[str, np.ndarray]:
    if not isinstance(clima, Mapping):
        raise ErrorProducto("C_est necesita el clima del estado en los puntos (fondo_era5l.clima_en_puntos; PRO-7)")
    salida = {}
    for v in fondo_era5l.VARIABLES_CLIMA:
        if v not in clima:
            raise ErrorProducto(f"al clima de C_est le falta {v!r}")
        x = _f8(clima[v])
        if x.shape != (n, 12, 24):
            raise ErrorProducto(f"clima[{v!r}]: forma {x.shape}; se espera punto × 12 × 24")
        salida[v] = x
    return salida


def _celdas_de_puntos(celdas, ids: np.ndarray) -> np.ndarray:
    """PRO-8: la celda de cada punto (por omisión, sus ids: los puntos son celdas), en int64."""
    c = np.asarray(ids if celdas is None else celdas).ravel()
    if c.shape != ids.shape:
        raise ErrorProducto("celdas: una por punto, en el orden de los puntos (PRO-8)")
    if c.dtype.kind in "iu":
        return c.astype(np.int64)
    if c.dtype == object and all(isinstance(x, (int, np.integer)) and not isinstance(x, (bool, np.bool_))
                                 for x in c.tolist()):
        return c.astype(np.int64)
    raise ErrorProducto("celdas: los ids de celda son enteros; si los puntos no son celdas (estaciones, píxeles), "
                        "quien llama pasa «celdas» (PRO-8)")


def _estaticos_de_puntos(estaticos, n: int, celdas: np.ndarray) -> pd.DataFrame:
    """PRO-8: ``ESQUEMA_ESTATICAS_CELDA_C`` exacto, una fila por punto, cotejada por su celda (no por la posición)."""
    if not isinstance(estaticos, pd.DataFrame):
        raise ErrorProducto("C y C_est necesitan los estáticos de los puntos (ESQUEMA_ESTATICAS_CELDA_C; PRO-8)")
    try:
        tipos.validar_esquema(estaticos, tipos.ESQUEMA_ESTATICAS_CELDA_C, nombre="estáticos de los puntos")
    except (ValueError, TypeError) as error:
        raise ErrorProducto(str(error)) from error
    if len(estaticos) != n:
        raise ErrorProducto(f"estáticos: {len(estaticos)} filas para {n} puntos (una por punto, en su orden)")
    if not np.array_equal(estaticos["celda"].to_numpy(np.int64), celdas):
        raise ErrorProducto("estáticos: la columna «celda» no es la celda de cada punto, en su orden (PRO-8)")
    return estaticos.reset_index(drop=True)


def _predecir_c_lote(modelo, estaticos: pd.DataFrame, indices: np.ndarray, h: np.ndarray,
                     estado: Mapping[str, np.ndarray]) -> np.ndarray:
    """R de C en un lote de puntos (hora × punto): ``candidatos.predecir_c`` sobre las filas punto × hora."""
    n_p, n_h = indices.size, h.size
    filas = estaticos.iloc[np.repeat(indices, n_h)]
    horas = np.tile(h, n_p)
    estado_filas = {v: np.ascontiguousarray(estado[v].T).ravel() for v in ESTADO_C}
    return candidatos.predecir_c(modelo, filas, horas, estado_filas).reshape(n_p, n_h).T


# ---------------------------------------------------------------------------
# R de un candidato en un conjunto de puntos y un lote de horas
# ---------------------------------------------------------------------------
def correccion(candidato, hiper, puntos, lote_h, datos, *, umbrales, uso, fondo=None, estaticos=None, clima=None,
               celdas=None, entrenamiento=None, lote_puntos: int | None = None) -> dict:
    """R_<variable> (hora × punto, float64) del candidato en los ``puntos`` y las horas ``lote_h`` (un mes UTC), para
    las variables de ``hiper`` (PRO-1 a PRO-9). Sólo en memoria: R nunca se guarda ni se informa (§0.4.3).

    ``puntos``: {ids, lat, lon, z} (z en m). ``hiper``: {variable: θ} (PRO-3). ``uso``: el de los hiperparámetros
    (C_est sólo en lo crónico; C no en lo crónico). C usa ``fondo`` (T_F, Td_F, u_F y v_F, y ``amp_TF`` si se tiene,
    hora × punto) y ``estaticos`` (``ESQUEMA_ESTATICAS_CELDA_C``, una fila por punto); C_est usa ``clima``
    (``fondo_era5l.clima_en_puntos`` de los puntos) y ``estaticos``. ``celdas``: la celda de cada punto, con la que se
    cotejan los estáticos (por omisión, los ids: los puntos son celdas; en estaciones y píxeles, su celda; PRO-8).
    ``entrenamiento``: por omisión, todas las estaciones que no están excluidas (PRO-4)."""
    cand = _enumerado(Candidato, candidato)
    uso = _uso(cand, uso)
    if not isinstance(datos, tipos.DatosCompetencia):
        raise ErrorProducto("datos debe ser tipos.DatosCompetencia")
    h = _lote_de_horas(lote_h)
    ids, lat, lon, z = _puntos(puntos)
    n, n_h = lat.size, h.size
    theta = _hiperparametros(cand, hiper)
    codigos = _entrenamiento(datos, entrenamiento)
    tam = _tamano_lote(cand, lote_puntos)
    salida = {CLAVE_R[v]: np.full((n_h, n), np.nan) for v in theta}
    if n == 0:
        return salida
    if cand in DE_C:
        _correccion_c(cand, theta, h, datos, codigos, tam, salida, fondo=fondo, clima=clima,
                      estaticos=_estaticos_de_puntos(estaticos, n, _celdas_de_puntos(celdas, ids)), n=n)
    else:
        _correccion_nucleo(cand, theta, (ids, lat, lon, z), h, datos, codigos, tam, salida, umbrales)
    return salida


def _correccion_nucleo(cand: Candidato, theta: Mapping, pts: tuple, h: np.ndarray, datos, codigos: tuple, tam: int,
                       salida: dict, umbrales) -> None:
    """A, B y AB por lotes de puntos (PRO-5): los vecinos se arman una vez por lote y por hiperparámetros."""
    ids, lat, lon, z = pts
    infos = datos.estaciones
    entrenamiento = {c: infos[c] for c in codigos}
    clima_a, q = {}, {}
    for v in theta:
        if cand in (Candidato.A, Candidato.AB):
            clima_a[v] = datos.climatologias[datos.climatologias["variable"] == v]
        if cand in (Candidato.B, Candidato.AB):
            q[v] = candidatos.matriz_q(datos, codigos, cand, v, h, umbrales)        # hora × estación (codigos)
    for i0 in range(0, lat.size, tam):
        sl = slice(i0, min(lat.size, i0 + tam))
        lote = {"ids": ids[sl], "lat": lat[sl], "lon": lon[sl], "z": z[sl]}
        vecinos: dict = {}

        def vec(hp: Hiper):
            if hp not in vecinos:
                vecinos[hp] = candidatos.vecinos(lote, entrenamiento, hp, umbrales)
            return vecinos[hp]
        for v, t in theta.items():
            if cand is Candidato.A:
                r = candidatos.correccion_a(vec(t), clima_a[v], h)
            elif cand is Candidato.B:
                r = candidatos.correccion_b(vec(t), q[v], np.isfinite(q[v]))
            else:
                r = candidatos.correccion_ab(vec(t[0]), vec(t[1]), clima_a[v], q[v], np.isfinite(q[v]), h)
            salida[CLAVE_R[v]][:, sl] = r


def _correccion_c(cand: Candidato, theta: Mapping, h: np.ndarray, datos, codigos: tuple, tam: int, salida: dict, *,
                  fondo, estaticos, clima, n: int) -> None:
    """C y C_est por lotes de puntos (PRO-5 a PRO-8): un ajuste por variable con el entrenamiento y la predicción
    fila a fila (punto × hora) con ``candidatos.predecir_c``. ``estaticos`` ya viene cotejado por celda."""
    est = estaticos
    if cand is Candidato.C:
        F = _fondo_de_c(fondo, h.size, n)
    else:
        cubo = _clima_de_c_est(clima, n)
    modelos = {}
    for v, alfa in theta.items():
        try:
            filas = datos.filas_c[cand.value][v]
        except (KeyError, TypeError):
            raise ErrorProducto(f"datos.filas_c no trae {cand.value}/{v}") from None
        modelo = candidatos.ajustar_c(filas, codigos, alfa)
        # PRO-7: en C_est el estado ya llega llevado a las horas; el diseño es el mismo (§4.7).
        modelos[v] = dataclasses.replace(modelo, diseno=DisenoC.ESTADO) if cand is Candidato.C_EST else modelo
    for i0 in range(0, n, tam):
        sl = slice(i0, min(n, i0 + tam))
        if cand is Candidato.C:
            estado = _estado_c_lote(F, h, sl)
        else:
            estado = fondo_era5l.clima_en_horas({v: cubo[v][sl] for v in fondo_era5l.VARIABLES_CLIMA}, h)
        indices = np.arange(sl.start, sl.stop)
        for v in theta:
            salida[CLAVE_R[v]][:, sl] = _predecir_c_lote(modelos[v], est, indices, h, estado)


# ---------------------------------------------------------------------------
# Campos del producto (PRO-10)
# ---------------------------------------------------------------------------
def direccion_hacia(u, v) -> np.ndarray:
    """Dirección en grados de [0, 360), desde el norte en sentido horario, convención «hacia» (MC-28: el ángulo
    ``arctan2(u, v)`` de ``el_*``); 0 en calma; NaN si u o v no es finito (PRO-10)."""
    u, v = _f8(u), _f8(v)
    with np.errstate(invalid="ignore"):
        d = np.mod(np.degrees(np.arctan2(u, v)), _VUELTA_GRADOS)
        d = np.where(d >= _VUELTA_GRADOS, 0.0, d)                  # el redondeo de mód puede dar 360
    return np.where(np.isfinite(u) & np.isfinite(v), d, np.nan)


def campos(F: dict, R: dict) -> dict:
    """El producto (§3, §4.1): T, Td, u, v y p de ``fondo_era5l.producto_desde`` y sus derivadas HR (Magnus sobre agua,
    recortada en [0, 100]), rapidez y dirección (PRO-10). ``R`` trae exactamente R_T, R_Td, R_u, R_v y R_p."""
    if not isinstance(R, Mapping) or set(R) != set(fondo_era5l.CLAVES_R):
        claves = sorted(map(str, R)) if isinstance(R, Mapping) else type(R).__name__
        raise ErrorProducto(f"R trae {claves}; se esperan exactamente {list(fondo_era5l.CLAVES_R)}")
    prod = fondo_era5l.producto_desde(F, R)
    T, Td = prod[Variable.T.value], prod[Variable.TD.value]
    u, v = prod[Variable.U.value], prod[Variable.V.value]
    with np.errstate(invalid="ignore", over="ignore"):
        hr = np.clip(numerico.hr_desde(T, Td), *_HR_RECORTE)
    salida = {c: prod[c] for c in VARIABLES}
    salida[tipos.Derivada.HR.value] = hr
    salida[tipos.Derivada.RAPIDEZ.value] = np.hypot(u, v)
    salida[tipos.Derivada.DIRECCION.value] = direccion_hacia(u, v)
    return salida


def producto_mes(mes, op, puntos, ganador, hiper, datos, *, umbrales, uso, estaticos=None, clima_estado=None,
                 celdas=None, entrenamiento=None, lote_puntos: int | None = None) -> tuple[dict, dict]:
    """(campos, F) de un mes ERA5-Land (``fondo_era5l.MesE5L``) en los puntos del operador ``op``: F con
    ``fondo_era5l.campos_fondo`` y R del ganador de cada grupo que decide el uso (``ganador``: {grupo: candidato};
    ``hiper``: {variable: θ}); las variables de los grupos que el uso no decide quedan NaN (PRO-9). ``puntos`` son los
    del operador: los mismos ids, en el mismo orden, y la misma z (A10). Con C_est, ``clima_estado`` es la tabla
    ``ESQUEMA_CLIMA_ESTADO`` y el clima en los puntos se calcula aquí con ``op`` (PRO-7)."""
    uso = _enumerado(Uso, uso)
    if not isinstance(puntos, (pd.DataFrame, Mapping)) or "ids" not in puntos:
        raise ErrorProducto("producto_mes: los puntos traen sus «ids», para cotejarlos con los del operador (PRO-8)")
    ids, _, _, z = _puntos(puntos)
    if not isinstance(op, tipos.OperadorPuntos):
        raise ErrorProducto("op debe ser tipos.OperadorPuntos")
    ids_op = np.asarray(op.ids).ravel()
    if ids_op.shape != ids.shape or not bool(np.all(ids_op == ids)):
        raise ErrorProducto("los puntos y el operador deben tener los mismos ids, en el mismo orden (PRO-8)")
    z_op = _f8(op.z)
    if z_op.shape != z.shape or not np.array_equal(z_op, z, equal_nan=True):
        raise ErrorProducto("los puntos y el operador deben tener la misma z, en el mismo orden (A10)")
    grupos = _ganador(ganador, uso)
    if not isinstance(hiper, Mapping):
        raise ErrorProducto("hiper es {variable: hiperparámetros}")
    clima = None
    if Candidato.C_EST in grupos.values():
        if not isinstance(clima_estado, pd.DataFrame):
            raise ErrorProducto("C_est necesita la tabla ESQUEMA_CLIMA_ESTADO (clima_estado; PRO-7)")
        clima = fondo_era5l.clima_en_puntos(clima_estado, op, umbrales)
    F = fondo_era5l.campos_fondo(mes, op, umbrales)
    h = np.asarray(mes.tiempos, dtype=np.int64)
    R = {c: np.full(F["T_F"].shape, np.nan) for c in fondo_era5l.CLAVES_R}
    for grupo, cand in grupos.items():
        variables = VARIABLES_DE_GRUPO[grupo]
        faltan = [v for v in variables if v not in hiper]
        if faltan:
            raise ErrorProducto(f"hiper no trae {faltan} del grupo {grupo.value}")
        R.update(correccion(cand, {v: hiper[v] for v in variables}, puntos, h, datos, umbrales=umbrales, uso=uso,
                            fondo=F, estaticos=estaticos, clima=clima, celdas=celdas, entrenamiento=entrenamiento,
                            lote_puntos=lote_puntos))
    return campos(F, R), F


def _ganador(ganador, uso: Uso) -> dict[Grupo, Candidato]:
    """{grupo: candidato} con exactamente los grupos que decide el uso y candidatos del uso (§6.1; PRO-9, PRO-13)."""
    if not isinstance(ganador, Mapping):
        raise ErrorProducto("ganador es {grupo: candidato}")
    salida = {}
    for g, c in ganador.items():
        grupo, cand = _enumerado(Grupo, g), _enumerado(Candidato, c)
        if cand not in CANDIDATOS_DEL_USO[uso]:
            raise ErrorProducto(f"{cand.value} no es candidato de lo {uso.value} (§6.1)")
        salida[grupo] = cand
    esperados = GRUPOS_DEL_USO[uso]
    if set(salida) != set(esperados):
        raise ErrorProducto(f"lo {uso.value} decide los grupos {[g.value for g in esperados]}; ganador trae "
                            f"{sorted(g.value for g in salida)}")
    return {g: salida[g] for g in esperados}


# ---------------------------------------------------------------------------
# int16 (PRO-11)
# ---------------------------------------------------------------------------
def formato_int16(umbrales) -> tuple[dict[str, tuple[float, float]], int]:
    """({variable: (escala, desplazamiento)}, relleno) de la fila «Formato» del Anexo A (PRO-11)."""
    salida = {}
    for v, (id_escala, id_desp) in FORMATO_IDS.items():
        escala = float(umbrales.a(id_escala))
        desplazamiento = 0.0 if id_desp is None else float(umbrales.a(id_desp))
        if not (math.isfinite(escala) and escala > 0 and math.isfinite(desplazamiento)):
            raise ErrorProducto(f"formato de {v}: escala {escala!r} y desplazamiento {desplazamiento!r}")
        salida[v] = (escala, desplazamiento)
    relleno = umbrales.a(RELLENO_ID)
    if isinstance(relleno, bool) or not isinstance(relleno, (int, np.integer)) or not (_INT16.min <= relleno <= _INT16.max):
        raise ErrorProducto(f"{RELLENO_ID} debe ser un entero de int16: {relleno!r}")
    return salida, int(relleno)


def _claves_del_producto(datos: Mapping, nombre: str) -> None:
    if not isinstance(datos, Mapping):
        raise ErrorProducto(f"{nombre}: un diccionario {{variable: arreglo}}")
    ajenas = sorted(str(k) for k in datos if k not in VARIABLES and k not in DERIVADAS)
    if ajenas:
        raise ErrorProducto(f"{nombre}: claves que no son del producto {ajenas} (R nunca se guarda, §0.4.3)")
    faltan = [v for v in VARIABLES if v not in datos]
    if faltan:
        raise ErrorProducto(f"{nombre}: faltan {faltan}")


def codificar_int16(campos: dict, umbrales) -> dict:
    """{variable: int16} de T, Td, u, v y p (§8, PRO-11): NaN → relleno; un valor que no cabe es ``DesbordeInt16``.
    HR, rapidez y dirección no se codifican (se derivan al leer)."""
    _claves_del_producto(campos, "codificar_int16")
    formato, relleno = formato_int16(umbrales)
    salida = {}
    for v in VARIABLES:
        escala, desplazamiento = formato[v]
        x = _f8(campos[v])
        nan = np.isnan(x)
        with np.errstate(invalid="ignore", over="ignore"):
            k = np.rint((x - desplazamiento) / escala)
            cabe = (k >= _INT16.min) & (k <= _INT16.max) & (k != relleno)
        malos = ~nan & ~cabe
        if malos.any():
            bajo = desplazamiento + escala * (_INT16.min + (relleno == _INT16.min))
            alto = desplazamiento + escala * (_INT16.max - (relleno == _INT16.max))
            raise DesbordeInt16(f"{v}: {int(malos.sum())} valores no caben en int16 con escala {escala} y "
                                f"desplazamiento {desplazamiento} (rango representable {bajo:.2f} a {alto:.2f} "
                                f"{UNIDADES[v]}, relleno {relleno}); §8: no puede desbordar sin aviso")
        q = np.full(x.shape, relleno, dtype=np.int16)
        q[~nan] = k[~nan].astype(np.int16)
        salida[v] = q
    return salida


def decodificar_int16(enteros: dict, umbrales) -> dict:
    """{variable: float64} desde el int16 de §8: entero·escala + desplazamiento; el relleno vuelve a NaN (PRO-11)."""
    _claves_del_producto(enteros, "decodificar_int16")
    formato, relleno = formato_int16(umbrales)
    salida = {}
    for v in VARIABLES:
        e = np.asarray(enteros[v])
        if e.dtype != np.int16:
            raise ErrorProducto(f"decodificar_int16: {v} debe ser int16, no {e.dtype}")
        escala, desplazamiento = formato[v]
        x = e.astype(np.float64) * escala + desplazamiento
        x[e == relleno] = np.nan
        salida[v] = x
    return salida


# ---------------------------------------------------------------------------
# NetCDF mensual de 0,1° (PRO-12 a PRO-14)
# ---------------------------------------------------------------------------
def _huellas_validas(huellas) -> dict[str, str]:
    """PRO-14: al menos una; nombres sin rutas absolutas ni datos privados y sha256 en hexadecimal minúsculo."""
    if not isinstance(huellas, Mapping) or not huellas:
        raise ErrorProducto("mes_01deg exige al menos una huella (§8, «Cadena de huellas»)")
    salida = {}
    for nombre, sha in huellas.items():
        if not isinstance(nombre, str) or not nombre or nombre != nombre.strip():
            raise ErrorProducto(f"nombre de huella inválido: {nombre!r}")
        if nombre.startswith(("/", "~")) or "\\" in nombre or chr(64) in nombre or _CARPETA_USUARIOS in nombre \
                or ".." in nombre.split("/"):
            raise ErrorProducto("el nombre de una huella va por alias, sin rutas absolutas, «~», barra invertida, "
                                "arroba, carpeta de usuario ni segmentos «..» (PRO-14)")
        if not isinstance(sha, str) or _SHA256.fullmatch(sha) is None:
            raise ErrorProducto(f"la huella de {nombre!r} no es un sha256 en hexadecimal minúsculo")
        salida[nombre] = sha
    return salida


def _pixel_id(pixel_id) -> np.ndarray:
    pid = np.asarray(pixel_id)
    if pid.ndim != 1 or pid.size == 0 or pid.dtype == bool or not np.issubdtype(pid.dtype, np.integer):
        raise ErrorProducto("pixel_id: enteros, en un arreglo de una dimensión y no vacío")
    pid = pid.astype(np.int64)
    if pid.size > 1 and not bool(np.all(np.diff(pid) > 0)):
        raise ErrorProducto("pixel_id estrictamente creciente, sin repetir (el orden de pixeles_validos; PRO-12)")
    if pid.min() < 0:
        raise ErrorProducto("pixel_id negativo")
    return pid


def atributos_01deg(h, uso, ganador, huellas) -> dict[str, str]:
    """Los atributos globales del NetCDF de 0,1° (PRO-12 a PRO-14), en su orden."""
    uso = _enumerado(Uso, uso)
    if uso is not USO_01DEG:
        raise ErrorProducto(f"el producto de 0,1° es el del uso {USO_01DEG.value} (MC-08), no {uso.value}")
    grupos = _ganador(ganador, uso)
    attrs = {"esquema": ESQUEMA_01DEG, "mes": _mes_aaaamm(_lote_de_horas(h)), "uso": uso.value}
    attrs.update({f"ganador_{g.value}": c.value for g, c in grupos.items()})
    attrs["convencion_viento"] = CONVENCION_VIENTO
    attrs["huellas"] = json.dumps(_huellas_validas(huellas), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return attrs


def mes_01deg(campos: dict, pixel_id, h, umbrales, huellas: dict, *, uso, ganador) -> bytes:
    """Los bytes del NetCDF mensual de 0,1° (§8, MC-08, A19): ``time`` × ``pixel``, ``pixel_id`` y T, Td, u, v y p en
    int16 con ``scale_factor``, ``add_offset`` y ``_FillValue``; atributos con las huellas, el uso (ambiental) y el
    ganador de cada grupo. Se arma en memoria: sólo ``salidas`` escribe los bytes. ``campos``: hora × píxel (los de
    ``campos``; las derivadas no se guardan)."""
    horas = _lote_de_horas(h)
    pid = _pixel_id(pixel_id)
    attrs = atributos_01deg(horas, uso, ganador, huellas)
    _claves_del_producto(campos, "mes_01deg")
    for v in VARIABLES:
        _matriz(campos[v], (horas.size, pid.size), f"campos[{v!r}]")
    enteros = codificar_int16(campos, umbrales)
    formato, relleno = formato_int16(umbrales)
    netCDF4 = _netcdf4()
    tamano = sum(e.nbytes for e in enteros.values()) + pid.nbytes + horas.nbytes + _HOLGURA_NC
    ds = netCDF4.Dataset(_ETIQUETA_NC, mode="w", memory=int(tamano), format="NETCDF4")  # no-escribe: en memoria (A19)
    try:
        for nombre, valor in attrs.items():
            ds.setncattr(nombre, valor)
        ds.createDimension("time", horas.size)
        ds.createDimension("pixel", pid.size)
        vt = ds.createVariable("time", "i4", ("time",))
        vt.setncatts({"units": UNIDADES_TIEMPO, "calendar": CALENDARIO, "standard_name": "time"})
        vt[:] = horas.astype(np.int32)
        vp = ds.createVariable("pixel_id", "i8", ("pixel",))
        vp.long_name = "identificador del píxel de 0,1° del catálogo"
        vp[:] = pid
        for v in VARIABLES:
            escala, desplazamiento = formato[v]
            var = ds.createVariable(v, "i2", ("time", "pixel"), fill_value=np.int16(relleno))
            var.setncatts({"units": UNIDADES[v], "long_name": NOMBRES_LARGOS[v], "scale_factor": np.float64(escala),
                           "add_offset": np.float64(desplazamiento)})
            var.set_auto_maskandscale(False)
            var[:] = enteros[v]
    except BaseException:
        ds.close()
        raise
    return bytes(ds.close())


# ---------------------------------------------------------------------------
# Finitud de E0 (PRO-15)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ConteoFinito:
    """Puntos-hora con fondo y, entre ellos, con el producto finito (MC-51, A21). Se suman entre lotes con «+»."""
    n_puntos_hora: int = 0
    n_finitos: int = 0

    def __post_init__(self) -> None:
        for nombre in ("n_puntos_hora", "n_finitos"):
            x = getattr(self, nombre)
            if isinstance(x, bool) or not isinstance(x, int) or x < 0:
                raise ErrorProducto(f"ConteoFinito.{nombre} es un entero ≥ 0: {x!r}")
        if self.n_finitos > self.n_puntos_hora:
            raise ErrorProducto("ConteoFinito: más finitos que puntos-hora con fondo")

    def __add__(self, otro: "ConteoFinito") -> "ConteoFinito":
        if not isinstance(otro, ConteoFinito):
            return NotImplemented
        return ConteoFinito(self.n_puntos_hora + otro.n_puntos_hora, self.n_finitos + otro.n_finitos)

    @property
    def fraccion(self) -> float:
        """La fracción finita; NaN sin puntos-hora con fondo."""
        return self.n_finitos / self.n_puntos_hora if self.n_puntos_hora else float("nan")

    def pasa(self) -> bool:
        """E0 (§6.2, paso 1): finito en ≥ ``E0_FINITO_PCT`` % de los puntos-hora con fondo, en enteros (PRO-15)."""
        if self.n_puntos_hora == 0:
            raise ErrorProducto("finitud de E0 sin ningún punto-hora con fondo: no hay decisión posible (PRO-15)")
        return _PORCENTAJE * self.n_finitos >= _E0_PCT * self.n_puntos_hora

    def como_dict(self) -> dict:
        return {"n_puntos_hora": self.n_puntos_hora, "n_finitos": self.n_finitos, "fraccion": self.fraccion}


def sumar_conteos(conteos) -> ConteoFinito:
    """La suma de los conteos de varios lotes (en el orden dado; son enteros, así que el orden no cambia nada)."""
    total = ConteoFinito()
    for c in conteos:
        if not isinstance(c, ConteoFinito):
            raise ErrorProducto("sumar_conteos: sólo ConteoFinito")
        total = total + c
    return total


def hay_fondo(F: Mapping, *, variables=None, grupo=None) -> np.ndarray:
    """``con_fondo`` (hora × punto) desde el fondo: los campos de F de todas las variables del grupo son finitos
    (PRO-15). Se da ``variables`` o ``grupo``, uno de los dos."""
    variables = _variables_o_grupo(variables, grupo)
    if not isinstance(F, Mapping):
        raise ErrorProducto("hay_fondo: F es el diccionario de campos_fondo")
    faltan = [CAMPO_F[v] for v in variables if CAMPO_F[v] not in F]
    if faltan:
        raise ErrorProducto(f"hay_fondo: faltan {faltan}")
    arreglos = [_f8(F[CAMPO_F[v]]) for v in variables]
    if len({a.shape for a in arreglos}) != 1:
        raise ErrorProducto("hay_fondo: campos del fondo con formas distintas")
    salida = np.ones(arreglos[0].shape, dtype=bool)
    for a in arreglos:
        salida &= np.isfinite(a)
    return salida


def _variables_o_grupo(variables, grupo) -> tuple[str, ...]:
    """PRO-15: las variables de la finitud, dadas por ``variables`` o por ``grupo`` (uno de los dos, sin omisión)."""
    if (variables is None) == (grupo is None):
        raise ErrorProducto("la finitud se mide en las variables de un grupo: se da «variables» o «grupo», uno de los dos")
    if grupo is not None:
        return VARIABLES_DE_GRUPO[_enumerado(Grupo, grupo)]
    return _variables_de(variables)


def _variables_de(variables) -> tuple[str, ...]:
    if isinstance(variables, str):
        variables = (variables,)
    try:
        salida = tuple(Variable(v).value for v in variables)
    except (ValueError, TypeError):
        raise ErrorProducto(f"variables del producto desconocidas: {variables!r}") from None
    if not salida or len(set(salida)) != len(salida):
        raise ErrorProducto("variables: al menos una y sin repetir")
    return salida


def conteo_finito(campos: Mapping, con_fondo, *, variables=None, grupo=None) -> ConteoFinito:
    """Los puntos-hora con fondo y, entre ellos, los que tienen finitas todas las variables del grupo (``variables`` o
    ``grupo``, uno de los dos): MC-51, A21, PRO-15. ``con_fondo``: bool hora × punto, o uno por punto."""
    if not isinstance(campos, Mapping):
        raise ErrorProducto("conteo_finito: campos es {variable: arreglo}")
    variables = _variables_o_grupo(variables, grupo)
    faltan = [v for v in variables if v not in campos]
    if faltan:
        raise ErrorProducto(f"conteo_finito: faltan {faltan}")
    arreglos = [_f8(campos[v]) for v in variables]
    forma = arreglos[0].shape
    if any(a.shape != forma for a in arreglos) or len(forma) != 2:
        raise ErrorProducto("conteo_finito: las variables son hora × punto, con la misma forma")
    finito = np.ones(forma, dtype=bool)
    for a in arreglos:
        finito &= np.isfinite(a)
    return _conteo(finito, con_fondo)


def _conteo(finito: np.ndarray, con_fondo) -> ConteoFinito:
    """El conteo de los puntos-hora con fondo y, entre ellos, los finitos (``finito``: hora × punto)."""
    forma = finito.shape
    mascara = np.asarray(con_fondo)
    if mascara.dtype != bool:
        raise ErrorProducto("con_fondo es booleano")
    if mascara.shape == forma[1:]:
        mascara = np.broadcast_to(mascara[None, :], forma)
    elif mascara.shape != forma:
        raise ErrorProducto(f"con_fondo: forma {mascara.shape}; se espera {forma} o {forma[1:]}")
    return ConteoFinito(int(np.count_nonzero(mascara)), int(np.count_nonzero(mascara & finito)))


def fraccion_finita(campos: dict, con_fondo, *, variables=None, grupo=None) -> float:
    """La fracción de los puntos-hora con fondo en que el producto es finito (MC-51; NaN sin ninguno). Para sumar
    lotes, ``conteo_finito`` y ``sumar_conteos`` (A21)."""
    return conteo_finito(campos, con_fondo, variables=variables, grupo=grupo).fraccion


def pasa_e0(conteos: Mapping[str, ConteoFinito]) -> bool:
    """E0 por finitud con cada conjunto por separado (N1, la lectura más estricta): por ejemplo {«celdas pobladas»:
    …, «estaciones de validación»: …}; pasa sólo si cada fracción es ≥ ``E0_FINITO_PCT`` % (PRO-15)."""
    if not isinstance(conteos, Mapping) or not conteos:
        raise ErrorProducto("pasa_e0: {conjunto: ConteoFinito}, con al menos un conjunto")
    if not all(isinstance(c, ConteoFinito) for c in conteos.values()):
        raise ErrorProducto("pasa_e0: sólo ConteoFinito")
    return all([c.pasa() for c in conteos.values()])          # todos se evalúan: uno sin puntos es un error


def conteo_finito_c(candidato, puntos, lote_h, con_fondo, *, estaticos, fondo=None, clima=None, celdas=None,
                    lote_puntos: int | None = None) -> ConteoFinito:
    """La finitud de E0 de C o C_est sin calcular R (PRO-18): un punto-hora con fondo es finito si los estáticos del
    punto lo son (el TPI truncado cuenta como finito, vale 0) y su estado también (C: T_F, T_F − Td_F, rapidez y
    amplitud desde ``fondo``; C_est: el clima llevado a la hora). Es lo que decide si ``candidatos.predecir_c`` da un
    valor finito, porque los armónicos del tiempo siempre lo son; ``test_producto`` lo compara con ``correccion`` +
    ``campos`` + ``conteo_finito``. ``con_fondo`` es el del grupo (``hay_fondo``)."""
    cand = _enumerado(Candidato, candidato)
    if cand not in DE_C:
        raise ErrorProducto(f"conteo_finito_c es de C y C_est; {cand.value} necesita su R (conteo_finito)")
    h = _lote_de_horas(lote_h)
    ids, lat, _, _ = _puntos(puntos)
    n = lat.size
    est = _estaticos_de_puntos(estaticos, n, _celdas_de_puntos(celdas, ids))
    tam = _tamano_lote(cand, lote_puntos) * h.size        # filas por lote: las mismas que en la predicción
    if cand is Candidato.C:
        F = _fondo_de_c(fondo, h.size, n)
    else:
        cubo = _clima_de_c_est(clima, n)
    estaticos_ok = np.zeros(n, dtype=bool)
    cero = np.zeros(1, dtype=np.int64)
    for i0 in range(0, n, tam):
        sl = slice(i0, min(n, i0 + tam))
        m = sl.stop - sl.start
        neutro = {v: np.zeros(m) for v in ESTADO_C}            # estado finito: sólo miran los estáticos
        X = candidatos.diseno_c(est.iloc[sl], np.repeat(cero, m), neutro)
        estaticos_ok[sl] = np.isfinite(X).all(axis=1)
    finito = np.zeros((h.size, n), dtype=bool)
    paso = LOTE_PUNTOS_NUCLEO                                  # el estado no arma filas: lotes más grandes
    for i0 in range(0, n, paso):
        sl = slice(i0, min(n, i0 + paso))
        if cand is Candidato.C:
            estado = _estado_c_lote(F, h, sl)
        else:
            estado = fondo_era5l.clima_en_horas({v: cubo[v][sl] for v in fondo_era5l.VARIABLES_CLIMA}, h)
        ok = np.ones((h.size, sl.stop - sl.start), dtype=bool)
        for v in ESTADO_C:
            ok &= np.isfinite(estado[v])
        finito[:, sl] = ok & estaticos_ok[None, sl]
    return _conteo(finito, con_fondo)


__all__ = (
    "CANDIDATOS_DEL_USO", "CLAVE_R", "ConteoFinito", "DesbordeInt16", "ErrorProducto", "FORMATO_IDS",
    "GRUPOS_DEL_USO", "LOTE_PUNTOS_C", "LOTE_PUNTOS_NUCLEO", "VARIABLES_DE_GRUPO", "atributos_01deg", "campos",
    "codificar_int16", "conteo_finito", "correccion", "decodificar_int16", "direccion_hacia", "estado_c_puntos",
    "conteo_finito_c", "formato_int16", "fraccion_finita", "hay_fondo", "mes_01deg", "pasa_e0", "producto_mes",
    "sumar_conteos",
)
