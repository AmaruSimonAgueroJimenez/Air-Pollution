"""Safety contracts for the new-gas engine; synthetic files, no network/data access."""
from __future__ import annotations

from contextlib import nullcontext
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import descargar_tropomi_gases as motor


class Granule(dict):
    def __init__(self, name, *, concept="G123-GES_DISC", revision=1,
                 checksum=None, size=12, unit="MB", gas="co"):
        self.link = "https://example.test/data/" + name
        entry = {"Name": name, "Size": size, "SizeUnit": unit}
        if checksum is not None:
            entry["Checksum"] = checksum
        short, collection_concept = motor.PRODUCTOS[gas]
        super().__init__(meta={"concept-id": concept, "revision-id": revision,
                              "collection-concept-id": collection_concept},
                         umm={"GranuleUR": short + ".2:" + name,
                              "CollectionReference": {"ShortName": short, "Version": "2"},
                              "DataGranule": {"ArchiveAndDistributionInformation": [entry],
                                              "Identifiers": [{"Identifier": name,
                                                               "IdentifierType": "ProducerGranuleId"}]}})

    def data_links(self):
        return [self.link]


def name(stream="OFFL", processor="020500", production="20231007T090000",
         orbit="31000", start="20231005T170000", end="20231005T184000"):
    return f"S5P_{stream}_L2__CO_____{start}_{end}_{orbit}_03_{processor}_{production}.nc"


def item(**kw):
    return motor.identidad(Granule(name(**kw)))


class SyntheticDataset:
    def __init__(self, path, *args, **kwargs):
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(path)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def setncattr(self, *args):
        pass


class EngineTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tropomi-gases-unit-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cfg = dict(root=str(self.root), execution_id="synthetic-run",
                        comunas=str(self.root / "mask.shp"), mask_sha256="mask-1",
                        code_sha256="code-1", code_archive="synthetic-archive",
                        volume_uuid=None, reserva_gib=100, staging_gib=10,
                        cuota_gib=40, max_granulos=0)

    def paths(self, source_item):
        out = (self.root / "CO/chile_l2_nativo_v1/year=2023/month=10" /
               source_item["name"].replace(".nc", ".chile.nc"))
        key = hashlib.sha256((source_item["name"] + source_item["cmr_sha256"] +
                              self.cfg["mask_sha256"] + motor.CONTRATO).encode()).hexdigest()
        return out, out.with_suffix(".json"), self.root / "CO/_staging_gases" / key

    def processing_mocks(self, *, validate=None, create=None):
        def default_create(source, out, *args):
            Path(out).write_bytes(b"validated Chile native subset")
            return {"pixels": 7}
        subset = types.SimpleNamespace(crear_subset=create or default_create,
                                       validar_subset=validate or (lambda *a: {"pixels": 7}))
        return patch.dict(sys.modules, {
            "netCDF4": types.SimpleNamespace(Dataset=SyntheticDataset),
            "_tropomi_gases_subset": subset,
        })

    def create_source(self, cfg, source_item, stage):
        path = stage / "source.nc"
        if not path.exists():
            path.write_bytes(b"provider synthetic source")
        return path


class IdentitySelectionTests(EngineTest):
    def test_archive_size_units_and_checksum_preserved(self):
        checksum = {"Algorithm": "MD5", "Value": "a" * 32}
        got = motor.identidad(Granule(name(), size=1.1, unit="GB", checksum=checksum))
        self.assertEqual(got["size_estimated"], 1_100_000_000)
        self.assertEqual(got["checksum"], checksum)
        self.assertEqual(got["orbit"], 31000)

    def test_public_snapshot_strips_signed_queries_recursively(self):
        got = motor.publico({"a": ["https://example.test/a?token=secret"]})
        self.assertEqual(got, {"a": ["https://example.test/a"]})

    def test_nrti_and_unidentifiable_filename_are_rejected(self):
        for bad in [name(stream="NRTI"), "foo.nc"]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                motor.identidad(Granule(bad))

    def test_invalid_acquisition_calendar_is_rejected(self):
        with self.assertRaises(ValueError):
            motor.identidad(Granule(name(start="20230230T170000")))

    def test_invalid_production_calendar_is_rejected(self):
        with self.assertRaises(ValueError):
            motor.identidad(Granule(name(production="20230230T170000")))

    def test_newer_reprocessed_revision_selected_and_orbits_separate(self):
        old = item(processor="020300")
        rpro = item(stream="RPRO", processor="020400")
        other = item(orbit="31001", start="20231005T190000", end="20231005T204000")
        self.assertEqual(motor.seleccionar_producciones([other, old, rpro]), [rpro, other])
        self.assertEqual(motor.seleccionar_producciones([rpro, old, other]), [rpro, other])

    def test_duplicate_bbox_identical_metadata_collapses(self):
        one = item()
        self.assertEqual(motor.seleccionar_producciones([one, copy.deepcopy(one)]), [one])

    def test_same_filename_distinct_concepts_cannot_silently_overwrite(self):
        a = motor.identidad(Granule(name(), concept="G1-GES_DISC"))
        b = motor.identidad(Granule(name(), concept="G2-GES_DISC"))
        with self.assertRaises(ValueError):
            motor.seleccionar_producciones([a, b])

    def test_same_filename_conflicting_revision_is_not_arbitrary(self):
        a = motor.identidad(Granule(name(), revision=1))
        b = motor.identidad(Granule(name(), revision=2))
        with self.assertRaises(ValueError):
            motor.seleccionar_producciones([a, b])

    def test_same_lineage_prefers_rpro_over_offl(self):
        a, b = item(), item(stream="RPRO")
        self.assertEqual(motor.seleccionar_producciones([a, b]), [b])
        self.assertEqual(motor.seleccionar_producciones([b, a]), [b])

    def test_equal_rank_distinct_acquisitions_in_one_orbit_rejected(self):
        a, b = item(), item(start="20231005T170001")
        with self.assertRaises(ValueError):
            motor.seleccionar_producciones([a, b])

    def test_product_and_collection_contract_must_match(self):
        for field, value in [("ShortName", "wrong"), ("Version", "1")]:
            g = Granule(name())
            g["umm"]["CollectionReference"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                motor.identidad(g, "co")
        with self.assertRaises(ValueError):
            motor.identidad(Granule(name()), "ch4")

    def test_filename_product_must_match_collection(self):
        with self.assertRaises(ValueError):
            motor.identidad(Granule(name(), gas="so2"), "so2")

    def test_event_proof_can_include_its_gas(self):
        motor.evento(self.cfg, "co", "publicacion_validada", gas="co", output="synthetic")
        row = json.loads((self.root / "_control_gases/co.jsonl").read_text())
        self.assertEqual(row["gas"], "co")

    def test_event_utc_is_actual_and_original_proof_time_is_transaction_utc(self):
        proof_time = "2026-09-15T15:51:24.516319+00:00"
        event_time = "2026-09-15T15:51:29.331894+00:00"
        with patch.object(motor, "ahora", return_value=event_time):
            motor.evento(self.cfg, "co", "crudo_eliminado_post_validacion",
                         gas="co", utc=proof_time, output="synthetic")
        row = json.loads((self.root / "_control_gases/co.jsonl").read_text())
        self.assertEqual(row["utc"], event_time)
        self.assertEqual(row["transaction_utc"], proof_time)


class DirectoryDurabilityTests(EngineTest):
    def test_nested_creation_syncs_every_directory_and_parent(self):
        target = self.root / "gas/year/month"
        synced = []
        def sync(path):
            self.assertTrue(Path(path).is_dir())
            synced.append(Path(path))
        with patch.object(motor, "fsync_dir", side_effect=sync):
            motor.mkdir_durable(target)
        self.assertEqual(synced, [self.root, self.root.parent,
                                 self.root / "gas", self.root,
                                 self.root / "gas/year", self.root / "gas",
                                 target, target.parent])

    def test_failed_parent_sync_stops_creation_and_retry_repairs_link(self):
        parent = self.root / "gas"
        target = parent / "month"
        def fail(path):
            if Path(path) == self.root and parent.exists():
                raise OSError("parent link not durable")
        with patch.object(motor, "fsync_dir", side_effect=fail):
            with self.assertRaisesRegex(OSError, "parent link"):
                motor.mkdir_durable(target)
        self.assertTrue(parent.is_dir())
        self.assertFalse(target.exists())
        synced = []
        with patch.object(motor, "fsync_dir", side_effect=lambda p: synced.append(Path(p))):
            motor.mkdir_durable(target)
        self.assertEqual(synced, [parent, self.root, target, parent])

    def test_file_in_directory_chain_is_not_replaced(self):
        protected = self.root / "protected"
        protected.write_bytes(b"keep")
        with self.assertRaises(NotADirectoryError):
            motor.mkdir_durable(protected / "month")
        self.assertEqual(protected.read_bytes(), b"keep")

    def test_atomic_catalogue_and_new_wal_entries_are_synced_after_write(self):
        catalogue = self.root / "CO/_catalogos_gases/run/day.json"
        wal = self.root / "_control_gases/co.jsonl"
        after_write = []
        def sync(path):
            for file in (catalogue, wal):
                if Path(path) == file.parent and file.exists() and file.stat().st_size:
                    after_write.append(file)
        with patch.object(motor, "fsync_dir", side_effect=sync):
            motor.atomico(catalogue, {"selected": []})
            motor.evento(self.cfg, "co", "consulta_cmr", snapshot=str(catalogue))
        self.assertIn(catalogue, after_write)
        self.assertIn(wal, after_write)

    def test_code_archive_syncs_copied_entry_with_existing_runtime(self):
        native = types.SimpleNamespace(__netcdf4libversion__="test", __hdf5libversion__="test")
        modules = {"netCDF4": native, "pyproj": types.SimpleNamespace(proj_version_str="test"),
                   "shapely": types.SimpleNamespace(geos_version_string="test")}
        with patch.dict(sys.modules, modules), patch.object(motor.importlib.metadata, "version", return_value="test"):
            _, archive = motor.codigo_reproducible(self.root)
            directory = Path(archive)
            target = directory / "descargar_tropomi_gases.py"
            target.unlink()  # Only a disposable synthetic archive, never repository code.
            events = []
            original_copy = motor.shutil.copyfile
            def copy_file(src, dst):
                result = original_copy(src, dst)
                events.append(("copy", Path(dst)))
                return result
            with patch.object(motor.shutil, "copyfile", side_effect=copy_file), \
                 patch.object(motor, "fsync_dir", side_effect=lambda p: events.append(("sync", Path(p)))):
                motor.codigo_reproducible(self.root)
        self.assertGreater(len(events), 1)
        self.assertIn(("copy", target), events)
        self.assertEqual(events[-1], ("sync", directory))
        self.assertLess(events.index(("copy", target)), len(events) - 1)


class CapacityAndLockTests(EngineTest):
    def test_exclusive_lock_rejects_second_writer_and_releases(self):
        path = self.root / "gas.lock"
        with motor.bloqueo(path):
            with self.assertRaises(BlockingIOError):
                with motor.bloqueo(path):
                    self.fail("second writer entered")
        with motor.bloqueo(path):
            pass

    def test_disk_reserve_counts_pending_bytes(self):
        disk = types.SimpleNamespace(free=102 * motor.GIB)
        with patch.object(motor.shutil, "disk_usage", return_value=disk):
            self.assertEqual(motor.comprobar_disco(self.cfg, 2 * motor.GIB), disk.free)
            with self.assertRaises(motor.LimiteSeguro):
                motor.comprobar_disco(self.cfg, 2 * motor.GIB + 1)

    def test_reservation_released_after_exception(self):
        with patch.object(motor, "comprobar_disco"), patch.object(motor, "bytes_arbol", return_value=0):
            with self.assertRaisesRegex(RuntimeError, "synthetic"):
                with motor.reservar(self.cfg, 10):
                    saved = json.loads((self.root / "_control_gases/reservas.json").read_text())
                    self.assertEqual(saved[str(motor.os.getpid())], motor.GIB)
                    raise RuntimeError("synthetic")
        self.assertEqual(json.loads((self.root / "_control_gases/reservas.json").read_text()), {})

    def test_staging_quota_prevents_entering_and_preserves_source(self):
        protected = self.root / "protected.nc"
        protected.write_bytes(b"unique")
        cfg = {**self.cfg, "staging_gib": 3}
        with patch.object(motor, "comprobar_disco"), patch.object(motor, "bytes_arbol", return_value=motor.GIB):
            with self.assertRaises(motor.LimiteSeguro):
                with motor.reservar(cfg, 1):
                    self.fail("quota gate bypassed")
        self.assertEqual(protected.read_bytes(), b"unique")

    def test_final_product_quota_prevents_entering(self):
        def usage(p):
            return motor.GIB if p.name == "chile_l2_nativo_v1" else 0
        with patch.object(motor, "comprobar_disco"), patch.object(motor, "bytes_arbol", side_effect=usage):
            with self.assertRaises(motor.LimiteSeguro):
                with motor.reservar({**self.cfg, "cuota_gib": 5}, 1):
                    self.fail("product quota gate bypassed")


class RetirementTests(EngineTest):
    def proof(self, stage, source):
        output = self.root / (stage.name + ".validated.nc")
        output.write_bytes(b"valid subset")
        transaction = output.with_suffix(".json")
        proof = {"gas": "co", "source_sha256": motor.sha256(source),
                 "output": str(output), "output_sha256": motor.sha256(output),
                 "transaction": str(transaction)}
        motor.atomico(transaction, proof)
        return proof

    def fixture(self):
        stage = self.root / "stage"
        stage.mkdir()
        source = stage / "source.nc"
        source.write_bytes(b"complete scientific source")
        part = stage / "download.prefix.part"
        part.write_bytes(b"complete")
        alien = stage / "download.unrelated.part"
        alien.write_bytes(b"different unique data")
        subset = stage / "subset.validated.nc"
        subset.write_bytes(b"derived")
        proof = self.proof(stage, source)
        return stage, source, part, alien, subset, proof

    def test_failed_wal_or_retirement_event_keeps_every_source(self):
        for failed_name in ["granulo_validado_pre_borrado", "retiro_temporales_autorizado"]:
            with self.subTest(event=failed_name):
                stage = self.root / failed_name
                stage.mkdir()
                source = stage / "source.nc"
                source.write_bytes(b"unique")
                part = stage / "download.a.part"
                part.write_bytes(b"uni")
                proof = self.proof(stage, source)
                def event(cfg, product, event_name, **kw):
                    if event_name == failed_name:
                        raise OSError("synthetic WAL fsync failure")
                with self.processing_mocks(), patch.object(motor, "evento", side_effect=event):
                    with self.assertRaises(OSError):
                        motor.retirar(self.cfg, "co", stage, source,
                                      proof)
                self.assertEqual(source.read_bytes(), b"unique")
                self.assertEqual(part.read_bytes(), b"uni")

    def test_new_wal_directory_sync_failure_prevents_first_unlink(self):
        stage, source, part, alien, subset, proof = self.fixture()
        wal = self.root / "_control_gases/co.jsonl"
        def fail(path):
            if Path(path) == wal.parent and wal.exists():
                raise OSError("WAL directory sync failed")
        with self.processing_mocks(), patch.object(motor, "fsync_dir", side_effect=fail), \
             patch.object(Path, "unlink", side_effect=AssertionError("no unlink authorized")):
            with self.assertRaisesRegex(OSError, "WAL directory"):
                motor.retirar(self.cfg, "co", stage, source, proof)
        self.assertTrue(all(p.exists() for p in (source, part, alien, subset)))

    def test_retire_only_matching_source_prefix_and_keep_unrelated_part(self):
        stage, source, part, alien, subset, proof = self.fixture()
        events = []
        with self.processing_mocks(), patch.object(motor, "evento", side_effect=lambda c,g,n,**kw: events.append((n,source.exists(),kw))):
            motor.retirar(self.cfg, "co", stage, source, proof)
        self.assertFalse(source.exists())
        self.assertFalse(part.exists())
        self.assertFalse(subset.exists())
        self.assertEqual(alien.read_bytes(), b"different unique data")
        self.assertEqual([x[0] for x in events], ["granulo_validado_pre_borrado", "retiro_temporales_autorizado", "crudo_eliminado_post_validacion"])
        self.assertTrue(events[1][1])
        self.assertFalse(events[2][1])

    def test_hash_mismatch_never_deletes_changed_source(self):
        stage, source, part, alien, subset, proof = self.fixture()
        proof["source_sha256"] = "wrong"
        motor.atomico(proof["transaction"], proof)
        with self.processing_mocks(), patch.object(motor, "evento"):
            with self.assertRaises(ValueError):
                motor.retirar(self.cfg, "co", stage, source, proof)
        self.assertTrue(source.exists())

    def test_prefix_comparison_handles_longer_and_different_files(self):
        source = self.root / "source"
        source.write_bytes(b"abc")
        candidate = self.root / "candidate"
        for data, expected in [(b"ab", True), (b"abc", True), (b"abcd", False), (b"ax", False)]:
            candidate.write_bytes(data)
            self.assertEqual(motor.mismos_prefijos(candidate, source), expected)


class PublicationTests(EngineTest):
    def test_all_new_publication_parents_are_synced_before_first_unlink(self):
        one = item()
        out, transaction, stage = self.paths(one)
        synced = set()
        original_unlink = Path.unlink
        required = {out.parent, out.parent.parent, out.parent.parent.parent,
                    self.root / "CO", self.root}
        def unlink(path, *args, **kwargs):
            self.assertTrue(required <= synced)
            self.assertTrue(out.is_file() and transaction.is_file())
            return original_unlink(path, *args, **kwargs)
        with self.processing_mocks(), patch.object(motor, "reservar", return_value=nullcontext()), \
             patch.object(motor, "descargar", side_effect=self.create_source), \
             patch.object(motor, "comprobar_disco"), \
             patch.object(motor, "fsync_dir", side_effect=lambda p: synced.add(Path(p))), \
             patch.object(Path, "unlink", new=unlink):
            motor.procesar(self.cfg, "co", one)
        self.assertTrue(out.exists() and transaction.exists())
        self.assertFalse(stage.exists())

    def test_new_month_parent_sync_failure_preserves_raw_and_never_unlinks(self):
        one = item()
        out, transaction, stage = self.paths(one)
        def fail(path):
            if Path(path) == out.parent.parent and out.parent.exists():
                raise OSError("new month parent sync failed")
        with self.processing_mocks(), patch.object(motor, "reservar", return_value=nullcontext()), \
             patch.object(motor, "descargar", side_effect=self.create_source), \
             patch.object(motor, "comprobar_disco"), patch.object(motor, "fsync_dir", side_effect=fail), \
             patch.object(Path, "unlink", side_effect=AssertionError("no unlink authorized")):
            with self.assertRaisesRegex(OSError, "new month parent"):
                motor.procesar(self.cfg, "co", one)
        self.assertTrue((stage / "source.nc").exists())
        self.assertTrue((stage / "prepare.json").exists())
        self.assertFalse(out.exists())
        self.assertFalse(transaction.exists())

    def test_recover_after_hardlink_before_commit_uses_prepared_output(self):
        one = item()
        out, transaction, stage = self.paths(one)
        def fail_publication(cfg, product, event_name, **kw):
            if event_name == "publicacion_validada":
                raise OSError("crash after hardlink")
        with self.processing_mocks(), patch.object(motor, "reservar", return_value=nullcontext()), \
             patch.object(motor, "descargar", side_effect=self.create_source), \
             patch.object(motor, "comprobar_disco"), patch.object(motor, "evento", side_effect=fail_publication):
            with self.assertRaisesRegex(OSError, "hardlink"):
                motor.procesar(self.cfg, "co", one)
        original_hash = motor.sha256(out)
        self.assertFalse(transaction.exists())
        self.assertTrue((stage / "prepare.json").exists())
        self.assertTrue((stage / "source.nc").exists())
        def no_recreate(*a):
            raise AssertionError("prepared output must not be recreated")
        with self.processing_mocks(create=no_recreate), patch.object(motor, "reservar", return_value=nullcontext()), \
             patch.object(motor, "descargar", side_effect=self.create_source), patch.object(motor, "evento"):
            motor.procesar(self.cfg, "co", one)
        self.assertEqual(motor.sha256(out), original_hash)
        self.assertTrue(transaction.exists())
        self.assertFalse(stage.exists())

    def test_modified_committed_output_is_preserved_and_not_reused(self):
        one = item()
        out, transaction, stage = self.paths(one)
        with self.processing_mocks(), patch.object(motor, "reservar", return_value=nullcontext()), \
             patch.object(motor, "descargar", side_effect=self.create_source), \
             patch.object(motor, "comprobar_disco"), patch.object(motor, "evento"):
            motor.procesar(self.cfg, "co", one)
        out.write_bytes(b"changed scientific result")
        with self.processing_mocks(), patch.object(motor, "descargar") as download, \
             patch.object(motor, "retirar") as retire:
            with self.assertRaisesRegex(ValueError, "alterada"):
                motor.procesar(self.cfg, "co", one)
        download.assert_not_called()
        retire.assert_not_called()
        self.assertEqual(out.read_bytes(), b"changed scientific result")

    def test_publish_prepare_commit_wal_then_delete_and_reuse_without_download(self):
        one = item()
        out, transaction, stage = self.paths(one)
        observations = []
        def event(cfg, product, event_name, **proof):
            observations.append((event_name, out.exists(), transaction.exists(), (stage / "source.nc").exists()))
        with self.processing_mocks(), patch.object(motor, "reservar", return_value=nullcontext()), \
             patch.object(motor, "descargar", side_effect=self.create_source) as download, \
             patch.object(motor, "comprobar_disco"), patch.object(motor, "evento", side_effect=event):
            result = motor.procesar(self.cfg, "co", one)
            self.assertEqual(result["status"], "downloaded")
            self.assertEqual(download.call_count, 1)
            self.assertTrue(transaction.exists())
            self.assertFalse(stage.exists(), "redundant staging should be retired after durable commit")
            self.assertFalse((stage / "source.nc").exists())
            again = motor.procesar(self.cfg, "co", one)
            self.assertEqual(again["status"], "reused")
            self.assertEqual(download.call_count, 1)
        names = [r[0] for r in observations]
        self.assertLess(names.index("publicacion_validada"), names.index("granulo_validado_pre_borrado"))
        self.assertTrue(next(r for r in observations if r[0] == "granulo_validado_pre_borrado")[2:][0])

    def test_failed_pre_delete_wal_recovery_does_not_recreate_output(self):
        one = item()
        out, transaction, stage = self.paths(one)
        def event(cfg, product, event_name, **kw):
            if event_name == "granulo_validado_pre_borrado":
                raise OSError("WAL unavailable")
        with self.processing_mocks(), patch.object(motor, "reservar", return_value=nullcontext()), \
             patch.object(motor, "descargar", side_effect=self.create_source), \
             patch.object(motor, "comprobar_disco"), patch.object(motor, "evento", side_effect=event):
            with self.assertRaises(OSError):
                motor.procesar(self.cfg, "co", one)
        original = out.read_bytes()
        self.assertTrue(transaction.exists())
        self.assertTrue((stage / "source.nc").exists())
        with self.processing_mocks(), patch.object(motor, "evento"), \
             patch.object(motor, "descargar", side_effect=AssertionError("must not download")):
            self.assertEqual(motor.procesar(self.cfg, "co", one)["status"], "reused")
        self.assertEqual(out.read_bytes(), original)
        self.assertFalse((stage / "source.nc").exists())

    def test_unproven_existing_output_never_overwritten(self):
        one = item()
        out, transaction, stage = self.paths(one)
        out.parent.mkdir(parents=True)
        out.write_bytes(b"unique unproven output")
        with self.processing_mocks(), patch.object(motor, "reservar", return_value=nullcontext()), \
             patch.object(motor, "descargar", side_effect=self.create_source):
            with self.assertRaises(ValueError):
                motor.procesar(self.cfg, "co", one)
        self.assertEqual(out.read_bytes(), b"unique unproven output")
        self.assertFalse(transaction.exists())
        self.assertTrue((stage / "source.nc").exists())

    def test_failed_validation_preserves_source_and_does_not_publish(self):
        one = item()
        out, transaction, stage = self.paths(one)
        def invalid(*a):
            raise ValueError("invalid native subset")
        with self.processing_mocks(validate=invalid), patch.object(motor, "reservar", return_value=nullcontext()), \
             patch.object(motor, "descargar", side_effect=self.create_source):
            with self.assertRaises(ValueError):
                motor.procesar(self.cfg, "co", one)
        self.assertFalse(out.exists())
        self.assertFalse(transaction.exists())
        self.assertTrue((stage / "source.nc").exists())


class ResumedSourceTests(EngineTest):
    def source_fixture(self):
        stage = self.root / "stage"
        stage.mkdir()
        source = stage / "source.nc"
        source.write_bytes(b"provider bytes")
        one = item()
        motor.atomico(stage / "downloaded.json", {"cmr_sha256": one["cmr_sha256"],
                                                "sha256": motor.sha256(source)})
        return stage, source, one

    def test_valid_durable_source_reentry_revalidates_without_auth_or_network(self):
        stage, source, one = self.source_fixture()
        with patch.dict(sys.modules, {"earthaccess": types.SimpleNamespace()}), \
             patch.object(motor, "autenticar", side_effect=AssertionError("network forbidden")), \
             patch.object(motor, "validar_fuente") as validate:
            self.assertEqual(motor.descargar(self.cfg, one, stage), source)
        validate.assert_called_once_with(source, one)

    def test_changed_source_or_cmr_record_fails_without_network(self):
        stage, source, one = self.source_fixture()
        for field in ["sha256", "cmr_sha256"]:
            proof = {"cmr_sha256": one["cmr_sha256"], "sha256": motor.sha256(source)}
            proof[field] = "different"
            motor.atomico(stage / "downloaded.json", proof)
            with self.subTest(field=field), patch.dict(sys.modules, {"earthaccess": types.SimpleNamespace()}), \
                 patch.object(motor, "autenticar", side_effect=AssertionError("network forbidden")):
                with self.assertRaisesRegex(ValueError, "registro"):
                    motor.descargar(self.cfg, one, stage)
            self.assertEqual(source.read_bytes(), b"provider bytes")

    def test_existing_source_must_match_provider_checksum_before_reuse(self):
        stage = self.root / "stage"
        stage.mkdir()
        source = stage / "source.nc"
        source.write_bytes(b"wrong but structurally readable NetCDF")
        one = item()
        one["checksum"] = {"Algorithm": "MD5", "Value": hashlib.md5(b"expected provider bytes").hexdigest()}
        motor.atomico(stage / "downloaded.json", {"cmr_sha256": one["cmr_sha256"],
                                                "sha256": motor.sha256(source)})
        nc = types.SimpleNamespace(orbit=one["orbit"], id=one["name"], ncattrs=lambda: ["orbit", "id"])
        with patch.dict(sys.modules, {"earthaccess": types.SimpleNamespace(),
                                      "netCDF4": types.SimpleNamespace(Dataset=lambda *a: nullcontext(nc))}):
            with self.assertRaisesRegex(ValueError, "checksum"):
                motor.descargar(self.cfg, one, stage)
        self.assertTrue(source.exists())

    def test_unknown_checksum_algorithm_is_not_silently_ignored(self):
        stage, source, one = self.source_fixture()
        one["checksum"] = {"Algorithm": "unknown", "Value": "ignored"}
        nc = types.SimpleNamespace(orbit=one["orbit"], id=one["name"], ncattrs=lambda: ["orbit", "id"])
        with patch.dict(sys.modules, {"netCDF4": types.SimpleNamespace(Dataset=lambda *a: nullcontext(nc))}):
            with self.assertRaisesRegex(ValueError, "no soportado"):
                motor.validar_fuente(source, one)
        self.assertTrue(source.exists())

    def test_native_source_id_and_orbit_must_match_catalogue(self):
        stage, source, one = self.source_fixture()
        for wrong in [{"orbit": 2, "id": one["name"]}, {"orbit": one["orbit"], "id": "other.nc"}]:
            nc = types.SimpleNamespace(**wrong, ncattrs=lambda: ["orbit", "id"])
            with self.subTest(wrong=wrong), patch.dict(sys.modules, {"netCDF4": types.SimpleNamespace(Dataset=lambda *a: nullcontext(nc))}):
                with self.assertRaises(ValueError):
                    motor.validar_fuente(source, one)


class HttpResumeTests(EngineTest):
    def request_fixture(self, *, status, headers, body):
        class Response:
            status_code = status
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def iter_content(self, *args):
                yield body
        response = Response()
        response.headers = headers
        session = unittest.mock.Mock()
        session.get.return_value = response
        earth = types.SimpleNamespace(get_requests_https_session=lambda: session)
        return earth, session

    def test_server_ignoring_range_retains_old_prefix_until_safe_retirement(self):
        stage = self.root / "stage"
        stage.mkdir()
        original = stage / "download.previous.part"
        original.write_bytes(b"abc")
        earth, session = self.request_fixture(status=200, headers={"Content-Length": "6"}, body=b"abcdef")
        with patch.dict(sys.modules, {"earthaccess": earth}), patch.object(motor, "autenticar"), \
             patch.object(motor, "comprobar_disco"), patch.object(motor, "validar_fuente"):
            source = motor.descargar(self.cfg, item(), stage)
        self.assertEqual(source.read_bytes(), b"abcdef")
        self.assertEqual(original.read_bytes(), b"abc")
        self.assertEqual(session.get.call_args.kwargs["headers"]["Range"], "bytes=3-")
        proof = json.loads((stage / "downloaded.json").read_text())
        self.assertEqual(proof["sha256"], motor.sha256(source))

    def test_wrong_content_range_does_not_append_or_delete_partial(self):
        stage = self.root / "stage"
        stage.mkdir()
        part = stage / "download.previous.part"
        part.write_bytes(b"abc")
        earth, session = self.request_fixture(status=206, headers={"Content-Range": "bytes 2-4/5"}, body=b"xyz")
        with patch.dict(sys.modules, {"earthaccess": earth}), patch.object(motor, "autenticar"):
            with self.assertRaisesRegex(ValueError, "Content-Range"):
                motor.descargar(self.cfg, item(), stage)
        self.assertEqual(part.read_bytes(), b"abc")
        self.assertFalse((stage / "source.nc").exists())

    def test_zero_byte_partial_is_preserved_without_exclusive_create_collision(self):
        stage = self.root / "stage"
        stage.mkdir()
        part = stage / "download.previous.part"
        part.touch()
        earth, session = self.request_fixture(status=200, headers={"Content-Length": "3"}, body=b"abc")
        with patch.dict(sys.modules, {"earthaccess": earth}), patch.object(motor, "autenticar"), \
             patch.object(motor, "comprobar_disco"), patch.object(motor, "validar_fuente"):
            source = motor.descargar(self.cfg, item(), stage)
        self.assertEqual(source.read_bytes(), b"abc")
        self.assertTrue(part.exists())
        self.assertEqual(part.stat().st_size, 0)
        self.assertNotIn("Range", session.get.call_args.kwargs["headers"])

    def test_truncated_http_response_retains_partial_without_durable_source(self):
        stage = self.root / "stage"
        stage.mkdir()
        earth, session = self.request_fixture(status=200, headers={"Content-Length": "9"}, body=b"abc")
        with patch.dict(sys.modules, {"earthaccess": earth}), patch.object(motor, "autenticar"), \
             patch.object(motor, "comprobar_disco"):
            with self.assertRaisesRegex(ValueError, "truncada"):
                motor.descargar(self.cfg, item(), stage)
        self.assertEqual([p.read_bytes() for p in stage.glob("*.part")], [b"abc"])
        self.assertFalse((stage / "source.nc").exists())
        self.assertFalse((stage / "downloaded.json").exists())

    def test_validated_part_with_durable_record_recovers_without_http_416(self):
        stage = self.root / "stage"
        stage.mkdir()
        part = stage / "download.completed.part"
        part.write_bytes(b"complete provider bytes")
        one = item()
        motor.atomico(stage / "downloaded.json", {"cmr_sha256": one["cmr_sha256"],
                                                "sha256": motor.sha256(part),
                                                "bytes": part.stat().st_size,
                                                "url": one["url"]})
        with patch.dict(sys.modules, {"earthaccess": types.SimpleNamespace()}), \
             patch.object(motor, "autenticar", side_effect=AssertionError("validated partial must not need HTTP Range")), \
             patch.object(motor, "validar_fuente") as validate:
            source = motor.descargar(self.cfg, one, stage)
        self.assertEqual(source.read_bytes(), b"complete provider bytes")
        self.assertFalse(part.exists())
        validate.assert_called_once()


class CatalogueTests(EngineTest):
    def aois(self):
        return [types.SimpleNamespace(id="a", bbox=(-76, -56.5, -66, -17)),
                types.SimpleNamespace(id="b", bbox=(-81.2, -34.1, -78.5, -26))]

    def test_snapshot_preserves_candidates_selection_and_never_closes_zero(self):
        found = [Granule(name(processor="020300")), Granule(name(stream="RPRO"))]
        earth = types.SimpleNamespace(search_data=lambda **kw: found)
        with patch.dict(sys.modules, {"earthaccess": earth}), patch.object(motor, "seleccionar", return_value=self.aois()):
            selected = motor.consultar(self.cfg, "co", "2023-10-05")
        self.assertEqual(len(selected), 1)
        event = json.loads((self.root / "_control_gases/co.jsonl").read_text())
        path = Path(event["snapshot"])
        proof = json.loads(path.read_text())
        self.assertEqual(len(proof["candidates"]), 2)
        self.assertEqual(proof["selected"], [selected[0]["name"]])
        self.assertFalse(proof["empty_is_final"])
        self.assertTrue(all(x["cmr_sha256"] and x["cmr"]["meta"]["concept-id"] for x in proof["candidates"]))

    def test_requery_same_execution_day_preserves_both_catalogue_snapshots(self):
        original = Granule(name(processor="020300"))
        newer = Granule(name(stream="RPRO"))
        search = unittest.mock.Mock(side_effect=[[original], [original, newer]])
        with patch.dict(sys.modules, {"earthaccess": types.SimpleNamespace(search_data=search)}), \
             patch.object(motor, "seleccionar", return_value=self.aois()[:1]):
            first = motor.consultar(self.cfg, "co", "2023-10-05")
            first_event = json.loads((self.root / "_control_gases/co.jsonl").read_text())
            first_path = Path(first_event["snapshot"])
            original_bytes = first_path.read_bytes()
            second = motor.consultar(self.cfg, "co", "2023-10-05")
        events = [json.loads(line) for line in (self.root / "_control_gases/co.jsonl").read_text().splitlines()]
        second_path = Path(events[-1]["snapshot"])
        self.assertNotEqual(first_path, second_path)
        self.assertEqual(first_path.read_bytes(), original_bytes)
        self.assertEqual(motor.sha256(first_path), first_event["snapshot_sha256"])
        self.assertEqual(motor.sha256(second_path), events[-1]["snapshot_sha256"])
        self.assertEqual(json.loads(first_path.read_text())["selected"], [first[0]["name"]])
        self.assertEqual(json.loads(second_path.read_text())["selected"], [second[0]["name"]])
        self.assertNotEqual(first[0]["name"], second[0]["name"])

    def test_conflicting_bbox_results_fail_before_processing(self):
        search = unittest.mock.Mock(side_effect=[[Granule(name(), revision=1)], [Granule(name(), revision=2)]])
        with patch.dict(sys.modules, {"earthaccess": types.SimpleNamespace(search_data=search)}), \
             patch.object(motor, "seleccionar", return_value=self.aois()), patch.object(motor, "procesar") as process:
            with self.assertRaisesRegex(ValueError, "CMR cambió"):
                motor.consultar(self.cfg, "co", "2023-10-05")
        process.assert_not_called()

    def test_zero_catalogue_is_pending_not_completed_day(self):
        with patch.object(motor, "consultar", return_value=[]), patch.object(motor, "procesar") as process:
            result = motor.dia_worker(self.cfg, "co", "2023-10-05")
        self.assertEqual(result["status"], "pending_source")
        process.assert_not_called()
        row = json.loads((self.root / "_control_gases/co.jsonl").read_text())
        self.assertEqual(row["evento"], "fuente_no_publicada_pendiente")


if __name__ == "__main__":
    unittest.main()
