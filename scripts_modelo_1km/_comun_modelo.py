"""Utilidades compartidas del modelo 1 km × hora (PM2.5 y NO2).

Rutas, grilla 0,01° alineada con ACAG, lectores de cada producto en su
formato nativo (sin promediar ni interpolar en la ingesta), convención
temporal y escritura atómica. Todo lo que aquí se decide queda documentado
en ``scripts_modelo_1km/README.md``.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
SCRIPTS_PIPELINE = RAIZ / "scripts_pipeline"
import sys  # noqa: E402

sys.path.insert(0, str(SCRIPTS_PIPELINE))
from _common import CONTAMINANTES as CONT, DATA  # noqa: E402
from _manifiesto_satelital import sha256  # noqa: E402
from _satellite_streaming import escribir_json_atomico  # noqa: E402

log = logging.getLogger("modelo_1km")
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
for _ruidoso in ("botocore", "boto3", "urllib3", "rasterio", "pyogrio", "fiona"):
    logging.getLogger(_ruidoso).setLevel(logging.WARNING)


def rellenar_por_vecino(lat, lon, valores: np.ndarray, max_km: float = 5.0) -> tuple[np.ndarray, np.ndarray]:
    """Rellena NaN con el valor de la celda válida más cercana (≤ max_km).

    Devuelve (valores_rellenos, bandera_relleno). Sirve para celdas costeras
    cuyo centro cae fuera de toda comuna (cod_comuna = −1) y no tienen
    atributo comunal propio.
    """
    from scipy.spatial import cKDTree

    valores = np.asarray(valores, dtype="float64").copy()
    faltan = ~np.isfinite(valores)
    bandera = np.zeros(valores.shape, dtype=bool)
    if not faltan.any() or faltan.all():
        return valores, bandera
    la, lo = np.radians(np.asarray(lat, float)), np.radians(np.asarray(lon, float))
    xyz = np.c_[np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)]
    arbol = cKDTree(xyz[~faltan])
    d, i = arbol.query(xyz[faltan])
    km = 2.0 * 6371.0 * np.arcsin(np.clip(d / 2.0, 0, 1))
    origen = np.flatnonzero(~faltan)[i]
    destino = np.flatnonzero(faltan)
    ok = km <= max_km
    valores[destino[ok]] = valores[origen[ok]]
    bandera[destino[ok]] = True
    return valores, bandera

DERIVED_ROOT = Path(os.environ.get("AIR_POLLUTION_DERIVED_ROOT") or DATA.parent / "derived").resolve()
SINCA_DERIVADO = DERIVED_ROOT / "modelado" / "SINCA" / "v1"          # insumo: lo publica el pipeline de datos
# El disco externo queda para los datos crudos: **nada de lo que genera este modelo** (grilla, estáticas,
# paneles, modelos, predicciones de validación ni superficies) se escribe allí. Todo va al disco interno,
# fuera del repositorio sincronizado, salvo que una variable de entorno indique otra raíz.
LOCAL_ROOT = Path(os.environ.get("AIR_POLLUTION_LOCAL_ROOT")
                  or Path.home() / "Asesorias_Data_local" / "AirPollution").expanduser().resolve()
MODELO_ROOT = Path(os.environ.get("AIR_POLLUTION_MODELO_1KM_ROOT") or LOCAL_ROOT / "modelado_1km").expanduser().resolve()
SUPERFICIES_ROOT = Path(os.environ.get("AIR_POLLUTION_SUPERFICIES_ROOT") or MODELO_ROOT).expanduser().resolve()
CONTRATO = "modelo-1km-horario-v1"
CONTAMINANTES = ("pm25", "no2")
UNIDADES = {"pm25": "µg/m³", "no2": "ppb"}
RANGO_VALIDO = {"pm25": (0.0, 1500.0), "no2": (0.0, 1000.0)}
# Reloj de monitoreo: UTC−4 fijo (D.S. 61/2008; R.E. 1449/2023). La etiqueta
# horaria se interpreta como fin del intervalo (R.E. 1449) salvo configuración.
OFFSET_UTC_H = 4
ETIQUETA_SINCA = os.environ.get("MODELO_1KM_ETIQUETA_SINCA", "fin")
MACROZONA_REGION = {15: "norte_grande", 1: "norte_grande", 2: "norte_grande",
                    3: "norte_chico", 4: "norte_chico",
                    5: "centro", 13: "centro", 6: "centro", 7: "centro",
                    8: "sur", 16: "sur", 9: "sur", 14: "sur", 10: "sur",
                    11: "austral", 12: "austral", 0: "sin_region"}
MACROZONA_CODIGO = {"norte_grande": 0, "norte_chico": 1, "centro": 2, "sur": 3,
                    "austral": 4, "sin_region": 5, "insular": 6}
ID_INSULAR_BASE = 900_000_000  # celdas generadas fuera del dominio ACAG (Rapa Nui, Sala y Gómez)
RES = 0.01


# ---------------------------------------------------------------------------
# Tiempo
# ---------------------------------------------------------------------------
def sinca_local_a_bin_utc(ts_local: pd.Series) -> pd.Series:
    """Etiqueta local SINCA → inicio del intervalo horario en UTC (naive).

    Con etiqueta al fin del intervalo (R.E. 1449) la hora 18 local cubre
    17:01–18:00; el bin horario que se cruza con reanálisis es 17:00 local,
    es decir 21:00 UTC. Con ``MODELO_1KM_ETIQUETA_SINCA=inicio`` no se resta.
    """
    ts = pd.to_datetime(ts_local)
    desplazamiento = OFFSET_UTC_H - (1 if ETIQUETA_SINCA == "fin" else 0)
    return ts + pd.Timedelta(hours=desplazamiento)


def bin_utc_a_local(ts_utc: pd.Series) -> pd.Series:
    return pd.to_datetime(ts_utc) - pd.Timedelta(hours=OFFSET_UTC_H)


def fechas(desde: str, hasta: str) -> list[date]:
    ini, fin = date.fromisoformat(desde), date.fromisoformat(hasta)
    if ini > fin:
        raise ValueError(f"rango vacío {desde} > {hasta}")
    return [ini + timedelta(days=k) for k in range((fin - ini).days + 1)]


def meses(desde: str, hasta: str) -> list[str]:
    out = []
    for f in fechas(desde, hasta):
        m = f.strftime("%Y%m")
        if not out or out[-1] != m:
            out.append(m)
    return out


# ---------------------------------------------------------------------------
# Escritura atómica
# ---------------------------------------------------------------------------
def publicar_parquet(df: pd.DataFrame, path: Path) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    part.unlink(missing_ok=True)
    try:
        df.to_parquet(part, index=False, compression="zstd")
        chk = pd.read_parquet(part, columns=[df.columns[0]])
        if len(chk) != len(df):
            raise ValueError(f"{path}: reapertura Parquet no coincide")
        with part.open("rb") as fh:
            os.fsync(fh.fileno())
        os.replace(part, path)
    finally:
        part.unlink(missing_ok=True)
    return sha256(path)


def publicar_json(datos: dict, path: Path) -> str:
    return escribir_json_atomico(datos, Path(path))


def hash_codigo() -> str:
    """Hash conjunto de los módulos ``scripts_modelo_1km/*.py`` y del documento
    ``docs/modelo_1km_horario.qmd`` (donde vive el modelo), si existe."""
    h = hashlib.sha256()
    archivos = sorted(Path(__file__).resolve().parent.glob("*.py"))
    qmd = RAIZ / "docs" / "modelo_1km_horario.qmd"
    if qmd.exists():
        archivos.append(qmd)
    for p in archivos:
        h.update(p.name.encode()); h.update(bytes.fromhex(sha256(p)))
    return h.hexdigest()[:16]


# ---------------------------------------------------------------------------
# Superficies diarias: contrato NetCDF (hora × celda, int16 empaquetado)
# ---------------------------------------------------------------------------
ESCALA_SUPERFICIE = {"pm25": 0.1, "no2": 0.01}     # unidad física por cuenta int16
FILL_SUPERFICIE = np.int16(-32768)


# Ámbitos de la grilla, por código numérico de región de ``celdas.parquet``. «biobio» incluye Ñuble
# (16): SINCA sigue etiquetando como RVIII a estaciones que hoy están en comunas de Ñuble, y el foco
# de leña de Chillán es justamente el que interesa. Definidos aquí para que el lanzador, el agregador
# de exposición y el documento no tengan cada uno su propia copia.
AMBITOS_GRILLA: dict[str, tuple[int, ...] | None] = {"nacional": None, "rm": (13,), "biobio": (8, 16)}


def celdas_de_ambito(celdas: pd.DataFrame, ambito: str) -> pd.DataFrame:
    cods = AMBITOS_GRILLA[ambito]
    return celdas if cods is None else celdas[celdas["codregion"].isin(cods)].reset_index(drop=True)


def carpeta_ambito(base: Path, prefijo: str, sufijo: str = "", ambito: str = "nacional") -> Path:
    """Carpeta de salida de un ámbito.

    Cada ámbito escribe en la suya porque un día de la RM y un día nacional tendrían **la misma
    ruta** (``ruta_superficie_dia`` no distingue el número de celdas). Separándolas, producir
    primero una región no pisa ni contamina la serie nacional, y la nacional no espera a nadie.
    """
    return Path(base) / (f"{prefijo}{sufijo}" if ambito == "nacional" else f"{prefijo}{sufijo}_{ambito}")


def ruta_superficie_dia(base: Path, pol: str, fecha: date) -> tuple[Path, Path]:
    carpeta = Path(base) / pol / f"year={fecha:%Y}" / f"month={fecha:%m}"
    return carpeta / f"{pol}_1km_{fecha:%Y%m%d}.nc", carpeta / f"{pol}_1km_{fecha:%Y%m%d}.json"


def escribir_superficie_dia(path: Path, pol: str, celdas: np.ndarray, ts_utc: np.ndarray,
                            valores: np.ndarray, atributos: dict) -> None:
    """NetCDF diario ``hora × celda`` con ``<pol>`` en int16 escalado (escritura atómica).

    ``valores`` es float (24 × n) en la unidad física; NaN → ``FILL_SUPERFICIE``.
    """
    import netCDF4

    path = Path(path)
    tmp = path.with_suffix(".nc.part")
    tmp.unlink(missing_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    escala = ESCALA_SUPERFICIE[pol]
    empaquetado = np.where(np.isfinite(valores), np.round(np.clip(valores, 0, 32000 * escala) / escala),
                           FILL_SUPERFICIE)
    with netCDF4.Dataset(tmp, "w", format="NETCDF4") as nc:
        nc.createDimension("hora", valores.shape[0])
        nc.createDimension("celda", valores.shape[1])
        for k, v in atributos.items():
            nc.setncattr(k, v if not isinstance(v, (list, dict)) else json.dumps(v, ensure_ascii=False))
        vt = nc.createVariable("ts_utc", "i8", ("hora",))
        vt.units = "seconds since 1970-01-01 00:00:00"
        vt.long_name = "inicio del bin horario UTC"
        vt[:] = np.asarray(ts_utc).astype("datetime64[s]").astype("int64")
        vc = nc.createVariable("celda", "i8", ("celda",), zlib=True, complevel=4)
        vc.long_name = "identificador de celda 0,01° (pixel_id ACAG o 900000000+k)"
        vc[:] = celdas
        v = nc.createVariable(pol, "i2", ("hora", "celda"), zlib=True, complevel=4, shuffle=True,
                              chunksizes=(1, valores.shape[1]), fill_value=FILL_SUPERFICIE)
        v.scale_factor = escala
        v.add_offset = 0.0
        v.units = UNIDADES[pol]
        v.long_name = f"{pol} estimado en superficie (modelo LightGBM 1 km × hora)"
        v.set_auto_maskandscale(False)
        v[:] = empaquetado.astype("int16")
    os.replace(tmp, path)


def leer_superficie_dia(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Devuelve (ts_utc datetime64[s], celdas int64, valores float32 con NaN)."""
    import netCDF4

    with netCDF4.Dataset(path) as nc:
        pol = [v for v in nc.variables if v not in ("ts_utc", "celda")][0]
        var = nc.variables[pol]
        var.set_auto_maskandscale(False)
        crudo = var[:].astype("int16")
        escala = float(var.scale_factor)
        ts = nc.variables["ts_utc"][:].astype("int64").astype("datetime64[s]")
        celdas = nc.variables["celda"][:].astype("int64")
    valores = np.where(crudo == FILL_SUPERFICIE, np.nan, crudo.astype("float32") * escala).astype("float32")
    return ts, celdas, valores


# ---------------------------------------------------------------------------
# Grilla 0,01° (alineada con ACAG V6GL03: centros en k·0,01 + 0,005)
# ---------------------------------------------------------------------------
GRILLA_DIR = MODELO_ROOT / "grilla_1km"
CELDAS_PATH = GRILLA_DIR / "celdas.parquet"
ENLACES_PATH = GRILLA_DIR / "enlaces_productos.parquet"
ESTATICAS_PATH = GRILLA_DIR / "estaticas.parquet"
LULC_PATH = GRILLA_DIR / "estaticas_lulc.parquet"


def cargar_celdas() -> pd.DataFrame:
    if not CELDAS_PATH.exists():
        raise SystemExit(f"Falta la grilla {CELDAS_PATH}; ejecuta construir_grilla.py")
    return pd.read_parquet(CELDAS_PATH)


def cargar_enlaces() -> pd.DataFrame:
    if not ENLACES_PATH.exists():
        raise SystemExit(f"Faltan los enlaces {ENLACES_PATH}; ejecuta construir_grilla.py")
    return pd.read_parquet(ENLACES_PATH)


def celda_de_lonlat(lon, lat, celdas: pd.DataFrame) -> np.ndarray:
    """Celda 0,01° que contiene cada punto (−1 si no está en la grilla)."""
    from scipy.spatial import cKDTree

    arbol = cKDTree(np.c_[celdas["lon"].to_numpy(), celdas["lat"].to_numpy()])
    d, i = arbol.query(np.c_[np.asarray(lon, float), np.asarray(lat, float)])
    fuera = (np.abs(celdas["lon"].to_numpy()[i] - lon) > RES / 2 + 1e-9) | \
            (np.abs(celdas["lat"].to_numpy()[i] - lat) > RES / 2 + 1e-9)
    out = celdas["celda"].to_numpy()[i].astype("int64")
    out[fuera] = -1
    return out


# ---------------------------------------------------------------------------
# Lectores nativos
# ---------------------------------------------------------------------------
def leer_catalogo(producto: str) -> pd.DataFrame:
    rutas = {
        "era5land": CONT / "ERA5Land" / "chile_nativo_01deg" / "catalogo_pixeles.parquet",
        "era5blh": CONT / "ERA5" / "chile_nativo_025deg" / "catalogo_pixeles.parquet",
        "merra2": CONT / "MERRA2_meteo" / "chile_nativo_05x0625deg" / "catalogo_pixeles.parquet",
        "cams": CONT / "CAMS_EAC4" / "chile_nativo_075deg" / "catalogo_pixeles.parquet",
    }
    df = pd.read_parquet(rutas[producto])
    return df.rename(columns={"latitude": "lat", "longitude": "lon"})[["pixel_id", "lat", "lon"]]


def ruta_mensual(producto: str, yyyymm: str) -> Path:
    return {
        "era5land": CONT / "ERA5Land" / "chile_nativo_01deg" / "mensual" / f"era5land_{yyyymm}_chile_pixeles.nc",
        "era5blh": CONT / "ERA5" / "chile_nativo_025deg" / "mensual" / f"era5_blh_{yyyymm}_chile_pixeles.nc",
        "merra2": CONT / "MERRA2_meteo" / "chile_nativo_05x0625deg" / "mensual" / f"merra2_meteo_{yyyymm}_chile_pixeles.nc",
        "cams": CONT / "CAMS_EAC4" / "chile_nativo_075deg" / "mensual" / f"cams_eac4_{yyyymm}_chile_pixeles.nc",
        "geoscf": CONT / "GEOS_CF" / "raw_chile" / f"geoscf_{yyyymm}.nc",
    }[producto]


MESES_REFERENCIA_VALIDEZ = ("200001", "201307", "202507")   # inicio, mitad y un mes reciente cerrado
VARIABLE_VALIDEZ = {"era5land": "t2m", "era5blh": "blh", "merra2": "t2m", "cams": "pm25"}


def pixeles_validos(producto: str) -> np.ndarray | None:
    """``pixel_id`` que traen algún dato finito en **todos** los meses de referencia disponibles.

    ERA5-Land no tiene valores sobre el mar: ~16 % de sus píxeles del recorte de Chile son NaN
    constante, y una celda costera enlazada a uno de ellos se quedaría sin meteorología de superficie.
    Devuelve ``None`` si no hay ningún mes de referencia en disco (no se puede decidir).
    """
    var = VARIABLE_VALIDEZ.get(producto)
    if var is None:
        return None          # sin variable de referencia no se filtra: GEOS-CF, por ejemplo, es una
                             # grilla completa y no tiene píxeles de mar en blanco
    validos = None
    for yyyymm in MESES_REFERENCIA_VALIDEZ:
        m = leer_mes_geoscf(yyyymm) if producto == "geoscf" else leer_mes_nativo(producto, yyyymm)
        if m is None or var not in m.datos:
            continue
        con_dato = set(m.pixel_id[np.isfinite(m.datos[var]).any(axis=0)].tolist())
        validos = con_dato if validos is None else validos & con_dato
    return None if validos is None else np.array(sorted(validos), dtype="int64")


VARIABLES_MENSUALES = {
    "era5land": ("t2m", "d2m", "sp", "u10", "v10", "tp"),
    "era5blh": ("blh",),
    "merra2": ("t2m", "qv2m", "rh2m", "u10m", "v10m", "ps", "pblh", "aod_m2", "pm25_m2"),
    "cams": ("no2", "pm25", "pm10", "o3", "co"),
}


RELLENO_MINIMO = 1e14   # GEOS y MERRA-2 rellenan con 1e15 y no siempre lo declaran como _FillValue


def sin_relleno(arr: np.ndarray) -> np.ndarray:
    """float32 con NaN donde el archivo trae enmascarado, no finito o el relleno 1e15 sin declarar."""
    arr = np.ma.filled(arr, np.nan).astype("float32")
    arr[~np.isfinite(arr) | (np.abs(arr) >= RELLENO_MINIMO)] = np.nan
    return arr


@dataclass
class MesNativo:
    """Un mes ``time × pixel`` en memoria, con índice de tiempo horario UTC."""
    producto: str
    tiempos: np.ndarray            # datetime64[ns] naive UTC, forma (T,)
    pixel_id: np.ndarray           # (P,)
    datos: dict[str, np.ndarray]   # var → (T, P) float32
    lat: np.ndarray | None = None
    lon: np.ndarray | None = None

    def indice_pixel(self, pixel_ids: np.ndarray) -> np.ndarray:
        if not hasattr(self, "_orden"):
            self._orden = np.argsort(self.pixel_id)
            self._ordenados = self.pixel_id[self._orden]
        pos = np.searchsorted(self._ordenados, pixel_ids)
        pos = np.clip(pos, 0, len(self._orden) - 1)
        idx = self._orden[pos]
        ok = self.pixel_id[idx] == pixel_ids
        return np.where(ok, idx, -1)

    def indice_tiempo(self, ts: np.ndarray, paso_h: int = 1) -> np.ndarray:
        """Posición del bin horario UTC (redondeo hacia el paso anterior)."""
        t0 = self.tiempos[0]
        delta = (ts.astype("datetime64[ns]") - t0) / np.timedelta64(paso_h, "h")
        idx = np.floor(delta).astype("int64")
        idx[(idx < 0) | (idx >= len(self.tiempos))] = -1
        return idx

    def extraer(self, var: str, it: np.ndarray, ip: np.ndarray) -> np.ndarray:
        out = np.full(len(it), np.nan, dtype="float32")
        ok = (it >= 0) & (ip >= 0)
        out[ok] = self.datos[var][it[ok], ip[ok]]
        return out


def leer_mes_nativo(producto: str, yyyymm: str) -> MesNativo | None:
    """Lee un NetCDF mensual ``time × pixel`` (ERA5-Land, BLH, MERRA-2, CAMS)."""
    import netCDF4

    path = ruta_mensual(producto, yyyymm)
    if not path.exists():
        return None
    with netCDF4.Dataset(path) as nc:
        t = nc["time"]
        tiempos = netCDF4.num2date(t[:], t.units, getattr(t, "calendar", "standard"),
                                   only_use_cftime_datetimes=False, only_use_python_datetimes=True)
        tiempos = np.array([np.datetime64(x.replace(tzinfo=None)) for x in tiempos], dtype="datetime64[ns]")
        pixel = np.asarray(nc["pixel_id"][:], dtype="int64")
        datos = {}
        for var in VARIABLES_MENSUALES[producto]:
            if var in nc.variables:
                datos[var] = sin_relleno(nc[var][:])
        lat = np.asarray(nc["latitude"][:], float) if "latitude" in nc.variables else None
        lon = np.asarray(nc["longitude"][:], float) if "longitude" in nc.variables else None
    if producto == "era5land" and "tp" in datos:
        # Acumulado desde 00 UTC: precipitación horaria = diferencia de acumulados,
        # salvo en 01 UTC, donde el acumulado es el primero del ciclo diario.
        tp = datos["tp"]
        horas = pd.DatetimeIndex(tiempos).hour.to_numpy()
        dif = np.full_like(tp, np.nan)
        dif[1:] = tp[1:] - tp[:-1]
        dif[horas == 1] = tp[horas == 1]
        datos["tp_1h_mm"] = (dif * 1000.0).astype("float32")
    # MERRA-2, CAMS y GEOS-CF etiquetan HH:30 (promedios); ERA5 etiqueta HH:00.
    # Se alinea todo al inicio del bin horario UTC.
    tiempos = np.asarray(tiempos, dtype="datetime64[ns]")
    minutos = pd.DatetimeIndex(tiempos).minute.to_numpy()
    if np.all(minutos == 30):
        tiempos = tiempos - np.timedelta64(30, "m")
    return MesNativo(producto, tiempos, pixel, datos, lat, lon)


def leer_mes_geoscf(yyyymm: str) -> MesNativo | None:
    """GEOS-CF rectángulo lat × lon 0,25°; pixel_id = ilat * 1000 + ilon."""
    import netCDF4

    path = ruta_mensual("geoscf", yyyymm)
    if not path.exists():
        return None
    with netCDF4.Dataset(path) as nc:
        t = nc["time"]
        tiempos = netCDF4.num2date(t[:], t.units, getattr(t, "calendar", "standard"),
                                   only_use_cftime_datetimes=False, only_use_python_datetimes=True)
        tiempos = np.array([np.datetime64(x.replace(tzinfo=None)) for x in tiempos], dtype="datetime64[ns]")
        lat = np.asarray(nc["lat"][:], float)
        lon = np.asarray(nc["lon"][:], float)
        datos = {}
        for var, nombre in (("no2", "no2"), ("o3", "o3"), ("co", "co"), ("so2", "so2"),
                            ("pm25_rh35_gcc", "pm25")):
            if var in nc.variables:
                arr = sin_relleno(nc[var][:])
                arr = arr.reshape(arr.shape[0], -1) if arr.ndim == 3 else arr[:, 0, :, :].reshape(arr.shape[0], -1)
                if nombre in ("no2", "o3", "co", "so2"):
                    arr = arr * 1e9  # mol/mol → ppb
                datos[nombre] = arr
    ilat, ilon = np.meshgrid(np.arange(lat.size), np.arange(lon.size), indexing="ij")
    pixel = (ilat.ravel() * 1000 + ilon.ravel()).astype("int64")
    tiempos = tiempos - np.timedelta64(30, "m")
    lat2, lon2 = np.meshgrid(lat, lon, indexing="ij")
    return MesNativo("geoscf", tiempos, pixel, datos, lat2.ravel(), lon2.ravel())


def catalogo_geoscf() -> pd.DataFrame | None:
    """Catálogo de nodos GEOS-CF a partir de cualquier archivo mensual disponible."""
    import netCDF4

    carpeta = CONT / "GEOS_CF" / "raw_chile"
    archivos = sorted(carpeta.glob("geoscf_*.nc"))
    if not archivos:
        return None
    with netCDF4.Dataset(archivos[-1]) as nc:
        lat = np.asarray(nc["lat"][:], float)
        lon = np.asarray(nc["lon"][:], float)
    ilat, ilon = np.meshgrid(np.arange(lat.size), np.arange(lon.size), indexing="ij")
    lat2, lon2 = np.meshgrid(lat, lon, indexing="ij")
    return pd.DataFrame({"pixel_id": (ilat.ravel() * 1000 + ilon.ravel()).astype("int64"),
                         "lat": lat2.ravel(), "lon": lon2.ravel()})


# --- MAIAC ------------------------------------------------------------------
MAIAC_DIR = CONT / "MCD19A2.061" / "pixeles_horario"


def catalogo_maiac() -> pd.DataFrame:
    partes = [pd.read_parquet(p, columns=["pixel_id", "lat", "lon"])
              for p in sorted(MAIAC_DIR.glob("catalogo_pixeles/tile=*/pixeles.parquet"))]
    if not partes:
        raise SystemExit("Falta el catálogo de píxeles MAIAC")
    return pd.concat(partes, ignore_index=True)


def decodificar_qa_maiac(qa: np.ndarray) -> dict[str, np.ndarray]:
    """Bits de AOD_QA (MCD19A2 v6.1): nube (0–2), adyacencia (5–7), QA AOD (8–11)."""
    qa = np.asarray(qa).astype("uint16")
    return {"nube": qa & 0b111, "adyacencia": (qa >> 5) & 0b111, "qa_aod": (qa >> 8) & 0b1111,
            "glint": (qa >> 12) & 0b1}


def maiac_dia(fecha: date, criterio: str = "estricta") -> pd.DataFrame | None:
    """Observaciones MAIAC de un día con calidad decodificada y hora de pasada."""
    etiqueta = fecha.strftime("%Y%m%d")
    sub = f"year={fecha:%Y}/month={fecha:%m}/day={fecha:%d}"
    obs_p = MAIAC_DIR / "observaciones" / sub / f"maiac_obs_{etiqueta}.parquet"
    pas_p = MAIAC_DIR / "catalogo_pasadas" / sub / f"maiac_pasadas_{etiqueta}.parquet"
    if not obs_p.exists() or not pas_p.exists():
        return None
    obs = pd.read_parquet(obs_p)
    pas = pd.read_parquet(pas_p, columns=["overpass_id", "ts_utc", "satelite"])
    q = decodificar_qa_maiac(obs["qa_raw"].to_numpy())
    if criterio == "estricta":
        ok = (q["nube"] == 1) & (q["qa_aod"] == 0)
    else:
        ok = (q["nube"] == 1) & np.isin(q["qa_aod"], [0, 1, 3, 4])
    ok &= np.isfinite(obs["aod055"].to_numpy()) & (obs["aod055"].to_numpy() >= -0.05) & (obs["aod055"].to_numpy() <= 5)
    obs = obs.loc[ok, ["overpass_id", "pixel_id", "aod055"]]
    obs = obs.merge(pas, on="overpass_id", how="inner")
    return obs


# --- TROPOMI NO2 -------------------------------------------------------------
TROPOMI_NO2_DIR = CONT / "S5P_TROPOMI" / "NO2" / "raw_chile"
MOLEC_CM2_POR_MOL_M2 = 6.02214e19 / 1e15  # mol m-2 → 1e15 moléculas cm-2


def orbitas_no2_dia(fecha: date) -> list[Path]:
    patron = f"____{fecha:%Y%m%d}T"
    return sorted(p for p in TROPOMI_NO2_DIR.glob("*.nc") if patron in p.name)


def leer_orbita_no2(path: Path, qa_min: float = 0.75) -> pd.DataFrame:
    """Píxeles de una órbita con qa ≥ qa_min: lat, lon, columna, precisión, hora UTC."""
    import netCDF4

    with netCDF4.Dataset(path) as nc:
        P = nc["PRODUCT"]
        lat = np.ma.filled(P["latitude"][:], np.nan)[0]
        lon = np.ma.filled(P["longitude"][:], np.nan)[0]
        qa = np.ma.filled(P["qa_value"][:], np.nan)[0].astype("float32")
        col = np.ma.filled(P["nitrogendioxide_tropospheric_column"][:], np.nan)[0]
        prec = np.ma.filled(P["nitrogendioxide_tropospheric_column_precision"][:], np.nan)[0]
        if "delta_time" in P.variables:
            dt = np.ma.filled(P["delta_time"][:], -1)[0].astype("int64")
            unidades = getattr(P["delta_time"], "units", "")
            m = re.search(r"since (\d{4}-\d{2}-\d{2})", unidades)
            base = np.datetime64(m.group(1)) if m else np.datetime64(f"{fecha_de_nombre(path.name)}")
            t_scan = base.astype("datetime64[ms]") + dt.astype("timedelta64[ms]")
        else:
            t_scan = np.full(lat.shape[0], np.datetime64("NaT"), dtype="datetime64[ms]")
        if "CHILE_SUBSET" in nc.groups:
            toca = np.asarray(nc["CHILE_SUBSET"]["toca_chile"][:], dtype=bool)
        else:
            toca = np.ones(lat.shape, dtype=bool)
    ok = toca & np.isfinite(col) & np.isfinite(lat) & np.isfinite(lon) & (qa >= qa_min)
    sl, gp = np.nonzero(ok)
    return pd.DataFrame({
        "lat": lat[sl, gp].astype("float64"), "lon": lon[sl, gp].astype("float64"),
        "no2_trop": (col[sl, gp] * MOLEC_CM2_POR_MOL_M2).astype("float32"),
        "no2_trop_prec": (prec[sl, gp] * MOLEC_CM2_POR_MOL_M2).astype("float32"),
        "qa": qa[sl, gp], "ts_utc": t_scan[sl],
    })


def fecha_de_nombre(nombre: str) -> str:
    m = re.search(r"____(\d{4})(\d{2})(\d{2})T", nombre)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else "1970-01-01"


# --- ACAG --------------------------------------------------------------------
ACAG_DIR = CONT / "ACAG_V6GL03" / "raw_chile"


def acag_mes(yyyymm: str) -> pd.DataFrame | None:
    """PM2.5 mensual ACAG por celda (pixel_id de la grilla fuente)."""
    import netCDF4

    archivos = sorted(ACAG_DIR.glob(f"V6GL03.CNNPM25.SA.{yyyymm}-{yyyymm}.*.chile.nc"))
    if not archivos:
        return None
    partes = []
    for p in archivos:
        with netCDF4.Dataset(p) as nc:
            pm = np.ma.filled(nc["PM25"][:], np.nan)
            pm = pm[0] if pm.ndim == 3 else pm
            pid = np.asarray(nc["pixel_id"][:], dtype="int64")
            toca = np.asarray(nc["toca_chile"][:], dtype=bool)
        ok = toca & np.isfinite(pm)
        partes.append(pd.DataFrame({"celda": pid[ok], "acag_pm25": pm[ok].astype("float32")}))
    return pd.concat(partes, ignore_index=True).drop_duplicates("celda")


def acag_meses_disponibles() -> list[str]:
    return sorted({re.search(r"\.(\d{6})-\d{6}\.", p.name).group(1)
                   for p in ACAG_DIR.glob("V6GL03.CNNPM25.SA.*.continente.chile.nc")})


# --- Estaciones ----------------------------------------------------------------
def leer_estaciones() -> pd.DataFrame:
    ruta = DATA / "sinca" / "estaciones_georreferenciadas.csv"
    est = pd.read_csv(ruta, dtype={"estacion": str})
    usable = est["usable_geoespacial"].astype(str).str.lower().isin(["true", "1"])
    est = est[usable].copy()
    est["cod_comuna"] = pd.to_numeric(est["cod_comuna_geografica"], errors="coerce").astype("Int64")
    return est[["estacion", "nombre", "region_sinca", "lat", "lon", "cod_comuna"]].reset_index(drop=True)


def version_sinca(carpeta: Path) -> Path | None:
    """Elige la versión del derivado SINCA v1 con la ventana más amplia.

    Una carpeta ``estacion=*/contaminante=*`` puede tener varias
    ``version=<sha>/`` (por ejemplo la serie completa desde 2000 y una corrida
    incremental de pocos días). Se prefiere la de ``since`` más temprano,
    luego ``until`` más tardío, luego ``created_utc`` más reciente (todo del
    ``manifest.json``); sin manifiesto, la de más filas. Nunca se elige por
    orden alfabético del hash.
    """
    candidatas = []
    for obs in carpeta.glob("version=*/observaciones.parquet"):
        mani = obs.parent / "manifest.json"
        since, until, creado, filas = "9999", "0000", "", 0
        if mani.exists():
            try:
                m = json.loads(mani.read_text(encoding="utf-8"))
                inp = m.get("inputs", {}) if isinstance(m.get("inputs"), dict) else {}
                since = str(inp.get("since") or m.get("since") or since)
                until = str(inp.get("until") or m.get("until") or until)
                creado = str(m.get("created_utc") or "")
                filas = int(next((f.get("rows", 0) for f in m.get("files", [])
                                  if f.get("name") == "observaciones.parquet"), 0))
            except (ValueError, TypeError, AttributeError):
                pass
        if filas == 0:
            try:
                import pyarrow.parquet as pq
                filas = int(pq.read_metadata(obs).num_rows)
            except Exception:  # noqa: BLE001
                filas = 0
        candidatas.append((since, until, creado, filas, obs))
    if not candidatas:
        return None
    # since ascendente, luego until / created / filas descendentes.
    candidatas.sort(key=lambda c: (c[0], _inv(c[1]), _inv(c[2]), -c[3]))
    return candidatas[0][4]


def _inv(texto: str) -> tuple:
    """Clave que invierte el orden lexicográfico de un texto ASCII."""
    return tuple(-ord(ch) for ch in texto) + (1,)


def series_sinca(pol: str, estaciones: list[str] | None = None) -> pd.DataFrame:
    """Observaciones SINCA del derivado v1: una versión por estación (``version_sinca``)."""
    filas = []
    for carpeta in sorted(SINCA_DERIVADO.glob(f"estacion=*/contaminante={pol}")):
        est = carpeta.parent.name.split("=", 1)[1]
        if estaciones is not None and est not in estaciones:
            continue
        p = version_sinca(carpeta)
        if p is None:
            continue
        df = pd.read_parquet(p, columns=["ts_local", "obs", "qc_observacion", "seleccionada"])
        df = df[df["seleccionada"].astype(bool) & df["obs"].notna()]
        lo, hi = RANGO_VALIDO[pol]
        df = df[df["obs"].between(lo, hi)]
        df["estacion"] = est
        df["version"] = p.parent.name.split("=", 1)[1]
        filas.append(df[["estacion", "ts_local", "obs", "qc_observacion", "version"]])
    if not filas:
        return pd.DataFrame(columns=["estacion", "ts_local", "obs", "qc_observacion", "version"])
    out = pd.concat(filas, ignore_index=True)
    out["ts_utc"] = sinca_local_a_bin_utc(out["ts_local"])
    out = out.groupby(["estacion", "ts_utc"], as_index=False).agg(
        obs=("obs", "mean"), n=("obs", "size"), version=("version", "first"))
    return out
