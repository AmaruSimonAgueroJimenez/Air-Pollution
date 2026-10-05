"""Utilidades para conservar observaciones L2 en su huella y tiempo nativos.

Este modulo no descarga nada. Lee escalas HDF-EOS, convierte el reloj TAI93
de OMI/MOPITT, construye huellas y cruza cada observacion con la mascara
administrativa completa de Chile. ``cod_comuna=0`` se conserva; ``-1`` indica
que el centro cae fuera, aunque la huella todavia intersecte Chile.
"""
from __future__ import annotations

import importlib.metadata
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from _satellite_streaming import (
    componentes_shapefile,
    sha256_archivo,
    sha256_conjunto,
)


# Fechas UTC en que entro en vigor cada segundo intercalar posterior a TAI93.
_SALTOS_UTC = pd.DatetimeIndex([
    "1993-07-01", "1994-07-01", "1996-01-01", "1997-07-01",
    "1999-01-01", "2006-01-01", "2009-01-01", "2012-07-01",
    "2015-07-01", "2017-01-01",
], tz="UTC")


def tai93_a_utc(valores) -> pd.DatetimeIndex:
    """Convierte el TAI93 de OMI/MOPITT a UTC y conserva microsegundos.

    En estas colecciones ``Time % 86400 - SecondsInDay`` coincide con el
    numero de saltos desde 1993 (5 s en la muestra oficial del 01-01-2005).
    Por ello no se aplica el segundo base adicional usado por algunos SDS EOS.
    """
    valores = np.asarray(valores, dtype=np.float64).reshape(-1)
    candidatos_tai = pd.to_datetime(
        valores, unit="s", origin="1993-01-01", utc=True, errors="coerce",
    )
    n_saltos = np.zeros(len(candidatos_tai), dtype=np.int8)
    for salto in _SALTOS_UTC:
        n_saltos += np.asarray(candidatos_tai >= salto, dtype=np.int8)
    return (candidatos_tai - pd.to_timedelta(n_saltos, unit="s")).round("us")


def expandir_scanline(valores, forma: tuple[int, int]) -> np.ndarray:
    """Expande un valor por scanline a la grilla scanline x cross-track."""
    arr = np.asarray(valores)
    if arr.shape == forma:
        return arr
    if arr.size == forma[0]:
        return np.repeat(arr.reshape(-1, 1), forma[1], axis=1)
    raise ValueError(f"campo temporal {arr.shape} incompatible con {forma}")


def _atributo_escalar(ds, *nombres):
    for nombre in nombres:
        if nombre in ds.attrs:
            valor = np.asarray(ds.attrs[nombre]).reshape(-1)
            if len(valor):
                return valor[0]
    return None


def leer_fisico(ds) -> np.ndarray:
    """Lee un SDS numerico aplicando fill, rango, escala y offset."""
    crudo = np.asarray(ds[:])
    salida = crudo.astype(np.float64)
    mascara = ~np.isfinite(salida)
    for clave in ("_FillValue", "MissingValue", "missing_value"):
        fill = _atributo_escalar(ds, clave)
        if fill is not None:
            mascara |= crudo == fill
    rango = None
    for clave in ("ValidRange", "valid_range"):
        if clave in ds.attrs:
            candidato = np.asarray(ds.attrs[clave]).reshape(-1)
            if len(candidato) >= 2:
                rango = candidato[:2].astype(np.float64)
                break
    if rango is not None:
        mascara |= (salida < rango[0]) | (salida > rango[1])
    escala = _atributo_escalar(ds, "ScaleFactor", "scale_factor")
    offset = _atributo_escalar(ds, "Offset", "add_offset")
    salida = salida * float(1.0 if escala is None else escala)
    salida += float(0.0 if offset is None else offset)
    salida[mascara] = np.nan
    return salida


def leer_entero(ds, fill: int = -1) -> np.ndarray:
    """Lee banderas enteras sin decodificarlas; fill se representa por -1."""
    crudo = np.asarray(ds[:])
    salida = crudo.astype(np.int64)
    for clave in ("_FillValue", "MissingValue", "missing_value"):
        valor = _atributo_escalar(ds, clave)
        if valor is not None:
            salida[crudo == valor] = fill
    return salida


def campo(grupo, nombre: str, *, entero: bool = False,
          requerido: bool = True) -> np.ndarray | None:
    if nombre not in grupo:
        if requerido:
            raise KeyError(f"falta SDS obligatorio {grupo.name}/{nombre}")
        return None
    return leer_entero(grupo[nombre]) if entero else leer_fisico(grupo[nombre])


def esquinas_desde_centros(lat, lon) -> tuple[np.ndarray, np.ndarray]:
    """Infiere cuatro vertices cuando el producto no publica corners.

    OMTO3 v004 no incluye vertices. Se preservan sus centros nativos y esta
    aproximacion explicita usa los gradientes locales del propio swath, sin
    remuestrear ni agregar observaciones.
    """
    lat = np.asarray(lat, dtype=np.float64)
    lon = np.asarray(lon, dtype=np.float64)
    if lat.ndim != 2 or lon.shape != lat.shape:
        raise ValueError("centros de swath deben ser matrices 2-D congruentes")
    lon_u = np.rad2deg(np.unwrap(np.deg2rad(lon), axis=1))
    dlat_f = np.gradient(lat, axis=0)
    dlat_c = np.gradient(lat, axis=1)
    dlon_f = np.gradient(lon_u, axis=0)
    dlon_c = np.gradient(lon_u, axis=1)
    # SW, SE, NE, NW alrededor del centro.
    signos = ((-1, -1), (-1, 1), (1, 1), (1, -1))
    clat = np.stack([
        lat + 0.5 * sf * dlat_f + 0.5 * sc * dlat_c
        for sf, sc in signos
    ], axis=-1)
    clon = np.stack([
        lon_u + 0.5 * sf * dlon_f + 0.5 * sc * dlon_c
        for sf, sc in signos
    ], axis=-1)
    clon = ((clon + 180.0) % 360.0) - 180.0
    return clat.astype(np.float32), clon.astype(np.float32)


def esquinas_mopitt(lat, lon, lado_km: float = 22.0):
    """Representa la huella nominal 22 x 22 km centrada en cada retrieval.

    MOP02J publica el centro pero no vertices por observacion. Los cuatro
    vertices geodesicos se guardan con ``huella_fuente`` que documenta esta
    limitacion; no se atribuyen falsamente al HDF.
    """
    from pyproj import Geod

    lat = np.asarray(lat, dtype=np.float64).reshape(-1)
    lon = np.asarray(lon, dtype=np.float64).reshape(-1)
    geod = Geod(ellps="WGS84")
    distancia = lado_km * 1000.0 / np.sqrt(2.0)
    lats, lons = [], []
    for rumbo in (225.0, 315.0, 45.0, 135.0):
        lo, la, _ = geod.fwd(lon, lat, np.full(len(lat), rumbo),
                             np.full(len(lat), distancia))
        lats.append(la)
        lons.append(lo)
    return (np.stack(lats, axis=1).astype(np.float32),
            np.stack(lons, axis=1).astype(np.float32))


def _territorio(lon: float, lat: float) -> str:
    if lon < -107.0:
        return "rapa_nui"
    if lon < -100.0:
        return "sala_y_gomez"
    if lon < -77.0:
        return "juan_fernandez" if lat < -30.0 else "desventuradas"
    return "continente"


class MascaraHuellasChile:
    """Selecciona huellas que intersectan al menos una unidad de Chile."""

    def __init__(self, comunas, aois):
        from shapely.prepared import prep

        self.comunas = comunas.reset_index(drop=True).copy()
        self.aois = tuple(aois)
        self.union = self.comunas.geometry.union_all()
        self.union_preparada = prep(self.union)
        self.sindex = self.comunas.sindex
        self.codigos = pd.to_numeric(
            self.comunas["cod_comuna"], errors="raise",
        ).astype("int64").to_numpy()
        self.nombres = self.comunas["Comuna"].fillna("").astype(str).to_numpy()

    def _candidatos(self, lat, lon, clat, clon) -> np.ndarray:
        lat = np.asarray(lat).reshape(-1)
        lon = np.asarray(lon).reshape(-1)
        clat = np.asarray(clat).reshape(-1, 4)
        clon = np.asarray(clon).reshape(-1, 4)
        minlat = np.nanmin(np.column_stack([clat, lat]), axis=1)
        maxlat = np.nanmax(np.column_stack([clat, lat]), axis=1)
        minlon = np.nanmin(np.column_stack([clon, lon]), axis=1)
        maxlon = np.nanmax(np.column_stack([clon, lon]), axis=1)
        finitos = np.isfinite(lat) & np.isfinite(lon)
        ok = np.zeros(len(lat), dtype=bool)
        for aoi in self.aois:
            x0, y0, x1, y1 = aoi.bbox
            ok |= ((maxlon >= x0) & (minlon <= x1) &
                   (maxlat >= y0) & (minlat <= y1))
        return np.flatnonzero(ok & finitos)

    def seleccionar(self, lat, lon, clat, clon) -> pd.DataFrame:
        """Devuelve posiciones y etiquetas; no agrega ni promedia pixeles."""
        from shapely.geometry import Point, Polygon

        forma = np.asarray(lat).shape
        lat1 = np.asarray(lat, dtype=np.float64).reshape(-1)
        lon1 = np.asarray(lon, dtype=np.float64).reshape(-1)
        cla = np.asarray(clat, dtype=np.float64).reshape(-1, 4)
        clo = np.asarray(clon, dtype=np.float64).reshape(-1, 4)
        candidatos = self._candidatos(lat1, lon1, cla, clo)
        filas = []
        ncol = forma[1] if len(forma) == 2 else 1
        for pos in candidatos:
            vertices = [(float(clo[pos, k]), float(cla[pos, k])) for k in range(4)
                        if np.isfinite(clo[pos, k]) and np.isfinite(cla[pos, k])]
            punto = Point(float(lon1[pos]), float(lat1[pos]))
            huella = Polygon(vertices) if len(vertices) == 4 else punto
            if not huella.is_valid:
                huella = huella.buffer(0)
            if huella.is_empty:
                huella = punto
            if not (self.union_preparada.intersects(huella) or
                    self.union_preparada.intersects(punto)):
                continue
            tocadas = np.asarray(
                self.sindex.query(huella, predicate="intersects"),
                dtype=np.int64,
            ).reshape(-1)
            centro = np.asarray(
                self.sindex.query(punto, predicate="intersects"),
                dtype=np.int64,
            ).reshape(-1)
            if len(centro):
                # Eleccion determinista si el centro cae exactamente en borde.
                ci = int(sorted(centro, key=lambda x: (self.codigos[x], x))[0])
                codigo = int(self.codigos[ci])
                etiqueta = ("Zona sin demarcar" if codigo == 0
                            else str(self.nombres[ci]).strip() or f"Comuna {codigo}")
            else:
                codigo = -1
                etiqueta = "Huella toca Chile; centro fuera de la mascara"
            pares = sorted({
                (int(self.codigos[i]),
                 "Zona sin demarcar" if int(self.codigos[i]) == 0
                 else str(self.nombres[i]).strip() or f"Comuna {int(self.codigos[i])}")
                for i in tocadas
            })
            filas.append({
                "_pos": int(pos),
                "fila": int(pos // ncol),
                "columna": int(pos % ncol),
                "cod_comuna": codigo,
                "etiqueta_comuna": etiqueta,
                "cod_comunas_huella": ";".join(str(x[0]) for x in pares),
                "comunas_huella": ";".join(x[1] for x in pares),
                "n_comunas_huella": len(pares),
                "criterio_inclusion": (
                    "centro_y_huella" if len(centro) else "solo_huella"
                ),
                "territorio": _territorio(float(lon1[pos]), float(lat1[pos])),
            })
        return pd.DataFrame(filas)


def agregar_esquinas(df: pd.DataFrame, clat, clon,
                      posiciones) -> pd.DataFrame:
    posiciones = np.asarray(posiciones, dtype=np.int64)
    cla = np.asarray(clat).reshape(-1, 4)[posiciones]
    clo = np.asarray(clon).reshape(-1, 4)[posiciones]
    for k in range(4):
        df[f"corner{k}_lat"] = cla[:, k].astype(np.float32)
        df[f"corner{k}_lon"] = clo[:, k].astype(np.float32)
    return df


def detalles_runtime(script: Path, shapefile: Path, aois) -> dict:
    """Proveniencia suficiente para reconstruir cada archivo Parquet."""
    paquetes = {}
    for nombre in ("earthaccess", "h5py", "numpy", "pandas", "pyarrow",
                   "geopandas", "shapely", "pyproj"):
        try:
            paquetes[nombre] = importlib.metadata.version(nombre)
        except importlib.metadata.PackageNotFoundError:
            paquetes[nombre] = None
    carpeta = Path(__file__).resolve().parent
    compartidos = [
        Path(__file__).resolve(),
        carpeta / "_satellite_streaming.py",
        carpeta / "_chile_aoi.py",
        carpeta / "_common.py",
    ]
    return {
        "script": {"ruta": str(Path(script).resolve()),
                   "sha256": sha256_archivo(Path(script).resolve())},
        "codigo_compartido": [
            {"ruta": str(p), "sha256": sha256_archivo(p)} for p in compartidos
        ],
        "python": {"version": sys.version, "executable": sys.executable,
                   "platform": platform.platform()},
        "dependencias": paquetes,
        "mascara": {
            "ruta": str(Path(shapefile).resolve()),
            "componentes": [str(p) for p in componentes_shapefile(shapefile)],
            "sha256_componentes": sha256_conjunto(componentes_shapefile(shapefile)),
            "cod_cero": "Zona sin demarcar; se conserva",
            "codigo_centro_fuera": -1,
        },
        "aois": [
            {"id": a.id, "territorio": a.territorio, "bbox": list(a.bbox)}
            for a in aois
        ],
        "antartica": False,
        "creado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
