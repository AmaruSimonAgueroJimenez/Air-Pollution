#!/usr/bin/env python3
"""descargar_geoscf.py — NASA GEOS-CF (composición) vía OPeNDAP.

Subconjunto horario de concentraciones de SUPERFICIE para Chile de la colección
``aqc_tavg_1hr_g1440x721_v1``: O3, NO2, SO2, CO y PM2.5. Guarda un netCDF por mes
en  data/contaminantes/GEOS_CF/raw_chile/.

Público (sin credenciales). Requiere xarray + pydap/netCDF4.
GEOS-CF cubre 2018-01 en adelante.

Uso:
  python descargar_geoscf.py --desde 2019-01-01 --hasta 2024-12-31
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import CHILE_BBOX, CONTAMINANTES, ensure_dir, get_logger, retry  # noqa: E402

log = get_logger("geoscf")

DEST = CONTAMINANTES / "GEOS_CF" / "raw_chile"
# Servidor DODS del NCCS. Concentraciones de superficie (aqc).
BASE = "https://opendap.nccs.nasa.gov/dods/gmao/geos-cf/assim/aqc_tavg_1hr_g1440x721_v1"
# Nombres de variable candidatos (el servidor a veces las expone en minúscula).
VARS = {
    "o3": ["O3", "o3"],
    "no2": ["NO2", "no2"],
    "so2": ["SO2", "so2"],
    "co": ["CO", "co"],
    "pm25": ["PM25_RH35_GCC", "pm25_rh35_gcc"],
}


def abrir():
    try:
        import xarray as xr
    except ImportError as e:
        raise SystemExit("Falta 'xarray'. Instala: pip install xarray pydap netCDF4") from e
    log.info("Abriendo OPeNDAP %s …", BASE)
    return xr.open_dataset(BASE, engine="pydap")


def resolver_vars(ds):
    presentes = {}
    for pol, cands in VARS.items():
        for c in cands:
            if c in ds.variables:
                presentes[pol] = c
                break
    faltan = [p for p in VARS if p not in presentes]
    if faltan:
        log.warning("no encontré en el servidor: %s (revisa nombres de variable)", faltan)
    return presentes


@retry(n=3, base=5.0)
def bajar_mes(ds, cols, ini, fin, dry_run=False):
    """Baja un mes. Escribe a .tmp y solo renombra si el archivo trae datos.

    El servidor OPeNDAP corta la conexión a media descarga con frecuencia
    ("Response ended prematurely"). Sin el .tmp, el archivo truncado quedaba con
    el nombre final y el reintento lo daba por bueno vía `destino.exists()`,
    dejando 72 archivos vacíos de 239 bytes que se reportaron como éxito.
    """
    lon_min, lat_min, lon_max, lat_max = CHILE_BBOX
    destino = DEST / f"geoscf_{ini:%Y%m}.nc"
    if destino.exists():
        log.info("  ya existe %s", destino.name)
        return
    if dry_run:
        log.info("  [dry-run] %s vars=%s", destino.name, list(cols))
        return
    sub = (ds[list(cols.values())]
           .sel(time=slice(str(ini.date()), str(fin.date())))
           .sel(lat=slice(lat_min, lat_max), lon=slice(lon_min, lon_max)))
    ensure_dir(DEST)
    tmp = destino.with_suffix(".tmp")
    try:
        enc = {v: {"zlib": True, "complevel": 4} for v in cols.values()}
        sub.to_netcdf(tmp, encoding=enc)
        with xr_abrir(tmp) as chk:
            pasos = chk.sizes.get("time", 0)
            if pasos == 0 or not chk.data_vars:
                raise RuntimeError(
                    f"descarga vacía ({pasos} pasos, {len(chk.data_vars)} variables)")
    except BaseException:
        tmp.unlink(missing_ok=True)  # sin esto el reintento lo daría por hecho
        raise
    tmp.rename(destino)
    log.info("  ✓ %s (%d pasos de tiempo)", destino.name, pasos)


def xr_abrir(ruta):
    import xarray as xr
    return xr.open_dataset(ruta)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--desde", default="2019-01-01")
    ap.add_argument("--hasta", default="2024-12-31")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    meses = pd.date_range(args.desde, args.hasta, freq="MS")
    if args.dry_run:
        for ini in meses:
            fin = ini + pd.offsets.MonthEnd(1)
            log.info("  [dry-run] mes %s vars=%s", ini.strftime("%Y-%m"), list(VARS))
        return
    ds = abrir()
    cols = resolver_vars(ds)
    if not cols:
        raise SystemExit("No se resolvió ninguna variable en GEOS-CF; revisa BASE/VARS.")
    log.info("GEOS-CF %s–%s, variables=%s", args.desde, args.hasta, cols)
    fallidos = []
    for ini in meses:
        fin = ini + pd.offsets.MonthEnd(1)
        try:
            bajar_mes(ds, cols, ini, fin, dry_run=args.dry_run)
        except Exception as e:  # noqa: BLE001
            log.warning("  ✗ %s agotó los reintentos (%s)", ini.strftime("%Y-%m"),
                        str(e)[:120])
            fallidos.append(ini.strftime("%Y-%m"))
    if fallidos:
        # salir con error: que el runner reintente en vez de darlo por completo
        raise SystemExit(f"GEOS-CF incompleto: fallaron {len(fallidos)} meses "
                         f"({', '.join(fallidos[:6])}{' …' if len(fallidos) > 6 else ''}). "
                         f"Relanza para retomar los que falten.")
    log.info("Listo GEOS-CF (%d meses).", len(meses))


if __name__ == "__main__":
    main()
