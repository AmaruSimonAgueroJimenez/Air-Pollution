"""Red de monitores ampliada de la v2: lista cerrada con huellas, maestros de coordenadas y red resultante.

Traduce los puntos R2, R3, R8 y R10 del bloque «Red ampliada e insumos de hoy» de la Enmienda 2 ambiental (anclado
en el repositorio de salud, commit f2c6cfc; texto con sha256 274ebae0…):

* **Lista cerrada (R2).** La red se cierra con los archivos de ``LISTA_CERRADA``, cada uno con su sha256 completo. Las
  rutas son relativas a la raíz de datos (``AIR_POLLUTION_DATA_ROOT``). ``verificar_lista_cerrada`` falla cerrado si
  alguno falta o cambió. El maestro del 2026-10-24 de la ampliación (``NO_SE_USAN``) no se lee.
* **Maestros de coordenadas (R8, decisión C3).** Las 109 configuradas salen de ``sinca/estaciones_georreferenciadas.csv``
  (51ff693e…), que no se toca; las 106 nuevas, del maestro corregido ``geometria_20261025`` (d5764ee2…). Un código
  no puede estar en los dos (``maestro_red2`` lo comprueba). Quedan fuera por coordenadas la 518 «Rural 1», la 408 y
  las fichas sin código (id 38 e id 44): no están en el maestro corregido.
* **Regla única de inclusión (R3).** Una estación entra al panel de un contaminante si está en la lista, tiene
  coordenadas usables y celda, y al menos una hora pasa R4 a R9. Sin mínimo de horas, días ni años. Aquí se arma la
  parte que no depende de las observaciones (``red_resultante``); el resto lo hace ``panel_red2_v2``.
* **Propietario (R10).** Se registran ``propietario``, ``operador``, ``red`` y ``calificacion`` de la ficha, con una
  clasificación descriptiva «pública» o «empresa» que no entra en la decisión (§9). La regla es la lectura T1(3) que
  aceptó el autor (``decisiones_autor_traduccion_20261025.md``): manda la calificación de la ficha y, si no la trae, el
  nombre del propietario. Cuatro fichas (517, 518, 525 y 533) no traen ni calificación ni propietario («NO INFORMADO»):
  T1(3) no alcanza a clasificarlas, así que quedan como «no informado», un tercer valor descriptivo que se informa
  aparte y nunca entra al §9. R10 sólo pide registrar los campos de la ficha, cosa que se hace para todas.
* **Orden (R22).** Nada de la red 2 se escribe antes de que la traducción esté confirmada en git:
  ``exigir_traduccion_confirmada`` lo comprueba (configuración con ``red_de_monitores``, contrato con su huella y los
  archivos de la traducción rastreados y sin cambios) en el par AP y espejo APH, se lance el programa desde donde se
  lance (``par_de_repositorios``); en el espejo exige además los textos de la auditoría que cita la configuración
  (``ARCHIVOS_DEL_ESPEJO``: el bloque, las decisiones del autor y las de la traducción) rastreados, sin cambios y con
  su sha256; y comprueba que ``config/componentes_compartidos.json`` registre la huella de cada archivo de la
  traducción (``verificar_componentes``). El anexo (R22, paso 4) tiene que estar además confirmado en git:
  ``exigir_config_confirmada`` exige ``config_v2.json`` rastreado y sin cambios en AP y en el espejo.
* **Ratificación antes del armado (T13 [delegada]).** El commit local de la traducción puede hacerse antes de que el
  autor ratifique T11, T12 y T13; el armado no. La compuerta, cuando la llama un programa del armado (todos los que la
  llaman lo son), exige además ``RATIFICACION_T11_T13`` llena y repetida en la configuración, con T11 a T13 y las
  lecturas §8.14, §8.15 y §8.17 de la propuesta, y los textos de T11 a T13 ya sin la marca de pendiente
  (``exigir_ratificacion``): se llena en el commit posterior a la ratificación, con la huella nueva del archivo de
  decisiones. Cada artefacto registra con qué ratificación se escribió (``traduccion_de``).
* **Procedencia de cada artefacto (§0 del contrato, «Procedencia»).** ``traza_red2`` es la ``_traza_v2.traza`` de la
  v2 (commit, huella del código, contrato, configuración, insumos, bibliotecas, Python e hilos) más la huella de cada
  módulo de la red 2 (``MODULOS_RED2``) y la traducción con que se escribió (``traduccion_de``: el último commit que
  tocó los archivos de la traducción en AP y en el espejo, los HEAD de los dos, el estado de la compuerta y la huella
  conjunta de esos archivos). Cada json que escribe la red 2 la lleva; el anexo exige que todos declaren la misma
  traducción (``pliegues_red2_v2.registro_de_la_red_desde_artefactos``).
* **Procedencia de la descarga (R2).** ``PROCEDENCIA_DESCARGA``: qué versión del descargador produjo cada archivo de
  la lista cerrada que la registra (la v1.0.0 no está en git; ver el docstring de la constante). Su estado (en git,
  recuperada o perdida) lo registra el anexo (``pliegues_red2_v2.procedencia_descarga_desde_artefactos``).

Sólo se leen cabeceras, columnas de identidad y conteos. No importa ``_comun_modelo``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import unidades_v2 as uv

BLOQUE = {"texto": "auditoria/20261024/sinca_al_modelo/ENMIENDA_2_BLOQUE_RED_AMPLIADA.md (repositorio de salud)",
          "sha256": "274ebae06bee8eeeb7470a650ce0539af751577d292513b8198cdec7c159094b", "commit": "f2c6cfc"}
DECISIONES_TRADUCCION = {"texto": "auditoria/20261024/sinca_al_modelo/decisiones_autor_traduccion_20261025.md "
                                  "(repositorio de salud)",
                         "sha256": "fdfbfa3149dae432a392c5dbea338b933fddf6f5f15a22cf2d18ad93d7da9a60",
                         "T1": ["(1) peso de un bloque = peso fijo × filas de sus estaciones (R16)",
                                "(2) duplicados: tolerancia relativa 1e-6; grupos de más de dos códigos como uno (R9)",
                                "(3) pública o de empresa: la calificación de la ficha y, si no la trae, el propietario (R10)",
                                "(4) órbitas antiguas de TROPOMI y GEOS-CF sin registro propio: por su fecha de "
                                "modificación (R11)"],
                         "T2": "aplicar después de una revisión independiente, en AP y en su espejo APH, ajustando las "
                               "pruebas que cambian, con commit local y sin envío al remoto",
                         "T3": "copia de MERRA-2 2026-10 con su huella en el disco interno",
                         # sección «2026-10-26» del mismo archivo
                         "T4": "una sola convención civil para todo SINCA, por las etiquetas de los días de cambio de "
                               "hora: gana la que da hora_civil en más unidades estación × contaminante × año local "
                               "(la unidad de T9) en que la otra no; empate, también en cero → inicio_mas_1h "
                               "(reloj_sinca_v2.elegir_convencion)",
                         "T5": "las teselas del catálogo MAIAC se registran antes del armado con su sha256; entran las "
                               "anteriores al corte (panel_red2_v2.registrar_catalogo_maiac)",
                         "T6": "la copia congelada de los insumos (≈ 232 GB) va al disco interno",
                         # T7 con su alcance literal (línea 22 del archivo de decisiones); lo que se agregó después
                         # al §8 de PROPUESTA.md lo cubre T12
                         "T7": "un revisor nuevo comprueba sólo las correcciones (y T4 y T5) contra el bloque anclado; "
                               "después se aplica en AP y en APH, se ajustan las pruebas y las huellas y se hace un "
                               "commit local sin envío; con esto se aceptan las diferencias con el cuadro del §3 del "
                               "bloque que listaba PROPUESTA §8.6 (programas propios para la red 2; catalogo_sinca y "
                               "metricas_v2 sin cambios) y la lectura de R21 como pliegues_v2_red2.json (PROPUESTA §9.4)",
                         # sección «tras la segunda revisión independiente»
                         "T8": "R5: rige el sha256 de afg_lib.py, el de la v1 (4391787a…); las huellas del árbol de "
                               "sintaxis quedan como procedencia, con la versión de Python (derivado_red2_v2.verificar_afg); "
                               "el derivado corre en amb_v2 (derivado_red2_v2.verificar_entorno al derivar y "
                               "contrato_de_la_version al leer)",
                         "T9": "votan las unidades del veredicto de R7, estación × contaminante × año local "
                               "(reloj_sinca_v2.elegir_convencion)",
                         "T10": "la conversión a hora civil está en reloj_sinca_v2.convertir y en el panel, no en "
                                "preparar_sinca_modelado.py; se acepta como diferencia con el cuadro del §3",
                         # sección «2026-10-26, por delegación del autor»: decidida con la opción recomendada, sin que
                         # el autor la viera; queda para que la ratifique
                         "T11": "[delegada] las 146 órbitas TROPOMI de 2024 sin registro (138 OFFL 02.08.00 del 2 al 31 "
                                "de diciembre y 8 RPRO 02.06.00 sueltas, formato antiguo .chile.nc) entran por su fecha "
                                "de modificación, como las de 2019-2022 (T1(4)); panel_red2_v2.TROPOMI_MTIME_ANIOS sin "
                                "límite (None); el anexo lista por año las órbitas que entran así (hoy 3.826); "
                                "pendiente de que el autor la ratifique",
                         "T12": "[delegada] diferencias con el cuadro del §3 y lecturas que T7 no cubría (verificaciones "
                                "de la madrugada del 2026-10-26); se aceptan cinco: (a) la segunda corrida del contraste "
                                "se hace con el derivado cerrado y antes de armar el panel, para que rija sobre él (la "
                                "lectura de «al cerrar el panel» y de R22.3); (b) el derivado de la red 2 vuelve a "
                                "derivar completas las 107 estaciones actuales desde DATOS/sinca (sellado más "
                                "actualización) en una sola raíz v1_red2, que leen el reloj, el contraste y el panel "
                                "(R4); (c) inferencia_diferencias.influencia.bloque_mas_influyente y …criterio no se "
                                "vuelven regla y quedan con nodos hermanos; (d) las raíces del derivado de la red 2 "
                                "viven en derivado_red2_v2 (raiz_derivados, destino_por_omision) y no en _rutas_v2; (e) "
                                "las lecturas §8.8 a §8.13 de PROPUESTA.md (la §8.12 queda corregida), entre ellas las "
                                "SNIFA como «no informado» (R10); y se corrige la sexta: la masa molar del O3 es la "
                                "literal de R6, 47,998 g/mol (unidades_v2.MASA_MOLAR y contraste_unidades_v2.M), y el panel "
                                "importa produccion.py con su huella fijada (HUELLAS_CODIGO_V1, la de cada repositorio) y "
                                "marca las rachas con produccion.marcar_rachas, la regla de produccion.observaciones; la "
                                "función misma lee las series de la v1 y no admite las de la red 2, así que el resto se "
                                "replica, con una prueba de equivalencia; pendiente de que el autor la ratifique",
                         "T13": "[delegada] el commit local de la traducción (T2) puede hacerse antes de la ratificación; "
                                "el armado no: el paso 2 de §11 (armado) no empieza hasta que el autor ratifique T11, "
                                "T12 y T13 (paso 0 de §11); si cambia alguna, se hace otro commit antes del armado; el "
                                "commit local se puede reemplazar, la copia congelada y los json del panel, de "
                                "escritura única, no; pendiente de que el autor la ratifique"}
# T13 [delegada] (PROPUESTA §9, «Queda abierto», 0, y §11, paso 0): el armado no empieza hasta que el autor ratifique
# T11, T12 y T13, con las lecturas de la traducción que ninguna decisión cubría: §8.14 (T11 por referencia), §8.15 (el
# límite de R7) y §8.17 (R15 en la decisión: rige la evaluabilidad de E2 registrada antes del ajuste, y la parada por
# defecto de la corrida) de PROPUESTA.md. Mientras sea None, la compuerta de R22 detiene todo programa del armado
# (``exigir_ratificacion``). Se llena en el commit posterior a la ratificación (§9.0), con la huella nueva del archivo de
# decisiones (anotar la ratificación la cambia) en DECISIONES_TRADUCCION, y se repite en
# red_de_monitores.ratificacion_t11_t13.valor:
#   {"fecha": "AAAA-MM-DD", "decisiones_sha256": <la huella nueva>, "T11": "ratificada" | "cambiada", "T12": …,
#    "T13": …, "§8.14": …, "§8.15": …, "§8.17": …}
# En ese mismo commit, los textos de T11, T12 y T13 (aquí y en contrato.enmiendas[2].decisiones_de_traduccion de la
# configuración) dejan de decir que están pendientes y dicen «<estado> por el autor el <fecha>» (MARCA_DE_RATIFICACION);
# la compuerta lo exige, para que los json de escritura única del armado, que copian esos textos, no los registren como
# pendientes.
RATIFICACION_T11_T13 = None
RATIFICABLES = ("T11", "T12", "T13", "§8.14", "§8.15", "§8.17")
ESTADOS_DE_RATIFICACION = ("ratificada", "cambiada")
DECISIONES_DELEGADAS = ("T11", "T12", "T13")
MARCAS_DE_PENDIENTE = ("pendiente de que el autor la ratifique", "pendiente de que la ratifique")
MARCA_DE_RATIFICACION = "{estado} por el autor el {fecha}"
# La huella del archivo de decisiones antes de la ratificación: la de después tiene que ser otra.
DECISIONES_SIN_RATIFICAR = "fdfbfa3149dae432a392c5dbea338b933fddf6f5f15a22cf2d18ad93d7da9a60"
# R8, decisión «518»: entra con las mismas reglas si aparece una coordenada oficial antes del anexo de R22; después, no.
CLAUSULA_518 = ("la 518 «Rural 1» entra con las reglas de R8 si aparece una coordenada oficial antes del anexo «Registro "
                "de la red v2» (R22, paso 4); después del anexo, no")
# Si la coordenada aparece después de empezar el armado y antes del anexo, el reloj, la segunda corrida y el panel ya se
# escribieron una sola vez sobre el maestro corregido d5764ee2…: para que la 518 entre hay que rehacerlos (ver
# red_de_monitores.fuera_por_coordenadas.clausula_518 de la configuración).
# Los archivos de la red 2 en <raíz v2>/paneles/ (los que publica panel_red2_v2.ejecutar). La carpeta guarda además la
# bandera de la red original (calidad_pm25 y calidad_no2, que lee test_calidad_artefacto_v2): nunca se mueve entera.
ARCHIVOS_RED2_EN_PANELES = (
    "panel_pm25_red2.parquet", "panel_pm25_red2.json", "panel_no2_red2.parquet", "panel_no2_red2.json",
    "calidad_pm25_red2.parquet", "calidad_no2_red2.parquet", "reloj_civil_pm25_red2.parquet",
    "reloj_civil_no2_red2.parquet", "observaciones_pm25_red2.parquet", "observaciones_no2_red2.parquet",
    "observaciones_o3_red2.parquet", "observaciones_o3_red2.json", "estaciones_red2.parquet",
    "satelites_estaciones_red2.parquet", "regimenes_red2.json")
CAMINO_518 = ("maestro corregido nuevo con la coordenada oficial y su huella en LISTA_CERRADA; commit nuevo de la "
              "traducción en AP y en el espejo (R22, paso 2); lo que el armado escribe una sola vez se mueve a mano a un "
              "respaldo «<nombre>_reemplazado_<marca>» con un registro del motivo «R8, 518»: las carpetas "
              "verificacion_reloj_sinca_red2, unidades_red2 e insumos_red2 (con registro_catalogo_maiac.json, "
              "inventario.json, congelados.json y la copia congelada), el archivo grilla/estaciones_enlaces_red2.parquet "
              "y, de paneles/, sólo los archivos de la red 2, nombrados uno por uno ("
              + ", ".join(ARCHIVOS_RED2_EN_PANELES) + "), nunca la carpeta entera, que guarda la bandera de la red "
              "original (calidad_pm25 y calidad_no2); y se rehacen, en este orden, el registro del catálogo MAIAC "
              "(T5, --registrar-catalogo-maiac, antes del armado), el derivado, el reloj, la segunda corrida del "
              "contraste, el panel y los pliegues (pliegues_v2_red2.json, que queda en la raíz v2, con --reemplazar "
              "--motivo «R8, 518»)")

AMP = "sinca_ampliacion_20261024"
GEO = f"{AMP}/geometria_20261025"
ACT = f"{AMP}/actualizacion_configuradas"

# R2: procedencia de la descarga de las estaciones nuevas y de la actualización (sólo las columnas y campos script_* de
# los archivos de la lista cerrada). La v1.0.0 del descargador no está en git ni junto al código: si se recupera del
# historial de versiones del Drive se confirma con su huella; si no, queda perdida. El estado de cada versión no es una
# constante: lo arma el anexo (``pliegues_red2_v2.procedencia_descarga_desde_artefactos``) en
# ``registro_de_la_red.procedencia_descarga``, mirando el código del commit y las copias recuperadas que estén en
# ``<raíz v2>/procedencia_descarga/`` (quinta revisión, menor 22). «estado» dice aquí sólo de dónde sale.
PROCEDENCIA_DESCARGA = {
    "programa": "scripts_pipeline/descargar_sinca_ampliacion.py",
    "versiones": [
        {"script_version": "1.0.0",
         "script_sha256": "647f55183155d66ccbe4712879b00fd6a2c1842cbb0f8c19c4fe1e058199442d",
         "produjo": {f"{AMP}/manifiesto_descarga.csv": 167, f"{AMP}/manifiesto_descarga_otras_series.csv": 1076},
         "estado": "no está en git ni junto al código; si se recupera del historial del Drive, la copia va a "
                   "<raíz v2>/procedencia_descarga/ y se confirma con esta huella; el anexo registra «recuperada» o "
                   "«perdida» en registro_de_la_red.procedencia_descarga"},
        {"script_version": "1.0.0",
         "script_sha256": "93f20aeb20179cefce3f4bbbe76631f1784f05f760053ace2140bd090475fd22",
         "produjo": {f"{AMP}/catalogo/20261024T232023Z/catalogo.json": 1},
         "estado": "otra huella con la misma versión 1.0.0 (el catálogo); no está en git ni junto al código; como la "
                   "anterior"},
        {"script_version": "1.1.0",
         "script_sha256": "d77247232ed4857941d8a4616193d805ed612af20a816949b44b6b1c9cb63c62",
         "produjo": {f"{ACT}/manifiesto_descarga.csv": 330},
         "estado": "la versión de hoy: entra en el commit de la traducción (ARCHIVOS_TRADUCCION); el anexo registra "
                   "«en_git» si el programa del commit tiene esta huella"}],
    "lectura": "filas de cada manifiesto con esa script_version y ese script_sha256 (catalogo.json: sus campos "
               "script_version y script_sha256); sólo columnas de procedencia, ningún valor"}
CARPETA_PROCEDENCIA_DESCARGA = "procedencia_descarga"     # en la raíz v2: copias recuperadas del historial del Drive

# R2 y §5 del bloque: archivo (relativo a la raíz de datos) → sha256.
LISTA_CERRADA = {
    "sinca/manifiesto_descarga.csv": "79d4fd770e5ad0aa7e5c88487598c20106989fb6be184b457f8502ecee289f7f",
    "sinca/estaciones_georreferenciadas.csv": "51ff693e6ac9a75eb92afc4da4995950f2b39fa4e241fd0e1f57a183cc381995",
    "sinca/estaciones_georreferenciadas.geojson": "85a8eb08bfb9315fb5c3324a9912641878943366e93137a7e0c0e316121ae12d",
    f"{ACT}/manifiesto_descarga.csv": "0fc77ae1b89cb9db5308ac38703dc7f2b8606902327705257e1b1b15551a8388",
    f"{ACT}/SHA256SUMS.txt": "785283793ee2aa79cb7e2ff3355af6121c542d5e12c2275e203320a07d621fbc",
    f"{ACT}/estaciones_georreferenciadas.csv": "51ff693e6ac9a75eb92afc4da4995950f2b39fa4e241fd0e1f57a183cc381995",
    f"{ACT}/estado_validacion_series.csv": "b398f69d2a701b7212a763d41f1ae422052e3e5ae64b168c5274a3d54fb902fb",
    f"{AMP}/manifiesto_descarga.csv": "19865e3b03f0abc2bd6d3673a5ddd63978c465625c1aec1355bc473824f85480",
    f"{AMP}/SHA256SUMS.txt": "db36e2084f75d262cea445665d7a403c53a0058cd18c87b7f5f1f48bffd3d7fa",
    f"{AMP}/estaciones_fichas.csv": "5d22889a185a41af067b36a1b066e1b988eb06d14b23e89b67566dda132a5f5b",
    f"{AMP}/catalogo/20261024T232023Z/catalogo.json": "1c523f6f66f70fb7c5e40bc13686309ec58137d5c34f722f3addb87ae44eaede",
    f"{AMP}/catalogo/20261024T232023Z/SHA256SUMS.txt": "14c9b5cba28d25daa62a9ec226350b5216dbc98efbe0479384d4ea002227e106",
    f"{AMP}/estado_validacion_series.csv": "b6ee431fe8be8960bce8620fd8e9017387b1dce4c121bcd2be9c739578eb0f03",
    f"{AMP}/manifiesto_descarga_otras_series.csv": "dee257046f0871e2f7d249c30f592a268bc6d49de3c8823f7ffaca1131edb9cc",
    f"{GEO}/estaciones_georreferenciadas.csv": "d5764ee2f8f6afa3a92cca609744080749254fbfb041d58783b99f31b4169308",
    f"{GEO}/estaciones_georreferenciadas.geojson": "eaeaf965ffa2f5a8d0a734128473ecc5646916ef2dd958c7c5b37b94364df29b",
    f"{GEO}/SHA256SUMS.txt": "945640f3cb5f0e9f244b6dda2ae7c4845f991225f7fb87a3b291bb1967bd6827",
    f"{GEO}/metadata/correcciones_coordenadas.json": "d0a42ac02aaff81db6af17d263f2d195aa75289536834689beda0c3c30075e97",
    f"{GEO}/metadata/envoltorio_geometria.json": "bd47ebcac10b6ac15e3c3153936f3b2a50fb63d382bef1f31deca4772b78cb0e",
    "snifa_adicional/processed/observaciones_horarias.parquet":
        "2aa177d9f0e3f8626d03c9e8381357a58eb81e43192b7aa802c5f03b4e055a55",
}
NO_SE_USAN = {f"{AMP}/estaciones_georreferenciadas.csv": "c5eb0806cf9346c2313e06a1ff98eb337dab8abaeaf707044d86083a452e4e6f"}
MAESTRO_ACTUALES = "sinca/estaciones_georreferenciadas.csv"
MAESTRO_NUEVAS = f"{GEO}/estaciones_georreferenciadas.csv"
GEOJSON_ACTUALES = "sinca/estaciones_georreferenciadas.geojson"
GEOJSON_NUEVAS = f"{GEO}/estaciones_georreferenciadas.geojson"
MANIFIESTO_SELLADO = "sinca/manifiesto_descarga.csv"
MANIFIESTO_ACTUALIZACION = f"{ACT}/manifiesto_descarga.csv"
MANIFIESTO_NUEVAS = f"{AMP}/manifiesto_descarga.csv"
FICHAS = f"{AMP}/estaciones_fichas.csv"
SNIFA = "snifa_adicional/processed/observaciones_horarias.parquet"

# Lo que el bloque enumera (R2, R6 y R8); las pruebas lo contrastan con los manifiestos (sólo conteos).
NUEVAS = {
    "pm25": {"µg/m³": ("332", "D31")},
    "no2": {"ppb": ("252", "501", "506", "507", "511", "602", "846", "850"),
            "µg/m³N": ("207", "209", "215", "216", "221", "329", "517", "518", "533", "534", "614", "876", "E01"),
            "sin": ("601", "603", "816", "A02", "A03")},
    "o3": {"ppb": ("501", "506", "507", "511", "601", "602", "603", "816", "846", "850"),
           "µg/m³N": ("207", "215", "216", "221", "329", "518", "519", "533", "534", "614", "876", "E01"),
           "sin": ("517", "A02", "A03")},
}
FUERA_POR_COORDENADAS = ("408", "518")
FICHAS_SIN_CODIGO = ("38", "44")
SIN_DATOS_NUEVOS = ("222", "236", "549", "833", "904", "A04", "D11", "D16", "D29", "E06")
ACTUALES_FUERA_SIN_UNIDAD = {"no2": ("513", "529", "532", "609", "878", "901"), "o3": ("827", "837", "901")}
RED_ESPERADA = {"pm25": {"actuales": 107, "nuevas": 2, "snifa": 0, "total": 109},
                "no2": {"actuales": 48, "nuevas": 20, "snifa": 3, "total": 71},
                "o3": {"actuales": 47, "nuevas": 22, "snifa": 0, "total": 69}}
CONTAMINANTES = uv.CONTAMINANTES_RED2

# R10: dueños públicos (descriptivo; no entra en el §9). La calificación de la ficha manda cuando existe.
PATRONES_PUBLICOS = ("ministerio", "secretar", "seremi", "municipalidad", "instituto de investigaciones agropecuarias",
                     "conama", "gobierno regional", "servicio de salud")


def sha256_archivo(ruta) -> str:
    return uv.sha256_archivo(ruta)


def verificar_lista_cerrada(datos, lista: dict[str, str] | None = None) -> dict[str, str]:
    """Comprueba el sha256 de cada archivo de la lista cerrada; falla cerrado. Devuelve {ruta: sha256}."""
    datos = Path(datos)
    lista = LISTA_CERRADA if lista is None else lista
    faltan, distintos = [], []
    for rel, sha in lista.items():
        p = datos / rel
        if not p.is_file():
            faltan.append(rel)
            continue
        if sha256_archivo(p) != sha:
            distintos.append(rel)
    if faltan or distintos:
        raise SystemExit(f"La lista cerrada de la red 2 no se cumple: faltan {faltan}; cambiaron {distintos}")
    return dict(lista)


def _leer_maestro(ruta: Path, grupo: str) -> pd.DataFrame:
    """Réplica de ``_comun_modelo.leer_estaciones`` (``:593-599``) sobre un maestro, con su grupo."""
    est = pd.read_csv(ruta, dtype={"estacion": str})
    usable = est["usable_geoespacial"].astype(str).str.lower().isin(["true", "1"])
    est = est[usable].copy()
    est["cod_comuna"] = pd.to_numeric(est["cod_comuna_geografica"], errors="coerce").astype("Int64")
    est = est[["estacion", "nombre", "region_sinca", "lat", "lon", "cod_comuna", "qc_comuna"]].reset_index(drop=True)
    est["grupo"] = grupo
    est["red"] = "sinca"
    return est


def combinar_maestros(actuales: pd.DataFrame, nuevas: pd.DataFrame) -> pd.DataFrame:
    """Maestro de la red 2: los dos maestros de R8, con códigos únicos (choque = error)."""
    choque = sorted(set(actuales["estacion"]) & set(nuevas["estacion"]))
    if choque:
        raise ValueError(f"códigos en los dos maestros de R8: {choque}")
    m = pd.concat([actuales, nuevas], ignore_index=True)
    if m["estacion"].duplicated().any():
        raise ValueError(f"códigos repetidos en un maestro: {m.loc[m['estacion'].duplicated(), 'estacion'].tolist()}")
    return m.sort_values("estacion", kind="stable").reset_index(drop=True)


def maestro_red2(datos) -> pd.DataFrame:
    """Las estaciones SINCA con coordenadas usables de los dos maestros de R8."""
    datos = Path(datos)
    return combinar_maestros(_leer_maestro(datos / MAESTRO_ACTUALES, "actual"),
                             _leer_maestro(datos / MAESTRO_NUEVAS, "nueva"))


def tipo_propietario(propietario, calificacion) -> str:
    """«pública» o «empresa» (R10, descriptivo; lectura T1(3)): la calificación de la ficha si es «Pública» o
    «Privada»; si no, el propietario (patrones de ``PATRONES_PUBLICOS``). «no informado» cuando la ficha no trae ni
    calificación ni propietario: T1(3) no la alcanza y se informa aparte (ver el docstring del módulo)."""
    cal = str(calificacion or "").strip().lower()
    if cal == "pública":
        return "pública"
    if cal == "privada":
        return "empresa"
    p = str(propietario or "").strip().lower()
    if not p or p in ("nan", "no informado"):
        return "no informado"
    return "pública" if any(x in p for x in PATRONES_PUBLICOS) else "empresa"


def fichas_red2(datos) -> pd.DataFrame:
    """Atributos descriptivos de R10 por estación (sólo columnas de texto de la ficha)."""
    f = pd.read_csv(Path(datos) / FICHAS, dtype=str,
                    usecols=["id_sinca", "estacion", "propietario", "operador", "red", "calificacion", "configurada"])
    f = f.dropna(subset=["estacion"]).drop_duplicates("estacion")
    f["tipo_propietario"] = [tipo_propietario(p, c) for p, c in zip(f["propietario"], f["calificacion"])]
    return f.reset_index(drop=True)


def series_contrato(datos, contaminantes=CONTAMINANTES, texto: bool = False) -> pd.DataFrame:
    """Series horarias de la red 2 (sellado + actualización + nuevas) de ``contaminantes``: una fila por archivo, con
    su origen y su grupo. Sólo columnas de identidad y conteos de los manifiestos. Con ``texto``, cada celda queda
    como está en el archivo (los vacíos, como cadena vacía, sin convertirlos), que es como las lee el preparador
    (``csv.DictReader``) y como las declara cada versión del derivado en ``inputs.sources``."""
    datos = Path(datos)
    cols = ["region", "estacion", "contaminante", "resolucion", "desde", "hasta", "ruta", "bytes", "sha256", "filas",
            "filas_con_observacion", "primera_observacion", "ultima_observacion"]
    partes = []
    for rel, origen, grupo in ((MANIFIESTO_SELLADO, "sellado", "actual"), (MANIFIESTO_ACTUALIZACION, "actualizacion",
                                                                             "actual"),
                               (MANIFIESTO_NUEVAS, "ampliacion", "nueva")):
        m = pd.read_csv(datos / rel, dtype=str, usecols=cols, keep_default_na=not texto)
        m["origen"], m["grupo"] = origen, grupo
        partes.append(m)
    s = pd.concat(partes, ignore_index=True)
    if (s["resolucion"] != "horario").any():
        raise ValueError("la red 2 usa sólo series horarias")
    s = s[s["contaminante"].isin(contaminantes)].reset_index(drop=True)
    actuales = set(s.loc[s["origen"] == "sellado", "estacion"])
    otra = s[(s["origen"] == "actualizacion") & ~s["estacion"].isin(actuales)]
    if len(otra):
        raise ValueError(f"la actualización trae estaciones que no están en el maestro sellado: {sorted(set(otra.estacion))}")
    choque = set(s.loc[s["grupo"] == "nueva", "estacion"]) & actuales
    if choque:
        raise ValueError(f"estaciones nuevas con el código de una actual: {sorted(choque)}")
    return s


def red_resultante(series: pd.DataFrame, unidades: pd.DataFrame, maestro: pd.DataFrame,
                   snifa_no2: int = 3) -> dict:
    """Red por contaminante antes de mirar las observaciones: series con unidad que entra (R6) y estación con
    coordenadas usables (R8). La regla de «al menos una hora» (R3) la aplica el panel."""
    con_coord = set(maestro["estacion"])
    grupo_de = dict(zip(maestro["estacion"], maestro["grupo"]))
    entra = {(e, p) for e, p, ok in zip(unidades["estacion"], unidades["contaminante"], unidades["entra"]) if ok}
    out = {}
    for pol in sorted(set(series["contaminante"])):
        est = sorted(set(series.loc[series["contaminante"] == pol, "estacion"]))
        dentro = [e for e in est if (e, pol) in entra and e in con_coord]
        fuera_unidad = [e for e in est if (e, pol) not in entra]
        fuera_coord = [e for e in est if (e, pol) in entra and e not in con_coord]
        n_snifa = snifa_no2 if pol == "no2" else 0
        out[pol] = {"actuales": sum(1 for e in dentro if grupo_de.get(e) == "actual"),
                    "nuevas": sum(1 for e in dentro if grupo_de.get(e) == "nueva"),
                    "snifa": n_snifa, "total": len(dentro) + n_snifa,
                    "estaciones": dentro, "fuera_por_unidad": fuera_unidad, "fuera_por_coordenadas": fuera_coord}
    return out


def series_esperadas_red2(datos, maestro: pd.DataFrame | None = None, contaminantes=CONTAMINANTES) -> set:
    """R2 y R8: las series (estación, contaminante) que tiene que traer el derivado de la red 2: las de los tres
    manifiestos de ``series_contrato`` en ``contaminantes``, de las estaciones con coordenada usable en los maestros de
    R8 (sin la 518 ni la 408). Es lo mismo que el plan de ``derivado_red2_v2.insumos_red2`` (los grupos sin las
    excluidas), pero sin cargar el preparador. Sólo columnas de identidad."""
    maestro = maestro_red2(datos) if maestro is None else maestro
    con_coord = set(maestro["estacion"].astype(str))
    s = series_contrato(datos, contaminantes)
    return {(str(e), str(p)) for e, p in zip(s["estacion"], s["contaminante"]) if str(e) in con_coord}


def diferencia_con_la_red_2(vistas, esperadas) -> dict:
    """{"faltan": [...], "sobran": [...]} entre las series leídas y las esperadas (``series_esperadas_red2``)."""
    vistas, esperadas = set(vistas), set(esperadas)
    return {"faltan": [f"{e}:{p}" for e, p in sorted(esperadas - vistas)],
            "sobran": [f"{e}:{p}" for e, p in sorted(vistas - esperadas)]}


def exigir_la_red_2(vistas, esperadas, quien: str) -> dict:
    """Se detiene si el conjunto estación × contaminante leído no es el de la red 2 (R2: «la red queda fijada por
    archivos con huella, no por lo que haya en disco el día que se corra»), mostrando la diferencia."""
    d = diferencia_con_la_red_2(vistas, esperadas)
    if d["faltan"] or d["sobran"]:
        raise SystemExit(f"{quien}: el derivado no trae las series de la red 2 (R2): faltan {len(d['faltan'])} "
                         f"{d['faltan'][:10]}; sobran {len(d['sobran'])} {d['sobran'][:10]}")
    return {"series": len(set(vistas)), "regla": "series_contrato ∩ maestros de R8, en PM2,5, NO2 y O3 (R2, R8)"}


# ---------------------------------------------------------------------------
# R22: nada de la red 2 se escribe antes de confirmar la traducción en git
# ---------------------------------------------------------------------------
CARPETA_PROPUESTA = "scripts_modelo_1km/v2/propuesta_red_ampliada"
ARCHIVOS_PROPUESTA = tuple(f"{CARPETA_PROPUESTA}/{n}" for n in (
    "PROPUESTA.md", "CAMBIOS_AL_CODIGO_SELLADO.md", "config_v2.propuesto.json", "DISENO_AMBIENTAL_V2.propuesto.md"))
ARCHIVOS_TRADUCCION = ("scripts_modelo_1km/v2/DISENO_AMBIENTAL_V2.md", "scripts_modelo_1km/v2/config_v2.json",
                       "scripts_modelo_1km/v2/_rutas_v2.py", "scripts_modelo_1km/v2/reloj_sinca_v2.py",
                       "scripts_modelo_1km/v2/unidades_v2.py", "scripts_modelo_1km/v2/contraste_unidades_v2.py",
                       "scripts_modelo_1km/v2/duplicados_v2.py", "scripts_modelo_1km/v2/red_ampliada_v2.py",
                       "scripts_modelo_1km/v2/derivado_red2_v2.py", "scripts_modelo_1km/v2/panel_red2_v2.py",
                       "scripts_modelo_1km/v2/pliegues_red2_v2.py",
                       # el código sellado que cambia al aplicar la propuesta (CAMBIOS_AL_CODIGO_SELLADO.md)
                       "scripts_modelo_1km/v2/calidad_v2.py", "scripts_modelo_1km/v2/pliegues_v2.py",
                       "scripts_modelo_1km/v2/vecindario_v2.py", "scripts_modelo_1km/v2/validar_vecindario_v2.py",
                       "scripts_modelo_1km/v2/correr_v2.py", "scripts_modelo_1km/v2/piloto_v2.py",
                       "scripts_modelo_1km/v2/factibilidad_v2.py",
                       # las pruebas selladas que cambia la propuesta (CAMBIOS_AL_CODIGO_SELLADO.md)
                       "scripts_modelo_1km/v2/tests/_sintetico_v2.py",
                       *(f"scripts_modelo_1km/v2/tests/test_{m}_v2.py" for m in (
                           "rutas", "manifiesto", "factibilidad", "calidad_artefacto", "calidad", "pliegues", "correr",
                           "piloto", "vecindario", "config", "metricas", "decision")),
                       # las pruebas nuevas
                       *(f"scripts_modelo_1km/v2/tests/test_{m}_v2.py" for m in (
                           "reloj_sinca", "unidades", "contraste_unidades", "duplicados", "red_ampliada",
                           "derivado_red2", "panel_red2", "pliegues_red2")),
                       # la propuesta misma (cuarta revisión, mayor 3): test_red_ampliada_v2 lee CAMBIOS, y sin rastrear
                       # dentro de scripts_modelo_1km/v2 detendría correr_v2.verificar_sellado
                       *ARCHIVOS_PROPUESTA,
                       # R8 y R22: el envoltorio de geometría y su descargador, con sus pruebas (sin rastrear hasta hoy);
                       # el descargador importa descargar_sinca_meteorologia (y registra su huella), que va con su prueba
                       "scripts_pipeline/geometria_sinca_ampliacion.py", "scripts_pipeline/descargar_sinca_ampliacion.py",
                       "scripts_pipeline/tests/test_geometria_sinca_ampliacion.py",
                       "scripts_pipeline/tests/test_descargar_sinca_ampliacion.py",
                       "scripts_pipeline/descargar_sinca_meteorologia.py",
                       "scripts_pipeline/tests/test_descargar_sinca_meteorologia.py",
                       # §3 del bloque, última fila: cambia scripts_pipeline/, así que se regenera en el mismo commit
                       "config/componentes_compartidos.json")
MANIFIESTO_COMPONENTES = "config/componentes_compartidos.json"
NOMBRE_CANONICO = "Air-Pollution"                  # el repositorio público (config/componentes_compartidos.json)
NOMBRE_ESPEJO = "Air-Pollution-Health-Chile"      # el espejo, junto al repositorio
# Los textos de la auditoría que cita la configuración (contrato.enmiendas[2]) y que sólo están en el espejo (AP no
# lleva /auditoria/): rastreados, sin cambios y con su sha256 en el git del espejo (cuarta revisión, menores 15, 31 y 36).
ARCHIVOS_DEL_ESPEJO = {
    "auditoria/20261024/sinca_al_modelo/ENMIENDA_2_BLOQUE_RED_AMPLIADA.md": BLOQUE["sha256"],
    "auditoria/20261024/sinca_al_modelo/decisiones_autor_20261024.md":
        "01744a98101ff149fc3e65a32046c27b2fd810bd2b23d8c72594e00b4355b7af",
    "auditoria/20261024/sinca_al_modelo/decisiones_autor_traduccion_20261025.md": DECISIONES_TRADUCCION["sha256"],
}


def estado_git(repo: Path, rutas) -> dict:
    """Estado de git de ``rutas`` en ``repo``, sólo leyendo: {ruta: «rastreado», «sin_rastrear», «modificado» o
    «desconocido»}."""
    import subprocess

    def git(*args):
        return subprocess.run(["git", "--no-optional-locks", "-C", str(repo), *args], capture_output=True, text=True,
                              timeout=60)
    out = {}
    for rel in rutas:
        try:
            rastreado = git("ls-files", "--error-unmatch", "--", rel).returncode == 0
            cambios = git("status", "--porcelain", "--", rel)
        except (OSError, subprocess.SubprocessError):
            out[rel] = "desconocido"
            continue
        if cambios.returncode != 0:
            out[rel] = "desconocido"
        elif not rastreado:
            out[rel] = "sin_rastrear"
        else:
            out[rel] = "modificado" if cambios.stdout.strip() else "rastreado"
    return out


def par_de_repositorios(repo: Path) -> tuple[Path, Path]:
    """(AP, espejo APH) sin importar desde cuál se lanza el programa (cuarta revisión, mayor 2): si ``repo`` es el
    espejo, el canónico es su hermano ``Air-Pollution``; si no, el espejo es su hermano ``Air-Pollution-Health-Chile``.
    Un espejo que resulte ser el mismo repositorio se rechaza."""
    repo = Path(repo).resolve()
    if repo.name == NOMBRE_ESPEJO:
        canonico, espejo = repo.parent / NOMBRE_CANONICO, repo
    else:
        canonico, espejo = repo, repo.parent / NOMBRE_ESPEJO
    if canonico.resolve() == espejo.resolve():
        raise SystemExit(f"el espejo {espejo.name} no puede ser el mismo repositorio que {canonico.name} (R22, paso 2)")
    return canonico, espejo


def verificar_espejo(repo: Path, espejo: Path, rutas, estado=None, del_espejo: dict | None = None) -> dict:
    """R22, paso 2 («confirmada en git en AP y en su espejo APH»): cada archivo de la traducción está en el espejo con
    los mismos bytes que en AP y confirmado en el git del espejo; y los textos de la auditoría que cita la
    configuración (``del_espejo``, por omisión ``ARCHIVOS_DEL_ESPEJO``) están rastreados y sin cambios en el git del
    espejo, con su sha256. ``estado``, para las pruebas."""
    espejo = Path(espejo)
    del_espejo = ARCHIVOS_DEL_ESPEJO if del_espejo is None else del_espejo
    if not espejo.is_dir():
        raise SystemExit(f"no está el espejo {espejo.name}: la traducción tiene que estar confirmada también ahí")
    if espejo.resolve() == Path(repo).resolve():
        raise SystemExit(f"el espejo {espejo.name} no puede ser el mismo repositorio que {Path(repo).name} (R22, paso 2)")
    distintos = [rel for rel in rutas if not (Path(espejo) / rel).is_file()
                 or (Path(espejo) / rel).read_bytes() != (Path(repo) / rel).read_bytes()]
    if distintos:
        raise SystemExit(f"el espejo {espejo.name} no tiene los mismos archivos de la traducción: {distintos[:5]}")
    otra_huella = [rel for rel, sha in del_espejo.items()
                   if not (espejo / rel).is_file() or sha256_archivo(espejo / rel) != sha]
    if otra_huella:
        raise SystemExit(f"el espejo {espejo.name} no tiene los textos de la auditoría que cita la configuración con su "
                         f"sha256: {otra_huella}")
    est = (estado or estado_git)(espejo, [*rutas, *del_espejo])
    pendientes = {k: v for k, v in est.items() if v != "rastreado"}
    if pendientes:
        raise SystemExit(f"la traducción no está confirmada en git en el espejo {espejo.name}: {pendientes}")
    return est


def verificar_componentes(repo: Path, rutas, manifiesto: str = MANIFIESTO_COMPONENTES) -> dict:
    """R22 y §3 del bloque, última fila (cuarta revisión, menor 26): ``config/componentes_compartidos.json`` tiene que
    estar regenerado con la traducción: cada archivo de ``rutas`` (salvo el manifiesto mismo, que no declara su propia
    huella) aparece en un grupo «identico» con su sha256 de hoy. Devuelve {ruta: sha256}."""
    ruta = Path(repo) / manifiesto
    try:
        man = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SystemExit(f"{manifiesto}: no se puede leer ({type(e).__name__}); regenéralo con la traducción")
    declarado: dict[str, str] = {}
    for g in man.get("grupos") or []:
        if g.get("modo") == "identico":
            declarado.update(g.get("sha256") or {})
    malos = {}
    for rel in rutas:
        if rel == manifiesto:
            continue
        real = sha256_archivo(Path(repo) / rel) if (Path(repo) / rel).is_file() else None
        if declarado.get(rel) != real:
            malos[rel] = "no registrado" if rel not in declarado else "otra huella"
    if malos:
        raise SystemExit(f"{manifiesto} no registra la traducción tal como está ({len(malos)} archivos: "
                         f"{dict(list(malos.items())[:5])}); regenéralo en el mismo commit (R22, paso 2)")
    return {rel: declarado[rel] for rel in rutas if rel != manifiesto}


def exigir_ratificacion(cfg: dict) -> dict:
    """T13 [delegada]: «el paso 2 de §11 (armado) no empieza hasta que el autor ratifique T11, T12 y T13». Exige
    ``RATIFICACION_T11_T13`` llena: cada una de ``RATIFICABLES`` (T11, T12, T13 y las lecturas §8.14, §8.15 y §8.17)
    «ratificada» o «cambiada»; ``decisiones_sha256`` igual a la huella del archivo de decisiones que cita el código
    (``DECISIONES_TRADUCCION``, que la compuerta compara con el archivo del espejo) y distinta de la de antes de la
    ratificación (``DECISIONES_SIN_RATIFICAR``: la ratificación queda anotada en ese archivo); la configuración
    repitiéndola en ``red_de_monitores.ratificacion_t11_t13.valor``; y los textos de T11, T12 y T13, en
    ``DECISIONES_TRADUCCION`` y en ``contrato.enmiendas[2].decisiones_de_traduccion``, sin ninguna marca de pendiente
    (``MARCAS_DE_PENDIENTE``) y con «<estado> por el autor el <fecha>» (``MARCA_DE_RATIFICACION``, con el estado y la
    fecha de la ratificación; ronda 5 de la traducción, menor 21): los json de escritura única del armado copian esos
    textos. Si no, se detiene. Devuelve la ratificación."""
    rat = RATIFICACION_T11_T13
    if not isinstance(rat, dict) or not rat:
        raise SystemExit("T13 [delegada]: el armado (PROPUESTA §11, paso 2) no empieza hasta que el autor ratifique T11, "
                         "T12 y T13 (§11, paso 0): red_ampliada_v2.RATIFICACION_T11_T13 está vacía; se llena en el commit "
                         "posterior a la ratificación (§9.0), con la huella nueva del archivo de decisiones")
    faltan = [k for k in RATIFICABLES if rat.get(k) not in ESTADOS_DE_RATIFICACION]
    if faltan:
        raise SystemExit(f"T13 [delegada]: la ratificación no dice si {faltan} quedan ratificadas o cambiadas "
                         f"({'/'.join(ESTADOS_DE_RATIFICACION)}); el armado no empieza")
    sha = rat.get("decisiones_sha256")
    if sha != DECISIONES_TRADUCCION["sha256"] or sha == DECISIONES_SIN_RATIFICAR:
        raise SystemExit(f"T13 [delegada]: la ratificación cita el archivo de decisiones {str(sha)[:8]}…; tiene que ser "
                         f"el de DECISIONES_TRADUCCION ({DECISIONES_TRADUCCION['sha256'][:8]}…) con la ratificación "
                         f"anotada, no el de antes ({DECISIONES_SIN_RATIFICAR[:8]}…)")
    en_cfg = (((cfg.get("red_de_monitores") or {}).get("ratificacion_t11_t13") or {}).get("valor")
              if isinstance(cfg, dict) else None)
    if en_cfg != rat:
        raise SystemExit("T13 [delegada]: config_v2.json no repite la ratificación de red_ampliada_v2.RATIFICACION_T11_T13 "
                         "en red_de_monitores.ratificacion_t11_t13.valor")
    try:
        en_contrato = cfg["contrato"]["enmiendas"][2]["decisiones_de_traduccion"]
    except (KeyError, IndexError, TypeError):
        en_contrato = None
    if not isinstance(en_contrato, dict):
        raise SystemExit("T13 [delegada]: config_v2.json no trae contrato.enmiendas[2].decisiones_de_traduccion, donde la "
                         "ratificación cambia los textos de T11, T12 y T13")
    malos = []
    for k in DECISIONES_DELEGADAS:
        marca = MARCA_DE_RATIFICACION.format(estado=rat.get(k), fecha=rat.get("fecha"))
        for donde, texto in (("red_ampliada_v2.DECISIONES_TRADUCCION", DECISIONES_TRADUCCION.get(k)),
                             ("contrato.enmiendas[2].decisiones_de_traduccion", en_contrato.get(k))):
            texto = " ".join(texto) if isinstance(texto, list) else str(texto or "")
            if any(m in texto for m in MARCAS_DE_PENDIENTE) or marca not in texto:
                malos.append(f"{k} en {donde}")
    if malos:
        raise SystemExit(f"T13 [delegada]: con la ratificación anotada, los textos de T11, T12 y T13 tienen que dejar de "
                         f"decir que están pendientes y decir «{MARCA_DE_RATIFICACION}» (con su estado y la fecha "
                         f"{rat.get('fecha')}): {malos}; los json de escritura única del armado los copian")
    return dict(rat)


def exigir_traduccion_confirmada(r, cfg: dict | None = None, estado=None, espejo: Path | None = None,
                                 rutas=None, del_espejo: dict | None = None, componentes: bool | None = None,
                                 ratificacion: bool | None = None) -> dict:
    """R22: antes de escribir cualquier artefacto de la red 2, la traducción tiene que estar en la configuración y
    confirmada en git, en AP y en su espejo APH (``verificar_espejo``), se lance el programa desde AP o desde el
    espejo (``par_de_repositorios``), y ``config/componentes_compartidos.json`` tiene que registrar la huella de cada
    archivo (``verificar_componentes``). Todos los programas que la llaman son del armado (§11, paso 2), así que exige
    además la ratificación de T11, T12 y T13 (T13 [delegada]: ``exigir_ratificacion``). ``estado``: función (repo,
    rutas) → estado, para las pruebas (por omisión, ``estado_git``); con un ``estado`` simulado, el espejo sólo se
    revisa si se da ``espejo``, los componentes sólo si ``componentes`` es True y la ratificación sólo si
    ``ratificacion`` es True. ``rutas`` y ``del_espejo``, sólo para las pruebas (por omisión, ``ARCHIVOS_TRADUCCION`` y
    ``ARCHIVOS_DEL_ESPEJO``); ``ratificacion=False``, sólo para las pruebas de git."""
    import _rutas_v2 as rv

    cfg = rv.cargar_config(r) if cfg is None else cfg
    rutas = ARCHIVOS_TRADUCCION if rutas is None else tuple(rutas)
    if "red_de_monitores" not in cfg:
        raise SystemExit("config_v2.json no trae red_de_monitores: el bloque de la red ampliada no está traducido "
                         "(R22, paso 2); la red 2 no escribe nada")
    if estado is None:
        canonico, del_par = par_de_repositorios(r.repo)
        espejo = del_par if espejo is None else Path(espejo)
    else:
        canonico = Path(r.repo)
    est = (estado or estado_git)(canonico, rutas)
    pendientes = {k: v for k, v in est.items() if v != "rastreado"}
    if pendientes:
        raise SystemExit(f"la traducción no está confirmada en git en {canonico.name} (R22, paso 2): {pendientes}")
    if espejo is not None:
        verificar_espejo(canonico, espejo, rutas, estado, del_espejo)
    if componentes if componentes is not None else estado is None:
        verificar_componentes(canonico, rutas)
    if ratificacion if ratificacion is not None else estado is None:
        exigir_ratificacion(cfg)
    return est


RUTA_CONFIG = "scripts_modelo_1km/v2/config_v2.json"


def exigir_config_confirmada(r, estado=None, espejo: Path | None = None) -> dict:
    """R22, paso 4 («el anexo, confirmado en git y sellado»; quinta revisión, menor 12): con la red 2 ningún ajuste corre
    sobre un ``config_v2.json`` sin confirmar: tiene que estar rastreado y sin cambios en AP y, con los mismos bytes,
    rastreado y sin cambios en el espejo (``par_de_repositorios``), se lance el programa desde donde se lance. El sello
    (OpenTimestamps) es un paso aparte que el código no comprueba. ``estado``: función (repo, rutas) → estado, para las
    pruebas; con un ``estado`` simulado, el espejo sólo se revisa si se da ``espejo``. Devuelve el estado en AP."""
    try:
        rel = Path(r.config).resolve().relative_to(Path(r.repo).resolve()).as_posix()
    except (AttributeError, ValueError):
        rel = RUTA_CONFIG
    if estado is None:
        canonico, del_par = par_de_repositorios(r.repo)
        espejo = del_par if espejo is None else Path(espejo)
    else:
        canonico = Path(r.repo)
    est = (estado or estado_git)(canonico, [rel])
    if est.get(rel) != "rastreado":
        raise SystemExit(f"{rel} no está confirmado en git en {canonico.name} ({est.get(rel)}): el anexo «Registro de la "
                         f"red v2» tiene que estar confirmado en git antes de cualquier ajuste (R22, paso 4)")
    if espejo is not None:
        espejo = Path(espejo)
        if not (espejo / rel).is_file() or (espejo / rel).read_bytes() != (canonico / rel).read_bytes():
            raise SystemExit(f"{rel} no es el mismo en el espejo {espejo.name}: el anexo «Registro de la red v2» tiene que "
                             f"estar confirmado en git en AP y en el espejo (R22, paso 4)")
        en_espejo = (estado or estado_git)(espejo, [rel])
        if en_espejo.get(rel) != "rastreado":
            raise SystemExit(f"{rel} no está confirmado en git en el espejo {espejo.name} ({en_espejo.get(rel)}): el anexo "
                             f"«Registro de la red v2» tiene que estar confirmado en git antes de cualquier ajuste (R22, "
                             f"paso 4)")
    return est


# ---------------------------------------------------------------------------
# §0 del contrato («Procedencia»): con qué código y con qué traducción se escribe cada artefacto de la red 2
# ---------------------------------------------------------------------------
AQUI = Path(__file__).resolve().parent
MODULOS_RED2 = ("reloj_sinca_v2.py", "unidades_v2.py", "contraste_unidades_v2.py", "duplicados_v2.py",
                "red_ampliada_v2.py", "derivado_red2_v2.py", "panel_red2_v2.py", "pliegues_red2_v2.py")


def commit_de(repo, rutas=None) -> str:
    """Sólo leyendo: el HEAD de ``repo`` o, con ``rutas``, el último commit que tocó alguna de ellas; «desconocido» si no
    hay git o ninguna está en la historia."""
    import subprocess

    args = ("log", "-1", "--format=%H", "--", *rutas) if rutas is not None else ("rev-parse", "HEAD")
    try:
        p = subprocess.run(["git", "--no-optional-locks", "-C", str(repo), *args], capture_output=True, text=True,
                           timeout=120)
    except (OSError, subprocess.SubprocessError):
        return "desconocido"
    return (p.stdout.strip() or "desconocido") if p.returncode == 0 else "desconocido"


def huellas_red2(carpeta: Path = AQUI) -> dict:
    """sha256 de cada módulo de la red 2 tal como corre (los que declara ``red_de_monitores.codigo``)."""
    return {f"scripts_modelo_1km/v2/{m}": sha256_archivo(Path(carpeta) / m) for m in MODULOS_RED2}


def traduccion_de(r, compuerta: dict | None = None) -> dict:
    """§0 y R22 (quinta revisión, mayores 1 y 2): la traducción con que se escribe un artefacto de la red 2. ``commit``
    es el último commit de AP que tocó un archivo de la traducción (``ARCHIVOS_TRADUCCION``) y ``commit_espejo`` el del
    espejo (con ``ARCHIVOS_DEL_ESPEJO``): no cambian si otro frente confirma otra cosa en el repositorio, pero sí con un
    commit nuevo de la traducción (la ratificación de T11 o el camino de la 518). Lleva también los HEAD de los dos, el
    estado de la compuerta (``exigir_traduccion_confirmada``), la huella conjunta de los archivos de la traducción tal
    como están en AP y la ratificación de T11 a T13 con que se escribió (``RATIFICACION_T11_T13``, T13 [delegada]; ronda
    5 de la traducción, menor 21). Sólo lee git y archivos de código."""
    from _traza_v2 import sha256_json

    try:
        canonico, espejo = par_de_repositorios(r.repo)
    except SystemExit:
        canonico, espejo = Path(r.repo), None
    hay_espejo = espejo is not None and Path(espejo).is_dir()
    huellas = {rel: sha256_archivo(Path(canonico) / rel) for rel in ARCHIVOS_TRADUCCION if (Path(canonico) / rel).is_file()}
    return {"commit": commit_de(canonico, ARCHIVOS_TRADUCCION), "head": commit_de(canonico),
            "commit_espejo": commit_de(espejo, [*ARCHIVOS_TRADUCCION, *ARCHIVOS_DEL_ESPEJO]) if hay_espejo
            else "desconocido",
            "head_espejo": commit_de(espejo) if hay_espejo else "desconocido",
            "compuerta": None if compuerta is None else
            {"archivos": len(compuerta), "confirmada": bool(compuerta) and all(v == "rastreado" for v in compuerta.values())},
            "huella_archivos": sha256_json(huellas), "archivos": len(huellas),
            "ratificacion": dict(RATIFICACION_T11_T13) if isinstance(RATIFICACION_T11_T13, dict) else None}


def traza_red2(r, compuerta: dict | None, insumos=None, semillas=None, hilos: int = 1, programa: str | None = None,
               parametros: dict | None = None) -> dict:
    """La procedencia que lleva cada json que escribe la red 2 (§0 del contrato: «cada artefacto registra el commit, el
    hash del código, el sha256 de cada insumo, la versión de cada biblioteca, los hilos y las semillas»): la
    ``_traza_v2.traza`` de la v2 más ``programa_red2`` (quién escribe), ``codigo_red2`` (``huellas_red2``) y
    ``traduccion`` (``traduccion_de``). No entra en ninguna comparación de escritura única, que compara huellas de
    series y de contenido."""
    from _traza_v2 import traza

    t = traza(dict(insumos or {}), semillas, int(hilos), rutas=r, parametros=parametros)
    t["programa_red2"] = programa
    t["codigo_red2"] = huellas_red2()
    t["traduccion"] = traduccion_de(r, compuerta)
    return t
