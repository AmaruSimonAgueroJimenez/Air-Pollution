#!/usr/bin/env python3
"""Derivado mensual inmutable de TP ERA5-Land; jamás modifica/retira fuentes.

Ejemplo: python3 -B scripts_pipeline/preparar_era5land_modelado.py --mes 2000-02
API: preparar_mes(mes, origen=ORIGEN, destino=DESTINO, comunas=COMUNAS).
Sólo acepta el contrato nativo local del endpoint reanalysis-era5-land.
"""
from __future__ import annotations

import argparse
import calendar
import ctypes
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import uuid

import cftime._cftime
import netCDF4
import netCDF4._netCDF4
import numpy as np
import numpy._core._multiarray_umath

REPO = Path(__file__).resolve().parents[1]
RAIZ = Path('/Volumes/Datos/Asesorias_Data/AirPollution')
ORIGEN = RAIZ / 'data/contaminantes/ERA5Land/chile_nativo_01deg'
DESTINO = RAIZ / 'derived/modelado/ERA5Land/v1'
COMUNAS = RAIZ / 'data/comunas.shp'
DISCO = Path('/Volumes/Datos')
UUID_DISCO = '54B3D309-A503-44C6-9229-581F3E4FECE3'
RESERVA_BYTES = 100 * 1024**3
CONTRATO_PREVIO = REPO / 'logs/metadatos_era5land_pendientes_20260914.json'
NORMALIZADOR_SHA = '843e25a1239b2ed2f15ab25c96016bd39908523f5dfa37cb055d92f2377b091f'
TIME_UNITS = 'seconds since 1970-01-01 00:00:00 UTC'
COORDS = ('pixel_id', 'latitude', 'longitude', 'lat_index_global',
          'lon_index_global', 'cod_comuna', 'latitude_longitude')
CURRENT_MISSING, PREDECESSOR_MISSING, TEMPORAL_GAP, NEGATIVE = 1, 2, 4, 8
FLAGS = 'current_missing predecessor_missing temporal_gap negative_increment'
S1 = 'https://confluence.ecmwf.int/pages/viewpage.action?pageId=140385202'
S2 = 'https://confluence.ecmwf.int/pages/viewpage.action?pageId=197702790'
S3 = ('https://confluence.ecmwf.int/spaces/UDOC/pages/208501579/'
      'Why+are+there+sometimes+small+negative+precipitation+accumulations+-+ecCodes+GRIB+FAQ')
CONTRATO = {
    'schema': 'airpollution.era5land.modelado.v1',
    'dataset': 'reanalysis-era5-land',
    'excluded_dataset': 'reanalysis-era5-land-timeseries',
    'native_time': 'instantaneous variables at native UTC valid time',
    'tp_native': 'm water equivalent accumulated from daily forecast 00 UTC; valid 00 is previous-day step 24',
    'formula': '1000*A(t) at 01 UTC; otherwise 1000*(A(t)-A(t-1h)), including 00 UTC',
    'derived_variable': 'tp_1h_mm', 'units': 'mm',
    'interval': '(t-3600 seconds,t]; timestamp t is interval end UTC',
    'negative_policy': 'retain signed increments, flag every finite negative; no clipping/tolerance',
    'missing_policy': 'NaN with flags; no interpolation, no zero imputation',
    'precision': 'float64 arithmetic from native stored values; original float32 is not recovered to higher precision',
    'spatial_operation': 'none; identical native pixels and commune labels, no aggregation',
    'references': [S1, S2, S3,
        'https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land?tab=overview'],
    'metadata_overlay': {
        't2m': {'units': 'K', 'param_id': 167, 'temporal_kind': 'instantaneous'},
        'd2m': {'units': 'K', 'param_id': 168, 'temporal_kind': 'instantaneous'},
        'u10': {'units': 'm s-1', 'param_id': 165, 'temporal_kind': 'instantaneous'},
        'v10': {'units': 'm s-1', 'param_id': 166, 'temporal_kind': 'instantaneous'},
        'sp': {'units': 'Pa', 'param_id': 134, 'temporal_kind': 'instantaneous'},
        'tp': {'units': 'm', 'param_id': 228, 'temporal_kind': 'forecast_accumulation'},
    },
    'overlay_evidence': 'Official documentation plus declared source endpoint; not retroactively observed attributes or independently proven historical provenance. Native files are unchanged.',
}


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024**2), b''):
            h.update(block)
    return h.hexdigest()


def _record(path, expected=None):
    path = Path(path).resolve(strict=True)
    value = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha256(path)}
    if expected is not None and value['sha256'] != expected:
        raise ValueError(f'Hash de fuente incompatible: {path}')
    return value


def _verify(records):
    for rec in records:
        if _record(rec['path']) != rec:
            raise ValueError(f'Fuente cambió: {rec["path"]}')


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _fsync(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _mkdir_durable(path):
    path = Path(path)
    missing = []
    parent = path
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for item in reversed(missing):
        item.mkdir(exist_ok=True)
        _fsync(item); _fsync(item.parent)


def _write_new(path, data):
    with Path(path).open('xb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def _publish(stage, final):
    """Darwin RENAME_EXCL: renombrado atómico que NO reemplaza ni un directorio vacío."""
    libc = ctypes.CDLL(None, use_errno=True)
    rename = libc.renamex_np  # Fail closed on unsupported platforms; this CLI targets the Mac.
    rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(os.fsencode(stage), os.fsencode(final), 0x00000004) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(final))


def _event(wal, phase, **fields):
    with Path(wal).open('ab') as f:
        f.write(_json({'utc': _utc(), 'phase': phase, **fields}) + b'\n')
        f.flush()
        os.fsync(f.fileno())


def _guard_disk(destino, required=0):
    """No fallback al disco interno si el externo se desconecta."""
    destino = Path(destino).resolve()
    if not destino.is_relative_to(RAIZ.resolve()) or not DISCO.is_mount():
        raise RuntimeError('Destino fuera del disco externo montado autorizado')
    info = plistlib.loads(subprocess.check_output(['diskutil', 'info', '-plist', str(DISCO)]))
    if info.get('VolumeUUID') != UUID_DISCO or info.get('MountPoint') != str(DISCO):
        raise RuntimeError('UUID/punto de montaje inesperado')
    free = shutil.disk_usage(DISCO).free
    if free - required < RESERVA_BYTES:
        raise RuntimeError('Reserva de 100 GiB insuficiente')
    return {'uuid': info['VolumeUUID'], 'free_bytes': free, 'reserve_bytes': RESERVA_BYTES,
            'estimated_additional_bytes': int(required), 'checked_utc': _utc()}


def calcular_precipitacion(tp, times, anterior=None, tiempo_anterior=None):
    """Devuelve (mm float64, flags u1). Los huecos se señalan, no se interpolan."""
    a = np.asarray(tp, dtype=np.float64)
    t = np.asarray(times)
    if a.ndim != 2 or t.ndim != 1 or len(t) != len(a) or not len(t):
        raise ValueError('Dimensiones temporales inválidas')
    if not np.issubdtype(t.dtype, np.integer) or np.any(t % 3600) or np.any(np.diff(t) <= 0):
        raise ValueError('Se requieren horas UTC enteras, únicas y crecientes')
    if anterior is not None and np.shape(anterior) != a.shape[1:]:
        raise ValueError('Antecedente espacial incompatible')
    p = np.full(a.shape, np.nan, dtype=np.float64)
    flags = np.zeros(a.shape, dtype=np.uint8)
    for i, instant in enumerate(t):
        current = np.isfinite(a[i])
        flags[i, ~current] |= CURRENT_MISSING
        if (int(instant) // 3600) % 24 == 1:
            p[i, current] = a[i, current] * 1000.0
            continue
        previous = a[i-1] if i else anterior
        previous_time = t[i-1] if i else tiempo_anterior
        if previous is None or previous_time is None or int(instant) - int(previous_time) != 3600:
            flags[i] |= PREDECESSOR_MISSING | TEMPORAL_GAP
            continue
        previous = np.asarray(previous, dtype=np.float64)
        finite_previous = np.isfinite(previous)
        flags[i, ~finite_previous] |= PREDECESSOR_MISSING
        ok = current & finite_previous
        p[i, ok] = (a[i, ok] - previous[ok]) * 1000.0
    flags[np.isfinite(p) & (p < 0)] |= NEGATIVE
    return p, flags


def _months(mes):
    date = datetime.strptime(mes, '%Y-%m').replace(tzinfo=timezone.utc)
    if date.strftime('%Y-%m') != mes:
        raise ValueError('Mes requiere formato YYYY-MM')
    prev = date.replace(year=date.year-1, month=12) if date.month == 1 else date.replace(month=date.month-1)
    return date, prev.strftime('%Y-%m')


def _source(origen, mes):
    manifest_path = origen / 'manifiestos' / f'era5land_{mes.replace("-", "")}.json'
    man = json.loads(manifest_path.read_text())
    if man['periodo'] != mes or man['descarga_cds']['dataset'] != CONTRATO['dataset']:
        raise ValueError('Periodo/endpoint no admitido; no des-acumular producto time-series')
    if man['software']['motor_normalizacion_sha256'] != NORMALIZADOR_SHA:
        raise ValueError('Motor nativo no auditado para este contrato')
    path = origen / 'mensual' / f'era5land_{mes.replace("-", "")}_chile_pixeles.nc'
    if Path(man['salida']['archivo']).resolve() != path.resolve():
        raise ValueError('Ruta nativa difiere del manifiesto')
    return {'mes': mes, 'native': _record(path, man['salida']['sha256']),
            'manifest': _record(manifest_path), 'catalog_sha256': man['catalogo']['sha256']}


def _inventory(origen, mes, comunas):
    _, prev_mes = _months(mes)
    current = _source(origen, mes)
    prev_path = origen / 'mensual' / f'era5land_{prev_mes.replace("-", "")}_chile_pixeles.nc'
    prev_manifest = origen / 'manifiestos' / f'era5land_{prev_mes.replace("-", "")}.json'
    if prev_path.exists() != prev_manifest.exists():
        raise ValueError('Antecedente incompleto: archivo/manifiesto no están ambos presentes')
    previous = _source(origen, prev_mes) if prev_path.exists() else None
    catalog_manifest = origen / 'metadata/catalogo_manifest.json'
    cm = json.loads(catalog_manifest.read_text())
    catalog_sha = cm['catalogo']['sha256']
    if current['catalog_sha256'] != catalog_sha or (previous and previous['catalog_sha256'] != catalog_sha):
        raise ValueError('Catálogos de meses incompatibles')
    records = [_record(catalog_manifest)]
    for field in ('catalogo', 'relacion_pixel_comuna'):
        records.append(_record(origen / cm[field]['archivo'], cm[field]['sha256']))
    for name, component in cm['mascara']['componentes'].items():
        record = _record(comunas.parent / name, component['sha256'])
        if record['bytes'] != component['bytes']:
            raise ValueError('Tamaño de máscara incompatible')
        records.append(record)
    records.append(_record(CONTRATO_PREVIO))
    return {'current': current, 'previous': previous, 'geometry_and_contract': records,
            'mask_components': cm['mascara']['componentes'],
            'catalog_sha256': catalog_sha,
            'pixel_commune_relation_sha256': cm['relacion_pixel_comuna']['sha256']}


def _records(inventory):
    values = list(inventory['geometry_and_contract'])
    for key in ('current', 'previous'):
        if inventory[key]:
            values += [inventory[key]['native'], inventory[key]['manifest']]
    return values


def _read_native(source):
    with netCDF4.Dataset(source['native']['path']) as ds:
        ds.set_auto_maskandscale(False)
        if ds.temporal_operation != 'none; exact native UTC hours' or float(ds.spatial_resolution_degrees) != 0.1:
            raise ValueError('Operación temporal/grilla fuente no admitida')
        if ds.catalog_sha256 != source['catalog_sha256']:
            raise ValueError('Catálogo interno distinto')
        tv = ds['time']
        if tv.dtype != np.dtype('int64') or tv.dimensions != ('time',) or tv.units != TIME_UNITS or tv.calendar != 'proleptic_gregorian':
            raise ValueError('Convención temporal nativa inesperada')
        t = np.array(tv[:], dtype=np.int64)
        date, _ = _months(source['mes'])
        maximum = calendar.monthrange(date.year, date.month)[1] * 24
        if not 1 <= len(t) <= maximum or not np.array_equal(t, int(date.timestamp()) + np.arange(len(t))*3600):
            raise ValueError('Mes no comienza a 00 UTC o no es horario continuo')
        units = {}
        for name, contract in CONTRATO['metadata_overlay'].items():
            v = ds[name]
            if v.dimensions != ('time', 'pixel') or v.dtype != np.dtype('float32'):
                raise ValueError(f'Esquema no nativo: {name}')
            observed = getattr(v, 'units', None)
            accepted = {contract['units'], contract['units'].replace(' s-1', ' s**-1')}
            if observed is not None and observed not in accepted:
                raise ValueError(f'Unidades incompatibles: {name}: {observed}')
            if 'scale_factor' in v.ncattrs() or 'add_offset' in v.ncattrs():
                raise ValueError('Empaquetamiento no contemplado en contrato nativo')
            units[name] = {**contract, 'observed_units': observed,
                'source_variable_names': getattr(v, 'source_variable_names', None),
                'evidence_status': 'observed_compatible' if observed else 'inferred_from_declared_endpoint_only'}
        coords = {name: np.array(ds[name][...]) for name in COORDS}
        coord_attrs = {name: {k: ds[name].getncattr(k) for k in ds[name].ncattrs() if k != '_FillValue'} for name in COORDS}
        if len(np.unique(coords['pixel_id'])) != len(coords['pixel_id']):
            raise ValueError('pixel_id repetido')
        tp = np.array(ds['tp'][:], dtype=np.float64)
    return {'time': t, 'tp': tp, 'coords': coords, 'coord_attrs': coord_attrs, 'overlay': units}


def _inputs(inventory):
    data = _read_native(inventory['current'])
    previous, previous_time = None, None
    if inventory['previous']:
        prior = _read_native(inventory['previous'])
        a, b = data['coords']['pixel_id'], prior['coords']['pixel_id']
        lookup = {int(value): i for i, value in enumerate(b)}
        if set(map(int, a)) != set(lookup):
            raise ValueError('Conjunto de píxeles del antecedente incompatible')
        order = np.array([lookup[int(value)] for value in a])
        for name in COORDS:
            left, right = data['coords'][name], prior['coords'][name]
            if right.ndim:
                right = right[order]
            if not np.array_equal(left, right, equal_nan=True):
                raise ValueError(f'Coordenada antecedente incompatible: {name}')
        previous, previous_time = prior['tp'][-1, order], int(prior['time'][-1])
    values, flags = calcular_precipitacion(data['tp'], data['time'], previous, previous_time)
    return data, values, flags


def _stats(data, values, flags):
    finite = np.isfinite(values)
    cycles = 0
    # La suma de intervalos de cada ciclo completo conserva el acumulado nativo.
    for i in np.where((data['time'] // 3600) % 24 == 1)[0]:
        if i + 23 >= len(values):
            continue
        complete = np.isfinite(values[i:i+24]).all(axis=0) & np.isfinite(data['tp'][i+23])
        expected = 1000.0 * data['tp'][i+23, complete]
        actual = values[i:i+24, complete].sum(axis=0)
        if not np.allclose(actual, expected, rtol=1e-12, atol=1e-12):
            raise ValueError('No conserva precipitación por ciclo completo')
        cycles += int(complete.sum())
    return {'hours': len(values), 'pixels': values.shape[1], 'values': int(values.size),
        'finite': int(finite.sum()), 'nan': int((~finite).sum()),
        'negative': int(((flags & NEGATIVE) != 0).sum()),
        'current_missing': int(((flags & CURRENT_MISSING) != 0).sum()),
        'predecessor_missing': int(((flags & PREDECESSOR_MISSING) != 0).sum()),
        'temporal_gap': int(((flags & TEMPORAL_GAP) != 0).sum()),
        'minimum_mm': float(values[finite].min()) if finite.any() else None,
        'maximum_mm': float(values[finite].max()) if finite.any() else None,
        'conserved_complete_pixel_cycles': cycles,
        'first_interval_end_utc': datetime.fromtimestamp(int(data['time'][0]), timezone.utc).isoformat(),
        'last_interval_end_utc': datetime.fromtimestamp(int(data['time'][-1]), timezone.utc).isoformat()}


def _write_nc(path, data, values, flags, revision, inventory):
    with netCDF4.Dataset(path, 'w', format='NETCDF4', clobber=False) as ds:
        ds.createDimension('time', len(values)); ds.createDimension('pixel', values.shape[1]); ds.createDimension('bounds', 2)
        ds.setncatts({'Conventions': 'CF-1.10', 'title': 'ERA5-Land precipitación incremental horaria derivada',
            'revision_sha256': revision, 'contract_sha256': hashlib.sha256(_json(CONTRATO)).hexdigest(),
            'source_sha256': inventory['current']['native']['sha256'],
            'catalog_sha256': inventory['catalog_sha256'], 'interval_convention': CONTRATO['interval'],
            'negative_policy': CONTRATO['negative_policy'], 'spatial_operation': CONTRATO['spatial_operation']})
        t = ds.createVariable('time', 'i8', ('time',)); t[:] = data['time']
        t.setncatts({'units': TIME_UNITS, 'calendar': 'proleptic_gregorian', 'standard_name': 'time', 'bounds': 'time_bounds', 'long_name': 'UTC interval end'})
        bounds = ds.createVariable('time_bounds', 'i8', ('time', 'bounds'))
        bounds[:] = np.column_stack((data['time']-3600, data['time']))
        bounds.setncatts({'units': TIME_UNITS, 'calendar': 'proleptic_gregorian'})
        for name, array in data['coords'].items():
            v = ds.createVariable(name, array.dtype, ('pixel',) if array.ndim else ())
            v[...] = array; v.setncatts(data['coord_attrs'][name])
        p = ds.createVariable('tp_1h_mm', 'f8', ('time', 'pixel'), fill_value=np.nan,
            zlib=True, complevel=4, shuffle=True, chunksizes=(min(168, len(values)), min(2048, values.shape[1])))
        p[:] = values
        p.setncatts({'units': 'mm', 'long_name': 'Precipitation water equivalent during preceding one-hour interval',
            'cell_methods': 'time: sum', 'coordinates': 'time latitude longitude', 'grid_mapping': 'latitude_longitude',
            'ancillary_variables': 'tp_1h_flags', 'comment': CONTRATO['formula']})
        q = ds.createVariable('tp_1h_flags', 'u1', ('time', 'pixel'), fill_value=False, zlib=True, complevel=4)
        q[:] = flags
        q.setncatts({'flag_masks': np.array([1, 2, 4, 8], dtype='u1'), 'flag_meanings': FLAGS,
                    'long_name': 'Non-destructive precipitation derivation diagnostics; zero means no flag'})
    _fsync(path)


def _validate_nc(path, data, values, flags, revision):
    with netCDF4.Dataset(path) as ds:
        ds.set_auto_maskandscale(False)
        if ds.revision_sha256 != revision or ds.contract_sha256 != hashlib.sha256(_json(CONTRATO)).hexdigest():
            raise ValueError('Identidad del derivado incompatible')
        expected = {'time': data['time'], 'time_bounds': np.column_stack((data['time']-3600, data['time'])),
                    **data['coords'], 'tp_1h_mm': values, 'tp_1h_flags': flags}
        if set(ds.variables) != set(expected):
            raise ValueError('Variables inesperadas/ausentes')
        for name, array in expected.items():
            actual = np.array(ds[name][...])  # Forzar lectura integral, no sólo muestras.
            if actual.dtype != array.dtype or not np.array_equal(actual, array, equal_nan=True):
                raise ValueError(f'Derivado/coord difiere de fuente o fórmula: {name}')
        if ds['tp_1h_mm'].units != 'mm' or ds['time'].bounds != 'time_bounds' or ds['tp_1h_flags'].flag_meanings != FLAGS:
            raise ValueError('Metadatos temporales/unidades/flags incompatibles')
    return _stats(data, values, flags)


def _dependencies():
    return {'python': platform.python_version(), 'platform': platform.platform(),
        **{name: importlib.metadata.version(name) for name in ('numpy', 'netCDF4', 'cftime')},
        'libnetcdf': netCDF4.__netcdf4libversion__, 'hdf5': netCDF4.__hdf5libversion__,
        'selected_compiled_modules': [_record(module.__file__) for module in
            (netCDF4._netCDF4, numpy._core._multiarray_umath, cftime._cftime)],
        'binary_fingerprint_scope': 'These three loaded extension modules only, not a complete vendored environment'}


def validar_producto(directory):
    """Reabre todas las variables; revalida hashes de fuentes y fórmula completa."""
    directory = Path(directory)
    m = json.loads((directory / 'manifest.json').read_text())
    if m['contract'] != CONTRATO or hashlib.sha256(_json(m['identity'])).hexdigest() != m['revision']:
        raise ValueError('Identidad/contrato del manifiesto inválido')
    _record(directory / 'preparar_era5land_modelado.py', m['identity']['code_sha256'])
    _verify(_records(m['identity']['inputs']))
    out = directory / 'tp_1h_mm.nc'
    if out.stat().st_size != m['output']['bytes']:
        raise ValueError('Tamaño del producto inválido')
    _record(out, m['output']['sha256'])
    data, values, flags = _inputs(m['identity']['inputs'])
    stats = _validate_nc(out, data, values, flags, m['revision'])
    if stats != m['validation'] or data['overlay'] != m['native_variable_metadata_overlay']:
        raise ValueError('Resumen/overlay difiere de fuentes')
    return {'directory': str(directory), 'revision': m['revision'], 'output': m['output'], 'validation': stats}


def preparar_mes(mes, origen=ORIGEN, destino=DESTINO, comunas=COMUNAS):
    """Publica una revisión nueva o revalida y reutiliza la idéntica; nunca sobrescribe.

    Los fallos conservan staging y WAL. Un fallo después de rename se recupera
    revalidando la publicación al repetir el mismo comando; no se borra nada.
    """
    _months(mes)
    origen, destino, comunas = Path(origen).resolve(), Path(destino).resolve(), Path(comunas).resolve()
    _guard_disk(destino)
    _mkdir_durable(destino)
    locks = destino / 'locks'; _mkdir_durable(locks)
    with (locks / f'{mes}.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        inventory = _inventory(origen, mes, comunas)
        code = Path(__file__).read_bytes()
        identity = {'inputs': inventory, 'contract': CONTRATO,
                    'code_sha256': hashlib.sha256(code).hexdigest(), 'dependencies': _dependencies()}
        revision = hashlib.sha256(_json(identity)).hexdigest()
        final = destino / 'meses' / mes / revision
        # Guardar evento de revalidación también cierra una publicación cuyo fsync/WAL final falló.
        wal_dir = destino / 'wal' / mes; _mkdir_durable(wal_dir)
        wal = wal_dir / f'{uuid.uuid4().hex}.jsonl'
        _write_new(wal, b''); _fsync(wal_dir)
        if final.exists():
            result = validar_producto(final)
            _fsync(final); _fsync(final.parent)
            _event(wal, 'revalidated_existing', revision=revision, directory=str(final))
            return {**result, 'status': 'reused', 'wal': str(wal)}
        data, values, flags = _inputs(inventory)
        estimate = values.nbytes + flags.nbytes + 32 * 1024**2
        disk = _guard_disk(destino, estimate)
        stage_parent = destino / 'staging'; _mkdir_durable(stage_parent)
        stage = stage_parent / f'{mes}.{uuid.uuid4().hex}'; stage.mkdir()
        _fsync(stage_parent)
        _event(wal, 'prepared', revision=revision, sources=_records(inventory), staging=str(stage), final=str(final), disk=disk)
        try:
            _write_new(stage / 'preparar_era5land_modelado.py', code)
            _write_nc(stage / 'tp_1h_mm.nc', data, values, flags, revision, inventory)
            stats = _validate_nc(stage / 'tp_1h_mm.nc', data, values, flags, revision)
            out_record = _record(stage / 'tp_1h_mm.nc')
            manifest = {'schema': CONTRATO['schema'], 'created_utc': _utc(), 'revision': revision,
                'identity': identity, 'contract': CONTRATO, 'native_variable_metadata_overlay': data['overlay'],
                'output': {k: out_record[k] for k in ('bytes', 'sha256')}, 'validation': stats,
                'originals_retained': True, 'disk_preflight': disk,
                'publication_wal': str(wal), 'original_variables_not_duplicated': list(CONTRATO['metadata_overlay'])}
            _write_new(stage / 'manifest.json', _json(manifest) + b'\n')
            _verify(_records(inventory))
            validar_producto(stage)
            _fsync(stage)
            _guard_disk(destino)
            _mkdir_durable(final.parent)
            _fsync(final.parent); _fsync(final.parent.parent)
            if final.exists():
                raise FileExistsError(final)
            _event(wal, 'validated_ready_to_publish', revision=revision, output=manifest['output'])
            _publish(stage, final)
            _fsync(final); _fsync(final.parent); _fsync(stage_parent)
            _event(wal, 'published', revision=revision, directory=str(final), output=manifest['output'])
            return {'status': 'published', 'directory': str(final), 'revision': revision,
                    'output': manifest['output'], 'validation': stats, 'wal': str(wal)}
        except BaseException as error:
            # No cleanup of potentially useful data, including failure during publication.
            try:
                _event(wal, 'failed_preserved', revision=revision, error_type=type(error).__name__,
                       staging_exists=stage.exists(), final_exists=final.exists())
            except Exception:
                pass
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mes', required=True, help='YYYY-MM; exactamente un mes por ejecución')
    parser.add_argument('--origen', type=Path, default=ORIGEN)
    parser.add_argument('--destino', type=Path, default=DESTINO)
    parser.add_argument('--comunas', type=Path, default=COMUNAS)
    args = parser.parse_args()
    print(json.dumps(preparar_mes(args.mes, args.origen, args.destino, args.comunas), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
