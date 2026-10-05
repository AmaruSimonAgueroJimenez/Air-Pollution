"""Utilidades compartidas por los extractores por estación.

Convención: todos los extractores escriben en ``data/procesado_estacion/``
un parquet chico (estación × fecha o estación × pasada) y llevan un
checkpoint de archivos ya procesados, así que se pueden interrumpir y
reanudar sin perder trabajo.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(os.environ.get("AFG_REPO_ROOT", Path(__file__).resolve().parents[2])).resolve()
_EXPLICIT_DATA_ROOT = os.environ.get("AIR_POLLUTION_DATA_ROOT")
_DATOS_VOLUME = Path("/Volumes/Datos")
AIR_POLLUTION_DATA_ROOT = Path(
    _EXPLICIT_DATA_ROOT
    or Path(os.environ.get("ASESORIAS_DATA_ROOT", "/Volumes/Datos/Asesorias_Data"))
    / "AirPollution" / "data"
).expanduser().resolve()


def require_data_root_available() -> None:
    """Aborta si el fallback externo ya no está montado."""
    if not _EXPLICIT_DATA_ROOT and \
            (AIR_POLLUTION_DATA_ROOT == _DATOS_VOLUME
             or _DATOS_VOLUME in AIR_POLLUTION_DATA_ROOT.parents) and \
            not _DATOS_VOLUME.is_mount():
        raise SystemExit(
            "El volumen externo /Volumes/Datos no está montado; se aborta "
            "para no crear datos en el disco interno. Conecta el disco o "
            "define AIR_POLLUTION_DATA_ROOT explícitamente."
        )


require_data_root_available()
DATA = AIR_POLLUTION_DATA_ROOT
CONT = DATA / "contaminantes"
SALIDA = DATA / "procesado_estacion"
SALIDA.mkdir(parents=True, exist_ok=True)

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


class Checkpoint:
    """Lista de archivos ya procesados (una línea por archivo)."""

    def __init__(self, nombre: str):
        self.ruta = SALIDA / f"_hecho_{nombre}.txt"
        self.hechos = set(self.ruta.read_text().split()) if self.ruta.exists() else set()

    def falta(self, archivos):
        return [f for f in archivos if Path(f).name not in self.hechos]

    def marcar(self, archivo):
        with self.ruta.open("a") as fh:
            fh.write(Path(archivo).name + "\n")
        self.hechos.add(Path(archivo).name)


def anexar_parquet(df: pd.DataFrame, nombre: str, parte: int) -> None:
    """Escribe una parte numerada; ``consolidar`` las une al final."""
    if df is None or not len(df):
        return
    d = SALIDA / f"_partes_{nombre}"
    d.mkdir(exist_ok=True)
    df.to_parquet(d / f"parte_{parte:05d}.parquet", index=False)


def consolidar(nombre: str) -> pd.DataFrame | None:
    d = SALIDA / f"_partes_{nombre}"
    partes = sorted(d.glob("parte_*.parquet")) if d.exists() else []
    if not partes:
        return None
    df = pd.concat([pd.read_parquet(p) for p in partes], ignore_index=True)
    df = df.drop_duplicates()
    df.to_parquet(SALIDA / f"{nombre}.parquet", index=False)
    return df


def consolidar_candidatos(nombre: str) -> pd.DataFrame | None:
    """Consolida pixel/retrieval por estacion sin promediar ni tocar listas.

    Perfiles y kernels son columnas list y no admiten ``drop_duplicates``
    sobre todas las columnas. La llave cientifica reversible es la pareja
    estacion-observacion nativa.
    """
    d = SALIDA / f"_partes_{nombre}"
    partes = sorted(d.glob("parte_*.parquet")) if d.exists() else []
    if not partes:
        return None
    df = pd.concat([pd.read_parquet(p) for p in partes], ignore_index=True)
    llaves = [c for c in ("estacion", "observation_id") if c in df]
    if len(llaves) != 2:
        raise ValueError(f"{nombre}: faltan llaves estacion/observation_id")
    df = df.drop_duplicates(llaves).sort_values(
        [c for c in ("ts_utc", "estacion", "distancia_km") if c in df]
    ).reset_index(drop=True)
    df.to_parquet(SALIDA / f"{nombre}.parquet", index=False)
    return df


def lista_archivos(carpeta: Path, patron: str, prueba: int = 0) -> list[Path]:
    archivos = sorted(carpeta.glob(patron))
    if prueba:
        archivos = archivos[:prueba]
    return archivos
