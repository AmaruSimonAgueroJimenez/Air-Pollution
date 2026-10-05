# Actualización ERA5-Land: 19 de septiembre de 2026

Se actualizó únicamente septiembre: **312 horas hasta el 13 de septiembre de 2026 a las 23 UTC**, con 9.725 píxeles nativos de 0,1°. Septiembre y 2026 siguen parciales.

La nueva revisión de precipitación es `9f18c92929461c38c561a16a041f0031fbd17fc1465cae25d19ca78256d8a4a1`. Elegir esta revisión o una anterior explícitamente, nunca concatenarlas como observaciones distintas. La colección seleccionada conserva 320 meses cerrados de enero de 2000 a agosto de 2026 y septiembre parcial: 234.072 marcas horarias; los NetCDF de precipitación suman 4.251.763.142 bytes.

El nuevo NetCDF de precipitación tiene 5.374.408 bytes, SHA-256 `53671228876f6d16eb4fd5596e5f2eaf83a4e3bf79045e96ecd3f813930bfaf8`. Se recalcularon y revalidaron todos sus valores y banderas; las primeras 288 horas coinciden bit a bit con la revisión anterior. Se mantienen 473.928 celdas NaN y 49.182 incrementos negativos en septiembre; no se imputaron ni truncaron. El día 13 todavía carece del intervalo de lluvia que termina el 14 a las 00 UTC.

## Reproducibilidad y conservación

- Conversor congelado: `scripts_pipeline/preparar_era5land_modelado.py` (SHA-256 `2aabcfc96ffe6e0821480379434c9abea5c24590eb0b80058a4371c92c19bc78`).
- Envoltorio acotado con preflight: `logs/actualizar_modelado_era5land_20260919T0215.py`. Sin argumentos no escribe; `--ejecutar` sólo prepara septiembre y rechaza una revisión ya existente.
- Resultado y comando exacto: `logs/actualizacion_modelado_era5land_20260919T0215.json`.
- Auditoría nativa: `logs/postflight_era5land_20260919T0215.json`.
- Revalidación íntegra de la revisión anterior usando su respaldo registrado: `logs/revalidacion_era5land_revision288_20260919T0215.json`.

Los seis campos nativos fueron reabiertos; las primeras 288 horas son idénticas, incluidos NaN. El respaldo exacto anterior está registrado en `_respaldos_publicacion/202609/5a4033ec892d4acbb99ff4540f765c98/`. Se preservaron las 63 referencias protegidas del envoltorio, todas las revisiones previas y junio legado; los respaldos necesarios para reproducir análisis **no son temporales descartables**.

El productor retiró 85.545.063 bytes de recortes temporales de cinco áreas después de publicar y registrar el mes. La auditoría independiente comprobó el producto final, respaldo y registros durables; no afirma haber reabierto los cinco crudos ya retirados ni certificado sus hashes independientemente antes del retiro. El conversor no retiró fuentes ni revisiones. Staging quedó vacío.

No se repitieron transformaciones históricas, SINCA ni MERRA-2; tampoco se entrenó un modelo. Se conservan las cautelas de `PREPARACION_MODELADO.md`: confirmar reloj/unidades SINCA, aplicar QA y construir cruces estación–píxel–hora antes del entrenamiento. Las horas satelitales siguen siendo las de adquisición, sin fabricar cobertura horaria continua.
