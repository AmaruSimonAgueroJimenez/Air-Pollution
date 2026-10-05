#!/usr/bin/env python3
"""MODIS AOD 3 km pixel × pasada, recortado a las comunas de Chile.

El flujo es diario y transaccional: descarga MOD04_3K/MYD04_3K en el disco
externo, conserva todos los píxeles AOD válidos a resolución nativa, les asigna
``cod_comuna`` mediante el polígono oficial y publica Parquet ZSTD particionado.
Se conserva ``Scan_Start_Time`` TAI93 por scanline/píxel (más un fallback
nominal explícito si falta); no se promedia por día.

Los HDF sólo existen en ``_trabajo_descarga``. El Parquet temporal se vuelve a
leer y validar antes de publicar la salida y antes de eliminar los HDF. INT,
TERM y cualquier fallo conservan el crudo no validado. Antes de retirar una
fuente se persiste un WAL inmutable con sus hashes y el de la salida validada;
después se registra la eliminación en la auditoría canónica y recién entonces
se actualiza el ledger. El manifiesto permite reanudar sin repetir particiones
ya validadas, salvo que exista crudo pendiente de ese día.

Recuperación: un ``*.pre_borrado.json`` sin confirmación canónica significa que
el Parquet ya fue validado, pero la eliminación/confirmación pudo interrumpirse.
Los HDF que sigan en ``_trabajo_descarga/<sensor>/<fecha>`` se preservan y
obligan a reintentar el día. Los ``*.error.json`` son sidecars inmutables de la
ejecución y nunca sustituyen el WAL ni la auditoría canónica previa.

Salida::

  MODIS_AOD_3K/pixeles_horario/year=YYYY/month=MM/day=DD/
      modis_aod3k_<sensor>_YYYYMMDD.parquet

Uso::

  python descargar_modis_aod.py --desde 2000-01-01 --hasta 2026-12-31
  python descargar_modis_aod.py --sensor terra --dry-run
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
from _common import CONTAMINANTES, DATA, bbox_earthaccess, get_logger  # noqa: E402
from _env_earthdata import login  # noqa: E402
import _producciones_modis as producciones_modis  # noqa: E402
from _satellite_streaming import (  # noqa: E402
    AreaTrabajo,
    BloqueoProceso,
    Manifiesto,
    anotar_checksums_descargados,
    cargar_comunas,
    componentes_shapefile,
    cobertura_territorios,
    deduplicar_granulos,
    describir_granulos,
    escribir_json_atomico,
    escribir_parquet_atomico,
    etiquetar_puntos_chile,
    fechas_inclusivas,
    limpiar_parciales,
    requerir_modulos,
    salida_diaria,
    sha256_archivo,
    sha256_conjunto,
    territorio_desde_lonlat,
    validar_parquet,
)

log = get_logger("modis_aod_pixeles")

BASE = CONTAMINANTES / "MODIS_AOD_3K"
TRABAJO = BASE / "_trabajo_descarga"
SALIDA = BASE / "pixeles_horario"
MANIFIESTO = BASE / "manifest_pixeles_horario.csv"
AUDITORIA = BASE / "manifiestos_pixeles_horario"
SHP = DATA / "comunas.shp"

# Consultas disjuntas: evitan descargar miles de km de océano entre el
# continente, Juan Fernández y Rapa Nui. El recorte final es poligonal.
BBOX_CHILE = (
    tuple(bbox_earthaccess()),
    (-81.2, -34.1, -78.5, -26.0),       # Juan Fernández + Desventuradas
    (-109.8, -27.6, -105.0, -26.2),     # Rapa Nui + Sala y Gómez
)

PRODUCTOS = {
    "terra": ("MOD04_3K", "6.1", "Terra", date(2000, 2, 24)),
    "aqua": ("MYD04_3K", "6.1", "Aqua", date(2002, 7, 4)),
}

# AOD combinado primero; Dark Target rellena sólo los píxeles donde falta.
SDS_COMBINADO = "AOD_550_Dark_Target_Deep_Blue_Combined"
SDS_COMBINADO_QA = "AOD_550_Dark_Target_Deep_Blue_Combined_QA_Flag"
SDS_DT = "Optical_Depth_Land_And_Ocean"
SDS_DT_QA = "Land_Ocean_Quality_Flag"

COLUMNAS = (
    "pixel_id", "granulo", "producto", "satelite", "ts_utc", "fecha",
    "hora_utc", "minuto_utc", "fila", "columna", "lat", "lon",
    "cod_comuna", "etiqueta_comuna", "aod550", "qa", "fuente", "tiempo_fuente",
    "scan_start_tai93", "territorio",
)
COLUMNAS_VALIDACION = (
    "pixel_id", "satelite", "ts_utc", "fecha", "hora_utc", "minuto_utc",
    "fila", "columna",
    "lat", "lon", "cod_comuna", "etiqueta_comuna", "aod550", "qa", "fuente", "tiempo_fuente",
    "scan_start_tai93", "territorio",
)


def _con_reintentos(descripcion, fn, intentos: int = 6, base: int = 10):
    ultimo = None
    for k in range(1, intentos + 1):
        try:
            return fn()
        except Exception as exc:
            ultimo = exc
            if k == intentos:
                break
            espera = base * k
            log.warning("%s falló (%s); reintento %d/%d en %ds",
                        descripcion, type(exc).__name__, k, intentos, espera)
            time.sleep(espera)
    raise ultimo


def _buscar_dia(earthaccess, short_name: str, version: str, dia: date) -> list:
    inicio = datetime.combine(dia, dt_time.min)
    fin = datetime.combine(dia, dt_time.max)
    encontrados = []
    for bbox in BBOX_CHILE:
        encontrados.extend(_con_reintentos(
            f"CMR {short_name} {dia} {bbox}",
            lambda bbox=bbox: earthaccess.search_data(
                short_name=short_name, version=version,
                bounding_box=bbox, temporal=(inicio, fin),
            ),
        ))
    return deduplicar_granulos(encontrados)


def _descargar(earthaccess, granulos: list, carpeta: Path, descripcion: str) -> list[Path]:
    paths = _con_reintentos(
        f"descarga {descripcion}",
        lambda: earthaccess.download(granulos, local_path=str(carpeta)),
    )
    raiz = carpeta.resolve()
    out = []
    for item in paths or []:
        path = Path(item).resolve()
        if path.is_file() and (path.parent == raiz or raiz in path.parents):
            out.append(path)
    if granulos and not out:
        raise RuntimeError(f"Earthdata no dejó HDF para {descripcion}")
    return out


def _leer_sds(sd, nombre: str, *, escalar: bool) -> np.ndarray | None:
    try:
        ds = sd.select(nombre)
    except Exception:
        return None
    try:
        arr = np.asarray(ds.get()).squeeze()
        attrs = ds.attributes()
    finally:
        ds.endaccess()
    fill = attrs.get("_FillValue")
    if escalar:
        out = arr.astype(np.float64)
        if fill is not None:
            out[out == float(fill)] = np.nan
        rango = attrs.get("valid_range")
        if rango is not None and len(rango) == 2:
            out[(out < float(rango[0])) | (out > float(rango[1]))] = np.nan
        scale = float(attrs.get("scale_factor", 1.0) or 1.0)
        offset = float(attrs.get("add_offset", 0.0) or 0.0)
        return ((out - offset) * scale).astype(np.float32)
    out = arr.astype(np.int32)
    if fill is not None:
        out[out == int(fill)] = -1
    return out


def _leer_scan_start_time(sd) -> np.ndarray | None:
    """Lee segundos TAI93 sin degradarlos a float32."""
    try:
        ds = sd.select("Scan_Start_Time")
    except Exception:
        return None
    try:
        arr = np.asarray(ds.get(), dtype=np.float64).squeeze()
        attrs = ds.attributes()
    finally:
        ds.endaccess()
    fill = attrs.get("_FillValue")
    if fill is not None:
        arr[arr == float(fill)] = np.nan
    scale = float(attrs.get("scale_factor", 1.0) or 1.0)
    offset = float(attrs.get("add_offset", 0.0) or 0.0)
    return (arr - offset) * scale


_RE_GRANULO = re.compile(
    r"(?P<producto>MOD04_3K|MYD04_3K)\.A(?P<year>\d{4})(?P<doy>\d{3})\."
    r"(?P<hh>\d{2})(?P<mm>\d{2})\."
)


def _metadatos_nombre(path: Path) -> tuple[str, datetime, str]:
    m = _RE_GRANULO.search(path.name)
    if not m:
        raise ValueError(f"nombre de gránulo sin fecha/hora: {path.name}")
    ts = (datetime(int(m["year"]), 1, 1, int(m["hh"]), int(m["mm"]),
                   tzinfo=timezone.utc)
          + pd.Timedelta(days=int(m["doy"]) - 1).to_pytimedelta())
    # Identificador estable: excluye el timestamp de producción final.
    partes = path.name.split(".")
    granulo = ".".join(partes[:4]) if len(partes) >= 4 else path.stem
    return m["producto"], ts, granulo


def _leer_granulo(path: Path) -> dict:
    try:
        from pyhdf.SD import SD, SDC
    except ImportError as exc:
        raise RuntimeError(
            "Falta pyhdf para MOD04_3K/MYD04_3K. Instálalo en el entorno "
            "que ejecuta el descargador."
        ) from exc
    sd = SD(str(path), SDC.READ)
    try:
        lat = _leer_sds(sd, "Latitude", escalar=True)
        lon = _leer_sds(sd, "Longitude", escalar=True)
        combinado = _leer_sds(sd, SDS_COMBINADO, escalar=True)
        combinado_qa = _leer_sds(sd, SDS_COMBINADO_QA, escalar=False)
        dt = _leer_sds(sd, SDS_DT, escalar=True)
        dt_qa = _leer_sds(sd, SDS_DT_QA, escalar=False)
        scan_start_time = _leer_scan_start_time(sd)
    finally:
        sd.end()
    if lat is None or lon is None or (combinado is None and dt is None):
        raise ValueError(f"SDS geográficos/AOD ausentes: {path.name}")
    forma = lat.shape
    if lon.shape != forma:
        raise ValueError(f"Latitude/Longitude incompatibles: {path.name}")
    for nombre, arr in ((SDS_COMBINADO, combinado), (SDS_DT, dt)):
        if arr is not None and arr.shape != forma:
            raise ValueError(f"{nombre} no coincide con geolocalización: {path.name}")

    aod = np.full(forma, np.nan, dtype=np.float32)
    fuente = np.zeros(forma, dtype=np.int8)  # 1 combinado, 2 dark target
    qa = np.full(forma, -1, dtype=np.int16)
    if combinado is not None:
        ok = np.isfinite(combinado)
        aod[ok], fuente[ok] = combinado[ok], 1
        if combinado_qa is not None and combinado_qa.shape == forma:
            qa[ok] = combinado_qa[ok].astype(np.int16)
    if dt is not None:
        ok = ~np.isfinite(aod) & np.isfinite(dt)
        aod[ok], fuente[ok] = dt[ok], 2
        if dt_qa is not None and dt_qa.shape == forma:
            qa[ok] = dt_qa[ok].astype(np.int16)
    aod[(aod < -0.1) | (aod > 5.0)] = np.nan
    producto, ts, granulo = _metadatos_nombre(path)
    return {"lat": lat, "lon": lon, "aod": aod, "qa": qa,
            "fuente": fuente, "producto": producto, "ts": ts,
            "granulo": granulo, "scan_start_time": scan_start_time}


def _tiempos_pixeles(g: dict, forma: tuple[int, ...], pos: np.ndarray,
                     filas: np.ndarray
                     ) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray]:
    """Timestamp por scanline/píxel; usa el nombre sólo como fallback.

    ``Scan_Start_Time`` se expresa en TAI93. Se descuentan los diez segundos
    intercalares introducidos desde 1993 hasta 2017; además se conserva TAI93
    crudo para que la conversión sea auditable y reversible.
    """
    nominal = pd.Timestamp(g["ts"])
    scan = g.get("scan_start_time")
    valores = None
    if scan is not None:
        scan = np.asarray(scan, dtype=np.float64)
        if scan.shape == forma:
            valores = scan.ravel()[pos]
        elif scan.size == forma[0]:
            valores = scan.reshape(-1)[filas]
        elif scan.ndim == 2 and scan.shape == (forma[0], 1):
            valores = scan[:, 0][filas]
    if valores is None:
        return (pd.DatetimeIndex([nominal] * len(pos)),
                np.full(len(pos), "granule_nominal", dtype=object),
                np.full(len(pos), np.nan, dtype=np.float64))
    candidatos_tai = pd.to_datetime(
        valores, unit="s", origin="1993-01-01",
        utc=True, errors="coerce",
    )
    # Fechas UTC de entrada en vigor de los saltos posteriores a la época.
    saltos = pd.DatetimeIndex([
        "1993-07-01", "1994-07-01", "1996-01-01", "1997-07-01",
        "1999-01-01", "2006-01-01", "2009-01-01", "2012-07-01",
        "2015-07-01", "2017-01-01",
    ], tz="UTC")
    n_saltos = np.zeros(len(candidatos_tai), dtype=np.int8)
    for salto in saltos:
        n_saltos += np.asarray(candidatos_tai >= salto, dtype=np.int8)
    # SDP Toolkit usa además un segundo base en la época TAI93. Ejemplo NASA:
    # 173357493.320 → 1998-06-30T10:51:28.320Z (4 saltos + 1 s base).
    candidatos = candidatos_tai - pd.to_timedelta(n_saltos + 1, unit="s")
    # Suprime artefactos nanosegundo de representar TAI93 como float64; el valor
    # original permanece en scan_start_tai93.
    candidatos = candidatos.round("us")
    cerca = (~pd.isna(candidatos)) & (
        np.abs((candidatos - nominal).total_seconds()) <= 86400
    )
    finales = pd.DatetimeIndex([
        candidatos[i] if cerca[i] else nominal for i in range(len(pos))
    ])
    fuente = np.where(cerca, "Scan_Start_Time_TAI93", "granule_nominal")
    tai93 = np.where(cerca, valores, np.nan).astype(np.float64)
    return finales, fuente, tai93


def _pixel_ids_modis(producto: str, ts_nominal: pd.Timestamp,
                      filas: np.ndarray, columnas: np.ndarray) -> np.ndarray:
    """ID uint64 determinista: pasada (40 bits útiles) + fila/columna (12+12).

    MOD04_3K no mantiene siempre la forma nominal 406×270 al exponerse por
    HDF4/pyhdf; algunos SDS/gránulos aparecen con ejes mayores que 512. Doce
    bits por eje admiten cualquier grilla de hasta 4096×4096 sin colisiones y
    el conjunto completo 2000–2068 continúa cabiendo holgadamente en uint64.
    """
    if np.max(filas, initial=0) >= 4096 or np.max(columnas, initial=0) >= 4096:
        raise ValueError("grilla MODIS excede el empaquetado 4096×4096")
    dias = (ts_nominal.date() - date(2000, 1, 1)).days
    minuto = ts_nominal.hour * 60 + ts_nominal.minute
    sensor_bit = 1 if producto.startswith("MYD") else 0
    base = np.uint64((dias * 1440 + minuto) * 2 + sensor_bit)
    return ((base << np.uint64(12) | filas.astype(np.uint64)) << np.uint64(12)
            | columnas.astype(np.uint64))


def _pixeles_granulo(path: Path, satelite: str, comunas) -> pd.DataFrame:
    g = _leer_granulo(path)
    forma = g["aod"].shape
    validos = np.isfinite(g["aod"]) & np.isfinite(g["lat"]) & np.isfinite(g["lon"])
    if not validos.any():
        return pd.DataFrame(columns=COLUMNAS)
    indices_validos = np.flatnonzero(validos.ravel())
    pos_rel, ci = etiquetar_puntos_chile(
        g["lon"].ravel()[indices_validos],
        g["lat"].ravel()[indices_validos],
        comunas,
    )
    if not len(pos_rel):
        return pd.DataFrame(columns=COLUMNAS)
    pos = indices_validos[pos_rel]
    filas, columnas = np.unravel_index(pos, forma)
    ts_nominal = pd.Timestamp(g["ts"])
    tiempos, tiempo_fuente, scan_tai93 = _tiempos_pixeles(g, forma, pos, filas)
    pixel_id = _pixel_ids_modis(g["producto"], ts_nominal, filas, columnas)
    fuentes = np.where(g["fuente"].ravel()[pos] == 1,
                       "DT_DB_combined", "dark_target")
    return pd.DataFrame({
        "pixel_id": pixel_id,
        "granulo": g["granulo"],
        "producto": g["producto"],
        "satelite": satelite,
        "ts_utc": tiempos,
        "fecha": tiempos.strftime("%Y-%m-%d"),
        "hora_utc": tiempos.hour.astype(np.int8),
        "minuto_utc": tiempos.minute.astype(np.int8),
        "fila": filas.astype(np.int16),
        "columna": columnas.astype(np.int16),
        "lat": g["lat"].ravel()[pos].astype(np.float32),
        "lon": g["lon"].ravel()[pos].astype(np.float32),
        "cod_comuna": pd.to_numeric(
            comunas.iloc[ci]["cod_comuna"], errors="coerce"
        ).to_numpy(dtype=np.int32),
        "etiqueta_comuna": comunas.iloc[ci]["Comuna"].astype(str).to_numpy(),
        "aod550": g["aod"].ravel()[pos].astype(np.float32),
        "qa": g["qa"].ravel()[pos].astype(np.int16),
        "fuente": fuentes,
        "tiempo_fuente": tiempo_fuente,
        "scan_start_tai93": scan_tai93,
        "territorio": territorio_desde_lonlat(
            g["lon"].ravel()[pos], g["lat"].ravel()[pos],
        ),
    })


def _procesar(paths: list[Path], satelite: str, comunas) -> pd.DataFrame:
    partes, errores = [], []
    for path in paths:
        try:
            df = _pixeles_granulo(path, satelite, comunas)
            if not df.empty:
                partes.append(df)
        except Exception as exc:
            errores.append(f"{path.name}: {type(exc).__name__}: {exc}")
    if errores:
        # No se publica una cobertura parcial silenciosa.
        raise RuntimeError("; ".join(errores[:3]))
    if not partes:
        return pd.DataFrame(columns=COLUMNAS)
    out = pd.concat(partes, ignore_index=True)
    return (out.drop_duplicates("pixel_id", keep="last")
            .sort_values(["ts_utc", "pixel_id"], kind="stable")
            .loc[:, list(COLUMNAS)].reset_index(drop=True))


def _validar(df: pd.DataFrame) -> None:
    if df.empty:
        raise ValueError("partición MODIS sin filas")
    ts = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
    if ts.isna().any():
        raise ValueError("timestamp UTC inválido")
    if not (ts.dt.strftime("%Y-%m-%d") == df["fecha"].astype(str)).all():
        raise ValueError("fecha no coincide con timestamp UTC")
    horas = pd.to_numeric(df["hora_utc"], errors="coerce")
    minutos = pd.to_numeric(df["minuto_utc"], errors="coerce")
    if not (horas.to_numpy() == ts.dt.hour.to_numpy()).all() \
            or not (minutos.to_numpy() == ts.dt.minute.to_numpy()).all():
        raise ValueError("hora/minuto no coincide con timestamp UTC")
    if df["pixel_id"].isna().any() or df["pixel_id"].duplicated().any():
        raise ValueError("pixel_id ausente o duplicado")
    lat = pd.to_numeric(df["lat"], errors="coerce")
    lon = pd.to_numeric(df["lon"], errors="coerce")
    aod = pd.to_numeric(df["aod550"], errors="coerce")
    cod = pd.to_numeric(df["cod_comuna"], errors="coerce")
    if lat.isna().any() or lon.isna().any() or not lat.between(-90, 90).all() \
            or not lon.between(-180, 180).all():
        raise ValueError("coordenadas inválidas")
    if aod.isna().any() or not aod.between(-0.1, 5.0).all():
        raise ValueError("AOD inválido")
    etiquetas = df["etiqueta_comuna"].astype("string")
    if cod.isna().any() or not (cod >= 0).all():
        raise ValueError("etiqueta comunal inválida")
    if etiquetas.isna().any() or (etiquetas.str.strip().str.len() == 0).any():
        raise ValueError("nombre/etiqueta comunal ausente")
    if ((cod == 0) & ~etiquetas.str.contains(
            "sin demarcar", case=False, na=False)).any():
        raise ValueError("cod_comuna=0 sin etiqueta explícita de zona no demarcada")
    if not df["fuente"].isin(["DT_DB_combined", "dark_target"]).all():
        raise ValueError("fuente AOD inválida")
    if not df["tiempo_fuente"].isin(
            ["Scan_Start_Time_TAI93", "granule_nominal"]).all():
        raise ValueError("fuente temporal inválida")
    tai93 = pd.to_numeric(df["scan_start_tai93"], errors="coerce")
    exacto = df["tiempo_fuente"].eq("Scan_Start_Time_TAI93")
    if tai93[exacto].isna().any() or tai93[~exacto].notna().any():
        raise ValueError("TAI93 crudo no corresponde a la fuente temporal")
    if not df["territorio"].isin(
            ["continente", "juan_fernandez", "desventuradas", "rapa_nui"]).all():
        raise ValueError("territorio inválido")


def _particion_valida(path: Path, fecha: str, flujo: str,
                      manifiesto: Manifiesto, auditoria: Path) -> bool:
    reg = manifiesto.obtener(fecha, flujo)
    if reg and reg.estado == "sin_datos":
        try:
            doc = json.loads(auditoria.read_text(encoding="utf-8"))
            return bool(doc.get("validacion") and doc.get("crudo_eliminado")) and (
                not reg.sha256 or sha256_archivo(auditoria) == reg.sha256
            )
        except Exception:
            return False
    if not path.exists():
        return False
    try:
        filas = validar_parquet(
            path, COLUMNAS, _validar, columnas_validacion=COLUMNAS_VALIDACION,
        )
        sha_salida = sha256_archivo(path)
        if not auditoria.is_file():
            return False
        doc = json.loads(auditoria.read_text(encoding="utf-8"))
        if not doc.get("validacion") or not doc.get("crudo_eliminado") \
                or (doc.get("salida") or {}).get("sha256") != sha_salida:
            return False
        sha_audit = sha256_archivo(auditoria)
        compuesto = f"{sha_salida}+{sha_audit}"
        if reg and reg.estado == "ok" and reg.sha256:
            return reg.filas == filas and compuesto == reg.sha256
        manifiesto.marcar(fecha, flujo, "ok", filas, compuesto)
        return True
    except Exception as exc:
        log.warning("partición previa inválida %s: %s", path, exc)
        return False


def _ruta_auditoria(fecha: str, sensor: str) -> Path:
    compacta = fecha.replace("-", "")
    return salida_diaria(
        AUDITORIA, fecha, f"modis_aod3k_{sensor}_{compacta}",
    ).with_suffix(".json")


def _ruta_evento_auditoria(
    ruta_canonica: Path,
    execution_id: str,
    evento: str,
) -> Path:
    """Ruta sibling única para un evento inmutable de la ejecución."""
    execution_seguro = re.sub(r"[^A-Za-z0-9_.-]+", "_", execution_id)
    evento_seguro = re.sub(r"[^A-Za-z0-9_.-]+", "_", evento)
    return ruta_canonica.with_name(
        f"{ruta_canonica.stem}.{execution_seguro}.{evento_seguro}.json"
    )


def _ruta_trabajo_dia(fecha: str, flujo: str) -> Path:
    flujo_seguro = re.sub(r"[^A-Za-z0-9_.-]+", "_", flujo)
    return TRABAJO / flujo_seguro / fecha


def _archivos_presentes(carpeta: Path) -> list[dict]:
    """Inventario conservador del crudo presente, sin atribuirle procedencia."""
    if not carpeta.is_dir():
        return []
    out = []
    for path in sorted((p for p in carpeta.rglob("*") if p.is_file()),
                       key=lambda p: str(p.relative_to(carpeta))):
        out.append({
            "archivo": path.name,
            "ruta_relativa": str(path.relative_to(carpeta)),
            "bytes": int(path.stat().st_size),
        })
    return out


def _particion_reutilizable_sin_crudo(
    *,
    carpeta: Path,
    destino: Path,
    fecha: str,
    flujo: str,
    manifiesto: Manifiesto,
    audit_path: Path,
) -> bool:
    """Una fuente pendiente siempre prevalece sobre un canónico previo válido."""
    if _archivos_presentes(carpeta):
        return False
    return _particion_valida(destino, fecha, flujo, manifiesto, audit_path)


def _verificar_crudos_para_wal(
    carpeta: Path,
    granulos: list[dict],
) -> list[dict]:
    """Exige que todo archivo a retirar esté identificado y checksummeado.

    Un residuo de una ejecución previa no puede eliminarse bajo el WAL de la
    ejecución actual. Por eso la igualdad entre archivos presentes y gránulos
    descargados es estricta, incluyendo bytes y SHA-256.
    """
    presentes = [p for p in carpeta.rglob("*") if p.is_file()]
    por_nombre: dict[str, Path] = {}
    duplicados: set[str] = set()
    for path in presentes:
        if path.name in por_nombre:
            duplicados.add(path.name)
        por_nombre[path.name] = path
    if duplicados:
        raise RuntimeError(
            "fuentes crudas duplicadas no atribuibles: " + ", ".join(sorted(duplicados))
        )

    esperados: dict[str, dict] = {}
    incompletos = []
    for item in granulos:
        nombre = str(item.get("archivo_descargado") or "")
        sha = str(item.get("sha256_descargado") or "")
        try:
            nbytes = int(item.get("bytes_descargados"))
        except (TypeError, ValueError):
            nbytes = -1
        if not nombre or len(sha) != 64 or nbytes < 0:
            incompletos.append(nombre or str(item.get("concept_id") or "sin-id"))
            continue
        if nombre in esperados:
            raise RuntimeError(f"gránulo descargado duplicado en WAL: {nombre}")
        esperados[nombre] = item
    if incompletos:
        raise RuntimeError(
            "gránulos sin identidad/checksum durable: " + ", ".join(sorted(incompletos))
        )

    faltan = sorted(set(esperados) - set(por_nombre))
    extras = sorted(set(por_nombre) - set(esperados))
    if faltan or extras:
        detalle = []
        if faltan:
            detalle.append(f"faltan {faltan}")
        if extras:
            detalle.append(f"extras no auditados {extras}")
        raise RuntimeError("crudo presente no coincide con el WAL: " + "; ".join(detalle))

    verificados = []
    for nombre in sorted(esperados):
        path = por_nombre[nombre]
        item = esperados[nombre]
        bytes_actuales = int(path.stat().st_size)
        sha_actual = sha256_archivo(path)
        if bytes_actuales != int(item["bytes_descargados"]):
            raise RuntimeError(f"tamaño de crudo cambió antes del WAL: {nombre}")
        if sha_actual != str(item["sha256_descargado"]):
            raise RuntimeError(f"hash de crudo cambió antes del WAL: {nombre}")
        verificados.append({
            "archivo": nombre,
            "ruta_relativa": str(path.relative_to(carpeta)),
            "bytes": bytes_actuales,
            "sha256": sha_actual,
        })
    return verificados


def _auditar(
    *,
    destino: Path | None,
    ruta: Path,
    execution_id: str,
    codigo_archivo: Path,
    codigo_sha256: str,
    fecha: str,
    sensor: str,
    short_name: str,
    version: str,
    granulos: list[dict],
    pixeles: pd.DataFrame | None,
    mask_sha256: str,
    estado: str,
    raw_eliminado: bool,
    error: str = "",
    transaccion: dict | None = None,
    seleccion_granulos: dict | None = None,
) -> str:
    cobertura = cobertura_territorios(
        [] if pixeles is None else pixeles.get("territorio", []),
    )
    tiempos = [] if pixeles is None else pd.to_datetime(
        pixeles["ts_utc"], utc=True, errors="coerce",
    ).dropna()
    fuentes_sds = [] if pixeles is None else sorted(
        set(pixeles.get("fuente", pd.Series(dtype=str)).astype(str))
    )
    fuente_a_sds = {
        "DT_DB_combined": SDS_COMBINADO,
        "dark_target": SDS_DT,
    }
    fuentes_tiempo = [] if pixeles is None else sorted(
        set(pixeles.get("tiempo_fuente", pd.Series(dtype=str)).astype(str))
    )
    documento = {
        "schema": "airpollution.satellite-file-manifest.v1",
        "execution_id": execution_id,
        "creado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        # Ambos valores se fijan una vez al comienzo de la ejecución. Así, una
        # edición o sincronización posterior del .py no mezcla procedencias
        # distintas dentro del mismo execution_id.
        "codigo": {"archivo": str(codigo_archivo), "sha256": codigo_sha256},
        "producto": short_name,
        "coleccion": version,
        "sensor": sensor,
        "fecha_adquisicion": fecha,
        "resolucion_nominal_m": 3000,
        "tiempo_nativo": {
            "escala": "TAI93 cuando Scan_Start_Time existe; convertido a UTC",
            "fuentes": fuentes_tiempo,
            "min_utc": "" if len(tiempos) == 0 else tiempos.min().isoformat(),
            "max_utc": "" if len(tiempos) == 0 else tiempos.max().isoformat(),
        },
        "aoi_busqueda": [list(b) for b in BBOX_CHILE],
        "mascara": {
            "archivo": str(SHP), "sha256_componentes": mask_sha256,
            "criterio": "centro de pixel intersecta poligono comunal; sin Antartica",
            "cod_cero": "se conserva como Zona sin demarcar (no es NaN)",
        },
        "qa": {
            "politica": "AOD fisicamente valido; QA crudo conservado",
            "sds_aod_usados": [fuente_a_sds.get(x, x) for x in fuentes_sds],
            "sds_qa": [SDS_COMBINADO_QA, SDS_DT_QA],
        },
        "granulos": granulos,
        "filas_pixeles": 0 if pixeles is None else int(len(pixeles)),
        "cobertura_por_territorio": cobertura,
        "territorios_sin_cobertura": [k for k, v in cobertura.items() if v == 0],
        "salida": None if destino is None else {
            "archivo": str(destino),
            "sha256": sha256_archivo(destino),
            "formato": "Parquet ZSTD",
        },
        "validacion": estado in {"ok", "sin_datos", "no_disponible"},
        "estado": estado,
        "crudo_eliminado": bool(raw_eliminado),
        "error": error,
    }
    if transaccion is not None:
        documento["transaccion"] = transaccion
    if seleccion_granulos is not None:
        documento["seleccion_granulos"] = seleccion_granulos
    return escribir_json_atomico(documento, ruta)


def _auditar_inmutable(*, ruta: Path, **kwargs) -> str:
    """Persiste un sidecar una sola vez; el lock evita carreras entre writers."""
    if ruta.exists():
        raise FileExistsError(f"evento de auditoría ya existe: {ruta}")
    return _auditar(ruta=ruta, **kwargs)


def _confirmar_particion(
    *,
    area: AreaTrabajo,
    carpeta: Path,
    destino: Path | None,
    audit_path: Path,
    estado: str,
    filas: int,
    sha_salida: str,
    manifiesto: Manifiesto,
    flujo: str,
    auditoria: dict,
) -> tuple[Path, str]:
    """WAL durable → retiro estricto del crudo → canónico → ledger."""
    if estado not in {"ok", "sin_datos"}:
        raise ValueError(f"estado no confirmable: {estado}")
    if estado == "ok":
        if destino is None or not destino.is_file():
            raise FileNotFoundError("salida MODIS validada ausente antes del WAL")
        if sha256_archivo(destino) != sha_salida:
            raise RuntimeError("hash de salida cambió antes del WAL")
    elif destino is not None or filas != 0 or sha_salida:
        raise ValueError("sin_datos no puede confirmar salida/filas/hash")

    crudos = _verificar_crudos_para_wal(carpeta, auditoria["granulos"])
    wal_path = _ruta_evento_auditoria(
        audit_path, auditoria["execution_id"], "pre_borrado",
    )
    sha_wal = _auditar_inmutable(
        destino=destino,
        ruta=wal_path,
        estado=estado,
        raw_eliminado=False,
        transaccion={
            "evento": "particion_validada_pre_borrado",
            "crudo_directorio": str(carpeta),
            "archivos_crudos_verificados": crudos,
        },
        **auditoria,
    )

    area.limpiar_dia(carpeta)
    if carpeta.exists():
        raise OSError(f"persisten fuentes después de limpieza validada: {carpeta}")

    sha_audit = _auditar(
        destino=destino,
        ruta=audit_path,
        estado=estado,
        raw_eliminado=True,
        transaccion={
            "evento": "crudo_eliminado_post_validacion",
            "wal": {"archivo": str(wal_path), "sha256": sha_wal},
        },
        **auditoria,
    )
    sha_compuesto = sha_audit if estado == "sin_datos" \
        else f"{sha_salida}+{sha_audit}"
    manifiesto.marcar(flujo=flujo, estado=estado, filas=filas,
                      sha256=sha_compuesto, fecha=auditoria["fecha"])
    return wal_path, sha_audit


def _registrar_error_sidecar(
    *,
    carpeta: Path,
    destino: Path,
    audit_path: Path,
    salida_nueva_publicada: bool,
    fase: str,
    error: str,
    auditoria: dict,
) -> tuple[Path, str]:
    """Registra un fallo sin sobrescribir el WAL ni el canónico del día."""
    execution_id = auditoria["execution_id"]
    wal_path = _ruta_evento_auditoria(audit_path, execution_id, "pre_borrado")
    error_path = _ruta_evento_auditoria(audit_path, execution_id, "error")
    wal_ref = None
    if wal_path.is_file():
        wal_ref = {"archivo": str(wal_path), "sha256": sha256_archivo(wal_path)}
    crudo_eliminado = bool(wal_ref is not None and not carpeta.exists())
    presentes = _archivos_presentes(carpeta)
    transaccion = {
        "evento": "particion_fallida",
        "fase": fase,
        "salida_nueva_publicada": bool(salida_nueva_publicada),
        "crudo_directorio": str(carpeta),
        "crudo_preservado": bool(presentes),
        "archivos_crudos_presentes": presentes,
        "wal": wal_ref,
    }
    datos = dict(auditoria)
    if not salida_nueva_publicada:
        datos["pixeles"] = None
    sha_error = _auditar_inmutable(
        destino=destino if salida_nueva_publicada else None,
        ruta=error_path,
        estado="error",
        raw_eliminado=crudo_eliminado,
        error=error,
        transaccion=transaccion,
        **datos,
    )
    return error_path, sha_error


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sensor", default="terra,aqua",
                   help="terra, aqua o ambos separados por coma")
    p.add_argument("--desde", default="2000-01-01", help="YYYY-MM-DD")
    p.add_argument("--hasta", default=date.today().isoformat(), help="YYYY-MM-DD")
    p.add_argument("--force", action="store_true",
                   help="reprocesa el rango; la salida anterior sólo cambia al validar")
    p.add_argument("--reserva-gb", type=float, default=100.0,
                   help="aborta limpiamente antes de bajar si queda menos espacio")
    p.add_argument("--dry-run", action="store_true",
                   help="no autentica, descarga, escribe ni limpia")
    return p


def main(argv=None) -> int:
    # Se captura antes de autenticar o tocar datos: toda la ejecución conserva
    # una única identidad de código aunque el archivo se sincronice después.
    codigo_archivo = Path(__file__).resolve()
    codigo_sha256 = sha256_archivo(codigo_archivo)
    selector_archivo = Path(producciones_modis.__file__).resolve()
    selector_codigo = {
        "archivo": str(selector_archivo),
        "sha256": sha256_archivo(selector_archivo),
    }
    args = _parser().parse_args(argv)
    sensores = [s.strip().lower() for s in args.sensor.split(",") if s.strip()]
    invalidos = [s for s in sensores if s not in PRODUCTOS]
    if invalidos:
        raise SystemExit(f"sensores inválidos: {invalidos}")
    try:
        dias = list(fechas_inclusivas(args.desde, args.hasta))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    log.info("MODIS píxel/pasada: %s→%s; sensores=%s; %d días",
             dias[0], dias[-1], ",".join(sensores), len(dias))
    log.info("Parquet ZSTD externo: %s", SALIDA)
    if args.dry_run:
        log.info("[dry-run] crudo efímero=%s; manifiesto=%s", TRABAJO, MANIFIESTO)
        return 0

    requerir_modulos("earthaccess", "pyhdf", "geopandas", "pyarrow")
    login()
    import earthaccess

    comunas = cargar_comunas(SHP)
    limpiar_parciales(
        SALIDA, AUDITORIA, MANIFIESTO.with_name(MANIFIESTO.name + ".part"),
    )
    manifiesto = Manifiesto(MANIFIESTO)
    execution_id = str(uuid.uuid4())
    mask_componentes = componentes_shapefile(SHP)
    mask_sha256 = sha256_conjunto(mask_componentes)
    errores = []
    try:
        with BloqueoProceso(BASE / ".descargar_pixeles.lock"), \
                AreaTrabajo(TRABAJO, preservar_no_validados=True) as area:
            for dia in dias:
                fecha = dia.isoformat()
                for sensor in sensores:
                    short, version, satelite, lanzamiento = PRODUCTOS[sensor]
                    flujo = sensor
                    destino = salida_diaria(
                        SALIDA, fecha, f"modis_aod3k_{sensor}_{dia:%Y%m%d}",
                    )
                    audit_path = _ruta_auditoria(fecha, sensor)
                    if dia < lanzamiento:
                        if args.force or not _particion_valida(
                                destino, fecha, flujo, manifiesto, audit_path):
                            sha_audit = _auditar(
                                destino=None, ruta=audit_path,
                                execution_id=execution_id,
                                codigo_archivo=codigo_archivo,
                                codigo_sha256=codigo_sha256, fecha=fecha,
                                sensor=sensor, short_name=short, version=version,
                                granulos=[], pixeles=None,
                                mask_sha256=mask_sha256,
                                estado="no_disponible", raw_eliminado=True,
                            )
                            manifiesto.marcar(fecha, flujo, "sin_datos", 0, sha_audit)
                        continue
                    carpeta_pendiente = _ruta_trabajo_dia(fecha, flujo)
                    crudos_pendientes = _archivos_presentes(carpeta_pendiente)
                    if not args.force and _particion_reutilizable_sin_crudo(
                            carpeta=carpeta_pendiente, destino=destino,
                            fecha=fecha, flujo=flujo, manifiesto=manifiesto,
                            audit_path=audit_path):
                        log.info("%s [%s]: ✓ partición validada", fecha, satelite)
                        continue
                    if crudos_pendientes:
                        log.warning(
                            "%s [%s]: se reintenta porque hay %d fuente(s) "
                            "no validada(s) preservada(s)",
                            fecha, satelite, len(crudos_pendientes),
                        )
                    libres = shutil.disk_usage(BASE).free / (1024 ** 3)
                    if libres < args.reserva_gb:
                        log.error(
                            "espacio libre %.1f GiB < reserva %.1f GiB; paro sin bajar HDF",
                            libres, args.reserva_gb,
                        )
                        return 2
                    carpeta = area.carpeta_dia(fecha, flujo)
                    granulos_desc: list[dict] = []
                    seleccion_granulos = {
                        "estado": "pendiente", "codigo": selector_codigo,
                    }
                    pixeles: pd.DataFrame | None = None
                    salida_nueva_publicada = False
                    salida_previa_observada = False
                    sha_salida_previa = ""
                    fase = "busqueda_cmr"
                    try:
                        granulos = _buscar_dia(earthaccess, short, version, dia)
                        granulos_desc = describir_granulos(granulos)
                        if not granulos:
                            # Un satélite polar ofrece cobertura diaria. Cero
                            # resultados CMR es latencia/falla reintentable, no
                            # evidencia científica de ausencia de AOD.
                            raise RuntimeError(
                                "CMR no devolvió gránulos; no se marca el día "
                                "como completo"
                            )
                        fase = "seleccion_produccion_nativa"
                        granulos, seleccion_granulos = (
                            producciones_modis.seleccionar_produccion_nativa(
                                granulos, producto=short, coleccion=version,
                                fecha=fecha,
                            )
                        )
                        seleccion_granulos = {
                            **seleccion_granulos, "codigo": selector_codigo,
                        }
                        granulos_desc = describir_granulos(granulos)
                        # La decisión y sus candidatos quedan durables antes
                        # de transferir HDF, incluso si la descarga se corta.
                        fase = "auditoria_seleccion_pre_descarga"
                        seleccion_path = _ruta_evento_auditoria(
                            audit_path, execution_id, "seleccion",
                        )
                        sha_seleccion = _auditar_inmutable(
                            destino=None, ruta=seleccion_path,
                            execution_id=execution_id,
                            codigo_archivo=codigo_archivo,
                            codigo_sha256=codigo_sha256, fecha=fecha,
                            sensor=sensor, short_name=short, version=version,
                            granulos=granulos_desc, pixeles=None,
                            mask_sha256=mask_sha256, estado="seleccionado",
                            raw_eliminado=False,
                            transaccion={
                                "evento": "seleccion_produccion_pre_descarga",
                            },
                            seleccion_granulos=seleccion_granulos,
                        )
                        seleccion_granulos = {
                            **seleccion_granulos,
                            "registro_pre_descarga": {
                                "archivo": str(seleccion_path),
                                "sha256": sha_seleccion,
                            },
                        }
                        fase = "descarga_crudo"
                        paths = _descargar(earthaccess, granulos, carpeta,
                                           f"{short} {fecha}")
                        # CMR suele omitir el checksum. Se calcula sobre cada
                        # HDF local antes de procesarlo y borrarlo.
                        granulos_desc = anotar_checksums_descargados(
                            granulos_desc, paths,
                        )
                        fase = "procesamiento_pixeles"
                        pixeles = _procesar(paths, satelite, comunas)
                        auditoria_base = {
                            "execution_id": execution_id,
                            "codigo_archivo": codigo_archivo,
                            "codigo_sha256": codigo_sha256,
                            "fecha": fecha,
                            "sensor": sensor,
                            "short_name": short,
                            "version": version,
                            "granulos": granulos_desc,
                            "pixeles": None if pixeles.empty else pixeles,
                            "mask_sha256": mask_sha256,
                            "seleccion_granulos": seleccion_granulos,
                        }
                        if pixeles.empty:
                            fase = "confirmacion_sin_datos"
                            _confirmar_particion(
                                area=area, carpeta=carpeta, destino=None,
                                audit_path=audit_path, estado="sin_datos",
                                filas=0, sha_salida="", manifiesto=manifiesto,
                                flujo=flujo, auditoria=auditoria_base,
                            )
                            log.info("%s [%s]: sin píxeles AOD dentro de comunas", fecha, satelite)
                            continue
                        fase = "publicacion_salida"
                        salida_previa_observada = True
                        sha_salida_previa = (
                            sha256_archivo(destino) if destino.is_file() else ""
                        )
                        filas, sha = escribir_parquet_atomico(
                            pixeles, destino, COLUMNAS, _validar,
                            columnas_validacion=COLUMNAS_VALIDACION,
                        )
                        salida_nueva_publicada = True
                        fase = "wal_y_confirmacion"
                        _confirmar_particion(
                            area=area, carpeta=carpeta, destino=destino,
                            audit_path=audit_path, estado="ok", filas=filas,
                            sha_salida=sha, manifiesto=manifiesto, flujo=flujo,
                            auditoria=auditoria_base,
                        )
                        log.info("%s [%s]: %s píxeles nativos", fecha, satelite,
                                 f"{filas:,}")
                    except BaseException as exc:
                        msg = f"{fecha} [{satelite}]: {type(exc).__name__}: {exc}"
                        if salida_previa_observada and not salida_nueva_publicada \
                                and destino.is_file():
                            # escribir_parquet_atomico puede fallar al revalidar
                            # después de os.replace: detecta esa publicación aun
                            # cuando la llamada no alcanzó a retornar.
                            try:
                                salida_nueva_publicada = (
                                    sha256_archivo(destino) != sha_salida_previa
                                )
                            except BaseException:
                                salida_nueva_publicada = False
                        auditoria_error = {
                            "execution_id": execution_id,
                            "codigo_archivo": codigo_archivo,
                            "codigo_sha256": codigo_sha256,
                            "fecha": fecha,
                            "sensor": sensor,
                            "short_name": short,
                            "version": version,
                            "granulos": granulos_desc,
                            "pixeles": pixeles,
                            "mask_sha256": mask_sha256,
                            "seleccion_granulos": seleccion_granulos,
                        }
                        sha_error = ""
                        try:
                            error_path, sha_error = _registrar_error_sidecar(
                                carpeta=carpeta, destino=destino,
                                audit_path=audit_path,
                                salida_nueva_publicada=salida_nueva_publicada,
                                fase=fase, error=msg, auditoria=auditoria_error,
                            )
                            log.error("%s; evidencia=%s", msg, error_path)
                        except BaseException as audit_exc:
                            log.error(
                                "%s; además falló el sidecar de error (%s: %s); "
                                "las fuentes no validadas permanecen en %s",
                                msg, type(audit_exc).__name__, audit_exc, carpeta,
                            )
                        try:
                            manifiesto.marcar(
                                fecha, flujo, "error", 0, sha_error,
                            )
                        except BaseException as ledger_exc:
                            log.error(
                                "%s; además falló registrar error en ledger (%s: %s)",
                                msg, type(ledger_exc).__name__, ledger_exc,
                            )
                        if isinstance(exc, KeyboardInterrupt):
                            raise
                        if not isinstance(exc, Exception):
                            raise
                        errores.append(msg)
                        log.error(msg)
    except KeyboardInterrupt:
        log.warning(
            "interrumpido: fuentes HDF no validadas preservadas; "
            "los Parquet .part fueron retirados"
        )
        return 130

    if errores:
        log.error("%d caso(s) reintentables; primera falla: %s",
                  len(errores), errores[0])
        return 1
    log.info(
        "Listo: HDF de particiones confirmadas retirados; cualquier fuente "
        "no validada permanece para recuperación."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
