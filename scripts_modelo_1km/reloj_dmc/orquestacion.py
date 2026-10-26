"""El pipeline de §5.2, fases 4 a 10, común a --aplicar, a la batería D y a C3b/C3c.

``evaluar_estacion`` (fase 4) es pura por estación: arma el ContextoEstacion, anota partes y corre
todas las líneas activas, las guardas y las marcas precalculadas → EvidenciaEstacion.
``evaluar_red`` recorre las estaciones UNA POR UNA (no guarda extractos en memoria) y después:
fase 5 (red.controles_red), fase 6 (decision.pasos_1_a_6), fase 7 (red.a4 y red.fijar_a4), fase 8
(decision.pasos_7_a_9, A6 y el diagnóstico de reglas vencidas de §4.1.4), fase 9 (decision.rachas y la
marca «posible media horaria») y fase 10 (politica.tramos y, con las huellas, politica.politica).
Además calcula la comparación descriptiva con E3t restringida en todas las macrozonas (§5.2).
No escribe nada ni muestra veredictos: devuelve ResultadoRed; salidas.py y el ejecutable escriben.
``avance(fase, hechos, total)`` recibe sólo conteos, y la sucesión de llamadas no depende de los
veredictos (§5.2, «Sin veredictos a la vista»; ORQ-11).
Depende de: todos los módulos de ciencia (tablas, lineas_*, guardas, red, decision, politica), de
extraccion (sólo para leer los extractos ya escritos y marcar las coordenadas inconsistentes) y de fijados
(la huella del adaptador fijado en el contexto de §7.3).
Al final de la fase 10 arma las predicciones de §1.13 (red.predicciones, con las consecuencias y el
calendario; RED-10), que van al informe y nunca a las desviaciones.

Lecturas propias de este módulo (van al addendum de C1):
- ORQ-1. «Año con datos» = año con algún mes que entra (``meses.entra``) o con alguna fila en el
  extracto; «mes con datos», lo mismo por mes. Un régimen con datos es uno con alguna etiqueta del
  extracto que no es especial ni astilla (R-30), tenga la variable que tenga: la política se aplica a
  toda la fila, así que una fila con sólo RR06 también impide fusionar dos hipótesis que la separan.
- ORQ-2. Las clases (§2.3) se calculan con P sin Cv y se copian en ``EvidenciaEstacion.clases``; la
  decisión las lee de ahí.
- ORQ-3. Reglas vencidas (§4.1.4, Enmienda 1 E1-4), por estación y para los años del Anexo A2 en que la
  decisión final quedó discrepante (salvo por G-versión, que no depende de H y deja la marca en falso):
  a. P ampliado = P ∪ {Cv(Z)} para cada C(Z) de P;
  b. las partes de esos años se cortan además en las etiquetas especiales de Cv(Z, y) (las de
     ``TablasCalendario.cambios_reglas_vencidas``): como en R-08, la etiqueta especial de Cv no
     pertenece a ninguna parte y queda ``especial`` para todas las H del diagnóstico. Los años-régimen
     siguen siendo los de Zs (R0 y R1). El corte es la interfaz pública de tablas
     (``TablasCalendario.con_cortes_reglas_vencidas``, ola 4b);
  c. E1a, E1b, E1c y E2 evalúan Cv como cualquier H (lineas_registro, lectura 8). E1a, E1b y E1c se
     calculan con todos los años de la estación, porque sus patrones son de estación;
  d. E3t, E3p (gruesa y fina) y E4p no admiten Cv (tablas.desfase no la define). En cada unidad (parte
     o año-régimen) en que Cv tiene un desfase constante c, su estado es el de la H de P con desfase c
     en esa unidad: esas líneas dan el estado por desfase, y c ya está en P, así que el conjunto de
     desfases de la regla gruesa no cambia. Donde el desfase de Cv no es constante, Cv queda sin
     información («desfase_no_constante», como en E2). Las filas anuales de Cv salen de la regla anual
     de cada línea (§4.0 para la gruesa de E3p; la de e3_fina; LF-7 en E3t; LF-11 en E4p). Esas reglas
     piden «todos» los años-régimen finos (§4.3.4) o evaluables (§4.4, LF-7): si en uno que es fino o
     evaluable para P el desfase de Cv no es constante, Cv no puede quedar compatible en el año y queda
     sin información («desfase_no_constante»), salvo que sea incompatible en otro;
  e. el apagado de la regla fina es de estación: se calcula con las métricas del diagnóstico en los
     años pedidos y con las de la evidencia en los demás;
  f. [pide enmienda] E6 no evalúa Cv (sin información, «cv_sin_E6»): E1-4 pide recalcular «todas las
     líneas», pero lineas_fisicas.e6 no admite Cv y la sustitución de d no basta (el estado de una H en
     E6 depende de las H′ del conjunto). En C0 E6 está inactiva; antes de activarla hace falta una
     enmienda o Cv en lineas_fisicas.e6. Mientras, ``controles["reglas_vencidas"]["lineas_sin_cv"]``
     nombra las líneas activas que el diagnóstico no recalcula con Cv, para las desviaciones del informe;
  g. se aplican los pasos 2 a 4 de §5.1 con ``decision.marca_reglas_vencidas`` y las consecuencias de
     A3 de la macrozona. La marca sólo cambia la cuenta de inestabilidad; el año sigue discrepante.
- ORQ-4. La comparación con E3t restringida rehace los pasos 7 a 9 con ``modo_e3t`` restringido en
  todas las macrozonas y A4 igual; los pasos 1 a 6 no dependen del modo. Se informa por estación-año,
  antes de §5.3 (es la «decisión» de §5.1). A6 se aplica a las dos decisiones (ORQ-5), para que una
  diferencia que viene de A6 no se informe como si la causara el modo de E3t.
- ORQ-5. A6 (con el registro documental que se pase; vacío con E5 inactiva) se aplica después del paso
  9 y antes de las rachas (R-47), a la decisión principal y a la restringida.
- ORQ-6. «Posible media horaria» (§4.3.5) después de §5.3, en las estaciones con algún año confirmado; con la
  Enmienda 3 (B6) ρ usa todos los años-régimen de la estación, no sólo los confirmados (LF-18). Calcularla
  sólo ahí no agrega una condición al texto: §7.2 pone «marcas» sólo en las entradas «confirmada» (con algún
  tramo, y un tramo sale de meses con regla de años confirmados); una estación sin años confirmados queda
  «sin_confirmar», sin «marcas», en la política y en el informe (también en la entrada derivada de SAL-11),
  así que su valor no llega a ninguna salida. «Reloj no
  verificado» lista, por año confirmado, las variables marcadas por G-HR («Td», «relative_humidity») y
  por G-viento («wind_speed_instant», «wind_direction_instant»), con los nombres de campo de §3.2.
- ORQ-7. En ``estaciones`` de la política: «confirmada» si la estación tiene algún tramo; su «reloj» es
  la sucesión de los relojes de las rachas con tramos (R-25), comparados por intersección de clases como
  en §5.3.1: rachas consecutivas con intersección no vacía (separadas por un año discrepante o
  insuficiente, sin cambio de reloj) son un solo término, con su intersección, y «→» va sólo donde la
  intersección es vacía, que es el cambio de §5.3.3 (R-25: «F(-4)→F(0)»). La regla es una sola,
  ``politica.reloj_de_rachas``, que salidas usa también sin política (SAL-11). Una estación sin tramos
  queda «sin_confirmar» con «motivo» = «inestable», o el veredicto anual más grave que tenga
  (discrepante > insuficiente > sin_confirmar > sin_datos), o «sin_meses_con_regla» si tuvo años
  confirmados pero ningún mes con regla; «detalle» trae el veredicto de cada año.
- ORQ-8. Las etiquetas de un tramo son todas las filas del extracto de sus meses con regla (cada fila
  es una etiqueta con dato de un artefacto evaluado).
- ORQ-9. Con A5 alto no se arma la política (``ResultadoRed.politica`` = None); los tramos y el resto
  del informe sí. Sin ``huellas`` tampoco se arma: el informe va antes que la política (§7.4) y su
  sha256 entra a ``source``; ``politica_de`` la arma después.
- ORQ-10 [pide enmienda]. §8, punto 16: «un aeródromo UTC, sin E4p, queda insuficiente, salvo con E3t en
  modo completo». Pero el filtro de §4.3.3 usa días de etiqueta con ≥ 20 valores (p = 1): un aeródromo
  de 11 a 23 h (13 valores por día) nunca lo pasa y E3t queda sin información aun en modo completo. La
  prueba C.16 muestra el rescate con un aeródromo de 20 h (sin E4p por su hueco de 5 h) y deja anotado
  que el de 13 h sigue insuficiente.
- ORQ-11. «Sin veredictos a la vista» (§5.2) vale también para la segunda pasada por la fábrica (reglas
  vencidas y etiquetas de los tramos): corre según las opciones (diagnóstico activo o etiquetas sin
  conservar), nunca según los veredictos; informa ``avance("segunda_pasada", k, n)`` por cada estación
  leída, con n = estaciones de la primera pasada, y exige que vuelvan todas. Sus errores no dependen de
  los veredictos: valida toda entrada como la fase 4, y si la fábrica no trae las mismas estaciones el
  error da sólo conteos, nunca códigos. El tiempo de la fase sí depende de los años diagnosticados: no
  se muestra (``ResultadoRed.tiempos`` no entra a las salidas, SAL-17).
- ORQ-12. Circularidad entre §7.3 y §7.4: §7.3 se corre sobre el JSON releído, la política lleva la
  sha256 del informe y el informe trae A7 y ``no_normalizables.csv``. Lectura (la de salidas, SAL-2):
  §7.3 corre sobre una política provisional, idéntica salvo ``informe.sha256`` y el «sha256=» de cada
  ``source`` (que ninguna comprobación usa), antes de las tablas y del informe; la final se compara con la
  provisional antes del sello.
- ORQ-13 [Enmienda 3, E3-2, opción A′, adoptada el 2026-10-24]. En la fase 9, ``decision.rachas`` recibe
  ``patron_regla_vencida`` = lineas_registro.patron_regla_vencida(evidencia.estados) («E1a señala reloj
  anómalo en algún año», que E1a sólo hace con el patrón de regla vencida; lineas_registro, lectura 9).
  El diagnóstico de §4.1.4 (ORQ-3) no cambia: en un año con ese reloj anómalo, P ∪ {Cv} sigue con E1a
  anómala y el año no lleva la marca.
- Orden para el ejecutable (el de salidas.escribir_corrida): evaluar_red → salidas.escribir_corrida(…,
  verificar=verificador_7_3(…)): artefactos_evaluados → §7.3 sobre la política provisional (A7 y no
  normalizables) → tablas y expedientes → informe → política final con las huellas reales → privacidad →
  sello. ``comprobar_politica`` no es parte de esa cadena: sólo sirve para pruebas y diagnósticos.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Iterator, Mapping, Sequence

import numpy as np
import pandas as pd

from reloj_dmc import constantes, decision, extraccion, fijados, guardas, lineas_fisicas, lineas_registro
from reloj_dmc import estados as mod_estados
from reloj_dmc import politica as mod_politica
from reloj_dmc import red
from reloj_dmc import tablas as mod_tablas
from reloj_dmc.tipos import (ESQUEMA_ESTADOS, ESQUEMA_EVENTOS, ESQUEMA_EXTRACTO_HORA, ESQUEMA_GUARDAS, ESQUEMA_HORAS,
                             ESQUEMA_ISD, ESQUEMA_MARCAS, ESQUEMA_MES, ESQUEMA_METRICAS_E2, ESQUEMA_METRICAS_E3,
                             ESQUEMA_METRICAS_E4, ESQUEMA_RACHAS, ConsecuenciasRed, ContextoEstacion, DecisionAnio,
                             Estado, EvidenciaEstacion, Hipotesis, InfoEstacion, Linea, ModoE3t, MotivoAnio,
                             MotivoSinInfo, Nivel, Regla, SerieEra5, Tramo, Veredicto, VeredictoEstacion,
                             tabla_vacia, validar_esquema)
from reloj_dmc.umbrales import Umbrales

LINEAS_ACTIVAS_C0 = frozenset({Linea.E1A, Linea.E1B, Linea.E1C, Linea.E2, Linea.E3T, Linea.E3P, Linea.E4P,
                               Linea.E3D, Linea.P7, Linea.TP, Linea.E4T, Linea.G_VERSION, Linea.G_HR,
                               Linea.G_VIENTO})   # decisiones de C0: sin E5 (red) ni E6
LINEAS_C3B = frozenset({Linea.E1A, Linea.E3P, Linea.E3T, Linea.E4P, Linea.E3D, Linea.P7, Linea.TP, Linea.E4T})

GUARDAS_PRECALCULADAS = (Linea.E3D, Linea.P7, Linea.TP, Linea.E4T, Linea.G_VERSION)
LINEAS_FISICAS_DIAGNOSTICO = frozenset({Linea.E3T, Linea.E3P, Linea.E4P, Linea.E6})
MARCAS_PRECALCULADAS = (Linea.G_HR, Linea.G_VIENTO, Linea.TP)     # T-P deja la marca térmica local

# Fases de §5.2 que informa ``avance`` (sólo conteos). «segunda_pasada»: reglas vencidas y etiquetas de
# los tramos (ORQ-11).
FASES = ("estados", "controles_red", "pasos_1_a_6", "A4", "pasos_7_a_9", "segunda_pasada", "rachas", "politica")
# Líneas que el diagnóstico de reglas vencidas no recalcula con Cv (ORQ-3f [pide enmienda]).
LINEAS_SIN_CV = frozenset({Linea.E6})

MOTIVO_DESFASE_CV = lineas_registro.MOTIVO_DESFASE     # «desfase_no_constante» (ORQ-3d)
MOTIVO_CV_SIN_E6 = "cv_sin_E6"                          # ORQ-3f
MOTIVO_SIN_MESES_CON_REGLA = "sin_meses_con_regla"      # ORQ-7
SEPARADOR_RACHAS = mod_politica.SEPARADOR_RACHAS        # «F(-4)→F(0)» (R-25)
SEPARADOR_CLASE = mod_politica.SEPARADOR_CLASE          # «F(-3)|C(Santiago)»
# ORQ-6: campos de §3.2 que llevan la marca «reloj no verificado».
VARIABLES_MARCA = {str(Linea.G_HR): ("Td", "relative_humidity"),
                   str(Linea.G_VIENTO): ("wind_speed_instant", "wind_direction_instant")}
_GRAVEDAD = (Veredicto.DISCREPANTE, Veredicto.INSUFICIENTE, Veredicto.SIN_CONFIRMAR, Veredicto.SIN_DATOS)
_INFORMATIVOS = (str(Estado.COMPATIBLE), str(Estado.INCOMPATIBLE))
_ESQUEMA_ANOTADO = {**ESQUEMA_EXTRACTO_HORA, "parte": "string", "regimen": "string", "especial": "bool"}


@dataclass(frozen=True)
class EntradaEstacion:
    info: InfoEstacion
    extracto: pd.DataFrame          # ESQUEMA_EXTRACTO_HORA
    meses: pd.DataFrame             # ESQUEMA_MES de la estación
    isd: pd.DataFrame | None = None # ESQUEMA_ISD (sólo con E6 activa)


@dataclass(frozen=True)
class OpcionesCorrida:
    lineas_activas: frozenset[Linea] = LINEAS_ACTIVAS_C0
    aplicar_exclusion_costera: bool = True
    remuestreo: bool = True                    # §4.0: obligatorio; False se rechaza (ninguna línea lo admite)
    comparacion_e3t_restringida: bool = True
    diagnostico_reglas_vencidas: bool = True
    # Guarda en memoria las etiquetas de cada estación (datetime64[h]) en la fase 4, para no volver a
    # recorrer la fábrica por los tramos. Útil con entradas en memoria (batería); en --aplicar, False.
    conservar_etiquetas: bool = False


@dataclass
class ResultadoRed:
    evidencias: list[EvidenciaEstacion]
    consecuencias: ConsecuenciasRed
    controles: dict
    decisiones: list[DecisionAnio]
    decisiones_e3t_restringida: list[DecisionAnio] | None
    rachas: pd.DataFrame
    meses_con_regla: Mapping[str, Mapping[str, str]]
    tramos: Mapping[str, list]
    politica: dict | None                       # None si A5 dio alto (o sin huellas; ORQ-9)
    descripcion_red: dict
    predicciones: dict
    no_normalizables: list = field(default_factory=list)
    # Agregados de la ola 3 (orquestacion):
    estaciones: dict = field(default_factory=dict)              # «estaciones» de §7.2 (ORQ-7), sin «tramos»
    resultados_rachas: dict = field(default_factory=dict)       # código → decision.ResultadoRachas
    estados_reglas_vencidas: pd.DataFrame | None = None         # ESQUEMA_ESTADOS del diagnóstico (P ∪ Cv)
    tiempos: dict = field(default_factory=dict)                 # segundos por fase y por estación-año


# ---------------------------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------------------------
def _unir(marcos: Sequence[pd.DataFrame | None], esquema: Mapping[str, str], nombre: str) -> pd.DataFrame:
    marcos = [m for m in marcos if m is not None and len(m)]
    if not marcos:
        return tabla_vacia(esquema)
    salida = pd.concat([m[list(esquema)] for m in marcos], ignore_index=True).astype(dict(esquema))
    if "valor" in esquema:              # ESQUEMA_MARCAS: los valores (None, NaN, bool, número) van tal cual
        salida["valor"] = pd.Series([v for m in marcos for v in m["valor"]], dtype="object")
    validar_esquema(salida, esquema, nombre=nombre)
    return salida


def _texto_mes(anio: int, mes: int) -> str:
    return f"{int(anio):04d}-{int(mes):02d}"


def _validar_entrada(entrada: EntradaEstacion) -> None:
    codigo = entrada.info.codigo
    validar_esquema(entrada.extracto, ESQUEMA_EXTRACTO_HORA, nombre=f"extracto {codigo}")
    validar_esquema(entrada.meses, ESQUEMA_MES, nombre=f"meses {codigo}")
    otros = sorted(set(entrada.meses["codigo"].dropna()) - {codigo})
    if otros:
        raise ValueError(f"{codigo}: meses de otras estaciones {otros}")
    if entrada.isd is not None:
        validar_esquema(entrada.isd, ESQUEMA_ISD, nombre=f"ISD {codigo}")
    L = entrada.extracto["L"]
    if L.isna().any() or not L.is_monotonic_increasing or L.duplicated().any():
        raise ValueError(f"{codigo}: el extracto debe venir ordenado por L y sin duplicados (§2.3 del diseño)")


def _validar_opciones(opciones: OpcionesCorrida) -> None:
    if not opciones.remuestreo:
        raise ValueError("el remuestreo de §4.0 no es opcional: ninguna línea admite remuestreo=False")
    desconocidas = [x for x in opciones.lineas_activas if not isinstance(x, Linea)]
    if desconocidas:
        raise ValueError(f"líneas activas que no son tipos.Linea: {desconocidas}")


def _anios_y_meses(extracto: pd.DataFrame, meses: pd.DataFrame) -> dict[int, tuple[int, ...]]:
    """ORQ-1: año → meses con datos (manifiesto que entra o filas en el extracto)."""
    por_anio: dict[int, set[int]] = {}
    entran = meses[meses["entra"].fillna(False).astype(bool)]
    for a, m in zip(entran["anio"], entran["mes"]):
        por_anio.setdefault(int(a), set()).add(int(m))
    for a, m in set(zip(extracto["anio"].tolist(), extracto["mes"].tolist())):
        por_anio.setdefault(int(a), set()).add(int(m))
    return {a: tuple(sorted(ms)) for a, ms in sorted(por_anio.items())}


def _contexto(anotado: pd.DataFrame, entrada: EntradaEstacion, info: InfoEstacion, calendario: object,
              umbrales: Umbrales, opciones: OpcionesCorrida) -> ContextoEstacion:
    """ContextoEstacion sobre un extracto ya anotado; las clases se fusionan con P sin Cv (ORQ-2)."""
    meses_con_datos = _anios_y_meses(entrada.extracto, entrada.meses)
    anios = tuple(meses_con_datos)
    zs = tuple(info.zs)
    regimenes = {a: mod_tablas.regimenes_del_anio(zs, a, calendario) for a in anios}
    usa = (~anotado["especial"].to_numpy(dtype=bool)) & anotado["regimen"].notna().to_numpy(dtype=bool)
    con_datos: dict[int, set[str]] = {}
    for a, r in set(zip(anotado.loc[usa, "anio"].tolist(), anotado.loc[usa, "regimen"].tolist())):
        con_datos.setdefault(int(a), set()).add(str(r))
    regimenes_con_datos = {a: tuple(sorted(con_datos.get(a, ()))) for a in anios}
    P_fijo_civil = tuple(h for h in info.P if h.tipo in ("F", "C"))
    clases = {}
    for a in anios:
        regs = [r for r in regimenes[a] if r.id in regimenes_con_datos[a]]
        clases[a] = mod_tablas.fusionar(P_fijo_civil, regs, zs)
    return ContextoEstacion(info=info, tablas=calendario, umbrales=umbrales, anios=anios, regimenes=regimenes,
                            regimenes_con_datos=regimenes_con_datos, clases=clases,
                            meses_con_datos=meses_con_datos, lineas_activas=frozenset(opciones.lineas_activas),
                            aplicar_exclusion_costera=bool(opciones.aplicar_exclusion_costera))


def _preparar(entrada: EntradaEstacion, tablas: object, umbrales: Umbrales,
              opciones: OpcionesCorrida) -> tuple[pd.DataFrame, ContextoEstacion]:
    _validar_opciones(opciones)
    _validar_entrada(entrada)
    anotado = mod_tablas.anotar_partes(entrada.extracto, entrada.info, tablas)
    validar_esquema(anotado, _ESQUEMA_ANOTADO, nombre=f"extracto anotado {entrada.info.codigo}")
    return anotado, _contexto(anotado, entrada, entrada.info, tablas, umbrales, opciones)


def contexto_estacion(entrada: EntradaEstacion, tablas: object, umbrales: Umbrales,
                      opciones: OpcionesCorrida) -> ContextoEstacion:
    """Años con datos, regímenes (todos y con datos), clases por año (§2.3), meses con datos y líneas
    activas de una estación (ORQ-1, ORQ-2)."""
    return _preparar(entrada, tablas, umbrales, opciones)[1]


def _horas(extracto: pd.DataFrame, codigo: str) -> pd.DataFrame:
    """ESQUEMA_HORAS: etiquetas con Ts o QFE por mes (denominadores de §5.4)."""
    ts = extracto["ts"].to_numpy(dtype=np.float64, na_value=np.nan)
    qfe = extracto["qfe"].to_numpy(dtype=np.float64, na_value=np.nan)
    con = np.isfinite(ts) | np.isfinite(qfe)
    if not con.any():
        return tabla_vacia(ESQUEMA_HORAS)
    cuentas = extracto.loc[con].groupby(["anio", "mes"], sort=True).size()
    filas = [{"codigo": codigo, "anio": int(a), "mes": int(m), "horas_ts_o_qfe": int(n)}
             for (a, m), n in cuentas.items()]
    return pd.DataFrame(filas, columns=list(ESQUEMA_HORAS)).astype(ESQUEMA_HORAS)


# ---------------------------------------------------------------------------------------------
# Fase 4: estados de las líneas de una estación
# ---------------------------------------------------------------------------------------------
@dataclass
class _Lineas:
    estados: list[pd.DataFrame] = field(default_factory=list)
    eventos: list[pd.DataFrame] = field(default_factory=list)
    metricas_e2: pd.DataFrame | None = None
    metricas_e3: list[pd.DataFrame] = field(default_factory=list)
    metricas_e4: list[pd.DataFrame] = field(default_factory=list)      # QFE y Ts (van a la evidencia)
    metricas_e4_hr: pd.DataFrame | None = None


def _con_fino(metricas_qfe: pd.DataFrame, metricas_fina: pd.DataFrame | None) -> pd.DataFrame:
    """Métricas de QFE con ``fino`` tal como lo recalculó e3_fina en los años-régimen."""
    if metricas_fina is None or not len(metricas_fina) or not len(metricas_qfe):
        return metricas_qfe
    fino = {(int(a), str(u)): bool(f) for a, u, f in zip(metricas_fina["anio"], metricas_fina["unidad"],
                                                         metricas_fina["fino"])}
    salida = metricas_qfe.copy()
    regs = salida["nivel"] == str(Nivel.REGIMEN)
    salida.loc[regs, "fino"] = [fino.get((int(a), str(u)), bool(f)) for a, u, f in
                                zip(salida.loc[regs, "anio"], salida.loc[regs, "unidad"], salida.loc[regs, "fino"])]
    return salida.astype(ESQUEMA_METRICAS_E3)


def _lineas_registro(anotado: pd.DataFrame, meses: pd.DataFrame, ctx: ContextoEstacion, salida: _Lineas,
                     *, con_e2: bool = True, anotado_e2: pd.DataFrame | None = None) -> None:
    activas = ctx.lineas_activas
    if Linea.E1A in activas:
        r = lineas_registro.e1a(anotado, ctx)
        salida.estados.append(r.estados)
        salida.eventos.append(r.eventos)
    if Linea.E1B in activas:
        r = lineas_registro.e1b(anotado, ctx)
        salida.estados.append(r.estados)
        salida.eventos.append(r.eventos)
    if Linea.E1C in activas:
        r = lineas_registro.e1c(meses, ctx)
        salida.estados.append(r.estados)
        salida.eventos.append(r.eventos)
    if con_e2 and Linea.E2 in activas:
        r = lineas_registro.e2(anotado if anotado_e2 is None else anotado_e2, ctx)
        salida.estados.append(r.estados)
        salida.metricas_e2 = r.metricas


def _lineas_fisicas(anotado: pd.DataFrame, serie: SerieEra5 | None, isd: pd.DataFrame | None,
                    ctx: ContextoEstacion, salida: _Lineas, *,
                    metricas_qfe_otros_anios: pd.DataFrame | None = None) -> None:
    """E3t, E3p (gruesa y fina), E4p y E6, y las métricas de E4 en Ts y HR que piden las guardas.

    ``metricas_qfe_otros_anios``: métricas de QFE de años fuera de ``ctx.anios`` que entran sólo al
    apagado de la regla fina, que es de estación (ORQ-3e)."""
    activas = ctx.lineas_activas
    if Linea.E3T in activas or Linea.TP in activas:
        r = lineas_fisicas.e3(anotado, serie, ctx, "Ts")
        if Linea.E3T in activas:
            salida.estados.append(r.estados)
        salida.metricas_e3.append(r.metricas)
    if Linea.E3P in activas:
        r = lineas_fisicas.e3(anotado, serie, ctx, "QFE")
        salida.estados.append(r.estados)
        para_fina = r.metricas
        if metricas_qfe_otros_anios is not None and len(metricas_qfe_otros_anios):
            para_fina = _unir([r.metricas, metricas_qfe_otros_anios], ESQUEMA_METRICAS_E3, "métricas para la fina")
        fina = lineas_fisicas.e3_fina(para_fina, ctx)
        salida.estados.append(fina.estados)
        salida.metricas_e3.append(_con_fino(r.metricas, fina.metricas))
    if Linea.E4P in activas:
        m_qfe = lineas_fisicas.ajustes_e4(anotado, ctx, "QFE")
        salida.estados.append(lineas_fisicas.e4p(m_qfe, ctx).estados)
        salida.metricas_e4.append(m_qfe)
    if Linea.E4T in activas or Linea.G_HR in activas:
        salida.metricas_e4.append(lineas_fisicas.ajustes_e4(anotado, ctx, "Ts"))
    if Linea.G_HR in activas:
        salida.metricas_e4_hr = lineas_fisicas.ajustes_e4(anotado, ctx, "HR")
    if Linea.E6 in activas:
        salida.estados.append(lineas_fisicas.e6(anotado, isd, ctx).estados)


def evaluar_estacion(entrada: EntradaEstacion, serie: SerieEra5 | None, tablas: object, umbrales: Umbrales,
                     opciones: OpcionesCorrida) -> EvidenciaEstacion:
    """Fase 4 para una estación: líneas activas, guardas y marcas precalculadas para toda H de P."""
    anotado, ctx = _preparar(entrada, tablas, umbrales, opciones)
    info = entrada.info
    lin = _Lineas()
    _lineas_registro(anotado, entrada.meses, ctx, lin)
    _lineas_fisicas(anotado, serie, entrada.isd, ctx, lin)
    metricas_e3 = _unir(lin.metricas_e3, ESQUEMA_METRICAS_E3, f"métricas E3 de {info.codigo}")
    metricas_e4 = _unir(lin.metricas_e4, ESQUEMA_METRICAS_E4, f"métricas E4 de {info.codigo}")
    para_guardas = {guardas.METRICAS_E3: metricas_e3,
                    guardas.METRICAS_E4: _unir([metricas_e4, lin.metricas_e4_hr], ESQUEMA_METRICAS_E4,
                                               f"métricas E4 con HR de {info.codigo}")}
    activas = ctx.lineas_activas
    tabla_guardas = (guardas.guardas(anotado, serie, entrada.meses, para_guardas, ctx)
                     if any(g in activas for g in GUARDAS_PRECALCULADAS) else tabla_vacia(ESQUEMA_GUARDAS))
    tabla_marcas = (guardas.marcas(anotado, serie, para_guardas, ctx)
                    if any(m in activas for m in MARCAS_PRECALCULADAS) else tabla_vacia(ESQUEMA_MARCAS))
    return EvidenciaEstacion(
        info=info,
        estados=_unir(lin.estados, ESQUEMA_ESTADOS, f"estados de {info.codigo}"),
        metricas_e2=lin.metricas_e2 if lin.metricas_e2 is not None else tabla_vacia(ESQUEMA_METRICAS_E2),
        metricas_e3=metricas_e3, metricas_e4=metricas_e4,
        eventos=_unir(lin.eventos, ESQUEMA_EVENTOS, f"eventos de {info.codigo}"),
        guardas=_unir([tabla_guardas], ESQUEMA_GUARDAS, f"guardas de {info.codigo}"),
        marcas=_unir([tabla_marcas], ESQUEMA_MARCAS, f"marcas de {info.codigo}"),
        meses=entrada.meses.reset_index(drop=True), horas=_horas(entrada.extracto, info.codigo),
        clases=dict(ctx.clases))


# ---------------------------------------------------------------------------------------------
# Diagnóstico de reglas vencidas (§4.1.4, E1-4; ORQ-3)
# ---------------------------------------------------------------------------------------------
def _CalendarioConCortes(base, cortes: Mapping[str, Sequence[tuple[datetime, datetime]]]):
    """tablas.TablasCalendario cuyas partes se cortan además en las etiquetas especiales de Cv (ORQ-3b).

    Desde la ola 4b es la interfaz pública de tablas (``TablasCalendario.con_cortes``): desfases civiles,
    cambios, Anexo A2 y regímenes son los del calendario base y sólo cambia ``especiales_en``, que usan
    ``tablas.partes_del_mes`` y ``tablas.anotar_partes``. Conserva el nombre de la ola 4a."""
    return base.con_cortes(cortes)


_intervalo_especial = mod_tablas.intervalo_especial     # [desde, hasta) de las etiquetas especiales de un Cambio


def _anios_pedidos(anio) -> tuple[int, ...]:
    if isinstance(anio, (int, np.integer)) and not isinstance(anio, bool):
        return (int(anio),)
    anios = tuple(sorted({int(a) for a in anio}))
    if not anios:
        raise ValueError("diagnostico_reglas_vencidas necesita al menos un año")
    return anios


def _desfases_cv(anotado: pd.DataFrame, cvs: Sequence[Hipotesis], anios: Sequence[int],
                 calendario: object) -> dict[str, dict[tuple[int, str, str], int | None]]:
    """Por Cv: (año, nivel, unidad) → desfase constante de Cv en las etiquetas de la unidad, o None."""
    usa = ((~anotado["especial"].to_numpy(dtype=bool)) & anotado["regimen"].notna().to_numpy(dtype=bool)
           & anotado["anio"].isin(list(anios)).to_numpy())
    x = anotado.loc[usa, ["L", "anio", "parte", "regimen"]]
    etiquetas = pd.DatetimeIndex(x["L"]).to_pydatetime()
    salida: dict[str, dict] = {}
    for cv in cvs:
        c = np.array([np.nan if (v := mod_tablas.desfase_en_etiqueta(cv, L, calendario)) is None else float(v)
                      for L in etiquetas], dtype=np.float64)
        por_unidad: dict[tuple[int, str, str], int | None] = {}
        for nivel, columna in ((Nivel.PARTE, "parte"), (Nivel.REGIMEN, "regimen")):
            grupos = pd.DataFrame({"anio": x["anio"].to_numpy(), "u": x[columna].astype(str).to_numpy(), "c": c})
            for (a, u), g in grupos.groupby(["anio", "u"], sort=True):
                valores = g["c"].to_numpy()
                unicos = np.unique(valores[np.isfinite(valores)])
                constante = unicos.size == 1 and np.isfinite(valores).all()
                por_unidad[(int(a), str(nivel), str(u))] = int(unicos[0]) if constante else None
        salida[cv.id] = por_unidad
    return salida


def _regimen_de_unidad(anotado: pd.DataFrame) -> dict[tuple[int, str], str]:
    """(año, parte) → año-régimen de la parte."""
    x = anotado[anotado["parte"].notna() & anotado["regimen"].notna()]
    return {(int(a), str(p)): str(r) for a, p, r in zip(x["anio"], x["parte"], x["regimen"])}


def _fila_cv(fila: pd.Series, cv: str, estado: str, motivo) -> dict:
    return {"codigo": fila["codigo"], "anio": int(fila["anio"]), "linea": fila["linea"], "regla": fila["regla"],
            "nivel": fila["nivel"], "unidad": fila["unidad"], "H": cv, "estado": estado,
            "reloj_anomalo": bool(fila["reloj_anomalo"]), "discordante": False, "motivo": motivo}


def _sustituir_cv(estados_P: pd.DataFrame, anotado: pd.DataFrame, cvs: Sequence[Hipotesis], ctx: ContextoEstacion,
                  anios: Sequence[int]) -> pd.DataFrame:
    """ORQ-3d: filas de unidad (parte, año-régimen) de Cv en E3t, E3p y E4p por sustitución."""
    info = ctx.info
    zs = tuple(info.zs)
    desfases = _desfases_cv(anotado, cvs, anios, ctx.tablas)
    regimen_de = _regimen_de_unidad(anotado)
    regimenes = {(a, r.id): r for a in anios for r in (ctx.regimenes or {}).get(a, ())}
    unidades = estados_P[estados_P["nivel"].isin([str(Nivel.PARTE), str(Nivel.REGIMEN)])
                         & estados_P["anio"].isin(list(anios))
                         & estados_P["linea"].isin([str(Linea.E3T), str(Linea.E3P), str(Linea.E4P)])]
    filas = []
    for (linea, regla, anio, nivel, unidad), g in unidades.groupby(["linea", "regla", "anio", "nivel", "unidad"],
                                                                    sort=True):
        por_h = {h: fila for h, (_, fila) in zip(g["H"], g.iterrows())}
        primera = g.iloc[0]
        reg_id = str(unidad) if nivel == str(Nivel.REGIMEN) else regimen_de.get((int(anio), str(unidad)))
        regimen = regimenes.get((int(anio), reg_id))
        for cv in cvs:
            c = desfases[cv.id].get((int(anio), str(nivel), str(unidad)))
            igual = None
            if c is not None and regimen is not None:
                igual = next((h.id for h in info.P if h.tipo in ("F", "C") and h.id in por_h
                              and mod_tablas.desfase(h, regimen, zs) == c), None)
            if igual is None:
                filas.append(_fila_cv(primera, cv.id, str(Estado.SIN_INFORMACION), MOTIVO_DESFASE_CV))
            else:
                fuente = por_h[igual]
                motivo = None if pd.isna(fuente["motivo"]) else str(fuente["motivo"])
                filas.append(_fila_cv(fuente, cv.id, str(fuente["estado"]), motivo))
    if not filas:
        return tabla_vacia(ESQUEMA_ESTADOS)
    return pd.DataFrame(filas, columns=list(ESQUEMA_ESTADOS)).astype(ESQUEMA_ESTADOS)


def _regimenes_de_P(estados_P: pd.DataFrame, linea: Linea, regla: Regla, anio: int,
                    estados_validos: Iterable[str]) -> set[str]:
    """Años-régimen del año en que alguna H de P tiene en la línea un estado de ``estados_validos``."""
    f = estados_P[(estados_P["linea"] == str(linea)) & (estados_P["regla"] == str(regla))
                  & (estados_P["anio"] == anio) & (estados_P["nivel"] == str(Nivel.REGIMEN))]
    validos = set(estados_validos)
    return {str(u) for u, e in zip(f["unidad"], f["estado"]) if e in validos}


def _sin_desfase_en(regs_cv: pd.DataFrame, unidades: Iterable[str]) -> bool:
    """ORQ-3d: True si en alguna de ``unidades`` Cv no tiene desfase constante (o no tiene fila)."""
    por_u = {str(u): (e, m) for u, e, m in zip(regs_cv["unidad"], regs_cv["estado"], regs_cv["motivo"])}
    for u in unidades:
        if u not in por_u:
            return True
        estado, motivo = por_u[u]
        if estado == str(Estado.SIN_INFORMACION) and not pd.isna(motivo) and str(motivo) == MOTIVO_DESFASE_CV:
            return True
    return False


def _anual_por_regimenes(filas_cv: pd.DataFrame, anuales_P: pd.DataFrame, cv: str, linea: Linea,
                         regla: Regla, anios: Sequence[int], codigo: str) -> list[pd.DataFrame]:
    """LF-7 (E3t) y LF-11 (E4p) para Cv: incompatible si lo es en algún año-régimen; si no, sin información
    («desfase_no_constante») si en algún año-régimen evaluable para P el desfase de Cv no es constante
    (§4.4: «compatible si lo es en todos los años-régimen evaluables»); compatible si lo es en todos los
    evaluables (≥ 1); dudosa si hay evaluables y no; si no, sin información. ``anuales_P``: los estados
    de P del diagnóstico (unidades y años)."""
    informan = [str(e) for e in Estado if e != Estado.SIN_INFORMACION]
    marcos = []
    for anio in anios:
        regs = filas_cv[(filas_cv["anio"] == anio) & (filas_cv["nivel"] == str(Nivel.REGIMEN))
                        & (filas_cv["linea"] == str(linea)) & (filas_cv["H"] == cv)]
        valores = [Estado(v) for v in regs["estado"]]
        evaluables = [v for v in valores if v != Estado.SIN_INFORMACION]
        evaluables_P = _regimenes_de_P(anuales_P, linea, regla, anio, informan)
        motivo = None
        if Estado.INCOMPATIBLE in valores:
            estado = Estado.INCOMPATIBLE
        elif _sin_desfase_en(regs, evaluables_P):
            estado, motivo = Estado.SIN_INFORMACION, MOTIVO_DESFASE_CV
        elif evaluables and all(v == Estado.COMPATIBLE for v in evaluables):
            estado = Estado.COMPATIBLE
        elif evaluables:
            estado = Estado.DUDOSA
        else:
            estado, motivo = Estado.SIN_INFORMACION, str(MotivoSinInfo.NO_INFORMATIVA)
        anomalo = _anomalo_anual(anuales_P, linea, regla, anio)
        marcos.append(mod_estados.filas_estado(codigo, anio, linea, Nivel.ANIO, f"{anio:04d}", {cv: estado},
                                               regla=regla, reloj_anomalo=anomalo, motivo=motivo))
    return marcos


def _anomalo_anual(anuales_P: pd.DataFrame, linea: Linea, regla: Regla, anio: int) -> bool:
    f = anuales_P[(anuales_P["linea"] == str(linea)) & (anuales_P["regla"] == str(regla))
                  & (anuales_P["anio"] == anio) & (anuales_P["nivel"] == str(Nivel.ANIO))]
    return bool(f["reloj_anomalo"].any())


def _anual_fina(filas_cv: pd.DataFrame, estados_P: pd.DataFrame, cv: str, anios: Sequence[int],
                codigo: str) -> list[pd.DataFrame]:
    """Regla anual de e3_fina (§4.3.4) para Cv, sobre los años-régimen activos (finos y sin apagado: P
    informativo): incompatible si alguno con Cv constante lo es; si no, sin información
    («desfase_no_constante») si en alguno el desfase de Cv no es constante, porque «compatible» pide
    ĉ^f = c_H(R) en todos los finos; compatible si hay alguno y en todos lo es."""
    marcos = []
    fina_P = estados_P[(estados_P["linea"] == str(Linea.E3P)) & (estados_P["regla"] == str(Regla.FINA))]
    apagada = bool(((fina_P["nivel"] == str(Nivel.ESTACION))
                    & (fina_P["motivo"] == str(MotivoSinInfo.APAGADA)).fillna(False)).any())
    for anio in anios:
        activos = _regimenes_de_P(fina_P, Linea.E3P, Regla.FINA, anio, _INFORMATIVOS)
        regs = filas_cv[(filas_cv["anio"] == anio) & (filas_cv["nivel"] == str(Nivel.REGIMEN))
                        & (filas_cv["linea"] == str(Linea.E3P)) & (filas_cv["regla"] == str(Regla.FINA))
                        & (filas_cv["H"] == cv)]
        propios = [Estado(e) for u, e in zip(regs["unidad"], regs["estado"])
                   if str(u) in activos and e in _INFORMATIVOS]
        sin_desfase = any(str(u) in activos and e not in _INFORMATIVOS for u, e in zip(regs["unidad"], regs["estado"]))
        sin_desfase = sin_desfase or bool(activos - {str(u) for u in regs["unidad"]})
        motivo = None
        if Estado.INCOMPATIBLE in propios:
            estado = Estado.INCOMPATIBLE
        elif sin_desfase:
            estado, motivo = Estado.SIN_INFORMACION, MOTIVO_DESFASE_CV
        elif not propios:
            estado = Estado.SIN_INFORMACION
            motivo = str(MotivoSinInfo.APAGADA) if apagada else str(MotivoSinInfo.NO_INFORMATIVA)
        else:
            estado = Estado.COMPATIBLE
        anomalo = _anomalo_anual(estados_P, Linea.E3P, Regla.FINA, anio)
        marcos.append(mod_estados.filas_estado(codigo, anio, Linea.E3P, Nivel.ANIO, f"{anio:04d}", {cv: estado},
                                               regla=Regla.FINA, reloj_anomalo=anomalo, motivo=motivo))
    return marcos


def _filas_cv_fisicas(estados_P: pd.DataFrame, anotado: pd.DataFrame, cvs: Sequence[Hipotesis],
                      ctx: ContextoEstacion, anios: Sequence[int]) -> pd.DataFrame:
    """Cv en E3t, E3p (gruesa y fina) y E4p: unidades por sustitución y filas anuales por la regla de cada
    línea (ORQ-3d); en E6, sin información (ORQ-3f)."""
    codigo = ctx.info.codigo
    unidades = _sustituir_cv(estados_P, anotado, cvs, ctx, anios)
    marcos = []
    activas = ctx.lineas_activas
    for cv in (h.id for h in cvs):
        propias = unidades[unidades["H"] == cv]
        if Linea.E3P in activas:
            gruesa = propias[(propias["linea"] == str(Linea.E3P)) & (propias["regla"] == str(Regla.GRUESA))]
            if len(gruesa):
                marcos.append(mod_estados.anual_por_partes(gruesa, linea=Linea.E3P, regla=Regla.GRUESA,
                                                           min_partes=constantes.valor("ANUAL_MIN_PARTES")))
            fina = propias[(propias["linea"] == str(Linea.E3P)) & (propias["regla"] == str(Regla.FINA))]
            marcos.append(fina)
            marcos += _anual_fina(fina, estados_P, cv, anios, codigo)
        for linea, regla in ((Linea.E3T, Regla.GRUESA), (Linea.E4P, Regla.UNICA)):
            if linea not in activas:
                continue
            de_linea = propias[propias["linea"] == str(linea)]
            marcos.append(de_linea)
            marcos += _anual_por_regimenes(de_linea, estados_P, cv, linea, regla, anios, codigo)
        if Linea.E6 in activas:
            for anio in anios:
                marcos.append(mod_estados.filas_estado(codigo, anio, Linea.E6, Nivel.ANIO, f"{anio:04d}",
                                                       {cv: Estado.SIN_INFORMACION}, motivo=MOTIVO_CV_SIN_E6))
    marcos = [m for m in marcos if len(m)]
    if not marcos:
        return tabla_vacia(ESQUEMA_ESTADOS)
    return pd.concat(marcos, ignore_index=True).astype(ESQUEMA_ESTADOS)


def diagnostico_reglas_vencidas(entrada: EntradaEstacion, serie: SerieEra5 | None, anio, tablas: object,
                                umbrales: Umbrales, opciones: OpcionesCorrida, *,
                                evidencia: EvidenciaEstacion | None = None) -> pd.DataFrame:
    """Estados del año con P ∪ {Cv(Z, y)} y partes cortadas también en las etiquetas especiales de Cv del
    Anexo A2 (R-09; Enmienda 1, E1-4; ORQ-3). ``anio`` es un año del Anexo A2 o varios (un iterable): se
    cortan las partes de todos ellos en una sola pasada. Devuelve ESQUEMA_ESTADOS (filas de P y de Cv)
    de esos años, que es lo que lee decision.marca_reglas_vencidas.

    ``evidencia`` (la de la fase 4) da las métricas de QFE de los otros años para el apagado de la regla
    fina, que es de estación; sin ella, E3p se recalcula en todos los años (más lento, mismo criterio)."""
    _validar_opciones(opciones)
    anios = _anios_pedidos(anio)
    a2 = {int(f.anio) for f in tablas.anexo_a2}
    fuera = [a for a in anios if a not in a2]
    if fuera:
        raise ValueError(f"Cv sólo existe en los años del Anexo A2 (§4.1.4): {fuera}")
    info = entrada.info
    cvs = tuple(Hipotesis("Cv", None, h.zona) for h in info.P if h.tipo == "C")
    if not cvs:
        return tabla_vacia(ESQUEMA_ESTADOS)
    _validar_entrada(entrada)
    calendario = tablas.con_cortes_reglas_vencidas([cv.zona for cv in cvs], anios)     # ORQ-3b
    anotado = mod_tablas.anotar_partes(entrada.extracto, info, calendario)
    ctx_P = _contexto(anotado, entrada, info, calendario, umbrales, opciones)
    pedidos = tuple(a for a in anios if a in ctx_P.anios)
    if not pedidos:
        return tabla_vacia(ESQUEMA_ESTADOS)
    ctx_cv = replace(ctx_P, info=replace(info, P=tuple(info.P) + cvs))

    lin = _Lineas()
    # E1a, E1b y E1c: patrones de estación, con todos los años (ORQ-3c). E2 sólo en los años pedidos.
    _lineas_registro(anotado, entrada.meses, ctx_cv, lin, con_e2=False)
    del_anio = anotado[anotado["anio"].isin(list(pedidos))].reset_index(drop=True)
    _lineas_registro(del_anio, entrada.meses, replace(ctx_cv, anios=pedidos,
                                                      lineas_activas=ctx_cv.lineas_activas & {Linea.E2}), lin)
    # Físicas: con P sin Cv y luego Cv por sustitución (ORQ-3d). Sin guardas ni marcas: los pasos 2 a 4
    # sólo miran G-versión, que no depende de H y ya está en la decisión.
    otros = None
    ctx_P = replace(ctx_P, lineas_activas=ctx_P.lineas_activas & LINEAS_FISICAS_DIAGNOSTICO)
    ctx_fisicas = replace(ctx_P, anios=pedidos)
    if evidencia is not None:
        m = evidencia.metricas_e3
        otros = m[(m["variable"] == "QFE") & ~m["anio"].isin(list(pedidos))]
    else:
        ctx_fisicas = ctx_P
    fis = _Lineas()
    _lineas_fisicas(anotado, serie, entrada.isd, ctx_fisicas, fis, metricas_qfe_otros_anios=otros)
    estados_P = _unir(fis.estados, ESQUEMA_ESTADOS, f"estados físicos del diagnóstico de {info.codigo}")
    estados_P = estados_P[estados_P["anio"].isin(list(pedidos))]
    con_cv = _filas_cv_fisicas(estados_P, anotado, cvs, ctx_cv, pedidos)
    todos = _unir(lin.estados + [estados_P, con_cv], ESQUEMA_ESTADOS,
                  f"diagnóstico de reglas vencidas de {info.codigo}")
    return todos[todos["anio"].isin(list(pedidos))].reset_index(drop=True)


# ---------------------------------------------------------------------------------------------
# Fases 5 a 10
# ---------------------------------------------------------------------------------------------
def _contexto_de_evidencia(ev: EvidenciaEstacion, tablas: object, umbrales: Umbrales,
                           opciones: OpcionesCorrida) -> ContextoEstacion:
    """ContextoEstacion sin extracto (para la marca «posible media horaria»): todo sale de la evidencia."""
    info = ev.info
    clases = dict(ev.clases or {})
    anios = tuple(sorted(clases))
    regimenes = {a: mod_tablas.regimenes_del_anio(tuple(info.zs), a, tablas) for a in anios}
    con_datos = {a: tuple(sorted({str(r) for c in clases[a] for r in c.desfases})) for a in anios}
    entran = ev.meses[ev.meses["entra"].fillna(False).astype(bool)]
    meses: dict[int, set[int]] = {}
    for a, m in zip(entran["anio"], entran["mes"]):
        meses.setdefault(int(a), set()).add(int(m))
    return ContextoEstacion(info=info, tablas=tablas, umbrales=umbrales, anios=anios, regimenes=regimenes,
                            regimenes_con_datos=con_datos, clases=clases,
                            meses_con_datos={a: tuple(sorted(meses.get(a, ()))) for a in anios},
                            lineas_activas=frozenset(opciones.lineas_activas),
                            aplicar_exclusion_costera=bool(opciones.aplicar_exclusion_costera))


def _etiquetas_por_mes(extracto: pd.DataFrame) -> dict[str, np.ndarray]:
    """«AAAA-MM» → etiquetas del extracto (datetime64[h], ordenadas) (ORQ-8)."""
    L = extracto["L"].to_numpy(dtype="datetime64[h]")
    n_meses = len(mod_tablas.MESES)
    clave = (extracto["anio"].to_numpy(dtype=np.int64) * n_meses
             + extracto["mes"].to_numpy(dtype=np.int64) - 1)
    salida = {}
    for k in np.unique(clave):
        anio, mes0 = divmod(int(k), n_meses)
        salida[_texto_mes(anio, mes0 + 1)] = L[clave == k]
    return salida


def _meses_con_datos(ev: EvidenciaEstacion) -> list[str]:
    entran = ev.meses[ev.meses["entra"].fillna(False).astype(bool)]
    return sorted({_texto_mes(a, m) for a, m in zip(entran["anio"], entran["mes"])})


def _reloj_de_estacion(rachas: pd.DataFrame, tramos: Sequence[Tramo]) -> str:
    """ORQ-7: relojes de las rachas que tienen tramos, en orden, con la regla única de
    politica.reloj_de_rachas (también la de SAL-11): rachas consecutivas cuya intersección de clases no es
    vacía son el mismo reloj (§5.3.1 y §5.3.3: no hay cambio entre ellas) y van en un solo término, con su
    intersección; «→» separa sólo relojes de intersección vacía (R-25)."""
    con_tramos = {int(t.id.split(".")[0]) for t in tramos}
    filas = rachas[rachas["racha"].isin(list(con_tramos))].sort_values("racha")
    return mod_politica.reloj_de_rachas(str(c) for c in filas["clase"])


def _reloj_no_verificado(decisiones: Sequence[DecisionAnio]) -> list[dict]:
    """ORQ-6: por año confirmado, las variables con la marca «reloj no verificado» (G-HR, G-viento)."""
    salida = []
    for d in sorted(decisiones, key=lambda d: d.anio):
        if d.veredicto != Veredicto.CONFIRMADO:
            continue
        variables = [v for marca, vs in VARIABLES_MARCA.items() if d.marcas.get(marca) is True for v in vs]
        if variables:
            salida.append({"anio": int(d.anio), "variables": variables})
    return salida


def _entrada_estacion(ev: EvidenciaEstacion, decisiones: Sequence[DecisionAnio], tramos: Sequence[Tramo],
                      rachas: decision.ResultadoRachas, media_horaria: bool) -> dict:
    """Entrada de ``estaciones`` de §7.2 (ORQ-7), sin «tramos» (los agrega politica.politica)."""
    conjunto = str(ev.info.conjunto)
    if tramos:
        return {"veredicto": str(VeredictoEstacion.CONFIRMADA), "reloj": _reloj_de_estacion(rachas.rachas, tramos),
                "conjunto": conjunto,
                "marcas": {"posible_media_horaria": bool(media_horaria),
                           "reloj_no_verificado": _reloj_no_verificado(decisiones)}}
    orden = sorted(decisiones, key=lambda d: d.anio)
    detalle = "; ".join(f"{d.anio} {d.veredicto}" + (f" ({d.motivo})" if d.motivo else "") for d in orden)
    if rachas.inestable:
        motivo = str(MotivoAnio.INESTABLE)
        detalle = "; ".join(rachas.motivos_inestable) + (f". {detalle}" if detalle else "")
    elif any(d.veredicto == Veredicto.CONFIRMADO for d in orden):
        motivo = MOTIVO_SIN_MESES_CON_REGLA
    else:
        vistos = {d.veredicto for d in orden}
        motivo = str(next((v for v in _GRAVEDAD if v in vistos), Veredicto.SIN_DATOS))
    return {"veredicto": str(VeredictoEstacion.SIN_CONFIRMAR), "motivo": motivo, "detalle": detalle or None,
            "conjunto": conjunto}


def _con_a6(decisiones: Sequence[DecisionAnio], contrarios: set[tuple[str, int]]) -> list[DecisionAnio]:
    """A6 (§5.4, §4.5): los estación-años confirmados que contradice un D1 quedan sin confirmar."""
    if not contrarios:
        return list(decisiones)
    return [replace(d, veredicto=Veredicto.SIN_CONFIRMAR, motivo=MotivoAnio.DOCUMENTAL_A6,
                    detalle="un D1 contradice el reloj confirmado (A6)")
            if (d.codigo, int(d.anio)) in contrarios else d for d in decisiones]


def _llamar(avance, fase: str, hechos: int, total: int) -> None:
    if avance is not None:
        avance(fase, int(hechos), int(total))


def _total(iterable) -> int:
    try:
        return len(iterable)
    except TypeError:
        return 0


def politica_de(resultado: ResultadoRed, huellas: mod_politica.HuellasPolitica, *, post_hoc: bool = False,
                errata_post_c4: bool = False, ajuste_documental: bool = False) -> dict | None:
    """El JSON de §7.2 de una corrida ya evaluada (sin escribirlo); None si A5 dio alto (§5.4; ORQ-9)."""
    if resultado.consecuencias.a5_alto:
        return None
    return mod_politica.politica(resultado.tramos, resultado.estaciones, huellas, post_hoc=post_hoc,
                                 errata_post_c4=errata_post_c4, ajuste_documental=ajuste_documental)


def evaluar_red(entradas: Callable[[], Iterable[EntradaEstacion]], serie: SerieEra5 | None, tablas: object,
                umbrales: Umbrales, opciones: OpcionesCorrida, *,
                avance: Callable[[str, int, int], None] | None = None,
                huellas: mod_politica.HuellasPolitica | None = None,
                registro_documental: Sequence[Mapping] = (),
                sensibilidades_bateria: Mapping | None = None) -> ResultadoRed:
    """Fases 4 a 10. ``entradas`` es una fábrica: se recorre una vez para la fase 4 y otra (la segunda
    pasada, ORQ-11) para el diagnóstico de reglas vencidas y las etiquetas de los tramos, salvo con el
    diagnóstico apagado y ``opciones.conservar_etiquetas``. La segunda pasada debe traer las mismas
    estaciones. ``avance(fase, hechos, total)`` sólo recibe conteos, en una sucesión que no depende de
    los veredictos (total 0 si la fábrica no da su largo en la fase 4). ``huellas``: si se dan y A5 no da
    alto, se arma la política (ORQ-9). ``registro_documental``: líneas de E5 para A6 (vacío con E5
    inactiva)."""
    _validar_opciones(opciones)
    U = umbrales
    tiempos: dict[str, float] = {}
    reloj = time.perf_counter()

    # Fase 4: estados de las líneas, estación por estación.
    evidencias: list[EvidenciaEstacion] = []
    etiquetas: dict[str, dict[str, np.ndarray]] = {}
    vistos: set[str] = set()
    iterable = entradas()
    total = _total(iterable)
    for k, entrada in enumerate(iterable, start=1):
        codigo = entrada.info.codigo
        if codigo in vistos:
            raise ValueError(f"estación repetida en las entradas: {codigo}")
        vistos.add(codigo)
        evidencias.append(evaluar_estacion(entrada, serie, tablas, U, opciones))
        if opciones.conservar_etiquetas:
            etiquetas[codigo] = _etiquetas_por_mes(entrada.extracto)
        _llamar(avance, "estados", k, total)
    por_codigo = {ev.info.codigo: ev for ev in evidencias}
    n_anios = sum(len(ev.clases or {}) for ev in evidencias)
    tiempos["estados"] = time.perf_counter() - reloj

    # Fase 5: A3, A5 y calibración de E3t.
    t = time.perf_counter()
    macrozonas = sorted({ev.info.macrozona for ev in evidencias})
    consecuencias, controles = red.controles_red(evidencias, macrozonas, U, calendario=tablas)
    _llamar(avance, "controles_red", 1, 1)
    tiempos["controles_red"] = time.perf_counter() - t

    # Fase 6: pasos 1 a 6 para todos los estación-años.
    t = time.perf_counter()
    insumos: dict[tuple[str, int], decision.InsumosAnio] = {}
    parciales: list[DecisionAnio] = []
    for k, ev in enumerate(evidencias, start=1):
        for anio in sorted(ev.clases or {}):
            ins = decision.insumos_anio(ev, anio, consecuencias, U)
            insumos[(ev.info.codigo, anio)] = ins
            parciales.append(decision.pasos_1_a_6(ins, U))
        _llamar(avance, "pasos_1_a_6", k, len(evidencias))
    tiempos["pasos_1_a_6"] = time.perf_counter() - t

    # Fase 7: A4, que se fija en las consecuencias.
    a4_restringe, detalle_a4 = red.a4(parciales, U)
    consecuencias = red.fijar_a4(consecuencias, a4_restringe)
    _llamar(avance, "A4", 1, 1)

    # Fase 8: pasos 7 a 9, la comparación con E3t restringida (ORQ-4) y A6 (ORQ-5).
    t = time.perf_counter()
    finales = [decision.pasos_7_a_9(p, insumos[(p.codigo, p.anio)], consecuencias, U) for p in parciales]
    restringidas = None
    if opciones.comparacion_e3t_restringida:
        todas_restringidas = replace(consecuencias, modo_e3t={})
        restringidas = [decision.pasos_7_a_9(p, insumos[(p.codigo, p.anio)], todas_restringidas, U)
                        for p in parciales]
    contrarios = set(red.a6(registro_documental, finales)) if registro_documental else set()
    finales = _con_a6(finales, contrarios)
    if restringidas is not None and registro_documental:      # ORQ-4: la comparación no mide A6
        restringidas = _con_a6(restringidas, set(red.a6(registro_documental, restringidas)))
    _llamar(avance, "pasos_7_a_9", 1, 1)
    del insumos
    tiempos["pasos_7_a_9"] = time.perf_counter() - t

    # Segunda pasada (ORQ-11): reglas vencidas (§4.1.4, ORQ-3) y etiquetas de los tramos. Corre según las
    # opciones, nunca según los veredictos, y su avance cuenta cada estación leída.
    t = time.perf_counter()
    anios_a2 = {int(f.anio) for f in tablas.anexo_a2}
    diagnosticar: dict[str, list[int]] = {}
    if opciones.diagnostico_reglas_vencidas:
        for d in finales:
            civil = any(h.tipo == "C" for h in por_codigo[d.codigo].info.P)
            if (d.veredicto == Veredicto.DISCREPANTE and d.anio in anios_a2 and civil
                    and d.motivo != MotivoAnio.G_VERSION):
                diagnosticar.setdefault(d.codigo, []).append(d.anio)
    anios_confirmados: dict[str, set[int]] = {}
    for d in finales:
        if d.veredicto == Veredicto.CONFIRMADO:
            anios_confirmados.setdefault(d.codigo, set()).add(int(d.anio))
    marcas_cv: set[tuple[str, int]] = set()
    estados_cv: list[pd.DataFrame] = []
    if evidencias and (opciones.diagnostico_reglas_vencidas or not opciones.conservar_etiquetas):
        n_estaciones = len(evidencias)
        vueltos: set[str] = set()
        for k, entrada in enumerate(entradas(), start=1):
            codigo = entrada.info.codigo
            if codigo not in por_codigo or codigo in vueltos:
                raise ValueError("la segunda pasada de la fábrica de entradas trajo una estación repetida o que "
                                 "no estaba en la primera")
            vueltos.add(codigo)
            _validar_entrada(entrada)
            if not opciones.conservar_etiquetas and codigo in anios_confirmados:
                ext = entrada.extracto
                etiquetas[codigo] = _etiquetas_por_mes(ext[ext["anio"].isin(sorted(anios_confirmados[codigo]))])
            if codigo in diagnosticar:
                ev = por_codigo[codigo]
                tabla = diagnostico_reglas_vencidas(entrada, serie, diagnosticar[codigo], tablas, U, opciones,
                                                    evidencia=ev)
                estados_cv.append(tabla)
                mz = ev.info.macrozona
                for d in finales:
                    if d.codigo == codigo and d.anio in diagnosticar[codigo] and decision.marca_reglas_vencidas(
                            d, tabla, U, e4p_activa=consecuencias.e4p_activa(mz),
                            fina_activa=consecuencias.fina_activa(mz)):
                        marcas_cv.add((codigo, d.anio))
            _llamar(avance, "segunda_pasada", k, n_estaciones)
        if len(vueltos) != n_estaciones:
            raise ValueError(f"la segunda pasada de la fábrica de entradas trajo {len(vueltos)} de "
                             f"{n_estaciones} estaciones")
    if marcas_cv:
        finales = [replace(d, reglas_vencidas=True) if (d.codigo, d.anio) in marcas_cv else d for d in finales]
    tiempos["segunda_pasada"] = time.perf_counter() - t

    # Fase 9: rachas, cambios, cuarentena y meses con regla (§5.3); marca «posible media horaria».
    t = time.perf_counter()
    por_estacion: dict[str, list[DecisionAnio]] = {}
    for d in finales:
        por_estacion.setdefault(d.codigo, []).append(d)
    resultados_rachas: dict[str, decision.ResultadoRachas] = {}
    decisiones: list[DecisionAnio] = []
    meses_con_regla: dict[str, dict[str, str]] = {}
    media_horaria: dict[str, bool] = {}
    for k, ev in enumerate(evidencias, start=1):
        codigo = ev.info.codigo
        res = decision.rachas(por_estacion.get(codigo, []), ev.meses, frozenset(), U,      # Enmienda 3, E3-2 (A′)
                              patron_regla_vencida=lineas_registro.patron_regla_vencida(ev.estados))
        resultados_rachas[codigo] = res
        decisiones.extend(res.decisiones)
        meses_con_regla[codigo] = dict(res.meses_con_regla)
        confirmados = {d.anio: d.clase_confirmada for d in res.decisiones if d.veredicto == Veredicto.CONFIRMADO}
        media_horaria[codigo] = bool(      # §4.3.5 con B6; sólo la llevan las entradas «confirmada» (§7.2, ORQ-6)
            confirmados and Linea.E3P in opciones.lineas_activas
            and guardas.marca_media_horaria(ev.metricas_e3[ev.metricas_e3["variable"] == "QFE"],
                                            _contexto_de_evidencia(ev, tablas, U, opciones)))
        _llamar(avance, "rachas", k, len(evidencias))
    rachas_todas = _unir([r.rachas for r in resultados_rachas.values()], ESQUEMA_RACHAS, "rachas")
    tiempos["rachas"] = time.perf_counter() - t

    # Fase 10: tramos y entradas de ``estaciones``; la política, con las huellas y sin A5 alto.
    t = time.perf_counter()
    tramos: dict[str, list[Tramo]] = {}
    estaciones: dict[str, dict] = {}
    for k, ev in enumerate(evidencias, start=1):
        codigo = ev.info.codigo
        res = resultados_rachas[codigo]
        mcr = meses_con_regla[codigo]
        lista: list[Tramo] = []
        if mcr:
            numero = {}
            for fila in res.rachas.itertuples(index=False):
                for a in range(int(fila.anio_desde), int(fila.anio_hasta) + 1):
                    numero[a] = int(fila.racha)
            clases_anio = {f"{d.anio:04d}": (numero[d.anio], d.clase_confirmada) for d in res.decisiones
                           if d.veredicto == Veredicto.CONFIRMADO}
            por_mes = etiquetas.get(codigo, {})
            lista = mod_politica.tramos(codigo, mcr, clases_anio, {m: por_mes.get(m, np.array([], "datetime64[h]"))
                                                                   for m in mcr}, tablas)
        tramos[codigo] = lista
        estaciones[codigo] = _entrada_estacion(ev, res.decisiones, lista, res, media_horaria[codigo])
        _llamar(avance, "politica", k, len(evidencias))
    tiempos["politica"] = time.perf_counter() - t

    controles = dict(controles)
    controles["A4"] = detalle_a4
    controles["A6"] = {"lineas_registro": len(registro_documental), "contrarios": sorted([list(x) for x in contrarios])}
    meses_con_datos = {ev.info.codigo: _meses_con_datos(ev) for ev in evidencias}
    controles["cambios_del_portal"] = red.cambios_del_portal(rachas_todas, meses_con_datos, U)
    lineas_sin_cv = (sorted(str(x) for x in opciones.lineas_activas & LINEAS_SIN_CV)
                     if opciones.diagnostico_reglas_vencidas else [])
    controles["reglas_vencidas"] = {"diagnosticados": {c: a for c, a in sorted(diagnosticar.items())},
                                    "con_marca": sorted([list(x) for x in marcas_cv]),
                                    "lineas_sin_cv": lineas_sin_cv}       # ORQ-3f: van a las desviaciones
    if restringidas is not None:
        distintas = [{"codigo": a.codigo, "anio": int(a.anio), "veredicto": str(a.veredicto),
                      "veredicto_e3t_restringida": str(b.veredicto), "clase": a.clase_confirmada,
                      "clase_e3t_restringida": b.clase_confirmada}
                     for a, b in zip(finales, restringidas)
                     if (a.veredicto, a.clase_confirmada) != (b.veredicto, b.clase_confirmada)]
        controles["comparacion_e3t_restringida"] = {"estacion_anios": len(restringidas), "distintas": distintas}

    descripcion = red.describir_red(decisiones, rachas_todas, evidencias, U, meses_con_regla=meses_con_regla,
                                    sensibilidades_bateria=sensibilidades_bateria)
    predicciones = red.predicciones(evidencias, decisiones, consecuencias=consecuencias, calendario=tablas)   # §1.13
    tiempos["total"] = time.perf_counter() - reloj
    tiempos["estacion_anios"] = n_anios
    tiempos["por_estacion_anio"] = tiempos["total"] / n_anios if n_anios else None   # JSON sin NaN

    resultado = ResultadoRed(
        evidencias=evidencias, consecuencias=consecuencias, controles=controles, decisiones=decisiones,
        decisiones_e3t_restringida=restringidas, rachas=rachas_todas, meses_con_regla=meses_con_regla,
        tramos=tramos, politica=None, descripcion_red=descripcion, predicciones=predicciones,
        estaciones=estaciones, resultados_rachas=resultados_rachas,
        estados_reglas_vencidas=_unir(estados_cv, ESQUEMA_ESTADOS, "estados con Cv") if estados_cv else None,
        tiempos=tiempos)
    if huellas is not None:
        resultado.politica = politica_de(resultado, huellas)
    return resultado


# ---------------------------------------------------------------------------------------------
# Fase 10: comprobaciones de §7.3 sobre la política releída desde disco
# ---------------------------------------------------------------------------------------------
def contexto_verificacion(resultado: ResultadoRed, politica_: Mapping, destino: Path, raiz_dmc: Path, *,
                          adaptador, preflight, dmc_features, tablas: object,
                          adaptador_sha256: str = fijados.SHA_ADAPTADOR) -> mod_politica.ContextoVerificacion:
    """ContextoVerificacion de una corrida: artefactos evaluados (de ``destino``), sus etiquetas (leídas
    del extracto, una estación a la vez), veredictos de los tramos, meses con regla y la muestra fijada
    de la comprobación 7 (politica.meses_muestra_lector_real, con los manifiestos bajo ``raiz_dmc``)."""
    artefactos = extraccion.leer_artefactos_evaluados(destino)
    evaluados = {a["artefacto_sha256"]: (a["codigo"], _texto_mes(a["anio"], a["mes"])) for a in artefactos}
    ident = {a["artefacto_sha256"]: (a["codigo"], int(a["id_artefacto"])) for a in artefactos}
    leido: dict[str, pd.DataFrame] = {}

    def etiquetas(sha: str) -> np.ndarray:
        codigo, n = ident[sha]
        if codigo not in leido:
            leido.clear()
            leido[codigo] = extraccion.leer_extracto(destino, codigo, ["L", "id_artefacto"])
        e = leido[codigo]
        return e.loc[e["id_artefacto"] == n, "L"].to_numpy(dtype="datetime64[h]")

    macrozonas = {ev.info.codigo: ev.info.macrozona for ev in resultado.evidencias}
    muestra = mod_politica.meses_muestra_lector_real(politica_, macrozonas, tablas)
    manifiestos = {c: [Path(raiz_dmc) / extraccion.CARPETA_ESTACIONES / c / f"{m}{extraccion.SUFIJO_MANIFIESTO}"
                       for m in meses] for c, meses in muestra.items()}
    return mod_politica.ContextoVerificacion(
        adaptador=adaptador, adaptador_sha256=adaptador_sha256, preflight=preflight, dmc_features=dmc_features,
        artefactos_evaluados=evaluados, etiquetas_de_artefacto=etiquetas,
        veredictos=mod_politica.veredictos_de(resultado.tramos),
        meses_con_regla={c: frozenset(m) for c, m in resultado.meses_con_regla.items()},
        muestra_lector_real=manifiestos, tablas=tablas)


def verificador_7_3(resultado: ResultadoRed, destino: Path, raiz_dmc: Path, *, adaptador, preflight,
                    dmc_features, tablas: object, adaptador_sha256: str = fijados.SHA_ADAPTADOR
                    ) -> Callable[[Path], tuple[list[str], list[dict]]]:
    """El ``verificar`` de salidas.escribir_corrida (ORQ-12, SAL-2): ruta → (fallas de las siete
    comprobaciones de §7.3, no normalizables de la comprobación 7). Relee la política de la ruta (la
    provisional, antes de las tablas y del informe), arma su ContextoVerificacion y no toca ``resultado``:
    A7 y no_normalizables.csv los escribe salidas en el informe y en las tablas."""
    def verificar(ruta: Path) -> tuple[list[str], list[dict]]:
        ruta = Path(ruta)
        try:
            pol = json.loads(ruta.read_bytes())
        except (OSError, ValueError):
            pol = {}                    # verificar_politica informa que no se puede releer (comprobación 1)
        if not isinstance(pol, Mapping):
            pol = {}
        ctx = contexto_verificacion(resultado, pol, destino, raiz_dmc, adaptador=adaptador, preflight=preflight,
                                    dmc_features=dmc_features, tablas=tablas, adaptador_sha256=adaptador_sha256)
        fallas = mod_politica.verificar_politica(ruta, ctx)
        return list(fallas), list(ctx.no_normalizables)
    return verificar


def comprobar_politica(resultado: ResultadoRed, ruta_politica: Path,
                       ctx: mod_politica.ContextoVerificacion) -> red.ResultadoControl:
    """§7.3 sobre la política releída (``ruta_politica``): A7 y los «no normalizables» de la comprobación 7,
    que quedan en ``resultado.no_normalizables`` y en ``resultado.controles["A7"]``.

    Sólo para pruebas y diagnósticos: no es parte de la cadena del ejecutable (ORQ-12). Allí §7.3 corre
    dentro de salidas.escribir_corrida con ``verificador_7_3``, antes del informe, y salidas reemplaza
    ``controles["A7"]`` y los no normalizables por los de esa política (SAL-20)."""
    fallas = mod_politica.verificar_politica(Path(ruta_politica), ctx)
    resultado.no_normalizables = list(ctx.no_normalizables)
    control = red.a7(fallas)
    resultado.controles["A7"] = {"pasa": control.pasa, **control.detalle,
                                 "no_normalizables": len(resultado.no_normalizables)}
    return control


# ---------------------------------------------------------------------------------------------
# Entradas de --aplicar desde los extractos ya escritos (fase 3 → fase 4)
# ---------------------------------------------------------------------------------------------
def entradas_desde_extraccion(destino: Path, catalogo_dmc: pd.DataFrame, infos: Mapping[str, InfoEstacion],
                              umbrales: Umbrales, *, isd: pd.DataFrame | None = None
                              ) -> tuple[dict[str, InfoEstacion], Callable[[], Iterator[EntradaEstacion]]]:
    """Después de extraccion.extraer_dmc: marca las coordenadas inconsistentes (§3.1, con los textos de
    los artefactos evaluados) y da la fábrica de entradas, que lee un extracto a la vez. Sólo entran
    las estaciones con algún mes evaluado. ``isd`` (ESQUEMA_ISD) se reparte por código si E6 está activa."""
    meses = extraccion.leer_meses(destino)
    marcadas = extraccion.marcar_coordenadas_inconsistentes(infos, catalogo_dmc, meses, umbrales)
    codigos = sorted(set(meses.loc[meses["entra"].fillna(False).astype(bool), "codigo"]))
    faltan = [c for c in codigos if c not in marcadas]
    if faltan:
        raise ValueError(f"estaciones con meses evaluados sin InfoEstacion: {faltan}")

    def fabrica() -> Iterator[EntradaEstacion]:
        for codigo in codigos:
            propios = meses[meses["codigo"] == codigo].reset_index(drop=True)
            yield EntradaEstacion(info=marcadas[codigo], extracto=extraccion.leer_extracto(destino, codigo),
                                  meses=propios,
                                  isd=None if isd is None else isd[isd["codigo"] == codigo].reset_index(drop=True))

    return dict(marcadas), fabrica
