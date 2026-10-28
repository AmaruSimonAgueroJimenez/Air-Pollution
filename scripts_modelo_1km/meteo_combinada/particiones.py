"""Particiones de la validación (§2.5, §4.9, §5.1, §5.3, §5.4): grupos, P1, P2, pliegues internos y días.

Funciones puras: reciben las estaciones (``InfoEstacion`` o cualquier objeto con ``lat``, ``lon``, ``excluida``,
``grupo`` y ``bloque``), los grupos y los umbrales (un objeto con ``.a(id)``), y devuelven ``tipos.Pliegue`` o
diccionarios. Las distancias son por haversine (``numerico.haversine_km``, R = 6.371 km; MC-60) y los bloques de
75 km en UTM 19S (EPSG:32719) con el origen de §5.1 (``constantes.valor("P2_ORIGEN_M")``, el (0, 0) de
``protocolos.BLQ-75.origen_m`` de ``v2/config_v2.json``; una prueba los compara).
Ninguna tabla lleva banda ni distancia (§0.4.5): la distancia sale de aquí sólo para calcular S.

Dueño: I3 (ola 1).
Lecturas propias (PAR-n), para el addendum de M1:
- PAR-1. Estaciones que entran: las de ``infos`` con ``excluida`` falso (K3 fallida, sin fondo…, §2.5: «la estación
  queda fuera»). Sólo ellas forman grupos, bloques y pliegues: una estación excluida no puede unir dos grupos, y
  ``grupos_mismo_sitio`` devuelve sólo las que entran (si M2a necesita un grupo para una excluida en
  ``InfoEstacion.grupo``, es el suyo propio, ``tipos.id_grupo([código])``). Una estación que entra sin coordenadas
  finitas es un error (ValueError): debió quedar excluida antes.
- PAR-2. «A ≤ 2 km» y «a ≤ 25 km» son inclusivos (distancia ≤ umbral, en km por haversine).
- PAR-3. Bloque de un punto: ie = ⌊(E − E0)/L⌋ e in = ⌊(N − N0)/L⌋ con L = P2_BLOQUE_KM·1.000 m y (E0, N0) = (0, 0):
  un punto sobre un borde va al bloque del este o del norte (bordes oeste y sur cerrados, como las celdas de §3).
- PAR-4. Un grupo va entero al bloque de su miembro de menor código (MC-46), también en los pliegues internos y en el
  remuestreo. El miembro de menor código es el del id del grupo («G» + el menor código; PAR-13 exige que lo sea).
- PAR-5. P1 (MC-46): los ids de grupo, ordenados, se permutan con ``numerico.generador(SEMILLA, "P1")`` y se reparten
  en rueda en P1_PLIEGUES pliegues (``P1-0`` … ``P1-9``); tamaños que difieren a lo más en 1. P1 no tiene
  amortiguador: «su amortiguador» de §4.9 es el de P2 (S5: «su amortiguador de P2»).
- PAR-6. P2: un pliegue por bloque con estaciones, en orden numérico de (ie, in). Quedan fuera de todo (``excluidas``)
  las estaciones a ≤ P2_AMORT_KM de alguna de prueba, **una por una**: el texto dice «las estaciones a ≤ 25 km de
  cualquier estación de prueba» (§5.1), así que el compañero de grupo de una estación del amortiguador que está más
  lejos sigue en el entrenamiento (en el núcleo sólo cuenta como disponible; §2.5).
- PAR-7. Pliegues internos (§4.9, MC-46): sólo las estaciones de entrenamiento del externo; sus bloques de
  SEL_BLOQUE_KM (por PAR-4), ordenados, se permutan con ``numerico.generador(SEMILLA, "internos", <id del externo>)``
  (la etiqueta «internos/<pliegue>» de MC-44) y se reparten en rueda en SEL_PLIEGUES. En un externo de P2 se sacan
  del entrenamiento interno las estaciones a ≤ SEL_AMORT_KM de las de prueba interna (``excluidas`` del interno); en uno
  de P1, no. Un pliegue interno sin estaciones de prueba no se devuelve.
- PAR-8. Un pliegue externo de P1 sin grupos (menos grupos que pliegues) no se devuelve.
- PAR-9. Días de selección (MC-44): el día es la fecha UTC de la hora, d2000 = ⌊h/24⌋; se eligen los días con
  d2000 mód SEL_MOD = SEL_RESTO, o mód SEL_MOD_RECORTE = SEL_RESTO con el recorte.
- PAR-10. ``distancia_entrenamiento_km``: para cada estación de prueba, la distancia a la de entrenamiento más cercana
  con ≥ MIN_HORAS horas válidas de la variable (``horas_validas``: código → horas; las que faltan valen 0); infinito
  si no hay ninguna.
- PAR-11. ``bloques_remuestreo`` (MC-34) da, para cada estación que entra, el bloque de P2 de su grupo (PAR-4) desde
  ``InfoEstacion.grupo`` y ``InfoEstacion.bloque``: sus valores son los bloques de P2 con estaciones, que es lo que se
  sortea. Su firma (§3) no trae ``grupos`` ni umbrales, así que la fuente es ``InfoEstacion``.
- PAR-12. Una sola geometría para los pliegues y el remuestreo (H20 de la revisión de la ola 1): ``pliegues_p2`` y
  ``pliegues_internos`` exigen que ``InfoEstacion.grupo`` de cada estación que entra sea el de ``grupos``, y
  ``pliegues_p2`` además que ``InfoEstacion.bloque`` sea el que da ``bloque``. Si difieren, ValueError: P2 (que usa
  ``grupos``) y el remuestreo (que usa ``InfoEstacion``) no pueden separarse.
- PAR-13. ``grupos`` es el de ``grupos_mismo_sitio``: en ``pliegues_p2`` y ``pliegues_internos`` debe cubrir
  exactamente las estaciones que entran (ni una de menos, que quedaría sin validar en P2, ni una excluida), y en las
  cuatro funciones de pliegues y en el remuestreo cada id de grupo debe ser «G» + el menor código de sus miembros. Si
  no, ValueError.
Depende de: tipos, constantes, umbrales, numerico.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

import numpy as np

from meteo_combinada import constantes, numerico, tipos
from meteo_combinada.tipos import Particion, Pliegue

# §5.1: origen (este, norte) de la rejilla de 75 km, «con el origen (0, 0) de protocolos.BLQ-75.origen_m de
# config_v2.json» (constante del texto, anexo A2). test_particiones lo compara con ese archivo.
ORIGEN_M = tuple(float(x) for x in constantes.valor("P2_ORIGEN_M"))
M_POR_KM = 1000
HORAS_POR_DIA = 24
ETIQUETA_P1 = "P1"
ETIQUETA_INTERNOS = "internos"


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def _elegibles(infos: Mapping[str, Any]) -> list[str]:
    """Códigos que entran (PAR-1), ordenados; ValueError si alguno no tiene coordenadas finitas."""
    salida = []
    for codigo in sorted(infos):
        info = infos[codigo]
        if getattr(info, "excluida", False):
            continue
        if not (math.isfinite(float(info.lat)) and math.isfinite(float(info.lon))):
            raise ValueError(f"la estación {codigo} entra a la validación sin coordenadas finitas")
        salida.append(codigo)
    return salida


def _coordenadas(infos, codigos) -> tuple[np.ndarray, np.ndarray]:
    return (np.array([float(infos[c].lat) for c in codigos], dtype=np.float64),
            np.array([float(infos[c].lon) for c in codigos], dtype=np.float64))


def _distancias(infos, filas, columnas) -> np.ndarray:
    lat_f, lon_f = _coordenadas(infos, filas)
    lat_c, lon_c = _coordenadas(infos, columnas)
    return numerico.haversine_km(lat_f[:, None], lon_f[:, None], lat_c[None, :], lon_c[None, :])


def _a_menos_de(infos, codigos, desde, radio_km: float) -> list[str]:
    """Los ``codigos`` a ≤ radio_km de alguno de ``desde`` (PAR-2)."""
    if not codigos or not desde:
        return []
    d = _distancias(infos, list(codigos), list(desde))
    return [c for c, cerca in zip(codigos, (d <= radio_km).any(axis=1)) if cerca]


def _bloques_lado(lat, lon, lado_km: float) -> np.ndarray:
    lat = np.asarray(lat, dtype=np.float64)
    lon = np.asarray(lon, dtype=np.float64)
    if not (np.isfinite(lat).all() and np.isfinite(lon).all()):
        raise ValueError("bloque: coordenadas no finitas")
    e, n = numerico.utm19s(lat, lon)
    lado = float(lado_km) * M_POR_KM
    ie = np.floor((e - ORIGEN_M[0]) / lado).astype(np.int64)
    i_n = np.floor((n - ORIGEN_M[1]) / lado).astype(np.int64)
    salida = np.empty(ie.shape, dtype=object)
    for idx in np.ndindex(ie.shape):
        salida[idx] = tipos.id_bloque(int(ie[idx]), int(i_n[idx]))
    return salida


def _orden_bloque(b: str) -> tuple[int, int]:
    m = tipos.PATRON_BLOQUE.fullmatch(b)
    if m is None:
        raise ValueError(f"bloque inválido: {b!r}")
    return int(m.group("ie")), int(m.group("in"))


def _comprobar_ids_de_grupo(grupos: Mapping[str, str]) -> None:
    """PAR-13: cada id de grupo es «G» + el menor código de sus miembros."""
    miembros: dict[str, list[str]] = {}
    for c, g in grupos.items():
        miembros.setdefault(g, []).append(c)
    for g, codigos in miembros.items():
        if tipos.id_grupo(codigos) != g:
            raise ValueError(f"el grupo {g!r} no es «G» + el menor código de sus miembros {sorted(codigos)}")


def _comprobar_grupos(infos, grupos, elegibles: list[str]) -> None:
    """PAR-12 y PAR-13: ``grupos`` cubre exactamente las que entran, con ids coherentes, y coincide con
    ``InfoEstacion.grupo``."""
    if set(grupos) != set(elegibles):
        faltan, sobran = sorted(set(elegibles) - set(grupos)), sorted(set(grupos) - set(elegibles))
        raise ValueError(f"grupos no cubre exactamente las estaciones que entran (faltan {faltan}, sobran {sobran})")
    _comprobar_ids_de_grupo(grupos)
    distintos = [c for c in elegibles if getattr(infos[c], "grupo", None) != grupos[c]]
    if distintos:
        raise ValueError(f"InfoEstacion.grupo distinto del de grupos en {distintos} (PAR-12)")


def _bloque_de_grupo(infos, grupos, codigos, lado_km: float) -> dict[str, str]:
    """Código → bloque de su grupo (el de su miembro de menor código, el del id; PAR-4), para los ``codigos``."""
    representantes = sorted({grupos[c][1:] for c in codigos})
    lat, lon = _coordenadas(infos, representantes)
    por_representante = dict(zip(representantes, _bloques_lado(lat, lon, lado_km))) if representantes else {}
    return {c: por_representante[grupos[c][1:]] for c in codigos}


def _reparto_en_rueda(ids: list[str], n_pliegues: int, rng) -> list[list[str]]:
    """Ids ordenados, permutados con ``rng`` y repartidos en rueda (MC-46)."""
    ordenados = sorted(ids)
    permutados = [ordenados[i] for i in rng.permutation(len(ordenados))]
    return [permutados[j::n_pliegues] for j in range(n_pliegues)]


def _entero(U, ident: str) -> int:
    v = U.a(ident)
    if isinstance(v, bool) or not isinstance(v, (int, np.integer)):
        raise ValueError(f"{ident} debe ser entero: {v!r}")
    return int(v)


# ---------------------------------------------------------------------------
# Funciones públicas (§3 del diseño)
# ---------------------------------------------------------------------------
def grupos_mismo_sitio(infos, umbrales) -> dict[str, str]:
    """Código → grupo a ≤ GRUPO_KM de las estaciones que entran (componentes conexas; §2.5, PAR-1, PAR-2)."""
    elegibles = _elegibles(infos)
    salida: dict[str, str] = {}
    if elegibles:
        d = _distancias(infos, elegibles, elegibles)
        vecinos = d <= float(umbrales.a("GRUPO_KM"))
        visto = np.zeros(len(elegibles), dtype=bool)
        for i in range(len(elegibles)):
            if visto[i]:
                continue
            componente, pendientes = [], [i]
            visto[i] = True
            while pendientes:
                j = pendientes.pop()
                componente.append(j)
                for k in np.flatnonzero(vecinos[j] & ~visto):
                    visto[k] = True
                    pendientes.append(int(k))
            codigos = [elegibles[j] for j in componente]
            gid = tipos.id_grupo(codigos)
            salida.update({c: gid for c in codigos})
    return dict(sorted(salida.items()))


def bloque(lat, lon, umbrales):
    """Bloque «<ie>_<in>» de P2_BLOQUE_KM en EPSG:32719 con origen (0, 0) de cada punto (§5.1, PAR-3)."""
    return _bloques_lado(lat, lon, umbrales.a("P2_BLOQUE_KM"))


def pliegues_p1(grupos, umbrales) -> list:
    """P1: los grupos en P1_PLIEGUES pliegues al azar, de igual número de grupos (§5.1, MC-46, PAR-5, PAR-8)."""
    _comprobar_ids_de_grupo(grupos)
    n = _entero(umbrales, "P1_PLIEGUES")
    rng = numerico.generador(_entero(umbrales, "SEMILLA"), ETIQUETA_P1)
    todos = sorted(grupos)
    salida = []
    for j, ids in enumerate(_reparto_en_rueda(sorted(set(grupos.values())), n, rng)):
        en = set(ids)
        prueba = tuple(c for c in todos if grupos[c] in en)
        if prueba:
            entrenamiento = tuple(c for c in todos if grupos[c] not in en)
            salida.append(Pliegue(tipos.id_pliegue_p1(j), Particion.P1, prueba, entrenamiento))
    return salida


def pliegues_p2(infos, grupos, umbrales) -> list:
    """P2: un pliegue por bloque con estaciones; amortiguador de P2_AMORT_KM fuera de todo (§5.1, PAR-4, PAR-6,
    PAR-12, PAR-13)."""
    elegibles = _elegibles(infos)
    _comprobar_grupos(infos, grupos, elegibles)
    if not elegibles:
        return []
    lado = umbrales.a("P2_BLOQUE_KM")
    propios = _bloques_lado(*_coordenadas(infos, elegibles), lado)
    for c, b in zip(elegibles, propios):
        declarado = getattr(infos[c], "bloque", None)
        if declarado != b:
            raise ValueError(f"{c}: InfoEstacion.bloque {declarado!r} ≠ {b!r} de particiones.bloque (PAR-12)")
    de_grupo = _bloque_de_grupo(infos, grupos, elegibles, lado)
    radio = float(umbrales.a("P2_AMORT_KM"))
    salida = []
    for b in sorted(set(de_grupo.values()), key=_orden_bloque):
        prueba = [c for c in elegibles if de_grupo[c] == b]
        resto = [c for c in elegibles if de_grupo[c] != b]
        excluidas = _a_menos_de(infos, resto, prueba, radio)
        fuera = set(excluidas)
        salida.append(Pliegue(tipos.id_pliegue_p2(b), Particion.P2, tuple(prueba),
                              tuple(c for c in resto if c not in fuera), tuple(excluidas)))
    return salida


def pliegues_internos(externo, infos, grupos, umbrales) -> list:
    """SEL_PLIEGUES pliegues internos de bloques de SEL_BLOQUE_KM, sólo con el entrenamiento del externo; en P2, con
    el amortiguador de SEL_AMORT_KM (§4.9, PAR-7)."""
    _comprobar_grupos(infos, grupos, _elegibles(infos))
    entrenamiento = list(externo.entrenamiento)
    if not set(entrenamiento) <= set(grupos):
        raise ValueError(f"{externo.id}: el entrenamiento trae estaciones que no entran")
    if not entrenamiento:
        return []
    de_grupo = _bloque_de_grupo(infos, grupos, entrenamiento, umbrales.a("SEL_BLOQUE_KM"))
    rng = numerico.generador(_entero(umbrales, "SEMILLA"), ETIQUETA_INTERNOS, externo.id)
    repartos = _reparto_en_rueda(sorted(set(de_grupo.values())), _entero(umbrales, "SEL_PLIEGUES"), rng)
    radio = float(umbrales.a("SEL_AMORT_KM"))
    salida = []
    for j, bloques in enumerate(repartos):
        en = set(bloques)
        prueba = [c for c in entrenamiento if de_grupo[c] in en]
        if not prueba:
            continue
        resto = [c for c in entrenamiento if de_grupo[c] not in en]
        excluidas = _a_menos_de(infos, resto, prueba, radio) if externo.particion is Particion.P2 else []
        fuera = set(excluidas)
        salida.append(Pliegue(tipos.id_interno(externo.id, j), externo.particion, tuple(prueba),
                              tuple(c for c in resto if c not in fuera), tuple(excluidas), externo=externo.id))
    return salida


def dias_de_seleccion(h, umbrales, *, recorte: bool):
    """Máscara de las horas cuyo día UTC cumple d2000 mód SEL_MOD (o SEL_MOD_RECORTE) = SEL_RESTO (§4.9, PAR-9)."""
    h = np.asarray(h)
    if not np.issubdtype(h.dtype, np.integer):
        raise ValueError("dias_de_seleccion: h son horas enteras desde 2000-01-01T00:00Z")
    modulo = _entero(umbrales, "SEL_MOD_RECORTE" if recorte else "SEL_MOD")
    return np.mod(np.floor_divide(h.astype(np.int64), HORAS_POR_DIA), modulo) == _entero(umbrales, "SEL_RESTO")


def distancia_entrenamiento_km(prueba, entrenamiento, infos, horas_validas, umbrales) -> dict[str, float]:
    """Distancia de cada estación de prueba a la de entrenamiento más cercana con ≥ MIN_HORAS horas válidas (§5.3,
    PAR-10)."""
    minimo = umbrales.a("MIN_HORAS")
    candidatas = [c for c in entrenamiento if horas_validas.get(c, 0) >= minimo]
    prueba = list(prueba)
    if not prueba:
        return {}
    if not candidatas:
        return {p: math.inf for p in prueba}
    d = _distancias(infos, prueba, candidatas).min(axis=1)
    return {p: float(x) for p, x in zip(prueba, d)}


def bloques_remuestreo(infos) -> dict[str, str]:
    """Código → bloque de P2 de su grupo (``InfoEstacion.grupo`` y ``.bloque``), para las estaciones que entran
    (MC-34, PAR-4, PAR-11)."""
    elegibles = _elegibles(infos)
    _comprobar_ids_de_grupo({c: infos[c].grupo for c in elegibles})
    salida = {}
    for c in elegibles:
        representante = infos[c].grupo[1:]
        b = infos[representante].bloque
        if not isinstance(b, str) or tipos.PATRON_BLOQUE.fullmatch(b) is None:
            raise ValueError(f"{representante}: InfoEstacion.bloque inválido {b!r}")
        salida[c] = b
    return salida
