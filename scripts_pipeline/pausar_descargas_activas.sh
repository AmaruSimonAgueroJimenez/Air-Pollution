#!/usr/bin/env bash
# Pausa limpiamente las descargas largas iniciadas de forma manual.
# SIGINT permite que Python cierre manifiestos/temporales; SIGTERM se usa solo
# si un proceso no responde. Los descargadores son idempotentes al relanzar.
set -u

PIDS=()
while IFS= read -r linea; do
  pid="${linea%% *}"
  comando="${linea#* }"
  ejecutable="${comando%% *}"
  case "$ejecutable" in
    *python*|*Python*) ;;
    *) continue ;;
  esac
  case "$comando" in
    *"scripts_pipeline/descargar_modis_aod.py"*|\
    *"scripts_pipeline/descargar_maiac_aod.py"*|\
    *"scripts_pipeline/descargar_tropomi.py"*|\
    *"scripts_superficie/extractores/descargar_era5land.py"*)
      PIDS+=("$pid")
      ;;
  esac
done < <(ps -axo pid=,command= | sed -E 's/^ +//')

if [ "${#PIDS[@]}" -eq 0 ]; then
  echo "No hay descargadores activos."
  exit 0
fi

echo "Pausando PID: ${PIDS[*]}"
kill -INT "${PIDS[@]}" 2>/dev/null || true

for _ in 1 2 3 4; do
  RESTANTES=()
  for pid in "${PIDS[@]}"; do
    kill -0 "$pid" 2>/dev/null && RESTANTES+=("$pid")
  done
  [ "${#RESTANTES[@]}" -eq 0 ] && break
  sleep 15
done

if [ "${#RESTANTES[@]}" -gt 0 ]; then
  echo "Terminación solicitada a PID que no respondieron: ${RESTANTES[*]}"
  kill -TERM "${RESTANTES[@]}" 2>/dev/null || true
  sleep 5
fi

ACTIVOS=()
for pid in "${PIDS[@]}"; do
  kill -0 "$pid" 2>/dev/null && ACTIVOS+=("$pid")
done

if [ "${#ACTIVOS[@]}" -gt 0 ]; then
  sync
  echo "No es seguro apagar todavía; siguen activos PID: ${ACTIVOS[*]}" >&2
  exit 1
fi

sync
echo "Pausa completada; es seguro apagar mediante macOS."
