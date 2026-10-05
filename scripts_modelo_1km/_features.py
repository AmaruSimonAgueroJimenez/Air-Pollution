"""Ensamblaje de predictores: el mismo código para estaciones y para la grilla.

Una fila es (celda, bin horario UTC). Los predictores horarios se toman del
píxel nativo enlazado a la celda en el bin correspondiente; los satelitales
diarios se calculan por celda y fecha local (UTC−4) y se propagan a las 24
horas del día; las estáticas y anuales se unen por celda y año. Ninguna
fuente se interpola espacial ni temporalmente: los huecos quedan NaN y el
modelo (LightGBM) los trata como valores faltantes.
"""
from __future__ import annotations

import os
from collections import OrderedDict, deque
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

import sys  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comun_modelo import (  # noqa: E402
    ESTATICAS_PATH, GRILLA_DIR, LULC_PATH, OFFSET_UTC_H, MesNativo, acag_mes,
    acag_meses_disponibles,
    cargar_celdas, cargar_enlaces, fechas, leer_mes_geoscf, leer_mes_nativo, leer_orbita_no2, log,
    maiac_dia, orbitas_no2_dia,
)

FEATURES_HORARIAS = {
    "era5land": {"t2m": "el_t2m", "d2m": "el_d2m", "sp": "el_sp", "u10": "el_u10", "v10": "el_v10",
                 "tp_1h_mm": "el_tp_1h_mm"},
    "era5blh": {"blh": "blh"},
    "merra2": {"t2m": "m2_t2m", "rh2m": "m2_rh2m", "u10m": "m2_u10m", "v10m": "m2_v10m",
               "pblh": "m2_pblh", "aod_m2": "m2_aod", "pm25_m2": "m2_pm25", "ps": "m2_ps"},
    "cams": {"no2": "cams_no2", "pm25": "cams_pm25", "o3": "cams_o3", "co": "cams_co"},
    "geoscf": {"no2": "gcf_no2", "pm25": "gcf_pm25", "o3": "gcf_o3", "co": "gcf_co"},
}
PASO_H = {"era5land": 1, "era5blh": 1, "merra2": 1, "cams": 3, "geoscf": 1}
M_AIRE, M_NO2, M_O3, M_CO = 28.9647, 46.0055, 47.9982, 28.0101
COLUMNAS_SATELITE = ("aod_terra", "aod_aqua", "aod_dia", "aod_n", "aod_3d", "aod_7d",
                     "no2_trop", "no2_trop_prec", "no2_trop_hora", "no2_trop_7d", "no2_trop_15d")


class FuentesHorarias:
    """Caché de meses nativos (máximo ``capacidad`` por producto)."""

    def __init__(self, productos=("era5land", "era5blh", "merra2", "cams", "geoscf"), capacidad: int = 2):
        self.productos = tuple(productos)
        self.capacidad = capacidad
        self._cache: dict[str, OrderedDict[str, MesNativo | None]] = {p: OrderedDict() for p in self.productos}
        self.faltantes: set[tuple[str, str]] = set()

    def mes(self, producto: str, yyyymm: str) -> MesNativo | None:
        cache = self._cache[producto]
        if yyyymm in cache:
            cache.move_to_end(yyyymm)
            return cache[yyyymm]
        m = leer_mes_geoscf(yyyymm) if producto == "geoscf" else leer_mes_nativo(producto, yyyymm)
        if m is None:
            self.faltantes.add((producto, yyyymm))
        cache[yyyymm] = m
        while len(cache) > self.capacidad:
            cache.popitem(last=False)
        return m

    def extraer(self, producto: str, ts_utc: np.ndarray, pixel: np.ndarray) -> dict[str, np.ndarray]:
        """Series por variable para filas (ts_utc, pixel) agrupadas por mes."""
        ts_utc = np.asarray(ts_utc, dtype="datetime64[ns]")
        pixel = np.asarray(pixel, dtype="int64")
        salida = {col: np.full(len(ts_utc), np.nan, dtype="float32")
                  for col in FEATURES_HORARIAS[producto].values()}
        idx = pd.DatetimeIndex(ts_utc)
        meses = (idx.year.to_numpy() * 100 + idx.month.to_numpy()).astype("int64")
        for clave in np.unique(meses):
            yyyymm = f"{clave // 100:04d}{clave % 100:02d}"
            m = self.mes(producto, yyyymm)
            if m is None:
                continue
            sel = np.flatnonzero(meses == clave) if len(np.unique(meses)) > 1 else slice(None)
            it = m.indice_tiempo(ts_utc[sel], PASO_H[producto])
            ip = m.indice_pixel(pixel[sel])
            for var, col in FEATURES_HORARIAS[producto].items():
                if var in m.datos:
                    salida[col][sel] = m.extraer(var, it, ip)
        return salida


def derivadas_horarias(df: pd.DataFrame) -> pd.DataFrame:
    """Humedad relativa, viento, unidades de CAMS y variables físico-informadas."""
    if {"el_t2m", "el_d2m"}.issubset(df.columns):
        t, td = df["el_t2m"] - 273.15, df["el_d2m"] - 273.15
        es = 6.112 * np.exp(17.67 * t / (t + 243.5))
        e = 6.112 * np.exp(17.67 * td / (td + 243.5))
        df["el_rh"] = (100.0 * e / es).clip(0, 100).astype("float32")
    if {"el_u10", "el_v10"}.issubset(df.columns):
        df["el_wind"] = np.sqrt(df["el_u10"] ** 2 + df["el_v10"] ** 2).astype("float32")
        ang = np.arctan2(df["el_u10"], df["el_v10"])
        df["el_wdir_sin"] = np.sin(ang).astype("float32")
        df["el_wdir_cos"] = np.cos(ang).astype("float32")
    if "cams_no2" in df:
        df["cams_no2"] = (df["cams_no2"] * (M_AIRE / M_NO2) * 1e9).astype("float32")   # kg/kg → ppb
    if "cams_o3" in df:
        df["cams_o3"] = (df["cams_o3"] * (M_AIRE / M_O3) * 1e9).astype("float32")
    if "cams_co" in df:
        df["cams_co"] = (df["cams_co"] * (M_AIRE / M_CO) * 1e9).astype("float32")
    if "cams_pm25" in df:
        df["cams_pm25"] = (df["cams_pm25"] * 1e9).astype("float32")                      # kg/m³ → µg/m³
    if "blh" in df:
        df["inv_blh"] = (1.0 / df["blh"].clip(lower=50.0)).astype("float32")
    if {"m2_aod", "m2_pblh"}.issubset(df.columns):
        df["m2_aod_pblh"] = (df["m2_aod"] / df["m2_pblh"].clip(lower=50.0) * 1000.0).astype("float32")
    if {"gcf_pm25", "blh"}.issubset(df.columns):
        df["gcf_pm25_blh"] = (df["gcf_pm25"] / df["blh"].clip(lower=50.0) * 1000.0).astype("float32")
    return df


def calendario(df: pd.DataFrame, ts_col: str = "ts_utc") -> pd.DataFrame:
    local = pd.to_datetime(df[ts_col]) - pd.Timedelta(hours=OFFSET_UTC_H)
    h = local.dt.hour.to_numpy()
    doy = local.dt.dayofyear.to_numpy()
    df["hora_local"] = h.astype("int8")
    df["hora_sin"] = np.sin(2 * np.pi * h / 24).astype("float32")
    df["hora_cos"] = np.cos(2 * np.pi * h / 24).astype("float32")
    df["doy_sin"] = np.sin(2 * np.pi * doy / 365.25).astype("float32")
    df["doy_cos"] = np.cos(2 * np.pi * doy / 365.25).astype("float32")
    df["dow"] = local.dt.dayofweek.to_numpy().astype("int8")
    df["mes"] = local.dt.month.to_numpy().astype("int8")
    df["anio"] = local.dt.year.to_numpy().astype("int16")
    df["fecha_local"] = local.dt.normalize()
    return df


class SatelitesDiarios:
    """Predictores satelitales por celda y fecha local, con ventanas móviles.

    Los días se piden en orden cronológico; la clase conserva los últimos 15
    días para las medias móviles (MAIAC 3 y 7 días; TROPOMI 7 y 15 días).
    ``celdas`` puede ser un subconjunto (p. ej. las celdas con estación).
    """

    def __init__(self, celdas: pd.DataFrame, enlaces: pd.DataFrame, *, criterio_maiac: str = "estricta",
                 qa_no2_min: float = 0.75, radio_no2_km: float = 5.0):
        from scipy.spatial import cKDTree

        self.celdas = celdas[["celda", "lat", "lon"]].reset_index(drop=True)
        enl = enlaces.set_index("celda")
        self.maiac_pixel = enl.loc[self.celdas["celda"], "maiac_pixel"].to_numpy(dtype="int64")
        self.criterio_maiac = criterio_maiac
        self.qa_no2_min = qa_no2_min
        self.radio_no2_km = radio_no2_km
        la, lo = np.radians(self.celdas["lat"].to_numpy()), np.radians(self.celdas["lon"].to_numpy())
        self._xyz = np.c_[np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)]
        self._historial: deque[tuple[date, dict[str, np.ndarray]]] = deque(maxlen=15)
        self._cKDTree = cKDTree
        self.dias_sin_maiac: list[str] = []
        self.dias_sin_no2: list[str] = []

    def _maiac(self, fecha: date) -> dict[str, np.ndarray]:
        n = len(self.celdas)
        out = {"aod_terra": np.full(n, np.nan, "float32"), "aod_aqua": np.full(n, np.nan, "float32"),
               "aod_dia": np.full(n, np.nan, "float32"), "aod_n": np.zeros(n, "float32")}
        obs = maiac_dia(fecha, self.criterio_maiac)
        if obs is None:
            self.dias_sin_maiac.append(fecha.isoformat())
            return out
        if obs.empty:
            return out
        por = obs.groupby(["pixel_id", "satelite"])["aod055"].agg(["mean", "size"]).reset_index()
        for sat, col in (("Terra", "aod_terra"), ("Aqua", "aod_aqua")):
            s = por[por["satelite"] == sat].set_index("pixel_id")["mean"]
            out[col] = s.reindex(self.maiac_pixel).to_numpy(dtype="float32")
        total = obs.groupby("pixel_id")["aod055"].agg(["mean", "size"])
        out["aod_dia"] = total["mean"].reindex(self.maiac_pixel).to_numpy(dtype="float32")
        out["aod_n"] = total["size"].reindex(self.maiac_pixel).fillna(0).to_numpy(dtype="float32")
        return out

    def _no2(self, fecha: date) -> dict[str, np.ndarray]:
        n = len(self.celdas)
        suma = np.zeros(n, "float64"); suma_p = np.zeros(n, "float64"); suma_h = np.zeros(n, "float64")
        cuenta = np.zeros(n, "int32")
        orbitas = orbitas_no2_dia(fecha)
        if not orbitas:
            self.dias_sin_no2.append(fecha.isoformat())
        for path in orbitas:
            px = leer_orbita_no2(path, self.qa_no2_min)
            if px.empty:
                continue
            la, lo = np.radians(px["lat"].to_numpy()), np.radians(px["lon"].to_numpy())
            arbol = self._cKDTree(np.c_[np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])
            d, i = arbol.query(self._xyz, distance_upper_bound=2.0 * np.sin(self.radio_no2_km / 6371.0 / 2.0))
            ok = np.isfinite(d)
            if not ok.any():
                continue
            hora = (pd.DatetimeIndex(px["ts_utc"]).hour + pd.DatetimeIndex(px["ts_utc"]).minute / 60.0).to_numpy()
            suma[ok] += px["no2_trop"].to_numpy()[i[ok]]
            suma_p[ok] += px["no2_trop_prec"].to_numpy()[i[ok]]
            suma_h[ok] += np.nan_to_num(hora[i[ok]], nan=0.0)
            cuenta[ok] += 1
        with np.errstate(invalid="ignore", divide="ignore"):
            out = {"no2_trop": np.where(cuenta > 0, suma / cuenta, np.nan).astype("float32"),
                   "no2_trop_prec": np.where(cuenta > 0, suma_p / cuenta, np.nan).astype("float32"),
                   "no2_trop_hora": np.where(cuenta > 0, suma_h / cuenta, np.nan).astype("float32")}
        return out

    def dia(self, fecha: date) -> pd.DataFrame:
        if self._historial and self._historial[-1][0] >= fecha:
            for f, d in self._historial:
                if f == fecha:
                    return self._tabla(fecha, d)
            raise ValueError("los días deben pedirse en orden cronológico")
        d = {**self._maiac(fecha), **self._no2(fecha)}
        self._historial.append((fecha, d))
        return self._tabla(fecha, d)

    def _ventana(self, fecha: date, clave: str, dias: int) -> np.ndarray:
        pilas = [d[clave] for f, d in self._historial if 0 <= (fecha - f).days < dias]
        if not pilas:
            return np.full(len(self.celdas), np.nan, "float32")
        apilado = np.vstack(pilas)
        con_dato = np.isfinite(apilado)
        suma = np.where(con_dato, apilado, 0.0).sum(axis=0)
        n = con_dato.sum(axis=0)
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(n > 0, suma / n, np.nan).astype("float32")

    def _tabla(self, fecha: date, d: dict[str, np.ndarray]) -> pd.DataFrame:
        out = pd.DataFrame({"celda": self.celdas["celda"].to_numpy()})
        for k, v in d.items():
            out[k] = v
        out["aod_3d"] = self._ventana(fecha, "aod_dia", 3)
        out["aod_7d"] = self._ventana(fecha, "aod_dia", 7)
        out["no2_trop_7d"] = self._ventana(fecha, "no2_trop", 7)
        out["no2_trop_15d"] = self._ventana(fecha, "no2_trop", 15)
        out["fecha_local"] = pd.Timestamp(fecha)
        return out


def satelites_tramo(desde: str, hasta: str, celdas: pd.DataFrame, enlaces: pd.DataFrame,
                    calentamiento: int = 15) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Predictores satelitales diarios de un tramo contiguo ``[desde, hasta]``.

    Cada tramo arranca ``calentamiento`` días antes para llenar las ventanas
    móviles, de modo que varios tramos consecutivos (uno por proceso) dan lo
    mismo que una sola pasada cronológica. Devuelve (tabla, días sin MAIAC,
    días sin TROPOMI), estos últimos sólo dentro del tramo.
    """
    sat = SatelitesDiarios(celdas, enlaces)
    ini, d0 = date.fromisoformat(desde) - timedelta(days=calentamiento), date.fromisoformat(desde)
    tablas = []
    for f in fechas(ini.isoformat(), hasta):
        tabla = sat.dia(f)
        if f >= d0:
            tablas.append(tabla)
    return (pd.concat(tablas, ignore_index=True), [d for d in sat.dias_sin_maiac if d >= desde],
            [d for d in sat.dias_sin_no2 if d >= desde])


class AcagMensual:
    """PM2.5 mensual ACAG por celda; meses sin publicación usan la climatología del mes."""

    def __init__(self, celdas: pd.DataFrame):
        self.celdas = celdas["celda"].to_numpy()
        self.disponibles = acag_meses_disponibles()
        self._cache: dict[str, np.ndarray] = {}
        self._clim: dict[int, np.ndarray] = {}

    def _leer(self, yyyymm: str) -> np.ndarray | None:
        if yyyymm not in self._cache:
            df = acag_mes(yyyymm)
            self._cache[yyyymm] = (None if df is None else
                                   df.set_index("celda")["acag_pm25"].reindex(self.celdas).to_numpy(dtype="float32"))
        return self._cache[yyyymm]

    def climatologia(self, mes: int, anios_ref=(2018, 2024)) -> np.ndarray:
        if mes not in self._clim:
            pilas = [self._leer(m) for m in self.disponibles
                     if int(m[4:6]) == mes and anios_ref[0] <= int(m[:4]) <= anios_ref[1]]
            pilas = [p for p in pilas if p is not None]
            self._clim[mes] = (np.nanmean(np.vstack(pilas), axis=0).astype("float32") if pilas
                               else np.full(len(self.celdas), np.nan, "float32"))
        return self._clim[mes]

    def mes(self, yyyymm: str) -> tuple[np.ndarray, bool]:
        v = self._leer(yyyymm)
        if v is not None:
            return v, False
        return self.climatologia(int(yyyymm[4:6])), True


def cargar_estaticas() -> tuple[pd.DataFrame, pd.DataFrame]:
    if not ESTATICAS_PATH.exists() or not LULC_PATH.exists():
        raise SystemExit("Faltan las covariables estáticas; ejecuta covariables_estaticas.py")
    est = pd.read_parquet(ESTATICAS_PATH)
    lulc = pd.read_parquet(LULC_PATH)
    return est, lulc


COLUMNAS_ESTATICAS = ("elev_m", "pendiente_deg", "dist_costa_km", "vias_km_km2",
                      "vias_princ_km_km2", "lat", "lon", "macrozona_cod")
COLUMNAS_LULC = ("lulc_urbano", "lulc_cultivo", "lulc_bosque", "lulc_matorral_pastizal",
                 "lulc_desnudo", "lulc_agua", "lulc_nieve_hielo", "pob_dens")


def unir_estaticas(df: pd.DataFrame, est: pd.DataFrame, lulc: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in COLUMNAS_ESTATICAS if c in est.columns and c not in df.columns]
    df = df.merge(est[["celda", *cols]], on="celda", how="left")
    anios = np.sort(lulc["anio"].unique())
    anio_l = np.clip(df["anio"].to_numpy(), anios.min(), anios.max())
    tmp = pd.DataFrame({"celda": df["celda"].to_numpy(), "anio": anio_l.astype("int16")})
    tmp = tmp.merge(lulc[["celda", "anio", *[c for c in COLUMNAS_LULC if c in lulc.columns]]],
                    on=["celda", "anio"], how="left")
    for c in COLUMNAS_LULC:
        if c in tmp.columns:
            df[c] = tmp[c].to_numpy(dtype="float32")
    return df


def vecinas_idw(obs: pd.DataFrame, estaciones: pd.DataFrame, h_km: float = 150.0):
    """Matrices para interpolar observaciones concurrentes de otras estaciones.

    Devuelve (tiempos, estaciones, valores (T×S), lat, lon). ``obs`` tiene
    columnas estacion, ts_utc, obs.
    """
    O = obs.pivot_table(index="ts_utc", columns="estacion", values="obs", aggfunc="mean")
    meta = estaciones.set_index("estacion").loc[O.columns]
    return O, meta["lat"].to_numpy(float), meta["lon"].to_numpy(float)


def haversine_km(lat1, lon1, lat2, lon2):
    a1, a2 = np.radians(lat1), np.radians(lat2)
    da, do = a2 - a1, np.radians(lon2 - lon1)
    x = np.sin(da / 2) ** 2 + np.cos(a1) * np.cos(a2) * np.sin(do / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(np.clip(x, 0, 1)))


def obs_vecinas_para(O: pd.DataFrame, lat_e: np.ndarray, lon_e: np.ndarray, ts: np.ndarray,
                     lat_q: np.ndarray, lon_q: np.ndarray, excluir: np.ndarray | None = None,
                     h_km: float = 150.0, lote: int = 200_000):
    """IDW gaussiano de las observaciones concurrentes para puntos (ts, lat, lon).

    ``excluir`` (opcional) es el nombre de estación de cada punto, que se
    omite del vecindario (validez bajo LOSO). Devuelve (obs_vec, peso_vec).
    """
    ts = np.asarray(ts, dtype="datetime64[ns]")
    idx_t = O.index.get_indexer(pd.DatetimeIndex(ts))
    V = np.nan_to_num(O.to_numpy(dtype="float64"))
    M = O.notna().to_numpy(dtype="float64")
    cols = O.columns.to_numpy()
    obs_vec = np.full(len(ts), np.nan, "float32")
    peso_vec = np.zeros(len(ts), "float32")
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
        obs_vec[sel] = val.astype("float32")
        peso_vec[sel] = den.astype("float32")
    return obs_vec, peso_vec


class VecindarioFijo:
    """``obs_vecinas_para`` cuando los puntos de consulta no cambian: la matriz de pesos se calcula una
    sola vez.

    En producción los puntos son siempre las mismas celdas de la grilla, así que recalcular las
    838.430 × N distancias en cada una de las 24 horas del día era trabajo repetido: era el 22 % del
    costo de un día nacional. El resultado es **idéntico bit a bit** al de ``obs_vecinas_para``:
    ``Σⱼ Wᵢⱼ·Mⱼ·Vⱼ`` es exactamente el producto matriz-vector ``W @ (M*V)``.
    """

    def __init__(self, O: pd.DataFrame, lat_e: np.ndarray, lon_e: np.ndarray, lat_q: np.ndarray,
                 lon_q: np.ndarray, h_km: float = 150.0, lote: int = 200_000):
        self.O = O
        self.V = np.nan_to_num(O.to_numpy(dtype="float64"))
        self.M = O.notna().to_numpy(dtype="float64")
        lat_q, lon_q = np.asarray(lat_q, dtype=float), np.asarray(lon_q, dtype=float)
        self.W = np.empty((len(lat_q), len(lat_e)), dtype="float64")
        for ini in range(0, len(lat_q), lote):
            fin = min(ini + lote, len(lat_q))
            D = haversine_km(lat_q[ini:fin, None], lon_q[ini:fin, None], lat_e[None, :], lon_e[None, :])
            self.W[ini:fin] = np.exp(-(D / h_km) ** 2)

    def para(self, ts_utc) -> tuple[np.ndarray, np.ndarray]:
        """(obs_vec, peso_vec) de todos los puntos en un instante."""
        n = self.W.shape[0]
        it = int(self.O.index.get_indexer(pd.DatetimeIndex([ts_utc]))[0])
        if it < 0:                                   # esa hora no existe en el registro observado
            return np.full(n, np.nan, "float32"), np.zeros(n, "float32")
        den = self.W @ self.M[it]
        num = self.W @ (self.M[it] * self.V[it])
        with np.errstate(invalid="ignore", divide="ignore"):
            val = np.where(den > 1e-6, num / den, np.nan)
        return val.astype("float32"), den.astype("float32")


_INTERP: pd.DataFrame | None = None


def productos_interpolados() -> tuple[str, ...]:
    """Productos cuyos predictores se interpolan bilinealmente en vez de tomarse del píxel más cercano.

    Se activa con ``MODELO_1KM_INTERPOLAR`` (lista separada por comas, o ``1``/``todos`` para los cuatro
    reanálisis gruesos). Vacío por omisión: sin la variable el camino es idéntico al histórico, byte a byte.
    """
    v = os.environ.get("MODELO_1KM_INTERPOLAR", "").strip().lower()
    if not v:
        return ()
    if v in {"1", "si", "sí", "todos", "all"}:
        return ("era5blh", "merra2", "cams", "geoscf")
    return tuple(x.strip() for x in v.split(",") if x.strip())


def enlaces_interpolacion() -> pd.DataFrame | None:
    """Pesos bilineales por celda, en caché. Los produce ``enlaces_interpolacion.py``."""
    global _INTERP
    if _INTERP is None:
        ruta = GRILLA_DIR / "enlaces_interpolacion.parquet"
        if not ruta.exists():
            raise FileNotFoundError(
                f"MODELO_1KM_INTERPOLAR está activo pero falta {ruta}; corre "
                "scripts_modelo_1km/enlaces_interpolacion.py")
        _INTERP = pd.read_parquet(ruta).set_index("celda")
    return _INTERP


def estencil(producto: str, celdas) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Píxeles y pesos de los cuatro nodos, como arreglos alineados con ``celdas``.

    Se calcula una vez y se reutiliza: hacer el ``.loc`` dentro del bucle horario era el grueso del
    sobrecosto de la interpolación.
    """
    w = enlaces_interpolacion()
    if f"{producto}_w0" not in w.columns:
        raise KeyError(f"{producto} no tiene pesos en enlaces_interpolacion.parquet")
    sub = w.loc[celdas]
    return ([sub[f"{producto}_pix{k}"].to_numpy("int64") for k in range(4)],
            [sub[f"{producto}_w{k}"].to_numpy("float64") for k in range(4)])


def combinar_nodos(producto, ts, pix, pes, fuentes) -> dict[str, np.ndarray]:
    """Media ponderada de los cuatro nodos que rodean a cada celda.

    Única implementación: la usan el panel de calibración y la producción de superficies, para que no
    puedan separarse. Los pesos se renormalizan sobre los nodos **con dato en esa hora**, de modo que un
    vecino sin archivo no arrastra el valor hacia abajo: con un solo nodo presente el resultado es ese
    nodo, como en el camino de siempre. Sin ningún nodo con dato, NaN, que es lo que el motor espera.
    """
    cols = list(FEATURES_HORARIAS[producto].values())
    num = {c: np.zeros(len(ts), "float64") for c in cols}
    den = {c: np.zeros(len(ts), "float64") for c in cols}
    for k in range(4):
        usa = pes[k] > 0
        if not usa.any():
            continue
        # donde el peso es cero el índice no se usa, pero igual tiene que ser legible: se sustituye por
        # cualquier píxel válido de la misma fila, nunca por -1
        respaldo = np.where(pix[0] >= 0, pix[0], np.maximum(pix[k], 0))
        seguro = np.where(usa & (pix[k] >= 0), pix[k], respaldo)
        for col, arr in fuentes.extraer(producto, ts, seguro).items():
            ok = usa & np.isfinite(arr)
            num[col][ok] += pes[k][ok] * arr[ok]
            den[col][ok] += pes[k][ok]
    return {c: np.where(den[c] > 1e-12, num[c] / np.maximum(den[c], 1e-12), np.nan).astype("float32")
            for c in cols}


def _extraer_interpolado(producto, ts, celdas, fuentes) -> dict[str, np.ndarray]:
    pix, pes = estencil(producto, celdas)
    return combinar_nodos(producto, ts, pix, pes, fuentes)


def ensamblar_horario(base: pd.DataFrame, enlaces: pd.DataFrame, fuentes: FuentesHorarias) -> pd.DataFrame:
    """Une los predictores horarios de reanálisis a ``base`` (celda, ts_utc)."""
    enl = enlaces.set_index("celda")
    interp = productos_interpolados()
    df = base.copy()
    ts = df["ts_utc"].to_numpy(dtype="datetime64[ns]")
    for producto in fuentes.productos:
        col_pix = f"{producto}_pixel"
        if col_pix not in enl.columns:
            continue
        if producto in interp:
            if f"{producto}_w0" not in enlaces_interpolacion().columns:
                raise KeyError(f"MODELO_1KM_INTERPOLAR nombra '{producto}' pero no tiene pesos en "
                               "enlaces_interpolacion.parquet; corre enlaces_interpolacion.py --forzar. "
                               "Caer al vecino más cercano en silencio dejaría un panel mitad "
                               "interpolado y la comparación no mediría el diseño que dice medir.")
            vals = _extraer_interpolado(producto, ts, df["celda"], fuentes)
        else:
            pix = enl.loc[df["celda"], col_pix].to_numpy(dtype="int64")
            vals = fuentes.extraer(producto, ts, pix)
        for col, arr in vals.items():
            df[col] = arr
    return derivadas_horarias(df)


def ensamblar_horario_tramo(base: pd.DataFrame, enlaces: pd.DataFrame) -> tuple[pd.DataFrame, list[tuple[str, str]]]:
    """``ensamblar_horario`` mes a mes sobre un tramo de filas con su propio caché de fuentes (apto para
    ejecutarse en otro proceso). Devuelve (tabla, [(producto, yyyymm) sin archivo])."""
    fuentes = FuentesHorarias()
    partes = [ensamblar_horario(bloque, enlaces, fuentes)
              for _, bloque in base.groupby(base["ts_utc"].dt.strftime("%Y%m"), sort=True)]
    return pd.concat(partes, ignore_index=True), sorted(fuentes.faltantes)


FEATURES_MODELO_BASE = [
    "hora_local", "hora_sin", "hora_cos", "doy_sin", "doy_cos", "dow", "mes", "anio",
    "lat", "lon", "macrozona_cod", "elev_m", "pendiente_deg", "dist_costa_km",
    "vias_km_km2", "vias_princ_km_km2", *COLUMNAS_LULC,
    "el_t2m", "el_d2m", "el_rh", "el_sp", "el_u10", "el_v10", "el_wind", "el_wdir_sin", "el_wdir_cos",
    "el_tp_1h_mm", "blh", "inv_blh",
    "m2_t2m", "m2_rh2m", "m2_u10m", "m2_v10m", "m2_pblh", "m2_aod", "m2_pm25", "m2_ps", "m2_aod_pblh",
    "cams_no2", "cams_pm25", "cams_o3", "cams_co",
    "gcf_no2", "gcf_pm25", "gcf_o3", "gcf_co", "gcf_pm25_blh",
    *COLUMNAS_SATELITE, "acag_pm25", "acag_clim",
    "obs_vec", "peso_vec", "dist_est_km",
]


EXCLUSIONES_POR_DEFECTO = "no2:dist_costa_km"


def predictores_excluidos(pol: str | None = None) -> set[str]:
    """Predictores que ``MODELO_1KM_EXCLUIR`` saca del modelo. Formato: ``no2:dist_costa_km,lon;pm25:acag_clim``
    (por contaminante, separados por ``;``) o una lista simple que aplica a todos. Nació el 30-sep-2026 para
    quitar ``dist_costa_km`` del NO₂: con tres estaciones en el norte grande, una sola de ellas tierra
    adentro, el árbol pintaba con el nivel de Calama toda celda a más de ~80 km de la costa."""
    import os
    # La exclusión del diseño publicado es el valor por omisión, no una variable que haya que recordar:
    # hasta el 2026-10-03 vivía sólo en MODELO_1KM_EXCLUIR, y una corrida sin ella habría reajustado el NO₂
    # con la distancia a la costa sin ningún aviso. La variable sigue permitiendo cambiarla para un
    # experimento; ``-`` la vacía del todo.
    raw = os.environ.get("MODELO_1KM_EXCLUIR", EXCLUSIONES_POR_DEFECTO).strip()
    if raw == "-":
        return set()
    fuera: set[str] = set()
    for tramo in filter(None, (t.strip() for t in raw.split(";"))):
        if ":" in tramo:
            quien, lista = tramo.split(":", 1)
            if pol is not None and quien.strip() != pol:
                continue
        else:
            lista = tramo
        fuera |= {c.strip() for c in lista.split(",") if c.strip()}
    return fuera


def columnas_modelo(df: pd.DataFrame, cobertura_min: float = 0.05, pol: str | None = None) -> list[str]:
    """Predictores presentes con cobertura mínima (el resto se omite y se registra), menos los excluidos
    por ``MODELO_1KM_EXCLUIR`` para ``pol``."""
    fuera = predictores_excluidos(pol)
    return [c for c in FEATURES_MODELO_BASE
            if c in df.columns and c not in fuera and df[c].notna().mean() >= cobertura_min]
