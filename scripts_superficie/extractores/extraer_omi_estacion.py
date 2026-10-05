#!/usr/bin/env python3
"""OMI L2 pixel/pasada -> candidatos cercanos por estacion SINCA.

Lee exclusivamente los Parquet nativos creados por ``descargar_omi_l2.py``.
Conserva cada pixel candidato, timestamp UTC, distancia, huella, QA e
incertidumbre: no elige un unico pixel, no promedia por comuna/dia/hora y no
inventa horas. La seleccion espacial predeterminada (45 km entre centros) es
reversible mediante ``--radio-km``.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from comun import (
    CONT, SALIDA, Checkpoint, anexar_parquet, consolidar_candidatos,
    haversine_km, leer_estaciones,
)

PRODUCTOS = {"NO2": "no2", "SO2": "so2", "O3": "o3"}


def candidatos_estacion(pixeles: pd.DataFrame, estaciones: pd.DataFrame,
                         radio_km: float) -> pd.DataFrame:
    """Devuelve todas las parejas estacion-pixel dentro del radio."""
    if pixeles.empty:
        return pd.DataFrame()
    requeridas = {"lat", "lon", "ts_utc", "pixel_id", "granulo",
                 "observation_id"}
    faltan = requeridas - set(pixeles.columns)
    if faltan:
        raise ValueError(f"Parquet OMI L2 sin columnas {sorted(faltan)}")
    latp = pd.to_numeric(pixeles["lat"], errors="coerce").to_numpy()
    lonp = pd.to_numeric(pixeles["lon"], errors="coerce").to_numpy()
    bloques = []
    margen_lat = radio_km / 110.6
    for est in estaciones.itertuples(index=False):
        margen_lon = radio_km / max(20.0, 111.3 * np.cos(np.deg2rad(est.lat)))
        cand = np.flatnonzero(
            (np.abs(latp - est.lat) <= margen_lat)
            & (np.abs(lonp - est.lon) <= margen_lon)
        )
        if not len(cand):
            continue
        dist = haversine_km(est.lat, est.lon, latp[cand], lonp[cand])
        usar = cand[np.asarray(dist) <= radio_km]
        if not len(usar):
            continue
        sub = pixeles.iloc[usar].copy()
        sub.insert(0, "estacion", str(est.estacion))
        sub.insert(1, "nombre_estacion", str(est.nombre))
        sub.insert(2, "lat_estacion", float(est.lat))
        sub.insert(3, "lon_estacion", float(est.lon))
        sub.insert(4, "distancia_km", haversine_km(
            est.lat, est.lon,
            pd.to_numeric(sub["lat"]).to_numpy(),
            pd.to_numeric(sub["lon"]).to_numpy(),
        ).astype(np.float32))
        # Un granulo OMI es una orbita/pasada; los scanlines vecinos tienen
        # segundos distintos y no deben convertirse falsamente en pasadas.
        sub["pasada_id"] = sub["granulo"].astype(str)
        sub["rank_distancia"] = sub.groupby(
            ["estacion", "pasada_id"], sort=False,
        )["distancia_km"].rank(method="first").astype(np.uint16)
        sub["radio_seleccion_km"] = np.float32(radio_km)
        bloques.append(sub)
    if not bloques:
        return pd.DataFrame()
    out = pd.concat(bloques, ignore_index=True)
    if out.duplicated(["estacion", "observation_id"]).any():
        raise ValueError("pareja estacion-observacion duplicada")
    return out.sort_values(
        ["ts_utc", "estacion", "distancia_km", "pixel_id"],
    ).reset_index(drop=True)


def procesar_producto(prod: str, estaciones: pd.DataFrame, prueba: int,
                      radio_km: float, entrada: Path | None = None) -> pd.DataFrame | None:
    slug = PRODUCTOS[prod]
    raiz = entrada or (CONT / "OMI_L2" / "pixeles_pasada" / slug)
    archivos = sorted(raiz.rglob("*.parquet")) if raiz.exists() else []
    if prueba:
        archivos = archivos[:prueba]
    nombre = f"omi_{slug}_estacion_pasadas"
    checkpoint = Checkpoint(nombre)
    pendientes = checkpoint.falta(archivos)
    for k, path in enumerate(pendientes, 1):
        pix = pd.read_parquet(path)
        out = candidatos_estacion(pix, estaciones, radio_km)
        anexar_parquet(out, nombre, len(checkpoint.hechos) + 1)
        checkpoint.marcar(path)
        if k % 200 == 0:
            print(f"  {prod}: {k}/{len(pendientes)}", flush=True)
    return consolidar_candidatos(nombre)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--producto", default="todos", choices=["todos", *PRODUCTOS])
    ap.add_argument("--radio-km", type=float, default=45.0)
    ap.add_argument("--prueba", type=int, default=0)
    ap.add_argument("--entrada", type=Path,
                    help="raiz alternativa de Parquet L2 para prueba")
    args = ap.parse_args(argv)
    if args.radio_km <= 0:
        ap.error("--radio-km debe ser positivo")
    estaciones = leer_estaciones()
    productos = list(PRODUCTOS) if args.producto == "todos" else [args.producto]
    for prod in productos:
        df = procesar_producto(prod, estaciones, args.prueba,
                              args.radio_km, args.entrada)
        destino = SALIDA / f"omi_{PRODUCTOS[prod]}_estacion_pasadas.parquet"
        print(f"LISTO {prod}: {0 if df is None else len(df):,} "
              f"candidatos pixel/pasada -> {destino}")


if __name__ == "__main__":
    main()
