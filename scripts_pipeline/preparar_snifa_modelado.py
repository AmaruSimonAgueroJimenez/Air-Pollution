#!/usr/bin/env python3
"""Procesa los originales SNIFA como una red independiente, con trazabilidad.

La salida es horaria en el reloj publicado; no se inventa UTC. Se conservan
observaciones originales, duplicados y conflictos antes de formar la tabla
canónica. Consultar docs/RED_ADICIONAL_SNIFA.md para límites y reanudación.
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import datetime as dt
import fcntl
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import unicodedata

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from descargar_snifa import CONFIG, atomic_json, check_disk, contained_path, data_root, now, sha256
from _snifa_excel import parse_excel
from _snifa_pdf import parse_pdf, parse_pdf_events

VERSION = '1.1.0'
LOG = logging.getLogger('preparar_snifa')
SCHEMA = pa.schema([
    ('network_id', pa.string()), ('record_type', pa.string()),
    ('station_id', pa.string()), ('station_name', pa.string()),
    ('pollutant', pa.string()), ('date_local', pa.string()), ('outside_report_period', pa.bool_()),
    ('hour_label', pa.string()),
    ('hour_index', pa.int16()), ('value', pa.float64()), ('raw_value', pa.string()),
    ('unit_original', pa.string()), ('unit', pa.string()), ('quality_code', pa.string()),
    ('numeric_usable', pa.bool_()), ('clock_status', pa.string()), ('timestamp_utc', pa.string()),
    ('latitude', pa.float64()), ('longitude', pa.float64()), ('coordinate_source_url', pa.string()),
    ('source_id', pa.string()), ('report_id', pa.int64()), ('document_id', pa.int64()),
    ('document_sha256', pa.string()), ('source_url', pa.string()), ('file_path', pa.string()),
    ('source_locator', pa.string()), ('source_format', pa.string()), ('resolution', pa.string()),
])


def canonical_unit(value):
    text = unicodedata.normalize('NFKC', str(value or '')).lower().replace('μ', 'u').replace('µ', 'u')
    text = re.sub(r'[\s^{}()]', '', text)
    aliases = {'ug/m3': 'ug/m3', 'ug/m3n': 'ug/m3N', 'ug/nm3': 'ug/m3N',
               'mg/m3': 'mg/m3', 'mg/m3n': 'mg/m3N', 'mg/nm3': 'mg/m3N',
               'ppb': 'ppb', 'ppm': 'ppm', 'ppbv': 'ppbv', 'ppmv': 'ppmv'}
    return aliases.get(text, 'unknown')


def hour_index(label):
    text = str(label).strip()
    if re.fullmatch(r'\d{1,2}:00(?::00)?', text):
        number = int(text.split(':')[0])
    else:
        try:
            value = float(text)
        except ValueError:
            return None
        if not math.isfinite(value):
            return None
        if 0 < value < 1:
            value *= 24
        elif value > 24 or (len(text) >= 3 and text.isdigit() and text.startswith('0')):
            if value % 100:
                return None
            value /= 100
        if abs(value - round(value)) > 1e-6:
            return None
        number = round(value)
    return number if 0 <= number <= 24 else None


def enrich(rows, record, stations):
    output, rejected = [], 0
    for row in rows:
        station = stations.get(row.get('station_id'))
        hour = hour_index(row.get('hour_label', ''))
        if (not station or station.get('source_id') != record['source_id'] or
                row.get('pollutant') not in station['pollutants'] or
                row.get('resolution') not in {'hourly', 'quality_event'} or hour is None):
            rejected += 1
            continue
        try:
            day = dt.date.fromisoformat(row['date']).isoformat()
        except (KeyError, ValueError, TypeError):
            rejected += 1
            continue
        # The report's portal metadata can differ from dates explicitly printed
        # in its attachments. Keep the source date and expose the discrepancy.
        outside_report_period = bool(
            (record.get('period_start') and day < record['period_start']) or
            (record.get('period_end') and day > record['period_end']))
        try:
            value = row.get('value')
            if isinstance(value, bool):
                raise ValueError('Una observación booleana no es una concentración')
            value = float(value) if value is not None and math.isfinite(float(value)) else None
        except (ValueError, TypeError, OverflowError):
            rejected += 1
            continue
        code = str(row.get('quality_code') or '')
        unit = canonical_unit(row.get('unit'))
        output.append({
            'network_id': 'snifa_adicional',
            'record_type': 'quality_event' if row['resolution'] == 'quality_event' else 'measurement',
            'station_id': station['id'],
            'station_name': station['name'], 'pollutant': row['pollutant'],
            'date_local': day, 'hour_label': str(row['hour_label']), 'hour_index': hour,
            'outside_report_period': outside_report_period,
            'value': value, 'raw_value': str(row['raw_value']) if row.get('raw_value') is not None else '',
            'unit_original': str(row.get('unit') or ''), 'unit': unit, 'quality_code': code,
            'numeric_usable': value is not None and value >= 0 and not code and unit != 'unknown',
            'clock_status': station.get('timezone_status', 'unverified'), 'timestamp_utc': None,
            'latitude': station['latitude'], 'longitude': station['longitude'],
            'coordinate_source_url': station['coordinate_source_url'],
            'source_id': record['source_id'], 'report_id': int(record['report_id']),
            'document_id': int(record['document_id']), 'document_sha256': record['sha256'],
            'source_url': record['source_url'], 'file_path': record['relative_path'],
            'source_locator': str(row.get('source_locator') or ''),
            'source_format': Path(record['relative_path']).suffix.lower().lstrip('.'),
            'resolution': row['resolution'],
        })
    return output, rejected


def parse_document(job):
    root, record, station_list, signature, force = job
    root = Path(root)
    document_id = str(record['document_id'])
    if not re.fullmatch(r'[0-9]+', document_id):
        return {'document_id': document_id, 'source_id': record.get('source_id'),
                'status': 'error', 'rows': 0, 'reused': False,
                'issues': ['document_id inválido; no se accedió a la caché']}
    cache = root / 'processed/by_document' / f'{document_id}.parquet'
    audit_path = root / 'processed/by_document' / f'{document_id}.json'
    # These fields affect the extracted rows or their provenance. Download/run
    # timestamps and the downloader's reused flag deliberately do not affect it.
    key_input = {'signature': signature, 'stations': station_list,
                 'record': {name: record.get(name, '') for name in (
                     'source_id', 'report_id', 'document_id', 'sha256', 'source_url',
                     'relative_path', 'period_start', 'period_end')}}
    key = hashlib.sha256(json.dumps(key_input, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    audit = {'document_id': document_id, 'source_id': record['source_id'],
             'report_id': record['report_id'],
             'relative_path': record['relative_path'], 'source_url': record['source_url'],
             'document_sha256': record['sha256'], 'cache_key': key,
             'processed_at': now(), 'rows': 0, 'issues': [], 'reused': False}
    if Path(record['relative_path']).suffix.lower() == '.pdf' and 'eventos' in Path(record['relative_path']).name.lower():
        audit.update(record_type='quality_event', quality_review_required=True)
    try:
        path = contained_path(root, record['relative_path'])
        if sha256(path) != record['sha256']:
            raise ValueError('El original no coincide con su SHA-256')
        if not force and audit_path.exists():
            try:
                old = json.loads(audit_path.read_text())
            except (ValueError, OSError):
                old = {}
            if isinstance(old, dict) and old.get('cache_key') == key and not old.get('partial_extraction') and old.get('status') in {
                    'parsed', 'no_hourly_data', 'unsupported'}:
                if old.get('rows', 0) == 0:
                    return {**old, 'reused': True}
                if cache.exists() and sha256(cache) == old.get('parquet_sha256'):
                    return {**old, 'parquet_path': str(cache.relative_to(root)), 'reused': True}
        suffix = path.suffix.lower()
        if suffix in {'.xls', '.xlsx', '.xlsm'}:
            parser = parse_excel
            # Excel has explicit dates and may also declare its own period.
            # Its internal template checks remain active; portal bounds do not
            # discard observations that are explicitly dated in the workbook.
            bounds = {'period_start': '', 'period_end': ''}
        elif suffix == '.pdf':
            parser = parse_pdf_events if 'eventos' in path.name.lower() else parse_pdf
            # PDF tables sometimes print only a day number. Portal dates remain
            # a fallback where the PDF itself has no explicit year/month.
            bounds = {'period_start': record.get('period_start', ''),
                      'period_end': record.get('period_end', '')}
        else:
            audit.update(status='unsupported', issues=[f'Formato pendiente de extractor: {suffix}'])
            if cache.exists():
                cache.unlink()
            atomic_json(audit_path, audit)
            return audit
        result = parser(path, station_list, **bounds)
        if parser is parse_pdf_events:
            audit['record_type'] = 'quality_event'
            audit['quality_tables_recognized'] = result.get('tables_recognized', 0)
            audit['quality_review_required'] = (not result.get('tables_recognized') or any(
                re.search(r'error|missing_or_ambiguous|requires_review|unsupported|unrecognized', str(issue), re.I)
                for issue in result.get('issues', [])))
        rows, rejected = enrich(result['rows'], record, {s['id']: s for s in station_list})
        audit['issues'] = list(result.get('issues', []))
        extraction_errors = sum(bool(re.search(
            r'^(?:No se pudo leer |pdf_error:|dependency_missing:)|(?:^|:\s*)extraction_error:',
            str(issue), re.I)) for issue in audit['issues'])
        audit['extraction_errors'] = extraction_errors
        audit['partial_extraction'] = bool(rows and extraction_errors)
        audit['outside_report_period_rows'] = sum(row['outside_report_period'] for row in rows)
        if audit['outside_report_period_rows']:
            issue = (f"{audit['outside_report_period_rows']} filas con fechas explícitas fuera del "
                     f"período SNIFA {record.get('period_start', '')}..{record.get('period_end', '')}; "
                     "se conservan las fechas del archivo")
            audit['issues'].append(issue)
            LOG.warning('Documento %s: %s', document_id, issue)
        if rejected:
            audit['issues'].append(f'{rejected} filas rechazadas por identidad, fecha, hora o alcance')
        audit['rows'] = len(rows)
        audit['status'] = 'parsed' if rows else 'error' if extraction_errors else 'no_hourly_data'
        if rows:
            audit['first_date'] = min(row['date_local'] for row in rows)
            audit['last_date'] = max(row['date_local'] for row in rows)
            cache.parent.mkdir(parents=True, exist_ok=True)
            pending = cache.with_suffix('.parquet.part')
            pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMA), pending, compression='zstd')
            os.replace(pending, cache)
            audit['parquet_sha256'] = sha256(cache)
            audit['parquet_path'] = str(cache.relative_to(root))
        elif cache.exists():
            cache.unlink()  # caché derivada obsoleta, nunca el original
    except Exception as exc:
        audit.update(status='error', rows=0, issues=[f'{type(exc).__name__}: {exc}'])
    atomic_json(audit_path, audit)
    return audit


def sql_string(value):
    return "'" + str(value).replace("'", "''") + "'"


def consolidate(root, audits):
    root = Path(root)
    files = sorted({str(contained_path(root, item['parquet_path'])) for item in audits
                    if item['status'] == 'parsed' and item.get('rows')})
    out = root / 'processed'
    out.mkdir(parents=True, exist_ok=True)
    canonical = out / 'observaciones_horarias.parquet'
    coverage_path = out / 'cobertura.csv'
    conflicts = out / 'conflictos.parquet'
    pending = canonical.with_suffix('.parquet.part')
    coverage_pending = coverage_path.with_suffix('.csv.part')
    conflicts_pending = conflicts.with_suffix('.parquet.part')
    for path in (pending, coverage_pending, conflicts_pending):
        path.unlink(missing_ok=True)
    db = duckdb.connect()
    try:
        db.execute("SET memory_limit='1GB'")
        db.execute('SET threads=2')
        temporary = out / 'duckdb_tmp'
        temporary.mkdir(exist_ok=True)
        db.execute(f'SET temp_directory={sql_string(temporary)}')
        if files:
            db.read_parquet(files).create_view('all_rows')
        else:
            # Publish explicitly empty results instead of leaving the last run's
            # files behind when no current document could be parsed.
            db.register('all_rows', pa.Table.from_pylist([], schema=SCHEMA))
        pending_quality = sorted({(a['source_id'], int(a['report_id'])) for a in audits
                                  if a.get('quality_review_required') and a.get('report_id')})
        db.register('pending_quality', pa.Table.from_pylist(
            [{'source_id': source, 'report_id': report} for source, report in pending_quality],
            schema=pa.schema([('source_id', pa.string()), ('report_id', pa.int64())])))
        # EVENTOS PDFs are a separate publication from DATOS. Link their flags
        # before judging a numeric cell usable; keep the source IDs/locators.
        # Do not match across stations, gases, expedientes, or native hour labels.
        db.execute('''CREATE TEMP VIEW event_flags AS
            SELECT source_id,report_id,station_id,pollutant,date_local,hour_index,
                string_agg(DISTINCT quality_code,';' ORDER BY quality_code) AS event_codes,
                string_agg(DISTINCT CAST(document_id AS VARCHAR),';' ORDER BY CAST(document_id AS VARCHAR)) AS quality_document_ids,
                string_agg(DISTINCT CAST(document_id AS VARCHAR)||':'||source_locator,';' ORDER BY CAST(document_id AS VARCHAR)||':'||source_locator) AS quality_source_locators
            FROM all_rows WHERE record_type='quality_event' AND quality_code<>''
            GROUP BY ALL''')
        db.execute('''CREATE TEMP VIEW observations AS
            SELECT m.* EXCLUDE(quality_code,numeric_usable),
                CASE WHEN e.event_codes IS NULL THEN m.quality_code
                     WHEN m.quality_code='' OR m.quality_code=e.event_codes THEN e.event_codes
                     ELSE m.quality_code||';'||e.event_codes END AS quality_code,
                m.numeric_usable AND e.event_codes IS NULL AND
                    NOT(q.source_id IS NOT NULL AND m.source_format='pdf') AS numeric_usable,
                coalesce(e.quality_document_ids,'') AS quality_document_ids,
                coalesce(e.quality_source_locators,'') AS quality_source_locators,
                e.event_codes IS NOT NULL AS external_quality_flag,
                q.source_id IS NOT NULL AND m.source_format='pdf' AS quality_review_required
            FROM all_rows m LEFT JOIN event_flags e
              USING(source_id,report_id,station_id,pollutant,date_local,hour_index)
            LEFT JOIN pending_quality q ON q.source_id=m.source_id AND q.report_id=m.report_id
            WHERE coalesce(m.record_type,'measurement')='measurement' ''')
        # Published native date/hour are the keys: hour24 is not silently moved.
        # Distinct units remain distinct observations; different units at one hour
        # are flagged below. All candidates remain in by_document/ for inspection.
        keys = 'station_id, pollutant, date_local, hour_index, unit_key'
        db.execute(f'''CREATE TEMP TABLE selected AS
            SELECT *, count(*) OVER (PARTITION BY {keys}) AS source_count,
                count(DISTINCT value) OVER (PARTITION BY {keys}) > 1 AS value_conflict,
                count(DISTINCT unit_key) OVER (PARTITION BY station_id,pollutant,date_local,hour_index) > 1 AS unit_conflict,
                count(DISTINCT quality_code) OVER (PARTITION BY {keys}) > 1 AS quality_conflict,
                row_number() OVER (PARTITION BY {keys} ORDER BY
                    CASE WHEN source_format IN ('xls','xlsx','xlsm') THEN 0 ELSE 1 END,
                    CASE WHEN numeric_usable THEN 0 ELSE 1 END,
                    document_id DESC, source_locator, file_path, raw_value,
                    quality_code, unit_original, value NULLS LAST) AS selection_rank
            FROM (SELECT *, CASE WHEN unit='unknown' THEN
                'unknown:' || unit_original ELSE unit END AS unit_key FROM observations)''')
        db.execute(f'''COPY (SELECT * EXCLUDE(selection_rank,unit_key),
            numeric_usable AND NOT(value_conflict OR unit_conflict OR quality_conflict) AS usable_native,
            false AS ready_for_utc_join
            FROM selected WHERE selection_rank=1
            ORDER BY station_id,pollutant,date_local,hour_index,unit,unit_original)
            TO {sql_string(pending)} (FORMAT PARQUET, COMPRESSION ZSTD)''')
        coverage_sql = '''SELECT station_id,pollutant,unit,min(date_local) AS first_date,
            max(date_local) AS last_date,count(*) AS hourly_slots,count(value) AS numeric_values,
            count(*) FILTER(WHERE usable_native) AS usable_native,
            count(*) FILTER(WHERE value_conflict OR unit_conflict OR quality_conflict) AS conflicts,
            count(*) FILTER(WHERE value IS NULL) AS missing_values
            FROM read_parquet(?) GROUP BY ALL ORDER BY station_id,pollutant,unit'''
        cursor = db.execute(coverage_sql, [str(pending)])
        names = [column[0] for column in cursor.description]
        coverage = [dict(zip(names, row)) for row in cursor.fetchall()]
        # CSV sencillo para revisión humana; no sustituye el Parquet.
        import csv
        with coverage_pending.open('w', encoding='utf8', newline='') as stream:
            writer = csv.DictWriter(stream, names)
            writer.writeheader()
            writer.writerows(coverage)
        db.execute(f'''COPY (SELECT * EXCLUDE(selection_rank,unit_key) FROM selected
            WHERE value_conflict OR unit_conflict OR quality_conflict
            ORDER BY station_id,pollutant,date_local,hour_index,unit,document_id,source_locator)
            TO {sql_string(conflicts_pending)} (FORMAT PARQUET, COMPRESSION ZSTD)''')
        # Finish every artifact before replacing any published result.
        for staged, published in ((pending, canonical), (coverage_pending, coverage_path),
                                  (conflicts_pending, conflicts)):
            os.replace(staged, published)
        return {'observations': db.execute('SELECT count(*) FROM observations').fetchone()[0],
                'quality_events': db.execute("SELECT count(*) FROM all_rows WHERE record_type='quality_event'").fetchone()[0],
                'observations_with_external_flags': db.execute('SELECT count(*) FROM observations WHERE external_quality_flag').fetchone()[0],
                'quality_reports_pending': len(pending_quality),
                'observations_pending_quality_review': db.execute('SELECT count(*) FROM observations WHERE quality_review_required').fetchone()[0],
                'canonical_rows': sum(item['hourly_slots'] for item in coverage),
                'canonical_path': str(canonical.relative_to(root)), 'canonical_sha256': sha256(canonical),
                'coverage': coverage}
    finally:
        db.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raiz', type=Path, default=data_root())
    parser.add_argument('--config', type=Path, default=CONFIG)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--min-gb-libres', type=float, default=100)
    parser.add_argument('--reprocesar', action='store_true')
    parser.add_argument('--limite-documentos', type=int)
    parser.add_argument('--formatos', default='all',
                        help='Extensiones separadas por coma; omitir para procesar todos los formatos')
    args = parser.parse_args(argv)
    if args.workers < 1 or args.workers > 8:
        parser.error('--workers debe estar entre 1 y 8')
    if not math.isfinite(args.min_gb_libres) or args.min_gb_libres < 0:
        parser.error('--min-gb-libres debe ser finito y no negativo')
    if args.limite_documentos is not None and args.limite_documentos < 1:
        parser.error('--limite-documentos debe ser positivo')
    if not set(args.formatos.lower().split(',')) <= {'all', 'pdf', 'xls', 'xlsx', 'xlsm'}:
        parser.error('--formatos admite all o pdf,xls,xlsx,xlsm')
    root = args.raiz.expanduser().resolve()
    check_disk(root, args.min_gb_libres)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s', datefmt='%H:%M:%S')
    (root / 'processed').mkdir(parents=True, exist_ok=True)
    with (root / '.process.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return run(args, root)


def run(args, root):
    config = json.loads(args.config.read_text())
    atomic_json(root / 'processed/station_config.json', config)
    manifest_path = root / 'metadata/download_manifest.json'
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
    formats = set(getattr(args, 'formatos', 'all').lower().split(','))
    records = [item for item in manifest['documents']
               if item.get('status') == 'downloaded' and item.get('role') == 'measurements'
               and ('all' in formats or Path(item.get('relative_path', '')).suffix.lower().lstrip('.') in formats)]
    records.sort(key=lambda item: int(item['document_id']))
    if args.limite_documentos:
        records = records[:args.limite_documentos]
    script_dir = Path(__file__).parent
    signature = hashlib.sha256(''.join(sha256(path) for path in [Path(__file__),
        script_dir / '_snifa_excel.py', script_dir / '_snifa_pdf.py', args.config]).encode()).hexdigest()
    common_signature = sha256(Path(__file__)) + sha256(args.config)
    format_signatures = {kind: hashlib.sha256((common_signature + sha256(script_dir / filename)).encode()).hexdigest()
                         for kind, filename in [('pdf', '_snifa_pdf.py'), ('excel', '_snifa_excel.py')]}
    jobs = [(str(root), record, [s for s in config['stations'] if s['source_id'] == record['source_id']],
             format_signatures['pdf' if Path(record['relative_path']).suffix.lower() == '.pdf' else 'excel'],
             args.reprocesar) for record in records]
    LOG.info('Procesando %s documentos descargados de medición', len(jobs))
    audits = []
    with futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        pending = {pool.submit(parse_document, job): job[1]['document_id'] for job in jobs}
        for i, future in enumerate(futures.as_completed(pending), 1):
            audit = future.result()
            audits.append(audit)
            if i % 10 == 0 or i == len(jobs):
                LOG.info('%s/%s documentos; %s filas extraídas', i, len(jobs), sum(a['rows'] for a in audits))
    check_disk(root, args.min_gb_libres)
    summary = consolidate(root, audits)
    summary.update(network_id='snifa_adicional', schema_version=1, processor_version=VERSION,
                   processor_signature=signature, processed_at=now(),
                   formats_selected=sorted(formats),
                   download_manifest_sha256=manifest_digest,
                   documents_selected=len(records), documents_in_manifest=len(manifest['documents']),
                   documents_parsed=sum(a['status'] == 'parsed' for a in audits),
                   documents_without_hourly_data=sum(a['status'] == 'no_hourly_data' for a in audits),
                   unsupported=sum(a['status'] == 'unsupported' for a in audits),
                   processing_errors=sum(a['status'] == 'error' for a in audits),
                   documents_with_extraction_errors=sum(bool(a.get('extraction_errors')) for a in audits),
                   extraction_errors=sum(a.get('extraction_errors', 0) for a in audits),
                   documents_partially_extracted=sum(bool(a.get('partial_extraction')) for a in audits),
                   outside_report_period_rows=sum(a.get('outside_report_period_rows', 0) for a in audits),
                   documents_outside_report_period=sum(bool(a.get('outside_report_period_rows')) for a in audits),
                   download_errors=sum(a.get('status') == 'error' for a in manifest['documents']),
                   clock_status='unverified', ready_for_utc_join=False,
                   complete_historical_coverage=False,
                   documents=sorted(audits, key=lambda a: int(a['document_id'])))
    atomic_json(root / 'processed/processing_report.json', summary)
    LOG.info('Resultado: %s filas originales; %s horas canónicas; %s errores; %s formatos pendientes',
             summary['observations'], summary['canonical_rows'], summary['processing_errors'], summary['unsupported'])
    return 2 if summary['processing_errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
