# Revisión del 2026-10-03: hallazgos sobre el modelo de 1 km y su estado

Nota del 2026-10-04. Conserva en este repositorio lo que la revisión adversarial del 2026-10-03 dijo
del producto de exposición a 1 km: el código de `scripts_modelo_1km/`, los datos de entrada y la
validación. Cada punto lleva su estado, comprobado el 2026-10-04 entre las 22:50 y las 23:45 (hora de
Chile) sólo con lecturas sobre `scripts_modelo_1km/`, `docs/modelo_1km_horario.qmd`,
`output_files/modelo_1km*/` y `~/Asesorias_Data_local/AirPollution/modelado_1km/`. Las líneas citadas
son las de esa hora.

## Origen

- Ocho revisores auditaron el proyecto y un refutador atacó cada hallazgo crítico o mayor. Cuando el
  refutador lo corrigió, aquí va su versión y su severidad. Los hallazgos menores no pasaron por
  refutación; los que esta nota da por comprobados se comprobaron ahora.
- La carpeta de la revisión, `others_files/20261003_revision_completa/` (`informe_revision.md`,
  `resultado_revision.json` con 71 hallazgos confirmados, 0 refutados y 58 menores, y
  `reanalisis_revisores/`), sale de Air-Pollution y queda en Air-Pollution-Health-Chile. De sus 129
  hallazgos, 21 son del modelo (dimensiones `modelo_estado` y `modelo_codigo`) y la sección 2.8 del
  informe resume los de robustez de la cadena. Otros, escritos contra el manuscrito, contienen hechos
  del modelo que también se recogen aquí.
- Los scripts con que la revisión reprodujo las fallas de la cadena quedan en `reanalisis_revisores/`
  de esa carpeta (`simular_corte.py`, `verif_retransf/`, `guard_demo/`, `interp_sin_etiqueta.py`,
  `verif_guard_interp.py`, `lpo_vs_loso_celdas.py`, `repredecir.py`). Están escritos para una raíz de
  prueba temporal: hay que ajustar sus rutas antes de usarlos.
- Los puntos marcados «(2.ª ronda)» vienen de la segunda ronda adversarial (2026-10-03/04), hecha sobre
  el manuscrito reescrito. Su resultado no quedó en la carpeta; sus cifras se recalcularon para esta nota.
- No se trata aquí el análisis de salud ni la redacción del paper.

## En resumen

- El producto publicado es coherente y no cambió desde la revisión: no se escribió ninguna superficie
  después del 2026-10-02 a las 22:57 ni ningún agregado de exposición después del 2026-10-03 a las 00:06.
- De los arreglos de código que pidió la revisión sólo uno está hecho: la exclusión de `dist_costa_km`
  en NO2 es el valor por omisión desde el 2026-10-03 (`_features.py:536`). Los demás siguen abiertos.
  Ninguno cambia hoy una cifra publicada, pero el doble reescalado (1.1) y la producción con un diseño
  de interpolación distinto del calibrado (1.4) pueden corromper una corrida futura sin que ninguna
  guarda lo detecte, y el control de la fase 2 (1.2) tampoco lo vería.
- Los hallazgos de validación son límites del producto que hay que declarar, no errores de cálculo:
  LOSO no retira juntos a los monitores gemelos de Coyhaique (R² diario de PM2,5 de 0,563 a 0,522),
  LPO conserva la red concurrente como entrada, el NO2 no se transfiere a regiones sin monitores y el
  Norte Grande quedó con la media de área de NO2 más alta del país.
- Tres cuantificaciones que pidió la revisión ya existen, pero sus productores están en
  `scripts_riesgo_agudo/` y se van a Air-Pollution-Health-Chile: `loso_pares.py`, `costa_no2.py` y
  `cobertura_predictores.py`. En Air-Pollution no queda nada que las rehaga.

## Estado del producto

La revisión dio por correcto el producto publicado (sección 6 del informe), y sigue igual:

- Grilla de 838.430 celdas; serie del 2000-01-01 al 2026-09-13 (9.753 días); paneles de calibración de
  9.740.634 filas y 107 estaciones (PM2,5) y de 5.711.491 filas y 57 estaciones (NO2), SINCA y SNIFA.
- 70 predictores candidatos (`FEATURES_MODELO_BASE`, en `_features.py`); el modelo de PM2,5 usa los
  70 y el de NO2 69 (sin `dist_costa_km`). Boosters de 800 árboles:
  `bdac463a84b3` (PM2,5) y `9b9a8664001c` (NO2). Los dos `modelo_final.json` declaran `duan_oof_macrozona`.
- Los 58.518 manifiestos publicados (dos gases, tres ámbitos, 9.753 días) declaran ese booster y esa
  corrección, su tamaño coincide con el NetCDF y no hay archivos `.part`. En NO2 se reescalaron 9.751
  días nacionales y los 9.753 de la RM y de Biobío (`retransformacion_origen = duan_oof`); los dos días
  nacionales restantes (2024-06-05 y 2024-06-06) se volvieron a predecir. Ningún día de PM2,5 se reescaló.
- Factores del reescalado de NO2, iguales a exp(smear nuevo − smear viejo): nacional, media 1,0674
  (0,9535 a 1,2521); RM 0,9589; Biobío 1,0377 (`output_files/modelo_1km/retransformacion_20261002T201239.log`).
- Los tres ámbitos coinciden en las celdas compartidas en 9 días por gas repartidos entre 2000 y 2026,
  incluido el 2003-09-02, salvo los dos días de NO2 vueltos a predecir, que difieren en 0,01 ppb como
  máximo. La revisión re-predijo 23 días nacionales en 2.500 celdas, todos dentro de 0,01 ppb. Este
  control no ve una falla común a los tres ámbitos.

R² del producto publicado (`output_files/modelo_1km/eval_niveles_<pol>.csv`, 2026-10-02). LOSO y LBO
agrupan por celda (102 grupos en PM2,5, 56 en NO2), LRO por región (15 y 12) y LPO por cuatrienio (7):

| Protocolo | PM2,5 horario | diario | mensual | anual | NO2 horario | diario | mensual | anual |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| LOSO | 0,405 | 0,563 | 0,709 | 0,583 | 0,496 | 0,604 | 0,697 | 0,704 |
| LBO (10 km) | 0,361 | 0,521 | 0,705 | 0,610 | 0,436 | 0,549 | 0,644 | 0,651 |
| LRO | 0,315 | 0,453 | 0,617 | 0,466 | 0,126 | 0,119 | 0,106 | −0,062 |
| LPO | 0,505 | 0,671 | 0,858 | 0,841 | 0,590 | 0,694 | 0,807 | 0,860 |

Retirar el entorno de 10 km cuesta poco (de LOSO a LBO); la caída fuerte es sólo la del NO2 bajo LRO.
En PM2,5 el LBO anual supera al LOSO, y LPO queda sobre LOSO en todos los niveles, así que los protocolos
no retienen «cada vez más» estructura.

## 1. Robustez de la cadena (sección 2.8 del informe)

### 1.1 `aplicar_retransformacion.py` puede reescalar dos veces (moderado)

- **Hallazgo.** `reescalar_dia` reemplaza el NetCDF (línea 94) antes de publicar el manifiesto
  (línea 100). `main` decide el método viejo de cada día sólo por el manifiesto, o por
  `smear_anterior` si no lo hay (líneas 152-155), sin comparar `sha256` ni `bytes` del manifiesto con
  el archivo; el atributo `retransformacion` del NetCDF se lee (línea 84) sólo para sobrescribirlo
  (línea 90). Un corte en esa ventana (≈14 % del tiempo de un día nacional, 8 a 32 % de uno de la RM)
  hace que la corrida siguiente aplique f_nuevo/f_viejo dos veces; después el manifiesto queda completo
  y coherente, así que no lo ven la guarda de producción ni el control del lanzador. La revisión lo
  reprodujo con una salida forzada: en la RM, (y + 1) corrido por un factor mediano de 0,9542 (0,9521
  a 0,9669), hasta 1,22 ppb; en el Norte Grande el factor llega a 1,2521. Un NetCDF sin manifiesto se
  reescala dos veces (hasta 1,78 ppb) y recibe un manifiesto parcial, sin `modelo_sha256`,
  `enlaces_sha256`, celdas ni fecha. Sin `smear_anterior` la corrida cae con `AttributeError`.
  `modelo_final.json` se escribe con `write_text` (línea 130), sin atomicidad.
- **Hoy no hay daño.** La ventana se tocó una vez: el apagón del 2026-10-02 dejó el 2003-09-02
  reescrito con su manifiesto viejo, y quedó bien sólo porque esa pasada usaba factor 1. Los 1.341
  NetCDF nacionales con dos notas «reescalada» en el atributo `nota` son los 1.340 días reetiquetados
  por esa pasada más el 2003-09-02.
- **Estado.** Abierto: el archivo no cambia desde el 2026-10-02 a las 20:09.
- **Arreglo** (versión del refutador). El discriminador es el `sha256` del manifiesto, no el atributo
  del NetCDF: los 1.340 días reetiquetados tenían atributo `duan_oof_macrozona` sobre valores
  `duan_oof`, y una regla por atributo los habría saltado en silencio (≈ −20 % en el Norte Grande,
  +4,9 % en la RM). Si el `sha256` calza, confiar en el manifiesto y avisar si el atributo discrepa; si
  no calza, tomar el atributo y republicar el manifiesto sin reescalar, o parar; sin manifiesto, usar
  el atributo y nunca `smear_anterior`, y parar si falta. Escribir `modelo_final.json` con
  `publicar_json`, registrar el factor aplicado o un digest del smear, saltar los días cuyo
  `modelo_sha256` no sea el vigente y agregar el corte forzado como prueba de regresión.

### 1.2 El control de la fase 2 sólo cuenta etiquetas (moderado)

- **Hallazgo.** `refrescar_retransformacion.sh:50-64` cuenta, por ámbito, los manifiestos cuya
  `retransformacion` no es `duan_oof_macrozona`. No lee valores ni exige un número de días: habría
  pasado el estado de factor 1 del 2026-10-02 y pasa con ámbitos vacíos (la revisión lo reprodujo:
  `nacional {}`, `rm {'duan_oof_macrozona': 3}`, `biobio {}`, código 0). La marca
  `output_files/modelo_1km/.refresco_retransf/fase1_ok` es un archivo vacío tocado a mano el
  2026-10-02 a las 20:10, dos horas después de que la fase 1 terminó (18:18); no guarda identidad, así
  que toda corrida futura se salta la calibración (líneas 39-46).
- **Estado.** Abierto. El lanzador se editó el 2026-10-04 (su fase 3 quedó en la exposición por
  ámbito, líneas 65-69), pero el control y la marca no cambiaron.
- **Arreglo.** Un detector exhaustivo que cuente las notas «reescalada» del atributo `nota` de cada
  NetCDF (≈98 s para todos); comparar re-predicciones en conteos int16 con |Δ| ≤ 1, porque un umbral en
  flotante de un cuanto da falsas alarmas (0,010002 ppb en el 17 % de las celdas); exigir conteos no
  nulos, iguales entre ámbitos e iguales al número de NetCDF, en vez de un 9.753 fijo; un control entre
  ámbitos en celdas compartidas (40 días en 12 s), sabiendo que no ve una falla común; una marca con el
  `sha256` del modelo, el método, el smear y el hash del código. Re-predecir cuesta ≈5 s de contexto más
  ≈6 s por día.

### 1.3 Sin candado de escritura (menor a moderado)

- **Hallazgo.** La única guarda es `pgrep -f` sobre la ruta del ejecutor del qmd
  (`refrescar_retransformacion.sh:23-25`, `completar_motores.sh:28-30`). Da falsos positivos con
  lanzamientos desacoplados: el «Ya hay una corrida del modelo en marcha» de
  `output_files/modelo_1km/retransf_lanzador.log` (2026-10-02, 20:10 hora local) lo causó el propio
  lanzador, y el relanzamiento de las 20:12 pasó. Tampoco ve un `quarto render` directo,
  `producir_serie.py`, `aplicar_retransformacion.py` ni `exposicion.py`. `lanzar_corrida_completa.sh`,
  `lanzar_produccion_serie.sh`, `reajuste_no2.sh` y `experimento_interpolacion.sh` no tienen guarda.
  Los registros del 2026-09-19 al 2026-10-03 no muestran escritores superpuestos.
- **Estado.** Abierto. No hay `flock`, `lockf` ni archivo de candado en `scripts_modelo_1km/` ni en el qmd.
- **Arreglo.** En los lanzadores, `lockf -k -t 0` sobre
  `~/Asesorias_Data_local/AirPollution/modelado_1km/.escritura.lock` con una variable de reentrada y un
  aviso en la salida 75 (sin `-k`, `lockf` borra el archivo al salir y abre una carrera con el `flock`
  de Python). `fcntl.flock` en el chunk de configuración del qmd, que cubre el ejecutor y
  `quarto render`, y en `producir_serie.py`, `aplicar_retransformacion.py` y `exposicion.py`, salvo en
  sus modos de sólo lectura. Detener corridas matando el grupo de procesos.

### 1.4 La producción no comprueba el diseño de interpolación (menor)

- **Hallazgo.** `ContextoPrediccion` toma los productos interpolados sólo de `MODELO_1KM_INTERPOLAR`
  (`produccion.py:330`) y `modelo_final.json` no guarda `interpolacion` (comprobado en los dos gases).
  Con la variable puesta y sin etiqueta, la firma pasa a `cams,era5blh,geoscf,merra2`, los 9.753 días
  publicados de cada gas fallan la guarda por día (`produccion.py:367-370`) y `producir_serie.py` los
  volvería a predecir sobre `superficies/` con predictores interpolados para un booster calibrado con
  el píxel más cercano. El desplazamiento medido antes, en el sentido inverso, fue de 0,2 a 0,67 DE por
  variable, y recuperar la serie costaría 31 a 34 h más lo de aguas abajo. Quedaría registrado en el
  log y en el atributo `interpolacion` de cada día.
- **Estado.** Abierto. El qmd sí está protegido: `panel()` aborta si la firma del panel no coincide
  (`docs/modelo_1km_horario.qmd:2054-2057`). No hay lanzamiento interpolado pendiente, porque la
  interpolación se rechazó (sección 5), y `lanzar_produccion_serie.sh` (2026-09-25) no hace
  `unset MODELO_1KM_INTERPOLAR`.
- **Arreglo.** Leer `paneles/panel_{pol}{sufijo}.json`, exigir que su `sha256` sea
  `modelo_final.json['panel_sha256']` (el enlace se cumple en todos los modelos actuales) y que su
  `interpolacion` sea la firma de producción; mejor, tomar el diseño de ahí y abortar sólo si el entorno
  discrepa. Escribir `interpolacion` en `modelo_final.json`. Como parche inmediato,
  `unset MODELO_1KM_INTERPOLAR` en `lanzar_produccion_serie.sh`, o que `producir_serie.py` se niegue a
  correr con la variable puesta y sin etiqueta.

### 1.5 Puntos menores

- **Exclusión de `dist_costa_km`: resuelto el 2026-10-03.** `EXCLUSIONES_POR_DEFECTO = "no2:dist_costa_km"`
  (`_features.py:536`) es el valor por omisión de `MODELO_1KM_EXCLUIR` (línea 549), así que un render
  simple ya no reajusta el NO2 con distancia a la costa. Quedan tres cabos: la variable definida y vacía
  anula la exclusión sin aviso (comprobado: `MODELO_1KM_EXCLUIR=` devuelve un conjunto vacío; el valor
  documentado para vaciarla es `-`); la lista de predictores no entra en la reutilización de
  `metricas.json` (`docs/modelo_1km_horario.qmd:2690-2692`) ni en la identidad de `oof_ml` (3307-3309),
  aunque sí en las firmas de los pliegues (2500 y 3209); `modelo_final.json` no guarda la exclusión,
  sólo su resultado en `features`.
- **Guardas por nombre de método: abierto.** La guarda por día (`produccion.py:367-370`), el reescalador,
  que decide cada día por el nombre (`aplicar_retransformacion.py:81` y 152-155), y la firma de
  exposición (`exposicion.py:159-162`) comparan el nombre `duan_oof_macrozona`, no los valores del
  smear, y esa firma no lleva `modelo_sha256`. Si `oof.parquet` cambiara con el mismo método, el qmd conservaría el
  `modelo_final.json` en caché (línea 2767) y nada marcaría superficies ni agregados como viejos. Hoy es
  coherente: el smear guardado es el recalculado desde `oof.parquet` (diferencia 0,0). Arreglo: un
  digest del smear en manifiestos, NetCDF y firma de exposición, y `modelo_sha256` en esa firma.
- **Validación de nombres: abierto.** `smear_de` trata todo método que no empiece por `smearing` como
  la corrección paramétrica (`produccion.py:152-153`; `duan_in_sample` da el mismo smear que `duan_oof`);
  `retransformacion_de` devuelve tal cual un nombre mal escrito (líneas 135-138);
  `MODELO_1KM_INTERPOLAR=0` se lee como el producto `'0'` (`_features.py:421-426`), con lo que el qmd
  rechaza paneles válidos mientras la producción filtra la firma a vacío; `smear_vigente` usa
  `RETRANSFORMACION_POR_DEFECTO` e ignora las variables de entorno (`aplicar_retransformacion.py:62`).
  Arreglo: lista blanca de los cuatro métodos; '', '0', 'no', 'false' y 'off' como apagado; rechazar
  productos fuera de era5blh, merra2, cams y geoscf; `smear_vigente` con `P.retransformacion_de(pol)`.
- **Firma de interpolación sin los pesos: abierto y latente.** La firma es sólo la lista de productos
  (`produccion.py:339-344`; qmd 2037-2041): reconstruir `enlaces_interpolacion.parquet` no invalida
  paneles, modelos ni superficies interpolados. Arreglo: sumar `sha256(enlaces_interpolacion.parquet)[:16]`.
- **Pruebas: abierto.** `scripts_modelo_1km/tests/test_modelo_1km.py` (2026-09-24) tiene 26 pruebas y
  las 26 pasan (corridas el 2026-10-04); ninguna cubre la interpolación, el reescalado, las firmas ni
  las guardas. Arreglo: identidad con la variable apagada sobre un mes sintético, bordes de
  `combinar_nodos`, guarda con manifiestos sin `interpolacion`, ida y vuelta de `reescalar_dia` y la
  regla de que un NetCDF ya convertido con manifiesto viejo no se vuelva a reescalar.

## 2. Retransformación

- El producto corrige por macrozona × franja en los dos gases (`produccion.py:132`); la franja diurna
  va de las 08:00 a las 18:59 (`hora_local` 8 a 18, `produccion.py:114-115`). Sesgo normalizado LOSO,
  recalculado desde `oof.parquet` con la corrección fuera de pliegue de cada método:

  | Gas | Corrección | Nacional | Norte Grande | Norte Chico | Centro | Sur | Austral | Rango |
  |---|---|---:|---:|---:|---:|---:|---:|---:|
  | PM2,5 | franja | +2,44 % | −4,1 | +7,8 | +12,0 | −6,6 | −4,8 | 18,6 puntos |
  | PM2,5 | macrozona × franja | +2,37 % | −0,9 | +6,4 | +3,7 | +0,8 | +3,8 | 7,3 puntos |
  | NO2 | franja | +3,63 % | −19,3 | −4,9 | +6,7 | −3,4 | −17,2 | 26,0 puntos |
  | NO2 | macrozona × franja | +1,69 % | −0,5 | +6,2 | +1,9 | +0,9 | −16,5 | 22,7 puntos |

  En la RM el PM2,5 pasa de +16,9 % a +8,3 %. El LOSO horario del NO2 sube de 0,4875 a 0,4958
  (`retransformacion_diagnostico` de `modelos/no2/metricas.json`). En NO2 la ganancia no es pareja:
  el Norte Chico pasa de −4,9 a +6,2 % y el Austral, con un solo monitor, sigue cerca de −17 %.
- **Costo bajo LRO (límite sin declarar).** En NO2 la corrección por macrozona baja el
  acuerdo donde el producto ya es más débil: LRO horario de 0,140 a 0,126, diario de 0,143 a 0,119,
  anual de −0,013 a −0,062, y sesgo LRO de −20,9 % a −26,1 % (mismo booster con corrección por franja
  en `output_files/modelo_1km_no2sincosta/eval_niveles_no2.csv`, contra el publicado). En PM2,5 mejora
  todos los protocolos (LRO horario de 0,310 a 0,315, según la revisión).
- **Respaldo fuera de pliegue (menor; abierto).** Cuando los demás grupos aportan menos de 100
  residuos al estrato, `retransformar_oof` usa el total del estrato, que incluye al grupo retenido
  (`docs/modelo_1km_horario.qmd:2572-2573`). Pasa sólo en NO2: bajo LOSO en 34.062 filas (0,60 %), las
  de la celda 5826637, Coyhaique II, único monitor de NO2 del Austral; bajo LRO en 255.728 filas
  (4,48 %), las de Antofagasta (RII) y Aysén (RXI). Celdas con monitor de NO2 por macrozona, del Norte
  Grande al Austral: 2, 3, 26, 24 y 1 (en PM2,5: 11, 6, 38, 42 y 5). Con un respaldo honesto, a la
  franja fuera del grupo, el LRO horario del NO2 pasaría de 0,1256 a 0,1250 según la revisión. En
  NO2, la corrección de producción del Austral (40,6 % de las celdas) sale de una estación y la del
  Norte Grande (19,6 %) de tres estaciones en dos celdas.
- **Predicciones en muestra con la corrección global (menor; abierto).** `_a_escala_original`
  (qmd 3356-3358, usada en 3414-3415) busca claves `macrozona|franja` en `smear_in_sample`, que sólo
  tiene `diurna`, `nocturna` y `_global` (comprobado en los dos `modelo_final.json`), así que toda fila
  cae en `_global`. Efecto despreciable: R² en muestra 0,55375 contra 0,55410 en PM2,5.
- **Nombre del método.** `duan_oof` y `duan_oof_macrozona` son la corrección lognormal
  exp(ẑ + ½·Var) con la varianza fuera de pliegue (`produccion.py:152-153`; el docstring de
  `retransformar_oof`, qmd 2560-2561, lo dice bien). El smearing de Duan es `smearing_oof`, evaluado y no
  usado (sesgo LOSO +1,73 % en PM2,5 y +7,77 % en NO2). El docstring de `aplicar_retransformacion.py`
  (línea 3) y `scripts_modelo_1km/README.md:89` la llaman «corrección de Duan». Cambiar el nombre
  invalidaría manifiestos y cachés; basta con decirlo bien.
- **Comentario viejo (menor; abierto).** `docs/modelo_1km_horario.qmd:2631-2637` sigue diciendo que en
  NO2 la corrección por macrozona «no mejora» y «se deja global», con cifras anteriores (+16,7 % y
  +8,2 % en la RM).
- **Camino de producción.** El cambio de corrección del NO2 se aplicó reescalando, sin volver a
  predecir: pred' = (pred + 1)·f'/f − 1, con `retransformacion_origen` y `reescalado_utc` en cada
  manifiesto. El informe del modelo no lo describe.

## 3. NO2 sin distancia a la costa

Con tres monitores de NO2 en el Norte Grande, uno tierra adentro, `dist_costa_km` pintaba con el nivel
de Calama toda celda a más de ≈80 km de la costa. Se quitó del NO2 (etiqueta `no2sincosta`, 2026-09-30 y
2026-10-01), se promovió a definitivo y después el NO2 pasó a la corrección por macrozona (2026-10-02/03).

| | v1: con distancia, corrección por franja | Reajuste solo: sin distancia, franja | Publicado: sin distancia, macrozona × franja |
|---|---:|---:|---:|
| Norte Grande, costa (< 80 km), ppb | 4,63 | 6,52 | 8,22 |
| Norte Grande, interior, ppb | 7,45 | 7,36 | 9,19 |
| Razón interior/costa | 1,61 | 1,13 | 1,12 |
| Mediana nacional, ppb | 4,27 | 4,24 | 4,36 |
| Máximo nacional, ppb | 31,12 | 30,86 | 29,55 |
| LOSO horario / diario / mensual | 0,480 / 0,581 / 0,666 | 0,487 / 0,593 / 0,682 | 0,496 / 0,604 / 0,697 |
| LRO horario / diario / anual | 0,191 / 0,212 / 0,100 | 0,140 / 0,143 / −0,013 | 0,126 / 0,119 / −0,062 |

Las medias del periodo salen de `exposicion/no2_v1_20261001` y `exposicion/no2`; la columna del medio la
reconstruyó la revisión deshaciendo el reescalado con `smear` y `smear_anterior`, porque las superficies
y agregados de NO2 con corrección por franja ya no existen (`superficies_no2sincosta*` y
`exposicion_no2sincosta*` no tienen días de NO2). Los R² salen de
`output_files/modelo_1km/respaldo_no2_v1_20261001/`, `output_files/modelo_1km_no2sincosta/` y
`output_files/modelo_1km/eval_niveles_no2.csv`. Los monitores del Norte Grande miden 10,87 ppb en la
costa y 9,65 en el interior.

- **El resto del país sí cambió.** Después del reescalado los factores por macrozona (día/noche) son:
  Norte Grande 1,2046/1,2521; Norte Chico 1,0979/1,1481; Centro 0,9653/0,9535; Sur 1,0325/1,0420;
  Austral 0,9710/1,0399.
- **El reajuste cuesta en LRO (2.ª ronda; abierto como límite).** Con la misma corrección, quitar la
  distancia a la costa subió el LOSO y bajó el LRO en todos los niveles (tabla). La compuerta mira sólo
  el LOSO horario (`diagnostico_franja_no2.py:26-32` y 73, umbral 0,45 en `reajuste_no2.sh:43`; la
  franja «se informa, no bloquea»). Con la regla de la interpolación, que decide por LRO, el cambio no
  habría pasado.
- **La banda bajó en razón, no en nivel (mayor; abierto como límite).** El Norte Grande es hoy la
  macrozona con la media de área de NO2 más alta: 8,89 ppb contra 7,87 en el Centro (en v1, 6,15 contra
  8,40). La Región de Antofagasta promedia 9,12 ppb (mediana 9,30) y la RM 11,67. Según la revisión, en
  2020 GEOS-CF (0,79 contra 0,15 ppb), CAMS (1,96 contra 1,15) y la columna de TROPOMI (0,42 contra
  0,44 × 10¹⁵ moléculas/cm²) ponen ese interior en niveles de fondo, y allí el producto es 64 veces
  GEOS-CF. Los tres monitores son dos sitios industriales: Tocopilla (222 y 251, en la misma celda) y
  Calama (236), con R² LOSO horario de −0,159, −0,121 y −0,031. La revisión propone enmascarar o sombrear
  el NO2 donde no hay soporte (distancia a un monitor de NO2, o macrozonas con R² LOSO negativo).
- **Dependencia de MERRA-2.** La presión de superficie de MERRA-2 (`m2_ps`) pasó del 8,1 % al 21,5 % de
  la ganancia del NO2 y es su segundo predictor, detrás de `obs_vec` (28,2 % → 32,9 %); en v1
  `dist_costa_km` tenía el 21,3 %. Sus costuras están en la sección 5.
- **Reproducibilidad.** El «antes» necesita `exposicion/no2_v1_20261001`, `modelos/no2_v1_20261001`,
  `output_files/modelo_1km/respaldo_no2_v1_20261001/` y `output_files/modelo_1km_no2sincosta/`. El
  cálculo quedó en `scripts_riesgo_agudo/costa_no2.py` → `output_files/paper/costa_no2.json`
  (2026-10-04), que se van a Air-Pollution-Health-Chile. Si se ordenan los respaldos hay que moverlos, no
  borrarlos, y actualizar esas rutas.

## 4. Validación

### 4.1 LOSO no retira juntos a los monitores gemelos (2.ª ronda)

- **Hallazgo.** LOSO y LBO agrupan por celda de 1 km (`docs/modelo_1km_horario.qmd:2654-2662`): dos
  monitores de la misma celda salen juntos (5 celdas en PM2,5, 1 en NO2), pero no los que están a menos
  de 1 km en celdas vecinas. En PM2,5 son siete pares: Huasco (309, 310, 330 y 333, entre 0,09 y
  0,86 km), Puchuncaví (503 y 548, 0,95 km) y Coyhaique (B03 y B04, 0,87 km). En NO2, 309-310 y 503-548.
- El par de Coyhaique pesa: comparte 111.912 horas, su DE diaria es 59,3 µg/m³ contra 26,1 nacional y
  el monitor de PM2,5 más cercano fuera del par está a 52,6 km. Reemplazando la predicción LOSO de los
  monitores afectados por la de LBO, que retira todo monitor a 10 km y por eso es una cota conservadora,
  el R² diario nacional de PM2,5 baja de 0,563 a 0,522, igual al LBO (0,521). Todo el descenso viene de
  Coyhaique: reemplazando sólo ese par también da 0,522. En las demás estaciones LOSO y LBO dan 0,525 y
  0,524. El NO2 no se afecta (0,604 → 0,607). Recalculado el 2026-10-04 desde `modelos/<pol>/oof.parquet`
  y `grilla_1km/estaciones_enlaces*.parquet`.
- **Estado.** Abierto en el modelo: el R² LOSO publicado (0,563) incluye el par. El cálculo existe en
  `scripts_riesgo_agudo/loso_pares.py` → `output_files/paper/loso_pares.json`, que se van a
  Air-Pollution-Health-Chile.
- **Arreglo.** Agrupar LOSO por distancia (monitores a menos de 1 km salen juntos) y recalcular sus
  pliegues, o informar las dos cifras.

### 4.2 El predictor de vecindad no se recalcula en LPO (menor a moderado; por diseño)

- **Hallazgo.** `ajuste_por_red` recalcula `obs_vec`, `peso_vec` y `dist_est_km` sólo en LOSO, LBO y
  LRO (`docs/modelo_1km_horario.qmd:2722`) y sólo cuando el pliegue retira dos o más estaciones
  (línea 2598); en los demás pliegues LOSO (97 de 102 en PM2,5, 55 de 56 en NO2) el valor del panel ya
  excluye a la propia estación. Bajo LPO cada fila de prueba conserva las observaciones concurrentes de
  los otros monitores, que son del mismo cuatrienio retenido. Ese predictor lleva el 60 % de la ganancia
  en PM2,5 y el 33 % en NO2.
- **Los resultados se sostienen.** En las celdas de una sola estación (94,1 % de las filas de PM2,5 y
  98,0 % de las de NO2) la entrada de prueba es idéntica en LOSO y LPO, y LPO gana lo mismo que en el
  total: +0,101 en R² horario de PM2,5 (0,412 → 0,513) y +0,094 en NO2 (0,509 → 0,603). La interpolación
  de vecinas, que es ese predictor solo, da el mismo R² diario en muestra, en LOSO y en LPO (0,490 en
  PM2,5, 0,361 en NO2). La brecha viene de que LPO ya vio a la estación en otros años: mide años no
  vistos con la red concurrente presente, como en producción, no un periodo sin monitores.
- **Estado.** Por diseño; lo que estaba mal era la descripción del suplemento. No recalcular `obs_vec`
  sin la ventana: dejaría sin vecindario a toda fila de prueba.

### 4.3 Alcance

- El NO2 no se transfiere a regiones sin monitores (LRO horario 0,126, anual −0,062), y fuera de
  estación la habilidad es casi nula en el norte aun con monitores (2.ª ronda). R² diario LOSO por
  macrozona: PM2,5, 0,058 en el Norte Grande (12 estaciones) y 0,146 en el Norte Chico (7); NO2, −0,195
  en el Norte Grande (3), −0,138 en el Norte Chico (3) y 0,115 en el Sur (24).
- ACAG (V6GL03 `CNNPM25`, `_comun_modelo.py:565-572`) es el segundo predictor del PM2,5 (7,8 % de la
  ganancia; 2,4 % en NO2) y está calibrado contra monitores de superficie. Según la revisión, su versión
  V6 (Shen et al., 2024) se entrenó fuera de Norteamérica, Europa, China y Australia con datos de la
  literatura, la base de calidad del aire de la OMS y OpenAQ, que muy probablemente incluyen SINCA; si es así, una estación retenida en LOSO, LBO o LRO no es del todo
  independiente de ese predictor y el acuerdo fuera de estación del PM2,5 puede ser optimista. Sin medir.
- Selección (2.ª ronda). Los hiperparámetros se fijaron antes de validar, pero la variante de
  retransformación se eligió entre cinco por su resultado LOSO (`retransformacion_diagnostico` de
  `metricas.json`), el conjunto de predictores del NO2 entró por una compuerta LOSO y el algoritmo se
  mantuvo después de la comparación de motores. Todos los protocolos informados llevan esas elecciones.

## 5. Interpolación de reanálisis y costuras

- La interpolación bilineal de ERA5 BLH, MERRA-2, CAMS y GEOS-CF se probó bajo la etiqueta `interp` y se
  rechazó con la regla fijada de antemano (`output_files/modelo_1km/interpolacion_20261001T230716.log`,
  2026-10-02 a las 03:24: «PM25: no mejora; NO2: no mejora»). La regla (`comparar_etiquetas.py:38-40` y
  126-153) exige que el LRO horario y diario mejoren al menos max(0,01; 2 × ruido) y que ningún otro
  protocolo pierda más que ese umbral. En PM2,5 el LRO horario subió +0,0084, bajo 0,01. En NO2 el LRO
  mejoró (+0,017 horario, +0,025 diario), pero el LOSO bajó (−0,015 horario, −0,019 diario, −0,034 anual).
- Precisiones (2.ª ronda y registro): la base del NO2 fue `no2sincosta`, con corrección por franja, no
  el producto publicado; en el registro la columna de ruido quedó vacía y el PM2,5 se comparó contra el
  definitivo, así que el umbral efectivo fue 0,01. El lanzador vigente (`experimento_interpolacion.sh`,
  modificado el 2026-10-02 a las 03:25, un minuto después del veredicto) ya pasa
  `--base pm25:no2sincosta --nulo pm25:no2sincosta`; contra esa base el LRO del PM2,5 sube +0,004
  horario y +0,008 diario, también bajo 0,01. Para el NO2 no hay par nulo. GEOS-CF se midió en 2 de las 8 horas de las costuras.
- La producción usa el píxel más cercano: los manifiestos tienen `interpolacion` vacía o ausente, y con
  la variable apagada el ensamblado es idéntico byte a byte a los paneles definitivos (revisión, 40.000
  filas por gas).
- **Costuras (límite conocido).** En `output_files/modelo_1km/costuras_reanalisis.json` (2026-10-01) el
  salto de cada predictor dentro de un píxel nativo es exactamente 0 y toda su variación está en los
  bordes, que son entre el 1,4 y el 4,2 % de los pares de celdas vecinas. La presión de MERRA-2 salta en
  los bordes 5.956 a 6.195 Pa en longitud (≈60 hPa) y 1.621 a 1.677 Pa en latitud (≈16 hPa); 39 hPa es
  el promedio de 8 horas y dos direcciones, no un máximo. Las costuras llegan a la superficie: en la
  media del periodo, la diferencia entre celdas vecinas que cruzan un borde de píxel de MERRA-2 es 1,5
  veces la de las que no lo cruzan en PM2,5 y 4,3 veces en NO2; en el Norte Grande, 4,9 y 6,6 veces
  (recalculado el 2026-10-04 desde `exposicion/<pol>/anual_*.parquet`). De las 345 comunas, el 77 %
  cruza dos o más píxeles de MERRA-2 y el 35 % tiene al menos el 90 % de sus celdas en uno solo.

## 6. Datos de entrada

- **Elevación y pendiente son comunales (mayor; abierto).** En `grilla_1km/estaticas_metadata.json`,
  `elev_fuente` es `comunal_topografia_csv` en 790.885 celdas, `vecino_mas_cercano` en 47.543 y
  `sin_dato` en 2; las 838.430 celdas tienen 346 valores distintos de elevación y 346 de pendiente, y
  `elev_sd_m` está vacía. `covariables_estaticas.py` busca NASADEM en
  `Topografia/NASADEM_30m_native/tiles` (línea 49), que no existe: en `Topografia/` sólo está
  `topografia_comunal.csv`. La elevación es la 15.ª importancia del PM2,5 y la 13.ª del NO2. Arreglo:
  completar la descarga de NASADEM y reajustar, o declarar que la elevación no resuelve el terreno a 1 km.
- **Otras estáticas** (según la revisión). Cobertura de suelo ESA CCI de 300 m por año, con 2022
  repetido en 2023 a 2026 (`lulc_raster_por_anio`); población comunal de proyecciones censales repartida
  en forma dasimétrica; distancia a la costa calculada por celda (805.185 valores distintos) hasta el
  píxel de agua de ESA CCI más cercano fuera de los polígonos comunales.
- **Ventanas de los predictores (abierto en este repositorio).** TROPOMI y GEOS-CF existen sólo del
  2019-01-01 al 2024-12-31 (`satelites.dias_sin_no2` = 7.563 de 9.753 días); CAMS, de 2003 a 2025;
  MERRA-2, hasta el 2026-05-31; ERA5 BLH, hasta el 2026-06-21; MAIAC Terra, desde el 2000-02-24 y Aqua,
  desde el 2002-07-05; ACAG propio hasta 2024-12 y después su climatología mensual 2018 a 2024, con la
  bandera `acag_clim` (`_features.py:259-288`). MOPITT y OMI no son predictores. La parte 2025-2026 se
  predice con menos fuentes y con ACAG climatológico. Lo calcula `scripts_riesgo_agudo/cobertura_predictores.py`
  → `output_files/paper/cobertura_predictores.csv`, que se va a Air-Pollution-Health-Chile; el informe del
  modelo no lo dice.
- **Radios de enlace** (`construir_grilla.py:40-43`). Píxel propio hasta 1,5 km (MAIAC), 9 (ERA5-Land),
  22 (ERA5 BLH y GEOS-CF), 45 (MERRA-2) y 65 km (CAMS); si el propio no trae datos, el píxel válido más
  cercano hasta 16, 40, 90 y 120 km (ERA5-Land, ERA5 BLH, MERRA-2 y CAMS). TROPOMI entra como media
  diaria de los píxeles L2 a menos de 5 km con QA ≥ 0,75 (`_features.py:143`). Se descartan las rachas
  de 24 o más valores idénticos consecutivos (`produccion.py:43`).
- **Filas.** El modelo final se ajusta con todas las filas del panel (qmd 2783); el tope de 1,5 millones
  de filas por pliegue rige en los dos gases (qmd 274 y 2538-2539).
- **Celdas sin comuna (2.ª ronda).** 52.400 celdas (6,2 %) tienen `cod_comuna` ≤ 0: 47.545 con −1, fuera
  de todo polígono comunal, y 4.855 con 0, la zona no delimitada entre 49,2 y 49,8 °S. Quedan fuera de
  toda agregación comunal.
- **Máximo del mapa de PM2,5** (mayor; corregido por el refutador). La media del periodo llega a
  53,74 µg/m³ en la celda del monitor de Cochrane (B06, celda 4969616), y 7.099 de las 8.000 celdas más
  altas (≥ 36,46 µg/m³) están entre 46 y 48 °S; la mediana nacional es 13,88. No es un artefacto sobre
  hielo (las celdas con al menos 50 % de hielo promedian 23,7 µg/m³): es el nivel de humo de leña de
  Cochrane y Coyhaique llevado por las covariables, sobre todo ACAG, a bosques y lagos casi despoblados,
  y aparece en todos los años desde 2000. Una máscara por distancia a monitores no lo resuelve.

## 7. Comparación de motores

- Los diez motores tienen los cuatro protocolos (`output_files/modelo_1km/eval_motores_<pol>.csv`,
  2026-10-02; sus firmas calzan con los `oof*.parquet` vigentes).
- PM2,5: LightGBM es 2.º de 10 en LOSO horario y diario, detrás del ensamble que lo contiene (0,405
  contra 0,412; 0,563 contra 0,568); 6.º en mensual y anual (0,709 y 0,583 contra 0,729 y 0,658 del
  modelo mixto); 1.º en LRO y LPO horario y diario, y en LBO diario.
- NO2: el bosque aleatorio supera a LightGBM en las 16 combinaciones de protocolo y nivel, por 0,010
  (LPO horario) a 0,099 (LBO anual), aun entrenado con la mitad de filas por pliegue (750.000 contra
  1.500.000). LightGBM queda 3.º, 3.º, 3.º y 4.º en LOSO (de horario a anual) y 5.º en LRO, donde lidera el perceptrón
  (0,340 horario, 0,444 diario). Esa ventaja viene de retener la RM: allí LightGBM subestima un 56,5 %
  (R² diario −0,63) y el perceptrón un 18,2 % (0,28); sin la RM, LightGBM da 0,019, el perceptrón −0,191
  y el bosque 0,102, y LightGBM gana al perceptrón en 10 de las otras 11 regiones. La RM es el 75 % del
  error cuadrático de LightGBM en LRO: los árboles no extrapolan sobre el rango de entrenamiento cuando
  se retiene la región más contaminada.
- Los motores no comparten entradas: LightGBM usa 70 y 69 predictores; el bosque, el perceptrón y el
  LightGBM de alertas usan el mismo conjunto con topes de 750.000, 300.000 y 1.500.000 filas; el proceso
  gaussiano, 17 y 16 predictores y 3.000 filas; GWR, RK y el modelo mixto, un diseño lineal de 15 y 13
  columnas con la constante (`oof_lineales.json`); la «interpolación de vecinas» es `obs_vec`, un núcleo
  gaussiano de 150 km (`_features.py:361`), no inverso de la distancia; el ensamble es una ridge sobre
  LightGBM, el bosque y el perceptrón. El bosque también enruta NaN de forma nativa (qmd 3112): el
  manejo de faltantes no distingue a LightGBM.
- El optimismo no es comparable entre motores (2.ª ronda): el proceso gaussiano se ajusta una vez con
  3.000 filas y se evalúa sobre 9,74 millones, así que su «en muestra» es casi todo fuera de muestra
  (R² diario 0,541 contra 0,543 en LOSO, PM2,5).
- **Estado.** Decisión, no defecto: LightGBM se mantuvo por el costo de predecir 838.430 celdas en 234.072
  horas (9.753 días) y por tener una sola cadena para los dos gases, con un costo de exactitud medido frente
  al bosque en NO2.

## 8. Metadatos, respaldos y productos viejos (menor; abierto)

- 29.257 manifiestos de NO2 (9.751 nacionales, 9.753 de la RM y 9.753 de Biobío) tienen `ruta` hacia
  `superficies_no2sincosta*`, y en los mismos NetCDF el atributo `modelo` apunta a
  `modelos/no2_no2sincosta`, hoy `modelos/no2`. En los dos gases `metricas.json` dice «retransformación
  por franja» en `objetivo` (escrito en qmd 2711), y la lista `predictores_omitidos_baja_cobertura` del
  NO2 incluye `dist_costa_km`, excluida por diseño con cobertura 1,0 (qmd 2708-2709). Los valores están
  bien. Arreglo: una pasada sólo de metadatos, y separar las exclusiones de diseño de las de cobertura.
- Respaldos dentro de las raíces del producto: `superficies/no2_v1_20261001` (192 GB),
  `superficies_rm/no2_v1_20261001` (4,3 GB), `superficies_biobio/no2_v1_20261001` (9,4 GB),
  `exposicion*/no2_v1_20261001`, `modelos/no2_v1_20261001` (1,6 GB), `modelos/pm25_no2sincosta`
  (2,6 GB, el mismo booster y panel que `modelos/pm25`), las etiquetas `*_interp`, `*_prueba*`, `*_smoke`
  y `*_previoenlace`, y `output_files/modelo_1km_{interp,no2sincosta,previoenlace,prueba,smoke}`. No
  existe `~/Asesorias_Data_local/AirPollution/respaldos/`. Los globs de `exposicion.py` y
  `aplicar_retransformacion.py` se limitan a la carpeta del gas y no los toman. Ver la sección 3 antes de
  mover los de `no2_v1_20261001`.
- Productos viejos: `docs/modelo_1km_horario.html` (2026-09-27) y `docs/modelo_1km_horario.pdf`
  (2026-09-25) son anteriores al reajuste del NO2, al reescalado y a los cuatro protocolos de los motores;
  `scripts_modelo_1km/README.md` (2026-09-24) describe la corrección «de Duan por franja» (línea 89) y la
  corrección por macrozona sólo para el PM2,5 (líneas 267-280).

## Pendientes, por prioridad

1. Antes de cualquier reescalado nuevo: el discriminador por `sha256` en `aplicar_retransformacion.py`,
   `modelo_final.json` atómico y la prueba del corte forzado (1.1).
2. Borrar o reemplazar `fase1_ok` por una marca con identidad y cambiar el control de la fase 2 por uno
   de valores (1.2).
3. Un candado de escritura común a lanzadores, qmd y scripts (1.3).
4. La guarda de interpolación en producción, o al menos `unset MODELO_1KM_INTERPOLAR` en
   `lanzar_produccion_serie.sh` (1.4).
5. Decidir LOSO por distancia o informar el R² con los gemelos retirados juntos (4.1).
6. Volver a renderizar `docs/modelo_1km_horario.qmd` y llevar al informe del modelo lo que hoy sólo
   calculan los scripts que se van con el paper: ventanas de los predictores, antes y después de la
   distancia a la costa y gemelos de LOSO. Corregir el comentario de las líneas 2631-2637 y el README.
7. La pasada de metadatos (sección 8) y mover los respaldos a `~/Asesorias_Data_local/AirPollution/respaldos/`.
8. Datos: NASADEM y la fracción de leña (sección 6).
9. Menores de código: validación de nombres, digest del smear en las firmas, pesos en la firma de
   interpolación, respaldo fuera de pliegue a la franja fuera del grupo, claves de la corrección en
   muestra y la variable `MODELO_1KM_EXCLUIR` vacía (1.5 y 2).
