# SINCA: evidencia temporal y de unidades aún pendiente de vincular a cada serie

Consulta de fuentes primarias: **15 de septiembre de 2026**. Revisión de sólo lectura: no se modificaron CSV, Parquet, descargadores, conversores ni `config/sinca/politica_temporal.json`. Este documento no habilita conversiones automáticas ni declara globalmente confirmadas las unidades o las horas UTC.

## 1. Lo demostrado oficialmente sobre el reloj

El **D.S. 61/2008 de MINSAL**, texto actualizado en 2009, define en su artículo 2(t) el horario continental de invierno, GMT−4, para el monitoreo. Su artículo 20(4) remite expresamente a esa zona horaria para reportar datos horarios. No prescribe seguir los cambios civiles de verano. [Texto oficial BCN](https://www.bcn.cl/leychile/navegar?f=2009-09-21&i=281728).

La **Resolución Exenta 1449/2023 de la SMA**, vigente desde el 1 de enero de 2025 según su disposición segunda, mantiene GMT−4. En su sección 2.2(b) exige ese reloj en instrumentos y adquisición, con desviación máxima de ±2 minutos. [Texto oficial BCN](https://www.bcn.cl/leychile/navegar?idNorma=1195320). El [sitio de normas del MMA](https://normasaire.mma.gob.cl/monitoreo/tipos-de-monitoreo/) enlaza esta resolución como referencia técnica vigente.

Esto establece un contrato normativo, **no demuestra por sí solo que cada CSV histórico cumpla el reloj**. Existe una excepción expresamente documentada por SINCA: la ficha de Escuela E-10 advierte un desfase técnico por utilizar la hora normal en lugar de UTC−4. La ficha no delimita exactamente el período afectado ni demuestra una corrección retrospectiva. [Ficha oficial Escuela E-10, id del portal 274](https://sinca.mma.gob.cl/index.php/estacion/index/id/274).

Por tanto, la hipótesis `hora_local_civil_sinca_sin_offset` y las zonas IANA de la política local **no son hechos confirmados del exportador**. Aplicar indiscriminadamente `America/Santiago`, `America/Coyhaique` o `America/Punta_Arenas` introduciría cambios civiles que el contrato normativo de monitoreo no prescribe. Tampoco corresponde convertir todo a UTC−4 sin comprobar excepciones y períodos. Los datos anteriores a 2008 requieren evidencia histórica adicional.

## 2. Diferencia oficial en la etiqueta del intervalo

Los documentos no presentan el mismo ejemplo:

| Fuente | Etiqueta de hora del ejemplo | Período descrito |
| --- | --- | --- |
| D.S. 61/2008, artículo 2(i) | 17 | 17:01 a 18:00, inclusive |
| R.E. 1449/2023, glosario «Hora» | 18 | 17:01 a 18:00, inclusive |

El primero ubica la etiqueta al comienzo nominal y el segundo al término del intervalo. Ambos describen promedios horarios; la resolución también exige al menos 75% de datos de la hora. [D.S. 61](https://www.bcn.cl/leychile/navegar?f=2009-09-21&i=281728), [R.E. 1449](https://www.bcn.cl/leychile/navegar?idNorma=1195320).

**No se encontró una especificación del exportador que permita trasladar esa diferencia automáticamente a todos los CSV**, ni prueba de que SINCA cambiara etiquetas en una fecha concreta o reetiquetara el histórico. No debe inferirse un cambio efectivo el 01-01-2025 sólo de la entrada en vigencia normativa. Falta vincular estación, contaminante, intervalo de fechas, configuración del equipo y transformación del portal.

La salida de modelado con `ts_utc` nulo y semántica pendiente sigue siendo prudente. Los candidatos bajo una zona IANA son hipótesis, no timestamps certificados. Para unir ERA5-Land se necesitará conocer tanto el reloj como si la etiqueta representa inicio o fin de la hora; una de esas comprobaciones no sustituye a la otra.

## 3. Unidades comprobadas en series concretas del portal

Las fichas oficiales de [Escuela E-10](https://sinca.mma.gob.cl/index.php/estacion/index/id/274) y [Quilicura I](https://sinca.mma.gob.cl/index.php/estacion/index/id/149) muestran estas unidades para sus series. Además, se leyeron en memoria los encabezados de exportaciones **TXT horarias** de Escuela E-10, código del exportador `RII/222`, período 10–17 de julio de 2019:

| Contaminante | Unidad en ficha y encabezado TXT | Macro horario comprobado |
| --- | --- | --- |
| PM2.5 | µg/m³, sin sufijo N | `PM25.horario.horario.ic` |
| PM10 | µg/m³N | `PM10.horario.horario.ic` |
| NO₂ | ppb | `0003.horario.horario.ic` |
| O₃ | ppb | `0008.horario.horario.ic` |
| SO₂ | ppb | `0001.horario.horario.ic` |
| CO | ppm | `0004.horario.horario.ic` |

Ejemplo reproducible de lectura pública: [exportación TXT de CO, Escuela E-10, julio de 2019](https://sinca.mma.gob.cl/cgi-bin/APUB-MMA/apub.tsindico2.cgi?outtype=txt&macro=.%2FRII%2F222%2FCal%2F0004%2F%2F0004.horario.horario.ic&from=190710&to=190717&path=%2Fusr%2Fairviro%2Fdata%2FCONAMA%2F&lang=esp&rsrc=&macropath=). Los demás encabezados proceden de los enlaces de registros horarios de la misma ficha, conservando su código de parámetro. No se guardaron archivos de observaciones nuevos ni se enviaron datos privados.

Los encabezados TXT confirman resolución de base de datos de una hora para esas macros. También exponen reglas de presentación: redondeo de PM10/PM2.5/O₃ a cero decimales y CO/NO₂/SO₂ a dos, según la condición temporal de la macro desde mayo de 2017; no son necesariamente valores instrumentales sin procesamiento. La inscripción de promedio móvil `1(1) centered` no basta para deducir la convención de etiqueta horaria del instrumento.

**Alcance de la comprobación:** son unidades observadas en esas fichas/macros y muestras, no una certificación de los archivos CSV locales completos, todas las estaciones ni todos los períodos. Hace falta relacionar cada archivo con su macro, versión y rango, y contrastar que la descarga CSV no aplique una transformación adicional. El enlace de ayuda de configuración CSV del portal (`https://sinca.mma.gob.cl/manual/`) devolvió 404 durante la consulta.

La R.E. 1449, sección 5.3, dispone que los gases se reporten en las unidades configuradas en el instrumento, sin factores; esto refuerza que **las unidades de una norma de concentración no permiten adivinar las del archivo**. [Texto oficial](https://www.bcn.cl/leychile/navegar?idNorma=1195320). No aplicar conversiones ppb↔µg/m³ o ppm↔mg/m³ sin especie, condiciones de referencia y metadatos suficientes. No borrar la distinción µg/m³ frente a µg/m³N.

## 4. Qué no confundir

La página general de monitoreo en línea presenta PM10/PM2.5 como promedios móviles de 24 horas y CO de ocho horas; O₃/NO₂/SO₂ se muestran como promedios de una hora. Es otra presentación, no evidencia de que la macro `horario.horario` sea una media móvil de 24 u ocho horas. [Explicación oficial SINCA](https://sinca.mma.gob.cl/index.php/intro/index/fullscreen/1).

La ficha incluye un campo denominado «Huso horario» junto a coordenadas UTM con valor 19. No interpretarlo como offset UTC: no aporta un reloj utilizable para la serie.

## 5. Seguimiento reproducible antes del cruce definitivo

1. Conservar etiquetas originales y calidad; mantener UTC e intervalo como no confirmados.
2. Crear evidencia por estación, parámetro y período que vincule macro/ficha/exportación con hash del archivo local. Registrar expresamente las excepciones de reloj.
3. Distinguir contrato normativo, configuración del portal y comportamiento observado; no convertir una hipótesis IANA o UTC−4 en dato confirmado.
4. Confirmar la etiqueta de intervalo y el tratamiento de medianoche por versión de exportador. No reconstruir DST, desplazar horas ni promediarlas para «resolver» duplicados sin esa evidencia.
5. Versionar cualquier conversión aprobada en una capa nueva, con reglas, fuentes y pruebas; conservar los originales y los derivados actuales.

No se contactó a instituciones ni se aplicó ninguna de esas acciones de seguimiento durante esta revisión.
