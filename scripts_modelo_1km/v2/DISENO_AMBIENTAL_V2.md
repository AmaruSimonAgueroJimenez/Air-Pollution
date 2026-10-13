# DISENO ambiental v2 · Comparación justa de motores y funciones de pérdida (modelo horario de 1 km)

**Fijado el 2026-10-12, antes de estimar cualquier motor v2.** Es el contrato de las etapas 7 y 8 del programa de
mejoras, más la parte de la etapa 9 que no requiere descargas nuevas. Cambiarlo después de ver resultados exige
una enmienda fechada al final, con su motivo, y que la especificación original se siga informando.

Base: la auditoría del 2026-10-12 del modelo y de sus datos (hallazgos AM-01 a AM-19) y el mapa verificado de la
validación v1: protocolos, vecindario, topes de filas, ensamble, retransformación y ruido.

## 0. Relación con la v1

- **La v1 queda intacta:**
  - modelos, paneles, OOF, superficies y exposición;
  - el documento `docs/modelo_1km_horario.qmd`, que no se re-renderiza en su lugar (AM-01);
  - sus huellas, registradas en la referencia del 2026-10-12.
- **Dónde va la v2:** código nuevo e independiente del documento en `scripts_modelo_1km/v2/`. Salidas en una raíz propia, `AIR_POLLUTION_MODELO_1KM_ROOT=~/Asesorias_Data_local/AirPollution/modelado_1km_v2`, con candado de escritura, y tablas pequeñas en `output_files/modelo_1km_v2/`.
- **Insumos:** la v2 lee los paneles v1 (`paneles/panel_{pm25,no2}.parquet`) en sólo lectura. Los recálculos van a la raíz v2.
- **Procedencia:** cada artefacto registra el commit, el hash del código, el sha256 de cada insumo, la versión de cada biblioteca, los hilos y las semillas.

## 1. Protocolos externos

Se fijan en un manifiesto de pliegues (`pliegues_v2.json`, con grupos, k y semillas) antes de ajustar ningún motor.

| Protocolo | Grupo de prueba | Exclusión adicional del entrenamiento |
|---|---|---|
| LOSO-D | conglomerado de estaciones a ≤ 2 km (componentes conexas; retira juntos 309/310/330/333, B03/B04, 503/548 y las celdas compartidas) | ninguna |
| LBO-10 | el mismo conglomerado | toda estación a ≤ 10 km del conglomerado (como la v1) |
| BLQ-75 | bloque de una rejilla fija de 75 km en UTM 19S (EPSG:32719) con al menos una estación | ninguna |
| LRO | región SINCA | ninguna |
| LPO | cuatrienio del año local | el vecindario de prueba usa la red concurrente; se declara así |

**Regla única de exclusión por pliegue:** el conjunto excluido se aplica en cuatro lugares:
1. a las filas de entrenamiento;
2. al vecindario de entrenamiento;
3. al vecindario de prueba;
4. a los residuos de la retransformación.

## 2. Vecindario

- **Recálculo:** `obs_vec`, `peso_vec` y `dist_est_km` se recalculan en todos los pliegues de LOSO-D, LBO-10, BLQ-75 y LRO, en entrenamiento y en prueba, sin ninguna estación excluida. No hay atajo para conjuntos de una estación.
- **Implementación:** una sola función para todos los motores (núcleo gaussiano de 150 km, como la v1), que registra cada recálculo.
- **Producción:** en las celdas con monitor propio, la estación entra al vecindario. Como ese régimen no existe en el entrenamiento, se informa como no evaluado.

## 3. Motores y ejes de comparación

**Eje A, mismos predictores, blanco y retransformación:**
- **Predictores y blanco:** los 70 predictores de PM2,5 y los 69 de NO2; blanco log1p.
- **LightGBM** (receta v1): 800 rondas, tasa 0,03, 127 hojas, mínimo 50 filas por hoja, bagging 0,8, feature_fraction 0,8 y L2 = 1; con `deterministic=True`, `force_col_wise=True` y 12 hilos.
- **XGBoost** (receta equivalente): `tree_method=hist`, `max_leaves=127`, `grow_policy=lossguide`, eta 0,03, 800 rondas, subsample 0,8, colsample 0,8, lambda 1 y `min_child_weight` equivalente.
- **Random Forest** (receta v1): 300 árboles, √p predictores por división y hojas de al menos 20 filas.
- **MLP** (receta v1): parada temprana con validación agrupada por estación, no al azar.
- **Promedio simple** de los cuatro motores, sin pesos ajustados.

**Eje B, líneas base de diseño restringido:** GP, LME, GWR, RK e IDW, cada uno en su diseño. Su preprocesamiento se ajusta dentro del pliegue: medianas, indicadoras, escala y selección por cobertura.

**Alertas:** el cuantil 0,80 se juzga aparte.

**Hiperparámetros:** recetas fijas declaradas aquí, sin búsqueda para ningún motor. Si después se busca alguno, será en pliegues internos agrupados con la misma regla de exclusión y el mismo presupuesto para todos, como enmienda.

**Apilado anidado:** sólo en LRO y BLQ-75. Las predicciones de nivel 2 salen de pliegues internos agrupados dentro de cada pliegue externo. Los pesos son no negativos y suman 1. No compite con los motores fuera de esos dos protocolos.

## 4. Filas de entrenamiento

- **Permutación común:** una sola por pliegue, con semilla [42, k], compartida por todos los motores. Cada tope es un prefijo, de modo que los topes quedan anidados.
- **Comparación principal (eje A):** N común de 750.000 filas en todos los protocolos.
- **Curvas de aprendizaje:** LightGBM y XGBoost con 300.000, 750.000, 1,5 M y todas las filas, en LRO y BLQ-75; RF hasta 1,5 M.
- **Pares de evaluación:** se impone en el código la intersección de las predicciones finitas de todos los motores antes de agregar.
- **Validado = desplegado:** el modelo que se proponga para producción se valida con el mismo N con que se despliega.

## 5. Retransformación

- **Primaria (fijada aquí):** Duan por macrozona × franja (diurna de 08 a 18 h local), estimada con residuos log fuera de pliegue de los demás grupos, aplicando la misma exclusión del protocolo.
- **Respaldo cuando el resto tiene menos de 100 filas:** la franja de los demás grupos y luego el global de los demás. Nunca un total que incluya al propio grupo.
- **Sensibilidad en LRO y BLQ-75:** Duan con OOF interno dentro de cada pliegue externo.
- **Métricas en log:** se informan también, para separar el motor de la corrección.

## 6. Funciones de pérdida (etapa 8)

Para LightGBM y XGBoost, con el mismo N y los mismos pliegues:

| Pérdida | Blanco | Uso |
|---|---|---|
| Cuadrática en log + Duan | log1p | referencia (v1) |
| Cuadrática en escala original | y | media condicional directa |
| Huber | y | robustez a picos; δ = 1,345 × MAD de los residuos de un ajuste cuadrático del entrenamiento del pliegue |
| Cuantílica (pinball) τ = 0,05, 0,5 y 0,95 | y | mediana e intervalos de predicción del 90 % |

- **Métricas comunes en escala original:** R², RMSE, MAE y NMB.
- **Cuantiles:** cobertura del intervalo del 90 %, puntaje de intervalo y calibración por decil de predicción, macrozona y franja.

## 7. Calidad del blanco (etapa 9, sin descargas nuevas)

- **Bandera de calidad:** se lleva `qc_observacion` de SINCA al panel v2, uniendo por estación × hora desde el derivado SINCA en sólo lectura.
- **Variantes de entrenamiento:**
  - todo, como la v1;
  - validado y preliminar;
  - sólo validado.
- **SNIFA:** `numeric_usable` frente a `usable_native`.
- **Evaluación:** siempre sobre filas validadas, y también sobre todas.
- **Comparación de variantes:** con LightGBM en el eje A, LOSO-D y LRO.

## 8. Métricas e inferencia de diferencias

- **Niveles:** horario, diario (día civil de America/Santiago y día UTC−4, con al menos 18 horas), mensual y anual.
- **Desagregaciones:**
  - macrozona y estación;
  - régimen de predictores (con o sin GEOS-CF y TROPOMI);
  - estrato de soporte (cuartiles de `peso_vec` y `dist_est_km`);
  - ponderado por población.
- **Ruido:** 3 semillas (submuestra y motor) en LRO y BLQ-75 para cada motor del eje A; en los demás protocolos, 1 semilla.
- **Diferencias entre motores:** ΔR², ΔRMSE y ΔNMB pareados, con bootstrap por bloques (conglomerado en LOSO-D y LBO-10, bloque en BLQ-75, región en LRO y cuatrienio en LPO; 2.000 réplicas).
- **Regla de superioridad:** un motor supera a otro sólo si el intervalo del 95 % de la diferencia excluye 0 y la diferencia supera el ruido de semillas medido.

## 9. Regla de decisión para el producto v2

- **Elección del motor:** se elige el motor de producción por el R² diario (día civil) ponderado por población en LRO y BLQ-75. Si ninguno supera a LightGBM según §8, se mantiene LightGBM.
- **NO2:** se publica además una máscara de soporte (`peso_vec` y `dist_est_km` fuera del rango del entrenamiento) y una capa de incertidumbre por celda a partir de los modelos cuantílicos.
- **Producción:** la producción de superficies v2, con su agregado diario civil, es un paso posterior y aparte (etapa 10).
- **Resultados que no ganan:** todos se guardan.

## 10. Presupuesto de cómputo

- **Piloto de tiempos:** antes de la corrida completa se miden los tiempos con 2 pliegues por protocolo y motor (un tiempo no es un resultado).
- **Ajuste según el piloto:** si el total supera unas 120 horas de máquina, se reduce en este orden:
  1. semillas sólo en LRO;
  2. curvas de aprendizaje sólo en LRO;
  3. MLP sólo en LRO y BLQ-75.

  Todo recorte queda en la bitácora del manifiesto.
- **Paralelización:** por pliegue, con puntos de control atómicos y reanudables.

## 11. Pendiente de autorización del autor (no forma parte de este contrato hasta aprobarse)

- **Descargas nuevas:** NASADEM o Copernicus GLO-30; extender GEOS-CF, TROPOMI NO2, MERRA-2 y BLH; GOES ABI.
- **Predictores DMC:** cuando termine su descarga y pase su control de calidad.

Cada una entrará como enmienda, con su propia variante etiquetada y la misma comparación.

## Enmiendas

### Enmienda 1 (2026-10-13, antes de cualquier ajuste comparativo)

**Motivo y transparencia.** La construcción dejó 39 valores provisionales y 1 pendiente en `config_v2.json`. El piloto de tiempos y la unión de la bandera de calidad mostraron vacíos de fondo. Un primer borrador de esta enmienda pasó una revisión independiente con dos enfoques: metodología, y caminos que se bifurcan y coherencia. Esta versión la incorpora; el borrador y la revisión quedan en el repositorio de salud (privado), en `auditoria/20261012/enmienda1_ambiental/`.

**Lo que se sabía al escribirla:**
- **v2:** sólo se midieron tiempos; no existe ninguna métrica de desempeño. Artefactos del piloto, que quedan congelados: `plan_corrida_v2.json` (sha256 7385414e…), `piloto_tiempos/mediciones.json` (aea002f6…) y `pliegues_v2.json` (5e965c22…).
- **v1:** sus resultados sí se conocen:
  - RF supera a LightGBM en NO2;
  - en la retransformación, la evidencia v1 es mixta. En PM2,5 el *smearing* global tuvo menor NMB (1,73 % frente a 2,37 %) pero menor R² (0,4031 frente a 0,4054); en NO2, ½·σ² por macrozona ganó en las dos métricas. El *smearing* por macrozona nunca se probó.
- **Salvaguardas:** cada decisión se funda en la literatura, la continuidad o los datos (no en esos resultados), y se informa la alternativa.
- **Declaración:** el 2026-10-13, entre las 00:44 y las 00:46, `DISENO_AMBIENTAL_V2.md` se reemplazó un minuto y medio por su versión del commit 51d125e, para confirmar la construcción contra el contrato original. En esa ventana sólo corrieron las pruebas unitarias. En adelante las comparaciones con versiones anteriores se hacen con `git show` a un temporal, nunca reemplazando el archivo.

#### 1. Provisionales ratificados (los 39, por nombre)

1. **Protocolos:** `protocolos.BLQ-75.origen_m` = (0, 0) de EPSG:32719, con el amortiguador del punto 8, y `protocolos.semilla.k` en orden lexicográfico, como la v1.
2. **XGBoost** (`motores.eje_A.xgboost.*`):
   - `colsample.variante` = `colsample_bytree` 0,8;
   - `min_child_weight` = 50, declarado como «equivalencia con hessiana 1»: el código impide usarlo con un objetivo de hessiana no constante;
   - `max_depth` = 0, `max_bin` = 255, `nthread` = 12 y `seed` = 42.
   - `determinismo`: se verifica con dos corridas idénticas bit a bit. LightGBM arma los cortes con una muestra de 200.000 filas y XGBoost con todas; la diferencia queda documentada y la receta v1 de LightGBM no se toca.
3. **RF y MLP:**
   - `motores.eje_A.random_forest.n_jobs` = 12, con la predicción por trozos y un hilo por trozo;
   - `motores.eje_A.mlp.parada_temprana.fraccion` y `.criterio`: se ratifican con el cambio del punto 6.
4. **Promedio, eje B y alertas:**
   - `motores.eje_A.promedio_simple.escala` = log;
   - `motores.eje_B.topes_de_filas` = GP 3.000, LME 300.000 y GWR, RK e IDW todas. A diferencia de la v1, el GP ya no estratifica: es un prefijo de la permutación común;
   - `motores.alertas.receta` = la de la v1, pero con el N común de 750.000 en lugar de 1,5 M.
5. **Apilado:** `motores.apilado_anidado.bases` = los cuatro motores del eje A, `.pliegues_internos` = 5 agrupados y `.escala` = log.
6. **Filas:** `filas_entrenamiento.permutacion.generador` = `default_rng(semilla).permutation` sobre los índices en orden ascendente; `.disponibles_menos_que_el_tope` = todas, con el N efectivo registrado.
7. **Retransformación:**
   - `retransformacion.primaria.global_de_los_demas_con_menos_de_100_filas` = sin corrección, con marca;
   - `retransformacion.sensibilidad.pliegues_internos` = los del apilado.
8. **Pérdidas:** `perdidas.variantes[2].delta.mad`, `.ajuste_cuadratico`, `.implementacion_xgboost` y `perdidas.hiperparametros_por_perdida` se ratifican con el cambio del punto 9.
9. **Calidad:** `calidad_blanco.codigos_qc` y `calidad_blanco.snifa.cruce_con_variantes_sinca` quedan como en el borrador:
   - «todo» = validado + preliminar + no validado, más SNIFA `numeric_usable`;
   - «validado y preliminar» = validado + preliminar, más SNIFA `usable_native`;
   - «sólo validado» = validado, más SNIFA `usable_native`.

   «No validado» no distingue un dato sin revisar de uno rechazado; E1 lo trata como observación, como la v1.
10. **Métricas:**
    - `metricas.niveles.mensual.minimo_dias` = 20 y `.anual.minimo_meses` = 9;
    - `metricas.desagregaciones.regimen_de_predictores.criterio`: ver el punto 10;
    - `.estrato_de_soporte.distribucion_de_referencia` = los pares de evaluación con el vecindario recalculado;
    - `.ponderado_por_poblacion.poblacion`: ver el punto 4.
11. **Ruido e inferencia:** `ruido.valores` se ratifica (réplicas 0-2; [42, k] y [42, k, r]; motor + 1.000·r). `inferencia_diferencias.bootstrap.metodo_del_intervalo`, `.semilla` y `.nivel_de_agregacion` y `inferencia_diferencias.regla_de_superioridad.medida_del_ruido` cambian según los puntos 3 y 5.
12. **Presupuesto:** `presupuesto.piloto.eleccion_de_los_pliegues` = el de más y el de menos filas de entrenamiento.

#### 2. Retransformación (§5)

- **Primaria:** el *smearing* de Duan (1983): ajuste = log(media de eʳ) por macrozona × franja. Es consistente sin suponer errores normales ni homocedásticos y además corrige el sesgo medio en log.
- **Sensibilidad fija:** la corrección lognormal ½·σ² de la v1, para todos los motores en log y todos los protocolos, con la misma clave, exclusión y respaldo, y su par en el bootstrap.
- **Nombres:** el código renombra las formas (`smearing_duan` y `lognormal_medio_sigma2`) y la variante de pérdida (`l2_log_smearing`; la referencia v1 es `l2_log_medio_sigma2`). La forma usada queda en `consolidado.json`, en las trazas y en las tablas.
- **Respaldo honesto:** la clave macrozona × franja de «los demás» se usa sólo si reúne al menos 3 conglomerados LOSO-D de al menos 2 grupos del protocolo distintos del retirado, con un piso de 100 filas. Si no, se usa la franja de los demás y después el global de los demás. Por pliegue se registran el nivel, las estaciones que aportan y el factor.
- **Fuga de segundo orden:** queda declarada. Los residuos de los demás grupos vienen de modelos que vieron al grupo retirado. La sensibilidad con OOF interno la elimina, pero tiende a sobrecorregir.
- **Regla previa:** un reemplazo de motor sólo vale si la decisión coincide con el *smearing* y con ½·σ².
- **Comparaciones v2 frente a v1:** se hacen con la misma corrección, para separar el aporte del motor del de la corrección.

#### 3. Ruido de semillas (§8)

- **Qué se mide:** el ruido de la **diferencia**, no el de cada motor. En cada réplica r = 0, 1, 2 se calcula Δ_r con los mismos pares, nivel y ponderación. La estimación puntual es la media Δ̄.
- **Condición:** se exige |Δ̄| > rango(Δ_r), lo que implica el mismo signo en las tres réplicas. Su tasa de paso por azar es fija (8,1 %) para cualquier correlación entre motores. Los tres Δ_r se publican.
- **Apilado:** como no tiene réplicas, su ruido es el máximo del de sus bases.

#### 4. Ponderación (§8)

- **Peso por estación:** la población de su celda (`pob_dens`) se fija como la **mediana de sus años**, para que los saltos del ráster entre versiones (2013, 2017 y 2022) no cambien el peso.
- **Sensibilidad:** un peso de desagrupamiento, la población de la comuna dividida por las estaciones de la red en ella.
- **Sin ponderar:** la dirección de todo reemplazo debe repetirse sin ponderación.
- **G efectivo:** junto a cada métrica ponderada se informan el G efectivo y el número efectivo de estaciones (Kish).

#### 5. Inferencia de diferencias (§8)

- **Bootstrap percentil:** se mantiene. Como ΔR² = −ΔSSE/SST con un SST común, se agrega una segunda prueba sobre los totales por bloque de w·(e_A² − e_B²): jackknife por bloque (CV3) con t de G − 1 gl, o la prueba de cambio de signo del bootstrap salvaje por conglomerado (Rademacher; Webb si G < 12).
- **Superioridad:** se declara sólo si las dos pruebas coinciden.
- **Influencia:** la superioridad debe sobrevivir a quitar el bloque más influyente (la RM en LRO y E004N083 en BLQ-75); si no, se informa como no robusta.
- **Informes:** G, G efectivo y Δ sin cada bloque.
- **Bloques del bootstrap en LOSO-D y LBO-10:** el bloque de 75 km, no el conglomerado, para captar la dependencia de cuenca.
- **LPO:** es descriptivo.

#### 6. Parada temprana de la MLP

- **Validación:** se sortea por conglomerados LOSO-D. En LRO y BLQ-75 se valida con grupos completos del protocolo (regiones o bloques), hasta ~10 % de las filas, estratificado por macrozona.
- **Vecindario:** se recalcula sin las estaciones de validación.
- **Reajuste:** después se reajusta con todas las estaciones del pliegue durante la época elegida, que queda registrada.

#### 7. Evaluación y calidad (§7)

- **Conjuntos:**
  - E1: todas las filas;
  - E2: filas validadas, con el `usable_native` de SNIFA;
  - E2-SINCA: sin SNIFA;
  - E1′: todas las filas de las estaciones que tienen alguna fila en E2, para separar calidad de composición.
- **E1 y E2 son coprimarios en la decisión:**
  - el reemplazo exige superioridad en E1;
  - en E2 exige el mismo signo del ΔR² diario civil ponderado sobre los pares comunes validados, en LRO y en BLQ-75.
- **Evaluabilidad:** E2 es evaluable en un protocolo si conserva ≥ 50 % del peso de E1 y ≥ 5 grupos con filas E2. Si no lo es, no bloquea, pero se informa como «sin confirmación con datos validados».
- **Registro:** los pliegues y las estaciones sin E2 quedan registrados. 45 de las 107 estaciones de PM2,5 y 33 de las 54 estaciones SINCA de NO2 no tienen ninguna fila validada.

#### 8. BLQ-75 con amortiguador

- **Problema:** la rejilla con origen (0, 0) parte Gran Santiago, Gran Concepción y Quintero-Puchuncaví. Así, 10 de 34 bloques de PM2,5 tenían una estación de entrenamiento a menos de 10 km.
- **Corrección:** en BLQ-75 se excluyen del entrenamiento y del vecindario las estaciones a ≤ 10 km (haversine) de cualquier estación del bloque de prueba, como en LBO-10.
- **Manifiesto:** se vuelve a fijar `pliegues_v2.json` con su bitácora, informando por bloque la distancia mínima de prueba a entrenamiento.

#### 9. Huber y cuantiles (§6)

- **δ común:** δ es el mismo para LightGBM y XGBoost en cada pliegue. Sale del ajuste cuadrático en escala original de LightGBM, con residuos honestos de una partición agrupada en dos dentro del entrenamiento: δ = 1,345 × MAD normalizado.
- **Sensibilidad:** δ = cuantil 0,9 de |r| (Friedman 2001).
- **Registro:** la fracción de filas recortadas y la pérdida final.
- **Declaración:** con el gradiente recortado y 800 rondas, los picos invernales pueden quedar fuera de alcance.
- **Huber y q50** no estiman la media y no compiten en el §9.
- **Cuantiles:** se reordenan (q05 ≤ q50 ≤ q95) antes de medir la cobertura, informando los cruces. Se calibran con conformal agrupado (CQR; Romano et al. 2019), con residuos fuera de pliegue de los demás grupos, la misma exclusión y la clave macrozona × franja. Así se arma la capa de incertidumbre del §9.

#### 10. Regímenes de predictores (§8, descriptivo)

- **Por disponibilidad:**
  - 2000-2002, sin CAMS;
  - 2003-2018, sin GEOS-CF ni TROPOMI;
  - 2019-2024, con GEOS-CF y con TROPOMI en ~70 % de las filas;
  - 2025, sin GEOS-CF ni TROPOMI y con ACAG climatológico;
  - 2026, además sin CAMS y con MERRA-2 y BLH incompletos.
- **Sensibilidad:** la disponibilidad fila a fila.
- **LPO:** 2024 se informa aparte de 2025-2026.
- **Alcance:** los regímenes no alteran el §9.

#### 11. Regla de decisión (§9, cerrada)

- **Por contaminante.** Los candidatos son XGBoost, RF, MLP y el promedio simple. El apilado es sólo descriptivo y no se despliega.
- **Condiciones para que un candidato c reemplace a LightGBM**, en LRO y en BLQ-75, todas a la vez:
  1. el ΔR² diario civil, ponderado con los pesos fijos del punto 4 y sobre E1, tiene un IC percentil del 95 % ajustado por Holm sobre los 4 candidatos que excluye 0 a favor de c, y la segunda prueba del punto 5 coincide;
  2. |Δ̄| supera el ruido de la diferencia (punto 3);
  3. pasa la consistencia con E2 del punto 7;
  4. sobrevive a quitar el bloque más influyente;
  5. el signo se repite sin ponderar y en las métricas en log;
  6. la decisión se repite con la corrección ½·σ²;
  7. |NMB_c| ≤ |NMB_LightGBM| + 1 punto porcentual (no inferioridad en sesgo).
- **Desempate:** si varios candidatos pasan, gana la mayor media simple de los dos R² ponderados sobre E1. Ante diferencias menores que el ruido, se prefiere un motor único al promedio, y el más barato de producir.
- **Evidencia parcial:** un candidato superior en un protocolo y no inferior en el otro se informa como «evidencia parcial». Sus superficies pasan a ser sensibilidad de exposición (etapa 10).
- **Pares de la decisión:** son la intersección sólo entre los candidatos y LightGBM. Se informa cuántos pares quita cada familia.
- **N de producción:** 750.000 filas para el motor elegido, el mismo N con que se valida en los dos protocolos. LightGBM con todas las filas se informa como sensibilidad en LRO, con la curva de aprendizaje.
- **Retransformación de producción:** los residuos fuera de pliegue de LRO con el mismo N.
- **Factibilidad, fijada ahora:** antes de la corrida se mide el tiempo de predecir un día completo de superficies con cada candidato (sólo tiempo). Un candidato cuya producción 2000-2026 exceda 7 días de máquina queda fuera de la decisión, con registro.
- **Implementación:** la regla se implementa como una función (`decidir_motor`), probada antes de la corrida. La decisión no se toma a mano.

#### 12. Presupuesto (§10)

- **Orden de recortes enmendado** (un tiempo no es un resultado):
  1. curvas de aprendizaje fuera de LRO;
  2. MLP fuera de LRO y BLQ-75;
  3. semillas fuera de LRO y BLQ-75;
  4. pérdidas del §6 fuera de LRO, BLQ-75 y LOSO-D.
- **Efecto:** con los recortes 1 y 2 el estimado es de 115,65 h y se conservan las semillas de BLQ-75. El punto 6 de la versión anterior (ruido de BLQ-75 tomado de LRO) queda sin efecto.
- **Revisión del plan:** antes de la corrida se vuelve a medir el piloto con la máquina libre (`--remedir-contaminadas 0.5`) y se rehace el plan con el nuevo orden.

#### 13. LOSO-D y distancias

- **LOSO-D:** la regla de componentes conexas a ≤ 2 km se mantiene. Hay conglomerados encadenados de hasta 3,7 km, listados en el manifiesto.
- **Distancias:** todos los radios usan haversine con R = 6.371 km, como la v1.

#### 14. Procedencia y sellado

- **Firma de los ajustes:** incluye el sha256 de la lista ordenada de predictores, la receta, la pérdida, la variante de calidad, y los sha256 del contrato y de la configuración. La retransformación se aplica al consolidar y queda registrada en `consolidado.json`.
- **Guardia de escritura:** compara rutas sin distinguir mayúsculas ni la forma Unicode, o por `st_dev` y `st_ino`.
- **Candado:** es por artefacto.
- **Sellado:** el contrato, la configuración y el código se confirman en git antes de cualquier ajuste comparativo.

### Complemento de la Enmienda 1 (2026-10-13, antes de cualquier ajuste comparativo)

**Motivo.** Al implementar la Enmienda 1, la configuración dejó 7 detalles con valor provisional. La verificación independiente encontró además que la regla de factibilidad y la segunda prueba no estaban bien fijadas. Sigue sin existir ninguna métrica de desempeño v2. Todo lo que sigue se decide con datos sintéticos, tiempos o principios.

1. **Segunda prueba del punto 5.**
   - **Prueba que decide:** el cambio de signo del bootstrap salvaje por bloque sobre los totales T_g = Σ w·d̄. Con G < 12 se usan pesos de Webb y 9.999 sorteos; con 12 ≤ G ≤ 16, Rademacher con enumeración completa; con G > 16, Rademacher con 9.999 sorteos. La semilla es [42, 3000, p].
   - **Jackknife CV3 con t de G − 1:** sólo informa.
   - **Motivo:** en simulación, con la concentración real del peso, el CV3 rechaza por encima de lo nominal y el cambio de signo mantiene el tamaño.
   - **Estimador:** el del provisional, con d̄ = media de las réplicas.
2. **Bootstrap percentil:** B = 1.999 réplicas, en vez de 2.000, para que el umbral de Holm nunca caiga en un empate exacto con el intervalo escalonado. La decisión usa el intervalo escalonado publicado.
3. **Factibilidad** (reemplaza la del punto 11):
   - **Cuándo y con qué:** se mide antes de cualquier ajuste comparativo, con predictores de producción:
     - LightGBM compilado con `lleaves`, como la producción v1;
     - XGBoost y RF compilados con `treelite` / `tl2cgen`;
     - la MLP en float32, por lotes.
   - **Datos:** matrices reales de predictores de 3 días (verano, invierno y transición), armadas con el código de producción v1 en sólo lectura y escritas en un temporal.
   - **Regla:** un candidato es factible si su producción 2000-2026 de los dos contaminantes cuesta ≤ 5 veces la de LightGBM compilado y ≤ 21 días de máquina con 12 hilos. El promedio simple cuesta la suma de sus miembros.
   - **Irrevisable:** esta regla y su medición no se revisan después de ver resultados.
4. **Ratificación de los 7 detalles provisionales,** con el valor que tienen en `config_v2.json`:
   1. la selección de grupos de validación de la MLP en LRO y BLQ-75;
   2. la partición honesta del δ de Huber (dos mitades de conglomerados LOSO-D, semilla [42, k, 1001]);
   3. el respaldo de la CQR, igual al de la retransformación primaria;
   4. las familias de la sensibilidad de régimen fila a fila;
   5. la población comunal del peso de desagrupamiento (INE, mediana de los años de la estación);
   6. el estimador de la segunda prueba (punto 1);
   7. la definición de evidencia parcial.
5. **Amortiguador en las particiones internas de BLQ-75.** El radio de 10 km del punto 8 también se aplica en las particiones internas:
   - la validación de la MLP;
   - los pliegues internos del apilado y de la retransformación con OOF interno;
   - la partición honesta del δ de Huber.

   En cada una se sacan del entrenamiento interno las estaciones a ≤ 10 km de las estaciones de su conjunto interno de validación.
6. **Réplicas:** la condición 2 del punto 11 exige las 3 réplicas comunes. Con menos queda «no evaluada», y un candidato no puede reemplazar a LightGBM. Lo mismo vale para el desempate.
7. **Firma:** la firma de los ajustes incluye el hash del código de las funciones de ajuste, en particular la validación de la MLP y el δ honesto de Huber. No depende de subir una versión a mano.
8. **Presupuesto:**
   - el orden de recortes del punto 12, incluido el recorte 4, se implementa en el código;
   - el piloto se vuelve a medir con la máquina libre (carga media < 2 al empezar y sin otros trabajos pesados), incluyendo el costo nuevo de la MLP (validación y reajuste) y del δ de Huber;
   - el código rehace el plan con esa medición, sin elección a mano.
9. **Manifiesto congelado del piloto:** es la copia `pliegues_v2_reemplazado_20261013T054105Z.json` (sha256 5e965c22…). El manifiesto vigente, con el amortiguador, es `pliegues_v2.json`.
10. **Candado:** los nombres de los candados por artefacto se normalizan (casefold + NFC), como la guardia de escritura.
