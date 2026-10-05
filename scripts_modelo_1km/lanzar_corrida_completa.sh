#!/bin/zsh
# Corrida completa del modelo 1 km × hora (toda la temporalidad SINCA, 2000–2026) y render del informe.
#
#   zsh scripts_modelo_1km/lanzar_corrida_completa.sh            # en primer plano
#   nohup zsh scripts_modelo_1km/lanzar_corrida_completa.sh &    # desacoplada del terminal
#
# Ejecuta los chunks de docs/modelo_1km_horario.qmd fuera de Quarto (correr_qmd.py) y, si terminan
# bien, arma el HTML con todo lo cacheado. Es reanudable: cada artefacto y cada pliegue de la
# validación se guardan al terminar, así que relanzar este mismo script continúa donde quedó.
# `caffeinate -i` impide que el Mac se duerma mientras corre. Variables MODELO_1KM_* ya exportadas
# se respetan (p. ej. MODELO_1KM_ETIQUETA para no pisar una corrida definitiva).
set -u
RAIZ="${0:A:h:h}"
cd "$RAIZ" || exit 1
PY="${AFG_PYTHON:-$HOME/micromamba/envs/afg/bin/python}"
if [[ ! -x "$PY" ]]; then
  echo "No existe $PY; define AFG_PYTHON con el Python del entorno afg" >&2
  exit 1
fi
export QUARTO_PYTHON="$PY" PYTHONDONTWRITEBYTECODE=1
export MODELO_1KM_LRO="${MODELO_1KM_LRO:-1}" MODELO_1KM_LPO="${MODELO_1KM_LPO:-1}" MODELO_1KM_LBO="${MODELO_1KM_LBO:-1}"
SALIDA="output_files/modelo_1km${MODELO_1KM_ETIQUETA:+_$MODELO_1KM_ETIQUETA}"
mkdir -p "$SALIDA"
REGISTRO="$SALIDA/corrida_$(date +%Y%m%dT%H%M%S).log"
echo "Registro: $REGISTRO  (avance fino: $SALIDA/modelo_1km.log)"
{
  echo "== $(date '+%F %T') correr_qmd.py (LRO=$MODELO_1KM_LRO LPO=$MODELO_1KM_LPO LBO=$MODELO_1KM_LBO etiqueta='${MODELO_1KM_ETIQUETA:-}')"
  caffeinate -i "$PY" -B scripts_modelo_1km/correr_qmd.py || { echo "== $(date '+%F %T') correr_qmd.py FALLÓ"; exit 1; }
  echo "== $(date '+%F %T') quarto render"
  # Quarto se lanza desde docs/: con `embed-resources` y `--output`, lanzado desde la raíz busca
  # modelo_1km_horario_files/ en el directorio de trabajo y falla al empaquetar el HTML.
  ( cd docs && caffeinate -i quarto render modelo_1km_horario.qmd \
      ${MODELO_1KM_ETIQUETA:+--output "modelo_1km_horario_${MODELO_1KM_ETIQUETA}.html"} ) \
    || { echo "== $(date '+%F %T') quarto render FALLÓ"; exit 1; }
  echo "== $(date '+%F %T') listo"
} > "$REGISTRO" 2>&1
