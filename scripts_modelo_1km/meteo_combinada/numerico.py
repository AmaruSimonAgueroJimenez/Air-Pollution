"""Funciones numéricas comunes (§2.3-§5 del texto): Magnus, presión, distancias, proyecciones y estadísticos.

Funciones puras sobre arreglos de numpy, sin umbrales propios: los fijos físicos vienen de ``constantes`` (definiciones
de §2.3, §2.4, §2.5, §4.1 y §4.2) y los umbrales del Anexo A llegan por argumento. Toda suma va en float64.

Dueño: I3 (ola 1).
Lecturas propias (NUM-n), para el addendum de M1:
- NUM-1. ``hr_desde(t, td, hielo=True)`` lee Td como punto de escarcha: e = e_i(Td) sobre hielo y la HR siempre
  respecto del agua, HR = 100·e/e_s(T) (MC-25). Ni ``hr_desde`` ni ``td_desde_hr`` recortan: el recorte a [0, 100]
  de la HR del producto (§3) y el de 100 < HR ≤ 103 (marca 15) son reglas de sus módulos.
- NUM-2. ``mediana_mad`` devuelve el MAD sin escalar, mediana(|x − mediana|): el texto escribe el factor aparte
  («6 · 1,4826 · MAD_s», §2.4). Mira sólo los valores finitos; sin ninguno da (NaN, NaN).
- NUM-3. ``cuantil_ponderado`` (MC-48): el menor valor cuyo peso acumulado alcanza q·Σw, sin interpolar, con los
  valores ordenados de forma estable. Los pesos nulos no cuentan; un valor no finito, un peso negativo o no finito, o
  ningún peso positivo son un error (el que llama filtra antes).
- NUM-4. ``armonico_recortado`` (§4.3): diseño [1, cos(2πk·h/24), sen(2πk·h/24)] para k = 1…k_max, en ese orden;
  mínimos cuadrados; ``recorte`` es la fracción por cola (el que llama pasa ``U.frac("A_RECORTE_PCT")``, 0,1). Se
  quitan los ⌊recorte·n⌋ residuos más bajos y los ⌊recorte·n⌋ más altos del primer ajuste, por rango (empates por
  orden de llegada), y se ajusta una vez más sobre el resto. ``valor_armonico`` evalúa los coeficientes.
  **Rango deficiente** (H21 de la revisión de la ola 1). Con m horas distintas sobre el círculo de 24 h, el diseño de
  2·k_max + 1 columnas tiene rango completo si y sólo si m ≥ 2·k_max + 1. Si el primer ajuste o el segundo (tras el
  recorte) no tienen rango completo, se lanza ``DisenoDeficiente`` (un ValueError) en vez de dar la solución de norma
  mínima. Con los requisitos de §4.3 el primero nunca falla (hueco ≤ 4 h da ≥ 6 horas distintas, y k = 3 se usa sólo
  con ≥ 12); el segundo puede fallar si el recorte se lleva todas las horas de algunas horas UTC. Qué hace entonces
  quien llama (``candidatos``, I13) lo fija una pregunta al autor (informe de I3, ola 1): este módulo no decide.
- NUM-5. ``hueco_circular_max`` (MC-27): las horas son enteras (horas UTC o índices de hora del día civil); un valor no
  entero, no finito o booleano es un error, nunca se trunca (H21). Se toman módulo ``periodo`` (24 h, o la duración
  del día civil) y sin repetir; con una sola hora el hueco es ``periodo``, y sin ninguna también.
- NUM-6. ``generador`` (MC-44): ``SeedSequence([semilla, huella])``, con huella = el entero de los 32 bytes del
  sha256 de ``"/".join(partes)`` en UTF-8 (sin truncar). Así ``generador(S, "internos", "P2-4_83")`` es la subsecuencia
  de la etiqueta «internos/P2-4_83» y ningún muestreo depende del orden en que se llamen. Exige al menos una parte.
- NUM-7. ``remuestreo_bloques``: los ids distintos se ordenan; cada réplica sortea con reposición tantos bloques como
  hay, con ``generador(semilla, "remuestreo")``; devuelve los ids sorteados (réplicas × bloques).
- NUM-8. Mollweide: el diseño dice «EPSG:54009», que no existe en la base de PROJ; es ``ESRI:54009`` (World Mollweide,
  la de las teselas GHS-POP). UTM 19S es EPSG:32719. Las dos con ``always_xy`` (longitud, latitud).
- NUM-9. ``ridge_ponderado`` resuelve (X'X + α·D)·β = X'y con D diagonal, 0 en las ``sin_penalizar`` primeras
  columnas y 1 en el resto; las sumas X'X y X'y ya traen los pesos de las filas. **Qué columnas no se penalizan lo fija
  quien llama**: §4.6 («Regresión ridge … con predictores estandarizados») no dice si la constante se penaliza, y eso
  cambia C. Lo fija I13 (``candidatos``) como lectura del addendum de M1; este módulo no tiene valor por omisión que
  decida por él (``sin_penalizar = 0`` penaliza todo y sólo existe por la firma de §3).
Depende de: constantes.
"""
from __future__ import annotations

import hashlib
from functools import lru_cache

import numpy as np

from meteo_combinada import constantes

_A_AGUA, _B_AGUA, _C_AGUA = constantes.valor("MAGNUS_AGUA")
_A_HIELO, _B_HIELO, _C_HIELO = constantes.valor("MAGNUS_HIELO")
_P0_STD, _K_STD, _N_STD = constantes.valor("P_STD")
_Z_HIPSO, _P0_HIPSO, _N_HIPSO = constantes.valor("HIPSOMETRICA")
_R_SECO = constantes.valor("R_SECO")
_G = constantes.valor("GRAVEDAD")
_R_TIERRA_KM = constantes.valor("R_TIERRA_KM")

CRS_GEOGRAFICO = "EPSG:4326"
CRS_UTM19S = "EPSG:32719"      # P2 (§5.1)
CRS_MOLLWEIDE = "ESRI:54009"   # teselas GHS-POP (NUM-8)
PERIODO_DIA_H = 24             # armónicos de la hora UTC (§4.3)
PORCENTAJE = 100


# ---------------------------------------------------------------------------
# Humedad (§2.4, Magnus como meteo_civil_v3)
# ---------------------------------------------------------------------------
def magnus_agua(t_c):
    """e_s(T) = 6,112·exp(17,625·T/(243,04 + T)) en hPa (§2.4)."""
    t = np.asarray(t_c, dtype=np.float64)
    return _A_AGUA * np.exp(_B_AGUA * t / (_C_AGUA + t))


def magnus_hielo(t_c):
    """e_i(T) = 6,112·exp(22,46·T/(272,62 + T)) en hPa (§2.4)."""
    t = np.asarray(t_c, dtype=np.float64)
    return _A_HIELO * np.exp(_B_HIELO * t / (_C_HIELO + t))


def td_desde_e(e_hpa):
    """Magnus⁻¹ sobre agua: el punto de rocío (°C) de una presión de vapor (hPa)."""
    lg = np.log(np.asarray(e_hpa, dtype=np.float64) / _A_AGUA)
    return _C_AGUA * lg / (_B_AGUA - lg)


def hr_desde(t_c, td_c, *, hielo: bool = False):
    """HR = 100·e(Td)/e_s(T), sin recortar; con ``hielo``, e(Td) = e_i(Td) (punto de escarcha; MC-25, NUM-1)."""
    e = magnus_hielo(td_c) if hielo else magnus_agua(td_c)
    return PORCENTAJE * e / magnus_agua(t_c)


def td_desde_hr(hr, t_c):
    """Td = Magnus⁻¹(HR·e_s(T)/100) sobre agua (marca 10, §2.4)."""
    e = np.asarray(hr, dtype=np.float64) / PORCENTAJE * magnus_agua(t_c)
    return td_desde_e(e)


# ---------------------------------------------------------------------------
# Presión y altitud (§2.3, §4.1)
# ---------------------------------------------------------------------------
def p_std(z_m):
    """p_std(z) = 1.013,25·(1 − 2,25577·10⁻⁵·z)^5,25588 en hPa (§2.3)."""
    z = np.asarray(z_m, dtype=np.float64)
    return _P0_STD * (1.0 - _K_STD * z) ** _N_STD


def z_hipsometrica(sp_hpa):
    """z = 44.330,8·[1 − (sp/1.013,25)^0,190263] en m (§4.1)."""
    sp = np.asarray(sp_hpa, dtype=np.float64)
    return _Z_HIPSO * (1.0 - (sp / _P0_HIPSO) ** _N_HIPSO)


def presion_a_altitud(sp_hpa, t_k_medio, dz_m):
    """p′ = sp·exp(−9,80665·dz/(287,05·T̄)), con dz = z_x − z_i en m y T̄ en K (§4.1)."""
    sp = np.asarray(sp_hpa, dtype=np.float64)
    return sp * np.exp(-_G * np.asarray(dz_m, dtype=np.float64) / (_R_SECO * np.asarray(t_k_medio, dtype=np.float64)))


# ---------------------------------------------------------------------------
# Distancias y proyecciones (§4.2, §5.1)
# ---------------------------------------------------------------------------
def haversine_km(lat1, lon1, lat2, lon2):
    """Distancia por haversine con R = 6.371 km (§4.2, MC-60), con difusión de numpy."""
    p1, p2 = np.radians(np.asarray(lat1, dtype=np.float64)), np.radians(np.asarray(lat2, dtype=np.float64))
    dp = p2 - p1
    dl = np.radians(np.asarray(lon2, dtype=np.float64) - np.asarray(lon1, dtype=np.float64))
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * _R_TIERRA_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


@lru_cache(maxsize=None)
def _transformador(destino: str):
    from pyproj import Transformer
    return Transformer.from_crs(CRS_GEOGRAFICO, destino, always_xy=True)


def _proyectar(destino: str, lat, lon) -> tuple:
    lat = np.asarray(lat, dtype=np.float64)
    lon = np.asarray(lon, dtype=np.float64)
    x, y = _transformador(destino).transform(lon, lat)
    return np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)


def utm19s(lat, lon) -> tuple:
    """(E, N) en m, EPSG:32719 (P2, §5.1)."""
    return _proyectar(CRS_UTM19S, lat, lon)


def mollweide(lat, lon) -> tuple:
    """(x, y) en m, Mollweide mundial (ESRI:54009; NUM-8), la de las teselas GHS-POP."""
    return _proyectar(CRS_MOLLWEIDE, lat, lon)


# ---------------------------------------------------------------------------
# Estadísticos
# ---------------------------------------------------------------------------
def mediana_mad(x) -> tuple[float, float]:
    """(mediana, MAD sin escalar) de los valores finitos (NUM-2)."""
    v = np.asarray(x, dtype=np.float64).ravel()
    v = v[np.isfinite(v)]
    if v.size == 0:
        return float("nan"), float("nan")
    med = float(np.median(v))
    return med, float(np.median(np.abs(v - med)))


def cuantil_ponderado(x, w, q: float) -> float:
    """El menor valor cuyo peso acumulado alcanza q·Σw, sin interpolar (MC-48, NUM-3)."""
    x = np.asarray(x, dtype=np.float64).ravel()
    w = np.asarray(w, dtype=np.float64).ravel()
    if x.shape != w.shape:
        raise ValueError("cuantil_ponderado: x y w deben tener el mismo largo")
    if not (np.isfinite(x).all() and np.isfinite(w).all()) or (w < 0).any():
        raise ValueError("cuantil_ponderado: valores y pesos finitos, pesos ≥ 0")
    if not 0 <= q <= 1:
        raise ValueError("cuantil_ponderado: q en [0, 1]")
    total = w.sum()
    if not total > 0:
        raise ValueError("cuantil_ponderado: ningún peso positivo")
    orden = np.argsort(x, kind="stable")
    xs, acum = x[orden], np.cumsum(w[orden])
    positivo = w[orden] > 0
    i = int(np.flatnonzero((acum >= q * total) & positivo)[0])
    return float(xs[i])


class DisenoDeficiente(ValueError):
    """El diseño armónico no tiene rango completo (NUM-4): menos horas distintas que coeficientes."""


def _ajuste_completo(X: np.ndarray, r: np.ndarray, paso: str) -> np.ndarray:
    beta, _, rango, _ = np.linalg.lstsq(X, r, rcond=None)
    if rango < X.shape[1]:
        raise DisenoDeficiente(f"armonico_recortado: el {paso} ajuste tiene rango {rango} < {X.shape[1]} coeficientes "
                               "(menos horas distintas que coeficientes; NUM-4)")
    return beta


def _diseno_armonico(h, k_max: int) -> np.ndarray:
    h = np.asarray(h, dtype=np.float64).ravel()
    columnas = [np.ones_like(h)]
    for k in range(1, k_max + 1):
        angulo = 2 * np.pi * k * h / PERIODO_DIA_H
        columnas += [np.cos(angulo), np.sin(angulo)]
    return np.column_stack(columnas)


def valor_armonico(coefs, h):
    """Valor de los coeficientes de ``armonico_recortado`` en las horas ``h``."""
    coefs = np.asarray(coefs, dtype=np.float64)
    k_max = (coefs.size - 1) // 2
    if coefs.size != 1 + 2 * k_max:
        raise ValueError("valor_armonico: los coeficientes son [a0, α1, β1, …]")
    return np.matmul(_diseno_armonico(h, k_max), coefs)


def armonico_recortado(h, r, k_max: int, recorte: float):
    """Mínimos cuadrados armónicos, recorte por rango de cada cola y un segundo ajuste (§4.3, NUM-4).

    Devuelve [a0, α1, β1, …, α_kmax, β_kmax]; ``DisenoDeficiente`` si algún ajuste no tiene rango completo."""
    if isinstance(k_max, bool) or not isinstance(k_max, (int, np.integer)) or k_max < 1:
        raise ValueError("armonico_recortado: k_max entero ≥ 1")
    if not (0 <= recorte and 2 * recorte < 1):
        raise ValueError("armonico_recortado: recorte es una fracción por cola en [0; 0,5)")
    h = np.asarray(h, dtype=np.float64).ravel()
    r = np.asarray(r, dtype=np.float64).ravel()
    if h.shape != r.shape or not (np.isfinite(h).all() and np.isfinite(r).all()):
        raise ValueError("armonico_recortado: h y r finitos y del mismo largo")
    X = _diseno_armonico(h, int(k_max))
    if r.size < X.shape[1]:
        raise ValueError("armonico_recortado: menos valores que coeficientes")
    beta = _ajuste_completo(X, r, "primer")
    n_cola = int(np.floor(recorte * r.size))
    if n_cola == 0:
        return beta
    orden = np.argsort(r - np.matmul(X, beta), kind="stable")
    quedan = np.sort(orden[n_cola:r.size - n_cola])
    return _ajuste_completo(X[quedan], r[quedan], "segundo")


def ridge_ponderado(xtx, xty, alfa: float, *, sin_penalizar: int = 0):
    """(X'X + α·D)·β = X'y, con D = 0 en las ``sin_penalizar`` primeras columnas y 1 en el resto (NUM-9)."""
    xtx = np.asarray(xtx, dtype=np.float64)
    xty = np.asarray(xty, dtype=np.float64)
    p = xtx.shape[0]
    if xtx.shape != (p, p) or xty.shape[0] != p:
        raise ValueError("ridge_ponderado: X'X cuadrada y X'y con el mismo número de filas")
    if not alfa >= 0 or not 0 <= sin_penalizar <= p:
        raise ValueError("ridge_ponderado: α ≥ 0 y 0 ≤ sin_penalizar ≤ p")
    d = np.ones(p)
    d[:sin_penalizar] = 0.0
    return np.linalg.solve(xtx + alfa * np.diag(d), xty)


def hueco_circular_max(horas, periodo: int) -> int:
    """Mayor distancia, en horas, entre horas observadas consecutivas sobre un círculo de ``periodo`` (MC-27, NUM-5)."""
    if isinstance(periodo, bool) or not isinstance(periodo, (int, np.integer)) or periodo < 1:
        raise ValueError("hueco_circular_max: periodo entero ≥ 1")
    crudas = np.asarray(horas).ravel()
    if crudas.dtype == bool:
        raise ValueError("hueco_circular_max: las horas son enteras, no booleanas")
    if not np.issubdtype(crudas.dtype, np.integer):
        if crudas.size and not np.issubdtype(crudas.dtype, np.floating):
            raise ValueError("hueco_circular_max: las horas son enteras")
        if not (np.isfinite(crudas).all() and (crudas == np.floor(crudas)).all()):
            raise ValueError("hueco_circular_max: las horas son enteras; no se truncan (NUM-5)")
    hs = np.unique(np.mod(crudas.astype(np.int64), periodo))
    if hs.size <= 1:
        return int(periodo)
    huecos = np.diff(hs)
    return int(max(huecos.max(), hs[0] + periodo - hs[-1]))


def _huella(partes: tuple[str, ...]) -> int:
    if not partes or not all(isinstance(p, str) for p in partes):
        raise ValueError("generador: se exige al menos una parte de texto (la etiqueta de MC-44)")
    return int.from_bytes(hashlib.sha256("/".join(partes).encode("utf-8")).digest(), "big")


def generador(semilla: int, *partes: str):
    """``np.random.Generator`` (PCG64) de ``SeedSequence([semilla, huella(partes)])`` (MC-44, NUM-6)."""
    if isinstance(semilla, bool) or not isinstance(semilla, (int, np.integer)) or semilla < 0:
        raise ValueError("generador: semilla entera ≥ 0")
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence([int(semilla), _huella(partes)])))


def remuestreo_bloques(ids_bloque, n_replicas: int, semilla: int):
    """Réplicas × bloques: ids sorteados con reposición entre los ids distintos ordenados (NUM-7)."""
    ids = np.array(sorted({str(b) for b in ids_bloque}), dtype=object)
    if ids.size == 0:
        raise ValueError("remuestreo_bloques: sin bloques")
    if isinstance(n_replicas, bool) or not isinstance(n_replicas, (int, np.integer)) or n_replicas < 1:
        raise ValueError("remuestreo_bloques: n_replicas entero ≥ 1")
    rng = generador(semilla, "remuestreo")
    return ids[rng.integers(0, ids.size, size=(int(n_replicas), ids.size))]
