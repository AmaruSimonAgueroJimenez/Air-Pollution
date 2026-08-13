#!/usr/bin/env python3
"""descargar_mopitt.py — Terra MOPITT (CO, L3 diario) vía NASA Earthdata.

MOP03J (CO en grilla, L3 diario global, recuperación conjunta TIR+NIR) a
data/contaminantes/MOPITT_CO/raw_chile/. MOPITT cubre 2000-03 en adelante
(el registro de CO más largo). Versiones en CMR: v9 y v10 (usa --version).

Requiere credenciales NASA Earthdata.

Uso:
  python descargar_mopitt.py --desde 2005-01-01 --hasta 2024-12-31
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import CONTAMINANTES, bbox_earthaccess, get_logger  # noqa: E402
from _env_earthdata import buscar_y_descargar, login  # noqa: E402

log = get_logger("mopitt")

SHORT = "MOP03J"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", default="10",
                    help="9 o 10 (version_id de CMR; '010' no existe)")
    ap.add_argument("--desde", default="2005-01-01")
    ap.add_argument("--hasta", default="2024-12-31")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if not args.dry_run:
        login()
    dest = CONTAMINANTES / "MOPITT_CO" / "raw_chile"
    log.info("=== MOPITT CO (%s v%s) ===", SHORT, args.version)
    buscar_y_descargar(SHORT, bbox_earthaccess(), args.desde, args.hasta, dest,
                       version=args.version, dry_run=args.dry_run)
    log.info("Listo MOPITT.")


if __name__ == "__main__":
    main()
