#!/usr/bin/env python3
"""Descarga NASADEM HGT v001 a 1 arc-second (~30 m) para Chile.

NASADEM es un modelo de superficie estatico derivado principalmente de SRTM
(adquisicion de febrero de 2000). Por eso no existe una frecuencia horaria:
la maxima resolucion temporal nativa es una sola superficie. El programa:

1. deriva las teselas de 1 grado que realmente intersectan las comunas;
2. localiza solo esas teselas mediante NASA Earthdata/CMR;
3. conserva la elevacion ``.hgt`` a su grilla nativa, sin remuestreo;
4. aplica una mascara de huellas de Chile, separada en cinco territorios;
5. relee y compara cada salida antes de borrar ZIP/HGT temporales; y
6. registra hashes, version, mascara, runtime y validaciones en JSONL.

No reemplaza automaticamente ``topografia_comunal.csv``: ese resumen pequeno
se mantiene hasta que el flujo analitico cambie a los pixeles nativos.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

import numpy as np

from _chile_aoi import AOI, seleccionar
from _common import CONTAMINANTES, DATA, ensure_dir
from _env_earthdata import login as earthdata_login
from _manifiesto_satelital import (
    Manifiesto,
    sha256,
    sha256_conjunto_shapefile,
    url_publica,
)


PRODUCTO = "NASADEM_HGT"
VERSION = "001"
RESOLUCION_GRADOS = 1.0 / 3600.0
CMR_URL = "https://cmr.earthdata.nasa.gov/search/collections.umm_json"
PRODUCT_URL = "https://lpdaac.usgs.gov/products/nasademhgtv001/"
RE_TILE = re.compile(r"(?P<tile>[ns]\d{2}[ew]\d{3})", re.IGNORECASE)


@dataclass
class Reemplazo:
    path: Path
    aoi: AOI
    pixeles: int
    conteos: Counter
    bbox: tuple[float, float, float, float]


def _geometrias(comunas_path: Path):
    import geopandas as gpd

    g = gpd.read_file(comunas_path).to_crs("EPSG:4326")
    if "cod_comuna" not in g:
        raise ValueError(f"{comunas_path}: falta cod_comuna")
    try:
        g["geometry"] = g.geometry.make_valid()
    except AttributeError:
        from shapely.validation import make_valid
        g["geometry"] = g.geometry.map(make_valid)
    g["cod_comuna"] = g.cod_comuna.astype("int32")
    return g


def _tile_id(lon_oeste: int, lat_sur: int) -> str:
    ns = "n" if lat_sur >= 0 else "s"
    ew = "e" if lon_oeste >= 0 else "w"
    return f"{ns}{abs(lat_sur):02d}{ew}{abs(lon_oeste):03d}"


def _tiles_requeridos(comunas, aois: tuple[AOI, ...]) -> dict[str, set[str]]:
    """Teselas cuya superficie tiene interseccion de area positiva con Chile."""
    from shapely.geometry import box

    asignacion: dict[str, set[str]] = defaultdict(set)
    for aoi in aois:
        caja = box(*aoi.bbox)
        piezas = [geom.intersection(caja) for geom in comunas.geometry
                  if geom is not None and not geom.is_empty and geom.intersects(caja)]
        piezas = [x for x in piezas if not x.is_empty]
        if not piezas:
            raise ValueError(f"AOI {aoi.id} no cruza la mascara comunal")
        minx = min(x.bounds[0] for x in piezas)
        miny = min(x.bounds[1] for x in piezas)
        maxx = max(x.bounds[2] for x in piezas)
        maxy = max(x.bounds[3] for x in piezas)
        for lat in range(math.floor(miny), math.ceil(maxy)):
            for lon in range(math.floor(minx), math.ceil(maxx)):
                celda = box(lon, lat, lon + 1, lat + 1)
                if any(geom.intersection(celda).area > 0 for geom in piezas):
                    asignacion[_tile_id(lon, lat)].add(aoi.id)
    return dict(asignacion)


def _granule_id(granulo) -> str:
    try:
        return str(granulo["umm"]["GranuleUR"])
    except Exception:  # noqa: BLE001
        return Path(_url_granulo(granulo)).stem


def _url_granulo(granulo) -> str:
    enlaces = list(granulo.data_links())
    if not enlaces:
        raise ValueError(f"granulo sin enlace: {granulo}")
    return str(enlaces[0])


def _tile_granulo(granulo) -> str:
    m = RE_TILE.search(_granule_id(granulo)) or RE_TILE.search(_url_granulo(granulo))
    if not m:
        raise ValueError(f"no se reconoce tesela NASADEM: {_granule_id(granulo)}")
    return m.group("tile").lower()


def _buscar(earthaccess, aois: tuple[AOI, ...], requeridos: set[str]):
    encontrados = {}
    for aoi in aois:
        resultados = earthaccess.search_data(
            short_name=PRODUCTO,
            version=VERSION,
            bounding_box=aoi.bbox,
            count=2000,
        )
        for g in resultados:
            tile = _tile_granulo(g)
            if tile in requeridos:
                encontrados.setdefault(tile, g)
    return encontrados


def _estimar_volumen(comunas) -> dict[str, float]:
    """Estimacion por area/celda; no supone compresion milagrosa."""
    areas = comunas.to_crs("EPSG:6933").area.to_numpy(dtype="float64")
    lat = comunas.geometry.representative_point().y.to_numpy(dtype="float64")
    area_celda = (111_320.0 / 3600.0) ** 2 * np.cos(np.deg2rad(lat))
    pixeles = float(np.sum(areas / area_celda))
    return {
        "area_chile_km2": float(areas.sum() / 1_000_000.0),
        "pixeles_chile_estimados": pixeles,
        "elevacion_int16_sin_compresion_GB": pixeles * 2 / 1_000_000_000,
        # DEFLATE de un DEM montanoso varia; rango deliberadamente conservador.
        "salida_final_estimada_GB_min": pixeles * 2 / 1_000_000_000 * 0.45,
        "salida_final_estimada_GB_max": pixeles * 2 / 1_000_000_000 * 1.10,
    }


def _descargar(earthaccess, granulo, carpeta: Path) -> Path:
    for intento in range(1, 5):
        try:
            paths = earthaccess.download([granulo], local_path=str(carpeta)) or []
            archivos = [Path(x).resolve() for x in paths if Path(x).is_file()]
            if len(archivos) != 1:
                raise RuntimeError(f"Earthdata devolvio {len(archivos)} archivos")
            raiz = carpeta.resolve()
            if raiz != archivos[0].parent and raiz not in archivos[0].parents:
                raise RuntimeError("Earthdata escribio fuera de la carpeta temporal")
            return archivos[0]
        except Exception:  # noqa: BLE001
            if intento == 4:
                raise
    raise AssertionError("inalcanzable")


def _extraer_hgt(raw: Path, carpeta: Path) -> Path:
    if raw.suffix.lower() == ".hgt":
        return raw
    if not zipfile.is_zipfile(raw):
        raise ValueError(f"{raw}: no es ZIP ni HGT")
    with zipfile.ZipFile(raw) as zf:
        miembros = [x for x in zf.infolist()
                    if not x.is_dir() and x.filename.lower().endswith(".hgt")]
        if len(miembros) != 1:
            raise ValueError(f"{raw}: se esperaba un HGT, hay {len(miembros)}")
        salida = carpeta / Path(miembros[0].filename).name
        with zf.open(miembros[0]) as origen, salida.open("wb") as destino:
            shutil.copyfileobj(origen, destino, length=8 * 1024 * 1024)
    return salida


def _recortar(hgt: Path, comunas, aoi: AOI):
    import rasterio
    from affine import Affine
    from rasterio.features import rasterize

    with rasterio.open(hgt) as src:
        if src.count != 1 or src.crs is None or src.crs.to_epsg() != 4326:
            raise ValueError(f"{hgt}: HGT sin banda unica EPSG:4326")
        if not (np.isclose(abs(src.transform.a), RESOLUCION_GRADOS, atol=1e-10) and
                np.isclose(abs(src.transform.e), RESOLUCION_GRADOS, atol=1e-10)):
            raise ValueError(f"{hgt}: resolucion no nativa {src.res}")
        datos = src.read(1).astype("int16", copy=False)
        transform = src.transform
        nodata = int(src.nodata) if src.nodata is not None else -32768
        tags = {str(k): str(v) for k, v in src.tags().items()}
    formas = [(geom, int(cod)) for geom, cod in
              zip(comunas.geometry, comunas.cod_comuna, strict=False)
              if geom is not None and not geom.is_empty and int(cod) >= 0]
    formas.sort(key=lambda x: x[1] == 0)
    toca = rasterize(
        [(geom, 1) for geom, _ in formas], out_shape=datos.shape,
        transform=transform, fill=0, dtype="uint8", all_touched=True,
    ).astype(bool)
    # Limita cada tesela al territorio asignado; evita copiar otro componente
    # remoto que casualmente caiga en el mismo grado.
    from shapely.geometry import box
    caja_aoi = box(*aoi.bbox)
    toca_aoi = rasterize(
        [(caja_aoi, 1)], out_shape=datos.shape, transform=transform,
        fill=0, dtype="uint8", all_touched=True,
    ).astype(bool)
    toca &= toca_aoi
    if not toca.any():
        raise ValueError(f"{hgt}: no toca {aoi.id}")
    codigos = rasterize(
        formas, out_shape=datos.shape, transform=transform,
        fill=-1, dtype="int32", all_touched=False,
    )
    filas, columnas = np.where(toca)
    r0, r1 = int(filas.min()), int(filas.max()) + 1
    c0, c1 = int(columnas.min()), int(columnas.max()) + 1
    datos = datos[r0:r1, c0:c1].copy()
    toca = toca[r0:r1, c0:c1]
    codigos = codigos[r0:r1, c0:c1]
    datos[~toca] = nodata
    conteos = Counter(int(x) for x in codigos[toca & (codigos >= 0)])
    return datos, toca, conteos, transform * Affine.translation(c0, r0), nodata, tags


def _escribir(
    path: Path,
    datos: np.ndarray,
    toca: np.ndarray,
    transform,
    nodata: int,
    tags: dict[str, str],
    *,
    tile: str,
    aoi: AOI,
    source_name: str,
    source_sha256: str,
    mask_sha256: str,
) -> None:
    import rasterio

    path.unlink(missing_ok=True)
    profile = {
        "driver": "GTiff", "width": datos.shape[1], "height": datos.shape[0],
        "count": 1, "dtype": "int16", "crs": "EPSG:4326",
        "transform": transform, "nodata": nodata, "compress": "deflate",
        "zlevel": 9, "predictor": 2, "tiled": True,
        "blockxsize": 256, "blockysize": 256, "BIGTIFF": "IF_SAFER",
    }
    tags = dict(tags)
    tags.update({
        "producto": PRODUCTO, "version": VERSION, "tile_id": tile,
        "aoi_id": aoi.id, "territorio": aoi.territorio,
        "spatial_resolution_native": "1 arc-second (~30 m)",
        "temporal_resolution_native": "static; SRTM acquisition February 2000",
        "resampling": "none", "variable": "elevation",
        "vertical_units": "meters", "source_filename": source_name,
        "source_sha256": source_sha256,
        "administrative_mask": "cell footprint touches Chile; Antarctica excluded",
        "administrative_mask_sha256": mask_sha256,
        "raw_deleted_after_validation": "true",
    })
    with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True):
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(datos, 1)
            dst.write_mask(toca.astype("uint8") * 255)
            dst.update_tags(**tags)
            dst.update_tags(1, long_name="surface elevation", units="m")


def _validar(path: Path, *, tile: str, aoi: AOI,
             datos=None, toca=None) -> tuple[int, tuple[float, float, float, float]]:
    import rasterio

    with rasterio.open(path) as ds:
        if ds.count != 1 or ds.dtypes[0] != "int16" or ds.crs.to_epsg() != 4326:
            raise ValueError(f"{path}: perfil NASADEM invalido")
        if not (np.isclose(abs(ds.transform.a), RESOLUCION_GRADOS, atol=1e-10) and
                np.isclose(abs(ds.transform.e), RESOLUCION_GRADOS, atol=1e-10)):
            raise ValueError(f"{path}: resolucion NASADEM alterada")
        if ds.tags().get("tile_id") != tile or ds.tags().get("aoi_id") != aoi.id:
            raise ValueError(f"{path}: identificadores inconsistentes")
        actual = ds.read(1)
        mask = ds.dataset_mask() > 0
        if not mask.any() or np.any(actual[~mask] != ds.nodata):
            raise ValueError(f"{path}: mascara administrativa invalida")
        if datos is not None and not np.array_equal(actual, datos):
            raise ValueError(f"{path}: elevaciones no coinciden pixel a pixel")
        if toca is not None and not np.array_equal(mask, toca):
            raise ValueError(f"{path}: huellas no coinciden pixel a pixel")
        for _, window in ds.block_windows(1):
            ds.read(1, window=window)
        b = ds.bounds
        return int(mask.sum()), (float(b.left), float(b.bottom),
                                 float(b.right), float(b.top))


def _conteos(path: Path, comunas) -> Counter:
    import rasterio
    from rasterio.features import rasterize

    formas = [(geom, int(cod)) for geom, cod in
              zip(comunas.geometry, comunas.cod_comuna, strict=False)
              if geom is not None and not geom.is_empty and int(cod) >= 0]
    formas.sort(key=lambda x: x[1] == 0)
    with rasterio.open(path) as ds:
        mask = ds.dataset_mask() > 0
        cod = rasterize(formas, out_shape=(ds.height, ds.width),
                        transform=ds.transform, fill=-1, dtype="int32")
    return Counter(int(x) for x in cod[mask & (cod >= 0)])


def _salida(root: Path, tile: str, aoi: AOI) -> Path:
    return root / "tiles" / f"NASADEM_HGT_{tile}_{aoi.id}_30m.tif"


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--aoi", default="todos")
    p.add_argument("--comunas", type=Path, default=DATA / "comunas.shp")
    p.add_argument("--salida", type=Path,
                   default=CONTAMINANTES / "Topografia" / "NASADEM_30m_native")
    p.add_argument("--min-gb-libres", type=float, default=100.0)
    p.add_argument("--dry-run", action="store_true")
    return p


def main() -> int:
    args = _parser().parse_args()
    if not args.comunas.exists():
        raise SystemExit(f"no existe {args.comunas}")
    comunas = _geometrias(args.comunas)
    aois = seleccionar(args.aoi, args.comunas)
    asignacion = _tiles_requeridos(comunas, aois)
    import earthaccess
    encontrados = _buscar(earthaccess, aois, set(asignacion))
    faltantes = sorted(set(asignacion) - set(encontrados))
    estimacion = _estimar_volumen(comunas)
    resumen = {
        "producto": f"{PRODUCTO}.v{VERSION}",
        "resolucion_espacial_nativa": "1 arc-second (~30 m)",
        "resolucion_temporal_nativa": "static; SRTM acquisition February 2000",
        "teselas_requeridas": len(asignacion),
        "teselas_encontradas_cmr": len(encontrados),
        "teselas_faltantes": faltantes,
        "aois": [a.id for a in aois],
        "salida": str(args.salida),
        "estimacion": estimacion,
        "nota": "topografia_comunal.csv se conserva hasta migrar consumidores",
    }
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    if faltantes:
        raise SystemExit("CMR no encontro todas las teselas administrativas")
    if args.dry_run:
        for tile in sorted(asignacion):
            g = encontrados[tile]
            print(json.dumps({
                "tile": tile,
                "aoi": sorted(asignacion[tile]),
                "granule_id": _granule_id(g),
                "url": url_publica(_url_granulo(g)),
                "salidas": [str(_salida(args.salida, tile, a)) for a in aois
                            if a.id in asignacion[tile]],
            }, ensure_ascii=False))
        return 0
    libres = shutil.disk_usage(args.salida.parent).free / 1_000_000_000
    if libres < args.min_gb_libres:
        raise SystemExit(
            f"quedan {libres:.1f} GB; se exige reserva de {args.min_gb_libres:.1f} GB"
        )
    earthdata_login()
    root = ensure_dir(args.salida)
    temporal = ensure_dir(root / ".tmp")
    mask_hash = sha256_conjunto_shapefile(args.comunas)
    manifiesto = Manifiesto(root / "manifiestos", PRODUCTO, {
        **resumen, "comunas": str(args.comunas), "comunas_sha256": mask_hash,
        "cmr_url": CMR_URL, "product_url": PRODUCT_URL,
    })
    reemplazos: list[Reemplazo] = []
    try:
        for tile in sorted(asignacion):
            aoi_tile = [a for a in aois if a.id in asignacion[tile]]
            existentes = [_salida(root, tile, a) for a in aoi_tile]
            if all(x.exists() for x in existentes):
                for path, aoi in zip(existentes, aoi_tile, strict=True):
                    pix, bbox = _validar(path, tile=tile, aoi=aoi)
                    reemplazos.append(Reemplazo(path, aoi, pix,
                                                _conteos(path, comunas), bbox))
                continue
            libres = shutil.disk_usage(root).free / 1_000_000_000
            if libres < args.min_gb_libres:
                raise OSError(f"reserva de disco alcanzada: {libres:.1f} GB")
            carpeta = temporal / tile
            carpeta.mkdir(parents=True, exist_ok=True)
            raw = _descargar(earthaccess, encontrados[tile], carpeta)
            raw_hash = sha256(raw)
            hgt = _extraer_hgt(raw, carpeta)
            hgt_hash = sha256(hgt)
            salidas_tile: list[Reemplazo] = []
            for aoi in aoi_tile:
                datos, toca, conteos, transform, nodata, tags = _recortar(
                    hgt, comunas, aoi)
                salida = _salida(root, tile, aoi)
                salida.parent.mkdir(parents=True, exist_ok=True)
                tmp = salida.with_suffix(salida.suffix + ".part")
                _escribir(tmp, datos, toca, transform, nodata, tags,
                          tile=tile, aoi=aoi, source_name=hgt.name,
                          source_sha256=hgt_hash, mask_sha256=mask_hash)
                pix, bbox = _validar(tmp, tile=tile, aoi=aoi,
                                     datos=datos, toca=toca)
                os.replace(tmp, salida)
                _validar(salida, tile=tile, aoi=aoi, datos=datos, toca=toca)
                salidas_tile.append(Reemplazo(salida, aoi, pix, conteos, bbox))
            # Solo ahora se retira todo el paquete fuente de la tesela.
            shutil.rmtree(carpeta)
            for s in salidas_tile:
                manifiesto.archivo(
                    salida=s.path, version=VERSION,
                    granule_id=_granule_id(encontrados[tile]),
                    url=_url_granulo(encontrados[tile]), aoi_id=s.aoi.id,
                    territorio=s.aoi.territorio, bbox=s.bbox,
                    resolucion="1 arc-second (~30 m), native, no resampling",
                    tiempo_nativo="static; SRTM acquisition February 2000",
                    qa="source HGT nodata + internal administrative mask",
                    pixeles=s.pixeles, mascara=str(args.comunas),
                    validacion="reopened; blocks readable; exact pixel/mask comparison",
                    crudo_eliminado=True, crudo=raw,
                    checksum_fuente=hgt_hash,
                    variables_conservadas=["elevation"],
                )
            manifiesto.registrar({
                "evento": "tesela_validada", "tile_id": tile,
                "zip_sha256": raw_hash, "hgt_sha256": hgt_hash,
                "crudo_eliminado": True,
            })
            reemplazos.extend(salidas_tile)
        total = Counter()
        for r in reemplazos:
            total.update(r.conteos)
        codigos = {int(x) for x in comunas.cod_comuna}
        faltan_comunas = sorted(codigos - set(total))
        menos_dos = sorted((c, total[c]) for c in codigos if total[c] < 2)
        if faltan_comunas or menos_dos:
            raise ValueError(f"cobertura incompleta: {faltan_comunas}; <2={menos_dos}")
        manifiesto.terminar(
            estado="completo", teselas=len(asignacion),
            pixeles_huella_chile=sum(x.pixeles for x in reemplazos),
            unidades_administrativas=len(codigos), temporales_restantes=0,
        )
    except BaseException as exc:
        manifiesto.terminar(estado="error", error=repr(exc))
        raise
    finally:
        if temporal.exists():
            for part in temporal.rglob("*.part"):
                part.unlink(missing_ok=True)
            # Directorios vacios de intentos exitosos o fallidos.
            for carpeta in sorted(temporal.glob("*"), reverse=True):
                if carpeta.is_dir():
                    shutil.rmtree(carpeta)
            try:
                temporal.rmdir()
            except OSError:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
