#!/usr/bin/env python3
"""MOPITT MOP02J L2 -> candidatos cercanos por estacion y pasada.

Lee los Parquet nativos de ``descargar_mopitt_l2.py``. Conserva todos los
retrievals dentro de ``--radio-km``, su distancia, perfil, error, kernels, QA y
hora UTC exacta. No usa MOP03J L3, no resume por dia y no fabrica una serie
horaria donde el satelite no observo.
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


def candidatos_estacion(pixeles: pd.DataFrame, estaciones: pd.DataFrame,
                         radio_km: float) -> pd.DataFrame:
    if pixeles.empty:
        return pd.DataFrame()
    requeridas = {"lat", "lon", "ts_utc", "pixel_id", "granulo",
                 "observation_id"}
    faltan = requeridas - set(pixeles.columns)
    if faltan:
        raise ValueError(f"Parquet MOPITT L2 sin columnas {sorted(faltan)}")
    latp = pd.to_numeric(pixeles["lat"], errors="coerce").to_numpy()
    lonp = pd.to_numeric(pixeles["lon"], errors="coerce").to_numpy()
    margen_lat = radio_km / 110.6
    bloques = []
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
        # MOP02J agrupa todo el dia en un HDF. Separamos pasadas para esta
        # estacion por huecos >30 min, conservando el timestamp de cada
        # retrieval (la etiqueta no remuestrea ni altera tiempo alguno).
        sub = sub.sort_values("ts_utc").copy()
        ts = pd.to_datetime(sub["ts_utc"], utc=True, errors="raise")
        bloque = ts.diff().gt(pd.Timedelta(minutes=30)).cumsum().astype(int)
        sub["pasada_id"] = [
            f"{g}:p{b:02d}" for g, b in zip(sub["granulo"].astype(str), bloque)
        ]
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--radio-km", type=float, default=35.0)
    ap.add_argument("--prueba", type=int, default=0)
    ap.add_argument("--entrada", type=Path,
                    help="raiz alternativa de Parquet L2 para prueba")
    args = ap.parse_args(argv)
    if args.radio_km <= 0:
        ap.error("--radio-km debe ser positivo")
    estaciones = leer_estaciones()
    raiz = args.entrada or (CONT / "MOPITT_L2_CO" / "pixeles_pasada")
    archivos = sorted(raiz.rglob("*.parquet")) if raiz.exists() else []
    if args.prueba:
        archivos = archivos[:args.prueba]
    nombre = "mopitt_co_estacion_pasadas"
    checkpoint = Checkpoint(nombre)
    pendientes = checkpoint.falta(archivos)
    for k, path in enumerate(pendientes, 1):
        pix = pd.read_parquet(path)
        out = candidatos_estacion(pix, estaciones, args.radio_km)
        anexar_parquet(out, nombre, len(checkpoint.hechos) + 1)
        checkpoint.marcar(path)
        if k % 200 == 0:
            print(f"  MOPITT: {k}/{len(pendientes)}", flush=True)
    df = consolidar_candidatos(nombre)
    destino = SALIDA / f"{nombre}.parquet"
    print(f"LISTO MOPITT: {0 if df is None else len(df):,} "
          f"candidatos retrieval/pasada -> {destino}")


if __name__ == "__main__":
    main()
