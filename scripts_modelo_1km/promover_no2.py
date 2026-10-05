"""Promueve el NO₂ de una etiqueta a definitivo, respaldando lo anterior con fecha.

Mueve (no copia) superficies, agregados de exposición y modelo de NO₂ de la etiqueta a las carpetas sin
sufijo, y lleva las tablas de evaluación de NO₂ de output_files/modelo_1km_<etiqueta>/ a
output_files/modelo_1km/. PM₂.₅ no se toca. Idempotente: lo ya movido se salta.

    python -B scripts_modelo_1km/promover_no2.py --etiqueta no2sincosta
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts_modelo_1km"))
from _comun_modelo import AMBITOS_GRILLA, MODELO_ROOT, SUPERFICIES_ROOT, carpeta_ambito  # noqa: E402


def mover(src: Path, dst: Path) -> None:
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        print(f"  {src} -> {dst}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--etiqueta", required=True)
    ap.add_argument("--respaldo", default=f"v1_{date.today():%Y%m%d}")
    a = ap.parse_args(argv)
    nuevo_modelo = MODELO_ROOT / "modelos" / f"no2_{a.etiqueta}"
    if not (nuevo_modelo / "modelo_final.json").exists():
        print(f"no existe {nuevo_modelo}/modelo_final.json", file=sys.stderr)
        return 1
    for amb in AMBITOS_GRILLA:
        for base, pref in ((SUPERFICIES_ROOT, "superficies"), (MODELO_ROOT, "exposicion")):
            definitivo = carpeta_ambito(base, pref, "", amb) / "no2"
            etiqueta = carpeta_ambito(base, pref, f"_{a.etiqueta}", amb) / "no2"
            if not etiqueta.exists():
                continue
            mover(definitivo, definitivo.with_name(f"no2_{a.respaldo}"))
            mover(etiqueta, definitivo)
    mover(MODELO_ROOT / "modelos" / "no2", MODELO_ROOT / "modelos" / f"no2_{a.respaldo}")
    mover(nuevo_modelo, MODELO_ROOT / "modelos" / "no2")
    fuente, destino = RAIZ / "output_files" / f"modelo_1km_{a.etiqueta}", RAIZ / "output_files" / "modelo_1km"
    respaldo = destino / f"respaldo_no2_{a.respaldo}"
    respaldo.mkdir(exist_ok=True)
    for f in sorted(fuente.glob("*no2*")):
        if f.is_file():
            viejo = destino / f.name
            if viejo.exists() and not (respaldo / f.name).exists():
                shutil.move(str(viejo), str(respaldo / f.name))
            shutil.copy2(f, viejo)
    print("promoción lista")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
