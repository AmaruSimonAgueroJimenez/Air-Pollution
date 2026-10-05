# GOES-East ABI AOD: cada escaneo, píxel nativo de Chile

Contrato operativo documentado el 18 de septiembre de 2026. Este documento
describe el código y el procedimiento; **no certifica que exista una descarga
terminada**. El estado efectivo se consulta en `manifest_escaneos.csv`, en los
manifiestos diarios y en los JSONL de `_manifiestos/`.

## Qué aporta y qué no

El único sensor con cadencia horaria o mayor sobre Chile es el Advanced
Baseline Imager (ABI) de GOES-East (GOES-16 hasta el 6 de abril de 2025,
GOES-19 desde el 7 de abril de 2025, ambos en 75,2°O). NOAA publica el
producto L2 `ABI-L2-AODF` (Aerosol Optical Depth a 550 nm, disco completo)
en los buckets públicos `s3://noaa-goes16` y `s3://noaa-goes19`, sin
credenciales, con un archivo por escaneo: cada 10 minutos en modo 6 (desde
abril de 2019), cada 15 minutos en modo 3 y cada 5 en modo 4.

Es una observación de **columna de aerosol diurna**, no de PM2.5 en superficie,
y con límites que el descargador no puede corregir:

- El algoritmo sólo recupera con Sol sobre el horizonte (ángulo cenital solar
  < 90°, calidad degradada por encima de 80°) y sobre superficies oscuras: no
  hay AOD sobre desierto, suelo desnudo, nieve ni glint. El Norte Grande y
  gran parte del Norte Chico quedan sin recuperación la mayor parte del
  tiempo; el centro-sur vegetado sí.
- La grilla fija es de 2 km al nadir. Sobre Chile el píxel efectivo va de
  ~2,2 km (Arica) a ~4,4 km norte-sur en Magallanes, donde el ángulo cenital
  del satélite supera los 60° que NOAA marca como umbral de calidad
  reducida. El catálogo guarda ese ángulo por celda.
- El archivo L2 no trae hora por píxel; el tiempo es el del escaneo
  (`time_bounds` y `t`), con incertidumbre intra-escaneo menor que la duración
  del barrido (≤ 10 minutos). No se rellenan horas ni noches.

Fuentes: [STAR AOD](https://www.star.nesdis.noaa.gov/goesr/product_aero_aod.php),
[readme NOAA del producto](https://www.ncei.noaa.gov/sites/default/files/2022-12/GOES-18_ABI_L2_AOD_APS_Provisional_ReadMe.pdf),
[NODD en AWS](https://registry.opendata.aws/noaa-goes/) y el GOES-R Product
User Guide vol. 3 (§4.2.8, geometría de la grilla fija).

## Motor

`scripts_pipeline/descargar_goes_abi_aod.py`. Por día UTC:

1. Lista `ABI-L2-AODF/AAAA/DDD/` en el bucket del satélite que corresponde a
   la fecha (`--satelite auto`) y guarda el listado en
   `_catalogos_s3/<ejecución>/<día>.json`. Ante reprocesamientos con el mismo
   inicio conserva la creación más reciente y registra el descartado.
2. Aplica la cadencia (`nativa`, `30min`, `horaria`: minuto 00 sin sustituir
   faltantes) y omite, **sin descargar**, los escaneos en que todo Chile tiene
   ángulo cenital solar ≥ `--sza-max` + 2° (malla de 0,5° sobre las cinco AOI,
   posición solar NOAA). Quedan registrados como `omitido_noche_geometrica`.
3. Descarga cada archivo completo (20–115 MB) a `_staging/<día>/`, verifica
   tamaño contra el listado y calcula SHA-256.
4. Lee la proyección (`goes_imager_projection`) y los ángulos `x`/`y`; rechaza
   cualquier archivo cuyo origen no sea el de GOES-East (−75,0°). La grilla
   se identifica con un `grid_id` (hash de proyección, forma y ángulos).
5. La primera vez que aparece un `grid_id` construye el catálogo de píxeles:
   convierte la grilla a lat/lon con las fórmulas del PUG (verificadas con el
   ejemplo oficial), forma la huella de cada celda con sus cuatro esquinas en
   ángulos de escaneo y conserva las celdas cuya huella intersecta alguna
   comuna. `cod_comuna` es el de la comuna que contiene el centro (−1 si sólo
   la huella toca Chile, 0 en la zona sin demarcar). En la prueba de
   preflight con la máscara oficial resultaron **136.486 celdas**
   (136.392 continentales, 45 Juan Fernández, 10 Desventuradas, 38 Rapa Nui y
   1 Sala y Gómez), con 344 comunas con centro de celda; la construcción tomó
   ~8 minutos y se hace una sola vez por grilla.
6. Extrae `AOD`, `DQF`, `AE1` y `AE2` en esas celdas y conserva cada valor
   empaquetado (`*_i16`) y decodificado con `scale_factor`/`add_offset`.
   Sólo generan fila las celdas con `AOD ≠ _FillValue`; el conteo por DQF de
   todas las celdas chilenas queda en el catálogo de escaneos, de modo que
   la ausencia es reconstruible y explícita (no es un filtro de calidad:
   DQF 0, 1 y 2 se conservan).
7. Publica `observaciones/` y `catalogo_escaneos/` del día como Parquet ZSTD
   (`.part` → reapertura → validación → reemplazo), escribe el manifiesto JSON
   del día con hashes de fuente y salida, persiste un WAL
   (`dia_validado_pre_borrado`) y sólo entonces retira los crudos
   (`crudo_eliminado_post_validacion`). Un día con cualquier descarga o recorte
   fallido no se publica ni se limpia: queda en `error` y se repite entero.
8. Marca el día en `manifest_escaneos.csv`; una nueva ejecución omite los
   días `ok` o `sin_datos` cuyas salidas conservan tamaño (y hash con
   `--revalidar`).

Reserva mínima de disco (`--reserva-gib`, 100 por defecto), presupuesto de
staging (`--staging-gib`, 12) y cuota acumulada de productos
(`--cuota-productos-gib`, 60) pausan el proceso con código 75 y evento
`pausado_limite_seguro`; nada se borra al pausar. En macOS se exige el UUID
del disco externo cuando la raíz vive en `/Volumes/Datos`. `LIMITE_MBPS` en
`.env` acota la transferencia media.

## Salidas

Bajo `data/contaminantes/GOES_ABI_AOD/`:

| Ruta | Contenido |
| --- | --- |
| `catalogo_pixeles/grid=<grid_id>/pixeles.parquet` + `metadata.json` | `pixel_id` (= `y_index·nx + x_index`, válido sólo dentro de ese `grid_id`), índices, ángulos de escaneo, centro y cuatro esquinas en lat/lon, ángulo cenital del satélite, `cod_comuna`, AOI |
| `catalogo_pixeles/grid=<grid_id>/enlaces_geoespaciales/` | sólo con `--enlaces`: `pixel_comuna.parquet` (muchos-a-muchos por intersección exacta de la huella con las comunas subdivididas en piezas de ≤ 512 vértices, área en EPSG:6933, fracción de celda recortada a [0, 1] con exceso máximo registrado en `metadata.json`) y `estacion_pixel.parquet`; ≈1 min por grilla (151.169 enlaces, 136.486 píxeles, 346 comunas, 109 estaciones a ≤ 1,8 km) |
| `observaciones/year=AAAA/month=MM/goes_abi_obs_AAAAMMDD.parquet` | `scan_id`, `pixel_id`, `aod_i16`, `aod`, `dqf`, `ae1_i16`, `ae1`, `ae2_i16`, `ae2` |
| `catalogo_escaneos/year=AAAA/month=MM/goes_abi_escaneos_AAAAMMDD.parquet` | un registro por escaneo procesado: satélite, modo, inicio/fin/medio UTC, archivo y SHA-256 de origen, `grid_id`, subpunto, SZA mínimo en Chile, conteos por DQF |
| `manifiestos_escaneos/year=AAAA/month=MM/goes_abi_AAAAMMDD.json` | transacción del día: listado S3, escaneos procesados con atributos globales y variables escalares (completos en el primero, diferencias en el resto), omitidos con motivo, huecos respecto de la cadencia esperada, hashes de salidas |
| `manifest_escaneos.csv`, `_manifiestos/*.jsonl`, `_control/avance.json` | reanudación, WAL durable y último estado |

`scan_id` es el inicio del escaneo en segundos desde 2000-01-01T12:00Z
(J2000), igual que la variable `t` del producto. `cod_comuna` del catálogo es
una etiqueta por centro; para una unión sin sesgo de borde use los enlaces
muchos-a-muchos. Los `pixel_id` no son comparables con otros productos ni
entre `grid_id` distintos.

## Cómo correr

Prueba real previa, un escaneo diurno de un día, desde la raíz del proyecto:

```sh
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -B \
  scripts_pipeline/descargar_goes_abi_aod.py \
  --desde 2023-10-05 --hasta 2023-10-05 --max-escaneos-por-dia 1 \
  --reserva-gib 100 --staging-gib 12 --cuota-productos-gib 60
```

Esa prueba construye el catálogo de píxeles (minutos), descarga un archivo,
publica el día con un solo escaneo y deja la transacción completa. **No
mantener `--max-escaneos-por-dia` en un histórico**: el manifiesto del día
registra la limitación y el día debe rehacerse sin ella.

Histórico a cadencia nativa (10 minutos) o, si el disco manda, horaria:

```sh
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -B \
  scripts_pipeline/descargar_goes_abi_aod.py --desde 2017-12-18 --hasta 2026-09-16
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -B \
  scripts_pipeline/descargar_goes_abi_aod.py --cadencia horaria --desde 2019-01-01 --hasta 2024-12-31
```

Los runners `lanzar_descargas.sh` y `ejecutar_descargas.sh` incluyen el
descargador inmediatamente después de Black Marble; la variable de entorno
`GOES_ABI_CADENCIA` (`nativa`, `30min`, `horaria`) fija la cadencia en esas
corridas. `--dry-run` imprime el plan sin red ni escritura; `--listar`
muestra el listado S3 del primer día. Una fuente permanentemente corrupta
se excluye a mano en `_control/exclusiones.json` (`{"clave S3": "motivo"}`) y
queda registrada en el manifiesto del día como `omitido_por_exclusion_manual`.

## Proyección de volumen y tiempo

Cada escaneo del disco completo pesa decenas de MB (el ensayo sintético con
campos aleatorios, incompresibles, llegó a 115 MB; los reales, con fill fuera
del disco y sin recuperación, comprimen mucho mejor). A cadencia nativa son
~70 archivos diurnos por día (los nocturnos no se descargan), del orden de
1–3 GB de transferencia diaria y varios TB para 2017–2026; la prueba real
registra `bytes_fuente` por escaneo y es la cifra que debe usarse. El recorte
a Chile tarda ~0,5 s por escaneo; la descarga domina. Con `LIMITE_MBPS=50` el
histórico completo a cadencia nativa toma semanas; a cadencia horaria, días.

Producto publicado: en el preflight sintético con 40 % de celdas con
recuperación y 70 escaneos diurnos, un día ocupa ~50 MB (14 bytes por fila
con datos aleatorios, incompresibles). Con datos reales, más nubes y el
desierto sin recuperación, la proyección es **5–18 GiB por año** a cadencia
nativa y **1–3 GiB por año** a cadencia horaria. La cuota inicial de 60 GiB es
un límite operativo para revisar el crecimiento real desde los manifiestos, no
una estimación del histórico completo. Con 244 GB libres y la descarga
multi-gas de TROPOMI pendiente, conviene decidir cadencia y rango antes de
lanzar el histórico.

## Qué no hace

- No convierte AOD en PM2.5 ni interpola a 1 km: eso pertenece al modelo.
- No filtra por DQF ni por ángulo: conserva la calidad nativa para que el
  filtro se defina y versione en el análisis.
- No mezcla satélites por escaneo: un día se lista en un solo bucket; la
  transición GOES-16 → GOES-19 se resuelve por fecha y se verifica por el
  origen de proyección de cada archivo.
- No lee el archivo por rangos HDF5: se descarga completo para registrar el
  SHA-256 de la fuente, como en los demás descargadores del proyecto.
