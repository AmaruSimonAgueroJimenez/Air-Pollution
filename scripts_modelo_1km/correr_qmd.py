"""Ejecuta los chunks Python de ``docs/modelo_1km_horario.qmd`` fuera de Quarto.

El modelo vive en el documento; este ejecutor sólo extrae sus chunks y los corre
en orden, en un único espacio de nombres, para que las etapas largas (panel,
validación cruzada, modelo final) no dependan de un kernel de Jupyter. Como cada
artefacto pesado se cachea, un ``quarto render`` posterior reutiliza todo y sólo
arma el HTML. Las mismas variables de entorno del documento aplican aquí.

    python -B scripts_modelo_1km/correr_qmd.py                       # todo el documento
    python -B scripts_modelo_1km/correr_qmd.py --hasta "PANELES ="    # hasta el chunk que contiene ese texto
    python -B scripts_modelo_1km/correr_qmd.py --listar               # índice de chunks
"""
from __future__ import annotations

import argparse
import re
import sys
import time
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PATRON = re.compile(r"^```\{python\}\n(.*?)^```", flags=re.S | re.M)


def chunks(qmd: Path) -> list[tuple[str, str]]:
    """(resumen, código) de cada chunk; las opciones ``#|`` se quitan del código."""
    out = []
    for cuerpo in PATRON.findall(qmd.read_text(encoding="utf-8")):
        lineas = cuerpo.splitlines()
        opciones = [l for l in lineas if l.startswith("#|")]
        resumen = next((l.split(":", 1)[1].strip().strip('"') for l in opciones
                        if l.startswith(("#| code-summary:", "#| label:"))), "")
        codigo = "\n".join("" if l.startswith("#|") else l for l in lineas)   # conserva los números de línea
        out.append((resumen or codigo.strip().splitlines()[0][:80], codigo))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--qmd", default=str(RAIZ / "docs" / "modelo_1km_horario.qmd"))
    ap.add_argument("--hasta", help="detenerse después del primer chunk cuyo código contiene este texto")
    ap.add_argument("--listar", action="store_true")
    args = ap.parse_args(argv)
    qmd = Path(args.qmd).resolve()
    lista = chunks(qmd)
    if args.listar:
        for i, (resumen, _) in enumerate(lista):
            print(f"{i:3d}  {resumen}")
        return 0
    import matplotlib
    matplotlib.use("Agg")
    espacio = {"__name__": "__main__", "__file__": str(qmd)}
    t0 = time.time()
    for i, (resumen, codigo) in enumerate(lista):
        t = time.time()
        try:
            exec(compile(codigo, f"{qmd.name}[chunk {i}]", "exec"), espacio)
        except BaseException:  # noqa: BLE001  (SystemExit del documento incluido)
            print(f"[{i:3d}] FALLÓ  {resumen}", flush=True)
            traceback.print_exc()
            return 1
        print(f"[{i:3d}] {time.time() - t:8.1f} s  {resumen}", flush=True)
        if args.hasta and args.hasta in codigo:
            break
    print(f"Listo en {(time.time() - t0) / 60:.1f} min", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
