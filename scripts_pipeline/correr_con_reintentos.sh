#!/usr/bin/env bash
# correr_con_reintentos.sh — envuelve un comando con reintentos (CMR/GES DISC dan 500).
# Uso:  bash correr_con_reintentos.sh python3 descargar_tropomi.py --contaminantes no2
set -u
MAX="${MAX:-5}"; ESPERA="${ESPERA:-30}"
for i in $(seq 1 "$MAX"); do
  echo ">>> intento $i/$MAX: $*"
  "$@" && { echo "OK"; exit 0; }
  echo "!! falló; reintento en ${ESPERA}s"; sleep "$ESPERA"
done
echo "XX agotados los reintentos"; exit 1
