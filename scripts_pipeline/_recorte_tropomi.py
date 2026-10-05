"""Recorta/máscara un gránulo L2 TROPOMI sin degradar sus píxeles ni horas.

Los gránulos L2 son órbitas completas (~600 MB, de polo a polo); sobre Chile
cae ~5% de los píxeles. Este módulo recorta la caja mínima de
``(scanline, ground_pixel)`` que contiene el AOI y conserva la selección mínima
necesaria para modelar exposición: columna y precisión, QA, tiempo, huella,
AMF, nube, presión/altura, nieve y ángulos. Se excluyen diagnósticos de ajuste y
el ``averaging_kernel`` de 34 capas; sólo se requeriría si el análisis aplicara
una corrección vertical explícita.

No se pierde ningún píxel ni se degrada la resolución. Además del recorte
rectangular mínimo, una máscara administrativa marca todos los píxeles cuya
huella toca Chile, conserva ``cod_comuna`` por centro (incluido el código 0) y
rellena los campos científicos fuera de esa máscara para que compriman bien.
La relación exacta muchos-a-muchos píxel↔comuna se construye aparte.

La copia es de bytes crudos (`set_auto_maskandscale(False)` en ambos extremos):
sin eso, las variables con `scale_factor`/`add_offset` se desempaquetarían al
leer y se re-empaquetarían al escribir, alterando valores por redondeo.
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

import netCDF4
import numpy as np

DIMS_ESPACIALES = ("scanline", "ground_pixel")
# Compresores que netCDF4 acepta en `compression=`; se propaga el que traiga.
COMPRESORES = ("zlib", "zstd", "bzip2", "szip", "blosc_lz", "blosc_lz4",
               "blosc_lz4hc", "blosc_zlib", "blosc_zstd")

# Política deliberadamente explícita: estos campos bastan para el modelo y la
# trazabilidad de cada observación; no se conservan cientos de diagnósticos del
# algoritmo de retrieval. Los nombres se comparten entre las colecciones HiR.
VARIABLES_PRODUCT = {
    "scanline", "ground_pixel", "time", "corner",
    "latitude", "longitude", "delta_time", "time_utc", "qa_value",
    "nitrogendioxide_tropospheric_column",
    "nitrogendioxide_tropospheric_column_precision",
    "sulfurdioxide_total_vertical_column",
    "sulfurdioxide_total_vertical_column_precision",
    "carbonmonoxide_total_column",
    "carbonmonoxide_total_column_precision",
    "ozone_total_vertical_column",
    "ozone_total_vertical_column_precision",
    "air_mass_factor", "air_mass_factor_total",
    "air_mass_factor_troposphere",
}
VARIABLES_GEO = {
    "latitude_bounds", "longitude_bounds", "geolocation_flags",
    "solar_zenith_angle", "solar_azimuth_angle",
    "viewing_zenith_angle", "viewing_azimuth_angle",
}
VARIABLES_INPUT = {
    "surface_pressure", "surface_altitude", "snow_ice_flag",
    "cloud_fraction", "cloud_fraction_crb", "cloud_pressure",
    "cloud_pressure_crb",
}
VARIABLES_DETALLE = {
    "processing_quality_flags",
    "cloud_fraction_crb_nitrogendioxide_window",
    "cloud_radiance_fraction_nitrogendioxide_window",
}
VARIABLES_COLUMNA = {
    "nitrogendioxide_tropospheric_column",
    "sulfurdioxide_total_vertical_column",
    "carbonmonoxide_total_column",
    "ozone_total_vertical_column",
}


def _variable_necesaria(ruta_grupo: str, nombre: str) -> bool:
    """Decide por ruta, evitando homónimos diagnósticos en subgrupos."""
    if ruta_grupo == "/PRODUCT":
        return nombre in VARIABLES_PRODUCT
    if ruta_grupo.endswith("/SUPPORT_DATA/GEOLOCATIONS"):
        return nombre in VARIABLES_GEO
    if ruta_grupo.endswith("/SUPPORT_DATA/INPUT_DATA"):
        return nombre in VARIABLES_INPUT
    if ruta_grupo.endswith("/SUPPORT_DATA/DETAILED_RESULTS"):
        return nombre in VARIABLES_DETALLE
    return False


def _variables_archivo(ds: netCDF4.Dataset) -> list[str]:
    rutas: list[str] = []

    def recorrer(grupo, prefijo=""):
        for nombre in grupo.variables:
            rutas.append(f"{prefijo}/{nombre}")
        for nombre, sub in grupo.groups.items():
            recorrer(sub, f"{prefijo}/{nombre}")

    recorrer(ds)
    return rutas


def limpiar_tmp(dest_dir: Path) -> int:
    """Borra recortes .tmp huérfanos (SIGKILL/SIGTERM previo). Devuelve cuántos."""
    huerfanos = list(Path(dest_dir).glob("*.tmp"))
    for t in huerfanos:
        t.unlink(missing_ok=True)
    return len(huerfanos)


def validar_recorte(path: Path, bbox, *, mascara_requerida: bool = False) -> dict:
    """Reabre el NetCDF y comprueba estructura/máscara antes de liberar crudo."""
    lon_min, lat_min, lon_max, lat_max = bbox
    with netCDF4.Dataset(path) as ds:
        if "PRODUCT" not in ds.groups:
            raise ValueError(f"{Path(path).name}: falta PRODUCT")
        prod = ds["PRODUCT"]
        for nombre in ("latitude", "longitude"):
            if nombre not in prod.variables:
                raise ValueError(f"{Path(path).name}: falta PRODUCT/{nombre}")
        requeridas_producto = {"qa_value", "delta_time", "time_utc"}
        faltan_producto = requeridas_producto - set(prod.variables)
        if faltan_producto:
            raise ValueError(
                f"{Path(path).name}: PRODUCT sin {sorted(faltan_producto)}")
        columnas = VARIABLES_COLUMNA.intersection(prod.variables)
        if len(columnas) != 1:
            raise ValueError(
                f"{Path(path).name}: se esperaba una columna gaseosa, hay "
                f"{sorted(columnas)}")
        columna = next(iter(columnas))
        if columna + "_precision" not in prod.variables:
            raise ValueError(f"{Path(path).name}: falta precisión de {columna}")
        if mascara_requerida and (
                "averaging_kernel_retained" not in ds.ncattrs() or
                str(ds.getncattr("averaging_kernel_retained")).lower() != "false"):
            raise ValueError(
                f"{Path(path).name}: no declara selección compacta validada")
        lat = np.ma.masked_invalid(prod["latitude"][:])
        lon = np.ma.masked_invalid(prod["longitude"][:])
        if not lat.count() or lat.shape != lon.shape:
            raise ValueError(f"{Path(path).name}: geolocalización vacía/inconsistente")
        dentro = ((lat >= lat_min) & (lat <= lat_max) &
                  (lon >= lon_min) & (lon <= lon_max))
        n_dentro = int(np.ma.filled(dentro, False).sum())
        if not n_dentro:
            raise ValueError(f"{Path(path).name}: ningún píxel dentro del AOI")
        pixeles_chile = n_dentro
        if "CHILE_SUBSET" in ds.groups:
            sub = ds["CHILE_SUBSET"]
            requeridas = {
                "pixel_id", "source_scanline", "source_ground_pixel",
                "cod_comuna", "dentro_chile_centro", "toca_chile",
            }
            faltan = requeridas - set(sub.variables)
            if faltan:
                raise ValueError(f"{Path(path).name}: CHILE_SUBSET sin {sorted(faltan)}")
            toca = np.asarray(sub["toca_chile"][:], dtype=bool)
            cod = np.asarray(sub["cod_comuna"][:], dtype="int32")
            pix = sub["pixel_id"]
            esperado = (len(sub.dimensions["scanline"]),
                        len(sub.dimensions["ground_pixel"]))
            if toca.shape != esperado or cod.shape != esperado or pix.shape != esperado:
                raise ValueError(f"{Path(path).name}: máscara/pixel_id inconsistentes")
            pixeles_chile = int(toca.sum())
            if not pixeles_chile:
                raise ValueError(f"{Path(path).name}: máscara administrativa vacía")
            if np.any((cod >= 0) & ~toca):
                raise ValueError(f"{Path(path).name}: centro chileno fuera de toca_chile")
            # Fuerza lecturas de identificadores y coordenadas reales.
            np.asarray(pix[:1, :1])
        elif mascara_requerida:
            raise ValueError(f"{Path(path).name}: falta CHILE_SUBSET")
        # Lectura real de la variable principal si está presente.
        if "qa_value" in prod.variables:
            prod["qa_value"][..., :1]
        return {"pixeles_aoi": n_dentro, "pixeles_chile": pixeles_chile,
                "shape_geolocalizacion": lat.shape}


def _rango_bbox(ds: netCDF4.Dataset, bbox) -> tuple[slice, slice] | None:
    """Caja mínima (scanline, ground_pixel) que cubre el bbox; None si no cruza."""
    lon_min, lat_min, lon_max, lat_max = bbox
    prod = ds["PRODUCT"]
    lat = prod["latitude"][:]
    lon = prod["longitude"][:]
    dentro = ((lat >= lat_min) & (lat <= lat_max) &
              (lon >= lon_min) & (lon <= lon_max))
    if not np.any(dentro):
        return None
    dims = prod["latitude"].dimensions
    ejes_sl = tuple(i for i, d in enumerate(dims) if d != "scanline")
    ejes_gp = tuple(i for i, d in enumerate(dims) if d != "ground_pixel")
    sl = np.where(np.any(dentro, axis=ejes_sl))[0]
    gp = np.where(np.any(dentro, axis=ejes_gp))[0]
    return (slice(int(sl.min()), int(sl.max()) + 1),
            slice(int(gp.min()), int(gp.max()) + 1))


def _matriz_espacial(var, sl: slice, gp: slice):
    """Lee una variable y coloca scanline/ground_pixel como primeros ejes."""
    dims = tuple(var.dimensions)
    indices = tuple(sl if d == "scanline" else gp if d == "ground_pixel"
                    else slice(None) for d in dims)
    arr = np.ma.masked_invalid(var[indices])
    e_sl, e_gp = dims.index("scanline"), dims.index("ground_pixel")
    return np.moveaxis(arr, (e_sl, e_gp), (0, 1))


def _firma_shapefile(path: Path):
    base = Path(path).with_suffix("")
    return tuple(
        (ext, base.with_suffix(ext).stat().st_mtime_ns,
         base.with_suffix(ext).stat().st_size)
        for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg")
        if base.with_suffix(ext).exists()
    )


@lru_cache(maxsize=4)
def _geometrias_validas_cache(comunas_path: str, firma):
    import geopandas as gpd
    import shapely

    del firma

    comunas = gpd.read_file(comunas_path).to_crs("EPSG:4326")
    if "cod_comuna" not in comunas:
        raise ValueError(f"{comunas_path}: falta cod_comuna")
    try:
        comunas["geometry"] = comunas.geometry.make_valid()
    except AttributeError:
        from shapely.validation import make_valid
        comunas["geometry"] = comunas.geometry.map(make_valid)
    comunas["cod_comuna"] = comunas["cod_comuna"].astype("int32")
    comunas = comunas[
        comunas.geometry.notna() & ~comunas.geometry.is_empty &
        (comunas.cod_comuna >= 0)
    ][["cod_comuna", "geometry"]].copy()
    if comunas.empty:
        raise ValueError(f"{comunas_path}: máscara administrativa vacía")
    union = shapely.union_all(comunas.geometry.to_numpy())
    shapely.prepare(union)
    # Inicializa el índice una sola vez; sjoin lo reutiliza para cada órbita.
    comunas.sindex
    return comunas, union


def _geometrias_validas(comunas_path: Path):
    path = Path(comunas_path).resolve()
    return _geometrias_validas_cache(str(path), _firma_shapefile(path))


def _mascara_administrativa(ds: netCDF4.Dataset, sl: slice, gp: slice,
                            comunas_path: Path) -> dict:
    """Centro comunal + intersección de la huella nativa con Chile."""
    import geopandas as gpd
    import shapely

    prod = ds["PRODUCT"]
    lat = np.squeeze(_matriz_espacial(prod["latitude"], sl, gp))
    lon = np.squeeze(_matriz_espacial(prod["longitude"], sl, gp))
    if lat.ndim != 2 or lon.shape != lat.shape:
        raise ValueError("TROPOMI: latitude/longitude no forman una malla 2-D")
    la = np.asarray(np.ma.filled(lat, np.nan), dtype=float)
    lo = np.asarray(np.ma.filled(lon, np.nan), dtype=float)
    plano_valido = np.isfinite(la.ravel()) & np.isfinite(lo.ravel())
    comunas, union = _geometrias_validas(comunas_path)

    cod = np.full(la.size, -1, dtype="int32")
    indices = np.flatnonzero(plano_valido)
    if indices.size:
        puntos = gpd.GeoDataFrame(
            {"flat": indices},
            geometry=gpd.points_from_xy(lo.ravel()[indices], la.ravel()[indices]),
            crs="EPSG:4326",
        )
        cruce = gpd.sjoin(puntos, comunas, how="inner", predicate="intersects")
        if not cruce.empty:
            # En solapes, código 0 (Zona sin demarcar) prevalece en el catálogo
            # por centro; la tabla muchos-a-muchos conserva todas las relaciones.
            cruce["prioridad_cero"] = (cruce.cod_comuna == 0).astype("uint8")
            cruce = cruce.sort_values(
                ["flat", "prioridad_cero", "cod_comuna"]
            ).drop_duplicates("flat", keep="last")
            cod[cruce.flat.to_numpy(dtype="int64")] = \
                cruce.cod_comuna.to_numpy(dtype="int32")
    cod = cod.reshape(la.shape)

    toca = cod >= 0
    metodo_huella = "centro (bounds no disponibles)"
    try:
        geo = ds["PRODUCT"]["SUPPORT_DATA"]["GEOLOCATIONS"]
        lat_b = np.squeeze(_matriz_espacial(geo["latitude_bounds"], sl, gp))
        lon_b = np.squeeze(_matriz_espacial(geo["longitude_bounds"], sl, gp))
        if lat_b.shape[:2] != la.shape or lon_b.shape != lat_b.shape or \
                lat_b.ndim != 3 or lat_b.shape[-1] < 3:
            raise ValueError("bounds con forma inesperada")
        coords = np.stack([
            np.asarray(np.ma.filled(lon_b, np.nan), dtype=float),
            np.asarray(np.ma.filled(lat_b, np.nan), dtype=float),
        ], axis=-1)
        validas = np.all(np.isfinite(coords), axis=(2, 3))
        if np.any(validas):
            huellas = shapely.polygons(coords[validas])
            huellas = shapely.make_valid(huellas)
            toca_bounds = np.zeros(la.shape, dtype=bool)
            toca_bounds[validas] = np.asarray(
                shapely.intersects(huellas, union), dtype=bool)
            toca |= toca_bounds
            metodo_huella = "latitude_bounds/longitude_bounds; intersects"
    except (KeyError, ValueError, TypeError) as exc:
        metodo_huella = f"centro; bounds no utilizables ({type(exc).__name__})"

    return {
        "latitude": la,
        "longitude": lo,
        "cod_comuna": cod,
        "toca_chile": toca,
        "metodo_huella": metodo_huella,
    }


def _copiar_atributos(origen, destino) -> None:
    destino.setncatts({a: origen.getncattr(a) for a in origen.ncattrs()})


def _tipo_destino(g_out, var):
    """Tipo con el que crear la variable destino.

    `var.dtype` degrada los tipos definidos por el usuario a su numpy
    subyacente; hay que recrear enum/compound/vlen en el archivo destino
    porque son por-archivo y no se pueden reutilizar entre Datasets.
    """
    if var.dtype is str:
        return str
    dt = var.datatype
    if isinstance(dt, netCDF4.EnumType):
        return (g_out.enumtypes.get(dt.name)
                or g_out.createEnumType(dt.dtype, dt.name, dt.enum_dict))
    if isinstance(dt, netCDF4.CompoundType):
        return (g_out.cmptypes.get(dt.name)
                or g_out.createCompoundType(dt.dtype, dt.name))
    if isinstance(dt, netCDF4.VLType):
        return (g_out.vltypes.get(dt.name)
                or g_out.createVLType(dt.dtype, dt.name))
    return dt


def _enmascarar_variable(datos, var, toca_chile: np.ndarray | None):
    """Sustituye por _FillValue sólo campos espaciales fuera de Chile."""
    if toca_chile is None or not {"scanline", "ground_pixel"}.issubset(
            var.dimensions):
        return datos
    # Estas cuatro variables permiten reconstruir/validar cada huella.
    if var.name.rsplit("/", 1)[-1] in {
            "latitude", "longitude", "latitude_bounds", "longitude_bounds"}:
        return datos
    if "_FillValue" not in var.ncattrs() or var.dtype is str:
        return datos
    arr = np.asarray(datos).copy()
    forma = [1] * arr.ndim
    forma[var.dimensions.index("scanline")] = toca_chile.shape[0]
    forma[var.dimensions.index("ground_pixel")] = toca_chile.shape[1]
    fuera = np.broadcast_to((~toca_chile).reshape(forma), arr.shape)
    arr[fuera] = var.getncattr("_FillValue")
    return arr


def _copiar_grupo(g_in, g_out, sl: slice, gp: slice,
                  toca_chile: np.ndarray | None = None,
                  ruta_grupo: str = "") -> None:
    """Copia sólo variables necesarias, recortando las dims espaciales."""
    _copiar_atributos(g_in, g_out)

    for nombre, dim in g_in.dimensions.items():
        if dim.isunlimited():
            g_out.createDimension(nombre, None)
        elif nombre == "scanline":
            g_out.createDimension(nombre, sl.stop - sl.start)
        elif nombre == "ground_pixel":
            g_out.createDimension(nombre, gp.stop - gp.start)
        else:
            g_out.createDimension(nombre, len(dim))

    for nombre, var in g_in.variables.items():
        if not _variable_necesaria(ruta_grupo, nombre):
            continue
        filtros = var.filters() or {}
        tipo = _tipo_destino(g_out, var)
        # fletcher32/compresión sobre vlen o compound → "NetCDF: HDF error"
        primitivo = tipo is not str and not isinstance(
            var.datatype, (netCDF4.VLType, netCDF4.CompoundType))
        kw = {"shuffle": bool(filtros.get("shuffle")),
              "fletcher32": bool(filtros.get("fletcher32")) and primitivo}
        if primitivo:
            for alg in COMPRESORES:
                if filtros.get(alg):
                    kw["compression"] = alg
                    kw["complevel"] = filtros.get("complevel", 4) or 4
                    break
        # _FillValue debe fijarse al crear la variable, no como atributo suelto
        relleno = var.getncattr("_FillValue") if "_FillValue" in var.ncattrs() else None
        nueva = g_out.createVariable(nombre, tipo, var.dimensions,
                                     fill_value=relleno, **kw)
        nueva.setncatts({a: var.getncattr(a) for a in var.ncattrs()
                         if a != "_FillValue"})
        # copia cruda: sin esto, scale_factor/add_offset alteran valores
        var.set_auto_maskandscale(False)
        nueva.set_auto_maskandscale(False)
        indices = tuple(sl if d == "scanline" else gp if d == "ground_pixel"
                        else slice(None) for d in var.dimensions)
        datos = var[indices] if indices else var[...]
        datos = _enmascarar_variable(datos, var, toca_chile)
        nueva[...] = datos

    for nombre, sub in g_in.groups.items():
        ruta_sub = f"{ruta_grupo}/{nombre}"
        _copiar_grupo(sub, g_out.createGroup(nombre), sl, gp, toca_chile,
                      ruta_sub)


def _orbita(ds: netCDF4.Dataset, src_name: str) -> int:
    if "orbit" in ds.ncattrs():
        return int(ds.getncattr("orbit"))
    m = re.search(r"_(\d{5})_\d{2}_\d{6}_", src_name)
    if not m:
        raise ValueError(f"{src_name}: no se pudo determinar órbita")
    return int(m.group(1))


def _agregar_subset(out: netCDF4.Dataset, src: netCDF4.Dataset,
                    sl: slice, gp: slice, mascara: dict, *, src_name: str,
                    bbox, comunas_path: Path, mascara_sha256: str | None,
                    aoi_id: str | None, territorio: str | None) -> None:
    """Publica identificadores/máscaras sin agregar observaciones."""
    prod = src["PRODUCT"]
    scan = np.asarray(prod["scanline"][sl], dtype="int64")
    ground = np.asarray(prod["ground_pixel"][gp], dtype="int64")
    orbit = _orbita(src, src_name)
    pixel_id = (np.int64(orbit) * np.int64(10_000_000_000) +
                scan[:, None] * np.int64(10_000) + ground[None, :])

    sub = out.createGroup("CHILE_SUBSET")
    sub.createDimension("scanline", len(scan))
    sub.createDimension("ground_pixel", len(ground))

    def crear(nombre, tipo, dims, datos, **attrs):
        v = sub.createVariable(nombre, tipo, dims, zlib=True, complevel=4,
                               shuffle=True, fill_value=False)
        v[:] = datos
        if attrs:
            v.setncatts(attrs)
        return v

    crear("source_scanline", "i4", ("scanline",), scan.astype("int32"))
    crear("source_ground_pixel", "i4", ("ground_pixel",),
          ground.astype("int32"))
    crear("pixel_id", "i8", ("scanline", "ground_pixel"), pixel_id,
          formula="orbit*10000000000 + source_scanline*10000 + source_ground_pixel",
          uniqueness="usar junto con granule_id; reprocesamientos de una órbita comparten ID")
    crear("cod_comuna", "i4", ("scanline", "ground_pixel"),
          mascara["cod_comuna"].astype("int32"), outside_mask_code=np.int32(-1),
          zone_without_demarcation_code=np.int32(0),
          semantics="código por centro; relaciones de huella se guardan aparte")
    crear("dentro_chile_centro", "u1", ("scanline", "ground_pixel"),
          (mascara["cod_comuna"] >= 0).astype("uint8"))
    crear("toca_chile", "u1", ("scanline", "ground_pixel"),
          mascara["toca_chile"].astype("uint8"),
          method=mascara["metodo_huella"])
    sub.setncatts({
        "granule_id": src_name.removesuffix(".nc"),
        "orbit": orbit,
        "aoi_id": aoi_id or "sin_etiqueta",
        "territorio": territorio or "sin_etiqueta",
        "crop_bbox": tuple(float(x) for x in bbox),
        "administrative_mask": str(comunas_path),
        "administrative_mask_sha256": mascara_sha256 or "no_registrado",
        "native_spatial_resolution_preserved": "true",
        "native_time_preserved": "PRODUCT/time_utc y PRODUCT/delta_time",
        "spatial_aggregation": "none",
        "temporal_interpolation": "none",
        "zone_without_demarcation": "cod_comuna=0 conservado",
    })


def _corregir_metadatos(out: netCDF4.Dataset, src_name: str, bbox,
                        mascara: dict | None = None) -> None:
    """Reescribe los metadatos de cobertura, que describen la órbita completa."""
    prod = out["PRODUCT"]
    lat, lon = prod["latitude"], prod["longitude"]
    lat.set_auto_maskandscale(True)
    lon.set_auto_maskandscale(True)
    la, lo = np.ma.masked_invalid(lat[:]), np.ma.masked_invalid(lon[:])
    if mascara is not None and np.any(mascara["toca_chile"]):
        dentro = mascara["toca_chile"]
        la_m = mascara["latitude"][dentro]
        lo_m = mascara["longitude"][dentro]
        out.setncatts({"geospatial_lat_min": float(np.nanmin(la_m)),
                       "geospatial_lat_max": float(np.nanmax(la_m)),
                       "geospatial_lon_min": float(np.nanmin(lo_m)),
                       "geospatial_lon_max": float(np.nanmax(lo_m))})
    elif la.count():
        out.setncatts({"geospatial_lat_min": float(la.min()),
                       "geospatial_lat_max": float(la.max()),
                       "geospatial_lon_min": float(lo.min()),
                       "geospatial_lon_max": float(lo.max())})
    if "time_utc" in prod.variables:
        t = prod["time_utc"][:]
        if getattr(t, "size", 0):
            plano = np.asarray(t).ravel()
            out.setncatts({"time_coverage_start": str(plano[0]),
                           "time_coverage_end": str(plano[-1])})
    previo = out.getncattr("history") if "history" in out.ncattrs() else ""
    out.setncattr("history", (f"{previo}\n" if previo else "") +
                  f"recorte/máscara administrativa a bbox {tuple(bbox)} de "
                  f"{src_name} con _recorte_tropomi.py; selección mínima de "
                  f"variables científicas, sin diagnósticos de retrieval")


def recortar(src: Path, dest_dir: Path, bbox, sufijo=".chile.nc", *,
             comunas_path: Path | None = None,
             mascara_sha256: str | None = None,
             aoi_id: str | None = None,
             territorio: str | None = None) -> Path | None:
    """Recorta `src` al bbox y lo escribe en `dest_dir`. None si no cruza el bbox.

    Escribe primero a un archivo temporal, lo valida releyéndolo y solo al final
    lo renombra: una interrupción nunca deja un recorte a medias que parezca
    terminado (el llamador borra el gránulo global de 600 MB tras esta llamada).
    Si el recorte ya existe, no rehace el trabajo.
    """
    src = Path(src)
    dest_dir = Path(dest_dir)
    # Los rectángulos históricos terminaban en `.chile.nc`; al migrarlos se
    # elimina ese marcador para publicar el mismo nombre que produciría el
    # descargador actual desde la órbita global.
    base = (src.name.removesuffix(".chile.nc")
            if src.name.endswith(".chile.nc")
            else src.name.removesuffix(".nc"))
    salida = dest_dir / (base + sufijo)
    # marca para gránulos que no cruzan el bbox: sin ella se re-descargarían
    # 600 MB en cada corrida
    centinela = dest_dir / (base + sufijo + ".vacio")
    if salida.exists():
        validar_recorte(salida, bbox, mascara_requerida=comunas_path is not None)
        return salida
    if centinela.exists():
        if not mascara_sha256:
            return None
        try:
            if json.loads(centinela.read_text(encoding="utf-8")).get(
                    "mascara_sha256") == mascara_sha256:
                return None
        except (OSError, ValueError, TypeError):
            pass
        centinela.unlink(missing_ok=True)

    tmp = dest_dir / (base + sufijo + ".tmp")
    with netCDF4.Dataset(src) as ds:
        rango = _rango_bbox(ds, bbox)
        if rango is None:
            marca_tmp = centinela.with_suffix(centinela.suffix + ".tmp")
            marca_tmp.write_text(json.dumps({
                "motivo": "sin_centros_en_bbox_expandido",
                "mascara_sha256": mascara_sha256,
                "aoi_id": aoi_id,
            }), encoding="utf-8")
            os.replace(marca_tmp, centinela)
            return None
        sl, gp = rango
        mascara = (_mascara_administrativa(ds, sl, gp, comunas_path)
                    if comunas_path else None)
        if mascara is not None and not np.any(mascara["toca_chile"]):
            marca_tmp = centinela.with_suffix(centinela.suffix + ".tmp")
            marca_tmp.write_text(json.dumps({
                "motivo": "ninguna_huella_intersecta_mascara",
                "mascara_sha256": mascara_sha256,
                "aoi_id": aoi_id,
            }), encoding="utf-8")
            os.replace(marca_tmp, centinela)
            return None
        try:
            with netCDF4.Dataset(tmp, "w", format="NETCDF4") as out:
                _copiar_grupo(ds, out, sl, gp,
                              mascara["toca_chile"] if mascara else None)
                out.setncatts({
                    "retained_source_variables": json.dumps(
                        _variables_archivo(out), ensure_ascii=True),
                    "variable_selection": (
                        "gas_column+precision; qa/time/geolocation/bounds; "
                        "AMF/cloud/surface/snow/angles"),
                    "averaging_kernel_retained": "false",
                    "averaging_kernel_note": (
                        "excluded; retain only if vertical-profile correction "
                        "is explicitly planned"),
                })
                if mascara is not None:
                    _agregar_subset(
                        out, ds, sl, gp, mascara, src_name=src.name, bbox=bbox,
                        comunas_path=comunas_path,
                        mascara_sha256=mascara_sha256,
                        aoi_id=aoi_id, territorio=territorio)
                _corregir_metadatos(out, src.name, bbox, mascara)
            validar_recorte(tmp, bbox, mascara_requerida=mascara is not None)
        except BaseException:  # incluye KeyboardInterrupt/SystemExit
            tmp.unlink(missing_ok=True)
            raise
    os.replace(tmp, salida)
    validar_recorte(salida, bbox, mascara_requerida=comunas_path is not None)
    centinela.unlink(missing_ok=True)
    return salida
