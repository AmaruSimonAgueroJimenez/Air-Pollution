#!/usr/bin/env python3
"""MAIAC MCD19A2 1 km: cada píxel/pasada, normalizado y sin HDF residuales.

La comuna funciona como máscara/etiqueta; no se promedia espacialmente. Para
que 2000–2026 quepa en disco sin repetir miles de millones de veces la misma
geografía, la salida está normalizada en tres conjuntos Parquet ZSTD:

``catalogo_pixeles/tile=.../pixeles.parquet``
    ``pixel_id`` uint32 → tile, fila, columna, lat, lon, cod_comuna (una vez).
``catalogo_pasadas/year=.../.../maiac_pasadas_YYYYMMDD.parquet``
    ``overpass_id`` uint32 → timestamp UTC exacto y satélite.
``observaciones/year=.../.../maiac_obs_YYYYMMDD.parquet``
    overpass_id, pixel_id, AOD 550 nm float32 y QA uint16.

Todos los AOD físicamente válidos quedan disponibles; QA no se descarta y se
decodifica después si el modelo necesita un filtro. Cada salida diaria se
publica atómicamente y se vuelve a leer antes de eliminar los HDF. El crudo
vive sólo en ``_trabajo_descarga`` y se retira explícitamente después de
persistir un WAL con sus hashes; fallos y señales preservan lo no validado. El
manifiesto permite reanudar sin repetir días ya verificados. Parciales previos
y publicaciones incompletas bloquean el reintento sin alterar sus bytes;
requieren recuperación específica con el WAL. Nunca se usa ``raw_chile``.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
import uuid
from datetime import date, datetime, time as dt_time, timedelta, timezone
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
    fechas_inclusivas,
    requerir_modulos,
    salida_diaria,
    sha256_archivo,
    sha256_conjunto,
    territorio_desde_lonlat,
    validar_parquet,
)

log = get_logger("maiac_aod_pixeles")

BASE = CONTAMINANTES / "MCD19A2.061"
TRABAJO = BASE / "_trabajo_descarga"
RAIZ_SALIDA = BASE / "pixeles_horario"
OBSERVACIONES = RAIZ_SALIDA / "observaciones"
CATALOGO_PASADAS = RAIZ_SALIDA / "catalogo_pasadas"
CATALOGO_PIXELES = RAIZ_SALIDA / "catalogo_pixeles"
MANIFIESTO = BASE / "manifest_pixeles_horario.csv"
AUDITORIA = BASE / "manifiestos_pixeles_horario"
SHP = DATA / "comunas.shp"
FLUJO = "mcd19a2_normalizado"
LANZAMIENTO = date(2000, 2, 24)

BBOX_CHILE = (
    tuple(bbox_earthaccess()),
    (-81.2, -34.1, -78.5, -26.0),       # Juan Fernández + Desventuradas
    (-109.8, -27.6, -105.0, -26.2),     # Rapa Nui + Sala y Gómez
)

N_TILE = 1200
N_COLUMNAS_GLOBALES = 36 * N_TILE
EPOCA_ID = datetime(2000, 1, 1, tzinfo=timezone.utc)

COLUMNAS_OBS = ("overpass_id", "pixel_id", "aod055", "qa_raw")
COLUMNAS_PASADAS = (
    "overpass_id", "ts_utc", "fecha", "hora_utc", "minuto_utc",
    "satelite", "coleccion", "orbit_amount", "granulos",
)
COLUMNAS_CATALOGO = (
    "pixel_id", "tile", "fila", "columna", "lat", "lon", "cod_comuna",
    "etiqueta_comuna", "territorio",
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


def _buscar_dia(earthaccess, dia: date) -> list:
    inicio = datetime.combine(dia, dt_time.min)
    fin = datetime.combine(dia, dt_time.max)
    encontrados = []
    for bbox in BBOX_CHILE:
        encontrados.extend(_con_reintentos(
            f"CMR MCD19A2 {dia} {bbox}",
            lambda bbox=bbox: earthaccess.search_data(
                short_name="MCD19A2", version="061", bounding_box=bbox,
                temporal=(inicio, fin),
            ),
        ))
    return deduplicar_granulos(encontrados)


def _descargar(earthaccess, granulos: list, carpeta: Path, fecha: str) -> list[Path]:
    paths = _con_reintentos(
        f"descarga MCD19A2 {fecha}",
        lambda: earthaccess.download(granulos, local_path=str(carpeta)),
    )
    raiz = carpeta.resolve()
    out = []
    for item in paths or []:
        path = Path(item).resolve()
        if path.is_file() and (path.parent == raiz or raiz in path.parents):
            out.append(path)
    if granulos and not out:
        raise RuntimeError(f"Earthdata no dejó HDF para {fecha}")
    return out


def _subdataset(sds: list[str], nombre: str) -> str | None:
    return next((uri for uri in sds if uri.endswith(f":{nombre}")), None)


def _parse_orbit_ts(token: str) -> tuple[datetime, str] | None:
    """Interpreta YYYYDDDHHMM[SS]T/A del atributo Orbit_time_stamp."""
    m = re.fullmatch(r"(\d{4})(\d{3})(\d{2})(\d{2})(\d{2})?([TA])",
                     token.strip())
    if not m:
        return None
    year, doy, hh, mm, ss, plataforma = m.groups()
    ts = (datetime(int(year), 1, 1, int(hh), int(mm), int(ss or 0),
                   tzinfo=timezone.utc)
          + timedelta(days=int(doy) - 1))
    return ts, ("Terra" if plataforma == "T" else "Aqua")


def _overpass_id(ts: datetime, satelite: str) -> np.uint32:
    """ID determinista: segundos desde 2000 × 2 + bit de plataforma."""
    segundos = int((ts.astimezone(timezone.utc) - EPOCA_ID).total_seconds())
    valor = segundos * 2 + (1 if satelite == "Aqua" else 0)
    if not 0 <= valor <= np.iinfo(np.uint32).max:
        raise ValueError(f"timestamp fuera del rango de overpass_id: {ts}")
    return np.uint32(valor)


def _tile_indices(path: Path) -> tuple[str, int, int]:
    m = re.search(r"\.(h(\d{2})v(\d{2}))\.", path.name)
    if not m:
        raise ValueError(f"tile ausente en nombre: {path.name}")
    return m.group(1), int(m.group(2)), int(m.group(3))


def _pixel_ids(h: int, v: int, filas: np.ndarray,
               columnas: np.ndarray) -> np.ndarray:
    global_row = np.asarray(filas, dtype=np.uint64) + np.uint64(v * N_TILE)
    global_col = np.asarray(columnas, dtype=np.uint64) + np.uint64(h * N_TILE)
    ids = global_row * np.uint64(N_COLUMNAS_GLOBALES) + global_col
    if ids.size and ids.max() > np.iinfo(np.uint32).max:
        raise ValueError("pixel_id excede uint32")
    return ids.astype(np.uint32)


def _validar_catalogo(df: pd.DataFrame) -> None:
    if df.empty or df["pixel_id"].duplicated().any():
        raise ValueError("catálogo de píxeles vacío/duplicado")
    lat = pd.to_numeric(df["lat"], errors="coerce")
    lon = pd.to_numeric(df["lon"], errors="coerce")
    cod = pd.to_numeric(df["cod_comuna"], errors="coerce")
    if lat.isna().any() or lon.isna().any() or not lat.between(-90, 90).all() \
            or not lon.between(-180, 180).all():
        raise ValueError("coordenadas inválidas en catálogo")
    etiquetas = df["etiqueta_comuna"].astype("string")
    if cod.isna().any() or not (cod >= 0).all():
        raise ValueError("comuna inválida en catálogo")
    if etiquetas.isna().any() or (etiquetas.str.strip().str.len() == 0).any():
        raise ValueError("nombre/etiqueta comunal ausente en catálogo")
    if ((cod == 0) & ~etiquetas.str.contains(
            "sin demarcar", case=False, na=False)).any():
        raise ValueError("cod_comuna=0 sin etiqueta explícita de zona no demarcada")
    if not df["territorio"].isin(
            ["continente", "juan_fernandez", "desventuradas", "rapa_nui"]).all():
        raise ValueError("territorio inválido en catálogo")


def _validar_obs(df: pd.DataFrame) -> None:
    if df.empty or df.duplicated(["overpass_id", "pixel_id"]).any():
        raise ValueError("observaciones vacías/duplicadas")
    aod = pd.to_numeric(df["aod055"], errors="coerce")
    if aod.isna().any() or not aod.between(-0.1, 5.0).all():
        raise ValueError("AOD inválido")
    if pd.to_numeric(df["overpass_id"], errors="coerce").isna().any() \
            or pd.to_numeric(df["pixel_id"], errors="coerce").isna().any():
        raise ValueError("IDs inválidos")


def _validar_pasadas(df: pd.DataFrame) -> None:
    if df.empty or df["overpass_id"].duplicated().any():
        raise ValueError("catálogo de pasadas vacío/duplicado")
    ts = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
    if ts.isna().any() or not (ts.dt.strftime("%Y-%m-%d") ==
                               df["fecha"].astype(str)).all():
        raise ValueError("timestamp/fecha de pasada inválido")
    if not df["satelite"].isin(["Terra", "Aqua"]).all():
        raise ValueError("satélite inválido")
    horas = pd.to_numeric(df["hora_utc"], errors="coerce")
    minutos = pd.to_numeric(df["minuto_utc"], errors="coerce")
    if not (horas.to_numpy() == ts.dt.hour.to_numpy()).all() \
            or not (minutos.to_numpy() == ts.dt.minute.to_numpy()).all():
        raise ValueError("hora/minuto no coincide con timestamp UTC")
    esperados = np.array([
        _overpass_id(t.to_pydatetime(), sat)
        for t, sat in zip(ts, df["satelite"].astype(str))
    ], dtype=np.uint32)
    ids = pd.to_numeric(df["overpass_id"], errors="coerce")
    if ids.isna().any() or not np.array_equal(
            ids.to_numpy(dtype=np.uint32), esperados):
        raise ValueError("overpass_id no corresponde al timestamp/plataforma")


class CacheMascarasTile:
    """Máscara comunal y catálogo espacial calculados una vez por tile."""

    def __init__(self, comunas):
        self.comunas = comunas
        self._cache: dict[tuple, tuple[np.ndarray, np.ndarray, int, int]] = {}
        self._catalogos_cache: dict[tuple, Path] = {}
        self._catalogos_sha256: dict[tuple, str] = {}
        self.catalogos_usados: set[Path] = set()

    def obtener(self, da, tile: str, h: int, v: int
                ) -> tuple[np.ndarray, np.ndarray, int, int]:
        from pyproj import Transformer
        from rasterio.features import rasterize

        transform = da.rio.transform()
        crs = da.rio.crs
        if crs is None:
            raise ValueError(f"tile {tile} sin CRS")
        shape = (int(da.sizes["y"]), int(da.sizes["x"]))
        if shape != (N_TILE, N_TILE):
            raise ValueError(f"tile {tile} no tiene grilla {N_TILE}×{N_TILE}: {shape}")
        clave = (tile, shape, tuple(transform), str(crs))
        if clave in self._cache:
            # El registro diario se vacía entre fechas, pero la máscara se
            # reutiliza. Cada día debe conservar también su catálogo espacial.
            destino = self._catalogos_cache.get(clave)
            if destino is not None:
                if sha256_archivo(destino) != self._catalogos_sha256[clave]:
                    raise RuntimeError(f"catálogo cambió durante la ejecución: {destino}")
                self.catalogos_usados.add(destino)
            return self._cache[clave]

        comunas_proj = self.comunas.to_crs(crs)
        etiquetas = rasterize(
            ((geom, int(ci) + 1)
             for geom, ci in zip(comunas_proj.geometry, comunas_proj["_ci"])
             if geom is not None and not geom.is_empty),
            out_shape=shape, transform=transform, fill=0,
            all_touched=False, dtype="int32",
        )
        territorio_grid = np.full(shape, -1, dtype=np.int8)
        if not np.any(etiquetas):
            self._cache[clave] = (etiquetas, territorio_grid, h, v)
            return self._cache[clave]

        filas, columnas = np.where(etiquetas > 0)
        ci = etiquetas[filas, columnas].astype(np.int64) - 1
        xs = np.asarray(da["x"].values)[columnas]
        ys = np.asarray(da["y"].values)[filas]
        lon, lat = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform(xs, ys)
        territorios = territorio_desde_lonlat(lon, lat)
        mapa_territorios = {
            "continente": 0, "juan_fernandez": 1,
            "desventuradas": 2, "rapa_nui": 3,
        }
        territorio_grid[filas, columnas] = np.array(
            [mapa_territorios[t] for t in territorios], dtype=np.int8,
        )
        catalogo = pd.DataFrame({
            "pixel_id": _pixel_ids(h, v, filas, columnas),
            "tile": tile,
            "fila": filas.astype(np.uint16),
            "columna": columnas.astype(np.uint16),
            "lat": np.asarray(lat, dtype=np.float32),
            "lon": np.asarray(lon, dtype=np.float32),
            "cod_comuna": pd.to_numeric(
                self.comunas.iloc[ci]["cod_comuna"], errors="coerce"
            ).to_numpy(dtype=np.int32),
            "etiqueta_comuna": self.comunas.iloc[ci]["Comuna"].astype(str).to_numpy(),
            "territorio": territorios,
        }).loc[:, list(COLUMNAS_CATALOGO)]
        destino = CATALOGO_PIXELES / f"tile={tile}" / "pixeles.parquet"
        existente_ok = False
        if destino.exists():
            # Un catálogo previo es compartido por días ya publicados: nunca
            # reemplazarlo para reparar silenciosamente una discrepancia.
            validar_parquet(destino, COLUMNAS_CATALOGO, _validar_catalogo)
            pd.testing.assert_frame_equal(
                pd.read_parquet(destino).loc[:, list(COLUMNAS_CATALOGO)],
                catalogo, check_exact=True, check_dtype=True,
            )
            existente_ok = True
        if not existente_ok:
            escribir_parquet_atomico(
                catalogo, destino, COLUMNAS_CATALOGO, _validar_catalogo,
            )
        self.catalogos_usados.add(destino)
        self._catalogos_cache[clave] = destino
        self._catalogos_sha256[clave] = sha256_archivo(destino)
        # Sólo cachea después de asegurar que el catálogo normalizador existe.
        self._cache[clave] = (etiquetas, territorio_grid, h, v)
        return self._cache[clave]


def _leer_tile(path: Path, mascaras: CacheMascarasTile
               ) -> tuple[list[pd.DataFrame], list[dict]]:
    import rasterio
    import rioxarray

    tile, h, v = _tile_indices(path)
    with rasterio.open(path) as src:
        sds = src.subdatasets or []
        attrs = src.tags()
    if not attrs.get("Orbit_time_stamp"):
        # GDAL/HDF4 no siempre expone los atributos globales en el dataset raíz.
        try:
            from pyhdf.SD import SD, SDC
            hdf = SD(str(path), SDC.READ)
            try:
                attrs = {**attrs, **hdf.attributes()}
            finally:
                hdf.end()
        except Exception as exc:
            raise ValueError(
                f"no se pudo leer Orbit_time_stamp de {path.name}: {exc}"
            ) from exc
    stamps = str(attrs.get("Orbit_time_stamp", "")).split()
    orbit_amounts = str(attrs.get("Orbit_amount", "")).split()
    uri_aod = _subdataset(sds, "Optical_Depth_055")
    uri_qa = _subdataset(sds, "AOD_QA")
    if uri_aod is None or uri_qa is None:
        raise ValueError(f"Optical_Depth_055/AOD_QA ausente: {path.name}")
    aod = rioxarray.open_rasterio(uri_aod, masked=True, mask_and_scale=True)
    qa = rioxarray.open_rasterio(uri_qa, masked=False, mask_and_scale=False)
    try:
        if "band" not in aod.dims:
            aod = aod.expand_dims("band")
        if "band" not in qa.dims:
            qa = qa.expand_dims("band")
        nband_aod = int(aod.sizes["band"])
        nband_qa = int(qa.sizes["band"])
        if nband_aod != nband_qa:
            raise ValueError(
                f"Optical_Depth_055 tiene {nband_aod} bandas y AOD_QA "
                f"{nband_qa}; se rechaza cobertura parcial"
            )
        nband = nband_aod
        if len(stamps) < nband:
            raise ValueError(
                f"Orbit_time_stamp tiene {len(stamps)} sellos para {nband} bandas"
            )
        etiquetas, territorio_grid, _, _ = mascaras.obtener(
            aod.isel(band=0), tile, h, v,
        )
        if not np.any(etiquetas):
            return [], []
        partes, pasadas = [], []
        for bi in range(nband):
            parsed = _parse_orbit_ts(stamps[bi])
            if parsed is None:
                raise ValueError(f"Orbit_time_stamp inválido: {stamps[bi]!r}")
            ts, satelite = parsed
            vals = np.asarray(aod.isel(band=bi).values, dtype=np.float32)
            qraw = np.asarray(qa.isel(band=bi).values, dtype=np.uint16)
            if vals.shape != etiquetas.shape or qraw.shape != etiquetas.shape:
                raise ValueError(f"dimensiones incompatibles: {path.name}")
            valido = np.isfinite(vals) & (vals >= -0.1) & (vals <= 5.0)
            valido &= etiquetas > 0
            filas, columnas = np.where(valido)
            if not len(filas):
                continue
            overpass_id = _overpass_id(ts, satelite)
            partes.append(pd.DataFrame({
                "overpass_id": overpass_id,
                "pixel_id": _pixel_ids(h, v, filas, columnas),
                "aod055": vals[filas, columnas].astype(np.float32),
                "qa_raw": qraw[filas, columnas].astype(np.uint16),
                "_territorio": territorio_grid[filas, columnas].astype(np.int8),
            }))
            pasadas.append({
                "overpass_id": overpass_id,
                "ts_utc": pd.Timestamp(ts),
                "fecha": ts.strftime("%Y-%m-%d"),
                "hora_utc": np.uint8(ts.hour),
                "minuto_utc": np.uint8(ts.minute),
                "satelite": satelite,
                "coleccion": "MCD19A2.061",
                "orbit_amount": orbit_amounts[bi] if bi < len(orbit_amounts) else "",
                "granulos": path.name,
            })
        return partes, pasadas
    finally:
        aod.close()
        qa.close()


def _procesar(paths: list[Path], mascaras: CacheMascarasTile
              ) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    observaciones, pasadas, errores = [], [], []
    for path in paths:
        try:
            obs, pases = _leer_tile(path, mascaras)
            observaciones.extend(obs)
            pasadas.extend(pases)
        except Exception as exc:
            errores.append(f"{path.name}: {type(exc).__name__}: {exc}")
    if errores:
        raise RuntimeError("; ".join(errores[:3]))
    if not observaciones:
        return (pd.DataFrame(columns=COLUMNAS_OBS),
                pd.DataFrame(columns=COLUMNAS_PASADAS),
                cobertura_territorios([]))

    obs_ext = (pd.concat(observaciones, ignore_index=True)
               .drop_duplicates(["overpass_id", "pixel_id"], keep="last"))
    etiquetas_territorio = np.array(
        ["continente", "juan_fernandez", "desventuradas", "rapa_nui"],
        dtype=object,
    )
    codigos = obs_ext["_territorio"].to_numpy(dtype=np.int8)
    cobertura = cobertura_territorios(etiquetas_territorio[codigos])
    obs = (obs_ext.sort_values(["overpass_id", "pixel_id"], kind="stable")
           .loc[:, list(COLUMNAS_OBS)].reset_index(drop=True))
    pases = pd.DataFrame(pasadas)
    # Una pasada abarca varios tiles: conserva trazabilidad sin repetir filas.
    def unir_unicos(valores) -> str:
        return "|".join(sorted({str(x) for x in valores if str(x)}))

    # ``Orbit_amount`` puede diferir entre tiles de una misma pasada (o faltar
    # en uno de ellos). No forma parte de la identidad temporal: se agrega
    # junto con los gránulos para mantener exactamente una fila por overpass.
    pases = (pases.groupby(
        ["overpass_id", "ts_utc", "fecha", "hora_utc", "minuto_utc",
         "satelite", "coleccion"], as_index=False, observed=True,
    ).agg({"orbit_amount": unir_unicos, "granulos": unir_unicos})
             .sort_values("overpass_id", kind="stable")
             .loc[:, list(COLUMNAS_PASADAS)].reset_index(drop=True))
    _validar_obs(obs)
    _validar_pasadas(pases)
    ids_obs = set(obs["overpass_id"].astype("uint32").unique())
    ids_cat = set(pases["overpass_id"].astype("uint32"))
    if ids_obs != ids_cat:
        raise ValueError("observaciones y catálogo de pasadas no coinciden")
    return obs, pases, cobertura


def _destinos(fecha: str) -> tuple[Path, Path]:
    compacta = fecha.replace("-", "")
    return (
        salida_diaria(OBSERVACIONES, fecha, f"maiac_obs_{compacta}"),
        salida_diaria(CATALOGO_PASADAS, fecha, f"maiac_pasadas_{compacta}"),
    )


def _particion_valida(obs_path: Path, pas_path: Path, fecha: str,
                      manifiesto: Manifiesto, auditoria: Path) -> bool:
    reg = manifiesto.obtener(fecha, FLUJO)
    if reg and reg.estado == "sin_datos":
        try:
            doc = json.loads(auditoria.read_text(encoding="utf-8"))
            return bool(doc.get("validacion") and doc.get("crudo_eliminado")) and (
                not reg.sha256 or sha256_archivo(auditoria) == reg.sha256
            )
        except Exception:
            return False
    if not obs_path.exists() or not pas_path.exists():
        return False
    try:
        n_obs = validar_parquet(obs_path, COLUMNAS_OBS, _validar_obs)
        validar_parquet(pas_path, COLUMNAS_PASADAS, _validar_pasadas)
        if not auditoria.is_file():
            return False
        doc = json.loads(auditoria.read_text(encoding="utf-8"))
        hashes = {x.get("tipo"): x.get("sha256") for x in doc.get("salidas", [])}
        if not doc.get("validacion") or not doc.get("crudo_eliminado") \
                or hashes.get("observaciones") != sha256_archivo(obs_path) \
                or hashes.get("catalogo_pasadas") != sha256_archivo(pas_path):
            return False
        _validar_referencias_catalogos(
            doc.get("normalizacion", {}).get("catalogo_pixeles", []),
            set(pd.read_parquet(obs_path, columns=["pixel_id"])["pixel_id"]),
        )
        hash_compuesto = (
            f"{sha256_archivo(obs_path)}+{sha256_archivo(pas_path)}+"
            f"{sha256_archivo(auditoria)}"
        )
        if reg and reg.estado == "ok" and reg.sha256:
            return reg.filas == n_obs and reg.sha256 == hash_compuesto
        # Una publicación sin cierre de ledger requiere recuperación explícita;
        # este comprobador no inventa un cierre ni modifica el estado anterior.
        return False
    except Exception as exc:
        log.warning("partición previa inválida %s: %s", fecha, exc)
        return False


def _ruta_auditoria(fecha: str) -> Path:
    return salida_diaria(
        AUDITORIA, fecha, f"maiac_{fecha.replace('-', '')}",
    ).with_suffix(".json")


def _ruta_auditoria_ejecucion(
    fecha: str,
    execution_id: str,
    evento: str,
) -> Path:
    """Ruta hermana por ejecución; nunca sustituye el manifiesto canónico."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", execution_id):
        raise ValueError("execution_id inseguro para nombre de auditoría")
    if evento not in {"seleccion", "pre_borrado", "error"}:
        raise ValueError(f"evento de auditoría inválido: {evento}")
    canonica = _ruta_auditoria(fecha)
    return canonica.with_name(
        f"{canonica.stem}.{execution_id}.{evento}{canonica.suffix}"
    )


def _ruta_trabajo_dia(fecha: str) -> Path:
    seguro = re.sub(r"[^A-Za-z0-9_.-]+", "_", FLUJO)
    return TRABAJO / seguro / fecha


def _inventario_crudo(carpeta: Path) -> list[dict]:
    """Inventario no destructivo para sidecars de error y señales."""
    carpeta = Path(carpeta).resolve()
    if not carpeta.exists():
        return []
    inventario = []
    for path in sorted(carpeta.rglob("*")):
        if path.is_file():
            inventario.append({
                "archivo": str(path.resolve()),
                "bytes": int(path.stat().st_size),
            })
    return inventario


def _hay_fuentes_pendientes(carpeta: Path) -> bool:
    """Un crudo retenido obliga a reanudar el día aunque su salida sea válida."""
    return bool(_inventario_crudo(carpeta))


def _validar_referencias_catalogos(referencias: list[dict], pixel_ids: set) -> None:
    """Reabrir el catálogo exacto que permite interpretar cada observación."""
    disponibles = set()
    for referencia in referencias:
        path = Path(referencia["archivo"])
        if sha256_archivo(path) != referencia["sha256"]:
            raise RuntimeError(f"hash de catálogo no coincide: {path}")
        validar_parquet(path, COLUMNAS_CATALOGO, _validar_catalogo)
        ids = set(pd.read_parquet(path, columns=["pixel_id"])["pixel_id"])
        if disponibles.intersection(ids):
            raise ValueError("pixel_id repetido entre catálogos")
        disponibles.update(ids)
    if not pixel_ids.issubset(disponibles):
        raise ValueError("observaciones sin referencia en catálogos espaciales")


def _rechazar_parciales_pendientes() -> None:
    """Dentro del lock, preservar todo parcial de una ejecución anterior."""
    pendientes = []
    for raiz in (RAIZ_SALIDA, AUDITORIA):
        if raiz.exists():
            pendientes.extend(raiz.rglob("*.part"))
            pendientes.extend(raiz.rglob("*.part.parquet"))
    parcial_ledger = MANIFIESTO.with_name(MANIFIESTO.name + ".part")
    if parcial_ledger.exists():
        pendientes.append(parcial_ledger)
    if pendientes:
        raise RuntimeError(
            "se preservan parciales previos; requieren recuperación específica: "
            + ", ".join(str(p) for p in sorted(set(pendientes)))
        )


def _sincronizar_publicacion(archivos: dict[Path, str]) -> None:
    """Revalidar y hacer durables archivos y renombres antes de retirar HDF.

    Los escritores compartidos validan el contenido; aquí se sincronizan
    también los directorios nuevos de las particiones y sus ancestros. No
    modifica contenido, ni trata un fallo de fsync como autorización de retiro.
    """
    base = BASE.resolve()
    directorios = set()
    for path, esperado in archivos.items():
        path = path.resolve()
        if base not in path.parents:
            raise ValueError(f"publicación fuera de MAIAC: {path}")
        if sha256_archivo(path) != esperado:
            raise RuntimeError(f"publicación cambió antes de fsync: {path}")
        with path.open("rb") as fh:
            os.fsync(fh.fileno())
        padre = path.parent
        while True:
            directorios.add(padre)
            if padre == base:
                break
            padre = padre.parent
    for directorio in sorted(directorios, key=lambda p: (-len(p.parts), str(p))):
        fd = os.open(directorio, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    for path, esperado in archivos.items():
        if sha256_archivo(path) != esperado:
            raise RuntimeError(f"publicación cambió después de fsync: {path}")


def _verificar_codigo_actual(codigo_archivo: Path, codigo_sha256: str,
                             selector_codigo: dict) -> None:
    """No atribuir una publicación nueva a archivos cambiados durante el run."""
    for path, esperado in (
        (codigo_archivo, codigo_sha256),
        (Path(selector_codigo["archivo"]), selector_codigo["sha256"]),
    ):
        if sha256_archivo(path) != esperado:
            raise RuntimeError(f"código cambió durante la ejecución: {path}")


def _archivos_crudos_verificados(
    carpeta: Path,
    paths: list[Path],
    granulos: list[dict],
    *,
    recalcular_hashes: bool = True,
) -> list[dict]:
    """Exige que el día contenga exactamente las fuentes hasheadas del WAL.

    ``limpiar_dia`` retira la carpeta completa. Por eso ningún archivo ajeno a
    ``paths`` puede quedar implícitamente autorizado por el manifiesto.
    """
    raiz = Path(carpeta).resolve()
    esperados: dict[Path, Path] = {}
    for original in paths:
        path = Path(original)
        rp = path.resolve()
        if raiz not in rp.parents:
            raise ValueError(f"fuente fuera del día de trabajo: {path}")
        if rp in esperados:
            raise ValueError(f"fuente duplicada para borrado: {path}")
        if not path.is_file():
            raise FileNotFoundError(f"fuente descargada ausente: {path}")
        esperados[rp] = path

    presentes = {
        Path(item["archivo"]).resolve()
        for item in _inventario_crudo(raiz)
    }
    extras = sorted(str(p) for p in presentes - set(esperados))
    faltantes = sorted(str(p) for p in set(esperados) - presentes)
    if extras or faltantes:
        partes = []
        if extras:
            partes.append(f"archivos no auditados={extras}")
        if faltantes:
            partes.append(f"fuentes ausentes={faltantes}")
        raise RuntimeError(
            "se preserva el día: inventario crudo distinto de la descarga; "
            + "; ".join(partes)
        )

    por_nombre: dict[str, dict] = {}
    for item in granulos:
        nombre = str(item.get("archivo_descargado") or "")
        if not nombre:
            continue
        if nombre in por_nombre:
            raise ValueError(f"checksum duplicado para fuente: {nombre}")
        por_nombre[nombre] = item

    verificados = []
    for rp, path in sorted(esperados.items(), key=lambda x: x[0].name):
        item = por_nombre.get(path.name)
        sha = "" if item is None else str(item.get("sha256_descargado") or "")
        try:
            nbytes = int(item.get("bytes_descargados")) if item else -1
        except (TypeError, ValueError):
            nbytes = -1
        if not re.fullmatch(r"[0-9a-f]{64}", sha) or nbytes != path.stat().st_size:
            raise RuntimeError(
                f"se preserva el día: fuente sin hash/tamaño verificable: {path.name}"
            )
        if recalcular_hashes and sha256_archivo(path) != sha:
            raise RuntimeError(
                f"se preserva el día: cambió el hash de la fuente: {path.name}"
            )
        verificados.append({
            "archivo": str(rp),
            "bytes": nbytes,
            "sha256": sha,
        })
    if not verificados:
        raise RuntimeError("se preserva el día: no hay fuentes verificadas")
    return verificados


def _registro_manifiesto(registro) -> dict | None:
    if registro is None:
        return None
    return {
        "fecha": registro.fecha,
        "flujo": registro.flujo,
        "estado": registro.estado,
        "filas": int(registro.filas),
        "sha256": registro.sha256,
        "actualizado_utc": registro.actualizado_utc,
    }


def _auditar_inmutable(*, ruta: Path, **kwargs) -> str:
    """Publica una sola vez un WAL/sidecar identificado por ejecución."""
    if ruta.exists():
        raise FileExistsError(f"auditoría inmutable ya existe: {ruta}")
    sha = _auditar(ruta=ruta, **kwargs)
    if not ruta.is_file():
        raise OSError(f"auditoría inmutable no quedó publicada: {ruta}")
    return sha


def _auditar(
    *,
    ruta: Path,
    execution_id: str,
    codigo_archivo: Path,
    codigo_sha256: str,
    fecha: str,
    granulos: list[dict],
    obs_path: Path | None,
    pas_path: Path | None,
    pasadas: pd.DataFrame | None,
    cobertura: dict[str, int],
    catalogos_pixeles: list[Path],
    mask_sha256: str,
    estado: str,
    raw_eliminado: bool,
    error: str = "",
    transaccion: dict | None = None,
    seleccion_granulos: dict | None = None,
) -> str:
    tiempos = [] if pasadas is None else pd.to_datetime(
        pasadas["ts_utc"], utc=True, errors="coerce",
    ).dropna()
    salidas = []
    for path, tipo in ((obs_path, "observaciones"),
                       (pas_path, "catalogo_pasadas")):
        if path is not None:
            salidas.append({
                "tipo": tipo, "archivo": str(path),
                "sha256": sha256_archivo(path), "formato": "Parquet ZSTD",
            })
    documento = {
        "schema": "airpollution.satellite-file-manifest.v1",
        "execution_id": execution_id,
        "creado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        # Estos valores se capturan una sola vez al iniciar ``main``. Así una
        # sincronización o edición del archivo durante una descarga larga no
        # mezcla hashes de código dentro de la misma ejecución.
        "codigo": {"archivo": str(codigo_archivo), "sha256": codigo_sha256},
        "producto": "MCD19A2",
        "coleccion": "061",
        "fecha_adquisicion": fecha,
        "resolucion_nominal_m": 1000,
        "tiempo_nativo": {
            "fuente": "Orbit_time_stamp",
            "min_utc": "" if len(tiempos) == 0 else tiempos.min().isoformat(),
            "max_utc": "" if len(tiempos) == 0 else tiempos.max().isoformat(),
        },
        "aoi_busqueda": [list(b) for b in BBOX_CHILE],
        "mascara": {
            "archivo": str(SHP), "sha256_componentes": mask_sha256,
            "criterio": "centro de pixel rasterizado en comuna; sin Antartica",
            "cod_cero": "se conserva como Zona sin demarcar (no es NaN)",
        },
        "qa": {
            "politica": "todos los AOD fisicamente validos; QA uint16 conservado",
            "sds": ["Optical_Depth_055", "AOD_QA"],
        },
        "normalizacion": {
            "catalogo_pixeles": [
                {"archivo": str(p), "sha256": sha256_archivo(p)}
                for p in sorted(catalogos_pixeles)
            ],
            "observacion_columnas": list(COLUMNAS_OBS),
        },
        "granulos": granulos,
        "filas_pixeles": 0 if obs_path is None else int(sum(cobertura.values())),
        "cobertura_por_territorio": cobertura,
        "territorios_sin_cobertura": [k for k, v in cobertura.items() if v == 0],
        "salidas": salidas,
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


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--desde", default="2000-01-01", help="YYYY-MM-DD")
    p.add_argument("--hasta", default=date.today().isoformat(), help="YYYY-MM-DD")
    p.add_argument("--force", action="store_true",
                   help="no omite días; una publicación previa se protege y bloquea")
    p.add_argument("--reserva-gb", type=float, default=100.0,
                   help="aborta limpiamente antes de bajar si queda menos espacio")
    p.add_argument("--dry-run", action="store_true",
                   help="no autentica, descarga, escribe ni limpia")
    return p


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    codigo_archivo = Path(__file__).resolve()
    codigo_sha256 = sha256_archivo(codigo_archivo)
    selector_archivo = Path(producciones_modis.__file__).resolve()
    selector_codigo = {
        "archivo": str(selector_archivo),
        "sha256": sha256_archivo(selector_archivo),
    }
    try:
        dias = list(fechas_inclusivas(args.desde, args.hasta))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    log.info("MAIAC nativo normalizado: %s→%s; %d días",
             dias[0], dias[-1], len(dias))
    log.info("Parquet ZSTD externo: %s", RAIZ_SALIDA)
    if args.dry_run:
        log.info("[dry-run] crudo efímero=%s; manifiesto=%s", TRABAJO, MANIFIESTO)
        return 0

    requerir_modulos(
        "earthaccess", "rasterio", "rioxarray", "pyproj", "geopandas",
        "pyarrow", "pyhdf",
    )
    login()
    import earthaccess

    comunas = cargar_comunas(SHP)
    # Corrige geometrías administrativas problemáticas antes de rasterizar.
    comunas.geometry = comunas.geometry.make_valid()
    mascaras = CacheMascarasTile(comunas)
    execution_id = str(uuid.uuid4())
    mask_componentes = componentes_shapefile(SHP)
    mask_sha256 = sha256_conjunto(mask_componentes)
    errores = []
    try:
        with BloqueoProceso(BASE / ".descargar_pixeles.lock"), \
                AreaTrabajo(TRABAJO, preservar_no_validados=True) as area:
            _rechazar_parciales_pendientes()
            manifiesto = Manifiesto(MANIFIESTO)
            for dia in dias:
                fecha = dia.isoformat()
                obs_path, pas_path = _destinos(fecha)
                audit_path = _ruta_auditoria(fecha)
                carpeta = _ruta_trabajo_dia(fecha)
                fuentes_pendientes = _hay_fuentes_pendientes(carpeta)
                if dia < LANZAMIENTO and not fuentes_pendientes:
                    if args.force or not _particion_valida(
                            obs_path, pas_path, fecha, manifiesto, audit_path):
                        if any(p.exists() for p in (obs_path, pas_path, audit_path)):
                            log.error("%s: publicación previa protegida", fecha)
                            return 2
                        sha_audit = _auditar(
                            ruta=audit_path, execution_id=execution_id,
                            codigo_archivo=codigo_archivo,
                            codigo_sha256=codigo_sha256,
                            fecha=fecha, granulos=[], obs_path=None,
                            pas_path=None, pasadas=None,
                            cobertura=cobertura_territorios([]),
                            catalogos_pixeles=[],
                            mask_sha256=mask_sha256,
                            estado="no_disponible", raw_eliminado=True,
                            transaccion={"evento": "no_disponible_sin_crudo"},
                        )
                        manifiesto.marcar(fecha, FLUJO, "sin_datos", 0, sha_audit)
                    continue
                if dia < LANZAMIENTO:
                    log.error(
                        "%s: fuentes retenidas antes del lanzamiento; "
                        "se preservan y el día no puede saltarse",
                        fecha,
                    )
                if not args.force and not fuentes_pendientes and _particion_valida(
                        obs_path, pas_path, fecha, manifiesto, audit_path):
                    log.info("%s: ✓ observaciones/pasadas validadas", fecha)
                    continue
                if any(p.exists() for p in (obs_path, pas_path, audit_path)):
                    log.error(
                        "%s: publicación previa protegida; requiere recuperación "
                        "específica con su WAL, no se sustituye automáticamente",
                        fecha,
                    )
                    return 2
                if fuentes_pendientes:
                    log.warning(
                        "%s: hay fuentes retenidas; se reanuda aunque la "
                        "partición publicada pudiera ser válida",
                        fecha,
                    )
                libres = shutil.disk_usage(BASE).free / (1024 ** 3)
                if libres < args.reserva_gb:
                    log.error(
                        "espacio libre %.1f GiB < reserva %.1f GiB; paro sin bajar HDF",
                        libres, args.reserva_gb,
                    )
                    return 2
                granulos_desc: list[dict] = []
                seleccion_granulos = {
                    "estado": "pendiente", "codigo": selector_codigo,
                }
                paths: list[Path] = []
                pasadas: pd.DataFrame | None = None
                cobertura = cobertura_territorios([])
                registro_previo = _registro_manifiesto(
                    manifiesto.obtener(fecha, FLUJO)
                )
                wal_path = _ruta_auditoria_ejecucion(
                    fecha, execution_id, "pre_borrado",
                )
                error_path = _ruta_auditoria_ejecucion(
                    fecha, execution_id, "error",
                )
                wal_sha256 = ""
                fase = "preparar_dia"
                obs_publicada = False
                pas_publicada = False
                hashes_pre_publicacion: dict[Path, str | None] = {}
                raw_eliminado = False
                mascaras.catalogos_usados.clear()
                try:
                    carpeta = area.carpeta_dia(fecha, FLUJO)
                    fase = "consulta_cmr"
                    granulos = _buscar_dia(earthaccess, dia)
                    granulos_desc = describir_granulos(granulos)
                    if not granulos:
                        # MCD19A2 es un producto terrestre diario; cero
                        # resultados CMR indica latencia/falla reintentable.
                        raise RuntimeError(
                            "CMR no devolvió gránulos; no se marca el día "
                            "como completo"
                        )
                    fase = "seleccion_produccion_nativa"
                    granulos, seleccion_granulos = (
                        producciones_modis.seleccionar_produccion_nativa(
                            granulos, producto="MCD19A2", coleccion="061",
                            fecha=fecha,
                        )
                    )
                    seleccion_granulos = {
                        **seleccion_granulos, "codigo": selector_codigo,
                    }
                    granulos_desc = describir_granulos(granulos)
                    # Conservar la selección antes de abrir la transferencia;
                    # no equivale a confirmar la partición científica del día.
                    fase = "auditoria_seleccion_pre_descarga"
                    seleccion_path = _ruta_auditoria_ejecucion(
                        fecha, execution_id, "seleccion",
                    )
                    sha_seleccion = _auditar_inmutable(
                        ruta=seleccion_path, execution_id=execution_id,
                        codigo_archivo=codigo_archivo,
                        codigo_sha256=codigo_sha256, fecha=fecha,
                        granulos=granulos_desc, obs_path=None, pas_path=None,
                        pasadas=None, cobertura=cobertura,
                        catalogos_pixeles=[], mask_sha256=mask_sha256,
                        estado="seleccionado", raw_eliminado=False,
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
                    fase = "descarga"
                    paths = _descargar(earthaccess, granulos, carpeta, fecha)
                    # Conserva hash/tamaño verificables aunque CMR no publique
                    # checksum y el HDF se elimine al terminar el día.
                    fase = "checksums_fuente"
                    granulos_desc = anotar_checksums_descargados(
                        granulos_desc, paths,
                    )
                    fase = "procesamiento"
                    obs, pasadas, cobertura = _procesar(paths, mascaras)
                    fase = "validacion_catalogos_espaciales"
                    referencias_catalogos = [
                        {"archivo": str(p), "sha256": sha256_archivo(p)}
                        for p in sorted(mascaras.catalogos_usados)
                    ]
                    _validar_referencias_catalogos(
                        referencias_catalogos,
                        set(obs["pixel_id"]) if not obs.empty else set(),
                    )
                    fase = "verificar_codigo_pre_publicacion"
                    _verificar_codigo_actual(
                        codigo_archivo, codigo_sha256, selector_codigo,
                    )
                    estado_final = "sin_datos" if obs.empty else "ok"
                    n_obs = 0
                    sha_obs = ""
                    sha_pas = ""
                    pasadas_auditoria = None
                    obs_auditoria = None
                    pas_auditoria = None
                    if not obs.empty:
                        fase = "publicacion_catalogo_pasadas"
                        hashes_pre_publicacion[pas_path] = (
                            sha256_archivo(pas_path) if pas_path.is_file() else None
                        )
                        _, sha_pas = escribir_parquet_atomico(
                            pasadas, pas_path, COLUMNAS_PASADAS, _validar_pasadas,
                        )
                        pas_publicada = True
                        fase = "publicacion_observaciones"
                        hashes_pre_publicacion[obs_path] = (
                            sha256_archivo(obs_path) if obs_path.is_file() else None
                        )
                        n_obs, sha_obs = escribir_parquet_atomico(
                            obs, obs_path, COLUMNAS_OBS, _validar_obs,
                        )
                        obs_publicada = True
                        # Verificación relacional antes de autorizar el borrado.
                        fase = "validacion_relacional"
                        ids_obs = set(obs["overpass_id"].astype("uint32").unique())
                        ids_pas = set(pasadas["overpass_id"].astype("uint32"))
                        if ids_obs != ids_pas:
                            raise ValueError(
                                "catálogo de pasadas no cubre observaciones"
                            )
                        pasadas_auditoria = pasadas
                        obs_auditoria = obs_path
                        pas_auditoria = pas_path
                        fase = "verificacion_salidas_pre_wal"
                        if sha256_archivo(obs_path) != sha_obs \
                                or sha256_archivo(pas_path) != sha_pas:
                            raise RuntimeError(
                                "una salida cambió antes de persistir el WAL"
                            )

                    fase = "inventario_pre_wal"
                    archivos_crudos = _archivos_crudos_verificados(
                        carpeta, paths, granulos_desc,
                    )
                    transaccion_wal = {
                        "evento": "particion_validada_pre_borrado",
                        "crudo_directorio": str(carpeta.resolve()),
                        "archivos_crudos_verificados": archivos_crudos,
                    }
                    fase = "wal_pre_borrado"
                    wal_sha256 = _auditar_inmutable(
                        ruta=wal_path, execution_id=execution_id,
                        codigo_archivo=codigo_archivo,
                        codigo_sha256=codigo_sha256,
                        fecha=fecha, granulos=granulos_desc,
                        obs_path=obs_auditoria, pas_path=pas_auditoria,
                        pasadas=pasadas_auditoria, cobertura=cobertura,
                        catalogos_pixeles=sorted(mascaras.catalogos_usados),
                        mask_sha256=mask_sha256, estado=estado_final,
                        raw_eliminado=False, transaccion=transaccion_wal,
                        seleccion_granulos=seleccion_granulos,
                    )
                    fase = "inventario_post_wal"
                    if _archivos_crudos_verificados(
                            carpeta, paths, granulos_desc,
                            recalcular_hashes=False) != archivos_crudos:
                        raise RuntimeError(
                            "se preserva el día: el inventario cambió después del WAL"
                        )
                    # Un canónico validado y durable debe existir ANTES del
                    # primer retiro. Aún no declara que los HDF se eliminaron;
                    # si falla el cierre posterior, éste y el WAL son recuperables.
                    fase = "auditoria_canonica_pre_borrado"
                    sha_canonico_pre = _auditar(
                        ruta=audit_path, execution_id=execution_id,
                        codigo_archivo=codigo_archivo,
                        codigo_sha256=codigo_sha256,
                        fecha=fecha, granulos=granulos_desc,
                        obs_path=obs_auditoria, pas_path=pas_auditoria,
                        pasadas=pasadas_auditoria, cobertura=cobertura,
                        catalogos_pixeles=sorted(mascaras.catalogos_usados),
                        mask_sha256=mask_sha256,
                        estado=estado_final, raw_eliminado=False,
                        transaccion={
                            "evento": "publicacion_validada_pendiente_retiro",
                            "wal": {"archivo": str(wal_path),
                                    "sha256": wal_sha256},
                        },
                        seleccion_granulos=seleccion_granulos,
                    )
                    fase = "fsync_publicacion_pre_borrado"
                    # Los hashes de catálogos deben ser los ya comprometidos
                    # por el WAL, no una nueva identidad si cambiaron después.
                    wal_publicado = json.loads(wal_path.read_text(encoding="utf-8"))
                    if (wal_publicado["normalizacion"]["catalogo_pixeles"]
                            != referencias_catalogos):
                        raise RuntimeError("catálogos cambiaron entre validación y WAL")
                    durables = {
                        seleccion_path: sha_seleccion,
                        wal_path: wal_sha256,
                        audit_path: sha_canonico_pre,
                    }
                    for salida in wal_publicado["salidas"]:
                        durables[Path(salida["archivo"])] = salida["sha256"]
                    for catalogo in wal_publicado["normalizacion"]["catalogo_pixeles"]:
                        durables[Path(catalogo["archivo"])] = catalogo["sha256"]
                    _sincronizar_publicacion(durables)
                    fase = "rehash_fuentes_pre_retiro"
                    if _archivos_crudos_verificados(
                            carpeta, paths, granulos_desc,
                            recalcular_hashes=True) != archivos_crudos:
                        raise RuntimeError("fuentes cambiaron antes del retiro")
                    fase = "verificar_codigo_pre_retiro"
                    _verificar_codigo_actual(
                        codigo_archivo, codigo_sha256, selector_codigo,
                    )
                    fase = "limpieza_crudo"
                    area.limpiar_dia(carpeta)
                    raw_eliminado = True
                    fase = "auditoria_canonica"
                    sha_audit = _auditar(
                        ruta=audit_path, execution_id=execution_id,
                        codigo_archivo=codigo_archivo,
                        codigo_sha256=codigo_sha256,
                        fecha=fecha, granulos=granulos_desc,
                        obs_path=obs_auditoria, pas_path=pas_auditoria,
                        pasadas=pasadas_auditoria,
                        cobertura=cobertura,
                        catalogos_pixeles=sorted(mascaras.catalogos_usados),
                        mask_sha256=mask_sha256,
                        estado=estado_final, raw_eliminado=True,
                        transaccion={
                            "evento": "crudo_eliminado_post_validacion",
                            "wal": {
                                "archivo": str(wal_path),
                                "sha256": wal_sha256,
                            },
                        },
                        seleccion_granulos=seleccion_granulos,
                    )
                    fase = "ledger"
                    if estado_final == "ok":
                        manifiesto.marcar(
                            fecha, FLUJO, "ok", n_obs,
                            f"{sha_obs}+{sha_pas}+{sha_audit}",
                        )
                        log.info("%s: %s observaciones píxel/pasada",
                                 fecha, f"{n_obs:,}")
                    else:
                        manifiesto.marcar(
                            fecha, FLUJO, "sin_datos", 0, sha_audit,
                        )
                        log.info("%s: sin AOD válido dentro de comunas", fecha)
                except BaseException as exc:
                    # Nunca se limpia desde el camino de error/señal. Si el
                    # fallo es posterior a la limpieza autorizada, el WAL ya
                    # conserva las fuentes, salidas y hashes pre-borrado.
                    # os.replace puede haber publicado antes de que el escritor
                    # falle al volver a leer/hashear y retorne al llamador.
                    for ruta, previo in hashes_pre_publicacion.items():
                        try:
                            cambio = ruta.is_file() and sha256_archivo(ruta) != previo
                            if ruta == obs_path:
                                obs_publicada = obs_publicada or cambio
                            else:
                                pas_publicada = pas_publicada or cambio
                        except Exception as hash_exc:
                            log.error("%s: no se pudo verificar salida %s: %s",
                                      fecha, ruta, hash_exc)
                    inventario_presente = _inventario_crudo(carpeta)
                    if paths and not inventario_presente and not carpeta.exists():
                        raw_eliminado = True
                    msg = f"{fecha}: {type(exc).__name__}: {exc}"
                    wal_ref = None
                    if wal_path.is_file():
                        if not wal_sha256:
                            try:
                                wal_sha256 = sha256_archivo(wal_path)
                            except BaseException:
                                wal_sha256 = ""
                        wal_ref = {
                            "archivo": str(wal_path),
                            "sha256": wal_sha256,
                        }
                    transaccion_error = {
                        "evento": "particion_fallida",
                        "fase": fase,
                        "salida_nueva_publicada": bool(
                            obs_publicada or pas_publicada
                        ),
                        "salidas_publicadas": {
                            "observaciones": obs_publicada,
                            "catalogo_pasadas": pas_publicada,
                        },
                        "crudo_preservado": bool(inventario_presente),
                        "crudo_directorio": str(carpeta.resolve()),
                        "archivos_crudos_presentes": inventario_presente,
                        "wal": wal_ref,
                        "registro_ledger_previo": registro_previo,
                    }
                    sha_error = ""
                    try:
                        sha_error = _auditar_inmutable(
                            ruta=error_path, execution_id=execution_id,
                            codigo_archivo=codigo_archivo,
                            codigo_sha256=codigo_sha256,
                            fecha=fecha, granulos=granulos_desc,
                            obs_path=(obs_path if obs_publicada else None),
                            pas_path=(pas_path if pas_publicada else None),
                            pasadas=pasadas,
                            cobertura=cobertura,
                            catalogos_pixeles=sorted(mascaras.catalogos_usados),
                            mask_sha256=mask_sha256,
                            estado="error", raw_eliminado=raw_eliminado,
                            error=msg, transaccion=transaccion_error,
                            seleccion_granulos=seleccion_granulos,
                        )
                    except BaseException as audit_exc:
                        log.error(
                            "%s: no se pudo persistir sidecar de error: %s",
                            fecha, audit_exc,
                        )
                    try:
                        # Un --force puede haber publicado Parquet nuevos antes
                        # de fallar el WAL; no se conserva un estado ok obsoleto.
                        manifiesto.marcar(
                            fecha, FLUJO, "error", 0, sha_error,
                        )
                    except BaseException as ledger_exc:
                        log.error(
                            "%s: no se pudo marcar error en ledger: %s",
                            fecha, ledger_exc,
                        )
                    if not isinstance(exc, Exception):
                        raise
                    errores.append(msg)
                    log.error(msg)
    except KeyboardInterrupt:
        log.warning(
            "interrumpido: las fuentes HDF no validadas fueron preservadas"
        )
        return 130

    if errores:
        log.error("%d día(s) reintentables; primera falla: %s",
                  len(errores), errores[0])
        return 1
    log.info("Listo: píxeles/pasadas nativos, normalizados; sin HDF temporales.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
