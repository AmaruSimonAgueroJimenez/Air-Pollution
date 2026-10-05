import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / 'preparar_datos_modelado.py'
spec = importlib.util.spec_from_file_location('coordinador_modelado', SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class CoordinatorTests(unittest.TestCase):
    def test_calendar_and_leap_year(self):
        self.assertEqual(m.months('1999-12', '2000-03'), ['1999-12', '2000-01', '2000-02', '2000-03'])

    def test_invalid_calendar(self):
        for first, last in [('2000-1', '2000-02'), ('2001-01', '2000-01'), ('2000-13', '2001-01')]:
            with self.assertRaises(ValueError): m.months(first, last)

    def test_scope_and_no_deletion(self):
        args = m.parser().parse_args(['--merra-hasta', '2026-05', '--sinca-hasta', '2026-09-13', '--era-hasta', '2026-09'])
        plan = m.build_plan(args)
        self.assertEqual(len(plan['jobs']), 323)
        self.assertFalse(plan['execution_enabled'])
        self.assertFalse(plan['source_deletion'])
        self.assertNotIn('--retirar-legado-validado', str(plan))
        self.assertEqual(plan['jobs'][-1]['period'], '2026-09')

    def test_explicit_end_required(self):
        with self.assertRaises(ValueError): m.build_plan(m.parser().parse_args([]))

    def test_selected_product_only(self):
        plan = m.build_plan(m.parser().parse_args(['--productos', 'era5land', '--era-desde', '2026-08', '--era-hasta', '2026-09']))
        self.assertEqual([j['product'] for j in plan['jobs']], ['era5land'] * 2)

    def test_failure_stops_and_records_without_running_next(self):
        import json
        plan = m.build_plan(m.parser().parse_args(['--productos', 'era5land', '--era-desde', '2026-08', '--era-hasta', '2026-09', '--ejecutar']))
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(m, 'OUTPUT', Path(directory)), mock.patch.object(m, 'disk_guard'), \
                    mock.patch.object(m.subprocess, 'run', return_value=mock.Mock(returncode=2)) as run:
                with self.assertRaises(RuntimeError): m.execute(plan)
                self.assertEqual(run.call_count, 1)
                progress = json.loads(next(Path(directory).glob('_ejecuciones/*/progreso.json')).read_text())
                self.assertEqual(progress['status'], 'stopped_originals_preserved')
                self.assertEqual(progress['failed_job']['returncode'], 2)

    def test_code_change_during_final_child_blocks_complete(self):
        import json
        plan = m.build_plan(m.parser().parse_args(['--productos', 'era5land', '--era-desde', '2026-09', '--era-hasta', '2026-09', '--ejecutar']))
        original_sha = m.sha256
        changed = False
        def simulate_child(*args, **kwargs):
            nonlocal changed
            changed = True
            return mock.Mock(returncode=0)
        def simulated_sha(path):
            return '0' * 64 if changed and str(path) == str(SCRIPT) else original_sha(path)
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(m, 'OUTPUT', Path(directory)), mock.patch.object(m, 'disk_guard'), \
                    mock.patch.object(m.subprocess, 'run', side_effect=simulate_child), \
                    mock.patch.object(m, 'sha256', side_effect=simulated_sha):
                with self.assertRaisesRegex(RuntimeError, 'Código cambió'): m.execute(plan)
                progress = json.loads(next(Path(directory).glob('_ejecuciones/*/progreso.json')).read_text())
                self.assertEqual(progress['status'], 'stopped_originals_preserved')
                self.assertEqual(progress['completed_jobs'], [])

    def test_completed_job_is_durable_before_next_job(self):
        import json
        plan = m.build_plan(m.parser().parse_args(['--productos', 'era5land', '--era-desde', '2026-08', '--era-hasta', '2026-09', '--ejecutar']))
        writes = []
        original_write = m.json_atomic
        def capture(path, value):
            writes.append(json.loads(json.dumps(value)))
            original_write(path, value)
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(m, 'OUTPUT', Path(directory)), mock.patch.object(m, 'disk_guard'), \
                    mock.patch.object(m.subprocess, 'run', return_value=mock.Mock(returncode=0)), \
                    mock.patch.object(m, 'json_atomic', side_effect=capture):
                result = m.execute(plan)
        self.assertEqual(result['status'], 'complete_for_requested_transformations')
        self.assertTrue(any(w.get('status') == 'running' and len(w.get('completed_jobs', [])) == 1
                            and w.get('current_job') is None for w in writes))


if __name__ == '__main__':
    unittest.main()
