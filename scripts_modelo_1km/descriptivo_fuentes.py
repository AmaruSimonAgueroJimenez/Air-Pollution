#!/usr/bin/env python3
"""Descriptivo de las fuentes de datos a su resolución nativa, en años muestreados cada cuatro.

Para cada fuente que alimenta el modelo y cada año de la muestra (2000, 2004, …) se calculan dos
resúmenes, sin interpolar nada:

* ``mapa``: el promedio anual **por píxel nativo** (o el total anual, para la precipitación). Para
  dibujarlo, cada celda de 0,01° toma el valor del píxel al que está enlazada, de modo que el mapa
  muestra literalmente la resolución con que esa fuente entra al modelo.
* ``serie``: la serie **diaria** (mensual para ACAG, anual para uso de suelo y población) de Chile y
  de cada macrozona, como promedio de los píxeles nativos ponderado por el **área** de territorio
  chileno que cada píxel cubre: la suma, sobre las celdas de 0,01° enlazadas al píxel, de cos(latitud)
  (una celda de 0,01° mide cos(lat) veces la ecuatorial: 0,95 en Arica y 0,56 en el Cabo de Hornos).

El día es el día local (UTC−4), igual que en el resto del modelo. TROPOMI es un producto de nivel 2
sin grilla fija: sus píxeles (~3,5 × 5,5 km) se acumulan en una malla regular de 0,05°, que es del
orden de su huella, sólo para poder promediar órbitas distintas.

    python -B scripts_modelo_1km/descriptivo_fuentes.py --procesos 4
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comun_modelo import (  # noqa: E402
    CONTRATO, GRILLA_DIR, LULC_PATH, MODELO_ROOT, OFFSET_UTC_H, TROPOMI_NO2_DIR, acag_mes, cargar_celdas, cargar_enlaces,
    catalogo_maiac, fecha_de_nombre, hash_codigo, leer_mes_geoscf, leer_mes_nativo, leer_orbita_no2, log,
    maiac_dia, publicar_json, publicar_parquet,
)

DIR = MODELO_ROOT / "descriptivo_fuentes"
VERSION = 2                       # cambia con el algoritmo: invalida lo cacheado (v2: pesos por área, no por conteo)
ZONAS = ("Chile", "norte_grande", "norte_chico", "centro", "sur", "austral")
CODIGO_ZONA = {"norte_grande": 0, "norte_chico": 1, "centro": 2, "sur": 3, "austral": 4}
M_AIRE, M_NO2, M_O3, M_CO = 28.9647, 46.0055, 47.9982, 28.0101
RES_TROPOMI = 0.05
CAJA_TROPOMI = (-76.5, -56.5, -66.0, -17.0)          # lon0, lat0, lon1, lat1 (Chile continental)

# fuente → variable → (etiqueta, unidad, agregación temporal, mapa de color)
VARIABLES: dict[str, dict[str, tuple[str, str, str, str]]] = {
    "era5land": {"t2m": ("temperatura a 2 m", "°C", "media", "RdYlBu_r"),
                 "rh": ("humedad relativa a 2 m", "%", "media", "YlGnBu"),
                 "wind": ("rapidez del viento a 10 m", "m/s", "media", "viridis"),
                 "sp": ("presión en superficie", "hPa", "media", "cividis"),
                 "tp": ("precipitación", "mm", "suma", "YlGnBu")},
    "era5blh": {"blh": ("altura de la capa límite", "m", "media", "cividis")},
    "merra2": {"t2m": ("temperatura a 2 m", "°C", "media", "RdYlBu_r"),
               "rh": ("humedad relativa a 2 m", "%", "media", "YlGnBu"),
               "wind": ("rapidez del viento a 10 m", "m/s", "media", "viridis"),
               "pblh": ("altura de la capa límite", "m", "media", "cividis"),
               "aod": ("AOD 550 nm", "adimensional", "media", "YlOrBr"),
               "pm25": ("PM₂.₅ en superficie", "µg/m³", "media", "magma_r")},
    "cams": {"no2": ("NO₂ en superficie", "ppb", "media", "magma_r"), "pm25": ("PM₂.₅ en superficie", "µg/m³", "media", "magma_r"),
             "o3": ("O₃ en superficie", "ppb", "media", "viridis"), "co": ("CO en superficie", "ppb", "media", "magma_r")},
    "geoscf": {"no2": ("NO₂ en superficie", "ppb", "media", "magma_r"), "pm25": ("PM₂.₅ en superficie", "µg/m³", "media", "magma_r"),
               "o3": ("O₃ en superficie", "ppb", "media", "viridis"), "co": ("CO en superficie", "ppb", "media", "magma_r")},
    "maiac": {"aod": ("AOD 550 nm (QA estricta)", "adimensional", "media", "YlOrBr"),
              "cobertura": ("días con observación válida", "% de los días", "media", "viridis")},
    "tropomi": {"no2_trop": ("columna troposférica de NO₂ (qa ≥ 0,75)", "10¹⁵ moléc/cm²", "media", "magma_r")},
    "acag": {"pm25": ("PM₂.₅ en superficie", "µg/m³", "media", "magma_r")},
    "lulc": {"lulc_urbano": ("fracción urbana", "fracción de la celda", "media", "magma_r"),
             "lulc_cultivo": ("fracción de cultivo", "fracción de la celda", "media", "YlGn"),
             "lulc_bosque": ("fracción de bosque", "fracción de la celda", "media", "Greens"),
             "lulc_desnudo": ("fracción de suelo desnudo", "fracción de la celda", "media", "YlOrBr"),
             "pob_dens": ("densidad de población", "hab/km²", "media", "magma_r")},
}
NOMBRE_FUENTE = {"era5land": "ERA5-Land (0,1°, horario)", "era5blh": "ERA5 BLH (0,25°, horario)",
                 "merra2": "MERRA-2 (0,5° × 0,625°, horario)", "cams": "CAMS EAC4 (0,75°, cada 3 h)",
                 "geoscf": "GEOS-CF (0,25°, horario)", "maiac": "MAIAC MCD19A2 (1 km, por pasada)",
                 "tropomi": "TROPOMI NO₂ nivel 2 (~3,5 × 5,5 km, por órbita; acumulado en 0,05°)",
                 "acag": "ACAG V6GL03 (0,01°, mensual)", "lulc": "ESA CCI 300 m y proyecciones censales (agregados a 0,01°, anual)"}
PASO_SERIE = {"acag": "mensual", "lulc": "anual"}          # el resto es diario
MENSUALES = ("era5land", "era5blh", "merra2", "cams", "geoscf")


def anios_muestra(desde: int = 2000, hasta: int = 2026, salto: int = 4) -> list[int]:
    return list(range(desde, hasta + 1, salto))


# ---------------------------------------------------------------------------
# Pesos por zona: cuántas celdas chilenas de cada macrozona cubre cada píxel nativo
# ---------------------------------------------------------------------------
class Pesos:
    """Matriz zona × píxel (en el orden de ``pixel_id`` que se le entregue). El peso de un píxel en una
    zona es el área relativa de las celdas de esa zona enlazadas a él: Σ cos(latitud de la celda)."""

    def __init__(self, pixel_de_celda: np.ndarray, macrozona_cod: np.ndarray, lat: np.ndarray):
        ok = (pixel_de_celda >= 0) & np.isin(macrozona_cod, list(CODIGO_ZONA.values()))
        self._tabla = (pd.DataFrame({"pixel": pixel_de_celda[ok], "zona": macrozona_cod[ok],
                                     "n": np.cos(np.radians(np.asarray(lat, dtype="float64")[ok]))})
                       .groupby(["pixel", "zona"])["n"].sum().reset_index())

    def matriz(self, pixel_id: np.ndarray) -> np.ndarray:
        orden = np.argsort(pixel_id)
        pos = orden[np.clip(np.searchsorted(pixel_id[orden], self._tabla["pixel"].to_numpy()), 0, len(pixel_id) - 1)]
        vale = pixel_id[pos] == self._tabla["pixel"].to_numpy()
        W = np.zeros((len(ZONAS), len(pixel_id)), dtype="float64")
        t = self._tabla[vale]
        np.add.at(W, (t["zona"].to_numpy() + 1, pos[vale]), t["n"].to_numpy(dtype="float64"))
        W[0] = W[1:].sum(axis=0)
        return W


def media_por_zona(X: np.ndarray, W: np.ndarray) -> np.ndarray:
    """Promedio ponderado por zona de cada fila de ``X`` (tiempo × píxel), ignorando NaN → (tiempo × zona)."""
    finito = np.isfinite(X)
    num = np.where(finito, X, 0.0) @ W.T
    den = finito.astype("float64") @ W.T
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, num / den, np.nan)


def _contexto() -> tuple[pd.DataFrame, pd.DataFrame]:
    celdas, enlaces = cargar_celdas(), cargar_enlaces()
    if not celdas["celda"].equals(enlaces["celda"]):
        enlaces = enlaces.set_index("celda").loc[celdas["celda"]].reset_index()
    return celdas, enlaces


# ---------------------------------------------------------------------------
# Productos mensuales tiempo × píxel (ERA5-Land, ERA5 BLH, MERRA-2, CAMS, GEOS-CF)
# ---------------------------------------------------------------------------
def _derivar(producto: str, d: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Variables descriptivas en unidades legibles a partir de las nativas."""
    out = {}
    if producto == "era5land":
        t, td = d["t2m"] - 273.15, d["d2m"] - 273.15
        out["t2m"] = t
        out["rh"] = np.clip(100.0 * np.exp(17.67 * td / (td + 243.5)) / np.exp(17.67 * t / (t + 243.5)), 0, 100)
        out["wind"] = np.sqrt(d["u10"] ** 2 + d["v10"] ** 2)
        out["sp"] = d["sp"] / 100.0
        out["tp"] = np.clip(d["tp_1h_mm"], 0, None)          # incrementos negativos del acumulado → 0
    elif producto == "era5blh":
        out["blh"] = d["blh"]
    elif producto == "merra2":
        out["t2m"] = d["t2m"] - 273.15
        rh = d["rh2m"]
        out["rh"] = np.clip(rh * 100.0 if np.nanmax(rh) <= 1.5 else rh, 0, 100)      # como la de ERA5-Land
        out["wind"] = np.sqrt(d["u10m"] ** 2 + d["v10m"] ** 2)
        out["pblh"], out["aod"], out["pm25"] = d["pblh"], d["aod_m2"], d["pm25_m2"]
    elif producto == "cams":
        out["no2"] = d["no2"] * (M_AIRE / M_NO2) * 1e9
        out["o3"] = d["o3"] * (M_AIRE / M_O3) * 1e9
        out["co"] = d["co"] * (M_AIRE / M_CO) * 1e9
        out["pm25"] = d["pm25"] * 1e9
    elif producto == "geoscf":                                # ``leer_mes_geoscf`` ya entrega ppb y µg/m³
        out = {k: d[k] for k in ("no2", "pm25", "o3", "co") if k in d}
    return out


def extraer_mensual(producto: str, anio: int, celdas: pd.DataFrame, enlaces: pd.DataFrame):
    pesos = Pesos(enlaces[f"{producto}_pixel"].to_numpy("int64"), celdas["macrozona_cod"].to_numpy(), celdas["lat"].to_numpy())
    variables = list(VARIABLES[producto])
    pixel_id = W = None
    suma, cuenta, series, meses_leidos = {}, {}, [], []
    for mes in range(1, 13):
        m = leer_mes_geoscf(f"{anio}{mes:02d}") if producto == "geoscf" else leer_mes_nativo(producto, f"{anio}{mes:02d}")
        if m is None:
            continue
        if pixel_id is None:
            pixel_id, W = m.pixel_id.copy(), pesos.matriz(m.pixel_id)
            suma = {v: np.zeros(len(pixel_id)) for v in variables}
            cuenta = {v: np.zeros(len(pixel_id)) for v in variables}
        elif not np.array_equal(pixel_id, m.pixel_id):
            raise ValueError(f"{producto} {anio}-{mes:02d}: cambia el orden de píxeles entre meses")
        meses_leidos.append(f"{anio}{mes:02d}")
        datos = _derivar(producto, m.datos)
        por_hora = {}
        for v in variables:
            if v not in datos:
                continue
            X = datos[v].astype("float64")
            suma[v] += np.nansum(X, axis=0); cuenta[v] += np.isfinite(X).sum(axis=0)
            por_hora[v] = media_por_zona(X, W)
        # Serie horaria por zona; el día local se arma al final del año, porque las primeras horas UTC de
        # cada mes pertenecen al último día local del mes anterior (otro archivo).
        for k, z in enumerate(ZONAS):
            series.append(pd.DataFrame({"ts_utc": m.tiempos, "zona": z, **{v: por_hora[v][:, k] for v in por_hora}}))
    if pixel_id is None:
        return None, None, {"archivos": 0}
    mapa = pd.DataFrame({"pixel_id": pixel_id})
    for v in variables:
        with np.errstate(invalid="ignore", divide="ignore"):
            mapa[v] = (suma[v] if VARIABLES[producto][v][2] == "suma" else
                       np.where(cuenta[v] > 0, suma[v] / cuenta[v], np.nan)).astype("float32")
        if VARIABLES[producto][v][2] == "suma":
            mapa.loc[cuenta[v] == 0, v] = np.nan
    horaria = pd.concat(series, ignore_index=True)
    horaria["fecha"] = (horaria["ts_utc"] - pd.Timedelta(hours=OFFSET_UTC_H)).dt.normalize()
    presentes = [v for v in variables if v in horaria.columns]
    agg = {v: ("sum" if VARIABLES[producto][v][2] == "suma" else "mean") for v in presentes}
    g = horaria.groupby(["fecha", "zona"])
    serie = g.agg(agg)
    for v in presentes:                                        # un total diario exige el día casi completo
        if VARIABLES[producto][v][2] == "suma":
            serie.loc[g[v].count() < 23, v] = np.nan
    serie = serie.reset_index()
    serie = serie[serie["fecha"].dt.year == anio].reset_index(drop=True)
    return mapa, serie, {"archivos": len(meses_leidos), "meses": meses_leidos}


# ---------------------------------------------------------------------------
# MAIAC 1 km
# ---------------------------------------------------------------------------
def extraer_maiac(anio: int, celdas: pd.DataFrame, enlaces: pd.DataFrame):
    cat = catalogo_maiac().drop_duplicates("pixel_id").sort_values("pixel_id")
    pix = cat["pixel_id"].to_numpy("int64")
    W = Pesos(enlaces["maiac_pixel"].to_numpy("int64"), celdas["macrozona_cod"].to_numpy(), celdas["lat"].to_numpy()).matriz(pix)
    total_zona = W.sum(axis=1)
    suma, dias_con_dato, dias, filas = np.zeros(len(pix)), np.zeros(len(pix)), 0, []
    f = date(anio, 1, 1)
    while f.year == anio:
        obs = maiac_dia(f, "estricta")
        if obs is not None:
            dias += 1
            if len(obs):
                g = obs.groupby("pixel_id")["aod055"].mean()
                ids, val = g.index.to_numpy("int64"), g.to_numpy("float64")
                pos = np.clip(np.searchsorted(pix, ids), 0, len(pix) - 1)
                ok = pix[pos] == ids                          # un píxel fuera del catálogo se descarta
                pos, val = pos[ok], val[ok]
                suma[pos] += val; dias_con_dato[pos] += 1
                x = np.full(len(pix), np.nan); x[pos] = val
                media = media_por_zona(x[None, :], W)[0]
                cobertura = 100.0 * ((np.isfinite(x).astype("float64")[None, :] @ W.T)[0] / np.where(total_zona > 0, total_zona, np.nan))
            else:
                media, cobertura = np.full(len(ZONAS), np.nan), np.zeros(len(ZONAS))
            filas += [{"fecha": pd.Timestamp(f), "zona": z, "aod": media[k], "cobertura": cobertura[k]} for k, z in enumerate(ZONAS)]
        f += timedelta(days=1)
    if not dias:
        return None, None, {"archivos": 0}
    with np.errstate(invalid="ignore", divide="ignore"):
        mapa = pd.DataFrame({"pixel_id": pix, "aod": np.where(dias_con_dato > 0, suma / dias_con_dato, np.nan).astype("float32"),
                             "cobertura": (100.0 * dias_con_dato / dias).astype("float32")})
    return mapa, pd.DataFrame(filas), {"archivos": dias}


# ---------------------------------------------------------------------------
# TROPOMI NO2 nivel 2, acumulado en una malla de 0,05°
# ---------------------------------------------------------------------------
def _bin_tropomi(lat, lon) -> np.ndarray:
    lon0, lat0, lon1, lat1 = CAJA_TROPOMI
    ncol = int(round((lon1 - lon0) / RES_TROPOMI))
    nfil = int(round((lat1 - lat0) / RES_TROPOMI))
    i = np.floor((np.asarray(lat) - lat0) / RES_TROPOMI).astype("int64")
    j = np.floor((np.asarray(lon) - lon0) / RES_TROPOMI).astype("int64")
    return np.where((i >= 0) & (i < nfil) & (j >= 0) & (j < ncol), i * ncol + j, -1)


def extraer_tropomi(anio: int, celdas: pd.DataFrame, enlaces: pd.DataFrame):
    lon0, lat0, lon1, lat1 = CAJA_TROPOMI
    n = int(round((lon1 - lon0) / RES_TROPOMI)) * int(round((lat1 - lat0) / RES_TROPOMI))
    bins = np.arange(n, dtype="int64")
    W = Pesos(_bin_tropomi(celdas["lat"].to_numpy(), celdas["lon"].to_numpy()), celdas["macrozona_cod"].to_numpy(),
              celdas["lat"].to_numpy()).matriz(bins)
    por_dia: dict[str, list[Path]] = {}
    for p in sorted(TROPOMI_NO2_DIR.glob(f"*____{anio}*T*.nc")):
        if fecha_de_nombre(p.name).startswith(str(anio)):
            por_dia.setdefault(fecha_de_nombre(p.name), []).append(p)
    if not por_dia:
        return None, None, {"archivos": 0}
    suma, cuenta, filas, leidos = np.zeros(n), np.zeros(n), [], 0
    for dia, rutas in sorted(por_dia.items()):
        s_d, c_d = np.zeros(n), np.zeros(n)
        for p in rutas:
            try:
                px = leer_orbita_no2(p)
            except Exception as e:  # noqa: BLE001  (una órbita ilegible no bota el año)
                log.warning("TROPOMI ilegible %s: %s", p.name, e)
                continue
            leidos += 1
            b = _bin_tropomi(px["lat"].to_numpy(), px["lon"].to_numpy())
            ok = b >= 0
            np.add.at(s_d, b[ok], px["no2_trop"].to_numpy("float64")[ok]); np.add.at(c_d, b[ok], 1.0)
        with np.errstate(invalid="ignore", divide="ignore"):
            x = np.where(c_d > 0, s_d / c_d, np.nan)
        suma += np.nan_to_num(x); cuenta += np.isfinite(x)
        media = media_por_zona(x[None, :], W)[0]
        filas += [{"fecha": pd.Timestamp(dia), "zona": z, "no2_trop": media[k]} for k, z in enumerate(ZONAS)]
    with np.errstate(invalid="ignore", divide="ignore"):
        mapa = pd.DataFrame({"pixel_id": bins, "no2_trop": np.where(cuenta > 0, suma / cuenta, np.nan).astype("float32")})
    return mapa[mapa["no2_trop"].notna()].reset_index(drop=True), pd.DataFrame(filas), {"archivos": leidos, "dias": len(por_dia)}


def pixel_de_celda(fuente: str, celdas: pd.DataFrame, enlaces: pd.DataFrame) -> np.ndarray:
    """Identificador del píxel nativo (o del bin de 0,05° en TROPOMI) al que pertenece cada celda."""
    if fuente == "tropomi":
        return _bin_tropomi(celdas["lat"].to_numpy(), celdas["lon"].to_numpy())
    if fuente in ("acag", "lulc"):
        return celdas["celda"].to_numpy("int64")
    return enlaces[f"{fuente}_pixel"].to_numpy("int64")


# ---------------------------------------------------------------------------
# ACAG mensual y uso de suelo / población anuales (ya en la grilla de 0,01°)
# ---------------------------------------------------------------------------
def _serie_por_celda(valores: np.ndarray, macrozona_cod: np.ndarray, lat: np.ndarray) -> np.ndarray:
    ids = np.arange(len(valores), dtype="int64")
    return media_por_zona(valores[None, :].astype("float64"), Pesos(ids, macrozona_cod, lat).matriz(ids))[0]


def extraer_acag(anio: int, celdas: pd.DataFrame, enlaces: pd.DataFrame):
    ids, mz, lat = celdas["celda"].to_numpy("int64"), celdas["macrozona_cod"].to_numpy(), celdas["lat"].to_numpy()
    pila, filas = [], []
    for mes in range(1, 13):
        df = acag_mes(f"{anio}{mes:02d}")
        if df is None:
            continue
        v = df.set_index("celda")["acag_pm25"].reindex(ids).to_numpy("float64")
        pila.append(v)
        media = _serie_por_celda(v, mz, lat)
        filas += [{"fecha": pd.Timestamp(anio, mes, 1), "zona": z, "pm25": media[k]} for k, z in enumerate(ZONAS)]
    if not pila:
        return None, None, {"archivos": 0}
    mapa = pd.DataFrame({"pixel_id": ids, "pm25": np.nanmean(np.vstack(pila), axis=0).astype("float32")})
    return mapa, pd.DataFrame(filas), {"archivos": len(pila)}


def extraer_lulc(anio: int, celdas: pd.DataFrame, enlaces: pd.DataFrame):
    variables = list(VARIABLES["lulc"])
    if not LULC_PATH.exists():                                   # las estáticas aún no se han calculado
        return None, None, {"archivos": 0, "motivo": f"falta {LULC_PATH.name}"}
    t = pd.read_parquet(LULC_PATH, columns=["celda", "anio", "lulc_anio_raster", *variables], filters=[("anio", "==", anio)])
    if t.empty:
        return None, None, {"archivos": 0}
    t = t.set_index("celda").reindex(celdas["celda"])
    mz = celdas["macrozona_cod"].to_numpy()
    mapa = pd.DataFrame({"pixel_id": celdas["celda"].to_numpy("int64"), **{v: t[v].to_numpy("float32") for v in variables}})
    medias = {v: _serie_por_celda(t[v].to_numpy("float64"), mz, celdas["lat"].to_numpy()) for v in variables}
    serie = pd.DataFrame([{"fecha": pd.Timestamp(anio, 1, 1), "zona": z, **{v: medias[v][k] for v in variables}}
                          for k, z in enumerate(ZONAS)])
    return mapa, serie, {"archivos": 1, "anio_raster_lulc": int(pd.Series(t["lulc_anio_raster"]).dropna().mode().iloc[0])}


EXTRACTORES = {"maiac": extraer_maiac, "tropomi": extraer_tropomi, "acag": extraer_acag, "lulc": extraer_lulc}


# ---------------------------------------------------------------------------
# Caché y ejecución
# ---------------------------------------------------------------------------
def rutas(fuente: str, anio: int) -> tuple[Path, Path, Path]:
    base = DIR / fuente
    return base / f"mapa_{fuente}_{anio}.parquet", base / f"serie_{fuente}_{anio}.parquet", base / f"resumen_{fuente}_{anio}.json"


def identidad_enlaces() -> str:
    """sha256 de ``enlaces_productos.parquet`` anotado al publicar la grilla (los pesos por zona dependen de él)."""
    import json
    meta = GRILLA_DIR / "metadata.json"
    return str(json.loads(meta.read_text(encoding="utf-8")).get("archivos", {}).get("enlaces_productos", "")) if meta.exists() else ""


def vigente(fuente: str, anio: int) -> dict | None:
    """Resumen cacheado si se calculó con esta versión del algoritmo y con los enlaces actuales."""
    import json
    r_json = rutas(fuente, anio)[2]
    if not r_json.exists():
        return None
    r = json.loads(r_json.read_text(encoding="utf-8"))
    sin_datos_por_falta_de_insumo = (not r.get("con_datos")) and r.get("motivo")
    ok = r.get("version") == VERSION and r.get("enlaces_sha256") == identidad_enlaces() and not sin_datos_por_falta_de_insumo
    return r if ok else None


def extraer(fuente: str, anio: int, forzar: bool = False) -> dict:
    """Calcula (o reutiliza) el mapa y la serie de ``fuente`` en ``anio``; devuelve su resumen."""
    r_mapa, r_serie, r_json = rutas(fuente, anio)
    if not forzar and (r := vigente(fuente, anio)) is not None:
        return r
    celdas, enlaces = _contexto()
    if fuente in MENSUALES:
        mapa, serie, info = extraer_mensual(fuente, anio, celdas, enlaces)
    else:
        mapa, serie, info = EXTRACTORES[fuente](anio, celdas, enlaces)
    resumen = {"schema": "airpollution.modelo-1km.descriptivo-fuentes.v2", "contrato": CONTRATO, "fuente": fuente,
               "anio": anio, "con_datos": mapa is not None, "version": VERSION, "enlaces_sha256": identidad_enlaces(),
               "ponderacion": "área: Σ cos(latitud) de las celdas de 0,01° enlazadas", "codigo": hash_codigo(), **info}
    if mapa is not None:
        con_valor = serie.dropna(how="all", subset=[c for c in serie.columns if c not in ("fecha", "zona")])
        resumen["pixeles"] = int(len(mapa))
        resumen["dias_en_la_serie"] = int(con_valor["fecha"].nunique())
        resumen["primera_fecha"], resumen["ultima_fecha"] = (str(con_valor["fecha"].min().date()), str(con_valor["fecha"].max().date())) \
            if len(con_valor) else (None, None)
        # un «promedio anual» de un año incompleto no es comparable con los demás: se deja dicho
        pasos = {"mensual": 12, "anual": 1}.get(PASO_SERIE.get(fuente, ""), 366 if anio % 4 == 0 else 365)
        resumen["anio_parcial"] = bool(resumen["dias_en_la_serie"] < 0.9 * pasos)
        resumen["sha256_mapa"] = publicar_parquet(mapa, r_mapa)
        resumen["sha256_serie"] = publicar_parquet(serie, r_serie)
    publicar_json(resumen, r_json)
    log.info("descriptivo %s %d: %s", fuente, anio, "sin datos" if mapa is None else f"{len(mapa):,} píxeles, {info}")
    return resumen


def leer(fuente: str, anio: int) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    r_mapa, r_serie, _ = rutas(fuente, anio)
    if not r_mapa.exists():
        return None, None
    return pd.read_parquet(r_mapa), pd.read_parquet(r_serie)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--anios", default=",".join(map(str, anios_muestra())))
    ap.add_argument("--fuentes", default=",".join(VARIABLES))
    ap.add_argument("--procesos", type=int, default=4)
    ap.add_argument("--forzar", action="store_true")
    args = ap.parse_args(argv)
    tareas = [(f, int(a), args.forzar) for f in args.fuentes.split(",") for a in args.anios.split(",")]
    tareas.sort(key=lambda t: {"tropomi": 0, "maiac": 1, "era5land": 2}.get(t[0], 3))      # lo más lento primero
    if args.procesos <= 1:
        res = [extraer(*t) for t in tareas]
    else:
        from joblib import Parallel, delayed
        res = Parallel(n_jobs=args.procesos, backend="loky")(delayed(extraer)(*t) for t in tareas)
    log.info("descriptivo de fuentes: %d tareas, %d con datos → %s", len(res), sum(r["con_datos"] for r in res), DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
