#!/usr/bin/env python3
"""Corre el pipeline completo de estimación en la máquina local (donde están
los datos crudos): tabla de predictores → panel por contaminante → validación
LOSO de los tres motores → protocolo del producto → series por nivel →
todas las figuras. Idéntico a lo que ejecuta el notebook, pero por consola
y con cada contaminante en un subproceso (memoria acotada).

Uso típico (desde cualquier carpeta):
  python scripts_superficie/correr_pipeline.py                 # todo, usa caché
  python scripts_superficie/correr_pipeline.py --fresh         # borra caché pesada y recalcula
  python scripts_superficie/correr_pipeline.py --pols so2 co   # solo esos contaminantes
  python scripts_superficie/correr_pipeline.py --solo-figuras  # regenera figuras desde artefactos

Variables de entorno útiles: AIR_POLLUTION_DATA_ROOT (raíz ``data`` externa;
si no se define usa ``$ASESORIAS_DATA_ROOT/AirPollution/data``), AFG_NEURO_ROOT
(repo hermano con la meteorología comunal), AFG_N_TREES, AFG_MAX_TRAIN_ROWS,
AFG_VERBOSE=1.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
os.environ.setdefault("AFG_REPO_ROOT", str(RAIZ))
os.environ.setdefault("AFG_NEURO_ROOT", str(RAIZ.parent / "Neurodegen-Epidemiology-Chile"))
os.environ.setdefault("AFG_VERBOSE", "1")
sys.path.insert(0, str(AQUI))

POLS = ["pm25", "pm10", "no2", "o3", "so2", "co"]

CODIGO_POL = r'''
import gc, os, sys
sys.path.insert(0, %r)
os.chdir(%r)
import afg_lib as L
pol = %r
p = L.construir_panel(pol)
print(f"{pol}: panel {p.shape} · met={'PBLH' in p.columns} · fuentes_so2={'carga_fuentes_so2' in p.columns}", flush=True)
del p; gc.collect()
res = L.validar_contaminante(pol)
print(f"{pol}: LOSO " + " ".join(f"{m}={v['horario']['r2']:.3f}" for m, v in res["motores"].items()), flush=True)
gc.collect()
prot = L.protocolo_producto(pol)
print(f"{pol}: producto r2={prot['r2_pearson']:.3f}", flush=True)
L.serie_mensual_niveles(pol)
'''

CODIGO_FIGS = r'''
import json, os, sys
sys.path.insert(0, %r)
os.chdir(%r)
import afg_lib as L
resultados = {}
for pol in %r:
    res = json.loads((L.OUT / f"metricas_cv_{pol}.json").read_text())
    prot = json.loads((L.OUT / f"metricas_producto_{pol}.json").read_text())
    resultados[pol] = res
    for f in [lambda: L.fig_acuerdo_nacional(pol), lambda: L.fig_acuerdo_macrozona(pol),
              lambda: L.fig_series_nacional_macrozona(pol), lambda: L.fig_series_region(pol),
              lambda: L.fig_series_satelites(pol), lambda: L.fig_series_satelites_region(pol),
              lambda: L.fig_series_sinca(pol), lambda: L.fig_series_sinca_region(pol),
              lambda: L.fig_comparacion(pol, res), lambda: L.fig_dispersion(pol, res),
              lambda: L.fig_mapa_r2(pol, res), lambda: L.fig_serie(pol, res),
              lambda: L.fig_importancias(pol), lambda: L.fig_protocolo(pol, prot)]:
        print("  ", f().name, flush=True)
if len(resultados) == 6:
    print("  ", L.fig_resumen(resultados).name)
'''


def correr(codigo: str, etiqueta: str):
    print(f"\n=== {etiqueta} ===", flush=True)
    r = subprocess.run([sys.executable, "-c", codigo], env=os.environ.copy())
    if r.returncode != 0:
        raise SystemExit(f"FALLÓ: {etiqueta}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pols", nargs="*", default=POLS)
    ap.add_argument("--fresh", action="store_true",
                    help="borra predictores, paneles, OOF y métricas (respalda en output_files/_bak)")
    ap.add_argument("--solo-figuras", action="store_true")
    ap.add_argument("--sin-figuras", action="store_true")
    a = ap.parse_args()
    out = RAIZ / "output_files"
    figs = out / "figures"
    if a.fresh:
        bak = out / "_bak"
        bak.mkdir(exist_ok=True)
        for patron in ["predictores_estaciones_horario.parquet", "panel_*_horario.parquet",
                       "oof_*.parquet", "producto_diario_*.parquet",
                       "metricas_cv_*.json", "metricas_producto_*.json",
                       "comparacion_motores_*.csv", "importancias_*.csv",
                       "r2_estacion_*.csv", "resumen_predictores.csv",
                       "cobertura_sinca.csv"]:
            for f in out.glob(patron):
                if f.suffix == ".parquet":
                    f.unlink()
                else:
                    shutil.move(str(f), bak / f.name)
        for f in figs.glob("*.png"):
            f.unlink()
        print("caché pesada borrada (artefactos chicos respaldados en output_files/_bak)")
    if not a.solo_figuras:
        correr(f"import os, sys; sys.path.insert(0, {str(AQUI)!r}); os.chdir({str(RAIZ)!r}); "
               f"import afg_lib as L; t = L.tabla_predictores(); "
               f"print('predictores', t.shape, [c for c in t.columns if c not in ('estacion','ts')]); "
               f"print(L.resumen_predictores().to_string(index=False)); "
               f"print(L.tabla_cobertura_sinca().to_string(index=False))",
               "tabla de predictores, resumen y cobertura SINCA")
        for pol in a.pols:
            correr(CODIGO_POL % (str(AQUI), str(RAIZ), pol), f"{pol}: panel + LOSO + producto")
    if not a.sin_figuras:
        correr(CODIGO_FIGS % (str(AQUI), str(RAIZ), a.pols), "figuras")
        if shutil.which("pngquant"):
            for f in figs.glob("*.png"):
                subprocess.run(["pngquant", "--quality", "60-85", "--speed", "1",
                                "--force", "--ext", ".png", str(f)])
            print("figuras comprimidas (pngquant)")
    print("\nLISTO. Para reconstruir el documento:  quarto render others_files/20260902_informe_modelos_estimacion.qmd")


if __name__ == "__main__":
    main()
