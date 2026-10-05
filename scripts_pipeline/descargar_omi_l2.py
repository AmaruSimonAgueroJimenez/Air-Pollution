#!/usr/bin/env python3
"""OMI L2 v004 a maxima resolucion instrumental (pixel x pasada).

Descarga OMNO2/OMSO2/OMTO3 granulo por granulo, conserva el tiempo TAI93 por
scanline, todos los pixeles cuya huella o centro toca Chile y los campos de
calidad/incertidumbre necesarios para modelar NO2, SO2 y O3. No agrega por
hora, dia ni comuna. Cada Parquet ZSTD se reabre y valida antes de eliminar el
HDF; INT/TERM/fallos retiran exclusivamente crudos y ``.part`` temporales.

OMNO2 y OMSO2 publican corners nativos. OMTO3 v004 no los incluye: para poder
decidir interseccion de borde se infieren vertices desde los centros vecinos
del mismo swath y se marca ``huella_fuente=centros_swath_inferida``.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
import uuid
from datetime import date, datetime, time as dt_time, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _chile_aoi import derivar  # noqa: E402
from _common import CONTAMINANTES, DATA, get_logger  # noqa: E402
from _env_earthdata import login  # noqa: E402
from _l2_swath import (  # noqa: E402
    MascaraHuellasChile,
    agregar_esquinas,
    campo,
    detalles_runtime,
    esquinas_desde_centros,
    expandir_scanline,
    tai93_a_utc,
)
from _satellite_streaming import (  # noqa: E402
    AreaTrabajo,
    BloqueoProceso,
    Manifiesto,
    anotar_checksums_descargados,
    cargar_comunas,
    deduplicar_granulos,
    describir_granulos,
    escribir_json_atomico,
    escribir_parquet_atomico,
    fechas_inclusivas,
    limpiar_parciales,
    requerir_modulos,
    salida_diaria,
    sha256_archivo,
    validar_parquet,
)

log = get_logger("omi_l2_pixeles")

BASE = CONTAMINANTES / "OMI_L2"
TRABAJO = BASE / "_trabajo_descarga"
SALIDA = BASE / "pixeles_pasada"
AUDITORIA = BASE / "manifiestos_pixeles_pasada"
MANIFIESTO = BASE / "manifest_pixeles_pasada.csv"
SHP = DATA / "comunas.shp"
INICIO = date(2004, 10, 1)

COMUNES = (
    "pixel_id", "observation_id", "granulo", "producto", "coleccion",
    "ts_utc", "fecha_utc", "hora_utc", "minuto_utc", "segundo_utc",
    "time_tai93", "seconds_in_day_native", "scanline", "cross_track",
    "lat", "lon", "corner0_lat", "corner0_lon", "corner1_lat",
    "corner1_lon", "corner2_lat", "corner2_lon", "corner3_lat",
    "corner3_lon", "huella_fuente", "cod_comuna", "etiqueta_comuna",
    "cod_comunas_huella", "comunas_huella", "n_comunas_huella",
    "criterio_inclusion", "territorio", "valor_objetivo_valido",
)

# (columna salida, grupo, SDS, entero). Se preservan QA crudos: el pipeline no
# impone un filtro cientifico irreversible y permite reproducir filtros futuros.
PRODUCTOS = {
    "no2": {
        "short": "OMNO2", "version": "004", "swath": "ColumnAmountNO2",
        "codigo": 1, "objetivo": "no2_trop_molec_cm2",
        "corners": ("FoV75CornerLatitude", "FoV75CornerLongitude"),
        "seconds": "deltaTime", "seconds_group": "geo",
        "variables": (
            ("no2_trop_molec_cm2", "data", "ColumnAmountNO2Trop", False),
            ("no2_trop_std_molec_cm2", "data", "ColumnAmountNO2TropStd", False),
            ("no2_total_molec_cm2", "data", "ColumnAmountNO2", False),
            ("no2_total_std_molec_cm2", "data", "ColumnAmountNO2Std", False),
            ("no2_strat_molec_cm2", "data", "ColumnAmountNO2Strat", False),
            ("no2_strat_std_molec_cm2", "data", "ColumnAmountNO2StratStd", False),
            ("no2_slant_molec_cm2", "data", "SlantColumnAmountNO2", False),
            ("no2_slant_std_molec_cm2", "data", "SlantColumnAmountNO2Std", False),
            ("amf_trop", "data", "AmfTrop", False),
            ("amf_trop_std", "data", "AmfTropStd", False),
            ("cloud_fraction", "data", "CloudFraction", False),
            ("cloud_pressure_hpa", "data", "CloudPressure", False),
            ("terrain_pressure_hpa", "data", "TerrainPressure", False),
            ("terrain_height_m", "data", "TerrainHeight", False),
            ("tropopause_pressure_hpa", "data", "TropopausePressure", False),
            ("solar_zenith_deg", "geo", "SolarZenithAngle", False),
            ("viewing_zenith_deg", "geo", "ViewingZenithAngle", False),
            ("vcd_quality_flags", "data", "VcdQualityFlags", True),
            ("xtrack_quality_flags", "data", "XTrackQualityFlagsModified", True),
            ("algorithm_flags", "data", "AlgorithmFlags", True),
            ("amf_quality_flags", "data", "AMFQualityFlags", True),
            ("measurement_quality_flags", "data", "MeasurementQualityFlags", True),
        ),
    },
    "so2": {
        "short": "OMSO2", "version": "004",
        "swath": "OMI Total Column Amount SO2", "codigo": 2,
        "objetivo": "so2_pbl_du",
        "corners": ("TiledCornerLatitude", "TiledCornerLongitude"),
        "seconds": "SecondsInDay", "seconds_group": "geo",
        "variables": (
            ("so2_pbl_du", "data", "ColumnAmountSO2_PBL", False),
            ("so2_stl_du", "data", "ColumnAmountSO2_STL", False),
            ("so2_trl_du", "data", "ColumnAmountSO2_TRL", False),
            ("so2_trm_du", "data", "ColumnAmountSO2_TRM", False),
            ("so2_tru_du", "data", "ColumnAmountSO2_TRU", False),
            ("so2_column_du", "data", "ColumnAmountSO2", False),
            ("so2_slant_du", "data", "SlantColumnAmountSO2", False),
            ("fitting_rms", "data", "RootMeanSquareFittingResiduals", False),
            ("cloud_fraction", "data", "CloudFraction", False),
            ("cloud_pressure_hpa", "data", "CloudPressure", False),
            ("radiative_cloud_fraction", "data", "RadiativeCloudFraction", False),
            ("o3_column_du", "data", "ColumnAmountO3", False),
            ("terrain_pressure_hpa", "data", "TerrainPressure", False),
            ("terrain_height_m", "geo", "TerrainHeight", False),
            ("surface_reflectivity", "data", "SurfaceReflectivity", False),
            ("solar_zenith_deg", "geo", "SolarZenithAngle", False),
            ("viewing_zenith_deg", "geo", "ViewingZenithAngle", False),
            ("ground_pixel_quality_flags", "geo", "GroundPixelQualityFlags", True),
            ("row_anomaly_flag", "data", "Flag_RowAnomaly", True),
            ("saa_flag", "data", "Flag_SAA", True),
            ("snow_ice_flag", "data", "AlgorithmFlag_SnowIce", True),
        ),
    },
    "o3": {
        "short": "OMTO3", "version": "004",
        "swath": "OMI Column Amount O3", "codigo": 3,
        "objetivo": "o3_total_du", "corners": None,
        "seconds": "SecondsInDay", "seconds_group": "geo",
        "variables": (
            ("o3_total_du", "data", "ColumnAmountO3", False),
            ("o3_step1_du", "data", "StepOneO3", False),
            ("o3_step2_du", "data", "StepTwoO3", False),
            ("o3_below_cloud_du", "data", "O3BelowCloud", False),
            ("cloud_pressure_hpa", "data", "CloudPressure", False),
            ("radiative_cloud_fraction", "data", "RadiativeCloudFraction", False),
            ("reflectivity_331_pct", "data", "Reflectivity331", False),
            ("reflectivity_360_pct", "data", "Reflectivity360", False),
            ("uv_aerosol_index", "data", "UVAerosolIndex", False),
            ("so2_index", "data", "SO2index", False),
            ("terrain_pressure_hpa", "data", "TerrainPressure", False),
            ("terrain_height_m", "geo", "TerrainHeight", False),
            ("solar_zenith_deg", "geo", "SolarZenithAngle", False),
            ("viewing_zenith_deg", "geo", "ViewingZenithAngle", False),
            ("water_fraction_pct", "geo", "WaterFraction", False),
            ("quality_flags", "data", "QualityFlags", True),
            ("algorithm_flags", "data", "AlgorithmFlags", True),
            ("ground_pixel_quality_flags", "geo", "GroundPixelQualityFlags", True),
            ("xtrack_quality_flags", "geo", "XTrackQualityFlags", True),
            ("measurement_quality_flags", "data", "MeasurementQualityFlags", True),
            ("instrument_configuration_id", "data", "InstrumentConfigurationId", True),
        ),
    },
}


def _columnas(pol: str) -> tuple[str, ...]:
    return COMUNES + tuple(x[0] for x in PRODUCTOS[pol]["variables"])


def _con_reintentos(descripcion, funcion, intentos: int = 6):
    ultimo = None
    for k in range(1, intentos + 1):
        try:
            return funcion()
        except Exception as exc:
            ultimo = exc
            if k == intentos:
                break
            espera = 10 * k
            log.warning("%s fallo (%s); reintento %d/%d en %ds",
                        descripcion, type(exc).__name__, k, intentos, espera)
            time.sleep(espera)
    raise ultimo


def _buscar(earthaccess, cfg: dict, dia: date, aois) -> list:
    inicio = datetime.combine(dia, dt_time.min)
    fin = datetime.combine(dia, dt_time.max)
    resultados = []
    for aoi in aois:
        resultados.extend(_con_reintentos(
            f"CMR {cfg['short']} {dia} {aoi.id}",
            lambda aoi=aoi: earthaccess.search_data(
                short_name=cfg["short"], version=cfg["version"],
                bounding_box=aoi.bbox, temporal=(inicio, fin),
            ),
        ))
    return deduplicar_granulos(resultados)


def _url(g) -> str:
    try:
        return str(g.data_links()[0])
    except Exception:
        return ""


def _nombre(g) -> str:
    return Path(_url(g).split("?", 1)[0]).name


def _id_estable(nombre: str) -> str:
    m = re.search(
        r"(OMI-Aura_L2-[A-Za-z0-9]+_\d{4}m\d{4}t\d{4}-o\d+_v\d+)",
        nombre,
    )
    if not m:
        raise ValueError(f"nombre OMI L2 no reconocido: {nombre}")
    return m.group(1)


def _fecha_nombre(nombre: str) -> str:
    m = re.search(r"_(\d{4})m(\d{2})(\d{2})t", nombre)
    if not m:
        raise ValueError(f"fecha ausente en {nombre}")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def _orbita(nombre: str) -> int:
    m = re.search(r"-o(\d+)_", nombre)
    if not m:
        raise ValueError(f"orbita ausente en {nombre}")
    return int(m.group(1))


def _destino(pol: str, nombre: str) -> Path:
    fecha = _fecha_nombre(nombre)
    return salida_diaria(
        SALIDA / pol, fecha, _id_estable(nombre).lower(),
    )


def _audit_path(pol: str, nombre: str) -> Path:
    fecha = _fecha_nombre(nombre)
    return salida_diaria(
        AUDITORIA / pol, fecha, _id_estable(nombre).lower(),
    ).with_suffix(".json")


def _day_path(pol: str, fecha: str) -> Path:
    return salida_diaria(
        AUDITORIA / pol / "_dias", fecha,
        f"omi_l2_{pol}_{fecha.replace('-', '')}",
    ).with_suffix(".json")


def _extraer(arr: np.ndarray, forma: tuple[int, int], posiciones,
             entero: bool):
    arr = np.asarray(arr)
    if arr.shape != forma:
        arr = expandir_scanline(arr, forma)
    valores = arr.reshape(-1)[np.asarray(posiciones, dtype=np.int64)]
    return valores.astype(np.int32 if entero else np.float32)


def _validar_tiempo(tai_scan, seconds_scan, utc_scan) -> None:
    if seconds_scan is None:
        return
    segundos = np.asarray(seconds_scan, dtype=np.float64).reshape(-1)
    utc = pd.DatetimeIndex(utc_scan)
    utc_sid = (utc.hour * 3600 + utc.minute * 60 + utc.second
               + utc.microsecond / 1_000_000.0)
    diferencia = np.abs(((utc_sid - segundos + 43200.0) % 86400.0) - 43200.0)
    validos = np.isfinite(segundos) & ~pd.isna(utc)
    if validos.any() and np.nanmax(diferencia[validos]) > 1.1:
        raise ValueError(
            "conversion TAI93 discrepa de SecondsInDay/deltaTime nativo"
        )


def _leer(path: Path, pol: str, mascara: MascaraHuellasChile) -> pd.DataFrame:
    import h5py

    cfg = PRODUCTOS[pol]
    with h5py.File(path, "r") as h:
        swath = h[f"HDFEOS/SWATHS/{cfg['swath']}"]
        geo, data = swath["Geolocation Fields"], swath["Data Fields"]
        lat = campo(geo, "Latitude")
        lon = campo(geo, "Longitude")
        if lat.ndim != 2 or lon.shape != lat.shape:
            raise ValueError(f"geolocalizacion OMI inesperada {lat.shape}/{lon.shape}")
        forma = lat.shape
        time_tai_scan = campo(geo, "Time")
        utc_scan = tai93_a_utc(time_tai_scan)
        seconds_group = geo if cfg["seconds_group"] == "geo" else data
        seconds_scan = campo(
            seconds_group, cfg["seconds"], requerido=False,
        )
        _validar_tiempo(time_tai_scan, seconds_scan, utc_scan)
        if cfg["corners"]:
            clat = campo(geo, cfg["corners"][0])
            clon = campo(geo, cfg["corners"][1])
            huella_fuente = "corners_nativos_hdf"
        else:
            clat, clon = esquinas_desde_centros(lat, lon)
            huella_fuente = "centros_swath_inferida"
        seleccion = mascara.seleccionar(lat, lon, clat, clon)
        if seleccion.empty:
            return pd.DataFrame(columns=_columnas(pol))
        pos = seleccion.pop("_pos").to_numpy(dtype=np.int64)
        filas = seleccion["fila"].to_numpy(dtype=np.uint16)
        columnas = seleccion["columna"].to_numpy(dtype=np.uint8)
        nombre = path.name
        estable = _id_estable(nombre)
        orbita = _orbita(nombre)
        if forma[0] >= 2048 or forma[1] >= 64:
            raise ValueError(f"swath excede codificacion pixel_id: {forma}")
        pixel_id = ((np.uint64(cfg["codigo"]) << np.uint64(56)) |
                    (np.uint64(orbita) << np.uint64(17)) |
                    (filas.astype(np.uint64) << np.uint64(6)) |
                    columnas.astype(np.uint64))
        utc_grid = expandir_scanline(
            np.asarray(utc_scan, dtype="datetime64[us]"), forma,
        ).reshape(-1)[pos]
        ts = pd.to_datetime(utc_grid, utc=True)
        tai_grid = expandir_scanline(time_tai_scan, forma).reshape(-1)[pos]
        if seconds_scan is None:
            sid = np.full(len(pos), np.nan, dtype=np.float32)
        else:
            sid = expandir_scanline(seconds_scan, forma).reshape(-1)[pos]
        df = pd.DataFrame({
            "pixel_id": pixel_id,
            "observation_id": [f"{estable}:{f}:{c}" for f, c in zip(filas, columnas)],
            "granulo": estable,
            "producto": cfg["short"],
            "coleccion": cfg["version"],
            "ts_utc": ts,
            "fecha_utc": ts.strftime("%Y-%m-%d"),
            "hora_utc": ts.hour.astype(np.uint8),
            "minuto_utc": ts.minute.astype(np.uint8),
            "segundo_utc": (ts.second + ts.microsecond / 1_000_000.0).astype(np.float32),
            "time_tai93": tai_grid.astype(np.float64),
            "seconds_in_day_native": sid.astype(np.float32),
            "scanline": filas,
            "cross_track": columnas,
            "lat": lat.reshape(-1)[pos].astype(np.float32),
            "lon": lon.reshape(-1)[pos].astype(np.float32),
            "huella_fuente": huella_fuente,
        })
        agregar_esquinas(df, clat, clon, pos)
        for columna in seleccion.columns:
            df[columna] = seleccion[columna].to_numpy()
        for salida, grupo, sds, entero in cfg["variables"]:
            origen = geo if grupo == "geo" else data
            arr = campo(origen, sds, entero=entero)
            df[salida] = _extraer(arr, forma, pos, entero)
        df["valor_objetivo_valido"] = np.isfinite(
            pd.to_numeric(df[cfg["objetivo"]], errors="coerce")
        )
        return df.loc[:, _columnas(pol)]


def _validar(df: pd.DataFrame, pol: str) -> None:
    if df.empty:
        raise ValueError("Parquet OMI sin observaciones")
    if df["pixel_id"].isna().any() or df["pixel_id"].duplicated().any():
        raise ValueError("pixel_id ausente o duplicado")
    if df["observation_id"].isna().any() or df["observation_id"].duplicated().any():
        raise ValueError("observation_id ausente o duplicado")
    ts = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
    if ts.isna().any():
        raise ValueError("timestamp UTC invalido")
    if not np.isfinite(pd.to_numeric(df["time_tai93"], errors="coerce")).all():
        raise ValueError("TAI93 crudo ausente")
    lat = pd.to_numeric(df["lat"], errors="coerce")
    lon = pd.to_numeric(df["lon"], errors="coerce")
    if lat.isna().any() or lon.isna().any() or not lat.between(-60, -16).all() \
            or not lon.between(-111, -65).all():
        raise ValueError("coordenadas fuera de Chile no antartico")
    for k in range(4):
        if (pd.to_numeric(df[f"corner{k}_lat"], errors="coerce").isna().any()
                or pd.to_numeric(df[f"corner{k}_lon"], errors="coerce").isna().any()):
            raise ValueError("huella sin cuatro vertices")
    cod = pd.to_numeric(df["cod_comuna"], errors="coerce")
    if cod.isna().any() or not (cod >= -1).all():
        raise ValueError("cod_comuna invalido")
    if (pd.to_numeric(df["n_comunas_huella"], errors="coerce") < 1).any() \
            or (df["cod_comunas_huella"].astype(str).str.len() == 0).any():
        raise ValueError("huella publicada no intersecta unidad chilena")
    if not df["producto"].eq(PRODUCTOS[pol]["short"]).all():
        raise ValueError("producto mezclado")
    esperado = np.isfinite(pd.to_numeric(
        df[PRODUCTOS[pol]["objetivo"]], errors="coerce",
    ))
    if not np.array_equal(esperado, df["valor_objetivo_valido"].astype(bool)):
        raise ValueError("bandera valor_objetivo_valido inconsistente")


def _descargar_uno(earthaccess, granulo, carpeta: Path) -> tuple[Path, dict]:
    descripciones = describir_granulos([granulo])
    descargados = _con_reintentos(
        f"descarga {_nombre(granulo)}",
        lambda: earthaccess.download([granulo], local_path=str(carpeta)),
    ) or []
    paths = [Path(x).resolve() for x in descargados if Path(x).is_file()]
    if len(paths) != 1:
        raise RuntimeError(f"se esperaba un HDF por granulo; llegaron {len(paths)}")
    descripcion = anotar_checksums_descargados(descripciones, paths)[0]
    descripcion["url"] = str(descripcion.get("url", "")).split("?", 1)[0]
    return paths[0], descripcion


def _audit(
    *, path: Path, runtime: dict, pol: str, fuente: dict, nombre: str,
    salida: Path | None, pixeles: pd.DataFrame | None, estado: str,
    raw_eliminado: bool, error: str = "",
) -> str:
    tiempos = pd.DatetimeIndex([]) if pixeles is None else pd.to_datetime(
        pixeles["ts_utc"], utc=True, errors="coerce",
    ).dropna()
    documento = {
        "schema": "airpollution.omi-l2-pixel-manifest.v1",
        "execution_id": runtime["execution_id"],
        "creado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "runtime": runtime["reproducibilidad"],
        "producto": PRODUCTOS[pol]["short"],
        "coleccion_cmr": PRODUCTOS[pol]["version"],
        "nivel": "L2 swath",
        "resolucion_instrumental": "13 x 24 km en nadir; variable cross-track",
        "fecha_adquisicion": _fecha_nombre(nombre),
        "granulo_id_estable": _id_estable(nombre),
        "fuente": fuente,
        "tiempo_nativo": {
            "campo": "Geolocation Fields/Time", "escala": "TAI93",
            "conversion": "UTC con segundos intercalares; contrastada con SecondsInDay/deltaTime",
            "min_utc": "" if len(tiempos) == 0 else tiempos.min().isoformat(),
            "max_utc": "" if len(tiempos) == 0 else tiempos.max().isoformat(),
            "sin_interpolacion_horaria": True,
        },
        "huella": {
            "fuente": ("corners nativos HDF" if PRODUCTOS[pol]["corners"]
                       else "inferida de centros vecinos: OMTO3 no publica corners"),
            "criterio": "centro o poligono de huella intersecta cualquier unidad administrativa",
            "multiples_pixeles_por_comuna": True,
            "agregacion_espacial": None,
        },
        "qa": {
            "politica": "campos QA/incertidumbre crudos conservados; sin filtro irreversible",
            "columnas": [x[0] for x in PRODUCTOS[pol]["variables"]],
        },
        "filas": 0 if pixeles is None else int(len(pixeles)),
        "comunas_centro": (0 if pixeles is None else int(
            pixeles.loc[pixeles["cod_comuna"] >= 0, "cod_comuna"].nunique()
        )),
        "max_pixeles_misma_comuna": (0 if pixeles is None else int(
            pixeles.loc[pixeles["cod_comuna"] >= 0, "cod_comuna"].value_counts().max()
            if (pixeles["cod_comuna"] >= 0).any() else 0
        )),
        "salida": None if salida is None else {
            "ruta": str(salida), "formato": "Parquet ZSTD",
            "bytes": salida.stat().st_size, "sha256": sha256_archivo(salida),
        },
        "estado": estado,
        "validacion": estado in {"ok", "sin_interseccion"},
        "crudo_eliminado": bool(raw_eliminado),
        "error": error,
    }
    return escribir_json_atomico(documento, path)


def _granulo_valido(pol: str, nombre: str, force: bool = False) -> bool:
    if force:
        return False
    audit_path = _audit_path(pol, nombre)
    if not audit_path.is_file():
        return False
    try:
        doc = json.loads(audit_path.read_text(encoding="utf-8"))
        if not doc.get("validacion") or not doc.get("crudo_eliminado"):
            return False
        fuente_nombre = (doc.get("fuente") or {}).get("archivo_descargado")
        if fuente_nombre != nombre:
            return False
        if doc.get("estado") == "sin_interseccion":
            return doc.get("salida") is None
        salida = _destino(pol, nombre)
        info = doc.get("salida") or {}
        if not salida.is_file() or info.get("sha256") != sha256_archivo(salida):
            return False
        validar_parquet(
            salida, _columnas(pol), lambda df: _validar(df, pol),
            columnas_validacion=_columnas(pol),
        )
        return True
    except Exception:
        return False


def _dia_valido(pol: str, fecha: str, manifiesto: Manifiesto) -> bool:
    reg = manifiesto.obtener(fecha, pol)
    path = _day_path(pol, fecha)
    if not reg or reg.estado not in {"ok", "sin_datos"} or not path.is_file():
        return False
    try:
        if reg.sha256 and sha256_archivo(path) != reg.sha256:
            return False
        doc = json.loads(path.read_text(encoding="utf-8"))
        if not doc.get("completo"):
            return False
        return all(
            sha256_archivo(Path(x["audit_path"])) == x["audit_sha256"]
            and _granulo_valido(pol, x["nombre"])
            for x in doc.get("granulos", [])
        )
    except Exception:
        return False


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--contaminantes", default="no2,so2,o3",
                   help="no2,so2,o3 separados por coma")
    p.add_argument("--desde", default=INICIO.isoformat(), help="YYYY-MM-DD")
    p.add_argument("--hasta", default=date.today().isoformat(), help="YYYY-MM-DD")
    p.add_argument("--comunas", type=Path, default=SHP)
    p.add_argument("--force", action="store_true")
    p.add_argument("--reserva-gb", type=float, default=10.0)
    p.add_argument("--dry-run", action="store_true")
    return p


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    pols = [x.strip().lower() for x in args.contaminantes.split(",") if x.strip()]
    invalidos = [x for x in pols if x not in PRODUCTOS]
    if invalidos:
        raise SystemExit(f"contaminantes invalidos: {invalidos}")
    try:
        dias_solicitados = list(fechas_inclusivas(args.desde, args.hasta))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    dias = [d for d in dias_solicitados if d >= INICIO]
    log.info("OMI L2 solicitado: %s -> %s; inicio nativo=%s; %s",
             dias_solicitados[0], dias_solicitados[-1], INICIO, ",".join(pols))
    if not dias:
        log.info("rango solicitado anterior al inicio OMI; nada que descargar")
        return 0
    log.info("rango efectivo %s -> %s; %d dias", dias[0], dias[-1], len(dias))
    if args.dry_run:
        log.info("[dry-run] salida=%s; crudo efimero=%s", SALIDA, TRABAJO)
        return 0
    requerir_modulos("earthaccess", "h5py", "geopandas", "shapely", "pyarrow")
    if not args.comunas.is_file():
        raise SystemExit(f"no existe mascara comunal {args.comunas}")
    login()
    import earthaccess

    comunas = cargar_comunas(args.comunas)
    aois = derivar(args.comunas)
    mascara = MascaraHuellasChile(comunas, aois)
    limpiar_parciales(SALIDA, AUDITORIA)
    manifiesto = Manifiesto(MANIFIESTO)
    runtime = {
        "execution_id": str(uuid.uuid4()),
        "reproducibilidad": detalles_runtime(Path(__file__), args.comunas, aois),
    }
    errores = []
    try:
        with BloqueoProceso(BASE / ".descargar_l2.lock"), AreaTrabajo(TRABAJO) as area:
            for dia in dias:
                fecha = dia.isoformat()
                for pol in pols:
                    if not args.force and _dia_valido(pol, fecha, manifiesto):
                        log.info("%s %s: validado", fecha, pol.upper())
                        continue
                    if shutil.disk_usage(BASE).free / (1024 ** 3) < args.reserva_gb:
                        log.error("espacio libre bajo reserva %.1f GiB", args.reserva_gb)
                        return 2
                    cfg = PRODUCTOS[pol]
                    try:
                        granulos = _buscar(earthaccess, cfg, dia, aois)
                        if not granulos:
                            raise RuntimeError(
                                "CMR no devolvio granulos; no se marca el dia completo"
                            )
                        registros = []
                        total = 0
                        for granulo in granulos:
                            nombre = _nombre(granulo)
                            if not nombre:
                                raise RuntimeError("granulo CMR sin URL de datos")
                            if not args.force and _granulo_valido(pol, nombre):
                                ap = _audit_path(pol, nombre)
                                doc = json.loads(ap.read_text(encoding="utf-8"))
                                total += int(doc.get("filas", 0))
                                registros.append({
                                    "nombre": nombre, "audit_path": str(ap),
                                    "audit_sha256": sha256_archivo(ap),
                                })
                                continue
                            carpeta = area.carpeta_dia(fecha, f"{pol}.{_id_estable(nombre)}")
                            fuente = {}
                            try:
                                src, fuente = _descargar_uno(earthaccess, granulo, carpeta)
                                pixeles = _leer(src, pol, mascara)
                                destino = _destino(pol, nombre)
                                if pixeles.empty:
                                    area.limpiar_dia(carpeta)
                                    if carpeta.exists():
                                        raise RuntimeError("no se pudo eliminar HDF temporal")
                                    # Si CMR republica el granulo sin una
                                    # interseccion previa, retira la salida
                                    # obsoleta antes de registrar la ausencia.
                                    destino.unlink(missing_ok=True)
                                    _audit(
                                        path=_audit_path(pol, nombre), runtime=runtime,
                                        pol=pol, fuente=fuente, nombre=nombre,
                                        salida=None, pixeles=None,
                                        estado="sin_interseccion", raw_eliminado=True,
                                    )
                                else:
                                    escribir_parquet_atomico(
                                        pixeles, destino, _columnas(pol),
                                        lambda df, pol=pol: _validar(df, pol),
                                        columnas_validacion=_columnas(pol),
                                    )
                                    area.limpiar_dia(carpeta)
                                    if carpeta.exists():
                                        raise RuntimeError("no se pudo eliminar HDF temporal")
                                    _audit(
                                        path=_audit_path(pol, nombre), runtime=runtime,
                                        pol=pol, fuente=fuente, nombre=nombre,
                                        salida=destino, pixeles=pixeles,
                                        estado="ok", raw_eliminado=True,
                                    )
                                    total += len(pixeles)
                                ap = _audit_path(pol, nombre)
                                registros.append({
                                    "nombre": nombre, "audit_path": str(ap),
                                    "audit_sha256": sha256_archivo(ap),
                                })
                            finally:
                                area.limpiar_dia(carpeta)
                        day_doc = {
                            "schema": "airpollution.omi-l2-day-manifest.v1",
                            "producto": cfg["short"], "coleccion": cfg["version"],
                            "fecha": fecha, "completo": True,
                            "consulta_aois": [a.id for a in aois],
                            "granulos": registros, "filas": total,
                            "cmr_vacio_no_se_acepta": True,
                        }
                        sha_day = escribir_json_atomico(day_doc, _day_path(pol, fecha))
                        manifiesto.marcar(fecha, pol, "ok", total, sha_day)
                        log.info("%s %s: %d granulos, %s pixeles",
                                 fecha, pol.upper(), len(granulos), f"{total:,}")
                    except KeyboardInterrupt:
                        raise
                    except Exception as exc:
                        manifiesto.marcar(fecha, pol, "error")
                        msg = f"{fecha} {pol}: {type(exc).__name__}: {exc}"
                        errores.append(msg)
                        log.error(msg)
    except KeyboardInterrupt:
        log.warning("interrumpido: HDF y archivos .part eliminados")
        return 130
    if errores:
        log.error("%d particiones reintentables; primera: %s", len(errores), errores[0])
        return 1
    log.info("Listo: OMI L2 pixel/pasada; no quedan HDF temporales.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
