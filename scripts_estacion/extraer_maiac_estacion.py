#!/usr/bin/env python3
"""MAIAC MCD19A2 (AOD 1 km, HDF4, proyección sinusoidal) → serie por estación.

Para cada tile-día toma, por pasada (orbit), la media 3×3 alrededor del
píxel de cada estación, filtrando por calidad (bits de nubes del AOD_QA).
Salida: ``output_files/estacion/maiac_aod.parquet`` con columnas
``estacion, ts, valor, n_pix, satelite`` (T=Terra, A=Aqua; AOD 550 nm).

Requiere ``pyhdf`` (conda-forge). Re-ejecutable. Referencia: 4–10 h.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from pyhdf.SD import SD, SDC

from comun import CONT, Acumulador, leer_estaciones

# Geometría sinusoidal MODIS (metros)
R_TIERRA = 6371007.181
MEDIO_MUNDO = 20015109.354
T_TILE = 1111950.5196666666      # 10° de arco en el ecuador
N_CELDAS = 1200                  # grilla 1 km
PASO = T_TILE / N_CELDAS


def estacion_a_tile(lat: float, lon: float):
    """(h, v, fila, col) del píxel sinusoidal 1 km de una coordenada."""
    x = R_TIERRA * np.radians(lon) * np.cos(np.radians(lat))
    y = R_TIERRA * np.radians(lat)
    h = int((x + MEDIO_MUNDO) // T_TILE)
    v = int((MEDIO_MUNDO / 2 - y) // T_TILE)
    col = int((x - (-MEDIO_MUNDO + h * T_TILE)) // PASO)
    fila = int(((MEDIO_MUNDO / 2 - v * T_TILE) - y) // PASO)
    return h, v, fila, col


def parsear_pasadas(atributo: str):
    """'2019010A1420 2019010T1315 …' → [(Timestamp UTC, 'A'|'T'), …]."""
    pasadas = []
    for tok in atributo.split():
        m = re.match(r"(\d{4})(\d{3})([AT])(\d{2})(\d{2})", tok)
        if not m:
            continue
        a, doy, sat, hh, mm = m.groups()
        ts = (pd.Timestamp(int(a), 1, 1)
              + pd.Timedelta(days=int(doy) - 1, hours=int(hh),
                             minutes=int(mm)))
        pasadas.append((ts, sat))
    return pasadas


def procesar_tile(ruta: Path, puntos: list) -> pd.DataFrame | None:
    """puntos: [(estacion, fila, col), …] de las estaciones de ese tile."""
    try:
        sd = SD(str(ruta), SDC.READ)
        aod_ds = sd.select("Optical_Depth_055")
        aod = aod_ds[:].astype(float)                  # (orbitas, 1200, 1200)
        atrib = aod_ds.attributes()
        escala = float(atrib.get("scale_factor", 0.001))
        relleno = float(atrib.get("_FillValue", -28672))
        qa = sd.select("AOD_QA")[:].astype(np.uint16)
        pasadas = parsear_pasadas(getattr(sd, "Orbit_time_stamp", "")
                                  if hasattr(sd, "Orbit_time_stamp")
                                  else sd.attributes().get("Orbit_time_stamp", ""))
        sd.end()
    except Exception as e:                             # HDF4 corrupto ocasional
        print(f"  [aviso] {ruta.name}: {e}; lo salto")
        return None

    aod[aod == relleno] = np.nan
    aod *= escala
    # bits 0–2 de AOD_QA: máscara de nubes; 1 = despejado
    despejado = (qa & 0b111) == 1
    aod[~despejado] = np.nan

    filas = []
    n_orb = min(aod.shape[0], len(pasadas)) if pasadas else aod.shape[0]
    for k in range(n_orb):
        ts, sat = pasadas[k] if pasadas else (None, "?")
        if ts is None:
            continue
        plano = aod[k]
        for est, fi, co in puntos:
            v = plano[max(fi - 1, 0):fi + 2, max(co - 1, 0):co + 2]
            n = int(np.isfinite(v).sum())
            if n:
                filas.append({"estacion": est, "ts": ts,
                              "valor": float(np.nanmean(v)),
                              "n_pix": n, "satelite": sat})
    return pd.DataFrame(filas) if filas else None


def main():
    est = leer_estaciones()
    por_tile: dict[tuple, list] = defaultdict(list)
    for e, la, lo in est[["estacion", "lat", "lon"]].itertuples(index=False):
        h, v, fi, co = estacion_a_tile(la, lo)
        por_tile[(h, v)].append((e, fi, co))
    print("tiles con estaciones:",
          {f"h{h:02d}v{v:02d}": len(p) for (h, v), p in por_tile.items()})

    carpeta = CONT / "MCD19A2.061" / "raw_chile"
    archivos = sorted(carpeta.glob("MCD19A2.A???????.h??v??.061.*.hdf"))
    acc = Acumulador("maiac_aod")
    pendientes = []
    for f in archivos:
        m = re.search(r"\.h(\d{2})v(\d{2})\.", f.name)
        if m and (int(m.group(1)), int(m.group(2))) in por_tile \
                and not acc.ya_visto(f.name):
            pendientes.append((f, (int(m.group(1)), int(m.group(2)))))
    print(f"{len(archivos)} tiles en disco; {len(pendientes)} pendientes útiles")
    for i, (f, hv) in enumerate(pendientes):
        acc.agregar(f.name, procesar_tile(f, por_tile[hv]))
        if (i + 1) % 200 == 0:
            print(f"  {i + 1}/{len(pendientes)}", flush=True)
    acc.consolidar()


if __name__ == "__main__":
    main()
