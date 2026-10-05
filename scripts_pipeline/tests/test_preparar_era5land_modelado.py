"""Fixtures sintéticas; no modifica ni requiere los originales externos."""
from contextlib import ExitStack
from datetime import datetime, timezone
import calendar
import json
from pathlib import Path
import sys
import plistlib
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import netCDF4
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import preparar_era5land_modelado as m


def epoch(iso):
    return int(datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp())


class CalculationTests(unittest.TestCase):
    def test_reset_one_not_midnight_and_negative(self):
        t = epoch('2000-01-01T23:00') + np.arange(4, dtype='i8') * 3600
        p, q = m.calcular_precipitacion([[.009], [.010], [.0004], [.0003]], t, [.008], t[0]-3600)
        np.testing.assert_allclose(p[:, 0], [1, 1, .4, -.1])
        self.assertEqual(q[:, 0].tolist(), [0, 0, 0, m.NEGATIVE])

    def test_initial_missing_zero_does_not_invent(self):
        t = epoch('2000-01-01T00:00') + np.arange(3, dtype='i8') * 3600
        p, q = m.calcular_precipitacion([[9], [.001], [.002]], t)
        self.assertTrue(np.isnan(p[0, 0])); self.assertEqual(q[0, 0], 6)
        np.testing.assert_allclose(p[1:, 0], [1, 1])

    def test_current_and_predecessor_missing_distinct(self):
        t = epoch('2000-01-01T00:00') + np.arange(3, dtype='i8')*3600
        p, q = m.calcular_precipitacion([[np.nan, 1], [.002, np.nan], [.003, .004]], t, [.1, np.nan], t[0]-3600)
        self.assertEqual(q.tolist(), [[1, 2], [0, 1], [0, 2]])
        self.assertEqual(p[1, 0], 2); self.assertTrue(np.isnan(p[2, 1]))

    def test_gap_does_not_difference_over_two_hours(self):
        t = np.array([epoch('2000-01-01T02:00'), epoch('2000-01-01T04:00')], dtype='i8')
        p, q = m.calcular_precipitacion([[.2], [.4]], t, [.1], t[0]-3600)
        self.assertTrue(np.isnan(p[1, 0])); self.assertEqual(q[1, 0], 6)

    def test_duplicate_unsorted_noninteger_and_offhour_rejected(self):
        for t in ([0, 0], [3600, 0], [0., 3600.], [0, 3601]):
            with self.subTest(t=t), self.assertRaises(ValueError):
                m.calcular_precipitacion([[0], [1]], np.asarray(t))

    def test_year_leap_and_month_boundary(self):
        for stamp in ['2000-01-01T00:00', '2000-02-01T00:00', '2000-02-29T00:00', '2000-03-01T00:00']:
            t = np.array([epoch(stamp)], dtype='i8')
            p, q = m.calcular_precipitacion([[.01]], t, [.009], t[0]-3600)
            self.assertAlmostEqual(p[0, 0], 1); self.assertEqual(q[0, 0], 0)

    def test_all_negative_magnitudes_preserved_without_clamp(self):
        t = np.array([epoch('2000-01-01T02:00')], dtype='i8')
        p, q = m.calcular_precipitacion([[.00099999999, 0]], t, [.001, 1], t[0]-3600)
        self.assertTrue((p < 0).all()); self.assertEqual(p[0, 1], -1000)
        self.assertTrue((q == 8).all())


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.base = Path(self.stack.enter_context(TemporaryDirectory()))
        self.origin = self.base / 'native'; self.origin.mkdir()
        self.dest = self.base / 'derived'
        self.mask = self.base / 'comunas.shp'; self.mask.write_bytes(b'mask fixture')
        self.contract = self.base / 'contract.json'; self.contract.write_text('{}')
        self.stack.enter_context(patch.object(m, 'CONTRATO_PREVIO', self.contract))
        self.guard = self.stack.enter_context(patch.object(m, '_guard_disk', return_value={'uuid': 'test', 'reserve_bytes': m.RESERVA_BYTES}))
        for name in ['mensual', 'manifiestos', 'metadata']:
            (self.origin / name).mkdir()
        for name in ['catalogo_pixeles.parquet', 'relacion_pixel_comuna.parquet']:
            (self.origin / name).write_bytes(name.encode())
        self.catalog_hash = m.sha256(self.origin / 'catalogo_pixeles.parquet')
        catalog = {
            'catalogo': {'archivo': 'catalogo_pixeles.parquet', 'sha256': self.catalog_hash},
            'relacion_pixel_comuna': {'archivo': 'relacion_pixel_comuna.parquet', 'sha256': m.sha256(self.origin / 'relacion_pixel_comuna.parquet')},
            'mascara': {'componentes': {'comunas.shp': {'sha256': m.sha256(self.mask), 'bytes': self.mask.stat().st_size}}}}
        (self.origin / 'metadata/catalogo_manifest.json').write_text(json.dumps(catalog))
        self.jan = self.source('2000-01')
        self.feb = self.source('2000-02', hours=26)
        self.originals = {p: m.sha256(p) for p in self.origin.rglob('*') if p.is_file()}

    def source(self, mes, hours=None, reverse=False):
        date, _ = m._months(mes)
        hours = hours or calendar.monthrange(date.year, date.month)[1]*24
        t = int(date.timestamp()) + np.arange(hours, dtype='i8')*3600
        ids = np.array([10, 11], dtype='i8')
        order = np.array([1, 0] if reverse else [0, 1])
        path = self.origin / 'mensual' / f'era5land_{mes.replace("-", "")}_chile_pixeles.nc'
        with netCDF4.Dataset(path, 'w') as ds:
            ds.createDimension('time', hours); ds.createDimension('pixel', 2)
            ds.temporal_operation = 'none; exact native UTC hours'
            ds.spatial_resolution_degrees = .1; ds.catalog_sha256 = self.catalog_hash
            tv = ds.createVariable('time', 'i8', ('time',)); tv[:] = t
            tv.units = m.TIME_UNITS; tv.calendar = 'proleptic_gregorian'
            for name, vals, dtype in [('pixel_id', ids, 'i8'), ('latitude', [-30, -30.1], 'f8'),
                                     ('longitude', [-70, -70.1], 'f8'), ('lat_index_global', [1200, 1201], 'i2'),
                                     ('lon_index_global', [2900, 2899], 'i2'), ('cod_comuna', [0, 0], 'i4')]:
                ds.createVariable(name, dtype, ('pixel',))[:] = np.asarray(vals)[order]
            ds.createVariable('latitude_longitude', 'i1', ())[...] = 0
            for name in m.CONTRATO['metadata_overlay']:
                v = ds.createVariable(name, 'f4', ('time', 'pixel'), fill_value=np.nan)
                steps = (t//3600)%24; steps = np.where(steps == 0, 24, steps)
                arr = steps[:, None]*np.array([.0001, .0002])[None, :]
                v[:] = arr[:, order]
                if name == 'tp': v.source_variable_names = '["tp"]'
        manifest = {'periodo': mes, 'descarga_cds': {'dataset': m.CONTRATO['dataset']},
            'software': {'motor_normalizacion_sha256': m.NORMALIZADOR_SHA},
            'salida': {'archivo': str(path), 'sha256': m.sha256(path)}, 'catalogo': {'sha256': self.catalog_hash}}
        (self.origin / 'manifiestos' / f'era5land_{mes.replace("-", "")}.json').write_text(json.dumps(manifest))
        return path

    def run_month(self):
        return m.preparar_mes('2000-02', self.origin, self.dest, self.mask)

    def assert_originals(self):
        self.assertEqual(self.originals, {p: m.sha256(p) for p in self.origin.rglob('*') if p.is_file()})

    def test_happy_full_validation_and_idempotence(self):
        first = self.run_month(); directory = Path(first['directory'])
        second = self.run_month()
        self.assertEqual(first['status'], 'published'); self.assertEqual(second['status'], 'reused')
        self.assertEqual(first['revision'], second['revision'])
        self.assertEqual(first['output'], second['output'])
        self.assertEqual(first['validation']['temporal_gap'], 0)
        self.assertEqual(len(list((self.dest/'meses').rglob('tp_1h_mm.nc'))), 1)
        self.assertEqual(list((self.dest/'staging').iterdir()), [])
        with netCDF4.Dataset(directory/'tp_1h_mm.nc') as ds:
            self.assertEqual(set(ds.variables)-set(m.COORDS), {'time','time_bounds','tp_1h_mm','tp_1h_flags'})
            self.assertEqual(ds['cod_comuna'][:].tolist(), [0, 0])
            self.assertEqual(ds['pixel_id'][:].tolist(), [10, 11])
        self.assert_originals()

    def test_previous_pixel_reordering_is_joined_by_id(self):
        self.source('2000-01', reverse=True)
        result = self.run_month()
        self.assertEqual(result['validation']['temporal_gap'], 0)
        with netCDF4.Dataset(Path(result['directory'])/'tp_1h_mm.nc') as ds:
            np.testing.assert_allclose(ds['tp_1h_mm'][0], [.1, .2], atol=1e-6)

    def test_missing_first_month_has_flag_not_zero(self):
        result = m.preparar_mes('2000-01', self.origin, self.dest, self.mask)
        self.assertEqual(result['validation']['temporal_gap'], 2)
        with netCDF4.Dataset(Path(result['directory'])/'tp_1h_mm.nc') as ds:
            ds.set_auto_mask(False)
            self.assertTrue(np.isnan(ds['tp_1h_mm'][0]).all())
            self.assertTrue(np.isfinite(ds['tp_1h_mm'][1]).all())

    def test_integrity_source_and_mask_hash_rejection(self):
        with self.mask.open('ab') as f: f.write(b'changed')
        with self.assertRaisesRegex(ValueError, 'Hash'):
            self.run_month()
        self.assertFalse((self.dest/'meses').exists())

    def test_endpoint_timeseries_rejected(self):
        path = self.origin/'manifiestos/era5land_200002.json'
        man = json.loads(path.read_text()); man['descarga_cds']['dataset'] = 'reanalysis-era5-land-timeseries'
        path.write_text(json.dumps(man))
        with self.assertRaisesRegex(ValueError, 'endpoint'):
            self.run_month()

    def test_incompatible_units_and_source_hash_rejected(self):
        with netCDF4.Dataset(self.feb, 'a') as ds: ds['tp'].units = 'mm'
        with self.assertRaisesRegex(ValueError, 'Hash'):
            self.run_month()
        path = self.origin/'manifiestos/era5land_200002.json'
        man = json.loads(path.read_text()); man['salida']['sha256'] = m.sha256(self.feb); path.write_text(json.dumps(man))
        with self.assertRaisesRegex(ValueError, 'Unidades'):
            self.run_month()

    def test_write_and_validation_and_publication_failures_preserve_sources(self):
        for func in ['_write_nc', '_validate_nc', '_publish']:
            with self.subTest(func=func), patch.object(m, func, side_effect=RuntimeError('injected')):
                with self.assertRaisesRegex(RuntimeError, 'injected'): self.run_month()
            self.assert_originals()
        self.assertEqual(len(list((self.dest/'staging').iterdir())), 3)
        self.assertEqual(self.run_month()['status'], 'published')

    def test_manifest_failure_preserves_staging_and_no_publish(self):
        original = m._write_new
        def failing(path, data):
            if Path(path).name == 'manifest.json': raise RuntimeError('manifest injected')
            return original(path, data)
        with patch.object(m, '_write_new', side_effect=failing), self.assertRaises(RuntimeError):
            self.run_month()
        self.assertEqual(len(list((self.dest/'staging').rglob('tp_1h_mm.nc'))), 1)
        self.assertFalse((self.dest/'meses').exists()); self.assert_originals()

    def test_wal_failure_after_rename_reenters_without_overwrite(self):
        original = m._event
        def failing(wal, phase, **fields):
            if phase == 'published': raise RuntimeError('wal injected')
            return original(wal, phase, **fields)
        with patch.object(m, '_event', side_effect=failing), self.assertRaises(RuntimeError):
            self.run_month()
        files = list((self.dest/'meses').rglob('tp_1h_mm.nc')); self.assertEqual(len(files), 1)
        before = m.sha256(files[0]); result = self.run_month()
        self.assertEqual(result['status'], 'reused'); self.assertEqual(before, m.sha256(files[0]))
        self.assert_originals()

    def test_existing_tamper_fails_and_never_rewrites(self):
        result = self.run_month(); output = Path(result['directory'])/'tp_1h_mm.nc'
        with netCDF4.Dataset(output, 'a') as ds: ds['tp_1h_mm'][0, 0] = 99
        tampered = m.sha256(output)
        with self.assertRaises(ValueError): self.run_month()
        self.assertEqual(tampered, m.sha256(output)); self.assert_originals()

    def test_rename_exclusive_does_not_replace_even_empty_directory(self):
        stage, final = self.base/'stage', self.base/'final'; stage.mkdir(); final.mkdir()
        (stage/'useful').write_text('useful')
        with self.assertRaises(FileExistsError): m._publish(stage, final)
        self.assertTrue((stage/'useful').exists()); self.assertTrue(final.is_dir())

    def test_disk_refusal_writes_nothing(self):
        self.guard.side_effect = RuntimeError('100 GiB')
        with self.assertRaisesRegex(RuntimeError, '100 GiB'): self.run_month()
        self.assertFalse(self.dest.exists()); self.assert_originals()

    def test_new_source_revision_retains_old_product_bytes(self):
        first = self.run_month(); old = Path(first['directory'])/'tp_1h_mm.nc'
        digest = m.sha256(old)
        with netCDF4.Dataset(self.feb, 'a') as ds: ds['tp'][2, 0] = .0004
        path = self.origin/'manifiestos/era5land_200002.json'
        man = json.loads(path.read_text()); man['salida']['sha256'] = m.sha256(self.feb)
        path.write_text(json.dumps(man))
        second = self.run_month()
        self.assertNotEqual(first['revision'], second['revision'])
        self.assertEqual(digest, m.sha256(old))
        self.assertEqual(len(list((self.dest/'meses').rglob('tp_1h_mm.nc'))), 2)

    def test_final_fsync_failure_reenters_existing_publication(self):
        original = m._fsync
        def failing(path):
            if Path(path).parent.name == '2000-02' and Path(path).is_dir():
                raise RuntimeError('fsync injected')
            return original(path)
        with patch.object(m, '_fsync', side_effect=failing), self.assertRaises(RuntimeError):
            self.run_month()
        self.assertEqual(self.run_month()['status'], 'reused'); self.assert_originals()

    def test_all_values_revalidated_not_just_endpoints(self):
        first = self.run_month(); directory = Path(first['directory'])
        path = directory/'tp_1h_mm.nc'
        with netCDF4.Dataset(path, 'a') as ds: ds['tp_1h_mm'][12, 1] = 42
        manifest = directory/'manifest.json'; man = json.loads(manifest.read_text())
        man['output'] = {'bytes': path.stat().st_size, 'sha256': m.sha256(path)}
        manifest.write_text(json.dumps(man))
        with self.assertRaisesRegex(ValueError, 'fórmula'):
            m.validar_producto(directory)


class DiskGuardTests(unittest.TestCase):
    def test_uuid_and_capacity_and_mount_checks(self):
        info = {'VolumeUUID': m.UUID_DISCO, 'MountPoint': str(m.DISCO)}
        with patch.object(Path, 'is_mount', return_value=True), \
             patch.object(m.subprocess, 'check_output', return_value=plistlib.dumps(info)) as call, \
             patch.object(m.shutil, 'disk_usage', return_value=SimpleNamespace(free=m.RESERVA_BYTES+100)) as usage:
            self.assertEqual(m._guard_disk(m.DESTINO, 99)['uuid'], m.UUID_DISCO)
            with self.assertRaisesRegex(RuntimeError, 'Reserva'):
                m._guard_disk(m.DESTINO, 101)
            call.return_value = plistlib.dumps({**info, 'VolumeUUID': 'wrong'})
            with self.assertRaisesRegex(RuntimeError, 'UUID'):
                m._guard_disk(m.DESTINO)
            with self.assertRaisesRegex(RuntimeError, 'fuera'):
                m._guard_disk(Path('/tmp/not-external'))
        with patch.object(Path, 'is_mount', return_value=False), self.assertRaisesRegex(RuntimeError, 'montado'):
            m._guard_disk(m.DESTINO)


if __name__ == '__main__':
    unittest.main()
