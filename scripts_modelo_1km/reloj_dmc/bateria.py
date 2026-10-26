"""Batería D (§8.D) y ajuste de umbrales antes de C1 (§8.F).

- ``tabla_bateria`` genera bateria_v1.csv desde la especificación de §8.D con
  ``sintetico.especificacion_bateria`` (7.320 estaciones en 50 redes: D1 núcleo con 20 réplicas, D2
  perturbaciones con 10, D3 E6 con 10). Una fila por estación sintética (COLUMNAS_BATERIA). Su sha256
  (``escribir_bateria`` o ``huella_tabla``) va a reloj_dmc_v1.json["bateria"] (R-04) y al addendum.
- ``redes``: cada combinación de sesgo de referencia y réplica es una red con todas sus estaciones; la
  calibración de E3t y A3 a A5 se calculan dentro de cada red (R-29).
- ``correr_red``: una red por ``orquestacion.evaluar_red``, con ``sintetico.entrada_en_memoria`` y la
  referencia ``SerieEra5Memoria`` (``sintetico.serie_era5_de_casos``) y
  ``OpcionesCorrida(conservar_etiquetas=True)``. Devuelve una fila por estación-año (ESQUEMA_RESULTADOS)
  con el veredicto, la verdad del año, la traza mínima para §8.F y la ida y vuelta de la política (§8,
  «Reglas comunes»: obligatoria también en D).
- ``criterios_por_celda``, ``es_confirmacion_erronea`` y ``es_confirmacion_correcta``: los criterios de §8.D.
- ``correr_bateria``: todas las redes, con el tiempo medido (reloj de pared y CPU, carga y memoria pico);
  ``replicas_por_tiempo`` baja D2 y D3 a 5 réplicas si pasa de 48 h (el núcleo nunca);
  ``proyectar_horas`` extrapola una medición.
- ``ajustar_umbrales``: §8.F, sólo hacia lo conservador, desde los valores del Anexo B, con
  ``registro_8F.jsonl`` y la salida de cada iteración en ``resultados_bateria_iterNN.parquet``.
- ``escribir_salidas``: bateria_v1.csv, resultados_bateria.parquet, criterios_bateria.json y
  tiempo_bateria.json en una carpeta (en una corrida de verdad, LOCAL/…/v1/c1/; en las pruebas, una
  temporal), más el registro de §8.F si se le da. Nunca bajo /Volumes ni en los repositorios
  (entorno.escribir_atomico).
- ``bateria_c1``: el camino único de ``--sintetico --bateria``: mide la batería con los valores del Anexo
  B antes de C1, la reduce si pasa de 48 h, la usa como primera corrida de §8.F y escribe todo con
  ``escribir_salidas``. Devuelve las sha256 para el addendum.
Depende de: sintetico, orquestacion, umbrales, constantes, tipos; además entorno (escritura y zonas),
extraccion y fijados (catálogo sintético, píxeles e InfoEstacion, como las pruebas del grupo C), tablas
(calendario) y politica (huellas de la política en memoria).

Lecturas propias de este módulo (van al addendum de C1):
- BAT-1. La verdad de un estación-año es el conjunto de las H de P que dan el mismo u que el reloj
  verdadero en todas las etiquetas con datos del año donde H está definida
  (``sintetico.equivalentes_en_P``), intersecado entre las variables con reloj propio (en el tipo g, Ts
  y QFE). Vacío = el verdadero está fuera de P ese año («fuera de P» se juzga por año: Cv(Santiago) es
  C(Santiago) en 2009; en 2018 ningún reloj de P coincide con el cambio de F(−4) a F(0)).
- BAT-2. Confirmación errónea (§8.D): el veredicto final (después de §5.3) es «confirmado» y (a) es del
  tipo g, o (b) la verdad del año es vacía, o (c) algún miembro de la clase confirmada no está en la
  verdad. (c) es la lectura estricta de «difiera del verdadero en alguna etiqueta del año»: cuenta todas
  las etiquetas con datos del año, también las de los meses que se quedan sin regla (partes
  discordantes, cuarentena). Ver BAT-9.
- BAT-3. Las líneas responsables de §8.F salen de la traza de cada confirmación errónea, sumando los tres
  puntos del texto (lectura acumulativa): si la verdad del año no es vacía, las líneas que excluyeron
  (paso 3 de §5.1) alguna clase que contiene un miembro de la verdad; si es vacía (el verdadero no está
  en P ese año), las líneas de apoyo del reloj confirmado; y en el tipo g, además, T-P. En el tipo g la
  verdad es siempre vacía (BAT-1: Ts y QFE no comparten reloj de P), así que responden T-P y las de
  apoyo. Una confirmación errónea sin línea responsable en la traza (la clase confirmada contiene al
  verdadero y a otra H que difiere de él) hace fallar C1: §8.F no tiene qué mover.
- BAT-4. «Sensibilidad por reloj»: estación-años confirmados con el reloj verdadero (correctos) sobre
  los estación-años con datos de las celdas de referencia de ese reloj, sumando sus celdas (tipos a y b):
  D1, datos completos, 33,4° S (el sitio «santiago» del generador), sin perturbación y red de sesgo 0.
  La razón civil compara la de C(Santiago) con la de F(0).
- BAT-5. «Confirmación correcta ≥ 90 %» [Enmienda 3, E3-6: enmienda motivada de la frase de §8.D, decidida por el
  autor el 2026-10-24 viendo resultados de la batería sintética, no datos DMC]. DECIDE la lectura estrecha a
  ≤ 50° S: tipos a y b (los dos traen QFE y RR06 en el generador), sin otra perturbación que el sesgo térmico
  de la referencia con |sesgo| ≤ 1 h (D1 sin perturbación y D2 «sesgo_termico_referencia»; 0 fuera de las
  redes con sesgo), datos completos o con 30 % faltante y |lat| ≤ 50°, sin Pascua ni Juan Fernández (BAT-7)
  y sin los años con la verdad vacía (fuera de P). El límite de 50° es el de la frase de §8.D, «a ≤ 50° S»
  (BATERIA_CORRECTA_LAT_S en CONSTANTES_BATERIA, con su fragmento del v1.0.3). Su motivo es la regla fina
  (FINA_LAT_MAX, §4.3.4), que es por lo que §6 y C3b no exigen separar F(−3), F(−4) y C(Santiago) al sur
  de 50° S, pero la frase que rige es la de §8.D. Deja fuera C(Punta_Arenas) a 53,0° S. La unidad es el
  estación-año, como en la sensibilidad; se informa también cuántos casos (estaciones) y celdas entran. El
  v1.0.3 lo aclara: entran los del bloque D1 sin perturbación y los del D2 con sólo ese sesgo; D3 no. Al
  lado, sin decidir, se
  informan la lectura literal (``lectura_literal``: tipos a o b, completo o 30 % faltante y |sesgo| ≤ 1 h, de
  cualquier bloque y con cualquier otra perturbación —desfase térmico, S1 local, fase de S2, semántica,
  latitud, territorio incierto, D3 con ISD—: 195 celdas) y la estrecha sin acotar la latitud
  (``lectura_estrecha``: 56 celdas). En las semánticas de ±0,5 h, «correcta» exige la marca (BAT-6).
- BAT-6. «Semánticas de ±0,5 h»: en las celdas D2 «semantica» con |Δc| = 0,5 h, una confirmación del
  reloj entero verdadero sin la marca «posible media horaria» de la estación no es errónea ni correcta
  (``es_confirmacion_correcta``: también en la columna «correcta» y en la sensibilidad por celda); la
  fracción con marca, sumada sobre esas celdas, debe ser ≥ 90 % (BAT_MEDIA_HORARIA_PCT). Sin
  confirmaciones, el criterio se cumple en vacío y se informa n = 0. La de −10 min no exige la marca.
- BAT-7. «Lo indecidible queda sin confirmar» se lee al pie de la letra en D1 y D2: ningún estación-año
  confirmado en las celdas de tipo e, ni en las de Isla de Pascua o Juan Fernández (todos sus relojes).
  [Enmienda 4, E4-1, texto v1.0.4, decidida por el autor el 2026-10-25 viendo la primera corrida de la
  batería completa, no datos DMC: el tipo f (cada 6 h) sale de la lista («el tipo f puede confirmarse, y
  toda confirmación errónea suya cuenta como tal»). Con el v1.0.3 la lista era «tipos e y f».] Las
  confirmaciones del tipo f no hacen fallar este criterio; las erróneas cuentan en «cero erróneas»
  (BAT-2), como las de cualquier celda, y el criterio las informa aparte (``tipo_f``). D3 activa E6, que
  es justo lo que los vuelve decidibles (§6), y no entra. Es la lectura conservadora; §6 sugiere otra
  más estrecha (la firma UTC con calendario propio de Pascua frente a F(−3), y F(0) frente a F(−3) sin
  píxel ni E6), que se informa aparte como diagnóstico (``indecidible_estrecho``), dentro de la misma
  lista (sin el tipo f).
- BAT-8. «Sin cruces»: una confirmación cruza si el verdadero es sólo civil (C o Cv) y la clase no tiene
  ningún miembro C, o si es sólo fijo y la clase no tiene ningún miembro F (una clase fusionada que
  contiene a ambos no cruza). «El cambio de 2018 queda ubicado en 2018» se lee «sin error de ubicación»
  [decisión del autor del 2026-10-24, lectura del addendum; afloja la lectura estricta anterior y se decidió
  viendo resultados de la batería sintética, no datos DMC]: en las celdas con cambio de reloj, el año del
  cambio no se confirma, ningún año es erróneo y todo cambio detectado (decision.rachas, «último año de la
  racha anterior - primer año de la siguiente») contiene al año del cambio (a < 2018 < b) sin ningún año
  confirmado dentro del intervalo. Un cambio en (2014, 2019) con 2015-2017 insuficientes queda ubicado; uno
  en (2016, 2017) no. Se informa al lado la lectura estricta anterior (``mal_ubicadas_lectura_estricta``: el
  año del cambio como el único año con datos entre las dos rachas), sin que decida. Una estación sin cambio
  detectado (una sola racha, o ninguna) no comete un error de ubicación y el criterio pasa, pero se cuenta y
  se nombra aparte (``sin_cambio_detectado``).
- BAT-9. La ida y vuelta (§8, «Reglas comunes») se comprueba en cada estación de la batería con la
  política armada en memoria (huellas sintéticas) y el adaptador fijado. Es un criterio más: toda
  etiqueta con regla vuelve a su u. La columna ``erronea`` (BAT-2) es más estricta que la ida y vuelta,
  que sólo mira las etiquetas con regla; ``criterios_por_celda`` informa cuántas confirmaciones
  erróneas son de estaciones cuya ida y vuelta pasa («erróneas sólo fuera de la regla»), que son las que
  cambiarían con la lectura menos estricta (C.21 da por bueno un año confirmado con una parte
  discordante sin regla).
- BAT-10. D3 comparte la red de sesgo 0 con D1 y D2 (R-29). La red corre con E6 activa sólo si tiene
  alguna estación de D3, y sólo éstas llevan ISD: en las demás E6 queda sin información, que equivale a
  inactiva para la decisión.
- BAT-11. Pérdidas por celda: «años falsamente discrepantes» son los discrepantes con la verdad no vacía
  (fuera del tipo g), sobre los estación-años de la celda; «pérdida por inestabilidad» es la fracción de
  estaciones de la celda que §5.3 deja inestables.
- BAT-12. Los criterios de §8.D se evalúan con los umbrales fijos de «Batería» del Anexo B
  (BAT_SENSIBILIDAD, BAT_RAZON_CIVIL, BAT_CORRECTA_PCT, BAT_MEDIA_HORARIA_PCT, BAT_HORAS_MAX) y con las
  constantes del cuerpo de CONSTANTES_BATERIA (con su fragmento literal; hoy viven aquí, ver pendientes).
  C1 aprueba la batería sólo si se cumplen todos (§10: «se aprueban las pruebas de §8, grupos A a D»);
  §8.F sólo actúa sobre las confirmaciones erróneas, y si éstas llegan a cero y falla otro criterio, C1
  falla y se enmienda.
- BAT-13. «Supera 48 h de cómputo»: más de BAT_HORAS_MAX horas medidas (o proyectadas) de la batería
  completa; entonces D2 y D3 bajan a 5 réplicas y la tabla se regenera. Decide el reloj de pared
  (time.perf_counter, MEDIDA_TIEMPO), como hasta ahora; tiempo_bateria.json registra además el tiempo de
  CPU del proceso (time.process_time), la carga del sistema al empezar y al terminar, la memoria pico y
  si la reducción cambiaría con la otra medida (``reduccion_depende_de_la_medida``). Con la máquina
  cargada el reloj de pared puede pasar el tope por la competencia de CPU: cuál de las dos es «cómputo»
  lo fija el autor (§9 pide la máquina libre para la corrida confirmatoria).
- BAT-14. §8.F: la primera corrida es con los valores del Anexo B (ningún paso movido; si llegan umbrales
  ya movidos, ValueError). En cada iteración se mueve un paso, en cada línea responsable, el primer
  umbral no agotado de su fila (umbrales.siguiente_ajuste). Si alguna línea responsable no tiene umbral
  que mover (lista agotada o línea sin filas, como E3d o P7), C1 falla. Se repite toda la batería después
  de cada iteración. El registro guarda por iteración la fecha UTC, la huella de los umbrales, los pasos,
  la salida (``salida_archivo`` y ``salida_sha256``), las erróneas por celda, las líneas responsables, el
  motivo y los umbrales movidos (de → a). La salida de cada iteración es un archivo:
  resultados_bateria_iterNN.parquet junto a registro_8F.jsonl, con los mismos bytes que
  resultados_bateria.parquet (``huella_resultados`` es su sha256), así que la de la última iteración
  coincide con resultados_bateria.parquet.
- BAT-15. §8.28 («las salidas no contienen “@”») frente a la gramática de tramos de sintetico, que escribe
  «F(-4);F(0)@2018-07-01T00:00Z» en las columnas «reloj_verdadero» y «celda» de bateria_v1.csv (720 veces)
  y en los nombres de celda de las demás salidas. Pendiente del autor: si §8.28 rige en C1, el separador
  cambia en sintetico y la sha256 de bateria_v1.csv se regenera antes de escribir la clave «bateria»
  (R-04). Hasta entonces test_bateria admite sólo ese «@», con la excepción nombrada.
"""
from __future__ import annotations

import gzip
import io
import json
import math
import os
import platform
import resource
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, Mapping, Sequence

import numpy as np
import pandas as pd

from reloj_dmc import entorno, extraccion, fijados, orquestacion, sintetico
from reloj_dmc import politica as mod_politica
from reloj_dmc import tablas as mod_tablas
from reloj_dmc import umbrales as mod_umbrales
from reloj_dmc.constantes import ConstanteTexto
from reloj_dmc.constantes import valor as constante
from reloj_dmc.tipos import Hipotesis, Linea, Territorio, Veredicto, tabla_vacia, validar_esquema
from reloj_dmc.umbrales import Umbrales

COLUMNAS_BATERIA = ("caso", "bloque", "celda", "reloj_verdadero", "fuera_de_P", "tipo", "escenario", "territorio",
                    "lat", "lon", "con_pixel", "cod_comuna", "perturbacion", "valor_perturbacion", "red", "replica",
                    "semilla")
TIPOS_BATERIA = {"fuera_de_P": "bool", "con_pixel": "bool", "cod_comuna": "int64", "replica": "int64",
                 "semilla": "int64", "lat": "float64", "lon": "float64", "valor_perturbacion": "float64"}

# Constantes del cuerpo de §8.D que usan los criterios y que no están en constantes.py (BAT-12). Llevan
# su fragmento literal; test_bateria las verifica con constantes.verificar_contra_texto.
CONSTANTES_BATERIA = (
    ConstanteTexto("BATERIA_LAT_REFERENCIA", 33.4, "§8.D",
                   "(tipos a y b, datos completos, 33,4° S, sin perturbación)"),
    ConstanteTexto("BATERIA_SESGO_CORRECTA", 1, "§8.D", "|sesgo| ≤ 1 h"),
    ConstanteTexto("BATERIA_SEMANTICA_H", 0.5, "§8.D",  # no-umbral: definición con su fragmento (BAT-12)
                   "**Semánticas de ±0,5 h.**"),
    # BAT-5 con la Enmienda 3, E3-6: «a ≤ 50° S». El 90 % que cita es BAT_CORRECTA_PCT del Anexo B.
    ConstanteTexto("BATERIA_CORRECTA_LAT_S", 50,  # no-umbral: constante del cuerpo con su fragmento (BAT-12)
                   "§8.D", "en ≥ 90 % de los casos de tipo a y b con QFE y RR06, a ≤ 50° S",
                   ajenos=(90,), desde="v1.0.3"),  # no-umbral: el 90 citado es BAT_CORRECTA_PCT, ajeno
)
_CONSTANTES = {c.nombre: c.valor for c in CONSTANTES_BATERIA}

# Factores de las celdas (textos de bateria_v1.csv; no son umbrales).
BLOQUE_NUCLEO, BLOQUE_PERTURBACIONES, BLOQUE_E6 = "D1", "D2", "D3"
SIN_PERTURBACION = "ninguna"
PERTURBACION_SESGO = "sesgo_termico_referencia"
PERTURBACION_SEMANTICA = "semantica"
TIPO_G = "g"
TIPOS_CON_QFE_Y_RR = ("a", "b")                 # §8.D: «tipo a y b con QFE y RR06»
TIPOS_INDECIDIBLES = ("e",)                     # §8.D, v1.0.4 (E4-1): «tipo e»; en el v1.0.3, «tipos e y f»
TIPO_SEIS_HORAS = "f"                           # §8.D, v1.0.4 (E4-1): «el tipo f puede confirmarse»
# La frase de §8.D que fija TIPOS_INDECIDIBLES (BAT-7), tal cual en el texto vigente; test_bateria la busca.
FRAGMENTO_INDECIDIBLE = ("lo indecidible (tipo e, Pascua y Juan Fernández) queda sin confirmar; el tipo f puede "
                         "confirmarse, y toda confirmación errónea suya cuenta como tal")
TERRITORIOS_INDECIDIBLES = (str(Territorio.PASCUA_SALA_Y_GOMEZ), str(Territorio.JUAN_FERNANDEZ_DESVENTURADAS))
ESCENARIO_COMPLETO = sintetico.ESCENARIOS[0]
ESCENARIOS_CORRECTA = sintetico.ESCENARIOS[:2]  # completo y con 30 % faltante
RELOJES_REFERENCIA = ("F(0)", "F(-3)", "F(-4)", "C(America/Santiago)")   # como en bateria_v1.csv
RELOJ_FIJO_DE_LA_RAZON, RELOJ_CIVIL_DE_LA_RAZON = "F(0)", "C(America/Santiago)"
CELDAS_REFERENCIA = {"bloque": (BLOQUE_NUCLEO,), "tipo": TIPOS_CON_QFE_Y_RR, "escenario": (ESCENARIO_COMPLETO,),
                     "lat": (-_CONSTANTES["BATERIA_LAT_REFERENCIA"],), "perturbacion": (SIN_PERTURBACION,),
                     "reloj_verdadero": RELOJES_REFERENCIA}
SEPARADOR = orquestacion.SEPARADOR_CLASE          # «|», también para listas de líneas e ids

# Una fila por estación-año evaluado (resultados_bateria.parquet).
ESQUEMA_RESULTADOS = {
    "red": "string", "caso": "string", "bloque": "string", "celda": "string", "reloj_verdadero": "string",
    "tipo": "string", "escenario": "string", "territorio": "string", "perturbacion": "string",
    "valor_perturbacion": "float64", "replica": "int64", "anio": "int16",
    "veredicto": "string", "motivo": "string", "clase_confirmada": "string",
    "verdad": "string",            # ids de P equivalentes al verdadero en el año (BAT-1), «|»; "" fuera de P
    "correcta": "bool",            # confirmado y clase ⊆ verdad (fuera del tipo g)
    "erronea": "bool",             # es_confirmacion_erronea (BAT-2)
    "cruce": "bool",               # BAT-8
    "clase_paso_9": "string",      # clase confirmada en el paso 9, antes de §5.3 (diagnóstico)
    "erronea_paso_9": "bool",      # esa clase habría sido errónea (BAT-2) si §5.3 no la dejaba sin confirmar
    "excluyen_verdad": "string",   # líneas que excluyeron una clase con un miembro de la verdad, «|»
    "lineas_apoyo": "string",      # «|»
    "guarda_tp": "string",         # resultado de T-P en el paso 5 (pasa, falla, no_evaluable) o NA
    "n_partes_discordantes": "int16",
    "meses_con_regla": "int16",    # meses del año con regla (§5.3)
    "reglas_vencidas": "bool",
    "modo_e3t": "string",
    "media_horaria": "bool",       # marca «posible media horaria» de la estación (§4.3.5)
    "inestable": "bool",           # estación inestable (§5.3.1)
    "cambios": "string",           # cambios de reloj de la estación (decision.rachas), «2017-2019;…»
    "ida_y_vuelta": "string",      # «ok», «falla» o «sin_politica» (BAT-9), de la estación
    "fallas_ida_y_vuelta": "int32",
    "a4_restringe": "bool",
    "a5_alto": "bool",
}
IDA_Y_VUELTA_OK, IDA_Y_VUELTA_FALLA, SIN_POLITICA = "ok", "falla", "sin_politica"

ARCHIVO_TABLA = "bateria_v1.csv"
ARCHIVO_RESULTADOS = "resultados_bateria.parquet"
ARCHIVO_CRITERIOS = "criterios_bateria.json"
ARCHIVO_TIEMPO = "tiempo_bateria.json"
ARCHIVO_REGISTRO_8F = "registro_8F.jsonl"
PLANTILLA_SALIDA_ITERACION = "resultados_bateria_iter{:02d}.parquet"   # la «salida» de cada iteración de §8.F
CARPETA_C1 = "c1"                                 # bajo LOCAL/modelado_1km/verificacion_reloj_dmc/v1 (R-32)
SEGUNDOS_POR_HORA = 3600
MEDIDA_TIEMPO = "reloj de pared (time.perf_counter)"   # la que decide la reducción de §8.D (BAT-13)
_BYTES_POR_KIB = 1 << 10             # no-umbral: bytes en un KiB (memoria pico)
EJEMPLOS_EN_MENSAJES = 10            # no-umbral: cuántos ejemplos cita un mensaje o el JSON de criterios
_COMMIT_SINTETICO = "0" * 40         # no-umbral: un commit de git tiene 40 hexadecimales


def _c(nombre: str):
    """Constante del cuerpo: las de constantes.py y las de CONSTANTES_BATERIA."""
    return _CONSTANTES[nombre] if nombre in _CONSTANTES else constante(nombre)


# ---------------------------------------------------------------------------------------------
# Tabla de casos (bateria_v1.csv) y redes
# ---------------------------------------------------------------------------------------------
def tabla_bateria(replicas_d2_d3: int | None = None) -> pd.DataFrame:
    """bateria_v1.csv en orden determinista (COLUMNAS_BATERIA). ``replicas_d2_d3`` = 5 tras la reducción
    (BATERIA_REPLICAS_REDUCIDAS); el núcleo siempre lleva sus 20 réplicas."""
    if replicas_d2_d3 is not None and replicas_d2_d3 != _c("BATERIA_REPLICAS_REDUCIDAS"):
        raise ValueError(f"sólo se admite la reducción de §8.D a {_c('BATERIA_REPLICAS_REDUCIDAS')} réplicas")
    tabla = sintetico.especificacion_bateria(replicas_d2_d3)
    if tuple(tabla.columns) != COLUMNAS_BATERIA or tuple(sintetico.COLUMNAS_BATERIA) != COLUMNAS_BATERIA:
        raise ValueError("las columnas de la especificación no son COLUMNAS_BATERIA")
    replicas = {BLOQUE_NUCLEO: _c("BATERIA_REPLICAS_D1"),
                BLOQUE_PERTURBACIONES: replicas_d2_d3 or _c("BATERIA_REPLICAS_D2"),
                BLOQUE_E6: replicas_d2_d3 or _c("BATERIA_REPLICAS_D3")}
    por_celda = tabla.groupby("celda", sort=False).agg(bloque=("bloque", "first"), n=("replica", "size"),
                                                       maximo=("replica", "max"))
    malas = por_celda[(por_celda["n"] != por_celda["bloque"].map(replicas)) | (por_celda["n"] != por_celda["maximo"])]
    if len(malas):
        raise ValueError("celdas con un número de réplicas distinto de §8.D: "
                         f"{list(malas.index[:EJEMPLOS_EN_MENSAJES])}")
    return tabla.reset_index(drop=True)


def _csv_bytes(tabla: pd.DataFrame) -> bytes:
    return tabla.to_csv(index=False, lineterminator="\n", na_rep="").encode("utf-8")


def huella_tabla(tabla: pd.DataFrame) -> str:
    """sha256 de bateria_v1.csv tal como lo escribe ``escribir_bateria``."""
    return entorno.sha256_bytes(_csv_bytes(tabla[list(COLUMNAS_BATERIA)]))


def escribir_bateria(tabla: pd.DataFrame, ruta: Path) -> str:
    """CSV UTF-8 con «\\n», sin índice; devuelve sha256 (escritura atómica, nunca bajo /Volumes)."""
    if tuple(tabla.columns) != COLUMNAS_BATERIA:
        raise ValueError("la tabla no tiene las columnas de COLUMNAS_BATERIA, en orden")
    return entorno.escribir_atomico(Path(ruta), _csv_bytes(tabla))


def leer_bateria(ruta: Path) -> pd.DataFrame:
    """bateria_v1.csv con los tipos de la especificación (la ida y vuelta de ``escribir_bateria``)."""
    tabla = pd.read_csv(ruta, dtype={"caso": str, "semilla": "int64"}, keep_default_na=False,
                        na_values={"valor_perturbacion": [""]}, float_precision="round_trip")
    if tuple(tabla.columns) != COLUMNAS_BATERIA:
        raise ValueError(f"{Path(ruta).name}: columnas distintas de COLUMNAS_BATERIA")
    for c in ("fuera_de_P", "con_pixel"):
        if not set(tabla[c].astype(str)) <= {"True", "False"}:
            raise ValueError(f"{Path(ruta).name}: «{c}» no es booleana")
        tabla[c] = tabla[c].astype(str) == "True"
    return tabla.astype(TIPOS_BATERIA)


def redes(tabla: pd.DataFrame) -> Iterator[tuple[str, pd.DataFrame]]:
    """(red, sus filas) en el orden de primera aparición en la tabla. Cada red es un sesgo de referencia
    y una réplica (R-29); se comprueba que no mezcle réplicas ni sesgos."""
    for red, filas in tabla.groupby("red", sort=False):
        if filas["replica"].nunique() != 1:
            raise ValueError(f"la red {red} mezcla réplicas")
        sesgos = {float(v) if p == PERTURBACION_SESGO else 0.0
                  for p, v in zip(filas["perturbacion"], filas["valor_perturbacion"])}
        if len(sesgos) != 1:
            raise ValueError(f"la red {red} mezcla sesgos de referencia")
        yield str(red), filas.reset_index(drop=True)


def celdas(tabla: pd.DataFrame) -> Sequence[str]:
    """Celdas (factores sin la réplica) en el orden de la tabla."""
    return list(dict.fromkeys(tabla["celda"].tolist()))


# ---------------------------------------------------------------------------------------------
# Una red
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ContextoBateria:
    """Lo que la batería carga una vez: calendario, MACROZONA_REGION y el adaptador fijado."""
    tablas: object                      # tablas.TablasCalendario
    macrozona_region: Mapping[int, str]
    adaptador: object | None            # meteorologia_v2 fijado (ida y vuelta); None la omite


def contexto_bateria(ap: Path | None = None, *, con_adaptador: bool = True) -> ContextoBateria:
    """Calendario con el paquete tzdata (§9: reset_tzpath(to=[])), MACROZONA_REGION por AST y el
    adaptador fijado, desde AP (por omisión, el repositorio de este paquete). No abre /Volumes."""
    ap = Path(ap) if ap is not None else entorno.rutas_reales().ap
    entorno.reiniciar_zonas("tzdata")
    return ContextoBateria(tablas=mod_tablas.cargar_tablas(), macrozona_region=fijados.macrozona_region(ap),
                           adaptador=fijados.cargar_adaptador(ap) if con_adaptador else None)


def _huellas(umbrales: Umbrales) -> mod_politica.HuellasPolitica:
    """Huellas de la política en memoria de una red sintética (no se publica ni se escribe)."""
    return mod_politica.HuellasPolitica(
        protocolo_sha256=mod_umbrales.SHA_PROTOCOLO_C0, commit_ap=_COMMIT_SINTETICO,
        configuracion_sha256=umbrales.sha256_json or mod_umbrales.SHA_JSON_C0,
        informe_sha256=entorno.sha256_bytes("batería D: sin informe".encode("utf-8")),
        artefactos_evaluados_sha256=entorno.sha256_bytes("batería D: extractos en memoria".encode("utf-8")),
        adaptador_sha256=fijados.SHA_ADAPTADOR, python=platform.python_version(),
        tzdata=mod_tablas.version_de_base(), transiciones_sha256=mod_tablas.SHA_ANEXO_A)


def _infos(casos: Sequence[sintetico.CasoSintetico], serie: sintetico.SerieEra5Memoria, umbrales: Umbrales,
           ctx: ContextoBateria) -> dict:
    """InfoEstacion de cada caso como en --aplicar (§3.3): catálogo DMC sintético leído con
    extraccion.leer_catalogo_dmc (desde una carpeta temporal), píxeles sintéticos, enlace y z_pix."""
    with tempfile.TemporaryDirectory(prefix="bateria_catalogo_") as carpeta:
        ruta = Path(carpeta) / "catalogo.json.gz"
        cuerpo = json.dumps({"stations": sintetico.catalogo_dmc_sintetico(casos)}, ensure_ascii=False)
        ruta.write_bytes(gzip.compress(cuerpo.encode("utf-8"), mtime=0))
        catalogo, _ = extraccion.leer_catalogo_dmc(ruta)
    pixeles = sintetico.catalogo_pixeles_sintetico(casos)
    validos = {int(p) for p in pixeles.loc[pixeles["valido"], "pixel_id"]}
    enlaces = extraccion.enlazar_pixeles(catalogo, pixeles, validos, umbrales)
    enlazados = sorted({e.pixel_id for e in enlaces.values() if e.pixel_id is not None})
    medias = {p: serie.media(p, "sp") for p in enlazados}          # sp̄ de todo el período (R-20)
    return extraccion.info_estaciones(catalogo, pixeles, enlaces, medias, {}, ctx.macrozona_region, umbrales)


def _variables_con_reloj(caso: sintetico.CasoSintetico) -> tuple[str, ...]:
    if len(caso.relojes) == 1:
        return ("Ts",)
    return tuple(r.variable for r in caso.relojes if r.variable is not None)


def _orden_ids(ids) -> list[str]:
    return sorted(ids, key=lambda h: Hipotesis.desde_id(h).orden())


def _verdad_por_anio(caso: sintetico.CasoSintetico, extracto: pd.DataFrame) -> dict[int, str]:
    """BAT-1: año → ids de P equivalentes al verdadero («|»), "" si está fuera de P ese año."""
    salida = {}
    for anio in sorted({int(a) for a in extracto["anio"].unique()}):
        comun = None
        for variable in _variables_con_reloj(caso):
            ids = set(sintetico.equivalentes_en_P(caso, anio, variable))
            comun = ids if comun is None else comun & ids
        salida[anio] = SEPARADOR.join(_orden_ids(comun or ()))
    return salida


def _clases_del_verdadero(caso: sintetico.CasoSintetico) -> frozenset[str]:
    """«F» y/o «C» según los tramos del reloj verdadero (Cv cuenta como civil; F0-Pascua como fijo)."""
    tipos = set()
    for reloj in caso.relojes:
        for _, spec in reloj.tramos:
            tipos.add("F" if spec == sintetico.PASCUA_PROPIO or spec.startswith("F(") else "C")
    return frozenset(tipos)


def _lista(valores) -> str:
    return SEPARADOR.join(str(v) for v in valores)


def _ids(texto) -> set[str]:
    if texto is None or (isinstance(texto, float) and math.isnan(texto)) or pd.isna(texto) or not str(texto):
        return set()
    return set(str(texto).split(SEPARADOR))


def es_confirmacion_erronea(fila: pd.Series) -> bool:
    """Difiere del verdadero en alguna etiqueta del año; verdadero fuera de P; o cualquier confirmación en
    (g) (§8.D; BAT-2). ``fila``: una fila de ESQUEMA_RESULTADOS (basta veredicto, tipo, verdad y clase)."""
    if str(fila["veredicto"]) != str(Veredicto.CONFIRMADO):
        return False
    if str(fila["tipo"]) == TIPO_G:
        return True
    verdad = _ids(fila["verdad"])
    if not verdad:
        return True
    miembros = _ids(fila["clase_confirmada"])
    return not miembros or not miembros <= verdad


def _con_el_verdadero(veredicto, tipo, verdad, clase) -> bool:
    """Confirmado con una clase no vacía contenida en la verdad del año (fuera del tipo g): la confirmación
    del reloj verdadero, sin mirar todavía la marca de media hora."""
    if str(veredicto) != str(Veredicto.CONFIRMADO) or str(tipo) == TIPO_G:
        return False
    miembros, en_verdad = _ids(clase), _ids(verdad)
    return bool(miembros) and bool(en_verdad) and miembros <= en_verdad


def _exige_marca(perturbacion, valor) -> bool:
    """Celda de semántica de ±0,5 h (BAT-6): la confirmación sólo es correcta con la marca."""
    if str(perturbacion) != PERTURBACION_SEMANTICA or valor is None or pd.isna(valor):
        return False
    return bool(np.isclose(abs(float(valor)), _c("BATERIA_SEMANTICA_H")))


def es_confirmacion_correcta(fila: pd.Series) -> bool:
    """Confirmada con el reloj verdadero (clase ⊆ verdad del año, fuera del tipo g) y, en las semánticas de
    ±0,5 h, con la marca «posible media horaria» de la estación (§8.D; BAT-6). ``fila``: una fila de
    ESQUEMA_RESULTADOS (basta veredicto, tipo, verdad, clase, perturbación, su valor y media_horaria)."""
    if not _con_el_verdadero(fila["veredicto"], fila["tipo"], fila["verdad"], fila["clase_confirmada"]):
        return False
    return not _exige_marca(fila["perturbacion"], fila["valor_perturbacion"]) or bool(fila["media_horaria"])


def _cruza(clase: str | None, del_verdadero: frozenset[str]) -> bool:
    """BAT-8: un verdadero sólo civil confirmado sin miembro C, o sólo fijo sin miembro F."""
    if not clase or len(del_verdadero) != 1:
        return False
    tipos = {Hipotesis.desde_id(h).tipo for h in _ids(clase)}
    tipos = {"C" if t in ("C", "Cv") else t for t in tipos}
    return not (del_verdadero & tipos)


def correr_red(filas: pd.DataFrame, umbrales: Umbrales, *, contexto: ContextoBateria | None = None,
               ida_y_vuelta: bool = True, tiempos: dict | None = None) -> pd.DataFrame:
    """Una red sintética por orquestacion.evaluar_red; una fila por estación-año (ESQUEMA_RESULTADOS) con
    reloj confirmado, veredicto, motivo, marcas y la traza mínima para §8.F (líneas que excluyeron, de
    apoyo y T-P). Los extractos se fabrican en memoria en cada pasada de la fábrica (no se guardan:
    memoria acotada); la verdad de cada año se calcula en la primera pasada, con la tabla del caso aún
    en la caché de sintetico. ``ida_y_vuelta`` comprueba la política en memoria con el adaptador fijado.
    ``tiempos`` (si se da) recibe los segundos de preparación, de evaluar_red y de la ida y vuelta."""
    reloj = time.perf_counter()
    filas = filas.reset_index(drop=True)
    if tuple(filas.columns) != COLUMNAS_BATERIA:
        raise ValueError("las filas no tienen las columnas de COLUMNAS_BATERIA")
    if filas["red"].nunique() != 1:
        raise ValueError("correr_red recibe las filas de una sola red")
    if filas["caso"].duplicated().any():
        raise ValueError("casos repetidos en la red")
    ctx = contexto if contexto is not None else contexto_bateria(con_adaptador=ida_y_vuelta)
    if ida_y_vuelta and ctx.adaptador is None:
        raise ValueError("la ida y vuelta necesita el adaptador fijado en el contexto")
    casos = [sintetico.caso_de_fila(f) for f in filas.to_dict("records")]
    con_e6 = bool((filas["bloque"] == BLOQUE_E6).any())                      # BAT-10
    lineas = orquestacion.LINEAS_ACTIVAS_C0 | ({Linea.E6} if con_e6 else frozenset())
    opciones = orquestacion.OpcionesCorrida(lineas_activas=frozenset(lineas), conservar_etiquetas=True)
    serie = sintetico.serie_era5_de_casos(casos)
    infos = _infos(casos, serie, umbrales, ctx)
    con_isd = set(filas.loc[filas["bloque"] == BLOQUE_E6, "caso"])
    verdades: dict[str, dict[int, str]] = {}

    def fabrica() -> Iterator[orquestacion.EntradaEstacion]:
        for caso in casos:
            extracto, meses = sintetico.entrada_en_memoria(caso)
            if caso.codigo not in verdades:
                verdades[caso.codigo] = _verdad_por_anio(caso, extracto)
            isd = sintetico.isd_sintetico(caso) if caso.codigo in con_isd else None
            yield orquestacion.EntradaEstacion(infos[caso.codigo], extracto, meses, isd=isd)

    preparacion = time.perf_counter() - reloj
    try:
        r = orquestacion.evaluar_red(fabrica, serie, ctx.tablas, umbrales, opciones, huellas=_huellas(umbrales))
        evaluacion = time.perf_counter() - reloj - preparacion
        estado_ida = {}
        for caso in casos:
            if not ida_y_vuelta:
                continue
            if r.politica is None:
                estado_ida[caso.codigo] = (SIN_POLITICA, 0)
                continue
            fallas = sintetico.comprobar_ida_y_vuelta(r.politica, [caso], ctx.adaptador)
            estado_ida[caso.codigo] = (IDA_Y_VUELTA_FALLA if fallas else IDA_Y_VUELTA_OK, len(fallas))
    finally:
        sintetico.vaciar_caches()
    salida = _filas_de_resultados(filas, casos, r, verdades, estado_ida)
    if tiempos is not None:
        total = time.perf_counter() - reloj
        tiempos.update({"preparacion": preparacion, "evaluar_red": evaluacion,
                        "ida_y_vuelta": total - preparacion - evaluacion, "total": total,
                        "estaciones": len(casos), "estacion_anios": int(len(salida))})
    return salida


def _filas_de_resultados(filas: pd.DataFrame, casos, r: orquestacion.ResultadoRed, verdades, estado_ida
                         ) -> pd.DataFrame:
    por_caso = {f["caso"]: f for f in filas.to_dict("records")}
    del_verdadero = {c.codigo: _clases_del_verdadero(c) for c in casos}
    salida = []
    for d in sorted(r.decisiones, key=lambda d: (d.codigo, d.anio)):
        f = por_caso[d.codigo]
        verdad = verdades.get(d.codigo, {}).get(int(d.anio), "")
        miembros_verdad = _ids(verdad)
        excluyen = set()
        for clase in d.clases:
            if _ids(clase) & miembros_verdad:
                excluyen |= {str(x) for x in d.excluidas.get(clase, ())}
        res = r.resultados_rachas.get(d.codigo)
        estacion = r.estaciones.get(d.codigo, {})
        ida, n_fallas = estado_ida.get(d.codigo, (pd.NA, 0))
        confirmado = d.veredicto == Veredicto.CONFIRMADO
        prefijo = f"{int(d.anio):04d}-"
        salida.append({
            "red": f["red"], "caso": d.codigo, "bloque": f["bloque"], "celda": f["celda"],
            "reloj_verdadero": f["reloj_verdadero"], "tipo": f["tipo"], "escenario": f["escenario"],
            "territorio": f["territorio"], "perturbacion": f["perturbacion"],
            "valor_perturbacion": f["valor_perturbacion"], "replica": f["replica"], "anio": int(d.anio),
            "veredicto": str(d.veredicto), "motivo": None if d.motivo is None else str(d.motivo),
            "clase_confirmada": d.clase_confirmada if confirmado else None,
            "verdad": verdad,
            "correcta": False,             # es_confirmacion_correcta, abajo (BAT-6)
            "erronea": False,
            "cruce": bool(confirmado and _cruza(d.clase_confirmada, del_verdadero[d.codigo])),
            "clase_paso_9": d.clase_confirmada,
            "erronea_paso_9": False,
            "excluyen_verdad": _lista(sorted(excluyen)),
            "lineas_apoyo": _lista(d.lineas_apoyo),
            "guarda_tp": d.guardas.get(str(Linea.TP)),
            "n_partes_discordantes": len(d.partes_discordantes),
            "meses_con_regla": sum(1 for m in r.meses_con_regla.get(d.codigo, {}) if str(m).startswith(prefijo)),
            "reglas_vencidas": bool(d.reglas_vencidas),
            "modo_e3t": None if d.modo_e3t is None else str(d.modo_e3t),
            "media_horaria": bool(estacion.get("marcas", {}).get("posible_media_horaria", False)),
            "inestable": bool(res.inestable) if res is not None else False,
            "cambios": ";".join(f"{a}-{b}" for a, b in (res.cambios if res is not None else ())),
            "ida_y_vuelta": ida, "fallas_ida_y_vuelta": int(n_fallas),
            "a4_restringe": bool(r.consecuencias.a4_restringe), "a5_alto": bool(r.consecuencias.a5_alto),
        })
    if not salida:
        return tabla_vacia(ESQUEMA_RESULTADOS)
    tabla = pd.DataFrame(salida, columns=list(ESQUEMA_RESULTADOS)).astype(ESQUEMA_RESULTADOS)
    tabla["correcta"] = [es_confirmacion_correcta(fila) for _, fila in tabla.iterrows()]
    tabla["erronea"] = [es_confirmacion_erronea(fila) for _, fila in tabla.iterrows()]
    paso_9 = tabla.assign(veredicto=str(Veredicto.CONFIRMADO), clase_confirmada=tabla["clase_paso_9"])
    tabla["erronea_paso_9"] = [bool(pd.notna(c)) and es_confirmacion_erronea(fila)
                               for c, (_, fila) in zip(tabla["clase_paso_9"], paso_9.iterrows())]
    tabla = tabla.astype(ESQUEMA_RESULTADOS)
    validar_esquema(tabla, ESQUEMA_RESULTADOS, nombre="resultados de la batería")
    return tabla


def correr_bateria(tabla: pd.DataFrame, umbrales: Umbrales, *, avance: Callable[[int, int], None] | None = None,
                   contexto: ContextoBateria | None = None, tiempos: dict | None = None,
                   correr: Callable[..., pd.DataFrame] | None = None) -> tuple[pd.DataFrame, float]:
    """(resultados por estación-año, horas medidas con el reloj de pared, MEDIDA_TIEMPO). Recorre las redes
    en orden, una a la vez y en un solo proceso. ``avance(estaciones hechas, total)`` después de cada red;
    ``tiempos`` (si se da) recibe los segundos de reloj y de CPU, por red y en total, la carga del sistema
    al empezar y al terminar y la memoria pico del proceso (BAT-13); ``correr`` reemplaza a correr_red
    (pruebas)."""
    correr = correr or correr_red
    ctx = contexto
    if ctx is None and correr is correr_red:
        ctx = contexto_bateria()
    carga_inicio = _carga_1min()
    inicio, inicio_cpu = time.perf_counter(), time.process_time()
    partes, hechas, total = [], 0, len(tabla)
    por_red, cpu_por_red, detalle = {}, {}, {}
    for red, filas in redes(tabla):
        t, t_cpu = time.perf_counter(), time.process_time()
        if correr is correr_red:
            detalle[red] = {}
            partes.append(correr(filas, umbrales, contexto=ctx, tiempos=detalle[red]))
        else:
            partes.append(correr(filas, umbrales, contexto=ctx))
        por_red[red] = time.perf_counter() - t
        cpu_por_red[red] = time.process_time() - t_cpu
        hechas += len(filas)
        if avance is not None:
            avance(hechas, total)
    segundos, segundos_cpu = time.perf_counter() - inicio, time.process_time() - inicio_cpu
    if tiempos is not None:
        tiempos.update({"segundos": segundos, "segundos_cpu": segundos_cpu, "redes": por_red,
                        "cpu_por_red": cpu_por_red, "detalle_por_red": detalle, "estaciones": total,
                        "estacion_anios": int(sum(len(p) for p in partes)), "carga_1min_inicio": carga_inicio,
                        "carga_1min_fin": _carga_1min(), "rss_pico_mib": _rss_pico_mib()})
    partes = [p for p in partes if len(p)]
    resultados = (pd.concat(partes, ignore_index=True).astype(ESQUEMA_RESULTADOS) if partes
                  else tabla_vacia(ESQUEMA_RESULTADOS))
    return resultados, segundos / SEGUNDOS_POR_HORA


def _carga_1min() -> float | None:
    """Carga media del sistema en el último minuto (None si el sistema no la da)."""
    try:
        return float(os.getloadavg()[0])
    except (OSError, AttributeError):
        return None


def _rss_pico_mib() -> float:
    """Memoria residente pico del proceso, en MiB (ru_maxrss viene en bytes en macOS y en KiB en Linux)."""
    pico = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    kib = pico / _BYTES_POR_KIB if platform.system() == "Darwin" else pico
    return kib / _BYTES_POR_KIB


def _resultados_bytes(resultados: pd.DataFrame) -> bytes:
    """resultados_bateria.parquet: ESQUEMA_RESULTADOS ordenado por caso y año (bytes deterministas con el
    pyarrow fijado; es también la salida de cada iteración de §8.F)."""
    validar_esquema(resultados, ESQUEMA_RESULTADOS, nombre="resultados de la batería")
    orden = resultados[list(ESQUEMA_RESULTADOS)].sort_values(["caso", "anio"], kind="mergesort")
    return _parquet_bytes(orden.reset_index(drop=True))


def huella_resultados(resultados: pd.DataFrame) -> str:
    """sha256 de la salida de la batería: la de resultados_bateria.parquet (y de resultados_bateria_iterNN.parquet)
    tal como la escriben ``escribir_salidas`` y ``ajustar_umbrales``. Es la «salida» que registra §8.F."""
    return entorno.sha256_bytes(_resultados_bytes(resultados))


# ---------------------------------------------------------------------------------------------
# Tiempo (§8.D, «Tiempo»)
# ---------------------------------------------------------------------------------------------
def replicas_por_tiempo(horas_medidas: float, umbrales: Umbrales) -> int | None:
    """None si cabe en 48 h (BAT_HORAS_MAX); 5 (para D2 y D3) si no (BAT-13)."""
    if not math.isfinite(float(horas_medidas)) or horas_medidas < 0:
        raise ValueError(f"horas medidas inválidas: {horas_medidas!r}")
    return None if horas_medidas <= umbrales.f("BAT_HORAS_MAX") else _c("BATERIA_REPLICAS_REDUCIDAS")


def proyectar_horas(segundos_medidos: float, estacion_anios_medidos: int, tabla: pd.DataFrame) -> float:
    """Horas de la batería completa, proporcionales a los estación-años (cada estación cubre 2008-2026)."""
    if estacion_anios_medidos <= 0:
        raise ValueError("sin estación-años medidos")
    desde, hasta = _c("BATERIA_ANIOS")
    total = len(tabla) * (hasta - desde + 1)
    return float(segundos_medidos) / estacion_anios_medidos * total / SEGUNDOS_POR_HORA


def tiempo_bateria(horas: float, tabla: pd.DataFrame, umbrales: Umbrales, *, tiempos: Mapping | None = None,
                   proyectadas: bool = False, previas: Sequence[Mapping] = ()) -> dict:
    """tiempo_bateria.json: horas medidas con MEDIDA_TIEMPO (o proyectadas), tope y la reducción que
    corresponde; además, si ``tiempos`` las trae (correr_bateria), las horas de CPU y la reducción que daría
    esa medida, la carga del sistema y la memoria pico (BAT-13). ``previas``: mediciones anteriores de la
    misma corrida (la de la tabla completa, si hubo reducción), ya en este formato."""
    t = tiempos or {}
    reduccion = replicas_por_tiempo(horas, umbrales)
    horas_cpu = None if t.get("segundos_cpu") is None else float(t["segundos_cpu"]) / SEGUNDOS_POR_HORA
    reduccion_cpu = None if horas_cpu is None else replicas_por_tiempo(horas_cpu, umbrales)
    d2_d3 = tabla.loc[tabla["bloque"].isin([BLOQUE_PERTURBACIONES, BLOQUE_E6]), "replica"]
    return {"horas": float(horas), "medida": MEDIDA_TIEMPO, "proyectadas": bool(proyectadas),
            "tope_horas": umbrales.f("BAT_HORAS_MAX"), "estaciones": int(len(tabla)),
            "replicas_d2_d3": int(d2_d3.max()) if len(d2_d3) else None, "reduce_d2_d3_a": reduccion,
            "horas_cpu": horas_cpu, "reduce_d2_d3_a_por_cpu": reduccion_cpu,
            "reduccion_depende_de_la_medida": horas_cpu is not None and reduccion != reduccion_cpu,
            "carga_1min": {"inicio": t.get("carga_1min_inicio"), "fin": t.get("carga_1min_fin")},
            "rss_pico_mib": t.get("rss_pico_mib"),
            "segundos_por_red": dict(t.get("redes", {})), "segundos_cpu_por_red": dict(t.get("cpu_por_red", {})),
            "detalle_por_red": dict(t.get("detalle_por_red", {})),
            "estacion_anios": t.get("estacion_anios"), "mediciones_previas": [dict(p) for p in previas]}


# ---------------------------------------------------------------------------------------------
# Criterios de §8.D
# ---------------------------------------------------------------------------------------------
@dataclass
class CriteriosBateria:
    por_celda: pd.DataFrame
    erroneas: int
    sensibilidad: dict
    pasa: bool
    motivos: list[str]
    criterios: dict = field(default_factory=dict)     # nombre → {"pasa", …} (BAT-12)


def _factores(resultados: pd.DataFrame, tabla: pd.DataFrame) -> pd.DataFrame:
    """Resultados con lat y la verdad del reloj (tabla) por caso; comprueba que los casos sean de la tabla."""
    extra = tabla[["caso", "lat", "fuera_de_P"]].drop_duplicates("caso")
    unido = resultados.merge(extra, on="caso", how="left", validate="many_to_one")
    if unido["lat"].isna().any():
        raise ValueError("resultados de casos que no están en la tabla de la batería")
    return unido


def _en(df: pd.DataFrame, condiciones: Mapping[str, Sequence]) -> pd.Series:
    m = pd.Series(True, index=df.index)
    for columna, valores in condiciones.items():
        m &= df[columna].isin(list(valores))
    return m


def _fraccion(numerador: int, denominador: int) -> float | None:
    return None if denominador == 0 else numerador / denominador


def _anio_de_cambio(reloj: str) -> int | None:
    """Año del cambio de reloj de un caso con un solo reloj y dos tramos (el de 2018 de §8.D)."""
    relojes = sintetico.relojes_desde_texto(reloj)
    if len(relojes) != 1 or len(relojes[0].tramos) < 2:
        return None
    anios = {d.year for d, _ in relojes[0].tramos[1:]}
    if len(anios) != 1:
        raise ValueError(f"un reloj con cambios en varios años: {reloj!r}")
    return anios.pop()


def _cambios_detectados(filas: pd.DataFrame) -> list[tuple[int, int]]:
    """Los cambios (a, b) de decision.rachas de una estación («a-b;…» en la columna «cambios»)."""
    pares = set()
    for texto in set(filas["cambios"].dropna()):
        for par in filter(None, str(texto).split(";")):
            a, b = (int(x) for x in par.split("-"))
            pares.add((a, b))
    return sorted(pares)


def _cambio_ubicado(filas: pd.DataFrame, anio: int) -> bool:
    """BAT-8 «sin error de ubicación» (filas de una estación): el año del cambio no se confirma, ningún año
    es erróneo y cada cambio detectado (a, b) contiene a ``anio`` (a < anio < b) sin años confirmados dentro.
    Sin cambio detectado, True (se cuenta aparte en el criterio)."""
    confirmado = filas["veredicto"].eq(str(Veredicto.CONFIRMADO))
    if (confirmado & filas["anio"].eq(anio)).any() or filas["erronea"].any():
        return False
    confirmados = {int(a) for a in filas.loc[confirmado, "anio"]}
    return all(a < anio < b and not any(a < y < b for y in confirmados) for a, b in _cambios_detectados(filas))


def _cambio_ubicado_estricto(filas: pd.DataFrame, anio: int) -> bool:
    """La lectura estricta anterior de BAT-8, que sólo se informa: además, ``anio`` es el único año con datos
    entre las dos rachas de cada cambio detectado (los demás años del hueco, sin datos)."""
    if not _cambio_ubicado(filas, anio):
        return False
    con_datos = {int(a) for a in filas.loc[filas["veredicto"] != str(Veredicto.SIN_DATOS), "anio"]}
    return all(not any(y in con_datos for y in range(a + 1, b) if y != anio) for a, b in _cambios_detectados(filas))


def _indecidible(df: pd.DataFrame) -> pd.Series:
    """BAT-7, al pie de la letra (v1.0.4, E4-1): tipo e, Pascua y Juan Fernández, en D1 y D2. El tipo f ya no
    entra."""
    return (df["bloque"].isin([BLOQUE_NUCLEO, BLOQUE_PERTURBACIONES])
            & (df["tipo"].isin(list(TIPOS_INDECIDIBLES)) | df["territorio"].isin(list(TERRITORIOS_INDECIDIBLES))))


def _indecidible_estrecho(df: pd.DataFrame) -> pd.Series:
    """Diagnóstico de BAT-7 con §6: F(0) o F(−3) sin E6 donde nada más los separa (sólo Ts, Juan Fernández)
    y el UTC con calendario propio de Pascua. Usa la misma lista de tipos que BAT-7 (sin el tipo f)."""
    sin_e6 = df["bloque"].isin([BLOQUE_NUCLEO, BLOQUE_PERTURBACIONES])
    f0_f3 = df["reloj_verdadero"].isin(["F(0)", "F(-3)"])
    jf = df["territorio"] == str(Territorio.JUAN_FERNANDEZ_DESVENTURADAS)
    return sin_e6 & ((f0_f3 & (df["tipo"].isin(list(TIPOS_INDECIDIBLES)) | jf))
                     | (df["reloj_verdadero"] == sintetico.PASCUA_PROPIO))


def _semantica_media_hora(df: pd.DataFrame) -> pd.Series:
    return ((df["perturbacion"] == PERTURBACION_SEMANTICA)
            & np.isclose(df["valor_perturbacion"].abs().to_numpy(dtype=float, na_value=np.nan),
                         _c("BATERIA_SEMANTICA_H")))


def _sesgo_referencia(df: pd.DataFrame) -> pd.Series:
    """Sesgo térmico de la referencia de la red de cada fila (0 fuera de las redes con sesgo)."""
    return df["valor_perturbacion"].where(df["perturbacion"] == PERTURBACION_SESGO, 0.0).astype("float64")


def _celdas_correcta(df: pd.DataFrame) -> pd.Series:
    """BAT-5, al pie de la letra: tipos a y b, completo o 30 % faltante, |sesgo de la referencia| ≤ 1 h, en
    cualquier bloque y con cualquier otra perturbación, sin Pascua ni Juan Fernández y con la verdad del
    año no vacía."""
    return (df["tipo"].isin(list(TIPOS_CON_QFE_Y_RR)) & df["escenario"].isin(list(ESCENARIOS_CORRECTA))
            & (_sesgo_referencia(df).abs() <= _c("BATERIA_SESGO_CORRECTA"))
            & ~df["territorio"].isin(list(TERRITORIOS_INDECIDIBLES)) & (df["verdad"].fillna("") != ""))


def _celdas_correcta_estrecha(df: pd.DataFrame) -> pd.Series:
    """BAT-5, la lectura estrecha sin acotar la latitud (se informa): además de la literal, el único factor
    distinto del núcleo es el sesgo de la referencia (D1 sin perturbación y D2 «sesgo_termico_referencia»)."""
    nucleo = (df["bloque"] == BLOQUE_NUCLEO) & (df["perturbacion"] == SIN_PERTURBACION)
    sesgo = (df["bloque"] == BLOQUE_PERTURBACIONES) & (df["perturbacion"] == PERTURBACION_SESGO)
    return _celdas_correcta(df) & (nucleo | sesgo)


def _celdas_correcta_estrecha_50(df: pd.DataFrame) -> pd.Series:
    """BAT-5 con la Enmienda 3, la lectura que decide: la estrecha a ≤ 50° S (|lat| ≤ BATERIA_CORRECTA_LAT_S,
    la frase de §8.D; E3-6)."""
    return _celdas_correcta_estrecha(df) & (df["lat"].abs() <= _c("BATERIA_CORRECTA_LAT_S"))


def _id_de_reloj(reloj: str) -> str:
    """Id de tipos de un reloj de un solo tramo de bateria_v1.csv («C(America/Santiago)» → «C(Santiago)»)."""
    relojes = sintetico.relojes_desde_texto(reloj)
    if len(relojes) != 1 or len(relojes[0].tramos) != 1:
        raise ValueError(f"se espera un reloj de un solo tramo: {reloj!r}")
    spec = relojes[0].tramos[0][1]
    if spec == sintetico.PASCUA_PROPIO:
        return Hipotesis("F", 0, None).id
    if spec.startswith("F("):
        return Hipotesis("F", int(spec[2:-1]), None).id
    tipo = spec.split("(")[0]
    return Hipotesis(tipo, None, spec[len(tipo) + 1:-1]).id


def criterios_por_celda(resultados: pd.DataFrame, tabla: pd.DataFrame, umbrales: Umbrales) -> CriteriosBateria:
    """Los criterios de §8.D (BAT-2 a BAT-12) y las pérdidas por celda. ``pasa`` exige todos; ``motivos``
    nombra los que no se cumplen. ``criterios`` da el detalle de cada uno (también su n)."""
    validar_esquema(resultados, ESQUEMA_RESULTADOS, nombre="resultados de la batería")
    U = umbrales
    df = _factores(resultados, tabla)
    confirmado = df["veredicto"] == str(Veredicto.CONFIRMADO)
    con_verdadero = pd.Series([_con_el_verdadero(*x) for x in zip(df["veredicto"], df["tipo"], df["verdad"],
                                                                  df["clase_confirmada"])],
                              index=df.index, dtype=bool)
    media_hora = _semantica_media_hora(df)
    correcta = con_verdadero & (~media_hora | df["media_horaria"])
    if (correcta != df["correcta"]).any():
        raise ValueError("la columna «correcta» no sigue es_confirmacion_correcta (BAT-6) en "
                         f"{int((correcta != df['correcta']).sum())} estación-años")
    df["_confirmado"] = confirmado
    df["_falsa_discrepante"] = ((df["veredicto"] == str(Veredicto.DISCREPANTE)) & (df["verdad"].fillna("") != "")
                                & (df["tipo"] != TIPO_G))
    df["_indecidible"] = _indecidible(df) & confirmado
    df["_media_hora"] = media_hora & con_verdadero        # confirmaciones del reloj entero verdadero (BAT-6)
    df["_con_marca"] = df["_media_hora"] & df["media_horaria"]
    df["_ida_falla"] = df["ida_y_vuelta"].fillna("") == IDA_Y_VUELTA_FALLA

    orden = {c: i for i, c in enumerate(celdas(tabla))}
    grupos = df.groupby("celda", sort=False)
    estaciones = df.drop_duplicates("caso")
    inestables = estaciones.groupby("celda", sort=False)["inestable"].agg(["size", "sum"])
    ida = estaciones.groupby("celda", sort=False)["_ida_falla"].sum()
    factores = tabla.drop_duplicates("celda").set_index("celda")
    por_celda = pd.DataFrame({
        "n_estacion_anios": grupos.size(), "confirmados": grupos["_confirmado"].sum(),
        "correctos": grupos["correcta"].sum(), "erroneas": grupos["erronea"].sum(), "cruces": grupos["cruce"].sum(),
        "falsamente_discrepantes": grupos["_falsa_discrepante"].sum(),
        "indecidibles_confirmados": grupos["_indecidible"].sum(),
        "media_hora_confirmadas": grupos["_media_hora"].sum(), "media_hora_con_marca": grupos["_con_marca"].sum(),
    })
    por_celda["n_estaciones"] = inestables["size"]
    por_celda["estaciones_inestables"] = inestables["sum"]
    por_celda["estaciones_ida_y_vuelta_falla"] = ida
    por_celda = por_celda.reset_index()
    por_celda = por_celda.join(factores[["bloque", "reloj_verdadero", "tipo", "escenario", "territorio",
                                         "perturbacion", "valor_perturbacion"]], on="celda")
    por_celda["sensibilidad"] = por_celda["correctos"] / por_celda["n_estacion_anios"]
    por_celda["tasa_falsamente_discrepantes"] = por_celda["falsamente_discrepantes"] / por_celda["n_estacion_anios"]
    por_celda["perdida_inestabilidad"] = por_celda["estaciones_inestables"] / por_celda["n_estaciones"]
    por_celda["_orden"] = por_celda["celda"].map(orden)
    por_celda = por_celda.sort_values("_orden").drop(columns="_orden").reset_index(drop=True)
    enteras = ["n_estacion_anios", "confirmados", "correctos", "erroneas", "cruces", "falsamente_discrepantes",
               "indecidibles_confirmados", "media_hora_confirmadas", "media_hora_con_marca", "n_estaciones",
               "estaciones_inestables", "estaciones_ida_y_vuelta_falla"]
    por_celda[enteras] = por_celda[enteras].astype("int64")

    criterios: dict[str, dict] = {}
    motivos: list[str] = []

    def registrar(nombre: str, pasa: bool | None, motivo: str, **detalle) -> None:
        criterios[nombre] = {"pasa": pasa, **detalle}
        if pasa is not True:
            motivos.append(motivo)

    # 1. Cero confirmaciones erróneas en cada celda (BAT-2).
    con_errores = por_celda.loc[por_celda["erroneas"] > 0, "celda"].tolist()
    erroneas = int(df["erronea"].sum())
    estaciones_ok = set(estaciones.loc[~estaciones["_ida_falla"], "caso"])
    fuera_de_regla = int((df["erronea"] & df["caso"].isin(estaciones_ok)).sum())
    protegidas = df["erronea_paso_9"] & ~confirmado
    registrar("cero_erroneas", erroneas == 0,
              f"{erroneas} confirmaciones erróneas en {len(con_errores)} celdas: {con_errores[:EJEMPLOS_EN_MENSAJES]}",
              erroneas=erroneas, celdas=con_errores, erroneas_solo_fuera_de_la_regla=fuera_de_regla,
              erroneas_en_el_paso_9_que_5_3_deja_sin_confirmar=int(protegidas.sum()),
              celdas_protegidas_por_5_3=sorted(set(df.loc[protegidas, "celda"]))[:EJEMPLOS_EN_MENSAJES])

    # 2. Semánticas de ±0,5 h (BAT-6).
    n_mh, n_marca = int(df["_media_hora"].sum()), int(df["_con_marca"].sum())
    frac_mh = _fraccion(n_marca, n_mh)
    pasa_mh = frac_mh is None or frac_mh >= U.frac("BAT_MEDIA_HORARIA_PCT")
    registrar("semanticas_media_hora", pasa_mh,
              f"semánticas de ±0,5 h: {n_marca} de {n_mh} confirmaciones con la marca «posible media horaria»",
              confirmaciones=n_mh, con_marca=n_marca, fraccion=frac_mh, minimo=U.frac("BAT_MEDIA_HORARIA_PCT"))

    # 3. Sensibilidad por reloj en las celdas de referencia (BAT-4) y razón civil.
    ref = _en(df, CELDAS_REFERENCIA)
    sensibilidad: dict = {}
    for reloj in RELOJES_REFERENCIA:
        m = ref & (df["reloj_verdadero"] == reloj)
        n, ok = int(m.sum()), int((m & df["correcta"]).sum())
        sensibilidad[_id_de_reloj(reloj)] = {"n": n, "correctos": ok, "sensibilidad": _fraccion(ok, n)}
    fijo = sensibilidad[_id_de_reloj(RELOJ_FIJO_DE_LA_RAZON)]["sensibilidad"]
    civil = sensibilidad[_id_de_reloj(RELOJ_CIVIL_DE_LA_RAZON)]["sensibilidad"]
    razon = None if fijo in (None, 0) or civil is None else civil / fijo
    sensibilidad["razon_civil"] = razon
    bajas = [h for h, s in sensibilidad.items() if h != "razon_civil"
             and (s["sensibilidad"] is None or s["sensibilidad"] < U.f("BAT_SENSIBILIDAD"))]
    registrar("sensibilidad_por_reloj", not bajas,
              f"sensibilidad < {U.f('BAT_SENSIBILIDAD')} (o sin estación-años de referencia) en {bajas}",
              minimo=U.f("BAT_SENSIBILIDAD"), relojes=bajas)
    pasa_razon = civil is not None and fijo is not None and civil >= U.f("BAT_RAZON_CIVIL") * fijo
    registrar("razon_civil", pasa_razon,
              f"sensibilidad civil {civil} < {U.f('BAT_RAZON_CIVIL')} × la de F(0) ({fijo})",
              razon=razon, minimo=U.f("BAT_RAZON_CIVIL"))

    # 4. Confirmación correcta ≥ 90 % (BAT-5, Enmienda 3): decide la estrecha a ≤ 50° S, por estación-año; la
    # literal y la estrecha sin acotar la latitud se informan al lado.
    def correcta_en(m: pd.Series) -> dict:
        n, ok = int(m.sum()), int((m & df["correcta"]).sum())
        frac = _fraccion(ok, n)
        return {"n": n, "correctos": ok, "fraccion": frac, "casos": int(df.loc[m, "caso"].nunique()),
                "celdas": int(df.loc[m, "celda"].nunique()),
                "pasa": frac is not None and frac >= U.frac("BAT_CORRECTA_PCT")}
    decide = correcta_en(_celdas_correcta_estrecha_50(df))
    literal, estrecha = correcta_en(_celdas_correcta(df)), correcta_en(_celdas_correcta_estrecha(df))
    registrar("confirmacion_correcta", decide["pasa"],
              f"confirmación correcta en {decide['correctos']} de {decide['n']} estación-años de la lectura "
              f"estrecha a ≤ {_c('BATERIA_CORRECTA_LAT_S')}° S (mínimo {U.frac('BAT_CORRECTA_PCT')})",
              **{k: v for k, v in decide.items() if k != "pasa"}, minimo=U.frac("BAT_CORRECTA_PCT"),
              unidad="estacion_anios", lectura="estrecha_50S", lectura_literal=literal, lectura_estrecha=estrecha)

    # 5. Sin cruces fijo/civil (BAT-8).
    cruces = int(df["cruce"].sum())
    registrar("sin_cruces", cruces == 0, f"{cruces} confirmaciones cruzadas entre fijo y civil", cruces=cruces)

    # 6. El cambio de 2018 ubicado en 2018 (BAT-8, «sin error de ubicación»; la estricta se informa).
    mal, estricta, sin_detectar, n_cambio = [], [], [], 0
    for caso, filas in df.groupby("caso", sort=True):
        anio = _anio_de_cambio(str(filas["reloj_verdadero"].iloc[0]))
        if anio is None or str(filas["tipo"].iloc[0]) == TIPO_G:
            continue
        n_cambio += 1
        if not _cambio_ubicado_estricto(filas, anio):
            estricta.append(str(caso))
        if not _cambio_ubicado(filas, anio):
            mal.append(str(caso))
        elif not _cambios_detectados(filas):
            sin_detectar.append(str(caso))
    registrar("cambio_ubicado", not mal,
              f"cambio de reloj mal ubicado en {len(mal)} estaciones: {mal[:EJEMPLOS_EN_MENSAJES]}",
              estaciones=n_cambio, mal_ubicadas=mal, lectura="sin_error_de_ubicacion",
              mal_ubicadas_lectura_estricta=estricta, sin_cambio_detectado=len(sin_detectar),
              sin_cambio_detectado_casos=sin_detectar[:EJEMPLOS_EN_MENSAJES])

    # 7. Lo indecidible (tipo e, Pascua y Juan Fernández) queda sin confirmar (BAT-7, v1.0.4). El tipo f puede
    # confirmarse: se informa, y sus erróneas ya cuentan en el criterio 1.
    n_ind = int(df["_indecidible"].sum())
    estrecho = int((_indecidible_estrecho(df) & confirmado).sum())
    celdas_ind = por_celda.loc[por_celda["indecidibles_confirmados"] > 0, "celda"].tolist()
    seis = df["bloque"].isin([BLOQUE_NUCLEO, BLOQUE_PERTURBACIONES]) & (df["tipo"] == TIPO_SEIS_HORAS)
    tipo_f = {"estacion_anios": int(seis.sum()), "confirmados": int((seis & confirmado).sum()),
              "correctos": int((seis & df["correcta"]).sum()), "erroneas": int((seis & df["erronea"]).sum()),
              "celdas_con_confirmados": sorted(set(df.loc[seis & confirmado, "celda"]))[:EJEMPLOS_EN_MENSAJES]}
    registrar("indecidible_sin_confirmar", n_ind == 0,
              f"{n_ind} estación-años indecidibles confirmados en {len(celdas_ind)} celdas: "
              f"{celdas_ind[:EJEMPLOS_EN_MENSAJES]}",
              confirmados=n_ind, celdas=celdas_ind, indecidible_estrecho=estrecho,
              tipos=list(TIPOS_INDECIDIBLES), tipo_f=tipo_f)

    # 8. Ida y vuelta en cada estación (BAT-9).
    fallan = sorted(estaciones.loc[estaciones["_ida_falla"], "caso"].tolist())
    sin_politica = sorted(estaciones.loc[estaciones["ida_y_vuelta"].fillna("") == SIN_POLITICA, "caso"].tolist())
    sin_comprobar = int(estaciones["ida_y_vuelta"].isna().sum())
    registrar("ida_y_vuelta", not fallan and not sin_politica and not sin_comprobar,
              f"ida y vuelta: {len(fallan)} estaciones fallan, {len(sin_politica)} sin política (A5) y "
              f"{sin_comprobar} sin comprobar", fallan=fallan[:EJEMPLOS_EN_MENSAJES], sin_politica=len(sin_politica),
              sin_comprobar=sin_comprobar)

    pasa = all(c["pasa"] is True for c in criterios.values())
    return CriteriosBateria(por_celda=por_celda, erroneas=erroneas, sensibilidad=sensibilidad, pasa=pasa,
                            motivos=motivos, criterios=criterios)


def lineas_responsables(resultados: pd.DataFrame) -> set[str]:
    """§8.F (BAT-3, acumulativa): las que excluyeron el verdadero; si estaba fuera de P, las de apoyo; en
    (g), además T-P."""
    return set(_responsables_por_linea(resultados))


def _responsables_de(fila: pd.Series) -> set[str]:
    """Las líneas responsables de una confirmación errónea, sumando los tres puntos de §8.F (BAT-3)."""
    if _ids(fila["verdad"]):
        lineas = set(_ids(fila["excluyen_verdad"]))
    else:
        lineas = set(_ids(fila["lineas_apoyo"]))
    if str(fila["tipo"]) == TIPO_G:
        lineas.add(str(Linea.TP))
    return lineas


def _responsables_por_linea(resultados: pd.DataFrame) -> dict[str, int]:
    """Línea → confirmaciones erróneas de las que es responsable; «» cuenta las que no tienen ninguna."""
    cuenta: dict[str, int] = {}
    for _, fila in resultados[resultados["erronea"]].iterrows():
        lineas = _responsables_de(fila)
        for linea in lineas or {""}:
            cuenta[linea] = cuenta.get(linea, 0) + 1
    if "" in cuenta:
        raise ErrorSinResponsable(f"{cuenta['']} confirmaciones erróneas sin línea responsable en la traza (BAT-3)")
    return dict(sorted(cuenta.items()))


class ErrorSinResponsable(ValueError):
    """Una confirmación errónea cuya traza no nombra ninguna línea: §8.F no tiene qué mover (C1 falla)."""


def criterios_a_json(criterios: CriteriosBateria) -> dict:
    """criterios_bateria.json (sin NaN)."""
    def limpio(v):
        if isinstance(v, float) and not math.isfinite(v):
            return None
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return limpio(float(v))
        if isinstance(v, (np.bool_,)):
            return bool(v)
        if v is pd.NA:
            return None
        if isinstance(v, dict):
            return {str(k): limpio(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [limpio(x) for x in v]
        return v
    por_celda = [limpio(f) for f in criterios.por_celda.to_dict("records")]
    return {"pasa": bool(criterios.pasa), "erroneas": int(criterios.erroneas), "motivos": list(criterios.motivos),
            "criterios": limpio(criterios.criterios), "sensibilidad": limpio(criterios.sensibilidad),
            "por_celda": por_celda}


# ---------------------------------------------------------------------------------------------
# §8.F
# ---------------------------------------------------------------------------------------------
@dataclass
class RegistroAjuste:
    iteraciones: list[dict]        # fecha UTC, motivo, umbral movido, salida de la batería (archivo y sha256)
    umbrales_finales: Umbrales | None
    c1_falla: bool
    motivo: str | None
    resultados: pd.DataFrame | None = None      # salida de la última corrida (para escribir_salidas)
    criterios: CriteriosBateria | None = None   # sus criterios de §8.D
    huellas: dict = field(default_factory=dict)  # {archivo: sha256}: registro_8F.jsonl y las salidas por iteración


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _escribir_registro(ruta: Path | None, iteraciones: Sequence[Mapping]) -> str | None:
    """registro_8F.jsonl, reescrito de forma atómica; devuelve su sha256 (None sin ruta)."""
    if ruta is None:
        return None
    lineas = b"".join(entorno.json_canonico(dict(i)) + b"\n" for i in iteraciones)
    return entorno.escribir_atomico(Path(ruta), lineas)


def _valor_json(v):
    return list(v) if isinstance(v, tuple) else v


def ajustar_umbrales(umbrales: Umbrales, correr: Callable[[Umbrales], pd.DataFrame], tabla: pd.DataFrame, *,
                     ruta_registro: Path | None = None, reloj: Callable[[], datetime] | None = None
                     ) -> RegistroAjuste:
    """Repite: correr → criterios → si hay erróneas, un paso conservador por línea responsable
    (umbrales.siguiente_ajuste) → correr toda la batería. Lista agotada o sensibilidades no cumplidas
    con cero errores → C1 falla. Nunca hacia lo menos conservador (BAT-14). ``umbrales`` debe traer los
    valores del Anexo B (ningún paso movido): la primera corrida es con ellos (§8.F).

    ``correr(U)`` corre la batería completa con los umbrales U. ``ruta_registro`` (registro_8F.jsonl) se
    reescribe de forma atómica después de cada iteración, y la salida de cada una queda junto a él en
    resultados_bateria_iterNN.parquet (su sha256 es ``salida_sha256``); ``RegistroAjuste.huellas`` trae las
    sha256 de todos esos archivos. Sin ``ruta_registro`` no se escribe nada y ``salida_sha256`` es
    ``huella_resultados``. ``reloj`` da la fecha UTC (pruebas)."""
    movidos_al_entrar = {i: p for i, p in umbrales.pasos.items() if p}
    if movidos_al_entrar:
        raise ValueError("§8.F: la primera corrida es con los valores del Anexo B; llegaron umbrales con pasos "
                         f"ya movidos: {movidos_al_entrar}")
    reloj = reloj or _ahora_utc
    carpeta = None if ruta_registro is None else Path(ruta_registro).parent
    U = umbrales
    iteraciones: list[dict] = []
    huellas: dict[str, str] = {}

    def registrar_iteraciones() -> None:
        sha = _escribir_registro(ruta_registro, iteraciones)
        if sha is not None:
            huellas[ARCHIVO_REGISTRO_8F] = sha

    def cerrar(umbrales_finales, c1_falla: bool, motivo, resultados, criterios) -> RegistroAjuste:
        registrar_iteraciones()
        return RegistroAjuste(iteraciones, umbrales_finales, c1_falla, motivo, resultados, criterios, dict(huellas))

    # Cada iteración mueve al menos un paso, así que el ciclo termina antes de agotar todas las listas.
    maximo = 1 + sum(len(U.ajustables[i]["lista_conservadora"]) for i in mod_umbrales.IDS_AJUSTABLES)
    for n in range(1, maximo + 1):
        resultados = correr(U)
        criterios = criterios_por_celda(resultados, tabla, U)
        datos = _resultados_bytes(resultados)
        archivo, salida_sha = None, entorno.sha256_bytes(datos)
        if carpeta is not None:
            archivo = PLANTILLA_SALIDA_ITERACION.format(n)
            salida_sha = entorno.escribir_atomico(carpeta / archivo, datos)
            huellas[archivo] = salida_sha
        registro = {"iteracion": n, "fecha_utc": reloj().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "umbrales_sha256": U.huella(), "pasos": {i: p for i, p in U.pasos.items() if p},
                    "salida_archivo": archivo, "salida_sha256": salida_sha, "estacion_anios": int(len(resultados)),
                    "erroneas": criterios.erroneas,
                    "erroneas_por_celda": {c: int(e) for c, e in zip(criterios.por_celda["celda"],
                                                                     criterios.por_celda["erroneas"]) if e},
                    "criterios": {k: v["pasa"] for k, v in criterios.criterios.items()},
                    "lineas_responsables": {}, "umbrales_movidos": [], "motivo": None, "fin": None}
        iteraciones.append(registro)
        if criterios.erroneas == 0:
            if criterios.pasa:
                registro.update(motivo="cero confirmaciones erróneas y todos los criterios de §8.D", fin="aprobado")
                return cerrar(U, False, None, resultados, criterios)
            motivo = "con cero confirmaciones erróneas no se cumplen: " + "; ".join(criterios.motivos)
            registro.update(motivo=motivo, fin="c1_falla")
            return cerrar(None, True, motivo, resultados, criterios)
        try:
            responsables = _responsables_por_linea(resultados)
        except ErrorSinResponsable as e:
            registro.update(motivo=str(e), fin="c1_falla")
            return cerrar(None, True, str(e), resultados, criterios)
        registro["lineas_responsables"] = responsables
        agotadas = [linea for linea in responsables if mod_umbrales.siguiente_ajuste(U, linea) is None]
        if agotadas:
            motivo = (f"{criterios.erroneas} confirmaciones erróneas; lista agotada (o línea sin filas en el "
                      f"Anexo B) en {agotadas}")
            registro.update(motivo=motivo, fin="c1_falla")
            return cerrar(None, True, motivo, resultados, criterios)
        movidos = []
        nuevo = U
        for linea in responsables:
            ident = mod_umbrales.siguiente_ajuste(nuevo, linea)
            antes = nuevo.a(ident)
            nuevo = nuevo.ajustado(ident)            # ErrorUmbrales si no fuera hacia lo conservador
            movidos.append({"linea": linea, "id": ident, "de": _valor_json(antes), "a": _valor_json(nuevo.a(ident)),
                            "paso": int(nuevo.pasos[ident])})
        if any(nuevo.pasos[i] < U.pasos[i] for i in mod_umbrales.IDS_AJUSTABLES):
            raise AssertionError("§8.F movió un umbral hacia atrás")
        registro.update(umbrales_movidos=movidos,
                        motivo=f"{criterios.erroneas} confirmaciones erróneas; un paso por línea responsable")
        registrar_iteraciones()
        U = nuevo
    raise AssertionError("§8.F no terminó: cada iteración debía mover un paso")


# ---------------------------------------------------------------------------------------------
# Salidas (§5.3 del diseño, punto 7)
# ---------------------------------------------------------------------------------------------
def carpeta_c1(rutas: entorno.Rutas) -> Path:
    """LOCAL/modelado_1km/verificacion_reloj_dmc/v1/c1 (R-32)."""
    return rutas.corridas / CARPETA_C1


def _parquet_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    return buf.getvalue()


def escribir_salidas(carpeta: Path, tabla: pd.DataFrame, resultados: pd.DataFrame, criterios: CriteriosBateria,
                     tiempo: Mapping, *, registro: RegistroAjuste | None = None) -> dict[str, str]:
    """bateria_v1.csv, resultados_bateria.parquet, criterios_bateria.json y tiempo_bateria.json. Devuelve
    {archivo: sha256} para el addendum. Con ``registro`` (el de ``ajustar_umbrales``, escrito en esta misma
    carpeta) suma registro_8F.jsonl y las salidas de cada iteración, después de comprobar sus sha256 en el
    disco, y exige que ``resultados`` sean los de la última iteración (misma sha256)."""
    carpeta = Path(carpeta)
    datos = _resultados_bytes(resultados)
    if registro is not None:
        ultima = registro.iteraciones[-1]["salida_sha256"] if registro.iteraciones else None
        if entorno.sha256_bytes(datos) != ultima:
            raise ValueError("los resultados no son la salida de la última iteración de §8.F")
        for archivo, sha in registro.huellas.items():
            ruta = carpeta / archivo
            if not ruta.is_file() or entorno.sha256_archivo(ruta) != sha:
                raise ValueError(f"{archivo}: el registro de §8.F no está en esta carpeta con su sha256")
    huellas = {
        ARCHIVO_TABLA: escribir_bateria(tabla, carpeta / ARCHIVO_TABLA),
        ARCHIVO_RESULTADOS: entorno.escribir_atomico(carpeta / ARCHIVO_RESULTADOS, datos),
        ARCHIVO_CRITERIOS: entorno.escribir_atomico(carpeta / ARCHIVO_CRITERIOS,
                                                    entorno.json_canonico(criterios_a_json(criterios))),
        ARCHIVO_TIEMPO: entorno.escribir_atomico(carpeta / ARCHIVO_TIEMPO, entorno.json_canonico(dict(tiempo))),
    }
    if registro is not None:
        huellas.update(registro.huellas)
    return huellas


@dataclass
class ResultadoBateriaC1:
    huellas: dict[str, str]        # {archivo: sha256} de la carpeta c1, para el addendum
    pasa: bool                     # §8.F sin fallar y todos los criterios de §8.D (BAT-12)
    registro: RegistroAjuste
    tiempo: dict                   # tiempo_bateria.json
    tabla: pd.DataFrame            # bateria_v1.csv (la reducida, si hubo reducción)


def bateria_c1(carpeta: Path, umbrales: Umbrales, *, contexto: ContextoBateria | None = None,
               avance: Callable[[int, int], None] | None = None,
               reloj: Callable[[], datetime] | None = None) -> ResultadoBateriaC1:
    """El camino único de ``--sintetico --bateria`` (§8.D «Tiempo» y §8.F, en este orden):
    1. corre la batería con los valores del Anexo B y mide su tiempo, antes de C1;
    2. si pasa del tope (replicas_por_tiempo), regenera la tabla con D2 y D3 a 5 réplicas y la vuelve a
       correr y a medir (las dos mediciones quedan en tiempo_bateria.json);
    3. esa corrida medida es la primera de §8.F (no se repite); ajustar_umbrales sigue desde ahí, con
       registro_8F.jsonl y las salidas por iteración en ``carpeta``;
    4. escribir_salidas con la última iteración y el registro.
    ``carpeta``: LOCAL/…/v1/c1 (``carpeta_c1``) o una temporal en las pruebas."""
    carpeta = Path(carpeta)
    ctx = contexto if contexto is not None else contexto_bateria()
    tabla = tabla_bateria()
    medido: dict = {}
    resultados, horas = correr_bateria(tabla, umbrales, avance=avance, contexto=ctx, tiempos=medido)
    tiempo = tiempo_bateria(horas, tabla, umbrales, tiempos=medido)
    if tiempo["reduce_d2_d3_a"] is not None:
        tabla = tabla_bateria(tiempo["reduce_d2_d3_a"])
        medido = {}
        resultados, horas = correr_bateria(tabla, umbrales, avance=avance, contexto=ctx, tiempos=medido)
        tiempo = tiempo_bateria(horas, tabla, umbrales, tiempos=medido, previas=[tiempo])
    primera = {umbrales.huella(): resultados}

    def correr(U: Umbrales) -> pd.DataFrame:
        if U.huella() in primera:
            return primera.pop(U.huella())
        return correr_bateria(tabla, U, avance=avance, contexto=ctx)[0]
    registro = ajustar_umbrales(umbrales, correr, tabla, ruta_registro=carpeta / ARCHIVO_REGISTRO_8F, reloj=reloj)
    huellas = escribir_salidas(carpeta, tabla, registro.resultados, registro.criterios, tiempo, registro=registro)
    pasa = not registro.c1_falla and bool(registro.criterios.pasa)
    return ResultadoBateriaC1(huellas=huellas, pasa=pasa, registro=registro, tiempo=tiempo, tabla=tabla)
