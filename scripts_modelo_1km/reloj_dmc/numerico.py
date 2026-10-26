"""Utilidades numéricas puras compartidas por las líneas, las guardas, la red y C3.

Sin estado, sin E/S, sin pandas en las firmas salvo donde se indica. Doble precisión siempre.
- Semilla y remuestreo por bloques de 5 días (§4.0).
- Paso nativo de una serie de etiquetas (§3.2): la única regla, que usan extraccion y lineas_fisicas.
- Correlación de Pearson, máximo estricto e interpolación parabólica (§4.3.1).
- Ajuste armónico por mínimos cuadrados con EE × 2, φ1 y ψ2 (§4.4), y quitar el armónico de 24 h.
- Ecuación del tiempo de Spencer y hora solar (§4.4).
- Estadística circular, envolturas de A3/A5 y distancias.
- z_pix (§3.3) y redondeo con empates hacia 0 (E1b).
Depende de: constantes (fórmulas). Los umbrales llegan como argumentos.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date

import numpy as np

from reloj_dmc import constantes

# Constantes del cuerpo del texto (constantes.py, con su fragmento literal). Se leen de POR_NOMBRE y
# no de ``constantes.valor`` para no depender del orden en que se implementan los módulos.
_C = constantes.POR_NOMBRE
_SPENCER = tuple(float(v) for v in _C["SPENCER"].valor)       # 229,18 y los cinco coeficientes (§4.4)
_SPENCER_DIAS = float(_C["SPENCER_B"].valor)                  # B = 2π(n − 1)/365
_Z_PIX = tuple(float(v) for v in _C["Z_PIX"].valor)           # 44.330,8; 1.013,25; 0,190263 (§3.3)
_SEMILLA_BYTES = int(_C["SEMILLA_BYTES"].valor)                # digest()[:8] (§4.0)

# Definiciones, no umbrales: 360°/24 h = 15° de longitud por hora («λ/15», §4.4; exacto en doble
# precisión) y el radio terrestre medio de dmc_features (R_TIERRA_KM, riesgo R-21).
GRADOS_POR_HORA = float(np.degrees(2 * np.pi)) / 24
R_TIERRA_KM = 6371.0088

# Por debajo de esta longitud resultante la dirección media circular no está definida.
_RESULTANTE_MIN = 1e-12

# Mínimo de pares de la correlación de Pearson. El texto no lo fija: con 2 pares r vale siempre ±1 y no informa, así
# que es parte de la definición, no un umbral (PEN-4 de C1; antes era un literal tolerado en test_umbrales).
PEARSON_MIN_PARES = 3  # no-umbral: definición de la correlación (con 2 pares, r = ±1 siempre)

VARIABLES_SEMILLA = ("Ts", "QFE")                              # R-13
_UNIDAD_PARTE = re.compile(r"(\d{4})-(\d{2})-([1-9]\d*)")      # «AAAA-MM-n»
_UNIDAD_REGIMEN = ("R0", "R1")
_UNIDAD_VERSION = re.compile(r"V-[0-9a-f]{8}")                 # G-versión (R-40)
_NS_POR_HORA = int(np.timedelta64(1, "h").astype("timedelta64[ns]").astype(np.int64))


# ---------------------------------------------------------------------------
# Semilla y remuestreo por bloques (§4.0)
# ---------------------------------------------------------------------------
def semilla(base: int, codigo: str, anio: int, unidad: str, variable: str) -> int:
    """``int.from_bytes(sha256(f"{base}|{codigo}|{anio}|{unidad}|{variable}".encode()).digest()[:8], "big")``.

    ``unidad``: «AAAA-MM-n» (parte) o «R0»/«R1» (año-régimen); «V-<sha8>» en G-versión (R-40).
    ``variable``: «Ts» o «QFE» (riesgo R-13: el texto no fija la cadena; se usa el nombre del campo
    del artefacto). La cadena se codifica en UTF-8. Cualquier otra forma lanza ValueError, porque un
    error en la cadena cambiaría las réplicas sin que nadie lo note.
    """
    if isinstance(base, bool) or not isinstance(base, (int, np.integer)):
        raise ValueError(f"base de semilla no entera: {base!r}")
    if isinstance(anio, bool) or not isinstance(anio, (int, np.integer)):
        raise ValueError(f"año no entero: {anio!r}")
    if not isinstance(codigo, str) or not codigo or "|" in codigo:
        raise ValueError(f"código inválido para la semilla: {codigo!r}")
    if variable not in VARIABLES_SEMILLA:
        raise ValueError(f"variable de semilla fuera de {VARIABLES_SEMILLA}: {variable!r}")
    if not isinstance(unidad, str):
        raise ValueError(f"unidad no es texto: {unidad!r}")
    parte = _UNIDAD_PARTE.fullmatch(unidad)
    if parte:
        if int(parte.group(1)) != int(anio):
            raise ValueError(f"la parte {unidad!r} no es del año {anio}")
        if not 1 <= int(parte.group(2)) <= 12:
            raise ValueError(f"mes inválido en la parte {unidad!r}")
    elif unidad not in _UNIDAD_REGIMEN and not _UNIDAD_VERSION.fullmatch(unidad):
        raise ValueError(f"unidad de semilla inválida: {unidad!r}")
    texto = f"{int(base)}|{codigo}|{int(anio)}|{unidad}|{variable}"
    return int.from_bytes(hashlib.sha256(texto.encode("utf-8")).digest()[:_SEMILLA_BYTES], "big")


def generador(semilla_: int) -> np.random.Generator:
    """``numpy.random.Generator(PCG64(semilla))``."""
    return np.random.Generator(np.random.PCG64(int(semilla_)))


def bloques_de_dias(fechas: np.ndarray, primer_dia: date, dias_bloque: int) -> np.ndarray:
    """Índice de bloque de cada fecha de etiqueta: (fecha − primer_dia).days // dias_bloque.

    ``primer_dia`` es el primer día calendario de la unidad (no el primer día con datos; R-42).
    ``fechas`` puede traer etiquetas completas (datetime64 o datetime ingenuos): cuenta su fecha de
    etiqueta. Una fecha anterior a ``primer_dia`` o ausente (NaT) es un error del llamador.
    """
    if isinstance(dias_bloque, bool) or int(dias_bloque) != dias_bloque or dias_bloque < 1:
        raise ValueError(f"dias_bloque debe ser un entero ≥ 1: {dias_bloque!r}")
    dias = np.asarray(fechas).astype("datetime64[D]")
    if np.isnat(dias).any():
        raise ValueError("fechas ausentes (NaT) en los bloques")
    desde = np.datetime64(primer_dia, "D")
    delta = (dias - desde).astype(np.int64)
    if delta.size and delta.min() < 0:
        raise ValueError(f"hay fechas anteriores al primer día de la unidad ({primer_dia})")
    return delta // int(dias_bloque)


def replicas_por_bloques(bloques: np.ndarray, n_replicas: int, rng: np.random.Generator) -> list[np.ndarray]:
    """Índices de filas de cada réplica: se sortean con reposición tantos bloques no vacíos como haya.

    Secuencia fija: para r = 1 … n, ``rng.integers(0, B, size=B)`` sobre la lista ordenada de bloques
    no vacíos; las filas de cada bloque sorteado se concatenan en orden (el de ``bloques``).
    Sin bloques (B = 0) devuelve n réplicas vacías y no consume el generador.
    """
    bloques = np.asarray(bloques)
    if bloques.ndim != 1:
        raise ValueError("bloques debe ser un arreglo de una dimensión")
    if int(n_replicas) != n_replicas or n_replicas < 0:
        raise ValueError(f"n_replicas inválido: {n_replicas!r}")
    if bloques.size == 0:
        return [np.empty(0, dtype=np.int64) for _ in range(int(n_replicas))]
    orden = np.argsort(bloques, kind="stable")              # filas agrupadas por bloque, en su orden
    _, inicio, cuenta = np.unique(bloques[orden], return_index=True, return_counts=True)
    n_bloques = len(inicio)
    replicas = []
    for _ in range(int(n_replicas)):
        sorteo = rng.integers(0, n_bloques, size=n_bloques)
        largos = cuenta[sorteo]
        # posición k-ésima de cada bloque sorteado: inicio del bloque + k
        base = np.repeat(inicio[sorteo] - (np.cumsum(largos) - largos), largos)
        replicas.append(orden[base + np.arange(largos.sum())].astype(np.int64))
    return replicas


# ---------------------------------------------------------------------------
# Paso nativo (§3.2)
# ---------------------------------------------------------------------------
def paso_nativo(etiquetas: np.ndarray) -> int | None:
    """Diferencia más frecuente (h) entre etiquetas consecutivas con valor; empate → la menor.

    Las etiquetas se ordenan y se toman sin repetir; None si hay menos de dos. Deben ser horas enteras
    (ValueError si no). No juzga si p está en PASOS_NATIVOS: eso lo decide quien llama. Es la única regla
    del paquete: ``extraccion.paso_nativo`` (p_v de los meses y rachas del control propio) y
    ``lineas_fisicas.pasos_por_mes`` (E3 y E4) la llaman.
    """
    t = np.asarray(etiquetas)
    if t.size == 0:
        return None
    t = t.astype("datetime64[ns]")
    t = np.unique(t[~np.isnat(t)])
    if len(t) < 2:
        return None
    d = np.diff(t).astype(np.int64)
    if (d % _NS_POR_HORA != 0).any():
        raise ValueError("paso_nativo recibe etiquetas que no son horas enteras")
    horas, cuentas = np.unique(d // _NS_POR_HORA, return_counts=True)
    return int(horas[np.argmax(cuentas)])       # np.unique ordena: el primer máximo es el menor paso


# ---------------------------------------------------------------------------
# Correlación (§4.3.1)
# ---------------------------------------------------------------------------
def _correlaciones(dy: np.ndarray, dx: np.ndarray) -> np.ndarray:
    """Núcleo común de ``pearson`` y ``correlaciones_por_desfase`` (mismas operaciones, mismos bits)."""
    n = dy.shape[0]
    r = np.full(dx.shape[0], np.nan)
    if n < PEARSON_MIN_PARES or np.all(dy == dy[0]):
        return r
    yc = dy - dy.mean()
    xc = dx - dx.mean(axis=1, keepdims=True)
    sxy = np.sum(xc * yc, axis=1)
    sxx = np.sum(xc * xc, axis=1)
    syy = np.sum(yc * yc)
    validas = ~np.all(dx == dx[:, :1], axis=1)              # varianza nula exacta → NaN
    r[validas] = sxy[validas] / np.sqrt(sxx[validas] * syy)
    return r


def pearson(x: np.ndarray, y: np.ndarray) -> float:
    """Correlación de Pearson en float64, sin redondeo; NaN si n < PEARSON_MIN_PARES (3) o varianza nula.

    Un NaN en las entradas da NaN (los pares M ya traen valores finitos).
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if x.ndim != 1 or x.shape != y.shape:
        raise ValueError("pearson exige dos vectores del mismo largo")
    return float(_correlaciones(y, x[np.newaxis, :])[0])


def correlaciones_por_desfase(dy: np.ndarray, dx_por_c: np.ndarray) -> np.ndarray:
    """r(c) para cada fila de ``dx_por_c`` (forma 19 × n) contra ``dy`` (n). Devuelve 19 valores.

    Cada valor es idéntico, bit a bit, a ``pearson(dx_por_c[i], dy)``.
    """
    dy = np.asarray(dy, dtype=np.float64)
    dx = np.ascontiguousarray(dx_por_c, dtype=np.float64)
    if dy.ndim != 1 or dx.ndim != 2 or dx.shape[1] != dy.shape[0]:
        raise ValueError("correlaciones_por_desfase exige dy (n) y dx_por_c (k × n)")
    return _correlaciones(dy, dx)


def desfases_ventana(umbrales) -> tuple[int, ...]:
    """c = −E3_VENTANA … +E3_VENTANA (Anexo B, «ventana ±9», §4.3.1), en orden creciente.

    Única regla de la ventana de E3: la usan ``lineas_fisicas.ventana`` y quien llame a
    ``maximo_estricto`` o a ``interpolar_parabola``. El ancho llega con los umbrales, como todo umbral.
    """
    n = int(umbrales.f("E3_VENTANA"))
    return tuple(range(-n, n + 1))


def maximo_estricto(r: np.ndarray, desfases: tuple[int, ...]) -> int | None:
    """ĉ = el c de mayor r(c); None si hay un empate exacto en el máximo o r es todo NaN.

    ``desfases`` es la ventana de ``desfases_ventana(U)``, en el orden de r.
    Los NaN no compiten. El empate se juzga con igualdad exacta en doble precisión (§4.3.1).
    """
    r = np.asarray(r, dtype=np.float64)
    if r.shape != (len(desfases),):
        raise ValueError(f"r tiene {r.shape} valores y la ventana {len(desfases)}")
    finitos = ~np.isnan(r)
    if not finitos.any():
        return None
    maximo = r[finitos].max()
    en_maximo = np.flatnonzero(r == maximo)
    if len(en_maximo) != 1:
        return None
    return int(desfases[en_maximo[0]])


def interpolar_parabola(r: np.ndarray, c_hat: int, desfases: tuple[int, ...],
                        c_max: int = _C["E3_CCONT_MAX"].valor) -> float | None:
    """ĉ_cont = ĉ + [r(ĉ−1) − r(ĉ+1)] / (2[r(ĉ−1) − 2r(ĉ) + r(ĉ+1)]); None si |ĉ| > c_max.

    También None si ĉ no está definido, si falta un vecino en la ventana, si alguno de los tres
    valores es NaN o si el denominador es 0 (no ocurre cuando ĉ es un máximo estricto).
    """
    if c_hat is None:
        return None
    c_hat = int(c_hat)
    if abs(c_hat) > c_max:
        return None
    r = np.asarray(r, dtype=np.float64)
    posicion = {int(c): i for i, c in enumerate(desfases)}
    if r.shape != (len(desfases),) or any(c not in posicion for c in (c_hat - 1, c_hat, c_hat + 1)):
        return None
    r_menos, r_0, r_mas = r[posicion[c_hat - 1]], r[posicion[c_hat]], r[posicion[c_hat + 1]]
    denominador = 2 * (r_menos - 2 * r_0 + r_mas)
    if not np.isfinite(denominador) or denominador == 0:
        return None
    return float(c_hat + (r_menos - r_mas) / denominador)


def es_alias_12(c_hat: int, c_h: int, periodo: int = _C["ALIAS_H"].valor) -> bool:
    """ĉ ≡ c_H (mód 12) y ĉ ≠ c_H (§4.3.1). Ver la contradicción R-01 sobre la prueba 11.

    R-01 (diseño, §7.1): con c = L − u (§2.1), el único alias de 12 h de c_H = −4 dentro de la
    ventana [−9, 9] es ĉ = +8; −8 es el alias de +4. La prueba 11 de §8 escribe «−8 con F(−4)», que
    contradice esta definición; aquí manda la definición de §4.3.1 y la prueba se corrige por enmienda.
    """
    c_hat, c_h = int(c_hat), int(c_h)
    return (c_hat - c_h) % int(periodo) == 0 and c_hat != c_h


# ---------------------------------------------------------------------------
# Armónicos (§4.4) y serie filtrada (§4.3.1)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AjusteArmonico:
    K: int
    alfa: tuple[float, ...]
    beta: tuple[float, ...]
    amplitudes: tuple[float, ...]       # A_k
    ee_amplitudes: tuple[float, ...]    # EE de A_k ya multiplicados por el factor (× 2)
    phi1: float                         # (24/2π)·atan2(β1, α1) mód 24
    psi2: float | None                  # (12/2π)·atan2(β2, α2) mód 12 (None si K < 2)
    n: int


def _diseno_armonico(t: np.ndarray, K: int, periodo: float, constante: bool) -> np.ndarray:
    """Columnas [1,] cos(2πk·t/P), sen(2πk·t/P) para k = 1 … K, en ese orden (α_k, β_k alternados)."""
    fase = 2 * np.pi * np.mod(t, periodo) / periodo
    columnas = [np.ones_like(fase)] if constante else []
    for k in range(1, K + 1):
        columnas += [np.cos(k * fase), np.sin(k * fase)]
    return np.column_stack(columnas)


def ajuste_armonico(t_horas: np.ndarray, a: np.ndarray, K: int, factor_ee: float,
                    periodo: float = 24.0) -> AjusteArmonico:
    """a = Σ_{k=1..K}[α_k cos(2πk·t/24) + β_k sen(2πk·t/24)] + e, sin constante (a ya es anomalía).

    Mínimos cuadrados (``numpy.linalg.lstsq``). EE de α_k y β_k: σ̂²·(XᵀX)⁻¹ con σ̂² = RSS/(n − 2K);
    EE de A_k por el método delta, multiplicado por ``factor_ee`` (§4.4: × 2). NaN si n ≤ 2K o A_k = 0.
    φ1 = (P/2π)·atan2(β1, α1) mód P y ψ2 = (P/4π)·atan2(β2, α2) mód P/2: la hora del máximo de cada
    armónico, en las unidades de t. Entradas no finitas o un diseño de rango incompleto lanzan ValueError.
    """
    t = np.asarray(t_horas, dtype=np.float64)
    y = np.asarray(a, dtype=np.float64)
    if t.ndim != 1 or t.shape != y.shape:
        raise ValueError("ajuste_armonico exige t y a del mismo largo")
    if isinstance(K, bool) or int(K) != K or K < 1:
        raise ValueError(f"K debe ser un entero ≥ 1: {K!r}")
    K = int(K)
    if not (np.isfinite(t).all() and np.isfinite(y).all()):
        raise ValueError("ajuste_armonico exige valores finitos")
    X = _diseno_armonico(t, K, periodo, constante=False)
    n, p = X.shape
    coef, _, rango, _ = np.linalg.lstsq(X, y, rcond=None)
    if rango < p:
        raise ValueError(f"diseño armónico de rango incompleto ({rango} < {p}) con K = {K}")
    alfa, beta = coef[0::2], coef[1::2]
    amplitudes = np.hypot(alfa, beta)
    if n > p:
        residuo = y - X @ coef
        sigma2 = float(residuo @ residuo) / (n - p)
        cov = sigma2 * np.linalg.inv(X.T @ X)
        ee = np.full(K, np.nan)
        for k in range(K):
            if amplitudes[k] > 0:
                va, vb, cab = cov[2 * k, 2 * k], cov[2 * k + 1, 2 * k + 1], cov[2 * k, 2 * k + 1]
                var_a = (alfa[k] ** 2 * va + beta[k] ** 2 * vb + 2 * alfa[k] * beta[k] * cab) / amplitudes[k] ** 2
                ee[k] = np.sqrt(max(var_a, 0.0))
        ee = ee * factor_ee
    else:
        ee = np.full(K, np.nan)
    phi1 = float(envolver(periodo / (2 * np.pi) * np.arctan2(beta[0], alfa[0]), 0.0, periodo))
    psi2 = None
    if K >= 2:
        psi2 = float(envolver(periodo / 2 / (2 * np.pi) * np.arctan2(beta[1], alfa[1]), 0.0, periodo / 2))
    return AjusteArmonico(K=K, alfa=tuple(float(v) for v in alfa), beta=tuple(float(v) for v in beta),
                          amplitudes=tuple(float(v) for v in amplitudes),
                          ee_amplitudes=tuple(float(v) for v in ee), phi1=phi1, psi2=psi2, n=int(n))


def K_de_n_h(n_h: int, k_max: int) -> int:
    """K = mín(k_max, ⌊(n_h − 1)/2⌋) (§4.4); 0 si n_h < 3 (no hay ajuste posible)."""
    return max(0, min(int(k_max), (int(n_h) - 1) // 2))


def quitar_armonico_24(t_horas: np.ndarray, y: np.ndarray,
                       periodo: float = float(_C["PERIODO_FILTRO_H"].valor)) -> np.ndarray:
    """Residuo de y tras mínimos cuadrados con constante, coseno y seno de período 24 h (§4.3.1).

    El ajuste usa sólo los valores finitos de y; donde y es NaN el residuo es NaN. El residuo de
    mínimos cuadrados es único aunque el diseño sea de rango incompleto (p. ej., paso de 12 h).
    No supone ningún reloj: t es la hora de etiqueta (QFE) o la hora UTC (sp), según el llamador.
    """
    t = np.asarray(t_horas, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if t.ndim != 1 or t.shape != y.shape:
        raise ValueError("quitar_armonico_24 exige t e y del mismo largo")
    if not np.isfinite(t).all():
        raise ValueError("quitar_armonico_24 exige horas finitas")
    salida = np.full(y.shape, np.nan)
    finitos = np.isfinite(y)
    if not finitos.any():
        return salida
    X = _diseno_armonico(t[finitos], 1, periodo, constante=True)
    coef, _, _, _ = np.linalg.lstsq(X, y[finitos], rcond=None)
    salida[finitos] = y[finitos] - X @ coef
    return salida


# ---------------------------------------------------------------------------
# Ecuación del tiempo y hora solar (§4.4)
# ---------------------------------------------------------------------------
def ecuacion_del_tiempo_min(n_dia: np.ndarray) -> np.ndarray:
    """Spencer: B = 2π(n − 1)/365; EoT en minutos (coeficientes de constantes.SPENCER).

    EoT = 229,18·(0,000075 + 0,001868 cos B − 0,032077 sen B − 0,014615 cos 2B − 0,040849 sen 2B):
    hora solar aparente menos hora solar media (positiva a comienzos de noviembre).
    """
    escala, c0, c1, s1, c2, s2 = _SPENCER
    B = 2 * np.pi * (np.asarray(n_dia, dtype=np.float64) - 1) / _SPENCER_DIAS
    return escala * (c0 + c1 * np.cos(B) + s1 * np.sin(B) + c2 * np.cos(2 * B) + s2 * np.sin(2 * B))


def hora_solar(etiquetas: np.ndarray, lon_este: float) -> np.ndarray:
    """t0(L) = (hora decimal de L + λ/15 + EoT/60) mód 24, con n = día del año de la fecha de L (R-22).

    ``etiquetas``: etiquetas ingenuas (datetime64 o datetime). λ en grados este (Chile: negativa).
    """
    L = np.asarray(etiquetas).astype("datetime64[ns]")
    if np.isnat(L).any():
        raise ValueError("etiquetas ausentes (NaT) en hora_solar")
    dia = L.astype("datetime64[D]")
    enero_1 = L.astype("datetime64[Y]").astype("datetime64[D]")
    n = (dia - enero_1).astype(np.int64) + 1
    hora = (L - dia.astype("datetime64[ns]")).astype(np.int64) / (3600 * 1e9)
    t0 = hora + float(lon_este) / GRADOS_POR_HORA + ecuacion_del_tiempo_min(n) / 60
    return np.asarray(envolver(t0, 0.0, 24.0), dtype=np.float64)


# ---------------------------------------------------------------------------
# Estadística circular, distancias y otros
# ---------------------------------------------------------------------------
def distancia_circular(a: np.ndarray | float, b: np.ndarray | float, periodo: float) -> np.ndarray | float:
    """Distancia en el círculo de período ``periodo``, en [0, periodo/2]."""
    d = np.mod(np.abs(np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64)), periodo)
    d = np.minimum(d, periodo - d)
    return float(d) if d.ndim == 0 else d


def envolver(x: np.ndarray | float, desde: float, periodo: float) -> np.ndarray | float:
    """Lleva x a [desde, desde + periodo)."""
    y = desde + np.mod(np.asarray(x, dtype=np.float64) - desde, periodo)
    y = np.where(y >= desde + periodo, desde, y)            # borde exacto por redondeo
    return float(y) if y.ndim == 0 else y


def media_circular(x: np.ndarray, periodo: float) -> float:
    """Dirección media circular de 2π·x/periodo, devuelta en las unidades de x (A5).

    El resultado queda en [−periodo/2, periodo/2) (A5: [−0,5; 0,5) con período 1 h). NaN si no hay
    valores o si la resultante es nula (dirección indefinida).
    """
    x = np.asarray(x, dtype=np.float64).ravel()
    if x.size == 0 or not np.isfinite(x).all():
        return float("nan")
    angulo = 2 * np.pi * x / periodo
    s, c = np.mean(np.sin(angulo)), np.mean(np.cos(angulo))
    if np.hypot(s, c) < _RESULTANTE_MIN:
        return float("nan")
    return float(envolver(np.arctan2(s, c) * periodo / (2 * np.pi), -periodo / 2, periodo))


def media_circular_en(x: np.ndarray, intervalo: tuple[float, float]) -> float:
    """``media_circular`` con período ``hasta − desde``, llevada a [desde, hasta). Es el estadístico m de A5
    (intervalo A5_ENVOLVER) y, con la Enmienda 3 (B6), el ρ de §4.3.5: la misma función para los dos. NaN si
    ``media_circular`` lo es."""
    desde, hasta = intervalo
    periodo = hasta - desde
    m = media_circular(x, periodo)
    return float(envolver(m, desde, periodo)) if np.isfinite(m) else float("nan")


def _xyz(lat, lon) -> np.ndarray:
    """Vector unitario, como ``dmc_features._xyz``."""
    a, b = np.deg2rad(np.asarray(lat, dtype=np.float64)), np.deg2rad(np.asarray(lon, dtype=np.float64))
    return np.stack([np.cos(a) * np.cos(b), np.cos(a) * np.sin(b), np.sin(a)], axis=-1)


def distancia_km(lat1: float, lon1: float, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    """Gran círculo (haversine) con R = 6371,0088 km, como dmc_features (R-21).

    Se calcula como dmc_features: 2·asen(‖p2 − p1‖/2)·R con vectores unitarios (cuerda), que es
    algebraicamente la fórmula de haversine.
    """
    p1 = _xyz(lat1, lon1)
    p2 = _xyz(lat2, lon2)
    cuerda = np.linalg.norm(p2 - p1, axis=-1)
    return 2 * np.arcsin(np.clip(cuerda / 2, 0, 1)) * R_TIERRA_KM


def z_pixel(sp_medio_hpa: float) -> float:
    """z_pix = 44.330,8·[1 − (sp̄/1.013,25)^0,190263] m (§3.3)."""
    escala, p0, exponente = _Z_PIX
    return float(escala * (1 - (float(sp_medio_hpa) / p0) ** exponente))


def redondear_empate_hacia_cero(x: float) -> int:
    """Redondeo al entero más cercano; los empates (…,5) van hacia 0 (§4.1.2)."""
    x = float(x)
    if not np.isfinite(x):
        raise ValueError(f"no se puede redondear {x!r}")
    magnitud = abs(x)
    entero = np.floor(magnitud)
    if 2 * (magnitud - entero) > 1:                       # más de media unidad: hacia afuera
        entero += 1
    return int(np.copysign(entero, x)) if entero else 0
