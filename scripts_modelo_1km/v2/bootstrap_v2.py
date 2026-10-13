"""Inferencia de diferencias entre motores (``DISENO_AMBIENTAL_V2.md`` §8): bootstrap pareado por bloques.

* **Estadísticos**: ΔR², ΔRMSE y ΔNMB del motor A menos el B, sobre **los mismos pares** (los comunes de
  ``metricas_v2.pares_comunes``). Se informa también Δ|NMB|, que es el que dice cuál sesga menos.
* **Bloques**: el grupo del pliegue externo de cada par: conglomerado en LOSO-D y LBO-10, bloque en BLQ-75,
  región en LRO y cuatrienio en LPO (``config_v2.json`` → ``inferencia_diferencias.bootstrap.unidad``). En los
  niveles agregados, el grupo de un agregado es el más frecuente entre sus horas (``metricas_v2``).
* **Pareado**: cada réplica sortea con reemplazo tantos bloques como hay y recalcula las métricas de los dos
  motores con **el mismo** sorteo; todas las comparaciones de un protocolo y nivel comparten los sorteos.
* **Réplicas**: 2.000 (contrato). Valores provisionales de la configuración: intervalo percentil (2,5 % y
  97,5 %); semilla ``[42, 2000, p]`` con p la posición del protocolo en ``protocolos.orden``.
* **Regla de superioridad** (§8): A supera a B sólo si el intervalo del 95 % excluye 0 en la dirección buena
  (ΔR² > 0, ΔRMSE < 0) **y** la diferencia supera el ruido de semillas medido. Provisional: el ruido de un motor
  es el rango (máximo − mínimo) de la métrica entre sus 3 semillas, y se exige ``|Δ| >`` el mayor de los dos.
  Sin ruido medido (protocolos o motores con una semilla), la segunda condición queda «no evaluada».

Implementación: sumas suficientes por bloque (n, Σw, Σwo, Σwo² y, por motor, Σw(p − o) y Σw(p − o)²); una réplica
es ``conteos @ sumas``, así que 2.000 réplicas cuestan milisegundos. Admite pesos (población). Módulo puro.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

REPLICAS = 2000
NIVEL = 0.95
ESTADISTICOS = ("delta_r2", "delta_rmse", "delta_nmb", "delta_abs_nmb")


def semilla_bootstrap(posicion_protocolo: int) -> list[int]:
    """Semilla provisional: ``[42, 2000, p]``."""
    return [42, REPLICAS, int(posicion_protocolo)]


@dataclass
class SumasBloques:
    """Sumas por bloque; ``motor`` → (Σw(p − o), Σw(p − o)²) por bloque."""

    bloques: np.ndarray
    n: np.ndarray
    sw: np.ndarray
    swo: np.ndarray
    swoo: np.ndarray
    motor: dict

    @classmethod
    def desde_pares(cls, bloque, obs, predicciones: Mapping[str, np.ndarray], w=None) -> "SumasBloques":
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


def bootstrap_diferencias(s: SumasBloques, pares: Sequence[tuple[str, str]], replicas: int = REPLICAS, semilla=None,
                          nivel: float = NIVEL) -> pd.DataFrame:
    """Δ = A − B de R², RMSE, NMB y |NMB| para cada par (A, B), con el intervalo percentil del bootstrap
    pareado por bloques, el error estándar bootstrap y la fracción de réplicas con Δ ≤ 0."""
    if semilla is None:
        raise ValueError("el bootstrap necesita una semilla explícita (config: inferencia_diferencias.bootstrap.semilla)")
    nb = len(s.bloques)
    completo = np.ones((1, nb))
    C = conteos_bootstrap(nb, replicas, semilla)
    a_inf, a_sup = (1.0 - nivel) / 2.0, 1.0 - (1.0 - nivel) / 2.0
    cache = {}

    def calc(nombre, c, clave):
        if (nombre, clave) not in cache:
            cache[(nombre, clave)] = _metricas(c, s, nombre)
        return cache[(nombre, clave)]

    filas = []
    for a, b in pares:
        for m in (a, b):
            if m not in s.motor:
                raise KeyError(f"motor sin sumas en el bootstrap: {m}")
        pa, pb = calc(a, completo, "todo"), calc(b, completo, "todo")
        ra, rb = calc(a, C, "boot"), calc(b, C, "boot")
        punto = {"delta_r2": pa[0][0] - pb[0][0], "delta_rmse": pa[1][0] - pb[1][0],
                 "delta_nmb": pa[2][0] - pb[2][0], "delta_abs_nmb": abs(pa[2][0]) - abs(pb[2][0])}
        dist = {"delta_r2": ra[0] - rb[0], "delta_rmse": ra[1] - rb[1], "delta_nmb": ra[2] - rb[2],
                "delta_abs_nmb": np.abs(ra[2]) - np.abs(rb[2])}
        for est in ESTADISTICOS:
            d = dist[est]
            fin = d[np.isfinite(d)]
            filas.append({"motor_a": a, "motor_b": b, "estadistico": est, "delta": float(punto[est]),
                          "ic_inf": float(np.quantile(fin, a_inf)) if len(fin) else np.nan,
                          "ic_sup": float(np.quantile(fin, a_sup)) if len(fin) else np.nan,
                          "ee_bootstrap": float(np.std(fin, ddof=1)) if len(fin) > 1 else np.nan,
                          "frac_menor_o_igual_0": float(np.mean(fin <= 0)) if len(fin) else np.nan,
                          "replicas_validas": int(len(fin)), "replicas": int(replicas), "bloques": int(nb),
                          "nivel_intervalo": float(nivel)})
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# Ruido de semillas y regla de superioridad
# ---------------------------------------------------------------------------
def ruido_semillas(valores) -> float:
    """Ruido de un motor: rango (máximo − mínimo) de la métrica entre sus semillas; NaN con menos de 2."""
    v = np.asarray([x for x in valores if x is not None and np.isfinite(x)], dtype="float64")
    return float(v.max() - v.min()) if len(v) >= 2 else float("nan")


def excluye_cero_a_favor(estadistico: str, ic_inf: float, ic_sup: float) -> bool:
    """¿El intervalo excluye 0 en la dirección en que A es mejor? ΔR² > 0; ΔRMSE y Δ|NMB| < 0. ΔNMB con signo
    no tiene una dirección buena y devuelve False."""
    if not (np.isfinite(ic_inf) and np.isfinite(ic_sup)):
        return False
    if estadistico == "delta_r2":
        return ic_inf > 0
    if estadistico in ("delta_rmse", "delta_abs_nmb"):
        return ic_sup < 0
    return False


def supera_ruido(delta: float, ruido_a: float, ruido_b: float):
    """``True``/``False`` si hay ruido medido para alguno de los dos motores; ``None`` («no evaluada») si no."""
    ruidos = [r for r in (ruido_a, ruido_b) if r is not None and np.isfinite(r)]
    if not ruidos:
        return None
    return bool(abs(delta) > max(ruidos))


def aplicar_regla(tabla: pd.DataFrame, ruido: Mapping[tuple[str, str], float] | None = None) -> pd.DataFrame:
    """Agrega a la tabla del bootstrap ``excluye_cero_a_favor``, ``supera_ruido`` y ``a_supera_b``. ``ruido`` es
    ``{(motor, estadístico): rango entre semillas}``, con el estadístico como ``r2``, ``rmse`` o ``abs_nmb``."""
    t = tabla.copy()
    ruido = ruido or {}
    exc, sup, gana = [], [], []
    for f in t.itertuples(index=False):
        e = excluye_cero_a_favor(f.estadistico, f.ic_inf, f.ic_sup)
        metrica = f.estadistico.replace("delta_", "")
        s = supera_ruido(f.delta, ruido.get((f.motor_a, metrica)), ruido.get((f.motor_b, metrica)))
        exc.append(e)
        sup.append(s)
        gana.append(bool(e and s) if s is not None else (None if e else False))
    t["excluye_cero_a_favor"] = exc
    t["supera_ruido"] = sup
    t["a_supera_b"] = gana
    return t
