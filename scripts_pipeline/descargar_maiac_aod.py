#!/usr/bin/env python3
"""descargar_maiac_aod.py — MODIS MAIAC MCD19A2 (AOD 1 km) vía NASA Earthdata.

Descarga gránulos L2 de AOD MAIAC (MCD19A2 v061), principal predictor de PM2.5,
a  data/contaminantes/MCD19A2.061/_tmp_global/.

Requiere credenciales NASA Earthdata.

Uso:
  python descargar_maiac_aod.py --desde 2019-01-01 --hasta 2024-12-31
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import CONTAMINANTES, bbox_earthaccess, get_logger  # noqa: E402
from _env_earthdata import buscar_y_descargar, login  # noqa: E402

log = get_logger("maiac")

# raw_chile, NO _tmp_global: los mosaicos MCD19A2 ya vienen acotados a tiles
# regionales, así que lo que se descarga es el producto final. Guardarlo en un
# directorio llamado "_tmp_global" invita a que una limpieza de temporales lo
# borre (ya pasó una vez).
DEST = CONTAMINANTES / "MCD19A2.061" / "raw_chile"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--desde", default="2019-01-01")
    ap.add_argument("--hasta", default="2024-12-31")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if not args.dry_run:
        login()
    log.info("=== MODIS MAIAC AOD (MCD19A2 v061) ===")
    buscar_y_descargar("MCD19A2", bbox_earthaccess(), args.desde, args.hasta,
                       DEST, version="061", dry_run=args.dry_run)
    log.info("Listo MAIAC AOD.")


if __name__ == "__main__":
    main()
