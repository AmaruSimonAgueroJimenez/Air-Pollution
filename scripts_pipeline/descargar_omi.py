#!/usr/bin/env python3
"""descargar_omi.py — Aura OMI (gases, L3 diario en grilla) vía NASA Earthdata.

Productos L3 diarios globales (grilla 0.25°), livianos, para NO2, O3 y SO2, a
data/contaminantes/OMI/<POL>/raw_chile/. OMI cubre 2004-10 en adelante
(registro largo, útil para el histórico de gases).

short_names/versiones verificados en CMR: OMNO2d v004 · OMTO3d v004 · OMSO2e v004.

Requiere credenciales NASA Earthdata.

Uso:
  python descargar_omi.py --contaminantes no2,o3,so2 --desde 2005-01-01 --hasta 2024-12-31
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import CONTAMINANTES, bbox_earthaccess, get_logger  # noqa: E402
from _env_earthdata import buscar_y_descargar, login  # noqa: E402

log = get_logger("omi")

SHORT = {"no2": "OMNO2d", "o3": "OMTO3d", "so2": "OMSO2e"}
VER = {"no2": "004", "o3": "004", "so2": "004"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--contaminantes", default="no2,o3,so2")
    ap.add_argument("--desde", default="2005-01-01")
    ap.add_argument("--hasta", default="2024-12-31")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    pols = [p.strip().lower() for p in args.contaminantes.split(",") if p.strip()]
    malos = [p for p in pols if p not in SHORT]
    if malos:
        ap.error(f"contaminantes inválidos: {malos}. Válidos: {list(SHORT)}")

    if not args.dry_run:
        login()
    bbox = bbox_earthaccess()
    for pol in pols:
        dest = CONTAMINANTES / "OMI" / pol.upper() / "raw_chile"
        log.info("=== OMI %s (%s v%s) ===", pol.upper(), SHORT[pol], VER[pol])
        buscar_y_descargar(SHORT[pol], bbox, args.desde, args.hasta, dest,
                           version=VER[pol], dry_run=args.dry_run)
    log.info("Listo OMI.")


if __name__ == "__main__":
    main()
