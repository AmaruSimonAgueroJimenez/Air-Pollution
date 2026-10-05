"""Utilidades compartidas por los extractores por estación.

Todos los extractores leen el maestro SINCA georreferenciado contra las
fichas oficiales y comunas, y escriben su salida en
``data/procesado_estacion/<producto>_estacion_<diario|horario>.parquet``,
que ``tabla_predictores()`` integra automáticamente.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def raiz_repo() -> Path:
    if os.environ.get("AFG_REPO_ROOT"):
        return Path(os.environ["AFG_REPO_ROOT"]).resolve()
    return Path(__file__).resolve().parents[2]


RAIZ = raiz_repo()
_EXPLICIT_DATA_ROOT = os.environ.get("AIR_POLLUTION_DATA_ROOT")
_DATOS_VOLUME = Path("/Volumes/Datos")
AIR_POLLUTION_DATA_ROOT = Path(
    _EXPLICIT_DATA_ROOT
    or Path(os.environ.get("ASESORIAS_DATA_ROOT", "/Volumes/Datos/Asesorias_Data"))
    / "AirPollution" / "data"
).expanduser().resolve()
if not _EXPLICIT_DATA_ROOT and \
        (AIR_POLLUTION_DATA_ROOT == _DATOS_VOLUME
         or _DATOS_VOLUME in AIR_POLLUTION_DATA_ROOT.parents) and \
        not _DATOS_VOLUME.is_mount():
    raise SystemExit(
        "El volumen externo /Volumes/Datos no está montado. Conecta el disco "
        "o define AIR_POLLUTION_DATA_ROOT explícitamente."
    )
DATA = AIR_POLLUTION_DATA_ROOT
CONT = DATA / "contaminantes"
PROCESADO = DATA / "procesado_estacion"
PROCESADO.mkdir(parents=True, exist_ok=True)
CACHE = PROCESADO / "_cache"        # resultados por archivo (reanudable)
CACHE.mkdir(exist_ok=True)


def leer_estaciones() -> pd.DataFrame:
    ruta = DATA / "sinca" / "estaciones_georreferenciadas.csv"
    if not ruta.exists():
        raise SystemExit(
            "Falta estaciones_georreferenciadas.csv; ejecuta primero "
            "scripts_pipeline/actualizar_geometria_sinca.py"
        )
    est = pd.read_csv(ruta)
    est["estacion"] = est["estacion"].astype(str)
    valores = est["usable_geoespacial"]
    if valores.dtype == bool:
        ok = valores.fillna(False)
    else:
        normalizados = valores.astype("string").str.strip().str.lower()
        invalidos = normalizados[~normalizados.isin(["true", "false"])].dropna()
        if len(invalidos):
            raise SystemExit("usable_geoespacial contiene valores inválidos")
        ok = normalizados.map({"true": True, "false": False}).fillna(False)
    return est.loc[ok, ["estacion", "nombre", "lat", "lon"]].reset_index(drop=True)


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    la1, lo1, la2, lo2 = map(np.radians, [lat1, lon1, lat2, lon2])
    a = (np.sin((la2 - la1) / 2) ** 2
         + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2)
    return 2 * r * np.arcsin(np.sqrt(a))


def xyz(lat, lon):
    """Coordenadas cartesianas unitarias (para KD-tree en la esfera)."""
    la, lo = np.radians(lat), np.radians(lon)
    return np.column_stack([np.cos(la) * np.cos(lo),
                            np.cos(la) * np.sin(lo), np.sin(la)])


def radio_a_cuerda(radio_km: float) -> float:
    """Distancia de cuerda (en unidades de radio terrestre) equivalente a un
    radio geodésico, para usar query_ball_point sobre xyz unitarios."""
    return 2 * np.sin(radio_km / 6371.0 / 2)


def progreso(i: int, n: int, cada: int = 50, etiqueta: str = ""):
    if i % cada == 0 or i == n:
        print(f"  {etiqueta} {i}/{n}", flush=True)


def escribir_salida(df: pd.DataFrame, nombre: str):
    ruta = PROCESADO / f"{nombre}.parquet"
    df.to_parquet(ruta, index=False)
    print(f"→ {ruta}  ({len(df):,} filas, {df['estacion'].nunique()} estaciones)")
    return ruta
