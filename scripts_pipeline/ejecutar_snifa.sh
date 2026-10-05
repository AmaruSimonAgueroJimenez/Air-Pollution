#!/usr/bin/env bash
# Descarga y procesamiento independiente de la red adicional SNIFA.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "${PYTHON_SNIFA:-}" ]]; then
  if [[ -x "$HOME/Asesorias_Data_local/AirPollution/runtime_snifa/bin/python" ]]; then
    PYTHON_SNIFA="$HOME/Asesorias_Data_local/AirPollution/runtime_snifa/bin/python"
  else
    PYTHON_SNIFA=python3
  fi
fi
if (( $# )); then
  echo "Este lanzador ejecuta el historial completo. Para filtros u opciones, use descargar_snifa.py y preparar_snifa_modelado.py por separado." >&2
  exit 2
fi
"$PYTHON_SNIFA" "$SCRIPT_DIR/descargar_snifa.py"
"$PYTHON_SNIFA" "$SCRIPT_DIR/preparar_snifa_modelado.py"
