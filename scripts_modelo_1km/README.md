# Modelo 1 km × hora de PM2.5 y NO2 (contrato v1)

Documentado el 18 de septiembre de 2026 (actualizado el 20). **El modelo
vive en `docs/modelo_1km_horario.qmd`** (documento Quarto ejecutable: panel,
motor LightGBM, validación LOSO/LRO, modelo final y superficies);
`scripts_modelo_1km/` es la librería de ingesta que ese documento importa
(lectores nativos, grilla, covariables estáticas, verificación del reloj
SINCA, escritura NetCDF). **El disco externo queda para los datos crudos**:
todo lo que genera el modelo (grilla, estáticas, verificación de reloj,
paneles, modelos, predicciones de validación y superficies) va al disco
interno, `~/Asesorias_Data_local/AirPollution/modelado_1km/` (reubicable con
`AIR_POLLUTION_MODELO_1KM_ROOT`; las superficies además con
`AIR_POLLUTION_SUPERFICIES_ROOT`), fuera del repositorio sincronizado; del
externo sólo se lee. Métricas y figuras en `output_files/modelo_1km/`. Este documento describe el contrato y las
decisiones; **no certifica que exista una corrida completa**: el estado se
lee en los manifiestos JSON de cada etapa.

## Qué produce

Una superficie horaria de concentración en superficie, PM2.5 (µg/m³) y NO2
(ppb), sobre las 838.430 celdas de 0,01° (~1 km) que tocan Chile, un NetCDF
por día con las 24 horas UTC:

```
superficies/<pol>/year=AAAA/month=MM/<pol>_1km_AAAAMMDD.nc   (+ .json con hashes)
  dims: hora (24), celda (838430)
  ts_utc  int64  inicio del bin horario UTC
  celda   int64  pixel_id ACAG (fila global × 5101 + columna) o 900000000+k (Rapa Nui)
  <pol>   int16  empaquetado: PM2.5 × 10 (0,1 µg/m³), NO2 × 100 (0,01 ppb); −32768 = sin dato
```

Es una **estimación de modelo**, no una observación. La textura de 1 km viene
de ACAG (0,01° mensual), MAIAC (1 km por pasada), TROPOMI (3,5–5,5 km por
pasada) y las covariables estáticas; la variación horaria viene de ERA5-Land,
ERA5 BLH, MERRA-2, GEOS-CF, CAMS y de las observaciones SINCA concurrentes.
Entre pasadas satelitales y de noche el valor de cada celda es enteramente
modelado.

## Cómo se presentan los resultados

El informe separa los dos regímenes en **dos secciones paralelas y
autocontenidas**, con las mismas subsecciones, las mismas tablas y las mismas
figuras, generadas por las mismas funciones (`evaluar(pol, base, motor)` y las
`fig_*(pol, base, motor)`):

1. **Sin validación cruzada** (`#sec-sin-validacion`): cada motor ajustado con
   todas las estaciones y evaluado sobre las mismas filas. Es el desempeño
   aparente; no es la habilidad del producto.
2. **Con validación cruzada** (`#sec-resultados`): LOSO por celda, LRO por
   región y LPO por cuatrienio. Es la cifra que aplica a una celda sin monitor.
3. **Optimismo** (`#sec-optimismo`): la diferencia entre ambas, que es lo que
   cada motor debe a haber visto las estaciones.

Cada sección trae, para el motor del producto, quince figuras por
contaminante, y para cada uno de los otros nueve motores el mismo juego de
seis (dispersión, serie mensual por macrozona, lectura espacial, desempeño por
estación, ciclo diurno y matriz de confusión), en pestañas. Las figuras por
motor se generan a `DPI_POR_MOTOR` para que el HTML siga siendo compartible.
Las únicas subsecciones que no se duplican son la referencia contra productos
crudos y el protocolo del producto, que no comparan motores. La única cifra
que cruza regímenes está declarada donde aparece: los pesos del ensamble se
aprenden con predicciones fuera de pliegue.

Cierra un **anexo regional** (`#sec-anexo-rm`, región elegible con
`MODELO_1KM_REGION_ANEXO`, por defecto `RM`) con las mismas tablas y figuras
calculadas sólo sobre las estaciones de esa región, en los dos regímenes, más
una tabla estación por estación y la comparación de motores con la región
completa fuera del entrenamiento (LRO). El modelo no cambia: sólo cambia el
subconjunto de pares sobre el que se calculan las métricas. Toda la
maquinaria de evaluación está parametrizada por `(contaminante, régimen,
motor, región)`; los archivos de cada ámbito llevan su propio prefijo y sus
figuras un sufijo propio, de modo que un ámbito nunca pisa las del otro.

El gráfico de importancia de predictores muestra los 40 primeros con su
**nombre legible** (diccionario `NOMBRE_VARIABLE`, el mismo que documenta
`tbl-predictores`), el porcentaje de ganancia en cada barra, el código
original en gris para trazabilidad y el color por grupo de predictores; el
título dice cuánta ganancia queda repartida entre los que no se dibujan.

## Decisiones acordadas

| Decisión | Valor | Motivo |
| --- | --- | --- |
| Dominio | Todo Chile continental e insular, 838.430 celdas | pedido; producto completo, requiere disco |
| Período | 2000-01-01 → 2026-09-13 (ambos contaminantes) | pedido (19-sep-2026): toda la temporalidad SINCA; GEOS-CF y TROPOMI sólo existen para 2019–2024 y CAMS desde 2003, fuera de esos años entran como faltantes |
| Grilla | 0,01° alineada con ACAG V6GL03 (centros k·0,01 + 0,005) | ACAG entra 1:1; MAIAC por píxel más cercano (≤ 1,5 km) |
| Reloj SINCA | UTC−4 fijo, etiqueta al fin del intervalo | norma (D.S. 61/2008, R.E. 1449/2023) y prueba estructural (abajo) |
| Unidad de análisis | celda × bin horario UTC; la estación se representa por su celda | los mismos predictores en entrenamiento y predicción |
| Modelo | LightGBM sobre log1p(obs) con corrección de retransformación por macrozona y franja (½·Var del residuo log), con la varianza estimada fuera de pliegue | mismo motor que `scripts_superficie/afg_lib.py`; la varianza in-sample deja la media estimada sistemáticamente baja |
| Validación | LOSO (deja un sitio fuera: las estaciones que comparten celda salen juntas); opcionales LRO (una región fuera, con el vecindario recalculado sin la región) y LPO (un cuatrienio fuera) | fuera de estación es la vara para un producto de 1 km; LRO y LPO miden extrapolación espacial y temporal |
| Control de calidad | se excluyen rachas de ≥ 24 registros idénticos consecutivos (`MODELO_1KM_QC_RACHA`) | sensores pegados: 0,5 % de PM2.5 y 0,6 % de NO2 |
| Sin interpolar | ninguna fuente se remuestrea ni se rellena en la ingesta | los huecos quedan NaN y LightGBM los trata como faltantes |
| Enlace celda–píxel | al píxel **válido** más cercano; si el píxel propio no trae datos (mar en ERA5-Land, ~16 % del recorte) se toma el píxel de tierra más cercano hasta 16 km y la celda queda marcada `era5land_enlace = vecino_valido` | con el vecino geométrico a secas el 8,2 % de las celdas (la costa, 17 de 109 estaciones) quedaba sin meteorología de superficie; ahora es el 0,9 % |
| Dónde se guarda lo que genera el modelo | disco **interno**, `~/Asesorias_Data_local/AirPollution/modelado_1km/` (`AIR_POLLUTION_MODELO_1KM_ROOT` lo reubica) | pedido (19-sep-2026): el disco externo queda para los datos crudos; el modelo sólo lee de él (`data/` y el derivado SINCA del pipeline) |
| Motores | LightGBM es el motor del producto; GWR (regresión geográficamente ponderada, ancho adaptativo k = 12) y regression-kriging (OLS global + kriging ordinario del residuo medio por estación) se evalúan como contraste con los mismos protocolos, pares y métricas | pedido (19-sep-2026): probar también los otros motores de `others_files/20260902_informe_modelos_estimacion.qmd` (el informe anterior); se resuelven con estadísticos suficientes por estación × cuatrienio, exactos y en segundos |
| Motores del proyecto anterior | Random Forest, red neuronal (MLP), proceso gaussiano, modelo lineal mixto, LightGBM de alertas (cuantil 0,80) y ensamble por apilado (ridge sobre las predicciones fuera de pliegue de LightGBM + RF + MLP), más una línea base de interpolación de vecinas; con los hiperparámetros originales salvo las desviaciones declaradas en el informe, bajo LOSO/LRO/LPO y las mismas métricas | pedido (19-sep-2026): implementar los modelos usados antes en `Neurodegen-Epidemiology-Chile/others_scripts/pm25_exposure_modeling.qmd`. Desviaciones documentadas: el modelo mixto lleva las concentraciones en log(1 + x) y suma el efecto aleatorio de la hora al predecir; el MLP acota sus entradas al rango del entrenamiento (sin eso extrapola en lat/lon al dejar una región fuera); el GP usa un subespacio compacto y 3.000 filas por pliegue (el original, 2.000); el apilado se arma a mano sobre estadísticos suficientes y sus bases son los motores principales del informe, no las versiones livianas que el original reajustaba dentro del `StackingRegressor`. No se portan el respaldo HistGradientBoosting (redundante), el kriging de residuos (cubierto por RK) ni el modo anclado (descartado allá). `MODELO_1KM_MOTORES_ML` elige cuáles correr |

## Reloj SINCA: evidencia estructural

`verificar_reloj_sinca.py` examina las etiquetas horarias originales en las
fechas de cambio de hora civil (zoneinfo, zonas regionales de
`config/sinca/politica_temporal.json`). Un exportador en hora civil no puede
emitir la hora inexistente del adelanto de septiembre ni evitar repetir u
omitir una etiqueta en el atraso de abril; un exportador de reloj fijo emite
24 etiquetas distintas ambos días. Corrida sobre el derivado SINCA completo
(19 de septiembre de 2026; 107 estaciones: 107 PM2.5, 54 NO2, 50 O3;
2018–2026): 1.899 estación-año-contaminante, 3.723 fechas de cambio de hora,
**todas `reloj_fijo`** (la hora civil inexistente está presente y ninguna
etiqueta se repite); 33 fechas sin etiquetas por falta de datos y 21
estación-año `sin_transiciones` porque Magallanes (desde 2017) y Aysén
(desde 2025) no cambian la hora. La prueba secundaria con el máximo de O3
(corrimiento verano−invierno −0,9 h) mezcla reloj y estacionalidad
fotoquímica y no discrimina por sí sola. La magnitud del offset (−4) y la
etiqueta al fin del intervalo siguen siendo la convención normativa, no una
medición. Resultados en `verificacion_reloj_sinca/{resumen.json,
veredictos.csv, detalle_transiciones.csv}`.

Advertencia sobre versiones del derivado SINCA: una carpeta
`estacion=*/contaminante=*` puede contener varias `version=<sha>/` (la serie
completa y corridas incrementales de pocos días). `version_sinca()` elige la
de ventana más amplia según `manifest.json` (nunca por orden del hash);
`series_sinca` y la verificación del reloj la usan.

## Predictores

Por celda y hora (píxel nativo enlazado; sin interpolación):

- ERA5-Land 0,1°: t2m, d2m, sp, u10, v10, precipitación horaria (diferencia
  de acumulados, 01 UTC toma el acumulado), y derivadas RH, viento, dirección.
- ERA5 BLH 0,25° e inverso; MERRA-2 0,5°×0,625°: t2m, rh2m, viento, ps,
  pblh, AOD, PM2.5; GEOS-CF 0,25°: NO2, PM2.5, O3, CO (ppb, µg/m³); CAMS
  0,75° cada 3 h (bin de 3 h anterior): NO2, PM2.5, O3, CO.
- Reanálisis con etiqueta HH:30 (MERRA-2, GEOS-CF, CAMS) se alinean al bin
  HH; ERA5 (HH:00) se toma al inicio del bin.

Por celda y fecha local (UTC−4):

- MAIAC MCD19A2 1 km: AOD 550 nm de Terra, Aqua y del día, conteo, medias
  móviles de 3 y 7 días. QA `estricta`: máscara de nube clara y QA AOD 0.
- TROPOMI NO2: columna troposférica (10¹⁵ moléc/cm²) del píxel a ≤ 5 km con
  qa ≥ 0,75, su precisión y hora, medias móviles de 7 y 15 días. Lee los
  recortes compactos y los legados.
- ACAG PM2.5 mensual 0,01°; meses no publicados (2025+) usan la climatología
  2018–2024 del mes con bandera `acag_clim`.

Por celda (estáticas y anuales, `covariables_estaticas.py`): fracciones ESA
CCI 300 m (urbano, cultivo, bosque, matorral/pastizal, desnudo, agua,
nieve/hielo) por año (2023+ usa 2022), población dasimétrica (proyecciones
censales comunales repartidas por fracción urbana + piso rural), elevación y
pendiente (NASADEM 30 m si hay teselas, si no la media comunal y luego la
celda vecina), distancia a la costa (fuera del modelo de NO2 por diseño:
`MODELO_1KM_EXCLUIR` vale `no2:dist_costa_km` por omisión, en
`_features.EXCLUSIONES_POR_DEFECTO`), densidad vial OSM (total y principal;
NaN si falta el shapefile), distancia a la estación más cercana. Calendario: hora local UTC−4 (seno y
coseno), día del año, día de semana, mes, año. Vecindario: `obs_vec` y
`peso_vec`, interpolación gaussiana (h = 150 km) de las observaciones SINCA
concurrentes de las demás estaciones; en el panel se excluye la propia
estación (válido bajo LOSO), en la grilla se usan todas.

## Etapas y cómo correr

Entorno: el `conda` `afg` de `scripts_superficie/` (Python 3.11 con
`lightgbm`, `scipy`, `netCDF4`, `pyarrow`, `matplotlib`, `jupyter`) más las
dependencias geoespaciales; `scripts_modelo_1km/requirements.txt` las lista.
LightGBM se usa por su API nativa (`lgb.train`), sin scikit-learn. Quarto
ejecuta el documento con el kernel `python3` de ese entorno.

```sh
conda activate afg
pip install -r scripts_modelo_1km/requirements.txt
python -B scripts_modelo_1km/tests/test_modelo_1km.py       # 14 pruebas herméticas de la librería
export QUARTO_PYTHON="$(python -c 'import sys; print(sys.executable)')"   # Quarto debe usar este mismo entorno
zsh scripts_modelo_1km/lanzar_corrida_completa.sh            # histórico 2000–2026 con LBO, LRO y LPO + HTML (horas; reanudable)
# o, paso a paso (Quarto se lanza desde docs/: desde la raíz, embed-resources + --output falla al empaquetar).
# Siempre con los cuatro protocolos: sin ellos los motores de contraste se rehacen sólo con LOSO.
export MODELO_1KM_LBO=1 MODELO_1KM_LRO=1 MODELO_1KM_LPO=1
python -B scripts_modelo_1km/correr_qmd.py
cd docs
quarto render modelo_1km_horario.qmd                                                  # arma el HTML con lo cacheado
cd .. && python -B others_scripts/aligerar_html.py docs/modelo_1km_horario.html     # figuras en 256 colores: bajo 50 MB
zsh scripts_modelo_1km/lanzar_produccion_serie.sh                                     # la serie completa de superficies, aparte
```

La prueba corta (`MODELO_1KM_SMOKE=1 quarto render modelo_1km_horario.qmd --output
modelo_1km_horario_smoke.html`) no pisa lo definitivo, pero el render real que la siga debe partir con un
kernel nuevo (`--execute-daemon-restart`): Quarto puede reutilizar el kernel de la corrida anterior.

`correr_qmd.py` ejecuta los mismos chunks del documento, en orden, en un
proceso de Python corriente, para que las etapas largas no dependan de un
kernel de Jupyter; cada pliegue de la validación se guarda al terminar
(`modelos/<pol>/pliegues/<protocolo>/pliegue_NNN.npz`), así que una corrida
interrumpida se reanuda donde quedó. En este Mac el entorno es el
micromamba `afg` (`~/micromamba/envs/afg`, Python 3.11, pandas 2.3,
LightGBM 4.7).

El documento construye (si faltan) la grilla, las estáticas y la
verificación del reloj llamando a la librería, y luego, dentro del propio
documento, el panel por contaminante, la validación LOSO (y LRO con
`MODELO_1KM_LRO=1`), el modelo final, los días de demostración de las
superficies y, con `MODELO_1KM_PRODUCCION=1`, la producción completa. Cada
artefacto pesado se cachea (si existe, el chunk se salta el cómputo; borrarlo
lo regenera) y los días ya publicados con el mismo modelo se omiten, así que
la producción se puede reanudar. Variables: `MODELO_1KM_DESDE`/`HASTA`
(período), `MODELO_1KM_ETIQUETA` (sufijo de panel, modelo y superficies;
`smoke` en la prueba corta, que no pisa lo definitivo),
`MODELO_1KM_DIAS_DEMO`, `MODELO_1KM_N_TREES`, `MODELO_1KM_MAX_TRAIN_ROWS`,
`MODELO_1KM_SIN_VIAS=1`, `MODELO_1KM_LRO=1`, `MODELO_1KM_LPO=1`,
`MODELO_1KM_QC_RACHA` (0 desactiva el filtro de rachas) y
`MODELO_1KM_PROCESOS` (procesos de la ingesta). El avance se escribe en
`output_files/modelo_1km/modelo_1km.log` (`tail -f`).

## Serie completa y métricas de exposición (24 de septiembre de 2026)

El contrato de producción (`Modelo`, `ContextoPrediccion`, `predecir_rango`) y
las redes observadas salieron del `.qmd` a `produccion.py`; el documento lo
importa, así que hay **una sola** implementación y el informe y el lanzador no
pueden divergir (lo comprueba una prueba hermética). Con eso, la serie se
produce sin renderizar el informe:

```sh
zsh scripts_modelo_1km/lanzar_produccion_serie.sh                       # rm → biobio → nacional, 6 procesos
python -B scripts_modelo_1km/producir_serie.py --ambito rm --solo-estado
python -B scripts_modelo_1km/exposicion.py --ambito rm --solo-estado
python -B scripts_modelo_1km/exposicion.py --ambito rm --ventanas 2     # métricas por celda, año y bienio
```

El lanzador recorre los ámbitos en orden —**primero la Región Metropolitana,
después Biobío y Ñuble, al final todo Chile**— y agrega la exposición de cada
uno al terminarlo: hay mapas de la RM en unas 3 h sin esperar las ~34 h de la
serie nacional. `MODELO_1KM_AMBITOS` cambia la lista o el orden. Cada ámbito
escribe en su propia carpeta (`superficies`, `superficies_rm`,
`superficies_biobio`) porque `ruta_superficie_dia` no distingue el número de
celdas: con una sola raíz, una corrida regional pisaría la nacional.

**Se puede apagar el equipo en cualquier momento.** Cada día se escribe en
`.part` y sólo al cerrarse se renombra y se publica su manifiesto; al
relanzar, los días ya publicados se saltan en milisegundos. El agregador de
exposición guarda un año a la vez, también de forma atómica. Por omisión la
producción hace **primero los años pares**, que son los de los mapas cada dos
años, y después el resto.

**Dos optimizaciones, las dos verificadas contra el camino anterior:**

| | antes | después | verificación |
|---|---|---|---|
| vecindario observado | 39 s/día | 0,3 s/día | salida **idéntica bit a bit** |
| predicción | 130 s/día | 8 s/día | dif. máx. 1,4 × 10⁻¹⁴ en log1p; 0 filas > 10⁻⁹ |
| **día nacional** | **208 s** | **23 s** | |

La primera es `VecindarioFijo` (`_features.py`): en producción los puntos de
consulta son siempre las mismas celdas, así que la matriz de pesos
gaussianos se calcula una vez y no 24 veces al día; `Σⱼ Wᵢⱼ·Mⱼ·Vⱼ` es
exactamente el producto matriz-vector `W @ (M*V)`. La segunda es `lleaves`,
que compila con LLVM **el mismo** `modelo_final.txt` —los mismos 800
árboles— a código máquina. Cada proceso lo compara contra el booster de
LightGBM sobre 20.000 filas reales antes de usarlo y vuelve solo a LightGBM
si difiere más de 10⁻⁹ (`MODELO_1KM_PREDICTOR=lightgbm` lo desactiva).
`lleaves` 1.3 exige `llvmlite < 0.45`.

Costo medido por ámbito (seis procesos, 19.506 días-contaminante cada uno):
**RM ~3 h** (2,4 s por día-contaminante, 15.094 celdas), **Biobío y Ñuble ~4 h**
(38.164 celdas) y **nacional ~34 h** (23 s, 838.430 celdas), con ~293 GB de
NetCDF horario nacional, ~28 GB los dos regionales y ~21 GB de métricas de
exposición, todo en el disco **interno** (`AIR_POLLUTION_SUPERFICIES_ROOT` lo
reubica). El disco externo sólo se lee.

**La matriz de predictores va en float32**, no en float64: el panel de
calibración guarda todas sus columnas en float32, así que el modelo aprendió
los cortes en esa precisión. Con `lat` y `lon` en float64 el 0,88 % de las
casillas cruza un umbral distinto (0,60 % sobrevive a la cuantización del
NetCDF, hasta 12,8 µg/m³ en celdas sueltas). El predictor compilado sube a
float64 después, lo que es exacto.

**La corrección de retransformación se estima por macrozona**
(`duan_oof_macrozona`), no con un solo factor por franja, en los dos
contaminantes: en PM2.5 desde el 24 de septiembre y en NO2 desde el 2 de
octubre de 2026. La mitad de la varianza del residuo log cambia mucho entre
macrozonas, así que un factor único acierta en el promedio nacional y
sobrecorrige donde el modelo ajusta bien; la tabla de retransformación del
informe (`tbl-retransformacion` en `docs/modelo_1km_horario.qmd`) calcula el
sesgo LOSO que deja cada forma, por macrozona y en la RM. Se fija por
contaminante en `produccion.RETRANSFORMACION_POR_DEFECTO`;
`MODELO_1KM_RETRANSFORMACION_PM25` o `_NO2` la cambian. Es un término
**aditivo posterior al ajuste**: `modelo_final`
conserva el booster y sólo recalcula la corrección, porque re-ajustar
cambiaría su sha256 y daría por caducas todas las superficies. El guarda de
reanudación compara la retransformación, así que cambiarla re-produce los
días afectados; `aplicar_retransformacion.py --solo-smear` la actualiza sin
tocar las superficies, y sin `--solo-smear` las reescala en vez de
re-predecirlas (exacto sobre valores sin cuantizar, pero partiendo del
NetCDF ya cuantizado a 0,1 µg/m3 deja el 23 % de las casillas a un paso de
distancia: sirve para la serie nacional, donde re-predecir cuesta 34 h, no
para una región).

**Los años que toca un proceso no son contiguos** (primero los pares), y
`SatelitesDiarios.dia()` aborta si le piden un día anterior al último: por eso
`producir_serie.py` llama a `ContextoPrediccion.reiniciar_ventana_satelital()`
antes de calentar cada año. Sin eso los seis procesos mueren al primer salto
hacia atrás y NO₂ no se produce nunca.

Las métricas de exposición (`exposicion.py`) replican celda a celda las once
del proyecto hermano de neuroepidemiología —`media`, `p95` (percentil 95 de
las **medias diarias**, no de las horarias) y `horas/auc/episodios` sobre
U ∈ {15, 25, 50} µg/m³— más el máximo horario. Tres cosas son decisión de
este proyecto y no réplica: el bienio como unidad temporal, los umbrales de
NO₂ (13,3 · 26,6 · 63,8 ppb, la guía OMS 2021 de 24 h) y el ámbito «Biobío»,
que incluye Ñuble. Se corrige además un artefacto del original: allá una
racha que cruzaba el Año Nuevo contaba como dos episodios. Las tasas «por
año» se normalizan por **días efectivamente cubiertos** (`365,25 / n_dias` por
celda) y no por el número de años presentes: 2026 llega al 13 de septiembre y
dividirlo por «un año» lo subestimaría un 30 %.

## Costo (Mac Apple Silicon, 16 núcleos, 128 GB; medido el 19 de septiembre de 2026)

- Grilla y enlaces: ~1 min. Estáticas 2000–2026 con densidad vial OSM:
  ~1,5 min (sin NASADEM).
- Panel 2000–2026: PM2.5 9.740.634 filas (107 estaciones), NO2 5.557.032
  (54 estaciones). Ensamblaje **medido: 11 min para ambos**, con la ingesta
  repartida en 8 procesos (`MODELO_1KM_PROCESOS`): los predictores
  satelitales se calculan una sola vez para todas las celdas con estación
  (9.753 días, ~6 min) y los reanálisis por año (~1 min por contaminante).
- Validación: **medido ~45 s por pliegue** con hasta 1,5 millones de filas
  y 800 árboles. LOSO agrupa por celda (del orden de 100 pliegues en PM2.5
  y 50 en NO2), LRO son 15 pliegues (algo más lentos: recalculan el
  vecindario) y LPO 7. `MODELO_1KM_MAX_TRAIN_ROWS` y `MODELO_1KM_N_TREES`
  acotan el costo. La validación es reanudable por pliegue.
- Motores de contraste (medido el 20 de septiembre de 2026, 195 pliegues entre
  ambos contaminantes y los tres protocolos): alertas ~46 s por pliegue con
  hasta 1,5 millones de filas (2 h 35 min en total); Random Forest ~60 s por
  pliegue con 750.000 filas (3 h 14 min); red neuronal 16 min (12 pliegues en
  paralelo, 300.000 filas); proceso gaussiano 34 min (4 en paralelo, 3.000
  filas); modelo mixto 4 min; ensamble, segundos. GWR, regression-kriging y
  la interpolación de vecinas, 10 min. `MODELO_1KM_MOTORES_ML` elige cuáles
  correr; todos son reanudables por pliegue.
- Predicción: 838.430 celdas × 24 h × ~70 predictores por día. Medido con
  un motor reducido de 150 árboles: ~75 s por día nacional y contaminante,
  dominado por el ensamblaje de predictores, no por LightGBM. Con 800
  árboles estimar 2–5 minutos por día y contaminante (sin medir). Para
  2000–2026 (~9.750 días) eso son semanas de cómputo por contaminante: la
  producción debe repartirse por rangos (`MODELO_1KM_DESDE`/`HASTA`).
- Disco: medido 10,5–11 MB por NetCDF diario (int16 con zlib, dominio
  nacional). 2000–2026 son ~9.750 días → del orden de 105 GB por
  contaminante y 210 GB ambos. Las superficies se escriben en el disco
  **interno** (1,4 TiB libres al 19 de septiembre de 2026), no en el externo,
  así que el espacio alcanza; la limitante de la producción completa es el
  tiempo de cómputo del punto anterior, no el disco. Conviene producir por
  tramos y medir antes de comprometer el período completo.

## Validación y lectura de la incertidumbre

`modelos/<pol>/metricas.json` reporta LOSO (y LRO/LPO si se corrieron)
horario y diario (R², RMSE, MAE, sesgo), por macrozona y por hora local;
`oof.parquet` conserva las predicciones fuera de muestra, una columna por
protocolo. De ese archivo el documento deriva, sin reentrenar, las tablas
`output_files/modelo_1km/eval_*.csv`: batería completa (R², r, ρ, CCC, IOA,
RMSE, NRMSE, MAE, sesgo, NMB, NME, pendiente, FAC2) a nivel horario,
diario, mensual y anual; por macrozona, cuatrienio, régimen de predictores,
temporada y año; lectura espacial (medias por estación, por cuatrienio) y
temporal (anomalías dentro de estación); acuerdo por categorías de la media
diaria y excedencias; y la referencia contra GEOS-CF, CAMS, MERRA-2 y ACAG
sin calibrar sobre los mismos pares. El descriptivo de la red SINCA (mapas
por cuatrienio, series por macrozona) queda en `desc_*.csv` y
`serie_mensual_sinca_<pol>.csv`; `residuos_sd.parquet` da la desviación de
los residuos por macrozona × hora local × decil de predicción, que junto con
`dist_est_km` (estáticas) permite construir una incertidumbre por celda sin
escribir una capa horaria adicional. La validación fuera de estación mide
la generalización espacial sólo donde hay estaciones (urbanas en su
mayoría); en desierto, cordillera y zonas sin monitoreo el producto es una
extrapolación y debe rotularse así.

## Limitaciones conocidas

- Máximos nocturnos de invierno en el centro-sur (leña, capa límite estable):
  sin observación satelital; el valor depende de reanálisis, ciclo diurno
  aprendido y vecindario de estaciones.
- Densidad vial sólo si está el shapefile OSM; elevación comunal mientras NASADEM no esté descargado.
- ACAG 2025+ es climatología, no observación (bandera `acag_clim`).
- GOES-East ABI AOD (`descargar_goes_abi_aod.py`) no entra aún como
  predictor; cuando exista histórico se agrega como columna horaria diurna.
- Rapa Nui y Sala y Gómez no tienen ACAG ni GEOS-CF; se predicen con el
  resto de predictores.

## Estado (20 de septiembre de 2026, tercera corrida: diez motores, con y sin validación cruzada)

**Existe una corrida completa 2000-01-01 → 2026-09-13** de ambos
contaminantes sobre la grilla con el enlace al píxel válido, hecha en el Mac
con el entorno micromamba `afg` (Python 3.11, pandas 2.3.3, LightGBM 4.7)
mediante `lanzar_corrida_completa.sh`. La validación de LightGBM es del 19 de
septiembre (3 h 8 min de punta a punta: LOSO + LRO + LPO 2 h 34 min, GWR y
regression-kriging 11 min, evaluación 5 min, dos días de superficies ~9 min)
y se reutilizó sin recalcular, porque está atada al panel. El 20 de
septiembre se agregaron los motores del proyecto anterior y la línea base de
interpolación: 7 h más (6 h 44 min de motores, ver Costo; evaluación de los
diez motores 4 min; render 1 min con todo cacheado). Todo lo generado vive en el disco interno
(`~/Asesorias_Data_local/AirPollution/modelado_1km/`): `grilla_1km/`,
`paneles/`, `modelos/<pol>/{oof.parquet, oof_lineales.parquet, oof_ml.parquet, ajuste.parquet, metricas.json,
modelo_final.*, pliegues/, importancias_*.csv, residuos_sd.parquet}`,
`descriptivo_fuentes/` y `superficies/` (2024-06-05 y 2024-06-06). En el
repositorio: `output_files/modelo_1km/` (tablas `desc_*`, `eval_*`,
`eval_motores_*`, `metricas_<pol>.json`, 83 figuras) y
`docs/modelo_1km_horario.html` (36,4 MB en esa fecha; desde el 5 de octubre el HTML se versiona
después de pasar por `others_scripts/aligerar_html.py`). Las 22 pruebas de
`scripts_modelo_1km/tests/` pasan. La producción completa de superficies
(`MODELO_1KM_PRODUCCION=1`) **no se ha corrido**. Los artefactos de la
primera corrida (grilla con el vecino geométrico) quedaron con la etiqueta
`previoenlace` y se pueden borrar.

Resultados (validación fuera de sitio; LOSO agrupa por celda, 102 pliegues
en PM2.5 y 53 en NO2; LRO 15 y 11 regiones; LPO 7 cuatrienios):

| LightGBM | PM2.5 (µg/m³) | NO2 (ppb) |
| --- | --- | --- |
| Panel | 9.740.634 filas, 107 estaciones | 5.557.032 filas, 54 estaciones |
| LOSO horario: R² / RMSE / NMB | 0,40 / 30,3 / +2,6 % | 0,47 / 9,1 / +1,9 % |
| LOSO diario / mensual / anual: R² | 0,56 / 0,70 / 0,55 | 0,58 / 0,66 / 0,66 |
| Lectura espacial (medias por estación, todo el período): R² | 0,54 (103 est.) | 0,73 (52 est.) |
| Lectura temporal (anomalías diarias dentro de estación): R² | 0,55 | 0,45 |
| R² diario mediano por estación [p25; p75] | 0,45 [0,01; 0,66] | 0,07 [−0,21; 0,34] |
| LRO (región fuera) horario: R² / NMB | 0,31 / +0,8 % | 0,17 / −19,0 % |
| LPO (cuatrienio fuera) horario: R² | 0,50 | 0,59 |
| Detección de ≥ 50 µg/m³ / ≥ 13,3 ppb en 24 h: sensibilidad | 65 % | 71 % |
| R² diario por macrozona (NG / NCh / C / S / A) | 0,07 / 0,14 / 0,58 / 0,51 / 0,66 | −0,20 / −0,12 / 0,60 / 0,09 / 0,37 |

Comparación de motores (R² fuera de muestra, mismos pares y protocolos; LOSO
h/d/m/a = horario/diario/mensual/anual; «esp.» = lectura espacial, medias por
estación; «temp.» = anomalías diarias dentro de estación):

| PM2.5 | LOSO h / d / m / a | LRO d | LPO d | esp. | temp. | sens. ≥ 50 / ≥ 80 µg/m³ |
| --- | --- | --- | --- | --- | --- | --- |
| LightGBM | 0,40 / 0,56 / 0,70 / 0,55 | 0,45 | 0,67 | 0,53 | 0,55 | 65 % / 41 % |
| Ensamble (apilado) | 0,40 / 0,56 / 0,71 / 0,57 | 0,42 | 0,67 | 0,53 | 0,55 | 63 % / 34 % |
| Random Forest | 0,38 / 0,53 / 0,69 / 0,57 | 0,42 | 0,61 | 0,53 | 0,52 | 55 % / 20 % |
| Red neuronal (MLP) | 0,34 / 0,47 / 0,59 / 0,28 | 0,22 | 0,63 | 0,29 | 0,49 | 64 % / 41 % |
| Proceso gaussiano | 0,36 / 0,53 / 0,71 / 0,61 | 0,40 | 0,51 | 0,62 | 0,51 | 62 % / 36 % |
| Modelo mixto | 0,38 / 0,54 / 0,71 / 0,61 | 0,39 | 0,54 | 0,61 | 0,52 | 54 % / 25 % |
| Alertas (cuantil 0,80) | 0,33 / 0,44 / 0,50 / 0,05 | 0,29 | 0,52 | 0,00 | 0,50 | 83 % / 68 % |
| GWR | 0,37 / 0,53 / 0,72 / 0,64 | 0,43 | 0,56 | 0,65 | 0,51 | 62 % / 35 % |
| Regression-kriging | 0,36 / 0,52 / 0,70 / 0,56 | 0,40 | 0,56 | 0,55 | 0,51 | 59 % / 32 % |
| Interpolación de vecinas | 0,33 / 0,49 / 0,67 / 0,53 | 0,26 | 0,49 | 0,53 | 0,48 | 55 % / 34 % |

| NO2 | LOSO h / d / m / a | LRO d | LPO d | esp. | temp. | sens. ≥ 13,3 / ≥ 26,6 ppb |
| --- | --- | --- | --- | --- | --- | --- |
| LightGBM | 0,47 / 0,58 / 0,66 / 0,66 | 0,19 | 0,69 | 0,73 | 0,45 | 71 % / 69 % |
| Ensamble (apilado) | 0,49 / 0,60 / 0,69 / 0,69 | −0,18 | 0,70 | 0,71 | 0,47 | 73 % / 74 % |
| Random Forest | 0,51 / 0,63 / 0,73 / 0,75 | 0,19 | 0,71 | 0,78 | 0,48 | 70 % / 69 % |
| Red neuronal (MLP) | 0,36 / 0,43 / 0,47 / 0,38 | 0,35 | 0,67 | 0,43 | 0,38 | 71 % / 66 % |
| Proceso gaussiano | 0,42 / 0,53 / 0,61 / 0,58 | 0,17 | 0,64 | 0,61 | 0,42 | 74 % / 72 % |
| Modelo mixto | 0,32 / 0,39 / 0,45 / 0,39 | −0,90 | 0,42 | 0,49 | 0,34 | 65 % / 12 % |
| Alertas (cuantil 0,80) | 0,46 / 0,56 / 0,64 / 0,62 | 0,26 | 0,62 | 0,64 | 0,45 | 82 % / 75 % |
| GWR | 0,43 / 0,55 / 0,66 / 0,67 | −0,61 | 0,59 | 0,71 | 0,40 | 72 % / 58 % |
| Regression-kriging | 0,41 / 0,54 / 0,67 / 0,75 | −0,51 | 0,59 | 0,81 | 0,31 | 83 % / 58 % |
| Interpolación de vecinas | 0,29 / 0,35 / 0,42 / 0,37 | −0,76 | 0,35 | 0,48 | 0,29 | 61 % / 27 % |

Desempeño **sin validación cruzada** (20 de septiembre de 2026; `#sec-sin-validacion` del informe, antes de la
sección LOSO): cada motor ajustado con todas las estaciones y evaluado sobre las mismas filas, con la
retransformación estimada con los residuos del propio ajuste (nada viene de LOSO salvo los pesos del ensamble).
LightGBM, que aquí es el modelo final del producto: R² horario / diario / mensual / anual 0,55 / 0,75 / 0,93 / 0,93 (NMB horario −2,8 %) en PM2.5 y
0,69 / 0,83 / 0,94 / 0,98 (NMB horario −0,4 %) en NO2; coincide con el control in-sample de `modelo_final.json`. **No es la habilidad del producto**: en
una celda sin monitor aplica LOSO. El «optimismo» es la diferencia entre ambos:

| PM2.5 | diario: sin validación / LOSO / optimismo | espacial: sin validación / LOSO | temporal: sin validación / LOSO |
| --- | --- | --- | --- |
| LightGBM | 0,75 / 0,56 / +0,19 | 0,94 / 0,53 | 0,72 / 0,55 |
| Ensamble (apilado) | 0,70 / 0,56 / +0,15 | 0,89 / 0,53 | 0,67 / 0,55 |
| Random Forest | 0,65 / 0,53 / +0,12 | 0,81 / 0,53 | 0,62 / 0,52 |
| Red neuronal (MLP) | 0,66 / 0,47 / +0,19 | 0,91 / 0,29 | 0,62 / 0,49 |
| Proceso gaussiano | 0,53 / 0,53 / +0,00 | 0,64 / 0,62 | 0,51 / 0,51 |
| Modelo mixto | 0,54 / 0,54 / +0,01 | 0,63 / 0,61 | 0,52 / 0,52 |
| Alertas (cuantil 0,80) | 0,61 / 0,44 / +0,16 | 0,36 / 0,00 | 0,64 / 0,50 |
| GWR | 0,57 / 0,53 / +0,04 | 0,73 / 0,65 | 0,54 / 0,51 |
| Regression-kriging | 0,57 / 0,52 / +0,06 | 0,99 / 0,55 | 0,52 / 0,51 |
| Interpolación de vecinas | 0,49 / 0,49 / +0,00 | 0,53 / 0,53 | 0,48 / 0,48 |

| NO2 | diario: sin validación / LOSO / optimismo | espacial: sin validación / LOSO | temporal: sin validación / LOSO |
| --- | --- | --- | --- |
| LightGBM | 0,83 / 0,58 / +0,25 | 0,99 / 0,73 | 0,70 / 0,45 |
| Ensamble (apilado) | 0,75 / 0,60 / +0,16 | 0,96 / 0,71 | 0,60 / 0,47 |
| Random Forest | 0,76 / 0,63 / +0,14 | 0,98 / 0,78 | 0,60 / 0,48 |
| Red neuronal (MLP) | 0,74 / 0,43 / +0,31 | 0,99 / 0,43 | 0,56 / 0,38 |
| Proceso gaussiano | 0,66 / 0,53 / +0,13 | 0,90 / 0,61 | 0,47 / 0,42 |
| Modelo mixto | 0,42 / 0,39 / +0,04 | 0,54 / 0,49 | 0,35 / 0,34 |
| Alertas (cuantil 0,80) | 0,71 / 0,56 / +0,15 | 0,78 / 0,64 | 0,64 / 0,45 |
| GWR | 0,61 / 0,55 / +0,06 | 0,79 / 0,71 | 0,44 / 0,40 |
| Regression-kriging | 0,60 / 0,54 / +0,06 | 0,97 / 0,81 | 0,33 / 0,31 |
| Interpolación de vecinas | 0,35 / 0,35 / +0,00 | 0,48 / 0,48 | 0,29 / 0,29 |

- **El optimismo es sobre todo espacial**: con la estación vista, LightGBM ordena los lugares casi perfectamente
  (lectura espacial 0,94 y 0,99) y fuera de estación baja a 0,53 y 0,73; lo que aprende es el nivel de cada estación.
- **La red neuronal es la que más memoriza** (lectura espacial 0,91 → 0,29 en PM2.5 y 0,99 → 0,43 en NO2), seguida de
  LightGBM; regression-kriging reproduce las medias de las estaciones vistas por construcción (0,99 y 0,97).
- **El proceso gaussiano, el modelo mixto, GWR y la interpolación casi no tienen optimismo** (≤ 0,06 en el diario,
  salvo el GP en NO2): lo que rinden con la estación vista es lo que rinden sin ella.
- El optimismo no es estrictamente comparable entre motores: LightGBM final entrena con todas las filas (cada pliegue
  LOSO, con un tope de 1,5 millones) y los motores con tope se evalúan sobre filas que en su mayoría no entraron al
  ajuste, aunque sus estaciones sí; el informe lo declara y da la fracción por motor.
- Costo: 37 min (motores lineales con el protocolo «ajuste» 10 min; ajuste de los motores y predicción de todo el
  panel 20 min, el GP es el más lento; evaluación 6 min). Artefactos: `modelos/<pol>/ajuste.parquet`,
  `pred_ajuste_*` en `oof_lineales.parquet`, `eval_ajuste_*` en `output_files/modelo_1km/`.

Anexo de la **Región Metropolitana** (13 estaciones de PM2.5 y 11 de NO2; 19 % y 26 % del panel),
R² horario / diario / mensual / anual de LightGBM:

| Régimen | PM2.5 | NO2 |
| --- | --- | --- |
| Sin validación cruzada | 0,72 / 0,87 / 0,93 / 0,74 | 0,71 / 0,80 / 0,89 / 0,89 |
| LOSO (estación fuera, vecinas dentro) | 0,56 / 0,70 / 0,70 / −0,49 | 0,43 / 0,46 / 0,42 / −1,00 |
| LRO (región completa fuera) | 0,23 / 0,43 / 0,42 / −1,82 | −0,17 / −0,42 / −0,91 / −6,68 |

R² diario por motor en la RM (sin validación / LOSO / LRO):

| Motor | PM2.5 | NO2 |
| --- | --- | --- |
| LightGBM | 0,87 / 0,70 / 0,43 | 0,80 / 0,46 / −0,42 |
| Ensamble (apilado) | 0,86 / 0,74 / 0,43 | 0,69 / 0,51 / −0,60 |
| Random Forest | 0,86 / **0,78** / **0,56** | 0,72 / **0,56** / −0,44 |
| Red neuronal (MLP) | 0,81 / 0,35 / −1,42 | 0,70 / 0,22 / **0,23** |
| Proceso gaussiano | 0,68 / 0,68 / 0,28 | 0,61 / 0,41 / −0,28 |
| Modelo mixto | 0,75 / 0,74 / 0,25 | 0,25 / 0,20 / −0,65 |
| Alertas (cuantil 0,80) | 0,72 / 0,52 / −0,59 | 0,66 / 0,50 / −0,06 |
| GWR | 0,77 / 0,72 / 0,37 | 0,54 / 0,50 / −0,88 |
| Regression-kriging | 0,74 / 0,72 / 0,30 | 0,56 / 0,50 / −0,83 |
| Interpolación de vecinas | 0,69 / 0,69 / −0,02 | 0,26 / 0,26 / −0,88 |

- **La RM sale mejor que el país porque tiene red densa, no porque el modelo sea mejor ahí.** En PM2.5 el
  R² diario LOSO es 0,70 contra 0,56 nacional; en NO2, 0,46 contra 0,58 (peor que el país: la RM concentra
  las estaciones de tráfico, más difíciles).
- **Casi todo ese desempeño depende de tener monitores en la cuenca.** Al sacar la región completa (LRO) el
  PM2.5 diario cae de 0,70 a 0,43 y el NO2 se vuelve negativo (−0,42). Para una comuna metropolitana sin
  monitor la cifra aplicable es la de LRO, no la de LOSO.
- **En la RM el mejor motor es Random Forest en los dos contaminantes y en los tres regímenes** (PM2.5 LOSO
  0,78 y LRO 0,56; NO2 LOSO 0,56), por encima de LightGBM. Refuerza la decisión abierta sobre el motor del
  producto en NO2.
- **El nivel anual es negativo en LOSO en ambos contaminantes** (−0,49 y −1,00): con 13 y 11 estaciones de
  niveles parecidos, ordenar años por su media es más difícil que a escala nacional.
- La interpolación de vecinas alcanza 0,69 diario en PM2.5 LOSO, casi lo mismo que LightGBM: dentro de la
  cuenca de Santiago, con estaciones a pocos kilómetros, interpolar ya explica la mayor parte.

Lecturas que conviene tener presentes antes de usar el producto:

- **En PM2.5 LightGBM es el mejor o empata a nivel horario y diario en los
  tres protocolos; en NO2 no.** Fuera de estación (LOSO) Random Forest supera
  a LightGBM en NO2 en todos los niveles de agregación (diario 0,63 contra
  0,58), en la lectura espacial (0,78 contra 0,73) y en la mediana por
  estación (0,21 contra 0,07), con la mitad de filas de entrenamiento por
  pliegue; en LRO y LPO empatan. Las superficies las sigue produciendo
  LightGBM: cambiar de motor para NO2 es una decisión abierta, y antes habría
  que medir el costo de predecir 838.430 celdas por hora con 300 árboles sin
  límite de profundidad.
- **Los motores simples ganan lo espacial.** En la lectura espacial y el nivel
  anual de PM2.5, GWR (0,65 y 0,64), el proceso gaussiano y el modelo mixto
  (~0,61) superan a LightGBM (0,53 y 0,55); en NO2, regression-kriging (0,81).
  Si el uso es exposición de largo plazo, un motor espacial simple compite; si
  es exposición horaria o diaria, los de árboles.
- **Interpolar las estaciones vecinas ya da R² diario 0,49 en PM2.5** (LightGBM
  0,56): esa es la vara real que el modelo supera, y refleja cuánto descansa
  en `obs_vec`. En NO2 la interpolación sólo da 0,35.
- **El apilado aporta poco y puede dañar.** Iguala a LightGBM en PM2.5 y queda
  bajo Random Forest en NO2; en NO2 LRO (−0,18) rinde peor que sus tres bases
  (0,19; 0,19; 0,35). No es un error: los pesos se aprenden en las otras
  regiones y re-escalan las predicciones, lo que agranda el error cuando la
  región excluida tiene otro nivel (V Región: 15,5 ppb estimados contra 7,9
  observados).
- **El motor de alertas cumple su función**: detecta el 83 % de los días sobre
  50 µg/m³ y el 68 % de los días ≥ 80 (LightGBM 65 % y 41 %), al costo de
  anunciar 1,65 días por cada día real y un sesgo de +30 %. Random Forest y
  el modelo mixto aplanan los episodios (20 % y 25 % de los días ≥ 80).
- **Nadie extrapola NO2 a regiones sin monitores**: el mejor en LRO es la red
  neuronal (0,35 diario); LightGBM y Random Forest dan 0,19, y los motores
  lineales (GWR, RK, modelo mixto, interpolación) son negativos. El modelo
  mixto es en la práctica una regresión lineal en log: sus efectos aleatorios
  por hora son ~0,02 y ningún pliegue necesitó el respaldo.
- La prueba de dos años (2019–2020) **no anticipó bien** el período completo:
  allí la red neuronal daba 0,07 en NO2 LOSO (aquí 0,36) y el proceso
  gaussiano superaba a LightGBM (aquí no). No sacar conclusiones de motores
  con muestras cortas.
- El desempeño es **desigual entre macrozonas**: bueno en Centro, Sur y
  Austral para PM2.5 y sólo en Centro para NO2; en el Norte Grande y el Norte
  Chico el R² diario es ≤ 0,14 en PM2.5 y negativo en NO2.
- En NO2 la mitad de las estaciones tiene R² diario < 0,07 pese a un R²
  agrupado de 0,58: el modelo ordena bien los lugares pero sigue mal el
  tiempo en muchos sitios, y ningún motor extrapola a regiones sin monitores
  (LRO: LightGBM 0,19 con sesgo −19 %; GWR y RK negativos).
- Las 17 estaciones costeras que no tenían ERA5-Land (sitios industriales en
  su mayoría) son las difíciles: R² horario agrupado 0,17 en PM2.5 y 0,02 en
  NO2, contra 0,42 y 0,50 del resto. El enlace al píxel válido las mejoró poco
  (mediana de ΔR² por estación +0,002 en PM2.5 y +0,02 en NO2), porque
  MERRA-2 ya hacía de respaldo meteorológico; su beneficio está en las
  superficies, donde el 7 % de las celdas recupera meteorología de superficie.
- `obs_vec` (observaciones concurrentes de estaciones vecinas) es el
  predictor dominante de LightGBM: lejos de la red el producto descansa en
  predictores mucho más débiles, y las series agregadas por macrozona se ven
  bien casi por construcción.
- Los valores altos se comprimen (pendiente horaria 0,42 en PM2.5 y 0,58 en
  NO2); la sensibilidad para días de alerta (≥ 80 µg/m³) es 41 %.
- La retransformación con varianza fuera de pliegue deja el sesgo normalizado
  en +2,6 % y +1,9 % (con la varianza in-sample era −5,0 % y −9,7 %).

Pendiente: verificar contra las normas los cortes de categorías (D.S.
12/2011, D.S. 114/2002 y guías OMS 2021), que se escribieron de memoria; y
decidir si se produce el período completo de superficies (cabe en el disco
interno; el costo es de cómputo y no está medido con 800 árboles).
