#!/usr/bin/env python3
"""Vecindario v2: ``obs_vec``, ``peso_vec`` y ``dist_est_km`` sin cualquier conjunto de estaciones excluidas.

Traduce §2 del contrato ``DISENO_AMBIENTAL_V2.md``. Los tres predictores que dependen de la red de estaciones
se recalculan en cada pliegue de LOSO-D, LBO-10, BLQ-75 y LRO, en las filas de entrenamiento y en las de
prueba, sin ninguna estación del conjunto excluido. **No hay atajo** para los conjuntos de una sola estación: la
v1 devolvía las matrices intactas cuando ``len(fuera) < 2`` (``qmd:2709``), de modo que la estación retenida
seguía en el ``obs_vec`` de todas las filas de entrenamiento. Es una sola función para todos los motores
(``Vecindario.recalcular``) y cada recálculo queda registrado (``config_v2.json`` → ``vecindario``).

Núcleo: el de la v1, tal como lo verificó el mapa ``auditoria/20261012/mapa_modelo_ambiental_v1.json``
(tema «vecinos_y_predictores»; ``qmd`` = ``docs/modelo_1km_horario.qmd``):

* media ponderada de Nadaraya–Watson con núcleo gaussiano, ``w = exp(−(d/150 km)²)`` (``_features.py:361``),
  con ``d`` haversine de radio 6371 km (``_features.py:330-334``) y sin radio de corte;
* observaciones del mismo contaminante en el mismo bin UTC exacto, sin rezagos (``_features.py:346``):
  ``obs_vec = Σ w·M·V / Σ w·M`` y ``peso_vec = Σ w·M``, con ``M = 1`` si la estación midió en ese bin y ``V``
  su valor (``_features.py:347-348`` y ``365-367``);
* la estación de la fila no entra en su propio vecindario (``_features.py:362-364``; el panel la excluye por
  nombre, ``qmd:2052-2053``);
* ``obs_vec`` es NaN si ``Σ w·M ≤ 1e-6`` (``_features.py:369``), y con ello si nadie midió en ese bin; si el
  bin no existe en el registro, NaN y peso 0 (``_features.py:370-371``);
* ``dist_est_km`` es estática, por contaminante: la distancia haversine a la estación más cercana distinta de
  la propia entre las columnas de la matriz de observaciones (``qmd:2055-2057``); en un pliegue, entre las que
  quedan (``qmd:2712``), también para las filas de prueba;
* las columnas de la matriz son las estaciones del panel del contaminante, en orden lexicográfico, como el
  pivote de ``qmd:2017``; sus coordenadas, las de ``estaciones_con_celda()`` (``qmd:2018`` y ``1968-1970``),
  que el manifiesto de pliegues guarda en float64.

Implementación (9,7 M filas de PM2,5 y 5,7 M de NO2):

* matrices por hora, estación × hora: ``V`` (valor, 0 donde falta) y ``M`` (0/1), de T ≈ 234 mil horas por S
  estaciones (107 y 57);
* ``W0`` (S × S) con el núcleo entre estaciones y la diagonal en cero: la propia nunca cuenta;
* sumas base con todas las estaciones, una sola vez: ``NUM0 = V·W0ᵀ``, ``DEN0 = M·W0ᵀ`` y ``CNT0 = M·[W0 > 0]ᵀ``
  (número de vecinas que midieron), leídas en la celda (hora, estación) de cada fila;
* descuento exacto de un conjunto excluido E: ``NUM = NUM0 − V[:, E]·W0[:, E]ᵀ``, y lo mismo con ``DEN`` y
  ``CNT``. Como la diagonal de ``W0`` es nula, la estación de la fila nunca se descuenta dos veces: las filas
  de prueba quedan sin E y las de entrenamiento pierden la contribución de E, sea E de una estación o de 28;
* dos guardas numéricas, para que el resultado sea el de la suma directa sobre las que quedan:
  1. si no queda ninguna vecina que haya medido (``CNT = 0``), ``NUM = DEN = 0`` exactos (``obs_vec`` NaN,
     ``peso_vec`` 0), en vez del residuo de redondeo de la resta;
  2. si lo excluido pesa más del 99,9 % del total (``DEN ≤ κ·DEN0`` o ``NUM ≤ κ·NUM0``, κ = 1e-3), la resta
     perdería dígitos por cancelación: esas filas se recalculan con la suma directa sobre las que quedan.
     Así el error relativo del descuento queda acotado por ~S·u/κ ≈ 1e-11 (u = 1,1e-16).

Valores ``V``: por omisión, la columna ``obs`` del panel v1 (float32, en sólo lectura), que es el insumo del
contrato (§0). La v1 armó su matriz con las observaciones en float64, antes de pasar el panel a float32
(``qmd:2058-2060``). Por eso, sin exclusiones, la v2 reproduce ``peso_vec`` y ``dist_est_km`` bit a bit y
``obs_vec`` a 1 ULP de float32 como máximo; esa es la cota que impone el redondeo de V. Con las observaciones
float64 reconstruidas desde las fuentes de la v1 (``validar_vecindario_v2.py``), la reproducción es bit a bit.

Diferencias deliberadas con la v1:

* sin el atajo ``len(fuera) < 2`` (``qmd:2709`` y ``3075``);
* las coordenadas de consulta van en float64 en todos los pliegues, como en la construcción del panel
  (``qmd:2052``). El recálculo por pliegue de la v1 (``qmd:2701``) las leía del panel ya guardado en float32
  (``qmd:2101``), mientras que las de las columnas seguían en float64;
* se exige un renglón por (estación, ts_utc). La v1 promediaba duplicados en el pivote (``qmd:2017``); el
  panel v1 no tiene ninguno.

Alcance: LPO no recalcula, porque usa la red concurrente (§1); ``para_pliegue`` le entrega el vecindario sin
exclusiones. El régimen de producción, con celdas que tienen monitor propio y la estación dentro del
vecindario (§2), no se evalúa aquí.

Uso como biblioteca::

    from vecindario_v2 import Vecindario
    vec = Vecindario.desde_panel("pm25")                 # panel v1 + manifiesto de pliegues (sólo lectura)
    rec = vec.para_pliegue(pliegue, "LRO")               # pliegue: un renglón de pliegues_v2.json
    Xtr = X[np.flatnonzero(rec.entrenamiento)]
    rec.asignar(Xtr, feats, filas=np.flatnonzero(rec.entrenamiento))
    vec.registro                                         # un dict por recálculo (huellas, filas, segundos)

Uso por consola (no escribe nada)::

    python -B scripts_modelo_1km/v2/vecindario_v2.py --contaminante pm25 --protocolo LRO --k 5
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _rutas_v2 import (  # noqa: E402
    RutasV2, ahora_utc, candado_escritura, cargar_config, leer_json, publicar_json, rutas_v2,
)
from _traza_v2 import sha256_archivo, traza  # noqa: E402
from pliegues_v2 import RADIO_TIERRA_KM, haversine_km, huella_pliegues, matriz_distancias  # noqa: E402

log = logging.getLogger("modelo_1km_v2.vecindario")

SCHEMA_REGISTRO = "airpollution.modelo-1km-v2.vecindario-registro.v1"
VARIABLES = ("obs_vec", "peso_vec", "dist_est_km")
H_KM_V1 = 150.0                     # ancho del núcleo de la v1 (_features.py:339 y 361)
UMBRAL_PESO_V1 = 1e-6               # Σw por debajo del cual obs_vec es NaN (_features.py:369)
KAPPA = 1e-3                        # descuento mal condicionado: lo que queda pesa ≤ 0,1 % → suma directa
LOTE_DIRECTO = 200_000              # filas por lote en la suma directa (el lote de _features.py:339)
PROTOCOLOS_ESPACIALES = ("LOSO-D", "LBO-10", "BLQ-75", "LRO")
PROTOCOLO_TEMPORAL = "LPO"
COLUMNAS_PANEL = ["estacion", "ts_utc", "obs", "anio", "lat_est", "lon_est"]
METODOS = ("descuento", "directo")


# ---------------------------------------------------------------------------
# Núcleo y utilidades (funciones puras)
# ---------------------------------------------------------------------------
def nucleo_gaussiano(d_km, h_km: float = H_KM_V1) -> np.ndarray:
    """``w = exp(−(d/h)²)``; réplica de ``_features.py:361``."""
    return np.exp(-(np.asarray(d_km, dtype="float64") / float(h_km)) ** 2)


def _limitar_hilos(n: int | None):
    """Tope de hilos de BLAS durante los productos de matrices (threadpoolctl, si está)."""
    if not n:
        return contextlib.nullcontext()
    try:
        from threadpoolctl import threadpool_limits
    except ImportError:                                  # sin threadpoolctl rige OPENBLAS_NUM_THREADS
        return contextlib.nullcontext()
    return threadpool_limits(limits=int(n), user_api="blas")


def _sha256_arreglo(a: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def _categorias_ordenadas(estacion) -> pd.Categorical:
    """Códigos de estación con las categorías en orden lexicográfico y sin categorías vacías: el mismo orden
    de columnas que el pivote de la v1 (``qmd:2017``)."""
    if isinstance(estacion, pd.Series):
        estacion = estacion.array
    if isinstance(estacion, pd.Categorical):
        nombres = [str(c) for c in estacion.categories]
        if len(set(nombres)) != len(nombres):
            raise ValueError("categorías de estación repetidas al pasarlas a texto")
        cat = pd.Categorical.from_codes(estacion.codes, categories=nombres)
    else:
        cat = pd.Categorical(np.asarray(estacion, dtype=object).astype(str))
    cat = cat.remove_unused_categories()
    cat = cat.reorder_categories(sorted(cat.categories))
    if (cat.codes < 0).any():
        raise ValueError("hay filas sin estación")
    return cat


def _coordenadas_de(coordenadas, estaciones: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(lat, lon) float64 de cada estación, desde un DataFrame (estacion, lat, lon) o un dict
    ``{estacion: (lat, lon)}``."""
    if isinstance(coordenadas, pd.DataFrame):
        c = coordenadas[["estacion", "lat", "lon"]].copy()
        c["estacion"] = c["estacion"].astype(str)
        if c.drop_duplicates().duplicated("estacion").any():
            raise ValueError("una estación con dos coordenadas distintas")
        tabla = {s: (float(a), float(b)) for s, a, b in c.drop_duplicates("estacion").itertuples(index=False)}
    else:
        tabla = {str(s): (float(v[0]), float(v[1])) for s, v in dict(coordenadas).items()}
    faltan = [s for s in estaciones if s not in tabla]
    if faltan:
        raise ValueError(f"estaciones sin coordenadas: {faltan}")
    lat = np.array([tabla[s][0] for s in estaciones], dtype="float64")
    lon = np.array([tabla[s][1] for s in estaciones], dtype="float64")
    if not (np.isfinite(lat).all() and np.isfinite(lon).all()):
        raise ValueError("coordenadas no finitas")
    return lat, lon


# ---------------------------------------------------------------------------
# Resultado de un recálculo
# ---------------------------------------------------------------------------
@dataclass
class Recalculo:
    """Los tres predictores para **todas** las filas de la tabla del vecindario (el panel), en su orden.

    ``entrenamiento`` y ``prueba`` son máscaras booleanas sobre esas filas cuando el recálculo es de un
    pliegue; las filas excluidas que no son de prueba (el entorno de LBO-10) no están en ninguna de las dos.
    """

    obs_vec: np.ndarray
    peso_vec: np.ndarray
    dist_est_km: np.ndarray
    registro: dict
    entrenamiento: np.ndarray | None = None
    prueba: np.ndarray | None = None

    def columnas(self, filas=None) -> np.ndarray:
        """Matriz (n, 3) con ``obs_vec``, ``peso_vec`` y ``dist_est_km`` de ``filas`` (todas, si es None)."""
        sel = slice(None) if filas is None else filas
        return np.column_stack([self.obs_vec[sel], self.peso_vec[sel], self.dist_est_km[sel]])

    def asignar(self, X: np.ndarray, feats, filas=None) -> np.ndarray:
        """Escribe in situ en ``X`` las columnas del vecindario que estén en ``feats``; la fila i de ``X`` es la
        fila ``filas[i]`` de la tabla (todas, en orden, si ``filas`` es None). Es lo que hacía la función
        ``ajuste`` de la v1 sobre ``Xtr`` y ``Xte`` (``qmd:2713-2720``)."""
        feats = list(feats)
        sel = slice(None) if filas is None else filas
        for c in VARIABLES:
            if c in feats:
                X[:, feats.index(c)] = getattr(self, c)[sel]
        return X


# ---------------------------------------------------------------------------
# Vecindario de un contaminante
# ---------------------------------------------------------------------------
class Vecindario:
    """Matrices estación × hora y sumas base de un contaminante, listas para recalcular por pliegue.

    ``estacion``, ``ts_utc`` y ``obs`` describen una fila por (estación, hora), en el orden de la tabla (el
    panel); ``obs`` NaN cuenta como «no midió». ``coordenadas`` da (lat, lon) float64 por estación. ``anio`` (año
    local de cada fila) sólo hace falta para LPO.
    """

    def __init__(self, pol: str, estacion, ts_utc, obs, coordenadas, *, anio=None, h_km: float = H_KM_V1,
                 umbral: float = UMBRAL_PESO_V1, kappa: float = KAPPA, hilos: int | None = None,
                 insumos: Mapping[str, Path] | None = None, origen: str = "tabla"):
        t0 = time.perf_counter()
        self.pol = str(pol)
        self.h_km, self.umbral, self.kappa = float(h_km), float(umbral), float(kappa)
        if not (self.h_km > 0 and self.umbral >= 0 and 0 < self.kappa < 1):
            raise ValueError("parámetros del núcleo fuera de rango")
        self.hilos = None if hilos is None else int(hilos)
        self.insumos = dict(insumos or {})
        self.origen = str(origen)

        cat = _categorias_ordenadas(estacion)
        self.estaciones = np.asarray(cat.categories, dtype=object)
        self.js = cat.codes.astype(np.int32)
        ts = pd.DatetimeIndex(np.asarray(ts_utc, dtype="datetime64[ns]"))
        obs = np.asarray(obs, dtype="float64")
        n = len(self.js)
        if len(ts) != n or len(obs) != n:
            raise ValueError("estacion, ts_utc y obs deben tener el mismo largo")
        if ts.hasnans:
            raise ValueError("hay filas sin ts_utc")
        it, tiempos = pd.factorize(ts, sort=True)
        self.tiempos = pd.DatetimeIndex(tiempos)
        self.it = it.astype(np.int32)
        self.n = n
        T, S = len(self.tiempos), len(self.estaciones)
        self.flat = self.it.astype(np.int64) * S + self.js
        if np.bincount(self.flat, minlength=T * S).max(initial=0) > 1:
            raise ValueError("hay (estación, ts_utc) repetidos: la v2 exige un renglón por par (la v1 los "
                             "promediaba en el pivote, qmd:2017; el panel v1 no tiene ninguno)")
        medido = np.isfinite(obs)
        V = np.zeros(T * S, dtype="float64")
        M = np.zeros(T * S, dtype="float64")
        V[self.flat[medido]] = obs[medido]
        M[self.flat[medido]] = 1.0
        self.V, self.M = V.reshape(T, S), M.reshape(T, S)
        self.anio = None if anio is None else np.asarray(anio).astype(np.int16)
        if self.anio is not None and len(self.anio) != n:
            raise ValueError("anio debe tener una entrada por fila")

        self.lat, self.lon = _coordenadas_de(coordenadas, self.estaciones)
        self.D = matriz_distancias(self.lat, self.lon)            # S × S, filas = consulta (qmd:2055)
        self.W0 = nucleo_gaussiano(self.D, self.h_km)
        np.fill_diagonal(self.W0, 0.0)                            # la propia no cuenta (_features.py:362-364)
        self.P0 = (self.W0 > 0).astype("float64")                 # vecina con peso positivo (para contar)
        self.Dinf = self.D.copy()
        np.fill_diagonal(self.Dinf, np.inf)                       # distinta de la propia (qmd:2056)
        with _limitar_hilos(self.hilos):
            self._num0 = np.take(self.V @ self.W0.T, self.flat)
            self._den0 = np.take(self.M @ self.W0.T, self.flat)
            self._cnt0 = np.take(self.M @ self.P0.T, self.flat)
        self._huella_insumos = self._calcular_huella(obs, ts)
        self.registro: list[dict] = []
        self.segundos_construccion = round(time.perf_counter() - t0, 3)
        log.info("%s: vecindario de %s filas, %d estaciones × %s horas (%.1f s)", self.pol, f"{n:,}", S, f"{T:,}",
                 self.segundos_construccion)

    # --- Construcción desde el panel v1 ---------------------------------------
    @classmethod
    def desde_panel(cls, pol: str, rutas: RutasV2 | None = None, *, manifiesto: dict | None = None,
                    cfg: dict | None = None, hilos: int | None = None, verificar_sha: bool = True,
                    kappa: float = KAPPA) -> "Vecindario":
        """Vecindario de ``pol`` sobre las filas del panel v1 (sólo lectura), con las coordenadas float64 del
        manifiesto de pliegues y el núcleo de ``config_v2.json``. Verifica que el panel sea el que fijó el
        manifiesto (sha256) y que sus coordenadas float32 sean las del manifiesto redondeadas."""
        import pyarrow.parquet as pq

        r = rutas or rutas_v2()
        cfg = cfg if cfg is not None else cargar_config(r)
        imp = cfg["vecindario"]["implementacion"]
        h_km, umbral = float(imp["ancho_km"]), float(imp["umbral_suma_de_pesos"])
        if (h_km, umbral) != (H_KM_V1, UMBRAL_PESO_V1):
            raise SystemExit(f"config_v2.json fija un núcleo distinto del de la v1 ({h_km} km, {umbral}); el "
                             f"contrato (§2) pide el de la v1: revisa la configuración")
        hilos = int(cfg["operacion"]["hilos_maximos"]) if hilos is None else int(hilos)
        if manifiesto is None:
            manifiesto = leer_json(r.manifiesto_pliegues)
            if manifiesto is None:
                raise SystemExit(f"Falta el manifiesto de pliegues {r.relativa(r.manifiesto_pliegues)}")
        if huella_pliegues(manifiesto) != manifiesto.get("huella_pliegues"):
            raise SystemExit("El manifiesto de pliegues no calza con su propia huella; no se usa")
        info = manifiesto["contaminantes"][pol]["panel"]
        ruta = r.panel(pol)
        if not ruta.exists():
            raise SystemExit(f"Falta el panel v1 {r.relativa(ruta)}")
        if verificar_sha:
            sha = sha256_archivo(ruta)
            if sha != info["sha256"]:
                raise SystemExit(f"{pol}: el panel en disco (sha256 {sha[:16]}) no es el del manifiesto "
                                 f"({info['sha256'][:16]})")
        df = pq.read_table(ruta, columns=COLUMNAS_PANEL, read_dictionary=["estacion"]).to_pandas()
        coords = {e["estacion"]: (e["lat"], e["lon"]) for e in manifiesto["estaciones"]}
        cat = _categorias_ordenadas(df["estacion"])
        nombres = [str(s) for s in cat.categories]
        if nombres != sorted(manifiesto["contaminantes"][pol]["estaciones"]):
            raise SystemExit(f"{pol}: las estaciones del panel no son las del manifiesto")
        lat32 = np.array([coords[s][0] for s in nombres], dtype="float32")
        lon32 = np.array([coords[s][1] for s in nombres], dtype="float32")
        codigos = cat.codes
        if not (np.array_equal(df["lat_est"].to_numpy(), lat32[codigos])
                and np.array_equal(df["lon_est"].to_numpy(), lon32[codigos])):
            raise SystemExit(f"{pol}: lat_est/lon_est del panel no son las coordenadas del manifiesto en float32")
        insumos = {f"panel_{pol}": ruta, "manifiesto_pliegues": r.manifiesto_pliegues}
        if r.panel_meta(pol).exists():
            insumos[f"panel_{pol}_json"] = r.panel_meta(pol)
        return cls(pol, cat, df["ts_utc"].to_numpy(), df["obs"].to_numpy(), coords, anio=df["anio"].to_numpy(),
                   h_km=h_km, umbral=umbral, kappa=kappa, hilos=hilos, insumos=insumos,
                   origen=f"panel v1 (obs float32, sha256 {info['sha256'][:16]})")

    # --- Identidad ----------------------------------------------------------
    def _calcular_huella(self, obs: np.ndarray, ts: pd.DatetimeIndex) -> str:
        h = hashlib.sha256()
        h.update(json.dumps({"contaminante": self.pol, "estaciones": [str(s) for s in self.estaciones],
                             "parametros": self.parametros(con_tamano=False)}, sort_keys=True).encode("utf-8"))
        for a in (self.lat, self.lon, self.js, ts.asi8, obs):
            h.update(np.ascontiguousarray(a).tobytes())
        return h.hexdigest()

    def huella(self) -> dict:
        """Identidad del vecindario base: estaciones, coordenadas, parámetros y filas (estación, ts_utc, obs)."""
        return {"huella": self._huella_insumos, "filas": int(self.n), "estaciones": int(len(self.estaciones)),
                "horas": int(len(self.tiempos)), "origen": self.origen}

    def parametros(self, con_tamano: bool = True) -> dict:
        p = {"nucleo": "gaussiano, w = exp(-(d/h)^2) (_features.py:361)", "ancho_km": self.h_km,
             "distancia": "haversine (_features.py:330-334)", "radio_tierra_km": RADIO_TIERRA_KM,
             "bin": "ts_utc exacto, concurrente (_features.py:346)",
             "propia": "fuera de su vecindario: diagonal de W0 nula (_features.py:362-364)",
             "umbral_suma_de_pesos": self.umbral, "kappa_descuento": self.kappa,
             "dist_est_km": "haversine a la estación más cercana distinta de la propia entre las que quedan (qmd:2055-2057, 2712)",
             "atajo_conjuntos_de_una_estacion": False}
        if con_tamano:
            p.update({"filas": int(self.n), "estaciones": int(len(self.estaciones)), "horas": int(len(self.tiempos)),
                      "fuente_valores": self.origen, "hilos_blas": self.hilos})
        return p

    def traza(self, rutas: RutasV2 | None = None, semillas=None) -> dict:
        """Procedencia (§0): commit, hash del código, sha256 de los insumos, bibliotecas, hilos y semillas."""
        return traza(self.insumos, semillas if semillas is not None else {"nota": "sin azar: cálculo determinista"},
                     int(self.hilos or 0), rutas=rutas or rutas_v2(), parametros=self.parametros())

    # --- Utilidades -------------------------------------------------------------
    def indices(self, nombres: Iterable) -> np.ndarray:
        """Índices (ordenados, sin repetir) de las estaciones ``nombres``; un nombre ajeno a la red es un error."""
        nombres = [str(s) for s in nombres]
        pos = pd.Index(self.estaciones).get_indexer(nombres)
        ajenas = sorted({s for s, p in zip(nombres, pos) if p < 0})
        if ajenas:
            raise ValueError(f"{self.pol}: estaciones que no están en la red del contaminante: {ajenas}")
        return np.unique(pos.astype(np.int64))

    def matriz_O(self) -> pd.DataFrame:
        """La matriz tiempo × estación de la v1 (``qmd:2017``): NaN donde la estación no midió."""
        return pd.DataFrame(np.where(self.M > 0, self.V, np.nan), index=self.tiempos,
                            columns=pd.Index(self.estaciones, name="estacion"))

    def distancias(self, excluidas: Iterable = ()) -> pd.Series:
        """``dist_est_km`` por estación con ``excluidas`` fuera (float64)."""
        quedan = self._quedan(self.indices(excluidas))
        return pd.Series(self.Dinf[:, quedan].min(axis=1), index=pd.Index(self.estaciones, name="estacion"),
                         name="dist_est_km")

    def _quedan(self, E: np.ndarray) -> np.ndarray:
        quedan = np.ones(len(self.estaciones), dtype=bool)
        quedan[E] = False
        if not quedan.any():
            raise ValueError(f"{self.pol}: el conjunto excluido deja la red vacía")
        return quedan

    # --- Sumas -------------------------------------------------------------------
    def _suma_directa(self, filas: np.ndarray, quedan: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """``Σ w·V`` y ``Σ w·M`` sobre las estaciones que quedan, fila a fila (por lotes)."""
        WR = self.W0 * quedan[None, :]
        num = np.empty(len(filas), dtype="float64")
        den = np.empty(len(filas), dtype="float64")
        for ini in range(0, len(filas), LOTE_DIRECTO):
            f = filas[ini:ini + LOTE_DIRECTO]
            Wf, t = WR[self.js[f]], self.it[f]
            num[ini:ini + len(f)] = np.sum(Wf * self.V[t], axis=1)
            den[ini:ini + len(f)] = np.sum(Wf * self.M[t], axis=1)
        return num, den

    def _descuento(self, E: np.ndarray, quedan: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
        if len(E) == 0:
            vacio = self._cnt0 < 0.5
            return (self._num0.copy(), self._den0.copy(),
                    {"filas_con_descuento": 0, "filas_suma_directa": 0, "filas_sin_vecinas": int(vacio.sum())})
        WE, PE = self.W0[:, E].T, self.P0[:, E].T                  # k × S
        VE, ME = self.V[:, E], self.M[:, E]                        # T × k
        with _limitar_hilos(self.hilos):
            num = self._num0 - np.take(VE @ WE, self.flat)
            den = self._den0 - np.take(ME @ WE, self.flat)
            sc = np.take(ME @ PE, self.flat)
        cnt = self._cnt0 - sc                                      # enteros exactos en float64
        tocada = sc > 0.5                                          # alguna excluida midió en esa hora
        vacio = cnt < 0.5                                          # no queda ninguna vecina que haya medido
        mal = tocada & ~vacio & ((den <= self.kappa * self._den0) | (num <= self.kappa * self._num0))
        num[vacio] = 0.0
        den[vacio] = 0.0
        filas_mal = np.flatnonzero(mal)
        if len(filas_mal):
            num[filas_mal], den[filas_mal] = self._suma_directa(filas_mal, quedan)
        return num, den, {"filas_con_descuento": int(tocada.sum()), "filas_suma_directa": int(len(filas_mal)),
                          "filas_sin_vecinas": int(vacio.sum())}

    def _directo(self, quedan: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
        """Suma directa sobre las que quedan, con las matrices completas (verificación del descuento)."""
        WR, PR = self.W0 * quedan[None, :], self.P0 * quedan[None, :]
        with _limitar_hilos(self.hilos):
            num = np.take(self.V @ WR.T, self.flat)
            den = np.take(self.M @ WR.T, self.flat)
            cnt = np.take(self.M @ PR.T, self.flat)
        vacio = cnt < 0.5
        num[vacio] = 0.0
        den[vacio] = 0.0
        return num, den, {"filas_con_descuento": 0, "filas_suma_directa": int(self.n),
                          "filas_sin_vecinas": int(vacio.sum())}

    # --- La función única de recálculo -------------------------------------------
    def recalcular(self, excluidas: Iterable = (), *, metodo: str = "descuento", precision: str = "float32",
                   contexto: dict | None = None, entrenamiento: np.ndarray | None = None,
                   prueba: np.ndarray | None = None, huellas: bool = True, registrar: bool = True) -> Recalculo:
        """``obs_vec``, ``peso_vec`` y ``dist_est_km`` de todas las filas sin las estaciones ``excluidas``.

        La estación de cada fila queda siempre fuera de su propio vecindario. ``metodo="descuento"`` (el de
        producción) parte de las sumas base y resta las contribuciones de las excluidas; ``"directo"`` suma
        sobre las que quedan con las matrices completas, y sólo sirve para verificar. ``precision`` es
        ``"float32"`` (como el panel) o ``"float64"``. Cada llamada agrega un renglón a ``self.registro``
        (``registrar=False`` lo omite, sólo para las verificaciones); el renglón viaja también en el resultado.
        """
        t0 = time.perf_counter()
        if metodo not in METODOS:
            raise ValueError(f"método desconocido: {metodo!r} (usa {METODOS})")
        if precision not in ("float32", "float64"):
            raise ValueError("precision debe ser 'float32' o 'float64'")
        E = self.indices(excluidas)
        quedan = self._quedan(E)
        num, den, info = self._descuento(E, quedan) if metodo == "descuento" else self._directo(quedan)
        with np.errstate(invalid="ignore", divide="ignore"):
            obs_vec = np.where(den > self.umbral, num / den, np.nan)      # _features.py:369
        dist_est = self.Dinf[:, quedan].min(axis=1)
        dist = dist_est[self.js]
        peso = den
        if precision == "float32":
            obs_vec, peso, dist = obs_vec.astype("float32"), peso.astype("float32"), dist.astype("float32")
        reg = {"utc": ahora_utc(), "contaminante": self.pol, **(contexto or {}), "metodo": metodo,
               "excluidas": [str(self.estaciones[i]) for i in E], "n_excluidas": int(len(E)),
               "filas": int(self.n), **info,
               "obs_vec_nan": int(np.isnan(obs_vec).sum()), "precision": precision,
               "dist_est_km_inf": [str(s) for s, d in zip(self.estaciones, dist_est) if not np.isfinite(d)]}
        for nombre, mascara in (("entrenamiento", entrenamiento), ("prueba", prueba)):
            if mascara is not None:
                mascara = np.asarray(mascara, dtype=bool)
                if mascara.shape != (self.n,):
                    raise ValueError(f"la máscara de {nombre} debe tener una entrada por fila")
                reg[f"filas_{nombre}"] = int(mascara.sum())
                reg[f"obs_vec_nan_{nombre}"] = int(np.isnan(obs_vec[mascara]).sum())
        if huellas:
            reg["sha256"] = {"obs_vec": _sha256_arreglo(obs_vec), "peso_vec": _sha256_arreglo(peso),
                             "dist_est_km": _sha256_arreglo(dist)}
        reg["vecindario"] = self._huella_insumos
        reg["segundos"] = round(time.perf_counter() - t0, 4)
        if registrar:
            self.registro.append(reg)
        return Recalculo(obs_vec, peso, dist, reg, entrenamiento, prueba)

    def base(self, **kw) -> Recalculo:
        """Sin exclusiones (sólo la propia estación): debe reproducir las columnas del panel v1."""
        return self.recalcular((), contexto={"protocolo": "base"}, **kw)

    def mascaras(self, pliegue: dict, protocolo: str) -> tuple[np.ndarray, np.ndarray, list[str]]:
        """(entrenamiento, prueba, excluidas) de un pliegue del manifiesto ``pliegues_v2.json``."""
        excluidas = [str(s) for s in pliegue.get("excluidas", [])]
        if protocolo == PROTOCOLO_TEMPORAL or "exclusion_temporal" in pliegue:
            if excluidas:
                raise ValueError("LPO no excluye estaciones del vecindario (§1)")
            if self.anio is None:
                raise ValueError("LPO necesita el año local de cada fila (anio)")
            et = pliegue["exclusion_temporal"]
            prueba = (self.anio >= int(et["anio_desde"])) & (self.anio <= int(et["anio_hasta"]))
            return ~prueba, prueba, []
        if protocolo not in PROTOCOLOS_ESPACIALES:
            raise ValueError(f"protocolo desconocido: {protocolo!r}")
        E, P = self.indices(excluidas), self.indices(pliegue.get("estaciones_prueba", []))
        if len(P) == 0 or not set(P.tolist()) <= set(E.tolist()):
            raise ValueError(f"pliegue {pliegue.get('grupo')}: estaciones de prueba vacías o fuera del conjunto excluido")
        en_E = np.zeros(len(self.estaciones), dtype=bool)
        en_P = np.zeros(len(self.estaciones), dtype=bool)
        en_E[E], en_P[P] = True, True
        return ~en_E[self.js], en_P[self.js], excluidas

    def para_pliegue(self, pliegue: dict, protocolo: str, **kw) -> Recalculo:
        """Recálculo de un pliegue del manifiesto: sin su conjunto excluido, con sus máscaras de entrenamiento
        y de prueba. En LPO, el vecindario sin exclusiones (red concurrente, §1)."""
        entrenamiento, prueba, excluidas = self.mascaras(pliegue, protocolo)
        contexto = {"protocolo": protocolo, "k": pliegue.get("k"), "grupo": pliegue.get("grupo")}
        if protocolo == PROTOCOLO_TEMPORAL:
            contexto["vecindario"] = "red concurrente, sin recálculo (§1)"
        return self.recalcular(excluidas, contexto=contexto, entrenamiento=entrenamiento, prueba=prueba, **kw)

    # --- Registro --------------------------------------------------------------
    def publicar_registro(self, ruta, rutas: RutasV2 | None = None, extra: dict | None = None,
                          semillas=None) -> str:
        """Escribe el registro de recálculos con su traza (en la raíz v2 o en ``output_files/modelo_1km_v2``,
        con candado y escritura atómica). Devuelve el sha256 del JSON."""
        r = rutas or rutas_v2()
        doc = {"schema": SCHEMA_REGISTRO, "contaminante": self.pol, "vecindario": self.huella(),
               "parametros": self.parametros(), **(extra or {}), "recalculos": self.registro,
               "traza": self.traza(r, semillas)}
        with candado_escritura("vecindario", rutas=r):
            return publicar_json(doc, ruta, r)


# ---------------------------------------------------------------------------
# Referencia ingenua (réplica literal de la v1) para las pruebas
# ---------------------------------------------------------------------------
def obs_vecinas_directo(O: pd.DataFrame, lat_e, lon_e, ts, lat_q, lon_q, excluir=None,
                        h_km: float = H_KM_V1, lote: int = 200_000, precision: str = "float32"):
    """Réplica literal de ``obs_vecinas_para`` (``_features.py:337-374``): pesos fila a fila por lotes, la propia
    estación fuera por nombre y sumas con ``np.sum``. ``precision="float64"`` sólo cambia el tipo de salida."""
    ts = np.asarray(ts, dtype="datetime64[ns]")
    idx_t = O.index.get_indexer(pd.DatetimeIndex(ts))
    V = np.nan_to_num(O.to_numpy(dtype="float64"))
    M = O.notna().to_numpy(dtype="float64")
    cols = O.columns.to_numpy()
    lat_e, lon_e = np.asarray(lat_e, dtype="float64"), np.asarray(lon_e, dtype="float64")
    tipo = "float32" if precision == "float32" else "float64"
    obs_vec = np.full(len(ts), np.nan, tipo)
    peso_vec = np.zeros(len(ts), tipo)
    for ini in range(0, len(ts), lote):
        fin = min(ini + lote, len(ts))
        sel = np.arange(ini, fin)
        it = idx_t[sel]
        valido = it >= 0
        if not valido.any():
            continue
        D = haversine_km(np.asarray(lat_q)[sel][:, None], np.asarray(lon_q)[sel][:, None],
                         lat_e[None, :], lon_e[None, :])
        W = np.exp(-(D / h_km) ** 2)
        if excluir is not None:
            propio = np.asarray(excluir)[sel][:, None] == cols[None, :]
            W = np.where(propio, 0.0, W)
        Wv = W * M[np.clip(it, 0, None)]
        num = np.sum(Wv * V[np.clip(it, 0, None)], axis=1)
        den = np.sum(Wv, axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            val = np.where(den > 1e-6, num / den, np.nan)
        val[~valido] = np.nan
        den[~valido] = 0.0
        obs_vec[sel] = val.astype(tipo)
        peso_vec[sel] = den.astype(tipo)
    return obs_vec, peso_vec


def recalculo_directo_v1(O: pd.DataFrame, lat_e, lon_e, estacion_fila, ts, lat_q, lon_q, excluidas,
                         h_km: float = H_KM_V1, precision: str = "float32"):
    """Réplica de ``ajuste_por_red`` (``qmd:2698-2721``) **sin** el atajo de ``qmd:2709``: la matriz restringida a
    las estaciones que quedan, ``obs_vecinas_para`` con la propia fuera y la distancia mínima entre las que
    quedan. Las coordenadas de consulta se pasan tal cual (la v2 las usa en float64)."""
    nombres = O.columns.to_numpy()
    lat_e, lon_e = np.asarray(lat_e, dtype="float64"), np.asarray(lon_e, dtype="float64")
    queda = ~np.isin(nombres, np.asarray(list(excluidas), dtype=object))
    D = haversine_km(lat_e[:, None], lon_e[:, None], lat_e[None, :], lon_e[None, :])
    np.fill_diagonal(D, np.inf)
    ov, pv = obs_vecinas_directo(O.loc[:, queda], lat_e[queda], lon_e[queda], ts, lat_q, lon_q,
                                 excluir=np.asarray(estacion_fila), h_km=h_km, precision=precision)
    dist = pd.Series(D[:, queda].min(axis=1), index=nombres).reindex(np.asarray(estacion_fila))
    return ov, pv, dist.to_numpy(dtype="float32" if precision == "float32" else "float64")


# ---------------------------------------------------------------------------
# Consola
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Recalcula el vecindario v2 de uno o más pliegues (no escribe nada).")
    ap.add_argument("--contaminante", required=True, choices=("pm25", "no2"))
    ap.add_argument("--protocolo", choices=(*PROTOCOLOS_ESPACIALES, PROTOCOLO_TEMPORAL),
                    help="sin protocolo, sólo el vecindario base frente a las columnas del panel")
    ap.add_argument("--k", type=int, nargs="*", help="pliegues del protocolo (todos si se omite)")
    ap.add_argument("--hilos", type=int, default=None, help="tope de hilos de BLAS (config: operacion.hilos_maximos)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    r = rutas_v2()
    m = leer_json(r.manifiesto_pliegues)
    vec = Vecindario.desde_panel(args.contaminante, r, manifiesto=m, hilos=args.hilos)
    if args.protocolo is None:
        import pyarrow.parquet as pq

        rec = vec.base()
        p = pq.read_table(r.panel(args.contaminante), columns=list(VARIABLES)).to_pandas()
        for c in VARIABLES:
            a, b = getattr(rec, c), p[c].to_numpy()
            ulp = np.abs(a.view(np.int32).astype(np.int64) - b.view(np.int32).astype(np.int64))
            ok = ~(np.isnan(a) | np.isnan(b))
            print(f"{c}: NaN iguales {bool(np.array_equal(np.isnan(a), np.isnan(b)))}; bit a bit "
                  f"{int((ulp[ok] == 0).sum()):,} de {int(ok.sum()):,}; ULP máx {int(ulp[ok].max(initial=0))}")
        return 0
    pliegues = m["contaminantes"][args.contaminante]["protocolos"][args.protocolo]["pliegues"]
    for f in pliegues:
        if args.k and f["k"] not in args.k:
            continue
        rec = vec.para_pliegue(f, args.protocolo)
        g = rec.registro
        print(f"{args.protocolo} k={f['k']:>3} {f['grupo']:<28} excluidas {g['n_excluidas']:>2}  entrenamiento "
              f"{g['filas_entrenamiento']:>9,}  prueba {g['filas_prueba']:>9,}  suma directa {g['filas_suma_directa']:>7,}"
              f"  NaN prueba {g['obs_vec_nan_prueba']:>6,}  {g['segundos']:.2f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
