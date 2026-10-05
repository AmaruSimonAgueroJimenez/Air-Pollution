#!/usr/bin/env python3
"""Normaliza ERA5-Land a su grilla nativa horaria recortada a Chile.

Contrato de salida
------------------
* conserva cada hora UTC y cada celda nativa de 0,1 grados;
* no interpola, remuestrea ni promedia por comuna;
* conserva toda celda cuya huella intersecta el Chile administrativo,
  incluidas Juan Fernandez, Desventuradas, Rapa Nui, Sala y Gomez y la zona
  sin demarcar ``cod_comuna=0``; Antartica no forma parte de la mascara;
* publica un catalogo de pixeles estable, una relacion muchos-a-muchos entre
  pixeles y comunas y un NetCDF compacto por mes (dimensiones hora x pixel);
* registra hashes SHA-256 de mascara, catalogos, fuentes y resultado;
* escribe primero ``*.part`` y solo publica despues de validar de nuevo;
* nunca elimina fuentes salvo que se use el argumento explicito
  ``--eliminar-fuentes-validadas``. El descargador integrado solo aplica esa
  limpieza a sus archivos transitorios de ``staging``.

El ``pixel_id`` se deriva de la grilla global ERA5-Land: indice latitudinal
norte-sur por 3600 mas indice longitudinal 0..359,9 grados. Por tanto no
depende del recorte ni del orden de los archivos fuente.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
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


RESOLUCION = 0.1
N_LAT_GLOBAL = 1801
N_LON_GLOBAL = 3600
PRODUCTO = "ERA5-Land"
PREFIJO_ARCHIVO = "era5land"
SCRIPT_PRODUCTO = Path(__file__)
VOLUMEN_DATOS = Path("/Volumes/Datos")
DATA_ROOT = Path(
    os.environ.get(
        "AIR_POLLUTION_DATA_ROOT",
        Path(os.environ.get("ASESORIAS_DATA_ROOT", "/Volumes/Datos/Asesorias_Data"))
        / "AirPollution" / "data",
    )
).expanduser().resolve()
RAIZ_SALIDA = DATA_ROOT / "contaminantes" / "ERA5Land" / "chile_nativo_01deg"
COMUNAS = DATA_ROOT / "comunas.shp"

ALIAS_VARIABLES: dict[str, tuple[str, ...]] = {
    "t2m": ("t2m", "2t", "T2M", "2m_temperature"),
    "d2m": ("d2m", "2d", "D2M", "2m_dewpoint_temperature"),
    "u10": ("u10", "10u", "U10M", "10m_u_component_of_wind"),
    "v10": ("v10", "10v", "V10M", "10m_v_component_of_wind"),
    "sp": ("sp", "PS", "surface_pressure"),
    "tp": ("tp", "total_precipitation"),
    "rh2m": ("rh2m", "RH2M", "2m_relative_humidity"),
}
ALIAS_A_CANONICO = {
    alias.lower(): canonico
    for canonico, aliases in ALIAS_VARIABLES.items()
    for alias in aliases
}


def asegurar_disco_externo(ruta: Path) -> None:
    """Impide escribir o borrar si el volumen externo no esta montado."""
    if not VOLUMEN_DATOS.is_mount():
        raise RuntimeError("/Volumes/Datos no esta montado")
    volumen = VOLUMEN_DATOS.resolve()
    real = Path(ruta).expanduser().resolve(strict=False)
    if real != volumen and volumen not in real.parents:
        raise RuntimeError(f"ruta fuera del disco externo obligatorio: {real}")


def sha256_archivo(path: Path, bloque: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for pedazo in iter(lambda: fh.read(bloque), b""):
            h.update(pedazo)
    return h.hexdigest()


def _fsync_archivo(path: Path) -> None:
    with path.open("rb") as fh:
        os.fsync(fh.fileno())


def _escribir_json_atomico(path: Path, objeto: dict) -> None:
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


def _hashes_shapefile(path: Path) -> dict[str, dict[str, object]]:
    base = Path(path).with_suffix("")
    partes: dict[str, dict[str, object]] = {}
    for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
        p = base.with_suffix(ext)
        if p.exists():
            partes[p.name] = {
                "bytes": p.stat().st_size,
                "sha256": sha256_archivo(p),
            }
    faltantes = {".shp", ".shx", ".dbf", ".prj"} - {
        Path(nombre).suffix.lower() for nombre in partes
    }
    if faltantes:
        raise FileNotFoundError(
            f"shapefile incompleto {path}: faltan {sorted(faltantes)}"
        )
    return partes


def _ahora_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _versiones_software() -> dict[str, str]:
    """Versiona el ejecutable y las librerias que determinan la salida."""
    versiones = {"python": platform.python_version()}
    for modulo in (
        "numpy", "pandas", "xarray", "netCDF4", "geopandas", "shapely",
        "pyarrow",
    ):
        try:
            paquete = __import__(modulo)
            versiones[modulo] = str(getattr(paquete, "__version__", "desconocida"))
        except ImportError:
            versiones[modulo] = "no_instalado"
    versiones["motor_normalizacion_sha256"] = sha256_archivo(Path(__file__))
    versiones["script_producto_sha256"] = sha256_archivo(SCRIPT_PRODUCTO)
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
                pid = int(path.read_text().strip())
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
            if path.read_text().strip() == str(os.getpid()):
                path.unlink(missing_ok=True)
        except OSError:
            pass


def _cargar_derivador_aoi():
    """Importa el derivador comunal sin depender del directorio de ejecucion."""
    import sys

    raiz_repo = Path(__file__).resolve().parents[2]
    if str(raiz_repo) not in sys.path:
        sys.path.insert(0, str(raiz_repo))
    from scripts_pipeline._chile_aoi import derivar

    return derivar


def _indices_candidatos(bbox: tuple[float, float, float, float]):
    """Centros globales cuyas huellas nativas cruzan un bbox."""
    oeste, sur, este, norte = bbox
    mitad = RESOLUCION / 2
    i0 = max(0, int(np.ceil((90.0 - (norte + mitad)) / RESOLUCION - 1e-9)))
    i1 = min(
        N_LAT_GLOBAL - 1,
        int(np.floor((90.0 - (sur - mitad)) / RESOLUCION + 1e-9)),
    )
    k0 = int(np.ceil((oeste - mitad) / RESOLUCION - 1e-9))
    k1 = int(np.floor((este + mitad) / RESOLUCION + 1e-9))
    for i in range(i0, i1 + 1):
        lat = round(90.0 - i * RESOLUCION, 10)
        for k in range(k0, k1 + 1):
            lon = round(k * RESOLUCION, 10)
            j = k % N_LON_GLOBAL
            yield i, j, lat, lon


def _escribir_parquet_atomico(df: pd.DataFrame, path: Path) -> None:
    asegurar_disco_externo(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.unlink(missing_ok=True)
    try:
        df.to_parquet(tmp, index=False, compression="zstd")
        # Verificacion independiente antes de publicar.
        leido = pd.read_parquet(tmp)
        if list(leido.columns) != list(df.columns) or len(leido) != len(df):
            raise ValueError(f"verificacion parquet fallida: {path.name}")
        _fsync_archivo(tmp)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _catalogo_vigente(raiz: Path, comunas_path: Path) -> bool:
    catalogo = raiz / "catalogo_pixeles.parquet"
    relacion = raiz / "relacion_pixel_comuna.parquet"
    manifiesto = raiz / "metadata" / "catalogo_manifest.json"
    if not (catalogo.exists() and relacion.exists() and manifiesto.exists()):
        return False
    try:
        meta = json.loads(manifiesto.read_text(encoding="utf-8"))
        if meta["resolucion_grados"] != RESOLUCION:
            return False
        software = meta.get("software", {})
        if (software.get("motor_normalizacion_sha256") != sha256_archivo(Path(__file__))
                or software.get("script_producto_sha256")
                != sha256_archivo(SCRIPT_PRODUCTO)):
            return False
        if meta["mascara"]["componentes"] != _hashes_shapefile(comunas_path):
            return False
        if sha256_archivo(catalogo) != meta["catalogo"]["sha256"]:
            return False
        if sha256_archivo(relacion) != meta["relacion_pixel_comuna"]["sha256"]:
            return False
        validar_catalogos(catalogo, relacion)
        return True
    except Exception:
        return False


def crear_catalogos(
    raiz: Path = RAIZ_SALIDA,
    comunas_path: Path = COMUNAS,
) -> tuple[Path, Path, Path]:
    """Crea/reutiliza el catalogo nativo y la relacion pixel-comuna."""
    raiz, comunas_path = Path(raiz), Path(comunas_path)
    asegurar_disco_externo(raiz)
    catalogo_path = raiz / "catalogo_pixeles.parquet"
    relacion_path = raiz / "relacion_pixel_comuna.parquet"
    manifest_path = raiz / "metadata" / "catalogo_manifest.json"
    lock = raiz / ".locks" / "catalogo.lock"
    with bloqueo(lock):
        if _catalogo_vigente(raiz, comunas_path):
            return catalogo_path, relacion_path, manifest_path

        import geopandas as gpd
        import shapely
        from shapely.geometry import box
        from shapely.strtree import STRtree

        derivar = _cargar_derivador_aoi()
        aois = derivar(comunas_path, margen=RESOLUCION / 2)
        candidatos: dict[int, dict[str, object]] = {}
        for aoi in aois:
            for i, j, lat, lon in _indices_candidatos(aoi.bbox):
                pixel_id = i * N_LON_GLOBAL + j
                previo = candidatos.get(pixel_id)
                if previo is None:
                    candidatos[pixel_id] = {
                        "pixel_id": pixel_id,
                        "lat_index_global": i,
                        "lon_index_global": j,
                        "latitude": lat,
                        "longitude": lon,
                        "territorio": aoi.territorio,
                        "aoi_id": aoi.id,
                    }
                elif previo["aoi_id"] != aoi.id:
                    raise ValueError(
                        f"pixel {pixel_id} aparece en AOIs remotas distintas"
                    )

        base = pd.DataFrame(candidatos.values()).sort_values("pixel_id")
        celdas = np.asarray(
            [
                box(
                    lon - RESOLUCION / 2,
                    lat - RESOLUCION / 2,
                    lon + RESOLUCION / 2,
                    lat + RESOLUCION / 2,
                )
                for lat, lon in zip(base.latitude, base.longitude, strict=True)
            ],
            dtype=object,
        )

        comunas = gpd.read_file(comunas_path).to_crs("EPSG:4326")
        if "cod_comuna" not in comunas:
            raise ValueError(f"{comunas_path}: falta cod_comuna")
        comunas["cod_comuna"] = pd.to_numeric(
            comunas["cod_comuna"], errors="raise"
        ).astype("int32")
        if (comunas.cod_comuna < 0).any():
            raise ValueError("la mascara contiene cod_comuna negativo")
        comunas["geometry"] = comunas.geometry.make_valid()
        geometrias = np.asarray(comunas.geometry.values, dtype=object)
        arbol = STRtree(geometrias)
        pares = arbol.query(celdas, predicate="intersects")
        intersecciones = shapely.intersection(
            celdas[pares[0]], geometrias[pares[1]]
        )
        # Los contactos de borde con area cero no convierten una celda oceanica
        # en pixel chileno.
        positivo = shapely.area(intersecciones) > 1e-14
        celda_idx = pares[0, positivo]
        comuna_idx = pares[1, positivo]
        intersecciones = intersecciones[positivo]
        if not len(celda_idx):
            raise ValueError(f"la mascara no intersecta ninguna celda {PRODUCTO}")

        area_inter = (
            gpd.GeoSeries(intersecciones, crs="EPSG:4326")
            .to_crs("EPSG:6933")
            .area.to_numpy()
        )
        unicos_celda = np.unique(celda_idx)
        area_celda_todos = (
            gpd.GeoSeries(celdas[unicos_celda], crs="EPSG:4326")
            .to_crs("EPSG:6933")
            .area.to_numpy()
        )
        area_por_indice = dict(zip(unicos_celda, area_celda_todos, strict=True))

        codigos = comunas.cod_comuna.to_numpy()
        relacion = pd.DataFrame(
            {
                "_celda_idx": celda_idx.astype("int64"),
                "pixel_id": base.pixel_id.to_numpy()[celda_idx].astype("int64"),
                "cod_comuna": codigos[comuna_idx].astype("int32"),
                "area_interseccion_m2": area_inter.astype("float64"),
                "fraccion_celda": np.asarray(
                    [area / area_por_indice[idx]
                     for idx, area in zip(celda_idx, area_inter, strict=True)],
                    dtype="float64",
                ),
            }
        )

        # Marca si el centro cae dentro de cada comuna candidata. Si no cae en
        # ninguna (islas/costa menores que la celda), se asigna la de mayor area
        # intersectada sin perder las otras relaciones.
        centros = shapely.points(
            base.longitude.to_numpy()[unicos_celda],
            base.latitude.to_numpy()[unicos_celda],
        )
        pares_centro = arbol.query(centros, predicate="intersects")
        centro_set = {
            (int(unicos_celda[i]), int(codigos[j]))
            for i, j in zip(pares_centro[0], pares_centro[1], strict=True)
        }
        relacion["centro_en_comuna"] = [
            (int(idx), int(cod)) in centro_set
            for idx, cod in zip(
                relacion._celda_idx, relacion.cod_comuna, strict=True
            )
        ]
        relacion = relacion.sort_values(
            ["pixel_id", "centro_en_comuna", "area_interseccion_m2", "cod_comuna"],
            ascending=[True, False, False, True],
            kind="mergesort",
        )
        principal = relacion.drop_duplicates("pixel_id", keep="first").set_index(
            "pixel_id"
        )
        base = base.iloc[unicos_celda].copy()
        base["cod_comuna"] = (
            base.pixel_id.map(principal.cod_comuna).astype("int32")
        )
        base["asignacion_comuna"] = np.where(
            base.pixel_id.map(principal.centro_en_comuna).astype(bool),
            "centro",
            "mayor_interseccion",
        )
        base["cell_west"] = base.longitude - RESOLUCION / 2
        base["cell_east"] = base.longitude + RESOLUCION / 2
        base["cell_south"] = base.latitude - RESOLUCION / 2
        base["cell_north"] = base.latitude + RESOLUCION / 2
        base = base[
            [
                "pixel_id",
                "lat_index_global",
                "lon_index_global",
                "latitude",
                "longitude",
                "cell_west",
                "cell_south",
                "cell_east",
                "cell_north",
                "cod_comuna",
                "asignacion_comuna",
                "territorio",
                "aoi_id",
            ]
        ].reset_index(drop=True)
        relacion = relacion.drop(columns="_celda_idx").reset_index(drop=True)
        validar_catalogos_df(base, relacion)

        _escribir_parquet_atomico(base, catalogo_path)
        _escribir_parquet_atomico(relacion, relacion_path)
        meta = {
            "schema_version": 1,
            "producto": PRODUCTO,
            "creado_utc": _ahora_utc(),
            "software": _versiones_software(),
            "resolucion_grados": RESOLUCION,
            "grid_global": {
                "latitud": f"90 - lat_index_global * {RESOLUCION:g}",
                "longitud": (
                    f"(lon_index_global * {RESOLUCION:g}) modulo 360; "
                    "expresada -180..180"
                ),
                "pixel_id": (
                    f"lat_index_global * {N_LON_GLOBAL} + lon_index_global"
                ),
            },
            "criterio_recorte": (
                "huella de celda nativa con area de interseccion positiva con "
                "Chile administrativo; sin Antartica"
            ),
            "codigos": {
                "zona_sin_demarcar": 0,
                "fuera_mascara": None,
            },
            "mascara": {
                "archivo": comunas_path.name,
                "componentes": _hashes_shapefile(comunas_path),
            },
            "aois_derivadas": [
                {
                    "id": a.id,
                    "territorio": a.territorio,
                    "bbox_wsen": list(a.bbox),
                }
                for a in aois
            ],
            "catalogo": {
                "archivo": catalogo_path.name,
                "filas": len(base),
                "sha256": sha256_archivo(catalogo_path),
            },
            "relacion_pixel_comuna": {
                "archivo": relacion_path.name,
                "filas": len(relacion),
                "sha256": sha256_archivo(relacion_path),
            },
        }
        _escribir_json_atomico(manifest_path, meta)
        if not _catalogo_vigente(raiz, comunas_path):
            raise ValueError("los catalogos publicados no superaron la revalidacion")
    return catalogo_path, relacion_path, manifest_path


def validar_catalogos_df(catalogo: pd.DataFrame, relacion: pd.DataFrame) -> None:
    requeridas = {
        "pixel_id", "lat_index_global", "lon_index_global", "latitude",
        "longitude", "cod_comuna", "territorio", "aoi_id",
    }
    faltan = requeridas - set(catalogo)
    if faltan:
        raise ValueError(f"catalogo sin columnas {sorted(faltan)}")
    if catalogo.empty or catalogo.pixel_id.duplicated().any():
        raise ValueError("catalogo vacio o con pixel_id duplicado")
    if (pd.to_numeric(catalogo.cod_comuna, errors="raise") < 0).any():
        raise ValueError("cod_comuna negativo en catalogo")
    esperado = (
        catalogo.lat_index_global.astype("int64") * N_LON_GLOBAL
        + catalogo.lon_index_global.astype("int64")
    )
    if not np.array_equal(esperado, catalogo.pixel_id.astype("int64")):
        raise ValueError("pixel_id no coincide con la grilla global")
    if not np.allclose(
        catalogo.latitude,
        90.0 - catalogo.lat_index_global * RESOLUCION,
        atol=1e-8,
    ):
        raise ValueError("latitudes fuera de la grilla nativa")
    lon_esperada = catalogo.lon_index_global * RESOLUCION
    lon_esperada = np.where(lon_esperada > 180.0, lon_esperada - 360.0, lon_esperada)
    if not np.allclose(catalogo.longitude, lon_esperada, atol=1e-8):
        raise ValueError("longitudes fuera de la grilla nativa")
    if relacion.empty or relacion.duplicated(["pixel_id", "cod_comuna"]).any():
        raise ValueError("relacion pixel-comuna vacia o duplicada")
    if (pd.to_numeric(relacion.cod_comuna, errors="raise") < 0).any():
        raise ValueError("cod_comuna negativo en relacion")
    if set(catalogo.pixel_id) != set(relacion.pixel_id):
        raise ValueError("cada pixel debe tener al menos una relacion comunal")
    if not catalogo.cod_comuna.isin(relacion.cod_comuna).all():
        raise ValueError("catalogo contiene codigos ausentes de la relacion")
    pares = set(zip(relacion.pixel_id, relacion.cod_comuna, strict=True))
    if any(
        (int(p), int(c)) not in pares
        for p, c in zip(catalogo.pixel_id, catalogo.cod_comuna, strict=True)
    ):
        raise ValueError("asignacion principal no pertenece a la relacion del pixel")
    if not np.isfinite(relacion.area_interseccion_m2).all() or (
        relacion.area_interseccion_m2 <= 0
    ).any():
        raise ValueError("areas de interseccion invalidas")
    if not relacion.fraccion_celda.between(0, 1 + 1e-8).all():
        raise ValueError("fraccion de celda fuera de rango")


def validar_catalogos(catalogo: Path, relacion: Path) -> None:
    validar_catalogos_df(pd.read_parquet(catalogo), pd.read_parquet(relacion))


def _coord(ds, candidatos: Sequence[str], etiqueta: str) -> str:
    for nombre in candidatos:
        if nombre in ds.coords or nombre in ds.dims:
            return nombre
    raise ValueError(f"falta coordenada {etiqueta}")


def _canonicas(ds) -> dict[str, str]:
    encontradas: dict[str, str] = {}
    for nombre in ds.data_vars:
        canonico = ALIAS_A_CANONICO.get(nombre.lower())
        if canonico:
            if canonico in encontradas:
                raise ValueError(
                    f"variables duplicadas para {canonico}: "
                    f"{encontradas[canonico]} y {nombre}"
                )
            encontradas[canonico] = nombre
    return encontradas


def _normalizar_lon(lon: np.ndarray) -> np.ndarray:
    lon = (np.asarray(lon, dtype="float64") + 180.0) % 360.0 - 180.0
    # Conserva +180 si asi venia; no afecta Chile pero evita ambiguedad global.
    return np.where(np.isclose(lon, -180.0), -180.0, lon)


def _indice_lat_global(lat: np.ndarray) -> np.ndarray:
    crudo = (90.0 - np.asarray(lat, dtype="float64")) / RESOLUCION
    indice = np.rint(crudo).astype("int64")
    if not np.allclose(crudo, indice, atol=1e-6):
        raise ValueError(
            f"latitudes fuente no alineadas a {PRODUCTO} {RESOLUCION:g} grados"
        )
    return indice


def _indice_lon_global(lon: np.ndarray) -> np.ndarray:
    lon = _normalizar_lon(lon)
    crudo = np.mod(lon, 360.0) / RESOLUCION
    indice = np.rint(crudo).astype("int64") % N_LON_GLOBAL
    if not np.allclose(crudo, np.rint(crudo), atol=1e-6):
        raise ValueError(
            f"longitudes fuente no alineadas a {PRODUCTO} {RESOLUCION:g} grados"
        )
    return indice


def _tiempos_fuente(ds, nombre: str) -> pd.DatetimeIndex:
    tiempos = pd.DatetimeIndex(
        pd.to_datetime(np.asarray(ds[nombre].values).reshape(-1), errors="coerce", utc=True)
    )
    if tiempos.hasnans or tiempos.has_duplicates or not tiempos.is_monotonic_increasing:
        raise ValueError("tiempo fuente ausente, duplicado o desordenado")
    if len(tiempos) > 1 and not np.all(np.diff(tiempos.asi8) == 3_600_000_000_000):
        raise ValueError("la fuente no conserva resolucion horaria exacta")
    return tiempos


def _esperado_periodo(periodo: pd.Period, n: int | None = None) -> pd.DatetimeIndex:
    inicio = pd.Timestamp(periodo.start_time, tz="UTC")
    total = periodo.days_in_month * 24 if n is None else n
    return pd.date_range(inicio, periods=total, freq="h")


def _inventario_fuente(path: Path, periodo: pd.Period) -> dict[str, object]:
    import xarray as xr

    with xr.open_dataset(path) as ds:
        time = _coord(ds, ("valid_time", "time"), "tiempo")
        lat = _coord(ds, ("latitude", "lat"), "latitud")
        lon = _coord(ds, ("longitude", "lon"), "longitud")
        tiempos = _tiempos_fuente(ds, time)
        if not tiempos.equals(_esperado_periodo(periodo, len(tiempos))):
            raise ValueError(f"{path.name}: horas no comienzan al inicio de {periodo}")
        latitudes = np.asarray(ds[lat].values, dtype="float64").reshape(-1)
        longitudes = _normalizar_lon(ds[lon].values).reshape(-1)
        ilat, ilon = _indice_lat_global(latitudes), _indice_lon_global(longitudes)
        if len(np.unique(ilat)) != len(ilat) or len(np.unique(ilon)) != len(ilon):
            raise ValueError(f"{path.name}: coordenadas espaciales duplicadas")
        if len(ilat) > 1 and not np.all(np.abs(np.diff(ilat)) == 1):
            raise ValueError(
                f"{path.name}: latitudes no contiguas a {RESOLUCION:g} grados"
            )
        if len(ilon) > 1 and not np.all(np.abs(np.diff(ilon)) == 1):
            raise ValueError(
                f"{path.name}: longitudes no contiguas a {RESOLUCION:g} grados"
            )
        variables = _canonicas(ds)
        if not variables:
            raise ValueError(
                f"{path.name}: no contiene variables {PRODUCTO} reconocidas"
            )
        for canonico, original in variables.items():
            dims = set(ds[original].dims)
            if not {time, lat, lon}.issubset(dims):
                raise ValueError(
                    f"{path.name}:{original} no depende de tiempo/latitud/longitud"
                )
        return {
            "path": path,
            "time_name": time,
            "lat_name": lat,
            "lon_name": lon,
            "times": tiempos,
            "ilat": ilat,
            "ilon": ilon,
            "variables": variables,
        }


def _leer_bloque(da, time: str, lat: str, lon: str, inicio: int, fin: int):
    """Lee un bloque y colapsa solo dimensiones extra complementarias."""
    extras = [d for d in da.dims if d not in (time, lat, lon)]
    orden = [time, *extras, lat, lon]
    sub = da.isel({time: slice(inicio, fin)}).transpose(*orden)
    arr = np.asarray(sub.values)
    for _ in extras:
        # expver suele repartir datos complementarios entre slices. Se elige
        # el primer valor finito; no se promedia.
        primero = arr[:, 0, ...]
        for k in range(1, arr.shape[1]):
            candidato = arr[:, k, ...]
            primero = np.where(np.isfinite(primero), primero, candidato)
        arr = primero
    if arr.ndim != 3:
        raise ValueError(f"forma inesperada al leer {da.name}: {arr.shape}")
    return arr.astype("float32", copy=False)


def _crear_netcdf_base(tmp: Path, catalogo: pd.DataFrame, tiempos: pd.DatetimeIndex,
                       variables: Iterable[str], attrs_fuente: dict[str, object]):
    from netCDF4 import Dataset

    nc = Dataset(tmp, "w", format="NETCDF4")
    nc.createDimension("time", len(tiempos))
    nc.createDimension("pixel", len(catalogo))
    nc.setncatts(
        {
            "Conventions": "CF-1.10",
            "title": f"{PRODUCTO} horario en pixeles nativos de Chile administrativo",
            "spatial_resolution_degrees": RESOLUCION,
            "temporal_resolution": "hourly_UTC",
            "spatial_operation": "native-cell footprint intersection; no resampling",
            "temporal_operation": "none; exact native UTC hours",
            "communal_operation": "label/link only; no aggregation",
            "zone_without_demarcation_code": 0,
            "pixel_id_formula": (
                f"lat_index_global * {N_LON_GLOBAL} + lon_index_global"
            ),
            **attrs_fuente,
        }
    )
    t = nc.createVariable("time", "i8", ("time",))
    t.units = "seconds since 1970-01-01 00:00:00 UTC"
    t.calendar = "proleptic_gregorian"
    t.standard_name = "time"
    t[:] = (tiempos.asi8 // 1_000_000_000).astype("int64")
    p = nc.createVariable("pixel_id", "i8", ("pixel",))
    p.long_name = f"stable {PRODUCTO} global-grid cell identifier"
    p[:] = catalogo.pixel_id.to_numpy("int64")
    for nombre, columna, dtype, atributos in (
        ("latitude", "latitude", "f8", {"units": "degrees_north", "standard_name": "latitude"}),
        ("longitude", "longitude", "f8", {"units": "degrees_east", "standard_name": "longitude"}),
        ("lat_index_global", "lat_index_global", "i2", {}),
        ("lon_index_global", "lon_index_global", "i2", {}),
        ("cod_comuna", "cod_comuna", "i4", {"zone_without_demarcation_code": 0}),
    ):
        var = nc.createVariable(nombre, dtype, ("pixel",))
        var.setncatts(atributos)
        var[:] = catalogo[columna].to_numpy()
    for nombre in variables:
        var = nc.createVariable(
            nombre,
            "f4",
            ("time", "pixel"),
            fill_value=np.float32(np.nan),
            zlib=True,
            complevel=4,
            shuffle=True,
            chunksizes=(min(168, len(tiempos)), min(2048, len(catalogo))),
        )
        var.coordinates = "time latitude longitude"
        var.grid_mapping = "latitude_longitude"
    crs = nc.createVariable("latitude_longitude", "i1")
    crs.grid_mapping_name = "latitude_longitude"
    crs.longitude_of_prime_meridian = 0.0
    crs.semi_major_axis = 6378137.0
    crs.inverse_flattening = 298.257223563
    return nc


def _mapear_catalogo_fuente(catalogo: pd.DataFrame, inventario: dict[str, object]):
    mapa_lat = {int(v): i for i, v in enumerate(inventario["ilat"])}
    mapa_lon = {int(v): i for i, v in enumerate(inventario["ilon"])}
    out, ilat, ilon = [], [], []
    for pos, (i, j) in enumerate(
        zip(catalogo.lat_index_global, catalogo.lon_index_global, strict=True)
    ):
        if int(i) in mapa_lat and int(j) in mapa_lon:
            out.append(pos)
            ilat.append(mapa_lat[int(i)])
            ilon.append(mapa_lon[int(j)])
    return (
        np.asarray(out, dtype="int64"),
        np.asarray(ilat, dtype="int64"),
        np.asarray(ilon, dtype="int64"),
    )


def validar_salida_mensual(
    path: Path,
    periodo: pd.Period,
    catalogo_path: Path,
    variables_esperadas: Iterable[str] | None = None,
    permitir_parcial: bool = False,
) -> dict[str, object]:
    from netCDF4 import Dataset

    catalogo = pd.read_parquet(catalogo_path)
    with Dataset(path, "r") as nc:
        if len(nc.dimensions["pixel"]) != len(catalogo):
            raise ValueError(f"{path.name}: numero de pixeles incorrecto")
        ids = np.asarray(nc["pixel_id"][:], dtype="int64")
        if not np.array_equal(ids, catalogo.pixel_id.to_numpy("int64")):
            raise ValueError(f"{path.name}: pixel_id no coincide con catalogo")
        if not np.allclose(nc["latitude"][:], catalogo.latitude, atol=1e-8):
            raise ValueError(f"{path.name}: latitud no coincide con catalogo")
        if not np.allclose(nc["longitude"][:], catalogo.longitude, atol=1e-8):
            raise ValueError(f"{path.name}: longitud no coincide con catalogo")
        if not np.array_equal(nc["cod_comuna"][:], catalogo.cod_comuna):
            raise ValueError(f"{path.name}: cod_comuna no coincide con catalogo")
        segundos = np.asarray(nc["time"][:], dtype="int64")
        tiempos = pd.DatetimeIndex(pd.to_datetime(segundos, unit="s", utc=True))
        esperado = _esperado_periodo(periodo, len(tiempos))
        if not tiempos.equals(esperado):
            raise ValueError(f"{path.name}: horas UTC incompletas o desplazadas")
        if not permitir_parcial and len(tiempos) != periodo.days_in_month * 24:
            raise ValueError(f"{path.name}: mes horario incompleto")
        variables = [v for v in ALIAS_VARIABLES if v in nc.variables]
        if variables_esperadas is not None:
            faltan = set(variables_esperadas) - set(variables)
            if faltan:
                raise ValueError(f"{path.name}: faltan variables {sorted(faltan)}")
        if not variables:
            raise ValueError(f"{path.name}: no tiene variables cientificas")
        resumen = {}
        for nombre in variables:
            var = nc[nombre]
            if var.dimensions != ("time", "pixel"):
                raise ValueError(f"{path.name}:{nombre} no conserva hora x pixel")
            muestra = np.asarray(var[[0, len(tiempos) - 1], :])
            mascara_finita = np.isfinite(muestra)
            finitos = int(mascara_finita.sum())
            if finitos == 0:
                raise ValueError(f"{path.name}:{nombre} sin valores finitos")
            disponible = mascara_finita.any(axis=0)
            por_territorio = {}
            for territorio, indices in catalogo.groupby("territorio").groups.items():
                idx = np.asarray(list(indices), dtype="int64")
                por_territorio[str(territorio)] = {
                    "pixeles_catalogo": int(len(idx)),
                    "pixeles_con_valor_muestra_inicio_o_fin": int(disponible[idx].sum()),
                }
            resumen[nombre] = {
                "finitos_muestra_inicio_fin": finitos,
                "pixeles_con_valor_muestra_inicio_o_fin": int(disponible.sum()),
                "por_territorio": por_territorio,
            }
    return {
        "horas": len(tiempos),
        "pixeles": len(catalogo),
        "inicio_utc": tiempos[0].isoformat(),
        "fin_utc": tiempos[-1].isoformat(),
        "variables": resumen,
    }


def normalizar_mes(
    fuentes: Sequence[Path],
    periodo: pd.Period | str,
    raiz: Path = RAIZ_SALIDA,
    comunas_path: Path = COMUNAS,
    variables_esperadas: Iterable[str] | None = None,
    permitir_parcial: bool = False,
) -> tuple[Path, Path]:
    """Publica un mes compacto a partir de uno o varios bboxes/AOIs fuente."""
    import xarray as xr

    periodo = pd.Period(periodo, freq="M")
    fuentes = [Path(p).expanduser().resolve() for p in fuentes]
    if not fuentes or len(set(fuentes)) != len(fuentes):
        raise ValueError("se requiere una lista no vacia de fuentes unicas")
    for fuente in fuentes:
        asegurar_disco_externo(fuente)
        if not fuente.is_file():
            raise FileNotFoundError(fuente)
    raiz = Path(raiz).expanduser().resolve()
    asegurar_disco_externo(raiz)
    catalogo_path, relacion_path, catalogo_manifest = crear_catalogos(
        raiz, comunas_path
    )
    catalogo = pd.read_parquet(catalogo_path)
    inventarios = [_inventario_fuente(p, periodo) for p in fuentes]
    tiempos = inventarios[0]["times"]
    for inv in inventarios[1:]:
        if not inv["times"].equals(tiempos):
            raise ValueError("los AOIs fuente no contienen las mismas horas UTC")
    if not permitir_parcial and len(tiempos) != periodo.days_in_month * 24:
        raise ValueError(f"{periodo}: fuentes mensuales incompletas")
    variables = sorted(
        {v for inventario in inventarios for v in inventario["variables"]}
    )
    if variables_esperadas is not None:
        faltan = set(variables_esperadas) - set(variables)
        if faltan:
            raise ValueError(f"faltan variables fuente {sorted(faltan)}")
        variables = sorted(set(variables_esperadas))

    salida = (
        raiz / "mensual"
        / f"{PREFIJO_ARCHIVO}_{periodo.strftime('%Y%m')}_chile_pixeles.nc"
    )
    manifest = raiz / "manifiestos" / f"{PREFIJO_ARCHIVO}_{periodo.strftime('%Y%m')}.json"
    salida.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    lock = raiz / ".locks" / f"normalizar_{periodo.strftime('%Y%m')}.lock"
    with bloqueo(lock):
        info_fuentes = []
        for fuente in fuentes:
            info_fuentes.append(
                {
                    "archivo": fuente.name,
                    "ruta_al_normalizar": str(fuente),
                    "bytes": fuente.stat().st_size,
                    "sha256": sha256_archivo(fuente),
                }
            )
        if salida.exists() and manifest.exists():
            try:
                meta_previa = json.loads(manifest.read_text(encoding="utf-8"))
                fuentes_previas = {
                    (x["ruta_al_normalizar"], x["sha256"])
                    for x in meta_previa["fuentes"]
                }
                fuentes_actuales = {
                    (x["ruta_al_normalizar"], x["sha256"])
                    for x in info_fuentes
                }
                software_previo = meta_previa.get("software", {})
                codigo_vigente = (
                    software_previo.get("motor_normalizacion_sha256")
                    == sha256_archivo(Path(__file__))
                    and software_previo.get("script_producto_sha256")
                    == sha256_archivo(SCRIPT_PRODUCTO)
                )
                if (codigo_vigente
                        and "parametros_normalizacion" in meta_previa
                        and fuentes_previas == fuentes_actuales
                        and sha256_archivo(salida) == meta_previa["salida"]["sha256"]):
                    validar_salida_mensual(
                        salida, periodo, catalogo_path, variables, permitir_parcial
                    )
                    return salida, manifest
            except Exception:
                pass

        cat_hash = sha256_archivo(catalogo_path)
        rel_hash = sha256_archivo(relacion_path)
        tmp = salida.with_suffix(salida.suffix + ".part")
        tmp.unlink(missing_ok=True)
        coberturas = {v: np.zeros(len(catalogo), dtype=bool) for v in variables}
        nombres_fuente: dict[str, set[str]] = {v: set() for v in variables}
        try:
            nc = _crear_netcdf_base(
                tmp,
                catalogo,
                tiempos,
                variables,
                {
                    "catalog_sha256": cat_hash,
                    "pixel_commune_relation_sha256": rel_hash,
                    "source_sha256_json": json.dumps(
                        {x["archivo"]: x["sha256"] for x in info_fuentes},
                        sort_keys=True,
                    ),
                },
            )
            try:
                for fuente, inv in zip(fuentes, inventarios, strict=True):
                    out_idx, src_lat_idx, src_lon_idx = _mapear_catalogo_fuente(
                        catalogo, inv
                    )
                    if not len(out_idx):
                        continue
                    with xr.open_dataset(fuente) as ds:
                        for canonico, original in inv["variables"].items():
                            if canonico not in variables:
                                continue
                            nombres_fuente[canonico].add(original)
                            ya = coberturas[canonico][out_idx]
                            for ini in range(0, len(tiempos), 168):
                                fin = min(ini + 168, len(tiempos))
                                bloque = _leer_bloque(
                                    ds[original],
                                    inv["time_name"],
                                    inv["lat_name"],
                                    inv["lon_name"],
                                    ini,
                                    fin,
                                )
                                valores = bloque[:, src_lat_idx, src_lon_idx]
                                if ya.any():
                                    posiciones = np.flatnonzero(ya)
                                    previos = np.asarray(
                                        nc[canonico][ini:fin, out_idx[posiciones]]
                                    )
                                    nuevos = valores[:, posiciones]
                                    ambos = np.isfinite(previos) & np.isfinite(nuevos)
                                    if ambos.any() and not np.allclose(
                                        previos[ambos], nuevos[ambos],
                                        rtol=1e-5, atol=1e-7,
                                    ):
                                        raise ValueError(
                                            f"AOIs solapados discrepan para {canonico}"
                                        )
                                nc[canonico][ini:fin, out_idx] = valores
                            coberturas[canonico][out_idx] = True
                for canonico in variables:
                    faltantes = int((~coberturas[canonico]).sum())
                    if faltantes:
                        raise ValueError(
                            f"{canonico}: {faltantes}/{len(catalogo)} pixeles sin "
                            "cobertura espacial; faltan AOIs insulares o continentales"
                        )
                    nc[canonico].source_variable_names = json.dumps(
                        sorted(nombres_fuente[canonico])
                    )
                nc.sync()
            finally:
                nc.close()
            _fsync_archivo(tmp)
            validar_salida_mensual(
                tmp, periodo, catalogo_path, variables, permitir_parcial
            )
            os.replace(tmp, salida)
            validacion = validar_salida_mensual(
                salida, periodo, catalogo_path, variables, permitir_parcial
            )
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

        meta = {
            "schema_version": 1,
            "producto": PRODUCTO,
            "periodo": str(periodo),
            "publicado_utc": _ahora_utc(),
            "software": _versiones_software(),
            "parametros_normalizacion": {
                "resolucion_grados": RESOLUCION,
                "permitir_mes_parcial": bool(permitir_parcial),
                "variables_esperadas": variables,
                "criterio_pixel": (
                    "area de interseccion positiva entre huella nativa y mascara"
                ),
                "asignacion_comuna_principal": (
                    "centro; si el centro queda fuera, mayor area de interseccion"
                ),
            },
            "resolucion_espacial": f"{RESOLUCION:g} degree native grid",
            "resolucion_temporal": "hourly UTC native",
            "operaciones_prohibidas_y_no_aplicadas": [
                "promedio comunal", "remuestreo espacial", "interpolacion temporal",
            ],
            "fuentes": info_fuentes,
            "fuentes_eliminadas_despues_de_validar": False,
            "catalogo": {
                "archivo": str(catalogo_path),
                "sha256": cat_hash,
                "manifest": str(catalogo_manifest),
            },
            "relacion_pixel_comuna": {
                "archivo": str(relacion_path),
                "sha256": rel_hash,
            },
            "salida": {
                "archivo": str(salida),
                "bytes": salida.stat().st_size,
                "sha256": sha256_archivo(salida),
            },
            "validacion": validacion,
            "cobertura_espacial": {
                v: {
                    "pixeles": int(coberturas[v].sum()),
                    "pixeles_esperados": len(catalogo),
                }
                for v in variables
            },
        }
        _escribir_json_atomico(manifest, meta)
        # Ultima verificacion: el manifest debe describir exactamente lo publicado.
        comprobacion = json.loads(manifest.read_text(encoding="utf-8"))
        if sha256_archivo(salida) != comprobacion["salida"]["sha256"]:
            raise ValueError("hash de salida no coincide tras publicar")
    return salida, manifest


def eliminar_fuentes_validadas(
    fuentes: Sequence[Path],
    salida: Path,
    manifest: Path,
    periodo: pd.Period | str,
    catalogo_path: Path,
    permitir_parcial: bool = False,
) -> int:
    """Elimina archivos enumerados solo tras revalidar hashes y salida."""
    periodo = pd.Period(periodo, freq="M")
    validar_salida_mensual(salida, periodo, catalogo_path, permitir_parcial=permitir_parcial)
    meta = json.loads(Path(manifest).read_text(encoding="utf-8"))
    if sha256_archivo(salida) != meta["salida"]["sha256"]:
        raise ValueError("no se elimina: hash de salida invalido")
    por_ruta = {Path(x["ruta_al_normalizar"]).resolve(): x for x in meta["fuentes"]}
    fuentes = [Path(p).resolve() for p in fuentes]
    for fuente in fuentes:
        asegurar_disco_externo(fuente)
        if fuente not in por_ruta:
            raise ValueError(f"no se elimina una fuente ajena al manifest: {fuente}")
        if not fuente.is_file() or sha256_archivo(fuente) != por_ruta[fuente]["sha256"]:
            raise ValueError(f"fuente cambio despues de normalizar: {fuente}")
    liberados = sum(p.stat().st_size for p in fuentes)
    for fuente in fuentes:
        fuente.unlink()
    eliminadas = set(meta.get("rutas_fuentes_eliminadas", []))
    eliminadas.update(str(p) for p in fuentes)
    todas = {str(Path(x["ruta_al_normalizar"]).resolve()) for x in meta["fuentes"]}
    meta["rutas_fuentes_eliminadas"] = sorted(eliminadas)
    meta["rutas_fuentes_conservadas"] = sorted(todas - eliminadas)
    meta["fuentes_eliminadas_despues_de_validar"] = todas.issubset(eliminadas)
    meta["eliminacion_fuentes_utc"] = _ahora_utc()
    meta["bytes_liberados"] = int(meta.get("bytes_liberados", 0)) + liberados
    _escribir_json_atomico(manifest, meta)
    return liberados


def _expandir_fuentes(valores: Sequence[str]) -> list[Path]:
    import glob

    resultado: list[Path] = []
    for valor in valores:
        coincidencias = sorted(Path(x) for x in glob.glob(valor))
        if coincidencias:
            resultado.extend(coincidencias)
        else:
            resultado.append(Path(valor))
    return resultado


def main() -> None:
    ap = argparse.ArgumentParser(
        description="ERA5-Land 0,1 grados horario: recorte administrativo sin promedios"
    )
    ap.add_argument("--fuente", action="append", required=True,
                    help="NetCDF fuente; se puede repetir y admite glob")
    ap.add_argument("--periodo", required=True, help="mes YYYY-MM")
    ap.add_argument("--salida-raiz", type=Path, default=RAIZ_SALIDA)
    ap.add_argument("--comunas", type=Path, default=COMUNAS)
    ap.add_argument("--variables-esperadas", nargs="*", choices=sorted(ALIAS_VARIABLES))
    ap.add_argument("--permitir-mes-parcial", action="store_true")
    ap.add_argument(
        "--eliminar-fuentes-validadas",
        action="store_true",
        help="BORRADO EXPLICITO: elimina solo las fuentes incluidas y hasheadas",
    )
    a = ap.parse_args()
    try:
        periodo = pd.Period(a.periodo, freq="M")
    except ValueError as exc:
        ap.error(str(exc))
    fuentes = _expandir_fuentes(a.fuente)
    salida, manifest = normalizar_mes(
        fuentes,
        periodo,
        a.salida_raiz,
        a.comunas,
        a.variables_esperadas,
        a.permitir_mes_parcial,
    )
    print(f"VALIDADO {salida}")
    print(f"MANIFEST {manifest}")
    if a.eliminar_fuentes_validadas:
        liberados = eliminar_fuentes_validadas(
            fuentes,
            salida,
            manifest,
            periodo,
            Path(a.salida_raiz) / "catalogo_pixeles.parquet",
            a.permitir_mes_parcial,
        )
        print(f"FUENTES ELIMINADAS TRAS VALIDAR: {liberados / 1024**3:.2f} GiB")


if __name__ == "__main__":
    main()
