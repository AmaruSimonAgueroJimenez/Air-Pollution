#!/bin/zsh
# Rehace la calibración definitiva con la corrección de retransformación vigente y reescala las
# superficies ya publicadas, sin volver a predecir.
#
#   fase 1  correr_qmd.py sobre la etiqueta definitiva: reutiliza los pliegues en caché (la firma no
#           incluye la retransformación) y sólo recalcula las predicciones en escala física, las
#           métricas y las tablas de evaluación. De paso rehace el eval de PM₂,₅, que en disco era de
#           una corrida anterior.
#   fase 2  aplicar_retransformacion.py: reescala los NetCDF publicados de los tres ámbitos. Un día ya
#           convertido se salta, así que es reanudable y se puede apagar el equipo.
#   fase 3  exposición por ámbito. El análisis agudo, sus figuras y los manuscritos se re-ejecutan en el
#           repositorio Air-Pollution-Health-Chile.
#
# Sin interpolación: el experimento la descartó (ver el veredicto del 2026-10-02).
# La fase 1 tarda unas 3-4 h porque calcula los seis motores de aprendizaje que le faltan al NO₂;
# los de PM₂,₅ se reutilizan. Todo es reanudable por pliegue.
set -u
RAIZ="${0:A:h:h}"
cd "$RAIZ" || exit 1
PY="${AFG_PYTHON:-$HOME/micromamba/envs/afg/bin/python}"
[[ -x "$PY" ]] || { echo "No existe $PY" >&2; exit 1; }
[[ -d /Volumes/Datos ]] || { echo "El disco externo /Volumes/Datos no está montado" >&2; exit 1; }
if pgrep -f "scripts_modelo_1km/correr_qmd.py" >/dev/null; then
  echo "Ya hay una corrida del modelo en marcha" >&2; exit 1
fi
SALIDA="output_files/modelo_1km"; mkdir -p "$SALIDA"
REG="$SALIDA/retransformacion_$(date +%Y%m%dT%H%M%S).log"
echo "Registro: $REG"
{
  export QUARTO_PYTHON="$PY" PYTHONDONTWRITEBYTECODE=1
  unset MODELO_1KM_ETIQUETA MODELO_1KM_INTERPOLAR
  export MODELO_1KM_EXCLUIR="no2:dist_costa_km"
    # Los motores de aprendizaje van ENCENDIDOS a propósito. Con la lista vacía, `motores_ml` no publica
  # nada pero `eval_motores_<pol>.csv` se rehace sólo con los motores lineales: así se perdieron los seis
  # de NO₂ el 2026-09-30, y lo mismo le pasaría ahora a PM₂,₅. Encendidos, PM₂,₅ reutiliza su
  # `oof_ml.parquet` (la identidad coincide) y sólo se calculan los de NO₂, que faltaban.
  export MODELO_1KM_LRO=1 MODELO_1KM_LPO=1 MODELO_1KM_LBO=1
  export MODELO_1KM_MOTORES_ML="alertas,rf,nn,gp,lme"
  M="$SALIDA/.refresco_retransf"; mkdir -p "$M"
  echo "== $(date '+%F %T') fase 1: calibración con la retransformación vigente"
  if [[ ! -e "$M/fase1_ok" ]]; then
    caffeinate -i "$PY" -B scripts_modelo_1km/correr_qmd.py || { echo "== fase 1 FALLÓ"; exit 1; }
    touch "$M/fase1_ok"
  else
    echo "   ya hecha"
  fi
  echo "== $(date '+%F %T') fase 2: reescalado de las superficies de NO₂"
  caffeinate -i "$PY" -B scripts_modelo_1km/aplicar_retransformacion.py --contaminantes no2 \
      --ambitos nacional,rm,biobio || { echo "== fase 2 FALLÓ"; exit 1; }
  # Control: ningún día puede quedar declarando el método nuevo sin haber pasado por un factor distinto
  # de uno; el reescalado del 2026-10-02 dejó 1.340 así y no avisó.
  "$PY" - <<'PYX' || { echo "== control de fase 2 FALLÓ"; exit 1; }
import sys, json
from collections import Counter
sys.path.insert(0, "scripts_modelo_1km")
from _comun_modelo import SUPERFICIES_ROOT, carpeta_ambito
malos = 0
for amb in ("nacional", "rm", "biobio"):
    c = Counter(json.loads(j.read_text()).get("retransformacion")
                for j in (carpeta_ambito(SUPERFICIES_ROOT, "superficies", "", amb) / "no2").rglob("no2_1km_*.json"))
    print(f"   {amb}: {dict(c)}")
    malos += sum(v for k, v in c.items() if k != "duan_oof_macrozona")
sys.exit(1 if malos else 0)
PYX
  echo "== $(date '+%F %T') fase 3: exposición"
  for AMB in nacional rm biobio; do
    caffeinate -i "$PY" -B scripts_modelo_1km/exposicion.py --ambito "$AMB" --contaminantes no2 --ventanas 2 \
      || { echo "== exposición $AMB FALLÓ"; exit 1; }
  done
  echo "== $(date '+%F %T') listo"
} >> "$REG" 2>&1
