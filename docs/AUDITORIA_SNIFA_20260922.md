# Auditoría acotada de extracción SNIFA - 22 de septiembre de 2026

Se revisaron ocho documentos históricos nuevos, independientes de los originales usados inicialmente como pruebas del lector PDF. Se contrastaron fechas, gas, estación, unidad y dos valores por documento con extracción positiva contra el texto original; también se inspeccionaron visualmente cabeceras columnarias, una matriz rotada y tablas como imagen. Esta auditoría valida las muestras indicadas, no certifica toda la serie descargada.

El cambio resultante fue añadir lectura de anexos PDF `DATOS COLUMNA`: fecha y hora `YYYYMMDDHHMM`, cabecera de gas, unidad y promedio horario por columna. Se excluyen las columnas móviles de ocho horas, NO, NOx, partículas y meteorología. La continuidad entre páginas exige dimensiones iguales y horas consecutivas; una estación explícita no configurada impide heredar la identidad anterior. Los códigos y blancos permanecen como valores nulos con su texto original. No se convierten unidades ni se asigna zona horaria.

## Muestras y contraste con originales

Los recuentos incluyen posiciones horarias con códigos de invalidación; «numéricos» significa celdas convertibles a número, sin una nueva validación ambiental. Las páginas son posiciones del archivo PDF, comenzando en uno.

| Documento SNIFA y período | Extracción y extremos con valores numéricos | Dos comprobaciones contra el original |
| --- | --- | --- |
| [4653, SEB-15919, expediente 2856](https://snifa.sma.gob.cl/SeguimientoAmbiental/Ficha/2856), enero 2013 | 2.232 posiciones, 2.194 numéricas. SAPU NO2/SO2 y Quinel NO2: 744 por serie; 1 a 31 enero, etiquetas 1 a 24. | SAPU NO2, 1 enero h1 = **5,6 µg/m3N**, p16; SAPU SO2, 31 enero h24 = **5,2 µg/m3N**, p24. Coinciden fecha, columna y unidad. |
| [35136, SEB-16995, expediente 18732](https://snifa.sma.gob.cl/SeguimientoAmbiental/Ficha/18732), febrero 2014 | 2.016 posiciones, 1.845 numéricas. Mismas tres series: 672 por serie; 1 a 28 febrero, etiquetas 1 a 24. | SAPU NO2, 1 febrero h1 = **17,3 µg/m3N**, p16; SAPU SO2, 28 febrero h24 = **3,9 µg/m3N**, p24. Las matrices están rotadas 90 grados. SAPU NO2 produce **603** valores numéricos, exactamente el número de datos válidos publicado al pie de la tabla. |
| [141627, DATOS CHARRUA COLUMNA, expediente 59516](https://snifa.sma.gob.cl/SeguimientoAmbiental/Ficha/59516), enero 2017 | 2.976 posiciones, 2.825 numéricas. NO2/O3/SO2/CO: 744 por gas; 1 a 31 enero, 0000 a 2300. | Charrúa CO, 1 enero 0000 = **0,1 µg/m3N**, p1; NO2, 31 enero 2300 = **4 µg/m3N**, p8. Se verificó que O3 móvil y CO móvil son columnas distintas. |
| [141630, DATOS PROGRESO COLUMNA, expediente 59516](https://snifa.sma.gob.cl/SeguimientoAmbiental/Ficha/59516), enero 2017 | 2.976 posiciones, 2.530 numéricas. Cuatro gases: 744 por gas; 1 a 31 enero, 0000 a 2300. | Progreso CO, 1 enero 0000 = **0,2 µg/m3N**, p1; O3, 31 enero 2300 = **2 µg/m3N**, p7. La estación se obtiene de su cabecera explícita. |
| [202321, DATOS CHARRUA, expediente 81626](https://snifa.sma.gob.cl/SeguimientoAmbiental/Ficha/81626), enero 2019 | 2.976 posiciones, 2.881 numéricas. Cuatro gases: 744 por gas; 1 a 31 enero, 0000 a 2300. | Charrúa CO, 1 enero 0000 = **0,2 ppm**, p1; O3, 31 enero 2300 = **15 ppb**, p9. Las unidades ppb/ppm se verificaron también visualmente. |
| [128909, MCA 053-04 07 01-17 v1, expediente 55004](https://snifa.sma.gob.cl/SeguimientoAmbiental/Ficha/55004), El Peñón enero 2017 | **0** posiciones extraídas: tablas horarias como imagen, señaladas para revisión. No hay fechas extraídas que reportar. | La inspección visual de p44 confirma SO2: 1 enero h0 = **1,6 µg/m³N**; 31 enero h2300 = **1,7 µg/m³N**. Son valores visibles que el lector actual **no extrae**; no fueron añadidos manualmente a la salida. |
| [128905, SEB-20664, expediente 55003](https://snifa.sma.gob.cl/SeguimientoAmbiental/Ficha/55003), Masisa enero 2017 | **0** posiciones extraídas. El informe incluye imágenes y resúmenes, sin recuperación horaria automática en esta muestra. | Se comprobó visualmente p26: tabla de máximos y promedios, no una serie horaria. No se convirtieron sus cifras de resumen en observaciones. Las tablas y gráficos posteriores requieren revisión o anexos alternativos. |
| [31237, Inf01E1.13-243, expediente 16684](https://snifa.sma.gob.cl/SeguimientoAmbiental/Ficha/16684), emisiones industriales de 2013 | **0** posiciones extraídas, resultado correcto como control negativo. | Informe de incineración/coincineración y emisiones industriales; no acredita observaciones ambientales de SAPU o Quinel. No corresponde comparar valores ambientales horarios. |

## Identidad, antigüedad y límites

- **SAPU y Quinel tienen evidencia horaria ambiental desde el 1 de enero de 2013.** En el documento 4653, SAPU NO2 comienza con 5,6; SAPU SO2 con 3,7; Quinel NO2 con 14,7, todos en µg/m3N y etiqueta horaria 1. Esto acredita datos en esa fecha, no la instalación de las estaciones ni continuidad hasta el presente.
- El documento 4653 contiene también páginas de **Policlínico MASISA**, correspondientes a meteorología. Ninguna se atribuyó a SAPU o Quinel: la salida está restringida a las matrices de gases de p16, p20 y p24. La regresión sintética adicional comprueba que un encabezado `ESTACION POLICLINICO` no hereda Charrúa.
- **El descubrimiento amplio conserva documentos industriales.** La revisión independiente del proceso principal identificó también el documento 1660 del [expediente 1343](https://snifa.sma.gob.cl/SeguimientoAmbiental/Ficha/1343), período 2012, como gases de chimenea AutoFlame; produjo cero observaciones ambientales. Por ello, una fecha 2012 en el manifiesto no debe usarse como inicio de SAPU/Quinel.
- **Unidades publicadas dispares:** los anexos Charrúa/Progreso de enero de 2017 imprimen µg/m3N para CO con valores como 0,1; el anexo Charrúa de enero de 2019 imprime ppm. El lector conserva ambas etiquetas. No se ha resuelto si el anexo de 2017 contiene un error editorial; esas series requieren comprobar la unidad antes de compararlas o convertirlas.
- Un resultado vacío indica cobertura no establecida por este lector, no ausencia de mediciones. El Peñón y algunos informes Masisa requieren sus planillas/anexos o una extracción de imágenes supervisada. Los ejes de gráficos, los resúmenes y los promedios móviles no sirven para rellenar esas lagunas.

## Reproducibilidad y verificación

Los originales permanecen fuera del repositorio, bajo `/Volumes/Datos/Asesorias_Data/AirPollution/data/snifa_adicional`. El archivo `metadata/download_manifest.json` resuelve cada `document_id` a su `relative_path`, URL, período y SHA-256. No se modificaron los originales ni se incorporaron PDF grandes al repositorio.

Versión inicial auditada de `scripts_pipeline/_snifa_pdf.py`, SHA-256: `7be7e9c6a5a2c688040a9a59f639a8d470f48b0f3917e266ab71f39b71d7d6d1`. **11 pruebas pasan** en esa revisión, incluyendo originales locales, columnas móviles, coma decimal, códigos, blancos, separación de estaciones, horas originales, contexto, fechas inválidas y rotación. Cada anexo columnario de 744 horas tardó aproximadamente 2,4 segundos en esta ejecución; el lector solo calcula geometría detallada en páginas candidatas.

```sh
SNIFA_TEST_FIXTURES_ROOT='/Users/amaruagueroj/.codex/.chatgpt-projects/g-p-6ab00989aedc8191997dcf9bcc53cbdf/investigacion_sinca_20260922' \
  /Users/amaruagueroj/Asesorias_Data_local/AirPollution/runtime_snifa/bin/python \
  -m unittest scripts_pipeline.tests.test_snifa_pdf -v
```

La ejecución general del descargador/agregador y sus recuentos finales son verificaciones separadas de esta auditoría del lector PDF.

## Ampliación: eventos de calidad en anexos separados

La comprobación posterior de la pareja **DATOS 141627 / EVENTOS 141628**, ambos del expediente 59516, demostró que los códigos de calidad del PDF separado deben acompañar a las concentraciones. `parse_pdf_events` extrae **227 eventos** de los cuatro gases horarios; todos coinciden por estación, gas, fecha y hora con las observaciones del anexo DATOS. **76 eventos invalidan celdas numéricas** (19 por gas, código `2.h`), además de 151 celdas que ya eran no numéricas en DATOS. Por ejemplo, el 27 de enero de 2017 a las 0000, SO2 = 13, O3 = 41, CO = 6,1 y NO2 = 123 tienen todos el código `2.h` en la página 6 de EVENTOS. Esos valores no deben considerarse utilizables por el mero hecho de ser números.

La nueva API devuelve filas `resolution='quality_event'`, valor nulo, código original, unidad `unknown` y localizador propio del anexo. Mantiene separado el lector de concentraciones. El agregador debe unir los eventos antes de deduplicar y conservar ambas procedencias. `tables_recognized` y `stations_recognized` permiten distinguir una tabla reconocida sin códigos de un anexo no extraíble; cualquier incidencia de extracción exige comprobar también cobertura parcial.

La versión ampliada tiene SHA-256 `113efb1bdd56e9495a3f38b38e8b517951fc72c85b34744646af88f02baf1ca1`. **14 pruebas pasan**, incluida la regresión real de las 76 celdas, las páginas inicialmente vacías, la exclusión de móviles/NO/NOx y el rechazo de la herencia desde Policlínico. Para ejecutar también la pareja real, añadir `SNIFA_TEST_DOWNLOAD_ROOT='/Volumes/Datos/Asesorias_Data/AirPollution/data/snifa_adicional'` al comando anterior. La integración completa y la regeneración del conjunto final corresponden al agregador.
