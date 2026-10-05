#!/usr/bin/env python3
"""MOPITT MOP02J v10 L2 a resolucion nativa de observacion (~22 km).

Conserva cada retrieval de CO, su tiempo TAI93 exacto, centro, huella nominal,
incertidumbres, perfil, kernels y diagnosticos QA. La comuna es mascara y
etiqueta, nunca una agregacion. El HDF global se descarga de a un granulo, el
Parquet ZSTD chileno se reabre/valida y solo entonces se elimina el crudo.

MOP02J publica centros de retrieval pero no vertices: las cuatro esquinas que
acompanan la salida representan explicitamente la huella nominal 22 x 22 km;
no se presentan como vertices medidos. MOPITT dejo de observar el 2025-02-01,
por lo que un ``--hasta`` posterior se limita a esa fecha sin inventar 2026.
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
    esquinas_mopitt,
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
    limpiar_parciales,
    requerir_modulos,
    salida_diaria,
    sha256_archivo,
    validar_parquet,
)

log = get_logger("mopitt_l2_pixeles")

BASE = CONTAMINANTES / "MOPITT_L2_CO"
TRABAJO = BASE / "_trabajo_descarga"
SALIDA = BASE / "pixeles_pasada"
AUDITORIA = BASE / "manifiestos_pixeles_pasada"
MANIFIESTO = BASE / "manifest_pixeles_pasada.csv"
SHP = DATA / "comunas.shp"
SHORT = "MOP02J"
VERSION_CMR = "10"
INICIO = date(2000, 3, 3)
FIN_OBSERVACIONES = date(2025, 2, 1)
EPOCA_ID = date(2000, 1, 1)

COLUMNAS = (
    "pixel_id", "observation_id", "granulo", "producto", "coleccion_cmr",
    "version_procesamiento", "ts_utc", "fecha_utc", "hora_utc",
    "minuto_utc", "segundo_utc", "time_tai93", "seconds_in_day_native",
    "record_index", "swath_index_0", "swath_index_1", "swath_index_2",
    "lat", "lon", "corner0_lat", "corner0_lon", "corner1_lat",
    "corner1_lon", "corner2_lat", "corner2_lon", "corner3_lat",
    "corner3_lon", "huella_fuente", "lado_huella_nominal_km",
    "cod_comuna", "etiqueta_comuna", "cod_comunas_huella",
    "comunas_huella", "n_comunas_huella", "criterio_inclusion",
    "territorio", "co_total_molec_cm2", "co_total_error_molec_cm2",
    "co_lower_trop_molec_cm2", "co_lower_trop_error_molec_cm2",
    "co_surface_ppbv", "co_surface_error_ppbv", "co_profile_ppbv",
    "co_profile_error_ppbv", "pressure_grid_hpa", "apriori_total_molec_cm2",
    "apriori_surface_ppbv", "apriori_profile_ppbv", "dry_air_column_molec_cm2",
    "water_vapor_column_molec_cm2", "surface_pressure_hpa", "dem_altitude_m",
    "degrees_freedom_signal", "signal_chi2", "solar_zenith_deg",
    "satellite_zenith_deg", "retrieval_iterations", "cloud_description",
    "surface_index", "mop_cloud_radiance_ratio", "anomaly_diagnostic",
    "averaging_kernel_row_sums", "total_column_averaging_kernel",
    "total_column_averaging_kernel_dimless", "total_column_diagnostic_0",
    "total_column_diagnostic_1", "valor_objetivo_valido",
)


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


def _buscar(earthaccess, dia: date, aois) -> list:
    inicio = datetime.combine(dia, dt_time.min)
    fin = datetime.combine(dia, dt_time.max)
    resultados = []
    for aoi in aois:
        resultados.extend(_con_reintentos(
            f"CMR MOP02J {dia} {aoi.id}",
            lambda aoi=aoi: earthaccess.search_data(
                short_name=SHORT, version=VERSION_CMR,
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


def _fecha_nombre(nombre: str) -> str:
    m = re.search(r"MOP02J-(\d{4})(\d{2})(\d{2})-", nombre)
    if not m:
        raise ValueError(f"nombre MOP02J no reconocido: {nombre}")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def _version_nombre(nombre: str) -> str:
    m = re.search(r"-L2V([^/]+?)\.he5$", nombre, flags=re.IGNORECASE)
    return m.group(1) if m else "no_codificada"


def _id_estable(nombre: str) -> str:
    if not re.fullmatch(r"MOP02J-\d{8}-L2V[^/]+\.he5", nombre,
                        flags=re.IGNORECASE):
        raise ValueError(f"nombre MOP02J no reconocido: {nombre}")
    return Path(nombre).stem


def _destino(nombre: str) -> Path:
    fecha = _fecha_nombre(nombre)
    return salida_diaria(SALIDA, fecha, _id_estable(nombre).lower())


def _audit_path(nombre: str) -> Path:
    fecha = _fecha_nombre(nombre)
    return salida_diaria(AUDITORIA, fecha, _id_estable(nombre).lower()).with_suffix(".json")


def _day_path(fecha: str) -> Path:
    return salida_diaria(
        AUDITORIA / "_dias", fecha, f"mopitt_l2_{fecha.replace('-', '')}",
    ).with_suffix(".json")


def _pares(arr, pos) -> tuple[np.ndarray, np.ndarray]:
    arr = np.asarray(arr)
    if arr.ndim != 2 or arr.shape[1] != 2:
        raise ValueError(f"campo valor/error inesperado: {arr.shape}")
    return (arr[pos, 0].astype(np.float64), arr[pos, 1].astype(np.float64))


def _listas_pares(arr, pos) -> tuple[list[list[float]], list[list[float]]]:
    arr = np.asarray(arr)
    if arr.ndim != 3 or arr.shape[2] != 2:
        raise ValueError(f"perfil valor/error inesperado: {arr.shape}")
    return (arr[pos, :, 0].astype(np.float32).tolist(),
            arr[pos, :, 1].astype(np.float32).tolist())


def _leer(path: Path, mascara: MascaraHuellasChile) -> pd.DataFrame:
    import h5py

    with h5py.File(path, "r") as h:
        swath = h["HDFEOS/SWATHS/MOP02"]
        geo, data = swath["Geolocation Fields"], swath["Data Fields"]
        lat = campo(geo, "Latitude")
        lon = campo(geo, "Longitude")
        if lat.ndim != 1 or lon.shape != lat.shape:
            raise ValueError(f"geolocalizacion MOPITT inesperada {lat.shape}")
        time_tai = campo(geo, "Time")
        seconds = campo(geo, "SecondsinDay")
        ts_todos = tai93_a_utc(time_tai)
        utc_sid = (ts_todos.hour * 3600 + ts_todos.minute * 60 + ts_todos.second
                   + ts_todos.microsecond / 1_000_000.0)
        diferencia = np.abs(((utc_sid - seconds + 43200.0) % 86400.0) - 43200.0)
        validos = np.isfinite(seconds) & ~pd.isna(ts_todos)
        if validos.any() and np.nanmax(diferencia[validos]) > 1.1:
            raise ValueError("TAI93 MOPITT discrepa de SecondsinDay")
        clat, clon = esquinas_mopitt(lat, lon, lado_km=22.0)
        seleccion = mascara.seleccionar(lat, lon, clat, clon)
        if seleccion.empty:
            return pd.DataFrame(columns=COLUMNAS)
        pos = seleccion.pop("_pos").to_numpy(dtype=np.int64)
        nombre = path.name
        fecha = date.fromisoformat(_fecha_nombre(nombre))
        dias = (fecha - EPOCA_ID).days
        if dias >= 2 ** 14 or int(pos.max()) >= 2 ** 20:
            raise ValueError("indices exceden codificacion pixel_id")
        pixel_id = ((np.uint64(4) << np.uint64(56)) |
                    (np.uint64(dias) << np.uint64(20)) |
                    pos.astype(np.uint64))
        ts = ts_todos[pos]
        swath_index = campo(data, "SwathIndex", entero=True)
        if swath_index.shape[1] != 3:
            raise ValueError(f"SwathIndex inesperado {swath_index.shape}")

        total, total_err = _pares(campo(data, "RetrievedCOTotalColumn"), pos)
        lower, lower_err = _pares(campo(data, "RetrievedCOLowerTropColumn"), pos)
        surface, surface_err = _pares(campo(data, "RetrievedCOSurfaceMixingRatio"), pos)
        perfil, perfil_err = _listas_pares(
            campo(data, "RetrievedCOMixingRatioProfile"), pos,
        )
        apr_surface = campo(data, "APrioriCOSurfaceMixingRatio")
        apr_profile = campo(data, "APrioriCOMixingRatioProfile")
        # En a priori, el segundo eje final no es error de retrieval. Se
        # conserva el primer componente coherente con la guia L2.
        if apr_surface.ndim == 2:
            apr_surface_val = apr_surface[pos, 0]
        else:
            apr_surface_val = apr_surface[pos]
        if apr_profile.ndim == 3:
            apr_profile_val = apr_profile[pos, :, 0].astype(np.float32).tolist()
        else:
            apr_profile_val = apr_profile[pos].astype(np.float32).tolist()
        pressure = campo(data, "PressureGrid").astype(np.float32).tolist()
        n = len(pos)
        diag = campo(data, "RetrievedCOTotalColumnDiagnostics")[pos]
        if diag.ndim != 2 or diag.shape[1] != 2:
            raise ValueError(f"diagnostico total inesperado {diag.shape}")

        df = pd.DataFrame({
            "pixel_id": pixel_id,
            "observation_id": [f"{_id_estable(nombre)}:{int(i)}" for i in pos],
            "granulo": _id_estable(nombre),
            "producto": SHORT,
            "coleccion_cmr": VERSION_CMR,
            "version_procesamiento": _version_nombre(nombre),
            "ts_utc": ts,
            "fecha_utc": ts.strftime("%Y-%m-%d"),
            "hora_utc": ts.hour.astype(np.uint8),
            "minuto_utc": ts.minute.astype(np.uint8),
            "segundo_utc": (ts.second + ts.microsecond / 1_000_000.0).astype(np.float32),
            "time_tai93": time_tai[pos].astype(np.float64),
            "seconds_in_day_native": seconds[pos].astype(np.float32),
            "record_index": pos.astype(np.uint32),
            "swath_index_0": swath_index[pos, 0].astype(np.int32),
            "swath_index_1": swath_index[pos, 1].astype(np.int32),
            "swath_index_2": swath_index[pos, 2].astype(np.int32),
            "lat": lat[pos].astype(np.float32),
            "lon": lon[pos].astype(np.float32),
            "huella_fuente": "centro_nativo_mop02j_mas_huella_nominal_22km",
            "lado_huella_nominal_km": np.full(n, 22.0, dtype=np.float32),
            "co_total_molec_cm2": total,
            "co_total_error_molec_cm2": total_err,
            "co_lower_trop_molec_cm2": lower,
            "co_lower_trop_error_molec_cm2": lower_err,
            "co_surface_ppbv": surface.astype(np.float32),
            "co_surface_error_ppbv": surface_err.astype(np.float32),
            "co_profile_ppbv": perfil,
            "co_profile_error_ppbv": perfil_err,
            "pressure_grid_hpa": [pressure] * n,
            "apriori_total_molec_cm2": campo(data, "APrioriCOTotalColumn")[pos],
            "apriori_surface_ppbv": apr_surface_val.astype(np.float32),
            "apriori_profile_ppbv": apr_profile_val,
            "dry_air_column_molec_cm2": campo(data, "DryAirColumn")[pos],
            "water_vapor_column_molec_cm2": campo(data, "WaterVaporColumn")[pos],
            "surface_pressure_hpa": campo(data, "SurfacePressure")[pos].astype(np.float32),
            "dem_altitude_m": campo(data, "DEMAltitude")[pos].astype(np.float32),
            "degrees_freedom_signal": campo(data, "DegreesofFreedomforSignal")[pos].astype(np.float32),
            "signal_chi2": campo(data, "SignalChi2")[pos].astype(np.float32),
            "solar_zenith_deg": campo(data, "SolarZenithAngle")[pos].astype(np.float32),
            "satellite_zenith_deg": campo(data, "SatelliteZenithAngle")[pos].astype(np.float32),
            "retrieval_iterations": campo(data, "RetrievalIterations", entero=True)[pos].astype(np.int16),
            "cloud_description": campo(data, "CloudDescription", entero=True)[pos].astype(np.int32),
            "surface_index": campo(data, "SurfaceIndex", entero=True)[pos].astype(np.int16),
            "mop_cloud_radiance_ratio": campo(data, "MOPCldRadRatio")[pos].astype(np.float32),
            "anomaly_diagnostic": campo(data, "RetrievalAnomalyDiagnostic", entero=True)[pos].astype(np.int16).tolist(),
            "averaging_kernel_row_sums": campo(data, "AveragingKernelRowSums")[pos].astype(np.float32).tolist(),
            "total_column_averaging_kernel": campo(data, "TotalColumnAveragingKernel")[pos].astype(np.float32).tolist(),
            "total_column_averaging_kernel_dimless": campo(data, "TotalColumnAveragingKernelDimless")[pos].astype(np.float32).tolist(),
            "total_column_diagnostic_0": diag[:, 0].astype(np.float32),
            "total_column_diagnostic_1": diag[:, 1].astype(np.float32),
            "valor_objetivo_valido": np.isfinite(total),
        })
        agregar_esquinas(df, clat, clon, pos)
        for columna in seleccion.columns:
            df[columna] = seleccion[columna].to_numpy()
        return df.loc[:, COLUMNAS]


def _validar(df: pd.DataFrame) -> None:
    if df.empty:
        raise ValueError("Parquet MOPITT sin observaciones")
    if df["pixel_id"].isna().any() or df["pixel_id"].duplicated().any():
        raise ValueError("pixel_id ausente o duplicado")
    if df["observation_id"].isna().any() or df["observation_id"].duplicated().any():
        raise ValueError("observation_id ausente o duplicado")
    ts = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
    if ts.isna().any():
        raise ValueError("timestamp UTC invalido")
    lat = pd.to_numeric(df["lat"], errors="coerce")
    lon = pd.to_numeric(df["lon"], errors="coerce")
    if lat.isna().any() or lon.isna().any() or not lat.between(-60, -16).all() \
            or not lon.between(-111, -65).all():
        raise ValueError("coordenadas fuera de Chile no antartico")
    for k in range(4):
        if (pd.to_numeric(df[f"corner{k}_lat"], errors="coerce").isna().any()
                or pd.to_numeric(df[f"corner{k}_lon"], errors="coerce").isna().any()):
            raise ValueError("huella nominal incompleta")
    if (pd.to_numeric(df["n_comunas_huella"], errors="coerce") < 1).any():
        raise ValueError("huella publicada no toca Chile")
    if (pd.to_numeric(df["cod_comuna"], errors="coerce") < -1).any():
        raise ValueError("codigo comunal invalido")
    total = pd.to_numeric(df["co_total_molec_cm2"], errors="coerce")
    if not np.array_equal(np.isfinite(total), df["valor_objetivo_valido"].astype(bool)):
        raise ValueError("bandera de retrieval valido inconsistente")
    for col, largo in (("co_profile_ppbv", 9), ("co_profile_error_ppbv", 9),
                       ("pressure_grid_hpa", 9), ("anomaly_diagnostic", 5),
                       ("averaging_kernel_row_sums", 10),
                       ("total_column_averaging_kernel", 10),
                       ("total_column_averaging_kernel_dimless", 10)):
        if not df[col].map(lambda x: len(x) == largo).all():
            raise ValueError(f"longitud invalida en {col}")


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


def _audit(*, path: Path, runtime: dict, fuente: dict, nombre: str,
           salida: Path | None, pixeles: pd.DataFrame | None, estado: str,
           raw_eliminado: bool, error: str = "") -> str:
    tiempos = pd.DatetimeIndex([]) if pixeles is None else pd.to_datetime(
        pixeles["ts_utc"], utc=True, errors="coerce",
    ).dropna()
    documento = {
        "schema": "airpollution.mopitt-l2-pixel-manifest.v1",
        "execution_id": runtime["execution_id"],
        "creado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "runtime": runtime["reproducibilidad"],
        "producto": SHORT, "coleccion_cmr": VERSION_CMR,
        "version_procesamiento": _version_nombre(nombre),
        "nivel": "L2 swath", "resolucion_instrumental": "~22 x 22 km en nadir",
        "fecha_adquisicion": _fecha_nombre(nombre), "granulo": _id_estable(nombre),
        "fuente": fuente,
        "disponibilidad": {"inicio": INICIO.isoformat(),
                           "ultima_observacion": FIN_OBSERVACIONES.isoformat()},
        "tiempo_nativo": {
            "campo": "Geolocation Fields/Time", "escala": "TAI93 por retrieval",
            "contraste": "SecondsinDay", "sin_interpolacion_horaria": True,
            "min_utc": "" if len(tiempos) == 0 else tiempos.min().isoformat(),
            "max_utc": "" if len(tiempos) == 0 else tiempos.max().isoformat(),
        },
        "huella": {
            "centro": "Latitude/Longitude nativos MOP02J",
            "vertices": "huella nominal geodesica 22 x 22 km; MOP02J no publica corners",
            "criterio": "centro o huella intersecta unidad administrativa chilena",
            "agregacion_espacial": None, "multiples_pixeles_por_comuna": True,
        },
        "qa": {
            "politica": "retrieval, incertidumbre, perfil, kernels y QA conservados sin filtro irreversible",
            "campos": [
                "RetrievalAnomalyDiagnostic", "RetrievalIterations", "SignalChi2",
                "CloudDescription", "DegreesofFreedomforSignal",
            ],
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
        "estado": estado, "validacion": estado in {"ok", "sin_interseccion"},
        "crudo_eliminado": bool(raw_eliminado), "error": error,
    }
    return escribir_json_atomico(documento, path)


def _granulo_valido(nombre: str, force: bool = False) -> bool:
    if force:
        return False
    ap = _audit_path(nombre)
    if not ap.is_file():
        return False
    try:
        doc = json.loads(ap.read_text(encoding="utf-8"))
        if not doc.get("validacion") or not doc.get("crudo_eliminado"):
            return False
        if (doc.get("fuente") or {}).get("archivo_descargado") != nombre:
            return False
        if doc.get("estado") == "sin_interseccion":
            return doc.get("salida") is None
        salida = _destino(nombre)
        if not salida.is_file() or (doc.get("salida") or {}).get("sha256") != sha256_archivo(salida):
            return False
        validar_parquet(salida, COLUMNAS, _validar, columnas_validacion=COLUMNAS)
        return True
    except Exception:
        return False


def _dia_valido(fecha: str, manifiesto: Manifiesto) -> bool:
    reg = manifiesto.obtener(fecha, "mop02j")
    path = _day_path(fecha)
    if not reg or reg.estado != "ok" or not path.is_file():
        return False
    try:
        if reg.sha256 and sha256_archivo(path) != reg.sha256:
            return False
        doc = json.loads(path.read_text(encoding="utf-8"))
        return bool(doc.get("completo")) and all(
            sha256_archivo(Path(x["audit_path"])) == x["audit_sha256"]
            and _granulo_valido(x["nombre"])
            for x in doc.get("granulos", [])
        )
    except Exception:
        return False


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--desde", default=INICIO.isoformat(), help="YYYY-MM-DD")
    p.add_argument("--hasta", default=date.today().isoformat(), help="YYYY-MM-DD")
    p.add_argument("--comunas", type=Path, default=SHP)
    p.add_argument("--force", action="store_true")
    p.add_argument("--reserva-gb", type=float, default=10.0)
    p.add_argument("--dry-run", action="store_true")
    return p


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    try:
        solicitado_ini = date.fromisoformat(args.desde)
        solicitado_fin = min(date.fromisoformat(args.hasta), date.today())
    except ValueError as exc:
        raise SystemExit("--desde/--hasta deben usar YYYY-MM-DD") from exc
    efectivo_ini = max(solicitado_ini, INICIO)
    efectivo_fin = min(solicitado_fin, FIN_OBSERVACIONES)
    log.info("MOPITT L2 solicitado %s -> %s; disponible %s -> %s",
             solicitado_ini, solicitado_fin, INICIO, FIN_OBSERVACIONES)
    if solicitado_fin > FIN_OBSERVACIONES:
        log.warning("MOPITT termino el %s: no se fabrican datos posteriores",
                    FIN_OBSERVACIONES)
    if efectivo_ini > efectivo_fin:
        log.info("rango solicitado fuera de la mision; nada que descargar")
        return 0
    dias = []
    actual = efectivo_ini
    while actual <= efectivo_fin:
        dias.append(actual)
        actual += pd.Timedelta(days=1).to_pytimedelta()
    if args.dry_run:
        log.info("[dry-run] %d dias efectivos; salida=%s; crudo efimero=%s",
                 len(dias), SALIDA, TRABAJO)
        return 0
    requerir_modulos("earthaccess", "h5py", "geopandas", "shapely", "pyarrow", "pyproj")
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
                if not args.force and _dia_valido(fecha, manifiesto):
                    log.info("%s: validado", fecha)
                    continue
                if shutil.disk_usage(BASE).free / (1024 ** 3) < args.reserva_gb:
                    log.error("espacio libre bajo reserva %.1f GiB", args.reserva_gb)
                    return 2
                try:
                    granulos = _buscar(earthaccess, dia, aois)
                    if not granulos:
                        raise RuntimeError(
                            "CMR no devolvio MOP02J; no se marca el dia completo"
                        )
                    registros, total = [], 0
                    for granulo in granulos:
                        nombre = _nombre(granulo)
                        if not nombre:
                            raise RuntimeError("granulo CMR sin URL")
                        if not args.force and _granulo_valido(nombre):
                            ap = _audit_path(nombre)
                            doc = json.loads(ap.read_text(encoding="utf-8"))
                            total += int(doc.get("filas", 0))
                            registros.append({
                                "nombre": nombre, "audit_path": str(ap),
                                "audit_sha256": sha256_archivo(ap),
                            })
                            continue
                        carpeta = area.carpeta_dia(fecha, _id_estable(nombre))
                        try:
                            src, fuente = _descargar_uno(earthaccess, granulo, carpeta)
                            pixeles = _leer(src, mascara)
                            destino = _destino(nombre)
                            if pixeles.empty:
                                area.limpiar_dia(carpeta)
                                if carpeta.exists():
                                    raise RuntimeError("no se pudo eliminar HDF temporal")
                                destino.unlink(missing_ok=True)
                                _audit(
                                    path=_audit_path(nombre), runtime=runtime,
                                    fuente=fuente, nombre=nombre, salida=None,
                                    pixeles=None, estado="sin_interseccion",
                                    raw_eliminado=True,
                                )
                            else:
                                escribir_parquet_atomico(
                                    pixeles, destino, COLUMNAS, _validar,
                                    columnas_validacion=COLUMNAS,
                                )
                                area.limpiar_dia(carpeta)
                                if carpeta.exists():
                                    raise RuntimeError("no se pudo eliminar HDF temporal")
                                _audit(
                                    path=_audit_path(nombre), runtime=runtime,
                                    fuente=fuente, nombre=nombre, salida=destino,
                                    pixeles=pixeles, estado="ok", raw_eliminado=True,
                                )
                                total += len(pixeles)
                            ap = _audit_path(nombre)
                            registros.append({
                                "nombre": nombre, "audit_path": str(ap),
                                "audit_sha256": sha256_archivo(ap),
                            })
                        finally:
                            area.limpiar_dia(carpeta)
                    day_doc = {
                        "schema": "airpollution.mopitt-l2-day-manifest.v1",
                        "producto": SHORT, "coleccion_cmr": VERSION_CMR,
                        "fecha": fecha, "completo": True,
                        "consulta_aois": [a.id for a in aois],
                        "granulos": registros, "filas": total,
                        "cmr_vacio_no_se_acepta": True,
                        "ultima_observacion_mision": FIN_OBSERVACIONES.isoformat(),
                    }
                    sha_day = escribir_json_atomico(day_doc, _day_path(fecha))
                    manifiesto.marcar(fecha, "mop02j", "ok", total, sha_day)
                    log.info("%s: %d granulo(s), %s observaciones",
                             fecha, len(granulos), f"{total:,}")
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    manifiesto.marcar(fecha, "mop02j", "error")
                    msg = f"{fecha}: {type(exc).__name__}: {exc}"
                    errores.append(msg)
                    log.error(msg)
    except KeyboardInterrupt:
        log.warning("interrumpido: HDF y archivos .part eliminados")
        return 130
    if errores:
        log.error("%d dias reintentables; primero: %s", len(errores), errores[0])
        return 1
    log.info("Listo: MOPITT L2 retrieval/pasada; no quedan HDF temporales.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
