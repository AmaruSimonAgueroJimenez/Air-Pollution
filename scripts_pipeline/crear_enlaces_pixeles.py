#!/usr/bin/env python3
"""Crea enlaces píxel↔comuna (muchos-a-muchos) y píxel↔estación SINCA.

Lee una muestra espacial validada por AOI (OMI, MOPITT, ACAG o Black Marble),
conserva una fila por intersección píxel-comuna y calcula la fracción de la
celda cubierta. Nunca promedia observaciones. Para SINCA exige exactamente
``data/sinca/estaciones_georreferenciadas.csv`` y ``usable_geoespacial=True``;
no usa el maestro histórico sin QC.
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import DATA, ensure_dir  # noqa: E402
from _chile_aoi import resumen_mascara  # noqa: E402
from _manifiesto_satelital import (  # noqa: E402
    Manifiesto, sha256, sha256_conjunto_shapefile,
)


def _malla(path: Path) -> pd.DataFrame:
    """Extrae sólo píxeles cuya huella toca Chile; una fila por pixel_id."""
    path = Path(path)
    if path.suffix.lower() in {".he5", ".h5", ".hdf5"}:
        import h5py
        with h5py.File(path, "r") as h:
            s = h["ChileSubset"]
            lat, lon = np.asarray(s["latitude"]), np.asarray(s["longitude"])
            pix, toca = np.asarray(s["pixel_id"]), np.asarray(s["toca_chile"]).astype(bool)
            resolucion = float(h.attrs.get("spatial_resolution_degrees", np.nan))
    elif path.suffix.lower() == ".nc":
        import netCDF4
        import shapely

        with netCDF4.Dataset(path) as nc:
            es_tropomi = "PRODUCT" in nc.groups and "CHILE_SUBSET" in nc.groups
            if es_tropomi:
                prod, sub = nc["PRODUCT"], nc["CHILE_SUBSET"]

                def espacial(var):
                    arr = np.ma.masked_invalid(var[:])
                    dims = tuple(var.dimensions)
                    arr = np.moveaxis(
                        arr, (dims.index("scanline"), dims.index("ground_pixel")),
                        (0, 1))
                    return np.squeeze(arr)

                lat, lon = espacial(prod["latitude"]), espacial(prod["longitude"])
                pix = np.asarray(sub["pixel_id"][:], dtype="int64")
                toca = np.asarray(sub["toca_chile"][:], dtype=bool)
                geo = prod["SUPPORT_DATA"]["GEOLOCATIONS"]
                lat_b = espacial(geo["latitude_bounds"])
                lon_b = espacial(geo["longitude_bounds"])
                if lat_b.ndim != 3 or lon_b.shape != lat_b.shape:
                    raise ValueError(f"{path.name}: bounds TROPOMI inconsistentes")
                iy, ix = np.where(toca)
                coords = np.stack([lon_b[iy, ix], lat_b[iy, ix]], axis=-1)
                if not np.all(np.isfinite(coords)):
                    raise ValueError(f"{path.name}: bounds no finitos en píxeles Chile")
                geoms = shapely.make_valid(shapely.polygons(coords))
                granule = str(getattr(sub, "granule_id", path.stem))
                return pd.DataFrame({
                    "pixel_id": pix[iy, ix],
                    "lat": np.asarray(lat)[iy, ix].astype(float),
                    "lon": np.asarray(lon)[iy, ix].astype(float),
                    "granule_id": granule,
                    "source_file": str(path),
                    "geometry": list(geoms),
                })
        import xarray as xr
        with xr.open_dataset(path, decode_times=False) as d:
            lat, lon = np.asarray(d.lat), np.asarray(d.lon)
            pix, toca = np.asarray(d.pixel_id), np.asarray(d.toca_chile).astype(bool)
            resolucion = float(d.attrs.get("spatial_resolution_degrees", np.nan))
    else:
        raise ValueError(f"formato no soportado: {path}")
    if lat.ndim == lon.ndim == 1:
        lat, lon = np.meshgrid(lat, lon, indexing="ij")
    if lat.shape != lon.shape or pix.shape != lat.shape or toca.shape != lat.shape:
        raise ValueError(f"{path.name}: malla/pixel_id/toca_chile inconsistentes")
    iy, ix = np.where(toca)
    return pd.DataFrame({"pixel_id": pix[iy, ix].astype("int64"),
                         "lat": lat[iy, ix].astype(float),
                         "lon": lon[iy, ix].astype(float),
                         "resolution_degrees": resolucion})


def _resolucion(pix: pd.DataFrame):
    if "resolution_degrees" in pix:
        declaradas = pd.to_numeric(
            pix.resolution_degrees, errors="coerce").dropna().unique()
        if len(declaradas):
            if not np.allclose(declaradas, declaradas[0]):
                raise ValueError(f"muestras mezclan resoluciones {declaradas.tolist()}")
            return float(declaradas[0]), float(declaradas[0])
    lats = np.sort(pix.lat.unique())
    lons = np.sort(pix.lon.unique())
    dy = float(np.median(np.diff(lats))) if len(lats) > 1 else np.nan
    dx = float(np.median(np.diff(lons))) if len(lons) > 1 else np.nan
    # AOIs insulares pueden tener sólo una fila/columna. Usa la menor
    # separación positiva disponible; el llamador debe aportar otra muestra si
    # ambas quedan indeterminadas.
    disponibles = [abs(x) for x in (dx, dy) if np.isfinite(x) and x]
    if not disponibles:
        raise ValueError("no se pudo inferir tamaño de celda; añade muestra continental")
    base = min(disponibles)
    return abs(dx) if np.isfinite(dx) else base, abs(dy) if np.isfinite(dy) else base


def construir_enlace(pix: pd.DataFrame, comunas_path: Path,
                     *, lote: int = 20_000) -> pd.DataFrame:
    import geopandas as gpd
    import shapely

    huella_nativa = "geometry" in pix and pix["geometry"].notna().all()
    if not huella_nativa:
        dx, dy = _resolucion(pix)
    comunas = gpd.read_file(comunas_path).to_crs("EPSG:4326")
    try:
        comunas["geometry"] = comunas.geometry.make_valid()
    except AttributeError:
        from shapely.validation import make_valid
        comunas["geometry"] = comunas.geometry.map(make_valid)
    cols = [c for c in ("cod_comuna", "Comuna", "Provincia", "Region")
            if c in comunas.columns]
    comunas = comunas[cols + ["geometry"]]
    partes = []
    for inicio in range(0, len(pix), lote):
        p = pix.iloc[inicio:inicio + lote].copy()
        if huella_nativa:
            geoms = p.pop("geometry").to_numpy()
        else:
            geoms = shapely.box(p.lon.to_numpy() - dx / 2,
                                p.lat.to_numpy() - dy / 2,
                                p.lon.to_numpy() + dx / 2,
                                p.lat.to_numpy() + dy / 2)
        celdas = gpd.GeoDataFrame(p, geometry=geoms, crs="EPSG:4326")
        candidatos = gpd.sjoin(celdas, comunas, how="inner", predicate="intersects")
        if candidatos.empty:
            continue
        geom_comuna = comunas.geometry.loc[candidatos.index_right].reset_index(drop=True)
        geom_celda = candidatos.geometry.reset_index(drop=True)
        inter = gpd.GeoSeries(
            [a.intersection(b) for a, b in zip(geom_celda, geom_comuna, strict=False)],
            crs="EPSG:4326")
        area_inter = inter.to_crs("EPSG:6933").area.to_numpy()
        area_celda = geom_celda.to_crs("EPSG:6933").area.to_numpy()
        candidatos = candidatos.reset_index(drop=True)
        candidatos["area_interseccion_m2"] = area_inter
        candidatos["fraccion_celda"] = np.divide(
            area_inter, area_celda, out=np.zeros_like(area_inter), where=area_celda > 0)
        candidatos = candidatos[candidatos.fraccion_celda > 0]
        partes.append(candidatos.drop(columns=["geometry", "index_right"]))
    if not partes:
        raise ValueError("ningún píxel intersecta las comunas")
    out = pd.concat(partes, ignore_index=True)
    out["cod_comuna"] = pd.to_numeric(out.cod_comuna, errors="raise").astype("int32")
    out = out.sort_values(["pixel_id", "cod_comuna"]).drop_duplicates(
        ["pixel_id", "cod_comuna"])
    if not out.fraccion_celda.between(0, 1.000001).all():
        raise ValueError("fracciones píxel-comuna fuera de rango")
    return out.reset_index(drop=True)


def _haversine(lat1, lon1, lat2, lon2):
    r = 6371.0
    a1, a2 = np.radians(lat1), np.radians(lat2)
    da, do = a2 - a1, np.radians(lon2 - lon1)
    x = np.sin(da / 2) ** 2 + np.cos(a1) * np.cos(a2) * np.sin(do / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(x))


def enlazar_estaciones(enlace: pd.DataFrame, estaciones_path: Path):
    est = pd.read_csv(estaciones_path)
    requeridas = {"estacion", "lat", "lon", "cod_comuna_geografica",
                  "qc_coordenada", "qc_comuna", "usable_geoespacial"}
    faltan = requeridas - set(est.columns)
    if faltan:
        raise ValueError(f"estaciones georreferenciadas sin {sorted(faltan)}")
    usable = est.usable_geoespacial.astype(str).str.lower().isin({"true", "1", "si", "sí"})
    qc_coord_ok = est.qc_coordenada.isin({
        "ficha_sinca_directa", "ficha_sinca_normalizada",
        "documento_mma_supletorio",
    })
    qc_comuna_ok = est.qc_comuna.isin({"coincide", "discrepancia_publicada"})
    finitas = (pd.to_numeric(est.lat, errors="coerce").notna() &
               pd.to_numeric(est.lon, errors="coerce").notna() &
               pd.to_numeric(est.cod_comuna_geografica, errors="coerce").notna())
    validas = usable & qc_coord_ok & qc_comuna_ok & finitas
    excluidas = [
        {"estacion": str(e.estacion), "motivo": "qc_geoespacial_no_valido",
         "qc_coordenada": e.qc_coordenada, "qc_comuna": e.qc_comuna}
        for _, e in est[~validas].iterrows()
    ]
    est = est[validas].copy()
    filas = []
    grupos = (enlace.groupby("granule_id", sort=False)
              if "granule_id" in enlace else [(None, enlace)])
    for granule_id, enlace_granulo in grupos:
        for _, e in est.iterrows():
            cand = enlace_granulo[
                enlace_granulo.cod_comuna == int(e.cod_comuna_geografica)
            ].copy()
            if cand.empty:
                fila = {"estacion": e.estacion,
                        "motivo": "producto_sin_pixel_en_comuna"}
                if granule_id is not None:
                    fila["granule_id"] = granule_id
                excluidas.append(fila)
                continue
            cand["distancia_km"] = _haversine(
                float(e.lat), float(e.lon), cand.lat.to_numpy(), cand.lon.to_numpy())
            mejor = cand.loc[cand.distancia_km.idxmin()]
            fila = {
                "estacion": str(e.estacion), "pixel_id": int(mejor.pixel_id),
                "cod_comuna": int(mejor.cod_comuna), "pixel_lat": float(mejor.lat),
                "pixel_lon": float(mejor.lon),
                "distancia_km": float(mejor.distancia_km),
                "qc_coordenada": e.qc_coordenada, "qc_comuna": e.qc_comuna,
                "fuente_estacion": str(estaciones_path),
            }
            if granule_id is not None:
                fila["granule_id"] = granule_id
            filas.append(fila)
    return pd.DataFrame(filas), pd.DataFrame(excluidas)


def _publicar_parquet(df: pd.DataFrame, path: Path):
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.unlink(missing_ok=True)
    try:
        df.to_parquet(tmp, index=False, compression="zstd")
        chk = pd.read_parquet(tmp)
        if len(chk) != len(df):
            raise ValueError(f"{path.name}: validación de filas falló")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--producto", required=True)
    ap.add_argument("--muestras", type=Path, nargs="+", required=True,
                    help="un archivo espacial validado por cada AOI/grilla")
    ap.add_argument("--comunas", type=Path, default=DATA / "comunas.shp")
    ap.add_argument("--estaciones", type=Path,
                    default=DATA / "sinca" / "estaciones_georreferenciadas.csv")
    ap.add_argument("--salida-dir", type=Path)
    ap.add_argument("--lote", type=int, default=20_000)
    ap.add_argument("--forzar", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    for p in [*args.muestras, args.comunas, args.estaciones]:
        if not p.exists():
            ap.error(f"no existe {p}")
    salida = ensure_dir(args.salida_dir or
                        (DATA / "enlaces_geoespaciales" / args.producto.lower()))
    p_com = salida / "pixel_comuna.parquet"
    p_est = salida / "estacion_pixel.parquet"
    p_exc = salida / "estaciones_excluidas.parquet"
    if not args.forzar and all(p.exists() for p in (p_com, p_est, p_exc)):
        try:
            for p in (p_com, p_est, p_exc):
                pd.read_parquet(p)
        except Exception:
            pass  # conjunto incompleto/corrupto: se reconstruye atómicamente
        else:
            print(f"Ya existen enlaces validados en {salida}; usa --forzar para rehacer")
            return

    pix = pd.concat([_malla(p) for p in args.muestras], ignore_index=True)
    pix = pix.drop_duplicates("pixel_id").sort_values("pixel_id").reset_index(drop=True)
    if args.dry_run:
        print(f"{len(pix):,} píxeles únicos; no se escribieron enlaces")
        return
    enlace = construir_enlace(pix, args.comunas, lote=args.lote)
    estaciones, excluidas = enlazar_estaciones(enlace, args.estaciones)
    _publicar_parquet(enlace, p_com)
    _publicar_parquet(estaciones, p_est)
    _publicar_parquet(excluidas, p_exc)
    mani = Manifiesto(salida / "_manifiestos", f"ENLACE_{args.producto}", {
        "muestras": [{"ruta": str(p), "sha256": sha256(p)} for p in args.muestras],
        "comunas": str(args.comunas),
        "comunas_sha256": sha256_conjunto_shapefile(args.comunas),
        "unidades_administrativas": resumen_mascara(args.comunas),
        "estaciones": str(args.estaciones),
        "estaciones_sha256": sha256(args.estaciones),
        "semantica": "muchos-a-muchos por intersección; sin agregación",
    })
    mani.terminar(pixeles=len(pix), enlaces=len(enlace),
                  estaciones=len(estaciones), excluidas=len(excluidas))
    print(f"{len(enlace):,} enlaces píxel-comuna; {len(estaciones)} estaciones → {salida}")


if __name__ == "__main__":
    main()
