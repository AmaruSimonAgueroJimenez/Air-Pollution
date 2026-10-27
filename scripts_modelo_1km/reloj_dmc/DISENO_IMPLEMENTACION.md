# Diseño de implementación del reloj DMC (compuerta C1)

**Qué es.** El plan para escribir, entre varios implementadores en paralelo, el código del «Procedimiento para confirmar el reloj de las horas DMC» v1 (protocolo adoptado y anclado en C0, APH `d02f918`; texto `PROTOCOLO_RELOJ_DMC_v1_propuesta.md`, sha256 `5fff0727…`; umbrales `c0/reloj_dmc_v1.json`, sha256 `3251a4d8…`). **Manda el texto**: si este diseño y el protocolo difieren, gana el protocolo, y la diferencia se anota como riesgo (§7 de este documento).

**Qué no es.** No implementa la ciencia. Fija módulos, estructuras de datos, firmas, el reparto de las pruebas de §8 y las lecturas propuestas de los puntos ambiguos. El esqueleto (`*.py` de esta carpeta y `tests/`) importa sin errores con el intérprete fijado. Cada cuerpo es `raise NotImplementedError` y cada prueba lleva `unittest.skip("por implementar")`.

**Cómo se verificó el esqueleto** (2026-10-23, `~/micromamba/envs/amb_v2/bin/python -B`):
- importan los 22 módulos;
- la fachada resuelve los 23 nombres de §9;
- `unittest discover` corre 218 pruebas, todas omitidas;
- no queda `_comun_modelo` ni `_common` en `sys.modules`, ni hay importaciones suyas en el AST;
- un gancho de auditoría no registró ningún acceso bajo `/Volumes`;
- no se escribió `__pycache__`;
- `sintetico.py` no importa nada del paquete.
- Las 33 plantillas de umbrales fijos calzan con `fijos_texto` del JSON de C0 y dan 124 valores.
- Los 53 fragmentos de `constantes.py` aparecen literalmente en el protocolo.

---

## 0. Reglas de trabajo

1. **Un dueño por módulo y por su archivo de pruebas.** Nadie edita el módulo de otro. Si hace falta cambiar una firma o un esquema de `tipos.py`, se pide al coordinador y se registra en el addendum de C1, porque es un cambio de implementación (§10).
2. **Ningún umbral del Anexo B se escribe a mano.** Se piden a `Umbrales` (`U.a`, `U.f`, `U.frac`); ver §4. Las constantes del cuerpo del texto que no están en el Anexo B viven en `constantes.py`, con su fragmento literal.
3. **Entorno.**
   - Siempre `python -B`.
   - Sólo numpy, pandas, pyarrow y netCDF4, más matplotlib (Agg) en los expedientes. scipy y statsmodels están instalados, pero no hacen falta: los mínimos cuadrados van con `numpy.linalg.lstsq`.
   - Pruebas con `unittest`, porque amb_v2 no trae pytest.
   - Un solo proceso: nada de `multiprocessing` ni de hilos propios.
4. **Datos.**
   - Grupos A a C de §8: sólo carpetas temporales con datos fabricados con el formato real (`sintetico.fabricar_descarga`).
   - Batería D: extractos en memoria.
   - Ninguna prueba abre `/Volumes`. Las de huellas de C1 leen código ya citado (Anexo C) en LOCAL, APH y `AP/logs/`, y se omiten si falta el archivo.
   - El modo `--control-era5` lee ERA5L. El modo `--aplicar` lee ERA5L y la DMC.
5. **Nombres.** Ningún archivo del paquete se llama `descargar_*` ni `download_*`. Lo verifica una prueba.
6. **Paquete.**
   - `reloj_dmc/` es un paquete y usa importaciones absolutas (`from reloj_dmc import tablas`).
   - El ejecutable, si se corre como script, agrega `scripts_modelo_1km` a `sys.path`.
   - Las pruebas se corren desde `scripts_modelo_1km`: `python -B -m unittest discover -s reloj_dmc/tests -t .`.

---

## 1. Mapa de módulos

El reparto sigue el sugerido y agrega archivos de apoyo, para que ninguno se solape y la integración quede en un solo lugar: `tipos`, `entorno`, `fijados`, `umbrales`, `constantes`, `numerico`, `estados`, `orquestacion`, `salidas` y `bateria` (que separa la batería D de los generadores de `sintetico`). `reloj_dmc.py` es la fachada con los 23 nombres de §9 (R-35).

| Módulo | Responsabilidad (y sólo ésa) | Secciones | Depende de |
|---|---|---|---|
| `tipos.py` | Enumerados, `Hipotesis`, `ClaseH`, `Regimen`, `ParteDef`, `Cambio`, `FilaA2`, `InfoEstacion`, `ContextoEstacion`, `ResultadoLinea`, `EvidenciaEstacion`, `ConsecuenciasRed`, `DecisionAnio`, `Tramo`, protocolo `SerieEra5` y **todos los esquemas de tablas**, también los de red (muestras de A3 y A5, calibración y G-dup) y los de salidas (evidencia por parte y por año, no normalizables y CSV de la calibración), que llegaron en la ola 4b; red y salidas conservan alias. Sin lógica. | §2, §4.0, §7.4 | — |
| `entorno.py` | Intérprete fijado, `dont_write_bytecode`, `reset_tzpath(to=[])`, rutas por alias, sha256, JSON canónico, escritura atómica y prohibición de escribir en `/Volumes`. | §9, §7.4 (privacidad) | — |
| `fijados.py` | Carga por ruta y huella del adaptador, de `dmc_features`, de `preflight_v3` y del descargador; extracción por AST (`MACROZONA_REGION`, `transiciones` SINCA); huella de la ruta de etiqueta y versiones admitidas (Anexo C). | §1.9, §3.1, §3.3, Anexo C | entorno |
| `umbrales.py` | `Umbrales` (lectura de `reloj_dmc_v1.json`), traducción de los fijos, regeneración desde el Anexo B y comparación (C1), pasos de §8.F. | Anexo B, §8.F, §10 C1 | — (lee y calcula la sha256 por su cuenta) |
| `constantes.py` | Constantes del cuerpo del texto que no están en el Anexo B, con su fragmento literal (80 desde la ola 4b, con los porcentajes de las predicciones de §1.13; 86 con la Enmienda 3, verificadas contra cada versión del texto y el vigente v1.0.3, `TEXTOS_PROTOCOLO`). | varias | — |
| `numerico.py` | Semilla y remuestreo por bloques; paso nativo (la regla única que usan extraccion y lineas_fisicas); ventana de E3 desde `U.f("E3_VENTANA")`; Pearson; máximo estricto; parábola; ajuste armónico con EE × 2; filtro de 24 h; Spencer y hora solar; estadística circular; distancias; z_pix; redondeo con empates hacia 0. | §4.0, §3.2, §4.3.1, §4.4, §3.3 | constantes |
| `estados.py` | Filas de estado; estado anual por partes según §4.0; combinación de sub-evaluaciones; estado de una clase fusionada. | §4.0, §2.3 | tipos |
| `tablas.py` | Anexos A y A2 (cálculo y huellas); territorio, Zs y P; macrozona; regímenes; partes; anotación del extracto; c_H(R); fusiones; d*; R_min; el calendario con cortes extra en las etiquetas de Cv (`TablasCalendario.con_cortes` y `con_cortes_reglas_vencidas`, ola 4b). | §2, §3.3, §3.5, §4.1.4, Anexos A y A2 | entorno, tipos, constantes (`MACROZONA_REGION` llega por argumento, copiado por `fijados`) |
| `extraccion.py` | Catálogos, conjuntos V/V2/N, manifiestos, admisión de meses, `leer_artefacto`, control propio, H(L), marcas, huella de fila, p_v, coordenadas inconsistentes, huella de manifiestos; lector ERA5-Land, píxeles válidos, elección de píxel, serie mapeada en disco. | §3.1 a §3.4 | entorno, fijados, tipos, umbrales, constantes, numerico, tablas |
| `lineas_registro.py` | E1a, E1b, E1c y E2. | §4.1, §4.2 | tipos, estados, constantes, numerico, tablas (los umbrales llegan en `ContextoEstacion.umbrales`) |
| `lineas_fisicas.py` | Pares de E3, E3t y E3p (regla gruesa), filtro de representatividad, regla fina, E3p anual, ajustes de E4, E4p, cruce ISD y E6. | §4.3, §4.4, §4.6 | tipos, estados, numerico, constantes, tablas (los umbrales llegan en `ContextoEstacion.umbrales`) |
| `guardas.py` | E3d, P7, T-P, E4t, G-versión; marcas G-HR, G-viento, posible media horaria y desfase térmico local. | §4.7, §4.3.5 | tipos, numerico, constantes, tablas, lineas_fisicas, lineas_registro (j* de E2 por versión, ola 3) |
| `red.py` | A1 a A6 y el resumen de A7; `fijar_a4`; muestras de A3 y A5; calibración de E3t; G-dup; cambio del portal; descripción de la red; predicciones de §1.13 (ola 4b, RED-10). | §5.4, §4.3.3, §1.13 | tipos, numerico, umbrales, constantes, tablas, lineas_fisicas, lineas_registro (clase de E2, id de evento y resultado de E1b, para §1.13) |
| `decision.py` | §5.1 en dos pasadas, §5.3, diagnóstico de reglas vencidas y muestra de expedientes de control. | §5.1, §5.3, §4.1.4, §5.5 | tipos, estados, umbrales, constantes, numerico, tablas, lineas_fisicas |
| `politica.py` | Bordes civiles, tramos, `source`, JSON de §7.2, el «reloj» de `estaciones` (`reloj_de_rachas`, la regla única de ORQ-7 y SAL-11, ola 4b), las siete comprobaciones de §7.3 (A7) y `validar_regla_reloj_dmc`. | §7.1 a §7.3, §7.5 | entorno, fijados, tipos, constantes, tablas |
| `orquestacion.py` | Fases 4 a 10 de §5.2, comunes a `--aplicar`, a la batería D y a C3b/C3c. Fase 4 por estación, en streaming; diagnóstico de reglas vencidas; comparación con E3t restringida; contexto y verificador de §7.3; entradas desde los extractos. | §5.2 | los de ciencia (tablas, estados, lineas_registro, lineas_fisicas, guardas, red, decision, politica), más extraccion (leer extractos y meses, coordenadas inconsistentes), fijados (huella del adaptador), constantes, tipos y umbrales |
| `salidas.py` | Tablas e informe de §7.4, `artefactos_evaluados.json.gz`, expedientes, privacidad, sello `recibo_corrida.json`; desviaciones automáticas (SAL-21 y SAL-22). | §7.4, §5.5, §7.1, §10 | entorno, tipos, decision (muestra de control), politica (política, «reloj» y nombres publicados), red (A7). `ResultadoRed` se lee por atributos: orquestacion sólo se importa para las anotaciones (`TYPE_CHECKING`) |
| `sintetico.py` | Generadores independientes, fabricación con el formato real (`run_download` con cliente y guarda falsos), `SerieEra5Memoria`, ISD sintético e ida y vuelta. **No importa el paquete.** | §8 (reglas comunes) | — (sólo la biblioteca estándar, numpy y pandas). El descargador y el adaptador llegan como argumento, cargados con `fijados` por quien llama. Copia los esquemas del extracto, de los meses y del ISD, y `test_sintetico` los compara con `tipos` |
| `bateria.py` | `bateria_v1.csv`, redes, corrida, criterios por celda, tiempo y §8.F. | §8.D, §8.F | sintetico, orquestacion, umbrales, constantes, tipos, entorno, extraccion, fijados, politica, tablas (estado del 2026-10-24, en implementación en la ola 4b) |
| `controles_era5.py` | C3a, C3b y C3c sobre ERA5-Land real. | §8.E | extraccion, numerico, orquestacion, sintetico, umbrales, constantes, tablas, tipos, entorno, fijados (adaptador y descargador), politica (política en memoria e ida y vuelta) y guardas |
| `verificar_reloj_dmc.py` | Ejecutable con `--sintetico`, `--control-era5` y `--aplicar`: rechazos de C4, C2 con candado retenido, cerrojo `intentos_aplicar.jsonl`, `avance.jsonl`, consola sin veredictos, carpeta HUMAN…, orden de §5.2 y sello. | §9, §10, §3.1, §7.1 | bateria, controles_era5, salidas, orquestacion, red, politica, extraccion, fijados, tablas, umbrales, constantes, entorno (estado del 2026-10-24, en implementación en la ola 4b) |
| `reloj_dmc.py` | Fachada perezosa con los 23 nombres de §9, en su orden (`NOMBRES_9`; «e4» es `lineas_fisicas.e4p`): importarla no carga nada del paquete, y cada nombre se resuelve una vez con `importlib`. | §9 | — (importa su módulo al pedir cada nombre) |

**Grafo, sin ciclos:**

```
tipos, entorno, constantes, umbrales
  → fijados, numerico, estados, tablas
  → extraccion, lineas_registro, lineas_fisicas, politica
  → guardas, red, decision
  → orquestacion
  → salidas, bateria, controles_era5
  → verificar_reloj_dmc
```

Así quedó en la ola 4b (2026-10-24), calculado por AST de las importaciones `reloj_dmc.*`: cada módulo depende sólo de los de capas anteriores, sin ciclos. Las dependencias que agregaron las olas 3 y 4 son guardas → lineas_registro, red → lineas_registro, orquestacion → extraccion y fijados, salidas → decision, politica y red, y controles_era5 → fijados, politica y guardas. `umbrales` no importa `entorno`, y `tablas` no importa `fijados`: recibe `MACROZONA_REGION` como argumento. salidas sólo nombra a orquestacion en anotaciones. `reloj_dmc.py` (la fachada) no importa nada al cargarse.

`sintetico` no importa el paquete y queda fuera del grafo (lo verifica una prueba por AST). Copia los esquemas de `tipos` (`ESQUEMA_EXTRACTO_HORA`, `ESQUEMA_MES` y `ESQUEMA_ISD`) y `test_sintetico` comprueba que coincidan. El descargador y el adaptador fijados le llegan como argumento (`ModuleType`), cargados con `fijados` por quien llama.

---

## 2. Estructuras de datos

**Manda `tipos.py`.** Lo de aquí es su resumen. `tipos.validar_esquema(df, ESQUEMA_*, nombre=…)` exige columnas, orden y tipos exactos en cada frontera entre módulos.

### 2.1 Identificadores

| Objeto | Identificador | Ejemplo |
|---|---|---|
| Estación | `codigo`, 6 dígitos (texto) | `"330020"` |
| Año | `anio`, año de etiqueta (int16) | `2019` |
| Mes | `"AAAA-MM"` | `"2019-09"` |
| Parte | `"AAAA-MM-n"`, n ≥ 1 en orden de etiqueta; es el `<unidad>` de la semilla | `"2019-09-2"` |
| Año-régimen | `"R0"` (contiene el 1 de enero) o `"R1"` | `"R1"` |
| Evento | `"<zona>|<AAAA-MM-DD>|<tipo>|<clase_evento>"` | `"America/Santiago|2019-09-08|adelanto|real"` |
| Hipótesis F(c) | `"F(c)"`, con signo explícito salvo en 0 | `"F(0)"`, `"F(-4)"`, `"F(+1)"` |
| Hipótesis C(Z) | `"C(<abreviatura>)"`; abreviaturas de §2.1; Pascua va completa | `"C(Santiago)"`, `"C(Pacific/Easter)"` |
| Reglas vencidas | `"Cv(<abreviatura>)"`; el año va en la unidad | `"Cv(Santiago)"` |
| Clase fusionada | ids de los miembros en orden canónico, unidos por `|` | `"F(-3)|C(Santiago)"` |
| Tramo | `"<racha>.<k>"` (R-25) | `"1.1"` |

- **Orden canónico.** Primero las F, por desfase descendente (0, −3, −4, −5, −6; las de fuera de P, en su lugar). Luego las C, en el orden Santiago, Coyhaique, Punta_Arenas, Pacific/Easter. Al final las Cv.
- **Errores.** `Hipotesis.desde_id("C(America/Easter)")` lanza error (prueba 4).
- **Rachas.** Las clases de dos años se comparan por la intersección de los ids de sus miembros (`tipos.interseccion_de_clases`).
- **Estados.** Las líneas evalúan **hipótesis**, nunca clases. `decision` convierte a clases con `estados.estado_de_clase`, que exige que los miembros coincidan; si no coinciden, lanza `ErrorFusion`, porque es un error de implementación (R-10).

### 2.2 Enumerados (`StrEnum`, se guardan como texto)

- `Estado`: `compatible`, `incompatible`, `dudosa` y `sin_informacion`. Aparte va `Senal`: `ninguna` o `reloj_anomalo`. El reloj anómalo es una señal de la unidad, adicional al estado por H (§4.0); en las tablas largas es la columna booleana `reloj_anomalo`.
- `Familia`: `registro`, `termica`, `presion_reanalisis`, `presion_marea`, `externa`, `documental`, `guarda` y `marca`.
- `Linea`: `E1a`, `E1b`, `E1c`, `E2`, `E3t`, `E3p`, `E4p`, `E6`, `E5`, `E3d`, `P7`, `T-P`, `E4t`, `G-version`, `G-HR` y `G-viento`. Las propiedades de cada una están en `tipos.LINEAS`: familia, Q, no térmica y si excluye.
- `Nivel`: `evento`, `parte`, `mes`, `regimen`, `anio` y `estacion`.
- `Regla`: `unica`, `gruesa` y `fina`.
- `Veredicto` por año: `confirmado`, `discrepante`, `insuficiente`, `sin_datos` y `sin_confirmar` (este último después de §5.3 o de A6). `MotivoAnio`.
- `VeredictoEstacion`: `confirmada` y `sin_confirmar`.
- `Conjunto`: V, V2 y N. `Territorio`: 7 valores. `ModoE3t`: `restringido` y `completo`. `ResultadoGuarda`: `pasa`, `falla` y `no_evaluable`. También `ResultadoEvento`, `ClaseEvento` y `MotivoSinInfo`.

### 2.3 Tablas

**Extracto estación-hora** (`extractos/dmc/<código>.parquet`, `ESQUEMA_EXTRACTO_HORA`). Una fila por etiqueta de un artefacto evaluado, ordenada por L y sin duplicados.

| columna | tipo | contenido |
|---|---|---|
| `L` | datetime64[ns] ingenuo | `timestamp_source` |
| `anio`, `mes` | int16, int8 | de L |
| `id_artefacto` | int32 | índice en `artefactos_evaluados` |
| `medida` | bool | H(L) = 1 (§3.2) |
| `ts`, `qfe` | float64 | NaN si falta o si lo descartó el control propio |
| `motivo_ts`, `motivo_qfe` | int8 | `CODIGOS_DESCARTE`: 0 válido, 1 ausente, 2 centinela, 3 rango, 4 mediana, 5 racha |
| `td`, `hr`, `ff_kt`, `dd_grados` | float64 | numéricos sin control propio, salvo el viento |
| `viento_valido` | bool | dirección en 0-360 y rapidez ≥ 0 |
| `qff_numerica` | bool | para H(L) |
| `rr`, `tx`, `tn`, `observador` | bool | marcas de §3.2 |
| `huella` | string | sha256 hex de los 21 textos crudos |

**Anotación** (`tablas.anotar_partes` → `ESQUEMA_ANOTACION`): `parte` (string), `regimen` (string o NA en una astilla de borde; R-08) y `especial` (bool: etiqueta repetida o inexistente de alguna zona de Zs). Todas las líneas reciben el extracto **anotado**.

**Meses** (`extractos/dmc/meses.parquet`, `ESQUEMA_MES`). Una fila por manifiesto considerado, entre o no. Columnas:
- identificación: código, año, mes, manifiesto (por alias), su sha256, sha256 del artefacto, `id_artefacto` y `script_sha256`;
- admisión: `entra` y `motivo_exclusion`;
- campos del manifiesto: `row_count`, `source_empty_slots`, `expected_hour_slots`, `n_available_hours`, `duplicate_display_rows_removed`, `source_sha256` y `requested_start/end`;
- `campos_faltantes`;
- `p_ts` y `p_qfe`;
- textos de coordenadas del artefacto, para §3.1.

**Estaciones** (`ESQUEMA_ESTACIONES` = `pixeles_dmc.parquet` de §7.4, ampliado):
- código, nombre, lat, lon, `alt_m` (z_cat);
- `coordenadas_validas` y `coordenadas_inconsistentes`;
- territorio, región, macrozona, Zs y P;
- `pixel_id`, `distancia_km`, `costera`, `z_pix` y `dz`;
- conjunto, tipo, propietario, OMM y OACI.

En memoria es `tipos.InfoEstacion`.

**Píxel-hora ERA5-Land** (`extractos/era5/`):
- `serie.f4`: float32 mapeado en disco, de forma (n_píxeles_enlazados, n_horas, 4) y variables en el orden (`t2m` °C, `sp` hPa, `u10`, `v10`) m/s;
- eje UTC global horario desde `t0` = 2000-01-01T00Z hasta 2026-09-15T23Z (~234 mil horas; ~3,7 MB por píxel);
- `indice.json`: `t0`, `n_horas`, `variables`, `pixel_ids` (orden de filas) y `meses` (por AAAAMM: sha256, `eje_ok`, medianas de t2m en K y de sp en Pa, `unidades_ok`), más `validos` y el sha256 de `catalogo_pixeles`;
- interfaz: `tipos.SerieEra5` (`valores(pixel_id, variable, u)` devuelve float64 con NaN fuera del eje). Las diferencias en los bordes de mes salen solas del eje global, que cumple «los dos días vecinos de cada mes» (§3.4).

**Partes y años-régimen.** No se guardan como tablas propias: los definen `tablas.partes_del_mes` y `tablas.regimenes_del_anio` y van como `unidad`/`regimen` en las métricas. Las métricas por unidad (`nivel` ∈ {parte, regimen}) son:
- `ESQUEMA_METRICAS_E2`: n_rr, frac_observador, valida, informativa, j*, κ3 y TX/TN;
- `ESQUEMA_METRICAS_E3`, una fila por unidad y variable Ts/QFE:
  - `paso_h`, `n_pares` y `n_bloques`;
  - `r` (lista de 19 float64, c = −9…9), `c_hat`, `c_hat_cont` y `estab_c_hat`;
  - `r_f`, `c_hat_f`, `c_hat_f_cont` y `estab_c_hat_f`;
  - `fino`, `filtro_e3t`, `cociente_a1` y `r_diaria`;
- `ESQUEMA_METRICAS_E4`: n_h, hueco máximo, K, A1, EE_A1, φ1, A2, EE_A2 y ψ2.

`evidencia_estacion_parte.parquet` (§7.4) es su unión en el nivel parte, más los estados por H y las partes discordantes.

**Estados por línea, H y unidad** (`estados_largos.parquet`, `ESQUEMA_ESTADOS`). Es la estructura central que intercambian las líneas y la decisión.

| columna | tipo | contenido |
|---|---|---|
| `codigo`, `anio` | string, int16 | |
| `linea` | string | `Linea` |
| `regla` | string | `Regla`: `gruesa`/`fina` en E3p y E3t; `unica` en el resto |
| `nivel` | string | `Nivel` |
| `unidad` | string | parte, mes, régimen, `"AAAA"`, `"*"` o id de evento |
| `H` | string | id de **hipótesis** |
| `estado` | string | `Estado` |
| `reloj_anomalo` | bool | señal de la unidad, repetida en cada H |
| `discordante` | bool | parte o mes discordante (§4.0) |
| `motivo` | string | `MotivoSinInfo` u otro texto corto |

Otras tablas:
- **Guardas** (`ESQUEMA_GUARDAS`): código, año, guarda, H, unidad, resultado y detalle. Se precalculan para toda H de P en la fase 4.
- **Marcas** (`ESQUEMA_MARCAS`): código, año, marca, H y valor.
- **Eventos** (`ESQUEMA_EVENTOS` → `eventos_transicion.csv`): E1a, E1b, E1c, placebos y reglas vencidas.
- **Horas** (`ESQUEMA_HORAS`): las estación-horas con Ts o QFE por mes, denominadores de §5.4.
- **ISD** (`ESQUEMA_ISD`): código, u, `tipo_parte` y tmp.
- **Rachas** (`ESQUEMA_RACHAS`).

**Objetos que cruzan fases:**
- `ContextoEstacion`: info, tablas, umbrales, años con datos, regímenes, regímenes con datos, clases por año, meses con datos, líneas activas y la opción de exclusión costera. Lo arma `orquestacion.contexto_estacion` y es la entrada común de toda línea.
- `ResultadoLinea`: línea, estados, métricas y eventos. Es la salida común de toda línea.
- `EvidenciaEstacion`: todo lo de la fase 4 de una estación. Basta para las fases 5 a 10 sin volver a leer extractos; sólo `politica` vuelve a leer la columna L para los tramos y la conversión exhaustiva.
- `ConsecuenciasRed`: A3 en el país y por macrozona, A5, modo de E3t por macrozona y A4.
- `DecisionAnio`: la traza de §5.1, que va a `evidencia_estacion_anio.parquet`.
- `Tramo`, y `orquestacion.ResultadoRed`.

### 2.4 Quién produce y quién consume, por fase de §5.2

| Fase | Produce | Módulo | Consume |
|---|---|---|---|
| 1. C2 y huellas | `EstadoC2`, candado tomado, huellas de entrada | verificar_reloj_dmc, extraccion | — |
| (A2 antes de leer) | huellas de los Anexos A y A2 | tablas, red.a2 | — |
| 2. ERA5-Land | `SerieEra5Mapeada`, `ControlMesEra5` por mes (A1) | extraccion | catálogo DMC (coordenadas → píxeles) |
| 3. Extracción DMC | extractos, meses, `artefactos_evaluados` y `InfoEstacion` | extraccion | manifiestos y artefactos |
| 4. Estados de las líneas | `EvidenciaEstacion` por estación | orquestacion → lineas_*, guardas | extractos y serie |
| 5. A3, A5 y calibración | `ConsecuenciasRed` (sin A4) | red | evidencias |
| 6. Pasos 1 a 6 | `DecisionAnio` parciales | decision | evidencias y consecuencias |
| 7. A4 | `a4_restringe` | red | decisiones parciales |
| 8. Pasos 7 a 9 | `DecisionAnio` finales | decision | lo anterior |
| 9. Rachas y meses con regla | `ResultadoRachas` | decision | decisiones y meses |
| 10. Política y §7.3 | tramos, política, fallas A7 | politica | rachas, columna L, código fijado |
| 11. Sello | tablas, informe, recibo | salidas | todo |

---

## 3. Firmas

Las firmas exactas están en el código y en el **Anexo F** de este documento, regenerado por AST del código en la ola 4b (el de la ola 0 salía del esqueleto). Estas son las decisiones de interfaz que más importan:

- **Las líneas nunca leen archivos.** Reciben el extracto anotado, la `SerieEra5` y el `ContextoEstacion`, y devuelven un `ResultadoLinea`. Así son puras y las pruebas les pasan DataFrames hechos a mano.
- **La E3p anual, que combina la gruesa con la fina, no la calcula la línea.** La calcula `lineas_fisicas.e3p_anual`, llamada desde `decision` después de A3. El orden de §5.2 pone A3 después de los estados, y A3 puede apagar la regla fina.
- **Las guardas y marcas que dependen de H se precalculan para toda H de P.** Así la decisión no vuelve a abrir extractos. El paso 5 sólo consulta la de K = {H}, y T-P aplica en `decision` sus condiciones de año: K = {H} y E3p compatible.
- **G-versión necesita E3p y E2 por versión.** Lo arma `guardas.resumen_por_version` desde el extracto y los meses; `guardas.g_version` sólo compara.
- **`orquestacion.evaluar_red(entradas, …)` recibe una fábrica de entradas.** Recorre las estaciones una por una (memoria < 4 GB) y puede recorrerlas otra vez para el diagnóstico de reglas vencidas y para la columna L de los tramos.
- **`politica.validar_regla_reloj_dmc(regla, artefacto_sha256, *, politica_ruta=None)`** conserva la firma de §7.3. El argumento extra es sólo de palabra clave y, por omisión, apunta a la política publicada en AP.
- **`fijados.cargar_preflight` agrega `v3/` a `sys.path` sólo durante la importación.** Se comprobó que importar `preflight_v3` no trae `_comun_modelo`, no toca `/Volumes` y tarda ~1,3 s. Efecto conocido: `runner_v3` fija a 2 los hilos de OMP, BLAS y pyarrow.
- **`fijados.transiciones_sinca` extrae la función por AST** (prueba 3), porque `verificar_reloj_sinca.py` importa `_comun_modelo`.

---

## 4. Umbrales: lectura y comparación en C1

**Tres fuentes, sin solape:**

1. **23 ajustables**, de `reloj_dmc_v1.json["ajustables"]`. `U.a("E3P_MU")` devuelve el valor vigente: el anclado o el que dejó §8.F. Los pares vuelven como tupla: `E1B_PATRON` = (0,75; 2), `E6_I12` = (0,6; 5) y `E6_I15` = (0,8; 2).
2. **124 fijos**, de `reloj_dmc_v1.json["fijos_texto"]`, que son el texto literal del Anexo B.
   - `umbrales.PLANTILLAS_FIJOS` tiene una plantilla por línea (33). Cada `{ID}` es un número escrito como en el texto: signo «−» (U+2212), miles con «.» y decimales con «,».
   - `traducir_fijos` construye la expresión regular de cada plantilla y exige `re.fullmatch` sobre su línea. Si el texto cambia fuera de los números, la traducción falla en vez de desviarse.
   - `U.f("TS_CENTINELA")` → −40.0. `U.frac` sólo vale para los ids `*_PCT` (`U.frac("A4_PCT")` → 0,10).
3. **Constantes del cuerpo** que no están en el Anexo B (53, en `constantes.py`). Cada una lleva su sección y un fragmento literal. `verificar_contra_texto` exige que el fragmento esté tal cual en el texto anclado y que sus números coincidan con el valor. No se ajustan por §8.F (R-17).

**Cómo C1 compara el JSON con el Anexo B** (`test_umbrales.PruebasC1Umbrales`):
1. `regenerar_desde_texto(texto_v1.1)` rehace el JSON con el mismo algoritmo que `c0/preparar_c0.anexo_b`: tabla de ajustables por «→» y lista de líneas «- » de «**Fijos**».
2. `comparar(publicado, regenerado)` debe dar `[]`. Sólo ignora `CLAVES_AJENAS_AL_ANEXO_B = ("bateria",)` (R-04).
3. `traducir_fijos` sobre los `fijos_texto` publicados debe dar los 124 ids sin error.
4. `constantes.verificar_contra_texto(texto_v1.1) == []`.
5. Una prueba AST busca en los módulos los literales numéricos que coinciden con valores del Anexo B y los rechaza fuera de `umbrales.py`, con una lista blanca explícita de constantes matemáticas: 0, 1, 2, 12, 24, 60, 3600, π. Es heurística: no detecta umbrales que coinciden con la lista blanca (por ejemplo, 2, 12 o 24), y su lista se revisa en la revisión de C1.
6. El sha256 del JSON y del texto v1.1 van al addendum de C1. `cargar_umbrales(…, sha256_json=…)` lo exige en `--aplicar`.

**§8.F.**
- `umbrales.FILAS_POR_LINEA` da las filas de cada línea en el orden del Anexo B.
- `siguiente_ajuste(U, línea)` devuelve el primer id cuya lista no esté agotada. Una línea sin filas (E3d, P7, E4t o G-versión) está agotada desde el principio, y eso hace fallar C1.
- `U.ajustado(id)` mueve un paso; nunca hacia lo menos conservador.
- `bateria.ajustar_umbrales` registra cada iteración: fecha UTC, motivo, umbral y sha256 de la salida de la batería.

---

## 5. Plan de pruebas

### 5.1 Puntos 1 a 28 de §8

En los nombres de las pruebas, «pNN» es el punto de §8. `test_reloj_dmc.test_indice_de_8_cada_punto_tiene_prueba` comprueba que cada punto de 1 a 28 tenga al menos una.

| § 8 | Qué | Módulo | Archivo y pruebas |
|---|---|---|---|
| A.1 | Signo; −240.0 rechazado | politica (+ adaptador) | `test_politica.PruebasGrupoA1` (2) |
| A.2 | Anexo A con tzdata y con el sistema; tabla alterada → A2; A2 desde sus reglas | tablas (+ red.a2) | `test_tablas.PruebasGrupoA2` (4); `test_red.test_a2_desde_huellas` |
| A.3 | Precedente SINCA | tablas + fijados | `test_tablas.test_p03_…`; `test_fijados.test_transiciones_sinca_por_ast_sin_importar` |
| A.4 | Fusiones; «America/Easter» | tablas, tipos | `test_tablas.PruebasGrupoA4` (4); `test_tipos.test_p04_america_easter_da_error` |
| A.5 | Territorio y P; vecino a ≤ 15 km y costera; Antártica; `cod_comuna = 0`; coordenadas no interpretables; inconsistentes | tablas, extraccion, lineas_fisicas | `test_tablas.PruebasGrupoA5Territorio`; `test_extraccion.test_p05_…` (3); `test_lineas_fisicas.test_p05_…` |
| A.6 | Bordes de tramo e ida y vuelta 2000-2026 en cuatro zonas | politica | `test_politica.PruebasGrupoA6` (5) |
| A.7 | Semilla y bloques | numerico | `test_numerico.test_p07_…` (2) |
| B.8 | E1a; diagnóstico de reglas vencidas | lineas_registro, decision | `test_lineas_registro.PruebasE1a` (5 pNN); `test_decision.test_p08_diagnostico_reglas_vencidas` |
| B.9 | E1b (signos, cambio administrativo); E1c | lineas_registro | `test_lineas_registro.test_p09_…` (3) |
| B.10 | E2 | lineas_registro | `test_lineas_registro.test_p10_…` (6) |
| B.11 | E3 | lineas_fisicas | `test_lineas_fisicas.test_p11_…` (6); el alias tiene la contradicción R-01 |
| B.12 | Regla fina; marca de media horaria | lineas_fisicas, guardas | `test_lineas_fisicas.test_p12_…` (2); `test_guardas.test_p12_marca_posible_media_horaria` |
| B.13 | E4; ecuación del tiempo | lineas_fisicas, numerico | `test_lineas_fisicas.test_p13_…` (2); `test_numerico.test_p13_ecuacion_del_tiempo_tabulada` |
| B.14 | Guardas y marcas | guardas | `test_guardas.test_p14_…` (8) |
| B.15 | E6 con ISD sintético | lineas_fisicas | `test_lineas_fisicas.test_p15_…` |
| C.16-23 | Decisión de punta a punta | orquestacion (+ decision, red) | `test_orquestacion.PruebasGrupoC` (10); unitarias `test_decision.test_p19_…`, `test_p20_…`, `PruebasP21.test_p21_…` (con `lineas_fisicas.e3p_anual` real; Enmienda 3, R) y `test_red.test_p22_…` |
| C.24 | Cuatro plantillas −240 | politica | `test_politica.test_p24_…` (las 4 reglas `clock` copiadas como datos con su cita archivo:línea, sin importar esos archivos) |
| C.25 | `timezone` con hora ambigua | politica | `test_politica.test_p25_…` |
| C.26 | Determinismo y cerrojo | verificar_reloj_dmc | `test_verificar_reloj_dmc.PruebasGrupoC26` (2) |
| C.27 | Ceguera: raíz falsa y gancho de auditoría sobre `open`, `os.stat` y `os.lstat`; sin `_comun_modelo` ni `_common` | verificar_reloj_dmc | `test_verificar_reloj_dmc.PruebasGrupoC27` (2) |
| C.28 | Sin «/Users/» ni «@»; sin `.pyc` en los repositorios | salidas, verificar_reloj_dmc | `test_salidas.test_p28_…`; `test_verificar_reloj_dmc.test_p28_…` |

**Datos.**
- Los grupos A a C fabrican sus datos con `sintetico.fabricar_descarga`: `run_download` del descargador vigente, con `ClienteFalso` y `GuardaFalsa` (`defer_heavy_checks = True`, como `scripts_pipeline/tests/test_meteo_chile_horaria.py`), siempre en `tempfile.TemporaryDirectory`.
- La ida y vuelta se comprueba con `sintetico.comprobar_ida_y_vuelta(política, casos, adaptador)` en todo caso de los grupos B a E. Las pruebas del grupo B pasan también por la política (R-34).

### 5.2 Comprobaciones propias de C1 (fuera de la numeración de §8)

- `test_umbrales.PruebasC1Umbrales` y `PruebasAjuste8F`: JSON contra Anexo B, fijos, constantes, literales y §8.F.
- `test_fijados.test_c1_huella_ruta_etiqueta_seis_admitidas` y `test_c1_versiones_halladas_por_el_inventario`. Es la comprobación mecánica del Anexo C para fc1f1bb6 y 975d9bf0, halladas por el inventario en `APH/tmp/…`; su resultado va al addendum de C1. Si el archivo falta, la prueba se omite con el motivo y no se da por aprobada.
- `test_reloj_dmc`: la fachada y el índice de §8 (ola 4b).
  - La fachada: los 23 nombres se leen de §9 del texto anclado en C0 y deben ser los de `NOMBRES_9`, en su orden; cada uno es el mismo objeto de su módulo, y la importación es perezosa (se comprueba en un intérprete aparte).
  - El índice: la numeración 1 a 28 se lee de §8 del texto anclado, y cada punto debe tener al menos una prueba «pNN» (AST de `tests/`). Otra prueba exige que ningún punto dependa sólo de pruebas del esqueleto (`unittest.skip(POR_IMPLEMENTAR)`); se omite, con la lista, mientras esos pendientes estén sólo en archivos de `EN_CURSO` (hoy `test_verificar_reloj_dmc.py` y `test_bateria.py`), y falla en cualquier otro. Al cerrar C1, `EN_CURSO` queda vacía.

### 5.3 Batería D

1. **Tabla.** `bateria.tabla_bateria()` genera `bateria_v1.csv` de forma determinista, con las columnas `COLUMNAS_BATERIA`:
   - caso, bloque, celda, reloj verdadero por etiqueta (especificación por tramos de u) y si está fuera de P;
   - tipo a-g, escenario, territorio, lat/lon, píxel y cod_comuna;
   - perturbación y su valor, red, réplica y semilla.
   - D1: 20 réplicas. D2: 10, con una perturbación a la vez. D3: 10.
   - Su sha256 va a `reloj_dmc_v1.json["bateria"]` (R-04) y al addendum. El diseño factorial exacto está en R-29.
2. **Redes.** Cada combinación de sesgo de referencia (0, −2, +1, +2,5 h) y réplica forma una red con todas sus estaciones. La calibración de E3t y A3 a A5 se calculan dentro de cada red.
3. **Corrida.** `correr_red` llama a `orquestacion.evaluar_red` con `sintetico.entrada_en_memoria` y `SerieEra5Memoria`. Las líneas son las de C0: sin E5 ni E6, salvo en D3, que activa E6.
4. **Criterios por celda** (`criterios_por_celda`; celda = combinación de factores sin la réplica):
   - cero confirmaciones erróneas (`es_confirmacion_erronea`: distinta en alguna etiqueta del año, verdadero fuera de P o cualquier confirmación en el tipo g);
   - semánticas de ±0,5 h: correctas sólo con la marca, en ≥ 90 %;
   - sensibilidad ≥ 0,80 por reloj en las celdas de referencia (`CELDAS_REFERENCIA`), y la civil ≥ 0,8 × F(0);
   - confirmación correcta ≥ 90 % en los tipos a y b con QFE y RR06, |sesgo| ≤ 1 h y datos completos o con 30 % faltante;
   - sin cruces entre fijo y civil;
   - el cambio de 2018 ubicado en 2018;
   - el tipo e, Pascua y Juan Fernández, sin confirmar. Con la Enmienda 4 del reloj (v1.0.4, E4-1) el tipo f sale de la lista: puede confirmarse, y sus confirmaciones erróneas cuentan en «cero erróneas» (BAT-7; con el v1.0.3 decía «los tipos e y f»).
   - Pérdidas por celda: años falsamente discrepantes y estaciones perdidas por inestabilidad.
5. **Tiempo.** `correr_bateria` devuelve las horas de cómputo medidas, que se registran antes de C1. Si pasan de 48 h, `replicas_por_tiempo` baja D2 y D3 a 5 réplicas y se regenera la tabla; el núcleo nunca baja.
6. **§8.F.** `ajustar_umbrales`.
7. **Salidas.** `verificar_reloj_dmc.py --sintetico --bateria` escribe en `LOCAL/modelado_1km/verificacion_reloj_dmc/v1/c1/` (R-32):
   - `bateria_v1.csv`, `resultados_bateria.parquet`, `criterios_bateria.json`, `tiempo_bateria.json` y `registro_8F.jsonl`;
   - la salida de `unittest` (`pruebas_c1.txt`).
   Sus sha256 van al addendum de C1.

### 5.4 C3 (`--control-era5`)

- `controles_era5.c3a/c3b/c3c` sobre ERA5L real, antes de C4, sin descargas activas y sin abrir nada bajo DMC (`test_c3_no_abre_la_dmc`, con registro de `open`).
- Las pruebas unitarias usan series sintéticas con fases conocidas.
- La salida va a `LOCAL/…/v1/c3/` con sus sha256.
- Si C3a falla, se enmienda; la constante de 9,75 h nunca se reemplaza sola (prueba `test_c3a_no_reemplaza_la_constante`).

---

## 6. Orden de implementación y dependencias

| Ola | En paralelo (un dueño cada uno) | Necesita | Entrega verificable |
|---|---|---|---|
| 0 (hecha) | `tipos` (estructuras), firmas y nombres de pruebas | — | este esqueleto |
| 1 | **I1** entorno + fijados · **I2** umbrales + constantes · **I3** numerico + estados + métodos de `tipos` (`id`, `desde_id`, `orden`, `validar_esquema`, `ConsecuenciasRed`) · **I4** tablas | sólo ola 0 (I4 puede simular `fijados.macrozona_region`) | pruebas de A.2, A.3, A.4, A.5 (territorio), A.7 y C1 de umbrales |
| 2 | **I5** sintetico · **I6** extraccion · **I7** lineas_registro · **I8** lineas_fisicas · **I9** politica · **I10** decision | ola 1; entre sí sólo por firmas: decision usa `lineas_fisicas.e3p_anual`, que se simula hasta que I8 lo entregue | grupos A.1, A.5 (píxel), A.6, B.8-B.13 y B.15; unitarias de decision |
| 2b | **I11** guardas · **I12** red | `lineas_fisicas.pares_e3`/`ajustes_e4`/`e3p_anual` (firmas fijas; se simulan) | B.14, A3/A5/calibración y unitarias de red |
| 3 | **I13** orquestacion (integración) · **I14** salidas · **I15** controles_era5 | olas 1 y 2 | C.16-C.23, C.28 (salidas) y C3 sintético |
| 4 | **I16** verificar_reloj_dmc · **I17** bateria | ola 3 | C.24-C.27, batería D medida, §8.F, addendum de C1 |

- **Camino crítico:** `tablas` → `lineas_fisicas` → `orquestacion` → `bateria`. Conviene darle `lineas_fisicas` a quien tenga más experiencia con E3 y E4, porque es el módulo más pesado y el de mayor costo de cómputo (200 réplicas por unidad).
- **Hitos de integración:**
  1. Una estación sintética F(0) de punta a punta (prueba 16) con líneas simuladas.
  2. La misma con líneas reales.
  3. Los casos 17 a 23.
  4. Una red de batería pequeña, para medir el tiempo y extrapolarlo a la batería completa antes de correrla.
- **Revisión de C1:** un revisor que no implementó el módulo lo contrasta con el texto, sección por sección. Sobre todo §4.3 (E3), §5.1 y §5.3, y las lecturas de §7 de este documento.

---

## 7. Riesgos de interpretación

**Marcas:**
- **[E]**: requiere enmienda antes de C4 (el texto no basta o se contradice).
- **[D]**: lectura propuesta que debe fijarse y registrarse en el addendum de C1 como cambio de implementación. Si el autor la considera un cambio de regla, pasa a [E].
- **[M]**: menor; la lectura propuesta basta y se documenta.

**CONTRADICCIÓN** señala una contradicción real dentro del texto, que este diseño no resuelve.

### 7.1 Contradicciones y puntos que requieren enmienda

- **R-01 [E] CONTRADICCIÓN.** La prueba 11 de §8 dice «−8 con F(−4) en P es alias de 12 h, no reloj anómalo». Pero según §2.1 (c = L − u) y la definición de §4.3.1 (ĉ ≡ c_H mód 12), el alias de −4 dentro de [−9, 9] es **+8**; −8 sería el alias de +4. Con la definición, ĉ = −8 en P continental da reloj anómalo.
  - Una de las dos frases está mal, y la prueba no puede pasar contra la definición tal como está escrita.
  - El esqueleto implementa la definición (`numerico.es_alias_12`) y deja la prueba nombrada con la nota.
- **R-02 [E] CONTRADICCIÓN.**
  - §4.3.3 dice «Su incompatibilidad [de E3t] se calcula sólo para T-P y para el informe».
  - Pero el modo completo (§4.3.3 y §5.1, paso 7) exige que una línea de apoyo sea incompatible con una rival de R_min(H). Sin su incompatibilidad, E3t nunca podría apoyar.
  - Lectura propuesta: «nunca excluye» se refiere sólo al paso 3. En modo completo, su incompatibilidad se usa en el paso 7. Conviene una enmienda aclaratoria.
- **R-03 [M] CONTRADICCIÓN literal.** §4.3.2 dice que el reloj anómalo «incluye ĉ ≥ +1», pero ĉ = +8 y +9 son alias de −4 y −3 cuando éstas están en P. La regla formal los deja «sin información (alias)», no anómalos. Se implementa la regla formal.
- **R-09 [E]** Reglas vencidas (§4.1.4).
  - Para decidir si «agregar C_venc(Z, y) a P dejaría K = {C_venc}» hay que evaluar todas las líneas bajo una hipótesis cuyos cambios no caen en los cortes de Zs. Las partes no tienen desfase constante para C_venc, y r(H) = r(c_H(R)) no está definido para ella.
  - La marca cambia la cuenta de inestabilidad (§5.3.1) y, por tanto, confirmaciones de estaciones.
  - Lectura propuesta (`orquestacion.diagnostico_reglas_vencidas`): sólo en años del A2 y sólo para el diagnóstico, cortar además las partes en las etiquetas especiales de C_venc y evaluar las líneas con P ∪ {Cv}, con las mismas reglas. Conviene fijarlo por enmienda.
- **R-17 [D → E si hace falta mover alguno].** Hay umbrales del cuerpo que no están en el Anexo B. Ejemplos: los rangos de unidades de ERA5 (200-330 K y 40.000-110.000 Pa), «≥ 20 valores» por día, «≥ 3 días» de los placebos de E1a, «≥ 80 %» de ausentes, «≥ 2 meses» de E1c, «≥ 2 partes» de E2, P7 «presencia ≥ 0,8», G-HR «A1(Ts) ≥ 1 °C y A1/EE ≥ 3», E6 «0,05 °C», «|lat| ≤ 50°» de la regla fina y los cortes de territorio.
  - §0 dice que los umbrales «quedan fijos aquí, en el Anexo B».
  - Se tratan como constantes del texto, no ajustables (`constantes.py`, 53 entradas con su fragmento).
  - Si §8.F necesitara mover uno, no podría, y C1 fallaría hasta una enmienda.

### 7.2 Lecturas que deben fijarse en el addendum de C1 [D]

- **R-04.** §8.D pone el sha256 de `bateria_v1.csv` «en `reloj_dmc_v1.json`», pero §10 (C1) regenera ese JSON del Anexo B y lo compara. Propuesta:
  - una clave `bateria` (`{"archivo", "sha256"}`) fuera de la comparación;
  - `generado_desde` apunta al texto v1.1.
- **R-05.** No está dicho cómo queda el Anexo B de v1.1 después de §8.F. Propuesta: la fila muestra el valor vigente como anclado y sólo el resto de la lista, por ejemplo «0,05 → 0,08», y el registro de §8.F guarda el historial.
- **R-06.** El formato y la ruta de la «línea de cierre de la descarga» (C2) y del «addendum fechado» de C1 no están fijados, y el ejecutable debe leerlos. Propuesta:
  - `APH/auditoria/<fecha C2>/reloj_dmc/cierre_descarga.json`, con fecha, sha256 de `progreso.json`, firma y commit;
  - `APH/auditoria/<fecha C1>/reloj_dmc/addendum_c1.json`, con la lista cerrada `{ruta: sha256}` y `commit_c1`.
  - Ambos se pasan por argumento. Debe quedar fijado antes de C2.
- **R-08.** Las partes se cortan en «los instantes de cambio de hora», pero un instante UTC no corresponde a una sola etiqueta sin suponer un reloj. Lectura:
  - se corta en la **etiqueta especial civil** de cada cambio de cada zona de Zs. Así toda H tiene desfase constante dentro de cada parte;
  - con dos zonas de Zs cuyas etiquetas especiales difieren (Pascua: Pacific/Easter el sábado 21:00/22:00; Santiago el sábado 23:00 o el domingo 00:00), queda una **astilla** de 1 a 2 h cuyo vector de desfases no es ni el de R0 ni el de R1;
  - la astilla queda con `regimen = NA`: no entra en E2, E3, E4 ni las guardas, y se informa. Así cada año conserva dos años-régimen.
- **R-10.** «Las fijas» y «C(Z)» en E1a, E1b y E1c, cuando Zs tiene varias zonas o hay fusiones.
  - Lectura: el evento de la zona Z en la etiqueta h0 deja incompatibles a las H bajo las cuales h0 es inexistente, y compatibles a las demás. Por ejemplo, C(Coyhaique) en 2025 cuenta como fija, y C(Coyhaique) y C(Santiago) antes de 2024 caen juntas.
  - Varias sub-evaluaciones de una línea en un año se combinan así: incompatible > compatible > dudosa > sin información.
  - Así los miembros de una clase reciben siempre el mismo estado; si no, salta `ErrorFusion`.
  - **Enmienda 3 (2026-10-24), sólo en E1c:** la lectura se aplica mes por mes y no zona por zona (lectura 10 de `lineas_registro`, para el addendum): en la sub-evaluación de Z, una H con otra etiqueta inexistente en el mes queda sin información. E1a y E1b no cambian.
- **R-11.** E2, TX y TN: «con ≥ 10 marcas y κ3 ≥ 0,90 cada una, deben caer en j* …».
  - Lectura A (propuesta): la exigencia se aplica sólo si ambas alcanzan esos mínimos.
  - Lectura B (más conservadora): si no los alcanzan, la unidad pasa a dudosa.
  - Cambia resultados en las partes cortas.
- **R-12.** E3p, «cada desigualdad … en ≥ 99 % de las réplicas». Lectura:
  - cada condición de compatible o incompatible se cuenta por separado, y «r(H) es el máximo en P» cuenta como desigualdad;
  - en «existe H′», H′ se fija con la muestra completa y se exige su desigualdad en ≥ 99 % de las réplicas;
  - en el reloj anómalo, se exige el mismo ĉ en ≥ 99 % de las réplicas.
- **R-13.** Cadenas exactas que el texto no fija:
  - en la semilla, `<variable>` es `"Ts"` o `"QFE"`;
  - la huella de fila serializa los 21 textos con `json.dumps(…, ensure_ascii=False, separators=(",", ":"))` en el orden de `RAW_COLUMNS` sin día ni hora;
  - todo en UTF-8.
- **R-14.** La mediana del mes del control propio se calcula sobre los valores que pasan centinela y rango.
- **R-15.** «Racha de valores idénticos de 12 h o más»: valores iguales en etiquetas consecutivas al paso nativo (un hueco la corta), que cubren n·p ≥ 12 h (24 h en QFE).
- **R-18.** Los varios 0,8 y 80 % de E1a:
  - `E1A_P` (ajustable) se aplica a «p ≥ 0,8» del ausente y a «presencia esperada ≥ 0,8» de §3.5;
  - `E1A_DIA_HABITUAL` (fijo) se aplica a «≥ 80 % de sus etiquetas habituales» y a la «presencia ≥ 0,8» que define una etiqueta habitual;
  - P7 usa su propia constante del cuerpo;
  - «ausentes ≥ 80 % de los evaluables» es otra constante del cuerpo.
  - Si §8.F mueve `E1A_P`, no arrastra a las demás.
- **R-19.** E1b en aeródromos que operan pasada la medianoche (Copiapó, 11-00 h).
  - Las horas s_d y e_d se desenrollan respecto del fin del bloque nocturno.
  - El «día» operativo empieza después de ese bloque.
  - Las medianas se toman sobre las horas desenrolladas.
- **R-20.** sp̄ de z_pix es la media de todas las horas 2000-01 a 2026-09 del píxel.
- **R-23.** El armónico de 24 h de sp (serie filtrada) se ajusta sobre las horas UTC que la unidad usa, [mín L − 9 − p, máx L + 9]. El de QFE se ajusta sobre las etiquetas de la unidad.
  - **Reemplazada por la Enmienda 3, E3-1 (§4.3.1, adoptada el 2026-10-24):** el armónico de sp se ajusta para cada c sobre {L − c, L − c − p : L ∈ M}. Ya no es una lectura [D] (LF-2 de `lineas_fisicas`).
- **R-24.** Las etiquetas especiales de Zs se excluyen también de E2, E4 y las guardas, no sólo de las correlaciones. Así una hora ambigua no carga marcas a la clase equivocada.
- **R-27.** Si falla A3, E4p «deja de excluir y de ser Q»; no dice si puede seguir apoyando. Lectura: puede apoyar como línea de la familia presión-marea, no cuantitativa.
- **R-28.** E6 con FM-15. «Incompatible(H): otra H′ es compatible» no debe alcanzar a las rivales a 1 h cuando la compatibilidad vino sólo de FM-15. Lectura: sólo vuelve incompatibles a las H a ≥ 2 h.
- **R-29.** Batería: el diseño factorial de D1 no está explícito. Lectura:
  - cruce completo de relojes × tipos a-f × escenarios;
  - el tipo g, sólo con su par de relojes;
  - Pascua, sólo con los tipos que tengan sentido allí (a, b y e);
  - cada red (sesgo × réplica) junta todas las estaciones de esa réplica con ese sesgo de referencia; las de D2 sin sesgo van a la red de sesgo 0.
- **R-33.** La serie filtrada usa las mismas réplicas (misma semilla) que la serie sin filtrar.
- **R-34.** «Ida y vuelta en cada caso de los grupos B a E»: las pruebas de línea del grupo B no emiten política. Lectura: cada caso B también pasa por el pipeline y su política se somete a la ida y vuelta.
- **R-35.** §9 nombra un solo archivo, `reloj_dmc.py`, y `tests/test_reloj_dmc.py`. Se reparten módulos y se conserva la fachada con los 23 nombres. Va al addendum como cambio de implementación.
- **R-41.** El alcance de `E3_RMAX` (línea «E3p» en el Anexo B, pero id «E3_»). Lectura: vale para E3t, E3p (con y sin filtro) y para las muestras de A3 y A5; si §8.F lo mueve, se mueve en todas.
- **R-42.** Los bloques se cuentan desde el primer día **calendario** de la unidad (R0 no es contiguo). «≥ 6 bloques» cuenta los bloques no vacíos, y el remuestreo sortea entre bloques no vacíos.
- **R-52.** En «E3p anual», un año-régimen es «informativo» si la regla gruesa le da compatible o incompatible para H, o si es fino.
  - **Reemplazada por la Enmienda 3, opción R de E3-2 (§4.3.4 y §8.21, adoptada el 2026-10-24):** «informativo» es por año-régimen (la gruesa da compatible o incompatible a alguna H de P, o es fino), el mismo para todas las H. Ya no es una lectura [D] (LF-17 de `lineas_fisicas`).

### 7.3 Lecturas menores [M]

- **R-07.** §5.1, paso 1, dice «se aplican las consecuencias de A3 y A4», pero §5.2 calcula A4 después del paso 6. No hay efecto: A4 sólo restringe E3t, que importa en el paso 7.
- **R-16.** Para H(L) sólo hay centinelas en Ts (−40,0) y QFE (500,0). Td, HR, QFF y el viento no tienen centinela.
- **R-21.** Distancias por gran círculo con R = 6.371,0088 km, como `dmc_features`.
- **R-22.** En Spencer, n es el día del año de la fecha de etiqueta.
- **R-25.** El id de tramo es «<n.º de racha>.<n.º de tramo>». Una estación con varias rachas lleva en `reloj` la sucesión, por ejemplo «F(-4)→F(0)».
- **R-26.** El mes de un «cambio del portal» es el primer mes con datos de la racha posterior.
- **R-30.** La lista de fusiones por calendario de §2.3 no es exhaustiva. La regla general da además C(Coyhaique) ≡ C(Santiago) hasta 2024 y C(Punta_Arenas) ≡ C(Santiago) hasta 2016. Un «régimen con datos» es uno con alguna etiqueta no especial con datos.
- **R-31.** Determinismo (prueba 26): se comparan las huellas de tablas y política con reloj de pared inyectado. Los campos de fecha del informe y del cerrojo quedan fuera.
- **R-32.** `--sintetico` y `--control-era5` escriben en `LOCAL/…/v1/c1/` y `c3/`, nunca en los repositorios.
- **R-36.** G-viento se evalúa por año-régimen, y marca si algún régimen cumple las cuatro condiciones.
- **R-37.** Bordes de un tramo civil: la intersección de los bordes de §7.2 con la primera y la última etiqueta con dato.
- **R-38.** La Antártica (lat < −60) va a la macrozona «austral» (región 12).
- **R-39.** Muestreos con la semilla 20261022 (C3b, C3c y expedientes): `Generator(PCG64(20261022)).choice` sin reposición sobre los ids ordenados, en el orden de llamadas documentado. Un vecino del catálogo es uno de los 8 contiguos en índices globales. «Sin dato» significa no válido.
- **R-40.** Unidad de semilla de G-versión: «V-<sha8>».
- **R-43.** Los extractos de la batería D se generan con el esquema de `extraer_dmc`, sin pasar por el descargador. El formato real ya lo cubren los grupos A a C.
- **R-44.** «El vecino más cercano que tenga Ts», en E1a: el más cercano en tiempo; en un empate, el anterior.
- **R-45.** «Un dígito» en CL, CM o CH: el texto, sin espacios, es un solo dígito 0-9.
- **R-46.** En T-P, un año-régimen sin ĉt_cont definido no es evaluable.
- **R-47.** Un año dejado sin confirmar por A6 corta la racha como un insuficiente. Con E5 inactiva antes de C4, no ocurre.
- **R-48.** En la comprobación 7 de §7.3, la estación de menor código por macrozona entra con todos sus meses con regla.
- **R-49.** La publicación (C5) es un paso aparte; el ejecutable nunca escribe en los repositorios.
- **R-50.** Los nombres de las columnas de tipo, propietario, OMM y OACI del catálogo DMC no se conocen sin abrirlo. Se toman si existen. E6 está inactiva.
- **R-51.** p_v se calcula por mes. Un mes con p ∉ {1, 2, 3, 6} queda fuera de E3 y E4 para esa variable.
- **R-53.** «Días completos» con p > 1: 24/p etiquetas presentes.
- **R-54.** V y V2 son disjuntas hoy (51 y 22 códigos). Si se cruzaran, V prevalece.
- **R-55.** La lista de «campos del manifiesto que se usan» (§3.1) omite `row_count`, `verification_status` y `artifact_name`, que la admisión y E1c usan igual.

### 7.4 Resumen para el autor

| Tipo | Riesgos | Qué hacer |
|---|---|---|
| Contradicciones reales del texto | R-01 (alias −8 en la prueba 11), R-02 (incompatibilidad de E3t «sólo para T-P»), R-03 (glosa «ĉ ≥ +1») | R-01 y R-02, enmienda antes de C4. R-01 bloquea también C1, porque su prueba no puede pasar. R-03 basta con la regla formal |
| Huecos que cambian resultados | R-09 (reglas vencidas), R-17 (umbrales fuera del Anexo B) | enmienda o aclaración antes de C4 |
| Lecturas [D] | R-04 a R-06, R-08, R-10 a R-15, R-18 a R-20, R-24, R-27 a R-29, R-33 a R-35, R-41, R-42 (R-23 y R-52 pasaron al texto con la Enmienda 3) | fijarlas en el addendum de C1; R-06, antes de C2 |
| Menores [M] | el resto | quedan documentadas aquí |

---

## Anexo F. Firmas públicas (generadas por AST del código; ola 4b, regeneradas con la Enmienda 3, 2026-10-24)

**Qué es.** Las firmas públicas de cada módulo, tal como están en el código (ya no en el esqueleto). Entra lo
que no empieza por «_» a nivel de módulo: funciones con su firma completa (`ast.unparse`), clases con sus campos
anotados y sus métodos públicos (más `__init__`, `__enter__`, `__exit__`, `__call__`, `__getattr__` y `__dir__`), y los
enumerados con sus valores. No se importa nada del paquete. Los módulos van en el orden de §1.

**Notas que el AST no ve:**
- `EvidenciaEstacion.clases` (ola 3): año → clases, None por omisión; el argumento `clases=` de `decision` manda.
- `numerico`: `paso_nativo` es la regla única de §3.2 (`extraccion.paso_nativo` delega en ella);
  `desfases_ventana(U)` da −E3_VENTANA … +E3_VENTANA y la ventana de `maximo_estricto` e `interpolar_parabola`
  es obligatoria desde la ola 3.
- Los esquemas de red y de salidas viven en `tipos` desde la ola 4b; `red` y `salidas` conservan alias.
- Se regeneró al implementar la Enmienda 3 (2026-10-24), con el mismo script: entran el Anexo A3 de `tablas`, el
  patrón de regla vencida de `lineas_registro`, `numerico.media_circular_en`, la firma de B6
  (`diagnostico_subhorario` y `marca_media_horaria` ya no reciben los años confirmados), `red.a2` con la huella del
  A3 y lo que la ola 4b dejó en `bateria` y `verificar_reloj_dmc`. Si algo cambia antes de sellar C1, se regenera.
- Se regeneró otra vez con los arreglos de la revisión de la Enmienda 3 (2026-10-24): sólo cambia `constantes`
  (`indice_version`, los campos `desde` y `fragmento_anterior`, `fragmento_en` y `verificar_contra_texto(…, version)`).
  `TEXTOS_PROTOCOLO`, `VERSIONES_TEXTO` y `VERSION_VIGENTE` son datos y el AST no los lista.
- Se regeneró con la Enmienda 5 del reloj (2026-10-26), con el mismo script. Cambian cinco firmas: entra
  `numerico.mas_cercano` (ERR-1); `guardas.p7` recibe la serie ERA5-Land y entra `guardas.p7_con_referencia`
  (E5-2); `red.controles_red` recibe `a3_solo_pais` y `OpcionesCorrida` suma el campo del mismo nombre (E5-1); y
  entra `controles_era5.controles_red_c3` (los controles de red de `C3b.json`). Las constantes nuevas
  (`numerico.EMPATE_DISTANCIA_KM`, `guardas.EMPATE_P7_C`) son datos y el AST no las lista.

**Cómo se regenera** (con `~/micromamba/envs/amb_v2/bin/python -B <script> reloj_dmc <salida.md>`, desde
`scripts_modelo_1km`; el resultado reemplaza la lista que sigue a este bloque):

```python
"""Anexo F de DISENO_IMPLEMENTACION.md: firmas públicas por AST (no importa nada del paquete)."""
import ast, sys
from pathlib import Path
paq = Path(sys.argv[1])
ORDEN = ("tipos", "entorno", "fijados", "umbrales", "constantes", "numerico", "estados", "tablas", "extraccion",
         "lineas_registro", "lineas_fisicas", "guardas", "red", "decision", "politica", "orquestacion", "salidas",
         "sintetico", "bateria", "controles_era5", "verificar_reloj_dmc", "reloj_dmc")
DUNDER = {"__init__", "__enter__", "__exit__", "__call__", "__getattr__", "__dir__"}
ENUMS = {"StrEnum", "Enum", "IntEnum"}


def firma(f):
    s = f"{f.name}({ast.unparse(f.args)})"
    return s + (f" -> {ast.unparse(f.returns)}" if f.returns is not None else "")


def publica(nombre):
    return not nombre.startswith("_") or nombre in DUNDER


def clase(c):
    bases = [ast.unparse(b) for b in c.bases]
    cab = f"clase `{c.name}{'(' + ', '.join(bases) + ')' if bases else ''}`"
    if set(bases) & ENUMS:
        valores = [n.value.value for n in c.body if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)]
        return [f"- {cab}: " + ", ".join(f"`{v}`" for v in valores)]
    campos = [n.target.id for n in c.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
              and not n.target.id.startswith("_")]
    lineas = [f"- {cab}" + (": campos " + ", ".join(f"`{x}`" for x in campos) if campos else "")]
    for n in c.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and publica(n.name):
            lineas.append(f"  - `{firma(n)}`")
    return lineas


salida = []
for m in ORDEN:
    arbol = ast.parse((paq / f"{m}.py").read_text(encoding="utf-8"))
    lineas = []
    for n in arbol.body:
        if isinstance(n, ast.ClassDef) and not n.name.startswith("_"):
            lineas += clase(n)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and publica(n.name):
            lineas.append(f"- `{firma(n)}`")
    salida += [f"**`{m}.py`**", ""] + lineas + [""]
Path(sys.argv[2]).write_text("\n".join(salida), encoding="utf-8")
print(len(salida), "líneas")
```

**`tipos.py`**

- clase `Estado(StrEnum)`: `compatible`, `incompatible`, `dudosa`, `sin_informacion`
- clase `Senal(StrEnum)`: `ninguna`, `reloj_anomalo`
- clase `Familia(StrEnum)`: `registro`, `termica`, `presion_reanalisis`, `presion_marea`, `externa`, `documental`, `guarda`, `marca`
- clase `Linea(StrEnum)`: `E1a`, `E1b`, `E1c`, `E2`, `E3t`, `E3p`, `E4p`, `E6`, `E5`, `E3d`, `P7`, `T-P`, `E4t`, `G-version`, `G-HR`, `G-viento`
- clase `PropiedadesLinea`: campos `familia`, `cuantitativa`, `no_termica`, `excluye`
- clase `Nivel(StrEnum)`: `evento`, `parte`, `mes`, `regimen`, `anio`, `estacion`
- clase `Regla(StrEnum)`: `unica`, `gruesa`, `fina`
- clase `MotivoSinInfo(StrEnum)`: `minimos`, `rmax`, `empate`, `residual`, `alias`, `coordenadas`, `costera`, `sin_pixel`, `sin_desnivel`, `paso`, `filtro_representatividad`, `sin_observador`, `no_informativa`, `hueco`, `amplitud`, `campos_faltantes`, `sin_evidencia`, `apagada`, `inactiva`
- clase `Veredicto(StrEnum)`: `confirmado`, `discrepante`, `insuficiente`, `sin_datos`, `sin_confirmar`
- clase `MotivoAnio(StrEnum)`: `reloj_anomalo`, `g_version`, `lineas_en_conflicto`, `guarda_E3d`, `guarda_P7`, `guarda_T-P`, `guarda_E4t`, `no_distingue`, `apoyo`, `cobertura`, `cambio_sin_respaldo`, `inestable`, `documental_A6`
- clase `VeredictoEstacion(StrEnum)`: `confirmada`, `sin_confirmar`
- clase `Conjunto(StrEnum)`: `V`, `V2`, `N`
- clase `Territorio(StrEnum)`: `continental`, `juan_fernandez_desventuradas`, `aysen`, `magallanes`, `antartica`, `pascua_sala_y_gomez`, `incierto`
- clase `ModoE3t(StrEnum)`: `restringido`, `completo`
- clase `ResultadoGuarda(StrEnum)`: `pasa`, `falla`, `no_evaluable`
- clase `ResultadoEvento(StrEnum)`: `presente`, `ausente`, `sin_evidencia`
- clase `ClaseEvento(StrEnum)`: `real`, `placebo_semana`, `placebo_A2`, `placebo_desplazado`, `regla_vencida`
- clase `Hipotesis`: campos `tipo`, `desfase`, `zona`
  - `id(self) -> str`
  - `desde_id(cls, texto: str) -> 'Hipotesis'`
  - `es_fija(self) -> bool`
  - `orden(self) -> tuple`
- clase `Regimen`: campos `anio`, `id`, `desfases_zs`
- clase `ClaseH`: campos `miembros`, `desfases`
  - `id(self) -> str`
  - `ids_miembros(self) -> frozenset[str]`
- `interseccion_de_clases(a: frozenset[str], b: frozenset[str]) -> frozenset[str]`
- clase `Cambio`: campos `zona`, `u`, `antes_min`, `despues_min`, `tipo`, `etiqueta`, `fecha_D`, `domingo`
- clase `FilaA2`: campos `anio`, `cambio`, `fecha_real`, `regla`, `fechas_placebo`
- clase `ParteDef`: campos `id`, `anio`, `mes`, `n`, `desde`, `hasta`, `regimen`
- clase `InfoEstacion`: campos `codigo`, `nombre`, `lat`, `lon`, `alt_m`, `coordenadas_validas`, `coordenadas_inconsistentes`, `territorio`, `region`, `macrozona`, `zs`, `P`, `pixel_id`, `distancia_km`, `costera`, `z_pix`, `dz`, `conjunto`, `tipo`, `propietario`, `omm`, `oaci`
- clase `ContextoEstacion`: campos `info`, `tablas`, `umbrales`, `anios`, `regimenes`, `regimenes_con_datos`, `clases`, `meses_con_datos`, `lineas_activas`, `aplicar_exclusion_costera`
- clase `SerieEra5(Protocol)`: campos `t0`, `n_horas`
  - `tiene(self, pixel_id: int) -> bool`
  - `valores(self, pixel_id: int, variable: str, u: np.ndarray) -> np.ndarray`
  - `media(self, pixel_id: int, variable: str) -> float`
- clase `ResultadoLinea`: campos `linea`, `estados`, `metricas`, `eventos`
- clase `EvidenciaEstacion`: campos `info`, `estados`, `metricas_e2`, `metricas_e3`, `metricas_e4`, `eventos`, `guardas`, `marcas`, `meses`, `horas`, `clases`
- clase `ConsecuenciasRed`: campos `a3_falla_pais`, `a3_fallan_macrozonas`, `a5_alto`, `modo_e3t`, `a4_restringe`
  - `e4p_activa(self, macrozona: str) -> bool`
  - `fina_activa(self, macrozona: str) -> bool`
  - `modo_e3t_en(self, macrozona: str) -> ModoE3t`
- clase `DecisionAnio`: campos `codigo`, `anio`, `P`, `clases`, `excluidas`, `K`, `veredicto`, `motivo`, `detalle`, `clase_confirmada`, `lineas_apoyo`, `familias_apoyo`, `n_lineas_q`, `meses_con_apoyo`, `meses_con_datos`, `partes_discordantes`, `guardas`, `marcas`, `reglas_vencidas`, `modo_e3t`
- clase `Tramo`: campos `codigo`, `id`, `valid_from`, `valid_to`, `fixed_offset_minutes`, `clase`, `meses`
- `validar_esquema(df: pd.DataFrame, esquema: Mapping[str, str], *, nombre: str) -> None`
- `tabla_vacia(esquema: Mapping[str, str]) -> pd.DataFrame`

**`entorno.py`**

- clase `Rutas`: campos `ap`, `aph`, `local`, `dmc`, `era5l`
  - `corridas(self) -> Path`
- `rutas_reales() -> Rutas`
- `rutas_sinteticas(raiz_temporal: Path) -> Rutas`
- `alias(ruta: Path, rutas: Rutas) -> str`
- `comprobar_interprete() -> dict[str, str]`
- `sha256_archivo(ruta: Path) -> str`
- `sha256_bytes(datos: bytes) -> str`
- `json_canonico(obj: Any) -> bytes`
- `escribir_atomico(ruta: Path, datos: bytes) -> str`
- `prohibido_volumes(ruta: Path) -> None`
- `prohibido_repositorios(ruta: Path) -> None`
- `sin_datos_privados(texto: str) -> bool`
- `reiniciar_zonas(base: str='tzdata') -> None`

**`fijados.py`**

- `cargar_por_ruta(ruta: Path, sha256: str, nombre_modulo: str, *, rutas_import: Sequence[Path]=()) -> ModuleType`
- `cargar_adaptador(ap: Path, sha256: str=SHA_ADAPTADOR) -> ModuleType`
- `cargar_dmc_features(ap: Path, sha256: str=SHA_DMC_FEATURES) -> ModuleType`
- `cargar_preflight(ap: Path, sha256: str=SHA_PREFLIGHT_V3) -> ModuleType`
- `cargar_descargador(ap: Path, sha256: str) -> ModuleType`
- `nodos_superiores(fuente: str) -> dict[str, list[ast.stmt]]`
- `extraer_por_ast(ruta: Path, sha256: str | None, nombres: Sequence[str], espacio: Mapping[str, Any]) -> dict[str, Any]`
- `macrozona_region(ap: Path) -> dict[int, str]`
- `transiciones_sinca(ap: Path)`
- `huella_ruta_etiqueta(fuente: str) -> str`
- `versiones_admitidas(fuentes: Mapping[str, Path]) -> dict[str, dict]`

**`umbrales.py`**

- clase `ErrorUmbrales(ValueError)`
- clase `Umbrales`: campos `ajustables`, `fijos`, `pasos`, `sha256_json`
  - `a(self, ident: str) -> Any`
  - `f(self, ident: str) -> int | float`
  - `frac(self, ident: str) -> float`
  - `ajustado(self, ident: str) -> 'Umbrales'`
  - `agotado(self, ident: str) -> bool`
  - `vigentes(self) -> dict[str, Any]`
  - `huella(self) -> str`
- `numero_del_texto(token: str) -> int | float`
- `traducir_fijos(fijos_texto: list[str]) -> dict[str, int | float]`
- `regenerar_desde_texto(texto_protocolo: str, nombre_archivo: str) -> dict`
- `comparar(json_publicado: dict, json_regenerado: dict) -> list[str]`
- `cargar_umbrales(ruta_json: Path, ruta_protocolo: Path, *, sha256_json: str | None=None) -> Umbrales`
- `cargar_c0(aph: Path) -> Umbrales`
- `siguiente_ajuste(umbrales: Umbrales, linea: str) -> str | None`

**`constantes.py`**

- `indice_version(version: str) -> int`
- clase `ConstanteTexto`: campos `nombre`, `valor`, `seccion`, `fragmento`, `ajenos`, `desde`, `fragmento_anterior`
  - `fragmento_en(self, version: str) -> str | None`
- `valor(nombre: str) -> Any`
- `numeros_del_fragmento(texto: str) -> list[int | float]`
- `numeros_del_valor(v: Any) -> Iterator[int | float]`
- `tramo_de_seccion(texto: str, seccion: str) -> str | None`
- `verificar_contra_texto(texto_protocolo: str, version: str=VERSION_VIGENTE) -> list[str]`

**`numerico.py`**

- `semilla(base: int, codigo: str, anio: int, unidad: str, variable: str) -> int`
- `generador(semilla_: int) -> np.random.Generator`
- `bloques_de_dias(fechas: np.ndarray, primer_dia: date, dias_bloque: int) -> np.ndarray`
- `replicas_por_bloques(bloques: np.ndarray, n_replicas: int, rng: np.random.Generator) -> list[np.ndarray]`
- `paso_nativo(etiquetas: np.ndarray) -> int | None`
- `pearson(x: np.ndarray, y: np.ndarray) -> float`
- `correlaciones_por_desfase(dy: np.ndarray, dx_por_c: np.ndarray) -> np.ndarray`
- `desfases_ventana(umbrales) -> tuple[int, ...]`
- `maximo_estricto(r: np.ndarray, desfases: tuple[int, ...]) -> int | None`
- `interpolar_parabola(r: np.ndarray, c_hat: int, desfases: tuple[int, ...], c_max: int=_C['E3_CCONT_MAX'].valor) -> float | None`
- `es_alias_12(c_hat: int, c_h: int, periodo: int=_C['ALIAS_H'].valor) -> bool`
- clase `AjusteArmonico`: campos `K`, `alfa`, `beta`, `amplitudes`, `ee_amplitudes`, `phi1`, `psi2`, `n`
- `ajuste_armonico(t_horas: np.ndarray, a: np.ndarray, K: int, factor_ee: float, periodo: float=24.0) -> AjusteArmonico`
- `K_de_n_h(n_h: int, k_max: int) -> int`
- `quitar_armonico_24(t_horas: np.ndarray, y: np.ndarray, periodo: float=float(_C['PERIODO_FILTRO_H'].valor)) -> np.ndarray`
- `ecuacion_del_tiempo_min(n_dia: np.ndarray) -> np.ndarray`
- `hora_solar(etiquetas: np.ndarray, lon_este: float) -> np.ndarray`
- `distancia_circular(a: np.ndarray | float, b: np.ndarray | float, periodo: float) -> np.ndarray | float`
- `envolver(x: np.ndarray | float, desde: float, periodo: float) -> np.ndarray | float`
- `media_circular(x: np.ndarray, periodo: float) -> float`
- `media_circular_en(x: np.ndarray, intervalo: tuple[float, float]) -> float`
- `distancia_km(lat1: float, lon1: float, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray`
- `mas_cercano(distancias: np.ndarray, ids: np.ndarray) -> int`
- `z_pixel(sp_medio_hpa: float) -> float`
- `redondear_empate_hacia_cero(x: float) -> int`

**`estados.py`**

- clase `ErrorFusion(RuntimeError)`
- `filas_estado(codigo: str, anio: int, linea: Linea, nivel: Nivel, unidad: str, estados: Mapping[str, Estado], *, regla: Regla=Regla.UNICA, reloj_anomalo: bool=False, discordante: bool=False, motivo: str | None=None) -> pd.DataFrame`
- `anual_por_partes(estados: pd.DataFrame, *, linea: Linea, regla: Regla=Regla.UNICA, min_partes: int=2) -> pd.DataFrame`
- `combinar(estados: Iterable[Estado]) -> Estado`
- `estado_de_clase(estados_miembros: Mapping[str, Estado]) -> Estado`
- `es_informativo(estado: Estado) -> bool`

**`tablas.py`**

- clase `ErrorTablas(RuntimeError)`
- `version_de_base(base: str=BASE_TZDATA) -> str`
- `transiciones_utc(base: str=BASE_TZDATA) -> dict[str, list[list]]`
- `serializar_anexo_a(tabla: Mapping[str, list[list]]) -> bytes`
- `intervalo_especial(c: Cambio) -> tuple[datetime, datetime]`
- `fechas_de_regla(anio: int, cambio: str, regla: str) -> tuple[date, ...]`
- `reglas_anteriores(anexo_a: Mapping[str, list[list]] | None=None) -> list[FilaA2]`
- `serializar_anexo_a2(filas: Sequence[FilaA2]) -> bytes`
- `fechas_reglas_vencidas(anexo_a: Mapping[str, list[list]] | None=None, anexo_a2: Sequence[FilaA2] | None=None) -> list[tuple[date, str, tuple[str, ...]]]`
- `serializar_anexo_a3(tabla: Mapping[str, Sequence[tuple[datetime, str]]]) -> bytes`
- clase `TablasCalendario`
  - `__init__(self, anexo_a: Mapping[str, list[list]], anexo_a2: Sequence[FilaA2])`
  - `reglas_vencidas(self) -> list[tuple[date, str, tuple[str, ...]]]`
  - `sha256_anexo_a3(self) -> str`
  - `zonas(self) -> tuple[str, ...]`
  - `cambios(self, zona: str, anio: int | None=None) -> tuple[Cambio, ...]`
  - `etiquetas_especiales(self, zona: str, anio: int) -> tuple[frozenset[datetime], frozenset[datetime]]`
  - `desfase_civil(self, zona: str, etiqueta) -> int | None`
  - `desfase_civil_utc(self, zona: str, u) -> int`
  - `placebos_a2(self, zona: str, anio: int) -> tuple[Cambio, ...]`
  - `eventos_reglas_vencidas(self, zona: str, anio: int) -> tuple[tuple[Cambio, str], ...]`
  - `cambios_reglas_vencidas(self, zona: str, anio: int) -> tuple[Cambio, ...]`
  - `desfase_vencido(self, zona: str, etiqueta) -> int | None`
  - `con_cortes(self, cortes: Mapping[str, Sequence[tuple[datetime, datetime]]]) -> 'TablasCalendario'`
  - `con_cortes_reglas_vencidas(self, zonas: Iterable[str], anios: Iterable[int]) -> 'TablasCalendario'`
- `anexo_a3(cal: TablasCalendario) -> dict[str, list[tuple[datetime, str]]]`
- `verificar_tablas(anexo_a: Mapping[str, list[list]], anexo_a2: Sequence[FilaA2]) -> tuple[str, str]`
- `cargar_tablas(*, verificar: bool=True) -> TablasCalendario`
- `interpretar_coordenada(texto: str | None, eje: str) -> float | None`
- `celda_que_contiene(lat: float, lon: float, catalogo_pixeles: pd.DataFrame) -> int | None`
- `coordenadas_en_rango(lat: float | None, lon: float | None) -> bool`
- `territorio_y_P(lat: float | None, lon: float | None, catalogo_pixeles: pd.DataFrame, macrozona_region: Mapping[int, str]) -> tuple[Territorio, int | None, str, tuple[str, ...], tuple[Hipotesis, ...]]`
- `hipotesis_de_P(ids: Sequence[str]) -> tuple[Hipotesis, ...]`
- `regimenes_del_anio(zs: Sequence[str], anio: int, tablas: TablasCalendario) -> tuple[Regimen, ...]`
- `partes_del_mes(zs: Sequence[str], anio: int, mes: int, tablas: TablasCalendario) -> tuple[ParteDef, ...]`
- `anotar_partes(extracto: pd.DataFrame, info: InfoEstacion, tablas: TablasCalendario) -> pd.DataFrame`
- `desfase(h: Hipotesis, regimen: Regimen, zs: Sequence[str]) -> int`
- `desfase_en_etiqueta(h: Hipotesis, etiqueta, tablas: TablasCalendario) -> int | None`
- `fusionar(P: Sequence[Hipotesis], regimenes_con_datos: Sequence[Regimen], zs: Sequence[str]) -> tuple[ClaseH, ...]`
- `d_estrella(a: ClaseH, b: ClaseH) -> int`
- `rivales_mas_cercanas(clase: ClaseH, clases: Sequence[ClaseH]) -> tuple[ClaseH, ...]`
- `macrozona(territorio: Territorio, region: int | None, macrozona_region: Mapping[int, str]) -> str`
- `fecha_de(etiqueta: datetime) -> date`

**`extraccion.py`**

- clase `ErrorExtraccion(RuntimeError)`
- `leer_catalogo_dmc(ruta: Path) -> tuple[pd.DataFrame, str]`
- `leer_conjuntos(lista_v: Path, lista_v2: Path) -> dict[str, str]`
- `leer_catalogo_pixeles(ruta: Path, sha256: str) -> pd.DataFrame`
- `enlazar_pixeles(catalogo_dmc: pd.DataFrame, catalogo_pixeles: pd.DataFrame, validos: set[int], umbrales: Umbrales) -> dict[str, 'EleccionPixel']`
- `info_estaciones(catalogo_dmc: pd.DataFrame, catalogo_pixeles: pd.DataFrame, enlaces: Mapping[str, 'EleccionPixel'], medias_sp_hpa: Mapping[int, float], conjuntos: Mapping[str, str], macrozona_region: Mapping[int, str], umbrales: Umbrales, *, codigos_extra: Iterable[str]=()) -> dict[str, InfoEstacion]`
- `marcar_coordenadas_inconsistentes(infos: Mapping[str, InfoEstacion], catalogo_dmc: pd.DataFrame, meses: pd.DataFrame, umbrales: Umbrales) -> dict[str, InfoEstacion]`
- `tabla_estaciones(infos: Mapping[str, InfoEstacion]) -> pd.DataFrame`
- `listar_manifiestos(raiz_dmc: Path) -> list[Path]`
- `alias_dmc(ruta: Path, raiz_dmc: Path) -> str`
- `conjunto_admitido(versiones: Collection[str] | Mapping[str, Mapping]) -> frozenset[str]`
- `admitir_mes(manifiesto: Mapping, versiones_admitidas: set[str]) -> tuple[bool, str | None]`
- `huella_agregada_manifiestos(rutas: Sequence[Path], alias: Callable[[Path], str]) -> str`
- `huella_fila(raw_cells: Mapping[str, Mapping]) -> str`
- `filas_a_extracto(payload: Mapping, id_artefacto: int, umbrales: Umbrales) -> pd.DataFrame`
- `control_propio(extracto_mes: pd.DataFrame, umbrales: Umbrales) -> pd.DataFrame`
- `paso_nativo(etiquetas: np.ndarray) -> int | None`
- `coordenadas_inconsistentes(textos_artefactos: Iterable[tuple[str, str, str]], catalogo: tuple[str, str, str], umbrales: Umbrales) -> bool`
- clase `ResumenExtraccion`: campos `estaciones`, `meses_evaluados`, `meses_excluidos`, `filas`, `huella_manifiestos`
- `extraer_dmc(raiz_dmc: Path, adaptador: ModuleType, versiones_admitidas: set[str], umbrales: Umbrales, destino: Path, *, hecho: Callable[[str, str], bool], registrar: Callable[[str, str, str], None], avance: Callable[[int, int], None]) -> ResumenExtraccion`
- `leer_extracto(destino: Path, codigo: str, columnas: Sequence[str] | None=None) -> pd.DataFrame`
- `leer_meses(destino: Path) -> pd.DataFrame`
- `leer_artefactos_evaluados(destino: Path) -> list[dict]`
- clase `ControlMesEra5`: campos `yyyymm`, `sha256`, `eje_ok`, `mediana_t2m_K`, `mediana_sp_Pa`, `unidades_ok`
- `ruta_mes_era5(raiz_era5l: Path, yyyymm: str) -> Path`
- `leer_mes_era5land(ruta: Path) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray], ControlMesEra5]`
- `pixeles_validos(raiz_era5l: Path, umbrales: Umbrales) -> set[int]`
- clase `EleccionPixel`: campos `pixel_id`, `distancia_km`, `costera`
- `elegir_pixel(lat: float, lon: float, catalogo_pixeles: pd.DataFrame, validos: set[int], umbrales: Umbrales) -> EleccionPixel`
- clase `SerieEra5Mapeada`
  - `__init__(self, carpeta: Path)`
  - `tiene(self, pixel_id: int) -> bool`
  - `valores(self, pixel_id: int, variable: str, u: np.ndarray) -> np.ndarray`
  - `media(self, pixel_id: int, variable: str) -> float`
- `extraer_era5land(raiz_era5l: Path, pixel_ids: Sequence[int], destino: Path, *, hecho: Callable[[str, str], bool], registrar: Callable[[str, str, str], None], avance: Callable[[int, int], None], meses: Sequence[str] | None=None, validos: Collection[int] | None=None, catalogo_sha256: str | None=None) -> tuple[SerieEra5Mapeada, dict[str, ControlMesEra5]]`

**`lineas_registro.py`**

- `id_evento(zona: str, fecha_D: date, tipo: str, clase: ClaseEvento | str) -> str`
- `e1a(extracto: pd.DataFrame, ctx: ContextoEstacion) -> ResultadoLinea`
- `eventos_e1a(extracto: pd.DataFrame, ctx: ContextoEstacion) -> pd.DataFrame`
- `patron_regla_vencida(estados: pd.DataFrame) -> bool`
- `es_estacion_diurna(extracto_anio: pd.DataFrame, ctx: ContextoEstacion) -> bool`
- `e1b(extracto: pd.DataFrame, ctx: ContextoEstacion) -> ResultadoLinea`
- `e1c(meses: pd.DataFrame, ctx: ContextoEstacion) -> ResultadoLinea`
- `clase_mod3(hora: int) -> int`
- `e2(extracto: pd.DataFrame, ctx: ContextoEstacion) -> ResultadoLinea`

**`lineas_fisicas.py`**

- `ventana(umbrales) -> tuple[int, ...]`
- `columnas_dx(umbrales) -> tuple[str, ...]`
- `pasos_por_mes(extracto: pd.DataFrame, variable: str) -> dict[tuple[int, int], int | None]`
- `pares_e3(extracto: pd.DataFrame, serie: SerieEra5, ctx: ContextoEstacion, variable: Variable, *, filtrada: bool=False) -> pd.DataFrame`
- `e3(extracto: pd.DataFrame, serie: SerieEra5 | None, ctx: ContextoEstacion, variable: Variable) -> ResultadoLinea`
- `filtro_representatividad(extracto: pd.DataFrame, serie: SerieEra5 | None, ctx: ContextoEstacion) -> pd.DataFrame`
- `fina_apagada(metricas_e3p: pd.DataFrame, ctx: ContextoEstacion) -> tuple[bool, float]`
- `e3_fina(metricas_e3p: pd.DataFrame, ctx: ContextoEstacion) -> ResultadoLinea`
- `e3p_anual(estados_gruesa: pd.DataFrame, estados_fina: pd.DataFrame, fina_activa: bool) -> pd.DataFrame`
- `diagnostico_subhorario(metricas_e3p: pd.DataFrame, ctx: ContextoEstacion) -> dict`
- `ajustes_e4(extracto: pd.DataFrame, ctx: ContextoEstacion, variable: VariableE4) -> pd.DataFrame`
- `e4p(metricas_e4_qfe: pd.DataFrame, ctx: ContextoEstacion) -> ResultadoLinea`
- `normalizar_nombre_isd(nombre: str) -> str`
- `cruce_isd(catalogo_dmc: pd.DataFrame, estaciones_isd: pd.DataFrame, *, umbrales) -> pd.DataFrame`
- `e6(extracto: pd.DataFrame, isd: pd.DataFrame | None, ctx: ContextoEstacion) -> ResultadoLinea`

**`guardas.py`**

- `e3d(extracto: pd.DataFrame, serie: SerieEra5 | None, ctx: ContextoEstacion) -> pd.DataFrame`
- `p7_con_referencia(ctx: ContextoEstacion, serie: SerieEra5 | None) -> bool`
- `p7(extracto: pd.DataFrame, ctx: ContextoEstacion, serie: SerieEra5 | None=None) -> pd.DataFrame`
- `tp(metricas_e3t: pd.DataFrame, filtro_e3t: pd.DataFrame | None, ctx: ContextoEstacion) -> pd.DataFrame`
- `desfase_termico_local(metricas_e3t: pd.DataFrame, filtro_e3t: pd.DataFrame | None, ctx: ContextoEstacion) -> pd.DataFrame`
- `e4t(metricas_e4_ts: pd.DataFrame, ctx: ContextoEstacion) -> pd.DataFrame`
- `resumen_por_version(extracto: pd.DataFrame, serie: SerieEra5 | None, meses: pd.DataFrame, ctx: ContextoEstacion) -> pd.DataFrame`
- `g_version(resumen: pd.DataFrame, ctx: ContextoEstacion) -> pd.DataFrame`
- `g_hr(metricas_e4_ts: pd.DataFrame, metricas_e4_hr: pd.DataFrame, ctx: ContextoEstacion, *, extracto: pd.DataFrame) -> pd.DataFrame`
- `g_viento(extracto: pd.DataFrame, serie: SerieEra5 | None, ctx: ContextoEstacion) -> pd.DataFrame`
- `marca_media_horaria(metricas_e3p: pd.DataFrame, ctx: ContextoEstacion) -> bool`
- `guardas(extracto: pd.DataFrame, serie: SerieEra5 | None, meses: pd.DataFrame, metricas: dict[str, pd.DataFrame], ctx: ContextoEstacion) -> pd.DataFrame`
- `marcas(extracto: pd.DataFrame, serie: SerieEra5 | None, metricas: dict[str, pd.DataFrame], ctx: ContextoEstacion) -> pd.DataFrame`

**`red.py`**

- clase `ResultadoControl`: campos `control`, `pasa`, `detalle`
- `fijar_a4(consecuencias: ConsecuenciasRed, a4_restringe: bool) -> ConsecuenciasRed`
- `a1(c2_ok: bool, controles_era5: Mapping[str, object]) -> ResultadoControl`
- `a2(sha_anexo_a_calculado: str, sha_anexo_a2_calculado: str, sha_anexo_a3_calculado: str) -> ResultadoControl`
- `muestra_a3(evidencias: Iterable[EvidenciaEstacion], umbrales: Umbrales) -> pd.DataFrame`
- `a3(muestra: pd.DataFrame, umbrales: Umbrales) -> tuple[bool, frozenset[str], dict]`
- `muestra_a5(evidencias: Iterable[EvidenciaEstacion], umbrales: Umbrales) -> pd.DataFrame`
- `a5(muestra: pd.DataFrame, umbrales: Umbrales) -> tuple[bool, dict]`
- `muestra_calibracion_e3t(evidencias: Iterable[EvidenciaEstacion], a3_pais: bool, a3_macro: frozenset[str], umbrales: Umbrales, *, calendario=None) -> pd.DataFrame`
- `calibrar_e3t(muestra: pd.DataFrame, a3_pais: bool, a3_macro: frozenset[str], macrozonas: Sequence[str], umbrales: Umbrales) -> tuple[dict[str, str], pd.DataFrame]`
- `controles_red(evidencias: Sequence[EvidenciaEstacion], macrozonas: Sequence[str], umbrales: Umbrales, *, calendario=None, a3_solo_pais: bool=False) -> tuple[ConsecuenciasRed, dict]`
- `a4(decisiones_parciales: Sequence[DecisionAnio], umbrales: Umbrales) -> tuple[bool, dict]`
- `a6(registro_documental: Sequence[Mapping], decisiones: Sequence[DecisionAnio]) -> list[tuple[str, int]]`
- `a7(fallas: Sequence[str]) -> ResultadoControl`
- `g_dup(copias_c2: Sequence[Path], tablas: object, *, zs_de: Mapping[str, Sequence[str]] | None=None) -> pd.DataFrame`
- `cambios_del_portal(rachas: pd.DataFrame, meses_con_datos: Mapping[str, Sequence[str]], umbrales: Umbrales) -> list[dict]`
- `describir_red(decisiones: Sequence[DecisionAnio], rachas: pd.DataFrame, evidencias: Sequence[EvidenciaEstacion], umbrales: Umbrales, *, meses_con_regla: Mapping[str, Mapping[str, str]] | None=None, sensibilidades_bateria: Mapping | None=None) -> dict`
- `predicciones(evidencias: Sequence[EvidenciaEstacion], decisiones: Sequence[DecisionAnio], *, consecuencias: ConsecuenciasRed | None=None, calendario=None) -> dict`

**`decision.py`**

- clase `InsumosAnio`: campos `codigo`, `anio`, `macrozona`, `P`, `clases`, `estados_anuales`, `estados_parciales`, `guardas`, `marcas`, `meses_con_datos`, `desfase_termico_local`, `e4p_activa`, `fina_activa`
- `insumos_anio(evidencia: EvidenciaEstacion, anio: int, consecuencias: ConsecuenciasRed, umbrales: Umbrales, *, clases: Sequence[ClaseH] | None=None) -> InsumosAnio`
- `pasos_1_a_6(insumos: InsumosAnio, umbrales: Umbrales) -> DecisionAnio`
- `pasos_7_a_9(parcial: DecisionAnio, insumos: InsumosAnio, consecuencias: ConsecuenciasRed, umbrales: Umbrales) -> DecisionAnio`
- `decidir_anio(evidencia: EvidenciaEstacion, anio: int, consecuencias: ConsecuenciasRed, umbrales: Umbrales, *, clases: Sequence[ClaseH] | None=None) -> DecisionAnio`
- clase `ResultadoRachas`: campos `rachas`, `decisiones`, `inestable`, `cambios`, `cuarentena`, `meses_con_regla`, `motivos_inestable`
- `rachas(decisiones: Sequence[DecisionAnio], meses: pd.DataFrame, partes_discordantes: frozenset[str], umbrales: Umbrales, *, patron_regla_vencida: bool=False) -> ResultadoRachas`
- `marca_reglas_vencidas(decision: DecisionAnio, estados_con_cv: pd.DataFrame, umbrales: Umbrales, *, e4p_activa: bool=True, fina_activa: bool=True) -> bool`
- `muestra_expedientes_control(codigos_con_confirmado: Sequence[str], semilla: int, n: int) -> list[str]`

**`politica.py`**

- clase `FallaA7(Exception)`
- `reloj_de_rachas(clases: Iterable[Any]) -> str`
- `bordes_civiles(zona: str, desde: datetime, hasta: datetime, tablas: object) -> list[tuple[datetime, datetime, int]]`
- `tramos(codigo: str, meses_con_regla: Mapping[str, str], clases: Mapping[str, object], etiquetas_por_mes: Mapping[str, Sequence[datetime]], tablas: object) -> list[Tramo]`
- `veredictos_de(tramos_por_estacion: Mapping[str, Sequence[Tramo]]) -> dict[str, dict[str, str]]`
- clase `HuellasPolitica`: campos `protocolo_sha256`, `commit_ap`, `configuracion_sha256`, `informe_sha256`, `artefactos_evaluados_sha256`, `adaptador_sha256`, `python`, `tzdata`, `transiciones_sha256`
- `source_de(informe_ruta: str, informe_sha256: str, codigo: str, tramo_id: str, protocolo_sha256: str) -> str`
- `politica(tramos_por_estacion: Mapping[str, Sequence[Tramo]], estaciones: Mapping[str, dict], huellas: HuellasPolitica, *, post_hoc: bool=False, errata_post_c4: bool=False, ajuste_documental: bool=False) -> dict`
- `escribir_politica(politica_: dict, ruta: Path) -> str`
- `es_plantilla_sospechosa(regla: Mapping, veredicto: str | None, *, tablas: object | None=None) -> bool`
- clase `ContextoVerificacion`: campos `adaptador`, `adaptador_sha256`, `preflight`, `dmc_features`, `artefactos_evaluados`, `etiquetas_de_artefacto`, `veredictos`, `meses_con_regla`, `muestra_lector_real`, `tablas`, `no_normalizables`
- `verificar_politica(ruta: Path, ctx: ContextoVerificacion) -> list[str]`
- `meses_muestra_lector_real(politica_: Mapping, macrozonas: Mapping[str, str], tablas: object) -> dict[str, tuple[str, ...]]`
- `validar_regla_reloj_dmc(regla: Mapping, artefacto_sha256: str, *, politica_ruta: Path | None=None) -> None`

**`orquestacion.py`**

- clase `EntradaEstacion`: campos `info`, `extracto`, `meses`, `isd`
- clase `OpcionesCorrida`: campos `lineas_activas`, `aplicar_exclusion_costera`, `remuestreo`, `comparacion_e3t_restringida`, `diagnostico_reglas_vencidas`, `conservar_etiquetas`, `a3_solo_pais`
- clase `ResultadoRed`: campos `evidencias`, `consecuencias`, `controles`, `decisiones`, `decisiones_e3t_restringida`, `rachas`, `meses_con_regla`, `tramos`, `politica`, `descripcion_red`, `predicciones`, `no_normalizables`, `estaciones`, `resultados_rachas`, `estados_reglas_vencidas`, `tiempos`
- `contexto_estacion(entrada: EntradaEstacion, tablas: object, umbrales: Umbrales, opciones: OpcionesCorrida) -> ContextoEstacion`
- `evaluar_estacion(entrada: EntradaEstacion, serie: SerieEra5 | None, tablas: object, umbrales: Umbrales, opciones: OpcionesCorrida) -> EvidenciaEstacion`
- `diagnostico_reglas_vencidas(entrada: EntradaEstacion, serie: SerieEra5 | None, anio, tablas: object, umbrales: Umbrales, opciones: OpcionesCorrida, *, evidencia: EvidenciaEstacion | None=None) -> pd.DataFrame`
- `politica_de(resultado: ResultadoRed, huellas: mod_politica.HuellasPolitica, *, post_hoc: bool=False, errata_post_c4: bool=False, ajuste_documental: bool=False) -> dict | None`
- `evaluar_red(entradas: Callable[[], Iterable[EntradaEstacion]], serie: SerieEra5 | None, tablas: object, umbrales: Umbrales, opciones: OpcionesCorrida, *, avance: Callable[[str, int, int], None] | None=None, huellas: mod_politica.HuellasPolitica | None=None, registro_documental: Sequence[Mapping]=(), sensibilidades_bateria: Mapping | None=None) -> ResultadoRed`
- `contexto_verificacion(resultado: ResultadoRed, politica_: Mapping, destino: Path, raiz_dmc: Path, *, adaptador, preflight, dmc_features, tablas: object, adaptador_sha256: str=fijados.SHA_ADAPTADOR) -> mod_politica.ContextoVerificacion`
- `verificador_7_3(resultado: ResultadoRed, destino: Path, raiz_dmc: Path, *, adaptador, preflight, dmc_features, tablas: object, adaptador_sha256: str=fijados.SHA_ADAPTADOR) -> Callable[[Path], tuple[list[str], list[dict]]]`
- `comprobar_politica(resultado: ResultadoRed, ruta_politica: Path, ctx: mod_politica.ContextoVerificacion) -> red.ResultadoControl`
- `entradas_desde_extraccion(destino: Path, catalogo_dmc: pd.DataFrame, infos: Mapping[str, InfoEstacion], umbrales: Umbrales, *, isd: pd.DataFrame | None=None) -> tuple[dict[str, InfoEstacion], Callable[[], Iterator[EntradaEstacion]]]`

**`salidas.py`**

- clase `ErrorRetenido(ValueError)`
  - `__init__(self, mensaje: str, detalle: str)`
- `redactar(texto: Any) -> str | None`
- `tabla_pixeles(evidencias: Iterable) -> pd.DataFrame`
- `tabla_evidencia_parte(evidencias: Iterable) -> pd.DataFrame`
- `tabla_evidencia_anio(resultado: 'ResultadoRed') -> pd.DataFrame`
- `tabla_eventos(evidencias: Iterable) -> pd.DataFrame`
- `tabla_estados_largos(evidencias: Iterable) -> pd.DataFrame`
- `tabla_estados_reglas_vencidas(resultado: 'ResultadoRed') -> pd.DataFrame`
- `tabla_rachas(rachas: pd.DataFrame) -> pd.DataFrame`
- `tabla_no_normalizables(filas: Iterable[Mapping]) -> pd.DataFrame`
- `tabla_calibracion(controles: Any) -> pd.DataFrame`
- `controles_red(resultado: 'ResultadoRed') -> dict`
- `escribir_tablas(resultado: 'ResultadoRed', carpeta: Path) -> dict[str, str]`
- `contenido_artefactos(artefactos: Iterable[Mapping]) -> list[dict]`
- `escribir_artefactos_evaluados(artefactos: list[dict], carpeta: Path) -> str`
- `faltantes(controles: Any, huellas_entrada: Mapping[str, object], meses: pd.DataFrame | None) -> list[str]`
- `desviaciones_de_controles(controles: Any) -> list[str]`
- `informe(resultado: 'ResultadoRed', huellas_tablas: Mapping[str, str], huellas_entrada: Mapping[str, object], desviaciones: list[str], *, expedientes_abiertos: Mapping[str, Any] | None=None, meses: pd.DataFrame | None=None, modo_sintetico: bool=False) -> dict`
- `informe_md(informe_: dict) -> str`
- `escribir_informe(informe_: dict, carpeta: Path) -> tuple[str, str]`
- `politica_de_la_corrida(resultado: 'ResultadoRed', huellas: mod_politica.HuellasPolitica, *, post_hoc: bool=False, errata_post_c4: bool=False, ajuste_documental: bool=False) -> dict | None`
- `diferencias_salvo_informe(provisional: Mapping, final: Mapping) -> list[str]`
- `expedientes_a_abrir(resultado: 'ResultadoRed', semilla: int, n_control: int) -> dict[str, Any]`
- `expedientes(resultado: 'ResultadoRed', leer_extracto, carpeta: Path, semilla: int, n_control: int) -> list[str]`
- `verificar_privacidad(carpeta: Path) -> list[str]`
- `huella_agregada(archivos: Mapping[str, str]) -> str`
- `huella_carpeta(carpeta: Path, sub: str) -> str`
- `sellar(carpeta: Path) -> str`
- `verificar_sello(carpeta: Path) -> list[str]`
- `comprobar_cadena(carpeta: Path) -> list[str]`
- `escribir_corrida(resultado: 'ResultadoRed', carpeta: Path, *, artefactos: Sequence[Mapping], huellas_entrada: Mapping[str, object], huellas_politica: mod_politica.HuellasPolitica | None, desviaciones: Sequence[str], leer_extracto, semilla: int, n_control: int, verificar: Callable[[Path], tuple[Sequence[str], Sequence[Mapping]]] | None=None, meses: pd.DataFrame | None=None, modo_sintetico: bool=False, post_hoc: bool=False, errata_post_c4: bool=False, ajuste_documental: bool=False) -> dict[str, Any]`

**`sintetico.py`**

- clase `Sitio`: campos `nombre`, `lat`, `lon`, `alt_m`, `cod_comuna`, `con_pixel`
- clase `RelojVerdadero`: campos `tramos`, `variable`
- clase `CasoSintetico`: campos `codigo`, `relojes`, `tipo`, `escenario`, `lat`, `lon`, `alt_m`, `con_pixel`, `cod_comuna`, `perturbaciones`, `replica`, `semilla`, `anios`
- `etiqueta_desde_utc(u: datetime, reloj: str) -> datetime`
- `horas_utc(desde: datetime, hasta: datetime) -> list[datetime]`
- `relojes_desde_texto(texto: str) -> tuple[RelojVerdadero, ...]`
- `texto_de_relojes(relojes: Sequence[RelojVerdadero]) -> str`
- `territorio_sintetico(lat: float, lon: float, cod_comuna: int) -> str`
- `fuera_de_P(relojes: Sequence[RelojVerdadero], territorio: str) -> bool`
- `caso_simple(codigo: str='900001', reloj: str='F(0)', tipo: str='a', escenario: str='completo', sitio: str='santiago', *, anios: tuple[int, int]=(2019, 2019), perturbaciones: Mapping[str, float] | None=None, replica: int=0, semilla: int=0) -> CasoSintetico`
- `senales(caso: CasoSintetico, u: Sequence[datetime]) -> pd.DataFrame`
- `referencia_era5(caso: CasoSintetico, u: Sequence[datetime], *, sesgo_termico_h: float=0.0) -> pd.DataFrame`
- `vaciar_caches() -> None`
- `textos_crudos(caso: CasoSintetico, anio: int, mes: int) -> list[list[str]]`
- `html_informe(caso: CasoSintetico, anio: int, mes: int, descargador: ModuleType) -> str`
- `catalogo_dmc_sintetico(casos: Sequence[CasoSintetico]) -> list[dict]`
- `html_catalogo(casos: Sequence[CasoSintetico]) -> str`
- `inventario_sintetico(caso: CasoSintetico) -> list[dict]`
- clase `ClienteFalso`
  - `__init__(self, casos: Sequence[CasoSintetico], descargador: ModuleType)`
  - `catalog(self)`
  - `inventory(self, code)`
  - `report(self, code, year, month, start=None, end=None)`
- clase `GuardaFalsa`
  - `__init__(self, raiz: Path | None=None)`
  - `check(self, *args, **kwargs)`
  - `ensure_directory(self, path)`
  - `write_atomic_bytes(self, path, body)`
- `fabricar_descarga(casos: Sequence[CasoSintetico], raiz_temporal: Path, descargador: ModuleType, desde: str, hasta: str, *, crear_candado: bool=True) -> Path`
- `entrada_en_memoria(caso: CasoSintetico, *, senales_dadas: pd.DataFrame | None=None) -> tuple[pd.DataFrame, pd.DataFrame]`
- `isd_sintetico(caso: CasoSintetico) -> pd.DataFrame`
- `u_de_etiqueta(caso: CasoSintetico, variable: str='Ts') -> Mapping[datetime, datetime]`
- `equivalentes_en_P(caso: CasoSintetico, anio: int, variable: str='Ts') -> tuple[str, ...]`
- `comprobar_ida_y_vuelta(politica: Mapping, casos: Sequence[CasoSintetico], adaptador: ModuleType, *, maximo_por_estacion: int=20) -> list[str]`
- `catalogo_pixeles_sintetico(casos: Sequence[CasoSintetico]) -> pd.DataFrame`
- clase `SerieEra5Memoria`
  - `__init__(self, t0: np.datetime64, por_pixel: Mapping[int, pd.DataFrame], *, n_horas: int | None=None)`
  - `tiene(self, pixel_id: int) -> bool`
  - `valores(self, pixel_id: int, variable: str, u: np.ndarray) -> np.ndarray`
  - `media(self, pixel_id: int, variable: str) -> float`
- `serie_era5_de_casos(casos: Sequence[CasoSintetico], *, sesgo_termico_h: float | None=None) -> SerieEra5Memoria`
- `especificacion_bateria(replicas_d2_d3: int | None=None) -> pd.DataFrame`
- `caso_de_fila(fila: Mapping) -> CasoSintetico`

**`bateria.py`**

- `tabla_bateria(replicas_d2_d3: int | None=None) -> pd.DataFrame`
- `huella_tabla(tabla: pd.DataFrame) -> str`
- `escribir_bateria(tabla: pd.DataFrame, ruta: Path) -> str`
- `leer_bateria(ruta: Path) -> pd.DataFrame`
- `redes(tabla: pd.DataFrame) -> Iterator[tuple[str, pd.DataFrame]]`
- `celdas(tabla: pd.DataFrame) -> Sequence[str]`
- clase `ContextoBateria`: campos `tablas`, `macrozona_region`, `adaptador`
- `contexto_bateria(ap: Path | None=None, *, con_adaptador: bool=True) -> ContextoBateria`
- `es_confirmacion_erronea(fila: pd.Series) -> bool`
- `es_confirmacion_correcta(fila: pd.Series) -> bool`
- `correr_red(filas: pd.DataFrame, umbrales: Umbrales, *, contexto: ContextoBateria | None=None, ida_y_vuelta: bool=True, tiempos: dict | None=None) -> pd.DataFrame`
- `correr_bateria(tabla: pd.DataFrame, umbrales: Umbrales, *, avance: Callable[[int, int], None] | None=None, contexto: ContextoBateria | None=None, tiempos: dict | None=None, correr: Callable[..., pd.DataFrame] | None=None) -> tuple[pd.DataFrame, float]`
- `huella_resultados(resultados: pd.DataFrame) -> str`
- `replicas_por_tiempo(horas_medidas: float, umbrales: Umbrales) -> int | None`
- `proyectar_horas(segundos_medidos: float, estacion_anios_medidos: int, tabla: pd.DataFrame) -> float`
- `tiempo_bateria(horas: float, tabla: pd.DataFrame, umbrales: Umbrales, *, tiempos: Mapping | None=None, proyectadas: bool=False, previas: Sequence[Mapping]=()) -> dict`
- clase `CriteriosBateria`: campos `por_celda`, `erroneas`, `sensibilidad`, `pasa`, `motivos`, `criterios`
- `criterios_por_celda(resultados: pd.DataFrame, tabla: pd.DataFrame, umbrales: Umbrales) -> CriteriosBateria`
- `lineas_responsables(resultados: pd.DataFrame) -> set[str]`
- clase `ErrorSinResponsable(ValueError)`
- `criterios_a_json(criterios: CriteriosBateria) -> dict`
- clase `RegistroAjuste`: campos `iteraciones`, `umbrales_finales`, `c1_falla`, `motivo`, `resultados`, `criterios`, `huellas`
- `ajustar_umbrales(umbrales: Umbrales, correr: Callable[[Umbrales], pd.DataFrame], tabla: pd.DataFrame, *, ruta_registro: Path | None=None, reloj: Callable[[], datetime] | None=None) -> RegistroAjuste`
- `carpeta_c1(rutas: entorno.Rutas) -> Path`
- `escribir_salidas(carpeta: Path, tabla: pd.DataFrame, resultados: pd.DataFrame, criterios: CriteriosBateria, tiempo: Mapping, *, registro: RegistroAjuste | None=None) -> dict[str, str]`
- clase `ResultadoBateriaC1`: campos `huellas`, `pasa`, `registro`, `tiempo`, `tabla`
- `bateria_c1(carpeta: Path, umbrales: Umbrales, *, contexto: ContextoBateria | None=None, avance: Callable[[int, int], None] | None=None, reloj: Callable[[], datetime] | None=None) -> ResultadoBateriaC1`

**`controles_era5.py`**

- clase `ErrorC3(RuntimeError)`
- clase `ResultadoC3`: campos `control`, `pasa`, `detalle`, `tabla`
- clase `UnidadC3`: campos `codigo`, `control`, `sitio`, `fuente`, `enlazado`, `reloj`, `zona`, `variante`, `ruido`, `con_qfe`
- `vecinos_catalogo(catalogo_pixeles: pd.DataFrame, pixel_id: int) -> Sequence[int]`
- `pixel_valido_mas_cercano(catalogo_pixeles: pd.DataFrame, validos: Iterable[int], pixel_id: int) -> int`
- `muestra_c3b(catalogo_pixeles: pd.DataFrame, validos: set[int], umbrales: Umbrales) -> list[int]`
- `parejas_c3c(catalogo_pixeles: pd.DataFrame, validos: set[int], z_pix: Mapping[int, float], umbrales: Umbrales) -> dict[int, tuple[int, float]]`
- `muestra_c3c(catalogo_pixeles: pd.DataFrame, validos: set[int], z_pix: dict[int, float], umbrales: Umbrales) -> list[tuple[int, int]]`
- `meses_c3a() -> tuple[str, ...]`
- `pixeles_c3a(catalogo_pixeles: pd.DataFrame, validos: set[int], macrozona_region: Mapping[int, str]) -> pd.DataFrame`
- `ajuste_desde_normales(XtX: np.ndarray, Xty: np.ndarray, yty: float, n: int, K: int, factor_ee: float, periodo: float=HORAS_DIA) -> numerico.AjusteArmonico | None`
- `criterios_c3a(tabla: pd.DataFrame, umbrales: Umbrales) -> dict`
- `c3a(raiz_era5l: Path, catalogo_pixeles: pd.DataFrame, validos: set[int], macrozona_region: dict, umbrales: Umbrales, *, meses: Sequence[str] | None=None, avance: Callable[[str, int, int], None] | None=None) -> ResultadoC3`
- `medias_sp_hpa(raiz_era5l: Path, pixel_ids: Iterable[int], *, meses: Sequence[str] | None=None, avance: Callable[[str, int, int], None] | None=None) -> dict[int, float]`
- `z_pix_de(medias: Mapping[int, float]) -> dict[int, float]`
- `plan_c3b(catalogo_pixeles: pd.DataFrame, validos: set[int], umbrales: Umbrales) -> list[UnidadC3]`
- `plan_c3c(pares: Sequence[tuple[int, int]]) -> dict[str, list[UnidadC3]]`
- `infos_de_prueba(unidades: Sequence[UnidadC3], catalogo_pixeles: pd.DataFrame, medias_sp: Mapping[int, float], macrozona_region: Mapping[int, str], umbrales: Umbrales) -> dict[str, InfoEstacion]`
- `eje_utc_c3() -> np.ndarray`
- `ruido_c3b(pixel_id: int, variable: str, n: int, sigma: float, umbrales: Umbrales) -> np.ndarray`
- `senales_de_prueba(unidad: UnidadC3, serie: SerieEra5, umbrales: Umbrales) -> pd.DataFrame`
- `caso_de_prueba(unidad: UnidadC3, info: InfoEstacion, catalogo_pixeles: pd.DataFrame) -> sintetico.CasoSintetico`
- `entrada_de_prueba(unidad: UnidadC3, info: InfoEstacion, serie: SerieEra5, catalogo_pixeles: pd.DataFrame, umbrales: Umbrales, *, caso: sintetico.CasoSintetico | None=None)`
- `controles_red_c3(resultado: Any) -> dict`
- `huellas_c3(control: str)`
- `ida_y_vuelta(politica: Mapping | None, casos: Sequence[sintetico.CasoSintetico], adaptador: ModuleType | None) -> dict`
- `meses_era5_anomalos(controles: Mapping[str, Any]) -> list[str]`
- `meses_era5_sin_control(controles: Mapping[str, Any], meses: Sequence[str] | None=None) -> list[str]`
- `es_confirmacion_erronea(decision: DecisionAnio, reloj_verdadero: str) -> bool`
- `recupera_unidad(decisiones: Sequence[DecisionAnio], reloj_verdadero: str, umbrales: Umbrales) -> dict`
- `tabla_anios(decisiones: Iterable[DecisionAnio], unidades: Sequence[UnidadC3]) -> pd.DataFrame`
- `tabla_unidades(decisiones: Iterable[DecisionAnio], unidades: Sequence[UnidadC3], umbrales: Umbrales) -> pd.DataFrame`
- `criterios_c3b(tabla: pd.DataFrame, umbrales: Umbrales) -> dict`
- `c3b(raiz_era5l: Path, catalogo_pixeles: pd.DataFrame, validos: set[int], umbrales: Umbrales, *, macrozona_region: Mapping[int, str], destino: Path | None=None, serie: SerieEra5 | None=None, tablas_calendario: object | None=None, evaluar_red: Callable | None=None, avance: Callable[[str, int, int], None] | None=None, hecho: Callable[[str, str], bool] | None=None, registrar: Callable[[str, str, str], None] | None=None, controles_era5: Mapping[str, Any] | None=None, adaptador: ModuleType | None=None, huellas: Any=None, fallas_era5: Sequence[str]=()) -> ResultadoC3`
- `tabla_pares(decisiones: Mapping[str, Sequence[DecisionAnio]], evidencias: Mapping[str, Sequence[Any]], planes: Mapping[str, Sequence[UnidadC3]], distancias: Mapping[int, float], z_pix: Mapping[int, float], umbrales: Umbrales) -> tuple[pd.DataFrame, pd.DataFrame]`
- `criterios_c3c(tabla: pd.DataFrame, umbrales: Umbrales) -> dict`
- `c3c(raiz_era5l: Path, catalogo_pixeles: pd.DataFrame, validos: set[int], umbrales: Umbrales, *, macrozona_region: Mapping[int, str], destino: Path | None=None, z_pix: Mapping[int, float] | None=None, serie: SerieEra5 | None=None, tablas_calendario: object | None=None, evaluar_red: Callable | None=None, avance: Callable[[str, int, int], None] | None=None, hecho: Callable[[str, str], bool] | None=None, registrar: Callable[[str, str, str], None] | None=None, controles_era5: Mapping[str, Any] | None=None, adaptador: ModuleType | None=None, huellas: Any=None, fallas_era5: Sequence[str]=()) -> ResultadoC3`
- `carpeta_c3(rutas: entorno.Rutas) -> Path`
- `escribir_c3(resultados: Sequence[ResultadoC3], carpeta: Path) -> dict[str, str]`
- `correr_c3(rutas: entorno.Rutas, catalogo_pixeles: pd.DataFrame, validos: set[int], macrozona_region: Mapping[int, str], umbrales: Umbrales, *, evaluar_red: Callable | None=None, tablas_calendario: object | None=None, avance: Callable[[str, int, int], None] | None=None, hecho: Callable[[str, str], bool] | None=None, registrar: Callable[[str, str, str], None] | None=None, adaptador: ModuleType | None=None) -> tuple[list[ResultadoC3], dict[str, str]]`

**`verificar_reloj_dmc.py`**

- clase `ErrorC2(RuntimeError)`
- clase `ErrorCerrojo(RuntimeError)`
- clase `Configuracion`: campos `rutas`, `ap_codigo`, `paquete`, `catalogo_pixeles`, `sha_catalogo_pixeles`, `lista_v`, `lista_v2`, `copias_c2`, `rutas_protocolo`, `reloj`, `procesos`, `nice`, `lineas_activas`, `vigiladas_c1`
- `configuracion_real(rutas: entorno.Rutas | None=None) -> Configuracion`
- `resolver_alias(alias: str, rutas: entorno.Rutas, raices: Sequence[str]=RAICES_LISTA) -> Path`
- clase `RegistroGit`: campos `commit`, `motivos`, `ruta_relativa`
- `registro_en_git(archivo: Path, repo: Path, nombre: str) -> RegistroGit`
- `comprobar_git(ap: Path, aph: Path, rutas_protocolo: Sequence[str], commit_c1: str) -> list[str]`
- `leer_addendum(ruta: Path) -> dict`
- `leer_cierre(ruta: Path) -> dict`
- `leer_errata(ruta: Path) -> dict`
- `comprobar_lista_cerrada(addendum: Path, *, rutas: entorno.Rutas | None=None, exigidos: Mapping[str, str | None] | None=None) -> list[str]`
- clase `EstadoC2`: campos `cumple`, `motivos`, `progreso_sha256`, `huella_manifiestos`, `n_manifiestos`, `cierre`
- clase `CandadoDMC`
  - `__init__(self, ruta: Path)`
  - `__enter__(self) -> 'CandadoDMC'`
  - `retenido(self) -> bool`
  - `liberar(self) -> None`
  - `__exit__(self, *exc) -> None`
- `huella_de_manifiestos(raiz_dmc: Path) -> tuple[str, int]`
- `comprobar_c2(raiz_dmc: Path, linea_cierre: Path, *, aph: Path | None=None, commit_c1: str | None=None, copias_c2: Path | None=None) -> EstadoC2`
- clase `Cerrojo`
  - `__init__(self, ruta: Path)`
  - `releer(self) -> None`
  - `hay_corrida_confirmatoria(self) -> bool`
  - `errata_confirmada(self) -> int | None`
  - `selladas(self) -> set[str]`
  - `reemplazadas(self) -> set[str]`
  - `sin_sellar(self) -> dict | None`
  - `erratas_usadas(self) -> set[int]`
  - `errata_registrada(self, n: int, sha256: str) -> bool`
  - `siguiente_intento(self) -> int`
  - `registrar(self, intento: dict) -> dict`
- clase `Avance`
  - `__init__(self, ruta: Path)`
  - `hecho(self, unidad: str, huella_entrada: str) -> bool`
  - `registrar(self, unidad: str, huella_entrada: str, huella_salida: str) -> None`
- `consola(fase: str, hechos: int, total: int) -> None`
- `carpeta_corrida(corridas: Path, fecha_utc: str, errata: int | None) -> Path`
- clase `RegistroAccesos`
  - `__init__(self, vigiladas: Iterable[Path | str], *, bloquear: bool=False)`
  - `__enter__(self) -> 'RegistroAccesos'`
  - `__exit__(self, *exc) -> None`
- `correr_pruebas(paquete: Path, patron: str=PATRON_PRUEBAS) -> tuple[unittest.TestResult, str]`
- `modo_sintetico(args: argparse.Namespace) -> int`
- `cargar_meteo_guard(ap_codigo: Path) -> ModuleType`
- `descargas_activas(cfg: Configuracion) -> list[dict]`
- `modo_control_era5(args: argparse.Namespace) -> int`
- `modo_aplicar(args: argparse.Namespace) -> int`
- `analizar_argumentos(argv: Sequence[str] | None) -> argparse.Namespace`
- `main(argv: Sequence[str] | None=None) -> int`

**`reloj_dmc.py`**

- `modulo_de(nombre: str) -> str`
- `__getattr__(nombre: str)`
- `__dir__() -> list[str]`
