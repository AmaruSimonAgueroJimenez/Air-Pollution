#!/usr/bin/env python3
"""descargar_sinca_ampliacion.py — Todo lo que SINCA publica, sin tocar lo previo.

Amplía las descargas SINCA a todas las estaciones del catálogo regional y a
todas las series que publica cada ficha (meteorología y contaminantes), sin
modificar ``data/sinca/`` (contaminantes usados por modelos sellados) ni los
registros previos de ``data/sinca_meteorologia/``.

Fases (``--fase``):

``catalogo``
    Descarga las 16 páginas regionales de SINCA, el listado del mapa en línea
    (``listadomapa2k19``) y la ficha de cada estación (por su id). Guarda las
    fuentes comprimidas con SHA-256 en ``<ampliacion>/catalogo/<marca_utc>/`` y
    escribe ``estaciones_fichas.csv`` (nombre, región, comuna, lat, lon,
    propietario, operador, red, calificación) y ``series_fichas.csv`` (cada
    serie que la ficha enlaza).
``inventario``
    Sin red: compara las series de las fichas con lo que ya hay en disco
    (``data/sinca/manifiesto_descarga.csv`` y los manifiestos de
    ``data/sinca_meteorologia/``) y escribe los pendientes y un plan con número
    de series, volumen y tiempo estimados.
``meteorologia``
    Descarga las series meteorológicas pendientes (TEMP, RHUM, WSPD, WDIR,
    GLOB, PRES, RAIN y cualquier otra que la ficha enlace) en
    ``data/sinca_meteorologia/<PARAM>/`` con la misma estructura de nombres, en
    archivos nuevos, y con manifiesto, no disponibles y SHA256SUMS fechados
    (``*_<sufijo>``). Nunca abre para escritura los registros previos.
``actualizacion``
    Actualiza las series horarias de los seis contaminantes del contrato que ya
    están en ``data/sinca`` (sin tocarla), desde su último día en disco hasta
    ``--hasta``, en archivos nuevos bajo ``<ampliacion>/actualizacion_configuradas/``
    con manifiesto, SHA256SUMS y una copia byte a byte del maestro georreferenciado.
``contaminantes``
    Descarga las series de contaminantes pendientes (horarias, diarias y
    discretas; PM2,5, PM10, SO2, NO2, O3, CO, NO, NOx, CH4, HCT, HCNM, TRS,
    carbono, metales…) en ``<ampliacion>/<contaminante>/<resolucion>/`` con un
    manifiesto de las mismas columnas que ``data/sinca``, ``no_disponibles.csv``,
    ``SHA256SUMS.txt`` y ``estado_validacion_series.csv`` (filas validadas,
    preliminares y no validadas de cada serie).

Reglas de seguridad: nunca sobrescribe ni borra un archivo publicado (enlace
duro que falla si el destino existe); conserva un piso de espacio libre
(``--piso-gb``); un solo escritor por carpeta (bloqueo ``fcntl``); peticiones
secuenciales (una conexión por proceso) y sólo hacia sinca.mma.gob.cl.

Rango: cada serie se pide desde ``min(--desde, primera fecha de la ficha)``,
sin bajar de ``--desde-piso``, hasta ``--hasta``. Reloj: hora civil local SINCA
sin desfase (``config/sinca/politica_temporal.json``); no se convierte a UTC.

Uso:
  python descargar_sinca_ampliacion.py --fase catalogo
  python descargar_sinca_ampliacion.py --fase inventario
  python descargar_sinca_ampliacion.py --fase meteorologia --sufijo 20261024b
  python descargar_sinca_ampliacion.py --fase contaminantes
"""
from __future__ import annotations

import argparse
import csv
import fcntl
import gzip
import hashlib
import html
import json
import math
import os
import re
import signal
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import DATA, REPO_ROOT, SINCA, ensure_dir, get_logger, retry  # noqa: E402
import descargar_sinca_meteorologia as smet  # noqa: E402

log = get_logger("sinca_ampliacion")

SCRIPT_VERSION = "1.1.0"
SCRIPT_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
MODULO_METEOROLOGIA_SHA256 = smet.SCRIPT_SHA256
HOST = "sinca.mma.gob.cl"
PORTAL = f"https://{HOST}"
URL_REGION = PORTAL + "/index.php/region/index/id/{region}"
URL_MAPA = PORTAL + "/index.php/json/listadomapa2k19/"
URL_FICHA = PORTAL + "/index.php/estacion/index/id/{id}"
REGIONES = ("XV", "I", "II", "III", "IV", "V", "M", "VI", "VII", "XVI",
            "VIII", "IX", "XIV", "X", "XI", "XII")
AGENTE = {"User-Agent": f"AirPollutionChile-reproducible-pipeline/{SCRIPT_VERSION}"}

AMPLIACION_POR_OMISION = DATA / "sinca_ampliacion_20261024"
METEOROLOGIA_POR_OMISION = DATA / "sinca_meteorologia"
MANIFIESTO_SINCA = SINCA / "manifiesto_descarga.csv"
POLITICA_TEMPORAL_RUTA = REPO_ROOT / "config" / "sinca" / "politica_temporal.json"
CONFIG_ESTACIONES = REPO_ROOT / "config" / "sinca" / "config_sinca_estaciones.json"

# Código SINCA (carpeta Cal/) -> nombre canónico. Los seis primeros son los de
# data/sinca (descargar_sinca.PARAM_CODES); un código nuevo se descarga igual
# con su código en minúsculas como nombre.
CONTAMINANTES = {
    "PM25": "pm25", "PM10": "pm10", "0001": "so2", "0003": "no2",
    "0008": "o3", "0004": "co", "0002": "no", "0NOX": "nox", "0CH4": "ch4",
    "THCM": "hct", "NMHC": "hcnm", "CORG": "carbono_organico",
    "CTOT": "carbono_total", "TRSG": "trs", "PM1D": "pm10", "PM2D": "pm25",
    "ARSE": "arsenico", "00Cu": "cobre", "00Ni": "niquel", "00Pb": "plomo",
}
# Parámetro meteorológico (carpeta Met/) -> (variable, unidad por omisión).
METEOROLOGIA = dict(smet.PARAMETROS) | {
    "GLOB": ("radiacion_global", "W/m2"),
    "PRES": ("presion_atmosferica", "hPa"),
    "RAIN": ("precipitacion", "mm"),
}
# Bytes por fila observados en las descargas previas (para el plan).
BYTES_POR_FILA = 17
SEGUNDOS_HORARIA, SEGUNDOS_DIARIA = 4.5, 1.2

# Mismas columnas y orden que data/sinca/manifiesto_descarga.csv ...
CAMPOS_MANIFIESTO_SINCA = [
    "region", "estacion", "nombre", "contaminante", "resolucion",
    "desde", "hasta", "ruta", "bytes", "sha256", "filas",
    "filas_con_observacion", "primera_marca", "ultima_marca",
    "primera_observacion", "ultima_observacion", "url_fuente",
    "accion", "script_version", "script_sha256", "config_estaciones_sha256",
    "marca_temporal", "politica_utc", "politica_temporal_sha256", "registrado_utc",
]
# ... más las que pide la auditoría (sinca_al_modelo, §3.1 y §3.4): macro y
# huella de la ficha, unidad, técnica, propietario y operador.
CAMPOS_MANIFIESTO_CONTAMINANTES = CAMPOS_MANIFIESTO_SINCA + [
    "codigo_sinca", "macro_ficha", "macro_exportada", "parametro_ficha",
    "unidad_ficha", "tecnica_ficha", "primer_registro_ficha", "ultimo_registro_ficha",
    "desde_ficha", "hasta_ficha", "id_sinca", "propietario", "operador", "grupo",
    "ficha_sha256", "catalogo",
]
# Lo que preparar_sinca_modelado.load_inputs acepta (GASES, sólo horario): va a
# manifiesto_descarga.csv; el resto, a manifiesto_descarga_otras_series.csv.
CONTAMINANTES_CONTRATO = ("pm25", "pm10", "no2", "o3", "so2", "co")
CAMPOS_FALTANTES_CONTAMINANTES = [
    "region", "estacion", "nombre", "contaminante", "resolucion",
    "desde", "hasta", "motivo", "codigo_sinca", "macro_exportada", "url_fuente",
    "registrado_utc",
]
CAMPOS_VALIDACION = [
    "ruta_relativa", "region", "estacion", "nombre", "contaminante",
    "resolucion", "codigo_sinca", "macro_exportada", "parametro_ficha",
    "unidad_ficha", "tecnica_ficha", "primer_registro_ficha",
    "ultimo_registro_ficha", "filas", "filas_con_observacion",
    "filas_validadas", "filas_preliminares", "filas_no_validadas",
    "primera_validada", "ultima_validada", "primera_preliminar",
    "ultima_preliminar", "primera_no_validada", "ultima_no_validada",
    "estado_validacion",
]
CAMPOS_ESTACIONES = [
    "id_sinca", "region_sinca", "estacion", "nombre", "region", "provincia",
    "comuna", "lat", "lon", "fuente_latlon", "utm_e", "utm_n", "huso",
    "propietario", "operador", "red", "calificacion", "fuente_calificacion",
    "publica_pagina_regional", "en_linea", "con_meteorologia",
    "empresa_mapa", "recepcion_datos", "inicio_operacion", "acreditacion",
    "representatividad", "configurada", "series_contaminantes",
    "series_meteorologicas", "ficha_url", "ficha_ruta", "ficha_sha256",
    "pagina_regional",
]
CAMPOS_SERIES = [
    "tipo", "region_sinca", "estacion", "id_sinca", "nombre", "codigo",
    "parametro", "macro_ficha", "resolucion", "parametro_ficha", "unidad_ficha",
    "altura_ficha", "tecnica_ficha", "primer_registro_ficha",
    "ultimo_registro_ficha", "desde_ficha", "hasta_ficha", "ficha_sha256",
]


class DetencionSegura(smet.DetencionSegura):
    """Condición que obliga a detener la corrida completa (espacio, señal)."""


# --------------------------------------------------------------------------
# Red (sólo SINCA)
# --------------------------------------------------------------------------
def _exigir_sinca(url: str) -> str:
    if urlparse(url).hostname != HOST:
        raise ValueError(f"destino de red no permitido: {url}")
    return url


def _pedir_pagina_una_vez(url: str) -> bytes:
    respuesta = requests.get(_exigir_sinca(url), timeout=120, headers=AGENTE)
    respuesta.raise_for_status()
    return respuesta.content


pedir_pagina = retry(n=4, base=5.0, exc=(requests.RequestException,))(_pedir_pagina_una_vez)


def _pedir_exportador_una_vez(params: dict) -> str:
    respuesta = requests.get(_exigir_sinca(smet.BASE), params=params, timeout=300,
                             headers=AGENTE)
    respuesta.raise_for_status()
    return respuesta.text


pedir_exportador = retry(n=4, base=5.0, exc=(requests.RequestException,))(
    _pedir_exportador_una_vez)


# --------------------------------------------------------------------------
# Catálogo: páginas regionales, listado del mapa y fichas
# --------------------------------------------------------------------------
_RE_TR = re.compile(r"<tr\b([^>]*)>(.*?)</tr>", re.S | re.I)
_RE_ID = re.compile(r'estacion/index/id/(\d+)"[^>]*>([^<]+)</a>')
_RE_MACROPATH = re.compile(r"macropath=\./([A-Za-z0-9]+)/([A-Za-z0-9]+)/(Cal|Met)/")
_RE_RED = re.compile(r'<a title="([^"]*)"[^>]*>\s*<span class="icon-red">')
_RE_COMUNA = re.compile(r'<div class="comuna">([^<]*)</div>')


def parsear_pagina_regional(texto: str, region_portal: str) -> list[dict]:
    """Filas de la tabla regional: id, nombre, comuna, íconos y clave SINCA."""
    inicio = texto.find('id="tablaRegional"')
    if inicio < 0:
        raise ValueError(f"la página regional {region_portal} no trae tablaRegional")
    filas = []
    for _attrs, cuerpo in _RE_TR.findall(texto[inicio:]):
        enlace = _RE_ID.search(cuerpo)
        if not enlace:
            continue
        claves = sorted({(r, e) for r, e, _ in _RE_MACROPATH.findall(cuerpo)})
        red = _RE_RED.search(cuerpo)
        comuna = _RE_COMUNA.search(cuerpo)
        filas.append({
            "id_sinca": enlace.group(1),
            "nombre_regional": html.unescape(enlace.group(2)).strip(),
            "comuna_regional": html.unescape(comuna.group(1)).strip() if comuna else "",
            "pagina_regional": region_portal,
            "publica_pagina_regional": "si" if "icon-publico" in cuerpo else "no",
            "en_linea": "si" if "icon-online" in cuerpo else "no",
            "con_meteorologia": "si" if "icon-meteo" in cuerpo else "no",
            "red_regional": html.unescape(red.group(1)).strip() if red else "",
            "claves_regionales": claves,
        })
    return filas


_RE_GENERAL = re.compile(r'<th class="right">\s*(.*?)\s*</th>\s*<td class="left">(.*?)</td>',
                         re.S | re.I)
_RE_LATLNG = re.compile(r"google\.maps\.LatLng\(\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\)")
_RE_H1 = re.compile(r"<h1>\s*(.*?)\s*</h1>", re.S)
_RE_UTM = re.compile(r"([\d.,]+)\s*E\s+([\d.,]+)\s*N", re.I)
_RE_ACREDITACION = re.compile(r"Acreditaci[oó]n\s+ENAC[^<]*", re.I)


def _texto(fragmento: str) -> str:
    return smet._texto_plano(fragmento)


def parsear_ficha_general(texto: str) -> dict:
    """Datos generales de la ficha (tal como los publica SINCA, sin corregir)."""
    general = {_texto(k): _texto(v) for k, v in _RE_GENERAL.findall(texto)}
    titulo = _RE_H1.search(texto)
    nombre = _texto(titulo.group(1)) if titulo else ""
    nombre = re.sub(r"^Estaci[oó]n\s+", "", nombre)
    latlng = _RE_LATLNG.search(texto)
    utm = _RE_UTM.search(general.get("Coordenadas UTM", ""))
    acreditacion = _RE_ACREDITACION.search(texto)
    representatividad = []
    rep_ini = texto.find('class="stn-rep"')
    if rep_ini >= 0:
        bloque = texto[rep_ini:texto.find("</table>", rep_ini)]
        cuerpo = bloque[bloque.find("<tbody>"):]
        for _attrs, fila in _RE_TR.findall(cuerpo):
            celdas = [_texto(c[1]) for c in smet._RE_CELDA.findall(fila)]
            if len(celdas) >= 3:
                representatividad.append(f"{celdas[0]}: {celdas[1]} a {celdas[2]}")
    region = general.get("Región", "")
    if region and not region.lower().startswith("región"):
        region = f"Región {region}"
    return {
        "nombre": nombre,
        "propietario": general.get("Propietario", ""),
        "operador": general.get("Operador", ""),
        "region": region,
        "provincia": general.get("Provincia", ""),
        "comuna": general.get("Comuna", ""),
        "utm_e": utm.group(1) if utm else "",
        "utm_n": utm.group(2) if utm else "",
        "huso": general.get("Huso horario", ""),
        "recepcion_datos": general.get("Recepción de datos", ""),
        "inicio_operacion": general.get("Inicio de operación reportada", ""),
        "lat": latlng.group(1) if latlng else "",
        "lon": latlng.group(2) if latlng else "",
        "acreditacion": (_texto(acreditacion.group(0)) if acreditacion
                         else ("Acreditada (nombre)" if "(Acreditada)" in nombre else "")),
        "representatividad": " | ".join(representatividad),
    }


_RE_ENLACE_CAL = re.compile(
    r"macropath=\./([A-Za-z0-9]+)/([A-Za-z0-9]+)/Cal/([A-Za-z0-9]+)"
    r"&(?:amp;)?macro=([A-Za-z0-9]+)\.([A-Za-z]+)\.([A-Za-z]+)"
    r"(?:&(?:amp;)?from=(\d*))?(?:&(?:amp;)?to=(\d*))?"
)
_RE_NOMBRE_CODIGO = re.compile(r'<a name="([A-Za-z0-9]+)">')
_RE_UNIDAD = re.compile(r"\(([^()]*)\)\s*$")


def contaminante_y_resolucion(codigo: str, tipo: str, resolucion: str) -> tuple[str, str]:
    """``PM25.horario.horario`` -> (pm25, horario); ``PM1D.discreto.diario``
    -> (pm10_discreto, diario)."""
    nombre = CONTAMINANTES.get(codigo, codigo.lower())
    if tipo != resolucion:
        nombre = f"{nombre}_{tipo}"
    return nombre, resolucion


def parsear_series_contaminantes(texto: str, region: str, estacion: str) -> list[dict]:
    """Series ``Cal/`` que la ficha enlaza (diarias, horarias y discretas)."""
    meta: dict[str, dict] = {}
    series: dict[tuple, dict] = {}
    for fila in smet._RE_FILA.findall(texto):
        nombre_codigo = _RE_NOMBRE_CODIGO.search(fila)
        if nombre_codigo and "/Met/" not in fila:
            celdas = [_texto(c[1]) for c in smet._RE_CELDA.findall(fila)]
            encabezado = celdas[0] if celdas else ""
            unidad = _RE_UNIDAD.search(encabezado)
            meta[nombre_codigo.group(1)] = {
                "parametro_ficha": _RE_UNIDAD.sub("", encabezado).strip(),
                "unidad_ficha": (unidad.group(1).split(" - ")[-1].strip() if unidad else ""),
                "primer_registro_ficha": celdas[1] if len(celdas) > 1 else "",
                "ultimo_registro_ficha": celdas[2] if len(celdas) > 2 else "",
                "tecnica_ficha": celdas[3] if len(celdas) > 3 else "",
            }
        for reg, est, carpeta, codigo, tipo, resol, desde, hasta in _RE_ENLACE_CAL.findall(fila):
            if reg != region or est != estacion or codigo != carpeta:
                continue
            clave = (codigo, tipo, resol)
            previa = series.get(clave)
            if previa:
                desdes = [x for x in (previa["desde_ficha"], desde) if x]
                hastas = [x for x in (previa["hasta_ficha"], hasta) if x]
                previa["desde_ficha"] = min(desdes, key=_fecha_ficha_orden) if desdes else ""
                previa["hasta_ficha"] = max(hastas, key=_fecha_ficha_orden) if hastas else ""
                continue
            contaminante, resolucion = contaminante_y_resolucion(codigo, tipo, resol)
            series[clave] = {
                "tipo": "contaminante", "region_sinca": region, "estacion": estacion,
                "codigo": codigo, "parametro": contaminante,
                "macro_ficha": f"{codigo}.{tipo}.{resol}", "resolucion": resolucion,
                "altura_ficha": "", "desde_ficha": desde, "hasta_ficha": hasta,
            }
    for (codigo, _t, _r), serie in series.items():
        serie.update({k: v for k, v in meta.get(codigo, {}).items()})
    return [series[k] for k in sorted(series)]


def _fecha_ficha_orden(yymmdd: str) -> date:
    fecha = fecha_de_ficha(yymmdd)
    return fecha or date.max


def fecha_de_ficha(yymmdd: str) -> date | None:
    """``yymmdd`` de los enlaces de la ficha (pivote de dos dígitos: 69/70)."""
    try:
        return datetime.strptime(yymmdd, "%y%m%d").date()
    except (TypeError, ValueError):
        return None


def series_de_ficha(texto: str, region: str, estacion: str) -> list[dict]:
    """Series meteorológicas (parser previo, todos los parámetros) y de contaminantes."""
    parametros = tuple(sorted(set(re.findall(
        rf"macropath=\./{re.escape(region)}/{re.escape(estacion)}/Met/([A-Z0-9]+)", texto))))
    salida = []
    for serie in smet.parsear_ficha(texto, region, estacion, parametros):
        salida.append({
            "tipo": "meteorologia", "region_sinca": region, "estacion": estacion,
            "codigo": serie["parametro"], "parametro": serie["parametro"],
            "macro_ficha": serie["macro_ficha"],
            "resolucion": serie.get("resolucion_ficha", ""),
            "parametro_ficha": serie.get("nombre_variable_ficha", ""),
            "unidad_ficha": serie.get("unidad_ficha", ""),
            "altura_ficha": serie.get("altura_ficha", ""),
            "tecnica_ficha": serie.get("instrumento_ficha", ""),
            "primer_registro_ficha": "", "ultimo_registro_ficha": "",
            "desde_ficha": serie.get("desde_ficha", ""),
            "hasta_ficha": serie.get("hasta_ficha", ""),
        })
    return salida + parsear_series_contaminantes(texto, region, estacion)


def clave_de_ficha(texto: str, claves_regionales: list) -> tuple[tuple[str, str], str]:
    """(región, estación) que enlaza la ficha y una nota si no es inequívoca."""
    claves = sorted({(r, e) for r, e, _ in _RE_MACROPATH.findall(texto)})
    regionales = [tuple(c) for c in claves_regionales]
    if len(claves) == 1:
        nota = "" if not regionales or claves[0] in regionales else (
            f"la ficha enlaza {claves[0]} y la página regional {regionales}")
        return claves[0], nota
    if not claves:
        return (regionales[0] if len(regionales) == 1 else ("", "")), (
            "la ficha no enlaza series" if regionales else "")
    comunes = [c for c in claves if c in regionales]
    if len(comunes) == 1:
        return comunes[0], f"la ficha enlaza varias estaciones {claves}; se usa la regional"
    return ("", ""), f"la ficha enlaza varias estaciones {claves}; sin clave inequívoca"


def _gzip_determinista(datos: bytes) -> bytes:
    return gzip.compress(datos, compresslevel=9, mtime=0)


def _sha256(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _leer_gz(ruta: Path) -> str:
    return gzip.decompress(ruta.read_bytes()).decode("utf-8", errors="replace")


def unir_estacion(regional: dict, ficha: dict, clave: tuple[str, str], mapa: dict,
                  configuradas: set[str]) -> dict:
    """Fila de ``estaciones_fichas.csv``; la calificación sale del mapa SINCA."""
    region_sinca, estacion = clave
    if not region_sinca:
        region_sinca = f"R{regional['pagina_regional']}"
    en_mapa = mapa.get(estacion, {}) if estacion else {}
    if en_mapa.get("calificacion"):
        calificacion, fuente = en_mapa["calificacion"], "listadomapa2k19"
    elif regional["publica_pagina_regional"] == "si":
        calificacion, fuente = "Pública", "pagina_regional"
    else:
        calificacion, fuente = "sin calificación publicada", "pagina_regional"
    lat, lon, fuente_latlon = ficha["lat"], ficha["lon"], "ficha"
    if not (lat and lon) and en_mapa.get("latitud") is not None:
        lat, lon, fuente_latlon = str(en_mapa["latitud"]), str(en_mapa["longitud"]), "listadomapa2k19"
    return {
        "id_sinca": regional["id_sinca"], "region_sinca": region_sinca,
        "estacion": estacion,
        "nombre": ficha["nombre"] or regional["nombre_regional"],
        "region": ficha["region"], "provincia": ficha["provincia"],
        "comuna": ficha["comuna"] or regional["comuna_regional"],
        "lat": lat, "lon": lon, "fuente_latlon": fuente_latlon if lat else "",
        "utm_e": ficha["utm_e"], "utm_n": ficha["utm_n"], "huso": ficha["huso"],
        "propietario": ficha["propietario"], "operador": ficha["operador"],
        "red": regional["red_regional"] or (en_mapa.get("red") or ""),
        "calificacion": calificacion, "fuente_calificacion": fuente,
        "publica_pagina_regional": regional["publica_pagina_regional"],
        "en_linea": regional["en_linea"], "con_meteorologia": regional["con_meteorologia"],
        "empresa_mapa": en_mapa.get("empresa") or "",
        "recepcion_datos": ficha["recepcion_datos"],
        "inicio_operacion": ficha["inicio_operacion"],
        "acreditacion": ficha["acreditacion"],
        "representatividad": ficha["representatividad"],
        "configurada": "si" if estacion and estacion in configuradas else "no",
        "pagina_regional": regional["pagina_regional"],
    }


# --------------------------------------------------------------------------
# Escritura segura y bloqueos
# --------------------------------------------------------------------------
publicar_sin_sobrescribir = smet.publicar_sin_sobrescribir
escribir_csv_atomico = smet.escribir_csv_atomico
escribir_json_atomico = smet.escribir_json_atomico


def comprobar_piso(carpeta: Path, piso_gb: float, bytes_nuevos: int = 0) -> int:
    try:
        return smet.comprobar_piso(carpeta, piso_gb, bytes_nuevos)
    except smet.DetencionSegura as exc:
        raise DetencionSegura(str(exc)) from exc


class Bloqueo:
    """Bloqueo exclusivo no bloqueante. ``solo_lectura`` toma el candado de
    un archivo previo sin abrirlo para escritura (no lo modifica)."""

    def __init__(self, ruta: Path, solo_lectura: bool = False):
        self.ruta, self.solo_lectura, self.archivo = ruta, solo_lectura, None

    def __enter__(self):
        if self.solo_lectura:
            if not self.ruta.exists():
                return self
            self.archivo = self.ruta.open("rb")
        else:
            ensure_dir(self.ruta.parent)
            self.archivo = self.ruta.open("a+")
        try:
            fcntl.flock(self.archivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.archivo.close()
            raise SystemExit(f"Ya hay otro escritor activo ({self.ruta.name})") from exc
        return self

    def __exit__(self, *_):
        if self.archivo is not None:
            fcntl.flock(self.archivo.fileno(), fcntl.LOCK_UN)
            self.archivo.close()
        return False


def _al_recibir_senal(signum, _frame):
    raise DetencionSegura(f"señal {signal.Signals(signum).name}")


def _leer_csv(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    with ruta.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def escribir_sha256sums(ruta: Path, filas: list[tuple[str, str]]) -> None:
    lineas = sorted(f"{h}  {r}" for h, r in filas)
    temporal = ruta.with_name(f".{ruta.name}.{os.getpid()}.part")
    try:
        temporal.write_text("\n".join(lineas) + ("\n" if lineas else ""), encoding="utf-8")
        temporal.replace(ruta)
    finally:
        temporal.unlink(missing_ok=True)


def _marca_utc() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _guardar_fuente(carpeta: Path, relativa: str, url: str, datos: bytes) -> dict:
    comprimido = _gzip_determinista(datos)
    ruta = carpeta / relativa
    publicar_sin_sobrescribir(comprimido, ruta)
    return {"tipo": relativa.split("/")[0], "url": url, "ruta_relativa": relativa,
            "bytes_crudos": len(datos), "sha256_crudo": _sha256(datos),
            "bytes_gz": len(comprimido), "sha256_gz": _sha256(comprimido),
            "consultado_utc": datetime.now(UTC).isoformat()}


# --------------------------------------------------------------------------
# Fase catálogo
# --------------------------------------------------------------------------
def fase_catalogo(args) -> int:
    ampliacion = args.ampliacion
    comprobar_piso(ensure_dir(ampliacion), args.piso_gb)
    configuradas = {str(e["estacion"]) for e in json.loads(CONFIG_ESTACIONES.read_bytes())}
    carpeta = ampliacion / "catalogo" / _marca_utc()
    if carpeta.exists():
        raise SystemExit(f"la instantánea {carpeta.name} ya existe")
    with Bloqueo(ampliacion / ".descarga_sinca_ampliacion.lock"):
        fuentes, regionales = [], []
        for region in REGIONES:
            url = URL_REGION.format(region=region)
            datos = pedir_pagina(url)
            filas = parsear_pagina_regional(datos.decode("utf-8", errors="replace"), region)
            fuentes.append(_guardar_fuente(carpeta, f"regiones/{region}.html.gz", url, datos))
            regionales.extend(filas)
            log.info("región %s: %d estaciones", region, len(filas))
            time.sleep(args.pausa)
        datos_mapa = pedir_pagina(URL_MAPA)
        mapa_lista = json.loads(datos_mapa)
        if not isinstance(mapa_lista, list):
            raise ValueError("listadomapa2k19 no es una lista")
        fuentes.append(_guardar_fuente(carpeta, "mapa/listadomapa2k19.json.gz", URL_MAPA,
                                       datos_mapa))
        mapa = {str(e.get("key")): e for e in mapa_lista}
        ids = sorted({f["id_sinca"] for f in regionales}, key=int)
        if args.limite:
            ids = ids[: args.limite]
        por_id = {f["id_sinca"]: f for f in regionales}
        estaciones, series, errores = [], [], []
        for i, id_sinca in enumerate(ids, 1):
            url = URL_FICHA.format(id=id_sinca)
            relativa = f"fichas/id_{id_sinca}.html.gz"
            try:
                datos = pedir_pagina(url)
                if b'id="tablaGeneral"' not in datos:
                    raise ValueError("la ficha no trae la tabla de información general")
            except (requests.RequestException, ValueError) as exc:
                errores.append({"id_sinca": id_sinca, "url": url, "error": str(exc)[:300]})
                log.error("ficha id %s: %s", id_sinca, exc)
                continue
            finally:
                time.sleep(args.pausa)
            fuente = _guardar_fuente(carpeta, relativa, url, datos)
            fuentes.append(fuente)
            texto = datos.decode("utf-8", errors="replace")
            regional = por_id[id_sinca]
            clave, nota = clave_de_ficha(texto, regional["claves_regionales"])
            if nota:
                errores.append({"id_sinca": id_sinca, "url": url, "error": f"aviso: {nota}"})
                log.warning("ficha id %s: %s", id_sinca, nota)
            estacion = unir_estacion(regional, parsear_ficha_general(texto), clave, mapa,
                                     configuradas)
            propias = series_de_ficha(texto, *clave) if clave[0] else []
            for s in propias:
                s.update(id_sinca=id_sinca, nombre=estacion["nombre"],
                         ficha_sha256=fuente["sha256_crudo"])
            estacion.update(
                series_contaminantes=sum(s["tipo"] == "contaminante" for s in propias),
                series_meteorologicas=sum(s["tipo"] == "meteorologia" for s in propias),
                ficha_url=url, ficha_ruta=relativa, ficha_sha256=fuente["sha256_crudo"])
            estaciones.append(estacion)
            series.extend(propias)
            if i % 25 == 0:
                log.info("… %d/%d fichas", i, len(ids))
        escribir_csv_atomico(carpeta / "estaciones_fichas.csv", CAMPOS_ESTACIONES,
                             sorted(estaciones, key=lambda e: (
                                 e["region_sinca"], not e["estacion"], e["estacion"],
                                 int(e["id_sinca"]))))
        escribir_csv_atomico(carpeta / "series_fichas.csv", CAMPOS_SERIES, series)
        escribir_csv_atomico(carpeta / "fuentes.csv", list(fuentes[0]) if fuentes else ["url"],
                             fuentes)
        escribir_csv_atomico(carpeta / "errores_fichas.csv", ["id_sinca", "url", "error"], errores)
        resumen = {
            "creado_utc": datetime.now(UTC).isoformat(), "script_version": SCRIPT_VERSION,
            "script_sha256": SCRIPT_SHA256,
            "modulo_meteorologia_sha256": MODULO_METEOROLOGIA_SHA256,
            "estaciones_paginas_regionales": len(regionales),
            "fichas_descargadas": len(estaciones),
        "fichas_con_error": sum(not e["error"].startswith("aviso") for e in errores),
        "avisos": sum(e["error"].startswith("aviso") for e in errores),
            "estaciones_configuradas": sum(e["configurada"] == "si" for e in estaciones),
            "estaciones_nuevas": sum(e["configurada"] == "no" for e in estaciones),
            "estaciones_en_mapa": len(mapa), "series_meteorologicas": sum(
                s["tipo"] == "meteorologia" for s in series),
            "series_contaminantes": sum(s["tipo"] == "contaminante" for s in series),
        }
        escribir_json_atomico(carpeta / "catalogo.json", resumen)
        propios = [p for p in carpeta.rglob("*") if p.is_file()
                   and p.name not in ("SHA256SUMS.txt",) and not p.name.startswith(".")]
        escribir_sha256sums(carpeta / "SHA256SUMS.txt",
                            [(_sha256(p.read_bytes()), str(p.relative_to(carpeta)))
                             for p in propios])
    log.info("Catálogo %s: %s", carpeta.name, resumen)
    return 1 if resumen["fichas_con_error"] else 0


# --------------------------------------------------------------------------
# Inventario y plan
# --------------------------------------------------------------------------
def catalogo_vigente(ampliacion: Path, explicito: str | None) -> Path:
    if explicito:
        carpeta = Path(explicito)
        if not carpeta.is_absolute():
            carpeta = ampliacion / "catalogo" / explicito
    else:
        candidatas = sorted(p for p in (ampliacion / "catalogo").glob("*T*Z")
                            if (p / "catalogo.json").exists())
        if not candidatas:
            raise SystemExit("no hay catálogo: corre primero --fase catalogo")
        carpeta = candidatas[-1]
    if not (carpeta / "catalogo.json").exists():
        raise SystemExit(f"catálogo incompleto: {carpeta}")
    return carpeta


def rango_serie(serie: dict, desde: str, hasta: str, desde_piso: str) -> tuple[str, str]:
    """Desde la primera fecha de la ficha si es anterior a ``desde`` (sin bajar
    de ``desde_piso``); hasta ``hasta``."""
    inicio = date.fromisoformat(desde)
    ficha = fecha_de_ficha(serie.get("desde_ficha", ""))
    if ficha and ficha < inicio:
        inicio = max(ficha, date.fromisoformat(desde_piso))
    return inicio.isoformat(), hasta


def _claves_meteorologia_previas(meteo: Path, sufijo: str) -> set[tuple]:
    """Series ya publicadas en manifiestos previos (excluye el del propio sufijo)."""
    claves = set()
    for ruta in sorted(meteo.glob("manifiesto_descarga*.csv")):
        if ruta.name == f"manifiesto_descarga_{sufijo}.csv":
            continue
        for f in _leer_csv(ruta):
            claves.add((f["region"], f["estacion"], f["parametro"], f["macro_ficha"]))
    return claves


def _claves_contaminantes_previas() -> set[tuple]:
    return {(f["region"], f["estacion"], f["contaminante"], f["resolucion"])
            for f in _leer_csv(MANIFIESTO_SINCA)}


def pendientes(catalogo: Path, tipo: str, args) -> tuple[list[dict], list[dict]]:
    """(pendientes, ya_en_disco) para ``meteorologia`` o ``contaminante``."""
    series = [s for s in _leer_csv(catalogo / "series_fichas.csv") if s["tipo"] == tipo]
    if tipo == "meteorologia":
        previas = _claves_meteorologia_previas(args.meteorologia, args.sufijo)
        clave = lambda s: (s["region_sinca"], s["estacion"], s["parametro"], s["macro_ficha"])  # noqa: E731
    else:
        previas = _claves_contaminantes_previas()
        clave = lambda s: (s["region_sinca"], s["estacion"], s["parametro"], s["resolucion"])  # noqa: E731
    estaciones = {e["estacion"]: e for e in _leer_csv(catalogo / "estaciones_fichas.csv")
                  if e["estacion"]}
    pend, en_disco = [], []
    for s in series:
        s = dict(s)
        est = estaciones.get(s["estacion"], {})
        s["grupo"] = "configurada" if est.get("configurada") == "si" else "nueva"
        s["propietario"], s["operador"] = est.get("propietario", ""), est.get("operador", "")
        s["catalogo"] = catalogo.name
        s["desde"], s["hasta"] = rango_serie(s, args.desde, args.hasta, args.desde_piso)
        (en_disco if clave(s) in previas else pend).append(s)
    if getattr(args, "solo_errores", False):
        nombre = (f"no_disponibles_{args.sufijo}.csv" if tipo == "meteorologia"
                  else "no_disponibles.csv")
        carpeta = args.meteorologia if tipo == "meteorologia" else args.ampliacion
        con_error = {(f["region"], f["estacion"],
                      f["parametro"] if tipo == "meteorologia" else f["contaminante"],
                      f["macro_ficha"] if tipo == "meteorologia" else f["resolucion"])
                     for f in _leer_csv(carpeta / nombre) if f["motivo"].startswith("error")}
        pend = [s for s in pend if clave(s) in con_error]
    if args.codigos:
        pedidos = {c.strip() for c in args.codigos.split(",") if c.strip()}
        pend = [s for s in pend if s["codigo"] in pedidos]
    if args.limite:
        pend = pend[: args.limite]
    return pend, en_disco


def estimar(series: list[dict]) -> dict:
    filas = bytes_ = segundos = 0
    for s in series:
        dias = (date.fromisoformat(s["hasta"]) - date.fromisoformat(s["desde"])).days
        horaria = s["resolucion"] == "horario"
        n = dias * 24 + 23 if horaria else dias
        filas += n
        bytes_ += n * BYTES_POR_FILA
        segundos += SEGUNDOS_HORARIA if horaria else SEGUNDOS_DIARIA
    return {"series": len(series), "filas": filas, "gb": round(bytes_ / 1e9, 3),
            "horas_estimadas": round(segundos / 3600, 2)}


def fase_inventario(args) -> int:
    catalogo = catalogo_vigente(args.ampliacion, args.catalogo)
    carpeta = args.ampliacion / "inventario" / _marca_utc()
    plan = {"catalogo": catalogo.name, "creado_utc": datetime.now(UTC).isoformat(),
            "script_sha256": SCRIPT_SHA256, "argumentos": {
                "desde": args.desde, "hasta": args.hasta, "desde_piso": args.desde_piso,
                "sufijo": args.sufijo}}
    campos = CAMPOS_SERIES + ["grupo", "desde", "hasta"]
    for tipo in ("meteorologia", "contaminante"):
        pend, en_disco = pendientes(catalogo, tipo, args)
        escribir_csv_atomico(carpeta / f"pendientes_{tipo}.csv", campos, pend)
        escribir_csv_atomico(carpeta / f"ya_en_disco_{tipo}.csv", campos, en_disco)
        plan[tipo] = {
            "pendientes": estimar(pend),
            "por_grupo": {g: estimar([s for s in pend if s["grupo"] == g])
                          for g in ("configurada", "nueva")},
            "por_codigo": {c: len([s for s in pend if s["codigo"] == c])
                           for c in sorted({s["codigo"] for s in pend})},
            "ya_en_disco": len(en_disco),
        }
    escribir_json_atomico(carpeta / "plan.json", plan)
    log.info("Plan (%s): %s", carpeta.relative_to(args.ampliacion),
             json.dumps({k: plan[k]["pendientes"] for k in ("meteorologia", "contaminante")},
                        ensure_ascii=False))
    return 0


# --------------------------------------------------------------------------
# Análisis de respuestas de contaminantes
# --------------------------------------------------------------------------
_RE_DATO = re.compile(r"^(\d{6});(\d{4});(.*)$")
CONTADOR_ESTADO = {"validada": "filas_validadas", "preliminar": "filas_preliminares",
                   "no_validada": "filas_no_validadas"}


def _numero(campo: str) -> float | None:
    campo = campo.strip().replace(",", ".")
    if not campo:
        return None
    try:
        valor = float(campo)
    except ValueError:
        return None
    return valor if math.isfinite(valor) else None


def analizar_contaminante(texto: str, desde: str, hasta: str, resolucion: str) -> dict:
    """Clasifica la exportación y cuenta filas por estado de validación.

    Columnas del exportador: registros validados, preliminares y no validados
    (misma lectura que ``descargar_sinca._calidades_observadas``). Horario:
    01:00 del primer día a 23:00 del último. Diario: del primer día al día
    anterior a ``hasta`` (el exportador excluye el último día).
    """
    r = {"estado": "", "motivo": "", "filas": 0, "filas_con_observacion": 0,
         "primera_marca": "", "ultima_marca": "", "primera_observacion": "",
         "ultima_observacion": ""}
    estados = ("validada", "preliminar", "no_validada")
    for e in estados:
        r[CONTADOR_ESTADO[e]] = 0
        r[f"primera_{e}"] = r[f"ultima_{e}"] = ""
    if "could not load macro" in texto.lower():
        r.update(estado="macro_inexistente", motivo="la macro no existe en SINCA")
        return r
    lineas = [x for x in texto.splitlines() if x.strip()]
    if not lineas or not lineas[0].upper().startswith("FECHA"):
        r.update(estado="formato_no_serie", motivo="sin encabezado FECHA")
        return r
    for linea in lineas[1:]:
        m = _RE_DATO.match(linea.strip())
        if not m:
            r.update(estado="formato_no_serie", motivo=f"fila inesperada: {linea.strip()[:40]!r}")
            return r
        fecha, hora, resto = m.groups()
        marca = f"{fecha} {hora}"
        r["filas"] += 1
        r["primera_marca"] = r["primera_marca"] or marca
        r["ultima_marca"] = marca
        campos = (resto.split(";") + ["", "", ""])[:3]
        observada = False
        for estado, campo in zip(estados, campos):
            if _numero(campo) is None:
                continue
            observada = True
            r[CONTADOR_ESTADO[estado]] += 1
            r[f"primera_{estado}"] = r[f"primera_{estado}"] or marca
            r[f"ultima_{estado}"] = marca
        if observada:
            r["filas_con_observacion"] += 1
            r["primera_observacion"] = r["primera_observacion"] or marca
            r["ultima_observacion"] = marca
    inicio, fin = date.fromisoformat(desde), date.fromisoformat(hasta)
    if resolucion == "horario":
        esperadas = ((fin - inicio).days + 1) * 24 - 1
        primera, ultima = f"{inicio:%y%m%d} 0100", f"{fin:%y%m%d} 2300"
    else:
        esperadas = (fin - inicio).days
        primera = f"{inicio:%y%m%d} 0000"
        ultima = f"{fin - timedelta(days=1):%y%m%d} 0000"
    if (r["filas"] != esperadas or r["primera_marca"] != primera
            or r["ultima_marca"] != ultima):
        r.update(estado="incompleta", motivo=(
            f"{r['filas']} filas de {esperadas}; {r['primera_marca']}..{r['ultima_marca']}"))
        return r
    if not r["filas_con_observacion"]:
        r.update(estado="sin_observaciones", motivo="plantilla sin mediciones")
        return r
    r["estado"] = "serie"
    return r


def estado_validacion(r: dict) -> str:
    presentes = [e for e, campo in CONTADOR_ESTADO.items() if r[campo]]
    if not presentes:
        return "sin_observaciones"
    return "solo_" + presentes[0] if len(presentes) == 1 else "mixta:" + "+".join(presentes)


# --------------------------------------------------------------------------
# Descarga de una serie (común)
# --------------------------------------------------------------------------
def _obtener(ruta: Path, params: dict, analizar, piso_gb: float, destino: Path):
    """Devuelve (datos, resumen, accion) o (None, resumen, motivo)."""
    if ruta.exists():
        datos = ruta.read_bytes()
        resumen = analizar(datos.decode("utf-8", errors="replace"))
        if resumen["estado"] != "serie":
            return None, resumen, f"archivo existente no válido ({resumen['estado']}); no se toca"
        return datos, resumen, "reutilizado_en_disco"
    comprobar_piso(destino, piso_gb, 16 * 1024**2)
    texto = pedir_exportador(params)
    resumen = analizar(texto)
    if resumen["estado"] != "serie":
        return None, resumen, f"{resumen['estado']}: {resumen['motivo']}"
    datos = texto.encode("utf-8")
    comprobar_piso(destino, piso_gb, len(datos))
    publicar_sin_sobrescribir(datos, ruta)
    if ruta.read_bytes() != datos:
        raise RuntimeError(f"la relectura de {ruta.name} no coincide")
    return datos, resumen, "descargado"


def _contexto_temporal() -> dict:
    politica = POLITICA_TEMPORAL_RUTA.read_bytes()
    sha = _sha256(politica)
    return {"marca_temporal": json.loads(politica)["sinca"]["reloj_fuente"],
            "politica_temporal_sha256": sha,
            "politica_utc": f"config/sinca/politica_temporal.json#sha256={sha}"}


def _bucle(series, procesar, guardar, pausa: float, etiqueta: str) -> tuple[str, dict]:
    conteo = {"descargado": 0, "reutilizado_en_disco": 0, "faltante": 0, "error": 0}
    estado = "en_curso"
    try:
        for i, serie in enumerate(series, 1):
            try:
                tipo, accion = procesar(serie)
            except (DetencionSegura, smet.DetencionSegura, KeyboardInterrupt):
                raise
            except Exception as exc:  # noqa: BLE001
                tipo, accion = "error", f"error: {type(exc).__name__}: {exc}"[:300]
                procesar.registrar_error(serie, accion)
            conteo[accion if tipo == "manifiesto" else tipo] += 1
            guardar()
            if i % 25 == 0:
                log.info("… %s %d/%d series %s", etiqueta, i, len(series), conteo)
            if accion != "reutilizado_en_disco":
                time.sleep(pausa)
        estado = "terminada"
    except (DetencionSegura, smet.DetencionSegura, KeyboardInterrupt) as exc:
        estado = f"detenida: {exc or type(exc).__name__}"
        log.error("Corrida detenida: %s", estado)
    finally:
        guardar()
    return estado, conteo


# --------------------------------------------------------------------------
# Fase meteorología (archivos nuevos en data/sinca_meteorologia)
# --------------------------------------------------------------------------
class ProcesadorMeteorologia:
    def __init__(self, destino: Path, piso_gb: float, contexto: dict,
                 manifiesto: dict, faltantes: dict):
        self.destino, self.piso_gb, self.contexto = destino, piso_gb, contexto
        self.manifiesto, self.faltantes = manifiesto, faltantes

    def _base(self, serie: dict) -> dict:
        macro_ic = smet.macro_exportacion(serie["region_sinca"], serie["estacion"],
                                          serie["parametro"], serie["macro_ficha"])
        params = smet.parametros_pedido(macro_ic, serie["desde"], serie["hasta"])
        return {"region": serie["region_sinca"], "estacion": serie["estacion"],
                "nombre": serie["nombre"], "parametro": serie["parametro"],
                "macro_ficha": serie["macro_ficha"], "macro_exportada": macro_ic,
                "desde": serie["desde"], "hasta": serie["hasta"],
                "url_fuente": smet.url_pedido(params),
                "registrado_utc": datetime.now(UTC).isoformat()}, params

    def clave(self, serie: dict) -> tuple:
        return (serie["region_sinca"], serie["estacion"], serie["parametro"],
                serie["macro_ficha"], serie["desde"], serie["hasta"])

    def registrar_error(self, serie: dict, motivo: str) -> None:
        base, _ = self._base(serie)
        self.faltantes[self.clave(serie)] = {**base, "motivo": motivo}
        log.info("  !! %s %s %s/%s: %s", serie["region_sinca"], serie["estacion"],
                 serie["parametro"], serie["macro_ficha"], motivo)

    def __call__(self, serie: dict) -> tuple[str, str]:
        base, params = self._base(serie)
        nombre = (f"{serie['region_sinca']}_{serie['estacion']}_{serie['parametro']}_"
                  f"{serie['macro_ficha']}_{serie['desde']}_{serie['hasta']}.csv")
        ruta = self.destino / serie["parametro"] / nombre
        analizar = lambda t: smet.analizar_respuesta(t, serie["desde"], serie["hasta"])  # noqa: E731
        datos, r, accion = _obtener(ruta, params, analizar, self.piso_gb, self.destino)
        clave = self.clave(serie)
        if datos is None:
            self.faltantes[clave] = {**base, "motivo": accion}
            log.info("  -- %s %s %s/%s: %s", serie["region_sinca"], serie["estacion"],
                     serie["parametro"], serie["macro_ficha"], accion)
            return "faltante", "faltante"
        variable, unidad = METEOROLOGIA.get(serie["parametro"],
                                            (serie["parametro"].lower(), ""))
        self.manifiesto[clave] = {
            **base, "variable": variable, "altura_ficha": serie.get("altura_ficha", ""),
            "unidad_ficha": serie.get("unidad_ficha", "") or unidad,
            "instrumento_ficha": serie.get("tecnica_ficha", ""),
            "desde_ficha": serie.get("desde_ficha", ""),
            "hasta_ficha": serie.get("hasta_ficha", ""),
            "ruta_relativa": str(ruta.relative_to(self.destino)), "bytes": len(datos),
            "sha256": _sha256(datos), "filas": r["filas"],
            "filas_con_observacion": r["filas_con_observacion"],
            "filas_no_numericas": r["filas_no_numericas"],
            "primera_observacion": r["primera_observacion"],
            "ultima_observacion": r["ultima_observacion"],
            "minimo": r["minimo"], "maximo": r["maximo"], "accion": accion,
            "ficha_sha256": serie.get("ficha_sha256", ""), **self.contexto,
        }
        self.faltantes.pop(clave, None)
        log.info("  ok %s %s %s/%s %d KB (%s; %s obs.)", serie["region_sinca"],
                 serie["estacion"], serie["parametro"], serie["macro_ficha"],
                 len(datos) // 1024, accion, r["filas_con_observacion"])
        return "manifiesto", accion


def fase_meteorologia(args) -> int:
    destino = args.meteorologia
    catalogo = catalogo_vigente(args.ampliacion, args.catalogo)
    series, en_disco = pendientes(catalogo, "meteorologia", args)
    log.info("meteorología: %d series pendientes; %d ya en disco (catálogo %s)",
             len(series), len(en_disco), catalogo.name)
    if args.dry_run:
        log.info("[dry-run] %s", json.dumps(estimar(series)))
        return 0
    if not re.fullmatch(r"\d{8}[a-z]?", args.sufijo):
        raise SystemExit("--sufijo debe ser AAAAMMDD con una letra opcional")
    ruta_m = destino / f"manifiesto_descarga_{args.sufijo}.csv"
    ruta_f = destino / f"no_disponibles_{args.sufijo}.csv"
    ruta_s = destino / f"SHA256SUMS_{args.sufijo}.txt"
    estaciones_sha = _sha256((catalogo / "estaciones_fichas.csv").read_bytes())
    contexto = {k: v for k, v in _contexto_temporal().items() if k != "politica_utc"}
    contexto |= {"config_estaciones_sha256": estaciones_sha,
                 "script_version": SCRIPT_VERSION, "script_sha256": SCRIPT_SHA256}
    comprobar_piso(destino, args.piso_gb)
    signal.signal(signal.SIGTERM, _al_recibir_senal)
    marca = _marca_utc()
    carpeta_corrida = destino / "corridas" / f"{marca}_ampliacion_{args.sufijo}"
    corrida = {"inicio_utc": datetime.now(UTC).isoformat(), "fin_utc": None,
               "estado": "en_curso", "fase": "meteorologia", "pid": os.getpid(),
               "catalogo": catalogo.name, "sufijo": args.sufijo,
               "argumentos": {k: str(v) for k, v in vars(args).items()
                              if k not in ("ampliacion", "meteorologia")},
               "modulo_meteorologia_sha256": MODULO_METEOROLOGIA_SHA256, **contexto,
               "series_pendientes": len(series), "series_ya_en_disco": len(en_disco)}
    with Bloqueo(destino / ".descarga_sinca_meteorologia.lock", solo_lectura=True), \
            Bloqueo(destino / ".descarga_sinca_ampliacion.lock"):
        escribir_csv_atomico(carpeta_corrida / "pendientes.csv",
                             CAMPOS_SERIES + ["grupo", "desde", "hasta"], series)
        escribir_json_atomico(carpeta_corrida / "corrida.json", corrida)
        clave = lambda f: (f["region"], f["estacion"], f["parametro"], f["macro_ficha"],  # noqa: E731
                           f["desde"], f["hasta"])
        manifiesto = {clave(f): f for f in _leer_csv(ruta_m)}
        faltantes = {clave(f): f for f in _leer_csv(ruta_f)}
        procesar = ProcesadorMeteorologia(destino, args.piso_gb, contexto, manifiesto,
                                          faltantes)

        def guardar():
            escribir_csv_atomico(ruta_m, smet.CAMPOS_MANIFIESTO,
                                 [manifiesto[k] for k in sorted(manifiesto)])
            escribir_csv_atomico(ruta_f, smet.CAMPOS_FALTANTES,
                                 [faltantes[k] for k in sorted(faltantes)])
            escribir_sha256sums(ruta_s, [(f["sha256"], f["ruta_relativa"])
                                         for f in manifiesto.values()])

        estado, conteo = _bucle(series, procesar, guardar, args.pausa, "meteorología")
        corrida.update(estado=estado, fin_utc=datetime.now(UTC).isoformat(), conteo=conteo,
                       series_en_manifiesto=len(manifiesto),
                       series_no_disponibles=len(faltantes),
                       bytes_en_manifiesto=sum(int(f["bytes"]) for f in manifiesto.values()))
        escribir_json_atomico(carpeta_corrida / "corrida.json", corrida)
    log.info("Listo meteorología (%s): %s", estado, conteo)
    return 2 if estado != "terminada" else (1 if conteo["error"] else 0)


# --------------------------------------------------------------------------
# Fase contaminantes (carpeta de ampliación, nunca data/sinca)
# --------------------------------------------------------------------------
class ProcesadorContaminantes:
    def __init__(self, destino: Path, piso_gb: float, contexto: dict, manifiesto: dict,
                 faltantes: dict, validacion: dict):
        self.destino, self.piso_gb, self.contexto = destino, piso_gb, contexto
        self.manifiesto, self.faltantes, self.validacion = manifiesto, faltantes, validacion

    def clave(self, serie: dict) -> tuple:
        return (serie["region_sinca"], serie["estacion"], serie["parametro"],
                serie["resolucion"], serie["desde"], serie["hasta"])

    def _base(self, serie: dict) -> tuple[dict, dict]:
        codigo = serie["codigo"]
        macro_ic = f"./{serie['region_sinca']}/{serie['estacion']}/Cal/{codigo}//{serie['macro_ficha']}.ic"
        params = smet.parametros_pedido(macro_ic, serie["desde"], serie["hasta"])
        return {"region": serie["region_sinca"], "estacion": serie["estacion"],
                "nombre": serie["nombre"], "contaminante": serie["parametro"],
                "resolucion": serie["resolucion"], "desde": serie["desde"],
                "hasta": serie["hasta"], "codigo_sinca": codigo, "macro_exportada": macro_ic,
                "url_fuente": smet.url_pedido(params),
                "registrado_utc": datetime.now(UTC).isoformat()}, params

    def registrar_error(self, serie: dict, motivo: str) -> None:
        base, _ = self._base(serie)
        self.faltantes[self.clave(serie)] = {**base, "motivo": motivo}
        log.info("  !! %s %s %s/%s: %s", serie["region_sinca"], serie["estacion"],
                 serie["parametro"], serie["resolucion"], motivo)

    def __call__(self, serie: dict) -> tuple[str, str]:
        base, params = self._base(serie)
        res = serie["resolucion"]
        nombre = (f"{serie['region_sinca']}_{serie['estacion']}_{res}_"
                  f"{serie['desde']}_{serie['hasta']}.csv")
        ruta = self.destino / serie["parametro"] / res / nombre
        analizar = lambda t: analizar_contaminante(t, serie["desde"], serie["hasta"], res)  # noqa: E731
        datos, r, accion = _obtener(ruta, params, analizar, self.piso_gb, self.destino)
        clave = self.clave(serie)
        if datos is None:
            self.faltantes[clave] = {**base, "motivo": accion}
            log.info("  -- %s %s %s/%s: %s", serie["region_sinca"], serie["estacion"],
                     serie["parametro"], res, accion)
            return "faltante", "faltante"
        self.manifiesto[clave] = {
            **base, "ruta": str(ruta), "bytes": len(datos), "sha256": _sha256(datos),
            "filas": r["filas"], "filas_con_observacion": r["filas_con_observacion"],
            "primera_marca": r["primera_marca"], "ultima_marca": r["ultima_marca"],
            "primera_observacion": r["primera_observacion"],
            "ultima_observacion": r["ultima_observacion"], "accion": accion,
            **self.contexto,
            **{k: serie.get(k, "") for k in (
                "macro_ficha", "parametro_ficha", "unidad_ficha", "tecnica_ficha",
                "primer_registro_ficha", "ultimo_registro_ficha", "desde_ficha",
                "hasta_ficha", "id_sinca", "propietario", "operador", "grupo",
                "ficha_sha256", "catalogo")},
        }
        self.validacion[clave] = {
            "ruta_relativa": str(ruta.relative_to(self.destino)),
            "region": serie["region_sinca"], "estacion": serie["estacion"],
            "nombre": serie["nombre"], "contaminante": serie["parametro"],
            "resolucion": res, "codigo_sinca": serie["codigo"],
            "macro_exportada": base["macro_exportada"],
            "parametro_ficha": serie.get("parametro_ficha", ""),
            "unidad_ficha": serie.get("unidad_ficha", ""),
            "tecnica_ficha": serie.get("tecnica_ficha", ""),
            "primer_registro_ficha": serie.get("primer_registro_ficha", ""),
            "ultimo_registro_ficha": serie.get("ultimo_registro_ficha", ""),
            **{k: r[k] for k in CAMPOS_VALIDACION if k in r},
            "estado_validacion": estado_validacion(r),
        }
        self.faltantes.pop(clave, None)
        log.info("  ok %s %s %s/%s %d KB (%s; %s obs.; %s)", serie["region_sinca"],
                 serie["estacion"], serie["parametro"], res, len(datos) // 1024, accion,
                 r["filas_con_observacion"], estado_validacion(r))
        return "manifiesto", accion


def es_serie_contrato(fila: dict) -> bool:
    return fila["resolucion"] == "horario" and fila["contaminante"] in CONTAMINANTES_CONTRATO


def fase_contaminantes(args) -> int:
    catalogo = catalogo_vigente(args.ampliacion, args.catalogo)
    series, en_disco = pendientes(catalogo, "contaminante", args)
    log.info("contaminantes: %d series pendientes; %d ya en data/sinca (catálogo %s)",
             len(series), len(en_disco), catalogo.name)
    return _descargar_contaminantes(args, args.ampliacion, catalogo, series, en_disco,
                                    "contaminantes", dividir=True)


# Código SINCA de los seis contaminantes del contrato (descargar_sinca.PARAM_CODES).
CODIGO_CONTRATO = {"pm25": "PM25", "pm10": "PM10", "so2": "0001", "no2": "0003",
                   "o3": "0008", "co": "0004"}
CARPETA_ACTUALIZACION = "actualizacion_configuradas"


def pendientes_actualizacion(catalogo: Path, args) -> tuple[list[dict], list[dict]]:
    """Series horarias del contrato que ya están en data/sinca, desde su último
    día en disco (el ``hasta`` mayor de sus archivos) hasta ``--hasta``.

    Repite ese último día, como las actualizaciones incrementales de data/sinca
    (``..._2026-09-12_2026-09-13.csv`` sigue a ``..._2026-09-10_2026-09-12.csv``).
    """
    ultimo: dict[tuple, str] = {}
    for f in _leer_csv(MANIFIESTO_SINCA):
        if f["resolucion"] != "horario" or f["contaminante"] not in CONTAMINANTES_CONTRATO:
            continue
        k = (f["region"], f["estacion"], f["contaminante"])
        ultimo[k] = max(ultimo.get(k, ""), f["hasta"])
    fichas = {(s["region_sinca"], s["estacion"], s["parametro"]): s
              for s in _leer_csv(catalogo / "series_fichas.csv")
              if s["tipo"] == "contaminante" and s["resolucion"] == "horario"}
    estaciones = {e["estacion"]: e for e in _leer_csv(catalogo / "estaciones_fichas.csv")
                  if e["estacion"]}
    pend, al_dia = [], []
    for (region, estacion, contaminante), hasta_previo in sorted(ultimo.items()):
        codigo = CODIGO_CONTRATO[contaminante]
        est = estaciones.get(estacion, {})
        s = dict(fichas.get((region, estacion, contaminante)) or {
            "tipo": "contaminante", "region_sinca": region, "estacion": estacion,
            "id_sinca": est.get("id_sinca", ""), "nombre": est.get("nombre", ""),
            "codigo": codigo, "parametro": contaminante,
            "macro_ficha": f"{codigo}.horario.horario", "resolucion": "horario"})
        s.update(grupo="configurada", propietario=est.get("propietario", ""),
                 operador=est.get("operador", ""), catalogo=catalogo.name,
                 desde=hasta_previo, hasta=args.hasta)
        (al_dia if hasta_previo >= args.hasta else pend).append(s)
    if args.solo_errores:
        con_error = {(f["region"], f["estacion"], f["contaminante"])
                     for f in _leer_csv(args.ampliacion / CARPETA_ACTUALIZACION
                                        / "no_disponibles.csv")
                     if f["motivo"].startswith("error")}
        pend = [s for s in pend if (s["region_sinca"], s["estacion"], s["parametro"])
                in con_error]
    if args.codigos:
        pedidos = {c.strip() for c in args.codigos.split(",") if c.strip()}
        pend = [s for s in pend if s["codigo"] in pedidos]
    if args.limite:
        pend = pend[: args.limite]
    return pend, al_dia


def _copiar_maestro_sellado(destino: Path) -> list[dict]:
    """Copia byte a byte el maestro georreferenciado de data/sinca (sólo lectura)
    para que ``preparar_sinca_modelado.py --fuente <destino>`` lo encuentre."""
    copias = []
    for nombre in ("estaciones_georreferenciadas.geojson", "estaciones_georreferenciadas.csv"):
        origen = SINCA / nombre
        if not origen.exists():
            log.warning("no existe %s en data/sinca; no se copia", nombre)
            continue
        datos = origen.read_bytes()
        copia = destino / nombre
        if not copia.exists():
            publicar_sin_sobrescribir(datos, copia)
        elif copia.read_bytes() != datos:
            raise DetencionSegura(f"{nombre} de la actualización no es copia del sellado")
        copias.append({"archivo": nombre, "sha256": _sha256(datos), "bytes": len(datos)})
    return copias


def fase_actualizacion(args) -> int:
    catalogo = catalogo_vigente(args.ampliacion, args.catalogo)
    destino = args.ampliacion / CARPETA_ACTUALIZACION
    series, al_dia = pendientes_actualizacion(catalogo, args)
    log.info("actualización: %d series de data/sinca por actualizar hasta %s; %d ya al día",
             len(series), args.hasta, len(al_dia))
    copias = []
    if not args.dry_run:
        with Bloqueo(args.ampliacion / ".descarga_sinca_ampliacion.lock"):
            copias = _copiar_maestro_sellado(ensure_dir(destino))
    return _descargar_contaminantes(args, destino, catalogo, series, al_dia,
                                    "actualizacion", dividir=False,
                                    extra_corrida={"maestro_copiado": copias})


def _descargar_contaminantes(args, destino: Path, catalogo: Path, series: list[dict],
                             en_disco: list[dict], fase: str, dividir: bool,
                             extra_corrida: dict | None = None) -> int:
    if args.dry_run:
        log.info("[dry-run] %s", json.dumps(estimar(series)))
        return 0
    ensure_dir(destino)
    ruta_m = destino / "manifiesto_descarga.csv"
    ruta_o = destino / "manifiesto_descarga_otras_series.csv"
    ruta_f = destino / "no_disponibles.csv"
    ruta_e = destino / "errores_descarga.csv"
    ruta_v = destino / "estado_validacion_series.csv"
    ruta_s = destino / "SHA256SUMS.txt"
    estaciones_sha = _sha256((catalogo / "estaciones_fichas.csv").read_bytes())
    contexto = _contexto_temporal() | {"config_estaciones_sha256": estaciones_sha,
                                       "script_version": SCRIPT_VERSION,
                                       "script_sha256": SCRIPT_SHA256}
    comprobar_piso(destino, args.piso_gb)
    signal.signal(signal.SIGTERM, _al_recibir_senal)
    carpeta_corrida = destino / "corridas" / _marca_utc()
    corrida = {"inicio_utc": datetime.now(UTC).isoformat(), "fin_utc": None,
               "estado": "en_curso", "fase": fase, "pid": os.getpid(),
               "catalogo": catalogo.name,
               "argumentos": {k: str(v) for k, v in vars(args).items()
                              if k not in ("ampliacion", "meteorologia")},
               "modulo_meteorologia_sha256": MODULO_METEOROLOGIA_SHA256, **contexto,
               "series_pendientes": len(series), "series_omitidas": len(en_disco),
               **(extra_corrida or {})}
    with Bloqueo(args.ampliacion / ".descarga_sinca_ampliacion.lock"):
        escribir_csv_atomico(carpeta_corrida / "pendientes.csv",
                             CAMPOS_SERIES + ["grupo", "desde", "hasta"], series)
        escribir_json_atomico(carpeta_corrida / "corrida.json", corrida)
        clave = lambda f: (f["region"], f["estacion"], f["contaminante"], f["resolucion"],  # noqa: E731
                           f["desde"], f["hasta"])
        manifiesto = {clave(f): f for f in _leer_csv(ruta_m) + _leer_csv(ruta_o)}
        faltantes = {clave(f): f for f in _leer_csv(ruta_f)}
        copia_estaciones = destino / "estaciones_fichas.csv"
        datos_estaciones = (catalogo / "estaciones_fichas.csv").read_bytes()
        if not copia_estaciones.exists():
            publicar_sin_sobrescribir(datos_estaciones, copia_estaciones)
        elif copia_estaciones.read_bytes() != datos_estaciones:
            log.warning("estaciones_fichas.csv de %s es de otro catálogo; no se toca",
                        destino.name)
        validacion = {}
        for f in _leer_csv(ruta_v):
            partes = Path(f["ruta_relativa"]).stem.split("_")
            validacion[(f["region"], f["estacion"], f["contaminante"], f["resolucion"],
                        partes[-2], partes[-1])] = f
        procesar = ProcesadorContaminantes(destino, args.piso_gb, contexto, manifiesto,
                                           faltantes, validacion)

        def guardar():
            ordenadas = [manifiesto[k] for k in sorted(manifiesto)]
            if dividir:
                escribir_csv_atomico(ruta_m, CAMPOS_MANIFIESTO_CONTAMINANTES,
                                     [f for f in ordenadas if es_serie_contrato(f)])
                escribir_csv_atomico(ruta_o, CAMPOS_MANIFIESTO_CONTAMINANTES,
                                     [f for f in ordenadas if not es_serie_contrato(f)])
            else:
                escribir_csv_atomico(ruta_m, CAMPOS_MANIFIESTO_CONTAMINANTES, ordenadas)
            escribir_csv_atomico(ruta_f, CAMPOS_FALTANTES_CONTAMINANTES,
                                 [faltantes[k] for k in sorted(faltantes)])
            escribir_csv_atomico(ruta_e, CAMPOS_FALTANTES_CONTAMINANTES,
                                 [faltantes[k] for k in sorted(faltantes)
                                  if faltantes[k]["motivo"].startswith("error")])
            escribir_csv_atomico(ruta_v, CAMPOS_VALIDACION,
                                 [validacion[k] for k in sorted(validacion)])
            escribir_sha256sums(ruta_s, [(f["sha256"], str(Path(f["ruta"]).relative_to(destino)))
                                         for f in manifiesto.values()])

        estado, conteo = _bucle(series, procesar, guardar, args.pausa, fase)
        corrida.update(estado=estado, fin_utc=datetime.now(UTC).isoformat(), conteo=conteo,
                       series_en_manifiesto=len(manifiesto),
                       series_no_disponibles=len(faltantes),
                       bytes_en_manifiesto=sum(int(f["bytes"]) for f in manifiesto.values()))
        escribir_json_atomico(carpeta_corrida / "corrida.json", corrida)
    log.info("Listo %s (%s): %s", fase, estado, conteo)
    return 2 if estado != "terminada" else (1 if conteo["error"] else 0)


# --------------------------------------------------------------------------
def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fase", required=True,
                    choices=["catalogo", "inventario", "meteorologia", "contaminantes",
                             "actualizacion"])
    ap.add_argument("--ampliacion", default=str(AMPLIACION_POR_OMISION))
    ap.add_argument("--meteorologia", default=str(METEOROLOGIA_POR_OMISION))
    ap.add_argument("--catalogo", default=None,
                    help="instantánea del catálogo (marca o ruta); por omisión, la última")
    ap.add_argument("--sufijo", default=date.today().strftime("%Y%m%d") + "b",
                    help="sufijo de los registros meteorológicos nuevos (AAAAMMDD[letra])")
    ap.add_argument("--desde", default="2000-01-01", help="YYYY-MM-DD")
    ap.add_argument("--desde-piso", default="1980-01-01",
                    help="fecha mínima aunque la ficha declare una anterior (las "
                         "fichas usan 1970 como marcador)")
    ap.add_argument("--solo-errores", action="store_true",
                    help="reintenta sólo las series cuyo no disponible fue un error")
    ap.add_argument("--hasta", default=date.today().isoformat())
    ap.add_argument("--codigos", default="", help="filtra por código SINCA (prueba)")
    ap.add_argument("--piso-gb", type=float, default=1.0)
    ap.add_argument("--pausa", type=float, default=1.0)
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    try:
        inicio, fin = date.fromisoformat(args.desde), date.fromisoformat(args.hasta)
        piso = date.fromisoformat(args.desde_piso)
    except ValueError:
        ap.error("--desde, --desde-piso y --hasta deben ser YYYY-MM-DD")
    if not piso <= inicio <= fin <= date.today():
        ap.error("se requiere desde-piso <= desde <= hasta <= hoy")
    for nombre in ("piso_gb", "pausa"):
        valor = getattr(args, nombre)
        if not math.isfinite(valor) or valor < 0:
            ap.error(f"--{nombre.replace('_', '-')} debe ser finito y no negativo")
    args.ampliacion = Path(args.ampliacion).expanduser().resolve()
    args.meteorologia = Path(args.meteorologia).expanduser().resolve()
    sinca = SINCA.resolve()
    for destino in (args.ampliacion, args.meteorologia):
        if destino == sinca or sinca in destino.parents:
            ap.error("ningún destino puede estar dentro de data/sinca")
    if args.ampliacion == args.meteorologia:
        ap.error("la ampliación y la meteorología deben ser carpetas distintas")
    return {"catalogo": fase_catalogo, "inventario": fase_inventario,
            "meteorologia": fase_meteorologia, "contaminantes": fase_contaminantes,
            "actualizacion": fase_actualizacion}[args.fase](args)


def main(argv=None) -> int:
    return _main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
