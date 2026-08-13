"""_recorte_tropomi.py — recorta un gránulo L2 de TROPOMI a un bbox.

Los gránulos L2 son órbitas completas (~600 MB, de polo a polo); sobre Chile
cae ~5% de los píxeles. Este módulo recorta la caja mínima de
(scanline, ground_pixel) que contiene el bbox y copia TODO lo demás tal cual:
los 6 grupos con datos (PRODUCT, SUPPORT_DATA/{GEOLOCATIONS, DETAILED_RESULTS,
DETAILED_RESULTS/{O22CLD,FRESCO}, INPUT_DATA}) y el árbol METADATA completo.

No se pierde ninguna variable ni se degrada la resolución: solo desaparece la
geografía fuera del bbox. El resultado pesa ~4% del original.

La copia es de bytes crudos (`set_auto_maskandscale(False)` en ambos extremos):
sin eso, las variables con `scale_factor`/`add_offset` se desempaquetarían al
leer y se re-empaquetarían al escribir, alterando valores por redondeo.
"""
from __future__ import annotations

from pathlib import Path

import netCDF4
import numpy as np

DIMS_ESPACIALES = ("scanline", "ground_pixel")
# Compresores que netCDF4 acepta en `compression=`; se propaga el que traiga.
COMPRESORES = ("zlib", "zstd", "bzip2", "szip", "blosc_lz", "blosc_lz4",
               "blosc_lz4hc", "blosc_zlib", "blosc_zstd")


def limpiar_tmp(dest_dir: Path) -> int:
    """Borra recortes .tmp huérfanos (SIGKILL/SIGTERM previo). Devuelve cuántos."""
    huerfanos = list(Path(dest_dir).glob("*.tmp"))
    for t in huerfanos:
        t.unlink(missing_ok=True)
    return len(huerfanos)


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


def _copiar_grupo(g_in, g_out, sl: slice, gp: slice) -> None:
    """Copia dimensiones, variables y subgrupos recortando las dims espaciales."""
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
        nueva[...] = var[indices] if indices else var[...]

    for nombre, sub in g_in.groups.items():
        _copiar_grupo(sub, g_out.createGroup(nombre), sl, gp)


def _corregir_metadatos(out: netCDF4.Dataset, src_name: str, bbox) -> None:
    """Reescribe los metadatos de cobertura, que describen la órbita completa."""
    prod = out["PRODUCT"]
    lat, lon = prod["latitude"], prod["longitude"]
    lat.set_auto_maskandscale(True)
    lon.set_auto_maskandscale(True)
    la, lo = np.ma.masked_invalid(lat[:]), np.ma.masked_invalid(lon[:])
    if la.count():
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
                  f"recorte a bbox {tuple(bbox)} de {src_name} con "
                  f"_recorte_tropomi.py; los estadísticos de METADATA siguen "
                  f"siendo los de la órbita completa")


def recortar(src: Path, dest_dir: Path, bbox, sufijo=".chile.nc") -> Path | None:
    """Recorta `src` al bbox y lo escribe en `dest_dir`. None si no cruza el bbox.

    Escribe primero a un archivo temporal, lo valida releyéndolo y solo al final
    lo renombra: una interrupción nunca deja un recorte a medias que parezca
    terminado (el llamador borra el gránulo global de 600 MB tras esta llamada).
    Si el recorte ya existe, no rehace el trabajo.
    """
    src = Path(src)
    dest_dir = Path(dest_dir)
    base = src.name.removesuffix(".nc")
    salida = dest_dir / (base + sufijo)
    # marca para gránulos que no cruzan el bbox: sin ella se re-descargarían
    # 600 MB en cada corrida
    centinela = dest_dir / (base + sufijo + ".vacio")
    if salida.exists():
        return salida
    if centinela.exists():
        return None

    tmp = dest_dir / (base + sufijo + ".tmp")
    with netCDF4.Dataset(src) as ds:
        rango = _rango_bbox(ds, bbox)
        if rango is None:
            centinela.touch()
            return None
        sl, gp = rango
        try:
            with netCDF4.Dataset(tmp, "w", format="NETCDF4") as out:
                _copiar_grupo(ds, out, sl, gp)
                _corregir_metadatos(out, src.name, bbox)
            with netCDF4.Dataset(tmp) as chk:  # detecta truncados
                chk["PRODUCT/latitude"][0, 0, :1]
        except BaseException:  # incluye KeyboardInterrupt/SystemExit
            tmp.unlink(missing_ok=True)
            raise
    tmp.rename(salida)
    return salida
