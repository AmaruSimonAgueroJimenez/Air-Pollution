"""Ejecutable del producto combinado (§8, §10, Anexo B): la batería de M1 y las corridas de M2a, M3-4, M5 y M6.

Uso (desde ``scripts_modelo_1km``, siempre con el intérprete fijado, ``-B`` y los hilos en 1):
  ~/micromamba/envs/amb_v2/bin/python -B -m meteo_combinada.verificar_meteo_combinada --sintetico [--costo]
          [--solo PATRON …] [--commits COMMIT_AP COMMIT_APH]
  … --estaticos --addendum RUTA --entradas RUTA                                         (M2a)
  … --aplicar   --addendum RUTA --entradas RUTA [--etiqueta E] [--errata RUTA]          (M3-4)
  … --producir  --addendum RUTA --entradas RUTA [--etiqueta E]                          (M5)
  … --m6        --addendum RUTA --entradas RUTA [--etiqueta E]                          (M6)

Qué hay:
- ``main(argv, *, rutas=None, servicios=None)``: los cinco modos. ``rutas`` y ``servicios`` (el reloj de pared,
  ``micromamba list``, el medidor del costo, las funciones de ``orquestacion`` y la fábrica de M6) son sólo para las
  pruebas; nunca llegan por la línea de comandos.
- ``correr_bateria``: la batería de M1 (§5.3 del diseño; A32).
- ``negativas_m34(cfg)`` (§10, «M3-4 se niega a correr»), ``negativas_m6(cfg)`` (Anexo B, «M6 se niega a correr») y
  las de M2a y M5; cada una devuelve la lista de motivos (vacía: corre). ``orquestacion`` las llama antes que todo
  (``Cfg.negativas``) y este módulo también, antes de la frontera, para registrar el intento.
- ``Cerrojo``: ``intentos_aplicar.jsonl`` e ``intentos_m6.jsonl`` en ``LOCAL/meteo_combinada/v1/cerrojo/``, sólo
  agregado, encadenados por huella y cotejados con las carpetas de las corridas.
- ``Consola``: la consola como documento (D13, CEG-18): ningún número que no salga del texto o de las fuentes.

Dueño: I22 (ola 6; corregido tras la revisión independiente de la ola 6).
Lecturas propias (VER-n), para el addendum de M1:
- VER-23. **Reutilización EMC5 [delegada].** ``--costo-desde`` exige ``--costo-sha256`` y ``--costo``; carga el
  informe fijado como mediciones históricas, proyecta con la regla vigente y corre todas las pruebas nuevas. Declara
  procedencia y no modifica ni aprueba retroactivamente el original. Si no se verifica, el costo no se aprueba.
- VER-1. **La batería** (§5.3 del diseño; A32; MC-31). ``--sintetico`` descubre ``tests/`` (como ``unittest discover -s
  meteo_combinada/tests -t .``) y la corre entera bajo ``ceguera.SinRed`` y ``ceguera.RegistroAccesos`` en bloqueo:
  uno sobre /Volumes y los dos repositorios, que deja **leer** AP y APH (el código y los textos que leen las pruebas) y,
  de /Volumes, los insumos de S14 y del costo; otro, más interior, sobre lo que nadie de M1 abre del reloj (su
  publicación en AP y sus corridas en LOCAL); y un tercero, el más interior, sobre los insumos de datos de S14 y del
  costo, que se suelta **sólo mientras corre** ``test_salud.PruebasS14`` (MC-31: «sólo en esas dos pruebas»; la
  medición del costo va antes de la suite, sin él). Escribir en AP o APH queda bloqueado (CEG-3: una permitida sólo se
  lee). Los registros miran del más interior al más exterior (VER-14 del reloj): un acceso que niega antes el registro
  propio de una prueba no cuenta como acceso de la batería («negados_dentro»). ``ceguera.accesos`` debe ser 0. La
  salida de ``unittest`` y lo que las pruebas escriben en la consola quedan en memoria: no se muestran.
- VER-2. **Qué escribe la batería** (§5.3 del diseño; A32, A33; CEG-18 a CEG-20). Por ``salidas``, en su propia
  subcarpeta ``LOCAL/meteo_combinada/v1/m1/<AAAAMMDDTHHMMSSZ>/`` (ENT-4 admite ``m1/<sub>``; ADD-2), para que su
  ``sha256.json`` liste sólo lo de esa corrida: ``pruebas_m1.txt`` (documento: la huella del texto en la primera línea
  y la salida de ``unittest`` en verbosidad 2, sin trazas: de una falla sólo su identificador, porque una traza trae
  rutas de la carpeta de usuario, números de línea y valores; se vigila con los archivos de ``tests/`` como fuentes y,
  si aun así no pasa, va en su forma reducida, sin las descripciones ni los motivos de omisión), ``anexo_a2.json``
  (documento, ``constantes.anexo_a2`` del texto vigente), ``deriva_s6.json`` (resumen, ``tendencias.contenido_deriva_s6``),
  ``costo_m1.json`` (resumen, ``costo.contenido_costo``; con ``--costo``), ``resumen_m1.json`` (resumen: conteos,
  ``ceguera`` y huellas), ``sha256.json`` (procedencia) y, si la batería es completa, ``addendum_m1.json`` y
  ``addendum_m1.md`` (documento; ``addendum``), que citan la subcarpeta y si la batería aprobó: uno no aprobado no
  habilita ninguna corrida (VER-7). El addendum se arma antes del resumen, con la lista que ya trae la salida escrita
  de la batería y una huella provisional del resumen, y pasa la guarda del documento: si no se puede armar o no la
  pasa, la batería no aprueba («addendum») y el resumen lo dice. Después del sello se arma otra vez, con la lista
  completa (el resumen y ``sha256.json``), y se escribe. Límite declarado: si ese segundo armado falla (un archivo de la
  lista cambió entre los dos armados, o no se pudo escribir), el resumen ya escrito dice «aprobada», pero no hay
  addendum (ninguna corrida se habilita), la consola dice «no aprobada: addendum» y el proceso sale con 1.
- VER-3. **Cuándo se aprueba M1** (§10, M1: «S1-S16 aprobadas y guardadas; costo medido con la máquina libre; … la
  compuerta de deriva y el recorte fijados»; EMC4/D68 retira el veto por carga de esa condición histórica). ``resumen_m1.json["aprobada"]`` exige: la suite entera (sin ``--solo``),
  ninguna falla, error, falla esperada ni éxito inesperado; ninguna prueba omitida fuera de la lista cerrada
  ``OMISIONES_PERMITIDAS`` (identificador y comienzo del motivo: la de 2.500 m de D56 y la de las huellas de datos; la
  del cierre de M1 ya no se omite, porque ``EN_CURSO`` quedó vacía); **S14 corrida y aprobada**
  (``test_salud.PruebasS14.informe`` no nulo y la prueba entre los éxitos: una S14 omitida no se da por aprobada,
  H11); la compuerta de deriva calculada; el costo medido (``--costo``) con su recorte fijado (uno «pendiente» no
  aprueba: «recorte_pendiente», A39) y sus procesos por fase con su forma exacta («procesos_por_fase», VER-22); el
  addendum armado (VER-2); ``ceguera.accesos`` = 0 y ningún proceso vivo al terminar; el intérprete fijado
  (``entorno.comprobar_interprete`` y la huella de ``micromamba list``, FIJ-3) y el código fijado sin diferencias
  (``fijados.comprobar_codigo_fijado``); la lista cerrada armada; y **el código del paquete y de ``tests/`` (y sus dos
  documentos) sin cambios durante la batería** (sus huellas se toman antes de descubrir la suite y se comparan al
  terminar). Si no se aprueba,
  ``motivos`` dice por qué y el proceso sale con 1.
- VER-4. **La deriva y S14 salen de las pruebas que corre la batería**, en el mismo proceso: la red de S6 calculada
  por ``test_tendencias`` (``_S6_CACHE``: D15, S6-1 a S6-6) pasa por ``tendencias.compuerta_deriva`` y
  ``contenido_deriva_s6`` tal como en ``test_s06_compuerta_de_deriva``; el informe de S14 es
  ``test_salud.PruebasS14.informe``. Así no se repite el cálculo (≈ 195 s) ni se abren otra vez los insumos de S14.
- VER-5. **FIJ-3.** ``--sintetico`` y las corridas reales corren ``~/.local/bin/micromamba list -n amb_v2`` (como
  ``m0/preparar_m0.interprete``) y pasan su texto a ``fijados``. Este módulo lanza, en sólo lectura, ``micromamba`` y
  ``git`` (CEG-7: «sólo ``orquestacion`` lanza procesos» se lee como el reparto del cómputo).
- VER-6. **Git, sólo lectura y sin red** (§10, testigo externo; como VER-2 y VER-3 del reloj). Siempre ``git
  --no-optional-locks --literal-pathspecs -c core.fsmonitor=false`` con ``GIT_OPTIONAL_LOCKS=0`` (sin tocar el índice)
  y la referencia local ``origin/main``. Un archivo está «confirmado en git» si es idéntico, byte a byte, a su versión
  en el último commit que lo tocó (``git log -n 1``, ``git show``) y ese commit es antecesor de ``origin/main`` de su
  repositorio. Las «rutas del protocolo» son: las de la lista cerrada que caen en AP o APH, la carpeta del paquete, la
  auditoría del producto (``APH/auditoria/20261023/meteo_combinada``, con sus enmiendas), los archivos pasados por
  argumento y el registro de C5 con sus carpetas, la errata con su prueba y su sello, y el espejo del paquete en APH
  cuando existe (la misma ruta relativa); en M6, además, la carpeta de la publicación y los archivos que confirma el
  Anexo B. Sobre ellas se exige ``git status --porcelain --untracked-files=all`` vacío y ``git diff --quiet origin/main``
  en cada repositorio: el código y los textos del disco son los del remoto (el testigo externo).
- VER-7. **M3-4 se niega a correr** (§10), juntando todos los motivos: el **contenido del addendum** (las claves exactas
  de ``addendum.CLAVES``, el texto vigente v2.4 con su huella, la batería aprobada y su subcarpeta, el recorte en
  {«mod11», «mod23»} desde los umbrales, la deriva fijada, los procesos por fase de D59 con su forma exacta y el
  veredicto del costo igual al recorte (VER-22), y todas las claves de ``addendum.claves_lista_cerrada`` con
  las seis salidas de la batería y las huellas fijadas del código y de la clausura); la lista cerrada (cada huella, del
  disco, y que cubra todo ``.py`` del paquete); el intérprete (VER-16); el árbol limpio e igual a ``origin/main``; los
  commits de M1 de AP y de APH antecesores de ``origin/main``; el addendum, las entradas, la errata (y su prueba y su
  sello) y el registro de C5 confirmados en git; la política de RELOJ (C5): sin registro, con una forma o una sha256
  distintas (``ErrorC5`` de ``leer_registro_c5`` y ``leer_politica_reloj``), ``post_hoc = true``, ``errata_post_c4 =
  true`` sin errata confirmada y lo demás de ``comprobar_c5`` y ``declaracion_c5``; la política y ``artefactos_
  evaluados`` publicados confirmados en git en AP, ``commit_c5`` antecesor de ``origin/main`` y, sin errata, con esas
  sha256 en ese commit; la errata confirmada del registro de C5, comprobada en git; el cerrojo (VER-9); MC-09, el anexo
  «Registro de la red v2» confirmado en git y con, en su clave ``huellas``, la de ``pliegues_v2_red2.json`` de las
  entradas (VER-15); y las huellas de datos de las entradas, iguales a las fijadas (``fijados.HUELLAS_DATOS``). La del
  registro de M2a la hace ``orquestacion`` (P119, ORQ-38): aquí sólo se exige que esté en la lista, por las entradas.
- VER-8. **M6 se niega a correr** (Anexo B): el contenido y la lista cerrada del addendum; el intérprete; las huellas
  de ``decision.json``, de ``sha256.json`` y del recibo de la corrida de M5 iguales a las publicadas en
  ``AP/config/meteorologia/meteo_combinada/v1/`` (``salidas.carpeta_publicacion``), y cada producto que lista el
  ``sha256.json`` publicado con esa huella en la carpeta de la corrida (los sólo agregado, por sus primeros bytes;
  ``m6/`` no entra); el árbol limpio e igual a ``origin/main``; el commit de M1 en ``origin/main``; los archivos de la
  Enmienda 2 ambiental, de la enmienda de la DMC, de ``correr_v2.py``, de ``config_v2.json`` y del código de la fábrica
  v2 (``confirmados_m6`` de las entradas) confirmados en git, y los de AP también en su espejo de APH, con los mismos
  bytes; MC-09 con los paneles ``panel_{pm25,no2}_red2.parquet``; el cerrojo de M6; la fábrica (``Cfg.fabrica_m6``,
  diferencia 33); y ninguna errata de M6 (VER-19).
- VER-9. **El cerrojo** (§8 y §10; P92, que decide I22; P118). ``intentos_aplicar.jsonl`` e ``intentos_m6.jsonl`` son
  sólo agregado (``salidas.agregar_linea``) y cada línea lleva la huella de todo lo anterior (``previa_sha256``, como
  el reloj): una línea borrada o cambiada rompe la cadena y nada corre. Eventos: «intento» (fecha UTC, etiqueta, huella
  de la corrida de ``orquestacion.huella_de_corrida``, las huellas de los archivos pasados por argumento y la del
  intérprete), «negada» (con los motivos; antes de la frontera: no cuenta como corrida, P118), «inicio» (las negativas
  pasaron) y «fin» («sellada», «detenida_por_alarma», «abortada», «negada_por_orquestacion» o «error», si cruzó la
  frontera, el tipo del error y los procesos vivos). **Corrida confirmatoria** = un «inicio» que cruzó la frontera (su
  carpeta trae ``avance.jsonl``, ORQ-35); es **terminal** si terminó sellada o detenida por una alarma (§10: la única
  detención). Una confirmatoria no terminal se reanuda con la misma etiqueta y la misma huella de corrida, también otro
  día (§10: «Reanudar la misma corrida»); cualquier otra exige una errata confirmada (``--errata``) no usada, y la
  corrida nueva lleva ``_ERRATA<n>``.
- VER-10. **El cerrojo no se puede borrar ni recortar sin que se note** (revisión de la ola 6). Vive en
  ``LOCAL/meteo_combinada/v1/cerrojo/`` (P92; la raíz que ``salidas`` admite para eso, PED-2), visible para toda
  corrida. En cada lectura se cotejan las carpetas ``v1/HUMAN*_METEO_COMB_*/`` (y su ``m6/`` para el de M6): cada una
  con ``avance.jsonl`` debe tener su «inicio» en el cerrojo; cada copia de ``intentos_*.jsonl`` debe ser un prefijo del
  cerrojo; cada una con ``recibo_corrida.json`` debe tener su «fin» terminal; y un cerrojo ausente con carpetas
  presentes detiene. Antes de llamar a ``orquestacion`` (y por lo tanto antes del sello), el cerrojo entero se copia a
  la carpeta de la corrida, como prefijo de lo que ya hubiera: el sello (``sha256.json``, que el recibo cita) lleva así
  la huella del cerrojo hasta la línea «inicio», y el testigo externo de M3-4 la ata. La línea «fin» va sólo al
  cerrojo, porque agregarla a la carpeta sellada la abriría. Límites declarados: una corrida sellada cuyo proceso
  murió antes de escribir su «fin» deja la carpeta con recibo y sin «fin», y nada corre hasta revisarla a mano; y una
  corrida que ``orquestacion`` niega antes de la frontera deja en su carpeta la copia del cerrojo e ``interprete.json``
  (procedencia y resumen, sin resultados), que la próxima corrida de esa etiqueta continúa.
- VER-11. **Un solo intento a la vez.** Mientras corre M3-4 o M6 se retiene un ``flock`` exclusivo, sin bloqueo, sobre
  la carpeta del cerrojo (abierta en sólo lectura); otro intento que llega mientras tanto queda registrado («negada»,
  «corrida_en_curso») y no corre. Cada línea se agrega con el archivo del cerrojo bajo un ``flock`` corto, después de
  releer y verificar la cadena. Límite declarado: dos primeros intentos simultáneos, antes de que exista el archivo,
  pueden romper la cadena; entonces nada corre hasta revisarla a mano.
- VER-12. **La etiqueta** (§10: ``HUMAN<AAAAMMDD>_METEO_COMB_1``; ENT-4, ENT-8). La fecha es la UTC del día de la
  corrida (como el reloj). M3-4 reanuda la etiqueta de su confirmatoria pendiente si la hay (con la misma errata, si es
  la corrida de una errata); si no, ``HUMAN<hoy UTC>_METEO_COMB_1`` y, con una errata n, ``…_ERRATA<n>``. ``--etiqueta``
  sólo admite ésa o la pendiente; otra se niega. M5 y M6 siguen la carpeta de la última M3-4 sellada del cerrojo
  (``--etiqueta`` debe ser ésa).
- VER-13. **Cómo se arma ``Cfg``** (MC-54, ORQ-1, A30, PED-11). Del addendum: la lista cerrada (``Cfg.huellas``), el
  recorte («mod23» → ``Cfg.recorte = True``), la compuerta de deriva (``Cfg.deriva``) y los procesos por fase
  (``Cfg.procesos_por_fase``, VER-22); si el addendum los trae pendientes o sin su forma, la corrida se arma con
  valores que no corren (sin recorte, B y AB fuera y 1 proceso en cada fase) y las negativas la niegan (VER-7). Del
  archivo de entradas (``--entradas``, esquema «meteo-combinada-entradas/1»: la compuerta, ``entradas`` por
  alias como las de ``orquestacion.ENTRADAS_*`` y las huellas de sus datos), lo demás; ``Cfg.procesos`` = D2
  (``opciones_m0``); los cinco pares de §6.1; ``Cfg.permitidas`` = todo lo de ``Cfg.entradas`` que cae bajo /Volumes y,
  en M3-4, la carpeta de la DMC (lo que leen los trabajadores, PED-11); ``Cfg.negativas`` = la de la compuerta (un
  objeto de este módulo, para que ``orquestacion.identidad_funcion`` la identifique). ``Cfg.entradas`` lleva además, por
  alias, el addendum, el archivo de entradas y la errata, y la identidad del intérprete (``orquestacion`` no los lee;
  entran a la huella de la corrida). La fábrica de M6 (``{modulo, funcion}`` de las entradas) se carga con su huella y
  dentro del aislamiento (VER-14), con un nombre de módulo que sale de esa huella.
- VER-14. **El aislamiento de las corridas reales** (§8: «Sólo lectura de /Volumes y sin red»; §1.9). Las negativas
  corren bajo ``SinRed``; M2a a M6 corren bajo ``SinRed`` y un ``RegistroAccesos`` en bloqueo sobre /Volumes y los
  repositorios que deja leer AP, APH y ``Cfg.permitidas``, y otro sobre lo del reloj: sus corridas en LOCAL nunca, y de
  su publicación en AP sólo, en M3-4, la política, ``artefactos_evaluados`` y el informe de donde sale K2. Al terminar
  se cuentan los procesos vivos (§8: «no quedan procesos vivos»): si queda alguno, el resultado lo dice y sale con 1.
  Toda excepción se captura: sale por la consola y el cerrojo registra el resultado con su tipo. Los trabajadores de
  ``orquestacion`` llevan su propio registro (ORQ-10); los procesos hijos (los trabajadores, ``git``, ``micromamba``)
  no pasan por el gancho de este proceso.
- VER-15. **El registro de la red v2 por su estructura** (MC-09; R22, paso 4). El anexo es un JSON con una clave
  ``huellas`` {ruta por alias: sha256}; la de ``pliegues_v2_red2.json`` (y en M6 las de los dos paneles) debe ser la de
  las entradas. Una subcadena con la huella en un texto no basta. Si R22 fija otra forma, cambia sólo
  ``_huellas_registro_red`` (pregunta P-VER-6).
- VER-16. **El intérprete en las corridas reales** (§8: «el código, la configuración y ``micromamba list``» en la
  cadena de huellas; FIJ-3). Cada corrida comprueba ``entorno.comprobar_interprete`` y la huella de ``micromamba
  list`` frente a ``fijados.SHA_MICROMAMBA_LIST``, como negativa. Su identidad va a ``Cfg.entradas`` (y por ella a la
  huella de la corrida) y a ``interprete.json`` (resumen) en la carpeta de la corrida, escrito antes de llamar a
  ``orquestacion`` con la huella que ya trae ``Cfg.huellas``: el recibo la cita.
- VER-17. **El costo** (§8.1 del diseño; A32; COS-1 a COS-13). Con ``--costo``, ``costo.medir`` (con
  ``real_era5=True``), ``proyectar``, ``recorte`` y ``contenido_costo`` corren **antes** de la suite, bajo el mismo
  aislamiento, para no sumar la suite a la medición; EMC4/D68 deja la carga como diagnóstico no excluyente.
  ``costo_m1.json`` (resumen) lleva lo medido y el addendum sólo su ruta, su huella y el recorte. Si la medición no
  corre por otro error, el resumen dice el tipo del error y M1 no se aprueba. La carga real no se falsea ni hace
  pasar una máquina ocupada por libre; los tiempos y la proyección pueden variar por trabajo concurrente.
- VER-18. **El directorio de trabajo** (CEG-4: «Un acceso por descriptor (un entero) no tiene ruta»). Mientras
  duran la batería y las corridas reales, el directorio de trabajo es la carpeta temporal del sistema y vuelve al
  terminar (``directorio_neutro``). ``shutil.rmtree`` (y con él ``tempfile.TemporaryDirectory``) borra con nombres
  relativos a un descriptor de carpeta, y ``ceguera`` junta un nombre relativo con el directorio actual: con el
  directorio en ``scripts_modelo_1km`` (dentro de AP), cada borrado de una carpeta temporal parecía una escritura en
  AP y se negaba (≈ 26.000 en un ensayo). Las pruebas no dependen del directorio de trabajo (``discover`` recibe rutas
  absolutas).
- VER-19. **La errata de M6** (§10, «una corrida nueva exige una errata … La corrida nueva lleva ``_ERRATA<n>``»;
  Anexo B, «una sola vez, con registro de intentos»). Una errata de M6 lleva su propia numeración («compuerta»: «m6»)
  y tendría que correr en su propia carpeta de la misma M3-4 (``<ETIQUETA>/m6_ERRATA<n>/``), que ``orquestacion`` y
  ``salidas`` todavía no admiten (sólo ``<ETIQUETA>/m6``, donde otra huella detiene: ORQ-8). Rige la más estricta: M6
  se niega con una errata (pregunta P-VER-5, PED-5).
- VER-20. **M2a y M5** (§10). M2a (``--estaticos``) exige lo común (el contenido y la lista cerrada del addendum de
  M1, el intérprete y las huellas de datos fijadas) y la línea de cierre de C2 de RELOJ (``cierre_c2`` de las
  entradas, el catálogo fijo de §10), confirmada en git y con su esquema «dmc-reloj-cierre-c2/1». M5 (``--producir``)
  exige lo común y su M3-4 sellada en el cerrojo, cuya etiqueta sigue (VER-12).
- VER-21. **La consola** (D13; CEG-18). Todo lo que se muestra pasa por ``ceguera.ConsolaDocumento``: la primera línea
  cita la huella del texto vigente y una línea con un número que no sale del texto ni de las fuentes se reemplaza por
  un aviso fijo. Después de la frontera, de un error sólo se muestra su tipo.
- VER-22. **Los procesos por fase** (D59, respuesta a P145; A39; P146, la extensión a M5). ``costo_m1.json`` lleva en
  su raíz «procesos_por_fase» = {compuerta: {fase: n}}: de cada fase que reparte (``orquestacion.FASES_REPARTO``), el
  mayor número de procesos que cabe en memoria, de 1 a 8, o 0 si no cabe ni con 1, y entonces el recorte queda
  «pendiente». La batería los pasa al addendum con el costo (``ref(COSTO_M1, recorte=…, procesos_por_fase=…)``). Con el
  costo medido, no aprueba si el recorte queda «pendiente» («recorte_pendiente»: el addendum sale igual, con el recorte
  y el costo «pendiente») ni si los procesos por fase no tienen la forma exacta («procesos_por_fase»): las compuertas y
  las fases de ``FASES_REPARTO``, y cada n un entero (no bool) de 1 a ``constantes.valor("PROCESOS")``. ``_armar`` pasa
  a ``Cfg.procesos_por_fase`` los del addendum si tienen esa forma; si no, 1 en cada fase, y la negativa «addendum»
  niega (los procesos por fase de D59 no están fijados), como con el recorte y la deriva (VER-13). D59 modifica D2 sólo
  en esa fase y no cambia ningún bit por sí mismo (S9); la pared que se vuelve a proyectar con esos procesos decide el
  recorte de §4.9 (§8: «fijado en el addendum de M1 desde la proyección»), y si con P = 8 fuera otro, ``costo_m1.json``
  lo dice en una nota de su veredicto (P147). Rige lo que hace el código.
Preguntas para el autor (P-VER-n; rige la más estricta):
- P-VER-1. Cita: Anexo B, «M6 se niega a correr … si: … alguna huella de la lista cerrada del addendum de M1 difiere» y
  «los commits … que confirman … la enmienda de la DMC, ``correr_v2.py``, ``config_v2.json`` y el código de la fábrica
  de producción v2». Problema: la lista cerrada de M1 trae ``correr_v2.py`` y ``config_v2.json`` (D51); si la enmienda
  de la DMC o la fábrica los cambian, M6 se niega siempre. Rige (la literal): M6 se niega; hace falta un addendum
  nuevo (o una errata) que fije las huellas posteriores. Propuesta: que la enmienda de la DMC fije, como D51, las
  huellas vigentes de esos dos archivos para M6.
- P-VER-2. Cita: §10, «el commit de M1 no es antecesor de ``origin/main`` de APH»; MC-54, «``commit_m1`` de AP y de
  APH». Rige (la más estricta): los dos commits, cada uno en ``origin/main`` de su repositorio. Propuesta: ratificarlo.
- P-VER-3. Cita: §10, «una corrida nueva exige una errata». Problema: el texto no dice si una errata de M3-4 sin una
  corrida confirmatoria previa vale. Rige (la más estricta): no; una errata sólo habilita la corrida que reemplaza a
  una confirmatoria.
- P-VER-4. Cita: §5.3 del diseño, «``resumen_m1.json``, con conteos, ``ceguera.accesos`` (debe ser 0)». Problema: las
  pruebas de ``ceguera`` intentan a propósito conexiones de red dentro de su propio ``SinRed``, y el de la batería las
  anota también (los intentos se niegan antes de ocurrir). Rige: se cuentan en ``ceguera.red_intentos`` y no detienen
  la aprobación; la red nunca llega a usarse.
- P-VER-5. Cita: §10 y el Anexo B (VER-19). Problema: si la corrida confirmatoria de M6 falla después de la frontera,
  hoy no hay dónde correr la de su errata. Rige (la más estricta): M6 no se repite. Propuesta: la errata de M6, con su
  propia numeración, en ``<ETIQUETA>/m6_ERRATA<n>/`` de la misma M3-4, con su línea en ``intentos_m6.jsonl``.
- P-VER-6. Cita: R22, paso 4, «Anexo «Registro de la red v2» … Lleva las huellas de R2, del panel, de los pliegues…».
  Problema: el texto no fija su forma. Rige (VER-15): un JSON con «huellas» {ruta por alias: sha256}. Propuesta: que
  R22 lo escriba así.
Pedidos (PED-n):
- PED-1 (coordinador; hecho). ``politicas``, ``tendencias``, ``salud``, ``tipos`` y ``constantes`` en
  ``DEPENDENCIAS["verificar_meteo_combinada"]`` y en §1 del diseño.
- PED-2 (I17, ``salidas``; hecho). La raíz ``LOCAL/meteo_combinada/v1/cerrojo`` para ``intentos_*.jsonl`` (P92).
- PED-3 (I21). Que ``costo.medir`` cree y borre su carpeta temporal: este módulo no puede borrar (§0, regla 8). Hasta
  entonces la batería le pasa una ruta bajo la carpeta temporal del sistema, nombrada en el resumen.
- PED-4 (I4, ``ceguera``; con I1 e I17). Bajo el registro de la batería, ocho pruebas hacían, fuera de sus propios
  registros, lo que ``ceguera`` anota y niega como acceso: crear un enlace simbólico hacia /Volumes o AP y abrir una
  ruta que pasa por «/Volumes/..». Propuesta (en curso en I4): que crear un enlace no cuente como acceso a su destino y
  que lo negado por un registro interior no cuente en el exterior. En el ensayo de la revisión de la ola 6 quedaban
  dos: ``test_salidas.PruebasS10Salidas.test_s10_nada_bajo_volumes`` (su ``_archivos`` sigue los enlaces con
  ``is_file`` y consulta /Volumes; I4 lo anotó como pedido a I17) y uno de ``test_ceguera.PruebasS10Ceguera``.
- PED-5 (I20 e I17). La carpeta ``<ETIQUETA>/m6_ERRATA<n>/`` para la errata de M6 (VER-19, P-VER-5).
Diferencias con el diseño (§3): ``main(argv, *, rutas=None, servicios=None)``; ``negativas_m34(cfg)`` y
``negativas_m6(cfg)`` leen el addendum, las entradas, la errata y el intérprete de ``Cfg.entradas`` (VER-13);
``Cerrojo(rutas, compuerta)``; nuevos: ``correr_bateria``, ``negativas_m2a``, ``negativas_m5``, ``Negativas``,
``Consola``, ``Servicios``, ``leer_entradas``, ``leer_errata``, ``registro_en_git``, ``arbol_limpio``,
``micromamba_list`` y ``directorio_neutro``; la subcarpeta de cada batería en ``m1/`` (VER-2).
Depende de: orquestacion, salidas, costo, addendum, ceguera, fijados, umbrales, entorno, politicas, tendencias, salud,
tipos y constantes (PED-1).
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse  # noqa: E402
import contextlib  # noqa: E402
import fcntl  # noqa: E402
import fnmatch  # noqa: E402
import functools  # noqa: E402
import hashlib  # noqa: E402
import importlib  # noqa: E402
import importlib.util  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402
import uuid  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path, PurePosixPath  # noqa: E402
from types import MappingProxyType  # noqa: E402
from typing import Any, Callable, Iterable, Mapping, Sequence  # noqa: E402

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # scripts_modelo_1km, para «import meteo_combinada»

from meteo_combinada import addendum, ceguera, constantes, entorno, fijados, orquestacion, salidas  # noqa: E402
from meteo_combinada import umbrales  # noqa: E402

# ---------------------------------------------------------------------------
# Nombres
# ---------------------------------------------------------------------------
PAQUETE = Path(__file__).resolve().parent
RAIZ_CODIGO = PAQUETE.parent                                    # scripts_modelo_1km
PRUEBAS = PAQUETE / "tests"
MICROMAMBA = Path.home() / ".local" / "bin" / "micromamba"     # m0/preparar_m0.interprete (VER-5)
ENTORNO_MICROMAMBA = "amb_v2"
MODOS = ("sintetico", "estaticos", "aplicar", "producir", "m6")
COMPUERTA_DE_MODO = MappingProxyType({"estaticos": "m2a", "aplicar": "m34", "producir": "m5", "m6": "m6"})
NOMBRE_COMPUERTA = MappingProxyType({"m2a": "M2a", "m34": "M3-4", "m5": "M5", "m6": "M6"})
CERROJOS = MappingProxyType({"m34": "intentos_aplicar.jsonl", "m6": "intentos_m6.jsonl"})
SUBCARPETA_CERROJO = salidas.CARPETA_CERROJO                    # LOCAL/meteo_combinada/v1/cerrojo (VER-10, PED-2)
ESQUEMA_CERROJO = "meteo-combinada-intentos/1"
ESQUEMA_RESUMEN = "meteo-combinada-resumen-m1/1"
ESQUEMA_ENTRADAS = "meteo-combinada-entradas/1"
ESQUEMA_ERRATA = "meteo-combinada-errata/1"
ESQUEMA_INTERPRETE = "meteo-combinada-interprete/1"
ESQUEMA_CIERRE_C2 = "dmc-reloj-cierre-c2/1"                     # VER-1 del reloj: cierre_descarga.json (VER-20)
INTERPRETE_JSON = "interprete.json"                             # VER-16
PRUEBAS_M1, RESUMEN_M1, DERIVA_S6, ANEXO_A2, COSTO_M1, _ = addendum.SALIDA_BATERIA
SHA256_JSON = salidas.SHA256_JSON
TERMINALES = ("sellada", "detenida_por_alarma")                 # VER-9
POR_IMPLEMENTAR = "por implementar"
CLAVES_RESERVADAS = ("addendum", "config_entradas", "errata", "interprete")   # VER-13: las pone este módulo
LINEA_OMITIDA = "(línea omitida: traía un número que no sale del texto ni de las fuentes; CEG-18)"
RELOJ_PUBLICACION = "config/meteorologia/reloj_dmc"             # AP: lo que M1 no abre del reloj (VER-1)
RELOJ_CORRIDAS = "modelado_1km/verificacion_reloj_dmc"          # LOCAL
CONFIRMADOS_M6 = ("enmienda_2_ambiental", "enmienda_dmc", "correr_v2", "config_v2", "fabrica_v2")   # Anexo B
# VER-3: las únicas omisiones que no detienen la aprobación (identificador → comienzo del motivo).
OMISIONES_PERMITIDAS = MappingProxyType({
    "meteo_combinada.tests.test_homogeneidad.PruebasS4.test_s04_traslado_de_15_m_a_2500_m": "P47 (D56)",
    "meteo_combinada.tests.test_fijados.PruebasHuellas.test_huellas_9_3_de_datos": "lee datos reales",
})
_SE_NIEGA = "se niega a correr"                                 # el texto de una negativa de orquestacion (VER-9)
_PATRON_S = re.compile(r"test_s(\d{2})_")
_SHA = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_FECHA = re.compile(r"\d{4}-\d{2}-\d{2}")
_ANCHO_ESTADO_GIT = 3              # no-umbral: las dos letras de estado y el espacio de «git status --porcelain»
_TIEMPO_GIT_S = 120                # no-umbral: espera de un git de sólo lectura
_TIEMPO_MICROMAMBA_S = 120         # no-umbral: espera de micromamba list
_CITADOS = 5                       # no-umbral: ejemplos citados en un motivo
_SOLO_AGREGADO = salidas.SOLO_AGREGADO


class ErrorCerrojo(RuntimeError):
    """El cerrojo está ilegible, fue reescrito o recortado, o lo tiene otra corrida: nada corre (VER-9 a VER-11)."""


class ErrorConfiguracion(ValueError):
    """El addendum, las entradas, la errata o la etiqueta no tienen la forma fijada (VER-12, VER-13)."""


@dataclass(frozen=True)
class Falla:
    """Un motivo de negativa: un código sin espacios (va al cerrojo) y su texto (va a la consola)."""
    motivo: str
    texto: str

    def __str__(self) -> str:
        return f"{self.motivo}: {self.texto}"


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def micromamba_list() -> str:
    """El texto de ``micromamba list -n amb_v2`` (FIJ-3; VER-5), en sólo lectura."""
    r = subprocess.run([str(MICROMAMBA), "list", "-n", ENTORNO_MICROMAMBA], capture_output=True, text=True,
                       check=True, timeout=_TIEMPO_MICROMAMBA_S)
    return r.stdout


@dataclass
class Servicios:
    """Lo que las pruebas reemplazan (nunca la línea de comandos): el reloj de pared, ``micromamba list``, el medidor
    del costo (el módulo ``costo``), las corridas de ``orquestacion`` y la fábrica de M6."""
    ahora: Callable[[], datetime] = _ahora
    micromamba: Callable[[], str] = micromamba_list
    medidor: Any = None
    ejecutores: Mapping[str, Callable] | None = None
    fabrica_m6: Callable | None = None

    def ejecutor(self, compuerta: str) -> Callable:
        if self.ejecutores is not None and compuerta in self.ejecutores:
            return self.ejecutores[compuerta]
        return {"m2a": orquestacion.correr_m2a, "m34": orquestacion.correr_m34, "m5": orquestacion.correr_m5,
                "m6": orquestacion.correr_m6}[compuerta]

    def costo(self):
        if self.medidor is None:
            from meteo_combinada import costo
            self.medidor = costo
        return self.medidor


def _fecha_utc(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dia_utc(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y%m%d")


# ---------------------------------------------------------------------------
# Consola (VER-21: D13, CEG-18)
# ---------------------------------------------------------------------------
class Consola:
    """La consola como documento (D13; CEG-18): la primera línea cita la huella del texto, y cada línea siguiente se
    muestra sólo si sus números salen del texto o de las fuentes; si no, se reemplaza por un aviso fijo."""

    def __init__(self, referencia: "ceguera.ReferenciaDocumento"):
        self._c = ceguera.ConsolaDocumento(referencia)
        self.lineas: list[str] = []
        self._mostrar(self._c.encabezado())

    def _mostrar(self, linea: str) -> None:
        self.lineas.append(linea)
        print(linea, file=sys.stdout, flush=True)

    def __call__(self, texto: str) -> None:
        for linea in str(texto).splitlines() or [""]:
            try:
                self._mostrar(self._c.linea(linea))
            except ceguera.SalidaProhibida:
                self._mostrar(LINEA_OMITIDA)


# ---------------------------------------------------------------------------
# Git, sólo lectura (VER-6)
# ---------------------------------------------------------------------------
def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    """git de sólo lectura: sin candados opcionales, sin fsmonitor, sin preguntas y con rutas literales."""
    entorno_git = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
    orden = ["git", "--no-optional-locks", "--literal-pathspecs", "-c", "core.fsmonitor=false", "-C", str(repo), *args]
    try:
        return subprocess.run(orden, capture_output=True, env=entorno_git, timeout=_TIEMPO_GIT_S, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(orden, -1, b"", type(e).__name__.encode("ascii"))


def _es_antecesor(repo: Path, antecesor: str, descendiente: str = "origin/main") -> bool | None:
    """True o False; None si git no lo puede decidir (commit o referencia inexistente)."""
    r = _git(repo, "merge-base", "--is-ancestor", antecesor, descendiente)
    return True if r.returncode == 0 else False if r.returncode == 1 else None


def _corto(sha: str | None) -> str:
    return (sha or "—")[:fijados.ABREVIATURA] + "…"


def _repo_y_relativa(alias_: str, rutas) -> tuple[str, Path, str]:
    raiz, _, resto = str(alias_).partition("/")
    if raiz not in ("AP", "APH") or not resto or ".." in PurePosixPath(resto).parts:
        raise ErrorConfiguracion(f"{alias_}: no es una ruta por alias de AP o APH")
    return raiz, Path(rutas.ap if raiz == "AP" else rutas.aph), resto


def registro_en_git(alias_: str, rutas) -> list[str]:
    """VER-6: el archivo es su versión del último commit que lo tocó, y ese commit está en ``origin/main``."""
    try:
        nombre, repo, rel = _repo_y_relativa(alias_, rutas)
    except ErrorConfiguracion as e:
        return [str(e)]
    try:
        with open(repo / rel, "rb") as f:
            datos = f.read()
    except OSError:
        return [f"{alias_}: no se puede leer"]
    r = _git(repo, "log", "-n", "1", "--format=%H", "--", rel)
    commit = r.stdout.decode("ascii", errors="replace").strip()
    if r.returncode != 0 or not _COMMIT.fullmatch(commit):
        return [f"{alias_}: no está confirmado en git"]
    motivos = []
    r = _git(repo, "show", f"{commit}:{rel}")
    if r.returncode != 0 or r.stdout != datos:
        motivos.append(f"{alias_}: difiere de su versión en git ({_corto(commit)})")
    if _es_antecesor(repo, commit) is not True:
        motivos.append(f"{alias_}: su commit ({_corto(commit)}) no está en origin/main de {nombre}")
    return motivos


def _sha_en_commit(repo: Path, commit: str, rel: str) -> str | None:
    r = _git(repo, "show", f"{commit}:{rel}")
    return entorno.sha256_bytes(r.stdout) if r.returncode == 0 else None


def archivo_en_commit(alias_: str, rutas, commit: str, sha256: str) -> list[str]:
    """La errata confirmada del registro de C5 (POL-2): el archivo con esa sha256, igual en ese commit, y el commit
    antecesor de ``origin/main`` (VER-7)."""
    try:
        nombre, repo, rel = _repo_y_relativa(alias_, rutas)
    except ErrorConfiguracion as e:
        return [str(e)]
    motivos = []
    try:
        with open(repo / rel, "rb") as f:
            if entorno.sha256_bytes(f.read()) != sha256:
                motivos.append(f"{alias_}: su sha256 no es la que cita el registro de C5")
    except OSError:
        motivos.append(f"{alias_}: no existe")
    if not isinstance(commit, str) or not _COMMIT.fullmatch(commit):
        return motivos + [f"{alias_}: el commit no es de 40 hexadecimales"]
    if _sha_en_commit(repo, commit, rel) != sha256:
        motivos.append(f"{alias_}: no está con esa sha256 en el commit {_corto(commit)}")
    if _es_antecesor(repo, commit) is not True:
        motivos.append(f"{alias_}: el commit {_corto(commit)} no está en origin/main de {nombre}")
    return motivos


def _por_repo(rutas, rutas_protocolo: Iterable[str]) -> tuple[dict[str, list[str]], list[str]]:
    motivos: list[str] = []
    por_repo: dict[str, set[str]] = {"AP": set(), "APH": set()}
    for a in rutas_protocolo:
        try:
            nombre, _, rel = _repo_y_relativa(a, rutas)
        except ErrorConfiguracion as e:
            motivos.append(str(e))
            continue
        por_repo[nombre].add(rel)
    return {k: sorted(v) for k, v in por_repo.items()}, motivos


def arbol_limpio(rutas, rutas_protocolo: Iterable[str]) -> list[str]:
    """VER-6: ``git status --porcelain --untracked-files=all -- <rutas>`` vacío en AP y APH (§10)."""
    por_repo, motivos = _por_repo(rutas, rutas_protocolo)
    for nombre, repo in (("AP", Path(rutas.ap)), ("APH", Path(rutas.aph))):
        if not por_repo[nombre]:
            continue
        r = _git(repo, "status", "--porcelain", "--untracked-files=all", "--", *por_repo[nombre])
        if r.returncode != 0:
            motivos.append(f"{nombre}: git status no se pudo correr")
            continue
        sucias = [ln[_ANCHO_ESTADO_GIT:] for ln in r.stdout.decode("utf-8", errors="replace").splitlines()
                  if ln.strip()]
        if sucias:
            motivos.append(f"{nombre}: el árbol no está limpio en las rutas del protocolo: "
                           + ", ".join(sucias[:_CITADOS]))
    return motivos


def igual_al_remoto(rutas, rutas_protocolo: Iterable[str]) -> list[str]:
    """VER-6: ``git diff --quiet origin/main -- <rutas>`` en AP y APH: lo del disco es lo del remoto."""
    por_repo, motivos = _por_repo(rutas, rutas_protocolo)
    for nombre, repo in (("AP", Path(rutas.ap)), ("APH", Path(rutas.aph))):
        if not por_repo[nombre]:
            continue
        r = _git(repo, "diff", "--quiet", "origin/main", "--", *por_repo[nombre])
        if r.returncode == 1:
            motivos.append(f"{nombre}: las rutas del protocolo difieren de origin/main (el testigo externo, §10)")
        elif r.returncode != 0:
            motivos.append(f"{nombre}: no se pudo comparar con origin/main")
    return motivos


# ---------------------------------------------------------------------------
# Cerrojo (VER-9 a VER-11)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Corrida:
    """Una corrida del cerrojo: su «inicio» y, si lo hay, su «fin» (VER-9)."""
    intento: int
    etiqueta: str
    huella: str
    errata: int | None
    resultado: str | None
    cruzo: bool

    @property
    def terminal(self) -> bool:
        return self.cruzo and self.resultado in TERMINALES


class Cerrojo:
    """``intentos_aplicar.jsonl`` (M3-4) o ``intentos_m6.jsonl`` (M6): sólo agregado, cada línea encadenada a todo lo
    anterior por su sha256 (VER-9), en ``LOCAL/meteo_combinada/v1/cerrojo/`` y cotejado con las carpetas de las
    corridas en cada lectura (VER-10)."""

    def __init__(self, rutas, compuerta: str):
        if compuerta not in CERROJOS:
            raise ValueError(f"el cerrojo es de M3-4 o de M6: {compuerta!r}")
        self.rutas, self.compuerta, self.nombre = rutas, compuerta, CERROJOS[compuerta]
        self.carpeta = Path(rutas.salidas) / SUBCARPETA_CERROJO
        self.ruta = self.carpeta / self.nombre
        self.lineas: list[dict] = []
        self._datos = b""
        self.releer()

    # --- lectura, cadena y cotejo ---
    def _leer(self) -> bytes:
        if not os.path.lexists(self.ruta):
            return b""
        if os.path.islink(self.ruta) or not self.ruta.is_file():
            raise ErrorCerrojo(f"{self.nombre} no es un archivo regular")
        with open(self.ruta, "rb") as f:
            return f.read()

    @staticmethod
    def verificar(datos: bytes) -> list[dict]:
        """Las líneas, si la cadena calza (VER-9); ``ErrorCerrojo`` si no."""
        if datos and not datos.endswith(b"\n"):
            raise ErrorCerrojo("el cerrojo termina en una línea incompleta")
        h = hashlib.sha256()
        lineas = []
        for crudo in datos.splitlines(keepends=True):
            try:
                obj = json.loads(crudo)
            except ValueError:
                raise ErrorCerrojo("el cerrojo tiene una línea ilegible") from None
            if not isinstance(obj, dict) or obj.get("esquema") != ESQUEMA_CERROJO \
                    or obj.get("previa_sha256") != h.hexdigest():
                raise ErrorCerrojo("el cerrojo fue reescrito: la cadena de huellas no calza (VER-9)")
            lineas.append(obj)
            h.update(crudo)
        return lineas

    def _carpetas_de_corridas(self) -> list[Path]:
        base = Path(self.rutas.salidas)
        if not base.is_dir():
            return []
        salida = []
        for d in sorted(base.iterdir(), key=lambda p: p.name):
            if d.is_dir() and not d.is_symlink() and entorno.es_etiqueta_corrida(d.name):
                c = d / salidas.CARPETA_M6 if self.compuerta == "m6" else d
                if c.is_dir():
                    salida.append(c)
        return salida

    def _cotejar(self, datos: bytes, lineas: Sequence[Mapping]) -> None:
        """VER-10: las carpetas de las corridas en disco están todas en el cerrojo, y sus copias son prefijos."""
        inicios = {ln.get("etiqueta") for ln in lineas if ln.get("evento") == "inicio"}
        terminales = {ln.get("etiqueta") for ln in lineas if ln.get("evento") == "fin"
                      and ln.get("cruzo_frontera") and ln.get("resultado") in TERMINALES}
        for c in self._carpetas_de_corridas():
            etiqueta = (c.parent if self.compuerta == "m6" else c).name
            copia = c / self.nombre
            presentes = [os.path.lexists(c / n) for n in (orquestacion.AVANCE, salidas.RECIBO, self.nombre)]
            if any(presentes) and not lineas:
                raise ErrorCerrojo(f"falta el cerrojo y hay corridas en disco ({etiqueta}): nada corre (VER-10)")
            if presentes[2]:
                with open(copia, "rb") as f:
                    if not datos.startswith(f.read()):
                        raise ErrorCerrojo(f"{etiqueta}: su copia de {self.nombre} no es un prefijo del cerrojo "
                                           "(se borraron o cambiaron líneas; VER-10)")
            if presentes[0] and etiqueta not in inicios:
                raise ErrorCerrojo(f"{etiqueta}: la corrida cruzó la frontera y el cerrojo no tiene su «inicio» "
                                   "(VER-10)")
            if presentes[1] and etiqueta not in terminales:
                raise ErrorCerrojo(f"{etiqueta}: la corrida está sellada y el cerrojo no tiene su «fin» (VER-10)")

    def releer(self, *, cotejar: bool = True) -> None:
        datos = self._leer()
        if not datos.startswith(self._datos):
            raise ErrorCerrojo("el cerrojo cambió desde que se leyó: se borraron o cambiaron líneas")
        lineas = self.verificar(datos)
        if cotejar:
            self._cotejar(datos, lineas)
        self.lineas, self._datos = lineas, datos

    @contextlib.contextmanager
    def _flock(self, ruta: Path, *, esperar: bool):
        fd = os.open(ruta, os.O_RDONLY)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | (0 if esperar else fcntl.LOCK_NB))
            except BlockingIOError:
                raise ErrorCerrojo("otra corrida retiene el cerrojo (VER-11)") from None
            yield
        finally:
            os.close(fd)

    def registrar(self, registro: Mapping) -> dict:
        """Agrega una línea encadenada (VER-9) y la devuelve; el número de «intento» se asigna aquí. Coteja las
        carpetas después de agregarla (así entra el «fin» de una corrida recién sellada)."""
        existe = os.path.lexists(self.ruta)
        with (self._flock(self.ruta, esperar=True) if existe else contextlib.nullcontext()):
            self.releer(cotejar=False)
            obj = {k: v for k, v in dict(registro).items() if k not in ("esquema", "previa_sha256")}
            if obj.get("evento") == "intento" and obj.get("intento") is None:
                obj["intento"] = sum(1 for ln in self.lineas if ln.get("evento") == "intento") + 1
            obj.update(esquema=ESQUEMA_CERROJO, previa_sha256=hashlib.sha256(self._datos).hexdigest())
            salidas.agregar_linea(self.nombre, obj, raiz=self.carpeta)
            self.releer(cotejar=False)
        if self.lineas[-1].get("previa_sha256") != obj["previa_sha256"]:
            raise ErrorCerrojo("otra línea se agregó a la vez: revisar el cerrojo (VER-11)")
        self.releer()
        return self.lineas[-1]

    @contextlib.contextmanager
    def retener(self):
        """El candado de toda la corrida: ``flock`` sobre la carpeta del cerrojo, sin esperar (VER-11)."""
        with self._flock(self.carpeta, esperar=False):
            yield self

    def copiar_a(self, carpeta_corrida) -> str:
        """VER-10: el cerrojo entero en la carpeta de la corrida, antes del sello (sólo agregado)."""
        self.releer(cotejar=False)
        return salidas.escribir(self.nombre, self._datos, clase="procedencia", raiz=carpeta_corrida)

    # --- estado ---
    def _carpeta_de(self, etiqueta: str) -> Path:
        base = entorno.carpeta_salida(self.rutas, "m34", etiqueta)
        return base / salidas.CARPETA_M6 if self.compuerta == "m6" else base

    def corridas(self) -> list[Corrida]:
        """Las corridas que pasaron las negativas, en orden (VER-9)."""
        fines = {ln["intento"]: ln for ln in self.lineas if ln.get("evento") == "fin"}
        salida = []
        for ln in self.lineas:
            if ln.get("evento") != "inicio":
                continue
            fin = fines.get(ln["intento"])
            if fin is not None:
                cruzo, resultado = bool(fin.get("cruzo_frontera")), fin.get("resultado")
            else:
                cruzo = os.path.lexists(self._carpeta_de(ln["etiqueta"]) / orquestacion.AVANCE)
                resultado = None
            salida.append(Corrida(int(ln["intento"]), str(ln["etiqueta"]), str(ln["huella_corrida"]),
                                  ln.get("errata"), resultado, cruzo))
        return salida

    def confirmatorias(self) -> list[Corrida]:
        return [c for c in self.corridas() if c.cruzo]

    def pendiente(self) -> Corrida | None:
        """La última confirmatoria no terminal (para reanudarla), o None."""
        conf = self.confirmatorias()
        return conf[-1] if conf and not conf[-1].terminal else None

    def sellada(self, etiqueta: str | None = None) -> Corrida | None:
        """La última confirmatoria sellada (de ``etiqueta``, si se da), o None."""
        sell = [c for c in self.confirmatorias() if c.resultado == TERMINALES[0]
                and (etiqueta is None or c.etiqueta == etiqueta)]
        return sell[-1] if sell else None

    def fallas(self, etiqueta: str | None, huella: str, errata: int | None) -> list[Falla]:
        """§10: «ya registra una corrida confirmatoria y no hay una errata confirmada» (VER-9)."""
        m = entorno.PATRON_ETIQUETA_CORRIDA.fullmatch(etiqueta or "")
        errata_etiqueta = int(m.group("errata")) if m and m.group("errata") else None
        conf = self.confirmatorias()
        ultima = conf[-1] if conf else None
        if ultima is not None and not ultima.terminal and (ultima.etiqueta, ultima.huella) == (etiqueta, huella):
            return []                                                   # reanudar la misma corrida
        if errata is None:
            if ultima is not None:
                return [Falla("cerrojo", f"{self.nombre} ya registra una corrida confirmatoria ({ultima.etiqueta}) y "
                                         "no hay una errata confirmada (§10); una pendiente se reanuda con su misma "
                                         "etiqueta y huellas")]
            if errata_etiqueta is not None:
                return [Falla("errata", "una etiqueta con _ERRATA exige su errata confirmada (§10)")]
            return []
        if ultima is None:
            return [Falla("errata", "no hay una corrida confirmatoria que la errata corrija (P-VER-3)")]
        if errata in {c.errata for c in conf if c.errata is not None}:
            return [Falla("errata", f"la errata {errata} ya habilitó una corrida (§10)")]
        if errata_etiqueta != errata:
            return [Falla("errata", "la corrida de una errata lleva _ERRATA<n> con su número (§10)")]
        return []


# ---------------------------------------------------------------------------
# Addendum, entradas y errata (VER-13)
# ---------------------------------------------------------------------------
def _alias_de_argumento(ruta, rutas) -> str:
    """La ruta por alias de un archivo pasado por argumento: una ruta («…/APH/auditoria/…») o ya un alias
    («APH/auditoria/…»); debe estar en AP o APH (el testigo externo, §10)."""
    texto = str(ruta)
    if texto.startswith(("AP/", "APH/")) and not os.path.exists(texto):
        return texto if ".." not in PurePosixPath(texto).parts else _alias_de_argumento(Path(texto).absolute(), rutas)
    try:
        a = entorno.alias(Path(ruta).absolute(), rutas)
    except ValueError as e:
        raise ErrorConfiguracion(f"{Path(ruta).name}: no está bajo ningún alias (§8)") from e
    if not a.startswith(("AP/", "APH/")):
        raise ErrorConfiguracion(f"{a}: debe estar en AP o APH (testigo externo, §10)")
    return a


def _json(datos: bytes, que: str) -> Any:
    def sin_duplicados(pares):
        claves = [k for k, _ in pares]
        if len(claves) != len(set(claves)):
            raise ErrorConfiguracion(f"{que}: claves repetidas")
        return dict(pares)
    try:
        return json.loads(datos.decode("utf-8"), object_pairs_hook=sin_duplicados)
    except (UnicodeDecodeError, ValueError) as e:
        if isinstance(e, ErrorConfiguracion):
            raise
        raise ErrorConfiguracion(f"{que}: JSON inválido ({type(e).__name__})") from e


def _leer_por_alias(alias_: str, rutas) -> bytes:
    with open(orquestacion.ruta_de_alias(rutas, alias_), "rb") as f:
        return f.read()


def leer_addendum(alias_: str, rutas) -> tuple[dict, str]:
    """(contenido, sha256) de ``addendum_m1.json`` (MC-54), con su esquema y su lista cerrada."""
    datos = _leer_por_alias(alias_, rutas)
    contenido = _json(datos, "addendum de M1")
    if not isinstance(contenido, dict) or contenido.get("esquema") != addendum.ESQUEMA:
        raise ErrorConfiguracion(f"el addendum no es un «{addendum.ESQUEMA}»")
    try:
        addendum._validar_declaraciones(contenido)
    except addendum.ErrorAddendum as e:
        raise ErrorConfiguracion(str(e)) from e
    lista = contenido.get("lista_cerrada")
    if not isinstance(lista, dict) or not lista or not all(
            isinstance(a, str) and ceguera.es_ruta_por_alias(a) and isinstance(s, str) and _SHA.fullmatch(s)
            for a, s in lista.items()):
        raise ErrorConfiguracion("el addendum no trae su lista cerrada {ruta por alias: sha256}")
    return contenido, entorno.sha256_bytes(datos)


def leer_entradas(alias_: str, rutas, compuerta: str) -> tuple[dict, str]:
    """(contenido, sha256) del archivo de entradas de una compuerta (VER-13)."""
    datos = _leer_por_alias(alias_, rutas)
    c = _json(datos, "entradas")
    if not isinstance(c, dict) or set(c) != {"esquema", "compuerta", "entradas", "huellas"} \
            or c["esquema"] != ESQUEMA_ENTRADAS:
        raise ErrorConfiguracion(f"las entradas son {{esquema: «{ESQUEMA_ENTRADAS}», compuerta, entradas, huellas}}")
    if c["compuerta"] != compuerta:
        raise ErrorConfiguracion(f"las entradas son de {c['compuerta']!r}, no de {compuerta!r}")
    if not isinstance(c["entradas"], dict) or set(c["entradas"]) & set(CLAVES_RESERVADAS):
        raise ErrorConfiguracion(f"«entradas» es un objeto sin {list(CLAVES_RESERVADAS)} (las pone verificar)")
    if not isinstance(c["huellas"], dict) or not all(
            isinstance(a, str) and ceguera.es_ruta_por_alias(a) and isinstance(s, str) and _SHA.fullmatch(s)
            for a, s in c["huellas"].items()):
        raise ErrorConfiguracion("«huellas» es {ruta por alias: sha256}")
    return c, entorno.sha256_bytes(datos)


def leer_errata(alias_: str, rutas, compuerta: str) -> tuple[int, str, dict]:
    """(n, sha256, contenido) de una errata confirmada (§10; como VER-7 del reloj): ``{esquema, n, compuerta, fecha,
    prueba, sello}``, con la prueba que falla contra el texto anclado y el sello, cada uno {ruta, sha256} presente."""
    datos = _leer_por_alias(alias_, rutas)
    c = _json(datos, "errata")
    if not isinstance(c, dict) or set(c) != {"esquema", "n", "compuerta", "fecha", "prueba", "sello"} \
            or c["esquema"] != ESQUEMA_ERRATA:
        raise ErrorConfiguracion(f"la errata es {{esquema: «{ESQUEMA_ERRATA}», n, compuerta, fecha, prueba, sello}}")
    n = c["n"]
    if isinstance(n, bool) or not isinstance(n, int) or n < 1 or c["compuerta"] != compuerta \
            or not (isinstance(c["fecha"], str) and _FECHA.fullmatch(c["fecha"])):
        raise ErrorConfiguracion("la errata trae «n» ≥ 1, su compuerta y su fecha AAAA-MM-DD")
    for clave in ("prueba", "sello"):
        x = c[clave]
        if not isinstance(x, dict) or set(x) != {"ruta", "sha256"} or not isinstance(x["sha256"], str) \
                or not str(x.get("ruta", "")).startswith(("AP/", "APH/")):
            raise ErrorConfiguracion(f"errata.{clave} es {{ruta (AP o APH), sha256}}")
        try:
            sha = entorno.sha256_bytes(_leer_por_alias(x["ruta"], rutas))
        except (OSError, orquestacion.ErrorOrquestacion) as e:
            raise ErrorConfiguracion(f"errata.{clave}: no se puede leer") from e
        if sha != x["sha256"]:
            raise ErrorConfiguracion(f"errata.{clave}: su sha256 no es la citada")
    return n, entorno.sha256_bytes(datos), c


def _addendum_de(cfg) -> tuple[dict | None, list[Falla]]:
    alias_ = cfg.entradas.get("addendum")
    if not isinstance(alias_, str):
        return None, [Falla("addendum", "falta el addendum de M1 (MC-54)")]
    try:
        contenido, sha = leer_addendum(alias_, cfg.rutas)
    except (OSError, ErrorConfiguracion, orquestacion.ErrorOrquestacion) as e:
        return None, [Falla("addendum", f"{alias_}: {e}")]
    if cfg.huellas.get(alias_) != sha:
        return None, [Falla("lista_cerrada", f"{alias_}: el addendum cambió desde que se armó la corrida")]
    return contenido, []


# ---------------------------------------------------------------------------
# Negativas (VER-7, VER-8, VER-16, VER-20)
# ---------------------------------------------------------------------------
def _recortes(U) -> tuple[str, str]:
    """«mod11» y «mod23» desde los umbrales (§4.9; COS-12)."""
    return f"mod{U.a('SEL_MOD')}", f"mod{U.a('SEL_MOD_RECORTE')}"


def _procesos_por_fase(x) -> dict[str, dict[str, int]] | None:
    """VER-22 (D59; A39): {compuerta: {fase: n}} con exactamente las compuertas y las fases de
    ``orquestacion.FASES_REPARTO`` y cada n un entero (no bool) de 1 a ``constantes.valor("PROCESOS")``, en el orden de
    ``FASES_REPARTO``; None si no tiene esa forma."""
    tope = int(constantes.valor("PROCESOS"))
    if not isinstance(x, Mapping) or set(x) != set(orquestacion.FASES_REPARTO):
        return None
    salida = {}
    for compuerta, fases in orquestacion.FASES_REPARTO.items():
        por_fase = x[compuerta]
        if not isinstance(por_fase, Mapping) or set(por_fase) != set(fases) or not all(
                isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= tope for n in por_fase.values()):
            return None
        salida[compuerta] = {f: int(por_fase[f]) for f in fases}
    return salida


def _procesos_que_no_corren() -> dict[str, dict[str, int]]:
    """VER-13: los procesos por fase de una corrida que se arma sin los del addendum: 1 en cada fase de
    ``FASES_REPARTO`` (las negativas la niegan)."""
    return {c: {f: 1 for f in fases} for c, fases in orquestacion.FASES_REPARTO.items()}


def _fallas_contenido(cfg, contenido: Mapping) -> list[Falla]:
    """VER-7: el contenido del addendum, no sólo su forma (revisión de la ola 6)."""
    fallas = []
    if set(contenido) != set(addendum.CLAVES):        # el JSON canónico las ordena (salidas): sólo el conjunto
        fallas.append(Falla("addendum", "el addendum no tiene las claves exactas de addendum_m1 (ADD-10)"))
    try:
        addendum._validar_declaraciones(contenido)
    except addendum.ErrorAddendum as e:
        fallas.append(Falla("addendum", str(e)))
    lista = contenido.get("lista_cerrada", {})
    vigente = f"APH/{umbrales.TEXTO_VIGENTE}"
    if contenido.get("texto_vigente") != {"ruta": vigente, "sha256": umbrales.SHA_TEXTO_VIGENTE} \
            or lista.get(vigente) != umbrales.SHA_TEXTO_VIGENTE:
        fallas.append(Falla("addendum", "el addendum no cita el texto vigente v2.4 con su huella"))
    bateria = contenido.get("bateria")
    carpeta = None
    if not isinstance(bateria, Mapping) or bateria.get("aprobada") is not True:
        fallas.append(Falla("addendum", "la batería de M1 no aprobó (o el addendum no lo dice): no habilita corridas"))
    else:
        try:
            carpeta = addendum.carpeta_bateria(bateria.get("carpeta"))
        except addendum.ErrorAddendum as e:
            fallas.append(Falla("addendum", str(e)))
    if contenido.get("recorte") not in _recortes(cfg.U):
        fallas.append(Falla("addendum", "el recorte no está fijado en el addendum («mod11» o «mod23»; §8): una "
                                        "medición pendiente impide sellar"))
    costo = contenido.get("costo")
    if not isinstance(costo, Mapping) or _procesos_por_fase(costo.get("procesos_por_fase")) is None:
        fallas.append(Falla("addendum", "los procesos por fase de D59 no están fijados en el costo del addendum (las "
                                        "fases de orquestacion.FASES_REPARTO, cada una de 1 a PROCESOS; A39)"))
    elif costo.get("veredicto") != contenido.get("recorte"):
        fallas.append(Falla("addendum", "el recorte del addendum no es el veredicto de su costo (§8)"))
    deriva = contenido.get("deriva")
    if not isinstance(deriva, Mapping) or "veredicto" not in deriva:
        fallas.append(Falla("addendum", "la compuerta de deriva sigue pendiente en el addendum (§5.7)"))
    else:
        try:
            addendum.deriva_de_veredicto(deriva["veredicto"])
        except addendum.ErrorAddendum as e:
            fallas.append(Falla("addendum", str(e)))
    try:
        faltan = sorted(set(addendum.claves_lista_cerrada(cfg.rutas, carpeta_bateria_=carpeta)) - set(lista))
    except addendum.ErrorAddendum as e:
        faltan, _ = [], fallas.append(Falla("lista_cerrada", str(e)))
    for a in faltan[:_CITADOS]:
        fallas.append(Falla("lista_cerrada", f"{a}: falta en la lista cerrada del addendum (ADD-1)"))
    if len(faltan) > _CITADOS:
        fallas.append(Falla("lista_cerrada", "faltan más claves en la lista cerrada del addendum (ADD-1)"))
    for a, sha in addendum.huellas_fijadas().items():
        if a in lista and lista[a] != sha:
            fallas.append(Falla("lista_cerrada", f"{a}: su huella en el addendum no es la fijada (§9.3 del diseño)"))
    return fallas


def _fallas_lista(cfg, contenido: Mapping) -> list[Falla]:
    """La lista cerrada del addendum: cada huella del disco, la misma en ``Cfg.huellas``, todo ``.py`` cubierto y el
    espejo del paquete en APH, si existe, con los mismos bytes (VER-6)."""
    fallas = []
    lista = contenido["lista_cerrada"]
    for a, sha in sorted(lista.items()):
        if cfg.huellas.get(a) != sha:
            fallas.append(Falla("lista_cerrada", f"{a}: la configuración no trae la huella del addendum"))
            continue
        try:
            actual = entorno.sha256_bytes(_leer_por_alias(a, cfg.rutas))
        except (OSError, orquestacion.ErrorOrquestacion):
            fallas.append(Falla("lista_cerrada", f"{a}: no existe"))
            continue
        if actual != sha:
            fallas.append(Falla("lista_cerrada", f"{a}: su sha256 difiere de la lista cerrada del addendum de M1 (§10)"))
    try:
        codigo = addendum.codigo_del_paquete(cfg.rutas.ap)
    except addendum.ErrorAddendum:
        codigo = {}
    for a in sorted(set(codigo) - set(lista)):
        fallas.append(Falla("lista_cerrada", f"{a}: código del paquete sin huella en la lista cerrada (VER-7)"))
    for a, espejo in sorted(_espejos(cfg, lista).items()):
        try:
            if _leer_por_alias(a, cfg.rutas) != _leer_por_alias(espejo, cfg.rutas):
                fallas.append(Falla("espejo", f"{espejo}: el espejo en APH no tiene los bytes de {a} (VER-6)"))
        except (OSError, orquestacion.ErrorOrquestacion):
            fallas.append(Falla("espejo", f"{a} o su espejo no se pueden leer"))
    return fallas


def _espejos(cfg, lista: Mapping) -> dict[str, str]:
    """{alias en AP: alias del espejo en APH} del código del paquete, si el espejo existe (misma ruta relativa)."""
    salida = {}
    for a in lista:
        if a.startswith(f"AP/{addendum.CARPETA_PAQUETE}/"):
            espejo = "APH/" + a[len("AP/"):]
            if (Path(cfg.rutas.aph) / a[len("AP/"):]).is_file():
                salida[a] = espejo
    return salida


def _fallas_commits(cfg, contenido: Mapping) -> list[Falla]:
    fallas = []
    commits = contenido.get("commits") if isinstance(contenido.get("commits"), Mapping) else {}
    for clave, nombre, repo in (("ap", "AP", cfg.rutas.ap), ("aph", "APH", cfg.rutas.aph)):
        c = commits.get(clave)
        if not isinstance(c, str) or not _COMMIT.fullmatch(c):
            fallas.append(Falla("commit_m1", f"el commit de M1 de {nombre} sigue pendiente en el addendum (MC-54)"))
            continue
        if _es_antecesor(Path(repo), c) is not True:
            fallas.append(Falla("commit_m1", f"el commit de M1 ({_corto(c)}) no es antecesor de origin/main de "
                                             f"{nombre} (§10: el testigo externo es condición dura)"))
    return fallas


def _archivos_de_errata(cfg) -> list[str]:
    alias_ = cfg.entradas.get("errata")
    if not isinstance(alias_, str):
        return []
    try:
        c = _json(_leer_por_alias(alias_, cfg.rutas), "errata")
        return [alias_] + [c[k]["ruta"] for k in ("prueba", "sello") if isinstance(c.get(k), Mapping)]
    except (OSError, ErrorConfiguracion, orquestacion.ErrorOrquestacion, KeyError, TypeError):
        return [alias_]


def _rutas_protocolo(cfg, contenido: Mapping, extras: Iterable[str] = ()) -> list[str]:
    """VER-6."""
    salida = {a for a in contenido["lista_cerrada"] if a.startswith(("AP/", "APH/"))}
    salida.update((f"AP/{addendum.CARPETA_PAQUETE}", f"APH/{addendum.CARPETA_PRODUCTO}"))
    salida.update(_espejos(cfg, contenido["lista_cerrada"]).values())
    for clave in ("addendum", "config_entradas", "registro_c5", "registro_red_v2"):
        v = cfg.entradas.get(clave)
        if isinstance(v, str) and v.startswith(("AP/", "APH/")):
            salida.update((v, str(PurePosixPath(v).parent)))
    for v in _archivos_de_errata(cfg):
        if v.startswith(("AP/", "APH/")):
            salida.update((v, str(PurePosixPath(v).parent)))
    salida.update(a for a in extras if a.startswith(("AP/", "APH/")))
    return sorted(salida)


def _fallas_git(cfg, contenido: Mapping, *, extras: Iterable[str] = ()) -> list[Falla]:
    protocolo = _rutas_protocolo(cfg, contenido, extras)
    fallas = [Falla("arbol_sucio", m) for m in arbol_limpio(cfg.rutas, protocolo)]
    fallas += [Falla("testigo", m) for m in igual_al_remoto(cfg.rutas, protocolo)]
    fallas += _fallas_commits(cfg, contenido)
    for clave in ("addendum", "config_entradas"):
        v = cfg.entradas.get(clave)
        if isinstance(v, str):
            fallas += [Falla("testigo", m) for m in registro_en_git(v, cfg.rutas)]
    for v in _archivos_de_errata(cfg):
        fallas += [Falla("testigo", m) for m in registro_en_git(v, cfg.rutas)]
    return fallas


def _fallas_c5(cfg) -> list[Falla]:
    """§2.1, precondición 1 (S2): la política de RELOJ válida y con su sha256 (VER-7)."""
    from meteo_combinada import politicas
    alias_ = cfg.entradas.get("registro_c5")
    if not isinstance(alias_, str):
        return [Falla("c5_sin_registro", "falta el registro de C5 de RELOJ en las entradas (§2.1, precondición 1)")]
    try:
        ruta = orquestacion.ruta_de_alias(cfg.rutas, alias_)
    except orquestacion.ErrorOrquestacion as e:
        return [Falla("c5_sin_registro", str(e))]
    if not ruta.is_file():
        return [Falla("c5_sin_registro", "no hay registro de C5 de RELOJ: M3-4 no corre (§2.1, precondición 1)")]
    try:
        registro = politicas.leer_registro_c5(ruta, ap=cfg.rutas.ap)
        politica, _ = politicas.leer_politica_reloj(registro, ap=cfg.rutas.ap)
    except politicas.ErrorC5 as e:
        return [Falla("c5_sha256" if "sha256" in str(e) else "c5_registro", str(e))]
    fallas = []
    for f in politicas.comprobar_c5(registro, politica):
        motivo = "c5_post_hoc" if "post_hoc = true" in f else "c5_errata" if "errata" in f else "c5_politica"
        fallas.append(Falla(motivo, f))
    if not fallas:
        try:
            politicas.declaracion_c5(registro, politica)
        except politicas.ErrorC5 as e:
            fallas.append(Falla("c5_politica", str(e)))
    errata = registro.errata_confirmada
    if errata is not None:
        fallas += [Falla("c5_errata", m) for m in archivo_en_commit(errata.ruta, cfg.rutas, errata.commit,
                                                                    errata.sha256)]
    # el registro, la política y artefactos_evaluados confirmados en git, y commit_c5 cotejado (revisión de la ola 6)
    fallas += [Falla("c5_git", m) for a in (alias_, politicas.RUTA_POLITICA_AP, politicas.RUTA_ARTEFACTOS_AP)
               for m in registro_en_git(a, cfg.rutas)]
    ap = Path(cfg.rutas.ap)
    if _es_antecesor(ap, registro.commit_c5) is not True:
        fallas.append(Falla("c5_git", f"commit_c5 ({_corto(registro.commit_c5)}) no es antecesor de origin/main de AP"))
    elif errata is None:
        for a, sha in ((politicas.RUTA_POLITICA_AP, registro.sha256_politica),
                       (politicas.RUTA_ARTEFACTOS_AP, registro.sha256_artefactos)):
            if _sha_en_commit(ap, registro.commit_c5, a[len("AP/"):]) != sha:
                fallas.append(Falla("c5_git", f"{a}: no tiene en commit_c5 la sha256 del registro de C5"))
    return fallas


def _huellas_registro_red(datos: bytes) -> dict | None:
    """VER-15: la clave «huellas» {ruta por alias: sha256} del anexo «Registro de la red v2», o None."""
    try:
        c = _json(datos, "registro de la red v2")
    except ErrorConfiguracion:
        return None
    huellas = c.get("huellas") if isinstance(c, dict) else None
    if not isinstance(huellas, dict) or not all(isinstance(a, str) and isinstance(s, str) for a, s in huellas.items()):
        return None
    return huellas


def _fallas_registro_red(cfg, *, paneles: bool) -> list[Falla]:
    """MC-09: el anexo «Registro de la red v2» (R22, paso 4) confirmado en git y con las huellas de la red 2 (VER-15)."""
    alias_ = cfg.entradas.get("registro_red_v2")
    if not isinstance(alias_, str):
        return [Falla("registro_red_v2", "falta el anexo «Registro de la red v2» (R22; MC-09)")]
    fallas = [Falla("registro_red_v2", m) for m in registro_en_git(alias_, cfg.rutas)]
    try:
        datos = _leer_por_alias(alias_, cfg.rutas)
    except (OSError, orquestacion.ErrorOrquestacion):
        return fallas + [Falla("registro_red_v2", f"{alias_}: no se puede leer")]
    if cfg.huellas.get(alias_) != entorno.sha256_bytes(datos):
        fallas.append(Falla("registro_red_v2", f"{alias_}: su sha256 no es la de las entradas"))
    registradas = _huellas_registro_red(datos)
    if registradas is None:
        return fallas + [Falla("registro_red_v2", f"{alias_}: no es un JSON con «huellas» {{ruta por alias: "
                                                  "sha256}} (VER-15)")]
    red2 = cfg.entradas.get("red2") if isinstance(cfg.entradas.get("red2"), Mapping) else {}
    citados = [("pliegues_v2_red2.json", red2.get("pliegues"))]
    if paneles:
        citados += [(f"panel_{p}_red2.parquet", a) for p, a in sorted((red2.get("paneles") or {}).items())]
        if not red2.get("paneles"):
            fallas.append(Falla("registro_red_v2", "las entradas no traen los paneles de la red 2 (MC-09)"))
    for nombre, a in citados:
        sha = cfg.huellas.get(a) if isinstance(a, str) else None
        if sha is None:
            fallas.append(Falla("registro_red_v2", f"las entradas no traen {nombre} con su huella (MC-09)"))
        elif registradas.get(a) != sha:
            fallas.append(Falla("registro_red_v2", f"el registro de la red v2 no registra {nombre} con la huella de las "
                                                   "entradas (MC-09)"))
    return fallas


def _fallas_datos(cfg) -> list[Falla]:
    """Las huellas de datos de las entradas, iguales a las fijadas en M0 (§9.3; FIJ-4)."""
    return [Falla("datos_fijados", f"{a}: su sha256 no es la fijada (§9.3)") for a, s in sorted(cfg.huellas.items())
            if a in fijados.HUELLAS_DATOS and fijados.HUELLAS_DATOS[a] != s]


def _fallas_interprete(cfg) -> list[Falla]:
    """VER-16: el intérprete fijado y la huella de ``micromamba list`` (FIJ-3)."""
    fallas = []
    try:
        entorno.comprobar_interprete()
    except RuntimeError as e:
        fallas.append(Falla("interprete", str(e)))
    ident = cfg.entradas.get("interprete")
    sha = ident.get("micromamba_list_sha256") if isinstance(ident, Mapping) else None
    if sha != fijados.SHA_MICROMAMBA_LIST:
        fallas.append(Falla("interprete", "la huella de micromamba list no es la fijada (FIJ-3; §8)"))
    return fallas


def _numero_errata(cfg, compuerta: str) -> tuple[int | None, list[Falla]]:
    alias_ = cfg.entradas.get("errata")
    if alias_ is None:
        return None, []
    try:
        n, sha, _ = leer_errata(alias_, cfg.rutas, compuerta)
    except (OSError, ErrorConfiguracion, orquestacion.ErrorOrquestacion) as e:
        return None, [Falla("errata", f"{alias_}: {e}")]
    if cfg.huellas.get(alias_) != sha:
        return None, [Falla("errata", f"{alias_}: cambió desde que se armó la corrida")]
    return n, []


def _fallas_cerrojo(cfg, compuerta: str) -> list[Falla]:
    n, fallas = _numero_errata(cfg, compuerta)
    if fallas:
        return fallas
    try:
        c = Cerrojo(cfg.rutas, compuerta)
    except ErrorCerrojo as e:
        return [Falla("cerrojo", str(e))]
    return c.fallas(cfg.etiqueta, orquestacion.huella_de_corrida(cfg, compuerta), n)


def _comunes(cfg) -> tuple[dict | None, list[Falla]]:
    contenido, fallas = _addendum_de(cfg)
    if contenido is None:
        return None, fallas
    return contenido, (_fallas_contenido(cfg, contenido) + _fallas_lista(cfg, contenido) + _fallas_interprete(cfg)
                       + _fallas_datos(cfg))


def _fallas_m34(cfg) -> list[Falla]:
    contenido, fallas = _comunes(cfg)
    if contenido is None:
        return fallas
    fallas += _fallas_git(cfg, contenido)
    fallas += _fallas_c5(cfg)
    fallas += _fallas_cerrojo(cfg, "m34")
    fallas += _fallas_registro_red(cfg, paneles=False)
    return fallas


def negativas_m34(cfg) -> list[str]:
    """§10, «M3-4 se niega a correr» (VER-7); vacía: corre. Lee el addendum, las entradas, la errata y el intérprete de
    ``Cfg.entradas`` (VER-13)."""
    return [str(f) for f in _fallas_m34(cfg)]


def _es_solo_agregado(nombre: str) -> bool:
    final = PurePosixPath(nombre).name.casefold()
    return any(fnmatch.fnmatchcase(final, p) for p in _SOLO_AGREGADO)


def _huella_prefijo(ruta: Path, n: int) -> str | None:
    with open(ruta, "rb") as f:
        datos = f.read(n)
    return entorno.sha256_bytes(datos) if len(datos) == n else None


def _fallas_publicacion(cfg) -> list[Falla]:
    """Anexo B: las huellas de ``decision.json`` y de los productos de M5 frente a las publicadas (VER-8)."""
    try:
        corrida = orquestacion.carpeta_de(cfg, "m5")
        publicada = salidas.carpeta_publicacion(cfg.rutas.ap)
    except (ValueError, PermissionError, orquestacion.ErrorOrquestacion) as e:
        return [Falla("publicacion", f"no se ubica la publicación de M5 ({type(e).__name__})")]
    fallas = []
    for nombre in (salidas.DECISION, salidas.SHA256_JSON, salidas.RECIBO):
        try:
            with open(publicada / nombre, "rb") as f:
                pub = f.read()
            with open(corrida / nombre, "rb") as f:
                local = f.read()
        except OSError:
            fallas.append(Falla("publicacion", f"falta {nombre} en la corrida o en la publicación de M5"))
            continue
        if pub != local:
            fallas.append(Falla("publicacion", f"{nombre}: la huella de la corrida difiere de la publicada (Anexo B)"))
    if fallas:
        return fallas
    with open(publicada / salidas.SHA256_JSON, "rb") as f:
        archivos = _json(f.read(), "sha256.json publicado").get("archivos", {})
    for rel, v in sorted(archivos.items()):
        if rel.casefold().startswith(salidas.CARPETA_M6 + "/"):
            continue
        ruta = corrida.joinpath(*rel.split("/"))
        sha, n = v.get("sha256"), v.get("bytes")
        if not ruta.is_file():
            fallas.append(Falla("publicacion", f"falta {rel} en la corrida de M5"))
        elif (_huella_prefijo(ruta, n) if _es_solo_agregado(rel) and isinstance(n, int)
              else entorno.sha256_archivo(ruta)) != sha:
            fallas.append(Falla("publicacion", f"{rel}: difiere de la huella publicada (Anexo B)"))
    return fallas


def _confirmados_m6(cfg) -> tuple[list[str], list[Falla]]:
    """Los archivos de la Enmienda 2 ambiental, de la DMC, de v2 y de la fábrica, y sus espejos (VER-8)."""
    c = cfg.entradas.get("confirmados_m6")
    if not isinstance(c, Mapping):
        return [], [Falla("confirmados_m6", "las entradas no traen «confirmados_m6» (Anexo B)")]
    fallas, alias_ = [], []
    for clave in CONFIRMADOS_M6:
        v = c.get(clave)
        lista = [v] if isinstance(v, str) else list(v) if isinstance(v, (list, tuple)) else []
        if not lista:
            fallas.append(Falla("confirmados_m6", f"falta «{clave}» en confirmados_m6 (Anexo B)"))
        alias_ += [a for a in lista if isinstance(a, str)]
    espejos = c.get("espejos") if isinstance(c.get("espejos"), Mapping) else {}
    todos = list(alias_)
    for a in alias_:
        fallas += [Falla("confirmados_m6", m) for m in registro_en_git(a, cfg.rutas)]
        if a.startswith("AP/"):
            e = espejos.get(a)
            if not isinstance(e, str) or not e.startswith("APH/"):
                fallas.append(Falla("confirmados_m6", f"{a}: falta su espejo en APH (Anexo B)"))
                continue
            todos.append(e)
            fallas += [Falla("confirmados_m6", m) for m in registro_en_git(e, cfg.rutas)]
            try:
                if _leer_por_alias(a, cfg.rutas) != _leer_por_alias(e, cfg.rutas):
                    fallas.append(Falla("confirmados_m6", f"{e}: no tiene los bytes de {a}"))
            except (OSError, orquestacion.ErrorOrquestacion):
                fallas.append(Falla("confirmados_m6", f"{a} o su espejo no se pueden leer"))
    return todos, fallas


def _fallas_m6(cfg) -> list[Falla]:
    contenido, fallas = _comunes(cfg)
    if contenido is None:
        return fallas
    fallas += _fallas_publicacion(cfg)
    confirmados, f_conf = _confirmados_m6(cfg)
    publicacion = f"AP/{salidas.SUBRUTA_PUBLICACION}"
    fallas += _fallas_git(cfg, contenido, extras=[publicacion, *confirmados]) + f_conf
    fallas += _fallas_registro_red(cfg, paneles=True)
    if cfg.entradas.get("errata"):
        fallas.append(Falla("errata_m6", "una errata de M6 necesita su propia carpeta (<ETIQUETA>/m6_ERRATA<n>, con su "
                                         "numeración), que orquestacion y salidas todavía no admiten: rige la más "
                                         "estricta, M6 no se repite (VER-19, P-VER-5)"))
    fallas += _fallas_cerrojo(cfg, "m6")
    if cfg.fabrica_m6 is None:
        fallas.append(Falla("fabrica", "M6 necesita la fábrica de producción v2 (Cfg.fabrica_m6; diferencia 33)"))
    return fallas


def negativas_m6(cfg) -> list[str]:
    """Anexo B, «M6 se niega a correr» (VER-8); vacía: corre."""
    return [str(f) for f in _fallas_m6(cfg)]


def _fallas_c2(cfg) -> list[Falla]:
    """VER-20: la línea de cierre de C2 de RELOJ (el catálogo fijo, §10), confirmada en git y con su esquema."""
    alias_ = cfg.entradas.get("cierre_c2")
    if not isinstance(alias_, str):
        return [Falla("cierre_c2", "las entradas de M2a no traen la línea de cierre de C2 de RELOJ (§10, M2a)")]
    fallas = [Falla("cierre_c2", m) for m in registro_en_git(alias_, cfg.rutas)]
    try:
        contenido = _json(_leer_por_alias(alias_, cfg.rutas), "cierre de C2")
    except (OSError, ErrorConfiguracion, orquestacion.ErrorOrquestacion):
        return fallas + [Falla("cierre_c2", f"{alias_}: no se puede leer")]
    if not isinstance(contenido, dict) or contenido.get("schema") != ESQUEMA_CIERRE_C2:
        fallas.append(Falla("cierre_c2", f"{alias_}: no es un «{ESQUEMA_CIERRE_C2}»"))
    return fallas


def _fallas_m2a(cfg) -> list[Falla]:
    contenido, fallas = _comunes(cfg)
    if contenido is None:
        return fallas
    return fallas + _fallas_c2(cfg)


def negativas_m2a(cfg) -> list[str]:
    """M2a (VER-20): el contenido y la lista cerrada del addendum de M1, el intérprete, la línea de cierre de C2 de
    RELOJ y las huellas de datos fijadas."""
    return [str(f) for f in _fallas_m2a(cfg)]


def _fallas_m5(cfg) -> list[Falla]:
    contenido, fallas = _comunes(cfg)
    if contenido is None:
        return fallas
    try:
        sellada = Cerrojo(cfg.rutas, "m34").sellada(cfg.etiqueta)
    except ErrorCerrojo as e:
        return fallas + [Falla("cerrojo", str(e))]
    if sellada is None:
        fallas.append(Falla("m34_no_sellada", f"{cfg.etiqueta}: no hay una M3-4 sellada con esta etiqueta (§10)"))
    return fallas


def negativas_m5(cfg) -> list[str]:
    """M5 (VER-20): lo común y su M3-4 sellada en el cerrojo (§10, M5)."""
    return [str(f) for f in _fallas_m5(cfg)]


_FALLAS = {"m2a": _fallas_m2a, "m34": _fallas_m34, "m5": _fallas_m5, "m6": _fallas_m6}


class Negativas:
    """``Cfg.negativas`` de una compuerta: un objeto de este módulo, para que ``orquestacion.identidad_funcion`` lo
    identifique por su clase y su archivo (ORQ-34; VER-13). Corre bajo ``SinRed`` (VER-14)."""

    def __init__(self, compuerta: str):
        if compuerta not in _FALLAS:
            raise ValueError(f"compuerta desconocida: {compuerta!r}")
        self.compuerta = compuerta

    def fallas(self, cfg) -> list[Falla]:
        with ceguera.SinRed():
            return _FALLAS[self.compuerta](cfg)

    def __call__(self, cfg) -> list[str]:
        return [str(f) for f in self.fallas(cfg)]


# ---------------------------------------------------------------------------
# Las corridas reales (VER-12 a VER-14, VER-16)
# ---------------------------------------------------------------------------
@contextlib.contextmanager
def directorio_neutro():
    """VER-18: el directorio de trabajo en la carpeta temporal del sistema mientras dura el aislamiento, y de vuelta
    al salir."""
    previo = os.getcwd()
    os.chdir(tempfile.gettempdir())
    try:
        yield
    finally:
        os.chdir(previo)


def _registro_aislado(rutas, permitidas: Sequence[str], compuerta: str):
    """VER-14: /Volumes y los repositorios en bloqueo (se leen AP, APH y lo permitido); del reloj, sus corridas nunca
    y de su publicación sólo, en M3-4, la política, ``artefactos_evaluados`` y el informe de K2 (§1.9; MC-19)."""
    reales = entorno.rutas_reales()
    repos = tuple(dict.fromkeys(str(p) for p in (reales.ap, reales.aph, rutas.ap, rutas.aph)))
    publicacion = Path(rutas.ap) / RELOJ_PUBLICACION
    del_reloj = () if compuerta != "m34" else tuple(
        str(publicacion / "v1" / n) for n in (ceguera.POLITICA_RELOJ, ceguera.ARTEFACTOS_RELOJ, ceguera.INFORME_RELOJ))
    pila = contextlib.ExitStack()
    pila.enter_context(directorio_neutro())
    pila.enter_context(ceguera.SinRed())
    pila.enter_context(ceguera.RegistroAccesos(("/" + "Volumes", *repos), bloquear=True,
                                               permitidas=(*repos, *permitidas)))
    pila.enter_context(ceguera.RegistroAccesos((str(publicacion), str(Path(reales.local) / RELOJ_CORRIDAS)),
                                               bloquear=True, permitidas=del_reloj))
    return pila


def _zonas_ciegas(reales) -> tuple[str, ...]:
    """Lo que nadie de M1 abre del reloj (VER-1): su publicación en AP y sus corridas en LOCAL."""
    return (str(Path(reales.ap) / RELOJ_PUBLICACION), str(Path(reales.local) / RELOJ_CORRIDAS))


def _permitidas(cfg_entradas: Mapping, rutas, compuerta: str) -> tuple[str, ...]:
    """PED-11: lo de las entradas que cae bajo /Volumes, y en M3-4 la carpeta de la DMC."""
    salida: set[str] = set()

    def recorrer(v):
        if isinstance(v, Mapping):
            for x in v.values():
                recorrer(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                recorrer(x)
        elif isinstance(v, str) and "/" in v and v.split("/", 1)[0] in entorno.ALIAS.values():
            try:
                ruta = orquestacion.ruta_de_alias(rutas, v)
            except orquestacion.ErrorOrquestacion:
                return
            if str(ruta).casefold().startswith("/volumes/"):
                salida.add(str(ruta))
    recorrer(cfg_entradas)
    if compuerta == "m34":
        salida.add(str(rutas.dmc))
    return tuple(sorted(salida))


def _cargar_fabrica(spec, rutas, huellas: Mapping[str, str]):
    """La fábrica de producción v2 de M6 (``Cfg.fabrica_m6``): ``{"modulo": alias, "funcion": nombre}``, con su huella,
    cargada dentro del aislamiento (VER-13)."""
    if spec is None:
        return None
    if not isinstance(spec, Mapping) or set(spec) != {"modulo", "funcion"}:
        raise ErrorConfiguracion("fabrica_m6 es {modulo: alias de un .py, funcion: nombre}")
    alias_ = spec["modulo"]
    datos = _leer_por_alias(alias_, rutas)
    if huellas.get(alias_) != entorno.sha256_bytes(datos):
        raise ErrorConfiguracion(f"{alias_}: la fábrica no tiene la huella de las entradas")
    ruta = orquestacion.ruta_de_alias(rutas, alias_)
    # el nombre del módulo sale de su huella: entra en la huella de la corrida (ORQ-34), que debe repetirse al reanudar
    sha = entorno.sha256_bytes(datos)
    with _registro_aislado(rutas, (), "m6"):
        especificacion = importlib.util.spec_from_file_location(f"fabrica_m6_{sha[:fijados.ABREVIATURA]}", ruta)
        modulo = importlib.util.module_from_spec(especificacion)
        especificacion.loader.exec_module(modulo)
    return getattr(modulo, spec["funcion"])


def _identidad_interprete(servicios: Servicios) -> dict:
    """VER-16: las versiones fijadas y la huella de ``micromamba list`` (None si algo no se puede leer)."""
    try:
        # sin la ruta del ejecutable (empieza con «~/»): la comprobación ya la exige
        versiones = {k: str(v) for k, v in entorno.comprobar_interprete().items() if k != "interprete"}
    except RuntimeError:
        versiones = {}
    try:
        sha = fijados.huella_micromamba(servicios.micromamba())
    except (OSError, subprocess.SubprocessError):
        sha = None
    return {"esquema": ESQUEMA_INTERPRETE, "micromamba_list_sha256": sha, "versiones": dict(sorted(versiones.items()))}


def _armar(args, rutas, modo: str, servicios: Servicios, U) -> tuple[Any, dict, str | None]:
    """(cfg, huellas de los argumentos, etiqueta): VER-12, VER-13 y VER-16. ``ErrorConfiguracion`` si algo no tiene su
    forma."""
    compuerta = COMPUERTA_DE_MODO[modo]
    if not args.addendum or not args.entradas:
        raise ErrorConfiguracion("--addendum y --entradas son obligatorios en las corridas reales (MC-54)")
    alias_add = _alias_de_argumento(args.addendum, rutas)
    alias_ent = _alias_de_argumento(args.entradas, rutas)
    contenido, sha_add = leer_addendum(alias_add, rutas)
    entradas, sha_ent = leer_entradas(alias_ent, rutas, compuerta)
    huellas = {**contenido["lista_cerrada"]}
    for a, s in entradas["huellas"].items():
        if huellas.get(a, s) != s:
            raise ErrorConfiguracion(f"{a}: dos huellas distintas en la lista cerrada y en las entradas")
        huellas[a] = s
    huellas[alias_add], huellas[alias_ent] = sha_add, sha_ent
    e = {**entradas["entradas"], "addendum": alias_add, "config_entradas": alias_ent}
    errata = None
    if getattr(args, "errata", None):
        if compuerta not in CERROJOS:
            raise ErrorConfiguracion("--errata es de --aplicar y --m6 (§10)")
        alias_err = _alias_de_argumento(args.errata, rutas)
        errata, sha_err, _ = leer_errata(alias_err, rutas, compuerta)
        e["errata"], huellas[alias_err] = alias_err, sha_err
    etiqueta = _etiqueta(args, rutas, compuerta, servicios, errata)
    # VER-16: el intérprete, en las entradas y, por interprete.json de la carpeta, en la lista que cita el recibo
    ident = _identidad_interprete(servicios)
    e["interprete"] = {"micromamba_list_sha256": ident["micromamba_list_sha256"], "versiones": ident["versiones"]}
    carpeta = orquestacion.carpeta_de(_CfgEtiqueta(rutas, etiqueta), compuerta)
    huellas[entorno.alias(carpeta / INTERPRETE_JSON, rutas)] = entorno.sha256_bytes(entorno.json_canonico(ident))
    fabrica = servicios.fabrica_m6 if servicios.fabrica_m6 is not None else (
        _cargar_fabrica(e.get("fabrica_m6"), rutas, huellas) if compuerta == "m6" else None)
    # VER-13: con el recorte o la deriva pendientes, valores que no corren; las negativas niegan (VER-7)
    deriva = {c: False for c in addendum.CANDIDATOS_DERIVA}
    if isinstance(contenido.get("deriva"), Mapping) and "veredicto" in contenido["deriva"]:
        try:
            deriva = addendum.deriva_de_veredicto(contenido["deriva"]["veredicto"])
        except (addendum.ErrorAddendum, TypeError, AttributeError):
            pass
    costo = contenido.get("costo") if isinstance(contenido.get("costo"), Mapping) else {}
    procesos_por_fase = _procesos_por_fase(costo.get("procesos_por_fase")) or _procesos_que_no_corren()   # VER-22
    cfg = orquestacion.Cfg(
        rutas=rutas, umbrales=U, entradas=e, huellas=huellas, etiqueta=etiqueta,
        procesos=int(U.opciones_m0["D2"]), modo=modo, pares=orquestacion.PARES,
        recorte=contenido.get("recorte") == _recortes(U)[1], deriva=deriva,
        permitidas=_permitidas(e, rutas, compuerta), negativas=Negativas(compuerta), fabrica_m6=fabrica,
        procesos_por_fase=procesos_por_fase)
    return cfg, {a: huellas[a] for a in (alias_add, alias_ent, e.get("errata")) if a}, etiqueta


@dataclass(frozen=True)
class _CfgEtiqueta:
    """Lo que ``orquestacion.carpeta_de`` mira de un ``Cfg`` (rutas y etiqueta), para ubicar la carpeta antes de
    armarlo."""
    rutas: Any
    etiqueta: str | None


def _etiqueta(args, rutas, compuerta: str, servicios: Servicios, errata: int | None) -> str | None:
    """VER-12: la del día (UTC) con su errata, o la de la confirmatoria pendiente para reanudarla; ``--etiqueta`` sólo
    admite ésas. M5 y M6: la de la última M3-4 sellada."""
    if compuerta == "m2a":
        return None
    pedida = getattr(args, "etiqueta", None)
    if pedida is not None and not entorno.es_etiqueta_corrida(pedida):
        raise ErrorConfiguracion("--etiqueta es HUMAN<AAAAMMDD>_METEO_COMB_<n>[_ERRATA<k>] (§10)")
    if compuerta == "m34":
        pendiente = Cerrojo(rutas, "m34").pendiente()
        del_dia = entorno.etiqueta_corrida(_dia_utc(servicios.ahora()), errata=errata)
        admitidas = {del_dia}
        if pendiente is not None and pendiente.errata == errata:
            admitidas.add(pendiente.etiqueta)
            if pedida is None:
                return pendiente.etiqueta
        if pedida is not None and pedida not in admitidas:
            raise ErrorConfiguracion("--etiqueta sólo admite la del día (HUMAN<AAAAMMDD UTC>_METEO_COMB_1, con su "
                                     "_ERRATA<n>) o la de la corrida pendiente (VER-12)")
        return pedida or del_dia
    sellada = Cerrojo(rutas, "m34").sellada()
    if sellada is None:
        raise ErrorConfiguracion("no hay una M3-4 sellada en el cerrojo (VER-12)")
    if pedida is not None and pedida != sellada.etiqueta:
        raise ErrorConfiguracion("--etiqueta de M5 y M6 es la de la última M3-4 sellada (VER-12)")
    return sellada.etiqueta


def _modo_real(args, rutas, modo: str, servicios: Servicios, consola: Consola) -> int:
    compuerta = COMPUERTA_DE_MODO[modo]
    nombre = NOMBRE_COMPUERTA[compuerta]
    ahora = servicios.ahora
    cerrojo = None
    if compuerta in CERROJOS:
        try:
            cerrojo = Cerrojo(rutas, compuerta)
        except ErrorCerrojo as e:
            consola(f"{nombre} no corre: {e}")
            return 1
    try:
        U = umbrales.cargar_m0(rutas.aph)
        cfg, huellas_args, etiqueta = _armar(args, rutas, modo, servicios, U)
    except Exception as e:                                          # noqa: BLE001 (VER-14: se registra y se informa)
        if cerrojo is not None:
            linea = cerrojo.registrar({"evento": "intento", "compuerta": compuerta, "fecha_utc": _fecha_utc(ahora()),
                                       "etiqueta": None, "huella_corrida": None, "huellas": {}})
            cerrojo.registrar({"evento": "negada", "intento": linea["intento"], "fecha_utc": _fecha_utc(ahora()),
                               "motivos": ["configuracion"], "error": type(e).__name__})
        detalle = Path(e.filename).name if isinstance(e, OSError) and e.filename else str(e)
        consola(f"{nombre} no se arma: {type(e).__name__}: {detalle}")
        return 1
    huella = orquestacion.huella_de_corrida(cfg, compuerta)
    intento = None
    if cerrojo is not None:
        intento = cerrojo.registrar({"evento": "intento", "compuerta": compuerta, "fecha_utc": _fecha_utc(ahora()),
                                     "etiqueta": etiqueta, "huella_corrida": huella, "huellas": huellas_args,
                                     "interprete": cfg.entradas["interprete"].get("micromamba_list_sha256")})["intento"]
    candado = cerrojo.retener() if cerrojo is not None else contextlib.nullcontext()
    try:
        with candado:
            try:
                fallas = cfg.negativas.fallas(cfg)
            except Exception as e:                                  # noqa: BLE001 (VER-14)
                if cerrojo is not None:
                    cerrojo.registrar({"evento": "negada", "intento": intento, "fecha_utc": _fecha_utc(ahora()),
                                       "motivos": ["error"], "error": type(e).__name__})
                consola(f"{nombre}: error en las negativas: {type(e).__name__}: {e}")
                return 1
            if fallas:
                if cerrojo is not None:
                    cerrojo.registrar({"evento": "negada", "intento": intento, "fecha_utc": _fecha_utc(ahora()),
                                       "motivos": sorted({f.motivo for f in fallas})})
                consola(f"{nombre} se niega a correr (§10; Anexo B):")
                for f in fallas:
                    consola(f"- {f}")
                return 1
            return _correr(cfg, compuerta, nombre, cerrojo, intento, servicios, consola)
    except ErrorCerrojo as e:
        if cerrojo is not None and intento is not None:
            try:
                cerrojo.registrar({"evento": "negada", "intento": intento, "fecha_utc": _fecha_utc(ahora()),
                                   "motivos": ["corrida_en_curso" if "retiene" in str(e) else "cerrojo"]})
            except ErrorCerrojo:
                pass
        consola(f"{nombre} no corre: {e}")
        return 1


def _correr(cfg, compuerta: str, nombre: str, cerrojo: Cerrojo | None, intento: int | None, servicios: Servicios,
            consola: Consola) -> int:
    ahora = servicios.ahora
    carpeta = orquestacion.carpeta_de(cfg, compuerta)
    previa = cerrojo is not None and os.path.lexists(carpeta / orquestacion.AVANCE)
    resultado, error, cruzo = "sellada", None, False
    try:
        if cerrojo is not None:
            n_errata = None
            if cfg.entradas.get("errata"):
                n_errata = leer_errata(cfg.entradas["errata"], cfg.rutas, compuerta)[0]
            cerrojo.registrar({"evento": "inicio", "intento": intento, "fecha_utc": _fecha_utc(ahora()),
                               "etiqueta": cfg.etiqueta,
                               "huella_corrida": orquestacion.huella_de_corrida(cfg, compuerta),
                               "reanuda": previa, "errata": n_errata})
            cerrojo.copiar_a(carpeta)                               # VER-10: antes del sello
        # VER-16: interprete.json con la huella que ya trae Cfg.huellas
        sha_int = salidas.escribir(INTERPRETE_JSON, _identidad_interprete(servicios), clase="resumen", raiz=carpeta)
        if cfg.huellas.get(entorno.alias(carpeta / INTERPRETE_JSON, cfg.rutas)) != sha_int:
            raise ErrorConfiguracion("el intérprete cambió desde que se armó la corrida (VER-16)")
        consola(f"{nombre}: {'se reanuda' if previa else 'empieza'} en {entorno.alias(carpeta, cfg.rutas)}")
        avance = orquestacion.abrir_avance(cfg, compuerta)
        ejecutor = servicios.ejecutor(compuerta)
        with _registro_aislado(cfg.rutas, cfg.permitidas, compuerta):
            if compuerta == "m6":
                ejecutor(cfg, avance=avance)
            else:
                ejecutor(cfg, avance=avance, procesos=cfg.procesos)
    except orquestacion.DetencionPorAlarma as e:
        resultado, error = "detenida_por_alarma", e
    except BaseException as e:                                      # noqa: BLE001 (VER-14: se registra y se informa)
        resultado, error = "abortada", e
    cruzo = os.path.lexists(carpeta / orquestacion.AVANCE)
    if error is not None and not cruzo and resultado == "abortada":
        resultado = ("negada_por_orquestacion" if isinstance(error, orquestacion.ErrorOrquestacion)
                     and _SE_NIEGA in str(error) else "error")
    vivos = ceguera.procesos_hijos_vivos()
    if cerrojo is not None:
        cerrojo.registrar({"evento": "fin", "intento": intento, "fecha_utc": _fecha_utc(ahora()),
                           "etiqueta": cfg.etiqueta, "resultado": resultado, "cruzo_frontera": cruzo,
                           "error": None if error is None else type(error).__name__, "procesos": len(vivos)})
    if vivos:
        consola(f"{nombre}: quedan procesos vivos al terminar (§8: «no quedan procesos vivos»)")
    if error is None:
        consola(f"{nombre}: {resultado} en {entorno.alias(carpeta, cfg.rutas)}")
        return 1 if vivos else 0
    if cruzo:
        consola(f"{nombre}: {resultado} ({type(error).__name__}); el detalle no se muestra después de la frontera")
    else:
        consola(f"{nombre}: {resultado}: {type(error).__name__}: {error}")
    if isinstance(error, (KeyboardInterrupt, SystemExit)):
        raise error
    return 1


# ---------------------------------------------------------------------------
# La batería de M1 (VER-1 a VER-5, VER-17)
# ---------------------------------------------------------------------------
class _Ventana:
    """VER-1 (MC-31): el registro de los insumos de datos de S14 y del costo se suelta sólo mientras corre una prueba
    de ``test_salud.PruebasS14``."""

    def __init__(self, registro, clases: set):
        self.registro, self.clases, self.activo = registro, set(clases), False

    def cerrar(self) -> None:
        if self.registro is not None and not self.activo:
            self.registro.__enter__()
            self.activo = True

    def abrir(self) -> None:
        if self.registro is not None and self.activo:
            self.registro.__exit__(None, None, None)
            self.activo = False

    def antes(self, test) -> None:
        if type(test) in self.clases:
            self.abrir()

    def despues(self, test) -> None:
        if type(test) in self.clases:
            self.cerrar()


class _Resultado(unittest.TextTestResult):
    """La salida de ``unittest`` en verbosidad 2, sin trazas ni parámetros de subTest (VER-2); guarda los éxitos y abre
    la ventana de S14 (VER-1)."""

    def __init__(self, *a, ventana: _Ventana | None = None, **k):
        super().__init__(*a, **k)
        self.exitos: list = []
        self._ventana = ventana

    def startTest(self, test):
        if self._ventana is not None:
            self._ventana.antes(test)
        super().startTest(test)

    def stopTest(self, test):
        super().stopTest(test)
        if self._ventana is not None:
            self._ventana.despues(test)

    def addSuccess(self, test):
        super().addSuccess(test)
        self.exitos.append(test)

    def getDescription(self, test):
        base = getattr(test, "test_case", None)
        if base is not None and type(test).__name__ == "_SubTest":
            return f"{base} [subTest]"
        return super().getDescription(test)

    def printErrorList(self, flavour, errors):
        for test, _ in errors:
            self.stream.writeln(self.separator1)
            self.stream.writeln(f"{flavour}: {_identificador(test)}")


def _identificador(test) -> str:
    """El identificador de una prueba (el de la prueba madre en un subTest), sin parámetros ni descripción."""
    base = getattr(test, "test_case", None)
    t = base if base is not None and type(test).__name__ == "_SubTest" else test
    return t.id() if hasattr(t, "id") else str(t)


def _descubrir(patrones: Sequence[str]) -> unittest.TestSuite:
    loader = unittest.TestLoader()
    if patrones:
        loader.testNamePatterns = [p if "*" in p else f"*{p}*" for p in patrones]
    return loader.discover(start_dir=str(PRUEBAS), top_level_dir=str(RAIZ_CODIGO))


def _pruebas(suite) -> Iterable[unittest.TestCase]:
    for t in suite:
        if isinstance(t, unittest.TestSuite):
            yield from _pruebas(t)
        elif t is not None:
            yield t


def _modulo_de_pruebas(nombre: str):
    return sys.modules.get(f"{PAQUETE.name}.tests.{nombre}")


def _insumos_s14(reales) -> tuple[str, ...]:
    """MC-31: las rutas que S14 abre, con el año de la prueba (MC-32)."""
    mod = _modulo_de_pruebas("test_salud")
    if mod is None or not hasattr(mod, "salud") or not hasattr(mod, "ANIO"):
        return ()
    return tuple(str(p) for p in mod.salud.insumos_s14(mod.ANIO, reales).values())


def _insumos_costo(medidor, reales) -> tuple[str, ...]:
    """§8.1, punto 6, y la geometría de la grilla (COS-10): sólo con ``--costo``."""
    salida = [str(Path(reales.grilla) / "celdas.parquet")]
    ruta_mes = getattr(medidor, "ruta_mes_real", None)
    if callable(ruta_mes):
        salida.append(str(ruta_mes(reales)))
    return tuple(salida)


def _clases_s14(suite) -> set:
    """Las clases ``test_salud.PruebasS14`` de la suite, tomadas antes de correrla (``TestSuite.run`` suelta cada
    prueba al terminarla)."""
    return {type(t) for t in _pruebas(suite) if type(t).__name__ == "PruebasS14"
            and type(t).__module__.endswith(".test_salud")}


def _informe_s14(clases: set, resultado) -> dict:
    """H11: S14 corrida (su prueba entre los éxitos) y su informe (``PruebasS14.informe``)."""
    clases = set(clases)
    if not clases:
        return {"corrio": False, "resultado": None, "carpetas": {}}
    clase = clases.pop()
    exitos = {t.id() for t in resultado.exitos if type(t) is clase}
    informe = getattr(clase, "informe", None)
    corrio = bool(exitos) and informe is not None
    carpetas = {}
    if corrio:
        for tipo, (res, dif, _) in dict(informe.get("carpetas", {})).items():
            carpetas[str(tipo)] = {"resultado": str(res), "dif_max": float(dif)}
    return {"corrio": corrio, "resultado": None if not corrio else str(informe.get("resultado")), "carpetas": carpetas}


def _deriva_s6() -> tuple[dict | None, dict | None, str | None]:
    """VER-4: (compuerta, contenido de ``deriva_s6.json``, error) de la S6 que corrió en la batería."""
    mod = _modulo_de_pruebas("test_tendencias")
    s6 = getattr(mod, "_S6_CACHE", None) if mod is not None else None
    if s6 is None:
        return None, None, None
    from meteo_combinada import tendencias
    try:
        compuerta = tendencias.compuerta_deriva(s6.deriva, umbrales=s6.U)
        contenido = tendencias.contenido_deriva_s6(s6.deriva, compuerta, regla=s6.escenarios.regla,
                                                   n_red=s6.escenarios.n_red, parametros=s6.red_d["parametros"])
    except Exception as e:                                          # noqa: BLE001 (se informa)
        return None, None, type(e).__name__
    return dict(compuerta), contenido, None


def _por_numero(resultado) -> dict[str, dict[str, int]]:
    salida: dict[str, dict[str, int]] = {}

    def contar(test, clave):
        base = getattr(test, "test_case", test)
        m = _PATRON_S.match(getattr(base, "_testMethodName", ""))
        if m:
            d = salida.setdefault(f"s{m.group(1)}", {"ok": 0, "fallas": 0, "errores": 0, "omitidas": 0})
            d[clave] += 1
    for t in resultado.exitos:
        contar(t, "ok")
    for t, _ in resultado.failures:
        contar(t, "fallas")
    for t, _ in resultado.errors:
        contar(t, "errores")
    for t, _ in resultado.skipped:
        contar(t, "omitidas")
    return dict(sorted(salida.items()))


def _omisiones_no_permitidas(resultado) -> list[str]:
    """VER-3: las omisiones fuera de ``OMISIONES_PERMITIDAS`` (identificador y comienzo del motivo)."""
    malas = []
    for t, motivo in resultado.skipped:
        ident = _identificador(t)
        prefijo = OMISIONES_PERMITIDAS.get(ident)
        if prefijo is None or not str(motivo).startswith(prefijo):
            malas.append(ident)
    return malas


def _medir_costo(medidor, reales, U) -> tuple[dict | None, str | None, str | None, str]:
    """(contenido, recorte, error, temporal); carga registrada, no excluyente (EMC4/D68; §8.1)."""
    temporal = Path(tempfile.gettempdir()) / f"meteo_combinada_costo_{os.getpid()}_{uuid.uuid4().hex}"
    try:
        mediciones = medidor.medir(reales, real_era5=True, umbrales=U, temporal=temporal)
        proyeccion = medidor.proyectar(mediciones, U)
        recorte = medidor.recorte(proyeccion, U)
        contenido = medidor.contenido_costo(mediciones, proyeccion, U)
    except Exception as e:                                          # noqa: BLE001 (se informa)
        return None, None, type(e).__name__, str(temporal)
    return contenido, recorte, None, str(temporal)


def _verificar_reproduccion_costo(mediciones, original, U):
    """EMC5: el código histórico fijado debe reproducir TODO el informe persistido, sin medir."""
    import dataclasses
    from types import ModuleType
    commit = "9bd45e1d5249ba4121fc8375983cc129d8bb0d7b"
    esperado = "eb0b07ec26a6aaa4ee89240177519e1dbad722a71b36c2db97a8bec85e8ace87"
    r = _git(entorno.rutas_reales().ap, "show", commit + ":scripts_modelo_1km/meteo_combinada/costo.py")
    if r.returncode != 0 or hashlib.sha256(r.stdout).hexdigest() != esperado:
        raise ValueError("no se dispone del código histórico fijado")
    nombre = "meteo_combinada._costo_historico_emc4"
    historico = ModuleType(nombre)
    historico.__file__ = str(PAQUETE / "costo.py")
    sys.modules[nombre] = historico
    try:
        exec(compile(r.stdout, historico.__file__, "exec"), historico.__dict__)
        U_historico = dataclasses.replace(U, sha256_texto_vigente=
            "7771e830c526d8a0da93453e7e2d821896ba797147d14803969907ce5749589d")
        proyeccion = historico.proyectar(mediciones, U_historico)
        reproducido = historico.contenido_costo(mediciones, proyeccion, U_historico)
    finally:
        sys.modules.pop(nombre, None)
    if original != reproducido:
        raise ValueError("la reconstrucción no reproduce exactamente el informe histórico")
    return {"comparacion_proyeccion_original": "identica", "codigo_historico_sha256": esperado,
            "commit_historico": commit}


def _reproyectar_costo(medidor, ruta, sha256, U):
    """EMC5: sólo proyección nueva de mediciones conservadas; nunca se presenta como medición nueva."""
    from meteo_combinada import reutilizacion_costo
    try:
        comprobacion = {}
        def verificar(mediciones, original):
            comprobacion.update(_verificar_reproduccion_costo(mediciones, original, U))
        mediciones, procedencia = reutilizacion_costo.cargar(ruta, sha256=sha256, umbrales=U, verificar=verificar)
        if comprobacion.get("comparacion_proyeccion_original") != "identica":
            raise ValueError("la reproducción histórica no se ejecutó")
        procedencia.update(comprobacion)
        historico = entorno.rutas_reales().local / "meteo_combinada/v1/m1/20261031T040149Z/costo_m1.json"
        if (Path(ruta) != historico or sha256 !=
                "c92aeec3a4cb003d1be0c36af2e0650bdb6ff3e5a89df9356167890234be06a6"):
            raise ValueError("la reutilización operativa sólo admite el origen histórico fijado")
        procedencia["fuente_historica"] = "LOCAL/meteo_combinada/v1/m1/20261031T040149Z/costo_m1.json"
        procedencia["fecha_inicio_bateria_historica_utc"] = "2026-10-31T04:01:49Z"
        procedencia["fecha_cierre_bateria_historica_utc"] = "2026-10-31T11:50:28.472900Z"
        procedencia["advertencia"] = ("No es una medición nueva. El informe histórico se reprodujo exactamente con "
            "su código fijado; la proyección nueva usa EMC5 y requiere la suite íntegra vigente. "
            "La batería histórica no cambia de estado y las cargas se conservan sin falsear.")
        proyeccion = medidor.proyectar(mediciones, U)
        contenido = medidor.contenido_costo(mediciones, proyeccion, U)
        contenido["mediciones_reutilizadas"] = True
        contenido["procedencia_reutilizacion"] = procedencia
        ceguera.vigilar_salida(COSTO_M1, contenido, clase="resumen")
        return contenido, medidor.recorte(proyeccion, U), None, None
    except Exception as e:                                          # noqa: BLE001 (queda como no aprobado)
        return None, None, type(e).__name__, None


def _texto_pruebas(sha: str, salida_unittest: str) -> str:
    return f"Pruebas de M1 del producto meteorológico combinado; texto vigente sha256 {sha}\n{salida_unittest}"


def _pruebas_reducidas(resultado, segundos: float, sha: str) -> str:
    """VER-2: la forma reducida de ``pruebas_m1.txt``: sólo identificadores y estados."""
    estados: dict[str, str] = {}
    for t in resultado.exitos:
        estados[_identificador(t)] = "ok"
    for t, _ in resultado.skipped:
        estados[_identificador(t)] = "skipped"
    for t, _ in resultado.expectedFailures:
        estados[_identificador(t)] = "expected failure"
    for t in resultado.unexpectedSuccesses:
        estados[_identificador(t)] = "unexpected success"
    for t, _ in resultado.failures:
        estados[_identificador(t)] = "FAIL"
    for t, _ in resultado.errors:
        estados[_identificador(t)] = "ERROR"
    lineas = [f"{i} ... {e}" for i, e in sorted(estados.items())]
    resumen = ("OK" if resultado.wasSuccessful() else "FAILED")
    partes = [f"{k}={v}" for k, v in (("failures", len(resultado.failures)), ("errors", len(resultado.errors)),
                                      ("skipped", len(resultado.skipped))) if v]
    lineas += ["", f"Ran {resultado.testsRun} tests in {segundos:.3f}s", "",
               resumen + (f" ({', '.join(partes)})" if partes else "")]
    return _texto_pruebas(sha, "\n".join(lineas) + "\n")


def _huellas_codigo(reales) -> dict[str, str]:
    """VER-3: las huellas del código del paquete y de ``tests/`` (y de sus documentos)."""
    salida = {a: entorno.sha256_archivo(p) for a, p in addendum.codigo_del_paquete(reales.ap).items()}
    salida.update({f"AP/{addendum.CARPETA_PAQUETE}/{n}": entorno.sha256_archivo(PAQUETE / n)
                   for n in addendum.DOCUMENTOS_PAQUETE if (PAQUETE / n).is_file()})
    return salida


def _carpeta_de_bateria(rutas, inicio: datetime) -> Path:
    """VER-2: ``LOCAL/meteo_combinada/v1/m1/<AAAAMMDDTHHMMSSZ>`` (con «-k» si ya existe)."""
    base = inicio.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    sub, k = base, 1
    while entorno.carpeta_salida(rutas, "m1", sub).exists():
        k += 1
        sub = f"{base}-{k}"
    return entorno.carpeta_salida(rutas, "m1", sub)


def correr_bateria(rutas, *, servicios: Servicios | None = None, patrones: Sequence[str] = (),
                   suite: unittest.TestSuite | None = None, costo: bool = False,
                   commits: Mapping[str, str] | None = None, consola: Consola | None = None,
                   forzar_completa: bool = False, costo_desde=None, costo_sha256: str | None = None) -> int:
    """La batería de M1 (VER-1 a VER-5, VER-17): 0 si M1 se aprueba (VER-3), 1 si no. ``patrones`` (``--solo``) o
    ``suite`` corren un subconjunto: la batería queda «parcial» y no se aprueba ni escribe el addendum.
    ``forzar_completa`` es sólo para las pruebas: trata una ``suite`` dada como completa, para ejercitar el addendum."""
    if (costo_desde is None) != (costo_sha256 is None) or (costo_desde is not None and not costo):
        raise ValueError("reutilizar costo exige --costo, fuente y SHA256 juntos")
    if costo_desde is not None:
        costo_desde = Path(costo_desde).absolute()
    servicios = servicios or Servicios()
    reales = entorno.rutas_reales()
    parcial = (bool(patrones) or suite is not None) and not forzar_completa
    referencia = addendum.referencia(reales)
    texto_sha = referencia.sha256_texto
    consola = consola or Consola(referencia)
    consola("batería de M1 (--sintetico" + (" --costo" if costo else "") + (", parcial" if parcial else "") + ")")
    inicio = servicios.ahora()
    motivos: list[str] = []
    codigo_antes = _huellas_codigo(reales)                          # VER-3: antes de descubrir la suite
    # 1. el entorno fijado y el código fijado (VER-3, VER-5)
    try:
        interprete = dict(entorno.comprobar_interprete())
    except RuntimeError:
        interprete = {}
        motivos.append("interprete")
    entorno.fijar_hilos()
    try:
        texto_mm = servicios.micromamba()
        sha_mm = fijados.huella_micromamba(texto_mm)
    except (OSError, subprocess.SubprocessError):
        texto_mm, sha_mm = None, None
    diferencias = fijados.comprobar_codigo_fijado(reales.ap, reales.aph, micromamba_list=texto_mm)
    if texto_mm is None:
        diferencias.append("micromamba list no se pudo correr (FIJ-3)")
    if diferencias:
        motivos.append("codigo_fijado")
    U = umbrales.cargar_m0(reales.aph)
    # 2. la suite, aislada (VER-1)
    repos = tuple(dict.fromkeys(str(p) for p in (reales.ap, reales.aph, rutas.ap, rutas.aph)))
    vigiladas = ("/" + "Volumes", *repos)
    medidor = servicios.costo() if costo else None
    captura, flujo = io.StringIO(), io.StringIO()
    with directorio_neutro(), ceguera.SinRed() as red:
        with ceguera.RegistroAccesos(vigiladas, bloquear=True, permitidas=repos) as reg0, \
                ceguera.RegistroAccesos(_zonas_ciegas(reales), bloquear=True) as ciego0, \
                contextlib.redirect_stdout(captura), contextlib.redirect_stderr(captura):
            suite = suite if suite is not None else _descubrir(patrones)
        insumos = _insumos_s14(reales) + ((str(Path(costo_desde).absolute()),) if costo_desde is not None
                                          else _insumos_costo(medidor, reales) if costo else ())
        de_datos = tuple(p for p in insumos if not any(p == r or p.startswith(r.rstrip("/") + "/") for r in repos))
        estricto = ceguera.RegistroAccesos(de_datos, bloquear=True) if de_datos else None
        with ceguera.RegistroAccesos(vigiladas, bloquear=True, permitidas=(*repos, *insumos)) as reg, \
                ceguera.RegistroAccesos(_zonas_ciegas(reales), bloquear=True) as ciego, \
                contextlib.redirect_stdout(captura), contextlib.redirect_stderr(captura):
            contenido_costo, recorte, error_costo, temporal = (None, None, None, None)
            if costo:                                               # VER-17: primero; carga informativa (EMC4)
                if costo_desde is None:
                    contenido_costo, recorte, error_costo, temporal = _medir_costo(medidor, reales, U)
                else:
                    contenido_costo, recorte, error_costo, temporal = _reproyectar_costo(
                        medidor, costo_desde, costo_sha256, U)
            clases_s14 = _clases_s14(suite)
            ventana = _Ventana(estricto, clases_s14)
            ventana.cerrar()
            try:
                t0 = time.perf_counter()
                resultado = unittest.TextTestRunner(stream=flujo, verbosity=2, resultclass=functools.partial(
                    _Resultado, ventana=ventana)).run(suite)
                segundos = time.perf_counter() - t0
            finally:
                ventana.abrir()
            s14 = _informe_s14(clases_s14, resultado)
            compuerta, contenido_deriva, error_deriva = _deriva_s6()
    vivos = ceguera.procesos_hijos_vivos()
    accesos = sum(len(r.accesos) for r in (reg0, reg, ciego0, ciego, *(() if estricto is None else (estricto,))))
    de_s14 = {i.casefold() for i in insumos}
    lecturas_s14 = sum(1 for _, p in reg.lecturas_permitidas if p.casefold() in de_s14)
    # 3. aprobación (VER-3)
    por_implementar = sum(1 for _, motivo in resultado.skipped if motivo == POR_IMPLEMENTAR)
    no_permitidas = _omisiones_no_permitidas(resultado)
    if resultado.failures:
        motivos.append("fallas")
    if resultado.errors:
        motivos.append("errores")
    if resultado.expectedFailures or resultado.unexpectedSuccesses:
        motivos.append("fallas_esperadas_o_exitos_inesperados")
    if por_implementar:
        motivos.append("omitidas_por_implementar")
    if no_permitidas:
        motivos.append("omitidas_no_permitidas")
    if not s14["corrio"]:
        motivos.append("s14_no_corrio")
    elif s14["resultado"] != "igual":
        motivos.append("s14_distinto")
    if contenido_deriva is None:
        motivos.append("deriva_no_calculada")
    if not costo:
        motivos.append("sin_costo")
    elif contenido_costo is None:
        motivos.append("costo_no_medido")
    elif recorte not in _recortes(U):
        motivos.append("recorte_pendiente")             # A39: alguna fase no cabe ni con 1 proceso, o no se midió
    elif _procesos_por_fase(contenido_costo.get("procesos_por_fase")) is None:
        motivos.append("procesos_por_fase")             # VER-22: sin la forma exacta de FASES_REPARTO
    if accesos:
        motivos.append("accesos")
    if vivos:
        motivos.append("procesos_vivos")
    if parcial:
        motivos.append("parcial")
    lista0 = None
    if not parcial:
        try:
            lista0 = addendum.lista_cerrada(reales)
        except (addendum.ErrorAddendum, OSError):
            motivos.append("lista_cerrada")
    if _huellas_codigo(reales) != codigo_antes:
        motivos.append("codigo_cambio")
    # 4. las salidas (VER-2), por salidas, en la subcarpeta de esta batería
    carpeta = _carpeta_de_bateria(rutas, inicio)
    alias_carpeta = entorno.alias(carpeta, rutas)
    huellas: dict[str, str] = {}

    def escribir(nombre, contenido, clase, ref=None):
        sha = salidas.escribir(nombre, contenido, clase=clase, raiz=carpeta, referencia=ref)
        huellas[entorno.alias(carpeta / nombre, rutas)] = sha
        return sha

    ref_pruebas = ceguera.ReferenciaDocumento(
        addendum.texto_vigente(reales)[0], texto_sha,
        fuentes={f"AP/{addendum.CARPETA_PAQUETE}/tests/{p.name}": _leer_texto(p) for p in sorted(PRUEBAS.glob("*.py"))})
    try:
        escribir(PRUEBAS_M1, _texto_pruebas(texto_sha, flujo.getvalue()), "documento", ref_pruebas)
        forma = "completa"
    except ceguera.SalidaProhibida:
        escribir(PRUEBAS_M1, _pruebas_reducidas(resultado, segundos, texto_sha), "documento", ref_pruebas)
        forma = "reducida"
    escribir(ANEXO_A2, addendum.anexo_a2(reales), "documento", referencia)
    if contenido_deriva is not None:
        escribir(DERIVA_S6, contenido_deriva, "resumen")
    if contenido_costo is not None:
        escribir(COSTO_M1, contenido_costo, "resumen")
    fecha = inicio.astimezone(timezone.utc).strftime("%Y-%m-%d")

    def ref(nombre, **extra):
        a = entorno.alias(carpeta / nombre, rutas)
        return {"ruta": a, "sha256": huellas[a], **extra}

    def armar(lista, resumen_ref, aprobada_):
        """El contenido del addendum de esta batería (A33), con los procesos por fase de su costo (VER-22)."""
        costo_ref = None if contenido_costo is None else ref(
            COSTO_M1, recorte=recorte, procesos_por_fase=contenido_costo.get("procesos_por_fase"))
        return addendum.addendum_m1(
            lista, ref(ANEXO_A2), None if contenido_deriva is None else ref(DERIVA_S6, pasa=compuerta), recorte,
            costo_ref, lecturas, dict(commits or {"ap": addendum.PENDIENTE, "aph": addendum.PENDIENTE}), fecha=fecha,
            bateria={"carpeta": alias_carpeta, "resumen": resumen_ref, "aprobada": aprobada_})

    # 5a. el addendum se arma antes del resumen, con una huella provisional de éste, y pasa la guarda del documento
    # (VER-2): si no, la batería no aprueba y el resumen lo dice
    lecturas = None
    if not parcial and lista0 is not None:
        try:
            lecturas = addendum.lecturas_m1(reales)
            escrita = addendum.lista_cerrada(reales, bateria=huellas, rutas_bateria=rutas)    # sin resumen ni sha256
            provisional = armar(escrita, {"ruta": entorno.alias(carpeta / RESUMEN_M1, rutas),
                                          "sha256": entorno.sha256_bytes(b"")}, False)
            ceguera.vigilar_salida(addendum.NOMBRE_JSON, provisional, clase="documento", referencia=referencia)
            ceguera.vigilar_salida(addendum.NOMBRE_MD, addendum.addendum_md(provisional), clase="documento",
                                   referencia=referencia)
        except (addendum.ErrorAddendum, ceguera.SalidaProhibida, OSError) as e:
            lecturas = None
            motivos.append("addendum")
            consola(f"el addendum no se puede armar: {type(e).__name__}")
    aprobada = not motivos
    resumen = {
        "esquema": ESQUEMA_RESUMEN, "texto_vigente_sha256": texto_sha, "fecha_utc": _fecha_utc(inicio),
        "modo": {"costo": bool(costo), "parcial": parcial, "patrones": len(patrones)},
        "pruebas": {"corridas": resultado.testsRun, "ok": len(resultado.exitos), "fallas": len(resultado.failures),
                    "errores": len(resultado.errors), "omitidas": len(resultado.skipped),
                    "omitidas_por_implementar": por_implementar, "omitidas_no_permitidas": len(no_permitidas),
                    "fallas_esperadas": len(resultado.expectedFailures),
                    "exitos_inesperados": len(resultado.unexpectedSuccesses), "segundos": round(segundos, 1),
                    "pruebas_m1": forma},
        "por_numero": _por_numero(resultado),
        "s14": s14,
        "deriva": {"calculada": contenido_deriva is not None, "pasa": compuerta, "error": error_deriva},
        "costo": {"medido": contenido_costo is not None, "recorte": recorte, "error": error_costo,
                  "carpeta_temporal": None if temporal is None else Path(temporal).name,
                  "mediciones_reutilizadas": costo_desde is not None,
                  "huella_origen": costo_sha256 if costo_desde is not None else None},
        "ceguera": {"accesos": accesos, "por_enlace": len(reg0.por_enlace) + len(reg.por_enlace),
                    "negados_dentro": len(reg0.negados_dentro) + len(reg.negados_dentro),
                    "lecturas_permitidas": len(reg0.lecturas_permitidas) + len(reg.lecturas_permitidas),
                    "lecturas_s14": lecturas_s14, "red_intentos": len(red.intentos), "procesos_vivos": len(vivos),
                    "lineas_capturadas": len(captura.getvalue().splitlines())},
        "interprete": {**interprete, "micromamba_list_sha256": sha_mm,
                       "micromamba_fijado": sha_mm == fijados.SHA_MICROMAMBA_LIST},
        "codigo_fijado": {"diferencias": len(diferencias)},
        "aprobada": aprobada, "motivos": motivos, "huellas": dict(sorted(huellas.items())),
    }
    escribir(RESUMEN_M1, resumen, "resumen")
    huellas[entorno.alias(carpeta / SHA256_JSON, rutas)] = salidas.escribir_sha256(carpeta)
    # 5b. el addendum (A33), sólo de una batería completa; marcado con «aprobada» (VER-2)
    salida_addendum = None
    if lecturas is not None:
        try:
            lista = addendum.lista_cerrada(reales, bateria=huellas, rutas_bateria=rutas)
            contenido = armar(lista, ref(RESUMEN_M1), aprobada)
            salidas.escribir(addendum.NOMBRE_JSON, contenido, clase="documento", raiz=carpeta, referencia=referencia)
            salidas.escribir(addendum.NOMBRE_MD, addendum.addendum_md(contenido), clase="documento", raiz=carpeta,
                             referencia=referencia)
            salida_addendum = entorno.alias(carpeta / addendum.NOMBRE_JSON, rutas)
        except (addendum.ErrorAddendum, ceguera.SalidaProhibida, OSError) as e:
            consola(f"el addendum no se escribió: {type(e).__name__}")    # VER-2: el límite declarado
            motivos.append("addendum")
            aprobada = False
    # 6. la consola (VER-21: D13, CEG-18)
    for linea in flujo.getvalue().splitlines():
        if linea.startswith(("Ran ", "OK", "FAILED")):
            consola(linea)
    consola("batería de M1: " + ("aprobada" if aprobada else "no aprobada: " + ", ".join(motivos)))
    consola(f"- carpeta: {alias_carpeta}")
    for a, s in sorted(huellas.items()):
        consola(f"- {a} {s}")
    if salida_addendum:
        consola(f"- {salida_addendum} (y su .md)")
    return 0 if aprobada else 1


def _leer_texto(ruta: Path) -> str:
    with open(ruta, "rb") as f:
        return f.read().decode("utf-8")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def analizar_argumentos(argv: Sequence[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="verificar_meteo_combinada", description=__doc__.splitlines()[0])
    g = p.add_mutually_exclusive_group(required=True)
    for m in MODOS:
        g.add_argument(f"--{m}", dest="modo", action="store_const", const=m)
    p.add_argument("--costo", action="store_true", help="con --sintetico: mide el costo (§8.1; carga informativa, EMC4)")
    p.add_argument("--costo-desde", help="con --sintetico --costo: informe histórico fijado, sin nueva medición")
    p.add_argument("--costo-sha256", help="SHA256 obligatorio de --costo-desde (EMC5)")
    p.add_argument("--solo", action="append", default=[], metavar="PATRON",
                   help="con --sintetico: sólo las pruebas cuyo nombre calza (batería parcial, no aprueba M1)")
    p.add_argument("--commits", nargs=2, metavar=("COMMIT_AP", "COMMIT_APH"),
                   help="con --sintetico: los commits de M1 para el addendum (si no, «pendiente»)")
    p.add_argument("--addendum", help="addendum_m1.json (MC-54)")
    p.add_argument("--entradas", help="archivo de entradas de la compuerta (VER-13)")
    p.add_argument("--etiqueta", help="HUMAN<AAAAMMDD>_METEO_COMB_<n>[_ERRATA<k>] (VER-12)")
    p.add_argument("--errata", help="errata confirmada (§10), con --aplicar o --m6")
    args = p.parse_args(argv)
    if (args.costo_desde is None) != (args.costo_sha256 is None):
        p.error("--costo-desde y --costo-sha256 se requieren juntos")
    if args.costo_desde is not None and (args.modo != "sintetico" or not args.costo):
        p.error("--costo-desde exige --sintetico --costo")
    if args.costo_desde is not None:
        args.costo_desde = str(Path(args.costo_desde).absolute())
    if args.costo_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", args.costo_sha256):
        p.error("--costo-sha256 requiere 64 hexadecimales")
    if args.modo != "sintetico" and (args.costo or args.solo or args.commits):
        p.error("--costo, --solo y --commits son de --sintetico")
    if args.modo == "sintetico" and (args.addendum or args.entradas or args.etiqueta or args.errata):
        p.error("--addendum, --entradas, --etiqueta y --errata son de las corridas reales")
    if args.commits and not all(_COMMIT.fullmatch(c) for c in args.commits):
        p.error("--commits lleva dos commits de 40 hexadecimales")
    return args


def main(argv: Sequence[str] | None = None, *, rutas=None, servicios: Servicios | None = None) -> int:
    """--sintetico [--costo] | --estaticos | --aplicar | --producir | --m6 (§8)."""
    args = analizar_argumentos(argv)
    rutas = rutas if rutas is not None else entorno.rutas_reales()
    servicios = servicios or Servicios()
    if args.modo == "sintetico":
        commits = None if not args.commits else {"ap": args.commits[0], "aph": args.commits[1]}
        return correr_bateria(rutas, servicios=servicios, patrones=tuple(args.solo), costo=args.costo,
                              commits=commits, costo_desde=args.costo_desde, costo_sha256=args.costo_sha256)
    consola = Consola(addendum.referencia(entorno.rutas_reales()))
    return _modo_real(args, rutas, args.modo, servicios, consola)


if __name__ == "__main__":
    # Un solo ejemplar del módulo, también corrido como script o con -m (VER-14 del reloj): así ``Negativas`` es la
    # misma clase con el mismo nombre de módulo y la huella de la corrida (ORQ-34) no depende de cómo se lanzó. Es el
    # propio módulo, no una dependencia.
    raise SystemExit(importlib.import_module(f"{PAQUETE.name}.{Path(__file__).stem}").main())
