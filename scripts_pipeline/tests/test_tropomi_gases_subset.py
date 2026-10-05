"""Synthetic-only tests; never opens/modifies production scientific files."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import geopandas as gpd
import netCDF4
import numpy as np
import shapely
from shapely.geometry import MultiPolygon, box

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _tropomi_gases_subset as m


class SubsetTests(unittest.TestCase):
    def setUp(self):
        m._mascara_preparada.cache_clear()
        self.addCleanup(m._mascara_preparada.cache_clear)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.mask = self.root / "comunas.shp"
        gpd.GeoDataFrame({"cod_comuna": [13101, 0, 5104, 5201, 999]}, geometry=[
            box(-71, -34, -70, -33), box(-70.3, -33.7, -70.1, -33.5),
            MultiPolygon([box(-80.9, -33.9, -80.7, -33.7), box(-80.2, -26.4, -80, -26.2)]),
            MultiPolygon([box(-109.5, -27.3, -109.3, -27.1), box(-105.4, -26.5, -105.2, -26.3)]),
            box(-75, -80, -74, -79),
        ], crs="EPSG:4326").to_file(self.mask)
        self.sha = m._sha_mascara(self.mask)

    def source(self, gas="co", omit=(), *, outside=False, all_invalid=False, invalid_candidate=False,
               cf_time=False, delta_per_pixel=False, empty_time=False):
        path = self.root / f"{gas}.nc"
        with netCDF4.Dataset(path, "w") as ds:
            ds.orbit = 12345
            ds.history = "source unmodified"
            ds.geospatial_lon_min = -180.0
            for name, size in (("time", 1), ("scanline", 3), ("ground_pixel", 4), ("corner", 4), ("layer", 2), ("level", 3)):
                ds.createDimension(name, None if name == "time" else size)
            p = ds.createGroup("PRODUCT")
            p.description = "full science tree"
            support = p.createGroup("SUPPORT_DATA")
            geo = support.createGroup("GEOLOCATIONS")
            inp = support.createGroup("INPUT_DATA")
            details = support.createGroup("DETAILED_RESULTS")
            points = [(-70.8, -33.2), (-70.6, -33.3), (-70.2, -33.6), (-71.1, -33.5),
                      (-80.8, -33.8), (-80.1, -26.3), (-109.4, -27.2), (-105.3, -26.4),
                      (-90, -35), (179.8, -30), (-74.5, -79.5), (999, 999)]
            if outside:
                points = [(-90, -35)] * 12
            if all_invalid:
                points = [(999, 999)] * 12
            lon = np.array([x[0] for x in points]).reshape(1, 3, 4)
            lat = np.array([x[1] for x in points]).reshape(1, 3, 4)
            for name, data in (("longitude", lon), ("latitude", lat)):
                if name not in omit:
                    v = p.createVariable(name, "f8", ("time", "scanline", "ground_pixel"), fill_value=999.)
                    v[:] = data
                    v.units = "degrees_east" if name == "longitude" else "degrees_north"
            bounds_lon, bounds_lat = [], []
            for i, (x, y) in enumerate(points):
                width = .25 if i == 3 and not outside else .04
                bounds_lon.append([x-width, x+width, x+width, x-width])
                bounds_lat.append([y-width, y-width, y+width, y+width])
            if not outside and not all_invalid:
                bounds_lon[9] = [179.5, -179.5, -179.5, 179.5]
                bounds_lon[11] = bounds_lat[11] = [999] * 4
            if all_invalid:
                bounds_lon = bounds_lat = [[999] * 4] * 12
            if invalid_candidate:
                bounds_lon[0][0] = 999
            for name, data in (("longitude_bounds", bounds_lon), ("latitude_bounds", bounds_lat)):
                if name not in omit:
                    v = geo.createVariable(name, "f8", ("time", "scanline", "ground_pixel", "corner"), fill_value=999.)
                    v[:] = np.array(data).reshape(1, 3, 4, 4)
            principal = m.PRINCIPALES[gas]
            for name in (principal, principal + "_precision", "qa_value"):
                if name in omit:
                    continue
                v = p.createVariable(name, "i2", ("time", "scanline", "ground_pixel"), fill_value=-999)
                v.set_auto_maskandscale(False)
                raw = np.arange(12, dtype="i2").reshape(1, 3, 4)
                raw[0, 0, 0] = -1
                raw[0, 0, 1] = -999
                v[:] = raw
                v.scale_factor = np.float32(.01)
                v.add_offset = np.float32(.1)
                v.units = "ppb" if gas == "ch4" else "mol m-2"
            for name, dim, data in (("scanline", "scanline", [10, 20, 30]), ("ground_pixel", "ground_pixel", [4, 5, 6, 7])):
                p.createVariable(name, "i4", (dim,))[:] = data
            base = p.createVariable("time", "i8", ("time",))
            base[:] = [434160000 if cf_time else 1000]
            if cf_time:
                base.units = "seconds since 2010-01-01 00:00:00"
                ds.time_reference = "2023-10-05T00:00:00Z"
            if "time_utc" not in omit:
                p.createVariable("time_utc", str, ("time", "scanline"))[:] = np.array([[""]*3] if empty_time else [["2023-10-05T17:00:00Z", "2023-10-05T17:00:01Z", "2023-10-05T17:00:02Z"]], dtype=object)
            if "delta_time" not in omit:
                dims = ("time", "scanline", "ground_pixel") if delta_per_pixel else ("time", "scanline")
                v = p.createVariable("delta_time", "i8", dims, fill_value=-999)
                v[:] = (63086385 + np.arange(12)).reshape(1, 3, 4) if delta_per_pixel else [[111, 222, 333]]
                v.units = "milliseconds since 2023-10-05 00:00:00Z" if cf_time else "milliseconds since reference time"
            v = details.createVariable("averaging_kernel", "f4", ("time", "scanline", "ground_pixel", "layer"))
            raw = np.arange(24, dtype="f4").reshape(1, 3, 4, 2)
            raw.view("u4")[0, 0, 0, 0] = 0x7fc00011  # preserve noncanonical NaN bits
            v[:] = raw
            v.units = "1"
            inp.createVariable("prior_profile", "f8", ("layer", "time", "ground_pixel", "scanline"))[:] = np.arange(24).reshape(2, 1, 4, 3)
            inp.createVariable("pressure_levels", "f8", ("time", "scanline", "ground_pixel", "level"))[:] = np.arange(36).reshape(1, 3, 4, 3)
            inp.createVariable("surface_class", "u1", ("ground_pixel",))[:] = [2, 3, 4, 5]
            inp.createVariable("constant", "f8")[:] = 42
            if gas == "ch4":
                details.createVariable("methane_mixing_ratio_bias_corrected", "f8", ("time", "scanline", "ground_pixel"))[:] = np.arange(12).reshape(1, 3, 4)
            ds.createGroup("INSTRUMENT").createVariable("not_science", "i4")[:] = 42
        return path

    def test_five_gases_all_native_variables_islands_and_bitwise(self):
        for gas in m.PRINCIPALES:
            with self.subTest(gas=gas):
                src = self.source(gas)
                before = src.read_bytes()
                out = self.root / f"{gas}.subset.nc"
                result = m.crear_subset(src, out, gas, self.mask, self.sha)
                self.assertEqual(result["pixeles_chile"], 8)
                self.assertEqual(result["cobertura_nativa"]["time_utc_first"], "2023-10-05T17:00:00Z")
                self.assertEqual(result["cobertura_nativa"]["time_utc_last"], "2023-10-05T17:00:01Z")
                self.assertEqual(result["cobertura_nativa"]["huellas_invalidas"], 1)
                self.assertEqual(set(result["cobertura_nativa"]["aois_con_pixeles"]), {"continente", "juan_fernandez", "desventuradas", "rapa_nui", "sala_y_gomez"})
                self.assertEqual(src.read_bytes(), before)
                with netCDF4.Dataset(src) as a, netCDF4.Dataset(out) as b:
                    self.assertNotIn("INSTRUMENT", b.groups)
                    self.assertEqual(b["PRODUCT"]["delta_time"].dimensions, ("time", "pixel"))
                    self.assertEqual(b["PRODUCT"]["SUPPORT_DATA"]["INPUT_DATA"]["prior_profile"].dimensions, ("layer", "time", "pixel"))
                    np.testing.assert_array_equal(b["CHILE_SUBSET"]["source_scanline_index"][:], [0]*4+[1]*4)
                    np.testing.assert_array_equal(b["CHILE_SUBSET"]["cod_comuna"][:], [13101, 13101, 0, -1, 5104, 5104, 5201, 5201])
                    np.testing.assert_array_equal(b["PRODUCT"]["delta_time"][:], [[111]*4+[222]*4])
                    self.assertEqual(b["PRODUCT"]["time_utc"][0, 0], "2023-10-05T17:00:00Z")
                    self.assertEqual(b["PRODUCT"]["time_utc"][0, 4], "2023-10-05T17:00:01Z")
                    for path, var in m._variables(a["PRODUCT"]):
                        actual = m._raw(b[path])[...]
                        expected = m._seleccionar(var, np.array([0]*4+[1]*4), np.array([0,1,2,3]*2))
                        if actual.dtype.kind == "O":
                            np.testing.assert_array_equal(actual, expected)
                        else:
                            self.assertEqual(actual.tobytes(), expected.tobytes(), path)
                        self.assertEqual(m._attrs_hash(var), m._attrs_hash(b[path]))
                self.assertEqual(m.validar_subset(out, gas, self.sha)["pixeles_chile"], 8)

    def test_missing_qa_precision_bounds_and_time_rejected(self):
        for name in ("qa_value", "carbonmonoxide_total_column_precision", "longitude_bounds", "time_utc", "delta_time"):
            with self.subTest(name=name):
                src = self.source(omit=(name,))
                out = self.root / f"missing_{name}.nc"
                with self.assertRaises(ValueError):
                    m.crear_subset(src, out, "co", self.mask, self.sha)
                self.assertFalse(out.exists())

    def test_prepared_mask_equals_unprepared_exact_selection_and_aoi_counts(self):
        src = self.source()
        with netCDF4.Dataset(src) as ds:
            prepared = m._seleccion_geografica(ds, self.mask)
        m._mascara_preparada.cache_clear()
        with mock.patch.object(shapely, "prepare", return_value=None) as prepare:
            with netCDF4.Dataset(src) as ds:
                unprepared = m._seleccion_geografica(ds, self.mask)
            self.assertEqual(prepare.call_count, 6)  # unión total y cinco AOIs
        for actual, expected in zip(prepared[:3], unprepared[:3]):
            np.testing.assert_array_equal(actual, expected)
        self.assertEqual(prepared[3], unprepared[3])

    def test_mask_cache_reuses_and_changed_mask_same_path_invalidates(self):
        src = self.source()
        with mock.patch.object(m, "_mascara", wraps=m._mascara) as build:
            with netCDF4.Dataset(src) as ds:
                old = m._seleccion_geografica(ds, self.mask)
                again = m._seleccion_geografica(ds, self.mask)
            self.assertEqual(build.call_count, 1)
            np.testing.assert_array_equal(old[0], again[0])
            frame = gpd.read_file(self.mask)
            frame.loc[0, "geometry"] = box(10, 10, 11, 11)
            frame.to_file(self.mask)
            self.assertNotEqual(self.sha, m._sha_mascara(self.mask))
            with self.assertRaises(ValueError):
                m.crear_subset(src, self.root / "stale.nc", "co", self.mask, self.sha)
            with netCDF4.Dataset(src) as ds:
                changed = m._seleccion_geografica(ds, self.mask)
            self.assertEqual(build.call_count, 2)
            self.assertLess(len(changed[0]), len(old[0]))
        cached = m._mascara_preparada(str(self.mask.resolve()), m._sha_mascara(self.mask))
        self.assertFalse(cached[0].flags.writeable)
        self.assertFalse(cached[1].flags.writeable)

    def test_empty_or_missing_utc_resolves_cf_per_pixel_and_preserves_original(self):
        for gas, omit in (("o3", ()), ("hcho", ()), ("co", ("time_utc",))):
            with self.subTest(gas=gas):
                src = self.source(gas, omit=omit, cf_time=True, delta_per_pixel=True, empty_time=True)
                before = src.read_bytes()
                out = self.root / (gas + ".cf.nc")
                result = m.crear_subset(src, out, gas, self.mask, self.sha)
                self.assertEqual(src.read_bytes(), before)
                with netCDF4.Dataset(out) as ds:
                    times = ds["CHILE_SUBSET"]["observation_time_utc"][:]
                    self.assertEqual(times[0], "2023-10-05T17:31:26.385000Z")
                    self.assertEqual(times[1], "2023-10-05T17:31:26.386000Z")
                    self.assertEqual(times[-1], "2023-10-05T17:31:26.392000Z")
                    if not omit:
                        self.assertTrue(all(x == "" for x in ds["PRODUCT"]["time_utc"][:].flat))
                    else:
                        self.assertNotIn("time_utc", ds["PRODUCT"].variables)
                self.assertEqual(result["cobertura_nativa"]["time_utc_first"], times[0])
                self.assertEqual(result["cobertura_nativa"]["time_resolution"]["resolved_cf_pixels"], 8)

    def test_cf_simple_units_and_reference_mismatches_or_fill(self):
        for setting in ("simple", "bad_time_reference", "bad_epoch", "fill", "invalid_units"):
            with self.subTest(setting=setting):
                src = self.source(cf_time=True, delta_per_pixel=True, empty_time=True)
                with netCDF4.Dataset(src, "r+") as ds:
                    if setting == "simple": ds["PRODUCT"]["delta_time"].units = "milliseconds"
                    if setting == "bad_time_reference": ds.time_reference = "2023-10-06T00:00:00Z"
                    if setting == "bad_epoch": ds["PRODUCT"]["delta_time"].units = "milliseconds since 2023-10-06 00:00:00Z"
                    if setting == "fill": ds["PRODUCT"]["delta_time"][0, 0, 0] = -999
                    if setting == "invalid_units": ds["PRODUCT"]["delta_time"].units = "unspecified"
                out = self.root / (setting + ".nc")
                if setting == "simple":
                    result = m.crear_subset(src, out, "co", self.mask, self.sha)
                    self.assertEqual(result["cobertura_nativa"]["time_utc_first"], "2023-10-05T17:31:26.385000Z")
                else:
                    with self.assertRaises(ValueError): m.crear_subset(src, out, "co", self.mask, self.sha)
                    self.assertFalse(out.exists())

    def test_original_time_never_gets_delta_added_and_conflict_rejected(self):
        src = self.source(cf_time=True)
        with netCDF4.Dataset(src, "r+") as ds:
            ds["PRODUCT"]["time_utc"][:] = np.array([["2023-10-05T00:00:00.111000Z", "2023-10-05T00:00:00.222000Z", "2023-10-05T00:00:00.333000Z"]], dtype=object)
        out = self.root / "original.nc"
        m.crear_subset(src, out, "co", self.mask, self.sha)
        with netCDF4.Dataset(out) as ds:
            self.assertEqual(ds["CHILE_SUBSET"]["observation_time_utc"][0], ds["PRODUCT"]["time_utc"][0, 0])
        with netCDF4.Dataset(src, "r+") as ds:
            ds["PRODUCT"]["time_utc"][0, 0] = "2023-10-05T01:00:00Z"
        with self.assertRaises(ValueError): m.crear_subset(src, self.root / "conflict.nc", "co", self.mask, self.sha)

    def test_legacy_contract_without_resolved_field_requires_complete_original_utc(self):
        for empty in (False, True):
            with self.subTest(empty=empty):
                src = self.source(cf_time=empty, delta_per_pixel=empty, empty_time=empty)
                modern = self.root / f"modern{empty}.nc"
                legacy = self.root / f"legacy{empty}.nc"
                m.crear_subset(src, modern, "co", self.mask, self.sha)
                with netCDF4.Dataset(modern) as a, netCDF4.Dataset(legacy, "w") as b:
                    def copy(group, target):
                        for name, dim in group.dimensions.items(): target.createDimension(name, len(dim))
                        target.setncatts({k: group.getncattr(k) for k in group.ncattrs()})
                        for name, var in group.variables.items():
                            if name == "observation_time_utc": continue
                            attrs = {k: var.getncattr(k) for k in var.ncattrs()}
                            dst = target.createVariable(name, m._tipo(target, var), var.dimensions,
                                                        fill_value=attrs.pop("_FillValue", False))
                            m._raw(dst)[...] = m._raw(var)[...]
                            dst.setncatts(attrs)
                        for name, child in group.groups.items(): copy(child, target.createGroup(name))
                    copy(a, b)
                    contract = json.loads(b.chile_subset_contract)
                    contract["variables"].pop("/CHILE_SUBSET/observation_time_utc")
                    b.chile_subset_contract = json.dumps(contract, sort_keys=True)
                if empty:
                    with self.assertRaises(ValueError): m.validar_subset(legacy, "co", self.sha)
                else:
                    self.assertEqual(m.validar_subset(legacy, "co", self.sha)["pixeles_chile"], 8)

    def test_ch4_requires_original_precision_not_invented_variant(self):
        src = self.source("ch4", omit=("methane_mixing_ratio_precision",))
        with self.assertRaises(ValueError):
            m.crear_subset(src, self.root / "bad.nc", "ch4", self.mask, self.sha)

    def test_zero_only_with_real_valid_remote_geolocation(self):
        src = self.source(outside=True)
        out = self.root / "empty.nc"
        self.assertEqual(m.crear_subset(src, out, "co", self.mask, self.sha)["pixeles_chile"], 0)
        self.assertEqual(m.validar_subset(out, "co", self.sha)["pixeles_chile"], 0)

    def test_invalid_global_or_candidate_bounds_not_empty(self):
        for kwargs in ({"all_invalid": True}, {"invalid_candidate": True}):
            with self.subTest(kwargs=kwargs):
                src = self.source(**kwargs)
                with self.assertRaises(ValueError):
                    m.crear_subset(src, self.root / "invalid.nc", "co", self.mask, self.sha)

    def test_degenerate_remote_bounds_cannot_prove_empty(self):
        src = self.source(outside=True)
        with netCDF4.Dataset(src, "r+") as ds:
            geo = ds["PRODUCT"]["SUPPORT_DATA"]["GEOLOCATIONS"]
            geo["longitude_bounds"][:] = -90.
            geo["latitude_bounds"][:] = -35.
        with self.assertRaises(ValueError):
            m.crear_subset(src, self.root / "degenerate.nc", "co", self.mask, self.sha)

    def test_copy_reopen_and_fsync_failure_preserve_source_and_partial(self):
        for target in ("_copiar_variable", "validar_subset", "os.fsync"):
            with self.subTest(target=target):
                src = self.source()
                before = src.read_bytes()
                out = self.root / (target + ".nc")
                with mock.patch.object(m, target, side_effect=RuntimeError("injected")) if "." not in target else mock.patch.object(m.os, "fsync", side_effect=RuntimeError("injected")):
                    with self.assertRaises(RuntimeError):
                        m.crear_subset(src, out, "co", self.mask, self.sha)
                self.assertEqual(src.read_bytes(), before)
                self.assertTrue(out.exists())
                with self.assertRaises(FileExistsError):
                    m.crear_subset(src, out, "co", self.mask, self.sha)

    def test_bad_mask_or_gas_and_existing_output_rejected(self):
        src = self.source()
        out = self.root / "ok.nc"
        with self.assertRaises(ValueError):
            m.crear_subset(src, out, "co", self.mask, "bad")
        m.crear_subset(src, out, "co", self.mask, self.sha)
        original = out.read_bytes()
        with self.assertRaises(FileExistsError):
            m.crear_subset(src, out, "co", self.mask, self.sha)
        self.assertEqual(out.read_bytes(), original)
        for gas, mask in (("co", "bad"), ("so2", self.sha)):
            with self.assertRaises(ValueError):
                m.validar_subset(out, gas, mask)

    def test_tampered_qa_precision_kernel_or_units_fails_reopen(self):
        for target, attribute in (("/PRODUCT/qa_value", False), ("/PRODUCT/carbonmonoxide_total_column_precision", False), ("/PRODUCT/SUPPORT_DATA/DETAILED_RESULTS/averaging_kernel", False), ("/PRODUCT/carbonmonoxide_total_column", True)):
            with self.subTest(target=target):
                src = self.source()
                out = self.root / (target.rsplit("/",1)[-1] + ".out.nc")
                m.crear_subset(src, out, "co", self.mask, self.sha)
                with netCDF4.Dataset(out, "r+") as ds:
                    v = m._raw(ds[target])
                    if attribute:
                        v.units = "wrong"
                    else:
                        v[tuple(0 for _ in v.dimensions)] = 10
                with self.assertRaises(ValueError):
                    m.validar_subset(out, "co", self.sha)

    def test_source_id_char_enum_compound_and_vlen_preserved(self):
        src = self.source()
        native = "S5P_OFFL_L2__CO_____20231005T170952_20231005T185121_30976_03_020500_20231007T065921.nc"
        with netCDF4.Dataset(src, "r+") as ds:
            ds.delncattr("orbit")
            ds.id = native
            p = ds["PRODUCT"]
            p.createDimension("strlen", 3)
            p.createVariable("text_metadata", "S1", ("scanline", "strlen"))[:] = np.array([list(b"abc"), list(b"def"), list(b"ghi")], dtype="u1").view("S1")
            enum = p.createEnumType("u1", "cloud_type", {"clear": 0, "cloudy": 1})
            p.createVariable("enum_flags", enum, ("scanline", "ground_pixel"))[:] = np.zeros((3, 4), dtype="u1")
            typ = p.createCompoundType(np.dtype([("x", "f4"), ("flag", "u1")], align=True), "pair_type")
            vals = np.zeros((3, 4), dtype=typ.dtype)
            vals["x"] = np.arange(12).reshape(3, 4)
            vals["flag"] = 3
            p.createVariable("compound_flags", typ, ("scanline", "ground_pixel"))[:] = vals
            vt = p.createVLType(np.int32, "vectors")
            vv = p.createVariable("vlen_metadata", vt, ("scanline",))
            for i in range(3):
                vv[i] = np.arange(i + 1, dtype="i4")
        out = self.root / "types.nc"
        result = m.crear_subset(src, out, "co", self.mask, self.sha)
        self.assertEqual(result["source_granule"], native)
        with netCDF4.Dataset(out) as ds:
            self.assertEqual(int(ds["CHILE_SUBSET"].orbit), 30976)
            self.assertEqual(ds["PRODUCT"]["compound_flags"].dimensions, ("pixel",))
            self.assertEqual(ds["PRODUCT"]["text_metadata"].dimensions, ("pixel", "strlen"))
            self.assertEqual(len(ds.dimensions["time"]), 1)
        m.validar_subset(out, "co", self.sha)


if __name__ == "__main__":
    unittest.main()
