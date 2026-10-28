"""Generadores sintéticos independientes para las pruebas S1-S16 (§9 del texto, §5 del diseño).

**No importa el paquete** (§1 del diseño) ni ``reloj_dmc``: sólo la biblioteca estándar, numpy y pandas al
importarse; netCDF4, pyarrow, rasterio y pyproj se cargan dentro de las funciones que los usan. Los esquemas de
``tipos`` que se fabrican están copiados aquí (``ESQUEMAS_COPIADOS``) y ``test_sintetico`` los compara con ``tipos``.
Lo mismo con las constantes de formato del código fijado (columnas del descargador, esquema de la política de RELOJ,
huellas): se copian y una prueba las compara con su fuente. El descargador y el adaptador llegan por argumento.

Sólo escribe en la carpeta que recibe, y la rechaza, antes de tocar el disco, si está bajo /Volumes o dentro de los
repositorios (ruta léxica primero y después la resuelta, la lección de la Enmienda 4 del reloj). Los tamaños por
omisión son pequeños: cada generador corre en segundos.

Qué fabrica cada generador (y para qué prueba):
- ``EstacionSintetica``, ``reportes_desde``, ``estacion_sintetica``, ``etiquetas_desde_utc``: los textos crudos de una
  estación por hora (S1, S2, S11, S12, S15).
- ``hoja_html``, ``html_catalogo``, ``ClienteFalsoMC``, ``GuardaFalsaMC``, ``fabricar_descarga``: el portal DMC falso y
  ``run_download`` del descargador fijado, sin red (S2, S12, S15). ``alterar_artefacto`` cambia un artefacto ya
  descargado (código QC, hora no nativa) para los abortos de S15 que el portal no puede producir.
- ``politica_reloj_sintetica``: la política de RELOJ, ``artefactos_evaluados.json.gz``, el informe con la lista K2 y el
  registro de C5 (S2; MC-40).
- ``mes_era5_netcdf``, ``horas_del_mes``, ``tp_acumulado``, ``catalogo_pixeles``, ``geopotencial_sintetico``:
  ERA5-Land en el formato real (S5, S11-S13).
- ``tesela_nasadem``, ``tesela_ghs``: teselas de elevación y de población (S3, M2a).
- ``grilla``: las tablas de ``grilla_1km`` y los pesos (S8, S6, C).
- ``verdad``: fondo + sesgo b(x, m, h) + anomalías correlacionadas; con ``anomalias=True``, las de MC-50 (S5; SIN-21).
- ``red_s6``, ``anomalias_s6``, ``campos_s6``: la red de S6 (MC-07, MC-50).
- ``series_traslado``, ``ciclo_diario_t2b_hpa``: las series de K4, con el ruido de MC-49 y las señales de la
  reducción y del horario (S4; SIN-13, SIN-20).
- ``tablas_metricas``, ``tablas_m6``: casos nombrados para la regla de decisión, el soporte y el Anexo B (S7, S16),
  tal como los lee ``decision`` (A11; SIN-14, SIN-22).
- ``sinca_sintetico``, ``huellas_sinca``: la meteorología SINCA con los dos manifiestos (§5.6, MC-10).
- ``panel_y_pliegues``: los paneles y los pliegues de la red 2 (MC-09, M6).

Lecturas propias (SIN-n), para el addendum de M1:
- SIN-1. **Portal DMC.** La hoja mensual sigue ``reloj_dmc.sintetico.html_informe`` (título «Hoja Mensual de Datos
  Estación (<código>) <Mes> de <año>», GROUP_COLUMNS, LEAF_COLUMNS y la tabla dos veces) y muestra la rejilla completa
  del mes: las horas sin reporte van con día y hora y el resto vacío (``source_empty_slots``). Formato de los números
  como el reloj: Ts, Td, TMin, TMax, QFE, QFF y RR06 con un decimal («−0.0» → «0.0»); DD y FF (nudos) enteros de
  tres cifras; HR entera. Un texto dado como ``str`` va tal cual (así se fabrican «s/p», «990» o «-005»).
- SIN-2. **Catálogo e inventario.** Los textos de coordenadas (``textos_coord``) van tal cual a «Latitud»,
  «Longitud» y «Altitud (Mts)»; por omisión, el número con hasta seis decimales. El inventario declara los elementos
  26, 28, 57, 64, 65 y 66 en los años con reportes (no QNH, 70: así un mes puede quedar completo).
- SIN-3. **Abortos que el portal no produce** (S15). ``parse_report`` siempre escribe ``source_qc = None`` y rechaza
  las horas no HH:00 y las repetidas contradictorias, así que el código QC presente, la hora no nativa y la hora
  repetida se fabrican cambiando el artefacto ya descargado (``alterar_artefacto``), con su manifiesto al día
  (sha256, bytes y filas). La dirección 990 y la rapidez negativa sí salen del portal.
- SIN-4. **Política de RELOJ.** Esquema «dmc-reloj-politica/1» con las claves y las rutas de ``reloj_dmc.politica``
  (copiadas, comparadas en la prueba): ``AP/config/meteorologia/reloj_dmc/v1/`` bajo la raíz que se recibe, con la
  política, ``artefactos_evaluados.json.gz`` (lista de ``{"artefacto_sha256", "codigo"}``) e
  ``informe_reloj_dmc.json``, que sólo trae la lista ``coordenadas_inconsistentes`` (K2, MC-19). Veredictos F(c);
  tramos «<racha>.<k>». Un tramo con ``veredicto`` None queda sin veredicto en ``estaciones[código].tramos``.
- SIN-5. **Registro de C5** (H14). Ningún código lo escribe todavía (RELOJ, Enmienda 2, E2-4). §2.1 y E2-4 dicen
  que lleva «el sha256 de la política y de ``artefactos_evaluados`` y el commit de C5»: el archivo
  ``APH/auditoria/<fecha>/meteo_combinada/registro_politica_reloj.json`` trae sólo ``schema``, ``politica_ruta``,
  ``sha256_politica``, ``artefactos_ruta``, ``sha256_artefactos``, ``commit_c5`` y ``errata_confirmada`` (None si no
  hay). Las banderas ``post_hoc`` y ``errata_post_c4`` son de la política, y ``tipos.RegistroReloj`` las junta en
  memoria. ``alterar_registro`` reemplaza campos (sha distinto…) para las negativas de S2. Pedido al coordinador:
  fijarlo con I6 y con el C5 de RELOJ.
- SIN-6. **ERA5-Land mensual** (``preparar_era5land_modelado._read_native``, ``meteo_civil_v3.leer_mes`` y
  ``_comun_modelo.leer_mes_nativo``, leídos como código): dimensiones ``time`` × ``pixel``; ``time`` int64 en
  «seconds since 1970-01-01 00:00:00 UTC», calendario proleptic_gregorian; coordenadas ``pixel_id``, ``latitude``,
  ``longitude``, ``lat_index_global``, ``lon_index_global``, ``cod_comuna`` y la escalar ``latitude_longitude``;
  variables float32 sin ``scale_factor``, ``add_offset`` ni rangos, con ``_FillValue`` NaN; atributos globales
  ``temporal_operation`` = «none; exact native UTC hours», ``spatial_resolution_degrees`` = 0.1 y ``catalog_sha256``.
  En las unidades malas de S13 (``t2m_celsius``, ``sp_hpa``, ``tp_mm``) cambian los valores y el atributo ``units``
  sigue diciendo la unidad nativa: un error no declarado, que sólo la regla de rango de §4.1 ve.
- SIN-7. **Píxeles.** ``pixel_id`` = i·3.600 + j con i = (90 − lat)/0,1 y j = (lon mód 360)/0,1, como
  ``descargar_era5land_geopotencial`` y el sintético del reloj; columnas del catálogo real (las de
  ``reloj_dmc.sintetico.catalogo_pixeles_sintetico`` sin ``valido``).
- SIN-8. **Geopotencial.** NetCDF del CDS: ``z`` float32 (valid_time, latitude, longitude) en m² s⁻², latitud
  descendente y longitud en −180..180; el derivado ``era5land_altitud_modelo_pixeles.parquet`` trae ``pixel_id``,
  ``lat_index_global``, ``lon_index_global``, ``latitude``, ``longitude``, ``z_m2_s2`` y ``z_m`` = z/9,80665, como lo
  escribe el descargador. ``corrimiento_filas`` corre la grilla del NetCDF y no la del parquet (S13).
- SIN-9. **NASADEM.** Las teselas en disco no son ``.hgt``: el descargador las guarda recortadas como GeoTIFF int16
  EPSG:4326 de 1/3.600°, con ``nodata`` −32768 y máscara interna (``tiles/NASADEM_HGT_<tesela>_<aoi>_30m.tif``). Se
  fabrica ese formato. Los centros de píxel están en múltiplos exactos de 1/3.600° (píxel-punto del HGT): la
  transformación empieza medio píxel al oeste y al norte del primer centro. I8 alinea su lector con éste.
- SIN-10. **GHS-POP.** GeoTIFF float32 de 100 m en Mollweide (ESRI:54009), ``nodata`` −200, alineado a la rejilla de
  teselas de ``pesos_poblacion`` (origen −18.041.000, 9.000.000 m); con ruta «.zip», el .zip con el .tif del mismo
  nombre adentro (se lee con /vsizip/). Es una ventana pequeña, no una tesela entera de 1.000 km.
- SIN-11. **Grilla.** Las columnas de ``celdas.parquet``, ``estaticas.parquet``, ``estaticas_lulc.parquet`` y
  ``enlaces_productos.parquet`` (sólo su esquema, leído por el coordinador; de los enlaces, sólo ERA5-Land) y de
  ``poblacion_celda_anio.parquet`` (según ``pesos_poblacion.py``). Los ids de celda son propios:
  ⌊(lat + 90)·100⌋·36.000 + ⌊(lon + 180)·100⌋; nadie debe deducir coordenadas de un id. ``estaticas_mc`` trae
  además los estáticos de M2a en ``ESQUEMA_ESTATICAS_CELDA``.
- SIN-12. **S6** (MC-07, MC-50; H10, H16). Verdad T = clima(x, t) + a(x, t), sin tendencia; fondo F = clima + β(x) +
  deriva(t), con β = −1,5 K en los valles (−71,0 ≤ lon ≤ −70,6) y deriva = d·(años desde el inicio)/10; observación =
  T desde el año de entrada de la estación. Residuo r = a − β − deriva. Las 20 históricas (2000-2024) están fuera de
  los valles; las 120 nuevas (2010-2024) en toda la región. **Paso horario por omisión**: con el paso de 3 h ninguna
  estación alcanza el 50 % de las horas UTC del año de la red constante (MC-47) y TF2 no sería evaluable, y la red de
  S6 debe darla evaluable (EMC1-2); con paso 1 h las 20 históricas forman la red constante de r2000_2025 y A tiene 24
  horas UTC con hueco 1 h. Anomalías con correlación exp(−d/L), L = 100 km, σ = 1,5 K y un AR(1) horario con
  τ = ``tau_h`` = 48 h (MC-50 no fija τ: es un parámetro, con el valor por omisión elegido aquí, y va con la pregunta
  al autor sobre los parámetros de S6). Cada mes se genera aparte, con su propia subsecuencia de la semilla, y se le
  resta la media en cada punto, así que la media es 0 en cada punto × mes × año (float64). Representación liviana:
  ``red_s6`` guarda las estaciones, las celdas, la geometría y los parámetros; ``anomalias_s6`` y ``campos_s6`` dan los
  campos por mes o por año, iguales se pidan como se pidan. 25 comunas con 4 celdas cada una.
- SIN-13. **S4** (MC-49, D42). Estructura del ruido, para el addendum: T2b = QFE − p_F lleva un AR(1) diario (un valor
  por día UTC) de σ = 0,7 hPa y τ = 2 días más ruido blanco horario de 0,3 hPa; z_impl lleva ruido blanco horario de
  σ = 5 m (``SIGMA_Z_IMPL_M``), sin componente diaria, independiente del de T2b y del de Ts (MC-49 sólo da σ; se lee
  como ruido horario independiente, que es la estructura que ya tenía la ola 1: así las tasas de P28 medidas por I9 y
  su revisor siguen valiendo). Con ≈ 30 valores por mes y hora, ese ruido deja ≈ 0,25 m en M(j), muy por debajo de
  10 m, así que los falsos quiebres de S4 son de T2b. Un solo generador por serie (semilla, «traslado», tipo y
  altitud), en orden fijo: Ts, el proceso sinóptico del fondo, T2b y, al final, z_impl. Traslado: QFE de la nueva
  altitud y QFF reducida con la altitud nueva; barómetro: QFE y QFF multiplicados por el mismo factor (z_impl igual);
  reducción estándar → real y horario, con las señales de SIN-20. Cambio el 2015-01-01; 2012-2017.
- SIN-14. **Casos de la regla** (``tablas_metricas``, ``tablas_m6``; H11, H12, A11). Cada caso trae su resultado
  esperado (``esperado``), calculado a mano con el Anexo A y §6: CD 1,10× + 0,05 K, + 0,5 puntos (HR), + 0,05 m/s o
  hPa; EX + 0,25 K (T), + 0,40 K (Td), + 2,0 puntos (HR) y + 0,30 m/s (rapidez), sin EX en p; MZ, nivel y anomalía
  1,15×; MZ sólo en las macrozonas con ≥ 10 estaciones evaluables (``n_estaciones`` del agregado, TIP-10) y publicables
  en P1, en P2 y en el agregado (MC-61, DEC-4). Variables (DEC-1): en (T, Td) ambiental, S y MZ en «T» y «HR», CD en T
  y HR, EX en T y Td; en lo agudo, S, EX, nivel y MZ en «temp_media» y «hr_media» y CD en T y HR; en (u, v), S en «uv»
  (RMSE vectorial), MZ en «uv» y en la rapidez (D43) y CD y EX en «rapidez»; en p, todo en «p»; en lo crónico, S, CD,
  anomalía y MZ en «T» y EX en «temp_media». Cada caso aísla una regla: una sola compuerta fallida (CD en T y en HR, EX
  en T, Td y hr_media, MZ en T, HR, temp_media, la rapidez y la T crónica, TF1 en Td, TF2 «falla», nivel, anomalía), E0
  sin un candidato (deriva o finitud), MZ que no aplica (8 estaciones; 6 en la familia crónica sin MZ), que no se
  publica en ninguna partición o sólo en P2, E1 vacío, empate y las reglas crónicas. La TF de A, C y C_est es 0 en
  todos los casos (§5.7, «artefacto 0 por construcción»; ``CERO_POR_CONSTRUCCION``): pedir una falla suya es un error.
  En «e1_vacio» cada candidato falla una compuerta (A CD en T, B EX en T, AB TF1 en Td, C CD en HR) y el paso 4 elige B
  porque AB, el de menor S, falla TF. Las notas siguen DEC-10: «regla sin ganador» si y sólo si E1 está vacío, también
  con la regla crónica («cronica_mixta»), en el orden de ``ORDEN_NOTAS``. ``esperado["conjunto"]`` es el conjunto del
  que sale el ganador (E1, el paso 4 o el 5), el mismo en que cada réplica elige el suyo para el intervalo de ΔS
  (D46). Las réplicas traen el S del grupo (S_par en (T, Td), ``ESQUEMA_REPLICAS``) de los de E0. Las tablas van tal
  como las lee ``decision`` (A11): ``test_sintetico`` corre cada caso con ``decidir_combinacion`` sin cambiarlas.
- SIN-15. **SINCA** (``descargar_sinca_meteorologia.py`` como código). Archivos
  ``<PARAM>/<REG>_<EST>_<PARAM>_<macro>_<desde>_<hasta>.csv``: una cabecera que empieza con «FECHA» (su texto exacto
  no está en el código: se eligió «FECHA (YYMMDD);HORA (HHMM);REGISTRO;») y filas «AAMMDD;HHMM;valor;» con coma
  decimal, de la 01:00 del primer día a las 23:00 del último (24·días − 1). Manifiestos con ``CAMPOS_MANIFIESTO``.
  El segundo manifiesto (``…_20261024b``) usa las mismas columnas y trae además PRES, RAIN y GLOB.
- SIN-16. **Red 2** (H15). El manifiesto real de la red ampliada se llama ``pliegues_v2_red2.json``
  (``v2/pliegues_red2_v2.py``); el diseño lo llama «``pliegues_v2.json`` de ese bloque». Lleva ``schema`` =
  «airpollution.modelo-1km-v2.pliegues.v2», ``schema_red2`` = «airpollution.modelo-1km-v2.pliegues-red2.v1», ``bloque``
  (el de ``red_ampliada_v2.BLOQUE``), ``parametros``, ``estaciones`` (con ``lat``, ``lon``, ``celda`` y el bloque de
  BLQ-75 «E<ix>N<iy>») y ``contaminantes.<pol>.panel`` y ``.protocolos.<LRO|BLQ-75>.pliegues``; ``huella_pliegues`` es
  la de ``pliegues_v2.huella_pliegues``: el sha256 del JSON canónico de v2 de ``CLAVES_HUELLA`` (schema, parametros,
  estaciones y contaminantes). Todo copiado del código y comparado en la prueba. El panel trae ``estacion``,
  ``ts_utc`` (sin zona, como el v1), ``obs``, ``n``, ``version``, ``celda``, ``region_sinca``, ``lat_est``,
  ``lon_est``, ``anio`` y ``pob_dens``.
- SIN-17. **NMB del Anexo B** (H12). ``nmb_c`` y ``nmb_otra`` van en porcentaje, como los da
  ``v2/decision_v2.py`` (``nmb_candidato_pct``, ``MARGEN_NMB_PP = 1.0``): la condición 7 suma 1 punto, no 0,01. Los
  casos ``borde_c7`` (|3,0| ≤ |−2,0| + 1) y ``c7_en_puntos`` (|−2,5| ≤ |2,0| + 1, que fallaría con 0,01) lo aíslan.
- SIN-18. **Sólo carpetas temporales** (H13). Toda escritura exige que el destino esté bajo ``tempfile.gettempdir()``
  resuelto. Se mira primero la ruta léxica (/Volumes y los repositorios, sin tocar el disco); después se resuelven los
  enlaces componente a componente, mirando antes de consultar cada componente que no caiga bajo /Volumes.
- SIN-19. **Macrozonas** (TIP-8, D9, D16). ``grilla`` usa ``MACROZONA_REGION`` y ``MACROZONA_CODIGO`` de
  ``_comun_modelo`` (copiados y comparados por AST con su huella a83c0384…). ``celdas_sin_comuna`` deja las últimas
  celdas con ``cod_comuna = 0``, región 0 y macrozona «sin_region» (5), para las pruebas de D9. La grilla sintética
  no trae celdas «insular» (D16 las trata como D9); se suman si I8 o I12 las piden.
- SIN-20. **Señales de S4** (D42; hallazgo 4 del crítico de la ola 2). Sin ellas las pruebas de reducción y de horario
  pasaban sin probar nada. Van, por omisión, sólo en su tipo; con ``dt_clima_k = 0`` y ``ciclo_diario_m = 0`` la serie
  es, bit a bit, la de la ola 1, y las de los demás tipos no cambian (``test_sintetico`` guarda sus huellas).
  - **Reducción estándar → real.** La estación es ``DT_CLIMA_REDUCCION_K`` = 10 K más cálida que la atmósfera
    estándar a su altitud (Ts y su T̄ de §2.5 suben 10 K; la T̄ de la reducción estándar, 288,15 − 0,0065·z/2, no lo
    ve). Antes del cambio z_impl = z·T̄/T̄_std, después z_impl = z: salta −z·ΔT/T̄_std, −17,5, −35 y −89 m a 500, 1.000
    y 2.500 m, sobre el umbral de T2a en las tres, sin tocar T2b. K4 debe ver un quiebre de T2a sin T2b («cambio del
    método de reducción», que sólo se informa) y no un traslado. Una estación 10 K más cálida es común en altura en el
    norte (Calama, ≈ 2.300 m, ≈ +12 K) y exigente a 500 m: es el valor que da la señal en las tres altitudes. Antes del
    cambio z_impl hereda además el ciclo anual y el diario de Ts (z·6/T̄ y z·5/T̄), que la reducción estándar no sigue.
  - **Horario diurno → 24 h.** z_impl lleva un ciclo diario de ``CICLO_HORARIO_M`` = 50 m con máximo a las 19 UTC (la
    reducción de la estación usa una temperatura con otro ciclo diario que la Ts de §2.5, por ejemplo la media de
    12 h) y T2b el de un desplazamiento vertical equivalente, −50·g·p̄/(R·T̄) hPa (``ciclo_diario_t2b_hpa``: 5,7, 5,4 y
    4,6 hPa a 500, 1.000 y 2.500 m; por ejemplo una brisa de valle que ERA5-Land no resuelve). Como se observan sólo
    las 11-23 UTC antes del cambio, una media diaria ingenua salta ≈ −25 m en z_impl y + 2,9, + 2,8 y + 2,2 hPa en T2b,
    coherentes como un traslado (Δz_b ≈ Δz_a): es el caso más difícil, y sólo H*(k) de §2.5 evita el quiebre. Restringidas
    a las mismas horas UTC, las medias de los dos lados difieren en < 0,2 m y < 0,1 hPa. La amplitud no es una
    estimación de la DMC: es la que da poder a la prueba en las tres altitudes, y va al addendum con el ruido de SIN-13.
- SIN-21. **Anomalías de S5** (MC-50, D42). ``verdad(…, anomalias=True)`` o «MC-50» da las de MC-50 (``ANOMALIAS_MC50``:
  σ = 1,5 K, L = 100 km, τ = 48 h y media 0 en cada punto × mes × año, restada en float64), con la semilla que recibe
  (la del protocolo, ``SEMILLA`` = 20261023, D42). Un diccionario cambia sólo las claves que trae y toma las demás de
  MC-50 (la prueba informativa sin la media 0 pasa ``{"media_cero": False}``); una clave desconocida es un error. Antes
  de la ola 3 las claves que faltaban valían σ = 1, τ = 24 h y sin media 0: ningún llamador dependía de eso (las pruebas
  de I9 pasan las cuatro claves con los valores de MC-50 y su serie no cambia).
- SIN-22. **Particiones de la validación publicada** (MC-61, A11). Cada fila de ``validacion`` va en P1, P2 y el
  agregado, en el estrato nacional y en la macrozona: el agregado lleva las métricas de la base del caso (las que lee
  la regla, DEC-2) y P1 y P2 su reparto, x·√(1 − ε_c) y x·√(1 + ε_c), con ε = +0,10 (A), −0,10 (B), +0,20 (AB) y −0,20
  (C y C_est), así x² = (x_P1² + x_P2²)/2, como un RMSE con las mismas evaluaciones en cada partición. El reparto
  depende del candidato a propósito: una regla que leyera P1 o P2 en lugar del agregado cambiaría de resultado (en los
  24 casos con P1 y en 20 con P2; ``test_sintetico`` lo comprueba). n_evaluaciones: 40 nacionales por partición y 80
  en el agregado; en la macrozona, n por partición y 2n en el agregado, con n_estaciones = n en las tres. ``publicable``:
  siempre en lo nacional (MC-61); en la macrozona, por partición (TIP-15), igual para todos los candidatos.
Depende de: biblioteca estándar, numpy, pandas (y, al llamarse, netCDF4, pyarrow, rasterio y pyproj).
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import html
import io
import json
import math
import os
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import pandas as pd

UTC = timezone.utc
SEMILLA_POR_OMISION = 20261023

# ---------------------------------------------------------------------------
# Esquemas copiados de tipos (camino propio; test_sintetico los compara)
# ---------------------------------------------------------------------------
_F4, _F8 = "float32", "float64"
LULC = ("lulc_urbano", "lulc_cultivo", "lulc_bosque", "lulc_matorral_pastizal", "lulc_desnudo", "lulc_agua",
        "lulc_nieve_hielo")

ESQUEMA_VALIDACION_PUB = {
    "uso": "string", "grupo": "string", "variable": "string", "candidato": "string", "particion": "string",
    "S": _F8, "CD": _F8, "EX": _F8, "nivel": _F8, "anomalia": _F8, "estrato": "string", "valor_estrato": "string",
    "n_evaluaciones": "int32", "n_estaciones": "int32", "publicable": "bool",
}
ESQUEMA_REPLICAS = {"replica": "int32", "candidato": "string", "S": _F8}
ESQUEMA_TF = {
    "candidato": "string", "uso": "string", "variable": "string", "prueba": "string", "media_pond": _F8,
    "p95_pond": _F8, "cota_media": _F8, "cota_p95": _F8, "resultado": "string", "regla_red": "string",
    "n_red": "int32",
}
ESQUEMA_EVALUACIONES = {
    "codigo": "string", "particion": "string", "pliegue": "string", "candidato": "string", "uso": "string",
    "variable": "string", "n_horas": "int32", "n_dias": "int32", "n_anios": "int32",
    "mse_h": _F8, "mae_h": _F8, "sesgo_h": _F8, "mse_dia": _F8, "mse_estrato": _F8, "mse_anual_neto": _F8,
    "mse_anomalia": _F8, "cd": _F8, "ex": _F8, "frac_sin_soporte": _F8,
}
ESQUEMA_COMPARACION_M6 = {
    "contaminante": "string", "sentido": "string", "protocolo": "string",
    "delta_r2": _F8, "ic_bajo": _F8, "ic_alto": _F8,
    "segunda_prueba_coincide": "bool", "supera_ruido": "bool", "consistencia_e2": "bool", "sobrevive_bloque": "bool",
    "signo_sin_ponderar": "bool", "signo_log": "bool", "decision_sigma2": "bool",
    "nmb_c": _F8, "nmb_otra": _F8,
}
ESQUEMA_ESTATICAS_CELDA = {
    "celda": "int64", "z_media": _F8, "z_poblada": _F8, "z_poblada_es_media": "bool", "frac_dato": _F8,
    "tpi1": _F8, "tpi5": _F8, "tpi1_truncado": "bool", "tpi5_truncado": "bool", "pendiente_deg": _F8,
    "log_dist_costa": _F8, **{c: _F8 for c in LULC}, "lat": _F8, "macrozona_cod": "int8", "cod_comuna": "int32",
}
# nombre del esquema en tipos → (versión, columnas)
ESQUEMAS_COPIADOS = {
    "validacion_pub": ("meteo-combinada-validacion-pub/1", ESQUEMA_VALIDACION_PUB),
    "tf": ("meteo-combinada-tf/1", ESQUEMA_TF),
    "evaluaciones": ("meteo-combinada-evaluaciones/1", ESQUEMA_EVALUACIONES),
    "comparacion_m6": ("meteo-combinada-comparacion-m6/1", ESQUEMA_COMPARACION_M6),
    "estaticas_celda": ("meteo-combinada-estaticas-celda/1", ESQUEMA_ESTATICAS_CELDA),
    "replicas": ("meteo-combinada-replicas/1", ESQUEMA_REPLICAS),
}


def _tabla(filas: Sequence[Mapping[str, Any]], esquema: Mapping[str, str], version: str | None = None) -> pd.DataFrame:
    """DataFrame con exactamente las columnas y los tipos del esquema (y su versión en ``attrs``)."""
    if filas:
        df = pd.DataFrame([{c: f.get(c) for c in esquema} for f in filas], columns=list(esquema))
    else:
        df = pd.DataFrame({c: pd.Series(dtype=t) for c, t in esquema.items()})
    df = df.astype(dict(esquema))
    if version:
        df.attrs["esquema"] = version
    return df


def _version(nombre: str) -> str:
    return ESQUEMAS_COPIADOS[nombre][0]


# ---------------------------------------------------------------------------
# Constantes de formato copiadas del código fijado (test_sintetico las compara con su fuente)
# ---------------------------------------------------------------------------
# descargar_meteo_chile_horaria.py (578fa26e…)
COLUMNAS_CRUDAS = (
    "day", "hour", "wind_direction_instant", "wind_speed_instant", "Ts", "Td",
    "TMin", "TMax", "relative_humidity", "WW", "VV", "visibility_reigning",
    "visibility_minimum", "QFE", "QFF", "QNH", "N", "Nh", "CL", "CM", "CH",
    "Hs1", "RR06",
)
COLUMNAS_TEXTO = COLUMNAS_CRUDAS[2:]               # los 21 textos de una hora, sin día ni hora
CABECERAS_CATALOGO = ("Código Nacional", "Nombre", "Latitud", "Longitud", "Altitud (Mts)", "Fecha Creación",
                      "Tipo", "Región")
ELEMENTOS_INVENTARIO = (26, 28, 57, 64, 65, 66)     # SIN-2
URL_FALSA = "https://example.invalid/sintetico"
_FORMATO = {"wind_direction_instant": "e3", "wind_speed_instant": "e3", "Ts": "d1", "Td": "d1", "TMin": "d1",
            "TMax": "d1", "relative_humidity": "e", "QFE": "d1", "QFF": "d1", "QNH": "d1", "RR06": "d1"}

# reloj_dmc.politica, tablas y fijados (SIN-4)
ESQUEMA_POLITICA_RELOJ = "dmc-reloj-politica/1"
CLAVES_POLITICA_RELOJ = ("schema", "post_hoc", "errata_post_c4", "ajuste_documental", "protocolo", "configuracion",
                         "informe", "artefactos_evaluados", "adaptador_sha256", "interprete", "transiciones_sha256",
                         "politicas_reloj", "estaciones")
RUTA_PUBLICACION_RELOJ = "config/meteorologia/reloj_dmc/v1"
ARCHIVO_POLITICA = "politica_reloj_dmc.json"
ARCHIVO_INFORME = "informe_reloj_dmc.json"
ARCHIVO_ARTEFACTOS = "artefactos_evaluados.json.gz"
RUTA_PROTOCOLO_RELOJ = "scripts_modelo_1km/reloj_dmc/PROTOCOLO_RELOJ_DMC.md"
RUTA_CONFIGURACION_RELOJ = "config/meteorologia/reloj_dmc_v1.json"
SHA_ADAPTADOR = "f61559eab281846a4935eb1ea66217e039ff37a727833bf8fcaa7a774b776754"
SHA_ANEXO_A_RELOJ = "8ea58b788ad6d8e236c5dae5f749a7fc7fe837cb2e34cb947e9904cf8f345a33"   # tablas.SHA_ANEXO_A
SHA_DESCARGADOR = "578fa26eea5b4ac4733c56aaf08e9b7b8904595fb8447dd54feb838642612120"
# Registro de C5 (SIN-5)
ESQUEMA_REGISTRO_C5 = "meteo-combinada-registro-politica-reloj/1"
FECHA_C5_SINTETICA = "20261101"
RUTA_REGISTRO_C5 = "auditoria/{fecha}/meteo_combinada/registro_politica_reloj.json"

# ERA5-Land (SIN-6)
VARIABLES_ERA5L = ("t2m", "d2m", "sp", "u10", "v10", "tp")
UNIDADES_ERA5L = {"t2m": "K", "d2m": "K", "sp": "Pa", "u10": "m s-1", "v10": "m s-1", "tp": "m"}
UNIDADES_TIEMPO_ERA5L = "seconds since 1970-01-01 00:00:00 UTC"
CALENDARIO_ERA5L = "proleptic_gregorian"
OPERACION_TEMPORAL_ERA5L = "none; exact native UTC hours"
UNIDADES_MALAS = ("nativas", "t2m_celsius", "sp_hpa", "tp_mm")
RESOLUCION_ERA5L = 0.1
_COLUMNAS_LON_GLOBAL = 3600
COLUMNAS_CATALOGO_PIXELES = ("pixel_id", "latitude", "longitude", "cell_west", "cell_east", "cell_south",
                             "cell_north", "cod_comuna", "territorio", "lat_index_global", "lon_index_global")
G0 = 9.80665
R_SECO = 287.05
KELVIN = 273.15
R_TIERRA_KM = 6371.0

# NASADEM y GHS-POP (SIN-9, SIN-10)
NASADEM_RES = 1.0 / 3600.0
NASADEM_NODATA = -32768
GHS_X0, GHS_Y0, GHS_LADO_TESELA, GHS_PIXEL = -18_041_000.0, 9_000_000.0, 1_000_000.0, 100.0
GHS_NODATA = -200.0
CRS_GHS = "ESRI:54009"

# SINCA (SIN-15): descargar_sinca_meteorologia.py
CAMPOS_MANIFIESTO_SINCA = [
    "region", "estacion", "nombre", "parametro", "variable", "macro_ficha",
    "macro_exportada", "altura_ficha", "unidad_ficha", "instrumento_ficha",
    "desde_ficha", "hasta_ficha", "desde", "hasta", "ruta_relativa", "bytes",
    "sha256", "filas", "filas_con_observacion", "filas_no_numericas",
    "primera_observacion", "ultima_observacion", "minimo", "maximo",
    "url_fuente", "accion", "ficha_sha256", "config_estaciones_sha256",
    "marca_temporal", "politica_temporal_sha256", "script_version",
    "script_sha256", "registrado_utc",
]
CAMPOS_FALTANTES_SINCA = [
    "region", "estacion", "nombre", "parametro", "macro_ficha",
    "macro_exportada", "desde", "hasta", "motivo", "url_fuente", "registrado_utc",
]
CABECERA_SINCA = "FECHA (YYMMDD);HORA (HHMM);REGISTRO;"
SUFIJO_SEGUNDO_MANIFIESTO = "_20261024b"
POLITICA_TEMPORAL_SHA = "41018e4c066d9e30b5ba0b1ff92d47eeb47bab1984b5b8c45a778939359ac61c"
_PARAMETROS_SINCA = {"TEMP": ("temperatura", "°C"), "RHUM": ("humedad_relativa", "%"),
                     "WSPD": ("rapidez_viento", "m/s"), "WDIR": ("direccion_viento", "°"),
                     "PRES": ("presion", "hPa"), "RAIN": ("precipitacion", "mm"), "GLOB": ("radiacion_global", "W/m2")}

# Red 2 (SIN-16): v2/pliegues_v2.py, v2/pliegues_red2_v2.py y v2/red_ampliada_v2.py
ESQUEMA_PLIEGUES_V2 = "airpollution.modelo-1km-v2.pliegues.v2"
ESQUEMA_PLIEGUES_RED2 = "airpollution.modelo-1km-v2.pliegues-red2.v1"
NOMBRE_PLIEGUES_RED2 = "pliegues_v2_red2.json"
CLAVES_HUELLA_PLIEGUES = ("schema", "parametros", "estaciones", "contaminantes")
BLOQUE_RED_AMPLIADA = {"texto": "auditoria/20261024/sinca_al_modelo/ENMIENDA_2_BLOQUE_RED_AMPLIADA.md (repositorio de salud)",
                       "sha256": "274ebae06bee8eeeb7470a650ce0539af751577d292513b8198cdec7c159094b", "commit": "f2c6cfc"}
ETIQUETA_BLQ = "E{ix:03d}N{iy:03d}"
EQUIVALENCIAS_LRO = {"RXVI": "RVIII"}

# _comun_modelo.py (a83c0384…; SIN-19): región → macrozona y macrozona → código (el de celdas.parquet).
MACROZONA_REGION = {15: "norte_grande", 1: "norte_grande", 2: "norte_grande",
                    3: "norte_chico", 4: "norte_chico",
                    5: "centro", 13: "centro", 6: "centro", 7: "centro",
                    8: "sur", 16: "sur", 9: "sur", 14: "sur", 10: "sur",
                    11: "austral", 12: "austral", 0: "sin_region"}
MACROZONA_CODIGO = {"norte_grande": 0, "norte_chico": 1, "centro": 2, "sur": 3,
                    "austral": 4, "sin_region": 5, "insular": 6}
COLUMNAS_PANEL_RED2 = ("estacion", "ts_utc", "obs", "n", "version", "celda", "region_sinca", "lat_est", "lon_est",
                       "anio", "pob_dens")


# ---------------------------------------------------------------------------
# Escritura sólo en carpetas temporales
# ---------------------------------------------------------------------------
def _lexica(ruta) -> Path:
    return Path(os.path.normpath(os.path.abspath(os.fspath(ruta))))


def _bajo(ruta: Path, raiz: Path) -> bool:
    return ruta == raiz or raiz in ruta.parents


def _repositorios() -> tuple[Path, Path]:
    ap = Path(__file__).resolve().parents[2]
    return ap, ap.parent / "Air-Pollution-Health-Chile"


def _en_volumes(ruta: Path) -> bool:
    """/Volumes o debajo, sin distinguir mayúsculas (APFS)."""
    return len(ruta.parts) >= 2 and ruta.parts[0] == "/" and ruta.parts[1].casefold() == "volumes"


def _exigir_fuera(r: Path) -> None:
    if _en_volumes(r):
        raise ValueError("los datos sintéticos nunca se escriben bajo /Volumes")
    for repo in _repositorios():
        if _bajo(r, repo) or _bajo(r, Path(os.path.realpath(repo))):
            raise ValueError("los datos sintéticos nunca se escriben en los repositorios")


def _resolver_sin_volumes(lexica: Path, profundidad: int = 0) -> Path:
    """Resuelve los enlaces simbólicos componente a componente. Antes de consultar un componente mira si cae bajo
    /Volumes; si cae, lanza ValueError sin tocarlo."""
    if profundidad > 40:
        raise ValueError("demasiados enlaces simbólicos al resolver la ruta")
    actual = Path(lexica.anchor or "/")
    for parte in lexica.parts[1:]:
        candidato = actual / parte
        if _en_volumes(candidato):
            raise ValueError("los datos sintéticos nunca se escriben bajo /Volumes")
        if os.path.islink(candidato):
            enlace = os.readlink(candidato)
            nuevo = _lexica(enlace if os.path.isabs(enlace) else candidato.parent / enlace)
            if _en_volumes(nuevo):
                raise ValueError("los datos sintéticos nunca se escriben bajo /Volumes (la ruta lleva allí por un enlace)")
            actual = _resolver_sin_volumes(nuevo, profundidad + 1)
        else:
            actual = candidato
    return actual


def carpeta_temporal() -> Path:
    """``tempfile.gettempdir()`` resuelta (SIN-18)."""
    return _resolver_sin_volumes(_lexica(tempfile.gettempdir()))


def destino_temporal(ruta) -> Path:
    """La ruta léxica, si está bajo la carpeta temporal del sistema y no bajo /Volumes ni en los repositorios (SIN-18).

    La léxica se mira primero, sin tocar el disco; después se resuelve componente a componente sin consultar nada bajo
    /Volumes, para atrapar un enlace que lleve a /Volumes, a un repositorio o fuera de la carpeta temporal."""
    lexica = _lexica(ruta)
    _exigir_fuera(lexica)
    resuelta = _resolver_sin_volumes(lexica)
    _exigir_fuera(resuelta)
    if not _bajo(resuelta, carpeta_temporal()):
        raise ValueError("los datos sintéticos sólo se escriben bajo la carpeta temporal del sistema (tempfile)")
    return lexica


def _escribir(ruta, datos: bytes) -> str:
    destino = destino_temporal(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(datos)
    return hashlib.sha256(datos).hexdigest()


def _json_canonico(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _rng(semilla: int, *partes: str) -> np.random.Generator:
    """Generador por subsecuencia: la semilla y la huella de una etiqueta propia (el orden de llamada no importa)."""
    huella = int.from_bytes(hashlib.sha256("/".join(("sintetico", *partes)).encode("utf-8")).digest()[:8], "big")
    return np.random.default_rng(np.random.SeedSequence([int(semilla), huella]))


def _haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl = np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R_TIERRA_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def _p_std(z):
    return 1013.25 * (1 - 2.25577e-5 * np.asarray(z, dtype=np.float64)) ** 5.25588


# ---------------------------------------------------------------------------
# Estaciones y textos crudos (SIN-1)
# ---------------------------------------------------------------------------
def _texto_numero(x: float) -> str:
    t = f"{float(x):.6f}".rstrip("0").rstrip(".")
    return "0" if t in ("", "-0") else t


@dataclass(frozen=True, eq=False)
class EstacionSintetica:
    """Una estación del portal falso: coordenadas, sus textos de catálogo y los textos crudos por hora.

    ``reportes``: columna ``L`` (datetime64[ns] ingenuo, la etiqueta de la fuente) y los 21 textos de
    ``COLUMNAS_TEXTO`` (cadenas; «» = celda vacía), una fila por etiqueta con algún reporte.
    """
    codigo: str
    lat: float
    lon: float
    alt_m: float
    textos_coord: tuple
    reportes: Any


def _texto_celda(valor: Any, formato: str | None) -> str:
    if isinstance(valor, str):
        return valor
    if valor is None:
        return ""
    v = float(valor)
    if v != v:
        return ""
    if formato == "d1":
        t = f"{v:.1f}"
        return "0.0" if t == "-0.0" else t
    if formato == "e3":
        return f"{int(round(v)):03d}"
    return f"{int(round(v)):d}"


def reportes_desde(L, **columnas) -> pd.DataFrame:
    """Textos crudos por hora: ``L`` (etiquetas ingenuas) y, por columna de ``COLUMNAS_TEXTO``, un valor o una
    sucesión (números, que se escriben como el portal, o textos, que van tal cual; NaN o None = vacío)."""
    etiquetas = pd.DatetimeIndex(pd.to_datetime(list(L) if not isinstance(L, (pd.Index, np.ndarray)) else L))
    if etiquetas.tz is not None:
        raise ValueError("las etiquetas de la fuente son ingenuas (sin zona)")
    if etiquetas.has_duplicates:
        raise ValueError("etiquetas repetidas: el portal muestra una sola fila por etiqueta")
    ajenas = sorted(set(columnas) - set(COLUMNAS_TEXTO))
    if ajenas:
        raise ValueError(f"columnas que no son del portal: {ajenas}")
    n = len(etiquetas)
    datos: dict[str, Any] = {"L": etiquetas.astype("datetime64[ns]")}
    for c in COLUMNAS_TEXTO:
        v = columnas.get(c)
        if v is None:
            datos[c] = [""] * n
            continue
        serie = list(v) if isinstance(v, (list, tuple, np.ndarray, pd.Series, pd.Index)) else [v] * n
        if len(serie) != n:
            raise ValueError(f"{c}: {len(serie)} valores para {n} etiquetas")
        datos[c] = [_texto_celda(x, _FORMATO.get(c)) for x in serie]
    df = pd.DataFrame(datos).sort_values("L", kind="stable").reset_index(drop=True)
    return df.astype({c: "string" for c in COLUMNAS_TEXTO})


def estacion_sintetica(codigo: str, lat: float, lon: float, alt_m: float, L, *, textos_coord: tuple | None = None,
                       **columnas) -> EstacionSintetica:
    """Una ``EstacionSintetica`` con sus reportes (``reportes_desde``) y, por omisión, los textos del número."""
    if not (isinstance(codigo, str) and len(codigo) == 6 and codigo.isdigit()):
        raise ValueError("el código DMC tiene 6 dígitos")
    textos = textos_coord or (_texto_numero(lat), _texto_numero(lon), _texto_numero(alt_m))
    return EstacionSintetica(codigo, float(lat), float(lon), float(alt_m), tuple(textos), reportes_desde(L, **columnas))


def etiquetas_desde_utc(u, minutos: int) -> np.ndarray:
    """Camino propio de S12 (como RELOJ §8): la etiqueta ingenua L = u + c, con c = ``minutos`` (−240 → UTC−4)."""
    u64 = np.asarray(pd.DatetimeIndex(pd.to_datetime(u, utc=True)).tz_convert("UTC").tz_localize(None),
                     dtype="datetime64[ns]")
    return u64 + np.timedelta64(int(minutos), "m")


def horas_de_la_rejilla(anio: int, mes: int) -> pd.DatetimeIndex:
    """Todas las etiquetas HH:00 del mes del portal (la rejilla completa)."""
    inicio = pd.Timestamp(anio, mes, 1)
    return pd.date_range(inicio, inicio + pd.offsets.MonthBegin(1), freq="h", inclusive="left")


def filas_del_mes(estacion: EstacionSintetica, anio: int, mes: int) -> list[list[str]]:
    """Las filas de 23 textos de la hoja del mes: la rejilla completa, con los reportes donde los hay (SIN-1)."""
    r = estacion.reportes.set_index("L")
    filas = []
    for t in horas_de_la_rejilla(anio, mes):
        textos = list(r.loc[t, list(COLUMNAS_TEXTO)].astype(str)) if t in r.index else [""] * len(COLUMNAS_TEXTO)
        filas.append([f"{t.day:02d}", f"{t.hour:02d}:00", *textos])
    return filas


def hoja_html(codigo, anio, mes, filas_textos, descargador) -> str:
    """Hoja mensual DMC en el formato de ``reloj_dmc.sintetico.html_informe``: título, GROUP_COLUMNS, LEAF_COLUMNS y
    la tabla dos veces (el portal muestra cada fila dos veces)."""
    if tuple(descargador.RAW_COLUMNS) != COLUMNAS_CRUDAS:
        raise ValueError("RAW_COLUMNS del descargador distintas de las del generador")
    e = html.escape
    for fila in filas_textos:
        if len(fila) != len(COLUMNAS_CRUDAS):
            raise ValueError(f"cada fila lleva {len(COLUMNAS_CRUDAS)} textos")
    cabecera = "<tr>" + "".join(f"<th>{e(x)}</th>" for x in descargador.GROUP_COLUMNS) + "</tr>"
    cabecera += "<tr>" + "".join(f"<td>{e(x)}</td>" for x in descargador.LEAF_COLUMNS) + "</tr>"
    cuerpo = "".join("<tr>" + "".join(f"<td>{e(x)}</td>" for x in fila) + "</tr>" for fila in filas_textos)
    tabla = "<table>" + cabecera + cuerpo + "</table>"
    titulo = (f'<div id="cabezera">Hoja Mensual de Datos Estación ({codigo}) '
              f"{descargador.MONTH_NAMES[int(mes) - 1]} de {int(anio)}</div>")
    return titulo + tabla + tabla


def _metadatos(est: EstacionSintetica) -> dict[str, str]:
    lat, lon, alt = est.textos_coord
    return {"Código Nacional": est.codigo, "Nombre": f"Estación sintética {est.codigo}", "Latitud": lat,
            "Longitud": lon, "Altitud (Mts)": alt, "Fecha Creación": "01-01-2000", "Tipo": "Automática",
            "Región": "Metropolitana"}


def _por_codigo(estaciones: Sequence[EstacionSintetica]) -> dict[str, EstacionSintetica]:
    salida: dict[str, EstacionSintetica] = {}
    for est in estaciones:
        if est.codigo in salida:
            raise ValueError(f"código repetido entre las estaciones: {est.codigo}")
        salida[est.codigo] = est
    return salida


def html_catalogo(estaciones: Sequence[EstacionSintetica]) -> str:
    e = html.escape
    filas = "".join("<tr>" + "".join(f"<td>{e(_metadatos(s)[h])}</td>" for h in CABECERAS_CATALOGO) + "</tr>"
                    for _, s in sorted(_por_codigo(estaciones).items()))
    return "<table><tr>" + "".join(f"<th>{e(h)}</th>" for h in CABECERAS_CATALOGO) + "</tr>" + filas + "</table>"


def inventario(est: EstacionSintetica) -> list[dict]:
    """Ficha de elementos (SIN-2): los años con reportes."""
    if est.reportes.empty:
        return []
    anios = pd.DatetimeIndex(est.reportes["L"]).year
    a0, a1 = int(anios.min()), int(anios.max())
    return [{"element_id": e, "first_year": a0, "last_year": a1, "source_count": int(len(est.reportes))}
            for e in ELEMENTOS_INVENTARIO]


class ClienteFalsoMC:
    """Cliente del descargador sin red: ``catalog()``, ``inventory(code)`` y ``report(code, year, month, start, end)``."""

    def __init__(self, estaciones: Sequence[EstacionSintetica], descargador: ModuleType):
        self.estaciones = _por_codigo(estaciones)
        self.descargador = descargador
        self.llamadas = {"catalog": 0, "inventory": 0, "report": 0}

    def catalog(self):
        self.llamadas["catalog"] += 1
        return self.descargador.parse_catalog(html_catalogo(list(self.estaciones.values())))

    def inventory(self, code):
        self.llamadas["inventory"] += 1
        return inventario(self.estaciones[code])

    def report(self, code, year, month, start=None, end=None):
        self.llamadas["report"] += 1
        est = self.estaciones[code]
        texto = hoja_html(code, year, month, filas_del_mes(est, year, month), self.descargador)
        url = f"{URL_FALSA}/hojaMensualDatos/{code}/{year}/{month}"
        return self.descargador.parse_report(texto, code, year, month, start, end), url


class GuardaFalsaMC:
    """Guarda mínima del descargador (``defer_heavy_checks = True``): ``check``, ``ensure_directory`` y
    ``write_atomic_bytes``. Con ``raiz`` rechaza toda escritura fuera de ella; nunca bajo /Volumes ni en los
    repositorios, por la ruta léxica antes de resolver."""
    defer_heavy_checks = True

    def __init__(self, raiz=None):
        self.raiz = None if raiz is None else Path(os.path.realpath(destino_temporal(raiz)))
        self.checks = 0
        self.escrituras: list[Path] = []

    def check(self, *args, **kwargs):
        self.checks += 1

    def _permitida(self, ruta: Path) -> Path:
        ruta = destino_temporal(ruta)
        if self.raiz is not None and not _bajo(Path(os.path.realpath(ruta)), self.raiz):
            raise ValueError("escritura fuera de la carpeta temporal de la guarda")
        return ruta

    def ensure_directory(self, path):
        self.check()
        self._permitida(Path(path)).mkdir(parents=True, exist_ok=True)

    def write_atomic_bytes(self, path, body):
        self.check()
        ruta = self._permitida(Path(path))
        ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal = ruta.with_name(f".{ruta.name}.tmp-sintetico")
        temporal.write_bytes(body)
        os.replace(temporal, ruta)
        self.escrituras.append(ruta)


def fabricar_descarga(estaciones, raiz_temporal, descargador, desde: str, hasta: str, *,
                      crear_candado: bool = True) -> Path:
    """Corre ``run_download`` del descargador recibido en ``raiz_temporal/DMC`` con el cliente y la guarda falsos
    (``http_workers=1``: sin red ni procesos) y devuelve esa raíz DMC sintética."""
    raiz = Path(os.path.realpath(destino_temporal(raiz_temporal)))
    dmc = raiz / "DMC"
    dmc.mkdir(parents=True, exist_ok=True)
    guarda = GuardaFalsaMC(dmc)
    resumen = descargador.run_download(dmc, desde, hasta, guarda, client=ClienteFalsoMC(list(estaciones), descargador),
                                       http_workers=1)
    if resumen.get("phase") != "finished" or resumen.get("status") not in ("finished", "finished_with_pending"):
        raise RuntimeError(f"run_download no terminó: {resumen.get('status')!r}")
    if crear_candado:
        (dmc / ".meteo_download.lock").touch()
    return dmc


def manifiestos_de(dmc) -> dict[str, list[Path]]:
    """Código → manifiestos ``estaciones/<código>/<AAAA-MM>.manifest.json`` de una raíz DMC sintética, en orden."""
    raiz = destino_temporal(dmc)
    salida: dict[str, list[Path]] = {}
    for ruta in sorted((raiz / "estaciones").glob("*/*.manifest.json")):
        salida.setdefault(ruta.parent.name, []).append(ruta)
    return salida


def artefactos_de_descarga(dmc) -> dict[str, list[str]]:
    """Código → sha256 de sus artefactos (los ``content_sha256`` que da ``leer_artefacto``), para la política."""
    salida: dict[str, list[str]] = {}
    for codigo, rutas in manifiestos_de(dmc).items():
        for ruta in rutas:
            meta = json.loads(ruta.read_text(encoding="utf-8"))
            if meta.get("artifact_sha256"):
                salida.setdefault(codigo, []).append(meta["artifact_sha256"])
    return salida


def alterar_artefacto(manifiesto, cambio: Callable[[dict], dict]) -> str:
    """Aplica ``cambio`` al contenido de un artefacto sintético ya descargado y deja el manifiesto al día (sha256,
    bytes y filas). Devuelve la sha256 nueva. Sólo en carpetas temporales (SIN-3)."""
    ruta = destino_temporal(manifiesto)
    meta = json.loads(ruta.read_text(encoding="utf-8"))
    archivo = ruta.parent / meta["artifact_name"]
    payload = json.loads(gzip.decompress(archivo.read_bytes()))
    nuevo = cambio(payload)
    if not isinstance(nuevo, dict):
        raise ValueError("el cambio debe devolver el contenido del artefacto")
    comprimido = gzip.compress(json.dumps(nuevo, ensure_ascii=False).encode("utf-8"), mtime=0)
    sha = _escribir(archivo, comprimido)
    meta.update(artifact_sha256=sha, artifact_bytes=len(comprimido), row_count=len(nuevo.get("rows", [])))
    _escribir(ruta, json.dumps(meta, ensure_ascii=False, indent=1).encode("utf-8"))
    return sha


# ---------------------------------------------------------------------------
# Política de RELOJ, artefactos evaluados y registro de C5 (SIN-4, SIN-5; MC-40)
# ---------------------------------------------------------------------------
def rutas_politica_sintetica(raiz, fecha_c5: str = FECHA_C5_SINTETICA) -> dict[str, Path]:
    """Dónde deja ``politica_reloj_sintetica`` cada archivo bajo ``raiz`` (``AP/…`` y ``APH/…``)."""
    base = _lexica(raiz)
    publicacion = base / "AP" / RUTA_PUBLICACION_RELOJ
    return {"politica": publicacion / ARCHIVO_POLITICA, "artefactos": publicacion / ARCHIVO_ARTEFACTOS,
            "informe": publicacion / ARCHIVO_INFORME,
            "registro": base / "APH" / RUTA_REGISTRO_C5.format(fecha=fecha_c5)}


def _source_reloj(informe_sha: str, codigo: str, tramo: str, protocolo_sha: str) -> str:
    return (f"reloj-dmc/v1 informe={RUTA_PUBLICACION_RELOJ}/{ARCHIVO_INFORME} sha256={informe_sha} estacion={codigo} "
            f"tramo={tramo} protocolo={protocolo_sha}")


def politica_reloj_sintetica(raiz, estaciones, reglas: dict, *, coordenadas_inconsistentes=(), marcas=None,
                             conjuntos=None, post_hoc: bool = False, errata_post_c4: bool = False,
                             errata_confirmada: str | None = None, commit_c5: str | None = None,
                             fecha_c5: str = FECHA_C5_SINTETICA, alterar_registro: Mapping | None = None) -> Path:
    """Política de RELOJ, ``artefactos_evaluados.json.gz``, informe (sólo K2) y registro de C5, bajo ``raiz``.

    - ``estaciones``: código → sha256 de sus artefactos evaluados (por ejemplo, ``artefactos_de_descarga``);
    - ``reglas``: código → lista de tramos ``{"tramo": "1.1", "valid_from": "AAAA-MM-DDTHH:00:00", "valid_to": …,
      "minutos": −240, "veredicto": "F(-4)" | None}``;
    - ``marcas``: código → ``{"posible_media_horaria": bool, "reloj_no_verificado": [{"anio", "variables"}]}``;
    - ``alterar_registro``: campos que reemplazan los del registro de C5 (las negativas de S2).
    Devuelve la ruta de la política (la que recibe ``validar_regla_reloj_dmc(…, politica_ruta=…)``). Cada caso debe ir
    en una raíz distinta (MC-40: el validador guarda cada publicación por ruta).
    """
    rutas = rutas_politica_sintetica(raiz, fecha_c5)
    marcas = dict(marcas or {})
    conjuntos = dict(conjuntos or {})
    artefactos = [{"artefacto_sha256": sha, "codigo": str(codigo)}
                  for codigo, shas in sorted(estaciones.items()) for sha in sorted(set(shas))]
    gz = gzip.compress(_json_canonico(artefactos), mtime=0)
    sha_artefactos = _escribir(rutas["artefactos"], gz)
    informe = {"schema": "dmc-reloj-informe-sintetico/1",
               "coordenadas_inconsistentes": sorted(str(c) for c in coordenadas_inconsistentes)}
    sha_informe = _escribir(rutas["informe"], _json_canonico(informe))
    sha_protocolo = _sha(b"protocolo de RELOJ sintetico")
    politicas_reloj, salida_estaciones = [], {}
    for codigo in sorted(set(estaciones) | set(reglas)):
        tramos = reglas.get(codigo, [])
        if not tramos:
            salida_estaciones[codigo] = {"veredicto": "sin_confirmar", "motivo": "sin_datos", "detalle": None}
            continue
        veredictos = {}
        for t in tramos:
            regla = {"verified": True, "source": _source_reloj(sha_informe, codigo, t["tramo"], sha_protocolo),
                     "valid_from": t["valid_from"], "valid_to": t["valid_to"], "timestamp_semantics": "instantaneous",
                     "fixed_offset_minutes": int(t["minutos"])}
            politicas_reloj.append({"station_code": codigo, "valid_from": t["valid_from"], "valid_to": t["valid_to"],
                                    "clock": regla})
            if t.get("veredicto") is not None:
                veredictos[t["tramo"]] = t["veredicto"]
        relojes = list(dict.fromkeys(veredictos.values()))
        salida_estaciones[codigo] = {
            "veredicto": "confirmada", "reloj": "→".join(relojes), "conjunto": conjuntos.get(codigo, "N"),
            "marcas": marcas.get(codigo, {"posible_media_horaria": False, "reloj_no_verificado": []}),
            "tramos": veredictos}
    politica = {"schema": ESQUEMA_POLITICA_RELOJ, "post_hoc": bool(post_hoc), "errata_post_c4": bool(errata_post_c4),
                "ajuste_documental": False,
                "protocolo": {"ruta": RUTA_PROTOCOLO_RELOJ, "sha256": sha_protocolo, "commit_ap": "0" * 40},
                "configuracion": {"ruta": RUTA_CONFIGURACION_RELOJ, "sha256": _sha(b"configuracion sintetica")},
                "informe": {"ruta": f"{RUTA_PUBLICACION_RELOJ}/{ARCHIVO_INFORME}", "sha256": sha_informe},
                "artefactos_evaluados": {"ruta": f"{RUTA_PUBLICACION_RELOJ}/{ARCHIVO_ARTEFACTOS}",
                                         "sha256": sha_artefactos},
                "adaptador_sha256": SHA_ADAPTADOR, "interprete": {"python": "3.11.16", "tzdata": "2026.3"},
                "transiciones_sha256": SHA_ANEXO_A_RELOJ, "politicas_reloj": politicas_reloj,
                "estaciones": salida_estaciones}
    sha_politica = _escribir(rutas["politica"], _json_canonico(politica))
    registro = {"schema": ESQUEMA_REGISTRO_C5,
                "politica_ruta": f"AP/{RUTA_PUBLICACION_RELOJ}/{ARCHIVO_POLITICA}", "sha256_politica": sha_politica,
                "artefactos_ruta": f"AP/{RUTA_PUBLICACION_RELOJ}/{ARCHIVO_ARTEFACTOS}",
                "sha256_artefactos": sha_artefactos, "commit_c5": commit_c5 or _sha(b"commit C5")[:40],
                "errata_confirmada": errata_confirmada}
    registro.update(dict(alterar_registro or {}))
    _escribir(rutas["registro"], json.dumps(registro, ensure_ascii=False, indent=1).encode("utf-8") + b"\n")
    return rutas["politica"]


# ---------------------------------------------------------------------------
# ERA5-Land (SIN-6 a SIN-8)
# ---------------------------------------------------------------------------
def horas_del_mes(anio: int, mes: int) -> np.ndarray:
    """Las horas HH:00 UTC de un mes (datetime64[s] ingenuo = UTC)."""
    inicio = np.datetime64(f"{int(anio):04d}-{int(mes):02d}", "M")
    return np.arange(inicio.astype("datetime64[h]"), (inicio + 1).astype("datetime64[h]"),
                     np.timedelta64(1, "h")).astype("datetime64[s]")


def _segundos_utc(tiempos) -> np.ndarray:
    if isinstance(tiempos, pd.DatetimeIndex) and tiempos.tz is not None:
        tiempos = tiempos.tz_convert("UTC").tz_localize(None)
    if isinstance(tiempos, (list, tuple)) and tiempos and isinstance(tiempos[0], datetime):
        tiempos = [t.astimezone(UTC).replace(tzinfo=None) if t.tzinfo else t for t in tiempos]
    return np.asarray(np.asarray(tiempos, dtype="datetime64[s]").astype("int64"), dtype=np.int64)


def _indices_globales(pixel_ids) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    pid = np.asarray(pixel_ids, dtype=np.int64)
    i, j = pid // _COLUMNAS_LON_GLOBAL, pid % _COLUMNAS_LON_GLOBAL
    lat = np.round(90.0 - i * RESOLUCION_ERA5L, 6)
    lon = np.round(j * RESOLUCION_ERA5L, 6)
    lon = np.where(lon > 180, np.round(lon - 360.0, 6), lon)
    return i, j, lat, lon


def tp_acumulado(tiempos, lluvia_m) -> np.ndarray:
    """El acumulado ``tp`` de ERA5-Land (m) desde la lluvia de cada hora (m, en la hora que termina en el sello):
    acumulado desde las 00 UTC del pronóstico, con el sello de las 00 UTC como paso 24 del día anterior."""
    s = _segundos_utc(tiempos)
    lluvia = np.asarray(lluvia_m, dtype=np.float64)
    dia = (s - 3600) // 86400                       # el pronóstico al que pertenece el fin de hora
    salida = np.empty_like(lluvia)
    for d in np.unique(dia):
        k = dia == d
        salida[k] = np.cumsum(lluvia[k], axis=0)
    return salida


def mes_era5_netcdf(ruta, campos: dict, tiempos, pixel_ids, *, unidades: str = "nativas", cod_comuna=None,
                    catalogo_sha256: str | None = None):
    """Un mes ERA5-Land en el NetCDF real (SIN-6). ``campos``: variable (de ``VARIABLES_ERA5L``) → tiempo × píxel, en
    unidades nativas (K, Pa, m s-1 y m). ``unidades`` ≠ «nativas» cambia los valores (S13) sin cambiar el atributo.
    Los ``tiempos`` se escriben como vienen (una hora que no es HH:00 queda en el archivo, para S12)."""
    import netCDF4

    if unidades not in UNIDADES_MALAS:
        raise ValueError(f"unidades {unidades!r}; se admiten {UNIDADES_MALAS}")
    destino = destino_temporal(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    t = _segundos_utc(tiempos)
    pid = np.asarray(pixel_ids, dtype=np.int64)
    i, j, lat, lon = _indices_globales(pid)
    ajenas = sorted(set(campos) - set(VARIABLES_ERA5L))
    if ajenas:
        raise ValueError(f"variables que no son de ERA5-Land: {ajenas}")
    with netCDF4.Dataset(destino, "w", format="NETCDF4") as nc:
        nc.setncattr("temporal_operation", OPERACION_TEMPORAL_ERA5L)
        nc.setncattr("spatial_resolution_degrees", RESOLUCION_ERA5L)
        nc.setncattr("catalog_sha256", catalogo_sha256 or "0" * 64)
        nc.setncattr("source", "meteo_combinada.sintetico")
        nc.createDimension("time", len(t))
        nc.createDimension("pixel", len(pid))
        vt = nc.createVariable("time", "i8", ("time",))
        vt.setncatts({"units": UNIDADES_TIEMPO_ERA5L, "calendar": CALENDARIO_ERA5L, "standard_name": "time"})
        vt[:] = t
        for nombre, tipo, valores in (("pixel_id", "i8", pid), ("latitude", "f8", lat), ("longitude", "f8", lon),
                                      ("lat_index_global", "i8", i), ("lon_index_global", "i8", j),
                                      ("cod_comuna", "i4", np.zeros(len(pid), np.int32) if cod_comuna is None
                                       else np.broadcast_to(np.asarray(cod_comuna, np.int32), (len(pid),)))):
            v = nc.createVariable(nombre, tipo, ("pixel",))
            v[:] = valores
        crs = nc.createVariable("latitude_longitude", "i4", ())
        crs.grid_mapping_name = "latitude_longitude"
        for var in VARIABLES_ERA5L:
            if var not in campos:
                continue
            x = np.asarray(campos[var], dtype=np.float64)
            if x.shape != (len(t), len(pid)):
                raise ValueError(f"{var}: forma {x.shape}; se espera {(len(t), len(pid))}")
            if unidades == "t2m_celsius" and var == "t2m":
                x = x - KELVIN
            elif unidades == "sp_hpa" and var == "sp":
                x = x / 100.0
            elif unidades == "tp_mm" and var == "tp":
                x = x * 1000.0
            v = nc.createVariable(var, "f4", ("time", "pixel"), fill_value=np.float32(np.nan), zlib=True, complevel=1)
            v.units = UNIDADES_ERA5L[var]
            v.set_auto_maskandscale(False)
            v[:] = x.astype(np.float32)
    return destino


def catalogo_pixeles(lat0, lon0, nlat, nlon, *, cod_comuna: int = 13101, territorio: str = "continental"):
    """Catálogo de píxeles de 0,1° (SIN-7): ``nlat`` filas hacia el sur desde el centro (lat0, lon0) y ``nlon``
    columnas hacia el este, con las columnas del catálogo real."""
    filas = []
    for a in range(int(nlat)):
        for b in range(int(nlon)):
            lat = round(float(lat0) - a * RESOLUCION_ERA5L, 6)
            lon = round(float(lon0) + b * RESOLUCION_ERA5L, 6)
            i = int(math.floor(round((90.0 - lat) / RESOLUCION_ERA5L, 6) + 0.5))
            j = int(math.floor(round((lon % 360.0) / RESOLUCION_ERA5L, 6) + 0.5)) % _COLUMNAS_LON_GLOBAL
            filas.append({"pixel_id": i * _COLUMNAS_LON_GLOBAL + j, "latitude": lat, "longitude": lon,
                          "cell_west": round(lon - RESOLUCION_ERA5L / 2, 6), "cell_east": round(lon + RESOLUCION_ERA5L / 2, 6),
                          "cell_south": round(lat - RESOLUCION_ERA5L / 2, 6), "cell_north": round(lat + RESOLUCION_ERA5L / 2, 6),
                          "cod_comuna": int(cod_comuna), "territorio": territorio, "lat_index_global": i,
                          "lon_index_global": j})
    tabla = pd.DataFrame(filas, columns=list(COLUMNAS_CATALOGO_PIXELES)).sort_values("pixel_id").reset_index(drop=True)
    enteros = {"pixel_id": "int64", "cod_comuna": "int64", "lat_index_global": "int64", "lon_index_global": "int64",
               "territorio": "string"}
    return tabla.astype({c: enteros.get(c, "float64") for c in COLUMNAS_CATALOGO_PIXELES})


def geopotencial_sintetico(carpeta, catalogo, z_m, *, corrimiento_filas: int = 0) -> dict[str, Path]:
    """El NetCDF crudo del geopotencial y su derivado por píxel (SIN-8). ``z_m``: la altitud de cada píxel del
    catálogo (en su orden). Con ``corrimiento_filas`` la grilla del NetCDF queda corrida respecto del parquet (S13)."""
    import netCDF4

    base = destino_temporal(carpeta)
    base.mkdir(parents=True, exist_ok=True)
    cat = catalogo.reset_index(drop=True)
    z_m = np.asarray(z_m, dtype=np.float64)
    if len(z_m) != len(cat):
        raise ValueError("una altitud por píxel del catálogo")
    i = cat["lat_index_global"].to_numpy(np.int64)
    j = cat["lon_index_global"].to_numpy(np.int64)
    i0, j0 = int(i.min()), int(j.min())
    nlat, nlon = int(i.max()) - i0 + 1, int(j.max()) - j0 + 1
    rejilla = np.full((nlat, nlon), np.nan, dtype=np.float32)
    crudo = (z_m * G0).astype(np.float32)
    rejilla[i - i0, j - j0] = crudo
    if corrimiento_filas:
        rejilla = np.roll(rejilla, int(corrimiento_filas), axis=0)
    lats = np.round(90.0 - (i0 + np.arange(nlat)) * RESOLUCION_ERA5L, 6)          # descendente
    lons = np.round((j0 + np.arange(nlon)) * RESOLUCION_ERA5L, 6)
    lons = np.where(lons > 180, np.round(lons - 360.0, 6), lons)
    ruta_nc = base / "era5land_geopotencial_invariante_chile.nc"
    with netCDF4.Dataset(destino_temporal(ruta_nc), "w", format="NETCDF4") as nc:
        nc.createDimension("valid_time", 1)
        nc.createDimension("latitude", nlat)
        nc.createDimension("longitude", nlon)
        vt = nc.createVariable("valid_time", "i8", ("valid_time",))
        vt.setncatts({"units": "seconds since 1970-01-01", "calendar": CALENDARIO_ERA5L})
        vt[:] = [0]
        vla = nc.createVariable("latitude", "f8", ("latitude",))
        vla.units = "degrees_north"
        vla[:] = lats
        vlo = nc.createVariable("longitude", "f8", ("longitude",))
        vlo.units = "degrees_east"
        vlo[:] = lons
        vz = nc.createVariable("z", "f4", ("valid_time", "latitude", "longitude"), fill_value=np.float32(np.nan))
        vz.setncatts({"units": "m**2 s**-2", "long_name": "Geopotential", "GRIB_shortName": "z"})
        vz[:] = rejilla[None, :, :]
    derivado = pd.DataFrame({"pixel_id": cat["pixel_id"].to_numpy(np.int64), "lat_index_global": i,
                             "lon_index_global": j, "latitude": cat["latitude"].to_numpy(np.float64),
                             "longitude": cat["longitude"].to_numpy(np.float64),
                             "z_m2_s2": crudo.astype(np.float64), "z_m": crudo.astype(np.float64) / G0})
    ruta_pq = base / "era5land_altitud_modelo_pixeles.parquet"
    buf = io.BytesIO()
    derivado.to_parquet(buf, index=False)
    _escribir(ruta_pq, buf.getvalue())
    return {"geopotencial": ruta_nc, "altitud": ruta_pq}


# ---------------------------------------------------------------------------
# NASADEM y GHS-POP (SIN-9, SIN-10)
# ---------------------------------------------------------------------------
def id_tesela_nasadem(lat_sur: int, lon_oeste: int) -> str:
    """«s34w071» para la tesela de 1° con esquina suroeste (−34, −71), como los nombres HGT."""
    ns = "s" if lat_sur < 0 else "n"
    ew = "w" if lon_oeste < 0 else "e"
    return f"{ns}{abs(int(lat_sur)):02d}{ew}{abs(int(lon_oeste)):03d}"


def tesela_nasadem(ruta, funcion_z, *, mascara=None, oeste: float = -70.70, norte: float = -33.40,
                   filas: int = 120, columnas: int = 120, tile_id: str | None = None, aoi_id: str = "continente"):
    """Tesela NASADEM recortada (SIN-9): GeoTIFF int16 EPSG:4326 de 1/3.600°, ``nodata`` −32768 y máscara interna.

    ``funcion_z(lat, lon)`` da la elevación (m) en los centros; ``mascara(lat, lon)`` es True donde hay dato (la
    máscara administrativa). El primer centro es (``norte``, ``oeste``), en múltiplos exactos de 1/3.600°.
    """
    import rasterio
    from rasterio.transform import Affine

    destino = destino_temporal(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    oeste = round(float(oeste) * 3600) / 3600
    norte = round(float(norte) * 3600) / 3600
    lat = norte - np.arange(int(filas))[:, None] * NASADEM_RES
    lon = oeste + np.arange(int(columnas))[None, :] * NASADEM_RES
    LAT, LON = np.broadcast_arrays(lat, lon)
    z = np.asarray(funcion_z(LAT, LON), dtype=np.float64)
    con_dato = np.isfinite(z) if mascara is None else (np.asarray(mascara(LAT, LON), dtype=bool) & np.isfinite(z))
    datos = np.where(con_dato, np.round(np.where(np.isfinite(z), z, 0.0)), NASADEM_NODATA).astype(np.int16)
    transform = Affine(NASADEM_RES, 0.0, oeste - NASADEM_RES / 2, 0.0, -NASADEM_RES, norte + NASADEM_RES / 2)
    perfil = {"driver": "GTiff", "width": int(columnas), "height": int(filas), "count": 1, "dtype": "int16",
              "crs": "EPSG:4326", "transform": transform, "nodata": NASADEM_NODATA, "compress": "deflate"}
    etiquetas = {"producto": "NASADEM_HGT", "tile_id": tile_id or id_tesela_nasadem(math.floor(norte), math.floor(oeste)),
                 "aoi_id": aoi_id, "spatial_resolution_native": "1 arc-second (~30 m)", "variable": "elevation",
                 "vertical_units": "meters", "resampling": "none", "source": "meteo_combinada.sintetico"}
    with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True):
        with rasterio.open(destino, "w", **perfil) as dst:
            dst.write(datos, 1)
            dst.write_mask(con_dato.astype("uint8") * 255)
            dst.update_tags(**etiquetas)
            dst.update_tags(1, long_name="surface elevation", units="m")
    return destino


def nombre_tesela_ghs(fila: int, columna: int, epoca: int = 2020) -> str:
    return f"GHS_POP_E{int(epoca)}_GLOBE_R2023A_54009_100_V1_0_R{int(fila)}_C{int(columna)}"


def tesela_ghs(ruta, funcion_pob, *, lat_centro: float = -33.45, lon_centro: float = -70.65, filas: int = 100,
               columnas: int = 100):
    """Ventana GHS-POP de 100 m en Mollweide (SIN-10): float32, ``nodata`` −200, alineada a la rejilla de teselas.

    ``funcion_pob(lat, lon)`` da los habitantes de cada píxel en su centro (NaN → nodata). Con ruta «.zip» escribe el
    .zip con el .tif del mismo nombre adentro.
    """
    import rasterio
    from pyproj import Transformer
    from rasterio.io import MemoryFile
    from rasterio.transform import Affine

    destino = destino_temporal(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    ida = Transformer.from_crs("EPSG:4326", CRS_GHS, always_xy=True)
    vuelta = Transformer.from_crs(CRS_GHS, "EPSG:4326", always_xy=True)
    x, y = ida.transform(float(lon_centro), float(lat_centro))
    x0 = GHS_X0 + math.floor((x - GHS_X0) / GHS_PIXEL) * GHS_PIXEL - (int(columnas) // 2) * GHS_PIXEL
    y0 = GHS_Y0 - math.floor((GHS_Y0 - y) / GHS_PIXEL) * GHS_PIXEL + (int(filas) // 2) * GHS_PIXEL
    xc = x0 + (np.arange(int(columnas)) + 0.5) * GHS_PIXEL
    yc = y0 - (np.arange(int(filas)) + 0.5) * GHS_PIXEL
    XC, YC = np.meshgrid(xc, yc)
    lon, lat = vuelta.transform(XC, YC)
    pob = np.asarray(funcion_pob(np.asarray(lat), np.asarray(lon)), dtype=np.float64)
    datos = np.where(np.isfinite(pob), pob, GHS_NODATA).astype(np.float32)
    perfil = {"driver": "GTiff", "width": int(columnas), "height": int(filas), "count": 1, "dtype": "float32",
              "crs": CRS_GHS, "transform": Affine(GHS_PIXEL, 0.0, x0, 0.0, -GHS_PIXEL, y0), "nodata": GHS_NODATA,
              "compress": "deflate"}
    with MemoryFile() as memoria:
        with memoria.open(**perfil) as dst:
            dst.write(datos, 1)
        contenido = bytes(memoria.getbuffer())
    if destino.suffix.lower() == ".zip":
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr(destino.stem + ".tif", contenido)
        _escribir(destino, buf.getvalue())
    else:
        _escribir(destino, contenido)
    return destino


# ---------------------------------------------------------------------------
# Grilla de ≈ 1 km y pesos (SIN-11)
# ---------------------------------------------------------------------------
def _id_celda(lat, lon) -> np.ndarray:
    return (np.floor((np.asarray(lat) + 90) * 100).astype(np.int64) * 36000
            + np.floor((np.asarray(lon) + 180) * 100).astype(np.int64))


def grilla(nceldas, comunas, *, lat0: float = -33.30, lon0: float = -70.80, anios_pesos=(2020,),
           semilla: int = SEMILLA_POR_OMISION, celdas_sin_comuna: int = 0) -> dict:
    """Las tablas de ``grilla_1km`` y los pesos de población para ``nceldas`` celdas de 0,01° en un rectángulo con
    esquina noroeste (``lat0``, ``lon0``), repartidas en bloques contiguos entre las ``comunas`` (códigos, o un
    número de comunas 13101, 13102…). Devuelve celdas, estaticas, estaticas_lulc (2015 y 2020),
    enlaces_productos (sólo ERA5-Land), pesos (poblacion_celda_anio) y estaticas_mc (ESQUEMA_ESTATICAS_CELDA).
    ``celdas_sin_comuna``: las últimas celdas quedan con ``cod_comuna = 0`` y macrozona «sin_region» (D9, SIN-19)."""
    comunas = tuple(13101 + k for k in range(int(comunas))) if isinstance(comunas, (int, np.integer)) else tuple(comunas)
    n = int(nceldas)
    if n < len(comunas) or not comunas:
        raise ValueError("al menos una celda por comuna")
    ncol = int(math.ceil(math.sqrt(n)))
    k = np.arange(n)
    lat = np.round(lat0 - (k // ncol) * 0.01 - 0.005, 6)
    lon = np.round(lon0 + (k % ncol) * 0.01 + 0.005, 6)
    cod = np.asarray(comunas, dtype=np.int32)[np.minimum(k * len(comunas) // n, len(comunas) - 1)]
    if celdas_sin_comuna:
        cod[n - int(celdas_sin_comuna):] = 0
    region = cod // 1000
    nombres_macro = [MACROZONA_REGION.get(int(r), MACROZONA_REGION[0]) for r in region]
    macro = [(m, MACROZONA_CODIGO[m]) for m in nombres_macro]
    celda = _id_celda(lat, lon)
    rng = _rng(semilla, "grilla")
    elev = 500.0 + 3000.0 * (lon - lon0) + 200.0 * np.sin(lat * 60.0)
    pendiente = np.abs(rng.normal(5.0, 3.0, n))
    dist_costa = np.maximum((lon - (-71.65)) * 92.0, 0.5)
    celdas = pd.DataFrame({"celda": celda, "lat": lat, "lon": lon, "cod_comuna": cod, "aoi_id": "continente",
                           "origen": "sintetico", "codregion": region.astype(np.int16),
                           "region_rellenada_por_vecino": False, "macrozona": [m[0] for m in macro],
                           "macrozona_cod": np.asarray([m[1] for m in macro], dtype=np.int8)})
    celdas = celdas.astype({"aoi_id": "string", "origen": "string", "macrozona": "string"})
    estaticas = pd.DataFrame({
        "celda": celda, "elev_m": elev.astype(np.float32), "elev_sd_m": np.full(n, 20.0, np.float32),
        "pendiente_deg": pendiente.astype(np.float32), "elev_fuente": "sintetico",
        "dist_costa_km": dist_costa.astype(np.float32), "frac_lena": np.zeros(n, np.float32),
        "vias_km_km2": np.ones(n, np.float32), "vias_princ_km_km2": np.full(n, 0.2, np.float32),
        "vias_fuente": "sintetico", "dist_est_pm25_km": np.full(n, 10.0, np.float32),
        "dist_est_no2_km": np.full(n, 12.0, np.float32), "lat": lat, "lon": lon,
        "macrozona_cod": celdas["macrozona_cod"].to_numpy(), "cod_comuna": cod})
    estaticas = estaticas.astype({"elev_fuente": "string", "vias_fuente": "string"})
    fr = rng.dirichlet(np.ones(len(LULC)), size=n)
    partes = []
    for anio in (2015, 2020):
        d = {"celda": celda, "anio": np.full(n, anio, np.int16)}
        d.update({c: fr[:, m].astype(np.float32) for m, c in enumerate(LULC)})
        d.update({"lulc_n_pixeles": np.full(n, 100, np.int16), "lulc_anio_raster": np.full(n, anio, np.int16),
                  "pob_dens": (fr[:, 0] * 3000.0).astype(np.float32)})
        partes.append(pd.DataFrame(d))
    lulc = pd.concat(partes, ignore_index=True)
    i_pix = np.floor(np.round((90.0 - lat) / RESOLUCION_ERA5L, 6) + 0.5).astype(np.int64)
    j_pix = np.floor(np.round((lon % 360.0) / RESOLUCION_ERA5L, 6) + 0.5).astype(np.int64) % _COLUMNAS_LON_GLOBAL
    _, _, lat_p, lon_p = _indices_globales(i_pix * _COLUMNAS_LON_GLOBAL + j_pix)
    enlaces = pd.DataFrame({"celda": celda, "lat": lat, "lon": lon,
                            "era5land_pixel": i_pix * _COLUMNAS_LON_GLOBAL + j_pix,
                            "era5land_dist_km": _haversine_km(lat, lon, lat_p, lon_p).astype(np.float32),
                            "era5land_enlace": pd.Categorical(["contiene"] * n)})
    poblada = (rng.random(n) > 0.3) & (cod > 0)
    pob = np.where(poblada, rng.uniform(10.0, 5000.0, n), 0.0)
    pesos = pd.concat([pd.DataFrame({"celda": celda, "anio": np.full(n, a, np.int16), "cod_comuna": cod,
                                     "pob_ghs": pob.astype(np.float32), "w_ghs": pob.astype(np.float32),
                                     "w_ur": pob.astype(np.float32), "w_dasim": pob.astype(np.float32),
                                     "ghs_respaldo_ur": False}) for a in anios_pesos], ignore_index=True)
    z_poblada = np.where(poblada, elev - 30.0, elev)
    filas_mc = [{"celda": int(celda[m]), "z_media": float(elev[m]), "z_poblada": float(z_poblada[m]),
                 "z_poblada_es_media": not bool(poblada[m]), "frac_dato": 1.0, "tpi1": float(elev[m] - elev.mean()) / 10,
                 "tpi5": float(elev[m] - elev.mean()) / 5, "tpi1_truncado": False, "tpi5_truncado": False,
                 "pendiente_deg": float(pendiente[m]), "log_dist_costa": float(np.log1p(dist_costa[m])),
                 **{c: float(fr[m, q]) for q, c in enumerate(LULC)}, "lat": float(lat[m]),
                 "macrozona_cod": int(macro[m][1]), "cod_comuna": int(cod[m])} for m in range(n)]
    estaticas_mc = _tabla(filas_mc, ESQUEMA_ESTATICAS_CELDA, _version("estaticas_celda"))
    return {"celdas": celdas, "estaticas": estaticas, "estaticas_lulc": lulc, "enlaces_productos": enlaces,
            "pesos": pesos, "estaticas_mc": estaticas_mc, "comunas": comunas}


# ---------------------------------------------------------------------------
# Verdad sintética (S5) y anomalías correlacionadas
# ---------------------------------------------------------------------------
def _mes_y_hora(h) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    t = np.datetime64("2000-01-01T00", "h") + np.asarray(h, dtype=np.int64).astype("timedelta64[h]")
    meses = t.astype("datetime64[M]")
    anio = meses.astype(np.int64) // 12 + 1970
    mes = meses.astype(np.int64) % 12 + 1
    hora = (np.asarray(h, dtype=np.int64) % 24)
    return anio, mes, hora


def _cholesky_exponencial(lat, lon, sigma: float, L_km: float) -> np.ndarray:
    """Factor de Cholesky de la covarianza σ²·exp(−d/L) entre los puntos."""
    lat, lon = np.asarray(lat, np.float64), np.asarray(lon, np.float64)
    d = _haversine_km(lat[:, None], lon[:, None], lat[None, :], lon[None, :])
    return np.linalg.cholesky(sigma ** 2 * np.exp(-d / L_km) + 1e-9 * np.eye(len(lat)))


def _ar1(rng: np.random.Generator, n_t: int, chol: np.ndarray, phi: float) -> np.ndarray:
    """AR(1) en el tiempo de un campo gaussiano con factor ``chol``, estacionario desde el primer paso."""
    salida = np.matmul(rng.standard_normal((n_t, chol.shape[0])), chol.T)   # innovaciones; el AR(1), en el lugar
    escala = math.sqrt(1 - phi ** 2)
    for t in range(1, n_t):
        salida[t] *= escala
        salida[t] += phi * salida[t - 1]
    return salida


def _anomalias(rng: np.random.Generator, n_t: int, lat, lon, sigma: float, L_km: float, tau_h: float,
               paso_h: float) -> np.ndarray:
    """AR(1) en el tiempo (τ en horas) de un campo gaussiano con covarianza σ²·exp(−d/L) entre los puntos."""
    phi = math.exp(-paso_h / tau_h) if tau_h > 0 else 0.0
    return _ar1(rng, n_t, _cholesky_exponencial(lat, lon, sigma, L_km), phi)


def _restar_media_por_mes(a: np.ndarray, h) -> np.ndarray:
    """Resta a cada punto su media en cada mes × año (los tiempos van en orden), en float64 y en el lugar (MC-50)."""
    anio, mes, _ = _mes_y_hora(h)
    clave = anio * 12 + mes
    if np.any(np.diff(clave) < 0):
        raise ValueError("los tiempos deben ir en orden")
    inicios = np.flatnonzero(np.r_[True, np.diff(clave) != 0])
    fines = np.r_[inicios[1:], len(clave)]
    salida = np.asarray(a, dtype=np.float64)          # en el lugar si ya es float64
    for i0, i1 in zip(inicios, fines):
        salida[i0:i1] -= salida[i0:i1].mean(axis=0)
    return salida


ANOMALIAS_MC50 = MappingProxyType({"sigma": 1.5, "L_km": 100.0, "tau_h": 48.0, "media_cero": True})   # SIN-21


def _parametros_anomalias(anomalias) -> dict:
    """SIN-21: ``True`` o «MC-50» son las anomalías de MC-50 (D42); un diccionario cambia sólo las claves que trae."""
    if anomalias is True or anomalias == "MC-50":
        return dict(ANOMALIAS_MC50)
    if not isinstance(anomalias, Mapping):
        raise ValueError(f"anomalias: None, True, «MC-50» o un diccionario, no {anomalias!r}")
    desconocidas = set(anomalias) - set(ANOMALIAS_MC50)
    if desconocidas:
        raise ValueError(f"anomalias: claves desconocidas {sorted(desconocidas)}; se admiten {sorted(ANOMALIAS_MC50)}")
    return {**ANOMALIAS_MC50, **anomalias}


def verdad(campos_base, sesgo, anomalias, *, semilla: int) -> dict:
    """Observación sintética = fondo + sesgo b(x, m, h) + anomalías con correlación espacial (S5).

    ``campos_base``: ``h`` (horas desde 2000-01-01T00Z, en orden), ``lat`` y ``lon`` de los puntos y ``F`` (tiempo ×
    punto). ``sesgo``: función b(lat, lon, mes, hora) → por punto, o arreglo punto × 12 × 24. ``anomalias``: None (sin
    anomalías), True o «MC-50» (las de MC-50: σ = 1,5 K, L = 100 km, τ = 48 h y media 0 en cada punto × mes × año;
    D42), o ``{"sigma", "L_km", "tau_h", "media_cero"}``, con las claves que falten tomadas de MC-50 (SIN-21; la prueba
    informativa sin la media 0 pasa ``{"media_cero": False}``). Devuelve h, lat, lon, F, b, a, obs y ``anomalias`` (los
    parámetros usados, o None)."""
    h = np.asarray(campos_base["h"], dtype=np.int64)
    lat = np.asarray(campos_base["lat"], dtype=np.float64)
    lon = np.asarray(campos_base["lon"], dtype=np.float64)
    F = np.asarray(campos_base["F"], dtype=np.float64)
    if F.shape != (len(h), len(lat)):
        raise ValueError("F debe ser tiempo × punto")
    _, mes, hora = _mes_y_hora(h)
    if callable(sesgo):
        b = np.empty_like(F)
        for m in range(1, 13):
            for hh in range(24):
                k = (mes == m) & (hora == hh)
                if k.any():
                    b[k] = np.asarray(sesgo(lat, lon, m, hh), dtype=np.float64)[None, :]
    else:
        tabla = np.asarray(sesgo, dtype=np.float64)
        if tabla.shape != (len(lat), 12, 24):
            raise ValueError("el sesgo en arreglo es punto × 12 × 24")
        b = tabla[:, mes - 1, hora].T
    parametros = None
    if anomalias is not None and anomalias is not False:
        parametros = _parametros_anomalias(anomalias)
        paso = float(np.median(np.diff(h))) if len(h) > 1 else 1.0
        a = _anomalias(_rng(semilla, "verdad"), len(h), lat, lon, float(parametros["sigma"]),
                       float(parametros["L_km"]), float(parametros["tau_h"]), paso)
        if parametros["media_cero"]:
            a = _restar_media_por_mes(a, h)
    else:
        a = np.zeros_like(F)
    return {"h": h, "lat": lat, "lon": lon, "F": F, "b": b, "a": a, "obs": F + b + a, "anomalias": parametros}


# ---------------------------------------------------------------------------
# Red de S6 (SIN-12; MC-07, MC-50)
# ---------------------------------------------------------------------------
VALLE_LON = (-71.0, -70.6)
REGION_S6 = {"lat": (-35.0, -33.0), "lon": (-71.5, -70.0)}
_HORAS_POR_ANIO = 24.0 * 365.25
_EPOCA_H = np.datetime64("2000-01-01T00", "h")


def _valle(lon) -> np.ndarray:
    lon = np.asarray(lon)
    return (lon >= VALLE_LON[0]) & (lon <= VALLE_LON[1])


def _hora_de_mes(mes2000: int) -> int:
    """Horas desde 2000-01-01T00Z al inicio del mes (meses desde enero de 2000)."""
    return int(((np.datetime64("2000-01", "M") + int(mes2000)).astype("datetime64[h]") - _EPOCA_H).astype(np.int64))


def red_s6(*, deriva_k_decada: float = 0.0, paso_h: int = 1, anios=(2000, 2024), semilla: int = SEMILLA_POR_OMISION,
           tau_h: float = 48.0, sigma_k: float = 1.5, L_km: float = 100.0, sesgo_valle_k: float = -1.5,
           n_historicas: int = 20, n_nuevas: int = 120, anio_nuevas: int = 2010, n_comunas: int = 25,
           celdas_por_comuna: int = 4) -> dict:
    """La red sintética de S6 en una representación liviana (SIN-12).

    Guarda: ``h`` (horas desde 2000-01-01T00Z, cada ``paso_h``; por omisión todas), ``anio``, ``mes`` y ``hora``; las
    ``estaciones`` (código, lat, lon, z_m, valle, historica, desde_anio) y las ``celdas`` (celda, lat, lon, z_m, valle,
    cod_comuna, w_ghs de 2020); por punto (primero las estaciones, después las celdas) ``lat``, ``lon``, ``base`` (clima
    medio) y ``beta`` (sesgo del fondo: −1,5 K en los valles); el factor de Cholesky de las anomalías y los
    ``parametros``. Los campos los dan ``anomalias_s6`` (un mes) y ``campos_s6`` (verdad, fondo y observación por años).
    """
    a0, a1 = int(anios[0]), int(anios[1])
    h0 = int((np.datetime64(f"{a0}-01-01T00", "h") - _EPOCA_H).astype(np.int64))
    h1 = int((np.datetime64(f"{a1 + 1}-01-01T00", "h") - _EPOCA_H).astype(np.int64))
    h = np.arange(h0, h1, int(paso_h), dtype=np.int64)
    anio, mes, hora = _mes_y_hora(h)
    rng = _rng(semilla, "red_s6")
    lat_h, lon_h = [], []
    while len(lat_h) < n_historicas:                      # las históricas, fuera de los valles
        la, lo = rng.uniform(*REGION_S6["lat"]), rng.uniform(*REGION_S6["lon"])
        if not _valle(lo):
            lat_h.append(la)
            lon_h.append(lo)
    lat_n = rng.uniform(*REGION_S6["lat"], n_nuevas)
    lon_n = rng.uniform(*REGION_S6["lon"], n_nuevas)
    lat_e, lon_e = np.r_[lat_h, lat_n], np.r_[lon_h, lon_n]
    valle_e = _valle(lon_e)
    z_e = np.where(valle_e, 300.0, 900.0) + rng.normal(0.0, 50.0, len(lat_e))
    codigos = [f"{900001 + k:06d}" for k in range(n_historicas)] + [f"{900101 + k:06d}" for k in range(n_nuevas)]
    desde = np.r_[np.full(n_historicas, a0), np.full(n_nuevas, max(a0, int(anio_nuevas)))].astype(np.int16)
    estaciones = pd.DataFrame({"codigo": codigos, "lat": lat_e, "lon": lon_e, "z_m": z_e, "valle": valle_e,
                               "historica": np.r_[np.ones(n_historicas, bool), np.zeros(n_nuevas, bool)],
                               "desde_anio": desde}).astype({"codigo": "string"})
    lado = int(math.ceil(math.sqrt(n_comunas)))
    dlat = (REGION_S6["lat"][1] - REGION_S6["lat"][0]) / lado
    dlon = (REGION_S6["lon"][1] - REGION_S6["lon"][0]) / lado
    filas = []
    for c in range(n_comunas):
        f, g = divmod(c, lado)
        for _ in range(celdas_por_comuna):
            filas.append((REGION_S6["lat"][0] + (f + rng.random()) * dlat,
                          REGION_S6["lon"][0] + (g + rng.random()) * dlon, 13101 + c))
    lat_c = np.array([x[0] for x in filas])
    lon_c = np.array([x[1] for x in filas])
    valle_c = _valle(lon_c)
    z_c = np.where(valle_c, 300.0, 900.0) + rng.normal(0.0, 50.0, len(lat_c))
    celdas = pd.DataFrame({"celda": _id_celda(lat_c, lon_c), "lat": lat_c, "lon": lon_c, "z_m": z_c,
                           "valle": valle_c, "cod_comuna": np.array([x[2] for x in filas], np.int32),
                           "w_ghs": rng.uniform(100.0, 5000.0, len(lat_c))})
    lat_p, lon_p, z_p = np.r_[lat_e, lat_c], np.r_[lon_e, lon_c], np.r_[z_e, z_c]
    return {"h": h, "anio": anio.astype(np.int16), "mes": mes.astype(np.int8), "hora": hora.astype(np.int8),
            "estaciones": estaciones, "celdas": celdas, "lat": lat_p, "lon": lon_p,
            "base": 15.0 - 6.5 * z_p / 1000.0, "beta": np.where(_valle(lon_p), float(sesgo_valle_k), 0.0),
            "cholesky": _cholesky_exponencial(lat_p, lon_p, float(sigma_k), float(L_km)),
            "parametros": {"deriva_k_decada": float(deriva_k_decada), "paso_h": int(paso_h), "anios": (a0, a1),
                           "semilla": int(semilla), "sesgo_valle_k": float(sesgo_valle_k), "sigma_k": float(sigma_k),
                           "L_km": float(L_km), "tau_h": float(tau_h), "anio_nuevas": int(anio_nuevas), "h_ref": h0}}


def ciclo_s6(h) -> np.ndarray:
    """Ciclo anual (máximo a mediados de enero) y diario (máximo a las 19 UTC) de la verdad de S6, en K."""
    h = np.asarray(h, dtype=np.float64)
    dia_anio = (h / 24.0) % 365.25
    return 5.0 * np.cos(2 * np.pi * (dia_anio - 15.0) / 365.25) + 4.0 * np.cos(2 * np.pi * ((h % 24) - 19.0) / 24.0)


def deriva_s6(red: dict, h) -> np.ndarray:
    """Deriva del fondo: d·(años desde el inicio de la red)/10."""
    p = red["parametros"]
    return p["deriva_k_decada"] * (np.asarray(h, dtype=np.float64) - p["h_ref"]) / (_HORAS_POR_ANIO * 10.0)


def anomalias_s6(red: dict, mes2000: int) -> tuple[np.ndarray, np.ndarray]:
    """(horas, anomalías tiempo × punto) de un mes (meses desde enero de 2000): un AR(1) propio del mes, con su
    subsecuencia de la semilla, y con la media del mes restada en cada punto (exactamente 0 en float64; MC-50)."""
    h = red["h"]
    i0, i1 = np.searchsorted(h, [_hora_de_mes(mes2000), _hora_de_mes(int(mes2000) + 1)])
    hh = h[i0:i1]
    p = red["parametros"]
    phi = math.exp(-p["paso_h"] / p["tau_h"]) if p["tau_h"] > 0 else 0.0
    a = _ar1(_rng(p["semilla"], "red_s6", "anomalias", str(int(mes2000))), len(hh), red["cholesky"], phi)
    if len(hh):
        a -= a.mean(axis=0)
    return hh, a


def campos_s6(red: dict, cuales: str = "estaciones", *, anios=None) -> dict[str, np.ndarray]:
    """Verdad, fondo y (en las estaciones) observación de ``red_s6`` en los ``anios`` pedidos (por omisión, todos),
    tiempo × punto en float64, con sus ``h`` y ``anio``. La observación es NaN antes del año de entrada de la estación.
    Un año en las 140 estaciones son ≈ 10 MB por campo: conviene pedirlo por años."""
    ne = len(red["estaciones"])
    if cuales == "estaciones":
        cols = slice(0, ne)
    elif cuales == "celdas":
        cols = slice(ne, None)
    else:
        raise ValueError("cuales: «estaciones» o «celdas»")
    a0, a1 = red["parametros"]["anios"] if anios is None else (int(anios[0]), int(anios[1]))
    partes_h, partes_a = [], []
    for m in range((a0 - 2000) * 12, (a1 + 1 - 2000) * 12):
        hh, a = anomalias_s6(red, m)
        partes_h.append(hh)
        partes_a.append(a[:, cols])
    h = np.concatenate(partes_h) if partes_h else np.zeros(0, np.int64)
    anom = np.concatenate(partes_a) if partes_a else np.zeros((0, len(red["base"][cols])))
    anio, _, _ = _mes_y_hora(h)
    clima = red["base"][None, cols] + ciclo_s6(h)[:, None]
    salida = {"h": h, "anio": anio, "verdad": clima + anom,
              "fondo": clima + red["beta"][None, cols] + deriva_s6(red, h)[:, None]}
    if cuales == "estaciones":
        activa = anio[:, None] >= red["estaciones"]["desde_anio"].to_numpy()[None, :]
        salida["obs"] = np.where(activa, salida["verdad"], np.nan)
    return salida


# ---------------------------------------------------------------------------
# Series de traslados (S4; SIN-13, MC-49)
# ---------------------------------------------------------------------------
TIPOS_TRASLADO = ("estacionaria", "traslado", "barometro", "reduccion", "horario")
_MAGNITUD_POR_OMISION = {"traslado": 15.0, "barometro": 1.5}
# Ruido y señales de S4 (SIN-13, SIN-20; MC-49, D42). Las señales de «reduccion» y «horario» van, por omisión, sólo
# en su tipo; en los demás valen 0 y la serie es, bit a bit, la de la ola 1 (test_sintetico guarda sus huellas).
SIGMA_T2B_DIARIO_HPA = 0.7               # MC-49: AR(1) diario de T2b
TAU_T2B_DIAS = 2.0                       # MC-49
SIGMA_T2B_HORARIO_HPA = 0.3              # MC-49
SIGMA_Z_IMPL_M = 5.0                     # MC-49: z_impl, ruido blanco horario (estructura fijada en SIN-13)
DT_CLIMA_REDUCCION_K = 10.0              # «reduccion»: T̄ real − T̄ de la atmósfera estándar (SIN-20)
CICLO_HORARIO_M = 50.0                   # «horario»: amplitud del ciclo diario de z_impl (SIN-20)
HORA_MAXIMO_CICLO_UTC = 19.0             # máximo del ciclo diario de z_impl (el de Ts)
HORARIO_DIURNO_UTC = (11, 23)            # horas UTC observadas antes del cambio en «horario»


def ciclo_diario_t2b_hpa(ciclo_m: float, altitud_m: float, dt_clima_k: float = 0.0) -> float:
    """Amplitud (hPa) del ciclo diario de T2b que acompaña a un ciclo de z_impl de ``ciclo_m`` m como lo haría un
    desplazamiento vertical (SIN-20): ``ciclo_m`` · g · p̄ / (R · T̄), con p̄ = p_std(z) y T̄ = 288,15 − 0,0065·z/2 +
    ``dt_clima_k`` (la T̄ media de §2.5). Con signo opuesto: cuando z_impl sube, QFE baja."""
    tbar = 288.15 - 0.0065 * float(altitud_m) / 2.0 + float(dt_clima_k)
    return float(ciclo_m) * G0 * float(_p_std(float(altitud_m))) / (R_SECO * tbar)


def series_traslado(tipo: str, altitud_m: float, *, semilla: int, magnitud: float | None = None,
                    desde: str = "2012-01-01", hasta: str = "2017-12-31", cambio: str = "2015-01-01",
                    dt_clima_k: float | None = None, ciclo_diario_m: float | None = None):
    """Serie horaria de una estación para K4 (S4): ``h``, ``Ts`` (°C), ``QFE``, ``QFF`` y ``p_F`` (hPa).

    ``tipo``: «estacionaria»; «traslado» (``magnitud`` m hacia arriba, por omisión 15); «barometro» (``magnitud`` hPa,
    por omisión 1,5, en QFE y QFF en la misma proporción); «reduccion» (QFF con la atmósfera estándar antes del
    cambio y real después, en una estación cuyo clima es ``dt_clima_k`` K más cálido que la atmósfera estándar: por
    omisión 10 K, así z_impl salta −z·ΔT/T̄_std en el cambio); «horario» (sólo 11-23 UTC antes del cambio, 24 h
    después, con un ciclo diario de ``ciclo_diario_m`` m en z_impl, por omisión 50, y el de T2b equivalente,
    ``ciclo_diario_t2b_hpa``). El fondo p_F está en la altitud del catálogo (``altitud_m``). Ruido de MC-49 con la
    estructura de SIN-13; ``attrs`` dice el tipo, la magnitud, las señales y la hora del cambio.
    """
    if tipo not in TIPOS_TRASLADO:
        raise ValueError(f"tipo {tipo!r}; se admiten {TIPOS_TRASLADO}")
    mag = _MAGNITUD_POR_OMISION.get(tipo, 0.0) if magnitud is None else float(magnitud)
    dt = (DT_CLIMA_REDUCCION_K if tipo == "reduccion" else 0.0) if dt_clima_k is None else float(dt_clima_k)
    amp_z = (CICLO_HORARIO_M if tipo == "horario" else 0.0) if ciclo_diario_m is None else float(ciclo_diario_m)
    if not (math.isfinite(dt) and math.isfinite(amp_z)):
        raise ValueError("dt_clima_k y ciclo_diario_m deben ser finitos")
    epoca = np.datetime64("2000-01-01T00", "h")
    h0 = int((np.datetime64(desde, "h") - epoca).astype(np.int64))
    h1 = int((np.datetime64(hasta, "h") - epoca).astype(np.int64)) + 24
    hc = int((np.datetime64(cambio, "h") - epoca).astype(np.int64))
    h = np.arange(h0, h1, dtype=np.int64)
    rng = _rng(semilla, "traslado", tipo, f"{float(altitud_m):.1f}")
    n = len(h)
    hora = h % 24
    dia_anio = (h / 24.0) % 365.25
    ts = (15.0 - 6.5 * altitud_m / 1000.0 + 6.0 * np.cos(2 * np.pi * (dia_anio - 15.0) / 365.25)
          + 5.0 * np.cos(2 * np.pi * (hora - 19.0) / 24.0) + rng.normal(0.0, 1.0, n))
    if dt != 0.0:
        ts = ts + dt                                       # clima de la estación ≠ atmósfera estándar (SIN-20)
    # Fondo: atmósfera estándar en la altitud del catálogo más un proceso sinóptico (τ = 3 días) y la marea S2.
    phi = math.exp(-1.0 / 72.0)
    ruido = rng.normal(0.0, 6.0 * math.sqrt(1 - phi ** 2), n)
    sinop = np.empty(n)
    sinop[0] = rng.normal(0.0, 6.0)
    for t in range(1, n):
        sinop[t] = phi * sinop[t - 1] + ruido[t]
    p_f = _p_std(altitud_m) + sinop + 1.0 * np.cos(2 * np.pi * (hora - 10.0) / 12.0)
    # T2b: AR(1) diario (σ = 0,7 hPa, τ = 2 días) más 0,3 hPa horario (MC-49).
    dias = (h - h0) // 24
    nd = int(dias.max()) + 1
    phid = math.exp(-1.0 / TAU_T2B_DIAS)
    e = np.empty(nd)
    e[0] = rng.normal(0.0, SIGMA_T2B_DIARIO_HPA)
    choques = rng.normal(0.0, SIGMA_T2B_DIARIO_HPA * math.sqrt(1 - phid ** 2), nd)
    for d in range(1, nd):
        e[d] = phid * e[d - 1] + choques[d]
    ruido_t2b = e[dias] + rng.normal(0.0, SIGMA_T2B_HORARIO_HPA, n)
    despues = h >= hc
    tk = ts + KELVIN
    dz = np.where(despues & (tipo == "traslado"), mag, 0.0)
    qfe = p_f * np.exp(-G0 * dz / (R_SECO * tk)) + ruido_t2b
    if tipo == "barometro":
        qfe = np.where(despues, qfe * (1.0 + mag / float(np.mean(qfe))), qfe)
    amp_p = ciclo_diario_t2b_hpa(amp_z, altitud_m, dt) if amp_z != 0.0 else 0.0
    if amp_z != 0.0:
        ciclo = np.cos(2 * np.pi * (hora - HORA_MAXIMO_CICLO_UTC) / 24.0)
        qfe = qfe - amp_p * ciclo                          # T2b con el ciclo de un desplazamiento vertical (SIN-20)
    # z_impl: ruido blanco horario de 5 m, independiente de T2b y de Ts (MC-49; estructura de SIN-13). Es la última
    # extracción del generador: las señales de SIN-20 no cambian ninguna otra.
    z_red = altitud_m + dz + rng.normal(0.0, SIGMA_Z_IMPL_M, n)
    if amp_z != 0.0:
        z_red = z_red + amp_z * ciclo                      # la reducción de la estación con otro ciclo diario de T
    t_red = ts + KELVIN + 0.0065 * (altitud_m + dz) / 2.0
    if tipo == "reduccion":
        t_std = 288.15 - 0.0065 * altitud_m / 2.0          # T̄ de la atmósfera estándar: no ve el clima ni el ciclo
        t_red = np.where(despues, t_red, t_std)
    qff = qfe * np.exp(z_red / (29.27 * t_red))
    observada = np.ones(n, bool)
    if tipo == "horario":
        observada = despues | ((hora >= HORARIO_DIURNO_UTC[0]) & (hora <= HORARIO_DIURNO_UTC[1]))
    df = pd.DataFrame({"h": h.astype(np.int32), "Ts": ts, "QFE": qfe, "QFF": qff, "p_F": p_f})[observada]
    df = df.reset_index(drop=True)
    df.attrs.update(tipo=tipo, altitud_m=float(altitud_m), z_cat=float(altitud_m), magnitud=mag, cambio_h=hc,
                    dt_clima_k=dt, ciclo_diario_m=amp_z, ciclo_diario_t2b_hpa=amp_p,
                    hora_maximo_ciclo_utc=HORA_MAXIMO_CICLO_UTC,
                    horario_diurno_utc=HORARIO_DIURNO_UTC if tipo == "horario" else None)
    return df


# ---------------------------------------------------------------------------
# Casos de la regla de decisión y del soporte (S7; SIN-14)
# ---------------------------------------------------------------------------
CASOS_METRICAS = ("ganador_claro", "compuerta_cd", "falla_cd_hr", "falla_ex_td", "falla_mz_hr", "falla_tf_td",
                  "tf2_falla", "e1_vacio", "empate", "deriva", "finitud", "mz_no_aplica", "mz_no_publicable",
                  "mz_no_publicable_p2", "agudo_nivel", "falla_ex_hr_media", "falla_mz_agudo", "uv",
                  "falla_mz_rapidez", "p_sin_ex", "cronica", "cronica_mixta", "tf2_no_evaluable", "falla_mz_cronica",
                  "soporte")
_COTAS_TF = {"T": (0.05, 0.15), "Td": (0.10, 0.25), "rapidez": (0.05, 0.15), "p": (0.10, 0.30)}
CERO_POR_CONSTRUCCION = ("A", "C", "C_est")       # §5.7: su artefacto de TF es 0 por construcción (SIN-14)
# Particiones de la validación publicada (MC-61) y reparto de cada métrica agregada entre P1 y P2 (SIN-22): la de P1 es
# x·√(1 − ε_c) y la de P2, x·√(1 + ε_c), así x² = (x_P1² + x_P2²)/2 (un RMSE con las mismas evaluaciones en cada una).
PARTICIONES_VALIDACION = ("P1", "P2", "agregado")
_EPS_PARTICION = {"A": 0.10, "B": -0.10, "AB": 0.20, "C": -0.20, "C_est": -0.20}
_EVALUACIONES_NACIONALES = 40                     # estaciones del agregado nacional: una evaluación por partición

# Métricas por candidato: «<métrica>_<variable>». S = puntaje; CD, EX, nivel y anom = compuertas; MZ = S en la
# macrozona «centro». Todas las compuertas pasan en la base de cada familia (comprobado a mano con el Anexo A).
_BASE_AMBIENTAL = {
    "A": {"S_T": 1.20, "S_HR": 8.0, "CD_T": 0.30, "CD_HR": 3.00, "EX_T": 0.50, "EX_Td": 0.80, "MZ_T": 1.15, "MZ_HR": 8.2},
    "B": {"S_T": 1.10, "S_HR": 7.6, "CD_T": 0.32, "CD_HR": 3.10, "EX_T": 0.55, "EX_Td": 0.90, "MZ_T": 1.10, "MZ_HR": 7.8},
    "AB": {"S_T": 1.00, "S_HR": 7.2, "CD_T": 0.31, "CD_HR": 3.05, "EX_T": 0.52, "EX_Td": 0.85, "MZ_T": 1.05, "MZ_HR": 7.4},
    "C": {"S_T": 1.30, "S_HR": 8.8, "CD_T": 0.33, "CD_HR": 3.20, "EX_T": 0.60, "EX_Td": 1.00, "MZ_T": 1.20, "MZ_HR": 8.4},
}
_BASE_AGUDO = {
    "A": {"S_temp_media": 0.80, "S_hr_media": 5.0, "EX_temp_media": 0.40, "EX_hr_media": 2.0, "nivel_temp_media": 1.00,
          "nivel_hr_media": 6.0, "CD_T": 0.30, "CD_HR": 3.00},
    "B": {"S_temp_media": 0.75, "S_hr_media": 4.8, "EX_temp_media": 0.42, "EX_hr_media": 2.1, "nivel_temp_media": 1.05,
          "nivel_hr_media": 6.1, "CD_T": 0.31, "CD_HR": 3.10},
    "AB": {"S_temp_media": 0.70, "S_hr_media": 4.5, "EX_temp_media": 0.41, "EX_hr_media": 2.2, "nivel_temp_media": 1.05,
           "nivel_hr_media": 6.2, "CD_T": 0.32, "CD_HR": 3.05},
    "C": {"S_temp_media": 0.85, "S_hr_media": 5.3, "EX_temp_media": 0.45, "EX_hr_media": 2.4, "nivel_temp_media": 1.10,
          "nivel_hr_media": 6.5, "CD_T": 0.33, "CD_HR": 3.20},
}
_BASE_UV = {       # AB falla CD de la rapidez (0,30 > 1,10·0,20 + 0,05) y B falla EX (0,70 > 0,30 + 0,30)
    # MZ en «uv» (mín 1,75 → cota 2,0125) y en la rapidez (D43; mín 0,82 → cota 0,943): todos pasan.
    "A": {"S_uv": 2.00, "CD_rapidez": 0.20, "EX_rapidez": 0.30, "MZ_uv": 2.00, "MZ_rapidez": 0.90},
    "B": {"S_uv": 1.80, "CD_rapidez": 0.21, "EX_rapidez": 0.70, "MZ_uv": 1.85, "MZ_rapidez": 0.86},
    "AB": {"S_uv": 1.70, "CD_rapidez": 0.30, "EX_rapidez": 0.35, "MZ_uv": 1.75, "MZ_rapidez": 0.82},
    "C": {"S_uv": 2.10, "CD_rapidez": 0.22, "EX_rapidez": 0.40, "MZ_uv": 2.01, "MZ_rapidez": 0.91},
}
_BASE_P = {        # AB falla CD (0,30 > 1,10·0,20 + 0,05); el EX_p de B (9,9) no cuenta: no hay EX de la presión
    "A": {"S_p": 1.00, "CD_p": 0.20, "EX_p": 0.10, "MZ_p": 1.02},
    "B": {"S_p": 0.90, "CD_p": 0.21, "EX_p": 9.90, "MZ_p": 0.95},
    "AB": {"S_p": 0.85, "CD_p": 0.30, "EX_p": 0.10, "MZ_p": 0.90},
    "C": {"S_p": 1.10, "CD_p": 0.22, "EX_p": 0.10, "MZ_p": 1.03},
}
_BASE_CRONICO = {
    "A": {"S_T": 0.40, "CD_T": 0.30, "EX_temp_media": 0.50, "anom_T": 0.20, "MZ_T": 0.40},
    "B": {"S_T": 0.30, "CD_T": 0.31, "EX_temp_media": 0.55, "anom_T": 0.21, "MZ_T": 0.30},
    "AB": {"S_T": 0.32, "CD_T": 0.30, "EX_temp_media": 0.52, "anom_T": 0.20, "MZ_T": 0.32},
    "C_est": {"S_T": 0.38, "CD_T": 0.32, "EX_temp_media": 0.53, "anom_T": 0.22, "MZ_T": 0.38},
}
# Lo agudo con MZ en «temp_media» y «hr_media» (mín 0,72 → cota 0,828; mín 4,6 → cota 5,29: todos pasan).
_BASE_AGUDO_MZ = {c: {**v, **mz} for (c, v), mz in zip(_BASE_AGUDO.items(), (
    {"MZ_temp_media": 0.80, "MZ_hr_media": 5.0}, {"MZ_temp_media": 0.75, "MZ_hr_media": 4.8},
    {"MZ_temp_media": 0.72, "MZ_hr_media": 4.6}, {"MZ_temp_media": 0.82, "MZ_hr_media": 5.2}))}
# Lo crónico con MZ que rige (12 estaciones): mín 0,30 (B) → cota 0,345; todos pasan.
_BASE_CRONICO_MZ = {c: {**v, "MZ_T": mz} for (c, v), mz in zip(_BASE_CRONICO.items(), (0.33, 0.30, 0.32, 0.34))}
# familia → (uso, grupo, base, variables de S, variables de TF, estaciones de la macrozona)
_FAMILIAS = {
    "amb": ("ambiental", "T_Td", _BASE_AMBIENTAL, ("T", "HR"), ("T", "Td"), 12),
    "agu": ("agudo", "T_Td", _BASE_AGUDO, ("temp_media", "hr_media"), ("T", "Td"), 12),     # sin filas de MZ
    "agu_mz": ("agudo", "T_Td", _BASE_AGUDO_MZ, ("temp_media", "hr_media"), ("T", "Td"), 12),
    "uv": ("ambiental", "u_v", _BASE_UV, ("uv",), ("rapidez",), 12),
    "p": ("ambiental", "p", _BASE_P, ("p",), ("p",), 12),
    "cro": ("cronico", "T_Td", _BASE_CRONICO, ("T",), ("T",), 6),        # 6 < 10: MZ no aplica en lo crónico
    "cro_mz": ("cronico", "T_Td", _BASE_CRONICO_MZ, ("T",), ("T",), 12),
}
# caso → especificación. «fallas» es el resultado esperado: candidato → compuertas que falla (§6.1, a mano).
_CASOS = {
    "ganador_claro": {"familia": "amb"},
    "compuerta_cd": {"familia": "amb", "cambios": {"AB__CD_T": 0.40}, "fallas": {"AB": ("CD",)}},
    "falla_cd_hr": {"familia": "amb", "cambios": {"AB__CD_HR": 3.90}, "fallas": {"AB": ("CD",)}},
    "falla_ex_td": {"familia": "amb", "cambios": {"AB__EX_Td": 1.25}, "fallas": {"AB": ("EX",)}},
    "falla_mz_hr": {"familia": "amb", "cambios": {"AB__MZ_HR": 9.10}, "fallas": {"AB": ("MZ",)}},
    "falla_tf_td": {"familia": "amb", "tf_fallas": (("AB", "Td", "TF1"),), "fallas": {"AB": ("TF",)}},
    "tf2_falla": {"familia": "amb", "tf_fallas": (("AB", "T", "TF2"),), "fallas": {"AB": ("TF",)}},
    # E1 vacío: cada uno falla una compuerta; AB (el de menor S) falla TF, así el paso 4 elige B y no AB. C queda
    # fuera por CD en HR (4,0 > 1,10·3,0 + 0,5): su TF es 0 por construcción (§5.7).
    "e1_vacio": {"familia": "amb", "cambios": {"A__CD_T": 0.45, "B__EX_T": 0.90, "C__CD_HR": 4.0},
                 "tf_fallas": (("AB", "Td", "TF1"),), "fallas": {"A": ("CD",), "B": ("EX",), "AB": ("TF",), "C": ("CD",)},
                 "notas": ("regla sin ganador",)},
    "empate": {"familia": "amb", "cambios": {"A__S_T": 1.00, "A__S_HR": 7.2}},
    "deriva": {"familia": "amb", "excluidos": {"B": ("deriva",)}},
    "finitud": {"familia": "amb", "excluidos": {"AB": ("finitud",)}},
    "mz_no_aplica": {"familia": "amb", "cambios": {"AB__MZ_T": 1.40}, "mz_estaciones": 8},
    "mz_no_publicable": {"familia": "amb", "cambios": {"AB__MZ_T": 1.40}, "mz_publicable": False},
    # MC-61: publicable en P1 y en el agregado, no en P2 → MZ no rige, y AB (1,40 > 1,15·1,10) no falla.
    "mz_no_publicable_p2": {"familia": "amb", "cambios": {"AB__MZ_T": 1.40},
                            "mz_publicable": {"P1": True, "P2": False, "agregado": True}},
    "agudo_nivel": {"familia": "agu", "cambios": {"AB__nivel_temp_media": 1.30}, "fallas": {"AB": ("nivel",)}},
    "falla_ex_hr_media": {"familia": "agu", "cambios": {"AB__EX_hr_media": 4.50}, "fallas": {"AB": ("EX",)}},
    "falla_mz_agudo": {"familia": "agu_mz", "cambios": {"AB__MZ_temp_media": 0.95}, "fallas": {"AB": ("MZ",)}},
    "uv": {"familia": "uv", "fallas": {"AB": ("CD",), "B": ("EX",)}},
    # D43: MZ también en la rapidez; A falla sólo allí (1,00 > 1,15·0,82) y gana C.
    "falla_mz_rapidez": {"familia": "uv", "cambios": {"A__MZ_rapidez": 1.00},
                         "fallas": {"AB": ("CD",), "B": ("EX",), "A": ("MZ",)}},
    "p_sin_ex": {"familia": "p", "fallas": {"AB": ("CD",)}},
    "cronica": {"familia": "cro", "cambios": {"A__S_T": 0.36}, "tf_fallas": (("B", "T", "TF1"),),
                "excluidos": {"AB": ("deriva",)}, "fallas": {"B": ("TF",)}, "notas": ("regla crónica",)},
    "cronica_mixta": {"familia": "cro",
                      "cambios": {"AB__CD_T": 0.45, "A__EX_temp_media": 0.90, "B__EX_temp_media": 0.50,
                                  "AB__EX_temp_media": 0.52, "C_est__EX_temp_media": 0.53, "B__anom_T": 0.20,
                                  "AB__anom_T": 0.21, "C_est__anom_T": 0.30, "AB__S_T": 0.31},
                      "tf_fallas": (("B", "T", "TF1"),),
                      "fallas": {"B": ("TF",), "AB": ("CD",), "A": ("EX",), "C_est": ("anomalia",)},
                      "notas": ("regla crónica", "regla sin ganador")},                  # E1 vacío (DEC-10)
    "tf2_no_evaluable": {"familia": "cro", "cambios": {"C_est__S_T": 0.37}, "no_evaluable": ("T",),
                         "fallas": {"B": ("TF",), "AB": ("TF",)}, "notas": ("regla crónica", "TF2 no evaluable")},
    # MZ rige en lo crónico (12 estaciones): B falla (0,50 > 1,15·0,32); AB sigue en E1, así no rige la regla crónica.
    "falla_mz_cronica": {"familia": "cro_mz", "cambios": {"B__MZ_T": 0.50}, "fallas": {"B": ("MZ",)}},
}
# Orden fijo de las notas del paso 6 (DEC-10), para los esperados.
ORDEN_NOTAS = ("regla crónica", "regla sin ganador", "TF2 no evaluable")


def _copiar(base: Mapping[str, Mapping[str, float]], cambios: Mapping[str, float]) -> dict[str, dict[str, float]]:
    salida = {c: dict(v) for c, v in base.items()}
    for clave, valor in cambios.items():
        candidato, metrica = clave.split("__")
        salida[candidato][metrica] = valor
    return salida


def _publicable_por_particion(mz_publicable) -> dict[str, bool]:
    """``True``/``False`` en las tres particiones, o {partición: bool} con las tres (MC-61, TIP-15)."""
    if isinstance(mz_publicable, bool):
        return dict.fromkeys(PARTICIONES_VALIDACION, mz_publicable)
    if set(mz_publicable) != set(PARTICIONES_VALIDACION):
        raise ValueError(f"mz_publicable: {sorted(mz_publicable)}; se esperan {PARTICIONES_VALIDACION}")
    return {p: bool(mz_publicable[p]) for p in PARTICIONES_VALIDACION}


def _filas_validacion(uso: str, grupo: str, m: Mapping[str, Mapping[str, float]], *, mz_estaciones: int,
                      mz_publicable=True) -> list[dict]:
    """Filas de ``ESQUEMA_VALIDACION_PUB`` en P1, P2 y el agregado (MC-61; SIN-22): el estrato nacional (40
    estaciones; una evaluación por partición, 80 en el agregado, siempre publicable) y la macrozona «centro» con
    ``mz_estaciones`` estaciones (``mz_estaciones`` evaluaciones en cada partición y el doble en el agregado) y su
    ``publicable`` por partición. El agregado lleva las métricas de la base; P1 y P2, su reparto (SIN-22)."""
    publicable = _publicable_por_particion(mz_publicable)
    filas = []
    nan = float("nan")
    for cand, v in m.items():
        eps = _EPS_PARTICION[cand]
        factor = {"P1": math.sqrt(1.0 - eps), "P2": math.sqrt(1.0 + eps), "agregado": None}

        def x(valor, p):
            return valor if factor[p] is None else factor[p] * valor

        variables = sorted({k.split("_", 1)[1] for k in v if not k.startswith("MZ_")})
        for var in variables:
            for p in PARTICIONES_VALIDACION:
                n_ev = _EVALUACIONES_NACIONALES * (2 if p == "agregado" else 1)
                filas.append({"uso": uso, "grupo": grupo, "variable": var, "candidato": cand, "particion": p,
                              "S": x(v.get(f"S_{var}", nan), p), "CD": x(v.get(f"CD_{var}", nan), p),
                              "EX": x(v.get(f"EX_{var}", nan), p), "nivel": x(v.get(f"nivel_{var}", nan), p),
                              "anomalia": x(v.get(f"anom_{var}", nan), p), "estrato": "nacional", "valor_estrato": "",
                              "n_evaluaciones": n_ev, "n_estaciones": _EVALUACIONES_NACIONALES, "publicable": True})
        for k in sorted(x_ for x_ in v if x_.startswith("MZ_")):
            for p in PARTICIONES_VALIDACION:
                filas.append({"uso": uso, "grupo": grupo, "variable": k[3:], "candidato": cand, "particion": p,
                              "S": x(v[k], p), "CD": nan, "EX": nan, "nivel": nan, "anomalia": nan,
                              "estrato": "macrozona", "valor_estrato": "centro",
                              "n_evaluaciones": mz_estaciones * (2 if p == "agregado" else 1),
                              "n_estaciones": mz_estaciones, "publicable": publicable[p]})
    return filas


def _filas_tf(uso: str, candidatos, variables, *, fallas=(), no_evaluable=()) -> list[dict]:
    """Filas de ``ESQUEMA_TF``: pasan todas salvo ``fallas`` ((candidato, variable, prueba)); con ``no_evaluable``
    (variables), TF2 «no_evaluable» con la red «ninguna» para todos los candidatos (EMC1-2). A, C y C_est dan 0 por
    construcción (§5.7): una falla suya sería un error de código, así que un caso no la pide (ValueError)."""
    malas = [f for f in fallas if f[0] in CERO_POR_CONSTRUCCION]
    if malas:
        raise ValueError(f"§5.7: A, C y C_est dan 0 por construcción; una TF fallida suya es un error de código: {malas}")
    filas = []
    for cand in candidatos:
        for var in variables:
            cm, cp = _COTAS_TF[var]
            for prueba in ("TF1", "TF2"):
                cero = cand in CERO_POR_CONSTRUCCION
                media, p95 = (0.0, 0.0) if cero else (cm / 5, cp / 5)
                resultado, regla, n_red = "pasa", "r2000_2025", 15
                if (cand, var, prueba) in fallas:
                    media, p95, resultado = cm * 3, cp * 3, "falla"
                if prueba == "TF2" and var in no_evaluable:
                    media, p95, resultado, regla, n_red = float("nan"), float("nan"), "no_evaluable", "ninguna", 7
                filas.append({"candidato": cand, "uso": uso, "variable": var, "prueba": prueba, "media_pond": media,
                              "p95_pond": p95, "cota_media": cm, "cota_p95": cp, "resultado": resultado,
                              "regla_red": regla, "n_red": n_red})
    return filas


def _replicas(S: Mapping[str, float], semilla: int, caso: str, n: int = 50) -> pd.DataFrame:
    rng = _rng(semilla, "replicas", caso)
    filas = [{"replica": r, "candidato": c, "S": float(s + rng.normal(0.0, 0.02))}
             for r in range(n) for c, s in S.items()]
    return _tabla(filas, ESQUEMA_REPLICAS, _version("replicas"))


def _s_del_grupo(m: Mapping[str, Mapping[str, float]], variables_s, e0) -> dict[str, float]:
    """S_par = ½(S_1/mín S_1 + S_2/mín S_2), con los mínimos sobre E0 (§5.3), o el S de la única variable."""
    if len(variables_s) == 1:
        return {c: m[c][f"S_{variables_s[0]}"] for c in m}
    v1, v2 = variables_s
    m1 = min(m[c][f"S_{v1}"] for c in e0)
    m2 = min(m[c][f"S_{v2}"] for c in e0)
    return {c: 0.5 * (m[c][f"S_{v1}"] / m1 + m[c][f"S_{v2}"] / m2) for c in m}


def _soporte(semilla: int) -> dict:
    """S7 (soporte, §0.4.4): evaluaciones de 10 estaciones, 6 en «centro» y 4 en «austral»; en la austral, A, B y AB
    carecen de soporte en el 80 % de las horas de prueba."""
    rng = _rng(semilla, "soporte")
    infos, filas = {}, []
    for k in range(10):
        codigo = f"{910001 + k:06d}"
        macro = "centro" if k < 6 else "austral"
        infos[codigo] = {"macrozona": macro, "conjunto": "N"}
        for particion, pliegue in (("P1", f"P1-{k % 10}"), ("P2", "P2-4_83" if macro == "centro" else "P2-3_60")):
            for cand in ("A", "B", "AB", "C"):
                sin = 0.8 if (macro == "austral" and cand != "C") else 0.1
                mse = float(rng.uniform(0.5, 1.5))
                filas.append({"codigo": codigo, "particion": particion, "pliegue": pliegue, "candidato": cand,
                              "uso": "ambiental", "variable": "T", "n_horas": 5000, "n_dias": 300, "n_anios": 5,
                              "mse_h": mse, "mae_h": math.sqrt(mse) * 0.8, "sesgo_h": 0.1, "mse_dia": mse / 2,
                              "mse_estrato": mse / 3, "mse_anual_neto": mse / 10, "mse_anomalia": mse / 12,
                              "cd": 0.3, "ex": 0.5, "frac_sin_soporte": sin})
    return {"caso": "soporte", "evaluaciones": _tabla(filas, ESQUEMA_EVALUACIONES, _version("evaluaciones")),
            "infos": infos,
            "esperado": {"no_publicables": [("macrozona", "austral")], "publicables": [("macrozona", "centro")],
                         "umbral_sin_soporte": 0.5}}


_ORDEN_DESEMPATE = {"A": 0, "AB": 1, "B": 2, "C": 3, "C_est": 3}


def _conjunto_esperado(e0, e1, fallas: Mapping[str, tuple], notas) -> tuple[str, ...]:
    """El conjunto del que sale el ganador de §6.2, escrito aparte de la regla (SIN-14): E1; con E1 vacío, los de E0
    que pasan TF (paso 4); con la regla crónica, A y C_est de E1 (o de E0 si ninguno está en E1; paso 5). Es también
    el conjunto en que cada réplica elige su ganador para el intervalo de ΔS (D46)."""
    if "regla crónica" in notas:
        return tuple(c for c in e1 if c in ("A", "C_est")) or tuple(c for c in e0 if c in ("A", "C_est"))
    if e1:
        return tuple(e1)
    return tuple(c for c in e0 if "TF" not in fallas.get(c, ()))


def _ganador_esperado(S: Mapping[str, float], conjunto) -> str:
    """Menor S del conjunto con el desempate A, AB, B, C (C_est en lo crónico)."""
    return min(conjunto, key=lambda c: (S[c], _ORDEN_DESEMPATE[c]))


def tablas_metricas(caso: str, *, semilla: int = SEMILLA_POR_OMISION) -> dict:
    """Casos nombrados para ``decidir_combinacion`` (S7) y para la regla de soporte (SIN-14; ``CASOS_METRICAS``).

    Un caso de decisión trae ``uso``, ``grupo``, ``candidatos``, ``variables_S``, ``validacion``
    (ESQUEMA_VALIDACION_PUB), ``tf`` (ESQUEMA_TF), ``replicas`` (ESQUEMA_REPLICAS: el S del grupo por réplica),
    ``e0_excluidos`` (candidato → motivos de E0: finitud o deriva) y ``esperado`` (``e0``, ``e1``, ``conjunto`` (de
    dónde sale el ganador, D46), ``ganador``, ``notas`` (en el orden de DEC-10), ``fallas``: candidato → compuertas que
    falla, y ``S``). Las tablas van tal como las lee ``decision.decidir_combinacion`` (acuerdo A11): macrozonas en P1,
    P2 y el agregado (MC-61) y la TF de A, C y C_est en 0 (§5.7).
    """
    if caso not in CASOS_METRICAS:
        raise ValueError(f"caso {caso!r}; se admiten {CASOS_METRICAS}")
    if caso == "soporte":
        return _soporte(semilla)
    spec = _CASOS[caso]
    uso, grupo, base, variables_s, variables_tf, mz_estaciones = _FAMILIAS[spec["familia"]]
    m = _copiar(base, spec.get("cambios", {}))
    excluidos = dict(spec.get("excluidos", {}))
    fallas = dict(spec.get("fallas", {}))
    notas = tuple(spec.get("notas", ()))
    if notas != tuple(n for n in ORDEN_NOTAS if n in notas) or len(set(notas)) != len(notas):
        raise ValueError(f"{caso}: notas {notas} fuera del orden de DEC-10 {ORDEN_NOTAS}")
    candidatos = tuple(m)
    e0 = tuple(c for c in candidatos if c not in excluidos)
    e1 = tuple(c for c in e0 if c not in fallas)
    if ("regla sin ganador" in notas) != (not e1):
        raise ValueError(f"{caso}: «regla sin ganador» va si y sólo si E1 está vacío (DEC-10)")
    conjunto = _conjunto_esperado(e0, e1, fallas, notas)
    S = _s_del_grupo(m, variables_s, e0)
    validacion = _tabla(_filas_validacion(uso, grupo, m, mz_estaciones=spec.get("mz_estaciones", mz_estaciones),
                                          mz_publicable=spec.get("mz_publicable", True)),
                        ESQUEMA_VALIDACION_PUB, _version("validacion_pub"))
    tf = _tabla(_filas_tf(uso, candidatos, variables_tf, fallas=spec.get("tf_fallas", ()),
                          no_evaluable=spec.get("no_evaluable", ())), ESQUEMA_TF, _version("tf"))
    return {"caso": caso, "uso": uso, "grupo": grupo, "candidatos": candidatos, "variables_S": variables_s,
            "validacion": validacion, "tf": tf, "replicas": _replicas({c: S[c] for c in e0}, semilla, caso),
            "e0_excluidos": excluidos,
            "esperado": {"e0": e0, "e1": e1, "conjunto": conjunto, "ganador": _ganador_esperado(S, conjunto),
                         "notas": notas, "fallas": fallas, "S": {c: S[c] for c in e0}}}


# ---------------------------------------------------------------------------
# Anexo B (S16; SIN-14, SIN-17)
# ---------------------------------------------------------------------------
CONTAMINANTES_M6 = ("pm25", "no2")
SENTIDOS_M6 = ("I_frente_a_D", "D_frente_a_I")
PROTOCOLOS_M6 = ("LRO", "BLQ-75")
MARGEN_NMB_PP = 1.0                     # Anexo A, «NMB + 1 punto porcentual»; NMB en porcentaje (SIN-17)
_CONDICIONES_BOOL = ("segunda_prueba_coincide", "supera_ruido", "consistencia_e2", "sobrevive_bloque",
                     "signo_sin_ponderar", "signo_log", "decision_sigma2")
# caso → quién supera en cada contaminante (la variante que cumple las 7 condiciones frente a la otra), las TF de
# contaminantes (I, D) y un cambio en las filas de pm25 del sentido D frente a I (las dos, o sólo la de BLQ-75).
# «supera_pm25» es el resultado esperado tras el cambio, calculado a mano.
_CASOS_M6 = {
    "rama1_I": {"quien": {"pm25": "I", "no2": "I"}},
    "rama1_D": {"quien": {"pm25": "D", "no2": "D"}},
    "rama2_ninguna": {"quien": {"pm25": None, "no2": None}},
    "rama2_supera_falla_tf": {"quien": {"pm25": "D", "no2": "D"},
                              "tf": {"pm25": ("pasa", "falla"), "no2": ("pasa", "falla")}},
    "rama3": {"quien": {"pm25": None, "no2": "I"}, "tf": {"pm25": ("falla", "falla")}},
    "o3_difieren": {"quien": {"pm25": "I", "no2": "D"}},
    "falla_c1_segunda": {"cambio": {"segunda_prueba_coincide": False}, "supera_pm25": False},
    "falla_c2": {"cambio": {"supera_ruido": False}, "supera_pm25": False},
    "falla_c3": {"cambio": {"consistencia_e2": False}, "supera_pm25": False},
    "falla_c4": {"cambio": {"sobrevive_bloque": False}, "supera_pm25": False},
    "falla_c5_sin_ponderar": {"cambio": {"signo_sin_ponderar": False}, "supera_pm25": False},
    "falla_c5_log": {"cambio": {"signo_log": False}, "supera_pm25": False},
    "falla_c6": {"cambio": {"decision_sigma2": False}, "supera_pm25": False},
    "falla_c7": {"cambio": {"nmb_c": 3.5, "nmb_otra": 2.0}, "supera_pm25": False},     # 3,5 > 2,0 + 1
    "borde_c7": {"cambio": {"nmb_c": 3.0, "nmb_otra": -2.0}, "supera_pm25": True},     # 3,0 ≤ |−2,0| + 1
    "c7_en_puntos": {"cambio": {"nmb_c": -2.5, "nmb_otra": 2.0}, "supera_pm25": True},  # con + 0,01 fallaría
    "solo_lro": {"cambio_blq": "neutra", "supera_pm25": False},                           # BLQ-75 no lo confirma
}
CASOS_M6 = tuple(_CASOS_M6)


def _fila_m6(pol: str, sentido: str, protocolo: str, tipo: str) -> dict:
    """«supera» (las 7 condiciones), «pierde» (el sentido contrario de uno que supera) o «neutra» (el IC incluye 0).
    NMB en porcentaje (SIN-17)."""
    if tipo == "supera":
        valores = dict(delta_r2=0.012, ic_bajo=0.004, ic_alto=0.020, nmb_c=2.0, nmb_otra=2.5)
        bools = True
    elif tipo == "pierde":
        valores = dict(delta_r2=-0.012, ic_bajo=-0.020, ic_alto=-0.004, nmb_c=2.5, nmb_otra=2.0)
        bools = False
    else:
        valores = dict(delta_r2=0.001, ic_bajo=-0.003, ic_alto=0.005, nmb_c=2.0, nmb_otra=2.0)
        bools = True
    return {"contaminante": pol, "sentido": sentido, "protocolo": protocolo, **valores,
            **{c: bools for c in _CONDICIONES_BOOL}}


def tablas_m6(caso: str) -> dict:
    """Casos nombrados del Anexo B (SIN-14, SIN-17; ``CASOS_M6``): ``comparacion`` (ESQUEMA_COMPARACION_M6,
    contaminante × sentido × protocolo), ``tf_contaminantes`` (contaminante → variante → «pasa»/«falla») y
    ``esperado`` (quién supera, rama y variante por contaminante, la de O3 y si rige el ganador restringido).

    Los casos ``falla_c*``, ``borde_c7``, ``c7_en_puntos`` y ``solo_lro`` parten de «D supera a I en los dos
    contaminantes» y cambian sólo una condición de pm25 (en LRO y BLQ-75, o sólo en BLQ-75)."""
    if caso not in _CASOS_M6:
        raise ValueError(f"caso {caso!r}; se admiten {CASOS_M6}")
    spec = _CASOS_M6[caso]
    quien = dict(spec.get("quien", {"pm25": "D", "no2": "D"}))
    tf = {pol: {"I": "pasa", "D": "pasa"} for pol in CONTAMINANTES_M6}
    for pol, (ti, td) in spec.get("tf", {}).items():
        tf[pol] = {"I": ti, "D": td}
    filas = []
    for pol in CONTAMINANTES_M6:
        for sentido in SENTIDOS_M6:
            c = sentido[0]                         # la variante que reemplaza en este sentido
            tipo = "neutra" if quien[pol] is None else ("supera" if quien[pol] == c else "pierde")
            for prot in PROTOCOLOS_M6:
                fila = _fila_m6(pol, sentido, prot, tipo)
                if pol == "pm25" and sentido == "D_frente_a_I":
                    if "cambio" in spec:
                        fila.update(spec["cambio"])
                    if spec.get("cambio_blq") and prot == "BLQ-75":
                        fila = _fila_m6(pol, sentido, prot, spec["cambio_blq"])
                filas.append(fila)
    supera = dict(quien)
    if "supera_pm25" in spec:
        supera["pm25"] = "D" if spec["supera_pm25"] else None
    rama, variante = {}, {}
    for pol in CONTAMINANTES_M6:
        sup = supera[pol]
        if sup is not None and tf[pol][sup] == "pasa":
            rama[pol], variante[pol] = 1, sup
        elif tf[pol]["I"] == "pasa":
            rama[pol], variante[pol] = 2, "I"
        elif tf[pol]["D"] == "pasa":
            rama[pol], variante[pol] = 2, "D"
        else:
            rama[pol], variante[pol] = 3, "I"
    variante["O3"] = variante["pm25"] if variante["pm25"] == variante["no2"] else "I"
    return {"caso": caso, "comparacion": _tabla(filas, ESQUEMA_COMPARACION_M6, _version("comparacion_m6")),
            "tf_contaminantes": tf,
            "esperado": {"supera": supera, "rama": rama, "variante": variante,
                         "restringido": any(r == 3 for r in rama.values())}}


# ---------------------------------------------------------------------------
# Meteorología SINCA (SIN-15; MC-10)
# ---------------------------------------------------------------------------
def _yymmdd(d: date) -> str:
    return d.strftime("%y%m%d")


def _serie_sinca(parametro: str, desde: str, hasta: str, rng: np.random.Generator, *, huecos: float = 0.0,
                 especiales: Mapping[int, str] | None = None) -> tuple[str, dict]:
    """Texto de una serie del exportador SINCA y su resumen (como ``analizar_respuesta``)."""
    d0, d1 = date.fromisoformat(desde), date.fromisoformat(hasta)
    inicio = datetime(d0.year, d0.month, d0.day, 1)
    n = ((d1 - d0).days + 1) * 24 - 1
    lineas, valores = [CABECERA_SINCA], []
    primera = ultima = ""
    for k in range(n):
        t = inicio + timedelta(hours=k)
        hora = t.hour
        if parametro == "TEMP":
            v = 18.0 + 8.0 * math.cos(2 * math.pi * (hora - 15) / 24) + rng.normal(0, 0.5)
        elif parametro == "RHUM":
            v = 60.0 - 20.0 * math.cos(2 * math.pi * (hora - 15) / 24) + rng.normal(0, 2.0)
        elif parametro == "WSPD":
            v = max(0.0, 2.5 + 1.5 * math.cos(2 * math.pi * (hora - 16) / 24) + rng.normal(0, 0.3))
        elif parametro == "WDIR":
            v = float(rng.uniform(0, 359))
        elif parametro == "PRES":
            v = 950.0 + rng.normal(0, 1.0)
        elif parametro == "RAIN":
            v = 0.0
        else:
            v = max(0.0, 800.0 * math.cos(2 * math.pi * (hora - 16) / 24))
        campo = f"{v:.1f}".replace(".", ",")
        if especiales and k in especiales:
            campo = especiales[k]
        elif huecos and rng.random() < huecos:
            campo = ""
        marca = f"{_yymmdd(t.date())};{t.hour:02d}00"
        lineas.append(f"{marca};{campo};")
        if campo:
            try:
                x = float(campo.replace(",", "."))
            except ValueError:
                x = None
            if x is not None and math.isfinite(x):
                valores.append(x)
                primera = primera or marca.replace(";", " ")
                ultima = marca.replace(";", " ")
    no_numericas = sum(1 for k, c in (especiales or {}).items() if c and not _es_numero(c))
    resumen = {"filas": n, "filas_con_observacion": len(valores), "filas_no_numericas": no_numericas,
               "primera_observacion": primera, "ultima_observacion": ultima,
               "minimo": f"{min(valores):g}" if valores else "", "maximo": f"{max(valores):g}" if valores else ""}
    return "\n".join(lineas) + "\n", resumen


def _es_numero(texto: str) -> bool:
    try:
        return math.isfinite(float(texto.replace(",", ".")))
    except ValueError:
        return False


# (manifiesto, región, estación, nombre, parámetro, altura en m, huecos, especiales)
_SERIES_SINCA = (
    ("", "RM", "D11", "Estación sintética A", "TEMP", 2, 0.0, None),
    ("", "RM", "D11", "Estación sintética A", "TEMP", 10, 0.0, None),
    ("", "RM", "D11", "Estación sintética A", "RHUM", 2, 0.0, None),
    ("", "RM", "D11", "Estación sintética A", "WSPD", 10, 0.0, None),
    ("", "RM", "D11", "Estación sintética A", "WDIR", 10, 0.0, None),
    ("", "RM", "D12", "Estación sintética B", "TEMP", 2, 0.0, None),
    ("", "RM", "D12", "Estación sintética B", "TEMP", 2, 0.2, None),      # empate de altura: gana la de más filas
    ("", "RM", "D12", "Estación sintética B", "RHUM", 2, 0.0, {5: "105,0", 6: "-1,0", 7: "s/d"}),
    ("", "RM", "D12", "Estación sintética B", "WSPD", 10, 0.0, None),
    ("", "RM", "D12", "Estación sintética B", "WDIR", 10, 0.0, {9: "400,0"}),
    (SUFIJO_SEGUNDO_MANIFIESTO, "V", "550", "Estación sintética C", "TEMP", 2, 0.0, None),
    (SUFIJO_SEGUNDO_MANIFIESTO, "V", "550", "Estación sintética C", "RHUM", 2, 0.0, None),
    (SUFIJO_SEGUNDO_MANIFIESTO, "V", "550", "Estación sintética C", "WSPD", 10, 0.0, None),
    (SUFIJO_SEGUNDO_MANIFIESTO, "V", "550", "Estación sintética C", "WDIR", 10, 0.0, None),
    (SUFIJO_SEGUNDO_MANIFIESTO, "V", "550", "Estación sintética C", "PRES", 2, 0.0, None),
    (SUFIJO_SEGUNDO_MANIFIESTO, "V", "550", "Estación sintética C", "RAIN", 2, 0.0, None),
    (SUFIJO_SEGUNDO_MANIFIESTO, "V", "550", "Estación sintética C", "GLOB", 2, 0.0, None),
)
_SCRIPT_SINCA_SHA = _sha(b"descargar_sinca_meteorologia sintetico")


def _escribir_csv(ruta: Path, campos: Sequence[str], filas: Sequence[Mapping[str, Any]]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(campos), extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for f in filas:
        w.writerow(f)
    return _escribir(ruta, buf.getvalue().encode("utf-8"))


def sinca_sintetico(raiz, *, desde: str = "2019-01-01", hasta: str = "2019-01-31",
                    semilla: int = SEMILLA_POR_OMISION) -> Path:
    """La carpeta de la meteorología SINCA (SIN-15) en ``raiz``: las series por parámetro, ``manifiesto_descarga.csv``
    y ``manifiesto_descarga_20261024b.csv`` (estaciones disjuntas), sus ``SHA256SUMS*.txt`` y los
    ``no_disponibles*.csv`` (idénticos). Devuelve la raíz."""
    base = destino_temporal(raiz)
    base.mkdir(parents=True, exist_ok=True)
    manifiestos: dict[str, list[dict]] = {"": [], SUFIJO_SEGUNDO_MANIFIESTO: []}
    for n_serie, (sufijo, region, est, nombre, param, altura, huecos, especiales) in enumerate(_SERIES_SINCA):
        rng = _rng(semilla, "sinca", str(n_serie))
        macro = f"horario_{altura:03d}" + ("_b" if (est == "D12" and param == "TEMP" and huecos) else "")
        texto, resumen = _serie_sinca(param, desde, hasta, rng, huecos=huecos, especiales=especiales)
        datos = texto.encode("utf-8")
        relativa = f"{param}/{region}_{est}_{param}_{macro}_{desde}_{hasta}.csv"
        sha = _escribir(base / relativa, datos)
        variable, unidad = _PARAMETROS_SINCA[param]
        sufijo_serie = "_spec" if param == "WDIR" else ""
        manifiestos[sufijo].append({
            "region": region, "estacion": est, "nombre": nombre, "parametro": param, "variable": variable,
            "macro_ficha": macro, "macro_exportada": f"./{region}/{est}/Met/{param}//{macro}{sufijo_serie}.ic",
            "altura_ficha": str(altura), "unidad_ficha": unidad, "instrumento_ficha": "sensor sintético",
            "desde_ficha": desde.replace("-", "")[2:], "hasta_ficha": hasta.replace("-", "")[2:], "desde": desde,
            "hasta": hasta, "ruta_relativa": relativa, "bytes": len(datos), "sha256": sha, **resumen,
            "url_fuente": f"{URL_FALSA}/sinca/{region}/{est}/{param}", "accion": "descargado",
            "ficha_sha256": _sha(f"ficha {region} {est}".encode()), "config_estaciones_sha256": _sha(b"config sinca"),
            "marca_temporal": "hora_local_civil_sinca_sin_offset", "politica_temporal_sha256": POLITICA_TEMPORAL_SHA,
            "script_version": "1.0.0", "script_sha256": _SCRIPT_SINCA_SHA,
            "registrado_utc": "2026-10-24T12:00:00+00:00"})
    faltante = [{"region": "RM", "estacion": "D13", "nombre": "Estación sintética D", "parametro": "TEMP",
                 "macro_ficha": "horario_002", "macro_exportada": "./RM/D13/Met/TEMP//horario_002.ic", "desde": desde,
                 "hasta": hasta, "motivo": "macro_inexistente: la macro no existe en SINCA",
                 "url_fuente": f"{URL_FALSA}/sinca/RM/D13/TEMP", "registrado_utc": "2026-10-24T12:00:00+00:00"}]
    for sufijo, filas in manifiestos.items():
        filas = sorted(filas, key=lambda f: (f["region"], f["estacion"], f["parametro"], f["macro_ficha"]))
        _escribir_csv(base / f"manifiesto_descarga{sufijo}.csv", CAMPOS_MANIFIESTO_SINCA, filas)
        _escribir_csv(base / f"no_disponibles{sufijo}.csv", CAMPOS_FALTANTES_SINCA, faltante)
        lineas = sorted(f"{f['sha256']}  {f['ruta_relativa']}" for f in filas)
        _escribir(base / f"SHA256SUMS{sufijo}.txt", ("\n".join(lineas) + "\n").encode("utf-8"))
    return base


def huellas_sinca(raiz) -> dict[str, str]:
    """sha256 de los manifiestos, sus SHA256SUMS y los no disponibles de una carpeta SINCA sintética."""
    base = destino_temporal(raiz)
    nombres = [f"{p}{s}.{e}" for s in ("", SUFIJO_SEGUNDO_MANIFIESTO)
               for p, e in (("manifiesto_descarga", "csv"), ("SHA256SUMS", "txt"), ("no_disponibles", "csv"))]
    return {n: _sha((base / n).read_bytes()) for n in nombres}


# ---------------------------------------------------------------------------
# Paneles y pliegues de la red 2 (SIN-16; MC-09)
# ---------------------------------------------------------------------------
_MONITORES = (("S001", -33.45, -70.66), ("S002", -33.50, -70.60), ("S003", -33.40, -70.75), ("S004", -33.60, -70.70),
              ("S005", -33.55, -70.55), ("S006", -32.95, -71.50), ("S007", -33.05, -71.60), ("S008", -36.80, -73.05),
              ("S009", -36.75, -72.95), ("S010", -36.60, -72.10), ("S011", -33.48, -70.68), ("S012", -34.17, -70.74))
_REGION_MONITOR = {"S006": "RV", "S007": "RV", "S008": "RVIII", "S009": "RVIII", "S010": "RXVI", "S012": "RVI"}


def _bloque_blq75(lat: float, lon: float) -> tuple[str, float, float]:
    """(etiqueta «E<ix>N<iy>» de BLQ-75, este, norte) en EPSG:32719 con origen (0, 0) y lado de 75 km."""
    from pyproj import Transformer
    este, norte = Transformer.from_crs("EPSG:4326", "EPSG:32719", always_xy=True).transform(float(lon), float(lat))
    lado = 75_000.0
    return ETIQUETA_BLQ.format(ix=int(math.floor(este / lado)), iy=int(math.floor(norte / lado))), float(este), float(norte)


def huella_pliegues(manifiesto: Mapping[str, Any]) -> str:
    """La de ``pliegues_v2.huella_pliegues``: sha256 del JSON canónico de v2 de ``CLAVES_HUELLA_PLIEGUES``."""
    return _sha(_json_canonico({k: manifiesto.get(k) for k in CLAVES_HUELLA_PLIEGUES}))


def panel_y_pliegues(raiz, *, desde: str = "2019-01-01", hasta: str = "2019-01-31",
                     semilla: int = SEMILLA_POR_OMISION) -> dict:
    """Paneles ``paneles/panel_{pm25,no2}_red2.parquet`` (con su .json) y ``pliegues_v2_red2.json`` de la red 2
    (SIN-16), bajo ``raiz``. El monitor «S012» no tiene observaciones de NO2 (un monitor-año sin datos, MC-09).
    Devuelve las rutas y la tabla de monitores."""
    base = destino_temporal(raiz)
    tiempos = pd.date_range(desde, pd.Timestamp(hasta) + pd.Timedelta(hours=23), freq="h")
    rng = _rng(semilla, "panel")
    lat = np.array([m[1] for m in _MONITORES])
    lon = np.array([m[2] for m in _MONITORES])
    celdas = _id_celda(lat, lon)
    monitores = pd.DataFrame({"estacion": [m[0] for m in _MONITORES], "lat": lat, "lon": lon, "celda": celdas,
                              "region_sinca": [_REGION_MONITOR.get(m[0], "RM") for m in _MONITORES]})
    monitores = monitores.astype({"estacion": "string", "region_sinca": "string"})
    rutas: dict[str, Any] = {}
    paneles = {}
    for pol, media in (("pm25", 25.0), ("no2", 18.0)):
        partes = []
        for fila in monitores.itertuples(index=False):
            if pol == "no2" and fila.estacion == "S012":
                continue
            presente = rng.random(len(tiempos)) > 0.1
            obs = np.maximum(rng.normal(media, media / 3, len(tiempos)), 0.5)[presente]
            ts = tiempos[presente]
            partes.append(pd.DataFrame({"estacion": fila.estacion, "ts_utc": ts.to_numpy("datetime64[ns]"),
                                        "obs": obs.astype(np.float32), "n": np.ones(len(ts), np.int8),
                                        "version": "sinca", "celda": np.int64(fila.celda),
                                        "region_sinca": fila.region_sinca, "lat_est": np.float32(fila.lat),
                                        "lon_est": np.float32(fila.lon), "anio": ts.year.astype(np.int16),
                                        "pob_dens": np.float32(1500.0)}))
        panel = pd.concat(partes, ignore_index=True)[list(COLUMNAS_PANEL_RED2)]
        panel = panel.astype({"estacion": "string", "version": "string", "region_sinca": "string"})
        buf = io.BytesIO()
        panel.to_parquet(buf, index=False)
        ruta = base / "paneles" / f"panel_{pol}_red2.parquet"
        sha = _escribir(ruta, buf.getvalue())
        _escribir(ruta.with_suffix(".json"), _json_canonico({"schema": "meteo-combinada-sintetico-panel-red2/1",
                                                             "sha256": sha, "redes": ["sinca"]}))
        rutas[f"panel_{pol}"] = ruta
        paneles[pol] = {"ruta": f"paneles/panel_{pol}_red2.parquet", "sha256": sha, "filas": int(len(panel)),
                        "estaciones": int(panel["estacion"].nunique())}
    registro = []
    for f in monitores.itertuples():
        bloque, este, norte = _bloque_blq75(f.lat, f.lon)
        registro.append({"estacion": str(f.estacion), "nombre": f"Monitor sintético {f.estacion}", "red": "sinca",
                         "region_sinca": str(f.region_sinca),
                         "region_lro": EQUIVALENCIAS_LRO.get(str(f.region_sinca), str(f.region_sinca)),
                         "cod_comuna": 13101, "lat": float(f.lat), "lon": float(f.lon), "celda": int(f.celda),
                         "utm19s_este_m": este, "utm19s_norte_m": norte, "bloque_blq75": bloque})
    contaminantes = {}
    for pol in CONTAMINANTES_M6:
        en_panel = [r for r in registro if not (pol == "no2" and r["estacion"] == "S012")]
        protocolos = {}
        for prot, clave in (("LRO", "region_lro"), ("BLQ-75", "bloque_blq75")):
            grupos = sorted({r[clave] for r in en_panel})
            pliegues = []
            for k, g in enumerate(grupos):
                miembros = sorted(r["estacion"] for r in en_panel if r[clave] == g)
                pliegues.append({"k": k, "semilla": [42, k], "grupo": g, "estaciones_prueba": miembros,
                                 "excluidas": miembros})
            protocolos[prot] = {"n_pliegues": len(pliegues), "pliegues": pliegues}
        contaminantes[pol] = {"panel": paneles[pol], "estaciones": sorted(r["estacion"] for r in en_panel),
                              "protocolos": protocolos}
    parametros = {"distancias": {"formula": "haversine", "radio_tierra_km": R_TIERRA_KM},
                  "BLQ-75": {"crs": "EPSG:32719", "lado_m": 75000.0, "origen_m": [0.0, 0.0], "etiqueta": ETIQUETA_BLQ},
                  "LRO": {"grupo": "region_sinca", "equivalencias": dict(EQUIVALENCIAS_LRO)},
                  "semilla": {"regla": [42, "k"], "orden_k": "posición lexicográfica de la etiqueta"}}
    manifiesto = {"schema": ESQUEMA_PLIEGUES_V2, "schema_red2": ESQUEMA_PLIEGUES_RED2, "bloque": dict(BLOQUE_RED_AMPLIADA),
                  "parametros": parametros, "estaciones": registro, "contaminantes": contaminantes}
    manifiesto["huella_pliegues"] = huella_pliegues(manifiesto)
    rutas["pliegues"] = base / NOMBRE_PLIEGUES_RED2
    _escribir(rutas["pliegues"], json.dumps(manifiesto, ensure_ascii=False, indent=1).encode("utf-8") + b"\n")
    return {**rutas, "monitores": monitores}
