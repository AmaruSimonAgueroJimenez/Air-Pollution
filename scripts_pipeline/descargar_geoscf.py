#!/usr/bin/env python3
"""NASA GEOS-CF horario nativo para Chile administrativo completo.

Lee por OPeNDAP las colecciones publicas ``aqc_tavg_1hr_g1440x721_v1`` hasta
2025 y ``aqc_tavg_1hr_glo_L1440x721_slv`` desde 2026 (0,25 grados, marcas
HH:30 UTC), y conserva O3, NO2, SO2, CO y PM2.5 de superficie.
Descarga cinco AOIs administrativos separados y publica un NetCDF mensual
``time x pixel``: sin corredor oceanico, remuestreo, interpolacion ni promedio
comunal. Cada salida se enlaza muchos-a-muchos a comuna.

Los AOIs son transitorios y se eliminan solo tras reabrir/hash-validar el mes
final. Los rectangulos continentales historicos se reutilizan, pero se
conservan hasta que exista reemplazo validado para su mes.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import CONTAMINANTES, ensure_dir, get_logger, retry  # noqa: E402
from _chile_aoi import derivar  # noqa: E402
from normalizar_reanalisis_chile import (  # noqa: E402
    COMUNAS,
    PRODUCTOS,
    _json_atomico,
    eliminar_fuentes_validadas,
    exigir_espacio,
    normalizar_mes,
    salida_vigente,
    sha256_archivo,
)


log = get_logger("geoscf")
SPEC = PRODUCTOS["geos_cf"]
BASES = {
    "v1": "https://opendap.nccs.nasa.gov/dods/gmao/geos-cf/assim/aqc_tavg_1hr_g1440x721_v1",
    "v2": "https://opendap.nccs.nasa.gov/dods/gmao/geos-cf/v2/ana/aqc_tavg_1hr_glo_L1440x721_slv",
}
STAGING = SPEC.salida / "_staging_descarga"
LEGADO = CONTAMINANTES / "GEOS_CF" / "raw_chile"
VARS = {
    "o3": ("O3", "o3"),
    "no2": ("NO2", "no2"),
    "so2": ("SO2", "so2"),
    "co": ("CO", "co"),
    "pm25": ("PM25_RH35_GCC", "pm25_rh35_gcc", "PM25_RH35", "pm25_rh35"),
}
DIAS_TROZO = 5


def version_periodo(periodo: pd.Period) -> str:
    """v1 cubre 2018-2025; v2 es la serie operativa para 2026+."""
    return "v1" if periodo.year <= 2025 else "v2"


def abrir(version: str):
    import xarray as xr

    base = BASES[version]
    log.info("Abriendo GEOS-CF %s: %s", version, base)
    return xr.open_dataset(base, engine="pydap")


def resolver_vars(ds):
    por_lower = {str(v).lower(): str(v) for v in ds.data_vars}
    out = {}
    for canonico, candidatos in VARS.items():
        for candidato in candidatos:
            if candidato.lower() in por_lower:
                out[canonico] = por_lower[candidato.lower()]
                break
    faltan = set(VARS) - set(out)
    if faltan:
        raise ValueError(f"GEOS-CF no expone {sorted(faltan)}")
    return out


def _legacy(periodo: pd.Period) -> list[Path]:
    path = LEGADO / f"geoscf_{periodo.strftime('%Y%m')}.nc"
    return [path] if path.exists() else []


def _slice_coord(coord, minimo: float, maximo: float):
    valores = np.asarray(coord.values)
    return slice(minimo, maximo) if valores[0] < valores[-1] else slice(maximo, minimo)


@retry(n=8, base=5.0)
def _bajar_trozo(ds, cols, desde, hasta, aoi):
    oeste, sur, este, norte = aoi.bbox
    time = "time"
    lat = "lat" if "lat" in ds.coords else "latitude"
    lon = "lon" if "lon" in ds.coords else "longitude"
    sub = (
        ds[list(cols.values())]
        .sel({time: slice(str(desde.date()), str(hasta.date()))})
        .sel({lat: _slice_coord(ds[lat], sur, norte), lon: _slice_coord(ds[lon], oeste, este)})
    )
    sub.load()
    return sub


def _validar_stage(
    path: Path, periodo: pd.Period, aoi_id: str, permitir_parcial: bool = False
) -> None:
    import xarray as xr

    with xr.open_dataset(path) as ds:
        time = "time"
        lat = "lat" if "lat" in ds.coords else "latitude"
        lon = "lon" if "lon" in ds.coords else "longitude"
        tiempos = pd.DatetimeIndex(pd.to_datetime(ds[time].values, utc=True))
        esperado = pd.date_range(
            pd.Timestamp(periodo.start_time, tz="UTC") + pd.Timedelta(minutes=30),
            periods=periodo.days_in_month * 24,
            freq="h",
        )
        temporal_ok = (
            tiempos.equals(esperado[: len(tiempos)])
            if permitir_parcial else tiempos.equals(esperado)
        )
        if not temporal_ok:
            raise ValueError(f"{path.name}: tiempo GEOS-CF incompleto/no nativo")
        if not len(ds[lat]) or not len(ds[lon]):
            raise ValueError(f"{path.name}: AOI vacia")
        if ds.attrs.get("aoi_id") not in (None, aoi_id):
            raise ValueError(f"{path.name}: aoi_id inconsistente")
        presentes = {str(v).lower() for v in ds.data_vars}
        for candidatos in VARS.values():
            if not any(v.lower() in presentes for v in candidatos):
                raise ValueError(f"{path.name}: falta {candidatos[0]}")
        for da in ds.data_vars.values():
            muestra = np.asarray(da.isel({time: [0, -1]}))
            if np.isfinite(muestra).any():
                break
        else:
            raise ValueError(f"{path.name}: sin datos finitos")


def bajar_aoi(
    ds, cols, periodo: pd.Period, aoi, destino: Path,
    *, version: str, fin_disponible: pd.Timestamp, permitir_parcial: bool,
) -> Path:
    import xarray as xr

    if destino.exists():
        _validar_stage(destino, periodo, aoi.id, permitir_parcial)
        inicio = pd.Timestamp(periodo.start_time, tz="UTC") + pd.Timedelta(minutes=30)
        ultimo_mes = pd.Timestamp(periodo.end_time.normalize(), tz="UTC") + pd.Timedelta(hours=23, minutes=30)
        fin_esperado = min(fin_disponible, ultimo_mes)
        n_esperado = int((fin_esperado - inicio) / pd.Timedelta(hours=1)) + 1
        with xr.open_dataset(destino) as previo:
            if previo.sizes.get("time", 0) == n_esperado:
                return destino
        # Es staging parcial de una corrida anterior; se reconstruye con el
        # prefijo mas reciente. La salida mensual publicada no se toca aqui.
        destino.unlink()
    trozos, cursor = [], pd.Timestamp(periodo.start_time)
    fin_mes = min(pd.Timestamp(periodo.end_time).normalize(), fin_disponible.tz_localize(None).normalize())
    while cursor <= fin_mes:
        fin = min(cursor + pd.Timedelta(days=DIAS_TROZO - 1), fin_mes)
        trozos.append(_bajar_trozo(ds, cols, cursor, fin, aoi))
        cursor = fin + pd.Timedelta(days=1)
    sub = xr.concat(trozos, dim="time") if len(trozos) > 1 else trozos[0]
    sub.attrs.update(
        aoi_id=aoi.id,
        territorio=aoi.territorio,
        source_opendap=BASES[version],
        geos_cf_version=version,
        native_resolution="0.25 degree",
        native_time="hourly UTC at HH:30",
        spatial_operation="temporary native-grid AOI; no resampling",
    )
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(destino.suffix + ".part")
    tmp.unlink(missing_ok=True)
    try:
        sub.to_netcdf(
            tmp, engine="netcdf4", format="NETCDF4",
            encoding={v: {"zlib": True, "complevel": 4, "shuffle": True} for v in sub.data_vars},
        )
        _validar_stage(tmp, periodo, aoi.id, permitir_parcial)
        with tmp.open("rb") as fh:
            os.fsync(fh.fileno())
        os.replace(tmp, destino)
        _validar_stage(destino, periodo, aoi.id, permitir_parcial)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return destino


def procesar_mes(
    ds,
    cols,
    periodo: pd.Period,
    comunas: Path,
    *,
    version: str,
    fin_disponible: pd.Timestamp,
    permitir_parcial: bool,
    espacio_minimo: float,
    dry_run: bool,
) -> None:
    if salida_vigente(SPEC, periodo, comunas, aceptar_parcial=False):
        log.info("%s ya validado", periodo)
        return
    legacy = _legacy(periodo)
    aois = derivar(comunas, margen=max(SPEC.resolucion_lat, SPEC.resolucion_lon) / 2)
    pedidos = tuple(a for a in aois if not legacy or a.id != "continente")
    log.info("%s: legado=%d; AOIs por OPeNDAP=%d", periodo, len(legacy), len(pedidos))
    if dry_run:
        return
    mes_dir = ensure_dir(STAGING / periodo.strftime("%Y%m"))
    staging = []
    for aoi in pedidos:
        exigir_espacio(SPEC.salida, espacio_minimo)
        destino = mes_dir / f"geoscf_{periodo.strftime('%Y%m')}.{aoi.id}.stage.nc"
        staging.append(
            bajar_aoi(
                ds, cols, periodo, aoi, destino,
                version=version,
                fin_disponible=fin_disponible,
                permitir_parcial=permitir_parcial,
            )
        )
    fuentes = [*legacy, *staging]
    salida, manifest = normalizar_mes(
        SPEC, fuentes, periodo, comunas,
        permitir_parcial=permitir_parcial,
        espacio_minimo_gib=espacio_minimo,
    )
    meta = json.loads(manifest.read_text(encoding="utf-8"))
    meta["adquisicion"] = {
        "opendap": BASES[version],
        "geos_cf_version": version,
        "variables_resueltas": cols,
        "fuentes_mensuales_legacy_reutilizadas": [str(x) for x in legacy],
        "aois_descargadas": [
            {"id": a.id, "territorio": a.territorio, "bbox_wsen": list(a.bbox)}
            for a in pedidos
        ],
        "descargador": str(Path(__file__).resolve()),
        "descargador_sha256": sha256_archivo(Path(__file__)),
        "estado_periodo": "parcial_pendiente" if permitir_parcial else "completo",
    }
    _json_atomico(manifest, meta)
    if staging and not permitir_parcial:
        liberados = eliminar_fuentes_validadas(SPEC, staging, periodo, salida, manifest)
        try:
            mes_dir.rmdir()
        except OSError:
            pass
        log.info("%s validado; staging retirado (%.3f GiB)", periodo, liberados / 1024**3)
    elif permitir_parcial:
        log.info("%s publicado parcial; staging conservado para completar", periodo)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--desde", default="2018-01-01")
    ap.add_argument("--hasta", default=date.today().isoformat())
    ap.add_argument("--comunas", type=Path, default=COMUNAS)
    ap.add_argument("--espacio-minimo-gb", type=float, default=100)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    p0 = max(pd.Period(a.desde[:7], "M"), pd.Period("2018-01", "M"))
    p1 = pd.Period(a.hasta[:7], "M")
    if p1 < p0:
        ap.error("rango anterior al inicio nativo 2018-01")
    periodos = list(pd.period_range(p0, p1, freq="M"))
    if a.dry_run:
        for periodo in periodos:
            version = version_periodo(periodo)
            log.info("[dry-run] %s usaria GEOS-CF %s (%s)", periodo, version, BASES[version])
        return
    abiertos = {}
    try:
        for k, periodo in enumerate(periodos):
            version = version_periodo(periodo)
            if version not in abiertos:
                ds = abrir(version)
                cols = resolver_vars(ds)
                ultimo = pd.Timestamp(ds.time.values[-1])
                ultimo = (
                    ultimo.tz_localize("UTC") if ultimo.tzinfo is None
                    else ultimo.tz_convert("UTC")
                )
                abiertos[version] = (ds, cols, ultimo)
            ds, cols, ultimo = abiertos[version]
            primero_mes = pd.Timestamp(periodo.start_time, tz="UTC") + pd.Timedelta(minutes=30)
            ultimo_mes = pd.Timestamp(periodo.end_time.normalize(), tz="UTC") + pd.Timedelta(hours=23, minutes=30)
            if primero_mes > ultimo:
                log.info("%s aun no disponible en GEOS-CF %s", periodo, version)
                continue
            parcial = ultimo < ultimo_mes
            if parcial and k != len(periodos) - 1:
                raise RuntimeError(
                    f"{periodo}: GEOS-CF {version} termina {ultimo.isoformat()} antes "
                    "del mes completo"
                )
            procesar_mes(
                ds, cols, periodo, a.comunas,
                version=version,
                fin_disponible=ultimo,
                permitir_parcial=parcial,
                espacio_minimo=a.espacio_minimo_gb,
                dry_run=False,
            )
    finally:
        for ds, _, _ in abiertos.values():
            ds.close()


if __name__ == "__main__":
    main()
