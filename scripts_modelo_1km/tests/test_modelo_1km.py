from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

_RAIZ_TEST = tempfile.mkdtemp(prefix="modelo1km-root-")
os.environ.setdefault("AIR_POLLUTION_DATA_ROOT", _RAIZ_TEST)
os.environ.setdefault("AIR_POLLUTION_DERIVED_ROOT", str(Path(_RAIZ_TEST) / "derived"))
os.environ.setdefault("AIR_POLLUTION_MODELO_1KM_ROOT", str(Path(_RAIZ_TEST) / "local" / "modelado_1km"))

AQUI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AQUI))

import _comun_modelo as cm  # noqa: E402
import _features as ft  # noqa: E402
import covariables_estaticas as ce  # noqa: E402
import verificar_reloj_sinca as vr  # noqa: E402


class TiempoTests(unittest.TestCase):
    def test_etiqueta_fin_de_intervalo_utc_menos_4(self):
        ts = pd.Series(pd.to_datetime(["2024-04-18 18:00", "2024-04-18 00:00"]))
        bins = cm.sinca_local_a_bin_utc(ts)
        # 18:00 local = intervalo 17:01–18:00 → bin 17:00 local → 21:00 UTC
        self.assertEqual(bins.iloc[0], pd.Timestamp("2024-04-18 21:00"))
        self.assertEqual(bins.iloc[1], pd.Timestamp("2024-04-18 03:00"))
        self.assertEqual(cm.bin_utc_a_local(bins).iloc[0], pd.Timestamp("2024-04-18 17:00"))

    def test_fechas_y_meses(self):
        self.assertEqual(len(cm.fechas("2024-02-27", "2024-03-02")), 5)
        self.assertEqual(cm.meses("2024-02-27", "2024-03-02"), ["202402", "202403"])


class MesNativoTests(unittest.TestCase):
    def test_indices_y_extraccion(self):
        tiempos = np.arange("2024-04-01T00:00", "2024-04-01T06:00", dtype="datetime64[h]").astype("datetime64[ns]")
        pixel = np.array([30, 10, 20], dtype="int64")
        datos = {"t2m": np.arange(18, dtype="float32").reshape(6, 3)}
        m = cm.MesNativo("x", tiempos, pixel, datos)
        it = m.indice_tiempo(np.array(["2024-04-01T02:30", "2024-03-31T23:00", "2024-04-01T05:59"], dtype="datetime64[ns]"))
        np.testing.assert_array_equal(it, [2, -1, 5])
        ip = m.indice_pixel(np.array([10, 20, 99]))
        np.testing.assert_array_equal(ip, [1, 2, -1])
        v = m.extraer("t2m", it, ip)
        self.assertEqual(v[0], datos["t2m"][2, 1])
        self.assertTrue(np.isnan(v[1]) and np.isnan(v[2]))
        # Paso de 3 h (CAMS): 04:00 cae en el bin 03:00 → índice 1 si los tiempos van cada 3 h
        m3 = cm.MesNativo("cams", tiempos[::3], pixel, {"no2": np.zeros((2, 3), "float32")})
        np.testing.assert_array_equal(m3.indice_tiempo(np.array(["2024-04-01T04:00"], dtype="datetime64[ns]"), 3), [1])


class VersionSincaTests(unittest.TestCase):
    def test_elige_ventana_mas_amplia_no_el_hash_mayor(self):
        import json

        with tempfile.TemporaryDirectory() as d:
            carpeta = Path(d) / "estacion=117" / "contaminante=pm25"
            # Hash "f..." (ordena último) con ventana corta; "8..." con la serie completa.
            for sha, since, until, filas in (("f36963", "2026-09-01", "2026-09-13", 312),
                                             ("80ba98", "2000-01-01", "2026-09-13", 234071)):
                v = carpeta / f"version={sha}"
                v.mkdir(parents=True)
                pd.DataFrame({"ts_local": pd.to_datetime(["2024-01-01"] * 2), "obs": [1.0, 2.0]}).to_parquet(
                    v / "observaciones.parquet", index=False)
                (v / "manifest.json").write_text(json.dumps({
                    "created_utc": "2026-09-15T17:56:39+00:00", "inputs": {"since": since, "until": until},
                    "files": [{"name": "observaciones.parquet", "rows": filas}]}), encoding="utf-8")
            self.assertEqual(cm.version_sinca(carpeta).parent.name, "version=80ba98")
            # Sin manifiestos: gana la de más filas.
            for v in carpeta.glob("version=*/manifest.json"):
                v.unlink()
            pd.DataFrame({"ts_local": pd.to_datetime(["2024-01-01"] * 5), "obs": [1.0] * 5}).to_parquet(
                carpeta / "version=f36963" / "observaciones.parquet", index=False)
            self.assertEqual(cm.version_sinca(carpeta).parent.name, "version=f36963")
            self.assertIsNone(cm.version_sinca(Path(d) / "no_existe"))


class MaiacTests(unittest.TestCase):
    def test_decodificacion_qa(self):
        q = cm.decodificar_qa_maiac(np.array([1, 1793, 1057, 0b0001_0000_0000_0001], dtype="uint16"))
        np.testing.assert_array_equal(q["nube"], [1, 1, 1, 1])
        np.testing.assert_array_equal(q["qa_aod"], [0, 7, 4, 0])
        np.testing.assert_array_equal(q["adyacencia"], [0, 0, 1, 0])
        np.testing.assert_array_equal(q["glint"], [0, 0, 0, 1])


class ClaveCeldaTests(unittest.TestCase):
    def test_pixeles_300m_caen_en_su_celda(self):
        lat_c, lon_c = -33.465, -70.665
        k = ce.clave_celda(np.array([lat_c]), np.array([lon_c]))[0]
        dentro = ce.clave_celda(np.array([lat_c + 0.004, lat_c - 0.0049]), np.array([lon_c - 0.0049, lon_c + 0.004]))
        fuera = ce.clave_celda(np.array([lat_c + 0.006]), np.array([lon_c]))
        self.assertTrue((dentro == k).all())
        self.assertNotEqual(fuera[0], k)


class VecinasTests(unittest.TestCase):
    def test_idw_excluye_la_propia_estacion(self):
        ts = pd.to_datetime(["2024-04-18 15:00", "2024-04-18 16:00"])
        O = pd.DataFrame({"A": [10.0, 20.0], "B": [30.0, np.nan]}, index=ts)
        lat_e, lon_e = np.array([-33.4, -33.5]), np.array([-70.6, -70.7])
        v, w = ft.obs_vecinas_para(O, lat_e, lon_e, ts.to_numpy(), lat_e, lon_e, excluir=np.array(["A", "B"]))
        self.assertAlmostEqual(float(v[0]), 30.0)   # A a las 15: sólo B
        self.assertAlmostEqual(float(v[1]), 20.0)   # B a las 16: sólo A (B excluida y sin dato)
        v2, w2 = ft.obs_vecinas_para(O, lat_e, lon_e, ts.to_numpy(), lat_e, lon_e)
        self.assertGreater(float(w2[0]), float(w[0]))
        # hora sin observaciones en la tabla → NaN y peso 0
        v3, w3 = ft.obs_vecinas_para(O, lat_e, lon_e, np.array(["2024-04-18T17:00"], dtype="datetime64[ns]"),
                                     np.array([-33.4]), np.array([-70.6]))
        self.assertTrue(np.isnan(v3[0]) and w3[0] == 0)

    def test_vecindario_fijo_da_lo_mismo_que_recalcular(self):
        """La producción precalcula la matriz de pesos; tiene que dar exactamente lo mismo."""
        rng = np.random.default_rng(7)
        ts = pd.date_range("2024-04-18 00:00", periods=6, freq="h")
        cols = [f"E{k}" for k in range(5)]
        val = rng.uniform(0, 80, (len(ts), len(cols)))
        val[rng.random(val.shape) < 0.3] = np.nan          # estaciones sin dato en algunas horas
        O = pd.DataFrame(val, index=ts, columns=cols)
        lat_e, lon_e = rng.uniform(-40, -30, len(cols)), rng.uniform(-73, -70, len(cols))
        lat_q, lon_q = rng.uniform(-40, -30, 500), rng.uniform(-73, -70, 500)
        vf = ft.VecindarioFijo(O, lat_e, lon_e, lat_q, lon_q)
        for t in list(ts) + [pd.Timestamp("2024-04-18 23:00")]:   # la última no está en la tabla
            esperado = ft.obs_vecinas_para(O, lat_e, lon_e, np.full(len(lat_q), np.datetime64(t, "ns")),
                                           lat_q, lon_q)
            obtenido = vf.para(np.datetime64(t, "ns"))
            for a, b in zip(esperado, obtenido):
                np.testing.assert_array_equal(np.nan_to_num(a, nan=-1), np.nan_to_num(b, nan=-1))


class OrdenSatelitalTests(unittest.TestCase):
    """La ventana móvil satelital exige orden cronológico; quien salte de año tiene que reiniciarla."""

    def _stub(self):
        celdas = pd.DataFrame({"celda": [1, 2], "lat": [-33.4, -36.8], "lon": [-70.6, -73.0]})
        enl = pd.DataFrame({"celda": [1, 2], "maiac_pixel": [10, 20]})
        s = ft.SatelitesDiarios(celdas, enl)
        s._maiac = lambda f: {"aod_terra": np.full(2, np.nan, "float32"), "aod_aqua": np.full(2, np.nan, "float32"),
                              "aod_dia": np.full(2, 0.1, "float32"), "aod_n": np.ones(2, "float32")}
        s._no2 = lambda f: {"no2_trop": np.full(2, 1.0, "float32"), "no2_trop_prec": np.full(2, 0.1, "float32"),
                            "no2_trop_hora": np.full(2, 13.0, "float32")}
        return s

    def test_un_dia_anterior_al_ultimo_falla(self):
        s = self._stub()
        for d in range(1, 6):
            s.dia(date(2000, 1, d))
        s.dia(date(2012, 1, 1))                      # hacia adelante no molesta: _ventana filtra por fecha
        with self.assertRaises(ValueError):
            s.dia(date(2003, 12, 17))                # hacia atrás, en cambio, aborta

    def test_calentar_una_instancia_nueva_da_la_misma_ventana(self):
        cronologico = self._stub()
        for k in range(20, -1, -1):
            t_cron = cronologico.dia(date.fromordinal(date(2003, 1, 1).toordinal() - k))
        reiniciado = self._stub()                    # lo que hace producir_serie.py al cambiar de año
        for k in range(15, 0, -1):
            reiniciado.dia(date.fromordinal(date(2003, 1, 1).toordinal() - k))
        t_nuevo = reiniciado.dia(date(2003, 1, 1))
        for col in ("aod_3d", "aod_7d", "no2_trop_7d", "no2_trop_15d"):
            np.testing.assert_array_equal(t_cron[col].to_numpy(), t_nuevo[col].to_numpy())

    def test_el_lanzador_reinicia_la_ventana_antes_de_cada_anio(self):
        lanzador = (AQUI / "producir_serie.py").read_text(encoding="utf-8")
        produccion = (AQUI / "produccion.py").read_text(encoding="utf-8")
        self.assertIn("def reiniciar_ventana_satelital", produccion)
        self.assertIn("ctx.reiniciar_ventana_satelital()", lanzador)


class EnlaceValidoTests(unittest.TestCase):
    """Una celda costera cuyo píxel propio es mar debe enlazarse al píxel de tierra más cercano."""

    def setUp(self):
        import construir_grilla as cg
        self.cg = cg
        # Tres píxeles de 0,1° en fila: mar (10), tierra (11), tierra (12).
        self.cat = pd.DataFrame({"pixel_id": [10, 11, 12], "lat": [-33.0, -33.0, -33.0], "lon": [-71.7, -71.6, -71.5]})
        self.lat = np.array([-33.0, -33.0, -33.0, -33.0])
        self.lon = np.array([-71.71, -71.61, -71.49, -72.5])        # sobre el mar, tierra, tierra, muy lejos

    def test_cae_al_vecino_valido_y_lo_marca(self):
        pid, d, tipo = self.cg.enlazar_pixel_valido(self.lat, self.lon, self.cat, np.array([11, 12]), 9.0, 16.0)
        self.assertEqual(pid.tolist(), [11, 11, 12, -1])
        self.assertEqual(tipo.tolist(), ["vecino_valido", "propio", "propio", "sin_enlace"])
        self.assertTrue(9.0 < float(d[0]) < 11.0)                   # ~10,3 km hasta el píxel de tierra

    def test_radio_del_vecino_se_respeta(self):
        pid, _, tipo = self.cg.enlazar_pixel_valido(self.lat, self.lon, self.cat, np.array([12]), 9.0, 16.0)
        # el único válido (12) queda a ~19,6 km del primer punto (fuera del radio) y a ~10,3 km del segundo
        self.assertEqual(pid.tolist(), [-1, 12, 12, -1])
        self.assertEqual(tipo.tolist(), ["sin_enlace", "vecino_valido", "propio", "sin_enlace"])

    def test_sin_mascara_es_el_mas_cercano(self):
        pid, _, tipo = self.cg.enlazar_pixel_valido(self.lat, self.lon, self.cat, None, 9.0, 16.0)
        self.assertEqual(pid.tolist(), [10, 11, 12, -1])
        self.assertEqual(set(tipo.tolist()), {"propio", "sin_enlace"})


class DescriptivoFuentesTests(unittest.TestCase):
    def setUp(self):
        import descriptivo_fuentes as dfu
        self.dfu = dfu

    def test_pesos_por_zona_son_celdas_cubiertas(self):
        # 5 celdas: tres del norte grande (0) en el píxel 10, una del centro (2) en el 20, una insular (6) en el 30.
        pesos = self.dfu.Pesos(np.array([10, 10, 10, 20, 30]), np.array([0, 0, 0, 2, 6]), np.zeros(5))   # lat 0 → cos = 1
        W = pesos.matriz(np.array([30, 20, 10]))                      # orden arbitrario de píxeles
        zonas = list(self.dfu.ZONAS)
        self.assertEqual(W[zonas.index("norte_grande")].tolist(), [0.0, 0.0, 3.0])
        self.assertEqual(W[zonas.index("centro")].tolist(), [0.0, 1.0, 0.0])
        self.assertEqual(W[zonas.index("Chile")].tolist(), [0.0, 1.0, 3.0])      # lo insular no entra en Chile continental

    def test_pesos_son_area_no_conteo(self):
        # Dos celdas en el píxel 10: una en el ecuador y otra a 60° S pesan 1 + 0,5, no 2.
        W = self.dfu.Pesos(np.array([10, 10]), np.array([4, 4]), np.array([0.0, -60.0])).matriz(np.array([10]))
        self.assertAlmostEqual(float(W[list(self.dfu.ZONAS).index("austral"), 0]), 1.5, places=6)

    def test_media_por_zona_pondera_por_area_e_ignora_nan(self):
        W = np.array([[1.0, 3.0], [0.0, 3.0]])
        X = np.array([[10.0, 20.0], [np.nan, 20.0], [np.nan, np.nan]])
        m = self.dfu.media_por_zona(X, W)
        self.assertAlmostEqual(m[0, 0], 17.5)                           # (1·10 + 3·20) / 4
        self.assertAlmostEqual(m[1, 0], 20.0)                           # el NaN no pesa
        self.assertTrue(np.isnan(m[2]).all())

    def test_bin_tropomi_y_anios(self):
        b = self.dfu._bin_tropomi([-33.45, -33.45, 10.0], [-70.66, -70.64, -70.0])
        self.assertNotEqual(b[0], b[1]); self.assertEqual(b[2], -1)
        self.assertEqual(self.dfu.anios_muestra(), [2000, 2004, 2008, 2012, 2016, 2020, 2024])


class RellenoTests(unittest.TestCase):
    def test_relleno_sin_declarar_queda_nan(self):
        """GEOS-CF trae pasos horarios completos en 1e15 sin _FillValue: deben leerse como faltantes."""
        import netCDF4

        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "geoscf_202001.nc"
            with netCDF4.Dataset(ruta, "w") as nc:
                nc.createDimension("time", 2); nc.createDimension("lev", 1)
                nc.createDimension("lat", 2); nc.createDimension("lon", 2)
                t = nc.createVariable("time", "f8", ("time",)); t.units = "hours since 2020-01-30 11:30:00"; t[:] = [0, 1]
                nc.createVariable("lat", "f8", ("lat",))[:] = [-33.5, -33.25]
                nc.createVariable("lon", "f8", ("lon",))[:] = [-70.75, -70.5]
                v = nc.createVariable("no2", "f4", ("time", "lev", "lat", "lon"))
                v[:] = np.array([[[[2e-9, 3e-9], [4e-9, 5e-9]]], [[[1e15] * 2] * 2]], dtype="float32")
            original = cm.ruta_mensual
            cm.ruta_mensual = lambda producto, yyyymm: ruta
            try:
                m = cm.leer_mes_geoscf("202001")
            finally:
                cm.ruta_mensual = original
        self.assertAlmostEqual(float(m.datos["no2"][0, 0]), 2.0, places=5)     # mol/mol → ppb
        self.assertTrue(np.isnan(m.datos["no2"][1]).all())
        self.assertTrue(np.isnan(cm.sin_relleno(np.ma.masked_invalid([np.inf, -1e15, 1.0]))[:2]).all())


class VentanaSatelitalTests(unittest.TestCase):
    def test_media_movil_ignora_nan(self):
        celdas = pd.DataFrame({"celda": [1, 2], "lat": [-33.0, -33.1], "lon": [-70.0, -70.1]})
        enl = pd.DataFrame({"celda": [1, 2], "maiac_pixel": [11, 22]})
        s = ft.SatelitesDiarios(celdas, enl)
        s._historial.append((date(2024, 4, 1), {"aod_dia": np.array([0.1, np.nan], "float32"), "no2_trop": np.array([1.0, 2.0], "float32")}))
        s._historial.append((date(2024, 4, 2), {"aod_dia": np.array([0.3, np.nan], "float32"), "no2_trop": np.array([np.nan, 4.0], "float32")}))
        v = s._ventana(date(2024, 4, 2), "aod_dia", 3)
        self.assertAlmostEqual(float(v[0]), 0.2, places=6)
        self.assertTrue(np.isnan(v[1]))
        self.assertAlmostEqual(float(s._ventana(date(2024, 4, 2), "no2_trop", 7)[1]), 3.0, places=6)


class DerivadasTests(unittest.TestCase):
    def test_humedad_viento_y_unidades(self):
        df = pd.DataFrame({"el_t2m": [293.15], "el_d2m": [283.15], "el_u10": [3.0], "el_v10": [4.0],
                           "cams_no2": [1e-9], "cams_pm25": [1e-8], "blh": [20.0]})
        out = ft.derivadas_horarias(df)
        self.assertAlmostEqual(float(out["el_wind"][0]), 5.0, places=5)
        self.assertTrue(50 < float(out["el_rh"][0]) < 55)
        self.assertAlmostEqual(float(out["cams_pm25"][0]), 10.0, places=5)
        self.assertAlmostEqual(float(out["cams_no2"][0]), 28.9647 / 46.0055, places=4)
        self.assertAlmostEqual(float(out["inv_blh"][0]), 1 / 50.0, places=6)


class QmdTests(unittest.TestCase):
    """El modelo vive en docs/modelo_1km_horario.qmd; aquí sólo se comprueba que sus chunks compilan."""

    def test_chunks_compilan_y_etiquetas_unicas(self):
        import ast
        import re

        qmd = AQUI.parent / "docs" / "modelo_1km_horario.qmd"
        if not qmd.exists():
            self.skipTest("docs/modelo_1km_horario.qmd no está en este árbol")
        texto = qmd.read_text(encoding="utf-8")
        chunks = re.findall(r"^```\{python\}\n(.*?)^```", texto, flags=re.S | re.M)
        self.assertGreater(len(chunks), 20)
        for i, c in enumerate(chunks):
            codigo = "\n".join(l for l in c.splitlines() if not l.startswith("#|"))
            try:
                ast.parse(codigo)
            except SyntaxError as e:  # pragma: no cover
                self.fail(f"chunk {i} no compila: {e}")
        etiquetas = re.findall(r"^#\| label: (\S+)", texto, flags=re.M)
        self.assertEqual(len(etiquetas), len(set(etiquetas)), "etiquetas de chunk repetidas")
        for nombre in ("def ajustar(", "def validacion_cruzada("):
            self.assertIn(nombre, texto)
        # La producción de superficies vive en produccion.py y el documento la importa: si alguien la
        # vuelve a definir aquí habría dos implementaciones del contrato NetCDF y podrían divergir.
        produccion = (AQUI / "produccion.py").read_text(encoding="utf-8")
        for nombre in ("def predecir(", "def franja(", "class ContextoPrediccion", "def predecir_rango("):
            self.assertIn(nombre, produccion)
        self.assertIn("from produccion import", texto)
        for nombre in ("class ContextoPrediccion", "def predecir_rango(", "def marcar_rachas("):
            self.assertNotIn(nombre, texto)


class NetCDFTests(unittest.TestCase):
    def test_escritura_y_reapertura(self):
        import netCDF4

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "pm25_1km_20240418.nc"
            valores = np.array([[12.34, np.nan, 3199.9], [0.0, 5.5, 60.0]], dtype="float32")
            ts = np.array(["2024-04-18T04:00", "2024-04-18T05:00"], dtype="datetime64[ns]")
            cm.escribir_superficie_dia(p, "pm25", np.array([1, 2, 3]), ts, valores, {"contrato": "t", "lista": [1, 2]})
            with netCDF4.Dataset(p) as nc:
                v = nc["pm25"][:]
                self.assertAlmostEqual(float(v[0, 0]), 12.3, places=5)
                self.assertTrue(np.ma.is_masked(v[0, 1]))
                self.assertAlmostEqual(float(v[0, 2]), 3199.9, places=1)
                self.assertEqual(int(nc["ts_utc"][0]), int(pd.Timestamp("2024-04-18 04:00").timestamp()))
                self.assertEqual(nc.getncattr("lista"), "[1, 2]")
            ts2, celdas, val = cm.leer_superficie_dia(p)
            self.assertEqual(celdas.tolist(), [1, 2, 3])
            self.assertTrue(np.isnan(val[0, 1]))
            self.assertAlmostEqual(float(val[1, 1]), 5.5, places=5)
            self.assertEqual(str(ts2[1]), "2024-04-18T05:00:00")
            nc_path, json_path = cm.ruta_superficie_dia(Path(d), "no2", date(2024, 4, 18))
            self.assertEqual(nc_path.name, "no2_1km_20240418.nc")
            self.assertEqual(json_path.parent.name, "month=04")


class RelojTests(unittest.TestCase):
    def test_transiciones_chile(self):
        t = vr.transiciones("America/Santiago", 2023)
        self.assertEqual(t, [(date(2023, 4, 2), "ambigua", 0), (date(2023, 9, 3), "inexistente", 1)])
        self.assertEqual(vr.transiciones("America/Punta_Arenas", 2023), [])

    def test_evaluacion_de_dias(self):
        fijo = pd.DatetimeIndex([datetime(2023, 9, 3, h) for h in range(24)])
        civil = pd.DatetimeIndex([datetime(2023, 9, 3, h) for h in range(24) if h != 1])
        self.assertEqual(vr.evaluar_dia(fijo, date(2023, 9, 3), "inexistente", 1)["estado"], "reloj_fijo")
        self.assertEqual(vr.evaluar_dia(civil, date(2023, 9, 3), "inexistente", 1)["estado"], "hora_civil")
        rep = pd.DatetimeIndex([datetime(2023, 4, 2, h) for h in range(24)] + [datetime(2023, 4, 2, 0)])
        self.assertEqual(vr.evaluar_dia(rep, date(2023, 4, 2), "ambigua", 0)["estado"], "hora_civil")
        self.assertEqual(vr.evaluar_dia(fijo, date(2023, 4, 2), "ambigua", 0)["estado"], "sin_etiquetas")
        self.assertEqual(vr.veredicto(["reloj_fijo", "reloj_fijo"]), "reloj_fijo")
        self.assertEqual(vr.veredicto(["reloj_fijo", "sin_evidencia"]), "reloj_fijo_parcial")
        self.assertEqual(vr.veredicto(["hora_civil", "reloj_fijo"]), "hora_civil")


class LulcSinteticoTests(unittest.TestCase):
    def test_fracciones_desde_raster(self):
        try:
            import rasterio
            from rasterio.transform import from_origin
        except ImportError:  # pragma: no cover
            self.skipTest("rasterio no instalado (sólo lo usa covariables_estaticas.py)")

        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d) / "2020"
            raiz.mkdir()
            # Raster 300 m (0,0027°) que cubre una celda 0,01° con 3×3 píxeles urbanos (190)
            # y el resto bosque (50); la celda vecina toda agua (210).
            arr = np.full((8, 8), 50, dtype="uint8")
            arr[0:3, 0:3] = 190
            arr[:, 4:] = 210
            tr = from_origin(-70.67, -33.46, 0.0025, 0.0025)
            with rasterio.open(raiz / "ESA_CCI_LC_2020_test_300m.tif", "w", driver="GTiff", height=8, width=8,
                               count=1, dtype="uint8", crs="EPSG:4326", transform=tr, nodata=0) as dst:
                dst.write(arr, 1)
            celdas = pd.DataFrame({"celda": [1, 2], "lat": [-33.465, -33.465], "lon": [-70.665, -70.655]})
            original = ce.LULC_DIR
            ce.LULC_DIR = Path(d)
            try:
                out, usado = ce.lulc_fracciones(celdas, 2024)
            finally:
                ce.LULC_DIR = original
            self.assertEqual(usado, 2020)
            fila = out.iloc[0]
            self.assertAlmostEqual(float(fila["lulc_urbano"]), 9 / 16, places=6)
            self.assertAlmostEqual(float(fila["lulc_bosque"]), 7 / 16, places=6)
            self.assertAlmostEqual(float(out.iloc[1]["lulc_agua"]), 1.0, places=6)
            self.assertEqual(int(fila["lulc_n_pixeles"]), 16)


if __name__ == "__main__":
    unittest.main()
