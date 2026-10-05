"""Sólo fixtures temporales: jamás abre ni modifica los datos productivos."""
import json
from pathlib import Path
import shutil
import sys
import unittest
from unittest.mock import patch

import netCDF4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import validar_revision_era5land_modelado as validator
import test_preparar_era5land_modelado as fixture_module


class RevisionValidationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.TransactionTests('test_new_source_revision_retains_old_product_bytes')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.origin = self.fixture.origin.resolve()
        self.revision = Path(self.fixture.run_month()['directory'])
        self.converter = fixture_module.m

    def validate(self):
        return validator.validar_revision(self.revision, origen=self.origin)

    def snapshot(self):
        return {str(p): self.converter.sha256(p) for p in self.fixture.base.rglob('*') if p.is_file()}

    def backup_and_refresh(self):
        folder = self.origin / '_respaldos_publicacion' / '200002' / 'test-backup'
        folder.mkdir(parents=True)
        artifacts = []
        for source in [self.origin / 'mensual/era5land_200002_chile_pixeles.nc',
                       self.origin / 'manifiestos/era5land_200002.json']:
            backup = folder / source.name
            shutil.copyfile(source, backup)
            artifacts.append({'original': str(source), 'respaldo': str(backup),
                              'sha256': self.converter.sha256(source), 'bytes': source.stat().st_size})
        registry = folder / 'respaldo.json'
        registry.write_text(json.dumps({'schema': validator.BACKUP_SCHEMA, 'periodo': '2000-02',
                                        'artefactos': artifacts, 'retiro_automatico_permitido': False}))
        self.fixture.source('2000-02', hours=50)
        return registry, artifacts

    def test_current_sources_full_recompute_without_mutation(self):
        before = self.snapshot()
        result = self.validate()
        self.assertEqual(result['status'], 'validated_readonly')
        self.assertEqual({m['via'] for m in result['source_resolution']}, {'canonical'})
        self.assertTrue(result['all_hashes_rechecked_after_recomputation'])
        self.assertEqual(result['validator']['sha256'], self.converter.sha256(validator.__file__))
        self.assertIn('python', result['runtime'])
        self.assertEqual(before, self.snapshot())

    def test_exact_backup_pair_resolves_old_revision_without_mutation(self):
        self.backup_and_refresh()
        with self.assertRaises(ValueError):
            self.converter.validar_producto(self.revision)
        before = self.snapshot()
        result = self.validate()
        feb = [m for m in result['source_resolution'] if m['month'] == '2000-02']
        self.assertEqual(len(feb), 2)
        self.assertTrue(all(m['via'] == 'registered_backup' and m['original'] != m['resolved'] for m in feb))
        self.assertEqual(before, self.snapshot())

    def test_missing_backup_is_not_silently_accepted(self):
        self.fixture.source('2000-02', hours=50)
        with self.assertRaisesRegex(ValueError, 'único respaldo'):
            self.validate()

    def test_corrupt_or_missing_backup_native_fails(self):
        _, artifacts = self.backup_and_refresh()
        native = Path(artifacts[0]['respaldo'])
        native.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'ausente/corrupto'):
            self.validate()
        native.unlink()
        with self.assertRaisesRegex(ValueError, 'ausente/corrupto'):
            self.validate()

    def test_corrupt_backup_manifest_fails(self):
        _, artifacts = self.backup_and_refresh()
        Path(artifacts[1]['respaldo']).write_text('{}')
        with self.assertRaisesRegex(ValueError, 'ausente/corrupto'):
            self.validate()

    def test_wrong_registry_hash_or_bytes_fails(self):
        registry, _ = self.backup_and_refresh()
        original = json.loads(registry.read_text())
        for field, bad_value in [('sha256', '0'*64), ('bytes', 7)]:
            changed = json.loads(json.dumps(original))
            changed['artefactos'][0][field] = bad_value
            registry.write_text(json.dumps(changed))
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'único respaldo'):
                self.validate()

    def test_wrong_registry_month_fails(self):
        registry, _ = self.backup_and_refresh()
        data = json.loads(registry.read_text()); data['periodo'] = '2000-01'
        registry.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'esquema/mes'):
            self.validate()

    def test_wrong_manifest_schema_fails(self):
        path = self.revision / 'manifest.json'
        data = json.loads(path.read_text()); data['schema'] = 'unsupported'
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'Identidad/contrato'):
            self.validate()

    def test_artifact_outside_registered_directory_fails(self):
        registry, _ = self.backup_and_refresh()
        data = json.loads(registry.read_text())
        data['artefactos'][0]['respaldo'] = str(self.origin / 'foreign.nc')
        registry.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'fuera de su carpeta'):
            self.validate()

    def test_ambiguous_duplicate_backup_pair_fails(self):
        registry, _ = self.backup_and_refresh()
        other = registry.parent.with_name('other-backup')
        shutil.copytree(registry.parent, other)
        data = json.loads((other / 'respaldo.json').read_text())
        for item in data['artefactos']:
            item['respaldo'] = str(other / Path(item['respaldo']).name)
        (other / 'respaldo.json').write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'encontrados 2'):
            self.validate()

    def test_geometry_stays_strict_without_backup_fallback(self):
        self.fixture.mask.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Fuente cambió'):
            self.validate()

    def test_output_corruption_and_recomputed_mismatch_fail(self):
        output = self.revision / 'tp_1h_mm.nc'
        with netCDF4.Dataset(output, 'a') as ds:
            ds['tp_1h_mm'][2, 0] = 9876
        with self.assertRaisesRegex(ValueError, 'Hash de fuente incompatible'):
            self.validate()
        # A forged output hash cannot bypass recomputation from source bytes.
        path = self.revision / 'manifest.json'; manifest = json.loads(path.read_text())
        manifest['output'].update(sha256=self.converter.sha256(output), bytes=output.stat().st_size)
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'difiere de fuente o fórmula'):
            self.validate()

    def test_archived_code_and_identity_corruption_fail(self):
        archive = self.revision / 'preparar_era5land_modelado.py'
        code = archive.read_bytes(); archive.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Hash de fuente incompatible'):
            self.validate()
        archive.write_bytes(code)
        path = self.revision / 'manifest.json'; manifest = json.loads(path.read_text())
        manifest['identity']['code_sha256'] = '0'*64
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'Identidad/contrato'):
            self.validate()

    def test_post_recomputation_hash_detects_concurrent_change(self):
        self.backup_and_refresh()
        original_inputs = self.converter._inputs
        def mutate_after_read(inventory):
            result = original_inputs(inventory)
            with Path(inventory['current']['native']['path']).open('ab') as stream:
                stream.write(b'concurrent change')
            return result
        with patch.object(self.converter, '_inputs', side_effect=mutate_after_read):
            with self.assertRaisesRegex(ValueError, 'Fuente cambió'):
                self.validate()


if __name__ == '__main__':
    unittest.main()
