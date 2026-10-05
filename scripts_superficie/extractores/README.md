# Extractores por estación (para correr en el Mac, donde viven los datos crudos)

Cada script lee un producto satelital ya descargado en `data/contaminantes/`
y lo reduce a una tabla chica **estación × día** (o × pasada) en
`data/procesado_estacion/`. Esas tablas pesan MB, se versionan en el repo y
se integran al pipeline (`tabla_predictores()`) como columnas nuevas sin
tocar los motores.

## Entorno (una vez)

```bash
# con conda/micromamba (recomendado por pyhdf, que necesita HDF4)
micromamba create -n extractores -c conda-forge python=3.11 numpy pandas pyarrow \
    netcdf4 h5py pyhdf cdsapi geopandas shapely
micromamba activate extractores
```

Con pip puro sirve todo salvo `pyhdf` (MAIAC); en macOS `brew install hdf4`
y luego `pip install pyhdf`.

## Orden sugerido y tiempos de referencia (Mac M-series, disco local)

| Paso | Script | Entrada | Salida | Tiempo aprox. |
|---|---|---|---|---|
| 1 | `extraer_omi_estacion.py` | OMI L2 píxel/pasada Parquet (13×24 km) | `omi_{no2,so2,o3}_estacion_pasadas.parquet` (todos los candidatos + distancia/QA) | depende de cobertura |
| 2 | `extraer_mopitt_estacion.py` | MOP02J L2 retrieval/pasada (~22 km) | `mopitt_co_estacion_pasadas.parquet` (todos los candidatos + perfil/error/QA) | depende de cobertura |
| 3 | `extraer_s5p_estacion.py --producto NO2` | TROPOMI L2 NO₂ compacto por AOI | `s5p_no2_estacion_pixeles_nativos.parquet` (maestro) + `{pasadas,diario}_derivado.parquet` | depende de cobertura |
| 4 | `extraer_maiac_estacion.py` | MCD19A2 1 km (24.048 tiles) | `maiac_aod_estacion_{pasadas,diario}.parquet` | 2–4 h |
| 5 | `descargar_era5land.py` | CDS + legado validado, AOIs derivados de `comunas.shp` | `ERA5Land/chile_nativo_01deg/`: catálogo nativo + relación píxel–comuna + NetCDF horarios mensuales | horas/días (cola CDS) |
| 6 | `normalizar_era5_blh_chile.py` | ERA5 BLH 0,25° horario | `ERA5/chile_nativo_025deg/` con contrato, catálogos y manifiestos equivalentes | ~10–20 min para 2000–2026 |

Todo es **reanudable**: si se corta, se vuelve a lanzar y sigue donde quedó
(checkpoints `_hecho_*.txt` en `data/procesado_estacion/`). Para probar en
un par de archivos antes de la corrida completa: `--prueba 5`.

```bash
cd scripts_superficie/extractores
bash correr_extractores.sh          # 1 → 4 en secuencia, con log en extractores.log
```

Cuando terminen, se suben al repo los parquet de `data/procesado_estacion/`
(no las carpetas `_partes_*`, que son temporales) y se integran al
documento con una re-validación.

## Detalles metodológicos

* **TROPOMI**: el maestro conserva cada píxel a ≤ 7 km de la estación con
  `qa_value ≥ 0,75`, su hora UTC nativa, identificadores, comuna por centro,
  coordenadas y distancia, en mol/m² y 10¹⁵ moléc/cm². Las medias por pasada
  y día llevan el sufijo `_derivado` y no sustituyen al maestro. SO₂/CO/O₃
  usan el mismo script (`--producto SO2`, qa ≥ 0,5) cuando estén disponibles.
* **OMI L2**: conserva todos los píxeles a ≤45 km de cada estación por pasada,
  con distancia, huella, incertidumbre y QA crudos. No elige un único vecino
  ni resume por día/hora; `--radio-km` permite reproducir otra vecindad.
* **MOPITT L2**: conserva todos los retrievals a ≤35 km por estación/pasada,
  incluida columna/superficie, errores, perfil, kernels y QA. No depende de
  MOP03J L3 ni inventa observaciones posteriores al 2025-02-01.
* **MAIAC**: ventana 3 × 3 píxeles (~2,8 km) alrededor de la estación en
  proyección sinusoidal; solo píxeles «clear» (máscara de nube) y calidad AOD
  mejor; `--qa-relajado` acepta también calidad 1 si la cobertura queda rala.
* **ERA5-Land**: `descargar_era5land.py` baja desde 2000 hasta la fecha
  disponible. Solicita por separado continente, Juan Fernández,
  Desventuradas, Rapa Nui y Sala y Gómez; `normalizar_era5land_chile.py`
  conserva hora UTC × celda nativa de 0,1° sin interpolar ni promediar. La
  pertenencia comunal principal y la relación muchos-a-muchos se guardan en
  catálogos estáticos, incluido `cod_comuna=0`. Cada manifiesto registra
  parámetros, versiones y SHA-256 de máscara, fuentes y salida. Los NetCDF de
  descarga sólo viven en `staging_descarga/` y se borran tras revalidar la
  salida. La altura de capa límite pertenece a ERA5 0,25° y se mantiene como
  producto separado para no fingir resolución de ERA5-Land.
* **ERA5 BLH**: `normalizar_era5_blh_chile.py` conserva sus 1.780 celdas
  chilenas a 0,25° y cada hora UTC. Los rectángulos históricos se conservan
  por defecto; sólo la opción explícita `--eliminar-fuentes-validadas` los
  retira, individualmente y después de comprobar salida y hashes.
