# Actualización ERA5-Land — 17 de septiembre de 2026

Se incorporó únicamente la revisión de septiembre con **264 horas**, desde el
1 de septiembre a las 00 UTC hasta el 11 a las 23 UTC. Los 320 meses completos
de enero de 2000 a agosto de 2026 no se volvieron a procesar.

La nueva precipitación horaria conserva los **9.725 píxeles nativos de 0,1°**,
sus códigos comunales, límites temporales y banderas. Las primeras 240 horas,
sus coordenadas y todas sus banderas son idénticas bit a bit a la revisión
anterior. Se reabrió el producto y se recalculó toda la fórmula contra las
fuentes exactas. El derivado nuevo ocupa 4.804.752 bytes.

Revisión seleccionable:
`9e3b9871baecb219dfbb4fef3a670a028ac453269336256d4265e5beb7ced255`.

Está en el disco externo, bajo
`derived/modelado/ERA5Land/v1/meses/2026-09/<revisión>/`.
Con esta revisión y los meses históricos, la colección seleccionada suma
234.024 marcas horarias y 4.251.193.486 bytes de precipitación.
**Elegir una sola revisión de septiembre: no concatenarlas.**

## Reproducción y evidencia

El conversor existente se ejecutó con Python 3.14:
`scripts_pipeline/preparar_era5land_modelado.py --mes 2026-09`.
El control acotado está archivado en
`logs/actualizar_modelado_era5land_20260917T0445.py`: exige las fuentes,
código, volumen y revisión exactos, reserva de 100 GiB y ausencia de productores
concurrentes. No usarlo para otra fecha o insumos distintos sin un nuevo control.

La ejecución, hashes de entrada/salida, diario durable, comprobaciones y
comparación completa constan en
`logs/actualizacion_modelado_era5land_20260917T0445.json`.
El nativo se auditó en `logs/postflight_era5land_20260917T0344.json`.
La revisión anterior de 240 horas se revalidó usando su respaldo exacto en
`logs/revalidacion_era5land_revision240_20260917T0344.json`.

## Límites y conservación

Septiembre sigue parcial. Para completar la lluvia del día 11 UTC falta el
intervalo terminado el día 12 a las 00 UTC. Se conservan 401.016 celdas NaN y
43.438 incrementos negativos, sin imputar ni recortar a cero. Las unidades
nativas ausentes siguen declaradas como inferidas del endpoint, no observadas.

Las revisiones anteriores y sus respaldos exactos permanecen protegidos:
son necesarios para reproducir análisis y no son temporales descartables.
El descargador retiró sólo sus cinco fuentes de trabajo tras validar y registrar
la publicación. La simulación posterior del retiro de legados encontró cero
fuentes elegibles; junio de 2026 permanece protegido. No se retiraron fuentes
SINCA ni MERRA-2. Sus transformaciones históricas no se repitieron.

El contrato general y las cautelas para cruces con SINCA siguen en
[PREPARACION_MODELADO.md](PREPARACION_MODELADO.md) y
[ERA5LAND_MODELADO.md](ERA5LAND_MODELADO.md).
