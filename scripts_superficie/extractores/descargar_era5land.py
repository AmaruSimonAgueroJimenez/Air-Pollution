#!/usr/bin/env python3
"""Descarga y publica ERA5-Land horario a resolucion nativa de 0,1 grados.

El flujo predeterminado cubre desde enero de 2000 hasta la fecha disponible
(fecha local menos ``--rezago-dias``), con cinco AOIs derivados y versionados
desde ``comunas.shp``: continente, Juan Fernandez, Desventuradas, Rapa Nui y
Sala y Gomez. Los AOIs se solicitan por separado, se unen sin interpolar y se
recortan por la huella real de cada celda. El resultado conserva todas las
horas UTC y todos los pixeles nativos; la comuna es una etiqueta y una tabla
muchos-a-muchos, nunca un promedio.

Por cada mes el programa realiza:

    CDS -> NetCDF transitorios por AOI -> validacion -> recorte verdadero ->
    NetCDF hora x pixel + catalogos + manifest/hashes -> revalidacion ->
    eliminacion de los NetCDF transitorios

Solo se publican archivos mediante renombre atomico. Ante error o interrupcion
se conservan las fuentes y parciales; solo se retiran crudos tras confirmar
una publicacion reabierta, hasheada y durable. Una publicacion anterior se
respalda antes de actualizarla, sin retirar automaticamente ese respaldo.
Los resultados y temporales deben residir fisicamente en ``/Volumes/Datos``.
Los NetCDF historicos de ``raw_chile`` no forman parte de este flujo y jamas se
eliminan implicitamente.

ERA5 ``boundary_layer_height`` tiene grilla nativa de 0,25 grados y no se
mezcla en este descargador de ERA5-Land. El argumento historico ``--sin-blh``
se acepta por compatibilidad, pero el comportamiento actual ya lo omite.
"""
from __future__ import annotations

import argparse
import atexit
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
from uuid import uuid4

import numpy as np
import pandas as pd

from normalizar_era5land_chile import (
    COMUNAS,
    DATA_ROOT,
    RAIZ_SALIDA,
    RESOLUCION,
    _escribir_json_atomico,
    _fsync_archivo,
    _indices_candidatos,
    _inventario_fuente,
    crear_catalogos,
    eliminar_fuentes_validadas,
    normalizar_mes,
    sha256_archivo,
    validar_salida_mensual,
)


VOLUMEN_DATOS = Path("/Volumes/Datos")
CONT = DATA_ROOT / "contaminantes"
LEGADO = CONT / "ERA5Land" / "raw_chile"
STAGING = CONT / "ERA5Land" / "staging_descarga"
ESPACIO_MINIMO_GB = 5.0
TAMANO_MINIMO_NETCDF = 4_096
VARS_LAND = [
    "2m_temperature",
    "2m_dewpoint_temperature",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "surface_pressure",
    "total_precipitation",
]
CANONICAS_LAND = ["t2m", "d2m", "u10", "v10", "sp", "tp"]
HORAS = [f"{h:02d}:00" for h in range(24)]
ALIASES_CDS = {
    "2m_temperature": {"t2m", "2m_temperature"},
    "2m_dewpoint_temperature": {"d2m", "2m_dewpoint_temperature"},
    "10m_u_component_of_wind": {"u10", "u10m", "10m_u_component_of_wind"},
    "10m_v_component_of_wind": {"v10", "v10m", "10m_v_component_of_wind"},
    "surface_pressure": {"sp", "ps", "surface_pressure"},
    "total_precipitation": {"tp", "total_precipitation"},
}

_PARCIALES_ACTIVOS: set[Path] = set()
_CRUDOS_TRANSITORIOS: set[Path] = set()
_LOCK_ACTIVO: Path | None = None


def asegurar_disco_externo(ruta: Path) -> None:
    volumen = VOLUMEN_DATOS.resolve()
    if not VOLUMEN_DATOS.is_mount():
        raise RuntimeError("/Volumes/Datos no esta montado; descarga abortada")
    real = Path(ruta).expanduser().resolve(strict=False)
    if real != volumen and volumen not in real.parents:
        raise RuntimeError(f"destino fuera del disco externo obligatorio: {real}")


def asegurar_espacio(ruta: Path, minimo_gb: float) -> None:
    asegurar_disco_externo(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    libres = shutil.disk_usage(ruta.parent).free
    if libres < int(minimo_gb * 1024**3):
        raise RuntimeError(
            f"espacio insuficiente: {libres / 1024**3:.1f} GiB libres; "
            f"se exigen {minimo_gb:.1f} GiB"
        )


def _limpiar_recursos() -> None:
    """Libera el lock; nunca interpreta un fallo como permiso para borrar."""
    global _LOCK_ACTIVO
    if _LOCK_ACTIVO is not None:
        try:
            if _LOCK_ACTIVO.read_text().strip() == str(os.getpid()):
                _LOCK_ACTIVO.unlink(missing_ok=True)
        except Exception:
            pass
        _LOCK_ACTIVO = None


def _interrumpir(signum, _frame) -> None:
    # Con AOIs paralelos, los hilos deben abandonar/cerrar primero sus archivos.
    # El finally del lock y atexit solo liberan el bloqueo, no las fuentes.
    raise KeyboardInterrupt(f"interrumpido por senal {signum}")


def _activar_limpieza() -> None:
    atexit.register(_limpiar_recursos)
    signal.signal(signal.SIGINT, _interrumpir)
    signal.signal(signal.SIGTERM, _interrumpir)


def _pid_activo(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, ValueError):
        return False
    except PermissionError:
        return True
    return True


def _otros_descargadores_python() -> list[int]:
    """Detecta una version antigua aunque alguien haya retirado su lock."""
    try:
        salida = subprocess.check_output(
            ["ps", "-ax", "-o", "pid=,command="], text=True
        )
    except (OSError, subprocess.SubprocessError):
        return []
    encontrados = []
    for linea in salida.splitlines():
        partes = linea.strip().split(maxsplit=1)
        if len(partes) != 2:
            continue
        try:
            pid = int(partes[0])
        except ValueError:
            continue
        comando = partes[1]
        ejecutable = Path(comando.split(maxsplit=1)[0]).name.lower()
        if (pid != os.getpid() and "python" in ejecutable
                and "descargar_era5land.py" in comando):
            encontrados.append(pid)
    return encontrados


@contextmanager
def bloqueo_exclusivo(carpeta: Path):
    """Comparte el lock historico para no competir con una descarga antigua."""
    global _LOCK_ACTIVO
    asegurar_disco_externo(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    otros = _otros_descargadores_python()
    if otros:
        raise RuntimeError(
            f"ya hay otra descarga ERA5 activa (PID {otros}); no se inicia otra"
        )
    lock = carpeta / ".descargar_era5land.lock"
    for _ in range(2):
        try:
            descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as fh:
                fh.write(str(os.getpid()))
            _LOCK_ACTIVO = lock
            break
        except FileExistsError:
            try:
                pid = int(lock.read_text().strip())
            except (OSError, ValueError):
                pid = -1
            if _pid_activo(pid):
                raise RuntimeError(
                    f"ya hay una descarga ERA5 activa (PID {pid}); no se inicia otra"
                )
            lock.unlink(missing_ok=True)
    else:
        raise RuntimeError(f"no se pudo adquirir el bloqueo {lock}")
    try:
        yield
    finally:
        _limpiar_recursos()


def _cargar_aois():
    import sys

    raiz_repo = Path(__file__).resolve().parents[2]
    if str(raiz_repo) not in sys.path:
        sys.path.insert(0, str(raiz_repo))
    from scripts_pipeline._chile_aoi import derivar

    return derivar(COMUNAS, margen=RESOLUCION / 2)


def _area_cds(aoi) -> list[float]:
    """Alinea el bbox derivado a centros exactos de la grilla nativa."""
    candidatos = list(_indices_candidatos(aoi.bbox))
    if not candidatos:
        raise ValueError(f"AOI sin centros ERA5-Land: {aoi.id}")
    latitudes = [x[2] for x in candidatos]
    longitudes = [x[3] for x in candidatos]
    return [max(latitudes), min(longitudes), min(latitudes), max(longitudes)]


def _nombre_coord(ds, candidatos: tuple[str, ...], etiqueta: str) -> str:
    for nombre in candidatos:
        if nombre in ds.variables or nombre in ds.dims:
            return nombre
    raise ValueError(f"falta coordenada de {etiqueta}")


def _comprobar_bbox(ds, lat: str, lon: str, area: list[float]) -> None:
    latitudes = np.asarray(ds[lat].values, dtype="float64").reshape(-1)
    longitudes = np.asarray(ds[lon].values, dtype="float64").reshape(-1)
    latitudes = np.unique(np.sort(latitudes[np.isfinite(latitudes)]))
    longitudes = np.unique(np.sort(
        ((longitudes[np.isfinite(longitudes)] + 180.0) % 360.0) - 180.0
    ))
    if not len(latitudes) or not len(longitudes):
        raise ValueError("grilla sin coordenadas espaciales finitas")
    norte, oeste, sur, este = area
    esperado_lat = np.sort(np.arange(sur, norte + RESOLUCION / 2, RESOLUCION))
    esperado_lon = np.sort(np.arange(oeste, este + RESOLUCION / 2, RESOLUCION))
    if (len(latitudes) != len(esperado_lat)
            or not np.allclose(latitudes, esperado_lat, atol=1e-6)):
        raise ValueError("latitudes incompletas o fuera del AOI solicitado")
    if (len(longitudes) != len(esperado_lon)
            or not np.allclose(longitudes, esperado_lon, atol=1e-6)):
        raise ValueError("longitudes incompletas o fuera del AOI solicitado")


def validar_netcdf(
    ruta: Path,
    variables: list[str],
    pasos_esperados: int,
    periodo: pd.Period,
    area: list[float],
) -> None:
    """Valida cada crudo AOI antes de permitir que alimente el recorte."""
    asegurar_disco_externo(ruta)
    if not ruta.exists() or ruta.stat().st_size <= TAMANO_MINIMO_NETCDF:
        raise ValueError(f"archivo ausente o demasiado pequeno: {ruta.name}")
    import xarray as xr

    with xr.open_dataset(ruta) as ds:
        presentes = {nombre.lower(): nombre for nombre in ds.data_vars}
        faltantes = [
            v for v in variables
            if not ({a.lower() for a in ALIASES_CDS[v]} & set(presentes))
        ]
        if faltantes:
            raise ValueError(f"faltan variables {faltantes} en {ruta.name}")
        temporal = _nombre_coord(ds, ("valid_time", "time"), "tiempo")
        lat = _nombre_coord(ds, ("latitude", "lat"), "latitud")
        lon = _nombre_coord(ds, ("longitude", "lon"), "longitud")
        _comprobar_bbox(ds, lat, lon, area)
        tiempos = pd.DatetimeIndex(pd.to_datetime(
            np.asarray(ds[temporal].values).reshape(-1), errors="coerce", utc=True
        )).sort_values()
        inicio = pd.Timestamp(periodo.start_time, tz="UTC")
        esperado = pd.date_range(inicio, periods=pasos_esperados, freq="h")
        if (tiempos.hasnans or tiempos.has_duplicates
                or not tiempos.equals(esperado)):
            raise ValueError(
                f"horas incompletas/desplazadas en {ruta.name}: "
                f"{len(tiempos)}/{pasos_esperados}"
            )
        for variable in variables:
            original = next(
                presentes[a.lower()] for a in ALIASES_CDS[variable]
                if a.lower() in presentes
            )
            if not {temporal, lat, lon}.issubset(ds[original].dims):
                raise ValueError(f"{original} no depende de hora/latitud/longitud")
            muestra = ds[original].isel({temporal: [0, -1]}).values
            # Islas pequenas pueden ser NaN por la mascara terrestre nativa;
            # se conservan y se declaran honestamente en el manifest.
            if area[1] > -77 and not np.isfinite(muestra).any():
                raise ValueError(f"{original} no contiene valores continentales")


def pedir(
    cliente,
    request: dict,
    destino: Path,
    variables: list[str],
    pasos: int,
    periodo: pd.Period,
    area: list[float],
    espacio_minimo_gb: float,
) -> Path:
    asegurar_espacio(destino, espacio_minimo_gb)
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        try:
            validar_netcdf(destino, variables, pasos, periodo, area)
            _CRUDOS_TRANSITORIOS.add(destino)
            print(f"  reutilizado transitorio validado {destino.name}", flush=True)
            return destino
        except Exception as exc:
            raise RuntimeError(
                f"se conserva fuente no valida para esta solicitud: {destino}; "
                "requiere revision antes de reemplazarla"
            ) from exc
    parcial = destino.with_name(f"{destino.stem}.part{destino.suffix}")
    if parcial.exists():
        # Puede contener una descarga completa cuyo renombre fue interrumpido.
        # Una parcial no validable queda intacta; no se sobrescribe a ciegas.
        validar_netcdf(parcial, variables, pasos, periodo, area)
        _fsync_archivo(parcial)
        os.replace(parcial, destino)
        _fsync_directorio(destino.parent)
        _CRUDOS_TRANSITORIOS.add(destino)
        return destino
    _PARCIALES_ACTIVOS.add(parcial)
    print(f"  solicitando {destino.name} ...", flush=True)
    try:
        cliente.retrieve("reanalysis-era5-land", request, str(parcial))
        validar_netcdf(parcial, variables, pasos, periodo, area)
        _fsync_archivo(parcial)
        os.replace(parcial, destino)
        _CRUDOS_TRANSITORIOS.add(destino)
        _fsync_directorio(destino.parent)
        print(f"  AOI validado {destino.name}", flush=True)
    finally:
        _PARCIALES_ACTIVOS.discard(parcial)
    return destino


def _salida_ya_valida(
    raiz: Path,
    periodo: pd.Period,
    variables: list[str],
    horas: int,
    permitir_parcial: bool,
) -> bool:
    salida = raiz / "mensual" / f"era5land_{periodo.strftime('%Y%m')}_chile_pixeles.nc"
    manifest = raiz / "manifiestos" / f"era5land_{periodo.strftime('%Y%m')}.json"
    catalogo = raiz / "catalogo_pixeles.parquet"
    if not (salida.exists() and manifest.exists() and catalogo.exists()):
        return False
    try:
        meta = json.loads(manifest.read_text(encoding="utf-8"))
        descarga = meta.get("descarga_cds", {})
        if (descarga.get("dataset") != "reanalysis-era5-land"
                or not descarga.get("requests_sin_credenciales")):
            return False
        # Publicar el NetCDF no completa la transaccion: una anotacion o un
        # retiro fallidos se deben reintentar usando las fuentes conservadas.
        # No exigir la bandera de retiro de TODAS las fuentes: el legado puede
        # haberse conservado deliberadamente y retirado en una auditoria aparte.
        pendientes = STAGING / periodo.strftime("%Y%m")
        if any(p.is_file() for p in pendientes.rglob("*")):
            return False
        if sha256_archivo(salida) != meta["salida"]["sha256"]:
            return False
        validacion = validar_salida_mensual(
            salida, periodo, catalogo, variables, permitir_parcial
        )
        return validacion["horas"] == horas
    except Exception:
        return False


def _tp_legado_continental_valida(
    path: Path,
    periodo: pd.Period,
    horas: int,
    catalogo_path: Path,
) -> bool:
    """Permite aprovechar TP nativa ya bajada sin declarar que cubre islas."""
    try:
        inventario = _inventario_fuente(path, periodo)
        if "tp" not in inventario["variables"] or len(inventario["times"]) != horas:
            return False
        catalogo = pd.read_parquet(
            catalogo_path,
            columns=["aoi_id", "lat_index_global", "lon_index_global"],
        )
        continente = catalogo[catalogo.aoi_id == "continente"]
        lat_fuente = set(int(x) for x in inventario["ilat"])
        lon_fuente = set(int(x) for x in inventario["ilon"])
        return (
            set(int(x) for x in continente.lat_index_global).issubset(lat_fuente)
            and set(int(x) for x in continente.lon_index_global).issubset(lon_fuente)
        )
    except Exception:
        return False


def _meteorologia_legado_valida(
    path: Path,
    periodo: pd.Period,
    horas: int,
    catalogo_path: Path,
) -> bool:
    """Valida que el rectangulo legado aporte los cinco campos no redundantes."""
    try:
        inventario = _inventario_fuente(path, periodo)
        requeridas = {"t2m", "d2m", "u10", "v10", "sp"}
        if (not requeridas.issubset(inventario["variables"])
                or len(inventario["times"]) != horas):
            return False
        catalogo = pd.read_parquet(
            catalogo_path, columns=["lat_index_global", "lon_index_global"]
        )
        return (
            set(int(x) for x in catalogo.lat_index_global).issubset(
                int(x) for x in inventario["ilat"]
            )
            and set(int(x) for x in catalogo.lon_index_global).issubset(
                int(x) for x in inventario["ilon"]
            )
        )
    except Exception:
        return False


def _anotar_descarga(
    manifest: Path,
    requests: list[dict[str, object]],
    fecha_corte: pd.Timestamp,
) -> None:
    meta = json.loads(manifest.read_text(encoding="utf-8"))
    try:
        import cdsapi
        version_cdsapi = str(getattr(cdsapi, "__version__", "desconocida"))
    except ImportError:
        version_cdsapi = "desconocida"
    meta["descarga_cds"] = {
        "dataset": "reanalysis-era5-land",
        "fecha_corte_disponibilidad_utc": fecha_corte.isoformat(),
        "requests_sin_credenciales": requests,
        "descargador": {
            "archivo": Path(__file__).name,
            "sha256": sha256_archivo(Path(__file__)),
            "cdsapi": version_cdsapi,
        },
    }
    _escribir_json_atomico(manifest, meta)


def _fsync_directorio(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _respaldar_publicacion(salida: Path, manifest: Path, periodo: pd.Period):
    """Conserva la pareja anterior incluso si la nueva publicacion falla."""
    existentes = [p for p in (salida, manifest) if p.exists()]
    if not existentes:
        return None
    raiz = salida.parent.parent / "_respaldos_publicacion"
    mes = raiz / periodo.strftime("%Y%m")
    destino = mes / uuid4().hex
    for carpeta in (raiz, mes, destino):
        asegurar_disco_externo(carpeta)
        carpeta.mkdir(exist_ok=carpeta != destino)
        _fsync_directorio(carpeta.parent)
    artefactos = []
    for original in existentes:
        asegurar_disco_externo(original)
        esperado = sha256_archivo(original)
        copia = destino / original.name
        with original.open("rb") as src, copia.open("xb") as dst:
            shutil.copyfileobj(src, dst)
            dst.flush()
            os.fsync(dst.fileno())
        if sha256_archivo(copia) != esperado or sha256_archivo(original) != esperado:
            raise ValueError(f"cambio durante respaldo: {original}")
        artefactos.append({
            "original": str(original), "respaldo": str(copia),
            "bytes": copia.stat().st_size, "sha256": esperado,
        })
    previo = None
    if manifest.exists():
        try:
            previo = json.loads((destino / manifest.name).read_text())
        except (ValueError, UnicodeError):
            pass  # Se conserva tambien un manifiesto incompleto/no interpretable.
    registro = destino / "respaldo.json"
    _escribir_json_atomico(registro, {
        "schema": "airpollution.era5land-respaldo-publicacion.v1",
        "periodo": str(periodo), "registrado_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "artefactos": artefactos, "manifiesto_previo": previo,
        "codigo_resguardo_sha256": sha256_archivo(Path(__file__)),
        "retiro_automatico_permitido": False,
    })
    _fsync_directorio(destino)
    return {"registro": str(registro), "sha256": sha256_archivo(registro)}


def _publicar_mes_seguro(
    fuentes, transitorios, periodo, raiz, catalogo_path, variables,
    permitir_parcial, requests_manifest, fecha_corte,
):
    """Resguardo local del descargador; no cambia el motor compartido/BLH."""
    salida_previa = raiz / "mensual" / f"era5land_{periodo.strftime('%Y%m')}_chile_pixeles.nc"
    manifest_previo = raiz / "manifiestos" / f"era5land_{periodo.strftime('%Y%m')}.json"
    respaldo = _respaldar_publicacion(salida_previa, manifest_previo, periodo)
    salida, manifest = normalizar_mes(
        fuentes, periodo, raiz, COMUNAS, variables, permitir_parcial,
    )
    _anotar_descarga(manifest, requests_manifest, fecha_corte)
    validar_salida_mensual(salida, periodo, catalogo_path, variables, permitir_parcial)
    meta = json.loads(manifest.read_text())
    if sha256_archivo(salida) != meta["salida"]["sha256"]:
        raise ValueError("no se retiran crudos: hash de publicacion invalido")
    declaradas = {Path(x["ruta_al_normalizar"]).resolve(): x for x in meta["fuentes"]}
    for fuente in transitorios:
        if STAGING.resolve() not in fuente.resolve().parents:
            raise ValueError(f"retiro fuera de staging prohibido: {fuente}")
        if (fuente.resolve() not in declaradas
                or sha256_archivo(fuente) != declaradas[fuente.resolve()]["sha256"]):
            raise ValueError(f"fuente sin hash confirmado: {fuente}")
    if respaldo is not None:
        meta["respaldo_publicacion_previa"] = respaldo
    meta["retiro_transitorios_prevalidado"] = {
        "registrado_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "fuentes": [str(p) for p in transitorios],
        "sha256_salida": meta["salida"]["sha256"],
    }
    _escribir_json_atomico(manifest, meta)
    # Persistir archivos y renombres antes de cualquier unlink de una fuente.
    for archivo in (salida, manifest):
        _fsync_archivo(archivo)
        _fsync_directorio(archivo.parent)
    liberados = eliminar_fuentes_validadas(
        transitorios, salida, manifest, periodo, catalogo_path, permitir_parcial,
    )
    _fsync_archivo(manifest)
    _fsync_directorio(manifest.parent)
    return liberados


def main() -> None:
    hoy = pd.Timestamp.now(tz="UTC").normalize()
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", default="2000-01")
    ap.add_argument("--hasta", default=hoy.strftime("%Y-%m"))
    ap.add_argument(
        "--rezago-dias", type=int, default=6,
        help="margen frente al rezago del CDS; fecha efectiva=hoy-rezago (default 6)",
    )
    ap.add_argument(
        "--solo-precipitacion", action="store_true",
        help="publica TP en una raiz separada para no sobrescribir el producto completo",
    )
    ap.add_argument(
        "--espacio-minimo-gb", type=float, default=ESPACIO_MINIMO_GB,
        help="abortar si el disco externo tiene menos espacio libre",
    )
    ap.add_argument(
        "--procesos-aoi", type=int, default=5,
        help="solicitudes CDS simultaneas por mes (1-5; default 5)",
    )
    ap.add_argument("--sin-blh", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--extraer-estaciones", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--extraer-y-limpiar", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if (a.espacio_minimo_gb < 0 or a.rezago_dias < 0
            or not 1 <= a.procesos_aoi <= 5):
        ap.error("espacio/rezago deben ser no negativos y procesos-aoi debe ser 1-5")
    if a.extraer_estaciones:
        ap.error(
            "la salida primaria ahora es la grilla nativa; la union con estaciones "
            "debe ejecutarse como etapa derivada"
        )
    if a.extraer_y_limpiar:
        print(
            "Aviso: --extraer-y-limpiar ya no es necesario; los crudos de staging "
            "siempre se eliminan despues de validar.", flush=True,
        )
    try:
        desde = pd.Period(a.desde, freq="M")
        hasta_pedida = pd.Period(a.hasta, freq="M")
    except ValueError as exc:
        ap.error(f"mes invalido: {exc}")
    fecha_corte = hoy - pd.Timedelta(days=a.rezago_dias)
    hasta_disponible = fecha_corte.tz_localize(None).to_period("M")
    hasta = min(hasta_pedida, hasta_disponible)
    if desde > hasta:
        ap.error("el rango no contiene meses disponibles")

    variables_cds = ["total_precipitation"] if a.solo_precipitacion else VARS_LAND
    variables_canon = ["tp"] if a.solo_precipitacion else CANONICAS_LAND
    raiz = (
        RAIZ_SALIDA.with_name("chile_nativo_01deg_tp")
        if a.solo_precipitacion else RAIZ_SALIDA
    )
    _activar_limpieza()
    asegurar_disco_externo(CONT)
    catalogo_path, _, _ = crear_catalogos(raiz, COMUNAS)
    aois = _cargar_aois()
    areas = {aoi.id: _area_cds(aoi) for aoi in aois}
    import cdsapi

    meses = list(pd.period_range(desde, hasta, freq="M"))
    print(
        f"ERA5-Land nativo: {desde} -> {hasta}; corte disponible "
        f"{fecha_corte.date()}; {len(aois)} AOIs sin corredor en la salida",
        flush=True,
    )

    # Se usa el lock antiguo para respetar cualquier proceso cargado con una
    # version previa del script. Modificar este archivo no afecta ese proceso.
    with bloqueo_exclusivo(LEGADO):
        for periodo in meses:
            ultimo_dia = periodo.days_in_month
            permitir_parcial = False
            if periodo == hasta_disponible and fecha_corte.day < ultimo_dia:
                ultimo_dia = int(fecha_corte.day)
                permitir_parcial = True
            dias = [f"{d:02d}" for d in range(1, ultimo_dia + 1)]
            horas_esperadas = len(dias) * 24
            if _salida_ya_valida(
                raiz, periodo, variables_canon, horas_esperadas, permitir_parcial
            ):
                print(f"  {periodo}: salida final ya validada; se omite CDS", flush=True)
                continue

            fuentes_mes: list[Path] = []
            transitorios: list[Path] = []
            requests_manifest: list[dict[str, object]] = []
            try:
                aois_pendientes = list(aois)
                variables_cds_mes = list(variables_cds)
                legado_meteo = (
                    LEGADO / f"era5land_{periodo.strftime('%Y%m')}_chile.nc"
                )
                if (not a.solo_precipitacion and legado_meteo.exists()
                        and _meteorologia_legado_valida(
                            legado_meteo, periodo, horas_esperadas, catalogo_path
                        )):
                    fuentes_mes.append(legado_meteo)
                    variables_cds_mes = ["total_precipitation"]
                    requests_manifest.append({
                        "aoi_id": "cinco_territorios",
                        "fuente_reutilizada": legado_meteo.name,
                        "sha256": sha256_archivo(legado_meteo),
                        "variables": [
                            "2m_temperature", "2m_dewpoint_temperature",
                            "10m_u_component_of_wind", "10m_v_component_of_wind",
                            "surface_pressure",
                        ],
                        "nota": (
                            "grilla 0,1 grados hasheada; se recorta, no se borra "
                            "en esta corrida; RH2M redundante no se duplica"
                        ),
                    })
                    print(
                        f"  {periodo}: reutilizando meteorologia nativa existente; "
                        "CDS solo debe completar TP",
                        flush=True,
                    )
                legado_tp = LEGADO / f"era5land_tp_{periodo.strftime('%Y%m')}.nc"
                if (variables_cds_mes == ["total_precipitation"]
                        and legado_tp.exists()
                        and _tp_legado_continental_valida(
                            legado_tp, periodo, horas_esperadas, catalogo_path
                        )):
                    fuentes_mes.append(legado_tp)
                    aois_pendientes = [x for x in aois if x.id != "continente"]
                    requests_manifest.append({
                        "aoi_id": "continente",
                        "territorio": "continental",
                        "fuente_reutilizada": legado_tp.name,
                        "sha256": sha256_archivo(legado_tp),
                        "nota": (
                            "NetCDF nativo 0,1 grados conservado; no se elimina "
                            "en esta corrida"
                        ),
                    })
                    print(
                        f"  {periodo}: reutilizando TP continental nativa; "
                        "se solicitan solo las islas",
                        flush=True,
                    )
                trabajos = []
                for aoi in aois_pendientes:
                    area = areas[aoi.id]
                    request = {
                        "variable": variables_cds_mes,
                        "year": str(periodo.year),
                        "month": f"{periodo.month:02d}",
                        "day": dias,
                        "time": HORAS,
                        "area": area,
                        "data_format": "netcdf",
                        "download_format": "unarchived",
                    }
                    destino = (
                        STAGING / periodo.strftime("%Y%m")
                        / f"era5land_{periodo.strftime('%Y%m')}.{aoi.id}.nc"
                    )
                    trabajos.append((aoi, area, request, destino))
                    requests_manifest.append(
                        {
                            "aoi_id": aoi.id,
                            "territorio": aoi.territorio,
                            **request,
                        }
                    )

                def descargar_trabajo(trabajo):
                    aoi, area, request, destino = trabajo
                    cliente_hilo = cdsapi.Client()
                    path = pedir(
                        cliente_hilo, request, destino, variables_cds_mes,
                        horas_esperadas, periodo, area, a.espacio_minimo_gb,
                    )
                    return aoi.id, path

                resultados = {}
                with ThreadPoolExecutor(
                    max_workers=min(a.procesos_aoi, len(trabajos))
                ) as pool:
                    futuros = {
                        pool.submit(descargar_trabajo, trabajo): trabajo[0].id
                        for trabajo in trabajos
                    }
                    for futuro in as_completed(futuros):
                        aoi_id, path = futuro.result()
                        resultados[aoi_id] = path
                # Orden estable para hashes/manifiesto aunque las descargas
                # terminen en distinto orden.
                for aoi in aois_pendientes:
                    path = resultados[aoi.id]
                    transitorios.append(path)
                    fuentes_mes.append(path)

                liberados = _publicar_mes_seguro(
                    fuentes_mes, transitorios, periodo, raiz, catalogo_path,
                    variables_canon, permitir_parcial, requests_manifest, fecha_corte,
                )
                for path in transitorios:
                    _CRUDOS_TRANSITORIOS.discard(path)
                print(
                    f"  {periodo}: publicado y revalidado; "
                    f"{liberados / 1024**2:.1f} MiB transitorios eliminados",
                    flush=True,
                )
            except BaseException:
                print(f"  {periodo}: fallo; se conservan fuentes y respaldos", flush=True)
                raise

    if STAGING.exists():
        for carpeta in sorted(STAGING.glob("*"), reverse=True):
            if carpeta.is_dir() and not any(carpeta.iterdir()):
                carpeta.rmdir()
        if not any(STAGING.iterdir()):
            STAGING.rmdir()
    print("DESCARGA ERA5-LAND COMPLETA Y SIN CRUDOS TRANSITORIOS", flush=True)


if __name__ == "__main__":
    main()
