# Ejecución de la red adicional SNIFA, 22 de septiembre de 2026

El descargador y el procesamiento se ejecutaron en el repositorio Air-Pollution. Los originales y productos se guardaron en `/Volumes/Datos/Asesorias_Data/AirPollution/data/snifa_adicional`, como una red independiente de SINCA.

Se descargaron **1.947 archivos de 437 expedientes**, 5.94 GB, con **cero errores de descarga**. Una repetición verificó los hashes y reutilizó los 1.947 originales.

El procesamiento examinó 1.688 documentos candidatos y recuperó **1.050.488 registros de medición**, además de 7.394 códigos de eventos. La selección canónica contiene **837.116 filas horarias**. Terminó sin errores de lectura/extracción. Las tablas sin diseño reconocido y las páginas escaneadas permanecen identificadas en la auditoría; no se imputaron valores.

## Cobertura efectivamente extraída

Las fechas son el primer y último registro recuperado; **no implican continuidad mensual ni completitud horaria**. Cada fila corresponde a una estación, gas, fecha, etiqueta horaria y unidad.

| Estación | Primer registro | Último registro | Filas canónicas | Utilizables en reloj nativo* |
|---|---|---|---:|---:|
| Charrúa | 2016-01-01 | 2026-03-31 | 266.928 | 227.681 |
| El Peñón | 2022-04-01 | 2026-07-31 | 152.084 | 141.364 |
| Progreso | 2015-12-01 | 2026-03-31 | 263.952 | 224.326 |
| Quinel | 2012-12-01 | 2026-08-31 | 51.144 | 46.175 |
| SAPU | 2012-12-01 | 2026-08-31 | 103.008 | 97.783 |

*En total, **737.329 filas** superan los controles numéricos y de conflicto implementados. Esto no equivale a certificación oficial ni permite todavía una unión temporal por UTC. Los gases son NO₂, O₃, SO₂ y CO en El Peñón, Charrúa y Progreso; NO₂ y SO₂ en SAPU; NO₂ en Quinel.

## Calidad y límites conservados

- 6.806 filas canónicas incorporan banderas desde PDF de eventos. Una comprobación independiente del informe 59516 confirmó que sus 76 valores numéricos invalidados por código `2.h` quedaron excluidos de `usable_native`; los 227 localizadores de calidad coincidieron exactamente.
- 33.168 filas canónicas requieren revisar anexos de eventos de 7 expedientes. Están marcadas `quality_review_required` y excluidas de los datos utilizables.
- 38.571 filas tienen discrepancias numéricas entre publicaciones, incluidas diferencias de precisión/redondeo; 461 tienen discrepancias de código. Las banderas pueden solaparse. Se conservan todas las alternativas, sin promediarlas.
- 7.920 filas conservan fechas explícitas fuera del período administrativo SNIFA y llevan `outside_report_period`. Por ejemplo, el documento 11050 contiene abril de 2013 aunque el expediente está fechado en mayo.
- 466 documentos contienen señales de páginas que requieren revisión de imagen/OCR. No todas esas páginas contienen gases horarios. El Peñón tiene documentos desde diciembre de 2012, pero la serie horaria extraída comienza en abril de 2022.
- En algunos libros El Peñón, las matrices conservan valores con más decimales que las hojas horarias validadas. Se respeta la precisión de cada publicación y se señala la diferencia.
- Se preservan etiquetas 0–23, 1–24 y HHMM. No se asigna UTC ni se cambia la fecha de una etiqueta 24. Se conservan ppm, ppb, ppmv, ppbv y unidades de masa; no se hacen conversiones que requieran condiciones físicas no verificadas.
- Se excluyeron 12 filas de planillas validadas con fecha sin hora o sello 21:10, sin corregirlos por inferencia. Se excluyen también móviles de ocho horas, NO/NOx, muestreos de cinco minutos y estaciones ajenas al catálogo.
- Un aviso de descompresión del PDF 1296238 afecta un gráfico en la página 272; la tabla horaria está en la 271. Se verificaron las 5.952 filas de sus ocho series; la página con el aviso no aporta observaciones.

## Validación y reproducción

Se aprobaron **77 pruebas**: la suite ejecutó 76 y omitió una integración opcional; esa integración se ejecutó después con los originales externos y también pasó. Incluyen archivos reales, códigos de invalidación, tablas giradas y columnares, XLSX con extensión XLS, lectura alternativa de XLS, reanudación, procedencia y conflictos.

Los 12 controles sobre el producto final pasaron: conteo consistente, cinco estaciones, red separada, claves canónicas sin duplicados, ausencia de códigos inválidos/conflictos/revisión pendiente entre las filas utilizables, ninguna concentración negativa o ausente marcada utilizable, UTC sin inventar, descarga completa y manifiesto coincidente.

Para repetir la descarga y el procesamiento desde la raíz del repositorio:

```bash
bash scripts_pipeline/ejecutar_snifa.sh
```

El lanzador detecta el entorno local instalado. Consulte [la guía de ejecución](RED_ADICIONAL_SNIFA.md), [la auditoría de muestras](AUDITORIA_SNIFA_20260922.md) y [el catálogo de estaciones](../config/snifa_adicional/README.md).

Productos y auditorías en el disco externo:

- `processed/observaciones_horarias.parquet`: selección canónica y banderas.
- `processed/by_document/`: mediciones y eventos con procedencia original.
- `processed/conflictos.parquet` y `processed/cobertura.csv`.
- `processed/processing_report.json` y `processed/validation_20260922.json`.
- `metadata/download_manifest.json`, `metadata/ejecucion_final_20260922.log` y `metadata/pruebas_20260922.log`.

La definición y el código están en el repositorio; los originales voluminosos y la base procesada están en el disco externo.

## Huellas de la ejecución

- Procesador: `1.1.0`.
- SHA-256 Parquet canónico: `2aa177d9f0e3f8626d03c9e8381357a58eb81e43192b7aa802c5f03b4e055a55`.
- SHA-256 manifiesto: `2667107ec104e1155eb0273d7e1aba64d6f00ec715700b41415813f4e07b10db`.
- Firma de código/configuración: `a0b0540542c6c765c9b6055fda5a664b6faab8ae58b98da245b3f65f1d9b6be3`.
