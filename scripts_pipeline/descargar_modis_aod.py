#!/usr/bin/env python3
"""descargar_modis_aod.py — MODIS AOD 3 km (MOD04_3K/MYD04_3K) vía NASA Earthdata.

AOD complementario (Dark Target 3 km) de Terra (MOD) y Aqua (MYD), predictor de
PM, a  data/contaminantes/MODIS_AOD_3K/_tmp_global/. Versión CMR: 6.1.

Requiere credenciales NASA Earthdata.

Uso:
  python descargar_modis_aod.py --desde 2019-01-01 --hasta 2024-12-31
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import CONTAMINANTES, bbox_earthaccess, get_logger  # noqa: E402
from _env_earthdata import buscar_y_descargar, login  # noqa: E402

log = get_logger("modis_aod")

# raw_chile, NO _tmp_global: los swaths MOD04/MYD04_3K ya vienen acotados por
# la búsqueda en CMR, así que lo que se descarga es el producto final. Guardarlo
# en un directorio llamado "_tmp_global" invita a que una limpieza de temporales
# lo borre (ya pasó una vez).
DEST = CONTAMINANTES / "MODIS_AOD_3K" / "raw_chile"
PRODUCTOS = {"terra": "MOD04_3K", "aqua": "MYD04_3K"}
VERSION = "6.1"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sensor", default="terra,aqua", help="terra, aqua o ambos (coma)")
    ap.add_argument("--desde", default="2019-01-01")
    ap.add_argument("--hasta", default="2024-12-31")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    sensores = [s.strip().lower() for s in args.sensor.split(",") if s.strip()]
    malos = [s for s in sensores if s not in PRODUCTOS]
    if malos:
        ap.error(f"sensores inválidos: {malos}. Válidos: {list(PRODUCTOS)}")

    if not args.dry_run:
        login()
    for s in sensores:
        short = PRODUCTOS[s]
        log.info("=== MODIS AOD 3K %s (%s v%s) ===", s, short, VERSION)
        buscar_y_descargar(short, bbox_earthaccess(), args.desde, args.hasta,
                           DEST, version=VERSION, dry_run=args.dry_run)
    log.info("Listo MODIS AOD 3K.")


if __name__ == "__main__":
    main()
