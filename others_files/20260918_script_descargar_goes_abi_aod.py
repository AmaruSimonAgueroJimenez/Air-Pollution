#!/usr/bin/env python3
"""GOES-East ABI L2 AOD (disco completo): cada escaneo, píxel nativo de Chile.

Fuente: NOAA Open Data Dissemination en S3 público (``s3://noaa-goes16`` hasta
la transición del 7 de abril de 2025 y ``s3://noaa-goes19`` desde entonces),
producto ``ABI-L2-AODF`` (Aerosol Optical Depth, Full Disk). No requiere
credenciales. Cada archivo es un escaneo del disco completo en la grilla fija
GOES-R de 2 km al nadir (5424 × 5424 celdas) con cadencia nativa de 10 minutos
(modo 6; 15 minutos en modo 3 antes de abril de 2019, 5 minutos en modo 4).

Contrato:

* Se conservan únicamente las celdas cuya huella nativa (esquinas del píxel
  en ángulos de escaneo) intersecta la unión de comunas de Chile: continente,
  Juan Fernández, Desventuradas, Rapa Nui y Sala y Gómez, sin Antártica.
  No hay promedio comunal, remuestreo ni interpolación; el píxel de 2 km
  al nadir mide en Chile entre ~2,2 km (Arica) y ~4,1 km (Magallanes) por el
  ángulo de visión, que se registra por celda en el catálogo.
* Cada observación conserva ``AOD``, ``DQF``, ``AE1`` y ``AE2`` tal como
  vienen empaquetados (``*_i16``) y decodificados con ``scale_factor`` y
  ``add_offset`` del archivo fuente. Las celdas sin recuperación (``AOD`` en
  ``_FillValue``) no generan fila; su conteo por DQF queda en el catálogo de
  escaneos, de modo que la ausencia es reconstruible y explícita.
* El tiempo es el del escaneo (``time_bounds``/``t`` del archivo y
  ``s``/``e`` del nombre). El producto L2 no trae hora por píxel: la
  incertidumbre intra-escaneo es menor que la duración del barrido (≤ 10 min).
  Nunca se rellenan horas ni se inventan observaciones nocturnas.
* El algoritmo NOAA sólo recupera AOD con Sol sobre el horizonte y no en
  superficies brillantes (desierto, nieve, glint). Los escaneos en que todo
  Chile tiene ángulo cenital solar ≥ ``--sza-max`` + 2° se omiten sin
  descargarlos y se registran como ``omitido_noche_geometrica``.
* Publicación por día: ``observaciones/`` y ``catalogo_escaneos/`` en Parquet
  ZSTD escritos como ``.part``, reabiertos y validados antes de reemplazar;
  un manifiesto JSON por día con hashes de fuente y salida; WAL durable antes
  de retirar cada crudo; manifiesto CSV para reanudar sin repetir días.
* Reserva mínima de disco, presupuesto de staging y cuota acumulada de
  productos: alcanzar un límite pausa el proceso (código 75) y no autoriza
  borrar nada.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _chile_aoi import AOI, resumen_mascara, seleccionar  # noqa: E402
from _common import CONTAMINANTES, DATA, ensure_dir, get_logger, load_env  # noqa: E402
from _manifiesto_satelital import (  # noqa: E402
    Manifiesto, ahora_utc, sha256, sha256_conjunto_shapefile,
)
from _satellite_streaming import (  # noqa: E402
    BloqueoProceso,
    Manifiesto as ManifiestoCSV,
    escribir_json_atomico,
    escribir_parquet_atomico,
    fechas_inclusivas,
    validar_parquet,
)

log = get_logger("goes_abi_aod")

PRODUCTO = "GOES_ABI_AOD"
CONTRATO = "goes-abi-aod-pixel-v1"
SCHEMA_DIA = "airpollution.goes-abi-aod.day.v1"
SCHEMA_CATALOGO = "airpollution.goes-abi-aod.pixel-catalog.v1"
FLUJO = "goes_abi_aod"
PREFIJO_PRODUCTO = "ABI-L2-AODF"
REGION = "us-east-1"
BUCKETS = {"G16": "noaa-goes16", "G19": "noaa-goes19"}
DOCUMENTACION = (
    "https://www.star.nesdis.noaa.gov/goesr/product_aero_aod.php; "
    "GOES-R PUG Vol. 3 (L1b) §4.2.8 fixed grid; "
    "https://registry.opendata.aws/noaa-goes/"
)
# GOES-16 fue GOES-East operativo desde 2017-12-18; GOES-19 lo reemplazó el
# 2025-04-07 en la misma ranura (75,2°O). La grilla fija usa el origen nominal
# -75,0°; cualquier archivo con otro origen se rechaza, no se mezcla.
FECHA_INICIO_GOES_EAST = date(2017, 12, 18)
TRANSICION_G19 = date(2025, 4, 7)
LON_ORIGEN_GOES_EAST = -75.0
TOLERANCIA_LON_ORIGEN = 0.05
VOLUME_UUID = "54B3D309-A503-44C6-9229-581F3E4FECE3"
VOLUMEN_EXTERNO = Path("/Volumes/Datos")
GIB = 2**30
CADENCIAS = {"nativa": None, "30min": (0, 30), "horaria": (0,)}
ESCANEOS_ESPERADOS = {"M3": 96, "M4": 288, "M6": 144}
J2000 = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
NOMBRE_ARCHIVO = re.compile(
    r"^OR_ABI-L2-AODF-M(?P<modo>\d)_G(?P<sat>\d{2})_s(?P<s>\d{14})_e(?P<e>\d{14})"
    r"_c(?P<c>\d{14})\.nc$")
VARIABLES_OBS = ("AOD", "DQF", "AE1", "AE2")
COLUMNAS_OBS = ("scan_id", "pixel_id", "aod_i16", "aod", "dqf",
                "ae1_i16", "ae1", "ae2_i16", "ae2")
COLUMNAS_ESCANEOS = (
    "scan_id", "satelite", "modo", "inicio_utc", "fin_utc", "t_medio_utc",
    "creacion_utc", "archivo_fuente", "bytes_fuente", "sha256_fuente", "etag",
    "grid_id", "subpoint_lon", "lon_origen_proyeccion", "sza_min_chile_deg",
    "n_pixeles_chile", "n_recuperados", "n_dqf_0", "n_dqf_1", "n_dqf_2",
    "n_dqf_3", "n_dqf_otro",
)
COLUMNAS_CATALOGO = (
    "pixel_id", "y_index", "x_index", "x_rad", "y_rad", "lat", "lon",
    "lat_esq_no", "lon_esq_no", "lat_esq_ne", "lon_esq_ne",
    "lat_esq_se", "lon_esq_se", "lat_esq_so", "lon_esq_so",
    "angulo_cenital_satelite_deg", "cod_comuna", "aoi_id", "territorio",
    "grid_id",
)
PROCESSOR_SHA256 = sha256(Path(__file__).resolve()) if Path(__file__).is_file() else None


class LimiteSeguro(RuntimeError):
    """Pausa recuperable de cuota/espacio; no autoriza retirar datos."""


class GrillaInesperada(ValueError):
    """El archivo no está en la grilla fija GOES-East catalogada."""


# ---------------------------------------------------------------------------
# Geometría de la grilla fija GOES-R (PUG Vol. 3, §4.2.8.1)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Proyeccion:
    perspective_point_height: float
    semi_major_axis: float
    semi_minor_axis: float
    longitude_of_projection_origin: float
    sweep_angle_axis: str

    @property
    def H(self) -> float:  # noqa: N802
        return self.perspective_point_height + self.semi_major_axis

    def como_dict(self) -> dict:
        return asdict(self)


def leer_proyeccion(nc) -> Proyeccion:
    """Lee ``goes_imager_projection`` de un archivo ABI abierto con netCDF4."""
    if "goes_imager_projection" not in nc.variables:
        raise GrillaInesperada("falta goes_imager_projection")
    v = nc.variables["goes_imager_projection"]
    try:
        return Proyeccion(
            perspective_point_height=float(v.getncattr("perspective_point_height")),
            semi_major_axis=float(v.getncattr("semi_major_axis")),
            semi_minor_axis=float(v.getncattr("semi_minor_axis")),
            longitude_of_projection_origin=float(
                v.getncattr("longitude_of_projection_origin")),
            sweep_angle_axis=str(v.getncattr("sweep_angle_axis")),
        )
    except AttributeError as exc:
        raise GrillaInesperada(f"proyección incompleta: {exc}") from exc


def fixed_grid_a_latlon(x, y, proj: Proyeccion):
    """Ángulos de escaneo (rad) → lat/lon geodésicas WGS84 (grados).

    ``x`` e ``y`` se difunden entre sí (``x`` varía por columna, ``y`` por fila).
    Las celdas fuera del disco terrestre quedan NaN.
    """
    if proj.sweep_angle_axis != "x":
        raise GrillaInesperada(
            f"sweep_angle_axis={proj.sweep_angle_axis!r}; se esperaba 'x' (GOES-R)")
    x = np.asarray(x, dtype="float64")
    y = np.asarray(y, dtype="float64")
    r_eq, r_pol, H = proj.semi_major_axis, proj.semi_minor_axis, proj.H
    lam0 = math.radians(proj.longitude_of_projection_origin)
    sx_, cx_ = np.sin(x), np.cos(x)
    sy_, cy_ = np.sin(y), np.cos(y)
    a = sx_**2 + cx_**2 * (cy_**2 + (r_eq**2 / r_pol**2) * sy_**2)
    b = -2.0 * H * cx_ * cy_
    c = H**2 - r_eq**2
    disc = b * b - 4.0 * a * c
    with np.errstate(invalid="ignore", divide="ignore"):
        rs = (-b - np.sqrt(np.where(disc >= 0, disc, np.nan))) / (2.0 * a)
        sx = rs * cx_ * cy_
        sy = -rs * sx_
        sz = rs * cx_ * sy_
        lat = np.degrees(np.arctan((r_eq**2 / r_pol**2) * sz / np.sqrt((H - sx)**2 + sy**2)))
        lon = np.degrees(lam0 - np.arctan(sy / (H - sx)))
    return lat, lon


def angulo_cenital_satelite(lat, lon, proj: Proyeccion, subpoint_lon: float | None = None):
    """Ángulo cenital local del satélite (grados) para celdas dadas."""
    lat = np.radians(np.asarray(lat, dtype="float64"))
    lon = np.radians(np.asarray(lon, dtype="float64"))
    lon_sat = math.radians(subpoint_lon if subpoint_lon is not None
                           else proj.longitude_of_projection_origin)
    k = proj.semi_major_axis / proj.H
    cos_g = np.cos(lat) * np.cos(lon - lon_sat)
    gamma = np.arccos(np.clip(cos_g, -1.0, 1.0))
    theta = np.arctan2(np.sin(gamma), np.cos(gamma) - k)
    return np.degrees(theta)


def _decodificar(var):
    """Valores decodificados de una variable netCDF4 leída sin autoscale."""
    raw = np.asarray(var[:])
    scale = float(getattr(var, "scale_factor", 1.0))
    offset = float(getattr(var, "add_offset", 0.0))
    return raw.astype("float64") * scale + offset


def grid_fingerprint(proj: Proyeccion, x_rad: np.ndarray, y_rad: np.ndarray) -> str:
    """Identidad estable de la grilla fija: proyección, forma y ángulos."""
    h = hashlib.sha256()
    h.update(json.dumps({k: (round(v, 9) if isinstance(v, float) else v)
                         for k, v in proj.como_dict().items()},
                        sort_keys=True).encode("utf-8"))
    for arr in (x_rad, y_rad):
        arr = np.asarray(arr, dtype="float64")
        h.update(np.int64(arr.shape[0]).tobytes())
        h.update(np.round(arr * 1e9).astype("int64").tobytes())
    return h.hexdigest()[:24]


# ---------------------------------------------------------------------------
# Posición solar (NOAA Solar Calculator; exactitud ~0,01°, suficiente para
# decidir noche geométrica con margen de 2°)
# ---------------------------------------------------------------------------
def zenit_solar_deg(lat, lon, instante: datetime):
    """Ángulo cenital solar geométrico (sin refracción) en grados."""
    if instante.tzinfo is None:
        raise ValueError("el instante debe tener zona horaria UTC")
    t = instante.astimezone(timezone.utc)
    jd = (t - datetime(2000, 1, 1, 12, tzinfo=timezone.utc)).total_seconds() / 86400.0 + 2451545.0
    jc = (jd - 2451545.0) / 36525.0
    l0 = (280.46646 + jc * (36000.76983 + jc * 0.0003032)) % 360.0
    m = 357.52911 + jc * (35999.05029 - 0.0001537 * jc)
    e = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc)
    mr = math.radians(m)
    c = (math.sin(mr) * (1.914602 - jc * (0.004817 + 0.000014 * jc))
         + math.sin(2 * mr) * (0.019993 - 0.000101 * jc)
         + math.sin(3 * mr) * 0.000289)
    sun_true_long = l0 + c
    omega = 125.04 - 1934.136 * jc
    sun_app_long = sun_true_long - 0.00569 - 0.00478 * math.sin(math.radians(omega))
    obliq0 = 23.0 + (26.0 + (21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))) / 60.0) / 60.0
    obliq = obliq0 + 0.00256 * math.cos(math.radians(omega))
    decl = math.degrees(math.asin(math.sin(math.radians(obliq))
                                  * math.sin(math.radians(sun_app_long))))
    y_ = math.tan(math.radians(obliq / 2.0)) ** 2
    eq_time = 4.0 * math.degrees(
        y_ * math.sin(2 * math.radians(l0))
        - 2 * e * math.sin(mr)
        + 4 * e * y_ * math.sin(mr) * math.cos(2 * math.radians(l0))
        - 0.5 * y_ * y_ * math.sin(4 * math.radians(l0))
        - 1.25 * e * e * math.sin(2 * mr))
    minutos_utc = t.hour * 60.0 + t.minute + t.second / 60.0
    lon = np.asarray(lon, dtype="float64")
    lat = np.asarray(lat, dtype="float64")
    true_solar = (minutos_utc + eq_time + 4.0 * lon) % 1440.0
    ha = np.where(true_solar / 4.0 < 0, true_solar / 4.0 + 180.0, true_solar / 4.0 - 180.0)
    latr, declr, har = np.radians(lat), math.radians(decl), np.radians(ha)
    cos_z = np.sin(latr) * math.sin(declr) + np.cos(latr) * math.cos(declr) * np.cos(har)
    return np.degrees(np.arccos(np.clip(cos_z, -1.0, 1.0)))


def puntos_muestra_chile(aois: tuple[AOI, ...], paso: float = 0.5) -> tuple[np.ndarray, np.ndarray]:
    """Malla de muestreo de las AOI para evaluar la iluminación solar."""
    lats, lons = [], []
    for aoi in aois:
        lon0, lat0, lon1, lat1 = aoi.bbox
        la = np.arange(lat0, lat1 + paso, paso)
        lo = np.arange(lon0, lon1 + paso, paso)
        la = np.unique(np.concatenate([la, [lat1]]))
        lo = np.unique(np.concatenate([lo, [lon1]]))
        g_lat, g_lon = np.meshgrid(la, lo, indexing="ij")
        lats.append(g_lat.ravel())
        lons.append(g_lon.ravel())
    return np.concatenate(lats), np.concatenate(lons)


def sza_minimo_chile(instante: datetime, muestra: tuple[np.ndarray, np.ndarray]) -> float:
    return float(np.min(zenit_solar_deg(muestra[0], muestra[1], instante)))


# ---------------------------------------------------------------------------
# Catálogo de escaneos en S3
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Escaneo:
    key: str
    bucket: str
    satelite: str
    modo: str
    inicio: datetime
    fin: datetime
    creacion: datetime
    bytes: int
    etag: str | None

    @property
    def nombre(self) -> str:
        return self.key.rsplit("/", 1)[-1]

    @property
    def scan_id(self) -> int:
        return int(round((self.inicio - J2000).total_seconds()))

    @property
    def medio(self) -> datetime:
        return self.inicio + (self.fin - self.inicio) / 2


def _tiempo_abi(texto: str) -> datetime:
    """``YYYYJJJHHMMSSd`` (décimas de segundo) → datetime UTC."""
    base = datetime.strptime(texto[:13], "%Y%j%H%M%S").replace(tzinfo=timezone.utc)
    return base + timedelta(milliseconds=100 * int(texto[13]))


def parsear_nombre(key: str, bucket: str, size: int, etag: str | None) -> Escaneo | None:
    nombre = key.rsplit("/", 1)[-1]
    m = NOMBRE_ARCHIVO.match(nombre)
    if not m:
        return None
    return Escaneo(
        key=key, bucket=bucket, satelite=f"G{m.group('sat')}",
        modo=f"M{m.group('modo')}",
        inicio=_tiempo_abi(m.group("s")), fin=_tiempo_abi(m.group("e")),
        creacion=_tiempo_abi(m.group("c")), bytes=int(size),
        etag=(etag or "").strip('"') or None,
    )


def satelite_para(fecha: date, seleccion: str) -> str:
    if seleccion != "auto":
        return seleccion
    return "G19" if fecha >= TRANSICION_G19 else "G16"


def cliente_s3():
    """Cliente de sólo lectura sin cadena de credenciales AWS."""
    try:
        import boto3
        from botocore import UNSIGNED
        from botocore.config import Config
    except ImportError as exc:
        raise SystemExit("Falta boto3: pip install boto3") from exc
    return boto3.client(
        "s3", region_name=REGION,
        config=Config(signature_version=UNSIGNED, connect_timeout=20,
                      read_timeout=120,
                      retries={"max_attempts": 10, "mode": "standard"}),
    )


def listar_escaneos(s3, fecha: date, satelite: str) -> list[Escaneo]:
    """Lista los archivos AODF de un día (prefijo ``AAAA/DDD/``) en el bucket."""
    bucket = BUCKETS[satelite]
    prefijo = f"{PREFIJO_PRODUCTO}/{fecha:%Y}/{fecha:%j}/"
    escaneos: list[Escaneo] = []
    for pagina in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefijo):
        for obj in pagina.get("Contents", []):
            e = parsear_nombre(obj["Key"], bucket, obj.get("Size", 0), obj.get("ETag"))
            if e is not None and e.inicio.date() == fecha:
                escaneos.append(e)
    return sorted(escaneos, key=lambda e: (e.inicio, e.creacion))


def deduplicar_escaneos(escaneos: list[Escaneo]) -> tuple[list[Escaneo], list[dict]]:
    """Ante reprocesamientos (mismo inicio) conserva la creación más reciente."""
    por_inicio: dict[datetime, Escaneo] = {}
    descartados: list[dict] = []
    for e in sorted(escaneos, key=lambda e: (e.inicio, e.creacion)):
        previo = por_inicio.get(e.inicio)
        if previo is None:
            por_inicio[e.inicio] = e
            continue
        perdedor, ganador = (previo, e) if e.creacion >= previo.creacion else (e, previo)
        por_inicio[e.inicio] = ganador
        descartados.append({"key": perdedor.key, "estado": "descartado_duplicado",
                            "creacion_utc": perdedor.creacion.isoformat(),
                            "reemplazado_por": ganador.key})
    return [por_inicio[k] for k in sorted(por_inicio)], descartados


def huecos_esperados(escaneos: list[Escaneo], fecha: date) -> list[str]:
    """Inicios esperados según el modo dominante que no aparecen en el listado."""
    if not escaneos:
        return []
    modos = pd.Series([e.modo for e in escaneos]).value_counts()
    modo = str(modos.index[0])
    paso = {"M3": 15, "M4": 5, "M6": 10}.get(modo)
    if paso is None:
        return []
    presentes = {e.inicio.replace(second=0, microsecond=0) for e in escaneos}
    inicio_dia = datetime(fecha.year, fecha.month, fecha.day, tzinfo=timezone.utc)
    esperados = [inicio_dia + timedelta(minutes=k * paso) for k in range(1440 // paso)]
    return [t.isoformat() for t in esperados if t not in presentes]


def seleccionar_cadencia(escaneos: list[Escaneo], cadencia: str) -> tuple[list[Escaneo], list[dict]]:
    minutos = CADENCIAS[cadencia]
    if minutos is None:
        return list(escaneos), []
    elegidos, omitidos = [], []
    for e in escaneos:
        if e.inicio.minute in minutos:
            elegidos.append(e)
        else:
            omitidos.append({"key": e.key, "estado": "omitido_cadencia",
                             "cadencia": cadencia})
    return elegidos, omitidos


# ---------------------------------------------------------------------------
# Catálogo de píxeles de Chile en la grilla fija
# ---------------------------------------------------------------------------
def _cargar_comunas(comunas_path: Path):
    import geopandas as gpd

    g = gpd.read_file(comunas_path).to_crs("EPSG:4326")
    if "cod_comuna" not in g:
        raise ValueError(f"{comunas_path}: falta cod_comuna")
    try:
        g["geometry"] = g.geometry.make_valid()
    except AttributeError:
        from shapely.validation import make_valid
        g["geometry"] = g.geometry.map(make_valid)
    g["cod_comuna"] = pd.to_numeric(g["cod_comuna"], errors="raise").astype("int32")
    if (g["cod_comuna"] < 0).any():
        raise ValueError("la máscara contiene códigos administrativos negativos")
    g = g[g.geometry.notna() & ~g.geometry.is_empty].reset_index(drop=True)
    return g


def _aoi_de_centros(lat: np.ndarray, lon: np.ndarray, aois: tuple[AOI, ...],
                    margen: float) -> tuple[np.ndarray, np.ndarray]:
    aoi_id = np.full(lat.shape, "", dtype=object)
    territorio = np.full(lat.shape, "", dtype=object)
    for aoi in aois:
        lon0, lat0, lon1, lat1 = aoi.bbox
        dentro = ((aoi_id == "") & (lon >= lon0 - margen) & (lon <= lon1 + margen)
                  & (lat >= lat0 - margen) & (lat <= lat1 + margen))
        aoi_id[dentro] = aoi.id
        territorio[dentro] = aoi.territorio
    return aoi_id, territorio


def construir_catalogo(proj: Proyeccion, x_rad: np.ndarray, y_rad: np.ndarray,
                       comunas, aois: tuple[AOI, ...], *, grid_id: str,
                       subpoint_lon: float | None = None,
                       margen: float = 0.1) -> pd.DataFrame:
    """Celdas cuya huella nativa intersecta Chile; ``cod_comuna`` por centro."""
    import shapely
    from shapely.strtree import STRtree

    x_rad = np.asarray(x_rad, dtype="float64")
    y_rad = np.asarray(y_rad, dtype="float64")
    nx, ny = x_rad.size, y_rad.size
    if nx < 2 or ny < 2:
        raise GrillaInesperada("la grilla fija necesita al menos 2×2 celdas")
    dx = float(np.median(np.diff(x_rad)))
    dy = float(np.median(np.diff(y_rad)))
    # Selección gruesa por bbox de las AOI (con margen) fila por fila para no
    # materializar 29 millones de coordenadas a la vez.
    cajas = [(a.bbox[0] - margen, a.bbox[1] - margen, a.bbox[2] + margen, a.bbox[3] + margen)
             for a in aois]
    filas_sel, cols_sel = [], []
    bloque = 256
    for y0 in range(0, ny, bloque):
        yy = y_rad[y0:y0 + bloque]
        lat, lon = fixed_grid_a_latlon(x_rad[None, :], yy[:, None], proj)
        dentro = np.zeros(lat.shape, dtype=bool)
        for lon0, lat0, lon1, lat1 in cajas:
            dentro |= (lat >= lat0) & (lat <= lat1) & (lon >= lon0) & (lon <= lon1)
        r, c = np.nonzero(dentro)
        filas_sel.append(r + y0)
        cols_sel.append(c)
    iy = np.concatenate(filas_sel).astype("int64")
    ix = np.concatenate(cols_sel).astype("int64")
    if not iy.size:
        raise ValueError("ninguna celda de la grilla fija cae en las AOI de Chile")
    xc, yc = x_rad[ix], y_rad[iy]
    lat_c, lon_c = fixed_grid_a_latlon(xc, yc, proj)
    esquinas = {}
    for nombre, (sx, sy) in {"no": (-0.5, +0.5), "ne": (+0.5, +0.5),
                             "se": (+0.5, -0.5), "so": (-0.5, -0.5)}.items():
        # dy es negativo (y decrece hacia el sur): +0.5*|dy| es el borde norte.
        la, lo = fixed_grid_a_latlon(xc + sx * dx, yc + sy * abs(dy), proj)
        esquinas[nombre] = (la, lo)
    coords = np.stack([
        np.stack([esquinas["no"][1], esquinas["no"][0]], axis=-1),
        np.stack([esquinas["ne"][1], esquinas["ne"][0]], axis=-1),
        np.stack([esquinas["se"][1], esquinas["se"][0]], axis=-1),
        np.stack([esquinas["so"][1], esquinas["so"][0]], axis=-1),
        np.stack([esquinas["no"][1], esquinas["no"][0]], axis=-1),
    ], axis=1)
    finitos = np.isfinite(coords).all(axis=(1, 2)) & np.isfinite(lat_c) & np.isfinite(lon_c)
    if not finitos.all():
        raise GrillaInesperada("huellas no finitas dentro de las AOI de Chile")
    huellas = shapely.polygons(coords)
    huellas = shapely.make_valid(huellas)
    arbol = STRtree(comunas.geometry.to_numpy())
    idx_huella, _ = arbol.query(huellas, predicate="intersects")
    toca = np.zeros(len(huellas), dtype=bool)
    toca[np.unique(idx_huella)] = True
    if not toca.any():
        raise ValueError("ninguna huella de la grilla fija intersecta las comunas")
    sel = np.flatnonzero(toca)
    centros = shapely.points(lon_c[sel], lat_c[sel])
    idx_c, idx_com = arbol.query(centros, predicate="intersects")
    codigos = comunas["cod_comuna"].to_numpy()
    cod = np.full(sel.size, -1, dtype="int32")
    # Varias comunas pueden tocar un centro en el borde: prevalece el código
    # positivo menor; la zona sin demarcar (0) sólo si es la única.
    if idx_c.size:
        orden = np.lexsort((np.where(codigos[idx_com] == 0, 10**9, codigos[idx_com]), idx_c))
        idx_c, idx_com = idx_c[orden], idx_com[orden]
        primero = np.concatenate([[True], idx_c[1:] != idx_c[:-1]])
        cod[idx_c[primero]] = codigos[idx_com[primero]]
    aoi_id, territorio = _aoi_de_centros(lat_c[sel], lon_c[sel], aois, margen)
    if (aoi_id == "").any():
        raise ValueError("celdas seleccionadas sin AOI asignable")
    pixel_id = (iy[sel] * nx + ix[sel]).astype("int64")
    if pixel_id.max() >= 2**31:
        raise GrillaInesperada("pixel_id excede int32; grilla inesperadamente grande")
    catalogo = pd.DataFrame({
        "pixel_id": pixel_id.astype("int32"),
        "y_index": iy[sel].astype("int16"),
        "x_index": ix[sel].astype("int16"),
        "x_rad": xc[sel], "y_rad": yc[sel],
        "lat": lat_c[sel], "lon": lon_c[sel],
        "lat_esq_no": esquinas["no"][0][sel], "lon_esq_no": esquinas["no"][1][sel],
        "lat_esq_ne": esquinas["ne"][0][sel], "lon_esq_ne": esquinas["ne"][1][sel],
        "lat_esq_se": esquinas["se"][0][sel], "lon_esq_se": esquinas["se"][1][sel],
        "lat_esq_so": esquinas["so"][0][sel], "lon_esq_so": esquinas["so"][1][sel],
        "angulo_cenital_satelite_deg": angulo_cenital_satelite(
            lat_c[sel], lon_c[sel], proj, subpoint_lon).astype("float32"),
        "cod_comuna": cod,
        "aoi_id": aoi_id.astype(str),
        "territorio": territorio.astype(str),
        "grid_id": grid_id,
    }).sort_values("pixel_id").reset_index(drop=True)
    if catalogo["pixel_id"].duplicated().any():
        raise ValueError("pixel_id duplicado en el catálogo")
    return catalogo.loc[:, list(COLUMNAS_CATALOGO)]


def _validar_catalogo_df(df: pd.DataFrame) -> None:
    if df.empty or df["pixel_id"].duplicated().any():
        raise ValueError("catálogo vacío o con pixel_id duplicado")
    if not np.isfinite(df[["lat", "lon"]].to_numpy(dtype="float64")).all():
        raise ValueError("catálogo con coordenadas no finitas")
    if not df["lat"].between(-60, 0).all() or not df["lon"].between(-115, -60).all():
        raise ValueError("catálogo con coordenadas fuera del dominio chileno")
    if df["grid_id"].nunique() != 1:
        raise ValueError("catálogo con más de un grid_id")
    if (df["cod_comuna"] < -1).any():
        raise ValueError("cod_comuna inválido en catálogo")


def _huellas_catalogo(catalogo: pd.DataFrame):
    import shapely

    coords = np.stack([
        np.stack([catalogo["lon_esq_no"], catalogo["lat_esq_no"]], axis=-1),
        np.stack([catalogo["lon_esq_ne"], catalogo["lat_esq_ne"]], axis=-1),
        np.stack([catalogo["lon_esq_se"], catalogo["lat_esq_se"]], axis=-1),
        np.stack([catalogo["lon_esq_so"], catalogo["lat_esq_so"]], axis=-1),
        np.stack([catalogo["lon_esq_no"], catalogo["lat_esq_no"]], axis=-1),
    ], axis=1).astype("float64")
    return list(shapely.make_valid(shapely.polygons(coords)))


def publicar_enlaces(carpeta: Path, catalogo: pd.DataFrame, comunas_path: Path,
                     mascara_sha: str, grid_id: str) -> dict:
    """Enlaces muchos-a-muchos píxel↔comuna con huella nativa y píxel↔estación."""
    from crear_enlaces_pixeles import construir_enlace, enlazar_estaciones

    carpeta = ensure_dir(carpeta)
    enlace_path = carpeta / "pixel_comuna.parquet"
    estacion_path = carpeta / "estacion_pixel.parquet"
    excluidas_path = carpeta / "estaciones_excluidas.parquet"
    meta_path = carpeta / "metadata.json"
    estaciones = DATA / "sinca" / "estaciones_georreferenciadas.csv"
    fuente_estaciones = ({"ruta": str(estaciones), "bytes": estaciones.stat().st_size,
                          "sha256": sha256(estaciones)} if estaciones.exists() else None)
    if meta_path.exists() and enlace_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if (meta.get("mascara_sha256") == mascara_sha and meta.get("grid_id") == grid_id
                and meta.get("processor_sha256") == PROCESSOR_SHA256
                and meta.get("estaciones_fuente") == fuente_estaciones):
            return meta
    pix = catalogo[["pixel_id", "lat", "lon"]].copy()
    pix["geometry"] = _huellas_catalogo(catalogo)
    enlace = construir_enlace(pix, comunas_path, lote=20_000)
    _publicar_parquet_simple(enlace, enlace_path)
    archivos = {"pixel_comuna": _registro_parquet(enlace_path, len(enlace))}
    if fuente_estaciones is not None:
        est, excluidas = enlazar_estaciones(enlace, estaciones)
        _publicar_parquet_simple(est, estacion_path)
        _publicar_parquet_simple(excluidas, excluidas_path)
        archivos["estacion_pixel"] = _registro_parquet(estacion_path, len(est))
        archivos["estaciones_excluidas"] = _registro_parquet(excluidas_path, len(excluidas))
    conteos = enlace.groupby("cod_comuna")["pixel_id"].nunique()
    meta = {
        "schema": "airpollution.pixel-commune-links.v1",
        "producto": PRODUCTO, "grid_id": grid_id,
        "processor_sha256": PROCESSOR_SHA256,
        "mascara_sha256": mascara_sha,
        "metodo": "intersección exacta de la huella nativa ABI (4 esquinas); muchos-a-muchos",
        "sin_agregacion": True,
        "enlaces_pixel_comuna": int(len(enlace)),
        "pixeles_enlazados": int(enlace["pixel_id"].nunique()),
        "unidades_administrativas": int(enlace["cod_comuna"].nunique()),
        "min_pixeles_por_unidad": int(conteos.min()),
        "max_pixeles_por_unidad": int(conteos.max()),
        "estaciones_fuente": fuente_estaciones,
        "archivos": archivos,
        "utc": ahora_utc(),
    }
    escribir_json_atomico(meta, meta_path)
    return meta


def _publicar_parquet_simple(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    part.unlink(missing_ok=True)
    try:
        df.to_parquet(part, index=False, compression="zstd")
        chk = pd.read_parquet(part)
        if len(chk) != len(df) or list(chk.columns) != list(df.columns):
            raise ValueError(f"{path}: reapertura Parquet no coincide")
        with part.open("rb") as fh:
            os.fsync(fh.fileno())
        os.replace(part, path)
    finally:
        part.unlink(missing_ok=True)


def _registro_parquet(path: Path, filas: int) -> dict:
    return {"filas": int(filas), "bytes": int(path.stat().st_size), "sha256": sha256(path)}


class CatalogoPixeles:
    """Carga o construye el catálogo de la grilla fija; se cachea por grid_id."""

    def __init__(self, base: Path, comunas_path: Path, aois: tuple[AOI, ...],
                 mascara_sha: str, mani: Manifiesto, *, enlaces: bool = False):
        self.base = base
        self.comunas_path = comunas_path
        self.aois = aois
        self.mascara_sha = mascara_sha
        self.mani = mani
        # Los enlaces muchos-a-muchos con huella exacta tardan decenas de
        # minutos sobre la máscara oficial (346 polígonos muy detallados);
        # se calculan sólo cuando se piden explícitamente (``--enlaces``).
        self.enlaces = enlaces
        self._cache: dict[str, dict] = {}
        self._comunas = None

    def _comunas_cargadas(self):
        if self._comunas is None:
            self._comunas = _cargar_comunas(self.comunas_path)
        return self._comunas

    def obtener(self, proj: Proyeccion, x_rad: np.ndarray, y_rad: np.ndarray,
                subpoint_lon: float | None) -> dict:
        grid_id = grid_fingerprint(proj, x_rad, y_rad)
        if grid_id in self._cache:
            return self._cache[grid_id]
        carpeta = self.base / "catalogo_pixeles" / f"grid={grid_id}"
        path = carpeta / "pixeles.parquet"
        meta_path = carpeta / "metadata.json"
        if path.exists() and meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if (meta.get("schema") != SCHEMA_CATALOGO
                    or meta.get("mascara_sha256") != self.mascara_sha
                    or meta.get("grid_id") != grid_id):
                raise ValueError(f"catálogo {carpeta} pertenece a otra máscara/grilla")
            registro = meta.get("archivo") or {}
            if (registro.get("bytes") != path.stat().st_size
                    or registro.get("sha256") != sha256(path)):
                raise ValueError(f"catálogo {path} no coincide con su metadata")
            df = pd.read_parquet(path)
            _validar_catalogo_df(df)
        else:
            if path.exists() != meta_path.exists():
                raise ValueError(f"catálogo {carpeta} incompleto; no se mezclará")
            log.info("Construyendo catálogo de píxeles de Chile para grid %s", grid_id)
            df = construir_catalogo(proj, x_rad, y_rad, self._comunas_cargadas(),
                                    self.aois, grid_id=grid_id, subpoint_lon=subpoint_lon)
            _validar_catalogo_df(df)
            filas, chk = escribir_parquet_atomico(df, path, COLUMNAS_CATALOGO, _validar_catalogo_df)
            meta = {
                "schema": SCHEMA_CATALOGO, "producto": PRODUCTO, "grid_id": grid_id,
                "proyeccion": proj.como_dict(),
                "nx": int(x_rad.size), "ny": int(y_rad.size),
                "dx_rad": float(np.median(np.diff(x_rad))),
                "dy_rad": float(np.median(np.diff(y_rad))),
                "pixel_id": "y_index * nx + x_index (int32); válido sólo dentro de este grid_id",
                "seleccion": "huella nativa (4 esquinas en ángulos de escaneo) intersecta comunas",
                "cod_comuna": "centro de celda; -1 si sólo la huella toca Chile; 0 zona sin demarcar",
                "mascara": str(self.comunas_path), "mascara_sha256": self.mascara_sha,
                "unidades_administrativas": resumen_mascara(self.comunas_path),
                "processor_sha256": PROCESSOR_SHA256,
                "pixeles": int(filas),
                "por_aoi": {k: int(v) for k, v in df["aoi_id"].value_counts().items()},
                "angulo_cenital_satelite_deg": {
                    "min": float(df["angulo_cenital_satelite_deg"].min()),
                    "max": float(df["angulo_cenital_satelite_deg"].max())},
                "archivo": {"filas": int(filas), "bytes": path.stat().st_size, "sha256": chk},
                "utc": ahora_utc(),
            }
            escribir_json_atomico(meta, meta_path)
            self.mani.registrar({"evento": "catalogo_pixeles_publicado", "grid_id": grid_id,
                                 "pixeles": int(filas), "ruta": str(path), "sha256": chk})
        enlaces = None
        if self.enlaces:
            try:
                enlaces = publicar_enlaces(carpeta / "enlaces_geoespaciales", df,
                                           self.comunas_path, self.mascara_sha, grid_id)
                self.mani.registrar({"evento": "enlaces_publicados", "grid_id": grid_id,
                                     "enlaces_pixel_comuna": enlaces.get("enlaces_pixel_comuna")})
            except Exception as exc:  # noqa: BLE001
                self.mani.registrar({"evento": "enlaces_no_publicados", "grid_id": grid_id,
                                     "error": f"{type(exc).__name__}: {exc}"})
                log.warning("Enlaces píxel-comuna no publicados para %s: %s", grid_id, exc)
        y_idx = df["y_index"].to_numpy(dtype="int64")
        x_idx = df["x_index"].to_numpy(dtype="int64")
        entrada = {
            "grid_id": grid_id, "meta": meta, "df": df, "enlaces": enlaces,
            "y0": int(y_idx.min()), "y1": int(y_idx.max()),
            "x0": int(x_idx.min()), "x1": int(x_idx.max()),
            "y_rel": y_idx - int(y_idx.min()), "x_rel": x_idx - int(x_idx.min()),
            "pixel_id": df["pixel_id"].to_numpy(dtype="int32"),
        }
        self._cache[grid_id] = entrada
        return entrada


# ---------------------------------------------------------------------------
# Lectura y recorte de un escaneo
# ---------------------------------------------------------------------------
def _attrs(var) -> dict:
    out = {}
    for nombre in var.ncattrs():
        valor = var.getncattr(nombre)
        if isinstance(valor, np.ndarray):
            valor = valor.tolist()
        elif isinstance(valor, np.generic):
            valor = valor.item()
        out[nombre] = valor
    return out


def _escalar(var):
    """Valor Python de una variable escalar o 1-D pequeña (sin autoscale)."""
    arr = np.asarray(var[:])
    if arr.dtype.kind in "SU" or arr.dtype == object:
        return arr.tolist() if arr.ndim else str(arr)
    if arr.ndim == 0:
        return arr.item()
    if arr.size <= 64:
        return arr.tolist()
    return {"shape": list(arr.shape), "dtype": str(arr.dtype), "omitido": True}


def _tiempo_j2000(segundos: float) -> datetime:
    return J2000 + timedelta(seconds=float(segundos))


def recortar_escaneo(path: Path, escaneo: Escaneo, catalogos: CatalogoPixeles,
                     muestra_sza: tuple[np.ndarray, np.ndarray]) -> tuple[pd.DataFrame, dict]:
    """Lee un AODF, verifica la grilla y devuelve filas de Chile + resumen."""
    import netCDF4

    with netCDF4.Dataset(path, "r") as nc:
        nc.set_auto_maskandscale(False)
        proj = leer_proyeccion(nc)
        if abs(proj.longitude_of_projection_origin - LON_ORIGEN_GOES_EAST) > TOLERANCIA_LON_ORIGEN:
            raise GrillaInesperada(
                f"origen de proyección {proj.longitude_of_projection_origin}° "
                f"≠ GOES-East {LON_ORIGEN_GOES_EAST}°")
        for nombre in ("x", "y", *VARIABLES_OBS):
            if nombre not in nc.variables:
                raise GrillaInesperada(f"falta la variable {nombre}")
        x_rad = _decodificar(nc.variables["x"])
        y_rad = _decodificar(nc.variables["y"])
        subpoint = None
        if "nominal_satellite_subpoint_lon" in nc.variables:
            subpoint = float(np.asarray(nc.variables["nominal_satellite_subpoint_lon"][:]).ravel()[0])
        cat = catalogos.obtener(proj, x_rad, y_rad, subpoint)
        ny, nx = y_rad.size, x_rad.size
        y0, y1, x0, x1 = cat["y0"], cat["y1"], cat["x0"], cat["x1"]
        if y1 >= ny or x1 >= nx:
            raise GrillaInesperada("el catálogo excede la forma del archivo")
        campos = {}
        attrs_vars = {}
        for nombre in VARIABLES_OBS:
            var = nc.variables[nombre]
            if tuple(var.dimensions) != ("y", "x") or var.shape != (ny, nx):
                raise GrillaInesperada(f"{nombre} no tiene dimensiones (y, x) de {ny}×{nx}")
            bloque = np.asarray(var[y0:y1 + 1, x0:x1 + 1])
            campos[nombre] = bloque[cat["y_rel"], cat["x_rel"]]
            attrs_vars[nombre] = _attrs(var)
        t_medio = None
        inicio_nc = fin_nc = None
        if "t" in nc.variables:
            t_medio = _tiempo_j2000(np.asarray(nc.variables["t"][:]).ravel()[0])
        if "time_bounds" in nc.variables:
            tb = np.asarray(nc.variables["time_bounds"][:]).ravel()
            if tb.size >= 2:
                inicio_nc, fin_nc = _tiempo_j2000(tb[0]), _tiempo_j2000(tb[1])
        if inicio_nc is not None and abs((inicio_nc - escaneo.inicio).total_seconds()) > 2.0:
            raise ValueError(
                f"time_bounds {inicio_nc.isoformat()} no coincide con el nombre "
                f"{escaneo.inicio.isoformat()}")
        escalares = {}
        for nombre, var in nc.variables.items():
            if nombre in VARIABLES_OBS or nombre in ("x", "y"):
                continue
            if var.ndim <= 1 and (var.ndim == 0 or var.shape[0] <= 64):
                escalares[nombre] = {"valor": _escalar(var), "attrs": _attrs(var)}
        globales = _attrs(nc)

    for nombre in ("AOD", "AE1", "AE2"):
        if campos[nombre].dtype != np.int16:
            raise GrillaInesperada(
                f"{nombre} viene como {campos[nombre].dtype}, no int16 empaquetado; "
                "revisar la versión del producto antes de conservarlo")
    if campos["DQF"].dtype.kind not in "iu" or campos["DQF"].dtype.itemsize != 1:
        raise GrillaInesperada(f"DQF viene como {campos['DQF'].dtype}, no entero de 8 bits")
    fill_aod = _fill_de_attrs(attrs_vars["AOD"])
    raw_aod = campos["AOD"]
    con_dato = np.ones(raw_aod.shape, dtype=bool) if fill_aod is None else raw_aod != fill_aod
    dqf = campos["DQF"].astype("int16")
    conteos = {f"n_dqf_{k}": int(np.count_nonzero(dqf == k)) for k in range(4)}
    conteos["n_dqf_otro"] = int(dqf.size - sum(conteos.values()))

    def decodificar(nombre):
        a = attrs_vars[nombre]
        raw = campos[nombre][con_dato]
        val = raw.astype("float64") * float(a.get("scale_factor", 1.0)) + float(a.get("add_offset", 0.0))
        f = _fill_de_attrs(a)
        if f is not None:
            val = np.where(raw == f, np.nan, val)
        return raw.astype("int16"), val.astype("float32")

    aod_i16, aod = decodificar("AOD")
    ae1_i16, ae1 = decodificar("AE1")
    ae2_i16, ae2 = decodificar("AE2")
    filas = pd.DataFrame({
        "scan_id": np.full(int(con_dato.sum()), escaneo.scan_id, dtype="int64"),
        "pixel_id": cat["pixel_id"][con_dato],
        "aod_i16": aod_i16, "aod": aod,
        "dqf": dqf[con_dato].astype("int8"),
        "ae1_i16": ae1_i16, "ae1": ae1,
        "ae2_i16": ae2_i16, "ae2": ae2,
    })
    resumen = {
        "grid_id": cat["grid_id"],
        "proyeccion": proj.como_dict(),
        "subpoint_lon": subpoint,
        "t_medio_utc": t_medio.isoformat() if t_medio else None,
        "inicio_nc_utc": inicio_nc.isoformat() if inicio_nc else None,
        "fin_nc_utc": fin_nc.isoformat() if fin_nc else None,
        "n_pixeles_chile": int(raw_aod.size),
        "n_recuperados": int(con_dato.sum()),
        **conteos,
        "sza_min_chile_deg": sza_minimo_chile(t_medio or escaneo.medio, muestra_sza),
        "atributos_variables": attrs_vars,
        "atributos_globales": globales,
        "variables_escalares": escalares,
    }
    return filas, resumen


def _fill_de_attrs(attrs: dict):
    for clave in ("_FillValue", "missing_value"):
        if clave in attrs:
            v = attrs[clave]
            return v[0] if isinstance(v, list) else v
    return None


def diferencias(referencia: dict, actual: dict) -> dict:
    """Claves de ``actual`` cuyo valor difiere de ``referencia`` (o faltan en ella).

    Los manifiestos diarios guardan completos los atributos globales y las
    variables escalares del primer escaneo y, para los demás, sólo lo que
    cambia (tiempos, estadísticas del escaneo, versiones). Las claves que
    desaparecen se listan bajo ``__ausentes__``.
    """
    out = {k: v for k, v in actual.items() if referencia.get(k, object()) != v}
    ausentes = sorted(set(referencia) - set(actual))
    if ausentes:
        out["__ausentes__"] = ausentes
    return out


# ---------------------------------------------------------------------------
# Validadores de salidas diarias
# ---------------------------------------------------------------------------
def _validar_obs(df: pd.DataFrame) -> None:
    if df.empty or df.duplicated(["scan_id", "pixel_id"]).any():
        raise ValueError("observaciones vacías o duplicadas (scan_id, pixel_id)")
    if not np.isfinite(df["aod"].to_numpy(dtype="float64")).all():
        raise ValueError("AOD no finito en filas con recuperación")
    if not df["dqf"].isin([-1, 0, 1, 2, 3]).all():
        raise ValueError("DQF fuera de {-1,0,1,2,3}")
    if (df["aod"] < -0.1).any() or (df["aod"] > 6.0).any():
        raise ValueError("AOD fuera del rango físico del producto")


def _validar_escaneos(df: pd.DataFrame) -> None:
    if df.empty or df["scan_id"].duplicated().any():
        raise ValueError("catálogo de escaneos vacío o con scan_id duplicado")
    if (df["n_recuperados"] > df["n_pixeles_chile"]).any():
        raise ValueError("más recuperaciones que píxeles")
    if df["sha256_fuente"].str.len().ne(64).any():
        raise ValueError("sha256 de fuente inválido")


# ---------------------------------------------------------------------------
# Disco, cuotas y volumen
# ---------------------------------------------------------------------------
def verificar_volumen(base: Path, volume_uuid: str | None) -> dict:
    """Exige el disco externo correcto cuando la raíz vive en /Volumes/Datos."""
    info = {"ruta": str(base), "verificado": False}
    if not volume_uuid or platform.system() != "Darwin":
        info["motivo"] = "sin verificación de UUID (no macOS o UUID vacío)"
        return info
    if VOLUMEN_EXTERNO not in base.parents and base != VOLUMEN_EXTERNO:
        info["motivo"] = "raíz explícita fuera de /Volumes/Datos"
        return info
    try:
        import plistlib
        salida = subprocess.run(["diskutil", "info", "-plist", str(VOLUMEN_EXTERNO)],
                                check=True, capture_output=True).stdout
        actual = plistlib.loads(salida).get("VolumeUUID")
    except Exception as exc:  # noqa: BLE001
        raise LimiteSeguro(f"no se pudo verificar el volumen externo: {exc}") from exc
    if actual != volume_uuid:
        raise LimiteSeguro(f"disco externo ausente o UUID distinto ({actual})")
    info.update({"verificado": True, "volume_uuid": actual})
    return info


def gib_libres(path: Path) -> float:
    return shutil.disk_usage(path).free / GIB


def tamano_gib(*rutas: Path) -> float:
    total = 0
    for ruta in rutas:
        if ruta.exists():
            for p in ruta.rglob("*"):
                if p.is_file():
                    total += p.stat().st_size
    return total / GIB


def exigir_reserva(base: Path, reserva_gib: float, *, fase: str, unidad: str) -> None:
    libres = gib_libres(base)
    if libres < reserva_gib:
        raise LimiteSeguro(f"quedan {libres:.1f} GiB libres; reserva {reserva_gib:.1f} GiB "
                           f"antes de {fase} {unidad}")


# ---------------------------------------------------------------------------
# Descarga
# ---------------------------------------------------------------------------
def descargar_objeto(s3, escaneo: Escaneo, destino: Path, limite_mbps: float | None) -> Path:
    """Descarga a ``.part`` y publica por rename; reutiliza un crudo íntegro."""
    if destino.exists() and destino.stat().st_size == escaneo.bytes:
        return destino
    part = destino.with_name(destino.name + "." + uuid.uuid4().hex + ".part")
    t0 = time.monotonic()
    try:
        s3.download_file(escaneo.bucket, escaneo.key, str(part))
        if part.stat().st_size != escaneo.bytes:
            raise ValueError(f"tamaño descargado {part.stat().st_size} ≠ listado {escaneo.bytes}")
        with part.open("rb") as fh:
            os.fsync(fh.fileno())
        os.replace(part, destino)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    if limite_mbps:
        minimo = escaneo.bytes * 8 / (limite_mbps * 1e6)
        restante = minimo - (time.monotonic() - t0)
        if restante > 0:
            time.sleep(restante)
    return destino


# ---------------------------------------------------------------------------
# Día transaccional
# ---------------------------------------------------------------------------
def rutas_dia(base: Path, fecha: date) -> dict[str, Path]:
    y, m = f"{fecha:%Y}", f"{fecha:%m}"
    etiqueta = f"{fecha:%Y%m%d}"
    return {
        "obs": base / "observaciones" / f"year={y}" / f"month={m}" / f"goes_abi_obs_{etiqueta}.parquet",
        "escaneos": base / "catalogo_escaneos" / f"year={y}" / f"month={m}" / f"goes_abi_escaneos_{etiqueta}.parquet",
        "manifiesto": base / "manifiestos_escaneos" / f"year={y}" / f"month={m}" / f"goes_abi_{etiqueta}.json",
    }


def dia_publicado_valido(base: Path, fecha: date, registro, *, revalidar: bool) -> bool:
    rutas = rutas_dia(base, fecha)
    mani = rutas["manifiesto"]
    if registro is None or not mani.exists():
        return False
    if registro.estado == "sin_datos":
        return True
    if registro.sha256 and sha256(mani) != registro.sha256:
        return False
    try:
        datos = json.loads(mani.read_text(encoding="utf-8"))
    except ValueError:
        return False
    salidas = datos.get("salidas", {})
    for clave in ("obs", "escaneos"):
        reg = salidas.get({"obs": "observaciones", "escaneos": "catalogo_escaneos"}[clave])
        if reg is None:
            if clave == "obs" and int(datos.get("filas_observaciones", 0)) == 0:
                continue
            if clave == "escaneos" and not datos.get("escaneos_procesados"):
                continue
            return False
        path = rutas[clave]
        if not path.exists() or path.stat().st_size != int(reg.get("bytes", -1)):
            return False
        if revalidar and sha256(path) != reg.get("sha256"):
            return False
    return True


@dataclass
class Configuracion:
    base: Path
    staging: Path
    comunas: Path
    mascara_sha: str
    aois: tuple[AOI, ...]
    cadencia: str
    omitir_noche: bool
    sza_max: float
    trabajadores: int
    reserva_gib: float
    staging_gib: float
    cuota_productos_gib: float
    max_escaneos_por_dia: int
    limite_mbps: float | None
    execution_id: str
    satelite: str
    exclusiones: dict[str, str] | None = None


def cargar_exclusiones(path: Path) -> dict[str, str]:
    """``_control/exclusiones.json``: {clave S3: motivo} escrito a mano.

    Una fuente permanentemente corrupta bloquearía su día para siempre; la
    exclusión manual deja constancia del motivo en el manifiesto del día
    (``omitido_por_exclusion_manual``) en vez de ocultarla.
    """
    if not path.exists():
        return {}
    datos = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(datos, dict) or not all(
            isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in datos.items()):
        raise ValueError(f"{path}: se esperaba un objeto {{clave S3: motivo no vacío}}")
    return datos


def procesar_dia(s3, fecha: date, cfg: Configuracion, catalogos: CatalogoPixeles,
                 mani: Manifiesto, mani_csv: ManifiestoCSV,
                 muestra_sza: tuple[np.ndarray, np.ndarray]) -> str:
    """Descarga, recorta, publica y retira los crudos de un día. Devuelve el estado."""
    satelite = satelite_para(fecha, cfg.satelite)
    listado = listar_escaneos(s3, fecha, satelite)
    escaneos, descartados = deduplicar_escaneos(listado)
    snapshot = {
        "schema": "airpollution.goes-abi-aod.s3-listing.v1", "fecha": fecha.isoformat(),
        "bucket": BUCKETS[satelite], "prefijo": f"{PREFIJO_PRODUCTO}/{fecha:%Y}/{fecha:%j}/",
        "utc": ahora_utc(), "archivos": [asdict_escaneo(e) for e in listado],
    }
    snap_path = cfg.base / "_catalogos_s3" / cfg.execution_id / f"{fecha.isoformat()}.json"
    snapshot_sha = escribir_json_atomico(snapshot, snap_path)
    rezago = (date.today() - fecha).days < 3
    if not escaneos:
        estado = "error" if rezago else "sin_datos"
        mani.registrar({"evento": "dia_sin_fuente", "fecha": fecha.isoformat(),
                        "bucket": BUCKETS[satelite], "posible_rezago_fuente": rezago,
                        "estado": estado})
        if not rezago:
            escribir_json_atomico({
                "schema": SCHEMA_DIA, "contrato": CONTRATO, "fecha": fecha.isoformat(),
                "satelite": satelite, "bucket": BUCKETS[satelite], "estado": "sin_datos",
                "listado_s3": {"ruta": str(snap_path), "sha256": snapshot_sha},
                "execution_id": cfg.execution_id, "utc": ahora_utc(),
            }, rutas_dia(cfg.base, fecha)["manifiesto"])
        mani_csv.marcar(fecha.isoformat(), FLUJO, estado, 0,
                        sha256(rutas_dia(cfg.base, fecha)["manifiesto"]) if not rezago else "")
        return estado

    elegidos, omitidos_cadencia = seleccionar_cadencia(escaneos, cfg.cadencia)
    excluidos = []
    if cfg.exclusiones:
        excluidos = [{"key": e.key, "estado": "omitido_por_exclusion_manual",
                      "motivo": cfg.exclusiones[e.key]}
                     for e in elegidos if e.key in cfg.exclusiones]
        elegidos = [e for e in elegidos if e.key not in cfg.exclusiones]
    plan, omitidos_noche = [], []
    for e in elegidos:
        sza = sza_minimo_chile(e.medio, muestra_sza)
        if cfg.omitir_noche and sza >= cfg.sza_max + 2.0:
            omitidos_noche.append({"key": e.key, "estado": "omitido_noche_geometrica",
                                   "sza_min_chile_deg": round(sza, 2),
                                   "inicio_utc": e.inicio.isoformat()})
        else:
            plan.append((e, sza))
    limitados = []
    if cfg.max_escaneos_por_dia and len(plan) > cfg.max_escaneos_por_dia:
        limitados = [{"key": e.key, "estado": "omitido_limite_prueba"} for e, _ in plan[cfg.max_escaneos_por_dia:]]
        plan = plan[:cfg.max_escaneos_por_dia]

    carpeta_dia = cfg.staging / fecha.isoformat()
    carpeta_dia.mkdir(parents=True, exist_ok=True)
    procesados: list[dict] = []
    fallidos: list[dict] = []
    tablas: list[pd.DataFrame] = []
    filas_escaneos: list[dict] = []
    crudos: list[Path] = []
    atributos_variables: dict | None = None
    atributos_diferentes: list[str] = []
    referencia_globales: dict | None = None
    referencia_escalares: dict | None = None

    def bajar(e: Escaneo) -> Path:
        exigir_reserva(cfg.base, cfg.reserva_gib, fase="descargar", unidad=e.nombre)
        if tamano_gib(cfg.staging) + e.bytes / GIB > cfg.staging_gib:
            raise LimiteSeguro(f"staging superaría {cfg.staging_gib:.1f} GiB antes de {e.nombre}")
        return descargar_objeto(s3, e, carpeta_dia / e.nombre, cfg.limite_mbps)

    with ThreadPoolExecutor(max_workers=max(1, cfg.trabajadores)) as pool:
        futuros = {}
        pendientes = list(plan)
        ventana = max(1, cfg.trabajadores)
        # Ventana deslizante: nunca hay más de `trabajadores` descargas en vuelo.
        for e, _ in pendientes[:ventana]:
            futuros[e.key] = pool.submit(bajar, e)
        siguiente = ventana
        for e, sza_plan in pendientes:
            try:
                crudo = futuros.pop(e.key).result()
            except LimiteSeguro:
                raise
            except Exception as exc:  # noqa: BLE001
                fallidos.append({"key": e.key, "estado": "descarga_fallida",
                                 "error": f"{type(exc).__name__}: {exc}"})
                log.warning("%s: descarga fallida: %s", e.nombre, exc)
            else:
                try:
                    sha_fuente = sha256(crudo)
                    filas, resumen = recortar_escaneo(crudo, e, catalogos, muestra_sza)
                    if atributos_variables is None:
                        atributos_variables = resumen["atributos_variables"]
                    elif resumen["atributos_variables"] != atributos_variables:
                        atributos_diferentes.append(e.key)
                    if referencia_globales is None:
                        referencia_globales = resumen["atributos_globales"]
                        referencia_escalares = resumen["variables_escalares"]
                        metadatos_escaneo = {
                            "metadatos": "completos",
                            "atributos_globales": resumen["atributos_globales"],
                            "variables_escalares": resumen["variables_escalares"],
                        }
                    else:
                        metadatos_escaneo = {
                            "metadatos": "diferencias respecto del primer escaneo procesado",
                            "atributos_globales": diferencias(
                                referencia_globales, resumen["atributos_globales"]),
                            "variables_escalares": diferencias(
                                referencia_escalares, resumen["variables_escalares"]),
                        }
                    tablas.append(filas)
                    crudos.append(crudo)
                    filas_escaneos.append({
                        "scan_id": e.scan_id, "satelite": e.satelite, "modo": e.modo,
                        "inicio_utc": e.inicio, "fin_utc": e.fin,
                        "t_medio_utc": (datetime.fromisoformat(resumen["t_medio_utc"])
                                        if resumen["t_medio_utc"] else e.medio),
                        "creacion_utc": e.creacion, "archivo_fuente": e.key,
                        "bytes_fuente": e.bytes, "sha256_fuente": sha_fuente, "etag": e.etag,
                        "grid_id": resumen["grid_id"], "subpoint_lon": resumen["subpoint_lon"],
                        "lon_origen_proyeccion": resumen["proyeccion"]["longitude_of_projection_origin"],
                        "sza_min_chile_deg": resumen["sza_min_chile_deg"],
                        "n_pixeles_chile": resumen["n_pixeles_chile"],
                        "n_recuperados": resumen["n_recuperados"],
                        **{k: resumen[k] for k in ("n_dqf_0", "n_dqf_1", "n_dqf_2", "n_dqf_3", "n_dqf_otro")},
                    })
                    procesados.append({
                        "key": e.key, "estado": "procesado", "bytes_fuente": e.bytes,
                        "sha256_fuente": sha_fuente, "etag": e.etag, "modo": e.modo,
                        "inicio_utc": e.inicio.isoformat(), "fin_utc": e.fin.isoformat(),
                        "creacion_utc": e.creacion.isoformat(),
                        "sza_min_chile_deg_plan": round(sza_plan, 2),
                        **{k: v for k, v in resumen.items()
                           if k not in ("atributos_variables", "atributos_globales",
                                        "variables_escalares")},
                        **metadatos_escaneo,
                        "filas": int(len(filas)),
                    })
                except LimiteSeguro:
                    raise
                except Exception as exc:  # noqa: BLE001
                    fallidos.append({"key": e.key, "estado": "recorte_fallido",
                                     "error": f"{type(exc).__name__}: {exc}",
                                     "crudo_preservado": str(crudo)})
                    log.warning("%s: recorte fallido: %s", e.nombre, exc)
            if siguiente < len(pendientes):
                e2, _ = pendientes[siguiente]
                futuros[e2.key] = pool.submit(bajar, e2)
                siguiente += 1

    if fallidos:
        # Un día con fallas no se publica ni se limpia: se reintenta entero.
        mani.registrar({"evento": "dia_incompleto", "fecha": fecha.isoformat(),
                        "fallidos": fallidos, "procesados": len(procesados),
                        "crudos_preservados": [str(p) for p in crudos]})
        mani_csv.marcar(fecha.isoformat(), FLUJO, "error", 0, "")
        return "error"

    rutas = rutas_dia(cfg.base, fecha)
    exigir_reserva(cfg.base, cfg.reserva_gib, fase="publicar", unidad=fecha.isoformat())
    obs = (pd.concat(tablas, ignore_index=True) if tablas
           else pd.DataFrame({c: pd.Series(dtype=t) for c, t in zip(
               COLUMNAS_OBS, ("int64", "int32", "int16", "float32", "uint8",
                              "int16", "float32", "int16", "float32"), strict=True)}))
    obs = obs.sort_values(["scan_id", "pixel_id"], kind="stable").reset_index(drop=True)
    salidas = {}
    if not obs.empty:
        n_obs, sha_obs = escribir_parquet_atomico(obs, rutas["obs"], COLUMNAS_OBS, _validar_obs)
        salidas["observaciones"] = {"ruta": str(rutas["obs"]), "filas": int(n_obs),
                                    "bytes": rutas["obs"].stat().st_size, "sha256": sha_obs}
    else:
        rutas["obs"].unlink(missing_ok=True)
    if filas_escaneos:
        esc = pd.DataFrame(filas_escaneos).loc[:, list(COLUMNAS_ESCANEOS)]
        for col in ("inicio_utc", "fin_utc", "t_medio_utc", "creacion_utc"):
            esc[col] = pd.to_datetime(esc[col], utc=True).dt.as_unit("ms")
        esc = esc.sort_values("scan_id").reset_index(drop=True)
        n_esc, sha_esc = escribir_parquet_atomico(esc, rutas["escaneos"], COLUMNAS_ESCANEOS,
                                                  _validar_escaneos)
        salidas["catalogo_escaneos"] = {"ruta": str(rutas["escaneos"]), "filas": int(n_esc),
                                        "bytes": rutas["escaneos"].stat().st_size, "sha256": sha_esc}
    else:
        rutas["escaneos"].unlink(missing_ok=True)

    manifiesto_dia = {
        "schema": SCHEMA_DIA, "contrato": CONTRATO, "producto": PRODUCTO,
        "fecha": fecha.isoformat(), "satelite": satelite, "bucket": BUCKETS[satelite],
        "fuente": {"prefijo": snapshot["prefijo"], "documentacion": DOCUMENTACION,
                   "autenticacion": "ninguna; S3 anónimo"},
        "estado": "ok", "posible_rezago_fuente": rezago,
        "cadencia": cfg.cadencia,
        "criterio_noche": (f"omitido sin descargar si SZA mínimo en la malla de las AOI "
                           f"≥ {cfg.sza_max:.0f}° + 2°" if cfg.omitir_noche else "sin omisión"),
        "mascara": str(cfg.comunas), "mascara_sha256": cfg.mascara_sha,
        "codigo_sha256": PROCESSOR_SHA256, "execution_id": cfg.execution_id,
        "listado_s3": {"ruta": str(snap_path), "sha256": snapshot_sha,
                       "archivos_listados": len(listado)},
        "huecos_fuente_esperados": huecos_esperados(escaneos, fecha),
        "escaneos_procesados": procesados,
        "escaneos_omitidos": (omitidos_noche + omitidos_cadencia + limitados + descartados
                              + excluidos),
        "atributos_variables": atributos_variables,
        "escaneos_con_atributos_distintos": atributos_diferentes,
        "filas_observaciones": int(len(obs)),
        "salidas": salidas,
        "semantica": {
            "tiempo": "inicio/fin del escaneo (time_bounds) y t medio; sin hora por píxel",
            "filas": "sólo celdas con AOD ≠ _FillValue; la ausencia se cuenta por DQF en catalogo_escaneos",
            "valores": "empaquetados nativos (*_i16) y decodificados con scale_factor/add_offset",
            "sin_promedio_sin_interpolacion": True,
        },
        "utc": ahora_utc(),
    }
    sha_mani = escribir_json_atomico(manifiesto_dia, rutas["manifiesto"])
    # WAL durable antes de retirar los crudos validados.
    mani.registrar({
        "evento": "dia_validado_pre_borrado", "fecha": fecha.isoformat(),
        "manifiesto_dia": str(rutas["manifiesto"]), "sha256_manifiesto": sha_mani,
        "salidas": salidas, "crudos": [{"ruta": str(p), "bytes": p.stat().st_size} for p in crudos],
        "crudo_eliminado": False,
    })
    for p in crudos:
        p.unlink()
    for p in carpeta_dia.glob("*.part"):
        p.unlink(missing_ok=True)
    if not any(carpeta_dia.iterdir()):
        carpeta_dia.rmdir()
    mani.registrar({"evento": "crudo_eliminado_post_validacion", "fecha": fecha.isoformat(),
                    "crudos": len(crudos), "crudo_eliminado": True,
                    "wal_evento": "dia_validado_pre_borrado"})
    mani_csv.marcar(fecha.isoformat(), FLUJO, "ok", int(len(obs)), sha_mani)
    log.info("%s: %d escaneos, %d omitidos (noche %d), %s filas",
             fecha.isoformat(), len(procesados),
             len(omitidos_noche) + len(omitidos_cadencia) + len(limitados),
             len(omitidos_noche), f"{len(obs):,}")
    return "ok"


def asdict_escaneo(e: Escaneo) -> dict:
    d = asdict(e)
    for k in ("inicio", "fin", "creacion"):
        d[k] = d[k].isoformat()
    return d


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _plan(args, aois) -> dict:
    return {
        "producto": PRODUCTO, "contrato": CONTRATO,
        "fuente": "NOAA NODD GOES-East ABI L2 AOD Full Disk (ABI-L2-AODF)",
        "buckets": BUCKETS, "transicion_goes19": TRANSICION_G19.isoformat(),
        "autenticacion": "ninguna; S3 anónimo",
        "rango": [args.desde, args.hasta], "satelite": args.satelite,
        "cadencia": args.cadencia,
        "resolucion": "grilla fija GOES-R 2 km al nadir; ~2,2–4,1 km sobre Chile según ángulo de visión",
        "tiempo": "cada escaneo (10 min modo 6; 15 min modo 3); sin hora por píxel",
        "noche": (f"omitida sin descargar si SZA ≥ {args.sza_max:.0f}° + 2° en toda la malla de AOI"
                  if args.omitir_noche else "no se omite"),
        "variables": list(VARIABLES_OBS),
        "qa": "DQF nativo conservado; sin filtro destructivo; celdas sin recuperación contadas",
        "aois": [asdict(a) for a in aois],
        "reserva_gib": args.reserva_gib, "staging_gib": args.staging_gib,
        "cuota_productos_gib": args.cuota_productos_gib,
        "estimacion_disco": ("cadencia nativa ≈ 5–18 GiB/año; horaria ≈ 1–3 GiB/año; "
                             "el techo corresponde a 40 % de celdas con recuperación en "
                             "70 escaneos diurnos (depende de nubes y superficie oscura)"),
        "dry_run_sin_red_y_sin_escritura": True,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--desde", default=FECHA_INICIO_GOES_EAST.isoformat())
    ap.add_argument("--hasta", default=(date.today() - timedelta(days=2)).isoformat(),
                    help="por defecto anteayer: NODD publica con rezago de horas")
    ap.add_argument("--satelite", choices=("auto", "G16", "G19"), default="auto",
                    help="auto: G16 antes del 2025-04-07 y G19 desde esa fecha")
    ap.add_argument("--cadencia", choices=tuple(CADENCIAS), default="nativa",
                    help="nativa (10/15 min), 30min u horaria (minuto 00); sin sustituir faltantes")
    ap.add_argument("--omitir-noche", action=argparse.BooleanOptionalAction, default=True,
                    help="no descargar escaneos con todo Chile bajo el horizonte")
    ap.add_argument("--sza-max", type=float, default=90.0,
                    help="ángulo cenital solar máximo con recuperación posible (NOAA: 90°)")
    ap.add_argument("--trabajadores", type=int, choices=(1, 2, 3, 4), default=2)
    ap.add_argument("--reserva-gib", type=float,
                    default=float(os.environ.get("MIN_GB_LIBRES", "100")))
    ap.add_argument("--min-gb-libres", dest="reserva_gib", type=float,
                    default=argparse.SUPPRESS,
                    help="alias de --reserva-gib (compatibilidad con los runners)")
    ap.add_argument("--staging-gib", type=float, default=12.0)
    ap.add_argument("--cuota-productos-gib", type=float, default=60.0,
                    help="límite operativo del tamaño publicado; pausa con código 75")
    ap.add_argument("--max-escaneos-por-dia", type=int, default=0,
                    help="sólo para prueba real; no usar en un histórico completo")
    ap.add_argument("--comunas", type=Path, default=DATA / "comunas.shp")
    ap.add_argument("--aoi", default="todos")
    ap.add_argument("--enlaces", action="store_true",
                    help="publica además los enlaces píxel↔comuna (huella exacta) y "
                         "píxel↔estación SINCA; tarda decenas de minutos por grilla")
    ap.add_argument("--volume-uuid", default=VOLUME_UUID)
    ap.add_argument("--revalidar", action="store_true",
                    help="vuelve a hashear las salidas de días ya publicados")
    ap.add_argument("--listar", action="store_true", help="lista el primer día y termina")
    ap.add_argument("--dry-run", action="store_true", help="muestra el plan sin red ni escritura")
    args = ap.parse_args(argv)
    load_env()
    try:
        # Los runners parten en 2000-01-01; la fuente aplica su fecha nativa.
        if date.fromisoformat(args.desde) < FECHA_INICIO_GOES_EAST:
            log.info("--desde %s anterior a GOES-East operativo; se usa %s",
                     args.desde, FECHA_INICIO_GOES_EAST.isoformat())
            args.desde = FECHA_INICIO_GOES_EAST.isoformat()
        fechas = list(fechas_inclusivas(args.desde, args.hasta))
        aois = seleccionar(args.aoi, args.comunas if args.comunas.exists() else None)
    except ValueError as exc:
        ap.error(str(exc))
    if len(aois) != 5:
        ap.error("la descarga reproducible exige las cinco AOI de Chile")
    if args.dry_run:
        print(json.dumps(_plan(args, aois), ensure_ascii=False, indent=2))
        return 0
    if not args.comunas.exists():
        ap.error(f"no existe {args.comunas}")
    if args.listar:
        s3 = cliente_s3()
        for e in listar_escaneos(s3, fechas[0], satelite_para(fechas[0], args.satelite)):
            print(f"{e.key}  {e.bytes / 2**20:6.1f} MB  {e.modo}")
        return 0
    limite = os.environ.get("LIMITE_MBPS")
    limite_mbps = float(limite) if limite else None

    base = ensure_dir(CONTAMINANTES / PRODUCTO)
    try:
        volumen = verificar_volumen(base, args.volume_uuid)
    except LimiteSeguro as exc:
        log.error("%s", exc)
        return 75
    mascara_sha = sha256_conjunto_shapefile(args.comunas)
    with BloqueoProceso(base / "_descarga.lock"):
        mani = Manifiesto(base / "_manifiestos", PRODUCTO, {
            **_plan(args, aois), "volumen": volumen,
            "mascara_sha256": mascara_sha, "unidades_administrativas": resumen_mascara(args.comunas),
            "codigo_sha256": PROCESSOR_SHA256, "limite_mbps": limite_mbps,
        })
        execution_id = mani.execution_id
        exclusiones = cargar_exclusiones(base / "_control" / "exclusiones.json")
        if exclusiones:
            mani.registrar({"evento": "exclusiones_manuales_cargadas", "n": len(exclusiones),
                            "claves": sorted(exclusiones)})
        cfg = Configuracion(
            base=base, staging=base / "_staging", comunas=args.comunas, mascara_sha=mascara_sha,
            aois=aois, cadencia=args.cadencia, omitir_noche=args.omitir_noche,
            sza_max=args.sza_max, trabajadores=args.trabajadores,
            reserva_gib=args.reserva_gib, staging_gib=args.staging_gib,
            cuota_productos_gib=args.cuota_productos_gib,
            max_escaneos_por_dia=args.max_escaneos_por_dia,
            limite_mbps=limite_mbps, execution_id=execution_id, satelite=args.satelite,
            exclusiones=exclusiones,
        )
        mani_csv = ManifiestoCSV(base / "manifest_escaneos.csv")
        catalogos = CatalogoPixeles(base, args.comunas, aois, mascara_sha, mani,
                                    enlaces=args.enlaces)
        muestra_sza = puntos_muestra_chile(aois)
        s3 = cliente_s3()
        control = base / "_control" / "avance.json"
        estados = {"ok": 0, "sin_datos": 0, "error": 0, "omitidos": 0}
        codigo = 0
        try:
            exigir_reserva(base, args.reserva_gib, fase="iniciar", unidad=PRODUCTO)
            for fecha in fechas:
                registro = mani_csv.obtener(fecha.isoformat(), FLUJO)
                if registro is not None and registro.estado in ("ok", "sin_datos") and \
                        dia_publicado_valido(base, fecha, registro, revalidar=args.revalidar):
                    estados["omitidos"] += 1
                    continue
                usado = tamano_gib(base / "observaciones", base / "catalogo_escaneos",
                                   base / "manifiestos_escaneos")
                if usado > args.cuota_productos_gib:
                    raise LimiteSeguro(f"productos publicados {usado:.1f} GiB superan la cuota "
                                       f"{args.cuota_productos_gib:.1f} GiB")
                estado = procesar_dia(s3, fecha, cfg, catalogos, mani, mani_csv, muestra_sza)
                estados[estado] += 1
                escribir_json_atomico({"execution_id": execution_id, "ultimo_dia": fecha.isoformat(),
                                       "estado": estado, "conteos": estados, "utc": ahora_utc()},
                                      control)
            escribir_json_atomico({"execution_id": execution_id, "estado": "recorrido_completo",
                                   "rango": [fechas[0].isoformat(), fechas[-1].isoformat()],
                                   "conteos": estados, "utc": ahora_utc()}, control)
        except LimiteSeguro as exc:
            mani.registrar({"evento": "pausado_limite_seguro", "motivo": str(exc)})
            escribir_json_atomico({"execution_id": execution_id, "estado": "pausado_limite_seguro",
                                   "motivo": str(exc), "conteos": estados, "utc": ahora_utc()}, control)
            log.error("Pausa segura: %s", exc)
            codigo = 75
        except KeyboardInterrupt:
            mani.registrar({"evento": "interrumpido", "conteos": estados})
            codigo = 130
        finally:
            mani.terminar("completo" if codigo == 0 and not estados["error"] else
                          ("pausado" if codigo == 75 else "con_fallos"), **estados)
    if estados["error"] and codigo == 0:
        return 1
    return codigo


if __name__ == "__main__":
    sys.exit(main())
