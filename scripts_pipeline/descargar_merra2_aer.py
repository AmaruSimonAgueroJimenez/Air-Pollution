#!/usr/bin/env python3
"""Descarga MERRA-2 M2T1NXAER horario y publica solo Chile nativo.

Contrato reproducible
---------------------
* rango predeterminado: 2000-01 hasta la ultima fecha pedida/disponible;
* producto nativo M2T1NXAER v5.12.4, 0,5 x 0,625 grados, 24 marcas
  horarias diarias a HH:30 UTC;
* conserva AOD 550 nm (TOTEXTTAU) y PM2.5 superficial derivado de las cinco
  masas necesarias mediante la formula GMAO; no conserva las otras decenas de
  variables si no alimentan el analisis;
* AOIs derivadas de ``comunas.shp``: continente, Juan Fernandez,
  Desventuradas, Rapa Nui y Sala y Gomez, sin Antartica;
* el global se elimina solo despues de validar los cinco recortes transitorios;
  estos se eliminan solo despues de publicar/reabrir el mes compacto y
  comprobar su hash. Un ultimo mes parcial queda explicitamente pendiente;
* la salida final usa el catalogo nativo y la relacion muchos-a-muchos a
  comuna de ``normalizar_reanalisis_chile.py``; no hay corredor oceanico,
  remuestreo, interpolacion ni promedio comunal.

Es reanudable. No inicie una segunda instancia sobre la misma salida.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import re
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ensure_dir, get_logger  # noqa: E402
from _env_earthdata import limite_bytes_s, login  # noqa: E402
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


log = get_logger("merra2_aer")
SPEC = PRODUCTOS["merra2_aer"]
COLECCION = "M2T1NXAER"
VERSION = "5.12.4"
STAGING = SPEC.salida / "_staging_descarga"
VARIABLES_MASA = ("SO4SMASS", "OCSMASS", "BCSMASS", "DUSMASS25", "SSSMASS25")
PATRON_FECHA = re.compile(r"\.(\d{8})\.")


def _aois(comunas: Path):
    from _chile_aoi import derivar

    return derivar(comunas, margen=0.0)


def _coord(ds, nombres):
    for nombre in nombres:
        if nombre in ds.coords or nombre in ds.dims:
            return nombre
    raise ValueError(f"falta coordenada {nombres}")


def _resolver(ds, nombre: str) -> str:
    por_lower = {str(v).lower(): str(v) for v in ds.data_vars}
    real = por_lower.get(nombre.lower())
    if real is None:
        raise ValueError(f"M2T1NXAER no contiene {nombre}")
    return real


def _validar_stage(path: Path, fecha: str, aoi_id: str) -> None:
    import xarray as xr

    with xr.open_dataset(path) as ds:
        if set(("AOD_M2", "PM25_M2")) - set(ds.data_vars):
            raise ValueError(f"{path.name}: faltan AOD_M2/PM25_M2")
        if not {"time", "lat", "lon"}.issubset(ds.coords):
            raise ValueError(f"{path.name}: faltan coordenadas time/lat/lon")
        tiempos = pd.DatetimeIndex(pd.to_datetime(ds.time.values, utc=True))
        esperado = pd.date_range(
            pd.Timestamp(fecha, tz="UTC") + pd.Timedelta(minutes=30),
            periods=24,
            freq="h",
        )
        if not tiempos.equals(esperado):
            raise ValueError(f"{path.name}: no conserva las 24 horas HH:30")
        if not len(ds.lat) or not len(ds.lon):
            raise ValueError(f"{path.name}: AOI vacia")
        if ds.attrs.get("aoi_id") != aoi_id:
            raise ValueError(f"{path.name}: aoi_id inconsistente")
        for nombre in ("AOD_M2", "PM25_M2"):
            if ds[nombre].dims != ("time", "lat", "lon"):
                raise ValueError(f"{path.name}:{nombre} no es time/lat/lon")
            muestra = np.asarray(ds[nombre].isel(time=[0, -1]))
            if not np.isfinite(muestra).any():
                raise ValueError(f"{path.name}:{nombre} sin valores finitos")


def _recortar_aoi(global_nc: Path, salida: Path, aoi, fecha: str, source_sha: str) -> Path:
    """Genera un AOI pequeno con solo AOD y las masas ya combinadas."""
    import xarray as xr

    if salida.exists():
        _validar_stage(salida, fecha, aoi.id)
        return salida
    salida.parent.mkdir(parents=True, exist_ok=True)
    tmp = salida.with_suffix(salida.suffix + ".part")
    tmp.unlink(missing_ok=True)
    try:
        with xr.open_dataset(global_nc) as ds:
            t = _coord(ds, ("time", "valid_time"))
            y = _coord(ds, ("lat", "latitude"))
            x = _coord(ds, ("lon", "longitude"))
            aod = _resolver(ds, "TOTEXTTAU")
            masas = {v: _resolver(ds, v) for v in VARIABLES_MASA}
            lat = np.asarray(ds[y], dtype="float64")
            lon_raw = np.asarray(ds[x], dtype="float64")
            lon = (lon_raw + 180.0) % 360.0 - 180.0
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
                raise ValueError(f"la grilla MERRA-2 no cruza AOI {aoi.id}")

            def tomar(nombre):
                da = ds[nombre].isel({y: iy, x: ix})
                extras = [d for d in da.dims if d not in (t, y, x)]
                if any(da.sizes[d] != 1 for d in extras):
                    raise ValueError(f"{nombre}: dimensiones extra no unitarias {extras}")
                da = da.transpose(t, *extras, y, x)
                arr = np.asarray(da.values)
                for _ in extras:
                    arr = arr[:, 0, ...]
                return arr.astype("float32", copy=False)

            so4, oc, bc, du, ss = (tomar(masas[v]) for v in VARIABLES_MASA)
            pm25 = (1.375 * so4 + 1.6 * oc + bc + du + ss) * 1e9
            out = xr.Dataset(
                data_vars={
                    "AOD_M2": (("time", "lat", "lon"), tomar(aod)),
                    "PM25_M2": (("time", "lat", "lon"), pm25.astype("float32")),
                },
                coords={
                    "time": np.asarray(ds[t].values),
                    "lat": lat[iy],
                    "lon": lon[ix],
                },
                attrs={
                    "product": f"{COLECCION} {VERSION}",
                    "source_granule": global_nc.name,
                    "source_sha256": source_sha,
                    "aoi_id": aoi.id,
                    "territorio": aoi.territorio,
                    "native_resolution": "0.5 x 0.625 degree",
                    "native_time": "hourly UTC at HH:30",
                    "spatial_operation": "temporary native-grid AOI; no resampling",
                    "pm25_formula": (
                        "(1.375*SO4SMASS + 1.6*OCSMASS + BCSMASS + "
                        "DUSMASS25 + SSSMASS25)*1e9"
                    ),
                },
            )
            out.AOD_M2.attrs.update(ds[aod].attrs)
            out.PM25_M2.attrs.update(
                units="ug m-3",
                long_name="Surface PM2.5 from MERRA-2 aerosol mass (GMAO formula)",
            )
            enc = {
                v: {"zlib": True, "complevel": 4, "shuffle": True}
                for v in out.data_vars
            }
            out.to_netcdf(tmp, engine="netcdf4", format="NETCDF4", encoding=enc)
        _validar_stage(tmp, fecha, aoi.id)
        with tmp.open("rb") as fh:
            os.fsync(fh.fileno())
        os.replace(tmp, salida)
        _validar_stage(salida, fecha, aoi.id)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return salida


def _nombre_granulo(g) -> str:
    try:
        return g.data_links()[0].split("?", 1)[0].rsplit("/", 1)[-1]
    except Exception as exc:
        raise ValueError(f"CMR no entrego nombre de granulo: {g}") from exc


def _url_granulo(g) -> str | None:
    try:
        return g.data_links()[0].split("?", 1)[0]
    except Exception:
        return None


def _fecha_nombre(nombre: str) -> str:
    m = PATRON_FECHA.search(nombre)
    if not m:
        raise ValueError(f"nombre MERRA-2 sin fecha: {nombre}")
    return pd.Timestamp(m.group(1)).strftime("%Y-%m-%d")


def _buscar_mes(periodo: pd.Period):
    import earthaccess

    ini = periodo.start_time.strftime("%Y-%m-%d")
    fin = periodo.end_time.strftime("%Y-%m-%dT23:59:59")
    resultados = earthaccess.search_data(
        short_name=COLECCION, version=VERSION, temporal=(ini, fin)
    )
    por_fecha = {}
    for g in resultados:
        nombre = _nombre_granulo(g)
        fecha = _fecha_nombre(nombre)
        if fecha in por_fecha and _nombre_granulo(por_fecha[fecha]) != nombre:
            raise ValueError(f"CMR devolvio dos granulos para {fecha}")
        por_fecha[fecha] = g
    return [por_fecha[k] for k in sorted(por_fecha)]


def _descargar_uno(g, carpeta: Path) -> Path:
    import earthaccess

    nombre = _nombre_granulo(g)
    existente = carpeta / nombre
    if existente.exists():
        import xarray as xr

        with xr.open_dataset(existente) as ds:
            _resolver(ds, "TOTEXTTAU")
        return existente
    archivos = [Path(p) for p in earthaccess.download([g], str(carpeta)) if p]
    if not archivos:
        raise RuntimeError(f"earthaccess no devolvio archivo para {nombre}")
    candidatos = [p for p in archivos if p.name == nombre] or archivos
    return candidatos[0]


def _proveniencia(path: Path, periodo: pd.Period) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "schema_version": 1,
        "producto": COLECCION,
        "version": VERSION,
        "periodo": str(periodo),
        "granulos": {},
    }


def _limpiar_directorios_vacios(path: Path, limite: Path) -> None:
    actual = path
    while actual != limite and limite in actual.parents:
        try:
            actual.rmdir()
        except OSError:
            break
        actual = actual.parent


def procesar_mes(
    periodo: pd.Period,
    comunas: Path,
    *,
    permitir_parcial: bool,
    espacio_minimo: float,
    dry_run: bool = False,
) -> bool:
    if salida_vigente(SPEC, periodo, comunas, aceptar_parcial=False):
        log.info("%s ya esta validado", periodo)
        return True
    resultados = _buscar_mes(periodo)
    fechas = [_fecha_nombre(_nombre_granulo(g)) for g in resultados]
    esperado = [x.strftime("%Y-%m-%d") for x in pd.date_range(periodo.start_time, periodo.end_time, freq="D")]
    es_prefijo = fechas == esperado[: len(fechas)]
    completo = fechas == esperado
    if not resultados:
        log.info("%s sin granulos publicados; queda pendiente", periodo)
        return False
    if not completo and not (permitir_parcial and es_prefijo):
        raise RuntimeError(
            f"{periodo}: CMR entrega {len(fechas)}/{len(esperado)} dias y no es un "
            "ultimo mes parcial continuo"
        )
    log.info(
        "%s: %d granulos (%s)", periodo, len(resultados),
        "completo" if completo else "PARCIAL explicito",
    )
    if dry_run:
        return completo
    mes_dir = ensure_dir(STAGING / periodo.strftime("%Y%m"))
    prov_path = mes_dir / "proveniencia_global.json"
    prov = _proveniencia(prov_path, periodo)
    aois = _aois(comunas)
    limite = limite_bytes_s()
    for k, g in enumerate(resultados, 1):
        exigir_espacio(SPEC.salida, espacio_minimo)
        nombre, fecha = _nombre_granulo(g), _fecha_nombre(_nombre_granulo(g))
        dia_dir = ensure_dir(mes_dir / fecha.replace("-", ""))
        salidas = [dia_dir / f"{Path(nombre).stem}.{a.id}.stage.nc" for a in aois]
        if all(p.exists() for p in salidas):
            for p, a in zip(salidas, aois, strict=True):
                _validar_stage(p, fecha, a.id)
            log.info("  %s ya preparado", fecha)
            continue
        t0 = time.monotonic()
        global_dir = ensure_dir(mes_dir / "global")
        global_nc = _descargar_uno(g, global_dir)
        bytes_global = global_nc.stat().st_size
        global_sha = sha256_archivo(global_nc)
        for salida, aoi in zip(salidas, aois, strict=True):
            _recortar_aoi(global_nc, salida, aoi, fecha, global_sha)
        global_nc.unlink()
        prov["granulos"][nombre] = {
            "fecha": fecha,
            "url_publica": _url_granulo(g),
            "bytes_global": bytes_global,
            "sha256_global": global_sha,
            "aois": [
                {"id": a.id, "archivo": p.name, "sha256": sha256_archivo(p)}
                for p, a in zip(salidas, aois, strict=True)
            ],
        }
        _json_atomico(prov_path, prov)
        if limite:
            espera = bytes_global / limite - (time.monotonic() - t0)
            if espera > 0:
                time.sleep(espera)
        log.info("  %s preparado (%d/%d)", fecha, k, len(resultados))

    fuentes = sorted(mes_dir.glob("????????/*.stage.nc"))
    esperado_stage = len(resultados) * len(aois)
    if len(fuentes) != esperado_stage:
        raise RuntimeError(f"{periodo}: staging incompleto {len(fuentes)}/{esperado_stage}")
    salida, manifest = normalizar_mes(
        SPEC, fuentes, periodo, comunas,
        permitir_parcial=not completo,
        espacio_minimo_gib=espacio_minimo,
    )
    meta = json.loads(manifest.read_text(encoding="utf-8"))
    meta["adquisicion"] = {
        "coleccion": COLECCION,
        "version": VERSION,
        "granulos_globales": list(prov["granulos"].values()),
        "descargador": str(Path(__file__).resolve()),
        "descargador_sha256": sha256_archivo(Path(__file__)),
        "estado_periodo": "completo" if completo else "parcial_pendiente",
    }
    _json_atomico(manifest, meta)
    if completo:
        liberados = eliminar_fuentes_validadas(SPEC, fuentes, periodo, salida, manifest)
        prov_path.unlink(missing_ok=True)
        for d in sorted((p for p in mes_dir.iterdir() if p.is_dir()), reverse=True):
            _limpiar_directorios_vacios(d, STAGING)
        _limpiar_directorios_vacios(mes_dir, STAGING)
        log.info("%s validado; staging retirado (%.3f GiB)", periodo, liberados / 1024**3)
    else:
        log.info("%s publicado como parcial; staging conservado para completarlo", periodo)
    return completo


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--desde", default="2000-01-01")
    ap.add_argument("--hasta", default=date.today().isoformat())
    ap.add_argument("--comunas", type=Path, default=COMUNAS)
    ap.add_argument("--espacio-minimo-gb", type=float, default=100)
    ap.add_argument(
        "--permitir-ultimo-mes-parcial", action=argparse.BooleanOptionalAction,
        default=True,
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    desde, hasta = pd.Period(args.desde[:7], "M"), pd.Period(args.hasta[:7], "M")
    if hasta < desde:
        ap.error("--hasta es anterior a --desde")
    periodos = list(pd.period_range(desde, hasta, freq="M"))
    if not args.dry_run:
        exigir_espacio(SPEC.salida, args.espacio_minimo_gb)
        login()
    for periodo in periodos:
        completo = procesar_mes(
            periodo,
            args.comunas,
            permitir_parcial=bool(args.permitir_ultimo_mes_parcial),
            espacio_minimo=args.espacio_minimo_gb,
            dry_run=args.dry_run,
        )
        if not completo:
            log.info("Se detiene en el ultimo mes nativo disponible: %s", periodo)
            break
    log.info("MERRA-2 AER terminado/reanudable")


if __name__ == "__main__":
    main()
