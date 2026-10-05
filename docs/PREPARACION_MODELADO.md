# Preparación reproducible para modelado

Los scripts transforman **datos locales ya disponibles**, sin descargar, entrenar,
imputar ni promediar comunas. Una transformación terminada no significa que la
fuente histórica esté completa o que todas sus observaciones sean válidas.

## Un único punto de entrada

El entorno probado es Python 3.14.3 en macOS; las versiones observadas están
en `scripts_pipeline/requirements-modelado.txt`. Los manifiestos de cada
ejecución son la referencia definitiva de su entorno. Ese archivo no representa
una imagen binaria completa del sistema ni reemplaza la evidencia de zonas
horarias. No modificar el entorno mientras haya procesos activos. En otro
equipo hay que configurar y auditar rutas/identidad del disco: no desactivar
las protecciones de montaje o integridad. Estos conversores publican mediante
operaciones de exclusión específicas de macOS.

Desde la raíz del proyecto, revisar el plan (no escribe):

```sh
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -B scripts_pipeline/preparar_datos_modelado.py \
  --merra-hasta 2026-05 --sinca-hasta 2026-09-13 --era-hasta 2026-09
```

Añadir `--ejecutar` para ejecutarlo. `--productos merra2`, `--productos sinca`
o `--productos era5land` permite ejecutar un componente. Los extremos iniciales
predeterminados son enero de 2000. Los extremos finales son explícitos: no se
solicitan meses futuros ni se declara completo el año 2026.

La misma orden revalida y reutiliza productos idénticos; si cambia una fuente,
SINCA y ERA5-Land crean una revisión distinta sin reemplazar la anterior.
MERRA-2 protege su publicación canónica y se detiene ante contradicciones.
Se exige el disco externo correcto y al menos 100 GiB libres. No hay destino
alternativo en el disco interno. Una interrupción se recupera repitiendo la orden;
un error de integridad requiere inspección, no borrado del producto señalado.

## Productos y claves de unión

| Componente | Salida | Resolución conservada | Cautela para modelar |
|---|---|---|---|
| SINCA | Parquet por estación, contaminante y versión; observaciones y solapes separados | Etiqueta horaria original, coordenadas de cada estación | `ts_utc` queda nulo hasta confirmar reloj e intervalo; unidades todavía no verificadas |
| MERRA-2 meteorológico | NetCDF mensual `time × pixel` y catálogos | 419 píxeles nativos de 0,5° × 0,625°; horas originales HH:30 UTC | No redondear HH:30 a HH:00 sin una regla temporal explícita; procedencia de variables derivadas heredadas no recertificada |
| ERA5-Land | NetCDF versionado de `tp_1h_mm`, banderas y límites de intervalos | 9.725 píxeles de 0,1°; una hora | Unidades ausentes se documentan como inferidas del endpoint declarado; faltantes y negativos conservados |

Los demás campos ERA5-Land (`t2m`, `d2m`, `sp`, `u10`, `v10`) se referencian
desde el archivo nativo y **no se duplican**. El manifiesto del derivado identifica
ese archivo con ruta y SHA-256. No utilizar el campo acumulado `tp` como si ya
fuera precipitación de una hora.

Los catálogos nativos relacionan píxeles y comunas sin colapsar varios píxeles de
una misma comuna. Para píxeles fronterizos se mantiene la relación múltiple
píxel–comuna. Los identificadores de píxel pertenecen a cada producto/grilla;
no unir productos distintos por igualdad numérica de `pixel_id`.

## Dónde están los datos

Raíz del disco: `/Volumes/Datos/Asesorias_Data/AirPollution/`.

- SINCA: `derived/modelado/SINCA/v1/estacion=*/contaminante=*/version=*/`.
- ERA5-Land precipitación: `derived/modelado/ERA5Land/v1/meses/YYYY-MM/<revision>/`.
- ERA5-Land campos nativos: `data/contaminantes/ERA5Land/chile_nativo_01deg/`.
- MERRA-2: `data/contaminantes/MERRA2_meteo/chile_nativo_05x0625deg/`.
- Historial del coordinador: `derived/modelado/_ejecuciones/<ejecucion>/`.

Elegir una revisión explícita y guardar su manifiesto con cada experimento:
no mezclar todas las carpetas `version=*` o `<revision>` como observaciones
distintas. Los nuevos Parquet SINCA contienen WKB Point y CRS EPSG:4326
explícitos; no se presentan como GeoParquet sin su metadata estándar.

## Calidad y conservación

SINCA conserva valor validado/preliminar/no validado, celdas originales,
coordenadas, discrepancias comunales, faltantes y fila/archivo/SHA de origen.
La ubicación procede del catálogo geográfico vigente; no acredita por sí sola
que una estación no se haya trasladado durante su historia.
El ranking de solapes reutiliza la regla existente de `afg_lib.py`, cuyo código
exacto queda archivado. Las alternativas no seleccionadas permanecen en
`solapamientos.parquet`. Los rangos heredados sólo informan banderas/ranking;
no prueban unidades ni autorizan desechar una observación. Los candidatos UTC
son hipótesis bajo una zona IANA documentada, **no horas confirmadas**.
La revisión primaria está en [SINCA_SEMANTICA_PENDIENTE.md](SINCA_SEMANTICA_PENDIENTE.md):
hay referencias oficiales a UTC−4 fijo, excepciones de estaciones y diferencias
documentales en la etiqueta del intervalo. No aplicar DST civil automáticamente.
Las unidades observadas en fichas concretas no certifican todos los CSV históricos.

El lector heredado `scripts_superficie/afg_lib.py` aplica su propia conversión
IANA y alineación temporal. La preparación nueva no lo sustituye ni certifica
esas decisiones: no tomar automáticamente su panel como la matriz validada de
estos derivados. Usar las versiones explícitas y resolver las cautelas anteriores
antes de conectar un entrenamiento.

ERA5-Land resta acumulados consecutivos, excepto a las 01 UTC, cuando usa el
primer acumulado del ciclo. Los intervalos son `(t−1 hora, t]`, con etiqueta al
final. La primera 00 UTC de enero de 2000 no tiene antecedente local de diciembre:
se conserva como NaN con bandera. No se convierten negativos a cero. Véase
`ERA5LAND_MODELADO.md` para contrato y referencias oficiales.

MERRA-2 compara todos los valores, horas y píxeles de cada mes con las fuentes
diarias locales al generar una publicación nueva, además de verificar hashes y
reabrir NetCDF. La reutilización de una publicación ya certificada comprueba
su salida, referencias, código archivado y calendario; no vuelve a comparar
todos los valores ni a calcular los hashes de todas las fuentes diarias.
Los certificados
se guardan en `_control_transformacion/meses/`. El coordinador **nunca activa**
el retiro opcional de originales. Las fuentes se conservan para auditoría;
las copias de trabajo equivalentes sólo se retiran con una publicación validada.

Cada componente archiva código, versiones de bibliotecas y manifiestos de
entrada/salida. Esto permite reproducir la transformación desde sus fuentes
locales; no reconstruye por sí solo credenciales, disponibilidades remotas ni
procedencia histórica que no se registró durante una descarga antigua.

## Antes de entrenar

1. Confirmar unidades y semántica horaria SINCA antes del cruce definitivo UTC.
2. Definir la unidad de predicción (estación o grilla), el instante objetivo y
   qué observaciones estarían disponibles en ese instante, evitando información
   futura en validación o pronóstico.
3. Mantener las horas de adquisición satelital. Estos scripts no fabrican una
   observación satelital por hora, ni rellenan nubes o días sin cobertura.
4. Registrar selección de QA, revisión de cada producto y particiones
   temporales/espaciales del experimento. No ajustar imputación o escalamiento
   sobre el conjunto de prueba.

Los satélites ya publicados en sus formatos nativos se mantienen sin otra copia
masiva. Los descargadores continúan independientemente. GEOS-CF legado y los
productos aún no descargados no se convierten ficticiamente en coberturas
nacionales completas mediante relleno.

## Verificación del código

```sh
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -B -m unittest discover -s scripts_pipeline/tests -p 'test_*modelado.py' -v
```

Los ensayos de transacciones usan directorios temporales de prueba. Comprueban
valores, calendario, calidad, idempotencia y protección frente a fallos. Los
conversores también reabren y validan los productos reales antes de publicarlos.

## Primera ejecución: 15 de septiembre de 2026

MERRA-2 terminó el alcance enero de 2000–mayo de 2026: 317 meses,
231.552 marcas horarias y 419 píxeles. Sus certificados documentan la comparación
exacta de 873.182.592 valores de nueve variables. Una comprobación adicional
reabrió los 317 archivos y verificó hashes, dimensiones y calendario. Los
NetCDF nativos suman 2.160.700.837 bytes (2,16 GB decimales); las 9.648 fuentes
diarias utilizadas siguen protegidas. El día disponible de junio no forma un
mes completo y no está incluido en ese alcance.

ERA5-Land también terminó: 320 meses completos de enero de 2000 a agosto de
2026 y septiembre parcial con 216 horas, hasta el 9 de septiembre a las 23 UTC.
Son 233.976 marcas horarias, 9.725 píxeles y 4.250.257.916 bytes de precipitación
derivada. Se reabrieron los 321 archivos y se comprobaron hashes, calendario y
dimensiones; los 25.555.424 incrementos negativos y 355.417.750 NaN permanecen
sin ocultar. Son conteos de celdas, no de horas ni estaciones.
La ejecución completa es `20260915T175211Z-c133205aa48f4b3a868fd2fea6299b75`.

SINCA terminó a las 18:12:42 UTC: 403 series de 107 estaciones a partir de
1.685 CSV. Se publicaron y auditaron 806 Parquet: 94.311.869 filas seleccionadas
y 29.486 alternativas conservadas. Entre las seleccionadas hay 42.708.344
mediciones observadas y 51.603.525 faltantes explícitos; no son todas mediciones
validadas. La calidad observada se conserva: 19.735.047 validadas, 8.115.921
preliminares y 14.857.376 no validadas. Los Parquet suman 2.286.243.844 bytes;
la carpeta de trabajo quedó vacía. UTC y unidades siguen pendientes de confirmar.
La ejecución es `20260915T175637Z-f1692b748a934ba0b15ec6e8e5de743b`.
Sus 403 registros en `progreso.json` identifican las versiones del alcance
histórico. Existe además una versión de ensayo de la estación 117/PM2.5:
por eso el conteo físico es 808 Parquet, aunque este alcance usa 806. No unir
el ensayo y la versión histórica como si fueran observaciones distintas.

El cierre verificable está en `logs/control_preparacion_modelado_20260915.json`.
El seguimiento automático continúa para las descargas y no vuelve a ejecutar
estos planes completos por defecto. Para futuras ejecuciones consultar su
`progreso.json` y comprobar el identificador y alcance. Un
estado `running` o un simple archivo presente no equivale a finalización.
Para MERRA-2, la ejecución `20260915T174354Z-ca3ec2ac` tiene un `fin.json` de
317 meses y cero pendientes; comprobar siempre que el identificador de cierre
corresponda a la ejecución que se está revisando.

## Revalidar ERA5-Land después de actualizar un mes parcial

`scripts_pipeline/validar_revision_era5land_modelado.py` permite comprobar una
revisión ya publicada sin escribir datos. Primero exige las fuentes exactas
de su manifiesto. Si la pareja mensual NetCDF/manifiesto fue reemplazada por
una actualización, busca un respaldo registrado del mismo mes y verifica
ruta de origen, tamaño y SHA-256 de ambos archivos. No restaura ni sobrescribe
el mes actual; no modifica la identidad de la revisión antigua.

Ejemplo con la revisión de septiembre de la primera ejecución:

```sh
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -B scripts_pipeline/validar_revision_era5land_modelado.py \
  /Volumes/Datos/Asesorias_Data/AirPollution/derived/modelado/ERA5Land/v1/meses/2026-09/41939327ba8664b48afda6b1b4c0468195e5029ea937415c97b11b2f58418319
```

El resultado JSON identifica rutas originales y efectivamente leídas. Se
recalcula toda la precipitación y sus banderas, manteniendo las comprobaciones
de geometría, contrato, código archivado y archivos antes y después del cálculo.
Si no hay un respaldo exacto inequívoco, cambió el código del conversor, o un
insumo cambió durante la lectura, la validación se detiene: no omitir hashes
ni restaurar a mano sobre los archivos actuales. La herramienta no reconstruye
fuentes perdidas ni certifica procedencia remota ausente.

Los respaldos exactos necesarios para reproducir revisiones usadas en análisis
**no son temporales descartables**. Deben conservarse junto con sus registros.
El conversor original y los descargadores no se han modificado para añadir
esta comprobación independiente.

## Actualización incremental: 16 de septiembre de 2026

La nueva descarga ERA5-Land amplió septiembre de 216 a **240 horas**, desde
el 1 de septiembre a las 00 UTC hasta el 10 a las 23 UTC. Se preparó únicamente
ese mes con `preparar_era5land_modelado.py --mes 2026-09`, sin repetir el plan
histórico ni modificar fuentes o código. La revisión de precipitación nueva es
`226c80b59cd81bdc9195dd11afcb9ad80820226e74423e83ad964a76775e06ba`.
Conserva los 9.725 píxeles, NaN, negativos, banderas e intervalos nativos.

Las primeras 216 horas de las seis variables nativas son idénticas a la
publicación anterior; también coinciden la precipitación derivada y sus
banderas en ese tramo. La revisión de 216 horas sigue disponible y se validó
usando su respaldo registrado exacto. Elegir **una sola revisión de septiembre**
por experimento: no concatenar ambas como observaciones distintas. Septiembre
sigue parcial, y el último día no tiene todavía su intervalo de lluvia terminado
el 11 de septiembre a las 00 UTC.

El registro reproducible, con comando, hashes, validaciones y diario de
publicación, es `logs/actualizacion_modelado_era5land_20260916T0835.json`.
La auditoría de la descarga es `logs/control_era5land_actualizacion_20260916T0835.json`.
El cierre histórico del 15 de septiembre permanece intacto; SINCA y MERRA-2
no se volvieron a transformar. Los respaldos necesarios para reproducir
revisiones se conservan y no son temporales descartables.
