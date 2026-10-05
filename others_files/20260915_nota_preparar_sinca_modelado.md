# SINCA para modelado: derivado conservador y reproducible

`scripts_pipeline/preparar_sinca_modelado.py` convierte únicamente fuentes SINCA locales verificadas por su manifiesto. No usa red, no entrena modelos, no modifica lectores existentes y nunca borra o reescribe originales. La primera ejecución autorizada es una estación/contaminante y ventana corta; el procesamiento histórico completo requiere coordinación del orquestador.

## Ejecución

La ejecución histórica del 15 de septiembre de 2026 usó Python 3.14.3,
NumPy 2.4.3, pandas 2.3.3 y PyArrow 23.0.1; no el entorno `neuro`.
Las dependencias observadas están en `scripts_pipeline/requirements-modelado.txt`.
Para reproducir una versión concreta, consultar además el entorno y el hash de
la base horaria registrados en su manifiesto: cambiar de entorno o de base IANA
puede crear otra versión. No actualizar el entorno de los descargadores activos.
El destino exige macOS/Darwin, el volumen Datos con UUID
`54B3D309-A503-44C6-9229-581F3E4FECE3` y un piso de 100 GiB libres,
comprobado antes y durante cada publicación.

```sh
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -B scripts_pipeline/preparar_sinca_modelado.py \
  --estacion 117 --contaminante pm25 --desde 2026-09-01 --hasta 2026-09-13 --max-series 1
```

Sin `--ejecutar` sólo se imprime el plan. Añadir `--ejecutar --reserva-gib 100` para publicar el alcance seleccionado. `--max-series 0` incluye todas las series coincidentes y es una elección explícita: no es el valor predeterminado. `--hasta` es inclusivo en etiquetas civiles originales. No se crean filas de calendario faltantes. Las etiquetas de fecha inválidas se conservan, aunque no se puedan asignar inequívocamente a la ventana.

Destino independiente:

```text
/Volumes/Datos/Asesorias_Data/AirPollution/derived/modelado/SINCA/v1/
  estacion=<id>/contaminante=<gas>/version=<SHA256>/
    observaciones.parquet
    solapamientos.parquet
    manifest.json
    procedencia/  # código, afg_lib, política y catálogo geográfico exactos
  _runs/<UTC-UUID>/  # plan, copias de configuración/código y progreso
  _staging/         # sólo intentos aún no publicados; no se borran por este programa
```

La partición por estación/contaminante permite consolidar todos sus solapamientos de forma conjunta, sin promediar por comuna. Los grupos de filas Parquet son de hasta 65.536 observaciones, con compresión Zstandard. La versión incluye fuentes y sus hashes, ventana, geometría, política temporal, funciones heredadas, código, paquetes y archivo IANA utilizado. Un cambio de esos insumos crea una versión nueva; no reemplaza la anterior. Una reentrada idéntica verifica hashes y reutiliza la versión ya válida.

## Contrato científico

- Se extraen por AST únicamente `leer_sinca_serie` y las cuatro instrucciones de ranking de `leer_sinca` en `scripts_superficie/afg_lib.py`. No se importa el módulo completo ni sus dependencias de modelado/efectos de arranque. Se archiva el archivo íntegro y los hashes de ambas reglas.
- El parser original prioriza valor validado, luego preliminar y luego no validado. Se conservan además las tres celdas originales, fecha/hora textuales y columna extra. Cero no equivale a faltante.
- Para cada etiqueta civil, el ranking heredado favorece medición finita dentro de sus rangos orientativos, calidad, fin de consulta, amplitud de consulta y nombre de archivo. No se borran valores fuera de rango: llevan `fuera_rango_afg`. Esos rangos no prueban unidades.
- `observaciones.parquet` contiene las filas elegidas; `solapamientos.parquet` conserva **cada alternativa** con las mismas columnas. Su unión conserva exactamente las filas originales dentro de la ventana y las etiquetas inválidas. `fuente_id`, `source_sha256`, `source_path`, `source_line`, `grupo_solapamiento`, `n_candidatos` y `seleccionada` reconstruyen la decisión. El identificador numérico de grupo es local a la versión, no una clave global.
- Las repeticiones de hora dentro de un mismo CSV se marcan `hora_repetida_en_fuente`. No se puede afirmar que sean revisiones y no horas civiles repetidas por DST: deben consultarse también las alternativas antes de modelar esas horas.
- `ts_local` representa la etiqueta civil, no demuestra el inicio/fin del intervalo. `ts_utc` permanece nulo y `semantica_intervalo_verificada=false`. `utc_candidato_1/2` son hipótesis explícitas de conversión IANA, **no horas confirmadas**. Una hora inexistente no se desplaza; una ambigua mantiene ambos candidatos. Se usa Santiago por defecto, Coyhaique para RXI y Punta Arenas para RXII, según política del proyecto y reglas históricas IANA congeladas por hash. No se aplica el desplazamiento/promedio posterior del lector heredado.
- Los CSV y el manifiesto actuales no demuestran la unidad de cada serie. Por ello `unidad=null`, `unidad_confirmada=false`; no hay conversión ni inferencia desde rangos o nombre de gas. Es necesaria evidencia adicional antes de interpretar concentraciones o unir unidades.
- Se preservan estación, latitud/longitud, punto WKB EPSG:4326 (`x=lon`, `y=lat`), catálogo geográfico exacto y discrepancias entre comuna SINCA y geográfica. Es Parquet con WKB explícito, **no se anuncia como GeoParquet formal**. No se agregan estaciones ni se descarta una discrepancia automáticamente.
- No hay imputación, escalado, filtrado automático de no validados ni transformación a promedios comunales. Estos derivados aún requieren decisiones analíticas documentadas sobre reloj, unidades, calidad y validación del modelo.

## Seguridad y reanudación

El CLI mantiene un bloqueo exclusivo durante toda la ejecución. Cada fuente se comprueba contra SHA256 y tamaño antes de leerla y se vuelve a comprobar antes de publicar. Los dos Parquet se escriben primero en staging, se sincronizan, se reabren y se exige igualdad exacta con las tablas en memoria, incluyendo esquema. El manifiesto conserva SHA256 y esquema de las salidas y de los archivos de procedencia. La publicación del directorio usa `renamex_np(RENAME_EXCL)`: no sustituye ni siquiera un destino vacío creado concurrentemente.

Un fallo deja originales y staging intactos. Si staging tiene un manifiesto completo y válido, una reentrada lo publica sin reconvertir. Los parciales sin manifiesto no se sobrescriben; se conserva el intento y se utiliza otro directorio UUID. Este programa no elimina parciales automáticamente: cualquier limpieza posterior necesita comprobar su reemplazo válido. Un estado `complete_for_selected_scope` significa sólo que terminó el filtro solicitado, no que SINCA tenga observaciones en todas las horas o estaciones.

API para el orquestador: `load_inputs(source, policy_path, afg_path, station=None, pollutant=None)` devuelve un snapshot inmutable; agrupar `inputs['rows']` por `(estacion, contaminante)` y llamar `process_series(rows, inputs, output, since=..., until=...)` **dentro de** `exclusive_lock(output / '.writer.lock')`. Validación posterior: `validate_publication(path, expected_version)`. En producción no desactivar la comprobación de UUID; `volume_uuid=None` está reservado a fixtures locales de pruebas.

```sh
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -B -m unittest scripts_pipeline.tests.test_preparar_sinca_modelado -v
```

Las pruebas sin red cubren conservación exacta de filas, ranking heredado, datos no validados y valores faltantes, DST por región, geometría/discrepancias, fuentes alteradas, bloqueos/reserva, idempotencia, fallos antes de publicación, recuperación de staging y publicación exclusiva sin sustitución.
