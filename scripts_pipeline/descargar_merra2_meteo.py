#!/usr/bin/env python3
"""MERRA-2 horario combinado, nativo y recortado a Chile administrativo.

Reemplaza de forma reproducible al productor historico de rectangulos
oceanicos. Combina por dia las colecciones oficiales M2T1NXSLV, M2T1NXFLX y
M2T1NXAER; conserva T2M, QV2M, U10M, V10M, PS, RH2M, PBLH, AOD_M2 y PM25_M2
en las marcas nativas HH:30 UTC. La salida mensual final contiene solo las
419 celdas nativas de 0,5 x 0,625 grados cuya huella toca Chile, con catalogo
y relacion muchos-a-muchos a las 346 unidades administrativas.

Si existen los archivos historicos ``raw_chile_horario`` los reutiliza antes
de recurrir a la red. Nunca elimina esos rectangulos salvo con
``--retirar-legado-validado`` y solo despues de reabrir/hash-validar el
reemplazo mensual. Los globales y recortes de staging nuevos se limpian
automaticamente tras validar un mes completo.
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
from _common import CONTAMINANTES, ensure_dir, get_logger  # noqa: E402
from _env_earthdata import login  # noqa: E402
from descargar_merra2_aer import (  # noqa: E402
    VERSION,
    _aois,
    _coord,
    _fecha_nombre,
    _limpiar_directorios_vacios,
    _nombre_granulo,
    _resolver,
    _url_granulo,
)
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


log = get_logger("merra2_meteo")
SPEC = PRODUCTOS["merra2_meteo"]
STAGING = SPEC.salida / "_staging_descarga"
LEGADO = CONTAMINANTES / "MERRA2_meteo" / "raw_chile_horario"
COLECCIONES = {
    "slv": "M2T1NXSLV",
    "flx": "M2T1NXFLX",
    "aer": "M2T1NXAER",
}
VARS_SLV = ("T2M", "QV2M", "U10M", "V10M", "PS")
VARS_AER_MASA = ("SO4SMASS", "OCSMASS", "BCSMASS", "DUSMASS25", "SSSMASS25")
VARS_SALIDA = (
    "T2M", "QV2M", "U10M", "V10M", "PS", "RH2M", "PBLH", "AOD_M2", "PM25_M2",
)


def _legacy(periodo: pd.Period) -> list[Path]:
    return sorted(LEGADO.glob(f"M2_merra2_hourly_{periodo.strftime('%Y%m')}??_chile.nc"))


def _fecha_legacy(path: Path) -> str:
    return pd.Timestamp(path.stem.split("_")[-2]).strftime("%Y-%m-%d")


def _buscar(short_name: str, periodo: pd.Period):
    import earthaccess

    resultados = earthaccess.search_data(
        short_name=short_name,
        version=VERSION,
        temporal=(
            periodo.start_time.strftime("%Y-%m-%d"),
            periodo.end_time.strftime("%Y-%m-%dT23:59:59"),
        ),
    )
    por_fecha = {}
    for g in resultados:
        fecha = _fecha_nombre(_nombre_granulo(g))
        if fecha in por_fecha:
            raise ValueError(f"{short_name}: mas de un granulo para {fecha}")
        por_fecha[fecha] = g
    return por_fecha


def _descargar(g, carpeta: Path) -> Path:
    import earthaccess
    import xarray as xr

    nombre = _nombre_granulo(g)
    existente = carpeta / nombre
    if existente.exists():
        with xr.open_dataset(existente) as ds:
            if not ds.data_vars:
                raise ValueError(f"global huerfano vacio: {existente}")
        return existente
    archivos = [Path(p) for p in earthaccess.download([g], str(carpeta)) if p]
    if not archivos:
        raise RuntimeError(f"earthaccess no devolvio {nombre}")
    return next((p for p in archivos if p.name == nombre), archivos[0])


def _validar_stage(path: Path, fecha: str, aoi_id: str) -> None:
    import xarray as xr

    with xr.open_dataset(path) as ds:
        if set(VARS_SALIDA) - set(ds.data_vars):
            raise ValueError(f"{path.name}: faltan variables MERRA-2")
        tiempos = pd.DatetimeIndex(pd.to_datetime(ds.time.values, utc=True))
        esperado = pd.date_range(
            pd.Timestamp(fecha, tz="UTC") + pd.Timedelta(minutes=30), periods=24, freq="h"
        )
        if not tiempos.equals(esperado) or ds.attrs.get("aoi_id") != aoi_id:
            raise ValueError(f"{path.name}: tiempo/AOI inconsistente")
        for nombre in VARS_SALIDA:
            if ds[nombre].dims != ("time", "lat", "lon"):
                raise ValueError(f"{path.name}:{nombre} no es time/lat/lon")
            if not np.isfinite(np.asarray(ds[nombre].isel(time=[0, -1]))).any():
                raise ValueError(f"{path.name}:{nombre} sin valores finitos")


def _preparar_aoi(paths: dict[str, Path], salida: Path, aoi, fecha: str, hashes: dict) -> Path:
    import xarray as xr

    if salida.exists():
        _validar_stage(salida, fecha, aoi.id)
        return salida
    tmp = salida.with_suffix(salida.suffix + ".part")
    tmp.unlink(missing_ok=True)
    salida.parent.mkdir(parents=True, exist_ok=True)
    try:
        with (
            xr.open_dataset(paths["slv"]) as slv,
            xr.open_dataset(paths["flx"]) as flx,
            xr.open_dataset(paths["aer"]) as aer,
        ):
            t = _coord(slv, ("time", "valid_time"))
            y = _coord(slv, ("lat", "latitude"))
            x = _coord(slv, ("lon", "longitude"))
            lat = np.asarray(slv[y], dtype="float64")
            lon = (np.asarray(slv[x], dtype="float64") + 180.0) % 360.0 - 180.0
            oeste, sur, este, norte = aoi.bbox
            iy = np.flatnonzero(
                (lat >= sur - SPEC.resolucion_lat / 2)
                & (lat <= norte + SPEC.resolucion_lat / 2)
            )
            ix = np.flatnonzero(
                (lon >= oeste - SPEC.resolucion_lon / 2)
                & (lon <= este + SPEC.resolucion_lon / 2)
            )
            if not len(iy) or not len(ix):
                raise ValueError(f"AOI {aoi.id} fuera de la grilla")

            def tomar(ds, nombre):
                real = _resolver(ds, nombre)
                ty = _coord(ds, ("time", "valid_time"))
                yy = _coord(ds, ("lat", "latitude"))
                xx = _coord(ds, ("lon", "longitude"))
                da = ds[real].isel({yy: iy, xx: ix})
                extras = [d for d in da.dims if d not in (ty, yy, xx)]
                if any(da.sizes[d] != 1 for d in extras):
                    raise ValueError(f"{nombre}: dimensiones extra {extras}")
                arr = np.asarray(da.transpose(ty, *extras, yy, xx).values)
                for _ in extras:
                    arr = arr[:, 0, ...]
                return arr.astype("float32", copy=False), dict(ds[real].attrs)

            datos, attrs = {}, {}
            for nombre in VARS_SLV:
                datos[nombre], attrs[nombre] = tomar(slv, nombre)
            datos["PBLH"], attrs["PBLH"] = tomar(flx, "PBLH")
            datos["AOD_M2"], attrs["AOD_M2"] = tomar(aer, "TOTEXTTAU")
            masas = {v: tomar(aer, v)[0] for v in VARS_AER_MASA}
            t2m, qv, ps = datos["T2M"], datos["QV2M"], datos["PS"]
            es = 611.2 * np.exp(17.67 * (t2m - 273.15) / (t2m - 29.65))
            vapor = qv * ps / (0.622 + 0.378 * qv)
            datos["RH2M"] = np.clip(100.0 * vapor / es, 0.0, 110.0).astype("float32")
            attrs["RH2M"] = {"units": "%", "formula": "Tetens from QV2M,T2M,PS"}
            datos["PM25_M2"] = (
                (1.375 * masas["SO4SMASS"] + 1.6 * masas["OCSMASS"]
                 + masas["BCSMASS"] + masas["DUSMASS25"] + masas["SSSMASS25"])
                * 1e9
            ).astype("float32")
            attrs["PM25_M2"] = {
                "units": "ug m-3",
                "formula": "GMAO: (1.375*SO4 + 1.6*OC + BC + DU25 + SS25)*1e9",
            }
            out = xr.Dataset(
                {v: (("time", "lat", "lon"), datos[v]) for v in VARS_SALIDA},
                coords={"time": slv[t].values, "lat": lat[iy], "lon": lon[ix]},
                attrs={
                    "collections": json.dumps(COLECCIONES, sort_keys=True),
                    "version": VERSION,
                    "source_sha256": json.dumps(hashes, sort_keys=True),
                    "aoi_id": aoi.id,
                    "territorio": aoi.territorio,
                    "native_resolution": "0.5 x 0.625 degree",
                    "native_time": "hourly UTC at HH:30",
                    "spatial_operation": "temporary native-grid AOI; no resampling",
                },
            )
            for nombre, atr in attrs.items():
                out[nombre].attrs.update(atr)
            out.to_netcdf(
                tmp, engine="netcdf4", format="NETCDF4",
                encoding={v: {"zlib": True, "complevel": 4, "shuffle": True} for v in out.data_vars},
            )
        _validar_stage(tmp, fecha, aoi.id)
        with tmp.open("rb") as fh:
            os.fsync(fh.fileno())
        os.replace(tmp, salida)
        _validar_stage(salida, fecha, aoi.id)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return salida


def _preparar_dia(fecha: str, granulos: dict, mes_dir: Path, comunas: Path) -> tuple[list[Path], dict]:
    dia_dir = ensure_dir(mes_dir / fecha.replace("-", ""))
    aois = _aois(comunas)
    nombre_base = fecha.replace("-", "")
    salidas = [dia_dir / f"merra2_meteo_{nombre_base}.{a.id}.stage.nc" for a in aois]
    if all(p.exists() for p in salidas):
        for p, a in zip(salidas, aois, strict=True):
            _validar_stage(p, fecha, a.id)
        return salidas, {"fecha": fecha, "reanudado": True}
    global_dir = ensure_dir(mes_dir / "global")
    paths = {k: _descargar(granulos[k], global_dir) for k in COLECCIONES}
    hashes = {k: sha256_archivo(p) for k, p in paths.items()}
    bytes_fuente = {k: p.stat().st_size for k, p in paths.items()}
    for salida, aoi in zip(salidas, aois, strict=True):
        _preparar_aoi(paths, salida, aoi, fecha, hashes)
    for path in paths.values():
        path.unlink()
    return salidas, {
        "fecha": fecha,
        "granulos": {
            k: {
                "nombre": _nombre_granulo(granulos[k]),
                "url_publica": _url_granulo(granulos[k]),
                "bytes": bytes_fuente[k],
                "sha256": hashes[k],
            }
            for k in COLECCIONES
        },
    }


def procesar_mes(
    periodo: pd.Period,
    comunas: Path,
    *,
    permitir_parcial: bool,
    espacio_minimo: float,
    retirar_legado: bool,
    dry_run: bool,
) -> bool:
    if salida_vigente(SPEC, periodo, comunas, aceptar_parcial=False):
        log.info("%s ya validado", periodo)
        return True
    esperado = [x.strftime("%Y-%m-%d") for x in pd.date_range(periodo.start_time, periodo.end_time, freq="D")]
    legacy = _legacy(periodo)
    por_fecha_legacy = {_fecha_legacy(p): p for p in legacy}
    faltan = [f for f in esperado if f not in por_fecha_legacy]
    log.info("%s: %d dias legacy; %d por adquirir", periodo, len(legacy), len(faltan))
    if dry_run:
        return len(legacy) == len(esperado)
    fuentes_nuevas: list[Path] = []
    prov: list[dict] = []
    mes_dir = STAGING / periodo.strftime("%Y%m")
    if faltan:
        ensure_dir(mes_dir)
        busquedas = {k: _buscar(short, periodo) for k, short in COLECCIONES.items()}
        comunes = sorted(set.intersection(*(set(x) for x in busquedas.values())))
        disponibles = [f for f in comunes if f in faltan]
        if disponibles != faltan[: len(disponibles)]:
            raise RuntimeError(f"{periodo}: disponibilidad MERRA-2 no es continua")
        if len(disponibles) < len(faltan) and not permitir_parcial:
            raise RuntimeError(f"{periodo}: faltan {len(faltan)-len(disponibles)} dias")
        for fecha in disponibles:
            exigir_espacio(SPEC.salida, espacio_minimo)
            salidas, info = _preparar_dia(
                fecha, {k: busquedas[k][fecha] for k in COLECCIONES}, mes_dir, comunas
            )
            fuentes_nuevas.extend(salidas)
            prov.append(info)
    fuentes = legacy + fuentes_nuevas
    if not fuentes:
        log.info("%s sin fuentes disponibles", periodo)
        return False
    dias_fuente = sorted(set(por_fecha_legacy) | {p.parent.name[:4] + "-" + p.parent.name[4:6] + "-" + p.parent.name[6:8] for p in fuentes_nuevas})
    parcial = dias_fuente != esperado
    salida, manifest = normalizar_mes(
        SPEC, fuentes, periodo, comunas,
        permitir_parcial=parcial,
        espacio_minimo_gib=espacio_minimo,
    )
    meta = json.loads(manifest.read_text(encoding="utf-8"))
    meta["adquisicion"] = {
        "colecciones": COLECCIONES,
        "version": VERSION,
        "dias_descargados_en_esta_corrida": prov,
        "fuentes_legacy_reutilizadas": len(legacy),
        "descargador": str(Path(__file__).resolve()),
        "descargador_sha256": sha256_archivo(Path(__file__)),
        "estado_periodo": "parcial_pendiente" if parcial else "completo",
    }
    _json_atomico(manifest, meta)
    if not parcial and fuentes_nuevas:
        eliminar_fuentes_validadas(SPEC, fuentes_nuevas, periodo, salida, manifest)
        for d in sorted((p for p in mes_dir.iterdir() if p.is_dir()), reverse=True):
            _limpiar_directorios_vacios(d, STAGING)
        _limpiar_directorios_vacios(mes_dir, STAGING)
    if not parcial and retirar_legado and legacy:
        liberados = eliminar_fuentes_validadas(SPEC, legacy, periodo, salida, manifest)
        log.info("%s: rectangulos legacy retirados (%.3f GiB)", periodo, liberados / 1024**3)
    return not parcial


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--desde", default="2000-01-01")
    ap.add_argument("--hasta", default=date.today().isoformat())
    ap.add_argument("--comunas", type=Path, default=COMUNAS)
    ap.add_argument("--espacio-minimo-gb", type=float, default=100)
    ap.add_argument("--permitir-ultimo-mes-parcial", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--retirar-legado-validado", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    p0, p1 = pd.Period(a.desde[:7], "M"), pd.Period(a.hasta[:7], "M")
    if p1 < p0:
        ap.error("--hasta es anterior a --desde")
    periodos = list(pd.period_range(p0, p1, freq="M"))
    if not a.dry_run:
        exigir_espacio(SPEC.salida, a.espacio_minimo_gb)
        # Solo autentica si algun mes no esta cubierto enteramente por legado.
        if any(len(_legacy(p)) < p.days_in_month for p in periodos):
            login()
    for periodo in periodos:
        completo = procesar_mes(
            periodo,
            a.comunas,
            permitir_parcial=bool(a.permitir_ultimo_mes_parcial),
            espacio_minimo=a.espacio_minimo_gb,
            retirar_legado=a.retirar_legado_validado,
            dry_run=a.dry_run,
        )
        if not completo:
            log.info("Se detiene en el ultimo mes nativo disponible: %s", periodo)
            break


if __name__ == "__main__":
    main()
