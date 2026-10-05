# Extractores por estación (correr en el Mac, junto a los datos crudos)

Convierten los productos satelitales ya descargados en `data/contaminantes/`
en **series chicas por estación SINCA** (`output_files/estacion/*.parquet`,
unos MB), que luego entran como columnas nuevas de `tabla_predictores()`
sin tocar los motores. Todos son **re-ejecutables**: si se cortan, se
vuelven a lanzar y retoman donde quedaron (checkpoint `*.procesados.txt`).

## Preparar el entorno (una vez)

Con micromamba (recomendado, resuelve HDF4 para MAIAC):

```bash
micromamba create -n extractores -c conda-forge \
    python=3.11 numpy pandas pyarrow netcdf4 h5py pyhdf
micromamba activate extractores
```

## Correr (desde esta carpeta)

```bash
cd "…/Air-Pollution/scripts_estacion"

# rápidos (~30–60 min entre ambos)
python extraer_mopitt_estacion.py            # CO superficial y columna, 1°
python extraer_omi_estacion.py               # columnas OMI 0,25° (SO2, …)

# largos — ideal dejarlos de un día para otro
nohup python extraer_s5p_estacion.py NO2 > s5p.log 2>&1 &  # puente al extractor canónico
nohup python extraer_maiac_estacion.py > maiac.log 2>&1 &  # MAIAC (4–10 h)
tail -f s5p.log
```

## Salidas

| Archivo | Contenido | Unidades |
|---|---|---|
| `data/procesado_estacion/s5p_no2_estacion_pixeles_nativos.parquet` | maestro TROPOMI estación–píxel con tiempo UTC, identificadores, QA, coordenadas y distancia; sin promedio | mol/m² y 10¹⁵ moléc/cm² |
| `data/procesado_estacion/s5p_no2_estacion_{pasadas,diario}_derivado.parquet` | resúmenes opcionales obtenidos del maestro anterior | mol/m² y 10¹⁵ moléc/cm² |
| `output_files/estacion/maiac_aod.parquet` | AOD 550 nm MAIAC, media 3×3 píxeles de 1 km por pasada, solo cielo despejado | adim. |
| `output_files/estacion/omi_so2.parquet` (…) | columna OMI, media 3×3 celdas de 0,25° por día | DU |
| `output_files/estacion/mopitt_co.parquet` | CO superficial y columna, día y noche, celda 1° | ppbv / molec·cm⁻² |

## ERA5-Land (descarga nueva; requiere cuenta CDS)

```bash
pip install "cdsapi>=0.7"     # y configurar ~/.cdsapirc (ver docstring)
python descargar_era5land.py  # 2019–2024; ~25–40 GB; re-ejecutable
```

Baja meteorología horaria 0,1° (T, punto de rocío → HR, viento, presión y
**precipitación**) + altura de capa límite de ERA5.

## Cuando terminen

Avísale a Claude en la sesión de Cowork: integra los parquet como columnas
del panel (`tabla_predictores()`), re-corre la validación LOSO de los seis
contaminantes y actualiza el documento con las métricas nuevas.
