#!/usr/bin/env python3
"""Normaliza reanalisis a sus celdas nativas de Chile administrativo.

Este modulo es el contrato comun para MERRA-2, CAMS EAC4 y GEOS-CF:

* conserva la cadencia y la marca UTC nativas (incluido el minuto 30 de
  MERRA-2/GEOS-CF); no interpola ni agrega en el tiempo;
* conserva cada celda nativa cuya huella tiene interseccion de area positiva
  con Chile continental, Juan Fernandez, Desventuradas, Rapa Nui o Sala y
  Gomez; ``comunas.shp`` no contiene la Antartica;
* publica un catalogo estable y la relacion muchos-a-muchos pixel-comuna;
* escribe NetCDF mensual ``time x pixel`` mediante ``*.part``, reabre y valida,
  publica atomico y registra hashes de mascara, fuentes, codigo y salida;
* solo elimina fuentes con ``--eliminar-fuentes-validadas``, despues de
  verificar otra vez el NetCDF y todos los hashes. Un mes parcial nunca
  autoriza borrado de sus fuentes.

Los productos se mantienen en su resolucion real:

* MERRA-2: 0,5 x 0,625 grados, horario a HH:30;
* CAMS EAC4: 0,75 x 0,75 grados, cada 3 horas;
* GEOS-CF: 0,25 x 0,25 grados, horario a HH:30.

No se crean corredores oceanicos ni promedios comunales.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
from typing import Iterable, Sequence

import numpy as np
import pandas as pd


VOLUMEN_DATOS = Path("/Volumes/Datos")
DATA_ROOT = Path(
    os.environ.get(
        "AIR_POLLUTION_DATA_ROOT",
        Path(os.environ.get("ASESORIAS_DATA_ROOT", "/Volumes/Datos/Asesorias_Data"))
        / "AirPollution" / "data",
    )
).expanduser().resolve()
COMUNAS = DATA_ROOT / "comunas.shp"


@dataclass(frozen=True)
class Producto:
    clave: str
    nombre: str
    prefijo: str
    salida: Path
    resolucion_lat: float
    resolucion_lon: float
    nlat_global: int
    nlon_global: int
    origen_lat: float
    origen_lon: float
    minutos_paso: int
    minuto_origen: int
    inicio_nativo: str
    aliases: dict[str, tuple[str, ...]]
    requeridas: tuple[str, ...]


PRODUCTOS: dict[str, Producto] = {
    "merra2_meteo": Producto(
        clave="merra2_meteo",
        nombre="MERRA-2 meteorologia y aerosoles",
        prefijo="merra2_meteo",
        salida=DATA_ROOT / "contaminantes" / "MERRA2_meteo"
        / "chile_nativo_05x0625deg",
        resolucion_lat=0.5,
        resolucion_lon=0.625,
        nlat_global=361,
        nlon_global=576,
        origen_lat=-90.0,
        origen_lon=-180.0,
        minutos_paso=60,
        minuto_origen=30,
        inicio_nativo="1980-01-01",
        aliases={
            "t2m": ("T2M", "t2m"),
            "qv2m": ("QV2M", "qv2m"),
            "u10m": ("U10M", "u10m"),
            "v10m": ("V10M", "v10m"),
            "ps": ("PS", "ps"),
            "rh2m": ("RH2M", "rh2m"),
            "pblh": ("PBLH", "pblh"),
            "aod_m2": ("AOD_M2", "TOTEXTTAU", "aod_m2"),
            "pm25_m2": ("PM25_M2", "pm25_m2"),
        },
        requeridas=(
            "t2m", "qv2m", "u10m", "v10m", "ps", "rh2m", "pblh",
            "aod_m2", "pm25_m2",
        ),
    ),
    "merra2_aer": Producto(
        clave="merra2_aer",
        nombre="MERRA-2 M2T1NXAER",
        prefijo="merra2_aer",
        salida=DATA_ROOT / "contaminantes" / "M2T1NXAER.5.12.4"
        / "chile_nativo_05x0625deg",
        resolucion_lat=0.5,
        resolucion_lon=0.625,
        nlat_global=361,
        nlon_global=576,
        origen_lat=-90.0,
        origen_lon=-180.0,
        minutos_paso=60,
        minuto_origen=30,
        inicio_nativo="1980-01-01",
        aliases={
            "aod_m2": ("AOD_M2", "TOTEXTTAU", "aod_m2"),
            "pm25_m2": ("PM25_M2", "pm25_m2"),
        },
        requeridas=("aod_m2", "pm25_m2"),
    ),
    "cams_eac4": Producto(
        clave="cams_eac4",
        nombre="CAMS global reanalysis EAC4",
        prefijo="cams_eac4",
        salida=DATA_ROOT / "contaminantes" / "CAMS_EAC4"
        / "chile_nativo_075deg",
        resolucion_lat=0.75,
        resolucion_lon=0.75,
        nlat_global=241,
        nlon_global=480,
        origen_lat=-90.0,
        origen_lon=-180.0,
        minutos_paso=180,
        minuto_origen=0,
        inicio_nativo="2003-01-01",
        aliases={
            "co": ("co", "carbon_monoxide"),
            "no2": ("no2", "nitrogen_dioxide"),
            "o3": ("go3", "o3", "ozone"),
            "so2": ("so2", "sulphur_dioxide"),
            "pm25": ("pm2p5", "pm25", "particulate_matter_2.5um"),
            "pm10": ("pm10", "particulate_matter_10um"),
        },
        requeridas=("co", "no2", "o3", "so2", "pm25", "pm10"),
    ),
    "geos_cf": Producto(
        clave="geos_cf",
        nombre="NASA GEOS-CF surface composition",
        prefijo="geos_cf",
        salida=DATA_ROOT / "contaminantes" / "GEOS_CF"
        / "chile_nativo_025deg",
        resolucion_lat=0.25,
        resolucion_lon=0.25,
        nlat_global=721,
        nlon_global=1440,
        origen_lat=-90.0,
        origen_lon=-180.0,
        minutos_paso=60,
        minuto_origen=30,
        inicio_nativo="2018-01-01",
        aliases={
            "co": ("co", "CO"),
            "no2": ("no2", "NO2"),
            "o3": ("o3", "O3"),
            "so2": ("so2", "SO2"),
            "pm25": (
                "pm25_rh35_gcc", "PM25_RH35_GCC",  # GEOS-CF v1
                "pm25_rh35", "PM25_RH35", "pm25",  # GEOS-CF v2
            ),
        },
        requeridas=("co", "no2", "o3", "so2", "pm25"),
    ),
}

MASAS_PM25_MERRA2 = (
    "SO4SMASS", "OCSMASS", "BCSMASS", "DUSMASS25", "SSSMASS25",
)


def asegurar_disco_externo(ruta: Path) -> None:
    if not VOLUMEN_DATOS.is_mount():
        raise RuntimeError("/Volumes/Datos no esta montado")
    volumen = VOLUMEN_DATOS.resolve()
    real = Path(ruta).expanduser().resolve(strict=False)
    if real != volumen and volumen not in real.parents:
        raise RuntimeError(f"ruta fuera del disco externo obligatorio: {real}")


def exigir_espacio(ruta: Path, minimo_gib: float) -> None:
    asegurar_disco_externo(ruta)
    libre = shutil.disk_usage(ruta if ruta.exists() else VOLUMEN_DATOS).free
    if libre < minimo_gib * 1024**3:
        raise RuntimeError(
            f"espacio insuficiente: {libre / 1024**3:.1f} GiB libres; "
            f"se exigen {minimo_gib:g} GiB"
        )


def sha256_archivo(path: Path, bloque: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for pedazo in iter(lambda: fh.read(bloque), b""):
            h.update(pedazo)
    return h.hexdigest()


def _fsync(path: Path) -> None:
    with path.open("rb") as fh:
        os.fsync(fh.fileno())


def _json_atomico(path: Path, objeto: dict) -> None:
    asegurar_disco_externo(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.unlink(missing_ok=True)
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(objeto, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _parquet_atomico(df: pd.DataFrame, path: Path) -> None:
    asegurar_disco_externo(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.unlink(missing_ok=True)
    try:
        df.to_parquet(tmp, index=False, compression="zstd")
        chk = pd.read_parquet(tmp)
        if list(chk.columns) != list(df.columns) or len(chk) != len(df):
            raise ValueError(f"Parquet no reabrio correctamente: {path.name}")
        _fsync(tmp)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _hashes_mascara(path: Path) -> dict[str, dict[str, object]]:
    partes: dict[str, dict[str, object]] = {}
    for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
        parte = path.with_suffix(ext)
        if parte.exists():
            partes[parte.name] = {
                "bytes": parte.stat().st_size,
                "sha256": sha256_archivo(parte),
            }
    requeridas = {".shp", ".shx", ".dbf", ".prj"}
    presentes = {Path(nombre).suffix.lower() for nombre in partes}
    if requeridas - presentes:
        raise FileNotFoundError(
            f"shapefile incompleto: faltan {sorted(requeridas - presentes)}"
        )
    return partes


def _software() -> dict[str, object]:
    versiones: dict[str, object] = {
        "python": platform.python_version(),
        "normalizador_sha256": sha256_archivo(Path(__file__)),
    }
    for modulo in ("numpy", "pandas", "xarray", "netCDF4", "geopandas", "shapely", "pyarrow"):
        try:
            paquete = __import__(modulo)
            versiones[modulo] = getattr(paquete, "__version__", "desconocida")
        except ImportError:
            versiones[modulo] = None
    return versiones


def _pid_activo(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, ValueError):
        return False
    except PermissionError:
        return True
    return pid > 0


@contextmanager
def bloqueo(path: Path):
    asegurar_disco_externo(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as fh:
                fh.write(str(os.getpid()))
            break
        except FileExistsError:
            try:
                pid = int(path.read_text(encoding="ascii").strip())
            except (OSError, ValueError):
                pid = -1
            if _pid_activo(pid):
                raise RuntimeError(f"proceso concurrente activo (PID {pid}): {path}")
            path.unlink(missing_ok=True)
    else:
        raise RuntimeError(f"no se pudo adquirir {path}")
    try:
        yield
    finally:
        try:
            if path.read_text(encoding="ascii").strip() == str(os.getpid()):
                path.unlink(missing_ok=True)
        except OSError:
            pass


def _cargar_aois(comunas: Path, margen: float):
    import sys

    raiz = Path(__file__).resolve().parent.parent
    if str(raiz) not in sys.path:
        sys.path.insert(0, str(raiz))
    from scripts_pipeline._chile_aoi import derivar

    return derivar(comunas, margen=margen)


def _candidatos(spec: Producto, bbox: tuple[float, float, float, float]):
    oeste, sur, este, norte = bbox
    dy, dx = spec.resolucion_lat, spec.resolucion_lon
    i0 = max(0, int(np.ceil((sur - dy / 2 - spec.origen_lat) / dy - 1e-9)))
    i1 = min(
        spec.nlat_global - 1,
        int(np.floor((norte + dy / 2 - spec.origen_lat) / dy + 1e-9)),
    )
    j0 = max(0, int(np.ceil((oeste - dx / 2 - spec.origen_lon) / dx - 1e-9)))
    j1 = min(
        spec.nlon_global - 1,
        int(np.floor((este + dx / 2 - spec.origen_lon) / dx + 1e-9)),
    )
    for i in range(i0, i1 + 1):
        lat = spec.origen_lat + i * dy
        for j in range(j0, j1 + 1):
            lon = spec.origen_lon + j * dx
            yield i, j, float(lat), float(lon)


def _catalogo_vigente(spec: Producto, comunas: Path) -> bool:
    raiz = spec.salida
    cat = raiz / "catalogo_pixeles.parquet"
    rel = raiz / "relacion_pixel_comuna.parquet"
    meta_path = raiz / "metadata" / "catalogo_manifest.json"
    if not (cat.exists() and rel.exists() and meta_path.exists()):
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta["producto_clave"] != spec.clave:
            return False
        if meta["software"]["normalizador_sha256"] != sha256_archivo(Path(__file__)):
            return False
        if meta["mascara"]["componentes"] != _hashes_mascara(comunas):
            return False
        if sha256_archivo(cat) != meta["catalogo"]["sha256"]:
            return False
        if sha256_archivo(rel) != meta["relacion_pixel_comuna"]["sha256"]:
            return False
        validar_catalogos(spec, pd.read_parquet(cat), pd.read_parquet(rel))
        return True
    except Exception:
        return False


def crear_catalogos(
    spec: Producto,
    comunas: Path = COMUNAS,
) -> tuple[Path, Path, Path]:
    """Publica catalogo nativo y todas las intersecciones pixel-comuna."""
    import geopandas as gpd
    import shapely
    from shapely.strtree import STRtree

    comunas = Path(comunas).expanduser().resolve()
    asegurar_disco_externo(spec.salida)
    cat_path = spec.salida / "catalogo_pixeles.parquet"
    rel_path = spec.salida / "relacion_pixel_comuna.parquet"
    meta_path = spec.salida / "metadata" / "catalogo_manifest.json"
    with bloqueo(spec.salida / ".locks" / "catalogo.lock"):
        if _catalogo_vigente(spec, comunas):
            return cat_path, rel_path, meta_path

        aois = _cargar_aois(
            comunas, margen=max(spec.resolucion_lat, spec.resolucion_lon) / 2
        )
        filas: dict[int, dict[str, object]] = {}
        for aoi in aois:
            for i, j, lat, lon in _candidatos(spec, aoi.bbox):
                pid = i * spec.nlon_global + j
                previo = filas.get(pid)
                if previo and previo["aoi_id"] != aoi.id:
                    raise ValueError(f"pixel {pid} aparece en AOIs remotas distintas")
                filas[pid] = {
                    "pixel_id": pid,
                    "lat_index_global": i,
                    "lon_index_global": j,
                    "latitude": lat,
                    "longitude": lon,
                    "territorio": aoi.territorio,
                    "aoi_id": aoi.id,
                }
        base = pd.DataFrame(filas.values()).sort_values("pixel_id").reset_index(drop=True)
        dx, dy = spec.resolucion_lon, spec.resolucion_lat
        celdas = np.asarray(
            [
                shapely.box(lon - dx / 2, lat - dy / 2, lon + dx / 2, lat + dy / 2)
                for lat, lon in zip(base.latitude, base.longitude, strict=True)
            ],
            dtype=object,
        )

        g = gpd.read_file(comunas).to_crs("EPSG:4326")
        if "cod_comuna" not in g:
            raise ValueError(f"{comunas}: falta cod_comuna")
        g["cod_comuna"] = pd.to_numeric(g.cod_comuna, errors="raise").astype("int32")
        if (g.cod_comuna < 0).any():
            raise ValueError("la mascara contiene cod_comuna negativo")
        g["geometry"] = g.geometry.make_valid()
        geoms = np.asarray(g.geometry.values, dtype=object)
        arbol = STRtree(geoms)
        pares = arbol.query(celdas, predicate="intersects")
        inter = shapely.intersection(celdas[pares[0]], geoms[pares[1]])
        positivo = shapely.area(inter) > 1e-14
        ci, gi, inter = pares[0, positivo], pares[1, positivo], inter[positivo]
        if not len(ci):
            raise ValueError("ninguna celda nativa intersecta Chile")
        areas_inter = gpd.GeoSeries(inter, crs=4326).to_crs(6933).area.to_numpy()
        unicos = np.unique(ci)
        areas_celda = gpd.GeoSeries(celdas[unicos], crs=4326).to_crs(6933).area.to_numpy()
        area_por_idx = dict(zip(unicos, areas_celda, strict=True))
        codigos = g.cod_comuna.to_numpy()
        relacion = pd.DataFrame(
            {
                "_celda": ci.astype("int64"),
                "pixel_id": base.pixel_id.to_numpy()[ci].astype("int64"),
                "cod_comuna": codigos[gi].astype("int32"),
                "area_interseccion_m2": areas_inter.astype("float64"),
                "fraccion_celda": np.asarray(
                    [a / area_por_idx[int(k)] for k, a in zip(ci, areas_inter, strict=True)]
                ),
            }
        )
        centros = shapely.points(
            base.longitude.to_numpy()[unicos], base.latitude.to_numpy()[unicos]
        )
        pc = arbol.query(centros, predicate="intersects")
        centros_dentro = {
            (int(unicos[a]), int(codigos[b]))
            for a, b in zip(pc[0], pc[1], strict=True)
        }
        relacion["centro_en_comuna"] = [
            (int(idx), int(cod)) in centros_dentro
            for idx, cod in zip(relacion._celda, relacion.cod_comuna, strict=True)
        ]
        relacion = relacion.sort_values(
            ["pixel_id", "centro_en_comuna", "area_interseccion_m2", "cod_comuna"],
            ascending=[True, False, False, True],
            kind="mergesort",
        )
        principal = relacion.drop_duplicates("pixel_id").set_index("pixel_id")
        base = base.iloc[unicos].copy()
        base["cod_comuna"] = base.pixel_id.map(principal.cod_comuna).astype("int32")
        base["asignacion_comuna"] = np.where(
            base.pixel_id.map(principal.centro_en_comuna).astype(bool),
            "centro",
            "mayor_interseccion",
        )
        base["cell_west"] = base.longitude - dx / 2
        base["cell_east"] = base.longitude + dx / 2
        base["cell_south"] = base.latitude - dy / 2
        base["cell_north"] = base.latitude + dy / 2
        base = base[
            [
                "pixel_id", "lat_index_global", "lon_index_global", "latitude",
                "longitude", "cell_west", "cell_south", "cell_east", "cell_north",
                "cod_comuna", "asignacion_comuna", "territorio", "aoi_id",
            ]
        ].reset_index(drop=True)
        relacion = relacion.drop(columns="_celda").reset_index(drop=True)
        validar_catalogos(spec, base, relacion)
        _parquet_atomico(base, cat_path)
        _parquet_atomico(relacion, rel_path)
        meta = {
            "schema_version": 1,
            "producto": spec.nombre,
            "producto_clave": spec.clave,
            "creado_utc": _ahora(),
            "software": _software(),
            "grilla_global": {
                "nlat": spec.nlat_global,
                "nlon": spec.nlon_global,
                "origen_lat": spec.origen_lat,
                "origen_lon": spec.origen_lon,
                "resolucion_lat": spec.resolucion_lat,
                "resolucion_lon": spec.resolucion_lon,
                "pixel_id": "lat_index_global * nlon_global + lon_index_global",
            },
            "criterio_recorte": (
                "area de interseccion positiva entre huella nativa y Chile "
                "administrativo; sin Antartica; sin corredor oceanico"
            ),
            "mascara": {"archivo": str(comunas), "componentes": _hashes_mascara(comunas)},
            "aois_derivadas": [
                {"id": a.id, "territorio": a.territorio, "bbox_wsen": list(a.bbox)}
                for a in aois
            ],
            "catalogo": {
                "archivo": str(cat_path), "filas": len(base),
                "sha256": sha256_archivo(cat_path),
            },
            "relacion_pixel_comuna": {
                "archivo": str(rel_path), "filas": len(relacion),
                "sha256": sha256_archivo(rel_path),
            },
        }
        _json_atomico(meta_path, meta)
        if not _catalogo_vigente(spec, comunas):
            raise ValueError("catalogos publicados no superaron la revalidacion")
    return cat_path, rel_path, meta_path


def validar_catalogos(spec: Producto, cat: pd.DataFrame, rel: pd.DataFrame) -> None:
    requeridas = {
        "pixel_id", "lat_index_global", "lon_index_global", "latitude",
        "longitude", "cod_comuna", "territorio", "aoi_id",
    }
    if requeridas - set(cat):
        raise ValueError(f"catalogo sin columnas {sorted(requeridas - set(cat))}")
    if cat.empty or cat.pixel_id.duplicated().any():
        raise ValueError("catalogo vacio o con pixel_id duplicado")
    esperado = cat.lat_index_global.astype("int64") * spec.nlon_global + cat.lon_index_global
    if not np.array_equal(esperado, cat.pixel_id):
        raise ValueError("pixel_id no coincide con la grilla global")
    lat = spec.origen_lat + cat.lat_index_global * spec.resolucion_lat
    lon = spec.origen_lon + cat.lon_index_global * spec.resolucion_lon
    if not np.allclose(lat, cat.latitude, atol=1e-8) or not np.allclose(
        lon, cat.longitude, atol=1e-8
    ):
        raise ValueError("coordenadas fuera de la grilla nativa")
    if (cat.cod_comuna < 0).any() or (rel.cod_comuna < 0).any():
        raise ValueError("cod_comuna negativo")
    if rel.empty or rel.duplicated(["pixel_id", "cod_comuna"]).any():
        raise ValueError("relacion pixel-comuna vacia o duplicada")
    if set(cat.pixel_id) != set(rel.pixel_id):
        raise ValueError("cada pixel debe tener al menos una relacion comunal")
    pares = set(zip(rel.pixel_id, rel.cod_comuna, strict=True))
    if any((int(p), int(c)) not in pares for p, c in zip(cat.pixel_id, cat.cod_comuna, strict=True)):
        raise ValueError("la comuna principal no pertenece a la relacion")
    if not np.isfinite(rel.area_interseccion_m2).all() or (rel.area_interseccion_m2 <= 0).any():
        raise ValueError("areas de interseccion invalidas")
    if not rel.fraccion_celda.between(0, 1 + 1e-8).all():
        raise ValueError("fracciones de celda invalidas")


def _coord(ds, candidatos: Sequence[str], etiqueta: str) -> str:
    for nombre in candidatos:
        if nombre in ds.coords or nombre in ds.dims:
            return nombre
    raise ValueError(f"falta coordenada {etiqueta}")


def _lon180(valores) -> np.ndarray:
    return (np.asarray(valores, dtype="float64") + 180.0) % 360.0 - 180.0


def _indices_grilla(spec: Producto, lat, lon) -> tuple[np.ndarray, np.ndarray]:
    lat = np.asarray(lat, dtype="float64").reshape(-1)
    lon = _lon180(lon).reshape(-1)
    ri = (lat - spec.origen_lat) / spec.resolucion_lat
    rj = (lon - spec.origen_lon) / spec.resolucion_lon
    i, j = np.rint(ri).astype("int64"), np.rint(rj).astype("int64")
    if not np.allclose(ri, i, atol=1e-6) or not np.allclose(rj, j, atol=1e-6):
        raise ValueError(f"coordenadas no alineadas a la grilla {spec.nombre}")
    if (i < 0).any() or (i >= spec.nlat_global).any() or (j < 0).any() or (j >= spec.nlon_global).any():
        raise ValueError("coordenadas fuera de indices globales")
    if len(np.unique(i)) != len(i) or len(np.unique(j)) != len(j):
        raise ValueError("coordenadas espaciales duplicadas")
    return i, j


def _esperado(spec: Producto, periodo: pd.Period) -> pd.DatetimeIndex:
    inicio = pd.Timestamp(periodo.start_time, tz="UTC") + pd.Timedelta(minutes=spec.minuto_origen)
    pasos = periodo.days_in_month * 24 * 60 // spec.minutos_paso
    return pd.date_range(inicio, periods=pasos, freq=f"{spec.minutos_paso}min")


def _variables_fuente(spec: Producto, ds) -> tuple[dict[str, object], dict[str, dict]]:
    por_lower = {str(nombre).lower(): str(nombre) for nombre in ds.data_vars}
    resultado: dict[str, object] = {}
    attrs: dict[str, dict] = {}
    for canonico, aliases in spec.aliases.items():
        for alias in aliases:
            original = por_lower.get(alias.lower())
            if original:
                resultado[canonico] = original
                attrs[canonico] = dict(ds[original].attrs)
                break
    if spec.clave == "merra2_aer" and "pm25_m2" not in resultado:
        reales = {v: por_lower.get(v.lower()) for v in MASAS_PM25_MERRA2}
        if all(reales.values()):
            resultado["pm25_m2"] = {"derivada": "pm25_gmao", "variables": reales}
            attrs["pm25_m2"] = {
                "units": "ug m-3",
                "long_name": "Surface PM2.5 from MERRA-2 aerosol mass (GMAO formula)",
                "formula": "(1.375*SO4SMASS + 1.6*OCSMASS + BCSMASS + DUSMASS25 + SSSMASS25)*1e9",
            }
    return resultado, attrs


def _inventario(path: Path, spec: Producto, periodo: pd.Period) -> dict[str, object] | None:
    import xarray as xr

    with xr.open_dataset(path) as ds:
        time = _coord(ds, ("valid_time", "time"), "tiempo")
        lat = _coord(ds, ("latitude", "lat"), "latitud")
        lon = _coord(ds, ("longitude", "lon"), "longitud")
        todos = pd.DatetimeIndex(pd.to_datetime(np.asarray(ds[time]).reshape(-1), utc=True))
        if todos.hasnans or todos.has_duplicates or not todos.is_monotonic_increasing:
            raise ValueError(f"{path.name}: tiempos invalidos")
        esperado = _esperado(spec, periodo)
        mascara = todos.isin(esperado)
        src_t = np.flatnonzero(mascara).astype("int64")
        if not len(src_t):
            return None
        tiempos = todos[mascara]
        if not tiempos.isin(esperado).all():
            raise ValueError(f"{path.name}: tiempos fuera del periodo")
        if len(tiempos) > 1 and not np.all(
            np.diff(tiempos.asi8) == spec.minutos_paso * 60 * 1_000_000_000
        ):
            raise ValueError(f"{path.name}: no conserva la cadencia nativa")
        ilat, ilon = _indices_grilla(spec, ds[lat].values, ds[lon].values)
        variables, attrs = _variables_fuente(spec, ds)
        for canonico, original in variables.items():
            nombres = (
                list(original["variables"].values())
                if isinstance(original, dict) else [original]
            )
            for nombre in nombres:
                dims = set(ds[nombre].dims)
                if not {time, lat, lon}.issubset(dims):
                    raise ValueError(f"{path.name}:{nombre} no depende de time/lat/lon")
                extras = [d for d in ds[nombre].dims if d not in (time, lat, lon)]
                if any(ds.sizes[d] != 1 for d in extras):
                    raise ValueError(
                        f"{path.name}:{nombre} tiene dimensiones extra no unitarias {extras}"
                    )
        return {
            "path": path,
            "time_name": time,
            "lat_name": lat,
            "lon_name": lon,
            "src_time_idx": src_t,
            "times": tiempos,
            "ilat": ilat,
            "ilon": ilon,
            "variables": variables,
            "attrs": attrs,
        }


def _leer_directa(ds, nombre: str, inv: dict, src_slice: slice) -> np.ndarray:
    time, lat, lon = inv["time_name"], inv["lat_name"], inv["lon_name"]
    da = ds[nombre].isel({time: src_slice})
    extras = [d for d in da.dims if d not in (time, lat, lon)]
    da = da.transpose(time, *extras, lat, lon)
    arr = np.asarray(da.values)
    for _ in extras:
        arr = arr[:, 0, ...]
    if arr.ndim != 3:
        raise ValueError(f"{nombre}: forma inesperada {arr.shape}")
    return arr.astype("float32", copy=False)


def _leer_variable(ds, referencia: object, inv: dict, src_slice: slice) -> np.ndarray:
    if isinstance(referencia, str):
        return _leer_directa(ds, referencia, inv, src_slice)
    if not isinstance(referencia, dict) or referencia.get("derivada") != "pm25_gmao":
        raise ValueError(f"referencia de variable desconocida: {referencia}")
    n = referencia["variables"]
    so4 = _leer_directa(ds, n["SO4SMASS"], inv, src_slice)
    oc = _leer_directa(ds, n["OCSMASS"], inv, src_slice)
    bc = _leer_directa(ds, n["BCSMASS"], inv, src_slice)
    du = _leer_directa(ds, n["DUSMASS25"], inv, src_slice)
    ss = _leer_directa(ds, n["SSSMASS25"], inv, src_slice)
    return ((1.375 * so4 + 1.6 * oc + bc + du + ss) * 1e9).astype("float32")


def _mapear_pixeles(cat: pd.DataFrame, inv: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mi = {int(v): k for k, v in enumerate(inv["ilat"])}
    mj = {int(v): k for k, v in enumerate(inv["ilon"])}
    out, si, sj = [], [], []
    for k, (i, j) in enumerate(zip(cat.lat_index_global, cat.lon_index_global, strict=True)):
        if int(i) in mi and int(j) in mj:
            out.append(k)
            si.append(mi[int(i)])
            sj.append(mj[int(j)])
    return np.asarray(out, "int64"), np.asarray(si, "int64"), np.asarray(sj, "int64")


def _segmentos(src_idx: np.ndarray, out_idx: np.ndarray):
    inicio = 0
    for k in range(1, len(src_idx) + 1):
        corte = (
            k == len(src_idx)
            or src_idx[k] != src_idx[k - 1] + 1
            or out_idx[k] != out_idx[k - 1] + 1
        )
        if corte:
            yield slice(int(src_idx[inicio]), int(src_idx[k - 1]) + 1), slice(
                int(out_idx[inicio]), int(out_idx[k - 1]) + 1
            )
            inicio = k


def _crear_netcdf(
    path: Path,
    spec: Producto,
    cat: pd.DataFrame,
    tiempos: pd.DatetimeIndex,
    variables: Iterable[str],
    attrs: dict[str, dict],
    cat_hash: str,
    rel_hash: str,
):
    from netCDF4 import Dataset

    nc = Dataset(path, "w", format="NETCDF4")
    nc.createDimension("time", len(tiempos))
    nc.createDimension("pixel", len(cat))
    nc.setncatts(
        {
            "Conventions": "CF-1.10",
            "title": f"{spec.nombre} en celdas nativas de Chile administrativo",
            "spatial_resolution_lat_degrees": spec.resolucion_lat,
            "spatial_resolution_lon_degrees": spec.resolucion_lon,
            "temporal_resolution_minutes": spec.minutos_paso,
            "native_timestamp_minute": spec.minuto_origen,
            "spatial_operation": "native-cell footprint intersection; no resampling",
            "temporal_operation": "none; exact native UTC timestamps",
            "communal_operation": "label/link only; no aggregation",
            "catalog_sha256": cat_hash,
            "pixel_commune_relation_sha256": rel_hash,
            "zone_without_demarcation_code": 0,
        }
    )
    t = nc.createVariable("time", "i8", ("time",))
    t.units = "seconds since 1970-01-01 00:00:00 UTC"
    t.calendar = "proleptic_gregorian"
    t.standard_name = "time"
    t[:] = (tiempos.asi8 // 1_000_000_000).astype("int64")
    for nombre, columna, tipo, atr in (
        ("pixel_id", "pixel_id", "i8", {"long_name": "stable global-grid cell identifier"}),
        ("latitude", "latitude", "f8", {"units": "degrees_north", "standard_name": "latitude"}),
        ("longitude", "longitude", "f8", {"units": "degrees_east", "standard_name": "longitude"}),
        ("lat_index_global", "lat_index_global", "i2", {}),
        ("lon_index_global", "lon_index_global", "i2", {}),
        ("cod_comuna", "cod_comuna", "i4", {"zone_without_demarcation_code": 0}),
    ):
        v = nc.createVariable(nombre, tipo, ("pixel",))
        v.setncatts(atr)
        v[:] = cat[columna].to_numpy()
    for nombre in variables:
        v = nc.createVariable(
            nombre, "f4", ("time", "pixel"), fill_value=np.float32(np.nan),
            zlib=True, complevel=4, shuffle=True,
            chunksizes=(min(max(1, 1440 // spec.minutos_paso * 7), len(tiempos)), min(2048, len(cat))),
        )
        v.coordinates = "time latitude longitude"
        for k, valor in attrs.get(nombre, {}).items():
            if k == "_FillValue" or isinstance(valor, (dict, list, tuple)):
                continue
            try:
                v.setncattr(k, valor)
            except (TypeError, ValueError):
                v.setncattr(k, str(valor))
    crs = nc.createVariable("latitude_longitude", "i1")
    crs.grid_mapping_name = "latitude_longitude"
    crs.longitude_of_prime_meridian = 0.0
    crs.semi_major_axis = 6378137.0
    crs.inverse_flattening = 298.257223563
    return nc


def validar_salida(
    path: Path,
    spec: Producto,
    periodo: pd.Period,
    cat_path: Path,
    permitir_parcial: bool = False,
) -> dict[str, object]:
    from netCDF4 import Dataset

    cat = pd.read_parquet(cat_path)
    esperado = _esperado(spec, periodo)
    with Dataset(path) as nc:
        if len(nc.dimensions["pixel"]) != len(cat):
            raise ValueError("numero de pixeles incorrecto")
        if not np.array_equal(nc["pixel_id"][:], cat.pixel_id):
            raise ValueError("pixel_id no coincide con catalogo")
        segundos = np.asarray(nc["time"][:], dtype="int64")
        tiempos = pd.DatetimeIndex(pd.to_datetime(segundos, unit="s", utc=True))
        if permitir_parcial:
            if not tiempos.equals(esperado[: len(tiempos)]):
                raise ValueError("serie parcial no es un prefijo continuo nativo")
        elif not tiempos.equals(esperado):
            raise ValueError("periodo temporal incompleto o desplazado")
        resumen: dict[str, object] = {}
        for nombre in spec.requeridas:
            if nombre not in nc.variables:
                raise ValueError(f"falta variable {nombre}")
            v = nc[nombre]
            if v.dimensions != ("time", "pixel"):
                raise ValueError(f"{nombre}: dimensiones no son time x pixel")
            muestra = np.ma.filled(v[[0, len(tiempos) - 1], :], np.nan)
            finita = np.isfinite(muestra)
            if not finita.any():
                raise ValueError(f"{nombre}: sin valores finitos")
            disponible = finita.any(axis=0)
            por_territorio = {}
            for territorio, indices in cat.groupby("territorio").groups.items():
                idx = np.asarray(list(indices), dtype="int64")
                por_territorio[str(territorio)] = {
                    "pixeles_catalogo": len(idx),
                    "pixeles_con_valor_muestra_inicio_o_fin": int(disponible[idx].sum()),
                }
            resumen[nombre] = {
                "finitos_muestra_inicio_fin": int(finita.sum()),
                "pixeles_con_valor_muestra_inicio_o_fin": int(disponible.sum()),
                "por_territorio": por_territorio,
            }
    return {
        "pasos_temporales": len(tiempos),
        "pixeles": len(cat),
        "inicio_utc": tiempos[0].isoformat(),
        "fin_utc": tiempos[-1].isoformat(),
        "variables": resumen,
    }


def rutas_periodo(spec: Producto, periodo: pd.Period) -> tuple[Path, Path]:
    salida = spec.salida / "mensual" / f"{spec.prefijo}_{periodo.strftime('%Y%m')}_chile_pixeles.nc"
    manifest = spec.salida / "manifiestos" / f"{spec.prefijo}_{periodo.strftime('%Y%m')}.json"
    return salida, manifest


def salida_vigente(
    spec: Producto,
    periodo: pd.Period,
    comunas: Path = COMUNAS,
    *,
    aceptar_parcial: bool = True,
) -> bool:
    salida, manifest = rutas_periodo(spec, periodo)
    cat_path = spec.salida / "catalogo_pixeles.parquet"
    if not (salida.exists() and manifest.exists() and cat_path.exists()):
        return False
    try:
        meta = json.loads(manifest.read_text(encoding="utf-8"))
        es_parcial = bool(meta["parametros_normalizacion"]["permitir_mes_parcial"])
        if es_parcial and not aceptar_parcial:
            return False
        if meta["software"]["normalizador_sha256"] != sha256_archivo(Path(__file__)):
            return False
        if sha256_archivo(salida) != meta["salida"]["sha256"]:
            return False
        if not _catalogo_vigente(spec, Path(comunas)):
            return False
        validar_salida(
            salida, spec, periodo, cat_path,
            es_parcial,
        )
        return True
    except Exception:
        return False


def normalizar_mes(
    spec: Producto,
    fuentes: Sequence[Path],
    periodo: pd.Period | str,
    comunas: Path = COMUNAS,
    permitir_parcial: bool = False,
    espacio_minimo_gib: float = 100,
) -> tuple[Path, Path]:
    """Publica un mes compacto desde fuentes temporales y/o AOIs."""
    import xarray as xr

    periodo = pd.Period(periodo, freq="M")
    fuentes = [Path(p).expanduser().resolve() for p in fuentes]
    if not fuentes or len(set(fuentes)) != len(fuentes):
        raise ValueError("se requiere una lista no vacia de fuentes unicas")
    for fuente in fuentes:
        asegurar_disco_externo(fuente)
        if not fuente.is_file():
            raise FileNotFoundError(fuente)
    exigir_espacio(spec.salida, espacio_minimo_gib)
    cat_path, rel_path, cat_manifest = crear_catalogos(spec, comunas)
    cat = pd.read_parquet(cat_path)
    inventarios = []
    for fuente in fuentes:
        inv = _inventario(fuente, spec, periodo)
        if inv is not None:
            inventarios.append(inv)
    if not inventarios:
        raise ValueError(f"ninguna fuente contiene tiempos de {periodo}")
    esperado = _esperado(spec, periodo)
    tiempos_union = pd.DatetimeIndex(
        sorted({t for inv in inventarios for t in inv["times"]})
    )
    if permitir_parcial:
        if not tiempos_union.equals(esperado[: len(tiempos_union)]):
            raise ValueError("las fuentes parciales no forman un prefijo temporal continuo")
        tiempos = tiempos_union
    else:
        if not tiempos_union.equals(esperado):
            faltan = len(esperado.difference(tiempos_union))
            raise ValueError(f"{periodo}: faltan {faltan} pasos temporales nativos")
        tiempos = esperado
    presentes = {v for inv in inventarios for v in inv["variables"]}
    faltan_vars = set(spec.requeridas) - presentes
    if faltan_vars:
        raise ValueError(f"faltan variables fuente {sorted(faltan_vars)}")
    attrs: dict[str, dict] = {}
    for inv in inventarios:
        for nombre, atr in inv["attrs"].items():
            attrs.setdefault(nombre, atr)

    salida, manifest = rutas_periodo(spec, periodo)
    salida.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with bloqueo(spec.salida / ".locks" / f"normalizar_{periodo.strftime('%Y%m')}.lock"):
        info_fuentes = [
            {
                "archivo": p.name,
                "ruta_al_normalizar": str(p),
                "bytes": p.stat().st_size,
                "sha256": sha256_archivo(p),
            }
            for p in fuentes
        ]
        cat_hash, rel_hash = sha256_archivo(cat_path), sha256_archivo(rel_path)
        tmp = salida.with_suffix(salida.suffix + ".part")
        tmp.unlink(missing_ok=True)
        cobertura = {
            v: np.zeros((len(tiempos), len(cat)), dtype=bool) for v in spec.requeridas
        }
        nombres_fuente: dict[str, set[str]] = {v: set() for v in spec.requeridas}
        mapa_t = {t: i for i, t in enumerate(tiempos)}
        try:
            nc = _crear_netcdf(
                tmp, spec, cat, tiempos, spec.requeridas, attrs, cat_hash, rel_hash
            )
            try:
                for inv in inventarios:
                    out_pix, src_i, src_j = _mapear_pixeles(cat, inv)
                    if not len(out_pix):
                        continue
                    out_t = np.asarray([mapa_t[t] for t in inv["times"]], dtype="int64")
                    src_t = np.asarray(inv["src_time_idx"], dtype="int64")
                    with xr.open_dataset(inv["path"]) as ds:
                        for canonico, referencia in inv["variables"].items():
                            if canonico not in cobertura:
                                continue
                            nombres = (
                                referencia["variables"].values()
                                if isinstance(referencia, dict) else [referencia]
                            )
                            nombres_fuente[canonico].update(str(x) for x in nombres)
                            for ss, oo in _segmentos(src_t, out_t):
                                bloque = _leer_variable(ds, referencia, inv, ss)
                                valores = bloque[:, src_i, src_j]
                                previo_mask = cobertura[canonico][oo, :][:, out_pix]
                                if previo_mask.any():
                                    previo = np.ma.filled(nc[canonico][oo, out_pix], np.nan)
                                    ambos = previo_mask & np.isfinite(previo) & np.isfinite(valores)
                                    if ambos.any() and not np.allclose(
                                        previo[ambos], valores[ambos], rtol=1e-5, atol=1e-7
                                    ):
                                        raise ValueError(
                                            f"fuentes solapadas discrepan para {canonico}"
                                        )
                                nc[canonico][oo, out_pix] = valores
                                cobertura[canonico][oo, out_pix] = True
                for nombre, mask in cobertura.items():
                    if not mask.all():
                        faltan = int((~mask).sum())
                        por_territorio = {}
                        for territorio, indices in cat.groupby("territorio").groups.items():
                            idx = np.asarray(list(indices), dtype="int64")
                            por_territorio[str(territorio)] = int((~mask[:, idx]).sum())
                        raise ValueError(
                            f"{nombre}: faltan {faltan}/{mask.size} celdas-tiempo; "
                            f"por territorio={por_territorio}"
                        )
                    nc[nombre].source_variable_names = json.dumps(
                        sorted(nombres_fuente[nombre])
                    )
                nc.sync()
            finally:
                nc.close()
            _fsync(tmp)
            validar_salida(tmp, spec, periodo, cat_path, permitir_parcial)
            os.replace(tmp, salida)
            validacion = validar_salida(
                salida, spec, periodo, cat_path, permitir_parcial
            )
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        meta = {
            "schema_version": 1,
            "producto": spec.nombre,
            "producto_clave": spec.clave,
            "periodo": str(periodo),
            "publicado_utc": _ahora(),
            "software": _software(),
            "parametros_normalizacion": {
                "resolucion_lat_grados": spec.resolucion_lat,
                "resolucion_lon_grados": spec.resolucion_lon,
                "paso_temporal_minutos": spec.minutos_paso,
                "minuto_marca_nativa": spec.minuto_origen,
                "permitir_mes_parcial": bool(permitir_parcial),
                "variables": list(spec.requeridas),
                "criterio_pixel": "area de interseccion positiva entre huella y mascara",
            },
            "operaciones_prohibidas_y_no_aplicadas": [
                "promedio comunal", "remuestreo espacial", "interpolacion temporal",
                "desplazamiento de la marca UTC nativa",
            ],
            "fuentes": info_fuentes,
            "fuentes_eliminadas_despues_de_validar": False,
            "catalogo": {
                "archivo": str(cat_path), "sha256": cat_hash,
                "manifest": str(cat_manifest),
            },
            "relacion_pixel_comuna": {"archivo": str(rel_path), "sha256": rel_hash},
            "salida": {
                "archivo": str(salida), "bytes": salida.stat().st_size,
                "sha256": sha256_archivo(salida),
            },
            "validacion": validacion,
            "cobertura_espacial_temporal": {
                v: {"celdas_tiempo": int(m.sum()), "esperadas": int(m.size)}
                for v, m in cobertura.items()
            },
        }
        _json_atomico(manifest, meta)
        comprobacion = json.loads(manifest.read_text(encoding="utf-8"))
        if sha256_archivo(salida) != comprobacion["salida"]["sha256"]:
            raise ValueError("hash de salida no coincide despues de publicar")
    return salida, manifest


def eliminar_fuentes_validadas(
    spec: Producto,
    fuentes: Sequence[Path],
    periodo: pd.Period | str,
    salida: Path,
    manifest: Path,
) -> int:
    """Retira exclusivamente fuentes hasheadas de un mes completo validado."""
    periodo = pd.Period(periodo, freq="M")
    meta = json.loads(Path(manifest).read_text(encoding="utf-8"))
    if meta["parametros_normalizacion"]["permitir_mes_parcial"]:
        raise ValueError("un mes parcial nunca autoriza borrar sus fuentes")
    cat_path = Path(meta["catalogo"]["archivo"])
    validar_salida(salida, spec, periodo, cat_path, permitir_parcial=False)
    if sha256_archivo(salida) != meta["salida"]["sha256"]:
        raise ValueError("hash de salida invalido; no se elimina")
    declaradas = {Path(x["ruta_al_normalizar"]).resolve(): x for x in meta["fuentes"]}
    fuentes = [Path(x).resolve() for x in fuentes]
    for fuente in fuentes:
        asegurar_disco_externo(fuente)
        if fuente not in declaradas:
            raise ValueError(f"fuente ajena al manifiesto: {fuente}")
        if not fuente.is_file() or sha256_archivo(fuente) != declaradas[fuente]["sha256"]:
            raise ValueError(f"fuente cambio desde la normalizacion: {fuente}")
    liberados = sum(x.stat().st_size for x in fuentes)
    for fuente in fuentes:
        fuente.unlink()
    eliminadas = set(meta.get("rutas_fuentes_eliminadas", []))
    eliminadas.update(str(x) for x in fuentes)
    todas = {str(x) for x in declaradas}
    meta["rutas_fuentes_eliminadas"] = sorted(eliminadas)
    meta["rutas_fuentes_conservadas"] = sorted(todas - eliminadas)
    meta["fuentes_eliminadas_despues_de_validar"] = todas.issubset(eliminadas)
    meta["bytes_liberados"] = int(meta.get("bytes_liberados", 0)) + liberados
    meta["eliminacion_fuentes_utc"] = _ahora()
    _json_atomico(Path(manifest), meta)
    return liberados


def descubrir_fuentes(spec: Producto, periodo: pd.Period) -> list[Path]:
    ym, y = periodo.strftime("%Y%m"), periodo.strftime("%Y")
    c = DATA_ROOT / "contaminantes"
    if spec.clave == "merra2_meteo":
        return sorted(
            (c / "MERRA2_meteo" / "raw_chile_horario").glob(
                f"M2_merra2_hourly_{ym}??_chile.nc"
            )
        )
    if spec.clave == "merra2_aer":
        correctas = (c / "M2T1NXAER.5.12.4" / "raw_chile").glob(
            f"MERRA2_*.{ym}??.chile.nc4"
        )
        legado = (c / "M2TMNXAER.5.12.4" / "raw_chile").glob(
            f"MERRA2_*.{ym}??.chile.nc4"
        )
        return sorted([*correctas, *legado])
    if spec.clave == "cams_eac4":
        return sorted((c / "CAMS_EAC4" / "raw_chile").glob(f"cams_eac4_*_{y}.nc"))
    if spec.clave == "geos_cf":
        return sorted((c / "GEOS_CF" / "raw_chile").glob(f"geoscf_{ym}.nc"))
    raise ValueError(spec.clave)


def _expandir(valores: Sequence[str]) -> list[Path]:
    import glob

    out: list[Path] = []
    for valor in valores:
        hallados = sorted(Path(x) for x in glob.glob(valor))
        out.extend(hallados or [Path(valor)])
    return out


def _periodos(desde: str, hasta: str) -> list[pd.Period]:
    a, b = pd.Period(desde[:7], "M"), pd.Period(hasta[:7], "M")
    if b < a:
        raise ValueError("--hasta es anterior a --desde")
    return list(pd.period_range(a, b, freq="M"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--producto", choices=sorted(PRODUCTOS), required=True)
    ap.add_argument("--periodo", help="un mes YYYY-MM")
    ap.add_argument("--desde", default="2000-01-01")
    ap.add_argument("--hasta", default=datetime.now().date().isoformat())
    ap.add_argument("--fuente", action="append", help="NetCDF fuente; repetible y admite glob")
    ap.add_argument("--comunas", type=Path, default=COMUNAS)
    ap.add_argument("--permitir-ultimo-mes-parcial", action="store_true")
    ap.add_argument("--eliminar-fuentes-validadas", action="store_true")
    ap.add_argument("--espacio-minimo-gb", type=float, default=100)
    a = ap.parse_args()
    spec = PRODUCTOS[a.producto]
    if a.fuente and not a.periodo:
        ap.error("--fuente requiere --periodo")
    periodos = [pd.Period(a.periodo, "M")] if a.periodo else _periodos(a.desde, a.hasta)
    for k, periodo in enumerate(periodos):
        if salida_vigente(spec, periodo, a.comunas):
            print(f"YA VALIDADO {spec.clave} {periodo}")
            continue
        fuentes = _expandir(a.fuente) if a.fuente else descubrir_fuentes(spec, periodo)
        if not fuentes:
            print(f"PENDIENTE {spec.clave} {periodo}: sin fuentes locales")
            continue
        parcial = bool(a.permitir_ultimo_mes_parcial and k == len(periodos) - 1)
        salida, manifest = normalizar_mes(
            spec, fuentes, periodo, a.comunas, parcial, a.espacio_minimo_gb
        )
        print(f"VALIDADO {salida}")
        print(f"MANIFEST {manifest}")
        if a.eliminar_fuentes_validadas:
            liberados = eliminar_fuentes_validadas(
                spec, fuentes, periodo, salida, manifest
            )
            print(f"FUENTES ELIMINADAS: {liberados / 1024**3:.3f} GiB")


if __name__ == "__main__":
    main()
