#!/usr/bin/env python3
"""descargar_merra2_aer.py — MERRA-2 aerosoles (insumo de PM) vía NASA Earthdata.

Descarga la colección de diagnóstico de aerosoles M2T1NXAER (horaria; incluye
AOD y componentes de polvo/sal marina/sulfato/carbono útiles para PM2.5/PM10)
y la RECORTA a Chile al vuelo: cada gránulo global (~470 MB) se baja a
_tmp_global/, se recorta a CHILE_BBOX (~3 MB) hacia raw_chile/ y el global se
borra de inmediato. Los 6 años completos ocupan ~6 GB en disco en vez del
~1 TB de los gránulos globales.

Si quedan gránulos globales de una corrida anterior (en raw_chile/ o
_tmp_global/), primero los recorta y los elimina; los truncados/corruptos se
borran y se vuelven a descargar. Es seguro relanzarlo: salta lo ya recortado.

Requiere credenciales NASA Earthdata. Cubre 1980 en adelante.

Uso:
  python descargar_merra2_aer.py --desde 2019-01-01 --hasta 2024-12-31
  python descargar_merra2_aer.py --coleccion M2TMNXAER   # variante mensual
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import CHILE_BBOX, CONTAMINANTES, ensure_dir, get_logger  # noqa: E402
from _env_earthdata import limite_bytes_s, login  # noqa: E402

log = get_logger("merra2_aer")

BASE = CONTAMINANTES / "M2TMNXAER.5.12.4"
DEST = BASE / "raw_chile"
TMP = BASE / "_tmp_global"
LOTE = 24  # gránulos por tanda (~11 GB de tránsito máximo en _tmp_global)


def nombre_recortado(nombre_global: str) -> str:
    return nombre_global.removesuffix(".nc4") + ".chile.nc4"


def recortar(src: Path) -> Path:
    """Recorta un gránulo global a CHILE_BBOX y lo guarda en DEST."""
    import xarray as xr
    lon_min, lat_min, lon_max, lat_max = CHILE_BBOX
    out = DEST / nombre_recortado(src.name)
    tmp_out = out.with_suffix(".tmp")
    try:
        with xr.open_dataset(src) as ds:
            sub = ds.sel(lat=slice(lat_min, lat_max), lon=slice(lon_min, lon_max))
            sub.to_netcdf(tmp_out)
        tmp_out.rename(out)
    except Exception:
        tmp_out.unlink(missing_ok=True)
        raise
    return out


def recortar_pendientes() -> None:
    """Procesa gránulos globales huérfanos de corridas anteriores."""
    globales = sorted(list(DEST.glob("MERRA2_*.nc4")) + list(TMP.glob("MERRA2_*.nc4")))
    globales = [f for f in globales if ".chile." not in f.name]
    if not globales:
        return
    log.info("Recortando %d gránulos globales de corridas anteriores ...", len(globales))
    for k, f in enumerate(globales, 1):
        try:
            recortar(f)
        except Exception as e:  # truncado/corrupto: se re-descargará
            log.warning("  gránulo ilegible %s (%s); lo borro para re-descargar", f.name, e)
        f.unlink(missing_ok=True)
        if k % 25 == 0:
            log.info("  ... %d/%d recortados", k, len(globales))
    log.info("Recorte de pendientes listo (%d).", len(globales))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--coleccion", default="M2T1NXAER",
                    help="M2T1NXAER (horario) o M2TMNXAER (mensual)")
    ap.add_argument("--version", default="5.12.4")
    ap.add_argument("--desde", default="2019-01-01")
    ap.add_argument("--hasta", default="2024-12-31")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    log.info("=== MERRA-2 aerosoles (%s v%s) — recorte a Chile al vuelo ===",
             args.coleccion, args.version)
    ensure_dir(DEST)
    ensure_dir(TMP)

    if not args.dry_run:
        login()
    import earthaccess

    kwargs = dict(short_name=args.coleccion, bounding_box=tuple(CHILE_BBOX),
                  temporal=(args.desde, args.hasta), version=args.version)
    results = earthaccess.search_data(**kwargs)
    log.info("%d gránulos en CMR", len(results))
    if args.dry_run:
        return

    recortar_pendientes()

    hechos = {p.name for p in DEST.glob("*.chile.nc4")}
    pendientes = []
    for g in results:
        try:
            nombre = g.data_links()[0].rsplit("/", 1)[-1]
        except Exception:
            pendientes.append(g)
            continue
        if nombre_recortado(nombre) not in hechos:
            pendientes.append(g)
    log.info("%d por descargar (%d ya recortados)", len(pendientes), len(hechos))

    import os
    import time
    limite = limite_bytes_s()
    paso = LOTE
    if limite:
        log.info("Límite de descarga activo: %.0f Mbps (promedio)", limite * 8 / 1e6)
        paso = 2  # lotes chicos para que las ráfagas sean cortas
    for i in range(0, len(pendientes), paso):
        lote = pendientes[i:i + paso]
        t0 = time.monotonic()
        archivos = [f for f in earthaccess.download(lote, str(TMP)) if f]
        n_bytes = sum(os.path.getsize(f) for f in archivos if os.path.exists(f))
        for f in archivos:
            f = Path(f)
            try:
                recortar(f)
            except Exception as e:
                log.warning("  fallo recortando %s (%s); quedará para el reintento", f.name, e)
            f.unlink(missing_ok=True)
        if limite:
            espera = n_bytes / limite - (time.monotonic() - t0)
            if espera > 0:
                time.sleep(espera)
        log.info("... %d/%d gránulos procesados", min(i + paso, len(pendientes)),
                 len(pendientes))

    n = len(list(DEST.glob("*.chile.nc4")))
    log.info("Listo MERRA-2 aerosoles: %d archivos recortados en %s", n, DEST)


if __name__ == "__main__":
    main()
