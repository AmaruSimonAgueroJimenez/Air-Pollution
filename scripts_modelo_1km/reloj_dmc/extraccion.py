"""Extracción: DMC desde manifiestos y artefactos, ERA5-Land por píxel, catálogo y píxel (§3.1-§3.4).

Fase 2 y 3 de §5.2. Es el único módulo que abre archivos de datos (además de controles_era5 en C3).
- DMC: lee sólo manifiestos ``estaciones/<código>/<AAAA-MM>.manifest.json`` y el artefacto que nombran,
  con ``leer_artefacto`` del adaptador fijado. Nunca abre ``metadata/`` ni versiones viejas de json.gz.
- Control propio de §3.2 (no es el QC del producto), fila medida H(L), marcas RR/TX/TN/observador,
  huella de fila y paso nativo p_v.
- ERA5-Land: lector propio (no el de _comun_modelo), eje y unidades por rango (A1), sha256 de cada mes,
  series de los píxeles enlazados en un arreglo mapeado en disco (eje UTC horario global desde
  2000-01-01T00Z; las diferencias de borde de mes salen solas).
- Píxel: celda propia válida o centro válido más cercano a ≤ 15 km (empate: menor pixel_id); costera
  si el píxel no es su celda. Nunca por correlación. La celda propia la da ``tablas.celda_que_contiene``,
  con la misma regla de bordes que el territorio.
Escrituras atómicas y reanudables por unidad (estación DMC; mes ERA5), registradas por el llamador.
Depende de: entorno, fijados, tipos, umbrales, constantes, numerico, tablas.

Archivos que escribe, bajo ``destino`` (la carpeta de la corrida; nunca bajo /Volumes ni en los repositorios):
- ``extractos/dmc/<código>.parquet`` (ESQUEMA_EXTRACTO_HORA) y ``extractos/dmc/meses/<código>.parquet``
  (ESQUEMA_MES de la estación): son la unidad reanudable «dmc/<código>»;
- ``extractos/dmc/meses.parquet``, ``artefactos_evaluados.json`` y ``resumen.json``, que se rehacen al final
  (``id_artefacto`` es el índice en ``artefactos_evaluados``);
- ``extractos/era5/serie.f4`` e ``indice.json``. Mientras se llena, la serie se llama ``serie.f4.part`` y
  ``progreso.json`` lleva los meses ya volcados. Un corte no deja un ``serie.f4`` a medias.

Lecturas de implementación de este módulo (para el addendum de C1, junto con las del diseño):
1. Admisión (§3.1): las cuatro condiciones se miran en el manifiesto de nivel superior. Motivo de exclusión,
   el primero que aplica: estado (``candidato`` si queda una clave ``verification_candidate``, ``failed``,
   y si no ``pending``; un manifiesto ilegible cuenta como ``failed``), versión (``sin_codigo`` si no trae
   ``script_sha256`` o su versión no tiene código recuperado; ``version_no_admitida`` en otro caso),
   ``artifact_name`` y ``row_count``. Un manifiesto verificado que aún lleve un candidato entra con su
   artefacto de nivel superior; el candidato nunca se lee.
2. ``campos_faltantes`` lista los campos de §3.1 y los de R-55 (``row_count``, ``verification_status``,
   ``artifact_name``) que faltan o vienen con otro tipo. Nunca excluyen el mes.
3. Control propio (§3.2, R-14, R-15): centinela y rango por valor; mediana del mes sobre los valores que
   pasan centinela y rango; racha = ≥ 2 valores idénticos en etiquetas consecutivas separadas exactamente
   por el paso nativo p de esos mismos valores, que cubren n·p ≥ 12 h (Ts) o 24 h (QFE). Las rachas se
   buscan dentro del mes, porque el control es mensual. Cada valor lleva el primer código que aplica
   (centinela, rango, mediana, racha). Con p = 6, dos Ts iguales seguidas ya cubren 12 h.
4. p_v de ``meses`` (R-51) se calcula sobre los valores definitivos, después del control. Se guarda en
   Int16: dentro de un mes el paso no pasa de 743 h, así que siempre cabe (con Int8, un p > 127 h quedaba <NA>).
5. Viento: es válido sólo si dirección y rapidez son numéricas y caen en el dominio; si no, ambas quedan NaN.
6. H(L) (§3.2, R-16): sólo Ts y QFE tienen centinela; un valor numérico fuera de rango cuenta para H(L).
7. Coordenadas inconsistentes (§3.1): un texto distinto del catálogo marca la estación salvo que ambos se
   interpreten y difieran a lo más 0,0005° o 0,5 m (con una holgura de 1e-9 por la representación binaria).
   Se miran sólo los artefactos evaluados, que son los únicos que se leen.
8. Huella agregada (§7.4): líneas «sha256␣␣ruta\\n» (formato de sha256sum, con salto final en cada línea),
   ordenadas por la ruta escrita por alias, sobre todos los manifiestos listados, entren o no.
9. Píxel (§3.3): sólo se enlaza una estación con coordenadas válidas (interpretables y en rango). Sin píxel,
   ``costera`` es False, porque no hay píxel enlazado. ``distancia_km`` es al centro del píxel enlazado.
10. ERA5-Land (§3.4): el eje es correcto si todas las horas son HH:00 enteras, van de 1 h en 1 h desde el
    inicio del mes, quedan dentro del mes y llegan al fin del mes (o a 2026-09-15T23Z). Un mes sin archivo
    queda con sha256 vacío y eje anómalo (A1). Las medianas de unidades son sobre todos los píxeles y horas
    del mes. t2m − 273,15 y sp/100 se calculan en float64 y se guardan en float32.
11. Eje global de la serie: 2000-01-01T00Z a 2026-09-15T23Z (234.120 h); fuera del eje o en una hora no
    entera, ``valores`` da NaN. sp̄ de z_pix (R-20) es la media de las horas con dato del píxel en ese eje.
12. Listado (§3.1): se ignoran los archivos ocultos («._*» de AppleDouble, temporales «.*»); cualquier otro
    nombre que termine en «.manifest.json» y no sea ``<6 dígitos>/<AAAA-MM>.manifest.json``, o un enlace
    simbólico, detiene la corrida.
"""
from __future__ import annotations

import gzip
import io
import json
import math
import os
import re
import stat
import warnings
from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Collection, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from reloj_dmc import constantes, entorno, fijados, numerico, tablas
from reloj_dmc.tipos import (CODIGOS_DESCARTE, ESQUEMA_ESTACIONES, ESQUEMA_EXTRACTO_HORA, ESQUEMA_MES,
                             VARIABLES_ERA5, Conjunto, InfoEstacion, tabla_vacia, validar_esquema)
from reloj_dmc.umbrales import Umbrales

CAMPOS_MANIFIESTO = ("available_hours", "source_empty_slots", "expected_hour_slots", "requested_start",
                     "requested_end", "duplicate_display_rows_removed", "source_sha256", "script_sha256")
CAMPOS_R55 = ("row_count", "verification_status", "artifact_name")      # R-55: se usan aunque §3.1 no los nombre
CAMPOS_FILA_MEDIDA = ("Ts", "Td", "relative_humidity", "wind_speed_instant", "wind_direction_instant", "QFE", "QFF")
COLUMNAS_CRUDAS_SIN_DIA_NI_HORA = ("wind_direction_instant", "wind_speed_instant", "Ts", "Td", "TMin", "TMax",
                                   "relative_humidity", "WW", "VV", "visibility_reigning", "visibility_minimum",
                                   "QFE", "QFF", "QNH", "N", "Nh", "CL", "CM", "CH", "Hs1", "RR06")  # 21 (§3.2)
NOMBRE_CATALOGO_DMC = "catalogo_nacional.json.gz"

if len(COLUMNAS_CRUDAS_SIN_DIA_NI_HORA) != constantes.valor("HUELLA_TEXTOS"):
    raise RuntimeError("La huella de fila debe usar los 21 textos crudos de §3.2")

# Estructura del árbol DMC (la que escribe el descargador).
CARPETA_ESTACIONES = "estaciones"
SUFIJO_MANIFIESTO = ".manifest.json"
_PATRON_ESTACION = re.compile(r"\d{6}")
_PATRON_MANIFIESTO = re.compile(r"(\d{4})-(\d{2})\.manifest\.json")
ESTADO_VERIFICADO = "verified_operational"
MAX_MANIFIESTO_BYTES = 32 * 1024 * 1024   # no-umbral: límite de lectura del descargador (MAX_RESPONSE)
MOTIVOS_EXCLUSION = ("pending", "failed", "candidato", "version_no_admitida", "sin_codigo", "artifact_name",
                     "row_count")

# Carpetas de salida bajo ``destino``.
CARPETA_DMC = Path("extractos") / "dmc"
CARPETA_ERA5 = Path("extractos") / "era5"
NOMBRE_MESES = "meses.parquet"
NOMBRE_ARTEFACTOS = "artefactos_evaluados.json"
NOMBRE_RESUMEN = "resumen.json"
NOMBRE_SERIE = "serie.f4"
NOMBRE_INDICE = "indice.json"
NOMBRE_PROGRESO_ERA5 = "progreso.json"

# Catálogo DMC: columnas de la tabla que devuelve leer_catalogo_dmc. Los estratos se toman si existen (R-50);
# los nombres de columna del portal no se conocen sin abrir el catálogo, así que se prueban estos.
COLUMNAS_CATALOGO_DMC = ("codigo", "nombre", "lat_txt", "lon_txt", "alt_txt", "tipo", "propietario", "omm", "oaci")
CLAVES_COORDENADAS = ("Latitud", "Longitud", "Altitud (Mts)")
ESTRATOS_CATALOGO = {
    "tipo": ("Tipo", "Tipo Estación", "Tipo de Estación"),
    "propietario": ("Propietario", "Institución", "Dueño"),
    "omm": ("Código OMM", "OMM", "Indicativo OMM", "Código WMO", "WMO"),
    "oaci": ("Código OACI", "OACI", "Indicativo OACI", "ICAO"),
}
COLUMNAS_CATALOGO_PIXELES = ("pixel_id", "latitude", "longitude", "cell_west", "cell_south", "cell_east",
                             "cell_north", "cod_comuna", "territorio")

# Códigos de descarte del extracto (tipos.CODIGOS_DESCARTE).
_CODIGO = {nombre: codigo for codigo, nombre in CODIGOS_DESCARTE.items()}
VALIDO, AUSENTE, CENTINELA, RANGO, MEDIANA, RACHA = (
    _CODIGO[n] for n in ("valido", "ausente", "centinela", "rango", "mediana", "racha"))

# Holgura numérica de la comparación de coordenadas (lectura 7): no es un umbral.
_HOLGURA_COORDENADAS = 1e-9
_N_EJEMPLOS = 5   # no-umbral: cuántos ejemplos muestra un mensaje de error
_EJES = ("lat", "lon", "alt")
_UNA_HORA = np.timedelta64(1, "h")
_NS_POR_HORA = int(_UNA_HORA.astype("timedelta64[ns]").astype(np.int64))

# ERA5-Land (§3.4).
T0_ERA5 = np.datetime64("2000-01-01T00", "h")
ULTIMA_HORA_ERA5 = np.datetime64(constantes.valor("ERA5_ULTIMA_HORA_UTC"), "h")
N_HORAS_ERA5 = int((ULTIMA_HORA_ERA5 - T0_ERA5) // _UNA_HORA) + 1
MESES_ERA5 = tuple(pd.period_range(str(T0_ERA5.astype("datetime64[M]")), str(ULTIMA_HORA_ERA5.astype("datetime64[M]")),
                                   freq="M").strftime("%Y%m"))
CARPETA_MENSUAL_ERA5 = "mensual"
PATRON_ARCHIVO_ERA5 = "era5land_{yyyymm}_chile_pixeles.nc"
_ARCHIVO_ERA5 = re.compile(r"era5land_(\d{6})_chile_pixeles\.nc")
IDS_MESES_VALIDEZ = ("PIXEL_MES_VALIDEZ_1", "PIXEL_MES_VALIDEZ_2", "PIXEL_MES_VALIDEZ_3")
KELVIN_A_CELSIUS = 273.15   # definición de unidad: t2m (K) → °C
PA_POR_HPA = 100.0          # no-umbral: definición de unidad (1 hPa = 100 Pa)
_FACTOR_TIEMPO = {"seconds": 1, "minutes": 60, "hours": 3600}
_UNIDADES_TIEMPO = re.compile(r"(?P<unidad>seconds|minutes|hours) since (?P<fecha>\d{4}-\d{2}-\d{2})"
                              r"(?:[ T](?P<hora>\d{2}:\d{2}(?::\d{2})?))?\s*(?:UTC|Z|\+00:00|\+0000)?")
_CALENDARIOS = (None, "standard", "gregorian", "proleptic_gregorian")


class ErrorExtraccion(RuntimeError):
    """Estructura inesperada de los datos o del árbol (no es un descarte del control propio): se detiene."""


# --- Utilidades ---------------------------------------------------------------
def _sin_na(x: Any) -> Any:
    """None en vez de pd.NA, NaN o None."""
    if x is None or x is pd.NA:
        return None
    if isinstance(x, float) and math.isnan(x):
        return None
    return x


def _texto(x: Any) -> str | None:
    x = _sin_na(x)
    return x if isinstance(x, str) else None


def _entero(x: Any) -> int | None:
    """Entero no negativo de un manifiesto (no bool); None si falta o tiene otro tipo."""
    if isinstance(x, bool) or not isinstance(x, int) or x < 0:
        return None
    return int(x)


def _es_sha(x: Any) -> bool:
    return isinstance(x, str) and re.fullmatch(r"[0-9a-f]{64}", x) is not None


def _parquet_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_parquet(buf, index=False, engine="pyarrow")
    return buf.getvalue()


def _marco(filas: Sequence[Mapping[str, Any]], esquema: Mapping[str, str]) -> pd.DataFrame:
    """DataFrame con las columnas, el orden y los tipos exactos del esquema."""
    columnas = {}
    for col, tipo in esquema.items():
        valores = [f[col] for f in filas]
        if tipo == "object":
            serie = pd.Series(valores, dtype=object)
        else:
            serie = pd.Series(valores, dtype=tipo)
        columnas[col] = serie
    df = pd.DataFrame(columnas)
    validar_esquema(df, esquema, nombre="marco")
    return df


def _leer_acotado(ruta: Path, maximo: int) -> bytes:
    """Bytes de un archivo regular sin seguir enlaces, a lo más ``maximo``; si no, ErrorExtraccion."""
    fd = os.open(ruta, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise ErrorExtraccion(f"no es un archivo regular: {Path(ruta).name}")
        datos = f.read(maximo + 1)
    if len(datos) > maximo:
        raise ErrorExtraccion(f"archivo demasiado grande: {Path(ruta).name}")
    return datos


def _sha_modulo(modulo: Any) -> str | None:
    archivo = getattr(modulo, "__file__", None)
    return entorno.sha256_archivo(Path(archivo)) if archivo else None


def _prohibido_escribir(ruta: Path) -> None:
    entorno.prohibido_volumes(ruta)
    entorno.prohibido_repositorios(ruta)


def _borrar(ruta: Path) -> None:
    _prohibido_escribir(ruta)
    try:
        os.unlink(ruta)
    except FileNotFoundError:
        pass


# --- Catálogo y conjuntos ---------------------------------------------------
def leer_catalogo_dmc(ruta: Path) -> tuple[pd.DataFrame, str]:
    """(tabla de estaciones con textos crudos de Latitud/Longitud/Altitud y estratos, sha256 del archivo).

    Columnas: COLUMNAS_CATALOGO_DMC, todas de texto («string»), ordenadas por código. Los textos se dejan tal
    cual (§3.3 los interpreta después). Un código repetido o que no tenga 6 dígitos detiene la lectura.
    """
    datos = Path(ruta).read_bytes()
    sha = entorno.sha256_bytes(datos)
    try:
        payload = json.loads(gzip.decompress(datos))
    except (OSError, EOFError, ValueError) as e:
        raise ErrorExtraccion(f"catálogo DMC ilegible: {e}") from e
    estaciones = payload.get("stations") if isinstance(payload, dict) else None
    if not isinstance(estaciones, list):
        raise ErrorExtraccion("el catálogo DMC no trae la lista «stations»")
    filas, vistos = [], set()
    for est in estaciones:
        if not isinstance(est, dict):
            raise ErrorExtraccion("estación del catálogo que no es un objeto")
        codigo = str(est.get("code", ""))
        if not _PATRON_ESTACION.fullmatch(codigo) or codigo in vistos:
            raise ErrorExtraccion(f"código de estación inválido o repetido en el catálogo: {codigo!r}")
        vistos.add(codigo)
        md = est.get("source_metadata") if isinstance(est.get("source_metadata"), dict) else {}
        fila = {"codigo": codigo, "nombre": _texto(md.get("Nombre")),
                "lat_txt": _texto(md.get(CLAVES_COORDENADAS[0])), "lon_txt": _texto(md.get(CLAVES_COORDENADAS[1])),
                "alt_txt": _texto(md.get(CLAVES_COORDENADAS[2]))}
        for campo, candidatos in ESTRATOS_CATALOGO.items():
            fila[campo] = next((_texto(md[c]) for c in candidatos if c in md), None)
        filas.append(fila)
    filas.sort(key=lambda f: f["codigo"])
    return _marco(filas, {c: "string" for c in COLUMNAS_CATALOGO_DMC}), sha


def _codigos_de_lista(ruta: Path) -> list[str]:
    tabla = pd.read_csv(ruta, dtype=str, keep_default_na=False)
    if "codigo" not in tabla.columns:
        raise ErrorExtraccion(f"la lista {Path(ruta).name} no tiene columna «codigo»")
    codigos = [c.strip() for c in tabla["codigo"]]
    malos = [c for c in codigos if not _PATRON_ESTACION.fullmatch(c)]
    if malos:
        raise ErrorExtraccion(f"códigos inválidos en {Path(ruta).name}: {malos[:_N_EJEMPLOS]}")
    return codigos


def leer_conjuntos(lista_v: Path, lista_v2: Path) -> dict[str, str]:
    """código → «V» | «V2»; el resto es N. V prevalece sobre V2 si un código estuviera en ambas (R-54).

    Las listas son los CSV del inventario de C0 (``lista_V.csv`` y ``lista_V2.csv``), con columna «codigo».
    Los valores son ``Conjunto.V`` o ``Conjunto.V2`` (StrEnum: se comparan iguales a «V» y «V2»).
    """
    salida: dict[str, str] = {c: Conjunto.V2 for c in _codigos_de_lista(lista_v2)}
    salida.update({c: Conjunto.V for c in _codigos_de_lista(lista_v)})
    return dict(sorted(salida.items()))


def leer_catalogo_pixeles(ruta: Path, sha256: str) -> pd.DataFrame:
    """catalogo_pixeles.parquet (pixel_id, latitude, longitude, cell_west…cell_north, cod_comuna, territorio).

    Exige la sha256 dada (``fijados.SHA_CATALOGO_PIXELES`` en la corrida real) y ``pixel_id`` único.
    Devuelve todas las columnas del archivo, ordenadas por ``pixel_id``.
    """
    if not _es_sha(sha256):
        raise ValueError("leer_catalogo_pixeles exige un sha256 de 64 hexadecimales")
    datos = Path(ruta).read_bytes()
    if entorno.sha256_bytes(datos) != sha256:
        corta = sha256[:8]   # no-umbral: abreviatura de una huella en un mensaje
        raise ErrorExtraccion(f"la huella de {Path(ruta).name} no es la fijada ({corta}…)")
    tabla = pd.read_parquet(io.BytesIO(datos))
    faltan = [c for c in COLUMNAS_CATALOGO_PIXELES if c not in tabla.columns]
    if faltan:
        raise ErrorExtraccion(f"al catálogo de píxeles le faltan {faltan}")
    if tabla["pixel_id"].duplicated().any():
        raise ErrorExtraccion("pixel_id repetido en el catálogo de píxeles")
    return tabla.sort_values("pixel_id", kind="mergesort").reset_index(drop=True)


def _coordenadas_de(fila: Any) -> tuple[float | None, float | None, float | None]:
    if fila is None:
        return None, None, None
    return (tablas.interpretar_coordenada(_texto(fila.lat_txt), "lat"),
            tablas.interpretar_coordenada(_texto(fila.lon_txt), "lon"),
            tablas.interpretar_coordenada(_texto(fila.alt_txt), "alt"))


def enlazar_pixeles(catalogo_dmc: pd.DataFrame, catalogo_pixeles: pd.DataFrame, validos: set[int],
                    umbrales: Umbrales) -> dict[str, "EleccionPixel"]:
    """Píxel de cada estación con coordenadas interpretables (antes de leer ERA5 entero y la DMC).

    Devuelve una entrada por estación del catálogo. Las que no tienen coordenadas válidas (interpretables y
    dentro de −90 ≤ lat ≤ −17, −110 ≤ lon ≤ −55) quedan sin píxel.
    """
    salida: dict[str, EleccionPixel] = {}
    for fila in catalogo_dmc.itertuples(index=False):
        lat, lon, _ = _coordenadas_de(fila)
        if tablas.coordenadas_en_rango(lat, lon):
            salida[fila.codigo] = elegir_pixel(lat, lon, catalogo_pixeles, validos, umbrales)
        else:
            salida[fila.codigo] = EleccionPixel(None, None, False)
    return salida


def info_estaciones(catalogo_dmc: pd.DataFrame, catalogo_pixeles: pd.DataFrame,
                    enlaces: Mapping[str, "EleccionPixel"], medias_sp_hpa: Mapping[int, float],
                    conjuntos: Mapping[str, str], macrozona_region: Mapping[int, str],
                    umbrales: Umbrales, *, codigos_extra: Iterable[str] = ()) -> dict[str, InfoEstacion]:
    """Territorio, P, píxel, costera, z_pix (con sp̄ de todo el período; R-20) y Δz de cada estación.

    ``coordenadas_inconsistentes`` queda en False aquí; ``marcar_coordenadas_inconsistentes`` la pone después
    de extraer_dmc, con los textos de los artefactos evaluados. ``codigos_extra``: estaciones con manifiestos
    que no están en el catálogo vigente; quedan sin coordenadas (territorio incierto).
    """
    filas = {f.codigo: f for f in catalogo_dmc.itertuples(index=False)}
    salida: dict[str, InfoEstacion] = {}
    for codigo in sorted(set(filas) | {str(c) for c in codigos_extra}):
        fila = filas.get(codigo)
        lat, lon, alt = _coordenadas_de(fila)
        territorio, region, macro, zs, P = tablas.territorio_y_P(lat, lon, catalogo_pixeles, macrozona_region)
        eleccion = enlaces.get(codigo) or EleccionPixel(None, None, False)
        z_pix = None
        if eleccion.pixel_id is not None:
            media = _sin_na(medias_sp_hpa.get(eleccion.pixel_id))
            if media is not None and math.isfinite(float(media)):
                z_pix = numerico.z_pixel(float(media))
        dz = alt - z_pix if alt is not None and z_pix is not None else None
        salida[codigo] = InfoEstacion(
            codigo=codigo, nombre=_texto(fila.nombre) if fila is not None else None, lat=lat, lon=lon, alt_m=alt,
            coordenadas_validas=tablas.coordenadas_en_rango(lat, lon), coordenadas_inconsistentes=False,
            territorio=territorio, region=region, macrozona=macro, zs=tuple(zs), P=tuple(P),
            pixel_id=eleccion.pixel_id, distancia_km=eleccion.distancia_km, costera=eleccion.costera,
            z_pix=z_pix, dz=dz, conjunto=Conjunto(conjuntos.get(codigo, Conjunto.N)),
            tipo=_texto(fila.tipo) if fila is not None else None,
            propietario=_texto(fila.propietario) if fila is not None else None,
            omm=_texto(fila.omm) if fila is not None else None,
            oaci=_texto(fila.oaci) if fila is not None else None)
    return salida


def marcar_coordenadas_inconsistentes(infos: Mapping[str, InfoEstacion], catalogo_dmc: pd.DataFrame,
                                      meses: pd.DataFrame, umbrales: Umbrales) -> dict[str, InfoEstacion]:
    """Pone la marca de §3.1 con los textos de coordenadas de los artefactos evaluados (``meses``)."""
    catalogo = {f.codigo: (_texto(f.lat_txt), _texto(f.lon_txt), _texto(f.alt_txt))
                for f in catalogo_dmc.itertuples(index=False)}
    evaluados: dict[str, list[tuple]] = {}
    for f in meses[meses["entra"]].itertuples(index=False):
        evaluados.setdefault(f.codigo, []).append((_texto(f.lat_txt), _texto(f.lon_txt), _texto(f.alt_txt)))
    salida = {}
    for codigo, info in infos.items():
        textos = evaluados.get(codigo, [])
        marca = bool(textos) and coordenadas_inconsistentes(textos, catalogo.get(codigo, (None, None, None)),
                                                            umbrales)
        salida[codigo] = replace(info, coordenadas_inconsistentes=marca)
    return salida


def tabla_estaciones(infos: Mapping[str, InfoEstacion]) -> pd.DataFrame:
    """InfoEstacion → ESQUEMA_ESTACIONES (``pixeles_dmc.parquet`` de §7.4, ampliado), ordenada por código."""
    filas = []
    for codigo in sorted(infos):
        i = infos[codigo]
        filas.append({
            "codigo": i.codigo, "nombre": i.nombre, "lat": i.lat, "lon": i.lon, "alt_m": i.alt_m,
            "coordenadas_validas": i.coordenadas_validas, "coordenadas_inconsistentes": i.coordenadas_inconsistentes,
            "territorio": str(i.territorio), "region": i.region, "macrozona": i.macrozona, "zs": list(i.zs),
            "P": [h.id for h in i.P], "pixel_id": i.pixel_id, "distancia_km": i.distancia_km, "costera": i.costera,
            "z_pix": i.z_pix, "dz": i.dz, "conjunto": str(i.conjunto), "tipo": i.tipo, "propietario": i.propietario,
            "omm": i.omm, "oaci": i.oaci})
    if not filas:
        return tabla_vacia(ESQUEMA_ESTACIONES)
    return _marco(filas, ESQUEMA_ESTACIONES)


# --- Manifiestos y artefactos DMC -------------------------------------------
def listar_manifiestos(raiz_dmc: Path) -> list[Path]:
    """``estaciones/*/*.manifest.json`` ordenados por ruta; sin seguir enlaces.

    Ignora los archivos ocultos (AppleDouble «._*», temporales «.*»). Un enlace simbólico en ``estaciones/``
    o donde iría un manifiesto, o un nombre «*.manifest.json» fuera del patrón, lanza ErrorExtraccion.
    """
    base = Path(raiz_dmc) / CARPETA_ESTACIONES
    if not base.is_dir():
        raise FileNotFoundError(f"no existe la carpeta {CARPETA_ESTACIONES}/ de la DMC")
    salida: list[Path] = []
    with os.scandir(base) as it:
        estaciones = sorted(it, key=lambda e: e.name)
    for est in estaciones:
        if est.name.startswith("."):
            continue
        if est.is_symlink():
            raise ErrorExtraccion(f"enlace simbólico en {CARPETA_ESTACIONES}/: {est.name}")
        if not est.is_dir(follow_symlinks=False):
            continue
        with os.scandir(est.path) as it:
            hijos = sorted(it, key=lambda e: e.name)
        for h in hijos:
            if h.name.startswith(".") or not h.name.endswith(SUFIJO_MANIFIESTO):
                continue
            nombre = f"{est.name}/{h.name}"
            if h.is_symlink() or not h.is_file(follow_symlinks=False):
                raise ErrorExtraccion(f"el manifiesto no es un archivo regular: {nombre}")
            m = _PATRON_MANIFIESTO.fullmatch(h.name)
            if not _PATRON_ESTACION.fullmatch(est.name) or m is None or not 1 <= int(m.group(2)) <= 12:
                raise ErrorExtraccion(f"manifiesto con nombre fuera del patrón: {nombre}")
            salida.append(base / est.name / h.name)
    return sorted(salida, key=lambda p: p.as_posix())


def alias_dmc(ruta: Path, raiz_dmc: Path) -> str:
    """«DMC/estaciones/<código>/<archivo>» (el alias de entorno.alias con la raíz DMC)."""
    return "DMC/" + Path(os.path.normpath(ruta)).relative_to(Path(os.path.normpath(raiz_dmc))).as_posix()


def conjunto_admitido(versiones: Collection[str] | Mapping[str, Mapping]) -> frozenset[str]:
    """Versiones admitidas como conjunto de sha256.

    Acepta un conjunto de sha256 o la salida de ``fijados.versiones_admitidas`` (se toman las que tienen
    ``admitida`` verdadero). Es el conjunto vigente de COORDINACION_C1.md (§3.1, Anexo C).
    """
    if isinstance(versiones, Mapping):
        salida = {v for v, fila in versiones.items() if isinstance(fila, Mapping) and fila.get("admitida") is True}
    else:
        salida = set(versiones)
    malos = [v for v in salida if not _es_sha(v)]
    if malos:
        raise ValueError(f"versión admitida que no es un sha256: {malos[:_N_EJEMPLOS]}")
    return frozenset(salida)


def _versiones_sin_codigo(versiones: Collection[str] | Mapping[str, Mapping],
                          admitidas: frozenset[str]) -> frozenset[str]:
    salida = set(fijados.VERSIONES_SIN_CODIGO_C0)
    if isinstance(versiones, Mapping):
        salida |= {v for v, fila in versiones.items()
                   if isinstance(fila, Mapping) and fila.get("motivo") == "sin_codigo"}
    return frozenset(salida - admitidas)


def _nombre_artefacto_valido(nombre: Any) -> bool:
    """La misma regla que ``leer_artefacto``: nombre local de un gzip, sin carpetas."""
    return isinstance(nombre, str) and bool(nombre) and Path(nombre).name == nombre and nombre.endswith(".json.gz")


def admitir_mes(manifiesto: Mapping, versiones_admitidas: set[str]) -> tuple[bool, str | None]:
    """Las cuatro condiciones de §3.1: verified_operational, artifact_name válido, row_count ≥ 1 y
    script_sha256 admitido. Devuelve (entra, motivo de exclusión).

    ``versiones_admitidas``: conjunto de sha256 o la salida de ``fijados.versiones_admitidas``. Orden de los
    motivos en la lectura 1 del encabezado.
    """
    if not isinstance(manifiesto, Mapping):
        return False, "failed"
    estado = manifiesto.get("verification_status")
    if estado != ESTADO_VERIFICADO:
        if "verification_candidate" in manifiesto:
            return False, "candidato"
        return False, "failed" if estado == "failed" else "pending"
    admitidas = conjunto_admitido(versiones_admitidas)
    version = manifiesto.get("script_sha256")
    if version not in admitidas:
        if not _es_sha(version) or version in _versiones_sin_codigo(versiones_admitidas, admitidas):
            return False, "sin_codigo"
        return False, "version_no_admitida"
    if not _nombre_artefacto_valido(manifiesto.get("artifact_name")):
        return False, "artifact_name"
    filas = manifiesto.get("row_count")
    if isinstance(filas, bool) or not isinstance(filas, int) or filas < 1:
        return False, "row_count"
    return True, None


def _huella_de_pares(pares: Iterable[tuple[str, str]]) -> str:
    """sha256 del texto «sha256␣␣ruta\\n» por manifiesto, ordenado por ruta (lectura 8)."""
    pares = sorted(pares)
    rutas = [r for r, _ in pares]
    if len(set(rutas)) != len(rutas):
        raise ValueError("ruta repetida en la huella agregada de manifiestos")
    texto = "".join(f"{sha}  {ruta}\n" for ruta, sha in pares)
    return entorno.sha256_bytes(texto.encode("utf-8"))


def huella_agregada_manifiestos(rutas: Sequence[Path], alias: Callable[[Path], str]) -> str:
    """sha256 del texto «sha256␣␣ruta», una línea por manifiesto, ordenado por ruta (§7.4)."""
    return _huella_de_pares((alias(Path(r)), entorno.sha256_archivo(Path(r))) for r in rutas)


def _huella_de_textos(textos: Sequence[str]) -> str:
    return entorno.sha256_bytes(json.dumps(list(textos), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def huella_fila(raw_cells: Mapping[str, Mapping]) -> str:
    """sha256 de ``json.dumps([raw_cells[k]["text"] for k in COLUMNAS_CRUDAS_SIN_DIA_NI_HORA],
    ensure_ascii=False, separators=(",", ":"))`` (serialización fijada aquí; R-13)."""
    return _huella_de_textos([raw_cells[k]["text"] for k in COLUMNAS_CRUDAS_SIN_DIA_NI_HORA])


def _valor_numerico(campo: Any) -> float:
    """``fields[v].value`` si ``parse_status == "numeric"`` y es finito; si no, NaN (§3.2)."""
    if isinstance(campo, Mapping) and campo.get("parse_status") == "numeric":
        v = campo.get("value")
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
            return float(v)
    return float("nan")


def _un_digito(texto: str) -> bool:
    """R-45: el texto, sin espacios, es un solo dígito 0-9."""
    return re.fullmatch(r"[0-9]", "".join(texto.split())) is not None


def _etiquetas(textos: Sequence[str]) -> np.ndarray:
    """``timestamp_source`` → datetime64[ns] ingenuo; exige etiquetas horarias (HH:00:00)."""
    try:
        segundos = np.array(textos, dtype="datetime64[s]")
    except (ValueError, TypeError) as e:
        raise ErrorExtraccion(f"timestamp_source ilegible: {e}") from e
    if len(segundos) and (np.isnat(segundos).any() or (segundos.astype(np.int64) % 3600 != 0).any()):
        raise ErrorExtraccion("timestamp_source que no es una hora entera")
    return segundos.astype("datetime64[ns]")


@dataclass(frozen=True)
class _Control:
    """Control propio de una variable (§3.2): columnas del extracto e ids del Anexo B."""
    columna: str
    motivo: str
    campo: str
    centinela: str
    minimo: str
    maximo: str
    desvio: str
    racha: str


_CONTROLES = (
    _Control("ts", "motivo_ts", "Ts", "TS_CENTINELA", "TS_MIN", "TS_MAX", "TS_DESVIO_MEDIANA", "TS_RACHA_H"),
    _Control("qfe", "motivo_qfe", "QFE", "QFE_CENTINELA", "QFE_MIN", "QFE_MAX", "QFE_DESVIO_MEDIANA", "QFE_RACHA_H"),
)


def _centinela_y_rango(v: np.ndarray, m: np.ndarray, c: _Control, umbrales: Umbrales) -> None:
    """En el lugar: centinela exacto y rango sobre los valores aún válidos; los descartados quedan NaN."""
    sel = m == VALIDO
    m[sel & (v == umbrales.f(c.centinela))] = CENTINELA
    sel = m == VALIDO
    m[sel & ((v < umbrales.f(c.minimo)) | (v > umbrales.f(c.maximo)))] = RANGO
    v[m != VALIDO] = np.nan


def filas_a_extracto(payload: Mapping, id_artefacto: int, umbrales: Umbrales) -> pd.DataFrame:
    """Filas de un artefacto → ESQUEMA_EXTRACTO_HORA sin el control por mediana ni rachas (eso es mensual).

    Ya aplica, por valor: ausente, centinela y rango de Ts y QFE, y el dominio del viento. H(L) usa los
    valores numéricos sin centinela (lectura 6). Ordenado por L; una etiqueta repetida detiene la lectura.
    """
    filas = payload.get("rows") if isinstance(payload, Mapping) else None
    if not isinstance(filas, list):
        raise ErrorExtraccion("el artefacto no trae una lista «rows»")
    n = len(filas)
    valores = {campo: np.full(n, np.nan) for campo in CAMPOS_FILA_MEDIDA}
    rr, tx, tn, obs = np.zeros(n, dtype=bool), np.zeros(n, dtype=bool), np.zeros(n, dtype=bool), np.zeros(n, dtype=bool)
    huellas, textos_l = [], []
    i_tmax, i_tmin = COLUMNAS_CRUDAS_SIN_DIA_NI_HORA.index("TMax"), COLUMNAS_CRUDAS_SIN_DIA_NI_HORA.index("TMin")
    i_nubes = [COLUMNAS_CRUDAS_SIN_DIA_NI_HORA.index(c) for c in ("CL", "CM", "CH")]
    for i, fila in enumerate(filas):
        try:
            textos_l.append(fila["timestamp_source"])
            campos = fila["fields"]
            crudas = fila["raw_cells"]
            textos = [crudas[k]["text"] for k in COLUMNAS_CRUDAS_SIN_DIA_NI_HORA]
        except (KeyError, TypeError) as e:
            raise ErrorExtraccion(f"fila del artefacto sin la forma del descargador: {e!r}") from e
        if not isinstance(campos, Mapping) or not all(isinstance(t, str) for t in textos):
            raise ErrorExtraccion("fila del artefacto con campos o textos crudos inválidos")
        for campo in CAMPOS_FILA_MEDIDA:
            valores[campo][i] = _valor_numerico(campos.get(campo))
        rr06 = campos.get("RR06")
        crudo_rr = rr06.get("raw") if isinstance(rr06, Mapping) else None
        rr[i] = isinstance(crudo_rr, str) and crudo_rr.strip() != ""
        tx[i] = textos[i_tmax].strip() != ""
        tn[i] = textos[i_tmin].strip() != ""
        obs[i] = any(_un_digito(textos[j]) for j in i_nubes)
        huellas.append(_huella_de_textos(textos))
    L = _etiquetas(textos_l)

    centinelas = {c.campo: umbrales.f(c.centinela) for c in _CONTROLES}
    medida = np.zeros(n, dtype=bool)
    for campo in CAMPOS_FILA_MEDIDA:
        v = valores[campo]
        presente = np.isfinite(v)
        if campo in centinelas:
            presente &= v != centinelas[campo]
        medida |= presente

    columnas: dict[str, Any] = {}
    for c in _CONTROLES:
        v = valores[c.campo].copy()
        m = np.where(np.isfinite(v), VALIDO, AUSENTE).astype(np.int8)
        _centinela_y_rango(v, m, c, umbrales)
        columnas[c.columna], columnas[c.motivo] = v, m

    dd, ff = valores["wind_direction_instant"], valores["wind_speed_instant"]
    with np.errstate(invalid="ignore"):
        viento = (np.isfinite(dd) & np.isfinite(ff) & (dd >= umbrales.f("VIENTO_DIR_MIN"))
                  & (dd <= umbrales.f("VIENTO_DIR_MAX")) & (ff >= umbrales.f("VIENTO_RAPIDEZ_MIN")))
    fechas = pd.DatetimeIndex(L)
    df = pd.DataFrame({
        "L": L,
        "anio": fechas.year.to_numpy().astype(np.int16),
        "mes": fechas.month.to_numpy().astype(np.int8),
        "id_artefacto": np.full(n, id_artefacto, dtype=np.int32),
        "medida": medida,
        "ts": columnas["ts"], "motivo_ts": columnas["motivo_ts"],
        "qfe": columnas["qfe"], "motivo_qfe": columnas["motivo_qfe"],
        "td": valores["Td"], "hr": valores["relative_humidity"],
        "ff_kt": np.where(viento, ff, np.nan), "dd_grados": np.where(viento, dd, np.nan),
        "viento_valido": viento,
        "qff_numerica": np.isfinite(valores["QFF"]),
        "rr": rr, "tx": tx, "tn": tn, "observador": obs,
        "huella": pd.array(huellas, dtype="string"),
    })
    df = df.sort_values("L", kind="mergesort").reset_index(drop=True)
    if df["L"].duplicated().any():
        raise ErrorExtraccion("etiqueta repetida en un artefacto")
    validar_esquema(df, ESQUEMA_EXTRACTO_HORA, nombre="extracto de un artefacto")
    return df


def _rachas(t: np.ndarray, v: np.ndarray, base: np.ndarray, p: int, horas_min: float) -> np.ndarray:
    """Máscara de los valores de ``base`` que forman una racha idéntica que cubre n·p ≥ horas_min (n ≥ 2)."""
    salida = np.zeros(len(t), dtype=bool)
    idx = np.flatnonzero(base)
    if len(idx) < 2:
        return salida
    orden = idx[np.argsort(t[idx], kind="mergesort")]
    tt, vv = t[orden], v[orden]
    enlace = (np.diff(tt) == np.timedelta64(p, "h")) & (vv[1:] == vv[:-1])
    if not enlace.any():
        return salida
    bordes = np.diff(np.concatenate(([0], enlace.astype(np.int8), [0])))
    for a, b in zip(np.flatnonzero(bordes == 1), np.flatnonzero(bordes == -1)):
        n = b - a + 1                      # enlaces a … b−1 unen los valores a … b
        if n * p >= horas_min:
            salida[orden[a:b + 1]] = True
    return salida


def _controlar_mes(v: np.ndarray, m: np.ndarray, t: np.ndarray, c: _Control, umbrales: Umbrales) -> None:
    """En el lugar, sobre un mes: centinela, rango, mediana (R-14) y rachas (R-15); descartados → NaN."""
    _centinela_y_rango(v, m, c, umbrales)
    base = m == VALIDO
    if base.any():
        mediana = float(np.median(v[base]))
        with np.errstate(invalid="ignore"):
            lejos = base & (np.abs(v - mediana) > umbrales.f(c.desvio))
        p = paso_nativo(t[base])
        en_racha = _rachas(t, v, base, p, umbrales.f(c.racha)) if p is not None else np.zeros(len(v), dtype=bool)
        m[lejos] = MEDIANA
        m[en_racha & (m == VALIDO)] = RACHA
    v[m != VALIDO] = np.nan


def control_propio(extracto_mes: pd.DataFrame, umbrales: Umbrales) -> pd.DataFrame:
    """Aplica §3.2 en el mes: centinela, rango, distancia a la mediana del mes y rachas idénticas.

    La mediana se toma sobre los valores que pasan centinela y rango; una racha son valores idénticos en
    etiquetas consecutivas al paso nativo, descartada si cubre ≥ 12 h (Ts) o ≥ 24 h (QFE) (R-14, R-15).
    Escribe NaN y el código de CODIGOS_DESCARTE; nunca aborta. Si el extracto trae varios meses, cada uno
    se controla por separado. Se aplica una sola vez: si ya hay descartes por mediana o racha, ValueError
    (aplicarlo de nuevo recalcularía la mediana sin los ya descartados).
    """
    validar_esquema(extracto_mes, ESQUEMA_EXTRACTO_HORA, nombre="extracto del mes")
    df = extracto_mes.copy()
    if df.empty:
        return df
    t = df["L"].to_numpy(dtype="datetime64[ns]")
    grupos = df.groupby(["anio", "mes"], sort=False).indices
    for c in _CONTROLES:
        v = df[c.columna].to_numpy(dtype=np.float64, copy=True)
        m = df[c.motivo].to_numpy(dtype=np.int8, copy=True)
        if np.isin(m, (MEDIANA, RACHA)).any():
            raise ValueError("el control propio ya se aplicó a este extracto")
        for pos in grupos.values():
            vv, mm = v[pos], m[pos]
            _controlar_mes(vv, mm, t[pos], c, umbrales)
            v[pos], m[pos] = vv, mm
        df[c.columna] = v
        df[c.motivo] = m
    validar_esquema(df, ESQUEMA_EXTRACTO_HORA, nombre="extracto controlado")
    return df


def paso_nativo(etiquetas: np.ndarray) -> int | None:
    """Diferencia más frecuente (h) entre etiquetas consecutivas con valor; empate → la menor.

    Las etiquetas se ordenan y se toman sin repetir; None si hay menos de dos. Deben ser horas enteras.
    Una sola regla en el paquete: delega en ``numerico.paso_nativo``, que también usa lineas_fisicas.
    """
    return numerico.paso_nativo(etiquetas)


def _paso_para_meses(p: int | None) -> int | None:
    """p_v en ESQUEMA_MES (Int16): <NA> si no hay paso o no cabe (lectura 4)."""
    return p if p is not None and p <= np.iinfo(np.int16).max else None


def coordenadas_inconsistentes(textos_artefactos: Iterable[tuple[str, str, str]], catalogo: tuple[str, str, str],
                               umbrales: Umbrales) -> bool:
    """§3.1: textos distintos del catálogo y, ya interpretados, a más de 0,0005° o 0,5 m (lectura 7)."""
    tolerancias = (umbrales.f("COORD_TOL_GRADOS"), umbrales.f("COORD_TOL_GRADOS"), umbrales.f("COORD_TOL_M"))
    catalogo = tuple(_texto(x) for x in catalogo)
    del_catalogo = [tablas.interpretar_coordenada(t, eje) for t, eje in zip(catalogo, _EJES)]
    for trio in textos_artefactos:
        for texto, texto_cat, valor_cat, eje, tol in zip(trio, catalogo, del_catalogo, _EJES, tolerancias):
            texto = _texto(texto)
            if texto == texto_cat:
                continue
            valor = tablas.interpretar_coordenada(texto, eje)
            if valor is None or valor_cat is None or abs(valor - valor_cat) > tol + _HOLGURA_COORDENADAS:
                return True
    return False


@dataclass
class ResumenExtraccion:
    estaciones: int                          # estaciones con algún mes evaluado
    meses_evaluados: int
    meses_excluidos: Mapping[str, int]       # motivo → conteo
    filas: int
    huella_manifiestos: str


def _registro_manifiesto(ruta: Path, raiz: Path, versiones: Collection[str] | Mapping[str, Mapping]) -> dict:
    """Pasada 1: sha256 del manifiesto, admisión y campos de ESQUEMA_MES (una sola lectura del archivo)."""
    datos = _leer_acotado(ruta, MAX_MANIFIESTO_BYTES)
    try:
        man = json.loads(datos)
    except ValueError:
        man = None
    if not isinstance(man, dict):
        man = None
    m = _PATRON_MANIFIESTO.fullmatch(ruta.name)
    entra, motivo = admitir_mes(man, versiones) if man is not None else (False, "failed")
    man = man or {}
    horas = man.get("available_hours")
    horas_ok = isinstance(horas, list) and all(isinstance(h, str) for h in horas)
    valores = {
        "row_count": _entero(man.get("row_count")),
        "source_empty_slots": _entero(man.get("source_empty_slots")),
        "expected_hour_slots": _entero(man.get("expected_hour_slots")),
        "n_available_hours": len(horas) if horas_ok else None,
        "duplicate_display_rows_removed": _entero(man.get("duplicate_display_rows_removed")),
        "source_sha256": _texto(man.get("source_sha256")),
        "requested_start": _texto(man.get("requested_start")),
        "requested_end": _texto(man.get("requested_end")),
        "script_sha256": _texto(man.get("script_sha256")),
    }
    presentes = {"available_hours": horas_ok, "verification_status": _texto(man.get("verification_status")) is not None,
                 "artifact_name": _nombre_artefacto_valido(man.get("artifact_name"))}
    for campo in CAMPOS_MANIFIESTO + CAMPOS_R55:
        if campo not in presentes:
            presentes[campo] = valores[campo] is not None
    return {
        "ruta": ruta, "alias": alias_dmc(ruta, raiz), "sha256": entorno.sha256_bytes(datos),
        "codigo": ruta.parent.name, "anio": int(m.group(1)), "mes": int(m.group(2)),
        "entra": entra, "motivo": motivo, "id_artefacto": None,
        "artifact_name": man.get("artifact_name") if _nombre_artefacto_valido(man.get("artifact_name")) else None,
        "artifact_sha256": _texto(man.get("artifact_sha256")),
        "meta": {k: man.get(k) for k in ("artifact_name", "artifact_sha256", "row_count", "script_sha256",
                                         "verification_status")},
        "valores": valores,
        "campos_faltantes": [c for c in CAMPOS_MANIFIESTO + CAMPOS_R55 if not presentes[c]],
    }


def _fila_mes(reg: Mapping) -> dict:
    """Fila de ESQUEMA_MES con lo que se sabe sin abrir el artefacto."""
    v = reg["valores"]
    return {
        "codigo": reg["codigo"], "anio": reg["anio"], "mes": reg["mes"], "manifiesto": reg["alias"],
        "manifiesto_sha256": reg["sha256"], "artefacto_sha256": reg["artifact_sha256"],
        "id_artefacto": reg["id_artefacto"], "script_sha256": v["script_sha256"], "entra": reg["entra"],
        "motivo_exclusion": reg["motivo"], "row_count": v["row_count"], "source_empty_slots": v["source_empty_slots"],
        "expected_hour_slots": v["expected_hour_slots"], "n_available_hours": v["n_available_hours"],
        "duplicate_display_rows_removed": v["duplicate_display_rows_removed"], "source_sha256": v["source_sha256"],
        "requested_start": v["requested_start"], "requested_end": v["requested_end"],
        "campos_faltantes": list(reg["campos_faltantes"]), "p_ts": None, "p_qfe": None,
        "lat_txt": None, "lon_txt": None, "alt_txt": None,
    }


def _extraer_estacion(codigo: str, regs: Sequence[Mapping], adaptador: ModuleType,
                      umbrales: Umbrales) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Extracto y meses de una estación (fase 3): lee cada artefacto admitido con ``leer_artefacto``."""
    partes, filas_meses = [], []
    for reg in regs:
        fila = _fila_mes(reg)
        if reg["entra"]:
            payload, meta = adaptador.leer_artefacto(reg["ruta"])
            if any(meta.get(k) != v for k, v in reg["meta"].items()):
                raise ErrorExtraccion(f"el manifiesto cambió durante la lectura: {reg['alias']}")
            estacion = payload.get("station") if isinstance(payload, dict) else None
            if not isinstance(estacion, dict) or str(estacion.get("code", "")) != codigo:
                raise ErrorExtraccion(f"el artefacto no es de la estación de su carpeta: {reg['alias']}")
            extracto = control_propio(filas_a_extracto(payload, reg["id_artefacto"], umbrales), umbrales)
            if ((extracto["anio"] != reg["anio"]) | (extracto["mes"] != reg["mes"])).any():
                raise ErrorExtraccion(f"el artefacto trae etiquetas de otro mes: {reg['alias']}")
            md = estacion.get("source_metadata") if isinstance(estacion.get("source_metadata"), dict) else {}
            t = extracto["L"].to_numpy(dtype="datetime64[ns]")
            fila.update(
                artefacto_sha256=meta.get("content_sha256"),
                p_ts=_paso_para_meses(paso_nativo(t[extracto["ts"].notna().to_numpy()])),
                p_qfe=_paso_para_meses(paso_nativo(t[extracto["qfe"].notna().to_numpy()])),
                lat_txt=_texto(md.get(CLAVES_COORDENADAS[0])), lon_txt=_texto(md.get(CLAVES_COORDENADAS[1])),
                alt_txt=_texto(md.get(CLAVES_COORDENADAS[2])))
            partes.append(extracto)
        filas_meses.append(fila)
    if partes:
        extracto = pd.concat(partes, ignore_index=True).sort_values("L", kind="mergesort").reset_index(drop=True)
    else:
        extracto = tabla_vacia(ESQUEMA_EXTRACTO_HORA)
    if extracto["L"].duplicated().any():
        raise ErrorExtraccion(f"etiqueta repetida entre artefactos de {codigo}")
    validar_esquema(extracto, ESQUEMA_EXTRACTO_HORA, nombre=f"extracto {codigo}")
    meses = _marco(filas_meses, ESQUEMA_MES) if filas_meses else tabla_vacia(ESQUEMA_MES)
    return extracto, meses


def _a_listas(meses: pd.DataFrame) -> pd.DataFrame:
    """parquet devuelve las listas de ``campos_faltantes`` como arreglos: vuelven a ser listas."""
    meses = meses.copy()
    meses["campos_faltantes"] = pd.Series([list(x) if x is not None else [] for x in meses["campos_faltantes"]],
                                          dtype=object, index=meses.index)
    return meses


def _leer_meses_archivo(ruta: Path) -> pd.DataFrame:
    meses = _a_listas(pd.read_parquet(ruta))
    validar_esquema(meses, ESQUEMA_MES, nombre=Path(ruta).name)
    return meses


def _carpeta_dmc(destino: Path) -> Path:
    return Path(destino) / CARPETA_DMC


def _ruta_extracto(destino: Path, codigo: str) -> Path:
    if not _PATRON_ESTACION.fullmatch(str(codigo)):
        raise ValueError(f"código de estación inválido: {codigo!r}")
    return _carpeta_dmc(destino) / f"{codigo}.parquet"


def _contexto_dmc(adaptador: ModuleType, admitidas: frozenset[str], umbrales: Umbrales) -> dict:
    """Lo que, además de los manifiestos, determina la salida de una estación (huella de entrada)."""
    return {"extraccion_sha256": entorno.sha256_archivo(Path(__file__)), "adaptador_sha256": _sha_modulo(adaptador),
            "umbrales": umbrales.huella(), "versiones_admitidas": sorted(admitidas)}


def extraer_dmc(raiz_dmc: Path, adaptador: ModuleType, versiones_admitidas: set[str], umbrales: Umbrales,
                destino: Path, *, hecho: Callable[[str, str], bool], registrar: Callable[[str, str, str], None],
                avance: Callable[[int, int], None]) -> ResumenExtraccion:
    """Fase 3 de §5.2: por estación, lee sus meses admitidos y escribe extractos/dmc/<código>.parquet,
    más meses.parquet y artefactos_evaluados (atómicos). ``hecho``/``registrar`` son de avance.jsonl.

    Pasada 1: lee cada manifiesto una vez (sha256, admisión, campos) y numera los admitidos en orden de ruta
    (``id_artefacto``). Pasada 2: por estación («dmc/<código>»), salta la unidad si ``hecho`` la da por hecha
    con la misma huella de entrada y sus dos archivos están; si no, lee los artefactos con ``leer_artefacto``,
    aplica el control propio y escribe de forma atómica. ``versiones_admitidas`` puede ser la salida de
    ``fijados.versiones_admitidas``. ``avance(hechas, total)`` se llama después de cada estación.
    """
    raiz = Path(raiz_dmc)
    carpeta = _carpeta_dmc(destino)
    admitidas = conjunto_admitido(versiones_admitidas)
    regs = [_registro_manifiesto(r, raiz, versiones_admitidas) for r in listar_manifiestos(raiz)]
    siguiente = 0
    for reg in regs:
        if reg["entra"]:
            reg["id_artefacto"] = siguiente
            siguiente += 1
    huella_manifiestos = _huella_de_pares((r["alias"], r["sha256"]) for r in regs)
    por_estacion: dict[str, list[dict]] = {}
    for reg in regs:
        por_estacion.setdefault(reg["codigo"], []).append(reg)

    contexto = _contexto_dmc(adaptador, admitidas, umbrales)
    partes_meses, filas, con_datos = [], 0, 0
    total = len(por_estacion)
    for k, (codigo, regs_est) in enumerate(por_estacion.items(), start=1):
        unidad = f"dmc/{codigo}"
        huella_entrada = entorno.sha256_bytes(entorno.json_canonico({
            "unidad": unidad, "contexto": contexto,
            "manifiestos": [[r["alias"], r["sha256"], r["entra"], r["motivo"], r["id_artefacto"]] for r in regs_est]}))
        ruta_extracto = _ruta_extracto(destino, codigo)
        ruta_meses = carpeta / "meses" / f"{codigo}.parquet"
        meses_est = None
        if hecho(unidad, huella_entrada) and ruta_extracto.is_file() and ruta_meses.is_file():
            try:
                meses_est = _leer_meses_archivo(ruta_meses)
                esperado = [[r["alias"], r["sha256"], r["id_artefacto"]] for r in regs_est]
                leido = [[a, s, _sin_na(i)] for a, s, i in zip(meses_est["manifiesto"], meses_est["manifiesto_sha256"],
                                                                meses_est["id_artefacto"])]
                if leido != esperado:
                    meses_est = None
                else:
                    import pyarrow.parquet as pq
                    n_filas = pq.ParquetFile(ruta_extracto).metadata.num_rows
            except (OSError, ValueError, KeyError):
                meses_est = None
        if meses_est is None:
            extracto, meses_est = _extraer_estacion(codigo, regs_est, adaptador, umbrales)
            sha_extracto = entorno.escribir_atomico(ruta_extracto, _parquet_bytes(extracto))
            sha_meses = entorno.escribir_atomico(ruta_meses, _parquet_bytes(meses_est))
            registrar(unidad, huella_entrada, entorno.sha256_bytes(f"{sha_extracto}{sha_meses}".encode("ascii")))
            n_filas = len(extracto)
        partes_meses.append(meses_est)
        filas += int(n_filas)
        con_datos += bool(meses_est["entra"].any())
        avance(k, total)

    meses = pd.concat(partes_meses, ignore_index=True) if partes_meses else tabla_vacia(ESQUEMA_MES)
    meses = _a_listas(meses)
    validar_esquema(meses, ESQUEMA_MES, nombre="meses")
    artefactos = []
    por_alias = {r["alias"]: r for r in regs}
    for f in meses[meses["entra"]].sort_values("id_artefacto", kind="mergesort").itertuples(index=False):
        reg = por_alias[f.manifiesto]
        artefactos.append({
            "id_artefacto": int(f.id_artefacto), "codigo": f.codigo, "anio": int(f.anio), "mes": int(f.mes),
            "manifiesto": f.manifiesto, "manifiesto_sha256": f.manifiesto_sha256,
            "artefacto": f"DMC/{CARPETA_ESTACIONES}/{f.codigo}/{reg['artifact_name']}",
            "artefacto_sha256": f.artefacto_sha256, "row_count": int(f.row_count), "script_sha256": f.script_sha256})
    if [a["id_artefacto"] for a in artefactos] != list(range(len(artefactos))):
        raise ErrorExtraccion("los id_artefacto no son 0…n−1 en orden")
    excluidos = Counter(m for m in meses.loc[~meses["entra"], "motivo_exclusion"])
    resumen = ResumenExtraccion(estaciones=con_datos, meses_evaluados=len(artefactos),
                                meses_excluidos=dict(sorted(excluidos.items())), filas=filas,
                                huella_manifiestos=huella_manifiestos)
    entorno.escribir_atomico(carpeta / NOMBRE_MESES, _parquet_bytes(meses))
    entorno.escribir_atomico(carpeta / NOMBRE_ARTEFACTOS, entorno.json_canonico(artefactos))
    entorno.escribir_atomico(carpeta / NOMBRE_RESUMEN, entorno.json_canonico({
        "estaciones": resumen.estaciones, "meses_evaluados": resumen.meses_evaluados,
        "meses_excluidos": resumen.meses_excluidos, "filas": resumen.filas,
        "huella_manifiestos": resumen.huella_manifiestos, "manifiestos": len(regs)}))
    return resumen


def leer_extracto(destino: Path, codigo: str, columnas: Sequence[str] | None = None) -> pd.DataFrame:
    """extractos/dmc/<código>.parquet (ESQUEMA_EXTRACTO_HORA), entero o sólo ``columnas``, con sus tipos."""
    cols = list(ESQUEMA_EXTRACTO_HORA) if columnas is None else list(columnas)
    desconocidas = [c for c in cols if c not in ESQUEMA_EXTRACTO_HORA]
    if desconocidas:
        raise KeyError(f"columnas fuera de ESQUEMA_EXTRACTO_HORA: {desconocidas}")
    df = pd.read_parquet(_ruta_extracto(destino, codigo), columns=cols)
    validar_esquema(df, {c: ESQUEMA_EXTRACTO_HORA[c] for c in cols}, nombre=f"extracto {codigo}")
    return df


def leer_meses(destino: Path) -> pd.DataFrame:
    """extractos/dmc/meses.parquet (ESQUEMA_MES), con ``campos_faltantes`` como listas."""
    return _leer_meses_archivo(_carpeta_dmc(destino) / NOMBRE_MESES)


def leer_artefactos_evaluados(destino: Path) -> list[dict]:
    """extractos/dmc/artefactos_evaluados.json: lista ordenada por ``id_artefacto``."""
    return json.loads((_carpeta_dmc(destino) / NOMBRE_ARTEFACTOS).read_text(encoding="utf-8"))


# --- ERA5-Land ---------------------------------------------------------------
@dataclass(frozen=True)
class ControlMesEra5:
    yyyymm: str
    sha256: str
    eje_ok: bool              # paso 1 h, sin huecos, todo HH:00
    mediana_t2m_K: float
    mediana_sp_Pa: float
    unidades_ok: bool         # rangos de §3.4


def _control_a_json(c: ControlMesEra5) -> dict:
    def num(x: float) -> float | None:
        return None if not math.isfinite(x) else float(x)
    return {"yyyymm": c.yyyymm, "sha256": c.sha256, "eje_ok": bool(c.eje_ok), "mediana_t2m_K": num(c.mediana_t2m_K),
            "mediana_sp_Pa": num(c.mediana_sp_Pa), "unidades_ok": bool(c.unidades_ok)}


def _control_de_json(d: Mapping) -> ControlMesEra5:
    def num(x: Any) -> float:
        return float("nan") if x is None else float(x)
    return ControlMesEra5(yyyymm=d["yyyymm"], sha256=d["sha256"], eje_ok=bool(d["eje_ok"]),
                          mediana_t2m_K=num(d["mediana_t2m_K"]), mediana_sp_Pa=num(d["mediana_sp_Pa"]),
                          unidades_ok=bool(d["unidades_ok"]))


def _control_ausente(yyyymm: str) -> ControlMesEra5:
    return ControlMesEra5(yyyymm, "", False, float("nan"), float("nan"), False)


def ruta_mes_era5(raiz_era5l: Path, yyyymm: str) -> Path:
    """ERA5L/mensual/era5land_<AAAAMM>_chile_pixeles.nc."""
    return Path(raiz_era5l) / CARPETA_MENSUAL_ERA5 / PATRON_ARCHIVO_ERA5.format(yyyymm=yyyymm)


def _limites_mes(yyyymm: str) -> tuple[np.datetime64, np.datetime64]:
    """(primera hora del mes, última hora esperada: fin del mes o la última de ERA5-Land)."""
    mes = np.datetime64(datetime.strptime(yyyymm, "%Y%m").strftime("%Y-%m"), "M")
    inicio = mes.astype("datetime64[h]")
    fin = (mes + 1).astype("datetime64[h]") - _UNA_HORA
    return inicio, min(fin, ULTIMA_HORA_ERA5)


def _segundos_unix(variable: Any) -> np.ndarray | None:
    """Segundos UTC desde 1970 del eje de tiempo; None si las unidades, el calendario o los valores no se
    entienden (eso deja el eje anómalo: A1)."""
    unidades = getattr(variable, "units", None)
    calendario = getattr(variable, "calendar", None)
    m = _UNIDADES_TIEMPO.fullmatch(unidades.strip()) if isinstance(unidades, str) else None
    if m is None or calendario not in _CALENDARIOS:
        return None
    crudos = variable[:]
    if np.ma.getmaskarray(crudos).any():
        return None
    valores = np.asarray(crudos)
    if valores.dtype.kind == "f":
        if not np.isfinite(valores).all() or (valores != np.round(valores)).any():
            return None
        valores = valores.astype(np.int64)
    elif valores.dtype.kind not in "iu":
        return None
    origen = np.datetime64(f"{m['fecha']}T{m['hora'] or '00:00'}", "s")
    base = int((origen - np.datetime64("1970-01-01T00:00:00", "s")).astype(np.int64))
    return base + valores.astype(np.int64) * _FACTOR_TIEMPO[m["unidad"]]


def _netcdf4() -> ModuleType:
    """netCDF4 del entorno fijado (1.7.4), importado sólo al leer ERA5-Land.

    Su extensión compilada avisa «numpy.ndarray size changed» al importarse con numpy 2 (cabeceras de numpy
    1.x); es un aviso conocido de ABI y no cambia la lectura. Sólo ese aviso se silencia.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="numpy.ndarray size changed", category=RuntimeWarning)
        import netCDF4
    return netCDF4


def _decodificar_mes(datos: bytes, yyyymm: str,
                     sha256: str) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray], ControlMesEra5]:
    """Lector propio (§3.4) sobre los bytes ya leídos del mes: eje, pixel_id, t2m, sp, u10 y v10 completos."""
    netCDF4 = _netcdf4()
    ds = netCDF4.Dataset(f"era5land_{yyyymm}", mode="r", memory=datos)
    try:
        faltan = [v for v in ("time", "pixel_id", *VARIABLES_ERA5) if v not in ds.variables]
        if faltan:
            raise ErrorExtraccion(f"al mes {yyyymm} de ERA5-Land le faltan {faltan}")
        segundos = _segundos_unix(ds.variables["time"])
        n_t = len(ds.variables["time"])
        pid = np.asarray(np.ma.filled(ds.variables["pixel_id"][:], -1)).astype(np.int64)
        valores = {}
        for nombre in VARIABLES_ERA5:
            var = ds.variables[nombre]
            if tuple(var.dimensions) != ("time", "pixel"):
                raise ErrorExtraccion(f"{nombre} de {yyyymm} no tiene dimensiones (time, pixel)")
            valores[nombre] = np.ma.filled(np.ma.asarray(var[:]).astype(np.float32), np.nan)
            if valores[nombre].shape != (n_t, len(pid)):
                raise ErrorExtraccion(f"{nombre} de {yyyymm} con forma inesperada")
    finally:
        ds.close()
    if len(np.unique(pid)) != len(pid):
        raise ErrorExtraccion(f"pixel_id repetido en el mes {yyyymm}")

    inicio, fin = _limites_mes(yyyymm)
    if segundos is None:
        tiempos = np.full(n_t, np.datetime64("NaT"), dtype="datetime64[h]")
        eje_ok = False
    else:
        enteras = segundos % 3600 == 0
        tiempos = np.where(enteras, segundos // 3600, np.iinfo(np.int64).min).astype("datetime64[h]")
        siguiente_mes = (inicio.astype("datetime64[M]") + 1).astype("datetime64[h]")
        eje_ok = bool(n_t and enteras.all() and (np.diff(segundos) == 3600).all() and tiempos[0] == inicio
                      and fin <= tiempos[-1] < siguiente_mes)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        med_t = float(np.nanmedian(valores["t2m"])) if valores["t2m"].size else float("nan")
        med_sp = float(np.nanmedian(valores["sp"])) if valores["sp"].size else float("nan")
    (t_min, t_max), (sp_min, sp_max) = constantes.valor("ERA5_T2M_K"), constantes.valor("ERA5_SP_PA")
    unidades_ok = bool(t_min <= med_t <= t_max and sp_min <= med_sp <= sp_max)
    return tiempos, pid, valores, ControlMesEra5(yyyymm, sha256, eje_ok, med_t, med_sp, unidades_ok)


def _yyyymm_de(ruta: Path) -> str:
    m = _ARCHIVO_ERA5.fullmatch(Path(ruta).name)
    if m is None:
        raise ValueError(f"nombre de mes ERA5-Land fuera del patrón: {Path(ruta).name}")
    return m.group(1)


def leer_mes_era5land(ruta: Path) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray], ControlMesEra5]:
    """(tiempos datetime64[h] UTC, pixel_id, {t2m, sp, u10, v10} float32 T × P, control). Lee entero.

    Lee los bytes una sola vez: la sha256 es la de esos bytes y netCDF4 los abre en memoria. Unidades sin
    convertir (K, Pa, m/s); una hora que no es entera queda NaT y deja el eje anómalo.
    """
    yyyymm = _yyyymm_de(ruta)
    datos = Path(ruta).read_bytes()
    return _decodificar_mes(datos, yyyymm, entorno.sha256_bytes(datos))


def pixeles_validos(raiz_era5l: Path, umbrales: Umbrales) -> set[int]:
    """Intersección: t2m y sp con algún valor finito en cada mes de validez (200001, 201307, 202507)."""
    validos: set[int] | None = None
    for ident in IDS_MESES_VALIDEZ:
        yyyymm = str(int(umbrales.f(ident)))
        _, pid, valores, _ = leer_mes_era5land(ruta_mes_era5(raiz_era5l, yyyymm))
        ok = np.isfinite(valores["t2m"]).any(axis=0) & np.isfinite(valores["sp"]).any(axis=0)
        del_mes = {int(p) for p in pid[ok]}
        validos = del_mes if validos is None else validos & del_mes
    return set() if validos is None else validos


@dataclass(frozen=True)
class EleccionPixel:
    pixel_id: int | None
    distancia_km: float | None
    costera: bool


def elegir_pixel(lat: float, lon: float, catalogo_pixeles: pd.DataFrame, validos: set[int],
                 umbrales: Umbrales) -> EleccionPixel:
    """§3.3: celda propia válida; si no, centro válido más cercano a ≤ 15 km (empate: menor pixel_id)."""
    propia = tablas.celda_que_contiene(lat, lon, catalogo_pixeles)
    ids = catalogo_pixeles["pixel_id"].to_numpy(dtype=np.int64)
    if propia is not None and propia in validos:
        fila = catalogo_pixeles.loc[ids == propia].iloc[0]
        d = float(numerico.distancia_km(lat, lon, np.array([fila["latitude"]]), np.array([fila["longitude"]]))[0])
        return EleccionPixel(int(propia), d, False)
    candidatos = np.isin(ids, np.fromiter((int(v) for v in validos), dtype=np.int64, count=len(validos)))
    if not candidatos.any():
        return EleccionPixel(None, None, False)
    cand = catalogo_pixeles.loc[candidatos]
    d = numerico.distancia_km(lat, lon, cand["latitude"].to_numpy(dtype=np.float64),
                              cand["longitude"].to_numpy(dtype=np.float64))
    cerca = d <= umbrales.f("PIXEL_RADIO_KM")
    if not cerca.any():
        return EleccionPixel(None, None, False)
    ids_c, d_c = ids[candidatos][cerca], d[cerca]
    orden = np.lexsort((ids_c, d_c))           # distancia y, en empate, menor pixel_id
    return EleccionPixel(int(ids_c[orden[0]]), float(d_c[orden[0]]), True)


class SerieEra5Mapeada:
    """Implementación de tipos.SerieEra5 sobre extractos/era5/serie.f4 (n_pix × n_horas × 4, float32).

    ``valores`` da float64, con NaN fuera del eje global, en horas no enteras o en NaT; un píxel no enlazado
    lanza KeyError. ``media`` es la media de las horas con dato del píxel (sp̄ de z_pix, R-20).
    """

    def __init__(self, carpeta: Path):
        carpeta = Path(carpeta)
        indice = json.loads((carpeta / NOMBRE_INDICE).read_text(encoding="utf-8"))
        if tuple(indice["variables"]) != VARIABLES_ERA5:
            raise ErrorExtraccion("la serie ERA5-Land no tiene las variables de tipos.VARIABLES_ERA5")
        self.t0 = np.datetime64(indice["t0"], "h")
        self.n_horas = int(indice["n_horas"])
        self.pixel_ids = tuple(int(p) for p in indice["pixel_ids"])
        self.meses = {m: _control_de_json(c) for m, c in indice["meses"].items()}
        self.validos = None if indice.get("validos") is None else frozenset(int(v) for v in indice["validos"])
        self.catalogo_pixeles_sha256 = indice.get("catalogo_pixeles_sha256")
        self._fila = {p: i for i, p in enumerate(self.pixel_ids)}
        forma = (len(self.pixel_ids), self.n_horas, len(VARIABLES_ERA5))
        ruta = carpeta / NOMBRE_SERIE
        esperado = int(np.prod(forma)) * np.dtype(np.float32).itemsize
        if os.path.getsize(ruta) != esperado:
            raise ErrorExtraccion("serie.f4 no tiene el tamaño de su índice")
        self._datos = (np.memmap(ruta, dtype=np.float32, mode="r", shape=forma) if esperado
                       else np.empty(forma, dtype=np.float32))
        self._medias: dict[tuple[int, int], float] = {}
        self._t0_ns = self.t0.astype("datetime64[ns]")

    def _posicion(self, pixel_id: int, variable: str) -> tuple[int, int]:
        if variable not in VARIABLES_ERA5:
            raise KeyError(f"variable ERA5-Land desconocida: {variable!r}")
        return self._fila[int(pixel_id)], VARIABLES_ERA5.index(variable)

    def tiene(self, pixel_id: int) -> bool:
        return int(pixel_id) in self._fila

    def valores(self, pixel_id: int, variable: str, u: np.ndarray) -> np.ndarray:
        i, j = self._posicion(pixel_id, variable)
        arr = np.asarray(u)
        if arr.dtype.kind != "M":
            arr = pd.to_datetime(arr.ravel(), utc=True).tz_localize(None).to_numpy().reshape(arr.shape)
        t = arr.astype("datetime64[ns]")
        nat = np.isnat(t)
        delta = np.where(nat, 0, (t - self._t0_ns).astype(np.int64))
        k = delta // _NS_POR_HORA
        ok = ~nat & (delta % _NS_POR_HORA == 0) & (k >= 0) & (k < self.n_horas)
        salida = np.full(t.shape, np.nan, dtype=np.float64)
        salida[ok] = self._datos[i, k[ok], j]
        return salida

    def media(self, pixel_id: int, variable: str) -> float:
        clave = self._posicion(pixel_id, variable)
        if clave not in self._medias:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                serie = np.asarray(self._datos[clave[0], :, clave[1]], dtype=np.float64)
                self._medias[clave] = float(np.nanmean(serie))
        return self._medias[clave]


def _volcar_mes(mm: np.ndarray, pixel_ids: Sequence[int], tiempos: np.ndarray, pid: np.ndarray,
                valores: Mapping[str, np.ndarray], yyyymm: str) -> bytes:
    """Escribe en la serie las horas del mes (dentro del eje) de los píxeles enlazados; devuelve el bloque."""
    inicio, _ = _limites_mes(yyyymm)
    fin_mes = (inicio.astype("datetime64[M]") + 1).astype("datetime64[h]") - _UNA_HORA
    dentro = ~np.isnat(tiempos) & (tiempos >= max(inicio, T0_ERA5)) & (tiempos <= min(fin_mes, ULTIMA_HORA_ERA5))
    columna = {int(p): c for c, p in enumerate(pid)}
    cols = np.array([columna.get(int(p), -1) for p in pixel_ids], dtype=np.int64)
    presentes = cols >= 0
    idx_t = ((tiempos[dentro] - T0_ERA5) // _UNA_HORA).astype(np.int64)
    bloque = np.full((len(pixel_ids), len(idx_t), len(VARIABLES_ERA5)), np.nan, dtype=np.float32)
    for j, nombre in enumerate(VARIABLES_ERA5):
        x = valores[nombre][dentro][:, cols[presentes]].astype(np.float64)
        if nombre == "t2m":
            x = x - KELVIN_A_CELSIUS
        elif nombre == "sp":
            x = x / PA_POR_HPA
        bloque[presentes, :, j] = x.T.astype(np.float32)
    if len(pixel_ids) and len(idx_t):
        if (np.diff(idx_t) == 1).all():
            mm[:, idx_t[0]:idx_t[-1] + 1, :] = bloque
        else:
            mm[:, idx_t, :] = bloque
    return bloque.tobytes()


def _config_era5(pixel_ids: Sequence[int], meses: Sequence[str]) -> dict:
    return {"t0": str(T0_ERA5), "n_horas": N_HORAS_ERA5, "variables": list(VARIABLES_ERA5),
            "pixel_ids": list(pixel_ids), "meses": list(meses),
            "extraccion_sha256": entorno.sha256_archivo(Path(__file__))}


def _leer_json(ruta: Path) -> dict | None:
    try:
        obj = json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def extraer_era5land(raiz_era5l: Path, pixel_ids: Sequence[int], destino: Path, *,
                     hecho: Callable[[str, str], bool], registrar: Callable[[str, str, str], None],
                     avance: Callable[[int, int], None], meses: Sequence[str] | None = None,
                     validos: Collection[int] | None = None,
                     catalogo_sha256: str | None = None) -> tuple[SerieEra5Mapeada, dict[str, ControlMesEra5]]:
    """Fase 2 de §5.2: cada mes 200001…202609 entero (sha256), t2m→°C, sp→hPa, recorte en memoria.

    Unidad reanudable «era5/<AAAAMM>»; su huella de entrada combina la sha256 del archivo con la configuración
    (píxeles, meses, código). Cada mes se lee siempre entero, porque su sha256 va al informe; si la unidad ya
    está hecha con la misma huella, no se vuelve a decodificar. La serie se llena como ``serie.f4.part`` y sólo
    al final pasa a ``serie.f4`` junto con ``indice.json``. ``meses`` (por omisión MESES_ERA5), ``validos`` y
    ``catalogo_sha256`` quedan en el índice. ``avance(hechos, total)`` se llama después de cada mes.
    """
    meses = tuple(MESES_ERA5 if meses is None else meses)
    pixel_ids = sorted({int(p) for p in pixel_ids})
    carpeta = Path(destino) / CARPETA_ERA5
    final, parcial = carpeta / NOMBRE_SERIE, carpeta / (NOMBRE_SERIE + ".part")
    indice_ruta, progreso_ruta = carpeta / NOMBRE_INDICE, carpeta / NOMBRE_PROGRESO_ERA5
    for r in (final, parcial, indice_ruta, progreso_ruta):
        _prohibido_escribir(r)
    config = _config_era5(pixel_ids, meses)
    huella_config = entorno.sha256_bytes(entorno.json_canonico(config))
    forma = (len(pixel_ids), N_HORAS_ERA5, len(VARIABLES_ERA5))
    tamano = int(np.prod(forma)) * np.dtype(np.float32).itemsize

    def huella_entrada(sha: str) -> str:
        return entorno.sha256_bytes(entorno.json_canonico({"config": huella_config, "sha256": sha}))

    # 1) Serie ya terminada con la misma configuración: sólo se vuelven a calcular las sha256.
    indice = _leer_json(indice_ruta)
    if (indice is not None and indice.get("config") == huella_config and final.is_file()
            and os.path.getsize(final) == tamano):
        controles: dict[str, ControlMesEra5] | None = {}
        for k, m in enumerate(meses, start=1):
            previo = indice.get("meses", {}).get(m)
            ruta = ruta_mes_era5(raiz_era5l, m)
            sha = entorno.sha256_archivo(ruta) if ruta.is_file() else ""
            if previo is None or previo.get("sha256") != sha or (sha and not hecho(f"era5/{m}", huella_entrada(sha))):
                controles = None
                break
            controles[m] = _control_de_json(previo)
            avance(k, len(meses))
        if controles is not None:
            _borrar(progreso_ruta)
            return SerieEra5Mapeada(carpeta), controles

    # 2) Serie parcial de la misma configuración: se reanuda; si no, se empieza de cero.
    progreso = _leer_json(progreso_ruta)
    reanudar = (progreso is not None and progreso.get("config") == huella_config and parcial.is_file()
                and os.path.getsize(parcial) == tamano)
    carpeta.mkdir(parents=True, exist_ok=True)
    if not reanudar:
        for r in (final, indice_ruta, parcial, progreso_ruta):
            _borrar(r)
        progreso = {"config": huella_config, "meses": {}}
        if tamano:
            mm = np.memmap(parcial, dtype=np.float32, mode="w+", shape=forma)
            for i in range(forma[0]):
                mm[i] = np.nan
            mm.flush()
            del mm
        else:
            parcial.write_bytes(b"")
        entorno.escribir_atomico(progreso_ruta, entorno.json_canonico(progreso))
    mm = np.memmap(parcial, dtype=np.float32, mode="r+", shape=forma) if tamano else np.empty(forma, np.float32)
    controles = {}
    try:
        for k, m in enumerate(meses, start=1):
            ruta = ruta_mes_era5(raiz_era5l, m)
            if not ruta.is_file():
                controles[m] = _control_ausente(m)
                progreso["meses"][m] = _control_a_json(controles[m])
                avance(k, len(meses))
                continue
            datos = ruta.read_bytes()
            sha = entorno.sha256_bytes(datos)
            previo = progreso["meses"].get(m)
            if previo is not None and previo.get("sha256") == sha and hecho(f"era5/{m}", huella_entrada(sha)):
                controles[m] = _control_de_json(previo)
                avance(k, len(meses))
                continue
            tiempos, pid, valores, control = _decodificar_mes(datos, m, sha)
            del datos
            bloque = _volcar_mes(mm, pixel_ids, tiempos, pid, valores, m)
            if tamano:
                mm.flush()
            controles[m] = control
            progreso["meses"][m] = _control_a_json(control)
            entorno.escribir_atomico(progreso_ruta, entorno.json_canonico(progreso))
            registrar(f"era5/{m}", huella_entrada(sha), entorno.sha256_bytes(bloque))
            avance(k, len(meses))
    finally:
        del mm
    with open(parcial, "rb+") as f:
        os.fsync(f.fileno())
    indice = {**config, "config": huella_config, "meses": {m: _control_a_json(controles[m]) for m in meses},
              "validos": None if validos is None else sorted(int(v) for v in validos),
              "catalogo_pixeles_sha256": catalogo_sha256}
    entorno.escribir_atomico(indice_ruta, entorno.json_canonico(indice))
    os.replace(parcial, final)
    _borrar(progreso_ruta)
    return SerieEra5Mapeada(carpeta), controles
