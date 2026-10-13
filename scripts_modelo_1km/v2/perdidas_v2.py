"""Funciones de pérdida de la v2 (``DISENO_AMBIENTAL_V2.md`` §6, etapa 8, con la Enmienda 1) para LightGBM y XGBoost.

Cuatro variantes, con el mismo N, los mismos pliegues y la receta del eje A (§3) sin cambios; sólo cambian el
objetivo y el blanco (``config_v2.json`` → ``perdidas``):

===============  ============  =====================================================================
variante         blanco        objetivo
===============  ============  =====================================================================
l2_log_smearing  log1p(y)      cuadrático; vuelve a escala original con la retransformación primaria
                               (smearing de Duan, §5 y Enmienda 1, punto 2). La referencia v1 es el mismo
                               ajuste con ½·σ² (``l2_log_medio_sigma2``), que se arma al consolidar.
l2_original      y             cuadrático en escala original (media condicional directa)
huber            y             Huber con δ común a LightGBM y XGBoost en cada pliegue (Enmienda 1, punto 9)
pinball          y             cuantílico, τ = 0,05, 0,5 y 0,95 (mediana e intervalo del 90 %)
===============  ============  =====================================================================

**Huber (Enmienda 1, punto 9).** δ = 1,345 × MAD normalizado de residuos **honestos** del ajuste cuadrático en
escala original de LightGBM: una partición agrupada en dos dentro del entrenamiento del pliegue, donde cada mitad
se predice con el modelo ajustado en la otra (``correr_v2`` arma la partición; aquí sólo la regla). El mismo δ
sirve a LightGBM y a XGBoost. Sensibilidad: δ = cuantil 0,9 de |r| (Friedman 2001), con los mismos residuos
(variante ``huber`` con ``regla="friedman"``, etiqueta ``huber_friedman``). Por pliegue se registran δ, la
fracción de filas recortadas (|y − ŷ| > δ) y la pérdida final de entrenamiento (``registro_huber``).
*Declaración:* con el gradiente recortado y 800 rondas, los picos invernales pueden quedar fuera de alcance; Huber
y q50 no estiman la media y no compiten en el §9.

**Cuantiles (Enmienda 1, punto 9).** Se reordenan (q05 ≤ q50 ≤ q95, Chernozhukov et al. 2010) antes de medir la
cobertura, informando los cruces (``reordenar_cuantiles``), y se calibran con conformal agrupado (CQR; Romano et
al. 2019) con los puntajes fuera de pliegue de los demás grupos, la misma exclusión del protocolo y la clave
macrozona × franja, con el respaldo honesto de la retransformación (``cqr_fuera_de_pliegue``).

Convenciones (ratificadas por la Enmienda 1 o provisionales de ``config_v2.json``):

* **MAD**: el normalizado, ``1,4826 × mediana(|r − mediana(r)|)``, de modo que ``1,345 × MAD`` es la constante
  de Huber para un 95 % de eficiencia bajo normalidad (Huber, 1981).
* **Huber en XGBoost**: XGBoost sólo trae ``reg:pseudohubererror``, que no es la Huber de LightGBM. Se usa un
  objetivo propio con el gradiente y la hessiana del Huber de LightGBM: gradiente ``recorte(ŷ − y, ±δ)`` y
  hessiana 1 en todas las filas (verificado contra ``objective="huber"`` de LightGBM 4.7.0 sin bagging: las
  predicciones coinciden a 1e-8). Con un objetivo propio XGBoost arranca en 0,5, así que ``base_score`` se fija
  en la media del blanco, que es el inicio de LightGBM para L2 y Huber (``boost_from_average``).
* **Cuantiles**: ``objective="quantile"`` (``alpha = τ``) en LightGBM y ``reg:quantileerror``
  (``quantile_alpha = τ``) en XGBoost; los dos parten del cuantil τ del blanco y renuevan las hojas con el
  cuantil de los residuos. Gradiente ``1 − τ`` si ŷ > y y ``−τ`` si no, hessiana 1.
* **min_child_weight** (Enmienda 1, punto 1.2): ``min_child_weight = 50`` de XGBoost equivale a
  ``min_data_in_leaf = 50`` de LightGBM sólo con hessiana 1 («equivalencia con hessiana 1»). Todas las variantes
  la tienen; ``parametros_xgboost`` **se niega** a usar ese valor con un objetivo de hessiana no constante
  (pseudo-Huber, Poisson, Gamma, …).
* Las predicciones en escala original (``l2_original``, ``huber`` y ``pinball``) se recortan en 0, como GWR y
  RK en la v1: el blanco es no negativo y el recorte sólo puede acercar la predicción a lo observado.

Este módulo es puro: no lee ni escribe archivos.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

VARIANTES = ("l2_log_smearing", "l2_original", "huber", "pinball")
NOMBRES_ANTERIORES = {"l2_log_duan": "l2_log_smearing"}          # Enmienda 1, punto 2
TAUS = (0.05, 0.5, 0.95)
FACTOR_HUBER = 1.345
CUANTIL_FRIEDMAN = 0.9                             # Friedman (2001): δ = cuantil 0,9 de |r|
REGLAS_DELTA = ("mad", "friedman")
CONSTANTE_MAD_NORMAL = 1.482602218505602          # 1 / Φ⁻¹(3/4)
BLANCO_LOG = "log1p"
BLANCO_ORIGINAL = "y"
# Objetivos nativos de XGBoost cuya hessiana es constante (1 por fila): con ellos min_child_weight cuenta filas.
OBJETIVOS_XGB_HESSIANA_CONSTANTE = frozenset({"reg:squarederror", "reg:quantileerror", "reg:absoluteerror"})
NIVELES_CQR = ("macrozona_franja", "franja", "global", "sin_calibracion")
NOMBRE_FRANJA = {1: "diurna", 0: "nocturna"}


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


def delta_friedman(residuos, cuantil: float = CUANTIL_FRIEDMAN) -> float:
    """δ de la sensibilidad de Friedman (2001): el cuantil 0,9 de |r| (interpolación lineal de numpy)."""
    r = np.asarray(residuos, dtype="float64")
    r = r[np.isfinite(r)]
    if r.size == 0:
        raise ValueError("δ de Friedman de un vector sin valores finitos")
    d = float(np.quantile(np.abs(r), float(cuantil)))
    if not (np.isfinite(d) and d > 0):
        raise ValueError(f"δ de Friedman no positivo ({d})")
    return d


def deltas_honestos(residuos) -> dict:
    """δ primario (1,345 × MAD normalizado) y δ de la sensibilidad (Friedman) de los mismos residuos honestos."""
    r = np.asarray(residuos, dtype="float64")
    d = delta_huber(r)
    return {"mad": d, "friedman": delta_friedman(r), "mad_normalizado": d / FACTOR_HUBER,
            "residuos": int(np.isfinite(r).sum())}


def registro_huber(y, pred, delta: float) -> dict:
    """Registro por pliegue de un ajuste Huber (Enmienda 1, punto 9) sobre sus filas de entrenamiento: δ, fracción
    de filas recortadas (|y − ŷ| > δ, en la zona lineal de la pérdida) y pérdida final (media de Huber)."""
    y, p = np.asarray(y, dtype="float64"), np.asarray(pred, dtype="float64")
    ok = np.isfinite(y) & np.isfinite(p)
    a = np.abs(p[ok] - y[ok])
    return {"delta": float(delta), "filas": int(ok.sum()),
            "fraccion_recortada": float(np.mean(a > float(delta))) if ok.any() else float("nan"),
            "perdida_final": float(np.mean(huber_perdida(p[ok], y[ok], float(delta)))) if ok.any() else float("nan")}


def objetivo_xgb_huber(delta: float):
    """Objetivo propio de XGBoost con el gradiente y la hessiana (constante, 1) del Huber de LightGBM."""
    delta = float(delta)

    def objetivo(pred, dtrain):
        return huber_gradiente(pred, dtrain.get_label(), delta)

    objetivo.__name__ = f"huber_lightgbm_delta_{delta:.6g}"
    objetivo.hessiana_constante = True
    return objetivo


# ---------------------------------------------------------------------------
# Especificación de una variante
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Variante:
    """Una pérdida concreta: ``nombre`` de §6, ``tau`` en pinball, ``delta`` en Huber (se fija por pliegue) y
    ``regla`` de δ en Huber («mad», la primaria, o «friedman», la sensibilidad)."""

    nombre: str
    tau: float | None = None
    delta: float | None = None
    extra: dict = field(default_factory=dict, compare=False, hash=False)
    regla: str | None = None

    def __post_init__(self):
        if self.nombre in NOMBRES_ANTERIORES:
            raise ValueError(f"la variante {self.nombre!r} se renombró {NOMBRES_ANTERIORES[self.nombre]!r} "
                             f"(Enmienda 1, punto 2: la primaria es el smearing de Duan)")
        if self.nombre not in VARIANTES:
            raise ValueError(f"variante de pérdida desconocida: {self.nombre!r} (usa {VARIANTES})")
        if self.nombre == "pinball" and not (self.tau is not None and 0.0 < float(self.tau) < 1.0):
            raise ValueError("pinball necesita un τ en (0, 1)")
        if self.nombre != "pinball" and self.tau is not None:
            raise ValueError(f"{self.nombre} no lleva τ")
        if self.nombre == "huber":
            if self.regla is None:
                object.__setattr__(self, "regla", "mad")
            elif self.regla not in REGLAS_DELTA:
                raise ValueError(f"regla de δ desconocida: {self.regla!r} (usa {REGLAS_DELTA})")
        elif self.regla is not None:
            raise ValueError(f"{self.nombre} no lleva regla de δ")

    @property
    def blanco(self) -> str:
        return BLANCO_LOG if self.nombre == "l2_log_smearing" else BLANCO_ORIGINAL

    @property
    def escala(self) -> str:
        """Escala de la salida del motor: «log» (necesita retransformación) u «original»."""
        return "log" if self.blanco == BLANCO_LOG else "original"

    @property
    def hessiana_constante(self) -> bool:
        """Todas las variantes de la v2 tienen hessiana 1 por fila (L2, el Huber de LightGBM y el cuantil)."""
        return True

    @property
    def estima_la_media(self) -> bool:
        """Huber y los cuantiles no estiman la media (Enmienda 1, punto 9): no compiten en el §9."""
        return self.nombre in ("l2_log_smearing", "l2_original")

    @property
    def etiqueta(self) -> str:
        if self.nombre == "pinball":
            return f"q{int(round(float(self.tau) * 100)):02d}"
        if self.nombre == "huber" and self.regla == "friedman":
            return "huber_friedman"
        return self.nombre

    def con_delta(self, delta: float) -> "Variante":
        if self.nombre != "huber":
            raise ValueError("sólo Huber lleva δ")
        return Variante("huber", delta=float(delta), regla=self.regla)

    def descripcion(self) -> dict:
        d = {"variante": self.nombre, "blanco": self.blanco, "escala_salida": self.escala}
        if self.tau is not None:
            d["tau"] = float(self.tau)
        if self.regla is not None:
            d["regla_delta"] = self.regla
        if self.delta is not None:
            d["delta"] = float(self.delta)
        return d


def variante_de_etiqueta(etiqueta: str) -> Variante:
    """``l2_log_smearing``, ``l2_original``, ``huber``, ``huber_friedman`` o ``qNN`` (pinball con τ = NN/100)."""
    if etiqueta.startswith("q") and etiqueta[1:].isdigit():
        return Variante("pinball", tau=int(etiqueta[1:]) / 100.0)
    if etiqueta == "huber_friedman":
        return Variante("huber", regla="friedman")
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
    if variante.nombre in ("l2_log_smearing", "l2_original"):
        p["objective"] = "regression"
    elif variante.nombre == "huber":
        if variante.delta is None:
            raise ValueError("Huber sin δ: se fija con el ajuste cuadrático honesto del pliegue")
        p["objective"], p["alpha"] = "huber", float(variante.delta)
    else:
        p["objective"], p["alpha"] = "quantile", float(variante.tau)
    return p


def hessiana_constante_xgboost(objetivo: str | None, obj=None) -> bool:
    """¿El objetivo de XGBoost tiene hessiana constante? Un objetivo propio debe declararlo
    (``obj.hessiana_constante = True``); uno nativo, estar en ``OBJETIVOS_XGB_HESSIANA_CONSTANTE``."""
    if obj is not None:
        return bool(getattr(obj, "hessiana_constante", False))
    return objetivo in OBJETIVOS_XGB_HESSIANA_CONSTANTE


def verificar_hessiana_xgboost(params: dict, obj=None, exigir: bool = True) -> None:
    """Salvaguarda de la Enmienda 1, punto 1.2: ``min_child_weight`` está fijado como «equivalencia con hessiana 1»
    (LightGBM cuenta filas y XGBoost suma hessianas), así que no se usa con un objetivo de hessiana no constante."""
    if not exigir or float(params.get("min_child_weight", 0.0) or 0.0) <= 0.0:
        return
    if not hessiana_constante_xgboost(params.get("objective"), obj):
        nombre = getattr(obj, "__name__", None) if obj is not None else params.get("objective")
        raise ValueError(f"XGBoost: min_child_weight = {params.get('min_child_weight')} está fijado como «equivalencia "
                         f"con hessiana 1» y el objetivo {nombre!r} no tiene hessiana constante; con él la "
                         f"equivalencia con min_data_in_leaf de LightGBM se rompe (Enmienda 1, punto 1.2)")


def parametros_xgboost(base: dict, variante: Variante, y_blanco,
                       exigir_hessiana_constante: bool = True) -> tuple[dict, object]:
    """(parámetros, objetivo propio o None) de XGBoost para la variante, sobre la receta ``base``. Con
    ``exigir_hessiana_constante`` (la receta v2) se niega a combinar ``min_child_weight`` con un objetivo de
    hessiana no constante."""
    p = dict(base)
    obj = None
    if variante.nombre in ("l2_log_smearing", "l2_original"):
        p["objective"] = "reg:squarederror"
    elif variante.nombre == "huber":
        if variante.delta is None:
            raise ValueError("Huber sin δ: se fija con el ajuste cuadrático honesto del pliegue")
        p.pop("objective", None)
        obj = objetivo_xgb_huber(variante.delta)
    else:
        p["objective"], p["quantile_alpha"] = "reg:quantileerror", float(variante.tau)
    if not variante.hessiana_constante:
        raise ValueError(f"la variante {variante.nombre} no tiene hessiana constante")
    verificar_hessiana_xgboost(p, obj, exigir_hessiana_constante)
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


# ---------------------------------------------------------------------------
# Cuantiles: reordenamiento y calibración conformal agrupada (Enmienda 1, punto 9)
# ---------------------------------------------------------------------------
def reordenar_cuantiles(q05, q50, q95) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """Reordenamiento de Chernozhukov et al. (2010) para tres cuantiles: en cada fila se ordenan los tres valores,
    de modo que q05 ≤ q50 ≤ q95. Devuelve los cuantiles reordenados (float32) y el conteo de cruces por par. Las
    filas con algún valor no finito quedan como estaban (y no cuentan)."""
    Q = np.vstack([np.asarray(q, dtype="float64") for q in (q05, q50, q95)])
    if Q.shape[0] != 3:
        raise ValueError("se esperan tres cuantiles")
    fin = np.isfinite(Q).all(axis=0)
    c01, c12, c02 = (fin & (Q[0] > Q[1])), (fin & (Q[1] > Q[2])), (fin & (Q[0] > Q[2]))
    S = Q.copy()
    S[:, fin] = np.sort(Q[:, fin], axis=0)
    registro = {"filas": int(fin.sum()), "filas_con_cruce": int((c01 | c12 | c02).sum()),
                "q05_mayor_que_q50": int(c01.sum()), "q50_mayor_que_q95": int(c12.sum()),
                "q05_mayor_que_q95": int(c02.sum())}
    registro["fraccion_con_cruce"] = registro["filas_con_cruce"] / registro["filas"] if registro["filas"] else float("nan")
    return S[0].astype("float32"), S[1].astype("float32"), S[2].astype("float32"), registro


def puntaje_cqr(y, inferior, superior) -> np.ndarray:
    """Puntaje de conformidad de CQR (Romano et al. 2019): E = máx(inferior − y, y − superior)."""
    y, lo, hi = (np.asarray(a, dtype="float64") for a in (y, inferior, superior))
    return np.maximum(lo - y, y - hi)


def rango_conformal(n: int, nivel: float) -> int:
    """Posición (1 = el menor) del cuantil conformal: ⌈(n + 1)·nivel⌉."""
    return int(math.ceil((int(n) + 1) * float(nivel) - 1e-12))


def cuantil_conformal(puntajes, nivel: float) -> float:
    """El valor ⌈(n + 1)·nivel⌉-ésimo de los puntajes ordenados (infinito si esa posición pasa de n)."""
    e = np.asarray(puntajes, dtype="float64")
    e = np.sort(e[np.isfinite(e)])
    j = rango_conformal(len(e), nivel)
    return float(e[j - 1]) if 1 <= j <= len(e) else float("inf")


def clave_cqr(macrozona: int, franja: int) -> str:
    """Clave de la v1, ``"{macrozona_cod}|{franja}"``, como la retransformación."""
    return f"{int(macrozona)}|{NOMBRE_FRANJA[int(franja)]}"


def cqr_fuera_de_pliegue(y, inferior, superior, estacion, macrozona, franja, pliegue_de_fila,
                         excluidas_por_pliegue: dict, temporal: bool, conglomerado_de_estacion, nivel: float = 0.9,
                         minimo_filas: int = 100, minimo_conglomerados: int = 3, minimo_grupos: int = 2,
                         piso: float | None = 0.0):
    """Calibración conformal agrupada (CQR) del intervalo [``inferior``, ``superior``] de un protocolo completo.

    Para las filas de prueba del pliegue k, Q sale de los puntajes ``E = máx(inferior − y, y − superior)`` **de
    los demás grupos**, con **la misma exclusión del protocolo** (en los espaciales, ninguna fila de una estación
    del conjunto excluido; en LPO, ninguna del propio cuatrienio), por clave macrozona × franja, con el respaldo
    honesto de la retransformación: la clave sólo si reúne al menos ``minimo_conglomerados`` conglomerados LOSO-D
    de al menos ``minimo_grupos`` grupos distintos del retirado y ``minimo_filas`` filas; si no, la franja de los
    demás y luego el global de los demás (``minimo_filas``); si ni eso, sin calibración (Q = 0, con marca).
    Q = el valor ⌈(n + 1)·nivel⌉-ésimo de esos puntajes y el intervalo calibrado es [inferior − Q, superior + Q],
    acotado abajo por ``piso`` (0: el blanco es no negativo, así que el piso no cambia la cobertura).

    ``estacion``: código entero por fila; ``conglomerado_de_estacion``: código entero del conglomerado LOSO-D de
    cada código de estación; ``franja``: 1 diurna, 0 nocturna. Devuelve ``(inferior_cal, superior_cal, Q, nivel,
    registro, resumen)``: Q y el nivel (índice en ``NIVELES_CQR``) por fila, un renglón por pliegue × clave y los
    totales (filas por nivel e intervalos vacíos, posibles cuando Q < 0)."""
    lo = np.asarray(inferior, dtype="float64")
    hi = np.asarray(superior, dtype="float64")
    E = puntaje_cqr(y, lo, hi)
    est = np.asarray(estacion, dtype="int64")
    mz = np.asarray(macrozona, dtype="int64")
    fr = np.asarray(franja, dtype="int64")
    pk = np.asarray(pliegue_de_fila, dtype="int64")
    congl_est = np.asarray(conglomerado_de_estacion, dtype="int64")
    if len(est) and est.max() >= len(congl_est):
        raise ValueError("falta el conglomerado LOSO-D de alguna estación")
    congl = congl_est[est] if len(est) else np.zeros(0, dtype="int64")
    maximo_excluido = max((int(np.max(v)) for v in excluidas_por_pliegue.values() if len(v)), default=-1)
    n_est = int(max(est.max() + 1 if len(est) else 0, len(congl_est), maximo_excluido + 1))
    n_congl = int(congl_est.max() + 1) if len(congl_est) else 0
    n_pl = int(pk.max() + 1) if len(pk) and pk.max() >= 0 else 0
    clave = mz * 2 + fr
    valido = np.isfinite(E) & (pk >= 0)

    def ordenados(mascara):
        idx = np.flatnonzero(mascara)
        idx = idx[np.argsort(E[idx], kind="stable")]
        return {"E": E[idx], "est": est[idx], "pk": pk[idx], "congl": congl[idx]}

    por_clave = {int(c): ordenados(valido & (clave == c)) for c in np.unique(clave[valido])}
    cache_franja, cache_global = {}, {}

    def pool(g, kk, ok_est):
        m = (g["pk"] != kk) & ok_est[g["est"]]
        return m, int(m.sum())

    def resolver(g, m, n):
        j = rango_conformal(n, nivel)
        return float(g["E"][np.flatnonzero(m)[j - 1]]) if 1 <= j <= n else float("inf")

    lo_c, hi_c = np.full(len(E), np.nan), np.full(len(E), np.nan)
    Q = np.full(len(E), np.nan)
    niv_f = np.full(len(E), -1, dtype="int8")
    registro = []
    for kk in np.unique(pk[pk >= 0]):
        filas = np.flatnonzero(pk == kk)
        ok_est = np.ones(n_est, dtype=bool)
        if not temporal:
            excl = np.asarray(excluidas_por_pliegue.get(int(kk), []), dtype="int64")
            if not np.isin(np.unique(est[filas]), excl).all():
                raise ValueError(f"pliegue {kk}: hay filas de prueba de estaciones fuera del conjunto excluido")
            ok_est[excl] = False
        for c in np.unique(clave[filas]):
            c = int(c)
            cmz, cfr = c // 2, c % 2
            nivel_usado, q, n_usado, n_c, n_g = "sin_calibracion", 0.0, 0, 0, 0
            g = por_clave.get(c)
            if g is not None:
                m, n = pool(g, int(kk), ok_est)
                if n:
                    n_c = int((np.bincount(g["congl"][m], minlength=n_congl) > 0).sum())
                    n_g = int((np.bincount(g["pk"][m], minlength=n_pl) > 0).sum())
                if n >= minimo_filas and n_c >= minimo_conglomerados and n_g >= minimo_grupos:
                    nivel_usado, q, n_usado = "macrozona_franja", resolver(g, m, n), n
            if nivel_usado == "sin_calibracion":
                if cfr not in cache_franja:
                    cache_franja[cfr] = ordenados(valido & (fr == cfr))
                gf = cache_franja[cfr]
                m, n = pool(gf, int(kk), ok_est)
                if n >= minimo_filas:
                    nivel_usado, q, n_usado = "franja", resolver(gf, m, n), n
            if nivel_usado == "sin_calibracion":
                if not cache_global:
                    cache_global["g"] = ordenados(valido)
                gg = cache_global["g"]
                m, n = pool(gg, int(kk), ok_est)
                if n >= minimo_filas:
                    nivel_usado, q, n_usado = "global", resolver(gg, m, n), n
            sel = filas[clave[filas] == c]
            Q[sel] = q
            niv_f[sel] = NIVELES_CQR.index(nivel_usado)
            lo_c[sel], hi_c[sel] = lo[sel] - q, hi[sel] + q
            registro.append({"k": int(kk), "clave": clave_cqr(cmz, cfr), "nivel": nivel_usado, "filas_usadas": n_usado,
                             "conglomerados_clave": n_c, "grupos_clave": n_g, "Q": q, "filas_prueba": int(len(sel))})
    if piso is not None:
        lo_c = np.where(np.isfinite(lo_c), np.maximum(lo_c, float(piso)), lo_c)
        hi_c = np.where(np.isfinite(hi_c), np.maximum(hi_c, float(piso)), hi_c)
    cuenta = np.bincount(niv_f[niv_f >= 0].astype("int64"), minlength=len(NIVELES_CQR))
    resumen = {"nivel": float(nivel), "filas_por_nivel": {n: int(cuenta[i]) for i, n in enumerate(NIVELES_CQR)},
               "intervalos_vacios": int(np.sum(np.isfinite(lo_c) & np.isfinite(hi_c) & (lo_c > hi_c)))}
    return lo_c.astype("float32"), hi_c.astype("float32"), Q, niv_f, registro, resumen
