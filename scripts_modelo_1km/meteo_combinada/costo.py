"""Medición del costo a escala y proyección de M3-4, M5, M6 y de la grilla v2 (§4.9, §7.1, §8; §8.1 del diseño).

Mide con la máquina libre (carga < 2, sin la descarga TROPOMI ni otra corrida pesada).

Qué hay:
- ``medir(rutas, *, real_era5, umbrales, temporal=None, escala=ESCALA_REAL, aislar=True, puntos=PUNTOS,
  procesos=8)``: los seis puntos de §8.1 del diseño y el factor de contención, cada uno en un proceso propio
  (``orquestacion.repartir``: sólo ``orquestacion`` lanza procesos, §0, regla 3) y bajo su propio registro de accesos
  en bloqueo, con su tiempo de pared, su tiempo de CPU (un hilo), su memoria pico (``resource``) y la carga de la
  máquina mientras corre:
  1. «qc»: ``orquestacion._unidad_estacion`` (paso 1 con ``cargar_dmc`` y el envoltorio) sobre ≥ 50 artefactos
     sintéticos de un año, en ms por hora de dato, la memoria de una estación y escribir y releer su tabla (COS-16);
  2. «pliegue»: un pliegue externo de P2 con 579 estaciones sintéticas y H horas (``orquestacion._unidad_pliegue``:
     selección de A, B, AB, C y C_est, predicción y evaluaciones), en frío y en tibio, y lo que M3-4 y M5 hacen en
     serie con esa red (residuos, A, filas de C, escribir los residuos, la representatividad);
  3. «tf»: un año de TF (``orquestacion._unidad_mes_tf``, las dos pasadas, con la finitud de E0) en 108.579 celdas
     pobladas, y C y C_est en esas celdas (``PasadaTF.correccion_mes``; CAN-18, TEN-14) en ms por celda-mes;
  4. «m5»: un mes de M5 (0,1° en los píxeles y los productos de salud con su agregación comunal en las celdas
     pobladas, para cada ganador del barrido), la lluvia y el operador de salud de un trabajador;
  5. «grilla»: el operador de la grilla y un mes de ``ambiental.mc_bloque`` con I y con D, para cada ganador del
     barrido, en una muestra de lotes de las 838.430 celdas;
  6. «mes_real»: la huella (``open`` de Python) y la lectura de un mes real (2024-01; sólo con ``real_era5``);
  y «contencion»: la misma unidad sola y en P copias a la vez (COS-20).
- ``proyectar(mediciones, umbrales, *, procesos=8)``: la memoria por trabajador, del principal y del grupo frente al
  tope de §8 y a la memoria física, y de ella los procesos de cada fase de reparto («procesos_por_fase», D59, COS-25);
  con ellos, las horas de pared de M3-4, M5, M6 y de la grilla v2, y el veredicto (COS-22).
- ``recorte(proyeccion, umbrales)``: «mod11», «mod23» o «pendiente» (§4.9; COS-12).
- ``contenido_costo(mediciones, proyeccion, umbrales)``: el contenido de ``costo_m1.json`` (resumen; lo escribe la
  batería por ``salidas``, CEG-20).

Dueño: I21 (ola 6).
Lecturas propias (COS-n), para el addendum de M1:
- COS-1. **El grafo: diferencia con §1 del diseño** (para el addendum; PED-1, aprobado y aplicado por el coordinador
  el 2026-10-28). §1 da a ``costo`` sintetico, candidatos, tendencias, producto, ambiental, orquestacion y entorno; la
  medición necesita además tipos, constantes, fijados, fondo_era5l, particiones, politicas (las políticas de lectura
  del punto 1), salud (la agregación comunal, la lluvia y la representatividad de M5, y la HR de las tablas anchas
  sintéticas) y ceguera (el registro de accesos de cada punto, COS-21; PED-3), que se importan directamente (todas de
  capas ≤ 5: sin ciclos). ``costo`` no escribe (§0, regla 8): los artefactos y los meses sintéticos los escribe
  ``sintetico`` en la carpeta temporal que da quien llama, o en una propia de ``entorno.carpeta_de_trabajo`` (COS-23).
- COS-2. **Los conteos de la proyección** (§8 del diseño, «Supuestos»; §8 del texto). 579 estaciones, 52,2 M horas
  con dato, H = 234.120 horas desde ``PRODUCTO_DESDE`` (2000-01-01 a 2026-09-15: 321 meses y 27 años, que se derivan
  de H), 8.206 píxeles válidos, 838.430 celdas, 108.579 celdas pobladas, ≈ 110 bloques de P2 con estaciones (M2a
  los cuenta), 345 comunas de la muestra de M6 (MC-14). Son cifras de costo, no reglas (anexo A2,
  ``NO_NORMATIVOS``): viven en ``CONTEOS`` y van a ``costo_m1.json``. P1 tiene ``P1_PLIEGUES`` pliegues (Anexo A).
- COS-3. **Una medición por proceso** (§8.1: «tiempo de pared y de CPU con un hilo, y memoria pico»). Cada punto corre
  en un trabajador de ``orquestacion.repartir`` (hilos en 1, ``nice``, ``RegistroAccesos`` en bloqueo sobre /Volumes,
  ``SinRed``); se le da una segunda unidad vacía para que ``repartir`` lance trabajadores (con una sola unidad corre en
  el principal). La memoria es ``ru_maxrss`` del trabajador: el pico de todo lo que vivió en él, también la
  fabricación del mundo sintético; por eso se informa además la memoria al terminar de fabricar y los bytes de cada
  insumo. Con ``aislar=False`` (pruebas) todo corre en este proceso, la memoria no es la de la medición y no hay
  contención.
- COS-4. **El mundo sintético a escala.** Estaciones en una franja con la forma de Chile (§8 del diseño no fija la
  geometría; la DMC no se abre): latitudes de ``-18`` a ``-54``, más densas en el centro, cada una con un período
  continuo de reportes horarios cuyo largo medio da las 52,2 M horas con dato (cobertura 52,2 M / (579·H)). El fondo
  en las estaciones cubre todas las horas (como M2a) y los residuos sólo las del período, con AR(1), un sesgo suave y
  un 2 % de horas inválidas (sin UTM: nada de lo medido la usa). Las celdas pobladas, si ``real_era5``, son 108.579
  sorteadas con la semilla entre las celdas de ``celdas.parquet`` con ``cod_comuna`` > 0 (sólo su geometría; la
  población y los pesos son sintéticos: no se abre ``poblacion_celda_anio.parquet`` ni GHS-POP); si no, una rejilla
  sintética. Los píxeles son los centros de 0,1° que rodean las celdas (catálogo y altitud sintéticos); los meses,
  campos suaves en unidades nativas.
- COS-5. **El peor caso donde el texto no fija el valor** (la decisión es ciega). Hiperparámetros del núcleo:
  el L más grande (más vecinos dentro del corte) y un par (λ, κ) distinto para cada variable y para cada parte de AB
  (8 juegos de núcleo: el peor caso del operador, P109); α del medio de ``C_ALFAS``. La TF, con las tres reglas de red
  constante (la medida usa la de 2000-2025) y decide la más cara. El 0,1°, la salud y la grilla, con un barrido por
  grupo y por candidato: «base» (A en todos) y cada grupo con cada otro candidato del uso; el peor es
  t(base) + Σ_g máx_c máx(0, t(g=c) − t(base)), una cota superior (si C gana en dos grupos, su diseño común se cuenta
  dos veces). La selección, con el mód 11 (sin recorte): el recorte sólo abarata la selección (MC-16). Decide la cota
  superior; la proyección informa también M3-4 con la regla más barata y, si el recorte cambiaría, lo dice (P-COS-5).
- COS-6. **Proyección** (§8.1 del diseño): por fase, T = Σ_u t_u·n_u·c / P + T_serie + arranque + el desequilibrio,
  con P = ``procesos`` (D2: 8), o en las fases de reparto el número de procesos que cabe en memoria (D59, COS-25), y c
  el factor de contención (COS-20). El desequilibrio es la unidad más larga (cota del
  reparto en lista), uno por cada ``repartir``: la selección, cada pasada de TF, las dos pasadas de M5 y cada variante
  de la grilla. Cada tiempo medido se escala linealmente por su número de unidades (horas con dato, estaciones,
  celdas-hora, pliegues o meses) del mundo medido al real. Lo que cada trabajador rearma una vez
  (``_datos_produccion``, la pasada de TF, los operadores) cuenta una vez en la pared de su fase.
- COS-7. **Las unidades de cada fase** (``orquestacion``): M3-4: una por estación (control de calidad), una por
  pliegue externo más la de producción (selección y predicción; P1 tiene ~N/10 estaciones de prueba por pliegue y P2
  las de un bloque) y una por mes en cada pasada de TF; en serie, lo de COS-18. M5: una primera pasada por mes (la
  t2m de los píxeles del reloj: una lectura) y una unidad por año (cada mes del año y el enero siguiente: otra
  lectura, el 0,1°, la salud con el agudo dos veces —las tres carpetas y la representatividad— y el crónico, y la
  lluvia); en serie, el operador de la grilla y la representatividad (COS-19). La grilla v2: una unidad por mes y
  variante. M6: sólo las columnas de la muestra de la TF de contaminantes (la fábrica de v2 no está escrita), en el
  proceso principal (ORQ-29), con los dos escenarios de TF1, las dos variantes y los dos contaminantes, sin las
  réplicas (el modelo las repite, no las columnas).
- COS-8. **TF por año** (TEN-4, TEN-10): un mes cuesta lo fijo del mes (leer, el fondo de los lotes y la finitud de E0)
  más una cuenta por cada red distinta de los escenarios de ese año (k = 2 en los años con «completo» y «constante»;
  k = 3 en 2015-2019, que suman la histórica). «Un año de TF» (§8.1) se mide como seis meses de 2017 (k = 3) y seis
  de 2012 (k = 2), y se proyecta cada año con su k (P-COS-8). El primer mes de cada pasada trae lo que el trabajador
  arma una vez (vecinos de las celdas); se cuenta aparte. Los tamaños de las redes van a ``costo_m1.json``.
- COS-9. **Lo que no se mide**: las laterales de M5 y el modelo de la TF de contaminantes de M6 («sin_medir»);
  las métricas, el remuestreo, π y la decisión de M3-4 (en serie) entran como la cota de §8 del diseño, < 0,3 h
  (``REFERENCIAS``), no como cero. La selección con el mód 23 no se mide (MC-16).
- COS-10. **El mes real** (§8.1, punto 6; CEG-5; MC-31): ``ERA5L/mensual/era5land_202401_chile_pixeles.nc`` (el nombre
  de ``_comun_modelo.ruta_mensual``, como ``salud.insumos_s14``), en sólo lectura: primero sus bytes con ``open`` de
  Python y su sha256, después ``fondo_era5l.leer_mes`` con esa huella. Sólo con ``real_era5=True``; con False no se
  abre nada real (tampoco ``celdas.parquet``). La escala de §8.1 exige ``real_era5=True`` (COS-22).
- COS-11. **La memoria** (§8: «≤ 8 GB en la competencia»; A30, P117, P-ORQ-11; H2). Cada punto arma su
  ``DatosCompetencia`` por el camino de la corrida (COS-24), así que el pico de su trabajador ya es el máximo entre la
  etapa en que se arma y la de su trabajo, no su suma. A otra escala se suma lo que la red real trae de más: por horas
  con dato, los residuos y el fondo guardado; por estaciones, las filas de C, el clima y la caché (COS-15); por celdas y
  píxeles, los estáticos y el clima de M2a; en M5, el operador de la grilla, que sus trabajadores leen para las
  laterales, y, sin la geometría real, el operador de salud en las 838.430 celdas como cota. El principal de M3-4
  (ORQ-44) es el máximo entre armar la ligera (el pico medido al armarla en la TF) y tenerla con un año de meses de
  ERA5-Land (RR06); el de M5, la ligera y el operador de la grilla. El grupo es n trabajadores más el principal,
  frente a la memoria física (de ``os.sysconf``; no lee datos), y de ahí los procesos de cada fase (COS-25). El
  control de calidad se proyecta en la estación más larga (H horas) por la recta entre una estación con la mitad de sus
  meses y con todos (``tracemalloc``), frente a los ≈ 340 MB de §8. GB = 10⁹ B y el tope es ``MEMORIA_MAX_GB``·10⁹ B (la
  lectura estricta; P-COS-4), también para el principal de M3-4 (P-ORQ-11, rige la propuesta).
- COS-12. **El recorte** (§4.9; §8: «Recorte por costo: sólo el de §4.9»): «mod23» si la pared proyectada de M3-4
  (con los procesos de cada fase, COS-25) pasa de ``SEL_UMBRAL_H`` horas (> 36 h; 36 h exactas es «mod11»), sólo si el
  veredicto decide (COS-22); si no, «pendiente», y ``costo_m1.json`` lo lleva marcado con sus motivos.
- COS-13. **La máquina libre** (§8.1: «con la máquina libre (carga < 2, sin la descarga TROPOMI ni otra corrida
  pesada)»; ``COSTO_CARGA_MAX``; H3). Lo que se exige es que no haya otro trabajo pesado, no que la medición no cargue
  la máquina. ``medir`` lee la carga de 1 min (``os.getloadavg``): al empezar, la bruta debe ser < 2 (la escala de
  §8.1 se niega a empezar si no); mientras corre cada punto, cada ``_INTERVALO_CARGA_S`` segundos (un hilo del
  principal), la carga ajena —la bruta menos los procesos de la medición que corren en ese momento (el que mide el
  punto: su trabajador, o este proceso sin aislar), sin bajar de 0— debe ser < 2 en toda lectura. Una lectura no finita
  no es libre. La contención carga la máquina a propósito y no cuenta. No se buscan otras corridas pesadas con ``ps``:
  haría falta lanzar un proceso, y sólo ``orquestacion`` los lanza (§0, regla 3). ``costo_m1.json`` lleva las dos series
  (bruta y ajena) de cada punto (P-COS-6).
- COS-14. **La grilla por muestra de lotes.** Un mes de la grilla entera con C cuesta ≈ 1,5 h por variante (ensayo a
  escala intermedia: ≈ 1,8 µs por celda-hora y variable, CAN-18) y el barrido mide diez ganadores: la escala real mide
  ``lotes_grilla`` = 16 lotes de ``LOTE_CELDAS`` repartidos parejo en el orden de las celdas (65.536 de 838.430) y
  proyecta por celda-hora, como «un mes de la grilla» (P-COS-7). Con ``lotes_grilla`` = None se mide el mes entero.
- COS-15. **La caché de ``candidatos``** (``_CACHE``, por ``DatosCompetencia``). Desde CAN-19 (I13, ola 6) no guarda
  series: sólo la referencia a cada tabla de residuos (que ``_bytes_cache`` no cuenta otra vez) y r̄ por estación y
  variable (12 × 24): ≈ 7 MB con la red entera; se escala por estaciones. La primera unidad de un trabajador la arma (en
  frío) y las demás la usan (en tibio): se mide el pliegue de P2 en frío y en tibio, y el de P1 con más estaciones de
  prueba en tibio. La selección de un pliegue es el de P2 en tibio menos sus estaciones de prueba; el tiempo de una
  estación de prueba, la diferencia entre P1 y P2 por estación; lo que el frío trae de más, una vez por trabajador.
- COS-16. **El punto 1** (§8.1, punto 1; ORQ-11). ``qc_estaciones`` estaciones sintéticas del centro de la franja,
  con reportes horarios limpios de ``qc_meses`` meses de 2017 (5 × 12 = 60 artefactos a escala real), descargadas por
  ``run_download`` del descargador fijado con el cliente falso (``sintetico.fabricar_descarga``), la política de RELOJ
  sintética con F(−4) (``sintetico.politica_reloj_sintetica``) y sus políticas de lectura (``politicas``); después
  ``orquestacion._unidad_estacion`` por estación, que carga el código fijado (adaptador, ``dmc_features`` y el
  validador de RELOJ, con ``permitir_cargados`` porque el mundo es sintético) y corre el paso 1, el envoltorio, K4,
  la retirada y la marca 14. La tasa es la pared de esas unidades por hora de dato (las etiquetas del período); la
  primera carga del código fijado queda dentro (una vez por trabajador).
- COS-17. **Las unidades reales, por sus nombres privados.** Se mide con las funciones que corre M3-4 y M5, no con
  copias: ``orquestacion._unidad_estacion``, ``_unidad_pliegue``, ``_seleccionar_todo``, ``_selecciones``,
  ``_unidad_mes_tf`` y ``_sub_operador`` (y ``ambiental._theta_json``, ``candidatos._CACHE``). Como la unidad de TF
  rearma su pasada desde el disco, la medición deja su ``tendencias.PasadaTF`` (armada en memoria) en
  ``orquestacion._PASADAS`` bajo una clave propia, que es la caché de una pasada por proceso que esa unidad consulta, y
  la vacía al terminar; su armado se mide aparte. Si ``orquestacion`` cambia esas firmas, las pruebas de este módulo
  fallan.
- COS-18. **La serie del principal de M3-4** (H5). Además de los residuos (``residuos_estacion``, ``en_horas`` y
  ``fondo_era5l.residuos``), A, la ``DatosCompetencia`` del principal y la lectura de los 321 meses para RR06: escribir
  las tablas de control de calidad y releerlas, y escribir los residuos, medidos como codificar y decodificar parquet
  en memoria (sin el disco: la medición no escribe) por fila, sobre las tablas reales del punto 1 y una muestra de
  ``_MUESTRA_TABLAS`` estaciones del punto 2; y la cota de COS-9.
- COS-19. **Lo que M5 suma** (H7). En serie en el principal: el operador de la grilla (con AB en todos los grupos,
  8 juegos de núcleo) y la representatividad (``salud.representatividad`` sobre la red del punto 2). En cada
  trabajador, una vez: su ``DatosCompetencia`` y el operador de salud sobre todas las celdas con ``cod_comuna`` > 0
  (``orquestacion._salud_de``; sin ``real_era5``, las 838.430 como cota). Por mes: la lluvia comunal en sus tres tipos
  de día (``salud.pesos_lluvia`` y ``lluvia_comunal``, con un enlace sintético de cada celda a su píxel).
- COS-20. **El factor de contención** (H5). Ocho procesos que leen la memoria a la vez van más lento que uno solo: la
  unidad de contención (un lote de ``LOTE_PUNTOS_TF`` celdas de un mes de TF, ``PasadaTF.sumas_mes``, tres veces) corre
  sola en un trabajador y en P copias a la vez; el factor (≥ 1) es la mediana de las copias, sin su primera
  repetición, sobre la sola, y multiplica lo que corre en paralelo. Sin medirlo (``aislar=False``), el veredicto queda
  «pendiente».
- COS-21. **Cada punto con su registro** (H8). Además del de ``repartir`` (/Volumes), cada punto corre bajo su
  ``ceguera.RegistroAccesos`` en bloqueo sobre /Volumes, DATOS, LOCAL, la auditoría de APH y la configuración de AP
  (las de ``rutas`` y las reales); con ``real_era5`` sólo se permiten ``GRILLA/celdas.parquet`` y el mes real, y cada
  punto informa qué archivos reales abrió (por nombre).
- COS-22. **La escala de §8.1 y el veredicto** (H1-H3). La escala se juzga por sus tamaños (``fallas_escala``), no por
  su nombre: 579 estaciones, H horas desde 2000-01-01, la cobertura de los conteos, ≥ 50 artefactos de un año, doce
  meses de TF con 2 y 3 redes, 108.579 celdas en la TF y en salud y las 838.430 de la grilla. El recorte decide sólo
  si la proyección está completa (los seis puntos y la contención), con P = ``PROCESOS``, a la escala de §8.1, con el
  mes real, con la máquina libre en toda la medición, si cada fase de reparto de M3-4 y de M5 cabe en memoria con al
  menos un proceso y si el principal de M3-4 queda bajo el tope (COS-25); si no, «pendiente» con sus motivos.
- COS-23. **La carpeta de trabajo** (H10; PED-3 de I22). Sin ``temporal``, ``medir`` corre en una carpeta nueva de
  ``entorno.carpeta_de_trabajo(PREFIJO_TRABAJO)`` (0700, directamente bajo la temporal del sistema), que se borra al
  terminar, también si un punto falla, sin seguir enlaces (ENT-9); ``costo`` no crea ni borra nada (§0, regla 8).
  Como el borrado usa nombres relativos, si quien llama vigila AP o APH con un ``RegistroAccesos``, el directorio
  actual debe estar en la temporal del sistema (VER-18).
- COS-24. **El mismo camino que la corrida** (ORQ-42 a ORQ-44). La ``DatosCompetencia`` de cada punto sale de
  ``orquestacion._datos_produccion`` (la misma de la receta) con lo de M2a en memoria como en el disco (en parquet: los
  estáticos de las celdas de la escala, 838.430 a escala real; z_E5L; el clima del estado de los píxeles; la tabla de
  las estaciones con su operador) y el fondo de cada estación pedido de a una, con lo que guarda cada variante: la
  selección, el fondo de los días de selección (``orquestacion._fondo_en_seleccion``), y cada pliegue lee el fondo
  entero de sus estaciones de prueba por demanda (``fondo_prueba``, ``orquestacion._con_fondo_de_prueba``); la TF, M5 y
  la grilla, la ligera, sin fondo. La diferencia con la corrida: el fondo y lo de M2a no se leen del disco (se
  fabrican; los bytes parquet de M2a viven en memoria mientras se arma) y las tablas anchas de prueba llevan sólo las
  columnas que lee la evaluación (como ``orquestacion._Anchas``). La contención usa un mundo chico (un mes).
- COS-25. **Los procesos por fase** (D59, respuesta a P145 y a P-COS-3; P146 la extiende a M5; A39). Las fases de
  reparto son las de ``orquestacion.FASES_REPARTO``: en M3-4, «artefactos» (la memoria del control de calidad en la
  estación más larga), «seleccion_y_prediccion» (la de la selección) y «tendencias_y_finitud» (la de la TF, las dos
  pasadas); en M5, «representatividad» y «anual» (la del punto 4). La de la representatividad
  (``orquestacion._unidad_t2m``: un mes ERA5-Land leído entero, del que guarda la t2m de los píxeles del reloj, con un
  contexto mínimo) tiene por cota el pico del trabajador del punto «mes_real», que lee entero el mes real (su huella y
  su lectura) y además importa todo el paquete; sin el mes real medido, no se midió. En cada fase, n es el mayor número
  de 1 a P con el trabajador bajo el tope de §8 y n trabajadores más el principal de su compuerta (el de M3-4 o el de
  M5, COS-11; en M5 la serie de t2m de los píxeles del reloj, ≤ H × 579 × 8 B, queda bajo el operador de la grilla que
  ya cuenta) bajo la memoria física; n = 0 si no cabe ni con uno o si falta una medida. La memoria se calcula primero y
  cada fase se proyecta con su n (con P si n = 0, sólo como información: el veredicto no decide), con el factor de
  contención medido con P copias (una cota superior con menos). M6 y la grilla v2 siguen con P. «procesos_por_fase»
  ({compuerta: {fase: n}}) va en la proyección y en la raíz de ``costo_m1.json`` (A39). Si alguna fase corre con menos
  de P, el veredicto lo dice en una nota. Cada fase de la memoria lleva el grupo con P («grupo_gb») y con su n
  («grupo_con_n_gb»). La proyección lleva además la pared de M3-4 con P en todas las fases («pared_h_con_P», la de
  antes de D59, con la regla de TF más cara con P; P147): no decide, pero si con ella el recorte sería otro, el
  veredicto lo dice en una nota. Con todo bajo los topes con P, ningún número cambia.
Preguntas para el autor (P-COS-n; rige la más estricta): P-COS-1, el desequilibrio como la unidad más larga entera
(rige: cota superior); P-COS-2, el tope de 8 GB: ¿por trabajador (rige, §8 «≤ 8 GB en la competencia»), y además el
grupo frente a la memoria física?; P-COS-3, respondida por D59 (P145; P146 la extiende a M5): la fase que no cabe en
memoria con 8 procesos corre con el mayor número que quepa y su pared se proyecta con ese número; si no cabe ni con uno,
el recorte queda «pendiente» (COS-25); P-COS-4, la unidad del tope:
¿8 GB son 8·10⁹ B (rige, la estricta) u 8·2³⁰ B?; P-COS-5, ¿qué proyección decide el recorte: la cota superior
coherente (rige: la regla de red y el ganador más caros) o la esperada?; P-COS-6 (revisada), ¿«carga < 2» es la carga
ajena a la medición —la bruta al empezar y, durante cada punto, la bruta menos los procesos de la medición que corren,
sin la contención— (rige, COS-13) o la bruta en toda la medición (que aquí nunca se cumple: el fondo de la máquina
ronda 1,3-1,7 y el trabajador suma ≈ 1)?; P-COS-7, ¿la grilla con 16
lotes repartidos (COS-14) vale como «un mes de la grilla» de §8.1? (rige: sí, proyectada por celda-hora; con
``lotes_grilla`` = None, el mes entero); P-COS-8, ¿seis meses de 2017 y seis de 2012 (COS-8) valen como «un año de
TF»? (rige: sí, son los dos tipos de año de la proyección).
Pedidos (PED-n): PED-1 (coordinador; aprobado y aplicado): tipos, constantes, fijados, fondo_era5l, particiones,
politicas y salud en ``DEPENDENCIAS["costo"]`` (COS-1). PED-2 (I13): resuelto por CAN-19 (la caché ya no crece con las
horas). PED-3 (coordinador; aplicado): ceguera en ``DEPENDENCIAS["costo"]`` (COS-21). PED-4: resuelto por I1 en
``entorno.carpeta_de_trabajo`` (ENT-9; COS-23), no en ``sintetico``.
Depende de: sintetico, candidatos, tendencias, producto, ambiental, orquestacion, entorno; y, por PED-1 y PED-3
(COS-1), tipos, constantes, fijados, fondo_era5l, particiones, politicas, salud y ceguera.
"""
from __future__ import annotations

import dataclasses
import gzip
import hashlib
import io
import json
import math
import os
import re
import resource
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping, Sequence

import numpy as np
import pandas as pd

from meteo_combinada import ambiental, candidatos, ceguera, constantes, entorno, fijados, fondo_era5l  # COS-1
from meteo_combinada import orquestacion, particiones, politicas, producto, salud, sintetico, tendencias, tipos  # COS-1
from meteo_combinada.tipos import Candidato, Grupo, Hiper, Uso

# Las lecturas COS-n de este encabezado, en orden (van a costo_m1.json y al addendum).
LECTURAS = tuple(f"COS-{n}" for n in sorted({int(x) for x in re.findall(r"^- COS-(\d+)\.", __doc__, re.M)}))
ESQUEMA_MEDICIONES = "meteo-combinada-costo-mediciones/1"
ESQUEMA_COSTO = "meteo-combinada-costo/1"
PUNTOS = ("qc", "pliegue", "tf", "m5", "grilla", "mes_real", "contencion")
PENDIENTE = "pendiente"
SIN_MEDIR = "sin_medir"
BASE = "base"                                 # COS-5: A en todos los grupos (el barrido parte de ahí)
PREFIJO_TRABAJO = "costo_"                    # COS-23: la carpeta de trabajo de medir sin «temporal»
PASADAS = ("ambiental", "salud")              # TEN-12
VARIANTES = (tipos.Variante.I.value, tipos.Variante.D.value)
MES_REAL = "202401"                           # COS-10: el mes de S14
CARPETA_MENSUAL = "mensual"                   # COS-10
_GB = 10 ** 9                                 # no-umbral: GB decimal, 10⁹ B (COS-11; P-COS-4)
_MB = 10 ** 6                                 # no-umbral: MB decimal
_MS = 1000
_S_H = 3600
_ARTEFACTOS_MIN = 50                          # no-umbral: §8.1 del diseño, «≥ 50 artefactos sintéticos de un año»
_MUESTRA_TABLAS = 20                          # no-umbral: estaciones cuya tabla de residuos se codifica (COS-18)
_REPETICIONES = 3                             # no-umbral: repeticiones de la unidad de contención (COS-20)
_INTERVALO_CARGA_S = 30                       # no-umbral: cada cuánto se lee la carga durante un punto (COS-13)

# COS-25 (D59, A39): de qué memoria medida sale cada fase de reparto de ``orquestacion.FASES_REPARTO``, y el principal
# de cada medida que no es de M3-4 («m34» por omisión).
_MEMORIA_DE_FASE = MappingProxyType({"artefactos": "control_de_calidad", "seleccion_y_prediccion": "seleccion",
                                     "tendencias_y_finitud": "tf", "representatividad": "representatividad",
                                     "anual": "m5"})
_COMPUERTA_DE_MEMORIA = MappingProxyType({"representatividad": "m5", "m5": "m5"})
_faltan_fases = sorted({f for fs in orquestacion.FASES_REPARTO.values() for f in fs} - set(_MEMORIA_DE_FASE))
if _faltan_fases:
    raise ImportError(f"costo (D59): las fases de reparto {_faltan_fases} no tienen memoria (COS-25)")

# COS-9: cifras del texto y del diseño que entran como referencia o como cota de lo no medido (no son reglas).
REFERENCIAS = MappingProxyType({
    "qc_por_proceso_mb": 340,                 # no-umbral: §8 del texto, «≈ 340 MB por proceso» (NO_NORMATIVOS)
    "serie_no_medida_h": 0.3,                 # no-umbral: §8 del diseño, métricas, remuestreo y decisión «< 0,3 h»
})

# COS-2: conteos de §8 del diseño (cifras de costo, no reglas).
CONTEOS = MappingProxyType({
    "estaciones": 579,                        # no-umbral: conteo de §8 del diseño (COS-2)
    "horas_con_dato": 52_200_000,             # no-umbral: conteo de §8 del diseño (COS-2)
    "horas": 234_120,                         # no-umbral: H de §8 del diseño (COS-2)
    "pixeles": 8_206,                         # no-umbral: conteo de §8 del diseño (COS-2)
    "celdas": 838_430,                        # no-umbral: conteo de §8 del diseño (COS-2)
    "celdas_pobladas": 108_579,               # no-umbral: conteo de §8 del diseño (COS-2)
    "bloques_p2": 110,                        # no-umbral: ≈ bloques de P2 de §8 del diseño (COS-2)
    "comunas_m6": 345,                        # no-umbral: comunas de la muestra de M6 (MC-14; COS-2)
})

# COS-4: coeficientes del mundo sintético (no son umbrales del texto).
_SINT = MappingProxyType({
    "lat_norte": -18.0, "lat_sur": -54.0,     # no-umbral: franja sintética (COS-4)
    "lon_costa": -70.3, "lon_pendiente": 0.1, "ancho_lon": 1.5,     # no-umbral: franja sintética (COS-4)
    "z_mar": 50.0, "z_andes": 2500.0,         # no-umbral: altitud sintética en m (COS-4)
    "t_media": 15.0, "gradiente": 0.0065, "t_lat": 0.03, "t_anual": 6.0, "t_diaria": 5.0,   # no-umbral: COS-4
    "deficit": 5.0, "deficit_diario": 2.0, "p_anual": 2.0, "p_diaria": 0.8,               # no-umbral: COS-4
    "u_diaria": 1.5, "v_media": 0.5, "v_amplitud": 0.3, "v_periodo_h": 41.0,              # no-umbral: COS-4
    "hora_max": 19.0, "hora_sesgo": 15.0, "fase_anual": 0.05,                              # no-umbral: COS-4
    "sesgo_T": 1.0, "sesgo_diario": 0.5, "ruido_T": 0.8, "ruido_Td": 0.9, "ruido_uv": 0.6,   # no-umbral: COS-4
    "sesgo_u": 0.3, "sesgo_v": -0.2, "sesgo_p": 0.002, "ruido_p": 0.0003,                 # no-umbral: COS-4
    "ar1": 0.9, "truncar_ar1": 1e-6, "invalidas": 0.02, "lluvia_m": 1e-4,                 # no-umbral: COS-4
    "beta": 2.5, "dispersion_cobertura": 0.6,                                              # no-umbral: COS-4
})
_HORAS_ANIO_MEDIO = 8766                      # no-umbral: horas de un año medio (365,25 × 24), sólo para el ciclo
_CIFRAS_ANIO = 4                              # no-umbral: AAAA de un AAAAMM
_VECINOS_F = orquestacion.N_VECINOS            # los 4 centros ERA5-Land de un punto (§4.1; pix0-pix3, w0-w3)
# Punto 1 (COS-16): reportes limpios de un año, como ``test_orquestacion._portal``.
_QC = MappingProxyType({
    "viento_min": 4, "viento_ciclo": 9, "dir_paso": 37, "dir_ciclo": 36, "dir_grados": 10,   # no-umbral: COS-16
    "lat_centro": -33.5, "anio": 2017,                                                       # no-umbral: COS-16
    "sha_catalogo": "c" * 64})
_GEO = MappingProxyType({"vuelta": 360.0, "polo": 90.0, "decimales": 6})   # no-umbral: grados y redondeo del catálogo


class ErrorCosto(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Escala de la medición
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Escala:
    """Los tamaños de una medición. ``ESCALA_REAL`` es la de §8.1 del diseño; ``ESCALA_PRUEBA``, la de las pruebas."""
    nombre: str
    estaciones: int
    desde: str                       # AAAA-MM-DD: primera hora del período (UTC)
    horas: int                       # H
    cobertura: float | None          # fracción media de H con dato por estación (None: la de CONTEOS, COS-4)
    lat_norte: float
    lat_sur: float
    qc_estaciones: int
    qc_meses: int
    celdas_tf: int
    meses_tf: tuple[str, ...]        # AAAAMM
    mes_m5: str                      # AAAAMM
    celdas_salud: int
    celdas_grilla: int
    lote_grilla: int
    lotes_grilla: int | None         # None: todos los lotes (el mes entero)

    @property
    def artefactos(self) -> int:
        return int(self.qc_estaciones * self.qc_meses)


ESCALA_REAL = Escala(
    nombre="real", estaciones=CONTEOS["estaciones"], desde=str(constantes.valor("PRODUCTO_DESDE")),
    horas=CONTEOS["horas"], cobertura=None, lat_norte=_SINT["lat_norte"], lat_sur=_SINT["lat_sur"],
    qc_estaciones=5, qc_meses=12,             # no-umbral: 60 artefactos de un año (§8.1: ≥ 50)
    celdas_tf=CONTEOS["celdas_pobladas"],
    meses_tf=("201701", "201702", "201703", "201704", "201705", "201706",
              "201207", "201208", "201209", "201210", "201211", "201212"),
    mes_m5="201707", celdas_salud=CONTEOS["celdas_pobladas"], celdas_grilla=CONTEOS["celdas"],
    lote_grilla=orquestacion.LOTE_CELDAS, lotes_grilla=16)         # no-umbral: COS-14 (65.536 celdas del mes)

ESCALA_PRUEBA = Escala(
    nombre="prueba", estaciones=36, desde="2016-01-01", horas=2 * 8784, cobertura=1.0,   # no-umbral: escala chica
    lat_norte=-32.6, lat_sur=-35.4,           # no-umbral: escala chica
    qc_estaciones=1, qc_meses=2, celdas_tf=240, meses_tf=("201701", "201207"), mes_m5="201701",   # no-umbral: chica
    celdas_salud=200, celdas_grilla=300, lote_grilla=128, lotes_grilla=None)                     # no-umbral: chica


# ---------------------------------------------------------------------------
# Tiempos y memoria
# ---------------------------------------------------------------------------
def _rss_gb() -> float:
    """El pico de memoria residente del proceso (``ru_maxrss``: bytes en macOS, KB en Linux), en GB."""
    pico = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return float(pico if sys.platform == "darwin" else pico * 1024) / _GB


class _Reloj:
    """Pared (``perf_counter``) y CPU del proceso (``process_time``; un hilo, §8) de un tramo."""

    def __enter__(self):
        self.t0, self.c0 = time.perf_counter(), time.process_time()
        return self

    def __exit__(self, *exc):
        self.pared = time.perf_counter() - self.t0
        self.cpu = time.process_time() - self.c0
        return False

    def dict(self) -> dict:
        return {"pared_s": float(self.pared), "cpu_s": float(self.cpu)}


def _carga() -> float:
    try:
        return float(os.getloadavg()[0])
    except OSError:
        return math.nan


def _bytes_tabla(df) -> int:
    return int(df.memory_usage(index=True, deep=True).sum())


def _bytes_obj(x) -> int:
    """Bytes de arreglos, tablas y estructuras de ellos (las filas de C, el clima)."""
    if isinstance(x, pd.DataFrame):
        return _bytes_tabla(x)
    if isinstance(x, np.ndarray):
        return int(x.nbytes)
    if isinstance(x, Mapping):
        return sum(_bytes_obj(v) for v in x.values())
    if isinstance(x, (list, tuple)):
        return sum(_bytes_obj(v) for v in x)
    if dataclasses.is_dataclass(x):
        return sum(_bytes_obj(getattr(x, f.name)) for f in dataclasses.fields(x))
    return 0


# ---------------------------------------------------------------------------
# El mundo sintético (COS-4)
# ---------------------------------------------------------------------------
def _h_de_fecha(texto: str) -> int:
    epoca = np.datetime64(str(constantes.valor("PRODUCTO_DESDE")), "h")
    return int((np.datetime64(texto, "h") - epoca).astype(np.int64))


def _anio(yyyymm: str) -> int:
    return int(str(yyyymm)[:_CIFRAS_ANIO])


def _mes(yyyymm: str) -> int:
    return int(str(yyyymm)[_CIFRAS_ANIO:])


def _horas_mes(yyyymm: str) -> np.ndarray:
    inicio = np.datetime64(f"{_anio(yyyymm):04d}-{_mes(yyyymm):02d}", "M")
    epoca = np.datetime64(str(constantes.valor("PRODUCTO_DESDE")), "h")
    return np.arange((inicio.astype("datetime64[h]") - epoca).astype(np.int64),
                     ((inicio + 1).astype("datetime64[h]") - epoca).astype(np.int64), dtype=np.int64)


def _lon_costa(lat):
    return _SINT["lon_costa"] - _SINT["lon_pendiente"] * (_SINT["lat_norte"] - np.asarray(lat, dtype=np.float64))


def _z(lat, lon):
    """Altitud sintética (m): sube de la costa a los Andes."""
    x = np.clip((np.asarray(lon, dtype=np.float64) - _lon_costa(lat)) / _SINT["ancho_lon"], 0.0, 1.0)
    return _SINT["z_mar"] + _SINT["z_andes"] * x ** 2


def _macrozona(lat: float) -> str:
    cortes = (-26.0, -32.0, -38.0, -44.0)     # no-umbral: macrozonas sintéticas por latitud (COS-4)
    for m, c in zip(tipos.MACROZONAS, cortes):
        if lat > c:
            return m
    return tipos.MACROZONAS[-1]


def _campos(lat, z, h, k=0):
    """El fondo sintético (°C, hPa y m/s) en puntos (columnas) y horas (filas)."""
    s = _SINT
    h = np.asarray(h, dtype=np.float64)[:, None]
    hora = np.mod(h, 24.0)
    anual = np.cos(2 * np.pi * (h / _HORAS_ANIO_MEDIO - s["fase_anual"]))
    diaria = np.cos(2 * np.pi * (hora - s["hora_max"]) / 24)
    lat, z = np.asarray(lat, dtype=np.float64)[None, :], np.asarray(z, dtype=np.float64)[None, :]
    T = s["t_media"] - s["gradiente"] * z + s["t_lat"] * (lat - _SINT["lat_norte"]) + s["t_anual"] * anual \
        + s["t_diaria"] * diaria
    Td = T - s["deficit"] - s["deficit_diario"] * diaria ** 2
    p = _p_std(z) + s["p_anual"] * np.sin(2 * np.pi * h / _HORAS_ANIO_MEDIO) \
        + s["p_diaria"] * np.cos(2 * 2 * np.pi * hora / 24)
    u = s["u_diaria"] * np.sin(2 * np.pi * hora / 24) + 0.0 * z + (np.asarray(k) % 7) / 10   # no-umbral: COS-4
    v = s["v_media"] + s["v_amplitud"] * np.cos(h / s["v_periodo_h"]) + 0.0 * z
    return {"T_F": T, "Td_F": Td, "p_F": p, "u_F": u, "v_F": v}


def _p_std(z):
    """p_std(z) en hPa con los coeficientes de ``constantes.P_STD`` (§2.3)."""
    p0, k, n = constantes.valor("P_STD")
    return p0 * (1.0 - k * np.asarray(z, dtype=np.float64)) ** n


def _ar1(rng, n: int) -> np.ndarray:
    """Un AR(1) de varianza 1 por su respuesta al impulso truncada donde φ^k < 10⁻⁶ (convolución)."""
    phi = _SINT["ar1"]
    k = int(math.ceil(math.log(_SINT["truncar_ar1"]) / math.log(phi)))
    nucleo = math.sqrt(1 - phi ** 2) * phi ** np.arange(k)
    e = rng.standard_normal(n + k)
    return np.convolve(e, nucleo, mode="valid")[:n]


def _residuos_sinteticos(rng, h, lat: float, z: float) -> dict:
    """r_T, r_Td, r_u, r_v y r_p = ln(QFE/p_F) de una estación en sus horas (NaN en las inválidas)."""
    s = _SINT
    hora = np.mod(h, 24).astype(np.float64)
    b = s["sesgo_T"] + s["sesgo_diario"] * np.cos(2 * np.pi * (hora - s["hora_sesgo"]) / 24) + z / 1000 \
        + (lat - s["lat_norte"]) / 100
    r = {"T": b + s["ruido_T"] * _ar1(rng, h.size), "Td": b / 2 + s["ruido_Td"] * _ar1(rng, h.size),
         "u": s["sesgo_u"] + s["ruido_uv"] * _ar1(rng, h.size), "v": s["sesgo_v"] + s["ruido_uv"] * _ar1(rng, h.size),
         "p": s["sesgo_p"] + s["ruido_p"] * _ar1(rng, h.size)}
    for v in r:
        r[v][rng.random(h.size) < s["invalidas"]] = np.nan
    return r


@dataclass
class _Red:
    infos: dict
    periodos: dict                   # código → (h0, h1) de sus reportes (h1 excluido)
    h0: int
    h1: int


def _red(U, escala: Escala) -> _Red:
    """Las estaciones sintéticas (COS-4): posición, altitud, grupo, bloque, celda y período de reportes."""
    rng = np.random.default_rng([int(U.a("SEMILLA")), escala.estaciones])
    n = int(escala.estaciones)
    u = rng.beta(_SINT["beta"], _SINT["beta"], n)
    lat = escala.lat_norte + (escala.lat_sur - escala.lat_norte) * u
    lon = _lon_costa(lat) + _SINT["ancho_lon"] * rng.random(n)
    z = np.round(_z(lat, lon))
    nan = math.nan
    codigos = [f"{300000 + i:06d}" for i in range(n)]     # no-umbral: códigos sintéticos de 6 dígitos
    infos = {}
    for i, c in enumerate(codigos):
        infos[c] = tipos.InfoEstacion(
            codigo=c, nombre=f"E{c}", conjunto="N", macrozona=_macrozona(float(lat[i])), grupo=tipos.id_grupo([c]),
            omm=None, tipo=None, propietario=None, lat_txt=f"{lat[i]:.4f}", lon_txt=f"{lon[i]:.4f}",
            alt_txt=f"{z[i]:.0f}", lat=float(lat[i]), lon=float(lon[i]), z_cat=float(z[i]), rho_km=nan, k3_pasa=True,
            z_s=float(z[i]), z_s_fuente="catalogo", celda=i + 1, utm_e=nan, utm_n=nan, bloque="",
            pix0=-1, pix1=-1, pix2=-1, pix3=-1, w0=nan, w1=nan, w2=nan, w3=nan, respaldo_16km=False, sin_fondo=False,
            excluida=False, motivo=None)
    grupos = particiones.grupos_mismo_sitio(infos, U)
    bloques = particiones.bloque(lat, lon, U)
    infos = {c: dataclasses.replace(infos[c], grupo=grupos[c], bloque=str(b)) for c, b in zip(codigos, bloques)}
    H = int(escala.horas)
    h0 = _h_de_fecha(escala.desde)
    cob = escala.cobertura if escala.cobertura is not None else \
        CONTEOS["horas_con_dato"] / (CONTEOS["estaciones"] * CONTEOS["horas"])
    d = _SINT["dispersion_cobertura"] * min(cob, 1 - cob)
    largos = np.clip(np.round(H * (cob + d * (2 * rng.random(n) - 1))), 24, H).astype(np.int64)
    inicios = h0 + np.floor(rng.random(n) * (H - largos + 1)).astype(np.int64)
    periodos = {c: (int(inicios[i]), int(inicios[i] + largos[i])) for i, c in enumerate(codigos)}
    return _Red(infos=infos, periodos=periodos, h0=h0, h1=h0 + H)


def _en_ventana(periodo, ventanas) -> np.ndarray:
    """Las horas del período de una estación que caen en ``ventanas`` [(h0, h1), …] (None: todo el período)."""
    a, b = periodo
    if ventanas is None:
        return np.arange(a, b, dtype=np.int64)
    partes = [np.arange(max(a, v0), min(b, v1), dtype=np.int64) for v0, v1 in ventanas if max(a, v0) < min(b, v1)]
    return np.concatenate(partes) if partes else np.empty(0, dtype=np.int64)


def _estaticos(ids, lat, lon, z_media, z_poblada, cod_comuna, rng) -> pd.DataFrame:
    """``tipos.ESQUEMA_ESTATICAS_CELDA_C`` sintético (TIP-22), una fila por celda."""
    n = len(ids)
    lat = np.asarray(lat, dtype=np.float64)
    fr = rng.dirichlet(np.ones(len(tipos.LULC)), size=n)
    macro = np.array([tipos.MACROZONA_COD[_macrozona(float(x))] for x in lat], dtype=np.int8)
    tabla = {"celda": np.asarray(ids, dtype=np.int64), "z_media": np.asarray(z_media, dtype=np.float64),
             "z_poblada": np.asarray(z_poblada, dtype=np.float64), "z_poblada_es_media": np.zeros(n, bool),
             "frac_dato": np.ones(n), "tpi1": rng.normal(0.0, 20.0, n),                   # no-umbral: COS-4
             "tpi5": rng.normal(0.0, 60.0, n),                                             # no-umbral: COS-4
             "tpi1_truncado": np.zeros(n, bool), "tpi5_truncado": np.zeros(n, bool),
             "pendiente_deg": rng.uniform(1.0, 15.0, n),                                  # no-umbral: COS-4
             "log_dist_costa": np.log1p(100 * np.clip(np.asarray(lon) - _lon_costa(lat), 0, None)),
             **{col: fr[:, i] for i, col in enumerate(tipos.LULC)}, "lat": lat, "macrozona_cod": macro,
             "cod_comuna": np.asarray(cod_comuna, dtype=np.int32),
             tipos.COLUMNA_Z_E5L: np.asarray(z_media, dtype=np.float64) - 100.0}         # no-umbral: COS-4
    df = pd.DataFrame(tabla).astype(dict(tipos.ESQUEMA_ESTATICAS_CELDA_C))
    df.attrs = {"esquema": tipos.ESQUEMA_ESTATICAS_CELDA_C.version}
    return df


def _clima_estado(lat, z) -> dict[str, np.ndarray]:
    """El clima del estado (TIP-17) de puntos: variable → punto × 12 × 24 (mes, hora UTC), desde el fondo sintético."""
    meses = np.arange(1, 13)
    horas = np.arange(24)
    h = ((meses[:, None] - 1) * (_HORAS_ANIO_MEDIO / 12) + horas[None, :]).ravel()
    F = _campos(lat, z, h)
    T = F["T_F"].T.reshape(-1, 12, 24)
    dif = (F["T_F"] - F["Td_F"]).T.reshape(-1, 12, 24)
    rap = np.hypot(F["u_F"], F["v_F"]).T.reshape(-1, 12, 24)
    amp = np.broadcast_to(T.max(axis=2, keepdims=True) - T.min(axis=2, keepdims=True), T.shape)
    return dict(zip(tipos.VARIABLES_CLIMA_ESTADO, (T, dif, rap, np.ascontiguousarray(amp))))


@dataclass
class _Mundo:
    """Lo que un punto arma de la red (COS-24): la ``DatosCompetencia`` (por ``orquestacion._datos_produccion``, como
    la receta), lo de M2a (``extras``), sus tiempos y bytes, y el fondo de cada estación por demanda (``fondo``)."""
    datos: object
    extras: dict
    tiempos: dict
    bytes: dict
    fondo: Callable
    anchas_de: Callable


def _tabla_estaciones(infos: Mapping) -> pd.DataFrame:
    """``ESQUEMA_ESTACIONES_MC`` (``estaticas/estaciones.parquet`` de M2a) desde las ``InfoEstacion``."""
    nombres = list(tipos.ESQUEMA_ESTACIONES_MC)
    filas = [{n: getattr(infos[c], n) for n in nombres} for c in sorted(infos)]
    df = pd.DataFrame(filas, columns=nombres).astype(dict(tipos.ESQUEMA_ESTACIONES_MC))
    df.attrs = {"esquema": tipos.ESQUEMA_ESTACIONES_MC.version}
    return df


def _tabla_z(z_tabla: pd.DataFrame) -> pd.DataFrame:
    """``ESQUEMA_ZE5L`` (``estaticas/z_e5l.parquet``) sintético: todos válidos, caso 1 (§4.1)."""
    n = len(z_tabla)
    nan = np.full(n, np.nan)
    df = pd.DataFrame({"pixel_id": z_tabla["pixel_id"].to_numpy(np.int64), "valido": np.ones(n, bool),
                       "z_e5l": z_tabla["z_e5l"].to_numpy(np.float64), "caso": "1", "z_nasadem": nan,
                       "frac_nasadem": nan, "z_hipso": nan, "dif_mayor_50m": np.zeros(n, bool)})
    return df.astype(dict(tipos.ESQUEMA_ZE5L))


def _estaticos_m2a(red: _Red, n_celdas: int, U) -> pd.DataFrame:
    """``estaticas/celdas.parquet`` de M2a: ``n_celdas`` celdas (las 838.430 a escala real), con las de las estaciones
    (ids 1 … N) en sus coordenadas y las demás repartidas en la franja (COS-24)."""
    rng = np.random.default_rng([int(U.a("SEMILLA")), n_celdas])
    infos = [red.infos[c] for c in sorted(red.infos)]
    n = max(int(n_celdas), len(infos))
    lat = rng.uniform(_SINT["lat_sur"], _SINT["lat_norte"], n)
    lon = _lon_costa(lat) + _SINT["ancho_lon"] * rng.random(n)
    for info in infos:
        lat[int(info.celda) - 1], lon[int(info.celda) - 1] = info.lat, info.lon
    z = _z(lat, lon)
    return _estaticos(np.arange(1, n + 1), lat, lon, z, z, np.ones(n, dtype=np.int32), rng)


def _datos(U, red: _Red, *, variante: str, c_est: bool, n_celdas: int, ventanas=None, recorte: bool = False) -> _Mundo:
    """La ``DatosCompetencia`` de la red por el camino de la corrida (COS-24; ORQ-42, ORQ-44): residuos por estación
    (``residuos_estacion``), A (``climatologias_a``) y después ``orquestacion._datos_produccion`` con lo de M2a en
    memoria (los estáticos de ``n_celdas`` celdas, z_E5L, el clima del estado de los píxeles y la tabla de las
    estaciones, en parquet como en el disco) y el fondo de cada estación pedido de a una (aquí se fabrica; en la corrida
    se lee del disco), con lo que guarda cada variante: «seleccion», el fondo de los días de selección
    (``orquestacion._fondo_en_seleccion``); «ligera», nada (TF, M5, M6, la grilla y el principal de M3-4).
    ``ventanas``: sólo esas horas (None: todo H)."""
    rng_base = int(U.a("SEMILLA"))
    codigos = sorted(red.infos)
    lat_e = np.array([red.infos[c].lat for c in codigos])
    lon_e = np.array([red.infos[c].lon for c in codigos])
    z_e = np.array([red.infos[c].z_s for c in codigos])
    cat, z_pix, validos = _pixeles(lat_e, lon_e)
    op_e = fondo_era5l.operador(lat_e, lon_e, z_e, cat, validos, z_pix, U, ids=np.array(codigos, dtype=object))
    cols = fondo_era5l.columnas_operador(op_e).set_index("id")
    infos = {}
    for c in codigos:
        f = cols.loc[c]
        infos[c] = dataclasses.replace(red.infos[c], **{f"pix{k}": int(f[f"pix{k}"]) for k in range(_VECINOS_F)},
                                       **{f"w{k}": float(f[f"w{k}"]) for k in range(_VECINOS_F)},
                                       respaldo_16km=bool(f["respaldo_16km"]), sin_fondo=bool(f["sin_fondo"]))
    horas_fondo = np.arange(red.h0, red.h1, dtype=np.int64) if ventanas is None else \
        np.concatenate([np.arange(a, b, dtype=np.int64) for a, b in ventanas])
    k_de = {c: k for k, c in enumerate(codigos)}
    t_gen = [0.0]

    def fondo(c):
        t0 = time.perf_counter()
        info = infos[c]
        F = fondo_era5l.tabla_puntos(horas_fondo, {key: v[:, 0] for key, v in
                                                   _campos([info.lat], [info.z_s], horas_fondo, k_de[c]).items()})
        t_gen[0] += time.perf_counter() - t0
        return F
    residuos, tramos = {}, []
    t_res = t_obs = 0.0
    horas_dato = 0
    for c in codigos:
        info = infos[c]
        h = _en_ventana(red.periodos[c], ventanas)
        if h.size == 0:
            continue
        r = _residuos_sinteticos(np.random.default_rng([rng_base, k_de[c]]), h, info.lat, info.z_s)
        Fh = {key: v[:, 0] for key, v in _campos([info.lat], [info.z_s], h, k_de[c]).items()}
        t0 = time.perf_counter()                       # M3-4, paso 6 (en serie): r desde la observación (COS-18)
        obs = {"T": Fh["T_F"] + r["T"], "Td": Fh["Td_F"] + r["Td"], "u": Fh["u_F"] + r["u"], "v": Fh["v_F"] + r["v"],
               "QFE": Fh["p_F"] * np.exp(r["p"])}
        fondo_era5l.residuos(obs, Fh)
        t_obs += time.perf_counter() - t0
        t0 = time.perf_counter()
        residuos[c], tr = candidatos.residuos_estacion(c, h, r, U)
        t_res += time.perf_counter() - t0
        tramos.append(tr)
        horas_dato += int(h.size)
        del r, Fh, obs
    with _Reloj() as t_clima:
        clima_a = candidatos.climatologias_a(residuos, U)
    tramos_t = pd.concat(tramos, ignore_index=True) if tramos else tipos.tabla_vacia(tipos.ESQUEMA_TRAMOS_HOMOGENEOS)
    del tramos
    est_m2a = _estaticos_m2a(red, n_celdas, U)
    archivos = {"estaticas/celdas.parquet": _codificar(est_m2a), "estaticas/z_e5l.parquet": _codificar(_tabla_z(z_pix)),
                "insumos/clima_estado.parquet": _codificar(_tabla_clima(cat, z_pix)),
                "estaticas/estaciones.parquet": _codificar(_tabla_estaciones(infos))}
    del est_m2a
    infos = orquestacion.infos_de_tabla(pd.read_parquet(io.BytesIO(archivos["estaticas/estaciones.parquet"])))
    if variante == "seleccion":
        guardar = lambda F: orquestacion._fondo_en_seleccion(F, U, recorte)        # noqa: E731 (ORQ-42)
    elif variante == "ligera":
        guardar = lambda F: None                                                       # noqa: E731 (ORQ-44)
    else:
        raise ErrorCosto(f"variante {variante!r}: «seleccion» o «ligera»")
    with _Reloj() as t_armar:
        datos, extras = orquestacion._datos_produccion(residuos, clima_a, tramos_t, {"leer": archivos.__getitem__},
                                                       infos, fondo, U, c_est=c_est, guardar=guardar)
    del archivos
    if variante == "ligera":
        datos = dataclasses.replace(datos, puntos_e5l={}, clima_estado={})
    else:
        grupos = {c: datos.estaciones[c].grupo for c in datos.estaciones}
        datos = dataclasses.replace(datos, pliegues=tuple(particiones.pliegues_p1(grupos, U)
                                                          + particiones.pliegues_p2(datos.estaciones, grupos, U)))

    def anchas_de(cods) -> dict:
        salida = {}
        for c in cods:
            df = datos.residuos[c]
            m = df["observada"].to_numpy(bool)
            hq = df["h"].to_numpy(np.int64)[m]
            Fh = fondo_era5l.en_horas(fondo(c), hq)
            r = {v: df[f"r_{v}"].to_numpy(np.float64)[m] for v in ("T", "Td", "u", "v", "p")}
            T, Td = Fh["T_F"] + r["T"], Fh["Td_F"] + r["Td"]
            u, v = Fh["u_F"] + r["u"], Fh["v_F"] + r["v"]
            qfe = Fh["p_F"] * np.exp(r["p"])
            hr = salud.hr_del_producto(T, Td)
            salida[c] = pd.DataFrame({
                "h": hq.astype(np.int32), "Ts": T, "valido_T": np.isfinite(T), "td_final": Td,
                "valido_Td": np.isfinite(Td), "hr_final": hr, "valido_HR": np.isfinite(hr), "u_final": u,
                "valido_viento": np.isfinite(u) & np.isfinite(v), "v_final": v, "QFE": qfe,
                "valido_p": np.isfinite(qfe)})
        return salida
    n_gen = t_gen[0]
    tiempos = {"residuos_s": t_res, "en_horas_residuos_s": t_obs, "clima_a_s": t_clima.pared,
               "filas_c_s": max(0.0, t_armar.pared - n_gen), "horas_dato": horas_dato,
               "estaciones_con_dato": len(datos.estaciones)}
    bytes_ = {"residuos": sum(_bytes_tabla(x) for x in datos.residuos.values()),
              "campos_estaciones": sum(_bytes_tabla(x) for x in datos.puntos_e5l.values()),
              "filas_c": _bytes_obj(datos.filas_c), "clima_estaciones": _bytes_obj(datos.clima_estado),
              "clima_a": _bytes_tabla(clima_a), "estaticos_celdas": _bytes_tabla(extras["estaticos_m2a"]),
              "clima_pixeles": _bytes_tabla(extras["clima_tabla"]),
              "filas_estaticos": int(len(extras["estaticos_m2a"])),
              "filas_clima_pixeles": int(len(extras["clima_tabla"]))}
    return _Mundo(datos=datos, extras=extras, tiempos=tiempos, bytes=bytes_, fondo=fondo, anchas_de=anchas_de)


def _ventanas_de_meses(meses) -> list[tuple[int, int]]:
    salida = []
    for m in sorted(meses):
        h = _horas_mes(m)
        salida.append((int(h[0]), int(h[-1]) + 1))
    return salida


# --- celdas y píxeles ---
def _leer_celdas_reales(rutas) -> pd.DataFrame:
    """La geometría de ``GRILLA/celdas.parquet`` (§8.1, punto 3; MC-31): sus bytes con ``open`` de Python y después
    pyarrow en memoria (CEG-5). Sólo ``celda``, ``lat``, ``lon`` y ``cod_comuna``."""
    import io
    import pyarrow.parquet as pq
    with open(Path(rutas.grilla) / "celdas.parquet", "rb") as f:
        datos = f.read()
    t = pq.read_table(io.BytesIO(datos), columns=["celda", "lat", "lon", "cod_comuna"]).to_pandas()
    t.attrs = {}
    return t


def _celdas_sinteticas(n: int, escala: Escala) -> pd.DataFrame:
    """Una rejilla de 0,01° en la franja sintética, con una comuna por cada 50 celdas."""
    paso = 0.01                                    # no-umbral: celdas de ≈ 1 km (§3)
    ancho = max(1, int(round(_SINT["ancho_lon"] / paso)))
    k = np.arange(n)
    lat = escala.lat_norte - paso / 2 - paso * (k // ancho)
    lon = np.round(_lon_costa(lat) / paso) * paso + paso / 2 + paso * (k % ancho)
    return pd.DataFrame({"celda": (k + 1).astype(np.int64), "lat": lat, "lon": lon,
                         "cod_comuna": (1000 + k // 50).astype(np.int64)})        # no-umbral: comunas sintéticas


def _celdas(ctx, n: int, *, pobladas: bool, semilla: str) -> pd.DataFrame:
    """``n`` celdas con su z media y poblada y, si ``pobladas``, un w_ghs sintético > 0 (COS-4): sorteadas con la
    semilla entre las de ``cod_comuna`` > 0 de ``celdas.parquet`` (``real_era5``) o de la rejilla sintética."""
    U, escala = ctx["U"], ctx["escala"]
    base = _leer_celdas_reales(ctx["rutas"]) if ctx["real_era5"] else _celdas_sinteticas(max(n, 1), escala)
    rng = np.random.default_rng([int(U.a("SEMILLA")), sum(map(ord, semilla))])
    if pobladas:
        base = base[base["cod_comuna"].to_numpy(np.int64) > 0]
        if n < len(base):
            base = base.iloc[np.sort(rng.choice(len(base), size=n, replace=False))]
    else:
        base = base.iloc[:n]
    t = base.sort_values("celda").reset_index(drop=True)
    lat, lon = t["lat"].to_numpy(np.float64), t["lon"].to_numpy(np.float64)
    t["z_media"] = _z(lat, lon)
    t["z_poblada"] = t["z_media"] - 10.0 * rng.random(len(t))                        # no-umbral: COS-4
    t["w_ghs"] = rng.lognormal(0.0, 1.0, len(t)) if pobladas else 0.0
    return t


def _pixeles(lat, lon) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray]:
    """(catálogo, z_E5L, válidos) sintéticos: los centros de 0,1° que rodean las celdas (con sus vecinos), con las
    columnas y la numeración del catálogo real (``sintetico.catalogo_pixeles``)."""
    res, vuelta, polo, d = float(sintetico.RESOLUCION_ERA5L), _GEO["vuelta"], _GEO["polo"], _GEO["decimales"]
    columnas_lon = int(round(vuelta / res))
    i = np.floor(np.round((polo - np.asarray(lat)) / res, d) + 1 / 2).astype(np.int64)
    j = np.floor(np.round(np.mod(np.asarray(lon), vuelta) / res, d) + 1 / 2).astype(np.int64) % columnas_lon
    base = np.unique(i * columnas_lon + j)
    bi, bj = base // columnas_lon, base % columnas_lon
    todos = np.unique(np.concatenate([(bi + di) * columnas_lon + (bj + dj) % columnas_lon
                                      for di in (-1, 0, 1) for dj in (-1, 0, 1)]))
    pi, pj = todos // columnas_lon, todos % columnas_lon
    plat = np.round(polo - pi * res, d)
    plon = np.round(pj * res, d)
    plon = np.where(plon > vuelta / 2, np.round(plon - vuelta, d), plon)
    cat = pd.DataFrame({"pixel_id": todos, "latitude": plat, "longitude": plon,
                        "cell_west": np.round(plon - res / 2, d), "cell_east": np.round(plon + res / 2, d),
                        "cell_south": np.round(plat - res / 2, d), "cell_north": np.round(plat + res / 2, d),
                        "cod_comuna": np.ones(todos.size, dtype=np.int64), "territorio": "continental",
                        "lat_index_global": pi, "lon_index_global": pj})
    cat = cat.astype({"territorio": "string"})
    z = pd.DataFrame({"pixel_id": todos, "z_e5l": _z(plat, plon)})
    return cat, z, todos


def _campos_mes(cat: pd.DataFrame, z_tabla: pd.DataFrame, yyyymm: str) -> tuple[dict, np.ndarray, np.ndarray]:
    """Los campos de un mes en unidades nativas (K, Pa, m/s y m) en los píxeles del catálogo: (campos, tiempos, h)."""
    h = _horas_mes(yyyymm)
    tiempos = sintetico.horas_del_mes(_anio(yyyymm), _mes(yyyymm))
    F = _campos(cat["latitude"].to_numpy(np.float64), z_tabla["z_e5l"].to_numpy(np.float64), h)
    kelvin = float(constantes.valor("KELVIN"))
    campos = {"t2m": F["T_F"] + kelvin, "d2m": F["Td_F"] + kelvin, "sp": F["p_F"] * 100.0, "u10": F["u_F"],
              "v10": F["v_F"],
              "tp": sintetico.tp_acumulado(tiempos, np.full((h.size, len(cat)), _SINT["lluvia_m"]))}
    return campos, tiempos, h


def _mes_en_memoria(cat, z_tabla, yyyymm: str):
    campos, _, h = _campos_mes(cat, z_tabla, yyyymm)
    return fondo_era5l.MesE5L(tiempos=h.astype(np.int32), pixel_id=cat["pixel_id"].to_numpy(np.int64),
                              datos={k: np.ascontiguousarray(v, dtype=np.float32) for k, v in campos.items()},
                              sha256="0" * 64)


# --- hiperparámetros y ganadores (COS-5) ---
_ORDEN_THETA = ("T", "Td", "u", "p")          # u y v comparten θ (MC-43)


def _hiper(U, k: int = 0) -> Hiper:
    """COS-5: el L más grande (más vecinos dentro del corte) y, para que cada variable y cada parte de AB tenga su
    juego de núcleo (hasta 8, el peor caso del operador, P109), el k-ésimo par (λ, κ) en el orden del texto."""
    lams, kappas = tuple(U.a("NUC_LAMBDA")), tuple(U.a("NUC_KAPPA"))
    pares = [(lam, kappa) for kappa in kappas for lam in lams]
    lam, kappa = pares[k % len(pares)]
    return Hiper(float(max(U.a("NUC_L"))), float(lam), float(kappa))


def _alfa(U) -> float:
    alfas = tuple(U.a("C_ALFAS"))
    return float(alfas[len(alfas) // 2])


def _theta(cand: str, U, variable: str = "T"):
    """θ de un candidato y una variable del producto (COS-5): A y B, el juego de la variable; AB, (el de A, el de Φ′),
    distintos; C y C_est, α."""
    i = 2 * _ORDEN_THETA.index("u" if variable == "v" else variable)
    return {"A": _hiper(U, i), "B": _hiper(U, i), "AB": (_hiper(U, i), _hiper(U, i + 1))}.get(cand, _alfa(U))


def _hiper_de(ganador: Mapping[str, str], U) -> dict:
    return {v: _theta(c, U, v) for g, c in ganador.items() for v in producto.VARIABLES_DE_GRUPO[Grupo(g)]}


# ---------------------------------------------------------------------------
# Los puntos de §8.1 (cada uno en su trabajador)
# ---------------------------------------------------------------------------
def _portal(T, Td, p, z_s: float, h: np.ndarray, k: int) -> dict:
    """Los reportes de una estación limpia (como ``test_orquestacion._portal``): Ts y Td al décimo, HR coherente,
    viento sin rachas ni ceros, QFE y un QFF coherente con QFE (ninguna regla de §2.4 debería saltar)."""
    i = np.arange(h.size)
    Ts = np.round(np.asarray(T, dtype=np.float64), 1)
    Td = np.round(np.minimum(np.asarray(Td, dtype=np.float64), Ts - 1 / 2), 1)
    HR = np.round(salud.hr_del_producto(Ts, Td))
    QFE = np.round(np.asarray(p, dtype=np.float64) * np.exp(_SINT["sesgo_p"]), 1)
    t_media = Ts + float(constantes.valor("KELVIN")) + _SINT["gradiente"] * z_s / 2
    QFF = np.round(QFE * np.exp(float(constantes.valor("GRAVEDAD")) * z_s
                                / (float(constantes.valor("R_SECO")) * t_media)), 1)
    vel = (_QC["viento_min"] + (i + k) % _QC["viento_ciclo"]).astype(float)
    dirs = (((_QC["dir_paso"] * i + k) % _QC["dir_ciclo"] + 1) * _QC["dir_grados"]).astype(float)
    return {"Ts": Ts, "Td": Td, "relative_humidity": HR, "wind_speed_instant": vel,
            "wind_direction_instant": dirs, "QFE": QFE, "QFF": QFF}


def _memoria_traza(funcion, *args) -> int:
    """El pico de lo que asigna una llamada (``tracemalloc``: numpy y Python; no las asignaciones de C que no lo
    informan)."""
    import tracemalloc
    tracemalloc.start()
    try:
        funcion(*args)
        return int(tracemalloc.get_traced_memory()[1])
    finally:
        tracemalloc.stop()


def _medir_qc(ctx) -> dict:
    """Punto 1: ``orquestacion._unidad_estacion`` (paso 1 con ``cargar_dmc``, el envoltorio, K4, retirada y marca 14)
    sobre los artefactos sintéticos de un año (el descargador fijado con su cliente falso, la política de RELOJ
    sintética con F(−4)), en ms por hora de dato."""
    U, escala = ctx["U"], ctx["escala"]
    ap = entorno.rutas_reales().ap                              # sólo el código fijado
    descargador = fijados.cargar_descargador(ap)
    raiz = sintetico.destino_temporal(Path(ctx["temporal"]) / "qc")
    rs = entorno.rutas_sinteticas(raiz)
    red = _red(U, escala)
    codigos = sorted(red.infos, key=lambda c: abs(red.infos[c].lat - _QC["lat_centro"]))[:escala.qc_estaciones]
    codigos = sorted(codigos)
    anio = _QC["anio"]
    desde = f"{anio:04d}-01-01"
    fin = np.datetime64(f"{anio:04d}-{escala.qc_meses:02d}", "M") + 1
    hasta = str((fin.astype("datetime64[D]") - 1))
    minutos = int(constantes.valor("S12_RELOJ")[0])            # UTC−4 (F(−4))
    L = pd.date_range(f"{desde}T00:00", f"{hasta}T23:00", freq="h")
    h = ((L - pd.Timedelta(minutes=minutos) - pd.Timestamp(str(constantes.valor("PRODUCTO_DESDE"))))
         // pd.Timedelta(hours=1)).to_numpy().astype(np.int64)
    estaciones, F = [], {}
    for k, c in enumerate(codigos):
        info = red.infos[c]
        campos = {key: v[:, 0] for key, v in _campos([info.lat], [info.z_s], h, k).items()}
        F[c] = fondo_era5l.tabla_puntos(h, campos)
        T = campos["T_F"] + _SINT["sesgo_T"]
        cols = _portal(T, campos["Td_F"] + _SINT["sesgo_T"] / 2, campos["p_F"], info.z_s, h, k)
        estaciones.append(sintetico.estacion_sintetica(c, info.lat, info.lon, info.z_s, L, **cols))
    with _Reloj() as t_fab:
        dmc = sintetico.fabricar_descarga(estaciones, rs.dmc.parent, descargador, desde, hasta)
    regla = [{"tramo": "1.1", "valid_from": f"{desde}T00:00:00", "valid_to": f"{hasta}T23:00:00",
              "minutos": minutos, "veredicto": "F(-4)"}]
    sintetico.politica_reloj_sintetica(rs.ap.parent, sintetico.artefactos_de_descarga(dmc), {c: regla for c in codigos})
    rp = sintetico.rutas_politica_sintetica(rs.ap.parent)
    registro = politicas.leer_registro_c5(rp["registro"], ap=rs.ap)
    pol, artefactos = politicas.leer_politica_reloj(registro, ap=rs.ap)
    k2 = politicas.coordenadas_inconsistentes(registro, ap=rs.ap)
    with open(rp["artefactos"], "rb") as f:
        lista = json.loads(gzip.decompress(f.read()))
    indice = {x["artefacto_sha256"]: k for k, x in enumerate(lista)}
    manifiestos = sintetico.manifiestos_de(dmc)
    ctx_est = {"ap": str(ap), "huellas_reloj": dict(fijados.HUELLAS_RELOJ), "ruta_politica": str(rp["politica"]),
               "artefactos": dict(artefactos), "U": U, "k2": k2, "sintetico": True}
    unidades = []
    for c in codigos:
        info = red.infos[c]
        meses = {(anio, m) for m in range(1, escala.qc_meses + 1)}
        tramos = politicas.tramos_de_lectura(pol, c, meses, politicas.marcas_g(pol, c), info=info, k2=k2)
        lectura = politicas.politicas_de_lectura(pol, info, tramos, U, sha_protocolo=U.sha256_texto_vigente,
                                                 sha_catalogo=_QC["sha_catalogo"])
        ms = []
        for ruta in manifiestos.get(c, []):
            with open(ruta, "rb") as f:
                meta = json.loads(f.read())
            ms.append((str(ruta), indice[meta["artifact_sha256"]]))
        unidades.append({"codigo": c, "info": info, "F": F[c], "lectura": lectura, "manifiestos": ms})
    n_art = sum(len(u["manifiestos"]) for u in unidades)
    tiempos, filas, anchas = [], 0, []
    antes = _rss_gb()                                  # COS-11: lo que crece con la estación
    for u in unidades:
        with _Reloj() as t:
            r = orquestacion._unidad_estacion(u, ctx_est)
        tiempos.append(t.dict())
        if r["ancha"] is not None:
            filas += int(len(r["ancha"]))
            anchas.append(r["ancha"])
    pico = _rss_gb()
    # COS-11: lo que pide una estación con todos sus meses y con la mitad (sin el código ya cargado): la recta da lo
    # que crece con las horas y lo fijo de una unidad
    memoria_meses = {}
    for n_m in sorted({max(1, len(unidades[0]["manifiestos"]) // 2), len(unidades[0]["manifiestos"])}):
        memoria_meses[n_m] = _memoria_traza(orquestacion._unidad_estacion,
                                            {**unidades[0], "manifiestos": unidades[0]["manifiestos"][:n_m]}, ctx_est)
    pared = sum(x["pared_s"] for x in tiempos)
    horas = int(len(L)) * len(codigos)
    return {"artefactos": n_art, "estaciones": len(codigos), "horas_dato": horas, "horas_estacion": int(len(L)),
            "filas_anchas": filas, "fabricar_s": t_fab.pared, "estaciones_t": tiempos,
            "pared_s": pared, "cpu_s": sum(x["cpu_s"] for x in tiempos), "ms_por_hora": pared * _MS / max(horas, 1),
            "memoria_antes_unidades_gb": antes, "memoria_unidades_gb": pico,
            "memoria_por_meses": {str(k): int(v) for k, v in memoria_meses.items()},
            "anchas_tablas": _tasas_de_tablas(anchas)}             # COS-18: escribirlas y releerlas (serie)


def _bytes_por_fila(esquema) -> int:
    """Bytes por fila de un esquema de columnas numéricas y lógicas (los anchos de numpy)."""
    return int(sum(np.dtype(str(t)).itemsize for t in dict(esquema).values()))


def _codificar(df) -> bytes:
    """Los bytes parquet de una tabla, en memoria (lo que ``salidas`` escribe; aquí no se escribe nada)."""
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)                   # no-escribe: en memoria, para medir la codificación (COS-18)
    return buf.getvalue()


def _tasas_de_tablas(tablas) -> dict:
    """Segundos por fila de codificar y de releer (parquet en memoria) unas tablas, y sus bytes por fila (COS-18)."""
    tablas = [t for t in tablas if t is not None and len(t)]
    filas = sum(len(t) for t in tablas)
    with _Reloj() as t_c:
        datos = [_codificar(t) for t in tablas]
    with _Reloj() as t_d:
        for b in datos:
            pd.read_parquet(io.BytesIO(b))
    return {"filas": int(filas), "codificar_s_por_fila": t_c.pared / max(filas, 1),
            "releer_s_por_fila": t_d.pared / max(filas, 1),
            "bytes_por_fila": sum(_bytes_tabla(t) for t in tablas) / max(filas, 1),
            "bytes_parquet_por_fila": sum(len(b) for b in datos) / max(filas, 1)}


def _medir_pliegue(ctx) -> dict:
    """Punto 2: la red a escala con la receta de la selección (COS-24; ORQ-42), lo que M3-4 hace en serie con ella
    (residuos, A, filas de C, escribir los residuos), un pliegue externo de P2 en frío y en tibio y el pliegue de P1 con
    más estaciones de prueba (en tibio), con el fondo entero de sus estaciones de prueba por demanda
    (``fondo_prueba``), y la representatividad de M5 (en serie en el principal, COS-19)."""
    U, escala = ctx["U"], ctx["escala"]
    red = _red(U, escala)
    mundo = _datos(U, red, variante="seleccion", c_est=True, n_celdas=escala.celdas_grilla)
    datos, t_datos, bytes_ = mundo.datos, mundo.tiempos, mundo.bytes
    p2 = [p for p in datos.pliegues if p.particion is tipos.Particion.P2 and p.prueba]
    p1 = [p for p in datos.pliegues if p.particion is tipos.Particion.P1 and p.prueba]
    if not p2 or not p1:
        raise ErrorCosto("la red sintética no tiene pliegues de P1 y de P2 con estaciones de prueba")
    externo = sorted(p2, key=lambda p: (len(p.prueba), p.id))[len(p2) // 2]
    mayor_p1 = sorted(p1, key=lambda p: (-len(p.prueba), p.id))[0]
    horas = _horas_validas(datos)
    n_bandas = len(tuple(U.a("BANDAS_KM"))) + 1
    pi = np.full(n_bandas, 1.0 / n_bandas)
    pi_sel = {u.value: {k: pi for k in horas} for u in (Uso.AMBIENTAL, Uso.AGUDO, Uso.CRONICO)}
    d1, h1, d2, h2 = constantes.valor("ESTRATO_PERIODOS")
    sel = orquestacion._selecciones(orquestacion.PARES)
    muestra = sorted(datos.residuos)[:_MUESTRA_TABLAS]
    residuos_t = _tasas_de_tablas([datos.residuos[c] for c in muestra])           # COS-18: escribirlos (serie)
    filas_res = sum(len(x) for x in datos.residuos.values())
    with _Reloj() as t_rep:                                                        # COS-19: M5, en serie
        _representatividad(datos, mundo.fondo, U)
    rss_fabricado = _rss_gb()

    def correr(externo_):
        anchas = mundo.anchas_de(externo_.prueba)
        ctx_sel = {"U": U, "datos": datos, "infos": datos.estaciones, "anchas": anchas, "F": datos.puntos_e5l,
                   "fondo_prueba": mundo.fondo, "horas": horas, "pi_sel": pi_sel, "recorte": False,
                   "pares": orquestacion.PARES, "periodos": {f"{d1}-{h1}": (d1, h1), f"{d2}-{h2}": (d2, h2)}}
        with _Reloj() as t:
            r = orquestacion._unidad_pliegue({"pliegue": externo_, "selecciones": sel}, ctx_sel)
        return t, r
    # COS-15: la caché de candidatos es por DatosCompetencia: la primera unidad del proceso la arma (en frío)
    t_frio, r = correr(externo)
    cache = _bytes_cache(datos)
    t_tibio, _ = correr(externo)
    t_p1, _ = correr(mayor_p1)
    n_p2, n_p1 = len(externo.prueba), len(mayor_p1.prueba)
    por_estacion = max(0.0, t_p1.pared - t_tibio.pared) / max(n_p1 - n_p2, 1)
    bytes_["cache_series"] = cache
    return {"estaciones": len(datos.estaciones), "horas": int(escala.horas),
            "horas_dato": t_datos["horas_dato"], "filas_residuos": int(filas_res), "pliegues_p1": len(p1),
            "pliegues_p2": len(p2), "prueba": n_p2, "prueba_p1": n_p1,
            "prueba_max_p1": max(len(p.prueba) for p in p1), "entrenamiento": len(externo.entrenamiento),
            "selecciones": len(sel), "evaluaciones": len(r["filas"]),
            "residuos_s": t_datos["residuos_s"], "en_horas_residuos_s": t_datos["en_horas_residuos_s"],
            "clima_a_s": t_datos["clima_a_s"], "filas_c_s": t_datos["filas_c_s"], "residuos_tablas": residuos_t,
            "representatividad_s": t_rep.pared, "pliegue": t_frio.dict(), "pliegue_tibio": t_tibio.dict(),
            "pliegue_p1": t_p1.dict(), "por_estacion_prueba_s": por_estacion,
            "memoria_tras_fabricar_gb": rss_fabricado, "bytes": bytes_,
            "filas_campos_estaciones": {"guardado": int(sum(len(F) for F in datos.puntos_e5l.values())),       # ORQ-42
                            "entero": int(len(datos.puntos_e5l) * escala.horas)}}


def _representatividad(datos, fondo: Callable, U) -> frozenset:
    """``salud.representatividad`` con las estaciones de la red (ORQ-24; COS-19): la T observada (fondo + residuo, en
    sus horas observadas) frente a la t2m del píxel (aquí, el fondo en todas las horas, en K)."""
    kelvin = float(constantes.valor("KELVIN"))
    obs, pix = {}, {}
    for c, df in datos.residuos.items():
        m = df["observada"].to_numpy(bool)
        h = df["h"].to_numpy(np.int64)[m]
        F = fondo(c)
        obs[c] = (h, fondo_era5l.en_horas(F, h)["T_F"] + df["r_T"].to_numpy(np.float64)[m])
        pix[c] = (F["h"].to_numpy(np.int64), F["T_F"].to_numpy(np.float64) + kelvin)
    return salud.representatividad(obs, pix, U)


def _bytes_cache(datos) -> int:
    """COS-15: los bytes de la caché de ``candidatos`` de una DatosCompetencia (desde CAN-19, sólo r̄: las tablas de
    residuos que referencia no se cuentan otra vez)."""
    return _bytes_obj(candidatos._CACHE.get(datos, {}))


def _horas_validas(datos) -> dict:
    """Las horas válidas por clave de ``validacion.CLAVES_HORAS`` (las de ``orquestacion._horas_validas_total``),
    desde los residuos observados: T, Td, HR = T y Td, viento = u y v, p."""
    ligeras = {}
    for c, df in datos.residuos.items():
        m = df["observada"].to_numpy(bool)
        f = {v: np.isfinite(df[f"r_{v}"].to_numpy(np.float64)[m]) for v in ("T", "Td", "u", "v", "p")}
        ligeras[c] = pd.DataFrame({"valido_T": f["T"], "valido_Td": f["Td"], "valido_HR": f["T"] & f["Td"],
                                   "valido_viento": f["u"] & f["v"], "valido_p": f["p"]})
    return orquestacion._horas_validas_total(ligeras, datos.estaciones)


def _red_de_escenario(red: _Red, desde: int, hasta: int, fraccion: float) -> frozenset[str]:
    """Las estaciones cuyo período cubre al menos ``fraccion`` de los años [desde, hasta] (COS-5: la regla real la
    decide la red; aquí sólo hace falta una red distinta de «todas»)."""
    a = _h_de_fecha(f"{desde:04d}-01-01")
    b = _h_de_fecha(f"{hasta + 1:04d}-01-01")
    salida = {c for c, (p0, p1) in red.periodos.items() if max(0, min(p1, b) - max(p0, a)) >= fraccion * (b - a)}
    if len(salida) < 2:
        salida = set(sorted(red.periodos)[::2])
    return frozenset(salida)


def _escenarios(red: _Red, variables) -> dict:
    desde, hasta = constantes.valor("TF1_RED_HISTORICA")[1:]
    _, _, _, r0, r1 = constantes.valor("TF2_RED_R2000_2025")
    historica = _red_de_escenario(red, desde, hasta, 0.1)                  # no-umbral: COS-5
    constante = _red_de_escenario(red, r0, r1, 0.5) - frozenset([min(red.periodos)])   # no-umbral: COS-5
    return {v: tendencias.EscenariosTF(variable=v, historica=historica, constante=constante,
                                       regla=tipos.ReglaRedConstante.R2000_2025.value) for v in variables}


def _redes_del_anio(escenarios: Mapping, anio: int) -> int:
    """k: cuántas redes distintas piden los escenarios de un año (TEN-4; COS-8)."""
    e = next(iter(escenarios.values()))
    return len({e.red(x, anio) for x in tendencias.ESCENARIOS if anio in e.anios(x)})


def _configuraciones(pasada: str, U) -> tuple[dict, tuple]:
    """Las configuraciones de producción de una pasada de TF (ORQ-13, TEN-12) y sus variables."""
    if pasada == "ambiental":
        cands, pvs, variables = ("A", "B", "AB", "C"), ("T", "Td", "u", "v", "p"), tendencias.VARIABLES_TF
    else:
        cands, pvs, variables = ("A", "B", "AB", "C", "C_est"), ("T", "Td"), ("T", "Td")
    return {c: {orquestacion.ETIQUETA_PRODUCCION: {pv: _theta(c, U, pv) for pv in pvs}} for c in cands}, \
        tuple(variables)


def _e0(pasada: str) -> list:
    pares = [(u, g) for u, g in orquestacion.PARES if (u == Uso.AMBIENTAL.value) == (pasada == "ambiental")]
    return [(u, g, c.value) for u, g in pares for c in producto.CANDIDATOS_DEL_USO[Uso(u)]]


def _medir_tf(ctx) -> dict:
    """Punto 3: las dos pasadas de TF en los meses de la escala, con la unidad real de M3-4
    (``orquestacion._unidad_mes_tf``, con la finitud de E0) y la pasada armada en memoria (COS-8, COS-17)."""
    U, escala = ctx["U"], ctx["escala"]
    red = _red(U, escala)
    mundo = _datos(U, red, variante="ligera", c_est=True, n_celdas=escala.celdas_grilla)      # COS-24 (ORQ-44)
    datos, t_datos, bytes_ = mundo.datos, mundo.tiempos, mundo.bytes
    rss_fabricado = _rss_gb()                          # la ligera armada: lo que guarda también el principal
    celdas = _celdas(ctx, escala.celdas_tf, pobladas=True, semilla="tf")
    cat, z_tabla, validos = _pixeles(celdas["lat"], celdas["lon"])
    est = _estaticos(celdas["celda"], celdas["lat"], celdas["lon"], celdas["z_media"], celdas["z_poblada"],
                     celdas["cod_comuna"], np.random.default_rng(int(U.a("SEMILLA"))))
    carpeta = sintetico.destino_temporal(Path(ctx["temporal"]) / "tf")
    meses = {}
    with _Reloj() as t_fab:
        for m in sorted(escala.meses_tf):
            campos, tiempos, _ = _campos_mes(cat, z_tabla, m)
            ruta = sintetico.mes_era5_netcdf(carpeta / f"mes_{m}.nc", campos, tiempos, cat["pixel_id"].to_numpy())
            with open(ruta, "rb") as f:
                meses[m] = (str(ruta), hashlib.sha256(f.read()).hexdigest())
    h_ultima = int(max(_horas_mes(m)[-1] for m in escala.meses_tf))
    salida: dict = {"celdas": int(len(celdas)), "pixeles": int(len(cat)), "fabricar_meses_s": t_fab.pared,
                    "pasadas": {}, "bytes": bytes_, "horas_dato": t_datos["horas_dato"],
                    "estaciones": len(datos.estaciones), "memoria_tras_fabricar_gb": rss_fabricado}
    for pasada in PASADAS:
        configuraciones, variables = _configuraciones(pasada, U)
        escenarios = _escenarios(red, variables)
        z_col = "z_media" if pasada == "ambiental" else "z_poblada"
        with _Reloj() as t_arm:
            op = fondo_era5l.operador(celdas["lat"].to_numpy(np.float64), celdas["lon"].to_numpy(np.float64),
                                      celdas[z_col].to_numpy(np.float64), cat, validos, z_tabla, U,
                                      ids=celdas["celda"].to_numpy(np.int64))
            clima = _clima_estado(celdas["lat"].to_numpy(np.float64), celdas[z_col].to_numpy(np.float64)) \
                if pasada == "salud" else None
            tabla = celdas[["celda", "lat", "lon", "cod_comuna", "w_ghs"]]
            ctf = tendencias.celdas_tf(tabla, celdas[z_col].to_numpy(np.float64), estaticos=est, clima_estado=clima)
            pasada_tf = tendencias.PasadaTF(datos, ctf, escenarios, configuraciones, U, variables=variables)
        clave = f"costo/{pasada}"
        e0 = _e0(pasada)
        orquestacion._PASADAS.clear()
        orquestacion._PASADAS[clave] = (pasada_tf, op, None)
        ctx_tf = {"U": U, "clave_pasada": clave, "args_pasada": None, "h_ultima": h_ultima, "e0": e0}
        filas = []
        try:
            for m in escala.meses_tf:
                ruta, sha = meses[m]
                with _Reloj() as t:
                    r = orquestacion._unidad_mes_tf({"mes": m, "ruta": ruta, "sha256": sha, "tf": True}, ctx_tf)
                filas.append({"mes": m, "horas": int(_horas_mes(m).size),
                              "redes": _redes_del_anio(escenarios, _anio(m)),
                              "finitud_e0": len(r.get("finitud", {})), **t.dict()})
        finally:
            orquestacion._PASADAS.clear()
        e = next(iter(escenarios.values()))
        salida["pasadas"][pasada] = {"armar": t_arm.dict(), "meses": filas, "configuraciones": len(configuraciones),
                                     "variables": list(variables), "e0": len(e0),
                                     "redes": {"historica": len(e.historica), "constante": len(e.constante),
                                               "entrenamiento": len(datos.estaciones), "regla": e.regla}}
        if pasada == "salud":
            salida["c_en_celdas"] = _c_en_celdas(pasada_tf, op, meses[escala.meses_tf[0]], U)
        del pasada_tf, op, clima, ctf
    bytes_["cache_series"] = _bytes_cache(datos)
    return salida


def _c_en_celdas(pasada_tf, op, mes_ruta, U) -> dict:
    """C y C_est en las celdas (CAN-18, TEN-14; pendiente de I21 de las olas 4 y 5): ``PasadaTF.correccion_mes`` de T
    en un mes y todas las celdas, menos lo que cuesta su fondo, en ms por celda-mes."""
    ruta, sha = mes_ruta
    mes = fondo_era5l.leer_mes(Path(ruta), sha256=sha)
    h = np.asarray(mes.tiempos, dtype=np.int64)

    def campos(hh, idx):
        F = fondo_era5l.campos_fondo(mes, orquestacion._sub_operador(op, idx), U)
        return {c: np.asarray(F[c], dtype=np.float64) for c in fondo_era5l.CAMPOS_F}
    n = int(pasada_tf.celdas.n)
    with _Reloj() as t_campos:
        for sl in pasada_tf.lotes:
            campos(h, np.arange(sl.start, sl.stop))
    salida = {"celdas": n, "horas": int(h.size), "campos": t_campos.dict()}
    for cand in (Candidato.C.value, Candidato.C_EST.value):
        with _Reloj() as t:
            pasada_tf.correccion_mes(h, campos, cand, orquestacion.ETIQUETA_PRODUCCION, "T")
        neto = max(0.0, t.pared - t_campos.pared)
        salida[cand] = {**t.dict(), "ms_por_celda_mes": neto * _MS / max(n, 1)}
    return salida


# --- el peor ganador, grupo por grupo y candidato por candidato (COS-5; H6) ---
def _barrido(uso) -> dict[str, dict[str, str]]:
    """Las configuraciones que se miden para un uso: «base» (A en todos los grupos) y, para cada grupo y cada otro
    candidato del uso, ese grupo con ese candidato y los demás con A; con un solo grupo, cada candidato."""
    uso = Uso(uso)
    grupos = [g.value for g in producto.GRUPOS_DEL_USO[uso]]
    otros = [c.value for c in producto.CANDIDATOS_DEL_USO[uso] if c is not Candidato.A]
    base = {g: Candidato.A.value for g in grupos}
    salida = {BASE: base}
    for g in grupos:
        for c in otros:
            salida[f"{g}={c}"] = {**base, g: c}
    return salida


def peor_configuracion(tiempos: Mapping[str, float]) -> dict:
    """La cota del peor ganador (COS-5): t(base) + Σ_g máx_c máx(0, t(g=c) − t(base)), y el candidato de cada grupo.
    Si C gana en más de un grupo, el diseño de C (común a sus grupos) se cuenta en cada uno: es una cota superior."""
    base = float(tiempos[BASE])
    por_grupo: dict[str, tuple[str, float]] = {}
    for nombre, t in tiempos.items():
        if nombre == BASE:
            continue
        g, c = nombre.split("=")
        d = float(t) - base
        if g not in por_grupo or d > por_grupo[g][1]:
            por_grupo[g] = (c, d)
    ganador = {g: (c if d > 0 else Candidato.A.value) for g, (c, d) in por_grupo.items()}
    return {"pared_s": base + sum(max(0.0, d) for _, d in por_grupo.values()), "ganador": ganador}


def _medir_m5(ctx) -> dict:
    """Punto 4: un mes de M5 (ORQ-23 a ORQ-27): el 0,1° en los píxeles (``producto.producto_mes`` y ``mes_01deg``) y
    los productos de salud en las celdas pobladas por lotes de ``LOTE_CELDAS_SALUD``, cada uno con su agregación
    comunal (``salud.AcumuladorMeteo.agregar``), para cada configuración del barrido (COS-5); la lluvia comunal del mes
    (``salud.pesos_lluvia`` y ``lluvia_comunal``) y el operador de salud de un trabajador sobre todas las celdas con
    ``cod_comuna`` > 0 (``orquestacion._salud_de``; COS-19)."""
    U, escala = ctx["U"], ctx["escala"]
    red = _red(U, escala)
    mundo = _datos(U, red, variante="ligera", c_est=True, n_celdas=escala.celdas_grilla)      # COS-24 (ORQ-42)
    datos, t_datos, bytes_ = mundo.datos, mundo.tiempos, mundo.bytes
    celdas = _celdas(ctx, escala.celdas_salud, pobladas=True, semilla="salud")
    cat, z_tabla, validos = _pixeles(celdas["lat"], celdas["lon"])
    mes = _mes_en_memoria(cat, z_tabla, escala.mes_m5)
    h = np.asarray(mes.tiempos, dtype=np.int64)
    rng = np.random.default_rng(int(U.a("SEMILLA")))
    op_pix = fondo_era5l.operador_pixeles(validos, cat, validos, z_tabla)
    pun_pix = {"ids": np.asarray(op_pix.ids), "lat": cat["latitude"].to_numpy(np.float64),
               "lon": cat["longitude"].to_numpy(np.float64), "z": np.asarray(op_pix.z, dtype=np.float64)}
    est_pix = _estaticos(validos, pun_pix["lat"], pun_pix["lon"], pun_pix["z"], pun_pix["z"],
                         np.ones(validos.size, dtype=np.int32), rng)
    est_sal = _estaticos(celdas["celda"], celdas["lat"], celdas["lon"], celdas["z_media"], celdas["z_poblada"],
                         celdas["cod_comuna"], rng)
    op_sal = fondo_era5l.operador(celdas["lat"].to_numpy(np.float64), celdas["lon"].to_numpy(np.float64),
                                  celdas["z_poblada"].to_numpy(np.float64), cat, validos, z_tabla, U,
                                  ids=celdas["celda"].to_numpy(np.int64))
    clima_pix = _tabla_clima(cat, z_tabla)
    lote = int(orquestacion.LOTE_CELDAS_SALUD)
    anio = _anio(escala.mes_m5)
    pesos = pd.DataFrame({"celda": celdas["celda"].to_numpy(np.int64), "anio": anio,
                          "w_ghs": celdas["w_ghs"].to_numpy(np.float64)})
    pc = salud.pesos_comuna(anio, celdas[["celda", "cod_comuna"]], pesos)
    pedidos = salud.dias_del_anio(h, anio)
    tipos_dia = {Uso.AGUDO.value: salud.TIPOS_DIA, Uso.CRONICO.value: (salud.TIPOS_DIA[0],)}   # §7.2, punto 3; §7.3
    salida: dict = {"pixeles": int(validos.size), "celdas_salud": int(len(celdas)), "horas": int(h.size),
                    "comunas": int(pc.comunas.size), "bytes": bytes_, "horas_dato": t_datos["horas_dato"],
                    "estaciones": len(datos.estaciones),
                    "pixeles_producto": {}, "salud": {}}
    nc = None
    for nombre, g_amb in _barrido(Uso.AMBIENTAL).items():
        con_c = Candidato.C.value in g_amb.values()
        with _Reloj() as t_prod:
            campos, _ = producto.producto_mes(mes, op_pix, pun_pix, g_amb, _hiper_de(g_amb, U), datos, umbrales=U,
                                              uso=Uso.AMBIENTAL.value, estaticos=est_pix if con_c else None,
                                              celdas=validos if con_c else None)
        salida["pixeles_producto"][nombre] = t_prod.dict()
        if nc is None:
            with _Reloj() as t_nc:
                nc = producto.mes_01deg(campos, validos, h, U, {"ERA5L/mes.nc": "0" * 64}, uso=Uso.AMBIENTAL.value,
                                        ganador=g_amb)
            salida["pixeles_netcdf"], salida["bytes_netcdf"] = t_nc.dict(), len(nc)
        del campos
    for uso in (Uso.AGUDO.value, Uso.CRONICO.value):
        salida["salud"][uso] = {}
        for nombre, g in _barrido(uso).items():
            acumulador = salud.AcumuladorMeteo(pc, h, tipos_dia[uso], dias=pedidos)
            t_agr = 0.0
            with _Reloj() as t:
                for i0 in range(0, len(celdas), lote):
                    idx = np.arange(i0, min(len(celdas), i0 + lote))
                    op_l = orquestacion._sub_operador(op_sal, idx)
                    puntos = {"ids": np.asarray(op_l.ids), "lat": celdas["lat"].to_numpy(np.float64)[idx],
                              "lon": celdas["lon"].to_numpy(np.float64)[idx], "z": np.asarray(op_l.z, np.float64)}
                    e = est_sal.iloc[idx].reset_index(drop=True)
                    e.attrs = dict(est_sal.attrs)
                    campos_l, _ = producto.producto_mes(mes, op_l, puntos, g, _hiper_de(g, U), datos, umbrales=U,
                                                        uso=uso, estaticos=e, clima_estado=clima_pix)
                    t0 = time.perf_counter()
                    acumulador.agregar({k: campos_l[k] for k in salud.CAMPOS}, op_l.ids, horas=h)
                    t_agr += time.perf_counter() - t0
            salida["salud"][uso][nombre] = {**t.dict(), "agregacion_s": t_agr}
    salida["lluvia"] = _lluvia(celdas, cat, mes, pesos, anio, h, pedidos)
    salida["operador_salud"] = _operador_salud(ctx, cat, validos, z_tabla, U)
    bytes_["cache_series"] = _bytes_cache(datos)
    return salida


def _lluvia(celdas, cat, mes, pesos, anio: int, h, pedidos) -> dict:
    """La lluvia comunal del mes en sus tres tipos de día (SAL-7, MC-13), con el enlace de cada celda al píxel que la
    contiene (sintético)."""
    res = float(sintetico.RESOLUCION_ERA5L)
    columnas_lon = int(round(_GEO["vuelta"] / res))
    i = np.floor((_GEO["polo"] - celdas["lat"].to_numpy(np.float64)) / res + 1 / 2).astype(np.int64)
    j = np.floor(np.mod(celdas["lon"].to_numpy(np.float64), _GEO["vuelta"]) / res + 1 / 2).astype(np.int64) \
        % columnas_lon
    enlaces = pd.DataFrame({"celda": celdas["celda"].to_numpy(np.int64), "era5land_pixel": i * columnas_lon + j})
    with _Reloj() as t:
        pl = salud.pesos_lluvia(anio, celdas[["celda", "cod_comuna"]], enlaces, pesos)
        col = pd.Index(np.asarray(mes.pixel_id, dtype=np.int64)).get_indexer(pl.pixeles)
        tp = np.asarray(mes.datos["tp"])[:, col]
        for tipo in salud.TIPOS_DIA:
            salud.lluvia_comunal(h, tp, pl.pixeles, pl, tipo, dias=pedidos)
    return {**t.dict(), "horas": int(np.asarray(h).size)}


def _operador_salud(ctx, cat, validos, z_tabla, U) -> dict:
    """El operador de salud de un trabajador de M5 (``orquestacion._salud_de``): todas las celdas con ``cod_comuna``
    > 0 de la geometría (las de ``celdas.parquet`` con ``real_era5``), su tiempo y sus bytes, y los de sus estáticos."""
    base = _leer_celdas_reales(ctx["rutas"]) if ctx["real_era5"] else _celdas_sinteticas(ctx["escala"].celdas_grilla,
                                                                                         ctx["escala"])
    t = base[base["cod_comuna"].to_numpy(np.int64) > 0].sort_values("celda").reset_index(drop=True)
    lat, lon = t["lat"].to_numpy(np.float64), t["lon"].to_numpy(np.float64)
    cat_t, z_t, validos_t = _pixeles(lat, lon)
    with _Reloj() as r:
        op = fondo_era5l.operador(lat, lon, _z(lat, lon), cat_t, validos_t, z_t, U, ids=t["celda"].to_numpy(np.int64))
    return {**r.dict(), "celdas": int(len(t)), "bytes": _bytes_obj(op),
            "estaticos_bytes": int(len(t)) * _bytes_por_fila(tipos.ESQUEMA_ESTATICAS_CELDA_C),
            "real": bool(ctx["real_era5"])}


def _tabla_clima(cat, z_tabla) -> pd.DataFrame:
    """``tipos.ESQUEMA_CLIMA_ESTADO`` sintético de los píxeles (para C_est, PRO-7)."""
    clima = _clima_estado(cat["latitude"].to_numpy(np.float64), z_tabla["z_e5l"].to_numpy(np.float64))
    n = len(cat)
    tabla = {"pixel_id": np.repeat(cat["pixel_id"].to_numpy(np.int64), 12 * 24),
             "mes": np.tile(np.repeat(np.arange(1, 13), 24), n), "hora": np.tile(np.arange(24), 12 * n)}
    for v in tipos.VARIABLES_CLIMA_ESTADO:
        tabla[v] = clima[v].reshape(-1)
    return pd.DataFrame(tabla).astype(dict(tipos.ESQUEMA_CLIMA_ESTADO))


def _decision_de(ganador: Mapping[str, str], U) -> tuple[dict, str]:
    """El contenido mínimo de ``decision.json`` que lee ``ambiental`` (AMB-7) con un ganador por grupo, y su sha256."""
    decisiones = []
    for g, c in ganador.items():
        hip = {v: ambiental._theta_json(_theta(c, U, v)) for v in producto.VARIABLES_DE_GRUPO[Grupo(g)]}
        decisiones.append({"uso": Uso.AMBIENTAL.value, "grupo": g, "ganador": c, "hiperparametros": {c: hip}})
    contenido = {"esquema": tipos.VERSION_DECISION, "decisiones": decisiones}
    return contenido, entorno.sha256_bytes(entorno.json_canonico(contenido))


def _medir_grilla(ctx) -> dict:
    """Punto 5: el operador de la grilla (P109, MC-15) con AB en todos los grupos (8 juegos de núcleo, su tamaño mayor;
    lo arma el principal de M5) y, para cada configuración del barrido (COS-5), su operador y un mes de
    ``ambiental.mc_bloque`` con I y con D en los lotes de la muestra (COS-14)."""
    U, escala = ctx["U"], ctx["escala"]
    red = _red(U, escala)
    mundo = _datos(U, red, variante="ligera", c_est=False, n_celdas=escala.celdas_grilla)     # COS-24 (ORQ-42)
    datos, t_datos, bytes_ = mundo.datos, mundo.tiempos, mundo.bytes
    celdas = _celdas(ctx, escala.celdas_grilla, pobladas=False, semilla="grilla")
    cat, z_tabla, validos = _pixeles(celdas["lat"], celdas["lon"])
    mes = _mes_en_memoria(cat, z_tabla, escala.mes_m5)
    meses = {int(escala.mes_m5): mes}
    h = np.asarray(mes.tiempos, dtype=np.int64)
    est = _estaticos(celdas["celda"], celdas["lat"], celdas["lon"], celdas["z_media"], celdas["z_poblada"],
                     np.maximum(celdas["cod_comuna"].to_numpy(np.int64), 1), np.random.default_rng(int(U.a("SEMILLA"))))
    ids = celdas["celda"].to_numpy(np.int64)
    lote = int(escala.lote_grilla)
    inicios = list(range(0, ids.size, lote))
    if escala.lotes_grilla is not None and int(escala.lotes_grilla) < len(inicios):    # COS-14: repartidos
        elegidos = np.unique(np.linspace(0, len(inicios) - 1, int(escala.lotes_grilla)).round().astype(np.int64))
        inicios = [inicios[i] for i in elegidos]
    medidas = int(sum(min(ids.size, i0 + lote) - i0 for i0 in inicios))
    salida: dict = {"celdas": int(ids.size), "celdas_medidas": medidas, "horas": int(h.size), "lote": lote,
                    "pixeles": int(len(cat)), "configuraciones": {}, "bytes": bytes_,
                    "horas_dato": t_datos["horas_dato"], "estaciones": len(datos.estaciones)}

    def operador(ganador):
        decision, sha = _decision_de(ganador, U)
        return ambiental.operador_grilla(decision, celdas=celdas[["celda", "lat", "lon"]], estaciones=datos.estaciones,
                                         catalogo=cat, z_celdas=celdas[["celda", "z_media"]], validos=validos,
                                         z_pix=z_tabla, umbrales=U, decision_sha256=sha)
    with _Reloj() as t_op:
        op = operador({g.value: Candidato.AB.value for g in producto.GRUPOS_DEL_USO[Uso.AMBIENTAL]})
    salida["operador_mayor"] = {**t_op.dict(), "bytes": int(op.tamano_bytes)}
    del op
    for nombre, ganador in _barrido(Uso.AMBIENTAL).items():
        with _Reloj() as t_op:
            op = operador(ganador)
        con_c = Candidato.C.value in op.ganador.values()
        por_variante = {}
        for var in VARIANTES:
            with _Reloj() as t:
                for i0 in inicios:
                    ambiental.mc_bloque(ids[i0:i0 + lote], h, var, operador=op, meses=meses, datos=datos, umbrales=U,
                                        estaticos=est if con_c else None)
            por_variante[var] = t.dict()
        salida["configuraciones"][nombre] = {"operador": t_op.dict(), "operador_bytes": int(op.tamano_bytes),
                                             "variantes": por_variante}
        del op
    bytes_["cache_series"] = _bytes_cache(datos)
    return salida


def _medir_mes_real(ctx) -> dict:
    """Punto 6 (COS-10): la huella con ``open`` de Python y la lectura del mes real, en sólo lectura."""
    if not ctx["real_era5"]:
        return {"estado": SIN_MEDIR, "motivo": "sin real_era5: no se abre nada real (COS-10)"}
    ruta = ruta_mes_real(ctx["rutas"])
    with _Reloj() as t_h:
        with open(ruta, "rb") as f:
            datos = f.read()
        sha = hashlib.sha256(datos).hexdigest()
    n_bytes = len(datos)
    del datos
    with _Reloj() as t_l:
        mes = fondo_era5l.leer_mes(ruta, sha256=sha)
        fondo_era5l.comprobar_unidades(mes)
    return {"bytes": n_bytes, "pixeles": int(np.asarray(mes.pixel_id).size), "horas": int(np.asarray(mes.tiempos).size),
            "huella": t_h.dict(), "lectura": t_l.dict(),
            "huellas_lecturas_reales": {entorno.alias(ruta, ctx["rutas"]): {"sha256": sha, "bytes": n_bytes}}}


def _medir_contencion(ctx) -> dict:
    """La unidad del factor de contención (COS-20): un lote de celdas de un mes de TF (``PasadaTF.sumas_mes``),
    repetido ``_REPETICIONES`` veces, en un trabajador; ``medir`` la corre sola y en P copias a la vez."""
    U, escala = ctx["U"], ctx["escala"]
    red = _red(U, escala)
    datos = _datos(U, red, variante="ligera", c_est=False, n_celdas=escala.estaciones,
                   ventanas=_ventanas_de_meses([escala.mes_m5])).datos             # COS-20: un mundo chico
    n = min(int(escala.celdas_tf), int(tendencias.LOTE_PUNTOS_TF))
    celdas = _celdas(ctx, n, pobladas=True, semilla="contencion")
    cat, z_tabla, validos = _pixeles(celdas["lat"], celdas["lon"])
    mes = _mes_en_memoria(cat, z_tabla, escala.mes_m5)
    h = np.asarray(mes.tiempos, dtype=np.int64)
    op = fondo_era5l.operador(celdas["lat"].to_numpy(np.float64), celdas["lon"].to_numpy(np.float64),
                              celdas["z_media"].to_numpy(np.float64), cat, validos, z_tabla, U,
                              ids=celdas["celda"].to_numpy(np.int64))
    est = _estaticos(celdas["celda"], celdas["lat"], celdas["lon"], celdas["z_media"], celdas["z_poblada"],
                     celdas["cod_comuna"], np.random.default_rng(int(U.a("SEMILLA"))))
    configuraciones, variables = _configuraciones("ambiental", U)
    configuraciones = {c: v for c, v in configuraciones.items() if c != Candidato.C_EST.value}
    ctf = tendencias.celdas_tf(celdas[["celda", "lat", "lon", "cod_comuna", "w_ghs"]],
                               celdas["z_media"].to_numpy(np.float64), estaticos=est)
    pasada = tendencias.PasadaTF(datos, ctf, _escenarios(red, variables), configuraciones, U, variables=variables)

    def campos(hh, idx):
        F = fondo_era5l.campos_fondo(mes, orquestacion._sub_operador(op, idx), U)
        return {c: np.asarray(F[c], dtype=np.float64) for c in fondo_era5l.CAMPOS_F}
    tiempos = []
    for _ in range(_REPETICIONES):
        with _Reloj() as t:
            pasada.sumas_mes(h, campos)
        tiempos.append(t.pared)
    return {"celdas": int(n), "horas": int(h.size), "repeticiones_s": tiempos}


def ruta_mes_real(rutas) -> Path:
    """COS-10: ``ERA5L/mensual/era5land_202401_chile_pixeles.nc``."""
    return Path(rutas.era5l) / CARPETA_MENSUAL / f"era5land_{MES_REAL}_chile_pixeles.nc"


_MEDIDORES: dict[str, Callable] = {"qc": _medir_qc, "pliegue": _medir_pliegue, "tf": _medir_tf, "m5": _medir_m5,
                                   "grilla": _medir_grilla, "mes_real": _medir_mes_real,
                                   "contencion": _medir_contencion}


def _vigiladas(rutas) -> tuple:
    """COS-21: las raíces de datos reales que cada punto vigila en bloqueo: /Volumes, DATOS, LOCAL, la auditoría de APH
    y la configuración de AP (la publicación del reloj), las de ``rutas`` y las reales."""
    reales = entorno.rutas_reales()
    salida = ["/" + "Volumes"]
    for r in (rutas, reales):
        salida += [str(Path(r.datos)), str(Path(r.local)), str(Path(r.aph) / "auditoria"), str(Path(r.ap) / "config")]
    return tuple(dict.fromkeys(salida))


def _permitidas(ctx) -> tuple:
    """COS-21: con ``real_era5``, sólo ``GRILLA/celdas.parquet`` y el mes real; si no, nada."""
    if not ctx["real_era5"]:
        return ()
    rutas = ctx["rutas"]
    return (str(Path(rutas.grilla) / "celdas.parquet"), str(ruta_mes_real(rutas)))


def _procedencia_lecturas(nombre: str, resultado: Mapping, eventos, ctx: Mapping) -> list[str]:
    """Nombres neutros sólo para accesos registrados y permitidos; la identidad del mes queda en huellas."""
    normalizar = lambda p: os.path.normpath(os.path.abspath(os.fspath(p)))    # noqa: E731
    abiertas = {normalizar(p) for e, p in eventos if e == "open"}
    permitidas = {normalizar(p) for p in _permitidas(ctx)}
    if abiertas - permitidas:
        raise ErrorCosto("el punto registró una lectura fuera de los dos insumos permitidos (COS-21)")
    mes = ruta_mes_real(ctx["rutas"])
    mes_abierto = normalizar(mes) in abiertas
    huellas = resultado.get("huellas_lecturas_reales")
    if mes_abierto:
        if nombre != "mes_real" or abiertas != {normalizar(mes)}:
            raise ErrorCosto("la lectura del mes sólo corresponde al punto mes_real (COS-10)")
        alias = entorno.alias(mes, ctx["rutas"])
        if not isinstance(huellas, Mapping) or set(huellas) != {alias}:
            raise ErrorCosto("la lectura del mes exige su ruta por alias y su huella medida")
        ceguera.vigilar_salida("costo_m1.json", {"huellas_lecturas_reales": huellas}, clase="resumen")
        evidencia = huellas[alias]
        if (not isinstance(evidencia, Mapping) or set(evidencia) != {"sha256", "bytes"}
                or isinstance(resultado.get("bytes"), bool) or not isinstance(resultado.get("bytes"), int)
                or evidencia["bytes"] != resultado["bytes"]):
            raise ErrorCosto("la huella del mes exige el tamaño efectivamente medido")
    elif huellas is not None or (nombre == "mes_real" and ctx["real_era5"]):
        raise ErrorCosto("la procedencia del mes requiere un evento de apertura registrado")
    return sorted("mes_real" if p == normalizar(mes) else Path(p).name for p in abiertas)


def _punto(unidad: Mapping, ctx: Mapping) -> dict:
    """La unidad de ``orquestacion.repartir``: un punto en su trabajador (COS-3), bajo su propio
    ``ceguera.RegistroAccesos`` en bloqueo (COS-21); la vacía no hace nada."""
    nombre = unidad["punto"]
    if nombre is None:
        return {}
    inicio = _rss_gb()
    with ceguera.RegistroAccesos(_vigiladas(ctx["rutas"]), bloquear=True, permitidas=_permitidas(ctx)) as reg:
        with _Reloj() as t:
            r = _MEDIDORES[nombre](ctx)
    lecturas = _procedencia_lecturas(nombre, r, reg.lecturas_permitidas, ctx)
    return {**r, "total": t.dict(), "memoria_inicio_gb": inicio, "memoria_pico_gb": _rss_gb(), "pid": os.getpid(),
            "lecturas_reales": lecturas}


# ---------------------------------------------------------------------------
# medir (COS-3, COS-13, COS-20 a COS-22)
# ---------------------------------------------------------------------------
def fallas_escala(escala: Escala) -> list[str]:
    """En qué se aparta una escala de la de §8.1 del diseño (COS-22): vacía si es la de §8.1. Se juzga por los tamaños,
    no por el nombre."""
    fallas = []
    esperado = {"estaciones": CONTEOS["estaciones"], "horas": CONTEOS["horas"],
                "desde": str(constantes.valor("PRODUCTO_DESDE")), "cobertura": None,
                "celdas_tf": CONTEOS["celdas_pobladas"], "celdas_salud": CONTEOS["celdas_pobladas"],
                "celdas_grilla": CONTEOS["celdas"]}
    for k, v in esperado.items():
        if getattr(escala, k) != v:
            fallas.append(f"{k}: {getattr(escala, k)!r} en vez de {v!r}")
    if escala.artefactos < _ARTEFACTOS_MIN or not 1 <= escala.qc_meses <= 12:
        fallas.append(f"≥ {_ARTEFACTOS_MIN} artefactos de un año: {escala.qc_estaciones} × {escala.qc_meses}")
    if len(set(escala.meses_tf)) != 12 or len(escala.meses_tf) != 12:
        fallas.append("un año de TF: 12 meses distintos (COS-8)")
    if len({_redes_reales(_anio(m)) for m in escala.meses_tf}) < 2:
        fallas.append("la TF necesita meses con 2 y con 3 redes (COS-8)")
    if len(str(escala.mes_m5)) != 6:                                       # no-umbral: AAAAMM
        fallas.append("un mes de M5 y de la grilla (AAAAMM)")
    return fallas


def _redes_reales(anio: int) -> int:
    return _k_reales(tipos.ReglaRedConstante.R2000_2025.value).get(int(anio), 0)


def _carga_libre(cargas) -> bool:
    """COS-13: libre si toda lectura es finita y menor que ``COSTO_CARGA_MAX`` (una NaN no es libre)."""
    tope = float(constantes.valor("COSTO_CARGA_MAX"))
    cargas = list(cargas)
    return bool(cargas) and all(math.isfinite(c) and c < tope for c in cargas)


def carga_ajena(bruta: float, propios: int) -> float:
    """COS-13: la carga ajena a la medición: la bruta menos los procesos de la medición que corren, sin bajar de 0
    (NaN si la bruta no es finita)."""
    bruta = float(bruta)
    return max(0.0, bruta - int(propios)) if math.isfinite(bruta) else math.nan


class _Muestreo:
    """La carga bruta y la ajena cada ``_INTERVALO_CARGA_S`` segundos mientras corre un punto (COS-13), en un hilo de
    este proceso. ``propios``: los procesos de la medición que corren mientras tanto."""

    def __init__(self, propios: int = 1):
        self.propios = int(propios)

    def __enter__(self):
        import threading
        self.cargas = [_carga()]
        self._fin = threading.Event()
        self._hilo = threading.Thread(target=self._bucle, daemon=True)
        self._hilo.start()
        return self

    def _bucle(self):
        while not self._fin.wait(_INTERVALO_CARGA_S):
            self.cargas.append(_carga())

    def __exit__(self, *exc):
        self._fin.set()
        self._hilo.join()
        self.cargas.append(_carga())
        return False

    def ajenas(self) -> list[float]:
        return [carga_ajena(c, self.propios) for c in self.cargas]

    def resumen(self) -> dict:
        return resumen_carga(self.cargas, self.propios)


def resumen_carga(brutas, propios: int) -> dict:
    """COS-13: las dos series de un punto (bruta y ajena), sus máximos y si fue libre (toda ajena finita y < 2)."""
    brutas = [float(c) for c in brutas]
    ajenas = [carga_ajena(c, propios) for c in brutas]
    fin_b = [c for c in brutas if math.isfinite(c)]
    fin_a = [c for c in ajenas if math.isfinite(c)]
    return {"lecturas": len(brutas), "propios": int(propios), "bruta": brutas, "ajena": ajenas,
            "maxima_bruta": max(fin_b) if fin_b else None, "maxima_ajena": max(fin_a) if fin_a else None,
            "no_finitas": len(brutas) - len(fin_b), "libre": _carga_libre(ajenas)}


def memoria_fisica() -> int:
    """Los bytes de memoria física de la máquina (``os.sysconf``; no lee datos)."""
    try:
        return int(os.sysconf("SC_PAGE_SIZE")) * int(os.sysconf("SC_PHYS_PAGES"))
    except (ValueError, OSError):
        return 0


def _contencion(ctx, procesos: int, permitidas) -> dict:
    """COS-20: la misma unidad sola (en un trabajador) y en ``procesos`` copias a la vez; el factor es la mediana de las
    copias (sin su primera repetición) sobre la sola."""
    solo = orquestacion.repartir([{"punto": "contencion"}, {"punto": None}], _punto, 2, contexto=ctx,
                                 permitidas=permitidas)[0]
    copias = orquestacion.repartir([{"punto": "contencion"}] * procesos, _punto, procesos, contexto=ctx,
                                   permitidas=permitidas)
    t_solo = float(np.median(solo["repeticiones_s"][1:] or solo["repeticiones_s"]))
    t_copias = [float(np.median(c["repeticiones_s"][1:] or c["repeticiones_s"])) for c in copias]
    return {"procesos": int(procesos), "solo_s": t_solo, "copias_s": t_copias,
            "factor": max(1.0, float(np.median(t_copias)) / t_solo) if t_solo > 0 else math.nan,
            "memoria_pico_gb": max(c["memoria_pico_gb"] for c in copias), "celdas": solo["celdas"]}


def medir(rutas, *, real_era5: bool, umbrales, temporal=None, escala: Escala = ESCALA_REAL, aislar: bool = True,
          puntos: Sequence[str] = PUNTOS, procesos: int = int(constantes.valor("PROCESOS"))) -> dict:
    """Los puntos de §8.1 del diseño y el factor de contención (COS-3 a COS-22). ``rutas``: ``entorno.Rutas`` (las
    reales con ``real_era5``); ``temporal``: una carpeta bajo ``tempfile.gettempdir()`` donde ``sintetico`` escribe lo
    que haga falta; sin ella, ``medir`` usa una propia de ``entorno.carpeta_de_trabajo``, que se borra al terminar,
    también con un error (COS-23; si quien llama vigila AP o APH, el directorio actual debe estar en la temporal del
    sistema, ENT-9).
    ``escala``: ``ESCALA_REAL`` (§8.1; horas) o una chica. ``aislar``: cada punto en su trabajador (False: en este
    proceso, sin memoria propia ni contención). Devuelve las mediciones (dict, en memoria)."""
    if not isinstance(real_era5, bool):
        raise ErrorCosto("real_era5 es True o False")
    desconocidos = [p for p in puntos if p not in PUNTOS]
    if desconocidos:
        raise ErrorCosto(f"puntos desconocidos {desconocidos}; son {PUNTOS}")
    if isinstance(procesos, bool) or not isinstance(procesos, int) or procesos < 1:
        raise ErrorCosto("procesos: un entero ≥ 1")
    a_escala = not fallas_escala(escala)
    if a_escala and not real_era5:
        raise ErrorCosto("la medición de §8.1 lee un mes real y la geometría de la grilla: exige real_era5=True "
                         "(COS-10, COS-22)")
    carga0 = _carga()
    if a_escala and not _carga_libre([carga0]):
        raise ErrorCosto(f"la máquina no está libre: carga {carga0:.2f} (tope {constantes.valor('COSTO_CARGA_MAX')}; "
                         "§8.1; COS-13)")
    if temporal is None:                               # COS-23 (PED-4, ENT-9): la crea y la borra entorno
        with entorno.carpeta_de_trabajo(PREFIJO_TRABAJO) as carpeta:
            return medir(rutas, real_era5=real_era5, umbrales=umbrales, temporal=carpeta, escala=escala,
                         aislar=aislar, puntos=puntos, procesos=procesos)
    temporal = sintetico.destino_temporal(temporal)
    ctx = {"U": umbrales, "escala": escala, "rutas": rutas, "real_era5": real_era5, "temporal": str(temporal)}
    permitidas = (str(ruta_mes_real(rutas)),) if real_era5 else ()
    salida: dict = {"esquema": ESQUEMA_MEDICIONES, "escala": dataclasses.asdict(escala), "a_escala": a_escala,
                    "fallas_escala": fallas_escala(escala), "real_era5": real_era5, "aislada": bool(aislar),
                    "procesos": int(procesos), "puntos": {},
                    "sistema": {"memoria_fisica_bytes": memoria_fisica(), "nucleos": int(os.cpu_count() or 0)}}
    libre = _carga_libre([carga0])
    maximas = []
    for nombre in puntos:
        if nombre == "contencion":
            r = _contencion(ctx, procesos, permitidas) if aislar else \
                {"estado": SIN_MEDIR, "motivo": "sin aislar no hay copias a la vez (COS-20)"}
            salida["puntos"][nombre] = r          # la contención carga la máquina a propósito: no cuenta en la carga
            continue
        with _Muestreo(propios=1) as muestreo:          # el que mide el punto (COS-13)
            if aislar:
                r = orquestacion.repartir([{"punto": nombre}, {"punto": None}], _punto, 2, contexto=ctx,
                                          permitidas=permitidas)[0]
            else:
                r = orquestacion.repartir([{"punto": nombre}], _punto, 1, contexto=ctx, permitidas=permitidas)[0]
        r = {k: v for k, v in r.items() if k != "pid"}
        r["carga"] = muestreo.resumen()
        libre = libre and r["carga"]["libre"]
        maximas.append(r["carga"]["maxima_ajena"])
        salida["puntos"][nombre] = r
    finitas = [c for c in maximas if c is not None]
    salida["carga"] = {"inicio": carga0, "inicio_libre": _carga_libre([carga0]),
                       "maxima_ajena": max(finitas) if finitas else None, "libre": bool(libre)}
    return salida


# ---------------------------------------------------------------------------
# Proyección (COS-6 a COS-8, COS-11, COS-18 a COS-20)
# ---------------------------------------------------------------------------
def _meses_y_anios() -> tuple[list[str], list[int]]:
    """Los meses y años UTC de H desde ``PRODUCTO_DESDE`` (COS-2: 321 y 27)."""
    epoca = np.datetime64(str(constantes.valor("PRODUCTO_DESDE")), "h")
    ultima = epoca + np.timedelta64(CONTEOS["horas"] - 1, "h")
    meses = np.arange(epoca.astype("datetime64[M]"), ultima.astype("datetime64[M]") + 1)
    textos = [str(m).replace("-", "") for m in meses]
    return textos, sorted({_anio(m) for m in textos})


def _horas_reales_mes(m: str) -> int:
    h = _horas_mes(m)
    return int(np.count_nonzero(h < CONTEOS["horas"]))


def _k_reales(regla: str) -> dict[int, int]:
    """k(año) de la pasada con la regla (COS-8), con redes ficticias distintas: lo que cuenta es cuántas son."""
    esc = tendencias.EscenariosTF(variable="T", historica=frozenset({"a"}), constante=frozenset({"b"}), regla=regla)
    _, anios = _meses_y_anios()
    return {a: len({esc.red(x, a) for x in tendencias.ESCENARIOS if a in esc.anios(x)}) for a in anios}


def _pared_fase(suma_s: float, maxima_s: float, procesos: int, *, serie_s: float = 0.0, arranque_s: float = 0.0,
                contencion: float = 1.0) -> dict:
    """COS-6: T = Σ·c/P + T_serie + arranque + el desequilibrio (la unidad más larga), con c el factor de contención
    (COS-20) sobre lo que corre a la vez."""
    total = suma_s * contencion / procesos + serie_s + arranque_s + maxima_s
    return {"suma_h": suma_s / _S_H, "procesos": int(procesos), "contencion": contencion,
            "desequilibrio_h": maxima_s / _S_H, "serie_h": serie_s / _S_H, "arranque_h": arranque_s / _S_H,
            "pared_h": total / _S_H}


def _sin(x) -> bool:
    return not isinstance(x, Mapping) or x.get("estado") in (PENDIENTE, SIN_MEDIR)


def _tasas_tf(filas) -> tuple[dict[int, float], float]:
    """({k: s por hora}, lo que el primer mes trae de más): COS-8."""
    if not filas:
        return {}, 0.0
    por_k: dict[int, list] = {}
    for f in filas[1:]:
        por_k.setdefault(int(f["redes"]), []).append(f["pared_s"] / f["horas"])
    primero = filas[0]
    tasa = {k: float(np.mean(v)) for k, v in por_k.items()}
    k0 = int(primero["redes"])
    if k0 in tasa:
        extra = max(0.0, primero["pared_s"] - tasa[k0] * primero["horas"])
    else:
        tasa[k0] = primero["pared_s"] / primero["horas"]
        extra = 0.0
    return tasa, extra


def _tasa_k(tasa: Mapping[int, float], k: int) -> float:
    """La tasa por hora de un mes con k redes: la medida, o la recta por las medidas (COS-8)."""
    if k in tasa:
        return tasa[k]
    ks = sorted(tasa)
    if len(ks) == 1:
        return tasa[ks[0]] * k / ks[0]
    a, b = ks[0], ks[-1]
    pendiente = (tasa[b] - tasa[a]) / (b - a)
    return max(0.0, tasa[a] + pendiente * (k - a))


def _horas_muestra_m6(U) -> int:
    """Horas de los días de la muestra de M6 (TEN-19): d2000 mód SEL_MOD = SEL_RESTO en M6_TF_DESDE-M6_TF_HASTA."""
    a = _h_de_fecha(f"{int(U.a('M6_TF_DESDE')):04d}-01-01") // 24
    b = _h_de_fecha(f"{int(U.a('M6_TF_HASTA')) + 1:04d}-01-01") // 24
    dias = tendencias.dias_tf_contaminantes(np.arange(a, b, dtype=np.int64), U)
    return int(np.asarray(dias).size) * 24


def proyectar(mediciones: dict, umbrales, *, procesos: int = int(constantes.valor("PROCESOS"))) -> dict:
    """Horas de pared de M3-4, M5, M6 y de la grilla v2 por variante, la memoria por proceso y del grupo, y el
    veredicto (COS-6 a COS-12, COS-18 a COS-22). Lo que no se midió queda en «sin_medir» con su motivo; lo que el texto
    no mide entra como cota declarada (``REFERENCIAS``)."""
    if isinstance(procesos, bool) or not isinstance(procesos, int) or procesos < 1:
        raise ErrorCosto("procesos: un entero ≥ 1")
    U, P = umbrales, procesos
    pts = mediciones["puntos"]
    N, H, hd = CONTEOS["estaciones"], CONTEOS["horas"], CONTEOS["horas_con_dato"]
    meses, anios = _meses_y_anios()
    memoria = _memoria(mediciones, P)                  # COS-25 (D59): la memoria primero
    por_fase = memoria["procesos_por_fase"]

    def n_de(compuerta: str, fase: str) -> int:
        """Los procesos de una fase de reparto (D59); sin ninguno que quepa, P (sólo informativa: no decide)."""
        n = int(por_fase[compuerta][fase])
        return n if n >= 1 else P
    sin_medir: dict[str, str] = {}
    esenciales = []
    lec = 0.0
    if _sin(pts.get("mes_real")):
        sin_medir["lectura_mes"] = "sin el mes real (punto 6): las lecturas de los meses no suman"
        esenciales.append("lectura_mes")
    else:
        lec = pts["mes_real"]["huella"]["pared_s"] + pts["mes_real"]["lectura"]["pared_s"]
    cont = pts.get("contencion")
    if _sin(cont) or not math.isfinite(float(cont.get("factor", math.nan))):
        sin_medir["contencion"] = (cont or {}).get("motivo", "sin el factor de contención (COS-20)")
        esenciales.append("contencion")
        fc = 1.0
    else:
        fc = float(cont["factor"])
    fases: dict[str, dict] = {}
    serie: dict[str, float] = {}
    qc = pts.get("qc")
    if _sin(qc):
        sin_medir["control_de_calidad"] = (qc or {}).get("motivo", "no se midió el punto 1")
        esenciales.append("control_de_calidad")
    else:
        t_h = qc["ms_por_hora"] / _MS
        args = (t_h * hd, t_h * H)
        fases["control_de_calidad"] = _con_p(_pared_fase(*args, n_de("m34", "artefactos"), contencion=fc),
                                             _pared_fase(*args, P, contencion=fc))
        tab = qc["anchas_tablas"]
        serie["escribir_y_releer_tablas_anchas"] = (tab["codificar_s_por_fila"] + tab["releer_s_por_fila"]) * hd
    pl = pts.get("pliegue")
    datos_s = 0.0
    if _sin(pl):
        sin_medir["seleccion"] = "no se midió el punto 2"
        esenciales.append("seleccion")
    else:
        f_h = hd / max(pl["horas_dato"], 1)
        f_n = N / max(pl["estaciones"], 1)
        # COS-15: el pliegue de P2 en tibio, menos sus estaciones de prueba (por la diferencia con el de P1), es la
        # selección de un pliegue; lo que el primero de un trabajador trae de más (en frío), una vez por trabajador
        tibio = pl["pliegue_tibio"]["pared_s"]
        t_est = pl["por_estacion_prueba_s"] * f_h / f_n
        t_sel = max(0.0, tibio - pl["prueba"] * pl["por_estacion_prueba_s"]) * f_h
        frio = max(0.0, pl["pliegue"]["pared_s"] - tibio) * f_h
        n_pl = int(U.a("P1_PLIEGUES")) + CONTEOS["bloques_p2"] + 1
        max_prueba = math.ceil(pl["prueba_max_p1"] * f_n)
        datos_s = pl["filas_c_s"] * f_n
        args, kw = (n_pl * t_sel + 2 * N * t_est, t_sel + max_prueba * t_est), {"arranque_s": datos_s + frio,
                                                                               "contencion": fc}
        fases["seleccion"] = _con_p(_pared_fase(*args, n_de("m34", "seleccion_y_prediccion"), **kw),
                                    _pared_fase(*args, P, **kw))
        serie["residuos"] = (pl["residuos_s"] + pl["en_horas_residuos_s"] + pl["clima_a_s"]) * f_h
        serie["datos_del_principal"] = datos_s
        rt = pl["residuos_tablas"]
        serie["escribir_residuos"] = rt["codificar_s_por_fila"] * pl["filas_residuos"] * f_h
    serie["rr06_lectura_de_los_meses"] = len(meses) * lec
    serie["metricas_remuestreo_pi_decision_cota"] = REFERENCIAS["serie_no_medida_h"] * _S_H
    fases["serie_m34"] = _pared_fase(0.0, 0.0, P, serie_s=sum(serie.values()))
    fases["serie_m34"]["pared_h_con_P"] = fases["serie_m34"]["pared_h"]
    fases["serie_m34"]["partes_h"] = {k: v / _S_H for k, v in serie.items()}
    tf = pts.get("tf")
    tf_por_regla = {}
    if _sin(tf):
        sin_medir["tf"] = "no se midió el punto 3"
        esenciales.append("tf")
    else:
        f_c = CONTEOS["celdas_pobladas"] / max(tf["celdas"], 1)
        n_tf = n_de("m34", "tendencias_y_finitud")         # las dos pasadas son de la misma fase (A39)
        for regla in (r.value for r in tipos.ReglaRedConstante if r is not tipos.ReglaRedConstante.NINGUNA):
            k_de = _k_reales(regla)
            por_pasada = {}
            for pasada in PASADAS:
                filas = tf["pasadas"][pasada]["meses"]
                tasa, primero = _tasas_tf(filas)
                arranque = (2 * tf["pasadas"][pasada]["armar"]["pared_s"] + primero) * f_c + datos_s
                t_meses = []
                for m in meses:
                    k = k_de.get(_anio(m), 0)
                    t_meses.append(_tasa_k(tasa, k) * _horas_reales_mes(m) * f_c if k else lec)
                args, kw = (sum(t_meses), max(t_meses)), {"arranque_s": arranque, "contencion": fc}
                por_pasada[pasada] = _con_p(_pared_fase(*args, n_tf, **kw), _pared_fase(*args, P, **kw))
            tf_por_regla[regla] = {"pasadas": por_pasada, "procesos": n_tf,
                                   "pared_h": sum(x["pared_h"] for x in por_pasada.values()),
                                   "pared_h_con_P": sum(x["pared_h_con_P"] for x in por_pasada.values())}
        peor = max(tf_por_regla, key=lambda r: tf_por_regla[r]["pared_h"])
        fases["tf"] = {**tf_por_regla[peor], "regla": peor}
    m34 = sum(f["pared_h"] for f in fases.values())
    # P147 (COS-25): la de antes de D59, con P en todas las fases (la regla de TF más cara con P); no decide
    m34_con_p = sum(f["pared_h_con_P"] for k, f in fases.items() if k != "tf")
    if "tf" in fases:
        m34_con_p += max(v["pared_h_con_P"] for v in tf_por_regla.values())
    m34_menor = m34
    if tf_por_regla:
        m34_menor = m34 - fases["tf"]["pared_h"] + min(v["pared_h"] for v in tf_por_regla.values())
    sin_medir["m34_cota"] = "métricas, remuestreo, π y decisión: la cota de §8 del diseño (COS-9)"
    m5_proy = _proyectar_m5(pts, U, (n_de("m5", "representatividad"), n_de("m5", "anual")), meses, anios, lec, fc,
                            datos_s, sin_medir)
    grilla_proy, m6_proy = _proyectar_grilla_m6(pts, U, P, meses, lec, fc, sin_medir)     # siguen con P (A39)
    proy = {"esquema": ESQUEMA_COSTO, "procesos": P, "procesos_por_fase": por_fase, "conteos": dict(CONTEOS),
            "referencias": dict(REFERENCIAS), "meses": len(meses), "anios": len(anios),
            "m34": {"fases": fases, "pared_h": m34, "pared_h_con_P": m34_con_p, "pared_h_regla_menor": m34_menor,
                    "completa": not esenciales, "faltan": esenciales},
            "tf_por_regla": tf_por_regla, "m5": m5_proy, "m6": m6_proy, "grilla_v2": grilla_proy,
            "memoria": memoria, "sin_medir": sin_medir}
    proy["veredicto"] = _veredicto(mediciones, proy, U)
    return proy


def _con_p(con_n: dict, con_p: dict) -> dict:
    """La pared de una fase con sus procesos (D59) y, aparte, la que tendría con P procesos (P147, COS-25)."""
    return {**con_n, "pared_h_con_P": con_p["pared_h"]}


def _proyectar_m5(pts, U, procesos: tuple[int, int], meses, anios, lec, fc, datos_s, sin_medir) -> dict | None:
    """M5 (COS-7, COS-19): la primera pasada (una lectura por mes; la fase «representatividad») y la unidad anual (el
    0,1° y la salud del peor ganador, la lluvia, las lecturas; la fase «anual»), cada una con sus procesos (D59,
    COS-25), y, en serie en el principal, el operador de la grilla y la representatividad."""
    n_rep, n_anual = procesos
    m5 = pts.get("m5")
    if _sin(m5):
        sin_medir["m5"] = "no se midió el punto 4"
        return None
    f_pix = CONTEOS["pixeles"] / max(m5["pixeles"], 1)
    f_sal = CONTEOS["celdas_pobladas"] / max(m5["celdas_salud"], 1)
    pix = peor_configuracion({k: v["pared_s"] for k, v in m5["pixeles_producto"].items()})
    agudo = peor_configuracion(_paredes(m5["salud"][Uso.AGUDO.value]))
    cronico = peor_configuracion(_paredes(m5["salud"][Uso.CRONICO.value]))
    # el agudo dos veces: el de las tres carpetas y el de la representatividad (COS-7)
    t_mes = ((pix["pared_s"] + m5["pixeles_netcdf"]["pared_s"]) * f_pix
             + (2 * agudo["pared_s"] + cronico["pared_s"] + m5["lluvia"]["pared_s"]) * f_sal) / m5["horas"]
    t_anio = [sum(_horas_reales_mes(m) * t_mes + lec for m in meses if _anio(m) == a) + lec for a in anios]
    op_s = m5["operador_salud"]
    n_cod = op_s["celdas"] if op_s["real"] else CONTEOS["celdas"]                       # sin la real, la cota
    arranque = datos_s + op_s["pared_s"] * n_cod / max(op_s["celdas"], 1)
    serie = {}
    gr, pl = pts.get("grilla"), pts.get("pliegue")
    if not _sin(gr):
        serie["operador_de_la_grilla"] = gr["operador_mayor"]["pared_s"] * CONTEOS["celdas"] / gr["celdas"]
    else:
        sin_medir["m5_operador_de_la_grilla"] = "sin el punto 5"
    if not _sin(pl):
        serie["representatividad"] = pl["representatividad_s"] * CONTEOS["horas_con_dato"] / max(pl["horas_dato"], 1)
    sin_medir["m5_laterales"] = "las tablas laterales de los monitores (COS-9)"
    primera = _pared_fase(len(meses) * lec, lec, n_rep, contencion=fc)
    anual = _pared_fase(sum(t_anio), max(t_anio), n_anual, arranque_s=arranque, contencion=fc)
    total = primera["pared_h"] + anual["pared_h"] + sum(serie.values()) / _S_H
    return {"primera_pasada": primera, "anual": anual, "serie_h": {k: v / _S_H for k, v in serie.items()},
            "pared_h": total, "peor": {"pixeles": pix["ganador"], "agudo": agudo["ganador"],
                                        "cronico": cronico["ganador"]},
            "disco_01deg_gb": m5["bytes_netcdf"] * f_pix * len(meses) / _GB}


def _paredes(tiempos: Mapping) -> dict:
    """Un uso de un solo grupo (agudo, crónico): sus configuraciones, como «base» y «grupo=candidato»."""
    salida = {}
    for nombre, t in tiempos.items():
        salida[nombre] = t["pared_s"]
    return salida


def _proyectar_grilla_m6(pts, U, P, meses, lec, fc, sin_medir) -> tuple:
    """La grilla v2 por variante con el peor ganador (COS-5, COS-14) y las columnas de la muestra de M6 (COS-7)."""
    gr = pts.get("grilla")
    m6 = {"estado": SIN_MEDIR, "motivo": "la fábrica de v2 no está escrita (COS-7)"}
    if _sin(gr):
        sin_medir["grilla"] = "no se midió el punto 5"
        return None, m6
    f_g = CONTEOS["celdas"] / max(gr["celdas_medidas"], 1)
    salida, tasas = {}, []
    for var in VARIANTES:
        peor = peor_configuracion({k: c["variantes"][var]["pared_s"] for k, c in gr["configuraciones"].items()})
        t_h = peor["pared_s"] * f_g / gr["horas"]
        tasas.append(peor["pared_s"] / (gr["celdas_medidas"] * gr["horas"]))
        t_meses = [t_h * _horas_reales_mes(m) + lec for m in meses]
        arranque = max(c["operador"]["pared_s"] for c in gr["configuraciones"].values()) * CONTEOS["celdas"] \
            / gr["celdas"]
        salida[var] = {**_pared_fase(sum(t_meses), max(t_meses), P, arranque_s=arranque, contencion=fc),
                       "peor": peor["ganador"]}
    filas_m6 = CONTEOS["comunas_m6"] * int(U.a("M6_CELDAS_COMUNA")) * _horas_muestra_m6(U)
    n_esc = len((tendencias.CAMBIO, tendencias.COMPLETO))          # TF1 de contaminantes (TEN-20)
    celda_horas = filas_m6 * n_esc * len(VARIANTES) * len(tipos.CONTAMINANTES_M6)
    # ORQ-29: la TF de contaminantes corre en el proceso principal, una unidad por contaminante y variante
    m6 = {"estado": "parcial", "motivo": "sólo las columnas meteorológicas de la muestra; el modelo de v2 no está "
                                         "escrito (COS-7, COS-9)",
          "filas_muestra": int(filas_m6), "celda_horas": int(celda_horas),
          "columnas": _pared_fase(celda_horas * max(tasas), 0.0, 1)}
    operador_gb = gr["operador_mayor"]["bytes"] * CONTEOS["celdas"] / gr["celdas"] / _GB
    return {"variantes": salida, "operador_gb": operador_gb}, m6


def _memoria(mediciones: Mapping, P: int) -> dict:
    """COS-11, COS-25: la memoria de cada trabajador por fase, del principal de M3-4 y de M5 y del grupo (n trabajadores
    y el principal) frente a la memoria física, los procesos que caben en cada fase de reparto (D59) y el control de
    calidad en la estación más larga frente a los ≈ 340 MB de §8. Cada punto arma su ``DatosCompetencia`` por el
    camino de la corrida (COS-24), así que su pico ya trae la etapa en que se arma y la de su trabajo (el máximo, no la
    suma); a otra escala, se suma lo que la red real trae de más: por horas con dato, los residuos y el fondo guardado;
    por estaciones, las filas de C, el clima y la caché; por celdas y píxeles, los estáticos y el clima de M2a. En
    bytes; el tope de §8 es ``MEMORIA_MAX_GB``·10⁹ B (la lectura estricta; P-COS-4)."""
    pts = mediciones["puntos"]
    tope = float(constantes.valor("MEMORIA_MAX_GB")) * _GB
    fisica = float((mediciones.get("sistema") or {}).get("memoria_fisica_bytes") or 0)
    hd, N = CONTEOS["horas_con_dato"], CONTEOS["estaciones"]
    salida: dict = {"unidad": "GB = 10^9 B", "tope_gb": tope / _GB, "fisica_gb": fisica / _GB, "faltan": []}
    trab, princ = {}, {}

    def falta(r) -> float:
        """Los bytes que la red real trae de más que el mundo medido de un punto."""
        b = r["bytes"]
        f_h = hd / max(r.get("horas_dato", hd), 1)
        f_n = N / max(r.get("estaciones", N), 1)
        f_c = CONTEOS["celdas"] / max(b.get("filas_estaticos", CONTEOS["celdas"]), 1)
        f_p = CONTEOS["pixeles"] * 12 * 24 / max(b.get("filas_clima_pixeles", CONTEOS["pixeles"] * 12 * 24), 1)
        return ((f_h - 1) * (b.get("residuos", 0) + b.get("campos_estaciones", 0))
                + (f_n - 1) * (b.get("filas_c", 0) + b.get("clima_estaciones", 0) + b.get("cache_series", 0))
                + (f_c - 1) * b.get("estaticos_celdas", 0) + max(0.0, f_p - 1) * b.get("clima_pixeles", 0))

    def ligera(r) -> float:
        """La ``DatosCompetencia`` ligera y lo de M2a que deja, a escala real (lo que guarda el principal, ORQ-44)."""
        b = r["bytes"]
        f_h = hd / max(r.get("horas_dato", hd), 1)
        f_n = N / max(r.get("estaciones", N), 1)
        f_c = CONTEOS["celdas"] / max(b.get("filas_estaticos", CONTEOS["celdas"]), 1)
        f_p = CONTEOS["pixeles"] * 12 * 24 / max(b.get("filas_clima_pixeles", CONTEOS["pixeles"] * 12 * 24), 1)
        return (b.get("residuos", 0) * f_h + (b.get("filas_c", 0) + b.get("clima_a", 0) + b.get("cache_series", 0))
                * f_n + b.get("estaticos_celdas", 0) * f_c + b.get("clima_pixeles", 0) * max(1.0, f_p))
    pl = pts.get("pliegue")
    if _sin(pl):
        salida["faltan"].append("pliegue")
    else:
        trab["seleccion"] = pl["memoria_pico_gb"] * _GB + falta(pl)
    op_grilla = 0.0
    gr = pts.get("grilla")
    if not _sin(gr):
        op_grilla = gr["operador_mayor"]["bytes"] * CONTEOS["celdas"] / gr["celdas"]
    for nombre in ("tf", "m5", "grilla"):
        r = pts.get(nombre)
        if _sin(r):
            salida["faltan"].append(nombre)
            continue
        w = r["memoria_pico_gb"] * _GB + falta(r)
        if nombre == "m5":
            op_s = r["operador_salud"]                         # medido en el punto; sin la geometría real, la cota
            if not op_s["real"]:
                w += (op_s["bytes"] + op_s["estaticos_bytes"]) * max(0.0, CONTEOS["celdas"] / max(op_s["celdas"], 1)
                                                                      - 1)
            w += op_grilla                                     # los trabajadores lo leen para las laterales (ORQ-28)
        trab[nombre] = w
    tf = pts.get("tf")
    if not _sin(tf):
        base = tf["memoria_inicio_gb"] * _GB
        mes = _bytes_mes(pts)
        princ["m34"] = max(tf["memoria_tras_fabricar_gb"] * _GB + falta(tf), base + ligera(tf) + 12 * mes)
        princ["m5"] = base + ligera(tf) + op_grilla
        salida["principal_detalle_gb"] = {"ligera": ligera(tf) / _GB, "un_anio_de_meses": 12 * mes / _GB,
                                          "operador_grilla": op_grilla / _GB}
    mes_real = pts.get("mes_real")                     # COS-25: la representatividad lee un mes real entero
    if not _sin(mes_real) and mes_real.get("memoria_pico_gb") is not None:
        trab["representatividad"] = float(mes_real["memoria_pico_gb"]) * _GB
    else:
        salida["faltan"].append("mes_real")
    qc = pts.get("qc")
    if not _sin(qc):
        trab["control_de_calidad"] = qc["memoria_antes_unidades_gb"] * _GB + _memoria_estacion(qc, CONTEOS["horas"])
        salida["control_de_calidad_frente_al_texto"] = {
            "estacion_mas_larga_gb": trab["control_de_calidad"] / _GB, "texto_gb": REFERENCIAS["qc_por_proceso_mb"]
            * _MB / _GB, "bajo_el_texto": bool(trab["control_de_calidad"] <= REFERENCIAS["qc_por_proceso_mb"] * _MB)}
    else:
        salida["faltan"].append("qc")
    salida["trabajador_gb"] = {k: v / _GB for k, v in trab.items()}
    salida["principal_gb"] = {k: v / _GB for k, v in princ.items()}
    fases = {}
    for nombre, w in trab.items():                     # por la memoria medida (la grilla v2, sólo informativa)
        p_fase = princ.get(_COMPUERTA_DE_MEMORIA.get(nombre, "m34"))
        n = _procesos_que_caben(w, p_fase, fisica, tope, P)
        fases[nombre] = {"trabajador_gb": w / _GB, "grupo_gb": None if p_fase is None else (P * w + p_fase) / _GB,
                         "grupo_con_n_gb": None if p_fase is None or n == 0 else (n * w + p_fase) / _GB,
                         "cabe": bool(n == P), "procesos_que_caben": n}
    salida["fases"] = fases
    por_fase, sin_procesos = {}, []                    # COS-25 (D59, A39): por las fases de reparto de orquestacion
    for compuerta, nombres in orquestacion.FASES_REPARTO.items():
        por_fase[compuerta] = {}
        for fase in nombres:
            n = _procesos_que_caben(trab.get(_MEMORIA_DE_FASE[fase]), princ.get(compuerta), fisica, tope, P)
            por_fase[compuerta][fase] = n
            if n == 0:
                sin_procesos.append(f"{compuerta}/{fase}")
    salida["procesos_por_fase"] = por_fase
    salida["sin_procesos"] = sin_procesos
    salida["principal_m34_cabe"] = bool("m34" in princ and princ["m34"] <= tope)
    return salida


def _procesos_que_caben(trabajador, principal, fisica, tope, procesos: int) -> int:
    """D59 (COS-25), D65: el mayor n de 1 a ``procesos`` con trabajador y principal bajo el tope de §8 y
    n·trabajador + principal bajo la memoria física (bytes, «≤»); 0 si no cabe ni con uno o falta alguna medida."""
    medidas = (trabajador, principal, fisica, tope)
    if any(x is None or not math.isfinite(float(x)) for x in medidas) or trabajador <= 0 or fisica <= 0:
        return 0
    if trabajador > tope or principal > tope:
        return 0
    for n in range(int(procesos), 0, -1):
        if n * trabajador + principal <= fisica:
            return n
    return 0


def _bytes_mes(pts: Mapping) -> float:
    """Los bytes de un mes ERA5-Land leído (float32, horas × píxeles × 6 variables): el real si se midió, si no los
    8.206 píxeles × 744 h."""
    r = pts.get("mes_real")
    horas, pixeles = (r["horas"], r["pixeles"]) if not _sin(r) else (744, CONTEOS["pixeles"])    # no-umbral: 31 × 24
    return float(horas * pixeles * len(sintetico.VARIABLES_ERA5L) * np.dtype(np.float32).itemsize)


def _memoria_estacion(qc: Mapping, horas: int) -> float:
    """COS-11: los bytes de una unidad de control de calidad con ``horas`` horas, por la recta entre la estación con la
    mitad de sus meses y con todos (con un solo punto, proporcional a las horas)."""
    por_meses = {int(k): float(v) for k, v in qc["memoria_por_meses"].items()}
    horas_mes = qc["horas_estacion"] / max(max(por_meses), 1)
    if len(por_meses) < 2:
        (n, b), = por_meses.items()
        return b * horas / max(n * horas_mes, 1)
    (n1, b1), (n2, b2) = sorted(por_meses.items())[0], sorted(por_meses.items())[-1]
    pendiente = max(0.0, (b2 - b1) / ((n2 - n1) * horas_mes))
    return max(b2, b1 + pendiente * (horas - n1 * horas_mes))


def _veredicto(mediciones: Mapping, proy: Mapping, U) -> dict:
    """COS-12, COS-22, COS-25: el recorte se decide sólo con una proyección completa, con P = ``PROCESOS``, a la escala
    de §8.1, con el mes real, con la máquina libre en toda la medición, si cada fase de reparto cabe con al menos un
    proceso (D59) y si los principales de M3-4 y M5 quedan bajo el tope. Si no, «pendiente» con sus motivos. Decide la cota
    superior (la regla y el ganador más caros; P-COS-5); si una fase corre con menos de P, una nota lo dice."""
    motivos = []
    if not proy["m34"]["completa"]:
        motivos.append("proyección incompleta: " + ", ".join(proy["m34"]["faltan"]))
    if proy["procesos"] != int(constantes.valor("PROCESOS")):
        motivos.append(f"P = {proy['procesos']}, no {constantes.valor('PROCESOS')} (D2)")
    if not mediciones.get("a_escala"):
        motivos.append("la medición no es la de §8.1 (COS-22)")
    if not mediciones.get("real_era5"):
        motivos.append("sin el mes real (COS-10)")
    if not (mediciones.get("carga") or {}).get("libre"):
        motivos.append("la máquina no estuvo libre en toda la medición (COS-13)")
    mem = proy["memoria"]
    tope = f"{constantes.valor('MEMORIA_MAX_GB')}·10⁹ B"
    if mem["sin_procesos"]:
        motivos.append("D59: no caben en memoria ni con un proceso, o no se midió su memoria: "
                       + ", ".join(mem["sin_procesos"]) + " (COS-25)")
    if not mem["principal_m34_cabe"]:
        motivos.append(f"el principal de M3-4 pasa del tope de {tope}, o no se midió (COS-11; P-ORQ-11)")
    umbral = float(U.a("SEL_UMBRAL_H"))
    notas = []
    menos = [f"{c}/{f} con {n}" for c, fs in proy["procesos_por_fase"].items() for f, n in fs.items()
             if 0 < n < proy["procesos"]]
    if menos:
        notas.append(f"D59: corren con menos de {proy['procesos']} procesos, y su pared se proyecta con ese número: "
                     + ", ".join(menos) + " (COS-25)")
    t, t_menor = proy["m34"]["pared_h"], proy["m34"]["pared_h_regla_menor"]
    if (t > umbral) != (t_menor > umbral):
        notas.append("el recorte lo decide la cota superior: con la regla de red más barata sería otro (P-COS-5)")
    t_p = float(proy["m34"].get("pared_h_con_P", t))
    if (t > umbral) != (t_p > umbral):                 # P147: la regla de decisión no cambia; se informa
        mod_p = int(U.a("SEL_MOD_RECORTE") if t_p > umbral else U.a("SEL_MOD"))
        notas.append(f"P147 (D59): con {proy['procesos']} procesos en todas las fases la pared de M3-4 sería "
                     f"{t_p:.2f} h y el recorte, «mod{mod_p}»; decide la pared con los procesos de cada fase, "
                     f"{t:.2f} h (COS-25)")
    return {"decide": not motivos, "motivos": motivos, "notas": notas, "criterio": "cota superior",
            "umbral_h": umbral}


def recorte(proyeccion: dict, umbrales) -> str:
    """«mod11», «mod23» o «pendiente» (§4.9; COS-12): «pendiente» si el veredicto no decide (COS-22); si decide, mód
    ``SEL_MOD_RECORTE`` si la pared de M3-4 pasa de ``SEL_UMBRAL_H`` horas."""
    veredicto = proyeccion.get("veredicto")
    if not isinstance(veredicto, Mapping):
        raise ErrorCosto("la proyección no trae su veredicto (proyectar)")
    if not veredicto["decide"]:
        return PENDIENTE
    t = float(proyeccion["m34"]["pared_h"])
    if not math.isfinite(t):
        raise ErrorCosto("la pared de M3-4 no es finita")
    mod = umbrales.a("SEL_MOD_RECORTE") if t > float(umbrales.a("SEL_UMBRAL_H")) else umbrales.a("SEL_MOD")
    return f"mod{int(mod)}"


# ---------------------------------------------------------------------------
# costo_m1.json (resumen)
# ---------------------------------------------------------------------------
_CLAVES_FUERA = ("pid",)


def _limpio(x):
    """Números de Python, sin NaN (None), sin rutas; las claves como texto."""
    if isinstance(x, Mapping):
        return {str(k): _limpio(v) for k, v in x.items() if k not in _CLAVES_FUERA}
    if isinstance(x, (list, tuple)):
        return [_limpio(v) for v in x]
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return float(x) if math.isfinite(float(x)) else None
    if isinstance(x, Path):
        return x.name
    return x


def contenido_costo(mediciones: dict, proyeccion: dict, umbrales) -> dict:
    """El contenido de ``costo_m1.json`` (resumen; CEG-20): la escala, las mediciones por punto (tiempos, memoria y
    conteos, sin rutas), la proyección, su veredicto, el recorte («pendiente» si no decide) y las lecturas COS-n. Sin
    «fondo», «era5l» ni «R_»."""
    puntos = {}
    for nombre, r in mediciones["puntos"].items():
        puntos[nombre] = {k: v for k, v in r.items() if k not in ("bytes",)}
        if "bytes" in r:
            puntos[nombre]["insumos_bytes"] = r["bytes"]
    rec = recorte(proyeccion, umbrales)
    contenido = {
        "esquema": ESQUEMA_COSTO, "escala": dict(mediciones["escala"]), "a_escala": bool(mediciones.get("a_escala")),
        "fallas_escala": list(mediciones.get("fallas_escala", [])), "mes_real_leido": bool(mediciones["real_era5"]),
        "aislada": bool(mediciones["aislada"]), "sistema": mediciones.get("sistema", {}),
        "carga": mediciones.get("carga", {}), "carga_maxima_permitida": float(constantes.valor("COSTO_CARGA_MAX")),
        "mediciones": puntos, "proyeccion": {k: v for k, v in proyeccion.items() if k not in ("esquema", "veredicto")},
        "veredicto": proyeccion["veredicto"], "recorte": rec, "recorte_pendiente": rec == PENDIENTE,
        "procesos_por_fase": proyeccion["procesos_por_fase"],                 # A39 (D59): los usa el addendum
        "umbral_recorte_h": float(umbrales.a("SEL_UMBRAL_H")), "lecturas": list(LECTURAS),
        "umbrales": {"sha256_json": umbrales.sha256_json, "sha256_texto": umbrales.sha256_texto,
                     "sha256_texto_vigente": getattr(umbrales, "sha256_texto_vigente", "")}}
    return _limpio(contenido)


__all__ = ("CONTEOS", "ESCALA_PRUEBA", "ESCALA_REAL", "ErrorCosto", "Escala", "PUNTOS", "REFERENCIAS", "carga_ajena",
           "contenido_costo", "fallas_escala", "medir", "memoria_fisica", "peor_configuracion", "proyectar",
           "recorte", "resumen_carga", "ruta_mes_real")
