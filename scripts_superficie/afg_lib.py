# --- 8<: setup ---
"""Configuración global: rutas del repo, contaminantes, unidades y caché.

El código y ``output_files/`` permanecen en el repo. La raíz ``data`` se
resuelve con ``AIR_POLLUTION_DATA_ROOT`` (o con la raíz común
``ASESORIAS_DATA_ROOT``). Si un artefacto cacheado existe, el chunk que lo
produce se salta el cómputo (borrar el artefacto = regenerarlo).
"""
from __future__ import annotations

import json
import os
import re
import warnings
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

def _encontrar_raiz() -> Path:
    """Raíz del repo; no depende de que ``data/`` esté dentro de él."""
    if os.environ.get("AFG_REPO_ROOT"):
        return Path(os.environ["AFG_REPO_ROOT"]).resolve()
    return Path(__file__).resolve().parents[1]

RAIZ = _encontrar_raiz()
_EXPLICIT_DATA_ROOT = os.environ.get("AIR_POLLUTION_DATA_ROOT")
_DATOS_VOLUME = Path("/Volumes/Datos")
AIR_POLLUTION_DATA_ROOT = Path(
    _EXPLICIT_DATA_ROOT
    or Path(os.environ.get("ASESORIAS_DATA_ROOT", "/Volumes/Datos/Asesorias_Data"))
    / "AirPollution" / "data"
).expanduser().resolve()
if not _EXPLICIT_DATA_ROOT and \
        (AIR_POLLUTION_DATA_ROOT == _DATOS_VOLUME
         or _DATOS_VOLUME in AIR_POLLUTION_DATA_ROOT.parents) and \
        not _DATOS_VOLUME.is_mount():
    raise SystemExit(
        "El volumen externo /Volumes/Datos no está montado. Conecta el disco "
        "o define AIR_POLLUTION_DATA_ROOT explícitamente."
    )
DATA = AIR_POLLUTION_DATA_ROOT
AIR_POLLUTION_DERIVED_ROOT = Path(
    os.environ.get("AIR_POLLUTION_DERIVED_ROOT")
    or DATA.parent / "derived"
).expanduser().resolve()
if os.environ.get("AFG_NEURO_OUTPUT_ROOT"):
    NEURO_OUTPUT = Path(os.environ["AFG_NEURO_OUTPUT_ROOT"]).expanduser().resolve()
elif os.environ.get("AFG_NEURO_ROOT"):  # compatibilidad con la variable antigua
    NEURO_OUTPUT = (Path(os.environ["AFG_NEURO_ROOT"]).expanduser().resolve()
                    / "output_files")
else:
    NEURO_OUTPUT = (AIR_POLLUTION_DERIVED_ROOT
                    / "Neurodegen-Epidemiology-Chile" / "output_files")
SINCA_DIR = DATA / "sinca"
CONT = DATA / "contaminantes"
SMOKE = os.environ.get("AFG_SMOKE", "0") == "1"      # corrida corta de prueba
OUT = RAIZ / "output_files" / ("_smoke" if SMOKE else "")
FIGS = OUT / "figures"
FIGS.mkdir(parents=True, exist_ok=True)

POLITICA_TEMPORAL_RUTA = RAIZ / "config" / "sinca" / "politica_temporal.json"
if not POLITICA_TEMPORAL_RUTA.exists():
    raise SystemExit(f"Falta la política temporal versionada: {POLITICA_TEMPORAL_RUTA}")
POLITICA_TEMPORAL = json.loads(POLITICA_TEMPORAL_RUTA.read_text(encoding="utf-8"))
_POLITICA_SINCA = POLITICA_TEMPORAL["sinca"]
_POLITICA_MERRA2 = POLITICA_TEMPORAL["merra2_comunal"]
ZONA_HORARIA_DEFAULT = str(_POLITICA_SINCA["zona_iana_default"])
ZONA_HORARIA_REGION = dict(_POLITICA_SINCA["zonas_iana_por_region"])
MERRA2_HORAS_PARA_UTC = int(_POLITICA_MERRA2["horas_para_recuperar_utc"])

# Contaminantes objetivo, sus unidades SINCA y rangos físicos plausibles
CONTAMINANTES = ["pm25", "pm10", "no2", "o3", "so2", "co"]
UNIDADES = {"pm25": "µg/m³", "pm10": "µg/m³", "no2": "ppb",
            "o3": "ppb", "so2": "ppb", "co": "ppm"}
RANGO_VALIDO = {"pm25": (0, 1500), "pm10": (0, 3000), "no2": (0, 1000),
                "o3": (0, 500), "so2": (0, 3000), "co": (0, 60)}

# Macrozonas (5) a partir del código de región SINCA
MACROZONA = {
    "RXV": "norte_grande", "RI": "norte_grande", "RII": "norte_grande",
    "RIII": "norte_chico", "RIV": "norte_chico",
    "RV": "centro", "RM": "centro", "RVI": "centro", "RVII": "centro",
    "RVIII": "sur", "RIX": "sur", "RXIV": "sur", "RX": "sur",
    "RXI": "austral", "RXII": "austral",
}

# Perillas de ejecución (sobre-escribibles por variable de entorno)
MAX_FILAS_TRAIN = int(os.environ.get("AFG_MAX_TRAIN_ROWS", "300000"))
N_ARBOLES = int(os.environ.get("AFG_N_TREES", "600"))
SEMILLA = 42

def cache_parquet(ruta: Path, generar):
    """Devuelve el DataFrame cacheado en `ruta`, o lo genera y lo guarda."""
    if ruta.exists():
        return pd.read_parquet(ruta)
    df = generar()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(ruta, index=False)
    return df

def leer_estaciones() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Metadatos SINCA validados contra ficha oficial y comuna geometrica."""
    ruta = SINCA_DIR / "estaciones_georreferenciadas.csv"
    if not ruta.exists():
        raise SystemExit(
            "Falta estaciones_georreferenciadas.csv; ejecuta primero "
            "scripts_pipeline/actualizar_geometria_sinca.py"
        )
    est = pd.read_csv(ruta)
    est["estacion"] = est["estacion"].astype(str)
    est["comuna"] = est["comuna_geografica"]
    est["macrozona"] = est["region_sinca"].map(MACROZONA)
    valores = est["usable_geoespacial"]
    if valores.dtype == bool:
        validas = valores.fillna(False)
    else:
        normalizados = valores.astype("string").str.strip().str.lower()
        desconocidos = normalizados[~normalizados.isin(["true", "false"])].dropna()
        if len(desconocidos):
            raise SystemExit(
                "Valores inválidos en usable_geoespacial: "
                + ", ".join(sorted(desconocidos.unique()))
            )
        validas = normalizados.map({"true": True, "false": False}).fillna(False)
    return (est[validas].reset_index(drop=True),
            est[~validas].reset_index(drop=True))

ESTACIONES, ESTACIONES_EXCLUIDAS = leer_estaciones()

def _zonas_horarias_por_estacion(estaciones: pd.Series) -> pd.Series:
    """Zona IANA histórica de cada código de estación SINCA.

    No se infiere desde la longitud: la política horaria de Aysén y Magallanes
    difiere de la del resto de Chile y ``zoneinfo`` conserva sus cambios
    históricos.
    """
    codigos = estaciones.astype("string")
    region_por_estacion = ESTACIONES.set_index("estacion")["region_sinca"]
    regiones = codigos.map(region_por_estacion)
    if regiones.isna().any():
        faltantes = sorted(codigos[regiones.isna()].dropna().unique())
        raise ValueError(
            "hay estaciones SINCA sin región para asignar zona horaria: "
            + ", ".join(faltantes)
        )
    return regiones.map(
        lambda region: ZONA_HORARIA_REGION.get(region, ZONA_HORARIA_DEFAULT)
    ).astype("string")

def _resolver_hora_local_utc(
    ts_local: pd.Series, zonas: pd.Series,
) -> pd.DataFrame:
    """Convierte reloj local a UTC sin borrar horas durante cambios DST.

    Para una hora repetida se conserva la ocurrencia estándar y también su
    alternativa UTC. Una hora inexistente se desplaza al primer instante
    válido. El reloj local y la decisión quedan auditables en el llamador.
    """
    local = pd.to_datetime(ts_local, errors="coerce")
    zonas = pd.Series(zonas, index=local.index, dtype="string")
    if (local.notna() & zonas.isna()).any():
        raise ValueError("hay horas locales válidas sin zona horaria")

    ts_utc = pd.Series(pd.NaT, index=local.index, dtype="datetime64[ns]")
    ts_alt = pd.Series(pd.NaT, index=local.index, dtype="datetime64[ns]")
    qc = pd.Series("ok", index=local.index, dtype="string")
    qc.loc[local.isna()] = "hora_local_invalida"

    for zona in sorted(zonas.dropna().unique()):
        indices = zonas.index[zonas == zona]
        local_zona = local.loc[indices]
        tz = ZoneInfo(str(zona))
        loc_estandar = local_zona.dt.tz_localize(
            tz, ambiguous=False, nonexistent="NaT"
        )
        loc_verano = local_zona.dt.tz_localize(
            tz, ambiguous=True, nonexistent="NaT"
        )
        ambiguas = (
            loc_estandar.notna() & loc_verano.notna()
            & (loc_estandar.astype("int64") != loc_verano.astype("int64"))
        )
        inexistentes = loc_estandar.isna() & loc_verano.isna() & local_zona.notna()
        loc_elegida = loc_estandar.copy()
        if inexistentes.any():
            loc_elegida.loc[inexistentes] = local_zona.loc[
                inexistentes
            ].dt.tz_localize(
                tz, ambiguous=False, nonexistent="shift_forward"
            )
        ts_utc.loc[indices] = (
            loc_elegida.dt.tz_convert("UTC").dt.tz_localize(None)
        )
        idx_ambiguas = ambiguas.index[ambiguas]
        idx_inexistentes = inexistentes.index[inexistentes]
        qc.loc[idx_ambiguas] = "ambigua_asumida_estandar"
        qc.loc[idx_inexistentes] = "inexistente_desplazada_adelante"
        ts_alt.loc[idx_ambiguas] = (
            loc_verano.loc[ambiguas].dt.tz_convert("UTC").dt.tz_localize(None)
        )
    return pd.DataFrame({
        "ts": ts_utc,
        "qc_hora": qc,
        "ts_utc_alternativo": ts_alt,
    })

def _hora_utc_a_local_por_estacion(
    ts_utc: pd.Series, estaciones: pd.Series,
) -> pd.Series:
    """Convierte UTC naive al reloj IANA histórico de cada estación."""
    utc = pd.to_datetime(ts_utc, errors="coerce")
    if utc.dt.tz is not None:
        raise ValueError("se esperaba una serie UTC sin zona horaria")
    zonas = _zonas_horarias_por_estacion(estaciones)
    local = pd.Series(pd.NaT, index=utc.index, dtype="datetime64[ns]")
    for zona in sorted(zonas.dropna().unique()):
        indices = zonas.index[zonas == zona]
        local.loc[indices] = (
            utc.loc[indices].dt.tz_localize("UTC")
            .dt.tz_convert(ZoneInfo(str(zona))).dt.tz_localize(None)
        )
    return local
# --- 8<: fin setup ---

# --- 8<: sinca ---
def leer_sinca_serie(ruta: Path) -> pd.DataFrame:
    """Parsea un CSV del exportador SINCA (``FECHA;HORA;validado;preliminar;no_validado``).

    Toma el primer valor numérico finito entre las tres columnas de registro
    (validado → preliminar → no validado) y usa coma decimal cuando aparece.
    Conserva la calidad en qc_observacion y ts_local naive (hora local Chile).
    """
    df = pd.read_csv(ruta, sep=";", header=None, dtype=str,
                     names=["fecha", "hora", "v1", "v2", "v3", "extra"],
                     usecols=range(6), skiprows=1, engine="c")
    obs = pd.Series(np.nan, index=df.index, dtype=float)
    calidad = pd.Series("sin_dato", index=df.index, dtype=object)
    for columna, etiqueta in zip(
        ["v1", "v2", "v3"], ["validado", "preliminar", "no_validado"]
    ):
        valores = pd.to_numeric(
            df[columna].str.strip().str.replace(",", ".", regex=False),
            errors="coerce",
        )
        tomar = obs.isna() & np.isfinite(valores)
        obs.loc[tomar] = valores.loc[tomar]
        calidad.loc[tomar] = etiqueta
    ts = pd.to_datetime(df["fecha"] + df["hora"], format="%y%m%d%H%M",
                        errors="coerce")
    out = pd.DataFrame({
        "ts_local": ts, "obs": obs, "qc_observacion": calidad,
    }).dropna(subset=["ts_local"])
    return out

def tabla_cobertura_sinca() -> pd.DataFrame:
    """Cobertura de la observación por contaminante (estaciones, filas
    horarias, periodo). Cacheada en ``output_files/cobertura_sinca.csv``
    para que el documento se reconstruya sin los CSV crudos."""
    ruta = OUT / "cobertura_sinca.csv"
    if ruta.exists():
        return pd.read_csv(ruta)
    filas = []
    for pol in CONTAMINANTES:
        o = leer_sinca(pol)
        filas.append({"contaminante": pol, "unidad": UNIDADES[pol],
                      "estaciones": int(o["estacion"].nunique()),
                      "filas horarias": int(len(o)),
                      "desde": str(o["ts"].min())[:10],
                      "hasta": str(o["ts"].max())[:10]})
    df = pd.DataFrame(filas)
    df.to_csv(ruta, index=False)
    return df

def leer_sinca(pol: str) -> pd.DataFrame:
    """Serie horaria SINCA de un contaminante, todas las estaciones, en UTC.

    La hora local siempre se conserva. En cambios de hora se elige de forma
    explícita la ocurrencia estándar para horas ambiguas y se desplazan hacia
    adelante las inexistentes. Se aplican las zonas IANA propias de Magallanes
    y Aysén; ``qc_hora`` y ``ts_utc_alternativo`` permiten auditar la decisión
    sin eliminar la medición original.
    """
    filas = []
    for ruta in sorted((SINCA_DIR / pol / "horario").glob("*.csv")):
        region, estacion = ruta.stem.split("_")[:2]
        s = leer_sinca_serie(ruta)
        if s["obs"].notna().sum() == 0:
            continue
        s["estacion"] = estacion
        rango = re.search(
            r"_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})$", ruta.stem
        )
        s["_fuente_desde"] = pd.Timestamp(rango.group(1)) if rango else pd.NaT
        s["_fuente_hasta"] = pd.Timestamp(rango.group(2)) if rango else pd.NaT
        s["_fuente_dias"] = (
            (s["_fuente_hasta"] - s["_fuente_desde"]).dt.days
            if rango else -1
        )
        s["_fuente_nombre"] = ruta.name
        filas.append(s)
    if not filas:
        return pd.DataFrame(columns=[
            "estacion", "ts", "ts_local", "zona_horaria", "qc_hora",
            "ts_utc_alternativo", "obs", "qc_observacion", "archivo_fuente",
        ])
    df = pd.concat(filas, ignore_index=True)
    # Pueden coexistir descargas solapadas (p. ej. 2019--2024 y 2000--2026).
    # Primero una medición finita/plausible y después su calidad SINCA.
    # Sólo a igual calidad prevalece la fuente más reciente/más amplia.
    # Una actualización vacía o fuera de rango no debe ocultar historia útil.
    lo, hi = RANGO_VALIDO[pol]
    df["_util"] = np.isfinite(df["obs"]) & df["obs"].between(lo, hi)
    df["_calidad"] = df["qc_observacion"].map({
        "sin_dato": 0, "no_validado": 1, "preliminar": 2, "validado": 3,
    }).fillna(0)
    df = (df.sort_values(
        ["estacion", "ts_local", "_util", "_calidad", "_fuente_hasta", "_fuente_dias",
         "_fuente_nombre"],
        kind="stable", na_position="first",
    ).drop_duplicates(["estacion", "ts_local"], keep="last"))
    df["zona_horaria"] = _zonas_horarias_por_estacion(df["estacion"])
    temporal = _resolver_hora_local_utc(df["ts_local"], df["zona_horaria"])
    df[["ts", "qc_hora", "ts_utc_alternativo"]] = temporal
    df.loc[~df["_util"], "obs"] = np.nan
    df["archivo_fuente"] = df["_fuente_nombre"]
    return df[[
        "estacion", "ts", "ts_local", "zona_horaria", "qc_hora",
        "ts_utc_alternativo", "obs", "qc_observacion", "archivo_fuente",
    ]].dropna(subset=["ts", "obs"])
# --- 8<: fin sinca ---

# --- 8<: fuentes ---
# Extracción de los modelos físicos desde los NetCDF mensuales nativos Chile.
# Los rectángulos históricos se usan únicamente para meses todavía no
# reemplazados. Todo queda en una tabla derivada estación × hora UTC; los
# archivos maestros conservan cada píxel y su timestamp nativo.

M_AIRE = 28.9647  # g/mol
M_GAS = {"no2": 46.0055, "o3": 47.9982, "so2": 64.066, "co": 28.0101}

def _puntos_xr(ds, lats, lons, lat="lat", lon="lon"):
    import xarray as xr
    return ds.sel({lat: xr.DataArray(lats, dims="est"),
                   lon: xr.DataArray(lons, dims="est")}, method="nearest")


def _xyz(lat, lon):
    la, lo = np.radians(lat), np.radians(lon)
    return np.column_stack([
        np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)
    ])


def _periodo_archivo(path: Path) -> pd.Period:
    coincidencias = re.findall(r"(?<!\d)((?:19|20)\d{4})(?!\d)", path.name)
    if not coincidencias:
        raise ValueError(f"mes YYYYMM ausente en {path.name}")
    return pd.Period(coincidencias[0], freq="M")


def _nativos_mensuales(base: Path, prefijo: str) -> dict[pd.Period, Path]:
    archivos = sorted((base / "mensual").glob(f"{prefijo}_*_chile_pixeles.nc"))
    return {_periodo_archivo(path): path for path in archivos}


def _extraer_nativos_mensuales(
    est: pd.DataFrame,
    archivos: dict[pd.Period, Path],
    nombres: dict[str, str],
) -> pd.DataFrame:
    """Selecciona la celda nativa chilena más cercana, sin interpolar."""
    if not archivos:
        return pd.DataFrame(columns=["estacion", "ts", *nombres.values()])
    import xarray as xr
    from scipy.spatial import cKDTree

    partes = []
    for _, path in sorted(archivos.items()):
        with xr.open_dataset(path) as ds:
            presentes = {src: dst for src, dst in nombres.items() if src in ds}
            if not presentes:
                continue
            if "pixel" not in ds.dims or not {"latitude", "longitude"}.issubset(ds.variables):
                raise ValueError(f"{path.name}: no cumple contrato time x pixel")
            lat = np.asarray(ds["latitude"].values, dtype=float)
            lon = np.asarray(ds["longitude"].values, dtype=float)
            validos = np.flatnonzero(np.isfinite(lat) & np.isfinite(lon))
            if not len(validos):
                continue
            arbol = cKDTree(_xyz(lat[validos], lon[validos]))
            _, cercanas = arbol.query(_xyz(est["lat"].to_numpy(), est["lon"].to_numpy()))
            elegidos = validos[np.asarray(cercanas, dtype=int)]
            sub = ds[list(presentes)].isel(
                pixel=xr.DataArray(elegidos, dims="est")
            ).to_dataframe().reset_index()
        sub["estacion"] = est["estacion"].to_numpy()[sub["est"].to_numpy(int)]
        sub = sub.rename(columns={"time": "ts", **presentes})
        sub["ts"] = pd.to_datetime(sub["ts"], errors="coerce", utc=True).dt.tz_convert(None)
        partes.append(sub[["estacion", "ts", *presentes.values()]])
    if not partes:
        return pd.DataFrame(columns=["estacion", "ts", *nombres.values()])
    return pd.concat(partes, ignore_index=True)


def _completar_con_legado(
    nativo: pd.DataFrame, legado: pd.DataFrame,
) -> pd.DataFrame:
    """Conserva legado sólo en meses sin reemplazo nativo."""
    if nativo.empty:
        return legado
    if legado.empty:
        return nativo
    meses = set(pd.to_datetime(nativo["ts"]).dt.to_period("M"))
    falta = ~pd.to_datetime(legado["ts"]).dt.to_period("M").isin(meses)
    return pd.concat([nativo, legado.loc[falta]], ignore_index=True)

def _escala_geoscf(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza unidades por archivo: el OPeNDAP de GEOS-CF sirve algunos
    meses con gases en mol/mol y PM2.5 en kg/m³, y otros ya convertidos a
    ppb/µg-m⁻³. Se detecta por magnitud (mediana) y se lleva todo a
    mol/mol y µg/m³ antes de la conversión final. Enmascara además los
    valores de relleno sin decodificar (≈1e15) que a veces trae el OPeNDAP."""
    pm = "pm25_rh35_gcc" if "pm25_rh35_gcc" in df else "pm25"
    for v in ["o3", "no2", "so2", "co", pm]:
        if v in df:
            df.loc[df[v].abs() > 1e13, v] = np.nan
    for v in ["o3", "no2", "so2", "co"]:
        if v not in df or not df[v].notna().any():
            continue
        med = float(np.nanmedian(df[v]))
        if med > 1e-3:                 # ya viene en ppb → devolver a mol/mol
            df[v] = df[v] * 1e-9
    if pm in df and df[pm].notna().any():
        med = float(np.nanmedian(df[pm]))
        if med < 1e-3:                 # viene en kg/m³ → µg/m³
            df[pm] = df[pm] * 1e9
    return df

def _extraer_geoscf_legado(est: pd.DataFrame) -> pd.DataFrame:
    """GEOS-CF (aqc_tavg_1hr): gases en mol/mol → ppb (CO → ppm), PM2.5 µg/m³."""
    import xarray as xr
    archivos = sorted((CONT / "GEOS_CF" / "raw_chile").glob("geoscf_*.nc"))
    if SMOKE:
        archivos = archivos[:2]
    partes = []
    for f in archivos:
        with xr.open_dataset(f) as ds:
            ds = ds.squeeze(drop=True)
            sub = _puntos_xr(ds, est["lat"].values, est["lon"].values)
            df = sub.to_dataframe().reset_index()
        partes.append(_escala_geoscf(df))
    if not partes:
        return pd.DataFrame(columns=[
            "estacion", "ts", "gcf_pm25", "gcf_no2", "gcf_o3", "gcf_so2", "gcf_co"
        ])
    g = pd.concat(partes, ignore_index=True)
    g["estacion"] = est["estacion"].values[g["est"].values]
    g = g.rename(columns={"time": "ts"})
    # tavg1: promedio de la hora estampado a la media hora (00:30 = 00–01 h);
    # se lleva al inicio de hora para calzar con SINCA (hora de inicio)
    g["ts"] = g["ts"].dt.floor("h")
    for v, col in [("no2", "gcf_no2"), ("o3", "gcf_o3"), ("so2", "gcf_so2")]:
        g[col] = g[v] * 1e9                       # mol/mol → ppb
    g["gcf_co"] = g["co"] * 1e6                   # mol/mol → ppm
    g["gcf_pm25"] = g["pm25_rh35_gcc"]            # ya en µg/m³
    cols = ["estacion", "ts", "gcf_pm25", "gcf_no2", "gcf_o3", "gcf_so2", "gcf_co"]
    return g[cols]


def extraer_geoscf(est: pd.DataFrame) -> pd.DataFrame:
    """GEOS-CF mensual nativo; rectángulos legados sólo cubren meses faltantes."""
    archivos = _nativos_mensuales(
        CONT / "GEOS_CF" / "chile_nativo_025deg", "geos_cf"
    )
    n = _extraer_nativos_mensuales(
        est, archivos,
        {"no2": "no2", "o3": "o3", "so2": "so2", "co": "co", "pm25": "pm25"},
    )
    if not n.empty:
        n = _escala_geoscf(n)
        n["ts"] = pd.to_datetime(n["ts"]).dt.floor("h")
        for v in ["no2", "o3", "so2"]:
            n[f"gcf_{v}"] = n[v] * 1e9
        n["gcf_co"] = n["co"] * 1e6
        n["gcf_pm25"] = n["pm25"]
        n = n[["estacion", "ts", "gcf_pm25", "gcf_no2", "gcf_o3",
               "gcf_so2", "gcf_co"]]
    legado = _extraer_geoscf_legado(est)
    return _completar_con_legado(n, legado).sort_values(["estacion", "ts"])

def _convertir_cams(c: pd.DataFrame) -> pd.DataFrame:
    """Convierte las unidades fuente sin inventar pasos horarios intermedios."""
    if c.empty:
        return pd.DataFrame(columns=[
            "estacion", "ts", "cams_pm25", "cams_pm10", "cams_no2",
            "cams_o3", "cams_so2", "cams_co",
        ])
    for gas, col in [("no2", "cams_no2"), ("o3", "cams_o3"), ("so2", "cams_so2")]:
        c[col] = c[gas] * (M_AIRE / M_GAS[gas]) * 1e9
    c["cams_co"] = c["co"] * (M_AIRE / M_GAS["co"]) * 1e6
    c["cams_pm25"] = c["pm25"] * 1e9
    c["cams_pm10"] = c["pm10"] * 1e9
    cols = ["estacion", "ts", "cams_pm25", "cams_pm10", "cams_no2",
            "cams_o3", "cams_so2", "cams_co"]
    c["ts"] = pd.to_datetime(c["ts"]).dt.floor("h")
    return c[cols].sort_values(["estacion", "ts"])


def _extraer_cams_legado(est: pd.DataFrame) -> pd.DataFrame:
    """CAMS EAC4 (3-horario): gases kg/kg → ppb (CO → ppm), PM kg/m³ → µg/m³.

    Los archivos de gases usan longitud 0–360 y los de PM −180–180; ambos se
    llevan a puntos de estación y luego se interpola linealmente a paso horario
    (huecos de máximo 2 h entre pasos de 3 h).
    """
    import xarray as xr
    base = CONT / "CAMS_EAC4" / "raw_chile"
    anios = sorted({f.stem[-4:] for f in base.glob("cams_eac4_gas_*.nc")})
    if SMOKE:
        anios = anios[:1]
    partes = []
    for anio in anios:
        with xr.open_dataset(base / f"cams_eac4_gas_{anio}.nc") as g:
            g = g.squeeze(drop=True)
            # los archivos de gases vienen en longitud 0–360: convertir las
            # longitudes de estación (negativas) a esa convención
            lons = est["lon"].values % 360 if float(g.longitude.min()) >= 0 \
                else est["lon"].values
            sub = _puntos_xr(g, est["lat"].values, lons,
                             lat="latitude", lon="longitude")
            dfg = sub.to_dataframe().reset_index()
        with xr.open_dataset(base / f"cams_eac4_pm_{anio}.nc") as p:
            subp = _puntos_xr(p, est["lat"].values, est["lon"].values,
                              lat="latitude", lon="longitude")
            dfp = subp.to_dataframe().reset_index()
        for df in (dfg, dfp):
            df["estacion"] = est["estacion"].values[df["est"].values]
        dfg = dfg.rename(columns={"valid_time": "ts"})
        dfp = dfp.rename(columns={"valid_time": "ts"})
        m = dfg.merge(dfp[["estacion", "ts", "pm2p5", "pm10"]],
                      on=["estacion", "ts"], how="outer")
        partes.append(m)
    if not partes:
        return _convertir_cams(pd.DataFrame())
    c = pd.concat(partes, ignore_index=True).rename(
        columns={"go3": "o3", "pm2p5": "pm25"}
    )
    return _convertir_cams(c)


def extraer_cams(est: pd.DataFrame) -> pd.DataFrame:
    """CAMS EAC4 nativo 3-horario; no interpola horas inexistentes."""
    archivos = _nativos_mensuales(
        CONT / "CAMS_EAC4" / "chile_nativo_075deg", "cams_eac4"
    )
    n = _extraer_nativos_mensuales(
        est, archivos,
        {"no2": "no2", "o3": "o3", "so2": "so2", "co": "co",
         "pm25": "pm25", "pm10": "pm10"},
    )
    n = _convertir_cams(n)
    legado = _extraer_cams_legado(est)
    return _completar_con_legado(n, legado).sort_values(["estacion", "ts"])

def extraer_acag(est: pd.DataFrame) -> pd.DataFrame:
    """ACAG V6GL03 mensual chileno 0,01°; anual sólo para meses faltantes."""
    import xarray as xr
    from scipy.spatial import cKDTree

    base = CONT / "ACAG_V6GL03" / "raw_chile"
    mensuales: dict[pd.Period, list[Path]] = {}
    patron = re.compile(r"\.(\d{6})-\1\.[^.]+\.chile\.nc$")
    for path in sorted(base.glob("*.chile.nc")):
        m = patron.search(path.name)
        if m:
            mensuales.setdefault(pd.Period(m.group(1), "M"), []).append(path)

    filas = []
    for periodo, archivos in sorted(mensuales.items()):
        latitudes, longitudes, valores = [], [], []
        for path in archivos:
            with xr.open_dataset(path) as ds:
                pm = np.asarray(ds["PM25"].values, dtype=float)
                toca = np.asarray(ds.get("toca_chile", xr.ones_like(ds["PM25"])).values,
                                  dtype=bool)
                lon2, lat2 = np.meshgrid(
                    np.asarray(ds["lon"].values, dtype=float),
                    np.asarray(ds["lat"].values, dtype=float),
                )
            ok = np.isfinite(pm) & toca
            latitudes.append(lat2[ok]); longitudes.append(lon2[ok]); valores.append(pm[ok])
        if not valores or not sum(map(len, valores)):
            continue
        lat = np.concatenate(latitudes); lon = np.concatenate(longitudes)
        pm = np.concatenate(valores)
        arbol = cKDTree(_xyz(lat, lon))
        distancia, indices = arbol.query(
            _xyz(est["lat"].to_numpy(), est["lon"].to_numpy())
        )
        # Una estación fuera de la cobertura sudamericana no debe heredar una
        # isla distante. 100 km es holgado frente a la celda nativa de ~1 km.
        km = 2 * 6371.0 * np.arcsin(np.clip(distancia / 2, 0, 1))
        seleccion = pm[np.asarray(indices, dtype=int)].astype(float)
        seleccion[km > 100] = np.nan
        filas.append(pd.DataFrame({
            "estacion": est["estacion"].values,
            "periodo": periodo,
            "acag_pm25": seleccion,
        }))

    meses_nativos = set(mensuales)
    for path in sorted(base.glob("V6GL03.CNNPM25.SA.*01-*12.nc")):
        m = re.search(r"\.((?:19|20)\d{2})01-((?:19|20)\d{2})12\.nc$", path.name)
        if not m or m.group(1) != m.group(2):
            continue
        anio = int(m.group(1))
        faltantes = [p for p in pd.period_range(f"{anio}-01", f"{anio}-12", freq="M")
                     if p not in meses_nativos]
        if not faltantes:
            continue
        with xr.open_dataset(path) as ds:
            sub = _puntos_xr(ds, est["lat"].values, est["lon"].values)
            vals = np.asarray(sub["PM25"].values, dtype=float)
        for periodo in faltantes:
            filas.append(pd.DataFrame({
                "estacion": est["estacion"].values,
                "periodo": periodo,
                "acag_pm25": vals,
            }))
    if not filas:
        return pd.DataFrame(columns=["estacion", "periodo", "acag_pm25"])
    return pd.concat(filas, ignore_index=True)

PROCESADO = DATA / "procesado_estacion"   # salidas de los extractores locales

def extraer_procesado_horario(nombre: str) -> pd.DataFrame | None:
    """Parquet horario por estación (``estacion``, ``ts`` UTC, columnas de
    valor) generado por un extractor local; None si no existe."""
    ruta = PROCESADO / f"{nombre}.parquet"
    if not ruta.exists():
        return None
    df = pd.read_parquet(ruta)
    df["estacion"] = df["estacion"].astype(str)
    df["ts"] = pd.to_datetime(df["ts"]).dt.floor("h")
    vals = [c for c in df.columns if c not in ("estacion", "ts")]
    return (df.groupby(["estacion", "ts"], as_index=False)[vals].mean())

def extraer_satelites_diarios() -> pd.DataFrame | None:
    """Une todos los productos satelitales DIARIOS por estación
    (``*_estacion_diario.parquet``: estacion, fecha, columnas) en una sola
    tabla estación × día; cada hora del día hereda el valor diario."""
    archivos = sorted(PROCESADO.glob("*_estacion_diario.parquet")) \
        if PROCESADO.exists() else []
    if not archivos:
        return None
    out = None
    for f in archivos:
        df = pd.read_parquet(f)
        df["estacion"] = df["estacion"].astype(str)
        df["fecha"] = pd.to_datetime(df["fecha"]).dt.floor("D")
        vals = [c for c in df.columns if c not in ("estacion", "fecha")]
        df = df.groupby(["estacion", "fecha"], as_index=False)[vals].mean()
        out = df if out is None else out.merge(df, on=["estacion", "fecha"],
                                              how="outer")
    return out

def _extraer_merra2_legado(est: pd.DataFrame) -> pd.DataFrame | None:
    """MERRA-2 aerosoles horarios (M2T1NXAER, recorte Chile) — opcional.

    Se incluye solo si ≥90 % de los días 2019–2024 están descargados en
    ``data/contaminantes/M2TMNXAER.5.12.4/raw_chile`` (en esta corrida puede
    omitirse). Aporta AOD total y masas superficiales de especies para PM.
    """
    import xarray as xr
    base = CONT / "M2TMNXAER.5.12.4" / "raw_chile"
    archivos = sorted(base.glob("MERRA2_*.tavg1_2d_aer_Nx.*.chile.nc4"))
    dias_esperados = pd.date_range("2019-01-01", "2024-12-31", freq="D").size
    if len(archivos) < 0.9 * dias_esperados:
        return None
    variables = ["TOTEXTTAU", "DUSMASS25", "SSSMASS25", "BCSMASS",
                 "OCSMASS", "SO4SMASS"]
    partes = []
    for f in archivos:
        with xr.open_dataset(f) as ds:
            pres = [v for v in variables if v in ds]
            sub = _puntos_xr(ds[pres], est["lat"].values, est["lon"].values)
            df = sub.to_dataframe().reset_index()
        df["estacion"] = est["estacion"].values[df["est"].values]
        partes.append(df)
    m = pd.concat(partes, ignore_index=True).rename(columns={"time": "ts"})
    m["m2_aod"] = m.get("TOTEXTTAU")
    # masa superficial de PM2.5 por especies (kg/m³ → µg/m³), receta MERRA-2
    comp = (m.get("DUSMASS25", 0) + m.get("SSSMASS25", 0) + m.get("BCSMASS", 0)
            + 1.4 * m.get("OCSMASS", 0) + 1.375 * m.get("SO4SMASS", 0))
    m["m2_pm25"] = comp * 1e9
    return m[["estacion", "ts", "m2_aod", "m2_pm25"]]


def extraer_merra2(est: pd.DataFrame) -> pd.DataFrame | None:
    """MERRA-2 horario nativo Chile; AER legado sólo cubre meses faltantes."""
    archivos = _nativos_mensuales(
        CONT / "MERRA2_meteo" / "chile_nativo_05x0625deg", "merra2_meteo"
    )
    n = _extraer_nativos_mensuales(
        est, archivos, {"aod_m2": "m2_aod", "pm25_m2": "m2_pm25"}
    )
    if not n.empty:
        n["ts"] = pd.to_datetime(n["ts"]).dt.floor("h")
    legado = _extraer_merra2_legado(est)
    if legado is None:
        legado = pd.DataFrame(columns=["estacion", "ts", "m2_aod", "m2_pm25"])
    out = _completar_con_legado(n, legado)
    return None if out.empty else out.sort_values(["estacion", "ts"])

def tabla_predictores() -> pd.DataFrame:
    """Tabla horaria compartida estación × hora UTC con todos los predictores."""
    def _generar():
        est = ESTACIONES
        g = extraer_geoscf(est)
        c = extraer_cams(est)
        t = g.merge(c, on=["estacion", "ts"], how="outer")
        a = extraer_acag(est)
        if len(a):
            t["periodo"] = t["ts"].dt.to_period("M")
            t = t.merge(a, on=["estacion", "periodo"], how="left").drop(columns="periodo")
        m2 = extraer_merra2(est)
        if m2 is not None:
            t = t.merge(m2, on=["estacion", "ts"], how="left")
        # productos pre-procesados POR ESTACIÓN (extractores locales de
        # scripts_superficie/extractores): satélites diarios, MAIAC 1 km
        # horario y ERA5-Land horario. Entran solos si el archivo existe.
        for horario in [extraer_procesado_horario("maiac_estacion_horario"),
                        extraer_procesado_horario("era5land_estacion_horario")]:
            if horario is not None:
                t = t.merge(horario, on=["estacion", "ts"], how="left")
        diario = extraer_satelites_diarios()
        if diario is not None:
            t["fecha"] = t["ts"].dt.floor("D")
            t = t.merge(diario, on=["estacion", "fecha"], how="left")
            t = t.drop(columns="fecha")
        for c in t.columns:
            if t[c].dtype == np.float64:
                t[c] = t[c].astype(np.float32)
        return t
    return cache_parquet(OUT / "predictores_estaciones_horario.parquet", _generar)

def resumen_predictores() -> pd.DataFrame:
    """Cobertura por fuente de la tabla de predictores, cacheada en
    ``output_files/resumen_predictores.csv`` (artefacto chico del render)."""
    ruta = OUT / "resumen_predictores.csv"
    if ruta.exists():
        return pd.read_csv(ruta)
    t = tabla_predictores()
    grupos = {
        "GEOS-CF (gcf_*)": [c for c in t.columns if c.startswith("gcf_")],
        "CAMS EAC4 (cams_*)": [c for c in t.columns if c.startswith("cams_")],
        "ACAG anual (acag_pm25)": [c for c in t.columns if c.startswith("acag_")],
        "MERRA-2 aerosol por estación (m2_*)": [c for c in t.columns if c.startswith("m2_")],
        "TROPOMI por estación (s5p_*)": [c for c in t.columns if c.startswith("s5p_")],
        "OMI por estación (omi_*)": [c for c in t.columns if c.startswith("omi_")],
        "MOPITT por estación (mop_*)": [c for c in t.columns if c.startswith("mop_")],
        "MAIAC 1 km por estación": [c for c in t.columns if c == "aod_maiac_est"],
        "ERA5-Land por estación (era5_*)": [c for c in t.columns if c.startswith("era5_")],
    }
    filas = []
    for fuente, cols in grupos.items():
        if not cols:
            continue
        con = t[cols].notna().any(axis=1)
        filas.append({"fuente": fuente, "columnas": len(cols),
                      "filas_con_dato": int(con.sum()),
                      "cobertura_pct": round(100 * float(con.mean()), 1),
                      "desde": str(t.loc[con, "ts"].min())[:10] if con.any() else "",
                      "hasta": str(t.loc[con, "ts"].max())[:10] if con.any() else ""})
    filas.append({"fuente": "TOTAL estación × hora", "columnas": t.shape[1] - 2,
                  "filas_con_dato": len(t), "cobertura_pct": 100.0,
                  "desde": str(t["ts"].min())[:10], "hasta": str(t["ts"].max())[:10]})
    df = pd.DataFrame(filas)
    df.to_csv(ruta, index=False)
    return df
# --- 8<: fin fuentes ---

# --- 8<: fuentes_neuro ---
# Insumos comunales pre-procesados: meteorología MERRA-2 agregada a comuna ×
# hora (T2M, RH2M, U10M, V10M, PS, PBLH, AOD y PM2.5 MERRA-2), AOD MAIAC
# comunal por pasada y covariables estáticas (fracción urbana, red vial,
# topografía). Se leen desde el almacén externo compartido. La variable
# AFG_NEURO_OUTPUT_ROOT permite reubicar sólo estos derivados; AFG_NEURO_ROOT
# se conserva por compatibilidad con ejecuciones antiguas.

def _leer_dbf(path: Path, enc: str = "utf-8") -> pd.DataFrame:
    """Lector mínimo de DBF (atributos de shapefile) sin dependencias."""
    import struct
    data = path.read_bytes()
    n_rec = struct.unpack("<I", data[4:8])[0]
    hdr_sz, rec_sz = struct.unpack("<HH", data[8:12])
    campos, off = [], 32
    while data[off] != 0x0D:
        nombre = data[off:off + 11].split(b"\x00")[0].decode("latin1")
        campos.append((nombre, data[off + 16])); off += 32
    filas, p = [], hdr_sz
    for _ in range(n_rec):
        rec = data[p:p + rec_sz]; p += rec_sz
        if not rec or rec[0:1] == b"*":
            continue
        v, q = {}, 1
        for nombre, flen in campos:
            v[nombre] = rec[q:q + flen].decode(enc, errors="replace").strip(); q += flen
        filas.append(v)
    return pd.DataFrame(filas)

def _norm_nombre(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return "".join(ch for ch in s if ch.isalnum())

def mapear_cod_comuna(est: pd.DataFrame) -> pd.Series:
    """cod_comuna oficial por estación (nombre de comuna → shapefile de comunas)."""
    dbf_path = DATA / "comunas.dbf"
    if not dbf_path.exists():
        return pd.Series(np.nan, index=est.index)
    dbf = _leer_dbf(dbf_path)
    dbf["k"] = dbf["Comuna"].map(_norm_nombre)
    mapa = dict(zip(dbf["k"], pd.to_numeric(dbf["cod_comuna"], errors="coerce")))
    return est["comuna"].map(_norm_nombre).map(mapa)

MET_COMUNAL_VARS = ["T2M", "RH2M", "U10M", "V10M", "PS", "PBLH",
                    "AOD_M2", "PM25_M2"]

def extraer_met_comunal(est: pd.DataFrame) -> pd.DataFrame | None:
    """MERRA-2 nativo por estación; el agregado comunal sólo llena brechas.

    La fuente preferida es ``MERRA2_meteo/chile_nativo_05x0625deg/mensual``.
    Conserva la celda nativa más cercana y los 24 pasos físicos diarios. Para
    meses todavía no migrados se admite el antiguo parquet comunal. Aunque ese
    parquet llama ``fecha_local`` a su reloj, su productor lo deriva
    de UTC restando exactamente tres horas (UTC−03 fijo), no con la hora civil
    ni con DST. Se invierte esa transformación sumando tres horas: así se
    conservan uno a uno los 24 pasos físicos diarios, sin horas ambiguas,
    desplazamientos ni promedios. Las claves duplicadas se consideran un error
    de integridad en vez de agregarse silenciosamente. Se lee con filtro por
    comuna (solo comunas con estación) para no cargar 63 M de filas.
    """
    archivos_nativos = _nativos_mensuales(
        CONT / "MERRA2_meteo" / "chile_nativo_05x0625deg", "merra2_meteo"
    )
    nativo = _extraer_nativos_mensuales(
        est, archivos_nativos,
        {"t2m": "T2M", "rh2m": "RH2M", "u10m": "U10M",
         "v10m": "V10M", "ps": "PS", "pblh": "PBLH",
         "aod_m2": "AOD_M2", "pm25_m2": "PM25_M2"},
    )
    if not nativo.empty:
        nativo["ts"] = pd.to_datetime(nativo["ts"]).dt.floor("h")
        for c in MET_COMUNAL_VARS:
            if c in nativo:
                nativo[c] = pd.to_numeric(nativo[c], errors="coerce").astype("float32")

    ruta = NEURO_OUTPUT / "merra2_comunal_horario.parquet"
    if not ruta.exists():
        return None if nativo.empty else nativo
    import pyarrow.parquet as pq
    cods = mapear_cod_comuna(est)
    validos = sorted(set(cods.dropna().astype(int)))
    tabla = pq.read_table(ruta, filters=[("cod_comuna", "in", validos)])
    met = tabla.to_pandas()
    pres = [v for v in MET_COMUNAL_VARS if v in met.columns]
    met["ts_reloj_fuente"] = (
        pd.to_datetime(met["fecha_local"])
        + pd.to_timedelta(met["hora"].astype(int), unit="h")
    )
    if met["ts_reloj_fuente"].isna().any():
        raise ValueError("MERRA-2 comunal contiene horas de fuente inválidas")
    met["ts"] = met["ts_reloj_fuente"] + pd.Timedelta(
        hours=MERRA2_HORAS_PARA_UTC
    )
    met = met[(met["ts"] >= "2018-12-31") & (met["ts"] <= "2025-01-02")]
    duplicadas = met.duplicated(["cod_comuna", "ts"], keep=False)
    if duplicadas.any():
        ejemplo = met.loc[duplicadas, ["cod_comuna", "ts"]].head(3)
        raise ValueError(
            "MERRA-2 comunal contiene claves comuna×UTC duplicadas; "
            "no se agregaron: " + ejemplo.to_dict("records").__repr__()
        )
    met = met[["cod_comuna", "ts"] + pres]
    for c in pres:
        met[c] = met[c].astype(np.float32)
    liga = pd.DataFrame({"estacion": est["estacion"].values,
                         "cod_comuna": cods.values}).dropna()
    liga["cod_comuna"] = liga["cod_comuna"].astype(int)
    out = liga.merge(met, on="cod_comuna", how="inner")
    if out.duplicated(["estacion", "ts"]).any():
        raise ValueError(
            "MERRA-2 comunal produjo claves estación×UTC duplicadas; "
            "no se agregaron"
        )
    legado = out.drop(columns="cod_comuna")
    combinado = _completar_con_legado(nativo, legado)
    return None if combinado.empty else combinado.sort_values(["estacion", "ts"])

def extraer_maiac_comunal(est: pd.DataFrame) -> pd.DataFrame | None:
    """AOD MAIAC comuna × pasada (CSV por año del repo neuro) → estación × hora UTC.

    Cada fila es una pasada Terra/Aqua con ``fecha`` + ``hora_utc``; se
    promedian pasadas coincidentes. La columna resultante ``aod_maiac`` es
    rala por construcción (solo horas con pasada y cielo despejado) — LightGBM
    maneja los NaN de forma nativa.
    """
    base = DATA / "contaminantes" / "MCD19A2.061" / "comunal_horario"
    if not base.exists():
        return None
    archivos = [base / f"maiac_aod_comunal_horario_{a}.csv" for a in range(2019, 2025)]
    archivos = [f for f in archivos if f.exists()]
    if not archivos:
        return None
    cods = mapear_cod_comuna(est)
    validos = set(cods.dropna().astype(int))
    partes = []
    for f in archivos:
        df = pd.read_csv(f, usecols=["cod_comuna", "fecha", "hora_utc",
                                     "aod055_media"])
        df = df[df["cod_comuna"].isin(validos)]
        hh = df["hora_utc"].astype(str).str.slice(0, 2).astype(int)
        df["ts"] = pd.to_datetime(df["fecha"]) + pd.to_timedelta(hh, unit="h")
        partes.append(df.groupby(["cod_comuna", "ts"], as_index=False)
                      ["aod055_media"].mean()
                      .rename(columns={"aod055_media": "aod_maiac"}))
    aod = pd.concat(partes, ignore_index=True)
    liga = pd.DataFrame({"estacion": est["estacion"].values,
                         "cod_comuna": cods.values}).dropna()
    liga["cod_comuna"] = liga["cod_comuna"].astype(int)
    out = liga.merge(aod, on="cod_comuna", how="left")
    return out.drop(columns="cod_comuna")

def extraer_estaticas(est: pd.DataFrame) -> pd.DataFrame | None:
    """Covariables estáticas por comuna (fracción urbana/pastizal, red vial OSM,
    altitud media y distancia a costa) del repo neuro → por estación."""
    rutas = {"estaticas": NEURO_OUTPUT / "estaticas_comunales_nac.csv",
             "topo": DATA / "contaminantes" / "Topografia" / "topografia_comunal.csv"}
    if not rutas["estaticas"].exists():
        return None
    cods = mapear_cod_comuna(est)
    liga = pd.DataFrame({"estacion": est["estacion"].values,
                         "cod_comuna": cods.values}).dropna()
    liga["cod_comuna"] = liga["cod_comuna"].astype(int)
    s = pd.read_csv(rutas["estaticas"])
    out = liga.merge(s, on="cod_comuna", how="left")
    if rutas["topo"].exists():
        t = pd.read_csv(rutas["topo"])[["cod_comuna", "alt_media", "dist_costa_km"]]
        out = out.merge(t, on="cod_comuna", how="left")
    return out.drop(columns="cod_comuna")
# --- 8<: fin fuentes_neuro ---

# --- 8<: fuentes_so2 ---
# Covariables de FUENTES PUNTUALES de SO₂ (fundiciones, termoeléctricas,
# refinerías). El diagnóstico LOSO muestra que la señal de SO₂ es de fuente
# puntual: sin saber dónde están los emisores, ningún motor generaliza a
# estaciones no vistas. La tabla ``data/fuentes_so2.csv`` lista las
# megafuentes con coordenadas y un peso relativo de emisión (orden de
# magnitud, refinable con RETC); de ella se derivan tres covariables por
# estación: distancia a la fuente más cercana, carga gravitacional Σ E/d²
# y — con el viento horario — la alineación direccional fuente → estación
# (¿está la estación viento abajo de una fuente pesada y cercana?).

def cargar_fuentes_so2() -> pd.DataFrame | None:
    ruta = DATA / "fuentes_so2.csv"
    if not ruta.exists():
        return None
    return pd.read_csv(ruta)

def _geometria_fuentes(est: pd.DataFrame):
    """Distancias (km) y versores fuente→estación para cada par."""
    f = cargar_fuentes_so2()
    if f is None or not len(f):
        return None
    la_e = est["lat"].to_numpy(float)[:, None]     # (n_est, 1)
    lo_e = est["lon"].to_numpy(float)[:, None]
    la_f = f["lat"].to_numpy(float)[None, :]       # (1, n_f)
    lo_f = f["lon"].to_numpy(float)[None, :]
    D = haversine_km(la_e, lo_e, la_f, lo_f)       # (n_est, n_f)
    # componentes planas locales del vector fuente→estación
    dx = (lo_e - lo_f) * 111.32 * np.cos(np.radians((la_e + la_f) / 2))
    dy = (la_e - la_f) * 110.57
    norma = np.sqrt(dx ** 2 + dy ** 2)
    norma[norma < 1e-6] = 1e-6
    ux, uy = dx / norma, dy / norma
    peso = f["peso_so2"].to_numpy(float)[None, :]
    W = peso / np.maximum(D, 2.0) ** 2             # carga gravitacional
    return {"D": D, "ux": ux, "uy": uy, "W": W}

def agregar_fuentes_so2(p: pd.DataFrame) -> pd.DataFrame:
    """Agrega las covariables de fuentes puntuales al panel.

    Estáticas por estación: ``dist_fuente_km`` (a la fuente más cercana) y
    ``carga_fuentes_so2`` = log(1 + Σ_k E_k/d_k²). Horaria (si hay viento
    MERRA-2): ``viento_fuentes_so2`` = log(1 + Σ_k (E_k/d_k²) ·
    max(0, u·x̂_k + v·ŷ_k)) — grande cuando el viento sopla DESDE una
    fuente pesada y cercana HACIA la estación."""
    geo = _geometria_fuentes(ESTACIONES)
    if geo is None:
        return p
    est_codes = ESTACIONES["estacion"].astype(str).to_numpy()
    idx_de = {e: i for i, e in enumerate(est_codes)}
    idx = p["estacion"].astype(str).map(idx_de)
    ok = idx.notna().to_numpy()
    fila_est = idx.fillna(0).astype(int).to_numpy()
    p["dist_fuente_km"] = np.where(
        ok, geo["D"].min(axis=1)[fila_est], np.nan).astype(np.float32)
    p["carga_fuentes_so2"] = np.where(
        ok, np.log1p(geo["W"].sum(axis=1))[fila_est], np.nan).astype(np.float32)
    if {"U10M", "V10M"}.issubset(p.columns):
        u = p["U10M"].to_numpy(np.float32)
        v = p["V10M"].to_numpy(np.float32)
        acc = np.zeros(len(p), dtype=np.float32)
        for k in range(geo["D"].shape[1]):
            proy = (u * geo["ux"][fila_est, k].astype(np.float32)
                    + v * geo["uy"][fila_est, k].astype(np.float32))
            acc += geo["W"][fila_est, k].astype(np.float32) * np.clip(proy, 0, None)
        p["viento_fuentes_so2"] = np.where(ok, np.log1p(acc), np.nan
                                           ).astype(np.float32)
    return p
# --- 8<: fin fuentes_so2 ---

# --- 8<: panel ---
# Panel de modelamiento por contaminante: observación SINCA + predictores +
# calendario (hora local, día del año, día de semana) + coordenadas.

FISICO = {   # columnas de modelo físico por contaminante: [principal, secundaria]
    "pm25": ["gcf_pm25", "cams_pm25"],
    "pm10": ["cams_pm10"],                # GEOS-CF aqc no trae PM10
    "no2":  ["gcf_no2", "cams_no2"],
    "o3":   ["gcf_o3", "cams_o3"],
    "so2":  ["gcf_so2", "cams_so2"],
    "co":   ["gcf_co", "cams_co"],
}
TODAS_FUENTES = ["gcf_pm25", "gcf_no2", "gcf_o3", "gcf_so2", "gcf_co",
                 "cams_pm25", "cams_pm10", "cams_no2", "cams_o3",
                 "cams_so2", "cams_co"]

def agregar_calendario(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega calendario según el reloj IANA histórico de cada estación."""
    ts_loc = _hora_utc_a_local_por_estacion(df["ts"], df["estacion"])
    h = ts_loc.dt.hour + ts_loc.dt.minute / 60
    doy = ts_loc.dt.dayofyear
    df["hora_sin"] = np.sin(2 * np.pi * h / 24)
    df["hora_cos"] = np.cos(2 * np.pi * h / 24)
    df["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    df["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    df["dow"] = ts_loc.dt.dayofweek.astype("int8")
    df["anio"] = ts_loc.dt.year.astype("int16")
    df["hora_loc"] = ts_loc.dt.hour.astype("int8")
    df["mes"] = ts_loc.dt.month.astype("int8")
    df["franja"] = np.where(df["hora_loc"].between(8, 18), "diurna", "nocturna")
    return df

def feats_fisicos(p: pd.DataFrame, pol: str) -> pd.DataFrame:
    """Features físico-informados estándar de la literatura AOD→PM:
    dilución masa/altura de mezcla (PBLH),
    crecimiento higroscópico f(RH), viento (ventilación) y AOD desinflado por
    humedad. Solo se crean si la meteorología comunal está disponible."""
    if "PBLH" in p:
        pblh = p["PBLH"].clip(lower=50.0)
        p["inv_pblh"] = 1.0 / pblh
        p["fis_div_pblh"] = p[FISICO[pol][0]] / pblh
        if "PM25_M2" in p:
            p["pm25m2_pblh"] = p["PM25_M2"] / pblh
    if "RH2M" in p:
        rh = p["RH2M"].clip(upper=97.0)
        rh = np.where(rh > 1.5, rh, rh * 100.0)      # acepta % o fracción
        p["frh"] = 1.0 / (1.0 - np.clip(rh, 0, 97) / 100.0)
    if {"U10M", "V10M"}.issubset(p.columns):
        p["wind"] = np.sqrt(p["U10M"] ** 2 + p["V10M"] ** 2)
    for aod in ["aod_maiac", "AOD_M2", "m2_aod"]:
        if aod in p and "frh" in p:
            p["aod_div_frh"] = p[aod] / p["frh"]
            break
    return p

def agregar_vecinas(p: pd.DataFrame, h_km: float = 150.0) -> pd.DataFrame:
    """Observación concurrente interpolada desde las DEMÁS estaciones (IDW
    gaussiano, diagonal en cero) — el insumo geoestadístico estándar de la
    interpolación espacial con bosques/boosting (p. ej. RFSI). Para la
    estación s en la hora t usa solo estaciones ≠ s, así que es válida bajo
    LOSO y calculable en cualquier comuna al generar la superficie.

    Agrega: ``obs_vec`` (interpolación) y ``peso_vec`` (suma de pesos =
    cuán informado está el vecindario; 0 = sin vecinos con dato).
    """
    O = p.pivot_table(index="ts", columns="estacion", values="obs",
                      aggfunc="mean")
    cols = O.columns.to_numpy()
    meta = ESTACIONES.set_index("estacion").loc[cols]
    lat, lon = meta["lat"].to_numpy(float), meta["lon"].to_numpy(float)
    D = haversine_km(lat[:, None], lon[:, None], lat[None, :], lon[None, :])
    W = np.exp(-(D / h_km) ** 2)
    np.fill_diagonal(W, 0.0)
    M = O.notna().to_numpy(float)
    V = np.nan_to_num(O.to_numpy(float))
    num = V @ W
    den = M @ W
    with np.errstate(invalid="ignore", divide="ignore"):
        idw = np.where(den > 0, num / den, np.nan)
    largo = pd.DataFrame(idw.astype(np.float32), index=O.index,
                         columns=cols).stack(future_stack=True)
    pesos = pd.DataFrame(den.astype(np.float32), index=O.index,
                         columns=cols).stack(future_stack=True)
    extra = pd.DataFrame({"obs_vec": largo, "peso_vec": pesos}).reset_index()
    extra.columns = ["ts", "estacion", "obs_vec", "peso_vec"]
    return p.merge(extra, on=["ts", "estacion"], how="left")

def _compactar(p: pd.DataFrame) -> pd.DataFrame:
    """float64 → float32 y texto → category: el panel horario cabe en RAM."""
    for c in p.columns:
        if p[c].dtype == np.float64:
            p[c] = p[c].astype(np.float32)
        elif p[c].dtype == object:
            p[c] = p[c].astype("category")
    return p

def construir_panel(pol: str) -> pd.DataFrame:
    """Panel horario listo para modelar (cacheado en output_files/)."""
    def _generar():
        import gc
        obs_cruda = leer_sinca(pol)
        obs_cruda["_dst_conflicto"] = obs_cruda["qc_hora"].ne("ok")
        # El lector crudo conserva cada medición. Sólo el panel, que exige una
        # clave estación×UTC única, combina las raras colisiones creadas al
        # resolver una hora civil inexistente. El conteo y la bandera hacen la
        # operación explícita y auditable; no hay deduplicación silenciosa.
        obs = (obs_cruda.groupby(
            ["estacion", "ts"], as_index=False, observed=True
        ).agg(
            obs=("obs", "mean"),
            sinca_n_mediciones_hora=("obs", "size"),
            sinca_dst_conflicto=("_dst_conflicto", "max"),
        ))
        obs["sinca_n_mediciones_hora"] = (
            obs["sinca_n_mediciones_hora"].astype("int8")
        )
        del obs_cruda
        pred = tabla_predictores()
        p = obs.merge(pred, on=["estacion", "ts"], how="inner")
        del obs, pred; gc.collect()
        # inner: solo estaciones con coordenadas válidas (ver leer_estaciones)
        p = p.merge(ESTACIONES[["estacion", "lat", "lon", "region_sinca",
                                "macrozona", "comuna"]], on="estacion", how="inner")
        p = agregar_calendario(p)
        p = agregar_vecinas(p)
        p = _compactar(p); gc.collect()
        met = extraer_met_comunal(ESTACIONES)
        if met is not None:
            p = p.merge(met, on=["estacion", "ts"], how="left")
            del met; gc.collect()
        aodm = extraer_maiac_comunal(ESTACIONES)
        if aodm is not None:
            p = p.merge(aodm, on=["estacion", "ts"], how="left")
            del aodm
        estat = extraer_estaticas(ESTACIONES)
        if estat is not None:
            p = p.merge(estat, on="estacion", how="left")
        p = agregar_fuentes_so2(p)
        p = feats_fisicos(p, pol)
        p = _compactar(p); gc.collect()
        # exige el modelo físico principal presente
        p = p.dropna(subset=[FISICO[pol][0]])
        return p
    ruta = OUT / f"panel_{pol}_horario.parquet"
    return cache_parquet(ruta, _generar)
# --- 8<: fin panel ---

# --- 8<: plotbase ---
# Primitivas compartidas de gráficos y métricas (se definen antes
# del análisis descriptivo y de la validación, que las reutilizan).
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({
    "figure.dpi": 150, "font.size": 10, "axes.titlesize": 12,
    "axes.titleweight": "bold", "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "grid.alpha": 0.25,
    # Tipografía Arial (o su equivalente métrico Liberation Sans)
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Liberation Sans", "Helvetica",
                        "DejaVu Sans"],
})
AZUL, NARANJO, VERDE, ROJO, MORADO = ("#4C72B0", "#DD8452", "#55A868",
                                      "#C44E52", "#8172B3")
COLOR_MOTOR = {"fisico": "#9a9a9a", "gwr": AZUL, "rk": VERDE, "lgbm": NARANJO}
NOMBRE_MOTOR = {"fisico": "Modelo físico crudo", "gwr": "GWR",
                "rk": "Regression-kriging", "lgbm": "LightGBM"}
NOMBRE_POL = {"pm25": "PM$_{2.5}$", "pm10": "PM$_{10}$", "no2": "NO$_2$",
              "o3": "O$_3$", "so2": "SO$_2$", "co": "CO"}
NOMBRE_POL_TXT = {"pm25": "PM₂.₅", "pm10": "PM₁₀", "no2": "NO₂",
                  "o3": "O₃", "so2": "SO₂", "co": "CO"}

def _guardar(fig, nombre: str) -> Path:
    ruta = FIGS / nombre
    fig.savefig(ruta, bbox_inches="tight")
    plt.close(fig)
    return ruta

def _fig_cacheada(nombre: str) -> Path | None:
    """Convención de caché del repo aplicada a FIGURAS: si el PNG ya existe en
    output_files/figures/, se reutiliza (borra el archivo para regenerarlo).
    Permite re-renderizar el sitio desde los artefactos versionados sin
    recomputar paneles ni OOF."""
    ruta = FIGS / nombre
    return ruta if ruta.exists() else None

def metricas(obs, pred) -> dict:
    m = np.isfinite(obs) & np.isfinite(pred)
    if m.sum() < 3:
        return {"n": int(m.sum()), "r2": np.nan, "rmse": np.nan,
                "mae": np.nan, "sesgo": np.nan}
    o, q = obs[m], pred[m]
    ss = float(np.sum((o - q) ** 2))
    var = float(np.sum((o - o.mean()) ** 2))
    r2 = (1 - ss / var) if var > 0 else np.nan   # obs constantes → R² indefinido
    return {"n": int(m.sum()), "r2": round(float(r2), 4),
            "rmse": round(float(np.sqrt(ss / len(o))), 3),
            "mae": round(float(np.mean(np.abs(o - q))), 3),
            "sesgo": round(float(np.mean(q - o)), 3)}

def metricas_diarias(df: pd.DataFrame, col: str) -> dict:
    d = (df.assign(dia=df["ts"].dt.floor("D"))
         .groupby(["estacion", "dia"])[["obs", col]].mean().dropna())
    return metricas(d["obs"].to_numpy(), d[col].to_numpy())
# --- 8<: fin plotbase ---

# --- 8<: descriptivo ---
# ANTES de calibrar: ¿cuánto acuerdan los modelos físicos CRUDOS (GEOS-CF /
# CAMS) con SINCA? Puntos horarios y diarios y series de tiempo, a tres
# niveles — nacional, macrozona y región. Este es el diagnóstico que motiva
# la calibración: dónde y cuándo el modelo global ya sirve, y dónde no.

NOMBRE_REGION = {
    "RXV": "Arica y P.", "RI": "Tarapacá", "RII": "Antofagasta",
    "RIII": "Atacama", "RIV": "Coquimbo", "RV": "Valparaíso",
    "RM": "Metropolitana", "RVI": "O'Higgins", "RVII": "Maule",
    "RVIII": "Biobío–Ñuble", "RIX": "Araucanía", "RXIV": "Los Ríos",
    "RX": "Los Lagos", "RXI": "Aysén", "RXII": "Magallanes",
}
ORDEN_REGIONES = list(NOMBRE_REGION)
ORDEN_MACROZONAS = ["norte_grande", "norte_chico", "centro", "sur", "austral"]
NOMBRE_MZ = {"norte_grande": "Norte Grande", "norte_chico": "Norte Chico",
             "centro": "Centro", "sur": "Sur", "austral": "Austral"}

def _modelos_de(p: pd.DataFrame, pol: str) -> list[tuple[str, str, str]]:
    """[(columna, etiqueta, color)] de los modelos físicos presentes."""
    out = []
    if f"gcf_{pol}" in p:
        out.append((f"gcf_{pol}", "GEOS-CF", NARANJO))
    if f"cams_{pol}" in p:
        out.append((f"cams_{pol}", "CAMS EAC4", MORADO))
    return out

def _pares_diarios(p: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    d = (p.assign(dia=p["ts"].dt.floor("D"))
         .groupby(["estacion", "dia"], observed=True)[["obs"] + cols]
         .mean().dropna(subset=["obs"]).reset_index())
    meta = ESTACIONES.set_index("estacion")[["macrozona", "region_sinca"]]
    return d.join(meta, on="estacion")

def _panel_hex(ax, o, q, unidad, titulo):
    m = np.isfinite(o) & np.isfinite(q)
    o, q = o[m], q[m]
    lim = float(np.nanquantile(np.concatenate([o, q]), 0.995)) or 1.0
    ax.hexbin(o, q, gridsize=50, bins="log", cmap="viridis",
              extent=(0, lim, 0, lim))
    ax.plot([0, lim], [0, lim], color=ROJO, lw=1.1, ls="--")
    met = metricas(o, q)
    r = np.corrcoef(o, q)[0, 1] if len(o) > 2 else np.nan
    ax.text(0.03, 0.97, f"n={met['n']:,}\nr²={r**2:.2f}\nR²={met['r2']:.2f}"
            f"\nRMSE={met['rmse']:.1f}", transform=ax.transAxes, va="top",
            fontsize=8, bbox=dict(boxstyle="round", fc="white", alpha=0.85))
    ax.set_xlim(0, lim); ax.set_ylim(0, lim)
    ax.set_title(titulo, fontsize=10)

def fig_acuerdo_nacional(pol: str) -> Path:
    """Dispersión nacional SINCA vs cada modelo físico crudo: horario y diario."""
    _c = _fig_cacheada(f"{pol}_acuerdo_nacional.png")
    if _c is not None:
        return _c
    p = construir_panel(pol)
    modelos = _modelos_de(p, pol)
    d = _pares_diarios(p, [c for c, _, _ in modelos])
    fig, axs = plt.subplots(len(modelos), 2,
                            figsize=(9.4, 4.4 * len(modelos)), squeeze=False)
    for i, (col, etq, _) in enumerate(modelos):
        _panel_hex(axs[i, 0], p["obs"].to_numpy(float), p[col].to_numpy(float),
                   UNIDADES[pol], f"{etq} — horario")
        _panel_hex(axs[i, 1], d["obs"].to_numpy(float), d[col].to_numpy(float),
                   UNIDADES[pol], f"{etq} — diario")
        axs[i, 0].set_ylabel(f"modelo ({UNIDADES[pol]})")
    for ax in axs[-1]:
        ax.set_xlabel(f"SINCA observado ({UNIDADES[pol]})")
    fig.suptitle(f"{NOMBRE_POL[pol]}: acuerdo crudo SINCA ↔ modelos físicos "
                 f"(nacional, sin calibrar)", fontweight="bold", y=1.005)
    fig.tight_layout()
    return _guardar(fig, f"{pol}_acuerdo_nacional.png")

def fig_acuerdo_macrozona(pol: str) -> Path:
    """Dispersión diaria por macrozona, modelo físico principal."""
    _c = _fig_cacheada(f"{pol}_acuerdo_macrozona.png")
    if _c is not None:
        return _c
    p = construir_panel(pol)
    col, etq, _ = _modelos_de(p, pol)[0]
    d = _pares_diarios(p, [col])
    mzs = [m for m in ORDEN_MACROZONAS if m in set(d["macrozona"].dropna())]
    fig, axs = plt.subplots(1, len(mzs), figsize=(3.1 * len(mzs), 3.5),
                            squeeze=False)
    for ax, mz in zip(axs[0], mzs):
        g = d[d["macrozona"] == mz]
        _panel_hex(ax, g["obs"].to_numpy(float), g[col].to_numpy(float),
                   UNIDADES[pol], NOMBRE_MZ[mz])
    axs[0][0].set_ylabel(f"{etq} ({UNIDADES[pol]})")
    for ax in axs[0]:
        ax.set_xlabel("SINCA")
    fig.suptitle(f"{NOMBRE_POL[pol]}: acuerdo diario por macrozona "
                 f"({etq} crudo)", fontweight="bold", y=1.04)
    fig.tight_layout()
    return _guardar(fig, f"{pol}_acuerdo_macrozona.png")

def tabla_acuerdo_niveles(pol: str) -> pd.DataFrame:
    """Métricas de acuerdo crudo por nivel (nacional / macrozona / región),
    horario y diario, por modelo. Cacheada en acuerdo_niveles_<pol>.csv."""
    ruta = OUT / f"acuerdo_niveles_{pol}.csv"
    if ruta.exists():
        return pd.read_csv(ruta)
    p = construir_panel(pol)
    modelos = _modelos_de(p, pol)
    cols = [c for c, _, _ in modelos]
    d = _pares_diarios(p, cols)
    ph = p    # el panel ya trae region_sinca y macrozona
    filas = []
    def _fila(nivel, nombre, sub_h, sub_d):
        for col, etq, _ in modelos:
            mh = metricas(sub_h["obs"].to_numpy(float), sub_h[col].to_numpy(float))
            md = metricas(sub_d["obs"].to_numpy(float), sub_d[col].to_numpy(float))
            filas.append({"nivel": nivel, "zona": nombre, "modelo": etq,
                          "n_h": mh["n"], "r2_h": mh["r2"], "rmse_h": mh["rmse"],
                          "sesgo_h": mh["sesgo"], "n_d": md["n"],
                          "r2_d": md["r2"], "rmse_d": md["rmse"],
                          "sesgo_d": md["sesgo"]})
    _fila("nacional", "Chile", ph, d)
    for mz in ORDEN_MACROZONAS:
        sh, sd = ph[ph["macrozona"] == mz], d[d["macrozona"] == mz]
        if len(sd):
            _fila("macrozona", NOMBRE_MZ[mz], sh, sd)
    for reg in ORDEN_REGIONES:
        sh = ph[ph["region_sinca"] == reg]
        sd = d[d["region_sinca"] == reg]
        if len(sd):
            _fila("region", NOMBRE_REGION[reg], sh, sd)
    out = pd.DataFrame(filas)
    out.to_csv(ruta, index=False)
    return out

def _serie_mensual(df, cols):
    g = (df.assign(mes_ts=df["ts"].dt.to_period("M").dt.to_timestamp())
         .groupby("mes_ts", observed=True)[["obs"] + cols].mean())
    return g

def fig_series_nacional_macrozona(pol: str) -> Path:
    """Series mensuales SINCA vs modelos crudos: nacional + macrozonas."""
    _c = _fig_cacheada(f"{pol}_series_nacional_macrozona.png")
    if _c is not None:
        return _c
    p = construir_panel(pol)
    modelos = _modelos_de(p, pol)
    cols = [c for c, _, _ in modelos]
    mzs = [m for m in ORDEN_MACROZONAS if m in set(p["macrozona"].dropna())]
    fig, axs = plt.subplots(len(mzs) + 1, 1, figsize=(10.5, 2.1 * (len(mzs) + 1)),
                            sharex=True)
    def _dibujar(ax, sub, titulo):
        s = _serie_mensual(sub, cols)
        ax.plot(s.index, s["obs"], color="#222", lw=1.8, label="SINCA")
        for col, etq, c in modelos:
            ax.plot(s.index, s[col], color=c, lw=1.2, alpha=0.9, label=etq)
        ax.set_title(titulo, fontsize=9, loc="left")
        ax.set_ylabel(UNIDADES[pol], fontsize=8)
    _dibujar(axs[0], p, "Chile (todas las estaciones)")
    for ax, mz in zip(axs[1:], mzs):
        _dibujar(ax, p[p["macrozona"] == mz], NOMBRE_MZ[mz])
    axs[0].legend(ncols=len(modelos) + 1, fontsize=8, frameon=False,
                  loc="upper right")
    fig.suptitle(f"{NOMBRE_POL[pol]}: series mensuales SINCA ↔ modelos crudos "
                 f"— nacional y macrozonas", fontweight="bold")
    fig.tight_layout()
    return _guardar(fig, f"{pol}_series_nacional_macrozona.png")

def fig_series_region(pol: str) -> Path:
    """Series mensuales SINCA vs modelos crudos por región (grilla)."""
    _c = _fig_cacheada(f"{pol}_series_region.png")
    if _c is not None:
        return _c
    p = construir_panel(pol)
    modelos = _modelos_de(p, pol)
    cols = [c for c, _, _ in modelos]
    regiones = [r for r in ORDEN_REGIONES
                if r in set(p["region_sinca"].dropna().astype(str))]
    ncol = 3
    nfil = int(np.ceil(len(regiones) / ncol))
    fig, axs = plt.subplots(nfil, ncol, figsize=(4.0 * ncol, 1.9 * nfil),
                            sharex=True, squeeze=False)
    ejes = axs.ravel()
    for ax, reg in zip(ejes, regiones):
        sub = p[p["region_sinca"] == reg]
        s = _serie_mensual(sub, cols)
        ax.plot(s.index, s["obs"], color="#222", lw=1.4, label="SINCA")
        for col, etq, c in modelos:
            ax.plot(s.index, s[col], color=c, lw=1.0, alpha=0.9, label=etq)
        r2d = tabla_acuerdo_niveles(pol)
        fila = r2d[(r2d["nivel"] == "region")
                   & (r2d["zona"] == NOMBRE_REGION[reg])]
        extra = f" · R²d {fila['r2_d'].iloc[0]:.2f}" if len(fila) else ""
        ax.set_title(f"{NOMBRE_REGION[reg]} ({sub['estacion'].nunique()} est.)"
                     f"{extra}", fontsize=8)
        ax.tick_params(labelsize=7)
    for ax in ejes[len(regiones):]:
        ax.axis("off")
    ejes[0].legend(fontsize=7, frameon=False, ncols=3)
    fig.suptitle(f"{NOMBRE_POL[pol]}: series mensuales por región — SINCA ↔ "
                 f"modelos crudos", fontweight="bold")
    fig.tight_layout()
    return _guardar(fig, f"{pol}_series_region.png")

def tabla_acuerdo_md(pol: str, nivel: str) -> str:
    """Tabla Markdown del acuerdo crudo para un nivel dado."""
    t = tabla_acuerdo_niveles(pol)
    t = t[t["nivel"] == nivel].drop(columns="nivel").copy()
    t.columns = ["zona", "modelo", "n horario", "R² horario", "RMSE horario",
                 "sesgo horario", "n diario", "R² diario", "RMSE diario",
                 "sesgo diario"]
    if nivel == "nacional":
        t = t.drop(columns="zona")
    return t.round(3).to_markdown(index=False)
# --- 8<: fin descriptivo ---

# --- 8<: niveles ---
# Series mensuales POR NIVEL (nacional / macrozona / región) separadas por
# fuente — primero los modelos globales de satélite+química, después los
# monitores SINCA — y métricas LOSO agregadas por macrozona y región.
# Los promedios mensuales por nivel quedan cacheados en un CSV chico y
# versionable (serie_mensual_<pol>.csv): las figuras se reconstruyen desde
# ese CSV sin necesidad del panel horario completo.

def serie_mensual_niveles(pol: str) -> pd.DataFrame:
    """Medias mensuales de SINCA y de cada modelo físico por nivel.

    Columnas: ``nivel`` (nacional | macrozona | region), ``zona``, ``mes``,
    ``n_est`` y, por cada fuente, la media agrupada del mes (todas las horas
    estación × mes del nivel). Para SINCA se agrega además la banda entre
    estaciones ``obs_p25``/``obs_p75`` (percentiles de las medias mensuales
    por estación). Cacheado en ``serie_mensual_<pol>.csv``."""
    ruta = OUT / f"serie_mensual_{pol}.csv"
    if ruta.exists():
        return pd.read_csv(ruta, parse_dates=["mes"])
    p = construir_panel(pol)
    cols = [c for c, _, _ in _modelos_de(p, pol)]
    p = p.assign(mes=p["ts"].dt.to_period("M").dt.to_timestamp())
    filas = []

    def _bloque(sub, nivel, zona):
        if not len(sub):
            return
        g = sub.groupby("mes", observed=True)
        agg = g[["obs"] + cols].mean()
        n_est = g["estacion"].nunique()
        por_est = (sub.groupby(["mes", "estacion"], observed=True)["obs"]
                   .mean().reset_index())
        q = por_est.groupby("mes")["obs"].quantile([0.25, 0.75]).unstack()
        for mes, fila in agg.iterrows():
            filas.append({
                "nivel": nivel, "zona": zona, "mes": mes,
                "n_est": int(n_est.loc[mes]),
                "obs": fila["obs"],
                "obs_p25": float(q.loc[mes, 0.25]) if mes in q.index else np.nan,
                "obs_p75": float(q.loc[mes, 0.75]) if mes in q.index else np.nan,
                **{c: fila[c] for c in cols}})

    _bloque(p, "nacional", "Chile")
    for mz in ORDEN_MACROZONAS:
        _bloque(p[p["macrozona"] == mz], "macrozona", NOMBRE_MZ[mz])
    for reg in ORDEN_REGIONES:
        _bloque(p[p["region_sinca"].astype(str) == reg], "region",
                NOMBRE_REGION[reg])
    df = pd.DataFrame(filas)
    df.to_csv(ruta, index=False)
    return df

def _modelos_csv(df: pd.DataFrame) -> list[tuple[str, str, str]]:
    """[(columna, etiqueta, color)] de los modelos presentes en el CSV."""
    out = []
    for c in df.columns:
        if c.startswith("gcf_"):
            out.append((c, "GEOS-CF", NARANJO))
        elif c.startswith("cams_"):
            out.append((c, "CAMS EAC4", MORADO))
    return out

def _zonas_nivel(df: pd.DataFrame, nivel: str) -> list[str]:
    orden = {"macrozona": [NOMBRE_MZ[m] for m in ORDEN_MACROZONAS],
             "region": [NOMBRE_REGION[r] for r in ORDEN_REGIONES]}
    presentes = list(df.loc[df["nivel"] == nivel, "zona"].unique())
    if nivel in orden:
        return [z for z in orden[nivel] if z in presentes]
    return presentes

def fig_series_satelites(pol: str) -> Path:
    """Series mensuales según los modelos globales (sin SINCA):
    Chile + macrozonas."""
    nombre = f"{pol}_series_satelites.png"
    _c = _fig_cacheada(nombre)
    if _c is not None:
        return _c
    df = serie_mensual_niveles(pol)
    modelos = _modelos_csv(df)
    paneles = ([("nacional", "Chile")] +
               [("macrozona", z) for z in _zonas_nivel(df, "macrozona")])
    fig, axs = plt.subplots(len(paneles), 1,
                            figsize=(10.5, 2.05 * len(paneles)),
                            sharex=True, squeeze=False)
    for ax, (nivel, zona) in zip(axs[:, 0], paneles):
        s = df[(df["nivel"] == nivel) & (df["zona"] == zona)].sort_values("mes")
        for col, etq, c in modelos:
            ax.plot(s["mes"], s[col], color=c, lw=1.3, label=etq)
        ax.set_title(zona, fontsize=9, loc="left")
        ax.set_ylabel(UNIDADES[pol], fontsize=8)
    axs[0, 0].legend(ncols=len(modelos), fontsize=8, frameon=False,
                     loc="upper right")
    fig.suptitle(f"{NOMBRE_POL[pol]}: series mensuales según los modelos "
                 f"globales de satélite+química — nacional y macrozonas",
                 fontweight="bold")
    fig.tight_layout()
    return _guardar(fig, nombre)

def fig_series_satelites_region(pol: str) -> Path:
    """Series mensuales según los modelos globales por región (grilla)."""
    nombre = f"{pol}_series_satelites_region.png"
    _c = _fig_cacheada(nombre)
    if _c is not None:
        return _c
    df = serie_mensual_niveles(pol)
    modelos = _modelos_csv(df)
    zonas = _zonas_nivel(df, "region")
    ncol = 3
    nfil = int(np.ceil(len(zonas) / ncol))
    fig, axs = plt.subplots(nfil, ncol, figsize=(4.0 * ncol, 1.9 * nfil),
                            sharex=True, squeeze=False)
    ejes = axs.ravel()
    for ax, zona in zip(ejes, zonas):
        s = df[(df["nivel"] == "region") & (df["zona"] == zona)].sort_values("mes")
        for col, etq, c in modelos:
            ax.plot(s["mes"], s[col], color=c, lw=1.0, alpha=0.95, label=etq)
        ax.set_title(zona, fontsize=8)
        ax.tick_params(labelsize=7)
    for ax in ejes[len(zonas):]:
        ax.axis("off")
    ejes[0].legend(fontsize=7, frameon=False, ncols=len(modelos))
    fig.suptitle(f"{NOMBRE_POL[pol]}: series mensuales por región según los "
                 f"modelos globales de satélite+química", fontweight="bold")
    fig.tight_layout()
    return _guardar(fig, nombre)

def fig_series_sinca(pol: str) -> Path:
    """Series mensuales según los monitores SINCA: Chile + macrozonas.
    Línea = media agrupada; banda = p25–p75 entre estaciones."""
    nombre = f"{pol}_series_sinca.png"
    _c = _fig_cacheada(nombre)
    if _c is not None:
        return _c
    df = serie_mensual_niveles(pol)
    paneles = ([("nacional", "Chile")] +
               [("macrozona", z) for z in _zonas_nivel(df, "macrozona")])
    fig, axs = plt.subplots(len(paneles), 1,
                            figsize=(10.5, 2.05 * len(paneles)),
                            sharex=True, squeeze=False)
    for ax, (nivel, zona) in zip(axs[:, 0], paneles):
        s = df[(df["nivel"] == nivel) & (df["zona"] == zona)].sort_values("mes")
        ax.fill_between(s["mes"], s["obs_p25"], s["obs_p75"],
                        color="#777", alpha=0.25, lw=0,
                        label="p25–p75 entre estaciones")
        ax.plot(s["mes"], s["obs"], color="#222", lw=1.6, label="media SINCA")
        n_med = int(np.nanmedian(s["n_est"])) if len(s) else 0
        ax.set_title(f"{zona} · {n_med} estaciones (mediana mensual)",
                     fontsize=9, loc="left")
        ax.set_ylabel(UNIDADES[pol], fontsize=8)
    axs[0, 0].legend(ncols=2, fontsize=8, frameon=False, loc="upper right")
    fig.suptitle(f"{NOMBRE_POL[pol]}: series mensuales según los monitores "
                 f"SINCA — nacional y macrozonas", fontweight="bold")
    fig.tight_layout()
    return _guardar(fig, nombre)

def fig_series_sinca_region(pol: str) -> Path:
    """Series mensuales según los monitores SINCA por región (grilla)."""
    nombre = f"{pol}_series_sinca_region.png"
    _c = _fig_cacheada(nombre)
    if _c is not None:
        return _c
    df = serie_mensual_niveles(pol)
    zonas = _zonas_nivel(df, "region")
    ncol = 3
    nfil = int(np.ceil(len(zonas) / ncol))
    fig, axs = plt.subplots(nfil, ncol, figsize=(4.0 * ncol, 1.9 * nfil),
                            sharex=True, squeeze=False)
    ejes = axs.ravel()
    for ax, zona in zip(ejes, zonas):
        s = df[(df["nivel"] == "region") & (df["zona"] == zona)].sort_values("mes")
        ax.fill_between(s["mes"], s["obs_p25"], s["obs_p75"],
                        color="#777", alpha=0.25, lw=0)
        ax.plot(s["mes"], s["obs"], color="#222", lw=1.1)
        n_med = int(np.nanmedian(s["n_est"])) if len(s) else 0
        ax.set_title(f"{zona} · {n_med} est.", fontsize=8)
        ax.tick_params(labelsize=7)
    for ax in ejes[len(zonas):]:
        ax.axis("off")
    fig.suptitle(f"{NOMBRE_POL[pol]}: series mensuales por región según los "
                 f"monitores SINCA (línea = media; banda = p25–p75 entre "
                 f"estaciones)", fontweight="bold")
    fig.tight_layout()
    return _guardar(fig, nombre)

MOTOR_CORTO = {"fisico": "físico crudo", "gwr": "GWR", "rk": "RK",
               "lgbm": "LGBM"}

def metricas_loso_niveles(pol: str) -> pd.DataFrame:
    """Métricas LOSO por estación agregadas por nivel (mediana e IQR del R²
    por estación, por motor). Fuente: ``r2_estacion_<pol>.csv`` — el artefacto
    chico por estación × motor que escribe ``validar_contaminante`` — más la
    región de cada estación vía ``ESTACIONES``."""
    df = pd.read_csv(OUT / f"r2_estacion_{pol}.csv", dtype={"estacion": str})
    reg = ESTACIONES[["estacion", "region_sinca"]].copy()
    reg["estacion"] = reg["estacion"].astype(str)
    df = df.merge(reg, on="estacion", how="left")
    filas = []

    def _agg(sub, nivel, zona):
        if not len(sub):
            return
        for motor, g in sub.groupby("motor"):
            filas.append({
                "nivel": nivel, "zona": zona, "motor": motor,
                "n_est": g["estacion"].nunique(),
                "r2_mediano": g["r2"].median(),
                "r2_p25": g["r2"].quantile(0.25),
                "r2_p75": g["r2"].quantile(0.75),
                "rmse_mediano": g["rmse"].median(),
                "sesgo_mediano": g["sesgo"].median()})

    _agg(df, "nacional", "Chile")
    for mz in ORDEN_MACROZONAS:
        _agg(df[df["macrozona"] == mz], "macrozona", NOMBRE_MZ[mz])
    for r in ORDEN_REGIONES:
        _agg(df[df["region_sinca"] == r], "region", NOMBRE_REGION[r])
    return pd.DataFrame(filas)

def tabla_metricas_niveles_md(pol: str, nivel: str) -> str:
    """Tabla Markdown: R² LOSO mediano por estación, por motor y zona del
    nivel pedido, con el mejor motor calibrado y su RMSE mediano."""
    t = metricas_loso_niveles(pol)
    t = t[t["nivel"] == nivel]
    if not len(t):
        return "(sin estaciones en este nivel)"
    zonas = ["Chile"] if nivel == "nacional" else _zonas_nivel(t, nivel)
    motores = [m for m in ["fisico", "gwr", "rk", "lgbm"]
               if m in set(t["motor"])]
    ancho = (t.pivot(index="zona", columns="motor", values="r2_mediano")
             .reindex(zonas)[motores])
    n_est = t.groupby("zona")["n_est"].max().reindex(zonas)
    rmse = t.set_index(["zona", "motor"])["rmse_mediano"]
    cal = [m for m in motores if m != "fisico"]
    mejor = ancho[cal].fillna(-9).idxmax(axis=1)
    out = ancho.copy()
    out.insert(0, "estaciones", n_est.astype("Int64"))
    out["mejor motor"] = [MOTOR_CORTO.get(m, m) for m in mejor]
    out["RMSE mediano (mejor)"] = [
        round(float(rmse.get((z, m), np.nan)), 2)
        for z, m in mejor.items()]
    out.columns = (["estaciones"]
                   + [f"R² med. {MOTOR_CORTO.get(m, m)}" for m in motores]
                   + ["mejor motor", "RMSE mediano (mejor)"])
    out.index.name = "zona"
    return out.round(3).to_markdown()
# --- 8<: fin niveles ---

# --- 8<: motores ---
# Tres motores comparables bajo LOSO + el modelo físico crudo como referencia.
#  · GWR   — regresión lineal local ponderada por distancia espacial (kernel
#            gaussiano, ancho de banda adaptativo), vía estadísticos suficientes
#            por estación (X'X, X'y): exacta y barata incluso con panel horario.
#  · LGBM  — gradient boosting (LightGBM) con todas las fuentes + calendario.
#  · RK    — regression-kriging: OLS global + kriging ordinario del residuo
#            medio por estación (variograma exponencial ajustado a los datos).

def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    la1, lo1, la2, lo2 = map(np.radians, [lat1, lon1, lat2, lon2])
    a = (np.sin((la2 - la1) / 2) ** 2
         + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2)
    return 2 * r * np.arcsin(np.sqrt(a))

def diseno_lineal(p: pd.DataFrame, pol: str):
    """Matriz de diseño lineal para GWR/RK: físico + vecinas + meteorología
    (T2M, viento, 1/PBLH — dilución) + calendario. NaN → mediana de columna."""
    cols = [c for c in FISICO[pol] if c in p]
    if pol == "pm25" and "acag_pm25" in p and p["acag_pm25"].notna().mean() > 0.9:
        cols = cols + ["acag_pm25"]
    if "obs_vec" in p:
        cols = cols + ["obs_vec"]
    cols += [c for c in ["T2M", "wind", "inv_pblh"]
             if c in p and p[c].notna().mean() > 0.5]
    Xd = p[cols + ["hora_sin", "hora_cos", "doy_sin", "doy_cos"]].astype(float)
    Xd = Xd.fillna(Xd.median(numeric_only=True))
    X = np.column_stack([np.ones(len(Xd)), Xd.to_numpy(float)])
    y = p["obs"].to_numpy(float)
    ok = np.isfinite(X).all(axis=1) & np.isfinite(y)
    return X, y, ok

def gwr_loso(p: pd.DataFrame, pol: str, k_vecinos: int = 12) -> np.ndarray:
    """Predicción LOSO del motor GWR (out-of-fold para todas las filas)."""
    X, y, ok = diseno_lineal(p, pol)
    est_codes, est_idx = np.unique(p["estacion"].to_numpy(), return_inverse=True)
    n_est, n_col = len(est_codes), X.shape[1]
    XtX = np.zeros((n_est, n_col, n_col)); Xty = np.zeros((n_est, n_col))
    for e in range(n_est):
        m = ok & (est_idx == e)
        Xe, ye = X[m], y[m]
        XtX[e] = Xe.T @ Xe
        Xty[e] = Xe.T @ ye
    coords = (ESTACIONES.set_index("estacion").loc[est_codes, ["lat", "lon"]]
              .to_numpy(float))
    D = haversine_km(coords[:, 0:1], coords[:, 1:2],
                     coords[:, 0], coords[:, 1])
    pred = np.full(len(p), np.nan)
    reg = 1e-6 * np.eye(n_col)
    for e in range(n_est):
        d = np.delete(D[e], e)
        idx = np.delete(np.arange(n_est), e)
        h = np.sort(d)[min(k_vecinos, len(d)) - 1] + 1e-9   # ancho adaptativo
        w = np.exp(-(d / h) ** 2)
        A = np.tensordot(w, XtX[idx], axes=1) + reg
        b = w @ Xty[idx]
        try:
            beta = np.linalg.solve(A, b)
        except np.linalg.LinAlgError:
            beta = np.linalg.lstsq(A, b, rcond=None)[0]
        m = ok & (est_idx == e)
        pred[m] = X[m] @ beta
    return pred

def _variograma_exponencial(dist, gamma):
    """Ajusta γ(h) = c0 + c1·(1 − exp(−h/a)) por mínimos cuadrados simples."""
    from scipy.optimize import least_squares
    c0 = max(np.nanmin(gamma), 1e-9)
    c1 = max(np.nanmax(gamma) - c0, 1e-9)
    a = max(np.nanmedian(dist), 1.0)
    def resid(t):
        return (t[0] + t[1] * (1 - np.exp(-dist / t[2]))) - gamma
    try:
        sol = least_squares(resid, x0=[c0, c1, a],
                            bounds=([0, 1e-12, 1e-3], [np.inf] * 3))
        return sol.x
    except Exception:
        return np.array([c0, c1, a])

def rk_loso(p: pd.DataFrame, pol: str) -> np.ndarray:
    """Regression-kriging LOSO: OLS global + kriging ordinario del residuo
    medio de estación (sesgo espacial persistente)."""
    X, y, ok = diseno_lineal(p, pol)
    est_codes, est_idx = np.unique(p["estacion"].to_numpy(), return_inverse=True)
    n_est, n_col = len(est_codes), X.shape[1]
    XtX = np.zeros((n_est, n_col, n_col)); Xty = np.zeros((n_est, n_col))
    for e in range(n_est):
        m = ok & (est_idx == e)
        XtX[e] = X[m].T @ X[m]
        Xty[e] = X[m].T @ y[m]
    coords = (ESTACIONES.set_index("estacion").loc[est_codes, ["lat", "lon"]]
              .to_numpy(float))
    D = haversine_km(coords[:, 0:1], coords[:, 1:2], coords[:, 0], coords[:, 1])
    pred = np.full(len(p), np.nan)
    reg = 1e-6 * np.eye(n_col)
    for e in range(n_est):
        idx = np.delete(np.arange(n_est), e)
        A = XtX[idx].sum(axis=0) + reg
        b = Xty[idx].sum(axis=0)
        beta = np.linalg.solve(A, b)
        # residuo medio por estación de entrenamiento
        resid_med = np.empty(len(idx))
        for j, ee in enumerate(idx):
            m = ok & (est_idx == ee)
            resid_med[j] = float(np.mean(y[m] - X[m] @ beta)) if m.any() else 0.0
        # variograma empírico sobre pares de estaciones de entrenamiento
        Dt = D[np.ix_(idx, idx)]
        iu = np.triu_indices(len(idx), k=1)
        gamma_emp = 0.5 * (resid_med[iu[0]] - resid_med[iu[1]]) ** 2
        c0, c1, a = _variograma_exponencial(Dt[iu], gamma_emp)
        cov = lambda h: c1 * np.exp(-h / a)                     # noqa: E731
        C = cov(Dt) + np.eye(len(idx)) * (c0 + 1e-9)
        c_vec = cov(D[e, idx])
        # sistema de kriging ordinario
        K = np.zeros((len(idx) + 1, len(idx) + 1))
        K[:-1, :-1] = C; K[-1, :-1] = 1; K[:-1, -1] = 1
        rhs = np.append(c_vec, 1.0)
        try:
            lam = np.linalg.solve(K, rhs)[:-1]
        except np.linalg.LinAlgError:
            lam = np.full(len(idx), 1 / len(idx))
        offset = float(lam @ resid_med)
        m = ok & (est_idx == e)
        pred[m] = X[m] @ beta + offset
    return pred

MET_FEATS = MET_COMUNAL_VARS + ["inv_pblh", "fis_div_pblh", "pm25m2_pblh",
                                "frh", "wind", "aod_div_frh", "aod_maiac"]
ESTATICAS_FEATS = ["frac_urbano", "frac_grassland", "vial_osm", "alt_media",
                   "dist_costa_km"]

def columnas_lgbm(p: pd.DataFrame, pol: str) -> list[str]:
    cols = [c for c in TODAS_FUENTES if c in p and p[c].notna().mean() > 0.5]
    extras = [c for c in ["acag_pm25", "m2_aod", "m2_pm25", "obs_vec",
                          "peso_vec"] if c in p and p[c].notna().mean() > 0.3]
    met = [c for c in MET_FEATS if c in p and p[c].notna().mean() > 0.3]
    estat = [c for c in ESTATICAS_FEATS if c in p and p[c].notna().mean() > 0.3]
    fuentes = [c for c in ["dist_fuente_km", "carga_fuentes_so2",
                           "viento_fuentes_so2"]
               if c in p and p[c].notna().mean() > 0.3]
    # productos por estación de los extractores locales (si existen)
    sat = [c for c in p.columns
           if c.startswith(("s5p_", "omi_", "mop_", "era5_", "aod_maiac_est"))
           and p[c].notna().mean() > 0.3]
    fuentes = fuentes + sat
    cal = ["hora_sin", "hora_cos", "doy_sin", "doy_cos", "dow", "anio",
           "hora_loc", "mes", "lat", "lon"]
    return cols + extras + met + estat + fuentes + cal

LOG_TARGET = os.environ.get("AFG_LOG_TARGET", "1") == "1"

def _params_lgbm(semilla: int) -> dict:
    """Hiperparámetros del gradient boosting: 600 árboles, lr 0.03, 127
    hojas — un ajuste profundo que mantiene los 400+ ajustes LOSO en tiempos
    razonables. Ajustables por entorno (AFG_N_TREES)."""
    return dict(objective="regression", n_estimators=N_ARBOLES,
                learning_rate=0.03, num_leaves=127, min_child_samples=30,
                subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
                n_jobs=os.cpu_count(), random_state=semilla, verbose=-1)

def _ajustar_lgbm(X, y, franja, semilla: int):
    """Ajusta LightGBM (en log1p si LOG_TARGET) y devuelve (modelo, smear),
    con la corrección de retransformación de Duan/Jensen POR FRANJA estimada
    en los residuos de entrenamiento."""
    import lightgbm as lgb
    mod = lgb.LGBMRegressor(**_params_lgbm(semilla))
    if not LOG_TARGET:
        mod.fit(X, y)
        return mod, None
    ylog = np.log1p(np.clip(y, 0, None))
    mod.fit(X, ylog)
    res = ylog - mod.predict(X)
    smear = {f: 0.5 * float(np.var(res[franja == f])) for f in np.unique(franja)}
    smear["_global"] = 0.5 * float(np.var(res))
    return mod, smear

def _predecir_lgbm(mod, smear, X, franja) -> np.ndarray:
    pred = mod.predict(X)
    if smear is None:
        return pred
    adj = np.vectorize(lambda f: smear.get(f, smear["_global"]))(franja)
    return np.expm1(pred + adj)

def lgbm_loso(p: pd.DataFrame, pol: str, semilla: int = SEMILLA):
    """LightGBM con LOSO. Devuelve (pred_oof, importancias_df).

    Para acotar tiempo de cómputo cada ajuste muestrea hasta
    ``MAX_FILAS_TRAIN`` filas de las estaciones de entrenamiento; la
    evaluación usa TODAS las horas de la estación excluida.
    """
    feats = columnas_lgbm(p, pol)
    Xall = p[feats].to_numpy(np.float32)
    yall = p["obs"].to_numpy(np.float32)
    fr = p["franja"].to_numpy()
    est = p["estacion"].to_numpy()
    rng = np.random.default_rng(semilla)
    pred = np.full(len(p), np.nan, dtype=np.float32)
    imp = np.zeros(len(feats))
    estaciones = np.unique(est)
    for i_e, e in enumerate(estaciones):
        if os.environ.get("AFG_VERBOSE") and i_e % 20 == 0:
            print(f"    lgbm fold {i_e + 1}/{len(estaciones)}", flush=True)
        tr = est != e
        idx_tr = np.flatnonzero(tr)
        if len(idx_tr) > MAX_FILAS_TRAIN:
            idx_tr = rng.choice(idx_tr, MAX_FILAS_TRAIN, replace=False)
        mod, smear = _ajustar_lgbm(Xall[idx_tr], yall[idx_tr], fr[idx_tr], semilla)
        te = np.flatnonzero(~tr)
        pred[te] = _predecir_lgbm(mod, smear, Xall[te], fr[te])
        imp += mod.booster_.feature_importance(importance_type="gain")
    importancias = (pd.DataFrame({"variable": feats,
                                  "importancia_gain": imp / len(estaciones)})
                    .sort_values("importancia_gain", ascending=False))
    return pred, importancias
# --- 8<: fin motores ---

# --- 8<: validacion ---
def validar_contaminante(pol: str) -> dict:
    """Corre los 3 motores bajo LOSO para `pol` y cachea OOF + métricas."""
    ruta_oof = OUT / f"oof_{pol}.parquet"
    ruta_met = OUT / f"metricas_cv_{pol}.json"
    ruta_imp = OUT / f"importancias_{pol}.csv"
    if ruta_met.exists():
        return json.loads(ruta_met.read_text())

    p = construir_panel(pol)
    if SMOKE:
        keep = p["estacion"].isin(p["estacion"].unique()[:6])
        p = p[keep].reset_index(drop=True)

    oof = p[["estacion", "ts", "obs", "macrozona"]].copy()
    oof["fisico"] = p[FISICO[pol][0]].to_numpy(float)
    oof["gwr"] = gwr_loso(p, pol)
    oof["rk"] = rk_loso(p, pol)
    pred_lgbm, importancias = lgbm_loso(p, pol)
    oof["lgbm"] = pred_lgbm
    for c in ["fisico", "gwr", "rk", "lgbm"]:
        oof[c] = oof[c].clip(lower=0)          # concentraciones no negativas
    importancias.to_csv(ruta_imp, index=False)
    oof.to_parquet(ruta_oof, index=False)

    res = {"contaminante": pol, "unidad": UNIDADES[pol],
           "n_estaciones": int(p["estacion"].nunique()),
           "n_filas": int(len(p)), "motores": {}}
    for c in ["fisico", "gwr", "rk", "lgbm"]:
        res["motores"][c] = {
            "horario": metricas(oof["obs"].to_numpy(), oof[c].to_numpy()),
            "diario": metricas_diarias(oof, c),
            "por_macrozona": {
                mz: metricas(g["obs"].to_numpy(), g[c].to_numpy())
                for mz, g in oof.groupby("macrozona")},
        }
    ruta_met.write_text(json.dumps(res, indent=1, ensure_ascii=False))
    # tabla de comparación de motores
    filas = []
    for c, r in res["motores"].items():
        filas.append({"motor": c, **{f"h_{k}": v for k, v in r["horario"].items()},
                      **{f"d_{k}": v for k, v in r["diario"].items()}})
    pd.DataFrame(filas).to_csv(OUT / f"comparacion_motores_{pol}.csv", index=False)
    # métricas por estación × motor (artefacto chico versionable: permite
    # re-renderizar mapas/tablas sin el parquet OOF)
    filas_e = []
    for c in ["fisico", "gwr", "rk", "lgbm"]:
        for e, g in oof.groupby("estacion", observed=True):
            met_e = metricas(g["obs"].to_numpy(), g[c].to_numpy())
            filas_e.append({"motor": c, "estacion": e, **met_e})
    (pd.DataFrame(filas_e)
       .merge(ESTACIONES[["estacion", "nombre", "comuna", "lat", "lon",
                          "macrozona"]], on="estacion", how="left")
       .to_csv(OUT / f"r2_estacion_{pol}.csv", index=False))
    return res

def r2_por_estacion(pol: str, motor: str) -> pd.DataFrame:
    """Métricas por estación del OOF. Si el parquet OOF no está (p. ej. solo
    se tienen los artefactos chicos versionados), usa el CSV
    ``r2_estacion_<pol>.csv`` que escribe validar_contaminante."""
    ruta_oof = OUT / f"oof_{pol}.parquet"
    ruta_csv = OUT / f"r2_estacion_{pol}.csv"
    if not ruta_oof.exists() and ruta_csv.exists():
        df = pd.read_csv(ruta_csv, dtype={"estacion": str})
        return df[df["motor"] == motor].drop(columns="motor")
    oof = pd.read_parquet(ruta_oof)
    filas = []
    for e, g in oof.groupby("estacion", observed=True):
        met = metricas(g["obs"].to_numpy(), g[motor].to_numpy())
        filas.append({"estacion": e, **met})
    df = pd.DataFrame(filas).merge(
        ESTACIONES[["estacion", "nombre", "comuna", "lat", "lon", "macrozona"]],
        on="estacion", how="left")
    return df

def mejor_motor(res: dict) -> str:
    """Motor con mejor R² horario (entre los calibrados, no el físico crudo)."""
    cand = {m: v["horario"]["r2"] for m, v in res["motores"].items()
            if m != "fisico"}
    return max(cand, key=lambda m: (cand[m] if np.isfinite(cand[m]) else -9))

def tabla_motores_md(pol: str) -> str:
    """Tabla de comparación de motores en Markdown (para el sitio)."""
    df = pd.read_csv(OUT / f"comparacion_motores_{pol}.csv").set_index("motor")
    df = df[["h_r2", "h_rmse", "h_mae", "h_sesgo", "d_r2", "d_rmse"]]
    df.columns = ["R² horario", "RMSE h", "MAE h", "sesgo h",
                  "R² diario", "RMSE d"]
    df.index = [NOMBRE_MOTOR.get(m, m) for m in df.index]
    df.index.name = "motor"
    return df.round(3).to_markdown()
# --- 8<: fin validacion ---

# --- 8<: figuras ---
def fig_comparacion(pol: str, res: dict) -> Path:
    _c = _fig_cacheada(f"{pol}_comparacion_motores.png")
    if _c is not None:
        return _c
    motores = ["fisico", "gwr", "rk", "lgbm"]
    r2h = [res["motores"][m]["horario"]["r2"] for m in motores]
    r2d = [res["motores"][m]["diario"]["r2"] for m in motores]
    x = np.arange(len(motores)); ancho = 0.38
    fig, ax = plt.subplots(figsize=(7, 4))
    b1 = ax.bar(x - ancho / 2, np.clip(r2h, 0, None), ancho,
                label="horario", color=[COLOR_MOTOR[m] for m in motores])
    b2 = ax.bar(x + ancho / 2, np.clip(r2d, 0, None), ancho,
                label="diario", color=[COLOR_MOTOR[m] for m in motores],
                alpha=0.55, hatch="//")
    for bars, vals in [(b1, r2h), (b2, r2d)]:
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, max(v, 0) + 0.012,
                    f"{v:.2f}", ha="center", fontsize=9)
    ax.set_xticks(x, [NOMBRE_MOTOR[m] for m in motores])
    ax.set_ylim(0, 1); ax.set_ylabel("R² (LOSO)")
    mm = mejor_motor(res)
    ax.set_title(f"{NOMBRE_POL[pol]}: {NOMBRE_MOTOR[mm]} lidera con "
                 f"R² horario {res['motores'][mm]['horario']['r2']:.2f} "
                 f"(diario {res['motores'][mm]['diario']['r2']:.2f})")
    ax.legend(title="resolución", frameon=False)
    return _guardar(fig, f"{pol}_comparacion_motores.png")

def fig_dispersion(pol: str, res: dict) -> Path:
    _c = _fig_cacheada(f"{pol}_dispersion.png")
    if _c is not None:
        return _c
    oof = pd.read_parquet(OUT / f"oof_{pol}.parquet")
    mm = mejor_motor(res)
    fig, axs = plt.subplots(1, 2, figsize=(10.5, 4.6), sharex=True, sharey=True)
    lim = float(np.nanquantile(oof["obs"], 0.999))
    for ax, m in zip(axs, ["fisico", mm]):
        d = oof[["obs", m]].dropna()
        hb = ax.hexbin(d["obs"], d[m], gridsize=60, bins="log",
                       cmap="viridis", extent=(0, lim, 0, lim))
        ax.plot([0, lim], [0, lim], color=ROJO, lw=1.2, ls="--")
        met = res["motores"][m]["horario"]
        ax.set_title(f"{NOMBRE_MOTOR[m]} — R² {met['r2']:.2f} · "
                     f"RMSE {met['rmse']:.1f}")
        ax.set_xlabel(f"Observado SINCA ({UNIDADES[pol]})")
    axs[0].set_ylabel(f"Predicho ({UNIDADES[pol]})")
    fig.colorbar(hb, ax=axs, label="n (escala log)", shrink=0.85)
    fig.suptitle(f"{NOMBRE_POL[pol]} horario: del modelo físico crudo al motor "
                 f"calibrado (LOSO)", fontweight="bold", y=1.04)
    return _guardar(fig, f"{pol}_dispersion.png")

def fig_mapa_r2(pol: str, res: dict) -> Path:
    _c = _fig_cacheada(f"{pol}_mapa_r2.png")
    if _c is not None:
        return _c
    mm = mejor_motor(res)
    df = r2_por_estacion(pol, mm).dropna(subset=["r2"])
    fig, ax = plt.subplots(figsize=(8.6, 8.2))
    sc = ax.scatter(df["lon"], df["lat"], c=df["r2"].clip(0, 1), s=60,
                    cmap="RdYlGn", vmin=0, vmax=1, edgecolor="k", lw=0.4)
    ax.set_aspect("auto")           # eje x estirado: prima la legibilidad
    lon_min, lon_max = df["lon"].min(), df["lon"].max()
    ax.set_xlim(lon_min - 0.8, lon_max + 2.2)
    ax.set_xlabel("Longitud"); ax.set_ylabel("Latitud")
    peor = df.nsmallest(3, "r2")
    for _, r in peor.iterrows():
        ax.annotate(r["nombre"], (r["lon"], r["lat"]), fontsize=8,
                    xytext=(6, 0), textcoords="offset points")
    fig.colorbar(sc, label=f"R² horario por estación ({NOMBRE_MOTOR[mm]})",
                 shrink=0.9)
    ax.set_title(f"{NOMBRE_POL[pol]}: habilidad temporal dentro de "
                 f"cada estación (LOSO) — mediana {df['r2'].median():.2f}")
    return _guardar(fig, f"{pol}_mapa_r2.png")

def fig_serie(pol: str, res: dict) -> Path:
    _c = _fig_cacheada(f"{pol}_serie.png")
    if _c is not None:
        return _c
    mm = mejor_motor(res)
    df = r2_por_estacion(pol, mm).dropna(subset=["r2"])
    oof = pd.read_parquet(OUT / f"oof_{pol}.parquet")
    mejor = df.loc[df["r2"].idxmax()]
    mediana = df.iloc[(df["r2"] - df["r2"].median()).abs().idxmin()]
    fig, axs = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
    for ax, fila in zip(axs, [mejor, mediana]):
        g = oof[oof["estacion"] == fila["estacion"]].assign(
            dia=lambda d: d["ts"].dt.floor("D"))
        d = g.groupby("dia")[["obs", mm]].mean()
        ax.plot(d.index, d["obs"], color="#444", lw=0.9, label="SINCA (obs.)")
        ax.plot(d.index, d[mm], color=COLOR_MOTOR[mm], lw=0.9, alpha=0.9,
                label=f"{NOMBRE_MOTOR[mm]} (LOSO)")
        ax.set_ylabel(f"{NOMBRE_POL[pol]} ({UNIDADES[pol]})")
        ax.set_title(f"{fila['nombre']} ({fila['comuna']}) — "
                     f"R² horario {fila['r2']:.2f}", fontsize=10)
    axs[0].legend(frameon=False, ncols=2)
    fig.suptitle(f"{NOMBRE_POL[pol]}: medias diarias, estación mejor y mediana "
                 f"(la estación se predice sin usar sus datos)",
                 fontweight="bold")
    return _guardar(fig, f"{pol}_serie.png")

# Nombres legibles y fuente de datos de cada variable del boosting.
_VAR_LEGIBLE = {
    "acag_pm25": ("PM₂.₅ satelital anual · ACAG", "sat"),
    "aod_maiac": ("AOD satelital · MAIAC", "sat"),
    "m2_aod": ("AOD por estación · MERRA-2", "met"),
    "m2_pm25": ("PM₂.₅ de reanálisis (estación) · MERRA-2", "met"),
    "obs_vec": ("Observación de estaciones vecinas (IDW)", "red"),
    "peso_vec": ("Peso del vecindario informante", "red"),
    "T2M": ("Temperatura 2 m · MERRA-2", "met"),
    "RH2M": ("Humedad relativa 2 m · MERRA-2", "met"),
    "U10M": ("Viento zonal 10 m · MERRA-2", "met"),
    "V10M": ("Viento meridional 10 m · MERRA-2", "met"),
    "PS": ("Presión superficial · MERRA-2", "met"),
    "PBLH": ("Altura de la capa límite · MERRA-2", "met"),
    "AOD_M2": ("AOD de reanálisis · MERRA-2", "met"),
    "PM25_M2": ("PM₂.₅ de reanálisis · MERRA-2", "met"),
    "inv_pblh": ("Inverso de la capa límite (1/PBLH)", "fis"),
    "fis_div_pblh": ("Dilución modelo físico / capa límite", "fis"),
    "pm25m2_pblh": ("Dilución PM₂.₅-MERRA2 / capa límite", "fis"),
    "frh": ("Crecimiento higroscópico f(RH)", "fis"),
    "wind": ("Rapidez del viento", "fis"),
    "aod_div_frh": ("AOD / higroscopía", "fis"),
    "frac_urbano": ("Fracción de suelo urbano", "terr"),
    "frac_grassland": ("Fracción de pastizal", "terr"),
    "vial_osm": ("Densidad de red vial", "terr"),
    "alt_media": ("Altitud media", "terr"),
    "dist_costa_km": ("Distancia a la costa", "terr"),
    "lat": ("Latitud", "terr"),
    "lon": ("Longitud", "terr"),
    "hora_sin": ("Hora (componente seno)", "cal"),
    "hora_cos": ("Hora (componente coseno)", "cal"),
    "doy_sin": ("Día del año (componente seno)", "cal"),
    "doy_cos": ("Día del año (componente coseno)", "cal"),
    "dow": ("Día de la semana", "cal"),
    "anio": ("Año", "cal"),
    "hora_loc": ("Hora del día", "cal"),
    "mes": ("Mes del año", "cal"),
    "dist_fuente_km": ("Distancia a la megafuente SO₂ más cercana", "fpun"),
    "carga_fuentes_so2": ("Carga de fuentes SO₂ (Σ emisión/d²)", "fpun"),
    "viento_fuentes_so2": ("Viento desde fuentes SO₂ (alineación)", "fpun"),
}
GRUPO_FUENTE = {
    "gcf": ("GEOS-CF (satélite+química)", AZUL),
    "cams": ("CAMS EAC4 (satélite+química)", "#64B5CD"),
    "sat": ("Satélite (ACAG / MAIAC)", NARANJO),
    "met": ("Meteorología MERRA-2", VERDE),
    "fis": ("Derivadas físicas", "#1B7837"),
    "red": ("Red SINCA (vecinas)", "#555555"),
    "terr": ("Territorio", MORADO),
    "cal": ("Tiempo/calendario", ROJO),
    "fpun": ("Fuentes puntuales SO₂", "#8c510a"),
    "otro": ("Otras", "#999999"),
}

def _etiqueta_var(v: str) -> tuple[str, str]:
    """(nombre legible, grupo de fuente) de una variable del boosting."""
    if v in _VAR_LEGIBLE:
        return _VAR_LEGIBLE[v]
    _PREFIJOS = {
        "s5p_": ("columna · TROPOMI", "sat"), "omi_": ("columna · OMI", "sat"),
        "mop_": ("· MOPITT", "sat"), "era5_": ("· ERA5-Land", "met"),
    }
    _GAS = {"no2": "NO₂", "so2": "SO₂", "co": "CO", "o3": "O₃",
            "hcho": "HCHO", "co_sup": "CO superficie", "co_col": "CO columna",
            "t2m": "Temperatura 2 m", "d2m": "Punto de rocío 2 m",
            "rh": "Humedad relativa", "u10": "Viento zonal 10 m",
            "v10": "Viento meridional 10 m", "sp": "Presión superficial",
            "tp": "Precipitación", "blh": "Altura de capa límite"}
    if v == "aod_maiac_est":
        return ("AOD MAIAC 1 km por estación", "sat")
    for pref, (sufijo, grupo) in _PREFIJOS.items():
        if v.startswith(pref):
            clave = v[len(pref):]
            return (f"{_GAS.get(clave, clave.upper())} {sufijo}", grupo)
    if v.startswith("gcf_"):
        return (f"{NOMBRE_POL_TXT.get(v[4:], v[4:].upper())} · GEOS-CF", "gcf")
    if v.startswith("cams_"):
        return (f"{NOMBRE_POL_TXT.get(v[5:], v[5:].upper())} · CAMS EAC4", "cams")
    return (v, "otro")

def fig_importancias(pol: str) -> Path:
    """Importancia (ganancia) de TODAS las variables del LightGBM, con
    nombres legibles y barras coloreadas por fuente de datos."""
    _c = _fig_cacheada(f"{pol}_importancias.png")
    if _c is not None:
        return _c
    from matplotlib.patches import Patch
    imp = pd.read_csv(OUT / f"importancias_{pol}.csv")
    imp["pct"] = 100 * imp["importancia_gain"] / imp["importancia_gain"].sum()
    imp = imp.sort_values("importancia_gain", ascending=True).reset_index(drop=True)
    pares = [_etiqueta_var(v) for v in imp["variable"]]
    etiquetas = [e for e, _ in pares]
    grupos = [g for _, g in pares]
    colores = [GRUPO_FUENTE[g][1] for g in grupos]
    alto = max(5.0, 0.27 * len(imp) + 1.7)
    fig, ax = plt.subplots(figsize=(9.6, alto))
    ax.barh(np.arange(len(imp)), imp["pct"], color=colores)
    ax.set_yticks(np.arange(len(imp)), etiquetas, fontsize=8)
    ax.margins(y=0.012)
    ax.set_xlabel("Importancia (% de la ganancia total, media entre folds LOSO)")
    ax.set_title(f"{NOMBRE_POL[pol]} · LightGBM: importancia de todas las "
                 f"variables, por fuente de datos", fontsize=11)
    orden_leyenda = ["gcf", "cams", "sat", "met", "fis", "red", "fpun",
                     "terr", "cal"]
    presentes = [Patch(color=GRUPO_FUENTE[g][1], label=GRUPO_FUENTE[g][0])
                 for g in orden_leyenda if g in set(grupos)]
    ax.legend(handles=presentes, loc="lower right", fontsize=8, frameon=True,
              title="Fuente de datos", title_fontsize=8)
    return _guardar(fig, f"{pol}_importancias.png")

def fig_resumen(resultados: dict) -> Path:
    _c = _fig_cacheada("resumen_r2_motores.png")
    if _c is not None:
        return _c
    pols = list(resultados)
    motores = ["fisico", "gwr", "rk", "lgbm"]
    M = np.array([[resultados[p]["motores"][m]["horario"]["r2"]
                   for m in motores] for p in pols], dtype=float)
    D = np.array([[resultados[p]["motores"][m]["diario"]["r2"]
                   for m in motores] for p in pols], dtype=float)
    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    im = ax.imshow(np.clip(M, 0, 1), cmap="YlGnBu", vmin=0, vmax=1,
                   aspect="auto")
    for i in range(len(pols)):
        for j in range(len(motores)):
            ax.text(j, i, f"{M[i, j]:.2f}\n({D[i, j]:.2f})", ha="center",
                    va="center", fontsize=9,
                    color="white" if M[i, j] > 0.6 else "#222")
    ax.set_xticks(range(len(motores)), [NOMBRE_MOTOR[m] for m in motores])
    ax.set_yticks(range(len(pols)), [NOMBRE_POL[p] for p in pols])
    ax.grid(False)
    ax.set_title("R² LOSO horario (y diario) por contaminante y motor")
    fig.colorbar(im, label="R² horario")
    return _guardar(fig, "resumen_r2_motores.png")
# --- 8<: fin figuras ---

# --- 8<: producto ---
# "Protocolo del producto": r² de Pearson del PRODUCTO FINAL a escala DIARIA
# contra SINCA, con las estaciones dentro del entrenamiento. Mide la calidad
# de ajuste del producto donde hay monitor — la pregunta complementaria a la
# validación fuera-de-estación (LOSO) de la sección anterior.

def protocolo_producto(pol: str) -> dict:
    """Entrena el LGBM final con TODAS las estaciones, evalúa el acuerdo
    diario in-situ (protocolo del producto) y cachea métricas + pares."""
    ruta_met = OUT / f"metricas_producto_{pol}.json"
    ruta_par = OUT / f"producto_diario_{pol}.parquet"
    if ruta_met.exists():
        return json.loads(ruta_met.read_text())
    p = construir_panel(pol)
    feats = columnas_lgbm(p, pol)
    X = p[feats].to_numpy(np.float32)
    y = p["obs"].to_numpy(np.float32)
    fr = p["franja"].to_numpy()
    rng = np.random.default_rng(SEMILLA)
    idx = np.arange(len(p))
    if len(idx) > 2 * MAX_FILAS_TRAIN:          # ajuste final con más filas
        idx = rng.choice(idx, 2 * MAX_FILAS_TRAIN, replace=False)
    mod, smear = _ajustar_lgbm(X[idx], y[idx], fr[idx], SEMILLA)
    pred = np.clip(_predecir_lgbm(mod, smear, X, fr), 0, None)
    d = (p.assign(pred=pred, dia=p["ts"].dt.floor("D"))
         .groupby(["estacion", "dia"], observed=True)[["obs", "pred"]]
         .mean().dropna().reset_index())
    o, q = d["obs"].to_numpy(float), d["pred"].to_numpy(float)
    b, a = np.polyfit(o, q, 1)
    res = {
        "contaminante": pol, "n_dias": int(len(d)),
        "r2_pearson": round(float(np.corrcoef(o, q)[0, 1] ** 2), 4),
        "r2_clasico": round(float(1 - np.sum((q - o) ** 2)
                                  / np.sum((o - o.mean()) ** 2)), 4),
        "rmse": round(float(np.sqrt(np.mean((q - o) ** 2))), 3),
        "ols_a": round(float(a), 3), "ols_b": round(float(b), 3),
        "m_origen": round(float(np.sum(o * q) / np.sum(o * o)), 3),
    }
    d.to_parquet(ruta_par, index=False)
    ruta_met.write_text(json.dumps(res, indent=1, ensure_ascii=False))
    return res

def fig_protocolo(pol: str, res: dict) -> Path:
    _c = _fig_cacheada(f"{pol}_protocolo_producto.png")
    if _c is not None:
        return _c
    """Dispersión diaria estilo 'producto' (como paper_scatter_dia_nac del
    repo neuro): x=y, guías factor-2 y caja de estadísticas."""
    d = pd.read_parquet(OUT / f"producto_diario_{pol}.parquet")
    lim = float(np.nanquantile(pd.concat([d["obs"], d["pred"]]), 0.999))
    fig, ax = plt.subplots(figsize=(6.4, 6))
    hb = ax.hexbin(d["obs"], d["pred"], gridsize=70, bins="log",
                   cmap="turbo", extent=(0, lim, 0, lim))
    ax.plot([0, lim], [0, lim], color="k", lw=1.4, label="x = y")
    ax.plot([0, lim / 2], [0, lim], color="#33658a", lw=1, ls="--", label="y = 2x")
    ax.plot([0, lim], [0, lim / 2], color="#33658a", lw=1, ls=":", label="y = x/2")
    ax.set_xlim(0, lim); ax.set_ylim(0, lim); ax.set_aspect("equal")
    ax.set_xlabel(f"{NOMBRE_POL[pol]} observado SINCA ({UNIDADES[pol]})")
    ax.set_ylabel(f"{NOMBRE_POL[pol]} modelo ({UNIDADES[pol]})")
    caja = (f"N = {res['n_dias']:,}\nr² = {res['r2_pearson']:.2f}"
            f"\nR² = {res['r2_clasico']:.2f}"
            f"\nRMSE = {res['rmse']:.1f} {UNIDADES[pol]}"
            f"\ny = {res['ols_a']:.2f} + {res['ols_b']:.2f}·x"
            f"\nm = {res['m_origen']:.2f}")
    ax.text(0.03, 0.97, caja, transform=ax.transAxes, va="top", fontsize=9,
            bbox=dict(boxstyle="round", fc="white", ec="#999", alpha=0.9))
    ax.legend(loc="lower right", fontsize=8, frameon=True)
    ax.set_title(f"{NOMBRE_POL[pol]}: acuerdo diario del producto final\n"
                 f"(modelo entrenado con todas las estaciones)", fontsize=10)
    fig.colorbar(hb, label="n (escala log)", shrink=0.8)
    return _guardar(fig, f"{pol}_protocolo_producto.png")
# --- 8<: fin producto ---
