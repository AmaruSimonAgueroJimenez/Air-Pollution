"""Meteorología para salud (§3, §7.2, §7.3; S8 y S14 de §9): días, medias comunales, lluvia, representatividad y crónico.

Este módulo es puro para la producción: recibe arreglos y tablas y devuelve tablas o conjuntos; no escribe nada (§0, regla
8 del diseño). La única función que lee archivos es ``regresion_s14`` (S14, MC-31), que abre en sólo lectura las rutas que
nombra ``insumos_s14`` y calcula la huella de cada una con ``open`` de Python antes de pasar sus bytes a netCDF4 o pyarrow
(CEG-5); no guarda el producto (§0.4.1) y sólo informa «igual» o «distinto» y la diferencia máxima.

Qué hace cada función:
- ``dias`` y ``horas_esperadas``: el día civil de una zona IANA (23, 24 o 25 horas) o el día UTC−4 fijo (``zona=None``),
  como ``exposicion_horaria_v3.dias_de_horas`` y ``horas_esperadas``. ``zonas_por_comuna``: la zona regional de cada
  comuna, como ``exposicion_horaria_v3.zonas_por_comuna``. ``dias_del_anio``: las filas de ``meteo_civil_v3``.
- ``pesos_comuna``: la matriz dispersa comuna × celda con w_ghs del año (§7.2, punto 1). ``pesos_lluvia``: los pares
  comuna × píxel de ``meteo_civil_v3.construir_pesos`` (MC-13).
- ``lluvia_horaria`` y ``lluvia_comunal``: la lluvia de ``meteo_civil_v3``, bit a bit (MC-13).
- ``AcumuladorMeteo`` y ``meteo_comunal``: T, Td y HR del producto en las celdas, por día y comuna, con el esquema de
  ``meteo_civil_v3`` (``tipos.ESQUEMA_METEO_DIARIA``), por lotes de celdas y, si se quiere, por tramos de horas
  (SAL-13). ``metadatos_tabla``: los atributos de una tabla diaria que van en sus metadatos al escribirla (SAL-10).
- ``representatividad``: la lista de estaciones excluidas de §7.2, punto 6 (MC-52).
- ``cronico_anual``: ``temp_media_anual`` y ``temp_media_fria`` de §7.3 (``tipos.ESQUEMA_CRONICO``).
- ``insumos_s14`` y ``regresion_s14``: S14 (MC-12, MC-31, MC-32).

Dueño: I18 (ola 5).
Lecturas propias (SAL-n), para el addendum de M1 (cita, lectura y motivo):
- SAL-1. **Horas y días** (§3; §2.1 del diseño). Las horas son ``h`` (horas UTC desde 2000-01-01T00Z, enteras y
  estrictamente crecientes). ``dia`` es el número de días desde 1970-01-01 (int32), el de ``meteo_civil_v3`` y de
  ``exposicion_horaria_v3`` (su ``fecha`` date32 es ese mismo número), no ``d2000``: así el esquema es idéntico al de
  ``meteo_civil_v3`` (S8). Motivo: §2.3 del diseño copia ese esquema por AST.
- SAL-2. **Día civil** (§3: «el día civil de America/Santiago con 23, 24 o 25 horas, como ``exposicion_horaria_v3``»). La
  fecha de una hora es la del intervalo [medianoche local, medianoche local siguiente) que la contiene, con las
  medianoches de ``exposicion_horaria_v3.limites_civiles`` (``datetime(…, tzinfo=zona)``, ``fold=0``: una medianoche
  que no existe cae en el instante del cambio). Es, hora por hora, la fecha de ``astimezone`` que usa
  ``dias_de_horas`` (``test_salud`` lo comprueba en 2000-2026 con las tres zonas). ``horas_esperadas`` es la duración de
  ese intervalo; con ``zona=None`` (UTC−4 fijo) siempre 24. La base de zonas es sólo la del paquete tzdata
  (``zoneinfo.TZPATH`` vacío, como VAL-3; ``reloj_dmc.entorno`` la fija al importarse): si no, ``RuntimeError``.
- SAL-3. **Día UTC−4** (§3: «Las sensibilidades usan el día UTC−4»). La fecha de (h − 4 h), como
  ``meteo_civil_v3.dias_utc4`` (``DESFASE_UTC4_H`` = 4, el mismo valor que ``sinca_meteo.DESFASE_FIJO_H``; las pruebas lo
  comparan con los dos). Es un literal marcado «no-umbral» porque ``constantes`` no lo trae (PED-2).
- SAL-4. **Zona regional** (§3: «la zona regional»; ``exposicion_horaria_v3.zonas_por_comuna``). Región = ``cod_comuna
  // 1000``; la 11 con America/Coyhaique, la 12 con America/Punta_Arenas y el resto con America/Santiago
  (``ZONAS_REGIONALES``, copiado; la prueba lo compara por AST con ``exposicion_horaria_v3``, 2eef68b3…).
- SAL-5. **Filas** (§7.2, punto 1: «con el esquema y las reglas de días de ``meteo_civil_v3``»). Las filas de las tres
  carpetas son las mismas: cada comuna × los días UTC−4 del año con al menos una hora en la serie (``dias_del_anio``;
  ``meteo_civil_v3``: «Las filas de los tres productos son las mismas»). ``n_horas`` cuenta las horas de la serie que
  caen en el día (con o sin dato), ``n_horas_esperadas`` es la duración del día en su zona y ``faltan_horas`` =
  ``n_horas < n_horas_esperadas``; un día con más horas que su duración es un error. Las horas de los días pedidos
  deben ser contiguas en la serie (``meteo_civil_v3.segmentos``).
- SAL-6. **Celdas y pesos de T, Td y HR** (§7.2, punto 1: «en las celdas de ≈ 1 km con ``cod_comuna > 0``, w_ghs > 0 y
  producto finito, con los pesos de la exposición»). ``pesos_comuna`` toma las celdas que le pasa quien llama (las que
  tienen producto: en S14, las que tienen enlace; en M5, las que tienen fondo) con ``cod_comuna > 0`` y w_ghs finito y
  > 0 de ``poblacion_celda_anio.parquet`` del año. El año de los pesos es el del producto, llevado al rango de años de la
  tabla (2026 usa 2025, como ``exposicion_horaria_v3.anio_pesos``). La comuna es la de la grilla (``celdas``); si la
  tabla trae ``cod_comuna`` y no coincide, es un error. «Producto finito» se aplica hora a hora y día a día como en
  ``meteo_civil_v3``: la media, la mínima y la máxima de un día de una celda usan sus horas con dato; una celda sin
  ningún dato en el día no pesa ese día y el peso se renormaliza sobre las demás; una comuna sin ninguna celda con dato
  queda en NaN. La mínima y la máxima comunales son la media ponderada de las mínimas y máximas de las celdas (como el
  panel v1 y ``meteo_civil_v3``). La HR es la del producto (``HR`` de ``producto.campos``) o, si no viene, Magnus sobre
  agua desde T y Td, recortada en [0, 100] (§3; ``numerico.hr_desde``). Las sumas van en float64, por lotes de celdas
  en el orden en que llegan (MC-37): el mismo orden da los mismos bits, también por tramos de horas (SAL-13).
- SAL-7. **Lluvia** (MC-13, aceptada en D5). ``precip_mm`` sale exactamente como en ``meteo_civil_v3``: los pares
  comuna × píxel del enlace celda → píxel de ``enlaces_productos.parquet`` (celdas con ``cod_comuna > 0`` y píxel ≥ 0;
  w_ghs con ``nan_to_num`` y recorte en 0; una comuna sin población en sus celdas enlazadas pesa por área), la lluvia
  horaria de ``lluvia_horaria``, la suma del día por píxel con ``_suma`` y la media comunal con ``ponderar``, con las
  mismas operaciones en el mismo orden (``test_salud`` lo compara bit a bit con el código de ``meteo_civil_v3`` leído por
  AST). La regional copia la regla de ``calcular_anio``: la civil de America/Santiago, salvo en las comunas de una zona
  cuyos días difieren de los de Santiago. La diferencia de soporte entre la lluvia (celdas con enlace) y T, Td y HR
  (celdas con producto) es la que declara MC-13.
- SAL-8. **Comunas de la tabla.** Las de los pesos de T más las de la lluvia (unión), en orden: una comuna sin celdas con
  producto queda con T, Td y HR en NaN, y una sin enlace, con la lluvia en NaN. En S14 los dos conjuntos coinciden.
- SAL-9. **Representatividad** (§7.2, punto 6; MC-52). Por estación, sobre todo su período con horas válidas: las horas
  emparejadas son las que tienen observación válida de T y t2m finita en el píxel del reloj (que elige quien llama,
  A27). La «correlación de medias diarias» es la de Pearson entre las medias del día civil de America/Santiago de la
  observación y de t2m en esas mismas horas, sobre los días civiles válidos de §5.2 (≥ ``DIA_MIN_H`` horas emparejadas
  y hueco circular ≤ ``DIA_HUECO_H``; «La media del día del producto se toma en las mismas horas que la observación»).
  El cociente es el de las amplitudes (máximo menos mínimo) de los ciclos diarios medios por hora UTC de las horas
  emparejadas, observación sobre píxel (MC-52; el intervalo [0,5; 2] es simétrico, así que el orden no cambia nada).
  Se excluye la estación con r < 0,8 o con el cociente fuera de [0,5; 2] (bordes incluidos en el intervalo), y también
  la que no permite calcularlos (sin dos días válidos, sin varianza, con menos de dos horas UTC o con amplitud nula del
  píxel): la lectura más estricta, porque la sensibilidad deja fuera lo que no muestra ser representativo (pregunta
  P-SAU-1). Las correlaciones y cocientes no salen de la función (§0.4.6): sólo el conjunto de códigos. Los días
  válidos son los de ``validacion.dias_validos`` (VAL-3; ``test_salud`` los compara en series al azar y en los bordes),
  y el día por omisión es el civil (``zona=None`` da el UTC−4, sólo si quien llama lo pide).
- SAL-10. **Crónico** (§7.3). ``temp_media_anual`` es la media de ``temp_media`` de los días civiles del año de la comuna
  y ``temp_media_fria`` la de abril a septiembre (los meses de la fecha civil), con los días que tienen valor (como
  ``covariables.clima``, que promedia las medias diarias del panel). «Con los pesos w_ghs de cada año»: cada tabla diaria
  se arma con los pesos de su año, y ``cronico_anual`` lo comprueba con la huella de esos pesos (``pesos_sha256`` en
  los atributos de la tabla) frente a ``pesos_por_anio``. Los atributos (``CLAVES_METADATOS``: ``tipo_dia``, ``anio``,
  ``anio_pesos``, ``pesos_sha256`` y ``anio_pesos_lluvia``) se buscan en ``attrs`` y, en una tabla releída de un parquet
  de ``salidas`` (que sólo guarda ``attrs["esquema"]`` y ``attrs["metadatos"]``, SLD-4), en ``attrs["metadatos"]``:
  así una M5 reanudada que relee los días civiles de disco puede armar lo crónico. Una clave que está en los dos
  lugares con valores distintos es un error. ``metadatos_tabla`` da lo que se pasa como ``metadatos=`` a
  ``salidas.escribir``. Los meses son un literal marcado (PED-2). ``td_media_anual`` y ``hr_media_anual`` no se
  calculan: el DISENO v3 no las pide todavía y ``ESQUEMA_CRONICO`` no las trae. Un año incompleto se promedia con los
  días que trae (pregunta P-SAU-4).
- SAL-11. **S14** (§9; MC-12, MC-31, MC-32). «Con corrección 0, z_x = z del píxel enlazado (sin Γ, sin ajuste de Td ni de
  p y sin el recorte Td ≤ T de §4.1)»: el operador de cada celda tiene un solo vecino, su píxel de
  ``enlaces_productos.parquet``, con peso 1 y Δz = 0 (``fondo_era5l.operador_desde_columnas`` con z_x = z_i = 0: con Δz = 0
  el valor de z no entra en ninguna cuenta, así que no se lee z_E5L), y el fondo es ``fondo_era5l.campos_fondo(…,
  recortar_td=False)``; no pasa por ``producto.campos``, que vuelve a recortar Td (PRO-10). La corrección 0 es no
  sumar nada. El lector por celda es este módulo (MC-12), por lotes de ``LOTE_CELDAS_S14`` celdas, con los meses del año
  y el enero siguiente (``meteo_civil_v3.archivos_anio``), que llegan al acumulador mes a mes (SAL-13), como en M5; las
  carpetas son las de ``confusores.meteorologia_productos`` de ``config_v3.json`` (su alias LOCAL es la carpeta superior
  de la de este texto, ENT-3), y cada una debe ser V3/<tipo> (si no, error). Se compara la serie entera del año
  (MC-32): mismas filas, mismos ``n_horas``, ``n_horas_esperadas`` y ``faltan_horas``, NaN en las mismas posiciones y
  |diferencia| ≤ 1e-9 en las seis variables, cada carpeta por su cuenta («igual» sólo si las tres lo son). Sólo
  informa «igual» o «distinto», la diferencia máxima y, si es «distinto», el motivo sin números; y las huellas de lo que
  leyó (pregunta P-SAU-5). Calcula la sha256 de cada ``meteo_<año>.parquet`` pero no la compara con nada fijado, ni
  rehace la huella de la carpeta entera que fija ``config_v3.json`` (pregunta P-SAU-3). **Td con p sin dato.** Con
  Δz = 0, ``campos_fondo`` toma Td_F = d2m − 273,15 sólo donde p_F es finita; en una hora en que el píxel trae d2m pero
  no sp (o no t2m), Td_F y la HR quedan sin dato, y la v3, que no usa sp, sí los tiene. S14 no lo arregla: lo informa
  «distinto», con el motivo ``MOTIVO_TD_SIN_DATO`` (pregunta P-SAU-2; PED-3). En 2024 real no ocurre (S14 da
  «igual»).
- SAL-12. **El fondo llega por ``producto``** (§1 del diseño). ``salud`` no puede importar ``fondo_era5l`` (no está en su
  «Depende de» ni en ``DEPENDENCIAS`` de ``test_meteo_combinada``, que lo detectaría), y S14 lo necesita
  (``leer_mes``, ``horas_de``, ``MesE5L``, ``operador_desde_columnas`` y ``campos_fondo``): lo usa como
  ``producto.fondo_era5l``, el módulo que ``producto`` ya importa, y ``_fondo`` comprueba que es
  ``meteo_combinada.fondo_era5l``. **Es una dependencia que el lector AST del grafo no ve** (llega por ``getattr``):
  queda declarada aquí y en «Depende de», y PED-1 pide agregarla al grafo para importarla directamente.
- SAL-13. **El acumulador por tramos de horas** (PED-8 de I20; MC-37). ``AcumuladorMeteo.agregar(campos, celdas,
  horas=…)`` recibe un tramo contiguo de las horas del acumulador (un mes, por ejemplo) para un lote de celdas: el
  primer tramo de cada lote empieza en la primera hora de la serie y cada uno sigue al anterior, sin huecos ni
  repeticiones, con las mismas celdas en el mismo orden. Cada día se agrega cuando llegaron todas sus horas; las de un
  día que cruza el corte se guardan para ese lote hasta el tramo siguiente (a lo más un día por zona), así que no hace
  falta tener todos los meses del año en memoria. Cada día usa las mismas horas, en el mismo orden y con las mismas
  operaciones que con la serie entera, y su suma por comuna se hace lote a lote; por eso, con los mismos lotes en el
  mismo orden, el resultado es bit a bit el de pasar la serie entera de una vez (``test_salud`` lo comprueba con cortes
  al azar y en los cambios de hora). Un lote que completa un día antes que otro aparecido antes que él cambiaría ese
  orden: es un error, que se detecta en ese tramo y antes de sumar nada. Sin ``horas``, el lote trae la serie entera,
  como antes.

Preguntas para el autor (P-SAU-n; las P-SAL-n son de ``salidas``). Mientras no responda, rige lo que dice cada una.
- P-SAU-1. **La estación sin r o sin cociente calculables** (SAL-9). Rige: se excluye (la lectura más estricta).
  Alternativa: se conserva.
- P-SAU-2. **Td del fondo cuando falta sp o t2m y d2m tiene dato** (SAL-11). §9, S14: «sin ajuste de Td». Rige: S14 usa
  ``campos_fondo`` tal cual, la misma cuenta que M5, y lo informa «distinto» con su motivo. Alternativa: que S14 tome
  Td = d2m − 273,15 directamente (es literalmente «sin ajuste de Td»), pero entonces S14 dejaría de probar el Td_F que
  usará M5. Lo de fondo es de ``fondo_era5l`` (PED-3). En 2024 real no ocurre.
- P-SAU-3. **La huella de la carpeta entera** (SAL-11). ``config_v3.json`` fija la ``sha256`` de cada carpeta de
  ``meteorologia_productos`` (la regla de ``exposicion_horaria_v3.huella_lista``: las líneas ordenadas «ruta\\0sha256»
  de todos sus archivos), y rehacerla exige las sha256 de todos los años de la carpeta, no sólo del de S14.
  Propuesta: agregar a los insumos de S14 el JSON de verificación de la v3 (``meteo_reproduccion_y_dia_civil.json``,
  cuyas ``huellas`` traen la sha256 por archivo de cada carpeta), con su huella fijada; rehacer con él la huella de la
  carpeta y compararla con la de ``config_v3.json``, y comparar la de ``meteo_<año>.parquet`` con su entrada.
  Alternativa: declararlo (S14 informa la sha256 de cada ``meteo_<año>.parquet`` y el addendum la coteja con ese
  JSON). Rige: se declara; los insumos de S14 (MC-31) no se amplían sin respuesta.
- P-SAU-4. **Lo crónico de un año incompleto** (SAL-10; ERA5-Land llega a 2026-09-15). Propuesta: sólo años completos
  (todos los días civiles del año). Rige hoy: ``cronico_anual`` promedia los días que trae la tabla y no exige el año
  completo; M5 decide qué años le pasa.
- P-SAU-5. **Qué informa S14.** §9: «Sólo informa «igual» o «distinto» y la diferencia máxima». Lectura: además, el
  motivo sin números de un «distinto» y las sha256 de lo que leyó (procedencia, no métricas). Rige esa lectura.
- P-SAU-6. **``dia`` int32 frente a ``fecha`` date32** (SAL-1). Las tablas de salud llevan ``dia`` (int32, días desde
  1970-01-01), el esquema de ``meteo_civil_v3`` en memoria (``ESQUEMA_DIARIO``, S8); los parquet v3 llevan ``fecha``
  date32 (``a_arrow``), y S14 los compara convirtiendo ``fecha`` en ``dia`` como ``leer_tabla``. Rige: los parquet de
  M5 llevan ``dia`` int32 (``ESQUEMA_METEO_DIARIA``); el adaptador de la Enmienda 4 (MC-12) haría la conversión.
  Alternativa: escribir ``fecha`` date32, como los v3.

Pedidos (PED-n):
- PED-1 (coordinador; H7). Agregar ``fondo_era5l`` a las dependencias de ``salud`` (§1 del diseño y ``DEPENDENCIAS`` de
  ``test_meteo_combinada``; capa 2 frente a 5, sin ciclos), para importarlo directamente y no por ``producto``
  (SAL-12).
- PED-2 (I2, ``constantes``). ``DESFASE_UTC4_H`` (el «UTC−4» de §3) y los meses fríos («abril a septiembre», §7.3) en
  ``constantes``, con su fragmento literal; hoy son literales marcados (SAL-3, SAL-10).
- PED-3 (I7, ``fondo_era5l``; H5). Con Δz = 0, que la identidad Td_F = d2m − 273,15 no exija p finita
  (``campos_fondo``: hoy ``identidad = (dz == 0) & isfinite(p_x) & isfinite(td_i)``), como en la v3; o declarar que
  una hora sin sp (o sin t2m) deja Td_F sin dato (SAL-11, P-SAU-2).
Avisos para I20 (``orquestacion``): escribir las tablas diarias con ``metadatos=salud.metadatos_tabla(tabla)``
(SAL-10), y pasar las horas por meses con ``agregar(…, horas=mes.tiempos)`` (SAL-13).
Depende de: tipos, constantes, umbrales, numerico, fijados, producto y, a través de ``producto``, ``fondo_era5l``
(SAL-12, PED-1). Los umbrales llegan como objeto (``.a``), así que ``umbrales`` no hace falta importarlo.
"""
from __future__ import annotations

import hashlib
import json
import zoneinfo
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from scipy import sparse

from meteo_combinada import constantes, fijados, numerico, producto, tipos

# ---------------------------------------------------------------------------
# Nombres y constantes
# ---------------------------------------------------------------------------
TIPOS_DIA = ("civil", "utc4", "regional")             # las carpetas de §2.3 del diseño y de config_v3.json
ESQUEMA = tipos.ESQUEMA_METEO_DIARIA
VARIABLES = ("temp_media", "temp_min", "temp_max", "hr_media", "td_media", "precip_mm")   # meteo_civil_v3.VARIABLES
VARIABLES_CAMPO = VARIABLES[:-1]                      # las que salen del producto en las celdas (SAL-6)
CAMPOS = ("T", "Td", "HR")
ZONA_BASE = tipos.ZONA_CIVIL                          # America/Santiago
ZONAS_REGIONALES: Mapping[int, str] = MappingProxyType(
    {11: "America/Coyhaique", 12: "America/Punta_Arenas"})   # no-umbral: regiones (CUT) de exposicion_horaria_v3
DIVISOR_REGION = 1000                                  # región = cod_comuna // 1000 (SAL-4)
DESFASE_UTC4_H = 4                                     # no-umbral: el «UTC−4» de §3 (SAL-3; meteo_civil_v3.DESFASE_UTC4_H)
MESES_FRIOS = (4, 9)                                   # no-umbral: «abril a septiembre» de §7.3 (SAL-10; PED-2)
HORAS_DIA = tuple(int(x) for x in constantes.valor("DIA_CIVIL_HORAS"))     # (23, 24, 25), §3
HORAS_UTC4 = HORAS_DIA[1]                              # 24: el reloj fijo no cambia de hora
_HR_MIN, _HR_MAX = (float(x) for x in constantes.valor("HR_PRODUCTO_RECORTE"))
_R_MIN = float(constantes.valor("REPRES_CORRELACION_MIN"))            # 0,8 (§7.2, punto 6)
_COCIENTE_MIN, _COCIENTE_MAX = (float(x) for x in constantes.valor("REPRES_COCIENTE"))   # [0,5; 2]
_TOL_S14 = float(constantes.valor("S14_TOLERANCIA"))                   # 1e-9 (§9, S14)
_N_VECINOS = int(constantes.valor("FONDO_VECINOS"))                    # 4 casillas del operador (§4.1)

_EPOCA_H = np.datetime64(tipos.EPOCA_H[:13], "h")                      # 2000-01-01T00 (h = 0)
_UNIX_D = np.datetime64("1970-01-01", "D")
_DIAS_UNIX_2000 = int((_EPOCA_H.astype("datetime64[D]") - _UNIX_D).astype(np.int64))   # días de 1970 a 2000
_SEGUNDOS_H = 3600
_S_UNIX_2000 = _DIAS_UNIX_2000 * HORAS_UTC4 * _SEGUNDOS_H
_ORDINAL_1970 = date(1970, 1, 1).toordinal()          # no-umbral: origen de ``dia`` (SAL-1), el EPOCA de la v3
_MARGEN_DIAS = 2                                       # días de holgura al buscar la fecha local de una hora
LOTE_PIXELES = 1024                                    # no-umbral: píxeles por lote de la lluvia (sólo memoria)
LOTE_CELDAS_S14 = 2048                                 # no-umbral: celdas por lote en S14 (sólo memoria)

# S14 (SAL-11): rutas relativas a sus alias.
RUTA_CONFIG_V3 = "scripts_riesgo_agudo/v3/config_v3.json"             # APH (fijados.SHA_CONFIG_V3)
CELDAS_PARQUET = "celdas.parquet"                                       # GRILLA
ENLACES_PARQUET = "enlaces_productos.parquet"                           # GRILLA
PESOS_PARQUET = "poblacion_celda_anio.parquet"                         # PESOS
CARPETA_MENSUAL = "mensual"                                             # ERA5L/mensual (_comun_modelo.ruta_mensual)
PREFIJO_LOCAL_V3 = "LOCAL/AirPollution/"               # el LOCAL de config_v3.json más «AirPollution» = LOCAL (ENT-3)
_VARIABLES_FONDO = ("t2m", "d2m", "sp", "u10", "v10")  # las que usa campos_fondo
_RESULTADOS = ("igual", "distinto")
# SAL-11, P-SAU-2: el motivo de S14 cuando Td_F queda sin dato donde la v3 lo tiene (sin números ni dígitos).
MOTIVO_TD_SIN_DATO = ("Td del fondo sin dato en horas en que el producto de referencia lo tiene (el píxel trae el "
                      "punto de rocío pero no la presión o la temperatura)")
# Los atributos de una tabla diaria que la identifican (SAL-10): van en sus metadatos al escribirla con ``salidas``.
CLAVES_METADATOS = ("tipo_dia", "anio", "anio_pesos", "pesos_sha256", "anio_pesos_lluvia")


class ErrorSalud(RuntimeError):
    """Un insumo mal armado o desalineado: detiene la corrida (como ``ErrorFondo`` y ``ErrorProducto``)."""


def _fondo() -> ModuleType:
    """``fondo_era5l`` a través de ``producto`` (SAL-12): una dependencia declarada que el grafo por AST no ve
    (PED-1)."""
    modulo = getattr(producto, "fondo_era5l", None)
    if not isinstance(modulo, ModuleType) or modulo.__name__ != "meteo_combinada.fondo_era5l":
        raise ImportError("producto.fondo_era5l no es meteo_combinada.fondo_era5l")
    return modulo


# ---------------------------------------------------------------------------
# Horas, zonas y días (SAL-1 a SAL-5)
# ---------------------------------------------------------------------------
def _horas(h, *, nombre: str = "h") -> np.ndarray:
    a = np.asarray(h)
    if a.ndim != 1 or a.dtype == bool or not np.issubdtype(a.dtype, np.integer):
        raise ErrorSalud(f"{nombre}: un arreglo de horas enteras (horas desde 2000-01-01T00Z)")
    return a.astype(np.int64)


def _crecientes(h: np.ndarray, nombre: str = "h") -> np.ndarray:
    if h.size > 1 and not (np.diff(h) > 0).all():
        raise ErrorSalud(f"{nombre}: las horas deben ir estrictamente crecientes y sin repetir")
    return h


_ZONAS: dict[str, zoneinfo.ZoneInfo] = {}


def _zona(nombre: str) -> zoneinfo.ZoneInfo:
    """La zona IANA desde el paquete tzdata (SAL-2)."""
    if not isinstance(nombre, str) or not nombre:
        raise ErrorSalud(f"zona IANA inválida: {nombre!r}")
    if zoneinfo.TZPATH:
        raise RuntimeError("la base de zonas debe ser sólo la del paquete tzdata (§0, regla 3 del diseño): "
                           "zoneinfo.TZPATH no está vacío (SAL-2)")
    if nombre not in _ZONAS:
        _ZONAS[nombre] = zoneinfo.ZoneInfo(nombre)
    return _ZONAS[nombre]


_INICIOS: dict[str, tuple[int, np.ndarray]] = {}


def _inicios_h(fechas: np.ndarray, zona: str) -> np.ndarray:
    """Hora (h) de la medianoche local de cada fecha (días desde 1970), como ``limites_civiles`` (SAL-2)."""
    fechas = np.asarray(fechas, dtype=np.int64)
    if fechas.size == 0:
        return np.zeros(0, dtype=np.int64)
    d0, d1 = int(fechas.min()), int(fechas.max())
    previo = _INICIOS.get(zona)
    if previo is None or d0 < previo[0] or d1 >= previo[0] + previo[1].size:
        if previo is not None:
            d0, d1 = min(d0, previo[0]), max(d1, previo[0] + previo[1].size - 1)
        tz = _zona(zona)
        segundos = []
        for d in range(d0, d1 + 1):
            f = date.fromordinal(d + _ORDINAL_1970)
            segundos.append(int(datetime(f.year, f.month, f.day, tzinfo=tz).timestamp()))
        s = np.asarray(segundos, dtype=np.int64) - _S_UNIX_2000
        if (s % _SEGUNDOS_H != 0).any():
            raise ErrorSalud(f"{zona}: una medianoche local no cae en una hora UTC exacta")
        tabla = s // _SEGUNDOS_H
        if tabla.size > 1 and not (np.diff(tabla) > 0).all():
            raise ErrorSalud(f"{zona}: las medianoches locales no crecen")
        _INICIOS[zona] = (d0, tabla)
        previo = _INICIOS[zona]
    return previo[1][fechas - previo[0]]


def dias(h, zona: str | None) -> np.ndarray:
    """Día (días desde 1970-01-01, int32) de cada hora ``h``: el civil de ``zona`` (SAL-2) o, con ``None``, el UTC−4 fijo
    (SAL-3)."""
    h = _horas(h)
    if zona is None:
        return ((h - DESFASE_UTC4_H) // HORAS_UTC4 + _DIAS_UNIX_2000).astype(np.int32)
    if h.size == 0:
        return np.zeros(0, dtype=np.int32)
    d0 = int(h.min() // HORAS_UTC4) + _DIAS_UNIX_2000 - _MARGEN_DIAS
    d1 = int(h.max() // HORAS_UTC4) + _DIAS_UNIX_2000 + _MARGEN_DIAS
    fechas = np.arange(d0, d1 + 1, dtype=np.int64)
    ini = _inicios_h(fechas, zona)
    k = np.searchsorted(ini, h, side="right") - 1
    if (k < 0).any() or (k >= fechas.size - 1).any():
        raise ErrorSalud(f"{zona}: una hora queda fuera de las fechas buscadas")
    return fechas[k].astype(np.int32)


def horas_esperadas(dias, zona: str | None) -> np.ndarray:
    """Duración de cada día (int64): 23, 24 o 25 horas en ``zona``; siempre 24 con ``None`` (SAL-2, SAL-3)."""
    d = np.asarray(dias)
    if d.ndim != 1 or d.dtype == bool or not np.issubdtype(d.dtype, np.integer):
        raise ErrorSalud("horas_esperadas: un arreglo de días enteros (días desde 1970-01-01)")
    d = d.astype(np.int64)
    if zona is None:
        return np.full(d.size, HORAS_UTC4, dtype=np.int64)
    if d.size == 0:
        return np.zeros(0, dtype=np.int64)
    e = _inicios_h(d + 1, zona) - _inicios_h(d, zona)
    if not np.isin(e, HORAS_DIA).all():
        raise ErrorSalud(f"{zona}: un día dura otra cosa que {HORAS_DIA} horas")
    return e


def zonas_por_comuna(comunas) -> dict[int, str]:
    """Zona horaria de cada comuna (SAL-4): la de su región en ``ZONAS_REGIONALES`` o ``ZONA_BASE``."""
    for nombre in {ZONA_BASE, *ZONAS_REGIONALES.values()}:
        _zona(nombre)
    cods = np.unique(np.asarray(list(comunas) if not isinstance(comunas, np.ndarray) else comunas, dtype=np.int64))
    return {int(c): ZONAS_REGIONALES.get(int(c) // DIVISOR_REGION, ZONA_BASE) for c in cods}


def _anio_de_dia(d: np.ndarray) -> np.ndarray:
    return (_UNIX_D + np.asarray(d, dtype=np.int64)).astype("datetime64[Y]").astype(np.int64) + 1970   # no-umbral: año base de datetime64


def _mes_de_dia(d: np.ndarray) -> np.ndarray:
    m = (_UNIX_D + np.asarray(d, dtype=np.int64)).astype("datetime64[M]").astype(np.int64)
    return m % 12 + 1


def dias_del_anio(h, anio: int) -> np.ndarray:
    """Las filas de ``meteo_civil_v3`` (SAL-5): los días UTC−4 del año con al menos una hora en ``h`` (int64)."""
    d = np.unique(dias(h, None).astype(np.int64))
    return d[_anio_de_dia(d) == int(anio)]


@dataclass(frozen=True, eq=False)
class _Dias:
    """Las horas de una serie repartidas en los días pedidos con una zona (``None``: UTC−4): el tramo contiguo de horas,
    el comienzo de cada día dentro del tramo, la posición de cada día en ``pedidos``, y por día pedido sus horas en la
    serie y su duración (SAL-5; ``meteo_civil_v3.segmentos`` y ``TipoDia``)."""
    zona: str | None
    tramo: slice
    inicios: np.ndarray
    pos: np.ndarray
    n_horas: np.ndarray
    esperadas: np.ndarray


def _dias_de(h: np.ndarray, pedidos: np.ndarray, zona: str | None) -> _Dias:
    dia = dias(h, zona).astype(np.int64)
    if np.any(np.diff(dia) < 0):
        raise ErrorSalud("la fecha de las horas retrocede")
    idx = np.flatnonzero(np.isin(dia, pedidos))
    n = np.zeros(pedidos.size, dtype=np.int64)
    esperadas = horas_esperadas(pedidos, zona)
    if idx.size == 0:
        vacio = np.zeros(0, dtype=np.int64)
        return _Dias(zona, slice(0, 0), vacio, vacio, n, esperadas)
    a, b = int(idx[0]), int(idx[-1]) + 1
    if b - a != idx.size:
        raise ErrorSalud("las horas de los días pedidos no son contiguas")
    d = dia[a:b]
    inicios = np.flatnonzero(np.r_[True, d[1:] != d[:-1]])
    pos = np.searchsorted(pedidos, d[inicios])
    n[pos] = np.diff(np.r_[inicios, b - a])
    if np.any(n > esperadas):
        raise ErrorSalud("hay días con más horas que su duración")
    return _Dias(zona, slice(a, b), inicios, pos, n, esperadas)


def _pedidos(h: np.ndarray, anio: int, dias_pedidos) -> np.ndarray:
    if dias_pedidos is None:
        p = dias_del_anio(h, anio)
    else:
        p = np.asarray(dias_pedidos)
        if p.ndim != 1 or p.dtype == bool or not np.issubdtype(p.dtype, np.integer):
            raise ErrorSalud("dias: un arreglo de días enteros (días desde 1970-01-01)")
        p = p.astype(np.int64)
        if p.size > 1 and not (np.diff(p) > 0).all():
            raise ErrorSalud("dias: crecientes y sin repetir")
    if p.size == 0:
        raise ErrorSalud("no hay días que publicar")
    return p


def _tipo(tipo_dia) -> str:
    if tipo_dia not in TIPOS_DIA:
        raise ErrorSalud(f"tipo de día {tipo_dia!r}; son {TIPOS_DIA}")
    return str(tipo_dia)


# ---------------------------------------------------------------------------
# Pesos (SAL-6, SAL-7)
# ---------------------------------------------------------------------------
def _anio_pesos(anio: int, anios_tabla) -> int:
    """El año de los pesos: el del producto, llevado al rango de la tabla (2026 usa 2025; SAL-6)."""
    anios = np.unique(np.asarray(anios_tabla, dtype=np.int64))
    if anios.size == 0:
        raise ErrorSalud("la tabla de pesos no tiene años")
    a = int(min(max(int(anio), int(anios[0])), int(anios[-1])))
    if a not in set(anios.tolist()):
        raise ErrorSalud(f"la tabla de pesos no tiene el año {a}")
    return a


def _tabla_del_anio(tabla_pesos: pd.DataFrame, anio: int) -> tuple[int, pd.DataFrame]:
    faltan = [c for c in ("celda", "anio", "w_ghs") if c not in tabla_pesos.columns]
    if faltan:
        raise ErrorSalud(f"poblacion_celda_anio: faltan las columnas {faltan}")
    a = _anio_pesos(anio, tabla_pesos["anio"].to_numpy())
    t = tabla_pesos[tabla_pesos["anio"].to_numpy(np.int64) == a]
    if t["celda"].duplicated().any():
        raise ErrorSalud(f"poblacion_celda_anio: celdas repetidas en {a}")
    return a, t


@dataclass(frozen=True, eq=False)
class PesosComuna:
    """La matriz dispersa comuna × celda de T, Td y HR (SAL-6): ``matriz`` (CSR, comunas × celdas) con w_ghs del año de
    los pesos; ``comunas`` (int32) y ``celdas`` (int64) en orden creciente; ``huella``: sha256 de lo que define los
    pesos (año, celdas, comunas y w)."""
    anio: int
    anio_pesos: int
    comunas: np.ndarray
    celdas: np.ndarray
    comuna_de_celda: np.ndarray
    w: np.ndarray
    matriz: Any
    huella: str


def _huella_pesos(*partes) -> str:
    h = hashlib.sha256()
    for p in partes:
        h.update(np.ascontiguousarray(p).tobytes() if isinstance(p, np.ndarray) else str(p).encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


def _celdas_y_comunas(celdas) -> pd.DataFrame:
    if not isinstance(celdas, pd.DataFrame) or "celda" not in celdas.columns or "cod_comuna" not in celdas.columns:
        raise ErrorSalud("celdas: una tabla con «celda» y «cod_comuna» (la de grilla_1km/celdas.parquet)")
    c = celdas[["celda", "cod_comuna"]]
    if c["celda"].isna().any() or c["cod_comuna"].isna().any():
        raise ErrorSalud("celdas: «celda» y «cod_comuna» sin nulos")
    if c["celda"].duplicated().any():
        raise ErrorSalud("celdas: celda repetida")
    return c


def pesos_comuna(anio: int, celdas, tabla_pesos) -> PesosComuna:
    """Matriz dispersa comuna × celda (SAL-6). ``celdas``: las celdas con producto (``celda``, ``cod_comuna`` de la
    grilla); ``tabla_pesos``: ``poblacion_celda_anio`` (``celda``, ``anio``, ``w_ghs``; ``cod_comuna`` si la trae)."""
    c = _celdas_y_comunas(celdas)
    a, t = _tabla_del_anio(tabla_pesos, anio)
    columnas = ["celda", "w_ghs"] + (["cod_comuna"] if "cod_comuna" in t.columns else [])
    d = c.merge(t[columnas], on="celda", how="inner", suffixes=("", "_pesos"))
    if "cod_comuna_pesos" in d.columns:
        if (d["cod_comuna"].to_numpy(np.int64) != d["cod_comuna_pesos"].to_numpy(np.int64)).any():
            raise ErrorSalud("la comuna de la tabla de pesos no es la de la grilla")
    w = d["w_ghs"].to_numpy(np.float64)
    cod = d["cod_comuna"].to_numpy(np.int64)
    ok = (cod > 0) & np.isfinite(w) & (w > 0)
    celda = d["celda"].to_numpy(np.int64)[ok]
    orden = np.argsort(celda, kind="stable")
    celda, cod, w = celda[orden], cod[ok][orden], w[ok][orden]
    if celda.size == 0:
        raise ErrorSalud("ninguna celda con cod_comuna > 0 y w_ghs > 0")
    comunas = np.unique(cod)
    fila = np.searchsorted(comunas, cod)
    matriz = sparse.csr_matrix((w, (fila, np.arange(celda.size))), shape=(comunas.size, celda.size))
    return PesosComuna(anio=int(anio), anio_pesos=a, comunas=comunas.astype(np.int32), celdas=celda,
                       comuna_de_celda=cod.astype(np.int32), w=w, matriz=matriz,
                       huella=_huella_pesos(a, celda, cod.astype(np.int32), w))


@dataclass(frozen=True, eq=False)
class PesosLluvia:
    """Los pares comuna × píxel de ``meteo_civil_v3.construir_pesos`` (SAL-7), ordenados por comuna y píxel."""
    anio: int
    anio_pesos: int
    comunas: np.ndarray
    pixeles: np.ndarray
    fila: np.ndarray
    col: np.ndarray
    w: np.ndarray
    w_norm: np.ndarray
    cortes: np.ndarray
    comunas_por_area: tuple[int, ...]


def pesos_lluvia(anio: int, celdas, enlaces, tabla_pesos) -> PesosLluvia:
    """Los pares comuna × píxel de la lluvia (SAL-7, MC-13), con las operaciones de ``construir_pesos`` en su orden.
    ``celdas`` y ``enlaces``: las tablas de la grilla tal como se leen (``celda``, ``cod_comuna`` y ``celda``,
    ``era5land_pixel``); ``tabla_pesos``: ``poblacion_celda_anio``."""
    cel = _celdas_y_comunas(celdas)
    if not isinstance(enlaces, pd.DataFrame) or any(c not in enlaces.columns for c in ("celda", "era5land_pixel")):
        raise ErrorSalud("enlaces: una tabla con «celda» y «era5land_pixel» (enlaces_productos.parquet)")
    enl = enlaces[["celda", "era5land_pixel"]]
    a, t = _tabla_del_anio(tabla_pesos, anio)
    s = t.set_index("celda").sort_index()["w_ghs"].astype("float64")             # _pesos._tabla_anio y pesos()
    pob = pd.DataFrame({"celda": s.index.to_numpy(), "pob_dens": s.to_numpy("float64")})
    # construir_pesos (meteo_civil_v3, panel_meteo.py:88-108), las mismas operaciones y en el mismo orden:
    d = cel.merge(enl, on="celda").merge(pob[["celda", "pob_dens"]], on="celda")
    d = d[(d["cod_comuna"] > 0) & (d["era5land_pixel"] >= 0)].copy()
    d["w"] = np.clip(np.nan_to_num(d["pob_dens"].to_numpy(dtype=float)), 0, None)
    sin_pob = d.groupby("cod_comuna")["w"].transform("sum") <= 0
    por_area = tuple(sorted(int(c) for c in d.loc[sin_pob, "cod_comuna"].unique()))
    d.loc[sin_pob, "w"] = 1.0
    g = d.groupby(["cod_comuna", "era5land_pixel"], as_index=False)["w"].sum()
    comunas = np.sort(g["cod_comuna"].unique())
    pixeles = np.sort(g["era5land_pixel"].unique())
    fi = pd.Index(comunas).get_indexer(g["cod_comuna"])
    ci = pd.Index(pixeles).get_indexer(g["era5land_pixel"])
    w = g["w"].to_numpy(np.float64)
    if w.size == 0:
        raise ErrorSalud("ninguna celda con cod_comuna > 0 y píxel enlazado")
    if not (np.all(np.diff(fi) >= 0) and np.all(fi >= 0) and np.all(ci >= 0)):
        raise ErrorSalud("los pares comuna-píxel no quedaron ordenados por comuna")
    cortes = np.flatnonzero(np.r_[True, fi[1:] != fi[:-1]])
    suma = np.add.reduceat(w, cortes)
    if not np.all(suma > 0):
        raise ErrorSalud("una comuna quedó sin peso")
    w_norm = w / np.repeat(suma, np.diff(np.r_[cortes, len(w)]))
    return PesosLluvia(int(anio), a, comunas.astype(np.int32), pixeles.astype(np.int64), fi.astype(np.int64),
                       ci.astype(np.int64), w, w_norm, cortes.astype(np.int64), por_area)


# ---------------------------------------------------------------------------
# Agregados diarios (meteo_civil_v3: _media, _suma, agregados_dia, ponderar)
# ---------------------------------------------------------------------------
def _media(x: np.ndarray, inicios: np.ndarray) -> np.ndarray:
    ok = np.isfinite(x)
    if ok.all():
        return np.add.reduceat(x, inicios, axis=0) / np.diff(np.r_[inicios, len(x)])[:, None]
    suma = np.add.reduceat(np.where(ok, x, 0.0), inicios, axis=0)
    n = np.add.reduceat(ok.astype(np.int64), inicios, axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n > 0, suma / n, np.nan)


def _suma(x: np.ndarray, inicios: np.ndarray) -> np.ndarray:
    ok = np.isfinite(x)
    if ok.all():
        return np.add.reduceat(x, inicios, axis=0)
    suma = np.add.reduceat(np.where(ok, x, 0.0), inicios, axis=0)
    n = np.add.reduceat(ok.astype(np.int64), inicios, axis=0)
    return np.where(n > 0, suma, np.nan)


def _ponderar(valores: np.ndarray, pesos: PesosLluvia) -> np.ndarray:
    """``meteo_civil_v3.ponderar``: media por comuna (días × comunas) de días × píxeles, con ``w_norm``."""
    x = valores[:, pesos.col]
    ok = np.isfinite(x)
    if ok.all():
        return np.add.reduceat(x * pesos.w_norm[None, :], pesos.cortes, axis=1)
    num = np.add.reduceat(np.where(ok, x * pesos.w_norm[None, :], 0.0), pesos.cortes, axis=1)
    den = np.add.reduceat(np.where(ok, pesos.w_norm[None, :], 0.0), pesos.cortes, axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, num / den, np.nan)


def _agregados_campo(T: np.ndarray, Td: np.ndarray, HR: np.ndarray, inicios: np.ndarray) -> dict[str, np.ndarray]:
    """Media, mínima y máxima de T, media de HR y de Td por día y celda (``agregados_dia`` sin la lluvia)."""
    return {"temp_media": _media(T, inicios), "temp_min": np.fmin.reduceat(T, inicios, axis=0),
            "temp_max": np.fmax.reduceat(T, inicios, axis=0), "hr_media": _media(HR, inicios),
            "td_media": _media(Td, inicios)}


def hr_del_producto(T, Td) -> np.ndarray:
    """HR (%) por Magnus sobre agua desde T y Td (°C), recortada en [0, 100] (§3; SAL-6)."""
    with np.errstate(invalid="ignore", over="ignore"):
        return np.clip(numerico.hr_desde(T, Td), _HR_MIN, _HR_MAX)


# ---------------------------------------------------------------------------
# Lluvia (SAL-7, MC-13)
# ---------------------------------------------------------------------------
def lluvia_horaria(h, tp) -> np.ndarray:
    """Lluvia (mm) de la hora que termina en cada ``h``, desde el acumulado ``tp`` (m, desde las 00 UTC), en float64:
    ``meteo_civil_v3.lluvia_horaria`` con ``h`` en lugar de los segundos UTC (la diferencia con la hora previa si es la
    inmediatamente anterior, salvo a las 01 UTC; por 1000 y recortada en 0; NaN sin la hora previa)."""
    h = _horas(h)
    tp = np.asarray(tp, dtype=np.float64)
    if tp.shape[:1] != h.shape:
        raise ErrorSalud("lluvia_horaria: tp debe traer una fila por hora")
    dif = np.full_like(tp, np.nan)
    seguidas = np.diff(h) == 1
    dif[1:][seguidas] = tp[1:][seguidas] - tp[:-1][seguidas]
    a_la_una = h % HORAS_UTC4 == 1
    dif[a_la_una] = tp[a_la_una]
    return np.clip(dif * 1000.0, 0, None)


def _zonas_aparte(h: np.ndarray, pedidos: np.ndarray, comunas: np.ndarray) -> tuple[_Dias, dict[str, _Dias]]:
    """La zona base y las zonas de las comunas cuyos días difieren de los de la base (``calcular_anio``)."""
    base = _dias_de(h, pedidos, ZONA_BASE)
    dia_base = dias(h, ZONA_BASE)
    aparte = {}
    for z in sorted(set(zonas_por_comuna(comunas).values())):
        if z == ZONA_BASE:
            continue
        t = _dias_de(h, pedidos, z)
        if not np.array_equal(dias(h, z)[t.tramo], dia_base[base.tramo]) or t.tramo != base.tramo:
            aparte[z] = t
    return base, aparte


def lluvia_comunal(h, tp, pixel_id, pesos: PesosLluvia, tipo_dia: str, *, dias=None) -> pd.DataFrame:
    """``cod_comuna``, ``dia`` y ``precip_mm`` (comuna × día, ordenadas), como ``meteo_civil_v3`` (SAL-7, MC-13).

    ``h``: horas de la serie continua; ``tp``: el acumulado (m, horas × píxeles, float32 de los archivos); ``pixel_id``: el
    píxel de cada columna de ``tp`` (deben estar todos los de ``pesos``); ``dias``: los días pedidos (por omisión, las
    filas de SAL-5 del año de ``pesos``)."""
    tipo = _tipo(tipo_dia)
    h = _crecientes(_horas(h))
    tp = np.asarray(tp)
    pid = np.asarray(pixel_id, dtype=np.int64)
    if tp.ndim != 2 or tp.shape != (h.size, pid.size):
        raise ErrorSalud("lluvia_comunal: tp debe ser horas × píxeles")
    col = pd.Index(pid).get_indexer(pesos.pixeles)
    if (col < 0).any():
        raise ErrorSalud(f"lluvia_comunal: faltan {int((col < 0).sum())} píxeles enlazados")
    pedidos = _pedidos(h, pesos.anio, dias)
    if tipo == "utc4":
        zonas = {None: _dias_de(h, pedidos, None)}
    else:
        base, aparte = _zonas_aparte(h, pedidos, pesos.comunas)
        zonas = {ZONA_BASE: base, **(aparte if tipo == "regional" else {})}
    n_pix = pesos.pixeles.size
    sumas = {z: np.full((pedidos.size, n_pix), np.nan) for z in zonas}
    for p0 in range(0, n_pix, LOTE_PIXELES):
        cols = slice(p0, min(p0 + LOTE_PIXELES, n_pix))
        pr = lluvia_horaria(h, tp[:, col[cols]])
        for z, t in zonas.items():
            if t.tramo.stop <= t.tramo.start:
                continue
            sumas[z][t.pos, cols] = _suma(pr[t.tramo], t.inicios)
        del pr
    if tipo == "utc4":
        valores = _ponderar(sumas[None], pesos)
    else:
        valores = _ponderar(sumas[ZONA_BASE], pesos)
        if tipo == "regional":
            zonas_com = zonas_por_comuna(pesos.comunas)
            for z in zonas:
                if z == ZONA_BASE:
                    continue
                cols_z = np.flatnonzero([zonas_com[int(c)] == z for c in pesos.comunas])
                valores[:, cols_z] = _ponderar(sumas[z], pesos)[:, cols_z]
    tabla = pd.DataFrame({"cod_comuna": np.repeat(pesos.comunas.astype(np.int32), pedidos.size),
                          "dia": np.tile(pedidos.astype(np.int32), pesos.comunas.size),
                          "precip_mm": np.ascontiguousarray(valores.T).reshape(-1)})
    tabla.attrs.update({"tipo_dia": tipo, "anio": int(pesos.anio), "anio_pesos": int(pesos.anio_pesos)})
    return tabla


# ---------------------------------------------------------------------------
# T, Td y HR en las celdas (SAL-5, SAL-6, SAL-8)
# ---------------------------------------------------------------------------
def _exigir_pesos(pesos) -> PesosComuna:
    if not isinstance(pesos, PesosComuna):
        raise ErrorSalud("pesos: un PesosComuna (pesos_comuna)")
    return pesos


@dataclass(eq=False)
class _Lote:
    """Un lote de celdas del acumulador (SAL-13): sus posiciones en los pesos; por zona, las columnas que la usan, sus
    selecciones por tipo de día y el lote anterior que usa esa zona (−1 si es el primero); los días ya agregados por
    zona; la próxima fila de la serie que espera, y las horas guardadas de los días que todavía no se completan (filas
    [``inicio_buffer``, ``fin``) de la serie)."""
    indice: int
    glob: np.ndarray
    zonas: dict
    hecho: dict
    fin: int = 0
    inicio_buffer: int = 0
    buffer: dict | None = None


class AcumuladorMeteo:
    """Medias comunales diarias de T, Td y HR por lotes de celdas, para uno o más tipos de día (SAL-6, SAL-13).

    ``agregar`` recibe los campos de un lote de celdas (horas × celdas: la serie entera ``h`` o, con ``horas``, un
    tramo contiguo de ella) y suma, por comuna y día, los pesos por los agregados de cada celda en cuanto el día está
    completo; ``tabla`` da la tabla de ``meteo_civil_v3`` cuando ya llegaron todas las celdas de los pesos con todas sus
    horas. Una celda que no está en los pesos (sin comuna, sin población o sin producto) se ignora; una que llega dos
    veces es un error."""

    def __init__(self, pesos: PesosComuna, h, tipos_dia: Sequence[str], *, dias=None):
        self.pesos = _exigir_pesos(pesos)
        self.h = _crecientes(_horas(h))
        tipos_dia = (tipos_dia,) if isinstance(tipos_dia, str) else tuple(tipos_dia)
        if not tipos_dia or len(set(tipos_dia)) != len(tipos_dia):
            raise ErrorSalud("tipos de día: al menos uno y sin repetir")
        self.tipos = tuple(_tipo(t) for t in tipos_dia)
        self.pedidos = _pedidos(self.h, pesos.anio, dias)
        zona_com = zonas_por_comuna(pesos.comunas)
        self._zona_de_comuna = np.asarray([zona_com[int(c)] for c in pesos.comunas], dtype=object)
        zona_celda = self._zona_de_comuna[np.searchsorted(pesos.comunas, pesos.comuna_de_celda)]
        self._clave = {}
        for t in self.tipos:
            if t == "utc4":
                self._clave[t] = np.full(pesos.celdas.size, None, dtype=object)
            elif t == "civil":
                self._clave[t] = np.full(pesos.celdas.size, ZONA_BASE, dtype=object)
            else:
                self._clave[t] = zona_celda
        zonas = {z for t in self.tipos for z in set(self._clave[t].tolist())}
        self._dias = {z: _dias_de(self.h, self.pedidos, z) for z in sorted(zonas, key=lambda z: (z is not None, z))}
        # Por zona, la primera y la siguiente a la última fila de la serie de cada día con horas (SAL-13), y el último
        # lote que agregó ese día.
        self._limites: dict = {}
        self._ultimo: dict = {}
        for z, d in self._dias.items():
            largo = d.tramo.stop - d.tramo.start
            ini = d.tramo.start + d.inicios.astype(np.int64)
            fin = d.tramo.start + np.r_[d.inicios[1:], largo].astype(np.int64) if d.inicios.size else ini.copy()
            self._limites[z] = (ini, fin)
            self._ultimo[z] = np.full(d.inicios.size, -1, dtype=np.int64)
        self._csc = pesos.matriz.tocsc()
        forma = (self.pedidos.size, pesos.comunas.size)
        self._num = {t: {v: np.zeros(forma) for v in VARIABLES_CAMPO} for t in self.tipos}
        self._den = {t: {v: np.zeros(forma) for v in VARIABLES_CAMPO} for t in self.tipos}
        self._lotes: list[_Lote] = []
        self._ultimo_de_zona: dict = {}
        self._lote_de = np.full(pesos.celdas.size, -1, dtype=np.int64)
        self._terminadas = np.zeros(pesos.celdas.size, dtype=bool)

    def _campos(self, campos: Mapping, n: int, filas: int) -> dict[str, np.ndarray]:
        if not isinstance(campos, Mapping) or "T" not in campos or "Td" not in campos:
            raise ErrorSalud("campos: T y Td (°C) del producto, horas × celdas; HR opcional")
        salida = {}
        for c in CAMPOS:
            if c not in campos:
                continue
            x = np.asarray(campos[c], dtype=np.float64)
            if x.shape != (filas, n):
                raise ErrorSalud(f"campos: {c} debe ser {(filas, n)} (horas × celdas) y es {x.shape}")
            salida[c] = x
        if "HR" not in salida:
            salida["HR"] = hr_del_producto(salida["T"], salida["Td"])
        return salida

    def _tramo(self, horas) -> tuple[int, int]:
        """Las filas [a, b) de la serie que trae un tramo (SAL-13); sin ``horas``, la serie entera."""
        if horas is None:
            return 0, int(self.h.size)
        hh = _horas(horas, nombre="horas")
        if hh.size == 0:
            raise ErrorSalud("horas: un tramo con al menos una hora")
        a = int(np.searchsorted(self.h, hh[0]))
        b = a + int(hh.size)
        if b > self.h.size or not np.array_equal(self.h[a:b], hh):
            raise ErrorSalud("horas: un tramo contiguo de las horas del acumulador (SAL-13)")
        return a, b

    def _lote(self, glob: np.ndarray, a: int) -> tuple[_Lote, bool]:
        """El lote de un tramo y si es nuevo (SAL-13). Uno nuevo no se registra aquí: lo hace ``agregar`` después de
        comprobar el orden, para que un error no deje nada a medias."""
        previo = self._lote_de[glob]
        if a == 0:
            if (previo >= 0).any():
                raise ErrorSalud("una celda llegó dos veces al acumulador")
            zonas = {}
            for z in self._dias:
                usa = np.zeros(glob.size, dtype=bool)
                for t in self.tipos:
                    usa |= self._clave[t][glob] == z
                if not usa.any() or self._limites[z][0].size == 0:
                    continue
                cols = np.flatnonzero(usa)
                g = glob[cols]
                por_tipo = {t: self._clave[t][g] == z for t in self.tipos}
                zonas[z] = (cols, g, {t: s for t, s in por_tipo.items() if s.any()}, self._ultimo_de_zona.get(z, -1))
            return _Lote(indice=len(self._lotes), glob=glob.copy(), zonas=zonas, hecho={z: 0 for z in zonas}), True
        if (previo < 0).any() or (previo != previo[0]).any():
            raise ErrorSalud("un tramo que no empieza en la primera hora de la serie continúa un lote ya empezado, con "
                             "las mismas celdas (SAL-13)")
        lote = self._lotes[int(previo[0])]
        if not np.array_equal(lote.glob, glob):
            raise ErrorSalud("los tramos de un lote traen las mismas celdas, en el mismo orden (SAL-13)")
        if lote.fin != a:
            raise ErrorSalud("los tramos de un lote van seguidos, sin huecos ni repeticiones de horas (SAL-13)")
        return lote, False

    def agregar(self, campos: Mapping, celdas, *, horas=None) -> None:
        """Agrega un lote de celdas (SAL-6) o un tramo de horas de un lote (SAL-13). ``campos``: {"T", "Td"[, "HR"]},
        horas × celdas, alineados con ``h`` o con ``horas`` (un tramo contiguo de ``h``); ``celdas``: sus ids."""
        ids = np.asarray(celdas)
        if ids.ndim != 1 or ids.dtype == bool or not np.issubdtype(ids.dtype, np.integer):
            raise ErrorSalud("celdas: los ids de las celdas del lote (enteros)")
        ids = ids.astype(np.int64)
        a, b = self._tramo(horas)
        x = self._campos(campos, ids.size, b - a)
        todas = self.pesos.celdas
        pos = np.minimum(np.searchsorted(todas, ids), todas.size - 1)
        esta = todas[pos] == ids
        locales, glob = np.flatnonzero(esta), pos[esta]
        if glob.size == 0:
            return
        if np.unique(glob).size != glob.size:
            raise ErrorSalud("una celda llegó dos veces al acumulador")
        lote, nuevo = self._lote(glob, a)

        def filas(c: str, r0: int, r1: int, cols: np.ndarray) -> np.ndarray:
            """Las filas [r0, r1) de la serie, en las columnas ``cols`` del lote: de lo guardado y del tramo."""
            partes = []
            if r0 < a:
                if lote.buffer is None or r0 < lote.inicio_buffer:
                    raise ErrorSalud("faltan horas guardadas de un día que cruza el corte (SAL-13)")
                partes.append(lote.buffer[c][r0 - lote.inicio_buffer:min(r1, a) - lote.inicio_buffer][:, cols])
            if r1 > a:
                partes.append(x[c][max(r0, a) - a:r1 - a][:, locales[cols]])
            return partes[0] if len(partes) == 1 else np.concatenate(partes, axis=0)

        # Los días que este tramo completa, por zona; cada uno debe haberlo completado ya el lote anterior que usa la
        # zona (SAL-13: el orden de las sumas por comuna es el de la serie entera). Se comprueba antes de tocar nada.
        listos = {z: int(np.searchsorted(self._limites[z][1], b, side="right")) for z in lote.zonas}
        for z, (_, _, _, previo) in lote.zonas.items():
            if not (self._ultimo[z][lote.hecho[z]:listos[z]] == previo).all():
                raise ErrorSalud("los lotes completan cada día en el orden en que aparecieron, como con la serie "
                                 "entera (SAL-13, MC-37)")
        if nuevo:
            self._lotes.append(lote)
            self._lote_de[glob] = lote.indice
            for z in lote.zonas:
                self._ultimo_de_zona[z] = lote.indice
        for z, (cols, g, por_tipo, _) in lote.zonas.items():
            ini, fin = self._limites[z]
            h0 = lote.hecho[z]
            if listos[z] <= h0:
                continue
            r0, r1 = int(ini[h0]), int(fin[listos[z] - 1])
            ag = _agregados_campo(filas("T", r0, r1, cols), filas("Td", r0, r1, cols), filas("HR", r0, r1, cols),
                                  ini[h0:listos[z]] - r0)
            dias_pos = self._dias[z].pos[h0:listos[z]]
            for t, sel in por_tipo.items():
                W = self._csc[:, g[sel]]
                for v in VARIABLES_CAMPO:
                    sub = ag[v][:, sel]
                    ok = np.isfinite(sub)
                    self._num[t][v][dias_pos] += np.asarray(W.dot(np.where(ok, sub, 0.0).T)).T
                    self._den[t][v][dias_pos] += np.asarray(W.dot(ok.T.astype(np.float64))).T
            self._ultimo[z][h0:listos[z]] = lote.indice
            lote.hecho[z] = listos[z]
        pendientes = [int(self._limites[z][0][lote.hecho[z]]) for z in lote.zonas
                      if lote.hecho[z] < self._limites[z][0].size]
        if not pendientes:
            lote.buffer, lote.inicio_buffer = None, b
            self._terminadas[lote.glob] = True
        else:
            p = min(pendientes)
            if p >= b:
                lote.buffer, lote.inicio_buffer = None, b
            else:
                todas_cols = np.arange(lote.glob.size)
                lote.buffer = {c: filas(c, p, b, todas_cols) for c in CAMPOS}
                lote.inicio_buffer = p
        lote.fin = b

    def tabla(self, tipo_dia: str, lluvia: pd.DataFrame) -> pd.DataFrame:
        """La tabla de ``tipos.ESQUEMA_METEO_DIARIA`` del tipo, con la lluvia de ``lluvia_comunal`` (SAL-5, SAL-8)."""
        tipo = _tipo(tipo_dia)
        if tipo not in self.tipos:
            raise ErrorSalud(f"el acumulador no lleva el tipo {tipo!r}")
        if not self._terminadas.all():
            raise ErrorSalud(f"faltan {int((~self._terminadas).sum())} celdas de los pesos en el acumulador, o sus "
                             "últimas horas (SAL-13)")
        if not isinstance(lluvia, pd.DataFrame) or list(lluvia.columns) != ["cod_comuna", "dia", "precip_mm"]:
            raise ErrorSalud("lluvia: la tabla de lluvia_comunal (cod_comuna, dia, precip_mm)")
        if lluvia.attrs.get("tipo_dia", tipo) != tipo:
            raise ErrorSalud(f"la lluvia es del día {lluvia.attrs.get('tipo_dia')!r}, no {tipo!r}")
        if not np.array_equal(np.unique(lluvia["dia"].to_numpy(np.int64)), self.pedidos):
            raise ErrorSalud("la lluvia no trae exactamente los días pedidos")
        comunas = np.union1d(self.pesos.comunas.astype(np.int64), lluvia["cod_comuna"].to_numpy(np.int64))
        nd, nc = self.pedidos.size, comunas.size
        ip = np.searchsorted(comunas, self.pesos.comunas)
        valores = {}
        for v in VARIABLES_CAMPO:
            num, den = self._num[tipo][v], self._den[tipo][v]
            m = np.full((nd, nc), np.nan)
            with np.errstate(invalid="ignore", divide="ignore"):
                m[:, ip] = np.where(den > 0, num / np.where(den > 0, den, 1.0), np.nan)
            valores[v] = m
        precip = (lluvia.pivot(index="dia", columns="cod_comuna", values="precip_mm")
                  .reindex(index=self.pedidos, columns=comunas).to_numpy(np.float64))
        valores["precip_mm"] = precip
        if tipo == "utc4":
            claves = np.full(nc, None, dtype=object)
        elif tipo == "civil":
            claves = np.full(nc, ZONA_BASE, dtype=object)
        else:
            zc = zonas_por_comuna(comunas)
            claves = np.asarray([zc[int(c)] for c in comunas], dtype=object)
        n_horas = np.zeros((nd, nc), dtype=np.int64)
        esperadas = np.zeros((nd, nc), dtype=np.int64)
        for z in set(claves.tolist()):
            d = self._dias[z] if z in self._dias else _dias_de(self.h, self.pedidos, z)
            k = claves == z
            n_horas[:, k] = d.n_horas[:, None]
            esperadas[:, k] = d.esperadas[:, None]
        return _tabla_meteo(comunas, self.pedidos, valores, n_horas, esperadas,
                            {"tipo_dia": tipo, "anio": int(self.pesos.anio), "anio_pesos": int(self.pesos.anio_pesos),
                             "pesos_sha256": self.pesos.huella, "anio_pesos_lluvia": lluvia.attrs.get("anio_pesos")})


def _tabla_meteo(comunas: np.ndarray, pedidos: np.ndarray, valores: Mapping[str, np.ndarray], n_horas: np.ndarray,
                 esperadas: np.ndarray, attrs: Mapping) -> pd.DataFrame:
    """``meteo_civil_v3.tabla_meteo``: tabla larga ordenada por comuna y día, con el esquema de S8."""
    if np.any(n_horas > esperadas):
        raise ErrorSalud("hay días con más horas que su duración")
    nd, nc = pedidos.size, comunas.size
    t = pd.DataFrame({"cod_comuna": np.repeat(np.asarray(comunas, dtype=np.int32), nd),
                      "dia": np.tile(np.asarray(pedidos, dtype=np.int32), nc)})
    for v in VARIABLES:
        t[v] = np.ascontiguousarray(np.asarray(valores[v], dtype=np.float64).T).reshape(-1)
    t["n_horas"] = np.ascontiguousarray(n_horas.T).reshape(-1).astype(np.int8)
    t["n_horas_esperadas"] = np.ascontiguousarray(esperadas.T).reshape(-1).astype(np.int8)
    t["faltan_horas"] = t["n_horas"] < t["n_horas_esperadas"]
    tipos.validar_esquema(t, ESQUEMA, nombre="meteo diaria de salud")
    t.attrs["esquema"] = ESQUEMA.version
    t.attrs.update(attrs)
    return t


def meteo_comunal(campos_celda, lluvia, pesos, tipo_dia, *, dias=None) -> pd.DataFrame:
    """La meteorología diaria comunal de un tipo de día (§7.2, punto 1; SAL-5 a SAL-8), con el esquema de
    ``meteo_civil_v3``. ``campos_celda``: {"h": horas, "celdas": ids, "T": °C, "Td": °C, "HR": % (opcional)}, con T, Td
    y HR horas × celdas; ``lluvia``: la de ``lluvia_comunal`` del mismo tipo; ``pesos``: ``pesos_comuna``. Para muchas
    celdas, ``AcumuladorMeteo`` por lotes da lo mismo."""
    if not isinstance(campos_celda, Mapping) or "h" not in campos_celda or "celdas" not in campos_celda:
        raise ErrorSalud("campos_celda: {h, celdas, T, Td[, HR]}")
    tipo = _tipo(tipo_dia)
    acumulador = AcumuladorMeteo(pesos, campos_celda["h"], (tipo,), dias=dias)
    acumulador.agregar(campos_celda, campos_celda["celdas"])
    return acumulador.tabla(tipo, lluvia)


# ---------------------------------------------------------------------------
# Representatividad (SAL-9; §7.2, punto 6; MC-52)
# ---------------------------------------------------------------------------
def _serie(fuente, variable: str, codigo: str) -> tuple[np.ndarray, np.ndarray]:
    if isinstance(fuente, (tuple, list)) and len(fuente) == 2:
        h, x = fuente
        valido = None
    elif hasattr(fuente, "__getitem__"):
        try:
            h, x = fuente["h"], fuente[variable]
        except (KeyError, IndexError, TypeError) as error:
            raise ErrorSalud(f"{codigo}: la serie trae «h» y «{variable}»") from error
        valido = fuente["valido"] if "valido" in fuente else None
    else:
        raise ErrorSalud(f"{codigo}: la serie es (h, {variable}) o una tabla con «h» y «{variable}»")
    h = _crecientes(_horas(h, nombre=f"{codigo}: h"), f"{codigo}: h")
    x = np.asarray(x, dtype=np.float64).copy()
    if x.shape != h.shape:
        raise ErrorSalud(f"{codigo}: «{variable}» no está alineada con «h»")
    if valido is not None:
        v = np.asarray(valido)
        if v.shape != h.shape or v.dtype != bool:
            raise ErrorSalud(f"{codigo}: «valido» es booleano y alineado con «h»")
        x[~v] = np.nan
    return h, x


def _dias_validos(h: np.ndarray, zona: str | None, min_h: int, hueco_max: int) -> tuple[np.ndarray, np.ndarray]:
    """Día de cada hora emparejada y si ese día es válido (§5.2: ≥ ``min_h`` horas y hueco circular ≤ ``hueco_max``)."""
    d = dias(h, zona).astype(np.int64)
    unicos, inicio, cuenta = np.unique(d, return_index=True, return_counts=True)
    if zona is None:
        ini = (unicos - _DIAS_UNIX_2000) * HORAS_UTC4 + DESFASE_UTC4_H
    else:
        ini = _inicios_h(unicos, zona)
    dur = horas_esperadas(unicos, zona)
    rep = np.repeat(np.arange(unicos.size), cuenta)
    pos = h - ini[rep]
    fin = inicio + cuenta - 1
    salto = np.zeros(h.size, dtype=np.int64)
    mismo = np.r_[False, d[1:] == d[:-1]]
    salto[mismo] = np.diff(pos)[mismo[1:]]
    interno = np.maximum.reduceat(salto, inicio)
    vuelta = pos[inicio] + dur - pos[fin]
    hueco = np.maximum(interno, vuelta)
    valido_dia = (cuenta >= min_h) & (hueco <= hueco_max)
    return d, valido_dia[rep]


def _metricas_representatividad(h: np.ndarray, obs: np.ndarray, pix: np.ndarray, *, zona: str | None, min_h: int,
                                 hueco_max: int) -> tuple[float, float]:
    """(r de las medias diarias, cociente de amplitudes de los ciclos medios por hora UTC), en memoria (SAL-9)."""
    ok = np.isfinite(obs) & np.isfinite(pix)
    h, a, b = h[ok], obs[ok], pix[ok]
    if h.size == 0:
        return float("nan"), float("nan")
    d, valida = _dias_validos(h, zona, min_h, hueco_max)
    r = float("nan")
    if valida.any():
        dv = d[valida]
        _, inv = np.unique(dv, return_inverse=True)
        n = np.bincount(inv).astype(np.float64)
        ma = np.bincount(inv, weights=a[valida]) / n
        mb = np.bincount(inv, weights=b[valida]) / n
        if ma.size >= 2:
            ca, cb = ma - ma.mean(), mb - mb.mean()
            sa, sb = float(np.sqrt((ca * ca).sum())), float(np.sqrt((cb * cb).sum()))
            if sa > 0 and sb > 0:
                r = float((ca * cb).sum() / (sa * sb))
    hora = h % HORAS_UTC4
    n_h = np.bincount(hora, minlength=HORAS_UTC4)
    con = n_h > 0
    cociente = float("nan")
    if int(con.sum()) >= 2:
        ciclo_a = np.bincount(hora, weights=a, minlength=HORAS_UTC4)[con] / n_h[con]
        ciclo_b = np.bincount(hora, weights=b, minlength=HORAS_UTC4)[con] / n_h[con]
        amp_a, amp_b = float(ciclo_a.max() - ciclo_a.min()), float(ciclo_b.max() - ciclo_b.min())
        if amp_b > 0:
            cociente = amp_a / amp_b
    return r, cociente


def _fuera(r: float, cociente: float) -> bool:
    """La regla de §7.2, punto 6 (SAL-9): r < 0,8 o cociente fuera de [0,5; 2]; sin valor calculable, también fuera."""
    if not (np.isfinite(r) and np.isfinite(cociente)):
        return True
    return bool(r < _R_MIN or cociente < _COCIENTE_MIN or cociente > _COCIENTE_MAX)


def representatividad(diarios_obs, t2m_pixel_reloj, umbrales, *, zona: str | None = ZONA_BASE) -> frozenset[str]:
    """Las estaciones excluidas de la sensibilidad de representatividad (§7.2, punto 6; MC-52; SAL-9).

    ``diarios_obs``: {código: serie horaria de la estación} con «h» y «T» (°C; NaN o ``valido`` = False donde la hora no
    es válida), o el par (h, T); ``t2m_pixel_reloj``: {código: serie de t2m en el píxel del reloj de esa estación} con
    «h» y «t2m», o el par (h, t2m), ya elegido por quien llama (A27). Las unidades de t2m (K o °C) no cambian nada: r y
    el cociente no dependen de un desplazamiento. Sólo devuelve los códigos (§0.4.6)."""
    if not isinstance(diarios_obs, Mapping) or not isinstance(t2m_pixel_reloj, Mapping):
        raise ErrorSalud("representatividad: {código: serie} para las estaciones y para sus píxeles")
    min_h, hueco_max = int(umbrales.a("DIA_MIN_H")), int(umbrales.a("DIA_HUECO_H"))
    if zona is not None:
        _zona(zona)
    excluidas = set()
    for codigo in sorted(diarios_obs):
        if not isinstance(codigo, str):
            raise ErrorSalud("representatividad: los códigos de estación son textos")
        if codigo not in t2m_pixel_reloj:
            raise ErrorSalud(f"{codigo}: falta la serie del píxel del reloj")
        h_o, x_o = _serie(diarios_obs[codigo], "T", codigo)
        h_p, x_p = _serie(t2m_pixel_reloj[codigo], "t2m", codigo)
        comunes, io, ip = np.intersect1d(h_o, h_p, assume_unique=True, return_indices=True)
        r, cociente = _metricas_representatividad(comunes, x_o[io], x_p[ip], zona=zona, min_h=min_h,
                                                  hueco_max=hueco_max)
        if _fuera(r, cociente):
            excluidas.add(codigo)
    return frozenset(excluidas)


# ---------------------------------------------------------------------------
# Crónico (SAL-10; §7.3)
# ---------------------------------------------------------------------------
def _a_json(v):
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    return v


def metadatos_tabla(tabla: pd.DataFrame) -> dict:
    """Los atributos de ``CLAVES_METADATOS`` de una tabla diaria, como números y textos de Python: lo que se pasa como
    ``metadatos=`` a ``salidas.escribir`` para que la tabla releída de disco sirva a ``cronico_anual`` (SAL-10)."""
    if not isinstance(tabla, pd.DataFrame):
        raise ErrorSalud("metadatos_tabla: una tabla diaria (DataFrame)")
    return {k: _a_json(tabla.attrs[k]) for k in CLAVES_METADATOS if k in tabla.attrs}


def _atributos(t: pd.DataFrame, nombre: str) -> dict:
    """Los ``attrs`` de una tabla con los de ``attrs["metadatos"]`` (una tabla releída de un parquet de ``salidas``,
    SLD-4); una clave en los dos lugares con valores distintos es un error (SAL-10)."""
    attrs = {k: v for k, v in t.attrs.items() if k != "metadatos"}
    meta = t.attrs.get("metadatos")
    if meta is None:
        return attrs
    if not isinstance(meta, Mapping):
        raise ErrorSalud(f"{nombre}: attrs['metadatos'] no es un diccionario")
    for k in CLAVES_METADATOS:
        if k not in meta:
            continue
        if k in attrs and _a_json(attrs[k]) != _a_json(meta[k]):
            raise ErrorSalud(f"{nombre}: «{k}» no es el mismo en attrs y en attrs['metadatos']")
        attrs.setdefault(k, meta[k])
    return attrs


def cronico_anual(diarios, pesos_por_anio) -> pd.DataFrame:
    """``temp_media_anual`` y ``temp_media_fria`` (abril a septiembre) por comuna y año (§7.3; SAL-10), con
    ``tipos.ESQUEMA_CRONICO``. ``diarios``: {año: la tabla civil de ``meteo_comunal`` de ese año, con el ganador
    crónico, en memoria o releída de un parquet escrito con ``metadatos=metadatos_tabla(…)``}; ``pesos_por_anio``:
    {año: el ``PesosComuna`` con que se armó}."""
    if not isinstance(diarios, Mapping) or not diarios:
        raise ErrorSalud("cronico_anual: {año: tabla diaria civil}")
    if not isinstance(pesos_por_anio, Mapping):
        raise ErrorSalud("cronico_anual: {año: PesosComuna}")
    partes = []
    for anio in sorted(diarios):
        t = diarios[anio]
        if not isinstance(t, pd.DataFrame):
            raise ErrorSalud(f"{anio}: la tabla diaria es un DataFrame")
        tipos.validar_esquema(t, ESQUEMA, nombre=f"meteo diaria {anio}")
        at = _atributos(t, f"{anio}")
        if at.get("tipo_dia") != "civil":
            raise ErrorSalud(f"{anio}: lo crónico sale de los días civiles (§7.3), no de {at.get('tipo_dia')!r}")
        if isinstance(at.get("anio"), bool) or at.get("anio") != int(anio):
            raise ErrorSalud(f"{anio}: la tabla diaria es de otro año")
        p = pesos_por_anio.get(anio)
        if not isinstance(p, PesosComuna) or p.anio != int(anio):
            raise ErrorSalud(f"{anio}: faltan los pesos w_ghs de ese año")
        if at.get("pesos_sha256") != p.huella:
            raise ErrorSalud(f"{anio}: la tabla diaria no se armó con los pesos w_ghs de su año")
        d = t["dia"].to_numpy(np.int64)
        if (_anio_de_dia(d) != int(anio)).any():
            raise ErrorSalud(f"{anio}: la tabla diaria trae días de otro año")
        mes = _mes_de_dia(d)
        g = pd.DataFrame({"cod_comuna": t["cod_comuna"].to_numpy(np.int32),
                          "temp_media": t["temp_media"].to_numpy(np.float64),
                          "fria": (mes >= MESES_FRIOS[0]) & (mes <= MESES_FRIOS[1])})
        anual = g.groupby("cod_comuna")["temp_media"].mean()
        fria = g[g["fria"]].groupby("cod_comuna")["temp_media"].mean().reindex(anual.index)
        partes.append(pd.DataFrame({"cod_comuna": anual.index.to_numpy(np.int32),
                                    "anio": np.full(anual.size, int(anio), dtype=np.int16),
                                    "temp_media_anual": anual.to_numpy(np.float64),
                                    "temp_media_fria": fria.to_numpy(np.float64)}))
    salida = pd.concat(partes, ignore_index=True).sort_values(["cod_comuna", "anio"], kind="stable")
    salida = salida.reset_index(drop=True).astype({"cod_comuna": "int32", "anio": "int16"})
    tipos.validar_esquema(salida, tipos.ESQUEMA_CRONICO, nombre="crónico")
    salida.attrs["esquema"] = tipos.ESQUEMA_CRONICO.version
    return salida


# ---------------------------------------------------------------------------
# S14 (SAL-11)
# ---------------------------------------------------------------------------
def _meses_s14(anio: int) -> list[tuple[int, int]]:
    """Los meses del año y el enero siguiente (``meteo_civil_v3.archivos_anio``)."""
    return [(int(anio), m) for m in range(1, 13)] + [(int(anio) + 1, 1)]


def _nombre_mes(anio: int, mes: int) -> str:
    return f"era5land_{anio:04d}{mes:02d}_chile_pixeles.nc"


def insumos_s14(anio: int, rutas) -> dict[str, Path]:
    """{alias: ruta} de todo lo que ``regresion_s14`` abre (SAL-11): ``config_v3.json``, ``celdas.parquet``,
    ``enlaces_productos.parquet``, ``poblacion_celda_anio.parquet``, los 13 meses ERA5-Land y los tres productos v3 del
    año. Es la lista de rutas permitidas de su ``RegistroAccesos``. No consulta el disco."""
    salida = {f"APH/{RUTA_CONFIG_V3}": Path(rutas.aph) / RUTA_CONFIG_V3,
              f"GRILLA/{CELDAS_PARQUET}": Path(rutas.grilla) / CELDAS_PARQUET,
              f"GRILLA/{ENLACES_PARQUET}": Path(rutas.grilla) / ENLACES_PARQUET,
              f"PESOS/{PESOS_PARQUET}": Path(rutas.pesos) / PESOS_PARQUET}
    for a, m in _meses_s14(anio):
        nombre = _nombre_mes(a, m)
        salida[f"ERA5L/{CARPETA_MENSUAL}/{nombre}"] = Path(rutas.era5l) / CARPETA_MENSUAL / nombre
    for tipo in TIPOS_DIA:
        salida[f"V3/{tipo}/meteo_{int(anio)}.parquet"] = Path(rutas.v3) / tipo / f"meteo_{int(anio)}.parquet"
    return salida


def _leer(ruta: Path) -> tuple[bytes, str]:
    """Los bytes de un archivo y su sha256, con ``open`` de Python (CEG-5)."""
    with open(ruta, "rb") as f:
        datos = f.read()
    return datos, hashlib.sha256(datos).hexdigest()


def _parquet(datos: bytes, columnas: Sequence[str] | None = None) -> pa.Table:
    return pq.read_table(pa.BufferReader(datos), columns=None if columnas is None else list(columnas))


def _carpetas_config(cfg: Mapping, rutas) -> dict[str, Path]:
    try:
        productos = cfg["confusores"]["meteorologia_productos"]
    except (KeyError, TypeError) as error:
        raise ErrorSalud("config_v3.json no trae confusores.meteorologia_productos") from error
    salida = {}
    for tipo in TIPOS_DIA:
        carpeta = productos.get(tipo, {}).get("carpeta") if isinstance(productos.get(tipo), Mapping) else None
        if not isinstance(carpeta, str) or not carpeta.startswith(PREFIJO_LOCAL_V3):
            raise ErrorSalud(f"config_v3.json: la carpeta de {tipo} no está bajo {PREFIJO_LOCAL_V3}")
        ruta = Path(rutas.local) / carpeta[len(PREFIJO_LOCAL_V3):]
        if ruta != Path(rutas.v3) / tipo:
            raise ErrorSalud(f"config_v3.json: la carpeta de {tipo} no es V3/{tipo} (ENT-3)")
        salida[tipo] = ruta
    return salida


def _tabla_v3(datos: bytes) -> pd.DataFrame:
    """Un producto v3 como DataFrame, con ``fecha`` (date32) como ``dia`` (``meteo_civil_v3.leer_tabla``)."""
    t = _parquet(datos)
    columnas = {}
    for c in t.column_names:
        if pa.types.is_date32(t.schema.field(c).type):
            columnas["dia"] = t[c].cast(pa.int32()).to_numpy()
        else:
            columnas[c] = t[c].to_numpy()
    return pd.DataFrame(columnas)


def _comparar(nuestra: pd.DataFrame, v3: pd.DataFrame, esquema_v3: Mapping, tolerancia: float) -> dict:
    """«igual» o «distinto», la diferencia máxima y, si difiere, el motivo sin números (SAL-11)."""
    motivos = []
    columnas_v3 = dict(esquema_v3["columnas"])
    if list(v3.columns) != list(columnas_v3) or any(str(v3[c].dtype) != t for c, t in columnas_v3.items()):
        motivos.append("columnas o tipos distintos del esquema de meteo_civil_v3")
    claves = ["cod_comuna", "dia"]
    a = nuestra.reset_index(drop=True)
    b = v3.reset_index(drop=True)
    if not all(c in b.columns for c in [*claves, *VARIABLES]):
        return {"resultado": "distinto", "dif_max": float("nan"), "motivo": "faltan columnas en el producto v3"}
    mismas_filas = len(a) == len(b) and all(np.array_equal(a[c].to_numpy(np.int64), b[c].to_numpy(np.int64))
                                            for c in claves)
    if not mismas_filas:
        motivos.append("filas distintas")
        b = a[claves].merge(b, on=claves, how="inner")
        a = a.merge(b[claves], on=claves, how="inner")
    for c in ("n_horas", "n_horas_esperadas", "faltan_horas"):
        if c in b.columns and not np.array_equal(a[c].to_numpy(), b[c].to_numpy()):
            motivos.append("conteos de horas distintos")
            break
    dif = 0.0
    otras_nan = False
    for v in VARIABLES:
        x, y = a[v].to_numpy(np.float64), b[v].to_numpy(np.float64)
        nx, ny = np.isnan(x), np.isnan(y)
        if not np.array_equal(nx, ny):
            otras_nan = True
        ambos = ~nx & ~ny
        if ambos.any():
            dif = max(dif, float(np.max(np.abs(x[ambos] - y[ambos]))))
    if otras_nan:
        motivos.append("NaN en otras posiciones")
    if dif > tolerancia:
        motivos.append("valores fuera de la tolerancia")
    return {"resultado": "distinto" if motivos else "igual", "dif_max": dif,
            "motivo": "; ".join(dict.fromkeys(motivos)) or None}


def _reducir_mes(fondo: ModuleType, mes, pixeles: np.ndarray):
    """El mes sólo en los píxeles pedidos (en su orden) y con las variables del fondo; y su ``tp``."""
    idx = pd.Index(np.asarray(mes.pixel_id, dtype=np.int64)).get_indexer(pixeles)
    if (idx < 0).any():
        raise ErrorSalud(f"mes {mes.yyyymm}: faltan {int((idx < 0).sum())} píxeles enlazados")
    datos = {v: np.ascontiguousarray(mes.datos[v][:, idx]) for v in _VARIABLES_FONDO}
    tp = np.ascontiguousarray(mes.datos["tp"][:, idx])
    return fondo.MesE5L(tiempos=mes.tiempos, pixel_id=pixeles, datos=datos, sha256=mes.sha256), tp


def _operador_enlazado(fondo: ModuleType, ids: np.ndarray, pix: np.ndarray):
    """El operador de S14 (SAL-11): un vecino, el píxel enlazado, con peso 1 y Δz = 0."""
    n = ids.size
    columnas: dict[str, Any] = {}
    for k in range(_N_VECINOS):
        columnas[f"pix{k}"] = pix.astype(np.int32) if k == 0 else np.full(n, -1, dtype=np.int32)
    for k in range(_N_VECINOS):
        columnas[f"w{k}"] = np.full(n, 1.0 if k == 0 else 0.0)
    columnas["respaldo_16km"] = np.zeros(n, dtype=bool)
    z_pix = pd.Series(0.0, index=np.unique(pix.astype(np.int64)))
    return fondo.operador_desde_columnas(ids, np.zeros(n), pd.DataFrame(columnas), z_pix)


def regresion_s14(anio: int, rutas, *, esquema_v3: dict, umbrales, exigir_huellas: bool = True,
                  lote_celdas: int = LOTE_CELDAS_S14) -> dict:
    """S14 (§9; SAL-11): el lector por celda con corrección 0 frente a las carpetas civil, UTC−4 y regional de
    ``config_v3.json`` en ``anio``. Lee sólo ``insumos_s14(anio, rutas)``, en sólo lectura, y no guarda nada.

    Devuelve {"anio", "resultado", "tolerancia", "carpetas": {tipo: {"resultado", "dif_max", "motivo"}}, "huellas":
    {alias: sha256}}. ``esquema_v3``: ``fijados.esquema_meteo_civil_v3``; ``umbrales``: los de M0 (el operador los pide;
    con Δz = 0, Γ no entra). ``exigir_huellas``: exige las huellas fijadas de ``config_v3.json``, ``celdas.parquet`` y
    ``enlaces_productos.parquet`` (``fijados``); sólo las pruebas sintéticas lo apagan."""
    fondo = _fondo()
    anio = int(anio)
    if ESQUEMA.version != esquema_v3.get("version") or dict(ESQUEMA) != dict(esquema_v3.get("columnas", {})) \
            or tuple(esquema_v3.get("variables", ())) != VARIABLES:
        raise ErrorSalud("el esquema de salud no es el de meteo_civil_v3 (S8)")
    if isinstance(lote_celdas, bool) or not isinstance(lote_celdas, int) or lote_celdas < 1:
        raise ErrorSalud("lote_celdas: un entero ≥ 1")
    insumos = insumos_s14(anio, rutas)
    huellas: dict[str, str] = {}
    fijas = {f"APH/{RUTA_CONFIG_V3}": fijados.SHA_CONFIG_V3,
             f"GRILLA/{CELDAS_PARQUET}": fijados.HUELLAS_DATOS[f"GRILLA/{CELDAS_PARQUET}"],
             f"GRILLA/{ENLACES_PARQUET}": fijados.HUELLAS_DATOS[f"GRILLA/{ENLACES_PARQUET}"]}

    def leer(alias: str) -> bytes:
        datos, sha = _leer(insumos[alias])
        huellas[alias] = sha
        if exigir_huellas and alias in fijas and sha != fijas[alias]:
            raise ErrorSalud(f"{alias}: la sha256 no es la fijada ({fijas[alias][:fijados.ABREVIATURA]}…)")
        return datos

    cfg = json.loads(leer(f"APH/{RUTA_CONFIG_V3}").decode("utf-8"))
    carpetas = _carpetas_config(cfg, rutas)
    cel = _parquet(leer(f"GRILLA/{CELDAS_PARQUET}"), ["celda", "cod_comuna"]).to_pandas()
    enl = _parquet(leer(f"GRILLA/{ENLACES_PARQUET}"), ["celda", "era5land_pixel"]).to_pandas()
    t_pesos = _parquet(leer(f"PESOS/{PESOS_PARQUET}"), ["celda", "anio", "w_ghs"])
    anios_tabla = t_pesos["anio"].to_numpy()
    a_pesos = _anio_pesos(anio, anios_tabla)
    fila_anio = anios_tabla.astype(np.int64) == a_pesos
    tabla_pesos = pd.DataFrame({"celda": t_pesos["celda"].to_numpy()[fila_anio],
                                "anio": anios_tabla[fila_anio],
                                "w_ghs": t_pesos["w_ghs"].to_numpy()[fila_anio]})
    del t_pesos, anios_tabla, fila_anio

    pl = pesos_lluvia(anio, cel, enl, tabla_pesos)
    unidas = cel.merge(enl, on="celda")
    unidas = unidas[(unidas["cod_comuna"] > 0) & (unidas["era5land_pixel"] >= 0)]
    pc = pesos_comuna(anio, unidas[["celda", "cod_comuna"]], tabla_pesos)
    enlace = pd.Series(unidas["era5land_pixel"].to_numpy(np.int64), index=unidas["celda"].to_numpy(np.int64))
    pix_de_celda = enlace.reindex(pc.celdas).to_numpy(np.int64)
    pixeles = pl.pixeles
    if not np.isin(pix_de_celda, pixeles).all():
        raise ErrorSalud("hay celdas con producto cuyo píxel no está en los pares de la lluvia")
    del cel, enl, unidas, enlace

    meses, tp = [], []
    for a, m in _meses_s14(anio):
        alias = f"ERA5L/{CARPETA_MENSUAL}/{_nombre_mes(a, m)}"
        mes = fondo.leer_mes(insumos[alias])                  # lee los bytes con open y calcula su sha256 (CEG-5)
        huellas[alias] = mes.sha256
        reducido, tp_mes = _reducir_mes(fondo, mes, pixeles)
        del mes
        meses.append(reducido)
        tp.append(tp_mes)
    h = fondo.horas_de(meses)
    tp = np.concatenate(tp, axis=0)
    pedidos = dias_del_anio(h, anio)
    lluvias = {tipo: lluvia_comunal(h, tp, pixeles, pl, tipo, dias=pedidos) for tipo in TIPOS_DIA}
    del tp

    acumulador = AcumuladorMeteo(pc, h, TIPOS_DIA, dias=pedidos)
    usadas = np.zeros(h.size, dtype=bool)                  # las horas de algún día pedido, en alguna zona
    for d in acumulador._dias.values():
        usadas[d.tramo] = True
    td_sin_dato = np.zeros(h.size, dtype=bool)             # Td_F sin dato donde el píxel trae d2m (SAL-11, P-SAU-2)
    col_de_celda = np.searchsorted(pixeles, pix_de_celda)
    for i0 in range(0, pc.celdas.size, lote_celdas):
        ids = pc.celdas[i0:i0 + lote_celdas]
        op = _operador_enlazado(fondo, ids, pix_de_celda[i0:i0 + lote_celdas])
        col = col_de_celda[i0:i0 + lote_celdas]
        fila = 0
        for mes in meses:                                   # mes a mes, como en M5 (SAL-13)
            F = fondo.campos_fondo(mes, op, umbrales, recortar_td=False)
            k = len(mes.tiempos)
            T, Td = F["T_F"], F["Td_F"]
            td_sin_dato[fila:fila + k] |= (np.isnan(Td) & np.isfinite(mes.datos["d2m"][:, col])).any(axis=1)
            acumulador.agregar({"T": T, "Td": Td, "HR": hr_del_producto(T, Td)}, ids, horas=mes.tiempos)
            fila += k
            del F, T, Td
    del meses
    hay_td_sin_dato = bool((td_sin_dato & usadas).any())

    carpetas_resultado = {}
    for tipo in TIPOS_DIA:
        nuestra = acumulador.tabla(tipo, lluvias[tipo])
        v3 = _tabla_v3(leer(f"V3/{tipo}/meteo_{anio}.parquet"))
        c = _comparar(nuestra, v3, esquema_v3, _TOL_S14)
        if c["resultado"] == "distinto" and hay_td_sin_dato:
            c["motivo"] = "; ".join(m for m in (c["motivo"], MOTIVO_TD_SIN_DATO) if m)
        carpetas_resultado[tipo] = c
    resultado = "igual" if all(c["resultado"] == "igual" for c in carpetas_resultado.values()) else "distinto"
    return {"anio": anio, "resultado": resultado, "tolerancia": _TOL_S14, "carpetas": carpetas_resultado,
            "huellas": dict(sorted(huellas.items()))}
