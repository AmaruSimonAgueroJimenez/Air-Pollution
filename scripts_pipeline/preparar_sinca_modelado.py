#!/usr/bin/env python3
"""SINCA original → Parquet versionado para modelado, sin red ni imputación.

El modo predeterminado sólo muestra el plan. --ejecutar publica derivados;
no modifica CSV, metadatos de estaciones, lectores ni manifiestos originales.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
import copy
import csv
import ctypes
from datetime import date, datetime, timezone
import hashlib
import importlib.metadata
import io
import json
import math
import os
from pathlib import Path
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import uuid
import zoneinfo

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path('/Volumes/Datos/Asesorias_Data/AirPollution/data/sinca')
DEFAULT_OUTPUT = Path('/Volumes/Datos/Asesorias_Data/AirPollution/derived/modelado/SINCA/v1')
VOLUME_UUID = '54B3D309-A503-44C6-9229-581F3E4FECE3'
CONTRACT = 'airpollution.sinca.modelado.v1.0.0'
GIB = 2 ** 30
GASES = ('pm25', 'pm10', 'no2', 'o3', 'so2', 'co')
SOURCE_NAME = re.compile(r'(?P<region>R[A-ZIVX]+)_(?P<station>[A-Za-z0-9-]+)_horario_(?P<start>\d{4}-\d{2}-\d{2})_(?P<end>\d{4}-\d{2}-\d{2})\.csv')


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def json_atomic(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.pending')
    with temp.open('x', encoding='utf8') as stream:
        json.dump(value, stream, sort_keys=True, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)
    fsync_dir(path.parent)


def publish_no_replace(stage, destination):
    """Publicación atómica Darwin; jamás sustituye siquiera un directorio vacío."""
    libc = ctypes.CDLL(None, use_errno=True)
    rename = libc.renamex_np  # No fallback inseguro en una plataforma no soportada.
    rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(os.fsencode(stage), os.fsencode(destination), 0x00000004) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(destination))


class SafeLimit(RuntimeError):
    pass


def check_disk(output, reserve_gib=100, pending_bytes=0, volume_uuid=VOLUME_UUID):
    if reserve_gib < 100 or not math.isfinite(reserve_gib):
        raise ValueError('la reserva debe ser finita y >=100 GiB')
    output = Path(output).resolve()
    if volume_uuid is not None:
        mount = Path('/Volumes/Datos')
        if not output.is_relative_to(mount) or not mount.is_mount():
            raise SafeLimit('el destino externo no está montado')
        info = plistlib.loads(subprocess.check_output(['diskutil', 'info', '-plist', str(mount)]))
        if info.get('VolumeUUID') != volume_uuid:
            raise SafeLimit('UUID del disco externo distinto')
    parent = output
    while not parent.exists():
        parent = parent.parent
    free = shutil.disk_usage(parent).free
    if free - pending_bytes < reserve_gib * GIB:
        raise SafeLimit('reserva de 100 GiB insuficiente; originales intactos')
    return free


@contextmanager
def exclusive_lock(path):
    import fcntl
    with Path(path).open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def load_existing_semantics(path):
    """Carga sólo el parser y el ranking AST de afg_lib, sin importar su setup.

    El módulo original crea directorios y carga otras dependencias. Compilar
    estas definiciones exactas evita ejecutar esos efectos y deja sus hashes.
    La extracción falla cerrada si cambia la estructura de la regla existente.
    """
    import numpy as np
    import pandas as pd
    content = Path(path).read_bytes()
    tree = ast.parse(content, filename=str(path))
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    parser = functions['leer_sinca_serie']
    ranges = next(ast.literal_eval(n.value) for n in tree.body
                  if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'RANGO_VALIDO' for t in n.targets))
    nodes = functions['leer_sinca'].body
    begin = next(i for i, n in enumerate(nodes) if isinstance(n, ast.Assign)
                 and ast.unparse(n.targets[0]) == '(lo, hi)')
    ranking = copy.deepcopy(nodes[begin:begin + 4])
    if len(ranking) != 4 or '.drop_duplicates(' not in ast.unparse(ranking[-1]) \
            or "'_util'" not in ast.unparse(ranking[1]) or "'_calidad'" not in ast.unparse(ranking[2]):
        raise ValueError('ranking afg_lib cambió; se requiere revisión explícita')
    wrapper = ast.FunctionDef(name='rank_existing',
                              args=ast.arguments(posonlyargs=[], args=[ast.arg(arg='df'), ast.arg(arg='pol')],
                                                 kwonlyargs=[], kw_defaults=[], defaults=[]),
                              body=ranking + [ast.Return(ast.Name(id='df', ctx=ast.Load()))],
                              decorator_list=[])
    module = ast.fix_missing_locations(ast.Module(body=[copy.deepcopy(parser), wrapper], type_ignores=[]))
    scope = {'np': np, 'pd': pd, 'Path': Path, 'RANGO_VALIDO': ranges}
    exec(compile(module, str(path), 'exec'), scope)
    return scope['leer_sinca_serie'], scope['rank_existing'], ranges, {
        'file_sha256': hashlib.sha256(content).hexdigest(),
        'parser_ast_sha256': digest(ast.dump(parser, include_attributes=False)),
        'ranking_ast_sha256': digest([ast.dump(n, include_attributes=False) for n in ranking]),
    }, content


def load_inputs(source, policy_path, afg_path, station=None, pollutant=None):
    source = Path(source).resolve()
    paths = {'manifest': source / 'manifiesto_descarga.csv',
             'geometry': source / 'estaciones_georreferenciadas.geojson',
             'policy': Path(policy_path).resolve()}
    contents = {k: p.read_bytes() for k, p in paths.items()}
    rows = list(csv.DictReader(io.StringIO(contents['manifest'].decode('utf-8-sig'))))
    selected = []
    seen = set()
    for row in rows:
        if station is not None and row['estacion'] != station:
            continue
        if pollutant is not None and row['contaminante'] != pollutant:
            continue
        if row['resolucion'] != 'horario' or row['contaminante'] not in GASES:
            raise ValueError('registro fuera del contrato horario de SINCA')
        path = Path(row['ruta']).resolve()
        if not path.is_relative_to(source):
            raise ValueError('fuente fuera del directorio SINCA autorizado')
        match = SOURCE_NAME.fullmatch(path.name)
        if not match or (match['station'], match['region'], match['start'], match['end']) != \
                (row['estacion'], row['region'], row['desde'], row['hasta']):
            raise ValueError('identidad/rango del archivo contradice el manifiesto')
        if date.fromisoformat(row['hasta']) < date.fromisoformat(row['desde']):
            raise ValueError('rango de consulta inválido')
        if not re.fullmatch('[a-fA-F0-9]{64}', row['sha256']):
            raise ValueError('fuente sin SHA256 comprobable')
        if str(path) in seen:
            raise ValueError('ruta duplicada en el manifiesto')
        seen.add(str(path))
        selected.append({**row, 'ruta': str(path), 'relative_path': str(path.relative_to(source))})
    geo = json.loads(contents['geometry'])
    features = {}
    for feature in geo['features']:
        code = str(feature['properties']['estacion'])
        if code in features:
            raise ValueError('estación geográfica duplicada')
        features[code] = feature
    parser, rank, ranges, semantics, afg_bytes = load_existing_semantics(afg_path)
    return {'source': source, 'rows': sorted(selected, key=lambda r: r['relative_path']),
            'geometry': features, 'policy': json.loads(contents['policy']),
            'hashes': {k: hashlib.sha256(b).hexdigest() for k, b in contents.items()},
            'parser': parser, 'rank': rank, 'ranges': ranges, 'semantics': semantics,
            'frozen_files': {**{paths[k].name: b for k, b in contents.items() if k != 'manifest'},
                             'afg_lib.py': afg_bytes}}


def read_source(row, inputs):
    import numpy as np
    import pandas as pd
    path = Path(row['ruta'])
    if path.stat().st_size != int(row['bytes']) or sha256(path) != row['sha256']:
        raise ValueError('hash/tamaño fuente no coincide con manifiesto; no publicar')
    # Índices originales se mantienen incluso si el parser existente omite
    # fechas inválidas. Sus celdas originales siguen disponibles para auditoría.
    raw_rows, physical_lines = [], []
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.reader(stream, delimiter=';')
        header = next(reader)
        if len(header) < 2 or not header[0].startswith('FECHA') or not header[1].startswith('HORA'):
            raise ValueError('encabezado SINCA inesperado')
        previous_line = reader.line_num
        for raw in reader:
            start_line = previous_line + 1
            previous_line = reader.line_num
            if not raw:
                continue
            if len(raw) > 6:
                raise ValueError('columnas originales adicionales no interpretadas')
            raw_rows.append(raw + [''] * (6 - len(raw)))
            physical_lines.append(start_line)
    df = pd.DataFrame(raw_rows, columns=['fecha_original', 'hora_original', 'v_validado_original',
                                         'v_preliminar_original', 'v_no_validado_original', 'extra_original'])
    parsed = inputs['parser'](path)
    if len(df) != int(row['filas']) or not parsed.index.isin(df.index).all():
        raise ValueError('conteo/índice del parser contradice fuente manifiesta')
    df['ts_local'] = parsed['ts_local']
    df['obs'] = parsed['obs']
    df['qc_observacion'] = parsed['qc_observacion']
    invalid = df['ts_local'].isna()
    # Sólo en fechas inválidas omitidas por el lector heredado: conservar
    # también el número/estado sin fingir una marca temporal interpretable.
    df.loc[invalid, 'qc_observacion'] = 'sin_dato'
    for col, quality in zip(['v_validado_original', 'v_preliminar_original', 'v_no_validado_original'],
                            ['validado', 'preliminar', 'no_validado']):
        value = pd.to_numeric(df[col].str.strip().str.replace(',', '.', regex=False), errors='coerce')
        take = invalid & df['obs'].isna() & np.isfinite(value)
        df.loc[take, ['obs', 'qc_observacion']] = pd.DataFrame({'obs': value[take], 'qc_observacion': quality})
    df['source_line'] = physical_lines
    df['source_path'] = row['relative_path']
    df['source_sha256'] = row['sha256']
    df['fuente_id'] = digest({'path': row['relative_path'], 'sha256': row['sha256']})
    df['estacion'], df['contaminante'] = row['estacion'], row['contaminante']
    df['_fuente_desde'], df['_fuente_hasta'] = pd.Timestamp(row['desde']), pd.Timestamp(row['hasta'])
    df['_fuente_dias'] = (pd.Timestamp(row['hasta']) - pd.Timestamp(row['desde'])).days
    df['_fuente_nombre'] = path.name
    if sha256(path) != row['sha256']:
        raise ValueError('fuente cambió durante lectura')
    return df


def time_candidates(local, zone):
    """Candidatos de la etiqueta civil; nunca UTC definitivo sin evidencia."""
    import pandas as pd
    tz = zoneinfo.ZoneInfo(zone)
    standard = local.dt.tz_localize(tz, ambiguous=False, nonexistent='NaT').dt.tz_convert('UTC')
    summer = local.dt.tz_localize(tz, ambiguous=True, nonexistent='NaT').dt.tz_convert('UTC')
    ambiguous = standard.notna() & summer.notna() & (standard != summer)
    quality = pd.Series('univoca_bajo_hipotesis_reloj_civil', index=local.index)
    quality.loc[local.isna()] = 'etiqueta_invalida'
    quality.loc[local.notna() & standard.isna() & summer.isna()] = 'inexistente_no_desplazada'
    quality.loc[ambiguous] = 'ambigua_no_resuelta'
    first = standard.where(~ambiguous | (standard < summer), summer)
    second = standard.where(ambiguous & (standard > summer), summer).where(ambiguous)
    return first, second, quality


def consolidate(rows, inputs, *, since=None, until=None):
    import numpy as np
    import pandas as pd
    station, pollutant = rows[0]['estacion'], rows[0]['contaminante']
    if any((r['estacion'], r['contaminante']) != (station, pollutant) for r in rows):
        raise ValueError('se exige una serie estación×contaminante')
    feature = inputs['geometry'].get(station)
    if feature is None or feature['geometry']['type'] != 'Point':
        raise ValueError('estación sin geometría Point documentada')
    prop = feature['properties']; lon, lat = feature['geometry']['coordinates']
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError('coordenadas fuera de rango')
    regions = {r['region'] for r in rows}
    if regions != {prop['region_sinca']}:
        raise ValueError('región de las fuentes contradice catálogo geográfico')
    policy = inputs['policy']['sinca']
    if policy['reloj_fuente'] != 'hora_local_civil_sinca_sin_offset':
        raise ValueError('política de reloj fuente desconocida')
    zone = policy['zonas_iana_por_region'].get(prop['region_sinca'], policy['zona_iana_default'])
    df = pd.concat([read_source(r, inputs) for r in rows], ignore_index=True)
    original_count = len(df)
    keep = df['ts_local'].isna()
    valid = df['ts_local'].notna()
    if since:
        valid &= df['ts_local'] >= pd.Timestamp(since)
    if until:
        valid &= df['ts_local'] < pd.Timestamp(until) + pd.Timedelta(days=1)
    df = df.loc[keep | valid].copy().reset_index(drop=True)
    valid = df['ts_local'].notna()
    picked = inputs['rank'](df.loc[valid].copy(), pollutant)
    df['seleccionada'] = ~valid | df.index.isin(picked.index)
    # Alternativas de solapes, incluidos timestamps repetidos en un archivo,
    # se publican separadamente. Nada observado se borra ni se promedia.
    keys = df['ts_local'].astype(str)
    keys.loc[~valid] = 'invalida:' + df.loc[~valid, 'fuente_id'] + ':' + df.loc[~valid, 'source_line'].astype(str)
    df['grupo_solapamiento'] = pd.factorize(keys, sort=False)[0].astype('int64')
    counts = df.groupby('grupo_solapamiento').size()
    df['n_candidatos'] = df['grupo_solapamiento'].map(counts)
    repeated = df.duplicated(['fuente_id', 'ts_local'], keep=False) & valid
    repeats = df.assign(_repeated=repeated).groupby('grupo_solapamiento')['_repeated'].any()
    df['hora_repetida_en_fuente'] = df['grupo_solapamiento'].map(repeats)
    df['valor_faltante'] = ~np.isfinite(df['obs'])
    lo, hi = inputs['ranges'][pollutant]
    df['fuera_rango_afg'] = ~df['valor_faltante'] & ~df['obs'].between(lo, hi)
    df['timestamp_invalido'] = ~valid
    df['utc_candidato_1'], df['utc_candidato_2'], df['qc_hora'] = time_candidates(df['ts_local'], zone)
    df['ts_utc'] = pd.Series(pd.NaT, index=df.index, dtype='datetime64[ns, UTC]')
    df['zona_iana'] = zone
    df['semantica_intervalo_verificada'] = False
    df['unidad'] = None
    df['unidad_confirmada'] = False
    # Los rangos se usan exclusivamente porque pertenecen al ranking afg
    # existente; no equivalen a una verificación de unidades del exportador.
    df['region_sinca'], df['nombre_estacion'] = prop['region_sinca'], prop.get('nombre')
    df['lat'], df['lon'] = float(lat), float(lon)
    point = struct.pack('<BIdd', 1, 1, float(lon), float(lat))
    df['geometry_wkb'] = [point] * len(df)
    df['crs'] = 'EPSG:4326; WKB x=longitude,y=latitude'
    df['geo_usable'] = prop.get('usable_geoespacial')
    df['qc_comuna'] = prop.get('qc_comuna')
    df['cod_comuna'] = prop.get('cod_comuna_geografica')
    df['comuna_geografica'] = prop.get('comuna_geografica')
    df['comuna_sinca'] = prop.get('comuna_sinca')
    df['coincide_comuna_sinca'] = prop.get('coincide_comuna_sinca')
    df['fuente_geo_sha256'] = inputs['hashes']['geometry']
    df = df.sort_values(['ts_local', 'source_path', 'source_line'], kind='stable', na_position='last')
    selected, alternatives = df[df['seleccionada']].copy(), df[~df['seleccionada']].copy()
    stats = {'filas_originales_leidas': original_count, 'filas_en_ventana': len(df),
             'filas_seleccionadas': len(selected), 'filas_alternativas_conservadas': len(alternatives),
             'mediciones_seleccionadas': int((~selected['valor_faltante']).sum()),
             'calidad_seleccionada': {str(k): int(v) for k, v in selected['qc_observacion'].value_counts().items()},
             'horas_qc': {str(k): int(v) for k, v in selected['qc_hora'].value_counts().items()},
             'utc_confirmados': 0, 'unidades_confirmadas': False}
    assert len(selected) + len(alternatives) == len(df)
    return to_arrow(selected), to_arrow(alternatives), stats


def to_arrow(df):
    import pyarrow as pa
    strings = ['estacion', 'contaminante', 'region_sinca', 'nombre_estacion', 'fecha_original', 'hora_original',
               'qc_observacion', 'v_validado_original', 'v_preliminar_original', 'v_no_validado_original',
               'extra_original', 'unidad', 'zona_iana', 'qc_hora', 'fuente_id', 'source_sha256', 'source_path',
               'crs', 'qc_comuna', 'comuna_geografica', 'comuna_sinca', 'fuente_geo_sha256']
    booleans = ['unidad_confirmada', 'valor_faltante', 'fuera_rango_afg', 'timestamp_invalido',
                'semantica_intervalo_verificada', 'hora_repetida_en_fuente', 'seleccionada',
                'geo_usable', 'coincide_comuna_sinca']
    fields = [pa.field(c, pa.string()) for c in strings]
    fields += [pa.field(c, pa.bool_()) for c in booleans]
    fields += [pa.field(c, pa.int64()) for c in ['source_line', 'grupo_solapamiento', 'n_candidatos', 'cod_comuna']]
    fields += [pa.field(c, pa.float64()) for c in ['obs', 'lat', 'lon']]
    fields += [pa.field('geometry_wkb', pa.binary()), pa.field('ts_local', pa.timestamp('us'))]
    fields += [pa.field(c, pa.timestamp('us', tz='UTC')) for c in ['ts_utc', 'utc_candidato_1', 'utc_candidato_2']]
    schema = pa.schema(fields, metadata={b'contract': CONTRACT.encode(),
                         b'utc_policy': b'no confirmed UTC; IANA label candidates only; no DST shift or imputation',
                         b'geometry': b'WKB Point, EPSG:4326, x=longitude/y=latitude; no communal averaging'})
    return pa.Table.from_pandas(df[schema.names], schema=schema, preserve_index=False, safe=True)


def timezone_evidence(zone):
    for root in zoneinfo.TZPATH:
        path = Path(root) / zone
        if path.is_file():
            return {'zone': zone, 'tzfile_sha256': sha256(path)}
    import importlib.resources
    content = importlib.resources.files('tzdata.zoneinfo').joinpath(*zone.split('/')).read_bytes()
    return {'zone': zone, 'tzfile_sha256': hashlib.sha256(content).hexdigest()}


def validate_publication(path, expected_version=None):
    import pyarrow.parquet as pq
    path = Path(path)
    proof = json.loads((path / 'manifest.json').read_text())
    if expected_version and proof['version'] != expected_version:
        raise ValueError('versión publicada distinta a la solicitada')
    if digest(proof['inputs']) != proof['version']:
        raise ValueError('identidad de publicación alterada')
    if [f['name'] for f in proof['files']] != ['observaciones.parquet', 'solapamientos.parquet']:
        raise ValueError('publicación sin ambos conjuntos de conservación')
    for archived in proof['provenance_files']:
        name = archived['name']
        if Path(name).name != name or sha256(path / 'procedencia' / name) != archived['sha256']:
            raise ValueError('archivo reproducible de procedencia alterado')
    total = 0
    for file in proof['files']:
        p = path / file['name']
        if p.name != file['name'] or not p.is_file() or sha256(p) != file['sha256']:
            raise ValueError('Parquet publicado ausente/alterado; no sobrescribir')
        table = pq.ParquetFile(p).read()
        if table.num_rows != file['rows'] or table.schema.metadata.get(b'contract') != CONTRACT.encode() \
                or hashlib.sha256(table.schema.serialize().to_pybytes()).hexdigest() != file['schema_sha256']:
            raise ValueError('filas/esquema publicados distintos')
        if table['ts_utc'].null_count != table.num_rows:
            raise ValueError('UTC definitivo no autorizado por este contrato')
        total += table.num_rows
    if total != proof['statistics']['filas_en_ventana']:
        raise ValueError('conservación de filas no comprobada')
    return proof


def process_series(rows, inputs, output, *, since=None, until=None, reserve_gib=100,
                   volume_uuid=VOLUME_UUID, code_bytes=None):
    """API para orquestador: llamar dentro de exclusive_lock(output/.writer.lock)."""
    import pyarrow.parquet as pq
    output = Path(output).resolve()
    if output == inputs['source'] or output.is_relative_to(inputs['source']):
        raise ValueError('los derivados no pueden escribirse sobre fuentes')
    if not rows:
        raise ValueError('serie vacía')
    code_bytes = code_bytes if code_bytes is not None else Path(__file__).read_bytes()
    station, pollutant = rows[0]['estacion'], rows[0]['contaminante']
    prop = inputs['geometry'][station]['properties']
    p = inputs['policy']['sinca']
    zone = p['zonas_iana_por_region'].get(prop['region_sinca'], p['zona_iana_default'])
    descriptor = {'contract': CONTRACT, 'station': station, 'pollutant': pollutant,
                  'since': since, 'until': until, 'sources': rows,
                  'geometry_feature': inputs['geometry'][station],
                  'geometry_sha256': inputs['hashes']['geometry'],
                  'temporal_policy_sha256': inputs['hashes']['policy'],
                  'afg_semantics': inputs['semantics'], 'code_sha256': hashlib.sha256(code_bytes).hexdigest(),
                  'runtime': {'python': sys.version, 'packages': {x: importlib.metadata.version(x) for x in ['pandas', 'numpy', 'pyarrow']},
                              'timezone': timezone_evidence(zone)},
                  'unit_policy': 'unknown; original CSV/manifest have no source unit; no conversion',
                  'temporal_override': 'preserve civil label; ts_utc null; DST candidates only; original afg UTC policy not applied'}
    version = digest(descriptor)
    destination = output / ('estacion=' + station) / ('contaminante=' + pollutant) / ('version=' + version)
    check_disk(output, reserve_gib, sum(int(r['bytes']) for r in rows) * 12 + 2**20, volume_uuid)
    for row in rows:
        if Path(row['ruta']).stat().st_size != int(row['bytes']) or sha256(row['ruta']) != row['sha256']:
            raise ValueError('fuente actual contradice snapshot; no publicar ni reutilizar')
    if destination.exists():
        proof = validate_publication(destination, version)
        return {'status': 'reused', 'path': str(destination), 'version': version, 'statistics': proof['statistics']}
    stage = output / '_staging' / version
    stage.mkdir(parents=True, exist_ok=True)
    if (stage / 'manifest.json').exists():
        proof = validate_publication(stage, version)
    else:
        if any(stage.iterdir()):
            # No se pisan parciales de una corrida interrumpida. Nueva carpeta
            # de intento, manteniendo la versión científica determinista.
            stage = output / '_staging' / (version + '-' + uuid.uuid4().hex)
            stage.mkdir()
        selected, alternatives, statistics = consolidate(rows, inputs, since=since, until=until)
        files = []
        for name, table in [('observaciones.parquet', selected), ('solapamientos.parquet', alternatives)]:
            check_disk(output, reserve_gib, max(table.nbytes * 2, 2**20), volume_uuid)
            path = stage / name
            with path.open('xb') as stream:
                pq.write_table(table, stream, compression='zstd', use_dictionary=True, row_group_size=65536)
                stream.flush()
                os.fsync(stream.fileno())
            reopened = pq.ParquetFile(path).read()
            if not reopened.equals(table, check_metadata=True):
                raise ValueError('reapertura no es exactamente igual a la tabla previa')
            files.append({'name': name, 'sha256': sha256(path), 'bytes': path.stat().st_size, 'rows': table.num_rows,
                          'schema_sha256': hashlib.sha256(table.schema.serialize().to_pybytes()).hexdigest()})
        provenance = []
        archive = stage / 'procedencia'
        archive.mkdir()
        for name, content in sorted({**inputs['frozen_files'], 'preparar_sinca_modelado.py': code_bytes}.items()):
            with (archive / name).open('xb') as stream:
                stream.write(content); stream.flush(); os.fsync(stream.fileno())
            provenance.append({'name': name, 'sha256': hashlib.sha256(content).hexdigest()})
        fsync_dir(archive)
        proof = {'contract': CONTRACT, 'version': version, 'created_utc': now(), 'inputs': descriptor,
                 'source_manifest_snapshot_sha256': inputs['hashes']['manifest'],
                 'statistics': statistics, 'files': files, 'provenance_files': provenance, 'source_files_deleted': False,
                 'source_clock_and_interval_semantics_verified': False}
        json_atomic(stage / 'manifest.json', proof)
    # Rehash de todas las fuentes antes de publicar; no tocar ningún original.
    for row in rows:
        if sha256(row['ruta']) != row['sha256']:
            raise ValueError('fuente cambió antes de publicar; staging preservado')
    validate_publication(stage, version)
    check_disk(output, reserve_gib, 2**20, volume_uuid)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError('otra publicación ya existe; no sobrescribir')
    publish_no_replace(stage, destination)
    fsync_dir(destination.parent)
    return {'status': 'published', 'path': str(destination), 'version': version, 'statistics': proof['statistics']}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--fuente', type=Path, default=DEFAULT_SOURCE)
    ap.add_argument('--salida', type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument('--estacion')
    ap.add_argument('--contaminante', choices=GASES)
    ap.add_argument('--desde')
    ap.add_argument('--hasta')
    ap.add_argument('--max-series', type=int, default=1, help='1 por defecto; 0=todas explícitamente')
    ap.add_argument('--reserva-gib', type=float, default=100)
    ap.add_argument('--ejecutar', action='store_true')
    args = ap.parse_args(argv)
    if args.max_series < 0:
        ap.error('max-series debe ser >=0')
    for value in (args.desde, args.hasta):
        if value:
            date.fromisoformat(value)
    if args.desde and args.hasta and args.desde > args.hasta:
        ap.error('ventana temporal invertida')
    inputs = load_inputs(args.fuente, REPO / 'config/sinca/politica_temporal.json',
                         REPO / 'scripts_superficie/afg_lib.py', args.estacion, args.contaminante)
    groups = {}
    for row in inputs['rows']:
        if args.desde and row['hasta'] < args.desde or args.hasta and row['desde'] > args.hasta:
            continue
        groups.setdefault((row['estacion'], row['contaminante']), []).append(row)
    selected = list(sorted(groups))[:args.max_series or None]
    if not selected:
        raise ValueError('ninguna serie coincide con el filtro')
    plan = {'contract': CONTRACT, 'series': [{'estacion': k[0], 'contaminante': k[1], 'archivos_fuente': len(groups[k])} for k in selected],
            'source_manifest_sha256': inputs['hashes']['manifest'], 'output': str(args.salida), 'writes_enabled': args.ejecutar}
    if not args.ejecutar:
        print(json.dumps(plan, ensure_ascii=False))
        return 0
    output = args.salida.resolve()
    if output.is_relative_to(inputs['source']) or not output.is_relative_to(DEFAULT_OUTPUT):
        raise ValueError('destino debe estar dentro del derivado SINCA autorizado')
    check_disk(output, args.reserva_gib)
    output.mkdir(parents=True, exist_ok=True)
    with exclusive_lock(output / '.writer.lock'):
        run = output / '_runs' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex)
        run.mkdir(parents=True)
        code_bytes = Path(__file__).read_bytes()
        for name, content in {**inputs['frozen_files'], 'preparar_sinca_modelado.py': code_bytes}.items():
            with (run / name).open('xb') as stream:
                stream.write(content); stream.flush(); os.fsync(stream.fileno())
        results = []
        json_atomic(run / 'plan.json', plan)
        try:
            for key in selected:
                result = process_series(groups[key], inputs, output, since=args.desde, until=args.hasta,
                                        reserve_gib=args.reserva_gib, code_bytes=code_bytes)
                results.append(result)
                json_atomic(run / 'progreso.json', {'status': 'running', 'updated_utc': now(), 'results': results,
                                                   'planned_series': len(selected)})
        except Exception as exc:
            json_atomic(run / 'progreso.json', {'status': 'stopped_without_deletion', 'updated_utc': now(),
                                               'error_type': type(exc).__name__, 'results': results,
                                               'planned_series': len(selected)})
            raise
        json_atomic(run / 'progreso.json', {'status': 'complete_for_selected_scope', 'updated_utc': now(),
                                           'results': results, 'planned_series': len(selected)})
        print(json.dumps({'status': 'complete_for_selected_scope', 'run': str(run), 'results': results}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
