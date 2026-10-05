# Actualización ERA5-Land, 18 de septiembre de 2026

Se publicó y revalidó únicamente la precipitación de septiembre con **288 horas**,
desde el 1 de septiembre a las 00 UTC hasta el 12 a las 23 UTC. Los 320 meses
completos de enero de 2000 a agosto de 2026 no se volvieron a procesar.
La ejecución incremental finalizó el 2026-09-18T04:58:31.349372+00:00.

## Producto y reproducción

Revisión seleccionable:
`167b91d61a79a6bc4a37eb7f4306f41e33b2914b34e5edb70daacc7fac6b4a40`.

Está en el disco externo bajo
`derived/modelado/ERA5Land/v1/meses/2026-09/<revisión>/`.
El NetCDF ocupa **5.085.468 bytes** y conserva 9.725 píxeles de 0,1°,
coordenadas, relaciones comunales, banderas y límites de intervalos.
Su SHA-256 es
`84026874282f1bc1e87a46ecb458fe78efcf5a8e376f0f26fdfa37c1b8107d47`.

El conversor existente es `scripts_pipeline/preparar_era5land_modelado.py`,
limitado mediante `--mes 2026-09`. El control congelado
`logs/actualizar_modelado_era5land_20260918T0357.py` fue preparado durante
el control anterior y ejecutado ahora. Exige fuente, entorno, código, UUID y
revisión exactos, reserva de 100 GiB y ausencia de productores concurrentes.
Sin argumentos hace sólo preflight; con `--ejecutar` publica. Este wrapper
de una sola ejecución rechaza un destino ya existente: no relanzarlo ciegamente.
Para reutilización idempotente se mantiene el conversor y su validación de
identidad. No usar este control para otras fuentes o fechas sin revisar sus guardas.

La evidencia de la ejecución, referencias protegidas, fórmula recalculada,
diario durable y hashes está en
`logs/actualizacion_modelado_era5land_20260918T0457.json`.
El cierre nativo previo es `logs/postflight_era5land_20260918T0357.json`;
la revisión antigua de 264 horas se revalidó contra su respaldo exacto en
`logs/revalidacion_era5land_revision264_20260918T0357.json`.
Se preservan sus fechas de comprobación: no se presentan como auditorías
nativas repetidas durante esta ejecución.

## Validación y límites

La fórmula de las 288 horas se volvió a calcular al reabrir el nuevo producto.
Las primeras 264 horas, precipitación, banderas, límites y coordenadas
son idénticas bit a bit a la revisión anterior. Los tres eventos del diario
son preparación, validación previa a publicar y publicación.

La colección seleccionada suma **234.048 marcas horarias** y
**4.251.474.202 bytes** de precipitación. Elegir una sola revisión de septiembre;
**no concatenar las revisiones**.

Septiembre permanece parcial. Para completar la lluvia del día 12 UTC falta
el intervalo que termina el 13 a las 00 UTC. La precipitación es cantidad en mm
para el intervalo `(t−1h,t]`, etiquetado al final. Permanecen **437.472 NaN**
y **48.889 incrementos negativos**, sin imputar ni truncar a cero.
Las unidades nativas ausentes se declaran inferidas del endpoint, no observadas.
El nativo tiene píxeles insulares sin valores válidos; conservar sus faltantes
no equivale a contar con mediciones en todas las islas.

Los campos meteorológicos nativos no se duplican. Se conservaron fuentes,
revisiones y respaldos exactos. El staging derivado quedó vacío por publicación,
sin limpieza manual. Esta actualización no retiró fuentes ni repitió SINCA,
MERRA-2 o el histórico ERA5-Land. Las cautelas de SINCA sobre UTC y unidades
siguen vigentes en `PREPARACION_MODELADO.md`.
