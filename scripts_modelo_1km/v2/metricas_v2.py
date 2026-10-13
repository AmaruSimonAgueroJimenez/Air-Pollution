"""Métricas de la comparación v2 (``DISENO_AMBIENTAL_V2.md`` §6 y §8).

**Pares de evaluación.** Antes de agregar se impone en el código la intersección de las predicciones finitas
de todos los motores (§4): ``pares_comunes``. Todo lo demás se calcula sobre esos pares, de modo que
observado y predicho se promedian siempre sobre las mismas horas en todos los motores.

**Niveles** (§8):

* ``horario``: cada par estación × hora;
* ``diario_civil``: estación × día civil de America/Santiago (con horario de verano), con al menos 18 horas;
* ``diario_utc4``: estación × día del reloj UTC−4 fijo (la ``fecha_local`` del panel, ``_features.py:119-130``),
  con al menos 18 horas, como la v1 (``qmd:2587-2589``);
* ``mensual``: estación × mes del día civil, con al menos 20 días civiles válidos (provisional: la regla de la
  v1, ``qmd:3653-3656``);
* ``anual``: estación × año, con al menos 9 meses válidos (provisional: la regla de la v1).

La hora de una fila es la del inicio de su bin UTC (``ts_utc``), como en la ``fecha_local`` de la v1.

**Escalas.** «original»: la predicción en µg/m³ o ppb contra lo observado. «log»: ``ẑ`` (la salida del motor
antes de la retransformación; en los motores de escala original, ``log1p(máx(ŷ, 0))``) contra ``log1p(y)``,
promediados en log en cada nivel. Así se separa el motor de la corrección (§5).

**Desagregaciones** (§8): total, macrozona, estación, régimen de predictores (año en 2019–2024, con GEOS-CF y
TROPOMI, o fuera; provisional de la v1, ``REGIMEN_SAT``, ``qmd:355``), estrato de soporte (cuartiles de
``peso_vec`` y de ``dist_est_km`` de las filas horarias de evaluación, con los valores recalculados en el
pliegue; en los niveles agregados se usa la media de las horas) y ponderación por población (``pob_dens`` de la
celda de la estación en cada fila; en los niveles agregados, su media). La ponderación por población se aplica
al total, a la macrozona y al régimen.

**Métricas** en escala original (§6): R² = 1 − SSE/SST (agrupado, como ``metricas`` de la v1, ``qmd:2580``;
NaN con menos de 3 pares o SST nula), RMSE, MAE, NMB = Σ(p − o)/Σo, sesgo medio y r de Pearson; con pesos,
las mismas en su versión ponderada. Se calculan con sumas por grupo (``numpy.bincount``): exacto y rápido.

**Cuantiles** (§6): cobertura del intervalo del 90 %, puntaje de intervalo y calibración por decil de la
predicción mediana, macrozona y franja. **Alertas** (§3): el cuantil 0,80 se juzga aparte.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import numpy as np
import pandas as pd

from perdidas_v2 import pinball_perdida, puntaje_intervalo
from retransformacion_v2 import NOMBRE_FRANJA, franja

ZONA_CIVIL = "America/Santiago"
OFFSET_UTC4_H = 4
NS_DIA = 86_400_000_000_000
NIVELES = ("horario", "diario_civil", "diario_utc4", "mensual", "anual")
MINIMO_HORAS_DIA = 18
MINIMO_DIAS_MES = 20                # provisional (v1)
MINIMO_MESES_ANIO = 9               # provisional (v1)
REGIMEN_SAT = (2019, 2024)          # provisional (v1, qmd:355)
NOMBRE_MACROZONA = {0: "norte_grande", 1: "norte_chico", 2: "centro", 3: "sur", 4: "austral", 5: "sin_region",
                    6: "insular"}                                         # _comun_modelo.py:88-89
COLUMNAS_METRICAS = ["n", "peso", "media_obs", "media_pred", "r2", "rmse", "mae", "nmb", "sesgo", "r"]
DESAGREGACIONES = ("total", "macrozona", "estacion", "regimen", "soporte_peso_vec", "soporte_dist_est_km")
PONDERABLES = ("total", "macrozona", "regimen")


# ---------------------------------------------------------------------------
# Pares comunes
# ---------------------------------------------------------------------------
def pares_comunes(obs, predicciones: Mapping[str, np.ndarray]) -> tuple[np.ndarray, dict]:
    """Máscara de los pares con observación finita y predicción finita **en todos** los motores, y cuántos
    pares quita cada motor (la intersección se impone antes de agregar, §4)."""
    o = np.asarray(obs, dtype="float64")
    ok = np.isfinite(o)
    info = {"filas": int(len(o)), "obs_no_finita": int((~ok).sum()), "no_finitas_por_motor": {}}
    for nombre, p in predicciones.items():
        p = np.asarray(p, dtype="float64")
        if p.shape != o.shape:
            raise ValueError(f"{nombre}: la predicción no tiene una entrada por par")
        malo = ~np.isfinite(p)
        info["no_finitas_por_motor"][nombre] = int(malo.sum())
        ok &= ~malo
    info["pares_comunes"] = int(ok.sum())
    return ok, info


def log_de(pred, z=None) -> np.ndarray:
    """Valor en escala log de un motor: su ``ẑ`` si trabaja en log; si no, ``log1p(máx(ŷ, 0))``."""
    if z is not None:
        return np.asarray(z, dtype="float64")
    return np.log1p(np.clip(np.asarray(pred, dtype="float64"), 0.0, None))


# ---------------------------------------------------------------------------
# Métricas por sumas
# ---------------------------------------------------------------------------
SUMAS = ("n", "sw", "swo", "swoo", "swp", "swpp", "swop", "swe", "swe2", "swae")


def _sumas_obs(g: np.ndarray, ng: int, o: np.ndarray, w: np.ndarray) -> np.ndarray:
    """n, Σw, Σwo y Σwo² por grupo (sólo dependen de lo observado: se comparten entre motores)."""
    wo = w * o
    return np.column_stack([np.bincount(g, minlength=ng).astype("float64"), np.bincount(g, weights=w, minlength=ng),
                            np.bincount(g, weights=wo, minlength=ng), np.bincount(g, weights=wo * o, minlength=ng)])


def _sumas_motor(g: np.ndarray, ng: int, o: np.ndarray, p: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Σwp, Σwp², Σwop, Σw(p − o), Σw(p − o)² y Σw|p − o| por grupo."""
    e = p - o
    wp, we = w * p, w * e
    return np.column_stack([np.bincount(g, weights=wp, minlength=ng), np.bincount(g, weights=wp * p, minlength=ng),
                            np.bincount(g, weights=wp * o, minlength=ng), np.bincount(g, weights=we, minlength=ng),
                            np.bincount(g, weights=we * e, minlength=ng),
                            np.bincount(g, weights=w * np.abs(e), minlength=ng)])


def sumas_por_grupo(g, ng: int, o, p, w=None) -> np.ndarray:
    """Sumas suficientes por grupo, matriz (ng, 10) en el orden de ``SUMAS``: n, Σw, Σwo, Σwo², Σwp, Σwp²,
    Σwop, Σw(p − o), Σw(p − o)² y Σw|p − o|. ``g`` es el código entero del grupo de cada par (−1 lo descarta)."""
    g = np.asarray(g, dtype="int64")
    o, p = np.asarray(o, dtype="float64"), np.asarray(p, dtype="float64")
    w = np.ones_like(o) if w is None else np.asarray(w, dtype="float64")
    sel = g >= 0
    g, o, p, w = g[sel], o[sel], p[sel], w[sel]
    return np.hstack([_sumas_obs(g, ng, o, w), _sumas_motor(g, ng, o, p, w)])


def metricas_desde_sumas(S: np.ndarray) -> np.ndarray:
    """Matriz (ng, 10) en el orden de ``COLUMNAS_METRICAS`` a partir de ``sumas_por_grupo``."""
    S = np.atleast_2d(np.asarray(S, dtype="float64"))
    n, sw, swo, swoo, swp, swpp, swop, swe, swe2, swae = (S[:, i] for i in range(S.shape[1]))
    with np.errstate(invalid="ignore", divide="ignore"):
        mo, mp = swo / sw, swp / sw
        sst = swoo - swo * mo
        r2 = np.where((n >= 3) & (sst > 1e-12 * np.maximum(swoo, 1e-300)), 1.0 - swe2 / sst, np.nan)
        rmse = np.sqrt(swe2 / sw)
        mae = swae / sw
        sesgo = swe / sw
        nmb = np.where(swo > 0, swe / swo, np.nan)
        vo, vp = swoo / sw - mo * mo, swpp / sw - mp * mp
        cov = swop / sw - mo * mp
        r = np.where((n >= 3) & (vo > 0) & (vp > 0), cov / np.sqrt(np.maximum(vo * vp, 1e-300)), np.nan)
    vacio = sw <= 0
    out = np.column_stack([n, sw, mo, mp, r2, rmse, mae, nmb, sesgo, r])
    out[vacio, 2:] = np.nan
    return out


def metricas(o, p, w=None) -> dict:
    """Métricas de un solo conjunto de pares (con pesos opcionales)."""
    o = np.asarray(o, dtype="float64")
    ok = np.isfinite(o) & np.isfinite(np.asarray(p, dtype="float64"))
    if w is not None:
        ok &= np.isfinite(np.asarray(w, dtype="float64"))
    g = np.where(ok, 0, -1)
    fila = metricas_desde_sumas(sumas_por_grupo(g, 1, np.where(ok, o, 0), np.where(ok, p, 0),
                                                None if w is None else np.where(ok, w, 0)))[0]
    d = dict(zip(COLUMNAS_METRICAS, (float(x) for x in fila)))
    d["n"] = int(d["n"])
    return d


# ---------------------------------------------------------------------------
# Días, meses y años
# ---------------------------------------------------------------------------
def dia_civil(ts_utc) -> np.ndarray:
    """Día civil de America/Santiago (con horario de verano) de cada inicio de bin UTC, como entero de días
    desde 1970-01-01. Convierte sólo las horas distintas."""
    t = np.asarray(ts_utc, dtype="datetime64[ns]")
    u, inv = np.unique(t, return_inverse=True)
    local = pd.DatetimeIndex(u).tz_localize("UTC").tz_convert(ZONA_CIVIL).tz_localize(None)
    return (local.asi8 // NS_DIA)[inv.ravel()].astype("int64")


def dia_utc4(ts_utc) -> np.ndarray:
    """Día del reloj UTC−4 fijo (la ``fecha_local`` de la v1) como entero de días desde 1970-01-01."""
    t = np.asarray(ts_utc, dtype="datetime64[ns]").astype("int64")
    return np.floor_divide(t - OFFSET_UTC4_H * 3_600_000_000_000, NS_DIA).astype("int64")


def _anio_mes(dias: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    d = pd.DatetimeIndex(np.asarray(dias, dtype="int64") * NS_DIA)
    return d.year.to_numpy().astype("int64"), d.month.to_numpy().astype("int64")


def _grupo_mayoritario(agg: np.ndarray, grupo: np.ndarray, n_agg: int) -> np.ndarray:
    """Para cada agregado, el grupo (pliegue) más frecuente entre sus horas; empate: el menor código."""
    G = int(grupo.max()) + 1 if len(grupo) else 1
    claves, cuentas = np.unique(agg.astype("int64") * G + grupo.astype("int64"), return_counts=True)
    a, gg = claves // G, claves % G
    orden = np.lexsort((gg, -cuentas, a))
    a, gg = a[orden], gg[orden]
    primero = np.ones(len(a), dtype=bool)
    primero[1:] = a[1:] != a[:-1]
    out = np.full(n_agg, -1, dtype="int64")
    out[a[primero]] = gg[primero]
    return out


# ---------------------------------------------------------------------------
# Niveles de agregación
# ---------------------------------------------------------------------------
@dataclass
class Nivel:
    """Pares de un nivel: observado y predicho (por motor) en escala original y log, con sus atributos."""

    nombre: str
    obs: np.ndarray
    log_obs: np.ndarray
    pred: dict
    log: dict
    estacion: np.ndarray
    macrozona: np.ndarray
    anio: np.ndarray
    peso_vec: np.ndarray
    dist_est_km: np.ndarray
    poblacion: np.ndarray
    grupo: np.ndarray
    unidades: np.ndarray = field(default=None)       # horas (o días o meses) por par


def _agregar(base: Nivel, clave: np.ndarray, minimo: int, nombre: str, anio_de=None) -> tuple[Nivel, np.ndarray]:
    """Promedio por ``clave`` (estación × período) de todas las series de ``base``, con al menos ``minimo``
    unidades; devuelve el nivel y la clave de cada agregado."""
    u, inv = np.unique(clave, axis=0, return_inverse=True)
    inv = inv.ravel()
    m = len(u)
    cuenta = np.bincount(inv, minlength=m)
    keep = cuenta >= minimo
    nuevo = -np.ones(m, dtype="int64")
    nuevo[keep] = np.arange(int(keep.sum()))
    ids = nuevo[inv]
    sel = ids >= 0
    mk = int(keep.sum())

    def media(v):
        return np.bincount(ids[sel], weights=np.asarray(v, dtype="float64")[sel], minlength=mk) / cuenta[keep]

    def primero(v):
        out = np.empty(mk, dtype=np.asarray(v).dtype)
        out[ids[sel]] = np.asarray(v)[sel]
        return out

    nivel = Nivel(nombre=nombre, obs=media(base.obs), log_obs=media(base.log_obs),
                  pred={k: media(v) for k, v in base.pred.items()}, log={k: media(v) for k, v in base.log.items()},
                  estacion=primero(base.estacion), macrozona=primero(base.macrozona),
                  anio=primero(base.anio) if anio_de is None else anio_de(u[keep]),
                  peso_vec=media(base.peso_vec), dist_est_km=media(base.dist_est_km),
                  poblacion=media(base.poblacion),
                  grupo=_grupo_mayoritario(ids[sel], base.grupo[sel], mk),
                  unidades=cuenta[keep].astype("int64"))
    return nivel, u[keep]


def niveles(base: Nivel, ts_utc, minimo_horas: int = MINIMO_HORAS_DIA, minimo_dias: int = MINIMO_DIAS_MES,
            minimo_meses: int = MINIMO_MESES_ANIO) -> dict[str, Nivel]:
    """Los cinco niveles de §8 a partir del nivel horario (ya restringido a los pares comunes)."""
    est = base.estacion.astype("int64")
    civil = dia_civil(ts_utc)
    utc4 = dia_utc4(ts_utc)
    anio_dia = lambda u: _anio_mes(u[:, 1])[0]                       # noqa: E731
    d_civil, k_civil = _agregar(base, np.column_stack([est, civil]), minimo_horas, "diario_civil", anio_dia)
    d_utc4, _ = _agregar(base, np.column_stack([est, utc4]), minimo_horas, "diario_utc4", anio_dia)
    anio_c, mes_c = _anio_mes(k_civil[:, 1])
    mensual, k_mes = _agregar(d_civil, np.column_stack([k_civil[:, 0], anio_c * 12 + (mes_c - 1)]), minimo_dias,
                              "mensual", lambda u: u[:, 1] // 12)
    anual, _ = _agregar(mensual, np.column_stack([k_mes[:, 0], k_mes[:, 1] // 12]), minimo_meses, "anual",
                        lambda u: u[:, 1])
    return {"horario": base, "diario_civil": d_civil, "diario_utc4": d_utc4, "mensual": mensual, "anual": anual}


# ---------------------------------------------------------------------------
# Tabla de métricas
# ---------------------------------------------------------------------------
def cortes_cuartiles(valores) -> np.ndarray:
    v = np.asarray(valores, dtype="float64")
    v = v[np.isfinite(v)]
    if len(v) == 0:
        return np.array([np.nan, np.nan, np.nan])
    return np.quantile(v, [0.25, 0.5, 0.75])


def estrato_cuartil(valores, cortes) -> np.ndarray:
    """Q1 … Q4 (0 … 3) con los cortes dados; −1 si el valor no es finito."""
    v = np.asarray(valores, dtype="float64")
    out = np.searchsorted(np.asarray(cortes, dtype="float64"), v, side="right").astype("int64")
    out[~np.isfinite(v)] = -1
    return out


def _grupos(nivel: Nivel, desag: str, cortes: dict, regimen=REGIMEN_SAT) -> tuple[np.ndarray, list]:
    if desag == "total":
        return np.zeros(len(nivel.obs), dtype="int64"), ["total"]
    if desag == "macrozona":
        cod = nivel.macrozona.astype("int64")
        u, inv = np.unique(cod, return_inverse=True)
        return inv.ravel(), [NOMBRE_MACROZONA.get(int(c), str(int(c))) for c in u]
    if desag == "estacion":
        u, inv = np.unique(nivel.estacion, return_inverse=True)
        return inv.ravel(), [str(x) for x in u]
    if desag == "regimen":
        a0, a1 = int(regimen[0]), int(regimen[1])
        con = (nivel.anio >= a0) & (nivel.anio <= a1)
        return con.astype("int64"), [f"sin GEOS-CF ni TROPOMI (fuera de {a0}–{a1})", f"con GEOS-CF y TROPOMI ({a0}–{a1})"]
    variable = desag.replace("soporte_", "")
    c = cortes[variable]
    etiquetas = []
    bordes = [-np.inf, *c, np.inf]
    for i in range(4):
        etiquetas.append(f"Q{i + 1} [{bordes[i]:.4g}, {bordes[i + 1]:.4g})")
    return estrato_cuartil(getattr(nivel, variable), c), etiquetas


def tabla_metricas(nvs: Mapping[str, Nivel], cortes: dict, motores=None, desagregaciones=DESAGREGACIONES,
                   ponderables=PONDERABLES, etiqueta_estacion=None, regimen=REGIMEN_SAT) -> pd.DataFrame:
    """Tabla larga: motor × escala × nivel × desagregación × estrato × ponderación, con las métricas de §6.

    ``cortes`` = ``{"peso_vec": [...], "dist_est_km": [...]}`` (cuartiles de las filas horarias de evaluación).
    ``etiqueta_estacion`` traduce el código entero de estación a su nombre."""
    filas = []
    for nombre_nivel, nv in nvs.items():
        lista = list(nv.pred) if motores is None else [m for m in motores if m in nv.pred]
        for desag in desagregaciones:
            g, etiquetas = _grupos(nv, desag, cortes, regimen)
            ng = len(etiquetas)
            if desag == "estacion" and etiqueta_estacion is not None:
                etiquetas = [etiqueta_estacion(int(e)) for e in etiquetas]
            sel = np.asarray(g) >= 0
            gs = np.asarray(g, dtype="int64")[sel]
            for pond in (("ninguna", "poblacion") if desag in ponderables else ("ninguna",)):
                w = np.ones(int(sel.sum())) if pond == "ninguna" else np.asarray(nv.poblacion, dtype="float64")[sel]
                for escala, obs, preds in (("original", nv.obs, nv.pred), ("log", nv.log_obs, nv.log)):
                    o = np.asarray(obs, dtype="float64")[sel]
                    So = _sumas_obs(gs, ng, o, w)                         # una vez por grupo, ponderación y escala
                    for motor in lista:
                        p = np.asarray(preds[motor], dtype="float64")[sel]
                        M = metricas_desde_sumas(np.hstack([So, _sumas_motor(gs, ng, o, p, w)]))
                        for j in range(ng):
                            if M[j, 0] == 0:
                                continue
                            filas.append({"motor": motor, "escala": escala, "nivel": nombre_nivel,
                                          "desagregacion": desag, "estrato": etiquetas[j], "ponderacion": pond,
                                          **dict(zip(COLUMNAS_METRICAS, M[j]))})
    t = pd.DataFrame(filas)
    if len(t):
        t["n"] = t["n"].astype("int64")
    return t


def nivel_horario(obs, pred: Mapping[str, np.ndarray], z: Mapping[str, np.ndarray | None], estacion, macrozona, anio,
                  peso_vec, dist_est_km, poblacion, grupo, mascara=None) -> Nivel:
    """Nivel horario restringido a ``mascara`` (los pares comunes, y si se pide, sólo los validados)."""
    m = np.ones(len(obs), dtype=bool) if mascara is None else np.asarray(mascara, dtype=bool)
    o = np.asarray(obs, dtype="float64")[m]
    return Nivel(nombre="horario", obs=o, log_obs=np.log1p(np.clip(o, 0.0, None)),
                 pred={k: np.asarray(v, dtype="float64")[m] for k, v in pred.items()},
                 log={k: log_de(pred[k], None if z.get(k) is None else z[k])[m] for k in pred},
                 estacion=np.asarray(estacion)[m], macrozona=np.asarray(macrozona)[m],
                 anio=np.asarray(anio, dtype="int64")[m], peso_vec=np.asarray(peso_vec, dtype="float64")[m],
                 dist_est_km=np.asarray(dist_est_km, dtype="float64")[m],
                 poblacion=np.asarray(poblacion, dtype="float64")[m], grupo=np.asarray(grupo, dtype="int64")[m],
                 unidades=np.ones(int(m.sum()), dtype="int64"))


def resumen_niveles(nvs: Mapping[str, Nivel]) -> dict:
    return {k: {"pares": int(len(v.obs)), "estaciones": int(len(np.unique(v.estacion)))} for k, v in nvs.items()}


# ---------------------------------------------------------------------------
# Cuantiles y alertas
# ---------------------------------------------------------------------------
def _calibracion_grupo(y, q05, q50, q95, alfa: float) -> dict:
    lo, hi = q05, q95
    pi = puntaje_intervalo(y, lo, hi, alfa)
    return {"n": int(len(y)), "cobertura_90": float(np.mean((y >= lo) & (y <= hi))),
            "bajo_q05": float(np.mean(y < q05)), "sobre_q95": float(np.mean(y > q95)),
            "tasa_q05": float(np.mean(y <= q05)), "tasa_q50": float(np.mean(y <= q50)), "tasa_q95": float(np.mean(y <= q95)),
            "ancho_medio": float(np.mean(hi - lo)), "puntaje_intervalo": float(np.mean(pi)),
            "pinball_q05": float(np.mean(pinball_perdida(y, q05, 0.05))),
            "pinball_q50": float(np.mean(pinball_perdida(y, q50, 0.5))),
            "pinball_q95": float(np.mean(pinball_perdida(y, q95, 0.95))),
            "cruces": float(np.mean(q05 > q95))}


def metricas_cuantiles(obs, q05, q50, q95, macrozona, hora_local, alfa: float = 0.1) -> pd.DataFrame:
    """Cobertura del intervalo [q05, q95] (nominal 90 %), puntaje de intervalo, tasas de cada cuantil y pinball,
    en total y por decil de la predicción mediana, macrozona y franja (§6). Un intervalo cruzado no cubre."""
    y, a, b, c = (np.asarray(v, dtype="float64") for v in (obs, q05, q50, q95))
    ok = np.isfinite(y) & np.isfinite(a) & np.isfinite(b) & np.isfinite(c)
    y, a, b, c = y[ok], a[ok], b[ok], c[ok]
    mz = np.asarray(macrozona)[ok]
    fr = franja(np.asarray(hora_local)[ok])
    filas = [{"agrupacion": "total", "grupo": "total", **_calibracion_grupo(y, a, b, c, alfa)}]
    if len(y) >= 10:
        decil = pd.qcut(pd.Series(b).rank(method="first"), 10, labels=False).to_numpy()
        for d in range(10):
            s = decil == d
            filas.append({"agrupacion": "decil_prediccion", "grupo": f"D{d + 1}",
                          **_calibracion_grupo(y[s], a[s], b[s], c[s], alfa)})
    for cod in np.unique(mz):
        s = mz == cod
        filas.append({"agrupacion": "macrozona", "grupo": NOMBRE_MACROZONA.get(int(cod), str(cod)),
                      **_calibracion_grupo(y[s], a[s], b[s], c[s], alfa)})
    for f in (0, 1):
        s = fr == f
        if s.any():
            filas.append({"agrupacion": "franja", "grupo": NOMBRE_FRANJA[f], **_calibracion_grupo(y[s], a[s], b[s], c[s], alfa)})
    return pd.DataFrame(filas)


def metricas_alerta(obs, q80, macrozona, hora_local, tau: float = 0.8) -> pd.DataFrame:
    """El cuantil 0,80 de alertas, aparte (§3): tasa de observaciones bajo el cuantil (nominal 0,80), pinball y
    fracción de excedencias, en total, por decil de la predicción, macrozona y franja."""
    y, q = np.asarray(obs, dtype="float64"), np.asarray(q80, dtype="float64")
    ok = np.isfinite(y) & np.isfinite(q)
    y, q = y[ok], q[ok]
    mz = np.asarray(macrozona)[ok]
    fr = franja(np.asarray(hora_local)[ok])

    def fila(s, agr, grupo):
        return {"agrupacion": agr, "grupo": grupo, "n": int(s.sum()), "tasa_bajo_cuantil": float(np.mean(y[s] <= q[s])),
                "nominal": tau, "pinball": float(np.mean(pinball_perdida(y[s], q[s], tau))),
                "media_cuantil": float(np.mean(q[s])), "media_obs": float(np.mean(y[s]))}

    filas = [fila(np.ones(len(y), dtype=bool), "total", "total")]
    if len(y) >= 10:
        decil = pd.qcut(pd.Series(q).rank(method="first"), 10, labels=False).to_numpy()
        filas += [fila(decil == d, "decil_prediccion", f"D{d + 1}") for d in range(10)]
    filas += [fila(mz == c, "macrozona", NOMBRE_MACROZONA.get(int(c), str(c))) for c in np.unique(mz)]
    filas += [fila(fr == f, "franja", NOMBRE_FRANJA[f]) for f in (0, 1) if (fr == f).any()]
    return pd.DataFrame(filas)
