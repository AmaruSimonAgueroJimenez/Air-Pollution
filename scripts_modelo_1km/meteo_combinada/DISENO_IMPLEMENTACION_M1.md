# Diseño de implementación del producto meteorológico combinado (compuerta M1)

**Qué es.** El plan para escribir, entre varios implementadores en paralelo, el código del «Producto meteorológico combinado
ERA5-Land + DMC» y sus pruebas S1 a S16, sin datos DMC. Es la compuerta M1 del protocolo (§10).

**Texto vigente de M1 (Enmienda 3 adoptada el 2026-10-28 y anclada el 2026-10-29).**
`APH/auditoria/20261023/meteo_combinada/enmienda3/PROTOCOLO_METEO_COMBINADA_v2.4.md`, sha256
`eaedb10998e1a3f37f83f036c478afb5cf3fd3ccb5262477bd394dc220b1908b`. D65 formaliza D59/D63/D64 como Enmienda 3 operativa,
`post_hoc = true` por §10: posterior al inicio del C4 de RELOJ, sin competencia meteorológica real vista. Anclaje del texto:
APH `ae670dd`, sello `b07791e`, enviados al remoto privado. El v2.3 se conserva como antecedente. Esto no sella M1:
no se lanza la batería de costo hasta confirmar el paquete final y comprobar sus precondiciones.

**Fuente de D65-D67:** `APH/auditoria/20261023/meteo_combinada/enmienda3/decisiones_autor_20261028.md`, tercer archivo que
suma el colector, sin modificar los anteriores. D1-D8 y D9-D64 se conservan en sus rutas; D1-D67 sin huecos. P79, P145,
P146 y P147 siguen cerradas. D66 y D67 autorizan los pasos posteriores, no son una ejecución ni un envío en esta tarea.

**Historia: texto vigente desde el 2026-10-27 hasta esta formalización.** `APH/auditoria/20261023/meteo_combinada/enmienda2/PROTOCOLO_METEO_COMBINADA_v2.3.md`
(sha256 `b4175f78…`): el v2.2 con la Enmienda 2 del producto (EMC2-1, la coincidencia de T2a y T2b en K4, §2.5; decisiones
D52, D55 y D56; APH `dd6c1c6`, sello `e3f9f97`). El v2.2
(`APH/auditoria/20261023/meteo_combinada/enmienda1/PROTOCOLO_METEO_COMBINADA_v2.2.md`, sha256 `f059c14c…`) es el v2.1 de M0
con la Enmienda 1 del producto (EMC1-1 a EMC1-3; APH `0517360`, sello `1a9889b`), y fue el texto vigente del 2026-10-26 al
2026-10-27. Los Anexos A y B del v2.3 son byte a byte los del v2.2, y el Anexo A, el del v2.1.
Las decisiones D1-D10 del autor para M1 están en `APH/auditoria/20261023/meteo_combinada/enmienda1/decisiones_autor_20261026.md`
y `APH/auditoria/20261023/meteo_combinada/m1/decisiones_autor_m1_20261026.md`; MC-01 y MC-03 quedan resueltos por la
enmienda. **Texto de M0:** `APH/auditoria/20261023/meteo_combinada/m0/PROTOCOLO_METEO_COMBINADA_v2.1.md` (sha256 `0d0972d8…`),
anclado en M0 (APH `e8141e4`, sello `6245a6b`). Umbrales: `m0/meteo_combinada_v1.json` (sha256 `156587f1…`), generado del
Anexo A. Tabla de anclaje: `m0/tabla_anclaje_m0.json`; huellas: `m0/huellas_m0.json` (`e2c1ecd1…`). **Manda el texto**: si
este diseño y el protocolo difieren, gana el protocolo, y la diferencia se anota como riesgo (§7).

**Decisiones posteriores a M0 que este diseño ya incorpora:**
- **Enmienda 3 operativa del producto (D65).** §8 usa hasta ocho procesos, el mayor número admisible por fase de
  M3-4/M5; se conservan los topes por trabajador/principal y del grupo frente a memoria física. El recorte se fija con
  la duración efectiva antes de M3-4, conservando la proyección con ocho y avisando si daría otro recorte. No cambian
  8 GB, PROCESOS = 8, 36 h, mód 11/mód 23 ni el Anexo A, §4.9 o §10. No cambia S6.
  El nuevo esquema del addendum es `meteo-combinada-addendum-m1/2`: agrega `enmienda_operativa` y concilia
  `declaracion_c4_reloj` (ADD-13). La publicación exige las declaraciones exactas, sin cambiar las negativas de C5.
  La formalización documental no cambia firmas. La corrección posterior de recibos añade el registro opcional de
  observaciones de reparto a `repartir`; su firma exacta y vigente queda en el Anexo F.

- **Enmienda 2 ambiental, bloque «red ampliada»** (APH `f2c6cfc`, sello `65afe8a`;
  `APH/auditoria/20261024/sinca_al_modelo/ENMIENDA_2_BLOQUE_RED_AMPLIADA.md`). Su punto R21 (decisión P7, «Con la red ampliada»)
  dice que π^mon usa el `pliegues_v2.json` de ese bloque y que las tablas laterales de M6 se arman sobre el panel de R11
  (`panel_{pm25,no2}_red2.parquet`). Pide registrar esa lectura en este protocolo antes de M3-4: va al addendum de M1 (MC-09).
- **Meteorología SINCA para §5.6**, ya en `DATOS/sinca_meteorologia/`, con dos manifiestos: `manifiesto_descarga.csv`
  (469 series de 87 estaciones; en M0) y `manifiesto_descarga_20261024b.csv` (507 series de 114 estaciones; nuevo). Los dos son
  disjuntos y suman 154 estaciones (MC-10).
- **Enmiendas 3 y 4 de RELOJ**, ancladas (APH `e43a6fe` y `261c44f`; texto v1.0.4, sha256 `d8f61cfc…`). El texto v2.1 dice
  «Hoy son dos»; ahora son cuatro. Ninguna toca §3.3 ni §7 de RELOJ (`texto_7_5.md` sigue en `58362640…`). E3-5 cambia el
  diagnóstico subhorario (§4.3.5), y con él qué estaciones reciben la marca «posible media horaria». La regla de este texto que
  consume esa marca (§2.2) no cambia (MC-18).

**Qué no es.** No implementa la ciencia ni crea el esqueleto: fija módulos, estructuras de datos, firmas, el reparto de las
pruebas S1-S16, el orden de trabajo y las lecturas propuestas de los puntos ambiguos. El esqueleto (archivos `*.py` con firmas,
cuerpos `raise NotImplementedError` y pruebas omitidas con `unittest.skip("por implementar")`) es la ola 0 (§6).

**Lo que se leyó para escribirlo (declaración de ceguera).** Nada bajo `DMC` (ni artefactos, ni manifiestos, ni
`progreso.json`, ni catálogo). Se leyeron:
- el texto v2.1 entero, el JSON, la tabla de anclaje, `huellas_m0.json` y la función `anexo_a` de `m0/preparar_m0.py`;
- de RELOJ: el diseño y la coordinación de C1, los encabezados y firmas de su código, y el texto v1.0.4 en §3.3, §4.3.5 y §7,
  comparado con el v1.0.2;
- el código fijado: `leer_artefacto`, `normalizar` y `unir_sidecar` del adaptador; `cargar_dmc` de `dmc_features`; `MesNativo`
  y `leer_mes_nativo` de `_comun_modelo`; las líneas de `el_*` de `_features.py`; los encabezados y firmas de `meteo_civil_v3.py`
  y de `_pesos.py`;
- de la Enmienda 2 ambiental: el encabezado, §0 y R2, R7, R11, R13, R21, R22 y §3;
- de la meteorología SINCA: nombres de archivos, la línea de cabecera de los dos manifiestos y conteos por parámetro,
  estación, acción y marca temporal. Las filas se cargaron en memoria para contarlas, pero no se miraron ni se imprimieron
  las columnas `minimo`, `maximo` ni los conteos de filas;
- `config/sinca/politica_temporal.json` (`41018e4c…`);
- de la grilla, sólo los esquemas (columnas y número de filas);
- de `pliegues_v2.json`, sólo las claves y los tipos de una estación;
- de `config_v3.json`, las rutas de meteorología;
- de `componentes_compartidos.json`, las claves;
- git sólo en lectura (`ls-files`, `log`).

Ningún valor de ERA5-Land, NASADEM, GHS-POP ni SINCA, y ninguna métrica de modelo.

---

## 0. Reglas de trabajo

1. **Un dueño por módulo y por su archivo de pruebas.** Nadie edita el módulo de otro. Un cambio de firma o de esquema de
   `tipos.py` se pide al coordinador y se anota en `COORDINACION_M1.md` (como `COORDINACION_C1.md` del reloj). Si cambia el
   comportamiento, va al addendum de M1.
2. **Ningún umbral se escribe a mano.**
   - Los del Anexo A se piden a `Umbrales` (`U.a("QTS_MIN")`; §4).
   - Los fijos del cuerpo y del Anexo B viven en `constantes.py`, cada uno con su sección y su fragmento literal (anexo A2).
   - Un detector por árbol sintáctico (AST) rechaza los literales numéricos sospechosos fuera de esos dos módulos (§4.5).
3. **Entorno.**
   - Siempre `~/micromamba/envs/amb_v2/bin/python -B`, y `zoneinfo` con sólo el paquete tzdata, como RELOJ §9 (se
     reutiliza `reloj_dmc.entorno`).
   - Bibliotecas:
     - numpy, pandas, pyarrow y netCDF4, como el reloj;
     - además, `scipy.sparse` y `scipy.spatial.cKDTree` (operadores dispersos);
     - `pyproj` (EPSG:32719 para P2 y EPSG:54009 para GHS-POP) y `rasterio` (teselas GHS-POP);
     - `threadpoolctl` (comprobar los hilos).
     Todas están instaladas en amb_v2.
   - Pruebas con `unittest`.
   - Hilos del álgebra lineal en 1 (`OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS` y `MKL_NUM_THREADS`; §8 del texto).
   - Sólo `orquestacion.py` lanza procesos (hasta 8, por fase de M3-4/M5, D59/D63/D65; antes, 8 por D2). El resultado debe ser idéntico, bit a bit, con 1 y con
     8 procesos (S9).
4. **Datos.**
   - S1-S13, S15 y S16 usan sólo carpetas temporales con datos fabricados por `sintetico.py`.
   - S14 lee, en sólo lectura, un año de ERA5L y los productos v3 fijados en LOCAL (MC-31).
   - La medición del costo puede leer un mes real de ERA5L.
   - Ninguna prueba abre DMC, la meteorología SINCA real, NASADEM real ni GHS-POP real.
5. **Ceguera (§1.9 del texto).**
   - De RELOJ sólo se abren la política, `artefactos_evaluados.json.gz` y, por código, la lista de «coordenadas
     inconsistentes» (MC-19). Nadie del equipo abre el informe ni las tablas de evidencia del reloj antes de que termine
     M3-4.
   - Lo hace cumplir `ceguera.py` (§1).
6. **Nombres.** Ningún archivo del paquete se llama `descargar_*` ni `download_*`. Lo comprueba una prueba.
7. **Paquete.**
   - `meteo_combinada/` es un paquete con importaciones absolutas (`from meteo_combinada import tipos`). Importa
     `reloj_dmc` como otro paquete hermano.
   - Las pruebas se corren desde `scripts_modelo_1km`:
     `~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s meteo_combinada/tests -t .`
8. **Sólo escribe `salidas.py`.** Todo otro módulo es puro y devuelve tablas, diccionarios o bytes. Una prueba por AST
   busca `open(…, "w…")`, `to_parquet`, `write_bytes`, `write_text`, `Dataset(…, "w")` y `mkdir` fuera de `salidas.py`,
   `entorno.py` y `sintetico.py` (este último sólo en carpetas temporales).
9. **Lecturas del implementador.** Cada módulo lleva en su encabezado sus lecturas propias, numeradas con el prefijo del
   módulo (`QC-1`, `FON-2`…), como `GU-n` y `RED-n` en el reloj. Al cerrar M1 se copian al addendum.
10. **Aislamiento.**
    - Nada se escribe en `/Volumes` ni en los repositorios, salvo el código y sus pruebas.
    - Las salidas de M1 van a `LOCAL/meteo_combinada/v1/m1/`.
    - Sin red.
    - Toda guarda de rutas mira primero la ruta léxica y sólo después la resuelve. Es la lección de los 7 accesos de C1 del
      reloj (COORDINACION_C1, 2026-10-25).

---

## 1. Mapa de módulos

Los once módulos que nombra §8 del texto conservan su nombre y su papel. Se agregan módulos de apoyo para que ninguno se
solape y la integración quede en un solo lugar, como en el reloj:
- base: `tipos`, `constantes`, `umbrales`, `entorno`, `fijados`, `numerico`, `ceguera` y `sintetico`;
- ciencia: `politicas`, `particiones`, `sinca_meteo` y `costo`;
- integración: `orquestacion`, `salidas` y `addendum`;
- la fachada `meteo_combinada.py`.

| Módulo | Responsabilidad (y sólo ésa) | Secciones | Depende de |
|---|---|---|---|
| `tipos.py` | Enumerados, clases de datos e identificadores, y **todos los esquemas de tablas**; `validar_esquema` y `tabla_vacia`. Sin lógica ni numpy al importarse | §2-§8 | — |
| `constantes.py` | Fijos del cuerpo y del Anexo B que no están en el Anexo A, y definiciones físicas (Magnus, p_std, hipsometría, 287,05, 9,80665, 0,622…), cada uno con su sección y su fragmento literal. `verificar_contra_texto`, `completitud` y `anexo_a2` | §10 (fijos), Anexo B | — |
| `umbrales.py` | `Umbrales`: lectura de `meteo_combinada_v1.json`, regeneración desde el Anexo A del texto, comparación estricta, traducción por plantillas a valores, `opciones_m0` | Anexo A, §10 M1 | — |
| `entorno.py` | Rutas por alias (AP, APH, LOCAL, DATOS, DMC, ERA5L, NASADEM, INVARIANTES, GHS, SINCA_MET, GRILLA, PESOS, V3), carpetas de salida, hilos en 1; reexporta de `reloj_dmc.entorno` el intérprete, las huellas, el JSON canónico, la escritura atómica y las prohibiciones | §8 | `reloj_dmc.entorno` |
| `fijados.py` | Código ajeno por ruta y huella: adaptador, `dmc_features`, descargador; verificación de la clausura del reloj y carga de `validar_regla_reloj_dmc`; extracción por AST de `MACROZONA_REGION`, del esquema y Magnus de `meteo_civil_v3`, de la regla `el_*` de `_features.py` y de `opciones_m0` de `preparar_m0.py` | §2.1, §7.1, §9 (S2, S8, S14) | entorno, `reloj_dmc.fijados` |
| `numerico.py` | Magnus (agua, hielo, inversa), p_std, altitud hipsométrica, haversine, UTM 19S y Mollweide, mediana y MAD, cuantil ponderado, mínimos cuadrados armónicos recortados, ridge con pesos, hueco circular, semillas por subsecuencia, remuestreo por bloques | §2.3-§5 | constantes |
| `ceguera.py` | Registro de accesos con bloqueo (patrón de `RegistroAccesos` del reloj); guarda de red y de procesos; guarda de vocabulario de las salidas (S7); lista de lo que se puede abrir de RELOJ (§1.9); guarda del residuo (§0.4.6) | §0.4, §1.9, §9 (S7, S10) | entorno |
| `sintetico.py` | Generadores independientes: hojas DMC en el formato real y `run_download` con cliente y guarda falsos; meses ERA5-Land en NetCDF real; teselas NASADEM y GHS-POP; grilla y comunas; verdades sintéticas; meteorología SINCA; paneles y pliegues; tablas de métricas para S7 y S16. **No importa el paquete** | §9 | — (biblioteca estándar, numpy, pandas, netCDF4; el descargador y el adaptador llegan por argumento) |
| `politicas.py` | Reglas `measurements`, `quality` y `coordinates` (§2.2, §2.3, §2.5), textos `source`, tramos; registro de C5, política y `artefactos_evaluados` de RELOJ; lista K2; política de lectura y política efectiva; JSON con números de Python | §2.1-§2.5 | tipos, constantes, umbrales, entorno, fijados |
| `estaticas_nasadem.py` | K1 (ρ desde el texto), K3, lectura de teselas, alineación píxel-punto, media por celda, altitud poblada (GHS-POP 2020), TPI 1 y 5 km, pendiente con cos φ, estáticos de estaciones | §2.5, §3, §4.6 | tipos, constantes, umbrales, numerico, entorno |
| `fondo_era5l.py` | Lector mensual propio de ERA5-Land (HH:00, unidades por rango, serie continua para tp), píxeles válidos, z_E5L y su alineación, operador bilineal con vecino a ≤ 16 km, T_F, p_F, Td_F, u_F y v_F, residuos, producto desde R, climatologías del estado, sumas para RR06 | §4.1, §2.6, §3 | tipos, constantes, umbrales, numerico, entorno |
| `particiones.py` | Grupos a ≤ 2 km, P1, P2 (UTM 19S, bloques de 75 km, amortiguador de 25 km), pliegues internos, días de selección (mód 11 o 23), bloques del remuestreo, distancias a la estación de entrenamiento más cercana | §2.5, §4.9, §5.1, §5.3, §5.4 | tipos, constantes, umbrales, numerico |
| `homogeneidad.py` | Detector común de quiebres (medianas por mes y hora UTC, H*(k), D(k), segmentación binaria), K4 (T2a, T2b, clasificación), tramos homogéneos y desplazamientos δ (§4.8) | §2.5 (K4), §4.8 | tipos, constantes, umbrales, numerico |
| `sinca_meteo.py` | Lector de la meteorología SINCA para §5.6: los dos manifiestos y sus huellas, elección de series, reloj, control mínimo y series horarias por estación | §5.6 | tipos, constantes, umbrales, entorno |
| `decision.py` | `decidir_combinacion` (§6.2) con las compuertas de §6.1 y `decision.json`; del Anexo B: condiciones, simetría, ramas, regla de O3, ganador restringido y `decision_m6.json` | §6, Anexo B | tipos, constantes, umbrales |
| `qc_dmc_meteo.py` | Orden de §2.1 por artefacto y por estación; el envoltorio `qc_meteo_combinada` (§2.4); K2; retirada de K4 (marcas 1 y 16); marca 14; tabla ancha; alarmas (§2.7); lectura y validación de RR06 (§2.6); `resumen_qc` | §2.1-§2.7 | tipos, constantes, umbrales, numerico, fijados, politicas, homogeneidad, fondo_era5l |
| `candidatos.py` | Núcleo (vecinos, d_ef, pesos, Φ, soporte), A, B, AB, C y C_est (diseño fijo), filas de C, selección anidada de hiperparámetros, predicción en estaciones de prueba y en puntos | §4.2-§4.9 | tipos, constantes, umbrales, numerico, particiones, homogeneidad |
| `validacion.py` | Métricas de §5.2 y §5.8, bandas y pesos (§5.3), S y S_par, remuestreo (§5.4), estratos y regla de soporte (§5.5), réplica con N, métricas SINCA y su aviso (§5.6) | §5 | tipos, constantes, umbrales, numerico, particiones |
| `tendencias.py` | Redes histórica y constante, escenarios, medias comunales en memoria, TF1, TF2, media y P95 ponderados, compuerta de deriva (S6), muestra y TF de contaminantes (Anexo B) | §5.7, Anexo B | tipos, constantes, umbrales, numerico, candidatos, fondo_era5l |
| `producto.py` | Campos del producto (T, Td, u, v, p, HR, rapidez y dirección) por lotes de horas para un conjunto de puntos y un ganador; NetCDF de 0,1° en int16; finitud de E0 | §3, §4.1, §6.2, §8 | tipos, constantes, umbrales, numerico, fondo_era5l, candidatos |
| `salud.py` | Días civil, UTC−4 y regional con 23, 24 o 25 horas; medias comunales con w_ghs; esquema de `meteo_civil_v3`; lluvia; lista de representatividad; anual crónico; regresión S14 | §3, §7.2, §7.3, §9 (S8, S14) | tipos, constantes, umbrales, numerico, fijados, producto, fondo_era5l [ola 5, SAL-12] |
| `ambiental.py` | `lateral_monitores`, `operador_grilla` y `mc_bloque` (§7.1), con las columnas de I y de D y metadatos que acepta `unir_sidecar` | §7.1, Anexo B | tipos, constantes, umbrales, fijados, producto, fondo_era5l, candidatos |
| `orquestacion.py` | Fases de M2a, M3-4, M5 y M6; unidades reanudables, `avance.jsonl`, reparto en procesos con orden fijo de agregación, fábrica de entradas | §2.1, §8, §10 | los de ciencia, más ceguera, sinca_meteo, entorno |
| `salidas.py` | La única escritura: atómica, vigilada por `ceguera`; esquemas de archivos; `recibo_corrida.json`, `resumen_qc.json`, `decision.json`; carpeta de publicación para M5 (paso aparte); privacidad | §8 | tipos, umbrales, entorno, ceguera, addendum [delegada: validación EMC3 sin ciclo] |
| `costo.py` | Medición a escala (sintética y un mes real de ERA5L), proyección de M3-4, M5, M6 y de la grilla v2, y la regla de mód 23 | §4.9, §7.1, §8 | sintetico, candidatos, tendencias, producto, ambiental, orquestacion, entorno; además tipos, constantes, fijados, fondo_era5l, particiones, politicas, salud y ceguera [ola 6, PED-1 y PED-3 de I21, COS-1] |
| `addendum.py` | Addendum de M1: lista cerrada de huellas, anexo A2, compuerta de deriva, recorte, costo, lecturas y commits | §10 | umbrales, constantes, fijados, entorno, ceguera |
| `verificar_meteo_combinada.py` | Ejecutable con `--sintetico` (M1, con `--costo`), `--estaticos` (M2a), `--aplicar` (M3-4), `--producir` (M5) y `--m6`; negativas de §10 y del Anexo B; cerrojos `intentos_aplicar.jsonl` e `intentos_m6.jsonl`; carpeta `HUMAN<AAAAMMDD>_METEO_COMB_1`; consola sin métricas | §8, §10, Anexo B | orquestacion, salidas, costo, addendum, ceguera, fijados, umbrales, entorno; además politicas, tendencias, salud, tipos y constantes [ola 6, PED-1 de I22] |
| `meteo_combinada.py` | Fachada perezosa con los nombres de código que cita el texto: `qc_meteo_combinada` (§2.1), `decidir_combinacion` (§6.2), `lateral_monitores`, `operador_grilla` y `mc_bloque` (§7.1) | — | — al importarse |

**Grafo, por capas y sin ciclos** (cada módulo depende sólo de capas anteriores; `reloj_dmc` es externo):

```
capa 0  tipos, constantes, umbrales, entorno
capa 1  fijados, numerico, ceguera
capa 2  politicas, estaticas_nasadem, fondo_era5l, particiones, homogeneidad, sinca_meteo, decision, addendum
capa 3  qc_dmc_meteo, candidatos, validacion, salidas
capa 4  tendencias, producto
capa 5  salud, ambiental
capa 6  orquestacion
capa 7  costo
capa 8  verificar_meteo_combinada
fuera   sintetico (no importa el paquete), meteo_combinada (fachada; no importa nada al cargarse)
```

- **Validación EMC3 [delegada], revisión de 2026-10-28.** `salidas` depende de `addendum` para exigir las declaraciones
  exactas de D65 antes de publicar sus documentos. No hay dependencia inversa: `addendum` es puro y depende sólo de
  capas 0/1. Pasa a capa 2, y `salidas` a capa 3; no cambia ningún algoritmo ni firma pública. La validación privada
  común la usan el lector, el formateador y el publicador. No se debilita la guarda documental general ni C5.
- **Prueba del grafo.** `test_meteo_combinada.test_grafo_sin_ciclos` lee por AST las importaciones `meteo_combinada.*` y
  `reloj_dmc.*` de cada módulo, y exige el grafo de arriba. También exige que `sintetico` no importe el paquete y que sólo
  `entorno` y `fijados` importen `reloj_dmc`. Todo lo demás del reloj (el validador de §7.5 y, en M5, `elegir_pixel`) llega
  por funciones de `fijados` que comprueban sus huellas. `ceguera` copia el patrón de `RegistroAccesos`, sin importarlo.
- **Base sin numpy.** `tipos`, `constantes` y `umbrales` no importan numpy ni pandas. Así `entorno` puede fijar los hilos
  antes de que se carguen (§2.4 y MC-36).
- **`decision` es puro.** Sólo recibe tablas de métricas y resultados de compuertas, y nunca datos. S7 y S16 lo prueban sin
  nada más.
- **`preflight_v3` y `runner_v3` nunca se cargan.** Quedan fuera del camino (§7.1, punto 5), y cargar `preflight_v3` fija a 2
  los hilos (efecto conocido en C1 del reloj). Sólo se compara su huella.

---

## 2. Estructuras de datos

**Manda `tipos.py`.** `tipos.validar_esquema(df, ESQUEMA_*, nombre=…)` exige columnas, orden y tipos exactos en cada frontera
entre módulos. `sintetico.py` copia los esquemas que fabrica, y una prueba los compara con `tipos`, como en el reloj.

### 2.1 Identificadores

| Objeto | Identificador | Ejemplo |
|---|---|---|
| Estación DMC | `codigo`, 6 dígitos (texto) | `"330020"` |
| Grupo a ≤ 2 km | `grupo` = «G» + el menor código del grupo | `"G330020"` |
| Tramo de política | `"<id de tramo de RELOJ>/<k>"`; k ≥ 1 cuenta los cortes de K4 y de los años G dentro del tramo de RELOJ | `"1.2/3"` |
| Tramo homogéneo (§4.8) | `g`, int8 ≥ 0, por estación y variable | `0` |
| Píxel ERA5-Land | `pixel_id`, int64 del catálogo | |
| Celda de ≈ 1 km | `celda`, int64 de `celdas.parquet` | |
| Comuna | `cod_comuna`, int32 | |
| Macrozona | texto de `MACROZONA_REGION` (copiado de `_comun_modelo` por AST) | `"centro"` |
| Hora | `h`, int32: horas desde 2000-01-01T00:00Z; o `ts_utc` con zona UTC en las fronteras con v2 | `h = 0` |
| Día de selección | `d2000`, días desde 2000-01-01 de la fecha UTC (MC-44) | |
| Bloque de 75 km | `"<ie>_<in>"`, con ie = ⌊E/75.000⌋ e in = ⌊N/75.000⌋ en EPSG:32719 y origen (0, 0) | `"4_83"` |
| Pliegue | `"P1-<k>"` (k = 0…9) o `"P2-<bloque>"`; los internos, `"<externo>/i<j>"` (j = 0…4) | `"P2-4_83/i2"` |
| Evaluación | (`codigo`, `particion`) | `("330020", "P2")` |
| Hiperparámetros del núcleo | (`L_km`, `lam`, `kappa`) | `(50.0, 150.0, 0.2)` |
| Monitor (π^mon, M6) | `estacion` del panel y de `pliegues_v2.json` de la red 2 | |

### 2.2 Enumerados (`StrEnum` o `IntEnum`; se guardan como texto o entero)

- `Variable`: `T`, `Td`, `u`, `v` y `p` (las del producto). `Derivada`: `HR`, `rapidez` y `direccion`.
- `VariableDMC`: los nombres del adaptador: `Ts`, `Td`, `relative_humidity`, `wind_speed_instant`,
  `wind_direction_instant`, `QFE`, `QFF`, `QNH`, `RR06`, `wind_u` y `wind_v`.
- `Candidato`: `A`, `B`, `AB`, `C` y `C_est`. No existe un valor «fondo» ni «sin DMC»: lo prohibido de §0.4.1 y §0.4.2 no
  se puede ni nombrar.
- `Uso`: `ambiental`, `agudo` y `cronico`. `Grupo`: `T_Td`, `u_v` y `p`. `Particion`: `P1` y `P2`.
- `Conjunto`: `V`, `V2` y `N`.
- `Marca` (`IntEnum`, bits 0 a 22 de §2.4): `SIN_RELOJ` … `POSIBLE_MEDIA_HORARIA`. `tipos.INVALIDANTES` lista, por marca,
  qué variables invalida (la tabla de §2.4).
- `OrigenTd` (observado, recortado y derivado), `OrigenHR` (observado y recortado) y `OrigenViento` (observado,
  cero_es_norte y calma_sin_direccion), en int8.
- `CasoZE5L`: `geopotencial`, `nasadem` e `hipsometrica`. `ClaseQuiebre`: `traslado`, `barometro` y `metodo_reduccion`.
- `Prueba`: `TF1` y `TF2`. `ResultadoTF`: `pasa`, `falla` y `no_evaluable` (MC-03). `ReglaRedConstante`: `r2000_2025`,
  `r2003_2025` y `r2010_2025`.
- `Compuerta`: `deriva`, `finitud`, `TF`, `CD`, `EX`, `MZ`, `nivel` y `anomalia`. `Alarma`: `Q1`, `Q1z`, `Q2` y `Q3`.
- `Variante`: `I` y `D`. `Rama`: 1, 2 y 3.
- `MotivoNoNormalizable`: el texto del `ValueError` o `TypeError` normalizado a una lista cerrada (`dd_fuera_de_dominio`,
  `rapidez_negativa`, `hora_no_nativa_o_repetida`, `codigo_qc_presente`, `intervalo_no_entero`, `limite_no_python`,
  `sha_o_tamano`, `sin_observaciones`, `otro`), y su origen, «datos» o «regla» (MC-21).
- `Modo`: `sintetico`, `estaticos`, `aplicar`, `producir` y `m6`.

### 2.3 Tablas

Los tipos son de pyarrow. «f4» es float32, «f8» float64. Toda tabla lleva la versión de su esquema en los metadatos.

**Tabla larga de `cargar_dmc`.** Es la que devuelve el código fijado. No se redefine: `qc_dmc_meteo` exige las columnas que usa
(`station_code`, `timestamp_source`, `timestamp_utc`, `variable`, `value`, `unit`, `raw`, `parse_status`, `source_qc`,
`clock_verified`, `coordinates_verified`, `measurement_verified`, `model_ready`, `usable`, `quality_reason`) y su `meta`
(`long_content_sha256`, `policies_sha256`, `adapter_sha256`).

**Tabla ancha de control de calidad** (`qc/estaciones/<código>.parquet`, `ESQUEMA_QC_ESTACION`). Una fila por hora con algún
reporte, ordenada por `h`. Nadie la abre antes de que termine M3-4.

| columna | tipo | contenido |
|---|---|---|
| `h` | int32 | hora UTC del reporte (reloj confirmado) |
| `ts_fuente` | texto | etiqueta local tal como viene |
| `id_artefacto` | int32 | índice en `artefactos_evaluados` |
| `tramo` | texto | id del tramo de política |
| `Ts`, `Td`, `HR`, `FF`, `DD`, `QFE`, `QFF` | f4 | valor normalizado (FF en m/s); NaN si falta |
| `td_final`, `hr_final`, `u_final`, `v_final` | f4 | derivadas, aparte (§2.4, monotonía) |
| `origen_td`, `origen_hr`, `origen_viento` | int8 | `OrigenTd`, `OrigenHR`, `OrigenViento` |
| `marcas_Ts`, `marcas_Td`, `marcas_HR`, `marcas_viento`, `marcas_QFE`, `marcas_QFF` | uint32 | bits de §2.4 (0 a 22) |
| `valido_T`, `valido_Td`, `valido_HR`, `valido_viento`, `valido_p` | bool | «hora válida» de §2.1 por variable del producto |
| `rr06_mm`, `rr06_valido` | f4, bool | RR06 desde `raw` («s/p» = 0), sólo para §2.6 |

Sin medianas, MAD ni residuos (§0.4.6).

**Estáticos de las estaciones** (`estaticas/estaciones.parquet`, `ESQUEMA_ESTACIONES_MC`; M2a):
- identidad y conjunto: `codigo`, `nombre`, `conjunto`, `macrozona`, `grupo`, `omm` (bool o nulo), `tipo` y `propietario`
  (si el catálogo los trae);
- textos del catálogo (`lat_txt`, `lon_txt` y `alt_txt`) y su lectura (`lat`, `lon` y `z_cat`);
- K1 y K3: `rho_km`, `k3_pasa`, `z_s` y `z_s_fuente`;
- celda y P2: `celda`, `utm_e`, `utm_n` y `bloque`;
- operador del fondo: `pix0`…`pix3`, `w0`…`w3`, `respaldo_16km` y `sin_fondo`;
- `excluida` y `motivo`.

**Estáticos de las celdas** (`estaticas/celdas.parquet`, `ESQUEMA_ESTATICAS_CELDA`; M2a): `celda`, `z_media`, `z_poblada`,
`z_poblada_es_media` (bool), `frac_dato`, `tpi1`, `tpi5`, `tpi1_truncado`, `tpi5_truncado`, `pendiente_deg`, `log_dist_costa`,
las 7 fracciones `lulc_*` de 2015, `lat`, `macrozona_cod` y `cod_comuna`. La de las estaciones es la fila de su celda.

**Altitud de los píxeles** (`estaticas/z_e5l.parquet`, `ESQUEMA_ZE5L`): `pixel_id`, `valido`, `z_e5l`, `caso`, `z_nasadem`,
`frac_nasadem`, `z_hipso` y `dif_mayor_50m`.

**Fondo en las estaciones** (`insumos/puntos_estacion/<código>.parquet`, `ESQUEMA_PUNTOS_E5L`; M2a): `h` y, en f4, `T_F`,
`Td_F`, `p_F`, `u_F`, `v_F` y `amp_TF` (amplitud del día UTC). Es un insumo, no una métrica: no se resume ni se compara con
observaciones fuera de la memoria (MC-02).

**Climatologías del estado** (`insumos/clima_estado.parquet`, `ESQUEMA_CLIMA_ESTADO`; M2a): `pixel_id`, `mes`, `hora` y, en
f4, `T`, `T_menos_Td`, `rapidez` y `amp` (para C_est, §4.7).

**Residuos** (`producto/residuos/<código>.parquet`, `ESQUEMA_RESIDUOS`; M3-4, para `mc_bloque` y la producción). Columnas:
- `h` (int32);
- en f4: `r_T`, `r_Td`, `r_u`, `r_v` y `r_p` (NaN donde la observación no es válida), `rt_T` y `rt_Td` (r̃, homogeneizados);
- `g_T` y `g_Td` (int8), `observada` (bool) e `interpolable` (bool).

Insumo de acceso restringido (MC-02).

**Tramos homogéneos** (`producto/tramos_homogeneos.parquet`): `codigo`, `variable`, `g`, `desde_mes`, `hasta_mes` y `delta`
(f8).

**Climatologías de A** (`producto/clima_a.parquet`): `codigo`, `variable`, `mes`, `hora`, `rbar` (f8) y `califica` (bool).

**Evaluaciones** (`validacion/_interno/evaluaciones.parquet`, interna; no se publica ni se abre antes del final). Columnas:
- `codigo`, `particion`, `pliegue`, `candidato`, `uso` y `variable`;
- `n_horas`, `n_dias` y `n_anios`;
- en f8: `mse_h`, `mae_h`, `sesgo_h`, `mse_dia`, `mse_estrato`, `mse_anual_neto`, `mse_anomalia`, `cd` y `ex`;
- `frac_sin_soporte`.

**Sin columna de banda ni de distancia**: la banda sale de `particiones`, desde la geometría, sólo al calcular S (§0.4.5).

**Validación publicada** (`validacion/puntajes.parquet`, `ESQUEMA_VALIDACION_PUB`): `uso`, `grupo`, `variable`, `candidato`,
`particion` (P1, P2 o agregado), `S`, `CD`, `EX` y, cuando aplican, `nivel` y `anomalia`; el estrato y su valor; `n_evaluaciones`;
y `publicable` (regla de soporte). Más `validacion/bandas.parquet`, con sólo `banda`, `pi_mon`, `pi_pob` y
`frac_sin_soporte` por candidato (§5.3, «Qué se publica»).

**Tendencias** (`tendencias/resumen_tf.parquet`, `ESQUEMA_TF`): `candidato`, `uso`, `variable` (T, Td, rapidez o p), `prueba`,
`media_pond`, `p95_pond`, `cota_media`, `cota_p95`, `resultado`, `regla_red` (la de TF2 que rigió) y `n_red`. Los Δ_c por
comuna sólo en memoria (§5.7).

**No normalizables** (`qc/no_normalizables.csv`): `id_artefacto`, `codigo`, `anio`, `mes`, `macrozona`, `conjunto`, `motivo`
y `origen`. Sin valores.

**Tabla lateral I** (`ambiental/lateral_<pol>_I.parquet`, `ESQUEMA_LATERAL_I`). Claves `estacion` (texto) y `ts_utc`
(timestamp[ns, UTC]); columnas, en f4, `mc_t2m` (K), `mc_d2m` (K), `mc_rh` (%), `mc_sp` (Pa), `mc_u10`, `mc_v10` y `mc_wind`
(m/s), y `mc_wdir_sin` y `mc_wdir_cos` (adimensionales, con el ángulo `arctan2(u, v)` como `el_*`; MC-28).

**Tabla lateral D** (`ESQUEMA_LATERAL_D`). Las mismas claves; `fe_*` con los mismos 9 sufijos (el fondo en la celda del
monitor, con el mismo operador); y `dmc_R_T`, `dmc_R_Td` (K), `dmc_R_u`, `dmc_R_v` (m/s) y `dmc_R_p` (adimensional:
ln(p/p_F)). Son 14 columnas, como dice §7.1.

**Metadatos de una tabla lateral** (lo que exige `unir_sidecar`, y más):
- `model_ready = True`, `source_policy_verified = True` y `policy_sha256` (de `politicas_meteo_v1.json`);
- `variante`, `columnas` y `unidades`;
- `content_sha256` y `decision_sha256`;
- `operador_sha256`, `panel_sha256` y `pliegues_sha256` (red 2, R21).

**Meteorología diaria de salud** (`salud/{civil,utc4,regional,representatividad}/meteo_<año>.parquet`). Es el esquema
de `meteo_civil_v3` (`meteo-diaria-v3/1`), copiado por AST y comparado en S8:
- `cod_comuna` (int32) y `dia` (int32);
- `temp_media`, `temp_min`, `temp_max`, `hr_media`, `td_media` y `precip_mm` (f8);
- `n_horas` y `n_horas_esperadas` (int8) y `faltan_horas` (bool).

**Crónico** (`salud/cronico/temperatura_anual.parquet`): `cod_comuna`, `anio`, `temp_media_anual` y `temp_media_fria`; más
`td_media_anual` y `hr_media_anual` si el DISENO v3 las pide.

**Producto de 0,1°** (`producto_01deg/meteo_<AAAAMM>.nc`). Dimensiones `time` × `pixel`; `pixel_id`; `T`, `Td`, `u`, `v` y `p`
en int16, con `scale_factor` y `add_offset` de la fila «Formato» del Anexo A y `_FillValue` = −32768; atributos con las
huellas, el uso (MC-08) y el ganador.

**Series SINCA** (`ESQUEMA_SINCA_HORA`, en memoria): `estacion`, `h`, `variable` (TEMP, RHUM, WSPD o WDIR), `valor` (f8),
`valido` (bool) y `serie` (la ruta relativa elegida).

**Comparación de M6** (`ESQUEMA_COMPARACION_M6`; interfaz con v2, MC-30). Una fila por contaminante × sentido (I frente a D, D
frente a I) × protocolo (LRO, BLQ-75), con las entradas de las 7 condiciones del Anexo B:
- `delta_r2`, `ic_bajo` e `ic_alto`;
- `segunda_prueba_coincide`, `supera_ruido`, `consistencia_e2` y `sobrevive_bloque`;
- `signo_sin_ponderar` y `signo_log`;
- `decision_sigma2`, `nmb_c` y `nmb_otra`.

### 2.4 Objetos que cruzan fases (clases de datos congeladas de `tipos`)

- `InfoEstacion`: la fila de `ESQUEMA_ESTACIONES_MC` en memoria.
- `RegistroReloj`: ruta y sha256 de la política, de `artefactos_evaluados` y del commit de C5; `post_hoc` y `errata_post_c4`.
- `TramoPolitica`: código, id, `valid_from` y `valid_to` (etiqueta ingenua, inclusivos), la regla `clock` de RELOJ copiada sin
  cambios, si las coordenadas están confirmadas y el motivo.
- `ResultadoArtefacto`: la tabla larga o el motivo de «no normalizable», `content_sha256` y las reglas rechazadas por
  `validar_regla_reloj_dmc`.
- `ResultadoK4`: los quiebres (estadístico, mes, D y clase), el último traslado y el último quiebre de barómetro.
- `OperadorPuntos`: ids, z, `pix` (n × 4, int32), `w` (n × 4, f8), `dz` (n × 4, f8) y `respaldo`. Es el operador del fondo
  para estaciones, celdas o píxeles (§4.1).
- `VecinosNucleo`: puntos, `est` (n × 30, int32; −1 si no hay), `d_ef` (n × 30, f8), `grupo_de` (n × 30) e `Hiper`. La lista es
  fija por punto, y la disponibilidad se aplica hora a hora (§4.2).
- `DatosCompetencia`: residuos, climatologías, tramos, filas de C, estáticos, estaciones y pliegues. Es la entrada común de la
  selección y de la validación.
- `ModeloC`: coeficientes, medias y desvíos de la estandarización, α y diseño (`climatologico` en C_est).
- `EntradasDecision`: por (uso, grupo), la tabla de candidatos con S, réplicas, compuertas, motivos de E0 y red de TF2.
- `DecisionGrupo` y `DecisionM6`.
- `Unidad`: nombre, huella de entrada y huella de salida, para `avance.jsonl`.

### 2.5 Quién produce y quién consume, por compuerta y fase

| Compuerta y fase | Produce | Módulo | Consume |
|---|---|---|---|
| **M1** · pruebas y costo | `pruebas_m1.txt`, `resumen_m1.json`, `costo_m1.json`, `deriva_s6.json`, `anexo_a2.json` y `addendum_m1.json` | verificar, costo, addendum | sintético; ERA5L sólo para S14 y el costo |
| **M2a** · 1. negativas | registro de C2 de RELOJ y huellas de entrada | verificar, fijados | addendum de M1 |
| M2a · 2. catálogo | `InfoEstacion` (K1, K3, z_s, grupos, celda y bloque) y conteo de bloques de P2 | estaticas_nasadem, particiones | catálogo DMC (sólo coordenadas y altitudes) y NASADEM |
| M2a · 3. celdas | `estaticas/celdas.parquet` | estaticas_nasadem | NASADEM, GHS-POP 2020, `estaticas.parquet` y `estaticas_lulc.parquet` |
| M2a · 4. z_E5L | `estaticas/z_e5l.parquet` y la alineación | fondo_era5l | geopotencial (`bec3c995…`) y parquet (`791f7ba2…`) |
| M2a · 5. pasada por ERA5-Land | fondo en estaciones, climatologías del estado y píxeles válidos | fondo_era5l (orquestacion) | 321 meses |
| M2a · 6. registro | `registro_m2a.json` | salidas | todo lo anterior |
| **M3-4** · 0. negativas | — | verificar | addendum, M2a, git, C5 y registro de la red v2 (MC-09) |
| M3-4 · 1. políticas de lectura | reglas §2.2-§2.5 por tramo | politicas | política de RELOJ, M2a y K2 |
| M3-4 · 2. por artefacto (8 procesos) | tablas largas y no normalizables | qc_dmc_meteo | manifiestos y artefactos de `artefactos_evaluados` |
| M3-4 · 3-5. envoltorio, K4, retirada, marca 14, alarmas | tablas anchas y `resumen_qc` (o la detención por alarma) | qc_dmc_meteo, homogeneidad | fondo en estaciones |
| M3-4 · 6. residuos | residuos, tramos homogéneos, δ, A y filas de C | fondo_era5l, homogeneidad, candidatos | tablas anchas |
| M3-4 · 7. selección y predicción | hiperparámetros por pliegue y predicciones en prueba | candidatos, particiones | `DatosCompetencia` |
| M3-4 · 8. métricas | evaluaciones, S, remuestreo, estratos, soporte y réplica N | validacion | predicciones; π^pob y π^mon (red 2) |
| M3-4 · 9. tendencias y finitud | `resumen_tf` y E0 (finitud) | tendencias, producto | ERA5-Land, celdas pobladas y pesos 2020 |
| M3-4 · 10. RR06 y SINCA (descriptivos) | resúmenes de §2.6 y §5.6 | qc_dmc_meteo, sinca_meteo, validacion | RR06, tp y SINCA |
| M3-4 · 11. producción y decisión | hiperparámetros de producción y `decision.json` | candidatos, decision | lo anterior |
| M3-4 · 12. sello | `politicas_meteo_v1.json` (efectiva), recibo e intentos | salidas | todo |
| **M5** | 0,1°; salud civil, UTC−4, regional, representatividad y crónico; tablas laterales I y D; operador | producto, salud, ambiental (orquestacion) | `decision.json`, residuos y ERA5-Land |
| **M6** | `decision_m6.json`, TF de contaminantes, `salud/s6` y, en la rama 3, laterales restringidas | decision, tendencias, ambiental | comparación v2 (`ESQUEMA_COMPARACION_M6`), fábrica v2 y M5 |

---

## 3. Firmas públicas

Son el contrato de la ola 0. Al cerrar M1 se regenera un anexo de firmas por AST del código, con el programa del Anexo F del
reloj (cambia sólo la lista `ORDEN`). Los argumentos de sólo palabra clave van después de `*`. Las «clases de datos» son
congeladas; aquí se escriben como `class X:` con sus campos.

**Decisiones de interfaz que más importan:**
- **Los módulos de ciencia nunca leen archivos.** Reciben tablas, matrices y `Umbrales`, y devuelven tablas. Sólo
  `orquestacion` arma entradas desde el disco (fábrica de entradas, como `evaluar_red` del reloj), y sólo `salidas` escribe.
- **Lo que depende sólo de la estación se calcula una vez.** Las climatologías r̄, los tramos homogéneos y sus δ, la muestra de
  filas de C y las sumas por estación no cambian de un pliegue a otro: cada pliegue sólo elige qué estaciones entran. Así
  S5 (bit a bit) se cumple por construcción y el costo baja (MC-45).
- **Φ se calcula con dos productos dispersos por lote de horas:** Σk·q y Σk·disponible. Los pesos de grupo 1/(miembros
  disponibles) van dentro de q y de la disponibilidad. κ se aplica al final, así que las 4 κ cuestan una sola pasada por
  (L, λ).
- **El tamaño del lote de horas es fijo** (un mes UTC) en todo M3-4 y M5. Así las sumas en punto flotante salen en el mismo
  orden con cualquier número de procesos (MC-37).

```python
# tipos.py  (sin lógica; ver §2)
def validar_esquema(df, esquema, *, nombre: str) -> None
def tabla_vacia(esquema) -> "pd.DataFrame"

# constantes.py
class ConstanteTexto: nombre: str; valor: object; seccion: str; fragmento: str; ajenos: tuple = ()
CONSTANTES: tuple[ConstanteTexto, ...]
def valor(nombre: str) -> object
def numeros_del_fragmento(texto: str) -> list[int | float]
def verificar_contra_texto(texto_protocolo: str) -> list[str]
def completitud(texto_protocolo: str) -> list[str]
def anexo_a2(texto_protocolo: str, sha256_texto: str) -> dict

# umbrales.py
ESQUEMA_JSON = "meteo-combinada-umbrales/1"
SHA_JSON_M0 = "156587f195f77009fe49bfa9497fd4a334d6b4bbe14064b46b8f3d3bca5e488a"
SHA_TEXTO_M0 = "0d0972d8c8ebf09bb39bf45154496e72b524cdb8d57f9ce029aa53a16708edaf"
PLANTILLAS: dict[str, str]                      # grupo del Anexo A -> plantilla con {ID}
class ErrorUmbrales(ValueError): ...
class Umbrales:
    def a(self, ident: str) -> int | float | tuple
    def frac(self, ident: str) -> float          # sólo ids *_PCT: valor/100
    sha256_json: str; sha256_texto: str; opciones_m0: dict
def numero_del_texto(token: str) -> int | float
def regenerar_desde_texto(texto: str, nombre_archivo: str, sha256_texto: str, opciones_m0: dict) -> dict
def comparar(publicado: dict, regenerado: dict) -> list[str]
def traducir(filas_anexo_a: list[dict]) -> dict[str, int | float | tuple]
def cargar_umbrales(ruta_json, ruta_texto, *, sha256_json: str | None = None) -> Umbrales
def cargar_m0(aph) -> Umbrales

# entorno.py
class Rutas: ap; aph; local; datos; dmc; era5l; nasadem; invariantes; ghs; sinca_met; grilla; pesos; v3
def rutas_reales() -> Rutas
def rutas_sinteticas(raiz_temporal) -> Rutas
def alias(ruta, rutas: Rutas) -> str
def carpeta_salida(rutas: Rutas, compuerta: str, etiqueta: str | None = None) -> "Path"   # LOCAL/meteo_combinada/v1/...
def fijar_hilos() -> dict                       # variables de entorno y threadpoolctl; falla si no queda en 1
# reexportadas de reloj_dmc.entorno: comprobar_interprete, sha256_archivo, sha256_bytes, json_canonico,
# escribir_atomico, prohibido_volumes, prohibido_repositorios, sin_datos_privados

# fijados.py
SHA_ADAPTADOR, SHA_DMC_FEATURES, SHA_PREFLIGHT_V3, SHA_COMUN_MODELO, SHA_DESCARGADOR, SHA_FEATURES, SHA_METEO_CIVIL_V3,
SHA_EXPOSICION_V3, SHA_PESOS_PY, SHA_PREPARAR_M0                  # §9.3
MODULOS_RELOJ = ("entorno", "fijados", "politica", "tipos", "constantes", "tablas")
def cargar_adaptador(ap) -> "ModuleType"
def cargar_dmc_features(ap) -> "ModuleType"
def cargar_descargador(ap) -> "ModuleType"
def huellas_reloj(ap) -> dict[str, str]
def cargar_validador_reloj(ap, huellas_esperadas: dict[str, str]) -> "Callable"
def macrozona_region(ap) -> dict[int, str]
def esquema_meteo_civil_v3(aph) -> dict          # VARIABLES, ESQUEMA_DIARIO, MAGNUS_A/B y tipos de tabla_meteo (AST)
def regla_el_features(ap) -> dict                # nombres el_*, Magnus 17,67/243,5 y arctan2(u, v) (AST)
def opciones_m0(aph) -> dict                     # OPCIONES_M0 de m0/preparar_m0.py (AST, sha 49503a3a…)
def comprobar_codigo_fijado(ap, aph) -> list[str]

# numerico.py
def magnus_agua(t_c): ...; def magnus_hielo(t_c): ...; def td_desde_e(e_hpa): ...
def hr_desde(t_c, td_c, *, hielo: bool = False): ...; def td_desde_hr(hr, t_c): ...
def p_std(z_m): ...; def z_hipsometrica(sp_hpa): ...; def presion_a_altitud(sp_hpa, t_k_medio, dz_m): ...
def haversine_km(lat1, lon1, lat2, lon2): ...
def utm19s(lat, lon) -> tuple; def mollweide(lat, lon) -> tuple
def mediana_mad(x) -> tuple[float, float]
def cuantil_ponderado(x, w, q: float) -> float
def armonico_recortado(h, r, k_max: int, recorte: float) -> "np.ndarray"
def ridge_ponderado(xtx, xty, alfa: float, *, sin_penalizar: int = 0) -> "np.ndarray"
def hueco_circular_max(horas, periodo: int) -> int
def generador(semilla: int, *partes: str) -> "np.random.Generator"   # SeedSequence([semilla, huella(partes)])
def remuestreo_bloques(ids_bloque, n_replicas: int, semilla: int) -> "np.ndarray"

# ceguera.py
class RegistroAccesos:                         # patrón del reloj; mira la ruta léxica antes de resolver
    def __init__(self, vigiladas, *, bloquear: bool = False, permitidas=()): ...
    def __enter__(self): ...; def __exit__(self, *exc): ...
class SinRed: ...                              # contexto: socket bloqueado
def procesos_hijos_vivos() -> list[int]
VOCABULARIO_PROHIBIDO = ("fondo", "era5l", "sin_dmc", "correccion", "R_")
def vigilar_salida(nombre_archivo: str, contenido, *, clase: str) -> None   # clase: metrica, resumen, insumo, procedencia
def permitido_de_reloj(ruta) -> bool           # política, artefactos_evaluados, lista K2 (§1.9)
class GuardaResiduo: ...                       # S7: centinelas en memoria que no deben aparecer en salidas

# sintetico.py  (no importa el paquete)
class EstacionSintetica: codigo; lat; lon; alt_m; textos_coord: tuple; reportes: "pd.DataFrame"   # textos crudos por hora
def hoja_html(codigo, anio, mes, filas_textos, descargador) -> str
class ClienteFalsoMC: ...; class GuardaFalsaMC: ...
def fabricar_descarga(estaciones, raiz_temporal, descargador, desde: str, hasta: str) -> "Path"
def politica_reloj_sintetica(raiz, estaciones, reglas: dict) -> "Path"   # política + artefactos_evaluados + registro C5
def mes_era5_netcdf(ruta, campos: dict, tiempos, pixel_ids, *, unidades: str = "nativas") -> "Path"
def catalogo_pixeles(lat0, lon0, nlat, nlon) -> "pd.DataFrame"
def tesela_nasadem(ruta, funcion_z, *, mascara=None) -> "Path"
def tesela_ghs(ruta, funcion_pob) -> "Path"
def grilla(nceldas, comunas) -> dict
def verdad(campos_base, sesgo, anomalias, *, semilla: int) -> dict
def red_s6(*, deriva_k_decada: float = 0.0) -> dict
def series_traslado(tipo: str, altitud_m: float, *, semilla: int) -> "pd.DataFrame"
def tablas_metricas(caso: str) -> dict; def tablas_m6(caso: str) -> dict
def sinca_sintetico(raiz) -> "Path"; def panel_y_pliegues(raiz) -> dict

# politicas.py
def leer_registro_c5(ruta) -> "RegistroReloj"
def leer_politica_reloj(registro, *, ap) -> tuple[dict, dict]     # exige sha256 de la política y de artefactos
def comprobar_c5(registro, politica) -> list[str]                  # post_hoc, errata_post_c4, sha256
def coordenadas_inconsistentes(registro, *, ap) -> frozenset[str] # K2: sólo esa lista, por código (MC-19)
def source_coordenadas(codigo: str, sha_catalogo: str, sha_protocolo: str) -> str
def source_medicion(variable: str, sha_protocolo: str, *, motivo: str | None = None) -> str
def source_calidad(variable: str, sha_protocolo: str) -> str
def tramos_de_lectura(politica_reloj, codigo, meses_con_artefacto, marcas_g) -> list["TramoPolitica"]
def politicas_de_lectura(politica_reloj, info, tramos, umbrales, *, sha_protocolo, sha_catalogo) -> list[dict]
def politicas_efectivas(politicas_lectura, resultados_k4: dict) -> list[dict]
def politicas_que_cruzan(politicas, codigo: str, anio: int, mes: int) -> list[dict]
def a_json(politicas) -> bytes                                     # números de Python; ida y vuelta exacta

# estaticas_nasadem.py
def rho_km(lat_txt: str, lon_txt: str, umbrales) -> float          # K1
def leer_tesela(ruta, sha256: str) -> "TeselaDEM"
def celda_de_puntos(lat, lon) -> "np.ndarray"                       # bordes oeste y sur cerrados
def k3(lat, lon, z_cat, rho_km, teselas, umbrales) -> tuple[bool, float]
def estaticos_celdas(celdas, teselas, ghs, estaticas_v1, lulc, umbrales) -> "pd.DataFrame"
def info_estaciones(catalogo, celdas, teselas, umbrales, *, macrozona_region, conjuntos) -> dict[str, "InfoEstacion"]

# fondo_era5l.py
class MesE5L: tiempos; pixel_id; datos: dict; sha256: str
def leer_mes(ruta, *, sha256: str | None = None) -> MesE5L         # rechaza horas que no son HH:00
def comprobar_unidades(mes: MesE5L, umbrales) -> None              # aborta (S13)
def pixeles_validos(meses_referencia: dict[str, MesE5L]) -> "np.ndarray"
def z_e5l(geopotencial, catalogo, teselas, sp_medio, umbrales) -> "pd.DataFrame"
def comprobar_alineacion(z, parquet_altitud) -> None                # M2a se detiene si difiere (S13)
def operador(lat, lon, z, catalogo, validos, z_pix, umbrales) -> "OperadorPuntos"
def campos_fondo(mes: MesE5L, op: "OperadorPuntos") -> dict[str, "np.ndarray"]   # T_F, Td_F, p_F, u_F, v_F
def producto_desde(F: dict, R: dict) -> dict                         # T, Td = mín(·, T), u, v, p = p_F·exp(R_p)
def residuos(obs: dict, F: dict) -> dict                             # r_T, r_Td, r_u, r_v, r_p = ln(QFE/p_F)
def incrementos_tp(meses: list[MesE5L]) -> "np.ndarray"             # serie continua; NaN sin la hora previa
def sumas_rr06(tp_horario, h_fin) -> "np.ndarray"
def climatologias_estado(acumulador, mes: MesE5L) -> None
def amplitud_dia_utc(T, h) -> "np.ndarray"

# particiones.py
def grupos_mismo_sitio(infos, umbrales) -> dict[str, str]
def bloque(lat, lon, umbrales) -> "np.ndarray"
def pliegues_p1(grupos, umbrales) -> list["Pliegue"]
def pliegues_p2(infos, grupos, umbrales) -> list["Pliegue"]
def pliegues_internos(externo: "Pliegue", infos, grupos, umbrales) -> list["Pliegue"]
def dias_de_seleccion(h, umbrales, *, recorte: bool) -> "np.ndarray"
def distancia_entrenamiento_km(prueba, entrenamiento, infos, horas_validas, umbrales) -> dict[str, float]
def bloques_remuestreo(infos) -> dict[str, str]

# homogeneidad.py
def medianas_mes_hora(h, valores, validos, umbrales) -> "pd.DataFrame"
def horas_estables(medianas, k: int, umbrales) -> frozenset[int]    # H*(k) (MC-06)
def salto(medianas, k: int, umbrales) -> float | None               # D(k)
def segmentar(medianas, umbral: float, umbrales) -> list[tuple[int, float]]
def k4(tabla_estacion, p_F, z_cat: float, umbrales) -> "ResultadoK4"
def tramos_homogeneos(h, residuo, variable, umbrales) -> list[tuple[int, int]]
def desplazamientos(h, residuo, tramos, umbrales) -> dict[int, float]

# sinca_meteo.py
def leer_manifiestos(raiz, huellas: dict[str, str]) -> "pd.DataFrame"
def elegir_series(manifiesto, umbrales) -> "pd.DataFrame"           # una por estación × variable (MC-10)
def series_horarias(raiz, elegidas, politica_temporal, umbrales) -> "pd.DataFrame"   # ESQUEMA_SINCA_HORA

# decision.py
def compuertas(uso, grupo, tabla, umbrales) -> "pd.DataFrame"
def decidir_combinacion(uso, grupo, entradas: "EntradasDecision", *, umbrales) -> "DecisionGrupo"
def decision_json(decisiones, hiperparametros, huellas: dict) -> dict
def condiciones_anexo_b(comparacion: "pd.DataFrame", contaminante: str, sentido: str, umbrales) -> list[bool]
def ramas_m6(condiciones: dict, tf_contaminantes: dict, ganador_ambiental: dict) -> "DecisionM6"
def variante_o3(por_contaminante: dict) -> str
def ganador_restringido(entradas_ambientales, grupos_con_b_ab, *, umbrales) -> dict
def decision_m6_json(decision: "DecisionM6", huellas: dict) -> dict

# qc_dmc_meteo.py
def normalizar_artefacto(manifiesto, politicas, *, adaptador, dmc_features, validar_regla, sha_adaptador) -> "ResultadoArtefacto"
def qc_meteo_combinada(larga, info: "InfoEstacion", F_estacion, umbrales, *, k2: frozenset[str]) -> "pd.DataFrame"
def aplicar_k4(tabla, resultado: "ResultadoK4") -> "pd.DataFrame"
def marca_14(tabla, F_estacion, umbrales) -> "pd.DataFrame"
def tabla_ancha(tabla) -> "pd.DataFrame"
def alarmas(conteos, denominadores, umbrales) -> list[dict]
def validar_rr06(tablas, tp_sumas, infos, umbrales) -> dict
def resumen_qc(conteos, alarmas, no_normalizables, sin_traslado) -> dict

# candidatos.py
def distancia_efectiva(puntos, estaciones, lam: float) -> "np.ndarray"
def vecinos(puntos, entrenamiento, hiper, umbrales) -> "VecinosNucleo"
def campo(vec: "VecinosNucleo", q, disponible) -> tuple["np.ndarray", "np.ndarray"]   # Φ y Σk
def climatologia_a(h, r, umbrales) -> "pd.DataFrame"
def correccion_a(vec, clima, h) -> "np.ndarray"                      # interpolada entre centros de mes
def correccion_b(vec, rt, disponible) -> "np.ndarray"
def correccion_ab(vec_a, vec_ab, clima, anomalias, disponible, h) -> "np.ndarray"
def interpolar_no_observadas(h, rt, umbrales) -> tuple["np.ndarray", "np.ndarray"]
def diseno_c(estaticos, h, estado, umbrales, *, climatologico: bool = False) -> "np.ndarray"
def filas_c(residuos, estaticos, estados, umbrales) -> dict           # muestra fija y sumas por estación
def ajustar_c(sumas_por_estacion, entrenamiento, alfa: float) -> "ModeloC"
def predecir_c(modelo, estaticos, h, estado) -> "np.ndarray"
def seleccionar(candidato, variable, uso, externo: "Pliegue", datos: "DatosCompetencia", umbrales) -> object
def predecir_prueba(candidato, variable, uso, hiper, externo: "Pliegue", datos) -> "pd.DataFrame"

# validacion.py
def metricas_horarias(pred, obs, variable) -> dict
def dias_validos(h, valido, zona: str, umbrales) -> "pd.DataFrame"
def desviacion_estrato(diario, umbrales) -> float
def anual_neto(anuales, macrozona) -> float; def anomalia_interanual(anuales, macrozona, umbrales) -> float
def ciclo_diario(h, pred, obs, umbrales) -> float
def extremos(diario_pred, diario_obs, uso, variable, umbrales) -> float
def bandas(distancias_km, umbrales) -> "np.ndarray"
def pi_poblacion(celdas_pobladas, estaciones_por_anio, variable, umbrales) -> dict
def pi_monitores(pliegues_red2, panel_red2, estaciones_por_anio, variable, umbrales) -> dict
def puntaje(mse_e, banda_e, pi, umbrales) -> float
def puntaje_par(S_T: dict, S_HR: dict, e0) -> dict
def remuestreo(evaluaciones, bloques, umbrales) -> "pd.DataFrame"
def publicable(frac_sin_soporte: dict, umbrales) -> bool
def estratos(evaluaciones, infos, umbrales) -> "pd.DataFrame"
def replica_n(entradas, infos, umbrales) -> dict
def validacion_sinca(series, producto_celda, producto_punto, tpi, umbrales) -> dict

# tendencias.py
def red_historica(horas_validas_anio, variable, umbrales) -> frozenset[str]
def red_constante(horas_validas_anio, variable, umbrales) -> tuple[frozenset[str], str]
def medias_comuna_anio(campo_lote, h, pesos_2020, comunas) -> "np.ndarray"
def tf1(cambio, completo, pesos_comuna, umbrales, variable) -> dict
def tf2(constante, completo, pesos_comuna, umbrales, variable, regla: str) -> dict
def media_p95_ponderados(x, w) -> tuple[float, float]
def compuerta_deriva(resultados_s6: dict) -> dict[str, bool]
def muestra_tf_contaminantes(celdas_pobladas, pesos, umbrales) -> "np.ndarray"
def tf_contaminantes(fabrica, modelo, variante, muestra, umbrales) -> dict

# producto.py
def correccion(candidato, hiper, puntos, lote_h, datos) -> dict
def campos(F: dict, R: dict) -> dict                                  # más HR, rapidez y dirección
def codificar_int16(campos: dict, umbrales) -> dict; def decodificar_int16(enteros: dict, umbrales) -> dict
def mes_01deg(campos: dict, pixel_id, h, umbrales, huellas: dict) -> bytes
def fraccion_finita(campos: dict, con_fondo) -> float

# salud.py
def dias(h, zona: str | None) -> "np.ndarray"                         # None: UTC−4 fijo
def horas_esperadas(dias, zona: str | None) -> "np.ndarray"
def pesos_comuna(anio: int, celdas, tabla_pesos) -> "csr_matrix"         # matriz dispersa comuna × celda
def meteo_comunal(campos_celda, lluvia, pesos, tipo_dia) -> "pd.DataFrame"   # esquema de meteo_civil_v3
def representatividad(diarios_obs, t2m_pixel_reloj, umbrales) -> frozenset[str]
def cronico_anual(diarios, pesos_por_anio) -> "pd.DataFrame"
def regresion_s14(anio: int, rutas, *, esquema_v3: dict) -> dict       # «igual» o «distinto» y la diferencia máxima

# ambiental.py
def lateral_monitores(pol, decision, operador, *, variante="I", panel, monitores, rutas) -> tuple["pd.DataFrame", dict]
def operador_grilla(decision, *, celdas, estaciones, catalogo, z_celdas, rutas) -> "Path"
def mc_bloque(celdas, horas, variante, *, operador, meses, residuos) -> "pd.DataFrame"
def comprobar_union(tabla, metadatos, adaptador) -> None              # llama a unir_sidecar sobre un panel de prueba

# orquestacion.py
FASES_M2A, FASES_M34, FASES_M5, FASES_M6: tuple[str, ...]
def correr_m2a(cfg, *, avance) -> dict
def correr_m34(cfg, *, avance, procesos: int) -> dict
def correr_m5(cfg, *, avance, procesos: int) -> dict
def correr_m6(cfg, *, avance) -> dict
def repartir(unidades, funcion, procesos: int) -> list                 # resultados en el orden de las unidades

# salidas.py
def escribir(ruta, contenido, *, clase: str, esquema=None) -> str      # sha256; pasa por ceguera.vigilar_salida
def recibo_corrida(huellas: dict, entorno_: dict) -> dict
def publicar_m5(carpeta_corrida, destino_ap) -> list[str]              # paso aparte; nunca dentro de una corrida

# costo.py
def medir(rutas, *, real_era5: bool) -> dict
def proyectar(mediciones: dict, umbrales, *, procesos: int) -> dict    # horas de M3-4, M5, M6 y grilla v2
def recorte(proyeccion: dict, umbrales) -> str                         # "mod11" o "mod23"

# addendum.py
def lista_cerrada(rutas) -> dict[str, str]
def addendum_m1(lista, anexo_a2, deriva, recorte, costo, lecturas, commits) -> dict

# verificar_meteo_combinada.py
def main(argv=None) -> int          # --sintetico [--costo] | --estaticos | --aplicar | --producir | --m6
def negativas_m34(cfg) -> list[str]; def negativas_m6(cfg) -> list[str]
class Cerrojo: ...                  # intentos_aplicar.jsonl e intentos_m6.jsonl, sólo agregado

# meteo_combinada.py (fachada)
NOMBRES_TEXTO = {"qc_meteo_combinada": "qc_dmc_meteo", "decidir_combinacion": "decision",
                 "lateral_monitores": "ambiental", "operador_grilla": "ambiental", "mc_bloque": "ambiental"}
```

Las tres funciones de §7.1 conservan los argumentos posicionales del texto: `(pol, decision, operador)`, `(decision)` y
`(celdas, horas, variante)`. Lo demás va por palabra clave.

---

## 4. Umbrales: lectura y comparación en M1

### 4.1 Tres fuentes, sin solape

1. **Anexo A** (27 grupos), desde `meteo_combinada_v1.json["anexo_a"]`. `U.a(id)` devuelve el valor; las listas vuelven como
   tupla (`NUC_L` = (10, 25, 50, 100, 200)).
2. **Anexo A2: fijos del cuerpo y del Anexo B** que no están en el Anexo A (§10: «M1 los lista en un anexo A2 generado del
   texto, cada uno con su fragmento literal»). Viven en `constantes.CONSTANTES`, cada uno con su sección y su fragmento.
3. **Definiciones físicas y de formato** (Magnus 6,112, 17,625, 243,04, 22,46 y 272,62; p_std 1.013,25, 2,25577·10⁻⁵ y
   5,25588; hipsométrica 44.330,8 y 0,190263; 287,05; 9,80665; 0,622 y 0,378; 29,27, 0,0065 y 273,15; 1.852/3.600 del
   adaptador). Van también en `constantes.py`, con su fragmento. No son ajustables.

Este protocolo no tiene umbrales ajustables (no hay un §8.F como en el reloj): todo valor es fijo desde M0, y sólo una
enmienda lo cambia (§10).

### 4.2 Formato numérico y plantillas

- **Números.** Se leen como los escribe el texto:
  - signo «−» (U+2212) o «+»;
  - miles con «.» y decimales con «,»;
  - «·10⁻⁵» en notación científica;
  - listas entre llaves: con «, » entre enteros y con «; » entre decimales («{0,05; 0,2; 0,5; 1,0}»).
  La regla es la de `reloj_dmc.constantes.numeros_del_fragmento`. Se copia, y una prueba de paridad la compara con la del
  reloj sobre los fragmentos de este texto.
- **Plantillas.** `umbrales.PLANTILLAS` tiene una por grupo. Cada `{ID}` es un número, o una lista, escrito como en el texto.
  `traducir` exige `re.fullmatch` sobre la fila: si el texto cambia fuera de los números, la traducción falla en vez de
  desviarse.
  - Un mismo id puede aparecer dos veces, como el 100 de «HR < 100» y «HR = 100»; la traducción exige que valgan lo mismo.
  - Los ceros y cientos definicionales («rapidez > 0», «u = v = 0») quedan literales en la plantilla.
  - Las barras escapadas del original («\\|Δz_b\\|») se conservan tal cual, como dice la nota del JSON.
- La lista de ids por grupo está en el **Anexo P** de este documento.

### 4.3 Comparación del JSON con el Anexo A (`test_umbrales.PruebasM1Umbrales`)

1. `regenerar_desde_texto(texto_v2.1)` rehace el JSON con el algoritmo de `m0/preparar_m0.anexo_a`:
   - las líneas «|» de la sección entre «## Anexo A.» y «## Anexo B.», partidas por «|» no escapadas;
   - 27 filas y 27 grupos distintos;
   - `json.dumps(…, ensure_ascii=False, indent=1)` más un salto de línea.
   Debe reproducir `meteo_combinada_v1.json` **byte a byte** (`156587f1…`).
2. `opciones_m0` no sale del Anexo A. Se compara con `OPCIONES_M0` de `m0/preparar_m0.py`, leído por AST con su huella
   `49503a3a…` (MC-35). `D2` = 8 es el número de procesos que usa `orquestacion`.
3. `comparar(publicado, regenerado)` es estricto (tipos y orden de claves) y debe dar `[]`.
4. `traducir` sobre las filas publicadas da todos los ids del Anexo P sin error, y cada valor coincide con el del texto.
5. `constantes.verificar_contra_texto(texto) == []`, y `constantes.completitud(texto) == []` (§4.4).
6. El sha256 del JSON y del texto van al addendum. `cargar_umbrales(…, sha256_json=…)` lo exige fuera de `--sintetico`.

### 4.4 Anexo A2

- **Qué entra.** Todo número normativo de §2 a §9 y del Anexo B que no esté en el Anexo A. Por ejemplo:
  - **TF:** las cotas de §5.7 (0,05/0,15 K; 0,10/0,25 K; 0,05/0,15 m/s; 0,10/0,30 hPa); la red histórica (2.000 h en
    2000-2009); la red constante (50 %, 22 de 26 años, 10 estaciones, 80 % en 2003-2025 y en 2010-2025); los períodos
    2015-2019, 2020-2024 y 2015-2024; el 10⁻⁶ de A, C y C_est;
  - **compuerta de deriva y S6:** 0,3 K por década, 2010, 20 y 120 estaciones, −1,5 K;
  - **ERA5-Land:** los meses de validez (200001, 201307 y 202507) y los rangos de unidades (200-330 K, 40.000-110.000 Pa y
    30 m/s);
  - **métricas y estratos:** las alturas de los estratos (500 y 2.000 m); los períodos 2000-2009 y 2010-2026; 2010-2023
    y ≥ 10 valores del CD; los cuantiles de §5.8;
  - **decisión y avisos:** el 99 % de E0; el 15 % del aviso SINCA;
  - **§7.2:** el 0,8 y el [0,5; 2] de la representatividad;
  - **§9:** los criterios de las pruebas (por ejemplo 20 h y 50 h en S1, 15 m, 5 m y 1,5 hPa en S4, 0,3 K y 0,2 K en S5,
    1e-9 en S14, 470 y 1.085 hPa en S15);
  - **Anexo B:** las 7 condiciones y «½·σ²».
- **Qué no entra.** Números que no son reglas: conteos de §1, cifras de costo, fechas de historia, números de línea y
  huellas. Van en una lista explícita `NO_NORMATIVOS` con su motivo. `completitud` falla si aparece un número normativo
  sin constante ni exclusión.
  - **Lectura:** «normativo» es todo número de §2-§9 y del Anexo B fuera de las tablas de costo de §7.1 y §8 y de los pasajes
    marcados como «Costo». En el reloj, la completitud sobre el cuerpo entero dejó 113 de 175 comparaciones sin fragmento
    propio, porque repetían el Anexo B: aquí la repetición de un valor del Anexo A en el cuerpo se acepta si el fragmento
    del cuerpo calza con el id del Anexo A (`ajenos`).
- **Salida.** `constantes.anexo_a2` genera `anexo_a2.json` (id, valor, sección, fragmento y sha256 del texto), que va a la lista
  cerrada del addendum.

### 4.5 Detector de literales (`test_umbrales.test_literales`)

- Busca por AST, en todos los módulos salvo `umbrales.py`, `constantes.py` y `sintetico.py`, los literales numéricos que
  coinciden con un valor del Anexo A o del A2.
- **Lista blanca** de constantes matemáticas: 0, 1, 2, 12, 24, 60, 3.600, 100 (porcentaje), 1.000 (m ↔ km) y π.
- `TOLERADOS` registra las excepciones, cada una con su motivo, y se vacía antes de sellar M1. La marca «no-umbral» en el
  código vale sólo con su motivo, como en el reloj.
- Es heurístico: no ve umbrales que coinciden con la lista blanca (el 12 de las rachas, el 24 de los desvíos o el 2 del
  remuestreo). La revisión de M1 los repasa a mano.

### 4.6 Lo que fija el addendum de M1

- **Compuerta de deriva:** el resultado de S6 para B y AB (`deriva_s6.json`: media y P95 de TF2 frente a sus cotas). El que
  falla queda fuera de E0 en todos los usos (§5.7).
- **Recorte:** «mód 11 = 3» o «mód 23 = 3», desde `costo.proyectar` (§8). Nunca a mitad de corrida.
- Las lecturas [D] de §7.

---

## 5. Plan de pruebas

### 5.1 Pruebas S1 a S16 de §9

En los nombres de las pruebas, «sNN» es la prueba de §9. `test_meteo_combinada.test_indice_de_9_cada_prueba_tiene_prueba`
lee la numeración S1-S16 de §9 del texto anclado (con su sha256) y exige al menos una prueba «sNN» por número (AST de
`tests/`), y ninguna de un número que §9 no tiene. Otra prueba exige que ningún número dependa sólo de pruebas omitidas;
`EN_CURSO` queda vacía al cerrar M1.

| S | Qué (punto por punto) | Módulo | Datos sintéticos | Archivo y pruebas |
|---|---|---|---|---|
| S1 | Cada regla de §2.4: centinelas (Ts −40,0 también invalida Td y HR; QFE 500,0 también QFF); rachas (HR = 100 de 20 h no, de 50 h sí; Td con HR = 100 no; Ts, QFE y QFF de 12 h; viento > 0 constante 12 h); picos con f = 1 y 1,5, y salto único; Td > Ts + 0,5 (7) y recorte (8); doble condición (9) también bajo 0 °C, agua o hielo, con su conteo; aire seco (17, ≥ 6 h y ≥ 3 reportes); Td derivado (10); cero como norte (19) y regla SYNOP (11); calma persistente (12) y sin dirección (20); error grueso aislado, de 3-24 h (18) y de > 24 h; monotonía de `usable` y derivadas aparte; Q1, Q1z, Q2 y Q3 con su denominador | qc_dmc_meteo | tablas largas hechas a mano con el esquema de `cargar_dmc` (validado en S2 contra una salida real del código fijado); fondo sintético en la estación para la marca 13 | `test_qc_dmc_meteo.PruebasS1` (≈ 25), más una prueba de propiedad: con marcas al azar ningún `usable` pasa de False a True |
| S2 | Reglas de §2.2 y §2.3 escritas y releídas del JSON (números de Python) pasan `cargar_dmc`; fuera de los tramos de reloj nada es usable; G-HR, G-viento y «posible media horaria» inhabilitan lo suyo; un rechazo de `validar_regla_reloj_dmc` (huella del módulo de RELOJ y política sintética) deja sin regla; −240 sin veredicto se rechaza; `--aplicar` se niega sin C5 válido (sin registro, sha distinto, `post_hoc = true`, o `errata_post_c4 = true` sin una errata confirmada) | politicas, qc_dmc_meteo, verificar | artefactos de `run_download` (descargador `578fa26e…`) con `ClienteFalsoMC` y `GuardaFalsaMC`; política y registro de C5 sintéticos (`politica_reloj_sintetica`), cada caso en una carpeta distinta (MC-40) | `test_politicas.PruebasS2`, `test_qc_dmc_meteo.test_s02_*`, `test_verificar_meteo_combinada.test_s02_aplicar_se_niega_*` |
| S3 | K1 (decimales, segundos, minutos, recortes en 0,1 y 2 km); K3 con un DEM con máscara administrativa (pasa, falla, sin z_cat → z_s NASADEM y QFE sin regla); píxeles-punto en celdas con bordes oeste y sur cerrados; pendiente con cos φ (plano de pendiente conocida en −20° y −50°) | estaticas_nasadem | teselas `.hgt` sintéticas de 1/3.600° con NaN fuera de una máscara | `test_estaticas_nasadem.PruebasS3` |
| S4 | Traslado de 15 m con QFE y QFF coherentes → traslado; de 5 m → nada; barómetro de 1,5 hPa → inhomogeneidad; reducción estándar → real y horario diurno → 24 h, en 500, 1.000 y 2.500 m, no son traslado; ≤ 2 % de falsos quiebres en 200 series estacionarias | homogeneidad | `series_traslado` con ruido fijado en el addendum (MC-49) | `test_homogeneidad.PruebasS4` |
| S5 | Fondo exacto con campos lineales en la altura (bilineal, Γ, hipsometría y q), con estaciones arriba y abajo del píxel, z en metros y QFE con p_std(z_s); A recupera b con RMSE < 0,3 K, y el núcleo decae a 0 sin NaN; con estaciones cada 3 h y aeródromos diurnos, A sin saltos horarios > 0,2 K; perturbar la estación de prueba, su grupo y su amortiguador (P1 y P2) no cambia sus predicciones, bit a bit, en A, B, AB, C y C_est; un cambio de sensor de 1 K da un tramo y no pasa a B ni a AB | fondo_era5l, candidatos, particiones, homogeneidad | `mes_era5_netcdf` con campos lineales; `verdad` (fondo + b(x, m, h) + anomalías correlacionadas) | `test_fondo_era5l.PruebasS5`, `test_candidatos.PruebasS5` |
| S6 | 20 estaciones en 2000-2024 y 120 desde 2010 (MC-07); verdad sin tendencia; sesgo fijo del fondo de −1,5 K en los valles: B falla TF1; A, C y C_est dan exactamente 0 (≤ 10⁻⁶); AB pasa. Compuerta de deriva: deriva del fondo de 0,3 K por década; TF2 a B y AB; resultado a `deriva_s6.json` | tendencias, candidatos | `red_s6` con anomalías de media 0 por estación-mes-año (MC-50) y grilla de ≈ 25 comunas | `test_tendencias.PruebasS6` |
| S7 | `decidir_combinacion`: cada compuerta, E1 vacío, regla crónica (también el caso mixto), empates exactos y determinismo; todos los módulos rechazan escribir métricas o tablas con «fondo», «era5l», «sin_dmc», «correccion» o «R_» como sujeto, salvo `dmc_R_*` y las clases exentas (MC-02); ninguna salida contiene la mediana ni el MAD del residuo; la regla de soporte bloquea un estrato | decision, ceguera, salidas, validacion | `tablas_metricas`; corrida mínima con `GuardaResiduo`: centinelas inyectados en la mediana y el MAD, buscados en los bytes de toda salida | `test_decision.PruebasS7`, `test_ceguera.PruebasS7`, `test_salidas.test_s07_*`, `test_validacion.test_s07_soporte` |
| S8 | Días de 23 y 25 h; producto que varía por celda y pesos conocidos dan la media comunal esperada; esquema idéntico al de `meteo_civil_v3` | salud | grilla sintética con 3 comunas y pesos a mano; `fijados.esquema_meteo_civil_v3` por AST | `test_salud.PruebasS8` |
| S9 | Mismas entradas, mismas huellas (hilos en 1, y 1 frente a 2 procesos); interrupción y reanudación dan salidas idénticas | orquestacion, verificar | corrida mínima sintética de M3-4 y M5; interrupción simulada entre unidades | `test_orquestacion.PruebasS9` |
| S10 | Nada se escribe en `/Volumes` ni en los repositorios; sin red; sin procesos vivos al terminar | ceguera, verificar | `RegistroAccesos` en bloqueo sobre toda la batería; `SinRed`; conteo de hijos | `test_meteo_combinada.PruebasS10`, `test_ceguera.test_s10_*` |
| S11 | DD 270 con 10 kt → u = +5,144 m/s, v ≈ 0; DD 360 → v < 0; la DMC «desde» y la ERA5-Land «hacia» dan residuo 0 con el mismo viento | fondo_era5l, qc_dmc_meteo | una estación y un píxel sintéticos, por el adaptador real | `test_fondo_era5l.test_s11_*` |
| S12 | ERA5-Land con ciclo diario marcado y etiquetas DMC fabricadas por un camino propio (u + c h) con reglas −240 y −180 dan residuo 0; un error de ±1 h aparece en CD; una hora que no es HH:00 se rechaza | fondo_era5l, politicas, qc_dmc_meteo, validacion | `mes_era5_netcdf`, hojas DMC por `run_download`, política sintética con F(−4) y F(−3) | `test_fondo_era5l.test_s12_*`, `test_validacion.test_s12_cd` |
| S13 | t2m en °C o sp en hPa abortan; tp de m a mm; el primer incremento del mes es NaN si se lee solo, y no con meses contiguos; ventanas de RR06 que cruzan un mes; geopotencial corrido un píxel detiene M2a | fondo_era5l, qc_dmc_meteo, orquestacion | meses sintéticos en las unidades malas; geopotencial y parquet sintéticos corridos | `test_fondo_era5l.PruebasS13`, `test_orquestacion.test_s13_m2a_se_detiene` |
| S14 | Con corrección 0, z_x = z del píxel enlazado (sin Γ, sin ajuste de Td ni de p y sin Td ≤ T) y el enlace de `enlaces_productos.parquet`, el lector por celda reproduce civil, UTC−4 y regional de `config_v3.json` dentro de 1e-9 en un año (2024; MC-32); sólo «igual» o «distinto» y la diferencia máxima; no guarda el producto | salud | **real:** ERA5L 2024-01 a 2025-01, enlaces, pesos y productos v3 (sólo lectura, con `RegistroAccesos` que sólo permite esas rutas) | `test_salud.test_s14_regresion_aguda` (se omite con su motivo si falta un insumo, y entonces no se da por aprobada) |
| S15 | Ida y vuelta int16 en los extremos (p 470 y 1.085 hPa; T −60 y 50 °C; u ±60 m/s); `dd_990`, código QC presente, `interval_minutes` en float y límite en float32 quedan «no normalizables», contados por motivo y origen, sin tumbar la corrida | producto, qc_dmc_meteo | campos sintéticos; artefactos y políticas sintéticos con cada defecto | `test_producto.PruebasS15`, `test_qc_dmc_meteo.test_s15_*` |
| S16 | Anexo B con tablas sintéticas: las tres ramas; simetría; desempate en I; regla de O3; variante por contaminante; TF de contaminantes en 0 con A y C y ≠ 0 con un artefacto sembrado; ganador restringido para todos cuando la rama 3 rige en uno (rehaciendo sólo los grupos con B o AB); `intentos_m6.jsonl`; cada negativa de M6 | decision, tendencias, verificar | `tablas_m6` en `ESQUEMA_COMPARACION_M6`; fábrica de contaminantes falsa (función conocida de las columnas `mc_*`) | `test_decision.PruebasS16`, `test_tendencias.test_s16_*`, `test_verificar_meteo_combinada.test_s16_*` |

**Datos.**
- Toda fabricación ocurre en `tempfile.TemporaryDirectory`. `GuardaFalsaMC` mira la ruta léxica antes de resolver.
- La tabla larga de S1 se valida contra una salida real de `cargar_dmc` sobre un artefacto sintético, para que las pruebas
  a mano no se desvíen del esquema del código fijado.
- El HTML de `sintetico.hoja_html` sigue el formato de `reloj_dmc.sintetico.html_informe` (`GROUP_COLUMNS`,
  `LEAF_COLUMNS` y la tabla dos veces). Una prueba de paridad lo comprueba con los mismos textos.

### 5.2 Comprobaciones propias de M1 (fuera de S1-S16)

- `test_umbrales`: §4.3 y §4.5. `test_constantes`: fragmentos, completitud y paridad de la regla de números con la del reloj.
- `test_fijados`:
  - huellas del código fijado de §9.3 y de la clausura del reloj;
  - `validar_regla_reloj_dmc` cargado es el de `reloj_dmc.politica` y su archivo tiene la huella esperada;
  - `preflight_v3` nunca se importa;
  - no queda `_comun_modelo` ni `_common` en `sys.modules`.
- `test_meteo_combinada`:
  - la fachada: cada nombre de `NOMBRES_TEXTO` aparece entre comillas invertidas en el texto anclado, es el mismo objeto
    de su módulo, y la importación es perezosa (intérprete aparte con `-B -I`);
  - el grafo de §1, el índice de §9 y los nombres prohibidos (`descargar_*`, `download_*`);
  - la escritura sólo en `salidas`, `entorno` y `sintetico` (§0, regla 8), y que ni el paquete ni las salidas contengan una
    ruta de la carpeta de usuario ni el signo arroba (`entorno.sin_datos_privados`, la misma regla de privacidad del reloj).
- `test_ambiental`: las tablas laterales pasan por `meteorologia_v2.unir_sidecar` real sobre un panel sintético sin cambiar
  filas ni orden, y se niegan con metadatos falsos, claves faltantes o columnas solapadas (§7.1, punto 2: pruebas nuevas).

### 5.3 Salida de la batería de M1

`verificar_meteo_combinada.py --sintetico [--costo]` escribe en `LOCAL/meteo_combinada/v1/m1/`:
- `pruebas_m1.txt` (la salida de `unittest`);
- `resumen_m1.json`, con conteos, `ceguera.accesos` (debe ser 0) y huellas;
- `deriva_s6.json`, `anexo_a2.json` y `costo_m1.json`;
- `sha256.json`.

Sus huellas van al addendum. La batería corre bajo `RegistroAccesos` en bloqueo sobre `/Volumes`. Sólo S14 y la medición del
costo abren, en lectura, las rutas de ERA5L y de los productos v3 que se nombran.

---

## 6. Orden de implementación y dependencias

| Ola | En paralelo (un dueño cada uno) | Necesita | Entrega verificable |
|---|---|---|---|
| 0 | **I0** coordinador: `tipos` (esquemas y clases de datos), las firmas de §3, nombres de pruebas «sNN» omitidas, `COORDINACION_M1.md` | — | el esqueleto importa sin errores con el intérprete fijado, sin `__pycache__` y sin accesos a `/Volumes` |
| 1 | **I1** `entorno` + `fijados` (clausura del reloj) · **I2** `umbrales` + `constantes` (JSON byte a byte, Anexo P, A2, detector) · **I3** `numerico` + `particiones` · **I4** `ceguera` · **I5** `sintetico` | ola 0 | §4.3 en verde; huellas de §9.3; S10 parcial; generadores con esquemas iguales a `tipos` |
| 2 | **I6** `politicas` · **I7** `fondo_era5l` · **I8** `estaticas_nasadem` · **I9** `homogeneidad` · **I10** `decision` · **I11** `sinca_meteo` | ola 1; entre sí, sólo por firmas | S2 (parte), S3, S4, S5 (fondo), S11, S12 (fondo), S13, S7 (regla), S16 (ramas) |
| 3 | **I12** `qc_dmc_meteo` · **I13** `candidatos` · **I14** `validacion` | ola 2 (`qc` usa `homogeneidad.k4` y `fondo_era5l.residuos`; `candidatos` simula `homogeneidad` hasta que I9 entregue) | S1, S2, S5 (candidatos), S12 (CD), S15 (abortos), S7 (soporte) |
| 4 | **I15** `tendencias` · **I16** `producto` · **I17** `salidas` | ola 3 | S6 y la compuerta de deriva; S15 (int16); S7 (escritura) |
| 5 | **I18** `salud` · **I19** `ambiental` · **I20** `orquestacion` (integración) | ola 4 | S8, S14, unión con `unir_sidecar`, S9 y S13 (M2a) |
| 6 | **I21** `costo` · **I22** `verificar_meteo_combinada` + `addendum` + fachada | ola 5 | S2 (`--aplicar`), S16 (negativas), S10 completo; batería y costo medidos; addendum |

- **Camino crítico:** `fondo_era5l` → `candidatos` → `tendencias` → `orquestacion` → `costo`. `candidatos` es el módulo más
  pesado: conviene dárselo a quien implementó `lineas_fisicas` en el reloj.
- **Hitos de integración:**
  1. una estación sintética de punta a punta (artefacto → política → `cargar_dmc` → envoltorio → tabla ancha), con la
     ciencia simulada;
  2. una red de 30 estaciones con A y B reales, P1 y P2, y una evaluación completa;
  3. TF de S6 con todos los candidatos;
  4. **una red de 579 estaciones sintéticas a escala real en un pliegue externo, y un año de TF**: es la base de la
     proyección de §8, antes de medir el resto.
- **Revisión de M1:** un revisor que no implementó el módulo lo contrasta con el texto, sección por sección, y busca refutar
  sus hallazgos, como en las olas 4a y 4b del reloj. Prioridad: §2.4, §2.5 (K4), §4.2-§4.9, §5.2-§5.7, §6.2 y el Anexo B.
  Después se regenera el anexo de firmas.

---

## 7. Riesgos de interpretación

**Marcas:**
- **[E]:** pide una enmienda ciega antes de la frontera (§10), porque el texto se contradice o calla en algo que cambia
  resultados.
- **[D]:** lectura propuesta que debe fijarse en el addendum de M1 como cambio de implementación. Si el autor la ve como cambio
  de regla, pasa a [E].
- **[M]:** menor; la lectura propuesta basta y se documenta.

Los ids MC-nn son de este diseño y no se reutilizan.

### 7.1 Contradicciones y vacíos del texto v2.1 (con su cita y una propuesta)

- **MC-01 [E] CONTRADICCIÓN. Q1 nunca puede saltar por la marca 3.**
  - **Cita:**
    - §2.7: «Una marca invalidante de §2.4 (bits 3-17) quita más del 10 % de las horas de la red en una variable.
      Denominador: las horas con `usable = True` en `cargar_dmc`, antes del envoltorio.»;
    - §2.1: «`usable = True` en `cargar_dmc` (reloj, coordenadas, medición y rango)».
  - **Problema:** las horas fuera de rango (bit 3) ya tienen `usable = False`, así que no están en el denominador, y Q1 de
    la marca 3 vale siempre 0.
  - **Propuesta:** para la marca 3, el numerador son las filas con `quality_reason = "documented_numeric_range_rejected"` y
    el denominador las filas con `model_ready = True` (reloj, coordenadas y medición). Las demás marcas no cambian. La
    lectura literal es implementable (Q1 vacía para la marca 3): no bloquea M1, pero deja sin alarma el rango.

- **MC-02 [D, o E si el autor lo prefiere] CONTRADICCIÓN. El vocabulario prohibido de S7 frente a tablas que el texto exige
  guardar.**
  - **Cita:**
    - S7: «Todos los módulos … rechazan escribir métricas o tablas con los identificadores «fondo», «era5l», «sin_dmc»,
      «correccion» o «R_» como sujeto, salvo las columnas de entrada `dmc_R_*` de D»;
    - §2.1, precondición 2: «M2a cerrado … climatologías del estado y fondo en las estaciones, con sus huellas»;
    - §7.1: `mc_bloque` lee «las tablas de residuos de las estaciones»;
    - Anexo B: «`fe_*`, el fondo reescalado a la celda del monitor»;
    - §8, «Cadena de huellas»: «cada mes de ERA5-Land»;
    - §2.6: la validación de la lluvia de ERA5-Land con RR06.
  - **Problema:** el fondo en las estaciones y las climatologías del estado son tablas cuyo sujeto es el fondo; las de
    residuos son series de obs − F, que §0.4.2 llama «métrica del fondo» si se resumen; la cadena de huellas nombra
    archivos de ERA5-Land; y la tabla de RR06 compara la lluvia de ERA5-Land con observaciones, que §0.4.2 sí permite.
  - **Propuesta:** la guarda se aplica por clase de salida (`ceguera.vigilar_salida(…, clase=…)`):
    - **métrica** y **resumen** (`validacion/`, `tendencias/`, `decision.json`, `resumen_qc.json`, informes y consola):
      vocabulario prohibido como sujeto, salvo `dmc_R_*` en D y la tabla de RR06, cuyo sujeto es «lluvia_producto»
      (§2.6 dice que la lluvia del producto es la de ERA5-Land);
    - **insumo** (`insumos/`, `producto/residuos/`, `ambiental/`): permitido. No se resume ni se abre antes del final de
      M3-4, y una prueba exige que ningún módulo de métricas lea esas rutas salvo `candidatos` y `producto`;
    - **procedencia** (recibos y huellas): permitido, sólo con rutas y sha256, sin valores.

- **MC-03 [E] VACÍO. TF2 «no evaluable» no dice si TF pasa.**
  - **Cita:**
    - §5.7: «Si ninguna alcanza 10, TF2 no es evaluable y se declara.»;
    - «Pasa si se cumplen las dos cotas»;
    - §6.2, paso 5: «al menos uno de ellos falla TF».
  - **Problema:** sin regla, B y AB quedan en un estado indefinido en la compuerta TF y en la regla crónica.
  - **Propuesta:** con TF2 no evaluable, TF se decide sólo por TF1, con la nota «TF2 no evaluable» en `decision.json`, y
    «falla TF» sólo cuenta pruebas evaluadas. La alternativa conservadora es tratar «no evaluable» como falla para B y AB.
    El autor elige; no hay valor por omisión, porque cambia el ganador posible.

- **MC-04 [D] VACÍO. TF no tiene dimensión de uso, pero el producto de un candidato sí.**
  - **Cita:**
    - §5.7, «Qué se guarda: por candidato × variable × prueba, la media y el P95 ponderados»;
    - §4.2: hiperparámetros «elegidos por candidato, variable y uso»;
    - §3: en lo ambiental, z = media NASADEM; en salud, z poblada.
  - **Problema:** el producto de B o AB en las celdas pobladas cambia con el uso (hiperparámetros y altitud de la celda), y
    §6.1 aplica TF por uso.
  - **Propuesta:** TF por candidato × uso × variable, con los hiperparámetros y la altitud de la celda de cada uso. Agudo y
    crónico comparten hiperparámetros (MC-55) y z poblada, así que sus TF coinciden y se calculan una vez. En lo crónico,
    TF sólo en T (como CD y MZ, §6.1).

- **MC-05 [D] AMBIGÜEDAD con lectura literal perversa. El peso de las filas de C.**
  - **Cita:** §4.6: «Filas: hasta 4.000 horas válidas por estación, al azar (semilla 20261023), con peso mín(4.000/n_s; 10).»
  - **Problema:** si n_s son las horas válidas de la estación, una estación con 200.000 horas pesa 4.000 × 0,02 = 80 en
    total, y una con 400 horas pesa 4.000. Se invierte el propósito, que es que cada estación aporte lo mismo.
  - **Propuesta:** n_s = número de filas de s en la muestra (= mín(4.000, horas válidas)). Da peso 1 a las estaciones con
    ≥ 4.000 horas y hasta 10 a las pequeñas. Coincide con la literal cuando n_s ≤ 4.000.

- **MC-06 [D] DEFINICIÓN CIRCULAR en K4 y en §4.8.**
  - **Cita:** §2.5: «H*(k) son las horas UTC con mediana en ≥ 80 % de los meses válidos de cada lado … Un mes es válido con
    ≥ 100 pares y mediana en todas las horas de H*(k).»
  - **Propuesta:** dos pasos.
    1. Los meses candidatos son los que tienen ≥ 100 pares; H*(k) sale del 80 % de los candidatos de cada lado.
    2. Los meses válidos son los candidatos con mediana en todas las horas de H*(k).
    Además:
    - ventanas: antes = k−12 … k−1 y después = k … k+11;
    - segmentación binaria codiciosa: en cada paso, el mayor |D| sobre el umbral entre todos los tramos, con D(k)
      recalculado dentro del tramo (ventanas recortadas al tramo, ≥ 6 meses válidos por lado y ≥ 12 meses a cada lado del
      corte), hasta 3 quiebres.

- **MC-07 [D] AMBIGÜEDAD que decide si la compuerta de deriva es evaluable.**
  - **Cita:** S6: «20 estaciones en 2000-2009 y 120 en 2010-2024».
  - **Problema:** si las 20 terminan en 2009, no hay red constante (22 de 26 años), TF2 no es evaluable y la compuerta de
    deriva no decide nada.
  - **Propuesta:** las 20 siguen de 2000 a 2024 y las 120 aparecen en 2010. Es lo que dice la compuerta: «estaciones que
    aparecen en 2010».

- **MC-08 [D] VACÍO. El producto de 0,1° no dice con qué ganador se hace.**
  - **Cita:**
    - §3: «0,1°: en los centros de los 8.206 píxeles ERA5-Land válidos … Se guarda.»;
    - §8: «`producto_01deg/`: un NetCDF mensual».
  - **Problema:** hay tres usos con ganadores y hiperparámetros quizá distintos.
  - **Propuesta:** el ganador y los hiperparámetros ambientales (el producto general, el más cercano a la grilla de ≈ 1 km).
    Los de salud se producen sólo a escala de celda. El uso va en los atributos del NetCDF.

- **MC-09 [D] VACÍO que exige R21 de la Enmienda 2 ambiental. Red ampliada en π^mon y en M6.**
  - **Cita:**
    - §5.3: «monitores de PM2,5 y NO2 de `pliegues_v2.json`»;
    - §7.1: «claves … del panel v1, leído en sólo lectura»;
    - R21: «π^mon usa el `pliegues_v2.json` de este bloque, con su huella en el registro de la red. Las tablas laterales de
      M6 se arman sobre el panel de R11.»
  - **Problema:** las negativas de M3-4 (§10) no incluyen el «Registro de la red v2», que R22 sella antes de M3-4.
  - **Propuesta:**
    - el addendum registra la lectura de R21;
    - M3-4 se niega si falta el anexo «Registro de la red v2» confirmado en git, o si la huella de `pliegues_v2.json` difiere
      de la registrada;
    - «monitor-año con datos» = (estación, año UTC) con alguna fila con observación del contaminante en el panel que cita
      `pliegues_v2.json` (`contaminantes.<pol>.panel`);
    - las coordenadas son las de `estaciones` de ese archivo;
    - M6 exige la huella de `panel_{pm25,no2}_red2.parquet` del mismo registro.

- **MC-10 [D] VACÍOS de §5.6 (meteorología SINCA). Es descriptiva y no cambia la decisión, pero hay que fijarla antes de
  verla.**
  - **Cita:**
    - §5.6: «se lee con su política temporal (`config/sinca/politica_temporal.json`)»;
    - §1.11: «su control de calidad le toca al lector de §5.6»;
    - R7 de la Enmienda 2 ambiental: «La regla general es UTC−4 fijo, con la etiqueta en el fin del intervalo».
  - **Problemas:**
    1. **Reloj:** la política dice «hora_local_civil_sinca_sin_offset», pero R7 halló, para los contaminantes, que la regla
       general es UTC−4 fijo, salvo un veredicto «hora civil».
    2. **Semántica:** el valor SINCA es una media horaria, y el producto es instantáneo.
    3. **Control de calidad:** no está fijado.
    4. **Varias series por estación y variable** (alturas e instrumentos distintos).
    5. **Segundo manifiesto:** `manifiesto_descarga_20261024b.csv` (`1c0a1567…`) y su `SHA256SUMS_20261024b.txt`
       (`87d659d5…`) no están en las huellas de M0.
    6. **Variables:** el segundo trae PRES, RAIN y GLOB.
  - **Propuesta:**
    1. reloj de R7: UTC−4 fijo con la etiqueta al fin de la hora, o la zona IANA de la región si la verificación corregida
       de la Enmienda 2 (`reloj_sinca_v2.py`) dio «hora civil» para esa estación y año en algún contaminante;
    2. la media SINCA de la hora [u−1, u] se compara con la media del producto en u−1 y u;
    3. rangos de §2.3 para TEMP (como Ts), RHUM (como HR, con el recorte a 100), WSPD y WDIR, y centinelas del descargador
       SINCA; sin rachas ni picos;
    4. por estación y variable, la serie de altura más cercana a 2 m (TEMP, RHUM) o a 10 m (WSPD, WDIR); en un empate, la de
       más filas con observación, y luego la de menor ruta;
    5. los dos manifiestos y sus huellas entran en la lista cerrada;
    6. sólo TEMP, RHUM, WSPD y WDIR (B13 autorizó «temperatura, HR y viento»).

- **MC-11 [M] Inconsistencia de redacción.** §2.3 dice «Sin z_s legible, QFE queda sin regla», pero §2.5 da z_s desde NASADEM
  cuando falta z_cat («z_s = NASADEM bilineal en el punto y QFE sin regla»). Lectura: «sin z_cat legible».

- **MC-12 [D] ¿Qué es «el lector por celda» de S14?**
  - **Cita:**
    - S14: «el lector por celda reproduce las carpetas civil, UTC−4 y regional»;
    - §7.2: «`meteo_combinada_v3.py` (nuevo): lector del producto a escala de celda», en `v3_next` de APH.
  - **Propuesta:** el núcleo del lector es `salud.py` (AP, M1), y S14 lo prueba. `meteo_combinada_v3.py` será un adaptador
    delgado de APH, escrito por la Enmienda 4, que llama a `salud.py` y no cambia los números.

- **MC-13 [D] La lluvia «igual que hoy» frente a las celdas y pesos de T.**
  - **Cita:** §7.2, punto 1: «en las celdas … con `cod_comuna > 0`, w_ghs > 0 y producto finito … La lluvia (`precip_mm`)
    sigue desde ERA5-Land, igual que hoy.»
  - **Problema:** T y Td salen del operador bilineal con vecino a ≤ 16 km, que cubre celdas costeras que `meteo_civil_v3`
    deja fuera. La lluvia de hoy usa el enlace celda → píxel.
  - **Propuesta:** `precip_mm` se calcula exactamente como en `meteo_civil_v3` (enlace, sus celdas y sus pesos), así que es
    bit a bit la de hoy (S14 lo cubre). T, Td y HR usan las celdas con producto finito. La diferencia de soporte entre
    variables se declara.

- **MC-14 [M] Cifra de costo.** El Anexo B dice «≈ 17.000 celdas × ≈ 12.500 h ≈ 2,2·10⁸ filas». Con los días de mód 11 = 3
  de 2015-2024 son 332 días = 7.968 h, y 345 × 50 × 7.968 ≈ 1,37·10⁸ filas. No es una regla; va como nota.

- **MC-15 [M] Tamaño del operador.** §7.1 estima `operador_grilla` en ≈ 200 MB. Con 838.430 celdas, hasta 30 vecinos y 4
  juegos de hiperparámetros (T, Td, (u, v) y p), queda en ≈ 0,5-1 GB según L. M1 lo mide.

- **MC-16 [M] El disparador de 36 h no es un tope.** La TF domina el costo de M3-4 (§8) y el mód 23 sólo abarata la selección
  anidada. §8 prohíbe otro recorte, así que M3-4 dura lo que dure. Se informa.

- **MC-17 [D] Clausura del reloj.**
  - **Cita:** §2.1: «El código fijado (`meteorologia_v2.py`, `dmc_features.py`, `preflight_v3.py` y RELOJ) no se modifica.»
  - **Problema:** `reloj_dmc.politica` importa `constantes`, `entorno`, `fijados`, `tablas` y `tipos` del reloj; el código
    del reloj aún no se sella (su C1 no aprobó) y no está en git.
  - **Propuesta:** la huella del reloj es la de esos seis archivos (`fijados.MODULOS_RELOJ`).
    - Va al addendum si el C1 del reloj cerró antes de sellar M1; si no, al registro de M2a (declaración de M0).
    - `cargar_validador_reloj` comprueba las seis huellas antes y después de importar.
  - [2026-10-27, decisión E5-F del autor: el C1 del reloj cerró de nuevo tras su Enmienda 5 (código AP `1da0236`, texto
    v1.2 en APH `1f59e6e`, addendum en APH `73615e8`). La clausura, con el `__init__` (FIJ-8), son las siete huellas de
    AP `1da0236` (`fijados.HUELLAS_RELOJ`) y va al addendum de M1. La del primer cierre, AP `4b50b0d`, queda como
    historia; entre las dos sólo cambió `constantes.py`.]

- **MC-18 [D] RELOJ tiene ahora cuatro enmiendas.**
  - **Cita:** encabezado: «con las enmiendas que se anclen antes de su C4. Hoy son dos».
  - **Propuesta:** el addendum registra las Enmiendas 3 (`e43a6fe`) y 4 (`261c44f`) y el texto v1.0.4 (`d8f61cfc…`), con la
    comprobación de que §3.3 y §7 no cambian (hecha al escribir este diseño: los dos son idénticos, línea a línea, entre el
    v1.0.2 y el v1.0.4, y `texto_7_5.md` sigue en `58362640…`).
  - E3-5 cambia el cálculo de ρ en §4.3.5 de RELOJ, y por eso qué estaciones llevan «posible media horaria». Este texto sólo
    consume la marca.

- **MC-19 [D] La lista K2 vive en tablas que §1.9 no deja abrir.**
  - **Cita:** §1.9: «consume sólo la política, `artefactos_evaluados` y, por código, la lista de «coordenadas
    inconsistentes» (K2). Nadie de ese equipo abre el informe ni las tablas de evidencia del reloj».
  - **Problema:** el reloj publica esa lista en la clave `coordenadas_inconsistentes` de su informe y en la columna de
    `pixeles_dmc.parquet`, no en la política.
  - **Propuesta:** `politicas.coordenadas_inconsistentes` lee por código sólo esa clave del informe (o sólo las columnas
    `codigo` y `coordenadas_inconsistentes` del parquet, por proyección de columnas). No la imprime; su huella va al
    registro de M3-4. `ceguera.permitido_de_reloj` deja pasar sólo esa lectura.

- **MC-20 [D] Un archivo de pruebas o varios.**
  - **Cita:** §8: «las pruebas en `tests/test_meteo_combinada.py`».
  - **Propuesta:** un archivo por módulo, con su dueño. `test_meteo_combinada.py` conserva el índice S1-S16, la fachada, el
    grafo y S10. Es la lectura R-35 del reloj.

- **MC-21 [D] Abortos por los datos y por la regla.**
  - **Cita:** S15: «`interval_minutes` en float y límite en float32 quedan «no normalizables», contados, sin tumbar la
    corrida».
  - **Problema:** esos dos son defectos de la regla, no del artefacto. Contarlos como «no normalizables» puede esconder un
    error de código.
  - **Propuesta:** se cuentan como dice el texto, pero con `origen` = «datos» o «regla», según si `normalizar` aborta
    también sin política, como la comprobación 7 de RELOJ. Un aborto de origen «regla» en `--aplicar` suma a Q3 y además
    va a las desviaciones del informe.

### 7.2 Lecturas que deben fijarse en el addendum de M1 [D]

- **MC-22.** «Cubren el lapso» (rachas) y «dura» (desvíos de la marca 13 y aire seco).
  - La duración de una sucesión de dos o más reportes es t_último − t_primero + p, con p la mediana de sus Δt (1, 2 o 3 h).
    Coincide con la R-15 del reloj (n·p) en series regulares.
  - Un reporte suelto cuenta siempre como «< 3 h», también en una serie cada 3 h, porque el texto lo dice («incluye el
    reporte suelto»).
- **MC-23.** Picos y saltos.
  - «Consecutivos» exige Δt ≤ 3 h a cada lado. f usa el mayor de los dos Δt (f = 1 sólo si los dos son de 1 h).
  - El salto único invalida sólo el valor posterior.
  - Se buscan sobre los valores que pasaron centinela y rango.
- **MC-24.** Orden de las reglas del envoltorio, y qué ve cada una.
  1. Bits 0-3, de `cargar_dmc`.
  2. Centinelas (4).
  3. Rachas (5) y calma (12).
  4. Picos y saltos (6).
  5. Td frente a Ts (7, 8).
  6. Incoherencia (9).
  7. HR recortada (15).
  8. Td derivado (10).
  9. Viento (11, 19, 20).
  10. Aire seco (17).
  11. Error grueso (13, 18).
  12. K4 y retirada (1, 16).
  13. Marca 14.
  Cada regla mira sólo los valores que siguen válidos tras las anteriores. Las derivadas nacen después de las reglas de sus
  fuentes.
  **Corrección por la decisión D7 del autor (2026-10-26; `APH/auditoria/20261023/meteo_combinada/enmienda1/`):** la marca 4
  es la excepción. Mira el valor de la fuente aunque el rango ya lo haya quitado, como dice §2.4: Ts = −40,0 invalida
  también Td y HR, QFE = 500,0 invalida QFF, y una hora puede llevar las marcas 3 y 4. Va al addendum de M1.
- **MC-25.** La marca 9 bajo 0 °C.
  - «Sobre hielo» lee Td como punto de escarcha: e = e_i(Td), y la HR se calcula siempre respecto del agua,
    HR_M = 100·e/e_s(Ts), como la OMM.
  - «Calza» quiere decir que la doble condición no se cumple con alguna de las dos.
  - Se cuenta cuál calzó: agua, hielo o las dos.
- **MC-26.** Base de la marca 13.
  - La mediana y el MAD se calculan sobre las horas válidas tras los pasos 1 a 10 de MC-24, una sola vez, sin iterar.
  - En Td se usa `td_final` con origen observado o recortado; el derivado no entra en la base y no se marca.
  - La marca 13 de Td invalida sólo Td.
- **MC-27.** Hueco circular. Es la mayor distancia, en horas, entre horas observadas consecutivas sobre un círculo de 24 h
  (A) o de la duración del día civil (día válido). Cada 3 h da hueco 3 y pasa; cada 5 h, no.
- **MC-28.** Nombres y convenciones de las columnas de §7.1 y del Anexo B.
  - Sufijos de `el_*`: `t2m`, `d2m`, `rh`, `sp`, `u10`, `v10`, `wind`, `wdir_sin` y `wdir_cos`, con los prefijos `mc_` y
    `fe_`.
  - Unidades de `el_*`: K, Pa, %, m/s y adimensional.
  - Dirección: `arctan2(u, v)` como `_features.py`.
  - `dmc_R_v` es el R de §4.1 antes del mín y de la exponencial (`dmc_R_p` = R_p, adimensional).
  - En `mc_*`, Magnus con 17,625 y 243,04.
- **MC-29.** CD y EX «se agregan como S»: con el cuadrado. CD = √(Σ_b π_b · media_b(CD_e²)), y lo mismo con EX_e.
- **MC-30.** Interfaz de M6 con v2.
  - Las 7 condiciones citan la Enmienda 1 ambiental y su Complemento, cuyas cifras salen de la maquinaria v2.
  - `decision.condiciones_anexo_b` lee una tabla `ESQUEMA_COMPARACION_M6` (§2.3) que la enmienda de la DMC obliga a v2 a
    producir; M1 prueba la regla con esa tabla (S16).
  - Si la enmienda fija otro formato, cambia sólo el lector.
- **MC-31.** La batería de M1 lee datos reales que no son DMC: S14 (ERA5L 2024-01 a 2025-01, enlaces, pesos y productos v3) y
  un mes de ERA5L para el costo. `--sintetico` bloquea todo `/Volumes` salvo esas rutas, sólo en esas dos pruebas.
- **MC-32.** Año de S14: 2024 (bisiesto, con los dos cambios de hora, y el mismo que leyó el revisor de M0). Se compara la
  serie entera del año en las tres carpetas.
- **MC-33.** MZ. S_c,z usa los π_b del uso (nacionales) y las evaluaciones de la macrozona; las bandas se unen con la regla de
  §5.3 dentro de la macrozona; se exige por variable (T y HR en (T, Td)).
- **MC-34.** Remuestreo. Cada réplica repite todo: la unión de bandas, los mínimos de S_par sobre E0 y el ganador. Los
  bloques que se sortean son los de P2 que tienen estaciones.
- **MC-35.** `opciones_m0` del JSON no sale del Anexo A. Se excluye de la regeneración y se compara con `OPCIONES_M0` de
  `preparar_m0.py` (§4.3, paso 2).
- **MC-36.** Hilos.
  - El paquete fija las tres variables en «1» al importarse, si numpy no está cargado.
  - Si ya lo está, `entorno.fijar_hilos` usa `threadpoolctl` y falla si no quedan en 1.
  - Los procesos hijos heredan las variables.
- **MC-37.** Tamaño fijo del lote (un mes UTC) y orden fijo de agregación (por estación, por mes y por comuna), para que el
  resultado sea idéntico con 1 y 8 procesos. Las sumas se hacen en float64.
- **MC-38.** Alineación del geopotencial: «coincidir píxel a píxel» es |z_E5L − z_parquet| ≤ 0,001 m en los 9.725 píxeles,
  con los mismos `pixel_id`.
- **MC-39.** «Vecinos sin dato» (§4.1): los píxeles que no son válidos según la regla de los tres meses (estático). Si un
  píxel válido no trae dato en una hora, se renormaliza esa hora y se cuenta en el registro.
- **MC-40.** `validar_regla_reloj_dmc` guarda en memoria cada publicación por ruta (`_PUBLICADAS`). Las pruebas usan una ruta
  distinta por caso.
- **MC-41.** A en el tiempo.
  - El centro de un mes es el punto medio entre su primera y su última hora UTC.
  - La interpolación es lineal y cíclica (diciembre con enero), porque la climatología no tiene año.
  - Cada mes usa sus estaciones calificadas.
- **MC-42.** La anomalía de AB es a_s(u) = r̃_s(u) − r̄_s(m, h), con m el mes de u y sin interpolar, literal. h es siempre la
  hora UTC.
- **MC-43.** u y v comparten hiperparámetros (L, λ, κ): se eligen juntos, con el RMSE vectorial como objetivo, porque el grupo
  (u, v) tiene un solo ganador.
- **MC-44.** Los días de selección son los de la fecha UTC de la hora. Las semillas son subsecuencias de
  `SeedSequence([20261023, huella(etiqueta)])`, con etiquetas fijas por uso: «P1», «internos/<pliegue>», «C/<código>/<variable>»,
  «remuestreo» y «tf_contaminantes». Así ningún muestreo depende del orden en que se llamen.
- **MC-45.** Lo que depende sólo de la estación se calcula una vez (§3): r̄, tramos, δ, la muestra de filas de C y sus sumas
  X'X y X'y. Cada pliegue suma sólo las de sus estaciones de entrenamiento, en orden de código. La estandarización de C se
  deriva de esas sumas.
- **MC-46.** P2 y los grupos. Un grupo a ≤ 2 km va entero al bloque de su miembro de menor código, para que «se validen
  juntas» (§2.5).
  - P1: los grupos se ordenan por id, se permutan con la semilla y se reparten en rueda en 10 pliegues (tamaños que difieren
    a lo más en 1).
  - Pliegues internos: los bloques de 75 km del entrenamiento se reparten igual en 5.
- **MC-47.** Red constante de TF2.
  - «≥ 50 % de horas válidas» se mide sobre las horas UTC del año: las estaciones sinópticas cada 3 h no la alcanzan nunca.
  - La pendiente se toma sobre los años de la regla que rigió (2000-2025, 2003-2025 o 2010-2025).
  - TF1: Δ_c es la diferencia de las medias de las medias anuales.
- **MC-48.** Cuantil ponderado: el menor valor cuyo peso acumulado alcanza 0,95, sin interpolar. El peso de una comuna es su
  Σ w_ghs de 2020.
- **MC-49.** Ruido de S4. En T2b, un AR(1) diario con σ = 0,7 hPa y τ = 2 días, más ruido horario de 0,3 hPa; en z_impl, σ
  = 5 m. Se fija en el addendum antes de correr S4: el 2 % depende de él.
- **MC-50.** Anomalías de S6. Correlación espacial de 100 km, σ = 1,5 K y media exactamente 0 en cada estación-mes-año, para
  que «AB pasa con sesgos estacionarios» pruebe el método y no el ruido de muestreo de cinco años.
- **MC-51.** E0, «≥ 99 % de los puntos con fondo»: se mide sobre las celdas pobladas y todas las horas de la pasada de TF, y
  sobre las estaciones de validación.
- **MC-52.** Representatividad (M5). «El píxel del RELOJ» se recalcula con su regla (`reloj_dmc.extraccion.elegir_pixel`,
  15 km), sin abrir `pixeles_dmc.parquet`. El cociente de amplitudes es el de los ciclos diarios medios por hora UTC.
- **MC-53.** Política de lectura y política efectiva.
  - `cargar_dmc` corre con la de lectura (tramos de RELOJ partidos por los años G).
  - La publicada (`politicas_meteo_v1.json`) es la efectiva: además de lo anterior, parte por los quiebres de K4 y marca
    `coordinates.verified = false` antes del último traslado.
  - Una prueba comprueba que releer con la efectiva da el mismo conjunto de filas usables de coordenadas que la marca 1 del
    envoltorio.
- **MC-54.** El addendum de M1 es `APH/auditoria/<fecha de M1>/meteo_combinada/m1/addendum_m1.json` (y su `.md`): lista
  cerrada `{ruta por alias: sha256}`, `commit_m1` de AP y de APH, anexo A2, deriva, recorte, costo y lecturas. Se pasa por
  argumento a `--estaticos`, `--aplicar`, `--producir` y `--m6`.

### 7.3 Lecturas menores [M]

- **MC-55.** Agudo y crónico tienen el mismo objetivo de selección (RMSE horario con π^pob), así que comparten
  hiperparámetros de A, B y AB; se eligen una vez. C_est es sólo crónico.
- **MC-56.** «Cuyo código pasó M1» (E0) = todos los candidatos, porque M1 exige S1-S16 completas.
- **MC-57.** Se capturan sólo `ValueError` y `TypeError` (§2.1): `json.JSONDecodeError` es un `ValueError`; un `KeyError` u
  `OSError` detiene la corrida como error de código.
- **MC-58.** «Estación-año» (regla del cero, años G) es el año de la etiqueta, como en RELOJ.
- **MC-59.** K1: 1° = π·6.371/180 km, sin cos φ (conservador). Con precisiones distintas en latitud y longitud, rige la más
  gruesa.
- **MC-60.** Haversine con R = 6.371 km también para el radio de 16 km. Los empates se rompen por menor `pixel_id` o menor
  código.
- **MC-61.** La regla de soporte no se aplica al agregado nacional, que §0.4.4 no nombra. Un estrato se evalúa por partición
  y en el agregado, y no se publica si falla en cualquiera.
- **MC-62.** Si el catálogo no trae OMM, tipo o propietario, esos estratos no se forman y se declara (R-50 del reloj).
- **MC-63.** «Empate exacto» es la igualdad en float64.
- **MC-64.** Estación del año en §2.6: DEF, MAM, JJA y SON.
- **MC-65.** La HR evaluable cuenta las horas con `hr_final` válida. r̄ de A se calcula sobre r (sin homogeneizar), como
  muestra la cuenta de §4.5: así las anomalías de AB tienen media 0 por tramo.

### 7.4 Resumen para el autor

| Tipo | Riesgos | Qué hacer |
|---|---|---|
| Contradicciones del texto | MC-01 (Q1 de la marca 3), MC-02 (vocabulario de S7) | MC-01: enmienda ciega antes de M3-4, o aceptar la literal. MC-02: fijar la lectura por clases en el addendum |
| Vacíos que cambian resultados | MC-03 (TF2 no evaluable) | decisión escrita del autor antes de M3-4; sin ella, M3-4 no puede decidir si B o AB quedan con TF2 no evaluable |
| Vacíos que fija el addendum | MC-04 a MC-10, MC-12, MC-13, MC-17 a MC-21 | addendum de M1; MC-09 y MC-10 antes de M3-4 |
| Lecturas [D] | MC-22 a MC-54 | addendum de M1 |
| Menores [M] | MC-11, MC-14 a MC-16, MC-55 a MC-65 | quedan aquí |

---

## 8. Costo estimado

**Supuestos.**
- Tamaños:
  - 579 estaciones y 52,2 millones de horas con dato;
  - H = 234.120 horas (2000-01-01 a 2026-09-15); 2000-2025 = 227.928 h; 2015-2024 = 87.672 h; 2015-2019 = 43.824 h;
  - 8.206 píxeles válidos, 838.430 celdas y 108.579 celdas pobladas;
  - hasta 30 vecinos por punto; ≈ 110 bloques de P2 con estaciones (M2a los cuenta);
  - ≈ 150 columnas en el diseño de C.
- Velocidades: 0,5-1·10⁹ operaciones por segundo y por proceso (productos dispersos y operaciones vectoriales de numpy, en
  un hilo).
- `cargar_dmc`, a 2,45 ms por hora de dato, según la medición de factibilidad, que se vuelve a medir.

| Paso | Cuenta | Cómputo (8 procesos) | E/S |
|---|---|---|---|
| **M1:** suite S1-S16 | sintética, salvo S14 (un año real) | 15-40 min | ≈ 1 GB de ERA5L en S14 |
| **M1:** medición a escala (§8.1) | un pliegue, un año de TF, un mes de M5 y un mes de grilla | 2-4 h | un mes de ERA5L |
| M2a: K1, K3, estáticos NASADEM y altitud poblada | 163 teselas; 838.430 celdas | 0,5-1 h | ≈ 0,6 GB y 8 teselas GHS-POP |
| M2a: una pasada por ERA5-Land | fondo en 579 puntos × H × 5 (≈ 10⁹ operaciones), climatologías del estado | 0,5-1 h (domina la lectura) | ≈ 19-23 GB |
| M3-4: `cargar_dmc` por artefacto | 52,2 M h × 2,45 ms ≈ 35 h de CPU | ≈ 4,5 h | ≈ 5 GB |
| M3-4: envoltorio, K4, tramos y marcas | ≈ 52 M filas × ≈ 30 reglas | 0,3-1 h | local |
| M3-4: selección anidada (B y AB) | ≈ 120 pliegues × 520 estaciones × ≈ 8.200 h observadas de selección × 15 (L, λ) × 30 × 2 × 5 campos × 2 ≈ 5·10¹² | 0,2-0,4 h | local |
| M3-4: C y C_est (sumas por estación) | 2,3 M filas × 150² × 5 × 2 usos × 2 ≈ 10¹² | < 0,1 h | local |
| M3-4: predicciones, métricas y remuestreo | 1.158 evaluaciones; 1.999 réplicas sobre tablas por evaluación | < 0,3 h | local |
| **M3-4: TF y finitud de E0** | B y AB: 7 combinaciones uso × campo × 499.680 h (completo, constante y cambio) × 108.579 celdas × 60 ≈ 4,6·10¹³; fondo ≈ 2,6·10¹²; A, C y C_est ≈ 1,7·10¹³ | **2,5-4,5 h** | ≈ 20 GB (una pasada por mes) |
| **Total M3-4** | | **≈ 9-12 h** (el doble en el peor caso) | |
| M5: 0,1°, salud (con representatividad y crónico) y monitores | ≈ 10¹³ operaciones; una sola pasada por ERA5-Land | 2-4 h | ≈ 23 GB leídos, ≈ 25 GB escritos |
| M6: TF de contaminantes | 1,37·10⁸ filas × 2 escenarios × 2 variantes × 3 réplicas × 2 contaminantes | depende de la fábrica v2 (no escrita) | |
| Grilla v2, por variante | 6,2·10⁸ celda-horas por mes × 5 campos × ≈ 75 operaciones ≈ 2,3·10¹¹: 4-8 min de CPU por mes, 21-43 h por los 321 meses | 2,7-5,4 h | ERA5L completo |

**Lectura de la tabla.**
- La TF domina M3-4, después de `cargar_dmc`. El mód 23 sólo abarata la selección (MC-16).
- Con esta estimación, M3-4 no pasa de 36 h y rige el mód 11. Lo decide la medición, no esta tabla.
- La estimación de M5 (2-4 h) queda bajo la del texto (8-12 h), porque supone una sola pasada por ERA5-Land para todos los
  productos. Si `orquestacion` no la logra, vuelve a 8-12 h.

### 8.1 Qué mide M1 y cómo proyecta

`costo.medir` corre con datos sintéticos a escala real. [EMC4-1, D68, 2026-10-31: la carga inicial y durante la
medición se registra como diagnóstico, no excluye la medición, la proyección ni el recorte. La referencia histórica
carga < 2 no es un requisito vigente ni se falsea su indicador. Los tiempos pueden variar por actividad concurrente;
no se garantiza una estimación de máquina libre. Se mantienen las demás comprobaciones.]
1. `cargar_dmc` + envoltorio sobre ≥ 50 artefactos sintéticos de un año, en ms por hora de dato;
2. un pliegue externo de P2 completo, con 579 estaciones y H horas: selección de B, AB, A, C y C_est;
3. un año de TF en las 108.579 celdas pobladas, con la geometría real de `celdas.parquet` (LOCAL, no DMC) y campos
   sintéticos;
4. un mes de M5 (0,1° y salud);
5. un mes de la grilla con I y con D;
6. la lectura y decodificación de un mes real de ERA5L.

`costo.proyectar` escala cada medición por su número de unidades. M3-4 en horas de pared es:

> T = Σ_u t_u · n_u / P + T_serie, con P = 8 (D2), más el máximo desequilibrio entre procesos.

[EMC3-2, D64/D65: esa proyección con P = 8 se conserva como referencia. Para decidir el recorte se usa la pared
reproyectada con los procesos efectivos de cada fase. No se ajusta durante M3-4.]

Si T > 36 h, `costo.recorte` da «mod23», y el addendum lo fija antes de M2a. La grilla v2 se mide para las dos variantes y va
al plan v2 (§7.1).

**Memoria.**
- Por proceso: un lote de un mes en 108.579 celdas son ≈ 0,65 GB por campo en float64. Con 4-6 campos vivos, ≤ 4 GB, bajo el
  tope de 8 GB de §8. Si no alcanza, el lote baja a una semana, fijado en el addendum, nunca a mitad de corrida (MC-37).
- `cargar_dmc`: ≈ 340 MB por proceso (§8).

**Disco** (LOCAL):
- tablas anchas ≈ 3 GB; residuos ≈ 4 GB; fondo en estaciones ≈ 2,7 GB; estáticos ≈ 0,5 GB;
- 0,1° ≈ 19,2 GB; operador ≈ 0,5-1 GB; laterales ≈ 1 GB.
- Total ≈ 31 GB, dentro de los ≈ 469 GiB libres, junto a los ≈ 276 GB de TROPOMI.

---

## 9. Lo que se reutiliza y las huellas fijadas

### 9.1 Del reloj (sin modificarlo)

- **`reloj_dmc.entorno`:** el entorno fijado (`PYTHON_FIJADO` 3.11.16, pandas 2.3.3, netCDF4 1.7.4, tzdata 2026.3 e IANA
  2026c), `reset_tzpath(to=[])`, `comprobar_interprete`, `sha256_archivo`, `sha256_bytes`, `json_canonico`,
  `escribir_atomico`, `prohibido_volumes` (léxica), `prohibido_repositorios` y `sin_datos_privados`. `meteo_combinada.entorno`
  agrega sus alias y sus carpetas.
- **`reloj_dmc.fijados`:**
  - `cargar_por_ruta`, que ejecuta exactamente los bytes con la huella y la recalcula al final;
  - `cargar_adaptador`, `cargar_dmc_features` y `cargar_descargador`;
  - `extraer_por_ast` y `macrozona_region` (de `_comun_modelo`, sin importarlo);
  - `MODULOS_PROHIBIDOS`.
- **`reloj_dmc.politica.validar_regla_reloj_dmc(regla, artefacto_sha256, *, politica_ruta=None)`:**
  - lo llama el envoltorio de §2.1, fuera del código fijado (RELOJ §7.5);
  - la ruta publicada es `AP/config/meteorologia/reloj_dmc/v1/politica_reloj_dmc.json`, con `artefactos_evaluados.json.gz` al
    lado;
  - acepta las claves `coordinates`, `measurements` y `quality` junto a la regla (`CLAVES_UNIDAS_S6`).
- **`reloj_dmc.extraccion.elegir_pixel`:** sólo para la representatividad de M5 (MC-52). Agrega `extraccion.py` y sus
  dependencias a la clausura en ese paso.
- **Patrones que se copian, con prueba de paridad:**
  - `RegistroAccesos` (con la corrección de la Enmienda 4: la ruta léxica antes de resolver);
  - la regla de números de `constantes`;
  - el HTML de la hoja mensual de `sintetico`;
  - `GuardaFalsa`;
  - la fachada perezosa;
  - el índice de pruebas;
  - el programa del Anexo F.

### 9.2 De v2, v3 y APH

- **`v2/meteorologia_v2.py`** (fijado):
  - `leer_artefacto` (da `content_sha256`);
  - `normalizar`, a través de `cargar_dmc`. Convierte nudos con 1.852/3.600 y da `wind_u = −vel·sen(dd)` y
    `wind_v = −vel·cos(dd)`, lo que prueba S11;
  - `unir_sidecar(panel, sidecar, *, metadata)`, que exige `model_ready`, `source_policy_verified`, `policy_sha256` y
    `ts_utc` con zona; `ambiental` la usa sólo en sus pruebas.
- **`v3/dmc_features.cargar_dmc(manifiestos, policies, *, adapter_sha256)`** (fijado):
  - se llama con `[manifiesto]` y las políticas de la estación que cruzan el mes (§2.1);
  - lanza `ValueError` con un código QC presente (l. 85-87), con límites que no son de Python, con políticas solapadas y sin
    observaciones;
  - importa `scipy.spatial`; no se usan sus operadores `nearest` ni `idw`.
- **`v3/preflight_v3.py`** y **`runner_v3.py`:** fuera del camino; sólo se comprueba su huella.
- **`_comun_modelo.py`:**
  - sólo se lee: `MACROZONA_REGION` por AST, y la regla de tp de las l. 411-419, que `fondo_era5l` replica sobre la serie
    continua (S13);
  - `MesNativo.indice_tiempo` redondea hacia abajo, y por eso el lector propio rechaza las horas que no son HH:00 (S12).
- **`_features.py`:** la regla de `el_*` (l. 31, 91-100): unidades, Magnus de 17,67 y 243,5, y `arctan2(u, v)`. Se lee por AST
  para MC-28.
- **APH `scripts_riesgo_agudo/v3_next/meteo_civil_v3.py`** (idéntico al de `v3`), por AST:
  - `VARIABLES`, `ESQUEMA_DIARIO` y los tipos de `tabla_meteo`;
  - Magnus de 17,625 y 243,04 y la HR recortada en [0, 100];
  - la regla de lluvia (`lluvia_horaria`);
  - los días UTC−4 y civil, y la zona regional (`exposicion_horaria_v3.zonas_por_comuna`).
  No se importa, porque arrastra `_rutas_v3`, `dlnm_v3` y `exposicion_horaria_v3`. S8 y S14 lo usan como referencia.
- **APH `scripts_neuro/_pesos.py`:** la tabla `poblacion_celda_anio.parquet` (w_ghs por celda y año; 2026 usa 2025). Se lee la
  tabla, no el módulo.
- **`v2/config_v2.json`:** `protocolos.BLQ-75.origen_m`, sólo lectura, para P2.
- **`pliegues_v2.json` de la red 2** (R13 y R21): monitores y panel para π^mon (MC-09).
- **`config/sinca/politica_temporal.json`:** zonas IANA por región y reglas de horas ambiguas e inexistentes (MC-10).
- **El descargador DMC:** sólo en S2, S12 y S15, con cliente falso.

### 9.3 Huellas fijadas que M1 no puede cambiar

Vienen de `m0/huellas_m0.json`; se vuelven a calcular en M1 y deben coincidir. [2026-10-26, D51: `correr_v2.py` y
`config_v2.json` cambiaron después de M0 con la traducción del bloque «red ampliada» y su ratificación; M1 fija las
vigentes y cita la de M0 como estado de M0, que es la de AP `c7c47e8` (`fijados.HUELLAS_D51`, FIJ-10).
`huellas_m0.json` no se toca.]

| Archivo | sha256 |
|---|---|
| `AP/scripts_modelo_1km/v2/meteorologia_v2.py` (adaptador) | `f61559eab281846a4935eb1ea66217e039ff37a727833bf8fcaa7a774b776754` |
| `AP/scripts_modelo_1km/v3/dmc_features.py` | `157628564ffafb2cfc6aab5403e984d8451f7faa31e6f5ce21e743023d766bec` |
| `AP/scripts_modelo_1km/v3/preflight_v3.py` | `21905706c69cb9a2b52cdd1a2e3ce17a535d5f18e32ead71d1348020f63bc0f7` |
| `AP/scripts_modelo_1km/_comun_modelo.py` | `a83c0384266554e16ab397749544759ae1cf161f138361eefa7d1ad3e29aa6f4` |
| `AP/scripts_pipeline/descargar_meteo_chile_horaria.py` | `578fa26eea5b4ac4733c56aaf08e9b7b8904595fb8447dd54feb838642612120` |
| `AP/scripts_modelo_1km/v2/correr_v2.py` (no se toca en M1) | vigente (D51; AP `889b972`): `1423ef3f7a8d7bc35d8ee1802187de95129e46afe276241e29a0c7e486f6445d`; estado de M0 (AP `c7c47e8`): `534e484b66ed9575f36a2ec5fc75052a9a2544656cf3e4a80077b90f96c69b07` |
| `AP/scripts_modelo_1km/v2/config_v2.json` | vigente (D51; AP `8542e61`, espacio SINCA): `1bcb3ff49729ffa65cc89f646f1c711f01a2ecae1241db1cef91eace36aabaae`; ratificación anterior (AP `6c15981`): `51df5063ed642c737d883a82c40382e7e211d288f5499151edce61bd692528d7`; estado de M0 (AP `c7c47e8`): `232c75b3376b6fd7c4f73c885c812e170abff7c1a8817d1ac64cc76c68b0534c` |
| `APH/scripts_riesgo_agudo/v3/config_v3.json` | `ab248343239b58853d59516b1409d937e0b6a7ee36461c9df3b1eb7c09d17d94` |
| `APH/scripts_riesgo_agudo/v3_next/meteo_civil_v3.py` (= `v3/`) | `483f63a634252fa383ae8a0abb3fd0e1472a73b67c8b36c1b2534a231f627bba` |
| `APH/scripts_riesgo_agudo/v3/exposicion_horaria_v3.py` | `2eef68b329793316acabcd7e58ea9654038dc7ac3ccfe13b4031db7608a99b29` |
| `APH/scripts_neuro/pesos_poblacion.py` | `b6cc4947f432ed5e26e6d68468c25816f680efec88ceffdce0613bff5cb63bf9` |
| `APH/scripts_neuro/covariables.py` | `0941baf39bd85eeb013118a2a026368b95932e37c480ecd22f4f9ec428113081` |
| `ERA5L/catalogo_pixeles.parquet` | `cc5054c20c43b08d30d21035b89052c521bc74d204149f205658df1dbdf69410` |
| ERA5-Land, huella de los 321 manifiestos | `2ada121c2b93bf1b2ef5135a5ab8712341504fbab243a459a2208fed66da6237` |
| ERA5-Land, huella de las salidas declaradas | `c05f04a15c1093ebebec642a0f0336e4aeeadcbe8a4bd27ba27f3b959ee3ca1c` |
| geopotencial `era5land_geopotencial_invariante_chile.nc` | `bec3c995e3ffdd98442c7db8f2f879bf8197482ae5d27742714b0b1ce5bba520` |
| `era5land_altitud_modelo_pixeles.parquet` | `791f7ba29a1ec2b9e5bb2582e48d1fb371e32c709246e70088f0090c035e88e1` |
| NASADEM, manifiesto `nasadem_hgt_20261023T110300Z-75461d99.jsonl` (163 teselas) | `0d837cb58c870df4c7e56ee57dbfd4a52a37b211dc0575b1c8f6b484424c8257` |
| `grilla_1km/celdas.parquet` | `42b4b19613c7de343c856473af64e2c0a6353351f1884c8dba145361292108c3` |
| `grilla_1km/estaticas.parquet` | `606701ef942d907b637cfde10bbe6dbb2e157920f6fae2611e82ecd031470049` |
| `grilla_1km/estaticas_lulc.parquet` | `9cb250712379752f33817d42ed72dd9d637f74e61ef8f60f02e37022cf4b9821` |
| `grilla_1km/enlaces_productos.parquet` | `f441617b16bc518685483a6304f581d0a6ed610bf8a79518ecf4cbd2a2cedbcc` |
| `grilla_1km/enlaces_interpolacion.parquet` | `e2e94bfb2858f432771d7e7b332d85ce7cbea99d115c62d59bb079e0ecaa67f4` |
| GHS-POP 2020, 8 teselas | las de `huellas_m0.json["fuentes"]["ghs_pop_2020"]` |
| SINCA meteorología `manifiesto_descarga.csv` | `82b8472136c7b5fede8a42e68c2537e6d6e479a108cb2005bae7c9a84b17ca21` |
| SINCA meteorología `SHA256SUMS.txt` | `c607e58a0c6c4620464cd4aa5eff286669d0cf84ec1f2ea3d1949c05488be01d` |
| Texto v2.1 | `0d0972d8c8ebf09bb39bf45154496e72b524cdb8d57f9ce029aa53a16708edaf` |
| `meteo_combinada_v1.json` | `156587f195f77009fe49bfa9497fd4a334d6b4bbe14064b46b8f3d3bca5e488a` |
| `m0/preparar_m0.py` (fuente de `opciones_m0`) | `49503a3a88a9b9b331d8f51704708a7154bfc311a1f4a0eb6ca1f22d2f255d81` |
| RELOJ C0 | `5fff072783e932843d210561a46f5344351a39b7dd85f5775ac884eaf96e4d85` |
| RELOJ v1.0.2 | `ee5dec6e7a1ff65f19a814d4994d804e9a4e3e8ad2765b6d8590e9286543217d` |
| RELOJ `texto_7_5.md` | `583626404e6326f44bd46be44bbb2a0222e03df0fb861817c94ca0d0ec017405` |
| intérprete, `micromamba list` | `0b5bc40b49e6cab503c88471a2e8dd4cd30bec9a0c2485b44705f8e9a670ec44` |

### 9.4 Huellas nuevas para la lista cerrada del addendum

Calculadas al escribir este diseño; M1 las vuelve a calcular.

| Archivo | sha256 | Por qué |
|---|---|---|
| RELOJ v1.0.3 y v1.0.4 | `7a019348…` y `d8f61cfc1ab01da17fd97b8e5e871b55d4557a66ff2599a585b362689475b54d` | MC-18 |
| RELOJ v1.0.5 (Enmienda 5, APH `07881ed`) | `21f1b4699dea7106b0e6065e0f232e8aeb97ca618b812b2dee4a2d3b9b803c89` | E5-F (2026-10-27); no toca §3 ni §7 de RELOJ |
| RELOJ `enmienda5/texto_7_5.md` | `583626404e6326f44bd46be44bbb2a0222e03df0fb861817c94ca0d0ec017405` (el mismo de la Enmienda 2) | E5-F |
| RELOJ v1.2, texto consolidado del C1 (APH `1f59e6e`, `auditoria/20261027/reloj_dmc/PROTOCOLO_RELOJ_DMC_v1.2.md`) | `479ed38f8e594e10996cd79e5741d440d291f0dfeac43a279386e30525cabb85` | E5-F; sólo su huella |
| RELOJ, addendum del C1 (APH `73615e8`, `auditoria/20261027/reloj_dmc/addendum_c1.json`) | `cd1c434493cafcda2ebfcdecf4a07738a9b9dac6794f41d960e03c6e445b51d2` | E5-F; sólo su huella |
| `AP/scripts_modelo_1km/_features.py` | `8fd699929c117067962e9ed24c0ea6b137d0c58d5ca17b9fce3a3759793d6838` | MC-28 |
| `APH/scripts_neuro/_pesos.py` | `2f19fa53bc7893d5220fd19034277eb840d11c020d43a3f83769ad2f09b310ed` | pesos de salud |
| `config/sinca/politica_temporal.json` | `41018e4c066d9e30b5ba0b1ff92d47eeb47bab1984b5b8c45a778939359ac61c` | MC-10 |
| SINCA `manifiesto_descarga_20261024b.csv` | `1c0a1567901581de49884891a3e0e7fe4659c856116a98ac647d62d362821ca1` | MC-10 |
| SINCA `SHA256SUMS_20261024b.txt` | `87d659d575da70bde9e3289b962673db6b2f8eceb04391a05abcd987a0528134` | MC-10 |
| SINCA `no_disponibles.csv` y `no_disponibles_20261024b.csv` | `2dd73b5c63b0b26d384e9770b27734abffa8cc520dcc7282d36e7be98a326cf3` (idénticos) | MC-10 |
| `ENMIENDA_2_BLOQUE_RED_AMPLIADA.md` | la de su anclaje (APH `f2c6cfc`) | MC-09 |
| `AP/scripts_modelo_1km/v2/reloj_sinca_v2.py` | `c1eb98c52660dae3755c65a69fb2cc33e7e8d54736c269cc111bde35289795f7` (AP `889b972`) | D54 (2026-10-26); lo leen por AST `test_sinca_meteo` y SNC-11 |
| clausura del reloj: `entorno.py`, `fijados.py`, `politica.py`, `tipos.py`, `constantes.py`, `tablas.py` | al sellar (MC-17) | §2.1 |
| clausura del reloj fijada (E5-F), AP `1da0236` | `__init__` `de78881a…`, `entorno` `adda1be8…`, `fijados` `1b1aec92…`, `politica` `ec869526…`, `tipos` `b260f4ef…`, `constantes` `95deee46…`, `tablas` `0c7e9179…` (enteras en `fijados.HUELLAS_RELOJ_1DA0236`); antes, en AP `4b50b0d`, igual salvo `constantes` `10354281…` | MC-17, FIJ-1 |
| clausura del reloj ampliada para `elegir_pixel` (FIJ-11, ola 5; MC-52), AP `1da0236` | `extraccion` `dc6a8788…`, `numerico` `c463336c…`, `umbrales` `075834dc…` (enteras en `fijados.HUELLAS_PIXEL_1DA0236`); con los siete de arriba son `fijados.HUELLAS_CLAUSURA`. Los umbrales del reloj en C0, `c0/reloj_dmc_v1.json` `3251a4d8…` (el de `m0/huellas_m0.json`); del v1.2, sólo su JSON `6f60f3bd…` (APH `1f59e6e`) y su generador `enmienda5/generar_v1_2.py` `faa0ba8a…` (APH `07881ed`, leído por AST) | MC-17, MC-52; va al addendum de M1 |
| `pliegues_v2.json` y paneles de la red 2 | las del «Registro de la red v2» (R22, paso 4) | MC-09; en el registro de M3-4, no en M1 |
| el paquete `meteo_combinada/` (cada archivo), sus pruebas, la salida de la batería, `anexo_a2.json`, `deriva_s6.json` y `costo_m1.json` | al sellar | §10, M1 |

---

## 10. Pendientes antes de sellar M1

1. **Código fijado fuera de git.** `meteorologia_v2.py`, `dmc_features.py` y `preflight_v3.py` no están en ningún commit de
   AP (comprobado con `git ls-files`), como ya declaró M0: «Deben entrar en un commit antes de M1, con autorización del
   autor». Tampoco `reloj_dmc/`. Sin eso no hay testigo externo de M1 ni M3-4 (§10, B14).
2. **El C1 del reloj.** Su código no está sellado: decide si la clausura del reloj va al addendum de M1 o al registro de
   M2a (MC-17). Si el reloj cambia antes, M1 vuelve a calcular las huellas. [Hecho el 2026-10-27 (E5-F): C1 cerró de
   nuevo; la clausura es la de AP `1da0236` y va al addendum de M1.]
3. **Decisiones del autor:** MC-03 (sin valor por omisión) y MC-01 (enmienda o literal). Las lecturas [D] van al addendum;
   el autor puede pasar cualquiera a [E].
4. **Carga registrada, no excluyente** para el costo (§8.1, EMC4-1/D68). Se recomienda no añadir otras corridas
   pesadas, pero la carga observada no rechaza inicio, proyección o recorte. No se autoriza por ello abrir resultados
   del C4 del reloj ni ejecutar otras tareas concurrentes sin permiso.
5. **Espejo en APH.** `meteo_combinada/` entra en un grupo de `config/componentes_compartidos.json`, regenerado con su
   generador, y se confirma en AP y en APH con el envío al remoto privado que autorice el autor (testigo externo de M1).
6. **El addendum de M1** (MC-54), con commit, envío y sello OpenTimestamps de su línea en
   `APH/auditoria/sellos/anclajes_<fecha>.txt`.

---

## Anexo P. Plantillas del Anexo A (ids por grupo, en orden)

Cada plantilla es el texto literal de la fila con estos ids en el lugar de sus números. `U.a` devuelve el valor. Los ids
`*_PCT` admiten `U.frac`. Las listas vuelven como tupla.

| Grupo | Ids |
|---|---|
| Rangos `quality` | `QTS_MIN`, `QTS_MAX`, `QTD_MIN`, `QTD_MAX`, `QHR_MIN`, `QHR_MAX`, `QFF_MIN`, `QFF_MAX`, `QDD_MIN`, `QDD_MAX`, `QQFE_BAJO` (−80), `QQFE_ALTO` (+50), `QQFF_MIN`, `QQFF_MAX` |
| Centinelas | `CENT_TS`, `CENT_QFE`, `CENT_TOL` |
| Rachas | `RACHA_H`, `HR_SAT` (100, dos veces), `RACHA_LARGA_H`, `RACHA_MIN_REPORTES`, `CONSECUTIVO_H` |
| Picos (θ) | `PICO_TS`, `PICO_TD`, `PICO_P`, `PICO_FF`, `F_1H`, `DT_1H`, `F_23H`, `DT_23_DESDE`, `DT_23_HASTA`, `SALTO_MULT` |
| Td y HR | `TD_TS_INV` (dos veces), `INCOH_TD`, `INCOH_HR`, `CERO_C`, `HR_SAT`, `HR_RECORTE_MAX`, `SECO_HR_PCT`, `SECO_H` |
| Viento | `CERO_NORTE_PCT` (360 y 0 quedan literales) |
| Error grueso | `EG_T`, `EG_TD`, `EG_P`, `EG_MULT`, `EG_MAD_K`, `EG_MIN_N`, `EG_CORTO_H` (dos veces), `EG_LARGO_H` (dos veces) |
| Altitud | `ALT_QFE_HPA`, `K3_DZ_M`, `RHO_MIN_KM`, `RHO_MAX_KM` |
| Traslados | `K4_T2A_M`, `K4_T2B_HPA`, `K4_MIN_MES_HORA`, `K4_HORAS_PCT`, `K4_VENTANA` (dos veces), `K4_MIN_LADO`, `K4_MIN_PARES`, `K4_MAX_QUIEBRES`, `K4_TRAMO_MIN`, `K4_COINC_MESES`, `K4_COINC_M`, `K4_COINC_FRAC` |
| Tramos homogéneos | `HOM_T`, `HOM_TD` |
| RR06 | `RR_MIN`, `RR_MAX` («s/p = 0» literal) |
| Alarmas | `Q1_PCT`, `Q1Z_PCT`, `Q2_PCT`, `Q2_DESDE`, `Q2_HASTA`, `Q2Z_PCT`, `Q3_PCT`, `LISTA_PCT` |
| Fondo | `GAMMA_K_KM`, `ZE5L_NASADEM_PCT`, `VECINO_KM` |
| Núcleo | `NUC_L` (lista), `NUC_LAMBDA` (lista), `NUC_KAPPA` (lista), `NUC_CORTE`, `NUC_VECINOS` |
| A | `A_VENTANA_MESES`, `A_P1_H`, `A_P2_H`, `A_P3_H`, `A_HORAS_K3`, `A_RECORTE_PCT`, `A_MIN_N`, `A_MIN_ANIOS`, `A_HUECO_H` |
| B y AB | `B_INTERP_H` |
| C y C_est | `C_ALFAS` (lista), `C_FILAS`, `C_PESO_MAX`, `C_ANIO_LULC`, `C_TPI_PCT` |
| Selección anidada | `SEL_PLIEGUES`, `SEL_BLOQUE_KM`, `SEL_AMORT_KM`, `SEL_MOD`, `SEL_RESTO`, `SEL_MOD_RECORTE`, `SEL_UMBRAL_H`, `SEMILLA` |
| P1 / P2 | `P1_PLIEGUES`, `GRUPO_KM`, `P2_BLOQUE_KM`, `P2_AMORT_KM` |
| Mínimos | `MIN_HORAS`, `DIA_MIN_H`, `DIA_HUECO_H`, `AGUDO_MIN_DIAS`, `ANIO_MIN_DIAS`, `MIN_ANIOS`, `MIN_ANIOS_ANOM`, `EX_MIN_DIAS` |
| Pesos | `BANDAS_KM` (cortes 10, 25 y 50), `BANDA_MIN_EVAL` («½» literal) |
| Soporte | `SOPORTE_PCT` |
| Remuestreo | `BOOT_REPLICAS`, `BOOT_BLOQUE_KM`, `SEMILLA` |
| Compuertas | `CD_MULT`, `CD_T`, `CD_HR`, `CD_P`, `EX_T`, `EX_TD`, `EX_HR`, `EX_FF`, `MZ_MULT`, `MZ_MIN_EST`, `NIVEL_MULT` («TF en §5.7» literal; las cotas de TF van al A2) |
| Decisión | sin números: el orden de desempate («A, AB, B, C», «C_est en lo crónico») y las ramas se comparan como texto literal |
| Formato | `FMT_RELLENO`, `FMT_ESC_T`, `FMT_ESC_UV`, `FMT_ESC_P`, `FMT_DESP_P` |
| M6 (Anexo B) | `M6_N`, `M6_REPLICAS`, `M6_B`, `M6_IC_PCT`, `M6_NMB_PP`, `M6_CELDAS_COMUNA`, `SEL_MOD`, `SEL_RESTO`, `SEMILLA`, `M6_TF_MEDIA_PCT`, `M6_TF_P95_PCT`, `M6_TF_DESDE`, `M6_TF_HASTA` |

Los ids repetidos entre grupos (`SEMILLA`, `SEL_MOD`, `SEL_RESTO` y `HR_SAT`) deben valer lo mismo en cada aparición: si no,
la traducción falla.

---

## Concordancia técnica de recibos EMC3 (2026-10-29)

La formalización documental no cambiaba firmas; su implementación final sí añade un argumento técnico opcional
`registro` a `repartir`, propagado por ayudantes privados. La firma completa del Anexo F es la vigente. El documento
inicial de la enmienda se conserva como referencia anclada; su frase sobre firmas se precisa en
`APH/auditoria/20261023/meteo_combinada/enmienda3/NOTA_FIRMAS_RECIBOS.md` (3fadd224…), incluida en la lista cerrada.

Los recibos separan `presupuesto` de la observación, con `alcance = "repartos_de_esta_invocacion"`. Cada llamada guarda
`unidades`, `limite.procesos`, `procesos` de ejecución y `trabajadores_creados.procesos`. Por fase se conserva el detalle,
el máximo de procesos de ejecución y la suma de creaciones. Un reparto vacío tiene 0/0; uno secuencial en el principal,
1/0. Reanudar sólo cuenta unidades pendientes de esa invocación, sin fabricar un acumulado histórico. El número fijado
en Cfg y en el registro normativo no se sustituye por esa observación; las huellas analíticas no incorporan el entorno
variable del recibo. La convención principal/trabajadores es una precisión técnica [delegada], sin cambio de cálculos.

## Anexo F. Firmas públicas (generadas por AST del código; cierre de M1, 2026-10-28)

**Qué es.** El anexo de firmas que pide §3 al cerrar M1: las firmas públicas de cada módulo, tal como están en el código.
Se genera con el programa del Anexo F del reloj (`reloj_dmc/DISENO_IMPLEMENTACION.md`), del que cambia sólo la lista
`ORDEN`; su línea de documentación sigue siendo la del reloj. Entra lo que no empieza por «_» a nivel de módulo: funciones
con su firma completa (`ast.unparse`), clases con sus campos anotados y sus métodos públicos (más `__init__`, `__enter__`,
`__exit__`, `__call__`, `__getattr__` y `__dir__`), y los enumerados con sus valores. No se importa nada del paquete. Los
módulos van en el orden de §1. Las constantes son datos y el AST no las lista (por ejemplo, `orquestacion.FASES_REPARTO`,
de D59).

**Cómo se regenera** (con `~/micromamba/envs/amb_v2/bin/python -B <script> meteo_combinada <salida.md>`, desde
`scripts_modelo_1km`; el resultado reemplaza la lista que sigue a este bloque). `test_meteo_combinada.PruebasAnexoFirmas`
comprueba que la lista sea la que da el programa con el código de hoy y que `ORDEN` sea la de §1: si cambia una firma, la
prueba falla hasta que se regenere.

```python
"""Anexo F de DISENO_IMPLEMENTACION.md: firmas públicas por AST (no importa nada del paquete)."""
import ast, sys
from pathlib import Path
paq = Path(sys.argv[1])
ORDEN = ("tipos", "constantes", "umbrales", "entorno", "fijados", "numerico", "ceguera", "sintetico", "politicas",
         "estaticas_nasadem", "fondo_era5l", "particiones", "homogeneidad", "sinca_meteo", "decision", "qc_dmc_meteo",
         "candidatos", "validacion", "tendencias", "producto", "salud", "ambiental", "orquestacion", "salidas", "costo",
         "addendum", "verificar_meteo_combinada", "meteo_combinada")
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

- `macrozona_o_ninguna(nombre: str | None) -> str | None`
- `macrozona_de_celda(macrozona: str | None, cod_comuna) -> str | None`
- clase `Variable(StrEnum)`: `T`, `Td`, `u`, `v`, `p`
- clase `Derivada(StrEnum)`: `HR`, `rapidez`, `direccion`
- clase `VariableDMC(StrEnum)`: `Ts`, `Td`, `relative_humidity`, `wind_speed_instant`, `wind_direction_instant`, `QFE`, `QFF`, `QNH`, `RR06`, `wind_u`, `wind_v`
- clase `Candidato(StrEnum)`: `A`, `B`, `AB`, `C`, `C_est`
- clase `Uso(StrEnum)`: `ambiental`, `agudo`, `cronico`
- clase `Grupo(StrEnum)`: `T_Td`, `u_v`, `p`
- clase `Particion(StrEnum)`: `P1`, `P2`
- clase `Conjunto(StrEnum)`: `V`, `V2`, `N`
- clase `Alcance(StrEnum)`: `fila`, `variable`, `variables`, `no`
- clase `Invalidacion`: campos `alcance`, `variables`, `arrastra`
- clase `OrigenTd(IntEnum)`: `0`, `1`, `2`
- clase `OrigenHR(IntEnum)`: `0`, `1`
- clase `OrigenViento(IntEnum)`: `0`, `1`, `2`
- clase `FuenteZs(StrEnum)`: `catalogo`, `nasadem`
- clase `CasoZE5L(StrEnum)`: `geopotencial`, `nasadem`, `hipsometrica`
- clase `Estadistico(StrEnum)`: `T2a`, `T2b`
- clase `ClaseQuiebre(StrEnum)`: `traslado`, `barometro`, `metodo_reduccion`
- clase `Prueba(StrEnum)`: `TF1`, `TF2`
- clase `ResultadoTF(StrEnum)`: `pasa`, `falla`, `no_evaluable`
- clase `ReglaRedConstante(StrEnum)`: `r2000_2025`, `r2003_2025`, `r2010_2025`, `ninguna`
- clase `Compuerta(StrEnum)`: `deriva`, `finitud`, `TF`, `CD`, `EX`, `MZ`, `nivel`, `anomalia`
- clase `Alarma(StrEnum)`: `Q1`, `Q1z`, `Q2`, `Q3`
- clase `Variante(StrEnum)`: `I`, `D`
- clase `Rama(IntEnum)`: `1`, `2`, `3`
- clase `MotivoNoNormalizable(StrEnum)`: `dd_fuera_de_dominio`, `rapidez_negativa`, `hora_no_nativa_o_repetida`, `codigo_qc_presente`, `intervalo_no_entero`, `limite_no_python`, `sha_o_tamano`, `sin_observaciones`, `otro`
- clase `OrigenAborto(StrEnum)`: `datos`, `regla`
- clase `Modo(StrEnum)`: `sintetico`, `estaticos`, `aplicar`, `producir`, `m6`
- clase `Sentido(StrEnum)`: `I_frente_a_D`, `D_frente_a_I`
- clase `Protocolo(StrEnum)`: `LRO`, `BLQ-75`
- clase `DisenoC(StrEnum)`: `estado`, `climatologico`
- clase `MotivoExclusion(StrEnum)`: `coordenadas_ilegibles`, `coordenadas_fuera_de_rango`, `sin_nasadem`, `k3`, `sin_z_s`, `sin_fondo`
- clase `VariableMetrica(StrEnum)`: `T`, `Td`, `HR`, `rapidez`, `uv`, `p`, `temp_media`, `hr_media`
- clase `Estrato(StrEnum)`: `nacional`, `macrozona`, `conjunto`, `altitud`, `periodo`, `tipo`, `propietario`, `omm`
- `indicadoras_macrozona(macrozona_cod) -> tuple[int, ...]`
- `id_grupo(codigos) -> str`
- `id_tramo(tramo_reloj: str, k: int) -> str`
- `id_bloque(ie: int, i_n: int) -> str`
- `id_pliegue_p1(k: int) -> str`
- `id_pliegue_p2(bloque: str) -> str`
- `id_interno(externo: str, j: int) -> str`
- clase `Esquema(_MappingABC)`
  - `__init__(self, nombre: str, version: str, columnas: Mapping[str, str])`
- `validar_esquema(df, esquema: Mapping[str, str], *, nombre: str) -> None`
- `tabla_vacia(esquema: Mapping[str, str]) -> 'pd.DataFrame'`
- clase `InfoEstacion`: campos `codigo`, `nombre`, `conjunto`, `macrozona`, `grupo`, `omm`, `tipo`, `propietario`, `lat_txt`, `lon_txt`, `alt_txt`, `lat`, `lon`, `z_cat`, `rho_km`, `k3_pasa`, `z_s`, `z_s_fuente`, `celda`, `utm_e`, `utm_n`, `bloque`, `pix0`, `pix1`, `pix2`, `pix3`, `w0`, `w1`, `w2`, `w3`, `respaldo_16km`, `sin_fondo`, `excluida`, `motivo`
- `fuera_de_la_grilla(info: InfoEstacion) -> bool`
- clase `ErrataConfirmada`: campos `ruta`, `sha256`, `commit`
- clase `RegistroReloj`: campos `ruta`, `sha256_politica`, `sha256_artefactos`, `commit_c5`, `post_hoc`, `errata_post_c4`, `errata_confirmada`
- clase `TramoPolitica`: campos `codigo`, `id`, `valid_from`, `valid_to`, `clock`, `coordenadas_confirmadas`, `motivo`
- clase `ResultadoArtefacto`: campos `id_artefacto`, `codigo`, `anio`, `mes`, `content_sha256`, `larga`, `meta`, `motivo`, `origen`, `reglas_rechazadas`
  - `normalizable(self) -> bool`
- clase `Quiebre`: campos `estadistico`, `mes`, `D`, `clase`
- clase `ResultadoK4`: campos `codigo`, `quiebres`, `ultimo_traslado`, `ultimo_barometro`, `sin_prueba`
- clase `Hiper`: campos `L_km`, `lam`, `kappa`
- clase `OperadorPuntos`: campos `ids`, `z`, `pix`, `w`, `dz`, `respaldo`
- clase `VecinosNucleo`: campos `puntos`, `est`, `d_ef`, `grupo_de`, `hiper`, `codigos`, `grupos`, `grupo_est`
- clase `SumasC`: campos `codigo`, `variable`, `diseno`, `xtx`, `xty`, `yty`, `n_filas`, `peso`, `horas`
- clase `Pliegue`: campos `id`, `particion`, `prueba`, `entrenamiento`, `excluidas`, `externo`
- clase `DatosCompetencia`: campos `residuos`, `climatologias`, `tramos`, `filas_c`, `estaticos`, `estaciones`, `pliegues`, `puntos_e5l`, `clima_estado`
- clase `ModeloC`: campos `coef`, `media`, `desvio`, `alfa`, `diseno`
- clase `EntradasDecision`: campos `uso`, `grupo`, `validacion`, `tf`, `replicas`, `motivos_e0`
- clase `DecisionGrupo`: campos `uso`, `grupo`, `e0`, `e1`, `motivos`, `S`, `delta_S`, `ic_delta_S`, `red_tf2`, `notas`, `ganador`
- clase `DecisionM6`: campos `rama`, `condiciones`, `variante`, `ganador_restringido`, `notas`
- clase `Unidad`: campos `nombre`, `huella_entrada`, `huella_salida`

**`constantes.py`**

- clase `ConstanteTexto`: campos `nombre`, `valor`, `seccion`, `fragmento`, `ajenos`, `clase`, `repite`, `negativos`, `pegados`
- clase `NoNormativo`: campos `seccion`, `fragmento`, `motivo`, `numeros`, `pegados`
- `valor(nombre: str) -> Any`
- `numeros_del_fragmento(texto: str) -> list[int | float]`
- `valor_de_literal(literal: str) -> int | None`
- `tramo_de_seccion(texto: str, seccion: str) -> tuple[int, int] | None`
- `verificar_contra_texto(texto_protocolo: str) -> list[str]`
- `verificar_repeticiones(valores_anexo_a: Mapping[str, Any]) -> list[str]`
- `completitud(texto_protocolo: str) -> list[str]`
- `anexo_a2(texto_protocolo: str, sha256_texto: str) -> dict`

**`umbrales.py`**

- clase `ErrorUmbrales(ValueError)`
- `numero_del_texto(token: str) -> int | float`
- clase `Umbrales`: campos `valores`, `sha256_json`, `sha256_texto`, `opciones_m0`, `sha256_texto_vigente`
  - `a(self, ident: str) -> int | float | tuple`
  - `frac(self, ident: str) -> float`
  - `vigentes(self) -> dict[str, Any]`
  - `huella(self) -> str`
- `seccion_anexo_a(texto: str) -> str`
- `filas_anexo_a(texto: str) -> list[dict]`
- `regenerar_desde_texto(texto: str, nombre_archivo: str, sha256_texto: str, opciones_m0: dict) -> dict`
- `serializar(obj: dict) -> bytes`
- `comparar(publicado: dict, regenerado: dict) -> list[str]`
- `traducir(filas_anexo_a: list[dict]) -> dict[str, int | float | tuple]`
- `cargar_umbrales(ruta_json, ruta_texto, *, sha256_json: str | None=None) -> Umbrales`
- `cargar_m0(aph) -> Umbrales`

**`entorno.py`**

- clase `Rutas`: campos `ap`, `aph`, `local`, `datos`, `dmc`, `era5l`, `nasadem`, `invariantes`, `ghs`, `sinca_met`, `grilla`, `pesos`, `v3`
  - `salidas(self) -> Path`
- `rutas_reales() -> Rutas`
- `rutas_sinteticas(raiz_temporal) -> Rutas`
- `alias(ruta, rutas: Rutas) -> str`
- `carpeta_salida(rutas: Rutas, compuerta: str, etiqueta: str | None=None) -> Path`
- `es_etiqueta_corrida(texto) -> bool`
- `etiqueta_corrida(fecha_aaaammdd: str, numero: int=1, errata: int | None=None) -> str`
- `prohibido_volumes(ruta) -> None`
- `prohibido_repositorios(ruta) -> None`
- `escribir_atomico(ruta, datos) -> str`
- `carpeta_de_trabajo(prefijo: str=PREFIJO_TRABAJO) -> Iterator[Path]`
- `fijar_hilos() -> dict`

**`fijados.py`**

- `cargar_adaptador(ap) -> ModuleType`
- `cargar_dmc_features(ap) -> ModuleType`
- `cargar_descargador(ap) -> ModuleType`
- `huellas_reloj(ap) -> dict[str, str]`
- `huellas_clausura(ap) -> dict[str, str]`
- `cargar_validador_reloj(ap, huellas_esperadas: dict[str, str], *, permitir_cargados: bool=False) -> Callable`
- clase `PixelReloj`: campos `elegir_pixel`, `EleccionPixel`, `umbrales`, `radio_km`, `huellas`, `coordenadas_en_rango`
  - `elegir(self, lat: float, lon: float, catalogo_pixeles, validos: set[int])`
  - `enlazar(self, lat: float | None, lon: float | None, catalogo_pixeles, validos: set[int])`
- `cargar_elegir_pixel(ap, aph, huellas_esperadas: Mapping[str, str], *, permitir_cargados: bool=False) -> PixelReloj`
- `macrozona_region(ap) -> dict[int, str]`
- `macrozona_codigo(ap) -> dict[str, int]`
- `extraer_meteo_civil_v3(aph, nombres: Iterable[str]) -> dict[str, Any]`
- `esquema_meteo_civil_v3(aph) -> dict`
- `regla_el_features(ap) -> dict`
- `opciones_m0(aph) -> dict`
- `huella_micromamba(texto: str) -> str`
- `comprobar_codigo_fijado(ap, aph, *, micromamba_list: str | None=None) -> list[str]`

**`numerico.py`**

- `magnus_agua(t_c)`
- `magnus_hielo(t_c)`
- `td_desde_e(e_hpa)`
- `hr_desde(t_c, td_c, *, hielo: bool=False)`
- `td_desde_hr(hr, t_c)`
- `p_std(z_m)`
- `z_hipsometrica(sp_hpa)`
- `presion_a_altitud(sp_hpa, t_k_medio, dz_m)`
- `haversine_km(lat1, lon1, lat2, lon2)`
- `utm19s(lat, lon) -> tuple`
- `mollweide(lat, lon) -> tuple`
- `mediana_mad(x) -> tuple[float, float]`
- `cuantil_ponderado(x, w, q: float) -> float`
- clase `DisenoDeficiente(ValueError)`
- `valor_armonico(coefs, h)`
- `armonico_recortado(h, r, k_max: int, recorte: float)`
- `ridge_ponderado(xtx, xty, alfa: float, *, sin_penalizar: int=0)`
- `hueco_circular_max(horas, periodo: int) -> int`
- `generador(semilla: int, *partes: str)`
- `remuestreo_bloques(ids_bloque, n_replicas: int, semilla: int)`

**`ceguera.py`**

- clase `SalidaProhibida(ValueError)`
- clase `RedProhibida(PermissionError)`
- `anunciar_acceso(ruta, *, evento: str='lectura', lectura: bool=True) -> None`
- clase `RegistroAccesos`
  - `__init__(self, vigiladas, *, bloquear: bool=False, permitidas=())`
  - `__enter__(self) -> 'RegistroAccesos'`
  - `__exit__(self, *exc) -> None`
- clase `SinRed`
  - `__init__(self)`
  - `__enter__(self) -> 'SinRed'`
  - `__exit__(self, *exc) -> None`
- `procesos_hijos_vivos(*, grupos: Iterable[int]=()) -> list[int]`
- `es_ruta_por_alias(texto: str) -> bool`
- `es_procedencia(texto: str) -> bool`
- `vocabulario_en(texto: str) -> str | None`
- clase `ReferenciaDocumento`
  - `__init__(self, texto: str, sha256_texto: str, *, fuentes: Mapping[str, str | bytes] | None=None)`
  - `permite(self, lecturas) -> bool`
- clase `ConsolaDocumento`
  - `__init__(self, referencia: ReferenciaDocumento)`
  - `encabezado(self) -> str`
  - `linea(self, texto: str) -> str`
- `clase_de_ruta(nombre_archivo) -> str | None`
- `vigilar_salida(nombre_archivo: str, contenido, *, clase: str, referencia: ReferenciaDocumento | None=None) -> None`
- `es_de_reloj(ruta) -> bool`
- `permitido_de_reloj(ruta, *, k2: bool=False) -> bool`
- clase `GuardaResiduo`
  - `__init__(self)`
  - `centinelas(self) -> Mapping[str, float]`
  - `centinela(self, nombre: str) -> float`
  - `registrar(self, nombre: str, valor: float) -> None`
  - `formas(self) -> dict[str, dict[str, bytes]]`
  - `buscar(self, contenido, *, nombre: str='contenido') -> list[tuple[str, str]]`
  - `buscar_en(self, ruta) -> list[tuple[str, str, str]]`
  - `comprobar(self, contenido_o_ruta, *, nombre: str='contenido') -> None`

**`sintetico.py`**

- `carpeta_temporal() -> Path`
- `destino_temporal(ruta) -> Path`
- clase `EstacionSintetica`: campos `codigo`, `lat`, `lon`, `alt_m`, `textos_coord`, `reportes`
- `reportes_desde(L, **columnas) -> pd.DataFrame`
- `estacion_sintetica(codigo: str, lat: float, lon: float, alt_m: float, L, *, textos_coord: tuple | None=None, **columnas) -> EstacionSintetica`
- `etiquetas_desde_utc(u, minutos: int) -> np.ndarray`
- `horas_de_la_rejilla(anio: int, mes: int) -> pd.DatetimeIndex`
- `filas_del_mes(estacion: EstacionSintetica, anio: int, mes: int) -> list[list[str]]`
- `hoja_html(codigo, anio, mes, filas_textos, descargador) -> str`
- `html_catalogo(estaciones: Sequence[EstacionSintetica]) -> str`
- `inventario(est: EstacionSintetica) -> list[dict]`
- clase `ClienteFalsoMC`
  - `__init__(self, estaciones: Sequence[EstacionSintetica], descargador: ModuleType)`
  - `catalog(self)`
  - `inventory(self, code)`
  - `report(self, code, year, month, start=None, end=None)`
- clase `GuardaFalsaMC`
  - `__init__(self, raiz=None)`
  - `check(self, *args, **kwargs)`
  - `ensure_directory(self, path)`
  - `write_atomic_bytes(self, path, body)`
- `fabricar_descarga(estaciones, raiz_temporal, descargador, desde: str, hasta: str, *, crear_candado: bool=True) -> Path`
- `manifiestos_de(dmc) -> dict[str, list[Path]]`
- `artefactos_de_descarga(dmc) -> dict[str, list[str]]`
- `alterar_artefacto(manifiesto, cambio: Callable[[dict], dict]) -> str`
- `rutas_politica_sintetica(raiz, fecha_c5: str=FECHA_C5_SINTETICA) -> dict[str, Path]`
- `politica_reloj_sintetica(raiz, estaciones, reglas: dict, *, coordenadas_inconsistentes=(), marcas=None, conjuntos=None, post_hoc: bool=False, errata_post_c4: bool=False, errata_confirmada: str | None=None, commit_c5: str | None=None, fecha_c5: str=FECHA_C5_SINTETICA, alterar_registro: Mapping | None=None) -> Path`
- `horas_del_mes(anio: int, mes: int) -> np.ndarray`
- `tp_acumulado(tiempos, lluvia_m) -> np.ndarray`
- `mes_era5_netcdf(ruta, campos: dict, tiempos, pixel_ids, *, unidades: str='nativas', cod_comuna=None, catalogo_sha256: str | None=None)`
- `catalogo_pixeles(lat0, lon0, nlat, nlon, *, cod_comuna: int=13101, territorio: str='continental')`
- `geopotencial_sintetico(carpeta, catalogo, z_m, *, corrimiento_filas: int=0) -> dict[str, Path]`
- `id_tesela_nasadem(lat_sur: int, lon_oeste: int) -> str`
- `tesela_nasadem(ruta, funcion_z, *, mascara=None, oeste: float=-70.7, norte: float=-33.4, filas: int=120, columnas: int=120, tile_id: str | None=None, aoi_id: str='continente')`
- `nombre_tesela_ghs(fila: int, columna: int, epoca: int=2020) -> str`
- `tesela_ghs(ruta, funcion_pob, *, lat_centro: float=-33.45, lon_centro: float=-70.65, filas: int=100, columnas: int=100)`
- `grilla(nceldas, comunas, *, lat0: float=-33.3, lon0: float=-70.8, anios_pesos=(2020,), semilla: int=SEMILLA_POR_OMISION, celdas_sin_comuna: int=0) -> dict`
- `verdad(campos_base, sesgo, anomalias, *, semilla: int) -> dict`
- `red_s6(*, deriva_k_decada: float=0.0, paso_h: int=1, anios=(2000, 2024), semilla: int=SEMILLA_POR_OMISION, tau_h: float=48.0, sigma_k: float=1.5, L_km: float=100.0, sesgo_valle_k: float=-1.5, n_historicas: int=20, n_nuevas: int=120, anio_nuevas: int=2010, n_comunas: int=25, celdas_por_comuna: int=4) -> dict`
- `ciclo_s6(h) -> np.ndarray`
- `deriva_s6(red: dict, h) -> np.ndarray`
- `anomalias_s6(red: dict, mes2000: int) -> tuple[np.ndarray, np.ndarray]`
- `campos_s6(red: dict, cuales: str='estaciones', *, anios=None) -> dict[str, np.ndarray]`
- `ciclo_diario_t2b_hpa(ciclo_m: float, altitud_m: float, dt_clima_k: float=0.0) -> float`
- `series_traslado(tipo: str, altitud_m: float, *, semilla: int, magnitud: float | None=None, desde: str='2012-01-01', hasta: str='2017-12-31', cambio: str='2015-01-01', dt_clima_k: float | None=None, ciclo_diario_m: float | None=None)`
- `tablas_metricas(caso: str, *, semilla: int=SEMILLA_POR_OMISION) -> dict`
- `tablas_m6(caso: str) -> dict`
- `sinca_sintetico(raiz, *, desde: str='2019-01-01', hasta: str='2019-01-31', semilla: int=SEMILLA_POR_OMISION) -> Path`
- `huellas_sinca(raiz) -> dict[str, str]`
- `huella_pliegues(manifiesto: Mapping[str, Any]) -> str`
- `panel_y_pliegues(raiz, *, desde: str='2019-01-01', hasta: str='2019-01-31', semilla: int=SEMILLA_POR_OMISION) -> dict`

**`politicas.py`**

- clase `ErrorC5(ValueError)`
- `leer_registro_c5(ruta, *, ap) -> RegistroReloj`
- `leer_politica_reloj(registro, *, ap) -> tuple[dict, dict]`
- `comprobar_c5(registro, politica) -> list[str]`
- `declaracion_c5(registro, politica) -> dict`
- `coordenadas_inconsistentes(registro, *, ap) -> frozenset[str]`
- `source_coordenadas(codigo: str, sha_catalogo: str, sha_protocolo: str, *, motivo: str | None=None) -> str`
- `source_medicion(variable: str, sha_protocolo: str, *, motivo: str | None=None) -> str`
- `source_calidad(variable: str, sha_protocolo: str) -> str`
- `marcas_g(politica_reloj, codigo: str) -> dict[int, frozenset[str]]`
- `media_horaria(politica_reloj, codigo: str) -> bool`
- `tramos_de_lectura(politica_reloj, codigo, meses_con_artefacto, marcas_g, *, info, k2) -> list[TramoPolitica]`
- `tramos_de_politicas(politicas) -> list[TramoPolitica]`
- `tramos_marca_14(efectivas, codigo: str) -> list[TramoPolitica]`
- `politicas_de_lectura(politica_reloj, info, tramos, umbrales, *, sha_protocolo, sha_catalogo) -> list[dict]`
- `politicas_efectivas(politicas_lectura, resultados_k4: dict) -> list[dict]`
- `politicas_que_cruzan(politicas, codigo: str, anio: int, mes: int) -> list[dict]`
- `regla_reloj(politica) -> dict`
- `validar_reglas(politicas, content_sha256: str, validar_regla: Callable) -> tuple[list[dict], tuple[str, ...]]`
- `a_json(politicas) -> bytes`
- `de_json(datos: bytes) -> list[dict]`

**`estaticas_nasadem.py`**

- `interpretar_coordenada(texto: str | None, eje: str) -> float | None`
- `coordenadas_en_rango(lat: float | None, lon: float | None) -> bool`
- `rho_km(lat_txt: str, lon_txt: str, umbrales) -> float`
- clase `TeselaDEM`: campos `nombre`, `sha256`, `i_norte`, `j_oeste`, `z`, `dato`, `tile_id`, `aoi_id`
  - `i_sur(self) -> int`
  - `j_este(self) -> int`
- `leer_tesela(ruta, sha256: str) -> TeselaDEM`
- `celda_de_puntos(lat, lon) -> np.ndarray`
- `ventana_k3(lat, lon, rho_km) -> dict[str, float]`
- `hay_tesela_a_rho(lat, lon, rho_km, teselas) -> bool`
- `k3(lat, lon, z_cat, rho_km, teselas, umbrales) -> tuple[bool, float]`
- clase `TeselaGHS`: campos `nombre`, `sha256`, `x_oeste`, `y_norte`, `paso_m`, `pob`, `nodata`
- `leer_ghs(ruta, sha256: str) -> TeselaGHS`
- `ventana_necesaria(celdas) -> dict[str, float]`
- `estaticos_celdas(celdas, teselas, ghs, estaticas_v1, lulc, umbrales) -> pd.DataFrame`
- `tpi_entra_a_estandarizar(tpi, truncado) -> np.ndarray`
- `estandarizar_tpi(tpi, truncado, media: float, desvio: float) -> np.ndarray`
- `nasadem_en_pixeles(catalogo, teselas) -> pd.DataFrame`
- `info_estaciones(catalogo, celdas, teselas, umbrales, *, macrozona_region, conjuntos) -> dict`
- `fuera_de_la_grilla(info: tipos.InfoEstacion) -> bool`
- `declaraciones_estaciones(infos: Mapping[str, tipos.InfoEstacion]) -> dict[str, Any]`
- `tabla_estaciones(infos: Mapping[str, tipos.InfoEstacion]) -> pd.DataFrame`

**`fondo_era5l.py`**

- clase `ErrorFondo(RuntimeError)`
- clase `ErrorUnidades(ErrorFondo)`
- clase `ErrorAlineacion(ErrorFondo)`
- clase `MesE5L`: campos `tiempos`, `pixel_id`, `datos`, `sha256`
  - `yyyymm(self) -> int`
  - `completo_hasta(self, h_ultima) -> bool`
- `leer_mes(ruta, *, sha256: str | None=None) -> MesE5L`
- `comprobar_unidades(mes: MesE5L, umbrales=None) -> None`
- `pixeles_validos(meses_referencia: Mapping) -> np.ndarray`
- clase `Geopotencial`: campos `lat`, `lon`, `z`, `sha256`
- `leer_geopotencial(ruta, *, sha256: str | None=None) -> Geopotencial`
- `z_e5l(geopotencial: Geopotencial, catalogo, nasadem, sp_medio, umbrales, *, validos) -> pd.DataFrame`
- `comprobar_alineacion(z, parquet_altitud) -> None`
- `operador(lat, lon, z, catalogo, validos, z_pix, umbrales, *, ids=None) -> tipos.OperadorPuntos`
- `operador_pixeles(pixel_ids, catalogo, validos, z_pix) -> tipos.OperadorPuntos`
- `columnas_operador(op: tipos.OperadorPuntos) -> pd.DataFrame`
- `operador_desde_columnas(ids, z, tabla, z_pix) -> tipos.OperadorPuntos`
- `campos_fondo(mes: MesE5L, op: tipos.OperadorPuntos, umbrales, *, recortar_td: bool=True) -> dict`
- `producto_desde(F: Mapping, R: Mapping) -> dict`
- `residuos(obs: Mapping, F: Mapping) -> dict`
- `amplitud_dia_utc(T, h) -> np.ndarray`
- `tabla_puntos(h, F: Mapping) -> pd.DataFrame`
- `en_horas(F_estacion: pd.DataFrame, h) -> dict`
- `horas_de(meses: Sequence[MesE5L]) -> np.ndarray`
- `incrementos_tp(meses: Sequence[MesE5L]) -> np.ndarray`
- `sumas_rr06(tp_horario, h_fin, *, h) -> np.ndarray`
- `pixel_de_lluvia(celdas, enlaces: pd.DataFrame) -> np.ndarray`
- `lluvia_rr06(tp_horario, h_fin, pixel, *, h, pixel_ids) -> tuple[np.ndarray, np.ndarray]`
- clase `AcumuladorEstado`: campos `pixel_id`, `suma`, `n`, `suma_sp`, `n_sp`, `meses`
- `acumulador_estado(pixel_id) -> AcumuladorEstado`
- `climatologias_estado(acumulador: AcumuladorEstado, mes: MesE5L) -> None`
- `tabla_clima_estado(acumulador: AcumuladorEstado) -> pd.DataFrame`
- `clima_en_puntos(clima: pd.DataFrame, op: tipos.OperadorPuntos, umbrales) -> dict`
- `clima_en_horas(clima_puntos: Mapping, h) -> dict`
- `sp_medio_hpa(acumulador: AcumuladorEstado) -> pd.Series`

**`particiones.py`**

- `grupos_mismo_sitio(infos, umbrales) -> dict[str, str]`
- `bloque(lat, lon, umbrales)`
- `pliegues_p1(grupos, umbrales) -> list`
- `pliegues_p2(infos, grupos, umbrales) -> list`
- `pliegues_internos(externo, infos, grupos, umbrales) -> list`
- `dias_de_seleccion(h, umbrales, *, recorte: bool)`
- `distancia_entrenamiento_km(prueba, entrenamiento, infos, horas_validas, umbrales) -> dict[str, float]`
- `bloques_remuestreo(infos) -> dict[str, str]`

**`homogeneidad.py`**

- `mes2000(h) -> np.ndarray`
- `hora_utc(h) -> np.ndarray`
- `medianas_mes_hora(h, valores, validos, umbrales) -> pd.DataFrame`
- `horas_estables(medianas, k: int, umbrales) -> frozenset[int]`
- `salto(medianas, k: int, umbrales) -> float | None`
- `segmentar(medianas, umbral: float, umbrales) -> list[tuple[int, float]]`
- `k4(tabla_estacion, p_F, z_cat: float, umbrales, *, codigo: str) -> ResultadoK4`
- `tramos_homogeneos(h, residuo, variable, umbrales) -> list[tuple[int, int]]`
- `desplazamientos(h, residuo, tramos, umbrales) -> dict[int, float]`

**`sinca_meteo.py`**

- clase `ErrorSinca(ValueError)`
- `leer_manifiestos(raiz, huellas: dict[str, str]) -> pd.DataFrame`
- `altura_de(altura_ficha: str, macro_ficha: str) -> tuple[float | None, str]`
- `series_descartadas(manifiesto, umbrales) -> pd.DataFrame`
- `elegir_series(manifiesto, umbrales) -> pd.DataFrame`
- `leer_politica_temporal(ruta, *, sha256: str=SHA_POLITICA_TEMPORAL) -> dict`
- `zona_de(region: str, politica) -> str`
- `huella_contenido(tabla) -> str`
- `veredictos_civiles(tabla, convencion: str, *, sha256: str, resumen: Mapping[str, Any]) -> dict`
- `parsear_serie(texto: str) -> tuple[np.ndarray, np.ndarray, dict[str, int]]`
- `horas_fin_utc(etiquetas, civil, *, zona: str | None=None, convencion: str | None=None) -> pd.DataFrame`
- `control_minimo(variable: str, valores, umbrales) -> tuple[np.ndarray, np.ndarray, np.ndarray]`
- `leer_serie(raiz, fila, politica_temporal, umbrales, *, veredictos) -> tuple[pd.DataFrame, dict]`
- `series_horarias(raiz, elegidas, politica_temporal, umbrales, *, veredictos) -> pd.DataFrame`

**`decision.py`**

- clase `VariablesGrupo`: campos `S`, `CD`, `EX`, `MZ`, `nivel`, `anomalia`, `TF`
- `compuertas(uso, grupo, tabla, umbrales) -> pd.DataFrame`
- `decidir_combinacion(uso, grupo, entradas, *, umbrales) -> DecisionGrupo`
- `decision_json(decisiones, hiperparametros, huellas: dict) -> dict`
- `condiciones_anexo_b(comparacion, contaminante: str, sentido: str, umbrales) -> list[bool]`
- `variante_o3(por_contaminante: dict) -> str`
- `decisiones_restringidas(entradas_ambientales, grupos_con_b_ab, *, umbrales) -> dict[str, DecisionGrupo]`
- `ganador_restringido(entradas_ambientales, grupos_con_b_ab, *, umbrales) -> dict`
- `ramas_m6(condiciones: dict, tf_contaminantes: dict, ganador_ambiental: dict, *, entradas_ambientales=None, umbrales=None) -> DecisionM6`
- `decision_m6_json(decision: DecisionM6, huellas: dict) -> dict`

**`qc_dmc_meteo.py`**

- `clave_marca(m) -> str`
- `clave_q1(m) -> str`
- `normalizar_artefacto(manifiesto, politicas, *, adaptador, dmc_features, validar_regla, sha_adaptador, id_artefacto, artefactos: Mapping[str, str]) -> ResultadoArtefacto`
- `unir_largas(resultados: Iterable[ResultadoArtefacto]) -> pd.DataFrame`
- `qc_meteo_combinada(larga, info, F_estacion, umbrales, *, k2: frozenset[str], politicas)`
- `entrada_k4(tabla, F_estacion) -> tuple[pd.DataFrame, np.ndarray]`
- `k4_estacion(tabla, F_estacion, info, umbrales) -> ResultadoK4`
- `aplicar_k4(tabla, resultado: ResultadoK4, umbrales)`
- `marca_14(tabla, F_estacion, umbrales, *, tramos: Sequence[TramoPolitica])`
- `qc_estacion(larga, info, F_estacion, umbrales, *, k2, politicas) -> tuple[pd.DataFrame, ResultadoK4, list[dict]]`
- `tabla_ancha(tabla)`
- `conteos_estacion(tabla, info) -> tuple[pd.DataFrame, pd.DataFrame]`
- `conteos_artefactos(resultados: Iterable[ResultadoArtefacto], infos: Mapping[str, tipos.InfoEstacion]) -> tuple[pd.DataFrame, pd.DataFrame]`
- `tabla_no_normalizables(resultados: Iterable[ResultadoArtefacto], infos: Mapping[str, tipos.InfoEstacion]) -> pd.DataFrame`
- `alarmas(conteos, denominadores, umbrales) -> list[dict]`
- `lista_descriptiva(conteos, denominadores, umbrales) -> list[dict]`
- `resumen_qc(conteos, alarmas, no_normalizables, sin_traslado, *, denominadores, lista, umbrales) -> dict`
- `sumas_lluvia_rr06(tablas, infos, enlaces, tp_horario, *, h, pixel_ids, previas=None) -> dict`
- `validar_rr06(tablas, tp_sumas, infos, umbrales) -> dict`

**`candidatos.py`**

- clase `ErrorCandidatos(ValueError)`
- clase `SinSeleccion(ErrorCandidatos)`
- `puntos_de_estaciones(infos: Mapping[str, Any], codigos=None) -> dict`
- `distancia_efectiva(puntos, estaciones, lam: float) -> np.ndarray`
- clase `VecinosEntrenamiento(tipos.VecinosNucleo)`: campos `codigos`, `grupos`, `grupo_est`
- `vecinos(puntos, entrenamiento, hiper, umbrales) -> VecinosEntrenamiento`
- `sumas_nucleo(vec, q, disponible) -> tuple[np.ndarray, np.ndarray]`
- `campo(vec, q, disponible) -> tuple[np.ndarray, np.ndarray]`
- `interpolar_no_observadas(h, rt, umbrales) -> tuple[np.ndarray, np.ndarray]`
- `residuos_estacion(codigo: str, h, r: Mapping, umbrales) -> tuple[pd.DataFrame, pd.DataFrame]`
- `climatologia_a(h, r, umbrales, *, codigo: str, variable: str) -> pd.DataFrame`
- `climatologias_a(residuos: Mapping[str, pd.DataFrame], umbrales) -> pd.DataFrame`
- `correccion_a(vec, clima, h) -> np.ndarray`
- `correccion_b(vec, rt, disponible) -> np.ndarray`
- `correccion_ab(vec_a, vec_ab, clima, anomalias, disponible, h) -> np.ndarray`
- clase `SumasC`: campos `codigo`, `variable`, `diseno`, `xtx`, `xty`, `yty`, `n_filas`, `peso`, `horas`
- `estado_c(F_estacion: pd.DataFrame, h) -> dict[str, np.ndarray]`
- `estado_c_est(clima_estacion: Mapping[str, np.ndarray], h) -> dict[str, np.ndarray]`
- `diseno_c(estaticos, h, estado, umbrales=None, *, climatologico: bool=False) -> np.ndarray`
- `diseno_estandarizado(X_bruto, modelo: ModeloC) -> np.ndarray`
- `filas_c(residuos, estaticos, estados, umbrales, *, infos, climatologico: bool=False) -> dict`
- `ajustar_c(sumas_por_estacion, entrenamiento, alfa: float) -> ModeloC`
- `predecir_c(modelo, estaticos, h, estado) -> np.ndarray`
- `matriz_q(datos, codigos, candidato, variable, horas, umbrales) -> np.ndarray`
- `fuera_de_rango_c(estaticos_celdas, estaticos_entrenamiento) -> np.ndarray`
- `seleccionar(candidato, variable, uso, externo, datos, umbrales, *, objetivo: Callable, recorte: bool, hiper_a: Hiper | None=None) -> object`
- `predecir_prueba(candidato, variable, uso, hiper, externo, datos, *, umbrales) -> pd.DataFrame`

**`validacion.py`**

- `dia_civil(h, zona: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]`
- `dias_validos(h, valido, zona: str, umbrales) -> pd.DataFrame`
- `medias_diarias(h, pred, obs, zona: str, umbrales) -> pd.DataFrame`
- `metricas_horarias(pred, obs, variable) -> dict`
- `nivel_diario(diario) -> float`
- `desviacion_estrato(diario, umbrales) -> float`
- `anios_validos(diario, umbrales) -> dict[int, float]`
- `anomalias(anuales, umbrales) -> dict[int, float] | None`
- `medias_macrozona_anio(por_evaluacion: Mapping[Any, Mapping[int, float]], macrozona_de: Mapping[Any, str | None]) -> dict[tuple[str, int], float]`
- `anual_neto(anuales, macrozona) -> float`
- `anomalia_interanual(anuales, macrozona, umbrales) -> float`
- `ciclo_diario(h, pred, obs, umbrales) -> float`
- `cociente_amplitudes(h, pred, obs, umbrales) -> float`
- `diarios_de(diario) -> tuple[pd.DataFrame, pd.DataFrame]`
- `extremos(diario_pred, diario_obs, uso, variable, umbrales) -> float`
- `extremos_descriptivos(serie_pred, serie_obs, umbrales) -> dict`
- `descriptivos_de(uso, variable) -> tuple[str, ...]`
- `evaluacion(h, pred, obs, *, uso, variable, umbrales, zona: str=tipos.ZONA_CIVIL) -> dict | None`
- `fila_evaluacion(metricas: Mapping[str, Any], *, codigo: str, particion: str, pliegue: str, candidato: str, uso, variable, frac_sin_soporte: float) -> dict`
- `tabla_evaluaciones(filas: Iterable[Mapping[str, Any]]) -> pd.DataFrame`
- `completar_cronico(evaluaciones, anuales: Mapping[tuple[str, str, str], Mapping[int, float]], infos, umbrales) -> pd.DataFrame`
- `rotulos_bandas(umbrales) -> tuple[str, ...]`
- `bandas(distancias_km, umbrales) -> np.ndarray`
- `bandas_de_pliegues(pliegues, infos, horas_validas: Mapping[str, Mapping[str, float]], umbrales) -> dict[tuple[str, str, str], int]`
- `pi_poblacion(celdas_pobladas, estaciones_por_anio, variable, umbrales) -> dict`
- `pi_monitores(pliegues_red2, panel_red2, estaciones_por_anio, variable, umbrales) -> dict`
- `pi_uso(uso, pi_pob, pi_mon=None, *, umbrales) -> np.ndarray`
- `puntaje(mse_e, banda_e, pi, umbrales) -> float`
- `puntaje_par(S_T: dict, S_HR: dict, e0) -> dict`
- `publicable(frac_sin_soporte: dict, umbrales) -> bool`
- `estratos(evaluaciones, infos, umbrales, *, uso, grupo, banda, pi, periodos=None) -> pd.DataFrame`
- `fracciones_sin_soporte(evaluaciones, infos, umbrales, *, uso, grupo, banda, pi, periodos=None) -> pd.DataFrame`
- `tabla_bandas(evaluaciones, infos, umbrales, *, uso, grupo, banda, pi_pob, pi_mon=None) -> pd.DataFrame`
- `filas_descriptivas(metricas: Mapping[str, Any], *, codigo: str, particion: str, candidato: str, uso, variable) -> list[dict]`
- `tabla_descriptivos(evaluaciones, descriptivas, infos, umbrales, *, uso, grupo, banda, pi) -> pd.DataFrame`
- `remuestreo(evaluaciones, bloques, umbrales, *, infos, uso, grupo, banda, pi, e0) -> pd.DataFrame`
- `replica_n(entradas, infos, umbrales, *, decidir: Callable) -> dict`
- `validacion_sinca(series, producto_celda, producto_punto, tpi, umbrales, *, ganadores=None, e0=None, macrozonas=None, zona: str=tipos.ZONA_CIVIL) -> dict`

**`tendencias.py`**

- clase `ErrorTendencias(ValueError)`
- `anio_de(h) -> np.ndarray`
- `mes2000(h) -> np.ndarray`
- `horas_del_anio(anio: int) -> int`
- `red_historica(horas_validas_anio, variable, umbrales) -> frozenset[str]`
- `anios_regla(regla) -> tuple[int, int]`
- `red_constante(horas_validas_anio, variable, umbrales) -> tuple[frozenset[str], str]`
- clase `EscenariosTF`: campos `variable`, `historica`, `constante`, `regla`
  - `evaluable(self) -> bool`
  - `n_red(self) -> int`
  - `anios(self, escenario: str, pruebas: Sequence[str]=PRUEBAS) -> tuple[int, ...]`
  - `red(self, escenario: str, anio: int) -> frozenset[str] | None`
- `escenarios_tf(horas_validas_anio, variable, umbrales) -> EscenariosTF`
- `medias_comuna_anio(campo_lote, h, pesos_2020, comunas, *, orden=None) -> np.ndarray`
- clase `MediasComunaAnio`: campos `comunas`, `anios`, `media`
  - `en(self, anios) -> np.ndarray`
- clase `AcumuladorComunas`
  - `__init__(self, comunas) -> None`
  - `sumar(self, clave, anio: int, sumas: np.ndarray) -> None`
  - `claves(self) -> tuple`
  - `medias(self, clave) -> MediasComunaAnio`
- `media_p95_ponderados(x, w) -> tuple[float, float]`
- `delta_tf1(cambio: MediasComunaAnio, completo: MediasComunaAnio) -> np.ndarray`
- `delta_tf2(constante: MediasComunaAnio, completo: MediasComunaAnio, anios) -> np.ndarray`
- `tf1(cambio, completo, pesos_comuna, umbrales, variable) -> dict`
- `tf2(constante, completo, pesos_comuna, umbrales, variable, regla: str) -> dict`
- `comprobar_cero(candidato, resultado: Mapping) -> None`
- `producto_tf(variable, F: Mapping, R: Mapping) -> np.ndarray`
- clase `CeldasTF`: campos `ids`, `lat`, `lon`, `z`, `cod_comuna`, `w_ghs`, `estaticos`, `clima_estado`
  - `n(self) -> int`
  - `puntos(self) -> dict`
- `celdas_tf(tabla, z, *, estaticos=None, clima_estado=None) -> CeldasTF`
- `combinaciones_nucleo(umbrales) -> tuple[Hiper, ...]`
- `etiqueta_hiper(hiper) -> str`
- clase `PasadaTF`
  - `__init__(self, datos, celdas: CeldasTF, escenarios: Mapping[str, EscenariosTF], configuraciones, umbrales, *, variables: Sequence[str]=VARIABLES_TF, pruebas: Sequence[str]=PRUEBAS, entrenamiento=None, lote_puntos: int=LOTE_PUNTOS_TF) -> None`
  - `anios(self) -> tuple[int, ...]`
  - `sumas_mes(self, h_mes, fondo: Callable) -> dict`
  - `correccion_mes(self, h_mes, fondo: Callable, candidato, etiqueta: str, variable_producto: str, *, red: frozenset[str] | None=None) -> np.ndarray`
  - `acumular(self, meses: Iterable[Mapping]) -> 'MediasTF'`
  - `meses(self, horas) -> list[np.ndarray]`
  - `correr(self, horas, fondo: Callable) -> 'MediasTF'`
- clase `MediasTF`: campos `comunas`, `pesos_comuna`, `tareas`, `escenarios`, `pruebas`, `medias`
- `resultados_tf(medias: MediasTF, umbrales, *, comprobar: bool=True) -> dict`
- `tf_por_uso(ambiental: Mapping | None=None, salud: Mapping | None=None) -> dict`
- `filas_tf(por_uso: Mapping, escenarios: Mapping[str, EscenariosTF]) -> pd.DataFrame`
- `compuerta_deriva(resultados_s6: dict, *, umbrales) -> dict[str, bool]`
- `contenido_deriva_s6(resultados_s6: dict, compuerta: Mapping[str, bool], *, regla: str, n_red: int, parametros: Mapping | None=None) -> dict`
- `dias_tf_contaminantes(d2000, umbrales) -> np.ndarray`
- `muestra_tf_contaminantes(celdas_pobladas, pesos, umbrales) -> np.ndarray`
- `tf_contaminantes(fabrica, modelo, variante, muestra, umbrales, *, verificacion_un_mes: bool=False) -> dict`

**`producto.py`**

- clase `ErrorProducto(RuntimeError)`
- clase `DesbordeInt16(ErrorProducto)`
- `estado_c_puntos(T_F, Td_F, u_F, v_F, amp) -> dict[str, np.ndarray]`
- `correccion(candidato, hiper, puntos, lote_h, datos, *, umbrales, uso, fondo=None, estaticos=None, clima=None, celdas=None, entrenamiento=None, lote_puntos: int | None=None) -> dict`
- `direccion_hacia(u, v) -> np.ndarray`
- `campos(F: dict, R: dict) -> dict`
- `producto_mes(mes, op, puntos, ganador, hiper, datos, *, umbrales, uso, estaticos=None, clima_estado=None, celdas=None, entrenamiento=None, lote_puntos: int | None=None) -> tuple[dict, dict]`
- `formato_int16(umbrales) -> tuple[dict[str, tuple[float, float]], int]`
- `codificar_int16(campos: dict, umbrales) -> dict`
- `decodificar_int16(enteros: dict, umbrales) -> dict`
- `atributos_01deg(h, uso, ganador, huellas) -> dict[str, str]`
- `mes_01deg(campos: dict, pixel_id, h, umbrales, huellas: dict, *, uso, ganador) -> bytes`
- clase `ConteoFinito`: campos `n_puntos_hora`, `n_finitos`
  - `fraccion(self) -> float`
  - `pasa(self) -> bool`
  - `como_dict(self) -> dict`
- `sumar_conteos(conteos) -> ConteoFinito`
- `hay_fondo(F: Mapping, *, variables=None, grupo=None) -> np.ndarray`
- `conteo_finito(campos: Mapping, con_fondo, *, variables=None, grupo=None) -> ConteoFinito`
- `fraccion_finita(campos: dict, con_fondo, *, variables=None, grupo=None) -> float`
- `pasa_e0(conteos: Mapping[str, ConteoFinito]) -> bool`
- `conteo_finito_c(candidato, puntos, lote_h, con_fondo, *, estaticos, fondo=None, clima=None, celdas=None, lote_puntos: int | None=None) -> ConteoFinito`

**`salud.py`**

- clase `ErrorSalud(RuntimeError)`
- `dias(h, zona: str | None) -> np.ndarray`
- `horas_esperadas(dias, zona: str | None) -> np.ndarray`
- `zonas_por_comuna(comunas) -> dict[int, str]`
- `dias_del_anio(h, anio: int) -> np.ndarray`
- clase `PesosComuna`: campos `anio`, `anio_pesos`, `comunas`, `celdas`, `comuna_de_celda`, `w`, `matriz`, `huella`
- `pesos_comuna(anio: int, celdas, tabla_pesos) -> PesosComuna`
- clase `PesosLluvia`: campos `anio`, `anio_pesos`, `comunas`, `pixeles`, `fila`, `col`, `w`, `w_norm`, `cortes`, `comunas_por_area`
- `pesos_lluvia(anio: int, celdas, enlaces, tabla_pesos) -> PesosLluvia`
- `hr_del_producto(T, Td) -> np.ndarray`
- `lluvia_horaria(h, tp) -> np.ndarray`
- `lluvia_comunal(h, tp, pixel_id, pesos: PesosLluvia, tipo_dia: str, *, dias=None) -> pd.DataFrame`
- clase `AcumuladorMeteo`
  - `__init__(self, pesos: PesosComuna, h, tipos_dia: Sequence[str], *, dias=None)`
  - `agregar(self, campos: Mapping, celdas, *, horas=None) -> None`
  - `tabla(self, tipo_dia: str, lluvia: pd.DataFrame) -> pd.DataFrame`
- `meteo_comunal(campos_celda, lluvia, pesos, tipo_dia, *, dias=None) -> pd.DataFrame`
- `representatividad(diarios_obs, t2m_pixel_reloj, umbrales, *, zona: str | None=ZONA_BASE) -> frozenset[str]`
- `metadatos_tabla(tabla: pd.DataFrame) -> dict`
- `cronico_anual(diarios, pesos_por_anio) -> pd.DataFrame`
- `insumos_s14(anio: int, rutas) -> dict[str, Path]`
- `regresion_s14(anio: int, rutas, *, esquema_v3: dict, umbrales, exigir_huellas: bool=True, lote_celdas: int=LOTE_CELDAS_S14) -> dict`

**`ambiental.py`**

- clase `ErrorAmbiental(RuntimeError)`
- `horas_dia_utc(dias) -> np.ndarray`
- `direccion_sin_cos(u, v) -> tuple[np.ndarray, np.ndarray]`
- `leer_decision(decision, *, decision_sha256: str | None=None) -> tuple[dict, str]`
- `etiqueta_hiper(h: Hiper) -> str`
- `ganador_ambiental(decision: Mapping, *, restringido=None) -> tuple[dict[str, str], dict[str, Any]]`
- clase `NucleoGrilla`: campos `hiper`, `indptr`, `indices`, `d_ef`
- clase `OperadorGrilla`: campos `celdas`, `lat`, `lon`, `z`, `pix`, `w`, `dz`, `respaldo`, `codigos`, `grupos`, `grupo_est`, `n_vecinos`, `nucleos`, `ganador`, `hiper`, `nucleo_de`, `estaciones_sha256`, `decision_sha256`, `umbrales`, `restringido`, `ramas_m6_sha256`, `umbrales_sha256`, `sha256`
  - `candidato_de(self, variable: str) -> Candidato`
  - `indices(self, celdas) -> np.ndarray`
  - `puntos_fondo(self, idx) -> tipos.OperadorPuntos`
  - `vecinos(self, etiqueta: str, idx) -> 'candidatos.VecinosEntrenamiento'`
  - `matriz_fondo(self)`
  - `matriz_nucleo(self, etiqueta: str)`
  - `cabecera(self) -> dict`
  - `a_bytes(self) -> bytes`
  - `tamano_bytes(self) -> int`
- `leer_operador(datos, *, sha256: str | None=None) -> OperadorGrilla`
- `operador_grilla(decision, *, celdas, estaciones, catalogo, z_celdas, validos, z_pix, umbrales, decision_sha256: str | None=None, restringido=None, ramas_m6_sha256: str | None=None) -> OperadorGrilla`
- `columnas_bloque(celdas, horas, variante, *, operador, meses, datos, umbrales, estaticos=None, redes=None, float64: bool=False) -> dict[str, np.ndarray]`
- `mc_bloque(celdas, horas, variante, *, operador, meses, datos, umbrales, estaticos=None, redes=None) -> pd.DataFrame`
- `huella_contenido(tabla) -> str`
- `lateral_monitores(pol, decision, operador, *, variante='I', panel, pliegues, meses, datos, umbrales, politica, h_ultima, estaticos=None, decision_sha256: str | None=None, pliegues_sha256: str | None=None, panel_sha256: str | None=None, policy_sha256: str | None=None, anios=None) -> tuple[pd.DataFrame, dict]`
- `unir_partes(partes) -> tuple[pd.DataFrame, dict]`
- `cargar_adaptador(ap) -> ModuleType`
- `comprobar_union(tabla, metadatos, adaptador, *, panel=None) -> dict`
- `fabrica_tf_contaminantes(predecir, *, operador, meses, datos, umbrales, escenarios, estaticos=None, horas_de_dias=None) -> Callable`
- `regla_el(ap) -> dict`
- `diferencias_con_el(regla: Mapping) -> list[str]`

**`orquestacion.py`**

- clase `ErrorOrquestacion(RuntimeError)`
- clase `ErrorReanudacion(ErrorOrquestacion)`
- clase `ErrorTrabajador(ErrorOrquestacion)`
- clase `InterrupcionSimulada(RuntimeError)`
- clase `DetencionPorAlarma(ErrorOrquestacion)`
  - `__init__(self, mensaje: str, resultado: dict)`
- clase `Cfg`: campos `rutas`, `umbrales`, `entradas`, `huellas`, `etiqueta`, `procesos`, `modo`, `pares`, `recorte`, `deriva`, `permitidas`, `negativas`, `fabrica_m6`, `procesos_por_fase`
  - `U(self)`
  - `entrada(self, clave: str)`
- `huella_del_codigo() -> str`
- `identidad_funcion(f) -> dict | None`
- `huella_de_corrida(cfg: Cfg, compuerta: str) -> str`
- `carpeta_de(cfg: Cfg, compuerta: str) -> Path`
- `ruta_de_alias(rutas: entorno.Rutas, texto: str) -> Path`
- `huella_archivo(ruta) -> str`
- `leer_entrada(cfg: Cfg, alias_: str) -> bytes`
- `leer_catalogo_dmc(datos: bytes)`
- `leer_conjuntos(cfg: Cfg) -> dict[str, str]`
- `infos_de_tabla(tabla) -> dict[str, tipos.InfoEstacion]`
- clase `Avance`
  - `__init__(self, carpeta, *, corrida: str, huella: str, interrumpir_tras: int | None=None, compuerta: str | None=None, prefijo: str='')`
  - `iniciar(self) -> None`
  - `hecha(self, fase: str, unidad: str, entrada: str) -> dict | None`
  - `parcial_pendiente(self, nombres: Iterable[str], unidad: str) -> None`
  - `registrar(self, fase: str, unidad: str, entrada: str, archivos: Mapping[str, str]) -> str`
- `abrir_avance(cfg: Cfg, compuerta: str, *, interrumpir_tras: int | None=None) -> Avance`
- `repartir(unidades, funcion, procesos: int, *, contexto=_SIN_CONTEXTO, al_terminar: Callable | None=None, permitidas: Sequence[str]=(), registro: list[dict] | None=None) -> list`
- `correr_m2a(cfg, *, avance) -> dict`
- `correr_m34(cfg, *, avance, procesos: int) -> dict`
- `correr_m5(cfg, *, avance, procesos: int) -> dict`
- `correr_m6(cfg, *, avance) -> dict`

**`salidas.py`**

- `clase_de_salida(nombre) -> str | None`
- `corrida_en_curso(carpeta) -> Iterator[Path]`
- `hay_corrida_en_curso() -> bool`
- `vigilar_residuo(guarda: 'ceguera.GuardaResiduo') -> Iterator['ceguera.GuardaResiduo']`
- `escribir(ruta, contenido, *, clase: str, esquema=None, referencia=None, raiz=None, metadatos=None) -> str`
- `agregar_linea(ruta, registro: Mapping, *, raiz=None) -> str`
- `inventario(carpeta) -> dict[str, dict[str, Any]]`
- `escribir_sha256(carpeta, *, raiz=None) -> str`
- `recibo_corrida(huellas: dict, entorno_: dict) -> dict`
- `sellar_corrida(carpeta, huellas_entrada: Mapping, entorno_: Mapping, *, rutas: 'entorno.Rutas') -> str`
- `fallas_de_sello_archivado(carpeta, n: int) -> list[str]`
- `fallas_de_cierre(carpeta_corrida) -> list[str]`
- `carpeta_publicacion(destino_ap) -> Path`
- `es_ap_real(destino_ap) -> bool`
- `publicar_m5(carpeta_corrida, destino_ap) -> list[str]`

**`costo.py`**

- clase `ErrorCosto(RuntimeError)`
- clase `Escala`: campos `nombre`, `estaciones`, `desde`, `horas`, `cobertura`, `lat_norte`, `lat_sur`, `qc_estaciones`, `qc_meses`, `celdas_tf`, `meses_tf`, `mes_m5`, `celdas_salud`, `celdas_grilla`, `lote_grilla`, `lotes_grilla`
  - `artefactos(self) -> int`
- `peor_configuracion(tiempos: Mapping[str, float]) -> dict`
- `ruta_mes_real(rutas) -> Path`
- `fallas_escala(escala: Escala) -> list[str]`
- `carga_ajena(bruta: float, propios: int) -> float`
- `resumen_carga(brutas, propios: int) -> dict`
- `memoria_fisica() -> int`
- `medir(rutas, *, real_era5: bool, umbrales, temporal=None, escala: Escala=ESCALA_REAL, aislar: bool=True, puntos: Sequence[str]=PUNTOS, procesos: int=int(constantes.valor('PROCESOS'))) -> dict`
- `proyectar(mediciones: dict, umbrales, *, procesos: int=int(constantes.valor('PROCESOS'))) -> dict`
- `recorte(proyeccion: dict, umbrales) -> str`
- `contenido_costo(mediciones: dict, proyeccion: dict, umbrales) -> dict`

**`addendum.py`**

- clase `ErrorAddendum(ValueError)`
- `codigo_del_paquete(ap) -> dict[str, Path]`
- `carpeta_bateria(alias_: str) -> str`
- `huellas_fijadas() -> dict[str, str]`
- `claves_lista_cerrada(rutas, *, carpeta_bateria_: str | None=None) -> list[str]`
- `lista_cerrada(rutas, *, bateria: Mapping[str, str] | None=None, rutas_bateria=None) -> dict[str, str]`
- `fuentes_documento(rutas) -> dict[str, str]`
- `texto_vigente(rutas) -> tuple[str, str]`
- `referencia(rutas, *, fuentes: Mapping[str, str] | None=None) -> 'ceguera.ReferenciaDocumento'`
- `anexo_a2(rutas) -> dict`
- `extraer_lecturas(fuentes: Mapping[str, str]) -> list[dict]`
- `extraer_mc(diseno: str) -> list[dict]`
- `decisiones_del_autor(textos: Mapping[str, str]) -> list[dict]`
- `respondidas(decisiones: Sequence[Mapping]) -> dict[str, str]`
- `secciones_coordinacion(texto: str) -> dict[str, list[dict]]`
- `lecturas_m1(rutas, *, fuentes: Mapping[str, str] | None=None) -> dict`
- `veredicto_deriva(pasa: Mapping[str, bool]) -> dict[str, str]`
- `deriva_de_veredicto(veredicto: Mapping[str, str]) -> dict[str, bool]`
- `addendum_m1(lista, anexo_a2, deriva, recorte, costo, lecturas, commits, *, fecha: str | None=None, bateria: Mapping | None=None) -> dict`
- `addendum_md(contenido: Mapping) -> str`

**`verificar_meteo_combinada.py`**

- clase `ErrorCerrojo(RuntimeError)`
- clase `ErrorConfiguracion(ValueError)`
- clase `Falla`: campos `motivo`, `texto`
- `micromamba_list() -> str`
- clase `Servicios`: campos `ahora`, `micromamba`, `medidor`, `ejecutores`, `fabrica_m6`
  - `ejecutor(self, compuerta: str) -> Callable`
  - `costo(self)`
- clase `Consola`
  - `__init__(self, referencia: 'ceguera.ReferenciaDocumento')`
  - `__call__(self, texto: str) -> None`
- `registro_en_git(alias_: str, rutas) -> list[str]`
- `archivo_en_commit(alias_: str, rutas, commit: str, sha256: str) -> list[str]`
- `arbol_limpio(rutas, rutas_protocolo: Iterable[str]) -> list[str]`
- `igual_al_remoto(rutas, rutas_protocolo: Iterable[str]) -> list[str]`
- clase `Corrida`: campos `intento`, `etiqueta`, `huella`, `errata`, `resultado`, `cruzo`
  - `terminal(self) -> bool`
- clase `Cerrojo`
  - `__init__(self, rutas, compuerta: str)`
  - `verificar(datos: bytes) -> list[dict]`
  - `releer(self, *, cotejar: bool=True) -> None`
  - `registrar(self, registro: Mapping) -> dict`
  - `retener(self)`
  - `copiar_a(self, carpeta_corrida) -> str`
  - `corridas(self) -> list[Corrida]`
  - `confirmatorias(self) -> list[Corrida]`
  - `pendiente(self) -> Corrida | None`
  - `sellada(self, etiqueta: str | None=None) -> Corrida | None`
  - `fallas(self, etiqueta: str | None, huella: str, errata: int | None) -> list[Falla]`
- `leer_addendum(alias_: str, rutas) -> tuple[dict, str]`
- `leer_entradas(alias_: str, rutas, compuerta: str) -> tuple[dict, str]`
- `leer_errata(alias_: str, rutas, compuerta: str) -> tuple[int, str, dict]`
- `negativas_m34(cfg) -> list[str]`
- `negativas_m6(cfg) -> list[str]`
- `negativas_m2a(cfg) -> list[str]`
- `negativas_m5(cfg) -> list[str]`
- clase `Negativas`
  - `__init__(self, compuerta: str)`
  - `fallas(self, cfg) -> list[Falla]`
  - `__call__(self, cfg) -> list[str]`
- `directorio_neutro()`
- `correr_bateria(rutas, *, servicios: Servicios | None=None, patrones: Sequence[str]=(), suite: unittest.TestSuite | None=None, costo: bool=False, commits: Mapping[str, str] | None=None, consola: Consola | None=None, forzar_completa: bool=False) -> int`
- `analizar_argumentos(argv: Sequence[str] | None) -> argparse.Namespace`
- `main(argv: Sequence[str] | None=None, *, rutas=None, servicios: Servicios | None=None) -> int`

**`meteo_combinada.py`**

- `modulo_de(nombre: str) -> str`
- `__getattr__(nombre: str)`
- `__dir__() -> list[str]`
