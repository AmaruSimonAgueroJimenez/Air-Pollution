"""Inferencia de diferencias entre motores (``DISENO_AMBIENTAL_V2.md`` §8, con la Enmienda 1, puntos 3 y 5, y su
Complemento, puntos 1, 2 y 6).

Todo sale de **sumas suficientes por bloque**: n, Σw, Σwo, Σwo² y, por motor, Σw(p − o) y Σw(p − o)². Una réplica
bootstrap es ``conteos @ sumas``, quitar un bloque es borrar una fila y el jackknife es un «deja uno fuera» de esas
filas, así que 1.999 réplicas, la segunda prueba y la prueba de influencia cuestan milisegundos. Las mismas sumas,
serializadas (``SumasBloques.a_dict``), son la evidencia que lee ``decision_v2``: no llevan predicciones. Módulo
puro.

**Pares y bloques.** Los pares son los comunes (§4) o los de la decisión (punto 11). El bloque de un par es el de la
inferencia del protocolo (``config_v2.json`` → ``inferencia_diferencias.bootstrap.unidad``): el bloque de 75 km de
su estación en LOSO-D y LBO-10 (punto 5: capta la dependencia de cuenca, no copia el conglomerado del pliegue), el
bloque en BLQ-75, la región en LRO y el cuatrienio en LPO, que es descriptivo. En los niveles agregados, el bloque
más frecuente entre sus horas (``metricas_v2``).

**Estadísticos.** ΔR², ΔRMSE y ΔNMB del motor A menos el B, sobre los mismos pares, más Δ|NMB| (cuál sesga menos).

**Ruido de la diferencia (punto 3; Complemento, punto 6).** En cada réplica r = 0, 1, 2 (``motor``, ``motor@r1``,
``motor@r2``) se calcula Δ_r con los mismos pares, nivel y ponderación. La estimación puntual es la media Δ̄ y el
ruido es el rango de los Δ_r; la condición es ``|Δ̄| > rango(Δ_r)``, que implica el mismo signo en las tres réplicas
y pasa por azar un 8,1 % de las veces, sea cual sea la correlación entre los motores. Las réplicas de un par son las
que tienen los dos motores; el ruido **exige las 3 réplicas comunes** (``REPLICAS_EXIGIDAS``): con menos, Δ̄ es la
media de las que haya (Δ_0 si hay una) y la condición queda «no evaluada». El apilado no tiene réplicas: su ruido es
el máximo del de sus bases (``bases_sin_replicas``), cada una frente al mismo rival (sin la base que es el rival).

**Bootstrap percentil (§8; puntos 3 y 5; Complemento, punto 2).** B = 1.999 réplicas (``REPLICAS``). Cada réplica
sortea con reemplazo tantos bloques como hay y recalcula las métricas de las tres réplicas de los dos motores con
**los mismos** bloques: Δ̄* es la media de los Δ*_r. Intervalo percentil (2,5 % y 97,5 %, con ``inverted_cdf``) y
``p = 2·mín(fracción de Δ̄* ≤ 0, fracción ≥ 0)``. La semilla ratificada es ``[42, 2000, p]`` (no cambia con B) con
p la posición del protocolo en ``protocolos.orden``: todas las comparaciones de un protocolo con los mismos bloques
usan la misma matriz de conteos (pareado), en las tres réplicas, los conjuntos de evaluación y las dos
ponderaciones.

**Segunda prueba (punto 5; Complemento, punto 1).** ΔR² = −ΔSSE/SST con un SST común, así que su signo es el de la
media ponderada de d = e_A² − e_B². Sobre los totales por bloque ``T_g = Σ_{i∈g} w_i·d̄_i`` (d̄_i, media de las
réplicas) y ``W_g = Σ_{i∈g} w_i``, con θ̂ = ΣT/ΣW (a favor de A si θ̂ < 0) y G los bloques con peso (W_g > 0):

* ``cambio_de_signo_salvaje`` (**la prueba que decide**): bootstrap salvaje por bloque con la nula impuesta
  (T*_g = ε_g·T_g), t = θ̂/√CV1 con CV1 = G/(G − 1)·Σ_g (T_g − θ̂·W_g)²/(Σ_g W_g)², y p bilateral = fracción de los
  vectores de signos con |t*| ≥ |t|. Con G < 12, pesos de Webb (±√1,5, ±1, ±√0,5) y 9.999 sorteos; con
  12 ≤ G ≤ 16, Rademacher con la **enumeración completa** de los 2^G vectores (exacta, no sortea); con G > 16,
  Rademacher con 9.999 sorteos. La semilla es ``[42, 3000, p]``;
* ``jackknife_cv3`` (**sólo informa**): CV3 = (G − 1)/G · Σ_g (θ̂_(−g) − θ̄)², t = θ̂/√CV3 con t de G − 1 gl,
  bilateral. En simulación, con la concentración real del peso, el CV3 rechaza por encima de lo nominal y el
  cambio de signo mantiene el tamaño (motivo del Complemento).

La segunda prueba vale para ΔR² y ΔRMSE (las dos dependen de las SSE); en ΔNMB y Δ|NMB| no aplica.

**Regla de superioridad descriptiva (§8 y punto 5)** (``aplicar_regla``): A supera a B si el IC del 95 % excluye
0 en la dirección buena (ΔR² > 0; ΔRMSE y Δ|NMB| < 0), la segunda prueba (el cambio de signo) coincide (al 5 %, a
favor de A) y |Δ̄| supera el ruido de la diferencia. LPO es descriptivo: no declara. **Influencia**: en LRO y
BLQ-75 la superioridad debe sobrevivir a quitar el bloque más influyente (la RM y E004N083); si no, es «no
robusta» (``comparar``). Se informan G, el G efectivo ``(ΣW_g)²/ΣW_g²`` y Δ̄ sin cada bloque
(``delta_sin_cada_bloque``).

**Holm (punto 11).** ``holm`` aplica el procedimiento escalonado a una familia de p (los 4 candidatos de la
decisión): el j-ésimo por p creciente se declara si ``p ≤ α/(m − j + 1)`` y se declararon los anteriores. Con el p
bootstrap equivale a que su IC percentil al nivel escalonado excluya 0: con B = 1.999 ningún ``(α_j/2)·B`` es
entero, así que no hay empates en el borde (Complemento, punto 2).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

REPLICAS = 1999                          # Complemento, punto 2 (antes 2.000): ningún umbral de Holm empata
REPLICAS_ANTES_DEL_COMPLEMENTO = 2000
NIVEL = 0.95
METODO_CUANTIL = "inverted_cdf"          # percentil sin interpolar: coincide con el p bootstrap (Holm, punto 11)
ESTADISTICOS = ("delta_r2", "delta_rmse", "delta_nmb", "delta_abs_nmb")
CON_SEGUNDA_PRUEBA = ("delta_r2", "delta_rmse")
SEP_REPLICA = "@r"
REPLICAS_DEL_RUIDO = (0, 1, 2)           # ruido.valores (ratificado): réplicas 0-2
REPLICAS_EXIGIDAS = len(REPLICAS_DEL_RUIDO)   # ruido.replicas_exigidas_en_la_decision (Complemento, punto 6)
SEMILLA_BASE = 42
SEMILLA_BOOTSTRAP = 2000                 # [42, 2000, p] (ratificada; no cambia con B = 1.999)
SEMILLA_SALVAJE = 3000                   # [42, 3000, p] (Complemento, punto 1)
PRUEBA_QUE_DECIDE = "cambio_de_signo_salvaje"
REPLICAS_SALVAJE = 9999                  # sorteos con G < 12 (Webb) y con G > 16 (Rademacher)
G_MINIMO_RADEMACHER = 12                 # Webb si G < 12
G_MAXIMO_ENUMERACION = 16                # 12 ≤ G ≤ 16: los 2^G vectores de signos de Rademacher, sin sortear
ENUMERACION_COMPLETA = "enumeracion_completa"
PESOS_WEBB = np.array([-np.sqrt(1.5), -1.0, -np.sqrt(0.5), np.sqrt(0.5), 1.0, np.sqrt(1.5)])
NIVEL_SEGUNDA_PRUEBA = 0.05              # regla descriptiva; en la decisión manda Holm (decision_v2)


def semilla_bootstrap(posicion_protocolo: int) -> list[int]:
    """Semilla del bootstrap percentil (ratificada): ``[42, 2000, p]``, también con B = 1.999 réplicas."""
    return [SEMILLA_BASE, SEMILLA_BOOTSTRAP, int(posicion_protocolo)]


def semilla_salvaje(posicion_protocolo: int) -> list[int]:
    """Semilla del cambio de signo del bootstrap salvaje, la prueba que decide (Complemento, punto 1):
    ``[42, 3000, p]``. La enumeración completa (12 ≤ G ≤ 16) no sortea."""
    return [SEMILLA_BASE, SEMILLA_SALVAJE, int(posicion_protocolo)]


# ---------------------------------------------------------------------------
# Nombres de las réplicas
# ---------------------------------------------------------------------------
def nombre_replica(motor: str, r: int) -> str:
    """``motor`` en la réplica 0 y ``motor@r{r}`` en las demás (como ``correr_v2.Tarea.nombres``)."""
    return motor if int(r) == 0 else f"{motor}{SEP_REPLICA}{int(r)}"


def separar_replica(nombre: str) -> tuple[str, int]:
    """(motor, réplica) de un nombre de predicción."""
    if SEP_REPLICA in nombre:
        base, r = nombre.rsplit(SEP_REPLICA, 1)
        if r.isdigit():
            return base, int(r)
    return nombre, 0


def replicas_de(nombres: Sequence[str], motor: str) -> list[int]:
    """Réplicas presentes de ``motor`` entre ``nombres`` (la 0 es el propio ``motor``)."""
    presentes = set(nombres)
    return sorted({r for r in REPLICAS_DEL_RUIDO if nombre_replica(motor, r) in presentes}
                  | {separar_replica(n)[1] for n in presentes if separar_replica(n)[0] == motor})


def replicas_comunes(nombres: Sequence[str], a: str, b: str) -> list[int]:
    """Réplicas que tienen los dos motores: en ellas se calcula Δ_r con los mismos pares (punto 3)."""
    return sorted(set(replicas_de(nombres, a)) & set(replicas_de(nombres, b)))


# ---------------------------------------------------------------------------
# Sumas por bloque
# ---------------------------------------------------------------------------
@dataclass
class SumasBloques:
    """Sumas por bloque; ``motor`` → (Σw(p − o), Σw(p − o)²) por bloque. ``bloques`` son las etiquetas."""

    bloques: np.ndarray
    n: np.ndarray
    sw: np.ndarray
    swo: np.ndarray
    swoo: np.ndarray
    motor: dict

    @classmethod
    def desde_pares(cls, bloque, obs, predicciones: Mapping[str, np.ndarray], w=None) -> "SumasBloques":
        """Sumas de los pares dados, que deben ser todos finitos en todos los motores (pares comunes)."""
        o = np.asarray(obs, dtype="float64")
        w = np.ones_like(o) if w is None else np.asarray(w, dtype="float64")
        ok = np.isfinite(o) & np.isfinite(w)
        for p in predicciones.values():
            ok &= np.isfinite(np.asarray(p, dtype="float64"))
        if not ok.all():
            raise ValueError("el bootstrap recibe sólo pares comunes: hay valores no finitos")
        u, b = np.unique(np.asarray(bloque), return_inverse=True)
        b = b.ravel()
        nb = len(u)
        motor = {}
        for nombre, p in predicciones.items():
            e = np.asarray(p, dtype="float64") - o
            motor[nombre] = (np.bincount(b, weights=w * e, minlength=nb), np.bincount(b, weights=w * e * e, minlength=nb))
        return cls(u, np.bincount(b, minlength=nb).astype("float64"), np.bincount(b, weights=w, minlength=nb),
                   np.bincount(b, weights=w * o, minlength=nb), np.bincount(b, weights=w * o * o, minlength=nb), motor)

    # --- Serialización (la evidencia de la decisión) ---------------------------------------------------
    def a_dict(self) -> dict:
        """Forma JSON exacta (los float de Python conservan los float64): etiquetas como texto."""
        return {"bloques": [str(x) for x in self.bloques], "n": self.n.tolist(), "sw": self.sw.tolist(),
                "swo": self.swo.tolist(), "swoo": self.swoo.tolist(),
                "motores": {m: {"se": se.tolist(), "se2": se2.tolist()} for m, (se, se2) in sorted(self.motor.items())}}

    @classmethod
    def desde_dict(cls, d: Mapping) -> "SumasBloques":
        a = lambda k: np.asarray(d[k], dtype="float64")  # noqa: E731
        motor = {m: (np.asarray(v["se"], dtype="float64"), np.asarray(v["se2"], dtype="float64"))
                 for m, v in d["motores"].items()}
        s = cls(np.asarray([str(x) for x in d["bloques"]], dtype=str), a("n"), a("sw"), a("swo"), a("swoo"), motor)
        largos = {len(s.bloques), len(s.n), len(s.sw), len(s.swo), len(s.swoo)}
        largos |= {len(x) for v in motor.values() for x in v}
        if len(largos) != 1:
            raise ValueError("las sumas por bloque no tienen todas una entrada por bloque")
        return s

    # --- Selección ---------------------------------------------------------------------------------------
    def motores(self) -> list[str]:
        return list(self.motor)

    def seleccionar(self, motores: Sequence[str]) -> "SumasBloques":
        faltan = [m for m in motores if m not in self.motor]
        if faltan:
            raise KeyError(f"motores sin sumas: {faltan}")
        return SumasBloques(self.bloques, self.n, self.sw, self.swo, self.swoo, {m: self.motor[m] for m in motores})

    def quitar(self, bloques: Sequence) -> "SumasBloques":
        """Las sumas sin los bloques dados (por etiqueta): la prueba de influencia (punto 5)."""
        quita = np.isin(np.asarray(self.bloques).astype(str), [str(x) for x in bloques])
        k = ~quita
        return SumasBloques(self.bloques[k], self.n[k], self.sw[k], self.swo[k], self.swoo[k],
                            {m: (se[k], se2[k]) for m, (se, se2) in self.motor.items()})

    def tiene_bloque(self, bloque) -> bool:
        return str(bloque) in set(np.asarray(self.bloques).astype(str))

    @property
    def G(self) -> int:
        """Bloques con pares."""
        return int((self.n > 0).sum())

    @property
    def G_efectivo(self) -> float:
        """``(Σ W_g)² / Σ W_g²`` con W_g el peso total del bloque (punto 4)."""
        return n_efectivo(self.sw)


def n_efectivo(totales) -> float:
    t = np.asarray(totales, dtype="float64")
    t = t[np.isfinite(t) & (t > 0)]
    return float(t.sum() ** 2 / (t * t).sum()) if len(t) else float("nan")


def conteos_bootstrap(n_bloques: int, replicas: int, semilla) -> np.ndarray:
    """Matriz (réplicas × bloques) de veces que cada bloque entra en cada réplica (sorteo con reemplazo)."""
    rng = np.random.default_rng(semilla)
    idx = rng.integers(0, n_bloques, size=(int(replicas), int(n_bloques)))
    return np.stack([np.bincount(fila, minlength=n_bloques) for fila in idx]).astype("float64")


def _metricas(c: np.ndarray, s: SumasBloques, nombre: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(R², RMSE, NMB) de un motor para cada vector de conteos (filas de ``c``)."""
    se, se2 = s.motor[nombre]
    n, sw, swo, swoo = c @ s.n, c @ s.sw, c @ s.swo, c @ s.swoo
    sum_e, sse = c @ se, c @ se2
    with np.errstate(invalid="ignore", divide="ignore"):
        sst = swoo - swo * swo / sw
        r2 = np.where((n >= 3) & (sst > 1e-12 * np.maximum(swoo, 1e-300)), 1.0 - sse / sst, np.nan)
        rmse = np.sqrt(sse / sw)
        nmb = np.where(swo > 0, sum_e / swo, np.nan)
    return r2, rmse, nmb


def metricas_de(s: SumasBloques, nombre: str) -> dict:
    """R², RMSE y NMB de un motor con todos los bloques."""
    r2, rmse, nmb = _metricas(np.ones((1, len(s.bloques))), s, nombre)
    return {"r2": float(r2[0]), "rmse": float(rmse[0]), "nmb": float(nmb[0])}


def _valores(estadistico: str, ma: tuple, mb: tuple) -> np.ndarray:
    """Δ = A − B del estadístico a partir de las tuplas (R², RMSE, NMB) de los dos motores."""
    if estadistico == "delta_r2":
        return ma[0] - mb[0]
    if estadistico == "delta_rmse":
        return ma[1] - mb[1]
    if estadistico == "delta_nmb":
        return ma[2] - mb[2]
    if estadistico == "delta_abs_nmb":
        return np.abs(ma[2]) - np.abs(mb[2])
    raise ValueError(f"estadístico desconocido: {estadistico!r}")


class _Cache:
    """Métricas por (motor, conteos) para no repetir productos de matrices entre pares."""

    def __init__(self, s: SumasBloques, C: np.ndarray | None = None):
        self.s, self.C = s, C
        self.uno = np.ones((1, len(s.bloques)))
        self._d: dict = {}

    def punto(self, nombre: str) -> tuple:
        if (nombre, "p") not in self._d:
            self._d[(nombre, "p")] = tuple(float(x[0]) for x in _metricas(self.uno, self.s, nombre))
        return self._d[(nombre, "p")]

    def boot(self, nombre: str) -> tuple:
        if (nombre, "b") not in self._d:
            self._d[(nombre, "b")] = _metricas(self.C, self.s, nombre)
        return self._d[(nombre, "b")]


# ---------------------------------------------------------------------------
# Ruido de la diferencia (punto 3)
# ---------------------------------------------------------------------------
def rango(valores) -> float:
    """Máximo − mínimo de los valores finitos; NaN con menos de 2."""
    v = np.asarray([x for x in valores if x is not None and np.isfinite(x)], dtype="float64")
    return float(v.max() - v.min()) if len(v) >= 2 else float("nan")


def supera_ruido(delta_medio: float, ruido: float):
    """``|Δ̄| > ruido`` (``True``/``False``); ``None`` («no evaluada») si el ruido no está medido."""
    if ruido is None or not np.isfinite(ruido) or delta_medio is None or not np.isfinite(delta_medio):
        return None
    return bool(abs(delta_medio) > ruido)


def deltas_por_replica(s: SumasBloques, a: str, b: str, estadistico: str = "delta_r2", cache: _Cache | None = None) -> dict:
    """``{r: Δ_r}`` en las réplicas comunes de A y B, con todos los bloques."""
    cache = cache or _Cache(s)
    out = {}
    for r in replicas_comunes(s.motores(), a, b):
        out[r] = float(_valores(estadistico, np.asarray(cache.punto(nombre_replica(a, r))),
                                np.asarray(cache.punto(nombre_replica(b, r)))))
    return out


def replicas_completas(replicas) -> bool:
    """¿Están las 3 réplicas comunes (0, 1 y 2)? El ruido de la diferencia las exige (Complemento, punto 6)."""
    return set(REPLICAS_DEL_RUIDO) <= {int(r) for r in replicas}


def ruido_de_las_replicas(d: Mapping[int, float]) -> float:
    """Rango de los Δ_r si están las 3 réplicas comunes; NaN («no evaluada») con menos (Complemento, punto 6)."""
    return rango(d[r] for r in REPLICAS_DEL_RUIDO) if replicas_completas(d) else float("nan")


def ruido_del_par(s: SumasBloques, a: str, b: str, estadistico: str = "delta_r2",
                  bases_sin_replicas: Mapping[str, Sequence[str]] | None = None, cache: _Cache | None = None) -> dict:
    """Ruido de la diferencia A − B: el rango de los Δ_r si el par tiene las 3 réplicas comunes; si uno de los dos
    es un motor sin réplicas con bases declaradas (el apilado), el máximo del ruido de sus bases frente al mismo
    rival (cada una con sus 3 réplicas); si no, NaN («no evaluada»; con 2 réplicas, «replicas_incompletas»)."""
    cache = cache or _Cache(s)
    d = deltas_por_replica(s, a, b, estadistico, cache)
    if replicas_completas(d):
        return {"ruido": ruido_de_las_replicas(d), "origen": "replicas", "replicas": sorted(d)}
    bases = bases_sin_replicas or {}
    for lado, (x, rival) in (("a", (a, b)), ("b", (b, a))):
        if x in bases:
            ruidos = {}
            for base in bases[x]:
                if base == rival or base not in s.motor:
                    continue
                par = (base, rival) if lado == "a" else (rival, base)
                ruidos[base] = ruido_de_las_replicas(deltas_por_replica(s, *par, estadistico, cache))
            fin = [v for v in ruidos.values() if np.isfinite(v)]
            if fin:
                return {"ruido": float(max(fin)), "origen": "maximo_de_las_bases", "bases": ruidos}
    origen = "replicas_incompletas" if len(d) >= 2 else "sin_replicas"
    return {"ruido": float("nan"), "origen": origen, "replicas": sorted(d)}


# ---------------------------------------------------------------------------
# Bootstrap percentil pareado por bloques
# ---------------------------------------------------------------------------
def _percentiles(v: np.ndarray, nivel: float) -> tuple[float, float]:
    # redondeo: (1 − 0,95)/2 = 0,025000000000000022 en coma flotante, y con B = 2.000 réplicas ese error movería el
    # percentil sin interpolar a la estadística de orden siguiente (con B = 1.999 ningún umbral cae en un entero)
    a = round((1.0 - float(nivel)) / 2.0, 12)
    return (float(np.quantile(v, a, method=METODO_CUANTIL)), float(np.quantile(v, 1.0 - a, method=METODO_CUANTIL)))


def p_bootstrap(distribucion) -> float:
    """``2·mín(fracción ≤ 0, fracción ≥ 0)`` de las réplicas finitas (acotado a 1)."""
    d = np.asarray(distribucion, dtype="float64")
    d = d[np.isfinite(d)]
    if len(d) == 0:
        return float("nan")
    return float(min(1.0, 2.0 * min(np.mean(d <= 0), np.mean(d >= 0))))


def bootstrap_diferencias(s: SumasBloques, pares: Sequence[tuple[str, str]], replicas: int = REPLICAS, semilla=None,
                          nivel: float = NIVEL, *, estadisticos: Sequence[str] = ESTADISTICOS,
                          bases_sin_replicas: Mapping[str, Sequence[str]] | None = None,
                          conteos: np.ndarray | None = None) -> pd.DataFrame:
    """Para cada par (A, B) y estadístico: los Δ_r de las réplicas comunes, Δ̄, el ruido de la diferencia, el
    intervalo percentil y el p bootstrap de Δ̄* (los mismos bloques sorteados en todas las réplicas), el error
    estándar bootstrap, G y el G efectivo. ``conteos`` permite reutilizar una matriz ya sorteada."""
    if semilla is None and conteos is None:
        raise ValueError("el bootstrap necesita una semilla explícita (config: inferencia_diferencias.bootstrap.semilla)")
    nb = len(s.bloques)
    C = conteos if conteos is not None else conteos_bootstrap(nb, replicas, semilla)
    if C.shape[1] != nb:
        raise ValueError("la matriz de conteos no tiene una columna por bloque")
    cache = _Cache(s, C)
    filas = []
    for a, b in pares:
        R = replicas_comunes(s.motores(), a, b)
        if not R:
            raise KeyError(f"par sin réplicas comunes con sumas en el bootstrap: {a} frente a {b}")
        for est in estadisticos:
            d_r = {r: float(_valores(est, np.asarray(cache.punto(nombre_replica(a, r))),
                                     np.asarray(cache.punto(nombre_replica(b, r))))) for r in R}
            dist = np.mean([_valores(est, cache.boot(nombre_replica(a, r)), cache.boot(nombre_replica(b, r)))
                            for r in R], axis=0)
            fin = dist[np.isfinite(dist)]
            dbar = float(np.mean(list(d_r.values())))
            rd = ruido_del_par(s, a, b, est, bases_sin_replicas, cache)
            lo, hi = _percentiles(fin, nivel) if len(fin) else (np.nan, np.nan)
            fila = {"motor_a": a, "motor_b": b, "estadistico": est, "delta": dbar}
            for r in REPLICAS_DEL_RUIDO:
                fila[f"delta_r{r}"] = d_r.get(r, np.nan)
            fila.update({"replicas_del_par": len(R), "ruido": rd["ruido"], "origen_ruido": rd["origen"],
                         "supera_ruido": supera_ruido(dbar, rd["ruido"]), "ic_inf": lo, "ic_sup": hi,
                         "p_bootstrap": p_bootstrap(fin),
                         "ee_bootstrap": float(np.std(fin, ddof=1)) if len(fin) > 1 else np.nan,
                         "frac_menor_o_igual_0": float(np.mean(fin <= 0)) if len(fin) else np.nan,
                         "frac_mayor_o_igual_0": float(np.mean(fin >= 0)) if len(fin) else np.nan,
                         "replicas_validas": int(len(fin)), "replicas": int(C.shape[0]), "bloques": int(nb),
                         "G": s.G, "G_efectivo": s.G_efectivo, "nivel_intervalo": float(nivel)})
            filas.append(fila)
    return pd.DataFrame(filas)


def distribucion_delta(s: SumasBloques, a: str, b: str, C: np.ndarray, estadistico: str = "delta_r2") -> np.ndarray:
    """Δ̄* (media de los Δ*_r de las réplicas comunes con los mismos bloques sorteados) para cada fila de ``C``."""
    cache = _Cache(s, C)
    R = replicas_comunes(s.motores(), a, b)
    if not R:
        raise KeyError(f"par sin réplicas comunes: {a} frente a {b}")
    return np.mean([_valores(estadistico, cache.boot(nombre_replica(a, r)), cache.boot(nombre_replica(b, r)))
                    for r in R], axis=0)


def delta_medio(s: SumasBloques, a: str, b: str, estadistico: str = "delta_r2") -> float:
    """Δ̄ con todos los bloques (NaN si el par no tiene réplicas comunes)."""
    d = deltas_por_replica(s, a, b, estadistico)
    return float(np.mean(list(d.values()))) if d else float("nan")


def delta_sin_cada_bloque(s: SumasBloques, a: str, b: str, estadistico: str = "delta_r2") -> pd.DataFrame:
    """Δ̄ sin cada bloque (punto 5, «Informes»), con el peso y los pares de cada bloque."""
    G = len(s.bloques)
    C = np.ones((G, G)) - np.eye(G)
    sin = distribucion_delta(s, a, b, C, estadistico) if G else np.zeros(0)
    total = delta_medio(s, a, b, estadistico)
    peso = s.sw / s.sw.sum() if s.sw.sum() > 0 else np.full(G, np.nan)
    return pd.DataFrame({"bloque": [str(x) for x in s.bloques], "pares": s.n.astype("int64"),
                         "fraccion_del_peso": peso, "delta_sin_bloque": sin, "cambio": sin - total})


# ---------------------------------------------------------------------------
# Segunda prueba (punto 5)
# ---------------------------------------------------------------------------
def totales_por_bloque(s: SumasBloques, a: str, b: str) -> tuple[np.ndarray, np.ndarray]:
    """``T_g = Σ w·d̄`` con d̄ = media de las réplicas comunes de e_A² − e_B², y ``W_g = Σ w`` por bloque."""
    R = replicas_comunes(s.motores(), a, b)
    if not R:
        raise KeyError(f"par sin réplicas comunes: {a} frente a {b}")
    T = np.mean([s.motor[nombre_replica(a, r)][1] - s.motor[nombre_replica(b, r)][1] for r in R], axis=0)
    return T, s.sw.copy()


def jackknife_cv3(T, W) -> dict:
    """Jackknife por bloque de θ̂ = ΣT/ΣW: CV3 = (G − 1)/G · Σ_g (θ̂_(−g) − θ̄)², t = θ̂/√CV3 y p bilateral con t
    de G − 1 gl. Sólo cuentan los bloques con peso. θ̂ = 0 con varianza 0 da p = 1. Desde el Complemento (punto
    1) sólo informa: la prueba que decide es ``cambio_de_signo_salvaje``."""
    from scipy import stats

    T, W = np.asarray(T, dtype="float64"), np.asarray(W, dtype="float64")
    k = W > 0
    T, W = T[k], W[k]
    G = int(len(T))
    vacio = {"theta": float("nan"), "ee": float("nan"), "t": float("nan"), "gl": max(G - 1, 0), "p": float("nan"),
             "G": G, "theta_sin_bloque": [float(x) for x in np.full(G, np.nan)]}
    if G < 2:
        return vacio
    ST, SW = float(T.sum()), float(W.sum())
    theta = ST / SW
    loo = (ST - T) / (SW - W)
    tbar = float(loo.mean())
    var = (G - 1) / G * float(((loo - tbar) ** 2).sum())
    ee = float(np.sqrt(var))
    if ee > 0:
        t = theta / ee
        p = float(2.0 * stats.t.sf(abs(t), G - 1))
    elif theta == 0:
        t, p = 0.0, 1.0
    else:
        t, p = float(np.sign(theta) * np.inf), 0.0
    return {"theta": theta, "ee": ee, "t": float(t), "gl": G - 1, "p": p, "G": G,
            "theta_sin_bloque": [float(x) for x in loo]}


def _t_cv1(Tm: np.ndarray, W: np.ndarray) -> np.ndarray:
    """t de θ̂ = ΣT/ΣW con la varianza por conglomerado CV1 (G/(G − 1)), para cada fila de ``Tm``."""
    G = Tm.shape[-1]
    SW = W.sum()
    th = Tm.sum(axis=-1) / SW
    u = Tm - th[..., None] * W
    v = G / (G - 1) * (u * u).sum(axis=-1) / (SW * SW)
    with np.errstate(invalid="ignore", divide="ignore"):
        return th / np.sqrt(v)


def _semilla_json(semilla):
    """La semilla como la registra la traza (lista de enteros o entero)."""
    if isinstance(semilla, (list, tuple, np.ndarray)):
        return [int(x) for x in semilla]
    return int(semilla)


def esquema_salvaje(G: int, sorteos: int = REPLICAS_SALVAJE) -> dict:
    """Pesos y sorteos del cambio de signo según G (Complemento, punto 1): Webb y ``sorteos`` con G < 12;
    Rademacher con la enumeración completa de los 2^G vectores con 12 ≤ G ≤ 16; Rademacher y ``sorteos`` con G > 16."""
    G = int(G)
    if G < G_MINIMO_RADEMACHER:
        return {"distribucion": "webb", "sorteos": int(sorteos), "enumeracion_completa": False}
    if G <= G_MAXIMO_ENUMERACION:
        return {"distribucion": "rademacher", "sorteos": ENUMERACION_COMPLETA, "enumeracion_completa": True}
    return {"distribucion": "rademacher", "sorteos": int(sorteos), "enumeracion_completa": False}


def signos_rademacher_completos(G: int) -> np.ndarray:
    """Los 2^G vectores de signos ±1 (filas), en el orden binario de 0 a 2^G − 1."""
    G = int(G)
    if G > G_MAXIMO_ENUMERACION:
        raise ValueError(f"la enumeración completa es sólo hasta G = {G_MAXIMO_ENUMERACION}")
    bits = (np.arange(2 ** G, dtype=np.int64)[:, None] >> np.arange(G, dtype=np.int64)[None, :]) & 1
    return (2.0 * bits - 1.0).astype("float64")


def cambio_de_signo_salvaje(T, W, replicas: int = REPLICAS_SALVAJE, semilla=None) -> dict:
    """Prueba de cambio de signo del bootstrap salvaje por bloque (Complemento, punto 1), la segunda prueba que
    decide: nula impuesta (T*_g = ε_g·T_g), t = θ̂/√CV1 y p bilateral = fracción de los vectores de signos con
    |t*| ≥ |t|. Sólo cuentan los bloques con peso (W_g > 0): G. Con G < 12, pesos de Webb y ``replicas`` sorteos;
    con 12 ≤ G ≤ 16, Rademacher con la enumeración completa (exacta: no usa la semilla); con G > 16, Rademacher y
    ``replicas`` sorteos. Los sorteos exigen una semilla explícita (``semilla_salvaje``: ``[42, 3000, p]``)."""
    T, W = np.asarray(T, dtype="float64"), np.asarray(W, dtype="float64")
    k = W > 0
    T, W = T[k], W[k]
    G = int(len(T))
    esq = esquema_salvaje(G, replicas)
    base = {"G": G, "distribucion": esq["distribucion"], "sorteos": esq["sorteos"],
            "semilla": None if esq["enumeracion_completa"] or semilla is None else _semilla_json(semilla)}
    if not esq["enumeracion_completa"] and semilla is None:
        raise ValueError("el cambio de signo del bootstrap salvaje necesita una semilla explícita "
                         "(inferencia_diferencias.segunda_prueba.metodo: [42, 3000, p])")
    if G < 2:
        return {"p": float("nan"), "t": float("nan"), **base, "vectores": 0}
    if esq["enumeracion_completa"]:
        E = signos_rademacher_completos(G)
    else:
        rng = np.random.default_rng(semilla)
        E = rng.choice(PESOS_WEBB if esq["distribucion"] == "webb" else np.array([-1.0, 1.0]), size=(int(replicas), G))
    t0 = float(_t_cv1(T[None, :], W)[0])
    tb = _t_cv1(E * T[None, :], W)
    tb = tb[np.isfinite(tb)]
    if not np.isfinite(t0):
        p = 1.0 if np.allclose(T, 0) else float("nan")
    else:
        p = float(np.mean(np.abs(tb) >= abs(t0) - 1e-12 * max(1.0, abs(t0)))) if len(tb) else float("nan")
    return {"p": p, "t": t0, **base, "vectores": int(len(E))}


def segunda_prueba(s: SumasBloques, a: str, b: str, *, semilla_salvaje=None,
                   replicas_salvaje: int = REPLICAS_SALVAJE) -> dict:
    """Segunda prueba del punto 5 sobre los totales por bloque de w·(e_A² − e_B²), con d̄ la media de las réplicas
    comunes: decide el cambio de signo del bootstrap salvaje (``salvaje``; Complemento, punto 1) y el jackknife CV3
    sólo informa (``jackknife``). ``theta`` = θ̂ = ΣT/ΣW y ``a_favor_de_a``: θ̂ < 0 (A tiene menos SSE)."""
    T, W = totales_por_bloque(s, a, b)
    k = W > 0
    theta = float(T[k].sum() / W[k].sum()) if k.any() and W[k].sum() > 0 else float("nan")
    return {"prueba_que_decide": PRUEBA_QUE_DECIDE, "theta": theta,
            "a_favor_de_a": bool(np.isfinite(theta) and theta < 0),
            "salvaje": cambio_de_signo_salvaje(T, W, replicas_salvaje, semilla_salvaje),
            "jackknife": jackknife_cv3(T, W)}


def segunda_prueba_coincide(sp: Mapping | None, nivel: float = NIVEL_SEGUNDA_PRUEBA) -> bool | None:
    """¿La segunda prueba (el cambio de signo) declara a favor de A al ``nivel``? None si no se calculó."""
    if sp is None:
        return None
    p = sp["salvaje"]["p"]
    return bool(np.isfinite(p) and p <= nivel and sp["a_favor_de_a"])


# ---------------------------------------------------------------------------
# Holm (punto 11)
# ---------------------------------------------------------------------------
def holm(p: Mapping[str, float], alfa: float = 0.05, m: int | None = None) -> dict:
    """Procedimiento escalonado de Holm sobre una familia de ``m`` hipótesis (por omisión, las dadas). Las que no
    tienen p finito no se declaran y van al final (cuentan en ``m``). Devuelve, por nombre, su p, su rango, su
    nivel escalonado y si se declaró."""
    nombres = list(p)
    m = len(nombres) if m is None else int(m)
    if m < len(nombres):
        raise ValueError("m no puede ser menor que el número de hipótesis dadas")
    clave = {k: (float(p[k]) if p[k] is not None and np.isfinite(p[k]) else np.inf) for k in nombres}
    orden = sorted(nombres, key=lambda k: (clave[k], nombres.index(k)))
    out, seguir = {}, True
    for j, k in enumerate(orden):
        nivel = alfa / (m - j)
        declarada = bool(seguir and np.isfinite(clave[k]) and clave[k] <= nivel)
        seguir = declarada
        out[k] = {"p": float(clave[k]) if np.isfinite(clave[k]) else float("nan"), "rango": j + 1,
                  "alfa_holm": float(nivel), "declarada": declarada}
    return out


# ---------------------------------------------------------------------------
# Regla de superioridad descriptiva (§8 y punto 5) e influencia
# ---------------------------------------------------------------------------
def excluye_cero_a_favor(estadistico: str, ic_inf: float, ic_sup: float) -> bool:
    """¿El intervalo excluye 0 en la dirección en que A es mejor? ΔR² > 0; ΔRMSE y Δ|NMB| < 0. ΔNMB con signo
    no tiene una dirección buena y devuelve False."""
    if not (np.isfinite(ic_inf) and np.isfinite(ic_sup)):
        return False
    if estadistico == "delta_r2":
        return bool(ic_inf > 0)
    if estadistico in ("delta_rmse", "delta_abs_nmb"):
        return bool(ic_sup < 0)
    return False


def _conjuncion(valores) -> bool | None:
    """Y lógico con «no evaluada»: False si alguno es False; None si falta alguno; True si todos son True."""
    v = list(valores)
    if any(x is False for x in v):
        return False
    if any(x is None for x in v):
        return None
    return True


COLUMNAS_SEGUNDA_PRUEBA = ("segunda_prueba", "theta_segunda_prueba", "p_salvaje", "t_salvaje", "G_salvaje",
                           "distribucion_salvaje", "sorteos_salvaje", "p_jackknife", "t_jackknife", "gl_jackknife")


def aplicar_regla(tabla: pd.DataFrame, segunda: Mapping[tuple[str, str], dict] | None = None,
                  descriptivo: bool = False, nivel_segunda: float = NIVEL_SEGUNDA_PRUEBA) -> pd.DataFrame:
    """Agrega ``excluye_cero_a_favor``, la segunda prueba (el cambio de signo del bootstrap salvaje, que decide: su
    p, t, G, pesos y sorteos; θ̂; y, sólo como información, el jackknife CV3: p, t y gl), si la segunda prueba
    coincide a favor de A al nivel dado y ``a_supera_b`` = IC a favor ∧ segunda prueba (ΔR² y ΔRMSE) ∧ ruido. En un
    protocolo descriptivo (LPO), ``a_supera_b`` queda vacío."""
    t = tabla.copy()
    segunda = segunda or {}
    cols = {k: [] for k in ("excluye_cero_a_favor", *COLUMNAS_SEGUNDA_PRUEBA, "segunda_prueba_coincide", "a_supera_b")}
    for f in t.itertuples(index=False):
        e = excluye_cero_a_favor(f.estadistico, f.ic_inf, f.ic_sup)
        sp = segunda.get((f.motor_a, f.motor_b)) if f.estadistico in CON_SEGUNDA_PRUEBA else None
        jk, sv = ({}, {}) if sp is None else (sp["jackknife"], sp["salvaje"])
        coincide = segunda_prueba_coincide(sp, nivel_segunda)
        cols["excluye_cero_a_favor"].append(e)
        cols["segunda_prueba"].append("" if sp is None else sp["prueba_que_decide"])
        cols["theta_segunda_prueba"].append(np.nan if sp is None else sp["theta"])
        cols["p_salvaje"].append(sv.get("p", np.nan))
        cols["t_salvaje"].append(sv.get("t", np.nan))
        cols["G_salvaje"].append(sv.get("G", np.nan))
        cols["distribucion_salvaje"].append(sv.get("distribucion", ""))
        cols["sorteos_salvaje"].append(str(sv.get("sorteos", "")))
        cols["p_jackknife"].append(jk.get("p", np.nan))
        cols["t_jackknife"].append(jk.get("t", np.nan))
        cols["gl_jackknife"].append(jk.get("gl", np.nan))
        cols["segunda_prueba_coincide"].append(coincide)
        partes = [e, f.supera_ruido] + ([coincide] if f.estadistico in CON_SEGUNDA_PRUEBA else [])
        cols["a_supera_b"].append(None if descriptivo else _conjuncion(partes))
    for k, v in cols.items():
        t[k] = pd.Series(v, index=t.index, dtype=object if k in ("segunda_prueba_coincide", "a_supera_b") else None)
    t["regla"] = "descriptivo" if descriptivo else "superioridad_95"
    return t


def comparar(s: SumasBloques, pares: Sequence[tuple[str, str]], replicas: int = REPLICAS, semilla=None,
             nivel: float = NIVEL, *, bases_sin_replicas: Mapping[str, Sequence[str]] | None = None,
             bloque_influyente=None, semilla_salvaje=None, replicas_salvaje: int = REPLICAS_SALVAJE,
             descriptivo: bool = False, estadisticos: Sequence[str] = ESTADISTICOS) -> pd.DataFrame:
    """Tabla descriptiva completa de un protocolo, nivel, conjunto y ponderación: bootstrap con el ruido de la
    diferencia, segunda prueba (el cambio de signo del bootstrap salvaje, con ``semilla_salvaje`` = ``[42, 3000, p]``,
    obligatoria salvo con la enumeración completa), regla de superioridad y, con ``bloque_influyente``, la misma
    regla sin ese bloque (``robusta_sin_bloque``: True/False si A supera a B con todos los bloques; vacía si no la
    supera o si el bloque no tiene pares)."""
    def una(sumas):
        tb = bootstrap_diferencias(sumas, pares, replicas, semilla, nivel, estadisticos=estadisticos,
                                   bases_sin_replicas=bases_sin_replicas)
        seg = {(a, b): segunda_prueba(sumas, a, b, semilla_salvaje=semilla_salvaje, replicas_salvaje=replicas_salvaje)
               for a, b in dict.fromkeys(pares)} if any(e in CON_SEGUNDA_PRUEBA for e in estadisticos) else {}
        return aplicar_regla(tb, seg, descriptivo)

    t = una(s)
    t["bloque_influyente"] = "" if bloque_influyente is None else str(bloque_influyente)
    if bloque_influyente is not None and s.tiene_bloque(bloque_influyente) and len(s.bloques) > 2:
        t2 = una(s.quitar([bloque_influyente]))
        t["delta_sin_bloque_influyente"] = t2["delta"].to_numpy()
        # sólo se pregunta por la robustez de una superioridad declarada: si no la hay, queda vacía
        t["robusta_sin_bloque"] = pd.Series([(b is True) if a is True else None
                                             for a, b in zip(t["a_supera_b"], t2["a_supera_b"])], index=t.index, dtype=object)
    else:
        t["delta_sin_bloque_influyente"] = np.nan
        t["robusta_sin_bloque"] = pd.Series([None] * len(t), index=t.index, dtype=object)
    return t
