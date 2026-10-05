# Auditoría de procedencia MODIS/MAIAC — 2026-09-06

## Alcance

Se revisaron los manifiestos diarios y sus archivos de auditoría de:

- MODIS AOD 3 km (`MOD04_3K` y `MYD04_3K`), 2000-02-24 a 2026-09-04.
- MAIAC AOD 1 km (`MCD19A2.061`), 2000-02-24 a 2026-09-04.

No se modificó ningún manifiesto histórico ni se adjudicaron manualmente días sin
datos. Los estados `error` recientes siguen siendo reintentables hasta que NASA
publique los gránulos o una verificación independiente demuestre una ausencia
oficial.

## Hallazgos

- MODIS: 19.380 claves únicas; 18.228 `ok`, 1.001 `sin_datos` y 151
  `error` al cerrar la corrida completa. Los Parquet, JSON, conteos y hashes
  embebidos concordaban. Ochenta y tres JSON del mismo `execution_id` registran
  un hash de script anterior intercalado con el hash posterior. El código en ese
  momento recalculaba el hash del archivo en disco al escribir cada JSON, por lo
  que una sincronización o edición durante la ejecución podía cambiar el valor
  registrado sin cambiar el código ya cargado por Python. No existe evidencia
  suficiente para reconstruir retroactivamente cuál de ambos hashes representa
  el código cargado; por ello se conservaron intactos.
- MAIAC: 9.690 días únicos; 9.621 `ok`, 11 `sin_datos` y 58 `error` al
  cerrar la corrida completa. Los manifiestos, Parquet, conteos y hashes
  concordaban. Cincuenta y seis auditorías exitosas conservan un hash histórico
  anterior; son procedencia válida y no se reescribieron.

## Corrección aplicada

Desde esta fecha, `descargar_modis_aod.py` y `descargar_maiac_aod.py` calculan
la ruta y el SHA256 del propio script una sola vez al inicio de `main()` y pasan
esa identidad inmutable a todas las auditorías de la ejecución. Así, una edición
o sincronización posterior del archivo no puede mezclar hashes dentro del mismo
`execution_id`.

Ambos descargadores usan además una reserva predeterminada de 100 GiB, publican
solo después de validar, conservan el crudo únicamente en el área de trabajo y
lo eliminan al salir. La corrección quedó cubierta por pruebas que verifican una
sola captura por ejecución y la estabilidad del hash aunque cambie el archivo
durante la corrida.

## Reintento posterior a la corrección

El 2026-09-06 se reintentaron únicamente 2026-09-04 y 2026-09-05. Terra MODIS
del 4 ya estaba validado. CMR todavía devolvió cero gránulos para Aqua MODIS del
4, ambos sensores MODIS del 5 y MAIAC de ambos días. Esos cinco casos quedaron
como `error` reintentable, con el hash único de su respectiva ejecución; no se
crearon Parquet vacíos ni quedaron HDF o parciales.
