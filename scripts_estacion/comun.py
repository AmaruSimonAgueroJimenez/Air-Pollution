"""Utilidades compartidas de los extractores por estación.

Todos los extractores leen el maestro SINCA georreferenciado y validado,
escriben su salida en
``output_files/estacion/`` y son RE-EJECUTABLES: cada archivo procesado
queda anotado en un checkpoint (``<nombre>.procesados.txt``) y los
resultados se acumulan en shards parquet que al final se consolidan.
Si el proceso se corta, basta volver a correr el script.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd


def raiz_repo() -> Path:
    """Raíz del repo; los datos pueden vivir fuera de esta carpeta."""
    if os.environ.get("AFG_REPO_ROOT"):
        return Path(os.environ["AFG_REPO_ROOT"]).resolve()
    return Path(__file__).resolve().parents[1]


RAIZ = raiz_repo()
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
SALIDA = RAIZ / "output_files" / "estacion"
SALIDA.mkdir(parents=True, exist_ok=True)


def leer_estaciones() -> pd.DataFrame:
    """Estaciones SINCA validadas contra fichas oficiales y comunas."""
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
    return est.loc[ok, ["estacion", "lat", "lon"]].reset_index(drop=True)


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    la1, lo1, la2, lo2 = map(np.radians, [lat1, lon1, lat2, lon2])
    a = (np.sin((la2 - la1) / 2) ** 2
         + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2)
    return 2 * r * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


class Acumulador:
    """Checkpoint de archivos procesados + shards parquet acumulables."""

    def __init__(self, nombre: str):
        self.nombre = nombre
        self.chk = SALIDA / f"{nombre}.procesados.txt"
        self.dir_shards = SALIDA / f"_{nombre}_shards"
        self.dir_shards.mkdir(exist_ok=True)
        self.vistos = set()
        if self.chk.exists():
            self.vistos = set(self.chk.read_text().split())
        self._buf: list[pd.DataFrame] = []
        self._n_shard = len(list(self.dir_shards.glob("*.parquet")))

    def ya_visto(self, clave: str) -> bool:
        return clave in self.vistos

    def agregar(self, clave: str, df: pd.DataFrame | None):
        if df is not None and len(df):
            self._buf.append(df)
        self.vistos.add(clave)
        with open(self.chk, "a") as f:
            f.write(clave + "\n")
        if sum(len(d) for d in self._buf) > 200_000:
            self._volcar()

    def _volcar(self):
        if not self._buf:
            return
        df = pd.concat(self._buf, ignore_index=True)
        self._n_shard += 1
        df.to_parquet(self.dir_shards / f"s{self._n_shard:04d}.parquet",
                      index=False)
        self._buf = []

    def consolidar(self) -> Path:
        """Une los shards en el parquet final y lo devuelve."""
        self._volcar()
        shards = sorted(self.dir_shards.glob("*.parquet"))
        if not shards:
            raise SystemExit(f"{self.nombre}: sin resultados que consolidar")
        df = pd.concat([pd.read_parquet(s) for s in shards], ignore_index=True)
        df = df.sort_values([c for c in ["estacion", "ts"] if c in df]) \
               .reset_index(drop=True)
        destino = SALIDA / f"{self.nombre}.parquet"
        df.to_parquet(destino, index=False)
        print(f"[{self.nombre}] consolidado: {len(df):,} filas -> {destino}")
        return destino
