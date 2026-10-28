"""Validación (§5): métricas por evaluación, bandas y pesos, S y S_par, remuestreo, estratos, soporte, réplica N y
SINCA.

Funciones puras: reciben horas, predicciones y observaciones (o tablas de evaluaciones), las estaciones
(``tipos.InfoEstacion``) y los umbrales (un objeto con ``.a(id)`` y ``.frac(id)``), y devuelven números, diccionarios o
tablas con los esquemas de ``tipos``. No leen ni escriben archivos (§3 del diseño): escribe ``salidas``. **Sin columna
de banda ni de distancia en las evaluaciones** (§0.4.5): la banda sale de ``particiones``, desde la geometría, sólo al
calcular S, y vive en memoria (``bandas_de_pliegues``).

En el orden del texto:
- §5.2: ``metricas_horarias``, ``dia_civil``, ``dias_validos``, ``medias_diarias``, ``desviacion_estrato``,
  ``nivel_diario``, ``anios_validos``, ``anomalias``, ``medias_macrozona_anio``, ``anual_neto``,
  ``anomalia_interanual``, ``ciclo_diario`` y ``cociente_amplitudes``; ``evaluacion`` las junta para una evaluación,
  ``fila_evaluacion`` y ``tabla_evaluaciones`` arman ``tipos.ESQUEMA_EVALUACIONES`` y ``completar_cronico`` llena el
  nivel neto y la anomalía de lo crónico, que necesitan todas las evaluaciones.
- §5.8: ``extremos`` (EX_e) y ``extremos_descriptivos``.
- §5.2 y §5.8, descriptivos (VAL-21): ``descriptivos_de``, ``filas_descriptivas`` y ``tabla_descriptivos`` (el cociente
  de amplitudes, el sesgo condicional, el acierto y Tmáx y Tmín del agudo, en lo nacional).
- §5.3: ``bandas``, ``rotulos_bandas``, ``bandas_de_pliegues``, ``pi_poblacion``, ``pi_monitores``, ``pi_uso``,
  ``puntaje`` (S, CD y EX con la unión de bandas) y ``puntaje_par``.
- §5.4: ``remuestreo`` (``tipos.ESQUEMA_REPLICAS``, la entrada de ``decision``).
- §5.5: ``publicable`` (regla de soporte), ``estratos`` (``tipos.ESQUEMA_VALIDACION_PUB``: nacional, las cinco
  macrozonas y los estratos descriptivos), ``fracciones_sin_soporte`` (lo único que se publica de un estrato sin
  soporte), ``tabla_bandas`` (``tipos.ESQUEMA_BANDAS_PUB``) y ``replica_n``.
- §5.6: ``validacion_sinca`` (métricas en la celda y en el punto, por terciles de TPI, y el aviso del 15 %).

Dueño: I14 (ola 3).
Lecturas propias (VAL-n), para el addendum de M1:
- VAL-1. **Rótulos** (TIP-15). ``variable`` lleva los de ``tipos.VariableMetrica``; ``estrato``, los de
  ``tipos.Estrato`` («nacional», «macrozona») y, mientras el coordinador no los agregue a ``tipos`` (pedido), los
  descriptivos de §5.5: «conjunto», «altitud», «periodo», «tipo», «propietario» y «omm». ``particion`` es «P1», «P2» o
  ``tipos.PARTICION_AGREGADO``. Las macrozonas son ``tipos.MACROZONAS``. Las variables de cada (uso, grupo) y lo que se
  publica de cada una están en ``METRICAS`` (DEC-1 de ``decision``; una prueba compara S, CD, EX, MZ, nivel y anomalía
  con ``decision.VARIABLES``):
  - ambiental (T, Td): T (S = MSE horario, CD, EX de Tmáx/Tmín), HR (S, CD), Td (S, EX de los extremos diarios de Td);
  - ambiental (u, v): «uv» (S = RMSE vectorial) y la rapidez (S = MSE horario de la rapidez, CD, EX); D43: MZ en las
    dos;
  - ambiental p: S y CD (no hay EX de la presión, §6.1);
  - agudo (T, Td): T y HR horarias (S descriptivo y CD), ``temp_media`` y ``hr_media`` (S = desviación dentro del
    estrato, EX de §5.8 y nivel = MSE de las medias diarias);
  - crónico (T, Td): T (S = nivel neto anual, CD y anomalía interanual) y ``temp_media`` (EX).
  Cada evaluación lleva en ``variable`` el mismo rótulo que la fila publicada.
- VAL-2. **Horas emparejadas** (§5.2). Son las horas con observación válida y producto finito; la evaluabilidad («≥
  2.000 horas válidas de la variable en su pliegue de prueba») se mide sobre ellas (la lectura más estricta: las
  métricas descansan siempre en ≥ ``MIN_HORAS`` horas). Quien llama pone NaN donde la hora no es válida (``valido_*``).
  Viento: «uv» compara (u, v) con el RMSE vectorial √mean(Δu² + Δv²) y su sesgo es el de la rapidez; su MAE (que el
  texto no define para el viento) es la media del módulo del error vectorial, sólo descriptiva. La rapidez es su propia
  variable (CD, EX y MZ de D43). HR: la del producto frente a ``hr_final``; p en hPa.
- VAL-3. **Día civil** (§5.2, §3; MC-27). El día es la fecha civil de la hora en la zona IANA que se pasa
  (America/Santiago, ``tipos.ZONA_CIVIL``), con 23, 24 o 25 horas: sus horas son las horas UTC contiguas con esa fecha
  civil, y la posición de una hora es el número de horas desde la primera del día. El hueco circular es el de MC-27
  sobre un círculo de la duración del día (vectorizado; una prueba lo compara con ``numerico.hueco_circular_max``). Un
  día es válido con ≥ ``DIA_MIN_H`` horas emparejadas y hueco ≤ ``DIA_HUECO_H``. Las medias, los máximos y los mínimos
  diarios del producto y de la observación se toman en las mismas horas emparejadas («la media del día del producto se
  toma en las mismas horas que la observación»; para los extremos de §5.8 la misma regla). La base de zonas debe ser
  sólo la del paquete tzdata (§0, regla 3 del diseño: ``entorno`` la fija al importarse con
  ``zoneinfo.reset_tzpath(to=[])``): si ``zoneinfo.TZPATH`` no está vacío, ``RuntimeError``. Este módulo no importa
  ``entorno`` (§1 del diseño).
- VAL-4. **Agudo** (§5.2). El estrato es estación × año × mes de la fecha civil; entran sólo los estratos con ≥
  ``AGUDO_MIN_DIAS`` días válidos. MSE_e = media sobre los días de esos estratos de (d_producto − d_obs)², con d = la
  media del día menos su media en el estrato. El nivel (columna ``mse_dia``) es la media de (media diaria del producto −
  observada)² sobre todos los días válidos.
- VAL-5. **Crónico** (§5.2, D22 (b)). Año válido = año civil con ≥ ``ANIO_MIN_DIAS`` días válidos; ε_e,y = media de las
  medias diarias del producto − la de las observadas en ese año. Una evaluación entra al nivel neto con ≥ ``MIN_ANIOS``
  años válidos y una macrozona (``InfoEstacion.macrozona`` por ``tipos.macrozona_o_ninguna``, TIP-11; VAL-16): **las
  evaluaciones sin macrozona no entran al nivel
  neto ni a la anomalía, ni a las medias de macrozona × año; se cuentan y se informan** (``attrs["declaraciones"]``; D22
  (b) [delegada]). La media de macrozona × año es la de ε sobre las evaluaciones que entran del mismo candidato en esa
  macrozona y ese año, **de P1 y de P2 juntas** (la literal: «las evaluaciones de la misma macrozona × año»; pregunta
  VAL-P1). MSE_e = media sobre sus años de (ε − media)². Anomalía: con los años válidos de ``ANOMALIA_PERIODO``
  (2010-2023) y ≥ ``MIN_ANIOS_ANOM``, a_e,y = ε_e,y − la media de ε_e en esos años, menos la media de macrozona × año de
  a (sobre las evaluaciones que entran a la anomalía); MSE_e = media de ese error al cuadrado. ``anual_neto`` y
  ``anomalia_interanual`` reciben los años de una evaluación y las medias de su macrozona por año; ``completar_cronico``
  arma esas medias.
- VAL-6. **CD_e** (§5.2). Celdas (mes del año UTC, hora UTC) con ≥ ``CD_MIN_VALORES`` horas emparejadas; δ(m, h) = la
  media de (producto − observación) en la celda; δ̄(m) = la media sin pesos de δ sobre las celdas del mes; CD_e =
  √(media sobre las celdas de (δ − δ̄)²). Sin ninguna celda, NaN. El cociente de amplitudes (descriptivo; «se informa
  aparte») es la media por mes de la amplitud (máximo − mínimo sobre las horas) de la media del producto por celda,
  dividida por la misma media de la observación (no la media de los cocientes de cada mes); NaN si la de la
  observación es 0. Se calcula en cada variable con CD y se publica en la tabla de descriptivos (VAL-21).
- VAL-7. **EX_e** (§5.8). Con ≥ ``EX_MIN_DIAS`` días válidos; si no, NaN. Ambiental: T y Td con los extremos diarios
  (``EX_CUANTILES_AMBIENTAL``: Q95 de los máximos y Q05 de los mínimos, (|b_calor| + |b_frío|)/2) y la rapidez con
  |Q95(máximo diario del producto) − Q95(máximo diario observado)|. Agudo (``temp_media`` y ``hr_media``) y crónico
  (``temp_media``): la media de |Q_q(producto) − Q_q(obs)| en q = 5, 10, 90 y 95 de las medias diarias. Los cuantiles
  son empíricos sin interpolar (``METODO_CUANTIL`` = «inverted_cdf», como MC-48 y DEC-12; pregunta VAL-P4). Los
  descriptivos de §5.8 (``extremos_descriptivos``): el sesgo condicional (media de producto − observación) en los días
  con la observación estrictamente sobre su Q95 o estrictamente bajo su Q05, y el acierto (fracción de los días con la
  observación estrictamente sobre su Q95 en que el producto queda estrictamente sobre su propio Q95; «sobre» es «>»).
  Se toman en la serie diaria de su EX: en T y Td ambientales, el Q95 y el acierto en los máximos diarios y el Q05 en
  los mínimos; en la rapidez, los tres en el máximo diario; en ``temp_media`` y ``hr_media``, en las medias diarias
  (pregunta VAL-P8). Tmáx y Tmín del agudo («quedan descriptivos») son ``extremos(…, "ambiental", "T", …)`` sobre las
  tablas diarias de ``temp_media`` (descriptivo «ex_tmax_tmin»). Todos van a la tabla de descriptivos (VAL-21).
- VAL-8. **Bandas** (§5.3). La banda b de una evaluación es la de la distancia de su estación a la estación de
  entrenamiento más cercana de su pliegue externo con ≥ ``MIN_HORAS`` horas válidas de su variable
  (``particiones.distancia_entrenamiento_km``, PAR-10). Las horas son las de ``valido_<clave>`` de la tabla ancha, con
  la clave ``HORAS_DE`` (``temp_media`` cuenta las de T, ``hr_media`` las de HR, «uv» y la rapidez las del viento). Los
  bordes son inclusivos por arriba: [0, 10], (10, 25], (25, 50] y (50, ∞) km («> 50 km» es el complemento de «≤ 50»);
  sin estación de entrenamiento, la distancia es infinita y va a la última banda.
- VAL-9. **π^pob y π^mon** (§5.3; MC-09). π^pob: cada año de ``PI_POB_PERIODO`` (2000-2025, todos exigidos), cada celda
  con w_ghs(x, y) > 0 a la estación más cercana con ≥ ``MIN_HORAS`` horas válidas de la variable ese año (haversine; el
  vecino se busca con un árbol k-d sobre vectores unitarios y la distancia se recalcula por haversine); π^pob_b = Σ w de
  la banda / Σ w. π^mon: un peso por monitor-año (estación, año UTC) con alguna observación finita de PM2,5 o de NO2 en
  el panel que cita ``pliegues_v2_red2.json`` (un monitor con los dos contaminantes pesa una vez ese año), en los años
  de ``PI_POB_PERIODO`` («lo mismo»), con las coordenadas de ``estaciones`` de ese archivo; cada panel llega con su
  sha256, que debe ser el que cita el manifiesto (R21). Ambiental: π = ``PI_AMBIENTAL``·(π^mon, π^pob); agudo y crónico:
  π = π^pob (``pi_uso``).
- VAL-10. **S y la unión de bandas** (§5.3, MC-29, MC-33). S = √(Σ_g π_g · MSE̅_g) sobre los grupos de bandas unidas,
  con π_g la suma de sus π_b y MSE̅_g la media de MSE_e de sus evaluaciones. Unión: mientras haya más de un grupo y
  alguno tenga < ``BANDA_MIN_EVAL`` evaluaciones, el primero de ellos (desde la banda más cercana a 0) se une con su
  vecino más cercano a 0, y el primero con el segundo («la de 0-10 km, con la de 10-25»); pregunta VAL-P3. Las
  evaluaciones que cuentan son las de la partición de la fila (P1, P2 o las dos en el agregado) y del estrato (MC-33: π
  nacional del uso, unión dentro del estrato) con valor finito de esa métrica. CD y EX se agregan con el cuadrado
  (MC-29): √(Σ_g π_g · media_g(CD_e²)). **El nivel agudo y la anomalía crónica se agregan como S** (√ de la media
  ponderada por bandas de su MSE_e; pregunta VAL-P2). Sin evaluaciones, NaN.
- VAL-11. **S_par** (§5.3; acuerdo A11). ``puntaje_par`` usa la misma fórmula que ``decision._s_del_grupo``:
  ``S_PAR_PESO``·(S_T,c/mín S_T + S_HR,c/mín S_HR), con los mínimos sobre E0, en el mismo orden de operaciones (una
  prueba compara las dos bit a bit en los casos de ``sintetico.tablas_metricas``). Sin S_HR (lo crónico), S_par = S_T.
  Un mínimo ≤ 0 o un S no finito es un error.
- VAL-12. **Remuestreo** (§5.4; MC-34, D46). ``BOOT_REPLICAS`` réplicas con ``numerico.remuestreo_bloques`` (semilla
  ``SEMILLA``, etiqueta «remuestreo»; las mismas réplicas para todos los usos y grupos) sobre los bloques de P2 con
  estaciones (los valores de ``particiones.bloques_remuestreo``, también los de estaciones sin evaluación). Cada réplica
  toma, por cada vez que sale un bloque, todas las evaluaciones (P1 y P2) de sus estaciones, y rehace la unión de bandas
  con sus conteos, S de cada candidato y variable y el S del grupo con los mínimos de S_par sobre E0 de la réplica.
  MSE_e, CD_e y EX_e son de la evaluación y no se recalculan (el nivel neto crónico tampoco: MC-34 enumera lo que se
  rehace). Sale ``tipos.ESQUEMA_REPLICAS`` sólo con los de E0; un S no finito en una réplica es un error. E0 se
  comprueba tal como llega, antes de usarlo: vacío, con un candidato desconocido, repetido o que no es del uso es un
  ``ValueError`` (no se descarta en silencio; igual en el aviso SINCA, VAL-20). ``bloques`` trae sólo estaciones de
  ``infos`` no excluidas (las de ``particiones.bloques_remuestreo``, PAR-1); un bloque de otra es un error.
- VAL-13. **Regla de soporte** (§0.4.4, §5.5; MC-61, TIP-15). La fracción sin soporte de un candidato en un estrato y
  una partición es la media de ``frac_sin_soporte`` de sus evaluaciones ponderada por ``n_horas`` (= fracción de sus
  horas de prueba). Un estrato es publicable en una partición si A, B y AB tienen evaluaciones y ninguno pasa de
  ``SOPORTE_PCT`` («en más del 50 %»: 0,5 exacto se publica); ``publicable`` va por partición y es igual para todos los
  candidatos. El estrato se publica sólo si es publicable en P1, en P2 y en el agregado: si no, sus filas de las tres
  particiones llevan S, CD, EX, nivel y anomalía en NaN (§0.4.4: «no se publica ni entra a una compuerta»; tampoco las
  diferencias entre candidatos), y de él sólo sale la fracción de cada candidato (``fracciones_sin_soporte``). La regla
  no se aplica al estrato nacional (MC-61): siempre publicable. Una macrozona sin evaluaciones lleva n = 0,
  ``publicable`` False y S NaN (A13).
- VAL-14. **Conteos** (§6.1, TIP-10). ``n_evaluaciones`` y ``n_estaciones`` de una fila cuentan las evaluaciones y las
  estaciones distintas con valor finito de la métrica principal de la variable (S, o EX si la variable no tiene S): son
  las «estaciones evaluables» de MZ. Los conteos se publican también en un estrato no publicado: son conteos de
  estaciones, no resultados de un candidato.
- VAL-15. **Las mismas evaluaciones para todos los candidatos** (la comparación es entre candidatos en las mismas
  evaluaciones, P23). Por (uso, variable), cada candidato del uso debe traer el mismo conjunto de (código, partición), y
  cada métrica debe ser finita en las mismas; si no, ValueError. Así ``publicable`` y ``n_estaciones`` son iguales para
  todos (DEC-4, que lo exige a todos los candidatos con filas). Quien arma las evaluaciones (``orquestacion``) debe usar
  las mismas horas emparejadas para todos los candidatos del uso (pedido a I20): un candidato fuera de E0 por finitud
  con otras horas haría fallar esta comprobación.
- VAL-16. **Estaciones** (D9, D16, D34). Una evaluación de una estación excluida o desconocida es un error. Las de una
  estación fuera de la grilla (no excluida y sin celda, NAS-17) se descartan de todo y se cuentan aparte (D34
  [delegada]; con la lectura (b) de P46 que rige). Una estación sin macrozona cuenta sólo en lo nacional y en los
  estratos que no son de macrozona, y se cuenta aparte. Toda macrozona pasa por ``tipos.macrozona_o_ninguna``: None,
  «sin_region» e «insular» son «sin macrozona» (D9, D16), y un nombre que no es de ``tipos.MACROZONAS`` es un error
  (vale en los estratos, en lo crónico y en la red SINCA).
- VAL-17. **Estratos descriptivos** (§5.5; MC-62). Conjunto (V, V2, N); altitud de z_s en < 500, [500, 2.000] y > 2.000
  m (``ESTRATO_ALTITUD_M``; sin z_s finita, en ninguno); período 2000-2009 y 2010-2026 (``ESTRATO_PERIODOS``), con las
  evaluaciones calculadas sólo con las horas del período, que pasa quien llama en ``periodos`` (sin ellas no se forma y
  se declara); tipo y propietario, con los textos del catálogo, si alguna estación los trae; y «con indicativo OMM»
  (``omm`` True; sólo ese estrato, el que nombra el texto; si ninguna estación trae el dato, no se forma y se declara).
  Las macrozonas van sólo en las variables de MZ del grupo (DEC-2 rechaza una fila de macrozona en otra variable) y
  siempre las cinco (A13); los demás estratos, en todas las variables del grupo. Las variables del grupo sin filas de
  macrozona (el EX de Td ambiental, el CD de T y HR del agudo, el EX de ``temp_media`` del crónico, …) se declaran en
  ``attrs["declaraciones"]["variables_sin_estrato_macrozona"]``: §5.5 («Estratos: macrozona; conjunto…») no restringe
  las variables, y la omisión queda a la vista hasta que el coordinador elija (pregunta VAL-P7). «En el viento, CD y
  EX por altitud» queda cubierto: las filas de altitud de (u, v) traen CD y EX.
- VAL-18. **Réplica con N** (§5.5). Las evaluaciones de las estaciones del conjunto N, con las bandas, los π, la TF y
  los motivos de E0 de la decisión completa (el entrenamiento sigue con todas), rehacen la tabla publicada y el
  remuestreo (sobre los bloques de P2 con estaciones N: los de todas las estaciones N de ``bloques``, también las que no
  tienen evaluaciones, como VAL-12), y la decisión se repite con la función que pasa quien llama
  (``decision`` es de la capa 2 y no está entre las dependencias de este módulo). Es descriptiva: un ``ValueError`` de
  la decisión da «no_decidible», sin el texto del error.
- VAL-19. **SINCA** (§5.6; A12 revisado, D47-D50, MC-10). Se usan sólo las filas ``valido`` de
  ``tipos.ESQUEMA_SINCA_HORA``; ``h`` es el fin u del intervalo [u − 1, u], y la media SINCA se compara con la media del
  producto en u − 1 y u (las dos finitas). La hora se asigna, para el día civil y la celda del ciclo, a u − 1 (el
  intervalo cae entero en el día de su comienzo). TEMP con T, RHUM con HR, WSPD con la media de la rapidez del producto
  en u − 1 y u, y (WSPD, WDIR) con la media del vector (u, v) del producto: el vector SINCA es (−WSPD·sen DD, −WSPD·cos
  DD) (DD «desde», como la DMC; con WSPD = 0 el vector es (0, 0) sin mirar DD, como la calma sin dirección de §2.4).
  D47-D50 los aplica ``sinca_meteo``; aquí se comprueban sus consecuencias en la tabla: sólo TEMP, RHUM, WSPD y WDIR,
  una sola ``serie`` por estación × variable, ninguna hora repetida y, en las filas válidas, WDIR en [``QDD_MIN``,
  ``QDD_MAX``] y WSPD ≥ ``QFF_MIN``. Las métricas son las de ``evaluacion`` (§5.2 y §5.8) por estación, uso, candidato y
  lugar (celda o punto), y se resumen en la red sin pesos de banda (√ de la media de MSE_e; CD y EX con el cuadrado; MAE
  y sesgo con la media): π describe a la población frente a las estaciones DMC, no a la red SINCA (pregunta VAL-P6).
  Terciles: de los valores de ``tpi`` de las estaciones de la serie (las sin TPI finito, en ninguno), con los cortes en
  los cuantiles 1/3 y 2/3 sin interpolar; los empates quedan juntos. Crónico: con ``macrozonas`` (estación →
  macrozona, para cada estación con una evaluación crónica de T; una que falta es un error) como VAL-5, con cada valor
  por ``tipos.macrozona_o_ninguna`` (VAL-16). La macrozona heredada de una celda con ``cod_comuna`` ≤ 0 no se reconoce
  por su nombre: quien llama la da con ``tipos.macrozona_de_celda`` de la celda de la estación SINCA (D20; pedido a
  I20). Sin ``macrozonas`` no se calcula y se declara. Los descriptivos de VAL-21 de cada variable también se resumen en
  la red: con la media, y «ex_tmax_tmin» con el cuadrado.
- VAL-20. **Aviso SINCA del 15 %** (§5.6). Por (uso, grupo) con variables SINCA, en la celda y en el punto: el puntaje
  del grupo en la red (S_par de §5.3 con los mínimos sobre E0 en lo ambiental y lo agudo; el único S en (u, v) y en lo
  crónico). Hay aviso si el del ganador supera en más de ``SINCA_AVISO_PCT`` % al menor de los demás candidatos de E0
  (la lectura más estricta de «el segundo»; pregunta VAL-P5), en la celda o en el punto. «En más de 15 %» es «>»: el
  ganador en 1,15 veces exactas el segundo no da aviso (1 + 15/100 es 1,15 exacto en float64; una prueba arma ese
  borde). Sin puntaje finito para todos los de E0, el aviso de ese lugar es None (no evaluable). p no tiene SINCA. No
  cambia ninguna decisión. E0 se comprueba como en VAL-12, y un (uso, grupo) de ``ganadores`` sin E0 es un error.
- VAL-21. **Descriptivos** (§5.2: «El cociente de amplitudes se informa aparte»; §5.8: «Tmáx y Tmín quedan
  descriptivos» y «Descriptivos: el sesgo condicional … y el acierto de días»). ``evaluacion`` los devuelve en
  ``descriptivos`` (``descriptivos_de``: «cociente_amplitudes» en las variables con CD; «sesgo_sobre_q_alto»,
  «sesgo_bajo_q_bajo» y «acierto» en las de EX; «ex_tmax_tmin» en ``temp_media`` del agudo), ``filas_descriptivas`` los
  pone en filas y ``tabla_descriptivos`` publica ``COLUMNAS_DESCRIPTIVOS`` (``validacion/descriptivos.parquet``; pedido
  al coordinador: ``ESQUEMA_DESCRIPTIVOS_PUB`` en ``tipos``): estrato nacional, por variable, candidato, partición (P1,
  P2 y el agregado) y descriptivo. Se agregan con los π_b del uso y la unión de bandas de VAL-10: el cociente, los
  sesgos y el acierto con la media ponderada Σ_g π_g · media_g(x) (sin raíz: un sesgo puede ser negativo), y
  «ex_tmax_tmin», que es un EX, con el cuadrado (MC-29); pregunta VAL-P8. Como en VAL-15, cada candidato trae un valor
  finito de cada descriptivo en las mismas evaluaciones (las demás no cuentan en ``n_evaluaciones``). No entran a
  ninguna compuerta (DEC-2 no los lee); la regla de soporte no se aplica a lo nacional (MC-61).
Preguntas al autor (cita y propuesta, en COORDINACION_M1.md por medio del coordinador): VAL-P1 (centrado crónico con P1
y P2 juntas), VAL-P2 (agregación del nivel agudo y de la anomalía), VAL-P3 (orden de la unión de bandas), VAL-P4
(cuantiles de §5.8), VAL-P5 (el «segundo» del aviso SINCA), VAL-P6 (red SINCA sin pesos y TPI de los terciles), VAL-P7
(macrozona en las variables que no son de MZ) y VAL-P8 (series y agregación de los descriptivos). Mientras no haya
respuesta rige lo que dice cada lectura.
Pedidos. Al coordinador: ``ESQUEMA_DESCRIPTIVOS_PUB``, ``ESQUEMA_SOPORTE_PUB`` y ``ESQUEMA_SINCA_PUB`` en ``tipos`` (hoy
``COLUMNAS_DESCRIPTIVOS``, ``COLUMNAS_SOPORTE`` y ``COLUMNAS_SINCA``) y los estratos descriptivos en ``tipos.Estrato``.
A I20 (``orquestacion``): las mismas horas emparejadas para todos los candidatos del uso (VAL-15); juntar los
``descriptivos`` de cada ``evaluacion`` con ``filas_descriptivas`` y escribir ``tabla_descriptivos`` como
``validacion/descriptivos.parquet`` por medio de ``salidas``; y dar las ``macrozonas`` SINCA con
``tipos.macrozona_de_celda`` (VAL-19).
Depende de: tipos, constantes, umbrales (un objeto con ``.a`` y ``.frac``; no hace falta importarlo), numerico,
particiones.
"""
from __future__ import annotations

import math
import zoneinfo
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping

import numpy as np
import pandas as pd

from meteo_combinada import constantes, numerico, particiones, tipos
from meteo_combinada.tipos import Candidato, Grupo, Particion, Uso, VariableMetrica

# ---------------------------------------------------------------------------------------------------------------
# Rótulos (VAL-1; TIP-15)
# ---------------------------------------------------------------------------------------------------------------
V_T = VariableMetrica.T.value
V_TD = VariableMetrica.TD.value
V_HR = VariableMetrica.HR.value
V_RAPIDEZ = VariableMetrica.RAPIDEZ.value
V_UV = VariableMetrica.UV.value
V_P = VariableMetrica.P.value
V_TEMP_MEDIA = VariableMetrica.TEMP_MEDIA.value
V_HR_MEDIA = VariableMetrica.HR_MEDIA.value
VARIABLES_HORARIAS = (V_T, V_TD, V_HR, V_RAPIDEZ, V_UV, V_P)
VARIABLES_DIARIAS = (V_TEMP_MEDIA, V_HR_MEDIA)
_ORDEN_VARIABLES = tuple(v.value for v in VariableMetrica)

# VAL-8: clave de las horas válidas de cada variable (sufijos de ``valido_*`` de ESQUEMA_QC_ESTACION).
CLAVES_HORAS = ("T", "Td", "HR", "viento", "p")
HORAS_DE = MappingProxyType({V_T: "T", V_TD: "Td", V_HR: "HR", V_RAPIDEZ: "viento", V_UV: "viento", V_P: "p",
                             V_TEMP_MEDIA: "T", V_HR_MEDIA: "HR"})

P1, P2, AGREGADO = Particion.P1.value, Particion.P2.value, tipos.PARTICION_AGREGADO
PARTICIONES = (P1, P2, AGREGADO)                     # MC-61, TIP-15

ESTRATO_NACIONAL = tipos.Estrato.NACIONAL.value
ESTRATO_MACROZONA = tipos.Estrato.MACROZONA.value
# Estratos descriptivos de §5.5 (VAL-17): pedido al coordinador para sumarlos a ``tipos.Estrato``.
ESTRATO_CONJUNTO = "conjunto"
ESTRATO_ALTITUD = "altitud"
ESTRATO_PERIODO = "periodo"
ESTRATO_TIPO = "tipo"
ESTRATO_PROPIETARIO = "propietario"
ESTRATO_OMM = "omm"
ESTRATOS = (ESTRATO_NACIONAL, ESTRATO_MACROZONA, ESTRATO_CONJUNTO, ESTRATO_ALTITUD, ESTRATO_PERIODO, ESTRATO_TIPO,
            ESTRATO_PROPIETARIO, ESTRATO_OMM)
VALOR_NACIONAL = ""
VALOR_OMM = "con_indicativo_omm"
MACROZONAS = tipos.MACROZONAS

_A, _B, _AB, _C, _CE = (c.value for c in (Candidato.A, Candidato.B, Candidato.AB, Candidato.C, Candidato.C_EST))
NUCLEO = (_A, _B, _AB)                               # §4.2: los candidatos del núcleo (soporte, §0.4.4)
CANDIDATOS_USO = MappingProxyType({Uso.AMBIENTAL: (_A, _B, _AB, _C), Uso.AGUDO: (_A, _B, _AB, _C),
                                   Uso.CRONICO: (_A, _B, _AB, _CE)})                     # §6.1 (= decision)

# Columnas publicadas y columnas de la evaluación de cada una (VAL-1). La primera es la métrica principal (VAL-14).
COLUMNAS_PUB = ("S", "CD", "EX", "nivel", "anomalia")
_CON_CUADRADO = ("CD", "EX")                          # MC-29
COLUMNAS_METRICA = ("mse_h", "mae_h", "sesgo_h", "mse_dia", "mse_estrato", "mse_anual_neto", "mse_anomalia", "cd",
                    "ex")


def _congelar(d: Mapping[str, Mapping[str, str]]) -> Mapping[str, Mapping[str, str]]:
    return MappingProxyType({v: MappingProxyType(dict(m)) for v, m in d.items()})


_DIARIA = {"S": "mse_estrato", "EX": "ex", "nivel": "mse_dia"}
METRICAS = MappingProxyType({
    (Uso.AMBIENTAL, Grupo.T_TD): _congelar({V_T: {"S": "mse_h", "CD": "cd", "EX": "ex"},
                                            V_TD: {"S": "mse_h", "EX": "ex"},
                                            V_HR: {"S": "mse_h", "CD": "cd"}}),
    (Uso.AMBIENTAL, Grupo.U_V): _congelar({V_RAPIDEZ: {"S": "mse_h", "CD": "cd", "EX": "ex"},
                                           V_UV: {"S": "mse_h"}}),
    (Uso.AMBIENTAL, Grupo.P): _congelar({V_P: {"S": "mse_h", "CD": "cd"}}),
    (Uso.AGUDO, Grupo.T_TD): _congelar({V_T: {"S": "mse_h", "CD": "cd"}, V_HR: {"S": "mse_h", "CD": "cd"},
                                        V_TEMP_MEDIA: _DIARIA, V_HR_MEDIA: _DIARIA}),
    (Uso.CRONICO, Grupo.T_TD): _congelar({V_T: {"S": "mse_anual_neto", "CD": "cd", "anomalia": "mse_anomalia"},
                                          V_TEMP_MEDIA: {"EX": "ex"}}),
})
# Variables del S del grupo y de MZ (§5.3, §6.1; = decision.VARIABLES[...].S y .MZ, comparadas en una prueba).
S_DEL_GRUPO = MappingProxyType({
    (Uso.AMBIENTAL, Grupo.T_TD): (V_T, V_HR), (Uso.AMBIENTAL, Grupo.U_V): (V_UV,), (Uso.AMBIENTAL, Grupo.P): (V_P,),
    (Uso.AGUDO, Grupo.T_TD): (V_TEMP_MEDIA, V_HR_MEDIA), (Uso.CRONICO, Grupo.T_TD): (V_T,)})
VARIABLES_MZ = MappingProxyType({
    (Uso.AMBIENTAL, Grupo.T_TD): (V_T, V_HR), (Uso.AMBIENTAL, Grupo.U_V): (V_UV, V_RAPIDEZ),     # D43
    (Uso.AMBIENTAL, Grupo.P): (V_P,), (Uso.AGUDO, Grupo.T_TD): (V_TEMP_MEDIA, V_HR_MEDIA),
    (Uso.CRONICO, Grupo.T_TD): (V_T,)})
GRUPO_DE = MappingProxyType({(u, v): g for (u, g), m in METRICAS.items() for v in m})


def _columnas_de(uso: Uso, variable: str) -> frozenset[str]:
    return frozenset(METRICAS[(uso, GRUPO_DE[(uso, variable)])][variable].values())


METODO_CUANTIL = "inverted_cdf"                       # VAL-7 (como MC-48 y DEC-12)
N_TERCILES = 3  # no-umbral: los terciles de TPI de §5.6 son tres grupos, no un umbral
LUGARES = ("celda", "punto")                          # §5.6: «en la celda y en el punto»
ESTRATO_RED = "red"
ESTRATO_TERCIL = "tercil_tpi"
_NAN = float("nan")
_EPOCA_H = np.datetime64("2000-01-01T00", "h")
_EPOCA_DIA = pd.Timestamp("2000-01-01")


# ---------------------------------------------------------------------------------------------------------------
# Ayudas
# ---------------------------------------------------------------------------------------------------------------
def _uso(uso) -> Uso:
    return Uso(uso)


def _variable(variable) -> str:
    return VariableMetrica(variable).value


def _horas(h, nombre: str = "h") -> np.ndarray:
    a = np.asarray(h)
    if a.ndim != 1:
        raise ValueError(f"{nombre}: se espera un arreglo de una dimensión")
    if a.dtype == bool or not np.issubdtype(a.dtype, np.integer):
        if a.size:
            raise ValueError(f"{nombre}: las horas son enteros desde 2000-01-01T00:00Z (§2.1 del diseño)")
    return a.astype(np.int64)


def _reales(x, n: int, nombre: str) -> np.ndarray:
    a = np.asarray(x, dtype=np.float64)
    if a.shape != (n,):
        raise ValueError(f"{nombre}: se esperan {n} valores en una dimensión, no la forma {a.shape}")
    return a


def _vector(x, n: int, nombre: str) -> np.ndarray:
    """(u, v) en una matriz n × 2: acepta una tupla (u, v) de dos arreglos o la matriz n × 2."""
    if isinstance(x, tuple) and len(x) == 2:
        a = np.column_stack([np.asarray(x[0], dtype=np.float64), np.asarray(x[1], dtype=np.float64)])
    else:
        a = np.asarray(x, dtype=np.float64)
    if a.shape != (n, 2):
        raise ValueError(f"{nombre}: el viento va como (u, v), {n} × 2; no la forma {a.shape}")
    return a


def _entero(umbrales, ident: str) -> int:
    v = umbrales.a(ident)
    if isinstance(v, bool) or not isinstance(v, (int, np.integer)):
        raise ValueError(f"{ident} debe ser entero: {v!r}")
    return int(v)


def _finito(x) -> bool:
    return isinstance(x, (int, float, np.integer, np.floating)) and not isinstance(x, bool) and math.isfinite(x)


def _texto_no_vacio(x) -> bool:
    return isinstance(x, str) and bool(x.strip())


def _cuantil(x: np.ndarray, q_pct) -> float:
    return float(np.quantile(x, q_pct / 100, method=METODO_CUANTIL))


def _macrozona(nombre, origen: str) -> str | None:
    """VAL-16 (D9, D16): la macrozona por ``tipos.macrozona_o_ninguna`` (None, «sin_region» e «insular» son None); un
    nombre que no es de ``tipos.MACROZONAS`` es un error."""
    if nombre is not None and not isinstance(nombre, str):
        raise ValueError(f"{origen}: la macrozona es un texto o None, no {nombre!r}")
    z = tipos.macrozona_o_ninguna(nombre)
    if z is not None and z not in MACROZONAS:
        raise ValueError(f"{origen}: {z!r} no es una macrozona de {MACROZONAS} ni de "
                         f"{sorted(tipos.MACROZONAS_NINGUNA)} (D9, D16)")
    return z


def _e0_del_uso(e0, uso: Uso, quien: str) -> tuple[str, ...]:
    """VAL-12, VAL-20: E0 tal como llega, comprobado antes de usarlo, en el orden de ``CANDIDATOS_USO``."""
    if isinstance(e0, (str, bytes)) or not isinstance(e0, Iterable):
        raise ValueError(f"{quien}: E0 es una lista de candidatos, no {e0!r}")
    dados = []
    for x in e0:
        try:
            dados.append(Candidato(x).value)
        except ValueError:
            raise ValueError(f"{quien}: {x!r} no es un candidato") from None
    ajenos = [c for c in dados if c not in CANDIDATOS_USO[uso]]
    repetidos = sorted({c for c in dados if dados.count(c) > 1})
    if not dados or ajenos or repetidos:
        raise ValueError(f"{quien}: E0 vacío, con candidatos que no son de lo {uso.value} ({ajenos}) o repetidos "
                         f"({repetidos})")
    return tuple(c for c in CANDIDATOS_USO[uso] if c in dados)


# ---------------------------------------------------------------------------------------------------------------
# Día civil (VAL-3)
# ---------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True, eq=False)
class _Calendario:
    h0: int
    dia: np.ndarray          # d2000 de la fecha civil de la hora h0 + i
    posicion: np.ndarray     # horas desde la primera hora UTC del día civil
    duracion: np.ndarray     # horas del día civil (23, 24 o 25)

    def cubre(self, hmin: int, hmax: int) -> bool:
        return self.h0 <= hmin and hmax < self.h0 + self.dia.size


_CALENDARIOS: dict[str, _Calendario] = {}
_MARGEN_H = 2 * numerico.PERIODO_DIA_H


def _zona_iana(zona: str) -> zoneinfo.ZoneInfo:
    if not isinstance(zona, str) or not zona:
        raise ValueError(f"zona IANA inválida: {zona!r}")
    if zoneinfo.TZPATH:
        raise RuntimeError("la base de zonas debe ser sólo la del paquete tzdata (§0, regla 3 del diseño; entorno la "
                           "fija al importarse): zoneinfo.TZPATH no está vacío (VAL-3)")
    return zoneinfo.ZoneInfo(zona)


def _calendario(zona: str, hmin: int, hmax: int) -> _Calendario:
    previo = _CALENDARIOS.get(zona)
    if previo is not None and previo.cubre(hmin, hmax):
        return previo
    if previo is not None:
        hmin = min(hmin, previo.h0)
        hmax = max(hmax, previo.h0 + previo.dia.size - 1)
    tz = _zona_iana(zona)
    hs = np.arange(hmin - _MARGEN_H, hmax + _MARGEN_H + 1, dtype=np.int64)
    utc = pd.DatetimeIndex(_EPOCA_H + hs).tz_localize("UTC")
    local = utc.tz_convert(tz).tz_localize(None)
    dia = (local.normalize() - _EPOCA_DIA).days.to_numpy(dtype=np.int64)
    if (np.diff(dia) < 0).any():
        raise RuntimeError(f"{zona}: la fecha civil retrocede entre dos horas UTC seguidas")
    inicios = np.r_[0, np.flatnonzero(np.diff(dia)) + 1]
    largos = np.diff(np.r_[inicios, dia.size])
    # El primero y el último días de la tabla pueden estar incompletos: se recortan.
    corte0, corte1 = int(inicios[1]), int(inicios[-1])
    dia, largos_dia = dia[corte0:corte1], largos[1:-1]
    rep = np.repeat(np.arange(largos_dia.size), largos_dia)
    inicio_local = np.r_[0, np.cumsum(largos_dia)[:-1]]
    posicion = np.arange(dia.size, dtype=np.int64) - inicio_local[rep]
    calendario = _Calendario(h0=int(hs[corte0]), dia=dia, posicion=posicion, duracion=largos_dia[rep].astype(np.int64))
    _CALENDARIOS[zona] = calendario
    return calendario


def dia_civil(h, zona: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """VAL-3: (d2000 de la fecha civil, posición en el día en horas, duración del día en horas) de cada hora UTC."""
    h = _horas(h)
    if h.size == 0:
        vacio = np.zeros(0, dtype=np.int64)
        return vacio, vacio.copy(), vacio.copy()
    cal = _calendario(zona, int(h.min()), int(h.max()))
    i = h - cal.h0
    return cal.dia[i], cal.posicion[i], cal.duracion[i]


def _fecha(dias: np.ndarray) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(_EPOCA_DIA + pd.to_timedelta(np.asarray(dias, dtype=np.int64), unit="D"))


def _unicas(h: np.ndarray, nombre: str) -> None:
    if np.unique(h).size != h.size:
        raise ValueError(f"{nombre}: horas repetidas")


def dias_validos(h, valido, zona: str, umbrales) -> pd.DataFrame:
    """§5.2 (VAL-3, MC-27): por día civil con alguna hora válida, ``dia`` (d2000 de la fecha civil), ``n_horas``,
    ``duracion`` (23, 24 o 25), ``hueco`` (máximo circular) y ``valido`` (≥ DIA_MIN_H horas y hueco ≤ DIA_HUECO_H)."""
    h = _horas(h)
    _unicas(h, "dias_validos")
    valido = np.asarray(valido)
    if valido.shape != h.shape or valido.dtype != bool:
        raise ValueError("dias_validos: «valido» es un arreglo booleano alineado con h")
    hv = np.sort(h[valido])
    columnas = {"dia": "int32", "n_horas": "int32", "duracion": "int8", "hueco": "int8", "valido": "bool"}
    if hv.size == 0:
        return pd.DataFrame({c: pd.Series(dtype=t) for c, t in columnas.items()})
    dia, pos, dur = dia_civil(hv, zona)
    dias, inicio, cuenta = np.unique(dia, return_index=True, return_counts=True)
    fin = inicio + cuenta - 1
    salto = np.zeros(hv.size, dtype=np.int64)
    mismo = np.r_[False, dia[1:] == dia[:-1]]
    salto[mismo] = np.diff(pos)[mismo[1:]]
    interno = np.maximum.reduceat(salto, inicio)
    vuelta = pos[inicio] + dur[inicio] - pos[fin]
    hueco = np.maximum(interno, vuelta)
    ok = (cuenta >= _entero(umbrales, "DIA_MIN_H")) & (hueco <= _entero(umbrales, "DIA_HUECO_H"))
    return pd.DataFrame({"dia": dias.astype(np.int32), "n_horas": cuenta.astype(np.int32),
                         "duracion": dur[inicio].astype(np.int8), "hueco": hueco.astype(np.int8), "valido": ok})


_COLUMNAS_DIARIAS = {"dia": "int32", "anio": "int16", "mes": "int8", "n_horas": "int32", "pred_media": "float64",
                     "obs_media": "float64", "pred_max": "float64", "obs_max": "float64", "pred_min": "float64",
                     "obs_min": "float64"}


def _emparejadas(pred, obs) -> np.ndarray:
    if pred.ndim == 2:
        return np.isfinite(pred).all(axis=1) & np.isfinite(obs).all(axis=1)
    return np.isfinite(pred) & np.isfinite(obs)


def medias_diarias(h, pred, obs, zona: str, umbrales) -> pd.DataFrame:
    """VAL-3: por día civil válido, la media, el máximo y el mínimo del producto y de la observación en las horas
    emparejadas, con el año y el mes civiles. Una fila por día válido, en orden de ``dia``."""
    h = _horas(h)
    _unicas(h, "medias_diarias")
    pred, obs = _reales(pred, h.size, "pred"), _reales(obs, h.size, "obs")
    par = _emparejadas(pred, obs)
    tabla = dias_validos(h, par, zona, umbrales)
    validos = tabla.loc[tabla["valido"], "dia"].to_numpy(dtype=np.int64)
    if validos.size == 0:
        return pd.DataFrame({c: pd.Series(dtype=t) for c, t in _COLUMNAS_DIARIAS.items()})
    hp, pp, op = h[par], pred[par], obs[par]
    dia, _, _ = dia_civil(hp, zona)
    dentro = np.isin(dia, validos)
    dia, pp, op = dia[dentro], pp[dentro], op[dentro]
    orden = np.argsort(dia, kind="stable")
    dia, pp, op = dia[orden], pp[orden], op[orden]
    dias, inicio, cuenta = np.unique(dia, return_index=True, return_counts=True)
    inv = np.repeat(np.arange(dias.size), cuenta)
    fechas = _fecha(dias)
    return pd.DataFrame({
        "dia": dias.astype(np.int32), "anio": fechas.year.to_numpy().astype(np.int16),
        "mes": fechas.month.to_numpy().astype(np.int8), "n_horas": cuenta.astype(np.int32),
        "pred_media": np.bincount(inv, weights=pp) / cuenta, "obs_media": np.bincount(inv, weights=op) / cuenta,
        "pred_max": np.maximum.reduceat(pp, inicio), "obs_max": np.maximum.reduceat(op, inicio),
        "pred_min": np.minimum.reduceat(pp, inicio), "obs_min": np.minimum.reduceat(op, inicio)})


def _exigir_columnas(df, columnas, nombre: str) -> None:
    faltan = [c for c in columnas if c not in df.columns]
    if faltan:
        raise ValueError(f"{nombre}: faltan las columnas {faltan}")


# ---------------------------------------------------------------------------------------------------------------
# §5.2: métricas
# ---------------------------------------------------------------------------------------------------------------
def metricas_horarias(pred, obs, variable) -> dict:
    """§5.2 (VAL-2): n_horas emparejadas, MSE, RMSE, MAE y sesgo (producto − observación). En «uv», ``pred`` y ``obs``
    son (u, v): RMSE vectorial, MAE del módulo del error vectorial y sesgo de la rapidez."""
    v = _variable(variable)
    if v in VARIABLES_DIARIAS:
        raise ValueError(f"metricas_horarias: {v} es diaria (§5.2)")
    if v == V_UV:
        n = len(pred[0]) if isinstance(pred, tuple) else np.asarray(pred).shape[0]
        p, o = _vector(pred, n, "pred"), _vector(obs, n, "obs")
        par = _emparejadas(p, o)
        p, o = p[par], o[par]
        e2 = np.sum((p - o) ** 2, axis=1)
        mae = np.sqrt(e2)
        sesgo = np.hypot(p[:, 0], p[:, 1]) - np.hypot(o[:, 0], o[:, 1])
    else:
        p = np.asarray(pred, dtype=np.float64)
        o = _reales(obs, p.size, "obs")
        p = _reales(p, o.size, "pred")
        par = _emparejadas(p, o)
        d = p[par] - o[par]
        e2, mae, sesgo = d ** 2, np.abs(d), d
    n = int(par.sum())
    if n == 0:
        return {"variable": v, "n_horas": 0, "mse": _NAN, "rmse": _NAN, "mae": _NAN, "sesgo": _NAN}
    mse = float(np.mean(e2))
    return {"variable": v, "n_horas": n, "mse": mse, "rmse": math.sqrt(mse), "mae": float(np.mean(mae)),
            "sesgo": float(np.mean(sesgo))}


def _diario(diario) -> pd.DataFrame:
    _exigir_columnas(diario, ("anio", "mes", "pred_media", "obs_media"), "diario")
    return diario


def nivel_diario(diario) -> float:
    """VAL-4: MSE de las medias diarias (el nivel agudo, columna ``mse_dia``); NaN sin días."""
    d = _diario(diario)
    if len(d) == 0:
        return _NAN
    x = d["pred_media"].to_numpy(np.float64) - d["obs_media"].to_numpy(np.float64)
    return float(np.mean(x ** 2))


def desviacion_estrato(diario, umbrales) -> float:
    """§5.2, agudo (VAL-4): MSE_e de la desviación dentro del estrato estación × año × mes, con los estratos de
    ≥ AGUDO_MIN_DIAS días válidos. ``diario``: la salida de ``medias_diarias`` (una evaluación). NaN sin estratos."""
    d = _diario(diario)
    if len(d) == 0:
        return _NAN
    clave = d["anio"].to_numpy(np.int64) * 100 + d["mes"].to_numpy(np.int64)
    _, inv, cuenta = np.unique(clave, return_inverse=True, return_counts=True)
    entra = cuenta[inv] >= _entero(umbrales, "AGUDO_MIN_DIAS")
    if not entra.any():
        return _NAN
    p = d["pred_media"].to_numpy(np.float64)
    o = d["obs_media"].to_numpy(np.float64)
    dp = p - (np.bincount(inv, weights=p) / cuenta)[inv]
    do = o - (np.bincount(inv, weights=o) / cuenta)[inv]
    return float(np.mean((dp - do)[entra] ** 2))


def anios_validos(diario, umbrales) -> dict[int, float]:
    """VAL-5: {año civil válido (≥ ANIO_MIN_DIAS días válidos): ε = media de las medias diarias del producto − la de
    las observadas}."""
    d = _diario(diario)
    if len(d) == 0:
        return {}
    anio = d["anio"].to_numpy(np.int64)
    p = d["pred_media"].to_numpy(np.float64)
    o = d["obs_media"].to_numpy(np.float64)
    anios, inv, cuenta = np.unique(anio, return_inverse=True, return_counts=True)
    eps = np.bincount(inv, weights=p) / cuenta - np.bincount(inv, weights=o) / cuenta
    minimo = _entero(umbrales, "ANIO_MIN_DIAS")
    return {int(y): float(e) for y, e, n in zip(anios, eps, cuenta) if n >= minimo}


def _anuales(anuales, nombre: str = "anuales") -> dict[int, float]:
    if not isinstance(anuales, Mapping):
        raise TypeError(f"{nombre}: se espera {{año: ε}}")
    salida = {}
    for y, e in anuales.items():
        if isinstance(y, bool) or not isinstance(y, (int, np.integer)) or not _finito(e):
            raise ValueError(f"{nombre}: {{año entero: ε finito}}, no {y!r}: {e!r}")
        salida[int(y)] = float(e)
    return dict(sorted(salida.items()))


def anomalias(anuales, umbrales) -> dict[int, float] | None:
    """VAL-5: a_e,y = ε_e,y − la media de ε_e en sus años válidos de ANOMALIA_PERIODO; None con < MIN_ANIOS_ANOM."""
    a = _anuales(anuales)
    desde, hasta = constantes.valor("ANOMALIA_PERIODO")
    dentro = {y: e for y, e in a.items() if desde <= y <= hasta}
    if len(dentro) < _entero(umbrales, "MIN_ANIOS_ANOM"):
        return None
    media = float(np.mean(list(dentro.values())))
    return {y: e - media for y, e in dentro.items()}


def medias_macrozona_anio(por_evaluacion: Mapping[Any, Mapping[int, float]],
                          macrozona_de: Mapping[Any, str | None]) -> dict[tuple[str, int], float]:
    """VAL-5: {(macrozona, año): media de los valores anuales de las evaluaciones de esa macrozona}. Las evaluaciones
    sin macrozona no entran (D22 (b)). Las sumas van en el orden de las claves, ordenadas."""
    sumas: dict[tuple[str, int], list[float]] = {}
    for clave in sorted(por_evaluacion, key=repr):
        macro = macrozona_de[clave]
        if macro is None:
            continue
        for y, e in _anuales(por_evaluacion[clave]).items():
            sumas.setdefault((macro, y), []).append(e)
    return {k: float(np.mean(v)) for k, v in sorted(sumas.items())}


def anual_neto(anuales, macrozona) -> float:
    """§5.2, crónico (VAL-5): MSE_e del error anual neto de la región, media de (ε_e,y − media de macrozona × año)².
    ``anuales``: {año válido: ε} de una evaluación; ``macrozona``: {año: media de ε de su macrozona}. NaN sin años."""
    a = _anuales(anuales)
    if not a:
        return _NAN
    m = _anuales(macrozona, "macrozona")
    faltan = sorted(set(a) - set(m))
    if faltan:
        raise ValueError(f"anual_neto: sin media de macrozona en los años {faltan}")
    return float(np.mean([(a[y] - m[y]) ** 2 for y in a]))


def anomalia_interanual(anuales, macrozona, umbrales) -> float:
    """§5.2, crónico (VAL-5): MSE_e de la anomalía interanual neta, con ``macrozona`` = {año: media de macrozona de las
    anomalías}. NaN con menos de MIN_ANIOS_ANOM años válidos en ANOMALIA_PERIODO."""
    a = anomalias(anuales, umbrales)
    if a is None:
        return _NAN
    m = _anuales(macrozona, "macrozona")
    faltan = sorted(set(a) - set(m))
    if faltan:
        raise ValueError(f"anomalia_interanual: sin media de macrozona en los años {faltan}")
    return float(np.mean([(a[y] - m[y]) ** 2 for y in a]))


def _celdas_ciclo(h, pred, obs, umbrales) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    h = _horas(h)
    pred, obs = _reales(pred, h.size, "pred"), _reales(obs, h.size, "obs")
    par = _emparejadas(pred, obs)
    hp = h[par]
    mes = (_EPOCA_H + hp).astype("datetime64[M]").astype(np.int64) % 12
    celda = mes * numerico.PERIODO_DIA_H + np.mod(hp, numerico.PERIODO_DIA_H)
    n_celdas = 12 * numerico.PERIODO_DIA_H
    cuenta = np.bincount(celda, minlength=n_celdas)
    ok = cuenta >= constantes.valor("CD_MIN_VALORES")
    with np.errstate(invalid="ignore", divide="ignore"):
        media_p = np.bincount(celda, weights=pred[par], minlength=n_celdas) / cuenta
        media_o = np.bincount(celda, weights=obs[par], minlength=n_celdas) / cuenta
    forma = (12, numerico.PERIODO_DIA_H)
    return ok.reshape(forma), media_p.reshape(forma), media_o.reshape(forma), cuenta.reshape(forma)


def ciclo_diario(h, pred, obs, umbrales) -> float:
    """§5.2, CD_e (VAL-6): √(media sobre las celdas (mes UTC, hora UTC) con ≥ CD_MIN_VALORES de (δ − δ̄_mes)²)."""
    ok, mp, mo, _ = _celdas_ciclo(h, pred, obs, umbrales)
    if not ok.any():
        return _NAN
    delta = np.where(ok, mp - mo, 0.0)
    n_mes = ok.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        media_mes = delta.sum(axis=1) / n_mes
    resto = np.where(ok, delta - media_mes[:, None], 0.0)
    return float(math.sqrt(np.sum(resto ** 2) / ok.sum()))


def cociente_amplitudes(h, pred, obs, umbrales) -> float:
    """VAL-6 (descriptivo): media por mes de la amplitud del ciclo medio del producto / la de la observación."""
    ok, mp, mo, _ = _celdas_ciclo(h, pred, obs, umbrales)
    meses = ok.any(axis=1)
    if not meses.any():
        return _NAN
    amp_p = [np.ptp(mp[m][ok[m]]) for m in np.flatnonzero(meses)]
    amp_o = [np.ptp(mo[m][ok[m]]) for m in np.flatnonzero(meses)]
    denominador = float(np.mean(amp_o))
    return float(np.mean(amp_p)) / denominador if denominador > 0 else _NAN


# ---------------------------------------------------------------------------------------------------------------
# §5.8: extremos
# ---------------------------------------------------------------------------------------------------------------
_COLUMNAS_EXTREMOS = ("media", "maximo", "minimo")


def _extremos_de(tabla, nombre: str) -> dict[str, np.ndarray]:
    _exigir_columnas(tabla, _COLUMNAS_EXTREMOS, nombre)
    salida = {c: np.asarray(tabla[c], dtype=np.float64) for c in _COLUMNAS_EXTREMOS}
    if not all(np.isfinite(x).all() for x in salida.values()):
        raise ValueError(f"{nombre}: sólo días válidos, con valores finitos")
    return salida


def diarios_de(diario) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Las tablas de ``extremos`` (media, máximo y mínimo por día válido) del producto y de la observación."""
    _exigir_columnas(diario, _COLUMNAS_DIARIAS, "diario")
    p = pd.DataFrame({"media": diario["pred_media"], "maximo": diario["pred_max"], "minimo": diario["pred_min"]})
    o = pd.DataFrame({"media": diario["obs_media"], "maximo": diario["obs_max"], "minimo": diario["obs_min"]})
    return p.reset_index(drop=True), o.reset_index(drop=True)


def extremos(diario_pred, diario_obs, uso, variable, umbrales) -> float:
    """§5.8, EX_e (VAL-7). ``diario_pred`` y ``diario_obs``: ``media``, ``maximo`` y ``minimo`` por día válido,
    alineados (``diarios_de``). NaN con menos de EX_MIN_DIAS días."""
    uso, v = _uso(uso), _variable(variable)
    p, o = _extremos_de(diario_pred, "diario_pred"), _extremos_de(diario_obs, "diario_obs")
    if p["media"].size != o["media"].size:
        raise ValueError("extremos: el producto y la observación deben traer los mismos días")
    if p["media"].size < _entero(umbrales, "EX_MIN_DIAS"):
        return _NAN
    if uso is Uso.AMBIENTAL:
        if v in (V_T, V_TD):
            q_alto, q_bajo = constantes.valor("EX_CUANTILES_AMBIENTAL")
            b_calor = _cuantil(p["maximo"], q_alto) - _cuantil(o["maximo"], q_alto)
            b_frio = _cuantil(p["minimo"], q_bajo) - _cuantil(o["minimo"], q_bajo)
            return float(np.mean([abs(b_calor), abs(b_frio)]))
        if v == V_RAPIDEZ:
            q = constantes.valor("EX_CUANTIL_RAPIDEZ")
            return abs(_cuantil(p["maximo"], q) - _cuantil(o["maximo"], q))
        raise ValueError(f"extremos: lo ambiental no tiene EX en {v} (§5.8, §6.1)")
    permitidas = (V_TEMP_MEDIA, V_HR_MEDIA) if uso is Uso.AGUDO else (V_TEMP_MEDIA,)
    if v not in permitidas:
        raise ValueError(f"extremos: lo {uso.value} tiene EX en {permitidas}, no en {v} (§5.8)")
    qs = constantes.valor("EX_CUANTILES_AGUDO")
    return float(np.mean([abs(_cuantil(p["media"], q) - _cuantil(o["media"], q)) for q in qs]))


def extremos_descriptivos(serie_pred, serie_obs, umbrales) -> dict:
    """§5.8, descriptivos: el sesgo condicional en los días con la observación sobre su Q95 o bajo su Q05, y el acierto
    (fracción de los días sobre el Q95 observado en que el producto también pasa su propio Q95). NaN con menos de
    EX_MIN_DIAS días."""
    p = np.asarray(serie_pred, dtype=np.float64)
    o = _reales(serie_obs, p.size, "serie_obs")
    if not (np.isfinite(p).all() and np.isfinite(o).all()):
        raise ValueError("extremos_descriptivos: sólo días válidos, con valores finitos")
    if p.size < _entero(umbrales, "EX_MIN_DIAS"):
        return {"sesgo_sobre_q_alto": _NAN, "sesgo_bajo_q_bajo": _NAN, "acierto": _NAN}
    q_alto, q_bajo = constantes.valor("EX_CUANTILES_DESCRIPTIVOS")
    q_acierto = constantes.valor("EX_ACIERTO_CUANTIL")
    sobre = o > _cuantil(o, q_alto)
    bajo = o < _cuantil(o, q_bajo)
    sobre_acierto = o > _cuantil(o, q_acierto)
    return {"sesgo_sobre_q_alto": float(np.mean((p - o)[sobre])) if sobre.any() else _NAN,
            "sesgo_bajo_q_bajo": float(np.mean((p - o)[bajo])) if bajo.any() else _NAN,
            "acierto": float(np.mean(p[sobre_acierto] > _cuantil(p, q_acierto))) if sobre_acierto.any() else _NAN}


# ---------------------------------------------------------------------------------------------------------------
# Descriptivos de §5.2 y §5.8 (VAL-21)
# ---------------------------------------------------------------------------------------------------------------
D_COCIENTE = "cociente_amplitudes"
D_SESGO_ALTO, D_SESGO_BAJO, D_ACIERTO = "sesgo_sobre_q_alto", "sesgo_bajo_q_bajo", "acierto"
D_EX_TMAX_TMIN = "ex_tmax_tmin"
DESCRIPTIVOS = (D_COCIENTE, D_SESGO_ALTO, D_SESGO_BAJO, D_ACIERTO, D_EX_TMAX_TMIN)
# Cómo se agrega cada uno (VAL-21): media ponderada por bandas, o con el cuadrado (un EX, MC-29).
AGREGACION_DESCRIPTIVO = MappingProxyType({D_COCIENTE: "media", D_SESGO_ALTO: "media", D_SESGO_BAJO: "media",
                                           D_ACIERTO: "media", D_EX_TMAX_TMIN: "cuadrado"})


def descriptivos_de(uso, variable) -> tuple[str, ...]:
    """VAL-21: los descriptivos de una (uso, variable): el cociente de amplitudes donde hay CD, el sesgo condicional y
    el acierto donde hay EX, y Tmáx y Tmín en ``temp_media`` del agudo."""
    uso, v = _uso(uso), _variable(variable)
    if (uso, v) not in GRUPO_DE:
        raise ValueError(f"descriptivos: lo {uso.value} no evalúa {v} (VAL-1)")
    columnas = _columnas_de(uso, v)
    salida = []
    if "cd" in columnas:
        salida.append(D_COCIENTE)
    if "ex" in columnas:
        salida += [D_SESGO_ALTO, D_SESGO_BAJO, D_ACIERTO]
    if (uso, v) == (Uso.AGUDO, V_TEMP_MEDIA):
        salida.append(D_EX_TMAX_TMIN)
    return tuple(salida)


def _descriptivos_extremos(diario_pred, diario_obs, uso: Uso, v: str, umbrales) -> dict:
    """VAL-7: los descriptivos de §5.8 en la serie diaria de su EX (pregunta VAL-P8)."""
    if uso is Uso.AMBIENTAL and v in (V_T, V_TD):
        alta, baja = "maximo", "minimo"
    elif uso is Uso.AMBIENTAL:
        alta = baja = "maximo"                               # la rapidez: el EX es del máximo diario
    else:
        alta = baja = "media"
    d_alta = extremos_descriptivos(diario_pred[alta], diario_obs[alta], umbrales)
    d_baja = extremos_descriptivos(diario_pred[baja], diario_obs[baja], umbrales)
    return {D_SESGO_ALTO: d_alta[D_SESGO_ALTO], D_SESGO_BAJO: d_baja[D_SESGO_BAJO], D_ACIERTO: d_alta[D_ACIERTO]}


# ---------------------------------------------------------------------------------------------------------------
# Una evaluación (§5.2, §5.8)
# ---------------------------------------------------------------------------------------------------------------
def evaluacion(h, pred, obs, *, uso, variable, umbrales, zona: str = tipos.ZONA_CIVIL) -> dict | None:
    """Las métricas de una evaluación e = (estación, partición) para un candidato, un uso y una variable (VAL-1, VAL-2):
    las columnas de métrica de ``tipos.ESQUEMA_EVALUACIONES`` que le tocan (las demás en NaN), ``n_horas``, ``n_dias`` y
    ``n_anios``, ``anuales`` ({año válido: ε}, sólo en T de lo crónico) y ``descriptivos`` ({nombre: valor} de
    ``descriptivos_de``, VAL-21). None si no es evaluable (< MIN_HORAS horas emparejadas). En ``temp_media`` y
    ``hr_media``, ``pred`` y ``obs`` son las series horarias de T y de HR."""
    uso, v = _uso(uso), _variable(variable)
    if (uso, v) not in GRUPO_DE:
        raise ValueError(f"evaluacion: lo {uso.value} no evalúa {v} (VAL-1)")
    h = _horas(h)
    _unicas(h, "evaluacion")
    if v == V_UV:
        pred, obs = _vector(pred, h.size, "pred"), _vector(obs, h.size, "obs")
    else:
        pred, obs = _reales(pred, h.size, "pred"), _reales(obs, h.size, "obs")
    par = _emparejadas(pred, obs)
    n = int(par.sum())
    if n < _entero(umbrales, "MIN_HORAS"):
        return None
    columnas = _columnas_de(uso, v)
    salida: dict[str, Any] = {"n_horas": n, "n_dias": 0, "n_anios": 0, **dict.fromkeys(COLUMNAS_METRICA, _NAN),
                              "anuales": {}, "descriptivos": {}}
    if v in VARIABLES_HORARIAS:
        m = metricas_horarias(pred, obs, v)
        salida.update(mse_h=m["mse"], mae_h=m["mae"], sesgo_h=m["sesgo"])
        if "cd" in columnas:
            salida["cd"] = ciclo_diario(h, pred, obs, umbrales)
            salida["descriptivos"][D_COCIENTE] = cociente_amplitudes(h, pred, obs, umbrales)
    if v == V_UV:
        salida["n_dias"] = int(dias_validos(h, par, zona, umbrales)["valido"].sum())
        return salida
    diario = medias_diarias(h, pred, obs, zona, umbrales)
    salida["n_dias"] = int(len(diario))
    anuales = anios_validos(diario, umbrales)
    salida["n_anios"] = len(anuales)
    diario_p, diario_o = diarios_de(diario)
    if "ex" in columnas:
        salida["ex"] = extremos(diario_p, diario_o, uso, v, umbrales)
        salida["descriptivos"].update(_descriptivos_extremos(diario_p, diario_o, uso, v, umbrales))
    if D_EX_TMAX_TMIN in descriptivos_de(uso, v):
        salida["descriptivos"][D_EX_TMAX_TMIN] = extremos(diario_p, diario_o, Uso.AMBIENTAL, V_T, umbrales)
    if "mse_dia" in columnas:
        salida["mse_dia"] = nivel_diario(diario)
    if "mse_estrato" in columnas:
        salida["mse_estrato"] = desviacion_estrato(diario, umbrales)
    if "mse_anual_neto" in columnas:
        salida["anuales"] = anuales
    return salida


def _codigo_de_pliegue(particion: str, pliegue: str) -> None:
    m = tipos.PATRON_PLIEGUE.fullmatch(pliegue) if isinstance(pliegue, str) else None
    if m is None or m.group("interno") is not None or not m.group("externo").startswith(particion + "-"):
        raise ValueError(f"pliegue {pliegue!r}: se espera un pliegue externo de {particion}")


def fila_evaluacion(metricas: Mapping[str, Any], *, codigo: str, particion: str, pliegue: str, candidato: str, uso,
                    variable, frac_sin_soporte: float) -> dict:
    """Una fila de ``tipos.ESQUEMA_EVALUACIONES`` con las métricas de ``evaluacion``. ``frac_sin_soporte``: la fracción
    de las horas de prueba en que el candidato carece de soporte (Σk = 0, §4.2): en [0, 1] para A, B y AB; NaN o en
    [0, 1] para C y C_est, que no son del núcleo."""
    uso, v = _uso(uso), _variable(variable)
    if not isinstance(codigo, str) or tipos.PATRON_CODIGO.fullmatch(codigo) is None:
        raise ValueError(f"código de estación inválido: {codigo!r}")
    particion = Particion(particion).value
    _codigo_de_pliegue(particion, pliegue)
    candidato = Candidato(candidato).value
    if candidato not in CANDIDATOS_USO[uso]:
        raise ValueError(f"{candidato} no es candidato de lo {uso.value} (§6.1)")
    f = float(frac_sin_soporte)
    if candidato in NUCLEO and not (math.isfinite(f) and 0 <= f <= 1):
        raise ValueError(f"frac_sin_soporte de {candidato} debe estar en [0, 1]: {frac_sin_soporte!r}")
    if math.isfinite(f) and not 0 <= f <= 1:
        raise ValueError(f"frac_sin_soporte fuera de [0, 1]: {frac_sin_soporte!r}")
    fila = {"codigo": codigo, "particion": particion, "pliegue": pliegue, "candidato": candidato, "uso": uso.value,
            "variable": v, "n_horas": int(metricas["n_horas"]), "n_dias": int(metricas["n_dias"]),
            "n_anios": int(metricas["n_anios"])}
    fila.update({c: float(metricas[c]) for c in COLUMNAS_METRICA})
    fila["frac_sin_soporte"] = f
    return fila


def tabla_evaluaciones(filas: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    """``tipos.ESQUEMA_EVALUACIONES`` de las filas de ``fila_evaluacion``, ordenada por código, partición, uso,
    variable y candidato; una evaluación repetida es un error."""
    filas = list(filas)
    esquema = tipos.ESQUEMA_EVALUACIONES
    df = pd.DataFrame(filas, columns=list(esquema)) if filas else tipos.tabla_vacia(esquema)
    df = df.astype(dict(esquema))
    claves = ["codigo", "particion", "uso", "variable", "candidato"]
    if df.duplicated(claves).any():
        raise ValueError("tabla_evaluaciones: evaluación repetida (código, partición, uso, variable, candidato)")
    orden_c = {c.value: i for i, c in enumerate(Candidato)}
    orden_v = {v: i for i, v in enumerate(_ORDEN_VARIABLES)}
    df = df.assign(_c=df["candidato"].map(orden_c), _v=df["variable"].map(orden_v))
    df = df.sort_values(["codigo", "particion", "uso", "_v", "_c"], kind="stable").drop(columns=["_c", "_v"])
    df = df.reset_index(drop=True)
    tipos.validar_esquema(df, esquema, nombre="evaluaciones")
    df.attrs["esquema"] = esquema.version
    return df


def completar_cronico(evaluaciones, anuales: Mapping[tuple[str, str, str], Mapping[int, float]], infos,
                      umbrales) -> pd.DataFrame:
    """§5.2, crónico (VAL-5; D22 (b)): llena ``mse_anual_neto`` y ``mse_anomalia`` de las filas de T de lo crónico.
    ``anuales``: (código, partición, candidato) → {año válido: ε} (de ``evaluacion``). Las medias de macrozona × año
    son por candidato, con P1 y P2 juntas. Las evaluaciones sin macrozona quedan en NaN y se cuentan en
    ``attrs["declaraciones"]``."""
    tipos.validar_esquema(evaluaciones, tipos.ESQUEMA_EVALUACIONES, nombre="evaluaciones")
    df = evaluaciones.copy()
    filas = np.flatnonzero(((df["uso"] == Uso.CRONICO.value) & (df["variable"] == V_T)).to_numpy(dtype=bool))
    previas = df.loc[df.index[filas], ["mse_anual_neto", "mse_anomalia"]].to_numpy(np.float64)
    if np.isfinite(previas).any():
        raise ValueError("completar_cronico: las filas de T de lo crónico ya traen nivel neto o anomalía")
    minimo = _entero(umbrales, "MIN_ANIOS")
    claves, macro = [], {}
    for i in filas:
        r = df.iloc[i]
        clave = (str(r["codigo"]), str(r["particion"]), str(r["candidato"]))
        if clave not in anuales:
            raise ValueError(f"completar_cronico: faltan los años de la evaluación {clave}")
        claves.append((i, clave))
        macro[clave] = _macrozona(infos[clave[0]].macrozona, f"estación {clave[0]}")
    sin_macro = {c[0] for _, c in claves if macro[c] is None}
    neto = np.full(len(df), _NAN)
    anom = np.full(len(df), _NAN)
    for cand in sorted({c[2] for _, c in claves}):
        propias = [(i, c) for i, c in claves if c[2] == cand]
        entran = {c: _anuales(anuales[c]) for _, c in propias
                  if macro[c] is not None and len(_anuales(anuales[c])) >= minimo}
        m_neto = medias_macrozona_anio(entran, macro)
        de_anom = {c: a for c, a in ((c, anomalias(e, umbrales)) for c, e in entran.items()) if a is not None}
        m_anom = medias_macrozona_anio(de_anom, macro)
        for i, c in propias:
            if c not in entran:
                continue
            neto[i] = anual_neto(entran[c], {y: m for (z, y), m in m_neto.items() if z == macro[c]})
            if c in de_anom:
                anom[i] = anomalia_interanual(entran[c], {y: m for (z, y), m in m_anom.items() if z == macro[c]},
                                              umbrales)
    df.loc[df.index[filas], "mse_anual_neto"] = neto[filas]
    df.loc[df.index[filas], "mse_anomalia"] = anom[filas]
    df = df.astype(dict(tipos.ESQUEMA_EVALUACIONES))
    df.attrs = {"esquema": tipos.ESQUEMA_EVALUACIONES.version,
                "declaraciones": {"cronico_sin_macrozona_estaciones": len(sin_macro),
                                  "cronico_sin_macrozona_evaluaciones": sum(1 for _, c in claves if macro[c] is None)}}
    return df


# ---------------------------------------------------------------------------------------------------------------
# §5.3: bandas, pesos y puntaje
# ---------------------------------------------------------------------------------------------------------------
def _cortes(umbrales) -> tuple:
    cortes = tuple(umbrales.a("BANDAS_KM"))
    if not cortes or list(cortes) != sorted(set(cortes)) or cortes[0] <= 0:
        raise ValueError(f"BANDAS_KM debe ser una lista creciente de cortes positivos: {cortes!r}")
    return cortes


def rotulos_bandas(umbrales) -> tuple[str, ...]:
    """«0-10», «10-25», «25-50» y «>50» (§5.3), desde BANDAS_KM."""
    cortes = _cortes(umbrales)
    bordes = (0, *cortes)
    return (*(f"{a}-{b}" for a, b in zip(bordes[:-1], bordes[1:])), f">{cortes[-1]}")


def bandas(distancias_km, umbrales) -> np.ndarray:
    """§5.3 (VAL-8): índice de banda (0 = 0-10 km … 3 = > 50 km), con los bordes inclusivos por arriba."""
    d = np.asarray(distancias_km, dtype=np.float64)
    if np.isnan(d).any() or (d < 0).any():
        raise ValueError("bandas: las distancias son ≥ 0 (infinitas sin estación de entrenamiento)")
    return np.searchsorted(np.asarray(_cortes(umbrales), dtype=np.float64), d, side="left").astype(np.int8)


def bandas_de_pliegues(pliegues, infos, horas_validas: Mapping[str, Mapping[str, float]],
                       umbrales) -> dict[tuple[str, str, str], int]:
    """VAL-8: (código, partición, clave de horas) → banda de la evaluación, para las estaciones de prueba de los
    pliegues externos de P1 y P2. ``horas_validas``: clave de ``CLAVES_HORAS`` → {código: horas válidas}. En memoria:
    nunca se escribe (§0.4.5)."""
    claves = [k for k in CLAVES_HORAS if k in horas_validas]
    if set(horas_validas) - set(CLAVES_HORAS):
        raise ValueError(f"horas_validas: claves {sorted(set(horas_validas) - set(CLAVES_HORAS))}; son {CLAVES_HORAS}")
    salida: dict[tuple[str, str, str], int] = {}
    for pliegue in pliegues:
        if pliegue.externo is not None:
            continue
        particion = Particion(pliegue.particion).value
        for k in claves:
            d = particiones.distancia_entrenamiento_km(pliegue.prueba, pliegue.entrenamiento, infos, horas_validas[k],
                                                       umbrales)
            codigos = sorted(d)
            for c, b in zip(codigos, bandas([d[c] for c in codigos], umbrales)):
                clave = (c, particion, k)
                if clave in salida:
                    raise ValueError(f"bandas_de_pliegues: {c} es de prueba en dos pliegues de {particion}")
                salida[clave] = int(b)
    return salida


def _vector_pi(pi, umbrales) -> np.ndarray:
    rotulos = rotulos_bandas(umbrales)
    if isinstance(pi, Mapping):
        if list(pi) != list(rotulos):
            raise ValueError(f"π: se esperan las bandas {rotulos}, en orden, no {list(pi)}")
        x = np.array([pi[r] for r in rotulos], dtype=np.float64)
    else:
        x = np.asarray(pi, dtype=np.float64)
    if x.shape != (len(rotulos),) or not np.isfinite(x).all() or (x < 0).any():
        raise ValueError(f"π: {len(rotulos)} pesos finitos ≥ 0")
    if not math.isclose(float(x.sum()), 1.0):
        raise ValueError(f"π: los pesos deben sumar 1, no {float(x.sum())!r}")
    return x


def _distancia_minima_km(lat, lon, lat_e, lon_e) -> np.ndarray:
    """Distancia por haversine al punto más cercano (VAL-9); infinita sin puntos."""
    lat, lon = np.asarray(lat, dtype=np.float64), np.asarray(lon, dtype=np.float64)
    if lat.size == 0:
        return np.zeros(0)
    lat_e, lon_e = np.asarray(lat_e, dtype=np.float64), np.asarray(lon_e, dtype=np.float64)
    if lat_e.size == 0:
        return np.full(lat.size, np.inf)
    if not (np.isfinite(lat).all() and np.isfinite(lon).all() and np.isfinite(lat_e).all()
            and np.isfinite(lon_e).all()):
        raise ValueError("distancias: coordenadas no finitas")
    from scipy.spatial import cKDTree

    def unitarios(la, lo):
        fi, la_ = np.radians(la), np.radians(lo)
        return np.column_stack([np.cos(fi) * np.cos(la_), np.cos(fi) * np.sin(la_), np.sin(fi)])

    _, i = cKDTree(unitarios(lat_e, lon_e)).query(unitarios(lat, lon), k=1)
    return numerico.haversine_km(lat, lon, lat_e[i], lon_e[i])


def _estaciones_del_anio(tabla, minimo: float, nombre: str) -> tuple[np.ndarray, np.ndarray]:
    _exigir_columnas(tabla, ("codigo", "lat", "lon", "horas"), nombre)
    horas = np.asarray(tabla["horas"], dtype=np.float64)
    if not np.isfinite(horas).all() or (horas < 0).any():
        raise ValueError(f"{nombre}: horas válidas finitas ≥ 0")
    if pd.Series(tabla["codigo"]).duplicated().any():
        raise ValueError(f"{nombre}: estación repetida")
    entra = horas >= minimo
    return np.asarray(tabla["lat"], dtype=np.float64)[entra], np.asarray(tabla["lon"], dtype=np.float64)[entra]


def _anios_pi() -> tuple[int, ...]:
    desde, hasta = constantes.valor("PI_POB_PERIODO")
    return tuple(range(desde, hasta + 1))


def _pi_de(pesos_por_banda: np.ndarray, umbrales) -> dict[str, float]:
    total = float(pesos_por_banda.sum())
    if not total > 0:
        raise ValueError("π: sin peso positivo")
    return {r: float(x / total) for r, x in zip(rotulos_bandas(umbrales), pesos_por_banda)}


def pi_poblacion(celdas_pobladas, estaciones_por_anio, variable, umbrales) -> dict:
    """§5.3, π^pob (VAL-9). ``celdas_pobladas``: ``anio``, ``lat``, ``lon`` y ``w_ghs`` (celda × año; las de w_ghs ≤ 0
    no cuentan); ``estaciones_por_anio``: año → tabla con ``codigo``, ``lat``, ``lon`` y ``horas`` (horas válidas de
    ``variable`` ese año). Todos los años de PI_POB_PERIODO, en las dos. Devuelve {banda: π^pob_b}."""
    _variable(variable)
    _exigir_columnas(celdas_pobladas, ("anio", "lat", "lon", "w_ghs"), "celdas_pobladas")
    anios = _anios_pi()
    w = np.asarray(celdas_pobladas["w_ghs"], dtype=np.float64)
    if not np.isfinite(w).all() or (w < 0).any():
        raise ValueError("celdas_pobladas: w_ghs finito ≥ 0")
    anio = np.asarray(celdas_pobladas["anio"], dtype=np.int64)
    if set(np.unique(anio[w > 0]).tolist()) != set(anios) or set(estaciones_por_anio) != set(anios):
        raise ValueError(f"π^pob: se exigen los años {anios[0]}-{anios[-1]} en las celdas pobladas y en las estaciones")
    lat = np.asarray(celdas_pobladas["lat"], dtype=np.float64)
    lon = np.asarray(celdas_pobladas["lon"], dtype=np.float64)
    minimo = umbrales.a("MIN_HORAS")
    acumulado = np.zeros(len(rotulos_bandas(umbrales)))
    for y in anios:
        m = (anio == y) & (w > 0)
        lat_e, lon_e = _estaciones_del_anio(estaciones_por_anio[y], minimo, f"estaciones de {y}")
        b = bandas(_distancia_minima_km(lat[m], lon[m], lat_e, lon_e), umbrales)
        acumulado += np.bincount(b, weights=w[m], minlength=acumulado.size)
    return _pi_de(acumulado, umbrales)


def pi_monitores(pliegues_red2, panel_red2, estaciones_por_anio, variable, umbrales) -> dict:
    """§5.3, π^mon (VAL-9; MC-09, R21). ``pliegues_red2``: el manifiesto ``pliegues_v2_red2.json`` leído;
    ``panel_red2``: contaminante → {"tabla": panel (``estacion``, ``ts_utc``, ``obs``), "sha256": del archivo}, que debe
    ser el que cita ``contaminantes.<pol>.panel.sha256``; ``estaciones_por_anio`` como en ``pi_poblacion``. Devuelve
    {banda: π^mon_b}."""
    _variable(variable)
    if not isinstance(pliegues_red2, Mapping) or not isinstance(panel_red2, Mapping):
        raise TypeError("pi_monitores: el manifiesto y los paneles son diccionarios")
    coordenadas: dict[str, tuple[float, float]] = {}
    for r in pliegues_red2["estaciones"]:
        e = str(r["estacion"])
        if e in coordenadas:
            raise ValueError(f"pliegues_red2: estación repetida {e!r}")
        coordenadas[e] = (float(r["lat"]), float(r["lon"]))
    contaminantes = pliegues_red2["contaminantes"]
    if set(contaminantes) != set(tipos.CONTAMINANTES_M6) or set(panel_red2) != set(tipos.CONTAMINANTES_M6):
        raise ValueError(f"π^mon: los monitores son los de {tipos.CONTAMINANTES_M6} (§5.3, R21)")
    anios = set(_anios_pi())
    monitor_anio: set[tuple[str, int]] = set()
    for pol in tipos.CONTAMINANTES_M6:
        entrada = panel_red2[pol]
        if entrada["sha256"] != contaminantes[pol]["panel"]["sha256"]:
            raise ValueError(f"π^mon: el panel de {pol} no es el que cita el manifiesto de la red 2 (MC-09)")
        tabla = entrada["tabla"]
        _exigir_columnas(tabla, ("estacion", "ts_utc", "obs"), f"panel de {pol}")
        obs = np.asarray(tabla["obs"], dtype=np.float64)
        ts = pd.DatetimeIndex(tabla["ts_utc"])
        ts = ts.tz_convert("UTC") if ts.tz is not None else ts
        con = np.isfinite(obs)
        est = pd.Series(tabla["estacion"]).astype(str).to_numpy()[con]
        desconocidas = sorted(set(est) - set(coordenadas))
        if desconocidas:
            raise ValueError(f"panel de {pol}: estaciones fuera del manifiesto {desconocidas}")
        for e, y in zip(est, ts.year.to_numpy()[con]):
            if int(y) in anios:
                monitor_anio.add((e, int(y)))
    if not monitor_anio:
        raise ValueError("π^mon: ningún monitor-año con datos")
    faltan = sorted({y for _, y in monitor_anio} - set(estaciones_por_anio))
    if faltan:
        raise ValueError(f"π^mon: faltan las estaciones de los años {faltan}")
    minimo = umbrales.a("MIN_HORAS")
    acumulado = np.zeros(len(rotulos_bandas(umbrales)))
    for y in sorted({y for _, y in monitor_anio}):
        ms = sorted(e for e, yy in monitor_anio if yy == y)
        lat_e, lon_e = _estaciones_del_anio(estaciones_por_anio[y], minimo, f"estaciones de {y}")
        d = _distancia_minima_km([coordenadas[m][0] for m in ms], [coordenadas[m][1] for m in ms], lat_e, lon_e)
        acumulado += np.bincount(bandas(d, umbrales), minlength=acumulado.size)
    return _pi_de(acumulado, umbrales)


def pi_uso(uso, pi_pob, pi_mon=None, *, umbrales) -> np.ndarray:
    """§5.3 (VAL-9): π del uso por banda: ambiental ½ π^mon + ½ π^pob (PI_AMBIENTAL); agudo y crónico, π^pob."""
    uso = _uso(uso)
    pob = _vector_pi(pi_pob, umbrales)
    if uso is not Uso.AMBIENTAL:
        return pob
    if pi_mon is None:
        raise ValueError("π ambiental: falta π^mon (§5.3)")
    peso_mon, peso_pob = constantes.valor("PI_AMBIENTAL")
    return peso_mon * _vector_pi(pi_mon, umbrales) + peso_pob * pob


def _grupos_de_bandas(cuentas, minimo: int) -> list[list[int]]:
    """VAL-10: la unión de bandas con < ``minimo`` evaluaciones, desde la más cercana a 0."""
    grupos = [[k] for k in range(len(cuentas))]
    n = [int(c) for c in cuentas]
    while len(grupos) > 1:
        i = next((j for j, c in enumerate(n) if c < minimo), None)
        if i is None:
            break
        j = 1 if i == 0 else i - 1
        a, b = min(i, j), max(i, j)
        grupos[a:b + 1] = [grupos[a] + grupos[b]]
        n[a:b + 1] = [n[a] + n[b]]
    return grupos


def _s_desde_sumas(cuentas: np.ndarray, sumas: np.ndarray, pi: np.ndarray, minimo: int) -> float:
    if cuentas.sum() == 0:
        return _NAN
    total = 0.0
    for g in _grupos_de_bandas(cuentas, minimo):
        n_g = float(cuentas[g].sum())
        total += float(pi[g].sum()) * (float(sumas[g].sum()) / n_g)
    return math.sqrt(total)


def puntaje(mse_e, banda_e, pi, umbrales) -> float:
    """§5.3 (VAL-10): S = √(Σ_g π_g · MSE̅_g), con la unión de las bandas de < BANDA_MIN_EVAL evaluaciones. ``mse_e``:
    MSE_e finitos ≥ 0 (o CD_e², EX_e² para CD y EX, MC-29); ``banda_e``: sus bandas (``bandas``); ``pi``: el del uso por
    banda. NaN sin evaluaciones."""
    x = np.asarray(mse_e, dtype=np.float64).ravel()
    b = np.asarray(banda_e).ravel()
    if b.shape != x.shape:
        raise ValueError("puntaje: una banda por evaluación")
    if not np.isfinite(x).all() or (x < 0).any():
        raise ValueError("puntaje: MSE_e finitos ≥ 0 (quien llama deja fuera las evaluaciones sin la métrica)")
    pi = _vector_pi(pi, umbrales)
    if b.size and (not np.issubdtype(b.dtype, np.integer) or b.min() < 0 or b.max() >= pi.size):
        raise ValueError(f"puntaje: bandas enteras en [0, {pi.size})")
    b = b.astype(np.int64)
    cuentas = np.bincount(b, minlength=pi.size)
    sumas = np.bincount(b, weights=x, minlength=pi.size)
    return _s_desde_sumas(cuentas, sumas, pi, _entero(umbrales, "BANDA_MIN_EVAL"))


def puntaje_par(S_T: dict, S_HR: dict, e0) -> dict:
    """§5.3 (VAL-11): S_par,c = ½ (S_T,c / mín_E0 S_T + S_HR,c / mín_E0 S_HR) para los c de E0; sin S_HR (lo crónico),
    S_T. La misma fórmula que ``decision._s_del_grupo`` (A11)."""
    e0 = tuple(Candidato(c).value for c in e0)
    if not e0:
        raise ValueError("puntaje_par: E0 vacío")
    for nombre, S in (("S_T", S_T), ("S_HR", S_HR)):
        if S is None:
            continue
        faltan = [c for c in e0 if c not in S]
        if faltan or not all(_finito(S[c]) and S[c] >= 0 for c in e0):
            raise ValueError(f"puntaje_par: {nombre} debe traer un número finito ≥ 0 para cada candidato de E0")
    s1 = {c: float(S_T[c]) for c in e0}
    if S_HR is None:
        return s1
    s2 = {c: float(S_HR[c]) for c in e0}
    m1, m2 = min(s1.values()), min(s2.values())
    if m1 <= 0 or m2 <= 0:
        raise ValueError("S_par: un mínimo sobre E0 es 0 (§5.3)")
    peso = constantes.valor("S_PAR_PESO")
    return {c: peso * (s1[c] / m1 + s2[c] / m2) for c in e0}


# ---------------------------------------------------------------------------------------------------------------
# Preparación de las evaluaciones de un (uso, grupo) (VAL-14 a VAL-16)
# ---------------------------------------------------------------------------------------------------------------
def _fuera_de_la_grilla(info) -> bool:
    """D34 (NAS-17): no excluida y sin celda (copia de ``estaticas_nasadem.fuera_de_la_grilla``; pedido a ``tipos``)."""
    return not info.excluida and info.celda is None


@dataclass(frozen=True, eq=False)
class _Bloque:
    """Las evaluaciones de una (variable, candidato), en arreglos."""
    codigo: np.ndarray
    particion: np.ndarray
    banda: np.ndarray
    n_horas: np.ndarray
    frac: np.ndarray
    metricas: Mapping[str, np.ndarray]


@dataclass(frozen=True, eq=False)
class _Preparadas:
    uso: Uso
    grupo: Grupo
    variables: tuple[str, ...]
    candidatos: tuple[str, ...]
    bloques: Mapping[tuple[str, str], _Bloque]
    codigos: frozenset[str]
    declaraciones: Mapping[str, int]


def _principal(uso: Uso, grupo: Grupo, variable: str) -> str:
    return next(iter(METRICAS[(uso, grupo)][variable].values()))


def _preparar(evaluaciones, infos, *, uso, grupo, banda) -> _Preparadas:
    tipos.validar_esquema(evaluaciones, tipos.ESQUEMA_EVALUACIONES, nombre="evaluaciones")
    uso, grupo = Uso(uso), Grupo(grupo)
    if (uso, grupo) not in METRICAS:
        raise ValueError(f"lo {uso.value} no decide el grupo {grupo.value} (§6.1)")
    variables = tuple(v for v in _ORDEN_VARIABLES if v in METRICAS[(uso, grupo)])
    candidatos = CANDIDATOS_USO[uso]
    df = evaluaciones[(evaluaciones["uso"] == uso.value).to_numpy(dtype=bool)
                      & evaluaciones["variable"].isin(variables).to_numpy(dtype=bool)]
    ajenos = sorted(set(df["candidato"]) - set(candidatos))
    if ajenos:
        raise ValueError(f"evaluaciones: {ajenos} no son candidatos de lo {uso.value} (§6.1)")
    if df.duplicated(["codigo", "particion", "candidato", "variable"]).any():
        raise ValueError("evaluaciones: evaluación repetida")
    for particion, pliegue in set(zip(df["particion"], df["pliegue"])):
        _codigo_de_pliegue(Particion(particion).value, pliegue)
    fuera, sin_macro = set(), set()
    for c in sorted(set(df["codigo"])):
        if c not in infos:
            raise ValueError(f"evaluaciones: estación desconocida {c}")
        info = infos[c]
        if info.excluida:
            raise ValueError(f"evaluaciones: {c} está excluida ({info.motivo}) y no se evalúa (§2.5)")
        if _fuera_de_la_grilla(info):
            fuera.add(c)
        elif _macrozona(info.macrozona, f"estación {c}") is None:
            sin_macro.add(c)
    df = df[~df["codigo"].isin(sorted(fuera)).to_numpy(dtype=bool)]
    bloques: dict[tuple[str, str], _Bloque] = {}
    for v in variables:
        cols = sorted(set(METRICAS[(uso, grupo)][v].values()))
        de_v = df[(df["variable"] == v).to_numpy(dtype=bool)]
        referencia = None
        for cand in candidatos:
            d = de_v[(de_v["candidato"] == cand).to_numpy(dtype=bool)].sort_values(["codigo", "particion"])
            claves = list(zip(d["codigo"], d["particion"]))
            patron = {c: tuple(np.isfinite(d[c].to_numpy(np.float64))) for c in cols}
            if referencia is None:
                referencia = (claves, patron)
            elif (claves, patron) != referencia:
                raise ValueError(f"evaluaciones de {v}: {cand} no trae las mismas evaluaciones, o las mismas métricas "
                                 "finitas, que los demás candidatos (VAL-15)")
            frac = d["frac_sin_soporte"].to_numpy(np.float64)
            if cand in NUCLEO and not (np.isfinite(frac).all() and ((frac >= 0) & (frac <= 1)).all()):
                raise ValueError(f"evaluaciones de {v}: frac_sin_soporte de {cand} fuera de [0, 1]")
            try:
                b = np.array([banda[(c, p, HORAS_DE[v])] for c, p in claves], dtype=np.int64)
            except KeyError as error:
                raise ValueError(f"evaluaciones de {v}: sin banda para {error.args[0]} (VAL-8)") from None
            bloques[(v, cand)] = _Bloque(
                codigo=d["codigo"].to_numpy(dtype=object), particion=d["particion"].to_numpy(dtype=object),
                banda=b, n_horas=d["n_horas"].to_numpy(np.float64), frac=frac,
                metricas={c: d[c].to_numpy(np.float64) for c in COLUMNAS_METRICA})
    return _Preparadas(uso=uso, grupo=grupo, variables=variables, candidatos=candidatos, bloques=bloques,
                       codigos=frozenset(df["codigo"]),
                       declaraciones={"fuera_de_la_grilla": len(fuera), "sin_macrozona": len(sin_macro)})


def _pi_de_variable(pi: Mapping[str, Any], variable: str, umbrales) -> np.ndarray:
    clave = HORAS_DE[variable]
    if clave not in pi:
        raise ValueError(f"π: falta el de {clave} (VAL-8)")
    return _vector_pi(pi[clave], umbrales)


# ---------------------------------------------------------------------------------------------------------------
# §5.5: regla de soporte y estratos
# ---------------------------------------------------------------------------------------------------------------
def publicable(frac_sin_soporte: dict, umbrales) -> bool:
    """§0.4.4 y §5.5 (VAL-13): True si ninguno de A, B y AB carece de soporte en más de SOPORTE_PCT de sus horas de
    prueba. ``frac_sin_soporte``: candidato → fracción en [0, 1]; exige A, B y AB (C y C_est no cuentan)."""
    if not isinstance(frac_sin_soporte, Mapping):
        raise TypeError("publicable: se espera {candidato: fracción}")
    fr = {Candidato(c).value: x for c, x in frac_sin_soporte.items()}
    faltan = [c for c in NUCLEO if c not in fr]
    if faltan:
        raise ValueError(f"publicable: faltan {faltan}; la regla mira A, B y AB (§0.4.4)")
    for c in NUCLEO:
        if not _finito(fr[c]) or not 0 <= fr[c] <= 1:
            raise ValueError(f"publicable: la fracción de {c} debe estar en [0, 1], no {fr[c]!r}")
    limite = umbrales.frac("SOPORTE_PCT")
    return all(fr[c] <= limite for c in NUCLEO)


def _fraccion(bl: _Bloque, filas: np.ndarray) -> float:
    n = bl.n_horas[filas]
    f = bl.frac[filas]
    if not filas.any() or not np.isfinite(f).all() or n.sum() <= 0:
        return _NAN
    return float(np.sum(f * n) / np.sum(n))


def _mascara(bl: _Bloque, codigos: frozenset[str], particion: str) -> np.ndarray:
    m = np.isin(bl.codigo, list(codigos)) if codigos else np.zeros(bl.codigo.size, dtype=bool)
    if particion != AGREGADO:
        m &= bl.particion == particion
    return m


@dataclass(frozen=True)
class _Estrato:
    estrato: str
    valor: str
    codigos: frozenset[str]
    variables: tuple[str, ...]
    prep: _Preparadas


def _estratos_de(prep: _Preparadas, infos, periodos: Mapping[str, _Preparadas]) -> tuple[list[_Estrato], dict]:
    """Los estratos de §5.5 (VAL-17), en el orden de ``ESTRATOS``, y lo que se declara."""
    codigos = sorted(prep.codigos)
    todas = prep.variables
    mz = tuple(v for v in todas if v in VARIABLES_MZ[(prep.uso, prep.grupo)])
    salida = [_Estrato(ESTRATO_NACIONAL, VALOR_NACIONAL, prep.codigos, todas, prep)]
    macro = {c: _macrozona(infos[c].macrozona, f"estación {c}") for c in codigos}
    for z in MACROZONAS:
        salida.append(_Estrato(ESTRATO_MACROZONA, z, frozenset(c for c in codigos if macro[c] == z), mz, prep))
    for conj in tipos.Conjunto:
        salida.append(_Estrato(ESTRATO_CONJUNTO, conj.value,
                               frozenset(c for c in codigos if infos[c].conjunto == conj.value), todas, prep))
    bajo, alto = constantes.valor("ESTRATO_ALTITUD_M")
    sin_altitud = 0
    tramos = {f"<{bajo}": [], f"{bajo}-{alto}": [], f">{alto}": []}
    for c in codigos:
        z = float(infos[c].z_s)
        if not math.isfinite(z):
            sin_altitud += 1
            continue
        tramos[f"<{bajo}" if z < bajo else (f">{alto}" if z > alto else f"{bajo}-{alto}")].append(c)
    for valor, cs in tramos.items():
        salida.append(_Estrato(ESTRATO_ALTITUD, valor, frozenset(cs), todas, prep))
    no_formados = []
    if periodos:
        for valor, p in periodos.items():
            salida.append(_Estrato(ESTRATO_PERIODO, valor, p.codigos, todas, p))
    else:
        no_formados.append(ESTRATO_PERIODO)
    for estrato, campo in ((ESTRATO_TIPO, "tipo"), (ESTRATO_PROPIETARIO, "propietario")):
        valores = sorted({getattr(infos[c], campo) for c in codigos if _texto_no_vacio(getattr(infos[c], campo))})
        if not valores:
            no_formados.append(estrato)
        for valor in valores:
            salida.append(_Estrato(estrato, valor, frozenset(c for c in codigos if getattr(infos[c], campo) == valor),
                                   todas, prep))
    if all(infos[c].omm is None for c in codigos):
        no_formados.append(ESTRATO_OMM)
    else:
        salida.append(_Estrato(ESTRATO_OMM, VALOR_OMM, frozenset(c for c in codigos if infos[c].omm is True), todas,
                               prep))
    return salida, {"sin_altitud": sin_altitud, "estratos_no_formados": tuple(no_formados),
                    "variables_sin_estrato_macrozona": tuple(v for v in todas if v not in mz)}     # VAL-17, VAL-P7


def _filas_de(e: _Estrato, pi: Mapping[str, Any], umbrales) -> tuple[list[dict], list[dict]]:
    """Las filas publicadas y las de soporte de un estrato (VAL-10, VAL-13, VAL-14)."""
    prep = e.prep
    nacional = e.estrato == ESTRATO_NACIONAL
    filas, soporte = [], []
    for v in e.variables:
        metricas = METRICAS[(prep.uso, prep.grupo)][v]
        principal = _principal(prep.uso, prep.grupo, v)
        pi_v = _pi_de_variable(pi, v, umbrales)
        cuenta: dict[str, tuple[int, int]] = {}
        fracciones: dict[str, dict[str, float]] = {}
        for p in PARTICIONES:
            fracciones[p] = {}
            for cand in prep.candidatos:
                bl = prep.bloques[(v, cand)]
                filas_p = _mascara(bl, e.codigos, p) & np.isfinite(bl.metricas[principal])
                fracciones[p][cand] = _fraccion(bl, filas_p)
                cuenta[(p, cand)] = (int(filas_p.sum()), len(set(bl.codigo[filas_p])))
        pub = {}
        for p in PARTICIONES:
            if nacional:
                pub[p] = True
            elif any(cuenta[(p, c)][0] == 0 or not math.isfinite(fracciones[p][c]) for c in NUCLEO):
                pub[p] = False
            else:
                pub[p] = publicable({c: fracciones[p][c] for c in NUCLEO}, umbrales)
        publicado = all(pub.values())
        for cand in prep.candidatos:
            bl = prep.bloques[(v, cand)]
            for p in PARTICIONES:
                valores = dict.fromkeys(COLUMNAS_PUB, _NAN)
                if publicado:
                    base = _mascara(bl, e.codigos, p)
                    for col_pub, col in metricas.items():
                        x = bl.metricas[col]
                        m = base & np.isfinite(x)
                        y = x[m] ** 2 if col_pub in _CON_CUADRADO else x[m]
                        valores[col_pub] = puntaje(y, bl.banda[m], pi_v, umbrales)
                n_ev, n_est = cuenta[(p, cand)]
                filas.append({"uso": prep.uso.value, "grupo": prep.grupo.value, "variable": v, "candidato": cand,
                              "particion": p, **valores, "estrato": e.estrato, "valor_estrato": e.valor,
                              "n_evaluaciones": n_ev, "n_estaciones": n_est, "publicable": pub[p]})
                if not publicado:
                    soporte.append({"uso": prep.uso.value, "grupo": prep.grupo.value, "variable": v,
                                    "candidato": cand, "particion": p, "estrato": e.estrato,
                                    "valor_estrato": e.valor, "frac_sin_soporte": fracciones[p][cand],
                                    "publicable": pub[p]})
    return filas, soporte


COLUMNAS_SOPORTE = MappingProxyType({                 # pedido al coordinador: ESQUEMA_SOPORTE_PUB en tipos
    "uso": "string", "grupo": "string", "variable": "string", "candidato": "string", "particion": "string",
    "estrato": "string", "valor_estrato": "string", "frac_sin_soporte": "float64", "publicable": "bool"})
VERSION_SOPORTE = "meteo-combinada-soporte-pub/1"


def _todo(evaluaciones, infos, umbrales, *, uso, grupo, banda, pi, periodos):
    prep = _preparar(evaluaciones, infos, uso=uso, grupo=grupo, banda=banda)
    de_periodos: dict[str, _Preparadas] = {}
    if periodos is not None:
        a0, a1, b0, b1 = constantes.valor("ESTRATO_PERIODOS")
        rotulos = (f"{a0}-{a1}", f"{b0}-{b1}")
        if not isinstance(periodos, Mapping) or list(periodos) != list(rotulos):
            raise ValueError(f"periodos: se esperan las evaluaciones de {rotulos}, en orden (VAL-17)")
        de_periodos = {r: _preparar(periodos[r], infos, uso=uso, grupo=grupo, banda=banda) for r in rotulos}
    estratos_, declaraciones = _estratos_de(prep, infos, de_periodos)
    filas, soporte = [], []
    for e in estratos_:
        f, s = _filas_de(e, pi, umbrales)
        filas += f
        soporte += s
    return prep, filas, soporte, {**prep.declaraciones, **declaraciones}


def estratos(evaluaciones, infos, umbrales, *, uso, grupo, banda, pi, periodos=None) -> pd.DataFrame:
    """§5.3 y §5.5: ``tipos.ESQUEMA_VALIDACION_PUB`` de un (uso, grupo): el estrato nacional, las cinco macrozonas (en
    las variables de MZ) y los estratos descriptivos, en P1, P2 y el agregado, con la regla de soporte (VAL-10 a
    VAL-17). ``banda``: la de ``bandas_de_pliegues``; ``pi``: clave de horas → π del uso (``pi_uso``); ``periodos``:
    {«2000-2009»: evaluaciones, «2010-2026»: evaluaciones} calculadas con las horas de cada período. Lo que se cuenta
    aparte va en ``attrs["declaraciones"]``."""
    _, filas, _, declaraciones = _todo(evaluaciones, infos, umbrales, uso=uso, grupo=grupo, banda=banda, pi=pi,
                                       periodos=periodos)
    esquema = tipos.ESQUEMA_VALIDACION_PUB
    df = pd.DataFrame(filas, columns=list(esquema)).astype(dict(esquema))
    tipos.validar_esquema(df, esquema, nombre="validacion")
    df.attrs = {"esquema": esquema.version, "declaraciones": declaraciones}
    return df


def fracciones_sin_soporte(evaluaciones, infos, umbrales, *, uso, grupo, banda, pi, periodos=None) -> pd.DataFrame:
    """§0.4.4 y §5.5 (VAL-13): de cada estrato que no se publica, la fracción de horas sin soporte de cada candidato,
    por partición (columnas ``COLUMNAS_SOPORTE``). Es lo único que se publica de él."""
    _, _, soporte, _ = _todo(evaluaciones, infos, umbrales, uso=uso, grupo=grupo, banda=banda, pi=pi,
                             periodos=periodos)
    df = pd.DataFrame(soporte, columns=list(COLUMNAS_SOPORTE)).astype(dict(COLUMNAS_SOPORTE))
    df.attrs = {"esquema": VERSION_SOPORTE}
    return df


def tabla_bandas(evaluaciones, infos, umbrales, *, uso, grupo, banda, pi_pob, pi_mon=None) -> pd.DataFrame:
    """§5.3, «Qué se publica»: ``tipos.ESQUEMA_BANDAS_PUB`` de un (uso, grupo): por variable, banda y candidato, π^mon
    (sólo en lo ambiental; si no, NaN), π^pob y la fracción de horas sin soporte de sus evaluaciones de P1 y P2 en esa
    banda (NaN en C y C_est y sin evaluaciones). ``pi_pob`` y ``pi_mon``: clave de horas → π."""
    prep = _preparar(evaluaciones, infos, uso=uso, grupo=grupo, banda=banda)
    rotulos = rotulos_bandas(umbrales)
    filas = []
    for v in prep.variables:
        pob = _pi_de_variable(pi_pob, v, umbrales)
        mon = _pi_de_variable(pi_mon, v, umbrales) if prep.uso is Uso.AMBIENTAL else np.full(len(rotulos), _NAN)
        principal = _principal(prep.uso, prep.grupo, v)
        for k, r in enumerate(rotulos):
            for cand in prep.candidatos:
                bl = prep.bloques[(v, cand)]
                m = (bl.banda == k) & np.isfinite(bl.metricas[principal])
                frac = _fraccion(bl, m) if cand in NUCLEO else _NAN
                filas.append({"uso": prep.uso.value, "variable": v, "banda": r, "candidato": cand,
                              "pi_mon": float(mon[k]), "pi_pob": float(pob[k]), "frac_sin_soporte": frac})
    esquema = tipos.ESQUEMA_BANDAS_PUB
    df = pd.DataFrame(filas, columns=list(esquema)).astype(dict(esquema))
    tipos.validar_esquema(df, esquema, nombre="bandas")
    df.attrs = {"esquema": esquema.version}
    return df


# ---------------------------------------------------------------------------------------------------------------
# §5.2 y §5.8: tabla de descriptivos (VAL-21)
# ---------------------------------------------------------------------------------------------------------------
COLUMNAS_DESCRIPTIVAS_EV = ("codigo", "particion", "candidato", "uso", "variable", "descriptivo", "valor")
COLUMNAS_DESCRIPTIVOS = MappingProxyType({            # pedido al coordinador: ESQUEMA_DESCRIPTIVOS_PUB en tipos
    "uso": "string", "grupo": "string", "variable": "string", "candidato": "string", "particion": "string",
    "descriptivo": "string", "valor": "float64", "n_evaluaciones": "int32", "n_estaciones": "int32"})
VERSION_DESCRIPTIVOS = "meteo-combinada-descriptivos-pub/1"


def filas_descriptivas(metricas: Mapping[str, Any], *, codigo: str, particion: str, candidato: str, uso,
                       variable) -> list[dict]:
    """VAL-21: los descriptivos de una evaluación (``metricas["descriptivos"]``, de ``evaluacion``) en filas de
    ``COLUMNAS_DESCRIPTIVAS_EV``, una por cada nombre de ``descriptivos_de``. En memoria; no se publican por estación."""
    uso, v = _uso(uso), _variable(variable)
    if not isinstance(codigo, str) or tipos.PATRON_CODIGO.fullmatch(codigo) is None:
        raise ValueError(f"código de estación inválido: {codigo!r}")
    particion = Particion(particion).value
    candidato = Candidato(candidato).value
    if candidato not in CANDIDATOS_USO[uso]:
        raise ValueError(f"{candidato} no es candidato de lo {uso.value} (§6.1)")
    nombres = descriptivos_de(uso, v)
    dados = metricas.get("descriptivos")
    if not isinstance(dados, Mapping) or set(dados) != set(nombres):
        raise ValueError(f"descriptivos de {codigo} ({uso.value}, {v}): se esperan {nombres}, no "
                         f"{sorted(dados) if isinstance(dados, Mapping) else dados!r}")
    return [{"codigo": codigo, "particion": particion, "candidato": candidato, "uso": uso.value, "variable": v,
             "descriptivo": nombre, "valor": float(dados[nombre])} for nombre in nombres]


def _media_bandas(x: np.ndarray, b: np.ndarray, pi: np.ndarray, umbrales) -> float:
    """VAL-21: Σ_g π_g · media_g(x) con la unión de bandas de VAL-10; NaN sin evaluaciones."""
    if x.size == 0:
        return _NAN
    cuentas = np.bincount(b, minlength=pi.size)
    sumas = np.bincount(b, weights=x, minlength=pi.size)
    total = 0.0
    for g in _grupos_de_bandas(cuentas, _entero(umbrales, "BANDA_MIN_EVAL")):
        total += float(pi[g].sum()) * (float(sumas[g].sum()) / float(cuentas[g].sum()))
    return total


def tabla_descriptivos(evaluaciones, descriptivas, infos, umbrales, *, uso, grupo, banda, pi) -> pd.DataFrame:
    """§5.2 y §5.8 (VAL-21): ``COLUMNAS_DESCRIPTIVOS`` de un (uso, grupo), en lo nacional, en P1, P2 y el agregado.
    ``evaluaciones``: las de ``estratos`` (dan las estaciones, las bandas y lo que se descarta, VAL-16);
    ``descriptivas``: las filas de ``filas_descriptivas`` (o una tabla con ``COLUMNAS_DESCRIPTIVAS_EV``) de esas
    evaluaciones; ``banda`` y ``pi`` como en ``estratos``."""
    prep = _preparar(evaluaciones, infos, uso=uso, grupo=grupo, banda=banda)
    d = descriptivas if isinstance(descriptivas, pd.DataFrame) else pd.DataFrame(
        list(descriptivas), columns=list(COLUMNAS_DESCRIPTIVAS_EV))
    _exigir_columnas(d, COLUMNAS_DESCRIPTIVAS_EV, "descriptivas")
    d = d[(d["uso"] == prep.uso.value).to_numpy(dtype=bool) & d["variable"].isin(prep.variables).to_numpy(dtype=bool)]
    claves = ["codigo", "particion", "candidato", "variable", "descriptivo"]
    if d.duplicated(claves).any():
        raise ValueError("descriptivas: descriptivo repetido de una evaluación")
    ev = evaluaciones[(evaluaciones["uso"] == prep.uso.value).to_numpy(dtype=bool)]
    conocidas = set(zip(ev["codigo"], ev["particion"], ev["candidato"], ev["variable"]))
    valores: dict[tuple[str, str, str, str, str], float] = {}
    for c, p, cand, v, nombre, x in zip(d["codigo"], d["particion"], d["candidato"], d["variable"], d["descriptivo"],
                                        d["valor"].to_numpy(np.float64)):
        if (c, p, cand, v) not in conocidas:
            raise ValueError(f"descriptivas: {(c, p, cand, v)} no es una evaluación de lo {prep.uso.value}")
        if nombre not in descriptivos_de(prep.uso, v):
            raise ValueError(f"descriptivas: {nombre!r} no es descriptivo de ({prep.uso.value}, {v}) (VAL-21)")
        valores[(str(c), str(p), str(cand), str(v), str(nombre))] = float(x)
    filas = []
    for v in prep.variables:
        pi_v = _pi_de_variable(pi, v, umbrales)
        for nombre in descriptivos_de(prep.uso, v):
            referencia = None
            for cand in prep.candidatos:
                bl = prep.bloques[(v, cand)]
                try:
                    x = np.array([valores[(c, p, cand, v, nombre)] for c, p in zip(bl.codigo, bl.particion)],
                                 dtype=np.float64)
                except KeyError as error:
                    raise ValueError(f"descriptivas: falta {error.args[0]} (código, partición, candidato, variable, "
                                     "descriptivo)") from None
                patron = tuple(np.isfinite(x))
                if referencia is None:
                    referencia = patron
                elif patron != referencia:
                    raise ValueError(f"descriptivas de {v}: {cand} no trae {nombre} finito en las mismas evaluaciones "
                                     "que los demás candidatos (VAL-15, VAL-21)")
                for p in PARTICIONES:
                    m = _mascara(bl, prep.codigos, p) & np.isfinite(x)
                    if AGREGACION_DESCRIPTIVO[nombre] == "cuadrado":
                        valor = puntaje(x[m] ** 2, bl.banda[m], pi_v, umbrales)
                    else:
                        valor = _media_bandas(x[m], bl.banda[m], pi_v, umbrales)
                    filas.append({"uso": prep.uso.value, "grupo": prep.grupo.value, "variable": v,
                                  "candidato": cand, "particion": p, "descriptivo": nombre, "valor": valor,
                                  "n_evaluaciones": int(m.sum()), "n_estaciones": len(set(bl.codigo[m]))})
    df = pd.DataFrame(filas, columns=list(COLUMNAS_DESCRIPTIVOS)).astype(dict(COLUMNAS_DESCRIPTIVOS))
    df.attrs = {"esquema": VERSION_DESCRIPTIVOS, "declaraciones": dict(prep.declaraciones)}
    return df


# ---------------------------------------------------------------------------------------------------------------
# §5.4: remuestreo
# ---------------------------------------------------------------------------------------------------------------
def remuestreo(evaluaciones, bloques, umbrales, *, infos, uso, grupo, banda, pi, e0) -> pd.DataFrame:
    """§5.4 (VAL-12; MC-34, D46): ``tipos.ESQUEMA_REPLICAS`` con el S del grupo de cada candidato de E0 en cada una de
    las BOOT_REPLICAS réplicas por bloques de P2. ``bloques``: código → bloque de P2 de su grupo
    (``particiones.bloques_remuestreo``)."""
    prep = _preparar(evaluaciones, infos, uso=uso, grupo=grupo, banda=banda)
    e0 = _e0_del_uso(e0, prep.uso, "remuestreo")
    if not isinstance(bloques, Mapping) or not bloques:
        raise ValueError("remuestreo: se esperan los bloques de P2 de las estaciones (particiones.bloques_remuestreo)")
    sin_bloque = sorted(prep.codigos - set(bloques))
    if sin_bloque:
        raise ValueError(f"remuestreo: estaciones evaluadas sin bloque de P2: {sin_bloque}")
    ajenas = sorted(str(c) for c in bloques if c not in infos or infos[c].excluida)
    if ajenas:
        raise ValueError(f"remuestreo: bloques de estaciones desconocidas o excluidas {ajenas}; son los de "
                         "particiones.bloques_remuestreo (PAR-1)")
    ids = sorted({str(b) for b in bloques.values()})
    posicion = {b: i for i, b in enumerate(ids)}
    n_rep = _entero(umbrales, "BOOT_REPLICAS")
    sorteo = numerico.remuestreo_bloques(ids, n_rep, _entero(umbrales, "SEMILLA"))       # réplicas × bloques
    idx = np.array([[posicion[b] for b in fila] for fila in sorteo], dtype=np.int64)
    W = np.zeros((n_rep, len(ids)), dtype=np.float64)                                      # veces que sale cada bloque
    np.add.at(W, (np.repeat(np.arange(n_rep), idx.shape[1]), idx.ravel()), 1.0)
    minimo = _entero(umbrales, "BANDA_MIN_EVAL")
    variables_s = S_DEL_GRUPO[(prep.uso, prep.grupo)]
    bloque_de = {c: posicion[str(bloques[c])] for c in prep.codigos}
    S: dict[str, dict[str, np.ndarray]] = {}
    for v in variables_s:
        pi_v = _pi_de_variable(pi, v, umbrales)
        col = METRICAS[(prep.uso, prep.grupo)][v]["S"]
        S[v] = {}
        for cand in e0:
            bl = prep.bloques[(v, cand)]
            x = bl.metricas[col]
            m = np.isfinite(x)
            fila_b = np.array([bloque_de[c] for c in bl.codigo[m]], dtype=np.int64)
            N = np.zeros((len(ids), pi_v.size))                # evaluaciones por bloque y banda
            Q = np.zeros((len(ids), pi_v.size))                # su suma de MSE_e
            np.add.at(N, (fila_b, bl.banda[m]), 1.0)
            np.add.at(Q, (fila_b, bl.banda[m]), x[m])
            n_r, q_r = np.matmul(W, N), np.matmul(W, Q)
            S[v][cand] = np.array([_s_desde_sumas(n_r[r], q_r[r], pi_v, minimo) for r in range(n_rep)])
    filas = []
    for r in range(n_rep):
        if len(variables_s) == 2:
            v1, v2 = variables_s
            s_r = puntaje_par({c: S[v1][c][r] for c in e0}, {c: S[v2][c][r] for c in e0}, e0)
        else:
            s_r = {c: float(S[variables_s[0]][c][r]) for c in e0}
        for c in e0:
            if not math.isfinite(s_r[c]):
                raise ValueError(f"remuestreo: S no definido para {c} en la réplica {r} (VAL-12)")
            filas.append({"replica": r, "candidato": c, "S": s_r[c]})
    esquema = tipos.ESQUEMA_REPLICAS
    df = pd.DataFrame(filas, columns=list(esquema)).astype(dict(esquema))
    df.attrs = {"esquema": esquema.version}
    return df


# ---------------------------------------------------------------------------------------------------------------
# §5.5: réplica con N
# ---------------------------------------------------------------------------------------------------------------
_CLAVES_ENTRADA_N = ("evaluaciones", "banda", "pi", "bloques", "tf", "motivos_e0", "ganador")


def _clave_uso_grupo(k) -> tuple[Uso, Grupo]:
    if isinstance(k, str):
        partes = k.split("/")
        if len(partes) != 2:
            raise ValueError(f"clave {k!r}: se espera «uso/grupo»")
        return Uso(partes[0]), Grupo(partes[1])
    u, g = k
    return Uso(u), Grupo(g)


def replica_n(entradas, infos, umbrales, *, decidir: Callable) -> dict:
    """§5.5 (VAL-18): ``decidir_combinacion`` con sólo las evaluaciones de las estaciones de N. ``entradas``:
    (uso, grupo) o «uso/grupo» → {evaluaciones, banda, pi, bloques, tf, motivos_e0, ganador}; ``decidir``:
    ``decision.decidir_combinacion``. Devuelve «uso/grupo» → {ganador, ganador_n, mismo_ganador, n_estaciones_n}."""
    salida = {}
    de_n = frozenset(c for c in infos if infos[c].conjunto == tipos.Conjunto.N.value and not infos[c].excluida)
    for k in sorted(entradas, key=lambda x: tuple(_clave_uso_grupo(x))):
        uso, grupo = _clave_uso_grupo(k)
        ent = entradas[k]
        faltan = [c for c in _CLAVES_ENTRADA_N if c not in ent]
        if faltan:
            raise ValueError(f"replica_n: faltan {faltan} en las entradas de {uso.value}/{grupo.value}")
        ev = ent["evaluaciones"]
        ev_n = ev[ev["codigo"].isin(sorted(de_n)).to_numpy(dtype=bool)].reset_index(drop=True)
        motivos = dict(ent["motivos_e0"])
        e0 = tuple(c for c in CANDIDATOS_USO[uso] if c not in motivos)
        validacion = estratos(ev_n, infos, umbrales, uso=uso, grupo=grupo, banda=ent["banda"], pi=ent["pi"])
        codigos_n = sorted(set(ev_n["codigo"]) - {c for c in set(ev_n["codigo"]) if _fuera_de_la_grilla(infos[c])})
        clave = f"{uso.value}/{grupo.value}"
        ganador = Candidato(ent["ganador"]).value
        if not isinstance(ent["bloques"], Mapping):
            raise ValueError(f"replica_n: los bloques de {clave} son código → bloque de P2")
        bloques_n = {c: b for c, b in ent["bloques"].items() if c in de_n}           # VAL-18, como VAL-12
        sin_bloque = sorted(set(codigos_n) - set(bloques_n))
        if sin_bloque:                                        # un error de la entrada, no «no_decidible»
            raise ValueError(f"replica_n: estaciones N evaluadas sin bloque de P2 en {clave}: {sin_bloque}")
        try:
            replicas = remuestreo(ev_n, bloques_n, umbrales, infos=infos, uso=uso, grupo=grupo, banda=ent["banda"],
                                  pi=ent["pi"], e0=e0)
            d = decidir(uso, grupo, tipos.EntradasDecision(uso, grupo, validacion, ent["tf"], replicas, motivos),
                        umbrales=umbrales)
        except ValueError:
            salida[clave] = {"ganador": ganador, "ganador_n": None, "mismo_ganador": None, "motivo": "no_decidible",
                             "n_estaciones_n": len(codigos_n)}
            continue
        salida[clave] = {"ganador": ganador, "ganador_n": d.ganador, "mismo_ganador": d.ganador == ganador,
                         "n_estaciones_n": len(codigos_n)}
    return salida


# ---------------------------------------------------------------------------------------------------------------
# §5.6: SINCA
# ---------------------------------------------------------------------------------------------------------------
COLUMNAS_PRODUCTO_SINCA = ("estacion", "h", "T", "HR", "u", "v")
SINCA_DE = MappingProxyType({V_T: ("TEMP",), V_HR: ("RHUM",), V_RAPIDEZ: ("WSPD",), V_UV: ("WSPD", "WDIR"),
                             V_TEMP_MEDIA: ("TEMP",), V_HR_MEDIA: ("RHUM",)})
COLUMNAS_SINCA = MappingProxyType({                   # pedido al coordinador: ESQUEMA_SINCA_PUB en tipos
    "uso": "string", "candidato": "string", "lugar": "string", "variable": "string", "metrica": "string",
    "estrato": "string", "valor_estrato": "string", "valor": "float64", "n_estaciones": "int32"})
VERSION_SINCA = "meteo-combinada-sinca-pub/1"
# Cómo se resume en la red cada columna de la evaluación (VAL-19): √ de la media, con el cuadrado o la media.
_RESUMEN_SINCA = MappingProxyType({"mse_h": "raiz", "mae_h": "media", "sesgo_h": "media", "mse_dia": "raiz",
                                   "mse_estrato": "raiz", "mse_anual_neto": "raiz", "mse_anomalia": "raiz",
                                   "cd": "cuadrado", "ex": "cuadrado", **AGREGACION_DESCRIPTIVO})


def _series_sinca(series, umbrales) -> dict[str, dict[str, tuple[np.ndarray, np.ndarray]]]:
    """VAL-19: estación → variable SINCA → (h, valor) de las filas válidas, con las comprobaciones de D47-D50."""
    tipos.validar_esquema(series, tipos.ESQUEMA_SINCA_HORA, nombre="series SINCA")
    ajenas = sorted(set(series["variable"]) - set(tipos.VARIABLES_SINCA))
    if ajenas:
        raise ValueError(f"series SINCA: variables {ajenas}; sólo {tipos.VARIABLES_SINCA} (MC-10, punto 6)")
    if series.groupby(["estacion", "variable"])["serie"].nunique().gt(1).any():
        raise ValueError("series SINCA: una sola serie por estación × variable (MC-10, punto 4; D47)")
    if series.duplicated(["estacion", "variable", "h"]).any():
        raise ValueError("series SINCA: hora repetida en una serie (R7, SNC-8; D48)")
    validas = series[series["valido"].to_numpy(dtype=bool)]
    v = validas["valor"].to_numpy(np.float64)
    if not np.isfinite(v).all():
        raise ValueError("series SINCA: una fila válida sin valor finito")
    var = validas["variable"].to_numpy(dtype=object)
    dd = v[var == "WDIR"]
    ff = v[var == "WSPD"]
    if ((dd < umbrales.a("QDD_MIN")) | (dd > umbrales.a("QDD_MAX"))).any() or (ff < umbrales.a("QFF_MIN")).any():
        raise ValueError("series SINCA: WDIR o WSPD válidos fuera de su rango (SNC-9)")
    salida: dict[str, dict[str, tuple[np.ndarray, np.ndarray]]] = {}
    for (est, variable), d in validas.groupby(["estacion", "variable"], sort=True):
        d = d.sort_values("h")
        salida.setdefault(str(est), {})[str(variable)] = (d["h"].to_numpy(np.int64), d["valor"].to_numpy(np.float64))
    for est in sorted(set(series["estacion"])):
        salida.setdefault(str(est), {})
    return salida


def _producto_sinca(tabla, nombre: str) -> dict[str, dict[str, np.ndarray]]:
    _exigir_columnas(tabla, COLUMNAS_PRODUCTO_SINCA, nombre)
    if tabla.duplicated(["estacion", "h"]).any():
        raise ValueError(f"{nombre}: hora repetida en una estación")
    salida = {}
    for est, d in tabla.groupby("estacion", sort=True):
        d = d.sort_values("h")
        salida[str(est)] = {"h": _horas(d["h"].to_numpy(), f"{nombre}.h"),
                            **{c: d[c].to_numpy(np.float64) for c in ("T", "HR", "u", "v")}}
    return salida


def _en(h_fuente: np.ndarray, valores: np.ndarray, h: np.ndarray) -> np.ndarray:
    """Los ``valores`` (de horas ``h_fuente`` crecientes y sin repetir) en las horas ``h``; NaN donde no hay."""
    salida = np.full(h.size, _NAN)
    if h_fuente.size == 0:
        return salida
    i = np.clip(np.searchsorted(h_fuente, h), 0, h_fuente.size - 1)
    ok = h_fuente[i] == h
    salida[ok] = valores[i[ok]]
    return salida


def _media_en_el_intervalo(prod: Mapping[str, np.ndarray], columna: str, h: np.ndarray) -> np.ndarray:
    """A12 (MC-10, punto 2): la media del producto en u − 1 y u."""
    return (_en(prod["h"], prod[columna], h - 1) + _en(prod["h"], prod[columna], h)) / 2


def _par_sinca(obs: Mapping[str, tuple[np.ndarray, np.ndarray]], prod, variable: str):
    """(hora de comienzo u − 1, pred, obs) de una estación y una variable (VAL-19), o None sin datos."""
    if prod is None:
        return None
    if variable == V_UV:
        if "WSPD" not in obs:
            return None
        h, ff = obs["WSPD"]
        h_dd, dd = obs.get("WDIR", (np.zeros(0, dtype=np.int64), np.zeros(0)))
        rad = np.deg2rad(_en(h_dd, dd, h))
        calma = ff == 0                                       # (0, 0) sin mirar la dirección (VAL-19)
        u_o = np.where(calma, 0.0, -ff * np.sin(rad))
        v_o = np.where(calma, 0.0, -ff * np.cos(rad))
        pred = np.column_stack([_media_en_el_intervalo(prod, "u", h), _media_en_el_intervalo(prod, "v", h)])
        return h - 1, pred, np.column_stack([u_o, v_o])
    nombre = SINCA_DE[variable][0]
    if nombre not in obs:
        return None
    h, x = obs[nombre]
    if variable in (V_T, V_TEMP_MEDIA):
        pred = _media_en_el_intervalo(prod, "T", h)
    elif variable in (V_HR, V_HR_MEDIA):
        pred = _media_en_el_intervalo(prod, "HR", h)
    else:                                                     # la rapidez: media de la rapidez en u − 1 y u
        rapidez = [np.hypot(_en(prod["h"], prod["u"], t), _en(prod["h"], prod["v"], t)) for t in (h - 1, h)]
        pred = (rapidez[0] + rapidez[1]) / 2
    return h - 1, pred, x


def _terciles(tpi: Mapping[str, float], estaciones) -> dict[str, str]:
    faltan = sorted(set(estaciones) - set(tpi))
    if faltan:
        raise ValueError(f"tpi: faltan las estaciones SINCA {faltan}")
    con = {e: float(tpi[e]) for e in estaciones if _finito(tpi[e])}
    if not con:
        return {}
    x = np.array(list(con.values()))
    cortes = np.quantile(x, np.arange(1, N_TERCILES) / N_TERCILES, method=METODO_CUANTIL)
    return {e: str(int(np.searchsorted(cortes, t, side="left")) + 1) for e, t in con.items()}


def _resumir(valores: list[float], modo: str) -> float:
    x = np.array([v for v in valores if math.isfinite(v)], dtype=np.float64)
    if x.size == 0:
        return _NAN
    if modo == "raiz":
        return float(math.sqrt(np.mean(x)))
    if modo == "cuadrado":
        return float(math.sqrt(np.mean(x ** 2)))
    return float(np.mean(x))


def validacion_sinca(series, producto_celda, producto_punto, tpi, umbrales, *, ganadores=None, e0=None,
                     macrozonas=None, zona: str = tipos.ZONA_CIVIL) -> dict:
    """§5.6 (VAL-19, VAL-20; A12 revisado, D47-D50). ``series``: ``tipos.ESQUEMA_SINCA_HORA``;
    ``producto_celda`` y ``producto_punto``: (uso, candidato) → tabla con ``COLUMNAS_PRODUCTO_SINCA`` (el producto
    horario en HH:00 UTC en la celda y en el punto de cada estación SINCA); ``tpi``: estación → TPI;
    ``ganadores``: «uso/grupo» → ganador; ``e0``: «uso/grupo» → candidatos de E0; ``macrozonas``: estación →
    macrozona o None, de ``tipos.macrozona_de_celda`` de su celda (para lo crónico; VAL-19). Devuelve {"metricas":
    tabla ``COLUMNAS_SINCA``, "aviso": «uso/grupo» → {celda, punto, aviso, ganador}, "declaraciones": conteos}."""
    obs = _series_sinca(series, umbrales)
    estaciones = sorted(obs)
    tercil = _terciles(tpi, estaciones)
    productos_por_lugar = {}
    for lugar, productos in zip(LUGARES, (producto_celda, producto_punto)):
        normalizados = {(Uso(u).value, Candidato(c).value): t for (u, c), t in productos.items()}
        if len(normalizados) != len(productos):
            raise ValueError(f"SINCA: (uso, candidato) repetido en el producto de la {lugar}")
        productos_por_lugar[lugar] = normalizados
    if set(productos_por_lugar[LUGARES[0]]) != set(productos_por_lugar[LUGARES[1]]):
        raise ValueError("SINCA: la celda y el punto deben traer los mismos (uso, candidato)")
    claves = sorted(productos_por_lugar[LUGARES[0]])
    filas, declaraciones = [], {"estaciones": len(estaciones), "sin_tpi": len(estaciones) - len(tercil),
                                "cronico_sin_macrozonas": 0, "cronico_sin_macrozona_estaciones": 0}
    puntajes: dict[tuple[str, str, str, str], float] = {}
    for uso_txt, cand in claves:
        uso = Uso(uso_txt)
        if cand not in CANDIDATOS_USO[uso]:
            raise ValueError(f"SINCA: {cand} no es candidato de lo {uso.value}")
        variables = [v for v in _ORDEN_VARIABLES if (uso, v) in GRUPO_DE and v in SINCA_DE]
        for lugar in LUGARES:
            prod = _producto_sinca(productos_por_lugar[lugar][(uso_txt, cand)], f"producto_{lugar}")
            por_var: dict[str, dict[str, dict]] = {}
            for v in variables:
                por_var[v] = {}
                for est in estaciones:
                    trio = _par_sinca(obs[est], prod.get(est), v)
                    if trio is None:
                        continue
                    m = evaluacion(*trio, uso=uso, variable=v, umbrales=umbrales, zona=zona)
                    if m is not None:
                        por_var[v][est] = {**m, **m["descriptivos"]}             # VAL-21 en la red
            if uso is Uso.CRONICO and V_T in por_var:
                if macrozonas is None:
                    declaraciones["cronico_sin_macrozonas"] = 1
                else:
                    _neto_sinca(por_var[V_T], macrozonas, umbrales, declaraciones)
            for v in variables:
                cols = sorted(_columnas_de(uso, v) | ({"mse_h", "mae_h", "sesgo_h"} if v in VARIABLES_HORARIAS
                                                      else set()) | set(descriptivos_de(uso, v)))
                grupos = [(ESTRATO_RED, "", estaciones)] + [
                    (ESTRATO_TERCIL, t, [e for e in estaciones if tercil.get(e) == t])
                    for t in (str(i) for i in range(1, N_TERCILES + 1))]
                for estrato, valor, ests in grupos:
                    for col in cols:
                        vals = [por_var[v][e][col] for e in ests if e in por_var[v]]
                        n = sum(1 for x in vals if math.isfinite(x))
                        filas.append({"uso": uso.value, "candidato": cand, "lugar": lugar, "variable": v,
                                      "metrica": col, "estrato": estrato, "valor_estrato": valor,
                                      "valor": _resumir(vals, _RESUMEN_SINCA[col]), "n_estaciones": n})
                        if estrato == ESTRATO_RED:
                            puntajes[(uso.value, cand, lugar, v + "/" + col)] = _resumir(vals, _RESUMEN_SINCA[col])
    tabla = pd.DataFrame(filas, columns=list(COLUMNAS_SINCA)).astype(dict(COLUMNAS_SINCA))
    tabla.attrs = {"esquema": VERSION_SINCA}
    return {"metricas": tabla, "aviso": _avisos_sinca(puntajes, ganadores, e0), "declaraciones": declaraciones}


def _neto_sinca(por_estacion: dict[str, dict], macrozonas, umbrales, declaraciones) -> None:
    """VAL-5 en la red SINCA: el nivel neto y la anomalía de lo crónico, con la macrozona de cada estación (por
    ``tipos.macrozona_o_ninguna``, VAL-16 y VAL-19)."""
    minimo = _entero(umbrales, "MIN_ANIOS")
    if not isinstance(macrozonas, Mapping):
        raise ValueError("SINCA: «macrozonas» es estación → macrozona (o None)")
    faltan = sorted(set(por_estacion) - set(macrozonas))
    if faltan:
        raise ValueError(f"SINCA: faltan las macrozonas de las estaciones {faltan} (None si no tienen; VAL-19)")
    macro = {e: _macrozona(macrozonas[e], f"macrozona SINCA de {e}") for e in por_estacion}
    declaraciones["cronico_sin_macrozona_estaciones"] = max(declaraciones["cronico_sin_macrozona_estaciones"],
                                                            sum(1 for z in macro.values() if z is None))
    entran = {e: m["anuales"] for e, m in por_estacion.items()
              if macro[e] is not None and len(m["anuales"]) >= minimo}
    m_neto = medias_macrozona_anio(entran, macro)
    de_anom = {e: a for e, a in ((e, anomalias(x, umbrales)) for e, x in entran.items()) if a is not None}
    m_anom = medias_macrozona_anio(de_anom, macro)
    for e, x in entran.items():
        por_estacion[e]["mse_anual_neto"] = anual_neto(x, {y: v for (z, y), v in m_neto.items() if z == macro[e]})
        if e in de_anom:
            por_estacion[e]["mse_anomalia"] = anomalia_interanual(
                x, {y: v for (z, y), v in m_anom.items() if z == macro[e]}, umbrales)


def _avisos_sinca(puntajes, ganadores, e0) -> dict:
    """VAL-20: el aviso del 15 % por (uso, grupo), en la celda y en el punto."""
    if ganadores is None or e0 is None:
        return {}
    factor = 1 + constantes.valor("SINCA_AVISO_PCT") / 100
    salida = {}
    for k in sorted(ganadores, key=lambda x: tuple(_clave_uso_grupo(x))):
        uso, grupo = _clave_uso_grupo(k)
        if (uso, grupo) not in S_DEL_GRUPO:
            raise ValueError(f"aviso SINCA: lo {uso.value} no decide el grupo {grupo.value} (§6.1)")
        if k not in e0:
            raise ValueError(f"aviso SINCA: falta E0 de {k}")
        e0_k = _e0_del_uso(e0[k], uso, f"aviso SINCA de {uso.value}/{grupo.value}")
        variables_s = S_DEL_GRUPO[(uso, grupo)]
        if any(v not in SINCA_DE for v in variables_s):
            continue                                          # p: la red SINCA no trae presión (VAL-20)
        ganador = Candidato(ganadores[k]).value
        if ganador not in e0_k:
            raise ValueError(f"aviso SINCA: el ganador {ganador} de {uso.value}/{grupo.value} no está en E0")
        otros = [c for c in e0_k if c != ganador]
        por_lugar: dict[str, bool | None] = {}
        for lugar in LUGARES:
            S_v = [{c: puntajes.get((uso.value, c, lugar, f"{v}/{METRICAS[(uso, grupo)][v]['S']}"), _NAN)
                    for c in e0_k} for v in variables_s]
            if not otros or not all(math.isfinite(s[c]) for s in S_v for c in e0_k):
                por_lugar[lugar] = None
                continue
            if len(S_v) == 2:
                try:
                    S = puntaje_par(S_v[0], S_v[1], e0_k)
                except ValueError:                            # un mínimo 0: S_par no está definido
                    por_lugar[lugar] = None
                    continue
            else:
                S = S_v[0]
            por_lugar[lugar] = bool(S[ganador] > factor * min(S[c] for c in otros))
        evaluados = [x for x in por_lugar.values() if x is not None]
        salida[f"{uso.value}/{grupo.value}"] = {**por_lugar, "aviso": any(evaluados) if evaluados else None,
                                                "ganador": ganador}
    return salida
