#!/usr/bin/env python3
"""Descarga y recorta ESA CCI/C3S Land Cover a Chile administrativo.

Contrato de salida
------------------
* Se conserva ``lccs_class`` a su malla nativa de 1/360 grado (~300 m),
  sin remuestreo ni promedio comunal.
* La frecuencia nativa es anual. No se inventan observaciones mensuales,
  diarias ni horarias para una variable que cambia lentamente.
* Continente, Juan Fernandez, Desventuradas, Rapa Nui y Sala y Gomez se
  publican por separado para no almacenar corredores oceanicos.
* Cada GeoTIFF tiene una mascara interna de la geometria administrativa;
  las celdas cuya huella toca Chile se conservan y el resto queda nodata.
* El archivo fuente se elimina solo despues de releer, validar y comparar
  pixel a pixel todas las salidas que lo reemplazan.

El modo ``auto`` reutiliza primero los antiguos TIFF rectangulares, si
existen. Cuando no existen, obtiene el producto oficial desde el Climate
Data Store. Asi, el mismo programa sirve para la migracion local y para una
reproduccion limpia desde cero.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import urllib.request
import zipfile
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from _chile_aoi import AOI, seleccionar
from _common import DATA, ensure_dir, retry
from _manifiesto_satelital import (
    Manifiesto,
    sha256,
    sha256_conjunto_shapefile,
)


PRODUCTO = "ESA_CCI_C3S_LC_300M"
DATASET_ID = "satellite-land-cover"
DATASET_URL = "https://cds.climate.copernicus.eu/datasets/satellite-land-cover"
CATALOG_URL = (
    "https://cds.climate.copernicus.eu/api/catalogue/v1/collections/"
    f"{DATASET_ID}"
)
RESOLUCION_GRADOS = 1.0 / 360.0
ANIOS_FALLBACK = {
    **{str(y): "v2_0_7cds" for y in range(1992, 2016)},
    **{str(y): "v2_1_1" for y in range(2016, 2023)},
}


@dataclass
class RasterFuente:
    datos: np.ndarray
    transform: object
    crs: object
    tags: dict[str, str]
    band_tags: dict[str, str]
    nombre: str


@dataclass
class SalidaValidada:
    path: Path
    aoi: AOI
    pixeles: int
    conteo_comunas: Counter
    bbox: tuple[float, float, float, float]


def _anio(texto: str) -> int:
    try:
        return int(str(texto).strip()[:4])
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(f"fecha/ano invalido: {texto!r}") from exc


def _version_legible(version: str) -> str:
    return version.removeprefix("v").replace("_", ".")


def _sha256_bytes(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


@retry(n=4, base=2.0)
def catalogo_disponible() -> tuple[dict[str, str], dict[str, object]]:
    """Lee anos/versiones oficiales, con fallback explicito y auditable."""
    with urllib.request.urlopen(CATALOG_URL, timeout=60) as respuesta:
        catalogo_bytes = respuesta.read()
    catalogo = json.loads(catalogo_bytes)
    form_url = next(
        enlace["href"] for enlace in catalogo.get("links", [])
        if enlace.get("rel") == "form"
    )
    constraints_url = next(
        enlace["href"] for enlace in catalogo.get("links", [])
        if enlace.get("rel") == "constraints"
    )
    with urllib.request.urlopen(form_url, timeout=60) as respuesta:
        form_bytes = respuesta.read()
    with urllib.request.urlopen(constraints_url, timeout=60) as respuesta:
        constraints_bytes = respuesta.read()
    restricciones = json.loads(constraints_bytes)
    por_anio: dict[str, str] = {}
    for grupo in restricciones:
        versiones = grupo.get("version", [])
        if len(versiones) != 1:
            raise ValueError(f"restriccion CDS ambigua: {grupo}")
        for anio in grupo.get("year", []):
            por_anio[str(anio)] = str(versiones[0])
    if not por_anio:
        raise ValueError("el catalogo CDS no publico ningun ano")
    return por_anio, {
        "catalogo_url": CATALOG_URL,
        "catalogo_sha256": _sha256_bytes(catalogo_bytes),
        "form_url": form_url,
        "form_sha256": _sha256_bytes(form_bytes),
        "constraints_url": constraints_url,
        "constraints_sha256": _sha256_bytes(constraints_bytes),
        "intervalo_catalogo": catalogo.get("extent", {}).get("temporal"),
    }


def catalogo_con_fallback() -> tuple[dict[str, str], dict[str, object]]:
    try:
        return catalogo_disponible()
    except Exception as exc:  # noqa: BLE001 - fallback debe funcionar sin red
        print(
            f"ADVERTENCIA: no se pudo consultar el catalogo CDS ({exc}); "
            "se usa el inventario 1992-2022 incorporado en el script.",
            file=sys.stderr,
        )
        return dict(ANIOS_FALLBACK), {
            "catalogo_url": CATALOG_URL,
            "fallback": True,
            "motivo": repr(exc),
        }


def _geometrias_validas(comunas_path: Path):
    import geopandas as gpd

    comunas = gpd.read_file(comunas_path).to_crs("EPSG:4326")
    if "cod_comuna" not in comunas:
        raise ValueError(f"{comunas_path}: falta cod_comuna")
    try:
        comunas["geometry"] = comunas.geometry.make_valid()
    except AttributeError:
        from shapely.validation import make_valid
        comunas["geometry"] = comunas.geometry.map(make_valid)
    comunas["cod_comuna"] = comunas.cod_comuna.astype("int32")
    if len(comunas) != comunas.cod_comuna.nunique():
        raise ValueError("la mascara administrativa repite cod_comuna")
    return comunas


def _window_aoi(dataset, aoi: AOI):
    from rasterio.windows import Window, from_bounds

    ventana = from_bounds(*aoi.bbox, transform=dataset.transform)
    ventana = ventana.round_offsets().round_lengths()
    completa = Window(0, 0, dataset.width, dataset.height)
    try:
        return ventana.intersection(completa)
    except Exception as exc:  # rasterio cambia el tipo concreto de excepcion
        raise ValueError(f"{dataset.name}: no cruza AOI {aoi.id}") from exc


def _leer_tiff_local(path: Path, aoi: AOI) -> RasterFuente:
    import rasterio

    with rasterio.open(path) as src:
        if src.count != 1:
            raise ValueError(f"{path}: se esperaba una banda lccs_class")
        if src.crs is None or src.crs.to_epsg() != 4326:
            raise ValueError(f"{path}: CRS no es EPSG:4326")
        rx, ry = abs(src.transform.a), abs(src.transform.e)
        if not (np.isclose(rx, RESOLUCION_GRADOS, atol=1e-12) and
                np.isclose(ry, RESOLUCION_GRADOS, atol=1e-12)):
            raise ValueError(f"{path}: resolucion no nativa {rx} x {ry}")
        window = _window_aoi(src, aoi)
        datos = src.read(1, window=window)
        return RasterFuente(
            datos=datos,
            transform=src.window_transform(window),
            crs=src.crs,
            tags={str(k): str(v) for k, v in src.tags().items()},
            band_tags={str(k): str(v) for k, v in src.tags(1).items()},
            nombre=path.name,
        )


def _nombre_coord(dataset, candidatos: tuple[str, ...]) -> str:
    minusculas = {str(nombre).lower(): str(nombre) for nombre in dataset.coords}
    for candidato in candidatos:
        if candidato in minusculas:
            return minusculas[candidato]
    for nombre in dataset.dims:
        if str(nombre).lower() in candidatos:
            return str(nombre)
    raise ValueError(f"coordenada ausente; se esperaba una de {candidatos}")


def _leer_netcdf(path: Path) -> RasterFuente:
    import rasterio
    import xarray as xr
    from affine import Affine

    with xr.open_dataset(path, decode_cf=False, mask_and_scale=False) as ds:
        if "lccs_class" not in ds:
            raise ValueError(f"{path}: falta variable lccs_class")
        lat_name = _nombre_coord(ds, ("lat", "latitude"))
        lon_name = _nombre_coord(ds, ("lon", "longitude"))
        lat = np.asarray(ds[lat_name].values, dtype="float64")
        lon = np.asarray(ds[lon_name].values, dtype="float64")
        if lat.ndim != 1 or lon.ndim != 1 or len(lat) < 1 or len(lon) < 1:
            raise ValueError(f"{path}: coordenadas espaciales invalidas")
        # El CDS puede expresar el hemisferio occidental en 0..360.
        lon = np.where(lon > 180.0, lon - 360.0, lon)
        da = ds["lccs_class"]
        otros = [d for d in da.dims if d not in (lat_name, lon_name)]
        for dim in otros:
            if da.sizes[dim] != 1:
                raise ValueError(f"{path}: dimension no espacial {dim} no unitaria")
            da = da.isel({dim: 0}, drop=True)
        datos = np.asarray(da.transpose(lat_name, lon_name).values)
        if datos.ndim != 2:
            raise ValueError(f"{path}: lccs_class no es bidimensional")
        if np.issubdtype(datos.dtype, np.floating):
            datos = np.where(np.isfinite(datos), datos, 0)
        datos = datos.astype("uint8", copy=False)
        if len(lon) > 1:
            dx = float(np.median(np.diff(lon)))
        else:
            dx = RESOLUCION_GRADOS
        if len(lat) > 1:
            dy = float(np.median(np.diff(lat)))
        else:
            dy = -RESOLUCION_GRADOS
        if not (np.isclose(abs(dx), RESOLUCION_GRADOS, atol=1e-10) and
                np.isclose(abs(dy), RESOLUCION_GRADOS, atol=1e-10)):
            raise ValueError(f"{path}: resolucion no nativa {dx} x {dy}")
        if dx < 0:
            lon, datos = lon[::-1], datos[:, ::-1]
        if dy > 0:
            lat, datos = lat[::-1], datos[::-1, :]
        transform = Affine(
            RESOLUCION_GRADOS, 0.0, float(lon[0] - RESOLUCION_GRADOS / 2),
            0.0, -RESOLUCION_GRADOS,
            float(lat[0] + RESOLUCION_GRADOS / 2),
        )
        attrs = {str(k): str(v) for k, v in ds.attrs.items()}
        band_attrs = {str(k): str(v) for k, v in ds["lccs_class"].attrs.items()}
        return RasterFuente(
            datos=datos,
            transform=transform,
            crs=rasterio.crs.CRS.from_epsg(4326),
            tags=attrs,
            band_tags=band_attrs,
            nombre=path.name,
        )


def _recortar_fuente(
    fuente: RasterFuente,
    comunas,
) -> tuple[np.ndarray, np.ndarray, Counter, object]:
    """Aplica mascara de huellas; devuelve datos, mascara, conteos y transform."""
    from affine import Affine
    from rasterio.features import rasterize

    formas = [
        (geom, int(cod)) for geom, cod in
        zip(comunas.geometry, comunas.cod_comuna, strict=False)
        if geom is not None and not geom.is_empty and int(cod) >= 0
    ]
    # La zona sin demarcar (codigo 0) debe prevalecer en posibles solapes.
    formas.sort(key=lambda par: par[1] == 0)
    shape = fuente.datos.shape
    toca = rasterize(
        [(geom, 1) for geom, _ in formas], out_shape=shape,
        transform=fuente.transform, fill=0, dtype="uint8", all_touched=True,
    ).astype(bool)
    codigos = rasterize(
        formas, out_shape=shape, transform=fuente.transform,
        fill=-1, dtype="int32", all_touched=False,
    )
    if not toca.any():
        raise ValueError(f"{fuente.nombre}: la AOI no toca Chile")
    filas, columnas = np.where(toca)
    r0, r1 = int(filas.min()), int(filas.max()) + 1
    c0, c1 = int(columnas.min()), int(columnas.max()) + 1
    toca = toca[r0:r1, c0:c1]
    codigos = codigos[r0:r1, c0:c1]
    datos = np.asarray(fuente.datos[r0:r1, c0:c1], dtype="uint8").copy()
    datos[~toca] = 0
    conteos = Counter(int(x) for x in codigos[toca & (codigos >= 0)])
    transform = fuente.transform * Affine.translation(c0, r0)
    return datos, toca, conteos, transform


def _escribir_tiff(
    tmp: Path,
    datos: np.ndarray,
    toca: np.ndarray,
    transform,
    fuente: RasterFuente,
    *,
    anio: int,
    version: str,
    aoi: AOI,
    fuente_sha256: str,
    mascara_sha256: str,
    raw_deleted_after_validation: bool,
) -> None:
    import rasterio

    tmp.unlink(missing_ok=True)
    profile = {
        "driver": "GTiff",
        "width": int(datos.shape[1]),
        "height": int(datos.shape[0]),
        "count": 1,
        "dtype": "uint8",
        "crs": fuente.crs,
        "transform": transform,
        "nodata": 0,
        "compress": "deflate",
        "zlevel": 9,
        "predictor": 2,
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
        "BIGTIFF": "IF_SAFER",
    }
    tags = dict(fuente.tags)
    tags.update({
        "producto": PRODUCTO,
        "dataset_id": DATASET_ID,
        "dataset_url": DATASET_URL,
        "version": _version_legible(version),
        "reference_year": str(anio),
        "spatial_resolution_native": "1/360 degree (~300 m)",
        "temporal_resolution_native": "annual",
        "resampling": "none",
        "aoi_id": aoi.id,
        "territorio": aoi.territorio,
        "administrative_mask": "cell footprint touches Chile; Antarctica excluded",
        "administrative_mask_sha256": mascara_sha256,
        "source_filename": fuente.nombre,
        "source_sha256": fuente_sha256,
        "raw_deleted_after_validation": str(raw_deleted_after_validation).lower(),
    })
    band_tags = dict(fuente.band_tags)
    band_tags.update({
        "variable": "lccs_class",
        "long_name": band_tags.get("long_name", "Land cover class defined in LCCS"),
    })
    with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True):
        with rasterio.open(tmp, "w", **profile) as dst:
            dst.write(datos, 1)
            dst.write_mask(toca.astype("uint8") * 255)
            dst.update_tags(**tags)
            dst.update_tags(1, **band_tags)


def _validar_tiff(
    path: Path,
    *,
    anio: int,
    aoi: AOI,
    datos_esperados: np.ndarray | None = None,
    toca_esperada: np.ndarray | None = None,
) -> tuple[int, tuple[float, float, float, float]]:
    import rasterio

    with rasterio.open(path) as ds:
        if ds.count != 1 or ds.dtypes[0] != "uint8" or ds.nodata != 0:
            raise ValueError(f"{path}: tipo, bandas o nodata invalidos")
        if ds.crs is None or ds.crs.to_epsg() != 4326:
            raise ValueError(f"{path}: CRS no es EPSG:4326")
        if not (np.isclose(abs(ds.transform.a), RESOLUCION_GRADOS, atol=1e-12) and
                np.isclose(abs(ds.transform.e), RESOLUCION_GRADOS, atol=1e-12)):
            raise ValueError(f"{path}: se altero la resolucion nativa")
        tags = ds.tags()
        if tags.get("reference_year") != str(anio) or tags.get("aoi_id") != aoi.id:
            raise ValueError(f"{path}: tags de ano/AOI inconsistentes")
        datos = ds.read(1)
        toca = ds.dataset_mask() > 0
        if not toca.any() or np.any(datos[~toca] != 0):
            raise ValueError(f"{path}: mascara administrativa invalida")
        if datos_esperados is not None and not np.array_equal(datos, datos_esperados):
            raise ValueError(f"{path}: los valores no coinciden pixel a pixel")
        if toca_esperada is not None and not np.array_equal(toca, toca_esperada):
            raise ValueError(f"{path}: la huella administrativa no coincide")
        # Fuerza lectura de bloques, no solo del encabezado.
        for _, ventana in ds.block_windows(1):
            ds.read(1, window=ventana)
        b = ds.bounds
        return int(toca.sum()), (float(b.left), float(b.bottom),
                                 float(b.right), float(b.top))


def _marcar_fuente_eliminada(path: Path, *, anio: int, aoi: AOI) -> None:
    """Actualiza la declaracion solo despues de comprobar que el crudo ya no existe."""
    import rasterio

    with rasterio.open(path, "r+") as ds:
        ds.update_tags(raw_deleted_after_validation="true")
    _validar_tiff(path, anio=anio, aoi=aoi)


def _conteo_comunas_salida(path: Path, comunas) -> Counter:
    import rasterio
    from rasterio.features import rasterize

    formas = [
        (geom, int(cod)) for geom, cod in
        zip(comunas.geometry, comunas.cod_comuna, strict=False)
        if geom is not None and not geom.is_empty and int(cod) >= 0
    ]
    formas.sort(key=lambda par: par[1] == 0)
    with rasterio.open(path) as ds:
        toca = ds.dataset_mask() > 0
        codigos = rasterize(
            formas, out_shape=(ds.height, ds.width), transform=ds.transform,
            fill=-1, dtype="int32", all_touched=False,
        )
    return Counter(int(x) for x in codigos[toca & (codigos >= 0)])


def _salida_path(root: Path, anio: int, aoi: AOI) -> Path:
    return root / str(anio) / f"ESA_CCI_LC_{anio}_{aoi.id}_300m.tif"


def _validar_existente(path: Path, comunas, anio: int, aoi: AOI) -> SalidaValidada:
    pixeles, bbox = _validar_tiff(path, anio=anio, aoi=aoi)
    return SalidaValidada(
        path=path,
        aoi=aoi,
        pixeles=pixeles,
        conteo_comunas=_conteo_comunas_salida(path, comunas),
        bbox=bbox,
    )


def _publicar(
    salida: Path,
    fuente: RasterFuente,
    comunas,
    *,
    anio: int,
    version: str,
    aoi: AOI,
    fuente_sha256: str,
    mascara_sha256: str,
    raw_deleted_after_validation: bool,
) -> SalidaValidada:
    datos, toca, conteos, transform = _recortar_fuente(fuente, comunas)
    salida.parent.mkdir(parents=True, exist_ok=True)
    tmp = salida.with_suffix(salida.suffix + ".part")
    try:
        _escribir_tiff(
            tmp, datos, toca, transform, fuente,
            anio=anio, version=version, aoi=aoi,
            fuente_sha256=fuente_sha256, mascara_sha256=mascara_sha256,
            raw_deleted_after_validation=raw_deleted_after_validation,
        )
        pixeles, bbox = _validar_tiff(
            tmp, anio=anio, aoi=aoi,
            datos_esperados=datos, toca_esperada=toca,
        )
        os.replace(tmp, salida)
        pixeles_final, bbox_final = _validar_tiff(
            salida, anio=anio, aoi=aoi,
            datos_esperados=datos, toca_esperada=toca,
        )
        if pixeles_final != pixeles or bbox_final != bbox:
            raise ValueError(f"{salida}: cambio despues de publicacion atomica")
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return SalidaValidada(salida, aoi, pixeles, conteos, bbox)


def _validar_cobertura_anual(salidas: list[SalidaValidada], comunas) -> dict:
    if len(salidas) != 5 or len({x.aoi.id for x in salidas}) != 5:
        raise ValueError("un ano debe tener exactamente las cinco AOI")
    total = Counter()
    for salida in salidas:
        total.update(salida.conteo_comunas)
    esperados = {int(x) for x in comunas.cod_comuna}
    faltantes = sorted(esperados - set(total))
    menos_de_dos = sorted((cod, total[cod]) for cod in esperados if total[cod] < 2)
    if faltantes or menos_de_dos:
        raise ValueError(
            f"cobertura comunal incompleta: faltantes={faltantes}, <2={menos_de_dos}"
        )
    return {
        "unidades_administrativas": len(esperados),
        "comunas_cod_positivo": sum(c > 0 for c in esperados),
        "zona_sin_demarcar_cod_0": int(0 in esperados),
        "pixeles_huella_chile": sum(x.pixeles for x in salidas),
        "min_pixeles_centro_por_unidad": min(total[c] for c in esperados),
        "max_pixeles_centro_por_unidad": max(total[c] for c in esperados),
    }


@contextmanager
def _netcdf_en_respuesta(path: Path, temporal: Path):
    """Entrega un NetCDF aunque CDS responda ZIP; limpia siempre el extraido."""
    extraido: Path | None = None
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as zf:
                miembros = [x for x in zf.infolist()
                            if not x.is_dir() and x.filename.lower().endswith(".nc")]
                if len(miembros) != 1:
                    raise ValueError(
                        f"{path}: se esperaba un NetCDF en el ZIP, hay {len(miembros)}"
                    )
                extraido = temporal / Path(miembros[0].filename).name
                with zf.open(miembros[0]) as origen, extraido.open("wb") as destino:
                    shutil.copyfileobj(origen, destino, length=8 * 1024 * 1024)
            yield extraido
        else:
            yield path
    finally:
        if extraido is not None:
            extraido.unlink(missing_ok=True)


@retry(n=4, base=5.0)
def _descargar_cds(request: dict, destino: Path) -> None:
    import cdsapi

    destino.unlink(missing_ok=True)
    cliente = cdsapi.Client()
    cliente.retrieve(DATASET_ID, request, str(destino))
    if not destino.exists() or destino.stat().st_size == 0:
        raise IOError("CDS no produjo un archivo descargado")


def _gb_libres(path: Path) -> float:
    existente = path
    while not existente.exists() and existente != existente.parent:
        existente = existente.parent
    return shutil.disk_usage(existente).free / 1_000_000_000


def _registrar_salidas(
    manifiesto: Manifiesto,
    salidas: list[SalidaValidada],
    *,
    anio: int,
    version: str,
    fuente: Path,
    fuente_sha256: str,
    fuente_eliminada: bool,
    comunas_path: Path,
) -> None:
    for s in salidas:
        manifiesto.archivo(
            salida=s.path,
            version=_version_legible(version),
            granule_id=fuente.name,
            url=DATASET_URL,
            aoi_id=s.aoi.id,
            territorio=s.aoi.territorio,
            bbox=s.bbox,
            resolucion="1/360 degree (~300 m), native grid, no resampling",
            tiempo_nativo=f"annual reference year {anio}",
            qa="LCCS class + internal administrative footprint mask",
            pixeles=s.pixeles,
            mascara=(
                f"{comunas_path}; all_touched=True; cod_comuna center retained "
                "for coverage validation"
            ),
            validacion=(
                "GeoTIFF reopened; all blocks readable; native transform; "
                "pixel values and administrative mask compared exactly"
            ),
            crudo_eliminado=fuente_eliminada,
            crudo=fuente,
            checksum_fuente=fuente_sha256,
            variables_conservadas=["lccs_class"],
        )


def _procesar_local(
    fuente_path: Path,
    *,
    anio: int,
    version: str,
    aois: tuple[AOI, ...],
    comunas,
    comunas_path: Path,
    salida_root: Path,
    mascara_sha256: str,
    eliminar_fuente: bool,
    manifiesto: Manifiesto,
) -> dict:
    fuente_hash = sha256(fuente_path)
    salidas: list[SalidaValidada] = []
    for aoi in aois:
        salida = _salida_path(salida_root, anio, aoi)
        if salida.exists():
            salidas.append(_validar_existente(salida, comunas, anio, aoi))
            continue
        fuente = _leer_tiff_local(fuente_path, aoi)
        salidas.append(_publicar(
            salida, fuente, comunas,
            anio=anio, version=version, aoi=aoi,
            fuente_sha256=fuente_hash, mascara_sha256=mascara_sha256,
            raw_deleted_after_validation=eliminar_fuente,
        ))
    cobertura = _validar_cobertura_anual(salidas, comunas)
    fuente_eliminada = False
    if eliminar_fuente:
        # Revalida desde disco justo antes de retirar la unica copia rectangular.
        revalidadas = [_validar_existente(x.path, comunas, anio, x.aoi)
                       for x in salidas]
        _validar_cobertura_anual(revalidadas, comunas)
        fuente_path.unlink()
        fuente_eliminada = not fuente_path.exists()
        if not fuente_eliminada:
            raise IOError(f"no se pudo retirar {fuente_path}")
        for s in salidas:
            _marcar_fuente_eliminada(s.path, anio=anio, aoi=s.aoi)
    _registrar_salidas(
        manifiesto, salidas, anio=anio, version=version,
        fuente=fuente_path, fuente_sha256=fuente_hash,
        fuente_eliminada=fuente_eliminada, comunas_path=comunas_path,
    )
    manifiesto.registrar({
        "evento": "anio_validado",
        "anio": anio,
        "fuente_tipo": "GeoTIFF rectangular local",
        "fuente_eliminada": fuente_eliminada,
        **cobertura,
    })
    return cobertura


def _procesar_cds(
    *,
    anio: int,
    version: str,
    aois: tuple[AOI, ...],
    comunas,
    comunas_path: Path,
    salida_root: Path,
    mascara_sha256: str,
    min_gb_libres: float,
    conservar_crudo: bool,
    manifiesto: Manifiesto,
) -> dict:
    salidas: list[SalidaValidada] = []
    temporal = ensure_dir(salida_root / ".tmp")
    try:
        for aoi in aois:
            salida = _salida_path(salida_root, anio, aoi)
            if salida.exists():
                existente = _validar_existente(salida, comunas, anio, aoi)
                salidas.append(existente)
                import rasterio
                with rasterio.open(salida) as src:
                    tags = src.tags()
                manifiesto.registrar({
                    "evento": "archivo_existente_revalidado",
                    "anio": anio,
                    "version": _version_legible(version),
                    "aoi_id": aoi.id,
                    "territorio": aoi.territorio,
                    "salida": str(salida),
                    "bytes_salida": salida.stat().st_size,
                    "sha256_salida": sha256(salida),
                    "sha256_fuente_original": tags.get("source_sha256"),
                    "crudo_eliminado": tags.get("raw_deleted_after_validation") == "true",
                    "pixeles_chile": existente.pixeles,
                    "validacion": "reopened; all blocks readable; native grid and mask",
                })
                continue
            libres = _gb_libres(salida_root)
            if libres < min_gb_libres:
                raise OSError(
                    f"reserva de disco: quedan {libres:.1f} GB, se exigen "
                    f"{min_gb_libres:.1f} GB"
                )
            request = {
                "variable": "all",
                "year": [str(anio)],
                "version": [version],
                "area": [aoi.bbox[3], aoi.bbox[0], aoi.bbox[1], aoi.bbox[2]],
            }
            crudo = temporal / f"{anio}_{aoi.id}.download.part"
            _descargar_cds(request, crudo)
            respuesta_hash = sha256(crudo)
            with _netcdf_en_respuesta(crudo, temporal) as netcdf:
                fuente_hash = sha256(netcdf)
                fuente = _leer_netcdf(netcdf)
                validada = _publicar(
                    salida, fuente, comunas,
                    anio=anio, version=version, aoi=aoi,
                    fuente_sha256=fuente_hash, mascara_sha256=mascara_sha256,
                    raw_deleted_after_validation=not conservar_crudo,
                )
            if not conservar_crudo:
                crudo.unlink(missing_ok=True)
            eliminado = not crudo.exists()
            manifiesto.registrar({
                "evento": "respuesta_cds_validada",
                "anio": anio,
                "aoi_id": aoi.id,
                "request": request,
                "respuesta_sha256": respuesta_hash,
                "netcdf_sha256": fuente_hash,
                "crudo_eliminado": eliminado,
            })
            _registrar_salidas(
                manifiesto, [validada], anio=anio, version=version,
                fuente=crudo, fuente_sha256=fuente_hash,
                fuente_eliminada=eliminado, comunas_path=comunas_path,
            )
            salidas.append(validada)
    finally:
        for sobrante in temporal.glob("*.part"):
            # Nunca conserva respuestas incompletas o no validadas.
            sobrante.unlink(missing_ok=True)
        try:
            temporal.rmdir()
        except OSError:
            pass
    cobertura = _validar_cobertura_anual(salidas, comunas)
    manifiesto.registrar({
        "evento": "anio_validado",
        "anio": anio,
        "fuente_tipo": "Climate Data Store",
        **cobertura,
    })
    return cobertura


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--desde", default="2000",
        help="ano inicial del analisis (producto nativo disponible desde 1992)",
    )
    p.add_argument("--hasta", default="2026", help="ano final solicitado")
    p.add_argument(
        "--fuente", choices=("auto", "cds", "tiff_local"), default="auto",
        help="auto usa el TIFF local si existe y CDS en caso contrario",
    )
    p.add_argument(
        "--aoi", default="todos",
        help="todos o lista: continente,juan_fernandez,desventuradas,rapa_nui,sala_y_gomez",
    )
    p.add_argument("--comunas", type=Path, default=DATA / "comunas.shp")
    p.add_argument(
        "--salida", type=Path,
        default=DATA / "lulc" / "ESA_CCI_300m_native",
    )
    p.add_argument(
        "--tiff-local-dir", type=Path, default=DATA / "lulc",
        help="carpeta de los antiguos ESA_CCI_AAAA_chile.tif",
    )
    p.add_argument("--min-gb-libres", type=float, default=100.0)
    p.add_argument(
        "--eliminar-fuente-local", action="store_true",
        help="retira cada TIFF rectangular solo tras validar sus cinco reemplazos",
    )
    p.add_argument(
        "--conservar-crudo", action="store_true",
        help="diagnostico: conserva respuestas CDS (por defecto se eliminan)",
    )
    p.add_argument("--dry-run", action="store_true")
    return p


def main() -> int:
    args = _parser().parse_args()
    desde, hasta = _anio(args.desde), _anio(args.hasta)
    if desde > hasta:
        raise SystemExit("--desde no puede ser posterior a --hasta")
    if args.min_gb_libres < 0:
        raise SystemExit("--min-gb-libres debe ser no negativo")
    if not args.comunas.exists():
        raise SystemExit(f"no existe mascara administrativa: {args.comunas}")
    if args.eliminar_fuente_local and args.fuente == "cds":
        raise SystemExit("--eliminar-fuente-local no aplica con --fuente cds")

    por_anio, metadatos_catalogo = catalogo_con_fallback()
    disponibles = sorted(int(x) for x in por_anio)
    pedidos = list(range(desde, hasta + 1))
    procesables = [y for y in pedidos if str(y) in por_anio]
    no_disponibles = [y for y in pedidos if str(y) not in por_anio]
    aois = seleccionar(args.aoi, args.comunas)
    # El contrato anual completo se valida con cinco AOI; subconjuntos sirven
    # para diagnostico, pero no autorizan eliminar la fuente rectangular.
    if args.eliminar_fuente_local and len(aois) != 5:
        raise SystemExit("para eliminar la fuente local se requieren las cinco AOI")

    resumen = {
        "producto": PRODUCTO,
        "resolucion_espacial_nativa": "1/360 degree (~300 m)",
        "resolucion_temporal_nativa": "annual",
        "anos_catalogo": [min(disponibles), max(disponibles)],
        "anos_solicitados": [desde, hasta],
        "anos_procesables": procesables,
        "anos_no_disponibles": no_disponibles,
        "aois": [{"id": a.id, "bbox": a.bbox} for a in aois],
        "salida": str(args.salida),
        "fuente": args.fuente,
        "eliminar_fuente_local": args.eliminar_fuente_local,
        "catalogo": metadatos_catalogo,
    }
    print(json.dumps(resumen, ensure_ascii=False, indent=2, default=str))
    if args.dry_run:
        for y in procesables:
            local = args.tiff_local_dir / f"ESA_CCI_{y}_chile.tif"
            usar_local = args.fuente == "tiff_local" or (
                args.fuente == "auto" and local.exists()
            )
            for aoi in aois:
                request = None if usar_local else {
                    "variable": "all",
                    "year": [str(y)],
                    "version": [por_anio[str(y)]],
                    "area": [aoi.bbox[3], aoi.bbox[0], aoi.bbox[1], aoi.bbox[2]],
                }
                print(json.dumps({
                    "anio": y,
                    "aoi": aoi.id,
                    "fuente": str(local) if usar_local else DATASET_URL,
                    "request_cds": request,
                    "salida": str(_salida_path(args.salida, y, aoi)),
                }, ensure_ascii=False, default=str))
        return 0

    if not procesables:
        raise SystemExit(
            f"ningun ano solicitado esta disponible; CDS ofrece {min(disponibles)}-"
            f"{max(disponibles)}"
        )
    salida_root = ensure_dir(args.salida)
    manifiesto = Manifiesto(
        salida_root / "manifiestos", PRODUCTO,
        {**resumen, "comunas": str(args.comunas),
         "comunas_sha256": sha256_conjunto_shapefile(args.comunas)},
    )
    comunas = _geometrias_validas(args.comunas)
    mascara_hash = sha256_conjunto_shapefile(args.comunas)
    try:
        for y in procesables:
            version = por_anio[str(y)]
            local = args.tiff_local_dir / f"ESA_CCI_{y}_chile.tif"
            usar_local = args.fuente == "tiff_local" or (
                args.fuente == "auto" and local.exists()
            )
            if usar_local:
                if not local.exists():
                    raise FileNotFoundError(local)
                cobertura = _procesar_local(
                    local, anio=y, version=version, aois=aois,
                    comunas=comunas, comunas_path=args.comunas,
                    salida_root=salida_root, mascara_sha256=mascara_hash,
                    eliminar_fuente=args.eliminar_fuente_local,
                    manifiesto=manifiesto,
                )
            else:
                cobertura = _procesar_cds(
                    anio=y, version=version, aois=aois,
                    comunas=comunas, comunas_path=args.comunas,
                    salida_root=salida_root, mascara_sha256=mascara_hash,
                    min_gb_libres=args.min_gb_libres,
                    conservar_crudo=args.conservar_crudo,
                    manifiesto=manifiesto,
                )
            print(f"{y}: validado {cobertura}")
        manifiesto.terminar(
            estado="completo",
            anos=procesables,
            anos_no_disponibles=no_disponibles,
            temporales_restantes=0,
        )
    except BaseException as exc:
        manifiesto.terminar(estado="error", error=repr(exc))
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
