"""Uso ambiental (§7.1 y Anexo B): tablas laterales I y D, operador de la grilla, columnas por lote y la fábrica de la TF
de contaminantes.

Las tres funciones de §7.1 conservan los argumentos posicionales del texto: ``(pol, decision, operador)``,
``(decision)`` y ``(celdas, horas, variante)``. Lo demás va por palabra clave.

El módulo es puro (§0, regla 8 del diseño): recibe tablas, meses ERA5-Land ya leídos (``fondo_era5l.MesE5L``),
``tipos.DatosCompetencia`` y los umbrales (un objeto con ``.a``), y devuelve tablas, diccionarios, bytes o el operador en
memoria. No lee ni escribe archivos: las laterales y el operador los escribe ``salidas`` (clase «insumo», carpeta
``ambiental/`` o ``m6/ambiental/``; D3 y P98). R, la corrección del ganador, vive en memoria; sólo sale como columna de
entrada de D (``dmc_R_*``, §0.4.3), que no se resume ni se informa.

Qué hace cada parte:
- ``leer_decision`` y ``ganador_ambiental``: el ganador y los hiperparámetros del uso ambiental de ``decision.json`` (o
  el restringido de la rama 3 del Anexo B).
- ``operador_grilla`` (``OperadorGrilla``, ``leer_operador``): el operador del fondo celda × píxel (pesos bilineales y
  Δz) y los vecinos del núcleo celda × estación de cada juego de hiperparámetros del ganador, con su sha256 y sus bytes.
- ``columnas_bloque`` y ``mc_bloque``: las columnas de la variante (I: ``mc_*``; D: ``fe_*`` y ``dmc_R_*``) en un lote de
  celdas y horas, con la red de cada variable si se pide un escenario de la TF.
- ``lateral_monitores``, ``huella_contenido``, ``unir_partes`` y ``comprobar_union``: la tabla lateral de un
  contaminante en la celda de cada monitor del panel de la red 2 (R11, R21), sus metadatos, la unión de sus partes
  (por año) y la unión con ``meteorologia_v2.unir_sidecar`` real.
- ``fabrica_tf_contaminantes``: la fábrica de A26, ``fabrica(modelo, variante, escenario, celdas, dias)`` → día × celda,
  que ``tendencias.tf_contaminantes`` llama (Anexo B, TF de contaminantes).
- ``direccion_sin_cos``, ``diferencias_con_el``, ``cargar_adaptador`` y ``regla_el``: la convención de ``el_*``
  (MC-28) y el código fijado, por ``fijados``.

Dueño: I19 (ola 5; con las correcciones de su revisión independiente: H2 a H9 y PED-7 de I20).
Lecturas propias (AMB-n), para el addendum de M1:
- AMB-1. **El soporte de una tabla lateral** (§7.1: «columnas ``mc_*`` en la celda de ≈ 1 km del monitor, con z de la
  celda (el mismo soporte que la producción)»; R21; MC-09: «las coordenadas son las de ``estaciones`` de ese archivo»).
  La celda de cada monitor es el campo ``celda`` de su entrada en ``estaciones`` de ``pliegues_v2_red2.json`` (A8: la
  celda nunca se deduce de un id; la buscó v2 por coordenadas). Las columnas se evalúan en esa celda del operador, en su
  centro y con su ``z_media`` (§3: «uso ambiental: z = media NASADEM de la celda»), con ``columnas_bloque``: la lateral
  de un monitor es, bit a bit, la columna de ``mc_bloque`` de su celda, la misma que verá la producción v2. Las
  coordenadas del monitor no entran a la cuenta. Si el panel trae ``celda``, debe ser la de ``pliegues`` en todas sus
  filas; un monitor del panel sin celda, sin entrada en ``estaciones`` o fuera de ``contaminantes.<pol>.estaciones`` es
  un error, y una celda que no está en el operador también.
- AMB-2. **Las claves** (§7.1: «claves (``estacion``, ``ts_utc`` en UTC) del panel […], leído en sólo lectura»; R11,
  R21). Las filas son los pares (``estacion``, ``ts_utc``) distintos del panel ``panel_<pol>_red2.parquet``, ordenados
  por estación y hora; el panel no se modifica (se leen sólo ``estacion``, ``ts_utc`` y, si está, ``celda``). Un
  ``ts_utc`` sin zona se lee como UTC (el nombre lo dice, y el panel de la red 2 lo guarda sin zona, como el v1; §7.1,
  punto 2: ``correr_v2`` lo comprueba y lo localiza); con zona, se lleva a UTC. Toda hora debe ser HH:00 exacta (§3: «en
  las mismas horas que ERA5-Land»). **El panel está atado a su registro** (R21, MC-09: «M6 exige la huella de
  ``panel_{pm25,no2}_red2.parquet`` del mismo registro»; H5 de la revisión): llega como los bytes del archivo, y su
  sha256 se calcula aquí y debe ser la de ``contaminantes.<pol>.panel.sha256`` de ``pliegues_v2_red2.json`` (como con
  ``decision.json`` y ``pliegues``); o ya leído, con ``panel_sha256`` (que debe ser la del registro) y con las filas y
  las estaciones distintas que registra ``contaminantes.<pol>.panel.filas`` y ``.estaciones``, que se cuentan. En los
  dos casos se exigen ``filas`` y ``estaciones`` enteros en el registro y que calcen. ``pliegues_sha256`` es la de los
  bytes de ``pliegues_v2_red2.json`` (se calcula aquí si llegan los bytes). **Por partes** (``anios``): el panel es
  siempre el entero (así queda atado) y la lateral se arma sólo con las filas de esos años UTC de ``ts_utc``; las partes
  se unen con ``unir_partes`` (AMB-16). Contaminantes: ``tipos.CONTAMINANTES_M6`` (pm25 y no2); O3 entra con su
  enmienda.
- AMB-3. **Las columnas de I** (§7.1; MC-28). Con el producto de ``producto.campos`` (T = T_F + R_T; Td = mín(Td_F +
  R_Td, T); u y v sumados; p = p_F·exp(R_p); HR por Magnus sobre agua 17,625 y 243,04, recortada en [0, 100]; rapidez
  √(u² + v²)): ``mc_t2m`` = T + 273,15 y ``mc_d2m`` = Td + 273,15 (K), ``mc_rh`` = HR (%), ``mc_sp`` = 100·p (Pa),
  ``mc_u10`` y ``mc_v10`` (m/s, «hacia», como u10 y v10), ``mc_wind`` = la rapidez, y ``mc_wdir_sin`` y ``mc_wdir_cos``
  = sin y cos del ángulo ``arctan2(u, v)`` de ``_features.py`` (en calma arctan2(0, 0) = 0: sin 0 y cos 1, como
  ``el_wdir_*``; NaN si u o v no es finito). Todo en float64 hasta el final y float32 al salir; los NaN se escriben
  con un solo patrón de bits, para que las huellas no dependan de cómo nació cada NaN.
- AMB-4. **Las columnas de D** (Anexo B: «``fe_*``, el fondo reescalado a la celda del monitor con el mismo operador
  que I (9 columnas análogas a ``mc_*``), más ``dmc_R_v``»; MC-28). ``fe_*`` son las fórmulas de AMB-3 sobre el fondo
  con R = 0 (``producto.campos(F, 0)``), así que ``fe_d2m`` es el Td_F de §4.1, ya con Td_F := mín(Td_F, T_F), y
  ``fe_rh`` su HR. ``dmc_R_T``, ``dmc_R_Td`` (K), ``dmc_R_u``, ``dmc_R_v`` (m/s) y ``dmc_R_p`` (adimensional, ln(p/p_F))
  son el R del ganador ambiental antes del mín y de la exponencial. Así I y D difieren sólo en integrar antes:
  ``mc_t2m`` = ``fe_t2m`` + ``dmc_R_T``, ``mc_d2m`` = mín(``fe_d2m`` + ``dmc_R_Td``, ``mc_t2m``), ``mc_u10`` =
  ``fe_u10`` + ``dmc_R_u``, ``mc_v10`` = ``fe_v10`` + ``dmc_R_v`` y ``mc_sp`` = ``fe_sp``·exp(``dmc_R_p``), hasta el
  redondeo (``test_ambiental`` lo comprueba en float64, también donde el mín recorta). No se agregan el soporte ni la
  distancia (Anexo B). **Eso vale en producción y en el escenario «completo» de la TF, no en «cambio»** (AMB-10;
  pregunta P-AMB-1): allí ``mc_d2m`` se recorta contra la T de la red de Td, no contra ``mc_t2m`` (que usa la de T), así
  que puede quedar ``mc_d2m > mc_t2m`` y ``mc_d2m`` ≠ mín(``fe_d2m`` + ``dmc_R_Td``, ``mc_t2m``): dentro de la TF, I y D
  no son «integrar contra separar» con las mismas R (``test_ambiental`` lo muestra).
- AMB-5. **R del ganador** (§4.1-§4.6; PRO-4, PRO-5). A, B y AB con ``candidatos`` (``correccion_a``, ``matriz_q`` y
  ``correccion_b``, ``correccion_ab``) sobre la lista fija de vecinos que guarda el operador; C con
  ``candidatos.ajustar_c`` sobre ``datos.filas_c["C"]`` del entrenamiento de producción y ``candidatos.predecir_c``
  fila a fila (celda × hora), con el estado del fondo de la celda (T_F, T_F − Td_F, la rapidez del fondo y la amplitud
  de T_F en el día UTC, que se calcula sobre los días UTC enteros de las horas pedidas) y los estáticos de la celda
  (``ESQUEMA_ESTATICAS_CELDA_C``, cotejados por ``celda``). El entrenamiento de producción son todas las estaciones no
  excluidas de ``datos.estaciones`` (§4.9, «Producción»), y deben ser las del operador: se comparan sus códigos y la
  huella de su geometría (lat, lon, z_s y grupo). Es la cuenta de ``producto.correccion``: ``test_ambiental`` la
  compara bit a bit.
- AMB-6. **El operador** (§7.1: «matrices dispersas celda × píxel (pesos bilineales y Δz) y celda × estación (pesos del
  núcleo por variable), con sus hiperparámetros y su sha256»). El del fondo es el de ``fondo_era5l.operador`` en las
  celdas (z = ``z_media``), en la forma ELL de ``tipos.OperadorPuntos`` (n × 4, en el orden NO, NE, SO, SE de las
  casillas, que es el de la suma). El del núcleo es, por cada juego de hiperparámetros distinto que usa el ganador
  (A y B: uno por variable; AB: el de A y el de Φ′), la lista fija de vecinos de ``candidatos.vecinos`` en forma CSR
  (``indptr``, ``indices`` = la estación de entrenamiento y ``d_ef`` en km), con los vecinos en su orden: la lista es
  siempre un prefijo de las 30 casillas, así que se rehace exacta. Se guarda d_ef y no k: los pesos k = exp(−½
  (d_ef/L)²) salen de d_ef y L con la misma cuenta de ``candidatos`` (``matriz_nucleo`` los da en CSR), bit a bit. Las
  celdas van ordenadas por id. Los bytes: una firma, una cabecera JSON canónica (esquema, uso, ganador,
  hiperparámetros, códigos y grupos de entrenamiento, huellas, los umbrales del operador y la lista de arreglos) y los
  arreglos en orden little-endian; no es un zip (``salidas`` rechaza los comprimidos que no son gzip, SLD-6).
  ``sha256`` es el de esos bytes y no depende del orden en que se arman. **Los umbrales del operador** (H9):
  ``UMBRALES_OPERADOR`` (Γ, el radio del respaldo del fondo y los NUC_*) van con sus valores en la cabecera y con su
  huella (``umbrales_sha256``, el sha256 del JSON canónico de {id: valor}); ``columnas_bloque`` (y con ella la lateral y
  la fábrica) exige que los umbrales con que se evalúa den la misma huella. **Inmutable** (H9): todos sus arreglos son de
  sólo lectura; ``leer_operador`` da ``ErrorAmbiental`` (nunca ``KeyError``) si a la cabecera le falta una clave o un
  arreglo, y la lista de arreglos debe ser exactamente la que escribe ``a_bytes``, seguidos y con sus tipos. Su tamaño:
  AMB-15.
- AMB-7. **Los hiperparámetros de ``decision.json``** (§6.2, paso 6; M3-4, paso 11). Las decisiones del uso ambiental
  (una por grupo: T_Td, u_v y p) traen ``ganador`` y ``hiperparametros`` = {candidato: {variable: θ}}, con θ en la forma
  de ``decision._a_json``: ``{"L_km", "lam", "kappa"}`` en A y B, ``[θ de A, θ de Φ′]`` en AB y α en C. Los grupos van
  enteros y u y v comparten θ (MC-43). **Rama 3** (Anexo B; §6.4): ``restringido`` = {grupo: candidato} de
  ``decision_m6.json``; sólo cambian los grupos cuyo ganador era B o AB, y sólo a A o C; los demás deben quedar iguales.
  Sus hiperparámetros salen del mismo ``decision.json`` (``hiperparametros`` del candidato restringido); si faltan, es
  un error. **El operador restringido lleva además la huella de ``m6/ramas_m6.json``** (``ramas_m6_sha256``; H3 de la
  revisión, ORQ-30 y P-ORQ-2 de ``orquestacion``): ``decision_m6.json`` cita las laterales y el operador vigentes, así
  que no puede ser citado por ellos; ``ramas_m6.json`` (la misma decisión de las ramas, con las huellas de sus entradas)
  se escribe antes que el operador restringido, y ``decision_m6.json`` va al final y la cita. Pregunta H3.
- AMB-8. **La huella de ``decision.json``** (§7.1: «sha256 […] de ``decision.json``»). Si llegan los bytes del archivo,
  es la de esos bytes (y el JSON se lee de ellos); si llega el diccionario, se exige ``decision_sha256``, la del
  archivo. El operador la guarda y la lateral exige la misma.
- AMB-9. **Los meses ERA5-Land** (§7.1: «leyendo los meses ERA5-Land y las tablas de residuos»; §0, regla 8: los
  módulos de ciencia no leen archivos). ``meses`` es un mapa o una función AAAAMM → ``fondo_era5l.MesE5L`` ya leído y
  comprobado (unidades y completitud: FON-1 y FON-2, de quien lo lee). Una hora pedida que su mes no trae es un error:
  el producto no interpola en el tiempo (§3). En la lateral, las horas posteriores a la última con dato de ERA5-Land
  no se piden (AMB-17); un mes que falte antes de ella sigue siendo un error.
- AMB-10. **La red de cada variable en un escenario de TF** (A26; TEN-4, TEN-5, TEN-20). ``redes`` da, por variable de
  la TF (T, Td, rapidez y p), la red del año UTC de cada hora (None: todas). Una estación está disponible si está en esa
  red y su q está definido. Las columnas: ``mc_t2m`` y ``dmc_R_T`` con la red de T; ``mc_d2m`` y ``dmc_R_Td`` con la de
  Td, también la R_T que entra al mín (P-TEN-3), así que en «cambio» ``mc_d2m`` puede quedar sobre ``mc_t2m`` (AMB-4);
  ``mc_rh`` con T y Td de la red de Td (la humedad es la variable de Td; pregunta P-AMB-1, que pide ratificar las dos
  cosas); viento y dirección con la de la rapidez; ``mc_sp`` y ``dmc_R_p`` con la de p. A y C no miran la
  red (TEN-4: r̄, la lista de vecinos y los coeficientes son los de la red completa), así que su TF es 0 por
  construcción. Con todas las redes en None («completo») la cuenta es la de producción, bit a bit.
- AMB-11. **Los días de la fábrica** (A26; MC-44: d2000 es el día UTC). La fábrica pide las columnas en las 24 horas UTC
  de cada día (``horas_dia_utc``), salvo que la fábrica de producción v2 dé otra ``horas_de_dias`` (por ejemplo, el día
  civil; pregunta P-AMB-2: los días de la muestra de ``tendencias``, d mód 11 = 3, se leen como días UTC por omisión,
  porque d2000 es el día UTC; si v2 predice por día civil, su fábrica pasa ``horas_de_dias``).
  ``predecir(modelo, variante, tabla, celdas, dias)`` es la fábrica de producción v2 (aún no
  escrita): recibe la tabla larga de ``mc_bloque`` y devuelve la predicción día × celda.
- AMB-12. **Los metadatos** (§2.3 del diseño): exactamente ``METADATOS_LATERAL`` y en ese orden, que son
  ``tipos.METADATOS_LATERAL`` más ``claves_tras_ultima_hora`` (AMB-17; pedido PED-AMB-1 a quien cuida ``tipos``, para
  que la agregue allí; mientras tanto la agrega este módulo, y no la repite si ``tipos`` ya la trae). ``model_ready`` y
  ``source_policy_verified`` son True y ``policy_sha256`` se calcula aquí (H7 de la revisión; pregunta H7): la lateral
  recibe los bytes de ``politicas_meteo_v1.json`` (``politica``), comprueba que son un JSON en UTF-8 que es una lista no
  vacía de políticas (objetos, sin claves repetidas ni NaN, la forma de ``politicas.de_json``) y toma su sha256; si
  llega además la huella esperada (``policy_sha256``, la de la procedencia de las entradas, p. ej. ``sha256.json`` de la
  corrida), debe ser la misma. Lo que «verificada» afirma es eso: la política de la corrida, leída y con su huella
  rehecha; que la DMC entró por ``cargar_dmc`` con ella lo garantiza la cadena de M3-4 (``qc`` con esa política, y su
  huella en ``sha256.json``), no este módulo. ``content_sha256`` es ``huella_contenido`` (AMB-18). No es la identidad
  que calcula ``unir_sidecar``, que depende de ``pandas.util.hash_pandas_object``.
- AMB-13. **La unión** (§7.1, punto 2; A29). ``comprobar_union`` hace lo que hará ``correr_v2``: localiza en UTC un
  ``ts_utc`` sin zona del panel (en una copia) y llama a ``meteorologia_v2.unir_sidecar`` real (cargado por
  ``fijados.cargar_adaptador``) con los metadatos tal cual. Si el código fijado la rechaza, su ``ValueError`` sale sin
  cambios. Si la acepta, exige: las mismas filas, el mismo índice y el mismo orden; las columnas del panel intactas; las
  nuevas, las de la variante en su orden y con los valores de la lateral en cada clave, comparada en UTC aunque el
  panel traiga otra zona (NaN donde la lateral no la tiene, como las horas tras la última con dato, AMB-17); la
  identidad de ``unir_sidecar`` con exactamente sus claves, esas columnas, la política, los conteos y un
  ``content_sha256`` de 64 hexadecimales; y los metadatos de AMB-12, también ``content_sha256``. Sin panel, arma uno de
  prueba con las claves de la tabla al revés y una clave más que la tabla no tiene.
- AMB-14. **El lote** (MC-37; PRO-1, PRO-2). ``columnas_bloque`` acepta horas cualesquiera (enteros h, crecientes y sin
  repetir) y celdas cualesquiera del operador (sin repetir, en el orden pedido). Parte las horas por mes UTC; cada hora
  y cada celda se calculan solas (el núcleo, A y C fila a fila; el fondo por punto), así que partir las celdas o las
  horas no cambia ningún bit, salvo el estado de C, que se toma de los días UTC enteros (``test_ambiental`` lo
  comprueba). ``mc_bloque`` da la tabla larga: ``celda`` (int64), ``ts_utc`` (UTC) y las columnas de la variante en
  float32, con las horas de cada celda seguidas y las celdas en el orden pedido.
- AMB-15. **El tamaño del operador** (MC-15; H6; pregunta P-AMB-3). Por celda: 32 B (celda, lat, lon y z) y 81 B del
  fondo (4 × (4 + 8 + 8) + 1); por cada juego del núcleo, 8 B de ``indptr`` y 12 B por vecino (4 de la estación y 8 de
  d_ef). Con las 838.430 celdas, la lista llena (NUC_VECINOS = 30) y los 8 juegos que puede pedir AB en los cuatro
  grupos de variables (T, Td, (u, v) y p, dos por grupo), son 3.057 B por celda: **≈ 2,6 GB**; con 4 juegos (A o B en
  todos), ≈ 1,3 GB. §7.1 decía ≈ 200 MB y MC-15 ≈ 0,5-1 GB. En memoria, ``leer_operador`` tiene los bytes y una sola
  copia de los arreglos (la segunda conversión de tipos es ``copy=False``), así que cada proceso que lo lee pide hasta
  ≈ 5,2 GB mientras rehace la huella y ≈ 2,6 GB después (si quien llama suelta los bytes). Lo mide I21; si no cabe con
  los procesos de M5, la salida es leer los arreglos como vistas de sólo lectura sobre los bytes (sin copia), con la
  cabecera rellenada para alinearlos.
- AMB-16. **Las partes de una lateral** (ORQ-27; PED-7 de I20). ``unir_partes`` recibe las partes (tabla, metadatos)
  de ``lateral_monitores`` con ``anios`` (cada una con su ``content_sha256`` comprobado) y devuelve la lateral entera:
  las filas de todas, ordenadas por estación y hora como ``lateral_monitores``, con los metadatos comunes (deben ser
  iguales salvo ``content_sha256`` y ``claves_tras_ultima_hora``), la suma de ``claves_tras_ultima_hora`` y el
  ``content_sha256`` de la tabla entera. Una clave en dos partes es un error. Como cada fila sale sólo de su celda, su
  hora y su mes ERA5-Land (AMB-14), es bit a bit la lateral armada de una vez sobre los mismos años
  (``test_ambiental`` lo comprueba).
- AMB-17. **Las horas tras el último dato de ERA5-Land** (§3: «del 2000-01-01 a su último dato […] Sin interpolación
  temporal»; H2 de la revisión; pregunta H2). El panel de la red 2 llega más allá (R4: al 2026-10-24). La lateral
  recibe la última hora con dato (``h_ultima``, la de FON-1, la misma con que se comprueban los meses): las claves con
  ``ts_utc`` posterior quedan fuera de la lateral (``unir_sidecar`` les pondrá NaN, AMB-13) y se cuentan, como claves
  distintas y en un solo entero, en ``claves_tras_ultima_hora`` de los metadatos (sin códigos ni horas). Una clave
  anterior o igual a ``h_ultima`` cuyo mes no llega sigue siendo un error (AMB-9).
- AMB-18. **La receta de ``content_sha256``** (``huella_contenido``; H9), para que ``correr_v2`` pueda rehacerla sin
  este módulo. Es el sha256 de la concatenación, en este orden, de:
  1. la cabecera: el JSON canónico (claves ordenadas, separadores «,» y «:» sin espacios, UTF-8 sin escapar lo que no es
     ASCII, sin NaN) de ``{"columnas": [las columnas de la tabla en su orden, también las claves], "esquema": la versión
     del esquema (``tipos.ESQUEMA_LATERAL_I.version`` o ``_D``), "filas": n, "tipos": [el tipo de pandas de cada
     columna según ese esquema: "string", "datetime64[ns, UTC]" y "float32"]}``;
  2. cada código de ``estacion``, en el orden de las filas, en UTF-8 y seguido de un byte 0 (un código con el carácter
     nulo es un error);
  3. ``ts_utc`` como enteros de 8 bytes little-endian con signo: nanosegundos desde 1970-01-01T00:00Z (8·n bytes);
  4. cada columna de la variante, en el orden de ``columnas`` de los metadatos: float32 little-endian (4·n bytes), con
     todo NaN escrito como 0x7FC00000 (los demás valores, sus bits).
  ``test_ambiental`` la rehace con sólo ``hashlib``, ``json`` y ``struct``.
Preguntas abiertas (P-AMB-n, en el informe de la ola 5): P-AMB-1, la red de ``mc_rh`` y del recorte de ``mc_d2m`` en la
TF de contaminantes (rige AMB-10, la de Td: ``mc_d2m`` puede quedar sobre ``mc_t2m`` en «cambio», e I y D no son allí
«integrar contra separar»); P-AMB-2, el día de la TF de contaminantes (rige el día UTC de MC-44, AMB-11); P-AMB-3, el
tamaño del operador, ≈ 2,6 GB como cota frente a los ≈ 200 MB de §7.1 y los 0,5-1 GB de MC-15 (AMB-15; lo mide I21);
H2, las claves del panel tras el último dato de ERA5-Land (rige AMB-17); H3, la huella que cita el operador restringido
(rige ``ramas_m6.json``, AMB-7); H7, qué afirma ``source_policy_verified`` (rige AMB-12).
Diferencias con el diseño (§3): ``lateral_monitores`` recibe ``pliegues`` (los bytes de ``pliegues_v2_red2.json``) en
vez de ``monitores``, y ``meses``, ``datos``, ``umbrales``, ``politica`` (bytes), ``h_ultima`` y, optativos,
``policy_sha256``, ``panel_sha256`` y ``anios`` en vez de ``rutas``; ``panel`` puede ser los bytes del archivo;
``operador_grilla`` devuelve un ``OperadorGrilla`` (con ``a_bytes()`` y ``sha256``) en vez de una ruta, y recibe
``validos``, ``z_pix``, ``umbrales`` y, en la rama 3, ``restringido`` y ``ramas_m6_sha256`` en vez de ``rutas``;
``mc_bloque`` recibe ``datos`` (``tipos.DatosCompetencia``, con los residuos en ``datos.residuos``, porque A usa las
climatologías y C sus filas) en vez de ``residuos``, y además ``umbrales``, ``estaticos`` y ``redes``;
``comprobar_union`` devuelve la identidad de ``unir_sidecar`` y recibe ``panel`` opcional; los metadatos traen una
clave más que §2.3 (AMB-12). Funciones nuevas: ``columnas_bloque``, ``leer_operador``, ``leer_decision``,
``ganador_ambiental``, ``huella_contenido``, ``unir_partes``, ``fabrica_tf_contaminantes``, ``horas_dia_utc``,
``direccion_sin_cos``, ``etiqueta_hiper``, ``diferencias_con_el``, ``cargar_adaptador`` y ``regla_el``.
Depende de: tipos, constantes, fijados, producto, fondo_era5l y candidatos. Los umbrales llegan como objeto (``.a``),
así que ``umbrales`` no hace falta importarlo. El panel en bytes se lee con ``pyarrow``, en memoria.
"""
from __future__ import annotations

import functools
import hashlib
import io
import json
import math
import re
import struct
from dataclasses import dataclass, field
from types import MappingProxyType, ModuleType
from typing import Any, Callable, Iterator, Mapping

import numpy as np
import pandas as pd

from meteo_combinada import candidatos, constantes, fijados, fondo_era5l, producto, tipos
from meteo_combinada.tipos import Candidato, Grupo, Hiper, Uso, Variable, VariableMetrica, Variante

# ---------------------------------------------------------------------------
# Nombres y constantes
# ---------------------------------------------------------------------------
USO = Uso.AMBIENTAL
CONTAMINANTES = tipos.CONTAMINANTES_M6                       # pm25 y no2 (Anexo B; O3 por su enmienda)
CLAVES = ("estacion", "ts_utc")                              # las de unir_sidecar
SUFIJOS = tipos.SUFIJOS_EL                                   # MC-28: los de el_*
COLUMNAS_MC = tuple(f"mc_{s}" for s in SUFIJOS)
COLUMNAS_FE = tuple(f"fe_{s}" for s in SUFIJOS)
COLUMNAS_R = tipos.COLUMNAS_R_D
COLUMNAS_VARIANTE: Mapping[str, tuple[str, ...]] = MappingProxyType({
    Variante.I.value: COLUMNAS_MC, Variante.D.value: COLUMNAS_FE + COLUMNAS_R})
ESQUEMA_DE: Mapping[str, tipos.Esquema] = MappingProxyType({
    Variante.I.value: tipos.ESQUEMA_LATERAL_I, Variante.D.value: tipos.ESQUEMA_LATERAL_D})
UNIDADES: Mapping[str, Mapping[str, str]] = MappingProxyType({
    Variante.I.value: MappingProxyType({f"mc_{s}": tipos.UNIDADES_EL[s] for s in SUFIJOS}),
    Variante.D.value: MappingProxyType({**{f"fe_{s}": tipos.UNIDADES_EL[s] for s in SUFIJOS}, **tipos.UNIDADES_R_D})})
R_DE_COLUMNA = dict(zip(COLUMNAS_R, fondo_era5l.CLAVES_R))   # dmc_R_T → R_T, …
VARIABLES = producto.VARIABLES                               # T, Td, u, v, p
GRUPO_DE = {v: g for g, vs in producto.VARIABLES_DE_GRUPO.items() for v in vs}
GRUPOS = producto.GRUPOS_DEL_USO[USO]                        # T_Td, u_v y p
CANDIDATOS = producto.CANDIDATOS_DEL_USO[USO]                # A, B, AB y C
DEL_NUCLEO = (Candidato.A, Candidato.B, Candidato.AB)
CON_RED = (Candidato.B, Candidato.AB)                        # AMB-10: sólo B y AB miran la red del escenario
CAMBIA_EN_RAMA_3 = (Candidato.B, Candidato.AB)               # Anexo B, rama 3: «sólo los grupos cuyo ganador era B o AB»
RESTRINGIDOS = (Candidato.A, Candidato.C)                    # «entre A y C»
# AMB-10: la variable de la TF (§5.7) cuya red rige cada variable del producto.
RED_DE: Mapping[str, str] = MappingProxyType({
    Variable.T.value: VariableMetrica.T.value, Variable.TD.value: VariableMetrica.TD.value,
    Variable.U.value: VariableMetrica.RAPIDEZ.value, Variable.V.value: VariableMetrica.RAPIDEZ.value,
    Variable.P.value: VariableMetrica.P.value})
VARIABLES_RED = (VariableMetrica.T.value, VariableMetrica.TD.value, VariableMetrica.RAPIDEZ.value,
                 VariableMetrica.P.value)
ESCENARIOS_TF = ("cambio", "completo", "constante")          # los de tendencias.ESCENARIOS (paridad en la prueba)
ESQUEMA_OPERADOR = "meteo-combinada-operador-grilla/2"      # /2: los umbrales y ramas_m6_sha256 en la cabecera (H3, H9)
FIRMA_OPERADOR = b"\x89MCOPERADOR\r\n\x1a\n"                # AMB-6: un byte que no es UTF-8, como la firma de PNG
CLAVES_HIPER = ("L_km", "lam", "kappa")
# AMB-6 (H9): los umbrales de los que depende el operador o su uso: Γ (campos_fondo), el radio del respaldo del fondo y
# los del núcleo (la lista fija de vecinos y las rejillas de sus hiperparámetros).
UMBRALES_OPERADOR = ("GAMMA_K_KM", "VECINO_KM", "NUC_L", "NUC_LAMBDA", "NUC_KAPPA", "NUC_CORTE", "NUC_VECINOS")
# AMB-12 y AMB-17 (H2): las claves del panel tras la última hora con dato de ERA5-Land, en un solo entero.
CLAVE_TRAS_ULTIMA = "claves_tras_ultima_hora"
METADATOS_LATERAL = tipos.METADATOS_LATERAL + (() if CLAVE_TRAS_ULTIMA in tipos.METADATOS_LATERAL
                                               else (CLAVE_TRAS_ULTIMA,))
# AMB-6: los arreglos de los bytes del operador, en su orden, con su tipo (los del núcleo, por cada juego).
_ARREGLOS_BASE = (("celdas", "<i8"), ("lat", "<f8"), ("lon", "<f8"), ("z", "<f8"), ("pix", "<i4"), ("w", "<f8"),
                  ("dz", "<f8"), ("respaldo", "|b1"), ("grupo_est", "<i4"))
_ARREGLOS_NUCLEO = (("indptr", "<i8"), ("indices", "<i4"), ("d_ef", "<f8"))
_CLAVES_CABECERA = ("esquema", "uso", "ganador", "hiperparametros", "nucleo_de", "nucleos", "n_vecinos", "n_celdas",
                    "codigos", "grupos", "estaciones_sha256", "decision_sha256", "umbrales", "umbrales_sha256",
                    "restringido", "ramas_m6_sha256", "arreglos")
_CLAVES_ARREGLO = ("nombre", "tipo", "forma", "inicio", "bytes")
# AMB-13: las claves de la identidad que devuelve meteorologia_v2.unir_sidecar.
_CLAVES_IDENTIDAD = ("content_sha256", "policy_sha256", "source_artifact_sha256", "columns", "sidecar_rows",
                     "panel_rows")

_LARGO = struct.Struct("<Q")                                 # el largo de la cabecera del operador
_KELVIN = float(constantes.valor("KELVIN"))
_PA_POR_HPA = 100.0
_HORAS_DIA = 24
_EPOCA_H = np.datetime64("2000-01-01T00", "h")               # h = 0 (tipos.EPOCA_H)
_EPOCA_NS = np.datetime64("2000-01-01T00:00:00", "ns")
_ANIO_UNIX = int(str(np.datetime64(0, "Y")))                  # el año del origen de datetime64
_NS_POR_HORA = int(np.timedelta64(1, "h").astype("timedelta64[ns]").astype(np.int64))
_INT32 = np.iinfo(np.int32)
_HEX64 = re.compile(r"[0-9a-f]{64}")
_HIPER_SOLO_CODIGOS = Hiper(1.0, 0.0, 1.0)                    # sólo para leer códigos y grupos sin puntos
_NAN32 = np.float32(np.nan)
_CITADOS = 5                                                 # no-umbral: elementos citados en un mensaje de error


class ErrorAmbiental(RuntimeError):
    """Una entrada mal armada o fuera de las reglas del uso ambiental: detiene la corrida (como ``ErrorProducto``,
    PRO-17); nunca se confunde con un «no normalizable»."""


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def _sha256(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _json_canonico(obj: Any) -> bytes:
    """El JSON canónico de ``entorno.json_canonico`` (claves ordenadas, «,» y «:», UTF-8, sin NaN): ``entorno`` no es
    una dependencia de este módulo (§1 del diseño); ``test_ambiental`` compara los bytes."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _hex64(valor, nombre: str) -> str:
    if not isinstance(valor, str) or _HEX64.fullmatch(valor) is None:
        raise ErrorAmbiental(f"{nombre}: un sha256 de 64 hexadecimales en minúscula")
    return valor


def _json_estricto(datos: bytes, nombre: str) -> Any:
    """Un JSON en UTF-8 sin claves repetidas ni NaN o Infinity (la lectura de ``politicas.de_json``)."""
    def sin_repetidas(pares):
        salida = {}
        for k, v in pares:
            if k in salida:
                raise ErrorAmbiental(f"{nombre}: la clave {k!r} se repite")
            salida[k] = v
        return salida

    def sin_no_finitos(token):
        raise ErrorAmbiental(f"{nombre}: {token} no es JSON válido")
    try:
        return json.loads(datos.decode("utf-8"), object_pairs_hook=sin_repetidas, parse_constant=sin_no_finitos)
    except (UnicodeDecodeError, ValueError) as error:
        raise ErrorAmbiental(f"{nombre} no es un JSON en UTF-8") from error


def _entero(valor, nombre: str, *, minimo: int | None = None) -> int:
    if isinstance(valor, (bool, np.bool_)) or not isinstance(valor, (int, np.integer)):
        raise ErrorAmbiental(f"{nombre}: un entero, no {valor!r}")
    if minimo is not None and int(valor) < minimo:
        raise ErrorAmbiental(f"{nombre}: un entero ≥ {minimo}, no {valor!r}")
    return int(valor)


def _umbrales_operador(umbrales) -> dict[str, Any]:
    """AMB-6 (H9): {id: valor} de ``UMBRALES_OPERADOR``, en la forma del JSON (listas en vez de tuplas)."""
    a = getattr(umbrales, "a", None)
    if not callable(a):
        raise ErrorAmbiental("umbrales: el objeto de umbrales de la corrida (con .a)")
    salida = {}
    for ident in UMBRALES_OPERADOR:
        try:
            valor = a(ident)
        except (KeyError, ValueError) as error:
            raise ErrorAmbiental(f"umbrales: falta {ident}") from error
        valores = list(valor) if isinstance(valor, (tuple, list)) else [valor]
        if not valores or any(isinstance(x, (bool, np.bool_)) or not isinstance(x, (int, float, np.integer, np.floating))
                              or not math.isfinite(float(x)) for x in valores):
            raise ErrorAmbiental(f"umbrales: {ident} no es numérico ({valor!r})")
        normal = tuple(int(x) if isinstance(x, (int, np.integer)) else float(x) for x in valores)
        salida[ident] = normal if isinstance(valor, (tuple, list)) else normal[0]
    return salida


def _huella_umbrales(valores: Mapping[str, Any]) -> str:
    return _sha256(_json_canonico(dict(valores)))


def _hora_ultima(h_ultima) -> int:
    """AMB-17: la última hora con dato de ERA5-Land (h desde 2000-01-01T00Z, la de FON-1), dentro de int32."""
    h = _entero(h_ultima, "h_ultima (la última hora con dato de ERA5-Land, FON-1)")
    if h < _INT32.min or h > _INT32.max:
        raise ErrorAmbiental("h_ultima fuera de int32")
    return h


def _anios(anios) -> np.ndarray | None:
    """AMB-2: None (todo el panel) o los años UTC de la parte, sin repetir."""
    if anios is None:
        return None
    lista = [anios] if isinstance(anios, (int, np.integer)) and not isinstance(anios, (bool, np.bool_)) else anios
    try:
        lista = [_entero(a, "anios") for a in lista]
    except TypeError:
        raise ErrorAmbiental("anios: un año o una lista de años (UTC)") from None
    if not lista or len(set(lista)) != len(lista):
        raise ErrorAmbiental("anios: al menos un año, sin repetir")
    return np.array(sorted(lista), dtype=np.int64)


def _variante(valor) -> Variante:
    try:
        return Variante(valor)
    except ValueError:
        raise ErrorAmbiental(f"variante desconocida: {valor!r}; son {[v.value for v in Variante]}") from None


def _contaminante(pol) -> str:
    if pol not in CONTAMINANTES:
        raise ErrorAmbiental(f"contaminante {pol!r}: las tablas laterales de M6 son de {list(CONTAMINANTES)} (Anexo B; "
                             "O3 entra por su propia enmienda, §7.1)")
    return pol


def _enteros(x, nombre: str) -> np.ndarray:
    a = np.asarray(x)
    if a.ndim != 1 or a.dtype == bool or not np.issubdtype(a.dtype, np.integer):
        if a.ndim == 1 and a.size == 0:
            return a.astype(np.int64)
        raise ErrorAmbiental(f"{nombre}: enteros en un arreglo de una dimensión")
    return a.astype(np.int64)


def _horas(horas) -> np.ndarray:
    """AMB-14: h enteras (horas desde 2000-01-01T00Z), estrictamente crecientes y dentro de int32."""
    h = _enteros(horas, "horas")
    if h.size and (h.min() < _INT32.min or h.max() > _INT32.max):
        raise ErrorAmbiental("horas fuera de int32")
    if h.size > 1 and not bool(np.all(np.diff(h) > 0)):
        raise ErrorAmbiental("las horas deben ir estrictamente crecientes y sin repetir")
    return h


def _yyyymm(h: np.ndarray) -> np.ndarray:
    m = (_EPOCA_H + h.astype("timedelta64[h]")).astype("datetime64[M]").astype(np.int64)   # meses desde el origen
    return (m // 12 + _ANIO_UNIX) * 100 + m % 12 + 1


def _por_mes(h: np.ndarray) -> Iterator[tuple[int, slice]]:
    """(AAAAMM, tramo) de cada mes UTC de unas horas crecientes, en orden."""
    if h.size == 0:
        return
    meses = _yyyymm(h)
    cortes = np.flatnonzero(np.diff(meses)) + 1
    inicios = np.r_[0, cortes]
    finales = np.r_[cortes, h.size]
    for i0, i1 in zip(inicios, finales):
        yield int(meses[i0]), slice(int(i0), int(i1))


def horas_dia_utc(dias) -> np.ndarray:
    """Las 24 horas UTC (h) de cada día d2000 (MC-44), en orden: el día de la fábrica por omisión (AMB-11)."""
    d = _enteros(dias, "dias")
    return (d[:, None] * _HORAS_DIA + np.arange(_HORAS_DIA)[None, :]).ravel()


def _ns_de(h: np.ndarray) -> np.ndarray:
    """Las horas h como datetime64[ns] sin zona (UTC)."""
    return (_EPOCA_NS + h.astype("timedelta64[h]")).astype("datetime64[ns]")


def direccion_sin_cos(u, v) -> tuple[np.ndarray, np.ndarray]:
    """sin y cos del ángulo ``arctan2(u, v)`` de ``_features.py`` (MC-28; AMB-3): la dirección «hacia» desde el norte en
    sentido horario. En calma (u = v = 0) el ángulo es 0: sin 0 y cos 1, como ``el_wdir_*``. NaN si u o v no es
    finito."""
    u, v = np.asarray(u, dtype=np.float64), np.asarray(v, dtype=np.float64)
    ok = np.isfinite(u) & np.isfinite(v)
    with np.errstate(invalid="ignore"):
        ang = np.arctan2(u, v)
        return np.where(ok, np.sin(ang), np.nan), np.where(ok, np.cos(ang), np.nan)


def _nan_canonico(x: np.ndarray) -> np.ndarray:
    """AMB-3: float32 con un solo patrón de bits de NaN."""
    x = np.asarray(x, dtype=np.float32)
    return np.where(np.isnan(x), _NAN32, x).astype(np.float32)


# ---------------------------------------------------------------------------
# decision.json: el ganador ambiental y sus hiperparámetros (AMB-7, AMB-8)
# ---------------------------------------------------------------------------
def leer_decision(decision, *, decision_sha256: str | None = None) -> tuple[dict, str]:
    """(contenido, sha256) de ``decision.json`` (AMB-8): de los bytes del archivo (y su sha256 es la de esos bytes), o
    del diccionario con la sha256 del archivo en ``decision_sha256``."""
    if isinstance(decision, (bytes, bytearray, memoryview)):
        datos = bytes(decision)
        sha = _sha256(datos)
        if decision_sha256 is not None and _hex64(decision_sha256, "decision_sha256") != sha:
            raise ErrorAmbiental("decision_sha256 no es la de los bytes de decision.json")
        try:
            contenido = json.loads(datos.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise ErrorAmbiental("decision.json no es un JSON en UTF-8") from error
    elif isinstance(decision, Mapping):
        if decision_sha256 is None:
            raise ErrorAmbiental("con el contenido de decision.json va la sha256 del archivo (decision_sha256; AMB-8)")
        contenido, sha = dict(decision), _hex64(decision_sha256, "decision_sha256")
    else:
        raise ErrorAmbiental(f"decision: los bytes de decision.json o su contenido, no {type(decision).__name__}")
    if not isinstance(contenido, Mapping) or contenido.get("esquema") != tipos.VERSION_DECISION:
        raise ErrorAmbiental(f"decision.json sin el esquema {tipos.VERSION_DECISION!r}")
    if not isinstance(contenido.get("decisiones"), list):
        raise ErrorAmbiental("decision.json sin la lista «decisiones»")
    return dict(contenido), sha


def _hiper_de(x, donde: str) -> Hiper:
    """Un ``tipos.Hiper`` desde sí mismo o desde ``{"L_km", "lam", "kappa"}`` (la forma de ``decision._a_json``)."""
    if isinstance(x, Hiper):
        valores = (x.L_km, x.lam, x.kappa)
    elif isinstance(x, Mapping) and set(x) == set(CLAVES_HIPER):
        valores = tuple(x[k] for k in CLAVES_HIPER)
    else:
        raise ErrorAmbiental(f"{donde}: los hiperparámetros del núcleo son {{L_km, lam, kappa}}, no {x!r}")
    if any(isinstance(v, (bool, np.bool_)) or not isinstance(v, (int, float, np.integer, np.floating)) for v in valores):
        raise ErrorAmbiental(f"{donde}: hiperparámetros no numéricos {x!r}")
    L, lam, kappa = (float(v) for v in valores)
    if not (math.isfinite(L) and L > 0 and math.isfinite(lam) and lam >= 0 and math.isfinite(kappa) and kappa > 0):
        raise ErrorAmbiental(f"{donde}: hiperparámetros inválidos {x!r}")
    return Hiper(L, lam, kappa)


def _theta(cand: Candidato, x, donde: str):
    """θ de una variable con la forma del candidato (AMB-7): Hiper en A y B, (Hiper de A, Hiper de Φ′) en AB, α en C."""
    if cand is Candidato.C:
        if isinstance(x, (bool, np.bool_)) or not isinstance(x, (int, float, np.integer, np.floating)) \
                or not math.isfinite(float(x)) or float(x) <= 0:
            raise ErrorAmbiental(f"{donde}: el hiperparámetro de C es α (finito y > 0), no {x!r}")
        return float(x)
    if cand is Candidato.AB:
        if not isinstance(x, (list, tuple)) or len(x) != 2:
            raise ErrorAmbiental(f"{donde}: los hiperparámetros de AB son [θ de A, θ de Φ′]")
        return (_hiper_de(x[0], f"{donde}[A]"), _hiper_de(x[1], f"{donde}[Φ′]"))
    if cand in (Candidato.A, Candidato.B):
        return _hiper_de(x, donde)
    raise ErrorAmbiental(f"{donde}: {cand.value} no es candidato de lo ambiental (§6.1)")


def _hiper_json(h: Hiper) -> dict:
    return {"L_km": float(h.L_km), "lam": float(h.lam), "kappa": float(h.kappa)}


def _theta_json(theta) -> Any:
    if isinstance(theta, Hiper):
        return _hiper_json(theta)
    if isinstance(theta, tuple):
        return [_hiper_json(t) for t in theta]
    return float(theta)


def etiqueta_hiper(h: Hiper) -> str:
    """La etiqueta de un juego de hiperparámetros del núcleo en el operador («L50.0_lam150.0_kappa0.2»)."""
    h = _hiper_de(h, "etiqueta_hiper")
    return f"L{h.L_km!r}_lam{h.lam!r}_kappa{h.kappa!r}"


def _etiquetas(cand: Candidato, theta) -> tuple[str, ...]:
    if cand in (Candidato.A, Candidato.B):
        return (etiqueta_hiper(theta),)
    if cand is Candidato.AB:
        return tuple(etiqueta_hiper(t) for t in theta)
    return ()


def ganador_ambiental(decision: Mapping, *, restringido=None) -> tuple[dict[str, str], dict[str, Any]]:
    """({grupo: candidato}, {variable: θ}) del uso ambiental de ``decision.json`` (AMB-7). ``restringido``: el
    {grupo: candidato} de la rama 3 (``decision_m6.json``, «ganador_restringido»), o None."""
    if not isinstance(decision, Mapping) or not isinstance(decision.get("decisiones"), list):
        raise ErrorAmbiental("decision: el contenido de decision.json (leer_decision)")
    por_grupo: dict[Grupo, Mapping] = {}
    for d in decision["decisiones"]:
        if not isinstance(d, Mapping):
            raise ErrorAmbiental("decision.json: cada decisión es un objeto")
        if d.get("uso") != USO.value:
            continue
        try:
            g = Grupo(d.get("grupo"))
        except ValueError:
            raise ErrorAmbiental(f"decision.json: grupo desconocido {d.get('grupo')!r}") from None
        if g in por_grupo:
            raise ErrorAmbiental(f"decision.json: ambiental/{g.value} repetido")
        por_grupo[g] = d
    if set(por_grupo) != set(GRUPOS):
        raise ErrorAmbiental(f"decision.json: lo ambiental decide {[g.value for g in GRUPOS]}; trae "
                             f"{sorted(g.value for g in por_grupo)}")
    if restringido is not None:
        if not isinstance(restringido, Mapping):
            raise ErrorAmbiental("restringido: {grupo: candidato} de decision_m6.json")
        claves = {}
        for g, c in restringido.items():
            try:
                claves[Grupo(g)] = Candidato(c)
            except ValueError:
                raise ErrorAmbiental(f"restringido: {g!r} → {c!r} no es un grupo y un candidato") from None
        if set(claves) != set(GRUPOS):
            raise ErrorAmbiental("restringido: trae exactamente los tres grupos ambientales (Anexo B, rama 3)")
        restringido = claves
    ganador, hiper = {}, {}
    for g in GRUPOS:
        d = por_grupo[g]
        try:
            cand = Candidato(d.get("ganador"))
        except ValueError:
            raise ErrorAmbiental(f"decision.json: ganador desconocido en ambiental/{g.value}") from None
        if restringido is not None:
            nuevo = restringido[g]
            if cand in CAMBIA_EN_RAMA_3 and nuevo not in RESTRINGIDOS:
                raise ErrorAmbiental(f"rama 3: ambiental/{g.value} ganaba {cand.value}; el restringido es A o C")
            if cand not in CAMBIA_EN_RAMA_3 and nuevo is not cand:
                raise ErrorAmbiental(f"rama 3: ambiental/{g.value} ganaba {cand.value} y queda igual («sólo los que "
                                     "tenían B o AB»)")
            cand = nuevo
        if cand not in CANDIDATOS:
            raise ErrorAmbiental(f"ambiental/{g.value}: {cand.value} no es candidato de lo ambiental (§6.1)")
        hip = d.get("hiperparametros")
        if not isinstance(hip, Mapping) or not isinstance(hip.get(cand.value), Mapping):
            raise ErrorAmbiental(f"decision.json no trae los hiperparámetros de {cand.value} en ambiental/{g.value} "
                                 "(AMB-7)")
        por_variable = hip[cand.value]
        variables = producto.VARIABLES_DE_GRUPO[g]
        if set(por_variable) != set(variables):
            raise ErrorAmbiental(f"ambiental/{g.value}: los hiperparámetros van para {list(variables)}, enteros")
        for v in variables:
            hiper[v] = _theta(cand, por_variable[v], f"ambiental/{g.value}/{cand.value}/{v}")
        ganador[g.value] = cand.value
    if hiper[Variable.U.value] != hiper[Variable.V.value]:
        raise ErrorAmbiental("u y v comparten sus hiperparámetros (MC-43)")
    return ganador, {v: hiper[v] for v in VARIABLES}


# ---------------------------------------------------------------------------
# El operador de la grilla (AMB-6)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, eq=False)
class NucleoGrilla:
    """La lista fija de vecinos de un juego de hiperparámetros, celda × estación en CSR con los vecinos en su orden
    (AMB-6): la fila i son ``indices[indptr[i]:indptr[i + 1]]`` (estaciones de entrenamiento) y su ``d_ef`` (km)."""
    hiper: Hiper
    indptr: np.ndarray            # n + 1, int64
    indices: np.ndarray           # nnz, int32
    d_ef: np.ndarray              # nnz, float64

    def __post_init__(self) -> None:
        _solo_lectura(self, (("indptr", np.int64), ("indices", np.int32), ("d_ef", np.float64)), "núcleo")


def _solo_lectura(obj, campos, donde: str) -> None:
    """AMB-6 (H9): cada arreglo es un ``numpy.ndarray`` de su tipo y queda de sólo lectura."""
    for nombre, tipo in campos:
        a = getattr(obj, nombre)
        if not isinstance(a, np.ndarray) or a.dtype != np.dtype(tipo):
            raise ErrorAmbiental(f"{donde}: {nombre} es un arreglo de {np.dtype(tipo)}")
        a.setflags(write=False)


_TIPOS_OPERADOR = (("celdas", np.int64), ("lat", np.float64), ("lon", np.float64), ("z", np.float64),
                   ("pix", np.int32), ("w", np.float64), ("dz", np.float64), ("respaldo", np.bool_),
                   ("grupo_est", np.int32))


@dataclass(frozen=True, eq=False)
class OperadorGrilla:
    """El operador de §7.1 en las celdas (AMB-6), con su ``sha256`` (el de ``a_bytes()``). Inmutable: sus arreglos son
    de sólo lectura (H9)."""
    celdas: np.ndarray            # n, int64, estrictamente creciente
    lat: np.ndarray               # n, float64 (centro de la celda)
    lon: np.ndarray
    z: np.ndarray                 # n, float64: z_media (uso ambiental, §3)
    pix: np.ndarray               # n × 4, int32 (−1 sin vecino)
    w: np.ndarray                 # n × 4, float64
    dz: np.ndarray                # n × 4, float64 (z de la celda − z_E5L del píxel, en m)
    respaldo: np.ndarray          # n, bool
    codigos: tuple[str, ...]      # entrenamiento de producción, ordenado
    grupos: tuple[str, ...]
    grupo_est: np.ndarray         # int32: el grupo de cada estación de entrenamiento
    n_vecinos: int                # las casillas de la lista fija (NUC_VECINOS)
    nucleos: Mapping[str, NucleoGrilla]
    ganador: Mapping[str, str]    # grupo → candidato
    hiper: Mapping[str, Any]      # variable → θ
    nucleo_de: Mapping[str, tuple[str, ...]]      # variable → etiquetas de sus núcleos
    estaciones_sha256: str        # la geometría del entrenamiento (AMB-5)
    decision_sha256: str
    umbrales: Mapping[str, Any]   # {id de UMBRALES_OPERADOR: valor} (AMB-6, H9)
    restringido: bool = False
    ramas_m6_sha256: str | None = None            # rama 3: la huella de m6/ramas_m6.json (AMB-7, H3)
    umbrales_sha256: str = field(init=False)
    sha256: str = field(init=False)

    def __post_init__(self) -> None:
        _solo_lectura(self, _TIPOS_OPERADOR, "operador")
        if not isinstance(self.umbrales, Mapping) or tuple(self.umbrales) != UMBRALES_OPERADOR:
            raise ErrorAmbiental(f"operador: los umbrales son exactamente {list(UMBRALES_OPERADOR)}, en orden")
        if self.n_vecinos != self.umbrales["NUC_VECINOS"]:
            raise ErrorAmbiental("operador: n_vecinos no es NUC_VECINOS de sus umbrales")
        _hex64(self.decision_sha256, "operador: decision_sha256")
        _hex64(self.estaciones_sha256, "operador: estaciones_sha256")
        if self.restringido:
            _hex64(self.ramas_m6_sha256, "operador restringido: ramas_m6_sha256")
        elif self.ramas_m6_sha256 is not None:
            raise ErrorAmbiental("operador: ramas_m6_sha256 sólo va con el ganador restringido (rama 3)")
        object.__setattr__(self, "umbrales", MappingProxyType(
            {k: tuple(v) if isinstance(v, (tuple, list)) else v for k, v in self.umbrales.items()}))
        object.__setattr__(self, "umbrales_sha256", _huella_umbrales(self.umbrales))
        for etq, nuc in self.nucleos.items():
            if not isinstance(nuc, NucleoGrilla) or etq != etiqueta_hiper(nuc.hiper):
                raise ErrorAmbiental(f"operador: el núcleo {etq!r} no es el de sus hiperparámetros")
        if self.celdas.ndim != 1:
            raise ErrorAmbiental("operador: celdas en int64, estrictamente crecientes")
        n = self.celdas.shape[0]
        if n > 1 and not bool(np.all(np.diff(self.celdas) > 0)):
            raise ErrorAmbiental("operador: celdas en int64, estrictamente crecientes")
        if self.grupo_est.shape != (len(self.codigos),):
            raise ErrorAmbiental("operador: grupo_est con una fila por estación de entrenamiento")
        for nombre in ("lat", "lon", "z", "respaldo"):
            if getattr(self, nombre).shape != (n,):
                raise ErrorAmbiental(f"operador: {nombre} con una fila por celda")
        for nombre in ("pix", "w", "dz"):
            if getattr(self, nombre).shape != (n, constantes.valor("FONDO_VECINOS")):
                raise ErrorAmbiental(f"operador: {nombre} es celda × vecinos del fondo")
        for etq, nuc in self.nucleos.items():
            if nuc.indptr.shape != (n + 1,) or nuc.indices.shape != nuc.d_ef.shape or nuc.indptr[-1] != nuc.indices.size:
                raise ErrorAmbiental(f"operador: el núcleo {etq} no tiene la forma CSR de las celdas")
        for v in VARIABLES:
            for etq in self.nucleo_de.get(v, ()):
                if etq not in self.nucleos:
                    raise ErrorAmbiental(f"operador: {v} usa el núcleo {etq}, que no está")
        h = hashlib.sha256()
        for parte in _partes(self):
            h.update(parte)
        object.__setattr__(self, "sha256", h.hexdigest())

    # -- consultas --------------------------------------------------------------------------------------------------
    def candidato_de(self, variable: str) -> Candidato:
        return Candidato(self.ganador[GRUPO_DE[variable].value])

    def indices(self, celdas) -> np.ndarray:
        """La posición de cada celda pedida en el operador; ``ErrorAmbiental`` si alguna no está."""
        c = _enteros(celdas, "celdas")
        n = self.celdas.size
        pos = np.searchsorted(self.celdas, c)
        ok = (pos < n) & (self.celdas[np.minimum(pos, max(n - 1, 0))] == c) if n else np.zeros(c.shape, bool)
        if not bool(np.all(ok)):
            raise ErrorAmbiental(f"{int((~ok).sum())} celdas no están en el operador de la grilla")
        return pos.astype(np.int64)

    def puntos_fondo(self, idx) -> tipos.OperadorPuntos:
        """El operador del fondo de esas celdas (``tipos.OperadorPuntos``)."""
        idx = np.asarray(idx, dtype=np.int64)
        return tipos.OperadorPuntos(ids=self.celdas[idx], z=self.z[idx], pix=self.pix[idx], w=self.w[idx],
                                    dz=self.dz[idx], respaldo=self.respaldo[idx])

    def vecinos(self, etiqueta: str, idx) -> "candidatos.VecinosEntrenamiento":
        """La lista fija de vecinos de esas celdas con el núcleo ``etiqueta``, como la da ``candidatos.vecinos``."""
        if etiqueta not in self.nucleos:
            raise ErrorAmbiental(f"el operador no tiene el núcleo {etiqueta}")
        nuc = self.nucleos[etiqueta]
        idx = np.asarray(idx, dtype=np.int64)
        m, k = idx.size, self.n_vecinos
        est = np.full((m, k), candidatos.SIN_VECINO, dtype=np.int32)
        d_ef = np.full((m, k), np.nan)
        inicio = nuc.indptr[idx]
        largo = nuc.indptr[idx + 1] - inicio
        total = int(largo.sum())
        if total:
            fila = np.repeat(np.arange(m), largo)
            columna = np.arange(total) - np.repeat(np.cumsum(largo) - largo, largo)
            fuente = np.repeat(inicio, largo) + columna
            est[fila, columna] = nuc.indices[fuente]
            d_ef[fila, columna] = nuc.d_ef[fuente]
        if self.codigos:
            grupo_de = np.where(est >= 0, self.grupo_est[np.maximum(est, 0)], candidatos.SIN_VECINO)
        else:
            grupo_de = np.full(est.shape, candidatos.SIN_VECINO)
        return candidatos.VecinosEntrenamiento(puntos=self.celdas[idx], est=est, d_ef=d_ef,
                                               grupo_de=grupo_de.astype(np.int32), hiper=nuc.hiper,
                                               codigos=self.codigos, grupos=self.grupos, grupo_est=self.grupo_est)

    def matriz_fondo(self):
        """(W, ΔZ): las matrices dispersas celda × píxel (columna = ``pixel_id``) de los pesos bilineales y de Δz (m)."""
        from scipy import sparse

        ok = self.pix >= 0
        filas = np.repeat(np.arange(self.celdas.size), self.pix.shape[1]).reshape(self.pix.shape)[ok]
        cols = self.pix[ok].astype(np.int64)
        forma = (self.celdas.size, int(cols.max()) + 1 if cols.size else 0)
        return (sparse.csr_matrix((self.w[ok], (filas, cols)), shape=forma),
                sparse.csr_matrix((self.dz[ok], (filas, cols)), shape=forma))

    def matriz_nucleo(self, etiqueta: str):
        """Los pesos del núcleo k = exp(−½ (d_ef/L)²) celda × estación (CSR), la cuenta de ``candidatos`` (CAN-3)."""
        from scipy import sparse

        nuc = self.nucleos[etiqueta]
        k = np.exp(-float(constantes.valor("NUCLEO_MEDIO")) * (nuc.d_ef / float(nuc.hiper.L_km)) ** 2)
        K = sparse.csr_matrix((k, nuc.indices.astype(np.int64), nuc.indptr), shape=(self.celdas.size, len(self.codigos)))
        K.sort_indices()
        return K

    # -- bytes ------------------------------------------------------------------------------------------------------
    def cabecera(self) -> dict:
        return _cabecera(self, _arreglos(self))

    def a_bytes(self) -> bytes:
        """Los bytes del operador (AMB-6), que escribe ``salidas`` (``ambiental/``, clase insumo)."""
        return b"".join(_partes(self))

    @property
    def tamano_bytes(self) -> int:
        """El tamaño de ``a_bytes()`` sin armarlos (MC-15)."""
        arreglos = _arreglos(self)
        return len(FIRMA_OPERADOR) + _LARGO.size + len(_json_canonico(_cabecera(self, arreglos))) + \
            sum(a.nbytes for _, a in arreglos)


def _nombres_arreglos(etiquetas) -> list[tuple[str, str]]:
    """AMB-6: (nombre, tipo) de cada arreglo de los bytes, en su orden (los núcleos por etiqueta ordenada)."""
    salida = list(_ARREGLOS_BASE)
    for etq in sorted(etiquetas):
        salida += [(f"nucleo/{etq}/{parte}", tipo) for parte, tipo in _ARREGLOS_NUCLEO]
    return salida


def _arreglos(op: OperadorGrilla) -> list[tuple[str, np.ndarray]]:
    salida = []
    for nombre, tipo in _nombres_arreglos(op.nucleos):
        if nombre.startswith("nucleo/"):
            _, etq, parte = nombre.split("/")
            a = getattr(op.nucleos[etq], parte)
        else:
            a = getattr(op, nombre)
        salida.append((nombre, np.ascontiguousarray(np.asarray(a).astype(np.dtype(tipo), copy=False))))
    return salida


def _cabecera(op: OperadorGrilla, arreglos) -> dict:
    lista, inicio = [], 0
    for nombre, a in arreglos:
        lista.append({"nombre": nombre, "tipo": a.dtype.str, "forma": list(a.shape), "inicio": inicio,
                      "bytes": int(a.nbytes)})
        inicio += int(a.nbytes)
    return {"esquema": ESQUEMA_OPERADOR, "uso": USO.value, "ganador": dict(op.ganador),
            "hiperparametros": {v: _theta_json(op.hiper[v]) for v in VARIABLES},
            "nucleo_de": {v: list(op.nucleo_de.get(v, ())) for v in VARIABLES},
            "nucleos": {etq: _hiper_json(op.nucleos[etq].hiper) for etq in sorted(op.nucleos)},
            "n_vecinos": int(op.n_vecinos), "n_celdas": int(op.celdas.size), "codigos": list(op.codigos),
            "grupos": list(op.grupos), "estaciones_sha256": op.estaciones_sha256, "decision_sha256": op.decision_sha256,
            "umbrales": {k: list(v) if isinstance(v, tuple) else v for k, v in op.umbrales.items()},
            "umbrales_sha256": op.umbrales_sha256, "restringido": bool(op.restringido),
            "ramas_m6_sha256": op.ramas_m6_sha256, "arreglos": lista}


def _partes(op: OperadorGrilla) -> Iterator[bytes]:
    arreglos = _arreglos(op)
    cabecera = _json_canonico(_cabecera(op, arreglos))
    yield FIRMA_OPERADOR
    yield _LARGO.pack(len(cabecera))
    yield cabecera
    for _, a in arreglos:
        yield a.tobytes()


def leer_operador(datos, *, sha256: str | None = None) -> OperadorGrilla:
    """El operador desde sus bytes (``OperadorGrilla.a_bytes``): se rehace y su sha256 debe ser la de los bytes y, si
    se da, la esperada (la del registro de M5; unos bytes alterados son coherentes consigo mismos). Toda falla de forma
    es ``ErrorAmbiental`` (H9); los arreglos se copian una sola vez y quedan de sólo lectura (H6, AMB-15)."""
    if not isinstance(datos, (bytes, bytearray, memoryview)):
        raise ErrorAmbiental("leer_operador: los bytes del operador")
    datos = bytes(datos)
    if sha256 is not None and _sha256(datos) != _hex64(sha256, "sha256 del operador"):
        raise ErrorAmbiental("los bytes del operador no tienen la sha256 esperada")
    if not datos.startswith(FIRMA_OPERADOR) or len(datos) < len(FIRMA_OPERADOR) + _LARGO.size:
        raise ErrorAmbiental("no son los bytes de un operador de la grilla")
    n = _LARGO.unpack_from(datos, len(FIRMA_OPERADOR))[0]
    inicio = len(FIRMA_OPERADOR) + _LARGO.size
    if inicio + n > len(datos):
        raise ErrorAmbiental("la cabecera del operador está truncada")
    cab = _json_estricto(datos[inicio:inicio + n], "la cabecera del operador")
    if not isinstance(cab, Mapping) or cab.get("esquema") != ESQUEMA_OPERADOR or cab.get("uso") != USO.value:
        raise ErrorAmbiental(f"el operador no es del esquema {ESQUEMA_OPERADOR!r} ni del uso ambiental")
    if set(cab) != set(_CLAVES_CABECERA):
        raise ErrorAmbiental(f"la cabecera del operador trae {sorted(cab)}; son {sorted(_CLAVES_CABECERA)} (AMB-6)")
    try:
        return _operador_de_cabecera(cab, datos, inicio + n)
    except (KeyError, TypeError, ValueError, AttributeError) as error:       # H9: nunca un KeyError suelto
        raise ErrorAmbiental(f"la cabecera del operador está mal formada ({type(error).__name__}: {error})") from error


def _operador_de_cabecera(cab: Mapping, datos: bytes, base: int) -> OperadorGrilla:
    """``leer_operador``: los arreglos de la lista de la cabecera (exactamente los de ``a_bytes``, seguidos y con sus
    tipos), con una sola copia (H6), y el operador rehecho con su sha256."""
    if not isinstance(cab["nucleos"], Mapping) or not isinstance(cab["arreglos"], list):
        raise ErrorAmbiental("la cabecera del operador: «nucleos» es un objeto y «arreglos» una lista")
    esperados = _nombres_arreglos(cab["nucleos"])
    if [e.get("nombre") if isinstance(e, Mapping) else None for e in cab["arreglos"]] != [m for m, _ in esperados]:
        faltan = sorted({m for m, _ in esperados} - {e.get("nombre") for e in cab["arreglos"] if isinstance(e, Mapping)})
        raise ErrorAmbiental(f"los arreglos del operador no son los de su cabecera (faltan {faltan[:_CITADOS]}; H9)")
    arreglos, desde = {}, 0
    for e, (nombre, tipo_esperado) in zip(cab["arreglos"], esperados):
        if set(e) != set(_CLAVES_ARREGLO) or e["tipo"] != np.dtype(tipo_esperado).str:
            raise ErrorAmbiental(f"el arreglo {nombre} del operador no tiene su forma de cabecera ni su tipo")
        tipo = np.dtype(e["tipo"])
        forma = tuple(_entero(x, f"forma de {nombre}", minimo=0) for x in e["forma"])
        cuenta = int(np.prod(forma)) if forma else 1
        if _entero(e["inicio"], f"inicio de {nombre}") != desde or cuenta * tipo.itemsize != e["bytes"] \
                or base + desde + e["bytes"] > len(datos):
            raise ErrorAmbiental(f"el arreglo {nombre} del operador está truncado o fuera de lugar")
        a = np.frombuffer(datos, dtype=tipo, count=cuenta, offset=base + desde).reshape(forma)
        arreglos[nombre] = a.astype(tipo.newbyteorder("="), copy=True)       # la única copia (H6)
        desde += int(e["bytes"])
    if base + desde != len(datos):
        raise ErrorAmbiental("los bytes del operador no calzan con su cabecera")

    def arr(nombre: str, tipo) -> np.ndarray:
        return arreglos[nombre].astype(tipo, copy=False)                     # sin segunda copia (H6)
    ganador = {g: Candidato(c).value for g, c in cab["ganador"].items()}
    hiper = {v: _theta(Candidato(ganador[GRUPO_DE[v].value]), cab["hiperparametros"][v], f"operador/{v}")
             for v in VARIABLES}
    nucleos = {etq: NucleoGrilla(hiper=_hiper_de(h, f"operador/{etq}"), indptr=arr(f"nucleo/{etq}/indptr", np.int64),
                                 indices=arr(f"nucleo/{etq}/indices", np.int32),
                                 d_ef=arr(f"nucleo/{etq}/d_ef", np.float64))
               for etq, h in cab["nucleos"].items()}
    umbrales = cab["umbrales"]
    if not isinstance(umbrales, Mapping) or set(umbrales) != set(UMBRALES_OPERADOR):
        raise ErrorAmbiental(f"la cabecera del operador: los umbrales son {list(UMBRALES_OPERADOR)} (AMB-6)")
    umbrales = {k: umbrales[k] for k in UMBRALES_OPERADOR}               # el JSON canónico los ordena
    op = OperadorGrilla(
        celdas=arr("celdas", np.int64), lat=arr("lat", np.float64), lon=arr("lon", np.float64), z=arr("z", np.float64),
        pix=arr("pix", np.int32), w=arr("w", np.float64), dz=arr("dz", np.float64), respaldo=arr("respaldo", bool),
        codigos=tuple(cab["codigos"]), grupos=tuple(cab["grupos"]), grupo_est=arr("grupo_est", np.int32),
        n_vecinos=_entero(cab["n_vecinos"], "n_vecinos"), nucleos=MappingProxyType(nucleos),
        ganador=MappingProxyType(ganador), hiper=MappingProxyType(hiper),
        nucleo_de=MappingProxyType({v: tuple(e) for v, e in cab["nucleo_de"].items()}),
        estaciones_sha256=cab["estaciones_sha256"], decision_sha256=cab["decision_sha256"],
        umbrales={k: tuple(v) if isinstance(v, list) else v for k, v in umbrales.items()},
        restringido=cab["restringido"] is True, ramas_m6_sha256=cab["ramas_m6_sha256"])
    if op.umbrales_sha256 != cab["umbrales_sha256"] or op.sha256 != _sha256(datos):
        raise ErrorAmbiental("el operador releído no reproduce la sha256 de sus bytes (ni la de sus umbrales)")
    return op


def _entrenamiento(estaciones) -> dict[str, tipos.InfoEstacion]:
    """AMB-5 (PRO-4): todas las estaciones no excluidas, en orden de código."""
    if not isinstance(estaciones, Mapping) or not estaciones:
        raise ErrorAmbiental("estaciones: {código: tipos.InfoEstacion}, no vacío")
    for c, info in estaciones.items():
        if not isinstance(info, tipos.InfoEstacion) or info.codigo != c:
            raise ErrorAmbiental(f"estaciones[{c!r}] debe ser la tipos.InfoEstacion de ese código")
    codigos = sorted(c for c, info in estaciones.items() if not info.excluida)
    if not codigos:
        raise ErrorAmbiental("sin estaciones de entrenamiento (todas excluidas)")
    return {c: estaciones[c] for c in codigos}


def _huella_estaciones(entrenamiento: Mapping[str, tipos.InfoEstacion]) -> str:
    filas = [[c, float(i.lat), float(i.lon), float(i.z_s), i.grupo] for c, i in entrenamiento.items()]
    try:
        return _sha256(_json_canonico(filas))
    except ValueError as error:
        raise ErrorAmbiental("una estación de entrenamiento sin lat, lon o z_s finitos") from error


def _celdas_y_z(celdas, z_celdas) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(ids, lat, lon, z_media) de las celdas, ordenadas por id; z_media cotejada por ``celda`` (no por posición)."""
    if not isinstance(celdas, pd.DataFrame) or not {"celda", "lat", "lon"} <= set(celdas.columns):
        raise ErrorAmbiental("celdas: la tabla de celdas.parquet con celda, lat y lon")
    if not isinstance(z_celdas, pd.DataFrame) or not {"celda", "z_media"} <= set(z_celdas.columns):
        raise ErrorAmbiental("z_celdas: la tabla de estáticos de las celdas con celda y z_media (uso ambiental, §3)")
    ids = _enteros(celdas["celda"].to_numpy(), "celdas.celda")
    if np.unique(ids).size != ids.size:
        raise ErrorAmbiental("celdas: ids repetidos")
    orden = np.argsort(ids, kind="stable")
    ids = ids[orden]
    lat = celdas["lat"].to_numpy(np.float64)[orden]
    lon = celdas["lon"].to_numpy(np.float64)[orden]
    zc = _enteros(z_celdas["celda"].to_numpy(), "z_celdas.celda")
    if np.unique(zc).size != zc.size:
        raise ErrorAmbiental("z_celdas: celdas repetidas")
    orden_z = np.argsort(zc, kind="stable")
    zs = zc[orden_z]
    pos = np.searchsorted(zs, ids)
    ok = (pos < zs.size) & (zs[np.minimum(pos, max(zs.size - 1, 0))] == ids) if zs.size else np.zeros(ids.shape, bool)
    if not bool(np.all(ok)):
        raise ErrorAmbiental(f"z_celdas: faltan {int((~ok).sum())} celdas")
    z = z_celdas["z_media"].to_numpy(np.float64)[orden_z][pos]
    return ids, lat, lon, z


def _nucleo_de_vecinos(vec) -> NucleoGrilla:
    """La lista fija de ``candidatos.vecinos`` en CSR, con los vecinos en su orden (siempre un prefijo; AMB-6)."""
    est = np.asarray(vec.est)
    ok = est >= 0
    largo = ok.sum(axis=1)
    if not np.array_equal(ok, np.arange(est.shape[1])[None, :] < largo[:, None]):
        raise ErrorAmbiental("la lista de vecinos no es un prefijo de sus casillas")
    if not (np.isfinite(vec.d_ef[ok]).all() and np.isnan(vec.d_ef[~ok]).all()):
        raise ErrorAmbiental("d_ef finito en los vecinos y NaN en las casillas vacías")
    indptr = np.concatenate([[0], np.cumsum(largo)]).astype(np.int64)
    return NucleoGrilla(hiper=vec.hiper, indptr=indptr, indices=est[ok].astype(np.int32),
                        d_ef=np.asarray(vec.d_ef, dtype=np.float64)[ok])


def operador_grilla(decision, *, celdas, estaciones, catalogo, z_celdas, validos, z_pix, umbrales,
                    decision_sha256: str | None = None, restringido=None,
                    ramas_m6_sha256: str | None = None) -> OperadorGrilla:
    """El operador de la grilla con el ganador ambiental de ``decision`` (§7.1; AMB-5 a AMB-8).

    ``celdas``: tabla con ``celda``, ``lat`` y ``lon`` (``celdas.parquet``); ``z_celdas``: tabla con ``celda`` y
    ``z_media`` (``ESQUEMA_ESTATICAS_CELDA``); ``catalogo``, ``validos`` y ``z_pix``: los de ``fondo_era5l.operador``;
    ``estaciones``: {código: InfoEstacion} (el entrenamiento de producción son las no excluidas). ``restringido``: el
    ganador de la rama 3, con ``ramas_m6_sha256``, la huella de ``m6/ramas_m6.json`` (AMB-7, H3)."""
    contenido, sha_decision = leer_decision(decision, decision_sha256=decision_sha256)
    ganador, hiper = ganador_ambiental(contenido, restringido=restringido)
    if restringido is not None:
        ramas_m6_sha256 = _hex64(ramas_m6_sha256, "ramas_m6_sha256 (rama 3: la huella de m6/ramas_m6.json)")
    elif ramas_m6_sha256 is not None:
        raise ErrorAmbiental("ramas_m6_sha256 sólo va con el ganador restringido (rama 3)")
    valores_umbrales = _umbrales_operador(umbrales)
    ids, lat, lon, z = _celdas_y_z(celdas, z_celdas)
    entrenamiento = _entrenamiento(estaciones)
    fondo = fondo_era5l.operador(lat, lon, z, catalogo, validos, z_pix, umbrales, ids=ids)
    vacio = np.empty(0, dtype=np.float64)
    base = candidatos.vecinos({"lat": vacio, "lon": vacio, "z": vacio}, entrenamiento, _HIPER_SOLO_CODIGOS, umbrales)
    puntos = {"ids": ids, "lat": lat, "lon": lon, "z": z}
    nucleo_de, juegos = {}, {}
    for v in VARIABLES:
        cand = Candidato(ganador[GRUPO_DE[v].value])
        theta = hiper[v]
        juego = (theta,) if cand in (Candidato.A, Candidato.B) else (theta if cand is Candidato.AB else ())
        nucleo_de[v] = tuple(etiqueta_hiper(t) for t in juego)
        for t in juego:
            juegos.setdefault(etiqueta_hiper(t), t)
    nucleos = {}
    for etq, t in juegos.items():
        vec = candidatos.vecinos(puntos, entrenamiento, t, umbrales)
        if vec.codigos != base.codigos or vec.grupos != base.grupos:
            raise ErrorAmbiental("los vecinos no traen el entrenamiento de producción")
        nucleos[etq] = _nucleo_de_vecinos(vec)
    return OperadorGrilla(
        celdas=ids, lat=lat, lon=lon, z=np.asarray(fondo.z, dtype=np.float64),
        pix=np.asarray(fondo.pix, dtype=np.int32), w=np.asarray(fondo.w, dtype=np.float64),
        dz=np.asarray(fondo.dz, dtype=np.float64), respaldo=np.asarray(fondo.respaldo, dtype=bool),
        codigos=tuple(base.codigos), grupos=tuple(base.grupos), grupo_est=np.asarray(base.grupo_est, dtype=np.int32),
        n_vecinos=int(base.est.shape[1]), nucleos=MappingProxyType(nucleos), ganador=MappingProxyType(ganador),
        hiper=MappingProxyType(hiper), nucleo_de=MappingProxyType(nucleo_de),
        estaciones_sha256=_huella_estaciones(entrenamiento), decision_sha256=sha_decision, umbrales=valores_umbrales,
        restringido=restringido is not None, ramas_m6_sha256=ramas_m6_sha256)


def _operador(operador) -> OperadorGrilla:
    if isinstance(operador, (bytes, bytearray, memoryview)):
        return leer_operador(operador)
    if not isinstance(operador, OperadorGrilla):
        raise ErrorAmbiental("operador: un OperadorGrilla (operador_grilla) o sus bytes")
    return operador


def _comprobar_umbrales(op: OperadorGrilla, umbrales) -> None:
    """AMB-6 (H9): los umbrales con que se evalúa son los del operador (la misma huella de ``UMBRALES_OPERADOR``)."""
    if _huella_umbrales(_umbrales_operador(umbrales)) != op.umbrales_sha256:
        raise ErrorAmbiental("los umbrales no son los del operador (Γ, VECINO_KM o NUC_*; AMB-6)")


# ---------------------------------------------------------------------------
# Las columnas de la variante en un lote (AMB-3 a AMB-5, AMB-9, AMB-10, AMB-14)
# ---------------------------------------------------------------------------
def _comprobar_datos(op: OperadorGrilla, datos) -> None:
    if not isinstance(datos, tipos.DatosCompetencia):
        raise ErrorAmbiental("datos debe ser tipos.DatosCompetencia (residuos, climatologías y filas de C)")
    entrenamiento = _entrenamiento(datos.estaciones)
    if tuple(entrenamiento) != op.codigos or _huella_estaciones(entrenamiento) != op.estaciones_sha256:
        raise ErrorAmbiental("las estaciones de datos no son el entrenamiento de producción del operador (AMB-5)")


def _mes(meses, yyyymm: int) -> "fondo_era5l.MesE5L":
    if callable(meses) and not isinstance(meses, Mapping):
        mes = meses(yyyymm)
    elif isinstance(meses, Mapping):
        mes = meses.get(yyyymm, meses.get(str(yyyymm)))
    else:
        raise ErrorAmbiental("meses: {AAAAMM: MesE5L} o una función AAAAMM → MesE5L (AMB-9)")
    if not isinstance(mes, fondo_era5l.MesE5L):
        raise ErrorAmbiental(f"falta el mes ERA5-Land {yyyymm} (AMB-9)")
    if mes.yyyymm != yyyymm:
        raise ErrorAmbiental(f"el mes ERA5-Land dado para {yyyymm} es el {mes.yyyymm}")
    return mes


def _fondo(mes, hm: np.ndarray, puntos: tipos.OperadorPuntos, umbrales) -> tuple[dict, np.ndarray]:
    """El fondo (hora × celda) en las horas ``hm`` y la amplitud de T_F en su día UTC, calculada sobre los días UTC
    enteros del mes (AMB-5, AMB-14)."""
    t = np.asarray(mes.tiempos, dtype=np.int64)
    if not bool(np.all(np.isin(hm, t))):
        raise ErrorAmbiental(f"el mes ERA5-Land {mes.yyyymm} no trae {int((~np.isin(hm, t)).sum())} de las horas "
                             "pedidas (§3: sin interpolación temporal; AMB-9)")
    dias = np.unique(np.floor_divide(hm, _HORAS_DIA))
    h_dia = (dias[:, None] * _HORAS_DIA + np.arange(_HORAS_DIA)[None, :]).ravel()
    h_dia = h_dia[np.isin(h_dia, t)]
    pos = np.searchsorted(t, h_dia)
    sub = fondo_era5l.MesE5L(tiempos=t[pos].astype(np.int32), pixel_id=mes.pixel_id,
                             datos={k: np.asarray(x)[pos] for k, x in mes.datos.items()}, sha256=mes.sha256)
    F = fondo_era5l.campos_fondo(sub, puntos, umbrales)
    amp = fondo_era5l.amplitud_dia_utc(F["T_F"], h_dia)
    filas = np.searchsorted(h_dia, hm)
    return {c: F[c][filas] for c in fondo_era5l.CAMPOS_F}, amp[filas]


def _estaticos_c(estaticos, ids: np.ndarray) -> pd.DataFrame:
    """Los estáticos de C de las celdas (``ESQUEMA_ESTATICAS_CELDA_C``), una fila por celda en su orden (PRO-8)."""
    if not isinstance(estaticos, pd.DataFrame):
        raise ErrorAmbiental("C gana un grupo: hacen falta los estáticos de las celdas (ESQUEMA_ESTATICAS_CELDA_C)")
    try:
        tipos.validar_esquema(estaticos, tipos.ESQUEMA_ESTATICAS_CELDA_C, nombre="estáticos de C")
    except (ValueError, TypeError) as error:
        raise ErrorAmbiental(str(error)) from error
    c = estaticos["celda"].to_numpy(np.int64)
    if np.unique(c).size != c.size:
        raise ErrorAmbiental("estáticos de C: celdas repetidas")
    orden = np.argsort(c, kind="stable")
    pos = np.searchsorted(c[orden], ids)
    ok = (pos < c.size) & (c[orden][np.minimum(pos, max(c.size - 1, 0))] == ids) if c.size else np.zeros(ids.shape, bool)
    if not bool(np.all(ok)):
        raise ErrorAmbiental(f"estáticos de C: faltan {int((~ok).sum())} celdas")
    return estaticos.iloc[orden[pos]].reset_index(drop=True)


class _Correcciones:
    """R de cada variable del ganador en un mes de un lote (hora × celda, float64), una vez por red (AMB-5, AMB-10)."""

    def __init__(self, op: OperadorGrilla, idx: np.ndarray, hm: np.ndarray, F: dict, amp: np.ndarray, datos,
                 umbrales, est_c, redes, anio: int):
        self.op, self.idx, self.hm, self.F, self.amp = op, idx, hm, F, amp
        self.datos, self.umbrales, self.est_c, self.redes, self.anio = datos, umbrales, est_c, redes, anio
        self._memo: dict = {}
        self._vecinos: dict = {}
        self._q: dict = {}

    def red(self, v: str, variable_red: str):
        cand = self.op.candidato_de(v)
        if cand not in CON_RED or self.redes is None:
            return None
        red = self.redes[variable_red](self.anio)
        if red is None:
            return None
        if isinstance(red, str) or not all(isinstance(c, str) for c in red):
            raise ErrorAmbiental(f"la red de {variable_red} en {self.anio} es un conjunto de códigos")
        return frozenset(red)

    def r(self, v: str, variable_red: str) -> np.ndarray:
        clave = (v, self.red(v, variable_red))
        if clave not in self._memo:
            self._memo[clave] = self._calcular(v, clave[1])
        return self._memo[clave]

    def _vec(self, theta: Hiper):
        etq = etiqueta_hiper(theta)
        if etq not in self._vecinos:
            self._vecinos[etq] = self.op.vecinos(etq, self.idx)
        return self._vecinos[etq]

    def _clima(self, v: str) -> pd.DataFrame:
        clima = self.datos.climatologias
        return clima[clima["variable"] == v]

    def _matriz_q(self, cand: Candidato, v: str) -> np.ndarray:
        if (cand, v) not in self._q:
            self._q[(cand, v)] = candidatos.matriz_q(self.datos, self.op.codigos, cand, v, self.hm, self.umbrales)
        return self._q[(cand, v)]

    def _calcular(self, v: str, red) -> np.ndarray:
        cand, theta, h = self.op.candidato_de(v), self.op.hiper[v], self.hm
        if cand is Candidato.A:
            return candidatos.correccion_a(self._vec(theta), self._clima(v), h)
        if cand in (Candidato.B, Candidato.AB):
            q = self._matriz_q(cand, v)
            disponible = np.isfinite(q)
            if red is not None:
                disponible = disponible & np.array([c in red for c in self.op.codigos], dtype=bool)[None, :]
            if cand is Candidato.B:
                return candidatos.correccion_b(self._vec(theta), q, disponible)
            return candidatos.correccion_ab(self._vec(theta[0]), self._vec(theta[1]), self._clima(v), q, disponible, h)
        return self._c(v, theta)

    def _c(self, v: str, alfa: float) -> np.ndarray:
        try:
            filas = self.datos.filas_c[Candidato.C.value][v]
        except (KeyError, TypeError):
            raise ErrorAmbiental(f"datos.filas_c no trae C/{v}") from None
        modelo = candidatos.ajustar_c(filas, self.op.codigos, alfa)
        F = self.F
        with np.errstate(invalid="ignore"):
            if bool(np.any(F["Td_F"] > F["T_F"])):
                raise ErrorAmbiental("el fondo de C trae Td_F > T_F: falta el recorte de §4.1")
        estado = producto.estado_c_puntos(F["T_F"], F["Td_F"], F["u_F"], F["v_F"], self.amp)
        n_h, n = h_n = (self.hm.size, self.idx.size)
        salida = np.full(h_n, np.nan)
        for i0 in range(0, n, producto.LOTE_PUNTOS_C):
            sl = slice(i0, min(n, i0 + producto.LOTE_PUNTOS_C))
            indices = np.arange(sl.start, sl.stop)
            filas_c = self.est_c.iloc[np.repeat(indices, n_h)]
            horas = np.tile(self.hm, indices.size)
            estado_filas = {e: np.ascontiguousarray(estado[e][:, sl].T).ravel() for e in candidatos.ESTADO_C}
            salida[:, sl] = candidatos.predecir_c(modelo, filas_c, horas, estado_filas).reshape(indices.size, n_h).T
        return salida


def _de_campos(prefijo: str, p_T: dict, p_Td: dict) -> dict[str, np.ndarray]:
    """Las 9 columnas de MC-28 (AMB-3) desde los campos del producto (o del fondo, con R = 0)."""
    s, c = direccion_sin_cos(p_T["u"], p_T["v"])
    return {f"{prefijo}t2m": p_T["T"] + _KELVIN, f"{prefijo}d2m": p_Td["Td"] + _KELVIN,
            f"{prefijo}rh": p_Td[tipos.Derivada.HR.value], f"{prefijo}sp": p_T["p"] * _PA_POR_HPA,
            f"{prefijo}u10": p_T["u"], f"{prefijo}v10": p_T["v"], f"{prefijo}wind": p_T[tipos.Derivada.RAPIDEZ.value],
            f"{prefijo}wdir_sin": s, f"{prefijo}wdir_cos": c}


def _columnas_mes(variante: Variante, F: dict, corr: _Correcciones) -> dict[str, np.ndarray]:
    T, Td, U, V, P = (Variable.T.value, Variable.TD.value, Variable.U.value, Variable.V.value, Variable.P.value)
    r_T = corr.r(T, RED_DE[T])
    r_Td = corr.r(Td, RED_DE[Td])
    r_u, r_v, r_p = corr.r(U, RED_DE[U]), corr.r(V, RED_DE[V]), corr.r(P, RED_DE[P])
    if variante is Variante.D:
        cero = np.zeros_like(F["T_F"])
        fondo = producto.campos(F, {c: cero for c in fondo_era5l.CLAVES_R})
        salida = _de_campos("fe_", fondo, fondo)
        salida.update({"dmc_R_T": r_T, "dmc_R_Td": r_Td, "dmc_R_u": r_u, "dmc_R_v": r_v, "dmc_R_p": r_p})
        return salida
    R = {"R_T": r_T, "R_Td": r_Td, "R_u": r_u, "R_v": r_v, "R_p": r_p}
    p_T = producto.campos(F, R)
    r_T_de_Td = corr.r(T, RED_DE[Td])                  # AMB-10 (P-TEN-3): la R_T del mín con la red de Td
    p_Td = p_T if r_T_de_Td is r_T else producto.campos(F, {**R, "R_T": r_T_de_Td})
    return _de_campos("mc_", p_T, p_Td)


def _redes(redes) -> Mapping[str, Callable] | None:
    if redes is None:
        return None
    if not isinstance(redes, Mapping) or set(redes) != set(VARIABLES_RED) \
            or not all(callable(f) for f in redes.values()):
        raise ErrorAmbiental(f"redes: {{variable de TF: función año → red o None}} para {list(VARIABLES_RED)} (AMB-10)")
    return redes


def columnas_bloque(celdas, horas, variante, *, operador, meses, datos, umbrales, estaticos=None, redes=None,
                    float64: bool = False) -> dict[str, np.ndarray]:
    """{columna: hora × celda} de la variante (AMB-3 a AMB-5) en las ``celdas`` (ids del operador, sin repetir, en
    ese orden) y las ``horas`` (h crecientes; se parten por mes UTC). float32 con el NaN canónico, o float64 con
    ``float64=True``. ``redes``: la red de cada variable de TF por año (AMB-10); None, la de producción."""
    var = _variante(variante)
    op = _operador(operador)
    _comprobar_umbrales(op, umbrales)
    ids = _enteros(celdas, "celdas")
    if np.unique(ids).size != ids.size:
        raise ErrorAmbiental("celdas: sin repetir")
    h = _horas(horas)
    idx = op.indices(ids)
    _comprobar_datos(op, datos)
    redes = _redes(redes)
    con_c = Candidato.C.value in op.ganador.values()
    est_c = _estaticos_c(estaticos, ids) if con_c and ids.size else None
    tipo = np.float64 if float64 else np.float32
    columnas = COLUMNAS_VARIANTE[var.value]
    salida = {c: np.full((h.size, ids.size), np.nan, dtype=tipo) for c in columnas}
    if h.size == 0 or ids.size == 0:
        return salida
    puntos = op.puntos_fondo(idx)
    for yyyymm, sl in _por_mes(h):
        hm = h[sl]
        F, amp = _fondo(_mes(meses, yyyymm), hm, puntos, umbrales)
        corr = _Correcciones(op, idx, hm, F, amp, datos, umbrales, est_c, redes, yyyymm // 100)
        valores = _columnas_mes(var, F, corr)
        for c in columnas:
            x = np.asarray(valores[c], dtype=np.float64)
            if x.shape != (hm.size, ids.size):
                raise ErrorAmbiental(f"{c}: forma {x.shape}; se espera hora × celda")
            salida[c][sl] = x if float64 else _nan_canonico(x)
    return salida


def mc_bloque(celdas, horas, variante, *, operador, meses, datos, umbrales, estaticos=None,
              redes=None) -> pd.DataFrame:
    """Las columnas de la variante (I: ``mc_*``; D: ``fe_*`` y ``dmc_R_*``) en un lote de celdas y horas (§7.1), como
    tabla larga: ``celda``, ``ts_utc`` (UTC) y las columnas en float32, con las horas de cada celda seguidas y las
    celdas en el orden pedido (AMB-14). La usan la TF de contaminantes (con las dos variantes) y la producción v2 (con
    la ganadora). ``datos``: los residuos, las climatologías y las filas de C de producción
    (``tipos.DatosCompetencia``); ``meses``: AAAAMM → ``fondo_era5l.MesE5L``; ``estaticos``: los de C de las celdas,
    si C gana algún grupo."""
    var = _variante(variante)
    ids = _enteros(celdas, "celdas")
    h = _horas(horas)
    cols = columnas_bloque(ids, h, var, operador=operador, meses=meses, datos=datos, umbrales=umbrales,
                           estaticos=estaticos, redes=redes)
    n_h, n_c = h.size, ids.size
    tabla = {"celda": np.repeat(ids, n_h).astype(np.int64),
             "ts_utc": pd.DatetimeIndex(np.tile(_ns_de(h), n_c)).tz_localize("UTC")}
    for c in COLUMNAS_VARIANTE[var.value]:
        tabla[c] = np.ascontiguousarray(cols[c].T).ravel()
    salida = pd.DataFrame(tabla)
    salida.attrs["variante"] = var.value
    return salida


# ---------------------------------------------------------------------------
# Tablas laterales y sus partes (AMB-1, AMB-2, AMB-12, AMB-16 a AMB-18)
# ---------------------------------------------------------------------------
def _pliegues(pliegues, pliegues_sha256) -> tuple[dict, str]:
    if isinstance(pliegues, (bytes, bytearray, memoryview)):
        datos = bytes(pliegues)
        sha = _sha256(datos)
        if pliegues_sha256 is not None and _hex64(pliegues_sha256, "pliegues_sha256") != sha:
            raise ErrorAmbiental("pliegues_sha256 no es la de los bytes de pliegues_v2_red2.json")
        try:
            contenido = json.loads(datos.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise ErrorAmbiental("pliegues_v2_red2.json no es un JSON en UTF-8") from error
    elif isinstance(pliegues, Mapping):
        if pliegues_sha256 is None:
            raise ErrorAmbiental("con el contenido de pliegues_v2_red2.json va la sha256 del archivo (pliegues_sha256)")
        contenido, sha = dict(pliegues), _hex64(pliegues_sha256, "pliegues_sha256")
    else:
        raise ErrorAmbiental("pliegues: los bytes de pliegues_v2_red2.json (R21) o su contenido")
    if not isinstance(contenido, Mapping) or not isinstance(contenido.get("estaciones"), list) \
            or not isinstance(contenido.get("contaminantes"), Mapping):
        raise ErrorAmbiental("pliegues_v2_red2.json sin «estaciones» ni «contaminantes»")
    return dict(contenido), sha


def _celdas_de_monitores(manifiesto: Mapping, pol: str) -> tuple[dict[str, int], Mapping]:
    """({monitor de pol: celda}, ``contaminantes.<pol>.panel`` del manifiesto) (AMB-1, AMB-2)."""
    registro = manifiesto["contaminantes"].get(pol)
    if not isinstance(registro, Mapping) or not isinstance(registro.get("estaciones"), list) \
            or not isinstance(registro.get("panel"), Mapping):
        raise ErrorAmbiental(f"pliegues_v2_red2.json no trae contaminantes.{pol} con estaciones y panel")
    por_codigo = {}
    for e in manifiesto["estaciones"]:
        if not isinstance(e, Mapping) or not isinstance(e.get("estacion"), str):
            raise ErrorAmbiental("pliegues_v2_red2.json: cada estación trae su código («estacion»)")
        if e["estacion"] in por_codigo:
            raise ErrorAmbiental(f"pliegues_v2_red2.json: estación repetida {e['estacion']!r}")
        por_codigo[e["estacion"]] = e
    celda = {}
    for m in registro["estaciones"]:
        if m not in por_codigo:
            raise ErrorAmbiental(f"el monitor {m!r} de {pol} no está en «estaciones» de pliegues_v2_red2.json")
        c = por_codigo[m].get("celda")
        if c is not None and (isinstance(c, bool) or not isinstance(c, int)):
            raise ErrorAmbiental(f"la celda del monitor {m!r} no es un entero")
        celda[m] = c
    return celda, registro["panel"]


def _politica(politica, policy_sha256) -> str:
    """AMB-12 (H7): la sha256 de los bytes de ``politicas_meteo_v1.json``, calculada aquí, después de comprobar que es
    una lista no vacía de políticas; ``policy_sha256``, si llega, debe ser la misma."""
    if not isinstance(politica, (bytes, bytearray, memoryview)):
        raise ErrorAmbiental("politica: los bytes de politicas_meteo_v1.json (la huella se calcula aquí; H7)")
    datos = bytes(politica)
    sha = _sha256(datos)
    if policy_sha256 is not None and _hex64(policy_sha256, "policy_sha256") != sha:
        raise ErrorAmbiental("policy_sha256 no es la de los bytes de politicas_meteo_v1.json")
    contenido = _json_estricto(datos, "politicas_meteo_v1.json")
    if not isinstance(contenido, list) or not contenido or not all(isinstance(p, dict) for p in contenido):
        raise ErrorAmbiental("politicas_meteo_v1.json no es una lista no vacía de políticas (objetos; AMB-12)")
    return sha


def _leer_panel_bytes(datos: bytes) -> pd.DataFrame:
    """Las columnas ``estacion``, ``ts_utc`` y (si está) ``celda`` de un parquet en memoria."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    try:
        archivo = pq.ParquetFile(io.BytesIO(datos))
        nombres = archivo.schema_arrow.names
        return archivo.read(columns=[c for c in (*CLAVES, "celda") if c in nombres]).to_pandas()
    except (pa.ArrowException, OSError, ValueError) as error:
        raise ErrorAmbiental("los bytes del panel no son un parquet legible") from error


def _panel_atado(panel, registro_panel: Mapping, pol: str, panel_sha256) -> tuple[pd.DataFrame, str]:
    """AMB-2 (H5): el panel entero, atado a ``contaminantes.<pol>.panel`` del registro: por la huella de sus bytes, o
    (ya leído) por la huella declarada y por sus filas y estaciones distintas. Devuelve (tabla, sha256)."""
    registrada = _hex64(registro_panel.get("sha256"), f"contaminantes.{pol}.panel.sha256")
    if isinstance(panel, (bytes, bytearray, memoryview)):
        datos = bytes(panel)
        sha = _sha256(datos)
        if panel_sha256 is not None and _hex64(panel_sha256, "panel_sha256") != sha:
            raise ErrorAmbiental("panel_sha256 no es la de los bytes del panel")
        if sha != registrada:
            raise ErrorAmbiental(f"los bytes del panel de {pol} no son los que cita pliegues_v2_red2.json (R21, MC-09)")
        tabla = _leer_panel_bytes(datos)
    elif isinstance(panel, pd.DataFrame):
        if panel_sha256 is None:
            raise ErrorAmbiental("con el panel ya leído va la sha256 de su archivo (panel_sha256; AMB-2)")
        sha = _hex64(panel_sha256, "panel_sha256")
        if sha != registrada:
            raise ErrorAmbiental(f"el panel de {pol} no es el que cita pliegues_v2_red2.json (R21, MC-09)")
        tabla = panel
    else:
        raise ErrorAmbiental("panel: los bytes de panel_<pol>_red2.parquet o el panel ya leído (R11)")
    if not set(CLAVES) <= set(tabla.columns):
        raise ErrorAmbiental("panel: la tabla del panel de la red 2 con estacion y ts_utc (R11)")
    filas = _entero(registro_panel.get("filas"), f"contaminantes.{pol}.panel.filas", minimo=0)
    estaciones = _entero(registro_panel.get("estaciones"), f"contaminantes.{pol}.panel.estaciones", minimo=0)
    if len(tabla) != filas or int(tabla["estacion"].nunique()) != estaciones:
        raise ErrorAmbiental(f"el panel de {pol} no tiene las filas ({filas}) ni las estaciones ({estaciones}) que "
                             "registra pliegues_v2_red2.json (H5): no es el panel entero")
    return tabla, sha


def _claves_panel(panel: pd.DataFrame, anios) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(estación, ts en ns UTC, posición) de cada fila del panel de los ``anios`` UTC (todas con None), sin modificarlo
    (AMB-2). Las horas se comprueban en todo el panel; los códigos, en las filas de la parte."""
    ts = panel["ts_utc"]
    if bool(ts.isna().any()):
        raise ErrorAmbiental("panel: ts_utc sin nulos")
    if isinstance(ts.dtype, pd.DatetimeTZDtype):
        ts = ts.dt.tz_convert("UTC").dt.tz_localize(None)
    elif not pd.api.types.is_datetime64_dtype(ts.dtype):
        raise ErrorAmbiental("panel: ts_utc es una fecha (sin zona, que se lee como UTC, o con zona)")
    ns = ts.to_numpy().astype("datetime64[ns]").astype(np.int64)
    if bool(np.any(np.mod(ns, _NS_POR_HORA) != 0)):
        raise ErrorAmbiental("panel: toda hora es HH:00 exacta (§3)")
    if anios is None:
        pos = np.arange(ns.size, dtype=np.int64)
    else:
        anio = ns.astype("datetime64[ns]").astype("datetime64[Y]").astype(np.int64) + _ANIO_UNIX
        pos = np.flatnonzero(np.isin(anio, anios)).astype(np.int64)
    est = panel["estacion"]
    if bool(est.isna().any()):
        raise ErrorAmbiental("panel: estacion es un texto en todas las filas")
    est = est.iloc[pos]
    lista = est.tolist()
    if not isinstance(est.dtype, pd.StringDtype) and not all(isinstance(x, str) for x in lista):
        raise ErrorAmbiental("panel: estacion es un texto en todas las filas")
    return np.asarray(lista, dtype=object), ns[pos], pos


def huella_contenido(tabla) -> str:
    """``content_sha256`` de una tabla lateral: sha256 de su forma canónica, con la receta de AMB-18."""
    variante = _variante_de_tabla(tabla)
    esquema = ESQUEMA_DE[variante]
    tipos.validar_esquema(tabla, esquema, nombre=f"tabla lateral {variante}")
    h = hashlib.sha256()
    h.update(_json_canonico({"esquema": esquema.version, "columnas": list(tabla.columns),
                             "tipos": [esquema[c] for c in tabla.columns], "filas": int(len(tabla))}))
    codigos = tabla["estacion"].tolist()
    if any("\x00" in c for c in codigos):
        raise ErrorAmbiental("un código de estación con el carácter nulo")
    h.update("".join(f"{c}\x00" for c in codigos).encode("utf-8"))
    h.update(pd.DatetimeIndex(tabla["ts_utc"]).asi8.astype("<i8").tobytes())
    for c in COLUMNAS_VARIANTE[variante]:
        h.update(_nan_canonico(tabla[c].to_numpy(np.float32)).astype("<f4").tobytes())
    return h.hexdigest()


def _variante_de_tabla(tabla) -> str:
    if not isinstance(tabla, pd.DataFrame):
        raise ErrorAmbiental("la tabla lateral es un DataFrame")
    for v, esquema in ESQUEMA_DE.items():
        if list(tabla.columns) == list(esquema):
            return v
    raise ErrorAmbiental(f"las columnas {list(tabla.columns)} no son las de I ni las de D (MC-28)")


def _metadatos(tabla: pd.DataFrame, variante: str, *, policy_sha256: str, decision_sha256: str, operador_sha256: str,
               panel_sha256: str, pliegues_sha256: str, tras_ultima: int) -> dict:
    """AMB-12: exactamente ``METADATOS_LATERAL``, en ese orden."""
    columnas = list(COLUMNAS_VARIANTE[variante])
    meta = {"model_ready": True, "source_policy_verified": True, "policy_sha256": policy_sha256, "variante": variante,
            "columnas": columnas, "unidades": {c: UNIDADES[variante][c] for c in columnas},
            "content_sha256": huella_contenido(tabla), "decision_sha256": decision_sha256,
            "operador_sha256": operador_sha256, "panel_sha256": panel_sha256, "pliegues_sha256": pliegues_sha256,
            CLAVE_TRAS_ULTIMA: int(tras_ultima)}
    if set(meta) != set(METADATOS_LATERAL):
        raise ErrorAmbiental("los metadatos no son los de METADATOS_LATERAL")
    return {k: meta[k] for k in METADATOS_LATERAL}


def _tabla_lateral(est: np.ndarray, ns: np.ndarray, valores: Mapping[str, np.ndarray], variante: str) -> pd.DataFrame:
    tabla = pd.DataFrame({"estacion": pd.array(est.tolist(), dtype="string"),
                          "ts_utc": pd.DatetimeIndex(ns.astype("datetime64[ns]")).tz_localize("UTC"),
                          **{c: valores[c] for c in COLUMNAS_VARIANTE[variante]}})
    esquema = ESQUEMA_DE[variante]
    tipos.validar_esquema(tabla, esquema, nombre=f"lateral {variante}")
    tabla.attrs["esquema"] = esquema.version
    return tabla


def _orden_claves(est: np.ndarray, ns: np.ndarray) -> np.ndarray:
    """El orden por estación y hora de ``lateral_monitores`` (AMB-2), estable."""
    claves = pd.DataFrame({"estacion": est, "ns": ns})
    return claves.sort_values(["estacion", "ns"], kind="mergesort").index.to_numpy(np.int64)


def lateral_monitores(pol, decision, operador, *, variante="I", panel, pliegues, meses, datos, umbrales, politica,
                      h_ultima, estaticos=None, decision_sha256: str | None = None,
                      pliegues_sha256: str | None = None, panel_sha256: str | None = None,
                      policy_sha256: str | None = None, anios=None) -> tuple[pd.DataFrame, dict]:
    """(tabla, metadatos) de la tabla lateral de un contaminante para ``unir_sidecar`` (§7.1; AMB-1, AMB-2, AMB-12,
    AMB-17).

    ``panel``: los bytes de ``panel_<pol>_red2.parquet`` (su huella se calcula aquí), o el panel entero ya leído (R11;
    sólo lectura) con ``panel_sha256``, la huella de su archivo; los dos, atados a ``contaminantes.<pol>.panel`` de
    ``pliegues`` (los bytes de ``pliegues_v2_red2.json``, R21; H5). ``decision``: los bytes de ``decision.json`` (o su
    contenido con ``decision_sha256``), el mismo del operador. ``politica``: los bytes de ``politicas_meteo_v1.json``
    (``policy_sha256``, optativa, debe ser su huella; H7). ``h_ultima``: la última hora con dato de ERA5-Land (h, la de
    FON-1); las claves posteriores no entran y se cuentan (H2). ``anios``: los años UTC de una parte (AMB-16), o None.
    Los demás, como ``mc_bloque``."""
    pol = _contaminante(pol)
    var = _variante(variante)
    op = _operador(operador)
    _comprobar_umbrales(op, umbrales)
    _, sha_decision = leer_decision(decision, decision_sha256=decision_sha256)
    if sha_decision != op.decision_sha256:
        raise ErrorAmbiental("decision.json no es el del operador (AMB-8)")
    policy_sha256 = _politica(politica, policy_sha256)
    h_ultima = _hora_ultima(h_ultima)
    anios = _anios(anios)
    manifiesto, sha_pliegues = _pliegues(pliegues, pliegues_sha256)
    celda_de, registro_panel = _celdas_de_monitores(manifiesto, pol)
    tabla_panel, panel_sha256 = _panel_atado(panel, registro_panel, pol, panel_sha256)
    est, ns, pos = _claves_panel(tabla_panel, anios)
    presentes = set(est.tolist())
    ajenos = sorted(presentes - set(celda_de))
    if ajenos:
        raise ErrorAmbiental(f"monitores del panel que no son de {pol} en pliegues_v2_red2.json: {ajenos[:_CITADOS]}")
    sin_celda = sorted(m for m in presentes if celda_de[m] is None)
    if sin_celda:
        raise ErrorAmbiental(f"monitores sin celda en pliegues_v2_red2.json: {sin_celda[:_CITADOS]} (R13: estaciones "
                             "con celda)")
    if "celda" in tabla_panel.columns:
        celda_panel = tabla_panel["celda"].iloc[pos]
        esperada = np.array([celda_de[m] for m in est.tolist()], dtype=np.int64)
        if bool(celda_panel.isna().any()) or not np.array_equal(celda_panel.to_numpy(np.int64), esperada):
            raise ErrorAmbiental("la celda del panel no es la de pliegues_v2_red2.json (AMB-1)")
    claves = pd.DataFrame({"estacion": est, "ns": ns}).drop_duplicates().sort_values(["estacion", "ns"],
                                                                                     kind="mergesort")
    est_u = claves["estacion"].to_numpy(dtype=object)
    ns_u = claves["ns"].to_numpy(np.int64)
    h = (ns_u - _EPOCA_NS.astype(np.int64)) // _NS_POR_HORA
    tras = h > h_ultima                                        # AMB-17 (H2): sin ERA5-Land, fuera de la lateral
    tras_ultima = int(tras.sum())
    est_u, ns_u, h = est_u[~tras], ns_u[~tras], h[~tras]
    if h.size and (h.min() < _INT32.min or h.max() > _INT32.max):
        raise ErrorAmbiental("panel: horas fuera de int32")
    celda_fila = np.array([celda_de[m] for m in est_u.tolist()], dtype=np.int64)
    celdas = np.unique(celda_fila)
    op.indices(celdas)                                         # todas en el operador
    columnas = COLUMNAS_VARIANTE[var.value]
    valores = {c: np.full(h.size, _NAN32, dtype=np.float32) for c in columnas}
    meses_fila = _yyyymm(h) if h.size else np.empty(0, np.int64)
    ci_fila = np.searchsorted(celdas, celda_fila)
    for yyyymm in np.unique(meses_fila):
        filas = np.flatnonzero(meses_fila == yyyymm)
        hm = np.unique(h[filas])
        bloque = columnas_bloque(celdas, hm, var, operador=op, meses=meses, datos=datos, umbrales=umbrales,
                                 estaticos=estaticos)
        hi = np.searchsorted(hm, h[filas])
        for c in columnas:
            valores[c][filas] = bloque[c][hi, ci_fila[filas]]
    tabla = _tabla_lateral(est_u, ns_u, valores, var.value)
    meta = _metadatos(tabla, var.value, policy_sha256=policy_sha256, decision_sha256=sha_decision,
                      operador_sha256=op.sha256, panel_sha256=panel_sha256, pliegues_sha256=sha_pliegues,
                      tras_ultima=tras_ultima)
    return tabla, meta


def unir_partes(partes) -> tuple[pd.DataFrame, dict]:
    """(tabla, metadatos) de una lateral desde sus partes (AMB-16; PED-7 de I20): ``partes`` son pares (tabla,
    metadatos) de ``lateral_monitores`` con ``anios`` (de memoria, o releídos con sus ``attrs["metadatos"]``), en
    cualquier orden. Bit a bit, la lateral armada de una vez sobre los mismos años."""
    lista = list(partes) if not isinstance(partes, (pd.DataFrame, Mapping)) else None
    if not lista:
        raise ErrorAmbiental("unir_partes: una lista no vacía de partes (tabla, metadatos)")
    tablas, metas, variante = [], [], None
    for i, parte in enumerate(lista):
        if not isinstance(parte, (tuple, list)) or len(parte) != 2:
            raise ErrorAmbiental(f"unir_partes: la parte {i} no es (tabla, metadatos)")
        tabla, meta = parte
        v = _comprobar_metadatos(tabla, meta)
        if variante is not None and v != variante:
            raise ErrorAmbiental("unir_partes: partes de variantes distintas")
        variante = v
        tablas.append(tabla)
        metas.append(dict(meta))
    propias = ("content_sha256", CLAVE_TRAS_ULTIMA)
    comunes = [{k: v for k, v in m.items() if k not in propias} for m in metas]
    if any(c != comunes[0] for c in comunes[1:]):
        raise ErrorAmbiental("unir_partes: las partes no traen los mismos metadatos (decisión, operador, panel, "
                             "pliegues o política; AMB-16)")
    est = np.concatenate([t["estacion"].to_numpy(dtype=object) for t in tablas])
    ns = np.concatenate([pd.DatetimeIndex(t["ts_utc"]).asi8 for t in tablas]).astype(np.int64)
    orden = _orden_claves(est, ns)
    est, ns = est[orden], ns[orden]
    if est.size > 1 and bool(np.any((est[1:] == est[:-1]) & (ns[1:] == ns[:-1]))):
        raise ErrorAmbiental("unir_partes: una clave (estacion, ts_utc) está en dos partes")
    valores = {c: np.concatenate([t[c].to_numpy(np.float32) for t in tablas])[orden]
               for c in COLUMNAS_VARIANTE[variante]}
    tabla = _tabla_lateral(est, ns, valores, variante)
    meta = {**metas[0], "content_sha256": huella_contenido(tabla),
            CLAVE_TRAS_ULTIMA: int(sum(m[CLAVE_TRAS_ULTIMA] for m in metas))}
    return tabla, {k: meta[k] for k in METADATOS_LATERAL}


# ---------------------------------------------------------------------------
# La unión con v2 (AMB-13; A29)
# ---------------------------------------------------------------------------
def cargar_adaptador(ap) -> ModuleType:
    """``meteorologia_v2`` (el adaptador fijado), por ruta y huella (``fijados.cargar_adaptador``)."""
    return fijados.cargar_adaptador(ap)


def _panel_de_prueba(tabla: pd.DataFrame) -> pd.DataFrame:
    """Las claves de la tabla al revés, más una clave que la tabla no tiene y una columna propia (AMB-13)."""
    claves = tabla[list(CLAVES)].iloc[::-1].reset_index(drop=True)
    if len(claves):
        extra = pd.DataFrame({"estacion": pd.array(["sin_lateral"], dtype="string"),
                              "ts_utc": claves["ts_utc"].iloc[:1].reset_index(drop=True)})
        claves = pd.concat([claves, extra], ignore_index=True)
    claves["fila_de_prueba"] = np.arange(len(claves), dtype=np.int64)
    return claves


def _panel_utc(panel) -> pd.DataFrame:
    if not isinstance(panel, pd.DataFrame):
        raise ErrorAmbiental("panel: un DataFrame")
    base = panel.copy()
    if "ts_utc" in base.columns and pd.api.types.is_datetime64_dtype(base["ts_utc"].dtype) \
            and not isinstance(base["ts_utc"].dtype, pd.DatetimeTZDtype):
        base["ts_utc"] = base["ts_utc"].dt.tz_localize("UTC")            # §7.1, punto 2 (correr_v2)
    return base


def _comprobar_metadatos(tabla: pd.DataFrame, metadatos) -> str:
    if not isinstance(metadatos, Mapping):
        raise ErrorAmbiental("metadatos: un diccionario")
    if set(metadatos) != set(METADATOS_LATERAL):
        raise ErrorAmbiental(f"metadatos: exactamente {list(METADATOS_LATERAL)} (AMB-12)")
    if metadatos["model_ready"] is not True or metadatos["source_policy_verified"] is not True:
        raise ErrorAmbiental("metadatos: model_ready y source_policy_verified en True")
    for clave in ("policy_sha256", "content_sha256", "decision_sha256", "operador_sha256", "panel_sha256",
                  "pliegues_sha256"):
        _hex64(metadatos[clave], f"metadatos.{clave}")
    _entero(metadatos[CLAVE_TRAS_ULTIMA], f"metadatos.{CLAVE_TRAS_ULTIMA}", minimo=0)
    variante = _variante_de_tabla(tabla)
    if metadatos["variante"] != variante:
        raise ErrorAmbiental(f"metadatos: la variante es {metadatos['variante']!r} y la tabla es de {variante}")
    columnas = list(COLUMNAS_VARIANTE[variante])
    if list(metadatos["columnas"]) != columnas:
        raise ErrorAmbiental("metadatos: columnas distintas de las de la tabla (MC-28)")
    if not isinstance(metadatos["unidades"], Mapping) or dict(metadatos["unidades"]) != dict(UNIDADES[variante]):
        raise ErrorAmbiental("metadatos: unidades distintas de las de MC-28")
    if metadatos["content_sha256"] != huella_contenido(tabla):
        raise ErrorAmbiental("metadatos: content_sha256 no es la huella del contenido de la tabla (AMB-12)")
    return variante


def comprobar_union(tabla, metadatos, adaptador, *, panel=None) -> dict:
    """Une la tabla lateral con ``adaptador.unir_sidecar`` real sobre un panel de prueba (o ``panel``) y comprueba que
    no cambia filas ni orden y que trae los valores de la lateral (§7.1, punto 2; AMB-13). Devuelve la identidad de
    ``unir_sidecar``. Si el código fijado se niega, su ``ValueError`` sale sin cambios."""
    unir = getattr(adaptador, "unir_sidecar", None)
    if not callable(unir):
        raise ErrorAmbiental("adaptador: el módulo meteorologia_v2 (fijados.cargar_adaptador)")
    if not isinstance(tabla, pd.DataFrame):
        raise ErrorAmbiental("la tabla lateral es un DataFrame")
    if not isinstance(metadatos, Mapping):
        raise ErrorAmbiental("metadatos: un diccionario")
    base = _panel_utc(_panel_de_prueba(tabla) if panel is None else panel)
    resultado, identidad = unir(base, tabla, metadata=dict(metadatos))
    nuevas = [c for c in tabla.columns if c not in CLAVES]
    if len(resultado) != len(base) or not resultado.index.equals(base.index):
        raise ErrorAmbiental("la unión cambió las filas o el índice del panel")
    if list(resultado.columns) != list(base.columns) + nuevas:
        raise ErrorAmbiental("la unión no agregó exactamente las columnas de la lateral, en su orden")
    for c in base.columns:
        if not resultado[c].equals(base[c]):
            raise ErrorAmbiental(f"la unión cambió la columna {c!r} del panel o su orden")
    izquierda = pd.DataFrame({"estacion": base["estacion"].astype(object),
                              "ts_utc": base["ts_utc"].dt.tz_convert("UTC"),          # en UTC aunque traiga otra zona
                              "_orden": np.arange(len(base))})
    derecha = tabla.assign(estacion=tabla["estacion"].astype(object), ts_utc=tabla["ts_utc"].dt.tz_convert("UTC"))
    esperado = izquierda.merge(derecha, on=list(CLAVES), how="left", sort=False).sort_values("_orden",
                                                                                            kind="mergesort")
    if len(esperado) != len(base):
        raise ErrorAmbiental("la lateral trae claves repetidas")
    for c in nuevas:
        if not np.array_equal(resultado[c].to_numpy(np.float32), esperado[c].to_numpy(np.float32), equal_nan=True):
            raise ErrorAmbiental(f"la unión no trae los valores de la lateral en {c!r}")
    if not isinstance(identidad, Mapping) or set(identidad) != set(_CLAVES_IDENTIDAD) \
            or list(identidad["columns"]) != nuevas or identidad["policy_sha256"] != metadatos["policy_sha256"] \
            or identidad["sidecar_rows"] != len(tabla) or identidad["panel_rows"] != len(base) \
            or not isinstance(identidad["content_sha256"], str) \
            or _HEX64.fullmatch(identidad["content_sha256"]) is None \
            or identidad["source_artifact_sha256"] != metadatos.get("source_artifact_sha256"):
        raise ErrorAmbiental("la identidad de unir_sidecar no es la de la lateral")
    _comprobar_metadatos(tabla, metadatos)
    return dict(identidad)


# ---------------------------------------------------------------------------
# La fábrica de la TF de contaminantes (A26; AMB-10, AMB-11)
# ---------------------------------------------------------------------------
def _red_del_escenario(escenarios, escenario: str, anio: int):
    return escenarios.red(escenario, int(anio))


def fabrica_tf_contaminantes(predecir, *, operador, meses, datos, umbrales, escenarios, estaticos=None,
                             horas_de_dias=None) -> Callable:
    """La fábrica de A26 para ``tendencias.tf_contaminantes``: ``fabrica(modelo, variante, escenario, celdas, dias)``
    → predicción día × celda (Anexo B; AMB-10, AMB-11).

    Arma con ``mc_bloque`` las columnas de la variante en las ``celdas`` y en las horas de los ``dias`` (d2000), con la
    red del escenario de cada variable (``escenarios``: {«T», «Td», «rapidez», «p»: objeto con ``red(escenario, año)``,
    como ``tendencias.EscenariosTF``), y llama a ``predecir(modelo, variante, tabla, celdas, dias)``, la fábrica de
    producción v2, que devuelve día × celda."""
    if not callable(predecir):
        raise ErrorAmbiental("predecir: la fábrica de producción v2 (modelo, variante, tabla, celdas, dias → día × "
                             "celda)")
    op = _operador(operador)
    _comprobar_umbrales(op, umbrales)
    if not isinstance(escenarios, Mapping) or set(escenarios) != set(VARIABLES_RED) \
            or not all(callable(getattr(e, "red", None)) for e in escenarios.values()):
        raise ErrorAmbiental(f"escenarios: {{variable de TF: EscenariosTF}} para {list(VARIABLES_RED)}")
    convertir = horas_dia_utc if horas_de_dias is None else horas_de_dias
    if not callable(convertir):
        raise ErrorAmbiental("horas_de_dias: una función días → horas h")

    def fabrica(modelo, variante, escenario, celdas, dias) -> np.ndarray:
        var = _variante(variante)
        if escenario not in ESCENARIOS_TF:
            raise ErrorAmbiental(f"escenario {escenario!r}; son {list(ESCENARIOS_TF)}")
        d = _enteros(dias, "dias")
        if d.size > 1 and not bool(np.all(np.diff(d) > 0)):
            raise ErrorAmbiental("dias: crecientes y sin repetir")
        c = _enteros(celdas, "celdas")
        h = _horas(convertir(d))
        redes = {vm: functools.partial(_red_del_escenario, escenarios[vm], escenario) for vm in VARIABLES_RED}
        tabla = mc_bloque(c, h, var, operador=op, meses=meses, datos=datos, umbrales=umbrales, estaticos=estaticos,
                          redes=redes)
        P = np.asarray(predecir(modelo, var.value, tabla, c, d), dtype=np.float64)
        if P.shape != (d.size, c.size):
            raise ErrorAmbiental(f"predecir: día × celda ({d.size} × {c.size}), no {P.shape}")
        return P

    return fabrica


# ---------------------------------------------------------------------------
# La convención de el_* (MC-28)
# ---------------------------------------------------------------------------
def regla_el(ap) -> dict:
    """La regla ``el_*`` de ``_features.py`` por AST (``fijados.regla_el_features``)."""
    return fijados.regla_el_features(ap)


def diferencias_con_el(regla: Mapping) -> list[str]:
    """Lo que difiere entre la regla ``el_*`` (``regla_el``) y las columnas de este módulo (MC-28); vacía si calzan.
    Magnus debe diferir (§7.1: ``mc_rh`` usa 17,625 y 243,04, distinto de ``el_rh``)."""
    diferencias = []
    nombres = list(regla.get("meteorologicas", ()))
    if sorted(n[len("el_"):] for n in nombres if n.startswith("el_")) != sorted(SUFIJOS) or len(nombres) != len(SUFIJOS):
        diferencias.append(f"sufijos de el_*: {nombres} frente a {list(SUFIJOS)}")
    if regla.get("kelvin") != _KELVIN:
        diferencias.append(f"kelvin: {regla.get('kelvin')!r} frente a {_KELVIN!r}")
    if tuple(regla.get("direccion", ())) != ("el_u10", "el_v10"):
        diferencias.append(f"dirección: arctan2{tuple(regla.get('direccion', ()))} frente a arctan2(u, v)")
    magnus_el = tuple(regla.get("magnus", ()))[1:]
    if magnus_el != tuple(constantes.valor("MAGNUS_EL_FEATURES")):
        diferencias.append(f"Magnus de el_rh: {magnus_el} frente a {tuple(constantes.valor('MAGNUS_EL_FEATURES'))}")
    if tuple(constantes.valor("MAGNUS_AGUA"))[1:] == magnus_el:
        diferencias.append("mc_rh usa el mismo Magnus que el_rh (§7.1 pide 17,625 y 243,04)")
    return diferencias


__all__ = (
    "CLAVE_TRAS_ULTIMA", "CLAVES", "COLUMNAS_FE", "COLUMNAS_MC", "COLUMNAS_R", "COLUMNAS_VARIANTE", "CONTAMINANTES",
    "ESCENARIOS_TF", "ESQUEMA_DE", "ESQUEMA_OPERADOR", "ErrorAmbiental", "FIRMA_OPERADOR", "METADATOS_LATERAL",
    "NucleoGrilla", "OperadorGrilla", "RED_DE", "UMBRALES_OPERADOR", "UNIDADES", "VARIABLES_RED", "cargar_adaptador",
    "columnas_bloque", "comprobar_union", "diferencias_con_el", "direccion_sin_cos", "etiqueta_hiper",
    "fabrica_tf_contaminantes", "ganador_ambiental", "horas_dia_utc", "huella_contenido", "lateral_monitores",
    "leer_decision", "leer_operador", "mc_bloque", "operador_grilla", "regla_el", "unir_partes",
)
