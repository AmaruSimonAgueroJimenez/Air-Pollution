"""Lector de la meteorología SINCA para la validación independiente (§5.6; MC-10).

Los dos manifiestos y sus huellas, la elección de series, el reloj, el control mínimo y las series horarias.
Es descriptiva y no entra en §6: no calcula métricas (las de §5.6 y su aviso son de ``validacion``, I14) ni escribe
nada. Lee sólo bajo la raíz que recibe (SINCA_MET), con ``open`` de Python, y devuelve tablas en memoria.

Funciones públicas:
- ``leer_manifiestos(raiz, huellas)``: los dos manifiestos, con las huellas de los seis archivos de la lista cerrada.
- ``series_descartadas(manifiesto, umbrales)`` y ``elegir_series(manifiesto, umbrales)``: una serie por estación ×
  variable (MC-10, puntos 4 y 6) y el motivo de cada serie que no entra.
- ``leer_politica_temporal(ruta)``, ``zona_de(region, politica)``, ``huella_contenido(tabla)`` y
  ``veredictos_civiles(tabla, convencion, sha256=, resumen=)``: la política temporal anclada y los veredictos «hora
  civil» del reloj SINCA de la Enmienda 2 ambiental (R7), atados a su ``resumen.json``.
- ``parsear_serie(texto)``, ``horas_fin_utc(etiquetas, civil, …)`` y ``control_minimo(variable, valores, umbrales)``:
  las tres piezas de una serie (formato, reloj y rangos), sueltas para probarlas.
- ``leer_serie(raiz, fila, …)`` y ``series_horarias(raiz, elegidas, politica_temporal, umbrales, veredictos=)``: las
  series en ``tipos.ESQUEMA_SINCA_HORA``, con su registro en ``attrs["registro_sinca"]``.

Dueño: I11 (ola 2).
Lecturas propias (SNC-n), para el addendum de M1:
- SNC-1. **Manifiestos y huellas** (MC-10, punto 5; §9.3 y §9.4 del diseño). Seis archivos bajo la raíz:
  ``manifiesto_descarga.csv``, ``SHA256SUMS.txt`` y ``no_disponibles.csv``, y los mismos con «_20261024b». Cada uno
  pasa la guarda de rutas (SNC-15), se lee una vez y su sha256 debe ser el de ``huellas`` (claves con el alias
  «SINCA_MET/» o sin él, como en ``fijados.HUELLAS_DATOS``; las demás claves se ignoran; falta una de las seis →
  error). Las columnas son exactamente ``CAMPOS_MANIFIESTO`` del descargador (copiadas; ``test_sinca_meteo`` las
  compara por AST con su huella 0942c4d0…; el segundo descargador escribe con ``smet.CAMPOS_MANIFIESTO``). Cada fila:
  ruta relativa sin «..», sha256 de 64 cifras hexadecimales y conteos enteros. El par (sha256, ruta) de cada fila está
  en su ``SHA256SUMS`` y al revés, sin líneas repetidas. **Los dos manifiestos son disjuntos por serie**, no por
  estación: ninguna (``estacion``, ``parametro``, ``macro_ficha``), ``ruta_relativa`` ni sha256 está en los dos. El
  diseño (l. 20-22) dice «Los dos son disjuntos y suman 154 estaciones» con 87 y 114 estaciones, así que comparten 47;
  y ``descargar_sinca_ampliacion.py`` (d7724723…), que escribió el segundo, deja fuera las series ya publicadas por
  (región, estación, parámetro, macro), no las estaciones (``_claves_meteorologia_previas``). Pregunta SNC-P4. Una
  estación puede estar en los dos; la elección (SNC-4) corre sobre los dos juntos. Además, una ruta relativa aparece
  una sola vez y cada código de estación tiene una sola región: si no, ``ErrorSinca``. ``no_disponibles`` sólo se
  comprueba por su huella. La tabla no lleva ``primera_observacion``, ``ultima_observacion``, ``minimo`` ni
  ``maximo`` (``CAMPOS_NO_EXPUESTOS``): son valores SINCA que ninguna lectura usa, y MC-10 pide fijar la lectura «antes
  de verla». Sólo entran en la huella del archivo.
- SNC-2. **Series que pueden entrar** (antes de leer un solo valor). Sólo TEMP, RHUM, WSPD y WDIR (MC-10, punto 6; B13:
  «temperatura, HR y viento»): PRES, RAIN y GLOB del segundo manifiesto quedan fuera. Además, con la lectura más
  estricta: ``accion`` de una serie publicada por los dos descargadores («descargado» o «reutilizado_en_disco»:
  ``procesar_serie`` del primero y ``_obtener`` del segundo; la prueba compara los dos conjuntos); ``unidad_ficha``
  igual a la que espera el descargador (°C, %, m/s y °; otra grafía no se adivina, pregunta SNC-P3); ``marca_temporal``
  = «hora_local_civil_sinca_sin_offset» (la ``reloj_fuente`` de la política) y ``politica_temporal_sha256`` =
  41018e4c…. Una serie que no cumple queda fuera con su motivo (``series_descartadas``); no detiene la lectura.
- SNC-3. **Altura de la serie.** Es el número de ``altura_ficha`` (con «m», «mts» o «metros» opcionales, coma o punto
  decimal); si no es un número, el NNN de ``macro_ficha`` = «horario_NNN» (el descargador documenta que NNN es la altura
  en metros y que «000» es sin información). Una altura ≤ 0 es sin información. Si las dos fuentes dan número y
  difieren, la serie queda fuera («altura_discrepante»); sin ninguna, también («sin_altura»). Es la lectura más
  estricta: el texto (MC-10, punto 4) no dice qué hacer sin altura (pregunta SNC-P1).
- SNC-4. **Elección** (MC-10, punto 4), sobre los dos manifiestos juntos: por estación y variable, la serie con
  |altura − objetivo| mínima, con objetivo ``ALTURA_T_M`` (2 m) en TEMP y RHUM y ``ALTURA_VIENTO_M`` (10 m) en WSPD y
  WDIR (§3, constantes del A2); en un empate, la de más ``filas_con_observacion`` (el conteo del descargador en el
  manifiesto: no hace falta leer la serie), y luego la de menor ``ruta_relativa`` (orden de los textos de Python). Las
  demás quedan como «no_elegida». ``umbrales`` no interviene (la firma de §3 lo trae): ningún número del Anexo A
  decide la elección.
- SNC-5. **Formato de una serie.** Antes de leer un byte, la guarda de rutas (SNC-15) y su tamaño en disco, que debe
  ser ``bytes`` del manifiesto; leída, su sha256 debe ser el del manifiesto. Después, la regla de
  ``analizar_respuesta`` del descargador, copiada: líneas no vacías, la primera empieza con «FECHA», cada fila calza con
  ``^(\\d{6});(\\d{4});(.*)$``, el valor es el primer campo, con la coma decimal cambiada por punto y ``float`` finito.
  Un campo vacío es una hora sin observación y no entra en la tabla; un campo no numérico o no finito es una
  observación inválida (valor NaN). Son los «centinelas del descargador SINCA» de MC-10, punto 3: el código del
  descargador no conoce otros. Los tres conteos (filas, con observación, no numéricas) deben ser los del manifiesto.
  Cualquier diferencia es ``ErrorSinca``: el archivo pasó esa misma regla al publicarse. Los mensajes de error dan el
  número de la fila, nunca su contenido ni un conteo (MC-10: la lectura se fija antes de ver los datos).
- SNC-6. **Etiqueta.** AAMMDD con ``%y`` (00-68 → 20AA) y HHMM con minutos «00» y hora 00-23, en toda fila (también
  en las vacías); otra cosa es ``ErrorSinca``. La etiqueta es la hora local que trae el archivo, sin zona. Una
  etiqueta repetida no se rechaza: cae en la misma hora UTC y la rige SNC-8.
- SNC-7. **Reloj** (MC-10, punto 1; R7 de la Enmienda 2 ambiental; ``config/sinca/politica_temporal.json``). Regla
  general: UTC−4 fijo con la etiqueta en el fin del intervalo, así que el fin en UTC es la etiqueta + 4 h y
  ``h`` es esa hora (A12: la hora UTC u del fin de [u − 1, u]). Si el veredicto de ``reloj_sinca_v2.py`` dio
  «hora_civil» para la estación y el año local de la etiqueta en algún contaminante (``veredictos["hora_civil"]``),
  se convierte con la zona IANA de su región (``zona_de``; America/Santiago por omisión) y la convención de la
  etiqueta civil que eligió T4 (``veredictos["convencion"]``): «fin», la etiqueta es la hora civil al terminar; o
  «inicio_mas_1h», la hora civil de inicio es la etiqueta − 1 h y el fin es una hora después. Una hora civil repetida
  toma la ocurrencia estándar (``dst()`` nulo) y se registra la otra; una inexistente se desplaza hacia adelante y se
  marca. Se convierte con ``zoneinfo`` y la base de zonas del paquete tzdata (``entorno``, como el reloj), etiqueta
  por etiqueta y con los dos ``fold`` (PEP 495), por un camino propio; una prueba lo compara con ``utc_civil`` de
  ``reloj_sinca_v2.py``. Una estación sin veredicto sigue la regla general.
- SNC-8. **Dos etiquetas en la misma hora UTC** (R7, punto 4): se promedian los valores válidos (la hora es válida si
  alguno lo es); si ninguno lo es, el valor es la media de los finitos y la hora queda inválida. El conteo y la bandera
  van en el registro (``colisiones``: [h, n.º de etiquetas]), porque ``ESQUEMA_SINCA_HORA`` no tiene esas columnas
  (pedido al coordinador). En WDIR una media aritmética de ángulos no tiene sentido (350° y 10° darían 180°): con la
  lectura más estricta, la hora queda inválida y sin valor (pregunta SNC-P2).
- SNC-9. **Control mínimo** (MC-10, punto 3): los rangos de §2.3, inclusivos como en ``cargar_dmc``
  (a ≤ v ≤ b): TEMP como Ts (``QTS_MIN``/``QTS_MAX``), RHUM como HR (``QHR_MIN``/``QHR_MAX``), WSPD como la rapidez
  (``QFF_MIN``/``QFF_MAX``: en el Anexo P los ``QFF_*`` son la rapidez, UMB-11) y WDIR como la dirección
  (``QDD_MIN``/``QDD_MAX``). RHUM válida en (``HR_SAT``, ``HR_RECORTE_MAX``] se recorta a ``HR_SAT`` (como la marca 15).
  Sin rachas, picos, saltos, error grueso ni las reglas del cero y de la calma (MC-10: «sin rachas ni picos»). Los
  centinelas de §2.4 (Ts = −40,0) caen fuera del rango de TEMP.
- SNC-10. **Valores.** ``valor`` va en °C, %, m/s y grados (A12), como el archivo; RHUM válida, ya recortada. Una
  observación inválida conserva su número (NaN si no es numérica) para poder contarla; quien compara usa sólo
  ``valido``. La comparación de MC-10, punto 2 (la media SINCA de [u − 1, u] frente a la media del producto en u − 1 y
  u), es de quien consume la tabla (I14).
- SNC-11. **Veredictos** (A12, propuesta de I11): ``veredictos`` es obligatorio y es
  {"sha256": <de ``veredictos.parquet`` de ``reloj_sinca_v2``>, "huella_contenido": <sha256 de su contenido>,
  "convencion": «fin» | «inicio_mas_1h» | None, "hora_civil": [(estacion, año local), …]}. Sin él no se lee nada: no
  se supone que todo es UTC−4. ``veredictos_civiles`` lo arma desde la tabla del reloj (estación × contaminante × año,
  con ``veredicto_fin`` y ``veredicto_inicio_mas_1h``) y su ``resumen.json``: la unión sobre los contaminantes, en la
  columna de la convención elegida. Antes exige que el resumen sea el del reloj (``schema`` =
  ``SCHEMA_RELOJ_SINCA``), con la política 41018e4c…; que su ``huella_veredictos_contenido`` sea la de la tabla
  recibida, calculada como la calcula el reloj (sha256 de ``tabla.to_csv(index=False)``, ``huella_contenido``); que
  su ``sha256_veredictos`` sea el ``sha256`` recibido; y que ``convencion`` sea ``convencion_civil["elegida"]`` (T4
  elige siempre una, también en un empate en cero, así que aquí no se acepta None). None sólo cabe en un diccionario
  armado a mano sin ningún estación-año civil.
- SNC-12. **Política temporal.** ``leer_politica_temporal`` exige la huella 41018e4c…. Las funciones que la reciben
  (``zona_de``, ``leer_serie`` y ``series_horarias``) aceptan el JSON entero o su bloque «sinca» y exigen que el
  bloque sea, clave por clave, el de la política anclada (``POLITICA_SINCA``, copiado del archivo de huella
  41018e4c…; ``test_sinca_meteo`` los compara): los cuatro textos de los que depende la lectura de R7
  (``reloj_fuente``, ``hora_ambigua``, ``hora_inexistente`` y ``colision_misma_utc_en_panel``), ``utc_salida``,
  ``zona_iana_default`` y ``zonas_iana_por_region``, sin claves de más. Si cambia una, la lectura deja de valer y es
  ``ErrorSinca``: las zonas no pueden venir de otra política. El registro anota esa huella.
- SNC-13. **Tabla.** Una fila por hora UTC con observación, por estación y variable, ordenada por estación, variable
  (en el orden de ``tipos.VARIABLES_SINCA``) y ``h``; ``serie`` es la ruta relativa elegida. En
  ``attrs["registro_sinca"]``: la huella de la política, las dos de los veredictos, la convención y, por serie, sus
  conteos (filas, con observación, no numéricas, fuera de rango, recortadas, válidas), la región y la zona, los años
  civiles, las etiquetas ambiguas e inexistentes, las alternativas ([h, h alternativa]) y las colisiones. Son datos
  SINCA, no DMC, y no son métricas.
- SNC-14. §9 no tiene pruebas de SINCA (§5.6 es descriptiva): este módulo no tiene pruebas «sNN» ni parte de S16.
- SNC-15. **Guarda de rutas** (regla 10 del diseño: «Toda guarda de rutas mira primero la ruta léxica y sólo después
  la resuelve»). Primero la mirada léxica: relativa POSIX, sin raíz, sin «..», «.», partes vacías ni «\\». Después, en
  el disco y antes de leer un byte: ninguna parte bajo la raíz es un enlace simbólico, la ruta resuelta queda dentro de
  la raíz resuelta y es un archivo regular. Vale para las series y para los seis archivos de huella. La raíz misma
  puede ser un enlace: la resuelve ``entorno`` (alias SINCA_MET).
Depende de: tipos, constantes, umbrales, entorno.
"""
from __future__ import annotations

import csv
import io
import json
import math
import re
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from meteo_combinada import constantes, entorno, tipos

# ---------------------------------------------------------------------------
# Formato del descargador (scripts_pipeline/descargar_sinca_meteorologia.py, sha256 0942c4d0…; leído como código)
# ---------------------------------------------------------------------------
SUFIJO_SEGUNDO = "_20261024b"                      # el segundo manifiesto (MC-10, punto 5)
SUFIJOS = ("", SUFIJO_SEGUNDO)
MANIFIESTOS = tuple(f"manifiesto_descarga{s}.csv" for s in SUFIJOS)
ARCHIVOS_HUELLA = tuple(f"{p}{s}.{e}" for s in SUFIJOS
                        for p, e in (("manifiesto_descarga", "csv"), ("SHA256SUMS", "txt"), ("no_disponibles", "csv")))
ALIAS = "SINCA_MET/"                               # alias de entorno; así vienen en fijados.HUELLAS_DATOS
CAMPOS_MANIFIESTO = (
    "region", "estacion", "nombre", "parametro", "variable", "macro_ficha",
    "macro_exportada", "altura_ficha", "unidad_ficha", "instrumento_ficha",
    "desde_ficha", "hasta_ficha", "desde", "hasta", "ruta_relativa", "bytes",
    "sha256", "filas", "filas_con_observacion", "filas_no_numericas",
    "primera_observacion", "ultima_observacion", "minimo", "maximo",
    "url_fuente", "accion", "ficha_sha256", "config_estaciones_sha256",
    "marca_temporal", "politica_temporal_sha256", "script_version",
    "script_sha256", "registrado_utc",
)
CAMPOS_ENTEROS = ("bytes", "filas", "filas_con_observacion", "filas_no_numericas")
CAMPOS_NO_EXPUESTOS = ("primera_observacion", "ultima_observacion", "minimo", "maximo")   # valores SINCA (SNC-1)
CAMPOS_LEIDOS = tuple(c for c in CAMPOS_MANIFIESTO if c not in CAMPOS_NO_EXPUESTOS)
CLAVE_SERIE = ("estacion", "parametro", "macro_ficha")  # _claves_meteorologia_previas, sin la región (una por estación)
UNIDADES = {"TEMP": "°C", "RHUM": "%", "WSPD": "m/s", "WDIR": "°"}       # PARAMETROS del descargador (SNC-2)
ACCIONES_PUBLICADAS = ("descargado", "reutilizado_en_disco")            # procesar_serie y _obtener de los descargadores
COLUMNA_MANIFIESTO = "manifiesto"
COLUMNAS_MANIFIESTO = (*CAMPOS_LEIDOS, COLUMNA_MANIFIESTO)              # la tabla de leer_manifiestos
_RE_DATO = re.compile(r"^(\d{6});(\d{4});(.*)$")                         # _RE_DATO del descargador
_RE_SHA = re.compile(r"[0-9a-f]{64}")
_RE_ENTERO = re.compile(r"\d+")
_RE_ALTURA = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:m|mt|mts|metros?)?\.?", re.IGNORECASE)
_RE_MACRO = re.compile(r"horario_(\d{3})(?:_\w+)?")
ENCABEZADO = "FECHA"

# ---------------------------------------------------------------------------
# Política temporal y reloj (R7 de la Enmienda 2 ambiental; config/sinca/politica_temporal.json)
# ---------------------------------------------------------------------------
SHA_POLITICA_TEMPORAL = "41018e4c066d9e30b5ba0b1ff92d47eeb47bab1984b5b8c45a778939359ac61c"
RELOJ_FUENTE = "hora_local_civil_sinca_sin_offset"
POLITICA_SINCA = MappingProxyType({                # SNC-12: el bloque «sinca» de la política anclada (41018e4c…)
    "reloj_fuente": RELOJ_FUENTE,
    "utc_salida": "datetime_naive_que_representa_utc",
    "zona_iana_default": "America/Santiago",
    "zonas_iana_por_region": MappingProxyType({"RXI": "America/Coyhaique", "RXII": "America/Punta_Arenas"}),
    "hora_ambigua": "conservar_hora_local_asumir_ocurrencia_estandar_y_registrar_utc_alternativo",
    "hora_inexistente": "conservar_hora_local_desplazar_adelante_y_marcar_qc",
    "colision_misma_utc_en_panel": "media_con_conteo_y_bandera_manteniendo_el_lector_crudo_sin_agregar",
})
DESFASE_FIJO_H = 4  # no-umbral: el «UTC−4 fijo» de R7 de la Enmienda 2 ambiental (MC-10, punto 1), no de este texto
CONVENCIONES = ("fin", "inicio_mas_1h")            # de reloj_sinca_v2.py; la elige T4
VEREDICTO_CIVIL = "hora_civil"
TIPO_FIJO, TIPO_UNIVOCA, TIPO_AMBIGUA, TIPO_INEXISTENTE = (
    "fijo", "civil_univoca", "civil_ambigua_estandar", "civil_inexistente_desplazada")   # QC_HORA del reloj SINCA
CLAVES_VEREDICTOS = ("sha256", "huella_contenido", "convencion", "hora_civil")
SCHEMA_RELOJ_SINCA = "airpollution.modelo-1km-v2.reloj-sinca-red2.v1"   # SCHEMA de reloj_sinca_v2.py (SNC-11)
CLAVES_RESUMEN = ("schema", "politica_temporal_sha256", "huella_veredictos_contenido", "sha256_veredictos",
                  "convencion_civil")             # las de resumen.json del reloj que ata veredictos_civiles
HORAS_DIA = 24
_UNA_HORA = timedelta(hours=1)
_EPOCA = datetime.fromisoformat(tipos.EPOCA_H).replace(tzinfo=None)     # h = 0 (2000-01-01T00:00Z)
_EPOCA_H64 = np.datetime64(_EPOCA, "h")

# ---------------------------------------------------------------------------
# Elección y control mínimo
# ---------------------------------------------------------------------------
OBJETIVO_ALTURA = {"TEMP": "ALTURA_T_M", "RHUM": "ALTURA_T_M", "WSPD": "ALTURA_VIENTO_M", "WDIR": "ALTURA_VIENTO_M"}
RANGO = {"TEMP": ("QTS_MIN", "QTS_MAX"), "RHUM": ("QHR_MIN", "QHR_MAX"), "WSPD": ("QFF_MIN", "QFF_MAX"),
         "WDIR": ("QDD_MIN", "QDD_MAX")}
VARIABLE_ANGULAR = "WDIR"
MOTIVOS_DESCARTE = ("variable_no_autorizada", "accion_no_publicada", "unidad_distinta", "marca_temporal_distinta",
                    "politica_temporal_distinta", "sin_altura", "altura_discrepante", "no_elegida")
COLUMNAS_DESCARTE = (COLUMNA_MANIFIESTO, "ruta_relativa", "estacion", "parametro", "motivo")
COLUMNAS_ELEGIDAS = (*COLUMNAS_MANIFIESTO, "altura_m", "altura_fuente")
FUENTES_ALTURA = ("ficha", "macro")
COLUMNAS_SERIE = ("estacion", "region", "parametro", "ruta_relativa", "sha256", "bytes", "filas",
                  "filas_con_observacion", "filas_no_numericas")


class ErrorSinca(ValueError):
    """Un manifiesto, una serie, la política o los veredictos no son los que fija MC-10."""


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def _ruta_relativa_segura(texto: str) -> PurePosixPath:
    """Ruta relativa POSIX sin «..», sin raíz y sin partes vacías (mirada léxica, sin tocar el disco)."""
    if not isinstance(texto, str) or not texto or "\\" in texto:
        raise ErrorSinca(f"ruta relativa inválida en el manifiesto: {texto!r}")
    p = PurePosixPath(texto)
    if p.is_absolute() or any(parte in ("", ".", "..") for parte in texto.split("/")):
        raise ErrorSinca(f"ruta relativa inválida en el manifiesto: {texto!r}")
    return p


def _ruta_bajo_raiz(raiz: Path, relativa: PurePosixPath) -> Path:
    """SNC-15, el paso en el disco (después de ``_ruta_relativa_segura``) y antes de leer un byte: ninguna parte bajo
    la raíz es un enlace simbólico, la ruta resuelta queda dentro de la raíz resuelta y es un archivo regular."""
    base = raiz.resolve(strict=True)
    actual = raiz
    for parte in relativa.parts:
        actual = actual / parte
        if actual.is_symlink():
            raise ErrorSinca(f"{relativa}: un enlace simbólico bajo la raíz SINCA (regla 10 del diseño; SNC-15)")
    real = actual.resolve(strict=True)
    if not real.is_relative_to(base):
        raise ErrorSinca(f"{relativa}: fuera de la raíz SINCA (SNC-15)")
    if not real.is_file():
        raise ErrorSinca(f"{relativa}: no es un archivo regular (SNC-15)")
    return real


def _exigir_columnas(df, columnas, nombre: str) -> None:
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"{nombre} debe ser un DataFrame")
    faltan = [c for c in columnas if c not in df.columns]
    if faltan:
        raise ErrorSinca(f"{nombre}: faltan las columnas {faltan}")


def _texto(x) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)) or x is pd.NA:
        return ""
    return str(x)


def _entero(x, campo: str) -> int:
    t = _texto(x).strip()
    if not _RE_ENTERO.fullmatch(t):
        raise ErrorSinca(f"{campo} no es un entero no negativo")      # sin el valor (SNC-5)
    return int(t)


def _orden_variable(parametro: str) -> int:
    return tipos.VARIABLES_SINCA.index(parametro)


def _h_de(fin_utc: datetime) -> int:
    segundos = (fin_utc - _EPOCA).total_seconds()
    horas = segundos / _UNA_HORA.total_seconds()
    if horas != math.floor(horas):
        raise ErrorSinca(f"hora UTC que no es HH:00: {fin_utc.isoformat()}")
    return int(horas)


# ---------------------------------------------------------------------------
# Manifiestos (SNC-1)
# ---------------------------------------------------------------------------
def _huellas_esperadas(huellas) -> dict[str, str]:
    if not isinstance(huellas, Mapping):
        raise TypeError("huellas debe ser un diccionario {archivo: sha256}")
    salida: dict[str, str] = {}
    for clave, sha in huellas.items():
        if not isinstance(clave, str):
            continue
        nombre = clave[len(ALIAS):] if clave.startswith(ALIAS) else clave
        if nombre not in ARCHIVOS_HUELLA:
            continue
        if not isinstance(sha, str) or not _RE_SHA.fullmatch(sha):
            raise ErrorSinca(f"huella inválida para {nombre}: {sha!r}")
        if nombre in salida and salida[nombre] != sha:
            raise ErrorSinca(f"dos huellas distintas para {nombre}")
        salida[nombre] = sha
    faltan = [n for n in ARCHIVOS_HUELLA if n not in salida]
    if faltan:
        raise ErrorSinca(f"faltan las huellas de {faltan} (MC-10, punto 5: los dos manifiestos y sus huellas)")
    return salida


def _leer_con_huella(raiz: Path, nombre: str, sha: str) -> bytes:
    datos = _ruta_bajo_raiz(raiz, _ruta_relativa_segura(nombre)).read_bytes()
    real = entorno.sha256_bytes(datos)
    if real != sha:
        raise ErrorSinca(f"{nombre}: sha256 {real} distinto del fijado {sha}")
    return datos


def _filas_csv(datos: bytes, nombre: str) -> list[list[str]]:
    try:
        texto = datos.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ErrorSinca(f"{nombre} no es UTF-8") from exc
    filas = list(csv.reader(io.StringIO(texto, newline="")))
    if not filas or tuple(filas[0]) != CAMPOS_MANIFIESTO:
        raise ErrorSinca(f"{nombre}: las columnas no son las del descargador (CAMPOS_MANIFIESTO)")
    cuerpo = filas[1:]
    for k, fila in enumerate(cuerpo, start=2):
        if len(fila) != len(CAMPOS_MANIFIESTO):
            raise ErrorSinca(f"{nombre}, fila {k}: {len(fila)} campos en vez de {len(CAMPOS_MANIFIESTO)}")
    return cuerpo


def _sumas(datos: bytes, nombre: str) -> set[tuple[str, str]]:
    pares = []
    for linea in datos.decode("utf-8").splitlines():
        if not linea.strip():
            continue
        sha, sep, ruta = linea.partition("  ")
        if not sep or not _RE_SHA.fullmatch(sha) or not ruta:
            raise ErrorSinca(f"{nombre}: línea con otro formato que «<sha256>  <ruta>»")
        pares.append((sha, ruta))
    if len(set(pares)) != len(pares):
        raise ErrorSinca(f"{nombre}: líneas repetidas")
    return set(pares)


def _exigir_disjuntos(primero: list[dict[str, str]], segundo: list[dict[str, str]]) -> None:
    """SNC-1: ninguna serie en los dos manifiestos, por su clave, su ruta relativa o su sha256 (sí estaciones)."""
    criterios = (("clave de serie (estacion, parametro, macro_ficha)", lambda r: tuple(r[c] for c in CLAVE_SERIE)),
                 ("ruta_relativa", lambda r: r["ruta_relativa"]), ("sha256", lambda r: r["sha256"]))
    for nombre, clave in criterios:
        comunes = {clave(r) for r in primero} & {clave(r) for r in segundo}
        if comunes:
            raise ErrorSinca(f"MC-10: los dos manifiestos deben ser disjuntos por serie; comparten {len(comunes)} por "
                             f"{nombre}, la primera {min(comunes)} (SNC-1)")


def leer_manifiestos(raiz, huellas: dict[str, str]) -> pd.DataFrame:
    """Los dos manifiestos (SNC-1), con ``COLUMNAS_MANIFIESTO``: las columnas del descargador salvo
    ``CAMPOS_NO_EXPUESTOS`` (todas de texto) más ``manifiesto`` (el nombre del archivo), en el orden de los archivos.
    Exige las seis huellas, ``SHA256SUMS`` coherentes, rutas relativas seguras, conteos enteros, manifiestos
    disjuntos por serie y una región por estación."""
    raiz = Path(raiz)
    esperadas = _huellas_esperadas(huellas)
    datos = {n: _leer_con_huella(raiz, n, esperadas[n]) for n in ARCHIVOS_HUELLA}
    registros: list[dict[str, str]] = []
    por_manifiesto: list[list[dict[str, str]]] = []
    for sufijo, nombre in zip(SUFIJOS, MANIFIESTOS):
        filas = _filas_csv(datos[nombre], nombre)
        propias = []
        for fila in filas:
            r = dict(zip(CAMPOS_MANIFIESTO, fila))
            _ruta_relativa_segura(r["ruta_relativa"])
            if not _RE_SHA.fullmatch(r["sha256"]):
                raise ErrorSinca(f"{nombre}: sha256 inválido en {r['ruta_relativa']}")
            for campo in CAMPOS_ENTEROS:
                _entero(r[campo], f"{nombre}: {campo} de {r['ruta_relativa']}")
            for campo in ("region", "estacion", "parametro"):
                if not r[campo].strip():
                    raise ErrorSinca(f"{nombre}: {campo} vacío en {r['ruta_relativa']}")
            r[COLUMNA_MANIFIESTO] = nombre
            propias.append(r)
        sumas = _sumas(datos[f"SHA256SUMS{sufijo}.txt"], f"SHA256SUMS{sufijo}.txt")
        if {(r["sha256"], r["ruta_relativa"]) for r in propias} != sumas or len(sumas) != len(propias):
            raise ErrorSinca(f"{nombre} y SHA256SUMS{sufijo}.txt no listan las mismas series")
        por_manifiesto.append(propias)
        registros += propias
    _exigir_disjuntos(*por_manifiesto)
    rutas = [r["ruta_relativa"] for r in registros]
    if len(set(rutas)) != len(rutas):
        raise ErrorSinca("una misma ruta relativa aparece dos veces en los manifiestos")
    region_de: dict[str, str] = {}
    for r in registros:
        if region_de.setdefault(r["estacion"], r["region"]) != r["region"]:
            raise ErrorSinca(f"la estación {r['estacion']} aparece con dos regiones")
    tabla = pd.DataFrame({c: pd.array([r[c] for r in registros], dtype="string") for c in COLUMNAS_MANIFIESTO})
    return tabla


# ---------------------------------------------------------------------------
# Elección (SNC-2 a SNC-4)
# ---------------------------------------------------------------------------
def _numero_altura(texto: str) -> float | None:
    m = _RE_ALTURA.fullmatch(texto.strip())
    if not m:
        return None
    x = float(m.group(1).replace(",", "."))
    return x if math.isfinite(x) and x > 0 else None


def altura_de(altura_ficha: str, macro_ficha: str) -> tuple[float | None, str]:
    """(altura en m, fuente) de una serie (SNC-3): fuente «ficha» o «macro»; sin altura, (None, motivo) con motivo
    «sin_altura» o «altura_discrepante»."""
    de_ficha = _numero_altura(_texto(altura_ficha))
    m = _RE_MACRO.fullmatch(_texto(macro_ficha).strip())
    de_macro = float(int(m.group(1))) if m and int(m.group(1)) > 0 else None
    if de_ficha is not None and de_macro is not None and de_ficha != de_macro:
        return None, "altura_discrepante"
    if de_ficha is not None:
        return de_ficha, "ficha"
    if de_macro is not None:
        return de_macro, "macro"
    return None, "sin_altura"


def _motivo_previo(r: Mapping[str, str]) -> str | None:
    parametro = r["parametro"]
    if parametro not in tipos.VARIABLES_SINCA:
        return "variable_no_autorizada"
    if r["accion"] not in ACCIONES_PUBLICADAS:
        return "accion_no_publicada"
    if r["unidad_ficha"].strip() != UNIDADES[parametro]:
        return "unidad_distinta"
    if r["marca_temporal"] != RELOJ_FUENTE:
        return "marca_temporal_distinta"
    if r["politica_temporal_sha256"] != SHA_POLITICA_TEMPORAL:
        return "politica_temporal_distinta"
    return None


def _clasificar(manifiesto) -> tuple[list[dict], list[dict]]:
    """(elegidas, descartadas), cada serie del manifiesto en una de las dos."""
    _exigir_columnas(manifiesto, COLUMNAS_MANIFIESTO, "manifiesto")
    registros = [{c: _texto(v) for c, v in fila.items()} for fila in manifiesto.to_dict("records")]
    descartadas, candidatas = [], {}
    for r in registros:
        motivo = _motivo_previo(r)
        altura, fuente = (None, "")
        if motivo is None:
            altura, fuente = altura_de(r["altura_ficha"], r["macro_ficha"])
            if altura is None:
                motivo = fuente
        if motivo is not None:
            descartadas.append({**r, "motivo": motivo})
            continue
        objetivo = float(constantes.valor(OBJETIVO_ALTURA[r["parametro"]]))
        clave = (abs(altura - objetivo), -_entero(r["filas_con_observacion"], "filas_con_observacion"),
                 r["ruta_relativa"])
        candidatas.setdefault((r["estacion"], r["parametro"]), []).append((clave, {**r, "altura_m": altura,
                                                                                  "altura_fuente": fuente}))
    elegidas = []
    for (estacion, parametro) in sorted(candidatas, key=lambda k: (k[0], _orden_variable(k[1]))):
        lista = sorted(candidatas[(estacion, parametro)], key=lambda x: x[0])
        elegidas.append(lista[0][1])
        descartadas += [{**r, "motivo": "no_elegida"} for _, r in lista[1:]]
    return elegidas, descartadas


def series_descartadas(manifiesto, umbrales) -> pd.DataFrame:
    """Las series que no entran, con su motivo (``MOTIVOS_DESCARTE``), en el orden del manifiesto."""
    _, descartadas = _clasificar(manifiesto)
    orden = {r: k for k, r in enumerate(_texto(x) for x in manifiesto["ruta_relativa"])}
    descartadas.sort(key=lambda r: orden[r["ruta_relativa"]])
    return pd.DataFrame({c: pd.array([r[c] for r in descartadas], dtype="string") for c in COLUMNAS_DESCARTE})


def elegir_series(manifiesto, umbrales) -> pd.DataFrame:
    """Una por estación × variable (MC-10): las filas elegidas del manifiesto, más ``altura_m`` (float64) y
    ``altura_fuente``, ordenadas por estación y variable (SNC-4). ``umbrales`` no interviene."""
    elegidas, _ = _clasificar(manifiesto)
    datos = {c: pd.array([r[c] for r in elegidas], dtype="string") for c in COLUMNAS_MANIFIESTO}
    datos["altura_m"] = np.array([r["altura_m"] for r in elegidas], dtype=np.float64)
    datos["altura_fuente"] = pd.array([r["altura_fuente"] for r in elegidas], dtype="string")
    return pd.DataFrame(datos, columns=list(COLUMNAS_ELEGIDAS))


# ---------------------------------------------------------------------------
# Política temporal y veredictos (SNC-11 y SNC-12)
# ---------------------------------------------------------------------------
def leer_politica_temporal(ruta, *, sha256: str = SHA_POLITICA_TEMPORAL) -> dict:
    """``config/sinca/politica_temporal.json`` con su huella (41018e4c…), entero."""
    datos = Path(ruta).read_bytes()
    real = entorno.sha256_bytes(datos)
    if real != sha256:
        raise ErrorSinca(f"política temporal con sha256 {real}; se exige {sha256}")
    politica = json.loads(datos.decode("utf-8"))
    _bloque_sinca(politica)
    return politica


def _bloque_sinca(politica) -> Mapping[str, Any]:
    if not isinstance(politica, Mapping):
        raise TypeError("la política temporal debe ser un diccionario")
    bloque = politica["sinca"] if "sinca" in politica else politica
    if not isinstance(bloque, Mapping):
        raise ErrorSinca("la política temporal no trae el bloque «sinca»")
    for clave, esperado in POLITICA_SINCA.items():
        valor = bloque.get(clave)
        if isinstance(esperado, Mapping):
            igual = isinstance(valor, Mapping) and dict(valor) == dict(esperado)
        else:
            igual = isinstance(valor, str) and valor == esperado
        if not igual:
            raise ErrorSinca(f"política temporal: {clave} no es el de la política anclada (41018e4c…), del que "
                             "dependen R7 y las zonas IANA (SNC-12)")
    de_mas = sorted(str(k) for k in bloque if k not in POLITICA_SINCA)
    if de_mas:
        raise ErrorSinca(f"política temporal: claves {de_mas} que no están en la política anclada (SNC-12)")
    return POLITICA_SINCA


def zona_de(region: str, politica) -> str:
    """Zona IANA de una región SINCA: la de ``zonas_iana_por_region`` o, si no está, ``zona_iana_default``, de la
    política anclada (SNC-12)."""
    bloque = _bloque_sinca(politica)
    return bloque["zonas_iana_por_region"].get(str(region), bloque["zona_iana_default"])


def huella_contenido(tabla) -> str:
    """La ``huella_veredictos_contenido`` de ``reloj_sinca_v2``: sha256 del CSV de la tabla, sin índice (SNC-11)."""
    texto = tabla.to_csv(index=False)  # no-escribe: sin ruta, to_csv devuelve el texto de la huella (como el reloj)
    return entorno.sha256_bytes(texto.encode("utf-8"))


def _exigir_resumen(resumen, sha256: str, contenido: str, convencion) -> None:
    """SNC-11: el ``resumen.json`` del reloj ata la tabla, la huella del parquet y la convención elegida por T4."""
    if not isinstance(resumen, Mapping):
        raise TypeError("resumen debe ser el diccionario de resumen.json de reloj_sinca_v2")
    faltan = [c for c in CLAVES_RESUMEN if c not in resumen]
    if faltan:
        raise ErrorSinca(f"el resumen del reloj SINCA no trae {faltan} (SNC-11)")
    if resumen["schema"] != SCHEMA_RELOJ_SINCA:
        raise ErrorSinca(f"el resumen no es de reloj_sinca_v2 (schema {SCHEMA_RELOJ_SINCA}; SNC-11)")
    if resumen["politica_temporal_sha256"] != SHA_POLITICA_TEMPORAL:
        raise ErrorSinca("los veredictos no se calcularon con la política temporal anclada (41018e4c…; SNC-11)")
    if resumen["sha256_veredictos"] != sha256:
        raise ErrorSinca("el sha256 de veredictos.parquet no es el de su resumen.json (SNC-11)")
    if resumen["huella_veredictos_contenido"] != contenido:
        raise ErrorSinca("la tabla de veredictos no es la del resumen (huella_veredictos_contenido; SNC-11)")
    eleccion = resumen["convencion_civil"]
    elegida = eleccion.get("elegida") if isinstance(eleccion, Mapping) else None
    if elegida not in CONVENCIONES:
        raise ErrorSinca("el resumen no trae la convención que eligió T4 (convencion_civil.elegida; SNC-11)")
    if convencion != elegida:
        raise ErrorSinca(f"convención {convencion!r} distinta de la que eligió T4 en el resumen ({elegida!r}; SNC-11)")


def veredictos_civiles(tabla, convencion: str, *, sha256: str, resumen: Mapping[str, Any]) -> dict:
    """El argumento ``veredictos`` (SNC-11) desde la tabla de veredictos de ``reloj_sinca_v2`` (``estacion``,
    ``contaminante``, ``anio``, ``veredicto_fin`` y ``veredicto_inicio_mas_1h``), el sha256 de ``veredictos.parquet``,
    su ``resumen.json`` y la convención que eligió T4, que debe ser la del resumen."""
    columnas = ("estacion", "contaminante", "anio", *(f"veredicto_{c}" for c in CONVENCIONES))
    _exigir_columnas(tabla, columnas, "veredictos")
    if not isinstance(sha256, str) or not _RE_SHA.fullmatch(sha256):
        raise ErrorSinca("veredictos sin la huella de su tabla (sha256 de 64 cifras hexadecimales)")
    if convencion not in CONVENCIONES:
        raise ErrorSinca(f"convención de etiqueta desconocida: {convencion!r} (T4 elige siempre una; SNC-11)")
    contenido = huella_contenido(tabla)
    _exigir_resumen(resumen, sha256, contenido, convencion)
    if tabla.duplicated(["estacion", "contaminante", "anio"]).any():
        raise ErrorSinca("la tabla de veredictos repite una unidad estación × contaminante × año")
    m = tabla[f"veredicto_{convencion}"].astype(str) == VEREDICTO_CIVIL
    civiles = sorted({(str(e), int(a)) for e, a in zip(tabla.loc[m, "estacion"], tabla.loc[m, "anio"])})
    salida = {"sha256": sha256, "huella_contenido": contenido, "convencion": convencion, "hora_civil": tuple(civiles)}
    _validar_veredictos(salida)
    return salida


def _validar_veredictos(veredictos) -> tuple[str, str, str | None, frozenset[tuple[str, int]]]:
    if not isinstance(veredictos, Mapping) or set(veredictos) != set(CLAVES_VEREDICTOS):
        raise ErrorSinca(f"veredictos debe ser un diccionario con exactamente {CLAVES_VEREDICTOS} (SNC-11)")
    sha, contenido = veredictos["sha256"], veredictos["huella_contenido"]
    for huella in (sha, contenido):
        if not isinstance(huella, str) or not _RE_SHA.fullmatch(huella):
            raise ErrorSinca("veredictos sin las huellas de su tabla (sha256 de 64 cifras hexadecimales)")
    convencion = veredictos["convencion"]
    if convencion is not None and convencion not in CONVENCIONES:
        raise ErrorSinca(f"convención de etiqueta desconocida: {convencion!r}")
    civiles = set()
    for par in veredictos["hora_civil"]:
        if (not isinstance(par, (tuple, list)) or len(par) != 2
                or not isinstance(par[0], str) or isinstance(par[1], bool) or not isinstance(par[1], (int, np.integer))):
            raise ErrorSinca(f"hora_civil lleva pares (estación, año): {par!r}")
        civiles.add((par[0], int(par[1])))
    if civiles and convencion is None:
        raise ErrorSinca("hay estación-años en hora civil y falta la convención de la etiqueta civil (T4)")
    return sha, contenido, convencion, frozenset(civiles)


# ---------------------------------------------------------------------------
# Serie: formato, reloj y control mínimo (SNC-5 a SNC-10)
# ---------------------------------------------------------------------------
def parsear_serie(texto: str) -> tuple[np.ndarray, np.ndarray, dict[str, int]]:
    """(etiquetas, valores, conteos) de una serie del exportador (SNC-5, SNC-6): las etiquetas locales
    (``datetime64[h]``, sin zona) y los valores (NaN si no es numérico) de las filas con campo no vacío; los conteos
    ``filas``, ``filas_con_observacion`` y ``filas_no_numericas`` como los da ``analizar_respuesta``."""
    lineas = [(n, x) for n, x in enumerate(texto.splitlines(), start=1) if x.strip()]   # n: línea del archivo
    if not lineas or not lineas[0][1].upper().startswith(ENCABEZADO):
        raise ErrorSinca("serie sin encabezado FECHA")
    dias: dict[str, np.datetime64] = {}
    etiquetas, valores = [], []
    filas = con_obs = no_num = 0
    for n, linea in lineas[1:]:                     # los errores dan la línea, no su contenido (SNC-5)
        m = _RE_DATO.match(linea.strip())
        if not m:
            raise ErrorSinca(f"línea {n}: fila no horaria (no calza con AAMMDD;HHMM;…)")
        fecha, hora, resto = m.groups()
        filas += 1
        if fecha not in dias:                       # toda etiqueta se valida, también la de una fila vacía
            try:
                dias[fecha] = np.datetime64(datetime.strptime(fecha, "%y%m%d").date(), "D")
            except ValueError as exc:
                raise ErrorSinca(f"línea {n}: fecha AAMMDD inválida") from exc
        hh, mm = int(hora[:2]), int(hora[2:])
        if mm != 0 or not 0 <= hh < HORAS_DIA:
            raise ErrorSinca(f"línea {n}: hora de etiqueta que no es HH00 con HH de 00 a 23")
        campo = resto.split(";")[0].strip()
        if not campo:
            continue
        try:
            x = float(campo.replace(",", "."))
        except ValueError:
            x = math.nan
        if math.isfinite(x):
            con_obs += 1
        else:
            no_num += 1
            x = math.nan
        etiquetas.append(dias[fecha] + np.timedelta64(hh, "h"))
        valores.append(x)
    conteos = {"filas": filas, "filas_con_observacion": con_obs, "filas_no_numericas": no_num}
    return (np.array(etiquetas, dtype="datetime64[h]"), np.array(valores, dtype=np.float64), conteos)


def _fin_civil(etiqueta: datetime, zona: ZoneInfo, convencion: str) -> tuple[datetime, str, datetime | None]:
    """(fin del intervalo en UTC, sin zona; tipo; fin alternativo) de una etiqueta civil (SNC-7)."""
    pared = etiqueta if convencion == "fin" else etiqueta - _UNA_HORA
    a, b = pared.replace(tzinfo=zona, fold=0), pared.replace(tzinfo=zona, fold=1)
    oa, ob = a.utcoffset(), b.utcoffset()
    alternativo = None
    if oa == ob:
        tipo, desfase = TIPO_UNIVOCA, oa
    elif oa > ob:                                   # hora repetida: fold 0 es la primera ocurrencia
        estandar = [x for x in (a, b) if x.dst() == timedelta(0)]
        if len(estandar) != 1:
            raise ErrorSinca(f"hora repetida sin una única ocurrencia estándar: {pared.isoformat()} en {zona.key}")
        tipo, desfase = TIPO_AMBIGUA, estandar[0].utcoffset()
        otro = ob if desfase == oa else oa
        alternativo = pared - otro
    else:                                           # hora inexistente: se desplaza hacia adelante
        tipo, desfase = TIPO_INEXISTENTE, oa
    utc = pared - desfase
    corrimiento = timedelta(0) if convencion == "fin" else _UNA_HORA
    return utc + corrimiento, tipo, (alternativo + corrimiento if alternativo is not None else None)


def horas_fin_utc(etiquetas, civil, *, zona: str | None = None, convencion: str | None = None) -> pd.DataFrame:
    """Hora UTC del fin del intervalo de cada etiqueta local (SNC-7): ``h`` (int32), ``tipo`` (``TIPO_*``) y
    ``h_alternativa`` (Int32: la otra ocurrencia de una hora civil repetida). ``civil`` dice, etiqueta por
    etiqueta, si su estación-año va en hora civil; entonces hacen falta ``zona`` y ``convencion``."""
    loc = np.asarray(etiquetas, dtype="datetime64[h]")
    civil = np.asarray(civil, dtype=bool)
    if civil.shape != loc.shape:
        raise ErrorSinca("etiquetas y civil deben tener el mismo largo")
    h = (loc - _EPOCA_H64).astype(np.int64) + DESFASE_FIJO_H
    tipo = np.full(loc.shape, TIPO_FIJO, dtype=object)
    alt = pd.array([pd.NA] * len(loc), dtype="Int64")
    if civil.any():
        if convencion not in CONVENCIONES or not isinstance(zona, str):
            raise ErrorSinca("hay etiquetas en hora civil: hacen falta la zona IANA y la convención de la etiqueta")
        tz = ZoneInfo(zona)
        cache: dict[np.datetime64, tuple[int, str, int | None]] = {}
        for k in np.flatnonzero(civil):
            e = loc[k]
            if e not in cache:
                fin, t, otro = _fin_civil(e.astype(datetime), tz, convencion)
                cache[e] = (_h_de(fin), t, _h_de(otro) if otro is not None else None)
            h[k], tipo[k], otro_h = cache[e]
            if otro_h is not None:
                alt[k] = otro_h
    if len(h) and (h.min() < np.iinfo(np.int32).min or h.max() > np.iinfo(np.int32).max):
        raise ErrorSinca("hora UTC fuera de int32")
    return pd.DataFrame({"h": h.astype(np.int32), "tipo": pd.array(tipo, dtype="string"),
                         "h_alternativa": alt.astype("Int32")})


def control_minimo(variable: str, valores, umbrales) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(valor, válido, recortada) de las observaciones de una variable (SNC-9, SNC-10): rango de §2.3 inclusivo y,
    en RHUM, el recorte de (HR_SAT, HR_RECORTE_MAX] a HR_SAT. NaN nunca es válido."""
    if variable not in RANGO:
        raise ErrorSinca(f"variable SINCA no autorizada: {variable!r} (MC-10, punto 6)")
    v = np.asarray(valores, dtype=np.float64)
    bajo, alto = (float(umbrales.a(i)) for i in RANGO[variable])
    valido = np.isfinite(v) & (v >= bajo) & (v <= alto)
    salida = v.copy()
    recortada = np.zeros(v.shape, dtype=bool)
    if variable == "RHUM":
        saturacion, tope = float(umbrales.a("HR_SAT")), float(umbrales.a("HR_RECORTE_MAX"))
        recortada = valido & (v > saturacion) & (v <= tope)
        salida[recortada] = saturacion
    return salida, valido, recortada


def _unir_colisiones(h: np.ndarray, valor: np.ndarray, valido: np.ndarray, variable: str):
    """SNC-8: una fila por hora UTC; las colisiones se promedian (WDIR: inválida y sin valor)."""
    orden = np.argsort(h, kind="stable")
    h, valor, valido = h[orden], valor[orden], valido[orden]
    unicas, inicio, cuantas = np.unique(h, return_index=True, return_counts=True)
    v_out, ok_out = valor[inicio].copy(), valido[inicio].copy()
    colisiones = []
    for j in np.flatnonzero(cuantas > 1):
        sl = slice(inicio[j], inicio[j] + cuantas[j])
        vs, oks = valor[sl], valido[sl]
        colisiones.append([int(unicas[j]), int(cuantas[j])])
        if variable == VARIABLE_ANGULAR:
            v_out[j], ok_out[j] = math.nan, False
        elif oks.any():
            v_out[j], ok_out[j] = float(np.mean(vs[oks])), True
        else:
            finitos = vs[np.isfinite(vs)]
            v_out[j], ok_out[j] = (float(np.mean(finitos)) if len(finitos) else math.nan), False
    return unicas, v_out, ok_out, colisiones


def _leer_serie(raiz: Path, fila: Mapping[str, Any], bloque, umbrales, convencion, civiles) -> tuple[pd.DataFrame, dict]:
    r = {c: _texto(fila[c]) for c in COLUMNAS_SERIE}
    estacion, parametro, ruta = r["estacion"], r["parametro"], r["ruta_relativa"]
    if parametro not in tipos.VARIABLES_SINCA:
        raise ErrorSinca(f"{ruta}: variable no autorizada {parametro!r} (MC-10, punto 6)")
    archivo = _ruta_bajo_raiz(raiz, _ruta_relativa_segura(ruta))     # SNC-15, antes de leer un byte
    if archivo.stat().st_size != _entero(r["bytes"], "bytes"):
        raise ErrorSinca(f"{ruta}: tamaño en disco distinto del del manifiesto (SNC-5)")
    datos = archivo.read_bytes()
    if entorno.sha256_bytes(datos) != r["sha256"]:
        raise ErrorSinca(f"{ruta}: sha256 distinto del del manifiesto (SNC-5)")
    try:
        texto = datos.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ErrorSinca(f"{ruta} no es UTF-8") from exc
    try:
        etiquetas, valores, conteos = parsear_serie(texto)
    except ErrorSinca as exc:
        raise ErrorSinca(f"{ruta}: {exc}") from exc
    for clave, n in conteos.items():
        if n != _entero(r[clave], clave):
            raise ErrorSinca(f"{ruta}: {clave} de la serie distinto del del manifiesto (SNC-5)")
    anios = pd.DatetimeIndex(etiquetas).year.to_numpy(np.int64)      # año local de la etiqueta (R7)
    anios_civiles = sorted({a for (e, a) in civiles if e == estacion})
    civil = np.isin(anios, anios_civiles)
    zona = zona_de(r["region"], {"sinca": bloque})
    reloj = horas_fin_utc(etiquetas, civil, zona=zona, convencion=convencion)
    valor, valido_etiqueta, recortada = control_minimo(parametro, valores, umbrales)
    h, valor, valido, colisiones = _unir_colisiones(reloj["h"].to_numpy(np.int64), valor, valido_etiqueta,
                                                    parametro)
    tabla = pd.DataFrame({
        "estacion": pd.array([estacion] * len(h), dtype="string"),
        "h": h.astype(np.int32),
        "variable": pd.array([parametro] * len(h), dtype="string"),
        "valor": valor.astype(np.float64),
        "valido": valido.astype(bool),
        "serie": pd.array([ruta] * len(h), dtype="string"),
    })
    tipos.validar_esquema(tabla, tipos.ESQUEMA_SINCA_HORA, nombre=f"serie SINCA {ruta}")
    ambiguas = reloj["tipo"] == TIPO_AMBIGUA
    registro = {
        "serie": ruta, "estacion": estacion, "variable": parametro, "manifiesto": _texto(fila.get(COLUMNA_MANIFIESTO)),
        "region": r["region"], "zona": zona if anios_civiles else None, **conteos,
        "fuera_de_rango": int((np.isfinite(valores) & ~valido_etiqueta).sum()),
        "recortadas": int(recortada.sum()), "horas": int(len(h)), "validas": int(valido.sum()),
        "anios_civiles": sorted(set(anios_civiles) & set(anios.tolist())),
        "etiquetas_ambiguas": int(ambiguas.sum()),
        "etiquetas_inexistentes": int((reloj["tipo"] == TIPO_INEXISTENTE).sum()),
        "alternativas": [[int(a), int(b)] for a, b in zip(reloj.loc[ambiguas, "h"], reloj.loc[ambiguas, "h_alternativa"])],
        "colisiones": colisiones,
    }
    return tabla, registro


def leer_serie(raiz, fila, politica_temporal, umbrales, *, veredictos) -> tuple[pd.DataFrame, dict]:
    """Una serie elegida (una fila de ``elegir_series``) en ``ESQUEMA_SINCA_HORA``, y su registro (SNC-13)."""
    bloque = _bloque_sinca(politica_temporal)
    _, _, convencion, civiles = _validar_veredictos(veredictos)
    return _leer_serie(Path(raiz), fila, bloque, umbrales, convencion, civiles)


def series_horarias(raiz, elegidas, politica_temporal, umbrales, *, veredictos) -> pd.DataFrame:
    """``tipos.ESQUEMA_SINCA_HORA`` de todas las series elegidas (una por estación × variable), ordenada por
    estación, variable y ``h``, con el registro en ``attrs["registro_sinca"]`` (SNC-13)."""
    bloque = _bloque_sinca(politica_temporal)
    sha, contenido, convencion, civiles = _validar_veredictos(veredictos)
    _exigir_columnas(elegidas, COLUMNAS_SERIE, "elegidas")
    filas = elegidas.to_dict("records")
    claves = [(_texto(f["estacion"]), _texto(f["parametro"])) for f in filas]
    if len(set(claves)) != len(claves):
        raise ErrorSinca("MC-10: una sola serie por estación × variable")
    for _, parametro in claves:
        if parametro not in tipos.VARIABLES_SINCA:
            raise ErrorSinca(f"variable SINCA no autorizada: {parametro!r} (MC-10, punto 6)")
    orden = sorted(range(len(filas)), key=lambda k: (claves[k][0], _orden_variable(claves[k][1])))
    partes, registros = [], []
    for k in orden:
        tabla, registro = _leer_serie(Path(raiz), filas[k], bloque, umbrales, convencion, civiles)
        partes.append(tabla)
        registros.append(registro)
    salida = pd.concat(partes, ignore_index=True) if partes else tipos.tabla_vacia(tipos.ESQUEMA_SINCA_HORA)
    tipos.validar_esquema(salida, tipos.ESQUEMA_SINCA_HORA, nombre="series SINCA")
    salida.attrs = {"esquema": tipos.ESQUEMA_SINCA_HORA.version,
                    "registro_sinca": {"politica_temporal_sha256": SHA_POLITICA_TEMPORAL, "veredictos_sha256": sha,
                                       "veredictos_huella_contenido": contenido, "convencion": convencion,
                                       "series": registros}}
    return salida
