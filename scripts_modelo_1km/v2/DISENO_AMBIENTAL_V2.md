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

### Enmienda 2 ambiental — bloque «Red ampliada e insumos de hoy» (2026-10-25, antes de cualquier ajuste comparativo)

**Texto que rige.** Este bloque es el que adoptó el autor el 2026-10-25 y se ancló en el repositorio de salud (commit f2c6cfc, sello OpenTimestamps en 65afe8a): `auditoria/20261024/sinca_al_modelo/ENMIENDA_2_BLOQUE_RED_AMPLIADA.md`, sha256 274ebae06bee8eeeb7470a650ce0539af751577d292513b8198cdec7c159094b. Se transcribe sin cambios desde su segunda línea, con los encabezados bajados dos niveles para que quepan bajo «Enmiendas». Sus puntos R1 a R22 se traducen en `config_v2.json` → `red_de_monitores` y en los nodos que cita su §3. Los demás bloques de la Enmienda 2 se agregan después, sin cambiar este texto. Las decisiones de la traducción —T1 a T10, del autor; T11 a T13, por delegación ([delegadas]: decididas con la opción recomendada sin que el autor las viera; T13 exige que el autor las ratifique antes del armado, y el estado de esa ratificación queda en `red_de_monitores.ratificacion_t11_t13`)— están en `config_v2.json` → `contrato.enmiendas[2].decisiones_de_traduccion`; entre ellas, T12 (a) [delegada]: la segunda corrida del contraste se hace con el derivado cerrado y antes de armar el panel (`red_de_monitores.orden`), que es como se lee aquí «al cerrar el panel» (R6, R22 paso 3 y §4.1 del bloque). Si la ratificación cambia T12 (a), este párrafo cambia con ella, en el commit de la ratificación.

**Adoptado por el autor el 2026-10-25.** Historia: `BORRADOR_ENMIENDA_red_ampliada.md`, el borrador previo, se conserva sin cambios. Es un bloque de la Enmienda 2 al contrato ambiental v2 (AP `c7c47e8`:
`DISENO_AMBIENTAL_V2.md` `5d879a05…` y `config_v2.json` `232c75b3…`), autónomo y numerado R1-R22. Se ancla en APH. Su
traducción al contrato y a la configuración de AP va con el código (R22).

#### Decisiones del autor que este texto aplica

Fuente: `decisiones_autor_20261024.md`, con las respuestas literales del autor. Su huella está en la tabla final.

| # | Tema | Respuesta del autor (literal) | Dónde rige |
|---|---|---|---|
| 0 | Alcance | «BAJA TODO LO DE SINCA IGUAL»; «ya descarga todo dinca»; «recuerda que hay que colocarlas en el modelo con los contaminantes» | R1, R2 |
| P1 | Completitud | «que entre todo sin regla de completitud» | R3 |
| P2 | Especificación original | «no quiero contrastar todo con lo anterior nuevos datos nuevos modelos en base a lo que ya se hizo es mejorar lo anterior sin comporbar» | R12 |
| P3 | Cómo se arma el panel | «Todo con los insumos de hoy» | R11 |
| P4 | Estaciones de empresas | «Igual que las actuales (Recomendado)» | R10 |
| P5 | O3 | «Esquema de la v2 (Recomendado)» | R20 |
| U | Unidades µg/m³N y series sin unidad | «Convertir µg/m³N (Recomendado)». La temperatura la corrige U′ | R6 |
| A | Actualizar las 107 hasta octubre | «Sí, actualizar (Recomendado)» | R2, R4 |
| P9 | Estación-años en hora civil | «Convertir con la hora civil» | R7 |
| P7 | Red del producto meteorológico | «Con la red ampliada (Recomendado)» | R21 |
| P6 | Presupuesto después de los cuatro recortes | por omisión: se corre igual y se registra | R18 |
| P8 | Series duplicadas | por omisión: una copia por hora, la del código con más horas | R9 |
| U′ | Condiciones normales | «25 °C y 1 atm (Recomendado)» | R6 |
| S | Unidades de las estaciones actuales | «Misma regla para todas (Recomendado)» | R6 |
| V | Verificar el rótulo | «Contrastar con CAMS (Recomendado)» | R6 |
| F | Fin del período | «2026-10-24 (Recomendado)» | R4 |
| — | Corte de los insumos | por omisión: lo registrado al fin del 2026-10-24 | R11 |
| C | Estaciones nuevas sin coordenada usable | «Corregir con documento oficial (Recomendado)» | R8 |
| I | Series de unidad indeterminada | «Que decida el rótulo» | R6 |
| Pil | Lo visto del piloto | «No vi sus cifras» | §1 |
| Lug | Dónde va el bloque | «Dentro de la Enmienda 2 (Recomendado)» | §0 |
| C2 | Tolerancia costera de la 207 | «Aceptar la tolerancia (Recomendado)» | R8 |
| C3 | Maestro de coordenadas del modelo | «La corregida, con 106 (Recomendado)» | R2, R8 |
| Anc | Cuándo se ancla | «Ahora, en APH (Recomendado)» | §0, R22 |

**Cómo se redactó.**
- Se leyeron el contrato, la configuración y el código v1 y v2.
- De los manifiestos y los paneles se leyeron sólo cabeceras, columnas y conteos.
- Para el contraste de unidades (R6), se leyeron valores de concentración de SINCA y de CAMS. No se leyó ninguna métrica de
  modelo ni se abrió el piloto.
- Las coordenadas corregidas (R8) las armó otro agente; aquí se citan sus archivos.
- Las huellas de la tabla final se calcularon con sha256 el 2026-10-25.
- Sin red ni datos DMC.

**Abreviaturas:**
- AP = repositorio `Air-Pollution`; APH = `Air-Pollution-Health-Chile`;
- DATOS = `/Volumes/Datos/Asesorias_Data/AirPollution/data`; AMP = `DATOS/sinca_ampliacion_20261024`;
  GEO = `AMP/geometria_20261025`;
- LOCAL = `~/Asesorias_Data_local/AirPollution`.

Cada punto trae tres partes:
- **Anclado:** cita exacta del contrato o de la configuración. Si el contrato no lo fija, se cita el código v1 que lo fija.
- **Nuevo:** el texto que rige.
- **Por qué.**

---

#### 0. Dónde va y cuándo se ancla

- **Lugar** (decisión Lug, «Dentro de la Enmienda 2 (Recomendado)»): este texto es un **bloque de la Enmienda 2 ambiental**,
  con un solo texto y un solo anclaje antes de M3-4 y de M6. Hay tres razones:
  1. La Enmienda 2 fija «cómo se comparan las extensiones», y este bloque mete extensiones del §11 sin comparación (R11 y R12).
  2. El protocolo meteorológico exige: «La Enmienda 2 ambiental y la enmienda de la DMC se anclan antes de cualquier ajuste de
     I o D».
  3. El piloto se declara una sola vez (§1).
- **Cláusula:** si la Enmienda 2 no está lista antes de M3-4, el bloque se ancla solo, **sin cambiar su texto**.
- **Anclaje** (decisión Anc, «Ahora, en APH (Recomendado)»): por esa cláusula, el bloque se ancla ya, solo, en APH (commit
  local y sello OpenTimestamps, sin envío al remoto). Los demás bloques de la Enmienda 2 se anclan después y no cambian este
  texto.

---

#### 1. Lo que se sabía al escribirlo (declaración)

- **v2:** no existe ninguna métrica de desempeño.
- **Piloto visto después del sellado.** Es `piloto_perdidas_sin_dmc`: «métricas reales de LightGBM frente a XGBoost en la
  región VIII, 2024» (protocolo meteorológico v2.1, §1, punto 5). Sus salidas están en:
  - `AP/output_files/modelo_1km_v2/piloto_pre_dmc_20261013/`;
  - `LOCAL/modelado_1km_v2/pilotos_exploratorios/`;
  - `AP/docs/piloto_perdidas_sin_dmc_20261013.html`.

  Este texto no abrió sus salidas.

  > **Declaración del autor (2026-10-25):** «No vi sus cifras».
  > - El piloto `piloto_perdidas_sin_dmc` se corrió el 2026-10-13 a las 22:28, después del sellado, y lo corrió un asistente.
  > - El autor no miró sus resultados.
  > - Ninguna decisión de este bloque se tomó a la vista de ellos.
- **El piloto y la red.**
  - Ninguna de las estaciones nuevas de NO2 de la región VIII (846, 850 y 876) tiene datos en 2024: sus series terminan entre
    2017 y 2018.
  - **7 de las 9 estaciones actuales de NO2 rotuladas µg/m³N son de la región VIII:** 802, 826, 827, 830, 841, 854 y 870. El
    contraste con CAMS las deja indeterminadas y, por la decisión I, entran convertidas según su rótulo. Sus valores bajan a
    cerca de la mitad de lo que usó la v1, lo que toca la región del piloto.
  - La regla de unidades se decidió por los rótulos y por el contraste, no por el piloto.
- **v1:** sus resultados sí se conocen. NO2 transfiere mal a regiones sin monitores (R² diario LRO 0,119) y RF supera a
  LightGBM en NO2.
- **Lo que vio el redactor de la ampliación:**
  - el número de estaciones y de series;
  - las unidades, la técnica, el propietario y el operador de las fichas;
  - las coordenadas;
  - las fechas de la primera y la última observación y las filas con observación por serie;
  - una cuenta aproximada de conglomerados y bloques;
  - **para el contraste de unidades, los valores** de NO2, O3, SO2 y CO de las series actuales y nuevas, y los de CAMS. De
    ellos sólo se calcularon razones de niveles y razones con la vecina más cercana.
- **Las decisiones del autor no se fundan en el piloto ni en métricas v2:**
  - «BAJA TODO LO DE SINCA IGUAL»;
  - «que entre todo sin regla de completitud»;
  - «mejorar lo anterior sin comprobar»;
  - «Todo con los insumos de hoy».

---

#### 2. Puntos del bloque

##### R1. Motivo y alcance

- **Anclado:** §11: «**Pendiente de autorización del autor (no forma parte de este contrato hasta aprobarse)**».
- **Nuevo:** «El 2026-10-24 y el 2026-10-25 el autor decidió:
  - bajar todo SINCA («BAJA TODO LO DE SINCA IGUAL»);
  - que las estaciones nuevas entren al modelo como monitores («recuerda que hay que colocarlas en el modelo con los
    contaminantes»), sin mínimo («que entre todo sin regla de completitud»);
  - armar el panel con los insumos de hoy («Todo con los insumos de hoy»);
  - no contrastar con lo anterior («no quiero contrastar todo con lo anterior… mejorar lo anterior sin comprobar»).

  Este bloque fija cómo entra eso al contrato. No existe ninguna métrica v2.»
- **Por qué:** una enmienda dice su motivo con las palabras de quien decide.

##### R2. Lista cerrada de estaciones y huellas

- **Anclado:** §0: «**Insumos:** la v2 lee los paneles v1 (`paneles/panel_{pm25,no2}.parquet`) en sólo lectura».
  `relacion_v1.insumos_v1_solo_lectura`: `["paneles/panel_pm25.parquet", "paneles/panel_no2.parquet"]`.
- **Nuevo:** «La red de la v2 se cierra con estas fuentes. Las huellas completas están en la tabla final. Ninguna estación
  posterior entra en la v2.

  | Fuente | Huella sha256 | Qué es |
  |---|---|---|
  | `DATOS/sinca/manifiesto_descarga.csv` | `79d4fd77…` | 1.685 series horarias de las 107 estaciones actuales, hasta el 2026-09-13 |
  | `DATOS/sinca/estaciones_georreferenciadas.csv` | `51ff693e…` | maestro de coordenadas de las 109 configuradas (idéntico, byte a byte, a `AMP/actualizacion_configuradas/estaciones_georreferenciadas.csv`) |
  | `AMP/actualizacion_configuradas/manifiesto_descarga.csv` | `0fc77ae1…` | actualización (decisión A): 330 series horarias de 97 de las 107 estaciones, desde su último día en disco (2026-09-03 a 2026-09-13) hasta el 2026-10-24, en archivos nuevos |
  | `AMP/actualizacion_configuradas/SHA256SUMS.txt` | `78528379…` | huellas de los archivos de la actualización |
  | `AMP/manifiesto_descarga.csv` | `19865e3b…` | 167 series horarias nuevas de 77 estaciones nuevas (los seis contaminantes del exportador) |
  | `AMP/SHA256SUMS.txt` | `db36e208…` | huellas de todos los archivos de la ampliación |
  | `AMP/estaciones_fichas.csv` (= `catalogo/20261024T232023Z/estaciones_fichas.csv`) | `5d22889a…` | 219 fichas: 109 configuradas y 110 nuevas |
  | `AMP/catalogo/20261024T232023Z/catalogo.json` y su `SHA256SUMS.txt` | `1c523f6f…`, `14c9b5cb…` | instantánea del catálogo |
  | `AMP/estado_validacion_series.csv` | `b6ee431f…` | filas validadas, preliminares y no validadas por serie |
  | `AMP/manifiesto_descarga_otras_series.csv` | `dee25704…` | 1.076 series diarias y discretas y de otros compuestos: **no entran** al panel horario. Sólo dan la unidad de la ficha de las estaciones actuales (R6) |
  | `GEO/estaciones_georreferenciadas.csv` | `d5764ee2…` | maestro de coordenadas de las **106** estaciones nuevas, con las correcciones de R8 (decisión C3) |
  | `GEO/SHA256SUMS.txt` | `945640f3…` | huellas del maestro corregido, sus fichas y sus documentos |
  | `DATOS/snifa_adicional/processed/observaciones_horarias.parquet` | `2aa177d9…` | los 3 monitores SNIFA de NO2, como hoy |

  El maestro `AMP/estaciones_georreferenciadas.csv` del 2026-10-24 (`c5eb0806…`) **no se usa**. No se mueve ni se pisa.

  **Estaciones nuevas con series horarias de los contaminantes del contrato:**
  - **PM2,5 (2):** 332 Copiapó Sivica y D31 Cerrillos.
  - **NO2 (26):**
    - 8 en ppb: 252, 501, 506, 507, 511, 602, 846 y 850;
    - 13 en µg/m³N: 207, 209, 215, 216, 221, 329, 517, 518, 533, 534, 614, 876 y E01;
    - 5 sin unidad: 601, 603, 816, A02 y A03.
  - **O3 (25, para su rama; R20):**
    - 10 en ppb: 501, 506, 507, 511, 601, 602, 603, 816, 846 y 850;
    - 12 en µg/m³N: 207, 215, 216, 221, 329, 518, 519, 533, 534, 614, 876 y E01;
    - 3 sin unidad: 517, A02 y A03.

  **Quedan fuera por coordenadas** (R8): 518 «Rural 1»; 408 «Punta Chungo», que no tiene series del contrato; y las fichas
  sin código (id 38 «Cine Inca» e id 44 «Intelec»).

  **Red resultante** (después de R6 y R8):
  - **PM2,5:** 107 actuales y 2 nuevas, 109 en total.
  - **NO2:** 71 en total:
    - 48 actuales SINCA: 39 en ppb y 9 rotuladas µg/m³N, convertidas;
    - 20 nuevas: 8 en ppb y 12 rotuladas µg/m³N, convertidas;
    - 3 SNIFA.

    Salen las 6 actuales sin unidad (513, 529, 532, 609, 878 y 901), las 5 nuevas sin unidad y la 518.
  - **O3, para su rama:** 69 en total:
    - 47 actuales (salen 827, 837 y 901, sin unidad);
    - 22 nuevas (salen A02 y A03, sin unidad, y la 518).»
- **Por qué:** la red queda fijada por archivos con huella, no por lo que haya en disco el día que se corra. Si la lista
  quedara abierta, la red podría cambiar después de ver resultados.

##### R3. Regla única de inclusión (sin completitud)

- **Anclado:** `protocolos.LOSO-D.estaciones`: «las del panel de cada contaminante, con las coordenadas de
  estaciones_con_celda() (qmd:1968-1970)». El contrato no tiene un criterio de inclusión: hoy entra toda estación del maestro
  con celda y con al menos una hora que pase el control. La 833 entra con 768 horas de PM2,5.
- **Nuevo:** «Una estación entra al panel de un contaminante si:
  1. está en la lista de R2;
  2. tiene coordenadas usables y celda (R8);
  3. tiene al menos una hora que pase R4 a R9.

  **No hay mínimo de horas, días ni años.** La regla es la misma para las 107 actuales, para las 3 SNIFA y para las nuevas.»
- **Por qué:** es la decisión P1 y es la regla vigente escrita. Una sola regla impide agregar un mínimo después. Los mínimos
  de agregación del §8 (≥ 18 h por día, ≥ 20 días por mes y ≥ 9 meses por año) no cambian: definen los niveles diario,
  mensual y anual, no qué estación entra.

##### R4. Período

- **Anclado:** `protocolos.LPO.ventanas`: `{"anio_desde": 2000, "anio_hasta": 2026, "largo_anios": 4, "fuente": "como la v1
  (qmd:300-301 y 344-351): 2000–2003 … 2024–2026, la última parcial"}`. El panel v1 va de 2000-01-01 a 2026-09-13.
- **Nuevo:** «Las observaciones van del 2000-01-01 al **2026-10-24**, para todas las estaciones.
  - Lo anterior a 2000 no entra: hay series nuevas que empiezan en 1990.
  - La actualización de cada serie actual parte de su último día en disco, con solape. El ranking del derivado elige la fila
    `seleccionada` en las horas repetidas.
  - Las 10 estaciones actuales sin datos nuevos (222, 236, 549, 833, 904, A04, D11, D16, D29 y E06) quedan con su serie hasta
    su último dato.
  - Una fila entra aunque le falten predictores, como en la v1 (los meses sin CAMS de 2026). Las filas posteriores al último
    dato de ERA5-Land (2026-09) llevan vacías las columnas meteorológicas.
  - Las ventanas LPO no cambian: 2024-2026 sigue siendo la última, parcial.»
- **Por qué:** son las decisiones A y F. Un solo período para todas, en el que entra todo lo bajado.

##### R5. Control de calidad de los valores

- **Anclado:**
  - §7: «**Bandera de calidad:** se lleva `qc_observacion` de SINCA al panel v2, uniendo por estación × hora desde el derivado
    SINCA en sólo lectura».
  - `calidad_blanco.no_validado`: «“no validado” no distingue un dato sin revisar de uno rechazado; E1 lo trata como
    observación, como la v1 (Enmienda 1, punto 1.9)».
  - El filtro de la v1 está en código: `_comun_modelo.series_sinca` y `produccion.observaciones` (`QC_RACHA = 24`).
- **Nuevo:** «Para todas las filas rige el mismo control:
  - filas `seleccionada` del derivado (ranking `afg_lib` con su huella);
  - valor finito, **después de convertir la unidad (R6)**, en el rango operacional: PM2,5 0-1.500 µg/m³; NO2 0-1.000 ppb;
    O3 0-500 ppb;
  - media de los duplicados por estación × hora;
  - rachas de ≥ 24 registros idénticos, sobre el registro completo;
  - celda ≥ 0.

  `qc_observacion` sale del derivado. E1, E2, E2-SINCA y E1′ siguen como en la Enmienda 1, punto 7. El derivado de las
  estaciones nuevas y de la actualización se arma con `preparar_sinca_modelado.py`, con el mismo contrato
  (`airpollution.sinca.modelado.v1.0.0`) y la misma huella del ranking, en una raíz aparte. El derivado v1 no se toca.»
- **Por qué:** «completitud» no es control de calidad, y el autor lo mantiene. El rango se aplica después de convertir porque
  está expresado en ppb.

##### R6. Unidades: contraste con CAMS, rótulo y conversión a 25 °C y 1 atm

- **Anclado:** el contrato no fija unidades. La v1 las fija en código:
  - `_comun_modelo.py`: `UNIDADES = {"pm25": "µg/m³", "no2": "ppb"}`, sin convertir ninguna serie SINCA;
  - `_red_adicional.py`: `PPB_POR_UG_M3N_NO2 = 22.414 / 46.0055  # 0 °C y 1 atm: 0,4872 ppb por µg/m³N`, aplicado sólo a
    SNIFA El Peñón;
  - el contraste con CAMS que decidió las unidades SNIFA (`_red_adicional.py:17-23`): «Contrastando cada período contra el
    NO₂ de CAMS en la misma celda (escala común) […]. Quinel y SAPU **no se incluyen**: […] su escala queda indeterminada por
    un factor de dos.»
- **Nuevo:** «Para todas las series de gases, actuales, nuevas y SNIFA (decisión S):
  1. **Rótulo:** es la unidad de la ficha SINCA (`unidad_ficha`). La ficha da una unidad por parámetro, que vale para la serie
     horaria y para la diaria. En la actualización, la unidad de la serie horaria coincide en todas con la de la diaria usada en
     el contraste.
  2. **Contraste** (decisión V): el contraste de niveles contra CAMS de la v1, extendido a una referencia de red, tal como
     fija `contraste_unidades_cams.md` (programa `contraste_unidades_cams.py`; resultado `contraste_unidades_cams.csv`).
     - Las series en ppb son la referencia y quedan en ppb.
     - Si el contraste indica una unidad, la serie toma esa unidad.
     - **Si el contraste es indeterminado, decide el rótulo** (decisión I): la serie rotulada µg/m³N se convierte según su
       ficha. La serie sin unidad queda fuera.
  3. **Conversión** de µg/m³N a ppb en condiciones normales de **25 °C y 1 atm** (decisión U′): ppb = c × V_m / M, donde:
     - V_m = 24,4654 L/mol;
     - M: NO2 46,0055; O3 47,998; SO2 64,064 g/mol.
     - 1 ppb de NO2 = 1,880 µg/m³N.
     - SNIFA El Peñón pasa de 0,4872 a 0,5318 ppb por µg/m³N.
     - Charrúa y Progreso siguen en ppb, como decidió el contraste de la v1.
     - CO, fuera de este contrato, pasa a ppm con la misma fórmula (decisión U).
  4. **PM2,5:** en µg/m³, sin conversión ni contraste. Una serie sin unidad toma µg/m³ (decisión S).

  **Resultado sobre las estaciones del contrato** (`contraste_unidades_cams.csv`, primera corrida):
  - **NO2:** el contraste no decide ninguna serie. La razón obs/CAMS de la referencia varía en un factor de ≈ 3 entre
    estaciones (dispersión del logaritmo 1,11), más que el factor de 1,88 que hay que distinguir.
    - **Entran convertidas por su rótulo:** las 9 actuales rotuladas µg/m³N (514, 515, 802, 826, 827, 830, 841, 854 y 870) y
      12 de las 13 nuevas. La 518 sale por R8.
    - **Quedan fuera:** las 11 sin unidad, que son 6 actuales (513, 529, 532, 609, 878 y 901) y 5 nuevas (601, 603, 816, A02 y
      A03).
  - **O3** (para su rama): de las 17 rotuladas µg/m³N:
    - el contraste confirma 4, que se convierten (826, 221, 329 y 614);
    - contradice 7, que **entran en ppb, sin convertir** (547, 841, 870, 215, 519, 533 y 534);
    - deja 6 indeterminadas: 830, 207, 216, 876 y E01 se convierten por su rótulo, y la 518 sale por R8.

    De las 7 sin unidad, entran 609 y 517 en ppb, porque el contraste lo mostró, y quedan fuera 827, 837, 901, A02 y A03.
  - **Segunda corrida:** el contraste se vuelve a correr, con el mismo programa y la misma regla, al cerrar el panel. Así
    entran la actualización de las 107 y las coordenadas de R8. Su salida y su huella van al registro de la red (R22). Si una
    serie cambia de decisión, rige la segunda corrida y el cambio se registra.»
- **Por qué:**
  - Son las decisiones U, U′, S, V e I, con una sola regla para todas.
  - **Fuente de los 25 °C:**
    - el decreto de la norma primaria de NO2 (D.S. 114/2002, FAOLEX `chi50322`) define la condición normal a 1 atm y 25 °C;
    - un informe de la SMA da 41,60 µg/m³N = 22,13 ppbv, que cuadra con 25 °C (41,60 / 1,880 = 22,13);
    - lo verificó en la web el coordinador, el 2026-10-25.
  - **El contraste es necesario:** en O3, 7 de los 11 rótulos µg/m³N que se pudieron decidir son falsos, y en CO todos lo
    son. En la v1, 2 de los 3 de SNIFA.
  - **Riesgo declarado** (la decisión I no es la recomendada, que dejaba fuera las indeterminadas hasta un documento oficial):
    - algunas de las 21 series de NO2 y de las 5 de O3 que se convierten por su rótulo podrían venir ya en ppb y quedar
      **≈ 1,9 veces más bajas** de lo real;
    - la tasa de rótulos falsos que se vio en O3 (7 de 11) sugiere que el riesgo no es pequeño;
    - se declara, sin comprobarlo después con métricas del modelo («mejorar lo anterior sin comprobar»);
    - el indicio de vecina del contraste (por ejemplo, 209 frente a 252: 1,08) queda como información.
  - **Hallazgos sobre la v1**, que se informan sin corregirla:
    - la v1 usó como ppb, sin convertir, 9 series de NO2 rotuladas µg/m³N, que la v2 convierte por su rótulo;
    - la v1 convirtió El Peñón a 0 °C y no a 25 °C (9,2 % de diferencia).

##### R7. Reloj: UTC−4 fijo y hora civil convertida

- **Anclado:**
  - `protocolos.LPO.anio_local`: «UTC−4 fijo (columna anio del panel v1)»;
  - el panel v1: `"reloj_sinca": "UTC-4 fijo; etiqueta=fin"`;
  - `config/sinca/politica_temporal.json` (`41018e4c…`):
    - `"hora_ambigua": "conservar_hora_local_asumir_ocurrencia_estandar_y_registrar_utc_alternativo"`;
    - `"hora_inexistente": "conservar_hora_local_desplazar_adelante_y_marcar_qc"`;
    - `"colision_misma_utc_en_panel": "media_con_conteo_y_bandera_manteniendo_el_lector_crudo_sin_agregar"`;
    - `"zonas_iana_por_region": {"RXI": "America/Coyhaique", "RXII": "America/Punta_Arenas"}`, con America/Santiago por
      omisión.
- **Nuevo:** «La regla general es UTC−4 fijo, con la etiqueta en el fin del intervalo: el inicio en UTC es la etiqueta + 4 h
  − 1 h.
  - **Verificación:** antes de armar el panel se pasa a todas las series horarias (actuales y nuevas; PM2,5, NO2 y O3) la
    verificación estructural del reloj, **corregida**, con la hora inexistente y la repetida en su hora real. Se prueba antes
    con series sintéticas en los dos relojes. El veredicto es por estación × contaminante × año local de la etiqueta.
  - **Si el veredicto es «hora civil»** (decisión P9), el estación-año no se excluye: se convierte a UTC con la zona IANA de
    su región.
    1. La etiqueta (fin del intervalo) se lleva a UTC y luego se resta 1 h.
    2. **Hora repetida:** se toma la ocurrencia **estándar** y se registra la alternativa.
    3. **Hora inexistente:** se desplaza hacia adelante y se marca.
    4. **Dos etiquetas en la misma hora UTC:** se promedian, con conteo y bandera.
  - **Los demás veredictos** («reloj fijo», «parcial», «sin evidencia» y «sin transiciones») siguen la regla general.»
- **Por qué:** es la decisión P9, aplicada a todas las series.
  - Antes hay que corregir la verificación: `verificar_reloj_sinca.transiciones` «ubica las horas especiales una hora tarde»
    (tablero) y no puede dar «hora civil».
  - **Límite declarado:** un estación-año en hora civil sin días de cambio de hora en sus datos no se detecta y queda en UTC−4.
    El error es de 1 h en verano.
  - **Aviso de código:** `utc_candidato_1` del derivado es la ocurrencia **más temprana**, no la estándar. La conversión no
    debe usarlo tal cual.

##### R8. Coordenadas y celda

- **Anclado:** `protocolos.BLQ-75.asignacion`: «cada estación va al bloque que contiene sus coordenadas proyectadas». La v1
  toma las coordenadas del maestro de `actualizar_geometria_sinca.py`, rearmadas desde el UTM y el huso de la ficha y
  validadas con la comuna, y corrige con documentos oficiales los casos defectuosos (560 y 548).
- **Nuevo:** «**Maestros que usa el modelo** (decisión C3):
  - **Estaciones actuales:** `DATOS/sinca/estaciones_georreferenciadas.csv` (`51ff693e…`), que no se toca.
  - **Estaciones nuevas:** `GEO/estaciones_georreferenciadas.csv` (`d5764ee2…`, 106 estaciones). Lo arma
    `scripts_pipeline/geometria_sinca_ampliacion.py` (`c1153b63…`), envoltorio del procedimiento sellado de
    `actualizar_geometria_sinca.py` (v1.2.0, `24355ab6…`), con las correcciones de `GEO/metadata/correcciones_coordenadas.json`
    (`d0a42ac0…`) y el registro `GEO/metadata/envoltorio_geometria.json`.
  - La latitud y longitud del mapa de la ficha sólo valen si un documento oficial citado las respalda.

  **Correcciones con documento oficial** (decisión C), guardadas con su huella en `GEO/metadata/fuentes_coordenadas_mma/`:
  - **312 Tierra Amarilla:** ficha SINCA id 224, marcador del mapa. El campo UTM publica Este y Norte invertidos.
  - **537 Chagres Meteorología:** ficha SINCA id 131, marcador del mapa. El campo UTM es inutilizable.
  - **E01 Consultorio Máfil:** ficha SINCA id 126, marcador del mapa, en UTM 18S. El campo UTM trae el huso y un dígito
    errados.
  - **207 Ferrocarriles (Mejillones):** ficha SINCA id 66, UTM tal como se publica, a 12 m del marcador. Evidencia adicional:
    el informe SINCA de calidad del aire de la II Región de 2004. Su tabla de redes trae una coordenada 110 km al norte, que no
    se usa.
  - **334 Chañaral:** coordenada directa de la ficha. Entra porque el polígono comunal inválido se valida en memoria (las
    16 comunas listadas en el envoltorio), **sin modificar `comunas.shp`** (`22422225…`).

  **Tolerancia costera** (decisión C2), regla declarada para todas las estaciones:
  - una coordenada oficial que cae fuera de los polígonos comunales, a ≤ 500 m de la costa generalizada de `comunas.shp`, se
    asigna a la comuna costera más cercana, con la marca `fuera_de_poligono_costero_<d>m_tolerancia_500m`;
  - más lejos, no se asigna;
  - hoy la aplica sólo la 207 (245 m, Mejillones).

  **Quedan fuera:**
  - la **518 «Rural 1»**: su UTM cae 61 km mar adentro, el marcador es 0,0 y el EIA de 2004 de Cemento Melón sólo la
    describe. Se queda fuera mientras no haya una coordenada oficial. Si aparece una antes del anexo de R22, entra con estas
    mismas reglas; después, no.
  - la 408 (sin series del contrato) y las fichas sin código (id 38 e id 44).

  La celda se asigna con `celda_de_lonlat` y los enlaces con `construir_enlaces`, sobre la grilla v1, que no cambia.»
- **Por qué:** misma calidad geográfica que las actuales, con fuentes citadas. El contraste de R6 se hizo con las
  coordenadas de las fichas; para 207 y E01 coinciden con las corregidas (12 m en la 207; el marcador oficial en la E01), y la
  segunda corrida usa el maestro corregido.

##### R9. Series duplicadas (por omisión, P8)

- **Anclado:** nada en el contrato. La v1 promedia sólo los duplicados dentro de una misma estación × hora
  (`series_sinca`: `groupby(["estacion","ts_utc"]).agg(obs=("obs","mean")…)`).
- **Nuevo:** «Dos códigos a ≤ 2 km (haversine) son la misma serie si tienen el mismo valor en ≥ 95 % de sus horas comunes,
  con ≥ 720 horas comunes. Se conserva una sola copia por hora, la del código con más horas, y se registra el par. Vale para
  todos los pares (actuales, nuevos y SNIFA) y se calcula antes de cualquier ajuste.»
- **Por qué:** una misma medición contada dos veces duplica el peso del sitio. Hay estaciones nuevas a 1 km de una actual
  (D31 a 1,0 km de D35; 329 a 0,9 km de 310). El conglomerado LOSO-D ya las retira juntas; la copia, no.

##### R10. Estaciones de empresas (P4)

- **Anclado:** §8: «macrozona y estación;» (`metricas.desagregaciones.estacion: true`). El contrato no distingue
  propietarios. Hoy, 38 de las 109 fichas configuradas son de empresas.
- **Nuevo:** «Una estación entra igual sea pública o de una empresa. Se registran `propietario`, `operador`, `red` y
  `calificacion` de la ficha. El §8 suma una desagregación descriptiva (pública o de empresa), que no entra en el §9.»
- **Por qué:** es la decisión P4 y ya es la práctica con las 38 actuales.

##### R11. Panel con los insumos de hoy (P3); las extensiones entran sin comparación

- **Anclado:**
  - §0: «la v2 lee los paneles v1 (`paneles/panel_{pm25,no2}.parquet`) en sólo lectura. Los recálculos van a la raíz v2»;
  - §11: «**Descargas nuevas:** NASADEM o Copernicus GLO-30; extender GEOS-CF, TROPOMI NO2, MERRA-2 y BLH; GOES ABI.» y
    «Cada una entrará como enmienda, con su propia variante etiquetada y la misma comparación.»;
  - `fuera_del_contrato.estado`: «pendiente de autorización del autor; cada una entra como enmienda, con su propia variante
    etiquetada y la misma comparación».
- **Nuevo:** «La v2 ya no lee los paneles v1. Lee `panel_{pm25,no2}_red2.parquet` en la raíz v2, armados con una sola
  elaboración para todas las filas.
  - **Código:** el de la v1 (`construir_panel`, `satelites_estaciones` y `obs_vecinas_para`), con sus huellas registradas.
  - **Insumos de hoy:** los archivos de cada producto cuyo registro en su manifiesto sea anterior al **2026-10-25 03:00
    UTC** (fin del 2026-10-24 en Chile continental), con su lista y sus huellas en el json del panel.
  - **Entran así, por decisión del autor y sin variante etiquetada ni comparación**, las extensiones del §11 que estén en esa
    lista:
    - TROPOMI NO2 2018-04-30 a 2018-12-31 y 2025-01-01 a 2026-10 (en disco hasta el 2026-10-13);
    - MERRA-2 de 2026-06, y lo que esté registrado antes del corte;
    - capa límite de ERA5 2026-07 a 2026-09;
    - GEOS-CF fuera de 2019-2024, si está registrado antes del corte (hoy sólo hay 2019-2024 en disco).
  - **No entran por este bloque:** NASADEM o GLO-30 como predictor (`elev_m` sigue saliendo de las estáticas v1) y GOES ABI.
    Lo que se registre después del corte sigue la regla del §11 y la de la Enmienda 2 para extensiones.
  - **Predictores:** siguen siendo las listas cerradas de 70 (PM2,5) y 69 (NO2) del §3; no se vuelven a elegir por
    cobertura.
  - **Vecindario:** sigue el §2, con toda la red.
  - **Meteorología:** las columnas `el_*` las reemplaza la enmienda de la DMC (M6), no este bloque.
  - **Los paneles v1 quedan intactos.»**
- **Por qué:**
  - Es la decisión P3, declarada como dice el autor: «mejorar lo anterior sin comprobar».
  - **El corte por omisión** (al fin del 2026-10-24) cierra un camino: sin él, el contenido del panel dependería del día en
    que se arme.
  - **La lista de extensiones es cerrada:** la que dio el autor. Por eso se nombra lo que no entra.

##### R12. Excepción a la regla del encabezado; sin comparación con la v1 (P2)

- **Anclado:**
  - el encabezado: «Cambiarlo después de ver resultados exige una enmienda fechada al final, con su motivo, y que la
    especificación original se siga informando.»;
  - Enmienda 1, punto 2: «**Comparaciones v2 frente a v1:** se hacen con la misma corrección, para separar el aporte del
    motor del de la corrección.»;
  - `retransformacion.comparaciones_v2_frente_a_v1`: «con la misma corrección (smearing frente a smearing, ½·σ² frente a
    ½·σ²), para separar el aporte del motor del de la corrección».
- **Nuevo:** «Por decisión del autor («no quiero contrastar todo con lo anterior… mejorar lo anterior sin comprobar»):
  - la especificación original (red de 107 estaciones de PM2,5 y 57 de NO2, insumos de la v1, sin las extensiones de R11)
    **no se estima ni se informa**;
  - no se informa nada sobre el subconjunto de las estaciones originales;
  - las extensiones de R11 no se comparan con su ausencia;
  - el punto 2 de la Enmienda 1 queda sin efecto en lo que dice de comparar la v2 con la v1: no se hacen esas comparaciones;
  - la v1 congelada queda sólo como referencia histórica.

  Si en algún documento se menciona la v1 junto a la v2, se rotula «cambian a la vez la red de monitores, los insumos, las
  unidades, el motor, la pérdida, los predictores y la meteorología».»
- **Por qué:** el cambio llega después del piloto, así que la regla del encabezado pediría seguir informando la
  especificación original. El autor pide la excepción, como hizo con la A3 del protocolo meteorológico. Se declara y se
  acepta el costo: la mejora no queda comprobada contra lo anterior.

##### R13. Pliegues: las mismas reglas, recalculadas

- **Anclado:**
  - §1: «Se fijan en un manifiesto de pliegues (`pliegues_v2.json`, con grupos, k y semillas) antes de ajustar ningún motor.»;
  - la fila LOSO-D del §1: «conglomerado de estaciones a ≤ 2 km (componentes conexas; retira juntos 309/310/330/333,
    B03/B04, 503/548 y las celdas compartidas)»;
  - Enmienda 1, punto 8: «**Manifiesto:** se vuelve a fijar `pliegues_v2.json` con su bitácora, informando por bloque la
    distancia mínima de prueba a entrenamiento.»
- **Nuevo:** «Se vuelven a aplicar, sin cambiar ningún parámetro, las reglas del §1, de la Enmienda 1 (puntos 1.1, 8 y 13) y
  del Complemento (punto 5) a la red de R3:
  - LOSO-D: componentes conexas a ≤ 2 km que unen celdas compartidas;
  - LBO-10 y amortiguador de BLQ-75 de 10 km, también en las particiones internas;
  - rejilla de 75 km en EPSG:32719 con origen (0, 0);
  - LRO por región SINCA, con `RXVI` → `RVIII`;
  - LPO por cuatrienios;
  - k = posición lexicográfica de la etiqueta, y semilla [42, k];
  - haversine con R = 6.371 km.

  El universo de los radios es el de las estaciones con celda de la lista de R2. El manifiesto del 2026-10-13 (archivo
  `f001d48c…`, huella de pliegues `3e9f5acd…`) queda congelado como `pliegues_v2_reemplazado_<marca>.json`, con un evento
  «reemplazo» en la bitácora. Los conglomerados de ejemplo y los conteos de la Enmienda 1 describen la red original.»
- **Por qué:** sólo cambian los datos, no las reglas.
  - Cuenta aproximada con las coordenadas de R8:
    - NO2 (71 estaciones): LOSO-D pasa de 48 a ≈ 57 y BLQ-75 de 18 a ≈ 22;
    - PM2,5: ≈ +1 en cada uno;
    - LRO no cambia (15 y 12).
  - Como k es lexicográfico, cambian semillas de pliegues viejos. Es mecánico.

##### R14. Pesos fijos y desagrupamiento: las mismas reglas

- **Anclado:**
  - Enmienda 1, punto 4: «**Peso por estación:** la población de su celda (`pob_dens`) se fija como la **mediana de sus
    años**…» y «**Sensibilidad:** un peso de desagrupamiento, la población de la comuna dividida por las estaciones de la red
    en ella.»;
  - `…ponderado_por_poblacion.poblacion.valor.peso_fijo_por_estacion`: «mediana de pob_dens sobre los años con filas de la
    estación en el panel»;
  - `…desagrupamiento.poblacion_comunal.valor`: «… dividida por el número de estaciones del panel del contaminante, de las
    dos redes, en esa comuna».
- **Nuevo:** «Los pesos fijos, el desagrupamiento, el G efectivo y el número de Kish se recalculan con esas mismas reglas
  sobre el panel de R11. «La red» y «el panel del contaminante» son los de este bloque.»
- **Por qué:** la regla no cambia. Sí cambian los valores: un peso viejo cambia si cambian los años con filas de su estación,
  y el desagrupamiento de una comuna cambia si llegan estaciones nuevas a ella.

##### R15. E2: cobertura y evaluabilidad recalculadas

- **Anclado:**
  - Enmienda 1, punto 7: «**Evaluabilidad:** E2 es evaluable en un protocolo si conserva ≥ 50 % del peso de E1 y ≥ 5 grupos
    con filas E2.» y «45 de las 107 estaciones de PM2,5 y 33 de las 54 estaciones SINCA de NO2 no tienen ninguna fila
    validada.»;
  - `calidad_blanco.evaluacion.cobertura_conocida`.
- **Nuevo:** «La evaluabilidad de E2 se calcula sobre el panel de R11, con los mismos umbrales, antes de cualquier ajuste, y
  se escribe en el registro de la red. `cobertura_conocida` informa la red original (la cifra de arriba) y la ampliada.»
- **Por qué:** las estaciones nuevas, casi todas de empresas en NO2, pueden mover el peso validado. Calcularlo antes cierra la
  puerta a declararlo según convenga.

##### R16. Bloque más influyente: por criterio, no por nombre

- **Anclado:**
  - Enmienda 1, punto 5: «**Influencia:** la superioridad debe sobrevivir a quitar el bloque más influyente (la RM en LRO y
    E004N083 en BLQ-75)»;
  - `inferencia_diferencias.influencia.lectura`: «Los bloques los nombra la enmienda (son los de mayor peso poblacional en los
    dos contaminantes).»
- **Nuevo:** «El bloque más influyente es, por protocolo, el de mayor peso poblacional (R14), sumado en los dos contaminantes,
  en la red de este bloque. Se calcula y se escribe en el manifiesto antes de cualquier ajuste. Si no es RM o E004N083, rige el
  calculado y se dice.»
- **Por qué:** se mantiene el criterio que la Enmienda 1 usó para nombrarlos.

##### R17. Regímenes de predictores (descriptivos)

- **Anclado:** Enmienda 1, punto 10: «2019-2024, con GEOS-CF y con TROPOMI en ~70 % de las filas;», «2025, sin GEOS-CF ni
  TROPOMI y con ACAG climatológico;» y «2026, además sin CAMS y con MERRA-2 y BLH incompletos.», con «**Alcance:** los
  regímenes no alteran el §9».
- **Nuevo:** «Con las extensiones de R11, los tramos de años se vuelven a definir con la misma regla: tramos de años seguidos
  con la misma combinación de familias disponibles. Una familia está disponible en un año si alguna de sus columnas es finita
  en al menos la mitad de los días del año en el panel. El código los calcula y los escribe en el manifiesto antes de
  cualquier ajuste. La sensibilidad fila a fila (Complemento 4.4) no cambia.»
- **Por qué:** con TROPOMI en 2018 y 2025-2026, los rótulos de hoy dejan de ser ciertos. Son descriptivos, así que basta una
  regla fija.

##### R18. Presupuesto (por omisión, P6)

- **Anclado:**
  - §10: «si el total supera unas 120 horas de máquina, se reduce en este orden:»;
  - `presupuesto.orden_de_recortes_en_el_codigo`: «los cuatro recortes, incluido el 4, se implementan en el código: el plan
    los aplica en este orden hasta quedar bajo el umbral, sin elección a mano (Complemento, punto 8)»;
  - Enmienda 1, punto 12: «**Revisión del plan:** antes de la corrida se vuelve a medir el piloto con la máquina libre
    (`--remedir-contaminadas 0.5`) y se rehace el plan con el nuevo orden.»
- **Nuevo:** «El piloto de tiempos se vuelve a medir sobre el panel de R11. Si después de los cuatro recortes el plan sigue
  sobre unas 120 h, se corre igual y se registra en la bitácora. No hay quinto recorte.»
- **Por qué:** el contrato no decía qué pasa después del cuarto recorte, y un tiempo no es un resultado. Estimación gruesa,
  sin el piloto:
  - ≈ +7 % por los ≈ 9 pliegues nuevos de LOSO-D y LBO-10 y los ≈ 4 de BLQ-75 en NO2, más el período algo más largo;
  - **unas 125 h (entre 123 y 127 h) frente a 115,65 h**, sobre el umbral de 120 h. Rigen los cuatro recortes y, después,
    esta regla.

##### R19. Factibilidad: no se revisa

- **Anclado:** Complemento, punto 3: «**Irrevisable:** esta regla y su medición no se revisan después de ver resultados.»
- **Nuevo:** «La regla y su medición no cambian. El costo del vecindario con más monitores y de los insumos nuevos está en el
  armado de la matriz y es común a todos los candidatos.»
- **Por qué:** se cumple el texto sellado.

##### R20. O3 (P5)

- **Anclado:**
  - §3: «los 70 predictores de PM2,5 y los 69 de NO2»: O3 no está en este contrato;
  - la rama `o3_next` (`config_real_pendiente.json`): `"quality": "validado"`.
- **Nuevo:** «O3 sigue fuera de este contrato. Su rama usa:
  - la lista de R2;
  - las reglas R3 a R10 (sin completitud, la misma calidad, unidades con contraste y rótulo, reloj y coordenadas);
  - el esquema de calidad de la v2: entrena con todo y evalúa en E1 y E2, en vez de «sólo validado».

  Se ancla en su propio diseño antes de su primer ajuste. La variante meteorológica de O3 la fija el Anexo B del protocolo
  meteorológico.»
- **Por qué:** es la decisión P5. Una sola red y una sola calidad para los tres contaminantes.

##### R21. Producto meteorológico (P7)

- **Anclado:**
  - protocolo meteorológico v2.1, §5.3: «**Distribución de los monitores π^mon_b:** lo mismo con los monitores de PM2,5 y NO2
    de `pliegues_v2.json`, un peso por monitor-año con datos.»;
  - §7.1: «`lateral_monitores(pol, decision, operador) -> (tabla, metadatos)`: claves (`estacion`, `ts_utc` en UTC) del panel
    v1, leído en sólo lectura».
- **Nuevo** (lectura registrada en el protocolo meteorológico antes de M3-4): «π^mon usa el `pliegues_v2.json` de este bloque,
  con su huella en el registro de la red. Las tablas laterales de M6 se arman sobre el panel de R11.»
- **Por qué:** es la decisión P7. Así hay una sola red en toda la cadena, y M6 compara I y D sobre los datos de la corrida
  larga.

##### R22. Sellado y orden

- **Anclado:** Enmienda 1, punto 14: «**Sellado:** el contrato, la configuración y el código se confirman en git antes de
  cualquier ajuste comparativo.»
- **Nuevo:** «Orden:
  1. **Anclaje de este texto en APH** (decisión Anc): commit local y sello OpenTimestamps, sin envío al remoto.
  2. **Traducción a AP:** a `DISENO_AMBIENTAL_V2.md` y a `config_v2.json`, con el código de §3 y sus pruebas, confirmada en
     git en AP y en su espejo APH antes de armar datos y antes de cualquier ajuste comparativo.
  3. **Armado:** derivados, verificación del reloj, panel, duplicados, calidad, pliegues y **segunda corrida del contraste de
     unidades** (R6).
  4. **Anexo «Registro de la red v2»**, confirmado en git y sellado **antes de M3-4**. Lleva las huellas de R2, del panel, de
     los pliegues, de la calidad, del reloj, de la segunda corrida del contraste y de los duplicados.
  5. Nueva medición del piloto de tiempos.
  6. M6.
  7. Corrida larga.

  Nada de esto ajusta un modelo comparativo antes del paso 4.»
- **Por qué:** lo exigen la Enmienda 1, la compuerta M6 y la decisión Anc. Un anexo con huellas evita que la red cambie entre
  el anclaje y la corrida.

---

#### 3. Qué tiene que cambiar el código (traducción a AP, paso 2 de R22)

Todo en AP, con espejo en APH si es un componente compartido. La v1 no se toca.

| Archivo | Función o cambio |
|---|---|
| `scripts_pipeline/geometria_sinca_ampliacion.py` (ya existe, `c1153b63…`) | envoltorio de `actualizar_geometria_sinca.py` sellado, con las correcciones oficiales, la tolerancia costera y la validación de polígonos en memoria (R8); se confirma en git con sus pruebas |
| `scripts_pipeline/preparar_sinca_modelado.py` | correr con `--fuente AMP` (y `AMP/actualizacion_configuradas`) y `--salida derived/modelado/SINCA/v1_red2`; conversión civil con la ocurrencia **estándar** y desplazamiento hacia adelante (R7). La conversión de unidades va en `unidades_v2.py` |
| `scripts_modelo_1km/v2/reloj_sinca_v2.py` (nuevo, copia corregida de `verificar_reloj_sinca.py`) | `transiciones` corregida; `veredicto` por estación × contaminante × año; varias raíces de derivado y maestros; pruebas sintéticas en los dos relojes |
| `scripts_modelo_1km/v2/unidades_v2.py` (nuevo) | `unidad_de_serie(manifiestos, contraste)`: lee el rótulo y la decisión del contraste (con su huella); si es indeterminada, usa el rótulo (I); sin unidad, fuera (salvo PM2,5). `a_ppb(valor, gas)` a 25 °C y 1 atm (24,4654 L/mol); tabla de masas molares; lista de las series que quedan fuera; aplica también a SNIFA (El Peñón × 0,5318) |
| `scripts_modelo_1km/v2/contraste_unidades_v2.py` (nuevo) | el programa `contraste_unidades_cams.py`, versionado, con pruebas sintéticas (una serie en ppb, una en µg/m³N y una indeterminada); lee el maestro corregido; produce la segunda corrida con huella |
| `scripts_modelo_1km/v2/duplicados_v2.py` (nuevo) | `pares_duplicados(series, radio_km=2, coincidencia=0.95, minimo=720)` y `quitar_copias` |
| `scripts_modelo_1km/v2/panel_red2_v2.py` (nuevo) | réplica de `observaciones_panel`, `satelites_estaciones`, `construir_panel` y `matriz_vecindario` (qmd 1492-1640), importando `produccion`, `_features` y `_comun_modelo` con huellas fijadas; `inventario_insumos(corte_utc)` (R11), con la lista y las huellas en el json; período R4; escribe en `LOCAL/modelado_1km_v2/paneles/` |
| `scripts_modelo_1km/v2/_rutas_v2.py` | `panel(pol)` → `panel_{pol}_red2.parquet`; `catalogo_sinca` → los dos maestros de R8; raíces del derivado; la guarda sigue prohibiendo la raíz v1, `DATOS/sinca` y `derived/…/SINCA/v1` |
| `scripts_modelo_1km/v2/pliegues_v2.py` | `leer_estaciones_sinca` y `estaciones_con_celda` con los dos maestros y los enlaces de la red 2; prueba de códigos únicos; `construir_manifiesto` con los insumos nuevos; bloque más influyente calculado (R16) |
| `scripts_modelo_1km/v2/calidad_v2.py` | `raiz_derivados` y `derivado_sinca` con varias raíces; réplica con las nuevas |
| `scripts_modelo_1km/v2/metricas_v2.py` | regímenes calculados (R17); desagregación por propietario (R10); `cobertura_conocida` antes y después |
| `scripts_modelo_1km/v2/validar_vecindario_v2.py` y `correr_v2.py` | leen el panel nuevo; la identidad del panel sale del manifiesto nuevo; quitar las comparaciones v2 frente a v1 (R12) |
| `scripts_modelo_1km/v2/piloto_v2.py` | sin cambio de reglas; se vuelve a medir sobre el panel nuevo; sin quinto recorte (R18) |
| `scripts_modelo_1km/v2/DISENO_AMBIENTAL_V2.md` | este bloque como «Enmienda 2, bloque de la red ampliada», con la huella de este texto |
| `scripts_modelo_1km/v2/config_v2.json` | nodo `red_de_monitores` (R2 a R10, con huellas); `relacion_v1.insumos_v1_solo_lectura` → paneles red 2; `contrato.enmiendas[…]`; `retransformacion.comparaciones_v2_frente_a_v1` → sin efecto; `inferencia_diferencias.influencia.bloque_mas_influyente` → regla; `fuera_del_contrato` → lo que entra y lo que queda; `metricas…regimen_de_predictores.criterio` → regla |
| `scripts_modelo_1km/v2/tests/` | pruebas nuevas: una estación con 1 hora entra; las huellas de la v1 no cambian; período; conversión de unidades (incluida SNIFA); reloj civil; duplicados; corte de insumos; códigos únicos; maestros de R8. `test_congelados_v2.py` debe seguir pasando |
| `scripts_modelo_1km/meteo_combinada/ambiental.py` (por escribir en M1) | `lateral_monitores` lee el panel red 2 (R21) |
| `scripts_modelo_1km/o3_next/` | universo, unidades, reloj y esquema E1/E2 (R20), en su diseño propio |
| `config/componentes_compartidos.json` (AP y APH) | regenerar si cambia código de `scripts_pipeline/` o `config/sinca/` |

---

#### 4. Pendientes de ejecución

No queda ninguna decisión pendiente. Faltan tres cosas de ejecución, todas con su regla ya fijada:

1. **Segunda corrida del contraste de unidades** al cerrar el panel (R6 y R22, paso 3), con la actualización de las 107 ya
   terminada y el maestro corregido de R8.
2. **Coordenada oficial de la 518**, si aparece antes del anexo de R22 (R8). Si no aparece, la 518 queda fuera.
3. **Traducción a AP con el código** (R22, paso 2).

**Para informar, fuera del contrato:**
- **CO:** los 9 rótulos µg/m³N y los 5 ppb están en la escala de ppm o mg/m³N (probablemente mg/m³N).
- **SO2:** el contraste no decide ninguna serie.

---

#### 5. Huellas de los archivos que cita el bloque

Calculadas con sha256 el 2026-10-25. Este archivo no figura en la tabla: su huella va en el anclaje.

| Archivo | sha256 |
|---|---|
| `APH/auditoria/20261023/meteo_combinada/m0/PROTOCOLO_METEO_COMBINADA_v2.1.md` | `0d0972d8c8ebf09bb39bf45154496e72b524cdb8d57f9ce029aa53a16708edaf` |
| `APH/auditoria/20261024/sinca_al_modelo/BORRADOR_ENMIENDA_red_ampliada.md` | `1b7002758341dde824e1cb36526d24aec52999ab02c16392d75fe7e002d6dd02` |
| `APH/auditoria/20261024/sinca_al_modelo/contraste_unidades_cams.csv` | `ca0805ae0e7af3c2ff8f241600ad46327ebfd68c27c470361a210b301bc9f855` |
| `APH/auditoria/20261024/sinca_al_modelo/contraste_unidades_cams.md` | `d8f69d5d8e8c543276df9088351f87fc4907c5b78c148f4684d97ad0a05600d8` |
| `APH/auditoria/20261024/sinca_al_modelo/contraste_unidades_cams.py` | `82637d7b6b7dab2228eb34caa4efa28ef413a2728fdb0af6af0c0771429108e9` |
| `APH/auditoria/20261024/sinca_al_modelo/decisiones_autor_20261024.md` | `01744a98101ff149fc3e65a32046c27b2fd810bd2b23d8c72594e00b4355b7af` |
| `AP/config/sinca/politica_temporal.json` | `41018e4c066d9e30b5ba0b1ff92d47eeb47bab1984b5b8c45a778939359ac61c` |
| `AP/scripts_modelo_1km/_comun_modelo.py` | `a83c0384266554e16ab397749544759ae1cf161f138361eefa7d1ad3e29aa6f4` |
| `AP/scripts_modelo_1km/_red_adicional.py` | `f7ab850b4784afa648e7e579294dee8f9e1a34c400b20a766a10e590a395941c` |
| `AP/scripts_modelo_1km/o3_next/config_real_pendiente.json` | `90187de7dbbe654cdd9d66cb7a15b556b5318253acfd3188c20fb65f5aedff81` |
| `AP/scripts_modelo_1km/v2/DISENO_AMBIENTAL_V2.md` | `5d879a05179a3e980d01e25e12bb4f3492d4fe6b4142f7be6daa2509df4c39b0` |
| `AP/scripts_modelo_1km/v2/config_v2.json` | `232c75b3376b6fd7c4f73c885c812e170abff7c1a8817d1ac64cc76c68b0534c` |
| `AP/scripts_modelo_1km/verificar_reloj_sinca.py` | `a93a1eab928d032b1d83c0e32702f2f2b73fa6d9a0b228b47ef9abb3f632d446` |
| `AP/scripts_pipeline/actualizar_geometria_sinca.py` | `24355ab65692f82ddca550d04e9540f8b8b2cad02e4c02564960ed2a451bbde5` |
| `AP/scripts_pipeline/descargar_sinca_ampliacion.py` | `d77247232ed4857941d8a4616193d805ed612af20a816949b44b6b1c9cb63c62` |
| `AP/scripts_pipeline/geometria_sinca_ampliacion.py` | `c1153b6396e965fa3f52697121fb2edb7f39241517e881daec94a3570532c76b` |
| `AP/scripts_pipeline/preparar_sinca_modelado.py` | `95f1ecd3c9071f3877e858e0b822b4e525b00b49ab4aced8f0490a71d0a65401` |
| `DATOS/comunas.shp` | `22422225a10a2df817f386f6d0a45652d14d76fad28c9b85c17da4c1edaaa755` |
| `DATOS/sinca/estaciones_georreferenciadas.csv` | `51ff693e6ac9a75eb92afc4da4995950f2b39fa4e241fd0e1f57a183cc381995` |
| `DATOS/sinca/estaciones_georreferenciadas.geojson` | `85a8eb08bfb9315fb5c3324a9912641878943366e93137a7e0c0e316121ae12d` |
| `DATOS/sinca/manifiesto_descarga.csv` | `79d4fd770e5ad0aa7e5c88487598c20106989fb6be184b457f8502ecee289f7f` |
| `DATOS/snifa_adicional/processed/observaciones_horarias.parquet` | `2aa177d9f0e3f8626d03c9e8381357a58eb81e43192b7aa802c5f03b4e055a55` |
| `AMP/SHA256SUMS.txt` | `db36e2084f75d262cea445665d7a403c53a0058cd18c87b7f5f1f48bffd3d7fa` |
| `AMP/actualizacion_configuradas/SHA256SUMS.txt` | `785283793ee2aa79cb7e2ff3355af6121c542d5e12c2275e203320a07d621fbc` |
| `AMP/actualizacion_configuradas/errores_descarga.csv` | `ff92e103dd4ea795360e117bb36fb57af7c1d8fcaf93c3eb72a4b9f77b454d7e` |
| `AMP/actualizacion_configuradas/estaciones_georreferenciadas.csv` | `51ff693e6ac9a75eb92afc4da4995950f2b39fa4e241fd0e1f57a183cc381995` |
| `AMP/actualizacion_configuradas/estado_validacion_series.csv` | `b398f69d2a701b7212a763d41f1ae422052e3e5ae64b168c5274a3d54fb902fb` |
| `AMP/actualizacion_configuradas/manifiesto_descarga.csv` | `0fc77ae1b89cb9db5308ac38703dc7f2b8606902327705257e1b1b15551a8388` |
| `AMP/catalogo/20261024T232023Z/SHA256SUMS.txt` | `14c9b5cba28d25daa62a9ec226350b5216dbc98efbe0479384d4ea002227e106` |
| `AMP/catalogo/20261024T232023Z/catalogo.json` | `1c523f6f66f70fb7c5e40bc13686309ec58137d5c34f722f3addb87ae44eaede` |
| `AMP/errores_descarga.csv` | `ff92e103dd4ea795360e117bb36fb57af7c1d8fcaf93c3eb72a4b9f77b454d7e` |
| `AMP/estaciones_fichas.csv` | `5d22889a185a41af067b36a1b066e1b988eb06d14b23e89b67566dda132a5f5b` |
| `AMP/estaciones_georreferenciadas.csv` | `c5eb0806cf9346c2313e06a1ff98eb337dab8abaeaf707044d86083a452e4e6f` |
| `AMP/estado_validacion_series.csv` | `b6ee431fe8be8960bce8620fd8e9017387b1dce4c121bcd2be9c739578eb0f03` |
| `AMP/manifiesto_descarga.csv` | `19865e3b03f0abc2bd6d3673a5ddd63978c465625c1aec1355bc473824f85480` |
| `AMP/manifiesto_descarga_otras_series.csv` | `dee257046f0871e2f7d249c30f592a268bc6d49de3c8823f7ffaca1131edb9cc` |
| `AMP/no_disponibles.csv` | `27bf9db6c871bc3bf5b13b207f6572478fc37e43e6f2dad44eafe5279033c6a8` |
| `GEO/SHA256SUMS.txt` | `945640f3cb5f0e9f244b6dda2ae7c4845f991225f7fb87a3b291bb1967bd6827` |
| `GEO/estaciones_georreferenciadas.csv` | `d5764ee2f8f6afa3a92cca609744080749254fbfb041d58783b99f31b4169308` |
| `GEO/estaciones_georreferenciadas.geojson` | `eaeaf965ffa2f5a8d0a734128473ecc5646916ef2dd958c7c5b37b94364df29b` |
| `GEO/metadata/correcciones_coordenadas.json` | `d0a42ac02aaff81db6af17d263f2d195aa75289536834689beda0c3c30075e97` |
| `GEO/metadata/envoltorio_geometria.json` | `bd47ebcac10b6ac15e3c3153936f3b2a50fb63d382bef1f31deca4772b78cb0e` |
| `GEO/metadata/estaciones_entrada_geometria.csv` | `a490e13750ecc5fce2b73401b26b3feefb66a4e6c89dde48d6e36c6d2f9fbd35` |
| `GEO/metadata/estaciones_excluidas_geometria.csv` | `a5fd7dc3cec8fa087913c888ad0f0cbc2a0070b50a8eae66889bc26db34eb505` |
| `GEO/metadata/fuentes_coordenadas_mma/207_evidencia_SINCA_informe_calidad_aire_II_region_2004.pdf` | `eff36bde434ee5bc1e518bc6396d98ad75cb5f133116e5fb0fd8870c8d83ff25` |
| `GEO/metadata/fuentes_coordenadas_mma/207_ficha_sinca_id66.html.gz` | `a2f1b17b2f6c3b1fb120c209658d7640964fba42e11ec5f36a2b24c41f59c3e7` |
| `GEO/metadata/fuentes_coordenadas_mma/312_ficha_sinca_id224.html.gz` | `2a0c0d86bf8fee854ea7a571401dc05b3efcd221e100291d61885f41a4fc56bc` |
| `GEO/metadata/fuentes_coordenadas_mma/537_ficha_sinca_id131.html.gz` | `2f139b566bdba5d0c6023c04f10aca7880c04d7f966d52ae39f9ccbc7b625f07` |
| `GEO/metadata/fuentes_coordenadas_mma/E01_ficha_sinca_id126.html.gz` | `c9a80adae985764e40eae4c8a96e273347e39f5334c60234e6b5f6f3066bc7a5` |
| `GEO/metadata/geometria_sinca_manifest.json` | `13f0991196ee9563510bfbe8aa4dbabebf31623fb91da726645e34979d17e34d` |
| `LOCAL/modelado_1km/grilla_1km/celdas.parquet` | `42b4b19613c7de343c856473af64e2c0a6353351f1884c8dba145361292108c3` |
| `LOCAL/modelado_1km/grilla_1km/estaciones_enlaces.parquet` | `372a6415ad5e88b1a2a820db0149baab04cd13f87e2cdd67e01e4b3ef99060d4` |
| `LOCAL/modelado_1km/grilla_1km/estaciones_enlaces_adicional.parquet` | `4f4edef9611cb34e4588e8a1a210f2f345d56851b2d6e3eb20aa6cfb37d2b688` |
| `LOCAL/modelado_1km/paneles/panel_no2.json` | `ea7c058e21d42cf263f5782b95d49152f04cbdbe49d9c354be8af8ebb5d857e4` |
| `LOCAL/modelado_1km/paneles/panel_no2.parquet` | `513394a296a5bc64ce850e1f7b5b726d86001e738c66db1413ecd889214118a3` |
| `LOCAL/modelado_1km/paneles/panel_pm25.json` | `2a6cda8e42a6938d0e41d015a4c0e13e439955e55d6265dc7e13673ba7ebc3a5` |
| `LOCAL/modelado_1km/paneles/panel_pm25.parquet` | `955ed14469dce75e2c6da6452fbd5749ff3f391345a910758b5550330a9f56cb` |
| `LOCAL/modelado_1km_v2/pliegues_v2.json` | `f001d48ca14a14a7f11c748f7ea1d349977727468cd8ed0d7bbb0f5092895053` |
| `LOCAL/modelado_1km_v2/pliegues_v2_reemplazado_20261013T054105Z.json` | `5e965c22cfc573c7da2719f7e0a7f51667c7229adeba8f5483b067a9bb6e18fa` |
