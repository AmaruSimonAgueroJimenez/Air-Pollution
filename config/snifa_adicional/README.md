# Red adicional de calidad del aire publicada en SNIFA

Revisión: 22 de septiembre de 2026. Esta configuración identifica cinco
estaciones con concentraciones ambientales de los gases de la tesis. No son
mediciones de emisiones de chimenea. Los datos se mantienen bajo la red
`snifa_adicional` para conservar su procedencia y sus limitaciones de calidad.

## Contenido y contrato

- `estaciones.json`: fuentes SNIFA, estaciones, alias, gases verificados y
  coordenadas de los monitores. `schema_version` es 1.
- `sinca_catalog_snapshot_20260922.csv`: 219 filas extraídas de las 16 páginas
  regionales de SINCA, incluyendo estaciones públicas y privadas, en línea y
  fuera de línea. No se aplicaron los filtros de la interfaz.
- `evidencia_sinca.json`: URLs y hashes de las páginas consultadas, hash de la
  instantánea CSV, distancias de contraste y candidatas excluidas.

Los identificadores de `sources` y `stations` son estables. Cada fuente tiene
una unidad fiscalizable `uf_id` y sus `station_ids`; cada estación se vincula a
una fuente mediante `source_id`. Los `aliases` ayudan a interpretar títulos y
documentos; no sustituyen la verificación de contenido, contaminante y unidad.
`pollutants` contiene únicamente los gases comprobados (`no2`, `o3`, `so2`,
`co`). La presencia de un gas no acredita que todos los documentos o períodos
lo incluyan. Los materiales particulados complementarios se indican en notas.

`verified_first_report` es el inicio del período más antiguo localizado y
comprobado durante esta búsqueda, no la primera observación válida ni la fecha
de inicio de una serie completa. No debe usarse como límite inferior de la
búsqueda de informes. `date_start_declared`, cuando existe, es un inicio
operativo declarado en un informe, sin garantía de disponibilidad histórica.

Las coordenadas geográficas WGS84 se derivaron con `pyproj` de las coordenadas
UTM publicadas para cada monitor (EPSG:32718 o EPSG:32719 a EPSG:4326). El huso
UTM y `utm_hemisphere` describen la proyección espacial; **no describen el
reloj de los registros**. `timezone_status: unverified` exige conservar la
hora original hasta determinar si es hora civil, estándar o un desplazamiento
UTC fijo. No aplicar automáticamente la política temporal de SINCA a SNIFA.

## Fuentes y cobertura verificada

| Fuente / UF | Estaciones | Gases verificados | Evidencia |
|---|---|---|---|
| Central El Peñón / 1256 | El Peñón | NO2, O3, SO2, CO | [Julio 2026, XLS y PDF](https://snifa.sma.gob.cl/SeguimientoAmbiental/Ficha/1099713) |
| CT Los Guindos / 9976 | Charrúa, antes Charrúa Sur; Progreso | NO2, O3, SO2, CO en ambas | [Enero-marzo 2016](https://snifa.sma.gob.cl/SeguimientoAmbiental/Ficha/45835); [octubre-diciembre 2025](https://snifa.sma.gob.cl/SeguimientoAmbiental/Ficha/1086487) |
| Planta Masisa Cabrero / 2443 | SAPU; Quinel | SAPU: NO2 y SO2; Quinel: NO2 | [Junio 2013](https://snifa.sma.gob.cl/SeguimientoAmbiental/Ficha/8889); [junio 2025, XLSX y PDF](https://snifa.sma.gob.cl/SeguimientoAmbiental/Ficha/1074239) |

Los IDs de unidad fiscalizable fueron comprobados en los enlaces de los
expedientes citados, no inferidos de sus nombres. El informe de El Peñón de
diciembre de 2012 también fue abierto: [documento SMA 1445](https://api-ssa.sma.gob.cl/api/v1/GetDocumentoById/1445).

Charrúa y Progreso declaran inicio de mediciones de aire el **1 de abril de
2015** en la página física 13 del informe de diciembre de 2025, documento
1343780. Esto no garantiza datos descargables para cada mes desde 2015, ni
continuidad, calidad suficiente o el mismo instrumental y emplazamiento.
SAPU/Quinel tienen informes de distintos años, pero no se auditó cada mes.

La descarga completa permitió ampliar la evidencia de SAPU/Quinel hasta **diciembre
de 2012**, [expediente 1722](https://snifa.sma.gob.cl/SeguimientoAmbiental/Ficha/1722),
documento 2378, SEB-15857, páginas 16, 20 y 24. También hay tablas en enero de 2013,
[expediente 2856](https://snifa.sma.gob.cl/SeguimientoAmbiental/Ficha/2856), documento
4653, SEB-15919: 2.232 casillas horarias de los tres pares estación–gas.
Los documentos industriales de Masisa de comienzos de 2012 no prueban cobertura
de esos monitores ambientales y no se incorporan como datos de SAPU/Quinel.
Para Progreso se recuperaron tablas de **diciembre de 2015**, documento 94657,
[expediente 42874](https://snifa.sma.gob.cl/SeguimientoAmbiental/Ficha/42874).

## Ubicación de El Peñón

La Tabla 1 del informe de julio de 2026, página interna 2 / física 9, distingue:

| Elemento | Este UTM | Norte UTM | Referencia |
|---|---:|---:|---|
| Estación El Peñón | 286272 | 6663796 | WGS84, huso 19-J (19 Sur) |
| Central El Peñón | 285379 | 6663325 | WGS84, huso 19-J (19 Sur) |

La cabecera del XLS utiliza la posición de la **central**, a aproximadamente
1,01 km del monitor. El catálogo conserva la posición de la **estación**:
latitud -30.138437489 y longitud -71.218808729. No sobrescribir los documentos
originales ni reemplazar estas coordenadas con una cabecera de planilla sin
revisar su significado. La declaratoria EMRP de abril de 2009 tampoco demuestra
una fecha de primera observación.

Las coordenadas de Charrúa/Progreso se verificaron en las páginas físicas
16-17 del documento 1343780. Las de SAPU/Quinel están en la página física 11
del documento 1292945, correspondiente a junio de 2025. Se conserva la fuente
y el detalle de página por estación en `estaciones.json`.

## Contraste con SINCA

`sinca_catalog_status: not_found_name_location` significa **no localizada por
nombre, alias y ubicación en el catálogo público consultado el 22-09-2026**.
No es una certificación administrativa de ausencia ni una afirmación de que la
estación jamás haya reportado a SINCA.

Se revisaron 219 filas de las 16 páginas regionales y 63 fichas de las regiones
IV, VI y VIII. La [página estadística SINCA](https://sinca.mma.gob.cl/index.php/estadisticas)
publica 225 estaciones: se conserva esta discrepancia. No usar únicamente el
mapa de estaciones en línea para decidir ausencia. El catálogo local anterior
de la tesis es un subconjunto histórico y tampoco basta por sí solo.

| Estación adicional | SINCA más cercana en su región | Distancia aproximada |
|---|---|---:|
| El Peñón | El Sauce | 15,9 km |
| Charrúa | Colicheu | 9,7 km |
| Progreso | Colicheu | 5,4 km |
| SAPU | Colicheu | 11,9 km |
| Quinel | Colicheu | 12,7 km |

Algunas fichas SINCA contienen errores de coordenadas o de huso. Para Biobío
se probaron conservadoramente ambos husos 18 y 19; la estación más cercana a
las cuatro candidatas es Colicheu y su huso 18 está publicado correctamente.
Las fichas de Coiron y Punta Chungo publican coordenadas evidentemente
defectuosas y se excluyeron del cálculo de distancia, conservándose en el
contraste de nombres y comunas. Sus comunas oficiales son Salamanca y Los
Vilos, distintas de la ubicación de El Peñón.

Se excluyen **Club de Empleados**, presente en SINCA con los cuatro gases, y
**Gultro antigua**, equivalente espacialmente a MVC (diferencia de 1 metro).
Gultro se reubicó en junio de 2026: ese cambio requiere un tratamiento temporal
específico y no convierte toda la serie anterior en datos espacialmente nuevos.

## Condiciones de procesamiento

Conservar documentos originales, identificadores de expediente/documento,
URL de origen, fecha de descarga, hash, estación, parámetro, unidad original,
fecha/hora original y códigos de invalidación. Mantener códigos como `2.e`,
`3.b` y `2.a` separados de las concentraciones; no convertirlos en cero.
Un número en una celda no acredita por sí solo validación ambiental.

Distinguir concentraciones horarias de promedios diarios, promedios móviles,
estadísticas mensuales/anuales y límites normativos. Evitar duplicar una misma
observación publicada en informe, anexo y planilla. Registrar cambios de
instrumento, ubicación y unidad antes de unir períodos. SAPU y Quinel no deben
heredar automáticamente parámetros de otras estaciones de Masisa.

La integración con modelos queda condicionada a la auditoría de cobertura,
duplicados, calidad, unidades y reloj; la configuración sola no valida la red.
