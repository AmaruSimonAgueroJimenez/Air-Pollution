"""Offline source integrity, resumability and native-clock SNIFA preparation."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import csv
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import preparar_snifa_modelado as m


class PrepareSnifaTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='prepare-snifa-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.station = {'id': 'sapu', 'name': 'SAPU', 'aliases': ['SAPU'],
                        'source_id': 'masisa_cabrero', 'pollutants': ['no2', 'so2'],
                        'latitude': -37.0, 'longitude': -72.0,
                        'coordinate_source_url': 'https://example.test/coordinates',
                        'timezone_status': 'unverified'}
        self.stations = {'sapu': self.station}
        network = patch('socket.socket.connect', side_effect=AssertionError('offline tests'))
        network.start()
        self.addCleanup(network.stop)

    def observation(self, **changes):
        row = {'station_id': 'sapu', 'pollutant': 'no2', 'date': '2025-06-01',
               'hour_label': '0100', 'value': 1.0, 'raw_value': '1', 'unit': 'ppb',
               'quality_code': '', 'source_locator': 'NO2!C11', 'resolution': 'hourly'}
        row.update(changes)
        return row

    def source(self, document_id=1, suffix='xlsx', **changes):
        relative = f'raw/masisa_cabrero/42/{document_id}_SAPU.{suffix}'
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f'original fixture {document_id}'.encode())
        record = {'document_id': str(document_id), 'report_id': '42', 'source_id': 'masisa_cabrero',
                  'relative_path': relative, 'sha256': m.sha256(path),
                  'source_url': f'https://example.test/document/{document_id}',
                  'period_start': '2025-06-01', 'period_end': '2025-06-30',
                  'status': 'downloaded', 'role': 'measurements'}
        record.update(changes)
        return record

    def job(self, record, force=False, stations=None):
        return (str(self.root), record, stations or [self.station], 'test-parser-signature', force)

    def cache(self, rows, document_id, suffix='xlsx'):
        record = self.source(document_id, suffix)
        enriched, rejected = m.enrich(rows, record, self.stations)
        self.assertEqual(rejected, 0)
        path = self.root / 'processed/by_document' / f'{document_id}.parquet'
        path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pylist(enriched, schema=m.SCHEMA), path)
        return {'status': 'parsed', 'rows': len(enriched), 'parquet_path': str(path.relative_to(self.root)),
                'document_id': str(document_id), 'parquet_sha256': m.sha256(path)}

    def canonical(self):
        return pq.read_table(self.root / 'processed/observaciones_horarias.parquet').to_pylist()

    def test_pdf_event_flags_join_before_selection_and_keep_numeric_source(self):
        values = self.cache([self.observation(value=13, raw_value='13'),
                             self.observation(hour_label='0200', value=4)], 1, 'pdf')
        events = self.cache([self.observation(value=None, raw_value='2.h', unit='unknown',
                            quality_code='2.h', resolution='quality_event',
                            source_locator='page:1;column:1;timestamp:202506010100')], 2, 'pdf')
        result = m.consolidate(self.root, [values, events])
        self.assertEqual(result['observations'], 2)
        self.assertEqual(result['quality_events'], 1)
        self.assertEqual(result['canonical_rows'], 2)
        rows = {r['hour_index']: r for r in self.canonical()}
        self.assertEqual(rows[1]['value'], 13)
        self.assertEqual(rows[1]['quality_code'], '2.h')
        self.assertEqual(rows[1]['quality_document_ids'], '2')
        self.assertFalse(rows[1]['numeric_usable'])
        self.assertFalse(rows[1]['usable_native'])
        self.assertTrue(rows[1]['external_quality_flag'])
        self.assertTrue(rows[2]['usable_native'])
        self.assertEqual(rows[1]['source_count'], 1)

    def test_unreadable_external_events_require_quality_review_for_pdf(self):
        values = self.cache([self.observation()], 1, 'pdf')
        pending = {'status': 'no_hourly_data', 'rows': 0, 'source_id': 'masisa_cabrero',
                   'report_id': '42', 'quality_review_required': True}
        result = m.consolidate(self.root, [values, pending])
        row = self.canonical()[0]
        self.assertTrue(row['quality_review_required'])
        self.assertFalse(row['numeric_usable'])
        self.assertFalse(row['usable_native'])
        self.assertEqual(result['observations_pending_quality_review'], 1)

    def test_quality_events_never_cross_report_boundaries(self):
        values = self.cache([self.observation()], 1, 'pdf')
        event_record = self.source(2, 'pdf', report_id='43')
        event_row = self.observation(value=None, quality_code='2.h', unit='unknown',
                                     resolution='quality_event')
        rows, _ = m.enrich([event_row], event_record, self.stations)
        path = self.root / 'event.parquet'
        pq.write_table(pa.Table.from_pylist(rows, schema=m.SCHEMA), path)
        m.consolidate(self.root, [values, {'status': 'parsed', 'rows': 1,
                                         'parquet_path': str(path.relative_to(self.root))}])
        row = self.canonical()[0]
        self.assertTrue(row['usable_native'])
        self.assertFalse(row['external_quality_flag'])

    def test_units_and_hours_are_normalized_without_conversion(self):
        for source, expected in [('µg/m³N', 'ug/m3N'), ('μg / m^3', 'ug/m3'),
                                 ('mg/Nm3', 'mg/m3N'), ('PPM', 'ppm'), ('ppb', 'ppb'),
                                 ('', 'unknown'), ('unexpected', 'unknown')]:
            self.assertEqual(m.canonical_unit(source), expected)
        for source, expected in [('0100', 1), ('100', 1), ('2400', 24), ('24:00:00', 24),
                                 ('0000', 0), ('0', 0), ('1.0', 1), ('0.5', 12)]:
            self.assertEqual(m.hour_index(source), expected)
        for source in ['0030', '23:59', '25', 'NaN', '-1', '', None]:
            self.assertIsNone(m.hour_index(source))
        record = self.source()
        rows, rejected = m.enrich([self.observation(value=2, unit='µg/m³N', hour_label='2400')], record, self.stations)
        self.assertEqual(rejected, 0)
        self.assertEqual(rows[0]['value'], 2)
        self.assertEqual(rows[0]['unit_original'], 'µg/m³N')
        self.assertEqual(rows[0]['unit'], 'ug/m3N')
        self.assertEqual(rows[0]['date_local'], '2025-06-01')
        self.assertEqual(rows[0]['hour_label'], '2400')
        self.assertEqual(rows[0]['hour_index'], 24)
        self.assertIsNone(rows[0]['timestamp_utc'])

    def test_identity_scope_and_malformed_rows_cannot_enter_enriched_data(self):
        record = self.source()
        wrong_source = {**self.station, 'id': 'other', 'source_id': 'another_source'}
        stations = {**self.stations, 'other': wrong_source}
        invalid = [self.observation(station_id='unknown'), self.observation(station_id='other'),
                   self.observation(pollutant='no'), self.observation(pollutant='pm10'),
                   self.observation(resolution='eight_hour'), self.observation(hour_label='25'),
                   self.observation(date='2025-02-30'),
                   self.observation(value='broken'), self.observation(value=True)]
        rows, rejected = m.enrich([self.observation(), *invalid], record, stations)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rejected, len(invalid))

    def test_zero_missing_negative_unknown_and_quality_survive(self):
        samples = [self.observation(value=0, raw_value=0), self.observation(value=None, raw_value=''),
                   self.observation(value=-1, raw_value='-1'), self.observation(unit='unknown'),
                   self.observation(value=1, quality_code='2.e', raw_value='2.e'),
                   self.observation(value=float('nan'), raw_value='NaN')]
        rows, rejected = m.enrich(samples, self.source(), self.stations)
        self.assertEqual(rejected, 0)
        self.assertEqual([row['numeric_usable'] for row in rows], [True, False, False, False, False, False])
        self.assertEqual(rows[0]['raw_value'], '0')
        self.assertIsNone(rows[1]['value'])
        self.assertEqual(rows[2]['value'], -1)
        self.assertEqual(rows[3]['unit'], 'unknown')
        self.assertEqual(rows[4]['quality_code'], '2.e')
        self.assertIsNone(rows[5]['value'])

    def test_resume_uses_stable_key_and_invalidates_changed_provenance(self):
        record = self.source()
        with patch.object(m, 'parse_excel', return_value={'rows': [self.observation()], 'issues': []}) as parser:
            first = m.parse_document(self.job(record))
            self.assertEqual(first['status'], 'parsed')
            second = m.parse_document(self.job({**record, 'reused': True, 'downloaded_at': 'different'}))
            self.assertTrue(second['reused'])
            self.assertEqual(parser.call_count, 1)
            revised = {**record, 'report_id': '43', 'source_url': 'https://example.test/revised'}
            third = m.parse_document(self.job(revised))
            self.assertFalse(third['reused'])
            stored = pq.read_table(self.root / third['parquet_path']).to_pylist()[0]
            self.assertEqual(stored['report_id'], 43)
            self.assertEqual(stored['source_url'], revised['source_url'])
            changed_station = {**self.station, 'latitude': -37.2}
            fourth = m.parse_document(self.job(revised, stations=[changed_station]))
            self.assertFalse(fourth['reused'])
            self.assertEqual(pq.read_table(self.root / fourth['parquet_path']).to_pylist()[0]['latitude'], -37.2)
            self.assertEqual(parser.call_count, 3)

    def test_cache_does_not_hide_changed_original(self):
        record = self.source()
        with patch.object(m, 'parse_excel', return_value={'rows': [self.observation()], 'issues': []}) as parser:
            m.parse_document(self.job(record))
            (self.root / record['relative_path']).write_bytes(b'changed source')
            result = m.parse_document(self.job(record))
            self.assertEqual(result['status'], 'error')
            self.assertEqual(result['rows'], 0)
            self.assertFalse(result['reused'])
            self.assertIn('SHA-256', result['issues'][0])
            self.assertEqual(parser.call_count, 1)

    def test_corrupt_derived_cache_and_audit_are_rebuilt_force_reparses(self):
        record = self.source()
        with patch.object(m, 'parse_excel', return_value={'rows': [self.observation()], 'issues': []}) as parser:
            first = m.parse_document(self.job(record))
            (self.root / first['parquet_path']).write_bytes(b'broken parquet')
            self.assertFalse(m.parse_document(self.job(record))['reused'])
            (self.root / 'processed/by_document/1.json').write_text('{broken')
            self.assertEqual(m.parse_document(self.job(record))['status'], 'parsed')
            self.assertFalse(m.parse_document(self.job(record, force=True))['reused'])
            self.assertEqual(parser.call_count, 4)

    def test_empty_reparse_removes_obsolete_cache_and_remains_resumable(self):
        record = self.source()
        with patch.object(m, 'parse_excel', return_value={'rows': [self.observation()], 'issues': []}):
            first = m.parse_document(self.job(record))
        revised = {**record, 'period_start': '2025-06-02'}
        with patch.object(m, 'parse_excel', return_value={'rows': [], 'issues': []}) as parser:
            result = m.parse_document(self.job(revised))
            self.assertEqual(result['status'], 'no_hourly_data')
            self.assertFalse((self.root / first['parquet_path']).exists())
            self.assertTrue(m.parse_document(self.job(revised))['reused'])
            self.assertEqual(parser.call_count, 1)

    def test_explicit_source_dates_override_portal_period_for_excel_and_pdf(self):
        for suffix, parser_name in [('xlsx', 'parse_excel'), ('pdf', 'parse_pdf')]:
            with self.subTest(suffix=suffix):
                record = self.source(suffix=suffix, period_start='2025-07-01', period_end='2025-07-31')
                with patch.object(m, parser_name, return_value={'rows': [self.observation()], 'issues': []}) as parser, \
                        self.assertLogs(m.LOG, level='WARNING') as log:
                    audit = m.parse_document(self.job(record))
                expected_bounds = {'period_start': '', 'period_end': ''} if suffix == 'xlsx' else {
                    'period_start': '2025-07-01', 'period_end': '2025-07-31'}
                parser.assert_called_once_with((self.root / record['relative_path']).resolve(), [self.station], **expected_bounds)
                self.assertEqual(audit['status'], 'parsed')
                self.assertEqual(audit['rows'], 1)
                self.assertEqual(audit['outside_report_period_rows'], 1)
                self.assertTrue(any('se conservan las fechas del archivo' in line for line in log.output))
                stored = pq.read_table(self.root / audit['parquet_path']).to_pylist()[0]
                self.assertEqual(stored['date_local'], '2025-06-01')
                self.assertTrue(stored['outside_report_period'])
                self.assertIsNone(stored['timestamp_utc'])
        rows, _ = m.enrich([self.observation()], self.source(), self.stations)
        self.assertFalse(rows[0]['outside_report_period'])

    def test_reader_and_dependency_failures_are_errors_and_retry(self):
        record = self.source()
        issues = ['No se pudo leer input.xls: corrupt header', 'pdf_error:PdfReadError:corrupt',
                  'dependency_missing:pypdf: requires pypdf', 'page:3: extraction_error:ValueError:test']
        for issue in issues:
            with self.subTest(issue=issue), patch.object(m, 'parse_excel', return_value={
                    'rows': [], 'issues': [issue]}) as parser:
                for _ in range(2):
                    result = m.parse_document(self.job(record))
                    self.assertEqual(result['status'], 'error')
                    self.assertEqual(result['extraction_errors'], 1)
                    self.assertFalse(result['reused'])
                self.assertEqual(parser.call_count, 2)
        with patch.object(m, 'parse_excel', return_value={'rows': [], 'issues': [
                'page:3: image_only_requires_ocr_review', 'no_hourly_rows_extracted: coverage_not_established']}):
            result = m.parse_document(self.job(record))
            self.assertEqual(result['status'], 'no_hourly_data')
            self.assertEqual(result['extraction_errors'], 0)
            self.assertTrue(m.parse_document(self.job(record))['reused'])

    def test_partial_page_failure_keeps_observations_and_retries_incomplete_cache(self):
        record = self.source()
        with patch.object(m, 'parse_excel', return_value={'rows': [self.observation()],
                'issues': ['page:3: extraction_error:ValueError:test']}) as parser:
            result = m.parse_document(self.job(record))
            self.assertEqual(result['status'], 'parsed')
            self.assertTrue(result['partial_extraction'])
            self.assertEqual(result['extraction_errors'], 1)
            self.assertEqual(result['rows'], 1)
            self.assertFalse(m.parse_document(self.job(record))['reused'])
            self.assertEqual(parser.call_count, 2)

    def test_relative_path_must_stay_within_root_even_when_cache_exists(self):
        record = self.source()
        for relative in ['../elsewhere.xlsx', str(self.root / record['relative_path'])]:
            with self.subTest(relative=relative), patch.object(m, 'parse_excel') as parser:
                result = m.parse_document(self.job({**record, 'relative_path': relative}))
                self.assertEqual(result['status'], 'error')
                parser.assert_not_called()
        invalid = m.parse_document(self.job({**record, 'document_id': '../escape'}))
        self.assertEqual(invalid['status'], 'error')
        self.assertFalse((self.root / 'processed/escape.json').exists())

    def test_dedup_selects_excel_and_keeps_native_day_hour(self):
        first = self.cache([self.observation(), self.observation(hour_label='2400', value=2)], 1, 'pdf')
        second = self.cache([self.observation(), self.observation(date='2025-06-02', hour_label='0000', value=3)], 2)
        summary = m.consolidate(self.root, [first, second, second])
        self.assertEqual(summary['observations'], 4)
        self.assertEqual(summary['canonical_rows'], 3)
        rows = self.canonical()
        duplicate = next(row for row in rows if row['hour_index'] == 1)
        self.assertEqual(duplicate['source_count'], 2)
        self.assertEqual(duplicate['document_id'], 2)
        self.assertFalse(duplicate['value_conflict'])
        self.assertTrue(duplicate['usable_native'])
        self.assertEqual({(row['date_local'], row['hour_index']) for row in rows},
                         {('2025-06-01', 1), ('2025-06-01', 24), ('2025-06-02', 0)})
        self.assertTrue(all(row['timestamp_utc'] is None and not row['ready_for_utc_join'] for row in rows))
        m.consolidate(self.root, [second, first])
        self.assertEqual(self.canonical(), rows)

    def test_value_quality_and_unit_conflicts_keep_all_candidates(self):
        first = self.cache([self.observation(hour_label='1', value=1),
                            self.observation(hour_label='2', value=3, unit='ppb'),
                            self.observation(hour_label='3', value=1),
                            self.observation(hour_label='4', unit='unrecognized-A')], 1)
        second = self.cache([self.observation(hour_label='1', value=2),
                             self.observation(hour_label='2', value=3, unit='µg/m³N'),
                             self.observation(hour_label='3', value=1, quality_code='2.e'),
                             self.observation(hour_label='4', unit='unrecognized-B')], 2)
        summary = m.consolidate(self.root, [first, second])
        rows = self.canonical()
        self.assertEqual(summary['canonical_rows'], 6)
        self.assertTrue(all(not row['usable_native'] for row in rows))
        self.assertTrue(next(row for row in rows if row['hour_index'] == 1)['value_conflict'])
        self.assertTrue(next(row for row in rows if row['hour_index'] == 3)['quality_conflict'])
        self.assertTrue(all(row['unit_conflict'] for row in rows if row['hour_index'] in {2, 4}))
        unknown = [row for row in rows if row['hour_index'] == 4]
        self.assertEqual({row['unit_original'] for row in unknown}, {'unrecognized-A', 'unrecognized-B'})
        self.assertEqual(pq.read_table(self.root / 'processed/conflictos.parquet').num_rows, 8)
        self.assertEqual(pq.read_table(self.root / first['parquet_path']).num_rows, 4)
        self.assertEqual(pq.read_table(self.root / second['parquet_path']).num_rows, 4)

    def test_empty_run_replaces_all_old_outputs_with_empty_results(self):
        audit = self.cache([self.observation()], 1)
        m.consolidate(self.root, [audit])
        summary = m.consolidate(self.root, [])
        self.assertEqual(summary['observations'], 0)
        self.assertEqual(summary['canonical_rows'], 0)
        self.assertEqual(self.canonical(), [])
        self.assertEqual(pq.read_table(self.root / 'processed/conflictos.parquet').num_rows, 0)
        with (self.root / 'processed/cobertura.csv').open() as stream:
            reader = csv.DictReader(stream)
            self.assertIn('station_id', reader.fieldnames)
            self.assertEqual(list(reader), [])

    def test_failed_staging_does_not_replace_published_results(self):
        first = self.cache([self.observation()], 1)
        m.consolidate(self.root, [first])
        before = {path.name: m.sha256(path) for path in (self.root / 'processed').iterdir() if path.is_file()}
        second = self.cache([self.observation(value=99)], 2)
        with patch('csv.DictWriter.writerows', side_effect=OSError('simulated write failure')):
            with self.assertRaises(OSError):
                m.consolidate(self.root, [second])
        for name, digest in before.items():
            self.assertEqual(m.sha256(self.root / 'processed' / name), digest)

    def test_run_consumes_downloader_manifest_keys_and_resumes(self):
        record = self.source()
        m.atomic_json(self.root / 'metadata/download_manifest.json', {'documents': [
            record, {**record, 'document_id': '2', 'role': 'report'},
            {**record, 'document_id': '3', 'status': 'error'}]})
        config_path = self.root / 'stations.json'
        m.atomic_json(config_path, {'stations': [self.station]})
        args = SimpleNamespace(config=config_path, limite_documentos=None, workers=2,
                               min_gb_libres=0, reprocesar=False)
        with patch.object(m.futures, 'ProcessPoolExecutor', ThreadPoolExecutor), \
                patch.object(m, 'parse_excel', return_value={'rows': [self.observation()], 'issues': []}) as parser:
            self.assertEqual(m.run(args, self.root), 0)
            self.assertEqual(m.run(args, self.root), 0)
            self.assertEqual(parser.call_count, 1)
        report = json.loads((self.root / 'processed/processing_report.json').read_text())
        self.assertEqual(report['documents_selected'], 1)
        self.assertEqual(report['documents_parsed'], 1)
        self.assertEqual(report['download_errors'], 1)
        self.assertEqual(report['documents'][0]['relative_path'], record['relative_path'])
        self.assertTrue(report['documents'][0]['reused'])
        self.assertFalse(report['ready_for_utc_join'])
        self.assertEqual(self.canonical()[0]['file_path'], record['relative_path'])

    def test_invalid_cli_limits_fail_before_touching_disk(self):
        invalid = [('--min-gb-libres', 'nan'), ('--min-gb-libres', 'inf'),
                   ('--min-gb-libres', '-1'), ('--limite-documentos', '0'),
                   ('--limite-documentos', '-1'), ('--workers', '0'), ('--workers', '9')]
        for arguments in invalid:
            with self.subTest(arguments=arguments), patch.object(m, 'check_disk') as disk, \
                    patch('sys.stderr'):
                with self.assertRaises(SystemExit) as error:
                    m.main(list(arguments))
                self.assertEqual(error.exception.code, 2)
                disk.assert_not_called()


if __name__ == '__main__':
    unittest.main()
