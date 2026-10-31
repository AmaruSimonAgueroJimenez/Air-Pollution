"""Integración por fases (M2a, M3-4, M5 y M6): unidades reanudables, ``avance.jsonl``, procesos y fábrica de entradas.

Es el único módulo que lanza procesos (8 en M3-4 y M5, por D2, o menos en una fase, por D59: ORQ-45) y el único que
arma entradas desde el disco (§3 del diseño: «Sólo ``orquestacion`` arma entradas desde el disco»). Toda escritura pasa
por ``salidas`` (§0, regla 8). El resultado es idéntico, bit a bit, con 1, 2 u 8 procesos (S9): lote de horas fijo (un
mes UTC), unidades en un orden fijo y agregación en ese orden (MC-37).

Qué hay (y para qué compuerta):
- ``Cfg``: la configuración de una corrida (rutas por alias de ``entorno.Rutas``, entradas por alias, la lista cerrada
  de huellas, umbrales, modo, procesos (y, D59, los de cada fase que reparte: ``FASES_REPARTO``), pares (uso,
  grupo), recorte, compuerta de deriva, las lecturas que se permiten a los trabajadores bajo /Volumes, y dos puntos de
  entrada: las negativas de I22 y la fábrica de v2 de M6).
- La fábrica de entradas: ``ruta_de_alias``, ``leer_entrada`` (los bytes con ``open`` de Python y su sha256 frente a
  la lista cerrada, antes de pasarlos a pandas, pyarrow, netCDF4 o rasterio; CEG-5), ``leer_catalogo_dmc``,
  ``leer_conjuntos``, ``infos_de_tabla`` y los lectores de M2a que usa M3-4.
- ``Avance``: ``avance.jsonl`` (sólo huellas y estado; §8 y §10), por ``salidas.agregar_linea``: una cabecera con la
  corrida y su huella, y una línea por unidad hecha con su huella de entrada, la de salida y los archivos que escribió;
  M5 agrega una línea de compuerta al de su M3-4 (ORQ-20).
- ``repartir``: los trabajadores en un grupo de procesos propio, que se cierra y se espera (``ceguera.
  procesos_hijos_vivos``); resultados en el orden de las unidades.
- ``correr_m2a``, ``correr_m34``, ``correr_m5`` y ``correr_m6`` con las fases de §2.5 del diseño (``FASES_M2A``,
  ``FASES_M34``, ``FASES_M5`` y ``FASES_M6``; ORQ-33).

Dueño: I20 (ola 5: M2a y M3-4 en la primera fase; M5 y M6 en la segunda; ola 6: la memoria, ORQ-42 a ORQ-44; cierre:
los procesos por fase, ORQ-45, D59).
Lecturas propias (ORQ-n), para el addendum de M1:
- ORQ-1. **La configuración** (§8, «Cadena de huellas»; §10, «alguna huella de la lista cerrada del addendum de M1 o
  del registro de M2a difiere»). ``Cfg.entradas`` dice qué es cada insumo, por ruta por alias (``ENTRADAS_M2A`` y
  ``ENTRADAS_M34``); ``Cfg.huellas`` es la lista cerrada {ruta por alias: sha256}. Toda entrada que se lee debe estar
  en la lista con su huella (la lectura más estricta): una que falta o difiere detiene la compuerta antes de leer el
  resto (fase «negativas»). Las negativas de §10 (git, intentos, C5…) son de I22: ``Cfg.negativas`` es su punto de
  entrada, una función (cfg) → lista de fallas que se llama antes que todo. En los modos reales (``estaticos``,
  ``aplicar``) ``pares`` debe traer los cinco (uso, grupo) de §6.1; en el sintético puede traer menos, porque la red
  mínima no alcanza los mínimos del Anexo A de EX (900 días) ni de lo crónico (ORQ-14).
- ORQ-2. **La huella antes de leer** (CEG-5). Cada entrada se lee una vez con ``open`` de Python (el gancho de
  ``ceguera.RegistroAccesos`` la ve) y su sha256 se compara con la lista cerrada; después los bytes van a pandas o
  pyarrow en memoria (``io.BytesIO``). Los lectores de otros módulos que reciben la ruta y la huella (``leer_mes``,
  ``leer_geopotencial``, ``leer_tesela``, ``leer_ghs``, ``leer_registro_c5``, ``leer_politica_reloj``,
  ``leer_manifiestos``, ``series_horarias``) ya leen con ``open`` y exigen la huella (diferencia 2 de la ola 2).
- ORQ-3. **El catálogo DMC** (M2a, fase «catálogo»): ``catalogo_nacional.json.gz`` del descargador, leído como
  ``reloj_dmc.extraccion.leer_catalogo_dmc`` (las mismas columnas, textos tal cual, un código de 6 dígitos sin
  repetir), sin importar el reloj (sólo ``entorno`` y ``fijados`` lo importan; §1 del diseño). Sólo coordenadas,
  altitudes y estratos (§10, M2a: «sólo coordenadas y altitudes del catálogo»).
- ORQ-4. **Teselas** (D37, NAS-15, NAS-16; pendiente de la ola 2). Una tesela NASADEM se lee si su caja de 1° (del
  nombre «[ns]DD[ew]DDD», como los HGT) toca la ventana que se pide (``ventana_k3`` de cada estación, la de los
  píxeles o ``ventana_necesaria`` de cada lote de celdas); un nombre sin esa forma se lee siempre (del lado seguro: la
  tesela que falta se lee como que no existe). Se leen una vez y se guardan en memoria mientras dure la fase.
- ORQ-5. **z_E5L y su alineación** (§4.1, MC-38, S13). La alineación compara el z del geopotencial crudo (sólo el caso
  1, ``z_e5l`` con NASADEM vacío, sp̄ NaN y ningún píxel válido) con ``era5land_altitud_modelo_pixeles.parquet``,
  antes de abrir ningún mes (en las negativas, antes de las huellas de los meses; H8 c): si difiere, ``ErrorAlineacion``
  y M2a se detiene sin escribir nada, ni la cabecera de ``avance.jsonl`` (ORQ-35). Después,
  ``z_e5l`` con NASADEM y sp̄ da la tabla de §4.1. Una sola pasada por ERA5-Land si todo píxel válido tiene caso 1 o 2
  (sp̄ sólo cambia ``z_hipso`` y ``dif_mayor_50m``); dos si alguno necesita la hipsométrica (pendiente de la ola 2).
- ORQ-6. **La pasada de M2a** (§4.1, §4.7; FON-1, FON-13, MC-39). Los meses van en orden; cada uno exige
  ``completo_hasta(h_ultima)`` y ``comprobar_unidades``; el fondo en las estaciones es ``campos_fondo`` con el operador
  de las estaciones (z_s) y se guarda en ``insumos/puntos_estacion/<código>.parquet`` (``tabla_puntos``, A1); las
  climatologías del estado y sp̄ se acumulan en el orden de los meses; ``renormalizada`` se cuenta por punto-hora y va
  al registro. El fondo se calcula para toda estación con coordenadas (también las que K3 excluye: cuentan en el
  control de calidad, A8). Una estación sin vecino válido queda «sin_fondo» según TIP-14.
- ORQ-7. **Los estáticos de las celdas** (TIP-22, P-CAN-3). ``estaticas/celdas.parquet`` es
  ``ESQUEMA_ESTATICAS_CELDA_C``: los de ``estaticos_celdas`` más ``z_e5l`` = Σ w_i z_E5L,i del operador de la celda
  con z = ``z_media`` (NaN sin vecino). Por lotes de ``LOTE_CELDAS`` celdas en el orden de ``celdas.parquet``; las
  declaraciones de los lotes se suman.
- ORQ-8. **Reanudación** (§8, «Reanudable»; §10, «Reanudar la misma corrida (misma etiqueta y huellas) es seguir sus
  unidades»). La huella de la corrida es la de su configuración (compuerta, etiqueta, entradas, lista cerrada, modo,
  pares, recorte y deriva). ``avance.jsonl`` empieza con ella; otra huella en la misma carpeta detiene (una corrida
  nueva exige una errata). Una unidad se salta si su última línea trae la misma huella de entrada y cada archivo que
  escribió sigue con su sha256; si no, se rehace. **Lo que sigue lee siempre del disco** lo que escribió cada unidad,
  también recién escrita: así la corrida interrumpida y reanudada da los mismos bytes que la de una vez. Lo que sólo
  vive en memoria (la selección, las métricas, la TF y la decisión) se recalcula siempre («La decisión se recalcula
  desde las tablas»). Una unidad sin archivos (una estación sin ningún artefacto normalizable) se rehace siempre.
- ORQ-9. **Un «.part» que quedó de un corte duro** (P-SAL-8). ``salidas.escribir`` se niega sobre él y este módulo no
  borra (§0, regla 8: sólo ``salidas`` escribe): la reanudación se detiene con el nombre del archivo y la unidad. Pedido
  PED-1 a I17: una función de ``salidas`` que lo descarte sólo si su unidad no figura hecha en ``avance.jsonl``, y lo
  registre.
- ORQ-10. **Los trabajadores** (§8, «Memoria y procesos»; S9, S10; CEG-7). ``repartir`` lanza ``mín(procesos, n)``
  intérpretes ``-B -I`` del intérprete en uso, en un grupo de procesos propio (el primero lo crea y los demás se suman),
  con los tres hilos en «1» en el entorno y ``entorno.fijar_hilos`` al empezar (el trabajador comprueba que toda
  biblioteca quede en 1 hilo). Cada trabajador corre bajo su propio ``ceguera.RegistroAccesos`` en bloqueo sobre
  /Volumes (con las lecturas permitidas de ``Cfg.permitidas``) y ``ceguera.SinRed``, con ``nice`` (§8); con un solo
  proceso, las unidades corren aquí bajo ese mismo bloqueo (H18). El protocolo son pickles con su largo por las
  tuberías: el contexto se serializa una sola vez para todos y viaja sin copias (H1); la salida estándar del
  trabajador queda fuera del protocolo. Un SIGTERM al principal cierra el grupo (H18). Una unidad a la vez por
  trabajador; los resultados vuelven en el orden de las unidades (``al_terminar`` los recibe en ese orden, en el
  proceso principal, que es el único que escribe). Al terminar o ante un error, se cierran las tuberías, se mata el
  grupo si hace falta y se espera a todos; si queda un proceso vivo del grupo, es un error.
- ORQ-11. **Unidades de M3-4** (§2.5 del diseño; MC-37). Paso 1 y envoltorio, K4, retirada y marca 14: una unidad por
  estación (los artefactos de una estación van juntos al envoltorio), en orden de código; su tabla ancha va a
  ``qc/estaciones/<código>.parquet`` con, en sus metadatos, lo que la estación aporta a §2.7 y a la política
  efectiva: los conteos de QC-22, el resultado de cada artefacto (sin la tabla larga), las políticas efectivas y si
  le falta la prueba de traslado (marca 21). Nunca D de K4 (§0.4.6). La selección y la predicción: una unidad por
  pliegue externo. La TF: una unidad por mes UTC (TEN-22).
- ORQ-12. **El objetivo de la selección** (A16, INT-5, P62): MSE_e = sse/n por estación de prueba interna, su banda con
  ``particiones.distancia_entrenamiento_km`` en el entrenamiento de su interno y un solo ``validacion.puntaje`` con el π
  del uso. Agudo y crónico comparten A, B y AB (MC-55, uso agudo); C_est se elige en lo crónico, en T y en Td (Td sale
  del mismo método que T, §6.1).
- ORQ-13. **El pliegue de producción** (P61, §4.9: «los hiperparámetros se vuelven a elegir con el mismo procedimiento
  sobre todas las estaciones»): ``Pliegue("produccion", P2, prueba=(), entrenamiento=todas las que entran)``, así que
  sus internos llevan el amortiguador de P2. Los hiperparámetros de producción alimentan la TF (TEN-12: «la de
  producción») y ``decision.json``; se eligen para todas las variables de cada uso presente en ``pares`` (la TF de un uso
  exige todas sus variables, ``tendencias.filas_tf``).
- ORQ-14. **Pares de la red mínima sintética.** Con la red de las pruebas (meses, no años) sólo es decidible lo
  ambiental de p, que no tiene EX (§6.1; DEC-3 exige cada métrica finita). ``Cfg.pares`` lo restringe sólo en el modo
  sintético; los demás pares siguen el mismo camino del código.
- ORQ-15. **Horas emparejadas y finitud** (INT-6, VAL-15, A25, P87, P88). En cada evaluación entran las horas con
  observación válida y producto finito en todos los candidatos del uso que predicen en la estación. La finitud de E0
  se cuenta aparte en las celdas pobladas de la pasada de TF de su uso (todas las horas de la pasada; A, B y AB con la
  corrección de la red completa, C y C_est con ``producto.conteo_finito_c``), por lotes de ``LOTE_PUNTOS_TF`` celdas
  (H3: los conteos son enteros y dan lo mismo), y en las estaciones de validación (sus horas observadas de prueba con
  fondo, en P1 y P2; sin las de D34).
- ORQ-16. **Las palabras del registro** (S7, D3, P42). ``registro_m2a.json`` y ``registro_m34.json`` son resumen y no
  pueden decir «fondo», «era5l» ni «e5l»: el motivo «sin_fondo» y sus conteos se informan como «sin_pixel_valido»
  (renombrado sólo en el registro; los estáticos guardan el motivo de TIP-14).
- ORQ-17. **Huellas de las salidas que cita ``decision.json``** (§8, «Cadena de huellas»; hallazgo de integración de
  la ola 2): las de ``validacion/puntajes.parquet``, ``tendencias/resumen_tf.parquet``, la política efectiva y las
  entradas de la corrida, por ruta por alias.
- ORQ-19. **SINCA** (§5.6, descriptiva; A12, D47-D50). Se leen los dos manifiestos con sus seis huellas, se eligen
  las series y se arman las series horarias con los veredictos civiles del reloj SINCA (su tabla, su sha256, su
  ``resumen.json`` y la convención elegida). La comparación con el producto no corre: los manifiestos no traen las
  coordenadas de las estaciones y el texto no dice de dónde salen (pregunta P-ORQ-1); el registro lo declara. Si la
  red falta en las entradas, se declara «sin_red» (§5.6: «Si llega después de M3-4, se informa como posterior»).
- ORQ-18. **M2a sin subcarpeta** (ENT-4 admite ``v1/m2a/<sub>``). Con una subcarpeta, el nombre de cada salida
  relativo a la corrida empieza con ``<sub>/`` y ninguna carpeta de ``ceguera.CLASE_DE_CARPETA`` (``estaticas/``,
  ``insumos/``) fija su clase (CEG-20 las ancla al comienzo del nombre): ``salidas`` se niega a escribirlas como
  insumo. M2a escribe siempre en ``v1/m2a`` (PED-4).
- ORQ-20. **M5 en la carpeta de su M3-4** (ENT-4: «M5 publica en la misma carpeta que su M3-4»; §8, «Reanudable»;
  §10). M5 sigue el ``avance.jsonl`` de M3-4: exige su cabecera (la misma corrida, cualquier huella) y le agrega una
  línea de compuerta («compuerta», «m5», con la huella de la corrida de M5); otra huella de M5 en la misma carpeta
  detiene (una corrida nueva exige una errata), como ORQ-8, y sin el ``avance.jsonl`` de M3-4 no corre. Lee lo de M3-4
  con la huella del ``sha256.json`` de la carpeta, que su recibo cita, y al terminar sella otra vez: el recibo de M3-4
  se archiva en ``recibos/`` (SLD-10). M6 escribe en ``v1/<ETIQUETA>/m6`` con su propio ``avance.jsonl``; la clase de
  cada salida de M6 se busca con el prefijo «m6/» (CEG-20).
- ORQ-21. **Las entradas de M5 y M6** (§8, «Cadena de huellas»). De la lista cerrada, ``ENTRADAS_M5`` (y
  ``comparacion_m6`` en ``ENTRADAS_M6``). De M2a y de la corrida, cada archivo con la huella de su ``sha256.json``: los
  estáticos de las estaciones y de las celdas, z_E5L, el clima del estado, el fondo en las estaciones,
  ``decision.json``, los residuos, A, los tramos, la política efectiva y las tablas de control de calidad. La
  ``DatosCompetencia`` de producción la arma ``_datos_produccion``, la misma función que usa M3-4 (las estaciones con
  residuos: el entrenamiento de producción de PRO-4 y AMB-5); M3-4 le agrega sus pliegues. La huella de las unidades es
  la de lo que se leyó, no la de toda la carpeta (que cambia al sellar M5).
- ORQ-22. **Los ganadores y sus hiperparámetros** (§6.2, paso 6; AMB-7). ``decision.json`` lleva, por (uso, grupo),
  {candidato: {variable del producto: θ}}, con θ en la forma de ``decision._a_json``: {L_km, lam, kappa} en A y B,
  [θ de A, θ de Φ′] en AB y α en C y C_est; «uv» va como u y v, con el mismo θ (MC-43). Corrige la primera fase, que
  escribía {«A», «phi_prima»}, {«alfa»} y la variable de selección («uv»), que ``ambiental.ganador_ambiental`` no
  lee. Lo ambiental se lee con ``ambiental.ganador_ambiental``; lo agudo y lo crónico, sólo (T, Td) (§6.1).
- ORQ-23. **Dos pasadas por ERA5-Land** (A28: «una sola pasada por ERA5-Land si se puede»; §8 del diseño). La lista
  de la representatividad depende de todo el período de cada estación (§7.2, punto 6) y el producto sin ellas la
  necesita antes, así que hay una primera pasada (``_unidad_t2m``, un mes por unidad) que sólo lee la t2m de los
  píxeles del reloj. La segunda, anual (``_unidad_anio``, una unidad por año UTC de ``meses_era5l``, en orden), lee
  cada mes del año una vez, y el enero siguiente (lo necesitan los días del 31 de diciembre, como
  ``meteo_civil_v3.archivos_anio`` y S14), y con ellos arma el 0,1° de los meses del año, las cinco tablas diarias de
  salud y las partes anuales de las laterales: cada enero se lee dos veces. Hay un solo mes en memoria a la vez: la
  salud se acumula mes a mes (``AcumuladorMeteo.agregar(…, horas=)``, SAL-13; bit a bit la serie entera) por lotes de
  ``LOTE_CELDAS_SALUD`` celdas (PRO-2), y de cada mes sólo quedan los píxeles que usan los monitores (ORQ-27). También
  hay unidad para los años con filas en el panel y sin ningún mes ERA5-Land (sólo laterales: AMB-17 cuenta sus
  claves). Los resultados vuelven al proceso principal en el orden de los años; él escribe y registra (ORQ-10).
  Pregunta P-ORQ-3.
- ORQ-24. **La representatividad** (§7.2, punto 6; MC-52, A27, SAL-9). Estaciones: las del entrenamiento de
  producción. El píxel del reloj, con ``PixelReloj.enlazar`` de ``fijados.cargar_elegir_pixel`` (la regla de 15 km
  y ``coordenadas_en_rango``, como ``extraccion.enlazar_pixeles``), el catálogo de píxeles y
  los píxeles válidos de M2a (la regla de los tres meses de §4.1, la misma de ``reloj_dmc.extraccion.pixeles_validos``),
  sin abrir ``pixeles_dmc.parquet``; ``permitir_cargados`` sólo en el modo sintético. La observación es ``Ts`` con
  ``valido_T`` de ``qc/estaciones/<código>.parquet``, y la t2m del píxel, la de ERA5-Land tal cual (K) en todos los
  meses. Sólo se guarda la lista (``salud/representatividad/excluidas.json``, insumo). El producto de
  representatividad es el agudo con el entrenamiento sin ellas (``entrenamiento`` de ``producto``), en el día civil
  (pregunta P-ORQ-4); sin excluidas, es el agudo. Si las excluye a todas, M5 se detiene.
- ORQ-25. **El 0,1°** (MC-08, A10, PRO-12 a PRO-14). Con el ganador y los hiperparámetros ambientales, en los
  píxeles válidos (``fondo_era5l.operador_pixeles``: z = z_E5L y el fondo tal cual), un NetCDF por mes
  (``producto_01deg/meteo_<AAAAMM>.nc``) con las huellas de ``decision.json``, de z_E5L, del catálogo y del mes. Si C
  gana un grupo ambiental, sus estáticos son los de la celda que contiene el centro del píxel con los bordes oeste y
  sur cerrados (P84, rige la a); un centro sin celda en la grilla detiene (pregunta P-ORQ-5).
- ORQ-26. **La salud** (§3; §7.2, puntos 1 y 3; §7.3; SAL-5 a SAL-8, SAL-10). Celdas: las de ``celdas.parquet`` con
  cod_comuna > 0 y z_poblada finita (§3: «usos de salud: z = media NASADEM ponderada por la población»), con su
  operador del fondo y sus estáticos; los pesos de su año (las filas del año de los pesos de SAL-6) y la lluvia como
  ``meteo_civil_v3`` (``salud.pesos_lluvia`` y ``lluvia_comunal``). Productos: el agudo (ganador agudo) en las carpetas
  civil, UTC−4 y regional, de las mismas horas (punto 3); la representatividad (ORQ-24); y lo crónico: los días
  civiles con el ganador crónico (C_est con el clima del estado y los estáticos), en
  ``salud/cronico/meteo_<año>.parquet``, y al final ``salud/cronico/temperatura_anual.parquet`` con
  ``salud.cronico_anual`` y los pesos de cada año, releyendo del disco las tablas diarias. Un producto igual a otro
  (la representatividad sin excluidas) se calcula una vez. Los ``attrs`` de cada tabla (año, tipo de día, año y huella
  de los pesos) van en sus metadatos, y vuelven a ser ``attrs`` al releerla.
- ORQ-27. **Las laterales** (§7.1; AMB-1, AMB-2, AMB-12, AMB-14). En la unidad de cada año,
  ``ambiental.lateral_monitores`` con el panel entero (leído del disco con su huella una vez por proceso; AMB-2),
  ``anios`` = el año, ``h_ultima``, la política y los meses del año reducidos a los píxeles del fondo de las celdas de
  los monitores (AMB-14: cada fila sale sólo de su celda, su hora y su mes), para I y D y cada contaminante; cada parte
  va a ``ambiental/partes/lateral_<pol>_<variante>_<año>.parquet`` (insumo) con sus metadatos. La lateral entera
  (``ambiental/lateral_<pol>_<variante>.parquet``) es ``ambiental.unir_partes`` de las partes releídas del disco con su
  huella (PED-7, resuelto por I19): bit a bit lo que da una sola llamada sobre el panel entero (lo comprueba la
  prueba), sin otra pasada. En las corridas reales los paneles (bajo DATOS) los leen los trabajadores: deben estar en
  ``Cfg.permitidas``, como los meses (PED-11).
- ORQ-28. **El operador de la grilla** (§7.1; AMB-6). ``ambiental.operador_grilla`` en todas las celdas de
  ``celdas.parquet``, con la z_media de los estáticos de M2a y el entrenamiento de producción, en
  ``ambiental/operador_grilla.bin`` (insumo). Los trabajadores lo leen del disco con su huella, una vez por proceso.
- ORQ-29. **M6** (Anexo B; MC-30, A26, A28). La comparación de v2 (``ESQUEMA_COMPARACION_M6``) llega por la lista
  cerrada. La TF de contaminantes es una unidad por contaminante y variante, en este proceso, con
  ``tendencias.tf_contaminantes`` y la muestra de TEN-19 (las celdas de la grilla con w_ghs de 2020): a D siempre, y a
  I entera si algún grupo ambiental gana con B o AB; si no, la verificación de un mes (DEC-14). La fábrica de A26 se
  ata aquí (``ambiental.fabrica_tf_contaminantes`` con el operador de M5, los meses de la lista cerrada, los datos de
  producción, los escenarios de TEN-4 desde las horas válidas de 2000-2025 y los estáticos), y
  ``Cfg.fabrica_m6(contaminante, variante, base)`` es el punto de entrada de la fábrica de producción v2, que no está
  escrita: recibe ``base`` (``predecir`` → la fábrica de A26) y devuelve (fábrica, modelo). Sin ella, M6 no corre. Las
  ramas, con ``decision.ramas_m6`` y las ``EntradasDecision`` ambientales rehechas desde las tablas de M3-4 (DEC-16: la
  decisión rehecha debe dar los ganadores de ``decision.json``). Las negativas y el cerrojo son de I22.
- ORQ-30. **``decision_m6.json`` y el operador restringido** (§7.1, punto 3; §8; AMB-7). §8 pide que ``--m6`` escriba
  en ``decision_m6.json`` las rutas y huellas de ``salud/s6`` y de las laterales restringidas, y AMB-7 que el operador
  restringido lleve la huella de ``decision_m6.json``: es circular. Rige: ``m6/ramas_m6.json`` (la misma decisión, con
  las huellas de sus entradas) se escribe primero y el operador restringido cita su huella (``ramas_m6_sha256``, que
  I19 adoptó, AMB-7); ``decision_m6.json`` va al
  final, con la misma decisión y las huellas de las entradas, de ``ramas_m6.json``, de ``s6.json``, de las tablas de
  la S6 y del operador y las laterales vigentes (las de M5, o las restringidas si la rama 3 rige en algún
  contaminante). P-ORQ-2 queda resuelta con ``ramas_m6_sha256``.
- ORQ-31. **La S6** (§7.2, punto 5; §6.4). El ganador ambiental definitivo de (T, Td) es el restringido si la rama 3
  rige en algún contaminante; si no, el de ``decision.json``. Si difiere del agudo, ese candidato con sus
  hiperparámetros ambientales; si coinciden, el de menor S entre los demás de E1 de lo agudo (empate: el orden fijo de
  DEC-8), con sus hiperparámetros agudos; si no hay ninguno (E1 sin otro candidato, o vacío), «no aplica» y no hay
  tablas. Las tablas van en ``m6/salud/s6/meteo_<año>.parquet`` (insumo), en el día civil (pregunta P-ORQ-4), con las
  mismas celdas, pesos y filas que la civil de M5 («sobre filas idénticas»); ``producto`` corre con el uso «agudo»,
  que sólo valida que el candidato sea de salud. La regla, el candidato y el uso de los hiperparámetros van en
  ``m6/s6.json`` (resumen).
- ORQ-32. **Lo restringido** (rama 3; §6.4: «el restringido para todos»; P98). El operador con el ganador restringido
  (``restringido`` de ``ambiental.operador_grilla``) va en ``m6/ambiental/operador_grilla.bin`` y las cuatro laterales
  en ``m6/ambiental/``, armadas en la misma pasada anual de la S6 (ORQ-23, ORQ-27).
- ORQ-33. **Las fases** (§2.5 del diseño). ``FASES_M5``: negativas, entradas, representatividad, operador, anual,
  monitores, crónico y sello. ``FASES_M6``: negativas, comparación, TF de contaminantes, ramas, restringido, anual,
  monitores, registro y sello. Cambian las del esbozo de la primera fase (tres y seis).
- ORQ-34. **La huella de la corrida** (H12; §10: «Reanudar la misma corrida (misma etiqueta y huellas)»). Además de
  lo de ORQ-8, lleva la identidad de los umbrales (``sha256_json``, ``sha256_texto`` y ``sha256_texto_vigente``), la
  del código del paquete (el sha256 del JSON canónico {módulo: sha256} de sus ``*.py``, sin las pruebas) y la de las
  funciones de entrada (``negativas`` y ``fabrica_m6``: módulo, nombre y sha256 de su archivo fuente). Las unidades de
  la TF de contaminantes llevan además la de la fábrica. Otro código o otra fábrica es otra corrida.
- ORQ-35. **Una negativa no ata la carpeta** (H7). Abrir el avance no escribe nada; la cabecera de ``avance.jsonl``
  (y en M5 la línea de compuerta en la carpeta de M3-4) se escribe con ``Avance.iniciar()`` recién cuando las negativas
  pasaron (o en el primer registro). Una corrida que se niega no deja nada, y la misma carpeta corre después con la
  lista corregida. Una última línea truncada de ``avance.jsonl`` (un corte duro) da ``ErrorReanudacion`` (H18).
- ORQ-36. **Lo que viaja a los trabajadores** (H1; §8, «Memoria y procesos», «≤ 8 GB en la competencia», D2). El
  contexto lleva referencias (``_Ref``: ruta y sha256 de ``sha256.json`` o de la lista cerrada) y recetas, no tablas:
  la ``DatosCompetencia`` de producción se rearma del disco una vez por proceso, en el principal y en cada trabajador,
  con ``_datos_produccion`` sobre los mismos bytes (los mismos bits; S9 con 1, 2 y 8 procesos). Lo que corre en celdas
  (TF, M5, M6) la usa sin el fondo ni el clima de las estaciones (``_solo_celdas``: sólo los usan las filas de C, ya
  armadas, y las estaciones de prueba). La selección lee por demanda las tablas anchas de sus estaciones de prueba y
  sólo las columnas de la evaluación (33 B por fila en vez de 231). La TF rearma sus celdas y su operador; M5 y M6,
  sus celdas de salud, el operador de la grilla y los paneles. Medido en la red mínima (bytes serializados por
  trabajador, contexto): selección 20,2 MB → 16 KB, TF 17,6 MB → 29 KB, M5 anual 33,8 MB → 117 KB. Escalado a los
  datos reales (residuos ≈ 36 B por estación-hora, tablas anchas ≈ 127 B, fondo ≈ 28 B, filas de C ≈ 1,5 MB por
  estación y diseño): antes ≈ 13-14 GB por trabajador en la selección y ≈ 8-9 GB en la TF y en M5, más las copias del
  protocolo; ahora < 1 MB por la tubería (más las filas de pesos de su año, ≈ 20 MB, en cada unidad de M5), y en
  memoria lo que cada trabajador rearma (en la ola 5): ≈ 7-7,5 GB en la selección (residuos ≈ 1,9 GB, fondo ≈ 3,8 GB,
  filas de C ≈ 1-1,6 GB, tablas anchas de la prueba ≈ 0,2 GB), ≈ 4,5-6 GB en la TF y ≈ 4,5-7,5 GB en M5 (con el
  operador de la grilla, ≈ 1,3-2,6 GB, AMB-15). La ola 6 lo baja en la selección (ORQ-42, ORQ-43) y quita el fondo de
  las estaciones del pico de la TF, M5 y M6 (ORQ-42). Lo mide I21 a escala; pregunta P-ORQ-6 y PED-9.
- ORQ-37. **RR06 por años** (§2.6; H2). Lotes de un año (y, dentro del año, de meses contiguos), con el último día del
  mes anterior delante si es contiguo, para las ventanas de 6 h que cruzan el 1 de enero; ``sumas_lluvia_rr06`` con
  ``previas`` sólo llena lo que sigue NaN, así que es bit a bit un solo lote con todos los meses contiguos (lo comprueba
  la prueba): ≈ 2 GB por lote en vez de ≈ 56 GB.
- ORQ-38. **Los registros de las compuertas anteriores** (§10: «alguna huella … del registro de M2a difiere»; H5).
  M3-4 exige ``registro_m2a.json`` en la lista cerrada con su huella, y que cada huella que cita de una entrada que M3-4
  también lista sea la misma; M5, lo mismo con ``decision.json``; M6, con ``decision.json`` y el recibo de M5. Si no,
  se niega (antes de escribir nada). Pregunta P-ORQ-8 (de quién es esta negativa).
- ORQ-39. **Los manifiestos** (§2.1; H4). Los artefactos hallados en los manifiestos deben ser exactamente los de
  ``artefactos_evaluados``, sin repetir y cada uno en su estación; si no, M3-4 se detiene antes de normalizar (un
  defecto de la entrada, no un «no normalizable»).
- ORQ-40. **La cadena de huellas de M3-4** (§8; H9 a H11). La huella agregada de los manifiestos usados (el sha256 del
  JSON canónico {ruta por alias: sha256}) va bajo ``DMC/estaciones`` en ``decision.json``, en el registro y en el
  recibo; la política efectiva se escribe antes de ``decision.json``, que cita su huella; el registro de C5 se lee
  primero por la lista cerrada (``leer_entrada``).
- ORQ-41. **Más estrictas** (H13 a H16). En los modos reales (también M6), ``Cfg.recorte`` y ``Cfg.deriva`` vienen
  explícitos (sin omisión) y M2a exige ``conjuntos``; M2a informa las celdas con población (w_ghs > 0 en algún año de
  ``poblacion_celda_anio.parquet``, que pasa a ser entrada de M2a) sin vecino válido (§4.1); el umbral de 2.000 horas
  de la banda y de la distancia al entrenamiento cuenta todas las horas válidas (§5.3, 2000-2026; π^pob sigue por año
  2000-2025; pregunta P-ORQ-10); ``MESES_VALIDEZ`` sale de ``constantes`` y la ruta de la publicación del reloj, de
  ``politicas``. ``_codigo_fijado`` sólo usa ``permitir_cargados`` en el modo sintético (H6).
- ORQ-42. **El fondo en la selección** (ola 6; PED-10; §8, «≤ 8 GB en la competencia», D2). La receta de la selección
  (``_para_seleccion``) guarda de cada estación sólo las filas del fondo de los días de selección (mód ``SEL_MOD``, o
  ``SEL_MOD_RECORTE`` con ``Cfg.recorte``), que es todo lo que la selección lee de él (CAN-19 (5)): ≈ 1/11 del fondo
  (≈ 1/23 con el recorte). Cada unidad de un pliegue externo lee además del disco, con su sha256, el fondo entero de sus
  estaciones de prueba (``_fondo_de_prueba``), para predecir C en todas sus horas observadas y evaluar el producto en
  las horas de su tabla ancha: mientras dura la predicción y la evaluación lo pone en el fondo de la misma
  ``DatosCompetencia`` del proceso y al salir (también por un error) vuelve el de los días de selección
  (``_con_fondo_de_prueba``). No es una copia porque la caché de ``candidatos`` (CAN-19) es por ``DatosCompetencia`` y
  no depende del fondo: con una copia, cada unidad rehacía los r̄ de todas sus estaciones de entrenamiento (≈ +40 % de
  tiempo en una unidad de P2 del mundo medido). La producción no tiene estaciones de prueba. Las filas de C,
  que usan el fondo entero, se arman estación por estación al leer su fondo (``candidatos.filas_c`` de cada una sola,
  con su propia semilla: el mismo diccionario, en el mismo orden, con las mismas comprobaciones primero): ningún
  trabajador tiene a la vez el fondo entero de todas las estaciones, ni al armarse; tampoco los de la TF, M5 y M6
  (variante ligera), que antes lo cargaban entero y lo dejaban retenido en la memoria del proceso: con las horas
  reales, el armado de la ligera pasa de 8,6 a 5,0 GiB de pico y de ≈ 8,1 a ≈ 4,5 GiB vivos después. Ya nadie pide la
  completa en M3-4 (ORQ-44). Mismos bits: la unidad de un pliegue de P1, uno de P2 y la de producción, con y sin
  recorte, dan los mismos bytes que la de la ola 5 (la prueba la compara con una copia literal), y M3-4, M5 y M6 dan
  las mismas huellas que antes en el mundo de prueba (todo ``sha256.json`` salvo ``avance.jsonl``).
- ORQ-43. **Las predicciones de un pliegue externo** (ola 6; §8; D2). ``_unidad_pliegue`` ya no retiene las 30
  predicciones a la vez (≈ 3,1 GiB en un pliegue de P1 a escala real): las calcula en el orden de siempre, reduce cada
  una en cuanto sale a lo que la evaluación lee de ella (por estación de prueba: sus horas en int64, la corrección y el
  soporte; las horas, una vez por estación si son las mismas) y la suelta cuando ya la evaluó el último par que la
  usa. Cada par se evalúa apenas tiene las suyas (nunca hay más de 8 vivas, las de un par), con la misma cuenta
  (``_evaluar_par``), y lo de los pares se junta en el orden de los pares. Un error de predicción sale en su lugar,
  como antes; el de una evaluación, el del primer par que falla, después de todas las predicciones (antes se evaluaba
  después de predecir todo). Las filas de cada estación se separan con ``pd.factorize`` del código, una vez por
  predicción, en vez de comparar el código fila a fila por cada par, estación, candidato y variable: las mismas filas,
  en su orden. Medido con ORQ-42 en el mundo sintético de ``costo`` con las horas reales (579 estaciones, H = 234.120
  h, 51,7 M filas de residuos: residuos ≈ 1,9 GB, fondo ≈ 3,8 GB, filas de C ≈ 1,8 GB), un proceso por la receta como
  un trabajador: el pico de un pliegue de P1 (58 estaciones de prueba) baja de 12,7 a 7,1 GiB (pared 1.025 → 794 s) y
  el de uno de P2 (5) de 9,3 a 6,0 GiB (640 → 634 s), con los mismos bytes. Lo que queda: ≈ 5,4 GiB al armar la
  ``DatosCompetencia`` (≈ 4 GiB de residuos, filas de C, fondo de la selección y A, y ≈ 1,4 GiB que el armado de las
  filas de C deja de más), más ≈ 0,6 GiB de la selección y, en P1, ≈ 1,1 GiB de la prueba (su fondo entero y sus tablas
  anchas, ≈ 0,3 GiB cada uno, las predicciones vivas y las de ``candidatos`` al predecir). Con 3 y 6 años: P1 3,63 →
  3,22 y 4,81 → 3,60 GiB; P2 3,44 → 3,04 y 4,30 → 3,58 GiB.
- ORQ-44. **La memoria del principal de M3-4 y de M6** (ola 6; §8; P-ORQ-11). Antes, durante la selección el
  principal de M3-4 tenía las tablas anchas de todas las estaciones con todas sus columnas (≈ 231 B por fila: ≈ 12 GB a
  escala real), el fondo dos veces (el de los pasos 2-4 y el de la ``DatosCompetencia`` completa, ≈ 3,8 GB cada uno),
  los residuos dos veces (≈ 1,9 GB cada uno), las filas de C (≈ 1,8 GB) y lo que deja su armado (≈ 1,4 GiB): ≈ 25-27
  GB. Ahora el fondo de cada estación viaja como referencia a su unidad de control de calidad (``_unidad_estacion`` lo
  lee del disco) y el paso 6 lo lee de a una estación; de cada tabla ancha quedan sus metadatos y su referencia; los
  residuos y las horas válidas (``_horas_de_una``: estación por estación, lo mismo que con todas juntas) salen de a una
  estación con sólo sus columnas (``_ancha_de``); los residuos en memoria se sueltan después de escribirlos; el
  principal pide la variante ligera (con un proceso, la selección rearma la suya), y RR06 lee las tablas enteras de a
  una del disco (``_TablasAnchas``: ``qc_dmc_meteo`` exige el esquema entero, PED-12), a costa de leerlas en cada lote
  de un año (≈ 28 pasadas, ≈ 10-20 min más de pared en el principal, sobre ≈ 30 h). Queda ≈ 5-7 GiB: la
  ``DatosCompetencia`` ligera (≈ 5 GiB medidos al armarla, con las horas reales), más un año de ERA5-Land en RR06
  (≈ 2 GB) o los pesos y las celdas de la π. El principal de M6 lee de las tablas anchas sólo la hora y la validez
  (≈ 9 B por fila en vez de ≈ 231). Mismos bits: M3-4, M5 y M6 dan las mismas huellas que en la ola 5 en el mundo de
  prueba, y S9 sigue igual con 1, 2 y 8 procesos.
- ORQ-45. **Los procesos por fase** (D59, respuesta a P145; P146 y A39; §8: «M3-4 con 8 procesos [M0, D2]»).
  ``FASES_REPARTO`` nombra las fases que reparten sus unidades con ``procesos``, con los nombres de ``FASES_M34`` y
  ``FASES_M5``: en M3-4, «artefactos», «seleccion_y_prediccion» y «tendencias_y_finitud»; en M5, «representatividad» y
  «anual». ``Cfg.procesos_por_fase`` es None o exactamente {compuerta: {fase: n}} con esas compuertas y fases y n entero
  (no bool) de 1 a ``PROCESOS``, congelado en el orden de ``FASES_REPARTO``. Es obligatorio en los modos reales, como
  el recorte y la deriva: lo da el addendum de M1, desde la memoria medida por ``costo`` (el mayor número que cabe en
  cada fase; EMC5/D69 retira el tope individual fijo y conserva factibilidad física del grupo). En el sintético es None. Cada ``repartir`` de esas fases usa mín(procesos, n) (``_procesos_de_fases``);
  con None, ``procesos``, como antes. M6 sigue con ``Cfg.procesos``, porque D59 no lo nombra. El registro de M3-4 lleva
  «procesos_por_fase» = el de ``Cfg`` (el del addendum; null en el sintético), que no cambia entre 1, 2 y 8 procesos.
  EMC3-1 (D65): el recibo de M3-4 y el de M5 separa el «presupuesto» del uso observado en ``repartir``. Su entorno
  lleva «procesos_por_fase»: el máximo de procesos de ejecución de cada fase, la suma de trabajadores creados y el
  detalle ordenado de sus repartos (unidades pendientes, límite, procesos de ejecución y trabajadores creados).
  Un reparto en el principal cuenta 1 proceso y 0 trabajadores; vacío, 0 y 0. Una fase sin llamadas cuenta 0.
  «procesos» del entorno es el máximo de los repartos, no el límite configurado ni la suma de trabajadores de
  llamadas sucesivas. El alcance explícito es esta invocación, no un acumulado de intentos anteriores: al reanudar
  sólo se observa el trabajo pendiente. Los conteos se anidan bajo las claves admitidas por CEG-11, sin ampliarlas.
  No entra en la huella de la corrida (ORQ-8), ni cambia el presupuesto fijo del registro normativo de M3-4.
  Ningún bit científico cambia (S9); los recibos sí pueden diferir. M6 sigue con ``Cfg.procesos``.
Preguntas para el autor (P-ORQ-n; rige la más estricta): P-ORQ-1 (ORQ-19: §5.6 no se cumple entero mientras tanto;
propuesta: las coordenadas de las estaciones SINCA salen de «estaciones» de ``pliegues_v2_red2.json``, por código, y
las que no están ahí se declaran sin comparación); P-ORQ-2, resuelta (ORQ-30); P-ORQ-3, las dos pasadas de ORQ-23
(propuesta: que M2a guarde la t2m de los píxeles del reloj y M5 lea una sola vez); P-ORQ-4, el día de la
representatividad y de la S6 (rige el civil, el de la primaria; alternativa: las tres meteorologías); P-ORQ-5, los
centros de píxel sin celda cuando C gana un grupo ambiental (P84; rige detener; alternativas: la celda más cercana, o
NaN en esos píxeles; el revisor cree que ocurrirá con datos reales); P-ORQ-6, la memoria y D2, respondida por D59
(respuesta a P145: «Menos procesos en esa fase»; ORQ-45): la fase que no quepa en memoria con 8 procesos corre con el
mayor número que quepa, declarado en el addendum y en el registro de M3-4, y también en M5 (P146). Con ORQ-42 y ORQ-43,
la selección queda en ≈ 7,1 GiB por trabajador en P1 y ≈ 6,0 GiB en P2 en el mundo sintético con las horas reales;
P-ORQ-7, si una negativa antes de la frontera cuenta como corrida (propuesta: no; sólo queda en
``intentos_aplicar.jsonl``); P-ORQ-8, de quién es la negativa de los registros (ORQ-38; hoy de aquí, I22 la puede
mover a ``negativas_m34``); P-ORQ-9, el π del objetivo de la selección (P62: rige el del uso, ½ monitores + ½
población en lo ambiental, con las horas de 2000-2025); P-ORQ-10, las 2.000 horas de la banda (ORQ-41: rige la literal
de §5.3, todas las horas válidas); P-ORQ-11, si el tope de 8 GB por proceso de §8 («≤ 8 GB en la competencia») rige
también al proceso principal de M3-4, que a escala real tenía ≈ 25-27 GB durante la selección (ORQ-44; propuesta: sí;
con ORQ-44 queda en ≈ 5-7 GiB).
Pedidos (PED-n): PED-1 (I17, ORQ-9); PED-4 (I4 o I17: que ``v1/m2a/<sub>`` conserve las clases de ``estaticas/`` e
``insumos/``, o que ENT-4 deje de admitir la subcarpeta); PED-2 (I15: que ``PasadaTF.sumas_mes`` dé también los conteos de finitud del
escenario completo, que hoy se rehacen con ``correccion_mes`` y duplican ese costo); PED-3 (I16 o I15: una forma de
tomar un subconjunto de un ``tipos.OperadorPuntos``, que hoy se copia aquí con ``_sub_operador``); PED-5 (I15:
``PasadaTF`` indexa sus configuraciones por ``id(cfg)`` y no se puede pasar por pickle a un trabajador, aunque TEN-22
dice que los meses se reparten entre procesos: hoy se arma una vez en cada trabajador desde sus entradas); PED-6, PED-7
y PED-8 resueltos por I17, I19 e I18; PED-9 (I15: ``PasadaTF.correccion_mes`` por lote de celdas, para que la finitud de
E0 no arme R del mes en todas las celdas; hoy se cuenta por lotes sobre R entero, H3); PED-10, resuelto por I13
(CAN-19: ``candidatos`` lee el fondo sólo en las horas que usa) y aquí (ORQ-42); PED-11 (I22: en las corridas reales,
``Cfg.permitidas`` con los meses de ERA5-Land, los paneles de la red 2 y la DMC que leen los trabajadores); PED-12
(I12: que ``sumas_lluvia_rr06`` y ``validar_rr06`` comprueben sólo las columnas que leen, la hora y las de RR06, para
que el principal guarde sólo ésas de todas las estaciones en vez de releer las tablas enteras en cada año, ORQ-44).
Diferencias con el diseño (§3): ``Cfg.fabrica_m6`` (ORQ-29), ``Cfg.procesos_por_fase`` y ``FASES_REPARTO`` (ORQ-45;
D59: el diseño lanza 8 procesos en M3-4 y M5, §0 y §8), ``Avance(…, compuerta=, prefijo=)`` y
``Avance.iniciar`` (ORQ-20, ORQ-35), ``huella_del_codigo`` e ``identidad_funcion`` (ORQ-34) son nuevos; ``Cfg.recorte``
y ``Cfg.deriva`` valen None por omisión (ORQ-41); ``ENTRADAS_M2A`` suma ``pesos``; ``MODOS_REALES`` suma M6;
``correr_m6`` usa ``Cfg.procesos`` (§3 no le da ``procesos``); salidas que §8 no nombra: ``ambiental/partes/``,
``salud/cronico/meteo_<año>.parquet``, ``salud/representatividad/excluidas.json``, ``m6/ramas_m6.json`` y
``m6/s6.json``.
Depende de: los de las capas 0 a 5 salvo ``sintetico``, más ``salidas`` (§1 del diseño y ``test_meteo_combinada``).
"""
from __future__ import annotations

import contextlib
import copyreg
import dataclasses
import gzip
import inspect
import io
import json
import math
import os
import pickle
import platform
import re
import selectors
import signal
import struct
import subprocess
import sys
import threading
import traceback
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, Sequence

from meteo_combinada import ceguera, constantes, entorno, fijados, salidas, tipos
from meteo_combinada.tipos import Candidato, Grupo, Uso

# ---------------------------------------------------------------------------
# Fases, en el orden de §2.5 del diseño
# ---------------------------------------------------------------------------
FASES_M2A = ("negativas", "catalogo", "celdas", "altitud_pixeles", "pasada_horaria", "registro")
FASES_M34 = ("negativas", "politicas_de_lectura", "artefactos", "envoltorio_k4_marcas_alarmas", "residuos",
             "seleccion_y_prediccion", "metricas", "tendencias_y_finitud", "rr06_y_sinca", "produccion_y_decision",
             "sello")
FASES_M5 = ("negativas", "entradas", "representatividad", "operador", "anual", "monitores", "cronico", "sello")
FASES_M6 = ("negativas", "comparacion", "tf_contaminantes", "ramas", "restringido", "anual", "monitores", "registro",
            "sello")
# ORQ-45 (D59, A39): las fases que reparten sus unidades entre procesos (``repartir`` con ``procesos``), por compuerta,
# con los nombres de FASES_M34 y FASES_M5; ``Cfg.procesos_por_fase`` les pone un tope a cada una. M6 usa Cfg.procesos.
FASES_REPARTO = MappingProxyType({"m34": ("artefactos", "seleccion_y_prediccion", "tendencias_y_finitud"),
                                  "m5": ("representatividad", "anual")})

# §6.1: los cinco (uso, grupo) que decide M3-4.
PARES = ((Uso.AMBIENTAL.value, Grupo.T_TD.value), (Uso.AMBIENTAL.value, Grupo.U_V.value),
         (Uso.AMBIENTAL.value, Grupo.P.value), (Uso.AGUDO.value, Grupo.T_TD.value),
         (Uso.CRONICO.value, Grupo.T_TD.value))
MODOS_REALES = (tipos.Modo.ESTATICOS.value, tipos.Modo.APLICAR.value, tipos.Modo.PRODUCIR.value,
                tipos.Modo.M6.value)

# ORQ-1: qué es cada entrada (claves de Cfg.entradas).
ENTRADAS_M2A = ("catalogo_dmc", "catalogo_pixeles", "geopotencial", "altitud_pixeles", "meses_era5l", "h_ultima",
                "nasadem", "ghs", "celdas", "estaticas", "estaticas_lulc", "pesos")
ENTRADAS_M34 = ("m2a", "registro_c5", "catalogo_dmc", "catalogo_pixeles", "meses_era5l", "h_ultima", "celdas",
                "enlaces", "pesos", "red2")
ENTRADAS_M5 = ("m2a", "catalogo_pixeles", "meses_era5l", "h_ultima", "celdas", "enlaces", "pesos", "red2")    # ORQ-21
ENTRADAS_M6 = (*ENTRADAS_M5, "comparacion_m6")                                                               # ORQ-29

AVANCE = "avance.jsonl"
ESQUEMA_AVANCE = "meteo-combinada-avance/1"
REGISTRO_M2A = "registro_m2a.json"
REGISTRO_M34 = "registro_m34.json"
ESQUEMA_REGISTRO_M2A = "meteo-combinada-registro-m2a/1"
ESQUEMA_REGISTRO_M34 = "meteo-combinada-registro-m34/1"
CORRIDA_M2A = "m2a"
CATALOGO_DMC = "catalogo_nacional.json.gz"
LOTE_CELDAS = 4096                     # no-umbral: celdas por lote de M2a (memoria; no cambia ningún valor)
ETIQUETA_PRODUCCION = "produccion"     # ORQ-13: la única configuración de cada candidato en la TF
MESES_VALIDEZ = tuple(str(int(m)) for m in constantes.valor("PIXEL_MESES_VALIDEZ"))    # §4.1 (H16)
_PATRON_TESELA = re.compile(r"(?i)(?P<ns>[ns])(?P<lat>\d{2})(?P<ew>[ew])(?P<lon>\d{3})")
_PATRON_CODIGO = re.compile(r"\d{6}")
_PATRON_MES = re.compile(r"(?P<anio>\d{4})(?P<mes>0[1-9]|1[0-2])")
_PATRON_MES_GUION = re.compile(r"(?P<anio>\d{4})-(?P<mes>0[1-9]|1[0-2])")
N_VECINOS = 4                          # no-umbral: los 4 centros ERA5-Land que rodean un punto (§4.1)
_ALIAS_A_CAMPO = {v: k for k, v in entorno.ALIAS.items()}
_SHA = re.compile(r"[0-9a-f]{64}")
_CITADOS = 5                           # no-umbral: elementos citados en un mensaje
_LARGO = struct.Struct("<Q")
_ESPERA_S = 60                         # no-umbral: espera de un trabajador al cerrarse
_NICE = 10                             # no-umbral: prioridad de los trabajadores (§8: «nice»)
_SIN_CONTEXTO = object()
_HORAS_DIA = 24
# M5 y M6 (ORQ-20 a ORQ-33)
FASE_COMPUERTA = "compuerta"           # ORQ-20: la línea de avance.jsonl que ata una compuerta a la carpeta de M3-4
LOTE_CELDAS_SALUD = 2048               # no-umbral: celdas por lote de salud (memoria; PRO-2: no cambia ningún bit)
OPERADOR_GRILLA = "ambiental/operador_grilla.bin"                       # ORQ-28
EXCLUIDAS = "salud/representatividad/excluidas.json"                     # ORQ-24
CRONICO_ANUAL = "salud/cronico/temperatura_anual.parquet"                # §7.3; diseño §2.3
RAMAS_M6 = "ramas_m6.json"                                               # ORQ-30 (en m6/)
S6_M6 = "s6.json"                                                        # ORQ-31 (en m6/)
ESQUEMA_EXCLUIDAS = "meteo-combinada-representatividad/1"
ESQUEMA_TF_M6 = "meteo-combinada-tf-contaminantes/1"
ESQUEMA_S6 = "meteo-combinada-s6/1"
REGLA_S6_AMBIENTAL, REGLA_S6_SEGUNDO, REGLA_S6_NO_APLICA = "ambiental_definitivo", "segundo_agudo", "no_aplica"
# ORQ-26: la carpeta de cada (producto de salud, tipo de día).
CARPETA_SALUD = MappingProxyType({("agudo", "civil"): "salud/civil", ("agudo", "utc4"): "salud/utc4",
                                  ("agudo", "regional"): "salud/regional",
                                  ("representatividad", "civil"): "salud/representatividad",
                                  ("cronico", "civil"): "salud/cronico", ("s6", "civil"): "salud/s6"})


def _de_solo_lectura(d: dict) -> MappingProxyType:
    return MappingProxyType(d)


def _reducir_mappingproxy(m):
    return _de_solo_lectura, (dict(m),)


# ORQ-10: los contextos llevan objetos de ``tipos`` y ``umbrales`` con diccionarios de sólo lectura; viajan a los
# trabajadores como un diccionario y vuelven a ser de sólo lectura al llegar.
copyreg.pickle(MappingProxyType, _reducir_mappingproxy)


class ErrorOrquestacion(RuntimeError):
    """Una entrada que falta o no tiene su huella, una configuración inválida o una corrida que no se puede seguir."""


class ErrorReanudacion(ErrorOrquestacion):
    """La carpeta ya trae otra corrida, o una unidad no se puede reanudar (ORQ-8, ORQ-9)."""


class ErrorTrabajador(ErrorOrquestacion):
    """Una unidad falló en un trabajador (el texto trae su traza)."""


class InterrupcionSimulada(RuntimeError):
    """S9: la corrida se corta entre dos unidades (``Avance(interrumpir_tras=n)``)."""


class DetencionPorAlarma(ErrorOrquestacion):
    """§2.7: una alarma de Q1, Q1z, Q2 o Q3 detiene M3-4 (la única detención, §10). Se lanza después de escribir
    ``qc/resumen_qc.json``, la política efectiva y el registro, y de sellar; ``resultado`` trae lo de la corrida."""

    def __init__(self, mensaje: str, resultado: dict):
        super().__init__(mensaje)
        self.resultado = resultado


# ---------------------------------------------------------------------------
# Configuración (ORQ-1)
# ---------------------------------------------------------------------------
def _congelado(x):
    if isinstance(x, Mapping):
        return MappingProxyType({k: _congelado(v) for k, v in x.items()})
    if isinstance(x, list):
        return tuple(_congelado(v) for v in x)
    return x


@dataclass(frozen=True, eq=False)
class Cfg:
    """La configuración de una corrida (ORQ-1). ``entradas``: qué es cada insumo, por ruta por alias (o, en
    ``h_ultima``, la última hora con dato de ERA5-Land; en ``conjuntos``, {código: V | V2} o {"V": alias, "V2": alias});
    ``huellas``: la lista cerrada {ruta por alias: sha256}; ``etiqueta``: la de la corrida (M3-4); en M2a no se usa
    (ORQ-18)."""
    rutas: entorno.Rutas
    umbrales: Any
    entradas: Mapping[str, Any]
    huellas: Mapping[str, str]
    etiqueta: str | None = None
    procesos: int = 1
    modo: str = tipos.Modo.SINTETICO.value
    pares: tuple = PARES
    recorte: bool | None = None
    deriva: Mapping[str, bool] | None = None
    permitidas: tuple = ()
    negativas: Callable | None = None
    fabrica_m6: Callable | None = None
    procesos_por_fase: Mapping[str, Mapping[str, int]] | None = None

    def __post_init__(self) -> None:
        for nombre in ("negativas", "fabrica_m6"):
            if getattr(self, nombre) is not None and not callable(getattr(self, nombre)):
                raise ErrorOrquestacion(f"Cfg.{nombre}: una función o None")
        if not isinstance(self.rutas, entorno.Rutas):
            raise ErrorOrquestacion("Cfg.rutas: un entorno.Rutas")
        if isinstance(self.procesos, bool) or not isinstance(self.procesos, int) or self.procesos < 1:
            raise ErrorOrquestacion("Cfg.procesos: un entero ≥ 1")
        if self.modo not in {m.value for m in tipos.Modo}:
            raise ErrorOrquestacion(f"Cfg.modo desconocido: {self.modo!r}")
        pares = tuple((Uso(u).value, Grupo(g).value) for u, g in self.pares)
        if not pares or len(set(pares)) != len(pares) or not set(pares) <= set(PARES):
            raise ErrorOrquestacion("Cfg.pares: (uso, grupo) de §6.1, sin repetir")
        if self.modo in MODOS_REALES and set(pares) != set(PARES):
            raise ErrorOrquestacion("en una corrida real se deciden los cinco (uso, grupo) de §6.1 (ORQ-14)")
        object.__setattr__(self, "pares", tuple(p for p in PARES if p in pares))
        if self.modo in MODOS_REALES and (self.recorte is None or self.deriva is None):
            raise ErrorOrquestacion("en una corrida real, el recorte y la compuerta de deriva vienen explícitos del "
                                    "addendum de M1 (H13; con S6, B y AB fallan la deriva): Cfg.recorte y Cfg.deriva")
        if self.modo in MODOS_REALES and self.procesos_por_fase is None:
            raise ErrorOrquestacion("en una corrida real, los procesos de cada fase que reparte vienen explícitos del "
                                    "addendum de M1 (D59, A39): Cfg.procesos_por_fase")
        if self.procesos_por_fase is not None:
            object.__setattr__(self, "procesos_por_fase", _forma_procesos_por_fase(self.procesos_por_fase))
        if self.modo == tipos.Modo.ESTATICOS.value and "conjuntos" not in self.entradas:
            raise ErrorOrquestacion("M2a real: «conjuntos» explícito en Cfg.entradas (las listas V y V2 de RELOJ C2; "
                                    "H13)")
        if self.recorte is None:
            object.__setattr__(self, "recorte", False)
        if self.deriva is None:
            object.__setattr__(self, "deriva", {"B": True, "AB": True})
        if not isinstance(self.recorte, bool):
            raise ErrorOrquestacion("Cfg.recorte: True o False (lo fija el addendum de M1)")
        if set(self.deriva) != {"B", "AB"} or not all(isinstance(v, bool) for v in self.deriva.values()):
            raise ErrorOrquestacion("Cfg.deriva: {«B»: pasa, «AB»: pasa} de la compuerta de deriva de M1 (§5.7)")
        for alias_, sha in self.huellas.items():
            if not isinstance(alias_, str) or not ceguera.es_ruta_por_alias(alias_) or not _SHA.fullmatch(str(sha)):
                raise ErrorOrquestacion("Cfg.huellas: {ruta por alias: sha256}")
        object.__setattr__(self, "entradas", _congelado(dict(self.entradas)))
        object.__setattr__(self, "huellas", MappingProxyType(dict(self.huellas)))
        object.__setattr__(self, "deriva", MappingProxyType(dict(self.deriva)))
        object.__setattr__(self, "permitidas", tuple(str(p) for p in self.permitidas))

    @property
    def U(self):
        return self.umbrales

    def entrada(self, clave: str):
        if clave not in self.entradas:
            raise ErrorOrquestacion(f"falta la entrada «{clave}» en Cfg.entradas (ORQ-1)")
        return self.entradas[clave]


def _forma_procesos_por_fase(x) -> MappingProxyType:
    """ORQ-45 (D59, A39): ``Cfg.procesos_por_fase`` es {compuerta: {fase: n}} con exactamente las compuertas y las fases
    de ``FASES_REPARTO`` y n entero (no bool) de 1 a ``PROCESOS``; queda congelado, en el orden de ``FASES_REPARTO``."""
    tope = constantes.valor("PROCESOS")
    forma = ("Cfg.procesos_por_fase: None o {compuerta: {fase: n}} con exactamente las compuertas y las fases de "
             f"FASES_REPARTO ({ {c: list(f) for c, f in FASES_REPARTO.items()} }; D59, A39)")
    if not isinstance(x, Mapping) or set(x) != set(FASES_REPARTO):
        raise ErrorOrquestacion(forma)
    salida = {}
    for compuerta, fases in FASES_REPARTO.items():
        por_fase = x[compuerta]
        if not isinstance(por_fase, Mapping) or set(por_fase) != set(fases):
            raise ErrorOrquestacion(forma)
        for fase in fases:
            n = por_fase[fase]
            if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= tope:
                raise ErrorOrquestacion(f"Cfg.procesos_por_fase[{compuerta!r}][{fase!r}]: un entero de 1 a {tope} "
                                        f"(D59, A39), no {n!r}")
        salida[compuerta] = MappingProxyType({fase: int(por_fase[fase]) for fase in fases})
    return MappingProxyType(salida)


def _procesos_de_fases(cfg: Cfg, compuerta: str, procesos) -> dict[str, int]:
    """ORQ-45 (D59, A39): {fase: procesos} de las fases de la compuerta que reparten (``FASES_REPARTO``): mín(procesos,
    n) con los n de ``Cfg.procesos_por_fase``, o ``procesos`` si es None. Un ``procesos`` que no es un entero ≥ 1 pasa
    tal cual, para que ``repartir`` lo rechace como siempre."""
    if compuerta not in FASES_REPARTO:
        raise ErrorOrquestacion(f"compuerta sin fases que repartan: {compuerta!r} ({sorted(FASES_REPARTO)})")
    por_fase = cfg.procesos_por_fase
    valido = not isinstance(procesos, bool) and isinstance(procesos, int) and procesos >= 1
    if por_fase is None or not valido:
        return dict.fromkeys(FASES_REPARTO[compuerta], procesos)
    return {fase: min(procesos, por_fase[compuerta][fase]) for fase in FASES_REPARTO[compuerta]}


def _a_plano(x):
    if isinstance(x, Mapping):
        return {str(k): _a_plano(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_a_plano(v) for v in x]
    return x


_CODIGO: dict[str, str] = {}


def huella_del_codigo() -> str:
    """ORQ-34 (H12): el sha256 del JSON canónico {módulo: sha256} de los módulos de este paquete (sin las pruebas),
    leído una vez por proceso."""
    if not _CODIGO:
        carpeta = Path(__file__).resolve().parent
        _CODIGO["sha"] = entorno.sha256_bytes(entorno.json_canonico(
            {r.name: entorno.sha256_archivo(r) for r in sorted(carpeta.glob("*.py"))}))
    return _CODIGO["sha"]


def identidad_funcion(f) -> dict | None:
    """ORQ-34 (H12): el módulo, el nombre y el sha256 del archivo fuente de una función (o de la clase de un objeto
    que se llama); None sin función."""
    if f is None:
        return None
    objeto = f if (inspect.isfunction(f) or inspect.ismethod(f) or inspect.isclass(f)) else type(f)
    try:
        fuente = inspect.getsourcefile(objeto)
        sha = entorno.sha256_archivo(Path(fuente)) if fuente else None
    except (TypeError, OSError):
        sha = None
    return {"modulo": str(getattr(objeto, "__module__", "")), "nombre": str(getattr(objeto, "__qualname__", "")),
            "fuente_sha256": sha}


def _identidad_umbrales(U) -> dict:
    return {k: getattr(U, k, None) for k in ("sha256_json", "sha256_texto", "sha256_texto_vigente")}


def huella_de_corrida(cfg: Cfg, compuerta: str) -> str:
    """ORQ-8, ORQ-34: la huella de lo que hace única a una corrida (no los procesos: el resultado no depende de
    ellos): la compuerta, la etiqueta, las entradas y su lista cerrada, el modo, los pares, el recorte, la deriva, los
    umbrales, el código del paquete y las funciones de entrada (``negativas`` y ``fabrica_m6``)."""
    contenido = {"compuerta": compuerta, "etiqueta": cfg.etiqueta, "entradas": _a_plano(cfg.entradas),
                 "huellas": dict(sorted(cfg.huellas.items())), "modo": cfg.modo, "pares": [list(p) for p in cfg.pares],
                 "recorte": cfg.recorte, "deriva": dict(sorted(cfg.deriva.items())),
                 "umbrales": _identidad_umbrales(cfg.U), "codigo": huella_del_codigo(),
                 "negativas": identidad_funcion(cfg.negativas), "fabrica_m6": identidad_funcion(cfg.fabrica_m6)}
    return entorno.sha256_bytes(entorno.json_canonico(contenido))


def carpeta_de(cfg: Cfg, compuerta: str) -> Path:
    """La carpeta de la corrida (ENT-4; ORQ-18, ORQ-20): ``v1/m2a`` (sin subcarpeta), ``v1/<ETIQUETA>`` (M3-4 y M5)
    o ``v1/<ETIQUETA>/m6``."""
    if compuerta == "m2a":
        return entorno.carpeta_salida(cfg.rutas, "m2a")
    if compuerta not in ("m34", "m5", "m6"):
        raise ErrorOrquestacion(f"compuerta desconocida: {compuerta!r}")
    return entorno.carpeta_salida(cfg.rutas, compuerta, cfg.etiqueta)


# ---------------------------------------------------------------------------
# Fábrica de entradas (ORQ-2)
# ---------------------------------------------------------------------------
def ruta_de_alias(rutas: entorno.Rutas, texto: str) -> Path:
    """La ruta absoluta de una ruta por alias («GRILLA/celdas.parquet» → rutas.grilla/celdas.parquet)."""
    if not isinstance(texto, str) or "/" not in texto and texto not in _ALIAS_A_CAMPO:
        raise ErrorOrquestacion(f"no es una ruta por alias: {texto!r}")
    cabeza, _, resto = texto.partition("/")
    if cabeza not in _ALIAS_A_CAMPO:
        raise ErrorOrquestacion(f"alias desconocido: {cabeza!r}")
    partes = [p for p in resto.split("/") if p]
    if any(p in (".", "..") for p in partes):
        raise ErrorOrquestacion(f"una ruta por alias no lleva «.» ni «..»: {texto!r}")
    return Path(getattr(rutas, _ALIAS_A_CAMPO[cabeza])).joinpath(*partes)


def huella_archivo(ruta) -> str:
    """sha256 de un archivo, leído con ``open`` de Python (CEG-5)."""
    return entorno.sha256_archivo(Path(ruta))


def _exigir_huella(cfg: Cfg, alias_: str) -> str:
    sha = cfg.huellas.get(alias_)
    if sha is None:
        raise ErrorOrquestacion(f"{alias_}: no está en la lista cerrada de huellas (ORQ-1)")
    return sha


def leer_entrada(cfg: Cfg, alias_: str) -> bytes:
    """Los bytes de una entrada, con su huella frente a la lista cerrada (ORQ-1, ORQ-2)."""
    sha = _exigir_huella(cfg, alias_)
    with open(ruta_de_alias(cfg.rutas, alias_), "rb") as f:
        datos = f.read()
    if entorno.sha256_bytes(datos) != sha:
        raise ErrorOrquestacion(f"{alias_}: su sha256 no es el de la lista cerrada (§10)")
    return datos


def _parquet(datos: bytes):
    import pandas as pd
    return pd.read_parquet(io.BytesIO(datos))


def _leer_propio(ruta: Path, sha: str | None = None) -> bytes:
    """Un archivo de una salida de este paquete (M2a), con su sha256 si se da."""
    with open(ruta, "rb") as f:
        datos = f.read()
    if sha is not None and entorno.sha256_bytes(datos) != sha:
        raise ErrorOrquestacion(f"{ruta.name}: su sha256 no es el registrado (§10)")
    return datos


def leer_catalogo_dmc(datos: bytes):
    """ORQ-3: la tabla del catálogo DMC (``reloj_dmc.extraccion.COLUMNAS_CATALOGO_DMC``), textos tal cual."""
    import pandas as pd
    try:
        payload = json.loads(gzip.decompress(datos))
    except (OSError, EOFError, ValueError) as e:
        raise ErrorOrquestacion(f"catálogo DMC ilegible: {type(e).__name__}") from e
    estaciones = payload.get("stations") if isinstance(payload, dict) else None
    if not isinstance(estaciones, list):
        raise ErrorOrquestacion("el catálogo DMC no trae la lista «stations»")

    def texto(x):
        return x if isinstance(x, str) else None

    estratos = {"tipo": ("Tipo", "Tipo Estación", "Tipo de Estación"),
                "propietario": ("Propietario", "Institución", "Dueño"),
                "omm": ("Código OMM", "OMM", "Indicativo OMM", "Código WMO", "WMO"),
                "oaci": ("Código OACI", "OACI", "Indicativo OACI", "ICAO")}
    filas, vistos = [], set()
    for est in estaciones:
        if not isinstance(est, dict):
            raise ErrorOrquestacion("una estación del catálogo DMC no es un objeto")
        codigo = str(est.get("code", ""))
        if not _PATRON_CODIGO.fullmatch(codigo) or codigo in vistos:
            raise ErrorOrquestacion(f"código de estación inválido o repetido en el catálogo DMC: {codigo!r}")
        vistos.add(codigo)
        md = est.get("source_metadata") if isinstance(est.get("source_metadata"), dict) else {}
        fila = {"codigo": codigo, "nombre": texto(md.get("Nombre")), "lat_txt": texto(md.get("Latitud")),
                "lon_txt": texto(md.get("Longitud")), "alt_txt": texto(md.get("Altitud (Mts)"))}
        for campo, claves in estratos.items():
            fila[campo] = next((texto(md[c]) for c in claves if c in md), None)
        filas.append(fila)
    filas.sort(key=lambda f: f["codigo"])
    columnas = ("codigo", "nombre", "lat_txt", "lon_txt", "alt_txt", "tipo", "propietario", "omm", "oaci")
    return pd.DataFrame(filas, columns=list(columnas)).astype({c: "string" for c in columnas})


def leer_conjuntos(cfg: Cfg) -> dict[str, str]:
    """Código → «V» o «V2» (las listas de RELOJ C2); {} si la entrada falta (todas «N»)."""
    import pandas as pd
    valor = cfg.entradas.get("conjuntos")
    if valor is None:
        return {}
    if set(valor) <= {"V", "V2"} and all(isinstance(v, str) and "/" in v for v in valor.values()):
        salida: dict[str, str] = {}
        for conjunto in ("V", "V2"):
            if conjunto not in valor:
                continue
            tabla = pd.read_csv(io.BytesIO(leer_entrada(cfg, valor[conjunto])), dtype=str, keep_default_na=False)
            for c in tabla["codigo"].str.strip():
                if not _PATRON_CODIGO.fullmatch(c) or c in salida:
                    raise ErrorOrquestacion(f"código inválido o repetido en las listas de conjuntos: {c!r}")
                salida[c] = conjunto
        return salida
    salida = {str(c): str(v) for c, v in valor.items()}
    if not all(_PATRON_CODIGO.fullmatch(c) and v in ("V", "V2") for c, v in salida.items()):
        raise ErrorOrquestacion("conjuntos: {código de 6 dígitos: V | V2}")
    return salida


def _caja_tesela(nombre: str) -> dict[str, float] | None:
    """La caja de 1° de una tesela por su nombre («s34w071»: esquina suroeste en −34°, −71°; ORQ-4)."""
    m = _PATRON_TESELA.search(nombre)
    if m is None:
        return None
    lat = int(m["lat"]) * (-1 if m["ns"].lower() == "s" else 1)
    lon = int(m["lon"]) * (-1 if m["ew"].lower() == "w" else 1)
    return {"sur": float(lat), "norte": float(lat + 1), "oeste": float(lon), "este": float(lon + 1)}


class _Teselas:
    """ORQ-4: las teselas NASADEM de la lista, leídas una vez y sólo si su caja toca una ventana."""

    def __init__(self, cfg: Cfg):
        from meteo_combinada import estaticas_nasadem as EN
        self._EN, self._cfg = EN, cfg
        self.aliases = tuple(cfg.entrada("nasadem"))
        self._leidas: dict[str, Any] = {}

    def _leer(self, a: str):
        if a not in self._leidas:
            self._leidas[a] = self._EN.leer_tesela(ruta_de_alias(self._cfg.rutas, a), _exigir_huella(self._cfg, a))
        return self._leidas[a]

    def en(self, ventanas: Iterable[Mapping[str, float]]) -> list:
        ventanas = [v for v in ventanas if all(math.isfinite(float(x)) for x in v.values())]
        salida = []
        for a in self.aliases:
            caja = _caja_tesela(PurePosixPath(a).name)
            toca = caja is None or any(caja["sur"] <= v["lat_norte"] and v["lat_sur"] <= caja["norte"]
                                       and caja["oeste"] <= v["lon_este"] and v["lon_oeste"] <= caja["este"]
                                       for v in ventanas)
            if toca:
                t = self._leer(a)
                if any(t.i_sur / 3600 <= v["lat_norte"] and v["lat_sur"] <= t.i_norte / 3600
                       and t.j_oeste / 3600 <= v["lon_este"] and v["lon_oeste"] <= t.j_este / 3600 for v in ventanas):
                    salida.append(t)
        return salida

    @property
    def huellas(self) -> dict[str, str]:
        return {a: _exigir_huella(self._cfg, a) for a in self.aliases}


def infos_de_tabla(tabla) -> dict[str, tipos.InfoEstacion]:
    """``ESQUEMA_ESTACIONES_MC`` (``estaticas/estaciones.parquet``) → {código: InfoEstacion}."""
    import pandas as pd
    tipos.validar_esquema(tabla, tipos.ESQUEMA_ESTACIONES_MC, nombre="estaciones")
    salida = {}
    nombres = [f.name for f in dataclasses.fields(tipos.InfoEstacion)]
    for fila in tabla.to_dict("records"):
        valores = {}
        for n in nombres:
            x = fila[n]
            if x is pd.NA or x is None:
                x = None
            elif tipos.ESQUEMA_ESTACIONES_MC[n] in ("float64",):
                x = float(x)
            elif tipos.ESQUEMA_ESTACIONES_MC[n] in ("int32", "Int64"):
                x = int(x)
            elif tipos.ESQUEMA_ESTACIONES_MC[n] in ("bool", "boolean"):
                x = bool(x)
            else:
                x = str(x)
            valores[n] = x
        for n in ("utm_e", "utm_n", "lat", "lon", "z_cat", "rho_km", "z_s", "w0", "w1", "w2", "w3"):
            if valores[n] is None:
                valores[n] = math.nan
        valores["bloque"] = valores["bloque"] or ""
        salida[valores["codigo"]] = tipos.InfoEstacion(**valores)
    return salida


# ---------------------------------------------------------------------------
# avance.jsonl (ORQ-8)
# ---------------------------------------------------------------------------
class Avance:
    """``avance.jsonl`` de una corrida: una cabecera {avance, corrida, huella} y una línea por unidad hecha
    {fase, unidad, entrada, salida, archivos}. Sólo huellas y estado (§8). ``interrumpir_tras``: S9, la corrida se
    corta (``InterrupcionSimulada``) después de registrar esa cantidad de unidades nuevas."""

    def __init__(self, carpeta, *, corrida: str, huella: str, interrumpir_tras: int | None = None,
                 compuerta: str | None = None, prefijo: str = ""):
        self.carpeta = Path(carpeta)
        self.corrida, self.huella = str(corrida), str(huella)
        self.compuerta, self.prefijo = compuerta, str(prefijo)
        self._interrumpir, self._nuevas = interrumpir_tras, 0
        self.saltadas: list[str] = []
        self.hechas_ahora: list[str] = []
        self._unidades: dict[tuple[str, str], dict] = {}
        self._cabecera_pendiente, self._compuerta_pendiente = False, None
        ruta = self.carpeta / AVANCE
        if os.path.lexists(ruta):
            with open(ruta, "rb") as f:
                datos = f.read()
            lineas = datos.splitlines()
            if not lineas:
                raise ErrorReanudacion("avance.jsonl vacío: no se puede saber qué corrida es")
            if not datos.endswith(b"\n"):
                raise ErrorReanudacion("avance.jsonl termina en una línea truncada (un corte duro al escribirla): la "
                                       "reanudación no la repara (H18, SLD-8)")
            try:
                registros = [json.loads(x) for x in lineas]
            except ValueError as e:
                raise ErrorReanudacion("avance.jsonl trae una línea que no es JSON (H18)") from e
            cabeza = registros[0]
            if compuerta is None and cabeza != self._cabecera():
                raise ErrorReanudacion("la carpeta ya trae otra corrida (otra etiqueta o huellas): una corrida nueva "
                                       "exige una errata (§10)")
            if compuerta is not None and (set(cabeza) != {"avance", "corrida", "huella"}
                                          or cabeza["avance"] != ESQUEMA_AVANCE or cabeza["corrida"] != self.corrida):
                raise ErrorReanudacion(f"{compuerta}: la carpeta no trae la corrida {self.corrida} de M3-4 (ORQ-20)")
            for r in registros[1:]:
                if not isinstance(r, dict) or "fase" not in r or "unidad" not in r:
                    raise ErrorReanudacion("avance.jsonl trae una línea que no es de una unidad (H18)")
                self._unidades[(r["fase"], r["unidad"])] = r
        elif compuerta is not None:
            raise ErrorReanudacion(f"{compuerta} sigue a su M3-4 en la misma carpeta (ENT-4) y no hay avance.jsonl de "
                                   "M3-4 (ORQ-20)")
        else:
            self._cabecera_pendiente = True
        if compuerta is not None:
            propia = self._unidades.get((FASE_COMPUERTA, compuerta))
            if propia is None:
                self._compuerta_pendiente = {"fase": FASE_COMPUERTA, "unidad": compuerta, "entrada": self.huella,
                                             "salida": self.huella, "archivos": {}}
            elif propia.get("entrada") != self.huella:
                raise ErrorReanudacion(f"la carpeta ya trae otra corrida de {compuerta} (otras entradas o huellas): "
                                       "una corrida nueva exige una errata (§10; ORQ-20)")

    def _cabecera(self) -> dict:
        return {"avance": ESQUEMA_AVANCE, "corrida": self.corrida, "huella": self.huella}

    def iniciar(self) -> None:
        """ORQ-35 (H7): ata la carpeta a la corrida (la cabecera y, en M5, la línea de compuerta) recién cuando las
        negativas pasaron; una corrida que se niega no deja nada escrito. ``registrar`` lo llama también."""
        if self._cabecera_pendiente:
            salidas.agregar_linea(AVANCE, self._cabecera(), raiz=self.carpeta)
            self._cabecera_pendiente = False
        if self._compuerta_pendiente is not None:
            r = self._compuerta_pendiente
            salidas.agregar_linea(AVANCE, r, raiz=self.carpeta)
            self._unidades[(FASE_COMPUERTA, r["unidad"])] = r
            self._compuerta_pendiente = None

    def hecha(self, fase: str, unidad: str, entrada: str) -> dict | None:
        """La línea de la unidad si está hecha con esa huella de entrada y sus archivos siguen con su sha256."""
        r = self._unidades.get((fase, unidad))
        if r is None or r.get("entrada") != entrada or not r.get("archivos"):
            return None
        for nombre, sha in r["archivos"].items():
            ruta = self.carpeta / nombre
            parcial = ruta.with_name(ruta.name + salidas.SUFIJO_PARCIAL)
            if os.path.lexists(parcial):
                raise ErrorReanudacion(f"{nombre}: queda un «.part» de una escritura interrumpida (unidad {unidad}); "
                                       "la reanudación no lo borra (ORQ-9, P-SAL-8)")
            if not ruta.is_file() or huella_archivo(ruta) != sha:
                return None
        return r

    def parcial_pendiente(self, nombres: Iterable[str], unidad: str) -> None:
        """ORQ-9: un «.part» de una unidad que no está hecha detiene la reanudación."""
        for nombre in nombres:
            ruta = self.carpeta / nombre
            if os.path.lexists(ruta.with_name(ruta.name + salidas.SUFIJO_PARCIAL)):
                raise ErrorReanudacion(f"{nombre}: queda un «.part» de una escritura interrumpida (unidad {unidad}); "
                                       "la reanudación no lo borra (ORQ-9, P-SAL-8; PED-1)")

    def registrar(self, fase: str, unidad: str, entrada: str, archivos: Mapping[str, str]) -> str:
        self.iniciar()
        archivos = {str(k): str(v) for k, v in sorted(archivos.items())}
        salida = entorno.sha256_bytes(entorno.json_canonico(archivos))
        r = {"fase": fase, "unidad": unidad, "entrada": entrada, "salida": salida, "archivos": archivos}
        salidas.agregar_linea(AVANCE, r, raiz=self.carpeta)
        self._unidades[(fase, unidad)] = r
        self.hechas_ahora.append(unidad)
        self._nuevas += 1
        if self._interrumpir is not None and self._nuevas >= self._interrumpir:
            raise InterrupcionSimulada(f"corte simulado tras {self._nuevas} unidades (S9)")
        return salida


def abrir_avance(cfg: Cfg, compuerta: str, *, interrumpir_tras: int | None = None) -> Avance:
    """El ``Avance`` de la corrida de ``compuerta`` («m2a», «m34», «m5» o «m6») de ``cfg`` (ORQ-8, ORQ-20): M5 sigue
    el ``avance.jsonl`` de su M3-4, con su propia línea de compuerta; M6 lleva el suyo en ``m6/``."""
    corrida = CORRIDA_M2A if compuerta == "m2a" else cfg.etiqueta
    return Avance(carpeta_de(cfg, compuerta), corrida=corrida, huella=huella_de_corrida(cfg, compuerta),
                  interrumpir_tras=interrumpir_tras, compuerta="m5" if compuerta == "m5" else None,
                  prefijo="m6/" if compuerta == "m6" else "")


def _huella_unidad(**partes) -> str:
    return entorno.sha256_bytes(entorno.json_canonico(_a_plano(partes)))


def _escribir(avance: Avance, nombre: str, contenido, *, esquema=None, metadatos=None, clase=None) -> str:
    clase = clase or ceguera.clase_de_ruta(avance.prefijo + nombre)
    if clase is None:
        raise ErrorOrquestacion(f"{nombre}: sin clase fijada por la ruta")
    return salidas.escribir(nombre, contenido, clase=clase, esquema=esquema, raiz=avance.carpeta,
                            metadatos=metadatos)


# ---------------------------------------------------------------------------
# Reparto en procesos (ORQ-10)
# ---------------------------------------------------------------------------
def _escribir_todo(flujo, datos) -> None:
    vista = memoryview(datos)
    while len(vista):
        n = flujo.write(vista)
        vista = vista[n if n is not None else len(vista):]


def _enviar(flujo, obj=None, *, cuerpo: bytes | None = None) -> None:
    """Un mensaje del protocolo: su largo y su pickle (``cuerpo``, si ya está serializado), sin copiarlo (H1)."""
    if cuerpo is None:
        cuerpo = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
    _escribir_todo(flujo, _LARGO.pack(len(cuerpo)))
    _escribir_todo(flujo, cuerpo)
    flujo.flush()


def _leer_exacto(flujo, n: int) -> bytearray | None:
    """n bytes en un solo búfer, sin juntar trozos (H1)."""
    buf = bytearray(n)
    vista, leidos = memoryview(buf), 0
    while leidos < n:
        k = flujo.readinto(vista[leidos:])
        if not k:
            return None
        leidos += k
    return buf


def _recibir(flujo):
    cabeza = _leer_exacto(flujo, _LARGO.size)
    if cabeza is None:
        raise ErrorTrabajador("un trabajador terminó sin responder")
    (n,) = _LARGO.unpack(cabeza)
    cuerpo = _leer_exacto(flujo, n)
    if cuerpo is None:
        raise ErrorTrabajador("un trabajador terminó a mitad de un mensaje")
    return pickle.loads(cuerpo)


def _llamar(funcion, unidad, contexto):
    return funcion(unidad) if contexto is _SIN_CONTEXTO else funcion(unidad, contexto)


def _trabajador() -> None:
    """El bucle de un trabajador (ORQ-10): lee la función y el contexto, y después una unidad a la vez."""
    sys.dont_write_bytecode = True
    os.nice(_NICE)                      # §8: «nice» (H18)
    canal = os.fdopen(os.dup(1), "wb")  # no-escribe: la tubería del protocolo, no un archivo
    os.dup2(2, 1)
    entrada = sys.stdin.buffer
    try:
        funcion, contexto, con_contexto, permitidas = _recibir(entrada)
        contexto = contexto if con_contexto else _SIN_CONTEXTO
        hilos = entorno.fijar_hilos()
    except BaseException:                                  # noqa: BLE001 (se informa al principal)
        _enviar(canal, ("error", -1, traceback.format_exc()))
        return
    with ceguera.RegistroAccesos(("/Volumes",), bloquear=True, permitidas=permitidas), ceguera.SinRed():
        _enviar(canal, ("listo", os.getpid(), [b["hilos"] for b in hilos["bibliotecas"]]))
        while True:
            try:
                mensaje = _recibir(entrada)
            except ErrorTrabajador:
                return
            if mensaje is None:
                return
            indice, unidad = mensaje
            try:
                resultado = _llamar(funcion, unidad, contexto)
            except BaseException:                          # noqa: BLE001 (se informa al principal)
                _enviar(canal, ("error", indice, traceback.format_exc()))
                return
            _enviar(canal, ("ok", indice, resultado))


_CODIGO_TRABAJADOR = ("import sys; sys.dont_write_bytecode = True; sys.path.insert(0, sys.argv[1]); "
                      "from meteo_combinada import orquestacion; orquestacion._trabajador()")


def _entorno_hijos() -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    env.update({v: entorno.UN_HILO for v in entorno.VARIABLES_HILOS})
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _cerrar(procesos, pgid: int | None, *, matar: bool) -> None:
    for p in procesos:
        for flujo in (p.stdin, p.stdout):
            try:
                if flujo is not None:
                    flujo.close()
            except OSError:
                pass
    if matar and pgid is not None:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    for p in procesos:
        try:
            p.wait(timeout=_ESPERA_S)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()


def repartir(unidades, funcion, procesos: int, *, contexto=_SIN_CONTEXTO, al_terminar: Callable | None = None,
             permitidas: Sequence[str] = (), registro: list[dict] | None = None) -> list:
    """Resultados en el orden de las unidades (ORQ-10).

    ``funcion(unidad)`` o, con ``contexto``, ``funcion(unidad, contexto)``: una función de módulo (se pasa por
    referencia a los trabajadores) que no escribe. ``al_terminar(i, resultado)`` se llama en este proceso, en el orden de
    las unidades, y lo que devuelve reemplaza al resultado en la lista. Con ``procesos`` = 1, todo corre aquí.
    ``registro`` recibe una observación por llamada (EMC3-1): unidades pendientes, límite y procesos que reciben
    trabajo, separados de los trabajadores creados. En el principal cuenta 1 y 0 trabajadores; sin unidades, 0 y 0.
    Los conteos se actualizan al crear y asignar, incluso si después falla o se interrumpe el reparto."""
    unidades = list(unidades)
    if isinstance(procesos, bool) or not isinstance(procesos, int) or procesos < 1:
        raise ErrorOrquestacion("procesos: un entero ≥ 1")
    entorno.fijar_hilos()
    salida: list = [None] * len(unidades)
    uso = {"unidades": len(unidades), "limite": {"procesos": procesos}, "procesos": 0,
           "trabajadores_creados": {"procesos": 0}}
    if registro is not None:
        registro.append(uso)
    if procesos == 1 or len(unidades) <= 1:
        uso["procesos"] = int(bool(unidades))
        # H18: con un proceso, las unidades corren con el mismo bloqueo que en un trabajador
        with ceguera.RegistroAccesos(("/Volumes",), bloquear=True, permitidas=tuple(permitidas)), ceguera.SinRed():
            for i, u in enumerate(unidades):
                r = _llamar(funcion, u, contexto)
                salida[i] = al_terminar(i, r) if al_terminar is not None else r
        return salida
    n = min(procesos, len(unidades))
    raiz = str(Path(__file__).resolve().parents[1])
    lanzados: list[subprocess.Popen] = []
    pgid = None
    ok = False
    con = contexto is not _SIN_CONTEXTO
    inicial = pickle.dumps((funcion, contexto if con else None, con, tuple(permitidas)),
                           protocol=pickle.HIGHEST_PROTOCOL)          # H1: una sola vez para todos los trabajadores
    previo = None
    if threading.current_thread() is threading.main_thread():
        def _senal(numero, _marco):
            raise ErrorOrquestacion(f"señal {numero}: se cierra el grupo de trabajadores (§8, S10)")
        previo = signal.signal(signal.SIGTERM, _senal)                 # H18: SIGTERM al principal cierra el grupo
    try:
        for _ in range(n):
            p = subprocess.Popen([sys.executable, "-B", "-I", "-c", _CODIGO_TRABAJADOR, raiz],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0,
                                 env=_entorno_hijos(), process_group=0 if pgid is None else pgid)
            lanzados.append(p)
            uso["trabajadores_creados"]["procesos"] = len(lanzados)
            if pgid is None:
                pgid = p.pid
            _enviar(p.stdin, cuerpo=inicial)
        for p in lanzados:
            r = _recibir(p.stdout)
            if r[0] != "listo":
                raise ErrorTrabajador(f"un trabajador no pudo empezar:\n{r[2]}")
            if any(h != int(entorno.UN_HILO) for h in r[2]):
                raise ErrorTrabajador("un trabajador no quedó con los hilos en 1 (§8)")
        pendientes = list(range(len(unidades)))[::-1]
        listos: dict[int, Any] = {}
        siguiente = 0
        sel = selectors.DefaultSelector()
        for p in lanzados:
            if pendientes:
                i = pendientes.pop()
                _enviar(p.stdin, (i, unidades[i]))
                uso["procesos"] += 1
                sel.register(p.stdout, selectors.EVENT_READ, p)
        activos = len(sel.get_map())
        while activos:
            for clave, _ in sel.select():
                p = clave.data
                estado, i, r = _recibir(p.stdout)
                if estado != "ok":
                    raise ErrorTrabajador(f"la unidad {i} falló en un trabajador:\n{r}")
                listos[i] = r
                if pendientes:
                    j = pendientes.pop()
                    _enviar(p.stdin, (j, unidades[j]))
                else:
                    sel.unregister(p.stdout)
                    activos -= 1
                while siguiente in listos:
                    r_s = listos.pop(siguiente)
                    salida[siguiente] = al_terminar(siguiente, r_s) if al_terminar is not None else r_s
                    siguiente += 1
        sel.close()
        for p in lanzados:
            _enviar(p.stdin, None)
        ok = True
    finally:
        _cerrar(lanzados, pgid, matar=not ok)
        if previo is not None:
            signal.signal(signal.SIGTERM, previo)
    if pgid is not None:
        vivos = ceguera.procesos_hijos_vivos(grupos=[pgid])
        if vivos:
            raise ErrorOrquestacion(f"quedan {len(vivos)} procesos vivos del grupo de trabajadores (§8, S10)")
    return salida


# ---------------------------------------------------------------------------
# Ayudas de la ciencia
# ---------------------------------------------------------------------------
def _sub_operador(op: tipos.OperadorPuntos, indices) -> tipos.OperadorPuntos:
    """PED-3: las filas ``indices`` de un operador."""
    import numpy as np
    k = np.asarray(indices, dtype=np.int64)
    return tipos.OperadorPuntos(ids=op.ids[k], z=op.z[k], pix=op.pix[k], w=op.w[k], dz=op.dz[k],
                                respaldo=op.respaldo[k])


def _horas_mes(yyyymm: str):
    import numpy as np
    m = _PATRON_MES.fullmatch(yyyymm)
    inicio = np.datetime64(f"{m['anio']}-{m['mes']}", "M")
    epoca = np.datetime64("2000-01-01T00", "h")
    a = (inicio.astype("datetime64[h]") - epoca).astype(np.int64)
    b = ((inicio + 1).astype("datetime64[h]") - epoca).astype(np.int64)
    return int(a), int(b)


def _meses_ordenados(cfg: Cfg) -> list[tuple[str, str]]:
    meses = cfg.entrada("meses_era5l")
    claves = sorted(str(k) for k in meses)
    if not all(_PATRON_MES.fullmatch(k) for k in claves):
        raise ErrorOrquestacion("meses_era5l: {AAAAMM: ruta por alias}")
    return [(k, meses[k]) for k in claves]


def _h_ultima(cfg: Cfg) -> int:
    h = cfg.entrada("h_ultima")
    if isinstance(h, bool) or not isinstance(h, int):
        raise ErrorOrquestacion("h_ultima: la última hora con dato de ERA5-Land (entero, h)")
    return h


def _leer_mes(cfg: Cfg, alias_mes: str):
    from meteo_combinada import fondo_era5l
    mes = fondo_era5l.leer_mes(ruta_de_alias(cfg.rutas, alias_mes), sha256=_exigir_huella(cfg, alias_mes))
    fondo_era5l.comprobar_unidades(mes)
    if not mes.completo_hasta(_h_ultima(cfg)):
        raise ErrorOrquestacion(f"{alias_mes}: el mes no trae todas sus horas hasta la última con dato (FON-1)")
    return mes


def _sin_palabras(obj):
    """ORQ-16: «fondo» → «pixel_valido» en las claves y los textos de un registro de clase resumen."""
    if isinstance(obj, Mapping):
        return {_sin_palabras(k): _sin_palabras(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sin_palabras(v) for v in obj]
    if isinstance(obj, str):
        return obj.replace("fondo", "pixel_valido")
    return obj


def _sumar_declaraciones(a: Mapping, b: Mapping) -> dict:
    salida = dict(a)
    for k, v in b.items():
        if k in salida and isinstance(v, Mapping) and isinstance(salida[k], Mapping):
            salida[k] = _sumar_declaraciones(salida[k], v)
        elif k in salida and isinstance(v, int) and not isinstance(v, bool) and isinstance(salida[k], int):
            salida[k] = salida[k] + v
        elif k not in salida:
            salida[k] = v
        elif salida[k] != v:
            salida[k] = sorted({*_lista(salida[k]), *_lista(v)})
    return salida


def _lista(x):
    return list(x) if isinstance(x, (list, tuple)) else [x]


def _numeros_python(obj):
    import numpy as np
    if isinstance(obj, Mapping):
        return {str(k): _numeros_python(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_numeros_python(v) for v in obj]
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    return obj


def _entorno_recibo(procesos: int, fases: Mapping[str, int] | None = None, *,
                    repartos: Mapping[str, Sequence[Mapping]] | None = None) -> dict:
    """Versiones y uso efectivo de los repartos de esta invocación (EMC3-1; no acumula intentos anteriores).

    En M3-4/M5, ``fases`` son límites, nunca observaciones: exige ``repartos`` recogidos por ``repartir``. «procesos»
    resume el máximo por reparto (no suma concurrencia ni incluye al principal cuando sólo coordina); cada fase
    conserva el detalle y la suma de trabajadores creados entre sus llamadas. Una fase omitida por avance da 0 y
    detalle vacío. El presupuesto queda aparte; nada de esto entra en registros normativos ni huellas de entrada.
    Los conteos de trabajadores y límites se anidan bajo «procesos», admitida por CEG-11, sin ampliar su lista.
    Sin ``fases`` se conserva el entorno de M2a/M6."""
    if fases is not None and (repartos is None or set(repartos) != set(fases)):
        raise ErrorOrquestacion("el recibo exige repartos observados para cada fase; los límites no son uso efectivo")
    if fases is None and repartos is not None:
        raise ErrorOrquestacion("repartos sin los límites de sus fases")
    import numpy
    import pandas
    import pyarrow
    import scipy
    salida = {"python": platform.python_version(), "pandas": pandas.__version__,
              "numpy": numpy.__version__, "pyarrow": pyarrow.__version__, "scipy": scipy.__version__,
              "procesos": int(procesos)}
    if fases is not None:
        salida["presupuesto"] = {"procesos": int(procesos), "procesos_por_fase": {
            fase: {"procesos": int(n)} for fase, n in fases.items()}}
        salida["alcance"] = "repartos_de_esta_invocacion"
        salida["procesos_por_fase"] = {
            fase: {"procesos": max((r["procesos"] for r in repartos[fase]), default=0),
                   "trabajadores_creados": {"procesos": sum(r["trabajadores_creados"]["procesos"]
                                                           for r in repartos[fase])},
                   "repartos": _a_plano(repartos[fase])} for fase in fases}
        salida["procesos"] = max((r["procesos"] for r in salida["procesos_por_fase"].values()), default=0)
    return salida


# ---------------------------------------------------------------------------
# M2a (§10: «K1, K3, NASADEM, altitud poblada, z_E5L, climatologías del estado, fondo en las estaciones y conteo de
# bloques de P2»)
# ---------------------------------------------------------------------------
def _negativas(cfg: Cfg, claves: Sequence[str]) -> list[str]:
    fallas = list(cfg.negativas(cfg)) if cfg.negativas is not None else []
    for clave in claves:
        if clave not in cfg.entradas:
            fallas.append(f"falta la entrada «{clave}»")
            continue
        valor = cfg.entradas[clave]
        valores = (valor.values() if isinstance(valor, Mapping) else valor if isinstance(valor, (list, tuple))
                   else [valor])
        for v in valores:
            if isinstance(v, Mapping):
                v = list(v.values())
            for a in _lista(v):
                if not isinstance(a, str) or "/" not in a or clave == "m2a":
                    continue
                if a not in cfg.huellas:
                    fallas.append(f"{a}: no está en la lista cerrada")
                    continue
                ruta = ruta_de_alias(cfg.rutas, a)
                if not ruta.is_file():
                    fallas.append(f"{a}: no existe")
                elif huella_archivo(ruta) != cfg.huellas[a]:
                    fallas.append(f"{a}: su sha256 difiere de la lista cerrada")
    return fallas


def _negativas_registro(cfg: Cfg, carpeta_leida: Mapping, nombre: str, que: str) -> list[str]:
    """ORQ-38 (H5; §10: «alguna huella de la lista cerrada del addendum de M1 o del registro de M2a difiere»): el
    registro de la compuerta anterior (``registro_m2a.json``, ``decision.json`` o ``recibo_corrida.json``) debe estar
    en la lista cerrada con su huella, y cada huella que cita de una entrada que esta corrida también lista debe ser la
    misma."""
    alias_ = entorno.alias(carpeta_leida["carpeta"] / nombre, cfg.rutas)
    if nombre == salidas.RECIBO:
        datos = _leer_propio(carpeta_leida["carpeta"] / nombre)
    else:
        datos = carpeta_leida["leer"](nombre)
    fallas = []
    sha = entorno.sha256_bytes(datos)
    if alias_ not in cfg.huellas:
        fallas.append(f"{alias_}: el registro de {que} no está en la lista cerrada (H5)")
    elif cfg.huellas[alias_] != sha:
        fallas.append(f"{alias_}: su sha256 difiere de la lista cerrada (H5)")
    citadas = json.loads(datos).get("huellas", {})
    for a in sorted(set(citadas) & set(cfg.huellas)):
        valor = citadas[a]
        valor = valor.get("sha256") if isinstance(valor, Mapping) else valor
        if valor != cfg.huellas[a]:
            fallas.append(f"{a}: su sha256 en la lista cerrada difiere de la que registró {que} (§10; H5)")
    return fallas


def correr_m2a(cfg, *, avance) -> dict:
    """M2a (§2.5 del diseño; §10): estáticos de estaciones y celdas, z_E5L, la pasada por ERA5-Land y el registro.
    Devuelve el registro (lo que va a ``registro_m2a.json``) y las huellas escritas."""
    import numpy as np
    import pandas as pd
    from meteo_combinada import estaticas_nasadem as EN
    from meteo_combinada import fondo_era5l, particiones

    U = cfg.U
    fases: list[str] = []
    # 1. negativas: primero lo que no son meses; la alineación de z_E5L (S13) antes de abrir ningún mes (ORQ-5);
    # después las huellas de los meses; y recién entonces la carpeta queda atada (ORQ-35, H7)
    fallas = _negativas(cfg, [k for k in ENTRADAS_M2A if k != "meses_era5l"])
    if fallas:
        raise ErrorOrquestacion("M2a se niega a correr: " + "; ".join(fallas[:_CITADOS]))
    geo = fondo_era5l.leer_geopotencial(ruta_de_alias(cfg.rutas, cfg.entrada("geopotencial")),
                                        sha256=_exigir_huella(cfg, cfg.entrada("geopotencial")))
    cat_pix = _parquet(leer_entrada(cfg, cfg.entrada("catalogo_pixeles")))
    altitud = _parquet(leer_entrada(cfg, cfg.entrada("altitud_pixeles")))
    pid = cat_pix["pixel_id"].to_numpy(np.int64)
    vacio = pd.DataFrame({"pixel_id": pid, "z_nasadem": np.nan, "frac_nasadem": 0.0})
    sp_nan = pd.Series(np.nan, index=pid)
    z_crudo = fondo_era5l.z_e5l(geo, cat_pix, vacio, sp_nan, U, validos=np.array([], dtype=np.int64))
    fondo_era5l.comprobar_alineacion(z_crudo, altitud)
    fallas = _negativas(cfg, ["meses_era5l"])
    if fallas:
        raise ErrorOrquestacion("M2a se niega a correr: " + "; ".join(fallas[:_CITADOS]))
    avance.iniciar()
    fases.append("negativas")
    # 2. catálogo: InfoEstacion con K1 y K3 (A8), grupos y bloques de P2
    catalogo = leer_catalogo_dmc(leer_entrada(cfg, cfg.entrada("catalogo_dmc")))
    conjuntos = leer_conjuntos(cfg)
    celdas = _parquet(leer_entrada(cfg, cfg.entrada("celdas")))
    teselas = _Teselas(cfg)
    ventanas_k3 = []
    for f in catalogo.itertuples(index=False):
        lat = EN.interpretar_coordenada(None if f.lat_txt is pd.NA else f.lat_txt, "lat")
        lon = EN.interpretar_coordenada(None if f.lon_txt is pd.NA else f.lon_txt, "lon")
        rho = EN.rho_km(None if f.lat_txt is pd.NA else f.lat_txt, None if f.lon_txt is pd.NA else f.lon_txt, U)
        if lat is not None and lon is not None and math.isfinite(rho):
            ventanas_k3.append(EN.ventana_k3(lat, lon, rho))
    infos = EN.info_estaciones(catalogo, celdas, teselas.en(ventanas_k3), U,
                               macrozona_region=fijados.macrozona_region(entorno.rutas_reales().ap),
                               conjuntos=conjuntos)
    codigos = sorted(infos)
    grupos = particiones.grupos_mismo_sitio(infos, U)
    con_coord = [c for c in codigos if math.isfinite(infos[c].lat) and math.isfinite(infos[c].lon)]
    bloques = dict(zip(con_coord, (str(b) for b in particiones.bloque(
        np.array([infos[c].lat for c in con_coord]), np.array([infos[c].lon for c in con_coord]), U))))
    infos = {c: dataclasses.replace(infos[c], grupo=grupos.get(c, infos[c].grupo), bloque=bloques.get(c, ""))
             for c in codigos}
    fases.append("catalogo")
    # 3. celdas (los estáticos; z_e5l se agrega en la fase 5, ORQ-7)
    estaticas_v1 = _parquet(leer_entrada(cfg, cfg.entrada("estaticas")))
    lulc = _parquet(leer_entrada(cfg, cfg.entrada("estaticas_lulc")))
    ghs_alias = tuple(cfg.entrada("ghs"))
    ghs = [EN.leer_ghs(ruta_de_alias(cfg.rutas, a), _exigir_huella(cfg, a)) for a in ghs_alias] or None
    entrada_celdas = _huella_unidad(celdas=cfg.huellas[cfg.entrada("celdas")],
                                    estaticas=cfg.huellas[cfg.entrada("estaticas")],
                                    lulc=cfg.huellas[cfg.entrada("estaticas_lulc")], nasadem=teselas.huellas,
                                    ghs={a: cfg.huellas[a] for a in ghs_alias})
    partes, declaraciones = [], {}
    for i in range(0, len(celdas), LOTE_CELDAS):
        lote = celdas.iloc[i:i + LOTE_CELDAS].reset_index(drop=True)
        est = EN.estaticos_celdas(lote, teselas.en([EN.ventana_necesaria(lote)]), ghs, estaticas_v1, lulc, U)
        declaraciones = _sumar_declaraciones(declaraciones, dict(est.attrs.get("declaraciones", {})))
        partes.append(est)
    estaticos = pd.concat(partes, ignore_index=True)
    # las teselas GHS que usaron los lotes, por su ruta por alias y frente a la lista cerrada (pendiente de la ola 2)
    usadas = set(_lista(declaraciones.pop("huellas_ghs", ())))
    de_ghs = {cfg.huellas[a]: a for a in ghs_alias}
    if not usadas <= set(de_ghs):
        raise ErrorOrquestacion("una tesela GHS-POP usada no está en la lista cerrada (§8, «Cadena de huellas»)")
    if usadas:
        declaraciones["huellas_ghs"] = {de_ghs[s]: s for s in sorted(usadas)}
    fases.append("celdas")
    # 4. z_E5L (la alineación del geopotencial crudo ya se comprobó en las negativas, antes de abrir ningún mes)
    meses = _meses_ordenados(cfg)
    por_mes = dict(meses)
    faltan = [m for m in MESES_VALIDEZ if m not in por_mes]
    if faltan:
        raise ErrorOrquestacion(f"faltan los meses de la regla de píxeles válidos: {faltan} (§4.1)")
    validos = fondo_era5l.pixeles_validos({m: _leer_mes(cfg, por_mes[m]) for m in MESES_VALIDEZ})
    ventana_pix = {"lat_norte": float(np.max(cat_pix["cell_north"])), "lat_sur": float(np.min(cat_pix["cell_south"])),
                   "lon_oeste": float(np.min(cat_pix["cell_west"])), "lon_este": float(np.max(cat_pix["cell_east"]))}
    nasadem_pix = EN.nasadem_en_pixeles(cat_pix, teselas.en([ventana_pix]))
    z_prov = fondo_era5l.z_e5l(geo, cat_pix, nasadem_pix, sp_nan, U, validos=np.array([], dtype=np.int64))
    hipso = np.isin(pid, validos) & ~np.isfinite(z_prov["z_e5l"].to_numpy(np.float64))
    fases.append("altitud_pixeles")
    # 5. pasada por ERA5-Land (ORQ-5, ORQ-6): una o dos
    entrada_pasada = _huella_unidad(meses={m: cfg.huellas[a] for m, a in meses}, h_ultima=_h_ultima(cfg),
                                    geopotencial=cfg.huellas[cfg.entrada("geopotencial")],
                                    catalogo=cfg.huellas[cfg.entrada("catalogo_pixeles")],
                                    catalogo_dmc=cfg.huellas[cfg.entrada("catalogo_dmc")], nasadem=teselas.huellas,
                                    celdas=cfg.huellas[cfg.entrada("celdas")])
    hecha = avance.hecha("pasada_horaria", "pasada", entrada_pasada)
    z_ruta, clima_ruta = "estaticas/z_e5l.parquet", "insumos/clima_estado.parquet"
    if hecha is None:
        archivos = _pasada_m2a(cfg, avance, meses, infos, cat_pix, validos, geo, nasadem_pix, z_prov, bool(hipso.any()))
        avance.registrar("pasada_horaria", "pasada", entrada_pasada, archivos)
        hecha = avance.hecha("pasada_horaria", "pasada", entrada_pasada)
    else:
        avance.saltadas.append("pasada")
    z_tabla = _parquet(_leer_propio(avance.carpeta / z_ruta, hecha["archivos"][z_ruta]))
    clima = _parquet(_leer_propio(avance.carpeta / clima_ruta, hecha["archivos"][clima_ruta]))
    renormalizadas = dict(clima.attrs.get("metadatos", {}))
    validos = z_tabla.loc[z_tabla["valido"].to_numpy(bool), "pixel_id"].to_numpy(np.int64)
    # el operador de las estaciones (el mismo que usó la pasada) y sus columnas en InfoEstacion (A8)
    op_est = _operador_estaciones(infos, cat_pix, validos, z_tabla, U)
    cols = fondo_era5l.columnas_operador(op_est).set_index("id")
    nuevos = {}
    for c in codigos:
        fila = cols.loc[c]
        sin_fondo = bool(fila["sin_fondo"])
        excl, motivo = infos[c].excluida, infos[c].motivo
        if sin_fondo and not excl:
            excl, motivo = True, tipos.MotivoExclusion.SIN_FONDO.value
        nuevos[c] = dataclasses.replace(
            infos[c], **{f"pix{k}": int(fila[f"pix{k}"]) for k in range(N_VECINOS)},
            **{f"w{k}": float(fila[f"w{k}"]) for k in range(N_VECINOS)}, respaldo_16km=bool(fila["respaldo_16km"]),
            sin_fondo=sin_fondo, excluida=excl, motivo=motivo)
    infos = nuevos
    fases.append("pasada_horaria")
    # celdas con z_e5l (ORQ-7) y estaciones
    op_cel = fondo_era5l.operador(celdas["lat"].to_numpy(np.float64), celdas["lon"].to_numpy(np.float64),
                                  estaticos["z_media"].to_numpy(np.float64), cat_pix, validos, z_tabla, U,
                                  ids=celdas["celda"].to_numpy(np.int64))
    z_de = dict(zip(z_tabla["pixel_id"].to_numpy(np.int64), z_tabla["z_e5l"].to_numpy(np.float64)))
    z_cel = np.full(len(celdas), np.nan)
    for i in range(len(celdas)):
        pix, w = op_cel.pix[i], op_cel.w[i]
        if (pix >= 0).any():
            z_cel[i] = sum(float(w[k]) * z_de[int(pix[k])] for k in range(N_VECINOS) if pix[k] >= 0)
    estaticos_c = estaticos.copy()
    estaticos_c[tipos.COLUMNA_Z_E5L] = z_cel
    estaticos_c = estaticos_c.astype(dict(tipos.ESQUEMA_ESTATICAS_CELDA_C))
    estaticos_c.attrs = {"esquema": tipos.ESQUEMA_ESTATICAS_CELDA_C.version}
    sha_cel = _unidad_simple(avance, "celdas", "celdas", _huella_unidad(base=entrada_celdas, pasada=hecha["salida"]),
                             "estaticas/celdas.parquet", estaticos_c, tipos.ESQUEMA_ESTATICAS_CELDA_C)
    tabla_est = EN.tabla_estaciones(infos)
    tabla_est.attrs = {"esquema": tipos.ESQUEMA_ESTACIONES_MC.version}
    sha_est = _unidad_simple(avance, "estaciones", "estaciones",
                             _huella_unidad(catalogo=cfg.huellas[cfg.entrada("catalogo_dmc")], pasada=hecha["salida"],
                                            nasadem=teselas.huellas, conjuntos=_a_plano(conjuntos)),
                             "estaticas/estaciones.parquet", tabla_est, tipos.ESQUEMA_ESTACIONES_MC)
    # 6. registro (resumen, ORQ-16) y sello
    # H14 (§4.1: «M2a informa las celdas con población que quedan sin fondo»): con población = w_ghs > 0 en algún
    # año de poblacion_celda_anio.parquet
    sin_vecino = (op_cel.pix < 0).all(axis=1)
    pesos = _parquet(leer_entrada(cfg, cfg.entrada("pesos")))
    pobladas = set(pesos.loc[(pesos["w_ghs"].to_numpy(np.float64) > 0), "celda"].astype(np.int64).tolist())
    con_poblacion = np.isin(celdas["celda"].to_numpy(np.int64), np.array(sorted(pobladas), dtype=np.int64))
    pobladas_sin = int((sin_vecino & con_poblacion).sum())
    entran = [c for c in codigos if not infos[c].excluida]
    casos = z_tabla.loc[z_tabla["valido"].to_numpy(bool), "caso"].astype(str).value_counts()
    registro = {
        "esquema": ESQUEMA_REGISTRO_M2A,
        "estaciones": EN.declaraciones_estaciones(infos),
        "bloques_p2": len({infos[c].bloque for c in entran}),
        "grupos": len({infos[c].grupo for c in entran}),
        "celdas": {"total": int(len(celdas)), "sin_vecino_valido": int(sin_vecino.sum()),
                   "con_poblacion": int(con_poblacion.sum()), "con_poblacion_sin_vecino_valido": pobladas_sin,
                   "declaraciones": declaraciones},
        "pixeles": {"validos": int(len(validos)), "por_caso": {str(k): int(v) for k, v in sorted(casos.items())},
                    "dif_mayor_50m": int(z_tabla["dif_mayor_50m"].sum())},
        "renormalizadas": renormalizadas,
        "pasadas": 2 if bool(hipso.any()) else 1,
        "huellas": {**dict(sorted(cfg.huellas.items())),
                    **{entorno.alias(avance.carpeta / n, cfg.rutas): s for n, s in sorted(hecha["archivos"].items())},
                    entorno.alias(avance.carpeta / "estaticas/celdas.parquet", cfg.rutas): sha_cel,
                    entorno.alias(avance.carpeta / "estaticas/estaciones.parquet", cfg.rutas): sha_est},
        "fases": [*fases, "registro"],
    }
    registro = _sin_palabras(_numeros_python(registro))
    sha_reg = _escribir(avance, REGISTRO_M2A, registro)
    salidas.sellar_corrida(avance.carpeta, dict(cfg.huellas), _entorno_recibo(1), rutas=cfg.rutas)
    return {"registro": registro, "registro_sha256": sha_reg, "carpeta": avance.carpeta, "infos": infos}


def _unidad_simple(avance: Avance, fase: str, unidad: str, entrada: str, nombre: str, tabla, esquema) -> str:
    hecha = avance.hecha(fase, unidad, entrada)
    if hecha is not None:
        avance.saltadas.append(unidad)
        return hecha["archivos"][nombre]
    avance.parcial_pendiente([nombre], unidad)
    sha = _escribir(avance, nombre, tabla, esquema=esquema)
    avance.registrar(fase, unidad, entrada, {nombre: sha})
    return sha


def _operador_estaciones(infos, cat_pix, validos, z_tabla, U):
    import numpy as np
    from meteo_combinada import fondo_era5l
    codigos = sorted(infos)
    return fondo_era5l.operador(np.array([infos[c].lat for c in codigos]), np.array([infos[c].lon for c in codigos]),
                                np.array([infos[c].z_s for c in codigos]), cat_pix, validos, z_tabla, U,
                                ids=np.array(codigos, dtype=object))


def _pasada_m2a(cfg, avance, meses, infos, cat_pix, validos, geo, nasadem_pix, z_prov, dos_pasadas: bool) -> dict:
    """ORQ-5 y ORQ-6: el fondo en las estaciones, las climatologías del estado y sp̄; escribe sus tres salidas."""
    import numpy as np
    from meteo_combinada import fondo_era5l
    U = cfg.U
    codigos = sorted(infos)
    acum = None
    if dos_pasadas:
        for _, a in meses:
            mes = _leer_mes(cfg, a)
            acum = acum or fondo_era5l.acumulador_estado(mes.pixel_id)
            fondo_era5l.climatologias_estado(acum, mes)
        z_tabla = fondo_era5l.z_e5l(geo, cat_pix, nasadem_pix, fondo_era5l.sp_medio_hpa(acum), U, validos=validos)
    else:
        sp_nan = z_prov.set_index("pixel_id")["z_hipso"].astype(np.float64) * np.nan
        z_tabla = fondo_era5l.z_e5l(geo, cat_pix, nasadem_pix, sp_nan, U, validos=validos)
    op = _operador_estaciones(infos, cat_pix, validos, z_tabla, U)
    horas, campos, renorm = [], {c: [] for c in fondo_era5l.CAMPOS_F}, 0
    for _, a in meses:
        mes = _leer_mes(cfg, a)
        if not dos_pasadas:
            acum = acum or fondo_era5l.acumulador_estado(mes.pixel_id)
            fondo_era5l.climatologias_estado(acum, mes)
        F = fondo_era5l.campos_fondo(mes, op, U)
        renorm += int(np.asarray(F["renormalizada"]).sum())
        horas.append(np.asarray(mes.tiempos, dtype=np.int64))
        for c in fondo_era5l.CAMPOS_F:
            campos[c].append(np.asarray(F[c], dtype=np.float64))
    if not dos_pasadas:
        z_final = fondo_era5l.z_e5l(geo, cat_pix, nasadem_pix, fondo_era5l.sp_medio_hpa(acum), U, validos=validos)
        a_val = z_final.set_index("pixel_id").loc[validos, "z_e5l"].to_numpy(np.float64)
        b_val = z_tabla.set_index("pixel_id").loc[validos, "z_e5l"].to_numpy(np.float64)
        if not np.array_equal(a_val, b_val):
            raise ErrorOrquestacion("z_E5L de los píxeles válidos cambió con sp̄ en una sola pasada (ORQ-5)")
        z_tabla = z_final
    h = np.concatenate(horas)
    F = {c: np.concatenate(v, axis=0) for c, v in campos.items()}
    archivos = {}
    for j, c in enumerate(codigos):
        col = {k: F[k][:, j] for k in fondo_era5l.CAMPOS_F}
        if not np.isfinite(col["u_F"]).any():
            continue                                 # sin fondo (A8): sin archivo
        tabla = fondo_era5l.tabla_puntos(h, col)
        nombre = f"insumos/puntos_estacion/{c}.parquet"
        avance.parcial_pendiente([nombre], "pasada")
        archivos[nombre] = _escribir(avance, nombre, tabla, esquema=tipos.ESQUEMA_PUNTOS_E5L)
    clima = fondo_era5l.tabla_clima_estado(acum)
    archivos["insumos/clima_estado.parquet"] = _escribir(avance, "insumos/clima_estado.parquet", clima,
                                                        esquema=tipos.ESQUEMA_CLIMA_ESTADO,
                                                        metadatos={"punto_hora": renorm})
    archivos["estaticas/z_e5l.parquet"] = _escribir(avance, "estaticas/z_e5l.parquet", z_tabla,
                                                    esquema=tipos.ESQUEMA_ZE5L)
    return archivos


# ---------------------------------------------------------------------------
# M3-4: unidades que corren en los trabajadores (funciones de módulo, ORQ-10)
# ---------------------------------------------------------------------------
_CARGADOS: dict[str, Any] = {}


def _codigo_fijado(ap: str, huellas_reloj: Mapping[str, str], sintetico: bool):
    """Adaptador, ``dmc_features`` y el validador de RELOJ, cargados por ruta y huella una vez por proceso;
    ``permitir_cargados`` sólo en el modo sintético (H6: es sólo para pruebas, FIJ-2)."""
    if "adaptador" not in _CARGADOS:
        _CARGADOS["adaptador"] = fijados.cargar_adaptador(ap)
        _CARGADOS["dmc_features"] = fijados.cargar_dmc_features(ap)
        _CARGADOS["validar"] = fijados.cargar_validador_reloj(ap, dict(huellas_reloj),
                                                              permitir_cargados=bool(sintetico))
    return _CARGADOS["adaptador"], _CARGADOS["dmc_features"], _CARGADOS["validar"]


def _unidad_estacion(unidad: Mapping, ctx: Mapping) -> dict:
    """ORQ-11: paso 1 de cada artefacto de la estación y pasos 2 a 4 (``qc_dmc_meteo.qc_estacion``)."""
    from meteo_combinada import qc_dmc_meteo as Q
    adaptador, dmc_features, validar = _codigo_fijado(ctx["ap"], ctx["huellas_reloj"], ctx["sintetico"])
    ruta_politica = ctx["ruta_politica"]
    resultados = [Q.normalizar_artefacto(Path(m), unidad["lectura"], adaptador=adaptador, dmc_features=dmc_features,
                                         validar_regla=lambda r, s: validar(r, s, politica_ruta=ruta_politica),
                                         sha_adaptador=fijados.SHA_ADAPTADOR, id_artefacto=i,
                                         artefactos=ctx["artefactos"])
                  for m, i in unidad["manifiestos"]]
    sin_tabla = [dataclasses.replace(r, larga=None) for r in resultados]
    if not any(r.normalizable for r in resultados):
        return {"codigo": unidad["codigo"], "artefactos": sin_tabla, "ancha": None}
    larga = Q.unir_largas(resultados)
    info = unidad["info"]
    F = unidad["F"]
    if isinstance(F, _Ref):                 # ORQ-44: el fondo de la estación viaja como referencia y se lee aquí
        F = _tabla_de(F)
    tabla, k4, efectivas = Q.qc_estacion(larga, info, F, ctx["U"], k2=ctx["k2"], politicas=unidad["lectura"])
    num, den = Q.conteos_estacion(tabla, info)
    return {"codigo": unidad["codigo"], "artefactos": sin_tabla, "ancha": Q.tabla_ancha(tabla),
            "efectivas": efectivas, "sin_prueba": bool(k4.sin_prueba), "num": num, "den": den}


def _tabla_a_json(df) -> dict:
    return {c: [None if (isinstance(x, float) and math.isnan(x)) or x is None or x is _pd_na() else
                _numeros_python(x) for x in df[c].tolist()] for c in df.columns}


def _pd_na():
    import pandas as pd
    return pd.NA


def _json_a_tabla(d: Mapping, esquema):
    import pandas as pd
    df = pd.DataFrame({c: pd.Series(d[c], dtype=object) for c in esquema})
    df = df.astype(dict(esquema))
    df.attrs = {"esquema": esquema.version}
    return df


def _artefacto_a_json(r: tipos.ResultadoArtefacto) -> dict:
    return {"id_artefacto": int(r.id_artefacto), "codigo": r.codigo, "anio": int(r.anio), "mes": int(r.mes),
            "content_sha256": r.content_sha256, "motivo": None if r.motivo is None else str(r.motivo.value),
            "origen": None if r.origen is None else str(r.origen.value),
            "reglas_rechazadas": list(r.reglas_rechazadas)}


def _artefacto_de_json(d: Mapping) -> tipos.ResultadoArtefacto:
    return tipos.ResultadoArtefacto(
        id_artefacto=int(d["id_artefacto"]), codigo=d["codigo"], anio=int(d["anio"]), mes=int(d["mes"]),
        content_sha256=d["content_sha256"],
        motivo=None if d["motivo"] is None else tipos.MotivoNoNormalizable(d["motivo"]),
        origen=None if d["origen"] is None else tipos.OrigenAborto(d["origen"]),
        reglas_rechazadas=tuple(d["reglas_rechazadas"]))


def _objetivo(ctx: Mapping) -> Callable:
    """ORQ-12 (A16, INT-5): el objetivo de ``candidatos.seleccionar`` con ``validacion``."""
    import numpy as np
    from meteo_combinada import particiones, validacion
    infos, horas, U = ctx["infos"], ctx["horas"], ctx["U"]

    def objetivo(internos, sumas, *, candidato, variable, uso):
        clave = validacion.HORAS_DE[str(variable)]
        pi = ctx["pi_sel"][str(Uso(uso).value)][clave]
        mse, banda = [], []
        for interno in internos:
            por = sumas[interno.id]
            d = particiones.distancia_entrenamiento_km(sorted(por), interno.entrenamiento, infos, horas[clave], U)
            for c in sorted(por):
                sse, n = por[c]
                if n > 0:
                    mse.append(sse / n)
                    banda.append(int(validacion.bandas([d[c]], U)[0]))
        if not mse:
            return math.nan
        return validacion.puntaje(np.array(mse), np.array(banda, dtype=np.int64), pi, U)
    return objetivo


# Qué se elige en cada uso de selección (ORQ-12, ORQ-13): (candidato, variable de selección, uso de los hiperparámetros).
_VARIABLES_SEL = {Uso.AMBIENTAL.value: ("T", "Td", "uv", "p"), Uso.AGUDO.value: ("T", "Td")}
_PRODUCTO_SEL = {"T": ("T",), "Td": ("Td",), "uv": ("u", "v"), "p": ("p",)}
_SEL_DE_PAR = {Grupo.T_TD.value: ("T", "Td"), Grupo.U_V.value: ("uv",), Grupo.P.value: ("p",)}


def _selecciones(pares) -> list[tuple[str, str, str]]:
    """(candidato, variable de selección, uso) de las selecciones de los pares (en un pliegue externo)."""
    salida = []
    for uso, grupo in pares:
        uso_sel = Uso.AMBIENTAL.value if uso == Uso.AMBIENTAL.value else Uso.AGUDO.value
        for var in _SEL_DE_PAR[grupo]:
            for cand in (Candidato.A.value, Candidato.B.value, Candidato.AB.value):
                salida.append((cand, var, uso_sel))
            if uso == Uso.CRONICO.value:
                salida.append((Candidato.C_EST.value, var, Uso.CRONICO.value))
            else:
                salida.append((Candidato.C.value, var, uso_sel))
    vistos, unicos = set(), []
    for s in salida:
        if s not in vistos:
            vistos.add(s)
            unicos.append(s)
    return unicos


def _seleccionar_todo(sel: Sequence[tuple[str, str, str]], externo, ctx) -> dict:
    from meteo_combinada import candidatos
    objetivo = _objetivo(ctx)
    hiper: dict = {}
    for cand, var, uso in sel:
        extra = {"hiper_a": hiper[(Candidato.A.value, var, uso)]} if cand == Candidato.AB.value else {}
        hiper[(cand, var, uso)] = candidatos.seleccionar(cand, var, uso, externo, ctx["datos"], ctx["U"],
                                                         objetivo=objetivo, recorte=ctx["recorte"], **extra)
    return hiper


def _unidad_produccion(unidad: Mapping, ctx: Mapping) -> dict:
    """ORQ-13: los hiperparámetros de producción de un conjunto de selecciones."""
    return _seleccionar_todo(unidad["selecciones"], unidad["pliegue"], ctx)


_OBS = {"T": ("Ts", "valido_T"), "Td": ("td_final", "valido_Td"), "HR": ("hr_final", "valido_HR"),
        "u": ("u_final", "valido_viento"), "v": ("v_final", "valido_viento"), "p": ("QFE", "valido_p")}
# Variables de métrica de cada par (validacion.METRICAS) y de qué variables del producto depende cada una.
_DEPENDE = {"T": ("T",), "Td": ("Td",), "HR": ("T", "Td"), "rapidez": ("u", "v"), "uv": ("u", "v"), "p": ("p",),
            "temp_media": ("T",), "hr_media": ("T", "Td")}


def _unidad_pliegue(unidad: Mapping, ctx: Mapping) -> dict:
    """ORQ-11, ORQ-12, ORQ-15: la selección, la predicción y las evaluaciones de un pliegue externo.

    ORQ-43: las predicciones se calculan en el orden de siempre (el de las selecciones), cada una se reduce en cuanto
    sale a lo que la evaluación lee de ella (por estación de prueba: sus horas, la corrección y el soporte, con las
    horas compartidas entre predicciones iguales) y se suelta cuando ya la evaluó el último par que la usa; cada par se
    evalúa apenas tiene todas las suyas, con la misma cuenta de siempre, y lo de los pares se junta en el orden de los
    pares. Un error de una predicción sale en el mismo orden que antes; el de una evaluación, el del primer par que
    falla, recién después de todas las predicciones (como antes, que evaluaba después de predecir todo)."""
    U, externo = ctx["U"], unidad["pliegue"]
    hiper = _seleccionar_todo(unidad["selecciones"], externo, ctx)
    with _con_fondo_de_prueba(ctx, externo):
        por_par = _predecir_y_evaluar(hiper, externo, ctx, U)
    filas, descriptivas, anuales, finitud = [], [], {}, {}
    periodos = {k: [] for k in ctx["periodos"]}
    for r in por_par:
        filas += r["filas"]
        descriptivas += r["descriptivas"]
        anuales.update(r["anuales"])
        for k in periodos:
            periodos[k] += r["periodos"][k]
        finitud.update(r["finitud"])
    return {"pliegue": externo.id, "hiper": hiper, "filas": filas, "descriptivas": descriptivas, "anuales": anuales,
            "periodos": periodos, "finitud": finitud}


def _predecir_y_evaluar(hiper: Mapping, externo, ctx: Mapping, U) -> list:
    """ORQ-43: las predicciones de un pliegue externo, en el orden de siempre, y la evaluación de cada par apenas tiene
    las suyas: lo de cada par, en el orden de los pares."""
    from meteo_combinada import candidatos
    datos, F = ctx["datos"], ctx["F"]
    orden = [((cand, pv, uso), h) for (cand, var, uso), h in hiper.items() for pv in _PRODUCTO_SEL[var]]
    claves = {k for k, _ in orden}
    pares = list(ctx["pares"])
    necesita = [_claves_del_par(uso, grupo, claves) for uso, grupo in pares]
    usos = {k: sum(k in n for n in necesita) for k in claves}
    reducidas: dict = {}
    horas_de: dict = {}
    por_par: list = [None] * len(pares)
    errores: dict = {}
    pendientes = list(range(len(pares)))

    def evaluar_listos():
        for i in [j for j in pendientes if necesita[j].issubset(reducidas)]:
            pendientes.remove(i)
            try:
                por_par[i] = _evaluar_par(*pares[i], externo, ctx, F, reducidas, claves, U)
            except Exception as e:                  # noqa: BLE001 (sale después de predecir todo, como antes)
                errores[i] = e
            for k in necesita[i]:
                usos[k] -= 1
                if not usos[k]:
                    del reducidas[k]
    evaluar_listos()
    for (cand, pv, uso), h in orden:
        g = candidatos.predecir_prueba(cand, pv, uso, h, externo, datos, umbrales=U)
        if usos[(cand, pv, uso)]:
            reducidas[(cand, pv, uso)] = _reducir_prediccion(g, externo.prueba, horas_de)
        del g
        evaluar_listos()
    if errores:
        raise errores[min(errores)]
    return por_par


@contextlib.contextmanager
def _con_fondo_de_prueba(ctx: Mapping, externo):
    """ORQ-42: mientras se predice y se evalúa un pliegue externo con la receta de la selección, el fondo entero de sus
    estaciones de prueba (del disco) está en el fondo de la ``DatosCompetencia`` del proceso, en vez del de los días de
    selección, y al salir (también por un error) vuelve el de los días de selección. Es la misma ``DatosCompetencia``
    (no una copia): la caché de ``candidatos`` (CAN-19), que no depende del fondo, sigue tibia para sus r̄ y sus tablas.
    Sin la receta (un contexto armado en memoria, como el de ``costo``), no cambia nada."""
    F = ctx["F"]
    if ctx.get("fondo_prueba") is None or not externo.prueba:
        yield
        return
    if not isinstance(F, dict) or F is not ctx["datos"].puntos_e5l:
        raise ErrorOrquestacion("ORQ-42: el fondo de la selección es el diccionario de la DatosCompetencia del proceso")
    previos = {c: F[c] for c in externo.prueba if c in F}
    try:
        for c in previos:
            F[c] = ctx["fondo_prueba"](c)
        yield
    finally:
        F.update(previos)


def _claves_del_par(uso: str, grupo: str, claves) -> frozenset:
    """ORQ-43: las predicciones (candidato, variable del producto, uso) que lee la evaluación de un par: las de sus
    candidatos y de las variables de sus métricas que se calculan (las demás valen 0 con soporte, como siempre)."""
    from meteo_combinada import validacion
    uso_sel = Uso.AMBIENTAL.value if uso == Uso.AMBIENTAL.value else Uso.AGUDO.value
    pvs = {pv for v in validacion.METRICAS[(Uso(uso), Grupo(grupo))] for pv in _DEPENDE[v]}
    return frozenset((cand, pv, uso if cand == Candidato.C_EST.value else uso_sel)
                     for cand in validacion.CANDIDATOS_USO[Uso(uso)] for pv in pvs) & frozenset(claves)


def _reducir_prediccion(g, prueba, horas_de: dict) -> dict:
    """ORQ-43: {código: (h, corrección, soporte)} de una predicción (``candidatos.COLUMNAS_PREDICCION``): las filas de
    cada estación de prueba (las mismas que ``g["codigo"] == código``, en su orden), h en int64, la corrección en
    float64 y el soporte en bool, como los leía la evaluación. Las horas de una estación se guardan una vez si son
    iguales en todas sus predicciones (``horas_de``)."""
    import numpy as np
    import pandas as pd
    cod, unicos = pd.factorize(g["codigo"])
    indice = {u: j for j, u in enumerate(unicos)}
    h = g["h"].to_numpy(np.int64)
    corr = g["correccion"].to_numpy(np.float64)
    sop = g["soporte"].to_numpy(bool)
    salida = {}
    for c in prueba:
        m = cod == indice[c] if c in indice else np.zeros(cod.size, dtype=bool)
        hc = h[m]
        previa = horas_de.setdefault(c, hc)
        salida[c] = (previa if previa is not hc and np.array_equal(previa, hc) else hc, corr[m], sop[m])
    return salida


def _evaluar_par(uso: str, grupo: str, externo, ctx: Mapping, F: Mapping, reducidas: Mapping, claves, U) -> dict:
    """ORQ-11, ORQ-15, ORQ-43: las evaluaciones de un par (uso, grupo) en las estaciones de prueba de un pliegue
    externo, con las predicciones reducidas (``_reducir_prediccion``): la misma cuenta, en el mismo orden."""
    import numpy as np
    from meteo_combinada import fondo_era5l, producto, validacion
    infos = ctx["infos"]
    filas, descriptivas, anuales, finitud = [], [], {}, {}
    periodos = {k: [] for k in ctx["periodos"]}
    uso_sel = Uso.AMBIENTAL.value if uso == Uso.AMBIENTAL.value else Uso.AGUDO.value
    metricas = list(validacion.METRICAS[(Uso(uso), Grupo(grupo))])
    pvs = sorted({pv for v in metricas for pv in _DEPENDE[v]})
    for c in externo.prueba:
        info = infos[c]
        ancha = ctx["anchas"][c]
        hq = ancha["h"].to_numpy(np.int64)
        Fh = fondo_era5l.en_horas(F[c], hq) if F.get(c) is not None else {
            k: np.full(hq.size, np.nan) for k in fondo_era5l.CAMPOS_F}
        cands = [x for x in validacion.CANDIDATOS_USO[Uso(uso)]
                 if not (tipos.fuera_de_la_grilla(info) and x in (Candidato.C.value, Candidato.C_EST.value))]
        campos, soporte = {}, {}
        for cand in cands:
            u_h = uso if cand == Candidato.C_EST.value else uso_sel
            R, sop = {}, {}
            for pv in ("T", "Td", "u", "v", "p"):
                clave = (cand, pv, u_h)
                if pv not in pvs or clave not in claves:
                    R[f"R_{pv}"], sop[pv] = np.zeros(hq.size), np.ones(hq.size, dtype=bool)
                    continue
                hg, corr, sg = reducidas[clave][c]
                pos = np.searchsorted(hg, hq)
                esta = (pos < hg.size)
                pos_c = np.clip(pos, 0, max(hg.size - 1, 0))
                if hg.size:
                    esta &= hg[pos_c] == hq
                r = np.full(hq.size, np.nan)
                s = np.zeros(hq.size, dtype=bool)
                r[esta] = corr[pos_c[esta]]
                s[esta] = sg[pos_c[esta]]
                R[f"R_{pv}"], sop[pv] = r, s
            campos[cand] = producto.campos(Fh, R)
            soporte[cand] = sop
            if not tipos.fuera_de_la_grilla(info):
                col = {k: np.asarray(x, dtype=np.float64)[:, None] for k, x in campos[cand].items()}
                con = producto.hay_fondo({k: x[:, None] for k, x in Fh.items()}, grupo=grupo)
                finitud[(uso, grupo, cand)] = finitud.get((uso, grupo, cand), producto.ConteoFinito(0, 0)) + \
                    producto.conteo_finito(col, con, grupo=grupo)
        for v in metricas:
            pred_v, obs_v, sop_v = {}, None, {}
            for cand in cands:
                pred_v[cand], obs_v = _serie(v, campos[cand], ancha)
                sop_v[cand] = np.logical_and.reduce([soporte[cand][pv] for pv in _DEPENDE[v]])
            fin = [np.isfinite(p) if not isinstance(p, tuple) else np.isfinite(p[0]) & np.isfinite(p[1])
                   for p in pred_v.values()]
            obs_fin = np.isfinite(obs_v) if not isinstance(obs_v, tuple) else (np.isfinite(obs_v[0])
                                                                              & np.isfinite(obs_v[1]))
            comun = obs_fin & np.logical_and.reduce(fin)
            for nombre_p, mascara in (("", np.ones(hq.size, dtype=bool)), *ctx["periodos"].items()):
                if nombre_p:
                    mascara = _mascara_periodo(hq, mascara)
                for cand in cands:
                    m_c = comun & mascara
                    p_c = _con_mascara(pred_v[cand], m_c)
                    met = validacion.evaluacion(hq, p_c, obs_v, uso=uso, variable=v, umbrales=U)
                    if met is None:
                        continue
                    frac = (float(1 - sop_v[cand][m_c].mean()) if cand in validacion.NUCLEO and m_c.any()
                            else math.nan)
                    fila = validacion.fila_evaluacion(met, codigo=c, particion=externo.particion.value,
                                                      pliegue=externo.id, candidato=cand, uso=uso, variable=v,
                                                      frac_sin_soporte=frac)
                    if nombre_p:
                        periodos[nombre_p].append(fila)
                        continue
                    filas.append(fila)
                    descriptivas += validacion.filas_descriptivas(met, codigo=c, particion=externo.particion.value,
                                                                  candidato=cand, uso=uso, variable=v)
                    if met.get("anuales") is not None:
                        anuales[(c, externo.particion.value, cand)] = met["anuales"]
    return {"filas": filas, "descriptivas": descriptivas, "anuales": anuales, "periodos": periodos,
            "finitud": finitud}


def _mascara_periodo(hq, periodo):
    from meteo_combinada import tendencias
    desde, hasta = periodo
    anio = tendencias.anio_de(hq)
    return (anio >= desde) & (anio <= hasta)


def _con_mascara(p, m):
    import numpy as np
    if isinstance(p, tuple):
        return tuple(np.where(m, x, np.nan) for x in p)
    return np.where(m, p, np.nan)


def _serie(v: str, campos: Mapping, ancha):
    """(producto, observación) de una variable de métrica (VAL-2): «uv» como (u, v), la rapidez como el módulo."""
    import numpy as np

    def obs(k):
        col, val = _OBS[k]
        return np.where(ancha[val].to_numpy(bool), ancha[col].to_numpy(np.float64), np.nan)
    if v == "uv":
        return (campos["u"], campos["v"]), (obs("u"), obs("v"))
    if v == "rapidez":
        return np.hypot(campos["u"], campos["v"]), np.hypot(obs("u"), obs("v"))
    if v == "temp_media":
        return campos["T"], obs("T")
    if v == "hr_media":
        return campos["HR"], obs("HR")
    return campos[v], obs(v)


def _unidad_mes_tf(unidad: Mapping, ctx: Mapping) -> dict:
    """ORQ-11, ORQ-15 (TEN-22): las sumas comunales de un mes de una pasada de TF y la finitud de E0 en sus celdas."""
    import numpy as np
    from meteo_combinada import fondo_era5l, producto, tendencias
    U = ctx["U"]
    mes = fondo_era5l.leer_mes(Path(unidad["ruta"]), sha256=unidad["sha256"])
    fondo_era5l.comprobar_unidades(mes)
    if not mes.completo_hasta(ctx["h_ultima"]):
        raise ErrorOrquestacion(f"{unidad['mes']}: el mes no trae todas sus horas (FON-1)")
    h = np.asarray(mes.tiempos, dtype=np.int64)
    pasada, op, _ = _pasada_de(ctx)
    cache: dict = {}

    renorm = {}

    def fondo(hh, idx):
        clave = (int(idx[0]), int(idx[-1]) if len(idx) else -1, len(idx))
        if clave not in cache:
            cache.clear()
            F = fondo_era5l.campos_fondo(mes, _sub_operador(op, idx), U)
            renorm[clave] = int(np.asarray(F["renormalizada"]).sum())
            cache[clave] = {c: np.asarray(F[c], dtype=np.float64) for c in fondo_era5l.CAMPOS_F}
        return cache[clave]
    salida = {}
    if unidad["tf"]:
        salida["sumas"] = pasada.sumas_mes(h, fondo)
    finitud = {}
    if ctx["e0"] and unidad["tf"]:                    # ORQ-15: todas las horas de la pasada de TF
        n = pasada.celdas.n
        puntos = pasada.celdas.puntos()
        lote = int(tendencias.LOTE_PUNTOS_TF)
        for uso, grupo, cand in ctx["e0"]:            # H3: por lotes de celdas; los conteos son enteros
            de_c = cand in (Candidato.C.value, Candidato.C_EST.value)
            R_mes = {} if de_c else {pv: pasada.correccion_mes(h, fondo, cand, ETIQUETA_PRODUCCION, pv)
                                     for pv in _PV_DE_GRUPO[grupo]}
            total = producto.ConteoFinito(0, 0)
            for i0 in range(0, n, lote):
                idx = np.arange(i0, min(n, i0 + lote))
                F = fondo(h, idx)
                F = {**F, "amp_TF": fondo_era5l.amplitud_dia_utc(F["T_F"], h)}
                con = producto.hay_fondo(F, grupo=grupo)
                if de_c:
                    est = None if pasada.celdas.estaticos is None else \
                        pasada.celdas.estaticos.iloc[idx].reset_index(drop=True)
                    clima = None if pasada.celdas.clima_estado is None else \
                        {k: np.asarray(v)[idx] for k, v in pasada.celdas.clima_estado.items()}
                    total = total + producto.conteo_finito_c(
                        cand, {k: np.asarray(v)[idx] for k, v in puntos.items()}, h, con, estaticos=est, fondo=F,
                        clima=clima, celdas=np.asarray(pasada.celdas.ids)[idx])
                    continue
                R = {f"R_{pv}": np.zeros((h.size, idx.size)) for pv in ("T", "Td", "u", "v", "p")}
                for pv, r in R_mes.items():
                    R[f"R_{pv}"] = r[:, idx]
                total = total + producto.conteo_finito(producto.campos(F, R), con, grupo=grupo)
            finitud[(uso, grupo, cand)] = total
            del R_mes
    salida["finitud"] = finitud
    # MC-39: los punto-hora renormalizados del mes, contados una vez (los lotes de la TF; la llamada con todas las
    # celdas de E0 repite los mismos punto-hora y sólo cuenta si es la única)
    salida["renormalizadas"] = int(sum(v for k, v in renorm.items() if k[2] != pasada.celdas.n or len(renorm) == 1))
    return salida


_PV_DE_GRUPO = {Grupo.T_TD.value: ("T", "Td"), Grupo.U_V.value: ("u", "v"), Grupo.P.value: ("p",)}
_PASADAS: dict[str, Any] = {}


def _pasada_de(ctx: Mapping) -> tuple:
    """(``tendencias.PasadaTF``, operador de sus celdas, punto-mes-hora renormalizados del clima) de un contexto,
    armados una vez en cada proceso (PED-5: la pasada indexa sus configuraciones por ``id`` y no sobrevive a pickle).
    Viaja su receta (ORQ-36, H1): la ``DatosCompetencia`` y las celdas de la pasada se rearman del disco, con sus
    huellas, en el principal y en cada trabajador, con la misma cuenta."""
    from meteo_combinada import tendencias
    clave = ctx["clave_pasada"]
    if clave not in _PASADAS:
        _PASADAS.clear()
        a = ctx["args_pasada"]
        datos, extras = _datos_de_receta(a["receta"], ctx["U"])
        c = a["celdas"]
        celdas_tf, op, clima_n = _celdas_tf(c["pasada_uso"], _tabla_de(c["celdas"]), _tabla_de(c["pesos"]),
                                            extras["estaticos_m2a"], extras["clima_tabla"], c["cat_pix"],
                                            extras["validos"], extras["z_tabla"], ctx["U"])
        _PASADAS[clave] = (tendencias.PasadaTF(datos, celdas_tf, a["escenarios"], a["configuraciones"], ctx["U"],
                                               variables=a["variables"]), op, clima_n)
    return _PASADAS[clave]


# ---------------------------------------------------------------------------
# M3-4 (§2.1, §4-§6; §2.5 del diseño)
# ---------------------------------------------------------------------------
def _leer_carpeta(cfg: Cfg, carpeta: Path, que: str) -> dict:
    """Las salidas selladas de una corrida de este paquete, cada una con la huella de su ``sha256.json``, que su recibo
    cita (§8, «Cadena de huellas»; §10). ``leidos`` junta {ruta por alias: sha256} de lo que se va leyendo (ORQ-21)."""
    inventario = json.loads(_leer_propio(carpeta / salidas.SHA256_JSON))["archivos"]
    recibo = json.loads(_leer_propio(carpeta / salidas.RECIBO))
    propia = entorno.alias(carpeta / salidas.SHA256_JSON, cfg.rutas)
    if recibo["huellas"].get(propia) != huella_archivo(carpeta / salidas.SHA256_JSON):
        raise ErrorOrquestacion(f"el recibo de {que} no cita su sha256.json (§8, «Cadena de huellas»)")
    leidos: dict[str, str] = {}

    def leer(nombre: str):
        if nombre not in inventario:
            raise ErrorOrquestacion(f"{que} no trae {nombre}")
        sha = inventario[nombre]["sha256"]
        leidos[entorno.alias(carpeta / nombre, cfg.rutas)] = sha
        return _leer_propio(carpeta / nombre, sha)
    def ref(nombre: str) -> _Ref:
        if nombre not in inventario:
            raise ErrorOrquestacion(f"{que} no trae {nombre}")
        sha = inventario[nombre]["sha256"]
        leidos[entorno.alias(carpeta / nombre, cfg.rutas)] = sha
        return _Ref(str(carpeta / nombre), sha)
    return {"carpeta": carpeta, "inventario": inventario, "leer": leer, "leidos": leidos, "ref": ref,
            "sha": lambda nombre: inventario[nombre]["sha256"],
            "huellas": {entorno.alias(carpeta / n, cfg.rutas): v["sha256"] for n, v in sorted(inventario.items())}}


def _leer_m2a(cfg: Cfg) -> dict:
    """Las salidas de M2a, cada una con la huella de su ``sha256.json`` (§10: «alguna huella … del registro de M2a
    difiere»)."""
    return _leer_carpeta(cfg, ruta_de_alias(cfg.rutas, cfg.entrada("m2a")), "M2a")


@dataclass(frozen=True)
class _Manifiesto:
    ruta: str
    sha_artefacto: str
    mes: str
    sha: str


def _manifiestos(cfg: Cfg, artefactos: Mapping[str, str]) -> dict[str, list[_Manifiesto]]:
    """Código → [(ruta del manifiesto, sha256 del artefacto, AAAA-MM)] de los manifiestos con artefacto evaluado
    (A17), en orden de nombre; y la huella de cada manifiesto."""
    base = cfg.rutas.dmc / "estaciones"
    salida: dict[str, list] = {}
    hallados: list[str] = []
    for d in (sorted(os.scandir(base), key=lambda e: e.name) if base.is_dir() else ()):
        if not d.is_dir(follow_symlinks=False) or not _PATRON_CODIGO.fullmatch(d.name):
            continue
        for m in sorted(os.scandir(d.path), key=lambda e: e.name):
            if not m.name.endswith(".manifest.json"):
                continue
            with open(m.path, "rb") as f:
                datos = f.read()
            meta = json.loads(datos)
            sha = meta.get("artifact_sha256")
            if sha and sha in artefactos and artefactos[sha] != d.name:
                raise ErrorOrquestacion(f"{d.name}: un manifiesto cita un artefacto evaluado de otra estación (H4)")
            if sha and artefactos.get(sha) == d.name:
                hallados.append(sha)
                mes = _PATRON_MES_GUION.match(m.name)
                if mes is None:
                    raise ErrorOrquestacion(f"{d.name}: manifiesto sin «AAAA-MM» en el nombre")
                salida.setdefault(d.name, []).append(_Manifiesto(m.path, sha, mes.group(0),
                                                                 entorno.sha256_bytes(datos)))
    # H4: los hallados deben ser exactamente los artefactos evaluados, sin repetir (un defecto de la entrada detiene:
    # no es un «no normalizable»)
    repetidos = len(hallados) - len(set(hallados))
    faltan = len(set(artefactos) - set(hallados))
    if repetidos or faltan:
        raise ErrorOrquestacion(f"los manifiestos no calzan con artefactos_evaluados: {faltan} artefactos evaluados "
                                f"sin manifiesto y {repetidos} citados más de una vez (H4, §2.1)")
    return salida


def correr_m34(cfg, *, avance, procesos: int) -> dict:
    """M3-4 (§2.5 del diseño): control de calidad, competencia, TF, descriptivos, decisión y sello, en una corrida
    (§10). Las negativas de §10 son de I22 (``Cfg.negativas``). Devuelve el registro y la decisión."""
    import numpy as np
    import pandas as pd
    from meteo_combinada import candidatos, decision, fondo_era5l, particiones, politicas, producto, tendencias
    from meteo_combinada import qc_dmc_meteo as Q
    from meteo_combinada import validacion

    U = cfg.U
    fases: list[str] = []
    # 0. negativas
    fallas = _negativas(cfg, [k for k in ENTRADAS_M34 if k != "m2a"])
    m2a = _leer_m2a(cfg)
    fallas += _negativas_registro(cfg, m2a, REGISTRO_M2A, "M2a")
    if fallas:
        raise ErrorOrquestacion("M3-4 se niega a correr: " + "; ".join(fallas[:_CITADOS]))
    avance.iniciar()                                      # ORQ-35 (H7): recién ahora la carpeta queda atada
    fases.append("negativas")
    # 1. políticas de lectura (§2.1, precondición 1; §2.2-§2.5)
    ap = cfg.rutas.ap
    leer_entrada(cfg, cfg.entrada("registro_c5"))         # H11: su huella frente a la lista cerrada, antes de leerlo
    registro_c5 = politicas.leer_registro_c5(ruta_de_alias(cfg.rutas, cfg.entrada("registro_c5")), ap=ap)
    pol, artefactos = politicas.leer_politica_reloj(registro_c5, ap=ap)
    fallas_c5 = politicas.comprobar_c5(registro_c5, pol)
    if fallas_c5:
        raise ErrorOrquestacion("C5 de RELOJ no es válido: " + "; ".join(fallas_c5[:_CITADOS]))
    declaracion = politicas.declaracion_c5(registro_c5, pol)
    k2 = politicas.coordenadas_inconsistentes(registro_c5, ap=ap)
    ruta_artefactos = ap / politicas.RUTA_PUBLICACION_RELOJ / ceguera.ARTEFACTOS_RELOJ
    lista = json.loads(gzip.decompress(_leer_propio(ruta_artefactos, registro_c5.sha256_artefactos)))
    indice = {x["artefacto_sha256"]: k for k, x in enumerate(lista)}
    ruta_politica = ap / politicas.RUTA_PUBLICACION_RELOJ / ceguera.POLITICA_RELOJ
    sha_catalogo = cfg.huellas[cfg.entrada("catalogo_dmc")]
    infos = infos_de_tabla(_parquet(m2a["leer"]("estaticas/estaciones.parquet")))
    manifiestos = _manifiestos(cfg, artefactos)
    # H9 (§8, «Cadena de huellas»): la huella agregada de los manifiestos usados, {ruta por alias: sha256}
    huella_manifiestos = {entorno.alias(cfg.rutas.dmc / "estaciones", cfg.rutas): entorno.sha256_bytes(
        entorno.json_canonico({entorno.alias(Path(x.ruta), cfg.rutas): x.sha
                               for c in sorted(manifiestos) for x in manifiestos[c]}))}
    lecturas = {}
    for c, ms in manifiestos.items():
        if c not in infos:
            raise ErrorOrquestacion(f"{c}: estación con artefactos y sin fila en los estáticos de M2a")
        meses = {(int(_PATRON_MES_GUION.match(x.mes)["anio"]), int(_PATRON_MES_GUION.match(x.mes)["mes"])) for x in ms}
        tramos = politicas.tramos_de_lectura(pol, c, meses, politicas.marcas_g(pol, c), info=infos[c], k2=k2)
        lecturas[c] = politicas.politicas_de_lectura(pol, infos[c], tramos, U, sha_protocolo=U.sha256_texto_vigente,
                                                     sha_catalogo=sha_catalogo)
    fases.append("politicas_de_lectura")
    por_fase = _procesos_de_fases(cfg, "m34", procesos)         # ORQ-45 (D59): límites, no procesos observados
    repartos = {fase: [] for fase in por_fase}                # EMC3-1: sólo esta invocación, tras filtrar el avance
    # 2-4. por estación (ORQ-11); ORQ-44: el fondo de cada estación, como referencia (se lee donde se usa)
    fondo_ref: dict[str, _Ref | None] = {}
    for c in infos:
        nombre = f"insumos/puntos_estacion/{c}.parquet"
        fondo_ref[c] = m2a["ref"](nombre) if nombre in m2a["inventario"] else None
    ctx_est = {"ap": str(entorno.rutas_reales().ap), "huellas_reloj": dict(fijados.HUELLAS_RELOJ),
               "ruta_politica": str(ruta_politica), "artefactos": dict(artefactos), "U": U, "k2": k2,
               "sintetico": cfg.modo == tipos.Modo.SINTETICO.value}
    unidades, salteadas = [], {}
    for c in sorted(manifiestos):
        entrada = _huella_unidad(codigo=c, manifiestos=[[x.sha_artefacto, x.sha] for x in manifiestos[c]],
                                 politica=registro_c5.sha256_politica, lectura=politicas.a_json(lecturas[c]).decode(),
                                 m2a=m2a["huellas"].get(entorno.alias(m2a["carpeta"] / f"insumos/puntos_estacion/{c}"
                                                                      ".parquet", cfg.rutas)),
                                 info=m2a["huellas"][entorno.alias(m2a["carpeta"] / "estaticas/estaciones.parquet",
                                                                   cfg.rutas)])
        nombre = f"qc/estaciones/{c}.parquet"
        hecha = avance.hecha("artefactos", f"estacion-{c}", entrada)
        if hecha is not None:
            salteadas[c] = hecha
            avance.saltadas.append(f"estacion-{c}")
            continue
        avance.parcial_pendiente([nombre], f"estacion-{c}")
        unidades.append({"codigo": c, "entrada": entrada, "info": infos[c], "F": fondo_ref[c], "lectura": lecturas[c],
                         "manifiestos": [(x.ruta, indice[x.sha_artefacto]) for x in manifiestos[c]]})
    sin_tabla: dict[str, list] = {}

    def al_terminar_estacion(i, r):
        c = r["codigo"]
        if r["ancha"] is None:
            sin_tabla[c] = r["artefactos"]
            return None
        meta = {"artefactos": [_artefacto_a_json(a) for a in r["artefactos"]],
                "efectivas": json.loads(politicas.a_json(r["efectivas"])), "sin_prueba": r["sin_prueba"],
                "num": _tabla_a_json(r["num"]), "den": _tabla_a_json(r["den"])}
        nombre = f"qc/estaciones/{c}.parquet"
        sha = _escribir(avance, nombre, r["ancha"], esquema=tipos.ESQUEMA_QC_ESTACION, metadatos=meta)
        avance.registrar("artefactos", f"estacion-{c}", unidades[i]["entrada"], {nombre: sha})
        return None
    repartir(unidades, _unidad_estacion, por_fase["artefactos"], contexto=ctx_est, al_terminar=al_terminar_estacion,
             permitidas=cfg.permitidas, registro=repartos["artefactos"])
    fases.append("artefactos")
    # lo de cada estación, leído del disco (ORQ-8); ORQ-44: de cada tabla ancha quedan sus metadatos y su referencia
    efectivas_de, resultados_art, nums, dens, sin_traslado = {}, [], [], [], []
    ref_ancha: dict[str, _Ref] = {}
    for c in sorted(manifiestos):
        if c in sin_tabla:
            resultados_art += sin_tabla[c]
            continue
        r = avance.hecha("artefactos", f"estacion-{c}", salteadas[c]["entrada"] if c in salteadas else
                         next(u["entrada"] for u in unidades if u["codigo"] == c))
        nombre = f"qc/estaciones/{c}.parquet"
        meta = _parquet(_leer_propio(avance.carpeta / nombre, r["archivos"][nombre])).attrs.get("metadatos", {})
        ref_ancha[c] = _ref_de_archivo(avance.carpeta, nombre, r["archivos"][nombre])
        efectivas_de[c] = politicas.de_json(json.dumps(meta["efectivas"]).encode("utf-8"))
        resultados_art += [_artefacto_de_json(a) for a in meta["artefactos"]]
        nums.append(_json_a_tabla(meta["num"], tipos.ESQUEMA_CONTEOS_QC))
        dens.append(_json_a_tabla(meta["den"], tipos.ESQUEMA_CONTEOS_QC))
        if meta["sin_prueba"]:
            sin_traslado.append(c)
    # alarmas y resumen (§2.7)
    n3, d3 = Q.conteos_artefactos(resultados_art, infos)
    num = pd.concat([*nums, n3], ignore_index=True)
    den = pd.concat([*dens, d3], ignore_index=True)
    alarmas = Q.alarmas(num, den, U)
    lista_d = Q.lista_descriptiva(num, den, U)
    nn = Q.tabla_no_normalizables(resultados_art, infos)
    resumen = Q.resumen_qc(num, alarmas, nn, sin_traslado, denominadores=den, lista=lista_d, umbrales=U)
    huellas_salida = {}
    huellas_salida["qc/resumen_qc.json"] = _escribir(avance, "qc/resumen_qc.json", resumen)
    huellas_salida["qc/no_normalizables.csv"] = _escribir(avance, "qc/no_normalizables.csv", nn,
                                                          esquema=tipos.ESQUEMA_NO_NORMALIZABLES)
    efectivas = [p for c in sorted(efectivas_de) for p in efectivas_de[c]]
    # H10: la política efectiva va antes que decision.json, que cita su huella
    huellas_salida[salidas.POLITICA] = _escribir(avance, salidas.POLITICA, politicas.a_json(efectivas))
    fases.append("envoltorio_k4_marcas_alarmas")
    base_registro = {"esquema": ESQUEMA_REGISTRO_M34, "c5": declaracion,
                     "estaciones": {"con_artefactos": len(manifiestos), "con_tabla": len(ref_ancha),
                                    "sin_tabla": len(sin_tabla)},
                     "procesos_por_fase": _a_plano(cfg.procesos_por_fase)}       # ORQ-45 (D59): los del addendum
    if resumen.get("detener"):
        r = _sellar_m34(cfg, avance, m2a, base_registro | {"detenida": True, "fases": fases}, efectivas, None,
                        huellas_salida, procesos, huella_manifiestos, por_fase, repartos=repartos)
        raise DetencionPorAlarma("M3-4 se detiene por una alarma de §2.7 (qc/resumen_qc.json)", r)
    # 6. residuos, tramos homogéneos, A y filas de C (MC-45); ORQ-44: de a una estación, con sólo las columnas de la
    # tabla ancha que se usan, y con ellas las horas válidas (TEN-1; A24: una sola vez para validacion y tendencias)
    anios = range(constantes.valor("PI_POB_PERIODO")[0], constantes.valor("PI_POB_PERIODO")[1] + 1)
    residuos, tramos = {}, []
    horas_anio = {k: {a: {} for a in anios} for k in validacion.CLAVES_HORAS}
    horas = {k: {} for k in validacion.CLAVES_HORAS}
    for c in sorted(ref_ancha):
        if infos[c].excluida or fondo_ref.get(c) is None:
            continue
        ancha = _ancha_de(ref_ancha[c])
        h = ancha["h"].to_numpy(np.int64)
        obs = {k: np.where(ancha[val].to_numpy(bool), ancha[col].to_numpy(np.float64), np.nan)
               for k, (col, val) in (("T", _OBS["T"]), ("Td", _OBS["Td"]), ("u", _OBS["u"]), ("v", _OBS["v"]),
                                     ("QFE", _OBS["p"]))}
        r = fondo_era5l.residuos(obs, fondo_era5l.en_horas(_tabla_de(fondo_ref[c]), h))
        residuos[c], tr = candidatos.residuos_estacion(c, h, {"T": r["r_T"], "Td": r["r_Td"], "u": r["r_u"],
                                                              "v": r["r_v"], "p": r["r_p"]}, U)
        tramos.append(tr)
        _horas_de_una(horas_anio, horas, c, ancha, anios)        # las que entran: las de los residuos, en su orden
        del ancha, r
    tramos_t = pd.concat(tramos, ignore_index=True) if tramos else tipos.tabla_vacia(tipos.ESQUEMA_TRAMOS_HOMOGENEOS)
    clima_a = candidatos.climatologias_a(residuos, U)
    for c in sorted(residuos):
        nombre = f"producto/residuos/{c}.parquet"
        huellas_salida[nombre] = _escribir(avance, nombre, residuos[c], esquema=tipos.ESQUEMA_RESIDUOS)
    tramos_t.attrs = {"esquema": tipos.ESQUEMA_TRAMOS_HOMOGENEOS.version}
    huellas_salida["producto/tramos_homogeneos.parquet"] = _escribir(
        avance, "producto/tramos_homogeneos.parquet", tramos_t, esquema=tipos.ESQUEMA_TRAMOS_HOMOGENEOS)
    huellas_salida["producto/clima_a.parquet"] = _escribir(avance, "producto/clima_a.parquet", clima_a,
                                                           esquema=tipos.ESQUEMA_CLIMA_A)
    # ORQ-36 (H1): la DatosCompetencia sale de su receta (los residuos, A y los tramos releídos del disco con su
    # huella, y lo de M2a), en el principal y en cada trabajador, con la misma cuenta; ORQ-44: el principal no usa el
    # fondo de las estaciones (la variante ligera) y suelta los residuos que ya escribió
    cod_res = sorted(residuos)
    del residuos
    entran = {c: infos[c] for c in cod_res}                      # las que entran y tienen datos (PAR-1)
    grupos = {c: infos[c].grupo for c in entran}
    pliegues = tuple(particiones.pliegues_p1(grupos, U) + particiones.pliegues_p2(entran, grupos, U))
    receta = _receta_datos(lambda n: _ref_de_archivo(avance.carpeta, n, huellas_salida[n]), m2a["ref"], cod_res,
                           c_est=any(u == Uso.CRONICO.value for u, _ in cfg.pares), pliegues=pliegues)
    datos, extras = _datos_de_receta(_solo_celdas(receta), U)
    entran = infos_res = dict(datos.estaciones)
    renormalizadas = dict(extras["renormalizadas"])
    fases.append("residuos")
    # π de cada uso (§5.3) con las horas válidas del paso 6. H15 (§5.3, la literal): las ≥ 2.000 horas de la banda y de
    # la distancia son todas las horas válidas (2000-2026); π^pob sigue por año en 2000-2025
    celdas_g = _parquet(leer_entrada(cfg, cfg.entrada("celdas")))
    pesos = _parquet(leer_entrada(cfg, cfg.entrada("pesos")))
    pob = pesos[["celda", "anio", "w_ghs"]].merge(celdas_g[["celda", "lat", "lon"]], on="celda", how="inner")
    pob = pob[pob["anio"].between(anios.start, anios.stop - 1).to_numpy(bool)]
    celdas_pobladas = pd.DataFrame({"anio": pob["anio"].astype(int), "lat": pob["lat"], "lon": pob["lon"],
                                    "w_ghs": pob["w_ghs"].astype(np.float64)})
    red2 = cfg.entrada("red2")
    pliegues_red2 = json.loads(leer_entrada(cfg, red2["pliegues"]))
    paneles = {pol_: {"tabla": _parquet(leer_entrada(cfg, a)), "sha256": cfg.huellas[a]}
               for pol_, a in red2["paneles"].items()}
    pi_pob, pi_mon, pi_sel = {}, {}, {}
    for k in validacion.CLAVES_HORAS:
        var = {"T": "T", "Td": "Td", "HR": "HR", "viento": "rapidez", "p": "p"}[k]
        por_anio = {a: pd.DataFrame({"codigo": sorted(entran), "lat": [entran[c].lat for c in sorted(entran)],
                                     "lon": [entran[c].lon for c in sorted(entran)],
                                     "horas": [horas_anio[k][a].get(c, 0) for c in sorted(entran)]}) for a in anios}
        pi_pob[k] = validacion.pi_poblacion(celdas_pobladas, por_anio, var, U)
        pi_mon[k] = validacion.pi_monitores(pliegues_red2, paneles, por_anio, var, U)
    for uso in (Uso.AMBIENTAL, Uso.AGUDO, Uso.CRONICO):
        pi_sel[uso.value] = {k: validacion.pi_uso(uso, pi_pob[k], pi_mon[k] if uso is Uso.AMBIENTAL else None,
                                                  umbrales=U) for k in validacion.CLAVES_HORAS}
    # 7. selección y predicción por pliegue externo (ORQ-11, ORQ-12) y producción (ORQ-13)
    sel_pliegue = _selecciones(cfg.pares)
    usos_prod = sorted({u for u, _ in cfg.pares})
    pares_prod = [(u, g) for u in usos_prod for (uu, g) in PARES if uu == u]
    sel_prod = _selecciones(pares_prod)
    d1, h1, d2, h2 = constantes.valor("ESTRATO_PERIODOS")
    periodos = {f"{d1}-{h1}": (d1, h1), f"{d2}-{h2}": (d2, h2)}
    ctx_sel = {"U": U, "receta": _para_seleccion(receta, cfg.recorte), "horas": horas, "pi_sel": pi_sel,
               "recorte": cfg.recorte, "pares": cfg.pares, "anchas": {c: ref_ancha[c] for c in cod_res},
               "periodos": periodos}                     # ORQ-36 (H1); ORQ-42: el fondo de los días de selección
    produccion = tipos.Pliegue("produccion", tipos.Particion.P2, prueba=(), entrenamiento=tuple(sorted(entran)))
    unidades_sel = [{"pliegue": p, "selecciones": sel_pliegue} for p in pliegues]
    unidades_sel.append({"pliegue": produccion, "selecciones": sel_prod, "produccion": True})
    resultados = repartir(unidades_sel, _unidad_seleccion, por_fase["seleccion_y_prediccion"], contexto=ctx_sel,
                          permitidas=cfg.permitidas, registro=repartos["seleccion_y_prediccion"])
    hiper_prod = resultados[-1]
    por_pliegue = resultados[:-1]
    fases.append("seleccion_y_prediccion")
    # 8. métricas (§5.2-§5.5)
    filas, descriptivas, anuales, finitud_est = [], [], {}, {}
    filas_periodo = {k: [] for k in periodos}
    for r in por_pliegue:
        filas += r["filas"]
        descriptivas += r["descriptivas"]
        anuales.update(r["anuales"])
        for k in periodos:
            filas_periodo[k] += r["periodos"][k]
        for clave, conteo in r["finitud"].items():
            finitud_est[clave] = finitud_est.get(clave, producto.ConteoFinito(0, 0)) + conteo
    evaluaciones = validacion.tabla_evaluaciones(filas)
    if any(u == Uso.CRONICO.value for u, _ in cfg.pares):
        evaluaciones = validacion.completar_cronico(evaluaciones, anuales, infos_res, U)
    ev_periodo = {k: validacion.tabla_evaluaciones(v) for k, v in filas_periodo.items()}
    banda = validacion.bandas_de_pliegues(pliegues, infos_res, horas, U)
    bloques = particiones.bloques_remuestreo(infos_res)
    fases.append("metricas")
    # 9. tendencias y finitud (§5.7; A24, A25)
    escenarios = {v: tendencias.escenarios_tf({a: horas_anio[k][a] for a in anios}, v, U)
                  for v, k in (("T", "T"), ("Td", "Td"), ("rapidez", "viento"), ("p", "p"))}
    cat_pix = _parquet(leer_entrada(cfg, cfg.entrada("catalogo_pixeles")))
    meses = _meses_ordenados(cfg)
    por_uso_tf, finitud_celdas = {}, {}
    for pasada_uso in sorted({"ambiental" if u == Uso.AMBIENTAL.value else "salud" for u in usos_prod}):
        cands = (("A", "B", "AB", "C") if pasada_uso == "ambiental" else
                 ("A", "B", "AB") + (("C",) if (Uso.AGUDO.value, Grupo.T_TD.value) in pares_prod else ())
                 + (("C_est",) if (Uso.CRONICO.value, Grupo.T_TD.value) in pares_prod else ()))
        uso_h = {"ambiental": Uso.AMBIENTAL.value, "salud": Uso.AGUDO.value}[pasada_uso]
        configuraciones = {}
        for cand in cands:
            u_c = Uso.CRONICO.value if cand == "C_est" else uso_h
            cfg_c = {}
            for (cc, var, uu), h in hiper_prod.items():
                if cc == cand and uu == u_c:
                    for pv in _PRODUCTO_SEL[var]:
                        cfg_c[pv] = h
            configuraciones[cand] = {ETIQUETA_PRODUCCION: cfg_c}
        variables = tendencias.VARIABLES_TF if pasada_uso == "ambiental" else ("T", "Td")
        args_pasada = {"receta": _solo_celdas(receta), "celdas": {"pasada_uso": pasada_uso,
                                                    "celdas": _ref_entrada(cfg, cfg.entrada("celdas")),
                                                    "pesos": _ref_entrada(cfg, cfg.entrada("pesos")),
                                                    "cat_pix": cat_pix},
                       "escenarios": {v: escenarios[v] for v in variables}, "configuraciones": configuraciones,
                       "variables": variables}                   # ORQ-36 (H1): la receta, no las tablas
        clave_pasada = _huella_unidad(corrida=avance.huella, pasada=pasada_uso)
        pasada, _, clima_n = _pasada_de({"clave_pasada": clave_pasada, "args_pasada": args_pasada, "U": U})
        anios_tf = set(pasada.anios())
        e0 = [(u, g, c) for (u, g) in cfg.pares
              if ("ambiental" if u == Uso.AMBIENTAL.value else "salud") == pasada_uso
              for c in validacion.CANDIDATOS_USO[Uso(u)]]
        unidades_tf = [{"mes": m, "ruta": str(ruta_de_alias(cfg.rutas, a)), "sha256": _exigir_huella(cfg, a),
                        "tf": int(_PATRON_MES.fullmatch(m)["anio"]) in anios_tf} for m, a in meses]
        ctx_tf = {"U": U, "clave_pasada": clave_pasada, "args_pasada": args_pasada, "h_ultima": _h_ultima(cfg),
                  "e0": e0}
        res_tf = repartir(unidades_tf, _unidad_mes_tf, por_fase["tendencias_y_finitud"], contexto=ctx_tf,
                          permitidas=cfg.permitidas, registro=repartos["tendencias_y_finitud"])
        medias = pasada.acumular([r["sumas"] for r in res_tf if "sumas" in r])
        por_uso_tf[pasada_uso] = tendencias.resultados_tf(medias, U)
        renormalizadas[f"celdas_{pasada_uso}"] = int(sum(r["renormalizadas"] for r in res_tf))
        if clima_n is not None:
            renormalizadas["clima_celdas_salud"] = clima_n
        for r in res_tf:
            for clave, conteo in r["finitud"].items():
                finitud_celdas[clave] = finitud_celdas.get(clave, producto.ConteoFinito(0, 0)) + conteo
    por_uso = tendencias.tf_por_uso(por_uso_tf.get("ambiental"), por_uso_tf.get("salud"))
    tf = tendencias.filas_tf(por_uso, escenarios)
    huellas_salida["tendencias/resumen_tf.parquet"] = _escribir(avance, "tendencias/resumen_tf.parquet", tf,
                                                                esquema=tipos.ESQUEMA_TF)
    motivos_e0 = {}
    for uso, grupo in cfg.pares:
        m = {}
        for cand in validacion.CANDIDATOS_USO[Uso(uso)]:
            motivos = []
            if cand in ("B", "AB") and not cfg.deriva[cand]:
                motivos.append("deriva")
            conteos = {"celdas": finitud_celdas.get((uso, grupo, cand), producto.ConteoFinito(0, 0)),
                       "estaciones": finitud_est.get((uso, grupo, cand), producto.ConteoFinito(0, 0))}
            if not producto.pasa_e0(conteos):
                motivos.append("finitud")
            if motivos:
                m[cand] = tuple(motivos)
        motivos_e0[(uso, grupo)] = m
    fases.append("tendencias_y_finitud")
    # métricas publicadas por par (con E0 ya conocido)
    publicadas, replicas, entradas_n, descriptivos_t, bandas_t, soporte_t = [], {}, {}, [], [], []
    for uso, grupo in cfg.pares:
        claves = sorted({validacion.HORAS_DE[v] for v in validacion.METRICAS[(Uso(uso), Grupo(grupo))]})
        pi = {k: pi_sel[uso][k] for k in claves}
        kw = {"uso": Uso(uso), "grupo": Grupo(grupo), "banda": banda, "pi": pi}
        ev = evaluaciones[(evaluaciones["uso"] == uso).to_numpy(bool)]
        per = {k: v[(v["uso"] == uso).to_numpy(bool)] for k, v in ev_periodo.items()}
        pub = validacion.estratos(ev, infos_res, U, periodos=per, **kw)
        e0 = tuple(c for c in validacion.CANDIDATOS_USO[Uso(uso)] if c not in motivos_e0[(uso, grupo)])
        rep = validacion.remuestreo(ev, bloques, U, infos=infos_res, e0=e0, **kw)
        publicadas.append(pub)
        replicas[(uso, grupo)] = rep
        descriptivos_t.append(validacion.tabla_descriptivos(ev, descriptivas, infos_res, U, **kw))
        bandas_t.append(validacion.tabla_bandas(ev, infos_res, U, uso=Uso(uso), grupo=Grupo(grupo), banda=banda,
                                                pi_pob={k: pi_pob[k] for k in claves},
                                                pi_mon={k: pi_mon[k] for k in claves} if uso == "ambiental" else None))
        soporte_t.append(validacion.fracciones_sin_soporte(ev, infos_res, U, periodos=per, **kw))
        entradas_n[(Uso(uso), Grupo(grupo))] = {"evaluaciones": ev, "banda": banda, "pi": pi, "bloques": bloques,
                                                "tf": tf[(tf["uso"] == uso).to_numpy(bool)],
                                                "motivos_e0": motivos_e0[(uso, grupo)]}
    puntajes = _concatenar(publicadas, tipos.ESQUEMA_VALIDACION_PUB)
    huellas_salida["validacion/puntajes.parquet"] = _escribir(avance, "validacion/puntajes.parquet", puntajes,
                                                              esquema=tipos.ESQUEMA_VALIDACION_PUB)
    for (uso, grupo), rep in replicas.items():
        nombre = f"validacion/remuestreo_{uso}_{grupo}.parquet"
        huellas_salida[nombre] = _escribir(avance, nombre, rep, esquema=tipos.ESQUEMA_REPLICAS)
    for nombre, partes, esquema in (("validacion/descriptivos.parquet", descriptivos_t,
                                     tipos.ESQUEMA_DESCRIPTIVOS_PUB),
                                    ("validacion/bandas.parquet", bandas_t, tipos.ESQUEMA_BANDAS_PUB),
                                    ("validacion/soporte.parquet", soporte_t, tipos.ESQUEMA_SOPORTE_PUB)):
        huellas_salida[nombre] = _escribir(avance, nombre, _concatenar(partes, esquema), esquema=esquema)
    huellas_salida["validacion/_interno/evaluaciones.parquet"] = _escribir(
        avance, "validacion/_interno/evaluaciones.parquet", evaluaciones, esquema=tipos.ESQUEMA_EVALUACIONES)
    # 10. RR06 (§2.6) y SINCA (§5.6), descriptivos
    rr06 = _rr06(cfg, _TablasAnchas(ref_ancha), infos, meses)              # ORQ-44: de a una, del disco
    huellas_salida["validacion/rr06.json"] = _escribir(avance, "validacion/rr06.json", rr06)
    sinca = _sinca(cfg)
    fases.append("rr06_y_sinca")
    # 11. decisión (§6.2)
    decisiones, hiper_json = [], {}
    for uso, grupo in cfg.pares:
        sub = puntajes[((puntajes["uso"] == uso) & (puntajes["grupo"] == grupo)).to_numpy(bool)].reset_index(drop=True)
        sub.attrs = dict(puntajes.attrs)
        entradas = tipos.EntradasDecision(Uso(uso), Grupo(grupo), sub, tf[(tf["uso"] == uso).to_numpy(bool)]
                                          .reset_index(drop=True), replicas[(uso, grupo)], motivos_e0[(uso, grupo)])
        d = decision.decidir_combinacion(Uso(uso), Grupo(grupo), entradas, umbrales=U)
        decisiones.append(d)
        entradas_n[(Uso(uso), Grupo(grupo))]["ganador"] = d.ganador
        hiper_json[f"{uso}/{grupo}"] = _hiper_de_par(uso, grupo, hiper_prod)
    replica = validacion.replica_n(entradas_n, infos_res, U, decidir=decision.decidir_combinacion)
    huellas_salida["validacion/replica_n.json"] = _escribir(avance, "validacion/replica_n.json",
                                                            _numeros_python(replica))
    huellas_dec = {**{entorno.alias(avance.carpeta / n, cfg.rutas): huellas_salida[n]
                      for n in ("validacion/puntajes.parquet", "tendencias/resumen_tf.parquet", salidas.POLITICA)},
                   **dict(sorted(cfg.huellas.items())), **m2a["huellas"], **huella_manifiestos}     # H9, H10
    registro_dec = decision.decision_json(decisiones, hiper_json, huellas_dec)
    huellas_salida[salidas.DECISION] = _escribir(avance, salidas.DECISION, registro_dec)
    fases.append("produccion_y_decision")
    _PASADAS.clear()
    registro = base_registro | {"sinca": sinca, "fases": [*fases, "sello"], "renormalizadas": renormalizadas,
                                "ganadores": {f"{d.uso.value}/{d.grupo.value}": d.ganador for d in decisiones}}
    return _sellar_m34(cfg, avance, m2a, registro, efectivas, registro_dec, huellas_salida, procesos,
                       huella_manifiestos, por_fase, repartos=repartos)


def _unidad_seleccion(unidad: Mapping, ctx: Mapping):
    ctx = _materializar(ctx)                      # ORQ-36 (H1): la receta y las tablas anchas, del disco
    if unidad.get("produccion"):
        return _unidad_produccion(unidad, ctx)
    return _unidad_pliegue(unidad, ctx)


def _hiper_de_par(uso: str, grupo: str, hiper: Mapping) -> dict:
    """ORQ-22: {candidato: {variable del producto: θ}} de un (uso, grupo), con θ tal cual (``tipos.Hiper`` en A y B,
    (Hiper de A, Hiper de Φ′) en AB y α en C y C_est), que ``decision.decision_json`` lleva a la forma de AMB-7:
    ``{"L_km", "lam", "kappa"}``, ``[θ de A, θ de Φ′]`` y α. «uv» va como u y v, con el mismo θ (MC-43)."""
    salida: dict = {}
    for (cand, var, uu), h in sorted(hiper.items(), key=lambda kv: kv[0]):
        if var not in _SEL_DE_PAR[grupo]:
            continue
        if (uso == Uso.CRONICO.value and ((cand == "C_est" and uu == uso) or (cand in ("A", "B", "AB")
                                                                               and uu == Uso.AGUDO.value))) \
                or (uso != Uso.CRONICO.value and cand != "C_est"
                    and uu == (Uso.AMBIENTAL.value if uso == Uso.AMBIENTAL.value else Uso.AGUDO.value)):
            for pv in _PRODUCTO_SEL[var]:
                salida.setdefault(cand, {})[pv] = h
    return salida


def _concatenar(partes, esquema):
    import pandas as pd
    df = pd.concat(partes, ignore_index=True) if partes else tipos.tabla_vacia(esquema)
    df = df.astype(dict(esquema))
    df.attrs = {"esquema": esquema.version}
    return df


def _horas_validas_anio(anchas, entran, anios) -> dict:
    """TEN-1, VAL-9: clave de horas → año → {código: horas válidas} (0 si no tiene)."""
    import numpy as np
    from meteo_combinada import tendencias, validacion
    col = {"T": "valido_T", "Td": "valido_Td", "HR": "valido_HR", "viento": "valido_viento", "p": "valido_p"}
    salida = {k: {a: {} for a in anios} for k in validacion.CLAVES_HORAS}
    for c in sorted(anchas):
        if c not in entran:
            continue
        anio = tendencias.anio_de(anchas[c]["h"].to_numpy(np.int64))
        for k in validacion.CLAVES_HORAS:
            v = anchas[c][col[k]].to_numpy(bool)
            for a in anios:
                n = int((v & (anio == a)).sum())
                if n:
                    salida[k][a][c] = n
    return salida


def _horas_de_una(horas_anio: dict, horas: dict, c: str, ancha, anios) -> None:
    """ORQ-44: suma a ``horas_anio`` y ``horas`` las horas válidas de una estación que entra; estación por estación,
    en el orden de los códigos, da lo mismo que ``_horas_validas_anio`` y ``_horas_validas_total`` con todas juntas
    (cada estación es su propia cuenta y su propia clave)."""
    un = {c: None}
    for k, por_anio in _horas_validas_anio({c: ancha}, un, anios).items():
        for a, n in por_anio.items():
            horas_anio[k][a].update(n)
    for k, n in _horas_validas_total({c: ancha}, un).items():
        horas[k].update(n)


def _horas_validas_total(anchas, entran) -> dict:
    """H15 (§5.3): clave de horas → {código: todas sus horas válidas} (todas las de su tabla ancha, 2000-2026), para
    el umbral de 2.000 horas de la banda y de la distancia al entrenamiento."""
    from meteo_combinada import validacion
    col = {"T": "valido_T", "Td": "valido_Td", "HR": "valido_HR", "viento": "valido_viento", "p": "valido_p"}
    return {k: {c: int(anchas[c][col[k]].to_numpy(bool).sum()) for c in sorted(entran) if c in anchas}
            for k in validacion.CLAVES_HORAS}


def _celdas_tf(pasada_uso: str, celdas_g, pesos, estaticos, clima_tabla, cat_pix, validos, z_tabla, U):
    """Las celdas pobladas de una pasada de TF (TEN-6, TEN-12), su operador (A24) y, en salud, los punto-mes-hora
    renormalizados del clima del estado (MC-39)."""
    import numpy as np
    from meteo_combinada import fondo_era5l, tendencias
    p20 = pesos[(pesos["anio"] == constantes.valor("TF_PESOS_ANIO")).to_numpy(bool)][["celda", "w_ghs"]]
    t = celdas_g[["celda", "lat", "lon", "cod_comuna"]].merge(p20, on="celda", how="inner").merge(
        estaticos, on="celda", how="inner", suffixes=("", "_est"))
    z_col = "z_media" if pasada_uso == "ambiental" else "z_poblada"
    ok = ((t["w_ghs"].to_numpy(np.float64) > 0) & (t["cod_comuna"].to_numpy(np.int64) > 0)
          & np.isfinite(t[z_col].to_numpy(np.float64)) & np.isfinite(t["lat"].to_numpy(np.float64)))
    t = t[ok].sort_values("celda").reset_index(drop=True)
    op = fondo_era5l.operador(t["lat"].to_numpy(np.float64), t["lon"].to_numpy(np.float64),
                              t[z_col].to_numpy(np.float64), cat_pix, validos, z_tabla, U,
                              ids=t["celda"].to_numpy(np.int64))
    est = t[list(tipos.ESQUEMA_ESTATICAS_CELDA_C)].copy()
    est.attrs = {"esquema": tipos.ESQUEMA_ESTATICAS_CELDA_C.version}
    clima, n_renorm = None, None
    if pasada_uso == "salud":
        cp = fondo_era5l.clima_en_puntos(clima_tabla, op, U)
        clima = {v: np.asarray(cp[v], dtype=np.float64) for v in tipos.VARIABLES_CLIMA_ESTADO}
        n_renorm = int(np.asarray(cp["renormalizada"]).sum())
    tabla = t[["celda", "lat", "lon", "cod_comuna", "w_ghs"]].copy()
    celdas = tendencias.celdas_tf(tabla, t[z_col].to_numpy(np.float64), estaticos=est, clima_estado=clima)
    return celdas, op, n_renorm


def _rr06(cfg: Cfg, anchas, infos, meses) -> dict:
    """§2.6 (D27, QC-21): la validación de RR06 con la lluvia de 6 h ERA5-Land por el píxel enlazado (ORQ-37)."""
    from meteo_combinada import qc_dmc_meteo as Q
    tablas = anchas if isinstance(anchas, _TablasAnchas) else {c: anchas[c] for c in sorted(anchas)}
    return _numeros_python(Q.validar_rr06(tablas, _sumas_rr06(cfg, tablas, infos, meses), infos, cfg.U))


def _sumas_rr06(cfg: Cfg, tablas, infos, meses) -> dict:
    """ORQ-37 (H2): código → (suma de 6 h, sin enlace), alineadas con las filas de su tabla ancha, por lotes de un año."""
    import numpy as np
    from meteo_combinada import fondo_era5l
    from meteo_combinada import qc_dmc_meteo as Q
    enlaces = _parquet(leer_entrada(cfg, cfg.entrada("enlaces")))
    sumas = None
    # H2 (ORQ-37): lotes de un año (y, dentro del año, de meses contiguos), con el último día del mes anterior delante
    # si es contiguo, para las ventanas de 6 h que cruzan el 1 de enero; ``previas`` sólo llena lo que sigue NaN, así
    # que da lo mismo que un solo lote con todos los meses contiguos.
    lotes: list[list] = []
    for m, a in meses:
        previo = lotes[-1][-1][0] if lotes else None
        nuevo = (previo is None or _PATRON_MES.fullmatch(m)["anio"] != _PATRON_MES.fullmatch(previo)["anio"]
                 or _horas_mes(m)[0] != _horas_mes(previo)[1])
        if nuevo:
            lotes.append([])
        lotes[-1].append((m, a))
    ultimo = None                                     # (AAAAMM, su último día UTC) del lote anterior
    for lote in lotes:
        serie = [_leer_mes(cfg, a) for _, a in lote]
        delante = [ultimo[1]] if ultimo is not None and _horas_mes(lote[0][0])[0] == _horas_mes(ultimo[0])[1] else []
        completa = delante + serie
        sumas = Q.sumas_lluvia_rr06(tablas, infos, enlaces, fondo_era5l.incrementos_tp(completa),
                                    h=fondo_era5l.horas_de(completa), pixel_ids=np.asarray(completa[0].pixel_id),
                                    previas=sumas)
        fin = serie[-1]
        dia = slice(max(0, len(fin.tiempos) - _HORAS_DIA), len(fin.tiempos))
        ultimo = (lote[-1][0], fondo_era5l.MesE5L(tiempos=np.asarray(fin.tiempos)[dia], pixel_id=fin.pixel_id,
                                                  datos={k: np.asarray(v)[dia] for k, v in fin.datos.items()},
                                                  sha256=fin.sha256))
        del serie, completa
    return sumas


def _sinca(cfg: Cfg) -> dict:
    """§5.6 (ORQ-19): la red SINCA, si está en las entradas: manifiestos, series elegidas y series horarias con los
    veredictos del reloj SINCA. La comparación con el producto (``validacion.validacion_sinca``) necesita el producto
    de T, HR y viento en la celda y en el punto de cada estación SINCA, y los manifiestos no traen coordenadas: queda
    declarada como pendiente (pregunta P-ORQ-1)."""
    from meteo_combinada import sinca_meteo
    sinca = cfg.entradas.get("sinca")
    if sinca is None:
        return {"estado": "sin_red"}
    raiz = ruta_de_alias(cfg.rutas, sinca["raiz"])
    huellas = {PurePosixPath(a).name: cfg.huellas[a] for a in sinca["archivos"]}
    manifiesto = sinca_meteo.leer_manifiestos(raiz, huellas)
    elegidas = sinca_meteo.elegir_series(manifiesto, cfg.U)
    politica = json.loads(leer_entrada(cfg, sinca["politica_temporal"]))
    veredictos = sinca_meteo.veredictos_civiles(
        _parquet(leer_entrada(cfg, sinca["veredictos"])), sinca["convencion"],
        sha256=cfg.huellas[sinca["veredictos"]], resumen=json.loads(leer_entrada(cfg, sinca["resumen"])))
    series = sinca_meteo.series_horarias(raiz, elegidas, politica, cfg.U, veredictos=veredictos)
    ambientales = {(Uso.AMBIENTAL.value, Grupo.T_TD.value), (Uso.AMBIENTAL.value, Grupo.U_V.value)}
    estado = "leida_sin_coordenadas" if ambientales <= set(cfg.pares) else "leida_sin_producto"
    return {"estado": estado, "series": int(len(elegidas)), "horas_validas": int(series["valido"].sum())}


def _sellar_m34(cfg, avance, m2a, registro, efectivas, registro_dec, huellas_salida, procesos,
                huella_manifiestos, por_fase: Mapping[str, int] | None = None, *,
                repartos: Mapping[str, Sequence[Mapping]] | None = None) -> dict:
    """§2.5, paso 12: la política efectiva (si no se escribió antes, H10), el registro y el sello (``sha256.json`` y el
    recibo, con los procesos de cada fase que reparte, ORQ-45), con la huella agregada de los manifiestos (H9)."""
    from meteo_combinada import politicas
    if salidas.POLITICA not in huellas_salida:
        huellas_salida[salidas.POLITICA] = _escribir(avance, salidas.POLITICA, politicas.a_json(efectivas))
    registro = _sin_palabras(_numeros_python({**registro, "huellas": {
        **{entorno.alias(avance.carpeta / n, cfg.rutas): s for n, s in sorted(huellas_salida.items())},
        **dict(sorted(cfg.huellas.items())), **m2a["huellas"], **huella_manifiestos}}))
    sha_reg = _escribir(avance, REGISTRO_M34, registro)
    recibo = salidas.sellar_corrida(avance.carpeta, {**dict(cfg.huellas), **m2a["huellas"], **huella_manifiestos},
                                    _entorno_recibo(procesos, por_fase, repartos=repartos), rutas=cfg.rutas)
    return {"registro": registro, "registro_sha256": sha_reg, "decision": registro_dec, "recibo_sha256": recibo,
            "carpeta": avance.carpeta}


# ---------------------------------------------------------------------------
# M5 y M6: segunda fase de la ola 5
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Lo que los trabajadores leen del disco (ORQ-36; H1)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _Ref:
    """ORQ-36 (H1): un archivo que un trabajador lee del disco, con su sha256 (la de ``sha256.json`` de la corrida o
    la de la lista cerrada): viaja la referencia, no la tabla."""
    ruta: str
    sha256: str


_TABLAS: dict[tuple, Any] = {}                   # por proceso: las tablas que se releen (paneles), por su sha256
_DATOS: dict[str, tuple] = {}                    # por proceso: la DatosCompetencia de la receta en uso
_SALUD: dict[str, dict] = {}                     # por proceso: las celdas de salud de la receta en uso
_M2A_DATOS = ("estaticas/celdas.parquet", "estaticas/z_e5l.parquet", "insumos/clima_estado.parquet",
              "estaticas/estaciones.parquet")


def _bytes_de(ref: _Ref) -> bytes:
    return _leer_propio(Path(ref.ruta), ref.sha256)


def _tabla_de(ref: _Ref):
    return _parquet(_bytes_de(ref))


def _ref_de_archivo(carpeta: Path, nombre: str, sha: str) -> _Ref:
    return _Ref(str(carpeta / nombre), str(sha))


def _ref_entrada(cfg: Cfg, alias_: str) -> _Ref:
    """Una entrada de la lista cerrada como referencia (ORQ-1, ORQ-36)."""
    return _Ref(str(ruta_de_alias(cfg.rutas, alias_)), _exigir_huella(cfg, alias_))


def _receta_datos(ref_corrida: Callable, ref_m2a: Callable, codigos, *, c_est: bool, pliegues=()) -> dict:
    """ORQ-36 (H1): lo que hace falta para rearmar la ``DatosCompetencia`` de producción desde el disco, con
    ``_datos_produccion`` (la misma de M3-4): las referencias de los residuos, de A, de los tramos y de lo de M2a."""
    cods = sorted(codigos)
    receta = {"residuos": {c: ref_corrida(f"producto/residuos/{c}.parquet") for c in cods},
              "clima_a": ref_corrida("producto/clima_a.parquet"),
              "tramos": ref_corrida("producto/tramos_homogeneos.parquet"),
              "m2a": {n: ref_m2a(n) for n in (*_M2A_DATOS, *(f"insumos/puntos_estacion/{c}.parquet" for c in cods))},
              "c_est": bool(c_est), "pliegues": tuple(pliegues)}
    receta["clave"] = _huella_unidad(residuos={c: r.sha256 for c, r in receta["residuos"].items()},
                                     clima_a=receta["clima_a"].sha256, tramos=receta["tramos"].sha256,
                                     m2a={n: r.sha256 for n, r in receta["m2a"].items()}, c_est=receta["c_est"],
                                     pliegues=repr(receta["pliegues"]))
    return receta


def _solo_celdas(receta: Mapping) -> dict:
    """ORQ-36 (H1): la misma receta para lo que se calcula en celdas (TF, M5, M6): sin el fondo ni el clima del estado
    en las estaciones, que sólo usan las filas de C (ya armadas) y las estaciones de prueba de la selección."""
    return {**receta, "solo_celdas": True}


def _para_seleccion(receta: Mapping, recorte: bool) -> dict:
    """ORQ-42 (PED-10): la misma receta para la selección y la evaluación de los pliegues externos: el fondo de cada
    estación sólo en las horas de los días de selección (mód ``SEL_MOD``, o ``SEL_MOD_RECORTE`` con el recorte), que es
    todo lo que la selección lee de él (CAN-19 (5)); el de las estaciones de prueba de cada pliegue externo se lee
    entero del disco en su unidad (``_fondo_de_prueba``)."""
    if not isinstance(recorte, bool):
        raise ErrorOrquestacion("el recorte de la selección es True o False (lo fija el addendum de M1)")
    return {**receta, "fondo_seleccion": recorte}


def _variante(receta: Mapping) -> tuple:
    """ORQ-36, ORQ-42: («ligera»,) sin el fondo ni el clima de las estaciones; («seleccion», recorte) con el fondo en
    los días de selección; («completa»,) con todo."""
    if receta.get("solo_celdas"):
        return ("ligera",)
    if "fondo_seleccion" in receta:
        return ("seleccion", bool(receta["fondo_seleccion"]))
    return ("completa",)


def _fondo_en_seleccion(F, U, recorte: bool):
    """ORQ-42: las filas del fondo de una estación (``ESQUEMA_PUNTOS_E5L``) en los días de selección, en su orden y con
    sus mismos valores y tipos (``estado_c`` las busca por hora: las de la selección están todas), con el índice de 0 a
    n − 1 (un ``RangeIndex``, sin los 8 B por fila del índice de las filas tomadas; nadie lee el índice)."""
    import pandas as pd
    from meteo_combinada import particiones
    salida = F[particiones.dias_de_seleccion(F["h"].to_numpy(), U, recorte=recorte)]
    salida.index = pd.RangeIndex(len(salida))
    salida.attrs = dict(F.attrs)
    return salida


def _fondo_de_prueba(receta: Mapping) -> Callable:
    """ORQ-42: el fondo entero de una estación, del disco con su sha256 (el mismo que lee ``_datos_de_receta``)."""
    return lambda c: _parquet(_bytes_de(receta["m2a"][f"insumos/puntos_estacion/{c}.parquet"]))


def _derivar_datos(datos, tiene: tuple, pedida: tuple, U):
    """ORQ-36, ORQ-42: la variante pedida desde la guardada, si sale de ella sin rearmar (None si no)."""
    if pedida == ("ligera",):
        return dataclasses.replace(datos, puntos_e5l={}, clima_estado={})
    if pedida[0] == "seleccion" and tiene == ("completa",):
        return dataclasses.replace(datos, puntos_e5l={c: _fondo_en_seleccion(F, U, pedida[1])
                                                      for c, F in datos.puntos_e5l.items()})
    return None


def _datos_de_receta(receta: Mapping, U) -> tuple:
    """(DatosCompetencia, lo de M2a) de una receta, armados una vez por proceso (ORQ-36): el proceso principal y los
    trabajadores corren la misma cuenta sobre los mismos bytes, así que dan los mismos bits. Se guarda una sola variante
    (``_variante``): la ligera (``solo_celdas``) va sin ``puntos_e5l`` ni ``clima_estado`` de las estaciones (los
    módulos de las celdas no los leen: ``candidatos`` sólo los usa en las filas de C y en las estaciones de prueba); la
    de la selección, con el fondo en los días de selección (ORQ-42). El fondo de cada estación se lee del disco de a
    una, para sus filas de C, y se guarda sólo lo que la variante usa: ningún proceso tiene el fondo entero de todas las
    estaciones salvo el que pide la completa (ninguno en M3-4, M5 ni M6, ORQ-44)."""
    clave, pedida = receta["clave"], _variante(receta)
    guardada = _DATOS.get(clave)
    if guardada is not None and guardada[2] != pedida:
        derivada = _derivar_datos(guardada[0], guardada[2], pedida, U)
        guardada = None if derivada is None else (derivada, guardada[1], pedida)
        _DATOS.clear()                      # la anterior se suelta (la completa se rearma si se vuelve a pedir)
        if guardada is not None:
            _DATOS[clave] = guardada
    if guardada is None:
        _DATOS.clear()
        m2a = {"leer": lambda n: _bytes_de(receta["m2a"][n])}
        residuos = {c: _tabla_de(r) for c, r in receta["residuos"].items()}
        infos = infos_de_tabla(_parquet(m2a["leer"]("estaticas/estaciones.parquet")))
        if pedida[0] == "seleccion":
            guardar = lambda F: _fondo_en_seleccion(F, U, pedida[1])        # noqa: E731
        else:
            guardar = (lambda F: None) if pedida == ("ligera",) else (lambda F: F)     # noqa: E731
        datos, extras = _datos_produccion(residuos, _tabla_de(receta["clima_a"]), _tabla_de(receta["tramos"]), m2a,
                                          infos, _fondo_de_prueba(receta), U, c_est=receta["c_est"], guardar=guardar)
        if pedida == ("ligera",):
            datos = dataclasses.replace(datos, puntos_e5l={}, clima_estado={})
        if receta["pliegues"]:
            datos = dataclasses.replace(datos, pliegues=tuple(receta["pliegues"]))
        guardada = _DATOS[clave] = (datos, extras, pedida)
    return guardada[0], guardada[1]


_COLUMNAS_ANCHAS = ("h", *dict.fromkeys(x for par in _OBS.values() for x in par))
_COLUMNAS_VALIDAS = ("h", "valido_T", "valido_Td", "valido_HR", "valido_viento", "valido_p")    # las horas válidas


def _ancha_de(ref: _Ref, columnas=_COLUMNAS_ANCHAS):
    """ORQ-36, ORQ-44: una tabla ancha de control de calidad desde su referencia (o sus bytes ya leídos con su huella),
    sólo con las columnas que usan los residuos, las horas válidas y la evaluación (la hora, las observaciones y su
    validez), sin sus metadatos."""
    import pyarrow.parquet as pq
    datos = ref if isinstance(ref, bytes) else _bytes_de(ref)
    df = pq.read_table(io.BytesIO(datos), columns=list(columnas)).to_pandas()
    df.attrs = {}
    return df


class _Anchas(Mapping):
    """ORQ-36 (H1): las tablas anchas de control de calidad por demanda, desde sus referencias (cada unidad lee sólo
    las de sus estaciones de prueba) y sólo con las columnas que usa la evaluación (``_ancha_de``)."""
    COLUMNAS = _COLUMNAS_ANCHAS

    def __init__(self, refs: Mapping[str, _Ref]):
        self._refs, self._leidas = dict(refs), {}

    def __getitem__(self, c):
        if c not in self._leidas:
            self._leidas[c] = _ancha_de(self._refs[c])
        return self._leidas[c]

    def __iter__(self):
        return iter(self._refs)

    def __len__(self):
        return len(self._refs)


class _TablasAnchas(Mapping):
    """ORQ-44: las tablas anchas enteras (``ESQUEMA_QC_ESTACION``, con sus metadatos fuera, como las dejaba M3-4 en
    memoria) que lee RR06, cada vez desde el disco con su huella y sin guardarlas: ``qc_dmc_meteo`` las recorre de a
    una, así que el principal no tiene a la vez las de todas las estaciones."""

    def __init__(self, refs: Mapping[str, _Ref]):
        self._refs = dict(sorted(refs.items()))

    def __getitem__(self, c):
        df = _tabla_de(self._refs[c])
        df.attrs = {"esquema": tipos.ESQUEMA_QC_ESTACION.version}
        return df

    def __iter__(self):
        return iter(self._refs)

    def __len__(self):
        return len(self._refs)


def _materializar(ctx: Mapping) -> dict:
    """ORQ-36 (H1): el contexto de una unidad con lo que se rearma del disco: la ``DatosCompetencia`` de su receta (una
    vez por proceso), las estaciones y su fondo, y las tablas anchas por demanda."""
    salida = dict(ctx)
    if "receta" in ctx:
        datos, extras = _datos_de_receta(ctx["receta"], ctx["U"])
        salida.update({"datos": datos, "infos": datos.estaciones, "F": datos.puntos_e5l, "extras": extras})
        if _variante(ctx["receta"])[0] == "seleccion":
            salida["fondo_prueba"] = _fondo_de_prueba(ctx["receta"])          # ORQ-42
    if "anchas" in ctx and not isinstance(ctx["anchas"], _Anchas):
        salida["anchas"] = _Anchas(ctx["anchas"])
    return salida


def _datos_produccion(residuos, clima_a, tramos, m2a, infos, fondo: Callable, U, *, c_est: bool,
                      guardar: Callable = lambda F: F) -> tuple:
    """M3-4 (paso 6) y la producción de M5 y M6 (ORQ-21): la ``DatosCompetencia`` de las estaciones con residuos, sin
    pliegues (los pone M3-4), con los estáticos de sus celdas, su fondo, su clima del estado (A14) y las filas de C (y
    de C_est con ``c_est``); y lo de M2a que se usa después: los estáticos de todas las celdas, z_E5L, los píxeles
    válidos, el clima del estado y los punto-hora renormalizados del clima en las estaciones (MC-39).

    ORQ-42: ``fondo(código)`` da el fondo entero de una estación y se pide de a una, en el orden de los códigos: con él
    salen sus filas de C (``candidatos.filas_c`` de esa estación sola: cada estación es su propia cuenta, con su propia
    semilla, así que es el mismo diccionario, en el mismo orden, que con todas juntas) y queda en ``puntos_e5l`` lo que
    da ``guardar`` (el fondo entero, el de los días de selección, o nada si da None)."""
    import numpy as np
    from meteo_combinada import candidatos, fondo_era5l
    entran = {c: infos[c] for c in sorted(residuos)}             # las que entran y tienen datos (PAR-1)
    estaticos_m2a = _parquet(m2a["leer"]("estaticas/celdas.parquet"))
    celdas_est = sorted({int(i.celda) for c, i in entran.items() if i.celda is not None})
    estaticos = estaticos_m2a[estaticos_m2a["celda"].isin(celdas_est).to_numpy(bool)].reset_index(drop=True)
    estaticos.attrs = {"esquema": tipos.ESQUEMA_ESTATICAS_CELDA_C.version}
    z_tabla = _parquet(m2a["leer"]("estaticas/z_e5l.parquet"))
    validos = z_tabla.loc[z_tabla["valido"].to_numpy(bool), "pixel_id"].to_numpy(np.int64)
    clima_tabla = _parquet(m2a["leer"]("insumos/clima_estado.parquet"))
    cod_res = sorted(residuos)
    tabla_est = _parquet(m2a["leer"]("estaticas/estaciones.parquet")).set_index("codigo").loc[cod_res].reset_index()
    op_res = fondo_era5l.operador_desde_columnas(np.array(cod_res, dtype=object), tabla_est["z_s"].to_numpy(np.float64),
                                                 tabla_est, z_tabla)
    clima_p = fondo_era5l.clima_en_puntos(clima_tabla, op_res, U)
    clima_estado = {c: {v: np.asarray(clima_p[v][j], dtype=np.float64) for v in tipos.VARIABLES_CLIMA_ESTADO}
                    for j, c in enumerate(cod_res)}
    renormalizadas = {"clima_estaciones": int(np.asarray(clima_p["renormalizada"]).sum())}      # MC-39, A14
    F_res = {}
    filas = candidatos.filas_c({}, estaticos, {}, U, infos=entran)  # las mismas comprobaciones primero, sin estaciones
    for c in cod_res:
        F_c = fondo(c)
        for v, por_codigo in candidatos.filas_c({c: residuos[c]}, estaticos, {c: F_c}, U, infos=entran).items():
            filas[v].update(por_codigo)
        guardado = guardar(F_c)
        if guardado is not None:
            F_res[c] = guardado
        del F_c, guardado
    filas_c = {Candidato.C.value: filas}
    if c_est:
        filas_c[Candidato.C_EST.value] = candidatos.filas_c(residuos, estaticos, clima_estado, U, infos=entran,
                                                            climatologico=True)
    datos = tipos.DatosCompetencia(residuos=residuos, climatologias=clima_a, tramos=tramos, filas_c=filas_c,
                                   estaticos=estaticos, estaciones=entran, pliegues=(), puntos_e5l=F_res,
                                   clima_estado=clima_estado)
    return datos, {"estaticos_m2a": estaticos_m2a, "z_tabla": z_tabla, "validos": validos, "clima_tabla": clima_tabla,
                   "renormalizadas": renormalizadas}


# ---------------------------------------------------------------------------
# M5 y M6: lo común (ORQ-20 a ORQ-28)
# ---------------------------------------------------------------------------
_GRUPOS_AMBIENTALES = (Grupo.T_TD.value, Grupo.U_V.value, Grupo.P.value)
_VARIANTES = (tipos.Variante.I.value, tipos.Variante.D.value)
_CON_B_AB = (Candidato.B.value, Candidato.AB.value)
_OPERADORES: dict[str, Any] = {}


def _theta_de_json(cand: str, x, donde: str):
    """ORQ-22: θ desde la forma de AMB-7 (``decision._a_json``): ``{"L_km", "lam", "kappa"}`` en A y B, ``[θ de A,
    θ de Φ′]`` en AB y α en C y C_est."""
    def hiper(y):
        if not isinstance(y, Mapping) or set(y) != {"L_km", "lam", "kappa"}:
            raise ErrorOrquestacion(f"{donde}: los hiperparámetros del núcleo son {{L_km, lam, kappa}} (AMB-7)")
        return tipos.Hiper(float(y["L_km"]), float(y["lam"]), float(y["kappa"]))
    if cand in (Candidato.C.value, Candidato.C_EST.value):
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            raise ErrorOrquestacion(f"{donde}: el hiperparámetro de {cand} es α (AMB-7)")
        return float(x)
    if cand == Candidato.AB.value:
        if not isinstance(x, (list, tuple)) or len(x) != 2:
            raise ErrorOrquestacion(f"{donde}: los hiperparámetros de AB son [θ de A, θ de Φ′] (AMB-7)")
        return (hiper(x[0]), hiper(x[1]))
    return hiper(x)


def _decision_de(contenido: Mapping, uso: str, grupo: str) -> Mapping:
    """La decisión de un (uso, grupo) de ``decision.json``."""
    halladas = [d for d in contenido.get("decisiones", ()) if d.get("uso") == uso and d.get("grupo") == grupo]
    if len(halladas) != 1:
        raise ErrorOrquestacion(f"decision.json no trae exactamente una decisión de {uso}/{grupo}")
    return halladas[0]


def _hiper_de_decision(d: Mapping, cand: str) -> dict:
    """{variable del producto: θ} de un candidato en una decisión (ORQ-22), con el grupo entero."""
    from meteo_combinada import producto
    variables = producto.VARIABLES_DE_GRUPO[Grupo(d["grupo"])]
    hip = d.get("hiperparametros", {}).get(cand)
    if not isinstance(hip, Mapping) or set(hip) != set(variables):
        raise ErrorOrquestacion(f"decision.json no trae los hiperparámetros de {cand} en {d['uso']}/{d['grupo']} para "
                                f"{list(variables)} (AMB-7)")
    return {v: _theta_de_json(cand, hip[v], f"{d['uso']}/{d['grupo']}/{cand}/{v}") for v in variables}


def _ganador_y_hiper(contenido: Mapping, uso: str) -> tuple[str, dict]:
    """(ganador, {T, Td: θ}) de lo agudo o lo crónico (§6.1: sólo (T, Td))."""
    d = _decision_de(contenido, uso, Grupo.T_TD.value)
    return str(d["ganador"]), _hiper_de_decision(d, str(d["ganador"]))


def _filas_por_celda(tabla, celdas, que: str):
    """Las filas de ``tabla`` (con «celda») de cada celda pedida, en su orden; error si falta alguna."""
    import numpy as np
    c = tabla["celda"].to_numpy(np.int64)
    orden = np.argsort(c, kind="stable")
    pedidas = np.asarray(celdas, dtype=np.int64)
    pos = np.searchsorted(c[orden], pedidas)
    ok = (pos < c.size) & (c[orden][np.minimum(pos, max(c.size - 1, 0))] == pedidas) if c.size else pedidas < 0
    if not bool(np.all(ok)):
        raise ErrorOrquestacion(f"{que}: faltan {int((~ok).sum())} celdas")
    salida = tabla.iloc[orden[pos]].reset_index(drop=True)
    salida.attrs = dict(tabla.attrs)
    return salida


def _pesos_del_anio(pesos, anio: int):
    """ORQ-26 (SAL-6): las filas de ``poblacion_celda_anio`` del año de los pesos (el del producto llevado al rango de
    la tabla, como ``salud``), para no mandar la tabla entera a cada unidad."""
    import numpy as np
    anios = np.unique(pesos["anio"].to_numpy(np.int64))
    if anios.size == 0:
        raise ErrorOrquestacion("la tabla de pesos no tiene años")
    a = int(min(max(int(anio), int(anios[0])), int(anios[-1])))
    return pesos[pesos["anio"].to_numpy(np.int64) == a].reset_index(drop=True)


def _operador_de_disco(ref) -> Any:
    """El ``ambiental.OperadorGrilla`` de ``ambiental/operador_grilla.bin`` (ruta y sha256), leído una vez por proceso
    (ORQ-28)."""
    from meteo_combinada import ambiental
    ruta, sha = (ref.ruta, ref.sha256) if isinstance(ref, _Ref) else ref
    if sha not in _OPERADORES:
        _OPERADORES.clear()
        _OPERADORES[sha] = ambiental.leer_operador(_leer_propio(Path(ruta), sha), sha256=sha)
    return _OPERADORES[sha]


class _LectorMeses:
    """AAAAMM → ``fondo_era5l.MesE5L`` de la lista cerrada, con su huella, sus unidades y sus horas (FON-1; AMB-9);
    guarda en memoria sólo el último mes."""

    def __init__(self, cfg: Cfg):
        self._cfg = cfg
        self._por_mes = dict(_meses_ordenados(cfg))
        self._ultimo: tuple | None = None

    def __call__(self, yyyymm):
        clave = str(int(yyyymm))
        if self._ultimo is None or self._ultimo[0] != clave:
            if clave not in self._por_mes:
                raise ErrorOrquestacion(f"falta el mes ERA5-Land {clave} en meses_era5l (ORQ-1)")
            self._ultimo = (clave, _leer_mes(self._cfg, self._por_mes[clave]))
        return self._ultimo[1]


def _produccion(cfg: Cfg, carpeta_corrida: Path, que: str, *, c_est: bool | None) -> dict:
    """ORQ-21: lo que M5 y M6 leen de M2a y de M3-4 (cada archivo con la huella de su ``sha256.json``) y de la lista
    cerrada, y la ``DatosCompetencia`` de producción, rearmada de su receta (ORQ-36) con la misma función que M3-4.
    ``c_est``: None arma las filas de C_est si el ganador crónico es C_est."""
    from meteo_combinada import ambiental
    U = cfg.U
    m2a = _leer_m2a(cfg)
    corrida = _leer_carpeta(cfg, carpeta_corrida, que)
    dec_bytes = corrida["leer"](salidas.DECISION)
    contenido, _ = ambiental.leer_decision(dec_bytes)
    prefijo = "producto/residuos/"
    cod_res = sorted(PurePosixPath(n).stem for n in corrida["inventario"]
                     if n.startswith(prefijo) and n.endswith(".parquet"))
    if not cod_res:
        raise ErrorOrquestacion(f"{que} no trae residuos (producto/residuos/)")
    if c_est is None:
        c_est = _decision_de(contenido, Uso.CRONICO.value, Grupo.T_TD.value)["ganador"] == Candidato.C_EST.value
    receta = _solo_celdas(_receta_datos(corrida["ref"], m2a["ref"], cod_res, c_est=c_est))   # ORQ-36: en celdas
    datos, extras = _datos_de_receta(receta, U)
    return {"m2a": m2a, "corrida": corrida, "decision_bytes": dec_bytes, "decision": contenido, "datos": datos,
            "receta": receta, **extras, "celdas_g": _parquet(leer_entrada(cfg, cfg.entrada("celdas"))),
            "cat_pix": _parquet(leer_entrada(cfg, cfg.entrada("catalogo_pixeles"))),
            "pesos": _parquet(leer_entrada(cfg, cfg.entrada("pesos"))),
            "politica_bytes": corrida["leer"](salidas.POLITICA)}


def _base_de(avance: Avance, p: Mapping, **mas) -> str:
    """La huella común de las unidades de M5 o M6: la de la corrida, lo leído de M3-4 (o M5) y M2a (ORQ-8, ORQ-21)."""
    return _huella_unidad(corrida=avance.huella, leidos=dict(sorted(p["corrida"]["leidos"].items())),
                          m2a=p["m2a"]["huellas"], **mas)


def _unidad_unica(avance: Avance, fase: str, unidad: str, entrada: str, nombre: str, producir: Callable, *,
                  esquema=None) -> str:
    """ORQ-8: una unidad de un archivo; ``producir()`` → (contenido, metadatos) sólo si no está hecha."""
    hecha = avance.hecha(fase, unidad, entrada)
    if hecha is not None and nombre in hecha["archivos"]:
        avance.saltadas.append(unidad)
        return hecha["archivos"][nombre]
    avance.parcial_pendiente([nombre], unidad)
    contenido, metadatos = producir()
    sha = _escribir(avance, nombre, contenido, esquema=esquema, metadatos=metadatos)
    avance.registrar(fase, unidad, entrada, {nombre: sha})
    return sha


def _producto_salud(nombre: str, ganador: Mapping, hiper: Mapping, uso: str, entrenamiento, tipos_dia) -> dict:
    """Un producto de salud de las unidades anuales (ORQ-26): nombre, ganador {grupo: candidato}, hiperparámetros,
    el uso de ``producto`` (C_est sólo en lo crónico), el entrenamiento (None: el de producción) y los tipos de día."""
    return {"nombre": nombre, "ganador": dict(ganador), "hiper": dict(hiper), "uso": uso,
            "entrenamiento": None if entrenamiento is None else tuple(entrenamiento), "tipos_dia": tuple(tipos_dia)}


def _clave_producto(p: Mapping) -> str:
    return repr((sorted(p["ganador"].items()), sorted((k, repr(v)) for k, v in p["hiper"].items()), p["uso"],
                 p["entrenamiento"]))


def _estaticos_pixeles(lat, lon, celdas_g, estaticos_m2a):
    """ORQ-25 (P84, rige la a): los estáticos de C en los centros de píxel son los de la celda que contiene el centro,
    con los bordes oeste y sur cerrados (la noreste), como en una estación. Un centro sin celda en la grilla detiene."""
    import numpy as np
    from meteo_combinada import estaticas_nasadem as EN
    clave = {(int(a), int(b)): int(c) for (a, b), c in zip(
        EN.celda_de_puntos(celdas_g["lat"].to_numpy(np.float64), celdas_g["lon"].to_numpy(np.float64)).tolist(),
        celdas_g["celda"].tolist())}
    celdas = np.array([clave.get((int(a), int(b)), -1) for a, b in EN.celda_de_puntos(lat, lon).tolist()],
                      dtype=np.int64)
    if (celdas < 0).any():
        raise ErrorOrquestacion(f"C gana un grupo ambiental y {int((celdas < 0).sum())} centros de píxel válidos no "
                                "tienen celda en la grilla: sus estáticos no están definidos (P84; pregunta P-ORQ-5)")
    est = _filas_por_celda(estaticos_m2a, celdas, "estáticos de los píxeles")
    est.attrs = {"esquema": tipos.ESQUEMA_ESTATICAS_CELDA_C.version}
    return est, celdas


def _contexto_pixeles(p: Mapping, ganador: Mapping, hiper: Mapping, huellas: Mapping) -> dict:
    """ORQ-25 (MC-08, A10): el 0,1° en los centros de los píxeles válidos, con z = z_E5L y el ganador ambiental."""
    import numpy as np
    from meteo_combinada import fondo_era5l
    pid = np.sort(np.asarray(p["validos"], dtype=np.int64))
    op = fondo_era5l.operador_pixeles(pid, p["cat_pix"], p["validos"], p["z_tabla"])
    cat = p["cat_pix"].set_index("pixel_id").loc[pid]
    puntos = {"ids": np.asarray(op.ids), "lat": cat["latitude"].to_numpy(np.float64),
              "lon": cat["longitude"].to_numpy(np.float64), "z": np.asarray(op.z, dtype=np.float64)}
    estaticos, celdas = None, None
    if Candidato.C.value in ganador.values():
        estaticos, celdas = _estaticos_pixeles(puntos["lat"], puntos["lon"], p["celdas_g"], p["estaticos_m2a"])
    return {"op": op, "puntos": puntos, "ganador": dict(ganador), "hiper": dict(hiper), "estaticos": estaticos,
            "celdas": celdas, "huellas": dict(huellas)}


def _salud_de(receta: Mapping, extras: Mapping, U) -> dict:
    """ORQ-26, ORQ-36: las celdas de salud (cod_comuna > 0 y z_poblada finita; §3: «usos de salud: z = media NASADEM
    ponderada por la población»), su operador del fondo, sus estáticos, la grilla y los enlaces de la lluvia, armados
    una vez por proceso desde las referencias de la receta (el principal y los trabajadores, con la misma cuenta)."""
    import numpy as np
    from meteo_combinada import fondo_era5l
    clave = _huella_unidad(celdas=receta["celdas"].sha256, enlaces=receta["enlaces"].sha256,
                           cat_pix=receta["cat_pix_sha256"], datos=receta["clave_datos"])
    if clave not in _SALUD:
        _SALUD.clear()
        celdas_g = _tabla_de(receta["celdas"])
        t = celdas_g[["celda", "lat", "lon", "cod_comuna"]]
        est = _filas_por_celda(extras["estaticos_m2a"], t["celda"].to_numpy(np.int64), "estáticos de las celdas")
        z = est["z_poblada"].to_numpy(np.float64)
        lat, lon = t["lat"].to_numpy(np.float64), t["lon"].to_numpy(np.float64)
        ok = (t["cod_comuna"].to_numpy(np.int64) > 0) & np.isfinite(z) & np.isfinite(lat) & np.isfinite(lon)
        orden = np.flatnonzero(ok)[np.argsort(t["celda"].to_numpy(np.int64)[ok], kind="stable")]
        t = t.iloc[orden].reset_index(drop=True)
        est = est.iloc[orden].reset_index(drop=True)
        est.attrs = {"esquema": tipos.ESQUEMA_ESTATICAS_CELDA_C.version}
        op = fondo_era5l.operador(t["lat"].to_numpy(np.float64), t["lon"].to_numpy(np.float64),
                                  est["z_poblada"].to_numpy(np.float64), receta["cat_pix"], extras["validos"],
                                  extras["z_tabla"], U, ids=t["celda"].to_numpy(np.int64))
        _SALUD[clave] = {"celdas": t[["celda", "cod_comuna"]].copy(),
                         "celdas_grilla": celdas_g[["celda", "cod_comuna"]].copy(),
                         "enlaces": _tabla_de(receta["enlaces"]), "op": op, "lat": t["lat"].to_numpy(np.float64),
                         "lon": t["lon"].to_numpy(np.float64), "estaticos": est, "clima": extras["clima_tabla"]}
    return _SALUD[clave]


def _receta_salud(cfg: Cfg, p: Mapping, productos) -> dict:
    """ORQ-36 (H1): lo que una unidad necesita para sus celdas de salud: referencias (celdas y enlaces de la grilla) y
    el catálogo de píxeles (chico); los productos y el lote."""
    return {"celdas": _ref_entrada(cfg, cfg.entrada("celdas")), "enlaces": _ref_entrada(cfg, cfg.entrada("enlaces")),
            "cat_pix": p["cat_pix"], "cat_pix_sha256": _exigir_huella(cfg, cfg.entrada("catalogo_pixeles")),
            "clave_datos": p["receta"]["clave"],
            "productos": [dict(x) for x in productos], "lote": LOTE_CELDAS_SALUD}


def _pixeles_de_monitores(op, pliegues: bytes) -> list[int]:
    """ORQ-27: los píxeles ERA5-Land que usa el fondo en las celdas de los monitores de la red 2 (los de
    ``contaminantes.<pol>.estaciones`` de ``pliegues_v2_red2.json``): con ellos solos, la lateral da los mismos bits
    (AMB-14: cada fila sale sólo de su celda, su hora y su mes)."""
    import numpy as np
    man = json.loads(pliegues)
    celda_de = {e["estacion"]: e.get("celda") for e in man.get("estaciones", ())}
    celdas = sorted({int(celda_de[m]) for reg in man.get("contaminantes", {}).values()
                     for m in reg.get("estaciones", ()) if celda_de.get(m) is not None})
    if not celdas:
        return []
    pix = np.asarray(op.pix)[op.indices(np.array(celdas, dtype=np.int64))]
    return sorted(int(x) for x in np.unique(pix[pix >= 0]))


def _contexto_anual(cfg: Cfg, p: Mapping, *, productos, pixeles, operador_ref) -> dict:
    """El contexto de las unidades anuales (ORQ-23, ORQ-26 a ORQ-28, ORQ-36): la receta de los datos de producción,
    el 0,1° (``pixeles``), la receta de las celdas de salud y lo de las laterales (``operador_ref``: el operador de la
    grilla en disco; los paneles, por referencia)."""
    ctx = {"U": cfg.U, "receta": p["receta"], "h_ultima": _h_ultima(cfg), "pixeles": pixeles,
           "salud": _receta_salud(cfg, p, productos) if productos else None, "laterales": None}
    if operador_ref is not None:
        red2 = cfg.entrada("red2")
        pliegues = leer_entrada(cfg, red2["pliegues"])
        op = _operador_de_disco(operador_ref)
        ctx["laterales"] = {"decision": p["decision_bytes"], "operador": operador_ref, "pliegues": pliegues,
                            "politica": p["politica_bytes"],
                            "paneles": {pol: _ref_entrada(cfg, a) for pol, a in sorted(red2["paneles"].items())},
                            "pixeles": _pixeles_de_monitores(op, pliegues)}
    return ctx


def _unidad_t2m(unidad: Mapping, ctx: Mapping) -> dict:
    """ORQ-23, ORQ-24: la t2m de ERA5-Land de un mes en los píxeles del reloj (sólo memoria)."""
    import numpy as np
    import pandas as pd
    from meteo_combinada import fondo_era5l
    mes = fondo_era5l.leer_mes(Path(unidad["ruta"]), sha256=unidad["sha256"])
    fondo_era5l.comprobar_unidades(mes)
    if not mes.completo_hasta(ctx["h_ultima"]):
        raise ErrorOrquestacion(f"{unidad['mes']}: el mes no trae todas sus horas hasta la última con dato (FON-1)")
    idx = pd.Index(np.asarray(mes.pixel_id, dtype=np.int64)).get_indexer(np.asarray(unidad["pixeles"], np.int64))
    if (idx < 0).any():
        raise ErrorOrquestacion(f"{unidad['mes']}: el mes no trae {int((idx < 0).sum())} píxeles del reloj")
    return {"h": np.asarray(mes.tiempos, dtype=np.int64),
            "t2m": np.asarray(mes.datos["t2m"], dtype=np.float64)[:, idx]}


def _horas_esperadas(meses, h_ultima: int):
    """Las horas de una serie de meses UTC, del comienzo de cada uno a su fin o a la última hora con dato (FON-1),
    sin leer los meses."""
    import numpy as np
    partes = []
    for m in meses:
        a, b = _horas_mes(m)
        partes.append(np.arange(a, min(b, int(h_ultima) + 1), dtype=np.int64))
    return np.concatenate(partes) if partes else np.zeros(0, dtype=np.int64)


class _SaludDelAnio:
    """ORQ-26 (SAL-5 a SAL-8, SAL-13): las tablas diarias de un año, mes a mes: cada mes, para cada lote de celdas y
    cada producto, ``producto.producto_mes`` y ``AcumuladorMeteo.agregar(…, horas=mes.tiempos)``; así sólo hay un mes en
    memoria, y con los mismos lotes en el mismo orden el resultado es bit a bit el de la serie entera (PED-8, resuelto
    por I18). La lluvia, con la tp de los píxeles enlazados de cada mes."""

    def __init__(self, anio: int, meses, h_ultima: int, pesos, sl: Mapping, datos, U):
        import numpy as np
        from meteo_combinada import salud
        self._salud, self.anio, self.sl, self.datos, self.U = salud, int(anio), sl, datos, U
        self.h = _horas_esperadas(meses, h_ultima)
        self.pedidos = salud.dias_del_anio(self.h, self.anio)
        self.pc = salud.pesos_comuna(self.anio, sl["celdas"], pesos)
        self.pl = salud.pesos_lluvia(self.anio, sl["celdas_grilla"], sl["enlaces"], pesos)
        self.calculos: dict[str, dict] = {}
        self.clave_de: dict[str, str] = {}
        for p in sl["productos"]:
            clave = _clave_producto(p)
            self.clave_de[p["nombre"]] = clave
            self.calculos.setdefault(clave, {"p": p, "tipos": set()})["tipos"] |= set(p["tipos_dia"])
        self.acumuladores = {k: salud.AcumuladorMeteo(self.pc, self.h, tuple(t for t in salud.TIPOS_DIA
                                                                             if t in c["tipos"]), dias=self.pedidos)
                             for k, c in self.calculos.items()}
        ids = np.asarray(sl["op"].ids, dtype=np.int64)
        pos = np.searchsorted(ids, self.pc.celdas)
        if pos.size and ((pos >= ids.size).any() or not np.array_equal(ids[np.minimum(pos, ids.size - 1)],
                                                                         self.pc.celdas)):
            raise ErrorOrquestacion(f"{anio}: celdas de los pesos sin operador de salud")
        self.pos = pos
        self.tp: list = []
        self._col_tp = None
        self._fila = 0

    def mes(self, mes) -> None:
        import numpy as np
        import pandas as pd
        from meteo_combinada import producto
        h_mes = np.asarray(mes.tiempos, dtype=np.int64)
        if not np.array_equal(h_mes, self.h[self._fila:self._fila + h_mes.size]):
            raise ErrorOrquestacion(f"{self.anio}: un mes no trae las horas esperadas de la serie (FON-1)")
        self._fila += h_mes.size
        if self._col_tp is None:
            self._col_tp = pd.Index(np.asarray(mes.pixel_id, dtype=np.int64)).get_indexer(self.pl.pixeles)
            if (self._col_tp < 0).any():
                raise ErrorOrquestacion(f"{self.anio}: faltan píxeles enlazados de la lluvia en ERA5-Land")
        self.tp.append(np.asarray(mes.datos["tp"])[:, self._col_tp])
        sl, lote = self.sl, int(self.sl["lote"])
        for i0 in range(0, self.pos.size, lote):
            idx = self.pos[i0:i0 + lote]
            op_l = _sub_operador(sl["op"], idx)
            puntos = {"ids": np.asarray(op_l.ids), "lat": sl["lat"][idx], "lon": sl["lon"][idx],
                      "z": np.asarray(op_l.z, dtype=np.float64)}
            est = sl["estaticos"].iloc[idx].reset_index(drop=True)
            est.attrs = {"esquema": tipos.ESQUEMA_ESTATICAS_CELDA_C.version}
            for clave, c in self.calculos.items():
                p = c["p"]
                campos, _ = producto.producto_mes(mes, op_l, puntos, p["ganador"], p["hiper"], self.datos,
                                                  umbrales=self.U, uso=p["uso"], estaticos=est,
                                                  clima_estado=sl["clima"], entrenamiento=p["entrenamiento"])
                self.acumuladores[clave].agregar({k: campos[k] for k in self._salud.CAMPOS}, op_l.ids, horas=h_mes)

    def tablas(self) -> dict:
        import numpy as np
        if self._fila != self.h.size:
            raise ErrorOrquestacion(f"{self.anio}: faltan meses de la serie del año")
        tp = np.concatenate(self.tp, axis=0)
        tipos_usados = [t for t in self._salud.TIPOS_DIA if any(t in p["tipos_dia"] for p in self.sl["productos"])]
        lluvias = {t: self._salud.lluvia_comunal(self.h, tp, self.pl.pixeles, self.pl, t, dias=self.pedidos)
                   for t in tipos_usados}
        return {(p["nombre"], t): self.acumuladores[self.clave_de[p["nombre"]]].tabla(t, lluvias[t])
                for p in self.sl["productos"] for t in p["tipos_dia"]}


def _reducir_mes(mes, pixeles):
    """Un mes ERA5-Land sólo en los píxeles pedidos (en su orden): lo que la lateral necesita de él (ORQ-27)."""
    import numpy as np
    import pandas as pd
    from meteo_combinada import fondo_era5l
    pix = np.asarray(pixeles, dtype=np.int64)
    idx = pd.Index(np.asarray(mes.pixel_id, dtype=np.int64)).get_indexer(pix)
    if (idx < 0).any():
        raise ErrorOrquestacion(f"{mes.yyyymm}: faltan {int((idx < 0).sum())} píxeles de los monitores")
    return fondo_era5l.MesE5L(tiempos=mes.tiempos, pixel_id=pix,
                              datos={k: np.ascontiguousarray(np.asarray(v)[:, idx]) for k, v in mes.datos.items()},
                              sha256=mes.sha256)


def _panel_de(ref: _Ref):
    """ORQ-27 (H1): las claves del panel entero de la red 2 (``estacion``, ``ts_utc`` y ``celda``), leídas del disco con
    su huella una vez por proceso (``lateral_monitores`` pide el panel entero, AMB-2)."""
    import pyarrow.parquet as pq
    clave = ("panel", ref.sha256)
    if clave not in _TABLAS:
        if len(_TABLAS) >= len(tipos.CONTAMINANTES_M6):
            _TABLAS.clear()
        archivo = pq.ParquetFile(io.BytesIO(_bytes_de(ref)))
        nombres = archivo.schema_arrow.names
        _TABLAS[clave] = archivo.read(columns=[c for c in ("estacion", "ts_utc", "celda") if c in nombres]).to_pandas()
    return _TABLAS[clave]


def _unidad_anio(unidad: Mapping, ctx: Mapping) -> dict:
    """ORQ-23 (una sola pasada): un año en un trabajador. Lee cada mes del año (y el enero siguiente, que necesitan los
    días del 31 de diciembre) una vez y, mes a mes, arma el 0,1° de los meses del año, las tablas diarias de salud
    (``_SaludDelAnio``) y guarda los píxeles de los monitores para las laterales de ese año. Lo grande llega del disco
    (ORQ-36): la receta de los datos, las celdas de salud, el operador y los paneles."""
    import numpy as np
    from meteo_combinada import ambiental, fondo_era5l, producto
    U = ctx["U"]
    datos, extras = _datos_de_receta(ctx["receta"], U)
    anio = int(unidad["anio"])
    px, lt = ctx.get("pixeles"), ctx.get("laterales")
    salud_anio = None
    if ctx.get("salud") is not None and unidad["meses"]:
        sl = {**_salud_de(ctx["salud"], extras, U), "productos": ctx["salud"]["productos"],
              "lote": ctx["salud"]["lote"]}
        salud_anio = _SaludDelAnio(anio, [m for m, _, _ in unidad["meses"]], ctx["h_ultima"], unidad["pesos"], sl,
                                   datos, U)
    con_panel = lt is not None and bool(unidad.get("paneles"))
    salida: dict = {"anio": anio, "nc": {}, "salud": {}, "laterales": {}}
    reducidos = {}
    for m, ruta, sha in unidad["meses"]:
        mes = fondo_era5l.leer_mes(Path(ruta), sha256=sha)
        fondo_era5l.comprobar_unidades(mes)
        if not mes.completo_hasta(ctx["h_ultima"]):
            raise ErrorOrquestacion(f"{m}: el mes no trae todas sus horas hasta la última con dato (FON-1)")
        del_anio = int(_PATRON_MES.fullmatch(m)["anio"]) == anio
        if px is not None and del_anio:
            campos, _ = producto.producto_mes(mes, px["op"], px["puntos"], px["ganador"], px["hiper"], datos,
                                              umbrales=U, uso=Uso.AMBIENTAL.value, estaticos=px["estaticos"],
                                              celdas=px["celdas"])
            huellas = {**px["huellas"], unidad["alias"][m]: mes.sha256}
            salida["nc"][m] = producto.mes_01deg(campos, np.asarray(px["op"].ids), np.asarray(mes.tiempos, np.int64),
                                                 U, huellas, uso=Uso.AMBIENTAL.value, ganador=px["ganador"])
            del campos
        if salud_anio is not None:
            salud_anio.mes(mes)
        if con_panel and del_anio:
            reducidos[int(m)] = _reducir_mes(mes, lt["pixeles"])
        del mes
    if salud_anio is not None:
        salida["salud"] = salud_anio.tablas()
    if con_panel:
        op = _operador_de_disco(lt["operador"])
        for pol in sorted(unidad["paneles"]):
            ref = lt["paneles"][pol]
            for var in _VARIANTES:
                salida["laterales"][(pol, var)] = ambiental.lateral_monitores(
                    pol, lt["decision"], op, variante=var, panel=_panel_de(ref), panel_sha256=ref.sha256,
                    pliegues=lt["pliegues"], meses=reducidos, datos=datos, umbrales=U, politica=lt["politica"],
                    h_ultima=ctx["h_ultima"], estaticos=extras["estaticos_m2a"], anios=anio)
    return salida


def _anios_de_paneles(cfg: Cfg) -> dict:
    """ORQ-27: {contaminante: los años UTC con filas en su panel de la red 2} (AMB-2; H17 de I19: también los años sin
    ningún mes ERA5-Land, cuyas filas cuenta la lateral como posteriores a la última hora)."""
    import numpy as np
    import pandas as pd
    salida = {}
    for pol, a in sorted(cfg.entrada("red2")["paneles"].items()):
        ts = _parquet(leer_entrada(cfg, a))["ts_utc"]
        if isinstance(ts.dtype, pd.DatetimeTZDtype):
            ts = ts.dt.tz_convert("UTC").dt.tz_localize(None)
        salida[pol] = set(int(x) for x in np.unique(ts.dt.year.to_numpy(np.int64)))
    return salida


def _correr_anual(cfg: Cfg, avance: Avance, p: Mapping, ctx: Mapping, base: str, procesos: int, *,
                  registro: list[dict] | None = None) -> dict:
    """ORQ-23: las unidades anuales (una por año UTC de ``meses_era5l`` y, con laterales, de los paneles; en orden) y su
    escritura en este proceso, en el orden de las unidades. Devuelve {año: línea de avance.jsonl}."""
    from meteo_combinada import ambiental, salud
    meses = _meses_ordenados(cfg)
    alias_de = dict(meses)
    anios_meses = {int(_PATRON_MES.fullmatch(m)["anio"]) for m, _ in meses}
    paneles = _anios_de_paneles(cfg) if ctx.get("laterales") is not None else {}
    anios = sorted(anios_meses | {a for s in paneles.values() for a in s})
    unidades, registros = [], {}
    for anio in anios:
        del_anio = [(m, a) for m, a in meses if int(_PATRON_MES.fullmatch(m)["anio"]) == anio]
        siguiente = f"{anio + 1:04d}01"
        if del_anio and siguiente in alias_de:
            del_anio.append((siguiente, alias_de[siguiente]))
        pan = sorted(pol for pol, s in paneles.items() if anio in s)
        hay_salud = ctx.get("salud") is not None and bool(del_anio)
        if not (ctx.get("pixeles") is not None and del_anio) and not hay_salud and not pan:
            continue
        pesos = _pesos_del_anio(p["pesos"], anio) if hay_salud else None
        anio_pesos = None if pesos is None or not len(pesos) else int(pesos["anio"].iloc[0])
        entrada = _huella_unidad(base=base, anio=anio, meses={m: cfg.huellas[a] for m, a in del_anio},
                                 pesos_anio=anio_pesos, paneles=pan)
        nombre_u = f"anio-{anio}"
        hecha = avance.hecha("anual", nombre_u, entrada)
        if hecha is not None:
            avance.saltadas.append(nombre_u)
            registros[anio] = hecha
            continue
        unidades.append({"anio": anio, "entrada": entrada, "pesos": pesos, "paneles": pan,
                         "meses": [(m, str(ruta_de_alias(cfg.rutas, a)), _exigir_huella(cfg, a)) for m, a in del_anio],
                         "alias": {m: a for m, a in del_anio}})

    def al_terminar(i, r):
        u = unidades[i]
        anio = u["anio"]
        escritos: list = []
        for m in sorted(r["nc"]):
            escritos.append((f"producto_01deg/meteo_{m}.nc", r["nc"][m], None, None))
        for (nombre_p, tipo), tabla in sorted(r["salud"].items()):
            meta = salud.metadatos_tabla(tabla)                  # SAL-10: lo crónico se rearma desde el disco
            tabla.attrs = {"esquema": tipos.ESQUEMA_METEO_DIARIA.version}
            escritos.append((f"{CARPETA_SALUD[(nombre_p, tipo)]}/meteo_{anio}.parquet", tabla,
                             tipos.ESQUEMA_METEO_DIARIA, meta))
        for (pol, var), (tabla, meta) in sorted(r["laterales"].items()):
            escritos.append((f"ambiental/partes/lateral_{pol}_{var}_{anio}.parquet", tabla, ambiental.ESQUEMA_DE[var],
                             meta))
        avance.parcial_pendiente([e[0] for e in escritos], f"anio-{anio}")
        archivos = {n: _escribir(avance, n, c, esquema=e, metadatos=m) for n, c, e, m in escritos}
        avance.registrar("anual", f"anio-{anio}", u["entrada"], archivos)
        return None
    repartir(unidades, _unidad_anio, procesos, contexto=ctx, al_terminar=al_terminar, permitidas=cfg.permitidas,
             registro=registro)
    for u in unidades:
        registros[u["anio"]] = avance.hecha("anual", f"anio-{u['anio']}", u["entrada"]) or {"archivos": {}}
    return dict(sorted(registros.items()))


def _ensamblar_laterales(avance: Avance, registros: Mapping) -> dict:
    """ORQ-27: ``ambiental/lateral_<pol>_<variante>.parquet`` desde sus partes anuales, releídas del disco con su
    huella (ORQ-8), con ``ambiental.unir_partes`` (PED-7, resuelto por I19): bit a bit la lateral armada de una vez.
    Devuelve {nombre: sha256}."""
    from meteo_combinada import ambiental
    archivos = {n: s for r in registros.values() for n, s in r["archivos"].items() if n.startswith("ambiental/partes/")}
    salida = {}
    for pol in tipos.CONTAMINANTES_M6:
        for var in _VARIANTES:
            prefijo = f"ambiental/partes/lateral_{pol}_{var}_"
            partes = sorted(n for n in archivos if n.startswith(prefijo))
            if not partes:
                continue
            nombre = f"ambiental/lateral_{pol}_{var}.parquet"
            esquema = ambiental.ESQUEMA_DE[var]

            def producir(partes=partes):
                leidas = []
                for n in partes:
                    t = _parquet(_leer_propio(avance.carpeta / n, archivos[n]))
                    meta = dict(t.attrs.get("metadatos", {}))
                    t.attrs = {}
                    leidas.append((t, meta))
                return ambiental.unir_partes(leidas)
            entrada = _huella_unidad(partes={n: archivos[n] for n in partes})
            salida[nombre] = _unidad_unica(avance, "monitores", f"lateral-{pol}-{var}", entrada, nombre, producir,
                                           esquema=esquema)
    return salida


# ---------------------------------------------------------------------------
# M5 (§2.5 del diseño; §3, §7.1-§7.3, §8)
# ---------------------------------------------------------------------------
def correr_m5(cfg, *, avance, procesos: int) -> dict:
    """M5: el 0,1° mensual con el ganador ambiental (MC-08), la salud civil, UTC−4 y regional con el ganador agudo, la
    representatividad (la lista de excluidas y el producto agudo sin ellas) y lo crónico (§7.2, puntos 1, 3 y 6;
    §7.3), el operador de la grilla y las laterales I y D por contaminante (§7.1), desde ``decision.json``, los
    residuos, los estáticos y los meses de ERA5-Land (ORQ-20 a ORQ-28). Escribe en la carpeta de su M3-4 (ENT-4) y la
    sella otra vez (el recibo de M3-4 se archiva, SLD-10). Las negativas de §10 son de I22 (``Cfg.negativas``); la del
    registro de M3-4 (``decision.json``), de aquí (H5)."""
    import numpy as np
    from meteo_combinada import ambiental, salud

    U = cfg.U
    fases: list[str] = []
    por_fase = _procesos_de_fases(cfg, "m5", procesos)          # ORQ-45 (D59, P146): límites
    repartos = {fase: [] for fase in por_fase}                # EMC3-1: observaciones de esta invocación
    # 1. negativas (H5, H7)
    if avance.compuerta != "m5":
        raise ErrorOrquestacion("M5 sigue el avance.jsonl de su M3-4 con su línea de compuerta (abrir_avance(cfg, "
                                "«m5»); ORQ-20)")
    fallas = _negativas(cfg, [k for k in ENTRADAS_M5 if k != "m2a"])
    corrida0 = _leer_carpeta(cfg, avance.carpeta, "M3-4")
    fallas += _negativas_registro(cfg, corrida0, salidas.DECISION, "M3-4")
    if fallas:
        raise ErrorOrquestacion("M5 se niega a correr: " + "; ".join(fallas[:_CITADOS]))
    avance.iniciar()
    fases.append("negativas")
    # 2. entradas (ORQ-21, ORQ-22)
    p = _produccion(cfg, avance.carpeta, "M3-4", c_est=None)
    datos, contenido = p["datos"], p["decision"]
    gan_amb, hiper_amb = ambiental.ganador_ambiental(contenido)
    gan_agu, hiper_agu = _ganador_y_hiper(contenido, Uso.AGUDO.value)
    gan_cro, hiper_cro = _ganador_y_hiper(contenido, Uso.CRONICO.value)
    base = _base_de(avance, p)
    meses = _meses_ordenados(cfg)
    fases.append("entradas")
    # 3. representatividad (ORQ-23, ORQ-24): la primera pasada, sólo t2m en los píxeles del reloj
    pixel = fijados.cargar_elegir_pixel(entorno.rutas_reales().ap, entorno.rutas_reales().aph, fijados.HUELLAS_CLAUSURA,
                                        permitir_cargados=cfg.modo == tipos.Modo.SINTETICO.value)
    validos = {int(v) for v in p["validos"]}
    pixel_de = {}
    for c, info in sorted(datos.estaciones.items()):
        e = pixel.enlazar(float(info.lat), float(info.lon), p["cat_pix"], validos)     # FIJ-11: como enlazar_pixeles
        pixel_de[c] = None if e.pixel_id is None else int(e.pixel_id)
    qc = {c: f"qc/estaciones/{c}.parquet" for c in sorted(datos.estaciones)}
    entrada_r = _huella_unidad(base=base, meses={m: cfg.huellas[a] for m, a in meses}, pixeles=pixel_de,
                               qc={n: p["corrida"]["sha"](n) for n in qc.values()})

    def producir_excluidas():
        unicos = sorted({x for x in pixel_de.values() if x is not None})
        unidades = [{"mes": m, "ruta": str(ruta_de_alias(cfg.rutas, a)), "sha256": _exigir_huella(cfg, a),
                     "pixeles": unicos} for m, a in meses]
        res = repartir(unidades, _unidad_t2m, por_fase["representatividad"], contexto={"h_ultima": _h_ultima(cfg)},
                       permitidas=cfg.permitidas, registro=repartos["representatividad"])
        h = np.concatenate([r["h"] for r in res])
        t2m = np.concatenate([r["t2m"] for r in res], axis=0)
        obs, serie = {}, {}
        for c in sorted(datos.estaciones):
            ancha = _parquet(p["corrida"]["leer"](qc[c]))
            obs[c] = {"h": ancha["h"].to_numpy(np.int64), "T": ancha["Ts"].to_numpy(np.float64),
                      "valido": ancha["valido_T"].to_numpy(bool)}
            serie[c] = (h, t2m[:, unicos.index(pixel_de[c])] if pixel_de[c] is not None else np.full(h.size, np.nan))
        return {"esquema": ESQUEMA_EXCLUIDAS, "excluidas": sorted(salud.representatividad(obs, serie, U))}, None
    sha_excl = _unidad_unica(avance, "representatividad", "excluidas", entrada_r, EXCLUIDAS, producir_excluidas)
    excluidas = tuple(json.loads(_leer_propio(avance.carpeta / EXCLUIDAS, sha_excl))["excluidas"])
    fases.append("representatividad")
    # 4. el operador de la grilla (ORQ-28)

    def producir_operador():
        op = ambiental.operador_grilla(p["decision_bytes"], celdas=p["celdas_g"], estaciones=datos.estaciones,
                                       catalogo=p["cat_pix"], z_celdas=p["estaticos_m2a"], validos=p["validos"],
                                       z_pix=p["z_tabla"], umbrales=U)
        return op.a_bytes(), None
    sha_op = _unidad_unica(avance, "operador", "operador", base, OPERADOR_GRILLA, producir_operador)
    fases.append("operador")
    # 5. la pasada anual (ORQ-23, ORQ-25 a ORQ-27)
    restantes = sorted(set(datos.estaciones) - set(excluidas))
    if not restantes:
        raise ErrorOrquestacion("la representatividad excluye todas las estaciones: no hay producto sin ellas (§7.2, "
                                "punto 6; pregunta P-ORQ-4)")
    productos = [
        _producto_salud("agudo", {Grupo.T_TD.value: gan_agu}, hiper_agu, Uso.AGUDO.value, None, salud.TIPOS_DIA),
        _producto_salud("representatividad", {Grupo.T_TD.value: gan_agu}, hiper_agu, Uso.AGUDO.value,
                        restantes if excluidas else None, ("civil",)),
        _producto_salud("cronico", {Grupo.T_TD.value: gan_cro}, hiper_cro, Uso.CRONICO.value, None, ("civil",))]
    carpeta = avance.carpeta
    huellas_nc = {entorno.alias(carpeta / salidas.DECISION, cfg.rutas): p["corrida"]["sha"](salidas.DECISION),
                  entorno.alias(p["m2a"]["carpeta"] / "estaticas/z_e5l.parquet", cfg.rutas):
                      p["m2a"]["sha"]("estaticas/z_e5l.parquet"),
                  cfg.entrada("catalogo_pixeles"): cfg.huellas[cfg.entrada("catalogo_pixeles")]}
    ctx = _contexto_anual(cfg, p, productos=productos, pixeles=_contexto_pixeles(p, gan_amb, hiper_amb, huellas_nc),
                          operador_ref=_ref_de_archivo(carpeta, OPERADOR_GRILLA, sha_op))
    registros = _correr_anual(cfg, avance, p, ctx, _huella_unidad(base=base, excluidas=sha_excl, operador=sha_op,
                                                                  productos=[_clave_producto(x) for x in productos]),
                              por_fase["anual"], registro=repartos["anual"])
    fases.append("anual")
    # 6. las laterales enteras (ORQ-27)
    laterales = _ensamblar_laterales(avance, registros)
    fases.append("monitores")
    # 7. lo crónico (§7.3): temperatura_anual desde los días civiles con el ganador crónico, releídos del disco
    diarios = {a: f"salud/cronico/meteo_{a}.parquet" for a, r in registros.items()
               if f"salud/cronico/meteo_{a}.parquet" in r["archivos"]}
    entrada_c = _huella_unidad(diarios={n: registros[a]["archivos"][n] for a, n in diarios.items()})

    def producir_cronico():
        sl = _salud_de(ctx["salud"], p, U)
        tablas, pesos = {}, {}
        for a, n in sorted(diarios.items()):
            tablas[a] = _parquet(_leer_propio(carpeta / n, registros[a]["archivos"][n]))      # attrs["metadatos"]
            pesos[a] = salud.pesos_comuna(a, sl["celdas"], _pesos_del_anio(p["pesos"], a))
        return salud.cronico_anual(tablas, pesos), None
    sha_cro = _unidad_unica(avance, "cronico", "temperatura_anual", entrada_c, CRONICO_ANUAL, producir_cronico,
                            esquema=tipos.ESQUEMA_CRONICO)
    fases.append("cronico")
    # 8. sello (§8, «Cadena de huellas»; SLD-10: el recibo de M3-4 y su sha256.json se archivan y el nuevo los cita)
    _OPERADORES.clear()
    recibo = salidas.sellar_corrida(carpeta, {**dict(cfg.huellas), **p["m2a"]["huellas"]},
                                    _entorno_recibo(procesos, por_fase, repartos=repartos), rutas=cfg.rutas)
    fases.append("sello")
    archivos = {EXCLUIDAS: sha_excl, OPERADOR_GRILLA: sha_op, CRONICO_ANUAL: sha_cro, **laterales,
                **{n: s for r in registros.values() for n, s in r["archivos"].items()}}
    return {"carpeta": carpeta, "recibo_sha256": recibo, "fases": fases, "excluidas": list(excluidas),
            "ganadores": {"ambiental": dict(gan_amb), "agudo": gan_agu, "cronico": gan_cro},
            "archivos": dict(sorted(archivos.items()))}


# ---------------------------------------------------------------------------
# M6 (Anexo B; §6.4, §7.2 punto 5, §8)
# ---------------------------------------------------------------------------
def _muestra_m6(celdas_g, pesos, U):
    """ORQ-29 (TEN-19): la muestra fija de la TF de contaminantes en las celdas de la grilla con w_ghs de 2020."""
    import numpy as np
    from meteo_combinada import tendencias
    p20 = pesos[(pesos["anio"] == constantes.valor("TF_PESOS_ANIO")).to_numpy(bool)][["celda", "w_ghs"]]
    t = celdas_g[["celda", "cod_comuna"]].merge(p20, on="celda", how="inner")
    t = t[np.isfinite(t["w_ghs"].to_numpy(np.float64))].sort_values("celda").reset_index(drop=True)
    return tendencias.muestra_tf_contaminantes(t[["celda", "cod_comuna"]], t["w_ghs"].to_numpy(np.float64), U)


def _entradas_ambientales(corrida: Mapping, contenido: Mapping) -> dict:
    """ORQ-29 (DEC-16): las ``EntradasDecision`` ambientales rehechas desde las tablas de M3-4, como las armó M3-4:
    las métricas publicadas del grupo, la TF del uso, las réplicas del grupo y los motivos de E0 (deriva y finitud) de
    los candidatos que no están en E0 en ``decision.json``."""
    puntajes = _parquet(corrida["leer"]("validacion/puntajes.parquet"))
    tf = _parquet(corrida["leer"]("tendencias/resumen_tf.parquet"))
    uso = Uso.AMBIENTAL.value
    tf_u = tf[(tf["uso"] == uso).to_numpy(bool)].reset_index(drop=True)
    de_e0 = (tipos.Compuerta.DERIVA.value, tipos.Compuerta.FINITUD.value)
    salida = {}
    for g in _GRUPOS_AMBIENTALES:
        d = _decision_de(contenido, uso, g)
        sub = puntajes[((puntajes["uso"] == uso) & (puntajes["grupo"] == g)).to_numpy(bool)].reset_index(drop=True)
        sub.attrs = dict(puntajes.attrs)
        rep = _parquet(corrida["leer"](f"validacion/remuestreo_{uso}_{g}.parquet"))
        motivos = {str(c): tuple(str(m) for m in ms if m in de_e0) for c, ms in d.get("motivos", {}).items()
                   if c not in d["e0"]}
        salida[g] = tipos.EntradasDecision(Uso.AMBIENTAL, Grupo(g), sub, tf_u, rep, motivos)
    return salida


def _regla_s6(contenido: Mapping, definitivo_t_td: str) -> tuple:
    """ORQ-31 (§7.2, punto 5; §6.4): (regla, candidato, {T, Td: θ}, uso de los hiperparámetros). Con el ganador
    ambiental definitivo de (T, Td) y sus hiperparámetros ambientales si difiere del agudo; si coinciden, el de menor
    S entre los demás de E1 de lo agudo (empate: el orden fijo de DEC-8), con sus hiperparámetros agudos; si no hay,
    «no aplica»."""
    from meteo_combinada import decision
    d_agu = _decision_de(contenido, Uso.AGUDO.value, Grupo.T_TD.value)
    if definitivo_t_td != d_agu["ganador"]:
        d_amb = _decision_de(contenido, Uso.AMBIENTAL.value, Grupo.T_TD.value)
        return REGLA_S6_AMBIENTAL, definitivo_t_td, _hiper_de_decision(d_amb, definitivo_t_td), Uso.AMBIENTAL.value
    otros = [c for c in d_agu["e1"] if c != d_agu["ganador"]]
    if not otros:
        return REGLA_S6_NO_APLICA, None, None, None
    orden = decision.ORDEN_DESEMPATE[Uso.AGUDO]
    cand = min(otros, key=lambda c: (float(d_agu["S"][c]), orden.index(c)))
    return REGLA_S6_SEGUNDO, cand, _hiper_de_decision(d_agu, cand), Uso.AGUDO.value


def correr_m6(cfg, *, avance) -> dict:
    """M6 (Anexo B): la comparación de v2 (MC-30), la TF de contaminantes con la fábrica de A26 (a D siempre; a I si
    su ganador ambiental es B o AB, y si no la verificación de un mes, DEC-14), las condiciones, la simetría, las ramas
    y la variante de cada contaminante y de O3; en la rama 3, el ganador restringido para todos, el operador y las
    laterales restringidos (``m6/ambiental/``, P98); ``salud/s6`` (§7.2, punto 5); ``decision_m6.json`` (ORQ-29 a
    ORQ-33). Escribe en ``v1/<ETIQUETA>/m6`` (ENT-4) y lo sella. Las negativas de M6 y el cerrojo
    ``intentos_m6.jsonl`` son de I22 (``Cfg.negativas``); las de los registros de M3-4 y de M5, de aquí (H5)."""
    import functools
    from meteo_combinada import ambiental, decision, tendencias

    U = cfg.U
    fases: list[str] = []
    # 1. negativas (H5, H7)
    if avance.prefijo != "m6/":
        raise ErrorOrquestacion("M6 corre con el avance de m6/ (abrir_avance(cfg, «m6»); ORQ-29)")
    carpeta_corrida = carpeta_de(cfg, "m5")
    fallas = _negativas(cfg, [k for k in ENTRADAS_M6 if k != "m2a"])
    corrida0 = _leer_carpeta(cfg, carpeta_corrida, "M5")
    fallas += _negativas_registro(cfg, corrida0, salidas.DECISION, "M3-4")
    fallas += _negativas_registro(cfg, corrida0, salidas.RECIBO, "M5")
    if fallas:
        raise ErrorOrquestacion("M6 se niega a correr: " + "; ".join(fallas[:_CITADOS]))
    avance.iniciar()
    fases.append("negativas")
    p = _produccion(cfg, carpeta_corrida, "M5", c_est=False)
    corrida, datos, contenido = p["corrida"], p["datos"], p["decision"]
    op_m5 = ambiental.leer_operador(corrida["leer"](OPERADOR_GRILLA), sha256=corrida["sha"](OPERADOR_GRILLA))
    # 2. la comparación de v2 (MC-30), por la lista cerrada
    alias_comp = cfg.entrada("comparacion_m6")
    comparacion = _parquet(leer_entrada(cfg, alias_comp))
    comparacion.attrs = {"esquema": tipos.ESQUEMA_COMPARACION_M6.version}
    tipos.validar_esquema(comparacion, tipos.ESQUEMA_COMPARACION_M6, nombre="comparacion de v2 (MC-30)")
    base = _base_de(avance, p, comparacion=cfg.huellas[alias_comp])
    fases.append("comparacion")
    # 3. la TF de contaminantes (Anexo B; A26, TEN-19 a TEN-21)
    gan_amb, _ = ambiental.ganador_ambiental(contenido)
    i_exigida = any(c in _CON_B_AB for c in gan_amb.values())
    anios = range(constantes.valor("PI_POB_PERIODO")[0], constantes.valor("PI_POB_PERIODO")[1] + 1)
    preparado: dict = {}

    def base_fabrica():
        if not preparado:
            anchas = {c: _ancha_de(corrida["leer"](f"qc/estaciones/{c}.parquet"), _COLUMNAS_VALIDAS)   # ORQ-44
                      for c in sorted(datos.estaciones)}
            horas_anio = _horas_validas_anio(anchas, datos.estaciones, anios)
            escenarios = {v: tendencias.escenarios_tf({a: horas_anio[k][a] for a in anios}, v, U)
                          for v, k in (("T", "T"), ("Td", "Td"), ("rapidez", "viento"), ("p", "p"))}
            del anchas
            preparado["muestra"] = _muestra_m6(p["celdas_g"], p["pesos"], U)
            preparado["base"] = functools.partial(ambiental.fabrica_tf_contaminantes, operador=op_m5,
                                                  meses=_LectorMeses(cfg), datos=datos, umbrales=U,
                                                  escenarios=escenarios, estaticos=p["estaticos_m2a"])
        return preparado
    fabrica_id = identidad_funcion(cfg.fabrica_m6)
    tf, tf_archivos = {}, {}
    for pol in tipos.CONTAMINANTES_M6:
        tf[pol] = {}
        for var in _VARIANTES:
            verificacion = var == tipos.Variante.I.value and not i_exigida
            nombre = f"tf_contaminantes_{pol}_{var}.json"

            def producir_tf(pol=pol, var=var, verificacion=verificacion):
                if cfg.fabrica_m6 is None:
                    raise ErrorOrquestacion("M6 necesita la fábrica de producción v2 (Cfg.fabrica_m6; A26, ORQ-29)")
                prep = base_fabrica()
                fabrica, modelo = cfg.fabrica_m6(pol, var, prep["base"])
                r = tendencias.tf_contaminantes(fabrica, modelo, var, prep["muestra"], U,
                                                verificacion_un_mes=verificacion)
                return {"esquema": ESQUEMA_TF_M6, "contaminante": pol, **_numeros_python(r)}, None
            entrada = _huella_unidad(base=base, contaminante=pol, variante=var, verificacion=verificacion,
                                     fabrica=fabrica_id)                                   # H12
            sha = _unidad_unica(avance, "tf_contaminantes", f"{pol}-{var}", entrada, nombre, producir_tf)
            tf[pol][var] = json.loads(_leer_propio(avance.carpeta / nombre, sha))["resultado"]
            tf_archivos[nombre] = sha
    fases.append("tf_contaminantes")
    # 4. las ramas (Anexo B; DEC-13 a DEC-17) y ramas_m6.json (ORQ-30)
    condiciones = {pol: {s.value: decision.condiciones_anexo_b(comparacion, pol, s.value, U) for s in tipos.Sentido}
                   for pol in tipos.CONTAMINANTES_M6}
    dm6 = decision.ramas_m6(condiciones, tf, gan_amb, entradas_ambientales=_entradas_ambientales(corrida, contenido),
                            umbrales=U)
    nombres_corrida = (salidas.DECISION, "validacion/puntajes.parquet", "tendencias/resumen_tf.parquet",
                       *(f"validacion/remuestreo_ambiental_{g}.parquet" for g in _GRUPOS_AMBIENTALES), OPERADOR_GRILLA)
    huellas_entrada = {entorno.alias(carpeta_corrida / n, cfg.rutas): corrida["sha"](n) for n in nombres_corrida}
    huellas_entrada[alias_comp] = cfg.huellas[alias_comp]
    huellas_entrada.update({entorno.alias(avance.carpeta / n, cfg.rutas): s for n, s in tf_archivos.items()})
    sha_ramas = _escribir(avance, RAMAS_M6, decision.decision_m6_json(dm6, huellas_entrada))
    fases.append("ramas")
    # 5. el operador restringido (rama 3; §6.4: el restringido para todos), que cita ramas_m6.json (AMB-7, ORQ-30)
    restringido = None if dm6.ganador_restringido is None else {Grupo(g).value: str(c)
                                                                for g, c in dm6.ganador_restringido.items()}
    sha_op_r = None
    if restringido is not None:
        def producir_operador():
            op = ambiental.operador_grilla(p["decision_bytes"], celdas=p["celdas_g"], estaciones=datos.estaciones,
                                           catalogo=p["cat_pix"], z_celdas=p["estaticos_m2a"], validos=p["validos"],
                                           z_pix=p["z_tabla"], umbrales=U, restringido=restringido,
                                           ramas_m6_sha256=sha_ramas)
            return op.a_bytes(), None
        sha_op_r = _unidad_unica(avance, "restringido", "operador", _huella_unidad(base=base, ramas=sha_ramas),
                                 OPERADOR_GRILLA, producir_operador)
    fases.append("restringido")
    # 6. la pasada anual: salud/s6 y las partes de las laterales restringidas (ORQ-31, ORQ-27)
    definitivo = restringido[Grupo.T_TD.value] if restringido is not None else gan_amb[Grupo.T_TD.value]
    regla, cand_s6, hiper_s6, uso_hiper = _regla_s6(contenido, definitivo)
    productos = [] if cand_s6 is None else [
        _producto_salud("s6", {Grupo.T_TD.value: cand_s6}, hiper_s6, Uso.AGUDO.value, None, ("civil",))]
    registros: dict = {}
    if productos or restringido is not None:
        ref = None if sha_op_r is None else _ref_de_archivo(avance.carpeta, OPERADOR_GRILLA, sha_op_r)
        ctx = _contexto_anual(cfg, p, productos=productos, pixeles=None, operador_ref=ref)
        registros = _correr_anual(cfg, avance, p, ctx, _huella_unidad(
            base=base, ramas=sha_ramas, operador=sha_op_r, productos=[_clave_producto(x) for x in productos]),
            cfg.procesos)
    fases.append("anual")
    laterales_r = _ensamblar_laterales(avance, registros) if restringido is not None else {}
    fases.append("monitores")
    # 7. registro: s6.json y decision_m6.json con las rutas y huellas vigentes (§7.1, punto 3; §8; ORQ-30)
    s6_archivos = {n: s for r in registros.values() for n, s in r["archivos"].items() if n.startswith("salud/s6/")}
    s6 = {"esquema": ESQUEMA_S6, "regla": regla, "candidato": cand_s6, "uso_hiperparametros": uso_hiper,
          "huellas": {entorno.alias(avance.carpeta / n, cfg.rutas): s for n, s in sorted(s6_archivos.items())}}
    sha_s6 = _escribir(avance, S6_M6, s6)
    vigentes = {}
    for nombre in (OPERADOR_GRILLA, *(f"ambiental/lateral_{pol}_{var}.parquet" for pol in tipos.CONTAMINANTES_M6
                                      for var in _VARIANTES)):
        if restringido is not None:
            sha = sha_op_r if nombre == OPERADOR_GRILLA else laterales_r.get(nombre)
            if sha is not None:
                vigentes[entorno.alias(avance.carpeta / nombre, cfg.rutas)] = sha
        elif nombre in corrida["inventario"]:
            vigentes[entorno.alias(carpeta_corrida / nombre, cfg.rutas)] = corrida["sha"](nombre)
    huellas_final = {**huellas_entrada, **vigentes, **s6["huellas"],
                     entorno.alias(avance.carpeta / RAMAS_M6, cfg.rutas): sha_ramas,
                     entorno.alias(avance.carpeta / S6_M6, cfg.rutas): sha_s6}
    registro = decision.decision_m6_json(dm6, huellas_final)
    sha_dec = _escribir(avance, "decision_m6.json", registro)
    fases.append("registro")
    # 8. sello
    _OPERADORES.clear()
    recibo = salidas.sellar_corrida(avance.carpeta, {**dict(cfg.huellas), **p["m2a"]["huellas"],
                                                     **dict(corrida["leidos"])}, _entorno_recibo(cfg.procesos),
                                    rutas=cfg.rutas)
    fases.append("sello")
    return {"carpeta": avance.carpeta, "recibo_sha256": recibo, "fases": fases, "decision_m6": registro,
            "decision_m6_sha256": sha_dec, "ramas_sha256": sha_ramas, "s6": s6, "tf": tf,
            "restringido": restringido, "laterales": laterales_r}
