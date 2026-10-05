#!/usr/bin/env python3
"""Covariables estáticas y anuales por celda de 0,01°.

* Uso de suelo ESA CCI 300 m → fracciones por celda y año (urbano, cultivo,
  bosque, matorral/pastizal, suelo desnudo, agua, nieve/hielo). Años sin
  raster usan el último disponible (2022) y lo declaran.
* Población: proyecciones censales comunales repartidas dasimétricamente por
  la fracción urbana de cada celda (más un piso rural), en hab/km².
* Elevación: NASADEM 30 m agregado a la celda (media, desviación, pendiente
  aproximada) cuando existen teselas; si no, la media comunal de
  ``topografia_comunal.csv`` con bandera ``elev_fuente``.
* Distancia a la costa: al píxel de agua ESA CCI más cercano cuyo centro no
  está en ninguna comuna (océano), en km.
* Vías: densidad OSM (km de vía por km²) total y de vías principales, cuando
  está ``data/osm/gis_osm_roads_free_1.shp``; si no, NaN con bandera.
* Distancia a la estación SINCA más cercana con cada contaminante.

Nada se interpola: cada celda recibe estadísticos de los píxeles nativos que
caen en ella.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comun_modelo import (  # noqa: E402
    CONT, CONTRATO, DATA, ESTATICAS_PATH, GRILLA_DIR, LULC_PATH, RES, SINCA_DERIVADO,
    cargar_celdas, hash_codigo, leer_estaciones, log, publicar_json, publicar_parquet,
    rellenar_por_vecino,
)

GRUPOS_CCI = {
    "urbano": [190],
    "cultivo": [10, 11, 12, 20, 30, 40],
    "bosque": [50, 60, 61, 62, 70, 71, 72, 80, 81, 82, 90, 100, 160, 170],
    "matorral_pastizal": [110, 120, 121, 122, 130, 140, 150, 151, 152, 153, 180],
    "desnudo": [200, 201, 202],
    "agua": [210],
    "nieve_hielo": [220],
}
LULC_DIR = DATA / "lulc" / "ESA_CCI_300m_native"
OSM_ROADS = DATA / "osm" / "gis_osm_roads_free_1.shp"
NASADEM_DIR = CONT / "Topografia" / "NASADEM_30m_native" / "tiles"
VIAS_PRINCIPALES = {"motorway", "motorway_link", "trunk", "trunk_link", "primary",
                    "primary_link", "secondary", "secondary_link"}


def clave_celda(lat, lon) -> np.ndarray:
    """Clave entera estable de la celda 0,01° que contiene (lat, lon)."""
    fila = np.floor(np.asarray(lat, float) / RES).astype("int64")
    col = np.floor(np.asarray(lon, float) / RES).astype("int64")
    return (fila + 20000) * 100000 + (col + 40000)


def _raster_bloques(path: Path, filas_bloque: int = 2000):
    """Itera (lat, lon, valor) de un GeoTIFF lat/lon regular por bloques de filas."""
    import rasterio
    from rasterio.windows import Window

    with rasterio.open(path) as src:
        tr = src.transform
        nodata = src.nodata
        for f0 in range(0, src.height, filas_bloque):
            nf = min(filas_bloque, src.height - f0)
            arr = src.read(1, window=Window(0, f0, src.width, nf))
            filas, cols = np.indices(arr.shape)
            lon = tr.c + (cols + 0.5) * tr.a
            lat = tr.f + (f0 + filas + 0.5) * tr.e
            ok = np.ones(arr.shape, dtype=bool) if nodata is None else arr != nodata
            yield lat[ok], lon[ok], arr[ok]


_GRUPOS = list(GRUPOS_CCI)
_CLASE_A_IDX = np.full(256, len(_GRUPOS), dtype="int64")  # 'otro' al final
for _g, _clases in GRUPOS_CCI.items():
    for _c in _clases:
        _CLASE_A_IDX[_c] = _GRUPOS.index(_g)


def lulc_fracciones(celdas: pd.DataFrame, anio: int) -> tuple[pd.DataFrame, int]:
    """Fracciones por grupo ESA CCI para el año (o el último disponible)."""
    anios = sorted(int(p.name) for p in LULC_DIR.glob("[12][0-9][0-9][0-9]") if p.is_dir())
    if not anios:
        raise SystemExit(f"No hay rasters ESA CCI en {LULC_DIR}")
    usado = max(a for a in anios if a <= anio) if anio >= anios[0] else anios[0]
    ng = len(_GRUPOS) + 1
    acumulado: dict[int, int] = {}
    for tif in sorted((LULC_DIR / str(usado)).glob("*.tif")):
        for lat, lon, val in _raster_bloques(tif):
            if not lat.size:
                continue
            clave = clave_celda(lat, lon)
            g = _CLASE_A_IDX[np.clip(val.astype("int64"), 0, 255)]
            llaves, conteos = np.unique(clave * ng + g, return_counts=True)
            for k, c in zip(llaves.tolist(), conteos.tolist()):
                acumulado[k] = acumulado.get(k, 0) + c
    llaves = np.fromiter(acumulado.keys(), dtype="int64", count=len(acumulado))
    conteos = np.fromiter(acumulado.values(), dtype="int64", count=len(acumulado))
    tabla = pd.DataFrame({"clave": llaves // ng, "g": llaves % ng, "n": conteos})
    piv = tabla.pivot_table(index="clave", columns="g", values="n", aggfunc="sum", fill_value=0)
    total = piv.sum(axis=1)
    out = celdas[["celda"]].copy()
    clave_c = clave_celda(celdas["lat"], celdas["lon"])
    pos = piv.index.get_indexer(clave_c)
    for gi, grupo in enumerate(_GRUPOS):
        col = piv[gi].to_numpy(dtype="float64") if gi in piv.columns else np.zeros(len(piv))
        frac = np.where(total.to_numpy() > 0, col / np.maximum(total.to_numpy(), 1), 0.0)
        valores = np.where(pos >= 0, frac[np.clip(pos, 0, None)], 0.0)
        out[f"lulc_{grupo}"] = valores.astype("float32")
    n_pix = np.where(pos >= 0, total.to_numpy()[np.clip(pos, 0, None)], 0)
    out["lulc_n_pixeles"] = n_pix.astype("int16")
    out["lulc_anio_raster"] = np.int16(usado)
    return out, usado


def poblacion_comunal_por_anio() -> pd.DataFrame:
    censo = pd.read_parquet(DATA / "censo_proyecciones_ano_edad_genero.parquet",
                            columns=["cut_comuna", "año", "población"])
    censo = censo.rename(columns={"cut_comuna": "cod_comuna", "año": "anio", "población": "poblacion"})
    return (censo.groupby(["cod_comuna", "anio"], as_index=False)["poblacion"].sum()
            .astype({"cod_comuna": "int32", "anio": "int16"}))


def poblacion_dasimetrica(celdas: pd.DataFrame, lulc: pd.DataFrame, anio: int) -> pd.Series:
    """hab/km² por celda: población comunal repartida por fracción urbana + piso rural."""
    pob = poblacion_comunal_por_anio()
    anios = sorted(pob["anio"].unique())
    usado = max(a for a in anios if a <= anio) if anio >= anios[0] else anios[0]
    pob = pob[pob["anio"] == usado].set_index("cod_comuna")["poblacion"]
    peso = lulc["lulc_urbano"].to_numpy(dtype="float64") + 0.02
    area_km2 = (RES * 111.32) * (RES * 111.32 * np.cos(np.radians(celdas["lat"].to_numpy())))
    df = pd.DataFrame({"cod": celdas["cod_comuna"].to_numpy(), "peso": peso, "area": area_km2})
    suma = df.groupby("cod")["peso"].transform("sum")
    pobl = df["cod"].map(pob).fillna(0.0).to_numpy()
    hab = np.where(suma > 0, pobl * df["peso"] / suma, 0.0)
    return pd.Series((hab / area_km2).astype("float32"), name="pob_dens")


def elevacion(celdas: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({"celda": celdas["celda"]})
    tiles = sorted(NASADEM_DIR.glob("*.tif")) if NASADEM_DIR.exists() else []
    if tiles:
        import rasterio

        clave_c = clave_celda(celdas["lat"], celdas["lon"])
        acum: dict[str, pd.Series] = {}
        for tif in tiles:
            with rasterio.open(tif) as src:
                arr = src.read(1).astype("float32")
                tr = src.transform
                nodata = src.nodata
            if nodata is not None:
                arr[arr == nodata] = np.nan
            filas, cols = np.indices(arr.shape)
            lat = tr.f + (filas + 0.5) * tr.e
            lon = tr.c + (cols + 0.5) * tr.a
            dz_y, dz_x = np.gradient(arr, abs(tr.e) * 111320.0, abs(tr.a) * 111320.0 * np.cos(np.radians(lat.mean())))
            pend = np.degrees(np.arctan(np.hypot(dz_x, dz_y)))
            df = pd.DataFrame({"clave": clave_celda(lat.ravel(), lon.ravel()), "z": arr.ravel(), "p": pend.ravel()}).dropna()
            g = df.groupby("clave").agg(z_sum=("z", "sum"), z2_sum=("z", lambda s: float(np.sum(s.to_numpy() ** 2))),
                                        p_sum=("p", "sum"), n=("z", "size"))
            for col in g.columns:
                acum[col] = acum[col].add(g[col], fill_value=0) if col in acum else g[col]
        tabla = pd.DataFrame(acum)
        media = tabla["z_sum"] / tabla["n"]
        sd = np.sqrt(np.clip(tabla["z2_sum"] / tabla["n"] - media ** 2, 0, None))
        pend = tabla["p_sum"] / tabla["n"]
        ref = pd.DataFrame({"elev_m": media, "elev_sd_m": sd, "pendiente_deg": pend})
        out = out.assign(clave=clave_c).merge(ref, left_on="clave", right_index=True, how="left").drop(columns="clave")
        out["elev_fuente"] = np.where(out["elev_m"].notna(), "nasadem_30m", "sin_dato")
    else:
        out["elev_m"] = np.nan
        out["elev_sd_m"] = np.nan
        out["pendiente_deg"] = np.nan
        out["elev_fuente"] = "sin_dato"
    topo = CONT / "Topografia" / "topografia_comunal.csv"
    if topo.exists():
        t = pd.read_csv(topo).set_index("cod_comuna")
        falta = out["elev_m"].isna()
        cod = celdas["cod_comuna"].to_numpy()
        out.loc[falta, "elev_m"] = pd.Series(cod).map(t["alt_media"]).to_numpy()[falta]
        out.loc[falta, "pendiente_deg"] = pd.Series(cod).map(t["pendiente"]).to_numpy()[falta]
        out.loc[falta & out["elev_m"].notna(), "elev_fuente"] = "comunal_topografia_csv"
    for c in ("elev_m", "pendiente_deg"):
        valores, relleno = rellenar_por_vecino(celdas["lat"], celdas["lon"], out[c].to_numpy(), max_km=30.0)
        out[c] = valores
        if c == "elev_m":
            out.loc[relleno, "elev_fuente"] = out.loc[relleno, "elev_fuente"].where(
                out.loc[relleno, "elev_fuente"] != "sin_dato", "vecino_mas_cercano")
    for c in ("elev_m", "elev_sd_m", "pendiente_deg"):
        out[c] = out[c].astype("float32")
    return out


def distancia_costa(celdas: pd.DataFrame, comunas) -> np.ndarray:
    """km al píxel de agua ESA CCI más cercano cuyo centro no está en comuna alguna."""
    import shapely
    from scipy.spatial import cKDTree
    from shapely.strtree import STRtree

    anios = sorted(int(p.name) for p in LULC_DIR.glob("[12][0-9][0-9][0-9]") if p.is_dir())
    puntos = []
    arbol_com = STRtree(comunas.geometry.to_numpy())
    for tif in sorted((LULC_DIR / str(anios[-1])).glob("*.tif")):
        for lat, lon, val in _raster_bloques(tif):
            agua = val == 210
            lat, lon = lat[agua][::3], lon[agua][::3]
            if not lat.size:
                continue
            pts = shapely.points(lon, lat)
            idx, _ = arbol_com.query(pts, predicate="intersects")
            interior = np.zeros(len(pts), dtype=bool)
            interior[np.unique(idx)] = True
            puntos.append(np.c_[lon[~interior], lat[~interior]])
    if not puntos:
        return np.full(len(celdas), np.nan, dtype="float32")
    oc = np.concatenate(puntos)
    from construir_grilla import _xyz
    arbol = cKDTree(_xyz(oc[:, 1], oc[:, 0]))
    d, _ = arbol.query(_xyz(celdas["lat"], celdas["lon"]))
    return (2.0 * 6371.0 * np.arcsin(np.clip(d / 2.0, 0, 1))).astype("float32")


def densidad_vial(celdas: pd.DataFrame, paso_m: float = 100.0) -> pd.DataFrame | None:
    """km de vía por km² (total y principales) muestreando cada vía cada 100 m."""
    if not OSM_ROADS.exists():
        return None
    import pyogrio
    import shapely

    clave_c = clave_celda(celdas["lat"], celdas["lon"])
    area_km2 = (RES * 111.32) * (RES * 111.32 * np.cos(np.radians(celdas["lat"].to_numpy())))
    conteo_total = pd.Series(dtype="float64")
    conteo_princ = pd.Series(dtype="float64")
    info = pyogrio.read_info(OSM_ROADS)
    n = int(info["features"])
    lote = 100_000
    for ini in range(0, n, lote):
        gdf = pyogrio.read_dataframe(OSM_ROADS, columns=["fclass"], skip_features=ini, max_features=lote)
        if gdf.empty:
            break
        geoms = gdf.geometry.to_numpy()
        # Densifica en grados (~100 m ≈ 0,0009°) y toma los vértices como muestra de longitud.
        dens = shapely.segmentize(geoms, paso_m / 111_320.0)
        coords, idx = shapely.get_coordinates(dens, return_index=True)
        princ = gdf["fclass"].isin(VIAS_PRINCIPALES).to_numpy()[idx]
        clave = clave_celda(coords[:, 1], coords[:, 0])
        s = pd.Series(clave).value_counts()
        conteo_total = conteo_total.add(s, fill_value=0)
        sp = pd.Series(clave[princ]).value_counts()
        conteo_princ = conteo_princ.add(sp, fill_value=0)
    km_total = pd.Series(clave_c).map(conteo_total).fillna(0).to_numpy() * paso_m / 1000.0
    km_princ = pd.Series(clave_c).map(conteo_princ).fillna(0).to_numpy() * paso_m / 1000.0
    return pd.DataFrame({"vias_km_km2": (km_total / area_km2).astype("float32"),
                         "vias_princ_km_km2": (km_princ / area_km2).astype("float32")})


def distancia_estaciones(celdas: pd.DataFrame) -> pd.DataFrame:
    from construir_grilla import vecino_mas_cercano

    est = leer_estaciones()
    out = pd.DataFrame(index=celdas.index)
    for pol in ("pm25", "no2"):
        con = sorted({p.parent.name.split("=", 1)[1] for p in
                      SINCA_DERIVADO.glob(f"estacion=*/contaminante={pol}")})
        sub = est[est["estacion"].isin(con)] if con else est
        if sub.empty:
            out[f"dist_est_{pol}_km"] = np.nan
            continue
        _, d = vecino_mas_cercano(celdas["lat"], celdas["lon"], sub["lat"].to_numpy(), sub["lon"].to_numpy())
        out[f"dist_est_{pol}_km"] = d.astype("float32")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--anios", default="2017-2026", help="rango de años para LULC/población, AAAA-AAAA")
    ap.add_argument("--sin-vias", action="store_true", help="omite la densidad vial OSM")
    ap.add_argument("--forzar", action="store_true")
    args = ap.parse_args(argv)
    a0, a1 = (int(x) for x in args.anios.split("-"))
    if ESTATICAS_PATH.exists() and LULC_PATH.exists() and not args.forzar:
        log.info("Estáticas ya publicadas en %s (usa --forzar)", GRILLA_DIR)
        return 0
    celdas = cargar_celdas()
    from construir_grilla import cargar_comunas
    comunas = cargar_comunas()

    log.info("LULC y población por año %d–%d", a0, a1)
    anuales = []
    rasters_usados = {}
    for anio in range(a0, a1 + 1):
        frac, usado = lulc_fracciones(celdas, anio)
        rasters_usados[anio] = usado
        frac["pob_dens"] = poblacion_dasimetrica(celdas, frac, anio)
        frac.insert(1, "anio", np.int16(anio))
        anuales.append(frac)
    lulc = pd.concat(anuales, ignore_index=True)
    sha_l = publicar_parquet(lulc, LULC_PATH)

    log.info("Elevación")
    est = elevacion(celdas)
    log.info("Distancia a la costa")
    est["dist_costa_km"] = distancia_costa(celdas, comunas)
    vias = None if args.sin_vias else densidad_vial(celdas)
    if vias is None:
        est["vias_km_km2"] = np.nan
        est["vias_princ_km_km2"] = np.nan
        est["vias_fuente"] = "sin_dato"
        log.warning("Sin densidad vial: %s ausente o --sin-vias", OSM_ROADS)
    else:
        est = pd.concat([est, vias], axis=1)
        est["vias_fuente"] = "osm_gis_osm_roads_free_1"
    est = pd.concat([est, distancia_estaciones(celdas)], axis=1)
    est["lat"] = celdas["lat"].to_numpy()
    est["lon"] = celdas["lon"].to_numpy()
    est["macrozona_cod"] = celdas["macrozona_cod"].to_numpy()
    est["cod_comuna"] = celdas["cod_comuna"].to_numpy()
    sha_e = publicar_parquet(est, ESTATICAS_PATH)
    publicar_json({
        "schema": "airpollution.modelo-1km.estaticas.v1", "contrato": CONTRATO,
        "celdas": int(len(celdas)), "anios": [a0, a1], "lulc_raster_por_anio": rasters_usados,
        "grupos_cci": GRUPOS_CCI, "elev_fuente": est["elev_fuente"].value_counts().to_dict(),
        "vias": est["vias_fuente"].iloc[0], "codigo": hash_codigo(),
        "archivos": {"estaticas": sha_e, "estaticas_lulc": sha_l},
    }, GRILLA_DIR / "estaticas_metadata.json")
    log.info("Publicado %s y %s", ESTATICAS_PATH.name, LULC_PATH.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
