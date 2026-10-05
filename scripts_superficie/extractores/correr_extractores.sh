#!/bin/bash
# Corre los cuatro extractores en secuencia (reanudables). Uso:
#   cd scripts_superficie/extractores && bash correr_extractores.sh
cd "$(dirname "$0")"
LOG=extractores.log
{
  echo "== $(date) OMI =="
  python3 extraer_omi_estacion.py || echo "FALLO OMI"
  echo "== $(date) MOPITT =="
  python3 extraer_mopitt_estacion.py || echo "FALLO MOPITT"
  echo "== $(date) TROPOMI NO2 =="
  python3 extraer_s5p_estacion.py --producto NO2 || echo "FALLO S5P"
  echo "== $(date) MAIAC =="
  python3 extraer_maiac_estacion.py || echo "FALLO MAIAC"
  echo "== $(date) LISTO =="
} 2>&1 | tee -a "$LOG"
