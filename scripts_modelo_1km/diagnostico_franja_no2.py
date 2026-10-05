"""Compuerta del reajuste de NO₂: ¿validó parecido y desapareció la franja del norte?

Compara el R² horario LOSO del NO₂ de la etiqueta con el definitivo y mide, sobre los días de
demostración ya producidos por el informe, la media de NO₂ en el norte grande (18–26,5° S) a menos y
a más de 80 km de la costa, que es donde el modelo anterior daba un salto de 4,6 a 7,5 ppb.

    python -B scripts_modelo_1km/diagnostico_franja_no2.py --etiqueta no2sincosta --umbral-r2 0.45
Sale con 0 si el R² pasa la compuerta; con 2 si no. La franja se informa, no bloquea.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts_modelo_1km"))
from _comun_modelo import MODELO_ROOT, SUPERFICIES_ROOT, cargar_celdas, carpeta_ambito, leer_superficie_dia, ruta_superficie_dia  # noqa: E402


def r2_loso(sufijo: str) -> float | None:
    f = RAIZ / "output_files" / f"modelo_1km{sufijo}" / "eval_niveles_no2.csv"
    if not f.exists():
        return None
    e = pd.read_csv(f)
    e = e[(e.estrato == "Chile") & (e.nivel == "horario") & (e.protocolo == "loso")]
    return float(e["r2"].iloc[0]) if len(e) else None


def franja(sufijo: str, dias: list[date]) -> dict | None:
    cel = cargar_celdas()
    est = pd.read_parquet(MODELO_ROOT / "grilla_1km" / "estaticas.parquet", columns=["celda", "dist_costa_km"])
    dc = est.set_index("celda")["dist_costa_km"].reindex(cel["celda"].to_numpy()).to_numpy()
    lat, lon = cel["lat"].to_numpy(), cel["lon"].to_numpy()
    norte = (lat > -26.5) & (lat < -18) & (lon > -76.5) & np.isfinite(dc)
    base = carpeta_ambito(SUPERFICIES_ROOT, "superficies", sufijo, "nacional")   # sufijo ya trae el guion bajo
    medias = []
    for d in dias:
        nc, _ = ruta_superficie_dia(base, "no2", d)
        if not nc.exists():
            continue
        _, celdas, val = leer_superficie_dia(nc)
        v = pd.Series(np.nanmean(val, axis=0), index=celdas).reindex(cel["celda"].to_numpy()).to_numpy()
        medias.append(v)
    if not medias:
        return None
    v = np.nanmean(np.vstack(medias), axis=0)
    ok = norte & np.isfinite(v)
    costa, interior = float(v[ok & (dc < 80)].mean()), float(v[ok & (dc >= 80)].mean())
    return {"dias": len(medias), "costa_menos_80km": costa, "interior_mas_80km": interior, "razon": interior / costa}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--etiqueta", required=True)
    ap.add_argument("--umbral-r2", type=float, default=0.45)
    ap.add_argument("--dias", default="2024-06-05,2024-06-06")
    a = ap.parse_args(argv)
    dias = [date.fromisoformat(x) for x in a.dias.split(",")]
    nuevo, viejo = r2_loso(f"_{a.etiqueta}"), r2_loso("")
    fr_nuevo, fr_viejo = franja(f"_{a.etiqueta}", dias), franja("", dias)
    out = {"r2_loso_horario": {"nuevo": nuevo, "definitivo": viejo}, "franja_norte": {"nuevo": fr_nuevo, "definitivo": fr_viejo}}
    print(json.dumps(out, indent=1, ensure_ascii=False))
    (RAIZ / "output_files" / f"modelo_1km_{a.etiqueta}" / "compuerta_no2.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    if nuevo is None:
        print("sin métricas LOSO del NO₂ nuevo: la calibración no terminó", file=sys.stderr)
        return 2
    if nuevo < a.umbral_r2:
        print(f"R² LOSO horario {nuevo:.3f} < umbral {a.umbral_r2}: no se produce la serie", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
