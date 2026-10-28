"""Estáticos desde NASADEM y GHS-POP: K1, K3, celdas, altitud poblada, TPI y pendiente (§2.5, §3, §4.6).

Es el único módulo que lee las teselas NASADEM (acuerdo A9 de ``COORDINACION_M1.md``) y las de GHS-POP. Lo demás es
puro: recibe tablas, teselas ya leídas y ``Umbrales``, y devuelve tablas o ``InfoEstacion``. No escribe nada (§0, regla
8 del diseño). Toda la aritmética de la red NASADEM es entera: cada punto es un par de índices (I, J) con
lat = I/3.600 y lon = J/3.600, y las sumas de altitudes van en int64 (exactas).

Funciones (§3 del diseño, y las nuevas de los acuerdos A8 y A9):
- ``interpretar_coordenada``, ``coordenadas_en_rango`` y ``rho_km`` (K1): los textos del catálogo, como RELOJ §3.3.
- ``leer_tesela`` (``TeselaDEM``) y ``leer_ghs`` (``TeselaGHS``): las teselas, con su sha256.
- ``celda_de_puntos``: la celda de 0,01° de cada punto, con los bordes oeste y sur cerrados.
- ``k3``: plausibilidad de las coordenadas con NASADEM, y z_s; ``hay_tesela_a_rho`` y ``ventana_k3`` (D37).
- ``estaticos_celdas`` (``ESQUEMA_ESTATICAS_CELDA``), ``ventana_necesaria``, ``estandarizar_tpi`` y
  ``tpi_entra_a_estandarizar`` (D33).
- ``info_estaciones`` (``InfoEstacion``, acuerdo A8), ``tabla_estaciones`` (``ESQUEMA_ESTACIONES_MC``),
  ``fuera_de_la_grilla`` (D34) y ``declaraciones_estaciones`` (D9, D16, D34, D37).
- ``nasadem_en_pixeles``: la media NASADEM de la huella de cada píxel ERA5-Land (acuerdo A9, para ``fondo_era5l``).

Dueño: I8 (ola 2, y su corrección con D30-D38 [delegadas]: P19-P27 de ``COORDINACION_M1.md``).
Lecturas propias (NAS-n), para el addendum de M1:
- NAS-1. **Lectura de los textos del catálogo** (§2.5: «se leen como en RELOJ §3.3»). ``interpretar_coordenada`` es
  copia de ``reloj_dmc.tablas.interpretar_coordenada`` (decimal con punto o coma; sexagesimal con signo o letra S/W;
  la altitud sólo decimal; nunca invierte un signo), y ``coordenadas_en_rango`` copia el rango de RELOJ §3.3
  (−90 ≤ lat ≤ −17 y −110 ≤ lon ≤ −55). Este módulo no puede importar el reloj (sólo ``entorno`` y ``fijados`` lo
  importan, §1 del diseño): la prueba compara la copia con el original por AST, con la huella de ``tablas.py`` de la
  clausura fijada (FIJ-1 de ``fijados``: AP ``1da0236``; ``tablas.py`` es el mismo que en ``4b50b0d``). Una estación con coordenadas fuera de ese rango queda como una sin coordenadas legibles: sin
  coordenadas confirmadas y fuera (motivo «coordenadas_fuera_de_rango»), porque la lectura de RELOJ §3.3 incluye el
  rango.
- NAS-2. **K1** (§2.5, MC-59). El medio paso de cada texto: con un decimal (también los grados de un sexagesimal sin
  minutos) son 0,5·10⁻ᵈ grados con d los decimales escritos (los ceros finales cuentan); con segundos, 0,5″ aunque
  los segundos traigan decimales; con minutos y sin segundos, 0,5′ aunque los minutos traigan decimales. Es la
  lectura literal («con segundos, 0,5″; sólo minutos, 0,5′») y da el ρ más grande, el lado conservador de MC-59; la
  fijó D38 [delegada] (P27). Rige el más grueso de latitud y longitud; 1° = π·6.371/180 km sin cos φ; × √2; ρ = mín(máx(ρ; RHO_MIN_KM);
  RHO_MAX_KM). Sin un texto legible, ρ es NaN.
- NAS-3. **La red NASADEM** (§3, SIN-9). Las teselas son GeoTIFF int16 EPSG:4326 de 1/3.600° con los centros en
  múltiplos exactos de 1/3.600° (píxel-punto del HGT), ``nodata`` −32768 y máscara interna; un punto tiene dato si la
  máscara lo marca y su valor no es ``nodata``. ``leer_tesela`` lee los bytes con ``open`` de Python (los ve el gancho
  de auditoría de ``ceguera``), exige su sha256 y abre esos mismos bytes en memoria: lo que se comprueba es lo que se
  usa. Exige una banda, int16, EPSG:4326, sin rotación, norte arriba, paso 1/3.600°, centros en la red y las
  etiquetas ``producto`` = NASADEM_HGT y ``vertical_units`` = meters del descargador.
- NAS-4. **Varias teselas.** Se usan como una sola red: un punto de la red tiene dato si alguna tesela lo tiene, y si
  dos teselas lo tienen deben valer lo mismo (las teselas HGT comparten su fila y su columna de borde); si no, es un
  error. Un punto sin tesela no tiene dato.
- NAS-5. **Celdas** (§3: «un píxel pertenece a la celda que contiene su centro, con los bordes oeste y sur cerrados»).
  Las celdas de ``celdas.parquet`` son las de 0,01° de ACAG, con centro en k/100 + 0,005° (lo dice
  ``construir_grilla``; se exige a cada celda, con 10⁻⁶ de holgura numérica). La celda (k, m) cubre
  I ∈ [36k, 36k + 35] y J ∈ [36m, 36m + 35]: 1.296 puntos, y un punto sobre el borde sur u oeste es de esa celda.
  ``celda_de_puntos`` da los índices (⌊lat·100⌋, ⌊lon·100⌋) con esa regla, después de llevar al punto de la red un
  valor que está a ≤ 10⁻⁶ pasos de él (≈ 0,03 mm; así −33,45 leído en binario cae en su borde). No es el id de
  ``celdas.parquet``: la celda de un punto se busca en la tabla por esos índices, calculados también desde el centro de
  cada celda (acuerdo A8: «nunca se deduce de un id»).
- NAS-6. **z_media y frac_dato** (§3, «uso ambiental: z = media NASADEM de la celda»): la media de los puntos de la
  celda con dato y la fracción de los 1.296 con dato. Sin ningún dato, z_media, z_poblada, la pendiente y el TPI son
  NaN: no se rellenan desde la vecina (v1 lo hacía; el texto no lo dice). ``attrs["declaraciones"]`` las cuenta.
- NAS-7. **Pendiente** (§3 y §4.6: «media de las pendientes de 30 m de la celda, en grados»; «se calcula en metros,
  con el factor cos φ»). En cada punto, diferencias centradas con sus cuatro vecinos de la red:
  dz/dy = (z_N − z_S)/(2Δy) y dz/dx = (z_E − z_O)/(2Δx), con Δy = 6.371.000 m · (π/180)/3.600 y Δx = Δy · cos φ de la
  fila del punto, y pendiente = arctan(√((dz/dx)² + (dz/dy)²)) en grados. Un punto sin dato, o con un vecino sin dato,
  no tiene pendiente (nunca diferencias de un lado). La de la celda es la media de las pendientes definidas de sus
  puntos. Es el esquema de ``np.gradient`` que usaba v1, con el cos φ de cada fila en vez del de la tesela y el R de
  MC-59.
- NAS-8. **Altitud poblada** (§3, «media NASADEM ponderada por la población GHS-POP R2023A de 100 m de 2020»). Cada
  punto NASADEM con dato de la celda pesa la población del píxel GHS de 100 m que contiene su centro (Mollweide,
  ``numerico.mollweide``; píxel ⌊(x − x₀)/100⌋, ⌊(y₀ − y)/100⌋). Como los píxeles GHS tienen igual área, el peso es la
  densidad de población en el punto. Un valor GHS ≤ 0, no finito o ``nodata`` pesa 0, como en ``pesos_poblacion.py``.
  Si la suma de pesos de la celda es 0 («una celda sin población»), z_poblada = z_media y ``z_poblada_es_media``. Con
  ``ghs=None`` («si las teselas no se pueden leer en M2a, se usa la media y se declara») todas las celdas usan la media
  y ``attrs["declaraciones"]["ghs_legible"]`` es False. ``ghs`` vacío es un error (ValueError): sin ninguna tesela
  legible se pasa None, para que la declaración no dependa de que quien llama elija entre None y []. Las celdas sin
  ningún punto dentro de una tesela GHS se cuentan aparte (``celdas_fuera_de_ghs``); así queda también una celda que
  sólo cubría una tesela que no se pudo leer. ``teselas_ghs`` y ``huellas_ghs`` declaran cuántos archivos GHS distintos
  llegaron (por su sha256) y cuáles, para que M2a los compare con las 8 de ``huellas_m0.json`` (pedido a I20). Que el
  peso sea el del píxel que contiene el punto lo fijó D32 [delegada] (P21, antes NAS-P3).
- NAS-9. **TPI** (§4.6: «TPI a 1 y a 5 km (media NASADEM de la celda menos la del disco), con la parte con dato; si
  el disco tiene < 50 % con dato, TPI = 0 tras estandarizar y marca ``tpi_truncado``»). El disco tiene centro en el
  centro de la celda y radio 1 km o 5 km («a 1 y a 5 km» como radio: D30 [delegada], P19, antes NAS-P1), y son suyos
  los puntos de la red a distancia haversine ≤ r (R = 6.371 km, MC-60), tengan tesela o no. TPI = z_media − media de
  los puntos del disco con dato; la fracción con dato es la de esos puntos sobre todos los del disco, y
  ``tpi_truncado`` es fracción < C_TPI_PCT/100. Se guarda el TPI calculado con la parte con dato también cuando queda
  truncado: el 0 rige después de estandarizar y lo aplica ``estandarizar_tpi``, que es la única que debe usar
  ``candidatos``. Sin dato en la celda o en el disco, TPI es NaN (y el disco sin dato queda truncado).
  **Estandarización (D33 [delegada], P22).** Un TPI truncado no entra a la media ni al desvío: entran sólo los TPI
  finitos y no truncados, que es la máscara de ``tpi_entra_a_estandarizar``. La media y el desvío, con sus filas y
  sus pesos de entrenamiento, los calcula ``candidatos`` (I13) con esa máscara; ``estandarizar_tpi`` sólo aplica la
  fórmula y el 0.
- NAS-10. **K3** (§2.5). Pasa si algún punto de la red con dato está a distancia haversine ≤ ρ del punto del catálogo
  y cumple |z_DEM − z_cat| ≤ K3_DZ_M (las dos desigualdades inclusivas). Si pasa, z_s = z_cat. Si no, la estación
  queda sin coordenadas confirmadas y fuera (motivo «k3») y z_s es NaN: §2.5 no le da altitud («si no, la estación
  queda fuera»), así que su QFE queda sin regla. Una tesela a ≤ ρ sin ningún punto con dato a ≤ ρ (la máscara
  administrativa, el mar) sí es una prueba K3, y falla: «Se exige algún punto NASADEM con dato a ≤ ρ». Sin ninguna
  tesela a ≤ ρ no hay prueba (NAS-16).
- NAS-11. **Sin z_cat legible** (§2.5 y MC-11): coordenadas confirmadas (``k3_pasa``), z_s = NASADEM bilineal en el
  punto y ``z_s_fuente`` = «nasadem» (con eso ``politicas`` deja QFE sin regla, acuerdo A7). La bilineal es la de los
  índices de la red, con los cuatro puntos que rodean al punto; cada punto con peso > 0 debe tener dato, y si no,
  z_s es NaN (sin renormalizar). Sin z_s la estación queda fuera con motivo «sin_z_s» y ``k3_pasa`` verdadero
  (D31 [delegada], P20, antes NAS-P2). ``z_s_fuente`` sigue a z_cat (``catalogo`` si es legible, ``nasadem`` si no)
  aunque z_s sea NaN.
- NAS-12. **``info_estaciones``** (acuerdo A8). Llena la identidad, los textos y su lectura, K1, K3, z_s y su fuente,
  la celda, ``utm_e`` y ``utm_n`` (``numerico.utm19s``; NaN sin coordenadas legibles o fuera de rango), ``excluida``
  y ``motivo``.
  Deja ``grupo`` = ``tipos.id_grupo([código])`` y ``bloque`` = «», y el operador del fondo en −1, NaN, False y True
  (lo completan ``orquestacion`` y ``fondo_era5l``). La macrozona es ``tipos.macrozona_de_celda`` de su celda
  (TIP-11, D9, D16); sin celda, None. ``macrozona_region`` (la de ``fijados``) no se usa para deducirla: sólo para
  exigir que las macrozonas de las celdas sean nombres conocidos (más «insular»). ``conjunto`` sale de ``conjuntos``
  (V o V2) y si no, N, como RELOJ. Una estación fuera de la grilla no queda excluida por eso (NAS-17).
  **OMM** (§5.5, «con indicativo OMM»; MC-62). El texto de cada estación se toma sin espacios en los bordes, y un texto
  que queda vacío es un texto que falta. Es un indicativo si tiene alguna cifra 0-9: «s/n», «-» o «» no lo son. Esta
  lectura es más estricta que la del reloj (``lineas_fisicas._indicativo``: cualquier texto no vacío), que sólo sirve
  para cruzar con ISD en E6, inactiva por R-50. ``omm`` es None en todas las estaciones si el catálogo no trae la
  columna o si ninguna estación trae un indicativo: la columna toda nula, toda «» o toda «s/n». Es el caso de
  ``reloj_dmc.extraccion.leer_catalogo_dmc`` sin el campo, que siempre devuelve la columna (está en
  ``COLUMNAS_CATALOGO_DMC``) y conserva los «». Con None el estrato no se forma y se declara (MC-62). Lo fijó D35
  [delegada] (P24, antes NAS-P4). Como depende de todo el catálogo, ``info_estaciones`` se llama una vez con el
  catálogo completo de C2.
  **Motivos de exclusión** (``MOTIVOS``, en su orden de precedencia; una estación lleva uno solo, TIP-14):
  «coordenadas_ilegibles», «coordenadas_fuera_de_rango», «sin_nasadem» (NAS-16), «k3» y «sin_z_s». Los cuatro de la
  ola 2 se toman de ``tipos.MotivoExclusion``; «sin_nasadem» es de D37 y está pedido al coordinador para ``tipos``
  (hasta entonces es un texto de este módulo, y ``test_tipos.PruebasOla2`` lo echa en falta).
  - Equivalencia con POL-5 de ``politicas`` (hoy, antes de K4): «coordenadas_ilegibles» → «sin_coordenadas»;
    «coordenadas_fuera_de_rango» → «k3», porque ``politicas`` ve la latitud legible y ``k3_pasa`` falso; «k3» → «k3»;
    «sin_z_s» → coordenadas confirmadas; «sin_nasadem» → «k3» con z_cat legible y confirmadas sin z_cat (NAS-16).
  - Q2 (§2.7: «las horas del denominador que K3 o K4 dejan sin coordenadas»). «coordenadas_ilegibles»,
    «coordenadas_fuera_de_rango» y «k3» cuentan como «K3 deja sin coordenadas» (``MOTIVOS_SIN_COORDENADAS_K3``, de
    ``tipos``): K3 exige «algún punto NASADEM con dato a ≤ ρ», y sin coordenadas legibles, o fuera del rango de RELOJ
    §3.3, no hay ese punto. Es la lectura más estricta, porque la alarma cuenta más horas, y con ella Q2 no depende de
    qué etiqueta lea I12; la fijó D36 [delegada] (P25, antes NAS-P5). «sin_z_s» no cuenta: sus coordenadas están
    confirmadas. «sin_nasadem» sale del numerador y del denominador (``MOTIVOS_FUERA_DE_Q2``, D37): Q2 se cuenta por el
    motivo, no por ``coordinates.verified`` de la política, que es falso en una «sin_nasadem» con z_cat.
- NAS-13. **``nasadem_en_pixeles``** (acuerdo A9). La huella de un píxel es [``cell_west``, ``cell_east``) ×
  [``cell_south``, ``cell_north``) con los bordes oeste y sur cerrados, como las celdas (§3). z_nasadem es la media de
  sus puntos con dato y frac_nasadem la fracción de sus puntos de la red con dato (NaN y 0 sin ninguno).
- NAS-14. **Otros estáticos** (§4.6): ``log_dist_costa`` = ln(1 + ``dist_costa_km``) de ``estaticas.parquet`` (logaritmo
  natural), las 7 ``lulc_*`` de ``estaticas_lulc.parquet`` del año C_ANIO_LULC, y ``lat``, ``macrozona_cod`` y
  ``cod_comuna`` de ``celdas.parquet`` tal cual. Una celda que falte en cualquiera de las dos tablas detiene el cálculo
  (ValueError): las tres tablas son de la misma grilla fijada.
- NAS-15. **Reproducibilidad.** Las celdas se calculan por lotes de celdas vecinas (memoria acotada, ``ventana_necesaria``
  dice qué teselas pide un conjunto de celdas). El resultado no depende del lote: las sumas de altitudes y conteos son
  enteras, y las sumas en coma flotante (pendiente y pesos GHS) se hacen sobre el bloque de 36 × 36 de cada celda, en
  el mismo orden siempre. La prueba lo compara bit a bit.
- NAS-16. **Sin ninguna tesela NASADEM a ≤ ρ** (D37 [delegada], P26). §2.5: «Se exige algún punto NASADEM con dato a
  ≤ ρ … Si no lo hay, la estación queda sin coordenadas confirmadas»; D37: «Sin ninguna tesela a ≤ ρ no hay prueba
  K3: sale del numerador y del denominador de Q2, se informa aparte y sigue fuera («sin_fondo»)».
  - **Qué es una tesela a ≤ ρ.** Una ``TeselaDEM`` de las que se pasan con algún punto de su red (con dato o sin él:
    su huella, de ``i_sur`` a ``i_norte`` y de ``j_oeste`` a ``j_este``) a distancia haversine ≤ ρ del punto del
    catálogo, inclusiva como K3 (``hay_tesela_a_rho``). Una tesela a ≤ ρ sin dato a ≤ ρ sí es prueba K3, y falla
    (NAS-10). Los puntos de la red a ≤ ρ caen en ``ventana_k3``.
  - **Quién pasa las teselas.** Una tesela que no se pasa se lee como que no existe. Por eso ``info_estaciones``
    recibe todas las teselas del conjunto de M0 cuya huella toca la ``ventana_k3`` de alguna estación (pendiente de
    I20); un recorte en memoria vale si cubre esas ventanas, porque fuera de ellas no se mira nada.
  - **La estación.** Lleva el motivo «sin_nasadem», que precede a «k3» y a «sin_z_s», y queda ``excluida`` aunque
    tenga fondo: con z_cat no tiene coordenadas confirmadas, y sin z_cat no tiene z_s (§2.5, D31). Vale con z_cat y
    sin él: D37 habla de la estación «sin cobertura NASADEM», y en las dos no hay prueba K3. ``k3_pasa`` y z_s son
    los de ``k3`` tal cual (§2.5): falso y NaN con z_cat; verdadero y NaN sin z_cat («coordenadas confirmadas»). No
    cambia resultados, porque la estación queda fuera y fuera de Q2; sólo cambia la etiqueta de la política (POL-5).
    «sigue fuera («sin_fondo»)» se lee como que la estación no vuelve a entrar: el motivo es «sin_nasadem» (TIP-14:
    el de este módulo prevalece) y ``sin_fondo`` lo pone después el operador. Las islas y la Antártica también son
    «sin_fondo»; ``declaraciones_estaciones`` cuenta aparte las «sin_nasadem» con fondo, que serían una sorpresa.
  - **Q2.** Sale del numerador y del denominador (``MOTIVOS_FUERA_DE_Q2``) y se informa aparte
    (``declaraciones_estaciones``). Lo aplica I12.
- NAS-17. **Una estación fuera de la grilla** (D34 [delegada], P23; §4.6: «Los estáticos de una estación son los de su
  celda»). Es la que tiene coordenadas legibles y en rango y cuya celda no está en ``celdas.parquet``: ``celda`` None
  y macrozona None (D9). No queda ``excluida``: «sigue entrenando A, B y AB», que no usan estáticos. Sin celda no
  tiene estáticos, así que no entra en las filas de C ni de C_est, y D34 la saca de la evaluación de todos los
  candidatos y la cuenta aparte. ``fuera_de_la_grilla`` es el predicado (no excluida y sin celda) y
  ``declaraciones_estaciones`` la cuenta. Lo aplican ``particiones``, ``candidatos`` y ``validacion`` (pedido al
  coordinador). Una estación excluida sin celda ya está fuera de todo y no se cuenta aquí.
- NAS-18. **Declaraciones de las estaciones** (D9, D16, D34, D37). ``declaraciones_estaciones`` da, en enteros de
  Python, el número de estaciones, de excluidas, de cada motivo de ``tipos.MotivoExclusion`` y de este módulo
  (también «sin_fondo», si ya lo puso ``orquestacion``), de «sin_nasadem» con fondo, de fuera de la grilla (NAS-17) y
  de estaciones sin macrozona. Sólo conteos: ningún código ni número de datos. ``tabla_estaciones`` las lleva en
  ``attrs["declaraciones"]`` para el registro de M2a. Un motivo desconocido, una excluida sin motivo o un motivo en
  una estación que entra son un error (ValueError).
Preguntas al autor: ninguna abierta de este módulo. NAS-P1 a NAS-P5 y las de sus revisores (P19 a P27) las fijaron
D30 a D38 [delegadas]; el código ya seguía esas propuestas, salvo D34 y D37, que se implementan en NAS-16 y NAS-17.
Depende de: tipos, constantes, umbrales, numerico, entorno.
"""
from __future__ import annotations

import dataclasses
import io
import math
import re
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from meteo_combinada import constantes, entorno, numerico, tipos

# ---------------------------------------------------------------------------
# Constantes de la red (§3) y de K1 (§2.5)
# ---------------------------------------------------------------------------
_PASO = constantes.valor("NASADEM_PASO_GRADOS")                  # (1, 3600): «paso 1/3.600°»
PUNTOS_POR_GRADO = _PASO[1] // _PASO[0]                          # 3.600
CELDAS_POR_GRADO = 100                                           # celdas de 0,01° (grilla nominal, CON-1)
PUNTOS_POR_CELDA = PUNTOS_POR_GRADO // CELDAS_POR_GRADO          # 36
PUNTOS_EN_CELDA = PUNTOS_POR_CELDA ** 2                          # 1.296
_MEDIO = 1 / 2
_R_KM = float(constantes.valor("R_TIERRA_KM"))                   # MC-59 y MC-60
_KM_POR_GRADO = math.radians(1) * _R_KM                         # «1° = π·6.371/180 km, sin cos φ» (MC-59)
_M_POR_PASO = _R_KM * 1000 * math.radians(1 / PUNTOS_POR_GRADO)  # Δy de la red, en m (NAS-7)
_K1_MEDIO, _K1_BASE = constantes.valor("K1_DECIMALES")           # 0,5·10⁻ᵈ grados
_K1_SEGUNDOS = constantes.valor("K1_SEGUNDOS")                   # 0,5″
_K1_MINUTOS = constantes.valor("K1_MINUTOS")                     # 0,5′
_K1_FACTOR = math.sqrt(constantes.valor("K1_RAIZ_DE"))           # √2
TPI_RADIOS_KM = tuple(float(r) for r in constantes.valor("TPI_RADIOS_KM"))   # (1, 5)
COLUMNAS_TPI = tuple(f"tpi{r:g}" for r in TPI_RADIOS_KM)          # «tpi1» y «tpi5» de ESQUEMA_ESTATICAS_CELDA
_C_LOG = constantes.valor("C_LOG_DISTANCIA")                     # log(1 + distancia)
_GHS_PASO_M = float(constantes.valor("GHS_RESOLUCION_M"))        # 100 m
_TOL_RED = 1e-6       # no-umbral: holgura numérica, en pasos de la red o de la celda, para reconocer un punto exacto
_LOTE_CELDAS = 64     # no-umbral: lado del lote de celdas (sólo memoria; el resultado no depende de él, NAS-15)
_ABREVIATURA = 8      # no-umbral: caracteres de una huella abreviada en un mensaje

# RELOJ §3.3 (copia de reloj_dmc.constantes COORD_LAT y COORD_LON; la prueba la compara por AST).
COORD_LAT_RELOJ = (-90, -17)    # no-umbral: rango de latitud de RELOJ §3.3, copiado (NAS-1)
COORD_LON_RELOJ = (-110, -55)   # no-umbral: rango de longitud de RELOJ §3.3, copiado (NAS-1)

# Motivos de exclusión que pone este módulo (NAS-12, TIP-14), en su orden de precedencia. «sin_fondo» lo pone
# orquestacion (PAR-1) y sólo en las que no estaban excluidas.
MOTIVO_COORDENADAS_ILEGIBLES = tipos.MotivoExclusion.COORDENADAS_ILEGIBLES.value
MOTIVO_FUERA_DE_RANGO = tipos.MotivoExclusion.COORDENADAS_FUERA_DE_RANGO.value
MOTIVO_SIN_NASADEM = "sin_nasadem"     # D37 (NAS-16); pedido al coordinador como tipos.MotivoExclusion.SIN_NASADEM
MOTIVO_K3 = tipos.MotivoExclusion.K3.value
MOTIVO_SIN_Z_S = tipos.MotivoExclusion.SIN_Z_S.value
MOTIVOS = (MOTIVO_COORDENADAS_ILEGIBLES, MOTIVO_FUERA_DE_RANGO, MOTIVO_SIN_NASADEM, MOTIVO_K3, MOTIVO_SIN_Z_S)
# Los que cuentan en Q2 como «K3 deja sin coordenadas» (D36, NAS-12); «sin_z_s» tiene coordenadas confirmadas.
MOTIVOS_SIN_COORDENADAS_K3 = tipos.MOTIVOS_SIN_COORDENADAS_K3
# Los que salen del numerador y del denominador de Q2 y se informan aparte (D37, NAS-16); pedido para tipos.
MOTIVOS_FUERA_DE_Q2 = frozenset({MOTIVO_SIN_NASADEM})
# Todos los motivos que puede llevar una InfoEstacion (los de este módulo y los de tipos, con «sin_fondo»; NAS-18).
_MOTIVOS_CONOCIDOS = tuple(dict.fromkeys([*MOTIVOS, *(m.value for m in tipos.MotivoExclusion)]))
_CIFRA = re.compile(r"[0-9]")     # un indicativo OMM tiene alguna cifra (NAS-12, NAS-P4)

# Etiquetas del descargador de NASADEM (descargar_topografia_nasadem.py) que se exigen (NAS-3).
PRODUCTO_NASADEM = "NASADEM_HGT"
UNIDADES_NASADEM = "meters"
_SHA = re.compile(r"[0-9a-f]{64}")

COLUMNAS_CATALOGO = ("codigo", "nombre", "lat_txt", "lon_txt", "alt_txt")       # las de RELOJ (leer_catalogo_dmc)
COLUMNAS_OPCIONALES = ("tipo", "propietario", "omm")
COLUMNAS_CELDAS = ("celda", "lat", "lon", "cod_comuna", "macrozona", "macrozona_cod")
COLUMNAS_PIXELES = ("pixel_id", "cell_west", "cell_east", "cell_south", "cell_north")


# ---------------------------------------------------------------------------
# Lectura de los textos del catálogo (NAS-1; copia de reloj_dmc.tablas, RELOJ §3.3)
# ---------------------------------------------------------------------------
_NUMERO = r"\d+(?:[.,]\d+)?"
_DECIMAL = re.compile(rf"(?P<signo>[+-]?)\s*(?P<valor>{_NUMERO})")
_SEXAGESIMAL = re.compile(
    rf"(?P<signo>[+-]?)\s*(?P<g>{_NUMERO})\s*[°º˚]?\s*"
    rf"(?:(?P<m>{_NUMERO})\s*['′’]?\s*)?"
    rf"(?:(?P<s>{_NUMERO})\s*(?:\"|″|”|''|′′|’’)?\s*)?"
    r"(?P<letra>[NSEWnsew])?")
_LETRAS = {"lat": {"S": -1, "N": 1}, "lon": {"W": -1, "E": 1}}


def _numero(texto: str | None) -> float | None:
    return None if texto is None else float(texto.replace(",", "."))


def _medio_decimal(numero: str) -> float:
    """K1: 0,5·10⁻ᵈ grados, con d los decimales escritos del número (NAS-2)."""
    partes = re.split(r"[.,]", numero)
    d = len(partes[1]) if len(partes) > 1 else 0
    return _K1_MEDIO * _K1_BASE ** (-d)


def _analizar_coordenada(texto: str | None, eje: str) -> tuple[float | None, float | None]:
    """(valor, medio paso en grados) de un texto del catálogo; (None, None) si no se puede interpretar.

    El valor es exactamente el de ``reloj_dmc.tablas.interpretar_coordenada`` (NAS-1); el medio paso es el de K1
    (NAS-2). La altitud sólo admite decimal y su medio paso no se usa."""
    if eje not in ("lat", "lon", "alt"):
        raise ValueError(f"eje desconocido: {eje!r}")
    if texto is None:
        return None, None
    t = str(texto).strip().replace("−", "-")
    if not t:
        return None, None
    m = _DECIMAL.fullmatch(t)
    if m:
        valor = float(m.group("valor").replace(",", "."))
        return (-valor if m.group("signo") == "-" else valor), _medio_decimal(m.group("valor"))
    if eje == "alt":
        return None, None
    m = _SEXAGESIMAL.fullmatch(t)
    if m is None:
        return None, None
    g, mi, s = _numero(m.group("g")), _numero(m.group("m")), _numero(m.group("s"))
    if (mi is not None and not 0 <= mi < 60) or (s is not None and not 0 <= s < 60):
        return None, None
    if (mi is not None and not float(g).is_integer()) or (s is not None and not float(mi).is_integer()):
        return None, None      # grados decimales con minutos, o minutos decimales con segundos
    valor = g + (mi or 0.0) / 60 + (s or 0.0) / 3600
    signo_escrito = {"-": -1, "+": 1, "": 0}[m.group("signo")]
    letra = m.group("letra")
    signo_letra = 0
    if letra is not None:
        signo_letra = _LETRAS[eje].get(letra.upper(), 0)
        if signo_letra == 0:
            return None, None
    if signo_escrito and signo_letra and signo_escrito != signo_letra:
        return None, None
    if s is not None:
        medio = _K1_SEGUNDOS / 3600          # «con segundos, 0,5″»
    elif mi is not None:
        medio = _K1_MINUTOS / 60             # «sólo minutos, 0,5′»
    else:
        medio = _medio_decimal(m.group("g"))
    return (-valor if -1 in (signo_escrito, signo_letra) else valor), medio


def interpretar_coordenada(texto: str | None, eje: str) -> float | None:
    """Como RELOJ §3.3 (copia de ``reloj_dmc.tablas.interpretar_coordenada``): decimal con punto o coma, o
    sexagesimal con signo o letra S/W; nunca invierte un signo. ``eje`` ∈ {"lat", "lon", "alt"}; None si no se lee."""
    return _analizar_coordenada(texto, eje)[0]


def coordenadas_en_rango(lat: float | None, lon: float | None) -> bool:
    """RELOJ §3.3: −90 ≤ lat ≤ −17 y −110 ≤ lon ≤ −55 (NAS-1)."""
    if lat is None or lon is None or not (math.isfinite(lat) and math.isfinite(lon)):
        return False
    return COORD_LAT_RELOJ[0] <= lat <= COORD_LAT_RELOJ[1] and COORD_LON_RELOJ[0] <= lon <= COORD_LON_RELOJ[1]


def rho_km(lat_txt: str, lon_txt: str, umbrales) -> float:
    """K1: ρ desde el texto de las coordenadas (§2.5, MC-59, NAS-2). NaN si un texto no se puede leer."""
    lat, medio_lat = _analizar_coordenada(lat_txt, "lat")
    lon, medio_lon = _analizar_coordenada(lon_txt, "lon")
    if lat is None or lon is None:
        return math.nan
    rho = max(medio_lat, medio_lon) * _KM_POR_GRADO * _K1_FACTOR
    return float(min(max(rho, float(umbrales.a("RHO_MIN_KM"))), float(umbrales.a("RHO_MAX_KM"))))


# ---------------------------------------------------------------------------
# La red NASADEM (NAS-3 a NAS-5)
# ---------------------------------------------------------------------------
def _a_red(grados) -> np.ndarray:
    """Posición en pasos de la red (grados·3.600), llevada al entero si está a ≤ _TOL_RED de él (NAS-5)."""
    v = np.asarray(grados, dtype=np.float64) * PUNTOS_POR_GRADO
    r = np.rint(v)
    return np.where(np.abs(v - r) <= _TOL_RED, r, v)


def _techo_red(grados) -> np.ndarray:
    return np.ceil(_a_red(grados)).astype(np.int64)


def _indice_exacto(x: float, que: str) -> int:
    """Índice de la red de un valor que debe caer en ella (centro de un píxel de tesela)."""
    v = float(x) * PUNTOS_POR_GRADO
    r = round(v)
    if abs(v - r) > _TOL_RED:
        raise ValueError(f"{que} no cae en la red de 1/{PUNTOS_POR_GRADO}° (píxel-punto): {x!r}")
    return int(r)


@dataclass(frozen=True, eq=False)
class TeselaDEM:
    """Una tesela NASADEM leída (píxel-punto de 1/3.600°), con su sha256 (NAS-3).

    La fila r y la columna c son el punto de la red (I, J) = (``i_norte`` − r, ``j_oeste`` + c), con lat = I/3.600 y
    lon = J/3.600. ``z`` es int16 y ``dato`` dice qué puntos tienen dato."""
    nombre: str
    sha256: str
    i_norte: int
    j_oeste: int
    z: np.ndarray
    dato: np.ndarray
    tile_id: str | None = None
    aoi_id: str | None = None

    @property
    def i_sur(self) -> int:
        return self.i_norte - self.z.shape[0] + 1

    @property
    def j_este(self) -> int:
        return self.j_oeste + self.z.shape[1] - 1


def _exigir_sha(sha256: str) -> None:
    if not isinstance(sha256, str) or not _SHA.fullmatch(sha256):
        raise ValueError("se exige un sha256 de 64 hexadecimales en minúscula")


def _leer_con_huella(ruta, sha256: str) -> bytes:
    """Los bytes del archivo, leídos con ``open`` de Python, si su sha256 es el dado (NAS-3)."""
    _exigir_sha(sha256)
    datos = Path(ruta).read_bytes()
    actual = entorno.sha256_bytes(datos)
    if actual != sha256:
        raise ValueError(f"la huella de {Path(ruta).name} no es la esperada ({actual[:_ABREVIATURA]}…)")
    return datos


def _es_paso(valor: float, paso: float) -> bool:
    return abs(abs(float(valor)) / paso - 1) <= _TOL_RED


def leer_tesela(ruta, sha256: str) -> TeselaDEM:
    """Lee una tesela NASADEM (GeoTIFF int16 de 1/3.600°, SIN-9) y exige su sha256 (NAS-3)."""
    datos = _leer_con_huella(ruta, sha256)
    import rasterio
    from rasterio.io import MemoryFile

    nombre = Path(ruta).name
    with rasterio.Env(), MemoryFile(datos) as memoria, memoria.open() as ds:
        t = ds.transform
        if ds.count != 1 or ds.dtypes[0] != "int16":
            raise ValueError(f"{nombre}: se espera una banda int16")
        if ds.crs is None or ds.crs.to_epsg() != 4326:
            raise ValueError(f"{nombre}: se espera EPSG:4326")
        if t.b != 0 or t.d != 0 or t.a <= 0 or t.e >= 0:
            raise ValueError(f"{nombre}: transformación rotada o que no es norte arriba")
        if not (_es_paso(t.a, 1 / PUNTOS_POR_GRADO) and _es_paso(t.e, 1 / PUNTOS_POR_GRADO)):
            raise ValueError(f"{nombre}: el paso no es 1/{PUNTOS_POR_GRADO}°")
        etiquetas = ds.tags()
        if etiquetas.get("producto") != PRODUCTO_NASADEM or etiquetas.get("vertical_units") != UNIDADES_NASADEM:
            raise ValueError(f"{nombre}: no trae las etiquetas de NASADEM del descargador")
        j_oeste = _indice_exacto(t.c + t.a * _MEDIO, f"{nombre}: el primer centro (longitud)")
        i_norte = _indice_exacto(t.f + t.e * _MEDIO, f"{nombre}: el primer centro (latitud)")
        z = ds.read(1)
        dato = ds.dataset_mask() > 0
        if ds.nodata is not None:
            dato &= z != ds.nodata
    return TeselaDEM(nombre=nombre, sha256=sha256, i_norte=i_norte, j_oeste=j_oeste, z=z, dato=dato,
                     tile_id=etiquetas.get("tile_id"), aoi_id=etiquetas.get("aoi_id"))


def _ventana(teselas: Sequence[TeselaDEM], i_norte: int, i_sur: int, j_oeste: int, j_este: int):
    """(z int32, dato) en el rectángulo de la red [i_sur, i_norte] × [j_oeste, j_este], norte arriba (NAS-4)."""
    alto, ancho = i_norte - i_sur + 1, j_este - j_oeste + 1
    if alto <= 0 or ancho <= 0:
        raise ValueError("ventana vacía")
    z = np.zeros((alto, ancho), dtype=np.int32)
    dato = np.zeros((alto, ancho), dtype=bool)
    for t in teselas:
        n, s = min(i_norte, t.i_norte), max(i_sur, t.i_sur)
        o, e = max(j_oeste, t.j_oeste), min(j_este, t.j_este)
        if n < s or e < o:
            continue
        fv, cv = slice(i_norte - n, i_norte - s + 1), slice(o - j_oeste, e - j_oeste + 1)
        ft, ct = slice(t.i_norte - n, t.i_norte - s + 1), slice(o - t.j_oeste, e - t.j_oeste + 1)
        dt = t.dato[ft, ct]
        zt = t.z[ft, ct].astype(np.int32)
        if np.any(dato[fv, cv] & dt & (z[fv, cv] != zt)):
            raise ValueError(f"{t.nombre}: un punto de la red con dato en dos teselas vale distinto")
        z[fv, cv] = np.where(dt, zt, z[fv, cv])
        dato[fv, cv] |= dt
    return z, dato


def celda_de_puntos(lat, lon) -> np.ndarray:
    """Celda de ≈ 1 km de cada punto, con los bordes oeste y sur cerrados (§3, NAS-5).

    Devuelve un arreglo (n, 2) int64 con los índices (⌊lat·100⌋, ⌊lon·100⌋) de la celda de 0,01° (no el id de
    ``celdas.parquet``). Un valor a ≤ 10⁻⁶ pasos de un punto de la red se lleva a él antes del piso."""
    lat = np.atleast_1d(np.asarray(lat, dtype=np.float64))
    lon = np.atleast_1d(np.asarray(lon, dtype=np.float64))
    if lat.shape != lon.shape or lat.ndim != 1:
        raise ValueError("lat y lon deben ser vectores del mismo largo")
    if not (np.isfinite(lat).all() and np.isfinite(lon).all()):
        raise ValueError("celda_de_puntos exige coordenadas finitas")
    fila = np.floor(_a_red(lat) / PUNTOS_POR_CELDA).astype(np.int64)
    columna = np.floor(_a_red(lon) / PUNTOS_POR_CELDA).astype(np.int64)
    return np.stack([fila, columna], axis=-1)


def _indices_de_centros(lat, lon) -> tuple[np.ndarray, np.ndarray]:
    """(k, m) de celdas con centro en k/100 + 0,005° (NAS-5); ValueError si alguna no está alineada."""
    salida = []
    for x, que in ((lat, "latitud"), (lon, "longitud")):
        u = np.asarray(x, dtype=np.float64) * CELDAS_POR_GRADO - _MEDIO
        k = np.rint(u)
        if not np.isfinite(u).all() or np.any(np.abs(u - k) > _TOL_RED):
            raise ValueError(f"celdas cuya {que} no es el centro de una celda de 0,01° (k/100 + 0,005°)")
        salida.append(k.astype(np.int64))
    return salida[0], salida[1]


def _bilineal(lat: float, lon: float, teselas: Sequence[TeselaDEM]) -> float:
    """NASADEM bilineal en el punto, en índices de la red; NaN si un punto con peso > 0 no tiene dato (NAS-11)."""
    vi, vj = float(_a_red(lat)), float(_a_red(lon))
    i0, j0 = math.floor(vi), math.floor(vj)
    fi, fj = vi - i0, vj - j0
    z, dato = _ventana(teselas, i0 + 1, i0, j0, j0 + 1)        # fila 0: I = i0 + 1 (norte); fila 1: I = i0
    pesos = np.array([[fi * (1 - fj), fi * fj], [(1 - fi) * (1 - fj), (1 - fi) * fj]])
    usados = pesos > 0
    if not dato[usados].all():
        return math.nan
    return float(np.sum(np.where(usados, pesos * z, 0.0)))


def _punto_k3(lat, lon, rho_km) -> tuple[float, float, float]:
    lat, lon, rho = float(lat), float(lon), float(rho_km)
    if not (math.isfinite(lat) and math.isfinite(lon) and math.isfinite(rho) and rho > 0):
        raise ValueError("K3 exige lat, lon y ρ finitos (ρ > 0)")
    return lat, lon, rho


def _rectangulo_k3(lat: float, lon: float, rho: float) -> tuple[int, int, int, int]:
    """(i_norte, i_sur, j_oeste, j_este) de la red que contiene todos los puntos a ≤ ρ del punto (con holgura), y
    también los cuatro de su bilineal (NAS-10, NAS-11 y NAS-16)."""
    n = math.ceil(math.degrees(rho / _R_KM) * PUNTOS_POR_GRADO) + 1
    cos_min = math.cos(math.radians(abs(lat) + n / PUNTOS_POR_GRADO))
    if cos_min <= 0:
        raise ValueError("K3: punto demasiado cerca del polo")
    m = math.ceil(n / cos_min) + 1
    ic, jc = int(np.rint(_a_red(lat))), int(np.rint(_a_red(lon)))
    return ic + n, ic - n, jc - m, jc + m


def _a_rho(lat: float, lon: float, rho: float, mascara: np.ndarray, i_norte: int,
           j_oeste: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(filas, columnas, cerca): los puntos de ``mascara`` en la ventana y si cada uno está a ≤ ρ (haversine)."""
    filas, columnas = np.nonzero(mascara)
    lat_p = (i_norte - filas) / PUNTOS_POR_GRADO
    lon_p = (j_oeste + columnas) / PUNTOS_POR_GRADO
    return filas, columnas, numerico.haversine_km(lat, lon, lat_p, lon_p) <= rho


def ventana_k3(lat, lon, rho_km) -> dict[str, float]:
    """Los bordes, en grados, de los puntos de la red que miran K3 y la bilineal de una estación: las teselas que
    tocan esta ventana son las que ``info_estaciones`` necesita para ella (NAS-16)."""
    i_norte, i_sur, j_oeste, j_este = _rectangulo_k3(*_punto_k3(lat, lon, rho_km))
    return {"lat_norte": i_norte / PUNTOS_POR_GRADO, "lat_sur": i_sur / PUNTOS_POR_GRADO,
            "lon_oeste": j_oeste / PUNTOS_POR_GRADO, "lon_este": j_este / PUNTOS_POR_GRADO}


def _cobertura(teselas: Sequence[TeselaDEM], i_norte: int, i_sur: int, j_oeste: int, j_este: int) -> np.ndarray:
    """Los puntos del rectángulo de la red que están en la huella de alguna tesela, con dato o sin él (NAS-16)."""
    cubierto = np.zeros((i_norte - i_sur + 1, j_este - j_oeste + 1), dtype=bool)
    for t in teselas:
        n, s = min(i_norte, t.i_norte), max(i_sur, t.i_sur)
        o, e = max(j_oeste, t.j_oeste), min(j_este, t.j_este)
        if n >= s and e >= o:
            cubierto[i_norte - n:i_norte - s + 1, o - j_oeste:e - j_oeste + 1] = True
    return cubierto


def hay_tesela_a_rho(lat, lon, rho_km, teselas) -> bool:
    """D37 (NAS-16): si alguna tesela tiene algún punto de su red, con dato o sin él, a distancia haversine ≤ ρ del
    punto. Si no, la estación no tiene prueba K3 (motivo «sin_nasadem»)."""
    lat, lon, rho = _punto_k3(lat, lon, rho_km)
    i_norte, i_sur, j_oeste, j_este = _rectangulo_k3(lat, lon, rho)
    cubierto = _cobertura(teselas, i_norte, i_sur, j_oeste, j_este)
    if not cubierto.any():
        return False
    return bool(np.any(_a_rho(lat, lon, rho, cubierto, i_norte, j_oeste)[2]))


def k3(lat, lon, z_cat, rho_km, teselas, umbrales) -> tuple[bool, float]:
    """K3 (§2.5, NAS-10 y NAS-11): (coordenadas confirmadas, z_s), la regla literal.

    Con z_cat: pasa si algún punto NASADEM con dato está a ≤ ρ (haversine) con |z_DEM − z_cat| ≤ K3_DZ_M; z_s = z_cat
    si pasa y NaN si no. Sin z_cat (NaN): (True, NASADEM bilineal en el punto), NaN si no se puede. Sin ninguna tesela a
    ≤ ρ da lo mismo que sin dato, (False, NaN) o (True, NaN): que entonces no haya prueba (D37) lo mira
    ``info_estaciones`` con ``hay_tesela_a_rho`` (NAS-16)."""
    lat, lon, rho = _punto_k3(lat, lon, rho_km)
    z_cat = float(z_cat) if z_cat is not None else math.nan
    if not math.isfinite(z_cat):
        return True, _bilineal(lat, lon, teselas)
    i_norte, i_sur, j_oeste, j_este = _rectangulo_k3(lat, lon, rho)
    z, dato = _ventana(teselas, i_norte, i_sur, j_oeste, j_este)
    if not dato.any():
        return False, math.nan
    filas, columnas, cerca = _a_rho(lat, lon, rho, dato, i_norte, j_oeste)
    coincide = np.abs(z[filas, columnas].astype(np.float64) - z_cat) <= float(umbrales.a("K3_DZ_M"))
    pasa = bool(np.any(cerca & coincide))
    return pasa, (z_cat if pasa else math.nan)


# ---------------------------------------------------------------------------
# GHS-POP (NAS-8)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, eq=False)
class TeselaGHS:
    """Una tesela (o ventana) GHS-POP de 100 m en Mollweide, con su sha256. ``pob`` es float32 (filas × columnas);
    la fila 0 empieza en ``y_norte`` y la columna 0 en ``x_oeste`` (m)."""
    nombre: str
    sha256: str
    x_oeste: float
    y_norte: float
    paso_m: float
    pob: np.ndarray
    nodata: float | None


def leer_ghs(ruta, sha256: str) -> TeselaGHS:
    """Lee una tesela GHS-POP (GeoTIFF float32 de 100 m en Mollweide, o el .zip con su .tif) y exige su sha256."""
    datos = _leer_con_huella(ruta, sha256)
    nombre = Path(ruta).name
    if zipfile.is_zipfile(io.BytesIO(datos)):
        with zipfile.ZipFile(io.BytesIO(datos)) as z:
            esperado = Path(nombre).stem + ".tif"
            tifs = [n for n in z.namelist() if n.lower().endswith(".tif")]
            elegido = esperado if esperado in tifs else (tifs[0] if len(tifs) == 1 else None)
            if elegido is None:
                raise ValueError(f"{nombre}: no se sabe qué .tif leer ({tifs})")
            datos = z.read(elegido)
    import rasterio
    from rasterio.io import MemoryFile

    with rasterio.Env(), MemoryFile(datos) as memoria, memoria.open() as ds:
        t = ds.transform
        if ds.count != 1 or ds.dtypes[0] != "float32":
            raise ValueError(f"{nombre}: se espera una banda float32")
        if ds.crs is None or "mollweide" not in ds.crs.to_wkt().lower():
            raise ValueError(f"{nombre}: se espera Mollweide (ESRI:54009)")
        if t.b != 0 or t.d != 0 or not (_es_paso(t.a, _GHS_PASO_M) and _es_paso(t.e, _GHS_PASO_M)) or t.e >= 0:
            raise ValueError(f"{nombre}: se esperan píxeles de {_GHS_PASO_M:g} m, norte arriba")
        pob = ds.read(1)
        nodata = None if ds.nodata is None else float(ds.nodata)
    return TeselaGHS(nombre=nombre, sha256=sha256, x_oeste=float(t.c), y_norte=float(t.f), paso_m=float(t.a),
                     pob=pob, nodata=nodata)


def _poblacion_en_puntos(lat: np.ndarray, lon: np.ndarray, ghs: Sequence[TeselaGHS]):
    """(peso, cubierto): la población del píxel GHS que contiene cada punto (0 si ≤ 0, no finita o nodata) y si
    alguna tesela lo cubre (NAS-8)."""
    x, y = numerico.mollweide(lat, lon)
    peso = np.zeros(x.shape, dtype=np.float64)
    cubierto = np.zeros(x.shape, dtype=bool)
    for t in ghs:
        columna = np.floor((x - t.x_oeste) / t.paso_m)
        fila = np.floor((t.y_norte - y) / t.paso_m)
        dentro = (columna >= 0) & (columna < t.pob.shape[1]) & (fila >= 0) & (fila < t.pob.shape[0])
        v = np.zeros(x.shape, dtype=np.float64)
        v[dentro] = t.pob[fila[dentro].astype(np.int64), columna[dentro].astype(np.int64)]
        valido = np.isfinite(v) & (v > 0)
        if t.nodata is not None:
            valido &= v != t.nodata
        v = np.where(valido, v, 0.0)
        if np.any(dentro & cubierto & (v != peso)):
            raise ValueError(f"{t.nombre}: un punto cubierto por dos teselas GHS con valores distintos")
        peso = np.where(dentro, v, peso)
        cubierto |= dentro
    return peso, cubierto


# ---------------------------------------------------------------------------
# Estáticos de las celdas (§3, §4.6)
# ---------------------------------------------------------------------------
def _perfil_disco(k_lat: int, radio_km: float) -> tuple[np.ndarray, np.ndarray]:
    """Disco de radio r alrededor del centro de una celda de la fila k (NAS-9): para cada fila dI de la red (I = I_c +
    dI), el medio ancho m(dI) en columnas, con los puntos (dI, dJ) a distancia haversine ≤ r para |dJ| ≤ m(dI)."""
    phi_c = math.radians((k_lat + _MEDIO) / CELDAS_POR_GRADO)
    h_r = math.sin(radio_km / (2 * _R_KM)) ** 2
    n = int(math.floor(math.degrees(radio_km / _R_KM) * PUNTOS_POR_GRADO))
    d_i = np.arange(-n, n + 1, dtype=np.int64)
    d_phi = np.radians(d_i / PUNTOS_POR_GRADO)
    q = (h_r - np.sin(d_phi / 2) ** 2) / (np.cos(phi_c + d_phi) * math.cos(phi_c))
    dentro = q >= 0
    d_lambda = 2 * np.arcsin(np.sqrt(np.clip(q, 0.0, 1.0)))
    m = np.floor(np.degrees(d_lambda) * PUNTOS_POR_GRADO).astype(np.int64)
    return d_i[dentro], m[dentro]


def _limites(k_lat: np.ndarray, k_lon: np.ndarray, perfiles: Mapping) -> tuple[int, int, int, int]:
    """(i_norte, i_sur, j_oeste, j_este) de la red que piden las celdas: sus puntos, un vecino más (pendiente) y los
    discos del TPI."""
    i_c = k_lat * PUNTOS_POR_CELDA + PUNTOS_POR_CELDA // 2
    j_c = k_lon * PUNTOS_POR_CELDA + PUNTOS_POR_CELDA // 2
    i_norte = int(np.max(k_lat * PUNTOS_POR_CELDA + PUNTOS_POR_CELDA))
    i_sur = int(np.min(k_lat * PUNTOS_POR_CELDA - 1))
    j_oeste = int(np.min(k_lon * PUNTOS_POR_CELDA - 1))
    j_este = int(np.max(k_lon * PUNTOS_POR_CELDA + PUNTOS_POR_CELDA))
    for k in np.unique(k_lat):
        sel = k_lat == k
        for r in TPI_RADIOS_KM:
            d_i, m = perfiles[(int(k), r)]
            i_norte = max(i_norte, int(np.max(i_c[sel])) + int(d_i.max()))
            i_sur = min(i_sur, int(np.min(i_c[sel])) + int(d_i.min()))
            j_oeste = min(j_oeste, int(np.min(j_c[sel])) - int(m.max()))
            j_este = max(j_este, int(np.max(j_c[sel])) + int(m.max()))
    return i_norte, i_sur, j_oeste, j_este


def _perfiles(k_lat: np.ndarray) -> dict:
    return {(int(k), r): _perfil_disco(int(k), r) for k in np.unique(k_lat) for r in TPI_RADIOS_KM}


def ventana_necesaria(celdas) -> dict[str, float]:
    """Los bordes, en grados, de los puntos de la red que piden las celdas (sus puntos, la pendiente y los discos del
    TPI): ``estaticos_celdas`` necesita las teselas que los cubren (NAS-15)."""
    k_lat, k_lon = _indices_de_centros(celdas["lat"], celdas["lon"])
    i_norte, i_sur, j_oeste, j_este = _limites(k_lat, k_lon, _perfiles(k_lat))
    return {"lat_norte": i_norte / PUNTOS_POR_GRADO, "lat_sur": i_sur / PUNTOS_POR_GRADO,
            "lon_oeste": j_oeste / PUNTOS_POR_GRADO, "lon_este": j_este / PUNTOS_POR_GRADO}


def _pendientes(z: np.ndarray, dato: np.ndarray, i_norte: int) -> np.ndarray:
    """Pendiente en grados de cada punto de la ventana (NAS-7); NaN sin dato o con un vecino sin dato."""
    alto, ancho = z.shape
    salida = np.full((alto, ancho), np.nan)
    if min(alto, ancho) <= 2:                                    # sin puntos interiores
        return salida
    zf = z.astype(np.float64)
    phi = np.radians((i_norte - np.arange(1, alto - 1)) / PUNTOS_POR_GRADO)
    dx = (_M_POR_PASO * np.cos(phi))[:, None]
    dz_dy = (zf[:-2, 1:-1] - zf[2:, 1:-1]) / (2 * _M_POR_PASO)
    dz_dx = (zf[1:-1, 2:] - zf[1:-1, :-2]) / (2 * dx)
    ok = dato[1:-1, 1:-1] & dato[:-2, 1:-1] & dato[2:, 1:-1] & dato[1:-1, 2:] & dato[1:-1, :-2]
    salida[1:-1, 1:-1] = np.where(ok, np.degrees(np.arctan(np.hypot(dz_dx, dz_dy))), np.nan)
    return salida


def _bloques(arreglo: np.ndarray, filas: np.ndarray, columnas: np.ndarray) -> np.ndarray:
    """(n, 36, 36): el bloque de puntos de cada celda, contiguo y en el mismo orden siempre (NAS-15)."""
    return np.ascontiguousarray(arreglo[filas[:, :, None], columnas[:, None, :]])


def _lote(k_lat, k_lon, teselas, ghs, perfiles, umbral_tpi) -> dict[str, np.ndarray]:
    """Los estáticos NASADEM y GHS de un lote de celdas (NAS-6 a NAS-9)."""
    i_norte, i_sur, j_oeste, j_este = _limites(k_lat, k_lon, perfiles)
    z, dato = _ventana(teselas, i_norte, i_sur, j_oeste, j_este)
    paso = np.arange(PUNTOS_POR_CELDA, dtype=np.int64)
    filas = (i_norte - (k_lat * PUNTOS_POR_CELDA + PUNTOS_POR_CELDA - 1))[:, None] + paso[None, :]
    columnas = (k_lon * PUNTOS_POR_CELDA - j_oeste)[:, None] + paso[None, :]
    bz, bd = _bloques(z, filas, columnas), _bloques(dato, filas, columnas)
    n_dato = bd.sum(axis=(1, 2))
    suma_z = np.where(bd, bz, 0).astype(np.int64).sum(axis=(1, 2))
    con_dato = n_dato > 0
    z_media = np.where(con_dato, suma_z / np.where(con_dato, n_dato, 1), np.nan)
    salida = {"z_media": z_media, "frac_dato": n_dato / PUNTOS_EN_CELDA}

    bp = _bloques(_pendientes(z, dato, i_norte), filas, columnas)
    definida = np.isfinite(bp)
    n_p = definida.sum(axis=(1, 2))
    suma_p = np.where(definida, bp, 0.0).sum(axis=(1, 2))
    salida["pendiente_deg"] = np.where(n_p > 0, suma_p / np.where(n_p > 0, n_p, 1), np.nan)

    if ghs is None:
        salida["z_poblada"], salida["z_poblada_es_media"] = z_media.copy(), np.ones(len(k_lat), dtype=bool)
        salida["fuera_de_ghs"] = np.zeros(len(k_lat), dtype=bool)
    else:
        lat_p = np.broadcast_to(((i_norte - filas) / PUNTOS_POR_GRADO)[:, :, None], bz.shape)
        lon_p = np.broadcast_to(((j_oeste + columnas) / PUNTOS_POR_GRADO)[:, None, :], bz.shape)
        peso, cubierto = _poblacion_en_puntos(lat_p.ravel(), lon_p.ravel(), ghs)
        peso = np.where(bd, peso.reshape(bz.shape), 0.0)
        suma_w = peso.sum(axis=(1, 2))
        suma_wz = (peso * bz).sum(axis=(1, 2))
        poblada = suma_w > 0
        salida["z_poblada"] = np.where(poblada, suma_wz / np.where(poblada, suma_w, 1.0), z_media)
        salida["z_poblada_es_media"] = ~poblada
        salida["fuera_de_ghs"] = ~cubierto.reshape(bz.shape).any(axis=(1, 2))

    acumulado_z = np.zeros((z.shape[0], z.shape[1] + 1), dtype=np.int64)
    acumulado_n = np.zeros((z.shape[0], z.shape[1] + 1), dtype=np.int64)
    acumulado_z[:, 1:] = np.cumsum(np.where(dato, z, 0), axis=1, dtype=np.int64)
    acumulado_n[:, 1:] = np.cumsum(dato, axis=1, dtype=np.int64)
    i_c = k_lat * PUNTOS_POR_CELDA + PUNTOS_POR_CELDA // 2
    j_c = k_lon * PUNTOS_POR_CELDA + PUNTOS_POR_CELDA // 2
    for columna, r in zip(COLUMNAS_TPI, TPI_RADIOS_KM):
        tpi = np.full(len(k_lat), np.nan)
        truncado = np.ones(len(k_lat), dtype=bool)
        for k in np.unique(k_lat):
            sel = np.flatnonzero(k_lat == k)
            d_i, m = perfiles[(int(k), r)]
            filas_d = (i_norte - (int(i_c[sel[0]]) + d_i))[None, :]
            cc = (j_c[sel] - j_oeste)[:, None]
            desde, hasta = cc - m[None, :], cc + m[None, :] + 1
            suma = (acumulado_z[filas_d, hasta] - acumulado_z[filas_d, desde]).sum(axis=1)
            cuenta = (acumulado_n[filas_d, hasta] - acumulado_n[filas_d, desde]).sum(axis=1)
            total = int(np.sum(2 * m + 1))
            media = np.where(cuenta > 0, suma / np.where(cuenta > 0, cuenta, 1), np.nan)
            tpi[sel] = z_media[sel] - media
            truncado[sel] = cuenta / total < umbral_tpi
        salida[columna], salida[f"{columna}_truncado"] = tpi, truncado
    return salida


def _por_celda(tabla, columnas: Sequence[str], nombre: str, celdas_ids: np.ndarray) -> pd.DataFrame:
    """Las filas de ``tabla`` de cada celda, en el orden de ``celdas_ids``; ValueError si falta o se repite una."""
    faltan = [c for c in ("celda", *columnas) if c not in tabla.columns]
    if faltan:
        raise ValueError(f"a {nombre} le faltan las columnas {faltan}")
    if tabla["celda"].duplicated().any():
        raise ValueError(f"celda repetida en {nombre}")
    indexada = tabla.set_index("celda")[list(columnas)]
    ausentes = pd.Index(celdas_ids).difference(indexada.index)
    if len(ausentes):
        raise ValueError(f"{len(ausentes)} celdas de la grilla no están en {nombre} (NAS-14)")
    return indexada.reindex(celdas_ids)


def estaticos_celdas(celdas, teselas, ghs, estaticas_v1, lulc, umbrales) -> pd.DataFrame:
    """``ESQUEMA_ESTATICAS_CELDA`` de las celdas de ``celdas`` (filas de ``celdas.parquet``), en su orden (§3, §4.6).

    ``teselas``: ``TeselaDEM`` que cubren ``ventana_necesaria(celdas)``; ``ghs``: ``TeselaGHS`` de 2020 (al menos una),
    o None si no se pudieron leer (se usa la media y se declara); ``estaticas_v1`` y ``lulc``: ``estaticas.parquet`` y
    ``estaticas_lulc.parquet``. ``attrs["declaraciones"]`` lleva los conteos de NAS-6 y NAS-8 y las teselas GHS."""
    faltan = [c for c in ("celda", "lat", "lon", "cod_comuna", "macrozona_cod") if c not in celdas.columns]
    if faltan:
        raise ValueError(f"a las celdas les faltan las columnas {faltan}")
    if ghs is not None:
        ghs = tuple(ghs)
        if not ghs:
            raise ValueError("ghs vacío: sin ninguna tesela GHS legible se pasa None (se usa la media y se declara, "
                             "NAS-8)")
        if not all(isinstance(g, TeselaGHS) for g in ghs):
            raise TypeError("ghs lleva TeselaGHS (las de leer_ghs) o es None")
    huellas_ghs = () if ghs is None else tuple(sorted({g.sha256 for g in ghs}))
    ids = celdas["celda"].to_numpy(dtype=np.int64)
    if len(np.unique(ids)) != len(ids):
        raise ValueError("celda repetida en la grilla")
    k_lat, k_lon = _indices_de_centros(celdas["lat"], celdas["lon"])
    claves = list(zip(k_lat.tolist(), k_lon.tolist()))
    if len(set(claves)) != len(claves):
        raise ValueError("dos celdas con el mismo centro")
    v1 = _por_celda(estaticas_v1, ("dist_costa_km",), "estaticas", ids)
    anio = umbrales.a("C_ANIO_LULC")
    if "anio" not in lulc.columns:
        raise ValueError("a estaticas_lulc le falta la columna anio")
    cobertura = _por_celda(lulc[lulc["anio"] == anio], tipos.LULC, f"estaticas_lulc de {anio}", ids)
    umbral_tpi = umbrales.frac("C_TPI_PCT")
    perfiles = _perfiles(k_lat)

    n = len(ids)
    res: dict[str, np.ndarray] = {c: np.full(n, np.nan) for c in ("z_media", "z_poblada", "frac_dato",
                                                                    "pendiente_deg", *COLUMNAS_TPI)}
    for c in ("z_poblada_es_media", *(f"{t}_truncado" for t in COLUMNAS_TPI), "fuera_de_ghs"):
        res[c] = np.zeros(n, dtype=bool)
    lotes: dict[tuple[int, int], list[int]] = defaultdict(list)
    for posicion, (k, m) in enumerate(claves):
        lotes[(k // _LOTE_CELDAS, m // _LOTE_CELDAS)].append(posicion)
    for clave in sorted(lotes):
        sel = np.asarray(lotes[clave], dtype=np.int64)
        for c, v in _lote(k_lat[sel], k_lon[sel], teselas, ghs, perfiles, umbral_tpi).items():
            res[c][sel] = v

    dist = v1["dist_costa_km"].to_numpy(dtype=np.float64)
    df = pd.DataFrame({
        "celda": ids, "z_media": res["z_media"], "z_poblada": res["z_poblada"],
        "z_poblada_es_media": res["z_poblada_es_media"], "frac_dato": res["frac_dato"],
        **{t: res[t] for t in COLUMNAS_TPI}, **{f"{t}_truncado": res[f"{t}_truncado"] for t in COLUMNAS_TPI},
        "pendiente_deg": res["pendiente_deg"],
        "log_dist_costa": np.log(_C_LOG + dist),
        **{c: cobertura[c].to_numpy(dtype=np.float64) for c in tipos.LULC},
        "lat": celdas["lat"].to_numpy(dtype=np.float64),
        "macrozona_cod": celdas["macrozona_cod"].to_numpy(), "cod_comuna": celdas["cod_comuna"].to_numpy(),
    })
    df = df.astype(dict(tipos.ESQUEMA_ESTATICAS_CELDA))
    tipos.validar_esquema(df, tipos.ESQUEMA_ESTATICAS_CELDA, nombre="estaticos_celdas")
    df.attrs["esquema"] = tipos.ESQUEMA_ESTATICAS_CELDA.version
    df.attrs["declaraciones"] = {
        "ghs_legible": ghs is not None,
        "teselas_ghs": len(huellas_ghs),
        "huellas_ghs": huellas_ghs,
        "celdas": int(n),
        "celdas_sin_dato_nasadem": int(np.sum(~np.isfinite(res["z_media"]))),
        "celdas_con_media_en_vez_de_poblada": int(np.sum(res["z_poblada_es_media"])),
        "celdas_fuera_de_ghs": int(np.sum(res["fuera_de_ghs"])) if ghs is not None else int(n),
        **{f"celdas_{t}_truncado": int(np.sum(res[f"{t}_truncado"])) for t in COLUMNAS_TPI},
    }
    return df


def _tpi_y_truncado(tpi, truncado) -> tuple[np.ndarray, np.ndarray]:
    tpi = np.asarray(tpi, dtype=np.float64)
    truncado = np.asarray(truncado)
    if tpi.shape != truncado.shape:
        raise ValueError("tpi y truncado deben tener la misma forma")
    if truncado.dtype != np.bool_:
        raise TypeError("truncado es la columna booleana tpi*_truncado")
    return tpi, truncado


def tpi_entra_a_estandarizar(tpi, truncado) -> np.ndarray:
    """D33 (NAS-9): los TPI que entran a la media y al desvío de la estandarización, los finitos y no truncados. Un
    TPI truncado no entra (y después vale 0)."""
    tpi, truncado = _tpi_y_truncado(tpi, truncado)
    return ~truncado & np.isfinite(tpi)


def estandarizar_tpi(tpi, truncado, media: float, desvio: float) -> np.ndarray:
    """§4.6: (TPI − media)/desvío, y 0 donde ``tpi_truncado`` («TPI = 0 tras estandarizar»; NAS-9). La media y el
    desvío los fija ``candidatos`` con su entrenamiento, sólo con los TPI de ``tpi_entra_a_estandarizar`` (D33)."""
    tpi, truncado = _tpi_y_truncado(tpi, truncado)
    if not (math.isfinite(media) and math.isfinite(desvio) and desvio > 0):
        raise ValueError("estandarizar_tpi exige media finita y desvío finito y positivo")
    return np.where(truncado, 0.0, (tpi - media) / desvio)


# ---------------------------------------------------------------------------
# Altitud de la huella de los píxeles ERA5-Land (acuerdo A9, NAS-13)
# ---------------------------------------------------------------------------
def nasadem_en_pixeles(catalogo, teselas) -> pd.DataFrame:
    """``pixel_id``, ``z_nasadem`` y ``frac_nasadem`` (float64) de cada píxel del catálogo, en su orden (NAS-13)."""
    faltan = [c for c in COLUMNAS_PIXELES if c not in catalogo.columns]
    if faltan:
        raise ValueError(f"al catálogo de píxeles le faltan {faltan}")
    i_lo = _techo_red(catalogo["cell_south"].to_numpy(dtype=np.float64))
    i_hi = _techo_red(catalogo["cell_north"].to_numpy(dtype=np.float64)) - 1
    j_lo = _techo_red(catalogo["cell_west"].to_numpy(dtype=np.float64))
    j_hi = _techo_red(catalogo["cell_east"].to_numpy(dtype=np.float64)) - 1
    if np.any(i_hi < i_lo) or np.any(j_hi < j_lo):
        raise ValueError("huella de píxel vacía en el catálogo")
    n = len(catalogo)
    z_media, frac = np.full(n, np.nan), np.zeros(n)
    lotes: dict[tuple[int, int], list[int]] = defaultdict(list)
    for p in range(n):
        lotes[(int(i_lo[p]) // PUNTOS_POR_GRADO, int(j_lo[p]) // PUNTOS_POR_GRADO)].append(p)
    for clave in sorted(lotes):
        sel = np.asarray(lotes[clave], dtype=np.int64)
        i_norte, i_sur = int(i_hi[sel].max()), int(i_lo[sel].min())
        j_oeste, j_este = int(j_lo[sel].min()), int(j_hi[sel].max())
        z, dato = _ventana(teselas, i_norte, i_sur, j_oeste, j_este)
        integral_z = np.zeros((z.shape[0] + 1, z.shape[1] + 1), dtype=np.int64)
        integral_n = np.zeros_like(integral_z)
        integral_z[1:, 1:] = np.cumsum(np.cumsum(np.where(dato, z, 0), axis=0, dtype=np.int64), axis=1)
        integral_n[1:, 1:] = np.cumsum(np.cumsum(dato, axis=0, dtype=np.int64), axis=1)
        f1, f2 = i_norte - i_hi[sel], i_norte - i_lo[sel] + 1
        c1, c2 = j_lo[sel] - j_oeste, j_hi[sel] - j_oeste + 1

        def rectangulo(integral):
            return integral[f2, c2] - integral[f1, c2] - integral[f2, c1] + integral[f1, c1]

        suma, cuenta = rectangulo(integral_z), rectangulo(integral_n)
        total = (i_hi[sel] - i_lo[sel] + 1) * (j_hi[sel] - j_lo[sel] + 1)
        z_media[sel] = np.where(cuenta > 0, suma / np.where(cuenta > 0, cuenta, 1), np.nan)
        frac[sel] = cuenta / total
    return pd.DataFrame({"pixel_id": catalogo["pixel_id"].to_numpy(dtype=np.int64), "z_nasadem": z_media,
                         "frac_nasadem": frac})


# ---------------------------------------------------------------------------
# Estáticos de las estaciones (acuerdo A8, NAS-10 a NAS-12)
# ---------------------------------------------------------------------------
def _texto(x: Any) -> str | None:
    if x is None or (not isinstance(x, str) and pd.isna(x)):
        return None
    return str(x)


def _celdas_por_indice(celdas, macrozona_region: Mapping[int, str]) -> dict[tuple[int, int], tuple[int, Any, Any]]:
    faltan = [c for c in COLUMNAS_CELDAS if c not in celdas.columns]
    if faltan:
        raise ValueError(f"a las celdas les faltan las columnas {faltan}")
    conocidas = set(macrozona_region.values()) | {tipos.MACROZONA_INSULAR}
    raras = sorted(set(celdas["macrozona"].dropna().astype(str)) - conocidas)
    if raras:
        raise ValueError(f"macrozonas de la grilla que no son de MACROZONA_REGION ni «insular»: {raras}")
    k_lat, k_lon = _indices_de_centros(celdas["lat"], celdas["lon"])
    salida: dict[tuple[int, int], tuple[int, Any, Any]] = {}
    for k, m, celda, macro, cod in zip(k_lat.tolist(), k_lon.tolist(), celdas["celda"].tolist(),
                                       celdas["macrozona"].tolist(), celdas["cod_comuna"].tolist()):
        if (k, m) in salida:
            raise ValueError("dos celdas con el mismo centro")
        salida[(k, m)] = (int(celda), _texto(macro), cod)
    return salida


def _texto_omm(x: Any) -> str | None:
    """El texto OMM de una estación sin espacios en los bordes; None si falta o queda vacío (NAS-12)."""
    t = _texto(x)
    t = None if t is None else t.strip()
    return t or None


def _omm(catalogo) -> list[bool | None]:
    """NAS-12: si el texto de cada estación tiene alguna cifra; None en todas si el catálogo no trae la columna o
    ninguna estación trae un indicativo (MC-62: el estrato no se forma y se declara)."""
    n = len(catalogo)
    if "omm" not in catalogo.columns:
        return [None] * n
    con = [t is not None and _CIFRA.search(t) is not None for t in map(_texto_omm, catalogo["omm"])]
    return con if any(con) else [None] * n


def info_estaciones(catalogo, celdas, teselas, umbrales, *, macrozona_region, conjuntos) -> dict:
    """``InfoEstacion`` de cada estación del catálogo de RELOJ C2, por código (acuerdo A8, NAS-12).

    ``catalogo``: el catálogo completo, con ``codigo``, ``nombre``, ``lat_txt``, ``lon_txt`` y ``alt_txt`` (y, si los
    trae, ``tipo``, ``propietario`` y ``omm``), como ``reloj_dmc.extraccion.leer_catalogo_dmc``; ``celdas``: filas de
    ``celdas.parquet``; ``teselas``: todas las ``TeselaDEM`` del conjunto de M0 que tocan la ``ventana_k3`` de alguna
    estación, porque una tesela que falta se lee como que no existe (D37, NAS-16); ``conjuntos``: código → V o V2."""
    faltan = [c for c in COLUMNAS_CATALOGO if c not in catalogo.columns]
    if faltan:
        raise ValueError(f"al catálogo le faltan las columnas {faltan}")
    teselas = tuple(teselas)
    if not all(isinstance(t, TeselaDEM) for t in teselas):
        raise TypeError("teselas lleva TeselaDEM (las de leer_tesela)")
    codigos = [str(c) for c in catalogo["codigo"]]
    if len(set(codigos)) != len(codigos) or not all(tipos.PATRON_CODIGO.fullmatch(c) for c in codigos):
        raise ValueError("códigos del catálogo repetidos o que no tienen 6 dígitos")
    por_indice = _celdas_por_indice(celdas, macrozona_region)
    omm = _omm(catalogo)
    opcional = {c: (list(map(_texto, catalogo[c])) if c in catalogo.columns else [None] * len(catalogo))
                for c in ("tipo", "propietario")}
    nan = math.nan
    salida: dict[str, tipos.InfoEstacion] = {}
    for posicion in sorted(range(len(codigos)), key=lambda p: codigos[p]):
        fila = catalogo.iloc[posicion]
        codigo = codigos[posicion]
        lat_txt, lon_txt, alt_txt = _texto(fila["lat_txt"]), _texto(fila["lon_txt"]), _texto(fila["alt_txt"])
        lat, lon = interpretar_coordenada(lat_txt, "lat"), interpretar_coordenada(lon_txt, "lon")
        alt = interpretar_coordenada(alt_txt, "alt")
        z_cat = nan if alt is None else float(alt)
        fuente = tipos.FuenteZs.CATALOGO if math.isfinite(z_cat) else tipos.FuenteZs.NASADEM
        rho = rho_km(lat_txt, lon_txt, umbrales)
        legibles = lat is not None and lon is not None
        k3_pasa, z_s, motivo, celda, macro = False, nan, None, None, None
        utm_e = utm_n = nan
        if not legibles:
            motivo = MOTIVO_COORDENADAS_ILEGIBLES
        elif not coordenadas_en_rango(lat, lon):
            motivo = MOTIVO_FUERA_DE_RANGO
        else:
            e, n = numerico.utm19s(lat, lon)
            utm_e, utm_n = float(e), float(n)
            k3_pasa, z_s = k3(lat, lon, z_cat, rho, teselas, umbrales)       # la regla literal (NAS-10, NAS-11)
            if not hay_tesela_a_rho(lat, lon, rho, teselas):
                motivo = MOTIVO_SIN_NASADEM                                    # sin prueba K3 (D37, NAS-16)
            elif not k3_pasa:
                motivo = MOTIVO_K3
            elif not math.isfinite(z_s):
                motivo = MOTIVO_SIN_Z_S
            k, m = (int(x) for x in celda_de_puntos(lat, lon)[0])
            encontrada = por_indice.get((k, m))
            if encontrada is not None:
                celda = encontrada[0]
                macro = tipos.macrozona_de_celda(encontrada[1], encontrada[2])
        salida[codigo] = tipos.InfoEstacion(
            codigo=codigo, nombre=_texto(fila["nombre"]),
            conjunto=tipos.Conjunto(conjuntos.get(codigo, tipos.Conjunto.N)).value, macrozona=macro,
            grupo=tipos.id_grupo([codigo]), omm=omm[posicion], tipo=opcional["tipo"][posicion],
            propietario=opcional["propietario"][posicion], lat_txt=lat_txt, lon_txt=lon_txt, alt_txt=alt_txt,
            lat=nan if lat is None else float(lat), lon=nan if lon is None else float(lon), z_cat=z_cat, rho_km=rho,
            k3_pasa=bool(k3_pasa), z_s=float(z_s), z_s_fuente=fuente.value, celda=celda, utm_e=utm_e, utm_n=utm_n,
            bloque="", pix0=-1, pix1=-1, pix2=-1, pix3=-1, w0=nan, w1=nan, w2=nan, w3=nan, respaldo_16km=False,
            sin_fondo=True, excluida=motivo is not None, motivo=motivo)
    return salida


def fuera_de_la_grilla(info: tipos.InfoEstacion) -> bool:
    """D34 (NAS-17): la estación entra (no está excluida) y no tiene celda. Entrena A, B y AB; no entra en C ni en
    C_est (sin estáticos) y sale de la evaluación de todos los candidatos, contada aparte."""
    return not info.excluida and info.celda is None


def declaraciones_estaciones(infos: Mapping[str, tipos.InfoEstacion]) -> dict[str, Any]:
    """Los conteos de las estaciones que se informan aparte (NAS-18; D9, D16, D34 y D37), en enteros de Python."""
    valores = [infos[c] for c in sorted(infos)]
    raros = sorted({i.motivo for i in valores} - {None, *_MOTIVOS_CONOCIDOS})
    if raros:
        raise ValueError(f"motivos de exclusión desconocidos: {raros}")
    if any(i.excluida != (i.motivo is not None) for i in valores):
        raise ValueError("una estación excluida lleva un motivo, y sólo ella (TIP-14)")
    return {
        "estaciones": len(valores),
        "excluidas": sum(1 for i in valores if i.excluida),
        "por_motivo": {m: sum(1 for i in valores if i.motivo == m) for m in _MOTIVOS_CONOCIDOS},
        "sin_nasadem_con_fondo": sum(1 for i in valores if i.motivo == MOTIVO_SIN_NASADEM and not i.sin_fondo),
        "fuera_de_la_grilla": sum(1 for i in valores if fuera_de_la_grilla(i)),
        "sin_macrozona": sum(1 for i in valores if i.macrozona is None),
    }


def tabla_estaciones(infos: Mapping[str, tipos.InfoEstacion]) -> pd.DataFrame:
    """Las ``InfoEstacion`` como ``ESQUEMA_ESTACIONES_MC``, ordenadas por código (para ``estaticas/estaciones.parquet``,
    que escribe ``salidas``), con ``declaraciones_estaciones`` en ``attrs["declaraciones"]`` (NAS-18)."""
    esquema = tipos.ESQUEMA_ESTACIONES_MC
    declaraciones = declaraciones_estaciones(infos)
    if not infos:
        df = tipos.tabla_vacia(esquema)
    else:
        filas = [dataclasses.asdict(infos[c]) for c in sorted(infos)]
        df = pd.DataFrame(filas, columns=list(esquema)).astype(dict(esquema))
        tipos.validar_esquema(df, esquema, nombre="estaciones_mc")
        df.attrs["esquema"] = esquema.version
    df.attrs["declaraciones"] = declaraciones
    return df


__all__ = ("TeselaDEM", "TeselaGHS", "interpretar_coordenada", "coordenadas_en_rango", "rho_km", "leer_tesela",
           "leer_ghs", "celda_de_puntos", "k3", "hay_tesela_a_rho", "ventana_k3", "estaticos_celdas",
           "ventana_necesaria", "estandarizar_tpi", "tpi_entra_a_estandarizar", "nasadem_en_pixeles",
           "info_estaciones", "tabla_estaciones", "fuera_de_la_grilla", "declaraciones_estaciones", "MOTIVOS",
           "MOTIVOS_SIN_COORDENADAS_K3", "MOTIVOS_FUERA_DE_Q2")
