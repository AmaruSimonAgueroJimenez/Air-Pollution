#!/usr/bin/env python3
"""Compatibilidad: ejecuta el extractor canonico MOPITT L2 retrieval/pasada."""
from pathlib import Path
import runpy
import sys

DESTINO = (Path(__file__).resolve().parents[1] / "scripts_superficie" /
           "extractores" / "extraer_mopitt_estacion.py")
sys.path.insert(0, str(DESTINO.parent))
runpy.run_path(str(DESTINO), run_name="__main__")
