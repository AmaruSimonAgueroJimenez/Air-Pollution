# Rama ambiental DMC nueva — no producción aprobada

Código canónico en Air-Pollution, espejo idéntico en Air-Pollution-Health-Chile.
No modifica v1/v2 ni importa desenlaces de salud. La plantilla
`config_preparacion_v3.json` mantiene cerrados ajuste real y producción.

Camino implementado con entradas explícitas:

0. `preparar_base_v3.py`: misma fábrica de predictores base para monitores y
   grilla; reutiliza funciones legadas por SHA, lectores nativos sin ejecutar
   sus lanzadores, índices de fuentes explícitos, calentamiento satelital y
   lotes acotados. No lee DMC ni fabrica Chile automáticamente.
1. `dmc_features.py`: adaptador v2 por SHA, políticas históricas documentadas,
   semántica/unidades/QC, reloj UTC y coordenadas; mismo nearest/IDW en monitores
   y grilla. No inventa reloj, códigos QC, radio ni potencia.
2. `features_pre_dmc.py`: unión exacta target_id × hora UTC y huellas de contenido.
3. `runner_v3.py`: rama experimental LightGBM/MSE original (media condicional),
   folds espaciales/temporales preparados, OOF y modelo nativo. Excluye vecindario
   contaminado y ACAG: es una ablación declarada, no reproducción completa de v2.
4. `produccion_v3.py`: modelo seleccionado/aprobado explícitamente, misma
   especificación de features/políticas/operador, partes de grilla ya preparadas.
5. `producto_horario_v3.py`: manifiesto de media condicional nominal≈1km/hora UTC, hashes,
   grilla real y soporte cartesiano completo, sin partes superpuestas/discontinuas.
6. `preflight_v3.py`: informe JSON de todos los bloqueos independientes, claves,
   folds, políticas, índices de fuentes y soporte de grilla preparados. No abre
   observaciones crudas DMC ni fabrica predictores. Sólo inspecciona manifiestos
   DMC cuando el progreso acredita el cierre de la descarga. Propone el próximo
   comando como argumentos explícitos cuando se cumplen las entradas y guardas.

La identidad de ESPECIFICACIÓN debe coincidir entre entrenamiento y producción;
la identidad de CONTENIDO cambia con monitores, grilla y fecha. Una mediana P50
no es una media. La grilla histórica angular0,01° conserva centros, ids y
alineación; no se declara como1000m exactos ni se regrilla. Este código no
selecciona el modelo según resultados de salud.

Faltantes: `base_missing_policy` debe declarar rechazo o una lista concreta
de columnas base con NaN nativoLightGBM; no se imputan ceros. Los infinitos y
los NaN DMC sin soporte se rechazan siempre. La política entra en la identidad
de predictores. `training.observation_unit` distingue PM₂,₅µg/m³ de NO₂ppb.

Pruebas: `python -B -m unittest discover -s scripts_modelo_1km/v3/tests` desde
el repositorio y el entorno `amb_v2`. Incluyen LightGBM real sobre datos sólo
sintéticos; no acreditan una mejora real ni la validez científica de un OOF real.

Preflight detallado, sin ajuste ni producción (salida 2 si hay bloqueos):

```bash
python -B scripts_modelo_1km/v3/preflight_v3.py \
  --config scripts_modelo_1km/v3/config_preparacion_v3.json
```

Con entradas propias ya preparadas se puede añadir `--base-config CONFIG_BASE`
(repetible para monitores y grilla), `--label ETIQUETA_NUEVA` y `--report JSON_NUEVO`.
El informe distingue controles aprobados, bloqueados y diferidos, conserva todas
las causas y expresa comandos en `next_commands`; nunca los ejecuta. Se comprueba
la identidad de los archivos indexados sin cargar sus matrices nativas. Esto no
equivale a verificar el contenido meteorológico ni sustituye los lectores/QC
del ajuste. Las reglas de decisión y aprobaciones reales deben documentarse
por separado; el preflight no las crea.

Ensayo integrado, con carpeta de salida nueva fuera del repositorio:

```bash
python -B scripts_modelo_1km/v3/ensayo_sintetico_v3.py --label ENSAYO_NUEVO
```

Genera ERA5 NetCDF, MAIAC Parquet, una órbita NO₂ NetCDF y DMC ficticios;
recorre la fábrica real, OOF espacial/temporal, persistencia/recarga LightGBM,
dos partes horarias y el lector completo del producto. Guarda fuentes, contratos,
informes de preflight y resumen de paridad reproducible bajo
`~/Asesorias_Data_local/AirPollution/modelado_1km_v3/ensayos_sinteticos/`.
Las aprobaciones llevan `FIXTURE` y sólo se aplican a esos archivos sintéticos.
La plantilla real permanece cerrada. La evidencia compacta del ensayo del
14 de octubre está en `output_files/modelo_1km_v3/preparacion_pre_dmc_20261014/`.

Pendientes antes de usar DMC: descarga terminada; políticas fuente documentadas;
operador espacial fijado; paneles base, folds y grilla preparados por SHA;
criterio previo de decisión y evidencias revisadas de QC/OOF/selección. El
fabricante base ya existe, pero sus índices/tablas reales y la ejecución
nacional aún no están preparados/verificados. No hay una fabricación nacional
nueva completada ni programada.

No leer DMC mientras el descargador escribe. No lanzar ajustes/producción
automáticos ni reemplazar productos históricos. Ver el informe
`docs/estado_ambiental_next_20261014.html` y los resultados del piloto anterior.
