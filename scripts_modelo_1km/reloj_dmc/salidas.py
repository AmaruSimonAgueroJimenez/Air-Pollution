"""Salidas de la corrida: tablas e informe de §7.4, ``artefactos_evaluados.json.gz``, expedientes de §5.5,
privacidad y sello ``recibo_corrida.json`` (§7.1, §7.4, §5.5; fases 10 y 11 de §5.2).

Todo se escribe dentro de la carpeta de la corrida (LOCAL/…/HUMAN<AAAAMMDD>_RELOJ_DMC_1[_ERRATA<n>]/), de
forma atómica con ``entorno.escribir_atomico`` (nunca bajo /Volumes ni en los repositorios). Nada se imprime:
la consola y los registros sólo muestran conteos de avance hasta el sello (§5.2), y eso lo hace el
ejecutable; las funciones de aquí devuelven huellas y rutas relativas, nunca veredictos.

Cadena de huellas (§7.4): tablas (y expedientes/) → informe → política → recibo_corrida.json.
- ``escribir_tablas``: las nueve tablas de TABLAS_7_4 y estados_reglas_vencidas.parquet (SAL-19); devuelve
  nombre → sha256.
- ``expedientes``: expedientes/<código>.md con cinco figuras, para cada estación con algún año discrepante y
  para la muestra de control (decision.muestra_expedientes_control), con el mismo contenido y la misma
  profundidad.
- ``informe`` / ``informe_md`` / ``escribir_informe``: informe_reloj_dmc.json (con las huellas de las tablas,
  de expedientes/ y de artefactos_evaluados.json.gz) y su versión legible.
- ``politica_de_la_corrida``: rehace la política de la fase 10 con las huellas reales del informe y de los
  artefactos (politica.politica) y exige que su contenido no cambie.
- ``verificar_privacidad`` y ``sellar``; ``verificar_sello`` y ``comprobar_cadena`` releen todo.
- ``escribir_corrida``: la cadena completa en su orden, con las comprobaciones de §7.3 (A7) por un
  verificador que pasa el llamador (el ejecutable arma ``politica.ContextoVerificacion``). Fuera del modo
  sintético exige el verificador, todos los controles, todas las huellas y la tabla completa de meses (SAL-20).

ResultadoRed (Anexo F) se lee por atributos (CAMPOS_RESULTADO_RED); orquestacion no se importa, para que este
módulo no dependa de que ya funcione. Las claves de ``ResultadoRed.controles`` que se leen: «A1» a «A7»,
«G-dup», «calibracion_e3t» y «tablas» (DataFrames, como red.controles_red). Se leen además, si están,
``estaciones`` (ORQ-7) y ``estados_reglas_vencidas`` (ORQ-3, SAL-19).

Lecturas propias de este módulo (van al addendum de C1):
- SAL-1. Esquemas. evidencia_estacion_parte, evidencia_estacion_anio, no_normalizables.csv y el CSV de la
  calibración (ESQUEMA_EVIDENCIA_PARTE, ESQUEMA_EVIDENCIA_ANIO, ESQUEMA_NO_NORMALIZABLES,
  ESQUEMA_CALIBRACION_CSV) viven en tipos desde la ola 4b, como pide §2 del diseño; aquí quedan como alias de los
  mismos objetos. Las métricas por parte se copian con el
  prefijo de su línea (e2_, e3_…_ts/_qfe, e4_…_ts/_qfe/_hr). Los estados por H van como JSON canónico
  {línea[/regla]: {H: estado}}; las listas, como listas de texto. pixeles_dmc.parquet es ESQUEMA_ESTACIONES.
- SAL-2. A7 en el informe. La política cita al informe, así que §7.3 no puede correr sobre la política final
  antes de escribir el informe. Se corre sobre una política provisional idéntica salvo la huella del
  informe (SHA_INFORME_PROVISIONAL), escrita en <carpeta>/provisional_7_3/ y releída desde disco; su
  resultado (A7) y no_normalizables.csv entran al informe. La política final se compara después con la
  provisional: sólo pueden diferir ``informe.sha256`` y el «sha256=» de cada ``source`` (ninguna
  comprobación depende de ese valor). Si difieren en otra cosa, la corrida se detiene antes del sello. La
  provisional se borra antes de sellar.
- SAL-3. «Tablas … con su sha256 en el informe» incluye la carpeta expedientes/ (que §7.4 lista con las
  tablas) y artefactos_evaluados.json.gz. La carpeta lleva una huella agregada con el formato de §7.4 para
  los manifiestos: sha256 del texto «sha256␣␣ruta\\n», una línea por archivo, ordenado por ruta relativa a
  la carpeta de la corrida. Por eso los expedientes se escriben antes del informe.
- SAL-4. Sello. ``recibo_corrida.json`` lleva la sha256 de cada archivo regular de la carpeta (recursivo,
  extractos incluidos) salvo el propio recibo, y la total con el formato de SAL-3. No sella si queda un
  «.part», un enlace simbólico, un recibo previo o una falla de privacidad.
- SAL-5. Privacidad (§7.4 «sin rutas absolutas, «/Users/» ni «@»»; §8 punto 28; §10 «quitar toda ruta con
  correo»). Un dato estructurado con «/Users/», «@», la carpeta personal o una ruta absoluta hace fallar la
  escritura. Ruta absoluta = «/a/…» o «~/…» al comienzo del texto o después de un espacio, una comilla, un
  paréntesis, «=», «,», «;» o «:»; así no cuentan «America/Santiago», «E3p/gruesa», los alias («DMC/…») ni
  los URL («https://…», la url de G-dup). Los textos libres que vienen de excepciones (motivo de
  no_normalizables, fallas de A7) se redactan, y la ruta va entera, antes que el correo: toda ruta que
  empieza por la carpeta personal, por «~/» o por «/» (entre comillas, con sus espacios, como «…/Mi unidad/…»;
  sin ellas, con los tramos que siguen a un espacio si llevan «/») → «<ruta>»; después, todo token con «@»
  → «<correo>». Así no queda el usuario ni el dominio de una carpeta de Google Drive.
  ``verificar_privacidad`` revisa en toda la carpeta los textos (json, md, csv, jsonl, txt) y los .gz
  descomprimidos, y las cadenas de los parquet del nivel superior (las tablas de §7.4). Los extractos son de
  extraccion, que escribe por alias.
- SAL-6. Figuras de §5.5: «marcas por hora» = RR06, TX, TN y observador por hora de etiqueta y año; «días de
  cambio» = etiquetas medidas por hora en D−1, D y D+1 de cada cambio real de E1a/E1b; «ventanas» = primera
  y última hora medida de cada día (s_d, e_d de E1b), con los cambios marcados; «r(c) por mes» = r(c) de E3
  por parte (Ts y QFE), con ĉ; «ciclo diario» = media de Ts y QFE por hora de etiqueta y año, como anomalía
  de la media del año. Misma profundidad: siempre las mismas secciones y las cinco figuras; si faltan
  datos, la figura lo dice.
- SAL-7. Muestra de control: sobre todas las estaciones con algún año confirmado al final (después de §5.3),
  aunque también tengan un año discrepante. Si la sorteada ya tiene expediente de discrepancia, es el
  mismo archivo con los dos motivos, y no se repone. Semilla U.f("SEMILLA") y EXPEDIENTES_CONTROL_N.
- SAL-8. «Estación con algún año discrepante»: veredicto final «discrepante», también con la marca «civil
  con reglas vencidas» (sigue discrepante).
- SAL-9. Meses excluidos: por estado (pending, failed, candidato), por versión (version_no_admitida,
  sin_codigo) y otros (artifact_name, row_count). «Por campos faltantes» = meses con ``campos_faltantes``
  (no excluyen; extraccion, lectura 2), contados por campo. Se cuentan sobre la tabla completa de meses de
  extraccion (``extraccion.leer_meses``: todos los manifiestos considerados, también los de las estaciones
  sin ningún mes evaluado, que no llegan a las evidencias por ORQ-1). La tabla debe traer cada mes de las
  evidencias con la misma admisión, y sus meses evaluados son los de las evidencias y los de
  artefactos_evaluados. Sin ella (sólo en modo sintético) se cuentan sobre los meses de las evidencias, el
  informe lo dice en ``exclusiones.fuente`` y queda en las desviaciones (SAL-21).
- SAL-10. «Versión del descargador» de un estación-año = los ``script_sha256`` de sus meses evaluados.
- SAL-11. Veredicto de estación: el de ``politica["estaciones"]`` si hay política; si no (A5 alto), el de
  ``resultado.estaciones`` (ORQ-7); y si tampoco está, «confirmada» si algún año final quedó confirmado, con
  ``reloj`` = sucesión de las clases de sus rachas aceptadas (R-25), y la marca ``derivada_de_las_decisiones``.
  Desde la ola 4b la sucesión sigue la regla única de ORQ-7 (politica.reloj_de_rachas): rachas consecutivas
  con intersección no vacía van en un término, con su intersección, y «→» sólo donde la intersección es
  vacía.
- SAL-12. Comparación con E3t restringida (§5.2): es la decisión de §5.1, antes de §5.3, como la calcula
  orquestacion (ORQ-4). Del lado principal, un año que §5.3 dejó «sin_confirmar» por inestable o por cambio
  sin respaldo cuenta como el «confirmado» que fue (§5.3 conserva su clase). Se informan los conteos de las
  dos y los estación-años que cambian; evidencia_estacion_anio trae también la restringida.
- SAL-13. La política es la de la fase 10 con las huellas reales. Si orquestacion la armó, se rehace con
  politica.politica y deben quedar iguales las estaciones, los intervalos, los desfases y los tramos. Las
  marcas (post_hoc, errata_post_c4, ajuste_documental) son las de la corrida: orquestacion.evaluar_red no
  las recibe y las deja en falso, y una corrida _ERRATA<n> lleva errata_post_c4 (§10). Una marca que la
  fase 10 trae y la corrida no se rechaza: nunca se quita. Si la dejó en None por no tener huellas (ORQ-9),
  se arma con ``resultado.estaciones`` y ``resultado.tramos``. Que no haya política lo decide sólo A5
  (``consecuencias.a5_alto``), no un None.
- SAL-14. ``huellas_entrada`` debe traer todas las claves de CLAVES_HUELLAS y CLAVES_ENTRADAS. None (o vacío)
  vale «no aplica» sólo en modo sintético, y queda en las desviaciones (SAL-21). Toda clave «sha256» lleva
  64 hexadecimales.
- SAL-15. En el informe, los DataFrames de ``controles["tablas"]`` (muestras de A3 y A5, distribución de δt)
  se resumen por su número de filas: van completos en controles_red.json y calibracion_e3t.csv. Los de otras
  claves (G-dup) van completos.
- SAL-16. artefactos_evaluados.json.gz es público: sólo admite las claves de CLAVES_ARTEFACTO (las que escribe
  extraccion), ninguna de veredictos; gzip sin nombre y con mtime 0, JSON canónico, en orden de
  ``id_artefacto``.
- SAL-17. Nada que cambie entre dos corridas iguales entra a las salidas: ni ``ResultadoRed.tiempos`` ni
  fechas de reloj (R-31). La fecha de la corrida, si se quiere, la pone el llamador en ``huellas_entrada``.
- SAL-18. Los textos de A7 se redactan siempre (SAL-5), también cuando A7 lo dejó
  orquestacion.comprobar_politica en ``controles["A7"]``.
- SAL-19 [D]. Los estados del diagnóstico de reglas vencidas (§4.1.4, P ∪ Cv; ORQ-3) deciden la marca «civil
  con reglas vencidas», y con ella la cuenta de inestabilidad (§5.3): son parte de «la traza de cada
  decisión» (§7.4). Van en estados_reglas_vencidas.parquet (ESQUEMA_ESTADOS, vacío si no hubo
  diagnóstico), con su huella en el informe y en la cadena, sin cambiar ESQUEMA_ESTADOS. La otra opción
  (una columna en estados_largos) cambia tipos y la decide el autor.
- SAL-20. escribir_corrida corre §7.3 siempre que hay política (§5.2, fase 10): sin verificador sólo
  escribe con ``modo_sintetico=True``, que queda en el informe (``modo_sintetico``) y en las desviaciones.
  Fuera del modo sintético exige, antes de escribir nada, el verificador, todos los controles de
  CLAVES_CONTROLES (A7 lo pone esta corrida), todas las huellas y entradas sin None y la tabla completa de
  meses. ``controles["A7"]`` se reemplaza siempre por el §7.3 de la política de esta corrida (o «no
  evaluado»): nunca se arrastra uno que orquestacion calculó sobre otra política. Por lo mismo, los no
  normalizables son sólo los de ese §7.3 (ninguno si no corrió).
- SAL-21. Desviaciones automáticas (§10: «El informe lista toda diferencia de procedimiento»): el informe
  agrega a las que pasa el llamador una por cada control de CLAVES_CONTROLES que falta, cada huella o
  entrada None o vacía y la falta de la tabla completa de meses.
- SAL-22. También agrega las que orquestacion deja en los controles (``desviaciones_de_controles``): si
  ``controles["reglas_vencidas"]["lineas_sin_cv"]`` no está vacía, una que nombra las líneas activas que el
  diagnóstico de reglas vencidas no recalcula con Cv (ORQ-3f [pide enmienda]).
Depende de: entorno, tipos, decision (muestra de control), politica (política, regla del «reloj» y nombres de
los archivos publicados) y red (A7 y el texto «sin_dato»). matplotlib (Agg, sin pyplot) sólo en los expedientes.
"""
from __future__ import annotations

import copy
import gzip
import io
import json
import math
import os
import re
from collections import Counter
from dataclasses import fields, is_dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path, PurePath
from typing import TYPE_CHECKING, Any, Callable, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from reloj_dmc import decision, entorno, politica as mod_politica, red, tipos
from reloj_dmc.tipos import (ESQUEMA_ESTACIONES, ESQUEMA_ESTADOS, ESQUEMA_EVENTOS, ESQUEMA_MES, ESQUEMA_RACHAS,
                             ClaseEvento, Linea, MotivoAnio, Nivel, Regla, Veredicto, VeredictoEstacion, tabla_vacia,
                             validar_esquema)

if TYPE_CHECKING:   # sólo para las anotaciones: no se importa orquestacion (se implementa en paralelo)
    from reloj_dmc.orquestacion import ResultadoRed

TABLAS_7_4 = ("pixeles_dmc.parquet", "evidencia_estacion_parte.parquet", "evidencia_estacion_anio.parquet",
              "eventos_transicion.csv", "calibracion_e3t.csv", "controles_red.json", "rachas.parquet",
              "estados_largos.parquet", "no_normalizables.csv")
TABLA_REGLAS_VENCIDAS = "estados_reglas_vencidas.parquet"     # SAL-19
TABLAS = TABLAS_7_4 + (TABLA_REGLAS_VENCIDAS,)                 # lo que escribe escribir_tablas, en orden
ARCHIVO_INFORME = mod_politica.ARCHIVO_INFORME
ARCHIVO_INFORME_MD = mod_politica.ARCHIVO_INFORME_MD
ARCHIVO_POLITICA = mod_politica.ARCHIVO_POLITICA
ARCHIVO_ARTEFACTOS = mod_politica.ARCHIVO_ARTEFACTOS
INFORMES = (ARCHIVO_INFORME, ARCHIVO_INFORME_MD)
RECIBO = "recibo_corrida.json"
CARPETA_EXPEDIENTES = "expedientes"
INDICE_EXPEDIENTES = "indice.json"
CLAVE_EXPEDIENTES = CARPETA_EXPEDIENTES + "/"      # huella agregada de la carpeta en las huellas del informe
CARPETA_PROVISIONAL = "provisional_7_3"           # SAL-2
FIGURAS = ("marcas_por_hora", "dias_de_cambio", "ventanas", "r_por_mes", "ciclo_diario")
SUFIJO_PARCIAL = ".part"

ESQUEMA_INFORME = "dmc-reloj-informe/1"
ESQUEMA_RECIBO = "dmc-reloj-recibo/1"
ESQUEMA_CONTROLES = "dmc-reloj-controles-red/1"
ESQUEMA_INDICE_EXPEDIENTES = "dmc-reloj-expedientes/1"
FORMATO_HUELLA_AGREGADA = "sha256 del texto «sha256␣␣ruta\\n», una línea por archivo, ordenado por ruta"
# SAL-2: huella del informe en la política provisional (cualquier sha256 sirve: ninguna comprobación la usa).
SHA_INFORME_PROVISIONAL = entorno.sha256_bytes("informe provisional de la fase 10 (SAL-2)".encode("utf-8"))

# Campos de ResultadoRed (Anexo F) que este módulo lee.
CAMPOS_RESULTADO_RED = ("evidencias", "consecuencias", "controles", "decisiones", "decisiones_e3t_restringida",
                        "rachas", "meses_con_regla", "tramos", "politica", "descripcion_red", "predicciones",
                        "no_normalizables")
# SAL-14: huellas y entradas que exige el informe (§7.4).
CLAVES_HUELLAS = ("protocolo", "configuracion", "codigo", "adaptador", "interprete", "anexo_a", "anexo_a2")
CLAVES_ENTRADAS = ("manifiestos", "progreso", "catalogo_dmc", "era5l", "copias_c2")
# SAL-16: claves de cada artefacto evaluado (las de extraccion.extraer_dmc); las dos primeras son obligatorias.
CLAVES_ARTEFACTO_OBLIGATORIAS = ("artefacto_sha256", "codigo")
CLAVES_ARTEFACTO = ("artefacto_sha256", "codigo", "id_artefacto", "anio", "mes", "manifiesto", "manifiesto_sha256",
                    "artefacto", "row_count", "script_sha256")
# SAL-9: grupos de los motivos de exclusión de extraccion.
MOTIVOS_POR_ESTADO = ("pending", "failed", "candidato")
MOTIVOS_POR_VERSION = ("version_no_admitida", "sin_codigo")
EXTENSIONES_TEXTO = (".json", ".md", ".csv", ".jsonl", ".txt")
CLAVES_CONTROLES = ("A1", "A2", "A3", "A4", "A5", "A6", "A7", "G-dup", "calibracion_e3t")
CLAVE_TABLAS_CONTROLES = "tablas"
CLAVE_CALIBRACION = "calibracion_e3t"
SIN_DATO = red.SIN_DATO
# SAL-9: de dónde salen los meses excluidos del informe.
FUENTE_EXTRACCION = "extraccion"     # la tabla completa de meses (extraccion.leer_meses)
FUENTE_EVIDENCIAS = "evidencias"     # sólo los meses de las estaciones con algún mes evaluado (modo sintético)
# SAL-20 y SAL-21: desviaciones que agrega salidas.
DESVIACION_SIN_7_3 = ("modo sintético: §7.3 no corrió (sin verificador), A7 quedó sin evaluar y la política escrita "
                      "no es publicable (§5.2, fase 10; §5.4, A7)")
DESVIACION_SIN_MESES = ("los meses excluidos se cuentan sólo en las estaciones con algún mes evaluado: falta la tabla "
                        "completa de meses de extraccion (§7.4, SAL-9)")
# SAL-22: el diagnóstico de reglas vencidas no recalcula con Cv algunas líneas activas (ORQ-3f [pide enmienda]).
CLAVE_REGLAS_VENCIDAS = "reglas_vencidas"
CLAVE_LINEAS_SIN_CV = "lineas_sin_cv"
DESVIACION_LINEAS_SIN_CV = ("el diagnóstico de reglas vencidas (§4.1.4; Enmienda 1, E1-4: «todas las líneas») no "
                            "recalcula con Cv las líneas activas {lineas}, que quedan sin información para Cv "
                            "(ORQ-3f, pide enmienda)")

# --- Esquemas propios (SAL-1) ---------------------------------------------------------------------------
# Viven en tipos desde la ola 4b (§2 del diseño); estos alias son los mismos objetos.
_CLAVES_METRICAS = tipos.CLAVES_METRICAS
VARIABLES_E3 = tipos.VARIABLES_EVIDENCIA_E3
VARIABLES_E4 = tipos.VARIABLES_EVIDENCIA_E4
_COLS_E2 = tipos.COLUMNAS_EVIDENCIA_E2
_COLS_E3 = tipos.COLUMNAS_EVIDENCIA_E3
_COLS_E4 = tipos.COLUMNAS_EVIDENCIA_E4
ESQUEMA_EVIDENCIA_PARTE = tipos.ESQUEMA_EVIDENCIA_PARTE
ESQUEMA_EVIDENCIA_ANIO = tipos.ESQUEMA_EVIDENCIA_ANIO
ESQUEMA_NO_NORMALIZABLES = tipos.ESQUEMA_NO_NORMALIZABLES
ESQUEMA_CALIBRACION_CSV = tipos.ESQUEMA_CALIBRACION_CSV

# --- Figuras (no son umbrales) ------------------------------------------------------------------------
HORAS_DIA = 24
DESPLAZAMIENTOS_DIA = (-1, 0, 1)        # no-umbral: D−1, D y D+1 de cada cambio de hora (SAL-6)
_DPI = 100                              # no-umbral: resolución de las figuras
_ANCHO = 11.0                           # no-umbral: ancho de figura (pulgadas)
_ALTO = 7.0                             # no-umbral: alto de figura (pulgadas)
_ALTO_FILA = 0.16                       # no-umbral: alto por fila de un mapa de calor (pulgadas)
_ALTO_MIN = 3.5                         # no-umbral: alto mínimo de un mapa de calor (pulgadas)
_PASO_HORAS = 3                         # no-umbral: marcas del eje de horas
_MAX_ETIQUETAS = 40                     # no-umbral: etiquetas como máximo en un eje de filas
_LETRA = 7                              # no-umbral: tamaño de letra de los ejes
_PUNTO = 2.0                            # no-umbral: tamaño de los puntos
_LINEA = 0.8                            # no-umbral: grosor de las líneas
_CENTRO = 0.5                           # no-umbral: centro de los ejes en coordenadas relativas
_GRIS = "0.6"

_SHA = re.compile(r"[0-9a-f]{64}")
_CODIGO = re.compile(r"\d{6}")
_PARTE = re.compile(r"(\d{4})-(\d{2})-(\d+)")
_SHA_EN_SOURCE = re.compile(r" sha256=[0-9a-f]{64} ")
# SAL-5: rutas absolutas. Una ruta empieza con «/» o «~/» al comienzo del texto o después de uno de estos
# caracteres; «America/Santiago», «E3p/gruesa», los alias («DMC/…») y los URL («https://…»: después de «:» viene
# otra «/») no cuentan.
_ANTES_DE_RUTA = r"\s'\"«‹“‘`(\[{=,;:"
_FIN_DE_RUTA = r"\s'\"«»‹›“”‘’`()\[\]{}<>,;:"
_INICIO_RUTA = rf"(?<![^{_ANTES_DE_RUTA}])(?:~/|/(?=[\w.~-]))"
# En un dato estructurado (falla la escritura): «~/…» o una ruta de dos tramos, «/a/…» (el nombre de una
# estación como «Arica /Chacalluta» no es una ruta).
_RUTA_EN_DATO = re.compile(rf"(?<![^{_ANTES_DE_RUTA}])(?:~/|/[\w.~-][^{_FIN_DE_RUTA}/]*/)")
# En un texto libre (se redacta) va la ruta entera: entre comillas, con sus espacios («…/Mi unidad/…»); sin
# ellas, con los tramos que siguen a un espacio si llevan «/».
_RUTA_ENTRE_COMILLAS = re.compile(r"'(?:~/|/[\w.~-])[^'\n]*'|\"(?:~/|/[\w.~-])[^\"\n]*\"|«(?:~/|/[\w.~-])[^»\n]*»")
_SIGUE_RUTA = rf"[^{_FIN_DE_RUTA}]*(?: [^{_FIN_DE_RUTA}/]+/[^{_FIN_DE_RUTA}]*)*"
_RUTA_LIBRE = re.compile(_INICIO_RUTA + _SIGUE_RUTA)
_RAICES = re.compile(r"/(?:Users|Volumes|home|private|var|tmp|opt|Library|System)/" + _SIGUE_RUTA)
_CORREO = re.compile(rf"[^{_FIN_DE_RUTA}]*@[^{_FIN_DE_RUTA}]*")
RUTA_REDACTADA = "<ruta>"
CORREO_REDACTADO = "<correo>"


# =========================================================================================================
# Utilidades: resultado, JSON, privacidad
# =========================================================================================================
class ErrorRetenido(ValueError):
    """Error cuyo detalle puede mostrar veredictos (§5.2: nada de veredictos a la vista antes del sello). El
    mensaje no los trae; el detalle queda en ``detalle``, para que el ejecutable lo escriba dentro de la
    carpeta de la corrida y no en la consola."""

    def __init__(self, mensaje: str, detalle: str):
        super().__init__(f"{mensaje} (detalle retenido hasta el sello, §5.2)")
        self.detalle = detalle


def _exigir_resultado(resultado: Any) -> None:
    faltan = [c for c in CAMPOS_RESULTADO_RED if not hasattr(resultado, c)]
    if faltan:
        raise TypeError(f"el resultado de la red no trae los campos {faltan} (Anexo F, ResultadoRed)")


def _ordenadas(evidencias: Iterable) -> list:
    lista = sorted(evidencias, key=lambda ev: ev.info.codigo)
    codigos = [ev.info.codigo for ev in lista]
    if len(set(codigos)) != len(codigos):
        raise ValueError("hay dos evidencias de una misma estación")
    return lista


def _na(v: Any) -> Any:
    """None para los nulos de pandas y numpy; los escalares de numpy pasan a Python."""
    if v is None or v is pd.NA or v is pd.NaT:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, np.generic):
        v = v.item()
        if isinstance(v, float) and math.isnan(v):
            return None
    return v


def _lista(v: Any) -> list | None:
    """Lista de Python (r(c), clases, partes…) desde lista, tupla o arreglo; None si es nulo."""
    if v is None or v is pd.NA:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    return [_na(x) if not isinstance(x, str) else x for x in list(v)]


def _id(h: Any) -> str:
    return str(getattr(h, "id", h))


def _texto_mes(anio: int, mes: int) -> str:
    return f"{int(anio):04d}-{int(mes):02d}"


def _clave_json(k: Any) -> str:
    if isinstance(k, str):
        return str(k)
    if isinstance(k, (int, np.integer)) and not isinstance(k, bool):
        return str(int(k))
    raise TypeError(f"clave no textual en una salida JSON: {type(k).__name__}")


def _registros(df: pd.DataFrame) -> dict:
    return {"columnas": [str(c) for c in df.columns],
            "filas": [[_json(v) for v in fila] for fila in df.itertuples(index=False, name=None)]}


def _json(x: Any) -> Any:
    """Valor apto para ``entorno.json_canonico`` (sin NaN, claves de texto, sin rutas absolutas)."""
    if x is None or isinstance(x, bool):
        return x
    if isinstance(x, str):
        return str(x)
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        v = float(x)
        return v if math.isfinite(v) else None
    if x is pd.NA or x is pd.NaT:
        return None
    if isinstance(x, pd.Timestamp):
        return x.isoformat()
    if isinstance(x, (datetime, date)):
        return x.isoformat()
    if isinstance(x, np.datetime64):
        return None if np.isnat(x) else pd.Timestamp(x).isoformat()
    if isinstance(x, PurePath):
        if x.is_absolute():
            raise ValueError("ruta absoluta en una salida (§7.4, privacidad)")
        return x.as_posix()
    if isinstance(x, pd.DataFrame):
        return _registros(x)
    if isinstance(x, (pd.Series, pd.Index, np.ndarray, pd.api.extensions.ExtensionArray)):
        return [_json(v) for v in list(x)]
    if is_dataclass(x) and not isinstance(x, type):
        return {f.name: _json(getattr(x, f.name)) for f in fields(x)}
    if isinstance(x, Mapping):
        salida: dict[str, Any] = {}
        for k, v in x.items():
            clave = _clave_json(k)
            if clave in salida:
                raise ValueError(f"clave repetida al pasar a JSON: {clave!r}")
            salida[clave] = _json(v)
        return salida
    if isinstance(x, (set, frozenset)):
        return sorted((_json(v) for v in x), key=entorno.json_canonico)
    if isinstance(x, (list, tuple)):
        return [_json(v) for v in x]
    raise TypeError(f"valor no serializable en una salida: {type(x).__name__}")


def _texto_json(x: Any) -> str:
    return entorno.json_canonico(_json(x)).decode("utf-8")


def _privado(texto: str) -> bool:
    """§7.4: sin «/Users/», «@», la carpeta personal ni rutas absolutas (SAL-5)."""
    return entorno.sin_datos_privados(texto) and _RUTA_EN_DATO.search(texto) is None


def _exigir_privado(texto: str, donde: str) -> None:
    if not _privado(texto):
        raise ValueError(f"{donde}: contiene «/Users/», «@», la carpeta personal o una ruta absoluta (§7.4, privacidad)")


def _casas() -> list[str]:
    """La carpeta personal, también resuelta (si es un enlace), de la más larga a la más corta."""
    casa = str(Path.home())
    return sorted({c for c in (casa, os.path.realpath(casa)) if len(c) > 1}, key=len, reverse=True)


def redactar(texto: Any) -> str | None:
    """SAL-5: texto libre (mensaje de excepción) sin rutas absolutas, carpeta personal ni correos.

    Primero va la ruta entera (entre comillas, la carpeta personal, toda ruta que empieza por «/» o «~/» y, en
    cualquier lugar, las raíces conocidas como «/Volumes/») → «<ruta>»; después, todo token con «@» →
    «<correo>». Así una ruta bajo una carpeta de Google Drive, que lleva el correo en su nombre, no deja ni el
    usuario ni el dominio."""
    if texto is None:
        return None
    t = _RUTA_ENTRE_COMILLAS.sub(lambda m: m.group(0)[0] + RUTA_REDACTADA + m.group(0)[-1], str(texto))
    for casa in _casas():
        t = re.sub(re.escape(casa) + _SIGUE_RUTA, RUTA_REDACTADA, t)
    t = _RUTA_LIBRE.sub(RUTA_REDACTADA, t)
    t = _RAICES.sub(RUTA_REDACTADA, t)
    t = _CORREO.sub(CORREO_REDACTADO, t)
    if not _privado(t):     # no debería pasar: los pasos de arriba cubren lo que _privado rechaza
        raise RuntimeError("la redacción dejó un dato privado (SAL-5)")
    return t


def _redactar_todo(x: Any) -> Any:
    """Redacta cada texto de una estructura JSON (fallas de A7)."""
    if isinstance(x, str):
        return redactar(x)
    if isinstance(x, list):
        return [_redactar_todo(v) for v in x]
    if isinstance(x, dict):
        return {k: _redactar_todo(v) for k, v in x.items()}
    return x


def _cadenas(v: Any) -> Iterable[str]:
    """Las cadenas que hay dentro de un valor (texto, lista, arreglo o diccionario); los números no cuentan."""
    if isinstance(v, str):
        yield v
    elif isinstance(v, Mapping):
        for k, x in v.items():
            yield from _cadenas(k)
            yield from _cadenas(x)
    elif isinstance(v, (list, tuple, set, frozenset)) or (isinstance(v, np.ndarray) and v.dtype == object):
        for x in v:
            yield from _cadenas(x)


def _revisar_marco(df: pd.DataFrame, donde: str) -> None:
    """Privacidad de las cadenas de un DataFrame antes de escribirlo (SAL-5)."""
    for c in df.columns:
        _exigir_privado(str(c), f"{donde}, nombre de columna")
        s = df[c]
        if s.dtype == object:
            vistos = {x for v in s for x in _cadenas(v)}
        elif str(s.dtype) == "string":
            vistos = set(s.dropna().unique().tolist())
        else:
            continue
        for v in vistos:
            _exigir_privado(str(v), f"{donde}, columna {c}")


def _marco(filas: Sequence[Mapping[str, Any]], esquema: Mapping[str, str], nombre: str) -> pd.DataFrame:
    """DataFrame con las columnas, el orden y los tipos exactos del esquema."""
    if not filas:
        return tabla_vacia(esquema)
    columnas = {}
    for col, tipo in esquema.items():
        valores = [f.get(col) for f in filas]
        if tipo == "object":
            columnas[col] = pd.Series(valores, dtype=object)
        elif tipo == "float64":
            columnas[col] = pd.Series([np.nan if _na(v) is None else float(v) for v in valores], dtype="float64")
        else:
            columnas[col] = pd.Series([_na(v) for v in valores], dtype=object).astype(tipo)
    df = pd.DataFrame(columnas)
    validar_esquema(df, esquema, nombre=nombre)
    return df


def _concatenar(marcos: Sequence[pd.DataFrame], esquema: Mapping[str, str], nombre: str) -> pd.DataFrame:
    utiles = []
    for m in marcos:
        validar_esquema(m, esquema, nombre=nombre)
        if len(m):
            utiles.append(m)
    if not utiles:
        return tabla_vacia(esquema)
    df = pd.concat(utiles, ignore_index=True)
    validar_esquema(df, esquema, nombre=nombre)
    return df


def _para_arrow(df: pd.DataFrame) -> pd.DataFrame:
    """Listas de numpy o tuplas → listas de Python en las columnas «object» (sin copiar las demás)."""
    objetos = [c for c in df.columns if df[c].dtype == object]
    if not objetos:
        return df
    salida = df.copy(deep=False)
    for c in objetos:
        salida[c] = pd.Series([_lista(v) if isinstance(v, (np.ndarray, tuple)) else v for v in df[c]],
                              dtype=object, index=df.index)
    return salida


def _bytes_parquet(df: pd.DataFrame, nombre: str) -> bytes:
    _revisar_marco(df, nombre)
    buf = io.BytesIO()
    _para_arrow(df).to_parquet(buf, index=False, engine="pyarrow")
    return buf.getvalue()


def _bytes_parquet_por_trozos(marcos: Iterable[pd.DataFrame], esquema: Mapping[str, str], nombre: str) -> bytes:
    """Un parquet escrito trozo a trozo (un grupo de filas por estación), para no juntar en memoria la tabla
    entera. Cada trozo se valida contra el esquema y se revisa su privacidad. Sólo para esquemas sin «object»,
    cuyo tipo de arrow no depende de los valores."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    if "object" in esquema.values():
        raise ValueError(f"{nombre}: la escritura por trozos no admite columnas «object»")
    buf = io.BytesIO()
    escritor, esquema_pa = None, None
    try:
        for m in marcos:
            validar_esquema(m, esquema, nombre=nombre)
            if not len(m):
                continue
            _revisar_marco(m, nombre)
            tabla = pa.Table.from_pandas(m, preserve_index=False)
            if escritor is None:
                esquema_pa = tabla.schema
                escritor = pq.ParquetWriter(buf, esquema_pa)
            elif not tabla.schema.equals(esquema_pa, check_metadata=False):
                raise ValueError(f"{nombre}: un trozo trae otro esquema de arrow")
            escritor.write_table(tabla.replace_schema_metadata(esquema_pa.metadata))
    finally:
        if escritor is not None:
            escritor.close()
    if escritor is None:
        return _bytes_parquet(tabla_vacia(esquema), nombre)
    return buf.getvalue()


def _bytes_csv(df: pd.DataFrame, nombre: str) -> bytes:
    salida = df.copy()
    for c in salida.columns:   # objetos (listas) → JSON canónico
        if salida[c].dtype == object:
            salida[c] = pd.Series([v if v is None or isinstance(v, str) else _texto_json(_lista(v) if isinstance(
                v, np.ndarray) else v) for v in salida[c]], dtype=object, index=salida.index)
    buf = io.StringIO()
    salida.to_csv(buf, index=False, lineterminator="\n")
    texto = buf.getvalue()
    _exigir_privado(texto, nombre)
    return texto.encode("utf-8")


def _bytes_json(obj: Any, nombre: str) -> bytes:
    datos = entorno.json_canonico(_json(obj))
    _exigir_privado(datos.decode("utf-8"), nombre)
    return datos


# =========================================================================================================
# Tablas de §7.4
# =========================================================================================================
def tabla_pixeles(evidencias: Iterable) -> pd.DataFrame:
    """pixeles_dmc.parquet (ESQUEMA_ESTACIONES): píxel, distancia, Δz, territorio, macrozona, costera y marcas."""
    filas = []
    for ev in _ordenadas(evidencias):
        i = ev.info
        filas.append({"codigo": i.codigo, "nombre": i.nombre, "lat": i.lat, "lon": i.lon, "alt_m": i.alt_m,
                      "coordenadas_validas": bool(i.coordenadas_validas),
                      "coordenadas_inconsistentes": bool(i.coordenadas_inconsistentes),
                      "territorio": str(i.territorio), "region": i.region, "macrozona": i.macrozona,
                      "zs": [str(z) for z in i.zs], "P": [_id(h) for h in i.P], "pixel_id": i.pixel_id,
                      "distancia_km": i.distancia_km, "costera": bool(i.costera), "z_pix": i.z_pix, "dz": i.dz,
                      "conjunto": str(i.conjunto), "tipo": i.tipo, "propietario": i.propietario, "omm": i.omm,
                      "oaci": i.oaci})
    return _marco(filas, ESQUEMA_ESTACIONES, "pixeles_dmc")


def _clave_linea(linea: Any, regla: Any) -> str:
    return str(linea) if str(regla) == str(Regla.UNICA) else f"{linea}/{regla}"


def _orden_parte(parte: str) -> tuple[int, int, int]:
    m = _PARTE.fullmatch(str(parte))
    if m is None:
        raise ValueError(f"id de parte distinto de «AAAA-MM-n»: {parte!r}")
    anio, mes, n = (int(g) for g in m.groups())
    return anio, mes, n


_CLAVES_PARTE = ["anio", "unidad"]
_SIN_ESTADOS = "{}"   # JSON canónico de un diccionario vacío


def _metricas_parte(metricas: pd.DataFrame, columnas: Sequence[str], prefijo: str, variable: str | None,
                    codigo: str) -> pd.DataFrame:
    """Filas de nivel parte de una tabla de métricas, con las columnas renombradas «prefijo_col[_variable]»."""
    sel = metricas[metricas["nivel"] == str(Nivel.PARTE)]
    if variable is not None:
        sel = sel[sel["variable"] == variable]
    sufijo = "" if variable is None else f"_{variable.lower()}"
    salida = sel[[*_CLAVES_PARTE, "regimen", *columnas]].rename(
        columns={"regimen": f"_regimen_{prefijo}{sufijo}", **{c: f"{prefijo}_{c}{sufijo}" for c in columnas}})
    salida = salida.assign(unidad=salida["unidad"].astype(str), anio=salida["anio"].astype("int16"))
    if salida.duplicated(_CLAVES_PARTE).any():
        raise ValueError(f"{codigo}: una parte tiene dos filas de métricas de {prefijo}{sufijo}")
    return salida.reset_index(drop=True)


def _estados_parte(ev) -> pd.DataFrame:
    """Por parte: estados por H en JSON canónico, líneas con reloj anómalo y líneas discordantes."""
    e = ev.estados
    sel = e[e["nivel"] == str(Nivel.PARTE)]
    columnas = [*_CLAVES_PARTE, "estados", "lineas_reloj_anomalo", "discordante", "lineas_discordantes"]
    if not len(sel):
        return pd.DataFrame({c: pd.Series(dtype="int16" if c == "anio" else object) for c in columnas})
    linea = sel["linea"].astype(str).to_numpy(object)
    regla = sel["regla"].astype(str).to_numpy(object)
    clave = np.where(regla == str(Regla.UNICA), linea, linea + "/" + regla)
    d = pd.DataFrame({"anio": sel["anio"].to_numpy(np.int16), "unidad": sel["unidad"].astype(str).to_numpy(object),
                      "clave": clave, "H": sel["H"].astype(str).to_numpy(object),
                      "estado": sel["estado"].astype(str).to_numpy(object),
                      "anom": sel["reloj_anomalo"].to_numpy(bool), "disc": sel["discordante"].to_numpy(bool)})
    if d.duplicated([*_CLAVES_PARTE, "clave", "H"]).any():
        raise ValueError(f"{ev.info.codigo}: un estado de parte repetido (misma línea, regla, parte y H)")
    d = d.sort_values([*_CLAVES_PARTE, "clave", "H"], kind="mergesort")
    filas, actual, por_clave, anom, disc = [], None, {}, set(), set()

    def cerrar() -> None:   # sólo textos: entorno.json_canonico sin el recorrido de _json
        filas.append((actual[0], actual[1], entorno.json_canonico(por_clave).decode("utf-8"), sorted(anom), bool(disc),
                      sorted(disc)))

    for anio, unidad, cl, h, estado, an, di in d.itertuples(index=False, name=None):
        if (anio, unidad) != actual:
            if actual is not None:
                cerrar()
            actual, por_clave, anom, disc = (anio, unidad), {}, set(), set()
        por_clave.setdefault(cl, {})[h] = estado
        if an:
            anom.add(cl)
        if di:
            disc.add(cl)
    cerrar()
    salida = pd.DataFrame(filas, columns=columnas)
    return salida.assign(anio=salida["anio"].astype("int16"))


def _partes_de(ev) -> pd.DataFrame:
    """evidencia_estacion_parte de una estación (sin validar tipos)."""
    codigo = ev.info.codigo
    piezas = [_metricas_parte(ev.metricas_e2, _COLS_E2, "e2", None, codigo)]
    for metricas, variables, columnas, prefijo in ((ev.metricas_e3, VARIABLES_E3, _COLS_E3, "e3"),
                                                   (ev.metricas_e4, VARIABLES_E4, _COLS_E4, "e4")):
        presentes = set(metricas.loc[metricas["nivel"] == str(Nivel.PARTE), "variable"].astype(str))
        ajenas = sorted(presentes - set(variables))
        if ajenas:
            raise ValueError(f"{codigo}: variables {ajenas} fuera de {variables} en las métricas de {prefijo}")
        piezas += [_metricas_parte(metricas, columnas, prefijo, v, codigo) for v in variables]
    estados = _estados_parte(ev)
    claves = pd.concat([p[_CLAVES_PARTE] for p in [*piezas, estados]], ignore_index=True).drop_duplicates()
    partes = claves["unidad"].str.extract(r"^(\d{4})-(\d{2})-(\d+)$")
    if partes.isna().any().any():
        raise ValueError(f"{codigo}: hay partes con un id distinto de «AAAA-MM-n»")
    partes = partes.astype(int)
    if (partes[0].to_numpy() != claves["anio"].to_numpy()).any():
        raise ValueError(f"{codigo}: hay partes cuyo id no es de su año")
    base = claves.assign(codigo=codigo, mes=partes[1].to_numpy(), _n=partes[2].to_numpy())
    base = base.sort_values(["anio", "mes", "_n"], kind="mergesort").reset_index(drop=True)
    for p in [*piezas, estados]:
        base = base.merge(p, on=_CLAVES_PARTE, how="left", validate="one_to_one")
    regimen = pd.Series(pd.NA, index=base.index, dtype="string")
    for c in (c for c in base.columns if c.startswith("_regimen_")):   # el primero que lo trae
        regimen = regimen.fillna(base[c].astype("string"))
    base["regimen"] = regimen
    base = base.rename(columns={"unidad": "parte"})
    for c, tipo in ESQUEMA_EVIDENCIA_PARTE.items():
        if c not in base.columns:
            base[c] = None
        elif tipo == "object":
            base[c] = pd.Series([v if isinstance(v, (list, np.ndarray)) else None for v in base[c]], dtype=object)
    base["estados"] = base["estados"].where(base["estados"].notna(), _SIN_ESTADOS)
    for c in ("lineas_reloj_anomalo", "lineas_discordantes"):
        base[c] = pd.Series([list(v) if v is not None else [] for v in base[c]], dtype=object)
    base["discordante"] = pd.Series([v is True or isinstance(v, np.bool_) and bool(v) for v in base["discordante"]],
                                    dtype=bool)
    return base[list(ESQUEMA_EVIDENCIA_PARTE)]


def tabla_evidencia_parte(evidencias: Iterable) -> pd.DataFrame:
    """evidencia_estacion_parte.parquet: una fila por parte (SAL-1): conteos, E2, r(c) de Ts y QFE (también
    filtrada), ĉ, ĉ_cont y estabilidad, E4, estados por H y partes discordantes."""
    marcos = [_partes_de(ev) for ev in _ordenadas(evidencias)]
    marcos = [m for m in marcos if len(m)]
    if not marcos:
        return tabla_vacia(ESQUEMA_EVIDENCIA_PARTE)
    df = pd.concat(marcos, ignore_index=True)
    sin_objetos = {c: t for c, t in ESQUEMA_EVIDENCIA_PARTE.items() if t != "object"}
    df = df.astype(sin_objetos)
    validar_esquema(df, ESQUEMA_EVIDENCIA_PARTE, nombre="evidencia_estacion_parte")
    return df


def _estados_anuales(ev) -> dict[int, str]:
    e = ev.estados
    sel = e[e["nivel"] == str(Nivel.ANIO)]
    por_anio: dict[int, dict] = {}
    for anio, linea, regla, h, estado in zip(sel["anio"], sel["linea"], sel["regla"], sel["H"], sel["estado"]):
        por_h = por_anio.setdefault(int(anio), {}).setdefault(_clave_linea(linea, regla), {})
        if str(h) in por_h:
            raise ValueError(f"{ev.info.codigo}: estado anual repetido ({anio}, {linea}, {h})")
        por_h[str(h)] = str(estado)
    return {a: _texto_json(v) for a, v in por_anio.items()}


def _versiones_por_anio(meses: pd.DataFrame) -> dict[int, list[str]]:
    salida: dict[int, set[str]] = {}
    entran = meses[meses["entra"].astype(bool)]
    for anio, sha in zip(entran["anio"], entran["script_sha256"]):
        if _na(sha) is not None:
            salida.setdefault(int(anio), set()).add(str(sha))
    return {a: sorted(v) for a, v in salida.items()}


def _clave_decision(d) -> tuple[str, int]:
    return str(d.codigo), int(d.anio)


def tabla_evidencia_anio(resultado: "ResultadoRed") -> pd.DataFrame:
    """evidencia_estacion_anio.parquet: la traza de §5.1 por estación-año (decisiones finales), con conjunto,
    estados anuales por línea y H, versión del descargador y la decisión con E3t restringida (SAL-10, SAL-12)."""
    _exigir_resultado(resultado)
    evidencias = {ev.info.codigo: ev for ev in _ordenadas(resultado.evidencias)}
    estados_anuales = {c: _estados_anuales(ev) for c, ev in evidencias.items()}
    versiones = {c: _versiones_por_anio(ev.meses) for c, ev in evidencias.items()}
    restringida = {_clave_decision(d): d for d in (resultado.decisiones_e3t_restringida or ())}
    filas, vistas = [], set()
    for d in sorted(resultado.decisiones, key=_clave_decision):
        clave = _clave_decision(d)
        if clave in vistas:
            raise ValueError(f"decisión repetida para {clave[0]} {clave[1]}")
        vistas.add(clave)
        ev = evidencias.get(d.codigo)
        info = ev.info if ev is not None else None
        alt = restringida.get(clave)
        filas.append({
            "codigo": d.codigo, "anio": int(d.anio),
            "conjunto": None if info is None else str(info.conjunto),
            "territorio": None if info is None else str(info.territorio),
            "macrozona": None if info is None else info.macrozona,
            "P": [str(h) for h in d.P], "clases": [str(c) for c in d.clases],
            "estados": estados_anuales.get(d.codigo, {}).get(int(d.anio), _texto_json({})),
            "excluidas": _texto_json({str(k): list(v) for k, v in dict(d.excluidas).items()}),
            "K": [str(c) for c in d.K], "veredicto": str(d.veredicto),
            "motivo": None if d.motivo is None else str(d.motivo), "detalle": d.detalle,
            "clase_confirmada": d.clase_confirmada,
            "lineas_apoyo": [str(x) for x in d.lineas_apoyo], "familias_apoyo": [str(x) for x in d.familias_apoyo],
            "n_lineas_q": int(d.n_lineas_q),
            "meses_con_apoyo": [str(x) for x in d.meses_con_apoyo], "meses_con_datos": [str(x) for x in d.meses_con_datos],
            "n_meses_con_apoyo": len(d.meses_con_apoyo), "n_meses_con_datos": len(d.meses_con_datos),
            "partes_discordantes": [str(x) for x in d.partes_discordantes],
            "guardas": _texto_json(dict(d.guardas)), "marcas": _texto_json(dict(d.marcas)),
            "reglas_vencidas": bool(d.reglas_vencidas), "modo_e3t": None if d.modo_e3t is None else str(d.modo_e3t),
            "versiones_descargador": versiones.get(d.codigo, {}).get(int(d.anio), []),
            "veredicto_e3t_restringida": None if alt is None else str(alt.veredicto),
            "clase_e3t_restringida": None if alt is None else alt.clase_confirmada})
    return _marco(filas, ESQUEMA_EVIDENCIA_ANIO, "evidencia_estacion_anio")


def tabla_eventos(evidencias: Iterable) -> pd.DataFrame:
    """eventos_transicion.csv (ESQUEMA_EVENTOS): E1a, E1b, E1c, placebos y reglas vencidas."""
    return _concatenar([ev.eventos for ev in _ordenadas(evidencias)], ESQUEMA_EVENTOS, "eventos_transicion")


def tabla_estados_largos(evidencias: Iterable) -> pd.DataFrame:
    """estados_largos.parquet (ESQUEMA_ESTADOS): la traza de cada decisión."""
    return _concatenar([ev.estados for ev in _ordenadas(evidencias)], ESQUEMA_ESTADOS, "estados_largos")


def tabla_estados_reglas_vencidas(resultado: "ResultadoRed") -> pd.DataFrame:
    """estados_reglas_vencidas.parquet (ESQUEMA_ESTADOS; SAL-19): los estados del diagnóstico de reglas vencidas
    de §4.1.4 (P ∪ Cv), que deciden la marca «civil con reglas vencidas». Vacía si no hubo diagnóstico."""
    df = getattr(resultado, "estados_reglas_vencidas", None)
    if df is None:
        return tabla_vacia(ESQUEMA_ESTADOS)
    if not isinstance(df, pd.DataFrame):
        raise ValueError("estados_reglas_vencidas no es un DataFrame (ESQUEMA_ESTADOS)")
    validar_esquema(df, ESQUEMA_ESTADOS, nombre="estados_reglas_vencidas")
    return df.sort_values("codigo", kind="mergesort").reset_index(drop=True)


def tabla_rachas(rachas: pd.DataFrame) -> pd.DataFrame:
    """rachas.parquet (ESQUEMA_RACHAS), ordenada por código y racha."""
    validar_esquema(rachas, ESQUEMA_RACHAS, nombre="rachas")
    return rachas.sort_values(["codigo", "racha"], kind="mergesort").reset_index(drop=True)


def tabla_no_normalizables(filas: Iterable[Mapping]) -> pd.DataFrame:
    """no_normalizables.csv: abortos por los datos de la comprobación 7 de §7.3 (textos redactados, SAL-5)."""
    salida = []
    for f in filas:
        if not isinstance(f, Mapping):
            raise ValueError("cada no normalizable es un objeto")
        ajenas = set(f) - set(ESQUEMA_NO_NORMALIZABLES)
        if ajenas:
            raise ValueError(f"no normalizable con claves ajenas: {sorted(ajenas)}")
        salida.append({k: redactar(_na(f.get(k))) for k in ESQUEMA_NO_NORMALIZABLES})
    salida.sort(key=lambda f: tuple(str(f[k] or "") for k in ESQUEMA_NO_NORMALIZABLES))
    return _marco(salida, ESQUEMA_NO_NORMALIZABLES, "no_normalizables")


def _tablas_de_controles(controles: Any) -> Mapping[str, Any]:
    """controles["tablas"] (DataFrames de red.controles_red), buscado también un nivel más adentro."""
    if not isinstance(controles, Mapping):
        return {}
    tablas = controles.get(CLAVE_TABLAS_CONTROLES)
    if isinstance(tablas, Mapping):
        return tablas
    for v in controles.values():
        if isinstance(v, Mapping) and isinstance(v.get(CLAVE_TABLAS_CONTROLES), Mapping):
            return v[CLAVE_TABLAS_CONTROLES]
    return {}


def tabla_calibracion(controles: Any) -> pd.DataFrame:
    """calibracion_e3t.csv: la distribución de δt de red.calibrar_e3t (ESQUEMA_CALIBRACION + «fuera»)."""
    df = _tablas_de_controles(controles).get(CLAVE_CALIBRACION)
    if df is None:
        return tabla_vacia(ESQUEMA_CALIBRACION_CSV)
    if not isinstance(df, pd.DataFrame):
        raise ValueError("controles.tablas.calibracion_e3t no es un DataFrame")
    validar_esquema(df, ESQUEMA_CALIBRACION_CSV, nombre="calibracion_e3t")
    return df.reset_index(drop=True)


def _consecuencias(c: Any) -> dict:
    return {"a3_falla_pais": bool(c.a3_falla_pais), "a3_fallan_macrozonas": sorted(str(m) for m in c.a3_fallan_macrozonas),
            "a5_alto": bool(c.a5_alto), "modo_e3t": {str(k): str(v) for k, v in dict(c.modo_e3t).items()},
            "a4_restringe": None if c.a4_restringe is None else bool(c.a4_restringe)}


def controles_red(resultado: "ResultadoRed") -> dict:
    """controles_red.json: consecuencias fijadas (A3, A4, A5 y modo de E3t) y todos los controles, con las
    muestras como registros (columnas y filas)."""
    _exigir_resultado(resultado)
    return {"schema": ESQUEMA_CONTROLES, "consecuencias": _consecuencias(resultado.consecuencias),
            "controles": _controles_json(resultado.controles)}


def _controles_json(controles: Any) -> Any:
    """Los controles en JSON, con los textos de A7 redactados (vienen de excepciones; SAL-5)."""
    salida = _json(controles)
    if isinstance(salida, dict) and "A7" in salida:
        salida["A7"] = _redactar_todo(salida["A7"])
    return salida


def escribir_tablas(resultado: "ResultadoRed", carpeta: Path) -> dict[str, str]:
    """Escribe TABLAS (las de §7.4 y la del diagnóstico de reglas vencidas, SAL-19) en la carpeta de la
    corrida; devuelve nombre → sha256."""
    _exigir_resultado(resultado)
    carpeta = Path(carpeta)
    evidencias = _ordenadas(resultado.evidencias)
    contenidos: dict[str, Callable[[], bytes]] = {
        "pixeles_dmc.parquet": lambda: _bytes_parquet(tabla_pixeles(evidencias), "pixeles_dmc.parquet"),
        "evidencia_estacion_parte.parquet":
            lambda: _bytes_parquet(tabla_evidencia_parte(evidencias), "evidencia_estacion_parte.parquet"),
        "evidencia_estacion_anio.parquet":
            lambda: _bytes_parquet(tabla_evidencia_anio(resultado), "evidencia_estacion_anio.parquet"),
        "eventos_transicion.csv": lambda: _bytes_csv(tabla_eventos(evidencias), "eventos_transicion.csv"),
        "calibracion_e3t.csv": lambda: _bytes_csv(tabla_calibracion(resultado.controles), "calibracion_e3t.csv"),
        "controles_red.json": lambda: _bytes_json(controles_red(resultado), "controles_red.json"),
        "rachas.parquet": lambda: _bytes_parquet(tabla_rachas(resultado.rachas), "rachas.parquet"),
        "estados_largos.parquet":      # la tabla más grande: por trozos, una estación a la vez
            lambda: _bytes_parquet_por_trozos((ev.estados for ev in evidencias), ESQUEMA_ESTADOS,
                                              "estados_largos.parquet"),
        "no_normalizables.csv":
            lambda: _bytes_csv(tabla_no_normalizables(resultado.no_normalizables or ()), "no_normalizables.csv"),
        TABLA_REGLAS_VENCIDAS:     # mismo esquema de arrow que estados_largos
            lambda: _bytes_parquet_por_trozos((tabla_estados_reglas_vencidas(resultado),), ESQUEMA_ESTADOS,
                                              TABLA_REGLAS_VENCIDAS),
    }
    if tuple(contenidos) != TABLAS:
        raise RuntimeError("las tablas escritas no son las de §7.4 (más la de SAL-19)")
    return {nombre: entorno.escribir_atomico(carpeta / nombre, hacer()) for nombre, hacer in contenidos.items()}


# =========================================================================================================
# artefactos_evaluados.json.gz
# =========================================================================================================
def contenido_artefactos(artefactos: Iterable[Mapping]) -> list[dict]:
    """Lista validada y ordenada (SAL-16): cada objeto con al menos ``artefacto_sha256`` y ``codigo``."""
    salida, codigo_de = [], {}
    for item in artefactos:
        if not isinstance(item, Mapping):
            raise ValueError("cada artefacto evaluado es un objeto")
        ajenas = sorted(set(item) - set(CLAVES_ARTEFACTO))
        if ajenas:
            raise ValueError(f"artefacto evaluado con claves no admitidas {ajenas}: el archivo es público y "
                             "sólo identifica artefactos (SAL-16)")
        for clave in CLAVES_ARTEFACTO_OBLIGATORIAS:
            if clave not in item:
                raise ValueError(f"artefacto evaluado sin «{clave}»")
        sha, codigo = item["artefacto_sha256"], item["codigo"]
        if not isinstance(sha, str) or not _SHA.fullmatch(sha):
            raise ValueError("«artefacto_sha256» no es un sha256 de 64 hexadecimales en minúscula")
        if not isinstance(codigo, str) or not _CODIGO.fullmatch(codigo):
            raise ValueError(f"«codigo» distinto de 6 dígitos: {codigo!r}")
        if codigo_de.setdefault(sha, codigo) != codigo:
            raise ValueError("un mismo artefacto figura en dos estaciones")
        for clave in ("manifiesto", "artefacto"):
            ruta = item.get(clave)
            if ruta is not None and (not isinstance(ruta, str) or ruta.startswith("/")):
                raise ValueError(f"«{clave}» debe ser una ruta por alias")
        salida.append({k: _json(item[k]) for k in CLAVES_ARTEFACTO if k in item})
    if all("id_artefacto" in a for a in salida):
        ids = [a["id_artefacto"] for a in salida]
        if len(set(ids)) != len(ids):
            raise ValueError("«id_artefacto» repetido")
        salida.sort(key=lambda a: a["id_artefacto"])
    else:
        salida.sort(key=lambda a: (a["codigo"], a["artefacto_sha256"]))
    return salida


def escribir_artefactos_evaluados(artefactos: list[dict], carpeta: Path) -> str:
    """artefactos_evaluados.json.gz (gzip con mtime=0, JSON canónico); devuelve sha256."""
    datos = _bytes_json(contenido_artefactos(artefactos), ARCHIVO_ARTEFACTOS)
    comprimido = gzip.compress(datos, mtime=0)
    return entorno.escribir_atomico(Path(carpeta) / ARCHIVO_ARTEFACTOS, comprimido)


# =========================================================================================================
# Informe (§7.4)
# =========================================================================================================
def _exigir_shas(x: Any, donde: str) -> None:
    """SAL-14: toda clave «sha256» (o terminada en «_sha256») lleva 64 hexadecimales o None."""
    if isinstance(x, Mapping):
        for k, v in x.items():
            if isinstance(k, str) and (k == "sha256" or k.endswith("_sha256")) and v is not None:
                if not isinstance(v, str) or not _SHA.fullmatch(v):
                    raise ValueError(f"{donde}.{k}: no es un sha256 de 64 hexadecimales en minúscula")
            _exigir_shas(v, f"{donde}.{k}")
    elif isinstance(x, (list, tuple)):
        for i, v in enumerate(x):
            _exigir_shas(v, f"{donde}[{i}]")


def _resumir_tablas(controles: Any) -> Any:
    """SAL-15: los DataFrames de controles["tablas"] se resumen por su número de filas."""
    if not isinstance(controles, Mapping):
        return controles
    salida = {}
    for k, v in controles.items():
        if k == CLAVE_TABLAS_CONTROLES and isinstance(v, Mapping):
            salida[k] = {str(n): ({"n_filas": len(t), "en": "calibracion_e3t.csv" if n == CLAVE_CALIBRACION
                                   else "controles_red.json"} if isinstance(t, pd.DataFrame) else t)
                         for n, t in v.items()}
        elif isinstance(v, Mapping):
            salida[k] = _resumir_tablas(v)
        else:
            salida[k] = v
    return salida


def _tramo_json(t: Any) -> dict:
    if isinstance(t, Mapping):
        return _json(t)
    return {"id": t.id, "valid_from": _json(t.valid_from), "valid_to": _json(t.valid_to),
            "fixed_offset_minutes": int(t.fixed_offset_minutes), "clase": str(t.clase),
            "meses": [str(m) for m in t.meses]}


def _desde(t: Any) -> str:
    return str(_tramo_json(t)["valid_from"])


def _estacion_derivada(codigo: str, decisiones: Sequence, rachas: pd.DataFrame) -> dict:
    """SAL-11: la entrada de estación cuando la política no existe (A5 alto)."""
    confirmados = [d for d in decisiones if str(d.veredicto) == str(Veredicto.CONFIRMADO)]
    entrada: dict[str, Any] = {"derivada_de_las_decisiones": True}
    if not confirmados:
        entrada["veredicto"] = str(VeredictoEstacion.SIN_CONFIRMAR)
        return entrada
    r = rachas[(rachas["codigo"] == codigo) & rachas["aceptada"].astype(bool)].sort_values("racha")
    clases = [str(c) for c in r["clase"]] or list(dict.fromkeys(str(d.clase_confirmada) for d in confirmados))
    entrada.update(veredicto=str(VeredictoEstacion.CONFIRMADA), reloj=mod_politica.reloj_de_rachas(clases))
    return entrada


def _estaciones_informe(resultado, infos: Mapping, decisiones: Sequence) -> dict[str, dict]:
    """Entradas de §7.2 por estación (de la política, o de ``resultado.estaciones``; si no hay, SAL-11), con
    sus tramos, el veredicto de cada año y el número de meses con regla."""
    pol = resultado.politica
    de_pol = pol.get("estaciones", {}) if isinstance(pol, Mapping) else dict(getattr(resultado, "estaciones", None) or {})
    por_codigo: dict[str, list] = {}
    for d in decisiones:
        por_codigo.setdefault(str(d.codigo), []).append(d)
    salida = {}
    for codigo in sorted(set(infos) | set(por_codigo) | set(de_pol)):
        dec = sorted(por_codigo.get(codigo, []), key=lambda d: int(d.anio))
        entrada = (_json(de_pol[codigo]) if codigo in de_pol
                   else _estacion_derivada(codigo, dec, resultado.rachas))
        info = infos.get(codigo)
        if info is not None:
            entrada.setdefault("conjunto", str(info.conjunto))
        entrada["tramos"] = [_tramo_json(t) for t in sorted(resultado.tramos.get(codigo, ()), key=_desde)]
        entrada["anios"] = {f"{int(d.anio):04d}": {"veredicto": str(d.veredicto), "clase": d.clase_confirmada,
                                                   "motivo": None if d.motivo is None else str(d.motivo)}
                            for d in dec}
        entrada["meses_con_regla"] = len(dict(resultado.meses_con_regla.get(codigo, {})))
        salida[codigo] = entrada
    return salida


def _grupos(info: Any) -> dict[str, str]:
    if info is None:
        return {"macrozona": SIN_DATO, "territorio": SIN_DATO, "conjunto": SIN_DATO, "propietario": SIN_DATO,
                "tipo": SIN_DATO}
    return {"macrozona": str(info.macrozona), "territorio": str(info.territorio), "conjunto": str(info.conjunto),
            "propietario": SIN_DATO if info.propietario is None else str(info.propietario),
            "tipo": SIN_DATO if info.tipo is None else str(info.tipo)}


def _contar(pares: Iterable[tuple[str, str]]) -> dict:
    salida: dict[str, Counter] = {}
    for grupo, veredicto in pares:
        salida.setdefault(grupo, Counter())[veredicto] += 1
    return {g: dict(sorted(c.items())) for g, c in sorted(salida.items())}


def _conteos(decisiones: Sequence, infos: Mapping, estaciones: Mapping[str, dict]) -> dict:
    """§7.4: conteos por veredicto, macrozona, territorio, propietario y tipo (si el catálogo los trae) y conjunto."""
    criterios = ["macrozona", "territorio", "conjunto"]
    for opcional in ("propietario", "tipo"):
        if any(getattr(i, opcional) is not None for i in infos.values()):
            criterios.append(opcional)
    anios = [(_grupos(infos.get(str(d.codigo))), str(d.veredicto)) for d in decisiones]
    est = [(_grupos(infos.get(c)), str(e.get("veredicto"))) for c, e in estaciones.items()]
    return {"estacion_anios": {"total": dict(sorted(Counter(v for _, v in anios).items())),
                               **{f"por_{c}": _contar((g[c], v) for g, v in anios) for c in criterios}},
            "estaciones": {"total": dict(sorted(Counter(v for _, v in est).items())),
                           **{f"por_{c}": _contar((g[c], v) for g, v in est) for c in criterios}}}


_MOTIVOS_5_3 = (str(MotivoAnio.INESTABLE), str(MotivoAnio.CAMBIO_SIN_RESPALDO))


def _veredicto_5_1(d) -> tuple[str, str | None]:
    """El veredicto de §5.1 de una decisión final: §5.3 sólo deja sin confirmar (inestable o cambio sin
    respaldo) y conserva la clase, así que esos años eran «confirmado» (SAL-12, ORQ-4)."""
    if str(d.veredicto) == str(Veredicto.SIN_CONFIRMAR) and d.motivo is not None and str(d.motivo) in _MOTIVOS_5_3:
        return str(Veredicto.CONFIRMADO), d.clase_confirmada
    return str(d.veredicto), d.clase_confirmada


def _comparacion_e3t(decisiones: Sequence, restringidas: Sequence | None) -> dict:
    """SAL-12: la decisión de §5.1 con el modo de E3t de cada macrozona frente a la de E3t restringida en
    todas (ORQ-4 la calcula antes de §5.3)."""
    if restringidas is None:
        return {"calculada": False}
    alt = {_clave_decision(d): d for d in restringidas}
    cambian = []
    for d in decisiones:
        a = alt.get(_clave_decision(d))
        principal = _veredicto_5_1(d)
        if a is None or (str(a.veredicto), a.clase_confirmada) != principal:
            cambian.append({"codigo": str(d.codigo), "anio": int(d.anio),
                            "principal": {"veredicto": principal[0], "clase": principal[1]},
                            "e3t_restringida": None if a is None else {"veredicto": str(a.veredicto),
                                                                       "clase": a.clase_confirmada}})
    return {"calculada": True, "antes_de_5_3": True,
            "principal": dict(sorted(Counter(_veredicto_5_1(d)[0] for d in decisiones).items())),
            "e3t_restringida": dict(sorted(Counter(str(d.veredicto) for d in restringidas).items())),
            "cambian": cambian}


def _filas_de_meses(m: pd.DataFrame) -> list[tuple[str, bool, str | None]]:
    """(manifiesto, entra, motivo de exclusión) de cada fila de una tabla de meses (ESQUEMA_MES)."""
    return [(str(man), bool(entra), None if _na(motivo) is None else str(motivo))
            for man, entra, motivo in zip(m["manifiesto"], m["entra"], m["motivo_exclusion"])]


def _meses_de_la_corrida(evidencias: Sequence, meses: pd.DataFrame | None) -> tuple[pd.DataFrame, str]:
    """SAL-9: la tabla de meses sobre la que se cuentan las exclusiones, y su fuente.

    ``meses`` es la tabla completa de extraccion (``extraccion.leer_meses``), con todas las estaciones,
    también las que no tienen ningún mes evaluado. Debe traer cada mes de las evidencias con la misma
    admisión, y sus meses evaluados deben ser los de las evidencias. Sin ella, los meses de las evidencias."""
    propios = [ev.meses for ev in evidencias if ev.meses is not None]
    if meses is None:
        tabla = pd.concat(propios, ignore_index=True) if propios else tabla_vacia(ESQUEMA_MES)
        return tabla, FUENTE_EVIDENCIAS
    if not isinstance(meses, pd.DataFrame):
        raise ValueError("«meses» es la tabla de extraccion.leer_meses (ESQUEMA_MES)")
    validar_esquema(meses, ESQUEMA_MES, nombre="meses")
    filas = _filas_de_meses(meses)
    if len({f[0] for f in filas}) != len(filas):
        raise ValueError("la tabla de meses repite un manifiesto")
    completa = set(filas)
    de_evidencias = {f for m in propios for f in _filas_de_meses(m)}
    if not de_evidencias <= completa:
        raise ValueError("la tabla completa de meses no trae los meses de las evidencias con la misma admisión (SAL-9)")
    if {f for f in completa if f[1]} != {f for f in de_evidencias if f[1]}:
        raise ValueError("los meses evaluados de la tabla completa no son los de las evidencias (SAL-9)")
    return meses, FUENTE_EXTRACCION


def _exigir_artefactos_de_los_meses(artefactos: Sequence[Mapping], meses: pd.DataFrame) -> None:
    """artefactos_evaluados son exactamente los meses evaluados de la corrida (por artefacto_sha256)."""
    evaluados = meses.loc[meses["entra"].astype(bool), "artefacto_sha256"]
    if Counter(str(s) for s in evaluados) != Counter(str(a.get("artefacto_sha256")) for a in artefactos):
        raise ValueError("artefactos_evaluados no son los meses evaluados de la corrida (SAL-9, SAL-16)")


def _exclusiones(meses: pd.DataFrame, fuente: str) -> dict:
    """SAL-9: meses excluidos por versión, por estado u otros; meses con campos faltantes."""
    grupos = {"por_estado": Counter(), "por_version": Counter(), "otros": Counter()}
    lista, campos, n_campos = [], Counter(), 0
    m = meses
    for codigo, anio, mes, entra, motivo, faltan in zip(m["codigo"], m["anio"], m["mes"], m["entra"],
                                                        m["motivo_exclusion"], m["campos_faltantes"]):
        if not bool(entra):
            motivo = str(_na(motivo) or "sin_motivo")
            grupo = ("por_estado" if motivo in MOTIVOS_POR_ESTADO
                     else "por_version" if motivo in MOTIVOS_POR_VERSION else "otros")
            grupos[grupo][motivo] += 1
            lista.append({"codigo": str(codigo), "mes": _texto_mes(anio, mes), "motivo": motivo})
        faltan = _lista(faltan) or []
        if faltan:
            n_campos += 1
            campos.update(str(c) for c in faltan)
    return {"fuente": fuente, **{g: dict(sorted(c.items())) for g, c in grupos.items()},
            "meses_excluidos": sorted(lista, key=lambda f: (f["codigo"], f["mes"])),
            "con_campos_faltantes": {"meses": n_campos, "por_campo": dict(sorted(campos.items()))}}


def _validar_huellas_entrada(huellas_entrada: Mapping[str, object]) -> None:
    """SAL-14: todas las claves de CLAVES_HUELLAS y CLAVES_ENTRADAS; sha256 de 64 hexadecimales."""
    if not isinstance(huellas_entrada, Mapping):
        raise ValueError("las huellas de entrada son un diccionario (§7.4)")
    faltan = [k for k in CLAVES_HUELLAS + CLAVES_ENTRADAS if k not in huellas_entrada]
    if faltan:
        raise ValueError(f"huellas de entrada incompletas (§7.4): faltan {faltan}")
    _exigir_shas(dict(huellas_entrada), "huellas_entrada")


def _vacio(v: Any) -> bool:
    return v is None or (isinstance(v, (Mapping, list, tuple, str)) and len(v) == 0)


def faltantes(controles: Any, huellas_entrada: Mapping[str, object], meses: pd.DataFrame | None) -> list[str]:
    """SAL-21: lo que §7.4 pide en el informe y no llegó, como desviaciones (§10): cada control de
    CLAVES_CONTROLES ausente o None, cada huella o entrada None o vacía, y la tabla completa de meses."""
    controles = controles if isinstance(controles, Mapping) else {}
    salida = [f"falta el resultado de {k} (§7.4: «Resultados de A1 a A7, de G-dup y de la calibración»)"
              for k in CLAVES_CONTROLES if controles.get(k) is None]
    salida += [f"falta la huella de «{k}» (§7.4: huellas del informe y de las entradas)"
               for k in CLAVES_HUELLAS + CLAVES_ENTRADAS if _vacio(huellas_entrada.get(k))]
    if meses is None:
        salida.append(DESVIACION_SIN_MESES)
    return salida


def desviaciones_de_controles(controles: Any) -> list[str]:
    """SAL-22: diferencias de procedimiento que orquestacion deja en los controles y el informe lista entre las
    desviaciones (§10). Hoy, las líneas activas que el diagnóstico de reglas vencidas no recalcula con Cv
    (``controles["reglas_vencidas"]["lineas_sin_cv"]``, ORQ-3f); vacía, no da ninguna."""
    controles = controles if isinstance(controles, Mapping) else {}
    vencidas = controles.get(CLAVE_REGLAS_VENCIDAS)
    lineas = vencidas.get(CLAVE_LINEAS_SIN_CV) if isinstance(vencidas, Mapping) else None
    if not lineas:
        return []
    return [DESVIACION_LINEAS_SIN_CV.format(lineas=", ".join(sorted(str(x) for x in lineas)))]


def informe(resultado: "ResultadoRed", huellas_tablas: Mapping[str, str], huellas_entrada: Mapping[str, object],
            desviaciones: list[str], *, expedientes_abiertos: Mapping[str, Any] | None = None,
            meses: pd.DataFrame | None = None, modo_sintetico: bool = False) -> dict:
    """informe_reloj_dmc.json: huellas (protocolo, configuración, código, adaptador, intérprete, Anexos),
    entradas (manifiestos, progreso.json, catálogo, cada mes ERA5, copias de C2), A1 a A7, G-dup,
    calibración, exclusiones, veredictos y tramos, conteos por estrato y conjunto, §1.13 y desviaciones.

    ``huellas_tablas``: nombre → sha256 de TABLAS (y de expedientes/ y artefactos_evaluados, SAL-3).
    ``huellas_entrada``: CLAVES_HUELLAS y CLAVES_ENTRADAS (SAL-14); las demás claves van a ``otras_huellas``.
    ``expedientes_abiertos``: la salida de ``expedientes_a_abrir``. ``meses``: la tabla completa de
    extraccion.leer_meses (SAL-9). A ``desviaciones`` se agregan las de ``faltantes`` (SAL-21)."""
    _exigir_resultado(resultado)
    _validar_huellas_entrada(huellas_entrada)
    faltan = [n for n in TABLAS if n not in huellas_tablas]
    if faltan:
        raise ValueError(f"faltan las huellas de las tablas {faltan}")
    for nombre, sha in huellas_tablas.items():
        if not isinstance(sha, str) or not _SHA.fullmatch(sha):
            raise ValueError(f"huella de {nombre} no es un sha256")
    if not isinstance(desviaciones, (list, tuple)) or not all(isinstance(d, str) for d in desviaciones):
        raise ValueError("las desviaciones son una lista de textos")
    evidencias = _ordenadas(resultado.evidencias)
    tabla_meses, fuente_meses = _meses_de_la_corrida(evidencias, meses)
    automaticas = [d for d in faltantes(resultado.controles, huellas_entrada, meses)
                   + desviaciones_de_controles(resultado.controles) if d not in desviaciones]
    infos = {ev.info.codigo: ev.info for ev in evidencias}
    decisiones = sorted(resultado.decisiones, key=_clave_decision)
    estaciones = _estaciones_informe(resultado, infos, decisiones)
    a5_alto = bool(resultado.consecuencias.a5_alto)
    salida = {
        "schema": ESQUEMA_INFORME,
        "modo_sintetico": bool(modo_sintetico),
        "huellas": {k: _json(huellas_entrada[k]) for k in CLAVES_HUELLAS},
        "entradas": {k: _json(huellas_entrada[k]) for k in CLAVES_ENTRADAS},
        "otras_huellas": {str(k): _json(v) for k, v in huellas_entrada.items()
                          if k not in CLAVES_HUELLAS + CLAVES_ENTRADAS},
        "tablas": {str(k): v for k, v in sorted(huellas_tablas.items())},
        "controles": _controles_json(_resumir_tablas(resultado.controles)),
        "consecuencias": _consecuencias(resultado.consecuencias),
        "exclusiones": _exclusiones(tabla_meses, fuente_meses),
        "coordenadas_inconsistentes": sorted(c for c, i in infos.items() if i.coordenadas_inconsistentes),
        "estaciones": estaciones,
        "conteos": _conteos(decisiones, infos, estaciones),
        "comparacion_e3t_restringida": _comparacion_e3t(decisiones, resultado.decisiones_e3t_restringida),
        "descripcion_red": _json(resultado.descripcion_red),
        "predicciones_1_13": _json(resultado.predicciones),
        "no_normalizables": {"n": len(resultado.no_normalizables or ()), "archivo": "no_normalizables.csv"},
        "artefactos_evaluados": {"archivo": ARCHIVO_ARTEFACTOS, "sha256": huellas_tablas.get(ARCHIVO_ARTEFACTOS),
                                 "n": int(tabla_meses["entra"].astype(bool).sum())},
        "expedientes": None if expedientes_abiertos is None else _json(expedientes_abiertos),
        "politica": {"se_escribe": not a5_alto, "a5_alto": a5_alto,
                     "motivo": "A5 dio alto: no se escribe politica_reloj_dmc.json (§5.4)" if a5_alto else None},
        "desviaciones": [*desviaciones, *automaticas],
    }
    _exigir_privado(entorno.json_canonico(salida).decode("utf-8"), ARCHIVO_INFORME)
    return salida


# --- Informe legible -------------------------------------------------------------------------------------
def _celda(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, (list, tuple)):
        v = ", ".join(str(x) for x in v) if v else "—"
    elif isinstance(v, Mapping):
        v = _texto_json(v)
    return str(v).replace("|", "\\|").replace("\n", " ")


def _huella_corta(v: Any) -> str:
    if v is None:
        return "no aplica"
    if isinstance(v, str):
        return v
    if isinstance(v, Mapping) and "sha256" in v:
        return str(v["sha256"])
    return _texto_json(v)


def _bloque_json(x: Any) -> list[str]:
    return ["```json", json.dumps(x, ensure_ascii=False, sort_keys=True, indent=1), "```"]


def _estado_control(nombre: str, c: Any, cons: Mapping) -> str:
    """Resultado de un control en una frase (las consecuencias fijadas mandan en A3, A4, A5 y E3t)."""
    if nombre == "A3":
        if cons["a3_falla_pais"]:
            return "falla en el país"
        return f"falla en: {_celda(cons['a3_fallan_macrozonas'])}" if cons["a3_fallan_macrozonas"] else "sin falla"
    if nombre == "A4":
        return ("no calculado" if cons["a4_restringe"] is None
                else "E3t restringida en todo el país" if cons["a4_restringe"] else "no restringe")
    if nombre == "A5":
        return "alto: no se escribe la política" if cons["a5_alto"] else "sin alto"
    if nombre == CLAVE_CALIBRACION:
        modos: dict[str, list[str]] = {}
        for mz, modo in sorted(cons["modo_e3t"].items()):
            modos.setdefault(modo, []).append(mz)
        return "; ".join(f"{m}: {', '.join(z)}" for m, z in sorted(modos.items())) or "sin macrozonas"
    if isinstance(c, Mapping) and "pasa" in c:
        if c["pasa"] is None:
            motivo = (c.get("detalle") or {}).get("motivo") if isinstance(c.get("detalle"), Mapping) else None
            return "no evaluado" + (f" ({motivo})" if motivo else "")
        return "pasa" if c["pasa"] else "falla"
    if isinstance(c, Mapping) and "filas" in c:
        return f"{len(c['filas'])} caso(s)"
    if isinstance(c, list):
        return f"{len(c)} caso(s)"
    return "ver detalle" if c is not None else "no informado"


def informe_md(informe_: dict) -> str:
    """Versión legible de informe_reloj_dmc.json (la misma información; manda el JSON).

    Se genera desde la forma canónica del informe, así que el dict original y el JSON releído dan el mismo
    texto (``comprobar_cadena`` lo usa)."""
    i = json.loads(entorno.json_canonico(_json(informe_)))
    L = ["# Informe del procedimiento del reloj DMC (protocolo v1)", "",
         f"Esquema `{i['schema']}`. Esta versión se genera desde `{ARCHIVO_INFORME}`; si difieren, manda el JSON.", "",
         f"Modo sintético: {'sí' if i.get('modo_sintetico') else 'no'}.", ""]
    L += ["## Huellas", "", "| elemento | huella |", "|---|---|"]
    L += [f"| {k} | {_celda(_huella_corta(v))} |" for k, v in i["huellas"].items()]
    L += ["", "## Entradas", "", "| entrada | huella |", "|---|---|"]
    L += [f"| {k} | {_celda(_huella_corta(v))} |" for k, v in i["entradas"].items()]
    if i.get("otras_huellas"):
        L += ["", "Otras huellas:", ""] + _bloque_json(i["otras_huellas"])
    L += ["", "## Tablas (§7.4)", "", "| archivo | sha256 |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in i["tablas"].items()]
    c = i["consecuencias"]
    L += ["", "## Controles de red", "", "| control | resultado |", "|---|---|"]
    controles = i.get("controles") or {}
    for k in CLAVES_CONTROLES:
        L.append(f"| {k} | {_celda(_estado_control(k, controles.get(k), c))} |")
    L += ["", "G-dup y la calibración sólo describen; las consecuencias de A3, A4 y A5 quedan fijadas (§5.4).", "",
          "Detalle de los controles:", ""]
    L += _bloque_json(controles)
    x = i["exclusiones"]
    fuente = ("la tabla completa de meses de extraccion" if x.get("fuente") == FUENTE_EXTRACCION
              else "sólo los meses de las estaciones con algún mes evaluado")
    L += ["", "## Meses excluidos y coordenadas", "", f"- Contados sobre {fuente}.",
          f"- Por estado: {_celda(x['por_estado'])}.", f"- Por versión: {_celda(x['por_version'])}.",
          f"- Otros: {_celda(x['otros'])}.",
          f"- Meses con campos faltantes (no excluyen): {x['con_campos_faltantes']['meses']} "
          f"({_celda(x['con_campos_faltantes']['por_campo'])}).",
          f"- Estaciones con «coordenadas inconsistentes»: {_celda(i['coordenadas_inconsistentes'])}."]
    k = i["conteos"]
    L += ["", "## Conteos", "", f"- Estación-años por veredicto: {_celda(k['estacion_anios']['total'])}.",
          f"- Estaciones por veredicto: {_celda(k['estaciones']['total'])}.", ""]
    for nivel in ("estacion_anios", "estaciones"):
        for criterio, tabla in k[nivel].items():
            if criterio == "total":
                continue
            L += [f"**{nivel.replace('_', '-')} {criterio.replace('_', ' ')}**", "", "| grupo | conteos |", "|---|---|"]
            L += [f"| {_celda(g)} | {_celda(v)} |" for g, v in tabla.items()] + [""]
    L += ["## Veredictos y tramos por estación", "",
          "| código | conjunto | veredicto | reloj | motivo | tramos | meses con regla |", "|---|---|---|---|---|---|---|"]
    for codigo, e in i["estaciones"].items():
        tramos = "; ".join(f"{t['id']} [{t['valid_from']}, {t['valid_to']}] {t['fixed_offset_minutes']}"
                           for t in e.get("tramos", []))
        L.append(f"| {codigo} | {_celda(e.get('conjunto'))} | {_celda(e.get('veredicto'))} | {_celda(e.get('reloj'))} "
                 f"| {_celda(e.get('motivo'))} | {_celda(tramos or None)} | {e.get('meses_con_regla', 0)} |")
    comp = i["comparacion_e3t_restringida"]
    L += ["", "## Comparación con E3t restringida en todas las macrozonas (§5.2)", ""]
    if comp.get("calculada"):
        L += [f"- Principal: {_celda(comp['principal'])}.", f"- Con E3t restringida: {_celda(comp['e3t_restringida'])}.",
              f"- Estación-años que cambian: {len(comp['cambian'])}."]
    else:
        L.append("- No se calculó.")
    L += ["", "## Descripción de la red (§5.4)", ""] + _bloque_json(i["descripcion_red"])
    L += ["", "## Predicciones de §1.13", ""] + _bloque_json(i["predicciones_1_13"])
    a = i["artefactos_evaluados"]
    L += ["", "## Artefactos evaluados y no normalizables", "",
          f"- `{a['archivo']}`: {a['n']} artefactos, sha256 {a['sha256'] or '—'}.",
          f"- No normalizables (§7.3, comprobación 7): {i['no_normalizables']['n']} (`{i['no_normalizables']['archivo']}`)."]
    L += ["", "## Expedientes (§5.5)", ""]
    exp = i.get("expedientes")
    if exp:
        L += [f"- De discrepancias: {_celda(exp.get('discrepancias'))}.", f"- De control: {_celda(exp.get('control'))}."]
    else:
        L.append("- No informados.")
    p = i["politica"]
    L += ["", "## Política", "", f"- Se escribe `{ARCHIVO_POLITICA}`: {'sí' if p['se_escribe'] else 'no'}."
          + (f" {p['motivo']}" if p.get("motivo") else "")]
    L += ["", "## Desviaciones de procedimiento", ""]
    L += [f"- {_celda(d)}" for d in i["desviaciones"]] or ["- Ninguna."]
    return "\n".join(L) + "\n"


def escribir_informe(informe_: dict, carpeta: Path) -> tuple[str, str]:
    """informe_reloj_dmc.json (JSON canónico) e informe_reloj_dmc.md; devuelve sus sha256."""
    carpeta = Path(carpeta)
    sha_json = entorno.escribir_atomico(carpeta / ARCHIVO_INFORME, _bytes_json(informe_, ARCHIVO_INFORME))
    texto = informe_md(informe_)
    _exigir_privado(texto, ARCHIVO_INFORME_MD)
    sha_md = entorno.escribir_atomico(carpeta / ARCHIVO_INFORME_MD, texto.encode("utf-8"))
    return sha_json, sha_md


# =========================================================================================================
# Política de la corrida (SAL-2, SAL-13)
# =========================================================================================================
def _contenido_politica(pol: Mapping) -> dict:
    """Lo que decide la política, sin las huellas ni las marcas: estaciones (sin «tramos») y reglas con su
    tramo (SAL-13: las marcas son las de la corrida y se comparan aparte)."""
    reglas = []
    for r in pol.get("politicas_reloj", []):
        clock = dict(r["clock"])
        m = re.fullmatch(mod_politica.PATRON_SOURCE, str(clock.pop("source", "")))
        tramo = None
        if m is not None:
            _, _, _, tramo, _ = m.groups()    # informe, sha256, estación, tramo, protocolo
        reglas.append({**{k: r[k] for k in r if k != "clock"}, "clock": clock, "tramo": tramo})
    estaciones = {c: {k: v for k, v in dict(e).items() if k != mod_politica.CLAVE_TRAMOS_ESTACION}
                  for c, e in dict(pol.get("estaciones", {})).items()}
    tramos = {c: dict(e.get(mod_politica.CLAVE_TRAMOS_ESTACION) or {}) for c, e in dict(pol.get("estaciones", {})).items()
              if e.get(mod_politica.CLAVE_TRAMOS_ESTACION)}
    return {"estaciones": estaciones, "reglas": reglas, "tramos": tramos}


def politica_de_la_corrida(resultado: "ResultadoRed", huellas: mod_politica.HuellasPolitica, *,
                           post_hoc: bool = False, errata_post_c4: bool = False,
                           ajuste_documental: bool = False) -> dict | None:
    """SAL-13: la política de la corrida con las huellas reales (informe y artefactos evaluados) y las marcas
    de la corrida. None si A5 dio alto (§5.4).

    Si orquestacion ya la armó (``resultado.politica``), se rehace con politica.politica y su contenido
    (estaciones, intervalos, desfases y tramos) debe quedar igual; una marca que trae y la corrida no, se
    rechaza (una marca nunca se quita). Si la dejó en None porque no tenía huellas (ORQ-9), se arma con
    ``resultado.estaciones`` y ``resultado.tramos``."""
    _exigir_resultado(resultado)
    if resultado.consecuencias.a5_alto:
        return None
    marcas = {"post_hoc": post_hoc, "errata_post_c4": errata_post_c4, "ajuste_documental": ajuste_documental}
    tramos = {str(c): list(ts) for c, ts in dict(resultado.tramos).items()}
    pol = resultado.politica

    def armar(estaciones: Mapping) -> dict:
        try:
            return mod_politica.politica(tramos, estaciones, huellas, **marcas)
        except ValueError as e:   # su mensaje puede nombrar una estación y su veredicto
            raise ErrorRetenido("politica.politica rechazó los tramos o las estaciones de la fase 10", str(e)) from None

    if pol is None:
        estaciones = getattr(resultado, "estaciones", None)
        if not estaciones:
            raise ValueError("no hay política de la fase 10 ni «estaciones» para armarla (§7.2)")
        return armar(estaciones)
    quitadas = [k for k in mod_politica.MARCAS_POLITICA if bool(pol.get(k, False)) and not marcas[k]]
    if quitadas:
        raise ValueError(f"la política de la fase 10 lleva las marcas {quitadas} y la corrida no: una marca no se "
                         "quita (§10)")
    nueva = armar(pol["estaciones"])
    if _json(_contenido_politica(pol)) != _json(_contenido_politica(nueva)):
        raise ValueError("la política rehecha con las huellas de la corrida no coincide con la de la fase 10 "
                         "(estaciones, intervalos, desfases o tramos)")
    return nueva


def _sin_huella_de_informe(pol: Mapping) -> dict:
    p = copy.deepcopy(dict(pol))
    if isinstance(p.get("informe"), dict):
        p["informe"]["sha256"] = "<informe>"
    for r in p.get("politicas_reloj", []):
        if isinstance(r, dict) and isinstance(r.get("clock"), dict) and isinstance(r["clock"].get("source"), str):
            r["clock"]["source"] = _SHA_EN_SOURCE.sub(" sha256=<informe> ", r["clock"]["source"])
    return p


def diferencias_salvo_informe(provisional: Mapping, final: Mapping) -> list[str]:
    """SAL-2: claves de primer nivel en que difieren dos políticas, sin contar la huella del informe."""
    a, b = _sin_huella_de_informe(provisional), _sin_huella_de_informe(final)
    return sorted(k for k in set(a) | set(b) if _json(a.get(k)) != _json(b.get(k)))


# =========================================================================================================
# Expedientes (§5.5)
# =========================================================================================================
def expedientes_a_abrir(resultado: "ResultadoRed", semilla: int, n_control: int) -> dict[str, Any]:
    """SAL-7 y SAL-8: estaciones con algún año discrepante y muestra de control (con algún año confirmado)."""
    _exigir_resultado(resultado)
    discrepantes = sorted({str(d.codigo) for d in resultado.decisiones
                           if str(d.veredicto) == str(Veredicto.DISCREPANTE)})
    confirmadas = sorted({str(d.codigo) for d in resultado.decisiones
                          if str(d.veredicto) == str(Veredicto.CONFIRMADO)})
    control = decision.muestra_expedientes_control(confirmadas, int(semilla), int(n_control))
    return {"discrepancias": discrepantes, "control": list(control), "candidatos_control": len(confirmadas),
            "semilla": int(semilla), "n_control": int(n_control)}


def _figure(alto: float | None = None):
    from matplotlib.figure import Figure   # Agg sin pyplot: no toca el backend global
    return Figure(figsize=(_ANCHO, _ALTO if alto is None else alto), dpi=_DPI, layout="constrained")


def _png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=_DPI, metadata={"Software": None})
    return buf.getvalue()


def _sin_datos(ax, texto: str) -> None:
    ax.text(_CENTRO, _CENTRO, texto, ha="center", va="center", transform=ax.transAxes, fontsize=_LETRA)
    ax.set_xticks([])
    ax.set_yticks([])


def _etiquetas_filas(ax, etiquetas: Sequence[str]) -> None:
    paso = max(1, -(-len(etiquetas) // _MAX_ETIQUETAS))
    pos = list(range(0, len(etiquetas), paso))
    ax.set_yticks(pos)
    ax.set_yticklabels([etiquetas[p] for p in pos], fontsize=_LETRA)


def _eje_horas(ax) -> None:
    ax.set_xticks(list(range(0, HORAS_DIA, _PASO_HORAS)))
    ax.tick_params(labelsize=_LETRA)
    ax.set_xlabel("hora de etiqueta (L)", fontsize=_LETRA)


def _extracto_util(extracto: pd.DataFrame | None) -> pd.DataFrame | None:
    if extracto is None or not len(extracto):
        return None
    return extracto.sort_values("L", kind="mergesort").reset_index(drop=True)


def _cambios_reales(ev) -> list[tuple[date, str, str]]:
    """Cambios de hora reales de E1a y E1b de la estación: (fecha D, zona, tipo)."""
    if ev is None:
        return []
    e = ev.eventos
    sel = e[(e["clase_evento"] == str(ClaseEvento.REAL)) & e["linea"].isin([str(Linea.E1A), str(Linea.E1B)])]
    salida = set()
    for fecha, zona, tipo in zip(sel["fecha_D"], sel["zona"], sel["tipo"]):
        if _na(fecha) is not None:
            salida.add((date.fromisoformat(str(fecha)), str(zona), str(tipo)))
    return sorted(salida)


def _fig_marcas_por_hora(codigo: str, extracto: pd.DataFrame | None) -> bytes:
    fig = _figure()
    marcas = (("rr", "RR06"), ("tx", "TX"), ("tn", "TN"), ("observador", "observador (CL, CM o CH)"))
    ejes = fig.subplots(len(marcas) // 2, 2).ravel()
    fig.suptitle(f"{codigo}: marcas por hora de etiqueta y año", fontsize=_LETRA + 1)
    for ax, (col, titulo) in zip(ejes, marcas):
        ax.set_title(titulo, fontsize=_LETRA)
        if extracto is None or not bool(extracto[col].any()):
            _sin_datos(ax, "sin marcas")
            continue
        sel = extracto[extracto[col].astype(bool)]
        anios = sorted(int(a) for a in extracto["anio"].unique())
        tabla = pd.crosstab(sel["anio"].astype(int), sel["L"].dt.hour).reindex(
            index=anios, columns=range(HORAS_DIA), fill_value=0)
        im = ax.imshow(tabla.to_numpy(np.float64), aspect="auto", interpolation="nearest", cmap="viridis")
        _etiquetas_filas(ax, [str(a) for a in anios])
        _eje_horas(ax)
        fig.colorbar(im, ax=ax).ax.tick_params(labelsize=_LETRA)
    return _png(fig)


def _fig_dias_de_cambio(codigo: str, extracto: pd.DataFrame | None, cambios: Sequence[tuple[date, str, str]]) -> bytes:
    filas_n = len(cambios) * len(DESPLAZAMIENTOS_DIA)
    fig = _figure(max(_ALTO_MIN, _ALTO_FILA * filas_n))
    ax = fig.subplots()
    ax.set_title(f"{codigo}: etiquetas medidas por hora en D−1, D y D+1 de cada cambio de hora real",
                 fontsize=_LETRA + 1)
    if extracto is None or not cambios:
        _sin_datos(ax, "sin cambios de hora reales en los años con datos" if extracto is not None else "sin extracto")
        return _png(fig)
    med = extracto[extracto["medida"].astype(bool)]
    conteo = pd.crosstab(med["L"].dt.normalize(), med["L"].dt.hour).reindex(columns=range(HORAS_DIA), fill_value=0)
    matriz, etiquetas = [], []
    for fecha, zona, tipo in cambios:
        for k in DESPLAZAMIENTOS_DIA:
            dia = pd.Timestamp(fecha + timedelta(days=k))
            matriz.append(conteo.loc[dia].to_numpy(np.float64) if dia in conteo.index else np.zeros(HORAS_DIA))
            etiquetas.append(f"{fecha.isoformat()} {tipo} ({zona.split('/')[-1]}) D{k:+d}" if k else
                             f"{fecha.isoformat()} {tipo} ({zona.split('/')[-1]}) D")
    matriz = np.vstack(matriz)
    im = ax.imshow(matriz, aspect="auto", interpolation="nearest", cmap="viridis", vmin=0,
                   vmax=max(1.0, float(np.nanmax(matriz))))
    _etiquetas_filas(ax, etiquetas)
    _eje_horas(ax)
    fig.colorbar(im, ax=ax).ax.tick_params(labelsize=_LETRA)
    return _png(fig)


def _fig_ventanas(codigo: str, extracto: pd.DataFrame | None, cambios: Sequence[tuple[date, str, str]]) -> bytes:
    fig = _figure()
    ax = fig.subplots()
    ax.set_title(f"{codigo}: primera y última etiqueta medida de cada día (s_d, e_d)", fontsize=_LETRA + 1)
    med = None if extracto is None else extracto[extracto["medida"].astype(bool)]
    if med is None or not len(med):
        _sin_datos(ax, "sin etiquetas medidas")
        return _png(fig)
    por_dia = med.groupby(med["L"].dt.normalize())["L"].agg(["min", "max"])
    ax.plot(por_dia.index, por_dia["min"].dt.hour, ".", markersize=_PUNTO, label="primera (s_d)")
    ax.plot(por_dia.index, por_dia["max"].dt.hour, ".", markersize=_PUNTO, label="última (e_d)")
    for fecha, _, _ in cambios:
        ax.axvline(pd.Timestamp(fecha), color=_GRIS, linewidth=_LINEA)
    ax.set_ylim(-1, HORAS_DIA)
    ax.set_ylabel("hora de etiqueta", fontsize=_LETRA)
    ax.tick_params(labelsize=_LETRA)
    ax.legend(fontsize=_LETRA, loc="upper right")
    return _png(fig)


def _fig_r_por_mes(codigo: str, ev) -> bytes:
    fig = _figure()
    ejes = fig.subplots(1, len(VARIABLES_E3))
    fig.suptitle(f"{codigo}: r(c) de E3 por parte (≈ mes), con ĉ", fontsize=_LETRA + 1)
    m = None if ev is None else ev.metricas_e3
    for ax, variable in zip(ejes, VARIABLES_E3):
        ax.set_title(variable, fontsize=_LETRA)
        sel = None if m is None else m[(m["nivel"] == str(Nivel.PARTE)) & (m["variable"] == variable)]
        filas = [] if sel is None else sorted(
            ((str(u), _lista(r), _na(c)) for u, r, c in zip(sel["unidad"], sel["r"], sel["c_hat"]) if _lista(r)),
            key=lambda t: _orden_parte(t[0]))
        if not filas:
            _sin_datos(ax, "sin r(c)")
            continue
        n = max(len(r) for _, r, _ in filas)
        mitad = (n - 1) // 2
        matriz = np.full((len(filas), n), np.nan)
        for k, (_, r, _) in enumerate(filas):
            if len(r) == n:
                matriz[k] = np.array([np.nan if v is None else v for v in r], dtype=np.float64)
        im = ax.imshow(matriz, aspect="auto", interpolation="nearest", cmap="RdBu_r", vmin=-1, vmax=1,
                       extent=(-mitad - _CENTRO, mitad + _CENTRO, len(filas) - _CENTRO, -_CENTRO))
        con_c = [(c, k) for k, (_, _, c) in enumerate(filas) if c is not None]
        if con_c:
            ax.plot([c for c, _ in con_c], [k for _, k in con_c], "k.", markersize=_PUNTO)
        _etiquetas_filas(ax, [u for u, _, _ in filas])
        ax.set_xlabel("c (h)", fontsize=_LETRA)
        ax.tick_params(labelsize=_LETRA)
        fig.colorbar(im, ax=ax).ax.tick_params(labelsize=_LETRA)
    return _png(fig)


def _fig_ciclo_diario(codigo: str, extracto: pd.DataFrame | None) -> bytes:
    from matplotlib import colormaps
    fig = _figure()
    ejes = fig.subplots(1, 2)
    fig.suptitle(f"{codigo}: ciclo diario por hora de etiqueta y año (anomalía de la media del año)",
                 fontsize=_LETRA + 1)
    for ax, (col, titulo) in zip(ejes, (("ts", "Ts (°C)"), ("qfe", "QFE (hPa)"))):
        ax.set_title(titulo, fontsize=_LETRA)
        d = None if extracto is None else extracto[["anio", "L", col]].dropna()
        if d is None or not len(d):
            _sin_datos(ax, "sin valores")
            continue
        anios = sorted(int(a) for a in d["anio"].unique())
        mapa = colormaps["viridis"]
        for k, anio in enumerate(anios):
            g = d[d["anio"] == anio]
            medias = g.groupby(g["L"].dt.hour)[col].mean().reindex(range(HORAS_DIA))
            ax.plot(range(HORAS_DIA), (medias - medias.mean()).to_numpy(np.float64), linewidth=_LINEA,
                    color=mapa(k / max(1, len(anios) - 1)), label=str(anio))
        _eje_horas(ax)
        ax.legend(fontsize=_LETRA - 1, ncol=2, loc="best")
    return _png(fig)


def _figuras(codigo: str, ev, extracto: pd.DataFrame | None) -> dict[str, bytes]:
    extracto = _extracto_util(extracto)
    cambios = _cambios_reales(ev)
    figuras = {"marcas_por_hora": _fig_marcas_por_hora(codigo, extracto),
               "dias_de_cambio": _fig_dias_de_cambio(codigo, extracto, cambios),
               "ventanas": _fig_ventanas(codigo, extracto, cambios),
               "r_por_mes": _fig_r_por_mes(codigo, ev),
               "ciclo_diario": _fig_ciclo_diario(codigo, extracto)}
    if tuple(figuras) != FIGURAS:
        raise RuntimeError("las figuras del expediente no son las de §5.5")
    return figuras


_TITULOS_FIGURAS = {"marcas_por_hora": "Marcas por hora", "dias_de_cambio": "Días de cambio",
                    "ventanas": "Ventanas de operación", "r_por_mes": "r(c) por mes", "ciclo_diario": "Ciclo diario"}


def _tabla_md(encabezado: Sequence[str], filas: Sequence[Sequence[Any]]) -> list[str]:
    if not filas:
        return ["(ninguna)"]
    return (["| " + " | ".join(encabezado) + " |", "|" + "---|" * len(encabezado)]
            + ["| " + " | ".join(_celda(v) for v in f) + " |" for f in filas])


def _expediente_md(codigo: str, motivos: Sequence[str], abiertos: Mapping[str, Any], ev, decisiones: Sequence,
                   resultado) -> str:
    info = None if ev is None else ev.info
    dec = sorted(decisiones, key=lambda d: int(d.anio))
    texto_motivos = []
    if "discrepancia" in motivos:
        anios = [str(int(d.anio)) for d in dec if str(d.veredicto) == str(Veredicto.DISCREPANTE)]
        texto_motivos.append(f"discrepancia (años discrepantes: {', '.join(anios)})")
    if "control" in motivos:
        k = list(abiertos["control"]).index(codigo) + 1
        texto_motivos.append(f"control (muestra al azar de §5.5, semilla {abiertos['semilla']}, sorteo {k} de "
                             f"{len(abiertos['control'])} entre {abiertos['candidatos_control']} estaciones con algún "
                             "año confirmado)")
    L = [f"# Expediente {codigo}", "", f"Motivo de apertura: {'; '.join(texto_motivos)}.", "",
         "Los expedientes de discrepancias y los de control tienen el mismo contenido y la misma profundidad (§5.5).", ""]
    L += ["## Estación", ""]
    campos = ([] if info is None else [
        ("nombre", info.nombre), ("conjunto", str(info.conjunto)), ("territorio", str(info.territorio)),
        ("región", info.region), ("macrozona", info.macrozona), ("Zs", list(info.zs)), ("P", [_id(h) for h in info.P]),
        ("lat", info.lat), ("lon", info.lon), ("z_cat (m)", info.alt_m), ("píxel", info.pixel_id),
        ("distancia (km)", info.distancia_km), ("costera", info.costera), ("z_pix (m)", info.z_pix), ("Δz (m)", info.dz),
        ("coordenadas válidas", info.coordenadas_validas), ("coordenadas inconsistentes", info.coordenadas_inconsistentes),
        ("tipo", info.tipo), ("propietario", info.propietario)])
    L += _tabla_md(("campo", "valor"), campos)
    L += ["", "## Veredictos por año", ""]
    L += _tabla_md(("año", "veredicto", "motivo", "detalle", "clase confirmada", "K", "excluidas (H′ → líneas)",
                    "líneas de apoyo", "familias", "Q", "meses con apoyo", "meses con datos", "partes discordantes",
                    "guardas", "marcas", "reglas vencidas", "modo E3t"),
                   [(int(d.anio), str(d.veredicto), None if d.motivo is None else str(d.motivo), d.detalle,
                     d.clase_confirmada, list(d.K), _json(dict(d.excluidas)) or None, list(d.lineas_apoyo),
                     list(d.familias_apoyo), int(d.n_lineas_q), len(d.meses_con_apoyo), len(d.meses_con_datos),
                     list(d.partes_discordantes), _json(dict(d.guardas)) or None, _json(dict(d.marcas)) or None,
                     bool(d.reglas_vencidas), None if d.modo_e3t is None else str(d.modo_e3t)) for d in dec])
    L += ["", "## Estados anuales por línea y H", ""]
    filas_estados = []
    if ev is not None:
        e = ev.estados
        sel = e[e["nivel"] == str(Nivel.ANIO)]
        hs = list(dict.fromkeys([_id(h) for h in (info.P if info is not None else ())] + sorted(set(sel["H"]))))
        por: dict[tuple[int, str], dict[str, str]] = {}
        for anio, linea, regla, h, estado in zip(sel["anio"], sel["linea"], sel["regla"], sel["H"], sel["estado"]):
            por.setdefault((int(anio), _clave_linea(linea, regla)), {})[str(h)] = str(estado)
        filas_estados = [(a, l, *[v.get(h) for h in hs]) for (a, l), v in sorted(por.items())]
        L += _tabla_md(("año", "línea", *hs), filas_estados)
    else:
        L += _tabla_md(("año", "línea"), [])
    L += ["", "## Partes y unidades con reloj anómalo o discordantes", ""]
    filas_partes = []
    if ev is not None:
        e = ev.estados
        sel = e[e["reloj_anomalo"].astype(bool) | e["discordante"].astype(bool)]
        filas_partes = [(int(a), _clave_linea(l, r), str(n), str(u), str(h), str(s), bool(an), bool(di))
                        for a, l, r, n, u, h, s, an, di in zip(sel["anio"], sel["linea"], sel["regla"], sel["nivel"],
                                                                sel["unidad"], sel["H"], sel["estado"],
                                                                sel["reloj_anomalo"], sel["discordante"])]
    L += _tabla_md(("año", "línea", "nivel", "unidad", "H", "estado", "reloj anómalo", "discordante"), filas_partes)
    L += ["", "## Eventos de cambio de hora (E1a, E1b, E1c)", ""]
    filas_eventos = []
    if ev is not None:
        x = ev.eventos
        filas_eventos = [tuple(_na(v) for v in fila) for fila in x[["linea", "zona", "anio", "tipo", "clase_evento",
                                                                    "fecha_D", "etiqueta", "p", "resultado", "delta"]]
                         .itertuples(index=False, name=None)]
    L += _tabla_md(("línea", "zona", "año", "tipo", "clase", "fecha D", "etiqueta", "p", "resultado", "δ"), filas_eventos)
    L += ["", "## Rachas, tramos y meses con regla", ""]
    r = resultado.rachas[resultado.rachas["codigo"] == codigo].sort_values("racha")
    L += _tabla_md(("racha", "desde", "hasta", "clase", "confirmados", "aceptada", "motivo"),
                   [tuple(_na(v) for v in f) for f in r[["racha", "anio_desde", "anio_hasta", "clase", "n_confirmados",
                                                         "aceptada", "motivo"]].itertuples(index=False, name=None)])
    L += [""]
    tramos = [_tramo_json(t) for t in sorted(resultado.tramos.get(codigo, ()), key=_desde)]
    L += _tabla_md(("tramo", "desde", "hasta", "desfase (min)", "clase", "meses"),
                   [(t["id"], t["valid_from"], t["valid_to"], t["fixed_offset_minutes"], t["clase"], len(t["meses"]))
                    for t in tramos])
    meses = dict(resultado.meses_con_regla.get(codigo, {}))
    L += ["", f"Meses con regla: {len(meses)}" + (f" ({_celda(sorted(meses))})." if meses else ".")]
    L += ["", "## Figuras", ""]
    for nombre in FIGURAS:
        L += [f"### {_TITULOS_FIGURAS[nombre]}", "", f"![{_TITULOS_FIGURAS[nombre]}]({codigo}/{nombre}.png)", ""]
    return "\n".join(L)


def expedientes(resultado: "ResultadoRed", leer_extracto, carpeta: Path, semilla: int, n_control: int) -> list[str]:
    """expedientes/<código>.md con figuras para cada estación con algún año discrepante y para la muestra
    de control (decision.muestra_expedientes_control); misma profundidad en ambos.

    ``leer_extracto(código)`` devuelve el extracto de la estación (ESQUEMA_EXTRACTO_HORA), por ejemplo
    ``lambda c: extraccion.leer_extracto(destino, c)``. Escribe también expedientes/indice.json. Devuelve
    las rutas relativas de los .md, ordenadas."""
    _exigir_resultado(resultado)
    carpeta = Path(carpeta)
    abiertos = expedientes_a_abrir(resultado, semilla, n_control)
    evidencias = {ev.info.codigo: ev for ev in _ordenadas(resultado.evidencias)}
    por_codigo: dict[str, list] = {}
    for d in resultado.decisiones:
        por_codigo.setdefault(str(d.codigo), []).append(d)
    raiz = carpeta / CARPETA_EXPEDIENTES
    rutas = []
    for codigo in sorted(set(abiertos["discrepancias"]) | set(abiertos["control"])):
        motivos = [m for m, lista in (("discrepancia", abiertos["discrepancias"]), ("control", abiertos["control"]))
                   if codigo in lista]
        ev = evidencias.get(codigo)
        extracto = leer_extracto(codigo)
        for nombre, png in _figuras(codigo, ev, extracto).items():
            entorno.escribir_atomico(raiz / codigo / f"{nombre}.png", png)
        texto = _expediente_md(codigo, motivos, abiertos, ev, por_codigo.get(codigo, []), resultado)
        _exigir_privado(texto, f"expediente {codigo}")
        entorno.escribir_atomico(raiz / f"{codigo}.md", texto.encode("utf-8"))
        rutas.append(f"{CARPETA_EXPEDIENTES}/{codigo}.md")
    entorno.escribir_atomico(raiz / INDICE_EXPEDIENTES,
                             _bytes_json({"schema": ESQUEMA_INDICE_EXPEDIENTES, **abiertos}, INDICE_EXPEDIENTES))
    return sorted(rutas)


# =========================================================================================================
# Privacidad, sello y cadena
# =========================================================================================================
def _archivos(carpeta: Path) -> list[Path]:
    """Archivos de la carpeta, recursivo, sin seguir enlaces (los enlaces también se listan)."""
    salida = []
    for raiz, dirs, nombres in os.walk(carpeta, followlinks=False):
        base = Path(raiz)
        salida += [base / d for d in dirs if (base / d).is_symlink()]
        salida += [base / n for n in nombres]
    return sorted(salida, key=lambda p: p.relative_to(carpeta).as_posix())


def _textos_parquet(ruta: Path) -> str:
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    tabla = pq.read_table(ruta)
    partes = [k.decode("utf-8", "replace") + v.decode("utf-8", "replace")
              for k, v in (tabla.schema.metadata or {}).items()]
    for col in tabla.columns:
        t = col.type
        while pa.types.is_list(t) or pa.types.is_large_list(t):
            col = pc.list_flatten(col)
            t = col.type
        if pa.types.is_string(t) or pa.types.is_large_string(t):
            partes += [v for v in pc.unique(col).to_pylist() if v is not None]
    return "\n".join(partes)


def verificar_privacidad(carpeta: Path) -> list[str]:
    """Archivos de texto (json, md, csv, jsonl, txt), .gz descomprimidos y parquet del nivel superior que
    contienen «/Users/», «@», la carpeta personal o una ruta absoluta; también enlaces simbólicos y nombres
    con esos textos (SAL-5). Devuelve las rutas relativas, ordenadas."""
    carpeta = Path(carpeta)
    hallados = []
    for ruta in _archivos(carpeta):
        rel = ruta.relative_to(carpeta).as_posix()
        if ruta.is_symlink() or not _privado(rel):
            hallados.append(rel)
            continue
        sufijo = ruta.suffix.lower()
        try:
            if sufijo in EXTENSIONES_TEXTO:
                texto = ruta.read_bytes().decode("utf-8", errors="replace")
            elif sufijo == ".gz":
                texto = gzip.decompress(ruta.read_bytes()).decode("utf-8", errors="replace")
            elif sufijo == ".parquet" and ruta.parent == carpeta:
                texto = _textos_parquet(ruta)
            else:
                continue
        except (OSError, EOFError, ValueError):
            hallados.append(rel)        # no se pudo revisar: no se da por limpio
            continue
        if not _privado(texto):
            hallados.append(rel)
    return hallados


def huella_agregada(archivos: Mapping[str, str]) -> str:
    """SAL-3: sha256 del texto «sha256␣␣ruta\\n», una línea por archivo, ordenado por ruta."""
    texto = "".join(f"{sha}  {ruta}\n" for ruta, sha in sorted(archivos.items()))
    return entorno.sha256_bytes(texto.encode("utf-8"))


def _inventario(carpeta: Path, *, sub: str | None = None, excluir: Sequence[str] = (RECIBO,)) -> dict[str, str]:
    """ruta relativa (a la carpeta de la corrida) → sha256 de cada archivo regular. Error con un enlace
    simbólico o un «.part» (escritura incompleta)."""
    carpeta = Path(carpeta)
    base = carpeta if sub is None else carpeta / sub
    if not base.exists():
        return {}
    salida = {}
    for ruta in _archivos(base):
        rel = ruta.relative_to(carpeta).as_posix()
        if rel in excluir:
            continue
        if ruta.is_symlink() or not ruta.is_file():
            raise ValueError(f"{rel}: no es un archivo regular (enlace u otro tipo); no se sella")
        if ruta.name.endswith(SUFIJO_PARCIAL):
            raise ValueError(f"{rel}: escritura incompleta; no se sella")
        salida[rel] = entorno.sha256_archivo(ruta)
    return salida


def huella_carpeta(carpeta: Path, sub: str) -> str:
    """Huella agregada de una subcarpeta (expedientes/), con rutas relativas a la carpeta de la corrida."""
    return huella_agregada(_inventario(carpeta, sub=sub))


def sellar(carpeta: Path) -> str:
    """recibo_corrida.json con la sha256 de cada archivo y la total; devuelve la total (SAL-4)."""
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        raise FileNotFoundError("la carpeta de la corrida no existe")
    recibo = carpeta / RECIBO
    if recibo.exists() or recibo.with_name(RECIBO + SUFIJO_PARCIAL).exists():
        raise FileExistsError("la carpeta ya está sellada")
    privados = verificar_privacidad(carpeta)
    if privados:
        raise ValueError(f"no se sella: archivos con «/Users/», «@», la carpeta personal o rutas absolutas: {privados}")
    archivos = _inventario(carpeta)
    total = huella_agregada(archivos)
    contenido = {"schema": ESQUEMA_RECIBO, "carpeta": carpeta.name, "archivos": archivos, "n_archivos": len(archivos),
                 "formato_total": FORMATO_HUELLA_AGREGADA, "total_sha256": total}
    entorno.escribir_atomico(recibo, _bytes_json(contenido, RECIBO))
    return total


def verificar_sello(carpeta: Path) -> list[str]:
    """Diferencias entre la carpeta y su recibo (archivos que faltan, sobran o cambiaron, y la total)."""
    carpeta = Path(carpeta)
    try:
        recibo = json.loads((carpeta / RECIBO).read_bytes())
    except (OSError, ValueError):
        return ["la carpeta no tiene un recibo_corrida.json legible"]
    anotados = dict(recibo.get("archivos", {}))
    try:
        actuales = _inventario(carpeta)
    except ValueError as e:
        return [str(e)]
    fallas = [f"falta {r}" for r in sorted(set(anotados) - set(actuales))]
    fallas += [f"sobra {r}" for r in sorted(set(actuales) - set(anotados))]
    fallas += [f"cambió {r}" for r in sorted(set(anotados) & set(actuales)) if anotados[r] != actuales[r]]
    if recibo.get("total_sha256") != huella_agregada(anotados):
        fallas.append("la huella total del recibo no corresponde a sus archivos")
    return fallas


def comprobar_cadena(carpeta: Path) -> list[str]:
    """Relee la cadena tablas → informe → política → recibo; devuelve los eslabones rotos."""
    carpeta = Path(carpeta)
    fallas = verificar_sello(carpeta)
    try:
        inf_bytes = (carpeta / ARCHIVO_INFORME).read_bytes()
        inf = json.loads(inf_bytes)
    except (OSError, ValueError):
        return fallas + ["no hay informe legible"]
    sha_inf = entorno.sha256_bytes(inf_bytes)
    tablas = dict(inf.get("tablas", {}))
    for nombre in TABLAS:
        if nombre not in tablas:
            fallas.append(f"el informe no trae la huella de {nombre}")
    for nombre, sha in sorted(tablas.items()):
        if nombre == CLAVE_EXPEDIENTES:
            actual = huella_carpeta(carpeta, CARPETA_EXPEDIENTES)
        elif (carpeta / nombre).is_file():
            actual = entorno.sha256_archivo(carpeta / nombre)
        else:
            fallas.append(f"falta {nombre}, citada por el informe")
            continue
        if actual != sha:
            fallas.append(f"{nombre} no tiene la huella que cita el informe")
    try:
        if (carpeta / ARCHIVO_INFORME_MD).read_text(encoding="utf-8") != informe_md(inf):
            fallas.append("informe_reloj_dmc.md no corresponde al informe JSON")
    except OSError:
        fallas.append("falta informe_reloj_dmc.md")
    ruta_pol = carpeta / ARCHIVO_POLITICA
    se_escribe = bool(inf.get("politica", {}).get("se_escribe"))
    if se_escribe == bool(inf.get("consecuencias", {}).get("a5_alto")):
        fallas.append("el informe no es coherente: con A5 alto no hay política, y sin él sí (§5.4)")
    if ruta_pol.is_file():
        pol = json.loads(ruta_pol.read_bytes())
        if not se_escribe:
            fallas.append("hay política, pero el informe dice que no se escribe (A5 alto)")
        if pol.get("informe", {}).get("sha256") != sha_inf:
            fallas.append("la política no cita la huella del informe")
        ruta_art = carpeta / ARCHIVO_ARTEFACTOS
        sha_art = entorno.sha256_archivo(ruta_art) if ruta_art.is_file() else None
        if pol.get("artefactos_evaluados", {}).get("sha256") != sha_art:
            fallas.append("la política no cita la huella de artefactos_evaluados.json.gz")
        for regla in pol.get("politicas_reloj", []):
            m = re.fullmatch(mod_politica.PATRON_SOURCE, str(regla.get("clock", {}).get("source", "")))
            if m is None or m.group(2) != sha_inf:
                fallas.append(f"{regla.get('station_code')}: ``source`` no cita el informe")
    elif se_escribe:
        fallas.append("el informe dice que hay política, pero no está")
    if (carpeta / CARPETA_PROVISIONAL).exists():
        fallas.append("quedó la política provisional de §7.3")
    return fallas


# =========================================================================================================
# La cadena completa (fases 10 y 11)
# =========================================================================================================
def _a7_no_evaluado(motivo: str) -> dict:
    return {"control": "A7", "pasa": None, "detalle": {"evaluado": False, "motivo": motivo}}


def _borrar_provisional(carpeta: Path) -> None:
    raiz = Path(carpeta) / CARPETA_PROVISIONAL
    if not raiz.exists():
        return
    for ruta in sorted(raiz.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if ruta.is_dir() and not ruta.is_symlink():
            ruta.rmdir()
        else:
            ruta.unlink()
    raiz.rmdir()


def _con(resultado: Any, **cambios: Any) -> Any:
    """Copia del resultado con otros valores en algunos campos (sin tocar el original)."""
    if is_dataclass(resultado) and not isinstance(resultado, type):
        return replace(resultado, **cambios)
    otro = copy.copy(resultado)
    for k, v in cambios.items():
        setattr(otro, k, v)
    return otro


def escribir_corrida(resultado: "ResultadoRed", carpeta: Path, *, artefactos: Sequence[Mapping],
                     huellas_entrada: Mapping[str, object], huellas_politica: mod_politica.HuellasPolitica | None,
                     desviaciones: Sequence[str], leer_extracto, semilla: int, n_control: int,
                     verificar: Callable[[Path], tuple[Sequence[str], Sequence[Mapping]]] | None = None,
                     meses: pd.DataFrame | None = None, modo_sintetico: bool = False,
                     post_hoc: bool = False, errata_post_c4: bool = False,
                     ajuste_documental: bool = False) -> dict[str, Any]:
    """Escribe la corrida en el orden de la cadena y la sella:
    artefactos_evaluados → (§7.3 sobre la política provisional, SAL-2) → tablas y expedientes → informe →
    política → privacidad → recibo.

    ``verificar(ruta)`` corre las siete comprobaciones de §7.3 sobre la política releída de ``ruta`` y
    devuelve (fallas, no normalizables). El ejecutable lo arma así::

        def verificar(ruta):
            pol = json.loads(ruta.read_bytes())
            ctx = orquestacion.contexto_verificacion(resultado, pol, destino, rutas.dmc, adaptador=…,
                                                     preflight=…, dmc_features=…, tablas=…)
            return politica.verificar_politica(ruta, ctx), ctx.no_normalizables

    ``meses``: la tabla completa de extraccion.leer_meses(destino) (SAL-9). ``artefactos`` deben ser sus
    meses evaluados.

    Fuera del modo sintético (SAL-20), antes de escribir nada, exige: el verificador (salvo con A5 alto,
    que no tiene política ni §7.3), todos los controles de CLAVES_CONTROLES salvo A7 (que pone esta
    corrida), todas las huellas y entradas sin None y ``meses``. Con ``modo_sintetico=True`` se puede omitir
    cualquiera de ellos: queda en el informe y en las desviaciones (SAL-21), y sin verificador A7 queda «no
    evaluado». ``controles["A7"]`` y los no normalizables son siempre los del §7.3 de esta corrida.
    La política sale de ``politica_de_la_corrida`` (de ``resultado.politica`` o, si orquestacion la dejó en
    None por no tener huellas, de ``resultado.estaciones``), con las marcas de la corrida.
    Devuelve sólo huellas (nunca veredictos): nombre → sha256, más «total_sha256»."""
    _exigir_resultado(resultado)
    carpeta = Path(carpeta)
    if (carpeta / RECIBO).exists():
        raise FileExistsError("la carpeta ya está sellada")
    hay_politica = not resultado.consecuencias.a5_alto
    if hay_politica and huellas_politica is None:
        raise ValueError("sin A5 alto hay política, y faltan sus huellas (HuellasPolitica)")
    # Todo lo que se puede comprobar antes de escribir, se comprueba antes (los mensajes no traen veredictos).
    artefactos = list(artefactos)
    desviaciones = list(desviaciones)
    _validar_huellas_entrada(huellas_entrada)
    _exigir_privado(_texto_json(huellas_entrada), "huellas_entrada")
    _exigir_privado(_texto_json(desviaciones), "desviaciones")
    tabla_meses, _ = _meses_de_la_corrida(_ordenadas(resultado.evidencias), meses)
    _exigir_artefactos_de_los_meses(artefactos, tabla_meses)
    if not modo_sintetico:
        faltan = faltantes({**dict(resultado.controles or {}), "A7": "lo pone el §7.3 de esta corrida"},
                           huellas_entrada, meses)
        if hay_politica and verificar is None:
            faltan.append("falta el verificador de §7.3 (§5.2, fase 10)")
        if faltan:
            raise ValueError("fuera del modo sintético la corrida exige todo lo de §7.3 y §7.4; no se escribió "
                             "nada: " + "; ".join(faltan))
    marcas = {"post_hoc": post_hoc, "errata_post_c4": errata_post_c4, "ajuste_documental": ajuste_documental}
    resumen: dict[str, Any] = {}
    sha_art = escribir_artefactos_evaluados(artefactos, carpeta)
    resumen[ARCHIVO_ARTEFACTOS] = sha_art
    controles = dict(resultado.controles)
    no_normalizables: list = []      # sólo los del §7.3 de esta corrida (SAL-20)
    provisional = None
    try:
        if not hay_politica:
            controles["A7"] = _a7_no_evaluado("A5 dio alto: no se escribe la política (§5.4)")
        elif verificar is None:      # sólo en modo sintético
            controles["A7"] = _a7_no_evaluado("modo sintético: sin verificador de §7.3")
            desviaciones.append(DESVIACION_SIN_7_3)
        else:
            pol_prov = politica_de_la_corrida(resultado, replace(huellas_politica, informe_sha256=SHA_INFORME_PROVISIONAL,
                                                                 artefactos_evaluados_sha256=sha_art), **marcas)
            ruta_prov = carpeta / CARPETA_PROVISIONAL / ARCHIVO_POLITICA
            mod_politica.escribir_politica(pol_prov, ruta_prov)
            fallas, no_normalizables = verificar(ruta_prov)
            no_normalizables = list(no_normalizables)
            provisional = json.loads(ruta_prov.read_bytes())
            a7 = red.a7([redactar(f) for f in fallas])
            controles["A7"] = {"control": a7.control, "pasa": a7.pasa, "detalle": _redactar_todo(_json(a7.detalle))}
        r = _con(resultado, controles=controles, no_normalizables=no_normalizables)
        huellas_tablas = escribir_tablas(r, carpeta)
        abiertos = expedientes_a_abrir(r, semilla, n_control)
        expedientes(r, leer_extracto, carpeta, semilla, n_control)
        huellas_tablas[CLAVE_EXPEDIENTES] = huella_carpeta(carpeta, CARPETA_EXPEDIENTES)
        huellas_tablas[ARCHIVO_ARTEFACTOS] = sha_art
        resumen.update(huellas_tablas)
        inf = informe(r, huellas_tablas, huellas_entrada, desviaciones, expedientes_abiertos=abiertos, meses=meses,
                      modo_sintetico=modo_sintetico)
        resumen[ARCHIVO_INFORME], resumen[ARCHIVO_INFORME_MD] = escribir_informe(inf, carpeta)
        resumen[ARCHIVO_POLITICA] = None
        if hay_politica:
            final = politica_de_la_corrida(r, replace(huellas_politica, informe_sha256=resumen[ARCHIVO_INFORME],
                                                      artefactos_evaluados_sha256=sha_art), **marcas)
            resumen[ARCHIVO_POLITICA] = mod_politica.escribir_politica(final, carpeta / ARCHIVO_POLITICA)
            if provisional is not None:
                distintas = diferencias_salvo_informe(provisional, json.loads((carpeta / ARCHIVO_POLITICA).read_bytes()))
                if distintas:
                    raise RuntimeError(f"la política final difiere de la verificada en §7.3 en {distintas} (SAL-2)")
    finally:
        _borrar_provisional(carpeta)
    privados = verificar_privacidad(carpeta)
    if privados:
        raise ValueError(f"no se sella: archivos con «/Users/», «@», la carpeta personal o rutas absolutas: {privados}")
    resumen["total_sha256"] = sellar(carpeta)
    resumen[RECIBO] = entorno.sha256_archivo(carpeta / RECIBO)
    return resumen
