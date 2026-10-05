#!/bin/zsh
# ¿Conviene interpolar los reanálisis gruesos en vez de tomar el píxel más cercano?
#
#   etapa 0  pesos bilineales por celda (enlaces_interpolacion.py) y medición de las costuras
#   etapa 1  paneles de estación y calibración de los dos contaminantes bajo la etiqueta `interp`
#            (LOSO, LBO, LRO, LPO), SIN producir superficies
#   etapa 2  comparación contra lo definitivo y veredicto
#
# **La etapa 2 no produce nada: imprime los números y para.** La serie completa (~34 h) sólo se lanza
# después, a mano, si el LRO mejora. La regla se fija antes de ver el resultado: decide el **LRO**
# (dejar una región fuera), porque el defecto vive entre estaciones y el LOSO casi no lo ve.
#
# Se puede apagar el equipo en cualquier momento: cada etapa deja su marca y al relanzar el mismo
# comando se salta lo hecho; dentro de la etapa 1, los paneles y los modelos tienen su propio caché.
#
#   python -c "import subprocess,os; subprocess.Popen(['zsh','scripts_modelo_1km/experimento_interpolacion.sh'],
#     stdin=open(os.devnull), stdout=open('output_files/modelo_1km/interp_lanzador.log','ab'),
#     stderr=subprocess.STDOUT, start_new_session=True)"
set -u
RAIZ="${0:A:h:h}"
cd "$RAIZ" || exit 1
PY="${AFG_PYTHON:-$HOME/micromamba/envs/afg/bin/python}"
[[ -x "$PY" ]] || { echo "No existe $PY" >&2; exit 1; }
[[ -d /Volumes/Datos ]] || { echo "El disco externo /Volumes/Datos no está montado" >&2; exit 1; }
ETQ=interp
SALIDA="output_files/modelo_1km_$ETQ"; mkdir -p "$SALIDA"
REG="output_files/modelo_1km/interpolacion_$(date +%Y%m%dT%H%M%S).log"
echo "Registro: $REG"
{
  export QUARTO_PYTHON="$PY" PYTHONDONTWRITEBYTECODE=1
  export MODELO_1KM_ETIQUETA="$ETQ" MODELO_1KM_EXCLUIR="no2:dist_costa_km"
  export MODELO_1KM_INTERPOLAR=1
  export MODELO_1KM_LRO=1 MODELO_1KM_LPO=1 MODELO_1KM_LBO=1 MODELO_1KM_MOTORES_ML=""

  echo "== $(date '+%F %T') etapa 0: pesos y costuras"
  "$PY" -B scripts_modelo_1km/enlaces_interpolacion.py || exit 1
  [[ -e "$SALIDA/.etapa0_ok" ]] || { "$PY" -B scripts_modelo_1km/diagnostico_interpolacion.py && touch "$SALIDA/.etapa0_ok"; }

  echo "== $(date '+%F %T') etapa 1: paneles y calibración (los dos contaminantes)"
  if [[ ! -e "$SALIDA/.etapa1_ok" ]]; then
    caffeinate -i "$PY" -B scripts_modelo_1km/correr_qmd.py || { echo "== $(date '+%F %T') etapa 1 FALLÓ"; exit 1; }
    touch "$SALIDA/.etapa1_ok"
  fi

  echo "== $(date '+%F %T') etapa 2: veredicto"
  # El PM₂,₅ definitivo en disco es de una corrida anterior y sus LBO/LRO/LPO se recalcularon
  # después bajo otro código: comparar contra él mide la deriva del código, no el diseño. La
  # etiqueta no2sincosta es el control del mismo código y sirve además de par nulo para medir
  # cuánto mueve un reajuste sin cambio de diseño.
  "$PY" -B scripts_modelo_1km/comparar_etiquetas.py --etiqueta "$ETQ" \
      --base pm25:no2sincosta --nulo pm25:no2sincosta
  echo "== $(date '+%F %T') hasta aquí. La producción se lanza a mano si el LRO mejora."
} >> "$REG" 2>&1
