"""Ceguera y aislamiento (§0.4 y §1.9 del texto; S7 y S10).

Responsabilidad única: impedir que una corrida vea o guarde lo que el texto prohíbe, y que toque lo que no debe.
- ``RegistroAccesos``: registro de «open», de los listados y de las demás operaciones de ruta (gancho de auditoría,
  ``sys.addaudithook``) y de ``os.stat``, ``os.lstat`` y ``os.access`` (envoltorios mientras dura), bajo unas carpetas
  vigiladas. Con ``bloquear`` niega el acceso antes de que ocurra (falla cerrado). Copia el patrón de
  ``reloj_dmc.verificar_reloj_dmc.RegistroAccesos`` (registros anidados, del más interior al más exterior; VER-14 del
  reloj), sin importarlo, con la lección de su Enmienda 4: **la ruta léxica antes de resolver**.
- ``SinRed``: niega toda conexión de red mientras dura (gancho de auditoría de ``socket`` y de los clientes de la
  biblioteca estándar).
- ``procesos_hijos_vivos``: los descendientes vivos del proceso y de los grupos que se vigilan (S10).
- ``vigilar_salida``: la guarda de S7 por clase de salida (decisiones D3, D12, D13, D14 y D53 del autor; MC-02), con
  la clase que fija la ruta (``clase_de_ruta``); los documentos se vigilan con una ``ReferenciaDocumento`` (el texto
  vigente y las fuentes de las lecturas), y la consola con ``ConsolaDocumento``.
- ``permitido_de_reloj``: lo único que se puede abrir de RELOJ (§1.9, MC-19).
- ``GuardaResiduo``: centinelas en memoria (la mediana y el MAD del residuo) que no deben aparecer en ninguna salida
  (§0.4.6, S7).
Sin E/S al importarse: el gancho de auditoría se instala la primera vez que se entra en un contexto y queda inerte
fuera de ellos (un gancho no se puede quitar).

Lecturas propias (CEG-n), para el addendum de M1 (corregidas tras la revisión independiente de la ola 1):
- CEG-1. **Registro: léxica antes de resolver, y el camino que sigue el sistema.** Cada acceso se juzga primero por su
  ruta léxica (``normpath(abspath(…))``, sin tocar el disco y sin distinguir mayúsculas, como APFS): si cae bajo una
  vigilada, se anota o se niega sin consultar nada. Si no, se recorre la ruta absoluta **sin normalizar sus «..»**
  (``os.path.join(os.getcwd(), ruta)``), componente a componente y como el sistema: se siguen los enlaces con los
  ``os.lstat`` y ``os.readlink`` originales y cada «..» se aplica sobre la ruta física a que se llegó. Así
  «afuera/L/../secreto.txt», con L → VIGILADA/sub, llega a VIGILADA/secreto.txt y se niega (hallazgo H7: con la ruta
  ya normalizada se perdía). **Antes de consultar un componente se mira si cae bajo una vigilada**: si cae, el acceso
  se anota con esa ruta (``accesos`` y ``por_enlace``) y no se consulta. Un componente bajo /Volumes nunca se consulta:
  desde allí el recorrido sigue léxico (y vuelve a consultar si un «..» lo saca de /Volumes); lo mismo bajo una
  vigilada (CEG-22). Un componente que no existe detiene el recorrido, como al sistema (el resto se mira léxico). En
  ``os.lstat``, ``os.remove``, ``os.rmdir``, ``os.rename``, ``os.link``, ``os.symlink`` y ``shutil.rmtree``/``move``
  el último componente no se sigue; el destino de ``os.symlink`` (su primer argumento) no se mira (CEG-22).
- CEG-2. **Vigiladas y permitidas en sus dos formas.** Al construir el registro, cada vigilada y cada permitida se guarda
  léxica y también recorrida con la misma regla de CEG-1 (en macOS, /var → /private/var), sin pasar por los registros
  activos y **sin consultar nunca /Volumes** (hallazgo H8: ``realpath`` seguía un enlace hacia /Volumes y consultaba sus
  componentes).
- CEG-3. **Permitidas** (S14 y la medición del costo, MC-31): dentro de una vigilada, una ruta igual a una permitida o
  bajo ella se puede **leer** (``open`` sin escritura, listados, ``os.stat``, ``os.lstat``, ``os.access`` y la lectura
  de atributos); no se anota como acceso sino en ``lecturas_permitidas``. Escribir, renombrar o borrar allí sigue
  siendo un acceso.
- CEG-4. **Eventos.** Los de ``reloj_dmc`` (open, listados, mkdir, rename, remove, symlink, link, truncate, utime,
  chmod, chown, atributos, glob y shutil), más ``glob.glob/2``, ``os.chflags``, ``os.setxattr``, ``os.removexattr`` y
  ``shutil.unpack_archive``. Sólo se miran los argumentos que son rutas de cada evento (en «open», sólo el primero:
  el reloj miraba también el modo, «rb», como si fuera una ruta). Un acceso por descriptor (un entero) no tiene ruta.
- CEG-5. **Límite declarado.** Las lecturas que hacen bibliotecas en C (netCDF4, pyarrow, rasterio) no pasan por el
  gancho de auditoría de Python: el registro sólo las ve si antes se abre el archivo con ``open`` de Python, por
  ejemplo para calcular su sha256 (la cadena de huellas de §8 lo hace siempre), o si quien lee llama a
  ``anunciar_acceso`` con la ruta. Lo mismo vale para la red en ``SinRed``.
- CEG-6. **Red.** ``SinRed`` niega ``socket.connect``, ``sendto``, ``sendmsg`` y ``bind`` de toda familia salvo
  AF_UNIX (comunicación local entre procesos, que usa ``multiprocessing``), las consultas de nombres
  (``getaddrinfo``, ``gethostbyname``, ``gethostbyaddr`` y ``getnameinfo``) y los clientes de la biblioteca estándar
  (``urllib``, ``http.client``, ``ftplib``, ``smtplib``, ``poplib``, ``imaplib``, ``nntplib`` y ``webbrowser``).
  El intento se anota en ``intentos`` y lanza ``RedProhibida`` antes de ocurrir.
- CEG-7. **Procesos vivos.** Según ``ps -A -o pid= -o ppid= -o pgid= -o stat=``: los descendientes del proceso,
  directos o no, **y los procesos de los grupos que se vigilan** (``grupos``) con sus descendientes, sin el propio
  ``ps``, sin este proceso y sin los zombis. Un nieto huérfano (``sh -c "sleep 20 &"``) ya no cuelga de este proceso:
  sólo se ve por su grupo (hallazgo H9), así que ``orquestacion`` lanza sus trabajadores en un grupo propio y lo pasa.
- CEG-8. **Qué se mira en una métrica o un resumen** (D3). **Todo texto**: cada componente del nombre del archivo (sin
  la extensión); las columnas, los nombres de índice, las claves, los nombres de variables, dimensiones, grupos y
  atributos de un NetCDF y las claves de los metadatos de un parquet; y como texto libre, palabra por palabra, todo
  valor de texto: celdas, valores de diccionarios y listas, valores de atributos y de metadatos, el texto de una
  consola o un informe (hallazgo H1: antes sólo se miraban los textos sin espacios). La privacidad se mira en todos.
  Los números no son sujeto.
- CEG-9. **Cuándo un texto trae vocabulario prohibido.** Sin tildes, sin distinguir mayúsculas y separando las
  mayúsculas intercaladas («rmseFondo», «sesgoEra5l»): «fondo» y «correccion» si alguna parte (cortado por todo lo que
  no es letra ni cifra) empieza así (``fondo_T``, ``rmse_fondos``, ``correccion_a``); «era5l» si aparecen «era5» y
  «l» o «land», con o sin separador (``era5land_t2m``, ``ERA5-Land``, «ERA5 Land»; no ``era5_blh``); «sin_dmc» si
  aparecen «sin» y «dmc» seguidos, con o sin separador (``sin_dmc``, «sin DMC»); y «R_», que distingue mayúsculas,
  si una parte empieza con «R_» (``R_T``, ``mse_R_p``, «R_T medio»).
- CEG-10. **Nombres propios del fondo y del residuo** (hallazgo H6; más estricto que S7, no cambia ninguna regla): en
  una métrica o un resumen tampoco caben ``T_F``, ``Td_F``, ``p_F``, ``u_F``, ``v_F``, ``amp_TF``, ``fe_*``, «E5L»
  (``z_e5l``, ``rmse_E5L``), ``r_T``, ``r_Td``, ``r_u``, ``r_v``, ``r_p``, ``rt_T``, ``rt_Td`` ni ``rbar`` (r̄), que
  distinguen mayúsculas salvo «E5L» y «rbar». La palabra «residuo» sí cabe (un resumen dice que no guarda estadísticas
  del residuo).
- CEG-11. **Procedencia: un esquema cerrado** (D3: «sólo rutas y sha256»; hallazgo H4). Un JSON (o JSONL) de
  diccionarios y listas, o un texto de líneas, en que todo texto es una ruta por alias («ERA5L/…»), una ruta relativa o
  un nombre de archivo, una huella hexadecimal (sha256 o commit, también abreviada), una fecha ISO, una versión (con
  dos puntos, «3.11.16», o «2026c»; con uno, «2026.3», sólo bajo una clave de ``CLAVES_VERSION``) o un identificador
  sin espacios; ningún texto que sea un número, ni un identificador o ruta relativa con un decimal dentro. Los **únicos
  números** son enteros (no booleanos) **no negativos** bajo una clave de ``CLAVES_ENTERAS`` (bytes, filas, líneas,
  archivos, meses, unidades, procesos, intento y errata: todos conteos): ningún decimal, en ninguna parte. Los booleanos
  y los nulos caben. Una tabla, un parquet o un NetCDF no son procedencia. Las rutas por alias pueden traer cualquier
  texto (también «era5l», que es procedencia) salvo espacios y datos privados. La lectura anterior (admitir números no
  asociados al vocabulario) pasó a la pregunta P2 al autor, y **D12 [delegada] confirmó ésta, la estricta**. Desde D12,
  un entero negativo también se rechaza (un conteo no es negativo; antes cabía).
- CEG-12. **Insumo**: permitido sin mirar el contenido. Son ``insumos/``, ``producto/residuos/`` y ``ambiental/``
  (D3), y ``estaticas/``, ``qc/estaciones/``, ``producto_01deg/``, ``salud/``, ``producto/clima_a.parquet`` y
  ``producto/tramos_homogeneos.parquet`` (D14 [delegada]). Que ningún módulo de métricas los lea, salvo ``candidatos``
  y ``producto``, lo vigila otra prueba (MC-02), no esta guarda.
- CEG-13. **Lo que se puede abrir de RELOJ** (§1.9, MC-19), por ruta léxica: la política
  (``…/config/meteorologia/reloj_dmc/v1/politica_reloj_dmc.json``) y ``artefactos_evaluados.json.gz`` a su lado, y el
  registro de C5 (``…/meteo_combinada/registro_politica_reloj.json``). Con ``k2=True``, además, la fuente de la lista
  de «coordenadas inconsistentes»: ``informe_reloj_dmc.json`` en la carpeta publicada o ``pixeles_dmc.parquet`` en
  una corrida del reloj (``…/verificacion_reloj_dmc/…``). Todo lo demás de RELOJ (informes, tablas de evidencia,
  resúmenes de la batería) da False, y una ruta que no es de RELOJ también: la función sólo responde por RELOJ.
- CEG-14. **Centinelas** (S7). La guarda reparte valores distintivos que una prueba inyecta en la mediana y el MAD del
  residuo, y los busca en las salidas tal como quedarían guardados: como texto (``repr`` en float64 y float32, y con
  6 y 9 cifras significativas), en binario float32 y float64 (los dos órdenes de bytes), y como valores numéricos de
  las tablas parquet y de las variables NetCDF (comparación exacta en float64 y float32). Descomprime gzip. No ve un
  centinela transformado (escalado a int16, promediado).
- CEG-15. **Huellas dentro de una métrica o un resumen** (hallazgo H2). Una ruta por alias no es procedencia en una
  métrica: es texto, y «ERA5L/…» trae «era5l». La única excepción es una clave ``huellas`` (o ``huellas_<algo>``),
  cuyo valor es un diccionario {ruta por alias: sha256} o {ruta por alias: {"sha256": …, "bytes": entero}} y nada más;
  así ``decision.json`` cita las entradas que usó (§8, «Cadena de huellas»). Una ruta nunca va como celda, ni como clave
  con números fuera de esa forma.
- CEG-16. **Columnas de D** (§0.4.3: «R entra como columna de entrada de D …, que no se resume ni se informa»;
  hallazgo H3). Sólo los cinco nombres de ``COLUMNAS_R_D`` (copia de ``tipos.COLUMNAS_R_D``; la prueba los compara), y
  en una métrica o un resumen sólo como nombres en una lista de textos bajo una clave ``columnas…`` o
  ``predictores…``: nunca como columna de una tabla, clave con valores ni con otro sufijo (``dmc_R_RMSE``).
- CEG-17. **La tabla de RR06** (§2.6) no tiene una exención propia: pasa porque su sujeto es «lluvia_producto» (D3).
  Con «era5l» o «fondo» en una columna o un valor se rechaza como cualquier métrica.
- CEG-18. **Documento** (quinta clase, D13 [delegada]): el addendum de M1 (``.md`` y ``.json``), ``anexo_a2.json``,
  ``pruebas_m1.txt``, el informe (``informe.md``; CEG-20) y la consola. Cita el texto, así que el vocabulario de S7
  cabe; a cambio, no lleva ningún número de datos. Se vigila con una ``ReferenciaDocumento``:
  - **la referencia** es el texto vigente, cuyo sha256 debe ser ``SHA_TEXTO_VIGENTE`` (copia de
    ``umbrales.SHA_TEXTO_VIGENTE``; ceguera no importa umbrales y una prueba las compara), más, si hace falta, las
    fuentes de las lecturas: código y documentos del paquete (``AP/scripts_modelo_1km/meteo_combinada/…``) o de la
    auditoría del producto (``APH/auditoria/<fecha>/meteo_combinada/…``), por ruta por alias y con su sha256. Nunca
    LOCAL, los datos ni otra carpeta: allí están las salidas y los datos;
  - **la huella**: el documento cita los 64 caracteres del sha256 del texto vigente (la abreviada no basta);
  - **los números**: todo número suelto y todo decimal, en cualquier parte (también dentro de un nombre o de una ruta),
    es un número del texto o de las fuentes. Se lee como allí: coma o punto decimal, miles con punto, «2,0·10¹¹»,
    «10⁻⁶», «1e-9» y «½», sin el signo. Los enteros dentro de un identificador, una ruta o un nombre de archivo
    («CEG-11», «HUMAN20261026_METEO_COMB_1», «330020.parquet»), las huellas, las fechas y las versiones de dos puntos
    («3.11.16») son nombres, no números; una sección («§5.7», «§0.4.3») se lee como sus números, que están en los
    encabezados del texto (o en los de una fuente, como el diseño). En un JSON, cada número es del texto o de las
    fuentes, salvo un entero no negativo bajo una clave de ``CLAVES_ENTERAS`` (D12), y un texto bajo una clave de
    ``CLAVES_VERSION`` puede ser una versión de un punto. Las únicas cifras ajenas a las fuentes son las dos líneas
    del resumen de unittest («Ran N tests in X.XXXs» y «OK (skipped=N)» o «FAILED (…)»), cada una sola en su línea;
  - **la forma**: texto (Markdown, texto plano, HTML) o JSON/JSONL, también en gzip; una tabla (DataFrame, CSV, TSV,
    parquet), un NetCDF o un binario no son documentos;
  - **la privacidad**, en el nombre y en todo texto; el mensaje de un rechazo cita la línea o la clave, nunca el número;
  - **la consola** se escribe por líneas: ``ConsolaDocumento.encabezado()`` es su primera línea y cita la huella;
    ``linea()`` vigila cada línea siguiente con la misma regla (y falla si no hubo encabezado).
  Consecuencias para los escritores (ola 6): lo que un documento deba cifrar con datos, sintéticos o reales (la media
  y el P95 de TF2 de S6, el costo medido, la fracción de §4.6, los mensajes de una batería con fallas), va a una
  métrica o un resumen, que pasan la guarda del vocabulario, y el documento lo cita por su ruta y su huella y copia
  sólo su veredicto («pasa», «mod23»). ``pruebas_m1.txt`` lleva una primera línea con la huella del texto y se vigila
  con los archivos de pruebas como fuentes (unittest muestra la primera línea de cada docstring). **Límite
  declarado:** un número de datos que coincide con uno del texto o de las fuentes (un entero chico, «0,8») pasa; no se
  ve un número escrito con letras, uno metido en un identificador sin separador decimal («rmse_083») ni uno con forma
  de huella, fecha o versión.
- CEG-19. **La clase la fija la ruta** (D3, D13 y D14). ``clase_de_ruta`` da la clase de cada salida que nombran el
  texto y las decisiones, por el nombre del archivo (sin «.gz») o por la carpeta (CEG-20), sin distinguir
  mayúsculas: métrica o resumen (``validacion/``, ``tendencias/``, ``decision.json``, ``resumen_qc.json`` y
  ``decision_m6.json``), insumo (CEG-12), procedencia (``avance.jsonl``, ``recibo_corrida.json``, ``sha256.json`` e
  ``intentos_*.jsonl``) y documento (``addendum_m1.json``, ``addendum_m1.md``, ``anexo_a2.json`` y ``pruebas_m1.txt``).
  El archivo manda sobre la carpeta. ``vigilar_salida`` rechaza otra clase declarada (métrica y resumen, que aplican
  la misma regla, valen una por otra); una salida sin clase fijada sigue la declarada. Las clases de P42 y P43 (D53)
  y cómo se leen las carpetas están en CEG-20.
- CEG-20. **Las clases de P42 y P43** (D53: las propuestas tal como están en ``COORDINACION_M1.md``; A22), y cómo se
  leen la ruta y las carpetas (tras la revisión independiente de la ola 4: H5, H14, H15 y H16).
  - **Archivos.** Resumen: ``resumen_m1.json``, ``costo_m1.json``, ``deriva_s6.json``, ``registro_m2a.json``,
    ``registro_m34.json``, ``m6/tf_contaminantes_*.json`` (los resúmenes de la TF de contaminantes, §8) e
    ``informe.json`` (P43: el resumen del informe, que lleva la fracción de §4.6). Insumo:
    ``politicas/politicas_meteo_v1.json``. Documento: ``informe.md`` (P43: el informe, sin números de datos, que
    cita ``informe.json`` por su ruta y su huella; CEG-18). Además, ``qc/no_normalizables.csv`` es resumen (H16:
    sólo motivos y conteos por artefacto, sin valores; §8 los cuenta en ``resumen_qc.json``), y los recibos
    archivados son procedencia (PED-6 de I17; SLD-10: al volver a sellar, ``salidas`` copia el recibo anterior, con
    sus mismos bytes, a ``recibos/recibo_<n>.json``): ``recibos/recibo_*.json`` en la raíz de la corrida y
    ``m6/recibos/recibo_*.json`` en la de M6, dos patrones porque el anclaje los separa. La carpeta ``recibos/`` no
    fija clase (``recibos/otro.json`` sigue la declarada), y ningún otro prefijo vale (``validacion/recibos/…`` es
    métrica). ``recibos/recibo_corrida.json`` calza también con ``recibo_corrida.json``, de la misma clase.
  - **El nombre relativo a la corrida.** ``clase_de_ruta`` lee el nombre relativo a la carpeta de la corrida, que es
    como lo pasa ``salidas``: lo de M6 empieza con «m6/». Si la ruta trae «meteo_combinada/v1/» (por alias o
    absoluta), se toma lo que sigue a la carpeta de la corrida (una etiqueta sellada, ``m1`` o ``m2a``) o, en la
    publicación (``AP/config/meteorologia/meteo_combinada/v1/``), lo que sigue a «v1». Un patrón de archivo sin «/»
    calza con el último componente, en cualquier carpeta; uno con «/» (``producto/clima_a.parquet``,
    ``politicas/politicas_meteo_v1.json``, ``m6/tf_contaminantes_*.json``, ``qc/no_normalizables.csv`` y los de los
    recibos archivados), sólo con el nombre entero. Las claves se comparan en minúsculas, como el nombre (H15).
  - **Carpetas, ancladas al comienzo** (H5; lectura más estricta, que va al autor como pregunta). Una carpeta de
    ``CLASE_DE_CARPETA`` fija la clase sólo al comienzo del nombre relativo a la corrida, o justo después de «m6/»,
    el único prefijo admitido; una subcarpeta más adentro no la cambia. Así ``validacion/ambiental/puntajes.parquet``
    y ``validacion/insumos/x.json`` siguen siendo métrica y ``tendencias/salud/tf.json``, resumen: una subcarpeta de
    insumo ya no saca una métrica de la guarda del vocabulario. Por lo mismo, ``salud/validacion/x.parquet`` es
    insumo, y un patrón de archivo con «/» dentro de otra carpeta (``validacion/producto/clima_a.parquet``) toma la
    clase de esa carpeta. Con la ruta por alias pero sin «meteo_combinada/v1/» (o con la subcarpeta de una etiqueta de
    ``m1`` o ``m2a``), las carpetas no fijan clase: sólo los patrones de archivo sin «/».
  - ``m6/`` es resumen. §8 pone allí ``decision_m6.json`` y los resúmenes de la TF de contaminantes (resúmenes) e
    ``intentos_m6.jsonl`` (procedencia, por su archivo); así, nada más que caiga en ``m6/`` se declara insumo ni pasa
    sin la guarda del vocabulario, salvo bajo una carpeta fijada justo después de «m6/» (``m6/ambiental/`` es
    insumo). Consecuencia: las tablas laterales y el operador con el ganador restringido (rama 3, §8) van en
    ``ambiental/`` o en ``m6/ambiental/``, nunca sueltos en ``m6/``. El patrón ``m6/tf_contaminantes_*.json`` no
    cambia ninguna clase, porque ``m6/`` ya es resumen: queda para nombrar lo de §8;
  - ``politicas/`` no fija clase: fijarla como insumo dejaría pasar sin mirar cualquier otro archivo que cayera allí.
    Sólo ese archivo, con su carpeta, es insumo (como ``producto/clima_a.parquet``); en otra carpeta sigue la
    declarada;
  - ``m1/`` y ``m2a/`` (ENT-4) tampoco: mezclan resúmenes con documentos o insumos, y cada archivo trae la suya.
  - **Sin choques.** Ningún nombre calza con dos patrones de archivo (una prueba lo vigila), así que el orden de
    búsqueda no cambia la clase; si alguna vez calzara con dos de clases distintas, ``clase_de_ruta`` lanza
    ValueError en vez de elegir uno.
  - **Lo de** ``validacion/`` (H14). Se declara métrica, también el aviso SINCA y la réplica con N, y no se publica
    en M5 (§8 publica ``decision.json``, los resúmenes y las huellas). Que la guarda acepte allí también «resumen»
    (la misma regla, CEG-19) no lo vuelve un resumen publicado. Si el aviso de §5.6 («se dice en el resumen») debe
    ir en un resumen publicado es pregunta al autor. ``informe.html`` sigue sin clase fijada.
- CEG-21. **El volumen de datos de macOS** (hallazgo H6 de la revisión de la ola 4). En macOS,
  ``/System/Volumes/Data/x`` es la misma carpeta que ``/x`` (``/Volumes``, ``/Users``, ``/private``…): el sistema las
  une con enlaces que ``lstat`` no muestra como enlaces. El registro quita ese prefijo al comienzo de la ruta, sin
  distinguir mayúsculas y también repetido, antes de comparar: en la ruta léxica, en cada componente del recorrido de
  CEG-1 (que sigue consultando la ruta física, para que un «..» se aplique donde lo aplica el sistema) y en las
  formas de las vigiladas y las permitidas (CEG-2). Así ``/System/Volumes/Data/Volumes/x`` se niega como
  ``/Volumes/x`` y nunca se consulta, también si se llega por un enlace. Lo mismo vale para lo que se puede abrir de
  RELOJ (CEG-13), que usa la ruta léxica. El registro del reloj no lo hace; la prueba de paridad compara sólo
  carpetas temporales, donde el prefijo no aparece, así que la paridad se mantiene.
- CEG-22. **Crear un enlace, y los registros anidados** (PED-4 de I22, ola 6: la batería corre la suite dentro de su
  propio registro en bloqueo sobre /Volumes y los repositorios, y debe dar 0 accesos). Se cuenta sólo lo que es un
  acceso:
  - **crear un enlace** (``os.symlink``, ``Path.symlink_to``) escribe sólo la ruta del enlace: el registro mira ese
    lugar, léxico y recorrido (sin seguir su último componente), y no su destino, que crear el enlace no lee ni
    escribe. Seguirlo después cuenta como siempre (CEG-1). ``os.link`` mira sus dos rutas: un enlace duro toca el
    archivo de origen;
  - **cada registro juzga por dónde lo toca la ruta**: la ruta léxica si cae bajo una de sus vigiladas; si no, la del
    recorrido de CEG-1, que ya no se detiene en la primera vigilada de cualquier registro: pasa por ella sin
    consultarla (léxico, como bajo /Volumes) y anota cada posición bajo una vigilada. A cada registro le toca la ruta
    final si cae bajo las suyas o, si no, la primera de esas posiciones que cae. Antes, una ruta que pasa por
    «/Volumes/..» quedaba sólo en el registro exterior que vigila /Volumes (el recorrido se detenía allí), aunque el
    interior la habría negado un paso después: ahora la niega el interior y el exterior la anota en
    ``negados_dentro``, no en ``accesos`` (VER-14 del reloj). Si el interior sólo anota, el acceso queda en los dos y lo
    niega el exterior; un acceso que el interior no vigila queda sólo en el exterior. ``por_enlace`` reúne lo que un
    registro vio por el recorrido y no por la ruta léxica;
  - **cada registro envuelve lo que encuentra**: al entrar, si ``os.stat``, ``os.lstat`` u ``os.access`` no es un
    envoltorio de ``ceguera`` (porque no hay otro registro activo, o porque una prueba lo tapó con su espía bajo el
    registro de la batería), lo envuelve, y al salir deja lo que había. El recorrido consulta la función que hay
    debajo de todo envoltorio que declara ``__wrapped__`` (los de ``ceguera`` y los del registro del reloj): la del
    sistema, o el espía de una prueba, que no lo declara. Así otro registro no cuenta el recorrido como acceso. Antes
    sólo envolvía el primer registro, y bajo la batería el espía de una prueba dejaba sus ``os.lstat`` fuera de todo
    registro. Mientras un envoltorio llama a lo que envuelve, los de más abajo no vuelven a juzgar: un espía que llama
    al envoltorio de la batería no hace contar dos veces la misma llamada. **Límite declarado:** mientras una prueba
    tapa una de esas funciones sin entrar a un registro, sus llamadas directas no pasan por el de afuera (el gancho de
    auditoría ve todo lo demás);
  - **límite declarado (VER-18):** un evento con ``dir_fd`` (``shutil.rmtree`` borra así) trae un nombre relativo a
    una carpeta abierta, que el gancho no informa, y el registro lo junta con el directorio actual; por eso la batería
    corre con el directorio en la carpeta temporal del sistema. Abrir esa carpeta ya pasó por el registro.
  Diferencias con el registro del reloj: éste mira los dos primeros argumentos de cada evento, también el destino de
  ``os.symlink``, y juzga sólo la ruta normalizada (H7). La prueba de paridad no crea enlaces dentro del registro ni
  usa rutas que pasen por la vigilada de otro registro, así que sigue igual; una comprobación aparte avisa si el reloj
  deja de contar el destino. Además, el del reloj, al salir, repone el ``os.stat`` y el ``os.lstat`` de cuando se
  importó, y borra así los envoltorios de un registro exterior (el de la batería): las pruebas de aquí que lo usan
  dejan lo que había.
Depende de: entorno.
"""
from __future__ import annotations

import csv
import fnmatch
import gzip
import io
import json
import math
import os
import re
import socket
import stat as _stat
import struct
import subprocess
import sys
import threading
import unicodedata
from collections import deque
from dataclasses import fields
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator, Mapping

from meteo_combinada import entorno

VOCABULARIO_PROHIBIDO = ("fondo", "era5l", "sin_dmc", "correccion", "R_")
CLASES_SALIDA = ("metrica", "resumen", "insumo", "procedencia", "documento")     # D3 (MC-02) y D13 del autor
CLASES_CON_VOCABULARIO = ("metrica", "resumen")

# Alias del texto (los campos de entorno.Rutas, en mayúsculas): «ERA5L/…» es una ruta por alias.
ALIAS = tuple(f.name.upper() for f in fields(entorno.Rutas))


class SalidaProhibida(ValueError):
    """Una salida trae vocabulario prohibido, valores donde sólo cabe procedencia, datos privados o un centinela."""


class RedProhibida(PermissionError):
    """Intento de conexión de red dentro de ``SinRed``."""


# =====================================================================================================
# Estado común de los ganchos (uno solo, instalado una vez, inerte sin contextos activos)
# =====================================================================================================
# Evento → índices de sus argumentos que son rutas (CEG-4).
_EVENTOS_DE_RUTA: Mapping[str, tuple[int, ...]] = {
    "open": (0,), "os.listdir": (0,), "os.scandir": (0,), "os.chdir": (0,), "os.mkdir": (0,),
    "os.rename": (0, 1), "os.remove": (0,), "os.rmdir": (0,), "os.symlink": (1,), "os.link": (0, 1),   # CEG-22
    "os.truncate": (0,), "os.utime": (0,), "os.chmod": (0,), "os.chown": (0,), "os.chflags": (0,),
    "os.listxattr": (0,), "os.getxattr": (0,), "os.setxattr": (0,), "os.removexattr": (0,),
    "glob.glob": (0,), "glob.glob/2": (0, 2), "shutil.copyfile": (0, 1), "shutil.copytree": (0, 1),
    "shutil.rmtree": (0,), "shutil.move": (0, 1), "shutil.unpack_archive": (0, 1),
}
# Eventos que sólo leen (CEG-3); en las copias, el origen (índice 0) se lee y el destino se escribe.
_EVENTOS_DE_LECTURA = frozenset({"os.listdir", "os.scandir", "os.chdir", "os.listxattr", "os.getxattr", "glob.glob",
                                 "glob.glob/2", "os.stat", "os.lstat", "os.access"})
_COPIAS = frozenset({"shutil.copyfile", "shutil.copytree"})
# Eventos cuyo último componente no se sigue (CEG-1).
_SIN_SEGUIR_FINAL = frozenset({"os.lstat", "os.remove", "os.rmdir", "os.rename", "os.link", "os.symlink",
                               "shutil.rmtree", "shutil.move"})
_ENVUELTAS = ("stat", "lstat", "access")
_FLAGS_ESCRITURA = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
_MODO_ESCRITURA = re.compile(r"[wax+]")
_MAX_ENLACES = 40               # no-umbral: tope de enlaces seguidos al recorrer (el de POSIX, SYMLOOP_MAX)
_VOLUMEN_DE_DATOS = ("system", "volumes", "data")     # macOS: /System/Volumes/Data/x es /x (CEG-21)

_ESTADO: dict[str, Any] = {"instalado": False, "registros": [], "redes": []}
_MARCA_ENVOLTORIO = "_envoltorio_de_ceguera"
_CANDADO = threading.RLock()
_LOCAL = threading.local()


def _instalar_gancho() -> None:
    if not _ESTADO["instalado"]:
        sys.addaudithook(_gancho)               # no se puede quitar: queda inerte sin contextos activos
        _ESTADO["instalado"] = True


def _gancho(evento: str, args: tuple) -> None:
    if _ESTADO["registros"] and evento in _EVENTOS_DE_RUTA:
        _evento_de_ruta(evento, args)
    if _ESTADO["redes"] and evento in _EVENTOS_DE_RED:
        _evento_de_red(evento, args)


# =====================================================================================================
# Registro de accesos
# =====================================================================================================
def _sin_volumen_de_datos(texto: str) -> str:
    """«/System/Volumes/Data/x» → «/x», sin distinguir mayúsculas y también repetido (macOS; CEG-21)."""
    while texto.startswith(os.sep):
        partes = [p for p in texto.split(os.sep) if p]
        if tuple(p.casefold() for p in partes[:len(_VOLUMEN_DE_DATOS)]) != _VOLUMEN_DE_DATOS:
            break
        texto = os.sep + os.sep.join(partes[len(_VOLUMEN_DE_DATOS):])
    return texto


def _texto_lexico(ruta) -> str | None:
    """Ruta absoluta normalizada y sin el prefijo del volumen de datos (CEG-21), sin tocar el disco; None si no es una
    ruta (un descriptor, por ejemplo)."""
    if not isinstance(ruta, (str, bytes, os.PathLike)):
        return None
    try:
        return _sin_volumen_de_datos(os.path.normpath(os.path.abspath(os.fsdecode(os.fspath(ruta)))))
    except (TypeError, ValueError):
        return None


def _texto_crudo(ruta) -> str | None:
    """Ruta absoluta SIN normalizar sus «..»: el sistema sigue un enlace antes de aplicar el «..» siguiente (CEG-1)."""
    if not isinstance(ruta, (str, bytes, os.PathLike)):
        return None
    try:
        texto = os.fsdecode(os.fspath(ruta))
    except (TypeError, ValueError):
        return None
    return texto if os.path.isabs(texto) else os.path.join(os.getcwd(), texto)


def _bajo(clave: str, prefijos: Iterable[str]) -> bool:
    """True si ``clave`` (ya en minúsculas) es uno de los prefijos o cuelga de él, componente a componente."""
    return any(clave == p or clave.startswith(p.rstrip(os.sep) + os.sep) for p in prefijos)


def _en_volumes(texto: str) -> bool:
    partes = PurePosixPath(texto).parts
    return len(partes) >= 2 and partes[0] == "/" and partes[1].casefold() == "volumes"


def _original(nombre: str):
    """La función que hay debajo de todo envoltorio que declara ``__wrapped__`` (los de ``ceguera`` y los del registro
    del reloj): la del sistema, o la que puso quien llama sin declararlo, como el espía de una prueba (CEG-22). Así el
    recorrido no se cuenta como acceso en otro registro."""
    funcion, vistas = getattr(os, nombre), set()
    while id(funcion) not in vistas:
        vistas.add(id(funcion))
        debajo = getattr(funcion, "__wrapped__", None)
        if not callable(debajo):
            break
        funcion = debajo
    return funcion


def _es_envoltorio(funcion) -> bool:
    """True sólo para un envoltorio de ``ceguera`` (un ``Mock`` responde a cualquier atributo: se exige ``True``)."""
    return getattr(funcion, _MARCA_ENVOLTORIO, None) is True


def _recorrer(texto: str, vigiladas: tuple[str, ...], *, seguir_final: bool) -> tuple[str, list[str]]:
    """Recorre una ruta absoluta como el sistema (CEG-1): sigue sus enlaces y aplica cada «..» sobre la ruta física,
    sin consultar nunca un componente bajo ``vigiladas`` ni bajo /Volumes: allí sigue léxico, y vuelve a consultar si
    un «..» lo saca (CEG-22). Tras un componente que no existe, el resto también es léxico.

    Devuelve (ruta, pasos): la ruta a que llega y las posiciones bajo ``vigiladas`` por las que pasa, en orden. Se
    consulta la ruta física (un «..» se aplica donde lo aplica el sistema), pero se compara y se devuelve sin el prefijo
    del volumen de datos (CEG-21).
    """
    lstat, saltos = _original("lstat"), 0
    pendientes = deque(p for p in texto.split(os.sep) if p)
    actual, pasos, lexico = os.sep, [], False
    while pendientes:
        parte = pendientes.popleft()
        if parte == ".":
            continue
        candidato = (os.path.dirname(actual) or os.sep) if parte == ".." else os.path.join(actual, parte)
        visto = _sin_volumen_de_datos(candidato)
        if _bajo(visto.casefold(), vigiladas):     # pasa por una vigilada: se anota y no se consulta
            pasos.append(visto)
            actual = candidato
            continue
        if parte == ".." or lexico or _en_volumes(visto) or (not pendientes and not seguir_final):
            actual = candidato              # bajo /Volumes nunca se consulta: el recorrido sigue léxico
            continue
        try:
            st = lstat(candidato)
        except OSError:                     # no existe: el sistema se detiene aquí; el resto, léxico
            actual, lexico = candidato, True
            continue
        if _stat.S_ISLNK(st.st_mode):
            saltos += 1
            if saltos > _MAX_ENLACES:       # el sistema da ELOOP
                return _sin_volumen_de_datos(os.path.normpath(os.path.join(visto, *pendientes))), pasos
            destino = os.readlink(candidato)
            if os.path.isabs(destino):
                actual = os.sep
            pendientes.extendleft(reversed([p for p in destino.split(os.sep) if p]))
            continue
        actual = candidato
    return _sin_volumen_de_datos(actual), pasos


def _recorrida_sin_registro(texto: str) -> str:
    """La ruta recorrida con la regla de CEG-1, sin pasar por los registros activos y sin consultar /Volumes (CEG-2)."""
    previo = getattr(_LOCAL, "dentro", False)
    _LOCAL.dentro = True
    try:
        return _recorrer(texto, (), seguir_final=True)[0]
    finally:
        _LOCAL.dentro = previo


def _formas(rutas: Iterable) -> tuple[str, ...]:
    """Forma léxica y forma recorrida de cada ruta, en minúsculas (CEG-2)."""
    salida: list[str] = []
    for r in rutas:
        lexica, cruda = _texto_lexico(r), _texto_crudo(r)
        if lexica is None or cruda is None:
            raise TypeError(f"no es una ruta: {r!r}")
        salida.append(lexica.casefold())
        salida.append(_recorrida_sin_registro(cruda).casefold())
    return tuple(dict.fromkeys(salida))


def _es_escritura_open(args: tuple) -> bool:
    modo = args[1] if len(args) > 1 else None
    banderas = args[2] if len(args) > 2 else None
    if isinstance(banderas, int) and not isinstance(banderas, bool):
        return bool(banderas & _FLAGS_ESCRITURA)
    return isinstance(modo, str) and bool(_MODO_ESCRITURA.search(modo))


def _evento_de_ruta(evento: str, args: tuple) -> None:
    for indice in _EVENTOS_DE_RUTA[evento]:
        if indice >= len(args):
            continue
        if evento == "open":
            lectura = not _es_escritura_open(args)
        elif evento in _COPIAS:
            lectura = indice == 0
        else:
            lectura = evento in _EVENTOS_DE_LECTURA
        _ver(evento, args[indice], lectura=lectura, seguir_final=evento not in _SIN_SEGUIR_FINAL)


def _objetivo(registro: "RegistroAccesos", final: str, pasos: Iterable[str]) -> str | None:
    """Dónde toca la ruta a un registro (CEG-22): la ruta final si cae bajo una de sus vigiladas o, si no, la primera
    posición bajo una de ellas por la que pasa; None si no lo toca."""
    if registro._vigila(final.casefold()):
        return final
    return next((p for p in pasos if registro._vigila(p.casefold())), None)


def _ver(evento: str, ruta, *, lectura: bool, seguir_final: bool = True) -> None:
    """Pasa un acceso por los registros activos, del más interior al más exterior (VER-14 del reloj): cada uno lo
    juzga por dónde lo toca la ruta (CEG-22)."""
    if getattr(_LOCAL, "dentro", False):
        return
    activos = list(_ESTADO["registros"])
    if not activos:
        return
    lexica, cruda = _texto_lexico(ruta), _texto_crudo(ruta)
    if lexica is None or cruda is None:
        return
    objetivos = {id(r): (lexica if r._vigila(lexica.casefold()) else None) for r in activos}
    por_enlace: set[int] = set()
    faltan = [r for r in activos if objetivos[id(r)] is None]
    if faltan:                              # los que la ruta léxica no toca: el camino que sigue el sistema (CEG-1)
        todas = tuple(dict.fromkeys(v for r in activos for v in r._vigiladas))
        _LOCAL.dentro = True
        try:
            final, pasos = _recorrer(cruda, todas, seguir_final=seguir_final)
        except OSError:
            final, pasos = lexica, []
        finally:
            _LOCAL.dentro = False
        for registro in faltan:
            objetivos[id(registro)] = _objetivo(registro, final, pasos)
            if objetivos[id(registro)] is not None:
                por_enlace.add(id(registro))
    negado = False
    for registro in reversed(activos):
        objetivo = objetivos[id(registro)]
        if objetivo is None:
            continue
        clave = objetivo.casefold()
        if negado:
            registro.negados_dentro.append((evento, objetivo))
            continue
        if lectura and registro._permite(clave):
            registro.lecturas_permitidas.append((evento, objetivo))
            continue
        registro.accesos.append((evento, objetivo))
        if id(registro) in por_enlace:
            registro.por_enlace.append((evento, lexica, objetivo))
        negado = registro.bloquear
    if negado:
        raise PermissionError(f"acceso prohibido bajo una carpeta vigilada ({evento})")


def _envoltorio(nombre: str, original):
    evento = f"os.{nombre}"

    def envoltorio(path, *a, **k):
        previo = getattr(_LOCAL, "en_envoltorio", False)
        if _ESTADO["registros"] and not previo and isinstance(path, (str, bytes, os.PathLike)):
            seguir = nombre != "lstat" and k.get("follow_symlinks", True)
            _ver(evento, path, lectura=True, seguir_final=bool(seguir))
        _LOCAL.en_envoltorio = True         # un espía entre dos envoltorios no hace contar dos veces (CEG-22)
        try:
            return original(path, *a, **k)
        finally:
            _LOCAL.en_envoltorio = previo

    envoltorio.__wrapped__ = original
    envoltorio.__name__ = nombre
    setattr(envoltorio, _MARCA_ENVOLTORIO, True)
    return envoltorio


def anunciar_acceso(ruta, *, evento: str = "lectura", lectura: bool = True) -> None:
    """Pasa una ruta por los registros activos, para lectores en C que no pasan por el gancho (CEG-5)."""
    _ver(evento, ruta, lectura=lectura)


class RegistroAccesos:
    """Registro de «open» y listados bajo unas carpetas; con ``bloquear``, lanza PermissionError antes del acceso.

    Mira la ruta léxica antes de resolverla (lección de los 7 accesos de C1 del reloj) y después el camino que sigue el
    sistema (CEG-1). ``permitidas``: rutas que se pueden leer dentro de las vigiladas (S14 y el costo, MC-31; CEG-3).
    - ``accesos``: los accesos que vio y no negó antes un registro más interior (en bloqueo, todos quedan negados);
    - ``por_enlace``: los de ``accesos`` que llegaron por el recorrido y no por la ruta léxica (un enlace, o un «..»
      que pasa por la vigilada), con su ruta léxica y la vigilada (CEG-22);
    - ``negados_dentro``: los que negó un registro más interior (no llegaron al disco);
    - ``lecturas_permitidas``: las lecturas bajo ``permitidas``.
    """

    def __init__(self, vigiladas, *, bloquear: bool = False, permitidas=()):
        if isinstance(vigiladas, (str, bytes, os.PathLike)):
            vigiladas = (vigiladas,)
        if isinstance(permitidas, (str, bytes, os.PathLike)):
            permitidas = (permitidas,)
        self._vigiladas = _formas(vigiladas)
        self._permitidas = _formas(permitidas)
        self.vigiladas = tuple(vigiladas)
        self.permitidas = tuple(permitidas)
        self.bloquear = bool(bloquear)
        self.accesos: list[tuple[str, str]] = []
        self.por_enlace: list[tuple[str, str, str]] = []
        self.negados_dentro: list[tuple[str, str]] = []
        self.lecturas_permitidas: list[tuple[str, str]] = []
        self._reemplazadas: dict[str, Any] = {}

    def _vigila(self, clave: str) -> bool:
        return _bajo(clave, self._vigiladas)

    def _permite(self, clave: str) -> bool:
        return _bajo(clave, self._permitidas)

    def __enter__(self) -> "RegistroAccesos":
        with _CANDADO:
            _instalar_gancho()
            self._reemplazadas = {}
            for n in _ENVUELTAS:                # sin envoltorio, o lo tapó otro (el espía de una prueba): CEG-22
                actual = getattr(os, n)
                if not _es_envoltorio(actual):
                    self._reemplazadas[n] = actual
                    setattr(os, n, _envoltorio(n, actual))
            _ESTADO["registros"].append(self)
        return self

    def __exit__(self, *exc) -> None:
        with _CANDADO:
            _ESTADO["registros"].remove(self)
            for n, f in self._reemplazadas.items():
                setattr(os, n, f)
            self._reemplazadas = {}


# =====================================================================================================
# Red
# =====================================================================================================
_EVENTOS_DE_RED = frozenset({
    "socket.connect", "socket.sendto", "socket.sendmsg", "socket.bind", "socket.getaddrinfo",
    "socket.gethostbyname", "socket.gethostbyaddr", "socket.getnameinfo",
    "urllib.Request", "http.client.connect", "ftplib.connect", "smtplib.connect", "poplib.connect", "imaplib.open",
    "nntplib.connect", "webbrowser.open"})
_DE_SOCKET = frozenset({"socket.connect", "socket.sendto", "socket.sendmsg", "socket.bind"})


def _evento_de_red(evento: str, args: tuple) -> None:
    if evento in _DE_SOCKET:
        familia = getattr(args[0], "family", None) if args else None
        if familia == getattr(socket, "AF_UNIX", object()):
            return
        destino = args[1] if len(args) > 1 else None
    else:
        destino = args[0] if args else None
    texto = str(destino)
    for red in list(_ESTADO["redes"]):
        red.intentos.append((evento, texto))
    raise RedProhibida(f"red prohibida ({evento})")


class SinRed:
    """Contexto: toda conexión de red lanza ``RedProhibida`` antes de ocurrir (CEG-6). ``intentos`` los anota."""

    def __init__(self):
        self.intentos: list[tuple[str, str]] = []

    def __enter__(self) -> "SinRed":
        with _CANDADO:
            _instalar_gancho()
            _ESTADO["redes"].append(self)
        return self

    def __exit__(self, *exc) -> None:
        with _CANDADO:
            _ESTADO["redes"].remove(self)


# =====================================================================================================
# Procesos
# =====================================================================================================
_PS = ("ps", "-A", "-o", "pid=", "-o", "ppid=", "-o", "pgid=", "-o", "stat=")
_NUMERICAS_PS = len(("pid", "ppid", "pgid"))     # las columnas numéricas de _PS, antes de «stat»
_ZOMBI = "Z"
_ESPERA_PS_S = 60


def procesos_hijos_vivos(*, grupos: Iterable[int] = ()) -> list[int]:
    """PID vivos, ordenados, de los descendientes de este proceso y de los procesos de ``grupos`` (CEG-7)."""
    vigilados = {int(g) for g in grupos}
    yo = os.getpid()
    proceso = subprocess.Popen(_PS, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    salida, _ = proceso.communicate(timeout=_ESPERA_PS_S)
    if proceso.returncode != 0:
        raise RuntimeError("ps no pudo listar los procesos")
    hijos: dict[int, list[int]] = {}
    vivos: set[int] = set()
    raices = [yo]
    for linea in salida.splitlines():
        partes = linea.split()
        numericas, resto = partes[:_NUMERICAS_PS], partes[_NUMERICAS_PS:]
        if len(numericas) < _NUMERICAS_PS or not all(p.isdigit() for p in numericas):
            continue
        pid, ppid, pgid = (int(p) for p in numericas)
        hijos.setdefault(ppid, []).append(pid)
        estado = resto[0] if resto else ""
        if not estado.startswith(_ZOMBI):
            vivos.add(pid)
        if pgid in vigilados:
            raices.append(pid)
    encontrados, pendientes = set(), list(raices)
    while pendientes:
        actual = pendientes.pop()
        for h in hijos.get(actual, []):
            if h not in encontrados:
                encontrados.add(h)
                pendientes.append(h)
    encontrados.update(raices[1:])
    encontrados.discard(proceso.pid)
    encontrados.discard(yo)
    return sorted(encontrados & vivos)


# =====================================================================================================
# Vocabulario de las salidas (S7, D3)
# =====================================================================================================
# §0.4.3: las cinco columnas de entrada de D (copia de tipos.COLUMNAS_R_D: ceguera no importa tipos; CEG-16).
COLUMNAS_R_D = ("dmc_R_T", "dmc_R_Td", "dmc_R_u", "dmc_R_v", "dmc_R_p")
PREFIJOS_LISTA_COLUMNAS = ("columnas", "predictores")         # CEG-16
CLAVE_HUELLAS = "huellas"                                      # CEG-15
CLAVES_DE_HUELLA = ("sha256", "bytes")
# CEG-11: los únicos números de la procedencia, y sólo enteros; y las claves que admiten una versión de un punto.
CLAVES_ENTERAS = ("bytes", "filas", "lineas", "archivos", "meses", "unidades", "procesos", "intento", "errata")
CLAVES_VERSION = ("version", "python", "pandas", "numpy", "pyarrow", "netCDF4", "scipy", "pyproj", "rasterio",
                  "threadpoolctl", "tzdata", "iana")

_ALIAS_RUTA = re.compile(r"(?:%s)/[^\s]*" % "|".join(re.escape(a) for a in sorted(ALIAS, key=len, reverse=True)))
_SHA256 = re.compile(r"[0-9a-f]{64}")
_HUELLA = re.compile(r"(?:sha256[:=])?(?=[0-9a-f]*[a-f])[0-9a-f]{7,64}…?")   # no-umbral: largo de una huella
_R_ = re.compile(r"(?<![A-Za-z0-9])R_")
_SIN_DMC = re.compile(r"(?<![0-9a-z])sin[\s_\-.]*dmc(?![0-9a-z])")
_ERA5L = re.compile(r"(?<![0-9a-z])era5[\s_\-.]*l(?:and)?(?![a-z])")
_PARTES = re.compile(r"[^0-9a-z]+")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
# CEG-10: nombres propios del fondo y del residuo en el código.
_NOMBRES_PROPIOS = (
    ("T_F", re.compile(r"(?<![A-Za-z0-9])(?:T|Td|p|u|v)_F(?![A-Za-z0-9])")),
    ("amp_TF", re.compile(r"(?<![A-Za-z0-9])amp_TF(?![A-Za-z0-9])")),
    ("fe_", re.compile(r"(?<![A-Za-z0-9])fe_[A-Za-z0-9]")),
    ("E5L", re.compile(r"(?i)(?<![a-z0-9])e5l(?![a-z])")),
    ("r_", re.compile(r"(?<![A-Za-z0-9])(?:r|rt)_(?:T|Td|u|v|p)(?![A-Za-z0-9])")),
    ("rbar", re.compile(r"(?i)(?<![a-z0-9])rbar(?![a-z0-9])")),
)
_BORDES = "\"'`()[]{}<>,;:«»*"
_EXTENSIONES = (".gz", ".parquet", ".jsonl", ".json", ".csv", ".tsv", ".txt", ".md", ".nc", ".html")
_GZ = ".gz"
_MAGIA_GZIP = b"\x1f\x8b"
_MAGIA_PARQUET = b"PAR1"
_MAGIAS_NETCDF = (b"CDF", b"\x89HDF\r\n\x1a\n")      # NetCDF clásico y NetCDF-4 (HDF5)
_MUESTRA = 80                  # no-umbral: caracteres de un texto citados en un mensaje
_CITADOS = 5                   # no-umbral: hallazgos citados en un mensaje
# CEG-11: formas de los textos de la procedencia.
_FORMA_FECHA = re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?(?:Z|[+-]\d{2}:?\d{2})?")
_FORMA_VERSION = re.compile(r"v?\d+(?:\.\d+){2,}[a-z0-9]*|\d{4}[a-z]")
_FORMA_VERSION_CORTA = re.compile(r"v?\d+(?:\.\d+)+[a-z0-9]*")
_FORMA_IDENTIFICADOR = re.compile(r"[A-Za-z_][\w.\-+]*")
_FORMA_RUTA = re.compile(r"~?[\w.\-+]*(?:/[\w.\-+]*)+|[\w.\-+]+\.(?:json|jsonl|parquet|csv|tsv|nc|gz|txt|md|py|zip|"
                         r"hgt|tif|tiff|html|log)")
_DECIMAL = re.compile(r"\d+[.,]\d+")
_NUMERO = re.compile(r"[−+-]?\d+(?:[.,]\d+)?(?:[eE][−+-]?\d+)?")


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def es_ruta_por_alias(texto: str) -> bool:
    """«ERA5L/…», «LOCAL/…»: un alias del texto seguido de «/» (sin espacios)."""
    return _ALIAS_RUTA.fullmatch(texto) is not None


def es_procedencia(texto: str) -> bool:
    """Una ruta por alias o una huella hexadecimal (sha256 o commit, también abreviada)."""
    t = texto.strip(_BORDES)
    return bool(t) and (es_ruta_por_alias(t) or _HUELLA.fullmatch(t) is not None)


def vocabulario_en(texto: str) -> str | None:
    """La palabra o el nombre propio prohibido que trae un texto de una métrica o un resumen, o None (CEG-9, CEG-10)."""
    if _R_.search(texto):
        return "R_"
    for nombre, patron in _NOMBRES_PROPIOS:
        if patron.search(texto):
            return nombre
    normal = _sin_tildes(_CAMEL.sub(" ", texto)).casefold()
    partes = [p for p in _PARTES.split(normal) if p]
    if any(p.startswith("fondo") for p in partes):
        return "fondo"
    if any(p.startswith("correccion") for p in partes):
        return "correccion"
    if _ERA5L.search(normal):
        return "era5l"
    if _SIN_DMC.search(normal):
        return "sin_dmc"
    return None


def _componentes_del_nombre(nombre: str) -> list[str]:
    casa = str(Path.home())
    if nombre.startswith(casa):
        nombre = nombre[len(casa):]
    salida = []
    for parte in PurePosixPath(nombre.replace(os.sep, "/")).parts:
        if parte in ("/", ".", ".."):
            continue
        while True:
            menor = parte.casefold()
            ext = next((e for e in _EXTENSIONES if menor.endswith(e) and len(parte) > len(e)), None)
            if ext is None:
                break
            parte = parte[:-len(ext)]
        salida.append(parte)
    return salida


def _es_tabla(x) -> bool:
    return hasattr(x, "columns") and hasattr(x, "dtypes") and hasattr(x, "index")


def _sin_gz(nombre: str) -> str:
    return nombre[:-len(_GZ)] if nombre.casefold().endswith(_GZ) else nombre


def _decodificar(nombre: str, datos: bytes) -> tuple[str, Any]:
    """(tipo, contenido) de unos bytes: «gzip», «parquet», «netcdf» o «texto»."""
    if datos.startswith(_MAGIA_GZIP):
        return "gzip", gzip.decompress(datos)
    if datos.startswith(_MAGIA_PARQUET):
        return "parquet", datos
    if datos.startswith(_MAGIAS_NETCDF):
        return "netcdf", datos
    try:
        return "texto", datos.decode("utf-8")
    except UnicodeDecodeError as e:
        raise SalidaProhibida(f"{nombre}: contenido binario que no se puede verificar") from e


def _texto_a_objeto(nombre: str, texto: str) -> tuple[str, Any]:
    """(«json», objeto), («jsonl», lista), («csv», filas) o («texto», texto)."""
    menor = nombre.casefold()
    if menor.endswith(".jsonl"):
        try:
            return "jsonl", [json.loads(l) for l in texto.splitlines() if l.strip()]
        except ValueError:
            return "texto", texto
    if menor.endswith(".json") or texto.lstrip()[:1] in ("{", "["):
        try:
            return "json", json.loads(texto)
        except ValueError:
            return "texto", texto
    if menor.endswith((".csv", ".tsv")):
        delimitador = "\t" if menor.endswith(".tsv") else ","
        return "csv", list(csv.reader(io.StringIO(texto), delimiter=delimitador))
    return "texto", texto


def _parquet(datos: bytes):
    """(tabla de pyarrow, DataFrame); pyarrow y pandas se cargan sólo al llamarse."""
    import pyarrow.parquet as pq
    tabla = pq.read_table(io.BytesIO(datos))
    return tabla, tabla.to_pandas()


def _texto_de(valor) -> list[str]:
    """Los textos de un valor de atributo o de metadato (texto, bytes o arreglo de textos)."""
    if isinstance(valor, bytes):
        return [valor.decode("utf-8", "replace")]
    if isinstance(valor, str):
        return [valor]
    if hasattr(valor, "dtype") and getattr(valor.dtype, "kind", "") in "OUS":
        return [x.decode("utf-8", "replace") if isinstance(x, bytes) else str(x) for x in valor.ravel().tolist()]
    return []


# --- métrica y resumen (CEG-8 a CEG-10, CEG-15 a CEG-17) --------------------------------------------------------
def _validar_huellas(valor, clave: str) -> None:
    """CEG-15: {ruta por alias: sha256} o {ruta por alias: {"sha256": …, "bytes": entero}}, y nada más."""
    if not isinstance(valor, Mapping) or not valor:
        raise SalidaProhibida(f"«{clave}» debe ser un diccionario de rutas por alias y sus huellas")
    for ruta, huella in valor.items():
        ruta = str(ruta)
        if not entorno.sin_datos_privados(ruta):
            raise SalidaProhibida(f"«{clave}» trae una ruta de la carpeta de usuario o una arroba")
        if not es_ruta_por_alias(ruta):
            raise SalidaProhibida(f"en «{clave}» sólo van rutas por alias: {ruta[:_MUESTRA]}")
        if isinstance(huella, Mapping):
            if set(huella) - set(CLAVES_DE_HUELLA) or "sha256" not in huella:
                raise SalidaProhibida(f"en «{clave}», la huella de {ruta[:_MUESTRA]} sólo lleva sha256 y bytes")
            bytes_ = huella.get("bytes", 0)
            if isinstance(bytes_, bool) or not isinstance(bytes_, int) or bytes_ < 0:
                raise SalidaProhibida(f"en «{clave}», «bytes» de {ruta[:_MUESTRA]} es un entero no negativo")
            huella = huella["sha256"]
        if not isinstance(huella, str) or _SHA256.fullmatch(huella) is None:
            raise SalidaProhibida(f"en «{clave}», la huella de {ruta[:_MUESTRA]} no es un sha256")


def _es_clave_huellas(clave: str) -> bool:
    return clave == CLAVE_HUELLAS or clave.startswith(CLAVE_HUELLAS + "_")


def _textos_de_objeto(obj, donde: str = "valor") -> Iterator[tuple[str, str]]:
    """(dónde, texto) de todo texto de un objeto: claves y valores (CEG-8)."""
    if obj is None or isinstance(obj, (bool, int, float, complex)):
        return
    if isinstance(obj, str):
        yield donde, obj
        return
    if isinstance(obj, bytes):
        yield donde, obj.decode("utf-8", "replace")
        return
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            k = str(k)
            if _es_clave_huellas(k):
                _validar_huellas(v, k)
                continue
            yield "clave", k
            if (k.startswith(PREFIJOS_LISTA_COLUMNAS) and isinstance(v, (list, tuple))
                    and all(isinstance(x, str) for x in v)):
                yield from ((f"columna listada en {k}", x) for x in v if x not in COLUMNAS_R_D)
                continue
            yield from _textos_de_objeto(v, f"valor de {k}")
        return
    if _es_tabla(obj):
        yield from _textos_de_tabla(obj)
        return
    if hasattr(obj, "dtype") and hasattr(obj, "ravel"):        # arreglo de numpy
        if getattr(obj.dtype, "kind", "") in "OUS":
            for v in obj.ravel().tolist():
                yield from _textos_de_objeto(v, donde)
        return
    if isinstance(obj, (list, tuple, set, frozenset)):
        for v in obj:
            yield from _textos_de_objeto(v, donde)
        return
    raise SalidaProhibida(f"no se puede verificar un contenido de tipo {type(obj).__name__}")


def _textos_de_tabla(df) -> Iterator[tuple[str, str]]:
    """Columnas, nombres de índice, todas las celdas de texto y ``attrs`` (CEG-8)."""
    for c in df.columns:
        yield "columna", str(c)
    for n in getattr(df.index, "names", []) or []:
        if n is not None:
            yield "índice", str(n)
    for c in df.columns:
        tipo = str(df[c].dtype)
        if tipo in ("object", "category") or tipo.startswith("string"):
            for v in df[c].dropna().unique():
                if isinstance(v, (str, bytes, Mapping, list, tuple)):
                    yield from _textos_de_objeto(v, f"celda de {c}")
    attrs = getattr(df, "attrs", None)
    if attrs:
        yield from _textos_de_objeto(dict(attrs), "attrs")


def _textos_de_parquet(datos: bytes) -> Iterator[tuple[str, str]]:
    """Tabla, más las claves y los valores de los metadatos del esquema (hallazgo H5)."""
    tabla, df = _parquet(datos)
    for k, v in (tabla.schema.metadata or {}).items():
        clave = k.decode("utf-8", "replace")
        yield "metadato", clave
        valor = v.decode("utf-8", "replace")
        try:
            objeto = json.loads(valor)
        except ValueError:
            yield f"metadato {clave}", valor
        else:
            yield from _textos_de_objeto(objeto, f"metadato {clave}")
    yield from _textos_de_tabla(df)


def _textos_de_grupo(g, ruta: str = "") -> Iterator[tuple[str, str]]:
    for nombre in g.dimensions:
        yield "dimensión", nombre
    for a in g.ncattrs():
        yield "atributo", a
        yield from ((f"atributo {a}{ruta}", t) for t in _texto_de(g.getncattr(a)))
    for nombre, var in g.variables.items():
        yield "variable", nombre
        for a in var.ncattrs():
            yield "atributo", a
            yield from ((f"atributo {a} de {nombre}", t) for t in _texto_de(var.getncattr(a)))
        if var.dtype is str or getattr(var.dtype, "kind", "") in "OUS":
            yield from ((f"variable {nombre}", t) for t in _texto_de(var[:]))
    for nombre, sub in g.groups.items():
        yield "grupo", nombre
        yield from _textos_de_grupo(sub, f"{ruta}/{nombre}")


def _textos_de_netcdf(datos: bytes) -> Iterator[tuple[str, str]]:
    """Dimensiones, variables, grupos, atributos y sus valores de texto (hallazgo H5)."""
    import netCDF4                     # sólo al llamarse
    with netCDF4.Dataset("memoria", mode="r", memory=datos) as ds:
        yield from list(_textos_de_grupo(ds))


def _textos(nombre: str, contenido) -> Iterator[tuple[str, str]]:
    if isinstance(contenido, (bytes, bytearray, memoryview)):
        tipo, valor = _decodificar(nombre, bytes(contenido))
        if tipo == "gzip":
            yield from _textos(_sin_gz(nombre), valor)
        elif tipo == "parquet":
            yield from _textos_de_parquet(valor)
        elif tipo == "netcdf":
            yield from _textos_de_netcdf(valor)
        else:
            yield from _textos(nombre, valor)
        return
    if isinstance(contenido, str):
        tipo, valor = _texto_a_objeto(nombre, contenido)
        if tipo in ("json", "jsonl"):
            yield from _textos_de_objeto(valor)
        elif tipo == "csv":
            for i, fila in enumerate(valor):
                for celda in fila:
                    yield ("columna" if i == 0 else "celda"), celda
        else:
            yield "texto", valor
        return
    yield from _textos_de_objeto(contenido)


def _privado(texto: str, donde: str, nombre: str) -> None:
    if not entorno.sin_datos_privados(texto):
        raise SalidaProhibida(f"{nombre}: {donde} trae una ruta de la carpeta de usuario o una arroba")


def _comprobar_vocabulario(nombre: str, contenido) -> None:
    for parte in _componentes_del_nombre(nombre):
        palabra = vocabulario_en(parte)
        if palabra:
            raise SalidaProhibida(f"{nombre}: el nombre trae «{palabra}»")
    try:
        for donde, texto in _textos(nombre, contenido):
            _privado(texto, donde, nombre)
            palabra = vocabulario_en(texto)
            if palabra:
                raise SalidaProhibida(f"{nombre}: «{palabra}» en {donde}: {texto[:_MUESTRA]}")
    except SalidaProhibida as e:
        if str(e).startswith(f"{nombre}:"):
            raise
        raise SalidaProhibida(f"{nombre}: {e}") from e


# --- procedencia (CEG-11) ------------------------------------------------------------------------------------------
def _texto_de_procedencia(texto: str, *, version: bool = False) -> bool:
    """True si el texto tiene una forma de la procedencia (CEG-11)."""
    if not texto or not entorno.sin_datos_privados(texto):
        return False
    if es_ruta_por_alias(texto) or _HUELLA.fullmatch(texto) or _FORMA_FECHA.fullmatch(texto):
        return True
    if _FORMA_VERSION.fullmatch(texto) or (version and _FORMA_VERSION_CORTA.fullmatch(texto)):
        return True
    if _NUMERO.fullmatch(texto):
        return False
    if _FORMA_RUTA.fullmatch(texto) or _FORMA_IDENTIFICADOR.fullmatch(texto):
        return _DECIMAL.search(_FORMA_VERSION.sub(" ", texto)) is None
    return False


def _procedencia_objeto(obj, nombre: str, clave: str | None = None) -> None:
    if obj is None or isinstance(obj, bool):
        return
    if isinstance(obj, int):
        if clave not in CLAVES_ENTERAS:
            raise SalidaProhibida(f"{nombre}: un número en la procedencia bajo «{clave}» (sólo enteros de "
                                  f"{list(CLAVES_ENTERAS)})")
        if obj < 0:
            raise SalidaProhibida(f"{nombre}: un entero negativo en la procedencia bajo «{clave}» (son conteos; D12)")
        return
    if isinstance(obj, float):
        raise SalidaProhibida(f"{nombre}: un número decimal en la procedencia (bajo «{clave}»)")
    if isinstance(obj, str):
        if not _texto_de_procedencia(obj, version=clave in CLAVES_VERSION):
            raise SalidaProhibida(f"{nombre}: un texto que no es procedencia (bajo «{clave}»): {obj[:_MUESTRA]}")
        return
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            k = str(k)
            if not _texto_de_procedencia(k):
                raise SalidaProhibida(f"{nombre}: una clave que no es procedencia: {k[:_MUESTRA]}")
            _procedencia_objeto(v, nombre, k)
        return
    if isinstance(obj, (list, tuple)):
        for v in obj:
            _procedencia_objeto(v, nombre, clave)
        return
    raise SalidaProhibida(f"{nombre}: la procedencia no lleva un contenido de tipo {type(obj).__name__}")


def _procedencia_texto(nombre: str, texto: str) -> None:
    for n, linea in enumerate(texto.splitlines(), start=1):
        for token in linea.split():
            t = token.strip(_BORDES)
            if t and not _texto_de_procedencia(t):
                raise SalidaProhibida(f"{nombre}: la línea {n} trae algo que no es procedencia: {t[:_MUESTRA]}")


def _comprobar_procedencia(nombre: str, contenido) -> None:
    if _es_tabla(contenido):
        raise SalidaProhibida(f"{nombre}: una tabla no es procedencia")
    if isinstance(contenido, (bytes, bytearray, memoryview)):
        tipo, valor = _decodificar(nombre, bytes(contenido))
        if tipo == "gzip":
            return _comprobar_procedencia(_sin_gz(nombre), valor)
        if tipo != "texto":
            raise SalidaProhibida(f"{nombre}: la procedencia no lleva tablas ni NetCDF ({tipo})")
        contenido = valor
    if isinstance(contenido, str):
        tipo, valor = _texto_a_objeto(nombre, contenido)
        if tipo in ("json", "jsonl"):
            return _procedencia_objeto(valor, nombre)
        if tipo == "csv":
            raise SalidaProhibida(f"{nombre}: una tabla no es procedencia")
        return _procedencia_texto(nombre, contenido)
    _procedencia_objeto(contenido, nombre)


# --- documento (CEG-18, D13) ---------------------------------------------------------------------------------------
# Copia de umbrales.SHA_TEXTO_VIGENTE (v2.4, Enmienda 3, D65; post_hoc): ceguera no importa umbrales; una prueba las compara.
SHA_TEXTO_VIGENTE = "eaedb10998e1a3f37f83f036c478afb5cf3fd3ccb5262477bd394dc220b1908b"
# Dónde pueden estar las fuentes de las lecturas, por componentes de la ruta por alias («*»: cualquier carpeta).
RAICES_FUENTES = (("AP", "scripts_modelo_1km", "meteo_combinada"), ("APH", "auditoria", "*", "meteo_combinada"))
_SUPERINDICES = "⁰¹²³⁴⁵⁶⁷⁸⁹"
_FRACCIONES = "½¼¾⅓⅔⅛⅜⅝⅞"
_CIFRA = re.compile(rf"[\d{_SUPERINDICES}{_FRACCIONES}]")
_CORRIDA = re.compile(rf"(\d+(?:[.,]\d+)*)(?:\s?[·×]\s?10([⁻⁺]?[{_SUPERINDICES}]+)|([⁻⁺]?[{_SUPERINDICES}]+)"
                      r"|[eE]([−+-]?\d+))?")
_LECTURA_ES = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?")     # miles con punto, coma decimal
_LECTURA_EN = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")     # miles con coma, punto decimal
_GRUPOS = re.compile(r"[.,]")
_ENTERO = re.compile(r"\d+")
_PARES = re.compile(r"(?=(\d+[.,]\d+))")
_BASE_POTENCIA = "10"
_SIGNOS_SUPERINDICE = {"⁻": "-", "⁺": "+"}
_BORDES_DOCUMENTO = _BORDES + ".…!?¿¡|#%′″°*~"
_LETRA = re.compile(r"[^\W\d_]")
_LINEA_UNITTEST = re.compile(r"Ran \d+ tests? in \d+\.\d+s|(?:OK|FAILED)(?: \([a-z ]+=\d+(?:, [a-z ]+=\d+)*\))?")
_RAIZ_JSON = "raíz"
_D13 = "D13: un documento no lleva números de datos"


def _lecturas(cuerpo: str) -> set[Decimal]:
    """Las lecturas de unas cifras con separadores: con coma decimal (miles con punto) y con punto decimal."""
    salida = set()
    if _LECTURA_ES.fullmatch(cuerpo):
        salida.add(Decimal(cuerpo.replace(".", "").replace(",", ".")))
    if _LECTURA_EN.fullmatch(cuerpo):
        salida.add(Decimal(cuerpo.replace(",", "")))
    return salida


def _exponente(superindice: str) -> int:
    return int("".join(_SIGNOS_SUPERINDICE.get(c) or str(unicodedata.digit(c)) for c in superindice))


def _ocurrencias(texto: str) -> list[frozenset]:
    """Por cada número de un texto, sus lecturas posibles, sin el signo (CEG-18)."""
    salida: list[frozenset] = []
    for m in _CORRIDA.finditer(texto):
        cuerpo, por_diez, superindice, exp_e = m.groups()
        lecturas = _lecturas(cuerpo)
        if not lecturas:                                   # «1.2,3»: cada grupo es un número
            salida.extend(frozenset({Decimal(g)}) for g in _GRUPOS.split(cuerpo))
            continue
        exponente = None
        if por_diez is not None:                           # «2,0·10¹¹»
            exponente = _exponente(por_diez)
        elif superindice is not None and cuerpo == _BASE_POTENCIA:     # «10⁻⁶»
            lecturas, exponente = {Decimal(1)}, _exponente(superindice)
        elif exp_e is not None:                            # «1e-9»
            exponente = int(exp_e.replace("−", "-"))
        if exponente is not None:
            lecturas = {x.scaleb(exponente) for x in lecturas}
        salida.append(frozenset(abs(x) for x in lecturas))
    salida.extend(frozenset({Decimal(repr(unicodedata.numeric(c)))}) for c in texto if c in _FRACCIONES)
    return salida


def _valores_de_fuente(texto: str) -> set[Decimal]:
    """Los números de una fuente (el texto o una lectura), con todas sus lecturas, también los enteros de cada grupo y
    los pares con separador («3.11» de «3.11.16»); sin las cifras de las huellas hexadecimales."""
    valores: set[Decimal] = set()
    for token in texto.split():
        t = token.strip(_BORDES_DOCUMENTO)
        if not _CIFRA.search(t) or _HUELLA.fullmatch(t):
            continue
        for lecturas in _ocurrencias(t):
            valores |= lecturas
        valores.update(Decimal(m.group(0)) for m in _ENTERO.finditer(t))
        for m in _PARES.finditer(t):
            valores |= _lecturas(m.group(1))
    return valores


def _es_fuente(ruta: str) -> bool:
    """CEG-18: una ruta por alias del paquete o de la auditoría del producto, sin «.» ni «..»."""
    if not isinstance(ruta, str) or not entorno.sin_datos_privados(ruta) or not es_ruta_por_alias(ruta):
        return False
    partes = ruta.split("/")
    if any(p in ("", ".", "..") for p in partes):
        return False
    return any(len(partes) > len(raiz) and all(fnmatch.fnmatchcase(p, r) for p, r in zip(partes, raiz))
               for raiz in RAICES_FUENTES)


class ReferenciaDocumento:
    """El texto vigente y las fuentes de las lecturas con que se vigila un documento (D13; CEG-18).

    ``texto``: el texto vigente (str), cuyo sha256 en UTF-8 es ``sha256_texto`` y debe ser ``SHA_TEXTO_VIGENTE``.
    ``fuentes``: {ruta por alias del paquete o de la auditoría del producto: contenido (str o bytes UTF-8)}.
    ValueError si algo no calza. ``fuentes`` queda como ((ruta, sha256), …), en orden.
    """

    __slots__ = ("sha256_texto", "fuentes", "_permitidos")

    def __init__(self, texto: str, sha256_texto: str, *, fuentes: Mapping[str, str | bytes] | None = None):
        if not isinstance(texto, str) or not isinstance(sha256_texto, str) or _SHA256.fullmatch(sha256_texto) is None:
            raise ValueError("la referencia de un documento es el texto (str) y su sha256 (64 hexadecimales)")
        if sha256_texto != SHA_TEXTO_VIGENTE:
            raise ValueError("un documento cita el texto vigente (SHA_TEXTO_VIGENTE), no otro (D13)")
        if entorno.sha256_bytes(texto.encode("utf-8")) != sha256_texto:
            raise ValueError("el texto no es el de su sha256")
        permitidos = _valores_de_fuente(texto)
        registradas = []
        for ruta, contenido in (fuentes or {}).items():
            if not _es_fuente(ruta):
                raise ValueError("una fuente de las lecturas es una ruta por alias bajo "
                                 f"{['/'.join(r) for r in RAICES_FUENTES]} (CEG-18)")
            datos = contenido.encode("utf-8") if isinstance(contenido, str) else bytes(contenido)
            try:
                texto_fuente = datos.decode("utf-8")
            except UnicodeDecodeError as e:
                raise ValueError(f"la fuente {ruta} no es un texto UTF-8") from e
            registradas.append((ruta, entorno.sha256_bytes(datos)))
            permitidos |= _valores_de_fuente(texto_fuente)
        self.sha256_texto = sha256_texto
        self.fuentes = tuple(sorted(registradas))
        self._permitidos = frozenset(permitidos)

    def permite(self, lecturas) -> bool:
        """True si alguna lectura de un número es un número del texto o de las fuentes."""
        return not self._permitidos.isdisjoint(lecturas)


def _token_de_documento(token: str, referencia: ReferenciaDocumento, *, version: bool = False) -> bool:
    """True si una palabra de un documento no trae un número de datos (CEG-18)."""
    t = token.strip(_BORDES_DOCUMENTO)
    if not _CIFRA.search(t):
        return True
    if (_HUELLA.fullmatch(t) or _FORMA_FECHA.fullmatch(t) or _FORMA_VERSION.fullmatch(t)
            or (version and _FORMA_VERSION_CORTA.fullmatch(t))):
        return True
    if _LETRA.search(t) and (es_ruta_por_alias(t) or _FORMA_RUTA.fullmatch(t) or _FORMA_IDENTIFICADOR.fullmatch(t)):
        decimales = " ".join(m.group(0) for m in _DECIMAL.finditer(_FORMA_VERSION.sub(" ", t)))
        return all(referencia.permite(x) for x in _ocurrencias(decimales))     # sus enteros son un nombre
    return all(referencia.permite(x) for x in _ocurrencias(t))


def _texto_de_documento(nombre: str, texto: str, referencia: ReferenciaDocumento, donde: str, *,
                        version: bool = False, unittest: bool = False) -> None:
    _privado(texto, donde, nombre)
    lineas = texto.splitlines()
    for n, linea in enumerate(lineas, start=1):
        if unittest and _LINEA_UNITTEST.fullmatch(linea.strip()):
            continue
        for token in linea.split():
            if not _token_de_documento(token, referencia, version=version):
                lugar = f"{donde}, línea {n}" if len(lineas) > 1 else donde
                raise SalidaProhibida(f"{nombre}: un número que no sale del texto ni de las lecturas en {lugar} "
                                      f"({_D13})")


def _documento_objeto(obj, nombre: str, referencia: ReferenciaDocumento, donde: str = _RAIZ_JSON,
                      clave: str | None = None) -> bool:
    """Revisa un JSON de un documento (CEG-18); True si cita la huella del texto."""
    if obj is None or isinstance(obj, bool):
        return False
    lugar = donde[:_MUESTRA]
    if isinstance(obj, int):
        if (clave in CLAVES_ENTERAS and obj >= 0) or referencia.permite({abs(Decimal(obj))}):
            return False
        raise SalidaProhibida(f"{nombre}: un entero que no sale del texto ni de las lecturas en «{lugar}» ({_D13})")
    if isinstance(obj, float):
        if math.isfinite(obj) and referencia.permite({abs(Decimal(repr(obj)))}):
            return False
        raise SalidaProhibida(f"{nombre}: un número que no sale del texto ni de las lecturas en «{lugar}» ({_D13})")
    if isinstance(obj, str):
        _texto_de_documento(nombre, obj, referencia, f"«{lugar}»", version=clave in CLAVES_VERSION)
        return referencia.sha256_texto in obj
    if isinstance(obj, Mapping):
        hallada = False
        for k, v in obj.items():
            k = str(k)
            _texto_de_documento(nombre, k, referencia, f"una clave de «{lugar}»")
            hallada |= referencia.sha256_texto in k
            hallada |= _documento_objeto(v, nombre, referencia, k if donde == _RAIZ_JSON else f"{donde}/{k}", k)
        return hallada
    if isinstance(obj, (list, tuple)):
        hallada = False
        for i, v in enumerate(obj):
            hallada |= _documento_objeto(v, nombre, referencia, f"{donde}[{i}]", clave)
        return hallada
    raise SalidaProhibida(f"{nombre}: un documento no lleva un contenido de tipo {type(obj).__name__}")


def _comprobar_documento(nombre: str, contenido, referencia: ReferenciaDocumento) -> None:
    casa = str(Path.home())
    if not entorno.sin_datos_privados(nombre[len(casa):] if nombre.startswith(casa + os.sep) else nombre):
        raise SalidaProhibida("el nombre de un documento trae una ruta de la carpeta de usuario o una arroba")
    if _es_tabla(contenido):
        raise SalidaProhibida(f"{nombre}: una tabla no es un documento")
    if isinstance(contenido, (bytes, bytearray, memoryview)):
        tipo, valor = _decodificar(nombre, bytes(contenido))
        if tipo == "gzip":
            return _comprobar_documento(_sin_gz(nombre), valor, referencia)
        if tipo != "texto":
            raise SalidaProhibida(f"{nombre}: un documento no lleva tablas ni NetCDF ({tipo})")
        contenido = valor
    if isinstance(contenido, str):
        if _sin_gz(nombre).casefold().endswith((".csv", ".tsv")):
            raise SalidaProhibida(f"{nombre}: una tabla no es un documento")
        tipo, valor = _texto_a_objeto(nombre, contenido)
        if tipo in ("json", "jsonl"):
            _documento_objeto(valor, nombre, referencia)
        else:
            _texto_de_documento(nombre, contenido, referencia, "el texto", unittest=True)
        hallada = referencia.sha256_texto in contenido
    else:
        hallada = _documento_objeto(contenido, nombre, referencia)
    if not hallada:
        raise SalidaProhibida(f"{nombre}: un documento cita la huella del texto vigente, con sus 64 caracteres (D13)")


class ConsolaDocumento:
    """La consola como documento (D13; CEG-18). ``encabezado()`` es su primera línea y cita la huella del texto;
    ``linea(texto)`` vigila cada línea siguiente con la regla del documento y la devuelve tal cual, para mostrarla."""

    def __init__(self, referencia: ReferenciaDocumento):
        if not isinstance(referencia, ReferenciaDocumento):
            raise ValueError("la consola se vigila con una ReferenciaDocumento")
        self._referencia = referencia
        self._abierta = False

    def encabezado(self) -> str:
        self._abierta = True
        return f"texto vigente sha256 {self._referencia.sha256_texto}"

    def linea(self, texto: str) -> str:
        if not self._abierta:
            raise SalidaProhibida("consola: la primera línea es el encabezado con la huella del texto (D13)")
        if not isinstance(texto, str):
            raise SalidaProhibida("consola: una línea es un texto")
        _texto_de_documento("consola", texto, self._referencia, "una línea", unittest=True)
        return texto


# --- la clase que fija la ruta (CEG-19 y CEG-20; D3, D13, D14 y D53) --------------------------------------------
# Por el nombre del archivo, sin «.gz» («*» como en fnmatch): sin «/», el último componente; con «/», el nombre entero
# relativo a la corrida (anclado al comienzo; CEG-20).
CLASE_DE_ARCHIVO: Mapping[str, str] = {
    "decision.json": "metrica", "resumen_qc.json": "resumen",                                     # D3 (MC-02)
    "decision_m6.json": "resumen", "avance.jsonl": "procedencia", "recibo_corrida.json": "procedencia",   # D14
    "sha256.json": "procedencia", "intentos_*.jsonl": "procedencia",                               # D14
    "producto/clima_a.parquet": "insumo", "producto/tramos_homogeneos.parquet": "insumo",          # D14
    "addendum_m1.json": "documento", "addendum_m1.md": "documento", "anexo_a2.json": "documento",  # D13
    "pruebas_m1.txt": "documento",                                                                 # D13
    "resumen_m1.json": "resumen", "costo_m1.json": "resumen", "deriva_s6.json": "resumen",         # P42 (D53)
    "registro_m2a.json": "resumen", "registro_m34.json": "resumen",                                # P42 (D53)
    "m6/tf_contaminantes_*.json": "resumen",                                                       # P42 (D53)
    "politicas/politicas_meteo_v1.json": "insumo",                                                 # P42 (D53)
    "informe.json": "resumen", "informe.md": "documento",                                          # P43 (D53)
    "qc/no_normalizables.csv": "resumen",                                          # §8 (H16): sin valores, CEG-20
    "recibos/recibo_*.json": "procedencia", "m6/recibos/recibo_*.json": "procedencia",   # SLD-10 (PED-6 de I17)
}
# Por la carpeta al comienzo del nombre relativo a la corrida, o justo después de «m6/» (CEG-20, H5).
CLASE_DE_CARPETA: Mapping[str, str] = {
    "validacion": "metrica", "tendencias": "resumen",                                              # D3
    "insumos": "insumo", "producto/residuos": "insumo", "ambiental": "insumo",                     # D3
    "estaticas": "insumo", "qc/estaciones": "insumo", "producto_01deg": "insumo", "salud": "insumo",   # D14
    "m6": "resumen",                                                         # P42 (D53): la más estricta, CEG-20
}
# CEG-20: lo que antecede al nombre relativo a la corrida («LOCAL/meteo_combinada/v1/<corrida>/», o
# «…/meteo_combinada/v1/» en la publicación) y el único prefijo admitido delante de una carpeta fijada.
_RAIZ_SALIDAS = ("meteo_combinada", "v1")
_CARPETAS_SIN_ETIQUETA = ("m1", "m2a")                                     # ENT-4
_PREFIJO_DE_CARPETA = "m6"


def _partes_de_salida(nombre_archivo) -> list[str]:
    """Los componentes del nombre de una salida relativo a la carpeta de su corrida, en minúsculas y sin «.gz» en el
    último (CEG-20): si la ruta trae «meteo_combinada/v1/», lo que sigue a la carpeta de la corrida (una etiqueta
    sellada, «m1» o «m2a») o, si no hay corrida (la publicación), lo que sigue a «v1»; si no, la ruta entera."""
    originales = [p for p in PurePosixPath(os.fsdecode(os.fspath(nombre_archivo)).replace(os.sep, "/")).parts
                  if p not in ("/", ".")]
    menores = [p.casefold() for p in originales]
    n = len(_RAIZ_SALIDAS)
    for i in range(len(menores) - n, -1, -1):                 # la última aparición
        if tuple(menores[i:i + n]) == _RAIZ_SALIDAS:
            j = i + n
            if j < len(menores) - 1 and (menores[j] in _CARPETAS_SIN_ETIQUETA
                                         or entorno.es_etiqueta_corrida(originales[j])):
                j += 1
            menores = menores[j:]
            break
    if menores:
        menores[-1] = _sin_gz(menores[-1])
    return menores


def _calza(partes: list[str], patron: str) -> bool:
    """True si el nombre relativo a la corrida calza con un patrón de ``CLASE_DE_ARCHIVO``: sin «/», su último
    componente; con «/», el nombre entero (CEG-20)."""
    p = patron.casefold().split("/")
    if len(p) == 1:
        return bool(partes) and fnmatch.fnmatchcase(partes[-1], p[0])
    return len(partes) == len(p) and all(fnmatch.fnmatchcase(a, b) for a, b in zip(partes, p))


def _carpeta_al_comienzo(carpetas: list[str]) -> str | None:
    """La clase de la carpeta fijada más larga con que empiezan ``carpetas`` (claves en minúsculas, H15), o None."""
    elegida, largo = None, 0
    for patron, clase in CLASE_DE_CARPETA.items():
        p = patron.casefold().split("/")
        if carpetas[:len(p)] == p and len(p) > largo:
            elegida, largo = clase, len(p)
    return elegida


def clase_de_ruta(nombre_archivo) -> str | None:
    """La clase que D3, D13, D14 y D53 (P42 y P43) fijan para una salida, por su nombre relativo a la carpeta de la
    corrida (o por alias), o None (CEG-19 y CEG-20). El archivo manda; si no, la carpeta al comienzo del nombre o
    justo después de «m6/» (una subcarpeta más adentro no cambia la clase). ValueError si calza con dos patrones de
    archivo de clases distintas."""
    partes = _partes_de_salida(nombre_archivo)
    if not partes:
        return None
    por_archivo = {clase for patron, clase in CLASE_DE_ARCHIVO.items() if _calza(partes, patron)}
    if len(por_archivo) > 1:
        raise ValueError(f"la ruta calza con patrones de archivo de clases distintas: {sorted(por_archivo)} (CEG-20)")
    if por_archivo:
        return por_archivo.pop()
    carpetas = partes[:-1]
    if carpetas[:1] == [_PREFIJO_DE_CARPETA]:
        detras = _carpeta_al_comienzo(carpetas[1:])
        if detras is not None:
            return detras
    return _carpeta_al_comienzo(carpetas)


def _misma_regla(fijada: str, declarada: str) -> bool:
    return fijada == declarada or {fijada, declarada} <= set(CLASES_CON_VOCABULARIO)


def vigilar_salida(nombre_archivo: str, contenido, *, clase: str, referencia: ReferenciaDocumento | None = None
                   ) -> None:
    """Rechaza (``SalidaProhibida``) una salida que la clase no admite (S7; D3, D12, D13, D14 y D53; CEG-8 a CEG-12 y
    CEG-15 a CEG-20).

    ``nombre_archivo``: su nombre por alias o relativo a la carpeta de la corrida. ``contenido``: bytes, texto,
    diccionarios y listas, o una tabla (DataFrame), tal como se va a escribir. Si la ruta tiene una clase fijada
    (``clase_de_ruta``), la declarada debe ser ésa.
    - «metrica» y «resumen»: ningún texto (nombres ni valores) con vocabulario prohibido o un nombre propio del fondo o
      del residuo, ni datos privados; huellas sólo bajo ``huellas``; ``dmc_R_*`` sólo listadas bajo ``columnas…``;
    - «insumo»: permitido;
    - «procedencia»: el esquema cerrado de CEG-11;
    - «documento»: con ``referencia`` (una ``ReferenciaDocumento``), la regla de CEG-18. Sólo esta clase la lleva.
    """
    if clase not in CLASES_SALIDA:
        raise ValueError(f"clase de salida desconocida: {clase!r} (son {list(CLASES_SALIDA)})")
    if clase == "documento" and not isinstance(referencia, ReferenciaDocumento):
        raise ValueError("un documento se vigila con la referencia del texto (ReferenciaDocumento; CEG-18)")
    if clase != "documento" and referencia is not None:
        raise ValueError("la referencia del texto sólo vale para un documento")
    nombre = os.fsdecode(os.fspath(nombre_archivo))
    fijada = clase_de_ruta(nombre)
    if fijada is not None and not _misma_regla(fijada, clase):
        raise SalidaProhibida(f"{nombre}: su clase es «{fijada}» (D3, D13, D14 y D53; CEG-19 y CEG-20), no «{clase}»")
    if clase in CLASES_CON_VOCABULARIO:
        _comprobar_vocabulario(nombre, contenido)
    elif clase == "procedencia":
        _comprobar_procedencia(nombre, contenido)
    elif clase == "documento":
        _comprobar_documento(nombre, contenido, referencia)


# =====================================================================================================
# RELOJ (§1.9, MC-19)
# =====================================================================================================
_PUBLICACION_RELOJ = ("config", "meteorologia", "reloj_dmc", "v1")
_CORRIDAS_RELOJ = "verificacion_reloj_dmc"
POLITICA_RELOJ = "politica_reloj_dmc.json"
ARTEFACTOS_RELOJ = "artefactos_evaluados.json.gz"
INFORME_RELOJ = "informe_reloj_dmc.json"
PIXELES_RELOJ = "pixeles_dmc.parquet"
REGISTRO_C5 = "registro_politica_reloj.json"


def _partes_lexicas(ruta) -> tuple[str, ...]:
    texto = _texto_lexico(ruta)
    if texto is None:
        raise TypeError(f"no es una ruta: {ruta!r}")
    return tuple(p.casefold() for p in PurePosixPath(texto).parts)


def es_de_reloj(ruta) -> bool:
    """True si la ruta es de lo que publica o deja RELOJ (su carpeta publicada o una de sus corridas), por ruta
    léxica, o si es el registro de su C5."""
    partes = _partes_lexicas(ruta)
    n = len(_PUBLICACION_RELOJ)
    publicada = any(partes[i:i + n] == _PUBLICACION_RELOJ for i in range(len(partes) - n + 1))
    return publicada or _CORRIDAS_RELOJ in partes or (partes[-1:] == (REGISTRO_C5,))


def permitido_de_reloj(ruta, *, k2: bool = False) -> bool:
    """Política, ``artefactos_evaluados`` y registro de C5; con ``k2``, la fuente de la lista K2 (§1.9, MC-19; CEG-13)."""
    partes = _partes_lexicas(ruta)
    if len(partes) < 2:
        return False
    nombre, carpeta = partes[-1], partes[:-1]
    if nombre == REGISTRO_C5:
        return carpeta[-1:] == ("meteo_combinada",)
    en_publicacion = carpeta[-len(_PUBLICACION_RELOJ):] == _PUBLICACION_RELOJ
    if nombre in (POLITICA_RELOJ, ARTEFACTOS_RELOJ):
        return en_publicacion
    if k2 and nombre == INFORME_RELOJ:
        return en_publicacion
    if k2 and nombre == PIXELES_RELOJ:
        return _CORRIDAS_RELOJ in carpeta
    return False


# =====================================================================================================
# Guarda del residuo (§0.4.6, S7)
# =====================================================================================================
_BASE_CENTINELA = 91.73528146209   # no-umbral: valor distintivo (no es un umbral), inyectado sólo en las pruebas
_PASO_CENTINELA = 7.31415926535    # no-umbral: separación entre centinelas
_CIFRAS = (6, 9)                   # no-umbral: cifras significativas de los textos que se buscan


def _repr_f32(valor: float) -> str:
    """El texto más corto que vuelve al mismo float32 (como ``repr(numpy.float32(x))``)."""
    empacado = struct.pack("<f", valor)
    redondeado = struct.unpack("<f", empacado)[0]
    for cifras in range(1, len(repr(redondeado)) + 1):
        texto = f"{redondeado:.{cifras}g}"
        if struct.pack("<f", float(texto)) == empacado:
            return texto
    return repr(redondeado)


class GuardaResiduo:
    """S7: centinelas en memoria (mediana y MAD del residuo) que no deben aparecer en los bytes de ninguna salida.

    ``centinela(nombre)`` da un valor distintivo (y lo registra) para inyectarlo en el cálculo; ``registrar`` agrega
    uno dado. ``buscar(contenido)`` y ``buscar_en(ruta)`` dicen dónde aparece alguno; ``comprobar`` lanza
    ``SalidaProhibida`` si aparece (CEG-14).
    """

    def __init__(self):
        self._centinelas: dict[str, float] = {}

    @property
    def centinelas(self) -> Mapping[str, float]:
        return dict(self._centinelas)

    def centinela(self, nombre: str) -> float:
        if nombre not in self._centinelas:
            self.registrar(nombre, _BASE_CENTINELA + _PASO_CENTINELA * len(self._centinelas))
        return self._centinelas[nombre]

    def registrar(self, nombre: str, valor: float) -> None:
        valor = float(valor)
        if not math.isfinite(valor) or valor == 0:
            raise ValueError("un centinela es un número finito distinto de 0")
        self._centinelas[str(nombre)] = valor

    def formas(self) -> dict[str, dict[str, bytes]]:
        """Por centinela, sus formas en bytes: textos y binarios float32/float64 en los dos órdenes."""
        salida = {}
        for nombre, v in self._centinelas.items():
            textos = {"repr64": repr(v), "repr32": _repr_f32(v), **{f"g{c}": f"{v:.{c}g}" for c in _CIFRAS}}
            f = {k: t.encode("ascii") for k, t in textos.items()}
            f.update({"f8<": struct.pack("<d", v), "f8>": struct.pack(">d", v),
                      "f4<": struct.pack("<f", v), "f4>": struct.pack(">f", v)})
            salida[nombre] = f
        return salida

    def _en_bytes(self, datos: bytes) -> list[tuple[str, str]]:
        return [(nombre, forma) for nombre, formas in self.formas().items()
                for forma, b in formas.items() if b in datos]

    def _en_numeros(self, valores) -> list[tuple[str, str]]:
        import numpy as np             # sólo al llamarse
        a = np.asarray(valores)
        if a.dtype.kind not in "fiu" or a.size == 0:
            return []
        hallados = []
        for nombre, v in self._centinelas.items():
            v32 = float(struct.unpack("<f", struct.pack("<f", v))[0])
            if a.dtype == np.float32:
                if np.any(a == np.float32(v)):
                    hallados.append((nombre, "valor float32"))
            elif np.any(a == v) or np.any(a == v32):
                hallados.append((nombre, "valor"))
        return hallados

    def buscar(self, contenido, *, nombre: str = "contenido") -> list[tuple[str, str]]:
        """(centinela, forma) de cada centinela que aparece en un contenido en memoria o en sus bytes."""
        if isinstance(contenido, (bytes, bytearray, memoryview)):
            datos = bytes(contenido)
            hallados = self._en_bytes(datos)
            try:
                tipo, valor = _decodificar(nombre, datos)
            except SalidaProhibida:
                return hallados
            if tipo == "gzip":
                hallados += self.buscar(valor, nombre=nombre)
            elif tipo == "parquet":
                hallados += self.buscar(_parquet(valor)[1], nombre=nombre)
            elif tipo == "netcdf":
                hallados += self._en_netcdf(valor)
            return sorted(set(hallados))
        if isinstance(contenido, str):
            return self.buscar(contenido.encode("utf-8"), nombre=nombre)
        if _es_tabla(contenido):
            hallados = []
            for c in contenido.columns:
                columna = contenido[c]
                if columna.dtype.kind in "fiu":
                    hallados += self._en_numeros(columna.to_numpy())
                else:
                    hallados += self._en_bytes(" ".join(map(str, columna.tolist())).encode("utf-8"))
            return sorted(set(hallados))
        if hasattr(contenido, "dtype") and hasattr(contenido, "ravel"):
            return sorted(set(self._en_numeros(contenido)))
        if isinstance(contenido, (Mapping, list, tuple)):
            numeros, textos = [], []
            pila = [contenido]
            while pila:
                x = pila.pop()
                if isinstance(x, Mapping):
                    textos.extend(map(str, x.keys()))
                    pila.extend(x.values())
                elif isinstance(x, (list, tuple)):
                    pila.extend(x)
                elif isinstance(x, (int, float)) and not isinstance(x, bool):
                    numeros.append(float(x))
                elif x is not None:
                    textos.append(str(x))
            hallados = self._en_numeros(numeros) if numeros else []
            return sorted(set(hallados + self._en_bytes(" ".join(textos).encode("utf-8"))))
        if isinstance(contenido, (int, float)):
            return sorted(set(self._en_numeros([contenido])))
        return []

    def _en_netcdf(self, datos: bytes) -> list[tuple[str, str]]:
        import netCDF4                 # sólo al llamarse
        hallados = []

        def recorrer(g):
            for var in g.variables.values():
                valores = var[:]
                hallados.extend(self._en_numeros(valores.filled(0) if hasattr(valores, "filled") else valores))
            for sub in g.groups.values():
                recorrer(sub)

        with netCDF4.Dataset("memoria", mode="r", memory=datos) as ds:
            recorrer(ds)
        return hallados

    def buscar_en(self, ruta) -> list[tuple[str, str, str]]:
        """(archivo, centinela, forma) en un archivo o en todos los de una carpeta (en orden)."""
        ruta = Path(ruta)
        archivos = sorted(p for p in ruta.rglob("*") if p.is_file()) if ruta.is_dir() else [ruta]
        salida = []
        for archivo in archivos:
            relativo = archivo.name if archivo == ruta else archivo.relative_to(ruta).as_posix()
            for nombre, forma in self.buscar(archivo.read_bytes(), nombre=archivo.name):
                salida.append((relativo, nombre, forma))
        return salida

    def comprobar(self, contenido_o_ruta, *, nombre: str = "contenido") -> None:
        """``SalidaProhibida`` si algún centinela aparece en el contenido o en la ruta (archivo o carpeta)."""
        if isinstance(contenido_o_ruta, Path):
            hallados = self.buscar_en(contenido_o_ruta)
        else:
            hallados = self.buscar(contenido_o_ruta, nombre=nombre)
        if hallados:
            raise SalidaProhibida(f"centinelas del residuo en una salida: {hallados[:_CITADOS]}")
