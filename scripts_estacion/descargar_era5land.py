#!/usr/bin/env python3
"""Descarga ERA5-Land horaria (0,1°) para Chile + BLH de ERA5.

Variables ERA5-Land: temperatura 2 m, punto de rocío 2 m (→ humedad
relativa), viento u/v 10 m, presión superficial y **precipitación total**
(el gran ausente del pipeline actual: lavado húmedo de PM). La altura de
capa límite (blh) no existe en ERA5-Land, así que se baja aparte de ERA5
(0,25°). Un archivo NetCDF por mes y dataset en
``data/contaminantes/ERA5Land/raw_chile/`` y ``ERA5/raw_chile/``.

Requisitos (una sola vez):
  1. Cuenta en https://cds.climate.copernicus.eu (gratita) y aceptar la
     licencia de cada dataset en su página web.
  2. Poner la llave API en ~/.cdsapirc  (la página "How to use the API"
     muestra el contenido exacto: url + key).
  3. pip install "cdsapi>=0.7"

Uso:
    python descargar_era5land.py              # 2019–2024 completo
    python descargar_era5land.py 2023 2024    # solo un rango

Volumen aproximado: 300–600 MB/mes ERA5-Land (~25–40 GB el total) +
~15 MB/mes de BLH. Re-ejecutable: salta los meses ya descargados.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cdsapi

from comun import CONT, require_data_root_available

AREA = [-17.0, -76.0, -56.5, -66.0]        # N, W, S, E (Chile continental)
VARS_LAND = [
    "2m_temperature", "2m_dewpoint_temperature",
    "10m_u_component_of_wind", "10m_v_component_of_wind",
    "surface_pressure", "total_precipitation",
]
HORAS = [f"{h:02d}:00" for h in range(24)]
DIAS = [f"{d:02d}" for d in range(1, 32)]


def descargar(cli, dataset: str, pedido: dict, destino: Path):
    require_data_root_available()
    if destino.exists() and destino.stat().st_size > 1_000_000:
        print(f"  ya está: {destino.name}")
        return
    destino.parent.mkdir(parents=True, exist_ok=True)
    print(f"  bajando {destino.name} …", flush=True)
    cli.retrieve(dataset, pedido, str(destino))


def main():
    anios = [int(a) for a in sys.argv[1:]] or list(range(2019, 2025))
    if len(anios) == 2 and anios[1] > anios[0] + 1:
        anios = list(range(anios[0], anios[1] + 1))
    cli = cdsapi.Client()
    base_land = CONT / "ERA5Land" / "raw_chile"
    base_era5 = CONT / "ERA5" / "raw_chile"
    for a in anios:
        for m in range(1, 13):
            descargar(cli, "reanalysis-era5-land", {
                "variable": VARS_LAND,
                "year": str(a), "month": f"{m:02d}",
                "day": DIAS, "time": HORAS,
                "area": AREA, "format": "netcdf",
            }, base_land / f"era5land_{a}{m:02d}.nc")
            descargar(cli, "reanalysis-era5-single-levels", {
                "product_type": "reanalysis",
                "variable": ["boundary_layer_height"],
                "year": str(a), "month": f"{m:02d}",
                "day": DIAS, "time": HORAS,
                "area": AREA, "format": "netcdf",
            }, base_era5 / f"era5_blh_{a}{m:02d}.nc")
    print("LISTO. Avísale a Claude para extraer las series por estación "
          "e integrarlas al panel.")


if __name__ == "__main__":
    main()
