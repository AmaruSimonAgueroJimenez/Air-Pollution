"""Métricas de la comparación v2 (``DISENO_AMBIENTAL_V2.md`` §6 y §8, con la Enmienda 1, puntos 4, 7 y 10).

**Pares de evaluación.** Antes de agregar se impone en el código la intersección de las predicciones finitas
de todos los motores (§4): ``pares_comunes``. Con ``motores`` se impone sólo entre ellos (los pares de la
decisión, punto 11) y se informa cuántos pares quitaría cada familia del resto.

**Niveles** (§8):

* ``horario``: cada par estación × hora;
* ``diario_civil``: estación × día civil de America/Santiago (con horario de verano), con al menos 18 horas;
* ``diario_utc4``: estación × día del reloj UTC−4 fijo (la ``fecha_local`` del panel, ``_features.py:119-130``),
  con al menos 18 horas, como la v1 (``qmd:2587-2589``);
* ``mensual``: estación × mes del día civil, con al menos 20 días civiles válidos (ratificado, punto 1.10);
* ``anual``: estación × año, con al menos 9 meses válidos (ratificado, punto 1.10).

La hora de una fila es la del inicio de su bin UTC (``ts_utc``), como en la ``fecha_local`` de la v1.

**Escalas.** «original»: la predicción en µg/m³ o ppb contra lo observado. «log»: ``ẑ`` (la salida del motor
antes de la retransformación; en los motores de escala original, ``log1p(máx(ŷ, 0))``) contra ``log1p(y)``,
promediados en log en cada nivel. Así se separa el motor de la corrección (§5).

**Desagregaciones** (§8 y punto 10):

* total, macrozona y estación;
* ``regimen``: los cinco regímenes de predictores por disponibilidad (2000-2002, 2003-2018, 2019-2024, 2025 y
  2026) según el año local de cada par (``REGIMENES``, que es el valor de la configuración);
* ``regimen_fila_a_fila`` (sensibilidad): la combinación de familias de predictores disponibles en cada fila
  (``disponibilidad_fila_a_fila``, con la regla provisional de la configuración). En los niveles agregados, la
  combinación más frecuente entre sus horas;
* ``periodo_lpo`` (sólo LPO): los cuatrienios de LPO con 2024 aparte de 2025-2026 (``periodos_lpo``);
* estrato de soporte: cuartiles de ``peso_vec`` y de ``dist_est_km`` de los pares horarios de evaluación, con los
  valores recalculados en el pliegue; en los niveles agregados, la media de las horas.

Los regímenes son descriptivos: no alteran el §9.

**Ponderación** (punto 4). El peso de decisión, «poblacion», es **fijo por estación**: la mediana sobre sus años
de la ``pob_dens`` de su celda (``peso_fijo_por_estacion``). Así, los saltos del ráster entre versiones (2013, 2017
y 2022) no cambian el peso. ``nivel_horario`` lo fija a partir de las filas que recibe, que deben ser todas las del
panel (las del protocolo) y no sólo los pares evaluados; los niveles agregados heredan el peso de su estación. La
sensibilidad «desagrupamiento» (``peso_desagrupamiento``) es la población de la comuna dividida por las estaciones
de la red en ella. La población comunal sale de las proyecciones del INE que la v1 usó para construir ``pob_dens``
(``CITA_POBLACION_COMUNAL``). Se ponderan el total, la macrozona y el régimen; como lectura, también la
sensibilidad fila a fila del régimen y los períodos de LPO, que son desagregaciones del régimen. Junto a cada
métrica se informan el número de estaciones y de bloques con pares, el número efectivo de estaciones de Kish y el G
efectivo, ``(Σ W)² / Σ W²`` con W el peso total por estación o por bloque (sin ponderar, W es el número de pares).
El bloque es el de la inferencia del protocolo (``Nivel.bloque``; si no se da, el grupo del pliegue).

**Conjuntos de evaluación** (punto 7):

* E1: todos los pares;
* E2: los pares validados, con el ``usable_native`` de SNIFA;
* E2-SINCA: los validados de SINCA, sin SNIFA;
* E1′: todos los pares de las estaciones con algún par en E2, para separar calidad de composición.

Cada conjunto es una máscara horaria: en los niveles agregados, un día de E2 exige 18 horas de E2.
``registro_conjuntos`` lista los pliegues y las estaciones sin E2. ``evaluabilidad_e2`` aplica la regla de un
protocolo: E2 es evaluable si conserva ≥ 50 % del peso de E1 y tiene ≥ 5 grupos del protocolo con pares E2, ambos
en el nivel diario civil y con los pesos fijos. Si no, no bloquea y se informa «sin confirmación con datos
validados».

**Métricas** en escala original (§6): R² = 1 − SSE/SST (agrupado, como ``metricas`` de la v1, ``qmd:2580``; NaN
con menos de 3 pares o SST nula), RMSE, MAE, NMB = Σ(p − o)/Σo, sesgo medio y r de Pearson; con pesos, las mismas
en su versión ponderada. Se calculan con sumas por grupo (``numpy.bincount``): exacto y rápido.

**Cuantiles** (§6): cobertura del intervalo del 90 %, puntaje de intervalo y calibración por decil de la
predicción mediana, macrozona y franja. **Alertas** (§3): el cuantil 0,80 se juzga aparte.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from perdidas_v2 import pinball_perdida, puntaje_intervalo
from retransformacion_v2 import NOMBRE_FRANJA, franja, valor_config

ZONA_CIVIL = "America/Santiago"
OFFSET_UTC4_H = 4
NS_DIA = 86_400_000_000_000
NIVELES = ("horario", "diario_civil", "diario_utc4", "mensual", "anual")
MINIMO_HORAS_DIA = 18
MINIMO_DIAS_MES = 20                # ratificado (Enmienda 1, punto 1.10)
MINIMO_MESES_ANIO = 9               # ratificado (Enmienda 1, punto 1.10)
NOMBRE_MACROZONA = {0: "norte_grande", 1: "norte_chico", 2: "centro", 3: "sur", 4: "austral", 5: "sin_region",
                    6: "insular"}                                         # _comun_modelo.py:88-89
COLUMNAS_METRICAS = ["n", "peso", "media_obs", "media_pred", "r2", "rmse", "mae", "nmb", "sesgo", "r"]
COLUMNAS_EFECTIVOS = ["estaciones", "estaciones_kish", "G", "G_efectivo"]
DESAGREGACIONES = ("total", "macrozona", "estacion", "regimen", "soporte_peso_vec", "soporte_dist_est_km")
PONDERABLES = ("total", "macrozona", "regimen", "regimen_fila_a_fila", "periodo_lpo")
PESO_FIJO = "poblacion"                       # nombre de la ponderación de decisión en las tablas
DESAGRUPAMIENTO = "desagrupamiento"           # nombre de la sensibilidad de ponderación

# Regímenes de predictores (Enmienda 1, punto 10; config: metricas.desagregaciones.regimen_de_predictores.criterio).
REGIMENES = (
    {"id": "2000-2002", "anios": (2000, 2002), "disponibilidad": "sin CAMS"},
    {"id": "2003-2018", "anios": (2003, 2018), "disponibilidad": "sin GEOS-CF ni TROPOMI"},
    {"id": "2019-2024", "anios": (2019, 2024), "disponibilidad": "con GEOS-CF y con TROPOMI en ~70 % de las filas"},
    {"id": "2025", "anios": (2025, 2025), "disponibilidad": "sin GEOS-CF ni TROPOMI y con ACAG climatológico"},
    {"id": "2026", "anios": (2026, 2026), "disponibilidad": "además sin CAMS y con MERRA-2 y BLH incompletos"},
)
FAMILIAS_INDICADORAS = ("acag_climatologico",)    # disponible si su columna vale 1 (regla provisional)
LPO_ANIO_APARTE = 2024                            # punto 10: en LPO, 2024 aparte de 2025-2026

# Conjuntos de evaluación (Enmienda 1, punto 7; config: calidad_blanco.evaluacion).
E1, E2, E2_SINCA, E1_PRIMA = "E1", "E2", "E2-SINCA", "E1′"
CONJUNTOS = (E1, E2, E2_SINCA, E1_PRIMA)
CODIGOS_E2 = ("validado", "usable_native")
CODIGOS_E2_SINCA = ("validado",)
MINIMO_FRACCION_PESO_E2 = 0.5
MINIMO_GRUPOS_E2 = 5
SIN_CONFIRMACION = "sin confirmación con datos validados"

# Población comunal para el peso de desagrupamiento (Enmienda 1, punto 4).
INSUMO_POBLACION_COMUNAL = "censo_proyecciones_ano_edad_genero.parquet"
CITA_POBLACION_COMUNAL = (
    "Proyecciones de población del INE por comuna, año, edad y sexo (base 2017; años 2002-2035): "
    "censo_proyecciones_ano_edad_genero.parquet en la raíz de datos de AirPollution (RutasV2.datos), en sólo "
    "lectura. Es el insumo con que la v1 construyó pob_dens: poblacion_comunal_por_anio(), "
    "scripts_modelo_1km/covariables_estaticas.py:121-126 (suma de edades y sexos por comuna × año).")


# ---------------------------------------------------------------------------
# Pares comunes
# ---------------------------------------------------------------------------
def pares_comunes(obs, predicciones: Mapping[str, np.ndarray], motores: Sequence[str] | None = None,
                  familias: Mapping[str, Sequence[str]] | None = None) -> tuple[np.ndarray, dict]:
    """Máscara de los pares con observación finita y predicción finita **en todos** los motores, y cuántos pares
    quita cada motor (la intersección se impone antes de agregar, §4).

    Con ``motores``, la intersección se impone sólo entre ellos (los pares de la decisión, punto 11) e
    ``info["quita_por_familia"]`` dice cuántos de esos pares quitaría cada familia (``familias``: nombre → motores;
    por omisión, cada motor fuera de ``motores`` es su propia familia)."""
    o = np.asarray(obs, dtype="float64")
    ok = np.isfinite(o)
    info = {"filas": int(len(o)), "obs_no_finita": int((~ok).sum()), "no_finitas_por_motor": {}}
    finitas = {}
    for nombre, p in predicciones.items():
        p = np.asarray(p, dtype="float64")
        if p.shape != o.shape:
            raise ValueError(f"{nombre}: la predicción no tiene una entrada por par")
        finitas[nombre] = np.isfinite(p)
        info["no_finitas_por_motor"][nombre] = int((~finitas[nombre]).sum())
    base = list(predicciones) if motores is None else list(motores)
    faltan = [m for m in base if m not in finitas]
    if faltan:
        raise ValueError(f"no hay predicciones de {faltan}")
    for nombre in base:
        ok &= finitas[nombre]
    info["pares_comunes"] = int(ok.sum())
    if motores is not None:
        info["motores_de_la_interseccion"] = base
        resto = [m for m in predicciones if m not in base]
        fam = {m: [m] for m in resto} if familias is None else {k: list(v) for k, v in familias.items()}
        quita = {}
        for nombre, miembros in fam.items():
            malo = np.zeros(len(o), dtype=bool)
            for m in miembros:
                if m in finitas:
                    malo |= ~finitas[m]
            quita[nombre] = int((ok & malo).sum())
        info["quita_por_familia"] = quita
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
# Números efectivos (punto 4)
# ---------------------------------------------------------------------------
def n_efectivo(totales) -> float:
    """``(Σ W)² / Σ W²`` de los totales positivos (Kish con W por estación; G efectivo con W por bloque)."""
    t = np.asarray(totales, dtype="float64")
    t = t[np.isfinite(t) & (t > 0)]
    return float(t.sum() ** 2 / (t * t).sum()) if len(t) else float("nan")


def _efectivos(g: np.ndarray, ng: int, ids: np.ndarray, w: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Por grupo de la desagregación: cuántas unidades (estaciones o bloques) tienen peso y su número efectivo."""
    if len(ids) == 0:
        return np.zeros(ng, dtype="int64"), np.full(ng, np.nan)
    u, cod = np.unique(ids, return_inverse=True)
    m = len(u)
    W = np.bincount(g * m + cod.ravel(), weights=w, minlength=ng * m).reshape(ng, m)
    s, s2 = W.sum(axis=1), (W * W).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        eff = np.where(s2 > 0, s * s / s2, np.nan)
    return (W > 0).sum(axis=1).astype("int64"), eff


# ---------------------------------------------------------------------------
# Pesos fijos por estación y de desagrupamiento (punto 4)
# ---------------------------------------------------------------------------
def _codigos(estacion) -> np.ndarray:
    e = np.asarray(estacion)
    if np.issubdtype(e.dtype, np.integer):
        e = e.astype("int64")
        if len(e) and e.min() < 0:
            raise ValueError("los códigos de estación deben ser ≥ 0")
        return e
    return np.unique(e, return_inverse=True)[1].ravel().astype("int64")


def peso_fijo_por_estacion(estacion, anio, pob_dens) -> np.ndarray:
    """Peso fijo de cada estación (punto 4), indexado por su código: la mediana, sobre los años con filas de la
    estación, de su ``pob_dens`` anual (la mediana de sus filas del año; en los paneles v1 es constante dentro de
    estación × año). Cada año cuenta una vez. NaN si la estación no tiene ninguna ``pob_dens`` finita."""
    est = _codigos(estacion)
    a = np.asarray(anio, dtype="int64")
    p = np.asarray(pob_dens, dtype="float64")
    if not (len(est) == len(a) == len(p)):
        raise ValueError("estacion, anio y pob_dens deben tener una entrada por fila")
    S = int(est.max()) + 1 if len(est) else 0
    out = np.full(S, np.nan)
    ok = np.isfinite(p)
    if ok.any():
        anual = pd.DataFrame({"e": est[ok], "a": a[ok], "p": p[ok]}).groupby(["e", "a"], sort=True)["p"].median()
        por_est = anual.groupby(level=0).median()
        out[por_est.index.to_numpy(dtype="int64")] = por_est.to_numpy(dtype="float64")
    return out


def ruta_poblacion_comunal(datos) -> Path:
    """Ruta del insumo de población comunal dentro de la raíz de datos de AirPollution (``RutasV2.datos``)."""
    return Path(datos) / INSUMO_POBLACION_COMUNAL


def leer_poblacion_comunal(ruta) -> pd.DataFrame:
    """Población total por comuna × año (``cod_comuna``, ``anio``, ``poblacion``), en sólo lectura: réplica de
    ``poblacion_comunal_por_anio`` (``scripts_modelo_1km/covariables_estaticas.py:121-126``), que suma edades y
    sexos de las proyecciones del INE (``CITA_POBLACION_COMUNAL``)."""
    c = pd.read_parquet(ruta, columns=["cut_comuna", "año", "población"])
    c = c.rename(columns={"cut_comuna": "cod_comuna", "año": "anio", "población": "poblacion"})
    c = c.dropna(subset=["cod_comuna", "anio"])
    out = c.groupby(["cod_comuna", "anio"], as_index=False)["poblacion"].sum()
    return (out.astype({"cod_comuna": "int64", "anio": "int64", "poblacion": "float64"})
            .sort_values(["cod_comuna", "anio"], kind="stable").reset_index(drop=True))


def comunas_de_manifiesto(manifiesto: Mapping, estaciones: Sequence) -> np.ndarray:
    """``cod_comuna`` de cada estación de ``estaciones`` (en ese orden) según el universo de estaciones de
    ``pliegues_v2.json``; −1 si no tiene comuna."""
    de = {str(e["estacion"]): e.get("cod_comuna") for e in manifiesto["estaciones"]}
    return np.array([-1 if de.get(str(s)) is None else int(de[str(s)]) for s in estaciones], dtype="int64")


def peso_desagrupamiento(estacion, anio, comuna_de_estacion, poblacion_comunal: pd.DataFrame,
                         nombres_estacion=None) -> tuple[np.ndarray, pd.DataFrame]:
    """Peso de desagrupamiento de cada estación (sensibilidad del punto 4), indexado por su código.

    Provisional de la configuración (``…desagrupamiento.poblacion_comunal``): la población total INE de la comuna
    de la estación, como mediana sobre los años con filas de la estación (un año sin dato INE toma el más cercano;
    en un empate, el anterior), dividida por el número de estaciones del panel del contaminante, de las dos redes,
    en esa comuna. Las filas que recibe deben ser todas las del panel del contaminante: las estaciones que cuentan
    son las que tienen filas. ``comuna_de_estacion``: ``cod_comuna`` por código de estación
    (``comunas_de_manifiesto``). Devuelve el peso por estación (NaN si no tiene filas) y una tabla por estación."""
    est = _codigos(estacion)
    a = np.asarray(anio, dtype="int64")
    com = np.asarray(comuna_de_estacion, dtype="int64")
    presentes = np.unique(est)
    if len(presentes) and presentes.max() >= len(com):
        raise ValueError("hay códigos de estación sin entrada en comuna_de_estacion")
    sin = [int(s) for s in presentes if com[s] < 0]
    if sin:
        raise ValueError(f"estaciones sin comuna (códigos): {sin}")
    pc = poblacion_comunal
    por_comuna = {int(c): (g["anio"].to_numpy(dtype="int64"), g["poblacion"].to_numpy(dtype="float64"))
                  for c, g in pc.groupby("cod_comuna")}
    faltan = sorted({int(com[s]) for s in presentes} - set(por_comuna))
    if faltan:
        raise ValueError(f"comunas sin población en el insumo INE: {faltan}")
    pares = np.unique(est * 10_000 + a)                     # (estación, año) con filas
    anios_de = {}
    for v in pares:
        anios_de.setdefault(int(v // 10_000), []).append(int(v % 10_000))
    n_comuna = pd.Series(com[presentes]).value_counts().to_dict()
    peso = np.full(len(com), np.nan)
    filas = []
    for s in presentes:
        anios_c, pob_c = por_comuna[int(com[s])]
        orden = np.argsort(anios_c, kind="stable")
        anios_c, pob_c = anios_c[orden], pob_c[orden]
        valores, sustituidos = [], []
        for y in anios_de[int(s)]:
            d = np.abs(anios_c - y)
            j = int(np.flatnonzero(d == d.min())[0])          # el más cercano; en un empate, el anterior
            valores.append(float(pob_c[j]))
            if int(anios_c[j]) != y:
                sustituidos.append(f"{y}→{int(anios_c[j])}")
        mediana = float(np.median(valores))
        n_c = int(n_comuna[int(com[s])])
        peso[s] = mediana / n_c
        filas.append({"estacion": int(s) if nombres_estacion is None else str(nombres_estacion[int(s)]),
                      "cod_comuna": int(com[s]), "anios": len(anios_de[int(s)]),
                      "anios_sustituidos": ", ".join(sustituidos), "poblacion_mediana": mediana,
                      "estaciones_en_la_comuna": n_c, "peso": float(peso[s])})
    return peso, pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# Regímenes de predictores y períodos de LPO (punto 10)
# ---------------------------------------------------------------------------
def _normalizar_regimenes(regimenes) -> tuple:
    if (isinstance(regimenes, (tuple, list)) and len(regimenes) == 2
            and all(isinstance(x, (int, np.integer)) for x in regimenes)):
        raise ValueError("la Enmienda 1 (punto 10) reemplaza el régimen binario (a0, a1) por cinco regímenes: usa "
                         "regimenes_de_config(cfg) o REGIMENES")
    out = []
    for r in regimenes:
        a0, a1 = (int(x) for x in r["anios"])
        if a1 < a0:
            raise ValueError(f"régimen {r.get('id')}: años invertidos")
        out.append({"id": str(r["id"]), "anios": (a0, a1), "disponibilidad": str(r.get("disponibilidad", ""))})
    out.sort(key=lambda r: r["anios"][0])
    for x, y in zip(out, out[1:]):
        if y["anios"][0] <= x["anios"][1]:
            raise ValueError(f"regímenes solapados: {x['id']} y {y['id']}")
    return tuple(out)


def regimenes_de_config(cfg: dict) -> tuple:
    """Los regímenes de ``metricas.desagregaciones.regimen_de_predictores.criterio`` (valor vigente)."""
    c = cfg["metricas"]["desagregaciones"]["regimen_de_predictores"]["criterio"]
    return _normalizar_regimenes(valor_config(c, "metricas.desagregaciones.regimen_de_predictores.criterio"))


def regimen_de_anio(anio, regimenes=REGIMENES) -> np.ndarray:
    """Índice del régimen de cada año (−1 si ningún régimen lo cubre)."""
    regs = _normalizar_regimenes(regimenes)
    a = np.asarray(anio, dtype="int64")
    out = np.full(a.shape, -1, dtype="int64")
    for i, r in enumerate(regs):
        out[(a >= r["anios"][0]) & (a <= r["anios"][1])] = i
    return out


def etiquetas_regimen(regimenes=REGIMENES) -> list[str]:
    return [f"{r['id']}: {r['disponibilidad']}" if r["disponibilidad"] else r["id"]
            for r in _normalizar_regimenes(regimenes)]


def familias_de_config(cfg: dict) -> dict:
    """Familias de predictores de la sensibilidad fila a fila (pendiente: su provisional)."""
    nodo = cfg["metricas"]["desagregaciones"]["regimen_de_predictores"]["sensibilidad"]["fila_a_fila"]
    v = valor_config(nodo, "metricas.desagregaciones.regimen_de_predictores.sensibilidad.fila_a_fila")
    return {str(k): [str(c) for c in cols] for k, cols in v["familias"].items()}


def disponibilidad_fila_a_fila(columnas: Mapping[str, np.ndarray], familias: Mapping[str, Sequence[str]],
                               indicadoras: Sequence[str] = FAMILIAS_INDICADORAS) -> tuple[np.ndarray, list, dict]:
    """Régimen fila a fila (sensibilidad del punto 10), con la regla provisional de la configuración: una familia
    está disponible en una fila si alguna de sus columnas es finita (en las ``indicadoras``, ACAG climatológico,
    si alguna vale 1); el régimen es la combinación de familias disponibles. Una columna que no viene en
    ``columnas`` cuenta como no disponible y queda registrada. Devuelve el código por fila (0 … m − 1, en el orden
    de la máscara de bits de las familias), las etiquetas («cams+merra2», o «ninguna») y un registro."""
    nombres = list(familias)
    longitudes = {len(np.asarray(v)) for v in columnas.values()}
    if len(longitudes) != 1:
        raise ValueError("las columnas deben tener una entrada por fila")
    n = longitudes.pop()
    bits = np.zeros(n, dtype="int64")
    info = {"familias": nombres, "regla": "alguna columna finita; indicadoras: alguna columna = 1",
            "columnas_ausentes": {}, "filas_con_familia": {}}
    for i, fam in enumerate(nombres):
        disp = np.zeros(n, dtype=bool)
        ausentes = [c for c in familias[fam] if c not in columnas]
        for c in familias[fam]:
            if c in columnas:
                v = np.asarray(columnas[c], dtype="float64")
                disp |= (v == 1.0) if fam in indicadoras else np.isfinite(v)
        if ausentes:
            info["columnas_ausentes"][fam] = ausentes
        info["filas_con_familia"][fam] = int(disp.sum())
        bits |= disp.astype("int64") << i
    u, cod = np.unique(bits, return_inverse=True)
    cod = cod.ravel().astype("int64")
    etiquetas = ["+".join(f for i, f in enumerate(nombres) if (int(b) >> i) & 1) or "ninguna" for b in u]
    info["filas_por_regimen"] = dict(zip(etiquetas, (int(x) for x in np.bincount(cod, minlength=len(u)))))
    return cod, etiquetas, info


def periodos_lpo(anio_desde: int = 2000, anio_hasta: int = 2026, largo: int = 4,
                 aparte: int | None = LPO_ANIO_APARTE) -> tuple:
    """Cuatrienios de LPO (como ``pliegues_v2.ventana_de``) con el año ``aparte`` separado del resto de su ventana
    (punto 10: 2024 aparte de 2025-2026). Cada período es ``(etiqueta, desde, hasta)``."""
    out = []
    for a in range(int(anio_desde), int(anio_hasta) + 1, int(largo)):
        b = min(a + int(largo) - 1, int(anio_hasta))
        partes = [(a, aparte - 1), (aparte, aparte), (aparte + 1, b)] if aparte is not None and a <= aparte <= b \
            else [(a, b)]
        out += [(f"{x}" if x == y else f"{x}–{y}", x, y) for x, y in partes if x <= y]
    return tuple(out)


def periodos_lpo_de_config(cfg: dict, aparte: int | None = LPO_ANIO_APARTE) -> tuple:
    v = cfg["protocolos"]["LPO"]["ventanas"]
    return periodos_lpo(int(v["anio_desde"]), int(v["anio_hasta"]), int(v["largo_anios"]), aparte)


def periodo_de_anio(anio, periodos) -> np.ndarray:
    a = np.asarray(anio, dtype="int64")
    out = np.full(a.shape, -1, dtype="int64")
    for i, (_, x, y) in enumerate(periodos):
        out[(a >= x) & (a <= y)] = i
    return out


# ---------------------------------------------------------------------------
# Conjuntos de evaluación (punto 7)
# ---------------------------------------------------------------------------
def codigos_evaluacion_de_config(cfg: dict) -> dict:
    """Códigos de E2 y E2-SINCA de ``calidad_blanco.evaluacion.conjuntos`` (E2 = codigos_qc → evaluacion_validadas)."""
    c = cfg["calidad_blanco"]["evaluacion"]["conjuntos"]
    e2 = [str(x) for x in c[E2]["codigos"]]
    validadas = valor_config(cfg["calidad_blanco"]["codigos_qc"], "calidad_blanco.codigos_qc")["evaluacion_validadas"]
    if sorted(e2) != sorted(validadas):
        raise ValueError("los códigos de E2 no coinciden con codigos_qc → evaluacion_validadas")
    return {E2: tuple(e2), E2_SINCA: tuple(str(x) for x in c[E2_SINCA]["codigos"])}


def evaluabilidad_de_config(cfg: dict) -> dict:
    ev = cfg["calidad_blanco"]["evaluacion"]["evaluabilidad"]
    return {"minimo_fraccion": float(ev["minimo_fraccion_del_peso_de_E1"]),
            "minimo_grupos": int(ev["minimo_grupos_con_filas_E2"])}


def conjuntos_evaluacion(comunes, calidad, estacion, codigos: Mapping[str, Sequence[str]] | None = None) -> dict:
    """Máscaras horarias de E1, E2, E2-SINCA y E1′ sobre los pares ``comunes`` (punto 7). ``calidad``: código de
    la bandera de cada fila (``calidad_v2``; nulo = sin bandera). E1′ son todos los pares de las estaciones con al
    menos un par en E2."""
    if calidad is None:
        raise ValueError("sin la bandera de calidad (calidad_v2) no hay E2, E2-SINCA ni E1′: sólo E1")
    m = np.asarray(comunes, dtype=bool)
    codigos = codigos or {E2: CODIGOS_E2, E2_SINCA: CODIGOS_E2_SINCA}
    q = np.asarray(calidad, dtype=object).astype(str)
    est = np.asarray(estacion)
    if not (len(q) == len(est) == len(m)):
        raise ValueError("comunes, calidad y estacion deben tener una entrada por fila")
    e2 = m & np.isin(q, list(codigos[E2]))
    e2s = m & np.isin(q, list(codigos[E2_SINCA]))
    e1p = m & np.isin(est, np.unique(est[e2]))
    return {E1: m, E2: e2, E2_SINCA: e2s, E1_PRIMA: e1p}


def registro_conjuntos(conjuntos: Mapping[str, np.ndarray], estacion, pliegue, nombres_estacion=None) -> dict:
    """Pares, estaciones y pliegues de cada conjunto, y los pliegues y las estaciones con pares en E1 que no tienen
    ninguno en E2 (o en E2-SINCA). ``pliegue``: el pliegue de prueba de cada fila."""
    est = np.asarray(estacion)
    pl = np.asarray(pliegue, dtype="int64")

    def nombre(s):
        return str(nombres_estacion[int(s)]) if nombres_estacion is not None else s.item() if hasattr(s, "item") else s

    out = {"pares": {}, "estaciones": {}, "pliegues": {}}
    for c, m in conjuntos.items():
        out["pares"][c] = int(np.asarray(m).sum())
        out["estaciones"][c] = int(len(np.unique(est[m])))
        out["pliegues"][c] = int(len(np.unique(pl[m])))
    base = conjuntos[E1]
    for c in (E2, E2_SINCA):
        if c not in conjuntos:
            continue
        sin_est = np.setdiff1d(np.unique(est[base]), np.unique(est[conjuntos[c]]))
        sin_pl = np.setdiff1d(np.unique(pl[base]), np.unique(pl[conjuntos[c]]))
        out[f"estaciones_sin_{c}"] = [nombre(s) for s in sin_est]
        out[f"pliegues_sin_{c}"] = [int(k) for k in sin_pl]
    return out


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
    """Para cada agregado, el código (≥ 0) más frecuente entre sus horas; empate: el menor código."""
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
    """Pares de un nivel: observado y predicho (por motor) en escala original y log, con sus atributos.

    ``poblacion`` es el peso fijo de la estación de cada par (punto 4); ``pesos_extra`` lleva las sensibilidades de
    ponderación (``desagrupamiento``), también fijas por estación. ``grupo`` es el pliegue de prueba y ``bloque`` el
    bloque de inferencia del protocolo (por omisión, el grupo). ``estratos`` lleva desagregaciones categóricas
    adicionales por par (``regimen_fila_a_fila``), con sus nombres en ``etiquetas``."""

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
    bloque: np.ndarray = field(default=None)
    pesos_extra: dict = field(default_factory=dict)
    estratos: dict = field(default_factory=dict)
    etiquetas: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.bloque is None:
            self.bloque = np.asarray(self.grupo, dtype="int64").copy()


def _agregar(base: Nivel, clave: np.ndarray, minimo: int, nombre: str, anio_de=None) -> tuple[Nivel, np.ndarray]:
    """Promedio por ``clave`` (estación × período) de todas las series de ``base``, con al menos ``minimo``
    unidades; devuelve el nivel y la clave de cada agregado. Los pesos son de la estación; el grupo, el bloque y
    los estratos, los más frecuentes entre sus horas."""
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

    def mayoritario(v):
        return _grupo_mayoritario(ids[sel], np.asarray(v)[sel], mk)

    nivel = Nivel(nombre=nombre, obs=media(base.obs), log_obs=media(base.log_obs),
                  pred={k: media(v) for k, v in base.pred.items()}, log={k: media(v) for k, v in base.log.items()},
                  estacion=primero(base.estacion), macrozona=primero(base.macrozona),
                  anio=primero(base.anio) if anio_de is None else anio_de(u[keep]),
                  peso_vec=media(base.peso_vec), dist_est_km=media(base.dist_est_km),
                  poblacion=primero(base.poblacion), grupo=mayoritario(base.grupo),
                  unidades=cuenta[keep].astype("int64"), bloque=mayoritario(base.bloque),
                  pesos_extra={k: primero(v) for k, v in base.pesos_extra.items()},
                  estratos={k: mayoritario(v) for k, v in base.estratos.items()}, etiquetas=dict(base.etiquetas))
    return nivel, u[keep]


def niveles(base: Nivel, ts_utc, minimo_horas: int = MINIMO_HORAS_DIA, minimo_dias: int = MINIMO_DIAS_MES,
            minimo_meses: int = MINIMO_MESES_ANIO) -> dict[str, Nivel]:
    """Los cinco niveles de §8 a partir del nivel horario (ya restringido a los pares comunes)."""
    est = _codigos(base.estacion)
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


def _por_estacion_constante(cod: np.ndarray, w: np.ndarray, nombre: str) -> None:
    """Exige que un peso sea constante dentro de cada estación."""
    if len(w) == 0:
        return
    g = pd.DataFrame({"e": cod, "w": w}).groupby("e")["w"]
    mn, mx = g.min().to_numpy(), g.max().to_numpy()
    if (mx - mn > 1e-9 * np.maximum(np.maximum(np.abs(mn), np.abs(mx)), 1.0)).any():
        raise ValueError(f"el peso {nombre!r} no es fijo por estación (punto 4)")


def nivel_horario(obs, pred: Mapping[str, np.ndarray], z: Mapping[str, np.ndarray | None], estacion, macrozona, anio,
                  peso_vec, dist_est_km, poblacion, grupo, mascara=None, *, bloque=None,
                  pesos_extra: Mapping[str, np.ndarray] | None = None,
                  estratos: Mapping[str, tuple] | None = None) -> Nivel:
    """Nivel horario restringido a ``mascara`` (los pares comunes y, si se pide, un conjunto de evaluación).

    Todas las entradas tienen una entrada por fila del panel del protocolo. ``poblacion`` es la ``pob_dens`` de la
    celda de la estación en cada fila: el peso fijo (mediana de sus años, punto 4) se calcula aquí con **todas** las
    filas recibidas, antes de aplicar la máscara, de modo que no depende del conjunto evaluado. ``pesos_extra``
    (por ejemplo ``{"desagrupamiento": w}``) deben ser ya fijos por estación. ``bloque``: bloque de inferencia de
    cada fila (por omisión, ``grupo``). ``estratos``: ``{nombre: (código por fila, etiquetas)}``."""
    m = np.ones(len(obs), dtype=bool) if mascara is None else np.asarray(mascara, dtype=bool)
    o = np.asarray(obs, dtype="float64")[m]
    cod = _codigos(estacion)
    fijo = peso_fijo_por_estacion(cod, anio, poblacion)[cod]
    if not np.isfinite(fijo[m]).all():
        sin = np.unique(np.asarray(estacion)[m][~np.isfinite(fijo[m])])
        raise ValueError(f"estaciones sin pob_dens finita para el peso fijo: {sin.tolist()}")
    extra = {}
    for nombre, w in (pesos_extra or {}).items():
        w = np.asarray(w, dtype="float64")
        if len(w) != len(m):
            raise ValueError(f"el peso {nombre!r} no tiene una entrada por fila")
        if not np.isfinite(w[m]).all():
            raise ValueError(f"el peso {nombre!r} no es finito en todos los pares")
        _por_estacion_constante(cod[m], w[m], nombre)
        extra[nombre] = w[m]
    etiquetas, cods = {}, {}
    if bloque is not None:
        b = np.asarray(bloque)
        if np.issubdtype(b.dtype, np.integer) and (len(b) == 0 or b.min() >= 0):
            cods_b = b.astype("int64")
        else:
            ub, cods_b = np.unique(b, return_inverse=True)
            cods_b = cods_b.ravel().astype("int64")
            etiquetas["bloque"] = [str(x) for x in ub]
        bloque = cods_b[m]
    for nombre, (c, etq) in (estratos or {}).items():
        c = np.asarray(c, dtype="int64")
        if len(c) != len(m) or (c[m] < 0).any():
            raise ValueError(f"el estrato {nombre!r} necesita un código ≥ 0 por fila")
        cods[nombre] = c[m]
        etiquetas[nombre] = list(etq)
    return Nivel(nombre="horario", obs=o, log_obs=np.log1p(np.clip(o, 0.0, None)),
                 pred={k: np.asarray(v, dtype="float64")[m] for k, v in pred.items()},
                 log={k: log_de(pred[k], None if z.get(k) is None else z[k])[m] for k in pred},
                 estacion=np.asarray(estacion)[m], macrozona=np.asarray(macrozona)[m],
                 anio=np.asarray(anio, dtype="int64")[m], peso_vec=np.asarray(peso_vec, dtype="float64")[m],
                 dist_est_km=np.asarray(dist_est_km, dtype="float64")[m], poblacion=fijo[m],
                 grupo=np.asarray(grupo, dtype="int64")[m], unidades=np.ones(int(m.sum()), dtype="int64"),
                 bloque=bloque, pesos_extra=extra, estratos=cods, etiquetas=etiquetas)


def resumen_niveles(nvs: Mapping[str, Nivel]) -> dict:
    return {k: {"pares": int(len(v.obs)), "estaciones": int(len(np.unique(v.estacion))),
                "bloques": int(len(np.unique(v.bloque)))} for k, v in nvs.items()}


# ---------------------------------------------------------------------------
# Evaluabilidad de E2 (punto 7)
# ---------------------------------------------------------------------------
def evaluabilidad_e2(nivel_e1: Nivel, nivel_e2: Nivel, minimo_fraccion: float = MINIMO_FRACCION_PESO_E2,
                     minimo_grupos: int = MINIMO_GRUPOS_E2) -> dict:
    """Regla de evaluabilidad de E2 en un protocolo: E2 conserva al menos ``minimo_fraccion`` del peso de E1 (pesos
    fijos por estación) y tiene pares en al menos ``minimo_grupos`` grupos del protocolo (``Nivel.grupo``: regiones
    en LRO, bloques en BLQ-75). Se aplica a los pares del nivel diario civil (lectura de la configuración); si no
    se cumple, no bloquea y se informa como «sin confirmación con datos validados»."""
    w1, w2 = float(np.sum(nivel_e1.poblacion)), float(np.sum(nivel_e2.poblacion))
    fr = w2 / w1 if w1 > 0 else float("nan")
    g1, g2 = int(len(np.unique(nivel_e1.grupo))), int(len(np.unique(nivel_e2.grupo)))
    motivo = []
    if not (fr >= minimo_fraccion):
        motivo.append(f"E2 conserva {fr:.1%} del peso de E1 (< {minimo_fraccion:.0%})")
    if g2 < minimo_grupos:
        motivo.append(f"{g2} grupos con pares E2 (< {minimo_grupos})")
    evaluable = not motivo
    return {"nivel": nivel_e1.nombre, "nivel_E2": nivel_e2.nombre, "peso_E1": w1, "peso_E2": w2,
            "fraccion_del_peso": fr, "grupos_E1": g1, "grupos_con_E2": g2, "minimo_fraccion": float(minimo_fraccion),
            "minimo_grupos": int(minimo_grupos), "evaluable": evaluable,
            "estado": "evaluable" if evaluable else SIN_CONFIRMACION, "motivo": motivo}


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


def _grupos(nivel: Nivel, desag: str, cortes: dict, regimen=REGIMENES, periodos=None) -> tuple[np.ndarray, list]:
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
        return regimen_de_anio(nivel.anio, regimen), etiquetas_regimen(regimen)
    if desag == "periodo_lpo":
        if periodos is None:
            raise ValueError("la desagregación periodo_lpo necesita los períodos de LPO (periodos_lpo)")
        return periodo_de_anio(nivel.anio, periodos), [p[0] for p in periodos]
    if desag in nivel.estratos:
        return np.asarray(nivel.estratos[desag], dtype="int64"), list(nivel.etiquetas[desag])
    if desag.startswith("soporte_"):
        variable = desag.replace("soporte_", "")
        c = cortes[variable]
        bordes = [-np.inf, *c, np.inf]
        etiquetas = [f"Q{i + 1} [{bordes[i]:.4g}, {bordes[i + 1]:.4g})" for i in range(4)]
        return estrato_cuartil(getattr(nivel, variable), c), etiquetas
    raise ValueError(f"desagregación desconocida: {desag!r}")


def tabla_metricas(nvs: Mapping[str, Nivel], cortes: dict, motores=None, desagregaciones=None,
                   ponderables=PONDERABLES, etiqueta_estacion=None, regimen=REGIMENES, periodos_lpo=None,
                   retransformacion: Mapping[str, str] | None = None) -> pd.DataFrame:
    """Tabla larga: motor × escala × nivel × desagregación × estrato × ponderación, con las métricas de §6 y, junto
    a cada una, las estaciones y los bloques con pares y sus números efectivos (Kish y G efectivo, punto 4).

    ``cortes`` = ``{"peso_vec": [...], "dist_est_km": [...]}`` (cuartiles de las filas horarias de evaluación).
    Por omisión, las desagregaciones son ``DESAGREGACIONES``, más cada estrato del nivel (``regimen_fila_a_fila``)
    y, si se dan ``periodos_lpo``, ``periodo_lpo``. Las ponderables se informan sin ponderar, con el peso fijo
    («poblacion») y con cada peso extra del nivel («desagrupamiento»). ``retransformacion`` (motor → forma) agrega
    la columna con la corrección usada. ``etiqueta_estacion`` traduce el código entero de estación a su nombre."""
    filas = []
    for nombre_nivel, nv in nvs.items():
        lista = list(nv.pred) if motores is None else [m for m in motores if m in nv.pred]
        desags = desagregaciones
        if desags is None:
            desags = (*DESAGREGACIONES, *nv.estratos, *(("periodo_lpo",) if periodos_lpo is not None else ()))
        cod_est = _codigos(nv.estacion)
        cod_bloque = np.asarray(nv.bloque, dtype="int64")
        for desag in desags:
            g, etiquetas = _grupos(nv, desag, cortes, regimen, periodos_lpo)
            ng = len(etiquetas)
            if desag == "estacion" and etiqueta_estacion is not None:
                etiquetas = [etiqueta_estacion(int(e)) for e in etiquetas]
            sel = np.asarray(g) >= 0
            gs = np.asarray(g, dtype="int64")[sel]
            ponds = ("ninguna", PESO_FIJO, *nv.pesos_extra) if desag in ponderables else ("ninguna",)
            for pond in ponds:
                if pond == "ninguna":
                    w = np.ones(int(sel.sum()))
                elif pond == PESO_FIJO:
                    w = np.asarray(nv.poblacion, dtype="float64")[sel]
                else:
                    w = np.asarray(nv.pesos_extra[pond], dtype="float64")[sel]
                n_est, kish = _efectivos(gs, ng, cod_est[sel], w)
                n_blq, g_ef = _efectivos(gs, ng, cod_bloque[sel], w)
                for escala, obs, preds in (("original", nv.obs, nv.pred), ("log", nv.log_obs, nv.log)):
                    o = np.asarray(obs, dtype="float64")[sel]
                    So = _sumas_obs(gs, ng, o, w)                         # una vez por grupo, ponderación y escala
                    for motor in lista:
                        p = np.asarray(preds[motor], dtype="float64")[sel]
                        M = metricas_desde_sumas(np.hstack([So, _sumas_motor(gs, ng, o, p, w)]))
                        for j in range(ng):
                            if M[j, 0] == 0:
                                continue
                            fila = {"motor": motor, "escala": escala, "nivel": nombre_nivel, "desagregacion": desag,
                                    "estrato": etiquetas[j], "ponderacion": pond,
                                    **dict(zip(COLUMNAS_METRICAS, M[j])),
                                    "estaciones": int(n_est[j]), "estaciones_kish": float(kish[j]),
                                    "G": int(n_blq[j]), "G_efectivo": float(g_ef[j])}
                            if retransformacion is not None:
                                fila["retransformacion"] = retransformacion.get(motor, "")
                            filas.append(fila)
    t = pd.DataFrame(filas)
    if len(t):
        t["n"] = t["n"].astype("int64")
    return t


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
