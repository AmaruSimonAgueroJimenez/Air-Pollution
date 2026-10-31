# Coordinación de la implementación M1 (producto meteorológico combinado)

Notas del coordinador y de los implementadores para las olas siguientes y para el addendum de M1. Se agregan al final,
por fecha, como `reloj_dmc/COORDINACION_C1.md`.

- **Texto vigente del código (2026-10-28):** v2.4, `APH/auditoria/20261023/meteo_combinada/enmienda3/PROTOCOLO_METEO_COMBINADA_v2.4.md`
  (eaedb109…). Enmienda 3 operativa adoptada por D65, `post_hoc = true`, pendiente de nuevo anclaje; se conserva el
  v2.3 anclado (b4175f78…, APH dd6c1c6). **Manda el texto.**
- **Diseño:** `DISENO_IMPLEMENTACION_M1.md`. **Decisiones:** D1-D8 en
  `APH/auditoria/20261023/meteo_combinada/enmienda1/decisiones_autor_20261026.md`; D9-D64 en
  `APH/auditoria/20261023/meteo_combinada/m1/decisiones_autor_m1_20261026.md`; D65-D67 en
  `APH/auditoria/20261023/meteo_combinada/enmienda3/decisiones_autor_20261028.md`. No se alteran esas fuentes.
- **Reglas de trabajo:** §0 del diseño. Un dueño por módulo y por su archivo de pruebas. Un cambio de `tipos.py` se pide
  al coordinador y se anota aquí; si cambia el comportamiento, va al addendum de M1.
- **Preguntas para el autor:** en la sección «Preguntas para el autor» de cada ola, con cita y propuesta. Nadie decide
  un punto donde el texto se contradice o calla en algo que cambia resultados.

## Ola 0 cerrada (2026-10-26)

**Qué quedó.** El esqueleto del paquete `meteo_combinada/`, con los 28 módulos de §1 del diseño y sus firmas de §3, y 27
archivos de pruebas (uno por módulo, más `test_meteo_combinada.py` y `test_tipos.py`). La suite da 255 pruebas: 33 pasan,
222 omitidas «por implementar» y ningún fallo. Importa con el intérprete fijado sin `__pycache__` y sin abrir ni listar
nada bajo /Volumes (lo comprueba un gancho de auditoría en un intérprete aparte,
`test_meteo_combinada.test_esqueleto_importa_sin_volumes_ni_pycache`).

**Implementado por el coordinador (I0):**
- `__init__.py`: `sys.dont_write_bytecode` y los hilos en «1» si numpy no está cargado (MC-36).
- `tipos.py` completo: enumerados, identificadores de §2.1, los 20 esquemas de §2.3 (`Esquema`, con su versión),
  `validar_esquema`, `tabla_vacia` (carga pandas sólo al llamarse) y las clases de datos de §2.4. Sus lecturas TIP-1 a
  TIP-7 están en su encabezado.
- `meteo_combinada.py` (la fachada perezosa, como la del reloj) y sus pruebas.
- `test_meteo_combinada.py`: fachada, grafo por capas (AST), índice de §9 con `EN_CURSO`, nombres prohibidos,
  escritura sólo en `salidas`, `entorno` y `sintetico`, privacidad del paquete y la importación del esqueleto.
- `test_tipos.py`: la tabla de marcas de §2.4 del texto vigente (bits, nombres y «¿Invalida?») contra `tipos`, los
  esquemas, `InfoEstacion` igual a `ESQUEMA_ESTACIONES_MC` e identificadores.
- En `constantes.py`, las once definiciones físicas que usa `numerico` (Magnus agua y hielo, p_std, hipsométrica, 287,05,
  9,80665, 0,622 y 0,378, z_impl, 273,15, nudos y R = 6.371 km), con su sección y fragmento, y `valor()`. Así I2 e I3
  trabajan en paralelo sobre los mismos nombres. I2 conserva nombres y valores y completa la verificación.
- En `umbrales.py`, las rutas relativas a APH del v2.1, del JSON, de `preparar_m0.py` y del v2.2, y `SHA_TEXTO_VIGENTE`.

**Decisiones de interfaz del coordinador** (no cambian reglas; van al addendum como lecturas de implementación):
1. **Grafo.** `test_meteo_combinada.DEPENDENCIAS` copia la columna «Depende de» de §1. Dos lecturas:
   - `orquestacion` («los de ciencia, más ceguera, sinca_meteo y entorno») puede importar todo lo de las capas 0 a 5
     salvo `sintetico`, **y `salidas`**: escribe sus unidades y `avance.jsonl` por `salidas`, la única escritura (§0,
     regla 8). La tabla de §1 no lo nombraba.
   - `ceguera` depende sólo de `entorno`, como dice la tabla: por eso las clases de salida (`CLASES_SALIDA`) viven en
     `ceguera` y no en `tipos`.
2. **Prueba de escritura** (§0, regla 8). Además de lo que lista el diseño, cuenta como escritura `to_csv`,
   `to_netcdf`, `to_json`, `write_table`, `escribir_atomico`, `touch`, `unlink` y `os.replace`/`os.rename`/`shutil.*`.
3. **Privacidad del paquete.** La regla de AP público (ni rutas absolutas de la carpeta de usuario ni el correo) se aplica también a las
   pruebas y a los documentos de la carpeta: ningún archivo trae la ruta de la carpeta de usuario ni la arroba, salvo
   los decoradores de Python. Las pruebas que necesiten esos textos los arman en tiempo de ejecución
   (`"/" + "Users" + "/x"`, `chr(64)`).
4. **Huellas de §9.3.** En las olas 0 y 1 se comprueban las del código, los textos, la configuración y el intérprete. Las
   de datos (catálogo y manifiestos de ERA5L, geopotencial, altitud de los píxeles, NASADEM, grilla, GHS-POP y SINCA) se
   escriben como constantes de `fijados`, pero se comprueban en M2a o en la batería con permiso explícito: leerlas exige
   abrir datos reales, y estas olas son sintéticas (prueba omitida con el motivo).
5. **Clausura del reloj (MC-17).** Desde el 2026-10-25 el código del reloj está en git: AP `4b50b0d` («Reloj DMC,
   compuerta C1: código del procedimiento y código fijado con huella de C0»), con `reloj_dmc/` y el código fijado
   (`meteorologia_v2.py`, `dmc_features.py`, `preflight_v3.py`, `_meteo_guard.py` y el descargador). El pendiente 1 de
   §10 del diseño queda resuelto para ese código; falta `meteo_combinada/`. La batería del reloj corre sobre ese commit,
   así que el C1 del reloj todavía no aprobó: la clausura sigue la regla de MC-17.
6. **`EN_CURSO`** lista los archivos de pruebas de las olas 2 a 6, y por ahora `test_ceguera.py` y
   `test_particiones.py` (ola 1). Se vacía al cerrar M1 (`test_en_curso_vacia_al_cerrar_m1`, omitida hasta entonces).
7. **Lectura del esquema de la grilla.** Para fijar las 7 columnas `lulc_*` (TIP-7) se leyó sólo el esquema (nombres y
   tipos, sin valores) de `celdas.parquet`, `estaticas.parquet`, `estaticas_lulc.parquet` y `enlaces_productos.parquet`,
   como el diseño. Ninguna otra lectura de datos.

## Ola 1: encargos (2026-10-26)

| Dueño | Módulos y pruebas | Entrega |
|---|---|---|
| I1 | `entorno.py`, `fijados.py`; `test_entorno.py`, `test_fijados.py` | rutas por alias, carpetas, hilos; huellas de §9.3 del código; clausura del reloj y su validador; extracciones por AST |
| I2 | `umbrales.py`, `constantes.py`; `test_umbrales.py`, `test_constantes.py` | §4.3 en verde (JSON byte a byte desde el v2.1 y Anexo A del v2.2 idéntico, m-8); Anexo P; anexo A2 con completitud; detector de literales |
| I3 | `numerico.py`, `particiones.py`; `test_numerico.py`, `test_particiones.py` | funciones de §3; grupos, P1, P2, internos, días y bloques; la parte de S5 de las particiones |
| I4 | `ceguera.py`; `test_ceguera.py` | `RegistroAccesos` (léxica antes de resolver), `SinRed`, procesos, vocabulario por clases (D3), `permitido_de_reloj`, `GuardaResiduo`; S10 parcial y S7 de la guarda |
| I5 | `sintetico.py`; `test_sintetico.py` | generadores de §3 con esquemas iguales a `tipos`; paridad del HTML con el reloj |

Nadie edita archivos de otro dueño ni `tipos.py`, `test_meteo_combinada.py` o este documento: los pedidos y las preguntas
van al coordinador, que los registra aquí.

## Ola 1 cerrada (2026-10-26)

Los cinco módulos de la ola 1 quedaron implementados, cada uno por su dueño, con sus lecturas en el encabezado
(ENT-1 a ENT-6, FIJ-1 a FIJ-7, UMB-1 a UMB-8, CON-1 a CON-10, NUM-1 a NUM-9, PAR-1 a PAR-12, CEG-1 a CEG-14 y SIN-1
a SIN-16). La suite da 332 pruebas: pasan todas las que corren y quedan 177 omitidas (las «por implementar» de las
olas 2 a 6, el índice de §9 con sus pendientes, el cierre de M1 y la de huellas de datos, con su motivo). Sin
`__pycache__`. Nada se escribió fuera de `meteo_combinada/`; `reloj_dmc/` y el código fijado siguen como en AP
`4b50b0d`.

**Entregas de §6 del diseño:**
- **§4.3 en verde** (`test_umbrales.PruebasM1Umbrales`): el JSON se regenera byte a byte desde el v2.1 (`156587f1…`) y
  el Anexo A del v2.2 es idéntico (m-8); `opciones_m0` = `OPCIONES_M0` por AST (`49503a3a…`); `comparar` estricto;
  `traducir` da los 150 ids de 27 plantillas, grupo por grupo como el Anexo P; `verificar_contra_texto`,
  `completitud` y `verificar_repeticiones` dan `[]`; `cargar_umbrales` exige la huella.
- **Anexo A2:** 104 constantes (78 umbrales del cuerpo y del Anexo B, 22 definiciones y 4 de operación), 127
  repeticiones del Anexo A en el cuerpo comparadas con su id (ninguna difiere), 114 exclusiones con su motivo y 17
  máscaras. La completitud cubre los 649 números de §2-§9 y del Anexo B.
- **Detector de literales** (`test_umbrales.test_literales`): en verde sobre todos los módulos, con `TOLERADOS` vacío;
  los literales que coinciden con un valor llevan `# no-umbral: <motivo>` (4 en `ceguera`, 1 en `fijados`, 1 en
  `tipos`). Ojo: el A2 trae los enteros del 3 al 36, así que cada dueño usa `U.a`, `constantes.valor` o la marca.
- **Huellas de §9.3:** las 26 de código, textos y configuración coinciden (`fijados.comprobar_codigo_fijado` da
  `[]`), y la del intérprete también (`0b5bc40b…`). Las de datos quedan como constantes y su prueba omitida (decisión 4).
- **S10 parcial** (`test_ceguera.PruebasS10Ceguera`): registro en bloqueo con la ruta léxica antes de resolver (un
  espía confirma que /Volumes nunca se consulta), paridad con el registro del reloj, sin red y sin procesos vivos. Y
  **S7 de la guarda** (`test_ceguera.PruebasS7`). **S5 de las particiones** (`test_particiones.PruebasS5Particiones`).
- **Generadores con esquemas iguales a `tipos`** (`test_sintetico`, 25 pruebas): los cinco esquemas copiados son
  iguales en columnas, tipos y versión; el HTML es el del reloj; la cadena descargador → adaptador → `cargar_dmc`
  corre entera (DD 270 con 10 kt da u = +5,144 m/s) y `validar_regla_reloj_dmc` acepta la política sintética.

**Arreglos de integración (coordinador):**
1. `test_particiones`: se quitó el respaldo de umbrales de prueba; usa `umbrales.cargar_m0(APH)` y comprueba que la red
   de prueba supone los valores del Anexo A.
2. `test_umbrales.test_opciones_m0_por_ast` usa `fijados.opciones_m0` y exige que `umbrales.SHA_PREPARAR_M0` y
   `fijados.SHA_PREPARAR_M0` sean la misma huella (las dos constantes se mantienen: `umbrales` es de la capa 0 y no
   puede importar `fijados`).
3. `test_ceguera.py` y `test_particiones.py` salen de `EN_CURSO`.

**Cambios de interfaz respecto de §3 del diseño** (aditivos; van al anexo de firmas que se regenera al cerrar M1):
- `umbrales`: `Umbrales.sha256_texto_vigente`, `vigentes()` y `huella()`; `IDS`, `IDS_LISTA`, `seccion_anexo_a`,
  `filas_anexo_a`, `serializar` y `SHA_PREPARAR_M0`.
- `constantes`: `ConstanteTexto` suma `clase`, `repite` y `negativos`; además `NoNormativo`, `REPETICIONES`,
  `MASCARAS`, `verificar_repeticiones` y `tramo_de_seccion`.
- `entorno`: `Rutas.salidas` y `etiqueta_corrida`. `fijados`: `HUELLAS_CODIGO`, `HUELLAS_DATOS`,
  `HUELLAS_ERA5L_AGREGADAS`, `HUELLAS_RELOJ_4B50B0D`, `extraer_meteo_civil_v3`, y el argumento `micromamba_list=` de
  `comprobar_codigo_fijado`.
- `numerico`: `valor_armonico`. `ceguera`: `SalidaProhibida`, `RedProhibida`, `vocabulario_en`, `es_procedencia`,
  `es_de_reloj`, `anunciar_acceso` y el argumento `k2` de `permitido_de_reloj`.
- `sintetico`: generadores de apoyo (`reportes_desde`, `estacion_sintetica`, `etiquetas_desde_utc`, `filas_del_mes`,
  `html_catalogo`, `alterar_artefacto`, `alterar_registro`, `horas_del_mes`, `tp_acumulado`,
  `geopotencial_sintetico`, `campos_s6`, `huellas_sinca`) y argumentos de palabra clave con valor por omisión.

**Diferencias con el diseño que se anotan** (lecturas de implementación; ninguna cambia una regla):
- NUM-8: «EPSG:54009» no existe en la base de PROJ; Mollweide es `ESRI:54009`.
- SIN-9: las teselas NASADEM en disco son GeoTIFF int16 de 1/3.600° (lo dice el código del descargador), no `.hgt`.
  I8 lee ese formato.
- SIN-16: el manifiesto de la red ampliada se llama `pliegues_v2_red2.json` (`v2/pliegues_red2_v2.py`); el diseño y R21
  lo llaman «`pliegues_v2.json` de este bloque» (MC-09).
- ENT-4: M2a escribe en `LOCAL/meteo_combinada/v1/m2a/` (su etiqueta es «m2a»: M2a corre antes de que exista la de
  M3-4); M3-4 y M5 en `v1/HUMAN<AAAAMMDD>_METEO_COMB_<n>/` y M6 en `…/m6/`. §8 dice «`LOCAL/meteo_combinada/v1/<ETIQUETA>/`»
  sin fijar la etiqueta de M2a. I20 e I22 lo confirman.
- `texto_7_5.md`: la huella vigente (`58362640…`) es la de `enmienda2/texto_7_5.md`; la copia de `c0/` es la anterior.
- CEG-7: `procesos_hijos_vivos` lanza `ps` (sólo lectura). §0, regla 3, dice que sólo `orquestacion` lanza procesos; se
  lee como el reparto del cómputo. En cambio `fijados` no corre `micromamba list` (FIJ-3): recibe su texto.

**Pendientes para las olas siguientes:**
- **Ola 2:**
  - I10 e I5: fijar en `tipos` el esquema de las réplicas (`replica`, `candidato`, `S`) y las columnas de las tablas
    de `EntradasDecision`; `sintetico` usa por ahora un `ESQUEMA_REPLICAS` propio.
  - I6, I22 y el C5 de RELOJ: el formato de `registro_politica_reloj.json` (SIN-5 eligió uno con los campos de
    `tipos.RegistroReloj`).
  - Formatos de `sintetico` que leen sus dueños: NASADEM (I8), ERA5-Land y geopotencial (I7), SINCA (I11), casos de la
    regla (I10 e I14), red de S6 (I15) y series de traslados (I9).
- **Pruebas:** quien saque el adaptador o `dmc_features` de `sys.modules` debe sacarlos también de
  `reloj_dmc.fijados._CARGADOS` (FIJ, aviso de I1).
- **Ola 4:** I17 asigna clase a las carpetas que D3 no nombra. Propuesta de I4:
  - insumo: `estaticas/`, `qc/estaciones/`, `producto_01deg/` y `salud/`;
  - procedencia: `avance.jsonl`, `recibo_corrida.json`, `sha256.json`, `intentos_*.jsonl` y `pruebas_m1.txt` (corregido
    después por D13: `pruebas_m1.txt` es documento, CEG-19);
  - resumen: `decision_m6.json`.
  `ESQUEMA_ESTACIONES_MC.sin_fondo` es de `estaticas/` (insumo) y por eso no choca con la guarda.
- **Ola 5:** la fábrica de entradas de `orquestacion` calcula la huella con `open` de Python (o llama a
  `ceguera.anunciar_acceso`) antes de pasar una ruta a netCDF4, pyarrow o rasterio, que no pasan por el gancho de
  auditoría (CEG-5).
- **Ola 6:** I22 corre `micromamba list -n amb_v2` y pasa su texto a `fijados.comprobar_codigo_fijado` (FIJ-3). Falta
  dueño para la prueba de MC-02 «ningún módulo de métricas lee las rutas de insumo salvo `candidatos` y `producto`».
- **Para todos:** la regla de privacidad prohíbe la arroba fuera de los decoradores, también el operador de producto
  matricial: se usa `np.matmul`.

## Revisión independiente de la ola 1 y sus arreglos (2026-10-26)

Dos revisores que no escribieron el código contrastaron cada módulo con el texto v2.2, el diseño y D1-D10, y buscaron
refutarlo con sondas propias (como las olas 4a y 4b del reloj). Revisor A: `tipos`, `umbrales` y `constantes`.
Revisor B: `entorno`, `fijados`, `numerico`, `particiones`, `ceguera`, `sintetico` y `test_meteo_combinada`. Los dos
dijeron «se puede cerrar con cambios», sin bloqueantes. Cada dueño corrigió lo suyo; el coordinador, `tipos` y
`test_meteo_combinada`. Después se volvieron a pasar las sondas de los dos revisores: todas las evasiones quedan
detectadas.

**Comprobado y correcto según los revisores** (además de lo corregido): el JSON sale byte a byte desde el v2.1 (con
una reimplementación propia de `preparar_m0.anexo_a`) y los Anexos A y B del v2.2 son idénticos a los del v2.1; los 150
ids de las 27 plantillas dan, uno por uno, el valor del texto; ninguna constante del A2 tiene valor o signo equivocado;
los 20 esquemas de `tipos` coinciden con §2.3 del diseño y la tabla de marcas con §2.4 del texto; las 26 huellas de
código y la del intérprete coinciden; las fórmulas de `numerico` son las del texto; las particiones no tienen fugas
(prueba, grupo y amortiguador fuera, también en los internos); los formatos de `sintetico` salen del código real y sus
«esperados» siguen §6 y los Anexos A y B.

**Revisor A, qué se corrigió:**
- H1 (mayor): la lectura de números no veía «½» ni cifras pegadas a una letra. Ahora lee ½, ¼, ¾, ⅓ y ⅔ (la paridad
  con el reloj declara la diferencia); constantes nuevas `NUCLEO_MEDIO` (el −½ del núcleo, §4.2), `S_PAR_PESO` y
  `PI_AMBIENTAL`; repetición de «3L» con `NUC_CORTE`; CON-11 declara a mano lo que la regla no lee (3L, 2πh, 19S,
  Q95, R2023A, «una vez más», «en un año»…) y la completitud exige que cada uno esté declarado.
- H2 (mayor): el detector de literales no veía 0,95 de un `*_PCT` ni 6,5 o 39 de un umbral negativo. Ahora suma v/100
  de los `*_PCT` y |v| de los negativos, y exige revisar los 26 módulos (todos menos los 3 excluidos).
- H3 (mayor): el A2 rige en todo el cuerpo (§0 a §10 y el Anexo B), no sólo en §2-§9: `ERRATA_MUESTRA` = (20, 20) de §10
  y las repeticiones de `SEMILLA` (§10) y `SOPORTE_PCT` (§0.4.4).
- H4: «+» sólo en `QQFE_ALTO` y «−» obligatorio en los seis ids negativos; listas con su separador y su largo.
- H5: `U.frac("SECO_HR_PCT")` se rechaza (está en unidades de HR); `K1_RAIZ_DE` (√2) y `C_PERIODOS` como (orden,
  período); UMB-11 documenta que `QFF_MIN/MAX` son la rapidez y `QQFF_*` la presión QFF (ids del Anexo P).
- H8 y H9: pasan al A2 la resolución y el producto de GHS-POP, las 343 comunas de los nudos, la definición de Δ_c, el
  «/2» de T̄ y los Q95 de la rapidez y del acierto de días (§5.8).
- H10: la máscara «referencia» ya no se traga números con unidad, y la completitud lo vigila; la ventana {m−1, m, m+1}
  es una repetición de `A_VENTANA_MESES`. H11: `anexo_a2.json` guarda ajenos, negativos y lo no leído. H12: la marca
  `# no-umbral` sólo vale en un comentario.
- H6 y H7 (`tipos`, coordinador): ver más abajo, TIP-8 y TIP-9. H13: el Anexo P del diseño dice que `HR_SAT` aparece
  «dos veces» en «Rachas»; son tres (UMB-1). El diseño no se toca: queda anotado aquí.
- Cifras al cierre: 119 constantes en el A2 (88 umbrales, 26 definiciones y 5 de operación), 133 repeticiones del
  Anexo A, 142 exclusiones y 18 máscaras; los 753 números del cuerpo y del Anexo B quedan cubiertos; `TOLERADOS` vacío.

**Revisor B, qué se corrigió:**
- `ceguera` (H1 a H9):
  - H1: en métrica y resumen se revisa todo texto (valores, celdas, atributos, metadatos, CSV y consola) como texto
    libre, y la privacidad en todos.
  - H2: una ruta por alias ya no vale como procedencia dentro de una métrica, salvo bajo una clave «huellas…» con
    {ruta: sha256} o {ruta: {sha256, bytes}}.
  - H3: la exención `dmc_R_*` se limita a los cinco nombres de `tipos.COLUMNAS_R_D` y, en métrica y resumen, sólo como
    lista de nombres de columnas (§0.4.3: «no se resume ni se informa»).
  - H4: la procedencia tiene un esquema cerrado (rutas, huellas, fechas, versiones y sólo enteros de una lista de
    claves: bytes, filas, procesos…), sin decimales. La lectura anterior pasa a la pregunta P2.
  - H5: se leen los metadatos del parquet, los atributos y los grupos NetCDF. H6: se rechazan también los nombres del
    fondo y del residuo (T_F, p_F, amp_TF, fe_*, E5L, r_T, rt_T, rbar…) y las mayúsculas intercaladas: más estricto que
    S7, no cambia ninguna regla (CEG-10).
  - H7 (mayor): el registro se evadía con «enlace/..» (el sistema sigue el enlace antes del «..»). Ahora recorre la ruta
    sin normalizar y aplica cada «..» sobre la ruta física. **Aviso para el reloj:** el `RegistroAccesos` de
    `reloj_dmc/verificar_reloj_dmc.py` tiene el mismo defecto; no se tocó (es código del reloj) y
    `test_ceguera.test_s10_paridad_con_el_reloj` lo documenta.
  - H8: vigiladas y permitidas se recorren sin `realpath`: un enlace hacia /Volumes no hace consultar /Volumes.
  - H9: `procesos_hijos_vivos(grupos=…)` cuenta también los procesos de los grupos vigilados (un nieto huérfano sólo se
    ve así): `orquestacion` debe lanzar sus trabajadores en un grupo propio.
- `entorno` y `fijados`:
  - H8: `entorno` define sus propias `prohibido_volumes` y `prohibido_repositorios` (mismo nombre y firma) que siguen
    los enlaces paso a paso y se detienen antes de consultar /Volumes; `escribir_atomico` las aplica y llama a la del
    reloj. Es una diferencia con §9.1 del diseño (ENT-7); la del reloj no se tocó.
  - H13: `rutas_sinteticas` sólo acepta una raíz bajo `tempfile.gettempdir()` (también rechaza la carpeta temporal de
    la sesión: hay que usar `tempfile.TemporaryDirectory`).
  - H17: la clausura del reloj suma `reloj_dmc/__init__.py` (siete archivos, `ARCHIVOS_RELOJ`; `MODULOS_RELOJ` sigue con
    los seis de MC-17); `cargar_validador_reloj` falla si `politica`, `tipos`, `constantes` o `tablas` del reloj ya
    estaban cargados (las pruebas pasan `permitir_cargados=True`).
  - H18: `macrozona_codigo` copia `MACROZONA_CODIGO` de `_comun_modelo` por AST, con pruebas de «sin_region».
    H22: la etiqueta de corrida exige una fecha que exista.
- `numerico` y `particiones` (H19 a H21): el origen de la rejilla sale de `constantes.valor("P2_ORIGEN_M")`; una sola
  fuente del grupo en P1, P2, internos y remuestreo (falla si `InfoEstacion.grupo` difiere de `grupos`);
  `hueco_circular_max` rechaza horas no enteras; `armonico_recortado` lanza `DisenoDeficiente` sin rango completo
  (pregunta P9); qué columnas no penaliza el ridge lo fija I13 en el addendum (§4.6 calla; NUM-9).
- `sintetico` (H10 a H16):
  - H10 (mayor): la red de S6 cada 3 h no habría dado TF2 evaluable (MC-47) y S6 habría fallado: ahora es horaria, se
    genera por meses, y una prueba exige ≥ 10 estaciones en la red constante (hay 20).
  - H11 (mayor): MZ cuenta estaciones, no evaluaciones (TIP-10); casos nuevos de MZ no aplicable y no publicable.
  - H12 (mayor): los casos aíslan cada condición: `tablas_metricas` pasa a 21 casos y `tablas_m6` a 17 (una condición
    fallida por caso, los bordes de la 7 con el NMB en puntos porcentuales, LRO sí y BLQ-75 no); la prueba recalcula
    por su cuenta las compuertas y las 7 condiciones.
  - H13: sólo escribe bajo la carpeta temporal del sistema. H14: el registro de C5 trae rutas, huellas y commit; las
    banderas son de la política. H15: la huella de los pliegues de la red 2 como en v2 (`CLAVES_HUELLA`, esquema y
    bloque). H16: τ = 48 h es un parámetro (pregunta P5).
- `test_meteo_combinada` (H23, coordinador): la prueba de escritura ve también `Path.open("w")`, `os.open` con banderas,
  `Path.rename/replace`, `ZipFile(…, "w")`, `savetxt`, `to_feather`/`to_pickle`/`to_hdf`, las carpetas temporales y un
  modo en una variable (con su propia prueba del detector y la marca `# no-escribe: <motivo>`); la importación del
  esqueleto vigila además `os.stat`, `os.lstat` y `os.access`; el grafo ve `import_module` y `__import__` con texto fijo
  y los nombres con punto («from v3 import preflight_v3»). `fijados` puede importar `reloj_dmc.politica`, sólo después de
  comprobar las huellas.

**Cambios del coordinador en `tipos`** (TIP-8 a TIP-10):
- TIP-8 (D9): `MACROZONA_SIN_REGION = "sin_region"` y `macrozona_o_ninguna(nombre)`; `macrozona_cod` sigue
  `_comun_modelo.MACROZONA_CODIGO`, que `fijados.macrozona_codigo` copia por AST.
- TIP-9: la tabla ancha guarda `marcas_FF` y `marcas_DD` por separado (el diseño traía `marcas_viento`). Así sirve a
  cualquier respuesta de la pregunta P1.
- TIP-10: `ESQUEMA_VALIDACION_PUB` lleva `n_estaciones` (MZ exige «≥ 10 estaciones evaluables», §6.1).
- `ESQUEMA_REPLICAS` (réplica, candidato, S), que `sintetico` ya usaba.

**Cifras al cierre de la ola 1:** la suite da 359 pruebas: 182 en verde, 177 omitidas y ninguna falla. Las omitidas son
las 174 «por implementar» de las olas 2 a 6, la de huellas de datos (decisión 4), la del cierre de M1 y el índice de §9
con sus pendientes. Sin `__pycache__`. Por archivo de la ola 1: `test_entorno` 19, `test_fijados` 19 (más la omitida),
`test_umbrales` 16, `test_constantes` 16, `test_numerico` 14, `test_particiones` 11, `test_ceguera` 20 y
`test_sintetico` 29; del coordinador, `test_tipos` 20 y `test_meteo_combinada` 18 (más cuatro omitidas: S10 de la
batería, el cierre de M1 y el índice).

## Preguntas para el autor (2026-10-26)

Ninguna se decidió en el código: donde hacía falta algo, el código sigue la propuesta o la lectura más estricta y lo
deja dicho en su lectura. Ninguna bloquea la ola 2; las marcadas «antes de M3-4» cambian resultados de M3-4.

- **P1. Q1 de las marcas distintas de la 3 (§2.7), antes de M3-4.** Cita: «Q1, por regla y variable. Una marca
  invalidante de §2.4 (bits 3-17) quita más del 10 % de las horas de la red en una variable»; EMC1-1 fija «Se cuenta
  por variable de la fuente (Ts, Td, `relative_humidity`, `wind_speed_instant`, `wind_direction_instant`, QFE y QFF)»
  sólo para la marca 3. Problema: para las demás marcas el texto no dice si FF y DD cuentan por separado o como par, y
  eso decide si una alarma detiene M3-4. Propuesta: por variable de la fuente para todas, como la 3; las marcas que
  invalidan «el viento» (11 y 12) cuentan en las dos, y un pico de la rapidez sólo en FF. (`tipos` ya guarda las marcas
  de FF y DD por separado, TIP-9.) Hallazgo P1 del revisor A.
- **P2. «Procedencia, sólo rutas y sha256» (D3).** Problema: un recibo o un `avance.jsonl` necesita enteros (bytes,
  filas, procesos). Hoy rige la lectura estricta: sólo enteros de una lista cerrada de claves y ningún decimal.
  Propuesta: confirmarla. Alternativa: ningún número. (Revisor B, P1; antes, CEG-11 de I4 admitía cualquier número no
  asociado al vocabulario.)
- **P3. Salidas documentales.** El addendum de M1 (`.md` y `.json`), `anexo_a2.json`, `pruebas_m1.txt` (la salida de
  unittest, con duraciones decimales), el informe y la consola citan el texto, que usa «fondo», «ERA5-Land»,
  «corrección» y «sin DMC». Con la guarda de S7 por clases (D3) se rechazarían en métrica, resumen y procedencia.
  Propuesta: una quinta clase «documento»: fragmentos del texto y lecturas, con la huella del texto, sin números de
  datos. Sus escritores son de la ola 6. (Revisor B, P2.)
- **P4. Clases de las salidas que D3 no nombra.** Propuesta: insumo: `estaticas/`, `qc/estaciones/`, `producto_01deg/`,
  `salud/`, `producto/clima_a.parquet` y `producto/tramos_homogeneos.parquet` (r̄ y δ son el sesgo estable del fondo en
  cada estación: resumidos serían una métrica del fondo, §0.4.2; los exige §8, «Datos nuevos»); procedencia:
  `avance.jsonl`, `recibo_corrida.json`, `sha256.json` e `intentos_*.jsonl`; resumen: `decision_m6.json`. (I4 y revisor B.)
- **P5. Parámetros de la red sintética de S6, antes de correr S6.** Cita: §5.7, «Compuerta de deriva (sintética, de
  M1). En la prueba S6, con una deriva del fondo de 0,3 K por década y estaciones que aparecen en 2010, B y AB deben
  cumplir las cotas de TF2. El que no las cumple queda fuera de E0 en todos los usos»; EMC1-2: la red de S6 «debe dar TF2
  evaluable (si no, S6 falla)». Problema: el texto, MC-07 y MC-50 fijan las estaciones (20 desde 2000 y 120 desde 2010),
  el sesgo de −1,5 K en los valles, la correlación de 100 km y σ = 1,5 K; no fijan la frecuencia (con paso de 3 h TF2 no
  es evaluable), la geometría de los valles (hoy −71,0 ≤ lon ≤ −70,6), la correlación temporal de las anomalías (τ =
  48 h), las comunas (25 con 4 celdas) ni la posición de las estaciones, y de ellos depende que B y AB entren a E0.
  Propuesta: fijarlos en el addendum de M1 antes de correr S6, como MC-49 para S4: horaria, τ = 48 h y los demás
  valores de `sintetico.red_s6` (SIN-12). (I5 y revisor B, P4 y H16.)
- **P6. La macrozona «insular» (§2.7, §3 y D9), antes de M3-4.** `_comun_modelo.MACROZONA_CODIGO` trae «insular» (6),
  la de las celdas fuera del dominio ACAG (Rapa Nui, Sala y Gómez), que ninguna región da. Ni el texto ni D9 dicen si
  cuenta como macrozona en Q1z, Q2 y los estratos; con pocas estaciones, una sola puede disparar la alarma de su
  macrozona y detener M3-4. Propuesta: tratarla como D9 (sólo en lo nacional, informada aparte); hoy
  `tipos.macrozona_o_ninguna` sólo vuelve None «sin_region». (I1.)
- **P7. ¿Une grupos una estación excluida? (§2.5).** Cita: «Las estaciones a ≤ 2 km (componentes conexas) forman un
  grupo»; con K3 fallida «la estación queda fuera». Problema: no dice si una excluida puede unir dos grupos en la
  cadena; cambia el reparto en pliegues. Propuesta: no puede (PAR-1, implementado). (I3 y revisor B, P6.)
- **P8. El amortiguador de P2 frente al grupo (§5.1 y §2.5).** Cita: «Se excluyen del entrenamiento las estaciones a
  ≤ 25 km de cualquier estación de prueba»; §2.5, las del mismo sitio «Se validan juntas». Problema: con la lectura
  literal, el compañero de grupo de una estación del amortiguador sigue entrenando si está a más de 25 km. Propuesta:
  la literal, estación por estación (PAR-6, implementada; el revisor B la da por correcta). Alternativa: sacar el grupo
  entero. Sólo para confirmar. (I3.)
- **P9. El segundo ajuste de A sin rango completo (§4.3).** Cita: «se quita el 10 % de cada cola de los residuos del
  ajuste y se ajusta una vez más». Problema: con los requisitos de §4.3 el primer ajuste siempre tiene rango completo,
  pero tras el recorte pueden quedar menos horas distintas que coeficientes, y el texto no dice qué hacer; cambia A.
  Propuesta: la estación no entra en A ese mes, como si no cumpliera los requisitos. Alternativa: usar el primer
  ajuste. Hoy `numerico.armonico_recortado` lanza `DisenoDeficiente` y decide quien llama (I13). (I3.)

## Pendientes para la ola 2 y siguientes (2026-10-26)

Además de los de «Ola 1 cerrada»:
- **I6 (`politicas`):** una prueba que exija que la regla `quality` de QFF use `QQFF_*` y no `QFF_*` (la rapidez);
  `registro_politica_reloj.json` con rutas, huellas y commit (las banderas, de la política; SIN-5), por acordar con el C5
  de RELOJ.
- **I10 (`decision`):** el NMB de `tablas_m6` va en puntos porcentuales, como `v2/decision_v2.py` (SIN-17); con la
  regla crónica y E1 vacío, decidir si la nota «regla sin ganador» también va (el texto calla y sólo cambia
  `decision.json`; revisor B, P5).
- **I13 (`candidatos`):** fijar en el addendum qué columnas no penaliza el ridge de C (NUM-9) y qué hace con
  `DisenoDeficiente` (P9).
- **I15 (`tendencias`):** la red de S6 ya no trae las anomalías: se piden por años con `sintetico.campos_s6`.
- **I20 (`orquestacion`):** los trabajadores en un grupo de procesos propio, que se pasa a
  `ceguera.procesos_hijos_vivos(grupos=…)`; la huella de cada entrada con `open` de Python (CEG-5).
- **I22:** `micromamba list -n amb_v2` para `fijados.comprobar_codigo_fijado` (FIJ-3); la clase de `pruebas_m1.txt` y
  del addendum depende de P3.

## Respuestas a P1-P9 (2026-10-26, por delegación del autor)

Decididas con su propuesta y marcadas [delegada], en `APH/auditoria/20261023/meteo_combinada/m1/decisiones_autor_m1_20261026.md`:
- **P1 → D11:** por variable de la fuente para todas; 11 y 12 en FF y DD; el pico de la rapidez, sólo en FF.
- **P2 → D12:** la lectura estricta.
- **P3 → D13:** la clase «documento».
- **P4 → D14:** las clases propuestas.
- **P5 → D15:** los parámetros de S6 al addendum antes de correr S6.
- **P6 → D16:** «insular» como D9; `tipos.macrozona_o_ninguna` devuelve None también para ella.
- **P7 → D17:** no une.
- **P8 → D18:** la literal.
- **P9 → D19:** la estación no entra en A ese mes.

Lo que cambia código (D11, D13, D16 y D19) se implementa en la ola 2 o en la del módulo dueño.

## Ola 2: encargos (2026-10-26)

### Cambios del coordinador antes de la ola

En `tipos.py` (TIP-9, TIP-11 y TIP-12) y en `test_meteo_combinada.py`. Son lecturas de implementación: ninguna cambia una
regla. La suite sigue en verde (cifras al final de esta sección).
- **D16 → TIP-11.** `macrozona_o_ninguna` vuelve None también con «insular» (`MACROZONA_INSULAR`, `MACROZONAS_NINGUNA`).
  Además, `macrozona_de_celda(macrozona, cod_comuna)`: la macrozona de una estación o celda sale de su celda de
  `celdas.parquet`, de la columna `macrozona` y de `cod_comuna`, y es None sin celda, con `cod_comuna` ≤ 0 o con
  «sin_region» o «insular». **Por qué hace falta:** en el código de `construir_grilla.construir_celdas` (sólo se leyó el
  código, ningún dato):
  - las cuatro islas (`aoi_id` rapa_nui, sala_y_gomez, juan_fernandez y desventuradas) llevan `macrozona` «insular»,
    aunque su región es la 5: por `cod_comuna // 1000` y `MACROZONA_REGION`, Juan Fernández y las Desventuradas
    contarían en «centro»;
  - las celdas con `cod_comuna` −1 o 0 heredan la región de la celda válida más cercana a ≤ 30 km: por la columna
    `macrozona` sola, una celda con `cod_comuna = 0` contaría en la macrozona vecina, contra D9.

  Ninguno de los dos caminos, solo, cumple D9 y D16; `macrozona_de_celda` los junta. El −1 queda como pregunta (P10).
- **D11: nada nuevo en `tipos`.** TIP-9 ya guarda `marcas_FF` y `marcas_DD` por separado, e `INVALIDANTES` ya pone las
  marcas 11 y 12 en FF y en DD. El pico (6) es de alcance «la variable»: va en la variable en que se detecta, así que el
  de la rapidez va sólo en FF. El conteo es de I12 (ola 3; ver «Pendientes»). La racha del viento queda como pregunta
  (P11).
- **D19: nada en `tipos`.** `ESQUEMA_CLIMA_A.califica` ya expresa «la estación no entra en A ese mes». Lo aplica I13
  (ola 3; ver «Pendientes»).
- **TIP-12 (pendiente «I10 e I5» de la ola 1).** `EntradasDecision` pasa a `(uso, grupo, validacion, tf, replicas,
  motivos_e0)`: son las tablas que ya fabrica `sintetico.tablas_metricas` (`validacion`, `tf`, `replicas` y
  `e0_excluidos`). Se quitan `candidatos`, `compuertas` y `red_tf2`, que nadie usaba: `decision` los calcula (acuerdo
  A11). `DecisionGrupo` no cambia.
- **Grafo:** `politicas` depende además de `numerico`. La regla `quality` de QFE va de p_std(z_s) − 80 a
  p_std(z_s) + 50 (§2.3), y p_std vive en `numerico`. Es una diferencia con la tabla de §1 del diseño (`numerico` es de
  la capa 1, así que el grafo sigue sin ciclos). `test_meteo_combinada.DEPENDENCIAS` ya la tiene.
- `test_tipos` suma tres pruebas. La primera revisa «insular» y «sin_region». La segunda compara las dos con
  `MACROZONA_CODIGO` de `_comun_modelo`, leído por AST con su huella. La tercera revisa `macrozona_de_celda` y arma
  `EntradasDecision` con un caso real de `tablas_metricas`.

### Reparto

| Dueño | Módulos y pruebas | Entrega |
|---|---|---|
| I6 | `politicas.py`; `test_politicas.py` | `PruebasS2` y `PruebasPoliticas` (S2, la parte de las políticas). Las reglas de §2.2 y §2.3 se escriben, se releen del JSON y pasan `cargar_dmc`. Fuera de los tramos de RELOJ, nada es usable. G-HR, G-viento y «posible media horaria» inhabilitan lo suyo. Una regla que rechaza `validar_regla_reloj_dmc` deja la estación sin regla. −240 sin veredicto se rechaza. También: el registro de C5 (`post_hoc`, errata y huellas), K2 por código (MC-19), los textos `source`, los tramos (años G, sin meses sin artefacto), la política efectiva (MC-53, acuerdo A5) y `a_json` con ida y vuelta exacta. Además, los pendientes de I6: QFF con `QQFF_*` (UMB-11), QFE con `QQFE_*` sobre p_std(z_s) y `registro_politica_reloj.json` (SIN-5, por acordar con el C5 de RELOJ) |
| I7 | `fondo_era5l.py`; `test_fondo_era5l.py` | S5, la parte del fondo: fondo exacto con campos lineales, estaciones arriba y abajo del píxel y QFE con p_std(z_s). S11. S12, la parte del fondo: residuo 0 con −240 y −180; una hora que no es HH:00 se rechaza. S13: t2m en °C y sp en hPa abortan; tp pasa de m a mm; el primer incremento del mes; RR06 que cruza un mes; el geopotencial corrido no se alinea. La detención de M2a es de I20. También: vecino a ≤ 16 km y renormalización (MC-39, MC-60), píxeles válidos de tres meses, y las funciones nuevas de los acuerdos A2 y A9 |
| I8 | `estaticas_nasadem.py`; `test_estaticas_nasadem.py` | S3: K1 (MC-59); K3 con el DEM con máscara; sin z_cat; bordes oeste y sur; pendiente con cos φ en −20° y −50°. Altitud poblada y media sin población. TPI truncado. `info_estaciones` con el esquema y la macrozona de TIP-11 (A8). `nasadem_en_pixeles` (A9). Las teselas son GeoTIFF int16 (SIN-9) |
| I9 | `homogeneidad.py`; `test_homogeneidad.py` | S4: traslados de 15 y de 5 m, barómetro de 1,5 hPa, reducción estándar → real y horario diurno → 24 h, en 500, 1.000 y 2.500 m, con `sintetico.series_traslado`, y ≤ 2 % de falsos quiebres en 200 series estacionarias, con el ruido de MC-49 (SIN-13). H*(k) en dos pasos (MC-06). Segmentación binaria hasta 3 quiebres. δ = 0 sin quiebres. La parte de S5 del cambio de sensor de 1 K (un tramo). Interfaz en A4 |
| I10 | `decision.py`; `test_decision.py` | S7, la regla: cada compuerta; E1 vacío; la regla crónica y el caso mixto; TF2 no evaluable con D4; empates exactos y determinismo. S16, las ramas: tres ramas, simetría, desempate en I, regla de O3, variante por contaminante y ganador restringido. Con `sintetico.tablas_metricas` y `tablas_m6`. También `decision.json`. El NMB va en puntos porcentuales (SIN-17). Interfaz en A11 |
| I11 | `sinca_meteo.py`; `test_sinca_meteo.py` | MC-10: los dos manifiestos con sus huellas; una serie por estación y variable; el reloj (UTC−4 o la hora civil); el control mínimo por rangos; sólo TEMP, RHUM, WSPD y WDIR. Devuelve `ESQUEMA_SINCA_HORA` (A12). Sólo con `sintetico.sinca_sintetico` |
| I4 (encargo corto) | `ceguera.py`; `test_ceguera.py` | D13: una quinta clase de salida, «documento». Lleva fragmentos del texto y lecturas, con la huella del texto y sin números de datos; sus escritores son de la ola 6. D12 ya rige (lectura estricta, CEG-11): basta citarlo en la lectura |
| I5 (a pedido) | `sintetico.py`; `test_sintetico.py` | Los formatos que pidan I7, I8, I9, I10 e I11, por medio del coordinador. Lo de D16 está en «Pendientes» |

Reglas de la ola (las de §0 del diseño y las de la ola 1):
- **Edición.** Nadie edita archivos de otro dueño, ni `tipos.py`, `test_meteo_combinada.py` o este documento. Los
  pedidos y las preguntas van al coordinador.
- **Entorno.** Intérprete fijado, con `-B` y los hilos en 1. Se corre desde `scripts_modelo_1km`. Sin `__pycache__`.
- **Ceguera.** Sólo datos de `sintetico` en `tempfile.TemporaryDirectory`. No se abre DMC, la meteorología SINCA real,
  NASADEM real, ERA5L real, GHS-POP real ni las salidas del reloj. Una prueba que exija datos reales se omite con su motivo
  y no se da por aprobada.
- **Umbrales.** Los del Anexo A se piden con `U.a`/`U.frac`; los fijos, con `constantes.valor`. El detector de literales
  sigue en verde.
- **Lecturas.** Cada módulo lleva las suyas en el encabezado: POL-n, FON-n, NAS-n, HOM-n, DEC-n y SNC-n.
- **Lo que no se decide.** Donde el texto calla o se contradice en algo que cambia resultados, no se decide en el código:
  se pregunta con cita y propuesta, y mientras tanto rige la lectura más estricta.

Al cerrar la ola, el coordinador saca de `EN_CURSO` los archivos cuyas pruebas «sNN» ya corren y pide la revisión
independiente.

**Entregas verificables de la ola** (§6 del diseño): S2 (parte), S3, S4, S5 (fondo), S11, S12 (fondo), S13 (salvo la
detención de M2a), S7 (regla) y S16 (ramas).

### Acuerdos de interfaces

- **A1. El fondo en las estaciones (I7 → I9, I12, I13 e I20).** Es `ESQUEMA_PUNTOS_E5L`.
  - Una fila por cada hora UTC del período de la pasada, no sólo por las horas con reporte; `h` va creciente y sin
    repetir.
  - Unidades: T_F y Td_F en °C, p_F en hPa, u_F y v_F en m/s, amp_TF en K. El viento va en la convención «hacia» de
    ERA5-Land, la misma de `wind_u` y `wind_v` del adaptador (S11).
  - NaN donde no hay fondo.
  - Se guarda en float32, y todo consumidor usa esos float32 y calcula en float64. En memoria también se redondea a
    float32 antes de usarlo. Así la corrida que lee del disco y la que trae el fondo en memoria dan lo mismo, bit a bit
    (S9).
- **A2. `fondo_era5l.en_horas(F_estacion, h) -> dict[str, np.ndarray]` (nueva, I7).** Da las columnas del fondo en las
  horas `h` (int32), en float64, con NaN donde la tabla no tiene esa hora. Es la única forma de alinear la tabla ancha
  (sólo horas con reporte) con el fondo, que tiene todas las horas.
- **A3. `fondo_era5l.residuos(obs, F) -> dict` (I7 → I12, I13 e I20).**
  - `obs` trae «T» (Ts, °C), «Td» (`td_final`, °C), «u» y «v» (`u_final` y `v_final`, m/s) y «QFE» (hPa).
  - `F` trae las columnas de A1. Los arreglos de `obs` y `F` van alineados.
  - Devuelve, en float64, r_T, r_Td, r_u y r_v (obs − F) y r_p = ln(QFE/p_F), con NaN donde falta la observación o el
    fondo.
  - No mira la validez: quien llama pone NaN donde la hora no es válida (en el producto, con los `valido_*` de la tabla
    ancha).
  - Es la única fuente de r_p. La diferencia en hPa, QFE − p_F, que usan las marcas 13 y 14 (§2.4) y T2b (§2.5), no es
    r_p. El texto la define aparte; cada consumidor la calcula con el p_F de A2.
- **A4. K4 y los tramos homogéneos (I9 → I12, I6, I13 e I20).**
  - **Firma.** `homogeneidad.k4(tabla_estacion, p_F, z_cat, umbrales) -> tipos.ResultadoK4`.
  - **Entrada.** `tabla_estacion` es un DataFrame con `h` (int32, creciente y sin repetir) y con `Ts` (°C), `QFE` y
    `QFF` (hPa), con los nombres de `ESQUEMA_QC_ESTACION`. Trae NaN donde el valor no es válido tras el paso 2 de §2.1, el
    envoltorio sin la marca 14. Los NaN los pone qc (I12); `homogeneidad` no lee marcas, y las columnas de más se
    ignoran. `p_F` va en float64, alineado con las filas (A2), en hPa. `z_cat` es un float en m, NaN si no es legible.
  - **Meses.** Es el `mes2000` de la hora UTC («medianas por mes y hora UTC», §2.5): (año − 2000)·12 + mes − 1 del instante
    UTC. Con numpy: `(np.datetime64("2000-01-01T00", "h") + h).astype("datetime64[M]").astype(np.int64) - 360`.
  - **Salida.** `Quiebre.mes` es k, el primer mes del tramo nuevo. `D` va en m (T2a) o en hPa (T2b). `clase` va en los
    quiebres de T2b (traslado o barómetro) y en los de T2a sin T2b (método de reducción). `ultimo_traslado` y
    `ultimo_barometro` son ese k: la marca 1 (en todas las variables) y la 16 (en QFE y QFF) van en las horas con
    mes2000(h) < k. `sin_prueba` quiere decir sin QFE válida (marca 21).
  - **En memoria.** `ResultadoK4` no se escribe tal cual: D es un estadístico de la presión frente al fondo (T2b). De K4
    sólo salen meses y clases (los conteos de `resumen_qc`), nunca D (§0.4.6).
  - **Tramos homogéneos (§4.8).** Usan el mismo detector. `tramos_homogeneos(h, residuo, variable, umbrales)` da
    [(desde_mes, hasta_mes)] en mes2000, inclusivos y en orden; g = 0, 1… en ese orden. `desplazamientos` da {g: δ} en K,
    con δ = 0 sin quiebres. Eso es `ESQUEMA_TRAMOS_HOMOGENEOS`. r̃ = r − δ(g(h)) lo arma quien llama.
- **A5. La política efectiva (I6, con I9 e I12; MC-53).**
  - `politicas_efectivas(politicas_lectura, resultados_k4)` recibe `resultados_k4` como {código: ResultadoK4}.
  - Parte cada tramo en todos los quiebres de `quiebres` (§2.5: «partidos por los quiebres de K4»). El corte del mes k
    cae en la etiqueta ingenua que corresponde, con la regla `clock` del tramo, a la primera hora UTC del mes k.
  - Marca `coordinates.verified = false` en los tramos anteriores al último traslado.
  - La prueba de MC-53 la hace I6 en esta ola, con un `ResultadoK4` armado a mano y `cargar_dmc` real: las filas con
    `coordinates_verified` deben ser las de mes2000(h) ≥ k. La comparación con `qc_dmc_meteo.aplicar_k4` la suma I12 en
    la ola 3.
- **A6. Las políticas y los artefactos (I6 → I12).**
  - **Forma.** `politicas_de_lectura` da los dicts en la forma de §2.5, con las claves `station_code`, `valid_from`,
    `valid_to`, `clock`, `coordinates`, `measurements` y `quality` y números de Python.
  - **Orden.** Van en el mismo orden que los `TramoPolitica` de `tramos_de_lectura`, con los mismos `valid_from` y
    `valid_to`.
  - **Filtro.** `politicas_que_cruzan` filtra por el mes de la etiqueta del artefacto.
  - **Tramo.** El `tramo` de la tabla ancha es el id del `TramoPolitica` cuyo intervalo de etiquetas, inclusivo,
    contiene `timestamp_source`. Es la regla que usa `cargar_dmc` para elegir la política.
- **A7. Las estaciones en las políticas (I8 → I6).**
  - **QFE.** La regla `quality` de QFE va de p_std(z_s) + `QQFE_BAJO` a p_std(z_s) + `QQFE_ALTO`, con `numerico.p_std` y
    la z_s de `InfoEstacion`, en float de Python. Con `z_s_fuente` = «nasadem», sin z_cat legible, QFE queda sin regla
    (§2.5, MC-11).
  - **Coordenadas.** `coordinates.verified` es false en todo el registro con K3 fallida o en la lista K2. Las estaciones
    que K3 excluye reciben igual sus políticas, con las coordenadas sin confirmar: pasan por el paso 1 para contarlas en
    Q2 (§2.7). `latitude` y `longitude` son las del catálogo, leídas como en RELOJ §3.3.
- **A8. `InfoEstacion` se arma por etapas (I8 e I7; la completa orquestacion, I20).**
  - **Lo que llena I8.** `estaticas_nasadem.info_estaciones` llena la identidad, los textos y su lectura, K1, K3, z_s y su
    fuente, la celda, `utm_e` y `utm_n` (`numerico.utm19s`), `excluida` y `motivo`.
  - **Macrozona.** Es `tipos.macrozona_de_celda` de su celda (TIP-11), no `cod_comuna // 1000` con `macrozona_region`.
  - **Celda.** Se busca en la tabla por coordenadas, con los bordes oeste y sur cerrados. Nunca se deduce de un id: los
    ids sintéticos son propios (SIN-11) y las celdas generadas de las islas tienen ids aparte en `construir_grilla`.
  - **Lo que queda pendiente.** I8 deja `grupo` = `tipos.id_grupo([código])` (PAR-1) y `bloque` = «».
  - **Grupo y bloque.** Los completa orquestacion con `particiones.grupos_mismo_sitio` y `particiones.bloque`.
    `estaticas_nasadem` no puede importar `particiones` (las dos son de la capa 2), y PAR-12 los exige completos antes de
    armar los pliegues.
  - **Operador del fondo.** `pix0`…`pix3`, `w0`…`w3`, `respaldo_16km` y `sin_fondo` salen de `fondo_era5l.operador`, con
    los píxeles válidos y z_E5L (M2a, paso 5). Hasta entonces valen −1, NaN, False y True. Una estación sin fondo (islas,
    Antártica) queda `excluida` con motivo «sin_fondo» (PAR-1), pero cuenta en el control de calidad, sólo en lo nacional
    (D9, D16).
  - **Escritura.** `estaticas/estaciones.parquet` se escribe una sola vez, completo (M2a, paso 6).
- **A9. z_E5L y NASADEM (I8 → I7).** `fondo_era5l` no puede importar `estaticas_nasadem`, porque las dos son de la capa 2.
  - **Función nueva.** `estaticas_nasadem.nasadem_en_pixeles(catalogo, teselas) -> DataFrame` da `pixel_id`, `z_nasadem`
    y `frac_nasadem` en float64. `z_nasadem` es la media NASADEM de la huella del píxel (`cell_west`…`cell_north` del
    catálogo, con la regla de bordes de §3); `frac_nasadem`, la fracción con dato.
  - **Uso.** `fondo_era5l.z_e5l` recibe esa tabla en lugar de `teselas` y aplica el 95 % (`ZE5L_NASADEM_PCT`).
  - **Lectura.** Las teselas las lee sólo I8.
- **A10. Los puntos del operador (I7, con I8, I16 e I18).** `operador(lat, lon, z, …)` recibe z en m:
  - en las estaciones, z_s;
  - en las celdas, `z_media` (uso ambiental) o `z_poblada` (salud), de `ESQUEMA_ESTATICAS_CELDA`;
  - en los píxeles, z_E5L.

  Un solo radio, de 16 km (`VECINO_KM`).
- **A11. La decisión (I10, con I14 e I15; TIP-12).**
  - **Entrada.** `EntradasDecision(uso, grupo, validacion, tf, replicas, motivos_e0)`, con las tablas de
    `sintetico.tablas_metricas`.
  - **Lo que calcula `decision`.** E0 (desde `motivos_e0`); las compuertas, con los mínimos sobre E0; el S del grupo
    (S_par en (T, Td) con los mínimos sobre E0, salvo en lo crónico; §5.3); y la red de TF2 (`regla_red` de `tf`).
  - **Ola 3.** `validacion.puntaje_par` (I14) arma con la misma fórmula el S del grupo de cada réplica, y una prueba de
    I14 compara las dos.
  - **`compuertas`.** `compuertas(uso, grupo, tabla, umbrales)` recibe la `EntradasDecision` en `tabla`. Si su salida
    cruza a otro módulo, I10 pide su esquema al coordinador.
  - **Nota «regla sin ganador».** Cuando E1 está vacío y rige la regla crónica, el texto calla si va esta nota (revisor B,
    P5). Sólo cambia `decision.json`, no el ganador, así que I10 la fija como lectura DEC-n.
- **A12. SINCA (I11 → I14).** Es `ESQUEMA_SINCA_HORA`.
  - **Columnas.** `h` es la hora UTC u del fin del intervalo [u − 1, u] (MC-10, punto 2). `valor` va en °C, %, m/s y
    grados. `valido` se fija tras el control mínimo, y `serie` es la ruta relativa elegida.
  - **Veredictos.** Los veredictos «hora civil» de `reloj_sinca_v2.py` (MC-10, punto 1) llegan por un argumento con su
    huella, que I11 propone al coordinador.

### Pendientes de D11-D19 para las olas siguientes

- **I12 (`qc_dmc_meteo`, ola 3).**
  - **D11, conteo.** Q1, Q1z, las tasas por marca de §1.10 y la lista descriptiva cuentan por variable de la fuente, para
    todas las marcas. Una marca se escribe en la columna `marcas_*` de cada variable que invalida: las de su fila de §2.4
    y las arrastradas.
  - **D11, en qué columnas va cada marca.** Con Ts = −40,0, la marca 4 va en Ts, Td y HR, y en Ts cuenta en la 3 (EMC1-1).
    La 7, la 9 y la 17 van en Td y HR; la 11 y la 12, en FF y DD; la 16, en QFE y QFF. El pico de la rapidez va sólo en
    FF. La racha del viento sigue P11; mientras tanto, la lectura más estricta: FF y DD.
  - **D16.** Q1z, Q2 y Q3 por macrozona se cuentan con `InfoEstacion.macrozona`. Con None, la hora cuenta sólo en lo
    nacional y se informa aparte.
  - **K4.** I12 arma la entrada de A4.
- **I13 (`candidatos`, ola 3).**
  - **D19.** Si `numerico.armonico_recortado` lanza `DisenoDeficiente`, la estación no entra en A ese mes. En
    `ESQUEMA_CLIMA_A` quedan `califica` = False y `rbar` = NaN en las 24 horas de (código, variable, mes), igual que sin
    los requisitos de §4.3. Por §4.5 («Sólo entran a Φ′ las estaciones que entran en A») tampoco entra a la parte de
    anomalías de AB ese mes.
  - **P12.** La macrozona en las indicadoras de C.
- **I14 (`validacion`, ola 3).** D16 en los estratos y en MZ: una estación sin macrozona no entra en ningún estrato de
  macrozona ni en ninguna macrozona de MZ. P12: el nivel neto y la anomalía de lo crónico.
- **D15.** Los parámetros de S6 (`sintetico.red_s6`, SIN-12) entran al addendum antes de correr S6: los usa I15 en la ola 4
  y los escribe I22 en la ola 6.
- **D14 y D13.** I17 (`salidas`, ola 4) asigna a cada carpeta su clase según D14 y usa la clase «documento» de D13. Los
  escritores de documentos son de I22 (ola 6).
- **D17 y D18.** Ya implementadas en `particiones` (PAR-1 y PAR-6): nada que hacer.
- **I1 e I5.** FIJ-9 y SIN-19 todavía hablan sólo de «sin_region». Quien vuelva a tocar esos módulos cita D16 (no cambia
  código). Si I8 o I12 lo piden, I5 suma a la grilla sintética dos tipos de celdas, como `construir_grilla`:
  - celdas de isla (`aoi_id` «juan_fernandez», región 5, macrozona «insular»);
  - celdas con `cod_comuna = 0` cuya macrozona se hereda de la vecina.

  Hoy la grilla sintética da «sin_region» a las celdas sin comuna y no trae islas, así que no distingue el camino de TIP-11
  del de la región.

### Preguntas para el autor (ola 2)

Ninguna bloquea la ola 2. El código sigue la propuesta, que es también la lectura más estricta, y lo deja dicho en su
lectura.

- **P10. Celdas con `cod_comuna = −1` (D9), antes de M3-4.**
  - **Cita.** D9: «coordenadas ilegibles en el catálogo, punto fuera de la grilla o celda con `cod_comuna = 0`» y «No se
    inventa una macrozona».
  - **Problema.** `construir_grilla.construir_celdas` (código) deja también celdas con `cod_comuna = −1`, las de centro
    fuera de toda comuna; así quedan, por ejemplo, las celdas generadas de las islas que no caen en un polígono. A estas
    celdas y a las de 0 les hereda la región de la celda válida más cercana a ≤ 30 km. D9 sólo nombra el 0. En las islas
    da igual (son «insular», D16), pero en el continente cambia en qué macrozona cuentan sus horas.
  - **Propuesta.** Tratar el −1 como el 0, sin macrozona: la suya es heredada, y D9 dice que no se inventa. Es lo que
    hace hoy `tipos.macrozona_de_celda`. (Coordinador.)
- **P11. La racha del viento en Q1 (D11), antes de M3-4.**
  - **Cita.** §2.4, marca 5: «viento con rapidez > 0 y la misma dirección y rapidez ≥ 12 h» | «sí, la variable». D11:
    «Las marcas que invalidan «el viento» (11 y 12) cuentan en FF y en DD; un pico de la rapidez, sólo en FF».
  - **Problema.** La racha del viento mira el par, y D11 no dice si cuenta en FF, en DD o en las dos. u y v quedan
    inválidos igual, porque con rapidez > 0 no hay viento sin dirección, pero cambia la tasa de Q1 de una de las dos
    variables.
  - **Propuesta.** En las dos, como la 11 y la 12: «la variable» de esa fila es «el viento». Es la lectura más estricta,
    y la sigue I12 mientras no haya respuesta. (Coordinador.)
- **P12. Estaciones y celdas sin macrozona fuera de las alarmas y los estratos (D9, D16), antes de M3-4.**
  - **Citas.** §4.6: «latitud e indicadoras de macrozona» y «las indicadoras de macrozona por los armónicos horarios».
    §5.2, en lo crónico: «Se resta a ε su media sobre las evaluaciones de la misma macrozona × año», y la anomalía
    interanual, «menos la media de macrozona × año». D9: «Vale para Q1z, Q2, Q3 y los estratos».
  - **Problema.** D9 y D16 no dicen dos cosas, y las dos cambian resultados (C y la S de lo crónico):
    - qué hace C con una estación o una celda sin macrozona, en el entrenamiento y en las celdas con `cod_comuna = 0`,
      que sí tienen producto;
    - cómo entra al nivel neto y a la anomalía de lo crónico una evaluación sin macrozona.
  - **Propuesta (a), C.** Las indicadoras salen de `macrozona_cod` de la celda tal como está en la grilla, con la
    macrozona heredada de la vecina: C usa la macrozona como predictor, y D9 habla de conteos y estratos. Con «sin_region»
    o «insular» (códigos 5 y 6), todas las indicadoras van en 0; las islas no tienen producto. Alternativa: todas en 0
    para toda celda sin macrozona según TIP-11. I13 deja la elección en un solo lugar y sigue la propuesta.
  - **Propuesta (b), lo crónico.** Las evaluaciones sin macrozona no entran al nivel neto ni a la anomalía, porque no
    tienen «misma macrozona»: se cuentan y se informan. Es la lectura más estricta, y la sigue I14. Alternativa: restarles
    la media nacional del año.

**Cifras antes de la ola 2:** la suite da 362 pruebas: 185 en verde, 177 omitidas y ninguna falla. Hay tres pruebas
nuevas en `test_tipos` (23 en total). Sin `__pycache__`.

## Ola 2 cerrada (2026-10-26)

Los seis módulos de ciencia de la ola 2 quedaron implementados, cada uno por su dueño, con sus lecturas en el
encabezado. Cada uno pasó por un revisor que no lo escribió (contraste con el v2.2, el diseño y D1-D19, y mutaciones en
una copia temporal) y por la corrección de su dueño; después, la integración del coordinador. Nada se escribió fuera de
`meteo_combinada/`; `reloj_dmc/`, el código fijado y `v2/` no se tocaron; ningún dato real se abrió. Sin commits.

**Entregas de §6 del diseño:** S2 (la parte de las políticas), S3, S4, S5 (fondo y el tramo del cambio de sensor), S11,
S12 (fondo), S13 (salvo la detención de M2a, que es de I20), S7 (la regla) y S16 (las ramas). Todas corren; ninguna
queda omitida.

### Qué entregó cada dueño (después de la revisión)

| Dueño | Módulo | Pruebas | Lecturas | Revisión → corrección |
|---|---|---|---|---|
| I6 | `politicas.py` | 22 en verde | POL-1 a POL-13 | 7 hallazgos (bordes del corte de MC-53, de `politicas_que_cruzan`, formas de C5, precedencia de motivos, firmas, registro fuera de APH, `k2` como texto); 26 mutaciones detectadas |
| I7 | `fondo_era5l.py` | 36 en verde | FON-1 a FON-13 | 11 hallazgos; el mayor: `completo` medía el mes calendario y el último mes es parcial (§3) → `MesE5L.completo_hasta(h_ultima)`; `operador_pixeles` para los píxeles; todo error es `ErrorFondo`; 50 mutaciones detectadas |
| I8 | `estaticas_nasadem.py` | 16 en verde | NAS-1 a NAS-15 | 5 hallazgos (celdas con dato parcial, OMM, GHS vacío, motivos, controles de `leer_tesela`); 14 de 16 mutaciones detectadas, 2 equivalentes |
| I9 | `homogeneidad.py` | 39 en verde | HOM-1 a HOM-12 | 5 hallazgos (clasificación de K4 en sus bordes, bordes del detector, δ, `codigo` obligatorio, horas repetidas); 17 mutaciones más 16 variantes detectadas; sobrevive una equivalente (el «≤» exacto de la tolerancia) |
| I10 | `decision.py` | 21 en verde | DEC-1 a DEC-19 | 11 hallazgos (MZ por partición, filas de macrozona en otra variable, bordes y sumandos, condición 1, TF fuera de E0, red de TF2, borde de 10⁻⁶, ganador ambiental, TF de I, lista de macrozonas); 21 mutaciones detectadas |
| I11 | `sinca_meteo.py` | 35 en verde | SNC-1 a SNC-15 | 9 hallazgos; el bloqueante: los manifiestos son disjuntos por serie, no por estación (comparten 47); política y veredictos atados a sus huellas; enlaces simbólicos (regla 10); 34 de 36 mutaciones detectadas, 2 equivalentes |

Los encargos cortos de I4 (D13, la clase «documento» de `ceguera`) e I5 (formatos a pedido) **no se entregaron** en esta
ola: `ceguera.py` y `sintetico.py` siguen como al cierre de la ola 1. Pasan a «Pendientes». El encargo de I8 decía por
error «Entrega: S4 y S11»; I8 entregó S3, que es lo que le asigna el reparto (S4 es de I9 y S11 de I7).

### Integración del coordinador

1. **`tipos.py`** (TIP-13 a TIP-16, lecturas de implementación; ninguna cambia una regla):
   - TIP-13 (pedido de I6): `ErrataConfirmada(ruta, sha256, commit)`; `RegistroReloj.errata_confirmada` es None o ese
     objeto (antes, un texto «ruta=… sha256=… commit=…» que I22 habría tenido que volver a partir).
   - TIP-14 (pedido de I8): `MotivoExclusion` (coordenadas ilegibles, fuera de rango, K3, sin z_s y «sin_fondo») y
     `MOTIVOS_SIN_COORDENADAS_K3` (los que Q2 cuenta como «K3 deja sin coordenadas»). Una estación lleva un solo motivo: el
     de `estaticas_nasadem` prevalece y «sin_fondo» va sólo en las que no estaban excluidas, para que Q2 no las pierda.
   - TIP-15 (pedidos de I10): `VariableMetrica` (T, Td, HR, rapidez, uv, p, temp_media, hr_media), `Estrato` (nacional
     y macrozona; I14 agrega los descriptivos de §5.5), `MACROZONAS`, `CONTAMINANTES_M6`, `CLAVE_O3`, `VERSION_DECISION`
     y `VERSION_DECISION_M6`, y qué dice `publicable` en P1, P2 y el agregado (MC-61; lo implementa I14 con su prueba).
   - TIP-16 (pedido de I11): `ESQUEMA_SINCA_HORA` no cambia; el conteo y la bandera de R7 y el reloj de cada serie van
     en `attrs["registro_sinca"]`, que `orquestacion` lleva al registro de M3-4.
   - Las columnas del manifiesto, de las elegidas y de las descartadas de SINCA siguen en `sinca_meteo` mientras no
     crucen a otro módulo; si I20 las necesita, se pasan a `tipos`.
2. **Corrección mínima de interfaz en archivos de I6** (por TIP-13; avisado aquí): `politicas._texto_errata` devuelve
   `tipos.ErrataConfirmada` y POL-1 lo dice; en `test_politicas.test_registro_c5_post_hoc_y_errata`, la comparación es
   con el objeto. No cambia ninguna regla ni ninguna otra prueba.
3. **Copias que siguen en los módulos.** `decision` (rótulos, macrozonas, contaminantes, versiones) y
   `estaticas_nasadem` (motivos) conservan sus constantes; `test_tipos.PruebasOla2` exige que sean iguales a las de
   `tipos` (y los rótulos de `sintetico.tablas_metricas`, y `MACROZONAS` contra `MACROZONA_CODIGO` por AST). Quien vuelva
   a tocar esos módulos las toma de `tipos`.
4. **`tests/test_integracion.py`** (nuevo, dueño I0): encadena la salida real de un módulo con la entrada real del
   siguiente, como lo hará `orquestacion`: `info_estaciones` → `tramos_de_lectura` y `politicas_de_lectura` (A8, A7, A6:
   QFE con p_std(z_s) sólo con z_cat que pasa K3; «k3» al final del `source`); `k4` → `politicas_efectivas` (A4, A5:
   el corte en u_k − 4 h y «traslado» antes del último traslado); `tabla_puntos` y `en_horas` → `k4` (A1, A2: el
   float32 guardado da lo mismo que el redondeo a mano, y una hora sin fondo es NaN); `nasadem_en_pixeles` → `z_e5l`
   (A9). Las cuatro pasan sin tocar ningún módulo: no apareció ningún desajuste de interfaz.
5. **`EN_CURSO`**: salen `test_politicas.py`, `test_fondo_era5l.py`, `test_estaticas_nasadem.py`,
   `test_homogeneidad.py` y `test_decision.py` (sus pruebas «sNN» corren). `test_sinca_meteo.py` no estaba (§9 no tiene
   prueba de SINCA, SNC-14).
6. **Comprobado:** detector de literales en verde (`TOLERADOS` vacío), grafo por capas, escritura sólo en `salidas`,
   `entorno` y `sintetico`, privacidad (ninguna ruta de la carpeta de usuario ni la arroba fuera de decoradores),
   sin `__pycache__` nuevo, nada escrito fuera del paquete.

### Acuerdos revisados al cierre (reemplazan lo dicho en «Acuerdos de interfaces»)

- **A2 y A3.** `en_horas`, `residuos` y toda función pública de `fondo_era5l` lanzan `ErrorFondo` (un `RuntimeError`,
  FON-2), nunca `ValueError` ni `TypeError`: si I12 los llama dentro de la captura del paso 1 de §2.1, un error de código
  detiene la corrida y no cuenta como «no normalizable» (MC-57).
- **A4.** `homogeneidad.k4(tabla_estacion, p_F, z_cat, umbrales, *, codigo) -> tipos.ResultadoK4`, con `codigo`
  obligatorio (texto no vacío). `Quiebre.mes`, `ultimo_traslado` y `ultimo_barometro` son `int` de Python;
  `tramos_homogeneos` da error con u, v y p («viento y presión no se segmentan»); δ puede ser NaN (HOM-11).
- **A6.** Los ids de tramo salen siempre de `tramos_de_politicas` sobre la lista completa de la estación (POL-10).
  [Ola 3, TIP-24 y QC-20: desde la marca 14 la columna `tramo` de la tabla ancha lleva los ids de la política efectiva
  (`politicas.tramos_marca_14`), no los de lectura. Ver «Ola 3 cerrada».]
- **A8.** Antes del operador, `w0`…`w3` valen NaN; después, una casilla sin vecino lleva `pix` −1, `w` 0 y `dz` NaN
  (FON-6). El motivo «sin_fondo» sigue TIP-14.
- **A10.** En los píxeles el operador es `fondo_era5l.operador_pixeles(pixel_ids, catalogo, validos, z_pix)` (por
  `pixel_id`, peso 1, dz = 0), no `operador(lat, lon, z_E5L, …)` con las coordenadas del catálogo (FON-6): así el
  fondo en un píxel es ERA5-Land tal cual, bit a bit.
- **A12.** `series_horarias(raiz, elegidas, politica_temporal, umbrales, *, veredictos)`, con `veredictos` obligatorio:
  el diccionario de `veredictos_civiles(tabla, convencion, *, sha256, resumen)` (claves `sha256`, `convencion`,
  `hora_civil` y `huella_contenido`; SNC-11). I20 pasa `veredictos.parquet` con su sha256 y el `resumen.json` del reloj
  SINCA. `h` es el fin del intervalo; I14 compara con la media del producto en h − 1 y h, sólo en las filas `valido`.

### Cambios de firma respecto de §3 del diseño (para el anexo de firmas que se regenera al cerrar M1)

- **Incompatibles** (una llamada con la firma de §3 falla; quien llama debe pasarlos):
  - `politicas.leer_registro_c5(ruta, *, ap)` y `politicas.tramos_de_lectura(politica_reloj, codigo,
    meses_con_artefacto, marcas_g, *, info, k2)`, sin valores por omisión (`k2`: conjunto de códigos, nunca un texto).
  - `homogeneidad.k4(…, *, codigo)`.
  - `fondo_era5l.z_e5l(geopotencial, catalogo, nasadem, sp_medio, umbrales, *, validos)` (la tabla de A9 en lugar de
    `teselas`), `campos_fondo(mes, op, umbrales, *, recortar_td=True)` (Γ es del Anexo A) y `sumas_rr06(tp_horario,
    h_fin, *, h)`.
  - `sinca_meteo.series_horarias(…, *, veredictos)`.
- **Más estricta:** `politicas.leer_politica_reloj` devuelve (política, {sha256 del artefacto: código}).
- **Aditivos:**
  - `politicas`: `ErrorC5`, `marcas_g`, `media_horaria`, `tramos_de_politicas`, `regla_reloj`, `validar_reglas`,
    `de_json`; `source_coordenadas(…, *, motivo=None)`.
  - `fondo_era5l`: `ErrorFondo`, `ErrorUnidades`, `ErrorAlineacion`, `MesE5L.completo_hasta`, `Geopotencial`,
    `leer_geopotencial`, `operador(…, *, ids=None)`, `operador_pixeles`, `columnas_operador`,
    `operador_desde_columnas`, `tabla_puntos`, `en_horas`, `horas_de`, `AcumuladorEstado`, `acumulador_estado`,
    `tabla_clima_estado`, `sp_medio_hpa`; `comprobar_unidades(mes, umbrales=None)` (no usa `umbrales`: los rangos son
    del A2); las constantes de claves.
  - `estaticas_nasadem`: `interpretar_coordenada`, `coordenadas_en_rango`, `TeselaDEM`, `TeselaGHS`, `leer_ghs`,
    `ventana_necesaria`, `estandarizar_tpi`, `nasadem_en_pixeles`, `tabla_estaciones`, `MOTIVOS`,
    `MOTIVOS_SIN_COORDENADAS_K3`; en `estaticos_celdas`, `ghs` es una lista de `TeselaGHS` o None (nunca vacía).
  - `homogeneidad`: `mes2000`, `hora_utc` y las constantes públicas; `medianas_mes_hora` da índice «mes» (mes2000) y
    columnas `pares` y `h00`…`h23`.
  - `sinca_meteo`: `ErrorSinca`, `altura_de`, `series_descartadas`, `leer_politica_temporal`, `zona_de`,
    `huella_contenido`, `veredictos_civiles`, `parsear_serie`, `horas_fin_utc`, `control_minimo`, `leer_serie`.
  - `decision`: `ramas_m6(…, *, entradas_ambientales=None, umbrales=None)`, `decisiones_restringidas`, `VariablesGrupo`.
  - `tipos`: `ErrataConfirmada`, `MotivoExclusion`, `MOTIVOS_SIN_COORDENADAS_K3`, `VariableMetrica`, `Estrato`,
    `MACROZONAS`, `CONTAMINANTES_M6`, `CLAVE_O3`, `VERSION_DECISION`, `VERSION_DECISION_M6`.

### Lecturas nuevas (en el encabezado de cada módulo; van al addendum de M1)

- **POL-1 a POL-13.** Registro de C5 sólo con rutas, huellas y commit, dentro del APH hermano de `ap`; las banderas, de
  la política. `ajuste_documental = true` contaba como falla (P13; desde D23 se acepta y se declara: ver «Cierre de la ola
  2»). K2 sólo del informe
  publicado, con la sha256 que cita la política. Tramos partidos el 1 de enero de cada año en que cambia el conjunto de
  marcas G y donde falta un mes con artefacto evaluado. Motivos de coordenadas: sin coordenadas legibles, K3, K2.
  Mediciones instantáneas con intervalo 0, RR06 suma de 360, QNH sin regla; «posible media horaria» quita todo. DD con
  `int` 0 y 360; QFF con `QQFF_*`; QFE sólo con z_s del catálogo. Política efectiva cortada en L_k = u_k + desfase.
  JSON canónico con tipos exactos.
- **FON-1 a FON-13.** Lector propio con HH:00 exacta y `completo_hasta(h_ultima)`; unidades por rango con la mediana del
  mes; todo error es `ErrorFondo`; píxeles válidos de los tres meses; z_E5L en tres casos con 10⁻⁵° de holgura;
  alineación a 0,001 m (NaN es diferencia); bilineal con renormalización por hora y respaldo a ≤ 16 km (empate por menor
  `pixel_id`); `residuos` redondea a float32 fondo y observación; lluvia como `meteo_civil_v3`; RR06 sin sumas
  parciales; climatologías 2000-2025 con la amplitud como media de las amplitudes diarias.
- **NAS-1 a NAS-15.** Coordenadas como RELOJ §3.3 (copia comparada por AST) y fuera de rango como ilegibles; K1 con el
  medio paso más grueso; red NASADEM entera (sumas exactas), varias teselas como una sola; celdas con bordes oeste y sur
  cerrados; sin dato no se rellena; pendiente con el cos φ de cada fila; altitud poblada con el píxel GHS que contiene
  el punto; TPI con disco de radio r y la parte con dato; K3 inclusiva; OMM con «alguna cifra».
- **HOM-1 a HOM-12.** mes2000 de la hora UTC; mediana con ≥ 5 valores; H*(k) en dos pasos con comparación entera;
  segmentación codiciosa con tramos de ≥ 12 meses; empates por el k central (P29); clasificación literal de §2.5 (P28);
  δ sobre las horas estables en todos los tramos (P30).
- **DEC-1 a DEC-19.** Variables por compuerta; sólo el agregado nacional y las tres particiones de macrozona; float64 sin
  tolerancia; MZ con ≥ 10 estaciones y publicable en P1, P2 y el agregado; TF leída y comprobada; empates por A, AB, B,
  C; regla crónica con la TF de la tabla para B o AB fuera de E0 por finitud (P35); «regla sin ganador» siempre con E1
  vacío; ΔS con el ganador fijo (P36; reemplazada por D46, DEC-12 reescrita); condiciones del Anexo B en LRO y BLQ-75 a
  la vez.
- **SNC-1 a SNC-15.** Seis huellas; disjuntos por serie (P40); sólo TEMP, RHUM, WSPD y WDIR; altura de la ficha o de la
  macro, y fuera si no calzan (P37); h = etiqueta + 4 h salvo veredicto civil; colisiones promediadas y WDIR inválida
  (P38); rangos inclusivos; veredictos atados a la tabla y al resumen del reloj SINCA; guarda de rutas antes de leer.
- **TIP-13 a TIP-16** (coordinador), arriba.

### Diferencias con el diseño (para el addendum de M1)

1. **Manifiestos SINCA** (diseño, l. 20-22: «Los dos son disjuntos y suman 154 estaciones»): con 87 y 114 estaciones
   comparten 47; son disjuntos por serie (`descargar_sinca_ampliacion.py`, d7724723…, excluye por región, estación,
   parámetro y macro). SNC-1. El diseño no se toca; queda anotado aquí.
2. **«Los módulos de ciencia nunca leen archivos»** (§3): la misma §3 da firmas que leen (`leer_tesela`, `leer_mes`,
   `leer_manifiestos`, `series_horarias`, `leer_registro_c5`, `leer_politica_reloj`, `coordenadas_inconsistentes`), y
   se suman `leer_ghs`, `leer_geopotencial` y `leer_politica_temporal`. Todas leen los bytes con `open` de Python, una
   vez, y exigen su sha256 sobre esos bytes (CEG-5). Ninguna escribe.
3. **Completitud del último mes** (FON-1): §3 lleva el producto hasta el último dato (hoy 2026-09-15 23:00 UTC), así que
   no hay completitud por mes calendario: `completo_hasta(h_ultima)`, con `h_ultima` de los manifiestos.
4. **El operador en los píxeles** es `operador_pixeles` (A10 revisado), y el respaldo es de 16 km para estaciones,
   celdas y píxeles, no los 15 km con que RELOJ elige su píxel (FON-6).
5. **Errores del fondo** como `RuntimeError` (FON-2), para que la captura de `ValueError` y `TypeError` del paso 1 de
   §2.1 nunca los cuente como «no normalizables».
6. **K4 recibe el código** (A4 revisado), y `tramos_homogeneos` sólo acepta T y Td.
7. **Coordenadas fuera del rango de RELOJ §3.3**: `estaticas_nasadem` las trata como ilegibles (NAS-1), pero
   `politicas` las rotula «k3» en el `source` (POL-5), porque ve la latitud legible y K3 fallida. El resultado es el
   mismo (sin coordenadas confirmadas, fuera, y en Q2 por TIP-14); sólo difiere el rótulo publicado (pendiente de I6).
8. **[Ya no existe: D46 aplica MC-34; ver «Cierre de la ola 2».]** **ΔS con el ganador fijo** (DEC-12) frente a MC-34,
   aceptada en bloque por D5 («Cada réplica repite todo: la unión
   de bandas, los mínimos de S_par sobre E0 y el ganador»). Va al autor como P36, por la cláusula de D5 («Si un
   revisor ve que alguna cambia una regla, se le pregunta aparte al autor»).
9. **S3 con teselas `.hgt`** (tabla de §5.1): son GeoTIFF int16 (SIN-9, ya anotado en la ola 1).
10. **El encargo de I8** (S4 y S11) no era el del reparto (S3); se entregó S3.

### Preguntas para el autor (ola 2)

Ninguna bloquea la ola 3. En todas, el código sigue la propuesta o, si el texto no calla, la lectura literal; donde
hay una más estricta, rige ésa.

- **P13. Política de RELOJ con `ajuste_documental = true`, antes de M3-4.** Cita: §2.1, «política con `post_hoc =
  false` y `errata_post_c4 = false`, o la corregida por una errata confirmada»; RELOJ §4.5, «Un documento obtenido
  después de C4 tiene ese mismo efecto y nada más. La política resultante lleva `ajuste_documental: true`». Problema:
  §2.1 no nombra la bandera y de ella depende qué política rige M3-4. Hoy: falla de C5 (POL-2). Propuesta: aceptarla,
  porque RELOJ no la trata como posterior al hecho y sólo quita confirmaciones, y declararla en el registro de M3-4. (I6.)
- **P14. El tramo de la marca 14, antes de M3-4.** Cita: §2.4, «|mediana(QFE − p_F)| > 8 hPa en el tramo»; §2.1, paso
  4, «con los tramos ya cortados»; §2.5, los tramos son los de RELOJ «partidos por los quiebres de K4 y por los años
  con marcas G-HR o G-viento». Problema: (a) en la lectura literal la mediana de QFE se toma en piezas cortadas también
  por años G y por quiebres de T2a sin T2b, que nada tienen que ver con QFE; (b) POL-4 junta en una pieza los años
  seguidos con las mismas marcas G (para `cargar_dmc` da lo mismo), pero con (a) literal eso cambia qué horas llevan
  la marca 14. Propuesta: los tramos de la política efectiva (`tramos_de_politicas` sobre la efectiva), con POL-4 tal
  cual. Alternativa: los tramos de RELOJ partidos sólo por los quiebres de T2b. Lo implementa I12. (I6 y su revisor.)
- **P15. Dónde queda la política corregida por una errata, antes de M3-4.** Cita: §2.1, «o la corregida por una errata
  confirmada, con su sha256 igual al registrado». Problema: POL-1 exige que el registro cite la ruta de publicación de
  RELOJ §7.1; si la errata publicara la política corregida en otra ruta, C5 fallaría y no habría producto (§2.1, «Sin
  política válida»). Propuesta: la corregida reemplaza a la publicada en la misma ruta, con su nueva sha256 en el
  registro; se acuerda con el C5 de RELOJ junto con el formato del registro. (Revisor de I6.)
- **P16. La lluvia de una estación en RR06, antes de M3-4.** Cita: §2.6, «contra la suma de las 6 horas ERA5-Land que
  terminan en la hora UTC del rótulo» y «Es una validación de la lluvia que entra al producto». Problema: no dice qué
  píxel o punto representa a la estación; cambia las métricas descriptivas de §2.6, no la decisión. Propuesta: el píxel
  que `enlaces_productos.parquet` enlaza a la celda de la estación (la lluvia que da el producto allí, MC-13); sin
  enlace no se compara y se cuenta. Alternativa: los pesos bilineales del operador. (I7, FON-P1.)
- **P17. La climatología de la amplitud diaria (C_est), antes de M3-4.** Cita: §4.7, «el operador del fondo aplicado a
  las climatologías por píxel, mes y hora UTC de 2000-2025 (T, T − Td, rapidez y amplitud diaria)». Problema: puede
  ser la media de las amplitudes diarias o la amplitud del ciclo diario medio (siempre menor); cambia C_est. Propuesta
  (implementada): la media de las amplitudes diarias, porque C_est reemplaza cada variable de estado por su
  climatología. (I7, FON-P2.)
- **P18. Cómo se aplica el operador a las climatologías, antes de M3-4.** Cita: la misma de P17. Problema: el operador
  de §4.1 no es lineal en Td (conserva q con el sp y el Td de cada píxel) y la rapidez del fondo es el módulo de (u_F,
  v_F); aplicado a climatologías de T − Td y de rapidez no queda definido, y `ESQUEMA_CLIMA_ESTADO` no trae Td, sp, u
  ni v. Tampoco dice si la climatología de T − Td lleva el recorte Td ≤ T de §4.1. Propuesta: T con los pesos bilineales
  y Γ; T − Td, rapidez y amplitud con los pesos bilineales solos; T − Td sin recorte (t2m − d2m del archivo); sin
  columnas nuevas. Alternativa: guardar también Td, sp, u y v y aplicar el operador completo. Lo aplica I13. (I7,
  FON-P3, y su revisor.)
- **P19. El radio del TPI, antes de M2a.** Cita: §4.6, «TPI a 1 y a 5 km (media NASADEM de la celda menos la del
  disco)». Problema: no dice si 1 y 5 km son el radio o el diámetro; con 1 km de diámetro el disco es casi la celda.
  Propuesta (implementada): radio, con centro en el centro de la celda y distancia haversine. (I8, NAS-P1.)
- **P20. Sin z_cat y sin bilineal completa, antes de M2a.** Cita: §2.5, «Sin z_cat legible: coordenadas confirmadas,
  z_s = NASADEM bilineal en el punto», y «si no, la estación queda fuera». Problema: en la costa o la frontera puede
  faltar un vecino de la bilineal. Propuesta (implementada): sin renormalizar; coordenadas confirmadas y la estación
  fuera con motivo «sin_z_s». Alternativa: renormalizar con los vecinos con dato. (I8, NAS-P2.)
- **P21. La ponderación de la altitud poblada, antes de M2a.** Cita: §3, «media NASADEM ponderada por la población
  GHS-POP R2023A de 100 m». Problema: no dice cómo se cruzan los puntos de 30 m con los píxeles de 100 m. Propuesta
  (implementada): cada punto NASADEM pesa la población del píxel GHS que contiene su centro. Alternativa: la media de
  cada píxel GHS asignada a la celda de su centro, como `pesos_poblacion`. (I8, NAS-P3.)
- **P22. El TPI truncado en la estandarización, antes de M3-4.** Cita: §4.6, «TPI = 0 tras estandarizar». Problema: no
  dice si las celdas truncadas entran a la media y al desvío. Propuesta: no entran. Lo aplica I13. (I8.)
- **P23. Una estación fuera de la grilla, antes de M3-4.** Cita: §4.6, «Los estáticos de una estación son los de su
  celda». Problema: sin celda no hay estáticos y C no puede predecir allí; el texto calla. Propuesta del coordinador (la
  más estricta para la comparación, que es entre candidatos en las mismas evaluaciones): la estación sale de la
  evaluación de todos los candidatos y se cuenta aparte; sigue entrenando A, B y AB. Alternativa (la de I8): sale sólo
  de C. La mayoría de estas estaciones (Antártica, islas sin celda) ya queda fuera por «sin_fondo». (I8.)
- **P24. Qué es un indicativo OMM, antes de M3-4.** Cita: §5.5, «con indicativo OMM»; MC-62, «Si el catálogo no trae
  OMM … esos estratos no se forman y se declara». Propuesta (implementada): un texto con alguna cifra; None en todas si
  ninguna lo trae. Alternativas: cualquier texto no vacío (el criterio del reloj) o las 5 cifras IIiii. Sólo cambia un
  estrato descriptivo. (I8, NAS-P4 nueva.)
- **P25. Coordenadas ilegibles o fuera de rango en Q2, antes de M3-4.** Cita: §2.7, «Numerador: las horas del
  denominador que K3 o K4 dejan sin coordenadas». Problema: no dice si cuentan las estaciones sin coordenadas legibles o
  fuera del rango de RELOJ §3.3. Propuesta (implementada, la más estricta): cuentan (`MOTIVOS_SIN_COORDENADAS_K3`).
  Alternativa: sólo las de K3 fallida con coordenadas legibles y en rango. (I8, NAS-P5 nueva.)
- **P26. Estaciones fuera de la cobertura de NASADEM, antes de M3-4.** Cita: §2.5, K3, «Se exige algún punto NASADEM con
  dato a ≤ ρ … Si no lo hay, la estación queda sin coordenadas confirmadas», y «Sin z_cat legible: coordenadas
  confirmadas»; §2.7, Q2 (> 5 % de las horas de una variable en 2000-2009 detiene M3-4). Problema: NASADEM no llega a la
  Antártica y el descargador la excluye; una estación antártica con altitud legible falla K3 y sus horas entran al
  numerador de Q2 (en lo nacional, D9 y D16), mientras que la misma sin altitud queda confirmada. Con pocas estaciones
  en 2000-2009 eso puede detener M3-4 por algo que no es un error de coordenadas. Hoy: la literal (K3 fallida, cuenta
  en Q2). Propuesta: una estación sin ninguna tesela NASADEM a ≤ ρ no tiene prueba K3 (como la marca 21 en K4): sale del
  numerador y del denominador de Q2, se informa aparte y sigue fuera («sin_fondo»). (Revisor de I8.)
- **P27. K1 con minutos decimales, antes de M2a.** Cita: §2.5, «con d decimales, 0,5·10⁻ᵈ grados; con segundos, 0,5″;
  sólo minutos, 0,5′». Problema: un texto «33°27,5'» trae minutos con decimales; con la lectura literal (0,5′) ρ es
  diez veces mayor que con 0,05′, y K3 pasa más fácil. Propuesta (implementada): la literal, 0,5′. Alternativa:
  0,5·10⁻ᵈ minutos. (Revisor de I8.)
- **P28. La coincidencia de T2a y T2b con ruido [E], antes de M3-4.** Cita: §2.5, «traslado: hay un quiebre de T2a a
  ≤ 3 meses, con |Δz_a − Δz_b| ≤ máx(10 m; 0,3·|Δz_b|)» y «en el k del máximo»; S4, «Un traslado de 15 m con QFE y QFF
  coherentes se declara traslado». Problema: la mediana de 12 meses hace una meseta de ±5 meses; el k del máximo de T2a
  y el de T2b caen en cualquier punto de ella y a veces quedan a más de 3 meses, y entonces el traslado se declara
  barómetro (marca 16 en vez de la 1). Con la regla literal y el ruido de MC-49, el revisor midió, con las semillas
  SEMILLA + i (i = 0…99), 90, 89 y 81 de 100 traslados de 15 m declarados a 500, 1.000 y 2.500 m (el implementador,
  con otras semillas, 84, 81 y 88). A 2.500 m, con la semilla del protocolo, 15 m mueven QFE sólo ≈ 1,4 hPa: sale un
  quiebre de T2a solo («método de reducción») y ninguna marca 1. S4 pasa (a 2.500 m no exige el traslado). Propuesta:
  enmienda ciega, «hay un salto de T2a de ≥ 10 m en algún k a ≤ 3 meses del quiebre de T2b», con Δz_a = D de ese k
  (100, 100 y 96 de 100 según el revisor). Mientras tanto rige la literal. (I9, HOM-P4.) [Respondida por D52 con la opción 2 del
  borrador, la del mismo mes, y no con esta propuesta; ver «Tras la ola 3».]
- **P29. Empates en «el k del máximo», antes de M3-4.** Cita: §2.5, «en el k del máximo». Problema: (a) el texto calla
  ante empates, que son frecuentes (23 % de los máximos en las series de S4); (b) dos mesetas separadas pueden empatar
  exactamente (con la resolución de 0,1 hPa de la DMC es posible) y entonces la mediana de todas las posiciones cae en
  el borde de una de ellas (dos escalones en 24 y 48 dan cortes en 24 y 43). Propuesta: (a) el k central de los
  empatados, con un número par el más tardío de los dos centrales (implementada); (b) el central dentro de la primera
  meseta de k consecutivos, y la otra queda para el paso siguiente (no implementada: rige HOM-5 tal como está).
  Alternativas: el primero, el último, o desempatar con la diferencia de medias. (I9, HOM-P1 y HOM-P5 nueva.)
- **P30. Las horas de δ, antes de M3-4.** Cita: §4.8, «media, sobre las horas de H*». Problema: H* sólo está definido
  para un corte k. Propuesta (implementada): las horas estables en ≥ 80 % de los meses candidatos de cada tramo; sin
  ninguna, δ = NaN y la estación no entra en B ni en AB. Alternativa: H*(k) del quiebre que abre cada tramo (el tramo 0
  no tiene uno). (I9, HOM-P2.)
- **P31. p̄ y T̄ «del tramo» en Δz_b, antes de M3-4.** Cita: §2.5, «T̄ en K y p̄ la media de QFE del tramo». Propuesta
  (implementada): el tramo que el quiebre partió. Alternativa: las ventanas de 12 + 12 meses. Efecto: < 1 % de Δz_b;
  sólo importa en el borde de la compatibilidad. (I9, HOM-P3.)
- **P32. Ruido y semillas de S4 y S5, al addendum antes de la batería de M1.** Como MC-49 y D15: semilla de S4 y S5 =
  `SEMILLA` (20261023); anomalías de S5 las de MC-50 (σ = 1,5 K, τ = 48 h, media 0 por mes y año). Aviso: sin la media
  0, 14 de 20 residuos estacionarios dan un tramo falso con 0,5 K (con ella, 0 de 20, confirmado por el revisor).
  Propuesta: fijarlos así. (I9, HOM-P5 de su primer informe.)
- **P33. MZ en (u, v), antes de M3-4.** Cita: §6.1, «CD y MZ, a las del puntaje del grupo: … la rapidez en (u, v)»;
  la tabla, «(u, v): RMSE vectorial horario»; MZ, «S_c,z ≤ 1,15 · mín S_c′,z». Problema: la lista dice rapidez y la
  definición de MZ usa S, que en (u, v) es el RMSE vectorial. Propuesta (implementada): MZ con el RMSE vectorial y CD
  con la rapidez. Alternativa: MZ con la rapidez. (I10, P-a.)
- **P34. Los mínimos del ganador restringido, antes de M6.** Cita: Anexo B, «entre A y C, los candidatos de E0 … con
  las compuertas de §6.2 y su paso 4»; §6.2, paso 2, «Los mínimos … sobre E0». Problema: E0 original (con B y AB) o
  {A, C}; cambia qué candidato pasa y el S_par. Propuesta (implementada, la más estricta): el E0 original. (I10, P-b.)
- **P35. Regla crónica con B o AB fuera de E0 por finitud, antes de M3-4.** Cita: §6.2, paso 5, «al menos uno de ellos
  falla TF o la compuerta de deriva … Si los dos quedan fuera sólo por otras compuertas, rigen los pasos 3 y 4».
  Propuesta (implementada, la más estricta): cuenta su TF de la tabla. Alternativa: no cuenta. (I10, P-c.)
- **P36. El intervalo de ΔS, antes de M3-4.** Cita: §5.4, «ΔS = S_c − S_ganador y su intervalo percentil del 95 %»;
  MC-34 (aceptada por D5), «Cada réplica repite todo: la unión de bandas, los mínimos de S_par sobre E0 y el ganador».
  Problema: con el ganador fijo, su propio intervalo es [0, 0]; con el ganador de cada réplica no, pero las réplicas de
  §5.4 sólo recalculan S, y elegir un ganador por réplica pediría también las compuertas por réplica, que el texto no
  define. Sólo cambia el intervalo publicado en `decision.json`. Hoy: el ganador fijo (DEC-12), apartándose de MC-34.
  Propuesta: el ganador fijo, que es lo que el texto dice, y anotar MC-34 como corregida en el addendum; alternativa:
  MC-34, con el ganador de cada réplica = el de menor S de réplica dentro del E1 de la decisión. (I10, P-d, y su
  revisor.)
- **P37. Series SINCA sin altura o con alturas que no calzan, antes de M3-4.** Cita: MC-10, punto 4, «la serie de
  altura más cercana a 2 m… en un empate, la de más filas con observación, y luego la de menor ruta». Problema: no dice
  qué hacer sin altura legible o si la ficha y la macro difieren («2,5» frente a «002»). Hoy: fuera. Alternativa: sin
  ninguna con altura, usar la sin altura con el mismo desempate; si difieren, la de la ficha. Sólo cambia la validación
  descriptiva de §5.6. (I11, SNC-P1.)
- **P38. Dirección del viento SINCA con dos etiquetas en la misma hora UTC.** Cita: R7 de la Enmienda 2 ambiental,
  «Dos etiquetas en la misma hora UTC: se promedian, con conteo y bandera». Problema: R7 se escribió para
  contaminantes; la media de 350° y 10° da 180°. Hoy: esa hora de WDIR queda inválida. Alternativa: media circular.
  Afecta una o dos horas por estación-año en hora civil. (I11, SNC-P2.)
- **P39. Unidades SINCA con otra grafía.** Cita: MC-10, punto 3, «rangos de §2.3 para TEMP (como Ts)…». Problema: el
  texto calla ante «ºC» o «km/h». Hoy: fuera con motivo «unidad_distinta». Propuesta: mantener la exclusión y, si en
  M3-4 los manifiestos traen otras grafías, listarlas en el addendum antes de leer valores. (I11, SNC-P3.)
- **P40. Manifiestos SINCA «disjuntos».** Cita: diseño, l. 20-22, «Los dos son disjuntos y suman 154 estaciones» (con
  87 y 114). Problema: comparten 47 estaciones; el descargador de la ampliación excluye por serie. Hoy: se rechaza una
  misma (estación, parámetro, macro), una misma ruta o un mismo sha256 en los dos (la más estricta: dos series
  distintas con bytes idénticos detendrían la lectura). Propuesta: confirmarlo. (I11, SNC-P4.)

### Pendientes para la ola 3 y siguientes

- **I12 (`qc_dmc_meteo`, ola 3).**
  - Firmas: `leer_registro_c5(ruta, *, ap)`, `tramos_de_lectura(…, *, info, k2)` con `k2` conjunto de códigos,
    `k4(…, *, codigo)`.
  - `normalizar_artefacto` usa `politicas_que_cruzan` y `validar_reglas`: `reglas_rechazadas` trae ids de RELOJ
    («1.1»). Sólo captura `ValueError` y `TypeError` del adaptador y de `cargar_dmc`; `ErrorFondo` no se captura.
  - La columna `tramo` sale de `tramos_de_politicas` sobre la lista completa (POL-10); la marca 14, con los tramos de P14
    (propuesta: la efectiva).
  - Entrada de A4 (NaN donde la hora no es válida tras el paso 2, sin la marca 14); marcas 1 y 16 en mes2000(h) < k;
    `ResultadoK4.D` nunca se escribe. Comparar MC-53 con `aplicar_k4` (A5).
  - QFE − p_F en hPa con el p_F de `en_horas` (marcas 13 y 14); `sumas_rr06` pide `h`; el punto de la lluvia, P16.
  - Q2 con `tipos.MOTIVOS_SIN_COORDENADAS_K3` (P25) y, si el autor acepta P26, sin las estaciones sin tesela NASADEM.
  - Lo de D11, D16 y P11 de la ola 2 sigue.
- **I13 (`candidatos`, ola 3).** `estandarizar_tpi` es la única estandarización del TPI, sin las celdas truncadas en la
  media y el desvío (P22); una estación sin celda no tiene estáticos (P23); δ puede ser NaN (la estación no entra en B ni
  en AB); `tramos_homogeneos` sólo con T y Td; el operador sobre las climatologías según P18; D19 y P12 siguen.
- **I14 (`validacion`, ola 3).** Rótulos de `tipos.VariableMetrica` y `tipos.Estrato`, y `tipos.MACROZONAS`; cada
  macrozona se publica en P1, P2 y el agregado para todo candidato de E0, con `publicable` y `n_estaciones` iguales para
  todos los candidatos (TIP-15), con una prueba; las réplicas, sólo de E0 y con S finito; `puntaje_par` con la fórmula de
  `decision._s_del_grupo`, comparadas en una prueba (A11). SINCA según A12 revisado.
- **I5 (`sintetico`, a pedido, ola 3).**
  - SIN-5 y la anotación de `politica_reloj_sintetica(errata_confirmada=…)`: un objeto {ruta, sha256, commit} (TIP-13;
    el código ya lo escribe tal cual).
  - `tablas_metricas`: en «e1_vacio», C falla TF1 con 0,15 K, que §5.7 hace error de código; que C quede fuera por otra
    compuerta y la TF fallida sea de B o AB. En «cronica_mixta», sumar «regla sin ganador» a las notas (DEC-10). Filas de
    macrozona en P1 y P2; casos de MZ en lo agudo (`temp_media`, `hr_media`) y en lo crónico con ≥ 10 estaciones.
  - `sinca_sintetico`: una estación en los dos manifiestos; corregir «estaciones disjuntas» de SIN-15.
  - Opcionales: ciclo diario en T2a y T2b de `series_traslado` (I9); calendarios, origen del eje y z transpuesto en los
    NetCDF (I7); celdas de isla y con `cod_comuna = 0` en la grilla (ola 2).
- **I4 (`ceguera`).** El encargo corto de la ola 2 (D13, la clase «documento», y citar D12 en CEG-11) no se entregó; debe
  estar antes de la ola 4 (I17).
- **I6 (si vuelve a `politicas`) o su revisor.** Rotular «sin_coordenadas» las coordenadas fuera de rango (diferencia
  7), cambiando a la vez la equivalencia de `test_estaticas_nasadem` (NAS-12); tomar los motivos de `tipos`.
- **I10 e I8 (al volver a sus módulos).** Tomar de `tipos` las constantes de TIP-14 y TIP-15 (hoy las guarda la
  paridad de `test_tipos`).
- **I1 (`fijados`).** Exponer la huella de la tabla de cambios de hora del reloj (`reloj_dmc.tablas.SHA_ANEXO_A`), que
  `politicas.SHA_TRANSICIONES_RELOJ` copia con su prueba de paridad.
- **I2 (`constantes`), si conviene.** `sinca_meteo.DESFASE_FIJO_H` (4 h, de R7) lleva «no-umbral»; I18 necesita el mismo
  valor para el día UTC−4.
- **I15 (`tendencias`, ola 4).** Filas de TF por uso (en lo crónico, sólo T); TF2 «no evaluable» en todos los
  candidatos, con red «ninguna» y < 10 estaciones; cotas de `constantes`; TF1 nunca «no evaluable»; la TF de
  contaminantes de I como verificación de un mes cuando ningún grupo ambiental gana con B o AB (DEC-14).
- **I16 e I18 (olas 4 y 5).** R lleva `R_T` … `R_p`; S14 con un operador del píxel enlazado (peso 1, Δz = 0, por
  `operador_desde_columnas`) y `recortar_td=False`.
- **I20 (`orquestacion`, ola 5).**
  - A `politicas`: `meses_con_artefacto` (pares de etiqueta de los manifiestos evaluados), `k2`, `resultados_k4`
    {código: ResultadoK4}, la sha256 del catálogo de C2 y `U.sha256_texto_vigente`.
  - Fondo: z_E5L necesita sp̄ (una pasada si todos los píxeles válidos tienen geopotencial, dos si no); en cada mes,
    `completo_hasta(h_ultima)` con `h_ultima` de los manifiestos y `comprobar_unidades`; los meses en orden al
    acumulador; contar los punto-hora `renormalizada` (MC-39); `campos_fondo` por lotes; detener M2a ante
    `ErrorAlineacion`; `operador_pixeles` en los píxeles (A10).
  - Estáticos: sólo las teselas de `ventana_necesaria` por lote (las 163 juntas son ≈ 6 GB); llevar
    `attrs["declaraciones"]` al registro de M2a; comparar `huellas_ghs` con las 8 de `huellas_m0.json`; «sin_fondo»
    según TIP-14.
  - SINCA: `veredictos_civiles(tabla, resumen["convencion_civil"]["elegida"], sha256=…, resumen=…)`. Riesgo: si el
    parquet releído no reproduce la huella de contenido del reloj SINCA, la lectura se detiene (del lado seguro).
  - Decisión: `hiperparametros` {(uso, grupo) o «uso/grupo»: {…}}, `tf_contaminantes` {pol: {«I»|«D»: «pasa»|«falla»}}
    y `ganador_ambiental` {grupo: candidato}.
- **I22 (ola 6).** `negativas_m34` captura `ErrorC5` y suma las fallas de `comprobar_c5`; comprueba en git el commit y
  la sha256 de `ErrataConfirmada`; el formato de `registro_politica_reloj.json` (POL-1) se acuerda con el C5 de RELOJ,
  con P15.
- **Huella de `v2/reloj_sinca_v2.py`.** No está en git y otro flujo lo edita (27cc8585… → 30c64edf… el 2026-10-26).
  MC-10, punto 1, depende de sus veredictos: antes de M3-4 su versión debe quedar anclada y en la lista cerrada del
  addendum (§9.4 del diseño). Si cambia, dos pruebas de `test_sinca_meteo` se omiten con su motivo.

**Cifras al cierre de la ola 2:** la suite da 478 pruebas: 364 en verde, 114 omitidas y ninguna falla. Por archivo de la
ola: `test_politicas` 22, `test_fondo_era5l` 36, `test_estaticas_nasadem` 16, `test_homogeneidad` 39, `test_decision`
21 y `test_sinca_meteo` 35, todas en verde; del coordinador, `test_tipos` 29 (seis nuevas, `PruebasOla2`) y
`test_integracion` 4 (nuevo). Las omitidas son las «por implementar» de las olas 3 a 6 (`test_qc_dmc_meteo` 41,
`test_candidatos` 10, `test_validacion` 9, `test_tendencias` 9, `test_verificar_meteo_combinada` 13, `test_salud` 6,
`test_ambiental` 5, `test_salidas` 5, `test_orquestacion` 4, `test_producto` 3, `test_addendum` 2 y `test_costo` 2), la
de huellas de datos (`test_fijados`, decisión 4) y cuatro de `test_meteo_combinada` (S10 de la batería, el cierre de M1
y el índice, que informa pendientes S1, S6, S8, S9, S14 y S15). Sin `__pycache__`.

## Cierre de la ola 2: decisiones D20-D50 aplicadas (2026-10-26)

Después de «Ola 2 cerrada», el autor delegó P10-P40: son D20-D50 [delegada], en
`APH/auditoria/20261023/meteo_combinada/m1/decisiones_autor_m1_20261026.md`. Rigen igual mientras el autor no las cambie;
P28 queda para el autor y rige la literal. Siete dueños volvieron a sus módulos para aplicarlas y el coordinador integró.
Nada se escribió fuera de `meteo_combinada/`; `reloj_dmc/`, el código fijado y `v2/` no se tocaron; ningún dato real se
abrió. Sin commits.

### Qué entregó cada dueño

| Dueño | Módulo | Decisiones | Pruebas (antes) | Mutaciones | Lecturas |
|---|---|---|---|---|---|
| I4 | `ceguera.py` | D12, D13, D14 | 27 en verde (20) | 19 de 19 | CEG-11 y CEG-12 cambiadas; CEG-18 y CEG-19 nuevas |
| I5 | `sintetico.py` | A11, D42, D43, D46 (formatos) | 35 en verde (29) | — | SIN-13, SIN-14 y SIN-19 cambiadas; SIN-20, SIN-21 y SIN-22 nuevas |
| I6 | `politicas.py` | D23, D24, D25, D26 | 27 en verde (22) | 8 de 8 | POL-1, POL-2 y POL-4 cambiadas; POL-14 y POL-15 nuevas |
| I7 | `fondo_era5l.py` | D27, D28, D29 | 44 en verde (36) | 19 de 20 (1 equivalente) | FON-12 y FON-13 cambiadas; FON-14 nueva |
| I8 | `estaticas_nasadem.py` | D30 a D38 | 19 en verde (16) | 19 de 19 | NAS-2, NAS-8 a NAS-12 cambiadas; NAS-16 a NAS-18 nuevas |
| I9 | `homogeneidad.py` (sólo el encabezado) | D39, D40, D41, D42 | 44: 43 en verde y 1 omitida con su motivo (39) | 8 de 8 | HOM-5 corregida; HOM-7 y HOM-11 citan D41 y D40; HOM-13 y HOM-14 nuevas |
| I10 | `decision.py` | D43, D44, D45, D46 | 24 en verde (21) | 6 de 7 (1 equivalente) | DEC-1, DEC-9, DEC-12 y DEC-15 cambiadas; DEC-2, DEC-4 y DEC-17 a DEC-19 citan `tipos`; DEC-20 nueva |

Lo principal de cada entrega:
- **I10.** D46: en cada réplica gana el de menor S de réplica dentro del mismo conjunto en que eligió la decisión (E1; el
  paso 4; A y C_est en el paso 5; E1 ∩ {A, C}, o el paso 4 entre A y C, en el ganador restringido), con el desempate
  fijo. Las compuertas no se rehacen por réplica y ΔS sigue con el ganador de la decisión. D43: MZ en «uv» y en la
  rapidez. DEC-20: las variables de MZ de un grupo traen las mismas macrozonas; si no, error. `test_decision` ya no
  tiene rodeos (se borraron `_con_particiones`, `_e1_vacio_valido` y el de la rapidez).
- **I5.** `tablas_metricas` calza tal cual con `decision` en sus 24 casos de la regla (A11): filas en P1, P2 y el
  agregado, con el reparto de SIN-22; la TF de A, C y C_est siempre 0 (§5.7; pedir otra da `ValueError`); «e1_vacio» y
  «cronica_mixta» corregidos; filas de macrozona de la rapidez (D43); cuatro casos nuevos (`mz_no_publicable_p2`,
  `falla_mz_agudo`, `falla_mz_rapidez` y `falla_mz_cronica`); `esperado["conjunto"]` (D46). S4: las señales de la
  reducción y del horario y el ruido blanco horario de 5 m de z_impl (SIN-13, SIN-20); sin señales, las series son bit
  a bit las de la ola 1. S5: las anomalías de MC-50 (SIN-21).
- **I4.** La clase «documento» (D13): `ReferenciaDocumento` con la huella completa del texto vigente; todo número suelto
  debe estar en el texto o en las fuentes, que son sólo el paquete o la auditoría del producto en APH. Además,
  `ConsolaDocumento`, la clase fijada por la ruta (`clase_de_ruta`, D3, D13 y D14) y los enteros negativos fuera de la
  procedencia (D12). `ceguera` guarda una copia de `SHA_TEXTO_VIGENTE`, con prueba de paridad.
- **I6.** D25: corte el 1 de enero de cada año con marcas G y el del año siguiente. D23: `ajuste_documental` ya no es
  falla, y `declaracion_c5` da lo que el registro de M3-4 declara. D24: `tramos_marca_14`. D26: el formato del registro
  de C5 (siete claves) y la errata en la misma ruta.
- **I7.** D29: T − Td = máx(t2m − d2m, 0) hora a hora antes de promediar (cambia el valor de `T_menos_Td`, no el
  esquema), y `clima_en_puntos` y `clima_en_horas`. D27: `pixel_de_lluvia` y `lluvia_rr06`; sin enlace da NaN con su
  marca y se cuenta aparte. D28: ya estaba.
- **I8.** D37: el motivo «sin_nasadem» (`hay_tesela_a_rho`, `ventana_k3`, `MOTIVOS_FUERA_DE_Q2`). D34:
  `fuera_de_la_grilla` y `declaraciones_estaciones` (`attrs["declaraciones"]`). D33: `tpi_entra_a_estandarizar`. Más
  estrictos: `estandarizar_tpi` exige truncados booleanos e `info_estaciones`, teselas leídas con `leer_tesela`.
- **I9.** D39: la justificación de HOM-5 corregida en los bordes del tramo, con una prueba mes a mes. D42: la reducción
  exige un solo quiebre de T2a «método de reducción» a ≤ 5 meses del cambio, con D a ≤ 10 % del salto esperado; el
  horario, ninguno. El traslado de 15 m se prueba a 500 y 1.000 m; a 2.500 m queda omitido con su motivo (P28 y P47).
  S5 usa las anomalías de MC-50 con media 0, y la prueba sin media 0 es sólo informativa.

**Tasas de S4 medidas (HOM-14, para el addendum).** Regla literal (P28 abierta), semillas SEMILLA + i, i = 0…99 por caso y
altitud (el conjunto del revisor de P28) [con EMC2-1 (D52) el traslado de 15 m pasa a 100, 100 y 96; lo demás no cambia;
ver «Tras la ola 3»]:

| Caso | 500 m | 1.000 m | 2.500 m |
|---|---|---|---|
| Traslado de 15 m declarado traslado | 90 | 89 | 81 |
| Traslado de 5 m sin ningún quiebre | 100 | 100 | 100 |
| Barómetro de 1,5 hPa: un solo quiebre, de T2b y «barómetro» | 100 | 99 | 100 |
| Reducción: un solo quiebre, de T2a y «método de reducción» | 100 | 100 | 100 |
| Horario sin ningún quiebre | 100 | 100 | 100 |

Ninguna de las 1.200 series de 5 m, barómetro, reducción y horario declara un traslado; falsos quiebres, 0 de 200
(i = 0…199; el texto pide ≤ 2 %). Si alguien cambia `series_traslado` o el detector, `PruebasS4Tasas` falla y hay que
volver a declarar las tasas en la prueba y en el addendum.

**Huellas sha256 de lo entregado:**
- `ceguera.py` `c97a49db15a8dd8412493aaf177212e91d628e965505d7e1f2c460bc700e4a97`; `tests/test_ceguera.py`
  `6b058c09638ca345d745f260479338c93a698cf0ed86316fac0feebcf7f3f076`.
- `sintetico.py` `f87148e775c52243a288c2ca045806f4b567ecbd0ebf4e868dad68849fd3fe0e`; `tests/test_sintetico.py`
  `b23c42ba0dca5e09ff757f3dad03fda0a2a9b431cb5c62d09dc5e6cd0287989f`.
- `politicas.py` `8116414a461ee6d1d7a76c04c2f12dc4164c5969c92821bb0f113d2ef9b8d5bc`; `tests/test_politicas.py`
  `fc1d878924c8d7e5ace7451d6c3a8791cdaf8283b8de090ce2344a4bb9ccaedf`.
- `fondo_era5l.py` `d305df752b955bd8344a26457f1e17ea9dce25abe5e343eb9011b1db00b8d2c2`; `tests/test_fondo_era5l.py`
  `9680d8a1167e5d553c35cb405dc47c59e1f8caf3f6bfb1097edc9ef682b58a35`.
- `estaticas_nasadem.py` `5f2b3add91c29f98cd4e4ea7c8bb71443dcd0476f0a890860d5d670086a2ef50`;
  `tests/test_estaticas_nasadem.py` `e1f04127af092c3bf6dd7d5a1ad24e60adae56b4be371e6bd306b6ba03859f30`.
- `homogeneidad.py` `b8ed49f739fdc56e775cabd09b35d612bd3c09650b33c4ff5f91180a08383b67`; `tests/test_homogeneidad.py`
  `48885c8cbc577e5d0bc84602bd12284d9f8760648c661e6f45ba809372c34700`.
- `decision.py` `d2d1891f0a2676af0bed79a7151a3e74770e830e1d0e94d3d46fde3667d9074e`; `tests/test_decision.py`
  `2cf505d814e31e96131c04327aeb8750e18dbd840a7ad9f80c6e847899e552fc`.

Las huellas del coordinador van al final de esta sección.

### Integración del coordinador

1. **`tipos.py`** (lecturas de implementación; ninguna cambia una regla):
   - **TIP-14 revisada** (pedido de I8; D36 y D37). Se agrega `MotivoExclusion.SIN_NASADEM` («sin_nasadem»). El
     enumerado queda en el orden de precedencia de `estaticas_nasadem.MOTIVOS`: va antes de «k3» y deja «sin_fondo» al
     final. Se agrega también `MOTIVOS_FUERA_DE_Q2` = {«sin_nasadem»}, disjunto de `MOTIVOS_SIN_COORDENADAS_K3`. Arregla
     la única falla de la suite (`test_tipos.test_motivos_de_exclusion`).
   - **TIP-11** cita D20: el −1 como el 0. El código ya lo hacía.
   - **TIP-17** (pedido de I7; acuerdo A14). `DatosCompetencia` suma `puntos_e5l` (el estado de C) y `clima_estado` (el
     de C_est), más `VARIABLES_CLIMA_ESTADO`. Nadie construía todavía `DatosCompetencia`, así que no se rompe ninguna
     llamada.
   - **TIP-18** (D22 (a)). `MACROZONA_COD` copia `_comun_modelo.MACROZONA_CODIGO`; `test_tipos` la compara por AST.
     `indicadoras_macrozona(macrozona_cod)` da las cinco indicadoras de C desde el código de la grilla (la macrozona
     heredada), todas en 0 con «sin_region» o «insular». Así `candidatos`, que no puede importar `fijados`, aplica D22
     (a) sin copiar la codificación.
   - **TIP-15.** `decision` ya toma de `tipos` sus nombres.
2. **`test_tipos`: 32 en verde (29).**
   - `test_motivos_de_exclusion` exige el orden de precedencia, que `MOTIVOS_FUERA_DE_Q2` sea igual al de
     `estaticas_nasadem`, que los dos conjuntos de Q2 sean disjuntos y que «sin_z_s» y «sin_fondo» no estén en ninguno.
   - La clase nueva `PruebasCierreOla2` tiene tres pruebas: `MACROZONA_COD` por AST, las indicadoras y el estado en
     `DatosCompetencia`. Esta última compara las variables con `fondo_era5l.VARIABLES_CLIMA` y con
     `ESQUEMA_CLIMA_ESTADO`.
3. **`test_integracion`: 5 en verde (4).** La prueba nueva es
   `PruebasIntegracionDecision.test_tablas_metricas_tal_cual_en_decidir_combinacion`. Toma los 24 casos de la regla de
   `tablas_metricas`, tal como salen, y los pasa por `tipos.EntradasDecision`, `decision.compuertas` y
   `decidir_combinacion`. Luego arma `decision_json` y lo pasa por la guarda de su clase (`clase_de_ruta`).
   - Compara las compuertas fallidas, E0, E1, el ganador (que sale de `esperado["conjunto"]`), S, ΔS y las notas.
   - Compara también el intervalo de ΔS de D46, contado aparte con el conjunto del esperado y un percentil sin
     interpolar hecho a mano.
   - Ningún caso se omite: si un caso no calza, la prueba falla.
   - Mutaciones en memoria, todas detectadas: el intervalo con el ganador fijo, el intervalo con todo E0, el desempate
     al revés, `indicadoras_macrozona` sin error para un código desconocido y «k3» en `MOTIVOS_FUERA_DE_Q2`.
   - **Hallazgo de integración.** `decision_json` acepta `huellas` vacías, pero la guarda (CEG-15) no deja escribir un
     `decision.json` sin huellas. Queda del lado seguro, y la prueba lo deja escrito. Pedidos: a I10, exigir al menos
     una huella (la lectura más estricta); a I20, pasar siempre las de sus entradas (§8, «Cadena de huellas»).
4. **Anotaciones en secciones anteriores.** Van entre corchetes o entre paréntesis, sin borrar el texto:
   - `pruebas_m1.txt` es documento (D13);
   - `ajuste_documental` (D23);
   - ΔS con el ganador fijo (D46);
   - la diferencia 8 de la ola 2.
5. **`EN_CURSO`** no cambia: todavía no corre ningún «sNN» de la ola 3.
6. **Comprobado:**
   - detector de literales en verde (`TOLERADOS` vacío), grafo por capas, escritura sólo en `salidas`, `entorno` y
     `sintetico`, y privacidad;
   - ningún `__pycache__` nuevo (los 7 que hay en `scripts_modelo_1km` son de otros flujos y ya estaban);
   - nada escrito fuera del paquete.

### Respuestas a P10-P40: dónde quedó cada decisión

| D | P | Qué fija | Dónde | Estado |
|---|---|---|---|---|
| D20 | P10 | `cod_comuna = −1` como el 0 | `tipos.macrozona_de_celda` (TIP-11) | Aplicada (el código ya lo hacía) |
| D21 | P11 | La racha del viento en FF y DD | `qc_dmc_meteo` (I12) | Pendiente, ola 3 |
| D22 | P12 | (a) indicadoras de C; (b) lo crónico sin macrozona | (a) `tipos` TIP-18 → `candidatos` (I13); (b) `validacion` (I14) | `tipos` listo; I13 e I14, ola 3 |
| D23 | P13 | `ajuste_documental` aceptado y declarado | `politicas` POL-2 y POL-15 (`declaracion_c5`) | Aplicada; I20 lo escribe en el registro de M3-4 |
| D24 | P14 | Tramos de la marca 14 | `politicas` POL-14 (`tramos_marca_14`) | Aplicada; la marca es de I12 |
| D25 | POL-4 | Cortes por años G | `politicas` POL-4 | Aplicada |
| D26 | P15 | Errata en la misma ruta; formato del registro | `politicas` POL-1 | Aplicada; el C5 de RELOJ debe escribirlo así |
| D27 | P16 | Lluvia de RR06 por el píxel enlazado | `fondo_era5l` FON-12 | Aplicada; la usa I12 |
| D28 | P17 | Media de las amplitudes diarias | `fondo_era5l` FON-13 | Aplicada (ya estaba) |
| D29 | P18 | El operador sobre las climatologías; recorte hora a hora | `fondo_era5l` FON-13 y FON-14; `tipos` TIP-17 | Aplicada; la usan I13 e I20 (A14) |
| D30 | P19 | 1 y 5 km son el radio | `estaticas_nasadem` NAS-9 | Aplicada (ya estaba) |
| D31 | P20 | Sin renormalizar, «sin_z_s» | NAS-11 | Aplicada (ya estaba) |
| D32 | P21 | Altitud poblada por el píxel GHS del centro | NAS-8 | Aplicada (ya estaba) |
| D33 | P22 | TPI truncado fuera de la media y el desvío | NAS-9 (`tpi_entra_a_estandarizar`) | Aplicada; la usa I13 |
| D34 | P23 | Fuera de la grilla: sin evaluación, entrena A, B y AB | NAS-17 (`fuera_de_la_grilla`, declaraciones) | En `estaticas_nasadem`; particiones, C y evaluación de I3, I13 e I14 (P46) |
| D35 | P24 | OMM con alguna cifra | NAS-12 | Aplicada (ya estaba) |
| D36 | P25 | Ilegibles y fuera de rango cuentan en Q2 | NAS-12; `tipos` TIP-14 | Aplicada; Q2 de I12 (A15) |
| D37 | P26 | Sin NASADEM a ≤ ρ: fuera de Q2 | NAS-16; `tipos` TIP-14 | Aplicada; Q2 de I12 (A15), teselas de I20 |
| D38 | P27 | K1 con minutos decimales: 0,5′ | NAS-2 | Aplicada (ya estaba) |
| D39 | P29 | El k central de los empatados | `homogeneidad` HOM-5 (corregida) | Aplicada |
| D40 | P30 | Las horas de δ | HOM-11 | Aplicada (ya estaba) |
| D41 | P31 | El tramo que el quiebre partió | HOM-7 | Aplicada (ya estaba) |
| D42 | P32 | Ruido, señales y semillas de S4 y S5 | HOM-13 y HOM-14; SIN-13, SIN-20 y SIN-21 | Aplicada; los valores van al addendum antes de correr S4 (P48) |
| D43 | P33 | MZ en el RMSE vectorial y en la rapidez | `decision` DEC-1 y DEC-20; SIN-14 | Aplicada; el S de la rapidez por macrozona lo publica I14 (P41) |
| D44 | P34 | El E0 original en el restringido | DEC-15 | Aplicada (ya estaba) |
| D45 | P35 | Cuenta su TF | DEC-9 | Aplicada (ya estaba) |
| D46 | P36 | MC-34: el ganador de cada réplica | DEC-12; `esperado["conjunto"]` (SIN-14); `test_integracion` | Aplicada |
| D47 | P37 | Serie SINCA sin altura o que no calza: fuera | `sinca_meteo` | El código ya sigue la estricta; falta citar D47 en su lectura (I11) |
| D48 | P38 | WDIR inválida con dos etiquetas | `sinca_meteo` | Ídem, con D48 |
| D49 | P39 | Otra grafía de unidades: fuera | `sinca_meteo` | Ídem, con D49; si aparecen en M3-4, se listan en el addendum |
| D50 | P40 | Disjuntos por serie, ruta y sha256 | `sinca_meteo` | Ídem, con D50 |

**P28 sigue abierta** y rige la literal. El archivo de decisiones dice que su borrador de enmienda ciega está en
`../enmienda2_borrador/`. Esa carpeta todavía no existe bajo `APH/auditoria/20261023/meteo_combinada/`; sólo se comprobó
el nombre. Hace falta antes de M3-4, y P47 se decide con ella.

### Acuerdos nuevos

- **A13. Las cinco macrozonas en cada variable de MZ** (pedido de I10; TIP-15). Hoy, si a un grupo le faltan sus filas de
  macrozona, pasa sin MZ y nada lo avisa. Ésta es la lectura más estricta:
  - **I14** publica las cinco de `tipos.MACROZONAS` para cada (uso, grupo) y cada variable en que rige MZ, incluida la
    rapidez de (u, v) (D43). Van en P1, P2 y el agregado, para todo candidato de E0, aunque una macrozona tenga 0
    estaciones (`n_estaciones` = 0, `publicable` = False, S NaN).
  - **I10** las exige en `decision` (error si falta alguna). Acepta un S no finito sólo donde MZ no rige: con menos de 10
    estaciones o sin publicar en alguna partición.
  - **I5** suma en `tablas_metricas` las otras cuatro macrozonas, con menos de 10 estaciones, para que ningún caso
    cambie.
  - **Orden:** primero I5 e I14 y después I10. Si no, `test_s07` y `test_integracion` fallan.
  - [Mientras no se cumpla, `test_integracion` (INT-2) declara los casos sin filas de macrozona. Ver «Revisión
    independiente tras el cierre de la ola 2».]
- **A14. El estado en las estaciones** (TIP-17; pedido de I7).
  - `orquestacion` (I20) arma `DatosCompetencia.puntos_e5l`: código → `ESQUEMA_PUNTOS_E5L`, con el float32 guardado de
    A1.
  - Arma también `clima_estado`: código → {`VARIABLES_CLIMA_ESTADO`: 12 × 24 en float64}, de
    `fondo_era5l.clima_en_puntos` con el operador de las estaciones, por lotes. Cuenta los `renormalizada` (MC-39).
  - `candidatos` (I13) los lleva a las horas con el mes y la hora UTC de cada h, como `clima_en_horas`, sin importar
    `fondo_era5l`.
  - En las celdas, para el producto de C_est, se hace lo mismo con el operador de las celdas (I16).
- **A15. Q2 se cuenta por motivo** (D36 y D37; pedido de I8).
  - **Numerador:** las horas de las estaciones con motivo en `tipos.MOTIVOS_SIN_COORDENADAS_K3`, más las que K4 deja
    sin coordenadas.
  - **Denominador:** sin las de `tipos.MOTIVOS_FUERA_DE_Q2`, que se informan aparte.
  - No se usa `coordinates.verified` de la política, que es falso también en una «sin_nasadem» con z_cat.

### Lecturas nuevas o cambiadas (van al addendum de M1)

- **CEG-11, CEG-12, CEG-18 y CEG-19.**
  - D12: los enteros de la procedencia son conteos y no pueden ser negativos.
  - Las carpetas de D14 se suman a las de D3.
  - La regla del documento, con su límite declarado: no ve un número de datos que coincide con uno del texto, uno
    escrito con letras ni uno dentro de un identificador.
  - La clase la fija la ruta.
- **SIN-13, SIN-14, SIN-19 a SIN-22.** El ruido y las señales de S4, las anomalías de S5 (MC-50) y el reparto entre P1 y
  P2. Los casos siguen A11, §5.7, DEC-10, D43 y D46, y SIN-19 cita D16.
- **POL-1, POL-2, POL-4, POL-14 y POL-15.**
  - El registro de C5: siete claves, JSON en UTF-8, sin claves repetidas ni NaN.
  - La errata va en la misma ruta y la original se archiva con un sufijo.
  - `ajuste_documental` se acepta y se declara.
  - Los cortes de D25, los tramos de la marca 14 y la declaración de C5.
- **FON-12, FON-13 y FON-14.**
  - El píxel enlazado para la lluvia: la tabla de enlaces se exige estricta, y una celda o un píxel que falta es un
    `ErrorFondo`.
  - El recorte de T − Td hora a hora.
  - El operador sobre las climatologías, con las 12 × 24 filas exactas de cada píxel.
- **NAS-2, NAS-8 a NAS-12 y NAS-16 a NAS-18.**
  - Una tesela a ≤ ρ cuenta aunque no tenga dato, con «≤ ρ» inclusivo; una tesela no pasada cuenta como inexistente.
  - `k3_pasa` y z_s siguen la regla literal.
  - Una tesela a ≤ ρ sin dato sigue siendo prueba K3.
  - D34, y las declaraciones, que llevan sólo conteos.
- **HOM-5, HOM-7, HOM-11, HOM-13 y HOM-14.**
  - Los empates en los bordes del tramo: 320 de 1.195 máximos empatados (27 %).
  - La verdad de S5.
  - Las semillas y tasas de S4, en la tabla de arriba.
- **DEC-1, DEC-9, DEC-12, DEC-15 y DEC-20.** MZ en «uv» y en la rapidez, D45, D46 en el intervalo, D44, y las mismas
  macrozonas en las variables de MZ.
- **TIP-11, TIP-14, TIP-15, TIP-17 y TIP-18** (coordinador), arriba.

### Cambios de firma (para el anexo de firmas)

- **Más estrictos:**
  - `ceguera`: la clase fijada por la ruta y los enteros negativos en la procedencia.
  - `politicas`: `politicas_de_lectura` rechaza un tramo que contenga un corte de D25 sin partir.
  - `estaticas_nasadem`: `estandarizar_tpi` exige truncados booleanos e `info_estaciones`, teselas de `leer_tesela`.
  - `decision`: DEC-20, y MZ también en la rapidez.
  - `sintetico.tablas_metricas` rechaza una TF fallida de A, C o C_est y las notas fuera de orden.
  - `tipos.DatosCompetencia` tiene dos campos obligatorios más; no había ninguna llamada.
- **Comportamiento:** el valor de la columna `T_menos_Td` de `ESQUEMA_CLIMA_ESTADO` cambia por D29; el esquema no.
- **Aditivos:**
  - `ceguera`: `vigilar_salida(…, referencia=None)`, `ReferenciaDocumento`, `ConsolaDocumento`, `clase_de_ruta`,
    `CLASE_DE_ARCHIVO`, `CLASE_DE_CARPETA`, `SHA_TEXTO_VIGENTE` y `RAICES_FUENTES`.
  - `sintetico`:
    - `series_traslado(…, dt_clima_k=None, ciclo_diario_m=None)`, con atributos nuevos, y `ciclo_diario_t2b_hpa`;
    - las constantes `SIGMA_*`, `TAU_T2B_DIAS`, `DT_CLIMA_REDUCCION_K`, `CICLO_HORARIO_M`, `HORA_MAXIMO_CICLO_UTC`,
      `HORARIO_DIURNO_UTC`, `ANOMALIAS_MC50`, `CERO_POR_CONSTRUCCION`, `PARTICIONES_VALIDACION` y `ORDEN_NOTAS`;
    - `verdad(…, anomalias=True | "MC-50" | dict)`, que devuelve la clave «anomalias»;
    - `esperado["conjunto"]` y los cuatro casos nuevos.
  - `politicas`: `tramos_marca_14`, `declaracion_c5` y `CLAVES_DECLARACION_C5`.
  - `fondo_era5l`: `clima_en_puntos`, `clima_en_horas`, `pixel_de_lluvia`, `lluvia_rr06`, `COLUMNAS_ENLACE` y
    `SIN_ENLACE`.
  - `estaticas_nasadem`: `hay_tesela_a_rho`, `ventana_k3`, `tpi_entra_a_estandarizar`, `fuera_de_la_grilla`,
    `declaraciones_estaciones`, `MOTIVO_SIN_NASADEM` y `MOTIVOS_FUERA_DE_Q2`.
  - `tipos`: `MotivoExclusion.SIN_NASADEM`, `MOTIVOS_FUERA_DE_Q2`, `MACROZONA_COD`, `indicadoras_macrozona` y
    `VARIABLES_CLIMA_ESTADO`.

### Diferencias con el diseño (para el addendum de M1)

- La diferencia 8 de la ola 2 (ΔS con el ganador fijo) ya no existe: rige MC-34 (D46). P33 a P36 quedan respondidas
  por D43 a D46.
- **11.** Una «sin_nasadem» con z_cat se rotula «k3» en el `source` de su política (NAS-16, POL-5), como las coordenadas
  fuera de rango (diferencia 7). El resultado es el mismo: sin coordenadas confirmadas, fuera, y fuera de Q2 por motivo
  (A15). Sólo difiere el rótulo publicado (pendiente de I6, con la 7).
- **12.** `DatosCompetencia` lleva dos campos más que §2.4 del diseño (TIP-17): el diseño no traía el estado del fondo
  en las estaciones, que C (§4.6) y C_est (§4.7) necesitan.
- **13.** La propuesta de la ola 1 ponía `pruebas_m1.txt` como procedencia; con D13 es documento (CEG-19).

### Preguntas para el autor (cierre de la ola 2)

Ninguna bloquea la ola 3. Mientras no haya respuesta, rige lo que dice cada una.

- **P41. El puntaje de la rapidez en MZ de (u, v), antes de M3-4.** (I10.)
  - **Cita.** §5.2, «Viento: RMSE vectorial … y sesgo de la rapidez»; D43, «MZ en el RMSE vectorial y en la rapidez».
  - **Problema.** MZ compara S por macrozona, y el texto no define un S propio de la rapidez.
  - **Propuesta.** Es la implementada: `decision` sólo lee S, y lo calcula I14. Es el puntaje de §5.3 con el MSE horario
    de la rapidez y los pesos de banda del uso (MC-33). Rige ésta.
- **P42. Las clases de las salidas que D3, D13 y D14 no nombran, antes de la ola 4.** (I4, CEG-19.)
  - **Propuesta.**
    - Resumen: `resumen_m1.json`, `costo_m1.json`, `deriva_s6.json`, los resúmenes de la TF de contaminantes en `m6/` y
      los registros de M2a y de M3-4.
    - Insumo: `politicas/politicas_meteo_v1.json`.
    - El informe necesita un nombre de archivo (ver P43).
  - **Mientras tanto.** Quien escribe declara la clase de la propuesta (una salida sin clase fijada sigue la declarada).
    Ninguna se escribe antes de la ola 4.
- **P43. La fracción de §4.6 en el informe, antes de la ola 6.** (I4, CEG-P1.)
  - **Cita.** §4.6, «Si C gana algún uso, esa fracción va en el informe»; D13, un documento va sin números de datos.
  - **Propuesta.** El informe son dos archivos: un documento y un resumen que lleva la fracción.
- **P44. «Deriva, recorte, costo» en el addendum (MC-54), antes de la ola 6.** (I4, CEG-P2.)
  - **Propuesta.** Van por referencia: su ruta y su sha256 en la lista cerrada, más el veredicto («pasa», «mod23»), y
    ningún número de datos en el documento.
- **P45. Un píxel enlazado que no es válido por la regla de tres meses (§4.1), en RR06.** (I7.)
  - **Cita.** D27, «El píxel que `enlaces_productos.parquet` enlaza a su celda; sin enlace, no se compara y se cuenta».
  - **Problema.** Si el píxel enlazado trae tp pero no es válido según §4.1, D27 calla. Sólo cambia las métricas
    descriptivas de §2.6, no la decisión.
  - **Hoy.** Se compara, que es la literal de D27.
  - **Propuesta.** Mantenerlo así. Alternativa: no compararlo y contarlo aparte.
- **P46. Una estación fuera de la grilla en las particiones (D34), antes de M3-4.** (I8, para I3, I13 e I14.)
  - **Cita.** D34, «Sale de la evaluación de todos los candidatos y se cuenta aparte; sigue entrenando A, B y AB»;
    PAR-6 pone de prueba a todas las estaciones que entran.
  - **Problema.** Hay dos maneras de cumplirla, y cambian los pliegues y el entrenamiento de las demás:
    - (a) nunca es estación de prueba en P1 ni en P2: entrena siempre, salvo cuando la sacan por grupo o por
      amortiguador, y no crea amortiguador;
    - (b) sigue de prueba y sólo se descartan sus evaluaciones: en su pliegue no entrena, y saca del entrenamiento a su
      grupo y a las estaciones a ≤ 25 km sin que nadie se evalúe por ella.
  - **Propuesta (de I8).** (a), que cumple «sigue entrenando» en todos los pliegues.
  - **Mientras tanto.** Rige (b), que es PAR-6 tal como está y ya pasó revisión. I14 descarta esas evaluaciones y las
    cuenta. Hace falta la respuesta antes de M3-4.
- **P47. El traslado de 15 m a 2.500 m con la semilla del protocolo, antes de M3-4 (junto con P28).** (I9, HOM-P6.)
  - **Cita.** D42, «la de 2.500 m queda omitida con su motivo hasta P28».
  - **Problema.** Con SEMILLA no hay quiebre de T2b: 15 m mueven QFE ≈ 1,4 hPa, el mayor |D| de T2b es 1,187 hPa y el
    umbral es 1,2 hPa. Sale sólo un quiebre de T2a, «método de reducción».
  - **Por qué P28 no lo arregla.** La enmienda de P28 sólo cambia cómo se clasifica un quiebre de T2b, y aquí no hay
    ninguno. Pasa lo mismo en 4 de las 100 semillas (i = 0, 14, 20 y 30), que son las que faltan en el 96 de 100 que
    midió el revisor con P28.
  - **Propuesta.** Al decidir P28, juzgar los 2.500 m por la tasa sobre el conjunto de semillas fijado (hoy 81 de 100).
    Alternativa: dejar la omisión con este motivo, porque §9 no pide el traslado a 2.500 m.
  - **Mientras tanto.** D42: la prueba queda omitida con su motivo.
  - [Respondida por D52: la alternativa, omitida con un motivo nuevo y la tasa informada (96 de 100). Ver «Tras la ola
    3».]
- **P48. Los valores de las señales y del ruido de S4, al addendum antes de correr S4 (D42).** (I5.)
  - **Cita.** §9, S4: «Un cambio de atmósfera estándar a real en la reducción y uno de horario diurno a 24 h, en
    estaciones a 500, 1.000 y 2.500 m, no se declaran traslado»; D42 manda fijar en el addendum la estructura del ruido
    de z_impl y el ciclo diario, sin dar valores.
  - **Propuesta (SIN-13 y SIN-20).**
    - Reducción: la estación es 10 K más cálida que la atmósfera estándar, y z_impl salta −17,5, −35 y −89 m.
    - Horario: un ciclo diario de 50 m con máximo a las 19 UTC, con su equivalente en T2b (5,7, 5,4 y 4,6 hPa).
    - Ruido: z_impl con ruido blanco horario de 5 m, independiente de T2b y de Ts. Es el que ya había, así que las tasas
      medidas para P28 siguen valiendo.
  - **Alternativa.** Una ΔT por altitud: 10 K a 500 m es una señal exigente.
  - **Mientras tanto.** Rigen esos valores, que son la lectura con señal (la más estricta).

### Pendientes para la ola 3 y siguientes

Reemplazan a los de «Ola 2 cerrada» donde se cruzan; los demás siguen.

- **I12 (`qc_dmc_meteo`, ola 3).**
  - D21: la racha del viento cuenta en FF y en DD.
  - D24: la marca 14, con `politicas.tramos_marca_14(efectivas, codigo)`.
  - D27: `validar_rr06`.
    - Usa `fondo_era5l.pixel_de_lluvia` con `InfoEstacion.celda`, y `lluvia_rr06` sobre la serie continua
      (`incrementos_tp`, `horas_de` y el `pixel_id` del primer mes).
    - Cuenta los «sin_enlace» aparte de los NaN por ventana incompleta.
    - El filtro de reloj y de coordenadas confirmadas es suyo.
  - A15: Q2 por motivo (D36 y D37), nunca por `coordinates.verified`.
  - Aviso de I6: `validar_regla_reloj_dmc` guarda la política en caché por fecha de modificación y tamaño. M3-4 lee una
    sola política por proceso, así que D26 se cumple.
  - Lo de la ola 2 sigue: firmas, D11, D16, la entrada de A4 y la comparación de MC-53 con `aplicar_k4`.
- **I13 (`candidatos`, ola 3).**
  - D22 (a): `tipos.indicadoras_macrozona` del `macrozona_cod` de la celda.
  - A14: C con `puntos_e5l` y C_est con `clima_estado` (D29).
  - D33: `estaticas_nasadem.estandarizar_tpi` es la única estandarización.
  - D34: una estación fuera de la grilla entrena A, B y AB, y no entra en las filas de C ni de C_est (P46).
  - D19 y D40: δ NaN deja la estación fuera de B y de AB.
  - Qué no penaliza el ridge (NUM-9).
- **I14 (`validacion`, ola 3).**
  - D22 (b): en lo crónico, las evaluaciones sin macrozona no entran al nivel neto ni a la anomalía; se cuentan y se
    informan.
  - D43 y P41: S en las filas de macrozona de la rapidez de (u, v), con la fórmula de §5.3, en las tres particiones y
    con las mismas macrozonas que «uv».
  - A13: las cinco macrozonas.
  - D34: sin evaluaciones de las estaciones fuera de la grilla, contadas aparte.
  - TIP-15; `puntaje_par` comparado con `decision._s_del_grupo` (A11).
  - SINCA según A12 revisado.
- **I10 (`decision`).**
  - A13, después de I5 e I14. [Con el cambio de I5, ajustar a la vez `test_decision._agudo_base` y `_con_macrozona`
    en `test_s07_bordes_y_sumandos_de_cada_compuerta`. Ver «Revisión independiente tras el cierre de la ola 2».]
  - Exigir al menos una huella en `decision_json` (hallazgo de integración).
  - Opcional: sumar el conjunto de la decisión a `decision.json`. Hoy se deduce de E1, los motivos y las notas. Si se
    quiere explícito, el coordinador agrega `DecisionGrupo.conjunto` cuando I10 lo llene.
  - Puede usar `esperado["conjunto"]` en vez de `_conjunto_a_mano`.
- **I5 (`sintetico`, a pedido).**
  - A13: las otras cuatro macrozonas. [Y las cinco en la familia «agu», que hoy no trae ninguna. Ver «Revisión
    independiente tras el cierre de la ola 2».]
  - En la grilla, `era5land_enlace` con «propio», «vecino_valido» y «sin_enlace», este último con −1, como
    `construir_grilla.enlazar_pixel_valido`, y algunas celdas de los dos últimos tipos (pedido de I7; hoy sus pruebas
    reescriben la columna en memoria).
  - Las celdas de isla y las de `cod_comuna` 0 y −1 (D20).
  - La anotación de `politica_reloj_sintetica(errata_confirmada=…)` (TIP-13, SIN-5).
  - En `sinca_sintetico`, una estación en los dos manifiestos.
- **I8 (`estaticas_nasadem`), al volver.** Tomar de `tipos` `MotivoExclusion.SIN_NASADEM` y `MOTIVOS_FUERA_DE_Q2`; hasta
  entonces, `test_tipos` vigila la paridad.
- **I6 (`politicas`) o su revisor.** Rotular «sin_coordenadas» las coordenadas fuera de rango y las «sin_nasadem»
  (diferencias 7 y 11), cambiando a la vez la equivalencia de `test_estaticas_nasadem` (NAS-12).
- **I3 (`particiones`).** D34 según la respuesta a P46. Si hace falta el predicado `fuera_de_la_grilla`, va a `tipos`.
- **I11 (`sinca_meteo`).** Citar D47-D50 en sus lecturas. No cambia código: ya sigue la estricta.
- **I9.** Si cambian `series_traslado` o el detector, volver a declarar `TASAS_S4`, en la prueba y en el addendum.
- **I17 (`salidas`, ola 4).**
  - `salidas.escribir(…, referencia=)` pasa la referencia a `vigilar_salida` cuando la clase es documento.
  - La clase se elige con `ceguera.clase_de_ruta`.
  - P42 para las salidas sin clase.
- **I20 (`orquestacion`, ola 5).**
  - A14: `puntos_e5l` y `clima_estado`.
  - D23: `politicas.declaracion_c5(...)` en el registro de M3-4.
  - D37: pasar todas las teselas del conjunto de M0 que tocan la `ventana_k3` de cada estación; un recorte en memoria
    sirve si cubre esas ventanas.
  - D35: llamar a `info_estaciones` una sola vez, con el catálogo completo.
  - D34, D35 y D37: llevar `attrs["declaraciones"]` al registro de M2a.
  - `decision.json` siempre con huellas.
  - Lo de la ola 2 sigue.
- **I22 (ola 6).**
  - Antes de correr S4 (D42, P48), el addendum lleva SIN-13, SIN-20, SIN-21 y SIN-22, HOM-5 corregida, HOM-13 y HOM-14
    con sus tasas. Lleva también los parámetros de S6 (D15) y anota que P33-P36 quedan respondidas por D43-D46 (MC-34
    rige).
  - Según P44: `deriva_s6.json` y `costo_m1.json` por su ruta y su sha256, con el veredicto.
  - `pruebas_m1.txt` lleva primero la línea con la huella del texto, y se vigila con los archivos de pruebas como
    fuentes (CEG-18).
  - La consola usa `ConsolaDocumento`.
  - La frase de §8 sobre la ruta de la carpeta de usuario y la arroba no puede citarse literal, por la regla de
    privacidad.
  - `ErrorC5` también sale de `declaracion_c5`.
- **Al anclar un texto nuevo** (por ejemplo, si se adopta la enmienda de P28), cambiar a la vez `umbrales.SHA_TEXTO_VIGENTE`
  y su copia en `ceguera`. La prueba de paridad lo exige.
- **El C5 de RELOJ** (fuera de M1; D26, POL-1).
  - Su ejecutable escribe `registro_politica_reloj.json` con exactamente las siete claves de POL-1.
  - Con una errata, reemplaza la política en la misma ruta y archiva la original con un sufijo, sin citarla.
- **Huella de `v2/reloj_sinca_v2.py`.** Cambió otra vez (hoy `743fb2e0…`; otro flujo lo edita). Por eso las dos pruebas
  de `test_sinca_meteo` que dependen de ella se omiten con su motivo. Debe quedar anclada antes de M3-4 (§9.4 del
  diseño).

### Cifras al cierre

**Suite:** 519 pruebas: 402 en verde, 117 omitidas y ninguna falla. Antes de la integración eran 515: 397 en verde, 117
omitidas y una falla (`test_tipos.test_motivos_de_exclusion`, por «sin_nasadem»).

**Por archivo de esta ronda:** `test_ceguera` 27, `test_sintetico` 35, `test_politicas` 27, `test_fondo_era5l` 44,
`test_estaticas_nasadem` 19, `test_homogeneidad` 44 (una omitida), `test_decision` 24, `test_tipos` 32 y
`test_integracion` 5.

**Las 117 omitidas:**
- 111 «por implementar»: 109 de los módulos de las olas 3 a 6 y las 2 de S10 de la batería en `test_meteo_combinada`;
- en `test_fijados`, la de huellas de datos (decisión 4);
- en `test_homogeneidad`, el traslado de 15 m a 2.500 m (D42, P47);
- en `test_meteo_combinada`, dos: el cierre de M1 y el índice de §9 (pendientes S1, S6, S8, S9, S14 y S15);
- en `test_sinca_meteo`, las dos de `reloj_sinca_v2.py`.

Sin `__pycache__` nuevo.

**Huellas sha256 del coordinador:**
- `tipos.py` `76385e13f9666337549f018676cdda5c2280efffe56cd2d76cdf617bb4b17add`
- `tests/test_tipos.py` `532790f38f9cefc96de53f2736018de4bb89adc9e45ff8b86c3a6bad91a04f4e`
- `tests/test_integracion.py` `f954e51814057b1976c991f21e34d4f3468d58e9ce053b9ddb63008e3c0ee672`

`tests/test_meteo_combinada.py` y `meteo_combinada.py` no cambiaron.

## Revisión independiente tras el cierre de la ola 2 y sus arreglos (2026-10-26)

Un revisor que no escribió el código halló dos cosas menores y una mutación no equivalente que la suite no detectaba.
Las dos se corrigen en `tests/test_integracion.py`, que es del coordinador. Ningún módulo cambió y no se tocaron archivos
de otros dueños: `sintetico.py`, `decision.py`, `test_sintetico.py` y `test_decision.py` siguen con su huella. Ningún
dato real se abrió. Sin commits.

### Hallazgo 1 [menor]. Las réplicas sintéticas y D46

- **Dónde.** `test_integracion.py`; `sintetico._replicas`, con su ruido de 0,02.
- **Qué pasaba.** La prueba de A11 compara el intervalo de ΔS con el de D46 contado a mano. Sólo lo separa del ganador
  fijo si en algún caso hay réplicas cuyo ganador, dentro de `esperado["conjunto"]`, no es el de la decisión.
  - Hoy los hay gracias al ruido: 29 de 50 réplicas en «empate», entre 9 y 11 en las tres crónicas, y 1 o 2 en
    «finitud», «falla_tf_td», «agudo_nivel» y «falla_ex_hr_media».
  - Pero ninguna prueba vigilaba esa capacidad. Con réplicas sin ruido (S de réplica = S del caso) la suite seguía en
    verde.
- **Corrección (INT-1).** Prueba nueva `test_replicas_separan_d46_del_ganador_fijo`:
  - algún caso debe tener réplicas con otro ganador;
  - el intervalo de D46 debe diferir del del ganador fijo en algún caso × candidato (los dos, contados a mano);
  - las dos cosas deben darse en «empate», donde el S de A es igual al de AB.
- **Lo que no fija.** No fija el valor del ruido, que es de I5. La alternativa del revisor (fijarlo en
  `test_sintetico`) queda para I5, si la quiere.
- `test_decision` sigue protegiendo D46 con sus réplicas hechas a mano.

### Hallazgo 2 [menor]. Grupos sin filas de macrozona (A13 pendiente)

- **Dónde.** `decision` DEC-20; la familia «agu» de `tablas_metricas`.
- **Qué pasaba.** `decision` acepta un grupo sin ninguna fila de macrozona: MZ no rige y nada lo avisa. Ya pasa en
  «agudo_nivel» y «falla_ex_hr_media», dos de los 24 casos que `test_integracion` pasa enteros. La prueba no lo veía.
- **Corrección (INT-2).** No adelanta A13. Prueba nueva `test_mz_en_cada_variable_de_mz_hasta_a13`:
  - Los casos sin filas de macrozona deben ser exactamente los de `_SIN_FILAS_DE_MZ_HASTA_A13` (los dos de «agu»).
    Ninguna variable de MZ debe traer filas, y `compuertas` no debe traer MZ. Así queda a la vista que MZ no rige.
  - En los otros 22 casos, cada variable de MZ del grupo trae filas, sólo de macrozonas de `tipos` (DEC-19).
    `compuertas` debe evaluar MZ, rija o no y con su motivo, en cada variable × macrozona para todo E0.
  - Si un caso nuevo llega sin filas de MZ, la prueba falla.
  - Cuando I5 sume las macrozonas a «agu», la prueba falla hasta que se vacíe el conjunto.
- **Orden de A13** (no cambia): primero I5 e I14, después I10. Al cumplirse:
  - I5 suma las cinco macrozonas también a la familia «agu».
  - Hay que ajustar a la vez `test_decision._agudo_base` y `_con_macrozona` (en
    `test_s07_bordes_y_sumandos_de_cada_compuerta`). Si «agu» trae filas de MZ, `_con_macrozona` las repite y esa prueba
    da error. Se comprobó en memoria.
  - El coordinador vacía `_SIN_FILAS_DE_MZ_HASTA_A13` y exige las de `tipos.MACROZONAS` en cada variable de MZ, en P1,
    P2 y el agregado.

### Mutaciones

Se aplicaron en memoria, sin tocar el disco, cada una en un proceso aparte. Se corrieron `test_integracion`,
`test_sintetico`, `test_decision` y `test_tipos` (98 pruebas).

| Mutación | Antes del arreglo | Después |
|---|---|---|
| `_replicas` sin ruido | Nadie la detecta | La detecta INT-1 (`test_replicas_separan_d46_del_ganador_fijo`) |
| Ganador fijo: `_intervalos` con el conjunto {ganador} | Detectada: la prueba de A11 en 7 casos, y 3 pruebas de `test_decision` | Igual |
| `_replicas` sin ruido y ganador fijo | Sólo `test_decision` (S7 y S16, réplicas a mano); la prueba de A11 ya no la ve | Además INT-1 |
| Desempate al revés al elegir el ganador de cada réplica (`_intervalos`) | Nadie la detecta | Nadie la detecta: es equivalente, no lleva prueba |
| «ganador_claro» sin filas de macrozona | `test_sintetico` y `test_decision` | Además INT-2 |
| Familia «agu» con filas de MZ (simula el cambio de I5 en A13) | `test_decision` (error por filas repetidas) | Además INT-2 |
| `decision._mz` sin evaluar | Detectada | Además INT-2, en 22 casos |

Sobre el desempate al revés: sólo elige entre S iguales, así que S_g(r),r es siempre el mínimo del conjunto y el
intervalo no cambia (DEC-12 lo dice).

### Lecturas nuevas (en el encabezado de `test_integracion`; van al addendum de M1)

- **INT-1.** Las réplicas sintéticas deben separar D46 del ganador fijo.
- **INT-2.** Los casos sin filas de macrozona quedan declarados hasta A13.

### Cifras

**Suite:** 521 pruebas: 404 en verde, 117 omitidas y ninguna falla. Antes eran 519: 402 en verde y las mismas 117
omitidas. Sin `__pycache__` nuevo (siguen los 7 de otros flujos). `test_integracion` tiene 7 pruebas (antes 5).

**Huellas sha256:**
- `tests/test_integracion.py` `1ff9181e8657d688f871d80794381723f363719206fb99998b40a739c318aba1`
- Sin cambios:
  - `sintetico.py` `f87148e775c52243a288c2ca045806f4b567ecbd0ebf4e868dad68849fd3fe0e`
  - `decision.py` `d2d1891f0a2676af0bed79a7151a3e74770e830e1d0e94d3d46fde3667d9074e`
  - `tests/test_sintetico.py` `b23c42ba0dca5e09ff757f3dad03fda0a2a9b431cb5c62d09dc5e6cd0287989f`
  - `tests/test_decision.py` `2cf505d814e31e96131c04327aeb8750e18dbd840a7ad9f80c6e847899e552fc`

## Ola 3 cerrada (2026-10-26)

Los tres módulos de la ola 3 quedaron implementados, cada uno por su dueño, con sus lecturas en el encabezado. Cada uno
pasó por un revisor que no lo escribió (contraste con el v2.2, el diseño y D1-D50, y mutaciones en copias en memoria) y
por la corrección de su dueño; después, la integración del coordinador. Nada se escribió fuera de `meteo_combinada/`;
`reloj_dmc/`, el código fijado y `v2/` no se tocaron; ningún dato real se abrió (ni DMC, ni el reloj, ni SINCA,
NASADEM, ERA5L o GHS-POP reales). Sin commits.

**Entregas de §6 del diseño:** S1, S2 (la parte de `qc`), S5 (la parte de los candidatos), S12 (CD), S15 (abortos) y S7
(soporte). Todas corren y ninguna queda omitida. Además, los hitos de integración 1 y 2 de §6 (abajo).

### Qué entregó cada dueño (después de la revisión)

| Dueño | Módulo | Pruebas | Lecturas | Revisión → corrección |
|---|---|---|---|---|
| I12 | `qc_dmc_meteo.py` | 57 en verde, ninguna omitida (el esqueleto tenía 41 «por implementar») | QC-1 a QC-25 | Sin bloqueantes; un hallazgo mayor (las pruebas de las marcas 13 y 18 no fijaban siete partes de la regla) y cinco menores (marca 9 bajo 0 °C, dos bordes, aserciones de las marcas 16, 21 y 14, QC-21 frente al código en «s/p» con espacios, y el paso 1 sin cotejar `artefactos_evaluados`). Corregidos: cinco en las pruebas y uno en el código (`normalizar_artefacto(…, *, artefactos)`). De 23 mutaciones, 22 detectadas; la otra es equivalente |
| I13 | `candidatos.py` | 28 en verde, ninguna omitida (10 «por implementar») | CAN-1 a CAN-17 | Sin bloqueantes ni mayores; diez menores (cuatro lecturas sin pregunta, dos de robustez: un insumo de C que falta ya no se esconde como «sin soporte» y C_est sólo en lo crónico; cuatro huecos de pruebas). Corregidos; todas las mutaciones detectadas |
| I14 | `validacion.py` | 50 en verde, ninguna omitida (9 «por implementar») | VAL-1 a VAL-21 | Un mayor (un candidato fuera de E0 por finitud hacía fallar `estratos` y `remuestreo`; queda en VAL-15 como exigencia a I20 y en la pregunta P76) y ocho menores (borde del aviso SINCA, CD sin la media del mes, bordes de los mínimos del Anexo A, horas emparejadas, lo crónico y agudo SINCA, descriptivos, E0 ajeno, réplica N). Corregidos; 31 mutaciones detectadas y una equivalente |

Lo principal de cada entrega:
- **I12.** Paso 1 por artefacto (sólo captura `ValueError` y `TypeError`; origen «datos» o «regla» como la comprobación 7
  de RELOJ; motivo por el texto del error del código fijado; el artefacto debe estar en `artefactos_evaluados` de su
  estación). Paso 2, todas las reglas de §2.4 salvo la 14, en el orden de MC-24 con D7, con las derivadas aparte. Pasos
  3 y 4: la entrada de A4, K4, marcas 1, 16 y 21 (MC-53 probado con `cargar_dmc` real) y la marca 14 con los tramos de
  la efectiva (D24). Conteos Q1 y Q1z (EMC1-1, D11, D21), Q2 por motivo (EMC1-3, A15, D10, D36, D37), sin macrozona
  sólo en lo nacional (D9, D16), Q3, la lista descriptiva y `resumen_qc`. RR06 por el píxel enlazado (D27). Una
  estación de 10 años pasa los pasos 2 a 4 en ≈ 1,2 s.
- **I13.** Núcleo (§4.2), A (§4.3, MC-41, D19), B y AB (§4.4, §4.5, D40), C y C_est (§4.6, §4.7, D22 (a), D29, D33,
  D34, MC-05, MC-44, MC-45), selección anidada (§4.9, MC-43) y predicción por lotes de un mes. S5: A recupera b con RMSE
  0,0996 K; una perturbación de la estación de prueba, su grupo y su amortiguador no cambia nada bit a bit.
- **I14.** Métricas de §5.2 y §5.8, bandas, π^pob y π^mon (MC-09), S con la unión de bandas, S_par (A11, comparado bit a
  bit con `decision`), remuestreo (MC-34, D46), estratos con las cinco macrozonas (A13, D43) y la regla de soporte por
  partición (MC-61), descriptivos, réplica con N y SINCA (A12 revisado, D47-D50).

**Huellas sha256 de lo entregado** (sin cambios desde la corrección):
- `qc_dmc_meteo.py` `0022d145ce86aaf185bfd1cfc56ff9202b3d4f42b46b8751e67206c22e11bd66`; `tests/test_qc_dmc_meteo.py`
  `dd1f355a4239f8fbe2b78f2fa1470363013f5afd3d990080b3bf758566159844`.
- `candidatos.py` `9060755526b4f3f400467048b143f922e375d69bdfe30bd3afe568e31d26853c`; `tests/test_candidatos.py`
  `f5eb85834e317b6c76ea6729d109b25d5fdfcdae182088f5b44c708c9f4a69e7`.
- `validacion.py` `86b0e2b89344dcd38fa28a100257f03f404a8f8e4b5eaa740fa3979d02dbc70c`; `tests/test_validacion.py`
  `2474c59f2dc20ccebfa5e2cb244044ceee63fffcf1557add9866ecf37d28c328`.

### Integración del coordinador

1. **`tipos.py`** (TIP-19 a TIP-24; lecturas de implementación, ninguna cambia una regla):
   - **TIP-19** (pedido de I14). `Estrato` suma «conjunto», «altitud», «periodo», «tipo», «propietario» y «omm», en el
     orden de `validacion.ESTRATOS`, y `VALOR_ESTRATO_OMM` («con_indicativo_omm»). `decision` sigue leyendo sólo
     «nacional» y «macrozona». Los rótulos de la tabla SINCA («red», «tercil_tpi») quedan en `validacion`.
   - **TIP-20** (pedidos de I13 e I14; P46). `fuera_de_la_grilla(info)`, el predicado de
     `estaticas_nasadem.fuera_de_la_grilla`; `test_tipos` compara las tres copias con él.
   - **TIP-21** (pedidos de I12, I13 e I14). En `ESQUEMAS`, los publicados: `ESQUEMA_SOPORTE_PUB`,
     `ESQUEMA_DESCRIPTIVOS_PUB` y `ESQUEMA_SINCA_PUB` (pasan la guarda de S7 como métrica). En `ESQUEMAS_EN_MEMORIA`, los
     que nunca se escriben: `ESQUEMA_CONTEOS_QC` (de `COLUMNAS_CONTEO`) y `ESQUEMA_PREDICCION` (de
     `COLUMNAS_PREDICCION`; R nunca se guarda, y no pasa ninguna clase con vocabulario).
   - **TIP-22** (PED-2 de I13). `ESQUEMA_ESTATICAS_CELDA_C` = `ESQUEMA_ESTATICAS_CELDA` + `COLUMNA_Z_E5L` («z_e5l», f8, m):
     Σ w_i z_E5L,i con el operador de la celda, que agrega `orquestacion` en M2a antes de escribir
     `estaticas/celdas.parquet`. `ESQUEMA_ESTATICAS_CELDA` no cambia: es la salida de `estaticas_nasadem` y de su
     prueba. Queda fuera de `ESQUEMAS` hasta que I4 la sume a `test_ceguera.test_s07_esquemas_de_tipos` (sólo pasa
     como insumo, como `ze5l`).
   - **TIP-23** (PED-1 y PED-4 de I13). `VecinosNucleo` suma `codigos`, `grupos` y `grupo_est` (los de
     `candidatos.VecinosEntrenamiento`, que los redeclara sin conflicto); `SumasC` en `tipos`, copia con paridad de
     campos; `DatosCompetencia.filas_c` = {«C» o «C_est»: {variable: {código: SumasC}}} y `estaticos` es
     `ESQUEMA_ESTATICAS_CELDA_C`. **Decisión de interfaz (D33, PED-1):** la fórmula de `estandarizar_tpi` sigue copiada
     en `candidatos` con su prueba de paridad; no se suma la dependencia a `DEPENDENCIAS`.
   - **TIP-24** (pedido de I12; anotado en A6). Desde la marca 14, `tramo` lleva el id de la política efectiva.
2. **`test_tipos`: 38 en verde (32).** Clase nueva `PruebasOla3`, seis pruebas: esquemas iguales a los de sus módulos
   (columnas, tipos y versión); los estáticos de C con `z_e5l` al final; los esquemas nuevos frente a la guarda de S7;
   los estratos descriptivos; `fuera_de_la_grilla` igual en sus cuatro copias (excluida × celda); `VecinosNucleo` y
   `SumasC` con los campos de `candidatos`.
3. **`test_meteo_combinada`:** salen de `EN_CURSO` `test_qc_dmc_meteo.py`, `test_candidatos.py` y `test_validacion.py`.
   El índice de §9 ya no informa S1 ni S15: quedan pendientes S6 (ola 4), S8, S9 y S14 (ola 5).
4. **`test_integracion`: 17 en verde (7).** Lecturas nuevas INT-3 a INT-8 en su encabezado.
   - **Hito 1** (`PruebasHito1`, 5 pruebas, ≈ 3,5 s): una estación de 3 meses horarios de punta a punta con el
     descargador, el adaptador, `dmc_features` y el validador de RELOJ reales (cliente falso), la política y el registro
     de C5 sintéticos leídos por `politicas`, `info_estaciones` con una tesela NASADEM plana, el paso 1 con
     `id_artefacto` = índice en `artefactos_evaluados`, `qc_estacion` y `tabla_ancha`. Un centinela de Ts (−40,0)
     invalida Ts, Td y HR de su fila y nada más salta; K4 no halla quiebres; el tramo es el de la efectiva. Una segunda
     estación con DD 990 queda «no normalizable» (datos), `unir_largas` la rechaza y la única alarma es Q3 (25 %), que
     detiene. `resumen_qc` y la validación de RR06 por el píxel enlazado pasan la guarda de su clase. Los residuos
     (A3) salen exactos en float32, con NaN en la hora del centinela.
   - **INT-3** (la tabla larga a escala): `_larga_vectorizada` es la salida de `cargar_dmc` bit a bit (columnas,
     tipos y valores) y da la misma tabla ancha. Con ella el hito 2 evita 720 artefactos.
   - **Hito 2** (`PruebasHito2`, 5 pruebas, ≈ 31 s): 30 estaciones a ≈ 22 km (un grupo de dos, 17 en «centro», 11 en
     «sur», una con `cod_comuna` 0 y una fuera de la grilla), 2010-2011 horario, 10 pliegues de P1 y 4 de P2. El
     envoltorio, K4 y la marca 14 en las 30; residuos; `DatosCompetencia`; selección anidada de A, B, AB y C con el
     objetivo armado con `validacion` (INT-5) y predicción; producto con `fondo_era5l.producto_desde`; 238 evaluaciones
     de p (la estación sin celda sin C, descartada y contada por `validacion`); bandas, π^pob, π^mon y π ambiental;
     `estratos` (las cinco macrozonas, MZ en «centro» y «sur»), el remuestreo (1.999 réplicas), `tabla_descriptivos`,
     `tabla_bandas`, `fracciones_sin_soporte` y `replica_n`; `decidir_combinacion` y `decision_json`, con las guardas.
     Los cuatro candidatos bajan el MSE de p frente al fondo sin corregir en cada evaluación; A recupera b de T con la
     cadena real de qc con RMSE 0,106 K (< 0,3). El S publicado de cada candidato y partición coincide con el contado
     aparte (VAL-10), y el intervalo de ΔS con D46 contado a mano. En esta red gana C (E1 = {C}; A, B y AB fallan MZ):
     el sesgo sintético es lineal en la latitud, que es un estático de C.
   - **Sin desajustes de interfaz:** las dos cadenas corrieron sin tocar ningún módulo. Sólo hizo falta lo que ya
     estaba pedido: `z_e5l` en los estáticos (TIP-22), las horas emparejadas comunes (VAL-15) y el objetivo de la
     selección (PED-3).
   - **Mutaciones en memoria** (un proceso por mutación, sin tocar el disco), todas detectadas por los hitos: el
     producto sin R; los residuos sin la validez de la tabla ancha; el nudo mal convertido en la tabla larga; S del
     agregado tomado de P1 (al principio sobrevivía: la prueba comparaba la decisión con la tabla publicada, que es su
     propia entrada; se agregó el S contado aparte); sin D34; y el intervalo de ΔS con el ganador fijo. [Corrección
     tras el crítico de la ola 3: el intervalo con el ganador fijo no lo veían los hitos, sólo la prueba de A11 y
     `test_decision`; desde INT-9 lo ve también el hito 2. Las mutaciones quedan descritas con su cambio exacto en
     «Tras la ola 3».]
5. **Comprobado:** detector de literales en verde (`TOLERADOS` vacío), grafo por capas, escritura sólo en `salidas`,
   `entorno` y `sintetico`, privacidad (ninguna ruta de la carpeta de usuario ni arroba fuera de decoradores), ningún
   `__pycache__` nuevo (siguen los 7 de otros flujos).

### Acuerdos nuevos

- **A16. El objetivo de la selección (PED-3; I13, I14 e I20).** `candidatos.seleccionar(…, *, objetivo, recorte,
  hiper_a=None)` recibe `objetivo(internos, sumas, *, candidato, variable, uso)`: `sumas` es {pliegue interno:
  {código: (sse, n)}} y `variable` es el rótulo de `tipos.VariableMetrica` («uv» para u y v juntos). Lo arma I20 con
  `validacion` como `_objetivo_de_validacion` de `test_integracion` (INT-5): MSE_e = sse/n, banda de cada estación
  interna con `particiones.distancia_entrenamiento_km` en el entrenamiento de su interno y `validacion.bandas`, y un
  solo `validacion.puntaje` con el π del uso (P62). `recorte` lo fija el addendum; en AB se pasa `hiper_a` (el de A).
- **A17. El paso 1 en `orquestacion` (I12 → I20).** `normalizar_artefacto(…, *, id_artefacto, artefactos)`:
  `id_artefacto` es el índice del artefacto en la lista `artefactos_evaluados` publicada (el mapa no guarda el orden)
  y `artefactos` el mapa sha256 → código de `politicas.leer_politica_reloj`. Sólo se normalizan los manifiestos con
  artefacto. Una estación sin ningún artefacto normalizable no pasa al envoltorio (`unir_largas` lanza `ValueError`):
  cuenta en Q3 y en `no_normalizables` y queda fuera.
- **A18. Las evaluaciones (I14 → I20).** Por (uso, variable), las horas emparejadas son las mismas para todos los
  candidatos del uso que predicen en la estación (INT-6, VAL-15); `fila_evaluacion` con `frac_sin_soporte` medida en
  esas horas (NaN en C y C_est); `filas_descriptivas` de cada evaluación; `completar_cronico` después de las crónicas;
  evaluaciones aparte por período (2000-2009 y 2010-2026) para el estrato «periodo»; `bandas_de_pliegues` con las
  horas válidas por clave; `replica_n(…, decidir=decision.decidir_combinacion)`; `entorno` importado antes que
  `validacion` (VAL-3). Las de una estación fuera de la grilla, sin C: `validacion` las descarta y las cuenta.

### Cambios de firma (para el anexo de firmas)

- **Incompatibles** (sin valor por omisión):
  - `qc_dmc_meteo`: `normalizar_artefacto(…, *, id_artefacto, artefactos)`, `qc_meteo_combinada(…, *, k2, politicas)`,
    `marca_14(…, *, tramos)`, `aplicar_k4(tabla, resultado, umbrales)` y `resumen_qc(…, *, denominadores, lista,
    umbrales)`.
  - `candidatos`: `climatologia_a(…, *, codigo, variable)`, `seleccionar(…, *, objetivo, recorte, hiper_a=None)`,
    `predecir_prueba(…, *, umbrales)` y `filas_c(…, *, infos, climatologico=False)`; `vecinos` devuelve
    `VecinosEntrenamiento`.
  - `validacion`: `estratos(…, *, uso, grupo, banda, pi, periodos=None)`, `remuestreo(…, *, infos, uso, grupo, banda,
    pi, e0)`, `replica_n(…, *, decidir)`; en `pi_monitores`, `panel_red2` es {contaminante: {"tabla", "sha256"}};
    `anual_neto` y `anomalia_interanual` reciben {año: ε} y {año: media de su macrozona}.
  - `tipos`: `VecinosNucleo` con tres campos más (sólo `candidatos` lo construye).
- **Más estrictos:** `candidatos` da `ErrorCandidatos` ante un insumo de C que falta (celda sin estáticos, sin fondo o
  sin clima) y rechaza C_est fuera de lo crónico; `validacion` comprueba E0 tal como llega y rechaza bloques de
  estaciones excluidas o desconocidas.
- **Aditivos:**
  - `qc_dmc_meteo`: `unir_largas`, `entrada_k4`, `k4_estacion`, `qc_estacion`, `sumas_lluvia_rr06`, `conteos_estacion`,
    `conteos_artefactos`, `tabla_no_normalizables`, `lista_descriptiva`, `COLUMNAS_CONTEO` y las constantes de claves;
    `qc_meteo_combinada` acepta la lista de `ResultadoArtefacto`.
  - `candidatos`: `residuos_estacion`, `climatologias_a`, `sumas_nucleo`, `puntos_de_estaciones`, `estado_c`,
    `estado_c_est`, `diseno_estandarizado`, `matriz_q`, `fuera_de_rango_c`, `SumasC`, `ErrorCandidatos`,
    `SinSeleccion`, las constantes de columnas; `diseno_c(…, umbrales=None, …)`.
  - `validacion`: `validacion_sinca(…, *, ganadores, e0, macrozonas, zona)`, `pi_uso`, `dia_civil`, `medias_diarias`,
    `evaluacion`, `fila_evaluacion`, `tabla_evaluaciones`, `completar_cronico`, `bandas_de_pliegues`,
    `fracciones_sin_soporte`, `tabla_bandas`, `descriptivos_de`, `filas_descriptivas`, `tabla_descriptivos` y ayudas.
  - `tipos`: `Estrato` (seis valores), `VALOR_ESTRATO_OMM`, `fuera_de_la_grilla`, `ESQUEMA_SOPORTE_PUB`,
    `ESQUEMA_DESCRIPTIVOS_PUB`, `ESQUEMA_SINCA_PUB`, `ESQUEMA_ESTATICAS_CELDA_C`, `COLUMNA_Z_E5L`, `ESQUEMA_CONTEOS_QC`,
    `ESQUEMA_PREDICCION`, `ESQUEMAS_EN_MEMORIA` y `SumasC`.

### Lecturas nuevas (en el encabezado de cada módulo; van al addendum de M1)

- **QC-1 a QC-25** (`qc_dmc_meteo`): el paso 1 y su captura; origen y motivo del aborto; la tabla intermedia; dos
  etiquetas con la misma hora UTC fuera y contadas (P49); diferencias decimales a 10⁻⁹; la hora válida y las excluidas
  también por las reglas; dónde va cada marca (D11, D21); el orden (MC-24, D7); rachas (P50, P51), picos y saltos, Td y
  HR (P52, P53), derivadas, viento, aire seco y error grueso; la entrada y la retirada de K4; la marca 14 y el tramo de
  la efectiva (TIP-24); RR06; conteos (P54), alarmas, lista descriptiva y resumen.
- **CAN-1 a CAN-17** (`candidatos`): vecinos (P56) y pesos de grupo; el campo; la climatología de A y su paso en el
  tiempo (P64); B y AB (P63, P67); la tabla de residuos; el diseño de C (P58, P59) y su estado; la estandarización;
  el ridge (NUM-9: sólo la constante sin penalizar; P65); las filas de C; la selección (P57, P60, P62, P66); la
  predicción; los errores; el área de aplicabilidad.
- **VAL-1 a VAL-21** (`validacion`): rótulos; horas emparejadas (P76); día civil; agudo; crónico (P68, P77); CD; EX
  (P71); bandas; π; S y la unión de bandas (P69, P70); S_par; remuestreo; regla de soporte; conteos; las mismas
  evaluaciones para todos; estaciones; estratos descriptivos (P74); réplica con N; SINCA (P72, P73); descriptivos
  (P75).
- **TIP-19 a TIP-24** (coordinador) e **INT-3 a INT-8** (`test_integracion`), arriba.

### Diferencias con el diseño (para el addendum de M1)

- **14.** `seleccionar` recibe el objetivo como función (A16): §3 del diseño lo daba sin ella, pero `candidatos` no
  puede importar `validacion` (grafo de §1), y los pesos del uso son de §5.3.
- **15.** `DatosCompetencia.estaticos` es `ESQUEMA_ESTATICAS_CELDA_C`, con `z_e5l` (TIP-22): §2.4 del diseño traía
  `ESQUEMA_ESTATICAS_CELDA`, que no tiene la altitud del fondo que pide Δz (§4.6).
- **16.** `VecinosNucleo` lleva tres campos más que §2.4 del diseño (TIP-23), los de los pesos de grupo (§2.5).
- **17.** Cuatro esquemas que §2.3 del diseño no traía: los tres publicados de TIP-21 y los dos en memoria; y `Estrato`
  con los descriptivos de §5.5 (TIP-19).
- **18.** La columna `tramo` de la tabla ancha lleva el id de la política efectiva desde la marca 14 (TIP-24); A6 decía
  el de lectura.
- **19.** El paso 1 recibe además el índice del artefacto y el mapa de `artefactos_evaluados` (A17): §3 del diseño no
  los traía y sin ellos no se puede cumplir «por artefacto de `artefactos_evaluados`» (§2.1).

### Preguntas para el autor (cierre de la ola 3)

Ninguna bloquea la ola 4; todas hacen falta antes de M3-4 salvo que se diga otra cosa. Mientras no haya respuesta,
rige lo que dice cada una (la lectura más estricta o, si el texto no calla, la literal).

**Control de calidad (I12 y su revisor).**
- **P49. Misma hora UTC en dos artefactos (QC-P1).**
  - **Cita.** §2.1: «una hora repetida o no HH:00» aborta el artefacto.
  - **Problema.** Un cambio de −240 a −180 justo en el borde de un mes da dos etiquetas con la misma hora UTC en
    artefactos distintos; ninguno aborta y el texto calla.
  - **Rige y se propone.** Las dos quedan fuera de la tabla ancha, sin marca, y se cuentan («colision_utc», QC-6).
- **P50. Rachas de HR entre 101 y 103 (QC-P2).**
  - **Cita.** §2.4, marca 5: «HR < 100 idéntica ≥ 12 h; HR = 100 ≥ 48 h».
  - **Problema.** Ninguna de las dos cubre 100 < HR ≤ 103, que la regla de rango admite.
  - **Rige y se propone.** 12 h para todo valor distinto de 100.
- **P51. «Td idéntico ≥ 12 h, sin contar las horas con HR = 100» (QC-P3).**
  - **Problema.** Esas horas pueden salir de la serie, cortarla o descontarse del lapso.
  - **Rige y se propone.** Salen de la serie y no la cortan si el hueco queda en ≤ 3 h.
- **P52. «Sin Td» en la marca 10 (QC-P4).**
  - **Problema.** Puede ser sin valor en la fuente o también con un Td presente pero inválido.
  - **Rige y se propone.** Sólo sin valor en la fuente.
- **P53. «Bajo 0 °C» en la marca 9 (QC-P5).**
  - **Problema.** Puede ser Ts < 0 o Td < 0.
  - **Rige y se propone.** Ts < 0.
- **P54. Q1 con marcas sobre horas ya quitadas (QC-P6).**
  - **Cita.** §2.7, Q1: «una marca invalidante … quita más del 10 %»; MC-24 (cada regla mira sólo lo que sigue válido).
  - **Problema.** Una regla escribe su marca también en variables que otra ya había quitado; Q1 puede contarla o no.
  - **Rige y se propone.** Q1 cuenta toda hora de su denominador que lleva la marca. Alternativa: sólo la primera marca
    que quita la hora.
- **P55. Una etiqueta repetida en dos artefactos de la estación (revisor de I12).**
  - **Cita.** §2.1: «una hora repetida o no HH:00» aborta el artefacto; nada dice de una etiqueta (`timestamp_source`)
    que aparece en dos artefactos.
  - **Problema.** Hoy `qc_meteo_combinada` lanza `ValueError` («la tabla larga repite una etiqueta y variable») y M3-4
    se detiene. El descargador escribe un artefacto por mes de etiqueta, así que sólo pasaría con una descarga dañada.
  - **Rige y se propone.** Detener (del lado seguro: es un defecto de la descarga, que el reloj debió ver).
    Alternativa: las dos fuera y contadas, como P49.

**Candidatos (I13 y su revisor).**
- **P56. La lista de vecinos (P-CAN-1).**
  - **Cita.** §4.2: «s está entre las 30 estaciones de entrenamiento más cercanas … La lista de vecinos es fija por
    punto y la disponibilidad se aplica hora a hora».
  - **Problema.** Una estación sin ningún q (sin la variable, δ NaN o nunca calificada en A) ocupa uno de los 30
    lugares; pesa sobre todo en p.
  - **Rige.** La literal. **Propuesta.** Armar la lista, por candidato y variable, sólo con las estaciones con algún q.
- **P57. El objetivo de A en la selección (P-CAN-2).**
  - **Cita.** §4.9: «el RMSE horario de lo que predice cada candidato (r̄ en A; …)».
  - **Problema.** A se interpola entre meses (MC-41), pero el texto no dice si el objetivo r̄ también.
  - **Rige y se propone.** r̄ del mes y la hora UTC de cada hora, sin interpolar, como MC-42.
- **P58. La z de C en salud (P-CAN-3).**
  - **Cita.** §4.6: «z y Δz = z_celda − z_E5L»; §3: en salud, z es la media ponderada por la población.
  - **Problema.** No dice si la z de C es la del uso ni qué es z_E5L en una celda.
  - **Rige y se propone.** `z_media` en todos los usos y z_E5L = Σ w_i z_E5L,i (TIP-22). Alternativa: la z del uso,
    con un C por uso.
- **P59. Estandarización e interacciones de C (P-CAN-4).**
  - **Cita.** §4.6: «predictores estandarizados en el entrenamiento», «TPI = 0 tras estandarizar», «cada estático por…»,
    «el armónico anual de primer orden».
  - **Rige y se propone.** Se estandarizan los predictores base con los pesos de las filas y las interacciones son sus
    productos; «cada estático» excluye las indicadoras; el armónico de primer orden es el par seno-coseno; 156 columnas.
- **P60. D34 en la selección (P-CAN-5).**
  - **Cita.** D34: «Sale de la evaluación de todos los candidatos».
  - **Problema.** No dice si la estación fuera de la grilla sale también del objetivo de la selección.
  - **Rige y se propone.** Sale (la estricta).
- **P61. Los pliegues internos de producción (P-CAN-6).**
  - **Cita.** §4.9: «los hiperparámetros se vuelven a elegir con el mismo procedimiento sobre todas las estaciones».
  - **Problema.** No dice si los internos de producción llevan el amortiguador de 25 km.
  - **Propuesta.** Sí, como en P2: I20 arma el pliegue de producción con `Particion.P2`.
- **P62. La agregación de los cinco pliegues internos (P-CAN-7).**
  - **Cita.** §4.9: «con los pesos del uso (§5.3) calculados en el pliegue interno … se agregan con los pesos de cada
    uso».
  - **Problema.** No dice cómo se juntan los cinco internos ni cómo se unen las bandas chicas de cada uno.
  - **Rige y se propone.** Un solo S sobre todas las estaciones de prueba internas, con la banda de cada una medida en
    su interno, el π del uso y la unión de bandas de §5.3 sobre ese conjunto (A16, INT-5).
- **P63. La interpolación de B (P-CAN-8).**
  - **Cita.** §4.4: «sin reporte en u pero sí reportes válidos consecutivos (≤ 3 h) a ambos lados».
  - **Rige y se propone.** La estricta: una hora con reporte inválido no se interpola y un reporte inválido entre dos
    válidos corta la interpolación.
- **P64. «≥ 2 años distintos» en la climatología de A (revisor de I13).**
  - **Cita.** §4.3: «≥ 60 valores de ≥ 2 años distintos».
  - **Problema.** Con el año calendario (CAN-4), una sola temporada de verano (diciembre de un año, enero y febrero del
    siguiente) da dos años en la ventana de diciembre y en la de enero; el revisor lo comprobó.
  - **Rige.** La literal (año calendario de cada hora). **Propuesta.** Contar temporadas: el año de cada valor es el de
    la ocurrencia del mes m de la ventana a la que pertenece (diciembre de 2010 cuenta con enero de 2011 en la ventana
    de enero), que exige dos temporadas.
- **P65. La escala de α del ridge de C (revisor de I13).**
  - **Cita.** §4.6: «Regresión ridge … Penalización: α ∈ {0,1; 1; 10; 100; 1.000}, por selección anidada».
  - **Problema.** Hoy α va sobre las sumas ponderadas sin normalizar (X'WX), así que la misma α encoge distinto según el
    tamaño del entrenamiento; en la red de prueba, de α = 0,1 a 1.000 la predicción cambia 0,16 K.
  - **Rige.** Las sumas sin normalizar (CAN-12). **Propuesta.** Mantenerlo, porque α se elige por selección anidada en
    cada pliegue. Alternativa: α sobre X'WX/Σw.
- **P66. Un solo α para u y v en C (revisor de I13).**
  - **Cita.** §4.6: «Regresión ridge por variable»; MC-43 (u y v eligen juntos sus hiperparámetros con el error
    vectorial).
  - **Problema.** MC-43 nombra el núcleo; no dice si el α de C también es conjunto.
  - **Rige y se propone.** Conjunto, por analogía con MC-43 (el grupo (u, v) tiene un ganador). Alternativa: un α por
    variable.
- **P67. La parte A de AB frente a D40 (revisor de I13).**
  - **Cita.** D40: «sin ninguna, δ = NaN y la estación no entra en B ni en AB»; §4.5: «A usa sus hiperparámetros ya
    elegidos» y «Sólo entran a Φ′ las estaciones que entran en A».
  - **Problema.** Una estación con δ NaN sigue en A; D40 no dice si sale también de la parte A de AB.
  - **Rige y se propone.** Sale sólo de Φ′: la parte A de AB es A tal cual (CAN-7).

**Validación (I14 y su revisor).**
- **P68. El centrado del nivel neto crónico (VAL-P1).**
  - **Cita.** §5.2: «Se resta a ε su media sobre las evaluaciones de la misma macrozona × año».
  - **Problema.** Cada estación da dos evaluaciones (P1 y P2); cambia el S crónico y MZ.
  - **Rige.** La literal, P1 y P2 juntas. **Propuesta.** Centrar dentro de cada partición.
- **P69. La agregación del nivel agudo y de la anomalía crónica (VAL-P2).**
  - **Cita.** §5.2, «CD y EX se agregan como S»; §6.1, «Nivel (agudo): RMSE de las medias diarias ≤ 1,15 · mín».
  - **Rige y se propone.** Como S, con π y la unión de bandas. Alternativa: RMSE sin pesos.
- **P70. El orden de la unión de bandas chicas (VAL-P3).**
  - **Cita.** §5.3: «Una banda con < 10 evaluaciones se une con la contigua más cercana a 0».
  - **Problema.** Con 12, 5, 6 y 12 evaluaciones, desde 0 quedan [23, 12]; desde lejos, [12, 11, 12].
  - **Rige y se propone.** Desde la banda más cercana a 0.
- **P71. El cuantil de §5.8 (VAL-P4).**
  - **Cita.** §5.8: «Q95(Tmáx diaria del producto) − Q95(Tmáx observada)».
  - **Rige y se propone.** Sin interpolar, como MC-48. Alternativa: interpolación lineal.
- **P72. «El segundo» del aviso SINCA (VAL-P5).**
  - **Cita.** §5.6: «si el ganador de un uso es peor que el segundo en más de 15 % en esta red».
  - **Rige (la más estricta) y se propone confirmarla.** El menor de los demás de E0 en la red, en la celda o en el
    punto. Alternativa: el segundo de la decisión, sólo en la celda.
- **P73. El resumen de la red SINCA y el TPI de los terciles (VAL-P6).**
  - **Cita.** §5.6: «métricas de §5.2 en la celda y en el punto, por terciles de TPI».
  - **Rige.** Cada estación pesa igual y el TPI lo pasa quien llama. **Propuesta.** Dos estratificaciones, con el TPI de
    1 y de 5 km. Es descriptiva.
- **P74. La macrozona en las variables que no son de MZ (VAL-P7).**
  - **Cita.** §5.5: «Estratos: macrozona; conjunto…», sin restringir variables.
  - **Problema.** Por DEC-2 no salen por macrozona el EX de Td ambiental, el CD de T y HR del agudo ni el EX de
    `temp_media` del crónico.
  - **Rige.** La omisión, declarada en `attrs["declaraciones"]["variables_sin_estrato_macrozona"]`. **Propuesta.** (a) un
    rótulo descriptivo aparte, que `decision` no lea, porque sigue la letra. Alternativa (b): dejar la omisión declarada
    en el addendum.
- **P75. Los descriptivos de §5.8 (VAL-P8).**
  - **Cita.** §5.8: «el sesgo condicional en los días observados sobre el Q95 o bajo el Q05, y el acierto de días».
  - **Rige y se propone.** En la serie de su EX (en T y Td, el máximo diario para el Q95 y el acierto y el mínimo para
    el Q05; en la rapidez, el máximo diario; en las diarias, la media), agregados con π y la unión de bandas: media
    ponderada, salvo Tmáx-Tmín, con el cuadrado.
- **P76. Las horas emparejadas comunes a los candidatos de un uso (revisor de I14; VAL-15, INT-6).**
  - **Cita.** §5.2: «Métricas por evaluación (horas emparejadas)», «Evaluable: ≥ 2.000 horas válidas»; §6.2, paso 1:
    E0 da «valor finito en ≥ 99 % de los puntos con fondo».
  - **Problema.** Un candidato de E0 puede no ser finito en ≤ 1 % de las horas; si cada uno usa sus horas, las
    evaluaciones de los candidatos difieren y `validacion` falla (VAL-15). El texto no fija si las horas son comunes.
  - **Rige y se propone.** Comunes: las horas con observación válida y producto finito en todos los candidatos del uso
    que predicen en la estación (los de E0 y los que quedaron fuera por finitud cuentan igual). Alternativa: comunes
    sólo a E0.
- **P77. El centrado crónico en cada réplica del remuestreo (revisor de I14).**
  - **Cita.** §5.4: «recalcula S de cada candidato con el mismo procedimiento»; MC-34: «Cada réplica repite todo: la
    unión de bandas, los mínimos de S_par sobre E0 y el ganador».
  - **Problema.** El nivel neto resta la media de macrozona × año sobre las evaluaciones; en una réplica con estaciones
    repetidas o ausentes esa media cambia. Hoy MSE_e queda fijo (VAL-12), y eso cambia el intervalo de ΔS crónico.
  - **Rige y se propone.** Fijo: MC-34 enumera lo que se rehace y el centrado no está. Alternativa: rehacer el centrado
    en cada réplica, que es «el mismo procedimiento».

**Huellas fijadas de v2 (coordinador).**
- **P78. `v2/correr_v2.py` y `v2/config_v2.json` cambiaron en la copia de trabajo de AP.**
  - **Cita.** §9.3 del diseño: «Huellas fijadas que M1 no puede cambiar».
  - **Problema.** Otro flujo los editó hoy (10:35): sus huellas son 1423ef3f… y 02d8c386…, y las fijadas (534e484b… y
    232c75b3…) son las del commit 4b50b0d de AP. Por eso fallan `test_fijados` (2) y `test_particiones` (1); el fallo es
    del lado seguro y no se ocultó.
  - **Propuesta.** M1 conserva las de 4b50b0d y su batería corre sobre una copia limpia de ese commit (un árbol de
    trabajo aparte), sin depender de la copia de trabajo del otro flujo. Si el autor quiere las nuevas, va por enmienda
    y se cambian a la vez en `fijados` y en `test_particiones`.
  - [Descartada por D53: contradice D51, que el autor ratificó. Rige D51, aplicada en «Tras la ola 3».]

**P28 sigue abierta** y rige la literal [respondida por D52: la Enmienda 2 del producto; ver «Tras la ola 3»]. Su borrador ya existe: `APH/auditoria/20261023/meteo_combinada/enmienda2_borrador/`
(`BORRADOR_ENMIENDA_2.md` y `simular_p28.py`, del 2026-10-26 a las 08:57). Hace falta antes de M3-4, y P47 se decide con
ella.

**Clases de salida (se suman a P42; I17 en la ola 4).** `ceguera.clase_de_ruta` ya da «metrica» a todo `validacion/` y
«resumen» a `qc/resumen_qc.json`. Propuestas: métrica para `validacion/soporte.parquet`, `validacion/sinca.parquet`,
`validacion/descriptivos.parquet` y `validacion/rr06.json` (I12, I14); resumen para el aviso SINCA y la réplica con N
(I14), que necesitan nombre de archivo.

### Pendientes para la ola 4 y siguientes

Reemplazan a los anteriores donde se cruzan; los demás siguen.
- **I15 (`tendencias`, ola 4).** Lo de la ola 2 sigue. Usar `candidatos.vecinos`, `campo`, `matriz_q`, `correccion_a` y
  `predecir_c` por lotes de puntos (PED-6: un mes en las 838.430 celdas son ≈ 5 GB). La TF de cada uso en
  `tipos.ESQUEMA_TF`, como la de `sintetico.tablas_metricas` que hoy simula el hito 2 (INT-8).
- **I16 (`producto`, ola 4).** PED-6 (por lotes); los estáticos de C con `z_e5l` (TIP-22); C_est con el clima del
  estado en las celdas (A14); `fondo_era5l.producto_desde`.
- **I17 (`salidas`, ola 4).** P42 con las salidas de arriba; lo de la ola 2 sigue.
- **I4 (`ceguera`), al volver.** Sumar «estaticas_celda_c» a la lista de `test_s07_esquemas_de_tipos` (sólo pasa como
  insumo); entonces el coordinador la pasa a `ESQUEMAS`.
- **I12, I13 e I14, al volver a sus módulos.** Tomar de `tipos` lo de TIP-19 a TIP-23 (`ESQUEMA_CONTEOS_QC`;
  `VecinosNucleo` sin la subclase, `SumasC`, `ESQUEMA_PREDICCION`, `COLUMNA_Z_E5L`, `fuera_de_la_grilla`; los
  `ESQUEMA_*_PUB`, `Estrato` y `VALOR_ESTRATO_OMM`). Hasta entonces `test_tipos.PruebasOla3` vigila la paridad. I12 puede
  ofrecer a I3 la inversa de Magnus sobre hielo en `numerico` (hoy local en `qc_dmc_meteo`).
- **I5 (`sintetico`) y después I10 (`decision`): A13.** I14 ya publica las cinco macrozonas en cada variable de MZ; falta
  que I5 las sume a la familia «agu» de `tablas_metricas` y que I10 las exija (ajustando a la vez `_agudo_base` y
  `_con_macrozona` de `test_decision`); entonces el coordinador vacía `_SIN_FILAS_DE_MZ_HASTA_A13`. Lo demás de I5 sigue.
- **I10.** Exigir al menos una huella en `decision_json` (sigue).
- **I3 (`particiones`).** D34 según P46; `fuera_de_la_grilla` está en `tipos`.
- **I20 (`orquestacion`, ola 5).** A16, A17 y A18. Además:
  - `qc_estacion` por estación; los residuos como INT-4; `sumas_lluvia_rr06` por lotes de meses con `previas=`;
  - `DatosCompetencia` según PED-5: `residuos_estacion` (NaN donde `valido_*` es falso), `climatologias_a`, `filas_c`
    dos veces (C y C_est), `recorte` según el addendum, `hiper_a` en AB;
  - `z_e5l` en los estáticos de las celdas antes de escribir `estaticas/celdas.parquet` (TIP-22);
  - SINCA: el producto en la celda y en el punto, el TPI, y las macrozonas con `tipos.macrozona_de_celda`;
  - los descriptivos por `salidas` (`validacion/descriptivos.parquet`);
  - el pliegue de producción con el amortiguador de P2 si se adopta P61;
  - lo de la ola 2 sigue.
- **I22 (ola 6).** El addendum lleva QC, CAN, VAL, TIP-19 a TIP-24, INT-3 a INT-8 y las diferencias 14 a 19; el anexo de
  firmas, lo de arriba. La batería corre sobre la copia de 4b50b0d si se adopta P78. [P78 descartada por D53.]
- **Huellas de v2.** Ver P78; y la de `v2/reloj_sinca_v2.py` sigue sin anclar (las dos pruebas de `test_sinca_meteo` se
  omiten con su motivo). [Hecho por D51 y D54: ver «Tras la ola 3».]

### Cifras al cierre

**Suite:** 612 pruebas: 552 en verde, 57 omitidas y 3 fallas. Las 3 fallas son las de P78 (`test_fijados`:
`test_huella_del_interprete` y `test_huellas_9_3_del_codigo`; `test_particiones.test_bloque_y_origen_de_config_v2`), y
ya estaban antes de la integración (596 pruebas: 536 en verde, 57 omitidas y las mismas 3 fallas). Tarda ≈ 153 s.

**Por archivo de esta ola:** `test_qc_dmc_meteo` 57, `test_candidatos` 28 y `test_validacion` 50, todas en verde; del
coordinador, `test_tipos` 38 (seis nuevas) y `test_integracion` 17 (diez nuevas: los hitos 1 y 2).

**Las 57 omitidas:**
- 51 «por implementar»: 49 de los módulos de las olas 4 a 6 (`test_tendencias` 9, `test_verificar_meteo_combinada` 13,
  `test_salud` 6, `test_ambiental` 5, `test_salidas` 5, `test_orquestacion` 4, `test_producto` 3, `test_addendum` 2 y
  `test_costo` 2) y las 2 de S10 de la batería en `test_meteo_combinada`;
- en `test_fijados`, la de huellas de datos (decisión 4);
- en `test_homogeneidad`, el traslado de 15 m a 2.500 m (D42, P47);
- en `test_meteo_combinada`, el cierre de M1 y el índice de §9 (pendientes S6, S8, S9 y S14);
- en `test_sinca_meteo`, las dos de `reloj_sinca_v2.py`.

Sin `__pycache__` nuevo.

**Huellas sha256 del coordinador:**
- `tipos.py` `01ac092cd287c8c52972f765db2e20e6817a2fe7705a487bf0462019dca68e99`
- `tests/test_tipos.py` `4d29d12c255cf5fc8b09a3599aa764fd13cd2d3f48d17f05b0fbb48b28e2f611`
- `tests/test_integracion.py` `fef55cd3f78d2601d07fcdc54117e21b29a55935a4fe3e4e6c562fbf9fde6ee2`
- `tests/test_meteo_combinada.py` `cd1c1f184dc50714da104d3f6c1011534a7ab751ba21c7abb73d77c29e056698`

## Tras la ola 3: D51 a D54, la Enmienda 2 y los hallazgos del crítico (2026-10-26)

Aplica las decisiones D51 a D54 del autor (`APH/auditoria/20261023/meteo_combinada/m1/decisiones_autor_m1_20261026.md`;
D51 ratificada a las 11:23 y D52 a D54 de las 23:23, hora de Chile) y corrige los hallazgos del crítico de la ola 3.
- En AP sólo se escribió dentro de `meteo_combinada/`, y en APH sólo en `auditoria/20261023/meteo_combinada/enmienda2/`.
- `reloj_dmc/`, `v2/` y lo anclado no se tocaron, y `m0/huellas_m0.json` tampoco.
- Ningún dato real se abrió: ni DMC, ni el reloj, ni SINCA, NASADEM, ERA5L o GHS-POP reales. Sin commits.

### D51 y D54: las huellas de v2 (FIJ-10)

- **`fijados.py`:**
  - vigentes: `SHA_CORRER_V2` 1423ef3f… (AP `889b972`) y `SHA_CONFIG_V2` 51df5063… (AP `6c15981`);
  - nueva, por D54: `SHA_RELOJ_SINCA_V2` c1eb98c5… (AP `889b972`, donde entró a git), que se suma a `HUELLAS_CODIGO`
    («§9.4, D54»);
  - el estado de M0, citado y no borrado: `SHA_CORRER_V2_M0` 534e484b… y `SHA_CONFIG_V2_M0` 232c75b3…;
  - `HUELLAS_D51`: por archivo, la de M0, la vigente y el commit de cada una;
  - lectura FIJ-10.
- **Comprobado al escribirlo.** Con `shasum -a 256` en la copia de trabajo de AP, las tres son las de
  `git show HEAD:<ruta>` (HEAD = `6c15981`). Las de M0 son las de `c7c47e8`, y `reloj_sinca_v2.py` no existía en ese
  commit. El bloque `protocolos.BLQ-75` de `config_v2.json` es el mismo en los dos commits.
- **`tests/test_fijados.py`:**
  - `test_huellas_coinciden_con_m0_y_con_el_reloj` compara las dos de v2 por su estado de M0 con `huellas_m0.json`, y
    exige que la vigente ya no sea esa;
  - prueba nueva `test_huellas_d51_de_m0_y_vigentes_en_git`: con `git cat-file`, la de M0 es la de AP `c7c47e8` y la
    vigente la de su commit; además, `test_particiones` cita las mismas dos de `config_v2.json`. Sin git o sin esos
    commits, se omite y no se da por aprobada.
- **`tests/test_particiones.py`:** `_SHA_CONFIG_V2` es la vigente (51df5063…) y `_SHA_CONFIG_V2_M0`, la de M0.
- **`tests/test_sinca_meteo.py`:**
  - `_SHA_RELOJ_SINCA` es `fijados.SHA_RELOJ_SINCA_V2`;
  - `test_paridad_con_reloj_sinca_v2` y `test_veredictos_como_el_reloj` dejan de omitirse: una huella distinta es una
    falla (`_exigir_reloj_sinca`), y sólo se omiten si falta el archivo. Las dos pasan con c1eb98c5….
- **El diseño:** la tabla de §9.3 cita, para cada uno de los dos archivos, la vigente y la de M0, con una nota de D51. §9.4
  suma `reloj_sinca_v2.py`.
- **P78 queda descartada** (D53): rige D51. Las 3 fallas del cierre de la ola 3 pasan a verde.

### Hallazgos del crítico de la ola 3

| # | Hallazgo | Qué se hizo |
|---|---|---|
| 1 | [mayor] P78 contradecía D51, que no se había aplicado | Aplicada D51 (arriba) |
| 2 | [mayor] La regla de días de §4.9 (mód 11 = 3) no la vigilaba ninguna prueba de la selección | Prueba nueva en `test_candidatos` (abajo) |
| 3 | [menor] Los hitos no detectaban el ganador fijo en el intervalo de ΔS | Corregida la afirmación de la ola 3 y agregado un caso al hito 2 (INT-9) |
| 4 | [menor] El guion de mutaciones citado no existe | Corregida la cita; las mutaciones quedan descritas con su cambio exacto (abajo) |
| 5 | [menor] Una aserción del hito 2 no probaba nada y un docstring describía mal la tabla de soporte | Corregidos |
| 6 | [menor, para el autor] La huella de `reloj_sinca_v2.py` se podía anclar | El autor la extendió (D54); aplicada |

- **2. La regla de días.** `test_candidatos.test_objetivo_solo_en_los_dias_de_seleccion`, con un objetivo que registra las
  sumas {pliegue interno: {código: (sse, n)}}:
  - cada n debe ser el número de horas observadas con residuo válido y (h // 24) mód 11 = 3 de esa estación, o
    mód 23 = 3 con el recorte;
  - lo cuenta la prueba con los valores del Anexo A escritos a mano (`VALORES_ANEXO_A` suma `SEL_MOD`, `SEL_RESTO` y
    `SEL_MOD_RECORTE`, que `test_valores_que_suponen_las_pruebas` compara);
  - corre en A, B, AB, C y C_est, con y sin recorte (10 casos);
  - para que el conteo dependa de qué días son, una estación es trihoraria y dos no tienen residuo en la mitad de los días
    de selección (330001 en los pares de mód 11 = 3, y 330003 en los impares de mód 23 = 3; las dos son de prueba
    interna en este pliegue).
- **3. El ganador fijo y los hitos.**
  - **La afirmación de «Ola 3 cerrada»** («todas detectadas por los hitos») no valía para el intervalo con el ganador
    fijo. En el hito 2, E1 = {C} y C gana las 1.999 réplicas, así que ahí D46 y el ganador fijo dan el mismo intervalo.
    Esa mutación la detectaban sólo la prueba de A11 (`test_tablas_metricas_tal_cual_en_decidir_combinacion`, que no es
    un hito) y `test_decision`.
  - **El caso nuevo**, INT-9 (`test_hito2_intervalo_de_d46_con_mas_de_un_candidato`), decide otra vez con las mismas
    tablas reales del hito sin las filas de macrozona (DEC-20: MZ no rige), con E1 = E0. C sigue ganando y AB gana 30
    de las 1.999 réplicas. El intervalo de D46 de la decisión es el contado a mano y difiere del del ganador fijo (en
    A, el extremo inferior es 0,0585 con D46 y 0,0557 con el ganador fijo). Ahora el hito 2 detecta la mutación.
- **4. El guion.** El informe de la integración de la ola 3 citaba un guion de mutaciones en el área temporal de la
  sesión, fuera del repositorio. Ese guion no existe, y `COORDINACION_M1.md` no lo nombraba. Desde ahora, cada mutación
  se describe con su cambio exacto, para que se pueda repetir (tabla de abajo). De las seis de la ola 3:
  - se repitieron cuatro: el ganador fijo, el producto sin R y sin D34 (en sus dos lugares); el S del agregado tomado
    de P1 lo repitió el crítico;
  - las otras dos, los residuos sin la validez de la tabla ancha y el nudo mal convertido en la tabla larga, fueron
    cambios en ayudas de la prueba que el informe no describió. No se pueden repetir tal cual, y quedan sin cambio
    exacto.
- **5. La réplica con N y la tabla de soporte.**
  - `assertIn(…, (True, False, None))` pasa a exigir el resultado entero: {ganador: C, ganador_n: C, mismo_ganador:
    True, n_estaciones_n: 7}, con las 7 estaciones de N con celda.
  - El docstring ya no dice que la tabla de soporte sale «vacía». Trae sólo los estratos sin estaciones, que no se
    publican: todo estrato con estaciones es publicable.

### Mutaciones (en memoria, un proceso por mutación; nada se escribe en el paquete)

Cada una reemplaza en memoria la función nombrada (o el fragmento de su código fuente, que se vuelve a compilar) antes de
cargar las pruebas.

| Mutación (cambio exacto) | Pruebas corridas | Resultado |
|---|---|---|
| `particiones.dias_de_seleccion` devuelve True en todas las horas | la prueba de días | Detectada (10 de 10 casos) |
| … devuelve False en todas | la prueba de días | Detectada (10 de 10) |
| … ignora `recorte` (siempre mód 11) | la prueba de días | Detectada (los 5 con recorte) |
| … con resto 4 en vez de 3 (`h − 24`) | la prueba de días | Detectada (10 de 10) |
| `decision._intervalos` con el conjunto (ganador de la decisión,) | `PruebasHito2` | Detectada por INT-9 (antes, ninguna del hito) |
| `validacion.replica_n` con `ganador_n` = `ganador` y `mismo_ganador` = True | `PruebasHito2` | No detectada: equivalente en esta red, donde N elige el mismo ganador |
| `validacion.replica_n` con todas las estaciones como de N | `PruebasHito2` | Detectada (la réplica con N) |
| `fondo_era5l.producto_desde` con R en cero | `PruebasHito2` | Detectada (6 de 6) |
| `validacion._fuera_de_la_grilla` → False; o `candidatos._fuera_de_la_grilla` → False | `PruebasHito2` | Detectadas (6 de 6) |
| Las 13 de `homogeneidad.k4`, cada una con su cambio exacto en la tabla de abajo | `PruebasBordesK4`, `PruebasK4` y `PruebasS4` (25 pruebas) | 11 detectadas; las 2 que no son equivalentes |
| Las 15 del generador del v2.3 (en `ENMIENDA_2.md`) | el generador, con `python -B` y con `python -B -O` | Detectadas las 15 |

**Las 13 de `homogeneidad.k4`** (corregida tras la revisión de la Enmienda 2, con las pruebas de M-4). Cada una cambia un
fragmento del código fuente de `k4`, que se vuelve a compilar en el módulo:

| # | Cambio exacto en `k4` | Resultado |
|---|---|---|
| 1 | `_salto(medias_a.recortar(a, b), k_b, umbrales)` → `… k_b + 1 …` | Detectada: la coincidencia, a −5 y +6 |
| 2 | … → `… k_b - 1 …` | Detectada: la coincidencia, a +5 y −6 |
| 3 | `dz_a is not None and abs(dz_a) >= umbral_a` → `dz_a is not None` | Detectada: la de 10 m (9 y 9,999 m) |
| 4 | `abs(dz_a) >= umbral_a` → `abs(dz_a) > umbral_a` | Detectada: la de los D exactos |
| 5 | `_salto(medias_a.recortar(a, b), k_b, umbrales)` → `_salto(medias_a, k_b, umbrales)` | No detectada: equivalente (HOM-4) |
| 6 | `_salto(medias_b.recortar(a, b), k_a, umbrales)` → `_salto(medias_b, k_a, umbrales)` | No detectada: equivalente (HOM-4) |
| 7 | `con_t2b = cerca or (` → `con_t2b = False or (` | Detectada: la del D que no se define, a 2 y 3 meses |
| 8 | `con_t2b = cerca or (salto_b is not None and abs(salto_b) >= umbral_b)` → `con_t2b = cerca` | Detectada: la coincidencia (±4, ±5 y ±6), la de 1,21 hPa y la de los D exactos |
| 9 | `abs(salto_b) >= umbral_b` → `abs(salto_b) > umbral_b` | Detectada: la de los D exactos |
| 10 | `salto_b is not None and abs(salto_b) >= umbral_b` → `salto_b is None or abs(salto_b) >= umbral_b` | Detectada: la del D sin quiebre cerca y la de 4 meses |
| 11 | `salto_b = _salto(…, k_a, …)` → el de mayor \|D\| entre los meses k_a − 3 … k_a + 3 en que se define | Detectada: la coincidencia (±7) y la de 1,19 hPa |
| 12 | el traslado → algún mes k_b − 3 … k_b + 3 con D de T2a definido, ≥ 10 m y compatible | Detectada: la coincidencia (±6 y ±7) |
| 13 | el traslado → algún quiebre de T2a a ≤ 3 meses de k_b y compatible (su D), y `con_t2b = cerca` (la regla del v2.2) | Detectada: la coincidencia (±4, ±5 y ±6), la de 1,21 hPa y la de los D exactos |

### D52: la Enmienda 2 del producto (P28 y P47)

**Escrito en `APH/auditoria/20261023/meteo_combinada/enmienda2/`:**
- `ENMIENDA_2.md`: el motivo con citas, la decisión literal, las tasas con sus semillas, lo que se vio, la diferencia de
  texto, los cambios del código y de las pruebas y el anclaje;
- `generar_v2_3.py`, en el estilo de `generar_v2_2.py`. Nunca sobrescribe y comprueba las huellas del v2.2, del v2.1 y del
  borrador. Exige que cada texto viejo esté una vez y que el texto nuevo sea el de la opción 2 del borrador. Comprueba los
  seis bloques del diff, los anexos byte a byte (el Anexo A también contra el v2.1), las listas ordenadas de [M0…] y
  [EMC1-n] y las tres [EMC2-1]. [Tras la revisión de la Enmienda 2: también la viñeta del traslado entera (M-1), los
  bloques editoriales y los commits 0517360 y 1a9889b con `git cat-file`, con SystemExit en vez de assert (m-7).]
- [Tras la revisión: `homogeneidad_regla_literal_v2_2.py`, la versión de `homogeneidad.py` con la regla literal
  (b8ed49f7…), como referencia (m-6).]
- `PROTOCOLO_METEO_COMBINADA_v2.3.md`, generado del v2.2: sha256
  `b4175f785ec57811702352d9d063164a5dce05f325a48c327a6d554a09ceddc2`.

**EMC2-1.** Un quiebre de T2b es traslado si el D(k) de T2a en el mismo mes, con las ventanas en el tramo que el quiebre
partió, llega a 10 m y es compatible con Δz_b. Un quiebre de T2a es «cambio del método de reducción» sólo si:
- no hay quiebre de T2b a ≤ 3 meses;
- y el D(k) de T2b en su mes no se define o no llega a 1,2 hPa.

El Anexo A no cambia.

**Código y pruebas:**
- **`homogeneidad.k4`** implementa EMC2-1, y HOM-7 y HOM-14 se reescriben.
- **`tests/test_homogeneidad.py`:**
  - `TASAS_S4["traslado_15"]` pasa a 100, 100 y 96 (antes 90, 89 y 81); lo demás de S4 no cambia;
  - `MOTIVO_P28` pasa a `MOTIVO_P47`: la prueba de 2.500 m sigue omitida, con el motivo de P47 y la tasa de 96;
  - `test_coincidencia_a_3_meses_si_y_a_4_no` pasa a `test_coincidencia_a_5_meses_si_y_a_6_no`;
  - pruebas nuevas: `test_traslado_exige_d_de_t2a_de_10_m_en_el_mes_del_quiebre` y
    `test_t2a_con_quiebre_de_t2b_cerca_va_sin_clase_aunque_su_d_no_se_defina` (ésta, tras la revisión, también a 3 y a 4
    meses);
  - y, tras la revisión de la Enmienda 2 (M-4): `test_d_de_t2b_que_no_se_define_sin_quiebre_cerca_es_metodo_de_reduccion`,
    `test_d_de_t2b_en_el_mes_del_t2a_a_1_21_y_1_19_hpa` y `test_umbrales_inclusivos_con_d_exactos`.
- **Cotejo con el borrador.** `homogeneidad.k4` da el mismo `ResultadoK4` que la «opcion_2» de `simular_p28.py` en las
  1.500 series de S4, las 200 estacionarias y 900 de dos sucesos.
- **Mutaciones de `k4`:** 11 de 13 detectadas (tabla de arriba). Las 2 que no son las ventanas en todo el registro, del D
  de T2a o del de T2b: equivalentes por HOM-4, porque las 12 + 12 de un corte admisible caen dentro de su tramo. [Antes
  decía que «>» en vez de «≥» no se detectaba porque un D exactamente igual al umbral no se podía fabricar en coma
  flotante. Era falso: el revisor lo fabricó, y `test_umbrales_inclusivos_con_d_exactos` detecta las dos.]

**P28 queda respondida por D52, y P47 por D52 y D56.** Las tasas de «Tasas de S4 medidas (HOM-14, para el addendum)» se
vuelven a declarar así, a 500, 1.000 y 2.500 m:
- traslado de 15 m, 100, 100 y 96 de 100;
- 5 m, reducción y horario, 100 en las tres;
- barómetro, 100, 99 y 100;
- ningún traslado fuera de los traslados;
- falsos quiebres, 0 de 200;
- 5 dobles informes a 2.500 m.

**Texto vigente.** `umbrales.TEXTO_VIGENTE` (y sus copias en `ceguera`, `fijados` y `test_entorno`) siguen en el v2.2
hasta que el v2.3 se ancle. El Anexo A es el mismo, así que `umbrales.cargar_m0` y los umbrales no cambian. El paso al
v2.3 queda en los pendientes.

### D53: P41 a P77

Quedan fijadas como propuestas para el addendum de M1, tal como están en «Preguntas para el autor (cierre de la ola 2)»
(P41-P48) y en «Preguntas para el autor (cierre de la ola 3)» (P49-P77). Si un revisor ve que alguna cambia una regla, se
le pregunta aparte al autor. P78 queda descartada: rige D51.

### Lecturas nuevas o cambiadas (van al addendum de M1)

- **FIJ-10** (`fijados`): las huellas de v2 después de M0 (D51 y D54).
- **HOM-7 y HOM-14** (`homogeneidad`): la clasificación de EMC2-1, sus tasas y P47 (y, tras la revisión, D55 y D56).
- **INT-9** (`test_integracion`): D46 con más de un candidato en el hito 2.

### Pendientes (se suman a los de la ola 4; reemplazan a los anteriores donde se cruzan)

- **Anclar la Enmienda 2.** [Hecho: APH dd6c1c6, sello e3f9f97; el paso al v2.3 está en «Texto vigente: el v2.3».] [La
  revisión independiente ya concluyó: «se puede anclar con cambios», sin bloqueantes; ver
  «Tras la revisión independiente de la Enmienda 2».] El autor autoriza el commit en APH, con el sello OpenTimestamps en
  `auditoria/sellos/anclajes_<fecha>_meteo_emc2.txt`; el envío al remoto espera su autorización (B14). Al anclar, el
  coordinador:
  - pasa `TEXTO_VIGENTE` y `SHA_TEXTO_VIGENTE` al v2.3 en `umbrales`, `ceguera` y `fijados` a la vez, y en
    `test_entorno`;
  - pone al día el mensaje del Anexo A en `umbrales` y las pruebas que nombran el v2.2;
  - en `constantes`, reemplaza REP_2.5_09 por dos repeticiones y suma otras dos (detalle en «Tras la revisión
    independiente de la Enmienda 2»). `completitud` y `verificar_contra_texto` deben dar 0 con el v2.3.
- **El reloj (MC-17).** [Hecho el 2026-10-27: ver «MC-17: la clausura del reloj tras su Enmienda 5».] Otro agente está
  cambiando `reloj_dmc/` por su Enmienda 5. Hoy fallan `test_clausura_del_reloj` y
  NAS-1 (`test_estaticas_nasadem.test_lectura_de_textos_como_reloj`), porque los dos comparan con las siete huellas de
  4b50b0d. Además se omiten, con su motivo, 14 pruebas que cargan el validador de RELOJ: 6 de `test_politicas`, 3 de
  `test_qc_dmc_meteo` y las 5 del hito 1. No se arreglan volviendo a fijar el reloj. Tras el commit de la Enmienda 5 del
  reloj, se recalcula la clausura (`HUELLAS_RELOJ_4B50B0D`, `COMMIT_RELOJ` y FIJ-1) y se vuelve a correr la batería.
  Con las huellas de la copia de trabajo puestas sólo en memoria, esas 14 y el resto de `test_integracion`,
  `test_qc_dmc_meteo` y `test_politicas` (102 pruebas) pasan.
- **I22 (ola 6).** El addendum lleva EMC2-1, D51 a D54, FIJ-10, HOM-7, HOM-14, INT-9 y P41 a P77 (D53).

### Cifras

**Suite:** 617 pruebas: 546 en verde, 69 omitidas y 2 fallas. Tarda ≈ 144 s.
- **Las 2 fallas son del reloj.** `test_fijados.test_clausura_del_reloj` y `test_estaticas_nasadem` NAS-1
  (`test_lectura_de_textos_como_reloj`) comparan `reloj_dmc/` con las siete huellas de 4b50b0d. Hoy
  `reloj_dmc/constantes.py` da 95deee46… (antes 10354281…), por la Enmienda 5 del reloj, en curso. Se arreglan en MC-17,
  después del commit de esa enmienda.
- **Antes de estos cambios** eran 612 pruebas: 552 en verde, 57 omitidas y las 3 fallas de D51. Esa corrida ya era con la
  copia de trabajo del reloj de entonces, que todavía calzaba.
- **Pruebas nuevas (5):** `test_fijados` 1, `test_candidatos` 1, `test_integracion` 1 y `test_homogeneidad` 2 (más una
  renombrada).
- **Las 69 omitidas:**
  - 51 «por implementar» (las mismas de la ola 3);
  - 14 porque la clausura del reloj cambió respecto de 4b50b0d: las 5 del hito 1, 6 de `test_politicas` y 3 de
    `test_qc_dmc_meteo`. Con las huellas de la copia de trabajo puestas sólo en memoria, pasan;
  - en `test_fijados`, la de huellas de datos;
  - en `test_homogeneidad`, la de 2.500 m, con el motivo de P47;
  - en `test_meteo_combinada`, el cierre de M1 y el índice de §9.
- **Dejaron de omitirse** las dos de `reloj_sinca_v2.py` en `test_sinca_meteo`.

Sin `__pycache__` nuevo.

**Huellas sha256** [las de `homogeneidad.py`, `tests/test_homogeneidad.py`, `ENMIENDA_2.md` y `generar_v2_3.py` cambiaron
tras la revisión: ver abajo]:
- `fijados.py` `114da9c3dc91155b0b769c5fe20518805fd5c2e70e73b410452eb5cf0f4ea630`
- `homogeneidad.py` `b26a7d69a59b280a92425ac5cc8e4be6aeda3eb717f5f3e6c917508880f1dc11`
- `tests/test_fijados.py` `f730b4edf83dd9dec5b6b2f8793b4844bef6803256d72cd308695f48eaaaf26b`
- `tests/test_particiones.py` `8576491cfe08d47373b73eea13c5c03d4603533bce5e0aa79e43cb348546aa36`
- `tests/test_sinca_meteo.py` `74bc9c8f6458f79baf9a48e3d491c2767b7d395276cdc4d77beb1f297181d797`
- `tests/test_candidatos.py` `fe537ebf85a94db5730a8098fc5f5eb982611f4d4bfc8208edc8e705d935f25f`
- `tests/test_integracion.py` `522df982e3701fcaaa9a3445849fb02f35e3ca471ac32483cab7cf5fc3ca6bb7`
- `tests/test_homogeneidad.py` `bb3c3e41cde9c610e8284212cad357335daeb8b74daea5bab7c10ecf0f07df0b`
- `DISENO_IMPLEMENTACION_M1.md` `81c039198544fbfafd1ab8f62666e3bcb10cc8c13197cb19f86c232b7b6a533e`
- En APH, en `enmienda2/`:
  - `ENMIENDA_2.md` `47677f561429d35c1dcdf7eb146ead9d4f974fac337b725152de1be1840c6cdf`
  - `generar_v2_3.py` `ba06fc15283182bbc5301d68c700bad7272ce1264779598596e8509a0085b885`
  - `PROTOCOLO_METEO_COMBINADA_v2.3.md` `b4175f785ec57811702352d9d063164a5dce05f325a48c327a6d554a09ceddc2`

## Tras la revisión independiente de la Enmienda 2 (2026-10-27)

La revisión concluyó «se puede anclar con cambios», sin bloqueantes. El texto v2.3 (b4175f78…) se ancla tal cual y no se
tocó. El autor respondió dos preguntas nuevas, que están en el archivo de decisiones junto con una nota sobre su encabezado:
- **D55:** «Mantener D52 (Recomendado)», conociendo el efecto sobre Q2;
- **D56:** P47, «Omitida e informada (Recomendado)».

Siguen las mismas reglas: en AP sólo se escribió dentro de `meteo_combinada/`, y en APH sólo en `enmienda2/`. Ningún dato
real. Sin commits.

### Qué se corrigió

- **M-1 (generador).** Exige la viñeta del traslado entera: la vieja, con la cita vieja del §8 del borrador cambiada por la
  nueva. Con eso detecta los cambios del texto normativo fuera de la cita.
- **M-2 (`ENMIENDA_2.md`, «Plazo y frontera»).** Cita las dos fronteras de §10. El C4 de RELOJ no ha empezado: RELOJ está
  anclado sólo hasta C1 (APH 962b5d0 y b1db6ee) y prepara su Enmienda 5. Por eso el cambio de `k4` queda antes de las dos.
- **M-3 (`ENMIENDA_2.md`, «El costo»).** Agrega el efecto sobre las alarmas:
  - los traslados que la literal dejaba como barómetro (del 10 al 19 % en S4) y los traslados falsos de dos sucesos pasan
    de la marca 16 (Q1, sólo QFE y QFF) a la marca 1 (toda la fila, que cuenta en Q2 en todas las variables);
  - eso sube la probabilidad de que Q2 detenga M3-4;
  - el autor lo vio y mantuvo D52 (D55).
- **M-4 (`tests/test_homogeneidad.py`, `PruebasBordesK4`).**
  - **Nuevas:**
    - `test_d_de_t2b_en_el_mes_del_t2a_a_1_21_y_1_19_hpa`;
    - `test_d_de_t2b_que_no_se_define_sin_quiebre_cerca_es_metodo_de_reduccion`;
    - `test_umbrales_inclusivos_con_d_exactos`: un D de T2b de 1,2 hPa exacto, como lo fabricó el revisor, y un D de T2a
      de 10 m exacto, hallado probando los saltos vecinos de 10 m.
  - **Ampliada:** `test_t2a_con_quiebre_de_t2b_cerca_va_sin_clase_aunque_su_d_no_se_defina`, ahora también con el quiebre
    de T2b a 3 meses (sin clase) y a 4 (cambio del método de reducción).
  - **Corregida** la frase que decía que un D exactamente igual al umbral no se podía fabricar, y la tabla de mutaciones,
    en la enmienda y aquí. Ahora son 13, con su cambio exacto: 11 detectadas y 2 equivalentes.
- **m-1.** La enmienda dice cómo se lee desde el v2.3 la fila «Traslados» del Anexo A. Los ± 3 meses rigen sólo en «Sin
  T2b»; en el traslado, la coincidencia es el mismo mes.
- **m-2.** Quedan exactos los pendientes de `constantes`, medidos en memoria con el v2.3: `verificar_contra_texto` da 1
  error (REP_2.5_09) y `completitud` da 5 (l. 418, 425 y 426). Al anclar:
  - REP_2.5_09 se reemplaza por dos repeticiones: `K4_COINC_MESES` en la regla de T2a («hay un quiebre de T2b a ≤ 3
    meses»), y `K4_COINC_M` y `K4_COINC_FRAC` en el traslado («|Δz_a − Δz_b| ≤ máx(10 m; 0,3·|Δz_b|)»);
  - se suman las de `K4_T2A_M` («cumple |D(k)| ≥ 10 m») y `K4_T2B_HPA` («|D(k)| < 1,2 hPa»).
- **m-3.** Las cifras de dos sucesos van por d: EMC2-1 reemplaza la regla literal y no la amplía (con d = −4, 36 frente a
  47).
- **m-4.** «El costo» dice ahora «Sólo en altitudes bajas, con la señal de SIN-20, donde el cambio de la reducción es de
  10 a 25 m».
- **m-5.** La enmienda cita literalmente:
  - la opción 2 y las preguntas del borrador;
  - las filas D52, D55 y D56 y la nota del encabezado del archivo de decisiones.

  Ya no infiere qué contestó el autor en cada pregunta del borrador. P47 queda en D56.
- **m-6.** Con el `k4` actual, `simular_p28.py` se detiene en SIM-3. Se guarda en `enmienda2/` la versión literal de
  `homogeneidad.py`, `homogeneidad_regla_literal_v2_2.py` (b8ed49f7…), reconstruida desde la actual y con su huella
  comprobada. Con ella en memoria, y con las tasas literales de `TASAS_S4` también en memoria, `simular_p28.py` reproduce
  byte a byte el anexo del borrador.
- **m-7 (generador).**
  - Usa SystemExit en vez de assert: con `python -O` sigue comprobando.
  - Compara cada bloque del diff con sus líneas viejas y nuevas, y comprueba lo que deben decir los bloques editoriales.
  - Comprueba con `git cat-file` que APH 0517360 trae el v2.2 con su huella y que 1a9889b trae el archivo del sello.
  - **Una opción nueva:** `--repositorio <raíz de APH>`, para correr una copia temporal.
  - **Resultado:** las 15 mutaciones que se le hicieron se detectan, con y sin `-O`.
- **m-8.** La enmienda anota que la entrada heredada termina en «Detalle en `ENMIENDA_1.md`.» y que eso no se resuelve
  desde `enmienda2/`. El v2.3 no se toca.
- **m-9.** La tabla de las 13 mutaciones de `k4` queda arriba, en «Mutaciones», con su cambio exacto. Se corrigió la cita
  que no era literal («Tasas de S4 medidas (HOM-14, para el addendum)»).
- **Además.** HOM-7 cita D55 y HOM-14 cita D56, y `MOTIVO_P47` dice D56.

### Comprobaciones

- **El generador en una copia temporal.** Se corrió en una carpeta temporal, con copias del v2.2, del v2.1, del borrador
  y del generador, y con `--repositorio` apuntando a APH. Salió b4175f785ec57811702352d9d063164a5dce05f325a48c327a6d554a09ceddc2,
  byte a byte el v2.3 de `enmienda2/`. Con `-O`, lo mismo.
- **La suite:** 620 pruebas, 549 en verde, 69 omitidas y 2 fallas. Las 2 fallas y 14 de las omitidas siguen siendo las del
  reloj (MC-17): la Enmienda 5 del reloj está en curso. Las otras 55 omitidas son las de antes: 51 «por implementar», la
  de datos reales, la de 2.500 m (P47, D56) y las dos del cierre de M1. Pruebas nuevas: 3, todas en `test_homogeneidad`
  (49).
- Sin `__pycache__` nuevo.

**Huellas sha256 nuevas:**
- `homogeneidad.py` `0918f354d4fda59e1369aa09b0c0e430ab9565033372485193781098146fbd17`
- `tests/test_homogeneidad.py` `b7dd43701e1e801d414e3a31eefa8ca9fb6969617abde2b8d4d192d845ffd235`
- En APH, en `enmienda2/`:
  - `ENMIENDA_2.md` `a56eba71c9e93d0148da80bc7edce8aba22d2fef4501df6bfafc475a26727918`
  - `generar_v2_3.py` `cdac9aa01e3ebc26a249aac07a16bbd19749bc810b4964122269bbdec5f8eb43`
  - `homogeneidad_regla_literal_v2_2.py` `b8ed49f739fdc56e775cabd09b35d612bd3c09650b33c4ff5f91180a08383b67`
  - `PROTOCOLO_METEO_COMBINADA_v2.3.md` `b4175f785ec57811702352d9d063164a5dce05f325a48c327a6d554a09ceddc2` (sin cambios)
- Los demás de «Tras la ola 3» no cambiaron.

## Texto vigente: el v2.3 (2026-10-27)

La Enmienda 2 del producto quedó anclada en APH dd6c1c6, con su sello en e3f9f97. El v2.3 de ese commit da
b4175f785ec57811702352d9d063164a5dce05f325a48c327a6d554a09ceddc2, comprobado con `git cat-file`. M1 pasa su texto vigente
del v2.2 al v2.3. En AP sólo se escribió dentro de `meteo_combinada/`, y en APH nada. Ningún dato real. Sin commits.

### Qué cambió

- **`umbrales.py`.**
  - `TEXTO_VIGENTE` es `auditoria/20261023/meteo_combinada/enmienda2/PROTOCOLO_METEO_COMBINADA_v2.3.md`, y
    `SHA_TEXTO_VIGENTE` es b4175f78….
  - El mensaje del Anexo A dice ahora «el Anexo A del texto vigente no es idéntico al del v2.1 (hallazgo m-8)».
  - UMB-7 habla del texto vigente, y la lectura nueva UMB-13 dice cuál es.
  - `cargar_m0` sigue comprobando que el Anexo A del vigente es el del v2.1: lo es, así que ningún umbral cambia.
- **`ceguera.py`.** Su copia de `SHA_TEXTO_VIGENTE` es b4175f78….
- **`fijados.py`.**
  - `SHA_TEXTO_VIGENTE` es b4175f78…, y `HUELLAS_CODIGO` lleva el v2.3 como «texto vigente».
  - El v2.2 (f059c14c…) sigue en la lista, como `SHA_TEXTO_V2_2`, con el origen «Enmienda 1»: es el texto que el v2.3
    enmienda.
- **`constantes.py`** (CON-15). REP_2.5_09, la repetición de K4 del v2.2, se reemplaza por cuatro, tal como estaba escrito:
  - `K4_T2A_M`: «cumple |D(k)| ≥ 10 m»;
  - `K4_COINC_M` y `K4_COINC_FRAC`: «|Δz_a − Δz_b| ≤ máx(10 m; 0,3·|Δz_b|)»;
  - `K4_COINC_MESES`: «hay un quiebre de T2b a ≤ 3 meses»;
  - `K4_T2B_HPA`: «|D(k)| < 1,2 hPa».

  Con el v2.3, `verificar_contra_texto`, `completitud` y `verificar_repeticiones` dan 0 problemas. Las repeticiones de §2.5
  que siguen se renumeran (ahora hay 13).
- **`tests/test_entorno.py`.** `_TEXTO_VIGENTE` y `_SHA_TEXTO_VIGENTE` son los del v2.3.
- **`tests/test_ceguera.py`.** El texto sintético dice «texto v2.3» y no «texto v2.2». Hace falta porque los documentos
  sintéticos citan la ruta del texto vigente (`_ALIAS_VIGENTE`), y la versión de esa ruta es un número que debe salir del
  texto. Sin el cambio, `test_s07_documento_positivos` daba 4 errores.
- **Sólo docstrings y mensajes** (el v2.2 pasa a v2.3, o a «el texto vigente»):
  - `__init__.py`, HOM-7 de `homogeneidad.py` y POL-8 de `politicas.py`;
  - `test_constantes`, `test_meteo_combinada`, `test_tipos`, `test_politicas`, `test_particiones` y `test_umbrales`.

  En `test_umbrales`, la variable `desde_v22` pasa a `desde_vigente`. El código no cambió en ninguno.
- **El diseño.** «Texto vigente» es el v2.3 (APH dd6c1c6, sello e3f9f97). Dice también qué es el v2.2 y que fue el vigente
  del 2026-10-26 al 2026-10-27.

### Suite

620 pruebas: **549 en verde, 69 omitidas y 2 fallas.** Tarda ≈ 141 s.
- **Las 2 fallas** son las conocidas de la clausura del reloj (MC-17): `test_fijados.test_clausura_del_reloj` y
  `test_estaticas_nasadem.test_lectura_de_textos_como_reloj`. Se arreglan después del nuevo cierre de C1.
- **Las 69 omitidas** son las de antes:
  - 14 por la misma clausura del reloj;
  - 51 «por implementar»;
  - la de datos reales;
  - la de 2.500 m (P47, D56);
  - las dos del cierre de M1.
- Sin `__pycache__` nuevo.

**Huellas sha256:**
- `umbrales.py` `e1c630b0810bdd487b46ba3e1369b6109cb6f7bd459cdfe171889c593bd4642b`
- `ceguera.py` `4be5ab5c58069dbd8ac3284d744b5ab186c14fb8c4d3691dd182d75cb2113270`
- `fijados.py` `4da3178299ae13d8f3d26be93d7e96b489812d6420c1b80f9e65b9b91b0415a2`
- `constantes.py` `2f51d68e6519ce851d1f7491c301eabd0787e1becca624de6ac9c2048449ca34`
- `politicas.py` `278226aed2f969cc38a07ceece57496e723bbfbace1b80b2b636fe98d6992ad9`
- `homogeneidad.py` `a3d399ce5956c83ec64fd23c1dbefed151d55d9d1879d06f18b5629a17fdbfed`
- `__init__.py` `c60afc2ea42845d87821d7bdc968625e25cd1e97c8255e40fd8235d68d62dd37`
- `DISENO_IMPLEMENTACION_M1.md` `543a3632460146400e62a7e8db77226cc3682aef4b05f7652a93221badce83b6`
- `tests/test_entorno.py` `7748c4f46c7c33d7a3b45391f7a7d3fad247de275bd4415ff7762addb45bb22d`
- `tests/test_ceguera.py` `cdc5c406f7bcbd543d344ef55ae3d278ae8d8579ba9d321b10decb6289f16b2d`
- `tests/test_umbrales.py` `63b7ba543cd96b46b46e2050374a93b18a22bead062693934dcb4ad8969f12cb`
- `tests/test_constantes.py` `b8de6b4cfd2d273bde32be26cb4643dbe528c9afe8eff1654df80efe359c81c4`
- `tests/test_meteo_combinada.py` `bd1782e4a99461b37dee81e91843fc3ae2a016b4d0508cb278029517d62805d7`
- `tests/test_tipos.py` `6b2c215a7932c69dffe60ecbc8b797448ee4c96bff663936f7528172ab7f9707`
- `tests/test_politicas.py` `1d3c14ad7ef8a7d9dd351a72bb2a3651315b91e326148d837a23a1b2931f70ef`
- `tests/test_particiones.py` `40f2fcd0dc59efd2619420f565d837fd93bd6823bbfadaf1bef53ebddbbaaa93`

### Pendientes

- **MC-17.** Después del nuevo cierre de C1 del reloj, recalcular la clausura (`HUELLAS_RELOJ_4B50B0D`, `COMMIT_RELOJ` y
  FIJ-1) y volver a correr la suite. [Hecho: ver «MC-17: la clausura del reloj tras su Enmienda 5».]
- **I22 (ola 6).** `anexo_a2.json` se genera del v2.3, y el addendum cita el v2.3 como texto vigente.

## MC-17: la clausura del reloj tras su Enmienda 5 (2026-10-27)

El C1 del reloj cerró de nuevo, tras su Enmienda 5. Por la decisión E5-F del autor, M1 vuelve a fijar la clausura del reloj
(MC-17).
- **Lo que ya está anclado:**
  - el código, en AP 1da0236 («Reloj DMC, Enmienda 5»);
  - el texto consolidado v1.2, en APH 1f59e6e (`auditoria/20261027/reloj_dmc/PROTOCOLO_RELOJ_DMC_v1.2.md`);
  - el addendum, en APH 73615e8 (`auditoria/20261027/reloj_dmc/addendum_c1.json`).
- **Las reglas.** En AP sólo se escribió dentro de `meteo_combinada/`, y en APH nada. `reloj_dmc/` y LOCAL no se tocaron.
  Del texto v1.2 y del addendum sólo se calculó la huella, sin leerlos. Hay una corrida C4 del reloj en curso, así que la
  suite se corrió con un hilo y la prioridad más baja (`nice -n 19`). Sin commits.

### Qué cambió

- **`fijados.py`:**
  - **La clausura nueva.** `COMMIT_RELOJ` es 1da023640f8e3c65fba461480b5faaf06f158ba2, y `HUELLAS_RELOJ_1DA0236` son las
    siete huellas de ese commit; `HUELLAS_RELOJ` la nombra como la vigente. Se comprobaron con `git show 1da0236:<ruta>`, y
    la copia de trabajo es igual.
  - **Sólo cambió `constantes.py`:** de 10354281… a 95deee46…. Lo que cambió son las versiones del texto del reloj: suma el
    v1.0.5, y el texto de C1 pasa a ser el v1.2.
  - **La historia.** La clausura anterior queda como `HUELLAS_RELOJ_4B50B0D` y `COMMIT_RELOJ_4B50B0D`.
  - **FIJ-1 reescrita.** C1 cerró antes de sellar M1, así que la clausura va al addendum de M1. FIJ-8 dice que el
    `__init__` es el mismo en los dos commits.
  - **`HUELLAS_CODIGO` suma cuatro archivos del reloj, sólo por su huella:**
    - el texto v1.0.5 de la Enmienda 5: 21f1b4699dea7106b0e6065e0f232e8aeb97ca618b812b2dee4a2d3b9b803c89;
    - su `texto_7_5.md`: 58362640…, el mismo de la Enmienda 2;
    - el v1.2: 479ed38f8e594e10996cd79e5741d440d291f0dfeac43a279386e30525cabb85;
    - el addendum de C1: cd1c434493cafcda2ebfcdecf4a07738a9b9dac6794f41d960e03c6e445b51d2.
- **Lo que usa el producto del reloj no cambia.** Se comparó por programa el v1.0.4 con el v1.0.5:
  - §3 y §7 del reloj son iguales;
  - el párrafo de §4.3.5, también;
  - `texto_7_5.md` sigue en 58362640….

  La Enmienda 5 cambia §4, §5, §6 y §8 del reloj, en otras partes.
- **Las pruebas:**
  - `test_fijados.test_clausura_del_reloj` compara con `HUELLAS_RELOJ`;
  - prueba nueva `test_clausura_en_git_y_su_historia`. Con `git cat-file` comprueba que la clausura vigente es la de
    1da0236 y la de la historia, la de 4b50b0d, y que entre las dos sólo cambió `constantes`. También comprueba las huellas
    del v1.2 y del addendum en APH 1f59e6e y 73615e8;
  - `_validador` de `test_politicas`, `test_qc_dmc_meteo` y `test_integracion` usa `HUELLAS_RELOJ`, y su motivo de omisión
    nombra la clausura fijada;
  - NAS-1 (`test_estaticas_nasadem`) lee `tablas.py` y `constantes.py` con `HUELLAS_RELOJ`;
  - la lectura NAS-1 de `estaticas_nasadem.py` y el encabezado de su prueba nombran 1da0236.
- **El diseño:**
  - MC-17 y el pendiente 2 de §10 quedan anotados como hechos;
  - §9.4 suma las filas del v1.0.5, de `enmienda5/texto_7_5.md`, del v1.2, del addendum de C1 y de la clausura fijada,
    con la de 4b50b0d como historia.

### Suite

621 pruebas: **566 en verde, 55 omitidas y ninguna falla.** Tarda ≈ 153 s, con un hilo y `nice -n 19`.
- **Volvieron a verde las 2 fallas:** `test_clausura_del_reloj` y NAS-1.
- **Volvieron a correr las 14 omitidas:** las 5 del hito 1, 6 de `test_politicas` y 3 de `test_qc_dmc_meteo`. Todas pasan.
- **Prueba nueva (1):** `test_clausura_en_git_y_su_historia`.
- **Las 55 omitidas:**
  - 51 «por implementar»;
  - la de datos reales;
  - la de 2.500 m (P47, D56);
  - las dos del cierre de M1.
- Sin `__pycache__` nuevo.

**Huellas sha256:**
- `fijados.py` `a89418bdf608f947372849e102415c053dd01caa65e388dbf792b3a0049545d9`
- `estaticas_nasadem.py` `3a9e90418e5605e927042d80f6f8ab614bf4f29c981e66679f00ddd447c049cd`
- `tests/test_fijados.py` `23337b0af031bbdd1095454272850c7dc3fa40d9bc42d0a90b081be8758cccd7`
- `tests/test_estaticas_nasadem.py` `f1c196eb632e53bc5a4fc971c933a0566f59efdaf057519b4d0ece7c16a6a11a`
- `tests/test_politicas.py` `3522649290bd896b305e7aa007d6410fbb71c68757517fe16c0485eadf9680c9`
- `tests/test_qc_dmc_meteo.py` `26eab858c568941514f5fab8ca3483b1bf294f3a7bd32a73f546e1430bc1dfa1`
- `tests/test_integracion.py` `79f33798a81167a6386362a61330dfda795e58e6bc34e73db81aae57bb905ec8`
- `DISENO_IMPLEMENTACION_M1.md` `5b3c4eae06a1b836e6be2232638e0a98b2e344da6b9a40bc2e6d25e89e4df409`

### Pendientes

- **I22 (ola 6).** El addendum de M1 lleva:
  - la clausura del reloj de 1da0236, con la de 4b50b0d como historia (MC-17, FIJ-1);
  - las huellas del v1.2 y del addendum de C1 del reloj.

## Ola 4: encargos (2026-10-27)

Línea base antes de la ola: 621 pruebas, 566 en verde, 55 omitidas y ninguna falla (≈ 154 s); sin `__pycache__` nuevo.
Texto vigente: el v2.3 (b4175f78…). Rigen D1-D56.

### D15: los parámetros de S6, fijados antes de correrla (13:46 hora de Chile)

Se fijan aquí, antes de que exista código de `tendencias` y antes de ver ningún resultado de S6, para que el addendum de
M1 los copie tal cual (D15, como MC-49 para S4). Son los valores por omisión de `sintetico.red_s6` en `sintetico.py`
f87148e775c52243a288c2ca045806f4b567ecbd0ebf4e868dad68849fd3fe0e (SIN-12); nadie cambia `sintetico.py` en esta ola.
- **S6-1. La red.** 20 estaciones históricas de 2000 a 2024, fuera de los valles, y 120 nuevas desde 2010 en toda la
  región (MC-07); región lat −35,0 a −33,0 y lon −71,5 a −70,0; valles −71,0 ≤ lon ≤ −70,6; altitudes 300 m en los
  valles y 900 m fuera, más N(0; 50 m); 25 comunas con 4 celdas cada una y w_ghs uniforme en [100; 5.000]; paso horario;
  semilla 20261023.
- **S6-2. La verdad y el fondo.** Verdad = clima + anomalías, sin tendencia; clima = 15 − 6,5·z/1.000 más un ciclo
  anual de 5 K (máximo a mediados de enero) y uno diario de 4 K (máximo a las 19 UTC); fondo = clima + β + deriva, con
  β = −1,5 K en los valles y 0 fuera; anomalías con correlación exp(−d/L), L = 100 km, σ = 1,5 K, AR(1) horario con
  τ = 48 h, y media exactamente 0 en cada punto × mes × año (MC-50).
- **S6-3. Los dos casos.** Sin deriva (`deriva_k_decada` = 0) para «B falla TF1», «A, C y C_est dan 0» y «AB pasa»;
  con 0,3 K por década desde 2000 para la compuerta de deriva.
- **S6-4. Los hiperparámetros (nuevo; pregunta P79 al cierre).** El texto no dice con qué (L, λ, κ) corren B y AB en
  S6, y de eso depende la compuerta. Rige la lectura más estricta: cada afirmación de S6 y la compuerta se evalúan en
  las 60 combinaciones de §4.2, y B o AB pasan la compuerta sólo si cumplen las dos cotas de TF2 en las 60. Razón: los
  hiperparámetros de producción se eligen en M3-4, después de la compuerta, así que ésta debe valer para cualquiera.
- **S6-5. Qué queda fijo entre escenarios.** A, las climatologías r̄, los δ y los coeficientes de C y de C_est son los del
  producto con la red completa, en TF1 (lo dice §5.7) y en TF2 (lo exige «A, C y C_est dan artefacto 0 por
  construcción»). En B y AB la lista de 30 vecinos es la de la red completa, fija por punto (§4.2), y el escenario sólo
  cambia qué estaciones están disponibles en cada hora.
- **S6-6. El producto en S6.** Sólo T; una sola altitud de celda (la `z_m` de la red). La TF por uso (MC-04) se prueba
  aparte, con una prueba unitaria.

### Reparto

| Dueño | Módulos y pruebas | Entrega |
|---|---|---|
| I15 | `tendencias.py`; `test_tendencias.py` | S6 y la compuerta de deriva (`deriva_s6.json`, por `salidas`, en una carpeta temporal en las pruebas); TF1 y TF2 por candidato × uso × variable en `ESQUEMA_TF` (MC-04, MC-47, MC-48, EMC1-2); redes histórica y constante; la TF de contaminantes y su muestra (S16, Anexo B) |
| I16 | `producto.py`; `test_producto.py` | S15 (int16 en los extremos); `correccion` por lotes de puntos (PED-6) para A, B, AB, C y C_est (C_est con el clima del estado en las celdas, A14; estáticos con `z_e5l`, TIP-22); `campos` con `fondo_era5l.producto_desde`; el NetCDF de 0,1° en memoria (MC-08); la finitud de E0 (MC-51) |
| I17 | `salidas.py`; `test_salidas.py` | S7 (escritura): la clase la fija la ruta (`ceguera.clase_de_ruta`) o, si no, la declarada (P42, D53); `referencia` en los documentos (D13); `GuardaResiduo` sobre los bytes; escritura atómica; ni /Volumes ni los repositorios; recibo; `publicar_m5` como paso aparte |
| I4 (encargo corto) | `ceguera.py`; `test_ceguera.py` | Las clases de P42 y P43 fijadas por la ruta (D53) y `estaticas_celda_c` en `test_s07_esquemas_de_tipos` (pendiente de la ola 3) |

### Acuerdos de interfaces nuevos

- **A19. El NetCDF de 0,1° se arma en memoria.** `producto.mes_01deg(…) -> bytes` usa netCDF4 sin disco (`memory=`) y
  marca esa línea con «# no-escribe: <motivo>» para el detector de §0, regla 8. Sólo `salidas` escribe los bytes.
- **A20. La TF no importa `producto`.** `tendencias` y `producto` son de la misma capa: `tendencias` arma el producto de
  cada candidato con `candidatos` y `fondo_era5l` (§5.7: «sobre el producto de cada candidato, no sobre R»). Si una
  fórmula se repite, se copia con su prueba de paridad, como en las olas anteriores.
- **A21. La finitud de E0 (MC-51).** `producto.fraccion_finita` cuenta puntos-hora con fondo y con producto finito;
  quien recorre las celdas pobladas y las estaciones de validación (I20) suma los conteos y divide al final.
- **A22. Las clases de las salidas nuevas.** Las fija la ruta en `ceguera` (encargo de I4). Mientras tanto, quien
  escribe declara la de P42 (D53); `salidas` rechaza una declarada distinta de la fijada.

Reglas de la ola: las de las olas anteriores (un dueño por módulo y su prueba; nadie edita `tipos.py`,
`test_meteo_combinada.py`, `test_integracion.py`, este documento ni el módulo de otro; pedidos y preguntas al
coordinador; intérprete fijado con `-B` y los hilos en 1; sin `__pycache__`; ningún dato real; sin commits).

## Ola 4 cerrada (2026-10-27)

Los tres módulos de la ola 4 quedaron implementados, cada uno por su dueño, con sus lecturas en el encabezado, y pasaron
por un revisor que no los escribió (contraste con el v2.3, el diseño y D1-D56, recálculo independiente donde hacía falta,
y mutaciones en memoria, un proceso por mutación) y por la corrección de su dueño. Hubo además dos encargos cortos: I4
(`ceguera`, las clases de P42 y P43 por la ruta, y después las correcciones de su revisor) e I13 (`candidatos`, el costo
del diseño de C sin cambiar ningún bit). Nada se escribió fuera de `meteo_combinada/`; `reloj_dmc/`, el código fijado y
`v2/` no se tocaron; ningún dato real se abrió (ni DMC, ni el reloj, ni SINCA, NASADEM, ERA5L o GHS-POP reales); nada en
LOCAL ni en APH. Sin commits.

**Entregas de §6 del diseño:** S6 y la compuerta de deriva; S15 (int16); S7 (escritura); el hito 3 de integración (TF de
S6 con todos los candidatos). Todas corren y ninguna queda omitida.

### Qué entregó cada dueño (después de la revisión)

| Dueño | Módulo | Pruebas | Lecturas | Revisión → corrección |
|---|---|---|---|---|
| I15 | `tendencias.py` | 31 en verde (el esqueleto tenía 9 «por implementar»), ≈ 195 s | TEN-1 a TEN-22 | Sin bloqueantes; un mayor para el autor (la compuerta y S6-4, P79) y diez menores: el borde de «pasa», la muestra de la TF de contaminantes sin fijar, `compuerta_deriva` sin exigir las 60, la media nacional del escenario completo, tres caminos sin prueba, `deriva_s6.json` sin pasar por `salidas`, la compuerta sin comprobar que la deriva entró, y tres lecturas. Recálculo independiente de la compuerta en 11 casos: coincide hasta ≈ 10⁻¹⁴. De 50 mutaciones, 37 detectadas, 6 equivalentes y 7 sin prueba; las 7 se detectan tras la corrección |
| I16 | `producto.py` | 32 en verde (3), ≈ 7 s | PRO-1 a PRO-18 | Sin bloqueantes; dos mayores (θ y α distintos por variable sin probar; el costo de C) y ocho menores (recorte de HR, «todas» en `hay_fondo`, horas con huecos, cotejo por identidad, atributos del NetCDF, conteo por omisión, S9 entre procesos, nombres de huella). De 76 mutaciones, 68 detectadas, 2 equivalentes y 6 sin prueba; con la corrección, las 6 y 15 nuevas se detectan |
| I17 | `salidas.py` | 21 en verde (5), ≈ 1,5 s | SLD-1 a SLD-14 | Sin bloqueantes; cuatro mayores (la clase dependía de la raíz y de las mayúsculas; pruebas de rechazo sin red de seguridad; volver a sellar borraba el recibo de M3-4; dentro de `validacion/` una subcarpeta de insumo cambiaba la clase, de `ceguera`) y catorce menores (vínculos duros, el alias `/System/Volumes/Data`, comprimidos ajenos, «.gz», pruebas que pasaban por otra razón, guardas sin prueba, el AP real como destino, nombres que no caben en `sha256.json`, publicación interrumpida, fsync, la corrida por hilo, clases sin ruta, la política publicada, firmas). De 46 mutaciones, 38 detectadas; tras la corrección, 25 de 26 (la otra la atajan dos capas anteriores) |
| I4 | `ceguera.py` | 33 en verde (27) | CEG-19 y CEG-20 cambiadas; CEG-21 nueva | Las 12 mutaciones del revisor se detectaron; corregidos H5 (carpetas ancladas al comienzo del nombre relativo a la corrida, con «m6/» como único prefijo), H14, H15, H16 (`qc/no_normalizables.csv` resumen) y H6 (el alias del volumen de datos de macOS); y PED-6 (`recibos/recibo_*.json` procedencia) |
| I13 | `candidatos.py` | 32 en verde (29) | CAN-18 nueva | Encargo de costo: las indicadoras de macrozona una vez por código y el diseño en bruto por bloques, sin cambiar ningún bit ni ningún error (copia literal de la ola 3 en la prueba). En 2.048 puntos × 744 h, `diseno_c` de 4,45 a 0,78 s y `predecir_c` de 6,32 a 2,73 s |

Lo principal de cada entrega:
- **I15.** Redes histórica y constante (las tres reglas y «ninguna», MC-47), escenarios «cambio», «completo» y «constante»
  (la lista de 30 vecinos de la red completa; el escenario sólo cambia la disponibilidad, S6-5), medias comunales por lotes
  de un mes y 4.096 celdas (PED-6, MC-37), TF1 y TF2 con la media y el P95 ponderados de MC-48 y las cotas de
  `constantes`, la regla de «pasa» en un solo lugar (≤ en las dos cotas), A, C y C_est con media, P95 y máximo de |Δ_c|
  ≤ 10⁻⁶ o error, TF2 «no evaluable» en todos los candidatos (EMC1-2), la TF por uso (MC-04, MC-55) en `ESQUEMA_TF`
  (pasa por `decision.compuertas` y `decidir_combinacion` en los 5 pares uso × grupo), la compuerta de deriva y el
  contenido de `deriva_s6.json` (escrito por `salidas` como resumen en la prueba), y el Anexo B (muestra con la
  subsecuencia «tf_contaminantes/<cod_comuna>» y la verificación de un mes de DEC-14).
- **I16.** `correccion` por lotes de puntos para A, B, AB, C y C_est con las funciones de `candidatos` (paridad bit a bit
  con `predecir_prueba`, también con θ y α distintos por variable), `campos`, `producto_mes`, int16 con error ante todo
  desborde, el NetCDF de 0,1° en memoria con bytes deterministas entre procesos, la finitud de E0 por conteos enteros
  (`conteo_finito`, `conteo_finito_c` sin calcular R, y `pasa_e0` por conjunto).
- **I17.** `escribir` (la carpeta de la corrida sólo con las formas de ENT-4; la ruta léxica antes que la resuelta, sin
  consultar /Volumes ni su alias del volumen de datos; la clase fijada por la ruta relativa a la corrida, y sin ruta sólo
  métrica, resumen o documento; bytes deterministas; privacidad también en lo comprimido; `GuardaResiduo`), los archivos
  sólo agregado, `sha256.json`, el recibo (un recibo nunca se borra: al volver a sellar se archiva en `recibos/`) y
  `publicar_m5` como paso aparte (también la política, P95).
- **I4.** CEG-20: las clases de P42 y P43 por la ruta; carpetas ancladas al comienzo del nombre relativo a la corrida, con
  «m6/» como único prefijo; patrones con «/» anclados al nombre entero; `m6/` resumen; los recibos archivados
  procedencia; `qc/no_normalizables.csv` resumen. CEG-21: el alias `/System/Volumes/Data` de macOS.
- **I13.** CAN-18: el diseño de C sin lazos por fila en las indicadoras, sin cambiar ningún bit.

**El resultado de S6 y de la compuerta de deriva** (medición para el addendum; las 60 combinaciones de (L, λ, κ), S6-4):

| Candidato | Prueba | Pasan | Media ponderada | P95 máximo |
|---|---|---|---|---|
| A | TF1 y TF2 | 60/60 | 0 exacto | 0 |
| C y C_est | TF1 y TF2 | todas (5 α) | 0 exacto | 0 |
| B | TF1 | 0/60 | 0,199 – 0,422 K | 1,49 K |
| AB | TF1 | 60/60 | 0,0009 – 0,0024 K | 0,0054 K |
| AB | TF2 sin deriva | 60/60 | ≤ 0,0014 K | 0,0031 K |
| **B, compuerta de deriva** | TF2 con 0,3 K por década | **0/60: falla** | 0,128 – 0,237 K | 0,724 K |
| **AB, compuerta de deriva** | TF2 con 0,3 K por década | **30/60: falla** | 0,020 – 0,073 K | 0,079 K |

La red constante es la de r2000_2025, con las 20 históricas: TF2 es evaluable (EMC1-2). AB falla siempre por la media
(cota 0,05 K), en las combinaciones con L ≥ 25 km y κ chico (la peor, L = 200, λ = 0, κ = 0,05); pasa en todas las de
L = 10 y en las de κ = 1. La causa, según el implementador y su revisor: la anomalía de cada estación nueva se toma contra
su r̄ de 2010-2024, que trae más deriva que el de las históricas, y su llegada mete un escalón en 2010 en la red completa.
El revisor lo recalculó con código propio en 11 casos y coincide hasta ≈ 10⁻¹⁴. **Con S6-4, B y AB quedan fuera de E0 en
todos los usos** (§5.7): no se ajustó nada; queda como pregunta P79. La medición está fijada como regla de regresión
(`MEDICION_DERIVA_S6` = {B: 0, AB: 30}).

### Integración del coordinador

1. **`tipos.py` (TIP-22 actualizada).** `ESQUEMA_ESTATICAS_CELDA_C` entra en `ESQUEMAS` (pedidos de I4 e I17). No cambia el
   esquema; `test_ceguera` ya lo contaba entre los que sólo pasan como insumo. `test_tipos` exige ahora que esté.
2. **`test_meteo_combinada`.** Salen de `EN_CURSO` `test_tendencias.py`, `test_producto.py` y `test_salidas.py`. El índice de
   §9 ya no informa S6: quedan S8, S9 y S14 (ola 5).
3. **Comprobado:** detector de literales en verde (`TOLERADOS` vacío), grafo por capas, escritura sólo en `salidas`,
   `entorno` y `sintetico`, privacidad del paquete (ni la carpeta de usuario ni la arroba fuera de decoradores), ningún `__pycache__`
   nuevo, nada nuevo en LOCAL ni en la auditoría de APH, y en AP nada fuera de `meteo_combinada/` (lo modificado en AP es
   de otros flujos, de antes de hoy).

### Acuerdos nuevos

- **A23. `salidas` es la puerta de toda escritura (I17 → I15, I20, I21, I22).** `escribir(ruta, contenido, *, clase,
  esquema=None, referencia=None, raiz=None, metadatos=None) -> sha256`, con `raiz=` o dentro de `corrida_en_curso(…)`;
  `agregar_linea` para `avance.jsonl` e `intentos_*.jsonl`; `sellar_corrida` (`sha256.json` y el recibo, archivando el
  anterior); `publicar_m5` aparte. La raíz sólo puede ser `v1/m1[/sub]`, `v1/m2a[/sub]`, `v1/<ETIQUETA>` o
  `v1/<ETIQUETA>/m6` (o su análogo en la carpeta temporal).
- **A24. La pasada de TF (I15 → I20; PED-c).** `fondo(h, índices)` da los campos `CAMPOS_F` hora × celda; el clima del
  estado en las celdas va con el operador de su uso; dos pasadas, ambiental (z_media) y salud (z_poblada); los meses se
  reparten entre procesos y se suman con `acumular` en su orden; `horas_validas_anio` de 2000-2025 se arma una sola vez
  para `validacion` y `tendencias`.
- **A25. La finitud de E0 (I16 → I20; A21 revisado).** Dos conteos, celdas pobladas en todas las horas de la pasada de TF
  y estaciones de validación, cada uno ≥ 99 % (`producto.pasa_e0`, P87); las estaciones de D34 no entran (P88); para C y
  C_est, `conteo_finito_c` (sin calcular R).
- **A26. La fábrica de la TF de contaminantes (I15 → I19; PED-d).** `fabrica(modelo, variante, escenario, celdas, dias)`
  → día × celda, que arma las columnas de la variante con la red del escenario de cada variable.

### Cambios de firma (para el anexo de firmas)

- **Incompatibles:**
  - `tendencias`: `compuerta_deriva(resultados_s6, *, umbrales)`; `medias_comuna_anio(…, *, orden=…)` da las sumas del
    lote; `tf1` y `tf2` reciben `MediasComunaAnio` y sus diccionarios llevan `max_abs`; `muestra_tf_contaminantes` da un
    arreglo estructurado (`DTYPE_MUESTRA`); `tf_contaminantes(…, *, verificacion_un_mes=…)`.
  - `producto`: `correccion(…, *, umbrales, uso, celdas=None, …)` con `hiper` por variable; `mes_01deg(…, *, uso,
    ganador)`; `fraccion_finita`, `conteo_finito` y `hay_fondo` con `variables=` o `grupo=` obligatorio.
  - `salidas`: `escribir(…, *, referencia=None, raiz=None, metadatos=None)` exige `raiz` o una corrida en curso.
- **Más estrictos:** `ceguera.clase_de_ruta` ancla las carpetas y puede lanzar `ValueError` (dos patrones de clases
  distintas); `producto` rechaza C en lo crónico y lotes de horas con huecos.
- **Aditivos:** en `tendencias`, todo lo de su sección 1 que §3 no nombraba (`escenarios_tf`, `PasadaTF`, `celdas_tf`,
  `filas_tf`, `tf_por_uso`, `combinaciones_nucleo`, `contenido_deriva_s6`, `dias_tf_contaminantes`…); en `producto`,
  `producto_mes`, `conteo_finito`, `conteo_finito_c`, `sumar_conteos`, `hay_fondo`, `pasa_e0`, `direccion_hacia`,
  `estado_c_puntos`, `formato_int16`, `atributos_01deg`, `ConteoFinito`, `ErrorProducto` y `DesbordeInt16`; en `salidas`,
  `corrida_en_curso`, `hay_corrida_en_curso`, `vigilar_residuo`, `agregar_linea`, `inventario`, `escribir_sha256`,
  `sellar_corrida`, `fallas_de_cierre`, `carpeta_publicacion`, `clase_de_salida` y `es_ap_real`, con sus constantes.

### Lecturas nuevas o cambiadas (en el encabezado de cada módulo; van al addendum de M1)

- **TEN-1 a TEN-22** (`tendencias`), con S6-4 y S6-5 como TEN-15 y TEN-16.
- **PRO-1 a PRO-18** (`producto`), con la nota para S14 en PRO-10.
- **SLD-1 a SLD-14** (`salidas`).
- **CEG-19 y CEG-20 cambiadas, CEG-21 nueva** (`ceguera`).
- **CAN-18** (`candidatos`).
- **TIP-22 actualizada** (coordinador).

### Diferencias con el diseño (para el addendum de M1)

- **20.** El motor del producto en la TF vive en `tendencias` (A20), con dos fórmulas copiadas con prueba de paridad (la
  interpolación de A y el producto) y C reasociado como X·(T·coef) (≤ 10⁻⁹ frente a `predecir_c`).
- **21.** `salidas` acepta sólo las raíces de ENT-4 y fija la clase por el nombre relativo a la corrida; las carpetas de
  `ceguera` se anclan al comienzo de ese nombre (CEG-20), cuando antes mandaba la más interior (CEG-19).
- **22.** Las guardas de `reloj_dmc.entorno` que reexporta `entorno` (`prohibido_volumes`, `prohibido_repositorios`)
  distinguen mayúsculas y no ven el alias `/System/Volumes/Data`; no se tocan (están fijadas con la clausura del
  reloj). `salidas` (SLD-2) y `ceguera` (CEG-21) lo compensan, y sólo `salidas` llama a `escribir_atomico`.
- **23.** Un recibo nunca se sobrescribe: al volver a sellar, el anterior se archiva en `recibos/recibo_<n>.json` (P90).
- **24.** La finitud de E0 se cuenta por conjunto (celdas y estaciones), no sumando todo (P87).

### Preguntas para el autor (cierre de la ola 4)

Ninguna bloquea la ola 5. Mientras no haya respuesta, rige lo que dice cada una (la lectura más estricta o, si el texto
no calla, la literal).

**Tendencias (I15 y su revisor).**
- **P79. Los hiperparámetros de S6 y la compuerta de deriva (S6-4), con el resultado a la vista.**
  - **Cita.** §5.7: «B y AB deben cumplir las cotas de TF2. El que no las cumple queda fuera de E0 en todos los usos»;
    §9, S6: «su resultado queda en el addendum de M1 y decide su entrada a E0».
  - **Problema.** El texto no dice con qué (L, λ, κ) corren B y AB en S6. Con la regla que el coordinador fijó antes del
    código (S6-4: pasar en las 60 combinaciones), B pasa en 0 y AB en 30: los dos quedan fuera de E0 en todos los usos.
    Con «al menos una», o con una combinación declarada de antemano, AB podría entrar. Si AB y B quedan fuera, en todos
    los usos compiten sólo A y C (C_est en lo crónico), rige siempre el paso 5 de §6.2 en lo crónico, y la TF de B y AB
    (el costo dominante de M3-4) se calcula igual para la tabla pero ya no puede cambiar ninguna decisión.
  - **Rige y se propone.** Ratificar S6-4: los hiperparámetros de producción se eligen en M3-4, después de la compuerta,
    y ésta debe valer para cualquiera. Si el autor la cambia, se registra como decidido después de ver S6 (aunque antes
    de la DMC).
- **P80. El peso en la TF de contaminantes (P-TEN-1 y P-TEN-6).**
  - **Cita.** Anexo B: «hasta 50 celdas por comuna, con probabilidad proporcional a w_ghs» y «media ponderada de |Δ_c|».
  - **Problema.** Sortear en proporción a w y además ponderar por w pesa dos veces la población; y el sorteo sucesivo sin
    reposición no da inclusión proporcional (en una comuna de prueba, la celda de mayor peso entra 6,8 veces más que la de
    menor, aunque pesa 20 veces más).
  - **Rige y se propone.** La literal: sorteo sucesivo (`Generator.choice` sin reposición, con la subsecuencia de MC-44) y
    media ponderada. Alternativa: inclusión proporcional exacta (sistemática, con tope en 1) y media sin el segundo peso.
- **P81. «Con la misma cota por década» en la regla r2010_2025 (P-TEN-2).**
  - **Rige y se propone.** Son las cotas de TF2 de la tabla de §5.7, que no cambian con un período más corto.
    Alternativa: exigir el 80 % en cada década.
- **P82. La red de R_T en el producto de Td (P-TEN-3).**
  - **Cita.** §4.1: «Td = mín(Td_F + R_Td, T)»; §5.7, escenarios por variable.
  - **Rige y se propone.** En el escenario de Td, R_T se calcula con la red de Td. Efecto menor.
- **P83. El mes y la tolerancia de la verificación de un mes (P-TEN-4; Anexo B, DEC-14).**
  - **Rige y se propone.** El primer mes de 2015-2019 con días de la muestra (enero de 2015) y 10⁻⁶.

**Producto (I16 y su revisor).**
- **P84. Los estáticos de C en los centros de píxel de 0,1° (P-PRO-1).**
  - **Cita.** §3: «0,1°: … con z = z_E5L. Allí el fondo es ERA5-Land tal cual y sólo se suma la corrección»; §4.6: «Los
    estáticos de una estación son los de su celda».
  - **Problema.** El centro de un píxel cae en la esquina común de cuatro celdas; con los bordes oeste y sur cerrados, «la
    celda que lo contiene» es la del noreste, y su z_media y su Δz no son los del fondo en el píxel.
  - **Rige y se propone.** (a) la celda noreste, como una estación, declarada. Alternativas: (b) la media de las cuatro
    celdas; (c) los estáticos de la celda con z := z_E5L y Δz := 0; (d) los estáticos agregados de las 100 celdas del
    píxel. Sólo importa si C gana algún grupo ambiental.
- **P85. La dirección en calma (P-PRO-2).** Rige 0 (arctan2(0, 0), como `_features.py`) y la convención «hacia». No
  afecta al NetCDF, que no guarda la dirección.
- **P86. «Puntos con fondo» en E0 (P-PRO-3).** Rige punto-hora, con el fondo de las variables del grupo finito; el revisor
  la apoya. Alternativa: un criterio fijo por punto.
- **P87. E0 en celdas y estaciones, ¿juntas o por separado? (N1).**
  - **Cita.** MC-51: «sobre las celdas pobladas y todas las horas de la pasada de TF, y sobre las estaciones de
    validación».
  - **Problema.** Juntas, las estaciones pesan ≈ 0,25 % de los puntos-hora: un candidato con NaN en el 10 % de las
    estaciones pasaría.
  - **Rige y se propone.** Dos fracciones, cada una ≥ 99 % (`pasa_e0`).
- **P88. Las estaciones de D34 en el conteo de E0 (N2).** Rige y se propone: fuera del conteo de estaciones en todos los
  candidatos (C y C_est dan NaN allí por construcción, y D34 las saca «de la evaluación de todos los candidatos»).

**Salidas y ceguera (I17, I4 y su revisor).**
- **P89. Qué se publica en M5 (P-SAL-1).** Cita: §8, «`decision.json`, los resúmenes y las huellas»; §5.3, «Las métricas
  por banda no se publican». Rige: `validacion/` e `informe.md` no se publican. Propuesta del implementador: sumar
  `validacion/` sin `_interno/`; el revisor apoya no publicarla.
- **P90. ¿Un recibo o dos? (P-SAL-2).** Cita: §8, «Cadena de huellas»; §10, testigo externo en M3-4; ENT-4 (M5 escribe
  en la carpeta de su M3-4). Problema: el sello de M5 reescribía el recibo de M3-4, cuya huella pudo citar el testigo.
  Rige: ninguno se borra; el anterior se archiva con sus bytes en `recibos/recibo_<n>.json` y el nuevo lo cita.
- **P91. El CSV sin la versión de su esquema (P-SAL-3).** Cita: diseño §2.3, `qc/no_normalizables.csv`, y «toda tabla
  lleva la versión de su esquema». Rige: el CSV sin versión. Propuesta: citarla, con su sha256, dentro de
  `resumen_qc.json`, o pasarlo a parquet.
- **P92. Dónde vive el cerrojo `intentos_*.jsonl` (P-SAL-4).**
  - **Cita.** §8 lo pone en la carpeta de la corrida; §10 lo usa entre corridas («ya registra una corrida confirmatoria»).
  - **Problema.** Una corrida nueva tiene otra carpeta y no vería los intentos de la anterior; y agregar un intento
    después del sello abre la corrida.
  - **Rige (lo decide I22, ola 6) y se propone.** El cerrojo en `LOCAL/meteo_combinada/v1/` (visible para toda corrida),
    con su copia agregada en la carpeta de cada corrida antes del sello.
- **P93. Cómo se publica una errata (P-SAL-5).** Cita: §10, «Se publican las dos decisiones y su diferencia». Rige:
  `publicar_m5` se niega si ya hay otra publicación en `v1/`. Propuesta: una subcarpeta por etiqueta.
- **P94. Una ruta sin clase no se declara insumo ni procedencia (P-SAL-6, H16).** Cita: P42 (D53): «una salida sin clase
  fijada sigue la declarada». Problema: insumo y procedencia no miran el vocabulario de S7. Rige (la más estricta): sin
  ruta, sólo métrica, resumen o documento.
- **P95. ¿Se publica la política? (P-SAL-7, H17).** Cita: §2.1, paso 4, «La política publicada»; MC-53, «La publicada
  (`politicas_meteo_v1.json`)». Rige (la literal): `publicar_m5` la publica junto a `decision.json`.
- **P96. Carpetas ancladas (H5; I4).** Cita: §8, «`validacion/`: métricas…»; D3 y S7. Problema: con «manda la más
  interior», `validacion/ambiental/…` era insumo. Rige (la más estricta): las carpetas se anclan al comienzo del nombre
  relativo a la corrida, con «m6/» como único prefijo; los patrones con «/», al nombre entero.
- **P97. El aviso SINCA (H14).** Cita: §5.6, «se dice en el resumen». Rige: métrica en `validacion/`, sin publicar.
  Propuesta: llevarlo a un resumen publicado (`informe.json` o `decision.json`).
- **P98. `m6/` como resumen e `informe.html` (I4).** Rige: todo lo suelto en `m6/` es resumen (las laterales restringidas
  de la rama 3 van en `ambiental/` o `m6/ambiental/`); el informe va como `informe.md` (documento) e `informe.json`
  (resumen, con la fracción de §4.6, P43), y `informe.html` no se fija.

**Candidatos (I13).**
- **P99. Un código de macrozona no entero.** `candidatos._bases` aplica `int(c)` antes de `tipos.indicadoras_macrozona`,
  así que 2,5 se trunca a 2 («centro») sin error, aunque `tipos` lo rechaza. Rige lo de hoy (no se cambió para no tocar
  bits ni errores). Propuesta: rechazarlo (`macrozona_cod` es int8 en el esquema, así que no ocurre con datos válidos).

### Pendientes para la ola 5 y siguientes

Reemplazan a los anteriores donde se cruzan; los demás siguen.
- **I18 (`salud`).** S14 no pasa por `producto.campos` (que recorta Td ≤ T): usa `campos_fondo(…, recortar_td=False)` con
  el operador del píxel enlazado (peso 1, Δz = 0, `operador_desde_columnas`) (PRO-10). La representatividad recibe el
  píxel del reloj desde fuera (MC-52).
- **I19 (`ambiental`).** A26 (la fábrica); las laterales restringidas de la rama 3 en `ambiental/` o `m6/ambiental/`
  (P98).
- **I20 (`orquestacion`).** A23 a A25; P-SAL-8: tras un corte duro queda un «.part» y `escribir` se niega sobre él
  (propuesta: la reanudación lo borra sólo si su unidad no figura hecha en `avance.jsonl`, y lo registra); las
  funciones de `producto` (`producto_mes(…, clima_estado=…)`, `conteo_finito_c`, `pasa_e0`); lo de las olas 2 y 3 sigue.
- **I21 (`costo`).** Medir C y C_est en las celdas (hoy, con CAN-18, ≈ 1,8 µs por punto-hora y variable en `predecir_c`;
  en la TF, ≈ 0,54 ms por celda-mes, TEN-14) y la pasada de finitud; las claves de `costo_m1.json` sin «fondo», «era5l»
  ni «R_» (es resumen).
- **I22 (`addendum`, `verificar`).** El addendum lleva TEN, PRO, SLD, CEG-19 a CEG-21, CAN-18, TIP-22, A19 a A26, las
  diferencias 20 a 24, P79 a P99, los parámetros S6-1 a S6-6 (D15) y la medición de S6 por referencia a `deriva_s6.json`
  (P44); `deriva_s6.json` con `tendencias.contenido_deriva_s6`; el cerrojo según P92. El borrador del addendum lo copia
  el coordinador a APH en un paso aparte (`salidas` no escribe en APH).
- **I13 (`candidatos`), si vuelve.** PED-7 y PED-8 de I16 y PED-a y PED-b de I15 (exponer el estado de C desde arreglos,
  `predecir_c` con un estado ya llevado a las horas, A por lotes): hoy se copian con prueba de paridad. `fuera_de_rango_c`
  sigue celda por celda (≈ 20 s en las celdas pobladas). Lo que queda del costo de C es el producto de matrices; bajarlo
  cambia bits.
- **I5 (`sintetico`).** `red_s6` repite un id de celda en dos de sus 100 celdas (PED-g); las pruebas de S6 usan ids
  propios. No se toca `sintetico.py` (D15).
- **I1 (`entorno`), si vuelve.** Diferencia 22: las guardas del reloj que reexporta.

### Cifras al cierre

**Suite:** 697 pruebas: **659 en verde, 38 omitidas y ninguna falla**, en ≈ 333 s con un hilo. Antes de la ola: 621, 566
y 55. El tiempo crece sobre todo por S6 (`test_tendencias`, ≈ 195 s).

**Por archivo de la ola:** `test_tendencias` 31, `test_producto` 32 y `test_salidas` 21, todas en verde; `test_ceguera`
33 (antes 27) y `test_candidatos` 32 (antes 29).

**Las 38 omitidas:**
- 34 «por implementar»: `test_verificar_meteo_combinada` 13, `test_salud` 6, `test_ambiental` 5, `test_orquestacion` 4,
  `test_addendum` 2, `test_costo` 2 y las 2 de S10 de la batería en `test_meteo_combinada`;
- en `test_fijados`, la de huellas de datos;
- en `test_homogeneidad`, la de 2.500 m (P47, D56);
- en `test_meteo_combinada`, el cierre de M1 y el índice de §9 (pendientes S8, S9 y S14).

Sin `__pycache__` nuevo.

**Huellas sha256:**
- `tendencias.py` `1ca7fa879677c4cb061636266e52a402936d1e93e514c89e77670a4d342462c0`; `tests/test_tendencias.py`
  `9a6b920f22a67dc2765c24d9269c6a0a61d7e6d8e0c2ff5505b276d6e4629788`
- `producto.py` `afa56ac51350b0dea290bdf1f509abefcae9365711dbb0516817918db700991d`; `tests/test_producto.py`
  `9de05939552aff6f0277740b854905ecbbd4368a4c0032b691bfd2aa4d359206`
- `salidas.py` `4bc33729e7e346a44c02d3cc63956c7dcaaaa995e9cd704cbb80e55da1ab0b79`; `tests/test_salidas.py`
  `cc4c06da87729f7fd7ad9cb734cb62b42bf7b9a63d0745ff3451fcdabb9645d1`
- `ceguera.py` `8afda807e4917888b725b0f81422d18f2622a858259577bf2d1ac807f24dd02e`; `tests/test_ceguera.py`
  `024b959524373a1e4808c10a887462a0c487161aa67a4ee1d55439fd08dd8b40`
- `candidatos.py` `189931a31f1db9f1f39a80de5ef0ef707d79538c582549dcd38e9478aea895d3`; `tests/test_candidatos.py`
  `db26d1f69e629e6bef16754dfa967ea5add643d48a511170cba310768581f3ce`
- `tipos.py` `31fc3a1ad00ccdc5219ee44796e77be44e0cc3f813901a03b69d6bf964743dab`; `tests/test_tipos.py`
  `17455af8d6a00764f58e457e9f8dfe4e7ea65f718eb68b90d49c380a20b4d603`
- `tests/test_meteo_combinada.py` `e0b7666a1c67de98f27c2bad80e51cabb7069a247af2a1e4848b5b5d5538770f`

## Ola 5: encargos (2026-10-27)

Línea base: la del cierre de la ola 4 (arriba). Texto vigente: el v2.3. Rigen D1-D56 y, mientras el autor no responda,
lo que dice cada una de P79-P99.

### Reparto

| Dueño | Módulos y pruebas | Entrega |
|---|---|---|
| I18 | `salud.py`; `test_salud.py` | S8 (días de 23 y 25 h; media comunal con pesos conocidos; el esquema de `meteo_civil_v3` por AST); la lluvia como hoy (MC-13); la representatividad (§7.2, punto 6; MC-52, con el píxel del reloj como entrada); lo crónico (§7.3); **S14** con datos reales (MC-31, MC-32) |
| I19 | `ambiental.py`; `test_ambiental.py` | §7.1 y Anexo B: `lateral_monitores` (I y D, metadatos de `unir_sidecar` y R21), `operador_grilla`, `mc_bloque` y la unión con `meteorologia_v2.unir_sidecar` real y sus negativas; la fábrica de la TF de contaminantes (PED-d de I15) |
| I20 | `orquestacion.py`; `test_orquestacion.py` | M2a y M3-4 primero (fábrica de entradas con huellas, A8, A14, A16-A18, la pasada de TF de PED-c, S13 de M2a, S9 con 1 y 8 procesos e interrupción); M5 y M6 en una segunda fase, cuando I18 e I19 entreguen |
| I1 (encargo corto) | `fijados.py`; `test_fijados.py` | `reloj_dmc.extraccion.elegir_pixel` por `fijados`, con la clausura ampliada (MC-52) |

### Excepción de datos de la ola (regla 4 del diseño; MC-31)

Sólo S14 (`test_salud.test_s14_regresion_aguda`) lee datos reales, y sólo en lectura: ERA5L de 2024-01 a 2025-01, la
grilla (`enlaces_productos.parquet` y lo que haga falta de `celdas.parquet`), los pesos (`poblacion_celda_anio.parquet`),
los productos v3 de 2024 (civil, UTC−4 y regional) y `config_v3.json`, bajo un `RegistroAccesos` en bloqueo que sólo deja
pasar esas rutas. Sólo informa «igual» o «distinto» y la diferencia máxima; no guarda el producto (§0.4.1). Nada de la
DMC, del reloj, de SINCA, de NASADEM ni de GHS-POP.

### Acuerdos de interfaces nuevos

- **A27. El píxel del reloj para la representatividad (I1 → I20 e I18; MC-52).** `fijados` carga
  `reloj_dmc.extraccion.elegir_pixel` por ruta y huella (la clausura se amplía con `extraccion.py` y lo que importa,
  comprobado en git en AP 1da0236) y lo entrega con la regla de 15 km del reloj. `salud.representatividad` recibe la serie
  t2m del píxel ya elegido; la elige `orquestacion`.
- **A28. M5 y M6 en `orquestacion` (I18 e I19 → I20).** `correr_m5` llama a `producto` (0,1°), a `salud` (civil, UTC−4,
  regional, representatividad y crónico) y a `ambiental` (laterales I y D y operador), con una sola pasada por ERA5-Land
  si se puede (§8 del diseño); `correr_m6` arma la TF de contaminantes con la fábrica de A26 y las ramas con
  `decision.ramas_m6`. Las negativas de M6 y los cerrojos son de I22.
- **A29. La unión con v2 (I19).** `ambiental.comprobar_union` usa `meteorologia_v2.unir_sidecar` real (código fijado, por
  `fijados.cargar_adaptador`), sólo en pruebas y en la verificación; el panel lleva `ts_utc` con zona UTC.

Reglas de la ola: las de las olas anteriores, con la excepción de datos de S14 de arriba.

## Ola 5 cerrada (2026-10-28)

Los tres módulos de la ola 5 quedaron implementados, revisados por quien no los escribió y corregidos por su dueño, y el
coordinador los integró. Hubo además dos encargos cortos: I1 (`fijados`, `elegir_pixel` del reloj, MC-52) e I17
(`salidas`, el sello archivado entero, PED-6 de I20).

**El apagado.** El equipo se apagó la tarde del 2026-10-27, después de que I18, I19, I1 y la primera fase de I20 dejaran su
código en disco (17:19-17:56) y antes de que entregaran sus informes. Al volver se corrió la suite (757 pruebas, 22
omitidas, ninguna falla), se comprobó que nada había quedado a medias salvo `correr_m5` y `correr_m6` (la segunda fase de
I20, todavía en `NotImplementedError`), y se siguió: la segunda fase de I20, las cuatro revisiones independientes y las
correcciones. I18 e I19 se retomaron con dueños nuevos, que leyeron su módulo; I1, I17 e I20 se retomaron con su
contexto. Nada se perdió en disco; los informes perdidos se reemplazan por lo que se ve en el código y en las
revisiones.

Nada se escribió fuera de `meteo_combinada/` y de las carpetas temporales; `reloj_dmc/`, el código fijado y `v2/` no se
tocaron; nada en LOCAL ni en APH. Ningún dato real se abrió salvo los insumos de S14 (ERA5L de 2024-01 a 2025-01, la
grilla, los pesos, los productos v3 de 2024 y `config_v3.json`, en sólo lectura, bajo su registro en bloqueo), que la
regla 4 del diseño y MC-31 permiten. Del reloj, sólo su código y sus umbrales anclados de C0 (FIJ-11); ninguna salida.
Sin commits.

**Entregas de §6 del diseño:** S8, S14 («igual» en civil, UTC−4 y regional de 2024, con diferencia máxima 3,41e-13), la
unión con `unir_sidecar`, S9 (idéntico con 1, 2 y 8 procesos, e interrupción y reanudación) en M3-4 y en M5, S13 (M2a se
detiene con el geopotencial corrido). Todas corren; ninguna queda omitida.

### Qué entregó cada dueño (después de la revisión)

| Dueño | Módulo | Pruebas | Lecturas | Revisión → corrección |
|---|---|---|---|---|
| I18 | `salud.py` | 28 en verde (el esqueleto tenía 6 «por implementar»); ≈ 3,4 s sin la S14 real, que tarda ≈ 150-170 s | SAL-1 a SAL-13 | Sin bloqueantes; un mayor (la S14 sintética no distinguía una comparación que mirara una sola variable) y diez menores (pesos de un año a otro que se cancelaban, representatividad sin bordes ni días civiles, la lluvia con `tp` que baja, Td sin sp, la carpeta de `config_v3`, la dependencia escondida de `fondo_era5l`, lo crónico desde disco, nombres de preguntas, firmas, la batería). De 60 mutaciones, 13 sobrevivían; tras la corrección, las 23 que se repitieron se detectan. La S14 real, cuatro veces en total: «igual» en las tres carpetas, 3,41e-13 |
| I19 | `ambiental.py` | 41 en verde (5), ≈ 13 s | AMB-1 a AMB-18 | «Aprobado con reservas»: un alto (las horas del panel después del último dato de ERA5-Land detenían toda la lateral), la circularidad de la rama 3, el formato de `decision.json` frente a `orquestacion` (ya corregido por I20), pruebas que no probaban lo que decían, el panel sin atar a su huella, el tamaño del operador, la política sin verificar. De 42 mutaciones, 31 detectadas; tras la corrección, 30 de 30 propias |
| I20 | `orquestacion.py` | 46 en verde (4), ≈ 137 s | ORQ-1 a ORQ-41 | «No se cierra tal como está»: tres mayores de memoria (cada trabajador recibía una copia de todo: ≈ 13-15 GB por trabajador en la selección; RR06 con los 321 meses de una vez; la finitud de E0 con el mes entero en todas las celdas), negativas que faltaban (artefactos sin manifiesto, el registro de M2a, `permitir_cargados`), una negativa que dejaba la carpeta atada, la huella agregada de los manifiestos, y pruebas que no vigilaban ORQ-22 ni otras lecturas centrales. De 42 mutaciones, 24 detectadas. Corregido: el contexto viaja por referencia a disco (16-117 KB por trabajador en la red de prueba; ≈ 7-7,5 GB estimados por trabajador en la selección real), RR06 por años, la finitud por lotes, las negativas y 17 pruebas nuevas. Un error real hallado al probar: las negativas de M2a leían todos los meses antes de la alineación |
| I1 | `fijados.py` | 37 en verde (30) | FIJ-11 nueva; FIJ-2 cambiada | «Aprobado con observaciones»; la ceguera confirmada (sólo los diez archivos de código y el texto y el JSON de C0) y las diez huellas en AP 1da0236. Corregidos: la comprobación «antes de cargar» por archivo, `permitir_cargados` ya no vuelve propio lo ajeno, la guarda contra un `.pyc` en `reloj_dmc/__pycache__`, `PixelReloj.enlazar` con `coordenadas_en_rango` del reloj, y la huella del JSON del v1.2 para M2a. De 24 mutaciones, 16 detectadas; las 5 que eran huecos, ahora detectadas |
| I17 | `salidas.py` | 22 en verde (21) | SLD-10 cambiada | PED-6 de I20: al volver a sellar se archivan el recibo y su `sha256.json` (`recibos/recibo_<n>.json` y `recibos/recibo_<n>_sha256.json`), y `fallas_de_sello_archivado` verifica el sello archivado |

Lo principal de cada entrega:
- **I18.** Días civil (23, 24 o 25 h), UTC−4 y regional como `exposicion_horaria_v3`; medias comunales con w_ghs del año en
  las celdas de §7.2, punto 1, por lotes y mes a mes; el esquema de `meteo_civil_v3` (S8); la lluvia bit a bit como hoy
  (MC-13); la representatividad (§7.2, punto 6; MC-52) con los días válidos de `validacion`; lo crónico (§7.3); S14 con el
  píxel enlazado, Δz = 0 y sin recorte, sin pasar por `producto.campos`, bajo un registro en bloqueo.
- **I19.** Las laterales I (9 `mc_*`) y D (9 `fe_*` + 5 `dmc_R_*`) en la celda del monitor con la z de la celda, con el
  panel atado a su huella, la política leída, la última hora de ERA5-Land y partes por año (`unir_partes`); el operador de
  la grilla (esquema `/2`, sólo lectura, con sus umbrales); `mc_bloque`; la fábrica de la TF de contaminantes (A26); la
  unión con `unir_sidecar` real y sus negativas.
- **I20.** M2a, M3-4, M5 y M6 por fases y unidades reanudables, con `avance.jsonl`, la fábrica de entradas con huellas, el
  reparto en un grupo de procesos propio (idéntico con 1, 2 y 8), S13, las alarmas como única detención, la decisión con
  huellas, el sello; M5 (0,1°, salud, representatividad, crónico, laterales y operador) en la carpeta de su M3-4 con el
  recibo archivado; M6 (TF de contaminantes, ramas, restringido, S6, `decision_m6.json`) en `m6/`.

### Integración del coordinador

1. **`test_meteo_combinada`.** Salen de `EN_CURSO` `test_salud.py` y `test_orquestacion.py`. El índice de §9 ya no informa
   pendientes. `DEPENDENCIAS` suma `fondo_era5l` a `salud` (PED-1 de I18: la dependencia llegaba por `producto` sin
   que el grafo la viera).
2. **El diseño.** La fila de `salud` en §1 nombra `fondo_era5l`; §9.4 suma la clausura ampliada de FIJ-11 (`extraccion`,
   `numerico` y `umbrales` del reloj en AP 1da0236), el JSON de umbrales de C0 del reloj y, sólo por su huella, el JSON y el
   generador del v1.2.
3. **Comprobado:** detector de literales en verde, grafo, escritura sólo en `salidas`, `entorno` y `sintetico`, privacidad,
   ningún `__pycache__` nuevo, nada en LOCAL ni en APH, y en AP nada fuera de `meteo_combinada/`.

### Acuerdos nuevos

- **A30. Los trabajadores leen por referencia (I20; H1 de su revisión).** El contexto de `repartir` lleva rutas por alias y
  sha256, no tablas; cada proceso rearma una vez lo suyo desde el disco, con la misma función y los mismos bytes. En las
  corridas reales, `Cfg.permitidas` debe incluir los meses de ERA5-Land, los paneles de la red 2 y la DMC (PED-11, I22).
- **A31. M5 y M6 y sus carpetas (I20).** M5 escribe en la carpeta de su M3-4, con una línea de compuerta propia en su
  `avance.jsonl`, y vuelve a sellar (el sello anterior queda archivado, I17); M6 escribe en `m6/` con su propio
  `avance.jsonl`; el operador restringido cita la huella de `m6/ramas_m6.json` (`ramas_m6_sha256`), y `decision_m6.json` va
  al final con las huellas de lo vigente.

### Cambios de firma (para el anexo de firmas)

- **Incompatibles:**
  - `salud`: `pesos_comuna` devuelve `PesosComuna` (la matriz en `.matriz`); `regresion_s14(…, *, esquema_v3, umbrales,
    exigir_huellas=True, lote_celdas=…)` devuelve también el motivo y las huellas.
  - `ambiental`: `lateral_monitores(pol, decision, operador, *, variante="I", panel, monitores, rutas, politica, h_ultima,
    anios=None, policy_sha256=None, panel_sha256=None, …)`; `operador_grilla(…, ramas_m6_sha256=…)`; `leer_operador`
    sólo acepta bytes.
  - `orquestacion`: `Cfg.recorte` y `Cfg.deriva` sin valor por omisión en los modos reales (y M6 entre ellos);
    `ENTRADAS_M2A` suma `pesos`; `correr_m6` usa `Cfg.procesos`; `Cfg.fabrica_m6(contaminante, variante, base)`.
  - `fijados`: `cargar_elegir_pixel(ap, aph, huellas, *, permitir_cargados=False)` → `PixelReloj` (`elegir`, `enlazar`,
    `coordenadas_en_rango`, `radio_km`).
- **Aditivos:** en `salud`, `zonas_por_comuna`, `dias_del_anio`, `pesos_lluvia`, `lluvia_horaria`, `lluvia_comunal`,
  `AcumuladorMeteo` (con `agregar(…, horas=)`), `hr_del_producto`, `insumos_s14`, `metadatos_tabla`, `CLAVES_METADATOS`
  y `MOTIVO_TD_SIN_DATO`; en `ambiental`, `METADATOS_LATERAL` (los 11 de `tipos` más `claves_tras_ultima_hora`),
  `unir_partes`, `ganador_ambiental`, `columnas_bloque` y la fábrica; en `orquestacion`, `Avance.iniciar()`,
  `huella_del_codigo()`, `identidad_funcion()` y las fases; en `salidas`, `fallas_de_sello_archivado`; en `fijados`,
  `HUELLAS_PIXEL_1DA0236`, `HUELLAS_CLAUSURA`, `SHA_JSON_RELOJ_C0`, `SHA_JSON_RELOJ_V1_2` y `SHA_GENERAR_V1_2`.

### Lecturas nuevas o cambiadas (van al addendum de M1)

- **SAL-1 a SAL-13** (`salud`).
- **AMB-1 a AMB-18** (`ambiental`).
- **ORQ-1 a ORQ-41** (`orquestacion`).
- **FIJ-11 nueva y FIJ-2 cambiada** (`fijados`); **SLD-10 cambiada** (`salidas`).

### Diferencias con el diseño (para el addendum de M1)

- **25.** M5 hace dos pasadas por ERA5-Land, no una: la representatividad necesita el período entero de cada estación
  antes del producto sin ellas (ORQ-23; P114).
- **26.** M5 escribe en la carpeta de su M3-4 y la vuelve a sellar; M6, en `m6/` (A31).
- **27.** Salidas que §8 no nombra: `ambiental/partes/`, `salud/cronico/meteo_<año>.parquet`,
  `salud/representatividad/excluidas.json`, `m6/ramas_m6.json` y `m6/s6.json`.
- **28.** Las laterales cubren sólo hasta la última hora de ERA5-Land; las claves posteriores quedan fuera y se cuentan
  (P106).
- **29.** El operador restringido cita `m6/ramas_m6.json`, no `decision_m6.json` (circularidad; A31).
- **30.** `salud` depende de `fondo_era5l` (por `producto`), declarado en §1.
- **31.** La clausura del reloj ampliada para `elegir_pixel` va al addendum de M1 (§9.1 del diseño decía «en ese paso»,
  M5).
- **32.** La negativa del registro de M2a la hace `orquestacion` (P119), no `verificar`.
- **33.** M6 necesita la fábrica de producción v2 (`Cfg.fabrica_m6`), que no está escrita: sin ella M6 no corre.

### Preguntas para el autor (cierre de la ola 5)

Ninguna bloquea la ola 6. Mientras no haya respuesta, rige lo que dice cada una.

**Salud (I18 y su revisor).**
- **P100. Una estación sin r o sin cociente calculables en la representatividad (P-SAU-1).** Cita: §7.2, punto 6. Rige (la
  más estricta): se excluye de la sensibilidad.
- **P101. Td del fondo cuando falta sp o t2m (P-SAU-2).** Cita: S14, «sin ajuste de Td ni de p». Problema: con Δz = 0,
  `fondo_era5l` exige p finita para la identidad, así que Td_F sale NaN donde la v3 da d2m − 273,15 (en 2024 no ocurre;
  en el 0,1°, con Δz = 0, tampoco sería «ERA5-Land tal cual»). Rige: S14 usa `campos_fondo` y dice «distinto» con su
  motivo. Propuesta: que `fondo_era5l` (I7) no exija p finita con Δz = 0 (PED-3 de I18).
- **P102. La huella de la carpeta entera de `config_v3.json` (P-SAU-3).** Rige: se declara y no se compara. Propuesta:
  agregar a los insumos de S14 el JSON de verificación de la v3 con su huella fijada y comparar con él.
- **P103. Lo crónico de 2026 con el año incompleto (P-SAU-4).** Rige: se promedian los días que trae la tabla, y M5 elige
  los años. Propuesta: sólo años completos (como `covariables`, 2000-2025).
- **P104. Qué informa S14 (P-SAU-5).** Rige: además de «igual» o «distinto» y la diferencia máxima, el motivo (sin
  números) y las huellas.
- **P105. `dia` int32 frente a `fecha` date32 (P-SAU-6).** Rige `dia` int32 (el esquema de §2.3 del diseño); el adaptador
  de la Enmienda 4 convierte.

**Ambiental (I19 y su revisor).**
- **P106. Las horas del panel después del último dato de ERA5-Land.** Cita: §3, «a su último dato … sin interpolación
  temporal»; R21. Rige: fuera de la lateral (NaN tras la unión) y contadas en `claves_tras_ultima_hora`.
- **P107. En «cambio», `mc_d2m` contra la T de la red de Td (P-AMB-1; P82).** Puede quedar `mc_d2m > mc_t2m`, y dentro de la
  TF I y D no son «integrar contra separar» con las mismas R. Rige y se propone ratificarlo.
- **P108. El día de la muestra de la TF de contaminantes (P-AMB-2).** Rige: día UTC; si v2 predice por día civil, su
  fábrica pasa `horas_de_dias`.
- **P109. El tamaño del operador (P-AMB-3; MC-15).** Hasta ≈ 2,6 GB con 8 juegos de núcleo (≈ 1,3 GB con 4), frente a los
  ≈ 200 MB de §7.1. Rige: se acepta y lo mide I21.
- **P110. Qué afirma `source_policy_verified` (H7).** Rige: la política de la corrida, leída y con su huella rehecha; que la
  DMC entró con esa política lo garantiza la cadena de M3-4.

**El píxel del reloj (I1 y su revisor).**
- **P111. Los umbrales del reloj en su C4.** Problema: C4 tomó los umbrales del JSON que nombra el addendum de C1; M1 usa los
  de C0. Propuesta: en M2a, `politicas` compara `configuracion.sha256` de la política publicada (que se puede abrir) con
  `fijados.SHA_JSON_RELOJ_V1_2`; si coinciden, el radio de 15 km es el de C0, porque el generador del v1.2 deja los
  umbrales de C0 salvo «generado_desde» y «bateria» (comprobado por AST). Hay que ratificar esa procedencia.
- **P112. Las coordenadas del píxel en M5 y la lista K2.** Rige: las del catálogo vigente en RELOJ C2, con
  `coordenadas_en_rango` del reloj (`PixelReloj.enlazar`); K2 no cambia el píxel. Pregunta: ¿la representatividad excluye
  las estaciones de K2?

**Orquestación (I20 y su revisor).**
- **P113. SINCA sin coordenadas (P-ORQ-1).** Mientras no se responda, §5.6 no se cumple entero (faltan las métricas en la
  celda y en el punto por terciles de TPI). Propuesta: las coordenadas de «estaciones» en `pliegues_v2_red2.json`, por
  código. Hace falta antes de M3-4.
- **P114. Las dos pasadas de M5 (P-ORQ-3).** Propuesta: que M2a guarde la t2m de los píxeles del reloj y M5 lea los meses
  una sola vez.
- **P115. El día de la representatividad y de la S6 (P-ORQ-4).** Rige el civil, el de la primaria.
- **P116. Píxeles de 0,1° sin celda cuando C gana un grupo ambiental (P-ORQ-5; P84).** Rige «detener» M5. El revisor cree
  que ocurrirá con datos reales (centros en la frontera o la costa). Alternativas: los estáticos de la celda más cercana, o
  NaN en esos píxeles.
- **P117. La memoria frente a D2 (P-ORQ-6).** Con el reparto por referencia, la selección queda en ≈ 7-7,5 GB por
  trabajador, justo bajo el tope de 8 GB de §8; lo que más pesa es el fondo de todas las estaciones (PED-10). Lo mide I21.
- **P118. ¿Una negativa antes de la frontera cuenta como corrida? (P-ORQ-7).** Cita: §10, «una corrida nueva exige una
  errata». Rige y se propone: no; sólo queda en `intentos_aplicar.jsonl`.
- **P119. La negativa del registro de M2a (P-ORQ-8).** Rige: la hace `orquestacion`; I22 ancla la huella del registro en la
  lista cerrada.
- **P120. El π del objetivo de la selección (P-ORQ-9).** Cita: §4.9, «con los pesos del uso (§5.3) calculados en el pliegue
  interno». Rige P62 (D53): un π por uso. Pregunta: ratificarlo o recalcular π con la red del entrenamiento interno.
- **P121. Las 2.000 horas de las bandas (P-ORQ-10).** Rige la literal de §5.3: todas las horas válidas, 2000-2026; π^pob
  sigue por año, 2000-2025.

### Pendientes para la ola 6 y siguientes

- **I21 (`costo`).** Medir con la máquina libre: la memoria real por trabajador en la selección, la TF y M5 (A30, P117) y el
  tamaño del operador (P109); C y C_est en las celdas; las dos pasadas de M5. Claves de `costo_m1.json` sin vocabulario.
- **I22 (`verificar`, `addendum`).** `Cfg.permitidas` en las corridas reales (PED-11); la batería exige que S14 no se omita
  (`PruebasS14.informe` no nulo; hallazgo H11 de la revisión de `salud`); el addendum lleva SAL, AMB, ORQ, FIJ-11, SLD-10,
  A30, A31, las diferencias 25 a 33 y P100 a P121, y la clausura ampliada (`fijados.HUELLAS_CLAUSURA`); la negativa de
  M6 frente a la fábrica.
- **I15 (`tendencias`), si vuelve.** PED-9: `correccion_mes` por lote de celdas.
- **I13 (`candidatos`), si vuelve.** PED-10: que la selección no necesite el fondo de todas las estaciones.
- **I7 (`fondo_era5l`), si vuelve.** PED-3 de I18 (P101).
- **I2 (`constantes`), si vuelve.** PED-2 de I18: `DESFASE_UTC4_H` y los meses fríos.
- **Coordinador.** PED-AMB-1: `claves_tras_ultima_hora` en `tipos.METADATOS_LATERAL` cuando el autor ratifique P106.

### Cifras al cierre

**Suite:** 813 pruebas: **791 en verde, 22 omitidas y ninguna falla**, en ≈ 608 s con un hilo. Antes de la ola: 697, 659 y
38. El tiempo crece por S14 (≈ 150 s, con datos reales) y por `test_orquestacion` (≈ 137 s).

**Por archivo de la ola:** `test_salud` 28, `test_ambiental` 41, `test_orquestacion` 46, todas en verde; `test_fijados` 37
(una omitida, la de datos reales) y `test_salidas` 22.

**Las 22 omitidas:**
- 19 «por implementar»: `test_verificar_meteo_combinada` 13, `test_addendum` 2, `test_costo` 2 y las 2 de S10 de la batería
  en `test_meteo_combinada`;
- en `test_fijados`, la de huellas de datos;
- en `test_homogeneidad`, la de 2.500 m (P47, D56);
- en `test_meteo_combinada`, la del cierre de M1.

Sin `__pycache__` nuevo.

**Huellas sha256:**
- `salud.py` `888a97902ce743b445706a6a77af330aef5ae6b8232c8cf2d5619c212f499f95`; `tests/test_salud.py`
  `e12eb1353a2bc742512834ec0805b3bf5e671e28caa2ec1d7ef2c1359e46eee2`
- `ambiental.py` `1e6cd4f8547d89516a514199e1cdc966c1120ef6b436b3cdf54c64c4f802fa1e`; `tests/test_ambiental.py`
  `6ba2a45c8a3b348099957403a662169c5db52f935141a087e70a5ab5380f3c99`
- `orquestacion.py` `7406e5de3cefeaa37f372a9e57a2727cfd6b533fec151fdd83cd0253c546b70a`; `tests/test_orquestacion.py`
  `7ff919709e394327fd601ab87120b2dbf12dfbc73325abf43fc711dec0b3f900`
- `fijados.py` `327f50e7a79ac26fc4b44813af77c6b295b893810688702a34d3f6d516a30fc7`; `tests/test_fijados.py`
  `155859b37275bcbde0ff404c37dd90283ff667add93eed5776054e68fb446f21`
- `salidas.py` `a42866d4d03243f68099c652e8d753d94c044f4984a80cb445b2859b2b36c118`; `tests/test_salidas.py`
  `2c06da0efab72bae585b5b21cfeb0aa7ac24d03a15ea76454b9a37882a4d9606`
- `tests/test_meteo_combinada.py` `f95b952c17a6447c51b5eaed6231ba55e8008129b6c0b515889d85f5d3e7f22d`
- `DISENO_IMPLEMENTACION_M1.md` `4a191c626f464aae8bfbd58aeea529cd071e82dbdd687d62dc632506af166abb`

## Ola 6: encargos (2026-10-28)

Línea base: la del cierre de la ola 5 (arriba). Texto vigente: el v2.3. Rigen D1-D56 y, mientras el autor no responda, lo
que dice cada una de las preguntas abiertas (P79-P99 y las de la ola 5).

### Reparto

| Dueño | Módulos y pruebas | Entrega |
|---|---|---|
| I21 | `costo.py`; `test_costo.py` | `medir` (§8.1 del diseño, puntos 1-6, con datos sintéticos a escala real y un mes real de ERA5L en sólo lectura), `proyectar` (T = Σ t_u·n_u/P + T_serie + el desequilibrio, con P = 8) y `recorte` («mod11» o «mod23» si M3-4 pasa de 36 h); la memoria por proceso (H1-H3 de la revisión de `orquestacion`, P-AMB-3); el contenido de `costo_m1.json` (resumen). Las pruebas, con mediciones fabricadas y una medición mínima; la medición real la corre el coordinador con la máquina libre (§8.1) |
| I22 | `verificar_meteo_combinada.py`, `addendum.py` y la fachada; `test_verificar_meteo_combinada.py`, `test_addendum.py`, y las dos de S10 de la batería en `test_meteo_combinada.py` | `--sintetico [--costo]` (la batería de §5.3 del diseño en `LOCAL/meteo_combinada/v1/m1/`), las negativas de M3-4 (§10, S2 `--aplicar`, MC-09) y de M6 (Anexo B, S16), los cerrojos (P92), la carpeta `HUMAN<AAAAMMDD>_METEO_COMB_1`, la consola sin métricas; `lista_cerrada` y `addendum_m1` (MC-54, P44); la fachada con los cinco nombres del texto ya resueltos; S10 completo |

### Acuerdos de interfaces nuevos

- **A32. La batería (I22).** `--sintetico` corre la suite entera bajo `ceguera.RegistroAccesos` en bloqueo sobre /Volumes y
  los repositorios, con `ceguera.SinRed`, y sólo deja leer las rutas de S14 y, con `--costo`, el mes real de ERA5L
  (MC-31). Escribe por `salidas` en `LOCAL/meteo_combinada/v1/m1/`: `pruebas_m1.txt` (documento, con la huella del texto
  en la primera línea, CEG-18), `resumen_m1.json`, `deriva_s6.json` (`tendencias.contenido_deriva_s6`),
  `anexo_a2.json` (`constantes.anexo_a2` del v2.3), `costo_m1.json` (`costo`) y `sha256.json`.
- **A33. El addendum (I22 → coordinador).** `addendum.addendum_m1(…)` da el contenido de `addendum_m1.json` (documento) y
  su `.md`; la batería los escribe en `LOCAL/…/m1/`; el coordinador los copia a
  `APH/auditoria/20261023/meteo_combinada/m1/` como borrador, en un paso aparte (`salidas` no escribe en APH). Los
  commits de M1 quedan «pendientes» hasta que el autor los autorice.

### Excepción de datos de la ola (regla 4 del diseño; §8.1; MC-31)

- **La medición del costo** lee, en sólo lectura, un mes real de ERA5L (2024-01, el mismo que ya abre S14) para medir la
  lectura y la decodificación, y la geometría real de `grilla_1km/celdas.parquet` (LOCAL; §8.1, punto 3). La población es
  sintética: no se abre `poblacion_celda_anio.parquet` ni GHS-POP; las 108.579 «celdas pobladas» se sortean con la semilla
  entre las celdas con `cod_comuna > 0`. Todo lo demás es sintético a escala real (579 estaciones, H horas).
- **La medición exige la máquina libre** (§8.1: carga < 2, sin TROPOMI ni otra corrida pesada). La corre el coordinador
  aparte, después de la revisión, con `uptime` y `pgrep` antes de empezar; si no está libre, queda pendiente y se dice.
- Las pruebas de la batería que corren S14 leen lo de S14 (ola 5). Nada de la DMC, del reloj (salvo su código), de SINCA,
  de NASADEM ni de GHS-POP.

Reglas de la ola: las de las olas anteriores. I22 es además dueño, en esta ola, de las dos pruebas de S10 de la batería en
`test_meteo_combinada.py` (la clase `PruebasS10`); el resto de ese archivo sigue siendo del coordinador.

## Ola 6 cerrada: el código (2026-10-28)

Los dos módulos de la ola 6 quedaron implementados, revisados por quien no los escribió y corregidos por su dueño, y el
coordinador los integró. Para que la batería pudiera aprobar y la selección cupiera en memoria hubo además seis encargos
cortos, cada uno a su dueño: I13 (`candidatos`, la caché de series), I20 (`orquestacion`, la memoria de la selección y
de las fases), I4 (`ceguera`, PED-4), I17 (`salidas`, la raíz `v1/cerrojo` y una prueba de S10), I1 (`entorno`, la
carpeta de trabajo) e I21 (la carga ajena). Nada se escribió fuera de `meteo_combinada/` y de las carpetas temporales;
`reloj_dmc/`, el código fijado y `v2/` no se tocaron; nada en LOCAL ni en APH. Ningún dato real salvo los insumos de S14
(ola 5). Sin commits. Lo que queda de la ola —la medición del costo y la batería real— va en la sección siguiente.

**Entregas de §6 del diseño:** S2 (`--aplicar` se niega en los cuatro casos), S16 (cada negativa de M6), S10 completo (la
batería en bloqueo, sin red y sin procesos vivos), la batería de §5.3, `costo` (los seis puntos de §8.1, la proyección y
el recorte), el addendum (MC-54) y la fachada.

### Qué entregó cada dueño (después de la revisión)

| Dueño | Módulo | Pruebas | Lecturas | Revisión → corrección |
|---|---|---|---|---|
| I21 | `costo.py` | 19 en verde (2 «por implementar»), ≈ 150 s | COS-1 a COS-24 | «Aprobado con reservas; no medir hasta resolver H1 a H3»: el recorte salía de cualquier proyección (incompleta, con P ≠ 8, sin memoria o con la máquina cargada), la memoria no condicionaba nada, la máquina libre sólo se miraba al empezar, un desequilibrio para dos pasadas, lo no medido contaba cero, el peor caso era parcial, a M5 le faltaban piezas, la ceguera dentro de los trabajadores y huecos de prueba. De 34 mutaciones, 24 detectadas. Corregido todo: el recorte da «pendiente» si falta algo; la memoria del grupo frente a la física; la carga ajena (COS-13); la contención medida; el barrido del peor ganador; un registro en bloqueo por punto; la carpeta de trabajo de `entorno` |
| I22 | `verificar_meteo_combinada.py`, `addendum.py`, fachada | 45 + 11 + las 2 de `PruebasS10` | VER-1 a VER-21, ADD-1 a ADD-8 | «Adoptable con cambios; todavía no sirve para sellar M1»: el cerrojo se podía borrar o recortar sin que se notara, las negativas no validaban el contenido del addendum, el testigo no ataba el código del disco al remoto, la batería aprobaba con omisiones no permitidas, la lista cerrada se tomaba al final, las corridas reales no comprobaban el intérprete, y quince menores. De 61 mutaciones, 47 detectadas. Corregido: el cotejo del cerrojo con las carpetas de corrida, el contenido del addendum, `git diff` contra `origin/main`, la lista cerrada de omisiones, las huellas del código antes y después, la negativa del intérprete, la declaración de C4 (P122) y lo demás |
| I13 | `candidatos.py` | 39 (32) | CAN-19 | La caché de series ya no guarda series: en 579 estaciones × 4 años la selección pasa de 7.278 MB a 85 MB, sin cambiar ningún bit (copia literal de la ola 4 en la prueba) |
| I20 | `orquestacion.py` | 52 (46) | ORQ-42 a ORQ-44 | El fondo de la selección sólo en los días de selección y el entero de sus estaciones de prueba; las predicciones de P1 sin retenerlas; la variante liviana armada directamente en la TF, M5, M6 y la grilla; el principal con referencias. A escala real, la selección pasa de 12,7 a 7,1 GiB (P1) y de 9,3 a 6,0 GiB (P2); el principal de M3-4, de ≈ 25 a ≈ 6-7 GiB. Mismos bits (M3-4, M5 y M6 idénticos a la ola 5; S9 con 1, 2 y 8) |
| I4 | `ceguera.py` | 36 (33) | CEG-1 cambiada, CEG-22 nueva | PED-4: crear un enlace no es un acceso a su destino; cada registro juzga por dónde lo toca la ruta, y lo negado en uno interior se cuenta como «negado dentro» en el exterior; cada registro envuelve lo que encuentra y juzga una vez. La suite entera dentro de los registros de la batería da 0 accesos |
| I17 | `salidas.py` | 23 (22) | SLD-1 cambiada | La raíz `v1/cerrojo` sólo para `intentos_*.jsonl`; la guarda de enlaces de la carpeta de la corrida misma; `_archivos` de su prueba de S10 sin seguir enlaces |
| I1 | `entorno.py` | 26 (19) | ENT-9 | `carpeta_de_trabajo(prefijo)`: crea bajo la temporal del sistema y borra al salir, sin seguir enlaces y negándose si la movieron |

### Integración del coordinador

1. **El grafo.** `DEPENDENCIAS["costo"]` suma tipos, constantes, fijados, fondo_era5l, particiones, politicas, salud y
   ceguera (PED-1 y PED-3 de I21, aprobados por el coordinador de la sesión principal); `DEPENDENCIAS["verificar_meteo_combinada"]`
   suma politicas, tendencias, salud, tipos y constantes (PED-1 de I22). Ninguno crea un ciclo. La tabla de §1 del diseño
   lo dice.
2. **`EN_CURSO` queda vacía.** Ningún archivo de pruebas tiene ya pruebas «por implementar».
3. **Comprobado:** detector de literales, grafo, escritura sólo en `salidas`, `entorno` y `sintetico`, privacidad, ningún
   `__pycache__` nuevo, nada en LOCAL ni en APH.

### Acuerdos nuevos

- **A34. La batería y el costo (I22, I21).** `--sintetico --costo` mide primero el costo, con la máquina libre, y después
  corre la suite; cada batería escribe en su propia subcarpeta `v1/m1/<AAAAMMDDTHHMMSSZ>/`; el addendum cita esa carpeta y si
  aprobó. La batería no aprueba si cambió el código o un documento del paquete mientras corría.
- **A35. El cerrojo (I22, I17).** Vive en `LOCAL/meteo_combinada/v1/cerrojo/` (P92), se coteja en cada lectura con las
  carpetas de corrida y su copia sellada llega al recibo.
- **A36. La máquina libre (I21).** Al empezar, la carga bruta de 1 min < 2; durante cada punto, la carga ajena (la bruta
  menos los procesos de la medición que corren) < 2; la contención no cuenta (P128).

### Lecturas nuevas o cambiadas (van al addendum de M1)

COS-1 a COS-24; VER-1 a VER-21; ADD-1 a ADD-8; CAN-19; ORQ-42 a ORQ-44; CEG-1 y CEG-22; SLD-1; ENT-9.

### Diferencias con el diseño (para el addendum de M1)

- **34.** `costo` y `verificar` importan más módulos que la tabla de §1 (integración 1 de arriba).
- **35.** El cerrojo vive en `v1/cerrojo/` y no en la carpeta de cada corrida (P92, A35).
- **36.** Cada batería escribe en su subcarpeta de `v1/m1/` (A34).
- **37.** `verificar` tiene negativas de M2a y de M5 que el diseño no nombraba (VER-20).
- **38.** «La máquina libre» se mide como carga ajena a la medición (A36, P128).
- **39.** `entorno` crea y borra carpetas de trabajo temporales (ENT-9).
- **40.** `ceguera` no cuenta como acceso la creación de un enlace ni lo que un registro interior ya negó (CEG-22); el
  registro del reloj sí lo hace.

### Preguntas para el autor (cierre de la ola 6)

Mientras no haya respuesta, rige lo que dice cada una.
- **P122. M1 no se selló antes del C4 de RELOJ.** Cita: §10, «M1 se sella antes del C4 de RELOJ si alcanza. Si no, rige
  el ítem prospectivo de §1.9 y, desde el inicio del C4 de RELOJ, el régimen estricto de abajo para todo cambio de M1».
  Hecho: el C4 de RELOJ corrió el 2026-10-27 (sello APH `4e16614`, 13:06); las olas 0 a 3 y las Enmiendas 1 y 2 del
  producto son de antes, y las olas 4 a 6, de después. El ítem prospectivo de §1.9 se cumplió: nadie del equipo de M1 abrió
  el informe ni las tablas de evidencia del reloj; del reloj se leyó sólo su código, sus umbrales anclados de C0 y, por
  huella, el JSON y el generador del v1.2. Rige y se propone: el código de las olas 4 a 6 implementa el texto anclado y no
  es errata ni enmienda; toda lectura de esas olas que el autor vea como cambio de regla pasa a enmienda con
  `post_hoc = true`. El addendum lo declara (`declaracion_c4_reloj`).
- **P123. El desequilibrio de la proyección (P-COS-1).** Rige: la unidad más larga entera de cada reparto (cota superior).
- **P124. El tope de memoria (P-COS-2).** Rige: 8 GB por trabajador y, además, el grupo (los P trabajadores y el
  principal) frente a la memoria física.
- **P125. Si una fase no cabe con P = 8 (P-COS-3).** Cita: §8, «≤ 8 GB en la competencia»; D2, 8 procesos. Rige: el
  recorte queda «pendiente» hasta que quepa. Alternativa: decidir con menos procesos en esa fase, que cambia D2.
- **P126. La unidad del tope (P-COS-4).** Rige (la estricta): 8 GB = 8·10⁹ B.
- **P127. Qué proyección decide el recorte (P-COS-5).** Rige: la cota superior coherente (regla de red, ganador y
  desequilibrio más caros, lo no medido acotado y la contención).
- **P128. La carga durante la medición (P-COS-6 revisada).** Cita: §8.1, «con la máquina libre (carga < 2, sin la descarga
  TROPOMI ni otra corrida pesada)». Problema: en esta máquina el fondo sin ninguna corrida ronda 1,3-1,7, y el trabajador
  de la medición suma ≈ 1, así que la carga bruta nunca baja de 2 durante la medición. Rige: la carga ajena (A36).
  Alternativa: la carga bruta en toda la medición, que no se cumpliría nunca aquí.
- **P129. La grilla medida (P-COS-7).** Rige: 16 lotes de 4.096 celdas repartidos por la grilla, por cada ganador y
  variante, valen como «un mes de la grilla» (§8.1, punto 5).
- **P130. El año de TF (P-COS-8).** Rige: seis meses de 2017 (tres redes) y seis de 2012 (dos redes) valen como «un año de
  TF» (§8.1, punto 3).
- **P131. El tope en el proceso principal (P-ORQ-11).** Rige: sí; con ORQ-44 queda en ≈ 6-7 GiB.
- **P132. `correr_v2.py` y `config_v2.json` en la lista cerrada de M1 (P-VER-1).** La enmienda de la DMC podría
  cambiarlos. Rige: M6 se niega si difieren; hace falta una errata o una enmienda que los vuelva a fijar.
- **P133. Los commits de M1 (P-VER-2).** Rige: los dos (AP y APH), cada uno antecesor de `origin/main` de su repositorio,
  y el código del disco igual al de `origin/main`.
- **P134. Una errata sin corrida confirmatoria previa (P-VER-3).** Rige: no vale.
- **P135. Los intentos de red que las pruebas de `ceguera` hacen a propósito (P-VER-4).** Rige: se cuentan, pero no
  detienen la aprobación.
- **P136. La errata de M6 (P-VER-5).** Problema: M6 toma la etiqueta de su M3-4, y una errata de M6 con `_ERRATA<n>` no
  tendría su M5. Rige: se niega (`errata_m6`). Propuesta: `<ETIQUETA>/m6_ERRATA<n>/` con su numeración (PED-5 de I22, a
  I20 e I17).
- **P137. La forma del registro de la red v2 (P-VER-6).** Rige: un JSON con `huellas`, confirmado en git y en
  `origin/main`.
- **P138. Los documentos del paquete en la lista cerrada (P-ADD-1).** Rige (la estricta): el diseño y la coordinación
  entran en la lista, además de citarse en «fuentes».
- **P139. El cotejo del cerrojo (A35).** Ratificar que una carpeta de corrida sin su «inicio» en el cerrojo, o una copia
  que no sea prefijo del cerrojo, detiene.
- **P140. Lo que copia el addendum (D5, D53).** Rige: copia el texto de las MC-n del diseño y de las preguntas, no sólo
  las cita.
- **P141. Las omisiones de la batería.** Rige: sólo tres omisiones permitidas (la de 2.500 m por D56, la de huellas de
  datos y la del cierre de M1); cualquier otra, también las «no se da por aprobada» condicionales, detiene.
- **P142. Los insumos de la fábrica v2 en M6.** `Cfg.permitidas` de M6 no incluye lo que lea la fábrica de producción v2,
  que no está escrita. Propuesta: que vayan en el archivo de entradas de M6 con su huella.

### Pendientes (para después de M1 o para el autor)

- **I22 → I20 e I17 (PED-5):** la carpeta de la errata de M6, si el autor acepta P136.
- **I12 (PED-12 de I20):** que las dos funciones de RR06 comprueben sólo las columnas que leen.
- **I15 (PED-9), I7 (PED-3 de I18), I2 (PED-2 de I18):** siguen de la ola 5.
- **`costo`:** la búsqueda de corridas pesadas ajenas con `ps` no se hizo (sólo `orquestacion` lanza procesos); la
  comprueba el coordinador antes de medir.

### Cifras al cierre del código

**Suite:** 895 pruebas: **892 en verde, 3 omitidas y ninguna falla**, en ≈ 1.082 s con un hilo. Antes de la ola: 813, 791 y
22. Las 3 omitidas son las tres permitidas por la batería (P141): la de 2.500 m (P47, D56), la de huellas de datos de
`test_fijados` y la del cierre de M1 en `test_meteo_combinada`. Ya no queda ninguna «por implementar». Sin `__pycache__`
nuevo.

**Huellas sha256** (del código que corre la batería):
- `costo.py` `f998eb62827aa5432bc11c4ce352c01e1814ffd9a0e94225c1313c7bab1ebfad`; `tests/test_costo.py`
  `c3a3a7cd3a3086d9ee044010225323c4554b5f7d77c570d474ff31c303a4464b`
- `verificar_meteo_combinada.py` `52d049acaea392de82528cdd8f0049e1ab16c3a8d776a2c3c6dd129e8e52b34d`;
  `tests/test_verificar_meteo_combinada.py` `476c10c67bf1b152efb4d4d9b032d7df883fe7ca8c3f29ad83391febf6717794`
- `addendum.py` `3a3c396724f877adf215cd92367742b44b31b517b6eb827de1e4932897835859`; `tests/test_addendum.py`
  `b92b4870cbd837580610e3b5e1942ef2e43af5320377825845fd03bca9e68c53`
- `meteo_combinada.py` `8b6d43b010fd3ad9240cce0b8b477237728e8f0dfd70e686ef52fc8d817ea872`
- `candidatos.py` `7fbc085e6f6523bbfe4aed2ddb92df6857c3b640b0e061c43559fa8b895b87b5`; `tests/test_candidatos.py`
  `4437f5b3ad7286c4f7076b324dd0b34bae702992c895f51b89a1200e36eda845`
- `orquestacion.py` `5b3acc9fa47fd32906c4292d9caeed464a824d3f80123408f8afb333a94973e5`; `tests/test_orquestacion.py`
  `1857abf349b765e4b0c77ff78436d69071271245df61460e67063588b99db223`
- `ceguera.py` `00d9e98674b859564541e4a01eea8962873a532c333eef60708bbaf157c96835`; `tests/test_ceguera.py`
  `cc55f10d0f183a9eec1c40ba5fd87ce8c8f7739ee14880e4d08eaea1c5fd8f5d`
- `salidas.py` `f20d87c59da2e989e0c2812c9cd6e3c2eee324e5633cdb2455b90ac667cd4435`; `tests/test_salidas.py`
  `4d297dbc6593bc5614884d783e37062d0c5a9458234aea796904670c65fe552e`
- `entorno.py` `1dab8f64462749be132d4794a529c6575a653277fc45387ed788fe9108ae736a`; `tests/test_entorno.py`
  `7bd071c03c3f426dc9c9d676b14e02188f3d29030d334079b4749c1e0f27f674`
- `tests/test_meteo_combinada.py` `fa99c145fe50f90611aac689e0c54bb7e23f598233e781a86f959b6b6d9f7958`
- `DISENO_IMPLEMENTACION_M1.md` `8ef8edbaca863e91eb0385ef0a302be0d96bdc97ef0776a03497546c293b8c54`

### La medición del costo y la batería real

Se corren juntas, con `verificar_meteo_combinada --sintetico --costo` (A34), con la máquina libre y sin que nadie edite el
paquete mientras corren (la batería no aprueba si cambia un archivo del paquete o de sus documentos, este incluido). El
resultado se anota en la sección que sigue a ésta, cuando terminen.

## La batería de M1 (2026-10-28)

Cuatro corridas de `verificar_meteo_combinada --sintetico`. Todas usaron el código y los documentos del paquete tal como
quedaron al cierre del código de la ola 6 (arriba), y nadie los editó mientras corrían. Reglas cumplidas:
- **Escrituras:** sólo en `LOCAL/meteo_combinada/v1/m1/<sello>/`, en `~/Asesorias_Data_local/_herramientas/` (los
  registros de lanzamiento) y en la carpeta temporal del sistema.
- **Datos reales:** sólo los insumos de S14 (ola 5) y, en la medición cortada, la geometría de `celdas.parquet`
  (permitida por §8.1, punto 3).
- **DMC y reloj:** nada de la DMC; del reloj, sólo su código y sus umbrales anclados de C0.
- Sin commits.

| Inicio (hora de Chile) | Modo | Qué pasó | Salida |
|---|---|---|---|
| 09:24 | `--costo` | Cortada en la medición por un apagado del equipo | ninguna |
| 12:08 | `--costo`, lanzada como `nohup caffeinate -i -s env … python …` | No aprobó: 28 fallas, 13 errores, costo no medido (`ErrorOrquestacion`) y un proceso vivo. La causa fue el lanzamiento, no el código (detalle abajo) | `v1/m1/20261028T150834Z/`, que queda como registro |
| 12:35 | `--costo`, con `caffeinate -i -s -w <pid>` aparte | Detenida entre las 13:57 y las 14:00 por decisión del autor («Sin costo hoy, costo de noche», la recomendada): terminaba hacia las 22 h y el equipo se apaga a las 19:20. Iba en el punto «tf» de la medición, después de «qc» y «pliegue», y no alcanzó a leer el mes real de ERA5-Land. Hicieron falta tres SIGTERM al principal (A38) | ninguna. Su carpeta de trabajo temporal (271 MB, 144 archivos sintéticos, sin enlaces) se borró con permiso de la sesión principal; la batería no la necesita, porque cada medición crea la suya |
| 14:01 | sin `--costo`, con `caffeinate -i -s -w <pid>` aparte | Terminó en ≈ 20 min: 895 pruebas, 892 en verde, 3 omitidas (las tres permitidas, P141) y ninguna falla. No aprobó por un solo motivo, `sin_costo` | `v1/m1/20261028T170115Z/` |

**Por qué falló la de las 12:08.** macOS dejó a `caffeinate` (pid 2791) como hijo del proceso de la batería (pid 2789).
`ceguera.procesos_hijos_vivos` cuenta todos los descendientes del principal, así que cada `repartir` dio «quedan 1
procesos vivos del grupo de trabajadores». Lo reproduje con una sola prueba: pasa directa y falla bajo `caffeinate` como
padre. La suite suelta, sin `caffeinate`, estaba en verde (895 pruebas). `caffeinate` terminó solo con su padre; no se
detuvo ningún proceso.

**La carga.**
- Al lanzar la de las 12:35, recién encendido el equipo y con Google Drive sincronizando: 1,38 (1 min), 2,18 (5 min) y 2,85
  (15 min).
- Durante su medición, la carga bruta rondó 2-3; la ajena, sin el trabajador de la medición, 1-2.
- Al lanzar la de las 14:01: 2,07, 2,25 y 2,28. Sin el costo no se exige la máquina libre.

### El resultado de la batería de las 14:01

- **Pruebas:** S1 a S16 en verde, cada número con al menos una prueba. La única omitida de un número es la de 2.500 m, en S4
  (P47, D56). En 1.195 s.
- **S14:** «igual» en civil, UTC−4 y regional de 2024, con una diferencia máxima de 3,41·10⁻¹³ (lo que se compara: los
  108 insumos reales, en sólo lectura).
- **Ceguera:**
  - 0 accesos;
  - 63 negados dentro: los de las pruebas que se niegan a propósito, CEG-22;
  - 0 por enlace;
  - 13 intentos de red, los que hacen a propósito las pruebas de `ceguera` (P135);
  - 0 procesos vivos al terminar.
- **Intérprete:** el fijado. `micromamba list` da 0b5bc40b…, con Python 3.11.16, pandas 2.3.3, netCDF4 1.7.4, tzdata
  2026.3 e IANA 2026c. El código fijado no tiene diferencias.
- **No aprobó** sólo por `sin_costo`: el costo queda para una noche, por la decisión del autor.
- **Salidas** (sha256):
  - `anexo_a2.json`: db60f0cfbbd248a29d4cedc1b18340e36d64339f96cc097c0d05ac044940126b
  - `deriva_s6.json`: 61a805d063b0ddbf39e8fa0ff3d19e53765a95fed3a41df03acf28aee99e3859
  - `pruebas_m1.txt`: 8bcda1dea3f29595c73930629b02de49aea4ce49f8b2b661a3571e75f3b186d7
  - `resumen_m1.json`: a281dcbb06cb111dc49dc14b5a1a97675cc7660013e1f45d0a3251faa14bfb4f
  - `sha256.json`: d850629dd7071fdf5ebda52be5bb6b3513a4d7cb860e4e001ca070b1c833f8d2
  - `addendum_m1.json`: 2ea8a8abed39ac56240b9fc879c50f3c653febdf200665bb7867a96d53ecccca
  - `addendum_m1.md`: 185eaa37357b801441f61fc308797ae6b4458bfb7d5c955450f420f8ff2012e3

### El resultado de S6 y de la compuerta de deriva

`deriva_s6.json` tiene la misma huella (61a805d0…) en las corridas de las 12:08 y de las 14:01. Corrió con la red de S6-1 a
S6-6: red constante r2000_2025 con las 20 históricas, TF2 evaluable, deriva de 0,3 K por década y cotas de T de 0,05 / 0,15 K.

| Candidato | Combinaciones que pasan | Media ponderada | P95 máximo | Peor combinación | Compuerta |
|---|---|---|---|---|---|
| B | 0 de 60 | 0,128 – 0,237 K | 0,724 K | media: L = 200, λ = 0, κ = 0,05; P95: L = 50, λ = 150, κ = 0,05 | falla |
| AB | 30 de 60 | 0,020 – 0,073 K | 0,079 K | L = 200, λ = 0, κ = 0,05, por la media | falla |

Es el mismo resultado que midió I15, y que su revisor recalculó con código propio, el 2026-10-27 (ola 4, «Ola 4 cerrada»).
Con S6-4 (las 60 combinaciones), B y AB quedan fuera de E0 en todos los usos (§5.7). Lo decide el autor en P79.

### El costo

Queda pendiente, por la decisión del autor de abajo. Ninguna corrida escribió `costo_m1.json`. Lo que se sabe son
estimaciones de los ensayos de I21 a escala intermedia (con la máquina cargada), no la medición:
- M3-4 en ≈ 25-35 h, cota superior; el recorte sería «mod11».
- La selección en ≈ 6,3-7,7 GB por trabajador tras CAN-19 y ORQ-42 a ORQ-44 (P145).

Se mide con `verificar_meteo_combinada --sintetico --costo` (≈ 9 h) una noche con el equipo encendido, lanzada según
A38. La máquina debe estar libre (A36) y nadie debe editar el paquete mientras corre.

**Decisión del autor (2026-10-28, transmitida por la sesión principal).** «Sin costo hoy, costo de noche (Recomendado)».
Falta registrarla en `APH/auditoria/20261023/meteo_combinada/m1/decisiones_autor_m1_20261026.md`. M1 sólo escribe en APH
el borrador del addendum, así que la registra quien escribe ese archivo.

### Acuerdos nuevos

- **A37. S6 queda congelado (D15; instrucción de la sesión principal del 2026-10-28).**
  - **Cuándo se vio el resultado.** Por primera vez el 2026-10-27, en la ola 4: lo midió I15 y lo recalculó su revisor.
    Quedó en «Ola 4 cerrada» y como regla de regresión `MEDICION_DERIVA_S6` = {B: 0, AB: 30} en `test_tendencias`. Se vio
    otra vez el 2026-10-28, en las baterías de las 12:08 (que no aprobó por otra causa: `caffeinate` como padre) y de las
    14:01, con la misma huella.
  - **Los parámetros.** S6-1 a S6-6 se fijaron por D15 el 2026-10-27 a las 13:46 hora de Chile, antes de que existiera el
    código de `tendencias`, y no cambiaron. `sintetico.py` sigue en f87148e7… desde la ola 2.
  - **Desde el 2026-10-28** nadie cambia `sintetico.red_s6` ni nada que alimente S6. Si una corrida da otro resultado, se
    informa sin ajustar nada. Un error real en S6 es una errata, con su prueba que falla contra el texto, no un ajuste.
- **A38. Cómo se lanzan y se detienen la batería y las corridas reales (M2a, M3-4, M5 y M6).**
  - **Lanzar:** con `nohup <comando> &` y el registro en `~/Asesorias_Data_local/_herramientas/`, y aparte `nohup caffeinate
    -i -s -w <pid> &`, como hermano.
  - **Nunca `caffeinate <comando>`:** macOS deja a `caffeinate` como hijo del proceso. `ceguera.procesos_hijos_vivos`
    cuenta todos los descendientes, así que cada `repartir` falla y el «fin» cuenta un proceso vivo. Es lo que pasó en la
    batería de las 12:08.
  - **La guarda no se cambia:** queda del lado seguro, y cambiarla exigiría otra batería (P143).
  - **Detener:** SIGTERM al principal y comprobar con `pgrep` que no quede ningún proceso. Si la señal llega mientras
    `repartir` reparte, su manejador (H18) cierra el grupo de trabajadores y lanza `ErrorOrquestacion`, y una captura amplia
    puede absorberla: en la batería la absorbió `_medir_costo`, y la suite siguió. Entonces se repite la señal cuando el
    principal no tenga hijos (P144).
  - **Mientras corre la batería,** nadie edita el paquete (A34).

### Preguntas para el autor (la batería de M1)

- **P143. Un `caffeinate` lanzado como padre cuenta como proceso vivo (A38).**
  - **Cita.** §8: «El grupo de procesos se cierra y se espera al terminar: no quedan procesos vivos»; S10.
  - **Problema.** `repartir` atribuye a su grupo de trabajadores cualquier descendiente vivo del principal, también el
    `caffeinate` que lanzó a la corrida. La corrida falla por un proceso que no es suyo: es un falso positivo, del lado
    seguro.
  - **Rige.** La guarda tal cual, con el procedimiento de A38.
  - **Propuesta, para después de M1** (exige otra batería). Que `repartir` cuente sólo los procesos de su grupo de
    trabajadores; los demás descendientes los sigue contando el «fin» de la corrida. Alternativa: dejarlo así.
- **P144. Una señal de detención que la batería absorbe (A38).**
  - **Cita.** §8: «El grupo de procesos se cierra y se espera al terminar»; H18 de la revisión de `orquestacion`.
  - **Problema.** En la batería de las 12:35 hicieron falta tres SIGTERM:
    - el primero llegó durante la medición: cerró sus trabajadores, y `verificar._medir_costo`, que atrapa toda excepción,
      siguió con la suite;
    - el segundo cayó en una prueba que reparte.
    
    Las corridas reales sí se detienen: `_correr` registra el error y termina.
  - **Rige.** Repetir la señal y comprobar con `pgrep`.
  - **Propuesta, para después de M1.** Que `_medir_costo` no atrape el error de `repartir` por una señal: que la batería
    termine y lo registre, con su prueba.
- **P145. La memoria de M3-4 con 8 procesos (D2; reúne P117, P124 a P126 y P131).**
  - **Cita.** §8: «M3-4 con 8 procesos [M0, D2], ≈ 340 MB por proceso en el control de calidad y ≤ 8 GB en la
    competencia».
  - **Problema.**
    - **Antes:** a mitad de la ola 6, el ensayo de I21 proyectó la selección en ≈ 25-30 GB por trabajador. Con 8
      procesos son ≈ 200-240 GB, frente a los 128 GB del equipo y a los 8 GB por trabajador de §8.
    - **Lo que se cambió, sin cambiar ningún bit:** I13 bajó la caché de series (CAN-19: de 7.278 MB a 85 MB en 579
      estaciones × 4 años). I20 recortó el fondo de la selección a los días de selección, dejó de retener las predicciones de
      P1, armó la variante liviana y llevó el principal por referencias (ORQ-42 a ORQ-44).
    - **Ahora, estimado a escala real:** ≈ 7,1 GiB (7,7 GB) por trabajador en P1 y 6,0 GiB en P2, y ≈ 6-7 GiB en el
      principal; el grupo suma 8 × 7,7 + 7 ≈ 69 GB.
    - **Pero:** cabe, aunque P1 queda a ≈ 4 % del tope estricto de 8·10⁹ B; todavía no está medido (lo mide `--costo`); y
      el control de calidad de la estación más larga se estimó en ≈ 1,5 GB, frente a los ≈ 340 MB del texto.
  - **Rige.**
    - Si en la medición alguna fase de M3-4 no cabe con 8 procesos, por trabajador o en el grupo frente a la memoria física,
      el recorte queda «pendiente» y M3-4 no corre (P125).
    - El tope es de 8·10⁹ B por trabajador, también en el principal (P126, P131).
    - Los ≈ 340 MB del control de calidad son una estimación del costo, no una regla: no están en el Anexo A ni en el A2.
  - **Propuesta.** Si no cabe, decidir antes de M3-4 entre dos caminos:
    - (a) correr las fases que no quepan con menos procesos: cambia D2 sólo en esas fases y alarga la pared, que se vuelve a
      proyectar;
    - (b) seguir reduciendo la memoria sin cambiar bits.

### Lo que falta para sellar M1

Según §10 del diseño y la fila «M1» de §10 del texto: «S1-S16 aprobadas y guardadas; costo medido con la máquina libre; el
JSON coincide con el Anexo A; la compuerta de deriva y el recorte fijados; addendum fechado con la lista cerrada de
huellas (texto, JSON, código, pruebas y salida de la batería) y el commit; mismo testigo».

**Hecho:**
- S1-S16, aprobadas y guardadas en `pruebas_m1.txt`;
- el JSON igual al Anexo A (§4.3 del diseño, en la suite);
- la compuerta de deriva fijada (B y AB fallan, con la decisión de P79 pendiente);
- el borrador del addendum.

**Falta:**
1. **Las respuestas del autor** (pendiente 3 de §10 del diseño): las preguntas abiertas P79 a P145. Antes de M3-4 importan
   sobre todo:
   - P79 (S6-4: B y AB fuera de E0 en todos los usos);
   - P122 (M1 se cierra después del C4 de RELOJ);
   - P145 y P124 a P126 (la memoria);
   - P87 y P88 (E0); P101, P106, P111 a P113 y P116; P118 a P121.
   
   Además, registrar la decisión «sin costo hoy».
2. **Los commits** (pendientes 1 y 5 de §10 del diseño), con la autorización del autor:
   - `meteo_combinada/` no está en git: hoy sale «??» en AP;
   - entra en un commit de AP y, con su grupo en `config/componentes_compartidos.json` (regenerado con su generador), en el
     espejo de APH;
   - envío al remoto privado (testigo externo, B14).
3. **El costo y la batería de sellado** (pendiente 4 de §10 del diseño; fila «M1» de §10 del texto):
   - **Cuándo:** después del último cambio del paquete (código y documentos, también éste).
   - **Qué:** `verificar_meteo_combinada --sintetico --costo --commits <AP> <APH>`, lanzada según A38, con la máquina libre;
     ≈ 9 h, o ≈ 5,5 h con seis meses de TF (P130).
   - **Qué tiene que dar:** aprobar, con los motivos vacíos, y fijar el recorte («mod11» o «mod23»), o dejarlo «pendiente»
     si una fase no cabe en memoria (P145).
   - **Para no medir dos veces:** conviene hacer primero los commits del punto 2 y que la noche del costo corra esta misma
     batería.
   - **Desde esta batería,** `COORDINACION_M1.md` y el diseño quedan fijos: están en la lista cerrada (P138). Lo que se
     anote después va a otro documento, como el registro de M2a.
4. **El addendum** (pendiente 6 de §10 del diseño; MC-54):
   - el de la batería de sellado, con los commits, reemplaza al borrador en `APH/auditoria/20261023/meteo_combinada/m1/`;
   - lleva su commit en APH, el envío y el sello OpenTimestamps de su línea en `APH/auditoria/sellos/anclajes_<fecha>.txt`.
5. **Cerrar la prueba del cierre.** Al sellar se quita la omisión «se exige al cerrar M1» de
   `test_meteo_combinada.test_en_curso_vacia_al_cerrar_m1`, porque `EN_CURSO` ya está vacía, y se saca de las omisiones
   permitidas de la batería (P141).
6. **El anexo de firmas** (§3 y §6 del diseño: «Al cerrar M1 se regenera un anexo de firmas por AST del código, con el
   programa del Anexo F del reloj»). No se hizo; los cambios de firma están anotados en cada ola.

### Pendientes (después de M1 o para el autor)

- **I22 (`verificar`):**
  - `_medir_costo` pasa `temporal=` a `costo.medir`, así que la carpeta de trabajo queda en disco al terminar. Que no lo pase,
    para que `costo` use `entorno.carpeta_de_trabajo`, que la borra.
  - P144.
  - PED-5 (la errata de M6).
- **I20 (`orquestacion`) e I4 (`ceguera`):** P143, si el autor la acepta.
- **Lo demás** sigue como en «Pendientes» de la ola 6.

**El borrador del addendum.** Se regeneró con las mismas funciones de la batería (`addendum.lista_cerrada`, `lecturas_m1`,
`addendum_m1` y `addendum_md`, serializadas como las escribe `salidas` y vigiladas como documento) sobre la salida de la
batería de las 14:01:
- antes de esta sección, el resultado es byte a byte el que escribió la batería;
- después de esta sección, trae A37, A38 y P143 a P145, y la huella nueva de este documento;
- se escribió como archivos nuevos en `APH/auditoria/20261023/meteo_combinada/m1/`.

Sus huellas van en el informe del coordinador y no aquí, porque el borrador cita la huella de este documento.

## Al cierre de las olas 4 a 6: D57 a D61 y los arreglos de cierre (2026-10-28)

El autor respondió por la sesión principal, que lo registró en
`APH/auditoria/20261023/meteo_combinada/m1/decisiones_autor_m1_20261026.md`, sección «Al cierre de las olas 4 a 6»: primero
D57 a D61 (el archivo quedó en 3de7f527…) y después D62 y D63 (a721e16b…).

El encabezado de esa sección habla de la sesión del autor: allí no se miró ningún resultado del C4 del reloj DMC, sólo la
política publicada, por huella. Para M1 vale `addendum.DECLARACION_C4`: la política publicada no se abrió en M1, porque las
pruebas usan políticas sintéticas y, en la batería, VER-1 vigila esa carpeta (0 accesos). I22 preguntó si alguien de M1 la
abrió para tomar su huella: el coordinador no la abrió ni encargó abrirla.

### Respuestas del autor (D57 a D61)

| Decisión | Responde a | Qué queda en M1 |
|---|---|---|
| D57 | La batería con costo, que no alcanzaba antes del apagado de las 19:20 | «Sin costo hoy, costo de noche». La batería de las 14:01, sin costo, queda como registro (`LOCAL/meteo_combinada/v1/m1/20261028T170115Z/`). La batería completa con costo (≈ 9 h), que es también la de sellado, se lanza una noche con el Mac encendido, cuando el autor lo indique, según A38 |
| D58 | P79, que queda cerrada | B y AB quedan fuera de E0 en todos los usos (§5.7): compiten A y C, y C_est en lo crónico. Sus tablas de TF se calculan igual, pero no deciden nada. El código ya lo hace con `Cfg.deriva` (H13), que sale del veredicto de la deriva del addendum: no cambia nada |
| D59 | P145, que queda cerrada | La fase que no quepa en memoria con 8 procesos corre con el mayor número que quepa. Sólo cambia la duración, que se vuelve a proyectar (S9). Se declara en el addendum y en el registro de M3-4, y modifica D2 sólo en esa fase. La interfaz está en A39 y la extensión a M5, en P146 |
| D60 | P80 a P144, incluida P122 | Entran al addendum de M1 tal como están en este documento. Si un revisor ve que alguna cambia una regla, se le pregunta aparte al autor |
| D61 | Los commits de `meteo_combinada/` | Con el paquete final: commit local en AP, sin enviarlo; espejo en APH y envío de APH sin forzar, con revisión previa de privacidad en AP. Después, la batería de sellado con `--commits` |

Con esto, las preguntas abiertas P79 a P145 quedan respondidas: `addendum.respondidas` las lee de la columna «Pregunta»
de esa tabla (ADD-4).

### Acuerdos nuevos (cierre)

- **A39. Los procesos por fase (D59; I20, I21 e I22).**
  - **Las fases.** `orquestacion.FASES_REPARTO` = {«m34»: («artefactos», «seleccion_y_prediccion»,
    «tendencias_y_finitud»), «m5»: («representatividad», «anual»)}, las fases que reparten con `procesos`. M6 sigue con
    `Cfg.procesos`, porque D59 no lo nombra.
  - **`costo`.** De la memoria de cada fase sale el mayor número de procesos que cabe, de 1 a 8: por trabajador, frente al
    tope de 8·10⁹ B, y en el grupo con el principal, frente a la memoria física. La proyección usa ese número en cada fase,
    y `costo_m1.json` lo lleva en «procesos_por_fase». Si alguna fase no cabe ni con 1 proceso, o no se midió, el veredicto
    no decide: el recorte queda «pendiente» y M3-4 no corre.
  - **`addendum`.** El costo del addendum lleva «procesos_por_fase» junto a su recorte, y el .md lo muestra con la
    declaración de D59.
  - **`verificar`.** `_armar` pasa al `Cfg` los procesos por fase del addendum, y `_fallas_contenido` se niega si faltan o
    no tienen su forma.
  - **`orquestacion`.** `Cfg.procesos_por_fase` es None (todas las fases con `procesos`, como en el modo sintético) o
    {compuerta: {fase: n}}, con exactamente las fases de `FASES_REPARTO` y 1 ≤ n ≤ 8. Es obligatorio en los modos reales,
    como el recorte y la deriva. Cada `repartir` de esas fases usa mín(procesos, n). El registro de M3-4 lleva los
    procesos por fase del addendum, que no cambian entre 1, 2 y 8 procesos, y el recibo lleva los que se usaron.
  - **Sin cambiar ningún bit.** Con `procesos_por_fase` = None todo sigue como antes, y S9 sigue igual con 1, 2 y 8.

### Diferencias con el diseño (cierre)

- **41.** `config/componentes_compartidos.json` no se regenera en M1, por instrucción de la sesión principal del
  2026-10-28. Es una diferencia con el pendiente 5 de §10 del diseño: «`meteo_combinada/` entra en un grupo de
  `config/componentes_compartidos.json`, regenerado con su generador». El espejo de APH se hace por D61 con los mismos
  archivos de `scripts_modelo_1km/meteo_combinada/` que entran al commit de AP, y el grupo queda para después de M1.
- **42.** El diseño lanza «8 [procesos] en M3-4 y M5, por D2» (§0) y proyecta con P = 8 (§8). Con D59, la fase que no
  quepa en memoria corre con menos (A39), y la pared se proyecta con ese número.

### Preguntas para el autor (cierre de las olas 4 a 6)

- **P146. D59 también en M5 (A39).**
  - **Cita.** D59: «Esa fase corre con el mayor número de procesos que quepa […] modifica D2 sólo en esa fase», en
    respuesta a P145, que trata de M3-4. §8 del texto: «M3-4 con 8 procesos [M0, D2]»; §0 del diseño: «8 en M3-4 y M5,
    por D2».
  - **Problema.** D59 nombra M3-4. M5 también reparte con 8 procesos, y cada trabajador de su fase anual lleva el operador
    de la grilla (COS-11). El encargo de la sesión principal extiende D59 a M5, en las fases «representatividad» y «anual».
  - **Rige.** La del encargo: también en M5, cada fase corre con el mayor número de procesos que quepa, y si alguna no cabe
    ni con 1, el recorte queda «pendiente». Sin la extensión, M5 con 8 procesos podría pasar de la memoria física. S9 vale
    igual en M5: no cambia ningún bit.
  - **Propuesta.** Ratificar la extensión.

### Respuestas del autor (D62 y D63)

| Decisión | Responde a | Qué queda en M1 |
|---|---|---|
| D62 | Cuándo se envía AP, que es público, a su remoto | Después de la batería de sellado: se fusiona `origin/main` sin rebase y se envía AP sin forzar, con una revisión previa de privacidad. Antes de eso, M2a y M3-4 no pueden correr, porque sus negativas (VER-7) exigen los commits de M1 en `origin/main` de AP y de APH |
| D63 | P146, que queda cerrada | D59 vale también para M5: si una fase de M5 no cabe con 8 procesos, corre con el mayor número que quepa. Es lo que ya hace A39 |

Con D63 no queda ninguna pregunta abierta de este documento.

### Preguntas para el autor (la revisión de D59)

- **P147. D59 y el recorte (A39).**
  - **Cita.** D59: «S9 mostró resultados idénticos bit a bit con 1, 2 y 8 procesos, así que sólo cambia la duración, que
    se vuelve a proyectar». §8 del texto: «Recorte por costo: sólo el de §4.9 (mód 23), fijado en el addendum de M1 desde
    la proyección».
  - **Problema.** La duración que se vuelve a proyectar es la que decide el recorte. Si una fase de M3-4 corre con menos de
    8 procesos, la pared puede pasar de 36 h, y el recorte, de «mod11» a «mod23». El recorte sí cambia los días de
    selección y, con ellos, los resultados de M3-4. D59 no habla de ese efecto, y la estimación de hoy con 8 procesos
    (≈ 25-35 h, cota superior) está cerca del umbral. Lo encontró la revisión de D59.
  - **Rige.** La pared reproyectada con n decide el recorte, porque es la duración que de verdad tendrá M3-4 (§8: «desde la
    proyección»; D59: «se vuelve a proyectar»). `costo_m1.json` lleva además la pared con 8 procesos en todas las fases, y
    el veredicto avisa si con ella el recorte sería otro.
  - **Propuesta.** Ratificar. La alternativa es decidir el recorte con 8 procesos aunque una fase corra con menos.
  - **Respuesta del autor, D64 (2026-10-28).** «Con la duración real (Recomendado)». P147 queda cerrada: el recorte se
    decide con la pared reproyectada con los procesos de cada fase; `costo_m1.json` conserva también la proyección con
    8 procesos y el veredicto avisa si con ella habría otro recorte. Esto corrige la descripción inicial de D59: reducir
    procesos no cambia los resultados para un recorte dado, pero la duración puede cambiar el recorte y los días de
    selección. No se modificaron S6 ni sus parámetros.

### Respuesta del autor (D64)

| Decisión | Responde a | Qué queda en M1 |
|---|---|---|
| D64 | P147, que queda cerrada | El recorte se decide con la duración reproyectada con los procesos de cada fase. Se conserva la proyección con 8 procesos y se informa si habría dado otro recorte. La respuesta consta en `APH/auditoria/20261023/meteo_combinada/m1/decisiones_autor_m1_20261026.md` |

Con D64 no queda ninguna pregunta abierta de este documento. El costo y el recorte definitivo siguen pendientes de la
batería de sellado autorizada para una noche con el equipo encendido (D57).

## Refijación D51 tras el cambio operativo de espacio SINCA (2026-10-28)

El autor autorizó reemplazar el mínimo rígido de 100 GiB del preparador por un presupuesto dinámico con margen, sin
borrar fuentes; consta en `APH/auditoria/20261028/sinca_espacio/DECISION_ESPACIO.md` (99e2970f…). El original sellado no
cambió. La variante y sus guardas quedaron confirmadas en AP `8542e61`, con revisión independiente y pruebas sintéticas.

El cambio de referencias del derivado modifica `v2/config_v2.json`: la vigente pasa de 51df5063… (AP `6c15981`) a
1bcb3ff4… (AP `8542e61`). Por D51 se refija aquí antes de la batería de sellado, en `fijados.SHA_CONFIG_V2`, el commit
correspondiente de `HUELLAS_D51`, `test_particiones` y §9.3 del diseño. `huellas_m0.json` y las huellas históricas de M0
no se tocan; tampoco cambia `correr_v2.py`, la partición BLQ-75 ni ningún parámetro o dato de S6.

Validación de esta refijación: las pruebas de `test_fijados`, `test_particiones`, el anexo de firmas y la privacidad del
paquete. La suite completa de 917 pruebas registrada para AP `b979586` sigue siendo la del cierre previo; no se afirma
que se haya repetido después de esta actualización. La batería nocturna de sellado deberá usar el commit posterior a
esta refijación y comprobar todas sus huellas; el costo y el addendum final siguen pendientes.

## Enmienda 3 operativa: formalización de D59/D63/D64 por D65 (2026-10-28)

El autor adoptó la formalización por §10, con `post_hoc = true`, y autorizó los pasos posteriores mediante D66-D67.
La fuente nueva es `APH/auditoria/20261023/meteo_combinada/enmienda3/decisiones_autor_20261028.md`; no se agregan
respuestas a fuentes anteriores. P79, P145 y P147 siguen cerradas. Esta tarea no ejecuta costo, batería, commit ni envío.

### Alcance normativo y lo visto

- EMC3-1: hasta ocho procesos por fase de M3-4/M5, el mayor número compatible con los topes del trabajador/principal y
  con la memoria física del grupo. Si no cabe ni un trabajador, sigue bloqueado; reducir procesos no elimina el tope.
- EMC3-2: el recorte se fija antes de M3-4 con la duración proyectada efectiva; se conserva la proyección con ocho y
  se informa si daría otro recorte. No se afirma que reducir procesos sólo cambia duración: puede cambiar el recorte,
  los días de selección y los resultados. S9 asegura igualdad para un recorte dado.
- No cambian PROCESOS = 8, MEMORIA_MAX_GB = 8, el umbral de 36 h ni mód 11/mód 23. Anexos A/B, Referencias, §4.9 y §10
  se conservan byte a byte. Tampoco se toca S6 ni la configuración de v2 (1bcb3ff4…).
- Después del inicio del C4 de RELOJ: sí es enmienda operativa post_hoc del producto. Se vieron código, pruebas sintéticas,
  ensayos preliminares de costo y S6 (ya congelada y ratificada en D58). No se vieron informes/evidencia del reloj ni
  competencia meteorológica real para elegir estas reglas. No se abre ninguna salida de S6 ni del costo en esta tarea.

### Código, documentos y esquema

- En APH, sólo `enmienda3/`: `ENMIENDA_3.md`, `generar_v2_4.py` y v2.4 (eaedb109…). No se modifica el archivo de
  decisiones. Generador: sha256 de origen/borrador/decisiones, reemplazos únicos, igualdad de bloques del diff y
  resultado completo, marcas conservadas y SystemExit también con -O; nunca sobrescribe.
- M1 usa v2.4 en `umbrales`, `ceguera`, `fijados` y las pruebas pertinentes. El v2.3 se conserva como historia y en la
  lista cerrada. Se cambian citas/repeticiones de `constantes`, no valores. Verificación/completitud/repeticiones: cero
  problemas. Se preserva la configuración v2 vigente y la clausura del reloj.
- `addendum.DECISIONES` suma la fuente de D65-D67: 67 decisiones sin huecos, ninguna pregunta abierta. Se añaden
  enmienda/generador/textos a su lista cerrada, sin cambiar fuentes ancladas.
- La declaración C4 deja de negar genéricamente que las olas posteriores sean enmienda: exceptúa explícitamente
  D59/D63/D64 formalizadas por D65. `enmienda_operativa` declara `post_hoc: true`, la fuente, el texto y la regla
  anclados, los enmendados, lo visto y las prohibiciones conservadas. Esquema /2, sin cambios de firmas públicas;
  el Anexo F sigue concordando con el código.
- `verificar` rechaza metadatos ausentes, post_hoc falso o numérico, lo visto alterado y declaración C4 incompatible.
  Las negativas de C5 para política post_hoc y errata posterior al C4 sin confirmar siguen pasando sus pruebas.

### Validación y cierre

Sólo pruebas dirigidas; el coordinador correrá la suite completa y la batería nocturna con costo después de confirmar
código, anclaje y huellas. No se regenera `componentes_compartidos.json`. No se hacen commits ni envíos aquí, ni se
escribe fuera de `meteo_combinada/` de AP y `enmienda3/` de APH (temporales propios de las pruebas, eliminados).

### Pendiente técnico previo a la nocturna (no reabre preguntas)

D65 exige el tope también en el principal. Se halló una discrepancia preexistente en la implementación del costo:
`_procesos_que_caben` rechaza al trabajador que supera el tope y compara el grupo con la memoria física, pero no
rechaza por sí mismo un principal sobre el tope. `_veredicto` sólo comprueba aparte `principal_m34_cabe`, no M5.
Una llamada sintética con trabajador = tope/8, principal = tope + 1 y memoria física = 4·tope devuelve ocho procesos.
No se midió memoria real. No se toca `costo.py` ni se decide una regla nueva: corresponde reconciliar la guarda con D65
antes de dar por lista la batería nocturna. La formalización no asegura que ese caso esté ya protegido.

### Pruebas dirigidas de esta formalización

226 pruebas: 225 en verde, una omitida (huellas de datos reales) y ninguna falla. Se cubren addendum, generador con y sin
-O, constantes/umbrales, ceguera, entorno, fijados, particiones, tipos, salidas, privacidad y anexo de firmas; además, las
negativas del contenido del addendum y las de C5 post_hoc/errata sin confirmar. No se corre suite completa ni batería,
ni S6 ni mediciones. El colector da D1-D67 y cero preguntas abiertas. No aparece bytecode nuevo en el paquete.

**Huellas de la entrega inicial de formalización** (anteriores a la corrección del principal de M5; las posteriores se
registran debajo. La de coordinación se informa aparte para evitar autorreferencia):
- `DISENO_IMPLEMENTACION_M1.md` `942db15c05d939b06aab6f91957cd403369e5d888f6a24a54aeaf10184fc6185`
- `__init__.py` `3418219a487520b716ca6744350a516bb268c95834d28af3f24e6971f73d6509`
- `addendum.py` `55f46adcd9c7dbeab839de12ecf4b2b2fa2601443e7c29f124b98cb50232625e`
- `ceguera.py` `a8fe8a2329cbba03a39c89e9ccd0d31a4b8a56c16b12ee071931460d8ef6829f`
- `constantes.py` `8f9a2889063b808cf2418a258154f438f53c01ede5236983b3651b6951c47e36`
- `fijados.py` `c8e36cdb2e2adb9e5d4ab6689d3925cf92ab3a8fb20fc23ba4d880948bab60ae`
- `homogeneidad.py` `f910b76e624c6472587b1c1f90842d4bd78ce3ae7e7045b30a3efcafe9d5155a`
- `politicas.py` `0e73444d6e4447a0d19427cc83f3242dffbdfb883b907b7d53fc9be46f3c5414`
- `tests/test_addendum.py` `10f45b7f3aab94d21b60d476459ec4cf28886cfb2596bb1832aa8cbec9e7365b`
- `tests/test_ceguera.py` `5ba039bbbe5d41bc512185aba2883495a8754654d5a69d6f23e084170a43b745`
- `tests/test_constantes.py` `aaf70eef9e76dfd85549f78bd1c3f60ff8e7e00b45aeedefd88ccc750d0d6216`
- `tests/test_entorno.py` `175fac62ff3c0dbb30df2161265f879bdf69b8039617dcf58fd43580b23e8b93`
- `tests/test_meteo_combinada.py` `2667e4fe95e9efe688aee3a85c7d11984a486ebd06911d6d426420d1d61b8202`
- `tests/test_particiones.py` `1e716a2cebea93445ea33c468c52f38a7d5d81d3bf037d7dab36f5e4225d9eb5`
- `tests/test_politicas.py` `d88166a64289bab75ec080a41743a71878dfda0a0ea27b4ec80adde76e99c0c6`
- `tests/test_salidas.py` `71eb2751c87abe98c7560ca8d8493ec31398bd7b2b5af27ef4d21b2ed80ac3f2`
- `tests/test_tipos.py` `fece006ee18d32bd6a9aa72547028c41168b5d116c08b784459f99585a34ba6d`
- `tests/test_umbrales.py` `6fa54b8781f17dee777f2a03b16817d5e1e13d2ccc134b1f8df4075ed9f486ef`
- `tests/test_verificar_meteo_combinada.py` `c50e1ae3341a3d4347e67b4af07499d89eb446a74789b8aaa370e99a6602fc79`
- `umbrales.py` `9131ae0d00002ccaae08e59fc13257d22c589ce5d3f3d9072152af6148e13a7e`
- `verificar_meteo_combinada.py` `d655930f5d89336f640f3726e5f987cdf2e7de9e6d868900bcf440490aa8ef00`
- `APH/auditoria/20261023/meteo_combinada/enmienda3/ENMIENDA_3.md` `b25a418f1f07b49176997eafedde320fe86fc61fc0e5cee61808c2d08c40a0ec`
- `APH/auditoria/20261023/meteo_combinada/enmienda3/generar_v2_4.py` `043090e95a9ad98a910d8937eacc0aec2d057c7d3cb64518d4459d6377d5d526`
- `APH/auditoria/20261023/meteo_combinada/enmienda3/PROTOCOLO_METEO_COMBINADA_v2.4.md` `eaedb10998e1a3f37f83f036c478afb5cf3fd3ccb5262477bd394dc220b1908b`

### Corrección del tope del principal de M5 antes de la nocturna

Al aplicar D65 se detectó que `_procesos_que_caben` rechazaba al trabajador sobre el tope, pero no al principal. El
veredicto bloqueaba aparte un principal M3-4 excesivo; M5 podía admitirse si el grupo cabía en la memoria física.
No se usó ningún pico real para modificar la guarda.

Se agregaron primero dos pruebas: una del ayudante en el límite y un byte por encima, y otra con principal M5 sobre el
tope pero trabajadores y grupo admisibles. Ambas fallaron con el código anterior, que devolvía ocho procesos. La
condición pasa a rechazar si trabajador o principal superan el tope. Se conserva la igualdad exacta y la comparación de
la suma del grupo con la memoria física. Las 31 pruebas de `test_costo` pasan con la corrección (146,100 s).

Hubo una advertencia de compatibilidad binaria de NumPy en esa ejecución, sin fallas. No se alteró el entorno fijado ni
se ocultó la advertencia. No cambiaron fórmulas de tiempo, escalas, factores, mediciones, muestras, S6 ni sus parámetros.
Es una reconciliación de implementación con D65, no una nueva decisión científica. La suite completa y la batería de
sellado deberán correr sobre el paquete posterior a esta corrección.

Huellas posteriores a esa corrección:
- `costo.py` `c18c27a857a63f564dc8bb6eb4d30d426b954fa29ecf143a3a2b6674826d45c4`
- `tests/test_costo.py` `6fe99d1d87b60c0e23d5724cf10690f8dfcd429d3a772c79593e43b72d7607c3`
- `APH/auditoria/20261023/meteo_combinada/enmienda3/ENMIENDA_3.md` `f9f78267751ba76ba51832a02b1e781ebad7485be5fee46e2b7551d6f92fe9fa`

El texto consolidado v2.4 y las decisiones D65-D67 conservan sus huellas. La actualización posterior de este registro o
cualquier archivo de la lista cerrada exige que la batería de sellado use esa versión final, no una anterior.

## Correcciones acotadas de la revisión EMC3: lectura y publicación (2026-10-29)

Se atendieron sólo los hallazgos 1, 2, 4 y 5. No se modifican orquestacion ni sus pruebas, costo ni sus pruebas ni S6.
Se conserva la corrección del principal M5 realizada por el coordinador y su documentación; no se cambia v2.4 ni D65-D67.

- **1, bloqueante.** La comprobación privada común de `addendum` exige las dos declaraciones exactas, el esquema
  vigente y `post_hoc is True`, no igualdad numérica. La llaman el lector `leer_addendum`, el formateador `addendum_md`
  y el escritor `salidas.escribir`, cada uno antes de aceptar o escribir. `_fallas_contenido` reutiliza esa comprobación.
  Se rechazan False, 1, 1.0, 'true', None, [], ausencia de la enmienda, lo visto falso y declaración C4 incompatible.
  La publicación comprueba JSON (también bytes) y el bloque Markdown canónico, incluyendo gzip. JSON repetido no es
  válido; el orden de claves se normaliza para las declaraciones Markdown. Las guardas generales se conservan.
- **Dependencia técnica [delegada].** salidas → addendum, sin dependencia inversa. Addendum es puro y depende sólo
  de capas 0/1: pasa a capa 2; salidas pasa a capa 3. Se actualizan §1 y la prueba del grafo. No se cambia ningún
  algoritmo científico ni firma pública. Se regeneró sólo el Anexo F por AST para reflejar la firma concurrente de
  `repartir` con `registro`, que arregla otro agente; no se editó su código ni sus pruebas.
- **2.** La lista obligatoria suma
  `APH/auditoria/20261023/meteo_combinada/enmienda3_borrador/BORRADOR_ENMIENDA_3_PROCESOS.md`, con su sha256
  3f38021d5a110ae450b79aa6c9aa16652be35f7025ce735c7a8a1cebb3bfed90 comprobada por prueba. No se altera el borrador.
- **4.** `PruebasEnmienda3` verifica disponibilidad de texto y fuentes antes de leer; sin APH/fuentes, SkipTest y no
  FileNotFoundError. Una prueba comprueba ese rechazo sin darse por omitida. No se agrega ninguna omisión permitida
  a la batería: sin las fuentes no se puede aprobar M1.
- **5.** `unittest.main` va al final. Descubrimiento y ejecución directa de `test_addendum.py` ejecutan las mismas
  15 pruebas e incluyen `PruebasEnmienda3` y su generador.

**Pruebas dirigidas finales:** 56 en verde, ninguna omitida y ninguna falla: addendum, salidas, grafo, firmas, privacidad,
negativas del contenido y negativas de C5 post_hoc/errata. Aparte se comprobaron las dos entradas del archivo del addendum
(descubrimiento y directo), ambas con 15 pruebas en verde. No se ejecutó suite completa, batería, costo ni S6.
El v2.4, la enmienda documental actualizada por el coordinador, las decisiones y la configuración de v2 no se tocaron.
Se conservan 67 decisiones y cero preguntas abiertas.

## Recibos efectivos: cierre del hallazgo 3 de EMC3 (2026-10-29)

El implementador corrigió sólo `orquestacion.py` y `tests/test_orquestacion.py`. `repartir` recibe un `registro` opcional,
sin alterar su lista de resultados. La observación nace en la creación y asignación de trabajo, no en Cfg. Se propaga
por las fases M3-4/M5 y por el sello tras una alarma. Un reparto vacío registra 0 procesos de ejecución/0 trabajadores;
la ejecución en el principal, 1/0. Se separa el presupuesto, el detalle de llamadas, el máximo de procesos por fase y la
suma de trabajadores creados. `alcance` es `repartos_de_esta_invocacion`: la reanudación cuenta lo pendiente de ese
intento y las fases omitidas tienen 0 y detalle vacío. No se inventa un acumulado de intentos anteriores.

El recibo rechaza límites por fase sin observaciones. Se usaron las claves enteras `procesos` y `unidades` ya admitidas;
no se amplió ceguera. El registro normativo conserva el presupuesto del addendum, y las huellas analíticas no usan el
entorno observado del recibo. La convención principal/trabajadores se documenta como precisión técnica [delegada].

Prueba roja previa: el recibo aceptaba sólo límites y no lanzaba `ErrorOrquestacion`. Tras el arreglo, el implementador
corrió 18 pruebas dirigidas aprobadas. El revisor independiente repitió 12 y seis reproducciones, con serialización,
escritura/lectura, ceguera, vacío, 1/2/11 unidades, distintos límites y reanudación; todas pasaron. Los cierres 1/2/4/5
mantienen su aprobación; los cinco hallazgos de código quedan cerrados, condicionados a la suite final y al costo.

Huellas de los dos archivos: `orquestacion.py` 253eb120b49293da4d14fc1105382074ae5a31087888d271245c8b5ee1f67c78 y
`tests/test_orquestacion.py` 950764fca444a386fa878864fda0bdf5c9958dd89b879200ba7600903ce6a949.

Concordancia de firmas: la entrega inicial de `ENMIENDA_3.md` (f9f78267…) se conserva anclada en APH `ae670dd`, sello
`b07791e`, enviados. Su frase sobre firmas describía la formalización inicial, no el arreglo final de recibos.
`APH/auditoria/20261023/meteo_combinada/enmienda3/NOTA_FIRMAS_RECIBOS.md` (3fadd224…) precisa el ajuste técnico y se
incluye como insumo obligatorio del addendum. El Anexo F se comprueba sobre las firmas finales. No se cambia el texto
v2.4 ni D65-D67, S6 o sus parámetros por esta concordancia.

## Corrección de procedencia del costo tras rechazo de escritura (2026-10-30)

El intento completo iniciado el 29 a las 18:33 terminó con salida 1 el 30 a las 02:29 al escribir `costo_m1.json`:
el nombre del mes en `lecturas_reales` activa correctamente la guarda léxica de un resumen. Las 930 pruebas de ese
intento terminaron (928 aprobadas y dos omisiones), pero no quedaron costo, resumen final ni addendum acreditados.
El cierre y diagnóstico están en `APH/auditoria/20261029/meteo_combinada/`; se conservan la versión fallida, sus
registros y los originales previos al cambio. El autor pidió avanzar con corrección/pruebas/revisión, no otra batería
larga ni un envío remoto.

Corrección del productor, sin tocar `ceguera.py`, `salidas.py`, umbrales, recorte o algoritmos: el punto del mes devuelve
el digest de los mismos bytes ya calculados para su lectura y el tamaño medido, en `huellas_lecturas_reales`.
La ruta completa se conserva por alias bajo la estructura cerrada de huellas ya permitida por CEG-15. **[delegada]**
En la lista de lecturas se usa el identificador técnico `mes_real`, enlazado a esa única huella y sólo cuando el punto
es el del mes y existe su apertura registrada. Se exige coincidencia de rutas completas permitidas, huella válida,
tamaño concordante y ausencia de accesos inesperados. `celdas.parquet` conserva su nombre; no se filtran lecturas
ni se hace pasar por libre una carga alta.

Regresión roja inicial reproducida con un mes inventado. Diez pruebas nuevas cubren escritura completa, procedencia
sin evento, rutas distintas con igual nombre, aperturas inesperadas, punto equivocado, tamaños/digest inválidos y
vocabulario prohibido fuera de huellas. Se amplía además el ensayo existente con seis puntos y trabajadores sobre
insumos inventados hasta la serialización, guarda y escritura real del informe. La proyección pendiente de un ensayo
reducido no se transforma en aprobación a escala real.

Pruebas dirigidas terminadas: **174 aprobadas, cero fallas, errores u omisiones, 357,830 s**. Cinco módulos:
`test_costo`, `test_ceguera`, `test_salidas`, `test_meteo_combinada` y `test_verificar_meteo_combinada`.
Incluyen el camino de seis puntos con trabajadores e insumos inventados hasta guarda/escritura. Huellas de los
archivos Python estables antes/después. No es la suite completa ni costo a escala real.

Revisión independiente acotada terminada: sin defectos concretos atribuibles al diff de `costo.py` y sus pruebas;
repetición directa de las diez regresiones, 10/10 aprobadas en 0,127 s. No ejecutó los ensayos de medición/camino real
ni el costo real; no acredita insumos reales o resistencia a sustituciones concurrentes. La revisión informó una
ejecución automática adicional fuera del alcance solicitado, cuyo resultado se descartó y no sustenta este cierre.

Cambio local sin nuevo commit, anclaje ni sello. El espejo de los tres archivos se coteja por bytes y se registra
por separado; no se actualiza el manifiesto compartido ni la lista histórica de 179 huellas del intento fallido.
No se añade persistencia/reutilización de mediciones. El futuro addendum debe registrar este cambio de representación
conforme §0 del diseño; esta nota no sustituye el addendum de una batería aprobada ni la suite completa pendiente.

## EMC4: carga informativa por decisión D68 (2026-10-31)

El autor indicó «no quiero que se rechaze por carga» y, en mensaje separado, «y lanzalo». La primera orden cambia
la regla operativa del costo y se formaliza como Enmienda 4 del producto, texto v2.5, `post_hoc = true` conforme §10.
La segunda autoriza una sola batería nueva después de integrar, verificar y confirmar el cambio, no un reintento
automático ilimitado. Los intentos anteriores y sus fuentes confirmadas se conservan.

Cambio explícito: la carga al inicio y durante la medición no excluye el costo, la proyección ni el recorte.
Se conservan lecturas brutas/ajenas, máximos, no finitas e indicador diagnóstico histórico de máquina libre;
no se sustituyen por ceros ni por `libre: true`. El valor histórico de referencia permanece sin aumentar el tope
ni usar infinito para eludirlo. No se identifica la medición bajo actividad concurrente con una de máquina libre.
Los tiempos y la proyección pueden variar; por D64 una proyección distinta puede cambiar el recorte antes de M3-4.
No se garantiza una cota superior ni se elige por métricas meteorológicas.

No cambian límites de memoria, número de procesos, factores/muestras de proyección, semillas, algoritmos, S6 y
sus parámetros, pruebas de ceguera, procedencia de archivos, integridad, reloj DMC, modelos de contaminantes,
descargas ni condiciones de publicación. El addendum conserva EMC3 y agrega una declaración separada de EMC4/D68,
con las versiones anclada y enmendada y lo ya visto. La regla de memoria que no cabe sigue bloqueando la ejecución.

Lo observado antes de esta decisión: la batería del 29 terminó por rechazo de escritura de procedencia, corregido
sin retirar la guarda; después la suite de 940 pruebas pasó (938 aprobadas y dos omisiones). Dos intentos posteriores
completaron la suite pero quedaron sin costo, con `ErrorCosto` sin mensaje persistido y cargas altas en el control.
Eso es compatible con el veto anterior, no prueba concluyente de su mensaje interno. No se abrieron informes ni
tablas de evidencia del reloj ni resultados de la competencia meteorológica real para elegir esta regla.

Estado al registrar esta nota: integración y pruebas en curso; no hay todavía batería bajo EMC4 ejecutada ni costo,
recorte o aprobación inventados. La formalización y el código deben recibir sus identidades nuevas antes de lanzar.

## EMC5: memoria física en vez de tope individual fijo (2026-10-31)

El autor indicó «borra limites neceisot que se ejcute todo para empesara ver los modelos». D69 retira el tope
individual fijo por trabajador y principal; no eleva su valor ni lo reemplaza por infinito. La memoria física
positiva y finita sigue determinando el mayor número de procesos por fase cuyo grupo cabe. No se eliminan
integridad, ceguera, procedencia, criterios científicos ni el testigo externo; máximo de procesos y recorte intactos.
Se conoce el costo medido anterior y su bloqueo operativo por memoria, no resultados meteorológicos reales.
La batería histórica no se aprueba retroactivamente.

**[delegada, para ratificar]** Evitar repetir la medición costosa si su informe conserva información reproducible:
reconstrucción y reproducción histórica exacta antes de usarla, nueva proyección, nueva suite completa y procedencia
explícita. No se inventan mediciones ni se sustituye la suite nueva por la antigua. Si falla esa reproducción, no
se reutiliza. Esta decisión técnica no se atribuye a palabras del autor. La ejecución avanza sólo por las etapas
habilitadas, sin envíos o descargas nuevas. Estado de esta nota: integración en curso, ninguna nueva batería aprobada.
