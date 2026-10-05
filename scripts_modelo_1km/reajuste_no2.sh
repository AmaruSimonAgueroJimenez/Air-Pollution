#!/bin/zsh
# Reajuste del modelo de NO₂ sin `dist_costa_km`, bajo la etiqueta no2sincosta, y re-estimación completa.
#
#   fase 0  copia los paneles y el modelo de PM₂.₅ definitivos a la etiqueta, para que sólo se recalcule NO₂
#   fase 1  calibración (LOSO, LBO, LRO, LPO), modelo final y tablas de evaluación (correr_qmd.py)
#   compuerta  el R² horario LOSO del NO₂ nuevo debe superar 0,45 (el anterior es 0,480); la franja se mide
#   fase 2  serie nacional de NO₂, luego RM y Biobío, con sus agregados de exposición
#   fase 3  promoción a definitivo (lo anterior queda respaldado con fecha). El análisis agudo, sus figuras y
#           los manuscritos se re-ejecutan en el repositorio Air-Pollution-Health-Chile
#
# Reanudable: cada fase salta lo ya hecho. Lanzar desacoplado:
#   python -c "import subprocess,os; subprocess.Popen(['zsh','scripts_modelo_1km/reajuste_no2.sh'],
#     stdin=open(os.devnull), stdout=open('output_files/modelo_1km/reajuste_no2_lanzador.log','ab'),
#     stderr=subprocess.STDOUT, start_new_session=True)"
set -u
RAIZ="${0:A:h:h}"
cd "$RAIZ" || exit 1
PY="${AFG_PYTHON:-$HOME/micromamba/envs/afg/bin/python}"
[[ -x "$PY" ]] || { echo "No existe $PY" >&2; exit 1; }
[[ -d /Volumes/Datos ]] || { echo "El disco externo /Volumes/Datos no está montado" >&2; exit 1; }
ETQ=no2sincosta
L="$HOME/Asesorias_Data_local/AirPollution/modelado_1km"
SALIDA="output_files/modelo_1km_$ETQ"; mkdir -p "$SALIDA"
REG="output_files/modelo_1km/reajuste_no2_$(date +%Y%m%dT%H%M%S).log"
echo "Registro: $REG"
{
  export QUARTO_PYTHON="$PY" PYTHONDONTWRITEBYTECODE=1
  export MODELO_1KM_ETIQUETA="$ETQ" MODELO_1KM_EXCLUIR="no2:dist_costa_km"
  export MODELO_1KM_LRO=1 MODELO_1KM_LPO=1 MODELO_1KM_LBO=1 MODELO_1KM_MOTORES_ML=""
  echo "== $(date '+%F %T') fase 0: copias a la etiqueta"
  for f in panel_pm25 panel_no2 satelites_estaciones; do
    for ext in parquet json; do
      [[ -e "$L/paneles/${f}_$ETQ.$ext" ]] || cp "$L/paneles/$f.$ext" "$L/paneles/${f}_$ETQ.$ext"
    done
  done
  [[ -d "$L/modelos/pm25_$ETQ" ]] || cp -R "$L/modelos/pm25" "$L/modelos/pm25_$ETQ"
  echo "== $(date '+%F %T') fase 1: calibración de NO₂ sin dist_costa_km"
  if [[ ! -e "$SALIDA/.fase1_ok" ]]; then
    caffeinate -i "$PY" -B scripts_modelo_1km/correr_qmd.py || { echo "== $(date '+%F %T') fase 1 FALLÓ"; exit 1; }
    touch "$SALIDA/.fase1_ok"
  fi
  echo "== $(date '+%F %T') compuerta"
  "$PY" -B scripts_modelo_1km/diagnostico_franja_no2.py --etiqueta "$ETQ" --umbral-r2 0.45 || { echo "== compuerta cerrada"; exit 2; }
  echo "== $(date '+%F %T') fase 2: producción de NO₂"
  for AMB in nacional rm biobio; do
    caffeinate -i "$PY" -B scripts_modelo_1km/producir_serie.py --ambito "$AMB" --contaminantes no2 --procesos 6 \
      || { echo "== $(date '+%F %T') producción $AMB FALLÓ"; exit 1; }
    caffeinate -i "$PY" -B scripts_modelo_1km/exposicion.py --ambito "$AMB" --contaminantes no2 --ventanas 2 \
      || { echo "== $(date '+%F %T') exposición $AMB FALLÓ"; exit 1; }
  done
  echo "== $(date '+%F %T') fase 3: promoción"
  "$PY" -B scripts_modelo_1km/promover_no2.py --etiqueta "$ETQ" || exit 1
  unset MODELO_1KM_ETIQUETA MODELO_1KM_EXCLUIR
  echo "== $(date '+%F %T') listo"
} >> "$REG" 2>&1
