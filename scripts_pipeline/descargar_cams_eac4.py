#!/usr/bin/env python3
"""descargar_cams_eac4.py — CAMS reanálisis global EAC4 (multi-gas) vía ADS.

Descarga, recortado al área de Chile y por año, en netCDF:
  * PM2.5 y PM10            (variables de nivel único)
  * CO, NO2, O3, SO2        (nivel de modelo 60 ≈ superficie)
a  data/contaminantes/CAMS_EAC4/raw_chile/.

Requiere ADSAPI_URL / ADSAPI_KEY en ../.env
(regístrate en https://ads.atmosphere.copernicus.eu/ y copia tu API key).

Uso:
  python descargar_cams_eac4.py --desde 2019-01-01 --hasta 2024-12-31
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (CONTAMINANTES, bbox_area_cds, ensure_dir, get_logger,  # noqa: E402
                     require_env, retry)

log = get_logger("cams_eac4")

DATASET = "cams-global-reanalysis-eac4"
DEST = CONTAMINANTES / "CAMS_EAC4" / "raw_chile"
HORAS = ["00:00", "03:00", "06:00", "09:00", "12:00", "15:00", "18:00", "21:00"]
VARS_PM = ["particulate_matter_2.5um", "particulate_matter_10um"]
VARS_GAS = ["carbon_monoxide", "nitrogen_dioxide", "ozone", "sulphur_dioxide"]
NIVEL_SUPERFICIE = "60"   # EAC4 tiene 60 niveles; el 60 es el más cercano a superficie


def cliente():
    require_env("ADSAPI_URL", "ADSAPI_KEY")
    try:
        import cdsapi
    except ImportError as e:
        raise SystemExit("Falta 'cdsapi'. Instala: pip install cdsapi") from e
    return cdsapi.Client(url=os.environ["ADSAPI_URL"], key=os.environ["ADSAPI_KEY"])


@retry(n=3, base=5.0)
def _retrieve(c, req, destino: Path):
    c.retrieve(DATASET, req, str(destino))


def bajar_anio(c, anio: int, area, dry_run=False):
    ensure_dir(DEST)
    fecha = f"{anio}-01-01/{anio}-12-31"
    base = dict(date=fecha, time=HORAS, area=area, data_format="netcdf")
    trabajos = [
        ("pm", {**base, "variable": VARS_PM}),
        ("gas", {**base, "variable": VARS_GAS, "model_level": NIVEL_SUPERFICIE}),
    ]
    for etiqueta, req in trabajos:
        destino = DEST / f"cams_eac4_{etiqueta}_{anio}.nc"
        if destino.exists():
            log.info("  ya existe %s", destino.name)
            continue
        if dry_run:
            log.info("  [dry-run] %s <- %s", destino.name, {k: req[k] for k in ("variable",)})
            continue
        log.info("  solicitando %s %d (%s)…", etiqueta, anio, req["variable"])
        _retrieve(c, req, destino)
        log.info("  ✓ %s", destino)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--desde", default="2019-01-01")
    ap.add_argument("--hasta", default="2024-12-31")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    a0 = int(args.desde[:4])
    a1 = int(args.hasta[:4])
    area = bbox_area_cds()
    c = None if args.dry_run else cliente()
    log.info("CAMS EAC4 %d–%d, área Chile=%s", a0, a1, area)
    for anio in range(a0, a1 + 1):
        bajar_anio(c, anio, area, dry_run=args.dry_run)
    log.info("Listo CAMS EAC4.")


if __name__ == "__main__":
    main()
