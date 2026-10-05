"""Subset L2 nativo por pares (scanline, ground_pixel), sin publicación ni retiro.

Escribe exclusivamente una ruta nueva proporcionada por el llamador. Conserva
todo PRODUCT, incluidos kernels/priores, empaquetamiento y tiempos originales.
La selección usa huellas verdaderas contra comunas, no QA ni centros solamente.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType

import netCDF4
import numpy as np

PRINCIPALES = {
    "co": "carbonmonoxide_total_column",
    "so2": "sulfurdioxide_total_vertical_column",
    "o3": "ozone_total_vertical_column",
    "hcho": "formaldehyde_tropospheric_vertical_column",
    "ch4": "methane_mixing_ratio",
}
ESPACIALES = {"scanline", "ground_pixel"}
PREFIJO = "chile_subset_"
CHUNK = 4096


def _sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def _sha_mascara(path):
    h = hashlib.sha256()
    for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
        p = Path(path).with_suffix(ext)
        if p.exists():
            h.update(ext.encode("ascii"))
            h.update(bytes.fromhex(_sha(p)))
    return h.hexdigest()


def _actualizar_hash(h, valor):
    a = np.asarray(valor)
    if a.dtype.fields:
        # Padding C de compound no es un valor científico definido. Cada
        # campo (incluyendo subarrays) se contrasta bit a bit por separado.
        for name in a.dtype.names:
            h.update(name.encode())
            _actualizar_hash(h, a[name])
    elif a.dtype.kind == "O":
        for x in a.flat:
            if isinstance(x, (str, bytes)):
                b = x.encode("utf-8") if isinstance(x, str) else x
                h.update(len(b).to_bytes(8, "big"))
                h.update(b)
            else:
                h.update(np.asarray(x).dtype.str.encode())
                _actualizar_hash(h, x)
    else:
        h.update(np.ascontiguousarray(a).tobytes())


def _attrs_hash(obj, *, root=False):
    h = hashlib.sha256()
    for name in sorted(obj.ncattrs()):
        if root and name.startswith(PREFIJO):
            continue
        a = np.asarray(obj.getncattr(name))
        h.update(name.encode())
        h.update(a.dtype.str.encode())
        h.update(str(a.shape).encode())
        _actualizar_hash(h, a)
    return h.hexdigest()


def _raw(var):
    var.set_auto_maskandscale(False)
    var.set_auto_chartostring(False)
    return var


def _grupos(group):
    yield group
    for child in group.groups.values():
        yield from _grupos(child)


def _variables(group):
    for g in _grupos(group):
        for name, var in g.variables.items():
            yield f"{g.path}/{name}", var


def _dims_salida(dims):
    resultado = []
    for dim in dims:
        if dim in ESPACIALES:
            if "pixel" not in resultado:
                resultado.append("pixel")
        else:
            resultado.append(dim)
    return tuple(resultado)


def _seleccionar(var, scan, ground):
    """Indexación emparejada, nunca el producto cartesiano de índices NetCDF."""
    _raw(var)
    dims = var.dimensions
    presentes = ESPACIALES.intersection(dims)
    if not presentes:
        return np.asarray(var[...])
    shape = tuple(len(scan) if d == "pixel" else var.shape[dims.index(d)]
                  for d in _dims_salida(dims))
    if not len(scan):
        dtype = object if var.dtype is str else var.dtype
        return np.empty(shape, dtype=dtype)
    indices = {"scanline": scan, "ground_pixel": ground}
    limites = {d: (int(indices[d].min()), int(indices[d].max()) + 1)
               for d in presentes}
    cortes = tuple(slice(*limites[d]) if d in presentes else slice(None)
                   for d in dims)
    datos = np.asarray(var[cortes])
    if len(presentes) == 1:
        dim = next(iter(presentes))
        return np.take(datos, indices[dim] - limites[dim][0], axis=dims.index(dim))
    movidos = np.moveaxis(datos, (dims.index("scanline"), dims.index("ground_pixel")), (0, 1))
    pares = movidos[scan - limites["scanline"][0], ground - limites["ground_pixel"][0]]
    return np.moveaxis(pares, 0, _dims_salida(dims).index("pixel"))


def _hash_inicio(var):
    h = hashlib.sha256()
    h.update(str(var.dtype).encode())
    h.update(str(tuple(var.shape)).encode())
    return h


def _digest_variable(var):
    _raw(var)
    h = _hash_inicio(var)
    if "pixel" not in var.dimensions:
        _actualizar_hash(h, var[...])
    else:
        eje = var.dimensions.index("pixel")
        for i in range(0, var.shape[eje], CHUNK):
            ix = [slice(None)] * var.ndim
            ix[eje] = slice(i, i + CHUNK)
            _actualizar_hash(h, var[tuple(ix)])
    return h.hexdigest()


def _tipo(group, var):
    if var.dtype is str:
        return str
    dt = var.datatype
    if isinstance(dt, netCDF4.EnumType):
        return group.enumtypes.get(dt.name) or group.createEnumType(dt.dtype, dt.name, dt.enum_dict)
    if isinstance(dt, netCDF4.CompoundType):
        return group.cmptypes.get(dt.name) or group.createCompoundType(dt.dtype, dt.name)
    if isinstance(dt, netCDF4.VLType):
        return group.vltypes.get(dt.name) or group.createVLType(dt.dtype, dt.name)
    return dt


def _copiar_variable(var, group, scan, ground):
    attrs = {k: var.getncattr(k) for k in var.ncattrs()}
    kwargs = {"fill_value": attrs.pop("_FillValue", False)}
    if var.dtype is not str and not isinstance(var.datatype, netCDF4.VLType):
        kwargs.update(zlib=True, complevel=4, shuffle=True)
    if getattr(var.dtype, "kind", None) in {"i", "u", "f"} and not isinstance(var.datatype, netCDF4.EnumType):
        kwargs["endian"] = var.endian()
    out = group.createVariable(var.name, _tipo(group, var), _dims_salida(var.dimensions), **kwargs)
    _raw(out)
    if "pixel" not in out.dimensions:
        out[...] = _seleccionar(var, scan, ground)
    else:
        eje = out.dimensions.index("pixel")
        for i in range(0, len(scan), CHUNK):
            ix = [slice(None)] * out.ndim
            ix[eje] = slice(i, min(i + CHUNK, len(scan)))
            out[tuple(ix)] = _seleccionar(var, scan[i:i + CHUNK], ground[i:i + CHUNK])
    # Los atributos de cuantización/packing se aplican DESPUÉS de escribir
    # valores crudos; nunca se vuelve a cuantizar ni a empaquetar la fuente.
    out.setncatts(attrs)
    return out


def _matriz(var, *, corners=False):
    var.set_auto_maskandscale(True)
    var.set_auto_chartostring(False)
    dims = var.dimensions
    if not ESPACIALES.issubset(dims):
        raise ValueError(f"{var.name}: faltan dimensiones espaciales")
    datos = np.ma.asarray(var[:])
    datos = np.moveaxis(datos, (dims.index("scanline"), dims.index("ground_pixel")), (0, 1))
    restantes = [d for d in dims if d not in ESPACIALES]
    for eje in range(len(restantes) - 1, -1, -1):
        if restantes[eje] == "time" and datos.shape[eje + 2] == 1:
            datos = np.take(datos, 0, axis=eje + 2)
    esperado = 3 if corners else 2
    if datos.ndim != esperado or (corners and datos.shape[-1] < 3):
        raise ValueError(f"{var.name}: dimensiones no soportadas {dims}")
    return np.asarray(np.ma.filled(datos.astype(float), np.nan))


def _partes(geom):
    if geom is None or geom.is_empty:
        return
    if geom.geom_type == "Polygon":
        yield geom
    elif hasattr(geom, "geoms"):
        for g in geom.geoms:
            yield from _partes(g)


def _mascara(path):
    import geopandas as gpd
    import shapely
    frame = gpd.read_file(path).to_crs("EPSG:4326")
    if "cod_comuna" not in frame:
        raise ValueError("máscara sin cod_comuna")
    geoms, codes, aois = [], [], []
    for code, geom in zip(frame.cod_comuna, frame.geometry):
        if not np.isfinite(float(code)) or int(code) != float(code) or int(code) < 0:
            raise ValueError("código comunal inválido")
        for part in _partes(shapely.make_valid(geom)):
            if part.bounds[3] <= -60:  # Antártica excluida; no corta Chile habitado.
                continue
            part = shapely.intersection(part, shapely.box(-180, -60, 180, 90))
            for p in _partes(part):
                name = ("juan_fernandez" if p.centroid.y < -30 else "desventuradas") if int(code) == 5104 else (("rapa_nui" if p.centroid.x < -107 else "sala_y_gomez") if int(code) == 5201 else "continente")
                geoms.append(p)
                codes.append(int(code))
                aois.append(name)
    if not geoms:
        raise ValueError("máscara chilena vacía")
    unions = {a: shapely.union_all([g for g, b in zip(geoms, aois) if b == a]) for a in sorted(set(aois))}
    return np.asarray(geoms, dtype=object), np.asarray(codes, dtype="i4"), unions


@lru_cache(maxsize=2)
def _mascara_preparada(ruta_resuelta, mascara_sha):
    """Caché privado por proceso; identidad de todos los componentes de máscara."""
    import shapely
    path = Path(ruta_resuelta)
    if _sha_mascara(path) != mascara_sha:
        raise ValueError("máscara cambió antes de construir caché")
    geoms, codes, unions = _mascara(path)
    total = shapely.union_all(list(unions.values()))
    shapely.prepare(total)
    for union in unions.values():
        shapely.prepare(union)
    if _sha_mascara(path) != mascara_sha:
        raise ValueError("máscara cambió al construir caché")
    geoms.flags.writeable = False
    codes.flags.writeable = False
    return geoms, codes, MappingProxyType(unions), total


def _seleccion_geografica(ds, comunas, mascara_sha=None):
    import shapely
    p = ds["PRODUCT"]
    try:
        geo = p["SUPPORT_DATA"]["GEOLOCATIONS"]
        la, lo = _matriz(p["latitude"]), _matriz(p["longitude"])
        lb, lob = _matriz(geo["latitude_bounds"], corners=True), _matriz(geo["longitude_bounds"], corners=True)
    except (KeyError, IndexError) as exc:
        raise ValueError("geolocalización y bounds nativos obligatorios") from exc
    if la.shape != lo.shape or lb.shape != lob.shape or lb.shape[:2] != la.shape:
        raise ValueError("geolocalización/bounds inconsistentes")
    key = (str(Path(comunas).resolve()), mascara_sha or _sha_mascara(comunas))
    geoms, codes, unions, union_total = _mascara_preparada(*key)
    centro_valido = np.isfinite(la) & np.isfinite(lo) & (np.abs(la) <= 90) & (np.abs(lo) <= 360)
    bounds_validos = np.all(np.isfinite(lb) & np.isfinite(lob) & (np.abs(lb) <= 90) & (np.abs(lob) <= 360), axis=-1)
    if not centro_valido.any() or not bounds_validos.any():
        raise ValueError("fuente sin geolocalización/bounds válidos; no puede declararse vacía")
    # Desenrollar cada huella alrededor de su primer vértice impide crear
    # polígonos que atraviesen Chile artificialmente al cruzar ±180 grados.
    lon = np.rad2deg(np.unwrap(np.deg2rad(lob), axis=-1))
    lon -= 360 * np.floor((np.mean(lon, axis=-1, keepdims=True) + 180) / 360)
    ancho = np.ptp(lon, axis=-1)
    alto = np.ptp(lb, axis=-1)
    bounds_validos &= (ancho <= 180) & (ancho > 0) & (alto > 0)
    if not bounds_validos.any():
        raise ValueError("ninguna huella interpretable")
    xmin, xmax, ymin, ymax = lon.min(axis=-1), lon.max(axis=-1), lb.min(axis=-1), lb.max(axis=-1)
    candidatos = np.zeros(la.shape, dtype=bool)
    centro_en_bbox = np.zeros(la.shape, dtype=bool)
    lo_norm = (lo + 180) % 360 - 180
    for union in unions.values():
        x0, y0, x1, y1 = union.bounds
        candidatos |= bounds_validos & (xmax >= x0) & (xmin <= x1) & (ymax >= y0) & (ymin <= y1)
        # La vecindad de riesgo para bounds corruptos se deriva de huellas
        # observadas; NO es un margen que recorte o excluya huellas válidas.
        dx = float(np.max((xmax - xmin)[bounds_validos]))
        dy = float(np.max((ymax - ymin)[bounds_validos]))
        centro_en_bbox |= centro_valido & (lo_norm >= x0-dx) & (lo_norm <= x1+dx) & (la >= y0-dy) & (la <= y1+dy)
    # Cualquier observación candidata con bounds incompletos es ambigua. No
    # inventar una huella a partir del centro, ni declararla vacía.
    sospechosos = centro_en_bbox & ~bounds_validos
    for union in unions.values():
        x0, y0, x1, y1 = union.bounds
        vertice_chileno = np.any(np.isfinite(lb) & np.isfinite(lon) & (lon >= x0) & (lon <= x1) & (lb >= y0) & (lb <= y1), axis=-1)
        sospechosos |= ~bounds_validos & vertice_chileno
    if sospechosos.any():
        raise ValueError("candidato chileno con bounds inválidos; fuente preservada")
    si, gi = np.nonzero(candidatos)
    coords = np.stack([lon[si, gi], lb[si, gi]], axis=-1)
    polygons = shapely.make_valid(shapely.polygons(coords)) if len(si) else np.empty(0, dtype=object)
    if len(polygons) and np.any(shapely.area(polygons) <= 0):
        raise ValueError("huella candidata degenerada, sin área geográfica")
    # Índice exacto cacheado, sin simplificar costa; primer argumento preparado.
    toca = shapely.intersects(union_total, polygons)
    si, gi, polygons = si[toca], gi[toca], polygons[toca]
    if len(si) and not centro_valido[si, gi].all():
        raise ValueError("huella chilena sin centro geolocalizado válido")
    cod = np.full(len(si), -1, dtype="i4")
    if len(si):
        puntos = shapely.points(lo_norm[si, gi], la[si, gi])
        pairs = shapely.STRtree(geoms).query(puntos, predicate="intersects")
        # Determinista: código 0 prevalece; otro solape escoge código máximo.
        for idx, code in sorted(zip(pairs[0], codes[pairs[1]]), key=lambda x: (x[0], x[1] == 0, x[1])):
            cod[idx] = code
    counts = {}
    for a, union in unions.items():
        counts[a] = int(np.count_nonzero(shapely.intersects(union, polygons)))
    return si.astype("i8"), gi.astype("i8"), cod, {
        "pixeles_fuente": int(la.size), "scanlines_fuente": int(la.shape[0]),
        "ground_pixels_fuente": int(la.shape[1]), "geolocalizaciones_invalidas": int((~centro_valido).sum()),
        "huellas_invalidas": int((~bounds_validos).sum()), "candidatos_bbox": int(candidatos.sum()),
        "aois_con_pixeles": counts, "metodo": "bounds nativos; make_valid; intersects unión comunal; sin Antártica",
        "latitude_min": float(la[si, gi].min()) if len(si) else None,
        "latitude_max": float(la[si, gi].max()) if len(si) else None,
        "longitude_min": float(lo_norm[si, gi].min()) if len(si) else None,
        "longitude_max": float(lo_norm[si, gi].max()) if len(si) else None,
        "filtro_qa": "ninguno", "interpolacion_temporal": "ninguna",
    }


def _source_id(ds, src):
    return str(ds.getncattr("id")) if "id" in ds.ncattrs() else src.name


def _orbit(ds, src):
    for key in ("orbit", "orbit_number", "orbitNumber"):
        if key in ds.ncattrs():
            value = int(ds.getncattr(key))
            if value >= 0:
                return value
    match = re.search(r"_(\d{5})_\d{2}_\d{6}_", _source_id(ds, src))
    if match:
        return int(match.group(1))
    raise ValueError("fuente sin órbita identificable")


def _utc(text):
    value = datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _valor_tiempo(var, scan, ground):
    return np.asarray(_raw(var)[...]) if scan is None else _seleccionar(var, scan, ground)


def _numerico_tiempo(var, scan, ground):
    raw = _valor_tiempo(var, scan, ground)
    a = np.ma.masked_invalid(np.ma.asarray(raw, dtype="f8"))
    for attr in ("_FillValue", "missing_value"):
        if attr in var.ncattrs():
            for value in np.asarray(var.getncattr(attr)).flat:
                a = np.ma.masked_where(raw == value, a)
    return a * getattr(var, "scale_factor", 1) + getattr(var, "add_offset", 0)


def _tiempo_cf(ds, n, scan, ground):
    """Resuelve referencia y desplazamiento UNA vez, manteniendo pares nativos."""
    p = ds["PRODUCT"]
    base, delta = p["time"], p["delta_time"]
    if "units" not in base.ncattrs() or "units" not in delta.ncattrs():
        raise ValueError("faltan unidades para resolver tiempo CF")
    calendar = getattr(base, "calendar", "standard")
    if calendar not in {"standard", "gregorian", "proleptic_gregorian"} or getattr(delta, "calendar", calendar) != calendar:
        raise ValueError("calendario temporal no compatible con UTC")
    def decode(values, units):
        result = netCDF4.num2date(values, units, calendar=calendar,
                                 only_use_cftime_datetimes=False, only_use_python_datetimes=True)
        return [_utc(x.isoformat()) for x in np.asarray(result, dtype=object).flat]
    base_value = _numerico_tiempo(base, None, None).reshape(-1)
    if len(base_value) != 1 or np.ma.getmaskarray(base_value).any():
        raise ValueError("referencia time ausente/ambigua")
    reference = decode(base_value, base.units)[0]
    if "time_reference" in ds.ncattrs() and _utc(ds.time_reference) != reference:
        raise ValueError("time y time_reference no coinciden")
    values = _numerico_tiempo(delta, scan, ground).reshape(-1)
    if len(values) != n or np.ma.getmaskarray(values).any():
        raise ValueError("delta_time inválido para píxeles seleccionados")
    units = str(delta.units).strip()
    if " since " in units.lower():
        origin = decode([0], units)[0]
        if origin != reference:
            raise ValueError("epoch CF delta_time distinto a time/time_reference")
        result = decode(values, units)
        method = "delta_time CF directo; epoch contrastado con time/time_reference; referencia no sumada otra vez"
    else:
        factors = {"ms": 0.001, "millisecond": 0.001, "milliseconds": 0.001,
                   "s": 1., "second": 1., "seconds": 1.,
                   "us": 0.000001, "microsecond": 0.000001, "microseconds": 0.000001}
        if units.lower() not in factors:
            raise ValueError("unidades delta_time no interpretables")
        result = [reference + timedelta(seconds=float(x) * factors[units.lower()]) for x in values]
        method = "time CF + delta_time con unidades de duración; sin interpolación"
    return result, {"method": method, "time_units": str(base.units),
                    "delta_time_units": units, "calendar": calendar,
                    "time_reference_utc": reference.isoformat().replace("+00:00", "Z")}


def _resolver_tiempo(ds, n, scan=None, ground=None):
    """Prefiere time_utc; sólo resuelve faltantes mediante referencia CF nativa."""
    p = ds["PRODUCT"]
    text = np.full(n, "", dtype=object)
    if "time_utc" in p.variables:
        values = _valor_tiempo(p["time_utc"], scan, ground)
        if values.dtype.kind == "S" and values.dtype.itemsize == 1 and values.ndim:
            values = netCDF4.chartostring(values)
        if values.size != n:
            raise ValueError("time_utc no corresponde a un tiempo por píxel")
        text[:] = [str(x.decode() if isinstance(x, bytes) else x).strip("\x00 ") for x in values.flat]
    missing = np.array([not x for x in text], dtype=bool)
    native = [_utc(x) if x else None for x in text]
    info = {"original_time_utc_pixels": int((~missing).sum()), "resolved_cf_pixels": int(missing.sum()),
            "method": "time_utc original; delta_time nunca se suma al texto UTC",
            "source_variables": "/PRODUCT/time_utc; /PRODUCT/time; /PRODUCT/delta_time; root/time_reference",
            "cf_comparison": "no requerida: time_utc completo y referencia CF no disponible"}
    # La CF se exige para vacíos. Si ambas referencias están presentes también
    # se contrastan: no ocultar referencias contradictorias detrás del texto.
    has_cf = all("units" in p[name].ncattrs() for name in ("time", "delta_time"))
    if n and (missing.any() or has_cf):
        derived, cf = _tiempo_cf(ds, n, scan, ground)
        differences = [abs((a-b).total_seconds()) for a, b in zip(native, derived) if a is not None]
        maximum = max(differences, default=0.)
        if maximum > 0.001:
            raise ValueError("time_utc contradice tiempo CF por más de 1 ms")
        info.update({"cf": cf, "cf_comparison": "contraste directo, sin doble suma",
                     "maximum_existing_cf_difference_seconds": maximum})
        for i in np.flatnonzero(missing):
            text[i] = derived[i].isoformat(timespec="microseconds").replace("+00:00", "Z")
        if missing.any():
            info["method"] = cf["method"] if missing.all() else "mixto: time_utc original + faltantes resueltos por CF"
    return text, info


def _requeridas(ds, gas):
    if gas not in PRINCIPALES:
        raise ValueError(f"gas no admitido: {gas}")
    try:
        p = ds["PRODUCT"]
    except (KeyError, IndexError) as exc:
        raise ValueError("falta PRODUCT") from exc
    required = {PRINCIPALES[gas], PRINCIPALES[gas] + "_precision", "qa_value", "latitude", "longitude", "time", "delta_time"}
    missing = required - set(p.variables)
    if missing:
        raise ValueError(f"{gas}: variables obligatorias ausentes {sorted(missing)}")
    for name in (PRINCIPALES[gas], PRINCIPALES[gas] + "_precision", "qa_value"):
        dims = set(p[name].dimensions)
        if not (ESPACIALES.issubset(dims) or "pixel" in dims):
            raise ValueError(f"{name}: no depende de píxeles nativos")
    for name in ("time_utc", "delta_time"):
        if name not in p.variables:
            continue
        if not {"scanline", "pixel"}.intersection(p[name].dimensions):
            raise ValueError(f"{name}: no depende de scanline/pixel")


def crear_subset(src: Path, out: Path, gas: str, comunas: Path, mascara_sha: str) -> dict:
    """Crea out exclusivamente; ante fallo conserva fuente y salida incompleta."""
    src, out, comunas = Path(src), Path(out), Path(comunas)
    if out.exists() or out.is_symlink() or src.resolve() == out.resolve():
        raise FileExistsError(f"no se reemplaza salida existente: {out}")
    if _sha_mascara(comunas) != mascara_sha:
        raise ValueError("hash de máscara no coincide")
    stat = src.stat()
    with netCDF4.Dataset(src, "r") as ds:
        _requeridas(ds, gas)
        scan, ground, cod, cobertura = _seleccion_geografica(ds, comunas, mascara_sha)
        orbit = _orbit(ds, src)
        source_id = _source_id(ds, src)
        tiempos, tiempo_info = _resolver_tiempo(ds, len(scan), scan, ground)
        cobertura.update({"time_utc_first": min(tiempos, key=_utc) if len(tiempos) else None,
                          "time_utc_last": max(tiempos, key=_utc) if len(tiempos) else None,
                          "time_semantics": tiempo_info["method"], "time_resolution": tiempo_info})
        if cobertura["ground_pixels_fuente"] >= 10000 or cobertura["scanlines_fuente"] >= 1000000 or orbit >= 1000000000:
            raise ValueError("índices fuera del contrato pixel_id")
        if any("pixel" in g.dimensions for g in _grupos(ds)):
            raise ValueError("dimensión pixel preexistente incompatible")
        contract = {"variables": {}, "group_attrs": {}, "source_root_attrs": _attrs_hash(ds, root=True)}
        with netCDF4.Dataset(out, "w", format="NETCDF4", clobber=False) as dst:
            dst.setncatts({a: ds.getncattr(a) for a in ds.ncattrs()})
            dst.createDimension("pixel", len(scan))
            def copy_dims(source, target):
                for name, dim in source.dimensions.items():
                    if name not in ESPACIALES:
                        # Subset inmutable: mantiene longitud de los ejes aun
                        # con cero píxeles y ejes originalmente unlimited.
                        target.createDimension(name, len(dim))
            copy_dims(ds, dst)
            def copy_group(source, target):
                copy_dims(source, target)
                target.setncatts({a: source.getncattr(a) for a in source.ncattrs()})
                contract["group_attrs"][source.path] = _attrs_hash(source)
                for name, var in source.variables.items():
                    copied = _copiar_variable(var, target, scan, ground)
                    expected = _hash_inicio(copied)
                    if "pixel" in copied.dimensions:
                        for i in range(0, len(scan), CHUNK):
                            _actualizar_hash(expected, _seleccionar(var, scan[i:i + CHUNK], ground[i:i + CHUNK]))
                    else:
                        _actualizar_hash(expected, _seleccionar(var, scan, ground))
                    contract["variables"][f"{source.path}/{name}"] = {
                        "source_dimensions": list(var.dimensions), "dimensions": list(copied.dimensions),
                        "shape": list(copied.shape), "dtype": str(copied.dtype),
                        "raw_selected_sha256": expected.hexdigest(), "attrs_sha256": _attrs_hash(var),
                    }
                for name, child in source.groups.items():
                    copy_group(child, target.createGroup(name))
            copy_group(ds["PRODUCT"], dst.createGroup("PRODUCT"))
            sub = dst.createGroup("CHILE_SUBSET")
            resolved = sub.createVariable("observation_time_utc", str, ("pixel",))
            resolved[:] = tiempos
            resolved.setncatts({"long_name": "Native observation time resolved without changing PRODUCT",
                               "method": tiempo_info["method"], "provenance": json.dumps(tiempo_info, sort_keys=True),
                               "source_granule": source_id})
            ids = orbit * np.int64(10000000000) + scan * 10000 + ground
            for name, dtype, values in (
                ("source_scanline_index", "i8", scan), ("source_ground_pixel_index", "i8", ground),
                ("pixel_id", "i8", ids), ("cod_comuna", "i4", cod),
                ("toca_chile", "u1", np.ones(len(scan), dtype="u1")),
                ("dentro_chile_centro", "u1", (cod >= 0).astype("u1")),
            ):
                v = sub.createVariable(name, dtype, ("pixel",), fill_value=False, zlib=True)
                v[:] = values
            sub.setncatts({"gas": gas, "source_granule": source_id, "orbit": orbit,
                           "mascara_sha256": mascara_sha, "outside_center_code": -1,
                           "zone_without_demarcation_code": 0,
                           "pixel_id_formula": "orbit*10000000000 + source_scanline_index*10000 + source_ground_pixel_index",
                           "pixel_id_scope": "gas + orbit; revisiones de la misma órbita comparten ID",
                           "native_time": "time_utc y delta_time conservados separadamente; sin sumar delta_time a time_utc"})
            for name, var in sub.variables.items():
                contract["variables"][f"/CHILE_SUBSET/{name}"] = {"dimensions": list(var.dimensions), "shape": list(var.shape), "dtype": str(var.dtype), "raw_selected_sha256": _digest_variable(var), "attrs_sha256": _attrs_hash(var)}
            contract["group_attrs"][sub.path] = _attrs_hash(sub)
            dst.setncatts({PREFIJO + "schema": "airpollution.tropomi.gases.native-pixel.v1",
                           PREFIJO + "gas": gas, PREFIJO + "source": source_id,
                           PREFIJO + "source_sha256": _sha(src), PREFIJO + "mascara_sha256": mascara_sha,
                           PREFIJO + "contract": json.dumps(contract, sort_keys=True),
                           PREFIJO + "coverage": json.dumps(cobertura, sort_keys=True)})
    if (stat.st_size, stat.st_mtime_ns) != (src.stat().st_size, src.stat().st_mtime_ns):
        raise ValueError("fuente cambió durante el subset")
    # Reapertura compara TODAS las variables con sus bytes seleccionados de
    # fuente y atributos originales, antes de autorizar al llamador a publicar.
    resultado = validar_subset(out, gas, mascara_sha)
    with out.open("rb") as f:
        os.fsync(f.fileno())
    return resultado


def validar_subset(out: Path, gas: str, mascara_sha: str) -> dict:
    """Reabre, lee y verifica íntegramente datos crudos, packing y procedencia."""
    with netCDF4.Dataset(out, "r") as ds:
        _requeridas(ds, gas)
        if ds.getncattr(PREFIJO + "gas") != gas or ds.getncattr(PREFIJO + "mascara_sha256") != mascara_sha:
            raise ValueError("gas/máscara no coincide")
        contract = json.loads(ds.getncattr(PREFIJO + "contract"))
        cobertura = json.loads(ds.getncattr(PREFIJO + "coverage"))
        if _attrs_hash(ds, root=True) != contract["source_root_attrs"]:
            raise ValueError("atributos raíz originales alterados")
        actual = dict(_variables(ds["PRODUCT"]))
        actual.update(dict(_variables(ds["CHILE_SUBSET"])))
        if set(actual) != set(contract["variables"]):
            raise ValueError("inventario de variables alterado")
        if set(ds.groups) != {"PRODUCT", "CHILE_SUBSET"}:
            raise ValueError("grupos fuera del contrato")
        for path, expected in contract["variables"].items():
            var = actual[path]
            if list(var.dimensions) != expected["dimensions"] or list(var.shape) != expected["shape"] or str(var.dtype) != expected["dtype"]:
                raise ValueError(f"{path}: dimensiones/tipo alterados")
            if _attrs_hash(var) != expected["attrs_sha256"] or _digest_variable(var) != expected["raw_selected_sha256"]:
                raise ValueError(f"{path}: bytes/atributos diferentes de fuente")
        for path, expected in contract["group_attrs"].items():
            if _attrs_hash(ds[path]) != expected:
                raise ValueError(f"{path}: atributos de grupo alterados")
        sub = ds["CHILE_SUBSET"]
        resolved, time_info = _resolver_tiempo(ds, len(ds.dimensions["pixel"]))
        if "observation_time_utc" in sub.variables:
            if not np.array_equal(sub["observation_time_utc"][:], resolved):
                raise ValueError("tiempo de observación resuelto no coincide con fuente nativa")
        elif time_info["resolved_cf_pixels"]:
            raise ValueError("fuente sin time_utc completo requiere observation_time_utc")
        scan = np.asarray(sub["source_scanline_index"][:])
        gp = np.asarray(sub["source_ground_pixel_index"][:])
        ids = np.asarray(sub["pixel_id"][:])
        cod = np.asarray(sub["cod_comuna"][:])
        n = len(ds.dimensions["pixel"])
        if len(ids) != n or len(np.unique(ids)) != n or np.any(ids != int(sub.orbit) * 10000000000 + scan * 10000 + gp):
            raise ValueError("identidad nativa inválida")
        if np.any(scan < 0) or np.any(scan >= cobertura["scanlines_fuente"]) or np.any(gp < 0) or np.any(gp >= cobertura["ground_pixels_fuente"]) or np.any(cod < -1):
            raise ValueError("índices/códigos fuera de rango")
        if not np.all(np.asarray(sub["toca_chile"][:]) == 1):
            raise ValueError("píxeles fuera de máscara")
        retained = sorted(path for path in actual if path.startswith("/PRODUCT/"))
        return {"gas": gas, "pixeles_chile": n, "pixeles_fuente": cobertura["pixeles_fuente"],
                "variables_conservadas": retained, "conteo_variables": len(retained),
                "mascara_sha256": mascara_sha, "cobertura_nativa": cobertura,
                "source_granule": ds.getncattr(PREFIJO + "source"),
                "source_sha256": ds.getncattr(PREFIJO + "source_sha256"),
                "validacion": "todas las variables reabiertas: bytes crudos, atributos y ejes contra selección fuente"}
