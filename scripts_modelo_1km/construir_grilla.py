#!/usr/bin/env python3
"""Grilla de predicción 0,01° (≈1 km) y enlaces a cada producto nativo.

La grilla es la de ACAG V6GL03 (centros en k·0,01 + 0,005): 838.048 celdas
continentales más Juan Fernández y Desventuradas desde los recortes ACAG, y
celdas generadas con la misma malla para Rapa Nui y Sala y Gómez, que ACAG no
cubre. ``celda`` es el ``pixel_id`` ACAG (fila global × 5101 + columna) o
``900000000 + k`` para las celdas generadas.

Para cada celda y cada estación SINCA se enlaza el píxel nativo más cercano
de ERA5-Land (0,1°), ERA5 BLH (0,25°), MERRA-2 (0,5°×0,625°), CAMS (0,75°),
GEOS-CF (0,25°) y MAIAC (1 km sinusoidal), con su distancia. No se
interpola: cada celda hereda el valor del píxel al que pertenece.

El enlace es al píxel **válido** más cercano. ERA5-Land no tiene valores
sobre el mar (~16 % de los píxeles del recorte son NaN constante): una celda
costera cuyo píxel propio es mar se enlaza al píxel de tierra más cercano,
dentro de un radio ampliado, y queda marcada ``<producto>_enlace =
"vecino_valido"``. Sigue sin interpolarse nada: el valor es el de un píxel
nativo, sólo que no el geométricamente más cercano.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comun_modelo import (  # noqa: E402
    ACAG_DIR, CELDAS_PATH, CONTRATO, DATA, ENLACES_PATH, GRILLA_DIR, ID_INSULAR_BASE,
    MACROZONA_CODIGO, MACROZONA_REGION, MESES_REFERENCIA_VALIDEZ, RES, catalogo_geoscf, catalogo_maiac,
    hash_codigo, leer_catalogo, leer_estaciones, log, pixeles_validos, publicar_json, publicar_parquet,
    rellenar_por_vecino,
)

PRODUCTOS_ENLACE = ("era5land", "era5blh", "merra2", "cams", "geoscf", "maiac")
DISTANCIA_MAX_KM = {"era5land": 9.0, "era5blh": 22.0, "merra2": 45.0, "cams": 65.0,
                    "geoscf": 22.0, "maiac": 1.5}
# Radio ampliado sólo para caer al píxel válido vecino cuando el propio no trae datos (≈ 1,5 píxeles).
DISTANCIA_MAX_VECINO_KM = {"era5land": 16.0, "era5blh": 40.0, "merra2": 90.0, "cams": 120.0}


def _xyz(lat, lon):
    la, lo = np.radians(np.asarray(lat, float)), np.radians(np.asarray(lon, float))
    return np.c_[np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)]


def vecino_mas_cercano(lat_q, lon_q, lat_c, lon_c):
    """Índice y distancia (km) del punto candidato más cercano en la esfera."""
    from scipy.spatial import cKDTree

    arbol = cKDTree(_xyz(lat_c, lon_c))
    d, i = arbol.query(_xyz(lat_q, lon_q))
    return i, 2.0 * 6371.0 * np.arcsin(np.clip(d / 2.0, 0, 1))


def celdas_acag(comunas) -> pd.DataFrame:
    import netCDF4

    archivos = sorted(ACAG_DIR.glob("V6GL03.CNNPM25.SA.*.chile.nc"))
    if not archivos:
        raise SystemExit(f"No hay recortes ACAG en {ACAG_DIR}")
    # Un archivo por AOI basta para la geometría; se toma el mes más reciente.
    por_aoi: dict[str, Path] = {}
    for p in archivos:
        aoi = p.name.split(".")[-3]
        por_aoi[aoi] = p
    partes = []
    for aoi, p in sorted(por_aoi.items()):
        with netCDF4.Dataset(p) as nc:
            lat = np.asarray(nc["lat"][:], float)
            lon = np.asarray(nc["lon"][:], float)
            pid = np.asarray(nc["pixel_id"][:], dtype="int64")
            toca = np.asarray(nc["toca_chile"][:], dtype=bool)
            cod = np.asarray(nc["cod_comuna"][:], dtype="int32")
        iy, ix = np.nonzero(toca)
        partes.append(pd.DataFrame({
            "celda": pid[iy, ix], "lat": lat[iy], "lon": lon[ix],
            "cod_comuna": cod[iy, ix], "aoi_id": aoi, "origen": "acag",
        }))
    return pd.concat(partes, ignore_index=True)


def celdas_generadas(comunas, aois_faltantes=("rapa_nui", "sala_y_gomez")) -> pd.DataFrame:
    """Celdas 0,01° para territorios fuera del dominio ACAG, sobre la misma malla."""
    import shapely
    from shapely.strtree import STRtree

    partes = []
    k0 = ID_INSULAR_BASE
    for aoi in aois_faltantes:
        geoms = comunas[comunas["aoi_id"] == aoi]
        if geoms.empty:
            continue
        union = shapely.union_all(geoms.geometry.to_numpy())
        lon0, lat0, lon1, lat1 = union.bounds
        lons = np.arange(np.floor(lon0 / RES) * RES + RES / 2, lon1 + RES, RES)
        lats = np.arange(np.floor(lat0 / RES) * RES + RES / 2, lat1 + RES, RES)
        la, lo = np.meshgrid(lats, lons, indexing="ij")
        cajas = shapely.box(lo.ravel() - RES / 2, la.ravel() - RES / 2, lo.ravel() + RES / 2, la.ravel() + RES / 2)
        toca = shapely.intersects(cajas, union)
        if not toca.any():
            continue
        centros = shapely.points(lo.ravel()[toca], la.ravel()[toca])
        arbol = STRtree(geoms.geometry.to_numpy())
        idx_c, idx_g = arbol.query(centros, predicate="intersects")
        cod = np.full(int(toca.sum()), -1, dtype="int32")
        cod[idx_c] = geoms["cod_comuna"].to_numpy()[idx_g]
        n = int(toca.sum())
        partes.append(pd.DataFrame({
            "celda": np.arange(k0, k0 + n, dtype="int64"), "lat": la.ravel()[toca], "lon": lo.ravel()[toca],
            "cod_comuna": cod, "aoi_id": aoi, "origen": "generada",
        }))
        k0 += n
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(
        columns=["celda", "lat", "lon", "cod_comuna", "aoi_id", "origen"])


def cargar_comunas():
    import geopandas as gpd

    from _chile_aoi import derivar

    comunas = gpd.read_file(DATA / "comunas.shp").to_crs("EPSG:4326")
    try:
        comunas["geometry"] = comunas.geometry.make_valid()
    except AttributeError:
        from shapely.validation import make_valid
        comunas["geometry"] = comunas.geometry.map(make_valid)
    comunas["cod_comuna"] = pd.to_numeric(comunas["cod_comuna"], errors="raise").astype("int32")
    comunas["codregion"] = pd.to_numeric(comunas["codregion"], errors="coerce").fillna(0).astype("int32")
    aois = derivar(DATA / "comunas.shp")
    centroides = comunas.geometry.representative_point()
    comunas["aoi_id"] = "continente"
    for aoi in aois:
        lon0, lat0, lon1, lat1 = aoi.bbox
        dentro = (centroides.x >= lon0) & (centroides.x <= lon1) & (centroides.y >= lat0) & (centroides.y <= lat1)
        if aoi.id != "continente":
            comunas.loc[dentro, "aoi_id"] = aoi.id
    # Las comunas 5104/5201 son multipolígonos que abarcan varias islas: se etiquetan por parte.
    return comunas


def construir_celdas(comunas) -> pd.DataFrame:
    celdas = pd.concat([celdas_acag(comunas), celdas_generadas(comunas)], ignore_index=True)
    if celdas["celda"].duplicated().any():
        raise ValueError("celda duplicada al unir AOI")
    region = comunas.set_index("cod_comuna")["codregion"].to_dict()
    codregion = celdas["cod_comuna"].map(region).to_numpy(dtype="float64").copy()
    # Celdas cuyo centro cae fuera de toda comuna (−1) o en la zona sin
    # demarcar (región 0) heredan la región de la celda válida más cercana.
    codregion[np.isin(celdas["cod_comuna"].to_numpy(), [-1, 0]) | ~np.isfinite(codregion)] = np.nan
    codregion, relleno = rellenar_por_vecino(celdas["lat"], celdas["lon"], codregion, max_km=30.0)
    celdas["codregion"] = np.nan_to_num(codregion, nan=0).astype("int16")
    celdas["region_rellenada_por_vecino"] = relleno
    macro = celdas["codregion"].map(lambda r: MACROZONA_REGION.get(int(r), "sin_region"))
    macro = np.where(celdas["aoi_id"].isin(["rapa_nui", "sala_y_gomez", "juan_fernandez", "desventuradas"]),
                     "insular", macro)
    celdas["macrozona"] = macro
    celdas["macrozona_cod"] = celdas["macrozona"].map(MACROZONA_CODIGO).astype("int8")
    celdas = celdas.sort_values("celda").reset_index(drop=True)
    celdas["lat"] = celdas["lat"].astype("float64").round(4)
    celdas["lon"] = celdas["lon"].astype("float64").round(4)
    return celdas


def enlazar_pixel_valido(lat_q, lon_q, cat: pd.DataFrame, validos: np.ndarray | None, max_km: float,
                         max_vecino_km: float | None):
    """Píxel enlazado, distancia (km) y tipo de enlace de cada punto.

    Primero el píxel más cercano (``propio``, hasta ``max_km``). Si ese píxel no está entre los
    ``validos`` (p. ej. mar en ERA5-Land), se toma el píxel válido más cercano hasta
    ``max_vecino_km`` (``vecino_valido``). Sin ninguno a distancia admisible queda −1 (``sin_enlace``).
    """
    pid_cat = cat["pixel_id"].to_numpy().astype("int64")
    i, d = vecino_mas_cercano(lat_q, lon_q, cat["lat"].to_numpy(), cat["lon"].to_numpy())
    pid, dist = pid_cat[i].copy(), d.copy()
    tipo = np.full(len(pid), "propio", dtype=object)
    sin = d > max_km
    if validos is not None and max_vecino_km is not None:
        es_valido = np.isin(pid_cat, validos)
        if es_valido.any() and not es_valido.all():
            malo = ~sin & ~es_valido[i]
            if malo.any():
                cv = cat[es_valido]
                j, dv = vecino_mas_cercano(np.asarray(lat_q)[malo], np.asarray(lon_q)[malo],
                                           cv["lat"].to_numpy(), cv["lon"].to_numpy())
                pid[malo], dist[malo] = cv["pixel_id"].to_numpy().astype("int64")[j], dv
                tipo[malo] = "vecino_valido"
                lejos = np.flatnonzero(malo)[dv > max_vecino_km]
                sin[lejos] = True
    pid[sin], tipo[sin] = -1, "sin_enlace"
    return pid, dist.astype("float32"), tipo


def construir_enlaces(puntos: pd.DataFrame, clave: str, validez: dict | None = None) -> pd.DataFrame:
    """Enlaza cada punto (celda o estación) con el píxel **válido** más cercano de cada producto."""
    out = puntos[[clave, "lat", "lon"]].copy()
    catalogos = {p: leer_catalogo(p) for p in ("era5land", "era5blh", "merra2", "cams")}
    geos = catalogo_geoscf()
    if geos is not None:
        catalogos["geoscf"] = geos
    catalogos["maiac"] = catalogo_maiac()
    validez = validez if validez is not None else {p: pixeles_validos(p) for p in DISTANCIA_MAX_VECINO_KM}
    for producto, cat in catalogos.items():
        pid, d, tipo = enlazar_pixel_valido(out["lat"].to_numpy(), out["lon"].to_numpy(), cat, validez.get(producto),
                                            DISTANCIA_MAX_KM[producto], DISTANCIA_MAX_VECINO_KM.get(producto))
        out[f"{producto}_pixel"] = pid
        out[f"{producto}_dist_km"] = d
        if producto in DISTANCIA_MAX_VECINO_KM:
            out[f"{producto}_enlace"] = pd.Categorical(tipo, categories=["propio", "vecino_valido", "sin_enlace"])
        log.info("%s: %d/%d puntos enlazados (propio ≤ %.1f km); %d al píxel válido vecino; %d sin enlace", producto,
                 int((pid >= 0).sum()), len(out), DISTANCIA_MAX_KM[producto], int((tipo == "vecino_valido").sum()),
                 int((pid < 0).sum()))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--forzar", action="store_true")
    args = ap.parse_args(argv)
    if CELDAS_PATH.exists() and ENLACES_PATH.exists() and not args.forzar:
        log.info("Grilla y enlaces ya existen en %s (usa --forzar para rehacer)", GRILLA_DIR)
        return 0
    comunas = cargar_comunas()
    celdas = construir_celdas(comunas)
    log.info("Grilla: %s celdas (%s)", f"{len(celdas):,}", celdas["aoi_id"].value_counts().to_dict())
    validez = {p: pixeles_validos(p) for p in DISTANCIA_MAX_VECINO_KM}
    enlaces = construir_enlaces(celdas, "celda", validez)
    estaciones = leer_estaciones()
    from _comun_modelo import celda_de_lonlat
    estaciones["celda"] = celda_de_lonlat(estaciones["lon"].to_numpy(), estaciones["lat"].to_numpy(), celdas)
    enl_est = construir_enlaces(estaciones, "estacion", validez)
    enl_est = enl_est.merge(estaciones[["estacion", "celda", "cod_comuna", "region_sinca"]], on="estacion")
    sha_c = publicar_parquet(celdas, CELDAS_PATH)
    sha_e = publicar_parquet(enlaces, ENLACES_PATH)
    sha_s = publicar_parquet(enl_est, GRILLA_DIR / "estaciones_enlaces.parquet")
    publicar_json({
        "schema": "airpollution.modelo-1km.grilla.v2", "contrato": CONTRATO,
        "enlace": "píxel válido más cercano; radio ampliado sólo si el píxel propio no trae datos",
        "meses_referencia_validez": list(MESES_REFERENCIA_VALIDEZ),
        "distancia_max_vecino_km": DISTANCIA_MAX_VECINO_KM,
        "pixeles_validos": {p: (None if v is None else int(len(v))) for p, v in validez.items()},
        "celdas_por_tipo_de_enlace": {p: enlaces[f"{p}_enlace"].astype(str).value_counts().to_dict()
                                      for p in DISTANCIA_MAX_VECINO_KM},
        "estaciones_por_tipo_de_enlace": {p: enl_est[f"{p}_enlace"].astype(str).value_counts().to_dict()
                                          for p in DISTANCIA_MAX_VECINO_KM},
        "resolucion_grados": RES, "alineacion": "ACAG V6GL03 (centros k·0,01 + 0,005)",
        "celdas": int(len(celdas)), "por_aoi": celdas["aoi_id"].value_counts().to_dict(),
        "por_origen": celdas["origen"].value_counts().to_dict(),
        "estaciones": int(len(enl_est)), "estaciones_sin_celda": int((enl_est["celda"] < 0).sum()),
        "distancia_max_km": DISTANCIA_MAX_KM, "codigo": hash_codigo(),
        "archivos": {"celdas": sha_c, "enlaces_productos": sha_e, "estaciones_enlaces": sha_s},
    }, GRILLA_DIR / "metadata.json")
    log.info("Publicado en %s", GRILLA_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
