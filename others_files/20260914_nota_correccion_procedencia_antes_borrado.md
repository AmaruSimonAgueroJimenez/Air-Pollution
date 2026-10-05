# Procedencia persistida antes de borrar fuentes

Control del 14 de septiembre de 2026. Primero se corrigieron los descargadores
TROPOMI y Black Marble; la revisión posterior extendió la protección a MODIS y
MAIAC. No cambiaron el recorte, los píxeles conservados, la hora nativa, las
variables científicas ni QA.

## Problema y corrección

Antes se validaban las salidas y se borraba la fuente, pero el registro de hashes
se escribía después. Una interrupción entre ambos pasos podía conservar el dato
científico sin su checksum de origen. No se detectó esa brecha en los 875 recortes
compactos TROPOMI existentes ni en las 12.191 salidas de la ejecución Black Marble
inspeccionada: todas estaban vinculadas a sus manifiestos y coincidían en tamaño.
Este control de cobertura de registros no fue una nueva reapertura/hash de todo
el archivo histórico.

Ahora la secuencia por fuente es:

1. Recortar y validar todos los resultados territoriales.
2. Construir `granulo_validado_pre_borrado`: fuente y salidas con SHA-256/tamaño,
   versión, máscara y resultados por AOI, incluidos los casos sin píxeles.
3. Persistir ese registro mediante `flush` y `fsync`, todavía con el crudo presente.
4. Eliminar el crudo y registrar `crudo_eliminado_post_validacion`.
5. Escribir los eventos finales compatibles `archivo_validado`/`aoi_sin_pixeles`.

Si falla la construcción o persistencia del registro previo, se conserva la
fuente. Black Marble tampoco puede borrarla desde su manejador externo de errores.
Conservar temporalmente una fuente tras un fallo es una protección de recuperación,
no una autorización para acumular crudos sin revisar.

Una interrupción después del paso 3 puede dejar sin evento final una operación
con evidencia durable. Al auditar una salida aparentemente sin registro final,
consultar primero el WAL de su `execution_id` y `granule_id`; verificar fuente,
hash de salida, máscara y AOI. No borrar la salida ni inventar hashes o reescribir
los manifiestos históricos. El WAL permite conservar la evidencia aunque el
crudo ya no exista; esta corrección no añade un reconciliador automático de eventos.

## Reproducibilidad y comprobaciones

- Código TROPOMI nuevo: `1ce98047b03990a7485a9988ce5993b0a9e4a5eef0b35834684a52c6811fbeae`.
- Código Black Marble nuevo: `0265f524e9c69a329ec10a9997f3b7ccfce0f557ffccd5303519f2563ff6a542`.
- Copias exactas anteriores, sólo como evidencia: `logs/procedencia_tropomi_20260914/*.py.txt`.
- 69/69 pruebas pasaron con Python 3.14; 12/12 de Black Marble pasaron también
  con el entorno `neuro` de producción. La prueba DMSP que exige `boto3` debe
  ejecutarse en Python 3.14, no en `neuro`.
- Los manifiestos anteriores no se reescribieron. Los reinicios crean ejecuciones
  nuevas que identifican el código realmente cargado.
- La primera operación real Black Marble del código corregido verificó dos
  recortes (Rapa Nui y Sala y Gómez), tres resultados vacíos, el orden WAL/borrado,
  hashes y ausencia del crudo y temporales.
- La primera operación real TROPOMI quedó comprobada a las 10:59:11 UTC: el
  registro previo persistió a las 10:35:10.125572 UTC, seguido del evento de
  borrado y del evento final. El recorte reabierto conserva 27.673 píxeles de
  Chile; el hash de la fuente coincide con la copia protegida antes del reinicio
  y el hash recalculado de la salida coincide con ambos registros. La fuente y
  los temporales ya no existen. Los hashes completos y el orden de eventos
  constan en `first_live_transaction_audit` del registro de recuperación.

Registros: `logs/correccion_procedencia_tropomi_20260914T100505.json` y
`logs/correccion_procedencia_blackmarble_20260914T101350.json`.

## Extensión a MODIS y MAIAC

La revisión previa a incorporar nuevas publicaciones de NASA encontró el mismo
orden inseguro en estos dos descargadores. Además, la limpieza automática del
área de trabajo podía retirar HDF tras una excepción o señal. Esta revisión no
constituye una auditoría exhaustiva de los hashes del archivo histórico ni prueba
que se hayan perdido fuentes en una ejecución anterior.

Ambos descargadores ahora usan retención explícita de fuentes no validadas. La
entrada, salida o reanudación del área de trabajo no elimina HDF. Antes de retirar
la carpeta de un día se exige un inventario exacto de los archivos descargados,
sus tamaños y hashes; cualquier archivo adicional no auditado bloquea la limpieza.
Un HDF retenido también impide saltar un día cuya partición ya parezca válida.

Después de reabrir los Parquet y validar su estructura —y la relación entre
observaciones y pasadas en MAIAC— se publica un JSON inmutable por ejecución
`<partición>.<execution_id>.pre_borrado.json`. Incluye hashes de las fuentes y
salidas, versión de código, máscara y cobertura. La escritura atómica sincroniza
tanto el archivo como el directorio antes del borrado. El manifiesto canónico y
el ledger de éxito sólo se publican después de la limpieza explícita.

Una excepción o señal conserva las fuentes aún presentes y escribe un registro
`<partición>.<execution_id>.error.json`, sin sustituir el WAL o el canónico anterior.
El ledger queda reintentable. Si falla una escritura después de reemplazar un
Parquet, el registro de error detecta el cambio por hash. Si el crudo ya fue
retirado con autorización, el WAL sigue siendo la evidencia durable para revisar
y reconciliar el intento. No se deben modificar en bloque los hashes históricos
para que coincidan con la versión actual del descargador.

Comprobaciones a las 19:09 UTC:

- 100/100 pruebas del pipeline con Python 3.14.
- 38/38 pruebas MODIS, MAIAC y retención con el entorno `neuro` de producción.
- Pruebas de éxito, vacío válido, fallos de persistencia/limpieza, interrupciones,
  publicación parcialmente completada y fuentes adicionales no auditadas.
- MODIS: `6fe0dae26a2cd0b00319483bb91915a03704c88f63bdcbf4fcd844db9001e9e4`.
- MAIAC: `11914fae70c747eef4d48e8db3c71415eb6b8e918f58e201e3cf082746e049b0`.
- Helper: `eaa78b1c0c330b54405f0614151c3d05e3a7fef1e303227891080c53407e979d`.
- Código anterior byte-exacto conservado en `logs/procedencia_modis_maiac_20260914/`.

El estado y las pruebas de las ejecuciones reales figuran en
`logs/correccion_procedencia_modis_maiac_20260914T1808.json`. MODIS y MAIAC ya tienen
ingestas reales validadas con esta protección. OMI y MOPITT todavía utilizan
los valores anteriores de limpieza del helper: deben auditarse antes de iniciar
sus descargas nativas completas. Los cuatro procesos prolongados que ya estaban
activos no se reiniciaron ni cambiaron su código.

Primera comprobación real MODIS cerrada a las 19:17 UTC: Aqua del 11 de septiembre
se actualizó de 1.171 a 1.546 observaciones, conservando exactamente todas las
anteriores; se añadieron los días 12 y 13 con 1.554 y 3.387 observaciones. Los
catálogos consultados y registrados contienen 5, 8 y 7 gránulos. Las tres salidas
se reabrieron, sus tiempos siguen siendo `Scan_Start_Time_TAI93`, y los hashes
de salida, WAL, canónico, código y ledger concuerdan. Los HDF de esos tres días
ya fueron retirados. Los archivos y filas fuera del objetivo no cambiaron. Se
eliminó únicamente el respaldo Parquet redundante del día 11 después de probar
que todas sus observaciones estaban en la nueva salida; se conservó su evidencia
de origen. Esta incorporación está validada contra el catálogo consultado, no
certifica que NASA no publique nuevas revisiones posteriormente.

Primera comprobación real MAIAC cerrada a las 20:12 UTC: los días 11, 12 y 13 de
septiembre incorporaron 582.493, 846.135 y 610.869 observaciones, correspondientes
a 8, 9 y 8 pasadas. Se verificaron las seis salidas Parquet, sus fechas nativas
`Orbit_time_stamp`, cada relación observación–pasada y el vínculo de todos los
identificadores de píxel con los catálogos hasheados. Cada día tuvo 12 fuentes y
10 catálogos espaciales relevantes; `h10v10` y `h12v11` no aportaron píxeles de
Chile y no se inventaron catálogos para ellos. Los diez catálogos anteriores,
sus 880.219 píxeles y las filas del ledger fuera de objetivo quedaron intactos.
Los 36 HDF fueron retirados después del WAL y la validación, sin sidecars de
error. No hubo cambios de código durante esta ejecución. Evidencia:
`logs/auditoria_maiac_20260911_13_20260914T2011Z.json` y su reapertura independiente
`logs/auditoria_maiac_20260911_13_reapertura_20260914T2012.json`.
