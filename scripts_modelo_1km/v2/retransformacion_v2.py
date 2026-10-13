"""Retransformación de log1p(y) a escala original en la v2 (``DISENO_AMBIENTAL_V2.md`` §5).

**Primaria (fijada en el contrato).** «Duan» por macrozona × franja en el sentido de la v1 (``duan_oof``:
``qmd:2688``; ``produccion.py:153``), que es la corrección lognormal: ``adj = ½·Var(r)``, con la varianza
poblacional (ddof = 0) del residuo log ``r = log1p(y) − ẑ``, y ``ŷ = exp(ẑ + adj) − 1``. La clave es
``macrozona|franja``, con la franja diurna de 08 a 18 h local, ambas inclusive (``produccion.py:114-115``).

Para las filas de prueba de un pliegue, ``adj`` se estima con los residuos fuera de pliegue de **los demás
grupos**, aplicando **la misma exclusión del protocolo** (§1, cuarto lugar de la regla única): en los protocolos
espaciales no entra ninguna fila de una estación del conjunto excluido (en LBO-10, tampoco el entorno de
10 km, que la v1 dejaba entrar, ``qmd:2836``); en LPO no entra ninguna fila del cuatrienio de prueba.

**Respaldo honesto** cuando lo que queda tiene menos de 100 filas en la clave (§5): primero la franja de los
demás grupos (todas las macrozonas), luego el global de los demás grupos. Nunca un total que incluya al propio
grupo, que es lo que hacía la v1 (``qmd:2683-2684``: en NO₂, 34.062 filas en LOSO y LBO y 255.728 en LRO). Si
incluso el global de los demás tiene menos de 100 filas, se aplica el valor provisional de
``config_v2.json`` (``retransformacion.primaria.global_de_los_demas_con_menos_de_100_filas``): sin corrección
(``adj = 0``), registrado.

**Sensibilidad (LRO y BLQ-75).** Duan con OOF interno: para el pliegue externo g, los residuos son los de las
predicciones de pliegues internos agrupados dentro del entrenamiento de g, de modo que ningún modelo que
aportó un residuo vio a g. Mismo respaldo (franja y luego global del entrenamiento de g).

Implementación: estadísticos suficientes (n, Σr, Σr² y Σeʳ) por unidad estación × macrozona × franja × pliegue
de prueba; cada pliegue suma las unidades permitidas. Es exacto y cuesta milisegundos por pliegue. Módulo puro.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

FRANJA_DIURNA = (8, 18)                 # horas locales, ambas inclusive (produccion.py:114-115)
DIURNA, NOCTURNA = 1, 0
NOMBRE_FRANJA = {DIURNA: "diurna", NOCTURNA: "nocturna"}
MINIMO_FILAS = 100
NIVELES = ("macrozona_franja", "franja", "global", "sin_correccion")
CODIGO_NIVEL = {n: i for i, n in enumerate(NIVELES)}          # el nivel por fila se guarda como int8
SIN_NIVEL = -1
FORMAS = ("duan", "smearing")
_B_PLIEGUE, _B_FRANJA, _B_MACROZONA = 1 << 12, 2, 1 << 6      # clave 1-D: ((est·64 + mz)·2 + franja)·4096 + k


def franja(hora_local, desde: int = FRANJA_DIURNA[0], hasta: int = FRANJA_DIURNA[1]) -> np.ndarray:
    """1 (diurna) si la hora local está en [desde, hasta], 0 (nocturna) si no; réplica de
    ``produccion.py:114-115`` con códigos enteros."""
    h = np.asarray(hora_local)
    return ((h >= desde) & (h <= hasta)).astype(np.int8)


def clave(macrozona: int, fr: int) -> str:
    """Clave de la v1, ``"{macrozona_cod}|{franja}"`` (``produccion.py:141-147``)."""
    return f"{int(macrozona)}|{NOMBRE_FRANJA[int(fr)]}"


def ajuste_desde_sumas(n, s1, s2, se, forma: str = "duan") -> np.ndarray:
    """``adj`` a partir de n, Σr, Σr² y Σeʳ: ½·Var poblacional (Duan de la v1) o log de la media de eʳ
    (smearing no paramétrico, ``qmd:2689-2690``)."""
    n = np.asarray(n, dtype="float64")
    with np.errstate(invalid="ignore", divide="ignore"):
        if forma == "duan":
            m = np.asarray(s1, dtype="float64") / n
            var = np.asarray(s2, dtype="float64") / n - m * m
            return 0.5 * np.maximum(var, 0.0)
        if forma == "smearing":
            return np.log(np.asarray(se, dtype="float64") / n)
    raise ValueError(f"forma de retransformación desconocida: {forma!r} (usa {FORMAS})")


def retransformar(z, adj) -> np.ndarray:
    """``ŷ = exp(ẑ + adj) − 1`` en float64, devuelto en float32 (como ``retransformar_oof``, qmd:2691)."""
    return np.expm1(np.asarray(z, dtype="float64") + np.asarray(adj, dtype="float64")).astype("float32")


def residuo_log(y, z) -> np.ndarray:
    """``log1p(clip(y, 0)) − ẑ`` en float64 (qmd:2675)."""
    return np.log1p(np.clip(np.asarray(y, dtype="float64"), 0.0, None)) - np.asarray(z, dtype="float64")


# ---------------------------------------------------------------------------
# Estadísticos por unidad
# ---------------------------------------------------------------------------
@dataclass
class Unidades:
    """Sumas de residuos por unidad (estación, macrozona, franja, pliegue de prueba)."""

    estacion: np.ndarray        # código entero de estación de cada unidad
    macrozona: np.ndarray
    franja: np.ndarray
    pliegue: np.ndarray         # k del pliegue en que las filas de la unidad son de prueba
    n: np.ndarray
    s1: np.ndarray
    s2: np.ndarray
    se: np.ndarray

    @classmethod
    def desde_filas(cls, res, estacion, macrozona, fr, pliegue) -> "Unidades":
        res = np.asarray(res, dtype="float64")
        ok = np.isfinite(res)
        est, mz = np.asarray(estacion, dtype="int64")[ok], np.asarray(macrozona, dtype="int64")[ok]
        f, k = np.asarray(fr, dtype="int64")[ok], np.asarray(pliegue, dtype="int64")[ok]
        if len(k) and (k.min() < 0 or k.max() >= _B_PLIEGUE or mz.min() < 0 or mz.max() >= _B_MACROZONA):
            raise ValueError("pliegue o macrozona fuera del rango de la clave de unidad")
        r = res[ok]
        if len(r) == 0:
            vacio = np.zeros(0, dtype="int64")
            return cls(vacio, vacio, vacio, vacio, np.zeros(0), np.zeros(0), np.zeros(0), np.zeros(0))
        clave = ((est * _B_MACROZONA + mz) * _B_FRANJA + f) * _B_PLIEGUE + k        # 1-D: mucho más rápido que axis=0
        u, inv = np.unique(clave, return_inverse=True)
        inv = inv.ravel()
        m = len(u)
        uk, resto = u % _B_PLIEGUE, u // _B_PLIEGUE
        uf, resto = resto % _B_FRANJA, resto // _B_FRANJA
        umz, uest = resto % _B_MACROZONA, resto // _B_MACROZONA
        return cls(uest, umz, uf, uk,
                   np.bincount(inv, minlength=m).astype("float64"),
                   np.bincount(inv, weights=r, minlength=m),
                   np.bincount(inv, weights=r * r, minlength=m),
                   np.bincount(inv, weights=np.exp(r), minlength=m))

    def permitidas(self, k: int, excluidas_cod: np.ndarray | None, temporal: bool) -> np.ndarray:
        """Unidades cuyos residuos puede usar el pliegue k: nunca las del propio pliegue y, en los protocolos
        espaciales, ninguna de una estación excluida (la misma exclusión del protocolo)."""
        ok = self.pliegue != int(k)
        if not temporal and excluidas_cod is not None and len(excluidas_cod):
            ok &= ~np.isin(self.estacion, np.asarray(excluidas_cod, dtype="int64"))
        return ok


def _tabla_respaldo(u: Unidades, ok: np.ndarray, minimo: int, forma: str) -> dict:
    """Ajuste por clave con respaldo honesto, usando sólo las unidades ``ok``."""
    def sumas(mascara):
        return (float(u.n[mascara].sum()), float(u.s1[mascara].sum()), float(u.s2[mascara].sum()),
                float(u.se[mascara].sum()))

    tabla = {"forma": forma, "minimo": int(minimo), "macrozona_franja": {}, "franja": {}, "global": None}
    for mz in np.unique(u.macrozona[ok]):
        for fr in (NOCTURNA, DIURNA):
            m = ok & (u.macrozona == mz) & (u.franja == fr)
            if m.any():
                tabla["macrozona_franja"][(int(mz), fr)] = sumas(m)
    for fr in (NOCTURNA, DIURNA):
        m = ok & (u.franja == fr)
        if m.any():
            tabla["franja"][fr] = sumas(m)
    tabla["global"] = sumas(ok) if ok.any() else (0.0, 0.0, 0.0, 0.0)
    return tabla


def _resolver_clave(tabla: dict, mz: int, fr: int) -> tuple[float, str, int]:
    """(adj, nivel, filas usadas) de una clave con el orden de respaldo de §5."""
    minimo, forma = tabla["minimo"], tabla["forma"]
    for nivel, s in (("macrozona_franja", tabla["macrozona_franja"].get((int(mz), int(fr)))),
                     ("franja", tabla["franja"].get(int(fr))),
                     ("global", tabla["global"])):
        if s is not None and s[0] >= minimo:
            return float(ajuste_desde_sumas(s[0], s[1], s[2], s[3], forma)), nivel, int(s[0])
    return 0.0, "sin_correccion", int(tabla["global"][0]) if tabla["global"] else 0


# ---------------------------------------------------------------------------
# Primaria: fuera de pliegue, de los demás grupos, con la exclusión del protocolo
# ---------------------------------------------------------------------------
def duan_fuera_de_pliegue(z, y, estacion, macrozona, hora_local, pliegue_de_fila, excluidas_por_pliegue: dict,
                          temporal: bool, minimo: int = MINIMO_FILAS, forma: str = "duan"):
    """Retransformación primaria de un protocolo completo.

    ``z``: predicción log fuera de pliegue de **todas** las filas del protocolo (cada fila es de prueba en un
    solo pliegue, ``pliegue_de_fila``). ``estacion``: código entero por fila. ``excluidas_por_pliegue``:
    ``{k: códigos de las estaciones excluidas}`` (en LPO no se usa: la exclusión es temporal y coincide con las
    filas del propio pliegue). Devuelve ``(pred, adj, nivel, registro)`` por fila y un renglón por pliegue × clave.
    """
    z = np.asarray(z, dtype="float64")
    pliegue_de_fila = np.asarray(pliegue_de_fila, dtype="int64")
    fr = franja(hora_local)
    mz = np.asarray(macrozona, dtype="int64")
    est = np.asarray(estacion, dtype="int64")
    u = Unidades.desde_filas(residuo_log(y, z), est, mz, fr, pliegue_de_fila)
    adj = np.full(len(z), np.nan)
    nivel = np.full(len(z), SIN_NIVEL, dtype="int8")
    registro = []
    clave_fila = mz * _B_FRANJA + fr
    for k in np.unique(pliegue_de_fila[pliegue_de_fila >= 0]):
        filas = np.flatnonzero(pliegue_de_fila == k)
        excl = None if temporal else np.asarray(excluidas_por_pliegue.get(int(k), []), dtype="int64")
        if not temporal and not np.isin(np.unique(est[filas]), excl).all():
            raise ValueError(f"pliegue {k}: hay filas de prueba de estaciones fuera del conjunto excluido")
        ok = u.permitidas(int(k), excl, temporal)
        if (u.pliegue[ok] == int(k)).any():                     # guarda: nunca el propio grupo
            raise AssertionError("la retransformación usaría residuos del propio pliegue")
        tabla = _tabla_respaldo(u, ok, minimo, forma)
        for c in np.unique(clave_fila[filas]):
            cmz, cfr = int(c) // _B_FRANJA, int(c) % _B_FRANJA
            a, niv, n_usado = _resolver_clave(tabla, cmz, cfr)
            sel = filas[clave_fila[filas] == c]
            adj[sel], nivel[sel] = a, CODIGO_NIVEL[niv]
            registro.append({"k": int(k), "clave": clave(cmz, cfr), "nivel": niv, "filas_usadas": n_usado,
                             "filas_prueba": int(len(sel)), "adj": a})
    pred = np.full(len(z), np.nan, dtype="float32")
    con = np.isfinite(adj) & np.isfinite(z)
    pred[con] = retransformar(z[con], adj[con])
    return pred, adj, nivel, registro


# ---------------------------------------------------------------------------
# Sensibilidad: OOF interno dentro de cada pliegue externo
# ---------------------------------------------------------------------------
def tabla_interna(z_interno, y_interno, macrozona_interno, hora_interno, minimo: int = MINIMO_FILAS,
                  forma: str = "duan") -> dict:
    """Tabla de ajuste con los residuos del OOF interno del entrenamiento de un pliegue externo."""
    res = residuo_log(y_interno, z_interno)
    n = len(res)
    u = Unidades.desde_filas(res, np.zeros(n, dtype="int64"), macrozona_interno, franja(hora_interno),
                             np.zeros(n, dtype="int64"))
    return _tabla_respaldo(u, np.ones(len(u.n), dtype=bool), minimo, forma)


def duan_interno(z_prueba, macrozona_prueba, hora_prueba, tabla: dict):
    """Aplica una ``tabla_interna`` a las filas de prueba del pliegue externo: ``(pred, adj, nivel, registro)``."""
    z = np.asarray(z_prueba, dtype="float64")
    mz = np.asarray(macrozona_prueba, dtype="int64")
    fr = franja(hora_prueba)
    adj = np.full(len(z), np.nan)
    nivel = np.full(len(z), SIN_NIVEL, dtype="int8")
    registro = []
    clave_fila = mz * _B_FRANJA + fr
    for c in np.unique(clave_fila):
        cmz, cfr = int(c) // _B_FRANJA, int(c) % _B_FRANJA
        a, niv, n_usado = _resolver_clave(tabla, cmz, cfr)
        sel = clave_fila == c
        adj[sel], nivel[sel] = a, CODIGO_NIVEL[niv]
        registro.append({"clave": clave(cmz, cfr), "nivel": niv, "filas_usadas": n_usado,
                         "filas_prueba": int(sel.sum()), "adj": a})
    pred = np.full(len(z), np.nan, dtype="float32")
    con = np.isfinite(adj) & np.isfinite(z)
    pred[con] = retransformar(z[con], adj[con])
    return pred, adj, nivel, registro


def nombre_nivel(nivel) -> np.ndarray:
    """Nombre del nivel de respaldo de cada fila a partir del código int8 (vacío si la fila no tiene ajuste)."""
    nombres = np.array([*NIVELES, ""], dtype=object)
    return nombres[np.asarray(nivel, dtype="int64")]


def resumen_niveles(nivel) -> dict:
    """Filas por nivel de respaldo (para el registro de la consolidación)."""
    cuenta = np.bincount(np.asarray(nivel, dtype="int64")[np.asarray(nivel) >= 0], minlength=len(NIVELES))
    return {n: int(cuenta[i]) for i, n in enumerate(NIVELES)}
