"""Control de calidad de la DMC (§2.1-§2.7): orden por artefacto, envoltorio ``qc_meteo_combinada``, K4, marcas y alarmas.

El envoltorio sólo puede quitar ``usable``, nunca darlo; las derivadas van aparte (§2.4, «Monotonía»). La mediana y
el MAD de la marca 13, la mediana de la marca 14 y los estadísticos de K4 se calculan en memoria y no se guardan
(§0.4.6).

Qué hace cada parte (el orden de §2.1):
- **Paso 1, por artefacto**: ``normalizar_artefacto`` (``leer_artefacto``, las políticas que cruzan el mes, el
  validador de RELOJ y ``cargar_dmc``) da un ``tipos.ResultadoArtefacto``; ``unir_largas`` junta las tablas largas de
  una estación con su ``id_artefacto``.
- **Paso 2**: ``qc_meteo_combinada``, las reglas de §2.4 salvo la marca 14, sobre la tabla larga de la estación. Da la
  **tabla intermedia** (una fila por etiqueta, con columnas privadas «_…» que necesitan los pasos siguientes y los
  conteos).
- **Paso 3**: ``entrada_k4`` (la entrada del acuerdo A4) y ``k4_estacion`` (llama a ``homogeneidad.k4``).
- **Paso 4**: ``aplicar_k4`` (marcas 1, 16 y 21) y ``marca_14`` (con los tramos de la política efectiva, D24).
  ``qc_estacion`` encadena los pasos 2 a 4 de una estación.
- **Paso 5**: ``tabla_ancha`` (``tipos.ESQUEMA_QC_ESTACION``; la escribe ``salidas``).
- **Conteos y alarmas** (§2.7): ``conteos_estacion``, ``conteos_artefactos``, ``tabla_no_normalizables``,
  ``alarmas``, ``lista_descriptiva`` y ``resumen_qc`` (``qc/resumen_qc.json``, clase «resumen»).
- **RR06** (§2.6): ``sumas_lluvia_rr06`` (D27) y ``validar_rr06``.

Dueño: I12 (ola 3).

Lecturas propias (QC-n), para el addendum de M1:
- QC-1. **Paso 1** (§2.1; A6, POL-11, POL-13). ``normalizar_artefacto`` lee el artefacto con ``leer_artefacto`` del
  adaptador (da ``content_sha256``), toma de ``politicas`` las de la estación que cruzan el mes de etiqueta
  (``politicas_que_cruzan``), las pasa por ``politicas.validar_reglas`` con el validador de RELOJ (una regla rechazada
  no se entrega; ``reglas_rechazadas`` trae sus ids de RELOJ, «1.1») y llama a ``cargar_dmc([manifiesto], aceptadas,
  adapter_sha256=…)``. El código, el año y el mes salen de la ruta que escribe el descargador
  («estaciones/<código>/<AAAA-MM>.manifest.json»), sin leerla; el ``id_artefacto`` (índice en
  ``artefactos_evaluados``) lo da quien llama (argumento nuevo, ver «Firmas»). ``sha_adaptador`` debe ser
  ``fijados.SHA_ADAPTADOR`` (f61559ea…): si no, ``ValueError`` antes de leer, porque ``cargar_dmc`` lo rechazaría
  dentro de la captura y un error de configuración quedaría contado como «no normalizable». «Por artefacto de
  ``artefactos_evaluados``» (§2.1, paso 1) se comprueba como la comprobación 7 de RELOJ («el artefacto … no es un
  artefacto evaluado de la estación»): ``artefactos`` es el mapa sha256 → código de ``politicas.leer_politica_reloj``
  (argumento nuevo), y si el ``content_sha256`` leído no está en él o es de otra estación, ``ValueError`` fuera de la
  captura (un artefacto ajeno no se normaliza ni cuenta en Q1 a Q3). Si ``leer_artefacto`` falla no hay sha256 que
  comprobar: cuenta como «no normalizable» de origen «datos», como en RELOJ. El mapa no trae el orden de la lista, así
  que el ``id_artefacto`` no se coteja con él: que sea el índice del artefacto en ``artefactos_evaluados`` lo asegura
  quien llama (I20).
- QC-2. **Qué se captura** (§2.1; MC-57). Sólo ``ValueError`` y ``TypeError`` de ``leer_artefacto``, de
  ``normalizar`` y de ``cargar_dmc``. ``fondo_era5l.ErrorFondo`` (un ``RuntimeError``, FON-2), ``KeyError``,
  ``OSError`` y lo que no sea ``ValueError`` del validador de RELOJ (POL-11) no se capturan: detienen la corrida como
  error de código y nunca cuentan como «no normalizables». Las funciones de los pasos 2 a 5 no capturan nada.
- QC-3. **Origen del aborto** (MC-21, como la comprobación 7 de RELOJ: ``reloj_dmc.politica._comprobacion_7``).
  «datos» si falla ``leer_artefacto``, o si con el mismo artefacto abortan también ``normalizar(payload,
  politica=None)`` o ``cargar_dmc([manifiesto], [])``; si no, «regla». Consecuencia mecánica: un código QC presente
  sale «regla», porque ``cargar_dmc`` sólo mira el código en las filas ``model_ready`` (``dmc_features.py``:75-76 y
  85-87), aunque sea un defecto del artefacto. Los dos orígenes cuentan en Q3.
- QC-4. **Motivo** (``tipos.MotivoNoNormalizable``), por el texto del error del código fijado (``_TEXTOS_ABORTO``,
  comparados en una prueba con el código fijado): «Viento fuera de dominio» se separa mirando el contenido del
  artefacto (una dirección fuera de [0, 360] primero, después una rapidez negativa); «Hora no nativa o duplicada» y
  «Observaciones DMC duplicadas/conflictivas» son hora no nativa o repetida; «Código QC presente…»; el intervalo no
  entero y el límite que no es de Python sólo si alguna regla entregada a ``cargar_dmc`` lo tiene (también cuando el
  número de numpy aborta antes, en la huella JSON de la política: «… is not JSON serializable», de
  ``meteorologia_v2._sha_json``; así aborta un límite en float32); las huellas o el tamaño del artefacto; «Sin
  observaciones DMC». Lo demás, «otro».
- QC-5. **Tabla intermedia** (§2.3 del diseño). Una fila por etiqueta (``timestamp_source``) de la estación; ``h`` es la
  hora UTC exacta de ``timestamp_utc`` (una hora UTC con minutos es un ``ValueError``: la regla de reloj estaría mal).
  Las filas sin reloj confirmado no tienen ``h``: llevan la marca 0 en las siete columnas, cuentan en los conteos con
  el año de su etiqueta y no van a la tabla ancha, cuya ``h`` es la «hora UTC del reporte (reloj confirmado)». El
  ``tramo`` es el id del ``TramoPolitica`` de la lista completa de lectura de la estación (``tramos_de_politicas``,
  POL-10) cuyo intervalo de etiquetas, inclusivo, contiene la etiqueta (A6); sin tramo, nulo.
- QC-6. **Dos etiquetas con la misma hora UTC** (en artefactos distintos de la estación; dentro de un artefacto,
  ``cargar_dmc`` aborta). No se promedian ni se elige una (como el adaptador: «no se promedian conflictos»): las dos
  quedan fuera de la tabla ancha, sin marca, y se cuentan («colision_utc»). El texto calla; es la pregunta QC-P1.
- QC-7. **Decimales.** Las reglas comparan los valores float64 de la fuente (``value`` de ``cargar_dmc``; la tabla
  ancha los guarda en float32), y toda comparación de una diferencia con un umbral se hace después de redondearla a
  10⁻⁹: los valores DMC traen a lo más un decimal y los umbrales a lo más cuatro, así que es la comparación decimal del
  texto sin el ruido del punto flotante (por ejemplo, 18,1 − 10,1 no supera 8). La identidad de las rachas es exacta.
  Las marcas 13 y 14 usan los float32 de la observación y del fondo (FON-8, como ``fondo_era5l.residuos``).
- QC-8. **Hora válida** (§2.1), por variable de la fuente: ``usable`` de ``cargar_dmc``, ningún bit invalidante en su
  columna de marcas, con ``h`` y sin colisión. ``valido_*`` exige además que la estación no esté excluida
  (``InfoEstacion.excluida``: «la estación y el tramo no están excluidos»). Las reglas corren también sobre las
  estaciones excluidas, cuyas horas cuentan en Q1 y Q2 como dice §2.7 (A7: pasan igual por el paso 1).
- QC-9. **Dónde se escribe cada marca** (D11, D21, TIP-9; §2.4). En la columna de cada variable que invalida,
  también las arrastradas: 0 y 1 («toda la fila») en las siete; 2, 3, 5 (Ts, Td, HR, QFE, QFF), 6 y 13 en la suya (la
  13 de Td sólo en Td, MC-26; el pico de la rapidez sólo en FF); 4 en Ts, Td y HR, o en QFE y QFF; 7, 9 y 17 en Td y
  HR; 5 del viento (D21), 11 y 12 en FF y DD; 14 en QFE; 16 en QFE y QFF. Una marca se escribe en sus variables
  destino aunque otra regla ya las haya quitado: sólo las entradas de la regla deben seguir válidas (MC-24). Así una
  hora puede llevar varias marcas invalidantes, y Q1 cuenta cada marca en las horas de su denominador que la llevan
  (pregunta QC-P6). Las informativas: 8 y 10 en Td; 15 en HR; 18 en la variable del desvío; 19 en FF y DD (las horas
  con DD = 0 y FF > 0 de un estación-año «cero_es_norte»); 20 en FF y DD; 21 en QFE y QFF de todas las filas; 22 en
  las siete, en toda la estación, junto al bit 2 (TIP-4).
- QC-10. **Orden** (MC-24 con la corrección D7). (1) Bits 0-3 de ``cargar_dmc``: 0, ``clock_verified`` falso; 1,
  ``coordinates_verified`` falso, o la estación sin coordenadas legibles, con K3 fallida o en la lista K2 (la regla de
  ``politicas._estado_coordenadas``, POL-5) y, en el paso 4, K4; 2, ``measurement_verified`` falso (y 22 si la
  estación tiene «posible media horaria»: alguna regla ``measurements`` de lectura lleva ese motivo, POL-6); 3,
  ``quality_reason`` = «documented_numeric_range_rejected». (2) Centinelas, **sobre el valor de la fuente aunque una
  regla anterior lo haya quitado** (D7). (3) Rachas y calma. (4) Picos y saltos. (5) Td frente a Ts. (6)
  Incoherencia. (7-8) HR recortada y Td derivado (QC-14). (9) Viento. (10) Aire seco. (11) Error grueso. (12) K4 y
  retirada. (13) Marca 14. Cada regla mira sólo los valores que siguen válidos tras las anteriores; las de un mismo paso
  miran lo mismo.
- QC-11. **Rachas** (§2.4; MC-22). La serie de una variable son sus valores válidos en orden de ``h``; dos son
  consecutivos si distan ≤ 3 h; una racha es una sucesión máxima de consecutivos idénticos con ≥ 4 reportes cuya
  duración, t_último − t_primero + la mediana de sus Δt, alcanza el lapso. Ts, QFE y QFF: 12 h. HR: 48 h con HR = 100;
  12 h con cualquier otro valor, también 100 < HR ≤ 103, que el texto no nombra (lectura más estricta; pregunta QC-P2).
  Td: 12 h sobre la serie de Td sin las horas con HR = 100 válida, que se quitan de la serie y no la cortan si el hueco
  queda ≤ 3 h (pregunta QC-P3). Viento: la serie de pares (FF, DD) válidos, con la racha de pares idénticos con FF > 0,
  12 h. Calma: la serie de FF válida, con la racha de FF = 0, 48 h.
- QC-12. **Picos y saltos** (MC-23). Sobre Ts (8 K), Td (10 K), QFE y QFF (4 hPa) y FF (15 m/s), con los valores
  válidos tras las rachas. Pico: el valor i con vecinos consecutivos a cada lado (Δt ≤ 3 h), cuyas dos diferencias
  superan θ·f con signo opuesto, con f del mayor de los dos Δt (1 con 1 h; 1,5 con 2-3 h). Después, sin los picos,
  el salto único: una diferencia entre consecutivos mayor que 2·θ·f, con f de su Δt, invalida sólo el valor posterior
  (no se encadena).
- QC-13. **Td y HR** (§2.4; MC-25). Marca 7 donde Td y Ts son válidas y Td − Ts > 0,5 K. Marca 9 donde Td, HR y Ts son
  válidas: |Td − Td_M(HR, Ts)| > 2,0 K y |HR − HR_M(Td, Ts)| > 5 puntos con Magnus sobre agua y, con Ts < 0 °C,
  también sobre hielo (Td como punto de escarcha, la HR respecto del agua; la inversa sobre hielo con
  ``MAGNUS_HIELO``). «Bajo 0 °C» es Ts < 0 (pregunta QC-P5). La HR es la observada, antes del recorte. Se cuenta con
  cuál calzaron las horas bajo 0 °C que no se marcan: agua, hielo o las dos («calza_*», MC-25).
- QC-14. **Derivadas** (§2.4, «Monotonía»; MC-24, pasos 7 y 8). Se recalculan al final de cada paso (envoltorio, K4 y
  marca 14) desde la validez final, así que nunca quedan derivadas de una fuente que una regla posterior quitó.
  ``hr_final``: HR válida; 100 si 100 < HR ≤ 103 (marca 15). ``td_final``: Td válida, = Ts si Ts es válida y
  0 < Td − Ts ≤ 0,5 (marca 8); sin valor de Td en la fuente («sin Td»: pregunta QC-P4), con HR y Ts válidas, Magnus⁻¹
  sobre agua con ``hr_final`` (marca 10; con el recorte de §3 da lo mismo que con la HR observada). ``u_final`` y
  ``v_final``: con FF y DD válidas, las ``wind_u`` y ``wind_v`` del adaptador (+0,0, para no guardar −0); con FF = 0,
  u = v = 0 (§2.4, «Calma»); origen «cero_es_norte» con la marca 19; con FF = 0 válida y DD sin valor, u = v = 0
  (marca 20). Las marcas 8, 10, 15 y 20 describen el origen de la derivada final y se recalculan con ella.
- QC-15. **Viento** (§2.4). La regla del cero va por estación y año de la etiqueta (MC-58), sobre las horas con FF > 0
  y DD válidas: sin ningún 360 y con ceros en ≥ 1 % de ellas (comparación entera), el año es «cero_es_norte» (marca
  19); si no, todo DD = 0 con FF > 0 lleva la marca 11 (también sin ningún 360, por la columna «Regla» de la tabla).
- QC-16. **Aire seco** (marca 17). HR válida < 2 (``SECO_HR_PCT``, en unidades de HR, UMB-12) en una sucesión máxima de
  reportes consecutivos con ≥ 3 reportes (``SECO_MIN_REPORTES``) y duración (MC-22) ≥ 6 h.
- QC-17. **Error grueso** (marcas 13 y 18; MC-26, MC-22). Base: los valores válidos tras los pasos 1 a 10, con el fondo
  de ``fondo_era5l.en_horas`` (A2). r_T y r_Td salen de ``fondo_era5l.residuos`` (Td con ``td_final`` observado o
  recortado; el derivado no entra ni se marca); en la presión, QFE − p_F en hPa con los float32 (A3: no es r_p).
  Celdas (mes del año UTC, hora UTC) con ≥ 30 valores; si no, (mes); si no, la marca no se evalúa en ese
  estación-mes. U = máx(θ_g; 6·1,4826·MAD). Un desvío es una sucesión máxima de reportes evaluados consecutivos
  (Δt ≤ 3 h, en la serie de los evaluados) con |r − med| > U/2 del mismo signo y alguno > U; un reporte suelto o una
  sucesión de < 3 h invalida los que superan U; de 3 a 24 h, marca 18 en todos; de más de 24 h, marca 13 en todos.
  La mediana y el MAD viven sólo dentro de la función. Sin fondo (``F_estacion`` None, la estación «sin_fondo»), las
  marcas 13 y 14 no se evalúan y K4 va sin T2b.
- QC-18. **K4** (A4, HOM-9). ``entrada_k4`` da ``h``, Ts, QFE y QFF en las filas con ``h`` (orden creciente) con NaN
  donde no son válidas tras el paso 2 (el envoltorio sin la marca 14), y p_F de ``en_horas``. ``k4_estacion`` llama a
  ``homogeneidad.k4(…, codigo=info.codigo)`` con ``z_cat``. ``ResultadoK4.D`` nunca sale de memoria.
- QC-19. **Retirada** (§2.1, paso 4; §2.5; A4). ``aplicar_k4``: marca 1 en las siete columnas de las filas con
  mes2000(h) < ``ultimo_traslado`` (cuentan en el numerador de Q2 como «K4»); marca 16 en QFE y QFF con mes2000(h) <
  ``ultimo_barometro``; marca 21 si ``sin_prueba``. Releer con la política efectiva da las mismas filas con
  coordenadas confirmadas que las que quedan sin marca 1 (MC-53; prueba con ``cargar_dmc`` real).
- QC-20. **Marca 14** (D24, POL-14). Los tramos son los de la política efectiva (``politicas.tramos_marca_14``). Las
  horas de un tramo son las de etiqueta dentro de su intervalo inclusivo; la mediana es la de float32(QFE) − p_F en
  las que tienen QFE válida tras K4 y p_F finito; si |mediana| > 8 hPa, la marca 14 va en QFE en todas las filas del
  tramo con valor. Después de la marca 14 la columna ``tramo`` lleva los ids de la política efectiva, la publicada
  (antes, los de lectura, A6): es la pieza en que se tomó la mediana y la que elige ``cargar_dmc`` al releer con la
  efectiva (pedido al coordinador: anotarlo en A6).
- QC-21. **RR06** (§2.6). Del ``raw`` de la fila: «s/p» después de quitar los espacios de los bordes (``str.strip``:
  « s/p » también es 0 mm) es 0 mm, con esas minúsculas («S/P» u otra grafía es sin dato); si el adaptador lo leyó
  como número (``parse_status`` «numeric»), su ``value``; cualquier otro texto, sin dato. ``rr06_valido``:
  legible, en [0, 200] mm y con reloj y coordenadas confirmados (sin los bits 0 y 1, también después de K4).
  ``sumas_lluvia_rr06`` da la suma de 6 h del píxel que ``enlaces_productos.parquet`` enlaza a la celda de la
  estación (``fondo_era5l.pixel_de_lluvia`` y ``lluvia_rr06``, D27), por lotes de meses. ``validar_rr06`` recibe las
  tablas anchas y compara con esas sumas, alineadas con sus filas: los reportes sin enlace y los de ventana incompleta se cuentan aparte; por
  macrozona (sin macrozona, aparte, D9) y estación del año del mes UTC de ``h`` (DEF, MAM, JJA y SON; MC-64), y en lo
  nacional: los totales, su diferencia y su cociente («sesgo de totales»), la frecuencia de períodos con ≥ 1 mm de
  cada uno y la correlación de Pearson de los pares agrupados. El sujeto es «lluvia_producto» (MC-02, D3).
- QC-22. **Conteos** (EMC1-1, EMC1-3, D9, D11, D16, D36, D37, A15). Por estación, variable de la fuente
  (``tipos.VARIABLES_FUENTE``; ``wind_u`` y ``wind_v`` no entran) y año (el UTC de ``h``; el de la etiqueta sin
  ``h``). Denominadores: «horas» (con valor), «q1» (``usable``), «q1_rango» (``usable`` o rechazada por rango), «q2»
  (reloj y medición confirmados y con valor, salvo las estaciones con motivo de ``tipos.MOTIVOS_FUERA_DE_Q2``) y
  «q2_fuera» (esas, aparte). Numeradores: «marca_<nombre>» (horas con valor y esa marca), «q1_<nombre>» de cada marca
  de ``tipos.MARCAS_Q1`` (en la 3, las rechazadas por rango; en las demás, las ``usable`` con la marca), «q1_alguna»
  (para la lista), «q2_sin_coordenadas» (las de «q2» de una estación con motivo de
  ``tipos.MOTIVOS_SIN_COORDENADAS_K3`` o que K4 dejó sin coordenadas; nunca por ``coordinates.verified``),
  «colision_utc» y «calza_agua», «calza_hielo» y «calza_ambas» (en Td). La macrozona es
  ``tipos.macrozona_o_ninguna(info.macrozona)``: sin macrozona («sin_region», «insular» o sin celda) cuenta sólo en
  lo nacional (D9, D16, D20).
- QC-23. **Alarmas** (§2.7). Q1 por marca de ``tipos.MARCAS_Q1`` y variable de la fuente, en la red; Q1z por macrozona;
  Q2 por variable en los años 2000-2009 en la red y por macrozona (D10); Q3 con los artefactos evaluados. «Más del»
  es estricto y se compara con enteros (n·100 > pct·d). Un denominador 0 no da alarma. ``alarmas`` devuelve sólo las
  que saltan, con la identificación de §2.7: ``alarma``, ``regla`` (el nombre de la marca, «coordenadas» o
  «no_normalizable»), ``variable``, ``zona`` («nacional» o la macrozona) y ``tasa`` en por ciento.
- QC-24. **Lista descriptiva** (§2.7; EMC1-1). Una estación entra si en alguna variable de la fuente más del 30 % de
  sus horas «q1_rango» llevan una marca de ``tipos.MARCAS_Q1`` (o el rechazo por rango); se listan el código y esas
  variables.
- QC-25. **resumen_qc** (§8; §0.4.6; clase «resumen»). Sólo conteos (numeradores y denominadores por clave × variable
  × macrozona × conjunto, sumados en los años, y los de Q2 en 2000-2009), las alarmas, los «no normalizables» por
  motivo × origen × macrozona × conjunto, las estaciones sin prueba de traslado, las estaciones sin macrozona y la
  lista descriptiva. Ninguna mediana, MAD, residuo ni valor.
Firmas respecto de §3 del diseño (para el anexo de firmas):
- **Incompatibles** (sin valor por omisión): ``normalizar_artefacto(…, *, id_artefacto, artefactos)``
  (``artefactos``: el mapa sha256 → código de ``politicas.leer_politica_reloj``; QC-1);
  ``qc_meteo_combinada(…, *, k2, politicas)`` (``politicas``: las de lectura de la estación, la lista completa, para el
  ``tramo`` y la marca 22); ``marca_14(…, *, tramos)`` (los de ``politicas.tramos_marca_14``, D24);
  ``resumen_qc(…, *, denominadores, lista, umbrales)``; ``aplicar_k4(tabla, resultado, umbrales)`` (las derivadas se
  rehacen con los umbrales).
- **Aditivos:** ``unir_largas``, ``entrada_k4``, ``k4_estacion``, ``qc_estacion``, ``sumas_lluvia_rr06``,
  ``conteos_estacion``,
  ``conteos_artefactos``, ``tabla_no_normalizables``, ``lista_descriptiva``, ``COLUMNAS_CONTEO`` (pedido al
  coordinador: pasarlo a ``tipos`` como esquema) y las constantes de claves. ``qc_meteo_combinada`` acepta en
  ``larga`` la tabla de ``unir_largas`` o la lista de ``ResultadoArtefacto``.
Depende de: tipos, constantes, umbrales, numerico, fijados, politicas, homogeneidad, fondo_era5l.
"""
from __future__ import annotations

import math
import re
import warnings
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from meteo_combinada import constantes, fijados, fondo_era5l, homogeneidad, numerico, tipos
from meteo_combinada import politicas as _politicas
from meteo_combinada.tipos import (Alarma, Marca, MotivoNoNormalizable, OrigenAborto, OrigenHR, OrigenTd,
                                   OrigenViento, ResultadoArtefacto, ResultadoK4, TramoPolitica, VariableDMC)

# ---------------------------------------------------------------------------
# Constantes del módulo (nombres; los números vienen de Umbrales y de constantes)
# ---------------------------------------------------------------------------
_FUENTE = tuple(tipos.VARIABLES_FUENTE)
_CORTA = {v.value: tipos.COLUMNA_ANCHA[v] for v in _FUENTE}            # nombre del adaptador → columna ancha
_CORTAS = tuple(_CORTA.values())                                        # Ts, Td, HR, FF, DD, QFE, QFF
_DE_CORTA = {c: v for v, c in _CORTA.items()}
TS, TD, HR, FF, DD, QFE, QFF = _CORTAS
_COL_MARCAS = {tipos.COLUMNA_ANCHA[v]: tipos.COLUMNA_MARCAS[v] for v in _FUENTE}
_WIND_U, _WIND_V, _RR06 = VariableDMC.WIND_U.value, VariableDMC.WIND_V.value, VariableDMC.RR06.value

_BIT = {m: np.uint32(m.bit) for m in Marca}
_MASCARA_INVALIDA = np.uint32(sum(m.bit for m in Marca if tipos.INVALIDANTES[m].alcance is not tipos.Alcance.NO))
_MASCARA_Q1 = np.uint32(sum(m.bit for m in tipos.MARCAS_Q1))
_MASCARA_FILA = np.uint32(Marca.SIN_RELOJ.bit | Marca.SIN_COORDENADAS.bit)
_MASCARA_DERIVADAS = np.uint32(Marca.TD_RECORTADO.bit | Marca.TD_DERIVADO.bit | Marca.HR_RECORTADA.bit
                               | Marca.CALMA_SIN_DIRECCION.bit)

_DECIMALES = 9                     # no-umbral: redondeo de diferencias decimales a 10⁻⁹ antes de comparar (QC-7)
_REPORTES_PICO = 3                 # no-umbral: un pico necesita el valor y sus dos vecinos (§2.4)
_SIN_TRAMO = -1                    # no-umbral: índice nulo de tramo
_NORTE_SYNOP = 360                 # no-umbral: el código 360 de la regla del cero (§2.4; literal en la plantilla)
_SP = "s/p"                        # §2.6: «s/p» = 0 mm
_ESTACIONES_DEL_ANIO = ("DEF", "DEF", "DEF", "MAM", "MAM", "MAM", "JJA", "JJA", "JJA", "SON", "SON", "SON")  # mes % 12
_EPOCA = pd.Timestamp(tipos.EPOCA_H)
_UNA_HORA = pd.Timedelta(hours=1)
_PATRON_MANIFIESTO = re.compile(r"(?P<anio>\d{4})-(?P<mes>\d{2})\.manifest\.json")
_A_HIELO, _B_HIELO, _C_HIELO = constantes.valor("MAGNUS_HIELO")

# Textos de error del código fijado → motivo (QC-4). test_qc_dmc_meteo comprueba que siguen en el código fijado.
_TEXTOS_ABORTO = (
    ("SHA256 del artefacto no coincide", MotivoNoNormalizable.SHA_O_TAMANO),
    ("Tamaño del artefacto no coincide", MotivoNoNormalizable.SHA_O_TAMANO),
    ("Viento fuera de dominio", None),                                   # se separa por el contenido
    ("Hora no nativa o duplicada", MotivoNoNormalizable.HORA_NO_NATIVA_O_REPETIDA),
    ("Observaciones DMC duplicadas/conflictivas", MotivoNoNormalizable.HORA_NO_NATIVA_O_REPETIDA),
    ("Código QC presente", MotivoNoNormalizable.CODIGO_QC_PRESENTE),
    ("La medición necesita estadístico e intervalo", MotivoNoNormalizable.INTERVALO_NO_ENTERO),
    ("Límites QC documentados inválidos", MotivoNoNormalizable.LIMITE_NO_PYTHON),
    ("Sin observaciones DMC", MotivoNoNormalizable.SIN_OBSERVACIONES),
)
# El TypeError de ``json`` en ``meteorologia_v2._sha_json`` y ``dmc_features.hash_json`` (huellas de la política):
# un número de numpy en una regla (un límite en float32) aborta allí, antes del control de rango (QC-4).
_TEXTO_JSON = "is not JSON serializable"

# Conteos (QC-22): una fila por estación × año × variable × clave. Pedido al coordinador: pasarlo a tipos.
COLUMNAS_CONTEO = {"codigo": "string", "conjunto": "string", "macrozona": "string", "anio": "int16",
                   "variable": "string", "clave": "string", "n": "int64"}
DEN_HORAS, DEN_Q1, DEN_Q1_RANGO, DEN_Q2, DEN_Q2_FUERA = "horas", "q1", "q1_rango", "q2", "q2_fuera"
DEN_ARTEFACTOS = "artefactos_evaluados"
NUM_Q1_ALGUNA, NUM_Q2, NUM_COLISION = "q1_alguna", "q2_sin_coordenadas", "colision_utc"
NUM_NO_NORMALIZABLES = "artefactos_no_normalizables"
_CALZA_AGUA, _CALZA_HIELO = 1, 2
NUM_CALZA = {_CALZA_AGUA: "calza_agua", _CALZA_HIELO: "calza_hielo", _CALZA_AGUA | _CALZA_HIELO: "calza_ambas"}
VARIABLE_ARTEFACTO = "artefacto"
ZONA_NACIONAL = "nacional"
REGLA_Q2, REGLA_Q3 = "coordenadas", "no_normalizable"
ESQUEMA_RESUMEN_QC = "meteo-combinada-resumen-qc/1"
ESQUEMA_RR06 = "meteo-combinada-rr06/1"
SUJETO_RR06 = "lluvia_producto"


def clave_marca(m) -> str:
    """«marca_<nombre>»: horas con valor y esa marca (QC-22)."""
    return f"marca_{Marca(m).nombre_texto}"


def clave_q1(m) -> str:
    """«q1_<nombre>»: el numerador de Q1 de la marca (EMC1-1; QC-22)."""
    return f"q1_{Marca(m).nombre_texto}"


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def _r(x) -> np.ndarray:
    """QC-7: una diferencia, en decimal (redondeada a 10⁻⁹)."""
    return np.round(np.asarray(x, dtype=np.float64), _DECIMALES)


def _f4(x) -> np.ndarray:
    return np.asarray(x, dtype=np.float64).astype(np.float32).astype(np.float64)


def _exigir_info(info) -> str:
    if not isinstance(info, tipos.InfoEstacion):
        raise TypeError("se espera una tipos.InfoEstacion")
    if not isinstance(info.codigo, str) or not tipos.PATRON_CODIGO.fullmatch(info.codigo):
        raise ValueError(f"código de estación inválido: {info.codigo!r}")
    return info.codigo


def _conjunto_k2(k2) -> frozenset[str]:
    """La lista K2 como conjunto de códigos (un texto o un objeto se rechazan, como POL-5)."""
    if isinstance(k2, (str, bytes, bytearray, Mapping)) or k2 is None:
        raise ValueError(f"k2 es un conjunto de códigos de la lista K2, no {type(k2).__name__}")
    salida = frozenset(k2)
    if not all(isinstance(c, str) and tipos.PATRON_CODIGO.fullmatch(c) for c in salida):
        raise ValueError("k2 debe traer códigos de 6 dígitos")
    return salida


def _coordenadas_de_estacion(info, k2: frozenset[str]) -> bool:
    """Las coordenadas de la estación en todo su registro, antes de K4 (la regla de POL-5): legibles, K3 y K2."""
    try:
        legibles = math.isfinite(float(info.lat)) and math.isfinite(float(info.lon))
    except (TypeError, ValueError):
        legibles = False
    return legibles and info.k3_pasa is True and info.codigo not in k2


def _segmentos(une: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray]:
    """(inicios, finales) inclusivos de las sucesiones de una serie de n elementos; ``une[i]`` une i + 1 con i."""
    if n == 0:
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64)
    inicio = np.r_[True, ~np.asarray(une, dtype=bool)]
    a = np.flatnonzero(inicio)
    b = np.r_[a[1:] - 1, n - 1]
    return a, b


def _duracion(t: np.ndarray, a: int, b: int) -> float | None:
    """MC-22: t_último − t_primero + la mediana de sus Δt; None para un reporte suelto."""
    if b <= a:
        return None
    dt = np.diff(t[a:b + 1])
    return float(t[b] - t[a] + np.median(dt))


def _factor_f(dt: np.ndarray, U) -> np.ndarray:
    """f de §2.4 por Δt (1 con 1 h; 1,5 con 2-3 h); NaN fuera de esos Δt."""
    dt = np.asarray(dt, dtype=np.float64)
    f = np.full(dt.shape, np.nan)
    f[dt == U.a("DT_1H")] = U.a("F_1H")
    f[(dt >= U.a("DT_23_DESDE")) & (dt <= U.a("DT_23_HASTA"))] = U.a("F_23H")
    return f


def _td_desde_e_hielo(e_hpa) -> np.ndarray:
    """La inversa de Magnus sobre hielo: el punto de escarcha (°C) de una presión de vapor (hPa) (MC-25)."""
    lg = np.log(np.asarray(e_hpa, dtype=np.float64) / _A_HIELO)
    return _C_HIELO * lg / (_B_HIELO - lg)


# ---------------------------------------------------------------------------
# Paso 1 (§2.1): por artefacto
# ---------------------------------------------------------------------------
def _ruta_manifiesto(manifiesto) -> tuple[Path, str, int, int]:
    ruta = Path(manifiesto)
    m = _PATRON_MANIFIESTO.fullmatch(ruta.name)
    codigo = ruta.parent.name
    if m is None or not tipos.PATRON_CODIGO.fullmatch(codigo):
        raise ValueError(f"el manifiesto no tiene la forma «estaciones/<código>/<AAAA-MM>.manifest.json»: {ruta.name}")
    anio, mes = int(m.group("anio")), int(m.group("mes"))
    if not 1 <= mes <= 12:
        raise ValueError(f"mes imposible en el manifiesto: {ruta.name}")
    return ruta, codigo, anio, mes


def _fuera_de_dominio(payload: Mapping) -> MotivoNoNormalizable:
    """QC-4: «Viento fuera de dominio» del adaptador, separado por el contenido del artefacto."""
    direccion = rapidez = False
    for fila in payload.get("rows", []):
        campos = fila.get("fields", {})
        for variable, campo in campos.items():
            valor = campo.get("value") if campo.get("parse_status") == "numeric" else None
            if valor is None or isinstance(valor, bool) or not isinstance(valor, (int, float)):
                continue
            if variable == VariableDMC.DD.value and not 0 <= valor <= _NORTE_SYNOP:
                direccion = True
            elif variable == VariableDMC.FF.value and valor < 0:
                rapidez = True
    if direccion:
        return MotivoNoNormalizable.DD_FUERA_DE_DOMINIO
    return MotivoNoNormalizable.RAPIDEZ_NEGATIVA if rapidez else MotivoNoNormalizable.OTRO


def _regla_con(politicas_entregadas: Sequence[Mapping], que: str) -> bool:
    """¿Alguna regla entregada tiene un intervalo no entero («intervalo») o un límite que no es de Python («limite»)?"""
    for p in politicas_entregadas:
        if que == "intervalo":
            for regla in (p.get("measurements") or {}).values():
                minutos = regla.get("interval_minutes") if isinstance(regla, Mapping) else None
                if type(minutos) is not int:
                    return True
        else:
            for regla in (p.get("quality") or {}).values():
                if not isinstance(regla, Mapping):
                    continue
                if any(type(regla.get(k)) not in (int, float) for k in ("minimum", "maximum")):
                    return True
    return False


def _motivo(error: BaseException, payload: Mapping | None, entregadas: Sequence[Mapping]) -> MotivoNoNormalizable:
    texto = str(error)
    if _TEXTO_JSON in texto:
        if _regla_con(entregadas, "limite"):
            return MotivoNoNormalizable.LIMITE_NO_PYTHON
        if _regla_con(entregadas, "intervalo"):
            return MotivoNoNormalizable.INTERVALO_NO_ENTERO
        return MotivoNoNormalizable.OTRO
    for fragmento, motivo in _TEXTOS_ABORTO:
        if fragmento not in texto:
            continue
        if motivo is None:
            return _fuera_de_dominio(payload or {})
        if motivo is MotivoNoNormalizable.INTERVALO_NO_ENTERO and not _regla_con(entregadas, "intervalo"):
            return MotivoNoNormalizable.OTRO
        if motivo is MotivoNoNormalizable.LIMITE_NO_PYTHON and not _regla_con(entregadas, "limite"):
            return MotivoNoNormalizable.OTRO
        return motivo
    return MotivoNoNormalizable.OTRO


def _origen(ruta: Path, payload: Mapping, sha: str, adaptador, dmc_features, sha_adaptador: str) -> OrigenAborto:
    """QC-3 (MC-21): «datos» si aborta también sin política."""
    try:
        adaptador.normalizar(payload, politica=None, content_sha256=sha)
        dmc_features.cargar_dmc([ruta], [], adapter_sha256=sha_adaptador)
    except (ValueError, TypeError):
        return OrigenAborto.DATOS
    return OrigenAborto.REGLA


def normalizar_artefacto(manifiesto, politicas, *, adaptador, dmc_features, validar_regla, sha_adaptador,
                         id_artefacto, artefactos: Mapping[str, str]) -> ResultadoArtefacto:
    """Paso 1 de §2.1: ``tipos.ResultadoArtefacto`` (QC-1 a QC-4). ``artefactos``: sha256 → código de
    ``artefactos_evaluados`` (``politicas.leer_politica_reloj``)."""
    ruta, codigo, anio, mes = _ruta_manifiesto(manifiesto)
    if sha_adaptador != fijados.SHA_ADAPTADOR:
        raise ValueError("sha_adaptador debe ser la huella fijada del adaptador (§2.1; QC-1)")
    if isinstance(id_artefacto, bool) or not isinstance(id_artefacto, (int, np.integer)) or id_artefacto < 0:
        raise ValueError(f"id_artefacto es un índice entero ≥ 0 de artefactos_evaluados: {id_artefacto!r}")
    if not callable(validar_regla):
        raise TypeError("validar_regla es el validador de RELOJ (validar_regla_reloj_dmc)")
    if not isinstance(artefactos, Mapping):
        raise TypeError("artefactos es el mapa sha256 → código de politicas.leer_politica_reloj")
    base = {"id_artefacto": int(id_artefacto), "codigo": codigo, "anio": anio, "mes": mes}
    try:
        payload, meta_artefacto = adaptador.leer_artefacto(ruta)
    except (ValueError, TypeError) as error:
        return ResultadoArtefacto(**base, content_sha256=None, motivo=_motivo(error, None, ()),
                                  origen=OrigenAborto.DATOS)
    sha = meta_artefacto["content_sha256"]
    estacion = str(payload.get("station", {}).get("code", ""))
    if estacion != codigo:
        raise ValueError(f"el artefacto {ruta.name} es de {estacion!r}, no de la carpeta {codigo}")
    if artefactos.get(sha) != codigo:
        raise ValueError(f"el artefacto {ruta.name} no es un artefacto evaluado de la estación {codigo} "
                         "(artefactos_evaluados; §2.1, paso 1; QC-1)")
    cruzan = _politicas.politicas_que_cruzan(list(politicas), codigo, anio, mes)
    aceptadas, rechazadas = _politicas.validar_reglas(cruzan, sha, validar_regla)
    try:
        larga, meta = dmc_features.cargar_dmc([ruta], aceptadas, adapter_sha256=sha_adaptador)
    except (ValueError, TypeError) as error:
        return ResultadoArtefacto(**base, content_sha256=sha, motivo=_motivo(error, payload, aceptadas),
                                  origen=_origen(ruta, payload, sha, adaptador, dmc_features, sha_adaptador),
                                  reglas_rechazadas=rechazadas)
    faltan = [c for c in tipos.COLUMNAS_LARGA_DMC if c not in larga.columns]
    faltan_meta = [k for k in tipos.META_LARGA_DMC if k not in meta]
    if faltan or faltan_meta:
        raise ValueError(f"la tabla larga de cargar_dmc no trae {faltan} ni su meta {faltan_meta}")
    return ResultadoArtefacto(**base, content_sha256=sha, larga=larga, meta=meta, reglas_rechazadas=rechazadas)


def unir_largas(resultados: Iterable[ResultadoArtefacto]) -> pd.DataFrame:
    """Las tablas largas normalizables de una estación, con la columna ``id_artefacto`` (int32), en orden."""
    partes = []
    codigos = set()
    for r in resultados:
        if not isinstance(r, ResultadoArtefacto):
            raise TypeError("unir_largas recibe tipos.ResultadoArtefacto")
        if not r.normalizable:
            continue
        codigos.add(r.codigo)
        d = r.larga.copy()
        d["id_artefacto"] = np.int32(r.id_artefacto)
        partes.append(d)
    if len(codigos) > 1:
        raise ValueError(f"unir_largas junta artefactos de una sola estación, no de {sorted(codigos)}")
    if not partes:
        raise ValueError("ninguna tabla larga normalizable")
    with warnings.catch_warnings():         # columnas todas nulas en un artefacto: los tipos ya coinciden
        warnings.filterwarnings("ignore", message="The behavior of DataFrame concatenation with empty",
                                category=FutureWarning)
        return pd.concat(partes, ignore_index=True)


# ---------------------------------------------------------------------------
# Paso 2: la tabla intermedia y las reglas de §2.4 (salvo la 14)
# ---------------------------------------------------------------------------
def _validar_larga(larga, codigo: str) -> pd.DataFrame:
    if isinstance(larga, (list, tuple)):
        larga = unir_largas(larga)
    if not isinstance(larga, pd.DataFrame):
        raise TypeError("larga es la tabla de unir_largas o la lista de ResultadoArtefacto")
    faltan = [c for c in (*tipos.COLUMNAS_LARGA_DMC, "id_artefacto") if c not in larga.columns]
    if faltan:
        raise ValueError(f"la tabla larga no trae {faltan} (tipos.COLUMNAS_LARGA_DMC más id_artefacto)")
    otras = sorted(set(larga["station_code"].astype(str)) - {codigo})
    if otras:
        raise ValueError(f"la tabla larga trae otras estaciones: {otras}")
    if larga.duplicated(["timestamp_source", "variable"]).any():
        raise ValueError("la tabla larga repite una etiqueta y variable")
    return larga


def _por_etiqueta(larga: pd.DataFrame) -> tuple[np.ndarray, dict]:
    """Etiquetas ordenadas y atributos de fila (reloj, coordenadas, UTC e id del artefacto), exigiendo que coincidan
    en todas las filas de una etiqueta."""
    fila = larga.groupby("timestamp_source", sort=True)
    distintos = fila[["clock_verified", "coordinates_verified", "id_artefacto"]].nunique(dropna=False)
    utc = pd.to_datetime(larga["timestamp_utc"], utc=True)
    utc_distintos = utc.groupby(larga["timestamp_source"]).nunique(dropna=False)
    if (distintos > 1).any().any() or (utc_distintos > 1).any():
        raise ValueError("una etiqueta con reloj, coordenadas, hora UTC o artefacto distintos entre sus variables")
    primera = larga.loc[fila.head(1).index].set_index("timestamp_source").sort_index()
    etiquetas = primera.index.to_numpy(dtype=object)
    reloj = primera["clock_verified"].to_numpy(dtype=bool)
    utc_e = pd.to_datetime(primera["timestamp_utc"], utc=True)
    horas = ((utc_e - _EPOCA) / _UNA_HORA).to_numpy(dtype=np.float64)
    con_h = np.isfinite(horas)
    if (con_h != reloj).any():
        raise ValueError("una etiqueta con reloj confirmado sin hora UTC, o sin reloj con hora UTC")
    if (horas[con_h] != np.floor(horas[con_h])).any():
        raise ValueError("una hora UTC no es exacta (HH:00): la regla de reloj no da horas enteras (QC-5)")
    return etiquetas, {"reloj": reloj, "coord": primera["coordinates_verified"].to_numpy(dtype=bool),
                       "horas": horas, "con_h": con_h,
                       "id_artefacto": primera["id_artefacto"].to_numpy(dtype=np.int64)}


def _columna_variable(larga, etiquetas, variable, columna, vacio, dtype):
    sub = larga[larga["variable"] == variable]
    salida = np.full(len(etiquetas), vacio, dtype=dtype)
    if len(sub):
        pos = pd.Index(etiquetas).get_indexer(sub["timestamp_source"])
        if (pos < 0).any():
            raise ValueError("una fila de la tabla larga sin etiqueta")
        valores = sub[columna].to_numpy()
        salida[pos] = valores.astype(dtype) if dtype is not object else valores
    return salida


def _rr06(larga, etiquetas, U) -> tuple[np.ndarray, np.ndarray]:
    """QC-21: (mm, legible y en [0, 200]) desde el ``raw`` de la fila RR06."""
    raw = pd.Series(_columna_variable(larga, etiquetas, _RR06, "raw", None, object), dtype=object)
    estado = pd.Series(_columna_variable(larga, etiquetas, _RR06, "parse_status", None, object), dtype=object)
    valor = _columna_variable(larga, etiquetas, _RR06, "value", np.nan, np.float64)
    sin_lluvia = raw.map(lambda x: isinstance(x, str) and x.strip() == _SP).to_numpy(bool)
    numerico_ = (estado == "numeric").to_numpy(bool) & np.isfinite(valor)
    mm = np.where(sin_lluvia, 0.0, np.where(numerico_, valor, np.nan))
    legible = np.isfinite(mm) & (mm >= U.a("RR_MIN")) & (mm <= U.a("RR_MAX"))
    return mm, legible


def _media_horaria(politicas_estacion: Sequence[Mapping]) -> bool:
    """QC-10: la estación tiene «posible media horaria» si alguna regla ``measurements`` lleva ese motivo (POL-6)."""
    sufijo = f" motivo={_politicas.MOTIVO_MEDIA_HORARIA}"
    for p in politicas_estacion:
        for regla in (p.get("measurements") or {}).values():
            if isinstance(regla, Mapping) and str(regla.get("source", "")).endswith(sufijo):
                return True
    return False


def _indice_tramo(etiquetas: np.ndarray, tramos: Sequence[TramoPolitica]) -> np.ndarray:
    """A6: el índice en ``tramos`` del tramo cuyo intervalo de etiquetas, inclusivo, contiene cada etiqueta;
    ``_SIN_TRAMO`` si ninguno."""
    salida = np.full(len(etiquetas), _SIN_TRAMO, dtype=np.int64)
    if not tramos or not len(etiquetas):
        return salida
    e = pd.to_datetime(pd.Series(etiquetas, dtype=object)).to_numpy("datetime64[s]")
    for i, t in enumerate(tramos):
        a, b = np.datetime64(t.valid_from, "s"), np.datetime64(t.valid_to, "s")
        dentro = (e >= a) & (e <= b)
        if (dentro & (salida != _SIN_TRAMO)).any():
            raise ValueError("tramos solapados")
        salida[dentro] = i
    return salida


def _tramo_de(etiquetas: np.ndarray, tramos: Sequence[TramoPolitica]) -> np.ndarray:
    """A6: el id del tramo de cada etiqueta (``_indice_tramo``), o None."""
    indice = _indice_tramo(etiquetas, tramos)
    ids = np.array([t.id for t in tramos] + [None], dtype=object)
    return ids[np.where(indice == _SIN_TRAMO, len(tramos), indice)]


def _arreglos(larga: pd.DataFrame, info, U, *, k2: frozenset[str], politicas_estacion) -> dict:
    """La tabla intermedia como diccionario de arreglos, ordenada por h (las filas sin h al final)."""
    etiquetas, fila = _por_etiqueta(larga)
    n = len(etiquetas)
    horas_o_inf = np.where(fila["con_h"], fila["horas"], np.inf)
    orden = np.lexsort((np.arange(n), horas_o_inf))
    A: dict[str, Any] = {"n": n}
    A["etiqueta"] = etiquetas[orden]
    A["con_h"] = fila["con_h"][orden]
    A["h"] = np.where(A["con_h"], fila["horas"][orden], 0).astype(np.int64)
    A["reloj"] = fila["reloj"][orden]
    A["coord"] = fila["coord"][orden]
    A["id_artefacto"] = fila["id_artefacto"][orden]
    hh = A["h"][A["con_h"]]
    repetidas = pd.Series(hh).duplicated(keep=False).to_numpy()
    A["colision"] = np.zeros(n, dtype=bool)
    A["colision"][np.flatnonzero(A["con_h"])[repetidas]] = True
    A["en_tabla"] = A["con_h"] & ~A["colision"]
    A["x"], A["usable"], A["med"], A["rango"] = {}, {}, {}, {}
    for v, c in _CORTA.items():
        A["x"][c] = _columna_variable(larga, etiquetas, v, "value", np.nan, np.float64)[orden]
        A["usable"][c] = _columna_variable(larga, etiquetas, v, "usable", False, bool)[orden]
        A["med"][c] = _columna_variable(larga, etiquetas, v, "measurement_verified", False, bool)[orden]
        razon = _columna_variable(larga, etiquetas, v, "quality_reason", None, object)[orden]
        A["rango"][c] = razon == tipos.RAZON_FUERA_DE_RANGO
    A["wu"] = _columna_variable(larga, etiquetas, _WIND_U, "value", np.nan, np.float64)[orden]
    A["wv"] = _columna_variable(larga, etiquetas, _WIND_V, "value", np.nan, np.float64)[orden]
    mm, legible = _rr06(larga, etiquetas, U)
    A["rr06"], A["rr06_base"] = mm[orden], legible[orden]
    A["anio_etiqueta"] = pd.to_datetime(pd.Series(A["etiqueta"], dtype=object)).dt.year.to_numpy(np.int64)
    A["tramo"] = _tramo_de(A["etiqueta"], _politicas.tramos_de_politicas(politicas_estacion))
    A["codigo"] = info.codigo
    A["excluida"] = bool(info.excluida)
    A["k4_coord"] = np.zeros(n, dtype=bool)
    A["calza"] = np.zeros(n, dtype=np.int8)
    A["marcas"] = {c: np.zeros(n, dtype=np.uint32) for c in _CORTAS}
    A["coord_estacion"] = _coordenadas_de_estacion(info, k2)
    A["media_horaria"] = _media_horaria(politicas_estacion)
    return A


def _valido(A, c: str) -> np.ndarray:
    """QC-8: usable, sin bits invalidantes, con h y sin colisión."""
    return A["usable"][c] & ((A["marcas"][c] & _MASCARA_INVALIDA) == 0) & A["en_tabla"]


def _marcar(A, columnas: Iterable[str], filas, marca) -> None:
    for c in columnas:
        A["marcas"][c][filas] |= _BIT[marca]


def _paso_cargar_dmc(A) -> None:
    """Bits 0 a 3 (y 22) de cargar_dmc (QC-10, paso 1)."""
    sin_reloj = ~A["reloj"]
    sin_coord = ~A["coord"] | (not A["coord_estacion"])
    _marcar(A, _CORTAS, sin_reloj, Marca.SIN_RELOJ)
    _marcar(A, _CORTAS, sin_coord, Marca.SIN_COORDENADAS)
    for c in _CORTAS:
        _marcar(A, (c,), ~A["med"][c], Marca.MEDICION_NO_VERIFICADA)
        _marcar(A, (c,), A["rango"][c], Marca.FUERA_DE_RANGO)
        if A["media_horaria"]:
            _marcar(A, (c,), slice(None), Marca.POSIBLE_MEDIA_HORARIA)


def _paso_centinelas(A, U) -> None:
    """Marca 4 sobre el valor de la fuente (D7)."""
    tol = U.a("CENT_TOL")
    for c, centinela, arrastra in ((TS, U.a("CENT_TS"), (TD, HR)), (QFE, U.a("CENT_QFE"), (QFF,))):
        x = A["x"][c]
        con = np.isfinite(x) & (_r(np.abs(x - centinela) - tol) < 0)
        _marcar(A, (c, *arrastra), con, Marca.CENTINELA)


def _rachas(t: np.ndarray, claves: Sequence[np.ndarray], lapso_de, n_min: int, consecutivo) -> np.ndarray:
    """MC-22: las sucesiones máximas de consecutivos idénticos con ≥ n_min reportes cuya duración alcanza
    ``lapso_de(i)`` (el lapso del valor de la sucesión que empieza en i, o None si esa sucesión no se evalúa)."""
    n = len(t)
    salida = np.zeros(n, dtype=bool)
    if n < n_min:
        return salida
    une = np.diff(t) <= consecutivo
    for x in claves:
        une &= x[1:] == x[:-1]
    inicios, finales = _segmentos(une, n)
    largos = finales - inicios + 1 >= n_min
    for a, b in zip(inicios[largos], finales[largos]):
        lapso = lapso_de(a)
        dur = _duracion(t, a, b)
        if lapso is not None and dur is not None and dur >= lapso:
            salida[a:b + 1] = True
    return salida


def _paso_rachas(A, U) -> None:
    """Rachas (5) y calma persistente (12) (QC-11)."""
    h, x = A["h"], A["x"]
    n_min, cons = U.a("RACHA_MIN_REPORTES"), U.a("CONSECUTIVO_H")
    corto, largo, saturada = U.a("RACHA_H"), U.a("RACHA_LARGA_H"), U.a("HR_SAT")
    v = {c: _valido(A, c) for c in _CORTAS}
    marcas: list[tuple[tuple[str, ...], np.ndarray, Any]] = []
    for c in (TS, QFE, QFF):
        idx = np.flatnonzero(v[c])
        r = _rachas(h[idx], (x[c][idx],), lambda i: corto, n_min, cons)
        marcas.append(((c,), idx[r], Marca.RACHA))
    idx = np.flatnonzero(v[HR])
    xs = x[HR][idx]
    r = _rachas(h[idx], (xs,), lambda i: largo if xs[i] == saturada else corto, n_min, cons)
    marcas.append(((HR,), idx[r], Marca.RACHA))
    idx = np.flatnonzero(v[TD] & ~(v[HR] & (x[HR] == saturada)))
    r = _rachas(h[idx], (x[TD][idx],), lambda i: corto, n_min, cons)
    marcas.append(((TD,), idx[r], Marca.RACHA))
    idx = np.flatnonzero(v[FF] & v[DD])
    ff = x[FF][idx]
    r = _rachas(h[idx], (ff, x[DD][idx]), lambda i: corto if ff[i] > 0 else None, n_min, cons)
    marcas.append(((FF, DD), idx[r], Marca.RACHA))
    idx = np.flatnonzero(v[FF])
    ff = x[FF][idx]
    r = _rachas(h[idx], (ff,), lambda i: largo if ff[i] == 0 else None, n_min, cons)
    marcas.append(((FF, DD), idx[r], Marca.CALMA_PERSISTENTE))
    for columnas, filas, marca in marcas:
        _marcar(A, columnas, filas, marca)


def _picos(t: np.ndarray, y: np.ndarray, theta: float, U) -> np.ndarray:
    n = len(t)
    salida = np.zeros(n, dtype=bool)
    if n < _REPORTES_PICO:
        return salida
    dt1, dt2 = t[1:-1] - t[:-2], t[2:] - t[1:-1]
    d1, d2 = y[1:-1] - y[:-2], y[2:] - y[1:-1]
    cons = U.a("CONSECUTIVO_H")
    lim = theta * _factor_f(np.maximum(dt1, dt2), U)
    salida[1:-1] = ((dt1 <= cons) & (dt2 <= cons) & (_r(np.abs(d1) - lim) > 0) & (_r(np.abs(d2) - lim) > 0)
                    & (np.sign(d1) * np.sign(d2) < 0))
    return salida


def _saltos(t: np.ndarray, y: np.ndarray, theta: float, U) -> np.ndarray:
    salida = np.zeros(len(t), dtype=bool)
    if len(t) < 2:
        return salida
    dt, d = np.diff(t), np.diff(y)
    lim = U.a("SALTO_MULT") * theta * _factor_f(dt, U)
    salida[1:] = (dt <= U.a("CONSECUTIVO_H")) & (_r(np.abs(d) - lim) > 0)
    return salida


def _paso_picos(A, U) -> None:
    """Picos y saltos (6) (QC-12)."""
    theta = {TS: U.a("PICO_TS"), TD: U.a("PICO_TD"), QFE: U.a("PICO_P"), QFF: U.a("PICO_P"), FF: U.a("PICO_FF")}
    v = {c: _valido(A, c) for c in theta}
    marcas = []
    for c, th in theta.items():
        idx = np.flatnonzero(v[c])
        t, y = A["h"][idx], A["x"][c][idx]
        pico = _picos(t, y, th, U)
        resto = idx[~pico]
        salto = _saltos(A["h"][resto], A["x"][c][resto], th, U)
        marcas.append((c, np.r_[idx[pico], resto[salto]]))
    for c, filas in marcas:
        _marcar(A, (c,), filas, Marca.PICO_O_SALTO)


def _paso_td_ts(A, U) -> None:
    """Marca 7 (QC-13)."""
    con = _valido(A, TD) & _valido(A, TS)
    d = _r(A["x"][TD] - A["x"][TS] - U.a("TD_TS_INV"))
    _marcar(A, (TD, HR), con & (d > 0), Marca.TD_MAYOR_TS)


def _incoherente(td, hr, ts, U, *, hielo: bool) -> np.ndarray:
    with np.errstate(invalid="ignore", divide="ignore"):
        if hielo:
            td_m = _td_desde_e_hielo(hr / numerico.PORCENTAJE * numerico.magnus_agua(ts))
        else:
            td_m = numerico.td_desde_hr(hr, ts)
        hr_m = numerico.hr_desde(ts, td, hielo=hielo)
    return (_r(np.abs(td - td_m) - U.a("INCOH_TD")) > 0) & (_r(np.abs(hr - hr_m) - U.a("INCOH_HR")) > 0)


def _paso_incoherencia(A, U) -> None:
    """Marca 9 y el conteo agua/hielo bajo 0 °C (QC-13)."""
    con = np.flatnonzero(_valido(A, TD) & _valido(A, HR) & _valido(A, TS))
    td, hr, ts = A["x"][TD][con], A["x"][HR][con], A["x"][TS][con]
    agua = _incoherente(td, hr, ts, U, hielo=False)
    bajo_cero = ts < U.a("CERO_C")
    hielo = np.zeros(len(con), dtype=bool)
    if bajo_cero.any():
        hielo[bajo_cero] = _incoherente(td[bajo_cero], hr[bajo_cero], ts[bajo_cero], U, hielo=True)
    marca = agua & (~bajo_cero | hielo)
    _marcar(A, (TD, HR), con[marca], Marca.TD_HR_INCOHERENTE)
    aceptada = bajo_cero & ~marca
    A["calza"][con[aceptada]] = (np.where(~agua[aceptada], _CALZA_AGUA, 0)
                                 + np.where(~hielo[aceptada], _CALZA_HIELO, 0)).astype(np.int8)


def _paso_viento(A, U) -> None:
    """Marcas 11 y 19 (QC-15)."""
    v = _valido(A, FF) & _valido(A, DD)
    ff, dd = A["x"][FF], A["x"][DD]
    rapidez = v & (ff > 0)
    cero = rapidez & (dd == 0)
    pct = U.a("CERO_NORTE_PCT")
    norte = np.zeros(A["n"], dtype=bool)
    for anio in np.unique(A["anio_etiqueta"][rapidez]):
        del_anio = rapidez & (A["anio_etiqueta"] == anio)
        n = int(del_anio.sum())
        n0 = int((cero & del_anio).sum())
        n360 = int((del_anio & (dd == _NORTE_SYNOP)).sum())
        if n360 == 0 and n0 * numerico.PORCENTAJE >= pct * n:
            norte |= del_anio
    _marcar(A, (FF, DD), cero & norte, Marca.CERO_ES_NORTE)
    _marcar(A, (FF, DD), cero & ~norte, Marca.DIR0_CON_RAPIDEZ)


def _paso_aire_seco(A, U) -> None:
    """Marca 17 (QC-16)."""
    idx = np.flatnonzero(_valido(A, HR))
    t, hr = A["h"][idx], A["x"][HR][idx]
    seco = hr < U.a("SECO_HR_PCT")
    une = (np.diff(t) <= U.a("CONSECUTIVO_H")) & seco[1:] & seco[:-1]
    filas = []
    inicios, finales = _segmentos(une, len(t))
    candidatas = seco[inicios] & (finales - inicios + 1 >= constantes.valor("SECO_MIN_REPORTES"))
    for a, b in zip(inicios[candidatas], finales[candidatas]):
        dur = _duracion(t, a, b)
        if dur is not None and dur >= U.a("SECO_H"):
            filas.append(idx[a:b + 1])
    if filas:
        _marcar(A, (HR, TD), np.concatenate(filas), Marca.AIRE_SECO_SOSTENIDO)


def _fondo_en_filas(A, F_estacion) -> dict[str, np.ndarray] | None:
    """El fondo (A2) en cada fila de la tabla intermedia; NaN sin h o sin esa hora."""
    if F_estacion is None:
        return None
    en = np.flatnonzero(A["en_tabla"])
    F = fondo_era5l.en_horas(F_estacion, A["h"][en].astype(np.int32))
    salida = {}
    for k, x in F.items():
        col = np.full(A["n"], np.nan)
        col[en] = x
        salida[k] = col
    return salida


def _desvios(t: np.ndarray, r: np.ndarray, theta_g: float, U) -> tuple[np.ndarray, np.ndarray]:
    """QC-17: (invalidar, persistente) de los reportes de una serie con residuo finito."""
    n = len(t)
    invalidar, persistente = np.zeros(n, dtype=bool), np.zeros(n, dtype=bool)
    if n == 0:
        return invalidar, persistente
    mes = homogeneidad.mes2000(t) % 12               # mes del año UTC (0 = enero)
    hora = homogeneidad.hora_utc(t)
    med, mad = np.full(n, np.nan), np.full(n, np.nan)
    n_min = U.a("EG_MIN_N")
    celda = mes * homogeneidad.HORAS_DIA + hora
    for clave_grupo, quien in ((celda, "celda"), (mes, "mes")):
        for g in np.unique(clave_grupo):
            en = clave_grupo == g
            if en.sum() < n_min:
                continue
            m, d = numerico.mediana_mad(r[en])
            pendiente = en & ~np.isfinite(med)
            med[pendiente], mad[pendiente] = m, d
    evaluado = np.isfinite(med)
    U_i = np.maximum(theta_g, U.a("EG_MULT") * U.a("EG_MAD_K") * mad)
    z = r - med
    medio = evaluado & (_r(np.abs(z) - U_i / constantes.valor("EG_DESVIO_DIVISOR")) > 0)
    sobre = evaluado & (_r(np.abs(z) - U_i) > 0)
    signo = np.sign(z)
    idx = np.flatnonzero(evaluado)
    te, me, se, so = t[idx], medio[idx], signo[idx], sobre[idx]
    une = (np.diff(te) <= U.a("CONSECUTIVO_H")) & me[1:] & me[:-1] & (se[1:] == se[:-1])
    inicios, finales = _segmentos(une, len(te))
    sobre_acum = np.r_[0, np.cumsum(so)]
    candidatas = me[inicios] & (sobre_acum[finales + 1] - sobre_acum[inicios] > 0)
    for a, b in zip(inicios[candidatas], finales[candidatas]):
        dur = _duracion(te, a, b)
        if dur is None or dur < U.a("EG_CORTO_H"):
            invalidar[idx[a:b + 1][so[a:b + 1]]] = True
        elif dur <= U.a("EG_LARGO_H"):
            persistente[idx[a:b + 1]] = True
        else:
            invalidar[idx[a:b + 1]] = True
    return invalidar, persistente


def _paso_error_grueso(A, F_estacion, U) -> None:
    """Marcas 13 y 18 (QC-17). La mediana y el MAD no salen de esta función."""
    F = _fondo_en_filas(A, F_estacion)
    if F is None:
        return
    D = _derivadas(A, U)
    vacio = np.full(A["n"], np.nan)
    obs_td = np.where(np.isin(D["origen_td"], (OrigenTd.OBSERVADO, OrigenTd.RECORTADO)), D["td_final"], np.nan)
    obs = {"T": np.where(_valido(A, TS), A["x"][TS], np.nan), "Td": obs_td, "u": vacio, "v": vacio,
           "QFE": vacio}
    r = fondo_era5l.residuos(obs, {k: F[k] for k in fondo_era5l.CAMPOS_F})
    r_p = np.where(_valido(A, QFE), _f4(A["x"][QFE]) - _f4(F["p_F"]), np.nan)
    marcas = []
    for c, residuo, theta in ((TS, r["r_T"], U.a("EG_T")), (TD, r["r_Td"], U.a("EG_TD")), (QFE, r_p, U.a("EG_P"))):
        idx = np.flatnonzero(np.isfinite(residuo))
        invalidar, persistente = _desvios(A["h"][idx], residuo[idx], theta, U)
        marcas.append((c, idx[invalidar], idx[persistente]))
    for c, inval, pers in marcas:
        _marcar(A, (c,), inval, Marca.ERROR_GRUESO)
        _marcar(A, (c,), pers, Marca.DESVIO_PERSISTENTE)


def _derivadas(A, U) -> dict[str, np.ndarray]:
    """QC-14: derivadas desde la validez final; ajusta las marcas 8, 10, 15 y 20 y devuelve las columnas."""
    n = A["n"]
    x, m = A["x"], A["marcas"]
    for c in _CORTAS:
        m[c] &= ~_MASCARA_DERIVADAS
    v = {c: _valido(A, c) for c in _CORTAS}
    saturada = U.a("HR_SAT")
    hr_final = np.where(v[HR], x[HR], np.nan)
    origen_hr = np.where(v[HR], OrigenHR.OBSERVADO, OrigenHR.SIN_VALOR).astype(np.int8)
    recortada = v[HR] & (x[HR] > saturada) & (x[HR] <= U.a("HR_RECORTE_MAX"))
    hr_final[recortada] = saturada
    origen_hr[recortada] = OrigenHR.RECORTADO
    m[HR][recortada] |= _BIT[Marca.HR_RECORTADA]

    td_final = np.where(v[TD], x[TD], np.nan)
    origen_td = np.where(v[TD], OrigenTd.OBSERVADO, OrigenTd.SIN_VALOR).astype(np.int8)
    d = _r(x[TD] - x[TS])
    recorte = v[TD] & v[TS] & (d > 0) & (_r(d - U.a("TD_TS_INV")) <= 0)
    td_final[recorte] = x[TS][recorte]
    origen_td[recorte] = OrigenTd.RECORTADO
    m[TD][recorte] |= _BIT[Marca.TD_RECORTADO]
    derivado = np.isnan(x[TD]) & v[HR] & v[TS]
    td_final[derivado] = numerico.td_desde_hr(hr_final[derivado], x[TS][derivado])
    origen_td[derivado] = OrigenTd.DERIVADO
    m[TD][derivado] |= _BIT[Marca.TD_DERIVADO]

    u_final, v_final = np.full(n, np.nan), np.full(n, np.nan)
    origen_v = np.full(n, OrigenViento.SIN_VALOR, dtype=np.int8)
    par = v[FF] & v[DD]
    if (par & ~(np.isfinite(A["wu"]) & np.isfinite(A["wv"]))).any():
        raise ValueError("FF y DD válidas sin wind_u y wind_v del adaptador")
    u_final[par], v_final[par] = A["wu"][par] + 0.0, A["wv"][par] + 0.0
    calma = par & (x[FF] == 0)
    u_final[calma], v_final[calma] = 0.0, 0.0
    origen_v[par] = OrigenViento.OBSERVADO
    origen_v[par & ((m[DD] & _BIT[Marca.CERO_ES_NORTE]) != 0)] = OrigenViento.CERO_ES_NORTE
    sin_direccion = v[FF] & (x[FF] == 0) & np.isnan(x[DD])
    u_final[sin_direccion], v_final[sin_direccion] = 0.0, 0.0
    origen_v[sin_direccion] = OrigenViento.CALMA_SIN_DIRECCION
    _marcar(A, (FF, DD), sin_direccion, Marca.CALMA_SIN_DIRECCION)

    fuera = A["excluida"]
    filas_ok = (m[TS] & _MASCARA_FILA) == 0
    return {"td_final": td_final, "hr_final": hr_final, "u_final": u_final, "v_final": v_final,
            "origen_td": origen_td, "origen_hr": origen_hr, "origen_viento": origen_v,
            "valido_T": v[TS] & (not fuera), "valido_Td": np.isfinite(td_final) & (not fuera),
            "valido_HR": np.isfinite(hr_final) & (not fuera), "valido_viento": np.isfinite(u_final) & (not fuera),
            "valido_p": v[QFE] & (not fuera),
            "rr06_valido": A["rr06_base"] & A["reloj"] & filas_ok & A["en_tabla"]}


_PRIVADAS_FILA = ("_con_h", "_en_tabla", "_colision", "_reloj", "_coord", "_k4_coord", "_calza", "_wu", "_wv",
                  "_rr06_base", "_anio_etiqueta")


def _a_tabla(A, U) -> pd.DataFrame:
    D = _derivadas(A, U)
    datos: dict[str, Any] = {
        "h": pd.array(np.where(A["con_h"], A["h"], 0), dtype="Int64"),
        "ts_fuente": pd.array(A["etiqueta"], dtype="string"),
        "id_artefacto": A["id_artefacto"].astype(np.int32),
        "tramo": pd.array(A["tramo"], dtype="string"),
    }
    datos["h"][~A["con_h"]] = pd.NA
    for c in _CORTAS:
        datos[c] = A["x"][c]
    for k in ("td_final", "hr_final", "u_final", "v_final", "origen_td", "origen_hr", "origen_viento"):
        datos[k] = D[k]
    for c in _CORTAS:
        datos[_COL_MARCAS[c]] = A["marcas"][c].copy()
    for k in ("valido_T", "valido_Td", "valido_HR", "valido_viento", "valido_p"):
        datos[k] = D[k]
    datos["rr06_mm"], datos["rr06_valido"] = A["rr06"], D["rr06_valido"]
    datos["_codigo"] = pd.array([A["codigo"]] * A["n"], dtype="string")
    datos["_excluida"] = np.full(A["n"], A["excluida"])
    datos["_con_h"], datos["_en_tabla"], datos["_colision"] = A["con_h"], A["en_tabla"], A["colision"]
    datos["_reloj"], datos["_coord"], datos["_k4_coord"] = A["reloj"], A["coord"], A["k4_coord"]
    datos["_calza"], datos["_wu"], datos["_wv"] = A["calza"], A["wu"], A["wv"]
    datos["_rr06_base"], datos["_anio_etiqueta"] = A["rr06_base"], A["anio_etiqueta"]
    for c in _CORTAS:
        datos[f"_usable_{c}"] = A["usable"][c]
        datos[f"_med_{c}"] = A["med"][c]
        datos[f"_rango_{c}"] = A["rango"][c]
    tabla = pd.DataFrame(datos)
    tabla.attrs["esquema"] = "meteo-combinada-qc-intermedia/1"
    return tabla


def _de_tabla(tabla: pd.DataFrame) -> dict:
    faltan = [c for c in ("_codigo", *_PRIVADAS_FILA) if c not in tabla.columns]
    if faltan:
        raise ValueError(f"se espera la tabla intermedia de qc_meteo_combinada (faltan {faltan})")
    codigos = set(tabla["_codigo"].astype(str))
    if len(codigos) > 1:
        raise ValueError("la tabla intermedia es de una sola estación")
    A: dict[str, Any] = {"n": len(tabla)}
    A["codigo"] = codigos.pop() if codigos else ""
    A["excluida"] = bool(tabla["_excluida"].any())
    A["con_h"] = tabla["_con_h"].to_numpy(bool)
    A["h"] = tabla["h"].to_numpy(dtype=np.float64, na_value=0).astype(np.int64)
    A["etiqueta"] = tabla["ts_fuente"].to_numpy(dtype=object)
    A["id_artefacto"] = tabla["id_artefacto"].to_numpy(np.int64)
    A["tramo"] = np.array([None if pd.isna(t) else str(t) for t in tabla["tramo"]], dtype=object)
    A["en_tabla"], A["colision"] = tabla["_en_tabla"].to_numpy(bool), tabla["_colision"].to_numpy(bool)
    A["reloj"], A["coord"] = tabla["_reloj"].to_numpy(bool), tabla["_coord"].to_numpy(bool)
    A["k4_coord"] = tabla["_k4_coord"].to_numpy(bool).copy()
    A["calza"] = tabla["_calza"].to_numpy(np.int8)
    A["wu"], A["wv"] = tabla["_wu"].to_numpy(np.float64), tabla["_wv"].to_numpy(np.float64)
    A["rr06"], A["rr06_base"] = tabla["rr06_mm"].to_numpy(np.float64), tabla["_rr06_base"].to_numpy(bool)
    A["anio_etiqueta"] = tabla["_anio_etiqueta"].to_numpy(np.int64)
    A["x"] = {c: tabla[c].to_numpy(np.float64) for c in _CORTAS}
    A["usable"] = {c: tabla[f"_usable_{c}"].to_numpy(bool) for c in _CORTAS}
    A["med"] = {c: tabla[f"_med_{c}"].to_numpy(bool) for c in _CORTAS}
    A["rango"] = {c: tabla[f"_rango_{c}"].to_numpy(bool) for c in _CORTAS}
    A["marcas"] = {c: tabla[_COL_MARCAS[c]].to_numpy(np.uint32).copy() for c in _CORTAS}
    return A


def qc_meteo_combinada(larga, info, F_estacion, umbrales, *, k2: frozenset[str], politicas):
    """Paso 2 de §2.1: reglas de §2.4 salvo la marca 14 (QC-5 a QC-17). Devuelve la tabla intermedia.

    ``larga``: la tabla de ``unir_largas`` (o la lista de ``ResultadoArtefacto``) de la estación; ``F_estacion``: su
    ``ESQUEMA_PUNTOS_E5L`` (A1) o None si no tiene fondo; ``k2``: la lista K2 (códigos); ``politicas``: las de lectura,
    la lista completa de la estación (A6; las de otras estaciones se ignoran)."""
    codigo = _exigir_info(info)
    k2 = _conjunto_k2(k2)
    larga = _validar_larga(larga, codigo)
    propias = [p for p in politicas if p.get("station_code") == codigo]
    A = _arreglos(larga, info, umbrales, k2=k2, politicas_estacion=propias)
    _paso_cargar_dmc(A)
    _paso_centinelas(A, umbrales)
    _paso_rachas(A, umbrales)
    _paso_picos(A, umbrales)
    _paso_td_ts(A, umbrales)
    _paso_incoherencia(A, umbrales)
    _derivadas(A, umbrales)
    _paso_viento(A, umbrales)
    _paso_aire_seco(A, umbrales)
    _paso_error_grueso(A, F_estacion, umbrales)
    return _a_tabla(A, umbrales)


# ---------------------------------------------------------------------------
# Pasos 3 y 4: K4, retirada y marca 14
# ---------------------------------------------------------------------------
def entrada_k4(tabla, F_estacion) -> tuple[pd.DataFrame, np.ndarray]:
    """A4 (QC-18): (``h``, Ts, QFE, QFF con NaN donde no son válidas tras el paso 2) en las filas con h, y p_F."""
    A = _de_tabla(tabla)
    en = np.flatnonzero(A["en_tabla"])
    datos = {"h": A["h"][en].astype(np.int32)}
    for c in (TS, QFE, QFF):
        datos[c] = np.where(_valido(A, c), A["x"][c], np.nan)[en]
    entrada = pd.DataFrame(datos)
    if F_estacion is None:
        return entrada, np.full(len(en), np.nan)
    return entrada, fondo_era5l.en_horas(F_estacion, datos["h"])["p_F"]


def k4_estacion(tabla, F_estacion, info, umbrales) -> ResultadoK4:
    """K4 de la estación con la entrada de A4 (``homogeneidad.k4(…, codigo=…)``; QC-18)."""
    codigo = _exigir_info(info)
    entrada, p_F = entrada_k4(tabla, F_estacion)
    return homogeneidad.k4(entrada, p_F, info.z_cat, umbrales, codigo=codigo)


def aplicar_k4(tabla, resultado: ResultadoK4, umbrales):
    """Paso 4 de §2.1: marcas 1 y 16 (y 21) de K4 (QC-19). ``umbrales`` hace falta para rehacer las derivadas."""
    if not isinstance(resultado, ResultadoK4):
        raise TypeError("aplicar_k4 recibe un tipos.ResultadoK4")
    for k in (resultado.ultimo_traslado, resultado.ultimo_barometro):
        if k is not None and (isinstance(k, bool) or not isinstance(k, (int, np.integer))):
            raise ValueError(f"los meses de K4 son enteros (mes2000): {k!r}")
    A = _de_tabla(tabla)
    if resultado.codigo != A["codigo"]:
        raise ValueError(f"el ResultadoK4 es de {resultado.codigo}, no de {A['codigo']}")
    meses = np.where(A["con_h"], homogeneidad.mes2000(A["h"]), np.iinfo(np.int64).max)
    if resultado.ultimo_traslado is not None:
        antes = A["con_h"] & (meses < int(resultado.ultimo_traslado))
        _marcar(A, _CORTAS, antes, Marca.SIN_COORDENADAS)
        A["k4_coord"] |= antes
    if resultado.ultimo_barometro is not None:
        antes = A["con_h"] & (meses < int(resultado.ultimo_barometro))
        _marcar(A, (QFE, QFF), antes, Marca.BAROMETRO_INHOMOGENEO)
    if resultado.sin_prueba:
        _marcar(A, (QFE, QFF), slice(None), Marca.SIN_PRUEBA_DE_TRASLADO)
    return _a_tabla(A, umbrales)


def marca_14(tabla, F_estacion, umbrales, *, tramos: Sequence[TramoPolitica]):
    """Marca 14 en los tramos de la política efectiva (D24; QC-20), y ``tramo`` con sus ids."""
    A = _de_tabla(tabla)
    tramos = list(tramos)
    if any(not isinstance(t, TramoPolitica) or t.codigo != A["codigo"] for t in tramos):
        raise ValueError("marca_14 recibe los TramoPolitica de la estación (politicas.tramos_marca_14)")
    indice = _indice_tramo(A["etiqueta"], tramos)
    sin_tramo = A["en_tabla"] & (indice == _SIN_TRAMO)
    if sin_tramo.any():
        raise ValueError(f"{int(sin_tramo.sum())} horas con reloj fuera de los tramos efectivos")
    A["tramo"] = np.where(indice != _SIN_TRAMO, _tramo_de(A["etiqueta"], tramos), A["tramo"])
    F = _fondo_en_filas(A, F_estacion)
    if F is not None:
        v = _valido(A, QFE)
        d = np.where(v, _f4(A["x"][QFE]) - _f4(F["p_F"]), np.nan)
        limite = umbrales.a("ALT_QFE_HPA")
        marcar = np.zeros(A["n"], dtype=bool)
        for i in range(len(tramos)):
            del_tramo = indice == i
            base = d[del_tramo & np.isfinite(d)]
            if base.size and _r(abs(float(np.median(base))) - limite) > 0:
                marcar |= del_tramo & np.isfinite(A["x"][QFE])
        _marcar(A, (QFE,), marcar, Marca.ALTITUD_INCOHERENTE)
    return _a_tabla(A, umbrales)


def qc_estacion(larga, info, F_estacion, umbrales, *, k2, politicas) -> tuple[pd.DataFrame, ResultadoK4, list[dict]]:
    """Pasos 2 a 4 de §2.1 en una estación: (tabla intermedia final, ResultadoK4, políticas efectivas de la
    estación). ``politicas`` son las de lectura de la estación, la lista completa."""
    codigo = _exigir_info(info)
    propias = [p for p in politicas if p.get("station_code") == codigo]
    tabla = qc_meteo_combinada(larga, info, F_estacion, umbrales, k2=k2, politicas=propias)
    resultado = k4_estacion(tabla, F_estacion, info, umbrales)
    efectivas = _politicas.politicas_efectivas(propias, {codigo: resultado})
    tabla = aplicar_k4(tabla, resultado, umbrales)
    tabla = marca_14(tabla, F_estacion, umbrales, tramos=_politicas.tramos_marca_14(efectivas, codigo))
    return tabla, resultado, efectivas


# ---------------------------------------------------------------------------
# Paso 5: la tabla ancha
# ---------------------------------------------------------------------------
def tabla_ancha(tabla):
    """``tipos.ESQUEMA_QC_ESTACION``: las horas con reloj y sin colisión, ordenadas por h (QC-5, QC-6)."""
    if "_en_tabla" not in tabla.columns:
        raise ValueError("tabla_ancha recibe la tabla intermedia de qc_meteo_combinada")
    t = tabla[tabla["_en_tabla"].to_numpy(bool)]
    h = t["h"].to_numpy(dtype=np.int64)
    if len(h) > 1 and not (np.diff(h) > 0).all():
        raise ValueError("las horas de la tabla ancha deben ir crecientes y sin repetir")
    esquema = tipos.ESQUEMA_QC_ESTACION
    datos = {}
    for c, tipo in esquema.items():
        if tipo == "string":
            datos[c] = pd.array(t[c].astype(object).where(t[c].notna(), None), dtype="string")
        else:
            datos[c] = t[c].to_numpy().astype(tipo)
    ancha = pd.DataFrame(datos, columns=list(esquema))
    tipos.validar_esquema(ancha, esquema, nombre="tabla ancha de control de calidad")
    ancha.attrs["esquema"] = esquema.version
    return ancha


# ---------------------------------------------------------------------------
# Conteos (§2.7, §1.10; QC-22)
# ---------------------------------------------------------------------------
def _filas_conteo(codigo, conjunto, macrozona, anios: np.ndarray, variable: str, clave: str,
                  mascara: np.ndarray) -> list[dict]:
    if not mascara.any():
        return []
    valores, cuentas = np.unique(anios[mascara], return_counts=True)
    return [{"codigo": codigo, "conjunto": conjunto, "macrozona": macrozona, "anio": int(a), "variable": variable,
             "clave": clave, "n": int(n)} for a, n in zip(valores, cuentas)]


def _tabla_conteo(filas: list[dict]) -> pd.DataFrame:
    if not filas:
        return pd.DataFrame({c: pd.Series(dtype=t) for c, t in COLUMNAS_CONTEO.items()})
    d = pd.DataFrame(filas, columns=list(COLUMNAS_CONTEO))
    return d.astype(COLUMNAS_CONTEO)


def conteos_estacion(tabla, info) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(numeradores, denominadores) de una estación desde su tabla intermedia final (QC-22)."""
    codigo = _exigir_info(info)
    A = _de_tabla(tabla)
    if A["codigo"] not in ("", codigo):
        raise ValueError(f"la tabla es de {A['codigo']}, no de {codigo}")
    macrozona = tipos.macrozona_o_ninguna(info.macrozona)
    conjunto = str(info.conjunto)
    anios_utc = (fondo_era5l.EPOCA_H + A["h"].astype("timedelta64[h]")).astype("datetime64[Y]")
    anios = np.where(A["con_h"], anios_utc.astype(np.int64) + _ANIO_EPOCA_UNIX, A["anio_etiqueta"])
    fuera_q2 = info.motivo in tipos.MOTIVOS_FUERA_DE_Q2
    k3 = info.motivo in tipos.MOTIVOS_SIN_COORDENADAS_K3
    num, den = [], []
    base = (codigo, conjunto, macrozona, anios)
    for c in _CORTAS:
        variable = _DE_CORTA[c]
        x, marcas = A["x"][c], A["marcas"][c]
        con_valor = np.isfinite(x)
        usable, rango = A["usable"][c], A["rango"][c]
        q2 = A["reloj"] & A["med"][c] & con_valor
        den += _filas_conteo(*base, variable, DEN_HORAS, con_valor)
        den += _filas_conteo(*base, variable, DEN_Q1, usable)
        den += _filas_conteo(*base, variable, DEN_Q1_RANGO, usable | rango)
        den += _filas_conteo(*base, variable, DEN_Q2_FUERA if fuera_q2 else DEN_Q2, q2)
        for m in Marca:
            num += _filas_conteo(*base, variable, clave_marca(m), con_valor & ((marcas & _BIT[m]) != 0))
        for m in tipos.MARCAS_Q1:
            n_q1 = rango if m is Marca.FUERA_DE_RANGO else usable & ((marcas & _BIT[m]) != 0)
            num += _filas_conteo(*base, variable, clave_q1(m), n_q1)
        num += _filas_conteo(*base, variable, NUM_Q1_ALGUNA, (usable | rango) & (((marcas & _MASCARA_Q1) != 0) | rango))
        if not fuera_q2:
            num += _filas_conteo(*base, variable, NUM_Q2, q2 & (k3 | A["k4_coord"]))
        num += _filas_conteo(*base, variable, NUM_COLISION, A["colision"] & con_valor)
        if c == TD:
            for codigo_calza, clave in NUM_CALZA.items():
                num += _filas_conteo(*base, variable, clave, A["calza"] == codigo_calza)
    return _tabla_conteo(num), _tabla_conteo(den)


_ANIO_EPOCA_UNIX = int(str(np.datetime64(0, "Y")))      # datetime64[Y] cuenta los años desde éste


def conteos_artefactos(resultados: Iterable[ResultadoArtefacto], infos: Mapping[str, tipos.InfoEstacion]
                       ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(numeradores, denominadores) de Q3: los artefactos evaluados y los «no normalizables» (QC-23)."""
    num, den = [], []
    for r in resultados:
        if not isinstance(r, ResultadoArtefacto):
            raise TypeError("conteos_artefactos recibe tipos.ResultadoArtefacto")
        if r.codigo not in infos:
            raise ValueError(f"falta la InfoEstacion de {r.codigo}")
        info = infos[r.codigo]
        fila = {"codigo": r.codigo, "conjunto": str(info.conjunto), "macrozona": tipos.macrozona_o_ninguna(info.macrozona),
                "anio": int(r.anio), "variable": VARIABLE_ARTEFACTO, "n": 1}
        den.append({**fila, "clave": DEN_ARTEFACTOS})
        if not r.normalizable:
            num.append({**fila, "clave": NUM_NO_NORMALIZABLES})
    return _sumar_conteo(num), _sumar_conteo(den)


def _sumar_conteo(filas: list[dict]) -> pd.DataFrame:
    """Las filas de conteo sumadas por sus claves, en orden."""
    if not filas:
        return _tabla_conteo([])
    claves = [c for c in COLUMNAS_CONTEO if c != "n"]
    d = _tabla_conteo(filas).groupby(claves, dropna=False, as_index=False, sort=True)["n"].sum()
    return d[list(COLUMNAS_CONTEO)].astype(COLUMNAS_CONTEO)


def tabla_no_normalizables(resultados: Iterable[ResultadoArtefacto], infos: Mapping[str, tipos.InfoEstacion]
                           ) -> pd.DataFrame:
    """``tipos.ESQUEMA_NO_NORMALIZABLES`` (``qc/no_normalizables.csv``): sin valores."""
    filas = []
    for r in resultados:
        if r.normalizable:
            continue
        info = infos[r.codigo]
        filas.append({"id_artefacto": r.id_artefacto, "codigo": r.codigo, "anio": r.anio, "mes": r.mes,
                      "macrozona": tipos.macrozona_o_ninguna(info.macrozona), "conjunto": str(info.conjunto),
                      "motivo": MotivoNoNormalizable(r.motivo).value, "origen": OrigenAborto(r.origen).value})
    esquema = tipos.ESQUEMA_NO_NORMALIZABLES
    if not filas:
        return tipos.tabla_vacia(esquema)
    d = pd.DataFrame(filas, columns=list(esquema)).astype(dict(esquema))
    d = d.sort_values("id_artefacto", kind="stable").reset_index(drop=True)
    tipos.validar_esquema(d, esquema, nombre="no normalizables")
    d.attrs["esquema"] = esquema.version
    return d


# ---------------------------------------------------------------------------
# Alarmas (§2.7; QC-23, QC-24)
# ---------------------------------------------------------------------------
def _exigir_conteo(d, nombre: str) -> pd.DataFrame:
    if not isinstance(d, pd.DataFrame) or list(d.columns) != list(COLUMNAS_CONTEO):
        raise ValueError(f"{nombre}: se espera una tabla con las columnas {list(COLUMNAS_CONTEO)}")
    return d


def _suma(d: pd.DataFrame, clave: str, variable: str, *, macrozona: str | None = None, anios=None) -> int:
    sel = (d["clave"] == clave) & (d["variable"] == variable)
    if macrozona is not None:
        sel &= d["macrozona"] == macrozona
    if anios is not None:
        sel &= (d["anio"] >= anios[0]) & (d["anio"] <= anios[1])
    return int(d.loc[sel.fillna(False).to_numpy(bool), "n"].sum())


def _supera(num: int, den: int, pct) -> bool:
    return den > 0 and num * numerico.PORCENTAJE > pct * den


def _alarma(alarma: Alarma, regla: str, variable: str, zona: str, num: int, den: int) -> dict:
    return {"alarma": alarma.value, "regla": regla, "variable": variable, "zona": zona,
            "tasa": float(num * numerico.PORCENTAJE / den)}


def _macrozonas(*tablas: pd.DataFrame) -> list[str]:
    zonas = set()
    for d in tablas:
        zonas |= {str(z) for z in d["macrozona"].dropna().unique()}
    return sorted(zonas)


def alarmas(conteos, denominadores, umbrales) -> list[dict]:
    """Q1, Q1z, Q2 y Q3 (§2.7, con EMC1-1, EMC1-3, D9 y D10): las que saltan (QC-23)."""
    num = _exigir_conteo(conteos, "conteos")
    den = _exigir_conteo(denominadores, "denominadores")
    zonas = _macrozonas(num, den)
    salida = []
    for m in tipos.MARCAS_Q1:
        clave_den = DEN_Q1_RANGO if m is Marca.FUERA_DE_RANGO else DEN_Q1
        for v in _FUENTE:
            n, d = _suma(num, clave_q1(m), v.value), _suma(den, clave_den, v.value)
            if _supera(n, d, umbrales.a("Q1_PCT")):
                salida.append(_alarma(Alarma.Q1, m.nombre_texto, v.value, ZONA_NACIONAL, n, d))
            for z in zonas:
                n, d = (_suma(num, clave_q1(m), v.value, macrozona=z), _suma(den, clave_den, v.value, macrozona=z))
                if _supera(n, d, umbrales.a("Q1Z_PCT")):
                    salida.append(_alarma(Alarma.Q1Z, m.nombre_texto, v.value, z, n, d))
    periodo = (umbrales.a("Q2_DESDE"), umbrales.a("Q2_HASTA"))
    for v in _FUENTE:
        n, d = _suma(num, NUM_Q2, v.value, anios=periodo), _suma(den, DEN_Q2, v.value, anios=periodo)
        if _supera(n, d, umbrales.a("Q2_PCT")):
            salida.append(_alarma(Alarma.Q2, REGLA_Q2, v.value, ZONA_NACIONAL, n, d))
        for z in zonas:
            n = _suma(num, NUM_Q2, v.value, macrozona=z, anios=periodo)
            d = _suma(den, DEN_Q2, v.value, macrozona=z, anios=periodo)
            if _supera(n, d, umbrales.a("Q2Z_PCT")):
                salida.append(_alarma(Alarma.Q2, REGLA_Q2, v.value, z, n, d))
    n, d = _suma(num, NUM_NO_NORMALIZABLES, VARIABLE_ARTEFACTO), _suma(den, DEN_ARTEFACTOS, VARIABLE_ARTEFACTO)
    if _supera(n, d, umbrales.a("Q3_PCT")):
        salida.append(_alarma(Alarma.Q3, REGLA_Q3, VARIABLE_ARTEFACTO, ZONA_NACIONAL, n, d))
    return salida


def lista_descriptiva(conteos, denominadores, umbrales) -> list[dict]:
    """§2.7: las estaciones con más del 30 % de horas marcadas en alguna variable de la fuente (QC-24)."""
    num = _exigir_conteo(conteos, "conteos")
    den = _exigir_conteo(denominadores, "denominadores")
    n = num[num["clave"] == NUM_Q1_ALGUNA].groupby(["codigo", "variable"])["n"].sum()
    d = den[den["clave"] == DEN_Q1_RANGO].groupby(["codigo", "variable"])["n"].sum()
    salida: dict[str, list[str]] = {}
    for (codigo, variable), total in d.items():
        marcadas = int(n.get((codigo, variable), 0))
        if _supera(marcadas, int(total), umbrales.a("LISTA_PCT")):
            salida.setdefault(str(codigo), []).append(str(variable))
    orden = [v.value for v in _FUENTE]
    return [{"codigo": c, "variables": sorted(vs, key=orden.index)} for c, vs in sorted(salida.items())]


def _agregado(d: pd.DataFrame, *, anios=None) -> list[dict]:
    if anios is not None:
        d = d[(d["anio"] >= anios[0]) & (d["anio"] <= anios[1])]
    if d.empty:
        return []
    g = d.groupby(["clave", "variable", "macrozona", "conjunto"], dropna=False, sort=True)["n"].sum()
    return [{"clave": str(c), "variable": str(v), "macrozona": None if pd.isna(z) else str(z), "conjunto": str(j),
             "n": int(n)} for (c, v, z, j), n in g.items()]


def resumen_qc(conteos, alarmas, no_normalizables, sin_traslado, *, denominadores, lista, umbrales) -> dict:
    """``qc/resumen_qc.json`` (§8; QC-25): sólo marcas, conteos y listas, sin estadísticas del residuo."""
    num = _exigir_conteo(conteos, "conteos")
    den = _exigir_conteo(denominadores, "denominadores")
    tipos.validar_esquema(no_normalizables, tipos.ESQUEMA_NO_NORMALIZABLES, nombre="no normalizables")
    periodo = (int(umbrales.a("Q2_DESDE")), int(umbrales.a("Q2_HASTA")))
    q2 = [DEN_Q2, DEN_Q2_FUERA, NUM_Q2]
    nn = no_normalizables
    if len(nn):
        g = nn.groupby(["motivo", "origen", "macrozona", "conjunto"], dropna=False, sort=True).size()
        por_motivo = [{"motivo": str(m), "origen": str(o), "macrozona": None if pd.isna(z) else str(z),
                       "conjunto": str(j), "n": int(n)} for (m, o, z, j), n in g.items()]
    else:
        por_motivo = []
    sin_macrozona = sorted({str(c) for c in den.loc[den["macrozona"].isna(), "codigo"]})
    return {
        "schema": ESQUEMA_RESUMEN_QC,
        "conteos": _agregado(num),
        "denominadores": _agregado(den),
        "q2_periodo": {"desde": periodo[0], "hasta": periodo[1]},
        "q2": _agregado(pd.concat([num[num["clave"].isin(q2)], den[den["clave"].isin(q2)]], ignore_index=True),
                        anios=periodo),
        "alarmas": [dict(a) for a in alarmas],
        "detener": bool(alarmas),
        "no_normalizables": {"total": int(len(nn)), "por_motivo": por_motivo},
        "sin_prueba_de_traslado": sorted({str(c) for c in sin_traslado}),
        "sin_macrozona": sin_macrozona,
        "lista_descriptiva": [dict(x) for x in lista],
    }


# ---------------------------------------------------------------------------
# RR06 (§2.6; QC-21)
# ---------------------------------------------------------------------------
def _estacion_del_anio(h: np.ndarray) -> np.ndarray:
    mes = homogeneidad.mes2000(h) % 12 + 1                                # 1 = enero
    return np.array(_ESTACIONES_DEL_ANIO, dtype=object)[mes % 12]


def _metricas_rr06(obs: np.ndarray, prod: np.ndarray, umbral_mm: float) -> dict:
    n = len(obs)
    salida = {"n_periodos": int(n), "total_obs_mm": float(obs.sum()) if n else 0.0,
              "total_lluvia_producto_mm": float(prod.sum()) if n else 0.0}
    salida["diferencia_totales_mm"] = salida["total_lluvia_producto_mm"] - salida["total_obs_mm"]
    salida["cociente_totales"] = (salida["total_lluvia_producto_mm"] / salida["total_obs_mm"]
                                  if salida["total_obs_mm"] > 0 else None)
    salida["frecuencia_obs_lluvia"] = float((obs >= umbral_mm).mean()) if n else None
    salida["frecuencia_lluvia_producto"] = float((prod >= umbral_mm).mean()) if n else None
    if n >= 2 and obs.std() > 0 and prod.std() > 0:
        salida["correlacion"] = float(np.corrcoef(obs, prod)[0, 1])
    else:
        salida["correlacion"] = None
    return salida


def sumas_lluvia_rr06(tablas, infos, enlaces, tp_horario, *, h, pixel_ids, previas=None) -> dict:
    """D27 (QC-21): código → (suma de 6 h en mm, sin enlace), alineadas con las filas de su tabla ancha, con el píxel
    que ``enlaces_productos.parquet`` enlaza a la celda de la estación (``fondo_era5l.pixel_de_lluvia``) y la serie
    continua de un lote de meses (``fondo_era5l.incrementos_tp`` y ``horas_de``, ``pixel_ids`` del primer mes). Con
    ``previas`` (lo de los lotes anteriores) sólo se llenan las sumas que siguen NaN: así se arma por años, como
    ``meteo_civil_v3``. Los errores del fondo (``ErrorFondo``) no se capturan."""
    salida = {}
    for codigo in sorted(tablas):
        t = tablas[codigo]
        tipos.validar_esquema(t, tipos.ESQUEMA_QC_ESTACION, nombre=f"tabla ancha de {codigo}")
        pixel = fondo_era5l.pixel_de_lluvia([infos[codigo].celda], enlaces)[0]
        fin = t["h"].to_numpy(np.int64)
        suma, sin = fondo_era5l.lluvia_rr06(tp_horario, fin, np.full(len(fin), pixel, dtype=np.int64), h=h,
                                            pixel_ids=pixel_ids)
        if previas is not None and codigo in previas:
            antes, _ = previas[codigo]
            antes = np.asarray(antes, dtype=np.float64)
            if antes.shape != suma.shape:
                raise ValueError(f"{codigo}: las sumas previas no van alineadas con la tabla")
            suma = np.where(np.isfinite(antes), antes, suma)
        salida[codigo] = (suma, sin)
    return salida


def validar_rr06(tablas, tp_sumas, infos, umbrales) -> dict:
    """§2.6 (QC-21). ``tablas``: código → tabla ancha (``ESQUEMA_QC_ESTACION``); ``tp_sumas``: código → (suma de 6 h
    en mm, sin enlace), alineados con las filas de su tabla ancha (``fondo_era5l.lluvia_rr06`` con h_fin = ``h``);
    ``infos``: código → InfoEstacion. Descriptivo: no cambia la lluvia ni entra en §6."""
    umbral = constantes.valor("RR06_LLUVIA_MM")
    filas = []
    sin_enlace = incompleta = 0
    for codigo in sorted(tablas):
        t = tablas[codigo]
        tipos.validar_esquema(t, tipos.ESQUEMA_QC_ESTACION, nombre=f"tabla ancha de {codigo}")
        suma, sin = tp_sumas[codigo]
        suma, sin = np.asarray(suma, dtype=np.float64), np.asarray(sin, dtype=bool)
        if suma.shape != (len(t),) or sin.shape != (len(t),):
            raise ValueError(f"{codigo}: las sumas de 6 h van alineadas con las filas de la tabla")
        validos = t["rr06_valido"].to_numpy(bool) & np.isfinite(t["rr06_mm"].to_numpy(np.float64))
        sin_enlace += int((validos & sin).sum())
        incompleta += int((validos & ~sin & ~np.isfinite(suma)).sum())
        par = validos & ~sin & np.isfinite(suma)
        if not par.any():
            continue
        h = t["h"].to_numpy(np.int64)[par]
        zona = tipos.macrozona_o_ninguna(infos[codigo].macrozona)
        filas.append(pd.DataFrame({"macrozona": zona, "estacion": _estacion_del_anio(h),
                                   "obs": t["rr06_mm"].to_numpy(np.float64)[par], "prod": suma[par]}))
    grupos = []
    if filas:
        todo = pd.concat(filas, ignore_index=True)
        for est in ("DEF", "MAM", "JJA", "SON"):
            sel = todo[todo["estacion"] == est]
            grupos.append({"zona": ZONA_NACIONAL, "estacion_del_anio": est,
                           **_metricas_rr06(sel["obs"].to_numpy(), sel["prod"].to_numpy(), umbral)})
            for z, sub in sel.groupby(sel["macrozona"].fillna(""), sort=True):
                grupos.append({"zona": z or None, "estacion_del_anio": est,
                               **_metricas_rr06(sub["obs"].to_numpy(), sub["prod"].to_numpy(), umbral)})
        grupos.append({"zona": ZONA_NACIONAL, "estacion_del_anio": None,
                       **_metricas_rr06(todo["obs"].to_numpy(), todo["prod"].to_numpy(), umbral)})
    return {"schema": ESQUEMA_RR06, "sujeto": SUJETO_RR06, "umbral_lluvia_mm": umbral,
            "reportes_sin_enlace": sin_enlace, "reportes_ventana_incompleta": incompleta, "grupos": grupos}
