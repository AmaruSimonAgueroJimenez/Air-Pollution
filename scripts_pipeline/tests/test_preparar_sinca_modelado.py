"""SINCA preparation safety/semantics: synthetic sources; no network, no originals written."""
from __future__ import annotations

import ast
from collections import Counter
import copy
import csv
import json
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import preparar_sinca_modelado as m
import numpy as np
import pandas as pd
import pyarrow.parquet as pq


class SincaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='sinca-modelado-unit-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'originales'
        self.source.mkdir()
        self.output = self.root / 'derivados'
        self.output.mkdir()
        self.policy = self.root / 'politica.json'
        self.policy.write_text(json.dumps({'sinca': {
            'reloj_fuente': 'hora_local_civil_sinca_sin_offset',
            'zona_iana_default': 'America/Santiago',
            'zonas_iana_por_region': {'RXI': 'America/Coyhaique', 'RXII': 'America/Punta_Arenas'}}}))
        self.feature = {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [-70.1, -20.3]},
                        'properties': {'estacion': '117', 'region_sinca': 'RI', 'nombre': 'Sintética',
                            'cod_comuna_geografica': 1107, 'comuna_geografica': 'A', 'comuna_sinca': 'B',
                            'coincide_comuna_sinca': False, 'qc_comuna': 'discrepancia',
                            'usable_geoespacial': True}}
        (self.source / 'estaciones_georreferenciadas.geojson').write_text(json.dumps({
            'type': 'FeatureCollection', 'features': [self.feature]}))
        self.rows = []
        # Any attempted network operation during an offline test is a failure.
        self.network = patch('socket.socket.connect', side_effect=AssertionError('network forbidden'))
        self.network.start(); self.addCleanup(self.network.stop)

    def add_source(self, body, start='2024-09-01', end='2024-09-10'):
        p = self.source / 'pm25' / 'horario' / f'RI_117_horario_{start}_{end}.csv'
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open('w', newline='') as stream:
            writer = csv.writer(stream, delimiter=';', lineterminator='\n')
            writer.writerow(['FECHA (YYMMDD)', 'HORA (HHMM)', ''])
            for row in body:
                writer.writerow(row + [''] * (6 - len(row)))
        row = {'region': 'RI', 'estacion': '117', 'nombre': 'Sintética', 'contaminante': 'pm25',
               'resolucion': 'horario', 'desde': start, 'hasta': end, 'ruta': str(p),
               'bytes': str(p.stat().st_size), 'sha256': m.sha256(p), 'filas': str(len(body))}
        self.rows.append(row)
        return p

    def inputs(self):
        with (self.source / 'manifiesto_descarga.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(self.rows[0]))
            writer.writeheader(); writer.writerows(self.rows)
        return m.load_inputs(self.source, self.policy, m.REPO / 'scripts_superficie/afg_lib.py', '117', 'pm25')

    def publish(self, inp, **kw):
        with m.exclusive_lock(self.output / '.writer.lock'), patch.object(m, 'check_disk', return_value=500*m.GIB):
            return m.process_series(inp['rows'], inp, self.output, volume_uuid=None, **kw)

    def test_leaf_parser_exact_and_no_import_side_effect(self):
        path = self.add_source([['240901', '0100', '0'], ['240901', '0200', '', '2,5'],
                                ['240901', '0300', '', '', '-3'], ['wrong', '0400', '4']])
        inp = self.inputs()
        original_ast = ast.parse((m.REPO / 'scripts_superficie/afg_lib.py').read_bytes())
        leaf = next(n for n in original_ast.body if isinstance(n, ast.FunctionDef) and n.name == 'leer_sinca_serie')
        namespace = {'np': np, 'pd': pd, 'Path': Path}
        exec(compile(ast.Module(body=[leaf], type_ignores=[]), 'frozen-original', 'exec'), namespace)
        pd.testing.assert_frame_equal(inp['parser'](path), namespace['leer_sinca_serie'](path))
        parsed = m.read_source(inp['rows'][0], inp)
        self.assertEqual(parsed['obs'].tolist(), [0, 2.5, -3, 4])
        self.assertEqual(parsed['qc_observacion'].tolist(), ['validado', 'preliminar', 'no_validado', 'validado'])
        self.assertTrue(pd.isna(parsed.iloc[-1]['ts_local']))
        self.assertNotIn('afg_lib', sys.modules)

    def test_overlaps_match_existing_rank_and_all_alternatives_survive(self):
        self.add_source([['240901', '0100', '10'], ['240901', '0200', '', '', '12'],
                         ['240901', '0300', '2000'], ['240901', '0400', '-1']])
        self.add_source([['240901', '0100'], ['240901', '0200', '', '13'],
                         ['240901', '0300', '', '', '15'], ['240901', '0400', '-2']], end='2024-09-11')
        inp = self.inputs()
        sources_before = {r['ruta']: m.sha256(r['ruta']) for r in inp['rows']}
        selected, alternatives, stats = m.consolidate(inp['rows'], inp)
        a, b = selected.to_pandas(), alternatives.to_pandas()
        self.assertEqual(a.obs.tolist(), [10, 13, 15, -2])
        self.assertEqual(stats['filas_en_ventana'], 8)
        self.assertEqual(len(a) + len(b), 8)
        self.assertIn(2000, b.obs.tolist())
        self.assertTrue(a.iloc[-1].fuera_rango_afg)
        combined = pd.concat([m.read_source(r, inp) for r in inp['rows']], ignore_index=True)
        keys = ['source_path', 'source_sha256', 'source_line', 'fecha_original', 'hora_original',
                'v_validado_original', 'v_preliminar_original', 'v_no_validado_original', 'extra_original']
        self.assertEqual(Counter(map(tuple, combined[keys].to_numpy())),
                         Counter(map(tuple, pd.concat([a, b])[keys].to_numpy())))
        expected = inp['rank'](combined.copy(), 'pm25').sort_values('ts_local')
        self.assertEqual(a.source_path.tolist(), expected.source_path.tolist())
        self.assertEqual(a.qc_observacion.tolist(), expected.qc_observacion.tolist())
        self.assertEqual(sources_before, {p: m.sha256(p) for p in sources_before})

    def test_unvalidated_zero_missing_and_unknown_units_preserved(self):
        self.add_source([['240901', '0000', '', '', '0'], ['240901', '0100'], ['240901', '0200', '2001']])
        inp = self.inputs(); selected, alt, _ = m.consolidate(inp['rows'], inp)
        df = selected.to_pandas()
        self.assertEqual(df.iloc[0].obs, 0)
        self.assertFalse(df.iloc[0].valor_faltante)
        self.assertEqual(df.iloc[0].qc_observacion, 'no_validado')
        self.assertTrue(df.iloc[1].valor_faltante)
        self.assertEqual(df.iloc[2].obs, 2001)
        self.assertTrue(df.iloc[2].fuera_rango_afg)
        self.assertTrue(df.unidad.isna().all())
        self.assertFalse(df.unidad_confirmada.any())
        self.assertEqual(alt.schema, selected.schema)

    def test_utc_never_confirmed_dst_not_shifted_or_collapsed(self):
        self.add_source([['240406', '2300', '2'], ['240406', '2300', '3'],
                         ['240908', '0000', '4'], ['invalid', '0100', '9']], start='2024-04-01')
        inp = self.inputs(); selected, alternatives, _ = m.consolidate(inp['rows'], inp)
        df = pd.concat([selected.to_pandas(), alternatives.to_pandas()])
        self.assertEqual(len(df), 4)
        self.assertTrue(df.ts_utc.isna().all())
        repeated = df[df.fecha_original == '240406']
        self.assertTrue(repeated.hora_repetida_en_fuente.all())
        self.assertEqual(repeated.qc_hora.tolist(), ['ambigua_no_resuelta']*2)
        self.assertEqual((repeated.utc_candidato_2 - repeated.utc_candidato_1).dt.total_seconds().tolist(), [3600]*2)
        missing = df[df.fecha_original == '240908'].iloc[0]
        self.assertEqual(missing.qc_hora, 'inexistente_no_desplazada')
        self.assertTrue(pd.isna(missing.utc_candidato_1))
        invalid = df[df.fecha_original == 'invalid'].iloc[0]
        self.assertEqual(invalid.obs, 9)
        self.assertTrue(invalid.timestamp_invalido)

    def test_zone_candidates_use_correct_chilean_regions(self):
        local = pd.Series(pd.to_datetime(['2025-07-01 12:00']))
        santiago, _, _ = m.time_candidates(local, 'America/Santiago')
        coyhaique, _, _ = m.time_candidates(local, 'America/Coyhaique')
        punta, _, _ = m.time_candidates(local, 'America/Punta_Arenas')
        self.assertEqual(santiago.iloc[0].hour, 16)
        self.assertEqual(coyhaique.iloc[0].hour, 15)
        self.assertEqual(punta.iloc[0].hour, 15)

    def test_geo_discrepancies_and_wkb_preserved_without_aggregation(self):
        self.add_source([['240901', '0000', '2'], ['240901', '0100', '8']])
        inp = self.inputs(); table, _, _ = m.consolidate(inp['rows'], inp)
        df = table.to_pandas()
        self.assertEqual(df.obs.tolist(), [2, 8])
        self.assertEqual(df.qc_comuna.tolist(), ['discrepancia']*2)
        self.assertFalse(df.coincide_comuna_sinca.any())
        self.assertEqual(struct.unpack('<BIdd', df.iloc[0].geometry_wkb), (1, 1, -70.1, -20.3))
        self.assertEqual(df.fuente_geo_sha256.nunique(), 1)

    def test_window_no_calendar_imputation_and_invalid_rows_retained(self):
        self.add_source([['240901', '0100', '1'], ['240903', '0100', '3'], ['bad', 'bad', '7']])
        inp = self.inputs(); selected, _, stats = m.consolidate(inp['rows'], inp, since='2024-09-02', until='2024-09-03')
        self.assertEqual(selected.num_rows, 2)
        self.assertEqual(selected['obs'].to_pylist(), [3, 7])
        self.assertEqual(stats['filas_originales_leidas'], 3)

    def test_empty_window_is_valid_typed_publication(self):
        self.add_source([['240901', '0100', '1']])
        inp = self.inputs(); result = self.publish(inp, since='2024-09-02', until='2024-09-03')
        proof = m.validate_publication(result['path'])
        self.assertEqual(proof['statistics']['filas_en_ventana'], 0)

    def test_hash_mismatch_and_bad_identity_rejected(self):
        path = self.add_source([['240901', '0100', '1']])
        inp = self.inputs(); path.write_text(path.read_text().replace(';1;', ';2;'))
        with self.assertRaisesRegex(ValueError, 'hash/tamaño'):
            m.read_source(inp['rows'][0], inp)
        self.rows[0]['estacion'] = 'different'
        with self.assertRaisesRegex(ValueError, 'identidad'):
            self._load_invalid_rows()

    def _load_invalid_rows(self):
        with (self.source / 'manifiesto_descarga.csv').open('w', newline='') as stream:
            w = csv.DictWriter(stream, fieldnames=list(self.rows[0])); w.writeheader(); w.writerows(self.rows)
        return m.load_inputs(self.source, self.policy, m.REPO / 'scripts_superficie/afg_lib.py')

    def test_path_outside_source_and_duplicate_manifest_rejected(self):
        self.add_source([['240901', '0100', '1']])
        self.rows[0]['ruta'] = str(self.root / Path(self.rows[0]['ruta']).name)
        with self.assertRaisesRegex(ValueError, 'fuera del directorio'):
            self._load_invalid_rows()
        self.rows[0]['ruta'] = str(next(self.source.rglob('RI_*.csv')))
        self.rows.append(copy.deepcopy(self.rows[0]))
        with self.assertRaisesRegex(ValueError, 'duplicada'):
            self._load_invalid_rows()

    def test_publication_reopen_archives_idempotent_and_no_original_changes(self):
        self.add_source([['240901', '0100', '1'], ['240901', '0200', '', '', '2']])
        inp = self.inputs()
        before = {str(p): (m.sha256(p), p.stat().st_mtime_ns) for p in self.source.rglob('*') if p.is_file()}
        first = self.publish(inp); destination = Path(first['path'])
        proof = m.validate_publication(destination, first['version'])
        self.assertEqual(proof['inputs']['afg_semantics'], inp['semantics'])
        self.assertEqual(m.sha256(destination/'procedencia/preparar_sinca_modelado.py'), proof['inputs']['code_sha256'])
        self.assertEqual(m.sha256(destination/'procedencia/afg_lib.py'), inp['semantics']['file_sha256'])
        mtimes = {p.name: p.stat().st_mtime_ns for p in destination.iterdir()}
        second = self.publish(inp)
        self.assertEqual(second['status'], 'reused')
        self.assertEqual(mtimes, {p.name: p.stat().st_mtime_ns for p in destination.iterdir()})
        self.assertEqual(before, {str(p): (m.sha256(p), p.stat().st_mtime_ns) for p in self.source.rglob('*') if p.is_file()})
        self.assertEqual(list((self.output/'_staging').iterdir()), [])

    def test_corrupt_publication_never_overwritten(self):
        self.add_source([['240901', '0100', '1']]); inp = self.inputs()
        result = self.publish(inp); path = Path(result['path']) / 'observaciones.parquet'
        path.write_bytes(b'corruption')
        with self.assertRaisesRegex(ValueError, 'alterado'):
            self.publish(inp)
        self.assertEqual(path.read_bytes(), b'corruption')

    def test_changed_source_disallows_cached_reentry(self):
        path = self.add_source([['240901', '0100', '1']]); inp = self.inputs()
        self.publish(inp); path.write_text(path.read_text().replace(';1;', ';2;'))
        with self.assertRaisesRegex(ValueError, 'fuente actual'):
            self.publish(inp)

    def test_failure_before_atomic_rename_preserves_stage_and_resume(self):
        self.add_source([['240901', '0100', '1']]); inp = self.inputs()
        with patch.object(m, 'publish_no_replace', side_effect=OSError('injected prepublish')):
            with self.assertRaisesRegex(OSError, 'injected'):
                self.publish(inp)
        stage = next((self.output/'_staging').iterdir())
        m.validate_publication(stage)
        with patch.object(m, 'consolidate', side_effect=AssertionError('must reuse validated stage')):
            result = self.publish(inp)
        self.assertEqual(result['status'], 'published')
        self.assertFalse(stage.exists())

    def test_exclusive_publish_does_not_replace_even_empty_directory(self):
        stage, dest = self.root/'stage', self.root/'already-exists'
        stage.mkdir(); dest.mkdir()
        (stage/'proof').write_text('durable')
        with self.assertRaises(FileExistsError):
            m.publish_no_replace(stage, dest)
        self.assertTrue((stage/'proof').is_file())
        self.assertEqual(list(dest.iterdir()), [])

    def test_destination_race_preserves_both_and_staging(self):
        self.add_source([['240901', '0100', '1']]); inp = self.inputs()
        real = m.publish_no_replace
        def race(stage, dest):
            dest.mkdir()
            return real(stage, dest)
        with patch.object(m, 'publish_no_replace', side_effect=race):
            with self.assertRaises(FileExistsError):
                self.publish(inp)
        stage = next((self.output/'_staging').iterdir())
        m.validate_publication(stage)

    def test_failed_exact_reopen_does_not_publish_or_remove_original(self):
        original = self.add_source([['240901', '0100', '1']]); inp = self.inputs()
        real = pq.ParquetFile
        def bad(*a, **kw):
            table = real(*a, **kw).read()
            return types.SimpleNamespace(read=lambda: table.slice(0, 0))
        with patch.object(pq, 'ParquetFile', side_effect=bad):
            with self.assertRaisesRegex(ValueError, 'reapertura'):
                self.publish(inp)
        self.assertTrue(original.exists())
        self.assertEqual(list(self.output.glob('estacion=*')), [])
        self.assertTrue(list((self.output/'_staging').rglob('*.parquet')))

    def test_input_change_during_publication_is_not_committed(self):
        original = self.add_source([['240901', '0100', '1']]); inp = self.inputs()
        actual = m.json_atomic
        def changed(path, proof):
            actual(path, proof)
            original.write_text(original.read_text().replace(';1;', ';2;'))
        with patch.object(m, 'json_atomic', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'fuente cambió antes'):
                self.publish(inp)
        self.assertEqual(list(self.output.glob('estacion=*')), [])
        self.assertTrue(list((self.output/'_staging').rglob('manifest.json')))

    def test_reserve_uuid_and_lock_fail_closed(self):
        with self.assertRaises(ValueError):
            m.check_disk(self.output, 99, volume_uuid=None)
        with patch.object(m.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=100*m.GIB)):
            with self.assertRaises(m.SafeLimit):
                m.check_disk(self.output, pending_bytes=1, volume_uuid=None)
        with self.assertRaises(m.SafeLimit):
            m.check_disk(self.output, volume_uuid='wrong')
        with m.exclusive_lock(self.output/'.writer.lock'):
            with self.assertRaises(BlockingIOError):
                with m.exclusive_lock(self.output/'.writer.lock'):
                    self.fail('lock admitted another writer')

    def test_output_under_source_forbidden(self):
        self.add_source([['240901', '0100', '1']]); inp = self.inputs()
        with self.assertRaisesRegex(ValueError, 'sobre fuentes'):
            m.process_series(inp['rows'], inp, self.source/'child', volume_uuid=None)


if __name__ == '__main__':
    unittest.main()
