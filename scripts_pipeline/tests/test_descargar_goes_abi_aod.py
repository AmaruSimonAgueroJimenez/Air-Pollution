from __future__ import annotations

import json
import math
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

# La raíz de datos debe existir antes de importar ``_common`` (comprueba el
# volumen externo cuando no hay raíz explícita). Los tests nunca escriben en
# la raíz real: cada caso usa su propio directorio temporal.
_RAIZ_TEST = tempfile.mkdtemp(prefix="goes-abi-test-root-")
os.environ.setdefault("AIR_POLLUTION_DATA_ROOT", _RAIZ_TEST)

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import descargar_goes_abi_aod as goes  # noqa: E402
from _chile_aoi import AOI  # noqa: E402

R_EQ, R_POL, ALTURA = 6378137.0, 6356752.31414, 35786023.0
PROJ = goes.Proyeccion(perspective_point_height=ALTURA, semi_major_axis=R_EQ,
                       semi_minor_axis=R_POL, longitude_of_projection_origin=-75.0,
                       sweep_angle_axis="x")
AOIS_TEST = (
    AOI("continente", "continental", (-75.80, -56.05, -66.35, -17.43)),
    AOI("juan_fernandez", "juan_fernandez_desventuradas", (-80.90, -33.87, -78.72, -33.52)),
    AOI("desventuradas", "juan_fernandez_desventuradas", (-80.20, -26.40, -79.80, -26.20)),
    AOI("rapa_nui", "isla_de_pascua", (-109.51, -27.26, -109.17, -26.99)),
    AOI("sala_y_gomez", "isla_de_pascua", (-105.42, -26.54, -105.30, -26.42)),
)


def latlon_a_fixed_grid(lat, lon, proj=PROJ):
    """Inversa PUG §4.2.8.2 (sólo para construir archivos sintéticos)."""
    lat, lon = math.radians(lat), math.radians(lon)
    lam0 = math.radians(proj.longitude_of_projection_origin)
    e2 = (proj.semi_major_axis**2 - proj.semi_minor_axis**2) / proj.semi_major_axis**2
    phi_c = math.atan((proj.semi_minor_axis**2 / proj.semi_major_axis**2) * math.tan(lat))
    r_c = proj.semi_minor_axis / math.sqrt(1 - e2 * math.cos(phi_c)**2)
    sx = proj.H - r_c * math.cos(phi_c) * math.cos(lon - lam0)
    sy = -r_c * math.cos(phi_c) * math.sin(lon - lam0)
    sz = r_c * math.sin(phi_c)
    y = math.atan(sz / sx)
    x = math.asin(-sy / math.sqrt(sx**2 + sy**2 + sz**2))
    return x, y


def escribir_abi_sintetico(path: Path, x_rad, y_rad, aod_raw, dqf_raw, ae1_raw, ae2_raw,
                           inicio: datetime, fin: datetime, *, lon_origen=-75.0,
                           subpoint=-75.2, dataset_name="sintetico"):
    import netCDF4

    x_rad = np.asarray(x_rad, dtype="float64")
    y_rad = np.asarray(y_rad, dtype="float64")
    with netCDF4.Dataset(path, "w", format="NETCDF4") as nc:
        nc.createDimension("y", y_rad.size)
        nc.createDimension("x", x_rad.size)
        nc.createDimension("number_of_time_bounds", 2)
        nc.setncattr("dataset_name", dataset_name)
        nc.setncattr("platform_ID", "G16")
        nc.setncattr("orbital_slot", "GOES-East")
        nc.setncattr("spatial_resolution", "2km at nadir")
        nc.setncattr("time_coverage_start", inicio.strftime("%Y-%m-%dT%H:%M:%S.%fZ"))
        nc.setncattr("time_coverage_end", fin.strftime("%Y-%m-%dT%H:%M:%S.%fZ"))
        proj = nc.createVariable("goes_imager_projection", "i4")
        proj.setncattr("perspective_point_height", ALTURA)
        proj.setncattr("semi_major_axis", R_EQ)
        proj.setncattr("semi_minor_axis", R_POL)
        proj.setncattr("longitude_of_projection_origin", float(lon_origen))
        proj.setncattr("sweep_angle_axis", "x")
        dx = float(np.median(np.diff(x_rad)))
        dy = float(np.median(np.diff(y_rad)))
        vx = nc.createVariable("x", "i2", ("x",))
        vx.set_auto_maskandscale(False)
        vx.setncattr("scale_factor", dx)
        vx.setncattr("add_offset", float(x_rad[0]))
        vx.setncattr("units", "rad")
        vx[:] = np.arange(x_rad.size, dtype="int16")
        vy = nc.createVariable("y", "i2", ("y",))
        vy.set_auto_maskandscale(False)
        vy.setncattr("scale_factor", dy)
        vy.setncattr("add_offset", float(y_rad[0]))
        vy.setncattr("units", "rad")
        vy[:] = np.arange(y_rad.size, dtype="int16")
        for nombre, datos, dtype, attrs in (
            ("AOD", aod_raw, "i2", {"_FillValue": np.int16(-1), "scale_factor": 7.706e-05,
                                    "add_offset": -0.05, "units": "1",
                                    "valid_range": [np.int16(0), np.int16(-6)],
                                    "long_name": "ABI L2+ Aerosol Optical Depth at 550 nm"}),
            ("DQF", dqf_raw, "i1", {"_FillValue": np.int8(-1),
                                    "flag_values": [np.int8(0), np.int8(1), np.int8(2), np.int8(3)],
                                    "flag_meanings": "good_quality_qf medium_quality_qf "
                                                     "low_quality_qf no_retrieval_qf"}),
            ("AE1", ae1_raw, "i2", {"_FillValue": np.int16(-1), "scale_factor": 1.0e-04,
                                    "add_offset": -1.0, "units": "1"}),
            ("AE2", ae2_raw, "i2", {"_FillValue": np.int16(-1), "scale_factor": 1.0e-04,
                                    "add_offset": -1.0, "units": "1"}),
        ):
            fill = attrs.pop("_FillValue")
            v = nc.createVariable(nombre, dtype, ("y", "x"), fill_value=fill, zlib=True)
            v.set_auto_maskandscale(False)
            for k, val in attrs.items():
                v.setncattr(k, val)
            v[:] = np.asarray(datos, dtype=dtype)
        t = nc.createVariable("t", "f8")
        t.setncattr("units", "seconds since 2000-01-01 12:00:00")
        medio = inicio + (fin - inicio) / 2
        t[...] = (medio - goes.J2000).total_seconds()
        tb = nc.createVariable("time_bounds", "f8", ("number_of_time_bounds",))
        tb[:] = [(inicio - goes.J2000).total_seconds(), (fin - goes.J2000).total_seconds()]
        sp = nc.createVariable("nominal_satellite_subpoint_lon", "f4")
        sp[...] = subpoint
        rsza = nc.createVariable("retrieval_solar_zenith_angle", "f4")
        rsza.setncattr("long_name", "threshold solar zenith angle")
        rsza[...] = 80.0
        est = nc.createVariable("aod550_retrievals_attempted_land", "i4")
        est[...] = int(np.count_nonzero(np.asarray(dqf_raw) != 3))


def comunas_sinteticas(carpeta: Path) -> Path:
    import geopandas as gpd
    from shapely.geometry import box

    g = gpd.GeoDataFrame({
        "cod_comuna": [13101, 5101, 0],
        "Comuna": ["Santiago Test", "Valparaiso Test", "Sin demarcar"],
        "Provincia": ["P1", "P2", "P0"],
        "Region": ["R13", "R05", "R00"],
        "geometry": [box(-71.0, -33.6, -70.4, -33.2),
                     box(-71.0, -33.2, -70.4, -32.8),
                     box(-70.4, -33.6, -70.2, -33.4)],
    }, crs="EPSG:4326")
    carpeta.mkdir(parents=True, exist_ok=True)
    path = carpeta / "comunas.shp"
    g.to_file(path)
    return path


def grilla_sintetica(n=24, factor=8):
    """Grilla fija de ``n×n`` celdas alrededor de Santiago, paso 2 km × factor."""
    x_c, y_c = latlon_a_fixed_grid(-33.2, -70.7)
    paso = 56e-6 * factor
    x = x_c + (np.arange(n) - n / 2) * paso
    y = y_c - (np.arange(n) - n / 2) * paso  # y decrece hacia el sur
    return x, y


class GeometriaTests(unittest.TestCase):
    def test_ejemplo_pug(self):
        lat, lon = goes.fixed_grid_a_latlon(-0.024052, 0.095340, PROJ)
        self.assertAlmostEqual(float(lat), 33.846162, places=4)
        self.assertAlmostEqual(float(lon), -84.690932, places=4)

    def test_inversa_coherente(self):
        for lat0, lon0 in ((-33.45, -70.65), (-18.5, -70.3), (-53.2, -70.9), (-27.1, -109.4)):
            x, y = latlon_a_fixed_grid(lat0, lon0)
            lat, lon = goes.fixed_grid_a_latlon(x, y, PROJ)
            self.assertAlmostEqual(float(lat), lat0, places=6)
            self.assertAlmostEqual(float(lon), lon0, places=6)

    def test_fuera_del_disco_es_nan(self):
        lat, lon = goes.fixed_grid_a_latlon(0.3, 0.3, PROJ)
        self.assertTrue(np.isnan(lat) and np.isnan(lon))

    def test_angulo_cenital_satelite(self):
        theta = goes.angulo_cenital_satelite([-33.45, -53.2], [-70.65, -70.9], PROJ, -75.2)
        self.assertAlmostEqual(float(theta[0]), 39.2, delta=0.5)
        self.assertAlmostEqual(float(theta[1]), 60.9, delta=0.5)

    def test_fingerprint_estable_y_sensible(self):
        x, y = grilla_sintetica()
        a = goes.grid_fingerprint(PROJ, x, y)
        self.assertEqual(a, goes.grid_fingerprint(PROJ, x.copy(), y.copy()))
        otro = goes.Proyeccion(**{**PROJ.como_dict(), "longitude_of_projection_origin": -137.0})
        self.assertNotEqual(a, goes.grid_fingerprint(otro, x, y))
        self.assertNotEqual(a, goes.grid_fingerprint(PROJ, x + 1e-6, y))

    def test_subdividir_conserva_area_y_acota_vertices(self):
        import shapely

        # Polígono con agujero y 4.000 vértices, más un multipolígono chico.
        anillo = shapely.Point(-70.5, -33.5).buffer(0.6, quad_segs=1000)
        con_agujero = anillo.difference(shapely.Point(-70.5, -33.5).buffer(0.1, quad_segs=50))
        multi = shapely.multipolygons([shapely.box(-71, -34, -70.9, -33.9).exterior.coords,
                                       shapely.box(-70.2, -34, -70.1, -33.9).exterior.coords])
        piezas, origen = goes.subdividir_poligonos(np.asarray([con_agujero, multi], dtype=object),
                                                   max_vertices=300)
        self.assertGreater(len(piezas), 10)
        self.assertLessEqual(int(shapely.get_num_coordinates(piezas).max()), 300)
        self.assertEqual(set(origen.tolist()), {0, 1})
        for i, g in enumerate((con_agujero, multi)):
            area_piezas = float(np.sum(shapely.area(piezas[origen == i])))
            self.assertAlmostEqual(area_piezas / g.area, 1.0, places=9)
        # Las piezas no se solapan: la unión tiene la misma área que la suma.
        union = shapely.union_all(piezas[origen == 0])
        self.assertAlmostEqual(union.area / con_agujero.area, 1.0, places=9)


class SolTests(unittest.TestCase):
    def test_referencias_solares(self):
        mediodia = datetime(2020, 6, 21, 12, 0, tzinfo=timezone.utc)
        sza = goes.zenit_solar_deg([23.44], [0.0], mediodia)
        self.assertLess(float(sza[0]), 1.5)
        medianoche = datetime(2020, 3, 20, 0, 0, tzinfo=timezone.utc)
        self.assertGreater(float(goes.zenit_solar_deg([0.0], [0.0], medianoche)[0]), 150.0)

    def test_noche_geometrica_chile(self):
        muestra = goes.puntos_muestra_chile(AOIS_TEST)
        noche = goes.sza_minimo_chile(datetime(2020, 6, 21, 6, 0, tzinfo=timezone.utc), muestra)
        dia = goes.sza_minimo_chile(datetime(2020, 6, 21, 16, 0, tzinfo=timezone.utc), muestra)
        self.assertGreaterEqual(noche, 92.0)
        self.assertLess(dia, 60.0)
        # Amanecer parcial: Rapa Nui todavía de noche pero el continente iluminado.
        amanecer = goes.sza_minimo_chile(datetime(2020, 6, 21, 12, 0, tzinfo=timezone.utc), muestra)
        self.assertLess(amanecer, 92.0)


class CatalogoS3Tests(unittest.TestCase):
    def test_parsear_nombre(self):
        key = "ABI-L2-AODF/2019/150/15/OR_ABI-L2-AODF-M6_G16_s20191501500204_e20191501509512_c20191501511409.nc"
        e = goes.parsear_nombre(key, "noaa-goes16", 12345, '"abc"')
        self.assertEqual(e.satelite, "G16")
        self.assertEqual(e.modo, "M6")
        self.assertEqual(e.inicio, datetime(2019, 5, 30, 15, 0, 20, 400000, tzinfo=timezone.utc))
        self.assertEqual(e.fin, datetime(2019, 5, 30, 15, 9, 51, 200000, tzinfo=timezone.utc))
        self.assertEqual(e.etag, "abc")
        self.assertEqual(e.scan_id, int(round((e.inicio - goes.J2000).total_seconds())))
        self.assertIsNone(goes.parsear_nombre("ABI-L2-AODF/2019/150/15/otro.nc", "b", 1, None))

    def _escaneo(self, hh, mm, creacion="20191501511409", modo=6):
        key = (f"ABI-L2-AODF/2019/150/{hh:02d}/OR_ABI-L2-AODF-M{modo}_G16_s2019150{hh:02d}{mm:02d}000"
               f"_e2019150{hh:02d}{mm + 9:02d}000_c{creacion}.nc")
        return goes.parsear_nombre(key, "noaa-goes16", 100, None)

    def test_dedup_y_cadencia_y_huecos(self):
        a = self._escaneo(15, 0, "20191501511409")
        b = self._escaneo(15, 0, "20191601511409")  # reprocesado, creación posterior
        c = self._escaneo(15, 10)
        d = self._escaneo(15, 30)
        unicos, descartados = goes.deduplicar_escaneos([a, b, c, d])
        self.assertEqual([e.key for e in unicos], [b.key, c.key, d.key])
        self.assertEqual(descartados[0]["key"], a.key)
        horaria, omitidos = goes.seleccionar_cadencia(unicos, "horaria")
        self.assertEqual([e.key for e in horaria], [b.key])
        self.assertEqual(len(omitidos), 2)
        media, _ = goes.seleccionar_cadencia(unicos, "30min")
        self.assertEqual([e.key for e in media], [b.key, d.key])
        huecos = goes.huecos_esperados(unicos, date(2019, 5, 30))
        self.assertEqual(len(huecos), 144 - 3)
        self.assertIn("2019-05-30T15:20:00+00:00", huecos)

    def test_satelite_para(self):
        self.assertEqual(goes.satelite_para(date(2025, 4, 6), "auto"), "G16")
        self.assertEqual(goes.satelite_para(date(2025, 4, 7), "auto"), "G19")
        self.assertEqual(goes.satelite_para(date(2019, 1, 1), "G19"), "G19")


class _ManifiestoMemoria:
    def __init__(self):
        self.eventos: list[dict] = []
        self.execution_id = "prueba"

    def registrar(self, datos: dict) -> None:
        self.eventos.append(datos)

    def terminar(self, estado="completo", **extra) -> None:
        self.eventos.append({"evento": "fin", "estado": estado, **extra})


class RecorteSinteticoTests(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory(prefix="goes-abi-recorte-")
        self.addCleanup(temporal.cleanup)
        self.raiz = Path(temporal.name)
        self.comunas = comunas_sinteticas(self.raiz / "mascara")
        self.base = self.raiz / "GOES_ABI_AOD"
        self.base.mkdir()
        self.x, self.y = grilla_sintetica()
        n = self.x.size
        rng = np.random.default_rng(7)
        self.aod_raw = rng.integers(0, 20000, size=(n, n)).astype("int16")
        self.dqf_raw = rng.integers(0, 3, size=(n, n)).astype("int8")
        # Sin recuperación en una franja: AOD fill y DQF=3.
        self.aod_raw[:, :5] = -1
        self.dqf_raw[:, :5] = 3
        self.ae1_raw = rng.integers(0, 30000, size=(n, n)).astype("int16")
        self.ae2_raw = rng.integers(0, 30000, size=(n, n)).astype("int16")
        self.ae2_raw[3, :] = -1
        self.inicio = datetime(2020, 1, 15, 15, 0, tzinfo=timezone.utc)
        self.fin = self.inicio + timedelta(minutes=9, seconds=51)
        self.src = self.raiz / "OR_ABI-L2-AODF-M6_G16_s20200151500000_e20200151509510_c20200151511000.nc"
        escribir_abi_sintetico(self.src, self.x, self.y, self.aod_raw, self.dqf_raw,
                               self.ae1_raw, self.ae2_raw, self.inicio, self.fin)
        self.escaneo = goes.parsear_nombre(
            f"ABI-L2-AODF/2020/015/15/{self.src.name}", "noaa-goes16",
            self.src.stat().st_size, None)
        self.mani = _ManifiestoMemoria()
        self.patch_data = patch.object(goes, "DATA", self.raiz / "data_inexistente")
        self.patch_data.start()
        self.addCleanup(self.patch_data.stop)
        self.catalogos = goes.CatalogoPixeles(self.base, self.comunas, AOIS_TEST, "m" * 64,
                                              self.mani, enlaces=True)
        self.muestra = goes.puntos_muestra_chile(AOIS_TEST)

    def test_catalogo_selecciona_huellas_que_tocan_comunas(self):
        import shapely

        comunas = goes._cargar_comunas(self.comunas)
        cat = goes.construir_catalogo(PROJ, self.x, self.y, comunas, AOIS_TEST,
                                      grid_id="test", subpoint_lon=-75.2)
        self.assertGreater(len(cat), 20)
        union = shapely.union_all(comunas.geometry.to_numpy())
        huellas = goes._huellas_catalogo(cat)
        self.assertTrue(all(h.intersects(union) for h in huellas))
        # Todas las celdas de la grilla que tocan la unión están en el catálogo.
        n = self.x.size
        dx = float(np.median(np.diff(self.x)))
        dy = abs(float(np.median(np.diff(self.y))))
        esperados = set()
        for iy in range(n):
            for ix in range(n):
                xc, yc = self.x[ix], self.y[iy]
                pts = []
                for sx, sy in ((-0.5, 0.5), (0.5, 0.5), (0.5, -0.5), (-0.5, -0.5)):
                    la, lo = goes.fixed_grid_a_latlon(xc + sx * dx, yc + sy * dy, PROJ)
                    pts.append((float(lo), float(la)))
                if shapely.Polygon(pts).intersects(union):
                    esperados.add(iy * n + ix)
        self.assertEqual(set(cat["pixel_id"].tolist()), esperados)
        # cod_comuna por centro: 0 conservado, -1 sólo huella.
        centros = shapely.points(cat["lon"].to_numpy(), cat["lat"].to_numpy())
        for cod, centro in zip(cat["cod_comuna"], centros, strict=True):
            dentro = [int(c) for g, c in zip(comunas.geometry, comunas.cod_comuna, strict=True)
                      if g.intersects(centro)]
            if not dentro:
                self.assertEqual(cod, -1)
            else:
                self.assertIn(cod, dentro)
        self.assertIn(0, set(cat["cod_comuna"]))
        self.assertIn(-1, set(cat["cod_comuna"]))
        self.assertTrue((cat["aoi_id"] == "continente").all())
        self.assertTrue(cat["angulo_cenital_satelite_deg"].between(38, 41).all())

    def test_recorte_conserva_empaquetado_y_descarta_fill(self):
        filas, resumen = goes.recortar_escaneo(self.src, self.escaneo, self.catalogos, self.muestra)
        cat = self.catalogos.obtener(PROJ, self.x, self.y, -75.2)
        n = self.x.size
        self.assertEqual(resumen["n_pixeles_chile"], len(cat["df"]))
        iy = cat["df"]["y_index"].to_numpy()
        ix = cat["df"]["x_index"].to_numpy()
        con_dato = self.aod_raw[iy, ix] != -1
        self.assertEqual(resumen["n_recuperados"], int(con_dato.sum()))
        self.assertEqual(len(filas), int(con_dato.sum()))
        self.assertEqual(resumen["n_dqf_3"], int((self.dqf_raw[iy, ix] == 3).sum()))
        self.assertTrue((filas["scan_id"] == self.escaneo.scan_id).all())
        esperado_i16 = self.aod_raw[iy, ix][con_dato]
        np.testing.assert_array_equal(filas["aod_i16"].to_numpy(), esperado_i16)
        np.testing.assert_allclose(filas["aod"].to_numpy(),
                                   esperado_i16.astype("float64") * 7.706e-05 - 0.05, rtol=1e-6)
        fila_ae2_fill = filas[filas["ae2_i16"] == -1]
        self.assertTrue(fila_ae2_fill["ae2"].isna().all())
        self.assertEqual(filas["dqf"].dtype, np.dtype("int8"))
        self.assertEqual(resumen["t_medio_utc"], (self.inicio + (self.fin - self.inicio) / 2).isoformat())
        self.assertEqual(resumen["atributos_variables"]["AOD"]["scale_factor"], 7.706e-05)
        self.assertEqual(resumen["atributos_globales"]["platform_ID"], "G16")
        self.assertIn("retrieval_solar_zenith_angle", resumen["variables_escalares"])
        self.assertLess(resumen["sza_min_chile_deg"], 90.0)
        # Catálogo publicado y reutilizable con validación de hash.
        carpeta = self.base / "catalogo_pixeles" / f"grid={cat['grid_id']}"
        self.assertTrue((carpeta / "pixeles.parquet").exists())
        meta = json.loads((carpeta / "metadata.json").read_text())
        self.assertEqual(meta["pixeles"], len(cat["df"]))
        self.assertTrue((carpeta / "enlaces_geoespaciales" / "pixel_comuna.parquet").exists())
        enlaces = pd.read_parquet(carpeta / "enlaces_geoespaciales" / "pixel_comuna.parquet")
        self.assertTrue(enlaces["fraccion_celda"].between(0, 1.000001).all())
        self.assertEqual(set(enlaces["cod_comuna"]), {13101, 5101, 0})
        otro = goes.CatalogoPixeles(self.base, self.comunas, AOIS_TEST, "m" * 64, self.mani)
        self.assertEqual(len(otro.obtener(PROJ, self.x, self.y, -75.2)["df"]), len(cat["df"]))
        self.assertEqual(n, 24)
        # Sin --enlaces el catálogo se publica igual y no se calculan enlaces.
        base2 = self.raiz / "sin_enlaces"
        base2.mkdir()
        sin = goes.CatalogoPixeles(base2, self.comunas, AOIS_TEST, "m" * 64, self.mani)
        entrada = sin.obtener(PROJ, self.x, self.y, -75.2)
        self.assertIsNone(entrada["enlaces"])
        self.assertFalse((base2 / "catalogo_pixeles" / f"grid={cat['grid_id']}"
                          / "enlaces_geoespaciales").exists())

    def test_rechaza_grilla_no_goes_east(self):
        otro = self.raiz / "OR_ABI-L2-AODF-M6_G17_s20200151500000_e20200151509510_c20200151511000.nc"
        escribir_abi_sintetico(otro, self.x, self.y, self.aod_raw, self.dqf_raw,
                               self.ae1_raw, self.ae2_raw, self.inicio, self.fin, lon_origen=-137.0)
        with self.assertRaises(goes.GrillaInesperada):
            goes.recortar_escaneo(otro, self.escaneo, self.catalogos, self.muestra)

    def test_rechaza_tiempo_incoherente(self):
        e = goes.parsear_nombre(
            "ABI-L2-AODF/2020/015/15/OR_ABI-L2-AODF-M6_G16_s20200151510000_e20200151519510_c20200151521000.nc",
            "noaa-goes16", 1, None)
        with self.assertRaises(ValueError):
            goes.recortar_escaneo(self.src, e, self.catalogos, self.muestra)


class DiaTransaccionalTests(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory(prefix="goes-abi-dia-")
        self.addCleanup(temporal.cleanup)
        self.raiz = Path(temporal.name)
        self.comunas = comunas_sinteticas(self.raiz / "mascara")
        self.base = self.raiz / "GOES_ABI_AOD"
        self.base.mkdir()
        self.fuentes = self.raiz / "fuentes"
        self.fuentes.mkdir()
        self.x, self.y = grilla_sintetica()
        n = self.x.size
        rng = np.random.default_rng(3)
        self.fecha = date(2020, 1, 15)
        self.escaneos = []
        # 15:00 y 15:10 UTC (día), 06:00 UTC (noche geométrica en todo Chile).
        for hh, mm in ((15, 0), (15, 10), (6, 0)):
            inicio = datetime(2020, 1, 15, hh, mm, tzinfo=timezone.utc)
            fin = inicio + timedelta(minutes=9, seconds=51)
            nombre = (f"OR_ABI-L2-AODF-M6_G16_s2020015{hh:02d}{mm:02d}000_e2020015{hh:02d}{mm + 9:02d}510"
                      f"_c2020015{hh:02d}{mm + 11:02d}000.nc")
            aod = rng.integers(0, 20000, size=(n, n)).astype("int16")
            aod[:, :4] = -1
            dqf = rng.integers(0, 3, size=(n, n)).astype("int8")
            dqf[:, :4] = 3
            escribir_abi_sintetico(self.fuentes / nombre, self.x, self.y, aod, dqf,
                                   rng.integers(0, 30000, size=(n, n)).astype("int16"),
                                   rng.integers(0, 30000, size=(n, n)).astype("int16"), inicio, fin)
            self.escaneos.append(goes.parsear_nombre(
                f"ABI-L2-AODF/2020/015/{hh:02d}/{nombre}", "noaa-goes16",
                (self.fuentes / nombre).stat().st_size, '"etag"'))
        self.mani = _ManifiestoMemoria()
        self.mani_csv = goes.ManifiestoCSV(self.base / "manifest_escaneos.csv")
        self.patch_data = patch.object(goes, "DATA", self.raiz / "data_inexistente")
        self.patch_data.start()
        self.addCleanup(self.patch_data.stop)
        self.catalogos = goes.CatalogoPixeles(self.base, self.comunas, AOIS_TEST, "m" * 64, self.mani)
        self.muestra = goes.puntos_muestra_chile(AOIS_TEST)
        self.descargas: list[str] = []

    def _cfg(self, **cambios):
        base = dict(base=self.base, staging=self.base / "_staging", comunas=self.comunas,
                    mascara_sha="m" * 64, aois=AOIS_TEST, cadencia="nativa", omitir_noche=True,
                    sza_max=90.0, trabajadores=2, reserva_gib=0.0, staging_gib=1.0,
                    cuota_productos_gib=10.0, max_escaneos_por_dia=0, limite_mbps=None,
                    execution_id="prueba", satelite="auto")
        base.update(cambios)
        return goes.Configuracion(**base)

    def _descargar(self, s3, escaneo, destino, limite):
        self.descargas.append(escaneo.key)
        shutil.copyfile(self.fuentes / escaneo.nombre, destino)
        return destino

    def test_dia_publica_y_retira_crudos(self):
        cfg = self._cfg()
        with patch.object(goes, "listar_escaneos", return_value=list(self.escaneos)), \
                patch.object(goes, "descargar_objeto", side_effect=self._descargar):
            estado = goes.procesar_dia(None, self.fecha, cfg, self.catalogos, self.mani,
                                       self.mani_csv, self.muestra)
        self.assertEqual(estado, "ok")
        self.assertEqual(len(self.descargas), 2)  # la noche no se descarga
        rutas = goes.rutas_dia(self.base, self.fecha)
        obs = pd.read_parquet(rutas["obs"])
        esc = pd.read_parquet(rutas["escaneos"])
        self.assertEqual(list(obs.columns), list(goes.COLUMNAS_OBS))
        self.assertEqual(list(esc.columns), list(goes.COLUMNAS_ESCANEOS))
        self.assertEqual(len(esc), 2)
        self.assertEqual(obs["scan_id"].nunique(), 2)
        self.assertEqual(int(esc["n_recuperados"].sum()), len(obs))
        self.assertTrue(esc["sha256_fuente"].str.len().eq(64).all())
        self.assertEqual(str(esc["inicio_utc"].dtype), "datetime64[ms, UTC]")
        manifiesto = json.loads(rutas["manifiesto"].read_text())
        self.assertEqual(manifiesto["estado"], "ok")
        self.assertEqual(len(manifiesto["escaneos_procesados"]), 2)
        omitidos = {o["estado"] for o in manifiesto["escaneos_omitidos"]}
        self.assertEqual(omitidos, {"omitido_noche_geometrica"})
        self.assertEqual(manifiesto["escaneos_procesados"][0]["metadatos"], "completos")
        self.assertIn("time_coverage_start",
                      manifiesto["escaneos_procesados"][1]["atributos_globales"])
        self.assertNotIn("platform_ID",
                         manifiesto["escaneos_procesados"][1]["atributos_globales"])
        self.assertEqual(manifiesto["salidas"]["observaciones"]["sha256"],
                         goes.sha256(rutas["obs"]))
        self.assertEqual(len(manifiesto["huecos_fuente_esperados"]), 144 - 3)
        eventos = [e["evento"] for e in self.mani.eventos]
        self.assertIn("catalogo_pixeles_publicado", eventos)
        pre = eventos.index("dia_validado_pre_borrado")
        post = eventos.index("crudo_eliminado_post_validacion")
        self.assertLess(pre, post)
        self.assertFalse(list((self.base / "_staging").rglob("*.nc")))
        registro = self.mani_csv.obtener(self.fecha.isoformat(), goes.FLUJO)
        self.assertEqual(registro.estado, "ok")
        self.assertEqual(registro.filas, len(obs))
        self.assertTrue(goes.dia_publicado_valido(self.base, self.fecha, registro, revalidar=True))
        # Una alteración de la salida invalida el día publicado.
        rutas["obs"].write_bytes(rutas["obs"].read_bytes() + b"x")
        self.assertFalse(goes.dia_publicado_valido(self.base, self.fecha, registro, revalidar=False))

    def test_fallo_de_descarga_no_publica_ni_borra(self):
        cfg = self._cfg()

        def fallar(s3, escaneo, destino, limite):
            if escaneo.inicio.minute == 10:
                raise OSError("red sintética")
            return self._descargar(s3, escaneo, destino, limite)

        with patch.object(goes, "listar_escaneos", return_value=list(self.escaneos)), \
                patch.object(goes, "descargar_objeto", side_effect=fallar):
            estado = goes.procesar_dia(None, self.fecha, cfg, self.catalogos, self.mani,
                                       self.mani_csv, self.muestra)
        self.assertEqual(estado, "error")
        rutas = goes.rutas_dia(self.base, self.fecha)
        self.assertFalse(rutas["obs"].exists())
        self.assertFalse(rutas["manifiesto"].exists())
        self.assertEqual(len(list((self.base / "_staging").rglob("*.nc"))), 1)
        self.assertEqual(self.mani_csv.obtener(self.fecha.isoformat(), goes.FLUJO).estado, "error")
        incompleto = [e for e in self.mani.eventos if e["evento"] == "dia_incompleto"][0]
        self.assertEqual(incompleto["fallidos"][0]["estado"], "descarga_fallida")
        self.assertFalse(goes.dia_publicado_valido(
            self.base, self.fecha, self.mani_csv.obtener(self.fecha.isoformat(), goes.FLUJO),
            revalidar=False))

    def test_limite_staging_pausa_sin_borrar(self):
        cfg = self._cfg(staging_gib=1e-9)
        with patch.object(goes, "listar_escaneos", return_value=list(self.escaneos)), \
                patch.object(goes, "descargar_objeto", side_effect=self._descargar), \
                self.assertRaises(goes.LimiteSeguro):
            goes.procesar_dia(None, self.fecha, cfg, self.catalogos, self.mani,
                              self.mani_csv, self.muestra)
        self.assertFalse(goes.rutas_dia(self.base, self.fecha)["manifiesto"].exists())

    def test_dia_sin_fuente(self):
        cfg = self._cfg()
        with patch.object(goes, "listar_escaneos", return_value=[]):
            estado = goes.procesar_dia(None, date(2018, 1, 1), cfg, self.catalogos, self.mani,
                                       self.mani_csv, self.muestra)
        self.assertEqual(estado, "sin_datos")
        registro = self.mani_csv.obtener("2018-01-01", goes.FLUJO)
        self.assertEqual(registro.estado, "sin_datos")
        self.assertTrue(goes.dia_publicado_valido(self.base, date(2018, 1, 1), registro, revalidar=True))
        reciente = date.today() - timedelta(days=1)
        with patch.object(goes, "listar_escaneos", return_value=[]):
            estado = goes.procesar_dia(None, reciente, cfg, self.catalogos, self.mani,
                                       self.mani_csv, self.muestra)
        self.assertEqual(estado, "error")

    def test_cadencia_horaria_y_limite_prueba(self):
        cfg = self._cfg(cadencia="horaria", max_escaneos_por_dia=1)
        with patch.object(goes, "listar_escaneos", return_value=list(self.escaneos)), \
                patch.object(goes, "descargar_objeto", side_effect=self._descargar):
            estado = goes.procesar_dia(None, self.fecha, cfg, self.catalogos, self.mani,
                                       self.mani_csv, self.muestra)
        self.assertEqual(estado, "ok")
        self.assertEqual(self.descargas, [self.escaneos[0].key])
        manifiesto = json.loads(goes.rutas_dia(self.base, self.fecha)["manifiesto"].read_text())
        estados = sorted(o["estado"] for o in manifiesto["escaneos_omitidos"])
        self.assertEqual(estados, ["omitido_cadencia", "omitido_noche_geometrica"])


class ExclusionesYMainTests(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory(prefix="goes-abi-main-")
        self.addCleanup(temporal.cleanup)
        self.raiz = Path(temporal.name)
        self.comunas = comunas_sinteticas(self.raiz / "mascara")
        self.fuentes = self.raiz / "fuentes"
        self.fuentes.mkdir()
        self.x, self.y = grilla_sintetica()
        n = self.x.size
        rng = np.random.default_rng(11)
        self.escaneos = []
        for hh, mm in ((15, 0), (15, 10)):
            inicio = datetime(2020, 1, 15, hh, mm, tzinfo=timezone.utc)
            fin = inicio + timedelta(minutes=9, seconds=51)
            nombre = (f"OR_ABI-L2-AODF-M6_G16_s2020015{hh:02d}{mm:02d}000_e2020015{hh:02d}{mm + 9:02d}510"
                      f"_c2020015{hh:02d}{mm + 11:02d}000.nc")
            aod = rng.integers(0, 20000, size=(n, n)).astype("int16")
            escribir_abi_sintetico(self.fuentes / nombre, self.x, self.y, aod,
                                   rng.integers(0, 3, size=(n, n)).astype("int8"),
                                   rng.integers(0, 30000, size=(n, n)).astype("int16"),
                                   rng.integers(0, 30000, size=(n, n)).astype("int16"), inicio, fin)
            self.escaneos.append(goes.parsear_nombre(
                f"ABI-L2-AODF/2020/015/{hh:02d}/{nombre}", "noaa-goes16",
                (self.fuentes / nombre).stat().st_size, None))
        self.descargas: list[str] = []

    def _descargar(self, s3, escaneo, destino, limite):
        self.descargas.append(escaneo.key)
        shutil.copyfile(self.fuentes / escaneo.nombre, destino)
        return destino

    def test_exclusiones_manuales(self):
        base = self.raiz / "GOES_ABI_AOD"
        base.mkdir()
        (base / "_control").mkdir()
        (base / "_control" / "exclusiones.json").write_text(json.dumps(
            {self.escaneos[1].key: "fuente corrupta verificada a mano"}), encoding="utf-8")
        with self.assertRaises(ValueError):
            goes.cargar_exclusiones(self._json(base, {"k": ""}))
        exclusiones = goes.cargar_exclusiones(base / "_control" / "exclusiones.json")
        cfg = goes.Configuracion(
            base=base, staging=base / "_staging", comunas=self.comunas, mascara_sha="m" * 64,
            aois=AOIS_TEST, cadencia="nativa", omitir_noche=True, sza_max=90.0, trabajadores=1,
            reserva_gib=0.0, staging_gib=1.0, cuota_productos_gib=10.0, max_escaneos_por_dia=0,
            limite_mbps=None, execution_id="prueba", satelite="auto", exclusiones=exclusiones)
        mani = _ManifiestoMemoria()
        with patch.object(goes, "DATA", self.raiz / "nada"), \
                patch.object(goes, "listar_escaneos", return_value=list(self.escaneos)), \
                patch.object(goes, "descargar_objeto", side_effect=self._descargar):
            catalogos = goes.CatalogoPixeles(base, self.comunas, AOIS_TEST, "m" * 64, mani)
            estado = goes.procesar_dia(None, date(2020, 1, 15), cfg, catalogos, mani,
                                       goes.ManifiestoCSV(base / "manifest_escaneos.csv"),
                                       goes.puntos_muestra_chile(AOIS_TEST))
        self.assertEqual(estado, "ok")
        self.assertEqual(self.descargas, [self.escaneos[0].key])
        manifiesto = json.loads(goes.rutas_dia(base, date(2020, 1, 15))["manifiesto"].read_text())
        self.assertEqual(manifiesto["escaneos_omitidos"][0]["estado"], "omitido_por_exclusion_manual")
        self.assertEqual(manifiesto["escaneos_omitidos"][0]["motivo"], "fuente corrupta verificada a mano")

    def _json(self, base, datos):
        p = base / "_control" / "otro.json"
        p.write_text(json.dumps(datos), encoding="utf-8")
        return p

    def test_main_publica_reanuda_y_omite_dias_validados(self):
        raiz_datos = self.raiz / "data"
        (raiz_datos / "contaminantes").mkdir(parents=True)
        shutil.copy(self.comunas, raiz_datos / "comunas.shp")
        for ext in (".shx", ".dbf", ".prj", ".cpg"):
            origen = self.comunas.with_suffix(ext)
            if origen.exists():
                shutil.copy(origen, raiz_datos / f"comunas{ext}")
        args = ["--desde", "2020-01-15", "--hasta", "2020-01-16", "--reserva-gib", "0",
                "--comunas", str(raiz_datos / "comunas.shp"), "--volume-uuid", ""]

        def listar(s3, fecha, satelite):
            return list(self.escaneos) if fecha == date(2020, 1, 15) else []

        with patch.object(goes, "DATA", raiz_datos), \
                patch.object(goes, "CONTAMINANTES", raiz_datos / "contaminantes"), \
                patch.object(goes, "seleccionar", return_value=AOIS_TEST), \
                patch.object(goes, "cliente_s3", return_value=object()), \
                patch.object(goes, "listar_escaneos", side_effect=listar), \
                patch.object(goes, "descargar_objeto", side_effect=self._descargar):
            self.assertEqual(goes.main(args), 0)
            base = raiz_datos / "contaminantes" / goes.PRODUCTO
            self.assertTrue(goes.rutas_dia(base, date(2020, 1, 15))["obs"].exists())
            self.assertEqual(len(self.descargas), 2)
            csv = goes.ManifiestoCSV(base / "manifest_escaneos.csv")
            self.assertEqual(csv.obtener("2020-01-15", goes.FLUJO).estado, "ok")
            self.assertEqual(csv.obtener("2020-01-16", goes.FLUJO).estado, "sin_datos")
            avance = json.loads((base / "_control" / "avance.json").read_text())
            self.assertEqual(avance["conteos"], {"ok": 1, "sin_datos": 1, "error": 0, "omitidos": 0})
            # Segunda corrida: nada se vuelve a descargar.
            self.assertEqual(goes.main(args), 0)
            self.assertEqual(len(self.descargas), 2)
            avance = json.loads((base / "_control" / "avance.json").read_text())
            self.assertEqual(avance["conteos"]["omitidos"], 2)
            # Cuota de productos alcanzada: pausa con código 75 sin borrar nada.
            csv.marcar("2020-01-15", goes.FLUJO, "error", 0, "")
            self.assertEqual(goes.main(args + ["--cuota-productos-gib", "0"]), 75)
            self.assertTrue(goes.rutas_dia(base, date(2020, 1, 15))["obs"].exists())
            eventos = [json.loads(l)["evento"] for p in (base / "_manifiestos").glob("*.jsonl")
                       for l in p.read_text().splitlines()]
            self.assertIn("pausado_limite_seguro", eventos)


class DiferenciasTests(unittest.TestCase):
    def test_diferencias(self):
        ref = {"a": 1, "b": {"x": 1}, "c": 3}
        act = {"a": 1, "b": {"x": 2}, "d": 4}
        self.assertEqual(goes.diferencias(ref, act), {"b": {"x": 2}, "d": 4, "__ausentes__": ["c"]})


if __name__ == "__main__":
    unittest.main()
