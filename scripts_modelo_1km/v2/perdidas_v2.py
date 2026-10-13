"""Funciones de pérdida de la v2 (``DISENO_AMBIENTAL_V2.md`` §6, etapa 8) para LightGBM y XGBoost.

Cuatro variantes, con el mismo N, los mismos pliegues y la receta del eje A (§3) sin cambios; sólo cambian el
objetivo y el blanco (``config_v2.json`` → ``perdidas``):

==============  ============  =====================================================================
variante        blanco        objetivo
==============  ============  =====================================================================
l2_log_duan     log1p(y)      cuadrático; vuelve a escala original con la retransformación primaria (§5)
l2_original     y             cuadrático en escala original (media condicional directa)
huber           y             Huber con δ = 1,345 × MAD de los residuos de un ajuste cuadrático del
                              entrenamiento del pliegue
pinball         y             cuantílico, τ = 0,05, 0,5 y 0,95 (mediana e intervalo del 90 %)
==============  ============  =====================================================================

Convenciones que el contrato deja pendientes y que aquí se usan con su valor provisional de la configuración
(cada una se ratifica o se corrige por enmienda):

* **MAD**: el normalizado, ``1,4826 × mediana(|r − mediana(r)|)``, de modo que ``1,345 × MAD`` es la constante
  de Huber para un 95 % de eficiencia bajo normalidad (Huber, 1981).
* **Ajuste cuadrático**: el mismo motor con la variante ``l2_original`` y las mismas filas del pliegue; los
  residuos son los de esas filas (in-sample).
* **Huber en XGBoost**: XGBoost sólo trae ``reg:pseudohubererror``, que no es la Huber de LightGBM. Se usa un
  objetivo propio con el gradiente y la hessiana del Huber de LightGBM: gradiente ``recorte(ŷ − y, ±δ)`` y
  hessiana 1 en todas las filas (verificado contra ``objective="huber"`` de LightGBM 4.7.0 sin bagging: las
  predicciones coinciden a 1e-8). Con un objetivo propio XGBoost arranca en 0,5, así que ``base_score`` se fija
  en la media del blanco, que es el inicio de LightGBM para L2 y Huber (``boost_from_average``).
* **Cuantiles**: ``objective="quantile"`` (``alpha = τ``) en LightGBM y ``reg:quantileerror``
  (``quantile_alpha = τ``) en XGBoost; los dos parten del cuantil τ del blanco y renuevan las hojas con el
  cuantil de los residuos. Gradiente ``1 − τ`` si ŷ > y y ``−τ`` si no, hessiana 1.
* Con hessiana 1 en todas las variantes, ``min_child_weight = 50`` de XGBoost equivale a
  ``min_data_in_leaf = 50`` de LightGBM.
* Las predicciones en escala original (``l2_original``, ``huber`` y ``pinball``) se recortan en 0, como GWR y
  RK en la v1: el blanco es no negativo y el recorte sólo puede acercar la predicción a lo observado.

Este módulo es puro: no lee ni escribe archivos.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

VARIANTES = ("l2_log_duan", "l2_original", "huber", "pinball")
TAUS = (0.05, 0.5, 0.95)
FACTOR_HUBER = 1.345
CONSTANTE_MAD_NORMAL = 1.482602218505602          # 1 / Φ⁻¹(3/4)
BLANCO_LOG = "log1p"
BLANCO_ORIGINAL = "y"


# ---------------------------------------------------------------------------
# Pérdidas y gradientes (convención de LightGBM: r = ŷ − y)
# ---------------------------------------------------------------------------
def huber_perdida(pred, y, delta: float) -> np.ndarray:
    """Pérdida de Huber por fila: ½r² si |r| ≤ δ y δ(|r| − ½δ) si no, con r = ŷ − y."""
    r = np.asarray(pred, dtype="float64") - np.asarray(y, dtype="float64")
    a = np.abs(r)
    return np.where(a <= delta, 0.5 * r * r, delta * (a - 0.5 * delta))


def huber_gradiente(pred, y, delta: float) -> tuple[np.ndarray, np.ndarray]:
    """Gradiente y hessiana del Huber **tal como los calcula LightGBM**: ``recorte(ŷ − y, ±δ)`` y 1.

    La hessiana verdadera es 0 fuera de ±δ; LightGBM usa 1 en todas las filas para que el paso de Newton no
    divida por cero en las hojas con sólo residuos grandes. La v2 copia esa convención en XGBoost para que
    los dos motores optimicen lo mismo."""
    r = np.asarray(pred, dtype="float64") - np.asarray(y, dtype="float64")
    return np.clip(r, -float(delta), float(delta)), np.ones_like(r)


def pinball_perdida(y, q, tau: float) -> np.ndarray:
    """Pérdida cuantílica por fila: ρ_τ(u) = u·(τ − 1{u < 0}), con u = y − q."""
    u = np.asarray(y, dtype="float64") - np.asarray(q, dtype="float64")
    return u * (float(tau) - (u < 0))


def pinball_gradiente(pred, y, tau: float) -> tuple[np.ndarray, np.ndarray]:
    """Subgradiente de ρ_τ(y − ŷ) respecto de ŷ y hessiana constante, como el objetivo ``quantile`` de
    LightGBM: ``1 − τ`` si ŷ > y y ``−τ`` si ŷ ≤ y; hessiana 1."""
    p, yy = np.asarray(pred, dtype="float64"), np.asarray(y, dtype="float64")
    return np.where(p > yy, 1.0 - float(tau), -float(tau)), np.ones_like(p)


def mad(x, normalizada: bool = True) -> float:
    """Desviación absoluta mediana; ``normalizada`` la multiplica por 1,4826 (consistente con σ normal)."""
    x = np.asarray(x, dtype="float64")
    x = x[np.isfinite(x)]
    if x.size == 0:
        raise ValueError("MAD de un vector sin valores finitos")
    m = float(np.median(np.abs(x - np.median(x))))
    return m * CONSTANTE_MAD_NORMAL if normalizada else m


def delta_huber(residuos, factor: float = FACTOR_HUBER, normalizada: bool = True) -> float:
    """δ = factor × MAD(residuos). Un MAD nulo (más de la mitad de los residuos iguales) dejaría a Huber sin
    zona cuadrática: se detiene en vez de inventar un valor."""
    d = float(factor) * mad(residuos, normalizada=normalizada)
    if not (np.isfinite(d) and d > 0):
        raise ValueError(f"δ de Huber no positivo ({d}): los residuos del ajuste cuadrático no tienen dispersión")
    return d


def objetivo_xgb_huber(delta: float):
    """Objetivo propio de XGBoost con el gradiente y la hessiana del Huber de LightGBM."""
    delta = float(delta)

    def objetivo(pred, dtrain):
        return huber_gradiente(pred, dtrain.get_label(), delta)

    objetivo.__name__ = f"huber_lightgbm_delta_{delta:.6g}"
    return objetivo


# ---------------------------------------------------------------------------
# Especificación de una variante
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Variante:
    """Una pérdida concreta: ``nombre`` de §6, ``tau`` en pinball y ``delta`` en Huber (se fija por pliegue)."""

    nombre: str
    tau: float | None = None
    delta: float | None = None
    extra: dict = field(default_factory=dict, compare=False, hash=False)

    def __post_init__(self):
        if self.nombre not in VARIANTES:
            raise ValueError(f"variante de pérdida desconocida: {self.nombre!r} (usa {VARIANTES})")
        if self.nombre == "pinball" and not (self.tau is not None and 0.0 < float(self.tau) < 1.0):
            raise ValueError("pinball necesita un τ en (0, 1)")
        if self.nombre != "pinball" and self.tau is not None:
            raise ValueError(f"{self.nombre} no lleva τ")

    @property
    def blanco(self) -> str:
        return BLANCO_LOG if self.nombre == "l2_log_duan" else BLANCO_ORIGINAL

    @property
    def escala(self) -> str:
        """Escala de la salida del motor: «log» (necesita retransformación) u «original»."""
        return "log" if self.blanco == BLANCO_LOG else "original"

    @property
    def etiqueta(self) -> str:
        if self.nombre == "pinball":
            return f"q{int(round(float(self.tau) * 100)):02d}"
        return self.nombre

    def con_delta(self, delta: float) -> "Variante":
        if self.nombre != "huber":
            raise ValueError("sólo Huber lleva δ")
        return Variante("huber", delta=float(delta))

    def descripcion(self) -> dict:
        d = {"variante": self.nombre, "blanco": self.blanco, "escala_salida": self.escala}
        if self.tau is not None:
            d["tau"] = float(self.tau)
        if self.delta is not None:
            d["delta"] = float(self.delta)
        return d


def variante_de_etiqueta(etiqueta: str) -> Variante:
    """``l2_log_duan``, ``l2_original``, ``huber`` o ``qNN`` (pinball con τ = NN/100)."""
    if etiqueta.startswith("q") and etiqueta[1:].isdigit():
        return Variante("pinball", tau=int(etiqueta[1:]) / 100.0)
    return Variante(etiqueta)


def transformar_blanco(y, variante: Variante) -> np.ndarray:
    """Blanco del motor: log1p(clip(y, 0)) en la referencia (como la v1, qmd:2206) o y en las demás."""
    y = np.asarray(y, dtype="float64")
    if variante.blanco == BLANCO_LOG:
        return np.log1p(np.clip(y, 0.0, None))
    return y.copy()


def a_escala_original(salida, variante: Variante) -> np.ndarray:
    """Para las variantes en escala original: recorte en 0 (la referencia en log pasa por la retransformación)."""
    if variante.escala == "log":
        raise ValueError("la variante en log vuelve a escala original con la retransformación (§5), no aquí")
    return np.clip(np.asarray(salida, dtype="float64"), 0.0, None).astype("float32")


def inicio_xgboost(y_blanco, variante: Variante) -> float:
    """``base_score`` equivalente al inicio de LightGBM (``boost_from_average``): la media en L2 y Huber, el
    cuantil τ en pinball."""
    yb = np.asarray(y_blanco, dtype="float64")
    if variante.nombre == "pinball":
        return float(np.quantile(yb, float(variante.tau)))
    return float(np.mean(yb))


def parametros_lightgbm(base: dict, variante: Variante) -> dict:
    """Parámetros nativos de LightGBM para la variante, sobre la receta ``base`` (sin ``num_boost_round``)."""
    p = dict(base)
    if variante.nombre in ("l2_log_duan", "l2_original"):
        p["objective"] = "regression"
    elif variante.nombre == "huber":
        if variante.delta is None:
            raise ValueError("Huber sin δ: se fija con el ajuste cuadrático del pliegue")
        p["objective"], p["alpha"] = "huber", float(variante.delta)
    else:
        p["objective"], p["alpha"] = "quantile", float(variante.tau)
    return p


def parametros_xgboost(base: dict, variante: Variante, y_blanco) -> tuple[dict, object]:
    """(parámetros, objetivo propio o None) de XGBoost para la variante, sobre la receta ``base``."""
    p = dict(base)
    obj = None
    if variante.nombre in ("l2_log_duan", "l2_original"):
        p["objective"] = "reg:squarederror"
    elif variante.nombre == "huber":
        if variante.delta is None:
            raise ValueError("Huber sin δ: se fija con el ajuste cuadrático del pliegue")
        p.pop("objective", None)
        obj = objetivo_xgb_huber(variante.delta)
    else:
        p["objective"], p["quantile_alpha"] = "reg:quantileerror", float(variante.tau)
    p["base_score"] = inicio_xgboost(y_blanco, variante)
    return p, obj


# ---------------------------------------------------------------------------
# Métricas propias de los cuantiles (las comunes viven en metricas_v2)
# ---------------------------------------------------------------------------
def cobertura(y, inferior, superior) -> float:
    """Fracción de observaciones dentro de [inferior, superior] (un intervalo cruzado no cubre nada)."""
    y, lo, hi = (np.asarray(a, dtype="float64") for a in (y, inferior, superior))
    ok = np.isfinite(y) & np.isfinite(lo) & np.isfinite(hi)
    if not ok.any():
        return float("nan")
    return float(np.mean((y[ok] >= lo[ok]) & (y[ok] <= hi[ok])))


def puntaje_intervalo(y, inferior, superior, alfa: float = 0.1) -> np.ndarray:
    """Puntaje de intervalo de Gneiting y Raftery (2007) por fila, para el intervalo central (1 − α):
    ``(u − l) + (2/α)(l − y)·1{y < l} + (2/α)(y − u)·1{y > u}``; menor es mejor."""
    y, lo, hi = (np.asarray(a, dtype="float64") for a in (y, inferior, superior))
    a = float(alfa)
    return (hi - lo) + (2.0 / a) * (lo - y) * (y < lo) + (2.0 / a) * (y - hi) * (y > hi)
