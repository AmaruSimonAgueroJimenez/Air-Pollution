#!/usr/bin/env python3
"""Revalida una revisión ERA5-Land sin escrituras, usando respaldos exactos.

No restaura rutas canónicas, no descarga y no cambia identidades. Sólo las
parejas mensuales NetCDF/manifiesto pueden resolverse en respaldos registrados;
catálogos, geometría y contrato conservan su comprobación estricta original.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

import preparar_era5land_modelado as converter


BACKUP_SCHEMA = 'airpollution.era5land-respaldo-publicacion.v1'


def _path(value):
    path = Path(value)
    if not path.is_absolute() or path.absolute() != path.resolve():
        raise ValueError(f'Ruta no absoluta, no canónica o con enlace: {path}')
    return path


def _matches(record):
    path = _path(record['path'])
    return path.is_file() and converter._record(path) == record


def _resolve_month(source, origin):
    month = source['mes']
    converter._months(month)
    basename = month.replace('-', '')
    expected = {
        'native': origin / 'mensual' / f'era5land_{basename}_chile_pixeles.nc',
        'manifest': origin / 'manifiestos' / f'era5land_{basename}.json',
    }
    for key, path in expected.items():
        if _path(source[key]['path']) != path:
            raise ValueError(f'Ruta mensual fuera de la raíz/mes esperado: {key}')
    if all(_matches(source[key]) for key in expected):
        return copy.deepcopy(source), [
            {'month': month, 'kind': key, 'original': source[key]['path'],
             'resolved': source[key]['path'], 'sha256': source[key]['sha256'],
             'bytes': source[key]['bytes'], 'via': 'canonical'}
            for key in expected
        ], []

    backup_root = origin / '_respaldos_publicacion' / basename
    _path(backup_root)
    candidates = []
    for registry_path in sorted(backup_root.glob('*/respaldo.json')):
        registry_path = _path(registry_path)
        if registry_path.parent.parent != backup_root:
            raise ValueError('Registro de respaldo fuera del mes permitido')
        registry_record = converter._record(registry_path)
        registry = json.loads(registry_path.read_text())
        if registry.get('schema') != BACKUP_SCHEMA or registry.get('periodo') != month:
            raise ValueError(f'Registro de respaldo con esquema/mes incompatible: {registry_path}')
        artifacts = registry.get('artefactos')
        if not isinstance(artifacts, list):
            raise ValueError('Registro sin lista de artefactos')
        by_original = {}
        for artifact in artifacts:
            original = _path(artifact['original'])
            if original not in expected.values() or str(original) in by_original:
                raise ValueError('Registro con original inesperado o duplicado')
            backup = _path(artifact['respaldo'])
            if backup != registry_path.parent / original.name:
                raise ValueError('Artefacto fuera de su carpeta de respaldo')
            by_original[str(original)] = artifact
        if set(by_original) != {str(p) for p in expected.values()}:
            # Un respaldo de una publicación incompleta no puede resolver
            # una pareja íntegra, pero se conserva y no se altera.
            continue
        if not all(
            by_original[source[key]['path']]['sha256'] == source[key]['sha256']
            and by_original[source[key]['path']]['bytes'] == source[key]['bytes']
            for key in expected
        ):
            continue
        resolved = copy.deepcopy(source)
        mappings = []
        for key in expected:
            artifact = by_original[source[key]['path']]
            record = {'path': artifact['respaldo'], 'sha256': artifact['sha256'], 'bytes': artifact['bytes']}
            if not _matches(record):
                raise ValueError(f'Respaldo ausente/corrupto: {record["path"]}')
            resolved[key] = record
            mappings.append({'month': month, 'kind': key, 'original': source[key]['path'],
                             'resolved': record['path'], 'sha256': record['sha256'],
                             'bytes': record['bytes'], 'via': 'registered_backup',
                             'backup_registry': registry_record})
        converter._verify([registry_record])
        candidates.append((resolved, mappings, [registry_record]))
    if len(candidates) != 1:
        raise ValueError(f'Se requiere un único respaldo exacto de {month}; encontrados {len(candidates)}')
    return candidates[0]


def validar_revision(directory, *, origen=converter.ORIGEN):
    """Comprueba identidad, archivos y fórmula completa; no escribe nada."""
    directory, origin = _path(directory), _path(origen)
    manifest_path = directory / 'manifest.json'
    manifest_record = converter._record(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    identity = manifest['identity']
    if (manifest.get('schema') != converter.CONTRATO['schema']
            or manifest['contract'] != converter.CONTRATO
            or identity['contract'] != converter.CONTRATO
            or hashlib.sha256(converter._json(identity)).hexdigest() != manifest['revision']):
        raise ValueError('Identidad/contrato de revisión incompatible')
    archive_record = converter._record(directory / 'preparar_era5land_modelado.py', identity['code_sha256'])
    runtime_code = converter._record(Path(converter.__file__), identity['code_sha256'])
    validator_record = converter._record(Path(__file__))
    runtime = converter._dependencies()
    # Se llama sólo al módulo conocido; jamás se ejecuta código de un manifiesto.
    inventory = copy.deepcopy(identity['inputs'])
    current_month = inventory['current']['mes']
    _, previous_month = converter._months(current_month)
    if inventory['previous'] and inventory['previous']['mes'] != previous_month:
        raise ValueError('Mes antecedente incompatible')
    mappings, registries = [], []
    for key in ('current', 'previous'):
        if inventory[key] is not None:
            inventory[key], resolved, records = _resolve_month(inventory[key], origin)
            mappings.extend(resolved)
            registries.extend(records)
    source_records = converter._records(inventory)
    output = directory / 'tp_1h_mm.nc'
    output_record = converter._record(output, manifest['output']['sha256'])
    if output_record['bytes'] != manifest['output']['bytes']:
        raise ValueError('Tamaño del derivado incompatible')
    stable_records = [manifest_record, archive_record, runtime_code, validator_record, output_record,
                      *runtime['selected_compiled_modules'], *registries, *source_records]
    converter._verify(stable_records)
    data, values, flags = converter._inputs(inventory)
    stats = converter._validate_nc(output, data, values, flags, manifest['revision'])
    if stats != manifest['validation'] or data['overlay'] != manifest['native_variable_metadata_overlay']:
        raise ValueError('Resumen/metadata difiere de la recomputación')
    converter._verify(stable_records)
    return {'schema': 'airpollution.era5land.modelado.revalidation.v1',
            'checked_utc': converter._utc(), 'validator': validator_record, 'runtime': runtime,
            'status': 'validated_readonly', 'directory': str(directory),
            'revision': manifest['revision'], 'manifest': manifest_record,
            'output': output_record, 'validation': stats, 'source_resolution': mappings,
            'backup_registries': registries, 'all_hashes_rechecked_after_recomputation': True,
            'archived_converter_matches_loaded_code': True, 'writes': False,
            'validation_scope': 'Full recomputation from exact local input bytes; not upstream historical provenance certification.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('revision', type=Path)
    parser.add_argument('--origen', type=Path, default=converter.ORIGEN)
    args = parser.parse_args()
    print(json.dumps(validar_revision(args.revision, origen=args.origen), ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
