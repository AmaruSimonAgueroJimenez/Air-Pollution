# Cierre ERA5-Land y recuperación de producciones satelitales, 14 septiembre 2026

## Resultado verificado

ERA5-Land terminó el rango solicitado: enero de 2000 a agosto de 2026 son 320 meses completos; septiembre contiene 192 horas, del 1 al 8. Se reabrieron y recalcularon los hashes de los 321 NetCDF, preservando 9.725 píxeles nativos de 0,1° y seis variables. Los vacíos de la máscara terrestre original, especialmente en islas pequeñas, no se interpolaron. Calendario completo no significa datos finitos en cada píxel.

El retiro oficial, sin descargador ERA concurrente, eliminó permanentemente 340 copias originales redundantes de 317 meses (72.341.912.043 bytes = 67,3737 GiB); no se enviaron a la papelera. Los recortes útiles permanecen y sus contenidos no cambiaron. Septiembre fue excluido. Se conservó `era5land_202606_chile.nc` (154.958.353 bytes), parcial y ajeno al manifiesto del reemplazo. La comparación exhaustiva encontró iguales valores base en Chile, pero la humedad relativa derivada no se ha reconstruido numéricamente; no se forzó su eliminación.

Evidencias: `logs/auditoria_era5land_cierre_20260914T2211.json`, `logs/auditoria_retiro_legado_era5land_20260914T2221.json` y `logs/diagnostico_legado_era5land_202606_20260914.json`.

## Datos históricos recuperados

| Producto | Fecha | Observaciones nuevas | Tiempo conservado |
|---|---|---:|---|
| MODIS Terra | 2022-10-24 | 4.043 | 144 tiempos de escaneo |
| MODIS Terra | 2022-10-31 | 4.292 | 215 tiempos de escaneo |
| MODIS Terra | 2022-11-05 | 5.525 | 200 tiempos de escaneo |
| MAIAC | 2003-08-16 | 537.157 | 14 pasadas, Terra y Aqua |

Se conservaron resolución nominal de 3 km MODIS y 1 km MAIAC, píxeles separados, horas nativas y QA. No se promediaron comunas ni se inventaron mediciones horarias. Las cuatro fechas suman 551.017 observaciones; no es una afirmación de completitud de toda la serie. Los 36 HDF seleccionados se retiraron sólo después de reabrir las salidas y persistir sus hashes.

La política 1.1.0 distingue adquisición y producción según la [nomenclatura NASA](https://modaps.modaps.eosdis.nasa.gov/services/about/nomenclature.html). Selecciona la producción reciente de la misma unidad nativa y conserva todas las unidades distintas. La [orientación LP DAAC](https://forum.earthdata.nasa.gov/viewtopic.php?t=5988) sobre duplicados MAIAC se refiere a un caso de 2022 y no demuestra igualdad científica de nuestros archivos. Se admite únicamente un rango máximo de 1e-6° en coordenadas del metadato CMR, con idéntica estructura y demás campos; los píxeles científicos no se modifican.

Selección inmutable antes de descargar → hashes fuente/salida y registro durable antes de borrar → manifiesto canónico → ledger. SHA de descargador y selector fijados una vez por ejecución. Código exacto anterior y desplegado archivado en `logs/procedencia_producciones_modis_maiac_20260914`. Pruebas: 131/131 sistema y 59/59 entorno neuro; extracciones científicas y helper compartido sin cambios. Evidencia integral: `logs/correccion_seleccion_producciones_20260914T2235.json`.

## Pendientes y cautelas

Diez fechas Terra permanecen con error sin nuevos intentos: seis presentan diferencias de 1–2 segundos entre fecha de producción UMM y filename; cuatro exceden la tolerancia espacial. Deben persistirse y examinarse metadatos completos antes de cambiar la política. Otros 193 errores anteriores por consultas CMR vacías no son ausencia definitiva. Los hashes históricos ambiguos y referencias incompletas de catálogos MAIAC siguen pendientes; no se reescribieron.

Las variables ERA5-Land finales carecen de atributos `units`. El contrato documental está en `logs/metadatos_era5land_pendientes_20260914.json`: cinco variables instantáneas y TP acumulada nativa. **No usar TP directamente como lluvia incremental horaria**. La transformación correcta debe conservar TP original, manejar reinicio a las 01 UTC, cruzar meses con la hora anterior y registrar faltantes; aún no está implementada. Documentación y fórmulas oficiales están citadas en ese registro. No se alteraron los valores para resolver un problema de metadatos.

A las 22:33 UTC quedaban 409,35 GiB libres. Tras acreditar lo ya almacenado en A2, la proyección restante deja unos 253,24 GiB libres en el escenario central o 175,41 GiB en el escenario de máximos observados, sin garantía para años futuros ni otros crecimientos. DMSP sigue aplazado hasta que termine Black Marble A2 y se verifique la capacidad. CAMS, TROPOMI y A2 continúan; no se reiniciaron ni se borraron sus archivos en curso.
