"""Líneas físicas: E3 (E3t y E3p, regla gruesa), regla fina de E3p, E4 (E4p) y E6 (§4.3, §4.4, §4.6).

Entradas: extracto ANOTADO (ESQUEMA_EXTRACTO_HORA + ESQUEMA_ANOTACION), serie ERA5-Land del píxel
enlazado (tipos.SerieEra5) y ContextoEstacion. Salidas: tipos.ResultadoLinea con estados
(ESQUEMA_ESTADOS; regla «gruesa»/«fina» en E3p y «gruesa» en E3t) y métricas (ESQUEMA_METRICAS_E3,
ESQUEMA_METRICAS_E4). Los estados por año-régimen y por parte salen aquí; la combinación anual de E3p
(gruesa + fina) y las consecuencias de A3 las aplica decision.py con ``e3p_anual``, porque A3 se
calcula después (§5.2, fases 4 y 5).

Reglas que fija este módulo (lecturas del diseño, §7):
- Pares: Δy(L) = y(L) − y(L − p) dentro de la misma parte; M exige Δx(L − c) finito para TODO c de la
  ventana ±E3_VENTANA; sin etiquetas especiales ni astillas (R-08, R-24); p = paso nativo del mes
  (meses con p ∉ {1, 2, 3, 6} no entran; R-51).
- Remuestreo: E3_REPLICAS réplicas por bloques de E3_DIAS_BLOQUE días contados desde el primer día
  calendario de la unidad (R-42); semilla de numerico.semilla con variable «QFE» (R-13); la serie
  filtrada usa las mismas réplicas (R-33).
- E3p: cada desigualdad de la regla gruesa, y la identidad de ĉ en el reloj anómalo, debe cumplirse en
  ≥ E3P_CONF de las réplicas, por separado y con la H′ fijada en la muestra completa (R-12).
- E3t: sin remuestreo; nunca excluye ni señala anomalía para la decisión; su incompatibilidad se
  calcula para T-P, para el informe y para el apoyo en modo completo (R-02; así lo dice el v1.0.1 desde la
  Enmienda 1, punto E1-2, adoptada y anclada en APH 81bb100).
- Alias de 12 h: ĉ ≡ c_H (mód 12), ĉ ≠ c_H (§4.3.1). Con F(−4) en P el alias es +8, no −8 (R-01; la
  prueba 11 de §8 lo dice así desde la Enmienda 1, punto E1-1). La glosa del v1 «incluye ĉ ≥ +1» quedó en
  el v1.0.1 como «todo ĉ positivo que no sea alias de 12 h de una H de P», que es la regla formal (R-03;
  punto E1-3).
- E3_RMAX vale para E3t, E3p y E3p filtrada (R-41). Un año-régimen es informativo en «E3p anual» si la
  gruesa le da compatible o incompatible a alguna H de P, o si es fino: por año-régimen y no por H (Enmienda 3,
  opción R de E3-2, que enmienda §4.3.4 y §8.21; R-52 deja de ser una lectura [D]; ver LF-17).
- E6 sólo con FM-15 vuelve incompatibles a las H a ≥ 2 h (R-28).
- Coordenadas no interpretables o inconsistentes: E3 y E4 sin información (§3.1, §3.3).

Lecturas propias de este módulo (van al addendum de C1):
- LF-1. El paso nativo (§3.2) se calcula aquí, por mes y variable, sobre todas las etiquetas del mes con
  valor (también las especiales), con la regla única ``numerico.paso_nativo`` (la misma de extraccion).
- LF-2. [Enmienda 3, E3-1, §4.3.1; implementación para el addendum] El armónico de QFE se ajusta sobre las
  etiquetas de la unidad con valor, en hora de etiqueta. El de sp, uno por cada c de la ventana, en hora UTC,
  sobre los instantes únicos que ese c empareja con la unidad, {L − c, L − c − p : L ∈ M} (antes, R-23: uno
  solo sobre la unión de esos instantes para todos los c). La serie filtrada se calcula una vez por unidad y
  sirve a la muestra completa y a las réplicas (R-33). Con c = c_H los dos ajustes usan casi los mismos
  instantes, no exactamente: QFE se ajusta sobre las etiquetas de la unidad y sp sobre los instantes de los
  pares, que difieren en los bordes y en los huecos (por eso la enmienda no dice «los mismos»).
- LF-3. r(c) de cada réplica se calcula con sumas por bloque de las series centradas en la muestra
  completa: es la correlación de Pearson de las filas de la réplica (difiere de numerico.pearson en
  ~1e-15 relativo, por el orden de las sumas). Las réplicas las sortea siempre numerico.replicas_por_bloques.
- LF-4. R-12, completada: en la segunda condición de incompatible, ĉ se fija con la muestra completa
  (como H′) y se exige r(ĉ) − r(H) ≥ μ en las réplicas; la condición |ĉ_cont − c_H| ≤ τ usa, en cada
  réplica, el ĉ_cont de la misma serie (filtrada si en la muestra completa ĉ^f_cont está definido);
  si en una réplica no está definido, la desigualdad no se cumple en ella.
- LF-5. «r(H) es el máximo en P»: estrictamente mayor que el de toda H′ de desfase distinto (un empate
  exacto no da máximo); las H con el mismo desfase comparten r.
- LF-6. «Si el máximo de r es alias de 12 h de alguna H, sin información (alias)» se aplica a la unidad
  entera (todas las H y sin reloj anómalo), antes de las reglas de compatible e incompatible.
- LF-7. El texto no fija el estado anual de E3t: incompatible si lo es en algún año-régimen; compatible
  si no lo es y es compatible en todos sus años-régimen informativos (≥ 1), como la gruesa de E3p.
- LF-8. Un año-régimen fino exige además ĉ^f definido y máx r^f ≥ E3_RMAX (R-41).
- LF-9. Con la regla fina apagada (mediana de ĉ^f_cont − ĉ^f > E3P_FINA_APAGADO), sus estados quedan
  «sin información» (motivo «apagada») y se agregan filas de nivel estación (unidad «*»).
- LF-10. E4: la media del día de etiqueta usa las etiquetas del día dentro de la unidad; horas cubiertas
  = horas enteras de etiqueta con el mínimo de valores, y sólo sus valores entran al ajuste; el hueco es
  la mayor distancia circular entre horas cubiertas consecutivas (con paso 3 h, 3 h).
- LF-11. E4p con E4P_COMPAT < δ < E4P_INCOMPAT queda «dudosa»; el anual es dudosa si hay años-régimen
  evaluables pero no todos compatibles y ninguno incompatible.
- LF-12. Filtro de E3t: A1 con el ajuste de §4.4 (anomalía del día y K de n_h con el mínimo del
  año-régimen), en hora de etiqueta para Ts y en hora UTC para t2m, sobre los días de etiqueta válidos
  de Ts que tienen el día UTC completo de t2m.
- LF-13. E6: «H′ con desfase distinto» = no fusionada con H en la unidad (algún desfase difiere);
  «|c_H′ − c_H| ≥ 2» = en todas las etiquetas de la unidad. Se excluyen las etiquetas especiales
  (como R-24). round(Ts) es el redondeo de numpy (empates al par). Un c fuera de P es anómalo con
  cualquiera de las dos condiciones de compatible.
- LF-14. Nombres ISD: la puntuación se reemplaza por un espacio antes de colapsar espacios.
- LF-15. Por qué E3-1 (Enmienda 3): con un solo armónico de sp sobre la unión de los instantes (R-23, el texto
  v1.0.2), en una estación con ventana diurna (aeródromos) los dos ajustes no quitaban lo mismo de la marea S2:
  el de QFE usa sus 13 h por día y el de sp, las 24. ĉ^f se corría hasta ±1,7 h en el generador de la batería, y
  la regla fina quedaba fina y errada en 1 h. Con LF-2 la regla fina queda exacta en la misma atmósfera
  (test_lineas_fisicas.PruebasVentanaParcial.test_regla_fina_exacta_en_ventana_parcial_con_e3_1) y el aeródromo
  tipo d hace ida y vuelta (test_orquestacion.test_ida_y_vuelta_aerodromo_tipo_d). Costo medido: ≤ +9 % en la red.
- LF-16. El filtro de E3t (§4.3.3), con días de etiqueta de ≥ 20 valores, se aplica tal cual a los aeródromos: con
  13 valores por día no pasa nunca, y E3t y T-P quedan sin información (ORQ-10; E3-4 de la misma propuesta).
- LF-17. «Informativo» en E3p anual, por año-régimen [Enmienda 3, opción R de E3-2, adoptada; R-52 sale de las
  lecturas [D]]: un año-régimen es informativo si la gruesa le da compatible o incompatible a alguna H de P en
  él, o si es fino con la fina activa, y cuenta igual para todas las H del año. Así, un R0 no fino en que la
  gruesa deja a H residual y da compatible o incompatible a otras H cuenta para H, y E3p no es compatible con
  H aunque el otro año-régimen lo sea. Consecuencias: en la celda «Cv × tipo a» de D1 (E3-2), R0 mezcla −3 y
  −4, la gruesa da F(0) incompatible y residual a las demás, y E3p ya no apoya F(−4); en C.21 (un año UTC con
  una parte en −4), R0 queda residual para F(0) e incompatible para las rivales y E3p ya no apoya F(0): sin E6
  el año queda insuficiente y ningún mes tiene regla, con E6 se confirma F(0) con ese mes sin regla, y con dos
  partes queda discrepante (§8.21 enmendado). Con la lectura anterior (por H), ese R0 no contaba para H. Un
  año-régimen sin ninguna H compatible ni incompatible y no fino sigue sin contar. Lo fijan
  test_lineas_fisicas.PruebasReglaFina.test_e3p_anual_r52_informativo_por_h (el nombre se conserva para la
  traza), test_decision.PruebasP21.test_p21_parte_menos4_en_anio_utc (con esta función, sin la simulación de
  test_decision, y con la premisa de §8.21: R0 residual para F(0)) y
  test_orquestacion.test_p21_parte_menos4_en_anio_utc; las dos de §8.21 fallan con la lectura por H.
- LF-18. Diagnóstico subhorario [Enmienda 3, E3-5 del texto (B6 en la medición), §4.3.5; implementación para el
  addendum]: ρ es la media
  circular de período 1 h de ĉ^f_cont (el mismo estadístico que m de A5: numerico.media_circular_en con el
  intervalo A5_ENVOLVER, [−0,5; 0,5)) sobre todos los años-régimen de QFE de la estación con ĉ^f_cont definido,
  si |lat| ≤ 50° (SUBH_LAT_MAX); ya no depende de los años confirmados ni de c_H(R). Mismos SUBH_RHO_H (0,35 h)
  y SUBH_MIN_REGIMENES (6). Sin años-régimen, ρ es NaN y no hay marca; con resultante nula, también. La marca
  sigue siendo de la estación y orquestacion la calcula sólo si tiene algún año confirmado: son las únicas
  cuya entrada de §7.2 lleva «marcas» (ORQ-6), así que no cambia ningún veredicto ni ninguna salida.
Depende de: tipos, estados, numerico, umbrales (vía ctx), constantes, tablas.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Callable, Literal, Mapping, Sequence

import numpy as np
import pandas as pd

from reloj_dmc import constantes, estados, numerico, tablas
from reloj_dmc.tipos import (ESQUEMA_ESTADOS, ESQUEMA_METRICAS_E3, ESQUEMA_METRICAS_E4, ContextoEstacion, Estado,
                             Hipotesis, Linea, MotivoSinInfo, Nivel, Regimen, Regla, ResultadoLinea, SerieEra5,
                             tabla_vacia, validar_esquema)

Variable = Literal["Ts", "QFE"]
VariableE4 = Literal["Ts", "QFE", "HR"]      # HR sólo para G-HR (guardas)

_c = constantes.valor

COLUMNA = {"Ts": "ts", "QFE": "qfe", "HR": "hr"}       # columna del extracto (ESQUEMA_EXTRACTO_HORA)
VARIABLE_ERA5 = {"Ts": "t2m", "QFE": "sp"}               # variable de la serie (§3.4)
LINEA_E3 = {"Ts": Linea.E3T, "QFE": Linea.E3P}

UNA_HORA = np.timedelta64(1, "h")
_EPOCA = np.datetime64("1970-01-01T00:00", "ns")   # medianoche: (t − época) mód 24 h es la hora del día
_HORAS_DIA = 24
_PERIODO_S2_H = 12                                 # §4.4: «distancia circular, de período 12 h»
_MESES_ANIO = 12

# Motivos de la regla fina (texto corto en la columna «motivo»).
_NO_FINO = "no_fino"
_ANOMALO_INFORME = "anomalo_informativo"            # E3t: anomalía que sólo va al informe
_E6_NO_CONCLUYENTE = "no_concluyente"
_PARTES_E6 = ("FM-12", "FM-15")                     # §4.6: SYNOP y METAR

COLUMNAS_PARES_BASE = ("anio", "nivel", "unidad", "regimen", "L", "paso_h", "bloque", "dy")
COLUMNAS_FILTRO = ("anio", "regimen", "pasa", "cociente_a1", "r_diaria")
COLUMNAS_CRUCE = ("codigo", "id_isd", "criterio", "distancia_km")


def ventana(umbrales) -> tuple[int, ...]:
    """c = −E3_VENTANA … +E3_VENTANA (Anexo B, «ventana ±9»). Se pasa explícita a numerico."""
    return numerico.desfases_ventana(umbrales)


def columnas_dx(umbrales) -> tuple[str, ...]:
    """Nombres de las columnas Δx(L − c) de ``pares_e3``: «dx_-9» … «dx_+0» … «dx_+9»."""
    return tuple(f"dx_{c:+d}" for c in ventana(umbrales))


def _horas(t: np.ndarray) -> np.ndarray:
    """Horas (float) desde la época; mód 24 da la hora del día (de etiqueta o UTC, según t)."""
    return (np.asarray(t, dtype="datetime64[ns]") - _EPOCA) / UNA_HORA


def _horas_td(n: np.ndarray | int) -> np.ndarray:
    return np.asarray(n, dtype=np.int64).astype("timedelta64[h]")


# ---------------------------------------------------------------------------------------------
# Paso nativo y base por año (§3.2, §3.5)
# ---------------------------------------------------------------------------------------------
def pasos_por_mes(extracto: pd.DataFrame, variable: str) -> dict[tuple[int, int], int | None]:
    """§3.2 (LF-1): por (año, mes), la diferencia más frecuente entre etiquetas consecutivas con valor;
    en un empate, la menor (``numerico.paso_nativo``). None si no queda en PASOS_NATIVOS (o si el mes tiene
    menos de dos valores)."""
    L = extracto["L"].to_numpy(dtype="datetime64[ns]")
    y = extracto[COLUMNA[variable]].to_numpy(dtype=np.float64, na_value=np.nan)
    Lv = np.sort(L[np.isfinite(y)])
    salida: dict[tuple[int, int], int | None] = {}
    if Lv.size == 0:
        return salida
    idx = pd.DatetimeIndex(Lv)
    clave = idx.year.to_numpy() * _MESES_ANIO + idx.month.to_numpy()
    validos = set(_c("PASOS_NATIVOS"))
    for k in np.unique(clave):
        anio, mes = int((k - 1) // _MESES_ANIO), int((k - 1) % _MESES_ANIO + 1)
        p = numerico.paso_nativo(Lv[clave == k])
        salida[(anio, mes)] = p if p in validos else None
    return salida


@dataclass
class _BaseAnio:
    """Etiquetas de un año con valor de la variable, fuera de especiales y astillas, ordenadas por L."""
    anio: int
    L: np.ndarray            # datetime64[ns]
    y: np.ndarray            # float64
    parte: np.ndarray        # object (str)
    regimen: np.ndarray      # object (str)
    mes: np.ndarray          # int
    p: np.ndarray            # int64; 0 = el paso del mes no es válido


def _base_por_anio(extracto: pd.DataFrame, variable: str, anios: Sequence[int]) -> dict[int, _BaseAnio]:
    col = COLUMNA[variable]
    faltan = [c for c in ("L", "parte", "regimen", "especial", col) if c not in extracto.columns]
    if faltan:
        raise ValueError(f"el extracto anotado no trae {faltan}")
    L = extracto["L"].to_numpy(dtype="datetime64[ns]")
    if np.isnat(L).any():
        raise ValueError("L con valores nulos")
    y = extracto[col].to_numpy(dtype=np.float64, na_value=np.nan)
    parte = extracto["parte"].to_numpy(dtype=object, na_value=None)
    regimen = extracto["regimen"].to_numpy(dtype=object, na_value=None)
    especial = extracto["especial"].to_numpy(dtype=bool)
    idx = pd.DatetimeIndex(L)
    anio, mes = idx.year.to_numpy(), idx.month.to_numpy()
    pasos = pasos_por_mes(extracto, variable)
    clave = anio * _MESES_ANIO + mes
    p = np.zeros(len(L), dtype=np.int64)
    for k in np.unique(clave):
        v = pasos.get((int((k - 1) // _MESES_ANIO), int((k - 1) % _MESES_ANIO + 1)))
        p[clave == k] = v or 0
    ok = np.isfinite(y) & ~especial & (parte != None) & (regimen != None)   # noqa: E711 (arreglo de objetos)
    salida = {}
    for a in anios:
        filas = np.flatnonzero(ok & (anio == a))
        orden = filas[np.argsort(L[filas], kind="stable")]
        if np.unique(L[orden]).size != orden.size:
            raise ValueError(f"etiquetas repetidas en el extracto ({a})")
        salida[int(a)] = _BaseAnio(int(a), L[orden], y[orden], parte[orden], regimen[orden], mes[orden], p[orden])
    return salida


def _paso_comun(p: np.ndarray) -> int | None:
    unicos = np.unique(p[p > 0])
    return int(unicos[0]) if unicos.size == 1 else None


# ---------------------------------------------------------------------------------------------
# Calendario de la estación: partes, primer día de cada unidad y c_H(R)
# ---------------------------------------------------------------------------------------------
class _Calendario:
    """Consultas a tablas con memoria, para una estación (Zs y P de ctx.info)."""

    def __init__(self, ctx: ContextoEstacion):
        self.ctx = ctx
        self.zs = tuple(ctx.info.zs)
        self._partes: dict[tuple[int, int], dict] = {}
        self._regs: dict[int, dict[str, Regimen]] = {}

    def partes(self, anio: int, mes: int) -> dict:
        clave = (anio, mes)
        if clave not in self._partes:
            self._partes[clave] = {p.id: p for p in tablas.partes_del_mes(self.zs, anio, mes, self.ctx.tablas)}
        return self._partes[clave]

    def parte(self, parte_id: str):
        anio, mes, _ = (int(x) for x in parte_id.split("-"))
        return self.partes(anio, mes)[parte_id]

    def regimenes(self, anio: int) -> dict[str, Regimen]:
        if anio not in self._regs:
            regs = (self.ctx.regimenes or {}).get(anio) or tablas.regimenes_del_anio(self.zs, anio, self.ctx.tablas)
            self._regs[anio] = {r.id: r for r in regs}
        return self._regs[anio]

    def primer_dia_regimen(self, anio: int, regimen: str) -> date:
        """Primer día calendario del año-régimen (R-42): el de su primera parte en el año."""
        for mes in range(1, _MESES_ANIO + 1):
            for p in self.partes(anio, mes).values():
                if p.regimen == regimen:
                    return tablas.fecha_de(p.desde)
        raise ValueError(f"{regimen} no tiene partes en {anio}")

    def desfases(self, anio: int, regimen: str) -> dict[str, int]:
        """c_H(R) para cada H de P (orden de P)."""
        r = self.regimenes(anio)[regimen]
        return {h.id: tablas.desfase(h, r, self.zs) for h in self.ctx.info.P}

    def regimenes_con_datos(self, anio: int, extra: Sequence[str] = ()) -> tuple[str, ...]:
        ids = set((self.ctx.regimenes_con_datos or {}).get(anio, ())) | set(extra)
        return tuple(sorted(ids))


def _clave_parte(parte_id: str) -> tuple[int, int, int]:
    return tuple(int(x) for x in parte_id.split("-"))


# ---------------------------------------------------------------------------------------------
# Pares de E3 (§4.3.1)
# ---------------------------------------------------------------------------------------------
@dataclass
class _Pares:
    """Pares M de un año: fila de L y de L − p en la base, Δy, Δx por desfase y los x crudos."""
    i: np.ndarray            # (m,)
    j: np.ndarray            # (m,)
    dy: np.ndarray           # (m,)
    dx: np.ndarray           # (k, m)
    u: np.ndarray            # (m, k) instantes L − c
    up: np.ndarray           # (m, k) instantes L − c − p
    xu: np.ndarray           # (m, k)
    xup: np.ndarray          # (m, k)


def _pares_vacios(k: int) -> _Pares:
    vacio_t = np.empty((0, k), dtype="datetime64[ns]")
    return _Pares(np.empty(0, np.int64), np.empty(0, np.int64), np.empty(0), np.empty((k, 0)), vacio_t, vacio_t,
                  np.empty((0, k)), np.empty((0, k)))


def _pares_anio(b: _BaseAnio, serie: SerieEra5, pixel: int, variable_era5: str, vent: tuple[int, ...]) -> _Pares:
    n, k = len(b.L), len(vent)
    if n == 0:
        return _pares_vacios(k)
    objetivo = b.L - _horas_td(b.p)
    j = np.searchsorted(b.L, objetivo)
    jj = np.minimum(j, n - 1)
    ok = (b.p > 0) & (j < n) & (b.L[jj] == objetivo) & (b.parte[jj] == b.parte)
    i = np.flatnonzero(ok)
    if i.size == 0:
        return _pares_vacios(k)
    j = jj[i]
    c = _horas_td(np.asarray(vent))
    u = b.L[i][:, None] - c[None, :]
    up = u - _horas_td(b.p[i])[:, None]
    xu = np.asarray(serie.valores(pixel, variable_era5, u.ravel()), dtype=np.float64).reshape(u.shape)
    xup = np.asarray(serie.valores(pixel, variable_era5, up.ravel()), dtype=np.float64).reshape(u.shape)
    dx = xu - xup
    dy = b.y[i] - b.y[j]
    m = np.isfinite(dx).all(axis=1) & np.isfinite(dy)
    return _Pares(i[m], j[m], dy[m], np.ascontiguousarray((dx[m]).T), u[m], up[m], xu[m], xup[m])


@dataclass
class _Unidad:
    anio: int
    nivel: Nivel
    id: str
    regimen: str
    filas: np.ndarray        # filas de la base (etiquetas de la unidad con paso válido)
    pares: np.ndarray        # posiciones en _Pares
    primer_dia: date
    paso: int | None
    hay_etiquetas: bool      # alguna etiqueta con valor (aunque el paso no sea válido)


def _unidades(b: _BaseAnio, pares: _Pares, cal: _Calendario, *, con_partes: bool = True) -> list[_Unidad]:
    salida = []
    reg_par = b.regimen[pares.i]
    for reg in sorted(set(b.regimen)):
        en = b.regimen == reg
        filas = np.flatnonzero(en & (b.p > 0))
        salida.append(_Unidad(b.anio, Nivel.REGIMEN, reg, reg, filas, np.flatnonzero(reg_par == reg),
                              cal.primer_dia_regimen(b.anio, reg), _paso_comun(b.p[filas]), bool(en.any())))
    if con_partes:
        parte_par = b.parte[pares.i]
        for parte in sorted(set(b.parte), key=_clave_parte):
            en = b.parte == parte
            filas = np.flatnonzero(en & (b.p > 0))
            reg = b.regimen[np.flatnonzero(en)[0]]
            salida.append(_Unidad(b.anio, Nivel.PARTE, parte, reg, filas, np.flatnonzero(parte_par == parte),
                                  tablas.fecha_de(cal.parte(parte).desde), _paso_comun(b.p[filas]), True))
    return salida


def _series_unidad(u: _Unidad, b: _BaseAnio, pares: _Pares, filtrada: bool) -> tuple[np.ndarray, np.ndarray]:
    """(Δy, Δx) de la unidad (Δx con forma k × m); con ``filtrada``, sin los armónicos de 24 h (§4.3.1)."""
    sel = u.pares
    if not filtrada:
        return pares.dy[sel], pares.dx[:, sel]
    k = pares.dx.shape[0]
    if sel.size == 0:
        return np.empty(0), np.empty((k, 0))
    # y: su armónico de 24 h en hora de etiqueta, sobre las etiquetas de la unidad (LF-2)
    yf = np.full(len(b.L), np.nan)
    yf[u.filas] = numerico.quitar_armonico_24(_horas(b.L[u.filas]), b.y[u.filas])
    dyf = yf[pares.i[sel]] - yf[pares.j[sel]]
    # x: Enmienda 3, E3-1 (§4.3.1): para cada c de la ventana, su armónico de 24 h en hora UTC sobre los
    # instantes que ese c empareja con la unidad, {L − c, L − c − p : L ∈ M} (LF-2 y LF-15).
    dxf = np.empty((k, sel.size))
    for n in range(k):
        instantes = np.concatenate([pares.u[sel, n], pares.up[sel, n]])
        valores = np.concatenate([pares.xu[sel, n], pares.xup[sel, n]])
        unicos, inversa = np.unique(instantes, return_inverse=True)
        x_unicos = np.empty(unicos.size)
        x_unicos[inversa] = valores
        xf = numerico.quitar_armonico_24(_horas(unicos), x_unicos)[inversa]
        dxf[n] = xf[:sel.size] - xf[sel.size:]
    return dyf, dxf


def _bloques(fechas: np.ndarray, primer_dia: date, dias: int) -> np.ndarray:
    return numerico.bloques_de_dias(fechas, primer_dia, int(dias))


def _preparado(ctx: ContextoEstacion, serie: SerieEra5 | None) -> str | None:
    """Motivo de estación que impide calcular E3 (coordenadas o píxel); None si se puede."""
    info = ctx.info
    if (not info.coordenadas_validas or info.coordenadas_inconsistentes or info.lat is None
            or info.lon is None):
        return str(MotivoSinInfo.COORDENADAS)
    if info.pixel_id is None or serie is None or not serie.tiene(int(info.pixel_id)):
        return str(MotivoSinInfo.SIN_PIXEL)
    return None


def pares_e3(extracto: pd.DataFrame, serie: SerieEra5, ctx: ContextoEstacion, variable: Variable,
             *, filtrada: bool = False) -> pd.DataFrame:
    """Pares (L, unidad, bloque, Δy, Δx(L − c) para c = −9…9) de cada parte y año-régimen.

    Con ``filtrada``, antes de diferenciar quita a y su armónico de 24 h en hora de etiqueta y a x el
    suyo en hora UTC, por unidad (parte o año-régimen) y para cada c, sobre los instantes que ese c empareja
    con la unidad (Enmienda 3, E3-1; LF-2).
    Cada par aparece una vez por unidad (en su parte y en su año-régimen), con el bloque de esa unidad
    (E3_DIAS_BLOQUE días desde su primer día calendario). Columnas: COLUMNAS_PARES_BASE + columnas_dx.
    Sin coordenadas o sin píxel devuelve una tabla vacía.
    """
    U = ctx.umbrales
    vent = ventana(U)
    columnas = list(COLUMNAS_PARES_BASE) + list(columnas_dx(U))
    if _preparado(ctx, serie) is not None:
        return pd.DataFrame(columns=columnas)
    cal = _Calendario(ctx)
    marcos = []
    for anio, b in _base_por_anio(extracto, variable, ctx.anios).items():
        pares = _pares_anio(b, serie, int(ctx.info.pixel_id), VARIABLE_ERA5[variable], vent)
        for u in _unidades(b, pares, cal):
            if u.pares.size == 0:
                continue
            dy, dx = _series_unidad(u, b, pares, filtrada)
            L = b.L[pares.i[u.pares]]
            datos = {"anio": anio, "nivel": str(u.nivel), "unidad": u.id, "regimen": u.regimen, "L": L,
                     "paso_h": b.p[pares.i[u.pares]], "bloque": _bloques(L, u.primer_dia, U.f("E3_DIAS_BLOQUE")),
                     "dy": dy}
            datos.update({nombre: dx[n] for n, nombre in enumerate(columnas_dx(U))})
            marcos.append(pd.DataFrame(datos, columns=columnas))
    if not marcos:
        return pd.DataFrame(columns=columnas)
    return pd.concat(marcos, ignore_index=True)


# ---------------------------------------------------------------------------------------------
# Estadístico y réplicas (§4.3.1, §4.0)
# ---------------------------------------------------------------------------------------------
@dataclass
class _Estadistico:
    r: np.ndarray                    # (k,)
    c_hat: int | None
    c_cont: float | None


def _estadistico(dy: np.ndarray, dx: np.ndarray, vent: tuple[int, ...]) -> _Estadistico:
    k = len(vent)
    if dy.size == 0:
        return _Estadistico(np.full(k, np.nan), None, None)
    r = numerico.correlaciones_por_desfase(dy, dx)
    c_hat = numerico.maximo_estricto(r, vent)
    c_cont = numerico.interpolar_parabola(r, c_hat, vent) if c_hat is not None else None
    return _Estadistico(r, c_hat, c_cont)


@dataclass
class _Pesos:
    """Réplicas de una unidad como cuentas de bloques (las sorteó numerico.replicas_por_bloques)."""
    W: np.ndarray            # (R, B) veces que cada bloque entra en cada réplica
    una_caliente: np.ndarray # (m, B) pertenencia de cada par a su bloque
    n_b: np.ndarray          # (B,) pares por bloque


def _pesos(bloques: np.ndarray, n_replicas: int, rng: np.random.Generator) -> _Pesos:
    indices = numerico.replicas_por_bloques(bloques, n_replicas, rng)
    _, pos, n_b = np.unique(bloques, return_inverse=True, return_counts=True)
    B = n_b.size
    W = np.empty((len(indices), B))
    for k, idx in enumerate(indices):
        W[k] = np.bincount(pos[idx], minlength=B) / n_b
    if not np.array_equal(W, np.round(W)):
        raise RuntimeError("las réplicas no son uniones de bloques completos")
    una = np.zeros((bloques.size, B))
    una[np.arange(bloques.size), pos] = 1.0
    return _Pesos(W, una, n_b.astype(np.float64))


def _r_replicas(dy: np.ndarray, dx: np.ndarray, pesos: _Pesos) -> np.ndarray:
    """r(c) de cada réplica (R × k) por sumas por bloque de las series centradas (LF-3)."""
    yc = dy - dy.mean()
    xc = dx - dx.mean(axis=1, keepdims=True)
    H = pesos.una_caliente
    sy, syy = yc @ H, (yc * yc) @ H
    sx, sxx, sxy = xc @ H, (xc * xc) @ H, (xc * yc) @ H          # (k, B)
    W = pesos.W
    N = W @ pesos.n_b
    Sy, Syy = W @ sy, W @ syy
    Sx, Sxx, Sxy = W @ sx.T, W @ sxx.T, W @ sxy.T                 # (R, k)
    vx = Sxx - Sx * Sx / N[:, None]
    vy = Syy - Sy * Sy / N
    cov = Sxy - Sx * (Sy / N)[:, None]
    with np.errstate(invalid="ignore", divide="ignore"):
        r = cov / np.sqrt(vx * vy[:, None])
    r[~((vx > 0) & (vy[:, None] > 0))] = np.nan
    return r


@dataclass
class _Replicas:
    r: np.ndarray            # (R, k)
    c_hat: np.ndarray        # (R,) float, NaN si no hay máximo estricto
    c_cont: np.ndarray       # (R,) float, NaN si no está definido


def _replicas(dy: np.ndarray, dx: np.ndarray, pesos: _Pesos, vent: tuple[int, ...]) -> _Replicas:
    r = _r_replicas(dy, dx, pesos)
    c_hat = np.full(r.shape[0], np.nan)
    c_cont = np.full(r.shape[0], np.nan)
    for k, fila in enumerate(r):
        c = numerico.maximo_estricto(fila, vent)
        if c is not None:
            c_hat[k] = c
            cc = numerico.interpolar_parabola(fila, c, vent)
            if cc is not None:
                c_cont[k] = cc
    return _Replicas(r, c_hat, c_cont)


# ---------------------------------------------------------------------------------------------
# Regla gruesa (§4.3.2)
# ---------------------------------------------------------------------------------------------
@dataclass
class _ResultadoGruesa:
    estados: dict[str, Estado]
    motivos: dict[str, str | None]
    anomalo: bool


def _regla_gruesa(r: np.ndarray, c_hat: int, c_cont: float | None, desfases_h: Mapping[str, int],
                  vent: tuple[int, ...], mu: float, tau: float, *, rep: _Replicas | None = None,
                  c_cont_rep: np.ndarray | None = None, conf: float | None = None) -> _ResultadoGruesa:
    """Estados por H de una unidad con mínimos, r máx ≥ E3_RMAX y ĉ definido (los revisa el llamador).

    ``c_cont`` es el ĉ_cont de la condición de tolerancia (en E3p, ĉ^f_cont si está definido) y
    ``c_cont_rep`` el mismo valor en cada réplica. Con ``rep`` (E3p) cada desigualdad debe cumplirse
    además en ≥ ``conf`` de las réplicas (R-12, LF-4).
    """
    pos = {c: i for i, c in enumerate(vent)}
    D = sorted(set(desfases_h.values()))
    hs = list(desfases_h)
    dist_rival, dist_chat = _c("E3_DIST_RIVAL"), _c("E3_DIST_CHAT")

    def en_replicas(condicion: Callable[[_Replicas], np.ndarray]) -> bool:
        return rep is None or float(np.mean(condicion(rep))) >= conf

    # LF-6: alias de 12 h de alguna H → la unidad entera sin información
    if c_hat not in D and any(numerico.es_alias_12(c_hat, c) for c in D):
        return _ResultadoGruesa({h: Estado.SIN_INFORMACION for h in hs},
                                {h: str(MotivoSinInfo.ALIAS) for h in hs}, False)

    por_desfase: dict[int, tuple[Estado, str | None]] = {}
    for c in D:
        ic = pos[c]
        otros = [pos[d] for d in D if d != c]
        lejanos = [pos[d] for d in D if abs(d - c) >= dist_rival]
        incompatible = False
        for id_ in lejanos:                                    # existe H′ a ≥ 2 h con ventaja ≥ μ
            if r[id_] - r[ic] >= mu and en_replicas(lambda q, a=id_: q.r[:, a] - q.r[:, ic] >= mu):
                incompatible = True
                break
        if (not incompatible and abs(c_hat - c) >= dist_chat and not numerico.es_alias_12(c_hat, c)
                and r[pos[c_hat]] - r[ic] >= mu
                and en_replicas(lambda q: q.r[:, pos[c_hat]] - q.r[:, ic] >= mu)):
            incompatible = True
        if incompatible:
            por_desfase[c] = (Estado.INCOMPATIBLE, None)
            continue
        maximo = all(r[ic] > r[o] for o in otros) and en_replicas(
            lambda q: np.all(q.r[:, [ic]] > q.r[:, otros], axis=1) if otros else np.ones(len(q.r), bool))
        margen = all(r[ic] - r[o] >= mu and en_replicas(lambda q, a=o: q.r[:, ic] - q.r[:, a] >= mu)
                     for o in lejanos)
        tolerancia = (c_cont is not None and abs(c_cont - c) <= tau
                      and (rep is None or float(np.mean(np.abs(c_cont_rep - c) <= tau)) >= conf))
        if maximo and margen and tolerancia:
            por_desfase[c] = (Estado.COMPATIBLE, None)
        else:
            por_desfase[c] = (Estado.SIN_INFORMACION, str(MotivoSinInfo.RESIDUAL))

    anomalo = False
    if c_hat not in D:
        en_P = [pos[d] for d in D]
        if r[pos[c_hat]] - max(r[i] for i in en_P) >= mu:
            anomalo = (en_replicas(lambda q: q.r[:, pos[c_hat]] - q.r[:, en_P].max(axis=1) >= mu)
                       and en_replicas(lambda q: q.c_hat == c_hat))
    return _ResultadoGruesa({h: por_desfase[desfases_h[h]][0] for h in hs},
                            {h: por_desfase[desfases_h[h]][1] for h in hs}, anomalo)


# ---------------------------------------------------------------------------------------------
# Filas de estados y de métricas
# ---------------------------------------------------------------------------------------------
def _filas(ctx: ContextoEstacion, anio: int, linea: Linea, nivel: Nivel, unidad: str,
           estados_h: Mapping[str, Estado], motivos: Mapping[str, str | None] | str | None = None, *,
           regla: Regla, anomalo: bool = False) -> pd.DataFrame:
    """estados.filas_estado con un motivo por H (o uno común)."""
    df = estados.filas_estado(ctx.info.codigo, anio, linea, nivel, unidad, estados_h, regla=regla,
                              reloj_anomalo=anomalo, motivo=motivos if isinstance(motivos, str) else None)
    if isinstance(motivos, Mapping):
        df["motivo"] = pd.array([motivos.get(h) for h in df["H"]], dtype="string")
    return df


def _todas(ctx: ContextoEstacion, estado: Estado) -> dict[str, Estado]:
    return {h.id: estado for h in ctx.info.P}


def _unir_estados(marcos: list[pd.DataFrame]) -> pd.DataFrame:
    marcos = [m for m in marcos if len(m)]
    if not marcos:
        return tabla_vacia(ESQUEMA_ESTADOS)
    salida = pd.concat(marcos, ignore_index=True).astype(ESQUEMA_ESTADOS)
    validar_esquema(salida, ESQUEMA_ESTADOS, nombre="estados de lineas_fisicas")
    return salida


def _tabla(filas: list[dict], esquema: Mapping[str, str], nombre: str) -> pd.DataFrame:
    if not filas:
        return tabla_vacia(esquema)
    df = pd.DataFrame(filas, columns=list(esquema)).astype(esquema)
    validar_esquema(df, esquema, nombre=nombre)
    return df


def _lista(r: np.ndarray | None) -> list[float] | None:
    return None if r is None else [float(v) for v in r]


def _nulo(v) -> bool:
    return v is None or (not isinstance(v, (list, tuple, np.ndarray)) and pd.isna(v))


# ---------------------------------------------------------------------------------------------
# E3 (§4.3.1 a §4.3.3)
# ---------------------------------------------------------------------------------------------
def _motivo_e3t(ctx: ContextoEstacion) -> str | None:
    """§3.3: sin z_cat legible → sin desnivel; estación costera → E3t sin información."""
    if ctx.info.dz is None or not np.isfinite(ctx.info.dz):
        return str(MotivoSinInfo.SIN_DESNIVEL)
    if ctx.info.costera and ctx.aplicar_exclusion_costera:
        return str(MotivoSinInfo.COSTERA)
    return None


def _fila_metrica(ctx, u: _Unidad, variable: str, n_pares: int, n_bloques: int, est: _Estadistico,
                  estab: float, est_f: _Estadistico | None, estab_f: float) -> dict:
    return {"codigo": ctx.info.codigo, "anio": u.anio, "nivel": str(u.nivel), "unidad": u.id,
            "regimen": u.regimen, "variable": variable, "paso_h": u.paso, "n_pares": n_pares,
            "n_bloques": n_bloques, "r": _lista(est.r), "c_hat": est.c_hat,
            "c_hat_cont": np.nan if est.c_cont is None else est.c_cont, "estab_c_hat": estab,
            "r_f": None if est_f is None else _lista(est_f.r), "c_hat_f": None if est_f is None else est_f.c_hat,
            "c_hat_f_cont": np.nan if est_f is None or est_f.c_cont is None else est_f.c_cont,
            "estab_c_hat_f": estab_f, "fino": False, "filtro_e3t": False, "cociente_a1": np.nan,
            "r_diaria": np.nan}


def _evaluar_unidad(ctx, cal: _Calendario, u: _Unidad, b: _BaseAnio, pares: _Pares, variable: str,
                    vent: tuple[int, ...]) -> tuple[dict, dict[str, Estado], dict[str, str | None], bool]:
    """Métricas y estados de la regla gruesa en una unidad (antes de los motivos de estación de E3t)."""
    U = ctx.umbrales
    qfe = variable == "QFE"
    dy, dx = _series_unidad(u, b, pares, False)
    n = int(dy.size)
    fechas = b.L[pares.i[u.pares]]
    bloques = _bloques(fechas, u.primer_dia, U.f("E3_DIAS_BLOQUE"))
    n_bloques = int(np.unique(bloques).size)
    if u.nivel == Nivel.PARTE:
        bloques_min = _bloques(fechas, u.primer_dia, U.f("E3_DIAS_BLOQUE_PARTE"))
        minimos = n >= U.f("E3_PARES_PARTE") and np.unique(bloques_min).size >= U.f("E3_BLOQUES_PARTE")
    else:
        minimos = n >= U.f("E3_PARES_REGIMEN")
    est = _estadistico(dy, dx, vent)
    est_f, rep, rep_f = None, None, None
    estab, estab_f = np.nan, np.nan
    if qfe:
        serie_f = _series_unidad(u, b, pares, True)          # una vez por unidad (E3-1: 19 ajustes de sp)
        est_f = _estadistico(*serie_f, vent)
        if minimos:
            semilla = numerico.semilla(int(U.f("SEMILLA")), ctx.info.codigo, u.anio, u.id, variable)
            pesos = _pesos(bloques, int(U.f("E3_REPLICAS")), numerico.generador(semilla))
            rep = _replicas(dy, dx, pesos, vent)
            rep_f = _replicas(*serie_f, pesos, vent)   # mismas réplicas (R-33)
            if est.c_hat is not None:
                estab = float(np.mean(rep.c_hat == est.c_hat))
            if est_f.c_hat is not None:
                estab_f = float(np.mean(rep_f.c_hat == est_f.c_hat))
    metrica = _fila_metrica(ctx, u, variable, n, n_bloques, est, estab, est_f, estab_f)
    desfases_h = cal.desfases(u.anio, u.regimen)
    if qfe and u.nivel == Nivel.REGIMEN:
        metrica["fino"] = _es_fino(metrica, ctx, desfases_h)[0]
    hs = [h.id for h in ctx.info.P]
    if not minimos:
        motivo = str(MotivoSinInfo.PASO) if u.filas.size == 0 and u.hay_etiquetas else str(MotivoSinInfo.MINIMOS)
        return metrica, {h: Estado.SIN_INFORMACION for h in hs}, {h: motivo for h in hs}, False
    if not np.isfinite(est.r).any() or np.nanmax(est.r) < U.a("E3_RMAX"):
        return metrica, {h: Estado.SIN_INFORMACION for h in hs}, {h: str(MotivoSinInfo.RMAX) for h in hs}, False
    if est.c_hat is None:
        return metrica, {h: Estado.SIN_INFORMACION for h in hs}, {h: str(MotivoSinInfo.EMPATE) for h in hs}, False
    if qfe:
        usar_f = est_f is not None and est_f.c_cont is not None
        res = _regla_gruesa(est.r, est.c_hat, est_f.c_cont if usar_f else est.c_cont, desfases_h, vent,
                            U.a("E3P_MU"), U.a("E3P_TAU"), rep=rep,
                            c_cont_rep=rep_f.c_cont if usar_f else rep.c_cont, conf=U.a("E3P_CONF"))
    else:
        res = _regla_gruesa(est.r, est.c_hat, est.c_cont, desfases_h, vent, U.a("E3T_MU"), U.a("E3T_TAU"))
    return metrica, res.estados, res.motivos, res.anomalo


def _evaluar_e3(extracto, serie, ctx, variable) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Estados por unidad (regimen y, en QFE, parte) y métricas de E3t o E3p."""
    linea = LINEA_E3[variable]
    U = ctx.umbrales
    vent = ventana(U)
    cal = _Calendario(ctx)
    hs = [h.id for h in ctx.info.P]
    marcos: list[pd.DataFrame] = []
    metricas: list[dict] = []
    bloqueo = _preparado(ctx, serie)
    if bloqueo is not None:
        for anio in ctx.anios:
            for reg in cal.regimenes_con_datos(anio):
                marcos.append(_filas(ctx, anio, linea, Nivel.REGIMEN, reg, _todas(ctx, Estado.SIN_INFORMACION),
                                     bloqueo, regla=Regla.GRUESA))
        return _unir_estados(marcos), _tabla(metricas, ESQUEMA_METRICAS_E3, "métricas E3")
    qfe = variable == "QFE"
    motivo_t = None if qfe else _motivo_e3t(ctx)
    filtro = None if qfe else filtro_representatividad(extracto, serie, ctx)
    for anio, b in _base_por_anio(extracto, variable, ctx.anios).items():
        pares = _pares_anio(b, serie, int(ctx.info.pixel_id), VARIABLE_ERA5[variable], vent)
        unidades = _unidades(b, pares, cal, con_partes=qfe)
        vistos = set()
        for u in unidades:
            metrica, est_h, mot_h, anomalo = _evaluar_unidad(ctx, cal, u, b, pares, variable, vent)
            if not qfe:
                fila_f = filtro[(filtro["anio"] == anio) & (filtro["regimen"] == u.id)]
                pasa = bool(fila_f["pasa"].iloc[0]) if len(fila_f) else False
                metrica.update(filtro_e3t=pasa, cociente_a1=float(fila_f["cociente_a1"].iloc[0]) if len(fila_f)
                               else np.nan, r_diaria=float(fila_f["r_diaria"].iloc[0]) if len(fila_f) else np.nan)
                if anomalo:                               # E3t nunca señala reloj anómalo (§4.3.3)
                    mot_h = {h: _ANOMALO_INFORME for h in hs}
                    anomalo = False
                # precedencia del motivo: estación (desnivel, costera) > datos (paso, mínimos) > filtro
                de_datos = set(mot_h.values()) <= {str(MotivoSinInfo.PASO), str(MotivoSinInfo.MINIMOS)}
                if motivo_t is not None or (not pasa and not de_datos):
                    motivo = motivo_t or str(MotivoSinInfo.FILTRO)
                    est_h, mot_h = {h: Estado.SIN_INFORMACION for h in hs}, {h: motivo for h in hs}
            metricas.append(metrica)
            marcos.append(_filas(ctx, anio, linea, u.nivel, u.id, est_h, mot_h, regla=Regla.GRUESA, anomalo=anomalo))
            if u.nivel == Nivel.REGIMEN:
                vistos.add(u.id)
        for reg in cal.regimenes_con_datos(anio):
            if reg not in vistos:
                marcos.append(_filas(ctx, anio, linea, Nivel.REGIMEN, reg, _todas(ctx, Estado.SIN_INFORMACION),
                                     str(MotivoSinInfo.MINIMOS), regla=Regla.GRUESA))
    return _unir_estados(marcos), _tabla(metricas, ESQUEMA_METRICAS_E3, "métricas E3")


def _anual_por_regimenes(ctx: ContextoEstacion, por_unidad: pd.DataFrame, linea: Linea, regla: Regla) -> pd.DataFrame:
    """Anual desde los años-régimen (E3t, LF-7; E4p, §4.4 y LF-11): incompatible si lo es en alguno;
    compatible si todos los evaluables lo son (≥ 1); dudosa si hay evaluables y no; si no, sin información."""
    regs = por_unidad[por_unidad["nivel"] == str(Nivel.REGIMEN)]
    marcos = []
    for anio in ctx.anios:
        del_anio = regs[regs["anio"] == anio]
        est_h, mot_h = {}, {}
        for h in ctx.info.P:
            valores = [Estado(v) for v in del_anio.loc[del_anio["H"] == h.id, "estado"]]
            evaluables = [v for v in valores if v != Estado.SIN_INFORMACION]
            if Estado.INCOMPATIBLE in valores:
                est_h[h.id], mot_h[h.id] = Estado.INCOMPATIBLE, None
            elif evaluables and all(v == Estado.COMPATIBLE for v in evaluables):
                est_h[h.id], mot_h[h.id] = Estado.COMPATIBLE, None
            elif evaluables:
                est_h[h.id], mot_h[h.id] = Estado.DUDOSA, None
            else:
                est_h[h.id], mot_h[h.id] = Estado.SIN_INFORMACION, str(MotivoSinInfo.NO_INFORMATIVA)
        marcos.append(_filas(ctx, anio, linea, Nivel.ANIO, f"{anio:04d}", est_h, mot_h, regla=regla))
    return _unir_estados(marcos)


def e3(extracto: pd.DataFrame, serie: SerieEra5 | None, ctx: ContextoEstacion, variable: Variable) -> ResultadoLinea:
    """r(c), ĉ, ĉ_cont (y en QFE r^f, ĉ^f, ĉ^f_cont y estabilidades) por parte y año-régimen; estados de
    la regla gruesa (§4.3.2) por unidad. Variable «Ts» → Linea.E3T (sólo años-régimen, sin réplicas);
    «QFE» → Linea.E3P (partes y años-régimen, con réplicas). Sin información si faltan los mínimos de
    §3.5, si máx r < E3_RMAX, si hay empate exacto, si es alias o residual.

    E3p: las filas de parte y año-régimen pasan por estados.anual_por_partes (§4.0), que marca las partes
    discordantes y agrega las filas anuales de la gruesa (sólo incompatible y anómalo; la compatibilidad
    anual la da ``e3p_anual``). E3t: filas por año-régimen y un anual propio (LF-7), sin reloj anómalo.
    Las métricas del año-régimen de QFE traen ``fino`` (§4.3.4); las de Ts, el filtro de §4.3.3.
    """
    if variable not in LINEA_E3:
        raise ValueError(f"variable de E3 desconocida: {variable!r}")
    linea = LINEA_E3[variable]
    por_unidad, metricas = _evaluar_e3(extracto, serie, ctx, variable)
    if variable == "QFE":
        estados_ = estados.anual_por_partes(por_unidad, linea=linea, regla=Regla.GRUESA,
                                            min_partes=_c("ANUAL_MIN_PARTES")) if len(por_unidad) else por_unidad
    else:
        estados_ = _unir_estados([_anual_por_regimenes(ctx, por_unidad, linea, Regla.GRUESA), por_unidad])
    return ResultadoLinea(linea=linea, estados=_unir_estados([estados_]), metricas=metricas)


# ---------------------------------------------------------------------------------------------
# Filtro de representatividad de E3t (§4.3.3)
# ---------------------------------------------------------------------------------------------
@dataclass
class _Diurno:
    n_h: int
    hueco: int
    K: int
    ajuste: numerico.AjusteArmonico | None


def _hueco_circular(cubiertas: np.ndarray) -> int:
    """Mayor distancia circular (h) entre horas cubiertas consecutivas (LF-10); 24 si hay 0 o 1."""
    if cubiertas.size <= 1:
        return _HORAS_DIA
    ordenadas = np.sort(cubiertas)
    saltos = np.diff(np.concatenate([ordenadas, ordenadas[:1] + _HORAS_DIA]))
    return int(saltos.max())


def _anomalias_del_dia(L: np.ndarray, y: np.ndarray, p: np.ndarray, min_valores: int) -> tuple[np.ndarray, np.ndarray]:
    """(filas en días válidos, anomalía respecto de la media de su día de etiqueta). Día válido: ≥
    ``min_valores`` valores si p = 1; completo (24/p etiquetas) si p > 1 (§4.4, R-53)."""
    if L.size == 0:
        return np.zeros(0, bool), np.zeros(0)
    dias = L.astype("datetime64[D]")
    _, primero, inversa, cuentas = np.unique(dias, return_index=True, return_inverse=True, return_counts=True)
    p_dia = p[primero]
    validos = np.where(p_dia == 1, cuentas >= min_valores, cuentas == _HORAS_DIA // np.maximum(p_dia, 1))
    media = np.bincount(inversa, y) / cuentas
    return validos[inversa], y - media[inversa]


def _ajuste_diurno(t: np.ndarray, a: np.ndarray, hora: np.ndarray, minimo: int, umbrales) -> _Diurno:
    """§4.4: horas cubiertas, hueco, K = mín(3, ⌊(n_h − 1)/2⌋) y ajuste con EE × E4_EE_FACTOR."""
    cuentas = np.bincount(hora.astype(np.int64), minlength=_HORAS_DIA)
    cubiertas = np.flatnonzero(cuentas >= minimo)
    n_h = int(cubiertas.size)
    K = numerico.K_de_n_h(n_h, _c("E4_K_MAX"))
    ajuste = None
    if K >= 1:
        usar = np.isin(hora, cubiertas)
        try:
            ajuste = numerico.ajuste_armonico(t[usar], a[usar], K, umbrales.f("E4_EE_FACTOR"))
        except ValueError:
            ajuste = None
    return _Diurno(n_h, _hueco_circular(cubiertas), K, ajuste)


def _a1(d: _Diurno) -> float:
    return float(d.ajuste.amplitudes[0]) if d.ajuste is not None else np.nan


def filtro_representatividad(extracto: pd.DataFrame, serie: SerieEra5 | None, ctx: ContextoEstacion) -> pd.DataFrame:
    """§4.3.3, por año-régimen: |Δz| ≤ 400 m, no costera, cociente A1(Ts)/A1(t2m) en [0,5; 2] y
    correlación ≥ 0,8 de medias diarias. Columnas: anio, regimen, pasa, cociente_a1, r_diaria.

    No depende de ningún reloj: compara el día de etiqueta D de Ts con el día UTC D de t2m (LF-12).
    Una fila por año de ctx.anios y año-régimen con datos; sin z_cat, costera (con la exclusión
    costera aplicada), sin coordenadas o sin píxel, ``pasa`` es falso. Las métricas se calculan igual
    cuando hay píxel, para el informe.
    """
    U = ctx.umbrales
    cal = _Calendario(ctx)
    filas = []
    bloqueo = _preparado(ctx, serie)
    dz = ctx.info.dz
    estacion_pasa = (bloqueo is None and _motivo_e3t(ctx) is None and abs(dz) <= U.f("E3T_DZ_M"))
    bases = _base_por_anio(extracto, "Ts", ctx.anios) if bloqueo is None else {}
    for anio in ctx.anios:
        b = bases.get(anio)
        regs = cal.regimenes_con_datos(anio, () if b is None else tuple(set(b.regimen)))
        for reg in regs:
            cociente, r_diaria = np.nan, np.nan
            if b is not None:
                cociente, r_diaria = _filtro_regimen(b, reg, serie, int(ctx.info.pixel_id), U)
            pasa = bool(estacion_pasa and np.isfinite(cociente) and np.isfinite(r_diaria)
                        and U.f("E3T_A1_MIN") <= cociente <= U.f("E3T_A1_MAX") and r_diaria >= U.f("E3T_R_DIARIA"))
            filas.append({"anio": int(anio), "regimen": reg, "pasa": pasa, "cociente_a1": float(cociente),
                          "r_diaria": float(r_diaria)})
    return pd.DataFrame(filas, columns=list(COLUMNAS_FILTRO)).astype(
        {"anio": "int16", "regimen": "string", "pasa": "bool", "cociente_a1": "float64", "r_diaria": "float64"})


def _filtro_regimen(b: _BaseAnio, regimen: str, serie: SerieEra5, pixel: int, U) -> tuple[float, float]:
    filas = np.flatnonzero((b.regimen == regimen) & (b.p > 0))
    if filas.size == 0:
        return np.nan, np.nan
    L, y, p = b.L[filas], b.y[filas], b.p[filas]
    en_dia_valido, anomalia = _anomalias_del_dia(L, y, p, _c("E3T_DIA_MIN_VALORES"))
    dias = L.astype("datetime64[D]")
    dias_validos = np.unique(dias[en_dia_valido])
    if dias_validos.size == 0:
        return np.nan, np.nan
    # t2m de los días UTC con el mismo calendario, completos
    horas = dias_validos.astype("datetime64[ns]")[:, None] + _horas_td(np.arange(_HORAS_DIA))[None, :]
    x = np.asarray(serie.valores(pixel, "t2m", horas.ravel()), dtype=np.float64).reshape(horas.shape)
    completos = np.isfinite(x).all(axis=1)
    if not completos.any():
        return np.nan, np.nan
    dias_ok = dias_validos[completos]
    x = x[completos]
    # medias diarias y correlación (§4.3.3)
    usar = en_dia_valido & np.isin(dias, dias_ok)
    _, inv = np.unique(dias[usar], return_inverse=True)
    media_ts = np.bincount(inv, y[usar]) / np.bincount(inv)
    r_diaria = numerico.pearson(media_ts, x.mean(axis=1)) if dias_ok.size >= 2 else np.nan
    # amplitudes diurnas: Ts en hora de etiqueta, t2m en hora UTC
    hora_et = np.mod(_horas(L[usar]), _HORAS_DIA)
    d_ts = _ajuste_diurno(hora_et, anomalia[usar], np.floor(hora_et), U.f("E4_VALORES_HORA_REGIMEN"), U)
    hora_utc = np.tile(np.arange(_HORAS_DIA, dtype=np.float64), dias_ok.size)
    a_x = (x - x.mean(axis=1, keepdims=True)).ravel()
    d_x = _ajuste_diurno(hora_utc, a_x, hora_utc, U.f("E4_VALORES_HORA_REGIMEN"), U)
    a1_x = _a1(d_x)
    cociente = _a1(d_ts) / a1_x if np.isfinite(a1_x) and a1_x > 0 else np.nan
    return float(cociente), float(r_diaria)


# ---------------------------------------------------------------------------------------------
# Regla fina de E3p (§4.3.4) y E3p anual
# ---------------------------------------------------------------------------------------------
def _es_fino(fila: Mapping, ctx: ContextoEstacion, desfases_h: Mapping[str, int]) -> tuple[bool, str | None]:
    """§4.3.4: año-régimen fino (seis condiciones, más ĉ^f definido y máx r^f ≥ E3_RMAX, LF-8)."""
    U = ctx.umbrales
    lat = ctx.info.lat
    if lat is None or not abs(lat) <= _c("FINA_LAT_MAX"):
        return False, "lat"
    if int(fila["n_pares"]) < U.f("E3_PARES_REGIMEN"):
        return False, str(MotivoSinInfo.MINIMOS)
    r_f = fila["r_f"]
    if r_f is None or not np.isfinite(np.asarray(r_f, dtype=float)).any() or np.nanmax(r_f) < U.a("E3_RMAX"):
        return False, str(MotivoSinInfo.RMAX)
    c = fila["c_hat_f"]
    if _nulo(c):
        return False, str(MotivoSinInfo.EMPATE)
    c = int(c)
    estab = fila["estab_c_hat_f"]
    if _nulo(estab) or not estab >= U.a("E3P_FINA_ESTAB"):
        return False, "estabilidad"
    if abs(c) > _c("FINA_C_MAX"):
        return False, "c_max"
    cc = fila["c_hat_f_cont"]
    if _nulo(cc) or not abs(cc - c) <= U.a("E3P_FINA_TAU"):
        return False, "interpolacion"
    if any(numerico.es_alias_12(c, d) for d in set(desfases_h.values())):
        return False, str(MotivoSinInfo.ALIAS)
    return True, None


def fina_apagada(metricas_e3p: pd.DataFrame, ctx: ContextoEstacion) -> tuple[bool, float]:
    """§4.3.4, «Apagado»: (apagada, mediana de ĉ^f_cont − ĉ^f en los años-régimen finos de la estación)."""
    cal = _Calendario(ctx)
    difs = []
    for _, fila in _regimenes_qfe(metricas_e3p).iterrows():
        if _es_fino(fila, ctx, cal.desfases(int(fila["anio"]), fila["unidad"]))[0]:
            difs.append(float(fila["c_hat_f_cont"]) - int(fila["c_hat_f"]))
    if not difs:
        return False, np.nan
    mediana = float(np.median(difs))
    return bool(abs(mediana) > ctx.umbrales.a("E3P_FINA_APAGADO")), mediana


def _regimenes_qfe(metricas: pd.DataFrame) -> pd.DataFrame:
    if metricas is None or not len(metricas):
        return tabla_vacia(ESQUEMA_METRICAS_E3)
    return metricas[(metricas["nivel"] == str(Nivel.REGIMEN)) & (metricas["variable"] == "QFE")]


def e3_fina(metricas_e3p: pd.DataFrame, ctx: ContextoEstacion) -> ResultadoLinea:
    """Regla fina (§4.3.4) sobre las métricas filtradas de E3p: años-régimen finos, estados por año,
    reloj anómalo y apagado por estación (mediana de ĉ^f_cont − ĉ^f > E3P_FINA_APAGADO). Regla «fina».

    Filas: por año-régimen (compatible si ĉ^f = c_H(R), incompatible si no; sin información si no es
    fino, con motivo «no_fino:<condición>»), y anuales: incompatible si algún año-régimen fino tiene
    ĉ^f ≠ c_H(R); compatible si todos los finos (≥ 1) tienen ĉ^f = c_H(R); anómalo si ĉ^f no es el
    desfase de ninguna H de P en R. Con la regla apagada, todo queda sin información (LF-9).
    Métricas: las del año-régimen con ``fino`` recalculado.
    """
    cal = _Calendario(ctx)
    hs = [h.id for h in ctx.info.P]
    regs = _regimenes_qfe(metricas_e3p).copy()
    apagada, _ = fina_apagada(metricas_e3p, ctx)
    marcos = []
    finos = []
    for anio in ctx.anios:
        del_anio = regs[regs["anio"] == anio]
        por_reg: dict[str, tuple[dict, bool, bool]] = {}   # estados, anómalo, fino y activo
        for idx, fila in del_anio.iterrows():
            desf = cal.desfases(int(anio), fila["unidad"])
            fino, motivo = _es_fino(fila, ctx, desf)
            finos.append((idx, fino))
            if apagada:
                est_h, mot, anom = _todas(ctx, Estado.SIN_INFORMACION), str(MotivoSinInfo.APAGADA), False
            elif fino:
                c = int(fila["c_hat_f"])
                est_h = {h: Estado.COMPATIBLE if desf[h] == c else Estado.INCOMPATIBLE for h in hs}
                mot, anom = None, c not in set(desf.values())
            else:
                est_h, mot, anom = _todas(ctx, Estado.SIN_INFORMACION), f"{_NO_FINO}:{motivo}", False
            por_reg[fila["unidad"]] = (est_h, anom, fino and not apagada)
            marcos.append(_filas(ctx, int(anio), Linea.E3P, Nivel.REGIMEN, fila["unidad"], est_h, mot,
                                 regla=Regla.FINA, anomalo=anom))
        for reg in cal.regimenes_con_datos(int(anio)):
            if reg not in por_reg:
                motivo = str(MotivoSinInfo.APAGADA) if apagada else f"{_NO_FINO}:{MotivoSinInfo.MINIMOS}"
                marcos.append(_filas(ctx, int(anio), Linea.E3P, Nivel.REGIMEN, reg, _todas(ctx, Estado.SIN_INFORMACION),
                                     motivo, regla=Regla.FINA))
        activos = [v for v in por_reg.values() if v[2]]
        anom_anual = any(v[1] for v in activos)
        est_h, mot_h = {}, {}
        for h in hs:
            if not activos:
                est_h[h] = Estado.SIN_INFORMACION
                mot_h[h] = str(MotivoSinInfo.APAGADA) if apagada else str(MotivoSinInfo.NO_INFORMATIVA)
            elif any(v[0][h] == Estado.INCOMPATIBLE for v in activos):
                est_h[h], mot_h[h] = Estado.INCOMPATIBLE, None
            else:
                est_h[h], mot_h[h] = Estado.COMPATIBLE, None
        marcos.append(_filas(ctx, int(anio), Linea.E3P, Nivel.ANIO, f"{int(anio):04d}", est_h, mot_h,
                             regla=Regla.FINA, anomalo=anom_anual))
        if apagada:
            marcos.append(_filas(ctx, int(anio), Linea.E3P, Nivel.ESTACION, "*", _todas(ctx, Estado.SIN_INFORMACION),
                                 str(MotivoSinInfo.APAGADA), regla=Regla.FINA))
    for idx, fino in finos:
        regs.at[idx, "fino"] = fino
    return ResultadoLinea(linea=Linea.E3P, estados=_unir_estados(marcos),
                          metricas=regs.astype(ESQUEMA_METRICAS_E3).reset_index(drop=True))


def e3p_anual(estados_gruesa: pd.DataFrame, estados_fina: pd.DataFrame, fina_activa: bool) -> pd.DataFrame:
    """E3p anual (§4.3.4): incompatible por la gruesa (según §4.0) o por la fina; compatible si no es
    incompatible y es compatible por la fina o por la gruesa en todos sus años-régimen informativos (≥ 1).
    Lo llama decision.py después de A3 (``fina_activa`` = consecuencia de A3 y del apagado).

    Informativo (Enmienda 3, opción R; por año-régimen, LF-17): la gruesa le da compatible o incompatible a
    alguna H de P en ese año-régimen, o es fino (la fina activa le da compatible o incompatible). El conjunto
    es el mismo para todas las H del año: un año-régimen en que la gruesa deja residual a H y da compatible o
    incompatible a otra H cuenta para H, y H no queda compatible. Reloj anómalo anual: el de la gruesa
    (§4.0) o, con la fina activa, el de la fina. Salida: filas de nivel «anio», regla «unica» (el estado
    combinado de la línea), con motivo «gruesa», «fina» o «gruesa,fina» según de dónde vino el estado. Si
    la gruesa no trae filas anuales, se calculan con estados.anual_por_partes.
    """
    columnas = list(ESQUEMA_ESTADOS)
    g = estados_gruesa[(estados_gruesa["linea"] == str(Linea.E3P)) & (estados_gruesa["regla"] == str(Regla.GRUESA))]
    g = g[columnas].astype(ESQUEMA_ESTADOS)
    if not len(g):
        return tabla_vacia(ESQUEMA_ESTADOS)
    if not (g["nivel"] == str(Nivel.ANIO)).any():
        g = estados.anual_por_partes(g[g["nivel"] != str(Nivel.ANIO)], linea=Linea.E3P, regla=Regla.GRUESA,
                                     min_partes=_c("ANUAL_MIN_PARTES"))
    if g["codigo"].nunique() != 1:
        raise ValueError("e3p_anual recibe filas de una sola estación")
    f = tabla_vacia(ESQUEMA_ESTADOS)
    if fina_activa and estados_fina is not None and len(estados_fina):
        f = estados_fina[(estados_fina["linea"] == str(Linea.E3P)) & (estados_fina["regla"] == str(Regla.FINA))]
        f = f[columnas].astype(ESQUEMA_ESTADOS)
    informativos = (str(Estado.COMPATIBLE), str(Estado.INCOMPATIBLE))
    codigo = g["codigo"].iloc[0]
    marcos = []
    anuales_g = g[g["nivel"] == str(Nivel.ANIO)]
    for anio, del_anio in anuales_g.groupby("anio", sort=True):
        anio = int(anio)
        fa_anio = f[(f["anio"] == anio) & (f["nivel"] == str(Nivel.ANIO))]
        anomalo = bool(del_anio["reloj_anomalo"].any()) or bool(fa_anio["reloj_anomalo"].any())
        # Enmienda 3, opción R (LF-17): informativo por año-régimen, el mismo conjunto para todas las H del año.
        sel_rg = (g["anio"] == anio) & (g["nivel"] == str(Nivel.REGIMEN)) & g["estado"].isin(informativos)
        sel_rf = (f["anio"] == anio) & (f["nivel"] == str(Nivel.REGIMEN)) & f["estado"].isin(informativos)
        info = sorted(set(g.loc[sel_rg, "unidad"]) | set(f.loc[sel_rf, "unidad"]))
        est_h, mot_h = {}, {}
        for _, fila in del_anio.iterrows():
            h = fila["H"]
            inc_g = fila["estado"] == str(Estado.INCOMPATIBLE)
            fh = fa_anio[fa_anio["H"] == h]
            inc_f = bool(len(fh)) and fh["estado"].iloc[0] == str(Estado.INCOMPATIBLE)
            if inc_g or inc_f:
                est_h[h] = Estado.INCOMPATIBLE
                mot_h[h] = ",".join(n for n, v in (("gruesa", inc_g), ("fina", inc_f)) if v)
                continue
            sel = (g["anio"] == anio) & (g["nivel"] == str(Nivel.REGIMEN)) & (g["H"] == h)
            reg_g = dict(zip(g.loc[sel, "unidad"], g.loc[sel, "estado"]))
            sel_f = (f["anio"] == anio) & (f["nivel"] == str(Nivel.REGIMEN)) & (f["H"] == h)
            reg_f = dict(zip(f.loc[sel_f, "unidad"], f.loc[sel_f, "estado"]))
            comp = str(Estado.COMPATIBLE)
            if info and all(reg_f.get(r) == comp or reg_g.get(r) == comp for r in info):
                est_h[h] = Estado.COMPATIBLE
                fuentes = (("gruesa", any(reg_g.get(r) == comp for r in info)),
                           ("fina", any(reg_f.get(r) == comp for r in info)))
                mot_h[h] = ",".join(n for n, v in fuentes if v)
            else:
                est_h[h] = Estado.SIN_INFORMACION
                mot_h[h] = str(MotivoSinInfo.NO_INFORMATIVA if not info else MotivoSinInfo.RESIDUAL)
        df = estados.filas_estado(codigo, anio, Linea.E3P, Nivel.ANIO, f"{anio:04d}", est_h, regla=Regla.UNICA,
                                  reloj_anomalo=anomalo)
        df["motivo"] = pd.array([mot_h.get(h) for h in df["H"]], dtype="string")
        marcos.append(df)
    return _unir_estados(marcos)


def diagnostico_subhorario(metricas_e3p: pd.DataFrame, ctx: ContextoEstacion) -> dict:
    """§4.3.5 con la Enmienda 3 (B6; LF-18): ρ = media circular de período 1 h de ĉ^f_cont, llevada a
    [−0,5; 0,5) (el estadístico de A5), en todos los años-régimen de QFE de la estación con ĉ^f_cont definido,
    si |lat| ≤ 50°; marca «posible media horaria» si |ρ| > SUBH_RHO_H con ≥ SUBH_MIN_REGIMENES años-régimen.
    Devuelve {"rho", "n", "marca"}. guardas.marca_media_horaria delega aquí. El reloj no cambia.
    """
    U = ctx.umbrales
    lat = ctx.info.lat
    valores = []
    if lat is not None and abs(lat) <= _c("SUBH_LAT_MAX"):
        valores = [float(v) for v in _regimenes_qfe(metricas_e3p)["c_hat_f_cont"] if not _nulo(v)]
    rho = numerico.media_circular_en(np.asarray(valores, dtype=np.float64), _c("A5_ENVOLVER")) if valores else np.nan
    marca = bool(len(valores) >= U.f("SUBH_MIN_REGIMENES") and np.isfinite(rho) and abs(rho) > U.f("SUBH_RHO_H"))
    return {"rho": float(rho), "n": len(valores), "marca": marca}


# ---------------------------------------------------------------------------------------------
# E4 (§4.4)
# ---------------------------------------------------------------------------------------------
def ajustes_e4(extracto: pd.DataFrame, ctx: ContextoEstacion, variable: VariableE4) -> pd.DataFrame:
    """Ajuste de §4.4 por parte y año-régimen en hora solar de etiqueta t0: anomalía respecto de la media
    del día de etiqueta (días con ≥ 20 valores si p = 1, completos si p > 1), K = mín(3, ⌊(n_h − 1)/2⌋),
    EE × 2. Devuelve ESQUEMA_METRICAS_E4. Lo usan E4p (QFE), E4t y G-HR (Ts, HR).

    Mínimo por hora cubierta: E4_VALORES_HORA_PARTE en la parte y E4_VALORES_HORA_REGIMEN en el
    año-régimen (LF-10). Con K < 2, A2, EE_A2 y ψ2 quedan NaN; sin ajuste posible, todo NaN.
    Coordenadas no interpretables o inconsistentes: tabla vacía (sin λ no hay hora solar).
    """
    if variable not in COLUMNA:
        raise ValueError(f"variable de E4 desconocida: {variable!r}")
    U = ctx.umbrales
    info = ctx.info
    filas: list[dict] = []
    if not info.coordenadas_validas or info.coordenadas_inconsistentes or info.lon is None:
        return _tabla(filas, ESQUEMA_METRICAS_E4, "métricas E4")
    cal = _Calendario(ctx)
    for anio, b in _base_por_anio(extracto, variable, ctx.anios).items():
        for u in _unidades(b, _pares_vacios(0), cal):
            if u.filas.size == 0:
                continue
            L, y, p = b.L[u.filas], b.y[u.filas], b.p[u.filas]
            en_dia, anomalia = _anomalias_del_dia(L, y, p, _c("E4_DIA_MIN_VALORES"))
            minimo = U.f("E4_VALORES_HORA_PARTE" if u.nivel == Nivel.PARTE else "E4_VALORES_HORA_REGIMEN")
            Lv = L[en_dia]
            t0 = numerico.hora_solar(Lv, info.lon) if Lv.size else np.zeros(0)
            hora = pd.DatetimeIndex(Lv).hour.to_numpy()
            d = _ajuste_diurno(t0, anomalia[en_dia], hora, minimo, U)
            aj = d.ajuste
            dos = aj is not None and aj.K >= 2
            filas.append({"codigo": info.codigo, "anio": anio, "nivel": str(u.nivel), "unidad": u.id,
                          "regimen": u.regimen, "variable": variable, "paso_h": u.paso, "n_h": d.n_h,
                          "hueco_max_h": d.hueco, "K": d.K,
                          "A1": aj.amplitudes[0] if aj else np.nan, "EE_A1": aj.ee_amplitudes[0] if aj else np.nan,
                          "phi1": aj.phi1 if aj else np.nan,
                          "A2": aj.amplitudes[1] if dos else np.nan, "EE_A2": aj.ee_amplitudes[1] if dos else np.nan,
                          "psi2": aj.psi2 if dos else np.nan})
    return _tabla(filas, ESQUEMA_METRICAS_E4, "métricas E4")


def _estado_e4p(fila: Mapping, desfases_h: Mapping[str, int], U) -> tuple[dict[str, Estado], dict[str, str | None]]:
    hs = list(desfases_h)

    def sin(motivo) -> tuple[dict, dict]:
        return {h: Estado.SIN_INFORMACION for h in hs}, {h: str(motivo) for h in hs}

    if not _nulo(fila["paso_h"]) and int(fila["paso_h"]) == _c("E4_PASO_6H"):
        return sin(MotivoSinInfo.PASO)
    if int(fila["n_h"]) < U.f("E4P_NH_MIN"):
        return sin(MotivoSinInfo.MINIMOS)
    if int(fila["hueco_max_h"]) > U.f("E4_HUECO_MAX_H"):
        return sin(MotivoSinInfo.HUECO)
    a2, ee2, psi2 = fila["A2"], fila["EE_A2"], fila["psi2"]
    if (_nulo(a2) or _nulo(ee2) or _nulo(psi2) or a2 < U.f("E4P_A2_MIN_HPA") or not ee2 > 0
            or a2 / ee2 < U.a("E4P_A2_EE")):
        return sin(MotivoSinInfo.AMPLITUD)
    est, mot = {}, {}
    for h, c in desfases_h.items():
        delta = numerico.distancia_circular(float(psi2) - c, U.f("E4P_S2_FASE_H"), _PERIODO_S2_H)
        if delta <= U.a("E4P_COMPAT"):
            est[h], mot[h] = Estado.COMPATIBLE, None
        elif delta >= U.a("E4P_INCOMPAT"):
            est[h], mot[h] = Estado.INCOMPATIBLE, None
        else:
            est[h], mot[h] = Estado.DUDOSA, "entre_umbrales"
    return est, mot


def e4p(metricas_e4_qfe: pd.DataFrame, ctx: ContextoEstacion) -> ResultadoLinea:
    """E4p (§4.4): sin información si n_h < 8, hueco circular > 3 h, A2 < 0,15 hPa o A2/EE < E4P_A2_EE
    (con p = 6 siempre); δ = distancia circular (período 12 h) entre ψ2 − c_H(R) y 9,75 h; compatible si
    δ ≤ E4P_COMPAT, incompatible si δ ≥ E4P_INCOMPAT; anual: incompatible en algún año-régimen,
    compatible en todos los evaluables (≥ 1). Las partes cuentan para la cobertura (§5.1, paso 8).

    Filas por parte y año-régimen (regla «unica») y anuales (LF-11). Sin reloj anómalo. Coordenadas no
    interpretables o inconsistentes: todo sin información (motivo «coordenadas»).
    """
    U = ctx.umbrales
    info = ctx.info
    cal = _Calendario(ctx)
    marcos = []
    if not info.coordenadas_validas or info.coordenadas_inconsistentes or info.lon is None:
        for anio in ctx.anios:
            for reg in cal.regimenes_con_datos(anio):
                marcos.append(_filas(ctx, anio, Linea.E4P, Nivel.REGIMEN, reg, _todas(ctx, Estado.SIN_INFORMACION),
                                     str(MotivoSinInfo.COORDENADAS), regla=Regla.UNICA))
    else:
        m = metricas_e4_qfe
        if m is not None and len(m):
            m = m[m["variable"] == "QFE"]
        for anio in ctx.anios:
            del_anio = m[m["anio"] == anio] if m is not None and len(m) else tabla_vacia(ESQUEMA_METRICAS_E4)
            vistos = set()
            for _, fila in del_anio.iterrows():
                est, mot = _estado_e4p(fila, cal.desfases(int(anio), fila["regimen"]), U)
                marcos.append(_filas(ctx, int(anio), Linea.E4P, Nivel(fila["nivel"]), fila["unidad"], est, mot,
                                     regla=Regla.UNICA))
                if fila["nivel"] == str(Nivel.REGIMEN):
                    vistos.add(fila["unidad"])
            for reg in cal.regimenes_con_datos(anio):
                if reg not in vistos:
                    marcos.append(_filas(ctx, anio, Linea.E4P, Nivel.REGIMEN, reg,
                                         _todas(ctx, Estado.SIN_INFORMACION), str(MotivoSinInfo.MINIMOS),
                                         regla=Regla.UNICA))
    por_unidad = _unir_estados(marcos)
    anual = _anual_por_regimenes(ctx, por_unidad, Linea.E4P, Regla.UNICA)
    return ResultadoLinea(linea=Linea.E4P, estados=_unir_estados([anual, por_unidad]),
                          metricas=metricas_e4_qfe)


# ---------------------------------------------------------------------------------------------
# E6 (§4.6)
# ---------------------------------------------------------------------------------------------
def normalizar_nombre_isd(nombre: str) -> str:
    """Mayúsculas, sin tildes (NFKD), sin puntuación, espacios simples y sin las palabras de §4.6.

    La puntuación se reemplaza por un espacio (LF-14): «SANTIAGO/PUDAHUEL» → «SANTIAGO PUDAHUEL» y
    «Ad.» → «AD», que se quita.
    """
    if nombre is None:
        return ""
    texto = unicodedata.normalize("NFKD", str(nombre))
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch)).upper()
    texto = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in texto)
    quitar = set(_c("E6_PALABRAS"))
    return " ".join(p for p in texto.split() if p not in quitar)


def _indicativo(v) -> str | None:
    if _nulo(v):
        return None
    texto = str(v).strip().upper()
    return texto or None


def cruce_isd(catalogo_dmc: pd.DataFrame, estaciones_isd: pd.DataFrame, *, umbrales) -> pd.DataFrame:
    """Cruce fijado antes de C4: indicativo OMM u OACI; si falta, ISD a ≤ 2 km con el mismo nombre normalizado.

    ``catalogo_dmc``: codigo, nombre, lat, lon, omm, oaci. ``estaciones_isd``: id_isd, nombre, lat, lon,
    omm, oaci. ``umbrales`` da E6_DIST_KM (argumento nuevo, sólo por palabra clave: la firma del esqueleto
    no traía de dónde leer el umbral). «Si falta» se lee como «si el catálogo no trae OMM ni OACI» (R-50:
    E6 está inactiva). Con varias candidatas gana la de menor id_isd. Salida: codigo, id_isd, criterio
    («omm», «oaci» o «nombre») y distancia_km; las estaciones sin cruce no aparecen.
    """
    filas = []
    isd = estaciones_isd.copy()
    isd["_omm"] = [_indicativo(v) for v in isd["omm"]]
    isd["_oaci"] = [_indicativo(v) for v in isd["oaci"]]
    isd["_nombre"] = [normalizar_nombre_isd(v) for v in isd["nombre"]]
    isd = isd.sort_values("id_isd", kind="stable")
    tope = float(umbrales.f("E6_DIST_KM"))
    for _, est in catalogo_dmc.sort_values("codigo", kind="stable").iterrows():
        candidatas, criterio = None, None
        omm, oaci = _indicativo(est.get("omm")), _indicativo(est.get("oaci"))
        if omm is not None and (isd["_omm"] == omm).any():
            candidatas, criterio = isd[isd["_omm"] == omm], "omm"
        elif oaci is not None and (isd["_oaci"] == oaci).any():
            candidatas, criterio = isd[isd["_oaci"] == oaci], "oaci"
        elif omm is None and oaci is None and not _nulo(est.get("lat")) and not _nulo(est.get("lon")):
            mismas = isd[isd["_nombre"] == normalizar_nombre_isd(est.get("nombre"))]
            if len(mismas):
                d = numerico.distancia_km(float(est["lat"]), float(est["lon"]), mismas["lat"].to_numpy(float),
                                          mismas["lon"].to_numpy(float))
                candidatas, criterio = mismas[d <= tope], "nombre"
        if candidatas is None or not len(candidatas):
            continue
        elegida = candidatas.iloc[0]
        distancia = np.nan
        if not any(_nulo(v) for v in (est.get("lat"), est.get("lon"), elegida["lat"], elegida["lon"])):
            distancia = float(numerico.distancia_km(float(est["lat"]), float(est["lon"]),
                                                    np.array([float(elegida["lat"])]),
                                                    np.array([float(elegida["lon"])]))[0])
        filas.append({"codigo": str(est["codigo"]), "id_isd": str(elegida["id_isd"]), "criterio": criterio,
                      "distancia_km": distancia})
    return pd.DataFrame(filas, columns=list(COLUMNAS_CRUCE)).astype(
        {"codigo": "string", "id_isd": "string", "criterio": "string", "distancia_km": "float64"})


@dataclass
class _CuentasE6:
    n12: int                 # coincidencias evaluadas con FM-12
    i12: float               # I12 (0 sin coincidencias)
    n15: int
    i15: float
    c: np.ndarray            # desfase del candidato en cada etiqueta de la unidad (NaN si no está definido)


@dataclass
class _CoincidenciasE6:
    """Por etiqueta: hay FM-12, coincide FM-12, hay FM-15, coincide FM-15; y el desfase del candidato."""
    hay12: np.ndarray
    ok12: np.ndarray
    hay15: np.ndarray
    ok15: np.ndarray
    c: np.ndarray

    def en(self, sel: np.ndarray) -> _CuentasE6:
        n12, n15 = int(self.hay12[sel].sum()), int(self.hay15[sel].sum())
        return _CuentasE6(n12, float(self.ok12[sel].sum() / n12) if n12 else 0.0,
                          n15, float(self.ok15[sel].sum() / n15) if n15 else 0.0, self.c[sel])


def _partes_por_hora(isd: pd.DataFrame, codigo: str, tolerancia_min: float) -> pd.DataFrame:
    """Un parte por hora en punto (±tolerancia): FM-12 antes que FM-15; luego el más cercano y el primero."""
    d = isd
    if "codigo" in d.columns:
        d = d[d["codigo"].astype("string") == codigo]
    d = d[d["tipo_parte"].isin(_PARTES_E6) & np.isfinite(d["tmp"].to_numpy(dtype=float, na_value=np.nan))]
    if not len(d):
        return pd.DataFrame({"hora": pd.Series(dtype="datetime64[ns]"), "tipo": pd.Series(dtype=object),
                             "tmp": pd.Series(dtype=float)})
    u = pd.DatetimeIndex(d["u"].to_numpy(dtype="datetime64[ns]"))
    hora = u.round("h")
    desvio = np.abs((u - hora) / pd.Timedelta(minutes=1))
    t = pd.DataFrame({"hora": hora.to_numpy(), "tipo": d["tipo_parte"].to_numpy(object),
                      "tmp": d["tmp"].to_numpy(float), "prioridad": [_PARTES_E6.index(x) for x in d["tipo_parte"]],
                      "desvio": desvio, "u": u.to_numpy()})
    t = t[t["desvio"] <= tolerancia_min]
    t = t.sort_values(["hora", "prioridad", "desvio", "u"], kind="stable").drop_duplicates("hora", keep="first")
    return t[["hora", "tipo", "tmp"]].reset_index(drop=True)


def e6(extracto: pd.DataFrame, isd: pd.DataFrame | None, ctx: ContextoEstacion) -> ResultadoLinea:
    """E6 (§4.6), sólo si está activa: I12_c e I15_c por mes y año para c ∈ [−9, 9] y las C(Z) de P;
    FM-12 decide; FM-15 sólo separa de H′ a ≥ 2 h (R-28); reloj anómalo si un c fuera de P es compatible.
    Inactiva → sin filas (equivale a sin información).

    Por unidad (mes, con ≥ E6_MIN_MES coincidencias; año, con ≥ E6_MIN_ANIO): compatible(H) con FM-12
    si I12_H ≥ a y I12_H ≥ b·I12_H′ para toda H′ no fusionada con H (E6_I12 = (a, b)); con FM-15 si
    I15_H ≥ a′ e I15_H ≥ b′·I15_H′ para toda H′ a ≥ 2 h (E6_I15); incompatible(H) si otra H′ de P es
    compatible por FM-12, o sólo por FM-15 y H está a ≥ 2 h de ella. Lecturas en LF-13. Estado anual por
    estados.anual_por_partes (la fila del año decide; ≥ 2 meses incompatibles también).
    """
    if Linea.E6 not in ctx.lineas_activas:
        return ResultadoLinea(linea=Linea.E6, estados=tabla_vacia(ESQUEMA_ESTADOS))
    U = ctx.umbrales
    info = ctx.info
    hs = [h.id for h in info.P]
    t = extracto[["L", "ts", "especial"]].copy()
    t = t[np.isfinite(t["ts"].to_numpy(dtype=float, na_value=np.nan)) & ~t["especial"].to_numpy(bool)]
    L = t["L"].to_numpy(dtype="datetime64[ns]")
    idx = pd.DatetimeIndex(L)
    anios_l, meses_l = idx.year.to_numpy(), idx.month.to_numpy()
    en_anios = np.isin(anios_l, list(ctx.anios))
    L, ts, anios_l, meses_l = L[en_anios], t["ts"].to_numpy(float)[en_anios], anios_l[en_anios], meses_l[en_anios]
    partes = _partes_por_hora(isd, info.codigo, U.f("E6_TOL_MIN")) if isd is not None and len(isd) else None
    marcos = []
    if partes is None or not len(partes):
        for anio in ctx.anios:
            for mes in sorted(set(meses_l[anios_l == anio])):
                marcos.append(_filas(ctx, int(anio), Linea.E6, Nivel.MES, f"{int(anio):04d}-{int(mes):02d}",
                                     _todas(ctx, Estado.SIN_INFORMACION), str(MotivoSinInfo.SIN_EVIDENCIA),
                                     regla=Regla.UNICA))
            marcos.append(_filas(ctx, int(anio), Linea.E6, Nivel.ANIO, f"{int(anio):04d}",
                                 _todas(ctx, Estado.SIN_INFORMACION), str(MotivoSinInfo.SIN_EVIDENCIA),
                                 regla=Regla.UNICA))
        estados_ = _unir_estados(marcos)
        return ResultadoLinea(linea=Linea.E6, estados=estados.anual_por_partes(
            estados_, linea=Linea.E6, min_partes=_c("ANUAL_MIN_PARTES")) if len(estados_) else estados_)
    # candidatos: F(c) de la ventana de E6 y las C(Z) de P, con su desfase en cada etiqueta
    lo, hi = _c("E6_VENTANA")
    candidatos: dict[str, np.ndarray] = {Hipotesis("F", c, None).id: np.full(L.size, float(c))
                                         for c in range(lo, hi + 1)}
    for h in info.P:
        if h.tipo == "C":
            candidatos[h.id] = np.array([np.nan if (v := tablas.desfase_en_etiqueta(h, x, ctx.tablas)) is None
                                         else float(v) for x in pd.DatetimeIndex(L).to_pydatetime()])
    horas_isd = partes["hora"].to_numpy(dtype="datetime64[ns]")
    tipo_isd = partes["tipo"].to_numpy(object)
    tmp_isd = partes["tmp"].to_numpy(float)
    tol12 = _c("E6_TOL_FM12_C")
    coincide: dict[str, _CoincidenciasE6] = {}
    for cid, c in candidatos.items():
        definido = np.isfinite(c)
        u = L - _horas_td(np.where(definido, c, 0).astype(np.int64))
        k = np.searchsorted(horas_isd, u)
        kk = np.minimum(k, max(horas_isd.size - 1, 0))
        hay = definido & (k < horas_isd.size) & (horas_isd[kk] == u)
        es12 = hay & (tipo_isd[kk] == _PARTES_E6[0])
        es15 = hay & (tipo_isd[kk] == _PARTES_E6[1])
        coincide[cid] = _CoincidenciasE6(es12, es12 & (np.abs(ts - tmp_isd[kk]) <= tol12),
                                         es15, es15 & (np.round(ts) == tmp_isd[kk]), c)
    unidades = [(int(a), Nivel.MES, f"{int(a):04d}-{int(m):02d}", (anios_l == a) & (meses_l == m), U.f("E6_MIN_MES"))
                for a, m in sorted(set(zip(anios_l.tolist(), meses_l.tolist())))]
    unidades += [(int(a), Nivel.ANIO, f"{int(a):04d}", anios_l == a, U.f("E6_MIN_ANIO")) for a in sorted(set(anios_l))]
    a12, b12 = U.a("E6_I12")
    a15, b15 = U.a("E6_I15")
    dist15 = _c("E6_FM15_DIST")
    for anio, nivel, unidad, sel, minimo in unidades:
        cuentas = {cid: co.en(sel) for cid, co in coincide.items()}
        ids = list(cuentas)

        def distinto(a, b) -> bool:
            ca, cb = cuentas[a].c, cuentas[b].c
            ok = np.isfinite(ca) & np.isfinite(cb)
            return bool(np.any(ca[ok] != cb[ok]))

        def dist_min(a, b) -> float:
            ca, cb = cuentas[a].c, cuentas[b].c
            ok = np.isfinite(ca) & np.isfinite(cb)
            return float(np.min(np.abs(ca[ok] - cb[ok]))) if ok.any() else 0.0

        comp12 = {a: cuentas[a].n12 >= minimo and cuentas[a].i12 >= a12
                  and all(cuentas[a].i12 >= b12 * cuentas[b].i12 for b in ids if b != a and distinto(a, b))
                  for a in ids}
        comp15 = {a: cuentas[a].n15 >= minimo and cuentas[a].i15 >= a15
                  and all(cuentas[a].i15 >= b15 * cuentas[b].i15 for b in ids if b != a and dist_min(a, b) >= dist15)
                  for a in ids}
        est_h, mot_h = {}, {}
        for h in hs:
            inc = any((comp12[o] and distinto(h, o)) or (comp15[o] and not comp12[o] and dist_min(h, o) >= dist15)
                      for o in hs if o != h)
            if inc:
                est_h[h], mot_h[h] = Estado.INCOMPATIBLE, None
            elif comp12[h] or comp15[h]:
                est_h[h], mot_h[h] = Estado.COMPATIBLE, "FM-12" if comp12[h] else "FM-15"
            else:
                pocas = cuentas[h].n12 < minimo and cuentas[h].n15 < minimo
                est_h[h] = Estado.SIN_INFORMACION
                mot_h[h] = str(MotivoSinInfo.MINIMOS) if pocas else _E6_NO_CONCLUYENTE
        fuera = [a for a in ids if a.startswith("F(") and not any(not distinto(a, h) for h in hs)]
        anomalo = any(comp12[a] or comp15[a] for a in fuera)
        marcos.append(_filas(ctx, anio, Linea.E6, nivel, unidad, est_h, mot_h, regla=Regla.UNICA, anomalo=anomalo))
    estados_ = _unir_estados(marcos)
    return ResultadoLinea(linea=Linea.E6, estados=estados.anual_por_partes(
        estados_, linea=Linea.E6, min_partes=_c("ANUAL_MIN_PARTES")) if len(estados_) else estados_)
