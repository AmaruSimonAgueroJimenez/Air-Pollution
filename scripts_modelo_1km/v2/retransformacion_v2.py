"""Retransformación de log1p(y) a escala original en la v2 (``DISENO_AMBIENTAL_V2.md`` §5 y Enmienda 1, punto 2).

**Formas.** Llevan los nombres de la Enmienda 1. Los de la construcción («duan» para ½·σ² y «smearing») quedan
retirados: el código los rechaza, para que el nombre engañoso no sobreviva.

* ``smearing_duan`` (**primaria**): el *smearing* de Duan (1983), ``adj = log(Σ eʳ / n)`` de los residuos log
  ``r = log1p(y) − ẑ`` de la clave. Es consistente sin suponer errores normales ni homocedásticos y además corrige
  el sesgo medio en log.
* ``lognormal_medio_sigma2`` (**sensibilidad fija**, para todos los motores en log y todos los protocolos): la
  corrección lognormal de la v1, ``adj = ½·Var(r)`` con la varianza poblacional (ddof = 0). Es la que la v1 publica
  como ``duan_oof`` (``qmd:2688``; ``produccion.py:153``).

En las dos, ``ŷ = exp(ẑ + adj) − 1``, y ``exp(adj)`` es el factor que multiplica a ``1 + ŷ``. La clave es
``macrozona|franja``, con la franja diurna de 08 a 18 h local, ambas inclusive (``produccion.py:114-115``).

**Residuos de los demás grupos, con la misma exclusión** (§1, cuarto lugar de la regla única). Las filas de prueba
del pliegue k sólo usan residuos fuera de pliegue de otros pliegues. En los protocolos espaciales tampoco entra
ninguna estación del conjunto excluido de k: en LBO-10, y en BLQ-75 con su amortiguador (punto 8), tampoco el
entorno de 10 km. En LPO la exclusión es temporal: entran las mismas estaciones con los demás cuatrienios.

**Respaldo honesto por unidades independientes** (Enmienda 1, punto 2):

1. la clave macrozona × franja de «los demás» se usa sólo si reúne al menos 3 conglomerados LOSO-D de al menos
   2 grupos del protocolo distintos del retirado, con un piso de 100 filas;
2. si no, la franja de los demás, con 100 filas como mínimo (§5);
3. después, el global de los demás, también con 100 filas;
4. si ni el global alcanza: sin corrección (``adj = 0``), con el nivel ``sin_correccion`` (ratificado, punto 1.7).

Nunca se usa un total que incluya al propio grupo. El grupo del protocolo de una unidad es el pliegue en que sus
filas son de prueba (en LPO, su cuatrienio). Por pliegue y clave se registran el nivel, las estaciones que aportan,
los conglomerados y grupos que se reúnen, el motivo de cada caída y el ajuste y el factor de cada forma. El nivel
no depende de la forma: las dos comparten clave, exclusión y respaldo, como pide la sensibilidad fija.

**Fuga de segundo orden (declarada, punto 2).** Los residuos de los demás grupos vienen de modelos que vieron al
grupo retirado. La sensibilidad con OOF interno la elimina, pero tiende a sobrecorregir.

**Sensibilidad con OOF interno (LRO y BLQ-75).** Para el pliegue externo g, los residuos salen de los pliegues
internos agrupados (los del apilado) dentro del entrenamiento de g, así que ningún modelo que aportó un residuo
vio a g. Usa ``smearing_duan`` e informa también ``lognormal_medio_sigma2``, con el mismo respaldo honesto. Los
grupos son los del protocolo externo de cada fila de entrenamiento.

**Producción** (``decision.retransformacion_de_produccion``): ``tabla_de_produccion`` usa los residuos fuera de
pliegue de LRO de todas las filas (no hay grupo retirado) y ``aplicar_tabla`` los aplica a las superficies.

Implementación: estadísticos suficientes (n, Σr, Σr² y Σeʳ) por unidad estación × macrozona × franja × grupo. Cada
pliegue suma las unidades permitidas: es exacto y cuesta milisegundos por pliegue. Módulo puro.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

FRANJA_DIURNA = (8, 18)                 # horas locales, ambas inclusive (produccion.py:114-115)
DIURNA, NOCTURNA = 1, 0
NOMBRE_FRANJA = {DIURNA: "diurna", NOCTURNA: "nocturna"}

# --- Formas (Enmienda 1, punto 2; config: retransformacion.formas) ---------------------------------------------
SMEARING = "smearing_duan"
LOGNORMAL = "lognormal_medio_sigma2"
FORMAS = (SMEARING, LOGNORMAL)
FORMA_PRIMARIA = SMEARING                       # retransformacion.primaria.forma
FORMA_SENSIBILIDAD_FIJA = LOGNORMAL             # retransformacion.sensibilidad_fija.forma
FORMA_SENSIBILIDAD_INTERNA = SMEARING           # retransformacion.sensibilidad.forma
NOMBRES_RETIRADOS = {"duan": LOGNORMAL, "smearing": SMEARING}     # retransformacion.formas.nombres_anteriores
# Nombre sugerido para la salida de cada forma (la primaria conserva el nombre del motor) y para la sensibilidad
# interna; la consolidación los puede usar para que el nombre diga la corrección.
SUFIJO_FORMA = {SMEARING: "", LOGNORMAL: "~lognormal"}
SUFIJO_INTERNA = "~sens"

# --- Respaldo honesto -----------------------------------------------------------------------------------------
MINIMO_FILAS = 100                      # §5 y piso del punto 2
MINIMO_CONGLOMERADOS = 3                # punto 2: conglomerados LOSO-D en la clave macrozona × franja
MINIMO_GRUPOS = 2                       # punto 2: grupos del protocolo distintos del retirado
NIVELES = ("macrozona_franja", "franja", "global", "sin_correccion")
CODIGO_NIVEL = {n: i for i, n in enumerate(NIVELES)}          # el nivel por fila se guarda como int8
SIN_NIVEL = -1
_B_PLIEGUE, _B_FRANJA, _B_MACROZONA = 1 << 12, 2, 1 << 6      # clave 1-D: ((est·64 + mz)·2 + franja)·4096 + k


@dataclass(frozen=True)
class ReglaRespaldo:
    """Umbrales del respaldo honesto: los de la clave macrozona × franja (punto 2) y el de la franja y el global
    (§5). Por omisión, los del contrato; ``regla_de_config`` los lee de ``config_v2.json``."""

    minimo_filas_clave: int = MINIMO_FILAS
    minimo_conglomerados: int = MINIMO_CONGLOMERADOS
    minimo_grupos: int = MINIMO_GRUPOS
    minimo_filas: int = MINIMO_FILAS

    def como_dict(self) -> dict:
        return {"macrozona_franja": {"minimo_filas": self.minimo_filas_clave,
                                     "minimo_conglomerados_loso_d": self.minimo_conglomerados,
                                     "minimo_grupos_del_protocolo": self.minimo_grupos},
                "franja_y_global": {"minimo_filas": self.minimo_filas}}


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
def valor_config(nodo, nombre: str = "?"):
    """Valor vigente de un nodo de ``config_v2.json`` según sus convenciones: el «valor» de un ratificado, el
    «provisional» de un pendiente (sin provisional, error) o el nodo tal cual."""
    if isinstance(nodo, dict) and str(nodo.get("estado", "")).startswith("ratificado"):
        return nodo["valor"]
    if isinstance(nodo, dict) and nodo.get("estado") == "pendiente":
        if "provisional" not in nodo:
            raise ValueError(f"{nombre}: está pendiente en config_v2.json y no tiene provisional")
        return nodo["provisional"]
    if isinstance(nodo, str) and nodo == "pendiente":
        raise ValueError(f"{nombre}: está pendiente en config_v2.json")
    return nodo


def regla_de_config(cfg: dict) -> ReglaRespaldo:
    """Umbrales de ``retransformacion.primaria`` (``minimo_filas`` y ``respaldo_honesto.macrozona_franja``)."""
    p = cfg["retransformacion"]["primaria"]
    mf = p["respaldo_honesto"]["macrozona_franja"]
    return ReglaRespaldo(minimo_filas_clave=int(mf["minimo_filas"]),
                         minimo_conglomerados=int(mf["minimo_conglomerados_loso_d"]),
                         minimo_grupos=int(mf["minimo_grupos_del_protocolo"]), minimo_filas=int(p["minimo_filas"]))


def formas_de_config(cfg: dict) -> dict:
    """Forma de la primaria, de la sensibilidad fija y de la sensibilidad interna, validadas contra ``FORMAS``."""
    r = cfg["retransformacion"]
    return {"primaria": validar_forma(r["primaria"]["forma"]),
            "sensibilidad_fija": validar_forma(r["sensibilidad_fija"]["forma"]),
            "sensibilidad": validar_forma(r["sensibilidad"]["forma"])}


# ---------------------------------------------------------------------------
# Piezas básicas
# ---------------------------------------------------------------------------
def franja(hora_local, desde: int = FRANJA_DIURNA[0], hasta: int = FRANJA_DIURNA[1]) -> np.ndarray:
    """1 (diurna) si la hora local está en [desde, hasta], 0 (nocturna) si no; réplica de
    ``produccion.py:114-115`` con códigos enteros."""
    h = np.asarray(hora_local)
    return ((h >= desde) & (h <= hasta)).astype(np.int8)


def clave(macrozona: int, fr: int) -> str:
    """Clave de la v1, ``"{macrozona_cod}|{franja}"`` (``produccion.py:141-147``)."""
    return f"{int(macrozona)}|{NOMBRE_FRANJA[int(fr)]}"


def validar_forma(forma: str) -> str:
    """Devuelve la forma si es una de ``FORMAS``; rechaza los nombres retirados por la Enmienda 1."""
    if forma in FORMAS:
        return forma
    if forma in NOMBRES_RETIRADOS:
        raise ValueError(f"la forma {forma!r} se retiró con la Enmienda 1 (punto 2): su nombre es "
                         f"{NOMBRES_RETIRADOS[forma]!r}. Usa {FORMAS}.")
    raise ValueError(f"forma de retransformación desconocida: {forma!r} (usa {FORMAS})")


def ajuste_desde_sumas(n, s1, s2, se, forma: str = FORMA_PRIMARIA) -> np.ndarray:
    """``adj`` a partir de n, Σr, Σr² y Σeʳ: ``log(Σeʳ / n)`` (``smearing_duan``) o ½·Var poblacional
    (``lognormal_medio_sigma2``)."""
    forma = validar_forma(forma)
    n = np.asarray(n, dtype="float64")
    with np.errstate(invalid="ignore", divide="ignore"):
        if forma == SMEARING:
            return np.log(np.asarray(se, dtype="float64") / n)
        m = np.asarray(s1, dtype="float64") / n
        var = np.asarray(s2, dtype="float64") / n - m * m
        return 0.5 * np.maximum(var, 0.0)


def factor(adj) -> np.ndarray:
    """Factor multiplicativo de la corrección sobre ``1 + ŷ``: ``exp(adj)``."""
    return np.exp(np.asarray(adj, dtype="float64"))


def retransformar(z, adj) -> np.ndarray:
    """``ŷ = exp(ẑ + adj) − 1`` en float64, devuelto en float32 (como ``retransformar_oof``, qmd:2691)."""
    return np.expm1(np.asarray(z, dtype="float64") + np.asarray(adj, dtype="float64")).astype("float32")


def residuo_log(y, z) -> np.ndarray:
    """``log1p(clip(y, 0)) − ẑ`` en float64 (qmd:2675)."""
    return np.log1p(np.clip(np.asarray(y, dtype="float64"), 0.0, None)) - np.asarray(z, dtype="float64")


def conglomerados_loso_d(manifiesto_pol: Mapping, estaciones: Sequence) -> np.ndarray:
    """Conglomerado LOSO-D (su k) de cada estación de ``estaciones``, en ese orden, a partir del manifiesto de
    pliegues de un contaminante (``pliegues_v2.json`` → ``contaminantes[pol]``). Cada estación debe estar en un
    solo pliegue de LOSO-D."""
    de: dict[str, int] = {}
    for f in manifiesto_pol["protocolos"]["LOSO-D"]["pliegues"]:
        for s in f["estaciones_prueba"]:
            if str(s) in de:
                raise ValueError(f"la estación {s} está en dos conglomerados de LOSO-D")
            de[str(s)] = int(f["k"])
    faltan = [str(s) for s in estaciones if str(s) not in de]
    if faltan:
        raise ValueError(f"estaciones sin conglomerado LOSO-D en el manifiesto: {faltan}")
    return np.array([de[str(s)] for s in estaciones], dtype="int64")


def _conglomerados(conglomerado_de_estacion, estacion: np.ndarray) -> np.ndarray:
    """Valida que cada estación presente tenga su conglomerado LOSO-D (arreglo indexado por código de estación)."""
    if conglomerado_de_estacion is None:
        raise ValueError("el respaldo honesto (Enmienda 1, punto 2) necesita el conglomerado LOSO-D de cada estación: "
                         "pasa conglomerado_de_estacion (ver conglomerados_loso_d)")
    c = np.asarray(conglomerado_de_estacion, dtype="int64")
    if c.ndim != 1:
        raise ValueError("conglomerado_de_estacion debe ser un arreglo 1-D indexado por el código de estación")
    usados = np.unique(np.asarray(estacion, dtype="int64"))
    if len(usados) and (usados.min() < 0 or usados.max() >= len(c)):
        raise ValueError("hay códigos de estación sin entrada en conglomerado_de_estacion")
    sin = usados[c[usados] < 0] if len(usados) else usados
    if len(sin):
        raise ValueError(f"estaciones sin conglomerado LOSO-D (códigos): {sin.tolist()}")
    return c


# ---------------------------------------------------------------------------
# Estadísticos por unidad
# ---------------------------------------------------------------------------
@dataclass
class Unidades:
    """Sumas de residuos por unidad (estación, macrozona, franja, grupo). ``pliegue`` es el grupo del protocolo de
    la unidad: el pliegue en que sus filas son de prueba (en la tabla interna, el pliegue externo de la fila)."""

    estacion: np.ndarray        # código entero de estación de cada unidad
    macrozona: np.ndarray
    franja: np.ndarray
    pliegue: np.ndarray
    n: np.ndarray
    s1: np.ndarray
    s2: np.ndarray
    se: np.ndarray

    @classmethod
    def desde_filas(cls, res, estacion, macrozona, fr, pliegue) -> "Unidades":
        """Unidades de las filas con residuo finito y grupo válido (≥ 0)."""
        res = np.asarray(res, dtype="float64")
        k_todas = np.asarray(pliegue, dtype="int64")
        ok = np.isfinite(res) & (k_todas >= 0)
        est, mz = np.asarray(estacion, dtype="int64")[ok], np.asarray(macrozona, dtype="int64")[ok]
        f, k = np.asarray(fr, dtype="int64")[ok], k_todas[ok]
        if len(k) and (k.max() >= _B_PLIEGUE or mz.min() < 0 or mz.max() >= _B_MACROZONA or est.min() < 0):
            raise ValueError("estación, pliegue o macrozona fuera del rango de la clave de unidad")
        r = res[ok]
        if len(r) == 0:
            vacio = np.zeros(0, dtype="int64")
            return cls(vacio, vacio, vacio, vacio, np.zeros(0), np.zeros(0), np.zeros(0), np.zeros(0))
        clave_u = ((est * _B_MACROZONA + mz) * _B_FRANJA + f) * _B_PLIEGUE + k     # 1-D: mucho más rápido que axis=0
        u, inv = np.unique(clave_u, return_inverse=True)
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


def _info(u: Unidades, m: np.ndarray, congl: np.ndarray) -> dict:
    """Sumas, estaciones, conglomerados LOSO-D y grupos del protocolo de las unidades ``m``."""
    est = np.unique(u.estacion[m])
    return {"n": float(u.n[m].sum()), "s1": float(u.s1[m].sum()), "s2": float(u.s2[m].sum()),
            "se": float(u.se[m].sum()), "estaciones": est,
            "conglomerados": int(len(np.unique(congl[est]))) if len(est) else 0,
            "grupos": int(len(np.unique(u.pliegue[m])))}


def _tabla_respaldo(u: Unidades, ok: np.ndarray, congl: np.ndarray, regla: ReglaRespaldo,
                    forma: str = FORMA_PRIMARIA) -> dict:
    """Sumas por clave, por franja y global con las unidades ``ok`` (las de «los demás»)."""
    tabla = {"forma": validar_forma(forma), "regla": regla, "macrozona_franja": {}, "franja": {}, "global": None}
    for mz in np.unique(u.macrozona[ok]):
        for fr in (NOCTURNA, DIURNA):
            m = ok & (u.macrozona == mz) & (u.franja == fr)
            if m.any():
                tabla["macrozona_franja"][(int(mz), fr)] = _info(u, m, congl)
    for fr in (NOCTURNA, DIURNA):
        m = ok & (u.franja == fr)
        if m.any():
            tabla["franja"][fr] = _info(u, m, congl)
    tabla["global"] = _info(u, ok, congl) if ok.any() else None
    return tabla


def _resolver_clave(tabla: dict, mz: int, fr: int) -> tuple[str, dict | None, list[str]]:
    """(nivel, sumas usadas, motivos de cada caída) de una clave con el respaldo honesto del punto 2."""
    r: ReglaRespaldo = tabla["regla"]
    motivo = []
    s = tabla["macrozona_franja"].get((int(mz), int(fr)))
    if s is None:
        motivo.append("macrozona_franja: sin residuos de los demás en la clave")
    else:
        falta = []
        if s["n"] < r.minimo_filas_clave:
            falta.append(f"filas {int(s['n'])} < {r.minimo_filas_clave}")
        if s["conglomerados"] < r.minimo_conglomerados:
            falta.append(f"conglomerados LOSO-D {s['conglomerados']} < {r.minimo_conglomerados}")
        if s["grupos"] < r.minimo_grupos:
            falta.append(f"grupos del protocolo {s['grupos']} < {r.minimo_grupos}")
        if not falta:
            return "macrozona_franja", s, motivo
        motivo.append("macrozona_franja: " + "; ".join(falta))
    for nivel, s in (("franja", tabla["franja"].get(int(fr))), ("global", tabla["global"])):
        if s is not None and s["n"] >= r.minimo_filas:
            return nivel, s, motivo
        motivo.append(f"{nivel}: filas {int(s['n']) if s is not None else 0} < {r.minimo_filas}")
    return "sin_correccion", None, motivo


def _entrada(nivel: str, s: dict | None, motivo: list, formas: Sequence[str], nombres_estacion) -> dict:
    """Renglón del registro de una clave: nivel, estaciones que aportan, conglomerados, grupos, ajuste y factor."""
    if nivel == "sin_correccion" or s is None:
        adj = {f: 0.0 for f in formas}
        est, n, cg, gr = [], 0, 0, 0
    else:
        adj = {f: float(ajuste_desde_sumas(s["n"], s["s1"], s["s2"], s["se"], f)) for f in formas}
        est = (s["estaciones"].tolist() if nombres_estacion is None
               else [str(nombres_estacion[int(c)]) for c in s["estaciones"]])
        n, cg, gr = int(s["n"]), s["conglomerados"], s["grupos"]
    return {"nivel": nivel, "filas_usadas": n, "estaciones": est, "conglomerados": cg, "grupos": gr,
            "motivo": list(motivo), "ajuste": adj, "factor": {f: float(np.exp(a)) for f, a in adj.items()}}


@dataclass
class Retransformacion:
    """Resultado de una retransformación: predicción y ajuste por forma, nivel de respaldo por fila (común a las
    formas) y registro por pliegue × clave."""

    formas: tuple
    pred: dict              # forma → float32 por fila (NaN si la fila no tiene ẑ o no tiene ajuste)
    adj: dict               # forma → float64 por fila
    nivel: np.ndarray       # int8 por fila (CODIGO_NIVEL; SIN_NIVEL si la fila no tiene ajuste)
    registro: list
    regla: ReglaRespaldo

    def resumen(self) -> dict:
        return {"formas": list(self.formas), "forma_primaria": FORMA_PRIMARIA, "niveles": resumen_niveles(self.nivel),
                "regla": self.regla.como_dict()}


def _formas(formas) -> tuple:
    out = tuple(validar_forma(f) for f in ((formas,) if isinstance(formas, str) else formas))
    if not out:
        raise ValueError("pide al menos una forma")
    return out


def _predicciones(z: np.ndarray, adj: Mapping[str, np.ndarray]) -> dict:
    out = {}
    for f, a in adj.items():
        p = np.full(len(z), np.nan, dtype="float32")
        con = np.isfinite(a) & np.isfinite(z)
        p[con] = retransformar(z[con], a[con])
        out[f] = p
    return out


# ---------------------------------------------------------------------------
# Primaria y sensibilidad fija: fuera de pliegue, de los demás grupos, con la exclusión del protocolo
# ---------------------------------------------------------------------------
def fuera_de_pliegue(z, y, estacion, macrozona, hora_local, pliegue_de_fila, excluidas_por_pliegue: Mapping,
                     temporal: bool, *, conglomerado_de_estacion, formas=FORMAS, regla: ReglaRespaldo | None = None,
                     nombres_estacion=None) -> Retransformacion:
    """Retransformación de un protocolo completo, con las formas pedidas (por omisión, la primaria y la
    sensibilidad fija, que comparten clave, exclusión y respaldo).

    ``z``: predicción log fuera de pliegue de **todas** las filas del protocolo (cada fila es de prueba en un solo
    pliegue, ``pliegue_de_fila``; −1 = sin pliegue). ``estacion``: código entero por fila.
    ``excluidas_por_pliegue``: ``{k: códigos de las estaciones excluidas}`` (en LPO no se usa: la exclusión es
    temporal). ``conglomerado_de_estacion``: conglomerado LOSO-D por código de estación (``conglomerados_loso_d``).
    ``nombres_estacion``: si se da, el registro lista las estaciones por nombre.
    """
    formas = _formas(formas)
    regla = regla or ReglaRespaldo()
    z = np.asarray(z, dtype="float64")
    n = len(z)
    pliegue_de_fila = np.asarray(pliegue_de_fila, dtype="int64")
    est = np.asarray(estacion, dtype="int64")
    mz = np.asarray(macrozona, dtype="int64")
    fr = franja(hora_local)
    if not (len(pliegue_de_fila) == len(est) == len(mz) == len(fr) == len(np.asarray(y)) == n):
        raise ValueError("z, y, estacion, macrozona, hora_local y pliegue_de_fila deben tener una entrada por fila")
    congl = _conglomerados(conglomerado_de_estacion, est)
    u = Unidades.desde_filas(residuo_log(y, z), est, mz, fr, pliegue_de_fila)
    adj = {f: np.full(n, np.nan) for f in formas}
    nivel = np.full(n, SIN_NIVEL, dtype="int8")
    registro = []
    clave_fila = mz * _B_FRANJA + fr
    orden = np.argsort(pliegue_de_fila, kind="stable")
    ps = pliegue_de_fila[orden]
    ks = np.unique(ps[ps >= 0])
    for k, a, b in zip(ks, np.searchsorted(ps, ks, "left"), np.searchsorted(ps, ks, "right")):
        filas = orden[a:b]
        excl = None if temporal else np.asarray(excluidas_por_pliegue.get(int(k), []), dtype="int64")
        if not temporal and not np.isin(np.unique(est[filas]), excl).all():
            raise ValueError(f"pliegue {k}: hay filas de prueba de estaciones fuera del conjunto excluido")
        ok = u.permitidas(int(k), excl, temporal)
        if (u.pliegue[ok] == int(k)).any():                      # guarda: nunca el propio grupo
            raise AssertionError("la retransformación usaría residuos del propio pliegue")
        if excl is not None and len(excl) and np.isin(u.estacion[ok], excl).any():
            raise AssertionError("la retransformación usaría residuos de una estación excluida")
        tabla = _tabla_respaldo(u, ok, congl, regla)
        cf = clave_fila[filas]
        for c in np.unique(cf):
            cmz, cfr = divmod(int(c), _B_FRANJA)
            niv, s, motivo = _resolver_clave(tabla, cmz, cfr)
            sel = filas[cf == c]
            ent = _entrada(niv, s, motivo, formas, nombres_estacion)
            for f in formas:
                adj[f][sel] = ent["ajuste"][f]
            nivel[sel] = CODIGO_NIVEL[niv]
            registro.append({"k": int(k), "clave": clave(cmz, cfr), "filas_prueba": int(len(sel)), **ent})
    return Retransformacion(formas, _predicciones(z, adj), adj, nivel, registro, regla)


def duan_fuera_de_pliegue(z, y, estacion, macrozona, hora_local, pliegue_de_fila, excluidas_por_pliegue: Mapping,
                          temporal: bool, minimo: int | None = None, forma: str = FORMA_PRIMARIA, *,
                          conglomerado_de_estacion=None, regla: ReglaRespaldo | None = None, nombres_estacion=None):
    """Una sola forma (por omisión, la primaria ``smearing_duan``): ``(pred, adj, nivel, registro)``.

    ``minimo``, si se da, reemplaza los mínimos de filas de la regla (los tres niveles). El conglomerado LOSO-D de
    cada estación es obligatorio: sin él no se puede aplicar el respaldo honesto del punto 2."""
    regla = regla or ReglaRespaldo()
    if minimo is not None:
        regla = ReglaRespaldo(int(minimo), regla.minimo_conglomerados, regla.minimo_grupos, int(minimo))
    r = fuera_de_pliegue(z, y, estacion, macrozona, hora_local, pliegue_de_fila, excluidas_por_pliegue, temporal,
                         conglomerado_de_estacion=conglomerado_de_estacion, formas=(forma,), regla=regla,
                         nombres_estacion=nombres_estacion)
    forma = r.formas[0]
    registro = [{**x, "forma": forma, "adj": x["ajuste"][forma]} for x in r.registro]
    return r.pred[forma], r.adj[forma], r.nivel, registro


# ---------------------------------------------------------------------------
# Tablas con todas las unidades: sensibilidad con OOF interno y producción
# ---------------------------------------------------------------------------
def tabla_de_residuos(z, y, macrozona, hora_local, *, estacion, grupo, conglomerado_de_estacion,
                      regla: ReglaRespaldo | None = None, forma: str = FORMA_PRIMARIA) -> dict:
    """Tabla de ajuste (sumas por clave, franja y global, con estaciones, conglomerados y grupos) con todas las
    filas dadas. ``grupo``: grupo del protocolo de cada fila (su pliegue de prueba)."""
    est = np.asarray(estacion, dtype="int64")
    g = np.asarray(grupo, dtype="int64")
    if len(g) != len(est) or (g < 0).any():
        raise ValueError("cada fila de la tabla necesita su grupo del protocolo (≥ 0)")
    congl = _conglomerados(conglomerado_de_estacion, est)
    u = Unidades.desde_filas(residuo_log(y, z), est, macrozona, franja(hora_local), g)
    return _tabla_respaldo(u, np.ones(len(u.n), dtype=bool), congl, regla or ReglaRespaldo(), forma)


def tabla_interna(z_interno, y_interno, macrozona_interno, hora_interno, minimo: int | None = None,
                  forma: str = FORMA_SENSIBILIDAD_INTERNA, *, estacion, grupo, conglomerado_de_estacion,
                  regla: ReglaRespaldo | None = None, retirado: int | None = None, excluidas=None) -> dict:
    """Tabla de la sensibilidad con OOF interno: residuos de los pliegues internos del entrenamiento de un pliegue
    externo, con el mismo respaldo honesto. ``grupo``: pliegue externo de prueba de cada fila de entrenamiento.
    Si se dan ``retirado`` (k externo) o ``excluidas`` (códigos), se verifica que ninguna fila sea de ellos."""
    regla = regla or ReglaRespaldo()
    if minimo is not None:
        regla = ReglaRespaldo(int(minimo), regla.minimo_conglomerados, regla.minimo_grupos, int(minimo))
    g = np.asarray(grupo, dtype="int64")
    if retirado is not None and (g == int(retirado)).any():
        raise AssertionError("la tabla interna recibe filas del grupo retirado")
    if excluidas is not None and len(excluidas) and np.isin(np.asarray(estacion, dtype="int64"),
                                                            np.asarray(excluidas, dtype="int64")).any():
        raise AssertionError("la tabla interna recibe filas de una estación excluida")
    return tabla_de_residuos(z_interno, y_interno, macrozona_interno, hora_interno, estacion=estacion, grupo=g,
                             conglomerado_de_estacion=conglomerado_de_estacion, regla=regla, forma=forma)


def tabla_de_produccion(z_oof, y, macrozona, hora_local, *, estacion, grupo, conglomerado_de_estacion,
                        regla: ReglaRespaldo | None = None) -> dict:
    """Tabla de producción (``decision.retransformacion_de_produccion``): residuos fuera de pliegue de LRO de todas
    las filas, con la forma y la clave de la primaria; en producción no hay grupo retirado."""
    return tabla_de_residuos(z_oof, y, macrozona, hora_local, estacion=estacion, grupo=grupo,
                             conglomerado_de_estacion=conglomerado_de_estacion, regla=regla, forma=FORMA_PRIMARIA)


def aplicar_tabla(z, macrozona, hora_local, tabla: dict, formas=FORMAS, nombres_estacion=None) -> Retransformacion:
    """Aplica una tabla (interna o de producción) a filas de prueba, con las formas pedidas."""
    formas = _formas(formas)
    z = np.asarray(z, dtype="float64")
    mz = np.asarray(macrozona, dtype="int64")
    fr = franja(hora_local)
    adj = {f: np.full(len(z), np.nan) for f in formas}
    nivel = np.full(len(z), SIN_NIVEL, dtype="int8")
    registro = []
    clave_fila = mz * _B_FRANJA + fr
    for c in np.unique(clave_fila):
        cmz, cfr = divmod(int(c), _B_FRANJA)
        niv, s, motivo = _resolver_clave(tabla, cmz, cfr)
        sel = clave_fila == c
        ent = _entrada(niv, s, motivo, formas, nombres_estacion)
        for f in formas:
            adj[f][sel] = ent["ajuste"][f]
        nivel[sel] = CODIGO_NIVEL[niv]
        registro.append({"clave": clave(cmz, cfr), "filas_prueba": int(sel.sum()), **ent})
    return Retransformacion(formas, _predicciones(z, adj), adj, nivel, registro, tabla["regla"])


def duan_interno(z_prueba, macrozona_prueba, hora_prueba, tabla: dict, forma: str | None = None):
    """Una sola forma (por omisión, la de la tabla): ``(pred, adj, nivel, registro)``."""
    forma = validar_forma(forma or tabla["forma"])
    r = aplicar_tabla(z_prueba, macrozona_prueba, hora_prueba, tabla, formas=(forma,))
    registro = [{**x, "forma": forma, "adj": x["ajuste"][forma]} for x in r.registro]
    return r.pred[forma], r.adj[forma], r.nivel, registro


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------
def nombre_nivel(nivel) -> np.ndarray:
    """Nombre del nivel de respaldo de cada fila a partir del código int8 (vacío si la fila no tiene ajuste)."""
    nombres = np.array([*NIVELES, ""], dtype=object)
    return nombres[np.asarray(nivel, dtype="int64")]


def resumen_niveles(nivel) -> dict:
    """Filas por nivel de respaldo (para el registro de la consolidación)."""
    nv = np.asarray(nivel, dtype="int64")
    cuenta = np.bincount(nv[nv >= 0], minlength=len(NIVELES))
    return {n: int(cuenta[i]) for i, n in enumerate(NIVELES)}
