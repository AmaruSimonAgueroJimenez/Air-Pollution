"""Álgebra de estados compartida por las líneas y la decisión (§4.0, §2.3).

- Construcción de filas de ESQUEMA_ESTADOS con tipos correctos.
- Estado anual de E2, E3p (regla gruesa) y E6 desde sus partes o meses y sus años-régimen (§4.0):
  incompatible si lo es en algún año-régimen (E2, E3p) o en el año (E6), o en ≥ 2 partes (E6: meses);
  anómalo si lo es en algún año-régimen o en ≥ 2 partes; una sola parte incompatible o anómala es
  discordante (no cambia el estado anual; deja su mes sin regla, §5.3).
- Combinación de sub-evaluaciones de una misma línea (varias zonas de Zs, varios eventos):
  incompatible > compatible > dudosa > sin_informacion (lectura R-10).
- Estado de una clase fusionada: el de sus miembros, que deben coincidir (si no, ErrorFusion).
Depende de: tipos.
"""
from __future__ import annotations

from typing import Iterable, Mapping

import pandas as pd

from reloj_dmc.tipos import ESQUEMA_ESTADOS, Estado, Linea, Nivel, Regla

# Niveles que entran a anual_por_partes: los «parciales» cuentan para la regla de ≥ 2 partes y pueden
# ser discordantes; los «agregados» deciden solos (año-régimen en E2 y E3p; el año en E6).
NIVELES_PARCIALES = (Nivel.PARTE, Nivel.MES)
NIVELES_AGREGADOS = (Nivel.REGIMEN, Nivel.ANIO)

# Prioridad de la combinación de sub-evaluaciones (R-10), de menor a mayor: gana la última.
_ORDEN_COMBINAR = (Estado.SIN_INFORMACION, Estado.DUDOSA, Estado.COMPATIBLE, Estado.INCOMPATIBLE)
_PRIORIDAD = {estado: i for i, estado in enumerate(_ORDEN_COMBINAR)}


class ErrorFusion(RuntimeError):
    """Dos miembros de una clase fusionada recibieron estados distintos: error de implementación."""


def _vacia() -> pd.DataFrame:
    return pd.DataFrame({col: pd.Series(dtype=tipo) for col, tipo in ESQUEMA_ESTADOS.items()})


def _marco(filas: list[dict]) -> pd.DataFrame:
    """DataFrame con exactamente las columnas, el orden y los tipos de ESQUEMA_ESTADOS."""
    if not filas:
        return _vacia()
    return pd.DataFrame(filas, columns=list(ESQUEMA_ESTADOS)).astype(ESQUEMA_ESTADOS)


def _estado(valor: Estado | str) -> Estado:
    try:
        return Estado(valor)
    except ValueError:
        raise ValueError(f"estado desconocido: {valor!r}") from None


def filas_estado(codigo: str, anio: int, linea: Linea, nivel: Nivel, unidad: str,
                 estados: Mapping[str, Estado], *, regla: Regla = Regla.UNICA, reloj_anomalo: bool = False,
                 discordante: bool = False, motivo: str | None = None) -> pd.DataFrame:
    """Una fila por H con el esquema ESQUEMA_ESTADOS.

    ``estados`` va de id de **hipótesis** a estado; un id de clase («…|…») lanza ValueError, porque las
    líneas evalúan hipótesis, nunca clases (§2.1 del diseño). El orden de las filas es el del mapeo.
    ``motivo`` None queda como <NA>.
    """
    linea, nivel, regla = Linea(linea), Nivel(nivel), Regla(regla)
    filas = []
    for h, estado in estados.items():
        if not isinstance(h, str) or not h or "|" in h:
            raise ValueError(f"H debe ser el id de una hipótesis, no {h!r}")
        filas.append({
            "codigo": codigo, "anio": int(anio), "linea": str(linea), "regla": str(regla),
            "nivel": str(nivel), "unidad": unidad, "H": h, "estado": str(_estado(estado)),
            "reloj_anomalo": bool(reloj_anomalo), "discordante": bool(discordante), "motivo": motivo,
        })
    return _marco(filas)


def _validar_entrada(estados: pd.DataFrame, linea: Linea, regla: Regla) -> pd.DataFrame:
    if list(estados.columns) != list(ESQUEMA_ESTADOS):
        raise ValueError(f"anual_por_partes exige las columnas de ESQUEMA_ESTADOS: {list(estados.columns)}")
    e = estados.astype(ESQUEMA_ESTADOS).reset_index(drop=True)
    if e.empty:
        return e
    if e["codigo"].nunique(dropna=False) != 1:
        raise ValueError("anual_por_partes recibe filas de una sola estación")
    if set(e["linea"]) != {str(linea)} or set(e["regla"]) != {str(regla)}:
        raise ValueError(f"anual_por_partes recibe sólo filas de {linea} con regla {regla}")
    permitidos = {str(n) for n in NIVELES_PARCIALES + NIVELES_AGREGADOS}
    otros = set(e["nivel"]) - permitidos
    if otros:
        raise ValueError(f"niveles no admitidos en anual_por_partes: {sorted(otros)}")
    for valor in set(e["estado"]):
        _estado(valor)
    if e.duplicated(["anio", "nivel", "unidad", "H"]).any():
        raise ValueError("filas repetidas (año, nivel, unidad, H)")
    senal = e.groupby(["anio", "nivel", "unidad"], sort=False)["reloj_anomalo"].nunique()
    if (senal > 1).any():
        raise ValueError("reloj_anomalo es una señal de la unidad: debe repetirse igual en cada H")
    return e


def anual_por_partes(estados: pd.DataFrame, *, linea: Linea, regla: Regla = Regla.UNICA,
                     min_partes: int = 2) -> pd.DataFrame:
    """Estado anual (nivel ANIO) y marca de partes discordantes según §4.0.

    Entrada: filas de una estación y una línea con nivel PARTE (o MES para E6) y REGIMEN.
    Salida: filas nivel ANIO (una por año y H) con ``reloj_anomalo`` anual, más las mismas filas de
    entrada con ``discordante`` recalculado. La compatibilidad anual NO se decide aquí (cada línea
    tiene su regla: E2 §4.2, E3p §4.3.4, E6 §4.6); aquí sólo incompatible/anómalo/discordante.

    Reglas, por año y H (``min_partes`` = 2, constante ANUAL_MIN_PARTES de §4.0):
    - incompatible si lo es en alguna fila agregada (REGIMEN; en E6, ANIO) o en ≥ min_partes unidades
      parciales distintas (PARTE; en E6, MES);
    - anómalo (señal del año, igual en cada H) si alguna fila agregada lo es o si lo son ≥ min_partes
      unidades parciales;
    - una unidad parcial es discordante para H si es incompatible con H y las incompatibles con H son
      menos de min_partes, o si es anómala y las anómalas son menos de min_partes. Se leen por separado
      (lectura propuesta): una parte incompatible y otra anómala dejan las dos discordantes. Las filas
      agregadas quedan con ``discordante`` falso.
    - Si no es incompatible, la fila anual queda «sin_informacion» con motivo <NA>, y la línea aplica
      su regla de compatibilidad. Excepción, E6: si la entrada trae la evaluación del año (nivel ANIO),
      la fila anual conserva su estado y su motivo, y esa fila de entrada no se repite en la salida
      (la fila anual la reemplaza).
    Orden: las filas anuales (por año; las H en el orden en que aparecen) y después las de entrada,
    en su orden. Una entrada vacía da una tabla vacía.
    """
    linea, regla = Linea(linea), Regla(regla)
    if isinstance(min_partes, bool) or int(min_partes) != min_partes or min_partes < 1:
        raise ValueError(f"min_partes debe ser un entero ≥ 1: {min_partes!r}")
    e = _validar_entrada(estados, linea, regla)
    if e.empty:
        return _vacia()

    parcial = e["nivel"].isin([str(n) for n in NIVELES_PARCIALES]).to_numpy()
    incompatible = (e["estado"] == str(Estado.INCOMPATIBLE)).to_numpy()
    anomala = e["reloj_anomalo"].to_numpy(dtype=bool)
    discordante = [False] * len(e)
    anuales: list[dict] = []
    codigo = e["codigo"].iloc[0]

    for anio, idx in e.groupby("anio", sort=True).groups.items():
        idx = list(idx)
        filas_p = [i for i in idx if parcial[i]]
        filas_a = [i for i in idx if not parcial[i]]
        nombre_parcial = "meses" if any(e.at[i, "nivel"] == str(Nivel.MES) for i in filas_p) else "partes"

        anomalas = {e.at[i, "unidad"] for i in filas_p if anomala[i]}
        anomalo_agregado = sorted({e.at[i, "unidad"] for i in filas_a if anomala[i]})
        anomalo_anual = bool(anomalo_agregado) or len(anomalas) >= min_partes

        hs = list(dict.fromkeys(e.loc[idx, "H"]))
        for h in hs:
            p_incomp = {e.at[i, "unidad"] for i in filas_p if e.at[i, "H"] == h and incompatible[i]}
            a_incomp = sorted({e.at[i, "unidad"] for i in filas_a if e.at[i, "H"] == h and incompatible[i]})
            for i in filas_p:
                if e.at[i, "H"] != h:
                    continue
                por_incomp = incompatible[i] and len(p_incomp) < min_partes
                por_anomalia = anomala[i] and len(anomalas) < min_partes
                discordante[i] = bool(por_incomp or por_anomalia)

            motivos = []
            if a_incomp:
                motivos.append("incompatible en " + ",".join(a_incomp))
            if len(p_incomp) >= min_partes:
                motivos.append(f"incompatible en {len(p_incomp)} {nombre_parcial}")
            if motivos:
                estado_anual, motivo = Estado.INCOMPATIBLE, "; ".join(motivos)
            else:
                evaluacion_anio = [i for i in filas_a if e.at[i, "H"] == h and e.at[i, "nivel"] == str(Nivel.ANIO)]
                if evaluacion_anio:
                    i = evaluacion_anio[0]
                    estado_anual = _estado(e.at[i, "estado"])
                    motivo = None if pd.isna(e.at[i, "motivo"]) else e.at[i, "motivo"]
                else:
                    estado_anual, motivo = Estado.SIN_INFORMACION, None
            anuales.append({
                "codigo": codigo, "anio": int(anio), "linea": str(linea), "regla": str(regla),
                "nivel": str(Nivel.ANIO), "unidad": f"{int(anio):04d}", "H": h, "estado": str(estado_anual),
                "reloj_anomalo": anomalo_anual, "discordante": False, "motivo": motivo,
            })

    entrada = e.copy()
    entrada["discordante"] = pd.array(discordante, dtype="bool")
    entrada = entrada[entrada["nivel"] != str(Nivel.ANIO)]
    salida = pd.concat([_marco(anuales), entrada], ignore_index=True)
    return salida.astype(ESQUEMA_ESTADOS)


def combinar(estados: Iterable[Estado]) -> Estado:
    """incompatible > compatible > dudosa > sin_informacion; vacío → sin_informacion."""
    resultado = Estado.SIN_INFORMACION
    for valor in estados:
        estado = _estado(valor)
        if _PRIORIDAD[estado] > _PRIORIDAD[resultado]:
            resultado = estado
    return resultado


def estado_de_clase(estados_miembros: Mapping[str, Estado]) -> Estado:
    """Estado de una clase fusionada; ErrorFusion si sus miembros difieren.

    Se exige igualdad exacta (también entre «dudosa» y «sin_informacion»): los miembros dan el mismo u
    en toda etiqueta con datos, así que toda línea debe darles el mismo estado (R-10).
    """
    if not estados_miembros:
        raise ErrorFusion("una clase fusionada sin miembros")
    vistos = {h: _estado(v) for h, v in estados_miembros.items()}
    distintos = set(vistos.values())
    if len(distintos) != 1:
        detalle = ", ".join(f"{h}={v}" for h, v in vistos.items())
        raise ErrorFusion(f"miembros de una clase con estados distintos: {detalle}")
    return distintos.pop()


def es_informativo(estado: Estado) -> bool:
    """compatible o incompatible (dudosa y sin_informacion no apoyan ni excluyen)."""
    return estado in (Estado.COMPATIBLE, Estado.INCOMPATIBLE)
