# scripts_superficie — pipeline local y extractores por estación

Todo lo que necesita el documento `others_files/20260902_informe_modelos_estimacion.qmd` se puede
producir **en esta máquina**, donde viven los datos crudos, sin copiar nada
a la nube. Dos piezas:

1. **`afg_lib.py` + `correr_pipeline.py`** — la librería del estudio (la
   misma que va embebida en el notebook) y un runner por consola: tabla de
   predictores → panel por contaminante → LOSO de los tres motores →
   protocolo del producto → series por nivel → figuras.
2. **`extractores/`** — scripts que llevan los productos ya descargados
   (TROPOMI, MAIAC 1 km, OMI, MOPITT, ERA5-Land) a series **por estación**
   chicas (`data/procesado_estacion/*.parquet`). `tabla_predictores()` las
   detecta y las integra sola: no hay que tocar los motores.

## 1. Entorno (una vez)

```bash
conda create -n afg python=3.11 -y && conda activate afg
pip install -r scripts_superficie/requirements.txt
brew install pngquant                          # opcional: comprime las figuras
```

La meteorología comunal y las covariables preprocesadas de Neuro se leen desde
`${ASESORIAS_DATA_ROOT}/AirPollution/derived/Neurodegen-Epidemiology-Chile/output_files`.
Se puede cambiar esa ubicación con `AIR_POLLUTION_DERIVED_ROOT` o, directamente,
con `AFG_NEURO_OUTPUT_ROOT`; `AFG_NEURO_ROOT` se conserva sólo por compatibilidad.

## 2. Extractores (correr una noche; todos son reanudables)

| Script | Entrada (ya descargada) | Salida por estación | Tiempo aprox. |
|---|---|---|---|
| `extraer_omi_estacion.py` | `OMI_L2/pixeles_pasada/**/*.parquet` (L2 13×24 km) | `omi_{no2,so2,o3}_estacion_pasadas.parquet` (candidatos, distancia y QA) | depende de cobertura |
| `extraer_mopitt_estacion.py` | `MOPITT_L2_CO/pixeles_pasada/**/*.parquet` (MOP02J ~22 km) | `mopitt_co_estacion_pasadas.parquet` (candidatos, perfil/error y QA) | depende de cobertura |
| `extraer_s5p_estacion.py` | recortes compactos TROPOMI L2 por AOI | maestro `s5p_<gas>_estacion_pixeles_nativos.parquet` + resúmenes `_derivado` | depende de cobertura |
| `extraer_maiac_estacion.py` | catálogos/observaciones Parquet de `MCD19A2.061/pixeles_horario/` | maestro píxel-estación + pasada exacta + hora derivada | depende de cobertura |
| `extraer_era5_estacion.py` | ERA5-Land 0,1° + ERA5 BLH 0,25° en `chile_nativo_*` | `era5land_estacion_horario.parquet` | depende de cobertura |
| `descargar_era5land.py` | API del CDS + máscara comunal versionada | grilla nativa horaria 0,1° de Chile, catálogo de píxeles y enlaces muchos-a-muchos a comunas; la tabla por estación es derivada | descarga prolongada; ~25–35 GB finales estimados para 2000–presente |
| `normalizar_era5_blh_chile.py` | ERA5 BLH histórico 0,25° | grilla nativa horaria BLH, sin interpolarla a 0,1° | ~1 GB final estimado |

Las tablas por estación de TROPOMI y ACAG son **derivados**, no sustituyen el
archivo píxel-nativo. Los `*.chile.nc` conservan todos los píxeles, la hora real
de observación cuando existe y los identificadores espaciales; cualquier media
dentro de un radio se calcula recién en el extractor. Para una unión auditable
sin promedio use primero `scripts_pipeline/crear_enlaces_pixeles.py`, que enlaza
huellas/píxeles con comunas y únicamente con el catálogo SINCA validado
`data/sinca/estaciones_georreferenciadas.csv`.

```bash
cd scripts_superficie/extractores
nohup python extraer_omi_estacion.py    > omi.log 2>&1 &
nohup python extraer_mopitt_estacion.py > mopitt.log 2>&1 &
nohup python extraer_s5p_estacion.py --procesos 4 > s5p.log 2>&1 &
nohup python extraer_maiac_estacion.py --procesos 4 > maiac.log 2>&1 &
# ERA5-Land: primero configurar ~/.cdsapirc (ver docstring del script).
# Descarga -> recorte administrativo -> validación/hash -> limpieza de crudos.
python descargar_era5land.py
# Sólo después de que la descarga anterior termine: validar el plan y retirar
# los rectángulos mensuales heredados ya sustituidos.
python ../../scripts_pipeline/retirar_legado_era5land.py --dry-run
python ../../scripts_pipeline/retirar_legado_era5land.py
```

Si un script se interrumpe, se vuelve a lanzar y continúa desde el cache
(`data/procesado_estacion/_cache/`).

## 3. Pipeline completo

```bash
# recalcula todo con los predictores nuevos (respalda las métricas anteriores en output_files/_bak)
python scripts_superficie/correr_pipeline.py --fresh
# luego el documento
quarto render others_files/20260902_informe_modelos_estimacion.qmd
```

Tiempos de referencia (Mac Apple Silicon, 6 contaminantes): predictores
~5 min, paneles ~1–2 min c/u, LOSO 15–50 min c/u (LightGBM domina),
figuras ~5 min. Total ≈ 2–4 h. Se puede acotar con `--pols so2 co`.

Qué queda versionado en `output_files/` para reconstruir el HTML sin
recomputar: `metricas_cv_*.json`, `metricas_producto_*.json`,
`comparacion_motores_*.csv`, `importancias_*.csv`, `r2_estacion_*.csv`,
`acuerdo_niveles_*.csv`, `serie_mensual_*.csv`, `resumen_predictores.csv` y
`figures/*.png`. Los parquet pesados (predictores, paneles, OOF) son caché
local.

## 4. Fuentes puntuales de SO₂

`data/fuentes_so2.csv` lista las megafuentes (fundiciones, termoeléctricas,
refinerías) con coordenadas y un **peso relativo de emisión** (orden de
magnitud). De ahí salen `dist_fuente_km`, `carga_fuentes_so2` (Σ E/d²) y
`viento_fuentes_so2` (alineación horaria del viento fuente → estación).
Para refinar: reemplazar `peso_so2` por toneladas/año del RETC
(https://retc.mma.gob.cl) y volver a correr con `--fresh --pols so2`.

## 5. Cómo entran las variables nuevas

`tabla_predictores()` busca en `data/procesado_estacion/`:
`*_estacion_diario.parquet` (una columna por producto; cada hora del día
hereda el valor diario y el boosting aprende la modulación con la hora) y
`*_estacion_horario.parquet` (se unen por estación × hora UTC). El
LightGBM toma toda columna con prefijo `s5p_`, `omi_`, `mop_`, `era5_` o
`aod_maiac_est` con cobertura > 30 %. La figura de importancias les asigna
nombre legible y fuente automáticamente.

OMI/MOPITT L2 se guardan primero como `*_estacion_pasadas.parquet`: una fila
por candidato nativo, con distancia y QA. No se incorporan automáticamente a
cada hora ni se promedian en el extractor; la regla de selección/agregación
debe definirse y versionarse como parte del modelo para evitar fuga temporal o
una falsa resolución horaria.
