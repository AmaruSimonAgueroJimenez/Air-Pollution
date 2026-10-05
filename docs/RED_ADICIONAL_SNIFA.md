# Red adicional de gases publicada en SNIFA

[Resultado de la ejecución del 22-09-2026](EJECUCION_SNIFA_20260922.md):
descarga completa, cobertura obtenida y revisión de calidad.

Este flujo descarga y procesa una red separada, identificada como `snifa_adicional`.
Sus cinco estaciones no se encontraron por nombre y ubicación en el catálogo SINCA
revisado el 22 de septiembre de 2026. SNIFA es el repositorio público de los informes,
no una red de medición con una única metodología. No se afirma que las estaciones
nunca hayan pertenecido a SINCA.

| Fuente pública | Estaciones | Gases incluidos |
|---|---|---|
| [Central El Peñón, UF 1256](https://snifa.sma.gob.cl/UnidadFiscalizable/Ficha/1256) | El Peñón | NO₂, O₃, SO₂, CO |
| [CT Los Guindos, UF 9976](https://snifa.sma.gob.cl/UnidadFiscalizable/Ficha/9976) | Charrúa, Progreso | NO₂, O₃, SO₂, CO |
| [Planta Masisa Cabrero, UF 2443](https://snifa.sma.gob.cl/UnidadFiscalizable/Ficha/2443) | SAPU, Quinel | SAPU: NO₂ y SO₂; Quinel: NO₂ |

Las identidades, alias, coordenadas, fechas documentadas y evidencia del contraste
con SINCA están en [la configuración](../config/snifa_adicional/README.md).
La descarga busca todo el historial publicado de estas fuentes: no utiliza la fecha
de una muestra previamente revisada como límite inferior. La cobertura extraída
de cada gas se calcula a partir de los registros, no de la fecha de instalación.

## Archivos y destino

El código vive en `scripts_pipeline/` y la configuración en `config/snifa_adicional/`.
Los originales y productos grandes se escriben por defecto en el disco externo:

```text
/Volumes/Datos/Asesorias_Data/AirPollution/data/snifa_adicional/
  raw/<fuente>/<informe>/<documento>_<nombre original>
  metadata/html/                  fichas públicas de origen
  metadata/download_manifest.json  URL, período, estado, tamaño y SHA-256
  metadata/station_config.json      configuración utilizada para la descarga
  processed/by_document/           Parquet y auditoría de cada documento
  processed/observaciones_horarias.parquet  selección canónica, con banderas
  processed/conflictos.parquet     todas las alternativas en conflicto
  processed/cobertura.csv          cobertura por estación, gas y unidad
  processed/processing_report.json errores, omisiones y trazabilidad
```

`AIR_POLLUTION_DATA_ROOT` permite cambiar la raíz `.../data`; alternativamente se
respeta `ASESORIAS_DATA_ROOT`. A ambas se añade la carpeta `snifa_adicional`.
Se comprueba que el volumen esté montado y se reserva un mínimo de **100 GiB**.
No se escribe en las carpetas SINCA ni se incorpora este flujo a los lanzadores
generales de descargas existentes.

## Ejecución reproducible

Desde la raíz del repositorio, con Python 3.11 o posterior:

```bash
python3 -m venv /ruta/local/runtime_snifa
/ruta/local/runtime_snifa/bin/python -m pip install -r scripts_pipeline/requirements-snifa.lock.txt
export PYTHON_SNIFA=/ruta/local/runtime_snifa/bin/python
bash scripts_pipeline/ejecutar_snifa.sh
```

El lanzador ejecuta el historial completo sin argumentos. El descargador admite
`--desde 2013-01-01`, `--hasta 2026-09-22`, `--fuentes el_penon,los_guindos` y
`--workers 4`. Para cambiar el destino en ambas etapas use la variable
`AIR_POLLUTION_DATA_ROOT`. Si usa `--destino` en el
descargador, ejecute el procesador por separado con el mismo directorio en `--raiz`.

El archivo `.lock.txt` fija las versiones principales utilizadas en la ejecución
verificada. `requirements-snifa.txt` expresa los rangos admitidos para una nueva
instalación; el inventario completo del entorno ejecutado se conserva en
`metadata/runtime_freeze.txt` en el disco externo.

En el equipo de la ejecución inicial, el entorno está instalado en
`~/Asesorias_Data_local/AirPollution/runtime_snifa`. El lanzador lo detecta cuando
`PYTHON_SNIFA` no está definido, de modo que basta ejecutar
`bash scripts_pipeline/ejecutar_snifa.sh` desde la raíz del repositorio.

```bash
"$PYTHON_SNIFA" scripts_pipeline/descargar_snifa.py --solo-descubrir
"$PYTHON_SNIFA" scripts_pipeline/descargar_snifa.py --actualizar
"$PYTHON_SNIFA" scripts_pipeline/preparar_snifa_modelado.py --workers 4
```

La primera orden guarda el plan sin descargar originales. `--actualizar` refresca
las fichas de los informes, además del índice de cada fuente, que se consulta en
cada ejecución. Los originales descargados se reutilizan si su SHA-256 coincide.
Las descargas incompletas usan archivos temporales; un error no se interpreta como
un PDF o una planilla válidos. Los cambios en extractores o configuración invalidan
la caché de procesamiento. `--reprocesar` la invalida explícitamente.

Los filtros de fecha seleccionan informes cuyo período se cruza con el solicitado;
no recortan físicamente esos archivos. El procesamiento incluye todos los documentos
descargados que figuran en el manifiesto acumulativo. `--limite-documentos` sirve
únicamente para diagnóstico y produce una salida parcial.

El procesador admite `--formatos pdf` para revisar solo ese formato; la salida de
esa ejecución es parcial y así lo registra `formats_selected`. Una ejecución sin
ese filtro vuelve a consolidar todos los documentos. Las cachés de Excel y PDF
son independientes: cambiar un lector no obliga a releer el otro formato.

## Obtención de datos y límites de interpretación

1. Se descubren informes públicos de gases/calidad del aire en las tres fichas de
   unidades fiscalizables y se guardan las fichas consultadas.
2. Los identificadores de documentos se resuelven con el servicio público oficial
   `api-ssa.sma.gob.cl/api/v1/GetDocumentoById/<id>` y su descarga de documentos.
   No se requieren credenciales. Se guardan el original, sus metadatos y su hash.
   El descubrimiento amplio de expedientes de gases también puede conservar
   documentos de emisiones industriales; solo las estaciones ambientales
   identificadas explícitamente entran en la base horaria.
3. Se leen matrices horarias y tablas largas de fecha/hora en XLS/XLSX y los diseños
   reconocidos de PDF. En Los Guindos se enlazan además los códigos publicados en
   hojas `EVENTOS` y en PDF separados por expediente, estación, fecha/hora y gas.
   Los códigos se aplican antes de seleccionar datos utilizables y se conservan
   los documentos y las celdas de origen. Se conservan
   blancos, códigos originales de invalidación y ceros. Los promedios móviles de
   ocho horas, resúmenes diarios y NO/NOx no se convierten en observaciones de NO₂.
4. Cada fila conserva documento, informe, hoja/celda o página, unidad original,
   fecha y etiqueta horaria publicada. Los registros siguen disponibles por documento.
5. La selección canónica agrupa estación, gas, fecha, hora y unidad. Prefiere Excel
   sobre PDF y señala valores, unidades o códigos de calidad que discrepan. No
   promedia las discrepancias. Las alternativas quedan en `conflictos.parquet`.

**Reloj:** las fuentes usan etiquetas como 1–24 y 0–23. Se preservan y se normaliza
solo la representación del índice horario. No se interpreta automáticamente si la
hora corresponde al inicio o al fin del intervalo, ni si el reloj usa hora oficial
o fija. `timestamp_utc` permanece vacío y `ready_for_utc_join` es falso hasta resolver
esa semántica. El producto sirve para revisar e integrar una fuente adicional, pero
todavía no debe unirse a satélites por UTC sin esa validación.

**Unidades y calidad:** se normaliza la escritura de ppb, ppm, µg/m³, µg/m³N, mg/m³
y mg/m³N, además de ppbv y ppmv, sin convertir entre ellas. La N se conserva porque implica condiciones
normalizadas. `numeric_usable` requiere valor numérico no negativo, unidad conocida
y ausencia de código de invalidación. `usable_native` exige además ausencia de
conflictos. Estas banderas no equivalen a certificación oficial del dato.

Si un anexo PDF de eventos no se puede interpretar, `quality_review_required`
marca los registros PDF del mismo expediente y evita considerarlos utilizables.
`quality_document_ids` y `quality_source_locators` permiten revisar las banderas
incorporadas desde otro documento. Las tablas de eventos se conservan por documento,
pero no cuentan como concentraciones en el archivo canónico.

Las fechas explícitas de las tablas prevalecen sobre el período administrativo del
expediente; `outside_report_period` conserva la discrepancia. Las filas de plantilla
fuera del período que declara la propia planilla siguen excluyéndose.

Los libros se detectan por su contenido, porque algunos `.XLS` son realmente XLSX.
Para XLS que el lector habitual no puede abrir, se utiliza Calamine como lector
alternativo y queda registrado en la auditoría; no se reparan ni modifican originales.

En las planillas de El Peñón inspeccionadas, 2022–2024 usan CO en mg/m³N y otros
gases en µg/m³N, con horas 0–2300; enero de 2025 usa CO en ppm y otros gases en ppb,
con horas 100–2400. No se fuerza continuidad de unidades o de convención horaria
entre esos formatos.

**PDF escaneados y diseños no reconocidos:** se descargan y conservan. Cuando no
puede extraerse una matriz inequívocamente, la auditoría informa la omisión; no se
rellenan datos. Por ejemplo, varios anexos antiguos de El Peñón necesitan OCR y
revisión de las cifras. Un informe que solo contiene resúmenes tampoco garantiza
que existan observaciones horarias extraíbles. `complete_historical_coverage` se
mantiene falso: tener un informe descargado no significa haber recuperado todas
sus mediciones.

**Ubicación:** se usa la coordenada de la estación del catálogo verificado. En El
Peñón algunas planillas publican la posición de la central, aproximadamente 1 km
distante del monitor; no se usa esa cabecera para geolocalizar la estación.

## Comprobación

```bash
"$PYTHON_SNIFA" -m unittest discover -s scripts_pipeline/tests -p 'test_*snifa*.py' -v
```

Las pruebas incluyen matrices sintéticas con blancos, códigos, rotaciones y
duplicados, así como muestras originales cuando están disponibles en el entorno.
La auditoría de cada ejecución es la fuente para los conteos finales, errores y
fechas efectivamente recuperadas.
