# Integración meteorológica ambiental: propuesta aislada

2026-10-28. **No aplicada, no anclada y no apta para autorizar ajustes.** Esta carpeta sólo contiene un diseño, una unión pura y pruebas pequeñas con datos inventados expresamente como pruebas. No termina M6. No modifica el paquete M1, `correr_v2.py`, `config_v2.json`, paneles, pliegues ni manifiestos; no tiene lector de datos reales ni ejecutor de modelos.

AP y APH son los repositorios canónico y espejo. Las rutas siguientes son relativas a esos repositorios o nombres contractuales dentro de una corrida: **no afirman que existan productos publicados**. No se consultaron datos ambientales reales, DMC, salidas del reloj, resultados de contaminación ni archivos de salud.

## 1. Fuente y estado de referencia

- AP: `b979586aff76d3cd695ca67e4408aa9089938ad6`; espejo APH: `14ff8b0b55df96b75769f5fdce12c0a686bc78b7`. M1 confirmado, **no sellado**.
- APH, `auditoria/RUTA_MODELOS_CONTAMINANTES_20261028.md`: SHA256 `dfc951ae41251d109a2a44049f75552bca745faad452a130d254fef1d5875bb0` al leerlo. Es un estado de trabajo, no otro protocolo.
- APH, `auditoria/20261023/meteo_combinada/enmienda2/PROTOCOLO_METEO_COMBINADA_v2.3.md`, §7.1 y Anexo B: SHA256 `b4175f785ec57811702352d9d063164a5dce05f325a48c327a6d554a09ceddc2`.
- También se contrastaron las decisiones D53/D58/D60 y las preguntas P106–P110, P132 y P142 de `meteo_combinada/COORDINACION_M1.md`. **P106–P110 ya están aceptadas por D60**: los rótulos «pregunta» que conserva `ambiental.py` no las vuelven pendientes.

Huellas SHA256 de las fuentes de AP leídas, todas en el estado del commit anterior:

| Fuente bajo `scripts_modelo_1km/` | SHA256 |
|---|---|
| `v2/correr_v2.py` | `1423ef3f7a8d7bc35d8ee1802187de95129e46afe276241e29a0c7e486f6445d` |
| `v2/config_v2.json` | `51df5063ed642c737d883a82c40382e7e211d288f5499151edce61bd692528d7` |
| `v2/meteorologia_v2.py` | `f61559eab281846a4935eb1ea66217e039ff37a727833bf8fcaa7a774b776754` |
| `v2/motores_v2.py` | `389f23f210bfe2dba55dca524b093f620adf6267309c42ceac2cb93ab3e35c57` |
| `meteo_combinada/ambiental.py` | `1e6cd4f8547d89516a514199e1cdc966c1120ef6b436b3cdf54c64c4f802fa1e` |
| `meteo_combinada/orquestacion.py` | `8c54bce481fc2c5a5215d97c2c6a970605f2e0d01d6104d32308e13aff0f8db1` |
| `meteo_combinada/tipos.py` | `31fc3a1ad00ccdc5219ee44796e77be44e0cc3f813901a03b69d6bf964743dab` |
| `meteo_combinada/decision.py` | `d2d1891f0a2676af0bed79a7151a3e74770e830e1d0e94d3d46fde3667d9074e` |
| `meteo_combinada/salidas.py` | `f20d87c59da2e989e0c2812c9cd6e3c2eee324e5633cdb2455b90ac667cd4435` |

Estas son huellas de **código/documentos**, no huellas de paneles ni productos. Los nuevos productos no reciben aquí ninguna identidad inventada. Si otro trabajo cambia una fuente, se revisa la propuesta sobre ese origen nuevo; no se actualizan automáticamente estas referencias ni las guardas de las pruebas.

**Concurrencia observada al cierre, 18:21 de Chile:** el otro frente de trabajo ya había modificado `config_v2.json`; su SHA256 observada fue `2ce768e76809bfc89912cc21a040a32f950159222ffd7ad8b4420329d872b5c9`, distinta del origen de la tabla. No se escribió ni se corrigió ese archivo desde esta propuesta. El resto de las fuentes de AP de la tabla seguía sin diferencias frente a `b979586`. La tabla conserva el origen leído: antes de una integración real habrá que reconciliarlo con la configuración final y su anclaje; las pruebas de esta carpeta no cargan esa configuración.

## 2. Contrato de entrada lateral ya existente

### 2.1 Productor y soporte

`ambiental.lateral_monitores(pol, decision, operador, *, variante="I", panel, pliegues, meses, datos, umbrales, politica, h_ultima, estaticos=None, decision_sha256=None, pliegues_sha256=None, panel_sha256=None, policy_sha256=None, anios=None) -> (tabla, metadatos)`.

No se reimplementa. En M5 produce las claves distintas del panel de la **red 2**, ordenadas por estación y hora; admite partes por año UTC. El panel entero se ata al registro de `pliegues_v2_red2.json`. La celda del monitor viene de `estaciones[].celda` de ese registro, no de un identificador ni de buscar de nuevo el monitor más cercano. El soporte ambiental es el centro de la celda con `z_media` NASADEM, igual al de producción.

`ambiental.unir_partes(partes)` verifica las partes y sus metadatos comunes; no se concatenan sin comprobar. `orquestacion._ensamblar_laterales` las relee con la huella del archivo y publica los nombres contractuales `ambiental/lateral_<pol>_<I|D>.parquet` mediante esa función. Los metadatos vuelven como `tabla.attrs["metadatos"]`; `attrs["esquema"]` contiene la versión. `salidas._bytes_parquet` los transporta en `PANDAS_ATTRS`.

### 2.2 Claves y columnas exactas

Claves, en este orden: `estacion: string`, `ts_utc: datetime64[ns, UTC]`. Una fila por estación × hora exacta HH:00; sin interpolación temporal. El consumidor no convierte un código numérico a texto ni interpreta una cadena como fecha para arreglar entradas.

| Variante | Columnas, en su orden | Tipos y unidades |
|---|---|---|
| I | `mc_t2m`, `mc_d2m`, `mc_rh`, `mc_sp`, `mc_u10`, `mc_v10`, `mc_wind`, `mc_wdir_sin`, `mc_wdir_cos` | Todas `float32`; K, K, %, Pa, m/s, m/s, m/s, 1, 1 |
| D | `fe_t2m`, `fe_d2m`, `fe_rh`, `fe_sp`, `fe_u10`, `fe_v10`, `fe_wind`, `fe_wdir_sin`, `fe_wdir_cos`, `dmc_R_T`, `dmc_R_Td`, `dmc_R_u`, `dmc_R_v`, `dmc_R_p` | Todas `float32`; las primeras nueve con las unidades de I; luego K, K, m/s, m/s, 1 |

Son `tipos.ESQUEMA_LATERAL_I` (`meteo-combinada-lateral-i/1`) y `_D` (`meteo-combinada-lateral-d/1`). No se agregan soporte DMC, distancia DMC, observaciones, etiquetas de pliegue ni variables de calidad como predictores de la lateral. `dmc_R_p` es `ln(p/p_F)`, **no** una diferencia en Pa.

La conversión física ocurre **en el productor**, no al unir: T/Td de °C a K sumando 273,15; presión del producto en hPa a Pa multiplicando por 100; u/v y rapidez ya en m/s; humedad Magnus 17,625 y 243,04 en %, dirección como seno/coseno de `arctan2(u,v)` («hacia»). En D, los incrementos térmicos conservan su magnitud en K. No se vuelve a convertir viento de nudos ni se recalcula Magnus en el consumidor.

### 2.3 Tiempo y cobertura: sin regla nueva

- El panel de red 2 guarda `ts_utc` sin zona, pero de procedencia UTC. §7.1 exige comprobar esa procedencia antes de localizar una **copia** con `tz_localize("UTC")`. No es una conversión desde hora civil. La lateral lleva zona explícita UTC.
- `unir_sidecar` compara claves en UTC y conserva la representación del panel que recibe. El módulo propuesto restaura al final la representación original de `ts_utc`, para no romper la alineación temporal de `Vecindario`/`Contexto`.
- AMB-17/P106, aceptada en D60: quedan **fuera de la lateral** las claves posteriores a la última hora con dato ERA5-Land; la unión les pone NaN y `claves_tras_ultima_hora` cuenta claves distintas. No se borran filas del panel.
- La última hora debe venir de FON-1/cadena de entradas verificada. En esa cadena `h` cuenta horas desde `2000-01-01T00:00Z`; en la propuesta se entrega el `Timestamp` UTC equivalente. **Nunca se deduce del máximo de la lateral**, porque eso permitiría disfrazar un truncamiento.
- Antes o en ese límite, una clave que falte es un error. Las filas extra, incluso posteriores al límite, se rechazan. Un NaN **dentro de una fila presente** no es una clave faltante y se conserva sin imputar. La unión no acredita su justificación científica.

### 2.4 Metadatos e identidades: cuatro conceptos distintos

Metadatos exactos de `ambiental.METADATOS_LATERAL`: `model_ready`, `source_policy_verified`, `policy_sha256`, `variante`, `columnas`, `unidades`, `content_sha256`, `decision_sha256`, `operador_sha256`, `panel_sha256`, `pliegues_sha256`, `claves_tras_ultima_hora`. Los dos primeros son el booleano `True`, no textos ni un juicio nuevo del consumidor.

1. **SHA256 del archivo Parquet:** de sus bytes, cotejada contra el inventario sellado/registro de la corrida. La verifica el futuro lector antes de deserializar; no es un campo adicional inventado en esos metadatos.
2. **`content_sha256` de la lateral:** receta canónica AMB-18 (cabecera de esquema, códigos, horas en ns y columnas float32 con NaN canónico). Se rehace con `ambiental.huella_contenido`. Depende del orden de las filas: reordenarlas exige rehacer la huella de ese contenido, aunque la unión siga dando los mismos valores.
3. **Identidad que devuelve `meteorologia_v2.unir_sidecar`:** otra huella, basada en `hash_pandas_object`, tipos, columnas y política. Se conserva aparte. Trae exactamente `content_sha256`, `policy_sha256`, `source_artifact_sha256`, `columns`, `sidecar_rows`, `panel_rows`. `source_artifact_sha256` sale `None` en esta interfaz: la lateral del producto no añade ese campo a sus metadatos ni corresponde a un único artefacto mensual.
4. **Identidad del panel y pliegues:** `panel_sha256` es la de los bytes del panel original registrados en `contaminantes.<pol>.panel.sha256`; `pliegues_sha256` es la de los bytes de `pliegues_v2_red2.json`. La `huella_pliegues` lógica que usa `Contexto` es otra identidad: se vuelve a calcular con `pliegues_v2.huella_pliegues`, no se equipara a la SHA256 del archivo.

El futuro lector debe verificar las seis huellas de los metadatos contra entradas autenticadas: contenido, política, decisión meteorológica, operador, panel y archivo de pliegues. El operador se lee con `ambiental.leer_operador(..., sha256=...)`, se ata a `decision.json` y contiene ganador/hiperparámetros y huellas de geometría/umbrales. La política debe ser la de la misma cadena M3-4. P110/D60 aclara que `source_policy_verified` por sí solo no demuestra esa cadena.

**Ganador y variante no son lo mismo.** `decision_sha256` ata al ganador meteorológico ambiental y sus hiperparámetros; el lector no acepta un ganador escrito a mano. La comparación preliminar usa explícitamente I y D de M5, sin exigir el futuro veredicto M6. Después de M6, `decision_m6.json` aporta `variante[pol]`, `ganador_restringido` y `huellas`; su huella también entra en la identidad del contexto definitivo. No contiene actualmente un objeto dedicado `lateral[pol]`: se deben resolver los nombres contractuales vigentes de `huellas`, conforme a la rama de `orquestacion.correr_m6`, con rechazo de ambigüedades y sin inventar otra ruta.

En rama 3, las laterales y el operador vigentes son los restringidos de `m6/ambiental/`; el operador cita `m6/ramas_m6.json`, **no** el `decision_m6.json` posterior. Se evita la circularidad ORQ-30. El restringido vale para todos los contaminantes si la rama 3 rige en alguno. D58 deja B/AB fuera de E0; no se reabren ni se eliminan sus cálculos contractuales.

## 3. Qué hace realmente `union_lateral.py`

API de propuesta: `unir_lateral_validada(panel, lateral, metadatos, *, variante, identidades_esperadas, ultima_hora_utc, ambiental, adaptador, panel_ingenuo_es_utc=False) -> (panel_ampliado, identidad_union)`.

- Sólo recibe tablas y dependencias ya cargadas. `ambiental` es la interfaz pura existente y `adaptador` el módulo fijado; no hay rutas ni búsqueda de datos. No importa `correr_v2`, `meteo_combinada` ni `reloj_dmc`, ni cambia hilos, configuración o pliegues.
- `identidades_esperadas` exige exactamente las seis claves de `HUELLAS`, todas SHA256 en minúsculas. Deben venir del lector que comprobó los bytes, no de copiar sin verificar una afirmación junto al DataFrame. El módulo no puede demostrar que un DataFrame arbitrario salió de un archivo cuya huella se le dice.
- Rechaza metadatos/variante/unidades incompatibles, contenido alterado, columnas extra o solapadas, claves nulas o duplicadas en cualquiera de las tablas, horas no exactas, ausencias no autorizadas y filas extra. Reutiliza `ambiental.huella_contenido`, sin copiar la receta de AMB-18.
- Llama una sola vez al **`meteorologia_v2.unir_sidecar` fijado**, no a un reemplazo implementado aquí. Comprueba filas, índice, orden y columnas originales antes de restaurar el tipo temporal original. Devuelve su identidad sin renombrarla como huella canónica.
- El resultado conserva `obs`, calidad, pesos, lluvia y demás columnas del panel, con sus tipos y NaN; añade exactamente las columnas de I o D. El panel y la lateral de entrada no se modifican. La fila por clave del panel debe ser única; no se deduplica silenciosamente un panel que no cumpla ese requisito.

**Fugas: alcance exacto.** La unión no estima nada ni usa el blanco/etiquetas de pliegue para producir meteorología; ata la lateral al archivo de pliegues esperado y no admite laterales con campos por pliegue. No sustituye las exclusiones del entrenamiento ambiental, el recálculo de `obs_vec` ni las pruebas de independencia de candidatos meteorológicos. No puede detectar que un productor ajeno haya usado respuestas de prueba y luego falsificado coherentemente sus metadatos. Eso exige verificar la cadena de producción y sus pruebas fijadas; no se anuncia aquí como resuelto.

## 4. Punto de entrada futuro a `Contexto`: no aplicado

`Contexto.desde_disco` (líneas 367–406 del origen) no recibe lateral. Construye `Vecindario` y lee directamente la lista de predictores de la configuración; si se cambiara sólo esa lista a `mc_*`, intentaría pedir al Parquet base columnas que aún no existen. El cambio debe ser coordinado, no sólo un reemplazo de nombres.

Secuencia propuesta para una enmienda futura:

1. Conservar las guardas de red 2 (`exigir_registro`), la huella del panel, el manifiesto lógico y la bandera de calidad obligatoria. Resolver primero modo explícito de comparación I/D de M5 o modo definitivo respaldado por M6; sin caída automática a `el_*`.
2. Separar la lista de lectura del panel base de la lista final del motor: leer claves, blanco, calendario, calidad y predictores no sustituidos; no pedir al archivo base las columnas laterales. Conservar las columnas de régimen de predictores ya previstas por el contexto.
3. Leer/verificar bytes y metadatos de la lateral y los registros descritos en §2; unir la tabla en memoria **después de leer el panel y antes de crear `X` en `desde_tablas`**. La calidad y `Vecindario` siguen alineados al panel original.
4. Construir `feats` con la variante explícita, de forma idéntica para I/D salvo la meteorología. I reemplaza los nueve `el_*` uno a uno; D contiene los nueve `fe_*` en el mismo orden y las cinco R en el orden del esquema. El lugar exacto de inserción de esas cinco R en la lista total debe quedar registrado en la configuración futura: la lista ordenada forma parte de la firma. No se implementa todavía aquí.
5. No reemplazar la identidad del panel por la de la lateral. Componer con `sha256_json` una identidad de contexto que incluya panel base, variante, SHA del archivo lateral, huella canónica, identidad real de unión, política, decisión, operador, archivo de pliegues y código del adaptador/unión. En el modo definitivo incluir además SHA de `decision_m6.json` y, cuando corresponda, de `ramas_m6.json`. Es una receta técnica propuesta, no una firma ya implementada.
6. Llevar esa identidad a `identidad_panel` y `huellas_firma`; registrar los archivos comprobados en `insumos`. Verificar propagación a `_base_firma`, `firma_tarea`, consolidación y reanudación: otra meteorología invalida los puntos anteriores, aun si el panel base no cambia. Mantener la huella lógica de pliegues y las firmas de filas/exclusiones/semillas actuales.
7. La interfaz futura `--lateral-meteo`/`lateral=` de §7.1 necesita lector, validación de modo, controles negativos y pruebas de contexto reales. **No existen en esta propuesta.**

Qué sustituye: exclusivamente los nueve `el_t2m`, `el_d2m`, `el_rh`, `el_sp`, `el_u10`, `el_v10`, `el_wind`, `el_wdir_sin`, `el_wdir_cos`. Qué no sustituye: **`el_tp_1h_mm`**, blanco, calidad, filas, pesos, pliegues, vecindario ambiental, BLH ni otras fuentes. Los `el_*` antiguos pueden seguir como columnas históricas del panel inmutable, pero no seleccionarse en el motor nuevo; tampoco se informa una comparación contra ellos.

## 5. Contrato de M6: comparación y fábrica son trabajos separados

### 5.1 Productor de `comparacion_m6` aún pendiente

El Anexo B exige entrenar LightGBM con receta v2, PM2,5/NO2, I/D, LRO/BLQ-75, N=750.000 y **tres réplicas totales**, con las mismas filas/permutaciones y código salvo las columnas meteorológicas. Reutilizar las exclusiones, recálculos de vecindario, calidad y retransformación v2; no sustituirlos por una prueba de la unión.

Entrada a `orquestacion.correr_m6`: alias `comparacion_m6` en la lista cerrada `ENTRADAS_M6`, bytes Parquet y su huella verificada. `tipos.ESQUEMA_COMPARACION_M6`, versión `meteo-combinada-comparacion-m6/1`, tiene exactamente, en orden:

- `contaminante`, `sentido`, `protocolo`: `string`.
- `delta_r2`, `ic_bajo`, `ic_alto`: `float64`.
- `segunda_prueba_coincide`, `supera_ruido`, `consistencia_e2`, `sobrevive_bloque`, `signo_sin_ponderar`, `signo_log`, `decision_sigma2`: `bool`.
- `nmb_c`, `nmb_otra`: `float64`.

Son **ocho filas**: 2 contaminantes (`pm25`, `no2`) × 2 sentidos (`I_frente_a_D`, `D_frente_a_I`) × 2 protocolos (`LRO`, `BLQ-75`). No son filas por réplica: la evidencia de las tres réplicas se resume honestamente según el Anexo B. La tabla no incluye campos de procedencia de ajustes; su huella en la lista cerrada debe quedar enlazada a las firmas/evidencias que produzca el futuro comparador, sin inventar columnas extra que el esquema rechazaría.

`decision.condiciones_anexo_b` verifica unicidad y ambos protocolos por sentido; exige las siete condiciones simultáneas. Usa el IC favorable, la segunda prueba, ruido, consistencia E2, bloque influyente, signos, sensibilidad sigma² y no inferioridad en NMB de un punto porcentual. No fabrica esa evidencia: **poner booleanos sintéticos en una tabla no demostraría superioridad**. Aquí no se crea una `comparacion_m6` ficticia ni se decide ganador.

### 5.2 Fábrica predictiva aún pendiente

Interfaz real: `Cfg.fabrica_m6(contaminante, variante, base) -> (fabrica, modelo)`.

- `base` es una función parcial de `ambiental.fabrica_tf_contaminantes`, con operador M5, meses ya autorizados, datos meteorológicos de producción, escenarios y estáticos ligados por el orquestador.
- El puente se construye conceptualmente como `fabrica = base(predecir=predecir_v2)` para el día UTC fijado; si corresponde otro conversor autorizado se pasa por `horas_de_dias`. No se ejecuta aquí.
- `predecir_v2(modelo, variante, tabla, celdas, dias) -> array[día, celda]`. Recibe la tabla larga de `mc_bloque`: `celda: int64`, `ts_utc` UTC y columnas de I/D `float32`. Debe armar **todos los demás predictores** con su procedimiento contractual, el orden de `feats` y la escala/retransformación del modelo; no bastan nueve o catorce columnas meteorológicas.
- La función devuelta debe cumplir `fabrica(modelo, variante, escenario, celdas, dias) -> array[día, celda]`. `ambiental` arma por escenario la meteorología y comprueba la forma. No entrena ni sabe construir los demás predictores ambientales.
- `orquestacion.correr_m6` llama a `tendencias.tf_contaminantes` por contaminante/variante y se niega sin fábrica. El identificador de esa función (módulo, nombre y SHA del archivo) entra en la identidad de corrida/unidad. P142/D60 exige listar con huella también los insumos que lea la fábrica; no basta registrar su código.

TF: D siempre; I con B/AB, completa, o verificación del mes fijado cuando sólo A/C. Muestra y cotas son las del Anexo B, no se vuelven a escoger. P107/P108, aceptadas en D60, fijan la red de Td para su recorte/HR y el día UTC por omisión; no se corrige `mc_d2m > mc_t2m` de «cambio» ni se impone identidad algebraica I/D en ese escenario. Si la producción define días civiles, la fábrica debe proporcionar su `horas_de_dias` coherente, no cambiar la muestra silenciosamente.

Salida M6 existente, sólo después de comparación y TF reales: `m6/ramas_m6.json`, productos restringidos si corresponden y `m6/decision_m6.json` con ramas, condiciones, variante por contaminante, `O3`, ganador restringido y huellas; después, sello/testigo. El módulo de unión no genera nada de eso.

## 6. Lista de intervención futura sobre fuentes fijadas: NO aplicar

Origen común de todas las filas: AP `b979586aff76d3cd695ca67e4408aa9089938ad6`; SHA256 de cada archivo en §1. Las líneas son localizadores del origen, no promesas de un parche aplicable después de otros cambios.

| Fuente y punto | Intervención futura y condición |
|---|---|
| `v2/correr_v2.py:367–406`, `Contexto.desde_disco` | Añadir entrada lateral y lector verificado; separar lectura base de predictores finales; unir antes de `desde_tablas`. Mantener guardas R22/calidad. |
| `v2/correr_v2.py:309–364`, `huellas_firma`/`desde_tablas`; `:571–605`, firmas | Identidad compuesta panel+meteorología y propagación a trazas, firmas y reanudación; pruebas nuevas de invalidación. |
| `v2/config_v2.json`, `motores.eje_A.predictores`, nuevo nodo de meteorología de §7.1 | Dos listas ordenadas I/D y resolución del veredicto definitivo sin editar la configuración tras M6. No tocar ahora. |
| `v2/motores_v2.py:100–105`, `GP_PREDICTORES`; `:690–709`, `base_lineal`; `:947–950`, `_columnas_crudas` | Resolver referencias literales `el_*`: **renombrar sólo la configuración no basta**. Hoy GP/lineales no consumirían automáticamente `mc_*`/`fe_*`/R; `base_lineal` podría omitir temperatura/viento. Requiere traducción explícita de recetas, no respaldo silencioso a la meteorología vieja. |
| `meteo_combinada/ambiental.py:1490`, `:1653`, `:1703` | Reutilizar productor, comprobación y puente TF. No reemplazar candidatos, fórmulas, soporte espacial ni normalización. Ninguna modificación propuesta al paquete M1 en esta entrega. |
| `meteo_combinada/orquestacion.py:3741–3793`, `Cfg.fabrica_m6` | Entregar la comparación externa y enlazar la fábrica real con sus insumos/huellas. El consumidor actual no es el entrenador que falta. |
| Guardas de M1, P132/D60 | Una modificación posterior de `correr_v2`/config invalida las huellas fijadas: resolver por enmienda/errata procedente y nuevo anclaje. No eludir la negativa M6 ni cambiar su lista cerrada desde esta carpeta. |

La posición de `piloto_v2` y la producción completa también deben coordinarse con esas interfaces y con sus contratos. No se cambia ahora ningún archivo fijado ni se copia la propuesta al espejo.

## 7. Separación entre lo fijado y lo que falta resolver

**Ya fijado:** dos variantes con DMC y ERA5-Land; unidades/esquemas; soporte de celda; lluvia intacta; comparación LightGBM de Anexo B; réplicas/protocolos/N; reglas simétricas y TF; P106–P110 por D60; ramas y O3; ausencia de comparación con la v1 o con una variante sin DMC; D58. Estas decisiones no se reabren para hacer pasar las pruebas.

**Cuestiones de traducción/diseño todavía no resueltas por esta propuesta:**

1. **Eje B con D:** qué columnas/traducción concretas preservan las recetas de GP y diseños lineales al cambiar las referencias literales `el_*`. Derivar para esos motores la meteorología I desde fe+R y, por tanto, colapsar la distinción D, no puede decidirse por conveniencia de programación. Debe localizarse la regla autorizada o fijarla por la vía correspondiente antes de esos ajustes; no bloquea la escritura del comparador M6 LightGBM.
2. **Modelo de contaminación de la TF:** `modelo` es opaco en la interfaz y el orquestador sólo recibe una matriz día × celda. Falta acreditar de qué ajuste final sale y cómo se representan/usan las tres réplicas (el presupuesto del Anexo B las cuenta), y su retransformación. No se supone que sea una réplica elegida a mano ni un promedio nuevo. Si otro contrato ya lo fija, se cita y traduce; si no, se resuelve antes del entrenamiento de la fábrica.
3. **Coherencia temporal de la predicción final:** P108 fija UTC por omisión y permite un conversor si la producción es civil; falta la fábrica que materialice ese caso y su agregación/retransformación diaria. No se dan por equivalentes promediar en log y promediar concentraciones.
4. **Detalles técnicos aún no escritos:** lector de bytes/registros, resolución inequívoca de laterales vigentes, lista ordenada de predictores, receta de firma compuesta, invalidación/reanudación y vinculación de evidencias del comparador a `comparacion_m6`. No son resultados científicos ni deben disfrazarse con archivos vacíos.

No se ha tomado ninguna decisión científica nueva ni usada la delegación del autor para cerrar estas cuestiones. La propuesta no declara producción aprobada aunque todas sus pruebas pasen.

## 8. Pruebas ejecutadas y límites

`pruebas_sinteticas.py`: **23 pruebas, 23 aprobadas, 0 omitidas, 0 fallas**, en el intérprete `amb_v2`, con `-I -B` e hilos de álgebra/Arrow limitados a uno. Última ejecución de esta versión: 2026-10-28; 0,170 s medidos por `unittest` (no es una medición de costo de M1 ni de producción).

Cobertura: unión correcta y desordenada I/D; panel con índice no único conservado; claves duplicadas; filas extra/faltantes; autorización AMB-17 con límite externo y conteo exacto; rechazo de las seis identidades incorrectas; contenido/orden alterado; variante, unidades y metadatos falsos; UTC explícito y panel ingenuo confirmado; NaN conservados; columnas solapadas; perturbación del blanco/calidad/partición sin cambiar meteorología; rechazo de etiquetas de pliegue en la lateral; detección de cambio indebido de hora por un adaptador defectuoso; unión con acceso a archivos/red bloqueado; serialización Parquet de una lateral **sintética** en `tempfile` dentro de esta carpeta, eliminada al salir.

Se cargan `tipos.py` y el adaptador por ruta, verificando las huellas de §1. De `ambiental.py` se compilan únicamente constantes/esquemas y funciones puras de huella seleccionadas de su árbol de sintaxis, con SHA256 del archivo entero verificada: **no se importa el paquete**, su inicialización que cambia hilos ni sus módulos de candidatos/fijados/reloj. No se copia su ciencia. Esto prueba reutilización de esas definiciones exactas y la unión real fijada; no pretende sustituir las 917 pruebas de M1 ni ejecutar `comprobar_union`/orquestación completos.

Ejecución reproducible desde la raíz AP, usando `PY_AMB_V2` como variable local de la terminal que apunte al intérprete ya instalado (no un cambio de configuración del proyecto):

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 BLIS_NUM_THREADS=1 ARROW_NUM_THREADS=1 \
"$PY_AMB_V2" -I -B scripts_modelo_1km/v2/propuesta_integracion_meteo/pruebas_sinteticas.py
```

No se creó un informe de desempeño, una comparación ficticia, un modelo de prueba que se hiciera pasar por producción ni un nuevo manifiesto compartido. Quedan sólo tres archivos de propuesta. Las tres fuentes reutilizadas por la suite (adaptador, tipos y definiciones puras de ambiental) conservaron sus huellas verificadas; el cambio concurrente de configuración se distingue en §1 y no entra en estas pruebas.

## 9. Trabajo restante hasta M6

1. Revisar esta propuesta y resolver las traducciones/definiciones faltantes sin resultados nuevos a la vista; integrar mediante la enmienda y los anclajes que correspondan, fuera de la ventana de archivos congelados. Actualizar coordinadamente huellas/commits y espejo, no desde esta entrega.
2. Terminar sellado de M1 y dependencias de red 2/M2a/M3-4; luego M5 y sus laterales verificadas. Este trabajo aislado no salta esas compuertas.
3. Implementar el lector/contexto y el comparador de Anexo B, con pruebas de firma, exclusión, reanudación y evidencia, antes de autorizar el primer ajuste real I/D. Obtener `comparacion_m6` de entrenamientos reales autorizados.
4. Completar y probar la fábrica predictiva v2 con todos los predictores, retransformación, modelo(s) definidos e insumos registrados. Medir su costo y memoria en una ventana autorizada: ahora no se midieron ni se entrenó nada.
5. Con comparación y fábrica, ejecutar TF y ramas por el M6 existente, registrar intentos, verificar anclajes/remotos/árbol limpio, publicar productos definitivos y sellar. **Sólo entonces** procede la comparación ambiental completa con la variante elegida. El diseño propio de O3 y su ejecutor siguen como frente separado.
