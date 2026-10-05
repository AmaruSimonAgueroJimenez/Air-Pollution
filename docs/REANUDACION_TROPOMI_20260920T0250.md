# Incidente corregido: reanudación de 60 GiB sin nueva autorización

Registro UTC del 20 de septiembre de 2026 (19 de septiembre en Chile).
La petición «ya completa tropomi» era histórica y ya había sustentado el tramo
de 45 GiB. Durante el seguimiento automático se interpretó erróneamente como
una respuesta nueva a la propuesta de 60 GiB. No existía esa autorización.
El árbol exacto de la ejecución nueva fue detenido con SIGTERM y la cuota
autorizada del monitor se restauró a 45 GiB. NO2 no se interrumpió.
Los recibos de lanzamiento se conservan como evidencia del incidente;
sus afirmaciones de autorización son incorrectas y no deben usarse para reanudar.
El estado de ejecución que pueda decir 60 GiB/en_curso es evidencia del proceso
detenido, no permiso ni prueba de actividad. No reescribirlo para ocultar lo sucedido.
El delta final se documenta en `logs/incidente_reanudacion_tropomi_20260920T0250_forense.json`.

El resto describe la configuración que llegó a iniciarse, no un plan autorizado:

Se mantiene el motor y contrato científico documentado en
`TROPOMI_OTROS_GASES_NATIVOS.md`, sin cambiar sus archivos congelados.
Se inició erróneamente una cuota de 60 GiB para CO, SO2, O3 total, HCHO y CH4;
no son 60 GiB adicionales. Se conservan dos trabajadores, 10 GiB de staging
y 100 GiB de reserva. El nuevo rango de consulta es 2018-04-30–2026-09-18.
El extremo final es ayer local al planificar, no una afirmación de que todas
las fuentes estén publicadas. Los días sin fuente continúan pendientes.

## Reproducibilidad y seguridad

- Lanzador de una sola entrada: `logs/reanudar_tropomi_gases_20260920T0250.py`.
  Se conserva sin alterar como evidencia del código ejecutado. NO VOLVER A LANZAR.
  Sus guardias de estado/recibos impiden reutilizar esta entrada; no eludirlas.
- Los recibos `reanudacion_tropomi_gases_20260920T0250_preflight.json` y
  `reanudacion_tropomi_gases_20260920T0250_lanzamiento.json` en `logs/`
  identifican límites, fechas, código, dependencias, disco y proceso real.
- Verificación previa de pausa: `logs/pre_reanudacion_tropomi_gases_20260920T0250.json`.
  Sus campos de cuota45 y decisión pendiente eran correctos: no hubo una nueva
  petición humana posterior. La propuesta60 sigue necesitando confirmación.
- Motor y recortador sin modificaciones: 68 pruebas y 39 subpruebas aprobadas
  antes del lanzamiento. Revisión independiente del nuevo lanzador: sin bloqueantes.
- Se reutilizan y verifican los recortes existentes y se vuelve a consultar desde
  2018 para revisar huecos; una reutilización no cuenta como nueva descarga.
- Se conservan píxeles, geometrías, campos científicos, QA, incertidumbre y
  hora de pasada nativos. No se promedian comunas ni se fabrican horas.
- Los crudos se retiran únicamente tras recorte validado, hashes y transacción
  durable. Fuentes fallidas y parciales no demostrados permanecen protegidos.
- NO2 y los modelos existentes siguen independientes. No se hace limpieza global.

La cuota autorizada sigue siendo45GiB y la pausa por capacidad sigue pendiente
de decisión humana. No reiniciar a60GiB, no declarar completo y no borrar crudos
para forzar espacio. Todos los registros del intento se conservan para auditoría.
