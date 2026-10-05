#!/usr/bin/env python3
"""Puente de compatibilidad al extractor TROPOMI canónico.

El extractor mantenido vive en
``scripts_superficie/extractores/extraer_s5p_estacion.py``. Este archivo se
conserva para que los comandos históricos desde ``scripts_estacion`` no usen
el lector antiguo que promediaba y descartaba los identificadores nativos.

Uso histórico compatible::

    python extraer_s5p_estacion.py          # NO2
    python extraer_s5p_estacion.py NO2 SO2  # productos en secuencia
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PRODUCTOS = ("NO2", "SO2", "CO", "O3")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("productos", nargs="*", choices=PRODUCTOS,
                    help="NO2 por defecto; se pueden indicar varios")
    ap.add_argument("--radio", type=float)
    ap.add_argument("--qa", type=float)
    ap.add_argument("--procesos", type=int)
    ap.add_argument("--prueba", type=int)
    args = ap.parse_args()

    destino = (Path(__file__).resolve().parents[1] / "scripts_superficie" /
               "extractores" / "extraer_s5p_estacion.py")
    if not destino.exists():
        ap.error(f"no existe el extractor canónico: {destino}")

    comunes: list[str] = []
    for opcion, valor in (("--radio", args.radio), ("--qa", args.qa),
                          ("--procesos", args.procesos),
                          ("--prueba", args.prueba)):
        if valor is not None:
            comunes.extend((opcion, str(valor)))

    productos = args.productos or ["NO2"]
    for producto in productos:
        comando = [sys.executable, str(destino), "--producto", producto,
                   *comunes]
        resultado = subprocess.run(comando, check=False)
        if resultado.returncode:
            return resultado.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
