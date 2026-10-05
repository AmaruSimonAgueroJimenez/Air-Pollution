# TROPOMI: otros gases en píxeles nativos de Chile

Contrato operativo documentado el 15 de septiembre de 2026. Este documento
describe el código y el procedimiento; **no certifica que las descargas, las
pruebas reales o el histórico hayan terminado**. El estado efectivo se consulta
en los registros y las transacciones indicados abajo.

## Alcance y significado científico

El motor `scripts_pipeline/descargar_tropomi_gases.py` incorpora cinco productos
L2, con recorte mediante `scripts_pipeline/_tropomi_gases_subset.py`. Es
independiente del proceso existente de NO₂: no lo sustituye ni modifica sus
archivos.

| Gas / argumento | Campo principal conservado de `PRODUCT` | Interpretación |
| --- | --- | --- |
| CO / `co` | `carbonmonoxide_total_column` | Columna total de monóxido de carbono. |
| SO₂ / `so2` | `sulfurdioxide_total_vertical_column` | Columna vertical de dióxido de azufre; conservar también los campos auxiliares sobre sensibilidad y supuestos de altura. |
| O₃ / `o3` | `ozone_total_vertical_column` | Columna total de ozono; no equivale al producto de columna troposférica ni al de perfil. |
| HCHO / `hcho` | `formaldehyde_tropospheric_vertical_column` | Columna vertical troposférica de formaldehído identificada por ese campo. |
| CH₄ / `ch4` | `methane_mixing_ratio` | Razón de mezcla de metano recuperada para la columna; no es una concentración puntual de superficie. |

La clasificación de los productos L2 y sus manuales están en
[SentiWiki: productos Sentinel-5P](https://sentiwiki.copernicus.eu/web/s5p-products).
Para interpretar campos, incertidumbres y cambios de procesador se debe usar
el PUM, IODD, ATBD y PRF correspondiente a la versión registrada en cada fuente;
están accesibles en la
[biblioteca oficial S5P](https://sentiwiki.copernicus.eu/web/s5p-documents).

Cada campo principal exige su variable original `_precision`. En CH₄ se exige
`methane_mixing_ratio_precision`, aunque existan variantes corregidas por sesgo
o bandas; las variantes presentes se conservan, pero no se inventa una precisión
para ellas. Las unidades y el empaquetamiento se copian del NetCDF original:
no se convierten a unidades de SINCA.

Estos datos corresponden al **momento de la pasada orbital**, no a una serie
horaria continua. Se conserva `time_utc` por píxel a partir de su scanline, junto
con `time` y `delta_time` originales. No se vuelve a sumar `delta_time` a
`time_utc`. En las salidas nuevas, `CHILE_SUBSET/observation_time_utc` proporciona
la hora nativa resuelta: copia el texto original cuando existe; si está vacío o
ausente, decodifica el desplazamiento nativo por píxel. Cuando las unidades de
`delta_time` incluyen `since fecha`, la fecha ya es su referencia CF y **no se
suma de nuevo `time`**. Si las unidades son sólo una duración, se suma una vez
al tiempo de referencia. Se contrastan `time` decodificado y `time_reference`
con la época declarada, y se conserva el método/procedencia del cálculo. Si
coexisten texto UTC y CF, se comprueba su concordancia (tolerancia de 1 ms).

El texto vacío de ciertos O₃/HCHO es un problema de producto reconocido por
su responsable; permanece intacto en `PRODUCT/time_utc`. No se sustituyen los
valores originales ni se promedian diferencias de tiempo entre píxeles de
una scanline. Véanse el [PUM HCHO, §8.4 y ficha temporal](https://sentiwiki.copernicus.eu/__attachments/1673595/S5P-L2-DLR-PUM-400F%20-%20Sentinel-5P%20Level%202%20Product%20User%20Manual%20Formaldehyde%20HCHO%202025-02.08.00.pdf)
y la [explicación oficial del problema UPAS](https://forum.dataspace.copernicus.eu/t/downloaded-s5p-l2-hcho-retrievals-with-an-empty-time-utc-variable/4363).
Los canónicos anteriores con `time_utc` completo siguen siendo válidos sin
reescribirlos para añadir el campo derivado.

OFFL y RPRO representan órbitas completas; los segmentos NRTI de
cinco minutos no aportan observaciones horarias nuevas y no son el formato
seleccionado por este motor. Véanse las especificaciones oficiales de
[HCHO](https://www.tropomi.eu/data-products/formaldehyde),
[CH₄](https://www.tropomi.eu/data-products/methane) y
[CO](https://www.tropomi.eu/data-products/carbon-monoxide).

Un modelo horario de superficie deberá tratar estas observaciones como
predictores satelitales de columna y resolver explícitamente su relación con
SINCA y otras covariables. El descargador no rellena horas, no convierte columnas
a superficie y no transforma estos gases en material particulado.

## Resolución espacial, cobertura y calidad

Se conservan las huellas nativas que intersectan la unión de comunas de Chile,
incluyendo continente, Juan Fernández, Desventuradas, Rapa Nui y Sala y Gómez,
sin Antártica. La búsqueda por cinco áreas es sólo un prefiltro de catálogo;
la selección final utiliza los verdaderos `latitude_bounds` y
`longitude_bounds` de cada píxel.

- No hay promedio comunal, cuadrícula remuestreada, interpolación ni filtro QA
  destructivo. Dos o más píxeles de la misma comuna permanecen separados.
- Se retiene una huella que toca Chile aunque su centro esté fuera. El
  `cod_comuna` corresponde al centro: `-1` indica centro fuera de la máscara y
  `0` conserva una zona sin demarcación; no significa dato faltante.
- Se conservan órbita, índices originales de scanline y ground pixel, y
  `pixel_id`. Este último se interpreta junto con el gas y la identidad/revisión
  de la fuente, no como identificador global entre gases distintos.
- Se copian todas las variables bajo `PRODUCT`, incluidos `SUPPORT_DATA`,
  kernels, priores, presiones, capas, esquinas, geometría, QA e incertidumbres.
  No se copian los grupos instrumentales externos a `PRODUCT`.
- Los valores empaquetados, atributos y ejes científicos se contrastan contra
  la selección de la fuente, leyendo nuevamente todas las variables de salida.
  Los ejes no espaciales conservan su longitud; el recorte publicado es
  inmutable, aunque un eje original fuese ampliable (`unlimited`).
- La máscara preparada se reutiliza únicamente en RAM por proceso, con caché
  máxima de dos entradas identificadas por ruta resuelta y hash de todos los
  componentes del shapefile. Una máscara modificada genera otra entrada; el
  hash se verifica antes de cada creación y al construir la entrada. Este
  índice exacto no simplifica ni aproxima la geometría y no deja temporales.
- No se inventan bounds. Una fuente sin geolocalización utilizable, o con
  huellas candidatas chilenas corruptas, se rechaza y conserva. Una salida con
  cero píxeles sólo se admite tras una selección geográfica válida, no por un
  fallo de lectura ni por una consulta vacía al catálogo.

«Máxima resolución» significa conservar la resolución realmente medida por
cada producto y fecha, no adjudicar a todos un tamaño único. Al nadir, HCHO
pasó de aproximadamente 3,5 × 7 km a 3,5 × 5,5 km el 6 de agosto de 2019;
CO y CH₄ pasaron de 7 × 7 km a 7 × 5,5 km. La huella concreta se toma del archivo,
no de estos tamaños nominales. Fuentes:
[HCHO](https://www.tropomi.eu/data-products/formaldehyde),
[CO](https://www.tropomi.eu/data-products/carbon-monoxide) y
[CH₄](https://www.tropomi.eu/data-products/methane).

Conservar QA no significa recomendar el uso indiscriminado de todos los
píxeles. Los filtros científicos se aplicarán después, de manera reproducible
y específica del producto/procesador. Los kernels y diagnósticos permiten
considerar la sensibilidad vertical y las limitaciones de las recuperaciones;
véanse las recomendaciones oficiales de
[CO](https://www.tropomi.eu/data-products/carbon-monoxide) y
[CH₄](https://www.tropomi.eu/data-products/methane).

## Fuentes de catálogo y periodo solicitado

El descargador consulta NASA CMR mediante Earthaccess, con autenticación
Earthdata configurada en el entorno o en `.netrc`, sin persistir credenciales
nuevas. No incluir credenciales en comandos, documentos ni registros.

| Gas | Colección CMR fijada, versión `2` |
| --- | --- |
| CO | `S5P_L2__CO_____HiR` / `C2087132178-GES_DISC` |
| SO₂ | `S5P_L2__SO2____HiR` / `C1918210292-GES_DISC` |
| O₃ total | `S5P_L2__O3_TOT_HiR` / `C1918209846-GES_DISC` |
| HCHO | `S5P_L2__HCHO___HiR` / `C1918210023-GES_DISC` |
| CH₄ | `S5P_L2__CH4____HiR` / `C2087216530-GES_DISC` |

El comienzo permitido por el código es `2018-04-30`, no el año 2000. Esto
define el periodo que se consulta, **no demuestra disponibilidad completa de
cada gas/día en esa colección**. La documentación oficial de
[HCHO](https://www.tropomi.eu/data-products/formaldehyde),
[CO](https://www.tropomi.eu/data-products/carbon-monoxide) y
[CH₄](https://www.tropomi.eu/data-products/methane) describe series históricas
y reprocesadas desde esa fecha.

El límite superior por defecto es ayer según la fecha local del Mac. Un límite
en 2026 no implica que exista todo 2026 ni que ayer ya esté publicado: los
productos OFFL pueden tener rezago. Para reproducibilidad, fijar `--hasta` y
conservar el catálogo de esa ejecución. Una consulta con cero fuentes queda
pendiente y se consulta nuevamente al reanudar.

Entre las producciones disponibles se selecciona una por gas/órbita, ordenando
colección, versión del procesador, preferencia RPRO sobre OFFL y fecha de
producción. Identidades CMR contradictorias o empates ambiguos detienen esa
unidad; no se resuelven escogiendo arbitrariamente un archivo.

## Ejecución acotada y prueba real previa

Desde la raíz del proyecto, este ejemplo propone consultar el histórico hasta
el 14 de septiembre de 2026. **Mostrar el comando no equivale a haberlo
ejecutado.**

```sh
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -B \
  scripts_pipeline/descargar_tropomi_gases.py \
  --gases co,so2,o3,hcho,ch4 \
  --desde 2018-04-30 --hasta 2026-09-14 \
  --trabajadores 2 \
  --reserva-gib 100 --staging-gib 10 --cuota-productos-gib 40
```

El modo histórico realiza primero una prueba real de **un gránulo por gas
seleccionado**, con hasta dos procesos simultáneos. Actualmente el día de prueba
es el menor entre `--hasta` y `2023-10-05`. Cada gas debe completar descarga,
identificación, recorte, lectura integral, publicación y retiro documentado,
con `pixeles_procesados > 0`, antes de ampliar el recorrido al histórico. Un
recorte geográficamente vacío puede ser válido como dato de ausencia de
intersección, pero no satisface esta prueba inicial del circuito científico.
El resultado queda en
`_control_gases/prueba_inicial.json`. Si falta una fuente o falla una prueba,
el supervisor queda en `pausado_prueba_inicial` y termina con código 2.

Para ejecutar exclusivamente la prueba explícita del día de referencia:

```sh
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -B \
  scripts_pipeline/descargar_tropomi_gases.py \
  --gases co,so2,o3,hcho,ch4 \
  --desde 2023-10-05 --hasta 2023-10-05 \
  --max-granulos-por-gas 1 --trabajadores 2 \
  --reserva-gib 100 --staging-gib 10 --cuota-productos-gib 40
```

`--max-granulos-por-gas` limita **por gas y por día**. No mantenerlo en un
histórico que se pretenda completo. Las pruebas limitadas quedan identificadas
como tales en los registros. Una prueba satisfactoria de cinco archivos no
certifica automáticamente todas las versiones históricas: cada archivo
posterior vuelve a pasar las mismas validaciones.

## Disco, concurrencia y pausas seguras

El destino es
`/Volumes/Datos/Asesorias_Data/AirPollution/data/contaminantes/S5P_TROPOMI/`
con la configuración local actual. El código exige una raíz en
`/Volumes/Datos/` y verifica el UUID del volumen
`54B3D309-A503-44C6-9229-581F3E4FECE3`; no debe continuar en una carpeta local
accidental si el disco está desmontado.

- Máximo **2 trabajadores adicionales**, un gránulo en procesamiento por
  trabajador. No son cinco descargas simultáneas ni un cambio al proceso NO₂.
- Reserva mínima **100 GiB libres**, compartida con las demás necesidades del
  disco. No es una cuota de descarga.
- Presupuesto inicial **10 GiB de staging**, global para estos cinco gases,
  con reservas coordinadas entre procesos y margen antes de cada gránulo.
- Cuota inicial **40 GiB de productos nuevos retenidos**, acumulada entre
  ejecuciones de estos gases. Es un límite operativo para revisar el crecimiento,
  **no una estimación del tamaño final del histórico**.
- Los límites contabilizan bloques asignados y reservas conservadoras; una
  pausa puede ocurrir antes de que el tamaño visible alcance 10 o 40 GiB. El
  código también rechaza una transferencia individual superior a 3 GiB.

Un bloqueo del supervisor impide dos instancias de este motor, y cada gas tiene
su propio bloqueo y staging. Alcanzar un límite registra
`pausado_limite_seguro` y hace terminar el supervisor con código 75. No eliminar
fuentes protegidas ni elevar cuotas a ciegas para evitar la pausa: revisar el
espacio efectivo, el crecimiento observado y los demás descargadores primero.

## Qué conservar y cómo reanudar

Dentro de cada carpeta `CO`, `SO2`, `O3`, `HCHO` o `CH4` se mantienen:

| Ruta relativa | Función |
| --- | --- |
| `chile_l2_nativo_v1/year=AAAA/month=MM/*.chile.nc` | Datos científicos recortados, sin degradar resolución. |
| Archivo `.json` junto a cada NetCDF | Transacción con hashes de fuente, salida, máscara, código y resumen de validación. |
| `_catalogos_gases/<ejecución>/<día>.<uuid>.json` | Snapshot CMR, candidatos, revisiones y selección por órbita; cada consulta conserva una identidad propia. |
| `_staging_gases/<identidad>/` | Descargas y recortes en curso o protegidos tras un fallo; no son automáticamente descartables. |

En `_control_gases/` se conservan los diarios JSONL por gas, la configuración y
avance de ejecución, la prueba inicial, el cierre y el archivo de código en
`codigo/<hash>/`, con versiones de dependencias y Python. Son parte de la
reproducibilidad del análisis, no «basura temporal». El registro de avance
indica el último día consultado; no reemplaza la comprobación de transacciones
individuales ni prueba por sí solo cobertura sin huecos.

Tras reconectar disco e Internet, **reanudar con el mismo comando y las mismas
fechas/cuotas**, siempre que no siga activo el supervisor anterior. El motor
vuelve a consultar los catálogos, valida publicaciones previas y aprovecha
fuentes/parciales que coincidan con su prueba durable. No basta que exista un
NetCDF para considerarlo terminado. Si cambian máscara, contrato o metadatos
CMR de una publicación, se requiere reconciliación explícita: no se sobrescribe
silenciosamente el producto previo.

Antes del primer borrado se reabren los datos publicados, se verifican sus
hashes y la fuente, y se escriben de forma durable la transacción y los eventos
`granulo_validado_pre_borrado` y `retiro_temporales_autorizado`. Después se
registra `crudo_eliminado_post_validacion`. Únicamente se retiran fuentes y
temporales identificados dentro de esa transacción; los parciales de descarga
deben demostrar que son prefijos de la misma fuente.

Un fallo de red, geolocalización, recorte, validación o publicación **no autoriza
a borrar el crudo completo ni una salida anterior útil**. Los fallidos quedan
protegidos; algunos parciales requieren diagnóstico específico y no se
resuelven repitiendo indiscriminadamente el comando. La limpieza automática es
una consecuencia de una publicación científica validada, nunca un barrido
general del disco.

## Reanudación autorizada el 19 de septiembre de 2026

Ante la petición «ya completa tropomi», se autoriza la ampliación propuesta
de **40 a 45 GiB acumulados** para los cinco gases. Se mantienen dos
trabajadores como máximo, 10 GiB de staging y 100 GiB de reserva externa.
Los 45 GiB no son adicionales ni garantizan que quepa todo el histórico;
otra pausa por capacidad requiere revisar la proyección y una nueva decisión.

El lanzamiento reproducible de esta reanudación está en
`logs/reanudar_tropomi_gases_20260919.py`: por defecto sólo verifica; con
`--lanzar` conserva los estados anteriores y arranca una única ejecución.
El recibo `logs/reanudacion_tropomi_gases_20260919_lanzamiento.json`, si existe,
identifica el proceso y su log; no equivale a una descarga completa.
El comando conserva el rango 2018-04-30–2026-09-14 y vuelve a consultar los
catálogos y validar las publicaciones existentes para recuperar también los
cuatro fallos de red y los 22 gas-días sin fuentes del recorrido anterior.
No usa el último día consultado como prueba de que todo lo anterior esté completo.

Antes de esta reanudación se refuerza la creación durable de directorios:
las entradas nuevas y sus padres se sincronizan antes de permitir el retiro
de una fuente. No cambia ningún campo científico, filtro, resolución o
regla de selección. El motor archiva la nueva versión de código y conserva
las versiones anteriores; NO2 y el modelado existente siguen independientes.
