"""Regla de decisión: §5.1 (pasos 1 a 9, en dos pasadas), §5.3 (rachas, cambios, cuarentena, meses con
regla), la tabla de §5.5, el diagnóstico de reglas vencidas (§4.1.4) y la muestra de expedientes de
control. Puro: trabaja sólo sobre EvidenciaEstacion, ConsecuenciasRed y DecisionAnio; nunca lee extractos.

Orden de §5.2: ``pasos_1_a_6`` para todos los estación-años → red.a4 → ``pasos_7_a_9`` → ``rachas``.
- Paso 1 (``insumos_anio``): P(s, y), clases del año (tablas.fusionar, que llegan de
  ContextoEstacion.clases), estados anuales de cada línea por clase (estados.estado_de_clase, que exige
  igualdad entre miembros y lanza ErrorFusion), E3p anual con la fina activa o no
  (lineas_fisicas.e3p_anual), E4p sin exclusión ni Q donde falla A3. A4 no se conoce aún: sólo toca a
  E3t, que importa en el paso 7 (R-07).
- Paso 2: discrepante si una línea que decide (no térmica; E4p sólo donde A3 no falla) señala reloj
  anómalo en el año, o si falla G-versión.
- Paso 3: H′ excluida si una línea no térmica la declara incompatible en el año. E3t nunca excluye.
- Paso 4: K = ∅ → discrepante («líneas en conflicto» con las exclusiones); |K| ≥ 2 → insuficiente.
- Paso 5: K = {H}: falla E3d, P7, T-P (si se evalúa: E3p compatible con H) o E4t → discrepante.
- Paso 7: apoyo discriminante contra R_min(H) (tablas.rivales_mas_cercanas, sobre todas las clases de P):
  ≥ 2 líneas, ≥ 2 familias, ≥ 1 Q; E3t sólo en modo completo y sin «desfase térmico local».
- Paso 8: cobertura de mín(3, meses con datos) meses con apoyo propio (E2, E3p, E4p, E6 por parte o mes).
- §5.3: rachas por intersección acumulada de clases; inestabilidad; cambios con ≥ 2 años por racha;
  cuarentena de 1 mes con datos; meses con regla.
Depende de: tipos, estados, umbrales, constantes, tablas, numerico (generador) y lineas_fisicas (e3p_anual).

Contratos que este módulo lee de otros (van al informe de la ola y al addendum de C1):
- Estado anual de cada línea = sus filas ``nivel = anio`` del año (una por H; repetidas → error). E3p es la
  excepción: su estado anual sale de ``lineas_fisicas.e3p_anual(gruesa, fina, fina_activa)`` con las filas
  «gruesa» del año y las «fina» del año más las de nivel estación; se usan las filas ``anio`` de su salida, y
  sus partes si las trae (si no, las partes «gruesa» de entrada). ``fina_activa`` = A3 no falla en la
  macrozona y no hay fila de la fina con ``nivel = estacion`` y ``motivo = apagada``.
- Guardas (ESQUEMA_GUARDAS): ``guarda`` = valor de Linea («E3d», «P7», «T-P», «E4t», «G-version»), ``H`` = id
  de hipótesis o «*» si no depende de H; resultado por año = falla si alguna unidad falla, pasa si alguna
  pasa, no_evaluable si no. ``DecisionAnio.guardas`` lleva G-versión siempre y las del paso 5 sólo con
  K = {H}; T-P queda «no_evaluable» si no se cumplen las condiciones de año (lo que cuenta red.a4).
- Marca «desfase térmico local» (ESQUEMA_MARCAS): ``marca = "desfase_termico_local"``, ``H`` = id de
  hipótesis o «*», ``valor`` = δt en horas (mediana de δt_R; None o NaN si no está definido) o un booleano
  ya resuelto. Rige sólo si T-P se evaluó y pasó, y con |δt| > DTL_DELTA_H (§4.7).
- Una parte (o mes, en E6) es discordante para la clase si alguna fila parcial de sus miembros lleva
  ``discordante``. Sus meses quedan sin regla (§5.3.5).

Lecturas propias (addendum de C1):
- Las líneas que pueden señalar reloj anómalo en el paso 2 son las que pueden excluir (no térmicas; E4p
  no, donde falla A3). E4p nunca señala anomalía (§4.4), así que da igual en la práctica.
- Paso 7: «al menos una Q» con E4p no Q donde falla A3, aunque siga apoyando como presión-marea (R-27).
- §5.3.1: «sin contar los civil con reglas vencidas» se aplica al numerador; el denominador son todos los
  años con datos.
- §5.3.1: los relojes de la sucesión de rachas se agrupan por intersección (la de cada grupo se angosta
  al sumar una racha); «vuelve a uno anterior» = una racha cae en un grupo que no es el de la racha previa.
- §5.3.3-4: el cambio entre la racha A y la B queda entre el último año de A y el primero de B; su
  cuarentena es el último mes con datos hasta fin del último año de A y el primero desde el primer año
  de B. La de un año discrepante, el último mes con datos antes de su enero y el primero después de su
  diciembre.
- R-47: un año «sin_confirmar» de entrada (A6) corta la racha como un insuficiente.
- La clase de un mes con regla es la clase confirmada de su año (en 2015, «F(-3)|C(Santiago)»).

Implementan la Enmienda 1, adoptada y anclada en APH 81bb100 (se marcan «E1-2» y «E1-4» en el código):
- E1-2: en modo completo, la incompatibilidad de E3t cuenta para el apoyo del paso 7; nunca excluye en
  el paso 3.
- E1-4: en el diagnóstico de reglas vencidas se aplican los pasos 2 a 4 a P ∪ {C_venc}; la marca sólo
  cambia la cuenta de inestabilidad (el año sigue discrepante: corta rachas y pone cuarentena).

Enmienda 3, E3-2 (opción A′, adoptada el 2026-10-24): §5.3, punto 1, con una tercera condición, «o tiene el
patrón de regla vencida de §4.1.1» (argumento ``patron_regla_vencida`` de ``rachas``; motivo «civil con
reglas vencidas»). Los años con un evento de regla vencida ausente ya llegan discrepantes por el paso 2
(E1a señala reloj anómalo; lineas_registro, lectura 9) y no llevan la marca de §4.1.4, así que cuentan para
la primera condición; la tercera deja la estación inestable aunque sean pocos.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from reloj_dmc import constantes, estados, lineas_fisicas, numerico, tablas
from reloj_dmc.estados import ErrorFusion
from reloj_dmc.tipos import (ESQUEMA_ESTADOS, ESQUEMA_GUARDAS, ESQUEMA_MARCAS, ESQUEMA_MES, ESQUEMA_RACHAS,
                             GUARDAS_DE_DECISION, LINEAS, LINEAS_DE_APOYO, LINEAS_DE_COBERTURA, ClaseH,
                             ConsecuenciasRed, DecisionAnio, Estado, EvidenciaEstacion, Hipotesis, Linea,
                             ModoE3t, MotivoAnio, MotivoSinInfo, Nivel, Regla, ResultadoGuarda, Veredicto,
                             interseccion_de_clases, tabla_vacia, validar_esquema)
from reloj_dmc.umbrales import Umbrales

MARCA_DESFASE_TERMICO_LOCAL = "desfase_termico_local"   # §4.7, T-P
# Enmienda 3, E3-2 (opción A′): motivo de la tercera condición de §5.3, punto 1.
MOTIVO_INESTABLE_REGLAS_VENCIDAS = "civil con reglas vencidas"
H_TODAS = "*"                                           # guarda o marca que no depende de H
SEPARADOR_CLASE = "|"
NIVELES_PARCIALES = tuple(str(n) for n in estados.NIVELES_PARCIALES)

MOTIVO_GUARDA = {Linea.E3D: MotivoAnio.GUARDA_E3D, Linea.P7: MotivoAnio.GUARDA_P7,
                 Linea.TP: MotivoAnio.GUARDA_TP, Linea.E4T: MotivoAnio.GUARDA_E4T}

# Columnas de InsumosAnio.estados_anuales: una fila por línea de apoyo y clase.
COLUMNAS_ANUALES = ("linea", "familia", "clase", "estado", "reloj_anomalo", "excluye", "cuantitativa")


# ---------------------------------------------------------------------------------------------
# Paso 1: insumos
@dataclass
class InsumosAnio:
    """Lo que necesitan los pasos de §5.1 para un estación-año, ya resuelto por clase."""
    codigo: str
    anio: int
    macrozona: str
    P: tuple[str, ...]
    clases: tuple[object, ...]                       # tipos.ClaseH, en orden canónico
    estados_anuales: pd.DataFrame                    # COLUMNAS_ANUALES (línea × clase → estado, anómalo)
    estados_parciales: pd.DataFrame                  # ESQUEMA_ESTADOS: partes y meses de E2, E3p, E4p y E6
    guardas: pd.DataFrame                            # ESQUEMA_GUARDAS del año
    marcas: pd.DataFrame                             # ESQUEMA_MARCAS del año
    meses_con_datos: tuple[str, ...]                 # «AAAA-MM» con algún artefacto evaluado
    desfase_termico_local: Mapping[str, bool]        # clase → |δt| > DTL_DELTA_H (rige si T-P pasa)
    e4p_activa: bool = True                          # A3 no falla en la macrozona (§5.4)
    fina_activa: bool = True                         # A3 no falla y la fina no está apagada (§4.3.4)


def _ids_miembros(clase: str) -> tuple[str, ...]:
    return tuple(clase.split(SEPARADOR_CLASE))


def _orden_canonico(ids) -> tuple[str, ...]:
    return tuple(sorted(ids, key=lambda h: Hipotesis.desde_id(h).orden()))


def _texto_mes(anio: int, mes: int) -> str:
    return f"{int(anio):04d}-{int(mes):02d}"


def _mes_de_unidad(unidad: str) -> str:
    """«AAAA-MM-n» (parte) o «AAAA-MM» (mes) → «AAAA-MM»."""
    trozos = str(unidad).split("-")
    if len(trozos) < 2 or not all(t.isdigit() for t in trozos):
        raise ValueError(f"unidad que no es parte ni mes: {unidad!r}")
    return "-".join(trozos[:2])


def _indice_mes(mes: str) -> int:
    anio, m = mes.split("-")
    return int(anio) * 12 + int(m) - 1


def _filtrar(df: pd.DataFrame, mascara) -> pd.DataFrame:
    return df[pd.Series(mascara, index=df.index).fillna(False).astype(bool)].reset_index(drop=True)


def _clases_del_anio(evidencia: EvidenciaEstacion, anio: int, clases) -> tuple[ClaseH, ...]:
    """Las clases del año (§2.3). Las calcula orquestacion (ContextoEstacion.clases[anio]) y llegan con el
    argumento ``clases=`` o, si no se pasa, en ``EvidenciaEstacion.clases`` (año → clases). El argumento manda."""
    if clases is None:
        por_anio = evidencia.clases
        if por_anio is None or anio not in por_anio:
            raise ValueError("insumos_anio necesita las clases del año (ContextoEstacion.clases[anio]): "
                             "páselas con clases=…")
        clases = por_anio[anio]
    clases = tuple(clases)
    if not clases or not all(isinstance(c, ClaseH) for c in clases):
        raise ValueError("las clases deben ser tipos.ClaseH (al menos una)")
    return clases


def _comprobar_particion(clases: Sequence[ClaseH], ids_P: Sequence[str]) -> None:
    vistos: list[str] = [h for c in clases for h in c.ids_miembros]
    if len(vistos) != len(set(vistos)) or set(vistos) != set(ids_P):
        raise ValueError(f"las clases {[c.id for c in clases]} no son una partición de P = {list(ids_P)}")


def _e3p_anual(estados_estacion: pd.DataFrame, anio: int, fina_activa_red: bool,
               ids_h: Sequence[str]) -> tuple[pd.DataFrame, bool]:
    """E3p del año desde lineas_fisicas.e3p_anual (§4.3.4); devuelve (filas del año, fina activa).
    Entran las filas de las H de ``ids_h`` y las que no dependen de H («*», p. ej. el apagado)."""
    e = estados_estacion
    e3p = _filtrar(e, (e["linea"] == str(Linea.E3P)) & e["H"].isin([*ids_h, H_TODAS]))
    otras = sorted(set(e3p["regla"]) - {str(Regla.GRUESA), str(Regla.FINA)})
    if otras:
        raise ValueError(f"E3p con reglas distintas de gruesa y fina: {otras}")
    gruesa = _filtrar(e3p, (e3p["regla"] == str(Regla.GRUESA)) & (e3p["anio"] == anio))
    fina = _filtrar(e3p, (e3p["regla"] == str(Regla.FINA))
                    & ((e3p["anio"] == anio) | (e3p["nivel"] == str(Nivel.ESTACION))))
    apagada = bool(((fina["nivel"] == str(Nivel.ESTACION))
                    & (fina["motivo"] == str(MotivoSinInfo.APAGADA)).fillna(False)).any())
    fina_activa = bool(fina_activa_red) and not apagada
    if gruesa.empty and fina.empty:
        return tabla_vacia(ESQUEMA_ESTADOS), fina_activa
    salida = lineas_fisicas.e3p_anual(gruesa, fina, fina_activa)
    validar_esquema(salida, ESQUEMA_ESTADOS, nombre="lineas_fisicas.e3p_anual")
    return _filtrar(salida, (salida["anio"] == anio) & (salida["linea"] == str(Linea.E3P))), fina_activa


def _filas_por_linea(estados_anio: pd.DataFrame, e3p: pd.DataFrame, linea: Linea) -> pd.DataFrame:
    if linea == Linea.E3P:
        return e3p
    return _filtrar(estados_anio, estados_anio["linea"] == str(linea))


def _anuales(estados_anio: pd.DataFrame, e3p: pd.DataFrame, clases: Mapping[str, tuple[str, ...]],
             e4p_activa: bool) -> pd.DataFrame:
    """Estado anual de cada línea de apoyo para cada clase (estados.estado_de_clase)."""
    filas = []
    for linea in LINEAS_DE_APOYO:
        de_linea = _filas_por_linea(estados_anio, e3p, linea)
        anual = _filtrar(de_linea, de_linea["nivel"] == str(Nivel.ANIO))
        if anual["H"].duplicated().any():
            raise ValueError(f"{linea}: más de una fila anual por H en el año {sorted(set(anual['anio']))}")
        por_h = dict(zip(anual["H"], anual["estado"]))
        anomalo = bool(anual["reloj_anomalo"].any())
        props = LINEAS[linea]
        activa = linea != Linea.E4P or e4p_activa               # §5.4, A3: E4p deja de excluir y de ser Q
        for clase, miembros in clases.items():
            try:
                estado = estados.estado_de_clase({h: por_h.get(h, Estado.SIN_INFORMACION) for h in miembros})
            except ErrorFusion as e:
                raise ErrorFusion(f"{linea}, clase {clase}: {e}") from None
            filas.append({"linea": str(linea), "familia": str(props.familia), "clase": clase, "estado": str(estado),
                          "reloj_anomalo": anomalo, "excluye": bool(props.excluye and activa),
                          "cuantitativa": bool(props.cuantitativa and activa)})
    return pd.DataFrame(filas, columns=list(COLUMNAS_ANUALES))


def _parciales(estados_anio: pd.DataFrame, e3p: pd.DataFrame) -> pd.DataFrame:
    """Filas de parte (o mes) de las líneas de cobertura; las de E3p, de la salida de e3p_anual si las trae."""
    marcos = []
    for linea in LINEAS_DE_COBERTURA:
        de_linea = _filas_por_linea(estados_anio, e3p, linea)
        parcial = _filtrar(de_linea, de_linea["nivel"].isin(NIVELES_PARCIALES))
        if linea == Linea.E3P and parcial.empty:
            crudas = _filtrar(estados_anio, (estados_anio["linea"] == str(Linea.E3P))
                              & (estados_anio["regla"] == str(Regla.GRUESA)))
            parcial = _filtrar(crudas, crudas["nivel"].isin(NIVELES_PARCIALES))
        marcos.append(parcial)
    marcos = [m for m in marcos if not m.empty]
    if not marcos:
        return tabla_vacia(ESQUEMA_ESTADOS)
    return pd.concat(marcos, ignore_index=True).astype(ESQUEMA_ESTADOS)


def _valor_dtl(valor, umbral: float) -> bool:
    if isinstance(valor, (bool, np.bool_)):
        return bool(valor)
    if valor is None or valor is pd.NA:
        return False
    try:
        delta = float(valor)
    except (TypeError, ValueError):
        raise ValueError(f"valor de «{MARCA_DESFASE_TERMICO_LOCAL}» no numérico: {valor!r}") from None
    return delta == delta and abs(delta) > umbral          # NaN → sin marca


def _dtl_de_clase(marcas: pd.DataFrame, clase: str, miembros: tuple[str, ...], umbral: float) -> bool:
    filas = _filtrar(marcas, marcas["marca"] == MARCA_DESFASE_TERMICO_LOCAL)
    por_miembro = []
    for h in miembros:
        valores = [v for hh, v in zip(filas["H"], filas["valor"]) if hh in (h, H_TODAS)]
        por_miembro.append(any(_valor_dtl(v, umbral) for v in valores))
    if len(set(por_miembro)) != 1:
        raise ErrorFusion(f"clase {clase}: «{MARCA_DESFASE_TERMICO_LOCAL}» distinta entre sus miembros")
    return por_miembro[0]


def insumos_anio(evidencia: EvidenciaEstacion, anio: int, consecuencias: ConsecuenciasRed,
                 umbrales: Umbrales, *, clases: Sequence[ClaseH] | None = None) -> InsumosAnio:
    """Paso 1. ``clases`` son las del año (ContextoEstacion.clases[anio]; ver _clases_del_anio)."""
    info = evidencia.info
    for tabla, esquema, nombre in ((evidencia.estados, ESQUEMA_ESTADOS, "estados"),
                                   (evidencia.guardas, ESQUEMA_GUARDAS, "guardas"),
                                   (evidencia.marcas, ESQUEMA_MARCAS, "marcas"),
                                   (evidencia.meses, ESQUEMA_MES, "meses")):
        validar_esquema(tabla, esquema, nombre=f"evidencia.{nombre}")
    anio = int(anio)
    ids_P = tuple(h.id for h in info.P)
    clases_ = _clases_del_anio(evidencia, anio, clases)
    _comprobar_particion(clases_, ids_P)
    miembros = {c.id: tuple(h.id for h in c.miembros) for c in clases_}

    e = evidencia.estados
    otras = sorted(set(e["codigo"]) - {info.codigo})
    if otras:
        raise ValueError(f"estados de otras estaciones: {otras}")
    del_anio = _filtrar(e, (e["anio"] == anio) & e["H"].isin(ids_P))
    e3p, fina_activa = _e3p_anual(e, anio, consecuencias.fina_activa(info.macrozona), ids_P)
    e4p_activa = consecuencias.e4p_activa(info.macrozona)

    g, m, meses = evidencia.guardas, evidencia.marcas, evidencia.meses
    marcas = _filtrar(m, m["anio"] == anio)
    entran = _filtrar(meses, (meses["anio"] == anio) & meses["entra"])
    umbral_dtl = umbrales.f("DTL_DELTA_H")
    return InsumosAnio(
        codigo=info.codigo, anio=anio, macrozona=info.macrozona, P=ids_P, clases=clases_,
        estados_anuales=_anuales(del_anio, e3p, miembros, e4p_activa),
        estados_parciales=_parciales(del_anio, e3p),
        guardas=_filtrar(g, g["anio"] == anio), marcas=marcas,
        meses_con_datos=tuple(sorted({_texto_mes(a, ms) for a, ms in zip(entran["anio"], entran["mes"])})),
        desfase_termico_local={c: _dtl_de_clase(marcas, c, h, umbral_dtl) for c, h in miembros.items()},
        e4p_activa=e4p_activa, fina_activa=fina_activa)


# ---------------------------------------------------------------------------------------------
# Pasos 2 a 6
def _estado_anual(anuales: pd.DataFrame, linea: Linea, clase: str) -> Estado:
    fila = anuales[(anuales["linea"] == str(linea)) & (anuales["clase"] == clase)]
    return Estado(fila["estado"].iloc[0]) if len(fila) else Estado.SIN_INFORMACION


def _lineas_anomalas(anuales: pd.DataFrame) -> tuple[str, ...]:
    """Paso 2: líneas que deciden (pueden excluir) y señalan reloj anómalo en el año. E3t no (§4.3.3)."""
    a = anuales[anuales["excluye"] & anuales["reloj_anomalo"]]
    return tuple(dict.fromkeys(a["linea"]))


def _exclusiones(anuales: pd.DataFrame, clases: Sequence[str]) -> tuple[dict[str, tuple[str, ...]], tuple[str, ...]]:
    """Paso 3: clase → líneas no térmicas que la declaran incompatible; K = las no excluidas, en orden.
    E3t tiene ``excluye`` falso: nunca excluye (§4.3.3; E1-2)."""
    excluidas: dict[str, tuple[str, ...]] = {}
    for clase in clases:
        f = anuales[(anuales["clase"] == clase) & anuales["excluye"]
                    & (anuales["estado"] == str(Estado.INCOMPATIBLE))]
        if len(f):
            excluidas[clase] = tuple(f["linea"])
    return excluidas, tuple(c for c in clases if c not in excluidas)


def _agregar_guarda(resultados) -> ResultadoGuarda:
    vistos = {ResultadoGuarda(r) for r in resultados}
    if ResultadoGuarda.FALLA in vistos:
        return ResultadoGuarda.FALLA
    if ResultadoGuarda.PASA in vistos:
        return ResultadoGuarda.PASA
    return ResultadoGuarda.NO_EVALUABLE


def _guarda_de_clase(guardas: pd.DataFrame, guarda: Linea, clase: str) -> ResultadoGuarda:
    filas = guardas[guardas["guarda"] == str(guarda)]
    por_miembro = [_agregar_guarda(filas.loc[filas["H"].isin([h, H_TODAS]), "resultado"])
                   for h in _ids_miembros(clase)]
    if len(set(por_miembro)) != 1:
        raise ErrorFusion(f"{guarda}, clase {clase}: resultados distintos entre sus miembros {por_miembro}")
    return por_miembro[0]


def _discordantes(parciales: pd.DataFrame, clase: str | None) -> tuple[str, ...]:
    """Partes (o meses) discordantes para la clase; sin clase, las discordantes por reloj anómalo."""
    if clase is None:
        f = parciales[parciales["discordante"] & parciales["reloj_anomalo"]]
    else:
        f = parciales[parciales["discordante"] & parciales["H"].isin(_ids_miembros(clase))]
    return tuple(sorted(set(f["unidad"])))


def _base(insumos: InsumosAnio) -> dict:
    return {"codigo": insumos.codigo, "anio": insumos.anio, "P": tuple(insumos.P),
            "clases": tuple(c.id for c in insumos.clases), "meses_con_datos": tuple(insumos.meses_con_datos)}


def _texto_exclusiones(excluidas: Mapping[str, tuple[str, ...]]) -> str:
    return "; ".join(f"{c}: {', '.join(l)}" for c, l in excluidas.items())


def pasos_1_a_6(insumos: InsumosAnio, umbrales: Umbrales) -> DecisionAnio:
    """Primera pasada; el veredicto queda provisional (CONFIRMADO = «K = {H} y guardas pasan»)."""
    base = _base(insumos)
    if not insumos.meses_con_datos:
        return DecisionAnio(**base, excluidas={}, K=(), veredicto=Veredicto.SIN_DATOS)
    anuales = insumos.estados_anuales
    clases = base["clases"]
    excluidas, K = _exclusiones(anuales, clases)
    base.update(excluidas=excluidas, K=K)

    # Paso 2: reloj anómalo o G-versión (no depende de H).
    g_version = _agregar_guarda(insumos.guardas.loc[insumos.guardas["guarda"] == str(Linea.G_VERSION), "resultado"])
    guardas = {str(Linea.G_VERSION): str(g_version)}
    anomalas = _lineas_anomalas(anuales)
    if anomalas or g_version == ResultadoGuarda.FALLA:
        motivos = []
        if anomalas:
            motivos.append("reloj anómalo en " + ", ".join(anomalas))
        if g_version == ResultadoGuarda.FALLA:
            motivos.append("falla G-versión")
        return DecisionAnio(**base, veredicto=Veredicto.DISCREPANTE,
                            motivo=MotivoAnio.RELOJ_ANOMALO if anomalas else MotivoAnio.G_VERSION,
                            detalle="; ".join(motivos), guardas=guardas,
                            partes_discordantes=_discordantes(insumos.estados_parciales, None))

    # Paso 4: K vacío o múltiple.
    if not K:
        return DecisionAnio(**base, veredicto=Veredicto.DISCREPANTE, motivo=MotivoAnio.LINEAS_EN_CONFLICTO,
                            detalle="líneas en conflicto: " + _texto_exclusiones(excluidas), guardas=guardas,
                            partes_discordantes=_discordantes(insumos.estados_parciales, None))
    if len(K) > 1:
        return DecisionAnio(**base, veredicto=Veredicto.INSUFICIENTE, motivo=MotivoAnio.NO_DISTINGUE,
                            detalle="no distingue entre " + ", ".join(K), guardas=guardas,
                            partes_discordantes=_discordantes(insumos.estados_parciales, None))

    # Paso 5: guardas con K = {H}. T-P se evalúa sólo con E3p compatible con H (§4.7); en ambos modos de E3t.
    H = K[0]
    for guarda in GUARDAS_DE_DECISION:
        if guarda == Linea.TP and _estado_anual(anuales, Linea.E3P, H) != Estado.COMPATIBLE:
            resultado = ResultadoGuarda.NO_EVALUABLE
        else:
            resultado = _guarda_de_clase(insumos.guardas, guarda, H)
        guardas[str(guarda)] = str(resultado)
    discordantes = _discordantes(insumos.estados_parciales, H)
    fallan = [g for g in GUARDAS_DE_DECISION if guardas[str(g)] == str(ResultadoGuarda.FALLA)]
    if fallan:
        return DecisionAnio(**base, veredicto=Veredicto.DISCREPANTE, motivo=MOTIVO_GUARDA[fallan[0]],
                            detalle=f"{H}: falla " + ", ".join(str(g) for g in fallan), guardas=guardas,
                            partes_discordantes=discordantes)
    # Paso 6: G-dup no interviene (§5.4).
    return DecisionAnio(**base, veredicto=Veredicto.CONFIRMADO, detalle="provisional: K = {H} y guardas pasan",
                        guardas=guardas, partes_discordantes=discordantes)


# ---------------------------------------------------------------------------------------------
# Pasos 7 a 9
def _apoyo(insumos: InsumosAnio, clase: ClaseH, modo: ModoE3t, dtl: bool) -> list[tuple[str, str, bool]]:
    """Paso 7: (línea, familia, Q) de cada línea compatible con H en el año e incompatible con alguna
    H′ de R_min(H). E3t sólo en modo completo y sin «desfase térmico local»; con E1-2 su
    incompatibilidad cuenta aquí (nunca en el paso 3)."""
    anuales = insumos.estados_anuales
    rivales = tablas.rivales_mas_cercanas(clase, tuple(insumos.clases))
    lineas = []
    for linea in LINEAS_DE_APOYO:
        cuantitativa = bool(anuales.loc[anuales["linea"] == str(linea), "cuantitativa"].any())
        if linea == Linea.E3T:
            if modo != ModoE3t.COMPLETO or dtl:
                continue
            cuantitativa = True                               # §4.0: Q sólo en modo completo
        if _estado_anual(anuales, linea, clase.id) != Estado.COMPATIBLE:
            continue
        if any(_estado_anual(anuales, linea, r.id) == Estado.INCOMPATIBLE for r in rivales):
            lineas.append((str(linea), str(LINEAS[linea].familia), cuantitativa))
    return lineas


def _meses_con_apoyo(insumos: InsumosAnio, clase: str, lineas_apoyo: Sequence[str]) -> tuple[str, ...]:
    """Paso 8: meses con una parte (o mes, en E6) compatible con H de alguna línea de apoyo de cobertura."""
    p = insumos.estados_parciales
    meses = set()
    for linea in LINEAS_DE_COBERTURA:
        if str(linea) not in lineas_apoyo:
            continue
        de_linea = p[(p["linea"] == str(linea)) & p["H"].isin(_ids_miembros(clase))]
        for unidad, filas in de_linea.groupby("unidad", sort=True):
            por_h = dict(zip(filas["H"], filas["estado"]))
            try:
                estado = estados.estado_de_clase({h: por_h.get(h, Estado.SIN_INFORMACION)
                                                  for h in _ids_miembros(clase)})
            except ErrorFusion as e:
                raise ErrorFusion(f"{linea}, {unidad}, clase {clase}: {e}") from None
            if estado == Estado.COMPATIBLE:
                meses.add(_mes_de_unidad(unidad))
    return tuple(sorted(meses))


def _marcas_de_clase(marcas: pd.DataFrame, clase: str) -> dict[str, object]:
    salida: dict[str, object] = {}
    primero = _ids_miembros(clase)[0]
    for marca, h, valor in zip(marcas["marca"], marcas["H"], marcas["valor"]):
        if h in (primero, H_TODAS) and marca not in salida:
            salida[marca] = valor
    return salida


def pasos_7_a_9(parcial: DecisionAnio, insumos: InsumosAnio, consecuencias: ConsecuenciasRed,
                umbrales: Umbrales) -> DecisionAnio:
    """Segunda pasada, con A4 ya fijado en ``consecuencias``."""
    if consecuencias.a4_restringe is None:
        raise ValueError("pasos_7_a_9 exige A4 calculado (consecuencias.a4_restringe no es None)")
    if (parcial.codigo, parcial.anio) != (insumos.codigo, insumos.anio):
        raise ValueError("la decisión parcial y los insumos son de estación-años distintos")
    modo = consecuencias.modo_e3t_en(insumos.macrozona)
    if parcial.veredicto != Veredicto.CONFIRMADO:
        return replace(parcial, modo_e3t=modo)
    if len(parcial.K) != 1:
        raise ValueError("una decisión parcial confirmada debe tener K = {H}")
    H = parcial.K[0]
    clase = next(c for c in insumos.clases if c.id == H)
    dtl = (parcial.guardas.get(str(Linea.TP)) == str(ResultadoGuarda.PASA)
           and bool(insumos.desfase_termico_local.get(H, False)))
    marcas = {**_marcas_de_clase(insumos.marcas, H), MARCA_DESFASE_TERMICO_LOCAL: dtl}

    # Paso 7: apoyo discriminante.
    apoyo = _apoyo(insumos, clase, modo, dtl)
    lineas = tuple(l for l, _, _ in apoyo)
    familias = tuple(dict.fromkeys(f for _, f, _ in apoyo))
    n_q = sum(1 for _, _, q in apoyo if q)
    min_lineas, min_familias = constantes.valor("APOYO_MINIMOS")
    traza = {"lineas_apoyo": lineas, "familias_apoyo": familias, "n_lineas_q": n_q, "modo_e3t": modo,
             "marcas": marcas}
    if len(lineas) < min_lineas or len(familias) < min_familias or n_q < 1:
        return replace(parcial, veredicto=Veredicto.INSUFICIENTE, motivo=MotivoAnio.APOYO,
                       detalle=f"{H}: apoyo de {len(lineas)} líneas, {len(familias)} familias y {n_q} Q "
                               f"contra {', '.join(r.id for r in tablas.rivales_mas_cercanas(clase, insumos.clases))}",
                       **traza)

    # Paso 8: cobertura.
    meses_apoyo = _meses_con_apoyo(insumos, H, lineas)
    exigidos = min(umbrales.f("COBERTURA_MESES"), len(insumos.meses_con_datos))
    if len(meses_apoyo) < exigidos:
        return replace(parcial, veredicto=Veredicto.INSUFICIENTE, motivo=MotivoAnio.COBERTURA,
                       detalle=f"{H}: {len(meses_apoyo)} meses con apoyo propio de {exigidos} exigidos",
                       meses_con_apoyo=meses_apoyo, **traza)

    # Paso 9: confirmado(H).
    return replace(parcial, veredicto=Veredicto.CONFIRMADO, motivo=None, detalle=None, clase_confirmada=H,
                   meses_con_apoyo=meses_apoyo, **traza)


def decidir_anio(evidencia: EvidenciaEstacion, anio: int, consecuencias: ConsecuenciasRed,
                 umbrales: Umbrales, *, clases: Sequence[ClaseH] | None = None) -> DecisionAnio:
    """Nombre de §9: ambas pasadas seguidas para un año (exige ``consecuencias.a4_restringe`` conocido)."""
    if consecuencias.a4_restringe is None:
        raise ValueError("decidir_anio exige A4 calculado (consecuencias.a4_restringe no es None)")
    insumos = insumos_anio(evidencia, anio, consecuencias, umbrales, clases=clases)
    return pasos_7_a_9(pasos_1_a_6(insumos, umbrales), insumos, consecuencias, umbrales)


# ---------------------------------------------------------------------------------------------
# §5.3: rachas, cambios, cuarentena y meses con regla
@dataclass
class ResultadoRachas:
    rachas: pd.DataFrame                    # ESQUEMA_RACHAS
    decisiones: list[DecisionAnio]          # con SIN_CONFIRMAR donde corresponde (§5.3.1, §5.3.3)
    inestable: bool
    cambios: list[tuple[int, int]]          # (último año de la racha anterior, primer año de la siguiente)
    cuarentena: frozenset[str]              # «AAAA-MM»
    meses_con_regla: Mapping[str, str]      # «AAAA-MM» → id de clase
    motivos_inestable: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class _Racha:
    anios: list[int]
    clase: frozenset[str]                   # intersección acumulada de los ids de miembros


def _sucesion_de_rachas(decisiones: Sequence[DecisionAnio]) -> list[_Racha]:
    """§5.3.2: sucesiones máximas de confirmados con intersección acumulada no vacía; los años sin datos
    no cortan; un discrepante, un insuficiente o un sin confirmar (A6, R-47) con datos, sí."""
    lista: list[_Racha] = []
    actual: _Racha | None = None
    for d in decisiones:
        if d.veredicto == Veredicto.SIN_DATOS:
            continue
        if d.veredicto != Veredicto.CONFIRMADO:
            if actual is not None:
                lista.append(actual)
                actual = None
            continue
        if not d.clase_confirmada:
            raise ValueError(f"{d.codigo} {d.anio}: confirmado sin clase")
        miembros = frozenset(_ids_miembros(d.clase_confirmada))
        if actual is not None:
            comun = interseccion_de_clases(actual.clase, miembros)
            if comun:
                actual.anios.append(d.anio)
                actual.clase = comun
                continue
            lista.append(actual)
        actual = _Racha([d.anio], miembros)
    if actual is not None:
        lista.append(actual)
    return lista


def _relojes(lista: Sequence[_Racha]) -> tuple[int, bool]:
    """§5.3.1: número de relojes distintos de la sucesión (por intersección) y si vuelve a uno anterior."""
    grupos: list[frozenset[str]] = []
    anterior, regreso = None, False
    for racha in lista:
        coinciden = [i for i, g in enumerate(grupos) if g & racha.clase]
        if not coinciden:
            grupos.append(racha.clase)
            actual = len(grupos) - 1
        else:
            actual = anterior if anterior in coinciden else coinciden[0]
            regreso = regreso or actual != anterior
            grupos[actual] = grupos[actual] & racha.clase
        anterior = actual
    return len(grupos), regreso


def _vecinos(meses_datos: Sequence[str], hasta: str | None, desde: str | None, n: int) -> list[str]:
    """Los n meses con datos anteriores a ``hasta`` (exclusive) o los n desde ``desde`` (inclusive)."""
    if hasta is not None:
        return [m for m in meses_datos if m < hasta][-n:] if n > 0 else []
    return [m for m in meses_datos if m >= desde][:n]


def rachas(decisiones: Sequence[DecisionAnio], meses: pd.DataFrame, partes_discordantes: frozenset[str],
           umbrales: Umbrales, *, patron_regla_vencida: bool = False) -> ResultadoRachas:
    """Nombre de §9: §5.3 puntos 1 a 5 para una estación (rachas por intersección acumulada de clases;
    los años sin datos no cortan; inestable con ≥ 3 discrepantes y > 20 % sin contar reglas vencidas, o
    con ≥ 3 relojes o regreso; cambio sin respaldo; cuarentena de 1 mes con datos; meses con regla).

    ``partes_discordantes`` son ids de parte («AAAA-MM-n») o de mes («AAAA-MM») de la estación; se unen a
    las de cada decisión. ``meses`` es la ESQUEMA_MES de la estación (mes con datos = ``entra``).
    ``patron_regla_vencida`` (Enmienda 3, E3-2, opción A′): la estación tiene el patrón de regla vencida
    de §4.1.1 (lineas_registro.patron_regla_vencida); es la tercera condición de §5.3, punto 1, con el
    motivo «civil con reglas vencidas»."""
    if not decisiones:
        return ResultadoRachas(tabla_vacia(ESQUEMA_RACHAS), [], False, [], frozenset(), {})
    codigos = {d.codigo for d in decisiones}
    if len(codigos) != 1:
        raise ValueError(f"rachas recibe decisiones de una sola estación: {sorted(codigos)}")
    codigo = codigos.pop()
    orden = sorted(decisiones, key=lambda d: d.anio)
    if len({d.anio for d in orden}) != len(orden):
        raise ValueError(f"{codigo}: años repetidos en las decisiones")
    validar_esquema(meses, ESQUEMA_MES, nombre="meses")
    entran = _filtrar(meses, meses["entra"] & (meses["codigo"] == codigo))
    meses_datos = sorted({_texto_mes(a, m) for a, m in zip(entran["anio"], entran["mes"])})

    # 2. Rachas y 3. cambios.
    lista = _sucesion_de_rachas(orden)
    cambios, limita = [], [False] * len(lista)
    for i in range(1, len(lista)):
        if not interseccion_de_clases(lista[i - 1].clase, lista[i].clase):
            cambios.append((lista[i - 1].anios[-1], lista[i].anios[0]))
            limita[i - 1] = limita[i] = True
    sin_respaldo = [limita[i] and len(r.anios) < umbrales.f("RACHA_ANIOS_CAMBIO") for i, r in enumerate(lista)]

    # 1. Inestabilidad. E1-4: los «civil con reglas vencidas» no cuentan (sólo el numerador).
    con_datos = [d for d in orden if d.veredicto != Veredicto.SIN_DATOS]
    discrepantes = [d for d in orden if d.veredicto == Veredicto.DISCREPANTE and not d.reglas_vencidas]
    motivos = []
    if (len(discrepantes) >= umbrales.f("INESTABLE_ANIOS")
            and len(discrepantes) / len(con_datos) > umbrales.frac("INESTABLE_PCT")):
        motivos.append(f"{len(discrepantes)} años discrepantes de {len(con_datos)} con datos")
    n_relojes, regreso = _relojes(lista)
    if n_relojes >= constantes.valor("INESTABLE_RELOJES"):
        motivos.append(f"{n_relojes} relojes distintos")
    if regreso:
        motivos.append("vuelve a un reloj anterior")
    if patron_regla_vencida:                 # Enmienda 3, E3-2 (A′): «o tiene el patrón de regla vencida»
        motivos.append(MOTIVO_INESTABLE_REGLAS_VENCIDAS)
    inestable = bool(motivos)

    # 4. Cuarentena. E1-4: un año con la marca sigue discrepante y también la pone.
    n = int(umbrales.f("CUARENTENA_MESES"))
    cuarentena: set[str] = set()
    for d in orden:
        if d.veredicto == Veredicto.DISCREPANTE:
            cuarentena.update(_vecinos(meses_datos, _texto_mes(d.anio, 1), None, n))
            cuarentena.update(_vecinos(meses_datos, None, _texto_mes(d.anio + 1, 1), n))
    for antes, despues in cambios:
        cuarentena.update(_vecinos(meses_datos, _texto_mes(antes + 1, 1), None, n))
        cuarentena.update(_vecinos(meses_datos, None, _texto_mes(despues, 1), n))

    # Veredictos finales.
    racha_de = {a: i for i, r in enumerate(lista) for a in r.anios}
    finales: list[DecisionAnio] = []
    for d in orden:
        if d.veredicto == Veredicto.CONFIRMADO and inestable:
            d = replace(d, veredicto=Veredicto.SIN_CONFIRMAR, motivo=MotivoAnio.INESTABLE,
                        detalle="estación inestable: " + "; ".join(motivos))
        elif d.veredicto == Veredicto.CONFIRMADO and sin_respaldo[racha_de[d.anio]]:
            d = replace(d, veredicto=Veredicto.SIN_CONFIRMAR, motivo=MotivoAnio.CAMBIO_SIN_RESPALDO,
                        detalle=f"racha de {len(lista[racha_de[d.anio]].anios)} año(s) junto a un cambio de reloj")
        else:
            d = replace(d)
        finales.append(d)

    # 5. Meses con regla.
    discordantes = {_mes_de_unidad(u) for u in partes_discordantes}
    discordantes |= {_mes_de_unidad(u) for d in orden for u in d.partes_discordantes}
    vecindad = umbrales.f("VECINDAD_MESES")
    con_regla: dict[str, str] = {}
    for d in finales:
        if d.veredicto != Veredicto.CONFIRMADO:
            continue
        apoyo = [_indice_mes(m) for m in d.meses_con_apoyo]
        for mes in meses_datos:
            if not mes.startswith(f"{d.anio:04d}-") or mes in cuarentena or mes in discordantes:
                continue
            if any(abs(_indice_mes(mes) - a) <= vecindad for a in apoyo):
                con_regla[mes] = d.clase_confirmada

    filas = []
    for i, r in enumerate(lista):
        motivo = (str(MotivoAnio.INESTABLE) if inestable
                  else str(MotivoAnio.CAMBIO_SIN_RESPALDO) if sin_respaldo[i] else None)
        filas.append({"codigo": codigo, "racha": i + 1, "anio_desde": r.anios[0], "anio_hasta": r.anios[-1],
                      "clase": SEPARADOR_CLASE.join(_orden_canonico(r.clase)), "n_confirmados": len(r.anios),
                      "aceptada": motivo is None, "motivo": motivo})
    tabla = (pd.DataFrame(filas, columns=list(ESQUEMA_RACHAS)).astype(ESQUEMA_RACHAS) if filas
             else tabla_vacia(ESQUEMA_RACHAS))
    return ResultadoRachas(rachas=tabla, decisiones=finales, inestable=inestable, cambios=cambios,
                           cuarentena=frozenset(cuarentena), meses_con_regla=dict(sorted(con_regla.items())),
                           motivos_inestable=tuple(motivos))


# ---------------------------------------------------------------------------------------------
# §4.1.4: diagnóstico de reglas vencidas
def marca_reglas_vencidas(decision: DecisionAnio, estados_con_cv: pd.DataFrame, umbrales: Umbrales, *,
                          e4p_activa: bool = True, fina_activa: bool = True) -> bool:
    """§4.1.4: año discrepante en un año del Anexo A2 en que, agregando Cv(Z, y) a P con las mismas
    reglas, K = {Cv}. ``estados_con_cv`` sale de orquestacion.diagnostico_reglas_vencidas (R-09).

    E1-4 (Enmienda 1, adoptada): se aplican los pasos 2 a 4 de §5.1 a P ∪ {Cv}. Las clases de P son las
    del año (``decision.clases``) y Cv va como clase propia: si coincidiera con C(Z) en todas las
    etiquetas con datos, sus estados serían iguales y K no quedaría en {Cv}. G-versión no depende de H,
    así que su falla también deja discrepante al P ampliado. ``e4p_activa`` y ``fina_activa`` son las
    consecuencias de A3 en la macrozona (las «mismas reglas»). El resultado sólo decide la marca."""
    if decision.veredicto != Veredicto.DISCREPANTE:
        return False
    validar_esquema(estados_con_cv, ESQUEMA_ESTADOS, nombre="estados_con_cv")
    e = _filtrar(estados_con_cv, estados_con_cv["codigo"] == decision.codigo)
    cv = _orden_canonico({h for h in e.loc[e["anio"] == decision.anio, "H"] if Hipotesis.desde_id(h).tipo == "Cv"})
    if not cv:
        return False
    if decision.guardas.get(str(Linea.G_VERSION)) == str(ResultadoGuarda.FALLA):
        return False
    clases = {c: _ids_miembros(c) for c in decision.clases}
    clases.update({h: (h,) for h in cv})
    ids = tuple(h for miembros in clases.values() for h in miembros)
    e3p, _ = _e3p_anual(e, decision.anio, fina_activa, ids)
    del_anio = _filtrar(e, (e["anio"] == decision.anio) & e["H"].isin(ids))
    anuales = _anuales(del_anio, e3p, clases, e4p_activa)
    if _lineas_anomalas(anuales):
        return False
    _, K = _exclusiones(anuales, tuple(clases))
    return len(K) == 1 and K[0] in cv


# ---------------------------------------------------------------------------------------------
# §5.5: expedientes de control
def muestra_expedientes_control(codigos_con_confirmado: Sequence[str], semilla: int, n: int) -> list[str]:
    """§5.5: n estaciones al azar con la semilla sobre la lista ordenada (Generator(PCG64(semilla)).choice
    sin reposición; si hay menos de n, todas). Devuelve los códigos en el orden del sorteo (R-39)."""
    if isinstance(n, bool) or int(n) != n or n < 0:
        raise ValueError(f"n debe ser un entero ≥ 0: {n!r}")
    lista = sorted({str(c) for c in codigos_con_confirmado})
    if len(lista) <= n:
        return lista
    indices = numerico.generador(semilla).choice(len(lista), size=int(n), replace=False)
    return [lista[int(i)] for i in indices]
