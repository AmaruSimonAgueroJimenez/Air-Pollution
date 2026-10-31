"""Código ajeno por ruta y huella: adaptador, ``dmc_features``, descargador, la clausura del reloj, su píxel y extracciones
por AST.

Nada de ese código se modifica (§2.1 del texto). Reutiliza ``reloj_dmc.fijados`` (``cargar_por_ruta``,
``extraer_por_ast``, ``macrozona_region``, ``MODULOS_PROHIBIDOS``). ``preflight_v3`` y ``runner_v3`` nunca se cargan:
sólo se compara su huella (§1 del diseño). Todo lo demás del reloj (el validador de RELOJ §7.5 y, en M5,
``elegir_pixel``, FIJ-11) llega por funciones de este módulo que comprueban sus huellas.

Lecturas propias (FIJ-n), para el addendum de M1:
- FIJ-1. **Clausura del reloj (MC-17; decisión E5-F del autor).** Son los seis archivos de ``MODULOS_RELOJ`` (los que
  arrastra ``reloj_dmc.politica``), más el ``__init__`` (FIJ-8). Desde el 2026-10-27 se fijan las huellas de AP
  ``1da0236`` («Reloj DMC, Enmienda 5»), el código del nuevo cierre de C1 del reloj: ``HUELLAS_RELOJ_1DA0236``, que
  ``HUELLAS_RELOJ`` nombra como la vigente, comprobadas con ``git show 1da0236:<ruta>`` y en la copia de trabajo. El C1
  cerró con el texto consolidado v1.2 (APH ``1f59e6e``, ``auditoria/20261027/reloj_dmc/PROTOCOLO_RELOJ_DMC_v1.2.md``)
  y su addendum (APH ``73615e8``, ``auditoria/20261027/reloj_dmc/addendum_c1.json``), cuyas huellas van en
  ``HUELLAS_CODIGO``. Como C1 cerró antes de sellar M1, por MC-17 la clausura va al addendum de M1. Si el reloj cambia
  otra vez, ``test_clausura_del_reloj`` falla y hay que recalcularla (§10, punto 2, del diseño).
  **Historia.** La clausura anterior, la del primer cierre de C1, era la de AP ``4b50b0d``
  (``HUELLAS_RELOJ_4B50B0D``, ``COMMIT_RELOJ_4B50B0D``). De ella a ``1da0236`` sólo cambió ``constantes.py``
  (10354281… → 95deee46…: las versiones del texto del reloj, v1.0.5 y v1.2); ``test_fijados`` lo comprueba con git.
- FIJ-2. ``cargar_validador_reloj`` compara las huellas antes de importar ``reloj_dmc.politica`` y otra vez
  después, y exige que los módulos cargados sean los de ``AP/scripts_modelo_1km/reloj_dmc``. Desde la revisión de la
  ola 1 (B-H17) la comprobación «antes» es de verdad previa: si ``reloj_dmc.politica``, ``tipos``, ``constantes`` o
  ``tablas`` ya están en ``sys.modules`` cuando se llama (y no los cargó antes esta misma función con las mismas
  huellas), falla; ``permitir_cargados=True`` lo permite, sólo para las pruebas que corren en un proceso donde otras
  pruebas ya los cargaron. Límites declarados: ``reloj_dmc`` (su ``__init__``), ``reloj_dmc.entorno`` y
  ``reloj_dmc.fijados`` ya están cargados siempre (los importan ``entorno`` y este módulo), así que para ellos la
  comprobación «antes» es la del archivo en disco al llamarse; y la importación es la normal de Python (no
  ``cargar_por_ruta``), porque ``politica`` importa a sus hermanos como paquete. Desde la ola 5, «los cargó antes esta
  misma función» vale para lo que cargó cualquiera de las dos funciones del reloj (FIJ-11). **``permitir_cargados=True``
  es sólo para pruebas:** ``orquestacion`` y el ejecutable no lo usan. Lo que ya estaba cargado por otro camino al
  empezar una llamada con él no queda anotado como propio, así que una llamada estricta posterior, de cualquiera de las
  dos funciones, sigue fallando (revisión de la ola 5, H2). Las dos funciones exigen además que el reloj no tenga
  bytecode guardado (FIJ-11, H3).
- FIJ-8. **La clausura lleva un séptimo archivo** (B-H17): ``reloj_dmc/__init__.py`` (de78881a…, igual en ``4b50b0d`` y
  en ``1da0236``), que
  se ejecuta al importar cualquier módulo del reloj. ``MODULOS_RELOJ`` sigue siendo la lista de seis de MC-17;
  ``ARCHIVOS_RELOJ`` (``__init__`` más los seis) es la que se comprueba y la que va al addendum o al registro de M2a.
  Es un refuerzo de MC-17, no un cambio de regla.
- FIJ-9. **Macrozonas** (B-H18, A-H6; D9). ``macrozona_region`` copia fiel ``MACROZONA_REGION`` de ``_comun_modelo``,
  que da a la región 0 la macrozona «sin_region»: no es una macrozona, y ``tipos.macrozona_o_ninguna`` la vuelve None
  (D9: esas horas cuentan sólo en lo nacional). ``macrozona_codigo`` copia, también por AST y con la misma huella,
  ``MACROZONA_CODIGO`` (la codificación de ``macrozona_cod`` de ``celdas.parquet``): trae además «insular» (6), la de
  las celdas generadas fuera del dominio ACAG (Rapa Nui y Sala y Gómez), que ninguna región da.
- FIJ-3. **Sólo ``orquestacion`` lanza procesos** (§0, regla 3): este módulo no corre ``micromamba list``. La huella
  del intérprete (§9.3) se compara con el texto de esa salida, que entrega quien llama
  (``comprobar_codigo_fijado(…, micromamba_list=…)``); la regla de la huella es la de ``m0/preparar_m0.interprete``
  (sha256 del texto en UTF-8).
- FIJ-4. **Huellas de §9.3.** ``HUELLAS_CODIGO`` son las del código, los textos y la configuración de §9.3 y §9.4, y
  ``comprobar_codigo_fijado`` las recalcula. Las de datos (``HUELLAS_DATOS`` y ``HUELLAS_ERA5L_AGREGADAS``) se copiaron
  de ``m0/huellas_m0.json`` y de §9.3 y §9.4 del diseño; no se comprueban en M1 porque exigen abrir datos reales
  (decisión 4 de ``COORDINACION_M1.md``): las comprueba M2a.
- FIJ-5. ``SHA_PESOS_PY`` es ``scripts_neuro/_pesos.py`` (2f19fa53…), el que carga ``exposicion_horaria_v3`` por ruta
  (``EX.PESOS_PY``) y del que ``meteo_civil_v3`` toma los pesos; ``SHA_PESOS_POBLACION`` es ``pesos_poblacion.py``
  (b6cc4947…), el que escribe la tabla. §9.3 del diseño cita el segundo y §9.4 el primero: los dos van a la lista.
- FIJ-6. ``esquema_meteo_civil_v3`` lee por AST ``VARIABLES``, ``ESQUEMA_DIARIO``, ``MAGNUS_A``, ``MAGNUS_B`` y la
  función ``tabla_meteo`` de ``v3_next/meteo_civil_v3.py`` (idéntico al de ``v3``), y llama a ``tabla_meteo`` con una
  comuna y un día para leer los tipos de sus columnas. No importa el módulo (arrastra ``_rutas_v3``, ``dlnm_v3`` y
  ``exposicion_horaria_v3``).
- FIJ-7. ``regla_el_features`` no ejecuta ``derivadas_horarias``: la lee por AST y exige su forma (Magnus
  a·exp(b·t/(t + c)) con las mismas constantes en e_s y en e, t2m y d2m en K menos una constante, y
  ``arctan2(el_u10, el_v10)``). Si cambia la forma, falla en vez de adivinar.
- FIJ-10. **Las huellas de v2 después de M0 (D51 y D54, decisiones del autor).** ``v2/correr_v2.py`` y
  ``v2/config_v2.json`` cambiaron después de M0 por la traducción de la red ampliada (AP ``889b972``) y su
  ratificación (AP ``6c15981``). La configuración cambió además por la política operativa de espacio SINCA autorizada
  el 2026-10-28 (AP ``8542e61``; autoridad en ``APH/auditoria/20261028/sinca_espacio/DECISION_ESPACIO.md``).
  Por MC-09 y D51 se fijan las vigentes: ``SHA_CORRER_V2`` (1423ef3f…, AP ``889b972``) y ``SHA_CONFIG_V2``
  (1bcb3ff4…, AP ``8542e61``). La configuración de la ratificación, 51df5063…, se conserva como historia en
  AP ``6c15981``; 02d8c386… fue la de antes de ratificar. Las de M0 (534e484b… y 232c75b3…) siguen citadas en
  ``SHA_CORRER_V2_M0`` y ``SHA_CONFIG_V2_M0``: son las de ``m0/huellas_m0.json``, que no se toca, y de AP ``c7c47e8``.
  D54 extiende D51 a ``v2/reloj_sinca_v2.py`` (c1eb98c5…, AP ``889b972``; en M0 no existía). ``HUELLAS_D51`` lleva,
  por archivo, la de M0, la vigente y el commit de cada una; ``test_fijados`` las compara con git. Si vuelven a
  cambiar antes de M3-4, rige la de su último commit (D51): se vuelve a fijar aquí, en ``test_particiones`` y en
  §9.3 del diseño. No se cambia ningún parámetro de S6. P78 queda descartada por D53.
- FIJ-11. **El píxel del reloj (MC-52, A27; ola 5).** ``cargar_elegir_pixel(ap, aph, huellas)`` entrega
  ``reloj_dmc.extraccion.elegir_pixel`` (el mismo objeto del módulo, no un envoltorio) en un ``PixelReloj``, junto con
  ``EleccionPixel``, los umbrales del reloj con que se llama (``PixelReloj.elegir`` los pone) y el radio (``radio_km``).
  ``PixelReloj.enlazar`` es la regla de ``extraccion.enlazar_pixeles`` para una estación: sin coordenadas finitas o
  fuera del rango de RELOJ §3.3 (``tablas.coordenadas_en_rango`` del reloj: −90 ≤ lat ≤ −17 y −110 ≤ lon ≤ −55) no hay
  píxel; si no, ``elegir``. Es la que debe usar M5. Las coordenadas son las del catálogo vigente en RELOJ C2, leídas como
  RELOJ §3.3 (en M1, ``estaticas_nasadem.interpretar_coordenada``, copia de ``tablas.interpretar_coordenada``: NAS-1);
  ``test_fijados`` comprueba que el rango del reloj y ``estaticas_nasadem.coordenadas_en_rango`` coinciden.
  - **La clausura ampliada.** ``extraccion.py`` arrastra seis archivos de la clausura de MC-17 (todos salvo
    ``politica``) y dos más del reloj, ``numerico.py`` y ``umbrales.py``; ``test_fijados`` lo comprueba por AST, también
    en las importaciones dentro de funciones. ``MODULOS_PIXEL`` son esos tres archivos nuevos y ``ARCHIVOS_CLAUSURA``
    los diez (los siete de FIJ-8 más ``MODULOS_PIXEL``): es la lista que va al addendum de M1, con ``HUELLAS_CLAUSURA``.
    Las tres huellas nuevas son las de AP ``1da0236`` (``HUELLAS_PIXEL_1DA0236``: ``extraccion`` dc6a8788…,
    ``numerico`` c463336c…, ``umbrales`` 075834dc…), comprobadas con ``git cat-file`` y en la copia de trabajo. En AP
    ``4b50b0d`` ``umbrales`` era el mismo, y ``numerico`` y ``extraccion`` eran otros: la errata E-1 de la Enmienda 5
    del reloj (el empate por menor ``pixel_id`` con tolerancia, ``numerico.mas_cercano``). ``HUELLAS_RELOJ`` (siete)
    sigue siendo la del validador.
  - **La carga.** Las diez huellas se comprueban antes y después, y los módulos del reloj cargados deben ser los de
    ``AP/scripts_modelo_1km/reloj_dmc``. ``extraccion.py`` se carga por ruta y huella (``reloj_dmc.fijados.cargar_por_ruta``
    con su nombre de paquete, ``reloj_dmc.extraccion``: se ejecutan exactamente los bytes con la huella); lo que importa
    llega por la importación normal, como los hermanos de ``politica`` (FIJ-2). Como el adaptador, esa carga no es una
    importación y la prueba del grafo de ``test_meteo_combinada`` no la ve: la comprueba ``test_fijados``. No puede
    haber cargado antes ninguno de ``CARGADOS_DESPUES_PIXEL`` (``tipos``, ``constantes``, ``tablas``, ``numerico``,
    ``umbrales`` y ``extraccion``) salvo este módulo con las mismas huellas, o con ``permitir_cargados=True``. **FIJ-2 se
    extiende:** las dos funciones anotan lo que cargaron (``_PROPIOS``), así que el validador acepta ``tipos``,
    ``constantes`` y ``tablas`` que cargó antes ``cargar_elegir_pixel`` con las mismas huellas, y al revés: M5 puede
    llamar a las dos en un mismo proceso, en cualquier orden. **``permitir_cargados=True`` es sólo para pruebas**
    (``orquestacion`` no lo usa): lo que estaba cargado por otro camino al empezar la llamada no se anota como propio, y
    una llamada estricta posterior sigue fallando (H2).
  - **Sin bytecode guardado (H3).** ``-B`` sólo evita escribir ``.pyc``: uno presente en ``reloj_dmc/__pycache__`` con
    la marca de tiempo y el tamaño del fuente se ejecutaría en lugar de los bytes con huella. Antes y después de cargar,
    las dos funciones exigen que no exista la carpeta ``reloj_dmc/__pycache__`` ni el ``.pyc`` de ningún archivo de su
    clausura (el que da ``importlib.util.cache_from_source`` y el ``__spec__.cached`` de los ya cargados).
    ``extraccion.py`` no depende de esto, porque se compila desde sus bytes; sus dependencias, sí.
  - **Los umbrales.** Son los anclados en C0, con el cargador del propio reloj (``reloj_dmc.umbrales.cargar_c0``): el
    JSON ``c0/reloj_dmc_v1.json`` (3251a4d8…, ``SHA_JSON_RELOJ_C0``, el de ``m0/huellas_m0.json``) y el texto C0
    (5fff0727…), los dos de APH ``d02f918``. Antes de llamarlo, este módulo exige que las rutas y huellas que ancla
    ``reloj_dmc.umbrales`` sean las suyas y lee los dos archivos con su huella. ``elegir_pixel`` sólo usa
    ``PIXEL_RADIO_KM`` (15 km). La línea «Píxel» del Anexo B es la misma en los seis textos del reloj, del v1 al v1.0.5
    (``test_fijados``, con ``regenerar_desde_texto`` y ``traducir_fijos`` del reloj), y los meses de validez del píxel
    (200001, 201307 y 202507) son los de ``fondo_era5l``.
  - **El v1.2 y la C4 del reloj (límite declarado, acotado).** C4 tomó sus umbrales del JSON y del texto v1.2 que nombra
    el addendum de C1. M1 no los lee (MC-17): fija sólo sus huellas, el texto (479ed38f…) y su JSON
    (``auditoria/20261027/reloj_dmc/reloj_dmc_v1.json``, 6f60f3bd…, ``SHA_JSON_RELOJ_V1_2``), los dos de APH ``1f59e6e``.
    Ese commit dice que los escribió ``enmienda5/generar_v1_2.py`` (faa0ba8a…, APH ``07881ed``, ``SHA_GENERAR_V1_2``).
    El código de ese generador, que ``test_fijados`` lee por AST sin correrlo, exige dos cosas: que los Anexos A a B del
    v1.2 sean byte a byte los del v1.0.5 (21f1b469…), y que su JSON sea el de C0 salvo «generado_desde» y «bateria».
    Así, los umbrales de C4 son los de C0 si C4 usó ese JSON. Lo dice ``configuracion.sha256`` de la política
    publicada, que CEG-13 deja abrir: M2a puede compararla con ``SHA_JSON_RELOJ_V1_2`` sin abrir el addendum ni el v1.2.
    Hasta esa comparación, y porque la autoría del generador la da el commit y no una prueba, queda como límite.
  - **Ceguera.** No abre ninguna salida del reloj (ni su política, ni ``artefactos_evaluados``, ni nada de sus
    corridas) ni datos DMC. ``test_fijados`` lo vigila en un intérprete nuevo, con un gancho de auditoría de Python:
    fuera del intérprete sólo se abren los diez archivos de código y los dos de C0. El gancho no ve las lecturas de las
    bibliotecas en C (pyarrow, netCDF4: CEG-5 de ``ceguera``); la carga no lee ningún archivo con ellas (``extraccion``
    las usa sólo dentro de funciones que no se llaman).
  - ``PixelReloj`` vive aquí y no en ``tipos`` porque lleva objetos del reloj, que ``tipos`` no importa.
Depende de: entorno, reloj_dmc.fijados (y, por ruta y huella, reloj_dmc.extraccion: FIJ-11).
"""
from __future__ import annotations

import ast
import hashlib
import importlib
import importlib.util
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Any, Callable, Iterable, Mapping

from meteo_combinada import entorno
from reloj_dmc import fijados as _rf

# ---------------------------------------------------------------------------
# Huellas fijadas (§9.3 y §9.4 del diseño; m0/huellas_m0.json). M1 las vuelve a calcular y deben coincidir.
# ---------------------------------------------------------------------------
SHA_ADAPTADOR = "f61559eab281846a4935eb1ea66217e039ff37a727833bf8fcaa7a774b776754"
SHA_DMC_FEATURES = "157628564ffafb2cfc6aab5403e984d8451f7faa31e6f5ce21e743023d766bec"
SHA_PREFLIGHT_V3 = "21905706c69cb9a2b52cdd1a2e3ce17a535d5f18e32ead71d1348020f63bc0f7"
SHA_COMUN_MODELO = "a83c0384266554e16ab397749544759ae1cf161f138361eefa7d1ad3e29aa6f4"
SHA_DESCARGADOR = "578fa26eea5b4ac4733c56aaf08e9b7b8904595fb8447dd54feb838642612120"
SHA_FEATURES = "8fd699929c117067962e9ed24c0ea6b137d0c58d5ca17b9fce3a3759793d6838"
SHA_METEO_CIVIL_V3 = "483f63a634252fa383ae8a0abb3fd0e1472a73b67c8b36c1b2534a231f627bba"
SHA_EXPOSICION_V3 = "2eef68b329793316acabcd7e58ea9654038dc7ac3ccfe13b4031db7608a99b29"
SHA_PESOS_PY = "2f19fa53bc7893d5220fd19034277eb840d11c020d43a3f83769ad2f09b310ed"          # scripts_neuro/_pesos.py (FIJ-5)
SHA_PESOS_POBLACION = "b6cc4947f432ed5e26e6d68468c25816f680efec88ceffdce0613bff5cb63bf9"   # scripts_neuro/pesos_poblacion.py
SHA_PREPARAR_M0 = "49503a3a88a9b9b331d8f51704708a7154bfc311a1f4a0eb6ca1f22d2f255d81"
SHA_CORRER_V2 = "1423ef3f7a8d7bc35d8ee1802187de95129e46afe276241e29a0c7e486f6445d"        # vigente (D51; AP 889b972)
SHA_CONFIG_V2 = "1bcb3ff49729ffa65cc89f646f1c711f01a2ecae1241db1cef91eace36aabaae"        # vigente (D51; AP 8542e61)
SHA_RELOJ_SINCA_V2 = "c1eb98c52660dae3755c65a69fb2cc33e7e8d54736c269cc111bde35289795f7"   # D54; AP 889b972
SHA_CORRER_V2_M0 = "534e484b66ed9575f36a2ec5fc75052a9a2544656cf3e4a80077b90f96c69b07"     # estado de M0 (FIJ-10)
SHA_CONFIG_V2_M0 = "232c75b3376b6fd7c4f73c885c812e170abff7c1a8817d1ac64cc76c68b0534c"     # estado de M0 (FIJ-10)
SHA_CONFIG_V3 = "ab248343239b58853d59516b1409d937e0b6a7ee36461c9df3b1eb7c09d17d94"
SHA_COVARIABLES = "0941baf39bd85eeb013118a2a026368b95932e37c480ecd22f4f9ec428113081"
SHA_POLITICA_TEMPORAL = "41018e4c066d9e30b5ba0b1ff92d47eeb47bab1984b5b8c45a778939359ac61c"
SHA_TEXTO_M0 = "0d0972d8c8ebf09bb39bf45154496e72b524cdb8d57f9ce029aa53a16708edaf"         # v2.1
SHA_JSON_M0 = "156587f195f77009fe49bfa9497fd4a334d6b4bbe14064b46b8f3d3bca5e488a"
SHA_TEXTO_V2_4 = "eaedb10998e1a3f37f83f036c478afb5cf3fd3ccb5262477bd394dc220b1908b"   # historia: EMC3, D65
SHA_TEXTO_VIGENTE = "7771e830c526d8a0da93453e7e2d821896ba797147d14803969907ce5749589d"   # v2.5: EMC4, D68; post_hoc
SHA_TEXTO_V2_3 = "b4175f785ec57811702352d9d063164a5dce05f325a48c327a6d554a09ceddc2"   # historia: Enmienda 2, APH dd6c1c6
SHA_TEXTO_V2_2 = "f059c14cc4114765a0618b263b6e8a0308d1b772c3ea824b79d0ebe0af5254e9"      # v2.2 (Enmienda 1), el que el v2.3 enmienda
SHA_RELOJ_C0 = "5fff072783e932843d210561a46f5344351a39b7dd85f5775ac884eaf96e4d85"
SHA_JSON_RELOJ_C0 = "3251a4d81a76f5066fc217557f279d428740898f6a2f26d6c8fbbfb721c77002"   # umbrales del reloj en C0 (FIJ-11)
SHA_RELOJ_V1_0_2 = "ee5dec6e7a1ff65f19a814d4994d804e9a4e3e8ad2765b6d8590e9286543217d"
SHA_RELOJ_V1_0_3 = "7a019348b8ff6e26cef81c86881265a3392172acbf175b118a8682e9cd345f97"
SHA_RELOJ_V1_0_4 = "d8f61cfc1ab01da17fd97b8e5e871b55d4557a66ff2599a585b362689475b54d"
SHA_RELOJ_V1_0_5 = "21f1b4699dea7106b0e6065e0f232e8aeb97ca618b812b2dee4a2d3b9b803c89"     # Enmienda 5 del reloj
SHA_RELOJ_V1_2 = "479ed38f8e594e10996cd79e5741d440d291f0dfeac43a279386e30525cabb85"       # C1 del reloj (APH 1f59e6e)
SHA_ADDENDUM_C1_RELOJ = "cd1c434493cafcda2ebfcdecf4a07738a9b9dac6794f41d960e03c6e445b51d2"  # APH 73615e8
SHA_JSON_RELOJ_V1_2 = "6f60f3bdd59b98754e458db8e7c3b5be720baffdf2428f1e1acbbe7455a6f05a"   # APH 1f59e6e; sólo su huella
SHA_GENERAR_V1_2 = "faa0ba8ae78f2fafa27f0f767bdf5dbd2f4ba83b224b67f13e42e2a8fef20b40"      # APH 07881ed (FIJ-11)
SHA_TEXTO_7_5 = "583626404e6326f44bd46be44bbb2a0222e03df0fb861817c94ca0d0ec017405"
SHA_ENMIENDA_2_RED = "274ebae06bee8eeeb7470a650ce0539af751577d292513b8198cdec7c159094b"     # la de APH f2c6cfc
SHA_MICROMAMBA_LIST = "0b5bc40b49e6cab503c88471a2e8dd4cd30bec9a0c2485b44705f8e9a670ec44"   # FIJ-3

# Rutas relativas a su repositorio.
RUTA_ADAPTADOR = _rf.RUTA_ADAPTADOR                      # AP
RUTA_DMC_FEATURES = _rf.RUTA_DMC_FEATURES                # AP
RUTA_PREFLIGHT_V3 = _rf.RUTA_PREFLIGHT_V3                # AP: sólo su huella
RUTA_COMUN_MODELO = _rf.RUTA_COMUN_MODELO                # AP: sólo por AST
RUTA_DESCARGADOR = _rf.RUTA_DESCARGADOR                  # AP
RUTA_FEATURES = "scripts_modelo_1km/_features.py"        # AP: sólo por AST
RUTA_RELOJ = "scripts_modelo_1km/reloj_dmc"              # AP
RUTA_METEO_CIVIL_V3 = "scripts_riesgo_agudo/v3_next/meteo_civil_v3.py"     # APH: sólo por AST
RUTA_PREPARAR_M0 = "auditoria/20261023/meteo_combinada/m0/preparar_m0.py"  # APH: sólo por AST
RUTA_CORRER_V2 = "scripts_modelo_1km/v2/correr_v2.py"     # AP: sólo su huella
RUTA_CONFIG_V2 = "scripts_modelo_1km/v2/config_v2.json"   # AP: sólo protocolos.BLQ-75.origen_m (test_particiones)
RUTA_RELOJ_SINCA_V2 = "scripts_modelo_1km/v2/reloj_sinca_v2.py"   # AP: sólo por AST o como texto (test_sinca_meteo)
RUTA_RELOJ_C0 = "auditoria/20261023/reloj_dmc/PROTOCOLO_RELOJ_DMC_v1_propuesta.md"   # APH: texto C0 del reloj
RUTA_JSON_RELOJ_C0 = "auditoria/20261023/reloj_dmc/c0/reloj_dmc_v1.json"               # APH: umbrales C0 (FIJ-11)
COMMIT_RELOJ_C0_APH = "d02f91882a13bcefc2cf90712dffba3760f346b6"   # APH: «Reloj DMC, compuerta C0» (los dos de arriba)
RUTA_RELOJ_V1_0_5 = "auditoria/20261023/reloj_dmc/enmienda5/PROTOCOLO_RELOJ_DMC_v1.0.5.md"     # APH
RUTA_GENERAR_V1_2 = "auditoria/20261023/reloj_dmc/enmienda5/generar_v1_2.py"     # APH: sólo por AST (FIJ-11)
RUTA_RELOJ_V1_2 = "auditoria/20261027/reloj_dmc/PROTOCOLO_RELOJ_DMC_v1.2.md"     # APH: sólo su huella (MC-17)
RUTA_JSON_RELOJ_V1_2 = "auditoria/20261027/reloj_dmc/reloj_dmc_v1.json"          # APH: sólo su huella (FIJ-11)
COMMIT_ENMIENDA5_APH = "07881ed6a5808c5ee28370f1cb56bbb3ef9900b9"   # APH: Enmienda 5 del reloj (v1.0.5 y el generador)
COMMIT_C1_RELOJ_APH = "1f59e6e18599bb72a59bbcb1e2e65996c5045564"    # APH: C1 del reloj (el v1.2 y su JSON)

# FIJ-10 (D51, D54): (ruta en AP, huella de M0 o None, commit de M0, huella vigente, commit de la vigente).
COMMIT_M0_AP = "c7c47e85d35889269ac30ae3582d96fbe697b6f8"
HUELLAS_D51: tuple[tuple[str, str | None, str, str, str], ...] = (
    (RUTA_CORRER_V2, SHA_CORRER_V2_M0, COMMIT_M0_AP, SHA_CORRER_V2, "889b97253ec65457fcd1e3136eac1a26edc0edeb"),
    (RUTA_CONFIG_V2, SHA_CONFIG_V2_M0, COMMIT_M0_AP, SHA_CONFIG_V2, "8542e615eeb83f6250911e7cbcea2d4cfdb15c5d"),
    (RUTA_RELOJ_SINCA_V2, None, COMMIT_M0_AP, SHA_RELOJ_SINCA_V2, "889b97253ec65457fcd1e3136eac1a26edc0edeb"),
)

# (repositorio, ruta, sha256, de dónde sale) del código, los textos y la configuración (FIJ-4).
HUELLAS_CODIGO: tuple[tuple[str, str, str, str], ...] = (
    ("AP", RUTA_ADAPTADOR, SHA_ADAPTADOR, "§9.3"),
    ("AP", RUTA_DMC_FEATURES, SHA_DMC_FEATURES, "§9.3"),
    ("AP", RUTA_PREFLIGHT_V3, SHA_PREFLIGHT_V3, "§9.3"),
    ("AP", RUTA_COMUN_MODELO, SHA_COMUN_MODELO, "§9.3"),
    ("AP", RUTA_DESCARGADOR, SHA_DESCARGADOR, "§9.3"),
    ("AP", RUTA_CORRER_V2, SHA_CORRER_V2, "§9.3, D51"),
    ("AP", RUTA_CONFIG_V2, SHA_CONFIG_V2, "§9.3, D51"),
    ("AP", RUTA_RELOJ_SINCA_V2, SHA_RELOJ_SINCA_V2, "§9.4, D54"),
    ("AP", RUTA_FEATURES, SHA_FEATURES, "§9.4"),
    ("AP", "config/sinca/politica_temporal.json", SHA_POLITICA_TEMPORAL, "§9.4"),
    ("APH", "scripts_riesgo_agudo/v3/config_v3.json", SHA_CONFIG_V3, "§9.3"),
    ("APH", RUTA_METEO_CIVIL_V3, SHA_METEO_CIVIL_V3, "§9.3"),
    ("APH", "scripts_riesgo_agudo/v3/meteo_civil_v3.py", SHA_METEO_CIVIL_V3, "§9.3"),
    ("APH", "scripts_riesgo_agudo/v3/exposicion_horaria_v3.py", SHA_EXPOSICION_V3, "§9.3"),
    ("APH", "scripts_neuro/pesos_poblacion.py", SHA_PESOS_POBLACION, "§9.3"),
    ("APH", "scripts_neuro/covariables.py", SHA_COVARIABLES, "§9.3"),
    ("APH", "scripts_neuro/_pesos.py", SHA_PESOS_PY, "§9.4"),
    ("APH", "auditoria/20261023/meteo_combinada/m0/PROTOCOLO_METEO_COMBINADA_v2.1.md", SHA_TEXTO_M0, "§9.3"),
    ("APH", "auditoria/20261023/meteo_combinada/m0/meteo_combinada_v1.json", SHA_JSON_M0, "§9.3"),
    ("APH", RUTA_PREPARAR_M0, SHA_PREPARAR_M0, "§9.3"),
    ("APH", "auditoria/20261023/meteo_combinada/enmienda1/PROTOCOLO_METEO_COMBINADA_v2.2.md", SHA_TEXTO_V2_2,
     "Enmienda 1"),
    ("APH", "auditoria/20261023/meteo_combinada/enmienda2/PROTOCOLO_METEO_COMBINADA_v2.3.md", SHA_TEXTO_V2_3,
     "Enmienda 2"),
    ("APH", "auditoria/20261023/meteo_combinada/enmienda3/PROTOCOLO_METEO_COMBINADA_v2.4.md", SHA_TEXTO_V2_4,
     "historia, Enmienda 3 (D65, post_hoc)"),
    ("APH", "auditoria/20261023/meteo_combinada/enmienda4/PROTOCOLO_METEO_COMBINADA_v2.5.md", SHA_TEXTO_VIGENTE,
     "texto vigente, Enmienda 4 (D68, post_hoc)"),
    ("APH", RUTA_RELOJ_C0, SHA_RELOJ_C0, "§9.3"),
    ("APH", RUTA_JSON_RELOJ_C0, SHA_JSON_RELOJ_C0, "M0, MC-52 (FIJ-11)"),
    ("APH", "auditoria/20261023/reloj_dmc/enmienda2/PROTOCOLO_RELOJ_DMC_v1.0.2.md", SHA_RELOJ_V1_0_2, "§9.3"),
    ("APH", "auditoria/20261023/reloj_dmc/enmienda2/texto_7_5.md", SHA_TEXTO_7_5, "§9.3"),
    ("APH", "auditoria/20261023/reloj_dmc/enmienda3/PROTOCOLO_RELOJ_DMC_v1.0.3.md", SHA_RELOJ_V1_0_3, "§9.4"),
    ("APH", "auditoria/20261023/reloj_dmc/enmienda4/PROTOCOLO_RELOJ_DMC_v1.0.4.md", SHA_RELOJ_V1_0_4, "§9.4"),
    ("APH", RUTA_RELOJ_V1_0_5, SHA_RELOJ_V1_0_5, "§9.4, E5-F"),
    ("APH", "auditoria/20261023/reloj_dmc/enmienda5/texto_7_5.md", SHA_TEXTO_7_5, "§9.4, E5-F"),
    ("APH", RUTA_GENERAR_V1_2, SHA_GENERAR_V1_2, "FIJ-11 (el v1.2 y la C4 del reloj; sólo por AST)"),
    ("APH", RUTA_RELOJ_V1_2, SHA_RELOJ_V1_2, "§9.4, C1 del reloj (E5-F)"),
    ("APH", RUTA_JSON_RELOJ_V1_2, SHA_JSON_RELOJ_V1_2, "FIJ-11 (el v1.2 y la C4 del reloj; sólo su huella)"),
    ("APH", "auditoria/20261027/reloj_dmc/addendum_c1.json", SHA_ADDENDUM_C1_RELOJ, "§9.4, C1 del reloj (E5-F)"),
    ("APH", "auditoria/20261024/sinca_al_modelo/ENMIENDA_2_BLOQUE_RED_AMPLIADA.md", SHA_ENMIENDA_2_RED, "§9.4"),
)

# Datos de §9.3 y §9.4, por alias (FIJ-4): constantes que comprueba M2a, no M1.
HUELLAS_DATOS: Mapping[str, str] = MappingProxyType({
    "ERA5L/catalogo_pixeles.parquet": "cc5054c20c43b08d30d21035b89052c521bc74d204149f205658df1dbdf69410",
    "INVARIANTES/era5land_geopotencial_invariante_chile.nc":
        "bec3c995e3ffdd98442c7db8f2f879bf8197482ae5d27742714b0b1ce5bba520",
    "INVARIANTES/era5land_altitud_modelo_pixeles.parquet":
        "791f7ba29a1ec2b9e5bb2582e48d1fb371e32c709246e70088f0090c035e88e1",
    "NASADEM/manifiestos/nasadem_hgt_20261023T110300Z-75461d99.jsonl":
        "0d837cb58c870df4c7e56ee57dbfd4a52a37b211dc0575b1c8f6b484424c8257",
    "GRILLA/celdas.parquet": "42b4b19613c7de343c856473af64e2c0a6353351f1884c8dba145361292108c3",
    "GRILLA/estaticas.parquet": "606701ef942d907b637cfde10bbe6dbb2e157920f6fae2611e82ecd031470049",
    "GRILLA/estaticas_lulc.parquet": "9cb250712379752f33817d42ed72dd9d637f74e61ef8f60f02e37022cf4b9821",
    "GRILLA/enlaces_productos.parquet": "f441617b16bc518685483a6304f581d0a6ed610bf8a79518ecf4cbd2a2cedbcc",
    "GRILLA/enlaces_interpolacion.parquet": "e2e94bfb2858f432771d7e7b332d85ce7cbea99d115c62d59bb079e0ecaa67f4",
    "GHS/E2020/GHS_POP_E2020_GLOBE_R2023A_54009_100_V1_0_R12_C12.zip":
        "45303a9dcb0d4d7167d6aad328a601a9af777e603435b67d6f77c334875ee61a",
    "GHS/E2020/GHS_POP_E2020_GLOBE_R2023A_54009_100_V1_0_R13_C12.zip":
        "1e13672c85e1f2d08c19aa54fefada258ae5c703b6c656a9348139e40639e482",
    "GHS/E2020/GHS_POP_E2020_GLOBE_R2023A_54009_100_V1_0_R14_C12.zip":
        "52e1867a6d48ad4c508f78b6ba1050b8d8747fb17206da53afddcaa3f1d03a7f",
    "GHS/E2020/GHS_POP_E2020_GLOBE_R2023A_54009_100_V1_0_R14_C13.zip":
        "25d8458718b6bd07d9ac40c2181e168c5bf67255fd930432747303066fc09430",
    "GHS/E2020/GHS_POP_E2020_GLOBE_R2023A_54009_100_V1_0_R15_C12.zip":
        "688a1d139f3bf4071fa7414c032b63614eb8736118da46dcd37af0e55ecc4e1d",
    "GHS/E2020/GHS_POP_E2020_GLOBE_R2023A_54009_100_V1_0_R15_C13.zip":
        "933637cbef487c0f1a5dcdd0f1253e50708c209b6df246209d3381e6eea551ce",
    "GHS/E2020/GHS_POP_E2020_GLOBE_R2023A_54009_100_V1_0_R16_C13.zip":
        "89e61b7b988ea071d198ef3b995d4295fea9bd3fc152ab07006f86c09395bae3",
    "GHS/E2020/GHS_POP_E2020_GLOBE_R2023A_54009_100_V1_0_R16_C14.zip":
        "242a35f99626f9d5dd4a23f0ae749edecf6261679d495cbab123637ac8a7b6b9",
    "SINCA_MET/manifiesto_descarga.csv": "82b8472136c7b5fede8a42e68c2537e6d6e479a108cb2005bae7c9a84b17ca21",
    "SINCA_MET/SHA256SUMS.txt": "c607e58a0c6c4620464cd4aa5eff286669d0cf84ec1f2ea3d1949c05488be01d",
    "SINCA_MET/no_disponibles.csv": "2dd73b5c63b0b26d384e9770b27734abffa8cc520dcc7282d36e7be98a326cf3",
    "SINCA_MET/manifiesto_descarga_20261024b.csv": "1c0a1567901581de49884891a3e0e7fe4659c856116a98ac647d62d362821ca1",
    "SINCA_MET/SHA256SUMS_20261024b.txt": "87d659d575da70bde9e3289b962673db6b2f8eceb04391a05abcd987a0528134",
    "SINCA_MET/no_disponibles_20261024b.csv": "2dd73b5c63b0b26d384e9770b27734abffa8cc520dcc7282d36e7be98a326cf3",
})
# ERA5-Land: huellas agregadas de los 321 manifiestos y de las salidas declaradas (regla de m0/preparar_m0.era5l).
HUELLAS_ERA5L_AGREGADAS: Mapping[str, str] = MappingProxyType({
    "huella_manifiestos": "2ada121c2b93bf1b2ef5135a5ab8712341504fbab243a459a2208fed66da6237",
    "huella_salidas_declaradas": "c05f04a15c1093ebebec642a0f0336e4aeeadcbe8a4bd27ba27f3b959ee3ca1c",
})

# Clausura del reloj (MC-17, FIJ-1; E5-F): los seis archivos que arrastra reloj_dmc.politica, más su __init__ (FIJ-8), y
# sus huellas en AP 1da0236, el código del nuevo cierre de C1 (Enmienda 5 del reloj). La de 4b50b0d queda como historia.
MODULOS_RELOJ = ("entorno", "fijados", "politica", "tipos", "constantes", "tablas")
ARCHIVOS_RELOJ = ("__init__", *MODULOS_RELOJ)
# Módulos que no pueden estar cargados antes de cargar_validador_reloj (FIJ-2): entorno y fijados del reloj ya lo están.
CARGADOS_DESPUES = ("politica", "tipos", "constantes", "tablas")
COMMIT_RELOJ = "1da023640f8e3c65fba461480b5faaf06f158ba2"
HUELLAS_RELOJ_1DA0236: Mapping[str, str] = MappingProxyType({
    "__init__": "de78881a183ed3144c70e8592db0b3bd31dfde8b6ba1febf9adf8d4aa0dabc6a",
    "entorno": "adda1be8e218e54efec67562097551b0ffb70ccf29a63ba3e95ce345ad379e31",
    "fijados": "1b1aec92ca826b901636e371fda542691c90fbd72017c22e595b4770f4fae19c",
    "politica": "ec8695261d27c7e7cd98082d51f47abd8a9988bffdd9546d050d3f37dbbfc96a",
    "tipos": "b260f4ef9c5f7e2476ea59eb8db6e257968018da69a82c081398fc13e5472ffe",
    "constantes": "95deee462ce3b00981e1333155eff00ac7bf7f33afaf60f379b94e4f9153dc74",
    "tablas": "0c7e91798a8e03d1a5068149ec3b2fd8bdc0d73ed681c4db6928129a5aa73a7f",
})
HUELLAS_RELOJ: Mapping[str, str] = HUELLAS_RELOJ_1DA0236          # la vigente (FIJ-1)
# Historia (FIJ-1): la clausura del primer cierre de C1, en AP 4b50b0d. Sólo difiere en constantes.
COMMIT_RELOJ_4B50B0D = "4b50b0d027d7652843e34de3ea68c386b693be4e"
HUELLAS_RELOJ_4B50B0D: Mapping[str, str] = MappingProxyType({
    "__init__": "de78881a183ed3144c70e8592db0b3bd31dfde8b6ba1febf9adf8d4aa0dabc6a",
    "entorno": "adda1be8e218e54efec67562097551b0ffb70ccf29a63ba3e95ce345ad379e31",
    "fijados": "1b1aec92ca826b901636e371fda542691c90fbd72017c22e595b4770f4fae19c",
    "politica": "ec8695261d27c7e7cd98082d51f47abd8a9988bffdd9546d050d3f37dbbfc96a",
    "tipos": "b260f4ef9c5f7e2476ea59eb8db6e257968018da69a82c081398fc13e5472ffe",
    "constantes": "10354281bf5b96e8ab652450668a58042fc922cc8fc8df5bd8537a67052cb699",
    "tablas": "0c7e91798a8e03d1a5068149ec3b2fd8bdc0d73ed681c4db6928129a5aa73a7f",
})
# Clausura ampliada para el píxel del reloj (FIJ-11; MC-52, A27): extraccion.py y los dos módulos del reloj que arrastra
# además de los de MC-17. Huellas de AP 1da0236 (las mismas que la copia de trabajo).
MODULOS_PIXEL = ("extraccion", "numerico", "umbrales")
ARCHIVOS_CLAUSURA = (*ARCHIVOS_RELOJ, *MODULOS_PIXEL)                # los diez que van al addendum de M1
HUELLAS_PIXEL_1DA0236: Mapping[str, str] = MappingProxyType({
    "extraccion": "dc6a8788d690081cdb201b9c3113053045a6d448a6c7c16dfc53f1db0eb06cbc",
    "numerico": "c463336c1fd1ef6bfc116ace8b1e652d1a23fc11f03665f4c53b159632c3f45b",
    "umbrales": "075834dc9a2c1ccbd030dfad5bb08339ab61fd45c89896ec9e04fab091e0af4d",
})
HUELLAS_CLAUSURA_1DA0236: Mapping[str, str] = MappingProxyType({**HUELLAS_RELOJ_1DA0236, **HUELLAS_PIXEL_1DA0236})
HUELLAS_CLAUSURA: Mapping[str, str] = HUELLAS_CLAUSURA_1DA0236    # la vigente (FIJ-11)
# Lo que carga extraccion y no puede estar cargado antes de cargar_elegir_pixel (salvo por este módulo; FIJ-2, FIJ-11), y
# lo que arrastra en total (los de la clausura de MC-17 salvo politica, más MODULOS_PIXEL).
CARGADOS_DESPUES_PIXEL = ("tipos", "constantes", "tablas", "numerico", "umbrales", "extraccion")
ARCHIVOS_PIXEL = ("__init__", "entorno", "fijados", *CARGADOS_DESPUES_PIXEL)
NOMBRE_EXTRACCION = "reloj_dmc.extraccion"
UMBRAL_PIXEL_RELOJ = "PIXEL_RADIO_KM"     # el único umbral del reloj que usa elegir_pixel (RELOJ §3.3, Anexo B)
MODULOS_PROHIBIDOS = _rf.MODULOS_PROHIBIDOS
# Código fijado que nunca se carga (sólo su huella): §1 del diseño.
NUNCA_CARGADOS = ("preflight_v3", "runner_v3")

ABREVIATURA = 8  # no-umbral: caracteres de una huella abreviada en los mensajes
_SHA = re.compile(r"[0-9a-f]{64}")


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def _leer(ruta: Path, sha256: str | None) -> bytes:
    """Bytes de un archivo fijado: regular, no enlace y, si se da, con esa sha256."""
    ruta = Path(ruta)
    if ruta.is_symlink():
        raise ValueError(f"El archivo fijado es un enlace simbólico: {ruta.name}")
    if not ruta.is_file():
        raise FileNotFoundError(f"No existe el archivo fijado: {ruta.name}")
    datos = ruta.read_bytes()
    if sha256 is not None and entorno.sha256_bytes(datos) != sha256:
        raise ValueError(f"La huella de {ruta.name} no coincide con la fijada ({sha256[:ABREVIATURA]}…)")
    return datos


def _exigir_sin_prohibidos(momento: str) -> None:
    presentes = [m for m in (*MODULOS_PROHIBIDOS, *NUNCA_CARGADOS) if m in sys.modules]
    if presentes:
        raise RuntimeError(f"{', '.join(presentes)} en sys.modules {momento} (nunca se cargan)")


def _exigir_sha(sha256: str) -> None:
    if not isinstance(sha256, str) or not _SHA.fullmatch(sha256):
        raise ValueError("Se exige un sha256 de 64 hexadecimales en minúscula")


# ---------------------------------------------------------------------------
# Código fijado por ruta y huella
# ---------------------------------------------------------------------------
def cargar_adaptador(ap) -> ModuleType:
    """``AP/scripts_modelo_1km/v2/meteorologia_v2.py`` (f61559ea…), por ``reloj_dmc.fijados.cargar_por_ruta``."""
    modulo = _rf.cargar_adaptador(Path(ap), SHA_ADAPTADOR)
    _exigir_sin_prohibidos("después de cargar el adaptador")
    return modulo


def cargar_dmc_features(ap) -> ModuleType:
    """``AP/scripts_modelo_1km/v3/dmc_features.py`` (15762856…); su ``_adapter`` vuelve a verificar el adaptador."""
    modulo = _rf.cargar_dmc_features(Path(ap), SHA_DMC_FEATURES)
    _exigir_sin_prohibidos("después de cargar dmc_features")
    return modulo


def cargar_descargador(ap) -> ModuleType:
    """El descargador vigente (578fa26e…), sólo para fabricar datos sintéticos con el formato real (S2, S12, S15)."""
    modulo = _rf.cargar_descargador(Path(ap), SHA_DESCARGADOR)
    _exigir_sin_prohibidos("después de cargar el descargador")
    return modulo


# ---------------------------------------------------------------------------
# Clausura del reloj (MC-17)
# ---------------------------------------------------------------------------
def _huellas_de(ap, archivos: Iterable[str]) -> dict[str, str]:
    carpeta = Path(ap) / RUTA_RELOJ
    return {m: entorno.sha256_bytes(_leer(carpeta / f"{m}.py", None)) for m in archivos}


def huellas_reloj(ap) -> dict[str, str]:
    """sha256 de los siete archivos de ``ARCHIVOS_RELOJ`` (``AP/scripts_modelo_1km/reloj_dmc/<m>.py``; FIJ-8)."""
    return _huellas_de(ap, ARCHIVOS_RELOJ)


def huellas_clausura(ap) -> dict[str, str]:
    """sha256 de los diez archivos de ``ARCHIVOS_CLAUSURA``: los de FIJ-8 más ``MODULOS_PIXEL`` (FIJ-11)."""
    return _huellas_de(ap, ARCHIVOS_CLAUSURA)


def _diferencias_reloj(esperadas: Mapping[str, str], actuales: Mapping[str, str],
                       archivos: Iterable[str] = ARCHIVOS_RELOJ) -> list[str]:
    return [f"{m}: {actuales.get(m, '—')[:ABREVIATURA]} ≠ {esperadas[m][:ABREVIATURA]}"
            for m in archivos if actuales.get(m) != esperadas[m]]


def _exigir_modulos_reloj(carpeta: Path, archivos: Iterable[str] = ARCHIVOS_RELOJ) -> None:
    for m in archivos:
        nombre = "reloj_dmc" if m == "__init__" else f"reloj_dmc.{m}"
        modulo = sys.modules.get(nombre)
        if modulo is None:
            continue
        archivo = Path(getattr(modulo, "__file__", "") or "").resolve()
        if archivo != (carpeta / f"{m}.py").resolve():
            raise RuntimeError(f"{nombre} está cargado desde otra carpeta que la del reloj de este AP")


def _exigir_huellas(huellas_esperadas: Mapping[str, str], archivos: tuple[str, ...], que: str) -> dict[str, str]:
    if set(huellas_esperadas) != set(archivos):
        raise ValueError(f"las huellas {que} deben ser exactamente las de {archivos}")
    for sha in huellas_esperadas.values():
        _exigir_sha(sha)
    return dict(huellas_esperadas)


# Módulos del reloj que cargó este módulo (cargar_validador_reloj o cargar_elegir_pixel), con las huellas comprobadas
# antes y después de cargarlos: nombre en sys.modules → (módulo, sha256). Ver FIJ-2 y FIJ-11.
_PROPIOS: dict[str, tuple[ModuleType, str]] = {}


def _ajenos(modulos: Iterable[str], huellas: Mapping[str, str]) -> list[str]:
    """Los de ``modulos`` (del reloj) que están en sys.modules y no los cargó este módulo con esas huellas."""
    ajenos = []
    for m in modulos:
        cargado = sys.modules.get(f"reloj_dmc.{m}")
        if cargado is None:
            continue
        propio = _PROPIOS.get(f"reloj_dmc.{m}")
        if propio is None or propio[0] is not cargado or propio[1] != huellas[m]:
            ajenos.append(m)
    return ajenos


def _anotar_propios(modulos: Iterable[str], huellas: Mapping[str, str], ajenos_al_empezar: Iterable[str]) -> None:
    """Anota como propios los de ``modulos`` que cargó esta llamada o que ya eran propios; nunca los que otro camino
    había cargado al empezar (aceptados sólo con ``permitir_cargados``; H2)."""
    excluidos = set(ajenos_al_empezar)
    for m in modulos:
        if m not in excluidos:
            _PROPIOS[f"reloj_dmc.{m}"] = (sys.modules[f"reloj_dmc.{m}"], huellas[m])


def _rechazar_ajenos(ajenos: list[str]) -> None:
    raise RuntimeError(f"reloj_dmc.{', reloj_dmc.'.join(ajenos)} ya estaba cargado: la comprobación de las huellas no "
                       "sería previa a la importación (FIJ-2, FIJ-11)")


def _exigir_sin_cache(carpeta: Path, archivos: Iterable[str], momento: str) -> None:
    """Ningún bytecode guardado del reloj (FIJ-11, H3): ni ``reloj_dmc/__pycache__`` ni el ``.pyc`` de ninguno de
    ``archivos`` (el de ``importlib.util.cache_from_source`` y el ``__spec__.cached`` del módulo, si está cargado).
    ``-B`` sólo evita escribirlos; uno presente se ejecutaría en lugar de los bytes con huella."""
    hallados = ["__pycache__"] if (carpeta / "__pycache__").exists() else []
    for m in archivos:
        cargado = sys.modules.get("reloj_dmc" if m == "__init__" else f"reloj_dmc.{m}")
        candidatos = {importlib.util.cache_from_source(str(carpeta / f"{m}.py")),
                      getattr(getattr(cargado, "__spec__", None), "cached", None)}
        if any(c and Path(c).exists() for c in candidatos):
            hallados.append(f"{m}.pyc")
    if hallados:
        raise RuntimeError(f"el reloj tiene bytecode guardado {momento} ({', '.join(hallados)}): se ejecutaría en lugar "
                           "de los bytes con huella (FIJ-11, H3)")


# El validador que cargó esta función: (huellas comprobadas, módulo politica, función). Ver FIJ-2.
_VALIDADOR: list = []


def cargar_validador_reloj(ap, huellas_esperadas: dict[str, str], *, permitir_cargados: bool = False) -> Callable:
    """``reloj_dmc.politica.validar_regla_reloj_dmc``, con las huellas comprobadas antes y después de importar.

    Exige exactamente las claves de ``ARCHIVOS_RELOJ`` con sha256 válidos y que los módulos del reloj cargados sean
    los de ``AP/scripts_modelo_1km/reloj_dmc`` (FIJ-2, FIJ-8). Falla si ``politica``, ``tipos``, ``constantes`` o
    ``tablas`` del reloj ya estaban cargados antes de llamarla, salvo que los haya cargado este módulo con las mismas
    huellas (ella misma, y entonces las vuelve a comprobar y devuelve el mismo validador, o ``cargar_elegir_pixel``:
    FIJ-11) o ``permitir_cargados``, que es sólo para pruebas (lo que acepta no queda anotado como propio: H2). Exige
    que el reloj no tenga bytecode guardado, antes y después (H3). Devuelve el mismo objeto del módulo, no un envoltorio.
    """
    huellas_esperadas = _exigir_huellas(huellas_esperadas, ARCHIVOS_RELOJ, "del reloj")
    carpeta = Path(ap) / RUTA_RELOJ
    diferencias = _diferencias_reloj(huellas_esperadas, huellas_reloj(ap))
    if diferencias:
        raise ValueError("La clausura del reloj no tiene las huellas esperadas (antes de importar): "
                         + "; ".join(diferencias))
    _exigir_sin_cache(carpeta, ARCHIVOS_RELOJ, "antes de importar")
    _exigir_modulos_reloj(carpeta)
    _exigir_sin_prohibidos("antes de cargar el validador del reloj")
    ajenos = _ajenos(CARGADOS_DESPUES, huellas_esperadas)
    if ajenos and not permitir_cargados:
        _rechazar_ajenos(ajenos)
    if (_VALIDADOR and _VALIDADOR[0][0] == huellas_esperadas
            and sys.modules.get("reloj_dmc.politica") is _VALIDADOR[0][1]):
        return _VALIDADOR[0][2]
    politica = importlib.import_module("reloj_dmc.politica")
    _exigir_modulos_reloj(carpeta)
    diferencias = _diferencias_reloj(huellas_esperadas, huellas_reloj(ap))
    if diferencias:
        raise ValueError("La clausura del reloj cambió mientras se importaba: " + "; ".join(diferencias))
    _exigir_sin_cache(carpeta, ARCHIVOS_RELOJ, "después de importar")
    _exigir_sin_prohibidos("después de cargar el validador del reloj")
    validar = getattr(politica, "validar_regla_reloj_dmc", None)
    if not callable(validar) or getattr(validar, "__module__", None) != "reloj_dmc.politica":
        raise RuntimeError("reloj_dmc.politica no trae validar_regla_reloj_dmc")
    _VALIDADOR[:] = [(huellas_esperadas, politica, validar)]
    _anotar_propios(CARGADOS_DESPUES, huellas_esperadas, ajenos)
    return validar


# ---------------------------------------------------------------------------
# El píxel del reloj (MC-52, A27; FIJ-11)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, eq=False)
class PixelReloj:
    """``reloj_dmc.extraccion.elegir_pixel`` con lo necesario para llamarlo con la regla del reloj (FIJ-11)."""
    elegir_pixel: Callable          # el mismo objeto de reloj_dmc.extraccion
    EleccionPixel: type             # reloj_dmc.extraccion.EleccionPixel(pixel_id, distancia_km, costera)
    umbrales: Any                   # reloj_dmc.umbrales.Umbrales anclado en C0 (cargar_c0)
    radio_km: int | float           # umbrales.f("PIXEL_RADIO_KM"): 15 km
    huellas: Mapping[str, str]      # la clausura ampliada comprobada (ARCHIVOS_CLAUSURA)
    coordenadas_en_rango: Callable  # reloj_dmc.tablas.coordenadas_en_rango (RELOJ §3.3)

    def elegir(self, lat: float, lon: float, catalogo_pixeles, validos: set[int]):
        """RELOJ §3.3: la celda propia válida; si no, el centro válido más cercano a ≤ ``radio_km`` (empate: menor
        ``pixel_id``); si no hay, ``EleccionPixel(None, None, False)``. Es ``elegir_pixel(…, umbrales)``."""
        return self.elegir_pixel(lat, lon, catalogo_pixeles, validos, self.umbrales)

    def enlazar(self, lat: float | None, lon: float | None, catalogo_pixeles, validos: set[int]):
        """La regla de ``extraccion.enlazar_pixeles`` para una estación: sin coordenadas finitas dentro del rango de
        RELOJ §3.3, ``EleccionPixel(None, None, False)``; si no, ``elegir``. Es la que usa M5 (FIJ-11)."""
        if not self.coordenadas_en_rango(lat, lon):
            return self.EleccionPixel(None, None, False)
        return self.elegir(lat, lon, catalogo_pixeles, validos)


# El píxel que cargó cargar_elegir_pixel: (huellas comprobadas, módulo extraccion, PixelReloj). Ver FIJ-11.
_PIXEL: list = []


def _umbrales_c0_anclados(aph) -> None:
    """Lee el texto y el JSON de umbrales del reloj en C0 con las huellas que fija M1 (FIJ-11)."""
    _leer(Path(aph) / RUTA_RELOJ_C0, SHA_RELOJ_C0)
    _leer(Path(aph) / RUTA_JSON_RELOJ_C0, SHA_JSON_RELOJ_C0)


def cargar_elegir_pixel(ap, aph, huellas_esperadas: Mapping[str, str], *,
                        permitir_cargados: bool = False) -> PixelReloj:
    """``reloj_dmc.extraccion.elegir_pixel`` con la regla del reloj, sus umbrales anclados en C0 (FIJ-11; MC-52, A27).

    Exige exactamente las claves de ``ARCHIVOS_CLAUSURA`` con sha256 válidos, las comprueba antes y después de cargar
    y exige que los módulos del reloj cargados sean los de ``AP/scripts_modelo_1km/reloj_dmc``. ``extraccion.py`` se
    carga por ruta y huella (``reloj_dmc.fijados.cargar_por_ruta``); lo que importa, por la importación normal. Falla si
    alguno de ``CARGADOS_DESPUES_PIXEL`` ya estaba cargado y no lo cargó este módulo con las mismas huellas, salvo
    ``permitir_cargados``, que es sólo para pruebas (lo que acepta no queda anotado como propio: H2). Exige que el reloj
    no tenga bytecode guardado, antes y después (H3). Los umbrales son los de ``reloj_dmc.umbrales.cargar_c0`` (texto y
    JSON de C0, APH ``d02f918``), que antes se leen con las huellas de M1. Sólo abre código del reloj y esos dos
    archivos: ninguna salida del reloj ni datos DMC. Una segunda llamada con las mismas huellas devuelve el mismo objeto.
    """
    huellas = _exigir_huellas(huellas_esperadas, ARCHIVOS_CLAUSURA, "de la clausura ampliada del reloj")
    carpeta = Path(ap) / RUTA_RELOJ
    diferencias = _diferencias_reloj(huellas, huellas_clausura(ap), ARCHIVOS_CLAUSURA)
    if diferencias:
        raise ValueError("La clausura ampliada del reloj no tiene las huellas esperadas (antes de cargar): "
                         + "; ".join(diferencias))
    _exigir_sin_cache(carpeta, ARCHIVOS_CLAUSURA, "antes de cargar")
    _exigir_modulos_reloj(carpeta, ARCHIVOS_CLAUSURA)
    _exigir_sin_prohibidos("antes de cargar elegir_pixel del reloj")
    _umbrales_c0_anclados(aph)
    ajenos = _ajenos(CARGADOS_DESPUES_PIXEL, huellas)
    if ajenos and not permitir_cargados:
        _rechazar_ajenos(ajenos)
    if _PIXEL and _PIXEL[0][0] == huellas and sys.modules.get(NOMBRE_EXTRACCION) is _PIXEL[0][1]:
        return _PIXEL[0][2]
    extraccion = sys.modules.get(NOMBRE_EXTRACCION)
    if extraccion is None:
        extraccion = _rf.cargar_por_ruta(carpeta / "extraccion.py", huellas["extraccion"], NOMBRE_EXTRACCION)
    _exigir_modulos_reloj(carpeta, ARCHIVOS_CLAUSURA)
    diferencias = _diferencias_reloj(huellas, huellas_clausura(ap), ARCHIVOS_CLAUSURA)
    if diferencias:
        raise ValueError("La clausura ampliada del reloj cambió mientras se cargaba: " + "; ".join(diferencias))
    _exigir_sin_cache(carpeta, ARCHIVOS_CLAUSURA, "después de cargar")
    _exigir_sin_prohibidos("después de cargar elegir_pixel del reloj")
    elegir = getattr(extraccion, "elegir_pixel", None)
    eleccion = getattr(extraccion, "EleccionPixel", None)
    if (not callable(elegir) or getattr(elegir, "__module__", None) != NOMBRE_EXTRACCION
            or not isinstance(eleccion, type) or eleccion.__module__ != NOMBRE_EXTRACCION):
        raise RuntimeError("reloj_dmc.extraccion no trae elegir_pixel ni EleccionPixel")
    mod_umbrales = sys.modules.get("reloj_dmc.umbrales")
    if mod_umbrales is None or getattr(extraccion, "Umbrales", None) is not getattr(mod_umbrales, "Umbrales", None):
        raise RuntimeError("reloj_dmc.extraccion no usa los Umbrales de reloj_dmc.umbrales")
    en_rango = getattr(sys.modules.get("reloj_dmc.tablas"), "coordenadas_en_rango", None)
    if not callable(en_rango) or getattr(en_rango, "__module__", None) != "reloj_dmc.tablas" \
            or getattr(extraccion, "tablas", None) is not sys.modules.get("reloj_dmc.tablas"):
        raise RuntimeError("reloj_dmc.extraccion no usa coordenadas_en_rango de reloj_dmc.tablas")
    anclados = tuple(getattr(mod_umbrales, n, None) for n in ("PROTOCOLO_C0", "SHA_PROTOCOLO_C0", "JSON_C0",
                                                               "SHA_JSON_C0"))
    if anclados != (RUTA_RELOJ_C0, SHA_RELOJ_C0, RUTA_JSON_RELOJ_C0, SHA_JSON_RELOJ_C0):
        raise RuntimeError("reloj_dmc.umbrales ancla en C0 otros archivos u otras huellas que las de M1 (FIJ-11)")
    umbrales_reloj = mod_umbrales.cargar_c0(Path(aph))
    if umbrales_reloj.sha256_json != SHA_JSON_RELOJ_C0:
        raise RuntimeError("los umbrales del reloj no son los del JSON de C0")
    _exigir_sin_prohibidos("después de cargar los umbrales del reloj")
    pixel = PixelReloj(elegir, eleccion, umbrales_reloj, umbrales_reloj.f(UMBRAL_PIXEL_RELOJ),
                       MappingProxyType(dict(huellas)), en_rango)
    _PIXEL[:] = [(huellas, extraccion, pixel)]
    _anotar_propios(CARGADOS_DESPUES_PIXEL, huellas, ajenos)
    return pixel


# ---------------------------------------------------------------------------
# Extracciones por AST (sin importar los módulos)
# ---------------------------------------------------------------------------
def macrozona_region(ap) -> dict[int, str]:
    """``MACROZONA_REGION`` de ``_comun_modelo.py`` (a83c0384…), por AST: nunca se importa."""
    if _rf.SHA_COMUN_MODELO != SHA_COMUN_MODELO:
        raise RuntimeError("reloj_dmc.fijados fija otra huella de _comun_modelo")
    tabla = _rf.macrozona_region(Path(ap))
    _exigir_sin_prohibidos("después de leer MACROZONA_REGION")
    return tabla


def macrozona_codigo(ap) -> dict[str, int]:
    """``MACROZONA_CODIGO`` de ``_comun_modelo.py`` (a83c0384…), por AST: la codificación de ``macrozona_cod`` de
    ``celdas.parquet`` (FIJ-9)."""
    valor = _rf.extraer_por_ast(Path(ap) / RUTA_COMUN_MODELO, SHA_COMUN_MODELO, ("MACROZONA_CODIGO",),
                                {})["MACROZONA_CODIGO"]
    if (not isinstance(valor, dict) or not valor
            or not all(isinstance(k, str) and k and type(v) is int for k, v in valor.items())
            or len(set(valor.values())) != len(valor)):
        raise RuntimeError("MACROZONA_CODIGO no es un diccionario {macrozona: código} sin códigos repetidos")
    _exigir_sin_prohibidos("después de leer MACROZONA_CODIGO")
    return dict(valor)


def extraer_meteo_civil_v3(aph, nombres: Iterable[str]) -> dict[str, Any]:
    """Nodos de nivel superior de ``v3_next/meteo_civil_v3.py`` (483f63a6…), por AST, con numpy, pandas y los tipos de
    ``typing`` que usan sus anotaciones. Para S8 y S14 (``humedad_relativa``, ``lluvia_horaria``…)."""
    import numpy as np
    import pandas as pd
    espacio = {"np": np, "pd": pd, "Mapping": Mapping, "Iterable": Iterable}
    return _rf.extraer_por_ast(Path(aph) / RUTA_METEO_CIVIL_V3, SHA_METEO_CIVIL_V3, tuple(nombres), espacio)


def esquema_meteo_civil_v3(aph) -> dict:
    """VARIABLES, ESQUEMA_DIARIO, MAGNUS_A/B y los tipos de ``tabla_meteo``, por AST (FIJ-6)."""
    import numpy as np
    ns = extraer_meteo_civil_v3(aph, ("VARIABLES", "ESQUEMA_DIARIO", "MAGNUS_A", "MAGNUS_B", "tabla_meteo"))
    variables = tuple(ns["VARIABLES"])
    una = np.ones((1, 1))
    tabla = ns["tabla_meteo"](np.array([1]), np.array([0]), {v: np.zeros((1, 1)) for v in variables}, una, una)
    return {"archivo": f"APH/{RUTA_METEO_CIVIL_V3}", "sha256": SHA_METEO_CIVIL_V3, "version": ns["ESQUEMA_DIARIO"],
            "variables": variables, "magnus": (ns["MAGNUS_A"], ns["MAGNUS_B"]),
            "columnas": {c: str(tabla[c].dtype) for c in tabla.columns}}


def _constante(nodo: ast.expr) -> float:
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, (int, float)) and not isinstance(nodo.value, bool):
        return nodo.value
    raise ValueError("la regla el_* de _features.py no tiene la forma esperada (se esperaba un número)")


def _columna(nodo: ast.expr) -> str:
    """``df["el_x"]`` → «el_x»."""
    if isinstance(nodo, ast.Subscript) and isinstance(nodo.slice, ast.Constant) and isinstance(nodo.slice.value, str):
        return nodo.slice.value
    raise ValueError("la regla el_* de _features.py no tiene la forma esperada (se esperaba df[\"…\"])")


def _es_binop(nodo, op) -> bool:
    return isinstance(nodo, ast.BinOp) and isinstance(nodo.op, op)


def _magnus(nodo: ast.expr) -> tuple[str, tuple[float, float, float]]:
    """``a * np.exp(b * x / (x + c))`` → (x, (a, b, c)); ValueError con otra forma."""
    llamada = nodo.right if _es_binop(nodo, ast.Mult) else None
    cociente = (llamada.args[0] if isinstance(llamada, ast.Call) and isinstance(llamada.func, ast.Attribute)
                and llamada.func.attr == "exp" and len(llamada.args) == 1 else None)
    if not _es_binop(cociente, ast.Div):
        raise ValueError("la regla el_* de _features.py no tiene la forma esperada (Magnus)")
    num, den = cociente.left, cociente.right
    if not (_es_binop(num, ast.Mult) and isinstance(num.right, ast.Name) and _es_binop(den, ast.Add)
            and isinstance(den.left, ast.Name) and num.right.id == den.left.id):
        raise ValueError("la regla el_* de _features.py no tiene la forma esperada (Magnus)")
    return num.right.id, (_constante(nodo.left), _constante(num.left), _constante(den.right))


def regla_el_features(ap) -> dict:
    """Nombres ``el_*``, Magnus 17,67/243,5, la conversión de K y ``arctan2(u, v)`` de ``_features.py`` (FIJ-7)."""
    ruta = Path(ap) / RUTA_FEATURES
    fuente = _leer(ruta, SHA_FEATURES).decode("utf-8")
    directas = dict(_rf.extraer_por_ast(ruta, SHA_FEATURES, ("FEATURES_HORARIAS",), {})["FEATURES_HORARIAS"]["era5land"])
    (funcion,) = [n for n in ast.parse(fuente).body if isinstance(n, ast.FunctionDef) and n.name == "derivadas_horarias"]
    derivadas, magnus, kelvin, direccion = [], {}, set(), None
    for nodo in ast.walk(funcion):
        if isinstance(nodo, ast.Assign):
            for objetivo in nodo.targets:
                if isinstance(objetivo, ast.Subscript) and isinstance(objetivo.slice, ast.Constant):
                    nombre = objetivo.slice.value
                    if isinstance(nombre, str) and nombre.startswith("el_") and nombre not in derivadas:
                        derivadas.append(nombre)
                elif isinstance(objetivo, ast.Name) and objetivo.id in ("es", "e"):
                    magnus[objetivo.id] = _magnus(nodo.value)
                elif isinstance(objetivo, ast.Tuple) and isinstance(nodo.value, ast.Tuple):
                    for valor in nodo.value.elts:
                        if (_es_binop(valor, ast.Sub) and isinstance(valor.left, ast.Subscript)
                                and _columna(valor.left) in ("el_t2m", "el_d2m")):
                            kelvin.add(_constante(valor.right))
        elif (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute) and nodo.func.attr == "arctan2"):
            direccion = tuple(_columna(a) for a in nodo.args)
    if set(magnus) != {"es", "e"} or magnus["es"][1] != magnus["e"][1] or len(kelvin) != 1 or direccion is None:
        raise ValueError("la regla el_* de _features.py no tiene la forma esperada")
    lluvia = [c for v, c in directas.items() if v.startswith("tp")]
    meteorologicas = [c for v, c in directas.items() if not v.startswith("tp")] + derivadas
    return {"archivo": f"AP/{RUTA_FEATURES}", "sha256": SHA_FEATURES, "directas": directas, "derivadas": derivadas,
            "lluvia": lluvia, "meteorologicas": meteorologicas, "magnus": magnus["es"][1], "kelvin": kelvin.pop(),
            "direccion": direccion}


def opciones_m0(aph) -> dict:
    """``OPCIONES_M0`` de ``m0/preparar_m0.py`` (AST, sha 49503a3a…; MC-35)."""
    valor = _rf.extraer_por_ast(Path(aph) / RUTA_PREPARAR_M0, SHA_PREPARAR_M0, ("OPCIONES_M0",), {})["OPCIONES_M0"]
    if not isinstance(valor, dict) or not all(isinstance(k, str) for k in valor):
        raise RuntimeError("OPCIONES_M0 no es un diccionario de opciones")
    return dict(valor)


# ---------------------------------------------------------------------------
# Comprobación de huellas (§9.3, §9.4)
# ---------------------------------------------------------------------------
def huella_micromamba(texto: str) -> str:
    """Huella del intérprete: sha256 del texto de ``micromamba list -n amb_v2`` en UTF-8 (FIJ-3)."""
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def comprobar_codigo_fijado(ap, aph, *, micromamba_list: str | None = None) -> list[str]:
    """Diferencias entre las huellas fijadas del código, los textos y la configuración, y las calculadas; lista vacía
    si coinciden. Con ``micromamba_list``, también la del intérprete. Los mensajes van por alias (AP/…, APH/…)."""
    raices = {"AP": Path(ap), "APH": Path(aph)}
    diferencias = []
    for repo, ruta, sha, origen in HUELLAS_CODIGO:
        p = raices[repo] / ruta
        try:
            actual = entorno.sha256_bytes(_leer(p, None))
        except (FileNotFoundError, ValueError) as e:
            diferencias.append(f"{repo}/{ruta} ({origen}): {e}")
            continue
        if actual != sha:
            diferencias.append(f"{repo}/{ruta} ({origen}): sha256 {actual[:ABREVIATURA]}… ≠ fijado "
                               f"{sha[:ABREVIATURA]}…")
    if micromamba_list is not None and huella_micromamba(micromamba_list) != SHA_MICROMAMBA_LIST:
        diferencias.append(f"intérprete: micromamba list {huella_micromamba(micromamba_list)[:ABREVIATURA]}… ≠ fijado "
                           f"{SHA_MICROMAMBA_LIST[:ABREVIATURA]}…")
    return diferencias
