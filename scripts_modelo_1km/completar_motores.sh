#!/bin/zsh
# Repone los motores de aprendizaje que faltan, bajo el diseño que esté vigente.
#
# El reajuste de NO₂ sin distancia a la costa (2026-10-01) corrió con MODELO_1KM_MOTORES_ML="" para no
# pagar seis horas de motores que no decidían nada, y al reemplazar la carpeta del modelo se llevó
# consigo oof_ml.parquet de NO₂: hoy eval_motores_no2.csv tiene cuatro motores (lgbm, gwr, rk, idw) y
# el de PM₂,₅ tiene los diez. La comparación de motores (eval_motores_<pol>.csv) necesita los diez en los dos gases.
#
# Lo mismo hará falta si gana la interpolación: el panel cambia y los motores hay que repetirlos.
#
#   MODELO_1KM_ETIQUETA=...  (vacío = el definitivo)
#   MODELO_1KM_EXCLUIR / MODELO_1KM_INTERPOLAR deben ser los del diseño vigente, o las métricas de los
#   motores no serán comparables con las de LightGBM.
#
# Unas 6 h 45 por los dos contaminantes (medido el 2026-09-20: alertas 2 h 35, RF 3 h 14, MLP 16 min,
# GP 34 min, mixto 4 min). Reanudable: cada pliegue de cada motor deja su punto de control en
# modelos/<pol>/pliegues/<protocolo>_<motor>/, así que se puede apagar el equipo.
#
#   python -c "import subprocess,os; subprocess.Popen(['zsh','scripts_modelo_1km/completar_motores.sh'],
#     stdin=open(os.devnull), stdout=open('output_files/modelo_1km/motores_lanzador.log','ab'),
#     stderr=subprocess.STDOUT, start_new_session=True)"
set -u
RAIZ="${0:A:h:h}"
cd "$RAIZ" || exit 1
PY="${AFG_PYTHON:-$HOME/micromamba/envs/afg/bin/python}"
[[ -x "$PY" ]] || { echo "No existe $PY" >&2; exit 1; }
[[ -d /Volumes/Datos ]] || { echo "El disco externo /Volumes/Datos no está montado" >&2; exit 1; }
if pgrep -f "scripts_modelo_1km/correr_qmd.py" >/dev/null; then
  echo "Ya hay una corrida del modelo en marcha; esperar a que termine" >&2; exit 1
fi
REG="output_files/modelo_1km/motores_$(date +%Y%m%dT%H%M%S).log"
echo "Registro: $REG"
{
  export QUARTO_PYTHON="$PY" PYTHONDONTWRITEBYTECODE=1
  export MODELO_1KM_MOTORES_ML="alertas,rf,nn,gp,lme"
  export MODELO_1KM_LRO=1 MODELO_1KM_LPO=1 MODELO_1KM_LBO=1
  echo "== $(date '+%F %T') motores de aprendizaje, etiqueta '${MODELO_1KM_ETIQUETA:-definitivo}'"
  echo "   excluir='${MODELO_1KM_EXCLUIR:-}'  interpolar='${MODELO_1KM_INTERPOLAR:-}'"
  caffeinate -i "$PY" -B scripts_modelo_1km/correr_qmd.py || { echo "== $(date '+%F %T') FALLÓ"; exit 1; }
  echo "== $(date '+%F %T') listo; motores por contaminante:"
  "$PY" - <<'PYX'
import pandas as pd, pathlib
for pol in ("pm25", "no2"):
    f = pathlib.Path(f"output_files/modelo_1km/eval_motores_{pol}.csv")
    if f.exists():
        d = pd.read_csv(f)
        g = d[(d.tabla == "nivel") & (d.protocolo == "loso") & (d.estrato == "diario")]
        print(f"  {pol}: {len(set(g.motor))} motores -> {sorted(set(g.motor))}")
PYX
} >> "$REG" 2>&1
