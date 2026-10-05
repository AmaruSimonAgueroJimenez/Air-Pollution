#!/bin/zsh
# Produce las superficies horarias de 1 km de toda la serie (2000-01-01 → 2026-09-13), en paralelo.
#
#   zsh scripts_modelo_1km/lanzar_produccion_serie.sh            # en primer plano
#   nohup zsh scripts_modelo_1km/lanzar_produccion_serie.sh &    # desacoplada del terminal
#
# **Desacoplarla de verdad.** Lanzada desde un agente o un terminal que después se cierra, la corrida
# muere con él y hay que relanzarla a mano. Para que sobreviva necesita su propia sesión de proceso:
#
#   python -c "import subprocess,os; subprocess.Popen(['zsh','scripts_modelo_1km/lanzar_produccion_serie.sh'], \
#     stdin=open(os.devnull), stdout=open('output_files/modelo_1km/lanzador_desacoplado.log','ab'), \
#     stderr=subprocess.STDOUT, start_new_session=True)"
#
# Se comprueba con `ps -o pid,ppid,pgid -p <pid>`: el padre tiene que ser 1, no el terminal. Con
# `nohup ... &` a secas no siempre basta, porque el proceso sigue en el grupo del que lo lanzó.
#
# **Se puede apagar el equipo cuando sea.** Cada día se publica entero o no se publica: el NetCDF se
# escribe en `.part` y sólo al cerrarse se renombra y se escribe su manifiesto. Relanzar este mismo
# script continúa donde quedó, saltando en milisegundos los días ya publicados. Lo que se pierde al
# apagar es, como mucho, el día que estuviera a medio calcular.
#
# Recorre los ámbitos en orden: primero la Región Metropolitana, después Biobío y Ñuble, y al final
# todo Chile; dentro de cada ámbito produce primero los años pares (los de los mapas cada dos años) y
# después el resto. Cada ámbito escribe en su propia carpeta, así que ninguno pisa a otro, y al
# terminar cada uno se agregan sus métricas de exposición: hay mapas de la RM en un par de horas sin
# esperar las ~34 h de la serie nacional. `MODELO_1KM_AMBITOS` cambia la lista o su orden.
# Argumentos extra se pasan tal cual a producir_serie.py (p. ej. `--anios 2024`, `--procesos 4`).
#
# Estado en cualquier momento:
#   python -B scripts_modelo_1km/producir_serie.py --ambito rm --solo-estado
#   python -B scripts_modelo_1km/exposicion.py --ambito rm --solo-estado
set -u
RAIZ="${0:A:h:h}"
cd "$RAIZ" || exit 1
PY="${AFG_PYTHON:-$HOME/micromamba/envs/afg/bin/python}"
if [[ ! -x "$PY" ]]; then
  echo "No existe $PY; define AFG_PYTHON con el Python del entorno afg" >&2
  exit 1
fi
# Los predictores nativos (ERA5-Land, CAMS, MERRA-2, GEOS-CF, MAIAC, TROPOMI) viven en el disco externo.
if [[ ! -d /Volumes/Datos ]]; then
  echo "El disco externo /Volumes/Datos no está montado: los predictores nativos no se pueden leer" >&2
  exit 1
fi
export PYTHONDONTWRITEBYTECODE=1
PROCESOS="${MODELO_1KM_PROCESOS_PRODUCCION:-6}"
AMBITOS="${MODELO_1KM_AMBITOS:-rm biobio nacional}"
SALIDA="output_files/modelo_1km${MODELO_1KM_ETIQUETA:+_$MODELO_1KM_ETIQUETA}"
mkdir -p "$SALIDA"
REGISTRO="$SALIDA/produccion_$(date +%Y%m%dT%H%M%S).log"
echo "Registro: $REGISTRO  (avance fino: $SALIDA/produccion_serie.log)"
echo "Estado:   $PY -B scripts_modelo_1km/producir_serie.py --solo-estado"
{
  for AMB in ${=AMBITOS}; do
    echo "== $(date '+%F %T') ámbito $AMB, $PROCESOS procesos $*"
    caffeinate -i "$PY" -B scripts_modelo_1km/producir_serie.py --ambito "$AMB" --procesos "$PROCESOS" "$@"
    COD=$?   # se guarda antes de cualquier otra expansión: $(date ...) pisaría $? con su propio estado
    echo "== $(date '+%F %T') ámbito $AMB terminó con código $COD"
    if [[ $COD -ne 0 ]]; then
      echo "== se detiene la cadena: $AMB no terminó bien"
      break
    fi
    echo "== $(date '+%F %T') métricas de exposición de $AMB"
    caffeinate -i "$PY" -B scripts_modelo_1km/exposicion.py --ambito "$AMB" --ventanas 2
    echo "== $(date '+%F %T') exposición de $AMB terminó con código $?"
  done
} > "$REGISTRO" 2>&1
