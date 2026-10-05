#!/usr/bin/env bash
# lanzar_descargas.sh — corre todos los descargadores de contaminantes en orden.
# Uso:   bash lanzar_descargas.sh  # 2000-01-01 → hoy; ajustable por entorno
# Requiere ../.env con credenciales (ver ../.env.example) y las libs de requirements.txt.
set -u
cd "$(dirname "$0")"
DESDE="${DESDE:-2000-01-01}"
HASTA="${HASTA:-$(date +%F)}"
PY="${PYTHON:-python3}"
MIN_GB_LIBRES="${MIN_GB_LIBRES:-100}"
echo "== Descargas $DESDE → $HASTA =="

FALLOS=0
run () { echo; echo ">>> $*"; "$PY" "$@" || { echo "!! falló $1 (continuo)"; FALLOS=$((FALLOS+1)); }; }

# Verdad-terreno (todos los contaminantes)
run descargar_sinca.py       --desde "$DESDE" --hasta "$HASTA" --resolucion horario
# ERA5-Land: descarga/recorte nativo y, sólo cuando termina, retiro del legado
# mensual que figure con hash en cada manifiesto final completo.
run ../scripts_superficie/extractores/descargar_era5land.py \
  --desde "$DESDE" --hasta "$HASTA" --espacio-minimo-gb "$MIN_GB_LIBRES"
run retirar_legado_era5land.py --desde "$DESDE" --hasta "$HASTA" \
  --min-gb-libres "$MIN_GB_LIBRES"
# Reanálisis multi-gas (una sola fuente cubre NO2/O3/SO2/CO/PM2.5/PM10)
run descargar_cams_eac4.py   --desde "$DESDE" --hasta "$HASTA"
run descargar_geoscf.py      --desde "$DESDE" --hasta "$HASTA"
# Gases satelitales
run descargar_tropomi.py     --desde "$DESDE" --hasta "$HASTA" --contaminantes no2,o3,so2,co
run descargar_omi_l2.py      --desde "$DESDE" --hasta "$HASTA" --contaminantes no2,so2,o3
run descargar_mopitt_l2.py   --desde "$DESDE" --hasta "$HASTA"
# descargar_omi.py/descargar_mopitt.py (L3) quedan sólo como opt-in legado y
# no se ejecutan ni se necesitan en el disco final.
# Material particulado (PM2.5/PM10)
run descargar_acag_pm25.py   --temporal monthly --desde "$DESDE" --hasta "$HASTA"
# MERRA-2 combinado ya contiene AOD_M2 y PM25_M2; evita duplicar el mismo AER.
run descargar_merra2_meteo.py --desde "$DESDE" --hasta "$HASTA" --espacio-minimo-gb 100
# `descargar_merra2_aer.py` queda disponible como flujo AER independiente,
# nativo y reproducible, pero no se ejecuta junto al combinado.
run descargar_maiac_aod.py   --desde "$DESDE" --hasta "$HASTA"
run descargar_modis_aod.py   --desde "$DESDE" --hasta "$HASTA"
# 2000–2012-01-18: World Bank LEN DMSP-OLS gratuito, cada segmento nocturno y
# grilla publicada de 30 arc-sec; lectura COG por ventanas, sin crudo global.
run descargar_dmsp_len.py --desde "$DESDE" --hasta "$HASTA" \
  --min-gb-libres "$MIN_GB_LIBRES"
# 2012+: máximo temporal Black Marble (diario, 500 m; A1 aporta UTC_Time).
run descargar_nightlights.py --producto daily --desde "$DESDE" --hasta "$HASTA" \
  --min-gb-libres "$MIN_GB_LIBRES"
# GOES-East ABI AOD (NOAA NODD, S3 público): cada escaneo diurno en la grilla fija de
# 2 km, sólo celdas que tocan Chile; GOES_ABI_CADENCIA=horaria reduce ~6× el volumen.
run descargar_goes_abi_aod.py --desde "$DESDE" --hasta "$HASTA" \
  --cadencia "${GOES_ABI_CADENCIA:-nativa}" --min-gb-libres "$MIN_GB_LIBRES"
# Predictores espaciales a su resolución nativa (sin agregación comunal).
run descargar_lulc_esa_cci.py --desde 2000 --hasta 2022 --fuente cds \
  --min-gb-libres "$MIN_GB_LIBRES"
run descargar_topografia_nasadem.py --min-gb-libres "$MIN_GB_LIBRES"
echo; echo "== Fin (fuentes fallidas: $FALLOS) =="
[ "$FALLOS" -eq 0 ] || exit 1
