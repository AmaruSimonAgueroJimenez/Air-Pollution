# MODIS Terra: ampliación versionada del 17 de septiembre de 2026

El 19 de septiembre se incorporaron cinco fuentes nuevas del catálogo para el
17 de septiembre. La revisión contiene **2.326 observaciones AOD**: las 46
anteriores, idénticas, y 2.280 nuevas. Conserva los 20 campos del extractor,
los píxeles de resolución nominal de 3 km, QA y la hora real de pasada;
119 comunas tienen más de un píxel. No hay promedio comunal ni interpolación
horaria. AOD no es una medición directa de concentración superficial de PM2.5.

## Archivo que se debe seleccionar

Raíz: `/Volumes/Datos/Asesorias_Data/AirPollution/data/contaminantes/MODIS_AOD_3K/`.

Revisión: `18e20ad28ca67eaa5d4cd7f0f035d612a3c1693f5c1e25a0a1f0f0d6b6a166b5`.

Dentro de `revisiones_pixeles_horario/terra_2026-09-17/<revision>/`:

- `observaciones.parquet`: 49.383 bytes, SHA-256
  `ecbe93317b396a53fc72ac0a767ac9525dafb0c707e5bd9c1d569cda6152757b`.
- `manifest.json`: identidad de las siete fuentes, resolución, cobertura,
  código, versiones y evidencia de las dos fuentes heredadas.

Para un análisis elegir **esta revisión o la partición canónica antigua, nunca
ambas**: las 46 observaciones antiguas están incluidas. El archivo canónico,
su manifiesto, los catálogos MODIS/MAIAC y sus cierres históricos se conservaron
sin cambios. Un lector que sólo consulte el catálogo canónico antiguo verá
todavía las 46 filas; debe seleccionar explícitamente esta revisión para usar
las 2.326. No se modificó ningún modelo ni su tabla de entrenamiento.

## Alcance real

Las siete identidades CMR se mantuvieron en tres consultas independientes.
Eso no prueba que el proveedor no vaya a publicar más fuentes después.
Cuatro fuentes aportaron filas: 11:55 (46), 13:25 (10), 13:30 (2.212) y
13:35 (58), horas nominales UTC. Las otras tres conservaron registro explícito
de cero filas bajo las reglas geográficas/de validez del extractor.

Todas las observaciones publicadas pertenecen al continente; no hay
observaciones AOD insulares en esta revisión. Las tres áreas de búsqueda
incluyeron islas y el recorte se aplicó a los polígonos chilenos, pero esto
**no declara cobertura nacional continua ni cierre definitivo del día**.
Las horas nativas observadas van de 11:59:35.494962 a 13:37:33.043226 UTC.

## Ejecución y conservación reproducibles

El publicador acotado es
`logs/lanzar_modis_revision_terra17_20260919T0921.py` (SHA-256
`842dede27cd3f17d9875776a66272e42f8dfc4e77922cda584ad98867b7eb266`).
No modifica los módulos científicos existentes. Se ejecutó con el Python
del entorno `neuro`, que cuenta con el lector HDF4, y `--ejecutar`.

Sin argumentos sólo comprueba el estado. Una revisión completada se reabre
y reutiliza sin descargar ni escribir. Una transacción incompleta se detiene
para diagnóstico y conserva sus archivos; no se fuerza ni se limpia a ciegas.
Los parámetros de este publicador están fijados a esta fecha e identidades;
no es un lanzador genérico para otros días.

Se verificaron tamaño CMR, MD5 y SHA-256 de los cinco HDF nuevos, se repitió
su extracción completa y se compararon todos los campos antes de retirarlos.
Salida, manifiesto y WAL quedaron durables antes de borrar exactamente
**32.981.454 bytes de fuentes nuevas** y el Parquet de trabajo validado.
El staging de la revisión quedó ausente. Las fuentes antiguas ya retiradas
heredan su evidencia anterior: no se afirma una nueva lectura de esos crudos.

La transacción está en `_control_revisiones/terra_2026-09-17/<revision>/`,
incluidos código archivado, `pre_borrado.json` y `fin.json`. Estos registros
y las versiones anteriores útiles **no son temporales descartables**.

Las siete pruebas de guardas están en
`logs/test_modis_revision_terra17_20260919T0921.py`; el registro de revisión
previa es `logs/revision_preflight_modis_terra17_20260919T0921.json`.
La reentrada sin red, con 23 archivos de publicación/control byte-idénticos,
está en `logs/reentrada_modis_revision_terra17_20260919T0921.json`.

Nota de interpretación del registro: el JSON impreso al terminar
`--ejecutar` es el resultado de la comprobación final `verify_completed`.
Sus campos `writes=false` y `network_requests=0` describen **esa comprobación**,
no el trabajo previo de descarga, publicación y retiro. El resultado efectivo
del trabajo se acredita en `fin.json`, WAL y el seguimiento incremental.
