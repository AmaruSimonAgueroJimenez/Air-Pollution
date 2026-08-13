#!/usr/bin/env python3
"""descargar_acag_pm25.py — ACAG SatPM2.5 (superficie) desde el S3 público.

Descarga la PM2.5 de superficie derivada por satélite del Atmospheric
Composition Analysis Group (WUSTL), versión V6GL03 (producto CNNPM25),
desde el bucket público de AWS  s3://satpmdata/  (us-east-1, acceso
anónimo, sin costo), a  data/contaminantes/ACAG_V6GL03/raw_chile/.

El bucket dejó de servir V6.GL.02.04; la estructura vigente es
V6GL03/{FineResolution,CoarseResolution}/<REGION>/{Annual,Monthly}/ y por
defecto se acota a FineResolution/SA (Sudamérica, incluye Chile).

Sin credenciales AWS (usa firma anónima). Requiere boto3.

Uso:
  python descargar_acag_pm25.py --listar                 # explora el bucket
  python descargar_acag_pm25.py --temporal annual        # baja los anuales V6GL03
  python descargar_acag_pm25.py --temporal monthly --prefijo <prefijo>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import CONTAMINANTES, ensure_dir, get_logger  # noqa: E402

log = get_logger("acag")

BUCKET = "satpmdata"
REGION = "us-east-1"
VERSION_TOKEN = "V6GL03"
PREFIJO_DEFECTO = "V6GL03/FineResolution/SA/"
DEST = CONTAMINANTES / "ACAG_V6GL03" / "raw_chile"


def cliente():
    try:
        import boto3
        from botocore import UNSIGNED
        from botocore.config import Config
    except ImportError as e:
        raise SystemExit("Falta 'boto3'. Instala: pip install boto3") from e
    return boto3.client("s3", region_name=REGION,
                        config=Config(signature_version=UNSIGNED))


def listar_llaves(s3, prefijo=""):
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefijo):
        for obj in page.get("Contents", []):
            yield obj["Key"], obj["Size"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--temporal", default="annual",
                    choices=["annual", "monthly", "todo"])
    ap.add_argument("--prefijo", default=PREFIJO_DEFECTO,
                    help="prefijo S3 para acotar la búsqueda (por defecto Sudamérica "
                         "en resolución fina; usa '' para el bucket completo)")
    ap.add_argument("--listar", action="store_true",
                    help="solo listar las primeras llaves y salir")
    ap.add_argument("--max-listar", type=int, default=40)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    s3 = cliente()

    if args.listar:
        log.info("Primeras %d llaves de s3://%s/%s :", args.max_listar, BUCKET, args.prefijo)
        for i, (k, sz) in enumerate(listar_llaves(s3, args.prefijo)):
            log.info("  %s  (%d MB)", k, sz // (1024 * 1024))
            if i + 1 >= args.max_listar:
                log.info("  … (usa --prefijo para acotar)")
                break
        return

    quiere_mensual = args.temporal in ("monthly", "todo")
    quiere_anual = args.temporal in ("annual", "todo")

    def coincide(key: str) -> bool:
        kl = key.lower()
        if VERSION_TOKEN.lower() not in kl or not kl.endswith(".nc"):
            return False
        if Path(key).name.startswith("._"):  # basura AppleDouble presente en el bucket
            return False
        if args.temporal == "todo":
            return True
        if quiere_anual and "annual" in kl:
            return True
        if quiere_mensual and "monthly" in kl:
            return True
        return False

    ensure_dir(DEST)
    n = 0
    for key, sz in listar_llaves(s3, args.prefijo):
        if not coincide(key):
            continue
        destino = DEST / Path(key).name
        if destino.exists():
            log.info("  ya existe %s", destino.name)
            continue
        if args.dry_run:
            log.info("  [dry-run] bajaría %s (%d MB)", key, sz // (1024 * 1024))
            n += 1
            continue
        log.info("  ↓ %s (%d MB)", key, sz // (1024 * 1024))
        s3.download_file(BUCKET, key, str(destino))
        n += 1
    if n == 0:
        log.warning("No se encontraron llaves que coincidan. Corre con --listar "
                    "(o ajusta --prefijo / --temporal) para inspeccionar el bucket.")
    else:
        log.info("Listo ACAG: %d archivos.", n)


if __name__ == "__main__":
    main()
