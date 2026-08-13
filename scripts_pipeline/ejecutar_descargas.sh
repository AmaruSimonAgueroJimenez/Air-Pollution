#!/usr/bin/env bash
# ejecutar_descargas.sh — corre todos los descargadores con log de estado y
# reintentos automáticos cada ESPERA segundos (2 min por defecto).
#
# Uso:
#   bash ejecutar_descargas.sh                                 # todo, 2019→2024
#   DESDE=2019-01-01 HASTA=2024-12-31 bash ejecutar_descargas.sh
#   SOLO=descargar_sinca.py,descargar_omi.py bash ejecutar_descargas.sh
#
# Logs (en ../logs/):
#   estado.txt        resumen vivo por fuente (ábrelo para ver el estado)
#   estado.log        cronológico de intentos/OK/fallos
#   <script>.log      salida completa de cada descargador
# Control:
#   touch ../logs/DETENER   → detiene limpio (revisa cada ~30 s, incluso a
#                             mitad de una descarga larga); bórralo para relanzar
#
# Notas de operación:
#   - Usa caffeinate para que el Mac no se duerma (conéctalo a la corriente;
#     con la tapa cerrada y sin pantalla externa igual se duerme).
#   - NO cierres la sesión de usuario de macOS: logout mata el proceso aunque
#     use nohup. Bloquear la pantalla sí es seguro.
#   - Solo puede correr una instancia a la vez (candado en ~/.air_pollution_descargas.pid).
#
# Ajustes por entorno: ESPERA (s entre reintentos), MAX_INTENTOS por fuente,
# MIN_GB_LIBRES (aborta si el disco baja de ese umbral), PYTHON.
set -u
cd "$(dirname "$0")"

# aserción de energía: sin esto, el sleep de macOS congela la corrida
if command -v caffeinate >/dev/null 2>&1; then
  caffeinate -i -s -w $$ &
fi

DESDE="${DESDE:-2019-01-01}"
HASTA="${HASTA:-2024-12-31}"
PY="${PYTHON:-python3}"
ESPERA="${ESPERA:-120}"
MAX_INTENTOS="${MAX_INTENTOS:-10}"
MIN_GB_LIBRES="${MIN_GB_LIBRES:-50}"
SOLO="${SOLO:-}"

LOGDIR="$(cd .. && pwd)/logs"
mkdir -p "$LOGDIR"
ESTADO_LOG="$LOGDIR/estado.log"
RESUMEN="$LOGDIR/estado.txt"

# Fuentes en orden liviano → pesado (las L2 satelitales, que pesan cientos de
# GB, van al final para tener antes lo esencial).
FUENTES=(
  "descargar_sinca.py --desde $DESDE --hasta $HASTA --resolucion horario"
  "descargar_acag_pm25.py --temporal annual"
  "descargar_omi.py --desde $DESDE --hasta $HASTA --contaminantes no2,o3,so2"
  "descargar_mopitt.py --desde $DESDE --hasta $HASTA"
  "descargar_cams_eac4.py --desde $DESDE --hasta $HASTA"
  "descargar_geoscf.py --desde $DESDE --hasta $HASTA"
  "descargar_merra2_aer.py --desde $DESDE --hasta $HASTA"
  # solo NO2: es el gas donde TROPOMI (~5.5 km) aporta detalle que ninguna otra
  # fuente da. O3/SO2/CO quedan cubiertos por OMI, MOPITT, CAMS y GEOS-CF, y los
  # cuatro gases juntos no caben en disco (~975 GB)
  "descargar_tropomi.py --desde $DESDE --hasta $HASTA --contaminantes no2"
  "descargar_maiac_aod.py --desde $DESDE --hasta $HASTA"
  "descargar_modis_aod.py --desde $DESDE --hasta $HASTA"
)

NOMBRES=(); ESTADOS=()
for i in "${!FUENTES[@]}"; do
  NOMBRES[$i]="${FUENTES[$i]%% *}"
  ESTADOS[$i]="· pendiente"
done

log_estado() { printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$ESTADO_LOG"; }

escribir_resumen() {
  # OJO: en bash las variables de función son globales; sin `local`, el bucle
  # de abajo pisaría el índice `i` del bucle principal (y el reintento
  # ejecutaría la fuente equivocada).
  local j
  {
    echo "== Estado de descargas · actualizado $(date '+%Y-%m-%d %H:%M:%S') =="
    echo "rango: $DESDE -> $HASTA | reintento cada ${ESPERA}s | max ${MAX_INTENTOS} intentos/fuente"
    echo "para detener: touch $LOGDIR/DETENER"
    echo
    for j in "${!NOMBRES[@]}"; do
      printf '%-26s %s\n' "${NOMBRES[$j]}" "${ESTADOS[$j]}"
    done
  } > "$RESUMEN.tmp" && mv "$RESUMEN.tmp" "$RESUMEN"
}

gb_libres() { df -g "$LOGDIR" | awk 'NR==2{print $4}'; }

hay_que_detener() {
  if [ -e "$LOGDIR/DETENER" ]; then
    log_estado "== DETENIDO por $LOGDIR/DETENER (bórralo para poder relanzar)"
    escribir_resumen
    exit 0
  fi
}

# candado anti doble instancia (fuera de la carpeta sincronizada con Drive)
PIDFILE="$HOME/.air_pollution_descargas.pid"
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Ya hay una instancia corriendo (pid $(cat "$PIDFILE")); aborto." >&2
  exit 3
fi
echo $$ > "$PIDFILE"
CHILD=""
trap 'rm -f "$PIDFILE" "$RESUMEN.tmp"' EXIT
trap '[ -n "$CHILD" ] && kill "$CHILD" 2>/dev/null; log_estado "== INTERRUMPIDO por señal =="; escribir_resumen; exit 130' INT TERM

log_estado "== INICIO pipeline $DESDE -> $HASTA (pid $$) =="
escribir_resumen
FALLOS=0

for i in "${!FUENTES[@]}"; do
  script="${NOMBRES[$i]}"
  if [ -n "$SOLO" ]; then
    case ",$SOLO," in
      *",$script,"*) ;;
      *) ESTADOS[$i]="~ omitida (SOLO=$SOLO)"; escribir_resumen; continue ;;
    esac
  fi
  LOGF="$LOGDIR/${script%.py}.log"
  intento=1
  while :; do
    hay_que_detener
    libres="$(gb_libres)"
    if [ "${libres:-0}" -lt "$MIN_GB_LIBRES" ]; then
      log_estado "XX ABORTADO: quedan ${libres} GB libres (umbral ${MIN_GB_LIBRES} GB)"
      ESTADOS[$i]="X abortada por disco lleno (${libres} GB libres)"
      escribir_resumen
      exit 2
    fi
    ESTADOS[$i]="> EN CURSO (intento $intento/$MAX_INTENTOS, desde $(date '+%H:%M'))"
    escribir_resumen
    log_estado ">> $script intento $intento/$MAX_INTENTOS"
    if [ "$(stat -f%z "$LOGF" 2>/dev/null || echo 0)" -gt 209715200 ]; then
      mv "$LOGF" "$LOGF.1"   # rota logs de más de 200 MB
    fi
    printf '\n===== %s · intento %s · %s =====\n' "$script" "$intento" "$(date '+%Y-%m-%d %H:%M:%S')" >> "$LOGF"
    "$PY" -u ${FUENTES[$i]} >> "$LOGF" 2>&1 &
    CHILD=$!
    # vigila al hijo: permite que DETENER surta efecto aun a mitad de descarga
    while kill -0 "$CHILD" 2>/dev/null; do
      if [ -e "$LOGDIR/DETENER" ]; then
        kill "$CHILD" 2>/dev/null
        wait "$CHILD" 2>/dev/null
        ESTADOS[$i]="~ interrumpida por DETENER $(date '+%d/%m %H:%M')"
        log_estado "== DETENIDO por $LOGDIR/DETENER durante $script (bórralo para poder relanzar)"
        escribir_resumen
        exit 0
      fi
      sleep 30
    done
    if wait "$CHILD"; then
      ESTADOS[$i]="OK terminada $(date '+%d/%m %H:%M') (intentos: $intento)"
      log_estado "OK $script"
      escribir_resumen
      break
    fi
    if [ "$intento" -ge "$MAX_INTENTOS" ]; then
      ESTADOS[$i]="X FALLO tras $MAX_INTENTOS intentos — revisa ${script%.py}.log"
      log_estado "XX $script agoto los $MAX_INTENTOS intentos; sigo con la siguiente fuente"
      escribir_resumen
      FALLOS=$((FALLOS + 1))
      break
    fi
    ESTADOS[$i]="~ fallo intento $intento; reintento a las $(date -v +${ESPERA}S '+%H:%M:%S')"
    log_estado "!! $script fallo (intento $intento); reintento en ${ESPERA}s"
    escribir_resumen
    intento=$((intento + 1))
    sleep "$ESPERA"
  done
done

log_estado "== FIN pipeline (fuentes fallidas: $FALLOS) =="
escribir_resumen
[ "$FALLOS" -eq 0 ] || exit 1
