"""Pesos bilineales de cada celda sobre la grilla nativa de los reanálisis gruesos.

**Por qué.** Los predictores entran al modelo por el píxel nativo más cercano, lo que es honesto sobre la
resolución de cada fuente pero convierte un campo continuo en una función escalón: el árbol parte sobre
ese escalón y la superficie hereda la cuadrícula. Medido sobre la media 2000–2026, cruzar el borde de un
píxel de MERRA-2 da un salto 7,6 veces mayor en NO₂ (11,8 en PM₂,₅) que moverse dentro de él, y en el
norte, donde la variación real es diminuta, esos rectángulos dominan el mapa.

La presión, la temperatura o la altura de capa límite **son** continuas en la realidad; la grilla de
MERRA-2 es una discretización de algo continuo, así que interpolar está más cerca de la verdad que el
vecino más cercano. Un borde afirma que en ese lugar hay un cambio; la suavidad no afirma nada.

**Qué hace.** Para cada celda y cada producto interpolable, los cuatro nodos de la grilla regular que la
rodean y sus pesos bilineales. Los recortes de Chile no son rectángulos completos (la franja del país
deja huecos, y las islas oceánicas están lejos), así que un nodo puede no existir o no ser válido: los
pesos se renormalizan sobre los que sí están, y si no queda ninguno la celda cae al enlace por vecino
más cercano de siempre.

Escribe ``grilla_1km/enlaces_interpolacion.parquet`` **sin tocar** ``enlaces_productos.parquet``, de modo
que el camino definitivo no se invalida: sólo lo usa quien active ``MODELO_1KM_INTERPOLAR``.

    python -B scripts_modelo_1km/enlaces_interpolacion.py
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from _comun_modelo import (GRILLA_DIR, cargar_celdas, catalogo_geoscf, leer_catalogo, pixeles_validos,
                           publicar_parquet)

log = logging.getLogger("enlaces_interp")
RUTA = GRILLA_DIR / "enlaces_interpolacion.parquet"
# Los gruesos. ERA5-Land (0,1°) y MAIAC (1 km) se dejan al vecino: sus costuras son de 2× y su grano ya
# es más fino que la agregación comunal. MAIAC además es una recuperación con huecos, no un campo.
PRODUCTOS = ("era5blh", "merra2", "cams", "geoscf")
K = 4


def _paso(v: np.ndarray) -> float:
    """Paso de la grilla: la menor diferencia positiva entre coordenadas únicas (los huecos del recorte
    inflan la media, de modo que el mínimo es lo correcto)."""
    u = np.unique(np.round(np.asarray(v, float), 6))
    d = np.diff(u)
    d = d[d > 1e-9]
    if len(d) == 0:
        raise ValueError("el catálogo tiene una sola coordenada")
    return float(np.min(d))


def pesos_bilineales(lat_q, lon_q, cat: pd.DataFrame, validos: np.ndarray | None):
    """(píxeles, pesos) de forma (n, 4). Peso 0 donde el nodo no existe o no es válido."""
    lat_c = cat["lat"].to_numpy(float); lon_c = cat["lon"].to_numpy(float)
    pid = cat["pixel_id"].to_numpy().astype("int64")
    plat, plon = _paso(lat_c), _paso(lon_c)
    lat0, lon0 = lat_c.min(), lon_c.min()
    ii = np.round((lat_c - lat0) / plat).astype("int64")
    jj = np.round((lon_c - lon0) / plon).astype("int64")
    ok = np.ones(len(pid), bool) if validos is None else np.isin(pid, validos)
    red = np.full((ii.max() + 2, jj.max() + 2), -1, "int64")          # celosía densa: sólo decenas de miles
    red[ii[ok], jj[ok]] = pid[ok]

    fi = (np.asarray(lat_q, float) - lat0) / plat
    fj = (np.asarray(lon_q, float) - lon0) / plon
    # Fuera del recorte del producto no se interpola: se deja sin nodo para que caiga al enlace por
    # vecino más cercano, que sí respeta el radio máximo. Sin esta guarda, recortar el índice al borde
    # daba peso 1 a un nodo a cualquier distancia: las 382 celdas insulares (Rapa Nui, Juan Fernández,
    # Desventuradas) recibían química continental de GEOS-CF a más de 3.000 km en vez de quedar en NaN,
    # que es lo que el modelo fue entrenado a esperar.
    tol = 1e-6
    fuera = (fi < -tol) | (fi > red.shape[0] - 1 + tol) | (fj < -tol) | (fj > red.shape[1] - 1 + tol)
    i0 = np.clip(np.floor(fi).astype("int64"), 0, red.shape[0] - 2)
    j0 = np.clip(np.floor(fj).astype("int64"), 0, red.shape[1] - 2)
    ti = np.clip(fi - i0, 0, 1); tj = np.clip(fj - j0, 0, 1)
    P = np.empty((len(fi), K), "int64"); W = np.empty((len(fi), K), "float64")
    for k, (di, dj) in enumerate(((0, 0), (0, 1), (1, 0), (1, 1))):
        P[:, k] = red[i0 + di, j0 + dj]
        W[:, k] = (ti if di else 1 - ti) * (tj if dj else 1 - tj)
    W = np.where((P >= 0) & ~fuera[:, None], W, 0.0)
    s = W.sum(axis=1)
    W = np.where(s[:, None] > 1e-12, W / np.where(s[:, None] > 0, s[:, None], 1), 0.0)
    return P, W.astype("float32")


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--forzar", action="store_true")
    a = ap.parse_args(argv)
    if RUTA.exists() and not a.forzar:
        log.info("%s ya existe (usa --forzar)", RUTA)
        return 0
    cel = cargar_celdas()
    enl = pd.read_parquet(GRILLA_DIR / "enlaces_productos.parquet").set_index("celda").reindex(cel["celda"])
    out = pd.DataFrame({"celda": cel["celda"].to_numpy()})
    for prod in PRODUCTOS:
        cat = catalogo_geoscf() if prod == "geoscf" else leer_catalogo(prod)
        if cat is None:
            log.warning("%s: sin catálogo, se omite", prod)
            continue
        P, W = pesos_bilineales(cel["lat"].to_numpy(), cel["lon"].to_numpy(), cat, pixeles_validos(prod))
        # sin ningún nodo utilizable: se cae al enlace de siempre, con peso 1
        huerfana = W.sum(axis=1) <= 1e-12
        if huerfana.any():
            vecino = enl[f"{prod}_pixel"].to_numpy("int64")
            P[huerfana, 0] = vecino[huerfana]
            # si tampoco hay vecino dentro del radio, la celda queda sin valor, como en el camino de
            # siempre: peso 0 en los cuatro nodos
            W[huerfana, 0] = np.where(vecino[huerfana] >= 0, 1.0, 0.0)
        for k in range(K):
            out[f"{prod}_pix{k}"] = P[:, k]
            out[f"{prod}_w{k}"] = W[:, k]
        nodos = (W > 0).sum(axis=1)
        log.info("%s: nodos por celda %.2f (4 = interior pleno); fuera del recorte, al vecino: %d",
                 prod, nodos.mean(), int(huerfana.sum()))
    sha = publicar_parquet(out, RUTA)
    log.info("%s · %s celdas · sha %s", RUTA, f"{len(out):,}", sha[:12])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
