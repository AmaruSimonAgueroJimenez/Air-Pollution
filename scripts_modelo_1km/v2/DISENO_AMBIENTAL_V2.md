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

(ninguna)
