#!/usr/bin/env bash
# lanzar_descargas.sh — corre todos los descargadores de contaminantes en orden.
# Uso:   DESDE=2019-01-01 HASTA=2024-12-31 bash lanzar_descargas.sh
# Requiere ../.env con credenciales (ver ../.env.example) y las libs de requirements.txt.
set -u
cd "$(dirname "$0")"
DESDE="${DESDE:-2019-01-01}"
HASTA="${HASTA:-2024-12-31}"
PY="${PYTHON:-python3}"
echo "== Descargas $DESDE → $HASTA =="

FALLOS=0
run () { echo; echo ">>> $*"; "$PY" "$@" || { echo "!! falló $1 (continuo)"; FALLOS=$((FALLOS+1)); }; }

# Verdad-terreno (todos los contaminantes)
run descargar_sinca.py       --desde "$DESDE" --hasta "$HASTA" --resolucion horario
# Reanálisis multi-gas (una sola fuente cubre NO2/O3/SO2/CO/PM2.5/PM10)
run descargar_cams_eac4.py   --desde "$DESDE" --hasta "$HASTA"
run descargar_geoscf.py      --desde "$DESDE" --hasta "$HASTA"
# Gases satelitales
run descargar_tropomi.py     --desde "$DESDE" --hasta "$HASTA" --contaminantes no2,o3,so2,co
run descargar_omi.py         --desde "$DESDE" --hasta "$HASTA" --contaminantes no2,o3,so2
run descargar_mopitt.py      --desde "$DESDE" --hasta "$HASTA"
# Material particulado (PM2.5/PM10)
run descargar_acag_pm25.py   --temporal annual
run descargar_merra2_aer.py  --desde "$DESDE" --hasta "$HASTA"
run descargar_maiac_aod.py   --desde "$DESDE" --hasta "$HASTA"
run descargar_modis_aod.py   --desde "$DESDE" --hasta "$HASTA"
echo; echo "== Fin (fuentes fallidas: $FALLOS) =="
[ "$FALLOS" -eq 0 ] || exit 1
