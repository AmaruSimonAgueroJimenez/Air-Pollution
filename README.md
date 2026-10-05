# Air-Pollution

Modelos de estimación de la contaminación del aire en Chile. El repositorio reúne el código, la
configuración y los informes que estiman la concentración en superficie de PM2.5, PM10, NO2, O3, SO2 y CO
a partir de satélites, reanálisis y monitores de tierra (la red SINCA y una red adicional publicada en
SNIFA).

Aquí está sólo la estimación de la exposición. El uso de estas estimaciones en salud vive en otro
repositorio (ver [Relación con Air-Pollution-Health-Chile](#relación-con-air-pollution-paper)).

## Qué contiene

| Parte | Dónde | Qué hace |
| --- | --- | --- |
| Fuentes de datos | `scripts_pipeline/`, `config/` | Descarga y prepara cada fuente en su resolución nativa: SINCA y la red adicional SNIFA, Sentinel-5P TROPOMI, OMI, MOPITT, MODIS MAIAC y AOD de 3 km, GOES-East ABI, ERA5 y ERA5-Land, MERRA-2, CAMS EAC4, GEOS-CF, ACAG, luces nocturnas (DMSP y VIIRS Black Marble), uso de suelo ESA CCI y topografía NASADEM. |
| Superficies multi-contaminante | `scripts_superficie/` | Modelos por estación y hora de los seis contaminantes, 2019 a 2024, con GWR, regression-kriging y LightGBM, validados dejando una estación fuera (LOSO). Los extractores por estación están en `scripts_superficie/extractores/`. |
| Modelo horario de 1 km | `scripts_modelo_1km/`, `docs/modelo_1km_horario.qmd` | PM2.5 (µg/m³) y NO2 (ppb) cada hora en las 838.430 celdas de 0,01° que tocan Chile, del 2000-01-01 al 2026-09-13. LightGBM es el motor del producto; nueve motores más se evalúan como contraste. Validación fuera de estación (LOSO, LBO, LRO y LPO), superficies NetCDF diarias y métricas de exposición por celda. |
| Extractores anteriores | `scripts_estacion/` | Primera versión de los extractores por estación. Tres de ellos ya son sólo puentes a los de `scripts_superficie/extractores/`. |

## Estructura

```
scripts_pipeline/     descarga y preparación de todas las fuentes, con sus pruebas (tests/)
scripts_superficie/   superficies multi-contaminante (afg_lib.py, correr_pipeline.py) y extractores/
scripts_modelo_1km/   librería, producción, exposición y diagnósticos del modelo de 1 km, con tests/
scripts_estacion/     extractores por estación de la primera versión
config/               catálogos versionados: estaciones y política temporal SINCA, red adicional SNIFA
docs/                 informe del modelo de 1 km, notas técnicas de las fuentes, index.html y references/
output_files/         resultados chicos y figuras de las superficies y del modelo de 1 km
others_files/         material archivado con nombre AAAAMMDD_tipo_nombre, con su índice README.md
others_scripts/       generar_indice_docs.py (regenera docs/index.html y others_files/README.md) y
                      aligerar_html.py (figuras del informe HTML en paleta de 256 colores)
presentaciones/       presentaciones, guiones y videos de avance del proyecto
data                  enlace simbólico a los datos crudos en el disco externo (no se versiona)
logs/                 bitácoras locales del pipeline de descarga (no se versiona)
```

## Datos

Nada pesado vive en el repositorio.

- **Datos crudos.** `data` es un enlace simbólico a `/Volumes/Datos/Asesorias_Data/AirPollution/data`:
  una carpeta por producto en `contaminantes/`, la verdad de terreno en `sinca/` y `snifa_adicional/`, y
  los insumos geográficos (`comunas.shp`, `lulc/`, `osm/`, `shapefiles_regiones/`). Los scripts ubican esa
  raíz con `AIR_POLLUTION_DATA_ROOT` o, si no está definida, con `$ASESORIAS_DATA_ROOT/AirPollution/data`.
  Con la ruta por omisión y el disco sin montar, los descargadores se detienen antes de escribir.
- **Derivados.** SINCA y ERA5-Land preparados para el modelado quedan junto a los crudos, en
  `$ASESORIAS_DATA_ROOT/AirPollution/derived/` (`AIR_POLLUTION_DERIVED_ROOT` los reubica). Ahí también
  está la meteorología comunal del proyecto hermano de neuroepidemiología que leen las superficies
  multi-contaminante (`derived/Neurodegen-Epidemiology-Chile/output_files`, reubicable con
  `AFG_NEURO_OUTPUT_ROOT`).
- **Salidas del modelo de 1 km.** Grilla, covariables estáticas, paneles, modelos, predicciones fuera de
  muestra, superficies NetCDF y métricas de exposición van al disco interno, en
  `~/Asesorias_Data_local/AirPollution/modelado_1km/`, fuera del repositorio.
  `AIR_POLLUTION_MODELO_1KM_ROOT` cambia esa raíz y `AIR_POLLUTION_SUPERFICIES_ROOT` sólo la de las
  superficies. El modelo sólo lee del disco externo; nunca escribe en él.
- **En el repositorio** quedan los resultados chicos y las figuras: los CSV y JSON de la raíz de
  `output_files/` y `output_files/figures/` (superficies multi-contaminante), `output_files/modelo_1km/`
  (tablas `eval_*` y `desc_*`, métricas, bitácoras y figuras del modelo de 1 km) y
  `output_files/modelo_1km_<etiqueta>/` para las corridas con etiqueta (`interp`, `no2sincosta`,
  `previoenlace`, `prueba`, `smoke`).
- El HTML del informe del modelo, `docs/modelo_1km_horario.html`, es autocontenido y se versiona. Tal
  como sale de Quarto supera el límite de 100 MB por archivo de GitHub; `others_scripts/aligerar_html.py`
  reescribe sus figuras incrustadas con una paleta de 256 colores y lo deja bajo 50 MB, sin tocar los
  PNG de `output_files/`. El informe no tiene versión PDF vigente.
- Las credenciales van en `.env`, que no se versiona; la plantilla es `.env.example`.

## Entorno

- **Descargas.** `pip install -r scripts_pipeline/requirements.txt` y `cp .env.example .env` con las
  credenciales de NASA Earthdata, Copernicus CDS y Copernicus ADS. SINCA, GEOS-CF, ACAG, GOES-East y las
  luces DMSP no piden cuenta. La preparación para modelado y la red SNIFA tienen sus propias versiones
  fijadas: `scripts_pipeline/requirements-modelado.txt` y `scripts_pipeline/requirements-snifa.txt`.
- **Modelos.** Python 3.11 con `scripts_superficie/requirements.txt` y
  `scripts_modelo_1km/requirements.txt` (LightGBM, scikit-learn, statsmodels, lleaves, geopandas,
  netCDF4, Jupyter). Los lanzadores del modelo usan `$AFG_PYTHON` o, si no está definida,
  `~/micromamba/envs/afg/bin/python`.
- **Informes.** Quarto, con `QUARTO_PYTHON` apuntando a ese mismo Python.

## Cómo correr

Todos los comandos van desde la raíz del repositorio.

### Descargas y preparación

```bash
bash scripts_pipeline/lanzar_descargas.sh        # todas las fuentes, en orden, de 2000-01-01 a hoy
DESDE=2019-01-01 HASTA=2024-12-31 bash scripts_pipeline/ejecutar_descargas.sh   # con reintentos; estado en logs/estado.txt
bash scripts_pipeline/ejecutar_snifa.sh          # red adicional SNIFA, historial completo
python scripts_pipeline/descargar_sinca.py --limite 3 --dry-run                  # un descargador suelto, sin bajar nada
python3 -B scripts_pipeline/preparar_datos_modelado.py --merra-hasta 2026-05 --sinca-hasta 2026-09-13 --era-hasta 2026-09
```

Los descargadores aceptan `--desde`, `--hasta` y `--dry-run`. `preparar_datos_modelado.py` sólo muestra
el plan; con `--ejecutar` lo aplica. Productos, identificadores verificados, coberturas y límites de cada
fuente: [`scripts_pipeline/README.md`](scripts_pipeline/README.md).

### Superficies multi-contaminante

```bash
python scripts_superficie/correr_pipeline.py                  # seis contaminantes, usa la caché
python scripts_superficie/correr_pipeline.py --pols so2 co    # sólo algunos
python scripts_superficie/correr_pipeline.py --fresh          # borra la caché pesada y recalcula
quarto render others_files/20260902_informe_modelos_estimacion.qmd
```

Extractores por estación, tiempos y archivos que se versionan:
[`scripts_superficie/README.md`](scripts_superficie/README.md).

### Modelo horario de 1 km

```bash
python -B scripts_modelo_1km/tests/test_modelo_1km.py     # pruebas herméticas de la librería
zsh scripts_modelo_1km/lanzar_corrida_completa.sh         # panel, validación, modelos finales e informe HTML
zsh scripts_modelo_1km/lanzar_produccion_serie.sh         # superficies 2000-2026 y exposición por ámbito
python -B scripts_modelo_1km/producir_serie.py --ambito rm --solo-estado
python -B scripts_modelo_1km/exposicion.py --ambito rm --solo-estado
```

- `lanzar_corrida_completa.sh` ejecuta los chunks de `docs/modelo_1km_horario.qmd` fuera de Quarto
  (con `correr_qmd.py`, en `scripts_modelo_1km/`) y después renderiza el HTML. Toma horas y es
  reanudable: cada artefacto y cada pliegue de la validación se guardan al terminar.
- `lanzar_produccion_serie.sh` produce la serie completa en tres ámbitos, primero la Región
  Metropolitana, después Biobío con Ñuble y al final todo Chile, y agrega las métricas de exposición de
  cada uno al terminarlo. Cada día se publica entero o no se publica, así que se puede apagar el equipo
  y relanzar el mismo comando. La serie nacional toma unas 34 horas.
- Las bitácoras quedan en `output_files/modelo_1km/` (`corrida_<fecha>.log`, `produccion_<fecha>.log`);
  el avance fino, en `modelo_1km.log` y `produccion_serie.log` de esa misma carpeta.

Para rearmar sólo el informe con todo en caché:

```bash
cd docs
export QUARTO_PYTHON=~/micromamba/envs/afg/bin/python
MODELO_1KM_LRO=1 MODELO_1KM_LPO=1 MODELO_1KM_LBO=1 quarto render modelo_1km_horario.qmd
cd .. && python -B others_scripts/aligerar_html.py docs/modelo_1km_horario.html
```

Quarto se lanza desde `docs/`: desde la raíz, `embed-resources` con `--output` falla al empaquetar el
HTML. Sin `MODELO_1KM_LRO`, `MODELO_1KM_LPO` y `MODELO_1KM_LBO` en 1 el render reescribe las predicciones
fuera de muestra de los motores de contraste sólo con LOSO. `aligerar_html.py` deja el HTML bajo 50 MB
para que se pueda versionar.

Variables más usadas: `MODELO_1KM_ETIQUETA` (corrida aparte que no pisa la definitiva),
`MODELO_1KM_DESDE` y `MODELO_1KM_HASTA`, `MODELO_1KM_MOTORES_ML` (motores de contraste),
`MODELO_1KM_EXCLUIR` (por omisión `no2:dist_costa_km`) y `MODELO_1KM_AMBITOS` (ámbitos y orden de la
producción). El contrato del producto, las decisiones, los costos medidos y los resultados están en
[`scripts_modelo_1km/README.md`](scripts_modelo_1km/README.md).

Cadenas de mantenimiento del modelo, todas reanudables:

| Lanzador | Qué hace |
| --- | --- |
| `scripts_modelo_1km/reajuste_no2.sh` | Reajusta el NO2 sin la distancia a la costa (etiqueta `no2sincosta`), lo hace pasar por una compuerta de R² y lo promueve a definitivo con respaldo. |
| `scripts_modelo_1km/refrescar_retransformacion.sh` | Recalibra con la corrección de retransformación vigente y reescala las superficies publicadas sin volver a predecir. |
| `scripts_modelo_1km/experimento_interpolacion.sh` | Prueba la interpolación bilineal de los reanálisis gruesos (etiqueta `interp`) sin producir superficies; la descartó el veredicto del 2026-10-02. |
| `scripts_modelo_1km/completar_motores.sh` | Repone los motores de contraste que falten bajo el diseño vigente. |

## Producto del modelo de 1 km

Un NetCDF por día y contaminante con las 24 horas UTC:
`superficies/<pol>/year=AAAA/month=MM/<pol>_1km_AAAAMMDD.nc`, más un JSON con sus hashes. Las
superficies regionales van en `superficies_rm/` y `superficies_biobio/`, y las métricas de exposición
por celda, año y bienio en `exposicion*/`, todo bajo `~/Asesorias_Data_local/AirPollution/modelado_1km/`.
Es una estimación de modelo, no una observación: entre pasadas satelitales y de noche el valor de cada
celda es enteramente modelado, y lejos de los monitores es una extrapolación.

## Documentos

- [`docs/modelo_1km_horario.qmd`](docs/modelo_1km_horario.qmd): el modelo de 1 km como documento
  ejecutable. Descriptivo de la red SINCA y de cada fuente a su resolución nativa, panel de calibración,
  diez motores con y sin validación cruzada, anexo regional, superficies y métricas de exposición. Su
  render es `docs/modelo_1km_horario.html`, con las figuras incrustadas en paleta de 256 colores.
- `docs/index.html`: índice del sitio. Lo regenera `python3 others_scripts/generar_indice_docs.py`;
  con `--archivar` además mueve a `others_files/` las notas de `docs/` que llevan 72 horas sin citarse ni
  modificarse.
- Notas técnicas de las fuentes en `docs/*.md` (ERA5-Land, MODIS, SNIFA, TROPOMI, reloj y unidades de
  SINCA, resolución satelital). Las bitácoras de `logs/` las verifican en `docs/` por ruta y hash: no
  moverlas a mano.
- `docs/_tablas_compactas.html`, `docs/_tablas_compactas.tex` y `docs/_pdf_unicode.tex`: estilos que se
  inyectan al renderizar el informe.
- `docs/references/`: `references.bib` y el estilo APA (`apa.csl`).
- Guías por carpeta: [`scripts_pipeline/README.md`](scripts_pipeline/README.md),
  [`scripts_superficie/README.md`](scripts_superficie/README.md),
  [`scripts_modelo_1km/README.md`](scripts_modelo_1km/README.md),
  [`scripts_estacion/README.md`](scripts_estacion/README.md),
  [`config/sinca/README.md`](config/sinca/README.md),
  [`config/snifa_adicional/README.md`](config/snifa_adicional/README.md),
  [`others_scripts/README.md`](others_scripts/README.md) y
  [`others_files/README.md`](others_files/README.md).
- `others_files/` guarda el informe anterior de modelos por estación y hora (seis contaminantes, 2019 a
  2024), las primeras corridas del modelo de 1 km, un respaldo de las tablas de los motores y notas de
  auditoría del pipeline.

## Relación con Air-Pollution-Health-Chile

El manuscrito para la revista The Innovation, en inglés y en español, con su suplemento y sus figuras,
el análisis epidemiológico de riesgo agudo (caso-cruzado sobre mortalidad, hospitalizaciones y
urgencias) y el estudio de muestreo de resonancias magnéticas de la Región Metropolitana viven en el
repositorio privado
[Air-Pollution-Health-Chile](https://github.com/AmaruSimonAgueroJimenez/Air-Pollution-Health-Chile). Ese repositorio
contiene además una copia completa de los modelos de este. Air-Pollution es la versión pública: los
modelos de estimación, sin el paper ni el análisis de salud.

## Licencia

GNU General Public License v3.0 (ver [`LICENSE`](LICENSE)).
