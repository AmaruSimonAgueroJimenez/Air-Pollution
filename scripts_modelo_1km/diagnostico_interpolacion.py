"""Mide si la interpolación bilineal borra las costuras de los reanálisis gruesos.

Para cada hora muestreada extrae los predictores de los productos gruesos por los dos caminos (píxel más
cercano e interpolación) y compara pares de celdas contiguas de 1 km, **en latitud y en longitud**,
separando los pares que quedan dentro de un píxel nativo de los que cruzan su borde.

Dos estadísticos, porque el cociente ingenuo es vacuo: con enlace al vecino más cercano el |Δ| dentro
del píxel es exactamente cero, así que el cociente borde/interior es infinito por construcción y no
dice cuánto. El que informa es la **concentración**: qué fracción de la variación espacial total del
predictor cae en los bordes, dividida por la fracción de pares que son borde. Vale 1 si la variación
está repartida y 1/fracción si toda se concentra en las costuras.

    python -B scripts_modelo_1km/diagnostico_interpolacion.py

Las horas por omisión cubren invierno y verano, de día y de noche: el salto de la capa límite es mucho
mayor a media tarde que de madrugada, y muestrear sólo las 18 UTC (14:00 local) lo exagera.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comun_modelo import MODELO_ROOT, cargar_celdas, cargar_enlaces  # noqa: E402

log = logging.getLogger("diag_interp")
PRODUCTOS = ("merra2", "cams", "era5blh", "geoscf")
PASO_GRILLA = 0.01
HORAS = ["2005-07-15T06", "2005-07-15T18", "2010-01-15T06", "2010-01-15T18",
         "2015-07-15T06", "2015-07-15T18", "2020-01-15T06", "2020-01-15T18"]
SALIDA = MODELO_ROOT / "diagnostico" / "interpolacion_costuras.json"
COPIA = Path(__file__).resolve().parent.parent / "output_files" / "modelo_1km" / "costuras_reanalisis.json"


def indices_grilla(cel: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Índices enteros de fila y columna en la grilla de 0,01°.

    Los centros terminan en 0,005, de modo que ``round(v * 100)`` cae justo en medios exactos y numpy
    redondea al par más cercano: dos celdas vecinas colapsan en la misma clave y una tercera se salta.
    Medido sobre la grilla real, 534.176 de las 838.430 celdas colisionaban. Restar el mínimo antes de
    dividir por el paso elimina el desfase y da índices consecutivos exactos.
    """
    lat = cel["lat"].to_numpy(float); lon = cel["lon"].to_numpy(float)
    i = np.round((lat - lat.min()) / PASO_GRILLA).astype("int64")
    j = np.round((lon - lon.min()) / PASO_GRILLA).astype("int64")
    if len(set(zip(i.tolist(), j.tolist()))) != len(cel):
        raise RuntimeError("los índices de grilla colisionan; revisar el paso")
    return i, j


def pares_contiguos(i: np.ndarray, j: np.ndarray) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Pares (a, b) de celdas contiguas, por separado en longitud (este-oeste) y en latitud."""
    pos = {k: n for n, k in enumerate(zip(i.tolist(), j.tolist()))}
    salida = {}
    for nombre, (di, dj) in (("longitud", (0, 1)), ("latitud", (1, 0))):
        a, b = [], []
        for n, (ii, jj) in enumerate(zip(i.tolist(), j.tolist())):
            v = pos.get((ii + di, jj + dj))
            if v is not None:
                a.append(n); b.append(v)
        salida[nombre] = (np.asarray(a), np.asarray(b))
    return salida


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--horas", nargs="+", default=HORAS)
    a = ap.parse_args(argv)

    cel = cargar_celdas()
    enl = cargar_enlaces()
    i, j = indices_grilla(cel)
    pares = pares_contiguos(i, j)
    log.info("%s celdas | pares contiguos: %s", f"{len(cel):,}",
             ", ".join(f"{k} {len(v[0]):,}" for k, v in pares.items()))
    pix = {p: enl.set_index("celda").loc[cel["celda"], f"{p}_pixel"].to_numpy() for p in PRODUCTOS}

    filas = []
    for hora in a.horas:
        base = pd.DataFrame({"celda": cel["celda"].to_numpy(), "ts_utc": pd.Timestamp(hora)})
        tablas = {}
        for modo, flag in (("vecino", ""), ("interp", "1")):
            os.environ["MODELO_1KM_INTERPOLAR"] = flag
            sys.modules.pop("_features", None)
            import _features as F
            fuentes = F.FuentesHorarias()
            fuentes.productos = PRODUCTOS
            tablas[modo] = F.ensamblar_horario(base, enl, fuentes)
        import _features as F
        log.info("%s listo", hora)

        for prod in PRODUCTOS:
            for direccion, (ia, ib) in pares.items():
                cruza = pix[prod][ia] != pix[prod][ib]
                if not cruza.any():
                    continue
                for col in F.FEATURES_HORARIAS[prod].values():
                    fila = {"hora": hora, "producto": prod, "direccion": direccion, "variable": col,
                            "frac_pares_borde": float(cruza.mean())}
                    util = True
                    for modo in ("vecino", "interp"):
                        v = tablas[modo][col].to_numpy("float64")
                        d = np.abs(v[ia] - v[ib])
                        ok = np.isfinite(d)
                        dentro, fuera = d[ok & ~cruza], d[ok & cruza]
                        if len(dentro) < 100 or len(fuera) < 100:
                            util = False
                            break
                        tot = dentro.sum() + fuera.sum()
                        fila[f"{modo}_dentro"] = float(dentro.mean())
                        fila[f"{modo}_cruza"] = float(fuera.mean())
                        # concentración: cuánta de la variación total cae en los bordes, contra cuántos
                        # pares son borde. 1 = repartida; 1/frac = toda en las costuras.
                        fb = len(fuera) / (len(dentro) + len(fuera))
                        fila[f"{modo}_frac_variacion_borde"] = float(fuera.sum() / tot) if tot > 0 else np.nan
                        fila[f"{modo}_concentracion"] = float((fuera.sum() / tot) / fb) if tot > 0 and fb > 0 else np.nan
                    if util:
                        filas.append(fila)

    d = pd.DataFrame(filas)
    texto = json.dumps(filas, indent=1, default=float)
    SALIDA.parent.mkdir(parents=True, exist_ok=True); SALIDA.write_text(texto)
    COPIA.parent.mkdir(parents=True, exist_ok=True); COPIA.write_text(texto)
    pd.set_option("display.width", 200)
    print("\nConcentración de la variación espacial en los bordes del píxel nativo")
    print("(1 = repartida por igual; el máximo posible es 1/fracción de pares que son borde)\n")
    r = (d.groupby(["producto", "direccion"])
           .agg(pares_borde_pct=("frac_pares_borde", lambda s: 100 * s.mean()),
                maximo=("frac_pares_borde", lambda s: 1 / s.mean()),
                vecino=("vecino_concentracion", "median"),
                interpolado=("interp_concentracion", "median")))
    print(r.round(2).to_string())
    print(f"\n{len(a.horas)} horas | {COPIA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
