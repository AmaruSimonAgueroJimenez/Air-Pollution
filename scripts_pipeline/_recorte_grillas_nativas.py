"""Recortes atómicos de grillas satelitales sin perder resolución nativa.

Los productos L3 de OMI y MOPITT que CMR filtra por ``bounding_box`` siguen
siendo archivos globales.  ACAG entrega Sudamérica completa.  Este módulo
convierte cada archivo temporal en subconjuntos compactos del Chile
administrativo (continente e islas) y sólo publica el resultado después de
volver a abrirlo y validarlo.

La salida conserva cada celda individual: no promedia por comuna ni por día.
Además incluye coordenadas, índices de la grilla fuente y ``pixel_id`` estable,
de modo que otro paso pueda enlazar todos los píxeles con comunas y estaciones
SINCA sin reducir prematuramente la resolución.
"""
from __future__ import annotations

import os
import re
import json
from functools import lru_cache
from pathlib import Path

import numpy as np


def _indices(coordenada: np.ndarray, minimo: float, maximo: float) -> np.ndarray:
    a = np.asarray(coordenada, dtype=float)
    return np.flatnonzero(np.isfinite(a) & (a >= minimo) & (a <= maximo))


def _copiar_attrs(origen, destino, *, omitir=()) -> None:
    for nombre, valor in origen.attrs.items():
        if nombre not in omitir:
            destino.attrs[nombre] = valor


def _crear_dataset(grupo, nombre: str, datos, origen=None):
    """Crea un dataset comprimido y copia atributos no referenciales."""
    arr = np.asarray(datos)
    kw = {}
    if arr.ndim and arr.size:
        kw.update(compression="gzip", compression_opts=4, shuffle=True)
    ds = grupo.create_dataset(nombre, data=arr, **kw)
    if origen is not None:
        # Las referencias HDF5 DIMENSION_LIST apuntan al archivo fuente y no
        # son válidas en la salida. Las coordenadas explícitas de ChileSubset
        # sustituyen esas referencias de forma inequívoca.
        _copiar_attrs(origen, ds, omitir={"DIMENSION_LIST", "REFERENCE_LIST"})
    return ds


def _firma_shapefile(path: Path) -> tuple[tuple[str, int, int], ...]:
    """Firma barata del conjunto Shapefile para invalidar la caché en caliente."""
    base = Path(path).with_suffix("")
    partes = []
    for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
        parte = base.with_suffix(ext)
        if parte.exists():
            st = parte.stat()
            partes.append((ext, st.st_mtime_ns, st.st_size))
    return tuple(partes)


@lru_cache(maxsize=64)
def _rasterizar_comunas_cacheada(
    lat_t: tuple[float, ...],
    lon_t: tuple[float, ...],
    comunas_path: str,
    firma: tuple[tuple[str, int, int], ...],
    resolucion: float | None,
):
    """Implementación cacheada por grilla, máscara y resolución."""
    del firma  # participa en la llave y fuerza recálculo si cambia la máscara
    try:
        import geopandas as gpd
        from rasterio.features import rasterize
        from rasterio.transform import from_origin
    except ImportError as exc:
        raise RuntimeError(
            "Para el recorte poligonal instala geopandas, shapely y rasterio") from exc

    lat, lon = np.asarray(lat_t, float), np.asarray(lon_t, float)
    dx = (float(abs(np.median(np.diff(lon)))) if len(lon) > 1
          else float(resolucion))
    dy = (float(abs(np.median(np.diff(lat)))) if len(lat) > 1
          else float(resolucion))
    comunas = gpd.read_file(comunas_path).to_crs("EPSG:4326")
    if "cod_comuna" not in comunas:
        raise ValueError(f"{comunas_path}: falta cod_comuna")
    # comunas.shp contiene geometrías históricamente inválidas; make_valid
    # evita huecos o errores topológicos durante el recorte.
    try:
        comunas["geometry"] = comunas.geometry.make_valid()
    except AttributeError:  # geopandas/shapely antiguos
        from shapely.validation import make_valid
        comunas["geometry"] = comunas.geometry.map(make_valid)
    formas = [(geom, int(cod)) for geom, cod in
              zip(comunas.geometry, comunas["cod_comuna"], strict=False)
              if geom is not None and not geom.is_empty and int(cod) >= 0]
    # ``rasterize`` deja prevalecer la última geometría en solapes. La zona
    # sin demarcar se conserva explícitamente como 0 (no como fondo); la tabla
    # muchos-a-muchos mantiene además cualquier comuna positiva solapada.
    formas.sort(key=lambda item: item[1] == 0)
    transform = from_origin(float(lon.min() - dx / 2),
                            float(lat.max() + dy / 2), dx, dy)
    cod_norte_sur = rasterize(
        formas, out_shape=(len(lat), len(lon)), transform=transform,
        fill=-1, dtype="int32", all_touched=False)
    toca_norte_sur = rasterize(
        [(geom, 1) for geom, _ in formas], out_shape=(len(lat), len(lon)),
        transform=transform, fill=0, dtype="uint8", all_touched=True)
    # rasterio siempre escribe norte→sur; restituye la orientación fuente.
    if lat[0] > lat[-1]:
        cod, toca = cod_norte_sur, toca_norte_sur
    else:
        cod, toca = np.flipud(cod_norte_sur), np.flipud(toca_norte_sur)
    return cod, toca.astype(bool)


def rasterizar_comunas(lat: np.ndarray, lon: np.ndarray, comunas_path: Path,
                       resolucion: float | None = None):
    """Rasteriza códigos comunales en la grilla regular, reparando geometrías.

    La pertenencia principal se define por el centro de la celda
    (``all_touched=False``), por lo que cada pixel_id tiene como máximo un
    ``cod_comuna``. La relación muchos-a-muchos basada en huellas/intersecciones
    se genera aparte; nunca se representa de manera ambigua con un solo código.

    La salida se cachea por grilla y firma de la máscara. OMI y MOPITT repiten
    la misma grilla miles de días; así las geometrías no se reparan y
    rasterizan otra vez para cada archivo temporal.
    """
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    if lat.ndim != 1 or lon.ndim != 1 or not len(lat) or not len(lon):
        raise ValueError("la rasterización comunal requiere coordenadas 1-D regulares")
    if (len(lat) < 2 or len(lon) < 2) and not resolucion:
        raise ValueError("una grilla 1×N requiere indicar su resolución")
    path = Path(comunas_path).resolve()
    cod, toca = _rasterizar_comunas_cacheada(
        tuple(float(x) for x in lat),
        tuple(float(x) for x in lon),
        str(path),
        _firma_shapefile(path),
        None if resolucion is None else float(resolucion),
    )
    # Evita que un consumidor contamine la entrada compartida para otros días.
    return cod.copy(), toca.copy()


def _aplicar_mascara(datos, mascara: np.ndarray, origen):
    """Rellena fuera de Chile cuando el campo dispone de un fill fiable."""
    arr = np.asarray(datos)
    if arr.ndim < 2 or arr.shape[:2] != mascara.shape:
        return arr
    relleno = None
    for clave in ("_FillValue", "MissingValue"):
        if clave in origen.attrs:
            valor = np.asarray(origen.attrs[clave]).ravel()
            if valor.size:
                relleno = valor[0]
                break
    if relleno is None:
        if np.issubdtype(arr.dtype, np.floating):
            relleno = np.nan
        else:
            return arr
    fuera = ~mascara
    if arr.ndim > 2:
        fuera = fuera[(...,) + (None,) * (arr.ndim - 2)]
    return np.where(fuera, relleno, arr)


def nombre_hdf_recortado(nombre: str, sufijo=".chile.he5") -> str:
    """Nombre estable del subconjunto para un HDF/HDF-EOS fuente."""
    base = nombre
    for ext in (".he5", ".h5", ".hdf5"):
        if base.lower().endswith(ext):
            base = base[: -len(ext)]
            break
    return f"{base}{sufijo}"


def _salida_h5(src: Path, dest_dir: Path, sufijo=".chile.he5") -> Path:
    return Path(dest_dir) / nombre_hdf_recortado(src.name, sufijo)


def _publicar_h5(tmp: Path, salida: Path, validador) -> Path:
    try:
        validador(tmp)
        os.replace(tmp, salida)
        validador(salida)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return salida


def _validar_subset_h5(path: Path, grupo_campos: str, *, nlat: int,
                       nlon: int, bbox, orientacion: str) -> None:
    import h5py

    lon_min, lat_min, lon_max, lat_max = bbox
    with h5py.File(path, "r") as h:
        if grupo_campos not in h or "ChileSubset" not in h:
            raise ValueError(f"{path.name}: faltan grupos científicos o ChileSubset")
        sub = h["ChileSubset"]
        lat = np.asarray(sub["latitude"])
        lon = np.asarray(sub["longitude"])
        pix = sub["pixel_id"]
        if lat.shape != (nlat,) or lon.shape != (nlon,):
            raise ValueError(f"{path.name}: coordenadas con forma inesperada")
        if pix.shape != (nlat, nlon):
            raise ValueError(f"{path.name}: pixel_id no coincide con la grilla")
        if (lat.min() < lat_min - 1e-6 or lat.max() > lat_max + 1e-6 or
                lon.min() < lon_min - 1e-6 or lon.max() > lon_max + 1e-6):
            raise ValueError(f"{path.name}: contiene centros fuera del bbox solicitado")
        campos = h[grupo_campos]
        if not campos.keys():
            raise ValueError(f"{path.name}: no contiene campos científicos")
        esperado = (nlat, nlon) if orientacion == "lat_lon" else (nlon, nlat)
        espaciales = [d for d in campos.values()
                      if getattr(d, "ndim", 0) >= 2 and d.shape[:2] == esperado]
        if not espaciales:
            raise ValueError(f"{path.name}: ningún campo conserva la grilla recortada")
        # Fuerza una lectura real, no sólo la apertura del encabezado.
        np.asarray(espaciales[0][tuple(slice(0, 1) for _ in espaciales[0].shape)])


def validar_omi(path: Path, bbox, producto: str) -> None:
    import h5py
    grupos = {
        "NO2": "HDFEOS/GRIDS/ColumnAmountNO2/Data Fields",
        "SO2": "HDFEOS/GRIDS/OMI Total Column Amount SO2/Data Fields",
        "O3": "HDFEOS/GRIDS/OMI Column Amount O3/Data Fields",
    }
    with h5py.File(path, "r") as h:
        nlat = len(h["ChileSubset/latitude"])
        nlon = len(h["ChileSubset/longitude"])
    _validar_subset_h5(path, grupos[producto.upper()], nlat=nlat, nlon=nlon,
                       bbox=bbox, orientacion="lat_lon")


def validar_mopitt(path: Path, bbox) -> None:
    import h5py
    with h5py.File(path, "r") as h:
        nlat = len(h["ChileSubset/latitude"])
        nlon = len(h["ChileSubset/longitude"])
    _validar_subset_h5(path, "HDFEOS/GRIDS/MOP03/Data Fields",
                       nlat=nlat, nlon=nlon, bbox=bbox,
                       orientacion="lon_lat")


def recortar_omi(src: Path, dest_dir: Path, bbox, *, producto: str,
                 comunas_path: Path | None = None,
                 etiqueta: str | None = None) -> Path:
    """OMI L3 diario global → HDF5 comprimido con todos los píxeles del bbox."""
    import h5py

    src, dest_dir = Path(src), Path(dest_dir)
    sufijo = f".{etiqueta}.chile.he5" if etiqueta else ".chile.he5"
    salida = _salida_h5(src, dest_dir, sufijo=sufijo)
    producto = producto.upper()
    config = {
        "NO2": ("HDFEOS/GRIDS/ColumnAmountNO2/Data Fields", 0.25),
        "SO2": ("HDFEOS/GRIDS/OMI Total Column Amount SO2/Data Fields", 0.25),
        "O3": ("HDFEOS/GRIDS/OMI Column Amount O3/Data Fields", 1.0),
    }
    if producto not in config:
        raise ValueError(f"producto OMI inválido: {producto}")
    grupo_campos, resolucion = config[producto]

    if salida.exists():
        with h5py.File(salida, "r") as h:
            nlat, nlon = len(h["ChileSubset/latitude"]), len(h["ChileSubset/longitude"])
        _validar_subset_h5(salida, grupo_campos, nlat=nlat, nlon=nlon,
                           bbox=bbox, orientacion="lat_lon")
        return salida

    lon_min, lat_min, lon_max, lat_max = bbox
    with h5py.File(src, "r") as h:
        if grupo_campos not in h:
            raise KeyError(f"{src.name}: no existe {grupo_campos}")
        campos = h[grupo_campos]
        formas = [d.shape for d in campos.values() if getattr(d, "ndim", 0) >= 2]
        if not formas:
            raise ValueError(f"{src.name}: grilla OMI sin campos 2-D")
        ny, nx = formas[0][:2]
        # La grilla geográfica OMI comienza en (-180,-90), centro de celda.
        res_y, res_x = 180.0 / ny, 360.0 / nx
        if not (np.isclose(res_y, resolucion) and np.isclose(res_x, resolucion)):
            raise ValueError(
                f"{src.name}: resolución {res_y:g}×{res_x:g} no coincide con "
                f"{producto} ({resolucion:g}°)")
        lat_global = -90.0 + (np.arange(ny) + 0.5) * res_y
        lon_global = -180.0 + (np.arange(nx) + 0.5) * res_x
        iy, ix = _indices(lat_global, lat_min, lat_max), _indices(lon_global, lon_min, lon_max)
        if not len(iy) or not len(ix):
            raise ValueError(f"{src.name}: la grilla no cruza el bbox")
        if comunas_path:
            cod_comuna, toca_chile = rasterizar_comunas(
                lat_global[iy], lon_global[ix], comunas_path, resolucion)
        else:
            cod_comuna = np.ones((len(iy), len(ix)), dtype="int32")
            toca_chile = np.ones_like(cod_comuna, dtype=bool)

        tmp = salida.with_suffix(salida.suffix + ".part")
        tmp.unlink(missing_ok=True)
        try:
            with h5py.File(tmp, "w") as out:
                out.attrs.update({
                    "source_filename": src.name,
                    "subset_convention": "huellas que tocan máscara administrativa del AOI",
                    "spatial_resolution_degrees": resolucion,
                    "temporal_resolution": "daily",
                    "no_temporal_interpolation": np.uint8(1),
                })
                g = out.require_group(grupo_campos)
                _copiar_attrs(campos, g)
                for nombre, ds in campos.items():
                    if ds.ndim >= 2 and ds.shape[:2] == (ny, nx):
                        datos = ds[iy[0]:iy[-1] + 1, ix[0]:ix[-1] + 1, ...]
                        datos = _aplicar_mascara(datos, toca_chile, ds)
                    else:
                        datos = ds[()]
                    _crear_dataset(g, nombre, datos, ds)

                sub = out.create_group("ChileSubset")
                sub.attrs["crs"] = "EPSG:4326"
                _crear_dataset(sub, "latitude", lat_global[iy])
                _crear_dataset(sub, "longitude", lon_global[ix])
                _crear_dataset(sub, "source_lat_index", iy.astype("int32"))
                _crear_dataset(sub, "source_lon_index", ix.astype("int32"))
                pix = iy[:, None].astype("int64") * nx + ix[None, :]
                p = _crear_dataset(sub, "pixel_id", pix)
                p.attrs["formula"] = "source_lat_index * source_nlon + source_lon_index"
                sub.attrs["source_nlat"] = ny
                sub.attrs["source_nlon"] = nx
                sub.attrs["bbox"] = bbox
                _crear_dataset(sub, "cod_comuna", cod_comuna)
                sub["cod_comuna"].attrs.update({
                    "outside_mask_code": np.int32(-1),
                    "zone_without_demarcation_code": np.int32(0),
                })
                _crear_dataset(sub, "dentro_chile_centro", (cod_comuna >= 0).astype("uint8"))
                _crear_dataset(sub, "toca_chile", toca_chile.astype("uint8"))
                sub.attrs["polygon_mask"] = (str(comunas_path) if comunas_path
                                               else "no aplicado")
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    return _publicar_h5(
        tmp, salida,
        lambda p: _validar_subset_h5(p, grupo_campos, nlat=len(iy), nlon=len(ix),
                                     bbox=bbox, orientacion="lat_lon"))


def recortar_mopitt(src: Path, dest_dir: Path, bbox,
                    *, comunas_path: Path | None = None,
                    etiqueta: str | None = None) -> Path:
    """MOPITT MOP03J diario global → todos los campos, grilla 1° de Chile."""
    import h5py

    src, dest_dir = Path(src), Path(dest_dir)
    sufijo = f".{etiqueta}.chile.he5" if etiqueta else ".chile.he5"
    salida = _salida_h5(src, dest_dir, sufijo=sufijo)
    grupo_campos = "HDFEOS/GRIDS/MOP03/Data Fields"
    if salida.exists():
        with h5py.File(salida, "r") as h:
            nlat, nlon = len(h["ChileSubset/latitude"]), len(h["ChileSubset/longitude"])
        _validar_subset_h5(salida, grupo_campos, nlat=nlat, nlon=nlon,
                           bbox=bbox, orientacion="lon_lat")
        return salida

    lon_min, lat_min, lon_max, lat_max = bbox
    with h5py.File(src, "r") as h:
        if grupo_campos not in h:
            raise KeyError(f"{src.name}: no existe {grupo_campos}")
        campos = h[grupo_campos]
        lat_global = np.asarray(campos["Latitude"], dtype=float)
        lon_global = np.asarray(campos["Longitude"], dtype=float)
        iy, ix = _indices(lat_global, lat_min, lat_max), _indices(lon_global, lon_min, lon_max)
        if not len(iy) or not len(ix):
            raise ValueError(f"{src.name}: la grilla no cruza el bbox")
        nlat_global, nlon_global = len(lat_global), len(lon_global)
        if comunas_path:
            cod_comuna, toca_chile = rasterizar_comunas(
                lat_global[iy], lon_global[ix], comunas_path, 1.0)
        else:
            cod_comuna = np.ones((len(iy), len(ix)), dtype="int32")
            toca_chile = np.ones_like(cod_comuna, dtype=bool)

        tmp = salida.with_suffix(salida.suffix + ".part")
        tmp.unlink(missing_ok=True)
        try:
            with h5py.File(tmp, "w") as out:
                out.attrs.update({
                    "source_filename": src.name,
                    "subset_convention": "huellas que tocan máscara administrativa del AOI",
                    "spatial_resolution_degrees": 1.0,
                    "temporal_resolution": "daily_day_night_fields",
                    "no_temporal_interpolation": np.uint8(1),
                })
                g = out.require_group(grupo_campos)
                _copiar_attrs(campos, g)
                for nombre, ds in campos.items():
                    if ds.ndim >= 2 and ds.shape[:2] == (nlon_global, nlat_global):
                        datos = ds[ix[0]:ix[-1] + 1, iy[0]:iy[-1] + 1, ...]
                        datos = _aplicar_mascara(datos, toca_chile.T, ds)
                    elif nombre == "Latitude" and ds.shape == (nlat_global,):
                        datos = ds[iy[0]:iy[-1] + 1]
                    elif nombre == "Longitude" and ds.shape == (nlon_global,):
                        datos = ds[ix[0]:ix[-1] + 1]
                    else:
                        datos = ds[()]
                    _crear_dataset(g, nombre, datos, ds)

                sub = out.create_group("ChileSubset")
                sub.attrs["crs"] = "EPSG:4326"
                _crear_dataset(sub, "latitude", lat_global[iy])
                _crear_dataset(sub, "longitude", lon_global[ix])
                _crear_dataset(sub, "source_lat_index", iy.astype("int32"))
                _crear_dataset(sub, "source_lon_index", ix.astype("int32"))
                pix = iy[:, None].astype("int64") * nlon_global + ix[None, :]
                p = _crear_dataset(sub, "pixel_id", pix)
                p.attrs["formula"] = "source_lat_index * source_nlon + source_lon_index"
                sub.attrs["source_nlat"] = nlat_global
                sub.attrs["source_nlon"] = nlon_global
                sub.attrs["bbox"] = bbox
                _crear_dataset(sub, "cod_comuna", cod_comuna)
                sub["cod_comuna"].attrs.update({
                    "outside_mask_code": np.int32(-1),
                    "zone_without_demarcation_code": np.int32(0),
                })
                _crear_dataset(sub, "dentro_chile_centro", (cod_comuna >= 0).astype("uint8"))
                _crear_dataset(sub, "toca_chile", toca_chile.astype("uint8"))
                sub.attrs["polygon_mask"] = (str(comunas_path) if comunas_path
                                               else "no aplicado")
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    return _publicar_h5(
        tmp, salida,
        lambda p: _validar_subset_h5(p, grupo_campos, nlat=len(iy), nlon=len(ix),
                                     bbox=bbox, orientacion="lon_lat"))


def nombre_acag_recortado(nombre: str, etiqueta: str | None = None) -> str:
    sufijo = f".{etiqueta}.chile.nc" if etiqueta else ".chile.nc"
    return re.sub(r"\.nc$", sufijo, nombre, flags=re.IGNORECASE)


def validar_acag(path: Path, bbox) -> None:
    import xarray as xr

    lon_min, lat_min, lon_max, lat_max = bbox
    with xr.open_dataset(path, decode_times=False) as ds:
        if "PM25" not in ds or "lat" not in ds.coords or "lon" not in ds.coords:
            raise ValueError(f"{path.name}: faltan PM25/lat/lon")
        if "pixel_id" not in ds:
            raise ValueError(f"{path.name}: falta pixel_id")
        lat, lon = np.asarray(ds.lat), np.asarray(ds.lon)
        if not lat.size or not lon.size or ds.PM25.shape[-2:] != (lat.size, lon.size):
            raise ValueError(f"{path.name}: grilla ACAG inconsistente")
        if (lat.min() < lat_min - 1e-5 or lat.max() > lat_max + 1e-5 or
                lon.min() < lon_min - 1e-5 or lon.max() > lon_max + 1e-5):
            raise ValueError(f"{path.name}: ACAG fuera del bbox")
        ds.PM25.isel(lat=slice(0, 1), lon=slice(0, 1)).load()


def recortar_acag(src: Path, dest_dir: Path, bbox,
                  *, comunas_path: Path | None = None,
                  etiqueta: str | None = None) -> Path:
    """ACAG SA mensual/anual → NetCDF Chile 0,01°, sin promediar píxeles."""
    import xarray as xr

    src, dest_dir = Path(src), Path(dest_dir)
    salida = dest_dir / nombre_acag_recortado(src.name, etiqueta)
    if salida.exists():
        validar_acag(salida, bbox)
        return salida

    lon_min, lat_min, lon_max, lat_max = bbox
    with xr.open_dataset(src, decode_times=False) as ds:
        if "PM25" not in ds or "lat" not in ds.coords or "lon" not in ds.coords:
            raise ValueError(f"{src.name}: no es una grilla ACAG reconocida")
        lat0, lon0 = np.asarray(ds.lat), np.asarray(ds.lon)
        iy, ix = _indices(lat0, lat_min, lat_max), _indices(lon0, lon_min, lon_max)
        if not len(iy) or not len(ix):
            raise ValueError(f"{src.name}: no cruza Chile")
        sub = ds.isel(lat=slice(int(iy[0]), int(iy[-1]) + 1),
                      lon=slice(int(ix[0]), int(ix[-1]) + 1)).load()
        sub = sub.assign_coords(
            source_lat_index=("lat", iy.astype("int32")),
            source_lon_index=("lon", ix.astype("int32")),
        )
        pix = iy[:, None].astype("int64") * len(lon0) + ix[None, :]
        sub["pixel_id"] = (("lat", "lon"), pix)
        sub["pixel_id"].attrs.update({
            "long_name": "identificador estable de celda en la grilla fuente",
            "formula": "source_lat_index * source_nlon + source_lon_index",
        })
        sub.attrs.update({
            "source_filename": src.name,
            "source_nlat": len(lat0),
            "source_nlon": len(lon0),
            "subset_bbox": str(tuple(bbox)),
            "subset_convention": "huellas que tocan máscara administrativa del AOI",
            "spatial_resolution_degrees": float(abs(np.median(np.diff(lon0)))),
            "no_spatial_aggregation": "true",
            "no_temporal_interpolation": "true",
        })
        temporal = str(sub.attrs.get("TIMECOVERAGE", ""))
        sub.attrs["temporal_resolution"] = (
            "monthly" if len(temporal) == 6 or re.search(r"\d{6}-\d{6}", src.name)
            else "annual")
        if comunas_path:
            cod_comuna, toca_chile = rasterizar_comunas(
                np.asarray(sub.lat), np.asarray(sub.lon), comunas_path, 0.01)
        else:
            cod_comuna = np.ones(sub.PM25.shape[-2:], dtype="int32")
            toca_chile = np.ones_like(cod_comuna, dtype=bool)
        sub["cod_comuna"] = (("lat", "lon"), cod_comuna)
        sub["cod_comuna"].attrs.update({
            "outside_mask_code": np.int32(-1),
            "zone_without_demarcation_code": np.int32(0),
        })
        sub["dentro_chile_centro"] = (("lat", "lon"),
                                       (cod_comuna >= 0).astype("uint8"))
        sub["toca_chile"] = (("lat", "lon"), toca_chile.astype("uint8"))
        # Conserva la grilla regular y todos sus identificadores, pero los
        # valores fuera del polígono chileno quedan como faltantes compresibles.
        sub["PM25"] = sub.PM25.where(sub.toca_chile.astype(bool))
        sub.attrs["polygon_mask"] = (str(comunas_path) if comunas_path
                                      else "no aplicado")

        tmp = salida.with_suffix(salida.suffix + ".part")
        tmp.unlink(missing_ok=True)
        encoding = {}
        for nombre, var in sub.variables.items():
            if var.ndim:
                encoding[nombre] = {"zlib": True, "complevel": 4, "shuffle": True}
        try:
            sub.to_netcdf(tmp, engine="netcdf4", format="NETCDF4", encoding=encoding)
            validar_acag(tmp, bbox)
            os.replace(tmp, salida)
            validar_acag(salida, bbox)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    return salida


def _grupo_viirs(h):
    candidatos = []

    def visitar(nombre, obj):
        try:
            import h5py
            if isinstance(obj, h5py.Group) and nombre.endswith("Data Fields"):
                bajos = {k.lower() for k in obj.keys()}
                espaciales = [x.shape[:2] for x in obj.values()
                              if isinstance(x, h5py.Dataset) and x.ndim >= 2]
                if espaciales:
                    prioridad = (2 if {"lat", "lon"}.issubset(bajos) else
                                 1 if "vnp_grid_dnb" in nombre.lower() else 0)
                    candidatos.append((prioridad, nombre))
        except Exception:
            return

    h.visititems(visitar)
    if not candidatos:
        raise KeyError("no se encontró Data Fields de Black Marble")
    return max(candidatos)[1]


def _coordenadas_viirs(campos, nombre_fuente: str):
    """Lat/lon 15 arc-sec; VNP46 oficial suele omitir arrays explícitos."""
    nombres = {k.lower(): k for k in campos.keys()}
    if {"lat", "lon"}.issubset(nombres):
        lat0 = np.asarray(campos[nombres["lat"]])
        lon0 = np.asarray(campos[nombres["lon"]])
        if lat0.ndim == lon0.ndim == 1:
            return np.meshgrid(lat0, lon0, indexing="ij")
        if lat0.shape == lon0.shape and lat0.ndim == 2:
            return lat0, lon0
        raise ValueError(f"{nombre_fuente}: lat/lon Black Marble no reconocidas")

    tile = re.search(r"\.h(\d{2})v(\d{2})\.", nombre_fuente, re.IGNORECASE)
    if not tile:
        raise ValueError(f"{nombre_fuente}: falta código hXXvYY para geolocalizar")
    formas = [d.shape[:2] for d in campos.values() if getattr(d, "ndim", 0) >= 2]
    if not formas or any(f != formas[0] for f in formas):
        raise ValueError(f"{nombre_fuente}: SDS Black Marble sin grilla común")
    ny, nx = formas[0]
    h, v = int(tile.group(1)), int(tile.group(2))
    # Tile geográfico Black Marble: 10°×10°, 15 arc-sec para 2400².
    oeste, norte = -180.0 + 10.0 * h, 90.0 - 10.0 * v
    lon = oeste + (np.arange(nx, dtype=float) + 0.5) * (10.0 / nx)
    lat = norte - (np.arange(ny, dtype=float) + 0.5) * (10.0 / ny)
    return np.meshgrid(lat, lon, indexing="ij")


def _validar_viirs(path: Path, bbox) -> dict:
    import h5py

    with h5py.File(path, "r") as h:
        if "ChileSubset" not in h:
            raise ValueError(f"{path.name}: falta ChileSubset")
        sub = h["ChileSubset"]
        lat, lon = np.asarray(sub["latitude"]), np.asarray(sub["longitude"])
        if lat.shape != lon.shape or lat.ndim != 2 or not lat.size:
            raise ValueError(f"{path.name}: lat/lon VIIRS inconsistentes")
        if sub["pixel_id"].shape != lat.shape:
            raise ValueError(f"{path.name}: pixel_id VIIRS inconsistente")
        if not int(np.asarray(sub["toca_chile"]).sum()):
            raise ValueError(f"{path.name}: el recorte no toca Chile")
        grupo = h.attrs.get("science_group", "")
        if isinstance(grupo, bytes):
            grupo = grupo.decode()
        if not grupo or grupo not in h:
            raise ValueError(f"{path.name}: falta grupo científico VIIRS")
        campos_por_nombre = {
            nombre: d for nombre, d in h[grupo].items()
            if getattr(d, "ndim", 0) >= 2 and d.shape[:2] == lat.shape
        }
        campos = list(campos_por_nombre.values())
        producto = str(h.attrs.get("source_filename", path.name)).split(".", 1)[0]
        obligatorios = {
            "VNP46A1": {"UTC_Time", "DNB_At_Sensor_Radiance",
                         "QF_DNB", "QF_Cloud_Mask"},
            "VNP46A2": {"DNB_BRDF-Corrected_NTL",
                         "Gap_Filled_DNB_BRDF-Corrected_NTL",
                         "Mandatory_Quality_Flag", "QF_Cloud_Mask",
                         "Snow_Flag", "Latest_High_Quality_Retrieval"},
        }.get(producto, set())
        faltan = obligatorios.difference(campos_por_nombre)
        if faltan:
            raise ValueError(
                f"{path.name}: faltan campos necesarios {sorted(faltan)}")
        if not campos:
            raise ValueError(f"{path.name}: sin campos VIIRS espaciales")
        np.asarray(campos[0][:1, :1])
        return {"pixeles_chile": int(np.asarray(sub["toca_chile"]).sum()),
                "shape": lat.shape}


validar_viirs_black_marble = _validar_viirs


def _campos_necesarios_viirs(campos) -> list[str]:
    """Radiancia/modelado + QA; excluye SDS auxiliares voluminosos."""
    exactos = {
        # VNP46A1: hora real/radiancia al sensor + QA mínima.
        "utc_time",
        # Nombre SDS real en VNP46A1 colección 2 (la resolución se codifica en
        # el producto/grilla, no en el nombre de la variable).
        "dnb_at_sensor_radiance",
        "qf_dnb",
        "qf_cloud_mask",
        # VNP46A2: radiancia corregida/gap-fill + QA necesaria.
        "dnb_brdf-corrected_ntl",
        "gap_filled_dnb_brdf-corrected_ntl",
        "mandatory_quality_flag",
        "snow_flag",
        "latest_high_quality_retrieval",
    }
    seleccion = []
    for nombre, ds in campos.items():
        bajo = nombre.lower()
        mensual = (
            ("composite" in bajo and "snow_free" in bajo) and
            (bajo.endswith("_num") or bajo.endswith("_std") or
             not bajo.endswith(("_lat", "_lon")))
        )
        conteo = ("number_of_observations" in bajo or
                  "number_of_retrievals" in bajo)
        if bajo in exactos or mensual or conteo:
            if getattr(ds, "ndim", 0) >= 2:
                seleccion.append(nombre)
    if not seleccion:
        raise ValueError("Black Marble: no se encontraron radiancia/QA necesarios")
    return seleccion


def recortar_viirs_black_marble(src: Path, dest_dir: Path, bbox, *,
                                comunas_path: Path,
                                etiqueta: str,
                                mascara_sha256: str | None = None) -> Path | None:
    """Recorta Black Marble preservando radiancia, tiempo nativo y QA mínima."""
    import hashlib
    import h5py

    src, dest_dir = Path(src), Path(dest_dir)
    salida = _salida_h5(src, dest_dir,
                        sufijo=f".{etiqueta}.chile.h5")
    centinela = salida.with_suffix(salida.suffix + ".vacio")
    if salida.exists():
        _validar_viirs(salida, bbox)
        return salida
    if centinela.exists():
        try:
            previo = json.loads(centinela.read_text(encoding="utf-8"))
            if not mascara_sha256 or previo.get("mascara_sha256") == mascara_sha256:
                return None
        except (OSError, ValueError, TypeError):
            pass
        centinela.unlink(missing_ok=True)
    with h5py.File(src, "r") as h:
        grupo_campos = _grupo_viirs(h)
        campos = h[grupo_campos]
        campos_conservados = _campos_necesarios_viirs(campos)
        lat2, lon2 = _coordenadas_viirs(campos, src.name)
        lon_min, lat_min, lon_max, lat_max = bbox
        dentro = ((lat2 >= lat_min) & (lat2 <= lat_max) &
                  (lon2 >= lon_min) & (lon2 <= lon_max))
        filas, cols = np.where(dentro)
        if not len(filas):
            marca_tmp = centinela.with_suffix(centinela.suffix + ".tmp")
            marca_tmp.write_text(json.dumps({
                "source_filename": src.name, "aoi_id": etiqueta,
                "motivo": "tile_sin_centros_en_bbox",
                "mascara_sha256": mascara_sha256,
            }, sort_keys=True), encoding="utf-8")
            os.replace(marca_tmp, centinela)
            return None
        sy = slice(int(filas.min()), int(filas.max()) + 1)
        sx = slice(int(cols.min()), int(cols.max()) + 1)
        lat, lon = lat2[sy, sx], lon2[sy, sx]
        # Black Marble es grilla lineal lat/lon; se comprueba antes de usar la
        # rasterización comunal regular.
        lat1, lon1 = lat[:, 0], lon[0, :]
        if not (np.allclose(lat, lat1[:, None], equal_nan=True) and
                np.allclose(lon, lon1[None, :], equal_nan=True)):
            raise ValueError(f"{src.name}: grilla VIIRS no regular")
        cod_comuna, toca_chile = rasterizar_comunas(
            lat1, lon1, comunas_path, 15.0 / 3600.0)
        if not np.any(toca_chile):
            marca_tmp = centinela.with_suffix(centinela.suffix + ".tmp")
            marca_tmp.write_text(json.dumps({
                "source_filename": src.name, "aoi_id": etiqueta,
                "motivo": "tile_bbox_sin_interseccion_mascara",
                "mascara_sha256": mascara_sha256,
            }, sort_keys=True), encoding="utf-8")
            os.replace(marca_tmp, centinela)
            return None

        tmp = salida.with_suffix(salida.suffix + ".part")
        tmp.unlink(missing_ok=True)
        try:
            with h5py.File(tmp, "w") as out:
                _copiar_attrs(h, out)
                out.attrs.update({
                    "source_filename": src.name,
                    "science_group": grupo_campos,
                    "subset_bbox": bbox,
                    "subset_aoi": etiqueta,
                    "spatial_resolution_degrees": 15.0 / 3600.0,
                    "retained_science_fields": json.dumps(
                        campos_conservados, ensure_ascii=True),
                    "no_spatial_aggregation": np.uint8(1),
                    "no_temporal_interpolation": np.uint8(1),
                })
                g = out.require_group(grupo_campos)
                _copiar_attrs(campos, g)
                ny, nx = lat2.shape
                for nombre in campos_conservados:
                    ds = campos[nombre]
                    if ds.ndim >= 2 and ds.shape[:2] == (ny, nx):
                        datos = ds[sy, sx, ...]
                        datos = _aplicar_mascara(datos, toca_chile, ds)
                    elif ds.shape == (ny,):
                        datos = ds[sy]
                    elif ds.shape == (nx,):
                        datos = ds[sx]
                    else:
                        datos = ds[()]
                    _crear_dataset(g, nombre, datos, ds)
                sub = out.create_group("ChileSubset")
                _crear_dataset(sub, "latitude", lat)
                _crear_dataset(sub, "longitude", lon)
                _crear_dataset(sub, "source_row", np.arange(ny, dtype="int32")[sy])
                _crear_dataset(sub, "source_col", np.arange(nx, dtype="int32")[sx])
                tile = re.search(r"\.h(\d{2})v(\d{2})\.", src.name)
                if tile:
                    tile_code = int(tile.group(1)) * 100 + int(tile.group(2))
                else:
                    tile_code = int.from_bytes(
                        hashlib.sha1(src.name.encode()).digest()[:4], "big")
                rr = np.arange(ny, dtype="int64")[sy, None]
                cc = np.arange(nx, dtype="int64")[None, sx]
                pix = (np.int64(tile_code) * ny + rr) * nx + cc
                _crear_dataset(sub, "pixel_id", pix)
                _crear_dataset(sub, "cod_comuna", cod_comuna)
                sub["cod_comuna"].attrs.update({
                    "outside_mask_code": np.int32(-1),
                    "zone_without_demarcation_code": np.int32(0),
                })
                _crear_dataset(sub, "dentro_chile_centro",
                               (cod_comuna >= 0).astype("uint8"))
                _crear_dataset(sub, "toca_chile", toca_chile.astype("uint8"))
                sub.attrs.update({"crs": "EPSG:4326", "source_tile_code": tile_code,
                                  "pixel_id_formula": "(tile_code*nrow+row)*ncol+col"})
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    try:
        _validar_viirs(tmp, bbox)
        os.replace(tmp, salida)
        _validar_viirs(salida, bbox)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    centinela.unlink(missing_ok=True)
    return salida
