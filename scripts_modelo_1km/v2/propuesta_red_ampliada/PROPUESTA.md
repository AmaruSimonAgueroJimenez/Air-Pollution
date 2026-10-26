# Propuesta: traducción del bloque «Red ampliada e insumos de hoy» (versión 5, tras la quinta revisión independiente)

**Estado: aplicada en AP y en el espejo el 2026-10-26 (paso 1 de §11), antes de la ratificación del paso 0, como permite
T13.** `DISENO_AMBIENTAL_V2.md` pasó de 5d879a05… a 5140306e…, `config_v2.json` de 232c75b3… a 02d8c386…, y los 21
archivos de código y pruebas de §5 tienen la huella de resultado de CAMBIOS. La v1 (código, paneles, grilla y derivado)
no se tocó. `config/componentes_compartidos.json` no entra en el commit de la traducción: se regenera antes del armado
(§11.1). **El paso 0, la ratificación de T11 a T13, se hizo el 2026-10-26 (§9.0):** el archivo de decisiones pasó a
a0b970d2…, `panel_red2_v2.py` a 18fa2b9d… (sólo un comentario) y `config_v2.json` a 51df5063…; falta su commit, en
AP y en el espejo. El código nuevo que pide el §3 del bloque está en módulos nuevos de
`scripts_modelo_1km/v2/` (§6), con sus pruebas. Esta versión reemplaza la del 2026-10-25, corrige los 15 hallazgos de
la revisión independiente (§3), implementa las decisiones del autor del 2026-10-26, T4 a T13 (§3.1, §3.2, §3.3, §3.6 y §9; las
de la traducción, en total, T1 a T13; T11, T12 y T13 **[delegadas]**), corrige
lo que pidió la segunda revisión independiente, cuyo veredicto fue «se puede aplicar con cambios» (§3.2), y lo que pidió
la tercera (§3.3), incluida la traducción de T11, decidida **[delegada]** por la opción recomendada y ratificada por el
autor el 2026-10-26 (§9). La versión 4 corrigió los 37 hallazgos de la cuarta revisión independiente (§3.4) y esta versión
5 corrige los 26 de la quinta (§3.5); cada arreglo de código se comprobó revirtiéndolo en una copia: su prueba falla
(§5.3). Las rondas de verificación de la traducción del 2026-10-26 corrigieron además un derivado auténtico pero
parcial que pasaba por el reloj y por el panel, e implementaron T12 y T13 (§3.6); la cuarta ronda de verificación
corrigió 25 hallazgos más, entre ellos la ratificación de T13 en la compuerta, la prueba sellada que la parada de R19
rompía y la huella de `produccion.py` por repositorio (§3.7); y la quinta ronda, 30 más (§3.8), entre ellos que en la
decisión rija la evaluabilidad de E2 registrada antes del ajuste, como dice R15, sin ninguna elección abierta al autor.

## 1. Origen

| Documento | Dónde | sha256 |
|---|---|---|
| Bloque de la Enmienda 2 (R1-R22), anclado en f2c6cfc y sellado en 65afe8a | repositorio de salud, `auditoria/20261024/sinca_al_modelo/ENMIENDA_2_BLOQUE_RED_AMPLIADA.md` | `274ebae06bee8eeeb7470a650ce0539af751577d292513b8198cdec7c159094b` |
| Decisiones del autor sobre el bloque | ídem, `decisiones_autor_20261024.md` | `01744a98101ff149fc3e65a32046c27b2fd810bd2b23d8c72594e00b4355b7af` |
| Decisiones del autor sobre la traducción (T1: las cuatro lecturas; T2: aplicar tras revisión; T3: copia de MERRA-2; sección 2026-10-26: T4 convención civil, T5 catálogo MAIAC, T6 espacio, T7 revisión y aceptación; tras la segunda revisión: T8 huella de afg_lib, T9 unidad de los votos de T4, T10 conversión civil; por delegación del autor: T11 **[delegada]**, las 146 órbitas TROPOMI de 2024 por fecha de modificación; T12 **[delegada]**, las diferencias y lecturas que T7 no cubría y dos correcciones; T13 **[delegada]**, el armado espera la ratificación de T11 a T13; las tres, ratificadas por el autor el 2026-10-26, con la ratificación anotada al final) | ídem, `decisiones_autor_traduccion_20261025.md` (en el git del espejo desde d690581, con fdfbfa31…, la de antes de la ratificación; la ratificación entra en el commit del paso 0 de §11; la compuerta lo exige rastreado y con esta huella, `red_ampliada_v2.ARCHIVOS_DEL_ESPEJO`) | `a0b970d2fbbf08a11c28d24c075ca1dd81ef2509d2093d243c1fc7a95dad3920` |
| Análisis y plan | ídem, `analisis_y_plan.md` | `3407fb28e6318b60ccb0c555b3396c9b94f8878d12e09b9d4913b22356d18fa4` |
| Nota del contraste de unidades | ídem, `contraste_unidades_cams.md` | `d8f69d5d8e8c543276df9088351f87fc4907c5b78c148f4684d97ad0a05600d8` |
| Primera corrida del contraste | ídem, `contraste_unidades_cams.csv` | `ca0805ae0e7af3c2ff8f241600ad46327ebfd68c27c470361a210b301bc9f855` |

## 2. Archivos de esta carpeta

| Archivo | Qué es | sha256 |
|---|---|---|
| `DISENO_AMBIENTAL_V2.propuesto.md` | texto nuevo completo: el contrato vigente más el bloque transcrito sin cambios al final de «Enmiendas», con sus encabezados bajados dos niveles | `5140306eae85f854e17748b1119300ce35f9239685487bff3806b285ca397670` |
| `config_v2.propuesto.json` | texto nuevo completo: la configuración vigente con los cambios de §4; el resto, byte a byte igual; desde el paso 0 (2026-10-26), con la ratificación de T11 a T13 (§9.0) | `51df5063ed642c737d883a82c40382e7e211d288f5499151edce61bd692528d7` |
| `CAMBIOS_AL_CODIGO_SELLADO.md` | 70 reemplazos exactos en 21 archivos sellados (código y pruebas), con la huella de cada origen y de cada resultado (el de `test_config_v2`, con la huella de las decisiones ratificadas) | `84362a574ca9cbb688106d46df94124f4767f4918d36a44d4b98f121403147e8` |

Para verlos frente a los vigentes, sin escribir nada:

    git diff --no-index -- scripts_modelo_1km/v2/DISENO_AMBIENTAL_V2.md scripts_modelo_1km/v2/propuesta_red_ampliada/DISENO_AMBIENTAL_V2.propuesto.md
    git diff --no-index -- scripts_modelo_1km/v2/config_v2.json scripts_modelo_1km/v2/propuesta_red_ampliada/config_v2.propuesto.json

No van como diffs unificados porque sus marcas de bloque llevan el carácter que la regla del repositorio público excluye.

Los cuatro archivos de esta carpeta entran en el commit de la traducción, en AP y en el espejo
(`red_ampliada_v2.ARCHIVOS_PROPUESTA`, dentro de `ARCHIVOS_TRADUCCION`): `test_red_ampliada_v2` lee
`CAMBIOS_AL_CODIGO_SELLADO.md` y, sin rastrear dentro de `scripts_modelo_1km/v2`, la carpeta detendría
`correr_v2.verificar_sellado` (cuarta revisión, mayor 3). Quedan como registro de la traducción; no se borran al aplicar.

## 3. Qué corrige esta versión

Cada arreglo tiene una prueba que falla sin él.

| Hallazgo | Arreglo | Prueba |
|---|---|---|
| **B1.** La segunda corrida del contraste no trae la 518 y la regla de unidades se detenía | `unidades_v2.unidades_red2(…, con_coordenada)`: las series sin coordenada de R8 salen y quedan registradas **antes** de la regla de unidades; la huella del contraste es obligatoria | `test_unidades_v2.SinCoordenadaTests` (3) y `DatosRealesTests.test_segunda_corrida_sin_la_518` |
| **M1.** Dos caminos para los pliegues, con huellas distintas | una sola fuente: `pliegues_red2_v2.py` → `pliegues_v2_red2.json` (pliegues, pesos, E2 y bloque más influyente, con `huella_pliegues` y `huella_pesos`); el primer fijado renombra intacto `pliegues_v2.json` (R13); el mismo candado «pliegues»; `pliegues_v2.py` se detiene bajo el contrato con la red; el anexo registra sha256 y huellas en `red_de_monitores.registro_de_la_red.pliegues` y `correr_v2` y `piloto_v2` lo exigen (después del anexo sólo caben los recortes que anota el piloto). La configuración dice dónde está cada cosa (`fuente_unica_de_pliegues`) y que su huella no es comparable con la del manifiesto original | `test_pliegues_red2_v2.test_una_sola_fuente_y_reemplazo_de_r13` y `test_el_anexo_exige_la_huella`; al aplicar, `test_pliegues_v2.test_con_la_red_ampliada_no_corre`, `test_manifiesto_v2.test_red_ampliada_una_sola_fuente` y `test_rutas_v2` (nombre y candado) |
| **M2.** Huellas no verificadas, tamaño en vez de huella, fecha de modificación demasiado amplia, enlaces vivos | cada archivo entra por su registro (con el sha256 que éste declara); los mensuales, por huella; por fecha de modificación sólo las órbitas antiguas de TROPOMI y GEOS-CF (T1-4); ACAG sin evento queda fuera; el armado **copia** lo que entra a `insumos_red2/congelados` (sólo lectura), calcula el sha256 al copiar y se detiene sin dejar nada si no calza | `test_panel_red2_v2.InventarioTests` (4) |
| **M3.** Sin la copia de MERRA-2 2026-10 | `panel_red2_v2.COPIAS_DE_CORTE`: copia del disco interno (archivo 6c329805…, su manifiesto 367b4d36…, `SHA256SUMS.txt` 16726973…); si el archivo de /Volumes cambió después del corte, entra la copia (T3) | `InventarioTests.test_reglas_de_registro` y `test_congela_copiando_con_su_huella` |
| **M4.** Convención de la etiqueta en hora civil | no está documentada: `verificar_serie` da el veredicto con `fin` y con `inicio_mas_1h`, y la elección la hace la regla T4 del autor (§3.1) | `test_reloj_sinca_v2`: `test_civil_inicio_mas_1h_el_original_si_la_ve` (la de c9), `test_civil_fin_el_original_no_la_ve`, `test_la_convencion_se_exige_si_hay_hora_civil`, `test_cada_convencion_vuelve_al_utc_verdadero`, `test_sin_convencion_no_convierte_anios_civiles` |
| **M5.** La propuesta no decía qué rompe | §5: cada archivo sellado que cambia, qué prueba rompe y su reemplazo, todo en `CAMBIOS_AL_CODIGO_SELLADO.md`, probado en una copia con todo aplicado | los reemplazos (hoy 70) aplicados a una copia temporal: §5.3 |
| 1. Decisiones de la traducción sin citar | `contrato.enmiendas[2].decisiones_de_traduccion` (fdfbfa31… hasta el paso 0, T1 a T13, T11 a T13 [delegadas]; a0b970d2… desde la ratificación, §9.0) y `red_ampliada_v2.DECISIONES_TRADUCCION` | `test_red_ampliada_v2.test_decisiones_de_la_traduccion_citadas`; al aplicar, `test_config_v2.test_entrada_del_bloque_red_ampliada` |
| 2. «no informado» sin explicar | cuatro fichas (517, 518, 525, 533) sin calificación ni propietario: R10 no da regla y la desagregación es descriptiva; el armado escribe propietario, operador, red y calificación en `paneles/estaciones_red2.parquet` | `test_red_ampliada_v2.test_no_informado_explicado`, `test_panel_red2_v2.test_propietarios_registrados` |
| 3. Regímenes si PM2,5 y NO2 difieren | `panel_red2_v2.regimenes_comunes`: los tramos comunes se cortan en todo año en que cambia cualquiera de los dos; `paneles/regimenes_red2.json` | `test_panel_red2_v2.test_regimenes_comunes` |
| 4. El piloto contradecía R18 | reemplazos en `piloto_v2.py`: se corre igual y se registra, sin quinto recorte | al aplicar, `test_piloto_v2` (dos aserciones nuevas) |
| 5. Escrituras antes de la confirmación en git | `red_ampliada_v2.exigir_traduccion_confirmada` al inicio de todo programa de la red 2 que escribe (nodo `red_de_monitores` y archivos de la traducción rastreados y sin cambios) | `test_red_ampliada_v2.GuardaR22Tests`, `test_pliegues_red2_v2.test_nada_se_escribe_sin_la_traduccion_confirmada`, `test_derivado_red2_v2.test_no_publica_sin_la_traduccion_confirmada` |
| 6. `--sin-e2`, desagrupamiento sin población, huella del contraste opcional | `pliegues_red2_v2.comprobar_opciones` (antes de leer nada); `--contraste-sha256` obligatoria, y también el json lateral | `test_pliegues_red2_v2.test_opciones_que_no_fijan_a_medias`, `test_panel_red2_v2.test_huella_del_contraste_y_sus_series`, `test_unidades_v2.test_la_huella_del_contraste_es_obligatoria` |
| 7. Cláusula de la 518 | `red_de_monitores.fuera_por_coordenadas.clausula_518` y `red_ampliada_v2.CLAUSULA_518` | al aplicar, `test_config_v2` (la ruta existe) |
| 8. Pruebas que afirmaban más de lo que probaban | renombradas y acotadas: `test_el_maestro_del_24_no_se_usa`, `test_grilla_y_json_de_los_paneles_v1_intactos` | — |
| 9. Huellas de `_common.py`, `_manifiesto_satelital.py` y `_satellite_streaming.py` | en `panel_red2_v2.HUELLAS_CODIGO_V1`, verificadas antes de importar la v1 | `test_panel_red2_v2.test_codigo_v1_con_huella` |

### 3.1 Decisiones del autor del 2026-10-26

| Decisión | Implementación | Prueba |
|---|---|---|
| **T4.** Una sola convención civil para todo SINCA, antes del paso a UTC y sólo con las etiquetas de los días de cambio de hora; gana la que da `hora_civil` en más unidades en que la otra no (unidad de T9, §3.2); empate, también en cero, `inicio_mas_1h`; conteos y elegida al anexo | `reloj_sinca_v2.elegir_convencion` (unidad: la del veredicto de R7, estación × contaminante × año local, T9). `reloj_sinca_v2.py --derivado` escribe los dos conteos y la elegida en `resumen.json`, junto a la huella de los veredictos. `panel_red2_v2.reloj_y_su_huella` toma la convención de ahí: comprueba la huella, vuelve a calcular la elección con los veredictos y exige que sea la del resumen; `--convencion-civil` sólo puede confirmarla. El json del panel registra la elegida, los conteos y las huellas de los veredictos y del resumen. El reloj sólo lee `ts_local` y `hora_repetida_en_fuente`, ningún valor | `test_reloj_sinca_v2.EleccionT4Tests` (4); `test_panel_red2_v2.test_reloj_de_su_carpeta_y_vuelto_a_calcular` |
| **T5.** Las 10 teselas del catálogo MAIAC se registran antes del armado con su sha256; entran sólo las de archivo anterior al corte; el registro va al anexo | `panel_red2_v2.registro_catalogo_maiac` (ruta, bytes, fecha del archivo, sha256; `huella_teselas`) y `registrar_catalogo_maiac` (`--registrar-catalogo-maiac`): escribe `insumos_red2/registro_catalogo_maiac.json` en la raíz v2 (junto al inventario y a `congelados.json`), después de la confirmación en git y una sola vez. El inventario toma las teselas de ahí (fuera las que no estén o sean posteriores al corte, anotadas); al congelar se compara cada tesela con su sha256; el armado se detiene sin el registro, y su sha256 va al json del panel | `test_panel_red2_v2.InventarioTests.test_catalogo_maiac_registrado_t5` |
| **T6.** ≈ 232 GB de la copia congelada en el disco interno | ya estaba así: `insumos_red2/congelados` en la raíz v2 | `InventarioTests.test_congela_copiando_con_su_huella` |
| **T7.** Revisión nueva de las correcciones y de T4 y T5 antes de aplicar; se aceptan las diferencias del §8.6 y la lectura de R21 | registrado en `contrato.enmiendas[2].decisiones_de_traduccion` y `red_ampliada_v2.DECISIONES_TRADUCCION` (fdfbfa31… hasta el paso 0; a0b970d2… desde la ratificación, §9.0), con su alcance literal: las diferencias que listaba entonces el §8.6 (programas propios para la red 2; `catalogo_sinca` y `metricas_v2` sin cambios) y la lectura de R21; lo agregado después lo cubre T12 (§8.16) | `test_red_ampliada_v2.test_decisiones_de_la_traduccion_citadas`; al aplicar, `test_config_v2.test_entrada_del_bloque_red_ampliada` |

### 3.2 Segunda revisión independiente y decisiones T8 a T10

| Hallazgo | Arreglo | Prueba |
|---|---|---|
| **Mayor 1.** T4 no quedaba atado a «todo SINCA» ni al derivado del panel | `reloj_sinca_v2.ejecutar_reloj`: para escribir la elección exige 2000-2026, los tres contaminantes y, desde la tercera revisión (§3.3), el derivado completo de la red 2; registra las raíces y cada serie (estación, contaminante, versión y sha256 de su `observaciones.parquet`) y la base de zonas horarias; comprueba la lista cerrada antes de leer los maestros; se escribe una sola vez. `panel_red2_v2.reloj_y_su_huella` exige esas mismas series (`series_con_huella` del `--derivado` del panel). Desde la tercera revisión (§3.3), además, el panel vuelve a calcular la tabla y toma las series evaluadas del resumen del reloj: una serie que el reloj no registró, o un año con 720 etiquetas o más sin fila en la tabla, detiene el armado (`observaciones_desde_derivado`); la serie sin ningún año evaluable sigue la regla general y queda contada | `test_reloj_sinca_v2.EjecutarRelojTests` (7 al cerrar la cuarta revisión y 10 desde la quinta, entre ellas el subconjunto, la raíz parcial, la independencia de los valores y las dos paradas de la escritura única); `test_panel_red2_v2.test_reloj_de_su_carpeta_y_vuelto_a_calcular` (subconjuntos de años, contaminantes, series, otra versión, otra raíz, otra corrida) y `test_serie_sin_veredicto_detiene` |
| **T9.** Unidad de los votos | `elegir_convencion` cuenta estación × contaminante × año local; una unidad repetida es un error | `EleccionT4Tests.test_la_unidad_es_la_del_veredicto_de_r7` (con la lectura anterior habría ganado la otra convención) |
| **Mayor 2.** R6, «rige la segunda corrida», no se exigía | `panel_red2_v2.contraste_y_su_huella`: el CSV en `<raíz v2>/unidades_red2/`, su lateral obligatorio con `schema` y `sha256_csv` igual a la huella (desde la tercera revisión, también la primera corrida con sus cambios y las mismas series que lee el panel: §3.3); `contraste_unidades_v2.publicar_una_vez`: una sola vez, después de la compuerta; la corrida comprueba la lista cerrada antes de leer los maestros y registra en el lateral las series y los archivos CAMS con su sha256 | `test_panel_red2_v2.test_huella_del_contraste_y_sus_series` (la primera corrida, sin lateral o fuera de la raíz, se rechaza); `test_contraste_unidades_v2.PublicacionTests` |
| **Mayor 3.** R16 y R17: nada comprobaba que rija lo calculado | `pliegues_red2_v2.exigir_lo_calculado`, llamado por `exigir_registro`: el bloque más influyente de la configuración tiene que ser el calculado, y `criterio.valor`, los tramos comunes de `regimenes_red2.json`, cuya huella registra el anexo (`registro_de_la_red.regimenes`) | `test_pliegues_red2_v2.test_rige_lo_calculado_r16_r17` |
| **Mayor 4 / T8.** R5: la huella de `afg_lib.py` | `derivado_red2_v2.SHA_AFG` (4391787a…) y `verificar_afg`; las huellas del árbol de sintaxis (v1: 8188ae3f… y 3eff1519…, Python 3.14.3; `amb_v2`: 877fb0f5… y 04734f63…, Python 3.11.16) quedan como procedencia; también en la configuración | `test_derivado_red2_v2.test_afg_lib_por_el_sha256_del_archivo` |
| **Mayor 5.** R22 y la geometría | `scripts_pipeline/geometria_sinca_ampliacion.py` (c1153b63…), `scripts_pipeline/descargar_sinca_ampliacion.py` (d7724723…, v1.1.0) y sus dos pruebas, entonces sin rastrear, entran en `ARCHIVOS_TRADUCCION` (también las pruebas nuevas); desde la tercera revisión, también `scripts_pipeline/descargar_sinca_meteorologia.py` (0942c4d0…), que el descargador importa y cuya huella registra, y su prueba `scripts_pipeline/tests/test_descargar_sinca_meteorologia.py` (d1ec5375…): sin ellos, el descargador y su prueba no corren desde git; ese módulo sólo importa `_common.py` (rastreado), no `_meteo_http_parallel.py`. No tienen rutas personales ni el correo; el espejo los tiene iguales. Procedencia de la descarga: la v1.1.0 sólo produjo `actualizacion_configuradas/manifiesto_descarga.csv` (330 filas); los manifiestos de las estaciones nuevas de la lista cerrada (`manifiesto_descarga.csv`, 167 filas, y `manifiesto_descarga_otras_series.csv`, 1.076) registran `script_version` 1.0.0 con sha256 647f5518…, una versión que no está en git ni junto al código (y el catálogo de la lista cerrada registra otra huella con la misma versión, 93f20aeb…): desde la cuarta revisión, las dos huellas de la v1.0.0 y la de la v1.1.0, con lo que produjo cada una, están en `red_de_monitores.procedencia_descarga` y en `red_ampliada_v2.PROCEDENCIA_DESCARGA` (si se recupera del historial de versiones del Drive, se confirma con esa huella; si no, el anexo la declara perdida) | `test_red_ampliada_v2.test_archivos_de_la_traduccion`; el descargador y el módulo que importa, en `SELLADOS` |
| Menor 2 | la clave de MERRA-2 era la huella del manifiesto: ahora `sha256_manifiesto` (367b4d36…) y `sha256_SHA256SUMS` (16726973…) | — |
| Menor 3 | el texto de la huella del Complemento dice cómo se obtiene: lo anterior al bloque, sin los saltos finales y terminado en uno | al aplicar, `test_config_v2` |
| Menor 4 | textos viejos: el catálogo MAIAC ya no está «pendiente del autor»; con la red 2, `a2_fuente_red2_float64` en lugar de `a2_fuente_v1_float64`; `protocolos.manifiesto.vigente` dice que deja de ser el vigente; el enlace MAIAC por estación no tiene efecto, porque `_features` lee MAIAC por celda | — |
| Menor 5 | `ejecutar` se detiene sin el registro MAIAC antes de leer nada; `leer_registro_maiac` exige el corte | `test_ejecutar_sin_registro_maiac_se_detiene`; `test_catalogo_maiac_registrado_t5` |
| Menor 6 | `test_hoy_no_esta_confirmada` se salta sola cuando la traducción ya está en git | — |
| Menor 7 | el reloj comprueba la lista cerrada y registra la base de zonas horarias: en `amb_v2` cada zona sale de la carpeta zoneinfo del entorno (tzdata de conda 2026c; America/Santiago fd006953…), la v1 usó la del sistema (d020f0d7…); las 132 horas especiales de 2000-2026 coinciden (huella 96a7b7cb…); desde la tercera revisión el paso a UTC usa la misma base (`ZoneInfo`, §3.3) | `EjecutarRelojTests.test_registra_las_series_y_se_escribe_una_vez` |
| Menor 8 | con la red 2, `correr_v2` exige la bandera de calidad y `calidad_v2.cargar_bandera` la compara con `calidad_sha256` del json del panel (reemplazos en CAMBIOS) | al aplicar, `test_calidad_v2.test_la_bandera_de_la_red_2_por_su_huella` |
| Menor 9 | `fijar` compara el original con f001d48c… antes del renombre de R13 | `test_una_sola_fuente_y_reemplazo_de_r13` |
| Menor 10 | §8.7: la segunda corrida lee desde el derivado | — |
| Menor 11 | TROPOMI por fecha de modificación: `panel_red2_v2.TROPOMI_MTIME_ANIOS` permite limitarlo por año de adquisición; T11 [delegada] lo deja sin límite (None), con los 146 de 2024 dentro (§9) | `test_tropomi_por_fecha_limitable` |
| Menor 12 | pendientes de §9 y la compuerta también en el espejo: `red_ampliada_v2.verificar_espejo` (mismos bytes y confirmados en el git del espejo) | `test_red_ampliada_v2.test_el_espejo_tambien` |
| **T10.** La conversión a hora civil | en `reloj_sinca_v2.convertir` y en el panel, no en `preparar_sinca_modelado.py`; diferencia aceptada (§8.6 d) | — |
| Prueba pedida | la elección de T4 no depende de los valores | `EjecutarRelojTests.test_la_eleccion_no_depende_de_los_valores` |

### 3.3 Tercera revisión independiente y T11 [delegada]

| Hallazgo | Arreglo | Prueba |
|---|---|---|
| **Mayores 1 y 10.** «Todo SINCA» no estaba atado al conjunto de estaciones: una raíz parcial, el derivado v1 o una corrida interrumpida pasaban por el reloj y por el panel | `red_ampliada_v2.series_esperadas_red2` (series de `series_contrato` en PM2,5, NO2 y O3 de las estaciones de los maestros de R8; hoy 262: 109, 79 y 74, igual al plan de `derivado_red2_v2`) y `exigir_la_red_2`, que muestra la diferencia; `derivado_red2_v2.exigir_derivado_completo`: una sola raíz, su última corrida con `progreso.json` en «complete_for_selected_scope», el conjunto de R2 y las versiones que publicó esa corrida. Lo exigen el reloj al escribir y `panel_red2_v2.ejecutar` antes de escribir nada; el json del panel registra la corrida (`derivado`) y la red por contaminante frente a `RED_ESPERADA`, con las estaciones que salen sin celda y las que salen por R3 (cero horas) (`red`) | `test_reloj_sinca_v2.EjecutarRelojTests.test_una_raiz_parcial_no_escribe` (también una corrida sin terminar y dos raíces); `test_panel_red2_v2.test_el_panel_rechaza_una_raiz_parcial` (por `ejecutar`); `test_red_ampliada_v2.test_series_esperadas_de_la_red_2` y `DatosRealesTests.test_series_esperadas_reales` |
| **Mayor 2** y menores 16, 17, 18, 36 y 45. El panel aceptaba cualquier par veredictos + resumen; la parada «serie sin veredicto» no se activaba; regiones y política inyectables al escribir; dos bases de zonas | `panel_red2_v2.reloj_y_su_huella` exige `<raíz v2>/verificacion_reloj_sinca_red2/veredictos.parquet`, el `schema` del reloj, `sha256_veredictos` y `huella_veredictos_contenido`, la política que lee el panel, la misma corrida del derivado, que toda fila sea de una serie registrada y tenga la zona de su región, la misma base de zonas (horas especiales, archivos de zona y biblioteca de la conversión) y que la tabla sea la que vuelve a dar `verificar_red` con las series; `observaciones_desde_derivado` toma las series del resumen del reloj y se detiene si un año con 720 etiquetas o más no tiene fila; el reloj no acepta `region_de` ni `politica` al escribir y registra la política leída, la región y la zona de cada serie; `utc_civil` pasa `ZoneInfo(zona)` a pandas (misma base que el veredicto; antes pandas resolvía con pytz) y `base_de_zonas` registra la biblioteca | `test_panel_red2_v2.test_reloj_de_su_carpeta_y_vuelto_a_calcular` (par hecho a mano en otra carpeta, tabla editada en su carpeta, sin C1, otra zona, otro esquema, otra política, otra base de zonas, otra corrida), `test_serie_sin_veredicto_detiene`; `test_reloj_sinca_v2.test_region_o_politica_dadas_no_escriben`, `test_la_conversion_usa_zoneinfo` |
| **Mayores 3, 6, 8, 9, 11 y 13** y menor 35. T11 no estaba traducida y la huella de las decisiones era la vieja | la huella de entonces (49c617ab…; luego fdfbfa31…, §3.6, y a0b970d2… desde la ratificación, §9.0) y T11 [delegada] en `red_ampliada_v2.DECISIONES_TRADUCCION`, en `contrato.enmiendas[2].decisiones_de_traduccion` y en el reemplazo de `test_config_v2` (que exige T11 y su marca); T4 con la unidad de T9; `insumos_de_hoy.tropomi_por_fecha` sin «pendiente del autor»; comentario de `TROPOMI_MTIME_ANIOS`; `resumen_inventario` cuenta por año de adquisición lo que entra por fecha de modificación, con la huella de la lista, y el anexo lo registra (`registro_de_la_red.tropomi_por_fecha`); §9: T11 decidida y su ratificación, pendiente | `test_red_ampliada_v2.test_decisiones_de_la_traduccion_citadas` (pasa de nuevo); `test_panel_red2_v2.test_tropomi_por_fecha_limitable` |
| **Mayores 4, 5 y 15** y menores 19, 20, 23, 24 y 31. La segunda corrida del contraste no quedaba atada a las series del panel ni registraba siempre los cambios | `contraste_y_su_huella` recibe las series del panel y exige en el lateral la primera corrida (ca0805ae…) con su lista de cambios, NO2 y O3, las mismas raíces y las mismas series; devuelve la huella del lateral, que va al json del panel (`unidades.segunda_corrida`) y al anexo; `contraste_unidades_v2.main` exige la traducción confirmada antes de leer nada, y para escribir NO2 y O3 y `--primera` comprobada por su huella; `publicar_una_vez` exige el lateral completo y, si una corrida se cortó entre el CSV y el lateral, lo completa con el mismo CSV o se detiene («corrida incompleta»); `unidades_v2`: rige la segunda corrida y el armado rechaza la huella de la primera | `test_panel_red2_v2.test_huella_del_contraste_y_sus_series` (también el derivado rearmado); `test_contraste_unidades_v2.PublicacionTests` (4: sin la primera, cortada, `main`); `test_unidades_v2.test_el_armado_rechaza_la_primera_corrida` |
| **Mayor 7** y menor 30. Al escribir el anexo los tramos y el bloque calculados, cuatro pruebas selladas fijaban los de la Enmienda 1 | ahora, dentro de la traducción (T7): `_sintetico_v2.anexo_de_la_red` da, con el anexo escrito, los tramos comunes de `regimenes_red2.json` y el bloque de `pliegues_v2_red2.json` (comprobados por las huellas del anexo) y, sin él, None; reemplazos en `test_metricas_v2`, `test_config_v2` (los cinco regímenes, el bloque y la entrada del bloque, que ya no exige el registro vacío) y `test_decision_v2`. La cuarta revisión encontró tres aserciones más en `test_correr_v2` y una dependencia en `factibilidad_v2` (mayor 1 y menor 9, §3.4) | al aplicar, las cuatro pruebas, con y sin anexo; desde la cuarta revisión, todas las pruebas de la v2 con el anexo simulado (§5.3) |
| **Mayores 12 y 14** y menores 29, 32 y 37. A la compuerta de R22 le faltaban archivos | `ARCHIVOS_TRADUCCION` suma las 13 pruebas selladas que cambia CAMBIOS (`_sintetico_v2` y `test_{rutas, manifiesto, factibilidad, calidad_artefacto, calidad, pliegues, correr, piloto, vecindario, config, metricas, decision}_v2`), `descargar_sinca_meteorologia.py` con su prueba y `config/componentes_compartidos.json`, que se regenera en el mismo commit (desde la cuarta revisión, la compuerta compara la huella de cada archivo con la que registra: `verificar_componentes`, §3.4) | `test_archivos_de_la_traduccion`: exige los módulos y pruebas nuevos, el contrato, la configuración, cada «## `…`» de CAMBIOS (leído del archivo), los de `scripts_pipeline` y `componentes_compartidos.json` |
| Menores 21 y 22. T8 en dos lugares sin comparar, y sin exigir en quien lee | `derivado_red2_v2.contrato_de_la_version`: el reloj, el contraste y el panel exigen en el `manifest.json` de cada versión el contrato, `afg_semantics.file_sha256` = SHA_AFG y `code_sha256` = SHA_PREPARADOR, y registran por serie la sintaxis de `afg_lib` con su Python | `test_reloj_sinca_v2.test_series_con_huella_exige_el_preparador_t8`; `test_derivado_red2_v2.test_t8_igual_en_el_codigo_y_en_la_configuracion` y, de punta a punta, con los manifiestos reales del preparador; al aplicar, `test_config_v2.test_entrada_del_bloque_red_ampliada` |
| Menor 25. `exigir_lo_calculado` no comparaba el rótulo | compara el tramo completo, con `disponibilidad` | `test_pliegues_red2_v2.test_rige_lo_calculado_r16_r17` (rótulo falso) |
| Menor 26. `decidir` no pasaba por el anexo | reemplazo en `correr_v2.decidir`: con el nodo, `exigir_registro` y el bloque de cada evidencia igual al de la configuración (R16) | al aplicar, `test_correr_v2.RedAmpliadaTests.test_decidir_exige_el_anexo_y_el_bloque` |
| Menores 27 y 44. La bandera obligatoria se podía saltar | reemplazos en `correr_v2`: `Contexto.desde_disco` se detiene con el nodo y sin calidad, y `main` rechaza `--sin-calidad`; en `piloto_v2.estimar_y_publicar`, con el nodo y sin la bandera no se estima el plan | al aplicar, `test_correr_v2.RedAmpliadaTests` (3) y `test_piloto_v2.PlanTests.test_con_la_red_ampliada_exige_la_bandera` |
| Menores 28 y 47. Sin `pliegues_v2.json`, `fijar` publicaba sin el evento de R13 | `pliegues_red2_v2.respaldo_de_r13` busca el respaldo por su sha256 (en la raíz real hay otros respaldos de la Enmienda 1); si lo hay, el evento «reemplazo» apunta a él; si no, se detiene (`permitir_sin_r13`, sólo para las pruebas) | `test_pliegues_red2_v2.test_r13_si_el_original_ya_no_esta` |
| Menores 33, 34 y 41. §8 mal numerado y §8.6 inexacto | la lista va 6 y 7 en orden; §8.6 (a) y (c) corregidos | — |
| Menor 38. La lista cerrada antes de los maestros no tenía prueba | una prueba por programa con una lista cerrada que no se cumple y los maestros prohibidos | `test_reloj_sinca_v2.test_lista_cerrada_antes_de_los_maestros`; `test_contraste_unidades_v2.PublicacionTests.test_main_no_lee_nada_antes_de_tiempo` |
| Menor 39. La parada sin registro MAIAC no se distinguía | la prueba usa un inventario hecho con el registro de T5 y afirma el mensaje exacto | `test_panel_red2_v2.test_ejecutar_sin_registro_maiac_se_detiene` |
| Menor 40. El anexo era un paso sin código | `pliegues_red2_v2.registro_de_la_red_desde_artefactos` lo arma de los artefactos (reloj, contraste, registro MAIAC, inventario, copia congelada, json de los paneles con sus banderas y duplicados, lista cerrada y T11), comprobando que cada json de panel declare las mismas huellas; `exigir_registro` lo compara campo por campo (`verificar_registro_de_la_red`); la configuración trae la estructura de cada entrada | `test_pliegues_red2_v2.test_el_anexo_es_el_de_los_artefactos`; desde la cuarta revisión, el anexo completo con `--anexo` (§3.4) |
| Menor 42. El archivo de decisiones no tenía ancla en git | entra en el commit del espejo con la traducción, con su huella final (después de agregar, si la da, la ratificación de T11, T12 y T13); AP no puede llevarlo (`/auditoria/` está excluida). Desde la cuarta revisión la compuerta lo exige rastreado, sin cambios y con su sha256 en el git del espejo, con el bloque y las decisiones del autor (`ARCHIVOS_DEL_ESPEJO`) | §9 y §11.1; `test_red_ampliada_v2.CompuertaConGitTests` |
| Menor 43. Huellas declaradas que nada comprobaba | prueba de `red_de_monitores.codigo` contra cada archivo; el descargador y el módulo que importa, en `SELLADOS`; `COPIAS_DE_CORTE` trae `sha256_sumas` (16726973…) y `copia_de_corte` lo comprueba | `test_red_ampliada_v2.test_huellas_del_codigo_nuevo_declaradas`; `InventarioTests.test_copia_de_corte_con_sus_sumas` |
| Menor 46. Procedencia de la descarga de las nuevas | desde la cuarta revisión, en `red_de_monitores.procedencia_descarga` (= `red_ampliada_v2.PROCEDENCIA_DESCARGA`), con las dos huellas de la v1.0.0 y la de la v1.1.0; el anexo declara su estado (recuperada o perdida) | `test_red_ampliada_v2.DatosRealesTests.test_procedencia_de_la_descarga` |

### 3.4 Cuarta revisión independiente

Cada arreglo de código tiene una prueba que falla sin él: se comprobó revirtiéndolo en una copia aplicada (§5.3).

| Hallazgo | Arreglo | Prueba |
|---|---|---|
| **Mayor 1** (el mayor 7 seguía abierto). `config_pequena` copia de la configuración real el bloque más influyente y los regímenes; tres aserciones selladas de `test_correr_v2` fijaban los de la Enmienda 1 | reemplazos 2 a 4 de `test_correr_v2` en CAMBIOS: comparan con lo que rige, el bloque de `dc.regla_de_config(CFG)` y los ids de `mt.regimenes_de_config(CFG)`; ahora el anexo sí no toca pruebas (§9, 3) | en una copia con el anexo simulado (bloque RV y E004N084, tramos sin 2019-2024), todas las pruebas de la v2, `test_correr_v2` completo incluido (§5.3) |
| **Mayor 2.** Lanzada desde el espejo, la compuerta comparaba el espejo consigo mismo y no miraba AP | `red_ampliada_v2.par_de_repositorios`: el par AP y APH es el mismo se lance desde donde se lance; un espejo igual al repositorio se rechaza | `test_red_ampliada_v2.CompuertaConGitTests` (git real en dos repositorios temporales hermanos): un cambio sin confirmar en AP, o en el espejo, detiene la compuerta desde los dos lados; `test_el_par_no_depende_de_donde_se_lanza` |
| **Mayor 3** y menor 27. `test_archivos_de_la_traduccion` lee `propuesta_red_ampliada/`, que no entraba en el commit | los cuatro archivos de la carpeta en `ARCHIVOS_TRADUCCION` (`ARCHIVOS_PROPUESTA`); §2, §9 y §11.1: entran en el commit de AP y del espejo y no se borran | `test_archivos_de_la_traduccion` |
| Menor 4. Quien lee el derivado no comprobaba que la versión fuera la que publicó el preparador | `derivado_red2_v2.contrato_de_la_version`: `files` con el sha256 del `observaciones.parquet` que se lee (lo da `series_con_huella`, sin leer valores), `version` igual al nombre de la carpeta y a `digest(inputs)` (`digest_del_preparador`, la del preparador sobre el json) y la estación y el contaminante de la carpeta | `test_reloj_sinca_v2.test_series_con_huella_exige_el_preparador_t8` (parquet reemplazado después de publicarse, versión de otra carpeta, inputs alterados, otra estación); `test_derivado_red2_v2.test_digest_es_el_del_preparador`; los manifiestos sintéticos traen ahora `files` y la versión |
| Menores 5 y 32. Volver a correr el derivado sin cambios después del reloj trababa el armado para siempre | `derivado_red2_v2.corridas_equivalentes` y `panel_red2_v2.reloj_y_su_huella(…, raiz_derivado)`: vale otra corrida si las dos terminaron y publicaron exactamente las versiones que registra el reloj; el json del panel registra las dos; §11: el derivado no se vuelve a correr después del reloj | `test_panel_red2_v2.test_corrida_repetida_del_derivado` (también sin terminar y con otras versiones) |
| Menor 6. Fecha imposible en un docstring | 2026-10-26 | — |
| Menor 7. El contraste se aceptaba en cualquier lugar de `unidades_red2/` | `contraste_y_su_huella` exige `unidades_red2/contraste_unidades_cams_segunda.csv` y su lateral `contraste_unidades_cams_segunda.json` (los nombres de la escritura única) | `test_huella_del_contraste_y_sus_series` (otro nombre y subcarpeta, con un lateral hecho a mano) |
| Menor 8. «El derivado corre en amb_v2» no se exigía | `derivado_red2_v2.verificar_entorno` (Python 3.11.16 y entorno `amb_v2`) dentro de `verificar_afg`, registrado en `plan.json`; `contrato_de_la_version` exige el Python de `amb_v2`; las huellas del árbol de sintaxis siguen siendo procedencia (T8) | `test_derivado_red2_v2.test_el_derivado_corre_en_amb_v2`; un manifiesto de 3.14.3 en `test_series_con_huella_exige_el_preparador_t8` |
| Menor 9. `factibilidad_v2.fechas_de_medicion` dependía del tramo 2019-2024 | lectura de R19 (§8.9): la factibilidad no se vuelve a medir con la red 2 y sus fechas quedan fijadas por la Enmienda 1; reemplazo en `factibilidad_v2.py` (con el anexo, las toma de `criterio.valor_red_original`) y dos en `test_factibilidad_v2`; `red_de_monitores.factibilidad` | al aplicar, `test_factibilidad_v2.FechasTests` (prueba nueva con los tramos calculados) |
| Menor 10. La E2 de R15 no comprobaba la bandera ni el panel contra su json | `construir_manifiesto_red2`: al fijar, el json del panel es obligatorio, su `sha256` y su `calidad_sha256` se comparan con los archivos leídos y la bandera se alinea por estación y hora; `exigir_registro` compara `traza.insumos.calidad_<pol>` con `registro_de_la_red.calidad` | `test_pliegues_red2_v2.test_la_bandera_y_el_panel_por_su_json`; caso «otra bandera» en `test_el_anexo_es_el_de_los_artefactos` |
| Menores 11 y 18. Los regímenes no quedaban atados a los json de los paneles ni al manifiesto | `pliegues_red2_v2.verificar_regimenes` (`comunes` = `regimenes_comunes` de los `regimenes` de los json de los paneles, y `por_contaminante` igual a ellos) en `construir_manifiesto_red2`, `exigir_lo_calculado` y `registro_de_la_red_desde_artefactos` (entrada `regimenes`); `pliegues_v2_red2.json` copia los tramos con el sha256 de `regimenes_red2.json`, bajo `huella_pesos` (§8.10) | `test_los_regimenes_van_al_manifiesto` (el caso del revisor); caso nuevo en `test_rige_lo_calculado_r16_r17` |
| Menor 12. La prueba «sin el registro del anexo» de `test_correr_v2` no probaba esa parada | reemplazo 1 de `test_correr_v2`: afirma «anexo» en el mensaje, con un manifiesto que calza con el panel en disco | en la copia aplicada, quitando la línea de `exigir_registro` de `desde_disco`, la prueba falla (§5.3) |
| Menor 13. Ni la prueba ni el registro estaban atados a lo que hace `utc_civil` | `utc_civil` dice en `attrs["biblioteca_zona"]` qué tipo de zona usó de verdad; `base_de_zonas` registra eso, con una conversión de prueba | `test_la_conversion_usa_zoneinfo` (el cuerpo de `utc_civil` por AST y la zona como texto) |
| Menor 14. Dos guardas sin una prueba que falle sin ellas | `ejecutar_reloj` lee la política con `RUTA_POLITICA` explícita (si no, la prueba no la podía reemplazar) | `test_ejecutar_sin_registro_maiac_se_detiene` (registro de T5 presente e inventario sin él); `test_reloj_sinca_v2.test_la_politica_se_lee_por_su_huella` |
| Menores 15, 31 y 36. El archivo de decisiones no tenía guarda | `red_ampliada_v2.ARCHIVOS_DEL_ESPEJO` (el bloque, las decisiones del autor y las de la traducción, con su sha256, los que cita `contrato.enmiendas[2]`); `verificar_espejo` los exige rastreados, sin cambios y con su huella en el git del espejo | `CompuertaConGitTests.test_las_decisiones_sin_rastrear_en_el_espejo`, `test_el_espejo_tambien`, `test_decisiones_de_la_traduccion_citadas` |
| Menor 16. La ratificación de T11 no tenía plazo | §9 y §11.1: antes del commit de la traducción o, a más tardar, antes de publicar `insumos_red2/inventario.json`; si no llega, T11 rige tal como está. Desde el 2026-10-26 lo reemplaza T13 [delegada]: el armado no empieza hasta la ratificación de T11, T12 y T13 (§3.6, §9.0 y §11, paso 0) | — |
| Menor 17. Las SNIFA quedaban como «empresa» sin regla | «no informado», como las cuatro fichas que T1(3) no alcanza, con `nota_tipo` «SNIFA, sin ficha SINCA» (§8.11) | `test_propietarios_registrados`, `EstratoPropietarioTests` |
| Menor 19. `cobertura_conocida.red_ampliada` era sólo una remisión | el anexo escribe ahí, por contaminante, «n de las N estaciones no tienen ninguna fila validada» (`pliegues_red2_v2.texto_cobertura`) y `exigir_registro` lo compara con el manifiesto (`verificar_cobertura`); §8.6 (c) corregido | caso «R15» en `test_el_anexo_es_el_de_los_artefactos` |
| Menores 20 y 37. La lista de insumos «en el json del panel» | lectura declarada (§8.13): por referencia, con la huella de `congelados.json` y de `inventario.json`; el json del panel lo dice (`insumos.lista`) y la configuración lo describe así | — |
| Menor 21. O3 47,998 en el bloque, 47,9982 en el código | declarado en `unidades.masas_molares_nota` y en `unidades_v2` (§8.12). Desde el 2026-10-26, T12 [delegada] la corrige: la conversión usa 47,998, la literal de R6 (§3.6 y §8.12), y el contraste de la segunda corrida también, sin excepción (ronda 4 de verificación, menor 9: §3.7) | — |
| Menor 22. El orden de la configuración no era el del código | `red_de_monitores.orden` con el orden real y la lectura de «al cerrar el panel» (§8.8) | — |
| Menor 23. El plazo de la 518 se acortaba al inicio del armado sin decirlo | el camino para que entre entre el armado y el anexo, en `fuera_por_coordenadas.clausula_518` y `red_ampliada_v2.CAMINO_518` (§9) | `test_la_configuracion_repite_las_constantes_del_codigo` |
| Menores 24, 30 y 35. La procedencia de la descarga estaba sólo en la propuesta | `red_de_monitores.procedencia_descarga` = `red_ampliada_v2.PROCEDENCIA_DESCARGA`: las dos huellas de la v1.0.0 (647f5518… para los dos manifiestos, 93f20aeb… para el catálogo) y la de la v1.1.0 (d7724723…, la actualización), con lo que produjo cada una y su estado | `DatosRealesTests.test_procedencia_de_la_descarga` (sólo columnas y campos `script_*`) |
| Menor 25. Valores repetidos en la configuración sin comparar | prueba que compara los nodos de `red_de_monitores` con las constantes del código (lista cerrada, corte, rangos, masas molares, factores SNIFA, red esperada, estaciones nuevas, duplicados, copia de corte, procedencia y cláusula de la 518) | `test_la_configuracion_repite_las_constantes_del_codigo` |
| Menor 26. La compuerta no comprobaba `config/componentes_compartidos.json` | `red_ampliada_v2.verificar_componentes`, dentro de la compuerta: cada archivo de la traducción con su sha256 de hoy en un grupo «identico» | `CompuertaConGitTests.test_componentes_sin_regenerar` |
| Menor 28. Dos mutaciones de «rige la segunda corrida» no detectadas | la subprueba de `--primera` corre con la lista cerrada cumplida y afirma «no es el registrado»; `panel_red2_v2.unidades_del_armado`, con su prueba | `test_main_no_lee_nada_antes_de_tiempo`; `test_el_armado_rechaza_la_primera_corrida` |
| Menor 29. La rama «modificado» de `estado_git` sin git real | — | `CompuertaConGitTests` |
| Menor 33. Sin camino para retomar después de congelar | `panel_red2_v2.congelar_o_retomar` y `retomar_congelados`: se reusa la copia si `congelados.json` calza con su huella y con el inventario de ahora y cada archivo con su sha256, vuelto a calcular (sólo lectura, sin archivos de más); `inventario.json` es de escritura única (`publicar_inventario`) | `InventarioTests.test_retomar_la_copia_congelada` |
| Menor 34. El paso 4 seguía siendo una edición a mano | `pliegues_red2_v2.py --anexo`: `anexo_desde_artefactos` arma el bloque completo (registro con pliegues y regímenes, bloque, tramos y cobertura) y `con_el_anexo` lo pone donde lo leen los programas; `exigir_registro` lo valida antes de mostrarlo; no escribe nada | `test_la_opcion_anexo_lo_muestra_validado`; `cfg_del_anexo` de las pruebas usa el programa |

### 3.5 Quinta revisión independiente

Cada arreglo de código tiene una prueba que falla sin él: se comprobó revirtiéndolo en una copia aplicada (§5.3).

| Hallazgo | Arreglo | Prueba |
|---|---|---|
| **Mayores 1 y 2.** Los artefactos nuevos no cumplían la procedencia del §0 («cada artefacto registra el commit, el hash del código, el sha256 de cada insumo, la versión de cada biblioteca, los hilos y las semillas»): sólo `pliegues_red2_v2` llamaba a `_traza_v2.traza`; nada decía con qué commit ni con qué código se hizo cada uno, y un commit nuevo a mitad del armado (T11 o la 518) no quedaba a la vista | `red_ampliada_v2.traza_red2`: la `_traza_v2.traza` (commit, huella del código v2, contrato, configuración, sha256 de cada insumo, bibliotecas, Python, hilos y semillas) más `codigo_red2` (la huella de cada módulo de la red 2 tal como corre) y `traduccion` (`traduccion_de`: el último commit que tocó los archivos de la traducción en AP y en el espejo, los HEAD de los dos, el estado de la compuerta, que ya no se descarta, y la huella conjunta de esos archivos). La llevan el `resumen.json` del reloj, el lateral de la segunda corrida, el registro MAIAC, `inventario.json`, `congelados.json`, los json de los paneles y de O3 y `regimenes_red2.json`; el `plan.json` del derivado registra además la huella de `derivado_red2_v2.py` (`plan_con_procedencia`). No entra en las comparaciones de escritura única. `pliegues_red2_v2.traduccion_comun` exige que los nueve artefactos que lee el anexo declaren la misma traducción y la lleva al anexo (`registro_de_la_red.traduccion`) | `test_reloj_sinca_v2.test_registra_las_series_y_se_escribe_una_vez`, `test_contraste_unidades_v2.test_una_vez_y_la_acepta_el_panel`, `test_panel_red2_v2.test_catalogo_maiac_registrado_t5`, `test_retomar_la_copia_congelada`, `test_ejecutar_registra_la_procedencia` (el armado de punta a punta, con el código v1 simulado, y el anexo sobre lo que escribió), `test_derivado_red2_v2.test_el_plan_registra_su_codigo_y_su_procedencia`, `test_red_ampliada_v2.TrazaRed2Tests` y `CompuertaConGitTests.test_la_traduccion_de_cada_artefacto`; `test_pliegues_red2_v2.test_el_anexo_es_el_de_los_artefactos` (sin traza, otro commit, commit desconocido) |
| Menor 3. Nada fijaba la base de zonas horarias: con otra base el reloj elegía por empate y el panel lo aceptaba | `reloj_sinca_v2.HORAS_ESPECIALES` (132 horas de 2000-2026, 96a7b7cb…) y `exigir_base_de_zonas`: el reloj que escribe se detiene antes de leer los maestros y las series, y `panel_red2_v2.reloj_y_su_huella` también; el origen de cada zona se registra con su ruta completa sin rutas de usuario (`origen_portable`) | `test_reloj_sinca_v2.BaseDeZonasTests` (otra base: America/Santiago copiada de America/Punta_Arenas), `EjecutarRelojTests.test_otra_base_de_zonas_no_escribe`; caso en `test_panel_red2_v2.test_reloj_de_su_carpeta_y_vuelto_a_calcular` |
| Menor 4. Faltaba declarar el límite del reloj en los años sin cambio de hora | declarado en `red_de_monitores.reloj.limite` y en §8.15; `reloj_sinca_v2.anios_sin_cambio_de_hora`, `sin_transiciones_junto_a_civil` y `limite_sin_transiciones`: el resumen del reloj lo declara, el panel lo vuelve a calcular y lo lleva a su json (`reloj.limite_sin_transiciones`) y el anexo lo registra (`registro_de_la_red.reloj.sin_transiciones_junto_a_civil`); la regla no cambia | `test_reloj_sinca_v2.LimiteR7Tests`; casos «otro límite» y «sin el límite» en `test_reloj_de_su_carpeta_y_vuelto_a_calcular` |
| Menor 5. Las dos paradas de la escritura única del reloj no tenían prueba; «6» en vez de «7» | `test_ya_escrito_con_otras_series_se_detiene` y `test_archivos_sin_su_resumen_se_detiene`; §3.2 corregido | las dos pruebas |
| Menor 6. `test_main_no_lee_nada_antes_de_tiempo` no detectaba que se quitara una guarda | cada guarda corre con la lista cerrada cumplida, los maestros y las series prohibidos, y se afirma su mensaje (la compuerta, con un texto propio) | la misma prueba |
| Menor 7. Nada exigía los archivos CAMS en el lateral | `contraste_unidades_v2.exigir_cams` (al menos un archivo, con ruta y sha256 de 64 hexadecimales) en `exigir_lateral_completo` y en `panel_red2_v2.contraste_y_su_huella` | casos nuevos en `test_sin_la_primera_corrida_no_se_publica` y `test_huella_del_contraste_y_sus_series` |
| Menores 8 y 17. T8 sin «el derivado corre en amb_v2»; faltaba T2 | `red_ampliada_v2.DECISIONES_TRADUCCION`: T8 completo (con 4391787a…) y T2 | `test_red_ampliada_v2.test_decisiones_iguales_en_el_codigo_y_en_la_configuracion` (lo esencial de cada Tn, en el código y en la configuración) |
| Menor 9. El contaminante del manifiesto no tenía prueba | — | caso «misma estación, otro contaminante» en `test_series_con_huella_exige_el_preparador_t8` |
| Menor 10. «No copió» sin prueba | — | dos casos en `test_rige_lo_calculado_r16_r17` (otro sha256 y otros tramos, con las huellas propias recalculadas) |
| Menores 11 y 14. `con_el_anexo` pisaba `red_original`; el «se dice» de R16 no quedaba en la configuración | `con_el_anexo`: `red_original` con `setdefault` y `aviso` por protocolo (`aviso_r16`: calculado, nombrado por la Enmienda 1 y si cambia); `exigir_lo_calculado` exige `red_original` = RM/E004N083 y el `aviso` del manifiesto | `test_el_anexo_se_puede_aplicar_dos_veces`; casos «aviso falso» y «red_original pisado» en `test_rige_lo_calculado_r16_r17` |
| Menor 12. El piloto podía correr con el anexo sin confirmar | `exigir_registro` → `red_ampliada_v2.exigir_config_confirmada`: `config_v2.json` rastreado y sin cambios en AP y, con los mismos bytes, en el espejo (`--anexo`, que no ajusta nada, lo valida en memoria) | `test_pliegues_red2_v2.test_sin_la_configuracion_confirmada_no_corre`; `CompuertaConGitTests.test_la_configuracion_confirmada_en_los_dos` (git real) |
| Menores 13 y 24. R19, «no se vuelven a medir», no lo hacía cumplir nada | reemplazos 2 y 3 de `factibilidad_v2.py` en CAMBIOS (`exigir_sin_red_ampliada` en `medir` y `publicar`) y reemplazo 3 de `test_factibilidad_v2` | al aplicar, `test_factibilidad_v2.RedAmpliadaR19Tests` (falla sin cada uno de los dos) |
| Menor 15. T11, «el anexo lista las órbitas», se leía por referencia sin declararlo | declarado en §8.14 y en `registro_de_la_red.tropomi_por_fecha.regla` | — |
| Menor 16. «§8.6 e)» | «§8.13» | — |
| Menor 18. Las pruebas de limpieza cubrían menos de lo necesario | `test_archivos_de_la_traduccion`: la revisión de las rutas personales se salta sólo en las pruebas selladas de CAMBIOS (las de `tests/`), y busca correos (usuario, arroba y dominio) en todos los archivos de la traducción, el módulo meteorológico, su prueba y `config/componentes_compartidos.json` incluidos | la misma prueba |
| Menor 19. Cinco archivos sin rastrear bajo `scripts_modelo_1km/v2` (y `meteorologia_v2.py` en el espejo) detendrían `verificar_sellado` | declarado en §11.1 y §11.4 | — |
| Menor 20. `config/componentes_compartidos.json` lo editan otros frentes | declarado en §11.1 y §11.2 | — |
| Menor 21. Retomar exigía el mismo texto de `inventario.json` | `panel_red2_v2.huella_de_lo_que_entra`: al retomar se compara sólo lo que entra (con `bytes` estable aunque aparezca una fila sin tamaño); §11.2.5 | caso «un archivo nuevo que no entra» en `test_retomar_la_copia_congelada` |
| Menor 22. El estado de la procedencia de la descarga no lo registraba nadie | entrada propia `registro_de_la_red.procedencia_descarga` (en_git, recuperada con su ruta y sha256, o perdida), que arma `pliegues_red2_v2.procedencia_descarga_desde_artefactos` y compara `verificar_registro_de_la_red`; la prueba de la configuración ya no compara «estado» | casos en `test_el_anexo_es_el_de_los_artefactos` (copia recuperada); `test_la_configuracion_repite_las_constantes_del_codigo` |
| Menor 23. `CAMINO_518` movía la carpeta `paneles` entera | `red_ampliada_v2.ARCHIVOS_RED2_EN_PANELES` nombra uno por uno los archivos de la red 2; el camino suma el registro MAIAC (T5) y los pliegues con `--reemplazar --motivo «R8, 518»` | `test_panel_red2_v2.test_los_archivos_de_la_red_2_en_paneles` |
| Menor 25. El camino de T11 después del commit | §9.0 | — |
| Menor 26. `_features.py:41` | `_features.py:40`; SO2 sólo del programa del contraste | — |

### 3.6 Rondas de verificación de la traducción (2026-10-26) y T12 y T13 [delegadas]

Cada arreglo de código tiene una prueba que falla sin él (§5.3).

| Hallazgo | Arreglo | Prueba |
|---|---|---|
| **Mayor (ronda 3, confirmado por un escéptico).** «Derivado completo» y «todo SINCA» sólo comparaban el conjunto estación × contaminante y las versiones de la última corrida, no las fuentes ni la ventana de cada versión: con un derivado auténtico pero parcial (`ins["grupos"]` filtrado o `process_series(…, until=…)`), el reloj escribía otra elección de T4 (`inicio_mas_1h` en vez de `fin`) y el panel la aceptaba, contra T4, R4 y R2 | `derivado_red2_v2.exigir_derivado_completo`, que usan el reloj y el contraste al escribir y el panel: la raíz tiene que ser `destino_por_omision(datos)`; el `plan.json` de la corrida, el de `derivado_red2_v2 --ejecutar`, con la huella rastreada de `derivado_red2_v2.py` (`exigir_plan_de_la_corrida`); y cada versión, `inputs.since` e `inputs.until` nulos e `inputs.sources` igual, por (`relative_path`, `sha256`), a sus filas en los tres manifiestos de la lista cerrada (`fuentes_de_la_red_2`, `exigir_fuentes_y_ventana`), y si no, se detiene mostrando la diferencia; desde la ronda 4 (§3.7), en todas las columnas de identidad de la fila y con los conteos de filas anclados a esos manifiestos. En la configuración, `red_de_monitores.calidad.derivado.lectura_completa` | `test_reloj_sinca_v2.EjecutarRelojTests.test_un_derivado_parcial_no_escribe` (el caso del revisor: con `until` o con un subconjunto de las fuentes la elección cambia y el reloj que escribe se detiene; también otra raíz, sin `plan.json` o con otra huella); `test_panel_red2_v2.test_el_panel_rechaza_un_derivado_parcial` (por `ejecutar` y por `exigir_derivado_completo`); `test_derivado_red2_v2.test_el_derivado_completo_con_el_preparador` (con el preparador sellado de verdad: el completo pasa; con `until` o sin la actualización, no). El derivado sintético de las pruebas declara ahora las filas de `datos_red2` y ninguna ventana (`manifiesto_del_preparador`) |
| **T12 (a)-(e)**, [delegada] | declaradas en el §8.16, en un grupo aparte del de T7; el §8.6 queda con el alcance literal de T7 (los nodos hermanos pasan al §8.16 c); `contrato.enmiendas[2].decisiones_de_traduccion` y `red_ampliada_v2.DECISIONES_TRADUCCION`: T7 literal (línea 22 del archivo de decisiones), T12 y T13; la lectura (a) en `red_de_monitores.unidades.contraste_segunda_corrida`, en `red_de_monitores.orden` y en el docstring de `contraste_unidades_v2` | `test_red_ampliada_v2.test_decisiones_de_la_traduccion_citadas` y `test_decisiones_iguales_en_el_codigo_y_en_la_configuracion` (T1 a T13) |
| **T12, corrección 1.** O3 47,998 g/mol, la literal de R6 | `unidades_v2.MASA_MOLAR` y `red_de_monitores.unidades.masas_molares`; desde la ronda 4 (menor 9), el contraste de la segunda corrida también usa 47,998 (`contraste_unidades_v2.M`), por T12, que no hace excepción para él: es su única diferencia con el programa de la primera corrida; §8.12 | `test_unidades_v2.FactoresTests.test_masas_molares_literales_de_r6` (el contraste y la conversión, la misma masa); `test_contraste_unidades_v2.MismoProgramaTests` (acepta sólo esa diferencia); `test_red_ampliada_v2` (configuración igual al código) |
| **T12, corrección 2.** El panel replicaba `produccion.observaciones` sin fijar su huella | su huella entra en `panel_red2_v2.HUELLAS_CODIGO_V1`, que el armado comprueba antes de importar la v1; desde la ronda 4 (mayor 4 y menor 16), por repositorio (AP dd2db2ef…, espejo e9e18b5a…: es «adaptado») y el armado lo importa (`importar_produccion`, después de `importar_v1`) y marca las rachas con `produccion.marcar_rachas` (§8.16) | `test_panel_red2_v2.ObservacionesTests.test_misma_regla_que_produccion_observaciones` (las funciones de `produccion.py`, extraídas por AST, sobre las mismas horas sintéticas), `test_codigo_v1_con_huella`, `test_la_huella_adaptada_es_la_de_cada_repositorio` y `ReplicaPanelTests` (lo importa de verdad) |
| **T13**, [delegada] | §11, paso 0: el armado no empieza hasta que el autor ratifique T11, T12 y T13; si cambia alguna, otro commit antes del armado; §9, «Queda abierto», 0; `red_de_monitores.orden`. Desde la ronda 4 (mayor 6), el código lo hace cumplir: `red_ampliada_v2.RATIFICACION_T11_T13` (None hasta el paso 0 y llena desde la ratificación del 2026-10-26, §9.0; repetida en `red_de_monitores.ratificacion_t11_t13`), que la compuerta exige llena (`exigir_ratificacion`) | `test_red_ampliada_v2.GuardaR22Tests.test_sin_ratificacion_el_armado_no_empieza` y `CompuertaConGitTests.test_con_git_exige_la_ratificacion` |
| Huella del archivo de decisiones | fdfbfa31… en `red_ampliada_v2.DECISIONES_TRADUCCION` (y `ARCHIVOS_DEL_ESPEJO`; desde la ronda 4, también `DECISIONES_SIN_RATIFICAR`, la de antes de la ratificación), en `contrato.enmiendas[2].decisiones_de_traduccion` y en el reemplazo de `test_config_v2` (CAMBIOS) | `test_decisiones_de_la_traduccion_citadas` (con el espejo a mano, compara el archivo) |

### 3.7 Ronda 4 de verificación de la traducción (2026-10-26)

Cada arreglo de código tiene una prueba que falla sin él (§5.3). Los hallazgos repetidos (mayores 2, 3 y 5; menores 18
y 25) se corrigen una vez.

| Hallazgo | Arreglo | Prueba |
|---|---|---|
| **Mayor 1.** `tropomi_por_fecha.regla` conservaba el plazo de T11 que T13 reemplazó | reescrita según T13: el commit local puede ir antes de la ratificación; el armado no empieza hasta que el autor ratifique T11, T12 y T13 (§11, paso 0); si cambia alguna, otro commit de la traducción antes del armado | — |
| **Mayores 2, 3 y 5.** Con la propuesta aplicada, `test_factibilidad_v2.PuntaAPuntaTests.test_publicar_rechaza_un_resumen_con_metricas` se detenía en la parada de R19 (SystemExit) y daba ERROR | reemplazo 4 de `test_factibilidad_v2` en CAMBIOS: la parada por métricas con la configuración real sin `red_de_monitores` (RuntimeError, sin archivo) y la de R19 con la configuración real (SystemExit con «R19») | al aplicar, la prueba pasa (§5.3) |
| **Mayor 4.** La huella de `produccion.py` era la de AP; en el espejo el archivo es otro («adaptado»: un comentario) y el armado lanzado desde el espejo se detenía | `panel_red2_v2.HUELLAS_CODIGO_V1` con la huella por repositorio (AP dd2db2ef…, espejo e9e18b5a…, las del grupo «adaptados» de `config/componentes_compartidos.json`) y `huellas_del_repositorio`, que toma la del repositorio desde el que corre | `test_codigo_v1_con_huella` (también contra el manifiesto de componentes) y `test_la_huella_adaptada_es_la_de_cada_repositorio`; las pruebas nuevas, corridas también en el espejo (§5.3) |
| **Mayor 6.** Nada hacía cumplir T13 | `red_ampliada_v2.RATIFICACION_T11_T13` (None hasta el commit posterior a la ratificación, §9.0), `RATIFICABLES` (T11, T12, T13, §8.14 y §8.15; desde la ronda 5, también §8.17) y `exigir_ratificacion`, que la compuerta llama siempre con git real (todos sus llamadores son del armado): exige la constante llena, la huella nueva del archivo de decisiones (la de `DECISIONES_TRADUCCION` y no la de antes, `DECISIONES_SIN_RATIFICAR`) y la configuración repitiéndola (`red_de_monitores.ratificacion_t11_t13.valor`) | `test_sin_ratificacion_el_armado_no_empieza` (seis casos), `CompuertaConGitTests.test_con_git_exige_la_ratificacion`, `test_la_configuracion_repite_las_constantes_del_codigo` |
| Menor 7. Un derivado con los `inputs` del completo y el contenido recortado pasaba (`files` queda fuera de `digest(inputs)`) | `contrato_de_la_version`, sólo con metadatos: `files` nombra los dos parquet, con su sha256, sus filas (`read_metadata`) y la huella de su esquema (`read_schema`); `exigir_fuentes_y_ventana`: filas publicadas = `statistics.filas_en_ventana` = `statistics.filas_originales_leidas` = Σ «filas» de sus filas en los manifiestos de la lista cerrada. Límite declarado (docstring, §6 y `calidad.derivado.lectura_completa`): una reescritura que conserve los conteos sólo se detecta volviendo a derivar desde los CSV sellados; el reloj registra el sha256 de cada `observaciones.parquet` | casos «contenido recortado» en `test_un_derivado_parcial_no_escribe` y `test_el_panel_rechaza_un_derivado_parcial`; cuatro casos de `files` en `test_series_con_huella_exige_el_preparador_t8`; las filas del preparador real en `test_el_derivado_completo_con_el_preparador`; el derivado sintético declara ahora los dos parquet y sus conteos (`archivos_de_la_version`) |
| Menor 8. Las fuentes se comparaban sólo por (`relative_path`, `sha256`): otro «hasta» en la fila cambiaba la fila seleccionada en los solapes | `exigir_fuentes_y_ventana` compara cada fuente con su fila de la lista cerrada en todas las columnas de identidad (`CAMPOS_DE_LA_FUENTE`, leídas como texto: `series_contrato(…, texto=True)`) y muestra el campo distinto | `test_derivado_red2_v2.test_otro_hasta_con_el_preparador` (con el preparador sellado: la selección cambia en las 48 horas del solape y se detienen `exigir_derivado_completo`, el reloj que escribe y el panel); caso «otro hasta» en las pruebas del reloj y del panel |
| Menor 9. El contraste conservaba O3 47,9982 con el argumento que T12 rechazó | `contraste_unidades_v2.M` = `unidades_v2.MASA_MOLAR` (O3 47,998), su única diferencia con el programa original; textos alineados (§8.12) | `MismoProgramaTests.test_constantes` y `test_misma_decision` (CANDIDATOS con la M nueva); `test_masas_molares_literales_de_r6` |
| Menor 10. Las huellas de CAMS se calculaban sólo después de leer | `contraste_unidades_v2.leer_cams_con_huellas`: antes y después de `leer_cams`; si un archivo cambió, «CAMS cambió durante la lectura» | `test_contraste_unidades_v2.PublicacionTests.test_cams_que_cambia_durante_la_lectura` |
| Menor 11. La fila del menor 21 de la cuarta revisión seguía describiendo como vigente lo que T12 cambió | nota de T12 en esa fila | — |
| Menor 12. El contrato no nombraba las decisiones de la traducción ni T12 (a) | una oración en el párrafo de entrada del bloque (texto de la traducción, fuera de la transcripción) que remite a `contrato.enmiendas[2].decisiones_de_traduccion` y a T12 (a), sin repetir la huella; contrato propuesto bb44ee5d… (en la ronda 5, menores 14, 16 y 24, la oración deja de atribuir T11 a T13 al autor: contrato 5140306e…, §3.8) | — |
| Menor 13. Tras `fijar --reemplazar`, el evento de R13 quedaba escondido en `bitacora_anterior` | `pliegues_red2_v2.evento_r13` y `fijar`: la bitácora nueva empieza con el evento de R13 del manifiesto anterior, copiado tal cual; sin él, no se reemplaza | `test_pliegues_red2_v2.test_tras_reemplazar_sigue_el_evento_de_r13` (las aserciones de `test_manifiesto_v2.test_red_ampliada_una_sola_fuente` sobre el archivo escrito) |
| Menor 14. La decisión no comparaba su evaluabilidad de E2 con la registrada antes del ajuste (R15) | `pliegues_red2_v2.misma_evaluabilidad_e2` y reemplazos 5 y 7 de `correr_v2.py`: `decidir` comparaba el «evaluable» por protocolo y se detenía si diferían. **Corregido en la ronda 5 (mayor 1, §3.8):** esa parada dejaba al autor elegir con las métricas a la vista; ahora rige la registrada (`evaluabilidad_e2_que_rige`) y la de la decisión sólo se registra (§8.17) | ronda 5: `test_pliegues_red2_v2.test_en_la_decision_rige_la_evaluabilidad_registrada`; al aplicar, `test_correr_v2.RedAmpliadaTests.test_decidir_usa_la_evaluabilidad_registrada_de_e2` |
| Menor 15. Ni el anexo ni `registro_de_la_red` traían la evaluabilidad de E2 (R15, «se escribe en el registro de la red») | `registro_de_la_red.evaluabilidad_e2` (por contaminante y protocolo: evaluable, fracción del peso, grupos con E2 y pesos de E1 y E2), de `evaluabilidad_e2_del_manifiesto`, que escribe `anexo_desde_artefactos` y compara `exigir_registro` (`verificar_evaluabilidad_e2`); su entrada vacía en la configuración | casos «evaluabilidad_e2» en `test_el_anexo_es_el_de_los_artefactos` |
| Menor 16. La razón para no importar `produccion.py` no era la verdadera | el armado lo importa (`importar_produccion`, después de `importar_v1` y de `verificar_codigo_v1`, con `_red_adicional.py` también por su huella) y `observaciones_red2` marca las rachas con `produccion.marcar_rachas`; las pruebas sin disco usan `rachas_sin_produccion`; la prueba de equivalencia por AST sigue (§8.16) | `ReplicaPanelTests` (lo importa de verdad: sin red adicional, con la raíz de la copia, sin manejadores de registro nuevos y las mismas rachas); `test_misma_regla_que_produccion_observaciones` (con y sin él); `test_las_rachas_las_marca_la_funcion_del_armado`; `test_ejecutar_registra_la_procedencia` (el armado pasa `produccion.marcar_rachas` en los tres contaminantes) |
| Menor 17. La regla de la Enmienda 2 de los regímenes estaba dentro de `criterio` | nodo hermano `metricas.desagregaciones.regimen_de_predictores.criterio_enmienda_2` (regla y lectura); los valores siguen en `criterio` (§4.8 y §8.16 c) | al aplicar, `test_config_v2` (la ruta de R17 existe) |
| Menores 18 y 25. Las lecturas §8.14 y §8.15 no tenían destino | se nombran en la ratificación antes del armado (§9, «Queda abierto», 0, y §11, paso 0) y entran en `RATIFICABLES`; `registro_de_la_red.tropomi_por_fecha.regla` lo dice (desde la ronda 5, también la §8.17: §3.8) | `test_sin_ratificacion_el_armado_no_empieza` (sin «§8.14», se detiene) |
| Menor 19. «hoy 65» en M5 | «hoy 70» | — |
| Menor 20. Cuatro controles de `exigir_fuentes_y_ventana` sin prueba | casos `con_since`, `con_una_fuente_de_mas`, `con_una_fuente_repetida` y `con_otra_huella` (`test_reloj_sinca_v2.DERIVADOS_PARCIALES`), en el reloj que escribe (que no crea su carpeta) y en el panel | `test_un_derivado_parcial_no_escribe`, `test_el_panel_rechaza_un_derivado_parcial` |
| Menor 21. El desempate de R9 estaba escrito dos veces | `duplicados_v2.orden_de_conservacion`, la única regla, que usan `pares_duplicados.conserva` y `quitar_copias` | `test_duplicados_v2.test_empate_por_codigo` (también por `quitar_copias` y el registro) |
| Menor 22. El mensaje de la raíz rechazada sólo mostraba su último nombre | `derivado_red2_v2.raiz_portable`: la ruta relativa a la carpeta de la raíz de datos («derived/v1_red2»), sin rutas absolutas | `test_un_derivado_parcial_no_escribe` |
| Menor 23. La rama v3 (sin rastrear) fija las huellas de `_rutas_v2.py` y `config_v2.json` | declarado en §11.1 | — |
| Menor 24. A la lista de §9.0 le faltaba `tests/test_red_ampliada_v2.py` | agregada a §9.0 y a §11, paso 0; la prueba ya no fija a mano el prefijo de la huella: la compara con el archivo y, mientras no haya ratificación, con `DECISIONES_SIN_RATIFICAR` | `test_decisiones_de_la_traduccion_citadas` |

### 3.8 Ronda 5 de verificación de la traducción (2026-10-26)

Cada arreglo de código tiene una prueba que falla sin él (§5.3). Los hallazgos repetidos se corrigen una vez: el mayor 1
con los menores 7, 8, 20 y 26; el 4 con el 23; el 12 con el 22; el 13 con el 19 y el 29; el 14 con el 16 y el 24; el 15
con el 27.

| Hallazgo | Arreglo | Prueba |
|---|---|---|
| **Mayor 1** (y menores 7, 8, 20 y 26). La decisión comparaba su evaluabilidad de E2 con la registrada y, si diferían, se detenía para que el autor eligiera con las métricas a la vista, lo que R15 cierra («antes de cualquier ajuste»); y la §8.17 no entraba en la ratificación | rige la registrada: `pliegues_red2_v2.evaluabilidad_e2_que_rige` (reemplaza a `misma_evaluabilidad_e2`) da a `decision_v2` una copia de la evidencia con el «evaluable» registrado y deja el de la decisión sólo en `decision.json`, con la huella de la evidencia consolidada; se detiene sólo si la registrada es evaluable y la evidencia no tiene pares E2 (defecto de la corrida). Reemplazos 5 y 7 de `correr_v2.py` y la prueba de `test_correr_v2` en CAMBIOS. §8.17 reescrita, sin «lo decide el autor», y en la ratificación: `RATIFICABLES`, §9.0, §11 paso 0, la introducción del §8 y `ratificacion_t11_t13.regla` | `test_pliegues_red2_v2.test_en_la_decision_rige_la_evaluabilidad_registrada` (con `decision_v2.evaluar_protocolo`: con la evidencia en 0,49 y la registrada en 0,51 la condición 3 se exige; al revés, no bloquea); al aplicar, `test_correr_v2.RedAmpliadaTests.test_decidir_usa_la_evaluabilidad_registrada_de_e2`; `test_sin_ratificacion_el_armado_no_empieza` (sin «§8.17», se detiene) |
| Menor 2. Pasar filas de `observaciones.parquet` a `solapamientos.parquet` conservaba el total y fabricaba otra elección de T4 | `exigir_fuentes_y_ventana`: archivo por archivo, las filas de `observaciones.parquet` son `statistics.filas_seleccionadas` y las de `solapamientos.parquet`, `statistics.filas_alternativas_conservadas`; y, como `statistics` queda fuera de `digest(inputs)`, `invariante_del_ranking`, sólo con `ts_local`: cada etiqueta válida una vez en observaciones y toda fila de solapamientos con una etiqueta válida que está en observaciones (`afg_lib.py:320-324`, `preparar_sinca_modelado.py:306`). Límite reescrito en los docstrings y en `calidad.derivado.lectura_completa` | casos «filas movidas a solapamientos» (con `statistics` del completo) y «filas movidas, statistics al día» en `DERIVADOS_PARCIALES` (el reloj que escribe y el panel); `test_el_derivado_completo_con_el_preparador`, con el preparador real (X01: 120 → 90 y 48 → 78; su `validate_publication` lo acepta, `exigir_derivado_completo` no) |
| Menor 3. El panel, el contraste y el reloj registraban el sha256 de cada serie y la leían después sin comprobarlo | `reloj_sinca_v2.leer_serie`: lee los bytes una vez, compara su sha256 con el registrado (`huellas_de`) y lee la tabla desde esos mismos bytes; la usan `verificar_red` (el reloj y el recálculo del panel), `panel_red2_v2.observaciones_desde_derivado` (con `huellas` obligatorio) y `contraste_unidades_v2.series_red2` (con el registro que va al lateral) | `test_reloj_sinca_v2.test_la_serie_se_lee_con_su_huella`, `test_panel_red2_v2.test_la_serie_se_lee_con_la_huella_registrada` y `test_contraste_unidades_v2.test_la_segunda_corrida_lee_cada_serie_con_su_huella` (una serie reemplazada entre el registro y la lectura) |
| Menores 4 y 23. Tres controles del derivado completo sin una prueba que fallara sin ellos: la versión de la última corrida, una sola raíz y las filas de los manifiestos fuera de la raíz de datos | casos nuevos: una versión que la corrida no publicó, plantada junto a la suya con `created_utc` posterior (la que elige `version_sinca`), y un `progreso.json` con otra versión («no tienen la versión»), en el reloj y en el panel; «un solo derivado», afirmado en el caso de dos raíces; una fila de manifiesto fuera de la raíz de datos («apuntan fuera de la raíz») | `test_un_derivado_parcial_no_escribe`, `test_una_raiz_parcial_no_escribe`, `test_el_panel_rechaza_un_derivado_parcial` |
| Menor 5. La regla de unidades del armado se comprobaba después de escribir el inventario, la copia congelada y los enlaces | `panel_red2_v2.ejecutar` llama a `unidades_del_armado` justo después de `contraste_y_su_huella` | `test_las_unidades_se_comprueban_antes_de_escribir` (con una segunda corrida a la que le falta una serie, no se escribe nada) |
| Menor 6. En el armado conviven dos masas molares del O3 y los textos declaraban una | T12 corrige la conversión de R6 y el contraste; `cams_o3` sigue con 47,9982, del código v1 con su huella (R11): en `masas_molares_nota`, en el docstring de `unidades_v2` y en §8.12; sin cambio de código | — |
| Menor 9. La E2 registrada fijaba a mano los códigos de E2 y el mínimo de horas | `evaluabilidad_e2_red2` lee `metricas_v2.codigos_evaluacion_de_config` y `metricas.niveles.diario.minimo_horas`, como la decisión, y los registra | `test_evaluabilidad_e2_con_los_umbrales_de_la_decision` (una SNIFA `usable_native`, más estaciones que grupos con `grupos_E1` y `grupos_con_E2`, y otro mínimo de horas) |
| Menor 10. Ninguna prueba distinguía el peso × filas de T1(1) de la suma de pesos fijos | un caso sintético en que difieren | `test_bloque_mas_influyente_por_peso_y_filas` (rige la RM, la suma de pesos fijos da RVIII y `coinciden` es False) |
| Menor 11. La regla de R17 («la mitad de los días») no estaba atada | un caso con tres estaciones y 24 horas por día, una familia en muchas filas de pocos días y un año con exactamente el 50 % | `RegimenesTests.test_cuenta_dias_distintos_y_la_mitad_exacta` |
| Menores 12 y 22. La huella del código v1 en `ejecutar` y las dos guardas de `importar_produccion` no tenían una prueba que fallara sin ellas | `ejecutar` con `HUELLAS_CODIGO_V1` alterado se detiene antes de `publicar_inventario` y de `importar_produccion`, sin escribir nada; `importar_produccion` con un `produccion` simulado con la red adicional o con otro `QC_RACHA`; y, de verdad, en un proceso aparte: sin `_comun_modelo` cargado, con MODELO_1KM_RED_ADICIONAL=1 y con otro MODELO_1KM_QC_RACHA | `test_el_codigo_v1_sin_su_huella_detiene_el_armado`, `test_importar_produccion_exige_su_regla`, `ReplicaPanelTests.test_importar_produccion_en_un_proceso_aparte` |
| Menores 13, 19 y 29. El índice de puntos no tenía los nodos nuevos de R15 ni de R22 | `contrato.enmiendas[2].puntos`: R15 con `red_de_monitores.registro_de_la_red.evaluabilidad_e2` y `red_de_monitores.fuente_unica_de_pliegues`; R22 con `red_de_monitores.compuerta_r22` y `red_de_monitores.ratificacion_t11_t13` | al aplicar, `test_config_v2.test_entrada_del_bloque_red_ampliada` (cada ruta existe) |
| Menores 14, 16 y 24. El párrafo de entrada del contrato atribuía T1 a T13 al autor | «T1 a T10, del autor; T11 a T13, por delegación ([delegadas]: decididas con la opción recomendada sin que el autor las viera; T13 exige que el autor las ratifique antes del armado, y el estado de esa ratificación queda en `red_de_monitores.ratificacion_t11_t13`)»: es verdad antes y después de la ratificación, así que ratificar no obliga a cambiar el contrato sellado; si la ratificación cambia T12 (a), el párrafo y su huella entran en ese commit (§9.0) y el contrato está en la lista de §8.16 (a). Contrato propuesto 5140306e… en `contrato.sha256`, en `CONTRATO_PROPUESTO` y en §2 | al aplicar, `test_la_v1_y_el_contrato_sellado_no_cambian` |
| Menores 15 y 27. La rama meteorológica fija las huellas de `correr_v2.py` y `config_v2.json` | §11.1: qué fija (`fijados.py`, sus dos pruebas y la tabla de `DISENO_IMPLEMENTACION_M1.md`), qué fallará desde el commit de la traducción y que el orden de los cambios a esos dos archivos, con la enmienda de `Contexto.desde_disco` del protocolo v2.2, se acuerda con ese frente; la traducción no toca esa carpeta | — |
| Menor 17. El registro MAIAC iba cuarto, dentro del armado, contra T5 («antes del armado») | primero, después de la ratificación y antes del derivado, rotulado «antes del armado (T5)», en §11 paso 2 y en `red_de_monitores.orden`; también en `CAMINO_518`, §8.8, §9.3 y `catalogo_maiac.registro` | `test_la_configuracion_repite_las_constantes_del_codigo` (`CAMINO_518`, igual en la configuración) |
| Menor 18. La introducción del §8 extendía T7 a §8.1-§8.7 | «T7 acepta sólo las diferencias del §8.6 y la lectura de R21 (§9.4); §8.1 a §8.5 son hallazgos sin cambio de regla y la lectura de §8.7 la cubre T12 (b)» | — |
| Menor 21. Con la ratificación anotada, nada obligaba a quitar «pendiente de que el autor la ratifique» de T11 a T13, y ningún artefacto registraba la ratificación | `exigir_ratificacion` exige T11 a T13 sin la marca de pendiente y con «<estado> por el autor el <fecha>» (`MARCA_DE_RATIFICACION`), en `DECISIONES_TRADUCCION` y en `contrato.enmiendas[2].decisiones_de_traduccion`; `traduccion_de` registra `ratificacion`; §9.0 y `ratificacion_t11_t13.regla` lo dicen | `test_sin_ratificacion_el_armado_no_empieza` (textos pendientes en el código o en la configuración, y otro estado), `TrazaRed2Tests.test_trae_lo_que_pide_el_contrato` |
| Menor 25. La prueba de la ratificación afirmaba el valor de hoy de la constante | sin el `assertIsNone`: el caso «vacía» fija la constante con `con_la_ratificacion(None, …)` | `test_sin_ratificacion_el_armado_no_empieza` |
| Menor 28. El commit del anexo no regeneraba `config/componentes_compartidos.json` | §11 paso 3: lo regenera, coordinado como en §11.1 | — |
| Menor 30. Una raíz rechazada fuera de la carpeta de la raíz de datos se mostraba sólo por su nombre | `derivado_red2_v2.raiz_portable`: «fuera de la carpeta de la raíz de datos: …/» con sus cuatro últimos componentes | caso en `test_un_derivado_parcial_no_escribe` |

## 4. Cambios en la configuración, nodo por nodo

1. `descripcion`, `contrato.sha256` (→ 5140306e…, el contrato propuesto) y `contrato.nota`. La entrada del Complemento
   conserva su sha256 (5d879a05…), que pasa a ser «el texto sin la Enmienda 2».
2. `contrato.enmiendas[2]` (nueva): el bloque, con su huella, el commit de anclaje, las decisiones del autor y **las de
   la traducción** (T1 a T13; T11, T12 y T13 con su marca [delegada]; T7 con su alcance literal), lo que se sabía y, por punto R2-R22, los nodos que lo
   traducen.
3. `relacion_v1.insumos_v1_solo_lectura` → sin efecto (R11).
4. `red_de_monitores` (nuevo): lista cerrada con 20 huellas; estaciones nuevas; `fuera_por_coordenadas` (con el orden
   frente a la regla de unidades y la cláusula de la 518); red resultante; regla de inclusión; período; calidad;
   unidades (con la huella del contraste obligatoria); reloj (con `convencion_de_la_etiqueta`: la regla T4, dónde se
   calcula y cómo la lee el armado, las dos opciones, su efecto y las fuentes revisadas); coordenadas; duplicados;
   propietarios (dónde se registran y por qué hay «no informado»); insumos de hoy (registro y huella, fecha de
   modificación sólo por T1-4 y T11, copia congelada, copia de corte de MERRA-2, `catalogo_maiac` por T5, 232 GB por
   T6);
   pesos (población obligatoria, `--sin-e2` sólo sin escribir); regímenes (regla común); `fuente_unica_de_pliegues`;
   `registro_de_la_red` (vacío, con la estructura de cada entrada: lo llena el anexo con
   `pliegues_red2_v2.registro_de_la_red_desde_artefactos`, con el reloj de T4, el registro MAIAC de T5, la segunda
   corrida con su lateral, los paneles, la calidad, los duplicados, la lista cerrada, los insumos y las órbitas de T11;
   desde la quinta revisión, también la traducción común de los artefactos, el límite de R7 y el estado de la procedencia
   de la descarga; desde la ronda 4 de verificación, la evaluabilidad de E2 por protocolo); `compuerta_r22` (con la
   procedencia de cada artefacto); O3; producto meteorológico; `ratificacion_t11_t13` (T13: null hasta el paso 0;
   desde el 2026-10-26, la ratificación); orden; huellas del código nuevo; desde la cuarta revisión,
   `procedencia_descarga`, `factibilidad` (R19, que desde la quinta detiene `medir` y `publicar`) y
   `unidades.masas_molares_nota`.
5. `protocolos.manifiesto.red_ampliada` (fuente única, renombre de R13, lectores y registro) y
   `protocolos.LOSO-D.estaciones`, `protocolos.LPO.anio_local` (con sus textos anteriores).
6. `retransformacion.comparaciones_v2_frente_a_v1` → sin efecto (R12).
7. `calidad_blanco.evaluacion.cobertura_conocida.red_ampliada` (R15): su regla y, por contaminante, la cifra de la red
   ampliada, que escribe el anexo.
8. `metricas.desagregaciones.propietario` (R10, descriptivo; se calcula como estrato de las métricas) y
   `…regimen_de_predictores.criterio_enmienda_2` (R17, con la regla común: nodo hermano de `criterio`, que conserva los
   valores; T12 c).
9. `inferencia_diferencias.influencia.bloque_mas_influyente_enmienda_2` (R16) → `pliegues_v2_red2.json`.
10. `presupuesto.despues_de_los_cuatro_recortes` (R18) y `fuera_del_contrato.entran_por_la_enmienda_2` (R11).
11. Tres cambios que esta lista no traía hasta la comprobación de la aplicación:
    - `protocolos.manifiesto.vigente.es`: «el manifiesto vigente hasta la Enmienda 2, con el amortiguador de BLQ-75
      (Enmienda 1, punto 8)»;
    - `protocolos.manifiesto.vigente.enmienda_2`, nuevo;
    - `calidad_blanco.evaluacion.cobertura_conocida.red_original`, nuevo, con las dos cifras anteriores.
    Son los tres de R13 y R15 sobre la red original; ninguno cambia un valor.

## 5. Cambios en el código sellado: qué rompen y sus reemplazos

### 5.1 Código

| Archivo (origen) | Cambio | Qué rompía sin reemplazo |
|---|---|---|
| `_rutas_v2.py` (eb8a92d2…) | `panel(pol)` → `paneles/panel_<pol>_red2.parquet` en la raíz v2; `panel_v1(pol)`; `manifiesto_pliegues` → `pliegues_v2_red2.json`; el derivado SINCA v1 entre las raíces de sólo lectura; candado «pliegues» para los dos manifiestos; `RutasRedOriginal` (las rutas de antes, para las réplicas de la red original y sus pruebas) | `test_rutas_v2` (2) |
| `calidad_v2.py` (5f34bf2d…) | `ruta_calidad` sigue al panel en uso (`calidad_<pol>_red2.parquet` o `calidad_<pol>.parquet`); con el nodo de la red se detiene siempre, con un mensaje que ya no sugiere `--no-escribir`; `cargar_bandera` compara la bandera con `calidad_sha256` del json del panel (obligatorio con la red 2) | el ciclo de `test_calidad_v2` (8) y `test_calidad_artefacto_v2`, que se saltaría para siempre |
| `pliegues_v2.py` (05cac03f…) | con el nodo de la red se detiene (también con `--no-escribir` y `--refijar`): la única fuente es `pliegues_red2_v2` | el ciclo de `test_pliegues_v2` (6) |
| `validar_vecindario_v2.py` (2465a31f…) | la reproducción (a2) en float64, con la red 2, lee las observaciones del armado por su huella (`observaciones_red2_float64`) y queda en `a2_fuente_red2_float64` | se detenía siempre por omisión (el json del panel red 2 no declara la configuración v1) |
| `vecindario_v2.py` (0121a6c4…) | el mensaje de panel faltante ya no dice «panel v1» | — |
| `correr_v2.py` (534e484b…) | `Contexto.desde_disco` exige el registro del anexo (que comprueba también R16, R17 y el resto del anexo) y, con la red 2, la bandera de calidad, también con `con_calidad=False`; `main` rechaza `--sin-calidad` con la red 2; `decidir` exige el anexo y que el bloque más influyente de cada evidencia sea el de la configuración (R16) y, desde la ronda 5 (antes, en la ronda 4, comparaba y se detenía), entrega a `decision_v2` la evaluabilidad de E2 registrada antes del ajuste, que rige (R15), con la de la evidencia sólo como registro en `decision.json` y una parada si la registrada es evaluable y la evidencia no tiene pares E2; el propietario entra como estrato de las métricas (R10) | — (las pruebas sintéticas usan la configuración sin el nodo); las piezas nuevas, en `test_correr_v2.RedAmpliadaTests` |
| `factibilidad_v2.py` (2229bd95…) | `fechas_de_medicion`: con el anexo (que deja los regímenes de la Enmienda 1 en `criterio.valor_red_original`), las fechas salen de esos (R19); desde la quinta revisión, `exigir_sin_red_ampliada` detiene `medir` y `publicar` (y sus órdenes de consola) con el nodo `red_de_monitores`: «R19, la medición no se revisa» | con los tramos calculados en `criterio.valor`, `test_factibilidad_v2.FechasTests.test_fechas_fijadas_por_calendario` se detenía (cuarta revisión, menor 9); sin la parada, `medir` mediría sobre el panel de la red 2 y `publicar` reescribiría `factibilidad_produccion.json` (quinta revisión, menores 13 y 24) |
| `piloto_v2.py` (60cfaba9…) | R18 en el docstring, en `decidir_recortes`, en la acción del último paso y en el plan (`sobre_el_umbral_tras_los_recortes` en lugar de `pendiente_del_autor`); con la red 2 y sin la bandera, `estimar_y_publicar` se detiene | `test_piloto_v2` (2) |

### 5.2 Pruebas

| Archivo (origen) | Reemplazo |
|---|---|
| `tests/_sintetico_v2.py` (c9cd550f…) | `config_pequena` sin el nodo `red_de_monitores` (la red de esas pruebas es la sintética); `anexo_de_la_red`: lo que rige después del anexo (tramos comunes y bloque calculados, por las huellas del anexo) o None |
| `tests/test_rutas_v2.py` (968b5b51…) | nombre del manifiesto, panel red 2 y `panel_v1`, derivado de sólo lectura, candados de los dos manifiestos |
| `tests/test_manifiesto_v2.py` (267b9707…) | procedencia con `sha256_declarado` (red 2) o `sha256_declarado_v1`; los conteos 10 y 6 y el ejemplo de 3,7 km, sólo para la red original; prueba nueva de la fuente única |
| `tests/test_factibilidad_v2.py` (4fcd0613…) | `test_mide_publica_respalda_y_no_deja_nada` crea la carpeta del panel red 2 (corre con la configuración sintética, sin el nodo); la prueba sin el régimen 2019-2024 lo quita también de `valor_red_original`; prueba nueva: con los tramos calculados, las mismas fechas; desde la quinta revisión, `RedAmpliadaR19Tests`: con el nodo, `medir` y `publicar` (también desde la consola) se detienen con «R19» sin armar ni escribir nada; desde la ronda 4 (reemplazo 4), `test_publicar_rechaza_un_resumen_con_metricas` prueba la parada por métricas con la configuración real sin el nodo y la de R19 con ella |
| `tests/test_calidad_artefacto_v2.py` (f3268c6e…) | mira la bandera real de la red original con `RutasRedOriginal` (si no, se saltaría para siempre) |
| `tests/test_calidad_v2.py` (fe1f7bd1…) | el ciclo corre con `RutasRedOriginal` y la configuración sin el nodo; pruebas nuevas: con el nodo se detiene, la bandera sigue al panel y la de la red 2 se lee por su huella |
| `tests/test_pliegues_v2.py` (21e1c1e3…) | ídem; prueba nueva: con el nodo se detiene |
| `tests/test_correr_v2.py` (59bbe799…) | prueba nueva del estrato de propietario; `RedAmpliadaTests`: `desde_disco` se detiene sin el registro del anexo (por su mensaje, con un manifiesto que calza con el panel), sin la bandera o sin calidad y corre con los dos; `decidir` exige el anexo y el bloque de la evidencia, y usa la evaluabilidad de E2 registrada en vez de la de la evidencia, que queda en el registro, y se detiene sin pares E2 (ronda 5, `test_decidir_usa_la_evaluabilidad_registrada_de_e2`); la consola rechaza `--sin-calidad`; las tres aserciones selladas del bloque y de los regímenes leen lo que rige (`dc.regla_de_config(CFG)` y `mt.regimenes_de_config(CFG)`) |
| `tests/test_piloto_v2.py` (26f921cc…) | R18: sin `pendiente_del_autor`, «no hay quinto recorte (Enmienda 2, R18)»; prueba nueva: con la red 2 y sin la bandera, no se estima el plan |
| `tests/test_vecindario_v2.py` (b21d5315…) | motivo correcto del salto con datos reales; prueba nueva de la lectura float64 con la red 2 |
| `tests/test_config_v2.py` (c7f4b4f6…) | el Complemento termina donde empieza el bloque; tres enmiendas; entrada del bloque con las decisiones de traducción (T1 a T13, T11 a T13 [delegadas], huella a0b970d2… desde la ratificación del paso 0; antes, fdfbfa31…), T8 igual en el código y en la configuración y el registro vacío antes del anexo; desagregación por propietario; los cinco regímenes y el bloque más influyente, los de la Enmienda 1 sin anexo y los calculados con él (`anexo_de_la_red`) |
| `tests/test_metricas_v2.py` (2ae7a194…) | los regímenes de la configuración: sin anexo, los cinco de la Enmienda 1; con él, los tramos comunes calculados |
| `tests/test_decision_v2.py` (2be67aec…) | la regla de la configuración es `ReglaDecision` con el bloque más influyente que rige: el de la Enmienda 1 sin anexo y el calculado con él |

### 5.3 Resultado en una copia temporal con todo aplicado

Con el contrato, la configuración y los reemplazos (65 en la cuarta revisión; 70 hoy) aplicados a una copia de AP en el borrador (sin tocar AP; sin la
DMC, sin `meteo_combinada` y con las raíces de datos vacías), corridos uno a uno con un hilo y prioridad baja
(2026-10-26, tras la cuarta revisión): pasan los 27 módulos corridos (todos salvo `test_meteorologia_v2`,
`test_piloto_perdidas_sin_dmc` y `test_preflight_pre_dmc`, que no toca la propuesta y que leen la DMC o un piloto con
cifras, y no se corrieron), con dos excepciones que no vienen de la propuesta: las cuatro citas `qmd:2007`, `2009`,
`2060` y `2064` de `test_calidad_v2` (la copia de trabajo de `docs/modelo_1km_horario.qmd` corrió sus líneas; ya fallan
hoy en AP), y dos de `test_factibilidad_v2` (`CompiladosTests` y `test_mide_publica_respalda_y_no_deja_nada`), que
necesitan al menos dos hilos de OpenMP (tl2cgen: «nthread cannot exceed 1»).

**Con un anexo simulado** (cuarta revisión, mayor 1): en otra copia, `pliegues_red2_v2.con_el_anexo` escribe en la
configuración un bloque calculado RV / E004N084 y tramos comunes sin 2019-2024 (2000-2002, 2003-2017, 2018, 2019-2022 y
2023-2026), con los de la Enmienda 1 en `valor_red_original`, y una raíz v2 de juguete trae `regimenes_red2.json` y un
`pliegues_v2_red2.json` mínimo. Pasan las pruebas selladas que leen lo que rige: `test_correr_v2` (las 49 que no leen el
manifiesto real), `test_config_v2` (las 59 que no lo leen), `test_metricas_v2`, `test_decision_v2` y
`test_factibilidad_v2.FechasTests`; sin los reemplazos 2 a 4 de `test_correr_v2`, sus tres aserciones fallan con el
anexo. Las otras fallas son las dos de arriba y las de las pruebas que leen el manifiesto real de la raíz v2
(`test_manifiesto_v2.ManifiestoRealTests`, `test_config_v2.test_bloques_influyentes_existen_en_el_manifiesto`,
`test_retransformacion_v2.test_manifiesto_real_cubre_todas_las_estaciones` y `test_correr_v2.test_plan_real_no_escribe`),
que con el manifiesto de juguete, sin `schema` ni `contaminantes`, dan KeyError: después del armado corren sobre el
`pliegues_v2_red2.json` de verdad.

**Cada arreglo, con una prueba que falla sin él** (cuarta revisión): en la copia aplicada se revirtió, uno por vez, cada
arreglo de código (26 mutaciones: el par de repositorios, la rama «modificado», los textos del espejo sin rastrear o con
otra huella, los componentes, `files`, la versión, `digest(inputs)`, el Python al leer y el entorno al derivar, la
corrida equivalente, el nombre del contraste, la zona como texto, el inventario sin T5, la política sin huella,
`--primera` sin huella, `rechazar_primera`, `calidad_sha256`, la alineación por estación, la bandera de la traza, los
regímenes de los paneles, la cobertura de E2, retomar sin volver a calcular las huellas, las SNIFA como empresa,
`desde_disco` sin el anexo y las fechas de la factibilidad): en las 26, su prueba falla con la mutación y pasa sin ella.

**Quinta revisión** (2026-10-26): en otra copia aplicada (los 68 reemplazos, con las raíces de datos vacías) pasan las
pruebas nuevas, `test_factibilidad_v2.FechasTests` y `RedAmpliadaR19Tests` y `test_correr_v2.RedAmpliadaTests`; y se
revirtió, uno por vez, cada arreglo de la quinta revisión (30 mutaciones: las dos paradas de la escritura única del
reloj, la base de zonas en el reloj y en el panel, el límite de R7, los archivos CAMS en el lateral y en el panel, las
tres guardas de `contraste_unidades_v2.main`, el contaminante del manifiesto, «no copió», `red_original` con
`setdefault`, el aviso y `red_original` en `exigir_lo_calculado`, la configuración confirmada en git y los bytes del
espejo, la traducción común y la procedencia de la descarga en el anexo, la traza de cada artefacto —reloj, lateral,
registro MAIAC, inventario, copia congelada, json de los paneles—, la huella del programa en `plan.json`, T8 completo,
la comparación de lo que entra al retomar y las dos paradas de R19 en `factibilidad_v2`): en las 30, su prueba falla con
la mutación y pasa sin ella.

**Se saltan hasta el armado** (no hay panel red 2 ni `pliegues_v2_red2.json`; después corren sobre la red 2): las 13 de
`test_manifiesto_v2`; `test_config_v2.test_bloques_influyentes_existen_en_el_manifiesto`; una de `test_metricas_v2`
(insumo INE y manifiesto); una de `test_retransformacion_v2` (manifiesto); las 3 de `test_vecindario_v2.PanelRealTests`;
y `test_correr_v2.test_plan_real_no_escribe`. Hoy, en AP, corren sobre la red original.

**Rondas de verificación de la traducción** (2026-10-26, tras la ronda 3; §3.6): en otra copia aplicada (los 68
reemplazos, con las raíces de datos vacías y sin la DMC), corridos uno a uno con un hilo y prioridad baja, se corrieron
los 26 módulos de `tests/` salvo `test_meteorologia_v2`, `test_piloto_perdidas_sin_dmc` y `test_preflight_pre_dmc`
(leen la DMC o un piloto con cifras). Pasan 24; en los otros dos sólo fallan pruebas que no vienen de esta ronda: las
cuatro citas `qmd` de `test_calidad_v2` y, en `test_factibilidad_v2`, las dos que piden dos hilos de OpenMP y
`PuntaAPuntaTests.test_publicar_rechaza_un_resumen_con_metricas`, que llamaba a `publicar` con la configuración real
y, con el nodo `red_de_monitores`, se detenía antes en la parada de R19 de la quinta revisión (la corrige el reemplazo
4 de `test_factibilidad_v2`, ronda 4: §3.7). Se revirtió, uno por vez, cada arreglo de esta
ronda (10 mutaciones: la llamada a `exigir_fuentes_y_ventana`, la ventana, las fuentes, la raíz, el `plan.json`, el O3
de la conversión y el del contraste, la huella de `produccion.py` y dos cambios en la réplica de
`produccion.observaciones`): en las 10, su prueba falla con la mutación y pasa sin ella.

**Ronda 4 de verificación de la traducción** (2026-10-26; §3.7): en otra copia aplicada (los 70 reemplazos, con todas
las raíces de datos vacías y sin la DMC), corridos uno a uno con un hilo y prioridad baja, se corrieron los 26 módulos
de `tests/` salvo `test_meteorologia_v2`, `test_piloto_perdidas_sin_dmc` y `test_preflight_pre_dmc`. Pasan 24; en los
otros dos sólo fallan pruebas que no vienen de la propuesta: las cuatro citas `qmd` de `test_calidad_v2` y, en
`test_factibilidad_v2`, las dos que piden dos hilos de OpenMP. `test_publicar_rechaza_un_resumen_con_metricas` pasa
(reemplazo 4) y `test_correr_v2` también (51 pruebas, con la nueva de R15). Se revirtió, uno por vez, cada arreglo de
esta ronda (22 mutaciones: la ratificación en la compuerta, la huella de antes de ratificar y la configuración que la
repite; `files` con los dos parquet, sus filas y su esquema; los conteos anclados a la lista cerrada; la identidad
completa de cada fuente; `since`, las fuentes de más y las repetidas; la raíz portable; el O3 del contraste; las huellas
de CAMS después de leer; el desempate de R9; la huella por repositorio; las rachas de `produccion.marcar_rachas` en
`observaciones_red2` y en el armado; el evento de R13 al reemplazar; la evaluabilidad de E2 en el registro de la red y
en la decisión, y su llamada en `correr_v2.decidir`): en las 22, su prueba falla con la mutación y pasa sin ella. Las
ocho pruebas nuevas de la red 2 y las tres de `scripts_pipeline` (geometría, descargador y módulo meteorológico) pasan
en AP y en el espejo, desde donde antes fallaban tres por la huella de `produccion.py` (mayor 4).

**Ronda 5 de verificación de la traducción** (2026-10-26; §3.8): en otra copia aplicada (los 70 reemplazos, con las
raíces de datos vacías, sin la DMC y sin `meteo_combinada`, `reloj_dmc`, `v3` ni `o3_next`), corridas una a una con un
hilo y prioridad baja, pasan las ocho pruebas nuevas de la red 2 (207), `test_config_v2` (60, una saltada) y
`test_correr_v2` (51, una saltada, con la nueva de R15); en AP pasan las mismas ocho. Se revirtió, uno por vez, cada
arreglo de esta ronda (27 mutaciones: la evidencia con la E2 registrada, la parada por defecto de la corrida y su
entrega en `correr_v2.decidir`; los conteos por archivo y el invariante del ranking; la lectura con huella en
`leer_serie`, en el panel, en el contraste, en el reloj y en el recálculo del panel; la versión de la última corrida;
las unidades antes de escribir; la §8.17 en `RATIFICABLES`; los códigos de E2, los grupos del protocolo y el mínimo de
horas de la configuración; el peso × filas; los días distintos y el «al menos la mitad» de R17; la huella del código v1
en `ejecutar`; las dos guardas de `importar_produccion`; los textos de T11 a T13 sin la marca de pendiente y la
ratificación en la traza; una sola raíz; las filas fuera de la raíz; y la raíz rechazada a la vista): en las 27, su
prueba falla con la mutación y pasa sin ella.

## 6. Código nuevo (escrito y probado; no toca nada sellado)

| Módulo | Qué hace (puntos del bloque) | sha256 |
|---|---|---|
| `reloj_sinca_v2.py` | verificación estructural con las dos convenciones de etiqueta, elección de la convención por T4 (unidad de T9) sobre todo SINCA y el derivado completo de la red 2, con las series (y su procedencia T8), la política leída, la región y la zona de cada serie y la base de zonas registradas y fijada por sus horas especiales (96a7b7cb…), el límite de R7 (años sin cambio de hora) declarado y la procedencia de la corrida, escrita una vez, y paso a UTC con `ZoneInfo` (R7); cada serie se lee desde los bytes cuyo sha256 registró (`leer_serie`, ronda 5); el original (a93a1eab…) no se toca | `c1eb98c52660dae3755c65a69fb2cc33e7e8d54736c269cc111bde35289795f7` |
| `unidades_v2.py` | rótulo, regla del contraste y del rótulo, 25 °C y 1 atm con las masas molares literales de R6 (O3 47,998: T12, también en el contraste; el predictor `cams_o3` del panel sigue con 47,9982 del código v1, con su huella), SNIFA; las series sin coordenada salen antes (R6, R8) | `5738943c623e3e2bf50b7b6abd7e67286fa1972dbd5543b09b04a5edcc8a354c` |
| `contraste_unidades_v2.py` | el programa del contraste versionado, con sus constantes (salvo O3, 47,998 por T12), para la segunda corrida (R6), con el derivado cerrado y antes del panel (T12 a): nada antes de la confirmación en git; NO2 y O3, la primera corrida por su huella y el derivado completo para escribir; lista cerrada, series, archivos CAMS con su sha256 antes y después de leerlos (exigidos) y cambios frente a la primera, con la procedencia de la corrida, escrita una vez (y completada si se cortó entre el CSV y el lateral); cada serie se lee desde los bytes cuyo sha256 registra el lateral (ronda 5) | `e2e9b6d37405ce331301c44cb5a569123dd3982aa0031e122ddeef84d3b1401e` |
| `duplicados_v2.py` | `pares_duplicados` y `quitar_copias`: una copia por hora (R9), con una sola regla de desempate (`orden_de_conservacion`) | `fd53bad7f7dc02822cce1ae7c1bccfc352d39f093018ca7e6772a73a172fb524` |
| `red_ampliada_v2.py` | lista cerrada, maestros de R8, propietarios, red resultante, series esperadas de la red 2, decisiones de traducción (T1 a T13), procedencia de la descarga, cláusula y camino de la 518 (con los archivos de la red 2 en `paneles/`, uno por uno), compuerta de R22: el par AP y espejo desde cualquiera de los dos, los textos de la auditoría en el espejo, `config/componentes_compartidos.json` y la ratificación de T11 a T13 antes del armado (T13: `RATIFICACION_T11_T13`, con las lecturas §8.14, §8.15 y §8.17, y los textos de T11 a T13 ya sin la marca de pendiente); la configuración confirmada en git para el anexo; y la procedencia de cada artefacto (`traza_red2`, con la traducción y la ratificación con que se escribió) (R2, R3, R8, R10, R22, §0) | `5de85a47486748c94cbffdc4de841a9a741d9338f47d0ab0bf2ba654725c47fe` |
| `derivado_red2_v2.py` | derivado SINCA red 2 con el preparador sellado cargado por su huella y `afg_lib.py` por la suya, en `amb_v2` (R4, R5, T8); para quien lo lee, el contrato de cada versión (T8 y la publicación del preparador: `files` con los dos parquet, sus filas y la huella de su esquema, sólo metadatos; versión y `digest(inputs)`), el derivado completo (R2 y R4: la raíz de `destino_por_omision`, el `plan.json` con la huella rastreada de este programa y cada versión sin ventana, con exactamente sus fuentes de la lista cerrada en todas sus columnas de identidad, con las filas que declaran esos manifiestos y, archivo por archivo, las que declaró el preparador, y con las etiquetas que deja el ranking afg, leídas sólo de `ts_local` (ronda 5); una reescritura que conserve los conteos de cada archivo y las etiquetas del ranking sólo se detecta volviendo a derivar) y las corridas equivalentes; la raíz rechazada, a la vista aunque esté fuera de la carpeta de la raíz de datos; `plan.json` con la huella de este programa y la procedencia | `eeee1995d12d22b171570a6b8e3c7f87fde54852539af8b3e4b624b99888f101` |
| `panel_red2_v2.py` | inventario (de escritura única) y copia congelada de los insumos, que se retoma si el armado se corta (R11, con TROPOMI por fecha sin límite por T11 y su conteo por año), registro del catálogo MAIAC (T5), derivado completo de la red 2 (R2), convención civil tomada del reloj de su carpeta, sobre las mismas series y vuelto a calcular (T4), segunda corrida del contraste sobre esas series y con sus cambios (R6), observaciones con R3-R9 y la red frente a la esperada, réplica del panel v1 (con `produccion.py` importado por su huella, la de cada repositorio, y sus rachas con `produccion.marcar_rachas`: T12), bandera de calidad, regímenes (R17), estaciones con propietarios (R10), observaciones float64 y estrato de propietario; base de zonas y límite de R7 comprobados en el reloj; los archivos CAMS del lateral; al retomar, se compara sólo lo que entra; la procedencia en cada json que escribe; desde la ronda 5, la regla de unidades antes de escribir nada y cada serie leída desde los bytes cuyo sha256 registró al empezar | `18fa2b9dfc5469e95e8137139032f53597ca0586c25b9fc446eec86f46f68428` |
| `pliegues_red2_v2.py` | la única fuente de pliegues, pesos, E2, bloque más influyente y regímenes de la red 2 (R13-R17), con el renombre de R13 (del f001d48c…, también si se cortó después del renombre) y el anexo: lo arma completo de los artefactos (`--anexo`), con la traducción común de todos y el estado de la procedencia de la descarga, y lo exige, con lo calculado (R15, también la evaluabilidad de E2 por protocolo, con los umbrales, los códigos de E2 y el mínimo de horas de la configuración, en el registro de la red y, la que rige, en la decisión: `evaluabilidad_e2_que_rige`; R16 con `red_original` conservado y su aviso, y R17 con su rótulo), y con `config_v2.json` confirmado en git; al reemplazar, el evento de R13 sigue primero en la bitácora | `aeebeac945fa1f2da92f53a291761f9c34fda0df813628fe2246319c262144d7` |

Las huellas cambian si el código se edita antes del commit de la traducción: `config_v2.propuesto.json` las trae en
`red_de_monitores.codigo`, se vuelven a fijar entonces y `test_red_ampliada_v2.test_huellas_del_codigo_nuevo_declaradas`
las compara con los archivos.

**Pruebas nuevas** (207, en `tests/`): `test_reloj_sinca_v2` 47, `test_unidades_v2` 20, `test_contraste_unidades_v2` 13, `test_duplicados_v2` 6, `test_red_ampliada_v2` 38, `test_derivado_red2_v2` 14, `test_panel_red2_v2` 48, `test_pliegues_red2_v2` 21. Son
sintéticas y sin red; las que leen datos reales sólo miran cabeceras, columnas de identidad, conteos y huellas (y se
saltan sin el disco), nunca valores ni métricas.

## 7. Comprobaciones con datos reales (sólo cabeceras, conteos y huellas)

- La lista cerrada se cumple (20 huellas). Maestros de R8: 109 actuales y 106 nuevas, sin códigos repetidos; fuera 518
  y 408. Red resultante igual a R2: PM2,5 107 + 2; NO2 48 + 20 + 3 SNIFA; O3 47 + 22.
- El derivado de la red 2 tiene que traer 262 series (109 de PM2,5, 79 de NO2 y 74 de O3): las de los tres manifiestos
  de las estaciones con coordenada usable (`series_esperadas_red2`); es exactamente el plan de `derivado_red2_v2`
  (los grupos sin la 518 de NO2 y O3), comprobado leyendo sólo identidades.
- La regla de unidades sobre la primera corrida reproduce las listas de R6; con un contraste sin la 518 (como será la
  segunda corrida) ya no se detiene: la 518 sale antes, por coordenadas.
- Propietarios de las 109 configuradas: 71 públicas y 38 de empresas.
- Insumos con las reglas nuevas: entra todo lo registrado antes del corte; 232,1 GB (TROPOMI 166,6; MAIAC 35,0;
  ERA5-Land 23,4; GEOS-CF 2,7; MERRA-2 2,2; capa límite 1,0; ACAG 0,94; CAMS 0,3).
- Catálogo MAIAC (T5), calculado sin escribir: las 10 teselas (h08v11, h10v11, h11v10, h11v11, h11v12, h12v12, h12v13,
  h13v13, h13v14 y h14v14; 9,0 MB) tienen archivo del 2026-09-02, antes del corte: entrarían las 10. Huella prevista de
  la lista: `038737be2430b3ef626b686ab7550b95a973e873f1e8b1e2dce630133242fa7f`. El registro se escribe al armar, después
  de la confirmación en git; si una tesela cambia antes, la huella cambia y queda a la vista.

## 8. Hallazgos para el autor (sin cambio de reglas)

1. `preparar_sinca_modelado.py --salida …/SINCA/v1_red2` fallaría (su `main` sólo admite destinos dentro de
   `SINCA/v1`); `derivado_red2_v2` usa su API, cargándolo por su huella (95f1ecd3…).
2. `load_inputs` toma la geometría de la carpeta fuente (la del 2026-10-24, excluida): se reemplaza por la del maestro
   corregido (eaeaf965…).
3. El verificador original no podía dar «hora civil» con el derivado: éste deja una fila por etiqueta y la repetición
   queda en `solapamientos.parquet`; la versión nueva usa `hora_repetida_en_fuente`.
4. `frac_lena`: el panel v1 la trae, pero `_features.py` de hoy ya no; no está en las listas cerradas de 70 y 69.
5. El ranking del derivado aplica el rango afg en la unidad nativa; el rango de R5 se aplica después de convertir.
6. **Diferencias con el cuadro del §3 del bloque** (aceptadas por el autor en T7, con el alcance que nombra: programas
   propios para la red 2, (a); `catalogo_sinca`, (b), y `metricas_v2`, (c), sin cambios; la (d), en T10): (a) los productores sellados de los
   pliegues y de la bandera no se adaptan a la red 2: `pliegues_v2.py` y la producción de la bandera de `calidad_v2.py`
   se detienen bajo el contrato con la red; la red 2 tiene sus programas (`pliegues_red2_v2`, la bandera en
   `panel_red2_v2`) y los sellados quedan como réplicas de la red original. El lector de la bandera de `calidad_v2` sí
   se adapta (reemplazos 1 y 2 de CAMBIOS): `ruta_calidad` sigue al panel en uso (`calidad_<pol>_red2.parquet`) y
   `cargar_bandera` la exige por el `calidad_sha256` del json del panel; (b) `catalogo_sinca` sigue siendo el catálogo
   v1: los maestros de R8 los lee `red_ampliada_v2`; (c) `metricas_v2` no cambia: los regímenes y el bloque más
   influyente los escribe el anexo en la configuración, y el propietario entra como estrato desde `correr_v2`; la
   tercera tarea del cuadro para `metricas_v2`, «cobertura_conocida antes y después», la calcula
   `pliegues_red2_v2.evaluabilidad_e2_red2`, queda en `pliegues_v2_red2.json` (bajo `huella_pesos`) y el anexo escribe
   la cifra de la red ampliada en `cobertura_conocida.red_ampliada`, por contaminante, que `exigir_registro` compara
   con el manifiesto (desde la cuarta revisión; antes ahí sólo había una remisión); y (d) la conversión a hora civil
   está en `reloj_sinca_v2.convertir` y en el panel, no en `preparar_sinca_modelado.py`, al que se usa por su API
   (aceptada en T10). Los nodos hermanos de `inferencia_diferencias` se agregaron a este punto después de T7: los
   cubre T12 (§8.16 c).
7. La segunda corrida del contraste lee las series nuevas (y las actuales) desde el derivado red 2, con el ranking afg
   (filas «seleccionada»), y no desde el CSV crudo como la primera: el valor es el mismo salvo en las etiquetas
   repetidas, donde rige la fila que elige el ranking.

**Lecturas nuevas de la cuarta revisión** (T7 acepta sólo las diferencias del §8.6 y la lectura de R21 (§9.4); §8.1 a
§8.5 son hallazgos sin cambio de regla y la lectura de §8.7 la cubre T12 (b)). Las §8.8 a §8.13 las acepta T12 (e)
[delegada], con la §8.12 corregida en vez de aceptada (§8.16); las §8.14 y §8.15, de la quinta revisión, y la §8.17, de
las rondas de verificación de la traducción, no las cubre ninguna decisión: entran en la ratificación de T11 a T13 antes
del armado (§9, «Queda abierto», 0, y §11, paso 0; `red_ampliada_v2.RATIFICABLES`), y la §8.14, que se aparta de la
letra de T11, se ratifica con ella; las tres quedaron ratificadas por el autor el 2026-10-26 (§9.0):

8. **«Al cerrar el panel» (R6) y el orden de R22, paso 3.** El paso 3 nombra la segunda corrida del contraste al final;
   R6 la pone «al cerrar el panel» y dice que rige. Se lee como «con la red del panel cerrada» (el derivado completo y
   el reloj escritos) y **antes** de armar el panel, que la exige (`--contraste`): orden real en
   `red_de_monitores.orden`: el registro MAIAC antes del armado (T5) y, en el armado, derivado, reloj, segunda corrida,
   panel con duplicados y calidad, y pliegues.
9. **R19, la factibilidad.** «La regla y su medición no cambian»: no se vuelve a medir con la red 2 y sus fechas quedan
   fijadas por el régimen 2019-2024 de la Enmienda 1. Como el anexo reemplaza los tramos de `criterio` por los
   calculados (R17), `factibilidad_v2.fechas_de_medicion` las toma de `criterio.valor_red_original` (reemplazo de
   CAMBIOS; `red_de_monitores.factibilidad`).
10. **R17, «los escribe en el manifiesto».** El manifiesto es `pliegues_v2_red2.json`, el mismo de R16: copia los tramos
    comunes con el sha256 de `paneles/regimenes_red2.json`, bajo `huella_pesos`; los regímenes por contaminante quedan
    además en cada json de panel, y los tres se comprueban entre sí (`verificar_regimenes`).
11. **R10 y las SNIFA.** No tienen ficha SINCA; T1(3) decide por la calificación de la ficha y, si falta, por el
    propietario, así que no las alcanza: quedan en «no informado», como las cuatro fichas sin calificación ni
    propietario (antes se las clasificaba «empresa» sin regla ni fuente). Si se quisiera «empresa», haría falta un
    documento que lo respalde y la decisión del autor.
12. **R6, masa molar de O3** (corregida por T12, §8.16). El bloque escribe 47,998 g/mol; el código usaba 47,9982, el
    valor del programa del contraste (`contraste_unidades_cams.py:39`) y de `_features.py:40`. T12 la corrige en vez de
    aceptarla: la conversión de µg/m³N a ppb (`unidades_v2.MASA_MOLAR`, `red_de_monitores.unidades.masas_molares`) usa
    47,998, la literal de R6. El contraste de la segunda corrida también usa 47,998 (`contraste_unidades_v2.M`), por
    T12, que no hace excepción para él (ronda 4 de verificación, menor 9): es su única diferencia con el programa de la
    primera corrida y `MismoProgramaTests` acepta sólo ésa. La diferencia relativa entre los dos valores es de unos
    4·10⁻⁶, así que no se espera que cambie ninguna decisión (`unidades.masas_molares_nota`). T12 corrige la conversión
    de R6 y el contraste; no toca el predictor `cams_o3` del panel, que sigue convirtiéndose con 47,9982
    (`_features.py:40` y `:104`), porque el panel usa el código de la v1 con su huella (`HUELLAS_CODIGO_V1`), como pide
    R11 («el de la v1 … con sus huellas registradas»): en el armado de la red 2 conviven las dos masas molares del O3,
    con un efecto numérico nulo (ronda 5 de verificación, menor 6; lo dicen también el docstring de `unidades_v2` y
    `masas_molares_nota`).
13. **R11, «con su lista y sus huellas en el json del panel».** La lista de cada archivo (ruta, origen y sha256, ≈ 10⁵
    entradas) está en `insumos_red2/congelados.json` y el inventario completo en `insumos_red2/inventario.json`; el
    json del panel los cita por su sha256 (`insumos.congelados_sha256`, `insumos.inventario_sha256` e
    `insumos.lista`). Se lee «por referencia, con huella»; copiar la lista en cada json de panel no agrega
    verificación.
14. **T11, «el anexo lista por año las órbitas que entran así».** Se lee también por referencia (quinta revisión, menor
    15): el anexo trae, en `registro_de_la_red.tropomi_por_fecha`, el total, el conteo por año de adquisición y la huella
    de la lista de rutas (`huella_lista`, de `panel_red2_v2.por_fecha_de_modificacion`); la lista misma, órbita por
    órbita, está en `insumos_red2/inventario.json`, cuyo sha256 registra el anexo (`insumos.inventario_sha256`). Poner
    las 3.826 rutas en el anexo no agrega verificación; si el autor las quiere ahí, es un cambio de forma.
15. **R7, años sin cambio de hora.** La regla está anclada (R7: «sin transiciones» sigue la regla general); lo que
    produce se declara (quinta revisión, menor 4): en 2015 ninguna zona tiene cambio de hora; America/Punta_Arenas
    (RXII: C05) no lo tiene en 2017-2026 ni America/Coyhaique (RXI: B03, B04 en sus tres contaminantes, B05 y B06) en
    2025-2026. Esas unidades dan `sin_transiciones`, no votan en T4 y quedan en UTC−4 fijo; un exportador en hora civil
    está esos años en −03 todo el año, así que el error sería de 1 h en todas sus horas, no sólo en verano. El reloj
    cuenta las unidades `sin_transiciones` cuyo año anterior o siguiente da `hora_civil` con la convención elegida
    (`reloj_sinca_v2.sin_transiciones_junto_a_civil`) y la cifra va al json del panel y al anexo. Tratar esos años de
    otro modo (convertir 2015, por ejemplo) sería una regla nueva y queda para el autor.

**Diferencias y lecturas aceptadas por T12** ([delegada], 2026-10-26; ratificada por el autor el 2026-10-26, §9,
«Queda abierto», 0). Es un grupo aparte del de T7 (§8.6): las hallaron las verificaciones de la madrugada del
2026-10-26 y T7 no las cubría.

16. **T12.** Se aceptan cinco y se corrige la sexta:
    - (a) **La segunda corrida del contraste, antes del panel.** Se hace con el derivado cerrado y antes de armar el
      panel, para que rija sobre él: es la lectura de «al cerrar el panel» (R6) y de R22, paso 3 (§8.8;
      `red_de_monitores.unidades.contraste_segunda_corrida`, `red_de_monitores.orden`, el docstring de
      `contraste_unidades_v2` y el párrafo de entrada del bloque en el contrato, «Texto que rige», que la nombra).
    - (b) **El derivado de la red 2 rehace las 107 actuales.** Vuelve a derivar completas las 107 estaciones actuales
      desde `DATOS/sinca` (sellado más actualización) en una sola raíz `v1_red2`, que leen el reloj, el contraste y el
      panel; lo exige R4 (`derivado_red2_v2.insumos_red2`). Quien lo lee para escribir lo exige completo, con todas sus
      fuentes y sin ventana (`exigir_derivado_completo`, §3.6).
    - (c) **Nodos hermanos.** `inferencia_diferencias.influencia.bloque_mas_influyente` y
      `metricas.desagregaciones.regimen_de_predictores.criterio` no se vuelven una regla, como pide el §3: llevan la
      regla al lado, en nodos hermanos, `bloque_mas_influyente_enmienda_2` (de `bloque_mas_influyente`) y, desde la ronda
      4 de verificación (menor 17), `criterio_enmienda_2` (de `criterio`, con regla y lectura; antes la regla estaba
      dentro de `criterio`); los valores siguen en `bloque_mas_influyente` y en `criterio` (`valor` y
      `valor_red_original`), donde los leen `decision_v2`, `metricas_v2.regimenes_de_config`, `factibilidad_v2` y
      `con_el_anexo`, y los escribe el anexo (`pliegues_red2_v2.con_el_anexo`), que `exigir_lo_calculado` comprueba.
      Estaba en el §8.6 (c), agregado después de T7.
    - (d) **Las raíces del derivado de la red 2.** Viven en `derivado_red2_v2` (`raiz_derivados`,
      `destino_por_omision`), no en `_rutas_v2`, que sólo agrega el derivado v1 a las raíces de sólo lectura
      (reemplazo 1 de `_rutas_v2.py` en CAMBIOS).
    - (e) **Las lecturas §8.8 a §8.13**, entre ellas las SNIFA como «no informado» (R10, §8.11); la §8.12 no se acepta:
      se corrige.
    - **Se corrige:** (1) la masa molar del O3 es la literal de R6, 47,998 g/mol, en la conversión y en el contraste
      (§8.12); (2) el panel usa `produccion.py` con su huella fijada: `panel_red2_v2.HUELLAS_CODIGO_V1` la trae por
      repositorio (AP dd2db2ef…, espejo e9e18b5a…, el archivo «adaptado» de `config/componentes_compartidos.json`), el
      armado la comprueba (`verificar_codigo_v1`, también la de `_red_adicional.py`, que importa) y, después de
      `importar_v1`, lo importa (`importar_produccion`: con `_comun_modelo` y `_common` ya cargados con la raíz de la
      copia congelada y `MODELO_1KM_RED_ADICIONAL=0`, importarlo no agrega efectos) y marca las rachas con
      `produccion.marcar_rachas`, la regla de `produccion.observaciones`. La función `produccion.observaciones` misma no
      se puede usar, porque lee el derivado y el catálogo de la v1 (`series_sinca` y `estaciones_usables`) y no admite
      las series de la red 2: lo demás de su regla (las estaciones usables, aquí las de celda) se replica, y
      `test_panel_red2_v2.ObservacionesTests.test_misma_regla_que_produccion_observaciones` prueba la equivalencia con
      datos sintéticos (ronda 4 de verificación, mayor 4 y menor 16; antes se daba como razón los efectos de importar
      `produccion.py`, que no ocurren en el armado).

**Lectura de la traducción de las rondas de verificación** (de la ronda 4, corregida en la ronda 5 para aplicar la letra
de R15; ninguna decisión la cubre, así que entra en la ratificación de T11 a T13 antes del armado: §9, «Queda abierto»,
0, §11, paso 0, y `red_ampliada_v2.RATIFICABLES`; ratificada por el autor el 2026-10-26, §9.0):

17. **R15 en la decisión.** «La evaluabilidad de E2 se calcula sobre el panel de R11, con los mismos umbrales, antes de
    cualquier ajuste» y, en su «Por qué», «Calcularlo antes cierra la puerta a declararlo según convenga»:
    `pliegues_v2_red2.json` la registra antes del ajuste (`pesos.<pol>.evaluabilidad_e2`, con los umbrales, los códigos
    de E2 y el mínimo de horas del día de la configuración, como la decisión) y el anexo la escribe en
    `registro_de_la_red.evaluabilidad_e2`; la decisión la vuelve a calcular sobre sus pares (`evidencia_de_decision`).
    **Rige la registrada.** `correr_v2.decidir`, con la red 2, entrega a `decision_v2` (condición 3), por protocolo, una
    copia de la evidencia con el «evaluable» registrado en vez del de la evidencia
    (`pliegues_red2_v2.evaluabilidad_e2_que_rige`) y deja el de la decisión sólo como registro en `decision.json`
    (`evaluabilidad_E2_red2`: la que rige, la de la decisión, si coinciden y la huella de la evidencia consolidada). Las
    dos coinciden cuando los pares de la decisión cubren las filas del panel; si difieren (basta que un candidato deje
    filas sin predecir para que cambie la fracción de peso de la decisión), no hay nada que elegir después de ver las
    métricas: rige la registrada. Si la registrada es evaluable y la evidencia no tiene pares E2, la decisión se detiene:
    es un defecto de la corrida (la bandera o los pares de la decisión) que se corrige rehaciendo la consolidación, no
    una elección. Con E2 no evaluable en la registrada, la condición 3 no bloquea (Enmienda 1, punto 7). Lo que se
    ratifica de esta lectura es el mecanismo (la copia de la evidencia con el «evaluable» registrado y la parada por
    defecto de la corrida); qué evaluabilidad rige no queda abierto: lo dice R15.
18. **R17, la familia indicadora ACAG** (comprobación de la aplicación, menor). R17 dice: «Una familia está disponible
    en un año si alguna de sus columnas es finita en al menos la mitad de los días». La columna `acag_clim` vale 0 o 1
    en todas las filas, así que con la letra la familia estaría disponible todos los años. El código
    (`panel_red2_v2.py`, `ok = (v == 1.0)` para las indicadoras) la lee con la regla fila a fila del Complemento 4.4,
    ya ratificado: disponible sólo cuando `acag_clim = 1`. Es una lectura nueva, aceptada **[delegada]** (T15, en
    `APH/auditoria/20261024/sinca_al_modelo/decisiones_autor_traduccion_20261026_lecturas.md`), ratificada por el autor
    el 2026-10-26 (en ese mismo archivo). El código queda como está.
19. **R6, la masa molar del O3 en la segunda corrida del contraste.** T12 corrigió la masa a 47,998 g/mol en
    `unidades_v2` y en la configuración. El contraste (`contraste_unidades_v2.M`) conserva 47,9982, porque R6 pide la
    segunda corrida «con el mismo programa» y `MismoProgramaTests` compara sus constantes con las de la primera. La
    diferencia es de 4·10⁻⁶ relativa y no mueve ningún veredicto de unidades. Es una lectura aceptada **[delegada]**
    (T15), ratificada por el autor el 2026-10-26 (`decisiones_autor_traduccion_20261026_lecturas.md`).

## 9. Decisiones del autor (2026-10-26) y lo que queda

**Decidido** (`decisiones_autor_traduccion_20261025.md`, secciones del 2026-10-26; fdfbfa31… antes de la ratificación y
a0b970d2… con ella, §9.0):

1. **Convención de la etiqueta en hora civil (T4).** No está documentada (`config/sinca/politica_temporal.json` la deja
   como hipótesis, su README no dice nada y `docs/SINCA_SEMANTICA_PENDIENTE.md` cita normas con las dos lecturas), así
   que la deciden las horas: una sola convención para todo SINCA, antes del paso a UTC y sólo con las etiquetas de los
   días de cambio de hora. Votan las unidades del veredicto de R7, estación × contaminante × año local (T9): se cuentan
   las que dan `hora_civil` con `fin` y no con `inicio_mas_1h`, y al revés; gana la de más y, si empatan (también en
   cero), `inicio_mas_1h`. Los dos conteos y la elegida salen en el
   `resumen.json` del reloj, van al json del panel y al anexo. Efecto que queda: si en la red conviven exportadores con
   las dos convenciones, los de la perdedora no se detectan y sus horas de verano quedan una hora corridas; los conteos
   del anexo dirán si ese caso existe.
2. **Catálogo MAIAC (T5).** Se registran sus 10 teselas con su sha256 antes del armado y entran como los demás
   insumos; las de archivo posterior al corte quedan fuera y se anotan (hoy no hay ninguna).
3. **Espacio (T6).** La copia congelada (≈ 232 GB) va al disco interno; hoy hay ≈ 462 GB libres.
4. **Revisión y aceptación (T7).** El autor acepta las diferencias que listaba el §8.6 (programas propios para la red 2;
   `catalogo_sinca` y `metricas_v2` sin cambios) y la lectura de R21 («el `pliegues_v2.json` de este bloque» =
   `pliegues_v2_red2.json`; el manifiesto de la red original queda intacto como `pliegues_v2_reemplazado_<marca>.json`).
   Lo que se agregó después al §8.6 (los nodos hermanos de `inferencia_diferencias`) lo cubre T12 (§8.16 c).
5. **R5 (T8).** Rige el sha256 de `afg_lib.py` (4391787a…); las huellas del árbol de sintaxis, como procedencia.
6. **Conversión civil (T10).** Aceptada la diferencia §8.6 (d).
7. **TROPOMI por fecha de modificación: los 146 archivos de 2024 (T11, [delegada]).** Decidido con la opción
   recomendada, por delegación del autor y sin que la viera; ratificada por el autor el 2026-10-26 (abajo, «Queda
   abierto», 0).
   Entran por su fecha de modificación, como las de 2019-2022: son órbitas antiguas, del formato del legado, sin
   registro propio y anteriores al corte, lo que describe T1(4); `TROPOMI_MTIME_ANIOS` queda sin límite (None). Si la
   regla se limitara a 2018-2022, diciembre de 2024 quedaría casi sin TROPOMI; si se bajaran de nuevo, su registro
   sería posterior al corte y no entrarían. El anexo lista por año las que entran así (hoy 3.826: 1.041 de 2019, 1.045
   de 2020, 1.040 de 2021, 554 de 2022 y 146 de 2024; `resumen_inventario`, `registro_de_la_red.tropomi_por_fecha`).
   Lo que se sabía, sólo con metadatos (nombres, fechas, registros):
   - las 3.826 son del formato anterior (sufijo `.chile.nc`, el rectángulo continental del legado); todas las que
     tienen evento llevan los sufijos nuevos (`.continente.chile.nc` y los de las islas);
   - las de 2019-2022 se escribieron el 2026-08-09 y las 146 de 2024 el 2026-08-10, entre las 05:34 y las 08:42 UTC,
     antes de que existieran los registros (el primero es del 2026-09-02);
   - la migración del legado continental (eventos `inicio_migracion_legado_continental`, del 2026-09-02 al 2026-09-14)
     avanzó en orden de fechas desde 2022-07: su último tramo (ejecución del 2026-09-14 10:16 UTC, 1.182 validadas, de
     2023-07 a 2024-12) no tiene evento de fin y se cortó el 2024-12-02, después de las 5 órbitas con evento de 2024-12-01
     y 2024-12-02;
   - por eso quedaron sin migrar las 138 órbitas OFFL 02.08.00 del 2024-12-02 al 2024-12-31 (de 4 a 6 por día) y 8
     órbitas RPRO 02.06.00 sueltas: 6 del 16 y 17 de febrero (días sin ninguna otra órbita) y 2 del 10 y 11 de mayo (esos
     días sí tienen otras órbitas OFFL con evento); ninguna de las 146 tiene otra copia con evento y ningún registro las
     menciona;
   - las ejecuciones del 2026-10-23 y 24 (sin migración) bajaron de nuevo 2018 y 2025-2026, pero no 2024-12.
8. **Diferencias y lecturas que T7 no cubría (T12, [delegada]).** Se aceptan las cinco del §8.16, (a) a (e), y se
   corrigen la masa molar del O3 (47,998, la literal de R6, en la conversión y en el contraste) y el uso de
   `produccion.observaciones` (`produccion.py` importado con su huella fijada, la de cada repositorio, y sus rachas con
   `produccion.marcar_rachas`; lo demás, replicado con prueba de equivalencia). Ratificada por el autor el 2026-10-26
   (abajo, «Queda abierto», 0).
9. **Orden de la ratificación (T13, [delegada]).** El commit local de la traducción (T2) puede hacerse antes de la
   ratificación; el armado no: no empieza hasta que el autor ratifique T11, T12 y T13 (§11, paso 0). Si cambia alguna,
   se hace otro commit antes del armado. El commit local se puede reemplazar; la copia congelada y los json del panel,
   de escritura única, no. Ratificada por el autor el 2026-10-26 (abajo, «Queda abierto», 0).

**Queda abierto:**

0. **Ratificación de T11, T12 y T13 por el autor, antes del armado (T13, [delegada]).** Las tres llevan la marca
   [delegada]: las tradujo esta versión (código, configuración y pruebas), pero el autor no las vio. Con ellas se
   ratifican las lecturas que ninguna decisión cubría: §8.14 (T11 por referencia: el anexo trae el conteo por año y la
   huella de la lista; la lista, en `inventario.json`), §8.15 (el límite de R7 en los años sin cambio de hora) y §8.17
   (R15 en la decisión: el mecanismo con que rige la evaluabilidad de E2 registrada antes del ajuste y la parada por
   defecto de la corrida). El commit local de la traducción (§11, paso 1) puede hacerse antes de la ratificación; el
   armado (§11, paso 2) **no empieza** hasta que el autor ratifique T11, T12 y T13 (§11, paso 0), y el código lo hace
   cumplir: la compuerta se detiene mientras `red_ampliada_v2.RATIFICACION_T11_T13` esté vacía (`exigir_ratificacion`).
   La ratificación va en otro commit de la traducción antes del armado, en AP y en el espejo, que la anota en
   `decisiones_autor_traduccion_20261025.md` (eso cambia su huella) y, si cambia alguna decisión o lectura, lleva
   también ese cambio: la compuerta (`ARCHIVOS_DEL_ESPEJO`) se detiene desde AP y desde el espejo hasta que ese commit
   cambie `red_ampliada_v2.py` (la huella nueva en `DECISIONES_TRADUCCION` y en `ARCHIVOS_DEL_ESPEJO`;
   `RATIFICACION_T11_T13` llena, con esa huella y cada una de T11, T12, T13, §8.14, §8.15 y §8.17 «ratificada» o
   «cambiada»; los textos de T11, T12 y T13 de `DECISIONES_TRADUCCION`, que dejan de decir «pendiente de que el autor
   la ratifique» y dicen «ratificada por el autor el AAAA-MM-DD» o «cambiada por el autor el AAAA-MM-DD», con la fecha
   de la ratificación (`MARCA_DE_RATIFICACION`; la compuerta lo exige, porque los json de escritura única del armado
   copian esos textos, y cada artefacto registra la ratificación en `traza.traduccion.ratificacion`; ronda 5 de
   verificación, menor 21); y lo que cambie la decisión: `panel_red2_v2.TROPOMI_MTIME_ANIOS` si cambia T11; las piezas
   del §8.16 si cambia T12), `config_v2.json` (`contrato.enmiendas[2].decisiones_de_traduccion`, con T11 a T13 sin la
   marca de pendiente y con la de la ratificación, como en el código; `red_de_monitores.ratificacion_t11_t13.valor`,
   igual a la constante; y `red_de_monitores.codigo`), `tests/test_config_v2.py` (su `SHA_DECISIONES_TRADUCCION`),
   `tests/test_red_ampliada_v2.py` sólo si la ratificación cambia la redacción de T11 a T13 más allá de esas marcas (sus
   partes esenciales, que `test_decisiones_iguales_en_el_codigo_y_en_la_configuracion` compara; las pruebas de la
   ratificación ya no dependen del valor de la constante ni la huella se fija a mano: ronda 5, menor 25), si la
   ratificación cambia T12 (a), el contrato (`DISENO_AMBIENTAL_V2.md`: su párrafo de entrada «Texto que rige» la
   nombra) con su huella nueva en `contrato.sha256` de `config_v2.json` (en sus dos lugares), en
   `tests/test_red_ampliada_v2.py` (`CONTRATO_PROPUESTO`) y en §2 (ronda 5, menores 14 y 16), en el espejo el archivo
   de decisiones, y `config/componentes_compartidos.json` regenerado. El commit local se puede reemplazar; la copia
   congelada y los json del panel, de escritura única, no: por eso nada del armado se escribe antes. Esto reemplaza el
   plazo anterior de T11 («antes del commit o, a más tardar, antes de publicar `inventario.json`; si no llega, T11 rige
   tal como está»; cuarta revisión, menor 16) y el camino de un commit nuevo a mitad del armado por T11 (quinta
   revisión, menor 25), que ya no hace falta.

   **Hecha el 2026-10-26, a las 11:23 hora de Chile.** A la pregunta «¿Cómo ratifica las decisiones que tomé por usted
   mientras dormía (T11 a T13 y T15 de la red ampliada, D11 a D51 de M1)?», el autor respondió «Ratificarlas todas»:
   T11, T12, T13, §8.14, §8.15 y §8.17 quedan «ratificada», sin cambios (T15, con §8.18 y §8.19, quedó anotada en
   `decisiones_autor_traduccion_20261026_lecturas.md`). La ratificación se anotó al final de
   `decisiones_autor_traduccion_20261025.md`, en el espejo (fdfbfa31… →
   `a0b970d2fbbf08a11c28d24c075ca1dd81ef2509d2093d243c1fc7a95dad3920`), y cambian, en AP y en el espejo:
   - `red_ampliada_v2.py` (85e16a9d… → 5de85a47…): la huella nueva en `DECISIONES_TRADUCCION` (y, por ella, en
     `ARCHIVOS_DEL_ESPEJO`); `RATIFICACION_T11_T13` = {fecha 2026-10-26, esa huella, las seis «ratificada»}; T11 a T13
     con «ratificada por el autor el 2026-10-26»; `DECISIONES_SIN_RATIFICAR` sigue en fdfbfa31…;
   - `panel_red2_v2.py` (2750d2dc… → 18fa2b9d…): sólo el comentario de `TROPOMI_MTIME_ANIOS`, que decía «T11
     [delegada, por ratificar]» y ahora dice «[delegada, ratificada por el autor el 2026-10-26]», como
     `insumos_de_hoy.tropomi_por_fecha.regla`; el valor (None) y el número de líneas no cambian. La compuerta no lo
     exigía (es un comentario: `MARCAS_DE_PENDIENTE` no lo mira y los json no lo copian), pero contradecía la
     ratificación;
   - `config_v2.json` (02d8c386… → 51df5063…): `contrato.enmiendas[2].decisiones_de_traduccion` con la huella nueva y
     T11 a T13 con la marca; `red_de_monitores.ratificacion_t11_t13.valor`, igual a la constante;
     `red_de_monitores.codigo`, con las huellas nuevas de `red_ampliada_v2.py` y de `panel_red2_v2.py` (y su nota); y
     `insumos_de_hoy.tropomi_por_fecha.regla`, también con la marca;
   - `tests/test_config_v2.py` (0e2eb6ec… → 186d590b…): su `SHA_DECISIONES_TRADUCCION`, con su reemplazo y su huella
     de resultado en CAMBIOS;
   - `tests/test_red_ampliada_v2.py` (03216071… → 6f52c755…), aunque la redacción de T11 a T13 no cambia más allá de
     las marcas: sus pruebas de la ratificación armaban los casos «pendientes» con los textos vigentes, que ya no lo
     están; ahora los arman ellas (`textos_pendientes`), y la prueba de las decisiones exige, ya ratificadas, la huella
     nueva, la ratificación anotada en el archivo y `exigir_ratificacion` sin detenerse;
   - en esta carpeta, `config_v2.propuesto.json` (igual a `config_v2.json`), `CAMBIOS_AL_CODIGO_SELLADO.md`
     (95bd3463… → 84362a57…) y este archivo.

   No cambian el valor de `panel_red2_v2.TROPOMI_MTIME_ANIOS`, las piezas del §8.16 ni el contrato (T12 (a) queda
   igual; sigue en 5140306e…). M1 fija la huella de `config_v2.json` (FIJ-4, D51): la que rige desde la ratificación
   es 51df5063…, no 02d8c386…, que D51 citaba antes del paso 0. Faltan el commit de la ratificación, en AP y en el
   espejo (con `panel_red2_v2.py`), y `config/componentes_compartidos.json`, que se regenera aparte antes del armado
   (§11.1): hasta entonces la compuerta sigue detenida por ellos, no por la ratificación.
1. **Revisión nueva (T7)** de las correcciones y de T4 y T5 contra el bloque anclado.
2. **Aplicar (T2)**, sólo después de esa revisión: poner el contrato y la configuración propuestos, aplicar los
   reemplazos, volver a fijar las huellas del código nuevo, confirmar en git en AP y en el espejo (commit local, sin
   envío; en el espejo, también `auditoria/20261024/sinca_al_modelo/decisiones_autor_traduccion_20261025.md`, entonces sin
   rastrear, con su huella final, porque la configuración la cita y AP no puede llevarlo: `/auditoria/` está excluida;
   la compuerta lo exige rastreado y con su sha256, con el bloque y las decisiones del autor: `ARCHIVOS_DEL_ESPEJO`),
   con la carpeta `propuesta_red_ampliada/`, y regenerar `config/componentes_compartidos.json` en el mismo commit (la
   compuerta compara su huella de cada archivo de la traducción: `verificar_componentes`).
3. **Anexo «Registro de la red v2»**: `pliegues_red2_v2.py --anexo` arma, sin escribir nada, el bloque completo desde
   los artefactos (`anexo_desde_artefactos`): `registro_de_la_red` (reloj con las huellas de los veredictos, del
   resumen y de las series, los dos conteos y la elegida; registro del catálogo MAIAC con su sha256 y su huella de
   teselas; segunda corrida del contraste con su CSV y su lateral; panel; calidad; duplicados; lista cerrada; insumos;
   órbitas de T11 por año; los pliegues con su sha256 y sus dos huellas; los regímenes con la huella de
   `regimenes_red2.json`), el bloque más influyente, los tramos comunes y la cobertura de E2 de la red ampliada; los
   valida con `exigir_registro` y los muestra; el autor los pega donde dice su «donde» (`con_el_anexo` hace lo mismo
   sobre una copia): si no, `exigir_registro` detiene la corrida. Las pruebas selladas que fijaban valores de la
   Enmienda 1 (`test_metricas_v2.test_cinco_regimenes_iguales_a_la_configuracion`,
   `test_config_v2.test_cinco_regimenes_contiguos` y `test_segunda_prueba_e_influencia`,
   `test_decision_v2.test_regla_de_la_configuracion`, desde la cuarta revisión también las tres aserciones de
   `test_correr_v2` y `test_factibilidad_v2.FechasTests`) ya leen lo que rige por los reemplazos de la traducción, así
   que el anexo no toca pruebas (comprobado con un anexo simulado, §5.3). El anexo registra además, en una entrada
   propia (`registro_de_la_red.procedencia_descarga`, de `procedencia_descarga_desde_artefactos`), el estado de cada
   versión del descargador de `red_de_monitores.procedencia_descarga`: «en_git» (el programa del commit tiene esa
   huella), «recuperada» (una copia del historial de versiones del Drive puesta antes del anexo en
   `<raíz v2>/procedencia_descarga/`, con su ruta y su sha256, comparado con 647f5518… o 93f20aeb…) o «perdida»; y la
   traducción común de los artefactos (`registro_de_la_red.traduccion`). Nada de eso obliga a tocar el código ni las
   pruebas después del armado (quinta revisión, menor 22). Si la 518 tiene antes una coordenada oficial, entra con las mismas reglas; después, no. Si aparece
   después de empezar el armado, el camino para que entre es el de `red_ampliada_v2.CAMINO_518`: maestro corregido
   nuevo con su huella en la lista cerrada, commit nuevo de la traducción, lo que el armado escribe una sola vez movido
   a mano a un respaldo con el motivo «R8, 518» (las carpetas del reloj, de la segunda corrida y de los insumos, el
   enlace de las estaciones nuevas y, de `paneles/`, sólo los archivos de la red 2, uno por uno:
   `red_ampliada_v2.ARCHIVOS_RED2_EN_PANELES`; la carpeta guarda la bandera de la red original), y registro MAIAC (T5,
   antes del armado), derivado, reloj, segunda corrida, panel y pliegues (con `--reemplazar --motivo «R8, 518»`) otra
   vez.
   Si se prefiere cerrar el plazo al empezar el armado, es una decisión del autor.
4. **R21 en el protocolo meteorológico**: registrar ahí, antes de M3-4, la lectura de R21 (π^mon con
   `pliegues_v2_red2.json` y las tablas laterales de M6 sobre el panel de la red 2).
5. **`scripts_modelo_1km/meteo_combinada/ambiental.py`** (por escribir en M1): `lateral_monitores` tiene que leer el
   panel de la red 2 (R21).
6. **`scripts_modelo_1km/o3_next/`**: universo, unidades, reloj y esquema E1/E2 de la rama O3 en su propio diseño, antes
   de su primer ajuste (R20).
7. **La compuerta en el espejo**: `exigir_traduccion_confirmada` revisa el par AP y espejo APH (mismos bytes y
   confirmados en los dos git), se lance el programa desde AP o desde el espejo, y en el espejo los textos de la
   auditoría que cita la configuración; el commit tiene que hacerse en los dos.

## 10. Costo medido con una muestra pequeña (sin escribir nada) y proyección

| Paso | Muestra medida | Proyección en serie |
|---|---|---|
| Derivado red 2 (262 series, 62,1 millones de filas fuente) | 3 series (880.715 filas): 8,1 s | ≈ 0,3 h con la publicación |
| Reloj, segunda corrida del contraste, inventario, enlaces nuevos | — | ≈ 5 min |
| Copia congelada de los insumos (232,1 GB) | lectura y copia de archivos no cacheados: ≈ 312 MB/s | ≈ 0,2 h (hasta 0,5 h con el disco ocupado) |
| Satélites diarios, 202 celdas, 9.794 días | 0,18-0,20 s por día | ≈ 0,6 h |
| Paneles PM2,5 (≈ 10,0 millones de filas) y NO2 (≈ 6,9 millones) | 9,5e-5 s por fila | ≈ 0,45 h |
| Pliegues, pesos y E2 | 11,5 s por millón de filas y 5 protocolos | ≈ 5 min |
| **Total** | | **≈ 1,8-2,1 h en serie; ≈ 0,8-1,1 h con 8 procesos** |

## 11. Orden para aplicarla (R22)

0. **Ratificación de T11, T12 y T13 por el autor**, con las lecturas §8.14, §8.15, §8.17, §8.18 y §8.19 (T13 y T15, [delegadas]; §9,
   «Queda abierto», 0). El armado (paso 2) no empieza hasta que el autor las ratifique, y la compuerta lo exige
   (`red_ampliada_v2.RATIFICACION_T11_T13`, repetida en `red_de_monitores.ratificacion_t11_t13`, y los textos de T11 a
   T13 ya sin la marca de pendiente). La ratificación va en otro commit de la traducción, en AP y en el espejo, antes
   del armado (con lo que cambie, si cambia algo): los archivos de §9.0, también `tests/test_red_ampliada_v2.py` si
   cambia la redacción de T11 a T13 más allá de las marcas de ratificación, y el contrato con su huella si cambia T12
   (a). El commit local del paso 1 puede hacerse antes de la ratificación y se puede reemplazar; la copia congelada y
   los json del panel, de escritura única, no.
   **Hecho el 2026-10-26** (11:23 hora de Chile, «Ratificarlas todas»): las seis de `RATIFICABLES` (T11, T12, T13,
   §8.14, §8.15 y §8.17), «ratificada» y sin cambios, con el archivo de decisiones en
   `a0b970d2fbbf08a11c28d24c075ca1dd81ef2509d2093d243c1fc7a95dad3920` (antes fdfbfa31…); T15 (§8.18 y §8.19), en
   `decisiones_autor_traduccion_20261026_lecturas.md`. Los archivos que cambian y sus huellas, en §9.0. Falta su commit,
   en AP y en el espejo; el armado espera además `config/componentes_compartidos.json` regenerado (§11.1).
1. **Revisión nueva** (T7) y **traducción** (T2): §9, «Queda abierto», 1 y 2. Este commit local puede hacerse antes de
   la ratificación del paso 0 (T13).
   El commit, en AP y en el espejo, lleva también `scripts_pipeline/geometria_sinca_ampliacion.py`,
   `scripts_pipeline/descargar_sinca_ampliacion.py` y sus pruebas (`scripts_pipeline/tests/test_geometria_sinca_ampliacion.py`
   y `test_descargar_sinca_ampliacion.py`), `scripts_pipeline/descargar_sinca_meteorologia.py` y su prueba
   (`scripts_pipeline/tests/test_descargar_sinca_meteorologia.py`), todos entonces sin rastrear, la carpeta
   `scripts_modelo_1km/v2/propuesta_red_ampliada/` (sus cuatro archivos, que no se borran) y
   `config/componentes_compartidos.json` regenerado; la compuerta los exige todos (`ARCHIVOS_TRADUCCION`) y compara la
   huella de cada uno con la que registra ese manifiesto. El módulo meteorológico es de la rama meteorológica: su
   entrada en el commit se coordina con quien trabaja en ella (los bytes son iguales en AP y en el espejo). En el
   espejo entran además el archivo de decisiones de la traducción con su huella final (§9, 2), que la compuerta exige
   rastreado y con su sha256, junto al bloque y a las decisiones del autor (`ARCHIVOS_DEL_ESPEJO`).
   - **`config/componentes_compartidos.json` se coordina con los otros frentes** (quinta revisión, menor 20). Lo editan
     también la DMC y la rama meteorológica, y hoy está modificado sin confirmar en AP y en el espejo. Antes de
     regenerarlo para la traducción, esos frentes confirman sus cambios (si no, el commit de la traducción se llevaría
     su trabajo pendiente y registraría la huella de su código en curso, porque sus grupos incluyen
     `scripts_modelo_1km/**` y `scripts_pipeline/**`); y nadie lo toca mientras dure el armado (§11.2): la compuerta
     lo exige rastreado y sin cambios en cada uno de los seis pasos, así que una edición sin confirmar de otro frente
     detiene todos los programas de la red 2.
   - **Lo que está sin rastrear bajo `scripts_modelo_1km/v2` y no es de la traducción** (quinta revisión, menor 19):
     `piloto_perdidas_sin_dmc.py`, `preflight_pre_dmc.py`, `tests/test_meteorologia_v2.py`,
     `tests/test_piloto_perdidas_sin_dmc.py` y `tests/test_preflight_pre_dmc.py` (del 2026-10-13), y en el espejo además
     `meteorologia_v2.py` (en AP, confirmado desde 4b50b0d). `_traza_v2.commit_git` los cuenta
     (`--untracked-files=all`) y `correr_v2.verificar_sellado` detendría el paso 4 («sellado pendiente», salvo
     `--sin-sellar`); la compuerta de R22 no los mira (sólo `ARCHIVOS_TRADUCCION`) y la traza de cada artefacto los
     lista en `git.v2_sin_commit`. Antes de M3-4 se confirman en un commit coordinado con sus ramas, en AP y en el
     espejo, o se sacan de `scripts_modelo_1km/v2`; no entran en el commit de la traducción.
   - **Efecto sobre la rama v3, sin rastrear** (ronda 4 de verificación, menor 23). `scripts_modelo_1km/v3/` (de
     ablación) fija en `config_preparacion_v3.json` las huellas de `_rutas_v2.py` (eb8a92d2…) y de `config_v2.json`
     (232c75b3…), que la traducción cambia. Después del commit, `runner_v3.plan()` informará «SHA v2 no coincide» y
     `motors()` se detendrá con «Código/config v2 cambió», así que la prueba que entrena con la plantilla
     (`tests/test_runner_produccion_v3.py`) fallará hasta que quien lleva esa rama actualice sus huellas fijadas. No
     cambia nada de la traducción; se avisa a ese frente.
   - **Efecto sobre la rama meteorológica, sin rastrear y en curso** (ronda 5 de verificación, menores 15 y 27).
     `scripts_modelo_1km/meteo_combinada/fijados.py` fija, dentro de `HUELLAS_CODIGO` (FIJ-4, «§9.3»),
     `SHA_CORRER_V2` (534e484b…) y `SHA_CONFIG_V2` (232c75b3…), que son el origen de `correr_v2.py` en CAMBIOS y la
     configuración sellada; `tests/test_fijados.py:77` exige `comprobar_codigo_fijado(AP, APH) == []`,
     `tests/test_particiones.py` (líneas 33 y 199, `_SHA_CONFIG_V2`) exige esa huella de `config_v2.json`, y
     `DISENO_IMPLEMENTACION_M1.md` (líneas 1374-1375) dice «correr_v2.py (no se toca en M1)» con las dos huellas.
     Desde el commit de la traducción, que T13 permite antes de la ratificación, `correr_v2.py` pasa a la huella de
     resultado de su sección de CAMBIOS y `config_v2.json` a la de `config_v2.propuesto.json` (§2), así que esas dos
     pruebas fallarán hasta que esa rama actualice lo que fija (`fijados.SHA_CORRER_V2`, `SHA_CONFIG_V2`,
     `test_particiones._SHA_CONFIG_V2` y la tabla de `DISENO_IMPLEMENTACION_M1.md`). Además, el protocolo meteorológico
     v2.2 (APH, `auditoria/20261023/meteo_combinada/enmienda1/PROTOCOLO_METEO_COMBINADA_v2.2.md`, líneas 913-922) prevé
     su propio cambio a `Contexto.desde_disco` de `correr_v2.py` (`lateral=None` y `--lateral-meteo`), el mismo lugar
     que tocan los reemplazos 1, 3 y 4, y a `config_v2.json`: si ese cambio entrara antes, los orígenes de CAMBIOS ya no
     coincidirían y la propuesta no se podría aplicar tal como está. El orden de los cambios a `correr_v2.py` y
     `config_v2.json` se acuerda con ese frente antes del commit de la traducción: lo previsto es que la traducción vaya
     primero y que la enmienda meteorológica de `Contexto.desde_disco` se escriba sobre el `correr_v2.py` traducido. La
     traducción no toca esa carpeta; se avisa a ese frente.
   - **Lo que se hizo al confirmar (2026-10-26).**
     - `config/componentes_compartidos.json` se regeneró al aplicar, pero registraba 218 huellas de trabajo sin
       confirmar de otros frentes. Se restauró al estado previo (57ddc2db…) y no entra en este commit.
     - Se regenera con `others_scripts/verificar_componentes_compartidos.py --generar` antes del armado, cuando la DMC,
       la rama meteorológica, TROPOMI y los documentos hayan confirmado sus cambios. La compuerta de R22 lo exige
       registrado en cada paso del armado, que ya espera el paso 0.
     - La rama meteorológica vuelve a fijar en el addendum de M1 las huellas de `correr_v2.py` y `config_v2.json`
       posteriores a este commit, por MC-09 (R21 exige la red ampliada en π^mon y en M6). `huellas_m0.json` no se toca:
       registra el estado de M0. Es la decisión D51 **[delegada]**, en
       `APH/auditoria/20261023/meteo_combinada/m1/decisiones_autor_m1_20261026.md`.
     - La rama v3 actualiza sus huellas fijadas en su propia enmienda (la Enmienda 4 aguda, pendiente del autor).
2. **Armado**, sólo después del paso 0 (T13), en una ventana de máquina libre, en este orden (ninguno escribe antes de
   la confirmación en git; es el de `red_de_monitores.orden`, §8.8 y T12 a). Mientras dure, nadie confirma ni edita los archivos de la traducción ni
   `config/componentes_compartidos.json` (§11.1), y no hay commits nuevos de la traducción: cada artefacto registra la
   traducción con que se escribió y el anexo exige que sea la misma en todos (§9.0; `CAMINO_518`). El registro del
   catálogo MAIAC va primero, **antes del armado** (T5: «Antes del armado se les arma un registro con su sha256»; ronda
   5 de verificación, menor 17), ya ratificadas T11 a T13: pasa por la misma compuerta, que exige la ratificación:
   0. `panel_red2_v2.py --registrar-catalogo-maiac`, **antes del armado (T5)**: las 10 teselas con su sha256, en
      `insumos_red2/registro_catalogo_maiac.json`, una sola vez; el panel lo exige (paso 4);
   1. `derivado_red2_v2.py --ejecutar` (en `amb_v2`: lo exige). Publica en `derived/modelado/SINCA/v1_red2`
      (`destino_por_omision`), la única raíz que aceptan el reloj, el contraste y el panel, que exigen además el
      `plan.json` de la corrida con la huella rastreada del programa y, en cada versión, todas sus fuentes de la lista
      cerrada y ninguna ventana (§3.6). No se vuelve a correr después del reloj; si se corre
      sin cambios, el preparador reabre las mismas versiones en otra corrida y el armado la acepta como equivalente;
      con cambios, el reloj ya escrito no calza y hay que rehacer el reloj a mano (escritura única);
   2. `reloj_sinca_v2.py --derivado <v1_red2>` (sin `--anios` ni `--contaminantes`): veredictos y, en `resumen.json`,
      las series con su huella, los dos conteos y la convención de T4, una sola vez;
   3. `contraste_unidades_v2.py --derivado <v1_red2> --primera <primera corrida>` (segunda corrida, una sola vez, en
      `<raíz v2>/unidades_red2/`, con el derivado cerrado y antes del panel: T12 a);
   4. `panel_red2_v2.py --ejecutar --derivado <v1_red2> --contraste <segunda corrida> --contraste-sha256 <su huella>
      --veredictos <veredictos.parquet> --procesos 8`: exige la segunda corrida y su lateral, con la regla de unidades
      comprobada antes de escribir nada (ronda 5, menor 5), que el reloj haya corrido sobre sus mismas series, y el
      registro MAIAC del paso 0; toma la convención del resumen del reloj (con `--convencion-civil` sólo se puede
      confirmar) y lee cada serie desde los bytes cuyo sha256 registró al empezar (ronda 5, menor 3). Si se corta después de congelar los insumos, se vuelve a lanzar igual: lo que entra en
      el inventario tiene que ser lo mismo (escritura única; se compara sólo lo que entra, `huella_de_lo_que_entra`,
      así que un archivo que una descarga agregue después del corte y no entre no detiene el armado y queda fuera, como
      queda fuera de la copia) y la copia congelada se retoma comprobando cada sha256 (`congelar_o_retomar`); una copia
      sin su `congelados.json` se revisa a mano;
   5. `pliegues_red2_v2.py --motivo "Enmienda 2, R13"` (hace el renombre de R13).
3. **Anexo** con `pliegues_red2_v2.py --anexo`, pegado en `config_v2.json`, en git en AP y en el espejo y sellado antes
   de M3-4 (§9, «Queda abierto», 3). Ningún ajuste corre antes: `exigir_registro` exige `config_v2.json` rastreado y sin
   cambios en los dos (`red_ampliada_v2.exigir_config_confirmada`), también el piloto, que sale de `correr_v2.main`
   antes de `verificar_sellado`. El sello (OpenTimestamps) es un paso aparte que el código no comprueba. El commit del
   anexo regenera también `config/componentes_compartidos.json` (ronda 5 de verificación, menor 28): `config_v2.json`
   está en su grupo «modelo_1km», en modo «identico» y con su sha256, y es un archivo de la traducción
   (`ARCHIVOS_TRADUCCION`); sin regenerarlo, `others_scripts/verificar_componentes_compartidos.py` informa que el
   canónico cambió desde el manifiesto y la compuerta (`red_ampliada_v2.verificar_componentes`) detiene cualquier
   programa de la red 2 que se vuelva a lanzar después del anexo. La regeneración se coordina con los otros frentes,
   como en §11.1.
4. Nueva medición del piloto de tiempos, M6 y corrida larga, con lo sin rastrear de `scripts_modelo_1km/v2` ya resuelto
   (§11.1). La factibilidad no se vuelve a medir (R19: `factibilidad_v2` se detiene con el nodo).
