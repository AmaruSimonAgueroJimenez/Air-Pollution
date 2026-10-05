"""Pruebas offline: fuentes sintéticas y disco temporal, nunca datos reales."""
from contextlib import ExitStack
from dataclasses import replace
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
import xarray as xr
from netCDF4 import Dataset

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import preparar_merra2_modelado as m


class MerraTransformTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(TemporaryDirectory())).resolve()
        self.dest = self.root / "native"
        self.legacy = self.root / "raw_chile_horario"
        self.legacy.mkdir()
        self.control = self.dest / "_control_transformacion"
        self.control.mkdir(parents=True)
        self.spec = replace(m.SPEC, salida=self.dest)
        self.period = pd.Period("2000-02", "M")
        for name, value in [("SPEC", self.spec), ("LEGACY", self.legacy), ("CONTROL", self.control)]:
            self.stack.enter_context(patch.object(m, name, value))
        self.stack.enter_context(patch.object(m, "guard", return_value=200 * 2**30))
        self.stack.enter_context(patch.object(m.nr, "asegurar_disco_externo"))
        self.stack.enter_context(patch.object(m.nr, "exigir_espacio"))
        self.stack.enter_context(patch.object(m.nr, "_catalogo_vigente", return_value=True))
        # Defaults ligados al importar: pasar el fixture a estas funciones.
        self.inventory_original = m.source_inventory
        self.compare_original = m.compare_full
        self.validate_original = m.validate_certificate
        self.retire_original = m.retire
        self.stack.enter_context(patch.object(m, "source_inventory", side_effect=lambda p: self.inventory_original(p, self.legacy)))
        self.stack.enter_context(patch.object(m, "compare_full", side_effect=lambda o, s, p: self.compare_original(o, s, p, self.spec)))
        self.stack.enter_context(patch.object(m, "validate_certificate", side_effect=lambda c: self.validate_original(c, self.spec)))
        self.stack.enter_context(patch.object(m, "retire", side_effect=lambda c, ctl, e: self.retire_original(c, ctl, e, self.legacy)))
        self.cat = self.dest / "catalogo_pixeles.parquet"
        self.rel = self.dest / "relacion_pixel_comuna.parquet"
        self.cm = self.dest / "metadata" / "catalogo_manifest.json"
        self.cm.parent.mkdir(parents=True)
        cat = pd.DataFrame({"pixel_id": [114*576+176,115*576+177],
                            "latitude": [-33., -32.5], "longitude": [-70., -69.375],
                            "lat_index_global": [114,115], "lon_index_global": [176,177],
                            "cod_comuna": [123,123], "territorio": ["continental"]*2, "aoi_id": ["continente"]*2})
        cat.to_parquet(self.cat,index=False)
        cat[["pixel_id","cod_comuna"]].to_parquet(self.rel,index=False)
        self.cm.write_text("{}")
        self.stack.enter_context(patch.object(m.nr, "crear_catalogos", side_effect=lambda spec, *a: (
            spec.salida / self.cat.name, spec.salida / self.rel.name, spec.salida / "metadata" / self.cm.name)))
        for day in pd.date_range("2000-02-01", "2000-02-29"):
            arr = np.arange(24*4, dtype="float32").reshape(24,2,2) + day.day
            arr[0,0,0] = np.nan
            ds = xr.Dataset({aliases[0]: (("time","lat","lon"),arr+i,{"units":"fixture", "source_flag":"preserved"})
                             for i,aliases in enumerate(self.spec.aliases.values())},
                            coords={"time":pd.date_range(day+pd.Timedelta(minutes=30),periods=24,freq="h"),
                                    "lat":[-33.,-32.5],"lon":[-70.,-69.375]})
            ds.to_netcdf(self.legacy / f"M2_merra2_hourly_{day:%Y%m%d}_chile.nc")
        self.code=m.archive_code(self.control)

    def run_month(self, retire=False):
        return m.process_month(self.period,self.code,"test",retire_legacy=retire)

    def cert(self):
        return json.loads((self.control / "meses/2000-02.json").read_text())

    def test_complete_exact_and_idempotent_preserves_sources(self):
        result=self.run_month()
        self.assertEqual(result["hours"],696)
        self.assertEqual(result["pixels"],2)
        self.assertEqual(len(list(self.legacy.glob("*.nc"))),29)
        cert=self.cert()
        self.assertEqual(cert["validation"]["valores_comparados"],696*2*9)
        before=Path(cert["output"]).read_bytes()
        self.assertEqual(self.run_month()["status"],"validated_existing")
        self.assertEqual(Path(cert["output"]).read_bytes(),before)

    def test_missing_day_is_pending_not_completed(self):
        (self.legacy / "M2_merra2_hourly_20000229_chile.nc").unlink()
        r=self.run_month()
        self.assertEqual(r["status"],"pending_local_sources")
        self.assertFalse((self.control / "meses/2000-02.json").exists())

    def test_changed_output_blocks_retirement(self):
        self.run_month()
        with Dataset(self.cert()["output"],"a") as nc:
            nc["t2m"][2,0]=999
        with self.assertRaisesRegex(RuntimeError,"alterada"):
            self.run_month(True)
        self.assertEqual(len(list(self.legacy.glob("*.nc"))),29)

    def test_retirement_wal_precedes_every_unlink(self):
        self.run_month()
        original=Path.unlink
        watched=[]
        def remove(path,*args,**kwargs):
            if path.parent==self.legacy:
                events=[json.loads(l) for l in (self.control / "eventos.jsonl").read_text().splitlines()]
                authorized=[e for e in events if e["evento"]=="retiro_legado_autorizado"]
                self.assertTrue(authorized)
                self.assertEqual(authorized[-1]["certificate_sha256"],m.sha(self.control / "meses/2000-02.json"))
                self.assertEqual(authorized[-1]["source_day_contract"],m.DAILY_CONTRACT)
                self.assertTrue((self.control / "meses/2000-02.json").exists())
                watched.append(path)
            return original(path,*args,**kwargs)
        with patch.object(Path,"unlink",remove):
            self.run_month(True)
        self.assertEqual(len(watched),29)
        self.assertEqual(len(list(self.legacy.glob("*.nc"))),0)
        self.assertEqual(self.run_month(True)["bytes_retired"],0)

    def test_validation_failure_preserves_sources_no_final_output(self):
        with patch.object(m,"compare_full",side_effect=ValueError("comparison")):
            with self.assertRaisesRegex(ValueError,"comparison"):
                self.run_month(True)
        self.assertEqual(len(list(self.legacy.glob("*.nc"))),29)
        self.assertFalse(m.nr.rutas_periodo(self.spec,self.period)[0].exists())

    def test_reentry_after_manifest_publication_failure(self):
        real=m.publish_file
        def fail(source,target,expected):
            if target.suffix==".json":raise OSError("manifest failure")
            return real(source,target,expected)
        with patch.object(m,"publish_file",side_effect=fail):
            with self.assertRaisesRegex(OSError,"manifest failure"):
                self.run_month()
        self.assertEqual(len(list(self.legacy.glob("*.nc"))),29)
        self.assertEqual(self.run_month()["status"],"validated")

    def test_nonfinite_metadata_is_valid_json(self):
        value=m.json_attr(np.array([np.nan,np.inf],dtype="float32"))
        json.dumps(value,allow_nan=False)

    def test_existing_foreign_output_not_overwritten(self):
        out,_=m.nr.rutas_periodo(self.spec,self.period)
        out.parent.mkdir(parents=True)
        out.write_bytes(b"previous protected")
        with self.assertRaisesRegex(RuntimeError,"previa"):
            self.run_month(True)
        self.assertEqual(out.read_bytes(),b"previous protected")

    def test_double_supervisor_rejected(self):
        with m.supervisor_lock(self.control):
            with self.assertRaisesRegex(RuntimeError,"activo"):
                with m.supervisor_lock(self.control):pass

    def test_exact_day_rejects_extra_missing_shifted_or_wrong_day_hours(self):
        path=self.legacy / "M2_merra2_hourly_20000201_chile.nc"
        with xr.open_dataset(path) as source:
            original=source.load()
        cases={
            "previous_month_extra":xr.concat([original.isel(time=[0]).assign_coords(time=[pd.Timestamp("2000-01-31T23:30")]),original],dim="time"),
            "next_month_extra":xr.concat([original,original.isel(time=[0]).assign_coords(time=[pd.Timestamp("2000-03-01T00:30")])],dim="time"),
            "missing_hour":original.isel(time=slice(1,None)),
            "wrong_minute":original.assign_coords(time=original.time-pd.Timedelta(minutes=30)),
            "wrong_day":original.assign_coords(time=original.time+pd.Timedelta(days=1)),
            "duplicate":xr.concat([original.isel(time=[0]),original],dim="time"),
        }
        for name,data in cases.items():
            with self.subTest(name=name):
                data.to_netcdf(path)
                with self.assertRaisesRegex(ValueError,"exactamente 24 horas"):
                    m.validate_source_day(path,self.period)

    def test_invalid_calendar_date_in_filename_rejected(self):
        path=self.legacy / "M2_merra2_hourly_20000230_chile.nc"
        path.write_bytes(b"not a calendar day")
        with self.assertRaisesRegex(ValueError,"calendario"):
            self.inventory_original(self.period,self.legacy)

    def test_old_certificate_with_extra_source_hour_cannot_authorize_retirement(self):
        path=self.legacy / "M2_merra2_hourly_20000201_chile.nc"
        with xr.open_dataset(path) as source:
            original=source.load()
        extra=original.isel(time=[0]).assign_coords(time=[pd.Timestamp("2000-01-31T23:30")])
        xr.concat([extra,original],dim="time").to_netcdf(path)
        # Simula el contrato antiguo: el motor mensual filtra la hora externa.
        with patch.object(m,"validate_source_day",return_value=None):
            self.run_month()
        certificate=self.cert()
        certificate["validation"].pop("source_day_contract",None)
        (self.control / "meses/2000-02.json").write_text(json.dumps(certificate))
        with self.assertRaisesRegex(ValueError,"exactamente 24 horas"):
            self.run_month(True)
        self.assertEqual(len(list(self.legacy.glob("*.nc"))),29)
        events=[json.loads(l) for l in (self.control / "eventos.jsonl").read_text().splitlines()]
        self.assertFalse(any(e["evento"]=="retiro_legado_autorizado" for e in events))

    def test_existing_certificate_fastpath_obeys_monthly_publisher_lock(self):
        self.run_month()
        lock=self.dest / ".locks/normalizar_200002.lock"
        with m.nr.bloqueo(lock):
            with self.assertRaisesRegex(RuntimeError,"concurrente activo"):
                self.run_month(True)
        self.assertEqual(len(list(self.legacy.glob("*.nc"))),29)

    def test_changed_runtime_blocks_retirement(self):
        self.run_month()
        (Path(self.cert()["code"]["bundle"]) / "runtime.json").write_text("{}")
        with self.assertRaisesRegex(RuntimeError,"Runtime archivado alterado"):
            self.run_month(True)
        self.assertEqual(len(list(self.legacy.glob("*.nc"))),29)

    def test_changed_source_or_catalogue_blocks_retirement(self):
        self.run_month()
        path=self.legacy / "M2_merra2_hourly_20000201_chile.nc"
        with Dataset(path,"a") as source:
            source["T2M"][2,0,0]=999
        with self.assertRaisesRegex(RuntimeError,"Fuente ausente o modificada"):
            self.run_month(True)
        self.cm.write_text('{"changed":true}')
        with self.assertRaisesRegex(RuntimeError,"Referencia alterada"):
            self.run_month(True)
        self.assertEqual(len(list(self.legacy.glob("*.nc"))),29)

    def test_certificate_duplicate_or_foreign_source_days_rejected(self):
        self.run_month()
        certificate=self.cert()
        certificate["sources"][0]=certificate["sources"][1]
        with self.assertRaisesRegex(ValueError,"exactamente una fuente"):
            self.validate_original(certificate,self.spec)
        certificate=self.cert()
        certificate["sources"][0]["archivo"]="M2_merra2_hourly_20000301_chile.nc"
        certificate["sources"][0]["ruta_al_normalizar"]=str(self.legacy / certificate["sources"][0]["archivo"])
        with self.assertRaisesRegex(ValueError,"ajena"):
            self.validate_original(certificate,self.spec)

    def test_missing_original_without_strict_wal_blocks_remaining_retirement(self):
        self.run_month()
        (self.legacy / "M2_merra2_hourly_20000201_chile.nc").unlink()
        with self.assertRaisesRegex(RuntimeError,"ausente sin autorización"):
            self.run_month(True)
        self.assertEqual(len(list(self.legacy.glob("*.nc"))),28)

    def test_resume_after_unlink_before_individual_event(self):
        self.run_month()
        original=Path.unlink
        def interrupt(path,*args,**kwargs):
            result=original(path,*args,**kwargs)
            if path.parent==self.legacy:
                raise OSError("interrupted after unlink")
            return result
        with patch.object(Path,"unlink",interrupt):
            with self.assertRaisesRegex(OSError,"interrupted after unlink"):
                self.run_month(True)
        self.assertEqual(len(list(self.legacy.glob("*.nc"))),28)
        self.assertGreater(self.run_month(True)["bytes_retired"],0)
        self.assertEqual(len(list(self.legacy.glob("*.nc"))),0)
        self.assertEqual(self.run_month(True)["bytes_retired"],0)


if __name__=="__main__":unittest.main()
