"""Pruebas de ``panel_red2_v2``: reglas R3-R11 y R17 con datos sintéticos, y la réplica de ``construir_panel``.

* R3: una estación con una sola hora entra; sin celda, no.
* R4: el período va del 2000-01-01 al 2026-10-24 por día local UTC−4.
* R5: la conversión va antes del rango; rachas sobre el registro completo; peor bandera de la hora.
* R6: factor por serie y SNIFA El Peñón × 0,5318.
* R7: colisión de dos etiquetas en la misma hora UTC, con conteo y bandera.
* R9: una copia por hora en los duplicados.
* R11: inventario de insumos con corte (manifiestos, eventos, legado por fecha de modificación) y vista de enlaces.
* R17: regímenes por la regla del 50 % de los días.

La réplica de ``construir_panel`` corre en un proceso aparte con el código v1 real (``_features``, ``_comun_modelo``),
una raíz de datos vacía y una grilla de cuatro celdas: sin red, sin el disco de datos y sin escribir nada.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))
sys.path.insert(0, str(V2 / "tests"))
import _rutas_v2 as rv  # noqa: E402
import calidad_v2 as cv  # noqa: E402
import panel_red2_v2 as pr  # noqa: E402
import reloj_sinca_v2 as rs  # noqa: E402
import unidades_v2 as uv  # noqa: E402
from _sintetico_v2 import raices_temporales  # noqa: E402
from test_reloj_sinca_v2 import RELOJES, datos_red2, escribir_derivado, etiquetas  # noqa: E402
from test_reloj_sinca_v2 import carpeta_de_version, destino_red2, plan_de_prueba, plantar_version  # noqa: E402

CFG = json.loads((V2 / "config_v2.json").read_text(encoding="utf-8"))
# Columnas del panel v1 (panel_no2.json, 2026-09-22). frac_lena ya no la produce _features (no está en las listas
# cerradas de predictores), así que la réplica de hoy la omite.
COLUMNAS_V1 = ["estacion", "ts_utc", "obs", "n", "version", "celda", "lat_est", "lon_est", "region_sinca", "hora_local",
               "hora_sin", "hora_cos", "doy_sin", "doy_cos", "dow", "mes", "anio", "fecha_local", "aod_terra",
               "aod_aqua", "aod_dia", "aod_n", "no2_trop", "no2_trop_prec", "no2_trop_hora", "aod_3d", "aod_7d",
               "no2_trop_7d", "no2_trop_15d", "el_t2m", "el_d2m", "el_sp", "el_u10", "el_v10", "el_tp_1h_mm", "blh",
               "m2_t2m", "m2_rh2m", "m2_u10m", "m2_v10m", "m2_pblh", "m2_aod", "m2_pm25", "m2_ps", "cams_no2",
               "cams_pm25", "cams_o3", "cams_co", "gcf_no2", "gcf_pm25", "gcf_o3", "gcf_co", "el_rh", "el_wind",
               "el_wdir_sin", "el_wdir_cos", "inv_blh", "m2_aod_pblh", "gcf_pm25_blh", "acag_pm25", "acag_clim",
               "elev_m", "pendiente_deg", "dist_costa_km", "frac_lena", "vias_km_km2", "vias_princ_km_km2", "lat", "lon",
               "macrozona_cod", "lulc_urbano", "lulc_cultivo", "lulc_bosque", "lulc_matorral_pastizal",
               "lulc_desnudo", "lulc_agua", "lulc_nieve_hielo", "pob_dens", "obs_vec", "peso_vec", "dist_est_km"]


def derivado(etiquetas, valores, qc="validado", seleccionada=True) -> pd.DataFrame:
    n = len(valores)
    return pd.DataFrame({"ts_local": pd.to_datetime(etiquetas), "obs": np.asarray(valores, dtype="float64"),
                         "qc_observacion": [qc] * n if isinstance(qc, str) else qc,
                         "seleccionada": [seleccionada] * n if isinstance(seleccionada, bool) else seleccionada})


def horas(inicio: str, n: int) -> pd.DatetimeIndex:
    return pd.Timestamp(inicio) + pd.to_timedelta(np.arange(n), unit="h")


def registrar_maiac_de_prueba(r, confirmada) -> dict:
    """Una tesela del catálogo MAIAC anterior al corte, registrada por T5 (``registrar_catalogo_maiac``)."""
    tesela = r.datos / "contaminantes" / pr.CATALOGO_MAIAC / "tile=h11v10" / "pixeles.parquet"
    tesela.parent.mkdir(parents=True)
    tesela.write_bytes(b"tile")
    vieja = (pr.utc(pr.CORTE_INSUMOS_UTC) - pd.Timedelta(days=50)).timestamp()
    os.utime(tesela, (vieja, vieja))
    reg, _, _ = pr.registrar_catalogo_maiac(r, r.datos, cfg={"red_de_monitores": {}}, estado=confirmada)
    return reg


class SerieTests(unittest.TestCase):
    def test_conversion_antes_del_rango(self):
        f = uv.PPB_POR_UG_M3N_NO2
        d = derivado(["2024-01-01 01:00", "2024-01-01 02:00", "2024-01-01 03:00", "2024-01-01 04:00"],
                     [1500.0, 2000.0, np.nan, -1.0])
        s = pr.procesar_serie_sinca(d, "X", "no2", f, {}, "America/Santiago", "v")
        self.assertEqual(len(s), 1)                                    # 1500 µg/m³N = 797,7 ppb entra; 2000 no
        self.assertAlmostEqual(float(s["obs"].iloc[0]), 1500.0 * f)
        s = pr.procesar_serie_sinca(derivado(["2024-01-01 01:00"], [1001.0]), "X", "no2", 1.0, {}, "America/Santiago", "v")
        self.assertTrue(s.empty)                                       # 1.001 ppb fuera del rango
        s = pr.procesar_serie_sinca(derivado(["2024-01-01 01:00"], [400.0]), "X", "o3", 1.0, {}, "America/Santiago", "v")
        self.assertEqual(len(s), 1)                                    # O3: 0-500 ppb
        with self.assertRaises(ValueError):
            pr.procesar_serie_sinca(derivado(["2024-01-01 01:00"], [1.0]), "X", "no2", float("nan"), {},
                                    "America/Santiago", "v")

    def test_seleccionada_y_bandera(self):
        d = derivado(["2024-01-01 01:00", "2024-01-01 02:00"], [5.0, 6.0], qc=["validado", "no_validado"],
                     seleccionada=[True, False])
        s = pr.procesar_serie_sinca(d, "X", "pm25", 1.0, {}, "America/Santiago", "v")
        self.assertEqual(list(s["qc"]), [cv.CODIGO_QC["validado"]])
        self.assertEqual(s["ts_utc"].iloc[0], pd.Timestamp("2024-01-01 04:00"))

    def test_colision_civil(self):
        d = derivado(["2023-09-02 23:00", "2023-09-03 00:00", "2023-09-03 01:00"], [10.0, 20.0, 30.0],
                     qc=["validado", "preliminar", "validado"])
        with self.assertRaises(SystemExit):                              # sin convención decidida no se convierte
            pr.procesar_serie_sinca(d, "X", "pm25", 1.0, {2023: "hora_civil"}, "America/Santiago", "v")
        s = pr.procesar_serie_sinca(d, "X", "pm25", 1.0, {2023: "hora_civil"}, "America/Santiago", "v", "fin")
        a = pr.agregar_hora(s)
        fila = a[a["ts_utc"] == pd.Timestamp("2023-09-03 03:00")].iloc[0]
        self.assertEqual((fila["n"], float(fila["obs"]), bool(fila["colision_utc"])), (2, 25.0, True))
        self.assertEqual(int(fila["qc"]), cv.CODIGO_QC["preliminar"])   # la peor de la hora
        self.assertEqual(int(a["colision_utc"].sum()), 1)


class ObservacionesTests(unittest.TestCase):
    def setUp(self):
        self.con_celda = pd.DataFrame({"estacion": ["A", "B", "C", "S"], "celda": [1, 2, -1, 3],
                                       "lat": [-33.0, -34.0, -35.0, -36.0], "lon": -70.6})

    def serie(self, est, inicio, valores):
        d = derivado(horas(inicio, len(valores)), valores)
        return pr.procesar_serie_sinca(d, est, "pm25", 1.0, {}, "America/Santiago", "v")

    def test_una_hora_basta_y_sin_celda_no(self):
        rng = np.random.default_rng(1)
        o, info = pr.observaciones_red2([self.serie("A", "2024-01-01 01:00", rng.uniform(1, 50, 100)),
                                         self.serie("B", "2024-01-01 01:00", [12.0]),
                                         self.serie("C", "2024-01-01 01:00", rng.uniform(1, 50, 100))],
                                        pd.DataFrame(), self.con_celda)
        self.assertEqual(sorted(o["estacion"].unique()), ["A", "B"])
        self.assertEqual(int((o["estacion"] == "B").sum()), 1)
        self.assertEqual(info["sin_celda"], ["C"])

    def test_periodo(self):
        et = ["1999-12-31 23:00", "2000-01-01 00:00", "2000-01-01 01:00", "2026-10-24 23:00", "2026-10-25 00:00",
              "2026-10-25 01:00"]
        d = derivado(et, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        s = pr.procesar_serie_sinca(d, "A", "pm25", 1.0, {}, "America/Santiago", "v")
        o, info = pr.observaciones_red2([s], pd.DataFrame(), self.con_celda)
        # Inicio UTC = etiqueta + 3 h; el período se corta por el día local del inicio (UTC − 4 h), es decir, por la
        # etiqueta − 1 h: la etiqueta 00:00 del 1 de enero cierra la última hora de 1999 y la 00:00 del 25 de octubre
        # cierra la última del 24.
        self.assertEqual(list(o["obs"]), [3.0, 4.0, 5.0])
        self.assertEqual(info["fuera_del_periodo"], 3)

    def test_rachas_sobre_el_registro_completo(self):
        valores = np.r_[np.full(30, 7.0), np.arange(101.0, 141.0)]
        s = self.serie("A", "1999-12-31 00:00", valores)              # la racha empieza antes del período
        o, info = pr.observaciones_red2([s], pd.DataFrame(), self.con_celda)
        self.assertNotIn(7.0, set(o["obs"]))
        self.assertEqual(info["horas_en_racha"], 30)

    def test_duplicados(self):
        rng = np.random.default_rng(2)
        v = np.round(rng.uniform(1, 80, 1000), 1)
        con = pd.DataFrame({"estacion": ["A", "B"], "celda": [1, 2], "lat": [-33.0, -33.005], "lon": -70.6})
        o, info = pr.observaciones_red2([self.serie("A", "2024-01-01 01:00", v),
                                         self.serie("B", "2024-01-01 01:00", v[:800])], pd.DataFrame(), con)
        self.assertEqual(info["pares_duplicados"], 1)
        self.assertEqual(sorted(o["estacion"].unique()), ["A"])
        self.assertEqual(info["horas_quitadas_por_copias"], 800)

    def test_misma_regla_que_produccion_observaciones(self):
        """T12 (corrección, [delegada]): el armado importa ``produccion.py`` con su huella fijada
        (``importar_produccion``) y marca las rachas con ``produccion.marcar_rachas``; ``produccion.observaciones``
        misma lee las series de la v1 y no admite las de la red 2, así que lo demás de su regla se replica. La réplica
        da lo mismo: ``marcar_rachas`` y ``observaciones`` se extraen de ``produccion.py`` por AST y se ejecutan
        aisladas sobre las mismas horas sintéticas (rachas de 23, 24 —cortada por un hueco— y 40 registros iguales, en
        estaciones con y sin celda); quedan exactamente las horas que deja ``observaciones_red2``, con las mismas
        rachas, con ``produccion.marcar_rachas`` (como en el armado) y sin él (``rachas_sin_produccion``)."""
        import ast
        from types import SimpleNamespace
        ruta = V2.parent / "produccion.py"
        self.assertEqual(uv.sha256_archivo(ruta), pr.huellas_del_repositorio()["scripts_modelo_1km/produccion.py"])
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        espacio, constantes = {"np": np, "pd": pd, "_OBS": {}}, {"int": int, "os": SimpleNamespace(environ={})}
        for nodo in arbol.body:
            if isinstance(nodo, ast.FunctionDef) and nodo.name in ("marcar_rachas", "observaciones"):
                exec(compile(ast.Module(body=[nodo], type_ignores=[]), str(ruta), "exec"), espacio)
            elif isinstance(nodo, ast.Assign) and [ast.unparse(t) for t in nodo.targets] == ["QC_RACHA"]:
                exec(compile(ast.Module(body=[nodo], type_ignores=[]), str(ruta), "exec"), constantes)
        self.assertEqual(constantes["QC_RACHA"], pr.QC_RACHA)                 # el umbral por omisión de la v1: 24
        self.assertEqual(pr.entorno_lectura(Path("d"), Path("v1"))["MODELO_1KM_QC_RACHA"], str(pr.QC_RACHA))
        rng = np.random.default_rng(7)
        series = [self.serie("A", "2024-01-01 01:00", np.full(12, 5.0)),              # 24 iguales, con un hueco
                  self.serie("A", "2024-01-02 01:00", np.r_[np.full(12, 5.0), rng.uniform(1, 50, 60)]),
                  self.serie("B", "2024-01-01 01:00", np.r_[np.full(23, 9.0), rng.uniform(1, 50, 30),
                                                            np.full(40, 0.0), rng.uniform(1, 50, 30)]),
                  self.serie("C", "2024-01-01 01:00", np.r_[np.full(30, 3.0), rng.uniform(1, 50, 30)])]
        horas = pd.concat([pr.agregar_hora(s) for s in series], ignore_index=True)
        usables = self.con_celda[self.con_celda["celda"] >= 0]
        espacio.update(series_sinca=lambda pol: horas, estaciones_usables=lambda: usables,
                       QC_RACHA=constantes["QC_RACHA"])
        v1 = espacio["observaciones"]("pm25")                                 # la de produccion.py
        self.assertEqual(sorted(v1["estacion"].unique()), ["A", "B"])
        self.assertEqual(v1.groupby("estacion")["racha"].sum().to_dict(), {"A": 24, "B": 40})
        esperado = v1.loc[~v1["racha"], ["estacion", "ts_utc", "obs"]]
        clave = ["estacion", "ts_utc"]
        for nombre, marcar in (("produccion.marcar_rachas", espacio["marcar_rachas"]), ("sin produccion.py", None)):
            with self.subTest(nombre):
                o, info = pr.observaciones_red2(series, pd.DataFrame(), self.con_celda, marcar_rachas=marcar)
                self.assertEqual((info["pares_duplicados"], info["fuera_del_periodo"]), (0, 0))
                pd.testing.assert_frame_equal(o[["estacion", "ts_utc", "obs"]].sort_values(clave).reset_index(drop=True),
                                              esperado.sort_values(clave).reset_index(drop=True), check_dtype=False)
                self.assertEqual(info["horas_en_racha"], 24 + 40 + 30)        # C, sin celda, también se marca


    def test_las_rachas_las_marca_la_funcion_del_armado(self):
        """T12 (ronda 4, menor 16): ``observaciones_red2`` usa la función de rachas que recibe (en el armado,
        ``produccion.marcar_rachas``) y ``observaciones_desde_derivado`` se la pasa."""
        from unittest import mock
        series = [self.serie("A", "2024-01-01 01:00", np.arange(30.0))]
        o, info = pr.observaciones_red2(series, pd.DataFrame(), self.con_celda,
                                        marcar_rachas=lambda h, minimo: h.assign(racha=True))
        self.assertEqual((len(o), info["horas_en_racha"]), (0, 30))           # todas en racha: no queda ninguna
        visto = {}

        def capturar(lista, sn, con_celda, **k):
            visto.update(k)
            return pd.DataFrame(columns=["estacion", "ts_utc", "obs"]), {}
        marcar = lambda h, minimo: h                                          # noqa: E731
        with mock.patch.object(pr, "observaciones_red2", capturar):
            pr.observaciones_desde_derivado("pm25", [], {}, {}, {}, rs.leer_politica(), Path("no_existe.parquet"),
                                            self.con_celda, evaluadas=set(), con_fila=set(), marcar_rachas=marcar,
                                            huellas={})
        self.assertIs(visto["marcar_rachas"], marcar)


class SnifaTests(unittest.TestCase):
    def test_factor_a_25_grados(self):
        o = pd.DataFrame({"station_id": ["el_penon", "charrua", "progreso", "quinel"], "pollutant": "no2",
                          "numeric_usable": True, "usable_native": [True, True, False, True],
                          "date_local": pd.to_datetime("2024-01-01"), "hour_index": [1, 1, 1, 1],
                          "value": [100.0, 100.0, 50.0, 10.0], "unit": ["ug/m3N", "ug/m3N", "ppb", "ug/m3N"],
                          "document_id": "d1", "value_conflict": False, "quality_conflict": False})
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "snifa.parquet"
            o.to_parquet(ruta)
            s = pr.series_snifa_red2(ruta, "no2").set_index("estacion")
        self.assertAlmostEqual(float(s.loc["SNIFA-ELPENON", "obs"]), 100.0 * uv.PPB_POR_UG_M3N_NO2, places=9)
        self.assertEqual(float(s.loc["SNIFA-CHARRUA", "obs"]), 100.0)
        self.assertEqual(int(s.loc["SNIFA-PROGRESO", "qc"]), cv.CODIGO_QC["solo_numeric_usable"])
        self.assertNotIn("quinel", " ".join(s.index))
        self.assertEqual(s["ts_utc"].iloc[0], pd.Timestamp("2024-01-01 05:00"))   # etiqueta de inicio 1 + 4 h
        self.assertTrue(pr.series_snifa_red2(Path("no_existe.parquet"), "pm25").empty)


class InventarioTests(unittest.TestCase):
    """Árbol de productos sintético con registros antes y después del corte (M2 y M3)."""

    def setUp(self):
        import hashlib
        self.tmp = tempfile.TemporaryDirectory()
        base0 = Path(self.tmp.name)
        d = base0 / "datos"
        c = d / "contaminantes"
        self.d, self.local = d, base0 / "local"
        corte = pr.utc(pr.CORTE_INSUMOS_UTC)
        antes, despues = (corte - pd.Timedelta(days=2)).isoformat(), (corte + pd.Timedelta(hours=1)).isoformat()
        h = lambda b: hashlib.sha256(b).hexdigest()                                  # noqa: E731
        base = c / "ERA5Land" / "chile_nativo_01deg"
        (base / "mensual").mkdir(parents=True)
        (base / "manifiestos").mkdir()
        self.bytes = {}
        for mes, pub, contenido in (("202608", antes, b"agosto"), ("202609", despues, b"septiembre"),
                                    ("202607", antes, b"julio-reescrito")):
            nc = base / "mensual" / f"era5land_{mes}_chile_pixeles.nc"
            nc.write_bytes(contenido)
            declarado = h(b"julio") if mes == "202607" else h(contenido)          # julio cambió en el disco
            (base / "manifiestos" / f"era5land_{mes}.json").write_text(json.dumps(
                {"publicado_utc": pub, "salida": {"archivo": str(nc), "bytes": len(contenido), "sha256": declarado},
                 "catalogo": {"archivo": str(base / "catalogo_pixeles.parquet"), "sha256": h(b"cat")}}))
        (base / "catalogo_pixeles.parquet").write_bytes(b"cat")
        (base / "mensual" / "era5land_202606_chile_pixeles.nc").write_bytes(b"sin manifiesto")
        g = c / "GEOS_CF" / "raw_chile"
        g.mkdir(parents=True)
        for mes, t in (("202401", corte - pd.Timedelta(days=30)), ("202501", corte + pd.Timedelta(days=1))):
            q = g / f"geoscf_{mes}.nc"
            q.write_bytes(b"g" + mes.encode())
            os.utime(q, (t.timestamp(), t.timestamp()))
        vieja = (corte - pd.Timedelta(days=60)).timestamp()
        for prod, carpeta, eventos, patron in (("tropomi", c / "S5P_TROPOMI" / "NO2", "_manifiestos", "tropomi_no2_x"),
                                               ("acag", c / "ACAG_V6GL03", "_manifiestos", "acag_x")):
            (carpeta / "raw_chile").mkdir(parents=True)
            (carpeta / eventos).mkdir()
            nombres = {k: f"{prod}_{k}.nc" for k in ("vieja", "rehecha", "nueva", "legado")}
            for k, n in nombres.items():
                (carpeta / "raw_chile" / n).write_bytes(k.encode())
            os.utime(carpeta / "raw_chile" / nombres["legado"], (vieja, vieja))
            with open(carpeta / eventos / f"{patron}.jsonl", "w", encoding="utf-8") as fh:
                for k, reg in (("vieja", antes), ("rehecha", antes), ("rehecha", despues), ("nueva", despues)):
                    fh.write(json.dumps({"evento": "archivo_validado", "registrado_utc": reg, "sha256_salida": h(k.encode()),
                                         "salida": str(carpeta / "raw_chile" / nombres[k])}) + "\n")
            setattr(self, f"nombres_{prod}", nombres)
        m = c / "MCD19A2.061"
        partes = []
        for tipo, nombre in (("observaciones", "maiac_obs_20240102.parquet"),
                             ("catalogo_pasadas", "maiac_pasadas_20240102.parquet")):
            q = m / "pixeles_horario" / tipo / "year=2024" / "month=01" / "day=02" / nombre
            q.parent.mkdir(parents=True)
            q.write_bytes(tipo.encode())
            partes.append(h(tipo.encode()))
        suelto = m / "pixeles_horario" / "observaciones" / "year=2024" / "month=01" / "day=05" / "maiac_obs_20240105.parquet"
        suelto.parent.mkdir(parents=True)
        suelto.write_bytes(b"sin fila")
        (m / "pixeles_horario" / "catalogo_pixeles" / "tile=h11v10").mkdir(parents=True)
        (m / "pixeles_horario" / "catalogo_pixeles" / "tile=h11v10" / "pixeles.parquet").write_bytes(b"tile")
        pd.DataFrame({"fecha": ["2024-01-02", "2024-01-03"], "flujo": "x", "estado": ["ok", "error"], "filas": 1,
                      "sha256": ["+".join(partes + ["c" * 64]), "d"], "actualizado_utc": [antes, antes]}).to_csv(
            m / "manifest_pixeles_horario.csv", index=False)
        # MERRA-2 2026-10 vuelto a publicar después del corte, con su copia de corte (T3) en la raíz local.
        mb = c / "MERRA2_meteo" / "chile_nativo_05x0625deg"
        (mb / "mensual").mkdir(parents=True)
        (mb / "manifiestos").mkdir()
        nc = mb / "mensual" / "merra2_meteo_202610_chile_pixeles.nc"
        nc.write_bytes(b"octubre-completo")
        (mb / "manifiestos" / "merra2_meteo_202610.json").write_text(json.dumps(
            {"publicado_utc": despues, "salida": {"archivo": str(nc), "bytes": 16, "sha256": h(b"octubre-completo")}}))
        copia = self.local / "copias" / "merra2"
        copia.mkdir(parents=True)
        (copia / "merra2_meteo_202610_chile_pixeles.nc").write_bytes(b"octubre-parcial")
        man_copia = {"publicado_utc": antes, "salida": {"archivo": "x/merra2_meteo_202610_chile_pixeles.nc", "bytes": 15,
                                                        "sha256": h(b"octubre-parcial")}}
        (copia / "merra2_meteo_202610.json").write_text(json.dumps(man_copia))
        rel = "contaminantes/MERRA2_meteo/chile_nativo_05x0625deg/mensual/merra2_meteo_202610_chile_pixeles.nc"
        rel7 = "contaminantes/ERA5Land/chile_nativo_01deg/mensual/era5land_202607_chile_pixeles.nc"
        (copia / "julio.nc").write_bytes(b"julio")
        self.copias = {rel: {"copia": "copias/merra2/merra2_meteo_202610_chile_pixeles.nc", "sha256": h(b"octubre-parcial"),
                             "manifiesto": "copias/merra2/merra2_meteo_202610.json",
                             "sha256_manifiesto": h((copia / "merra2_meteo_202610.json").read_bytes())},
                       rel7: {"copia": "copias/merra2/julio.nc", "sha256": h(b"julio"),
                              "manifiesto": "copias/merra2/merra2_meteo_202610.json",
                              "sha256_manifiesto": h((copia / "merra2_meteo_202610.json").read_bytes())}}

    def tearDown(self):
        for q in Path(self.tmp.name).rglob("*"):
            if q.is_file():
                os.chmod(q, 0o644)
        self.tmp.cleanup()

    def inventario(self):
        return pr.inventario_insumos(self.d, local=self.local, copias=self.copias).set_index("clave")

    def test_reglas_de_registro(self):
        e = self.inventario()
        self.assertTrue(e.loc["202608", "entra"])
        self.assertFalse(e.loc["202609", "entra"])                       # publicado después del corte
        self.assertTrue(e.loc["202607", "entra"])                        # el tamaño ya no decide: lo decide la huella
        self.assertFalse(e.loc["202606", "entra"])                       # sin manifiesto: no hay fecha que valga
        self.assertTrue(e.loc["202401", "entra"])                        # GEOS-CF por su fecha (T1(4))
        self.assertEqual(e.loc["202401", "verificacion"], pr.HUELLA_REGISTRAR)
        self.assertFalse(e.loc["202501", "entra"])
        t, a = self.nombres_tropomi, self.nombres_acag
        self.assertTrue(e.loc[t["vieja"], "entra"])
        self.assertFalse(e.loc[t["rehecha"], "entra"])                  # validada de nuevo después del corte
        self.assertFalse(e.loc[t["nueva"], "entra"])
        self.assertTrue(e.loc[t["legado"], "entra"])                    # órbita antigua sin evento (T1(4))
        self.assertFalse(e.loc[a["legado"], "entra"])                   # ACAG sin evento: T1(4) no lo cubre
        self.assertTrue(e.loc["2024-01-02:observaciones", "entra"])
        self.assertFalse(e.loc["maiac_obs_20240105:observaciones", "entra"])   # en el disco, sin fila en el manifiesto
        self.assertNotIn("2024-01-03:observaciones", e.index)           # día con error: no hay archivo que leer
        self.assertTrue(e.loc["era5land", "entra"])                     # catálogo con la huella de los manifiestos
        self.assertFalse(e.loc["maiac/tile=h11v10", "entra"])           # catálogo MAIAC sin registro
        self.assertTrue(e.loc["202610", "entra"])                       # MERRA-2 de la copia de corte (T3)
        self.assertTrue(e.loc["202610", "origen"].startswith("copia_de_corte:"))
        mtime = e[e["fuente_registro"].str.startswith("mtime")]
        self.assertEqual(set(mtime["producto"]), {"geoscf", "tropomi_no2"})

    def test_copia_de_corte_con_sus_sumas(self):
        """Menor 43: el SHA256SUMS.txt de la copia de corte de T3 también se comprueba por su huella."""
        rel = "contaminantes/MERRA2_meteo/chile_nativo_05x0625deg/mensual/merra2_meteo_202610_chile_pixeles.nc"
        sumas = self.local / "copias" / "merra2" / "SHA256SUMS.txt"
        sumas.write_text("x  y\n")
        bien = {rel: {**self.copias[rel], "sumas": "copias/merra2/SHA256SUMS.txt",
                      "sha256_sumas": hashlib.sha256(sumas.read_bytes()).hexdigest()}}
        self.assertIsNotNone(pr.copia_de_corte(rel, self.local, bien))
        for malo in ({"sha256_sumas": "0" * 64}, {"sha256_sumas": None}):
            with self.subTest(malo), self.assertRaises(SystemExit):
                pr.copia_de_corte(rel, self.local, {rel: {**bien[rel], **malo}})
        sumas.unlink()
        with self.assertRaises(SystemExit):
            pr.copia_de_corte(rel, self.local, bien)
        real = next(iter(pr.COPIAS_DE_CORTE.values()))
        self.assertEqual((real["sha256_sumas"][:8], real["sumas"].endswith("SHA256SUMS.txt")), ("16726973", True))

    def test_congela_copiando_con_su_huella(self):
        inv = pr.inventario_insumos(self.d, local=self.local, copias=self.copias)
        with raices_temporales("v2-congelado-") as r:
            destino = r.raiz_v2 / "insumos_red2" / "congelados" / "data"
            info = pr.congelar_insumos(inv, self.d, destino, r, local=self.local, copias=self.copias)
            self.assertEqual(info["archivos"], int(inv["entra"].sum()))
            for x in info["registro"]:
                q = destino / x["ruta"]
                self.assertTrue(q.is_file() and not q.is_symlink())
                self.assertFalse(os.access(q, os.W_OK))                  # de sólo lectura
            reg = {x["ruta"]: x for x in info["registro"]}
            rel7 = "contaminantes/ERA5Land/chile_nativo_01deg/mensual/era5land_202607_chile_pixeles.nc"
            self.assertEqual((destino / rel7).read_bytes(), b"julio")        # el disco cambió: entra la copia de corte
            self.assertTrue(reg[rel7]["origen"].startswith("copia_de_corte:"))
            rel10 = "contaminantes/MERRA2_meteo/chile_nativo_05x0625deg/mensual/merra2_meteo_202610_chile_pixeles.nc"
            self.assertEqual((destino / rel10).read_bytes(), b"octubre-parcial")
            # Lo que cambie después en el disco de datos no toca la copia congelada.
            (self.d / "contaminantes/ERA5Land/chile_nativo_01deg/mensual/era5land_202608_chile_pixeles.nc").write_bytes(b"otra")
            self.assertEqual((destino / "contaminantes/ERA5Land/chile_nativo_01deg/mensual/era5land_202608_chile_pixeles.nc")
                             .read_bytes(), b"agosto")
            with self.assertRaises(SystemExit):
                pr.congelar_insumos(inv, self.d, destino, r, local=self.local, copias=self.copias)   # una sola vez

    def test_retomar_la_copia_congelada(self):
        """Cuarta revisión, menor 33: si el armado se cortó después de congelar, la copia se retoma sólo si sigue siendo la
        del inventario de ahora, archivo por archivo (sha256 vuelto a calcular, sólo lectura y sin archivos de más); el
        inventario.json se escribe una sola vez; y una copia sin su registro detiene el armado."""
        inv = pr.inventario_insumos(self.d, local=self.local, copias=self.copias)
        with raices_temporales("v2-retomar-") as r:
            raiz_ins = r.raiz_v2 / "insumos_red2"
            fuentes = {"datos": self.d, "local": self.local, "copias": self.copias}
            sha_inv, estado = pr.publicar_inventario(inv, r, raiz_ins)
            self.assertEqual((estado, pr.publicar_inventario(inv, r, raiz_ins)), ("escrito", (sha_inv, "sin_cambios")))
            with self.assertRaises(SystemExit) as e:                         # entra otra cosa: no se reescribe
                pr.publicar_inventario(inv.assign(entra=inv["entra"] & (inv["producto"] != "geoscf")), r, raiz_ins)
            self.assertIn("otro inventario", str(e.exception))
            # quinta revisión, menor 21: una descarga agregó después del corte un archivo que no entra (otra fila de
            # GEOS-CF y una de MAIAC sin tamaño): lo que entra no cambió y el armado retomado sigue
            corte = pr.utc(pr.CORTE_INSUMOS_UTC)
            nuevas = pd.DataFrame([pr._fila("geoscf", "202611", "contaminantes/GEOS_CF/raw_chile/geoscf_202611.nc", 9,
                                            None, corte + pd.Timedelta(days=1), "mtime (sin registro propio; T1(4))",
                                            corte, verificacion=pr.HUELLA_REGISTRAR),
                                   pr._fila("maiac", "2026-10-30:observaciones", "contaminantes/x.parquet", None, "s",
                                            corte + pd.Timedelta(days=5), "manifest_pixeles_horario.actualizado_utc",
                                            corte, pr.HUELLA_PARTE, "falta en el disco")], columns=pr.COLUMNAS_INVENTARIO)
            con_mas = pd.concat([inv, nuevas], ignore_index=True)
            self.assertEqual(pr.huella_de_lo_que_entra(con_mas), pr.huella_de_lo_que_entra(inv))
            self.assertEqual(pr.publicar_inventario(con_mas, r, raiz_ins), (sha_inv, "sin_cambios"))
            escrito = json.loads((raiz_ins / "inventario.json").read_text(encoding="utf-8"))
            self.assertEqual(escrito["huella_de_lo_que_entra"], pr.huella_de_lo_que_entra(inv))
            self.assertIn("traduccion", escrito["traza"])                     # quinta revisión, mayor 1
            registro, sha, estado = pr.congelar_o_retomar(inv, r, raiz_ins, **fuentes)
            self.assertEqual(estado, "congelado")
            cong = json.loads((raiz_ins / "congelados.json").read_text(encoding="utf-8"))
            self.assertEqual(cong["traza"]["insumos"]["inventario"]["sha256"], sha_inv)
            self.assertIn("codigo_red2", cong["traza"])
            self.assertEqual(pr.congelar_o_retomar(inv, r, raiz_ins, **fuentes), (registro, sha, "retomado"))
            with self.assertRaises(SystemExit):                              # el inventario cambió
                pr.retomar_congelados(inv.assign(entra=inv["entra"] & (inv["producto"] != "geoscf")),
                                      raiz_ins / "congelados" / "data", raiz_ins / "congelados.json", r)
            q = raiz_ins / "congelados" / "data" / registro["registro"][0]["ruta"]
            original = q.read_bytes()
            os.chmod(q, 0o644)
            q.write_bytes(original + b"x")
            os.chmod(q, 0o444)
            with self.assertRaises(SystemExit) as e:                         # un archivo de la copia cambió
                pr.congelar_o_retomar(inv, r, raiz_ins, **fuentes)
            self.assertIn("la copia congelada cambió", str(e.exception))
            os.chmod(q, 0o644)
            q.write_bytes(original)
            with self.assertRaises(SystemExit):                              # escribible: ya no es la copia
                pr.congelar_o_retomar(inv, r, raiz_ins, **fuentes)
            os.chmod(q, 0o444)
            (q.parent / "de_mas.nc").write_bytes(b"x")
            with self.assertRaises(SystemExit):                              # un archivo de más
                pr.congelar_o_retomar(inv, r, raiz_ins, **fuentes)
            (q.parent / "de_mas.nc").unlink()
            self.assertEqual(pr.congelar_o_retomar(inv, r, raiz_ins, **fuentes)[2], "retomado")
            os.chmod(raiz_ins / "congelados.json", 0o644)
            (raiz_ins / "congelados.json").unlink()
            with self.assertRaises(SystemExit) as e:                         # copia sin su registro
                pr.congelar_o_retomar(inv, r, raiz_ins, **fuentes)
            self.assertIn("sin congelados.json", str(e.exception))

    def test_huella_distinta_detiene_y_no_deja_nada(self):
        inv = pr.inventario_insumos(self.d, local=self.local, copias={})
        with raices_temporales("v2-congelado-") as r:
            destino = r.raiz_v2 / "insumos_red2" / "congelados" / "data"
            with self.assertRaises(SystemExit):                          # julio cambió y no hay copia de corte
                pr.congelar_insumos(inv, self.d, destino, r, local=self.local, copias={})
            self.assertFalse(destino.exists())
            self.assertFalse(destino.with_name(destino.name + ".parcial").exists())

    def test_catalogo_maiac_registrado_t5(self):
        """T5: las teselas del catálogo MAIAC entran por su registro, con su sha256, si su archivo es anterior al corte;
        el registro se escribe una vez, después de la confirmación en git, y nadie puede editarlo a mano."""
        corte = pr.utc(pr.CORTE_INSUMOS_UTC)
        cat = self.d / "contaminantes" / pr.CATALOGO_MAIAC
        vieja, nueva = (corte - pd.Timedelta(days=50)).timestamp(), (corte + pd.Timedelta(hours=2)).timestamp()
        os.utime(cat / "tile=h11v10" / "pixeles.parquet", (vieja, vieja))
        (cat / "tile=h12v12").mkdir()
        (cat / "tile=h12v12" / "pixeles.parquet").write_bytes(b"tesela nueva")
        os.utime(cat / "tile=h12v12" / "pixeles.parquet", (nueva, nueva))
        reg = pr.registro_catalogo_maiac(self.d)
        self.assertEqual((reg["entran"], reg["fuera"]), (1, 1))
        e = pr.inventario_insumos(self.d, local=self.local, copias=self.copias, registro_maiac=reg).set_index("clave")
        self.assertTrue(e.loc["maiac/tile=h11v10", "entra"])
        self.assertEqual(e.loc["maiac/tile=h11v10", "sha256_declarado"], hashlib.sha256(b"tile").hexdigest())
        self.assertFalse(e.loc["maiac/tile=h12v12", "entra"])                 # archivo posterior al corte, anotado
        self.assertIn("posterior", e.loc["maiac/tile=h12v12", "motivo"])
        sin = self.inventario()
        self.assertFalse(sin.loc["maiac/tile=h12v12", "entra"])               # sin registro, fuera
        confirmada = lambda repo, rutas: {k: "rastreado" for k in rutas}      # noqa: E731
        with raices_temporales("v2-maiac-") as r:
            with self.assertRaises(SystemExit):                               # sin la traducción confirmada en git
                pr.registrar_catalogo_maiac(r, self.d, cfg={"red_de_monitores": {}})
            self.assertEqual(pr.leer_registro_maiac(r), (None, None))
            escrito, sha, estado = pr.registrar_catalogo_maiac(r, self.d, cfg={"red_de_monitores": {}}, estado=confirmada)
            self.assertEqual((estado, pr.leer_registro_maiac(r)[1]), ("registrado", sha))
            self.assertEqual(escrito["traza"]["codigo_red2"]["scripts_modelo_1km/v2/panel_red2_v2.py"],
                             hashlib.sha256(Path(pr.__file__).read_bytes()).hexdigest())     # quinta revisión, mayor 1
            self.assertEqual(pr.registrar_catalogo_maiac(r, self.d, cfg={"red_de_monitores": {}}, estado=confirmada)[2],
                             "sin_cambios")
            inv = pr.inventario_insumos(self.d, local=self.local, copias=self.copias, registro_maiac=escrito)
            destino = r.raiz_v2 / "insumos_red2" / "congelados" / "data"
            info = pr.congelar_insumos(inv, self.d, destino, r, local=self.local, copias=self.copias)
            self.assertIn("contaminantes/" + pr.CATALOGO_MAIAC + "/tile=h11v10/pixeles.parquet",
                          {x["ruta"] for x in info["registro"]})
            (cat / "tile=h11v10" / "pixeles.parquet").write_bytes(b"otra tesela")
            with self.assertRaises(SystemExit):                               # cambió después de registrarla
                pr.registrar_catalogo_maiac(r, self.d, cfg={"red_de_monitores": {}}, estado=confirmada)
            with self.assertRaises(SystemExit):                               # y el armado no la copia
                pr.congelar_insumos(inv, self.d, r.raiz_v2 / "insumos_red2" / "otra", r, local=self.local,
                                    copias=self.copias)
            ruta = r.raiz_v2 / "insumos_red2" / pr.NOMBRE_REGISTRO_MAIAC
            editado = json.loads(ruta.read_text(encoding="utf-8"))
            fuera = next(t for t in editado["teselas"] if not t["entra"])
            fuera["entra"], fuera["motivo"] = True, ""                         # la posterior al corte, metida a mano
            os.chmod(ruta, 0o644)
            ruta.write_text(json.dumps(editado), encoding="utf-8")
            with self.assertRaises(SystemExit):                               # editado a mano
                pr.leer_registro_maiac(r)
            otro = pr.registro_catalogo_maiac(self.d, "2026-10-26T03:00:00Z")
            ruta.write_text(json.dumps(otro), encoding="utf-8")
            with self.assertRaises(SystemExit):                               # otro corte
                pr.leer_registro_maiac(r)

    def test_fuera_de_la_raiz_v2_o_de_la_carpeta(self):
        inv = pr.inventario_insumos(self.d, local=self.local, copias=self.copias)
        with raices_temporales("v2-congelado-") as r:
            with self.assertRaises(rv.EscrituraNoPermitida):
                pr.congelar_insumos(inv, self.d, Path(self.tmp.name) / "fuera", r, local=self.local, copias=self.copias)
            malo = inv[inv["entra"]].iloc[:1].assign(ruta="../fuera.nc")
            with self.assertRaises(rv.EscrituraNoPermitida):
                pr.congelar_insumos(malo, self.d, r.raiz_v2 / "insumos_red2" / "otra", r, local=self.local, copias={})


class ObservacionesFloat64Tests(unittest.TestCase):
    """La reproducción (a2) de validar_vecindario con la red 2 lee las observaciones float64 del armado, por huella."""

    def test_lee_por_huella_y_en_float64(self):
        with raices_temporales("v2-obs64-") as r:
            (r.raiz_v2 / "paneles").mkdir(parents=True)
            o = pd.DataFrame({"estacion": ["A", "B"], "ts_utc": pd.to_datetime(["2020-01-01 03:00", "2020-01-01 04:00"]),
                              "obs": np.array([1.0000000001, 2.5]), "n": [1, 1]})
            ruta = r.raiz_v2 / "paneles" / pr.NOMBRE_OBS.format(pol="pm25")
            o.to_parquet(ruta, index=False)
            meta = {"observaciones_sha256": {"pm25": pr.sha256_de(ruta)},
                    "qc": {"horas_totales": 5, "horas_en_racha": 3, "estaciones_con_racha": 1}}
            leido, info = pr.observaciones_float64("pm25", r, meta)
            self.assertEqual(leido["obs"].dtype, np.float64)
            self.assertEqual(leido["obs"].iloc[0], 1.0000000001)               # sin pasar por float32
            self.assertEqual(list(leido.columns), ["estacion", "ts_utc", "obs"])
            self.assertEqual((info["filas_validas"], info["filas_en_racha"], info["estaciones_con_racha"]), (5, 3, 1))
            with self.assertRaises(SystemExit):                                # otra huella
                pr.observaciones_float64("pm25", r, {**meta, "observaciones_sha256": {"pm25": "0" * 64}})
            with self.assertRaises(SystemExit):                                # sin huella declarada
                pr.observaciones_float64("pm25", r, {"qc": meta["qc"]})
            o.assign(obs=o["obs"].astype("float32")).to_parquet(ruta, index=False)
            with self.assertRaises(SystemExit):                                # float32 aunque la huella calce
                pr.observaciones_float64("pm25", r, {**meta, "observaciones_sha256": {"pm25": pr.sha256_de(ruta)}})


class EstratoPropietarioTests(unittest.TestCase):
    """R10: el propietario de la estación de cada fila, como estrato descriptivo de las métricas, por huella."""

    def test_codigos_por_fila_y_huella(self):
        with raices_temporales("v2-propietario-") as r:
            (r.raiz_v2 / "paneles").mkdir(parents=True)
            est = pd.DataFrame({"estacion": ["A", "B", "C", "D"],
                                "tipo_propietario": ["pública", "empresa", None, "no informado"]})          # D: SNIFA
            ruta = r.raiz_v2 / "paneles" / pr.NOMBRE_ESTACIONES
            est.to_parquet(ruta, index=False)
            meta = r.raiz_v2 / "paneles" / pr.NOMBRE_PANEL.format(pol="no2").replace(".parquet", ".json")
            meta.write_text(json.dumps({"estaciones": {"sha256": pr.sha256_de(ruta)}}), encoding="utf-8")
            cod, etiquetas, reg = pr.estrato_propietario(r, "no2", ["A", "B", "C", "D"], [0, 0, 1, 2, 3, 3])
            self.assertEqual(etiquetas, ["pública", "empresa", "no informado"])
            self.assertEqual(cod.tolist(), [0, 0, 1, 2, 2, 2])                 # SNIFA: «no informado» (menor 17)
            self.assertEqual(reg["estaciones"], {"pública": 1, "empresa": 1, "no informado": 2})
            with self.assertRaises(SystemExit):                                # una estación sin fila
                pr.estrato_propietario(r, "no2", ["A", "Z"], [0, 1])
            meta.write_text(json.dumps({"estaciones": {"sha256": "0" * 64}}), encoding="utf-8")
            with self.assertRaises(SystemExit):                                # otra huella
                pr.estrato_propietario(r, "no2", ["A"], [0])


class RegimenesTests(unittest.TestCase):
    def test_regla_del_50_por_ciento(self):
        dias = pd.date_range("2017-01-01", "2020-12-31", freq="D")
        anio = dias.year.to_numpy()
        trop = np.where((anio >= 2019) | ((anio == 2018) & (dias.dayofyear > 245)), 1.0, np.nan)  # 2018: < 50 %
        cams = np.where(anio >= 2017, 1.0, np.nan)
        clim = np.where(anio == 2020, 1, 0)
        r = pr.regimenes_calculados(dias, anio, {"no2_trop": trop, "cams_no2": cams, "acag_clim": clim},
                                    {"cams": ["cams_no2"], "tropomi": ["no2_trop", "no2_trop_7d"],
                                     "acag_climatologico": ["acag_clim"]})
        self.assertEqual([(t["id"], t["familias"]) for t in r["tramos"]],
                         [("2017-2018", "cams"), ("2019", "cams+tropomi"), ("2020", "cams+tropomi+acag_climatologico")])
        self.assertLess(r["fraccion_de_dias"]["tropomi"][2018], 0.5)

    def test_cuenta_dias_distintos_y_la_mitad_exacta(self):
        """Ronda 5 de la traducción, menor 11 (R17, «finita en al menos la mitad de los días del año en el panel»): con
        tres estaciones y 24 horas por día, como en el panel, una familia finita en todas las filas de 2 de los 10 días
        de 2021 (144 de 720 filas) no está disponible: cuenta días distintos, no filas. Y una finita en una sola fila de
        exactamente 5 de los 10 días de 2022 (el 50 %) sí lo está: «al menos la mitad»."""
        estaciones, horas_dia = 3, 24
        dias = pd.date_range("2021-01-01", periods=10, freq="D").append(pd.date_range("2022-01-01", periods=10, freq="D"))
        por_dia = estaciones * horas_dia
        k = np.arange(len(dias) * por_dia)
        dia = k // por_dia
        fecha = pd.DatetimeIndex(dias[dia]) + pd.to_timedelta(k % horas_dia, unit="h")
        anio = fecha.year.to_numpy()
        cams = np.where((anio == 2021) & (dia % 10 < 2), 1.0, np.nan)
        trop = np.where((anio == 2022) & (dia % 10 < 5) & (k % por_dia == 0), 1.0, np.nan)
        r = pr.regimenes_calculados(fecha, anio, {"cams_no2": cams, "no2_trop": trop},
                                    {"cams": ["cams_no2"], "tropomi": ["no2_trop"]})
        self.assertEqual(r["fraccion_de_dias"], {"cams": {2021: 0.2, 2022: 0.0}, "tropomi": {2021: 0.0, 2022: 0.5}})
        self.assertEqual([(t["id"], t["familias"]) for t in r["tramos"]], [("2021", "ninguna"), ("2022", "tropomi")])


class AuxiliaresTests(unittest.TestCase):
    def test_estaciones_con_celda(self):
        m = pd.DataFrame({"estacion": ["A", "N"], "nombre": "x", "region_sinca": "RM", "lat": -33.0, "lon": -70.6,
                          "cod_comuna": 13101, "red": "sinca", "grupo": ["actual", "nueva"]})
        s = pd.DataFrame({"estacion": ["SNIFA-X"], "nombre": "x", "region_sinca": "RVIII", "lat": -37.0, "lon": -72.0,
                          "cod_comuna": 8101, "red": "snifa"})
        enl = pd.DataFrame({"estacion": ["A", "N", "SNIFA-X"], "celda": [10, -1, 30]})
        e = pr.estaciones_con_celda_red2(m, s, enl)
        self.assertEqual(list(e["estacion"]), ["A", "SNIFA-X"])
        with self.assertRaises(ValueError):
            pr.estaciones_con_celda_red2(pd.concat([m, m.iloc[:1]]), s, enl)

    def test_calidad_alineada(self):
        panel = pd.DataFrame({"estacion": ["B", "A"], "ts_utc": pd.to_datetime(["2024-01-01 04:00", "2024-01-01 04:00"])})
        obs = pd.DataFrame({"estacion": ["A", "B"], "ts_utc": panel["ts_utc"], "qc": [0, 3], "version": ["v", "snifa"]})
        q = pr.calidad_alineada(panel, obs)
        self.assertEqual(list(q["estacion"]), ["B", "A"])
        self.assertEqual(list(q["qc"]), ["usable_native", "validado"])
        self.assertEqual(list(q["fuente"]), ["snifa", "sinca"])

    def test_filas_estimadas(self):
        s = pd.DataFrame({"contaminante": "no2", "origen": ["ampliacion", "sellado"],
                          "filas_con_observacion": ["2000", "100"],
                          "primera_observacion": ["900101 0100", "2010-01-01"],    # formato SINCA e ISO
                          "ultima_observacion": ["100101 0100", "2010-01-05"]})
        f = pr.filas_estimadas(s)["no2"]
        self.assertAlmostEqual(f["ampliacion"], 1000, delta=10)          # la mitad del lapso cae desde 2000
        self.assertEqual(f["sellado"], 100)

    def test_codigo_v1_con_huella(self):
        """El código v1 que replica o importa el panel, con su huella, desde AP o desde el espejo (ronda 4, mayor 4):
        ``produccion.py`` es «adaptado» (sólo cambia un comentario en el espejo), así que su huella va por repositorio,
        la misma que declara el grupo «adaptados» de config/componentes_compartidos.json."""
        self.assertEqual(pr.verificar_codigo_v1(), pr.huellas_del_repositorio())          # desde donde corre la prueba
        for dep in ("scripts_pipeline/_common.py", "scripts_pipeline/_manifiesto_satelital.py",
                    "scripts_pipeline/_satellite_streaming.py", "scripts_modelo_1km/_red_adicional.py"):
            self.assertIn(dep, pr.HUELLAS_CODIGO_V1)                     # lo que importan _comun_modelo y produccion
        # T12: produccion.py, que importa el armado, con la huella de cada repositorio
        prod = pr.HUELLAS_CODIGO_V1["scripts_modelo_1km/produccion.py"]
        self.assertEqual({k: v[:8] for k, v in prod.items()},
                         {"Air-Pollution": "dd2db2ef", "Air-Pollution-Health-Chile": "e9e18b5a"})
        man = json.loads((V2.parents[1] / "config" / "componentes_compartidos.json").read_text(encoding="utf-8"))
        adaptados = {}
        for g in man.get("grupos") or []:
            if g.get("modo") == "adaptado":
                adaptados.update(g.get("archivos") or {})
        if "scripts_modelo_1km/produccion.py" in adaptados:
            a = adaptados["scripts_modelo_1km/produccion.py"]
            self.assertEqual((a["sha256_canonico"], a["sha256_espejo"]),
                             (prod["Air-Pollution"], prod["Air-Pollution-Health-Chile"]))
        with self.assertRaises(SystemExit):
            pr.verificar_codigo_v1(huellas={"scripts_modelo_1km/_features.py": "0" * 64})

    def test_la_huella_adaptada_es_la_de_cada_repositorio(self):
        """Ronda 4, mayor 4: un archivo con huella por repositorio pasa en cada uno con la suya y se detiene con la del
        otro; un repositorio con otro nombre se detiene."""
        rel = "scripts_modelo_1km/produccion.py"
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            textos = {"Air-Pollution": b"canonico", "Air-Pollution-Health-Chile": b"espejo"}
            huellas = {rel: {n: hashlib.sha256(x).hexdigest() for n, x in textos.items()}}
            for n, x in textos.items():
                (base / n / "scripts_modelo_1km").mkdir(parents=True)
                (base / n / rel).write_bytes(x)
                self.assertEqual(pr.verificar_codigo_v1(base / n, huellas), {rel: huellas[rel][n]})
            (base / "Air-Pollution" / rel).write_bytes(b"espejo")               # la del otro repositorio
            with self.assertRaises(SystemExit):
                pr.verificar_codigo_v1(base / "Air-Pollution", huellas)
            (base / "otro" / "scripts_modelo_1km").mkdir(parents=True)
            (base / "otro" / rel).write_bytes(b"canonico")
            with self.assertRaises(SystemExit):
                pr.verificar_codigo_v1(base / "otro", huellas)

    def test_huella_del_contraste_y_sus_series(self):
        """R6: rige la segunda corrida, en la raíz v2, con su lateral; el lateral registra la primera corrida por su
        huella con sus cambios (aunque no haya ninguno) y leyó las mismas series de NO2 y O3 que lee el panel (mayores
        4, 5, 15 y 31)."""
        with raices_temporales("v2-contraste-") as r:
            raiz = escribir_derivado(destino_red2(r))
            reg, _ = rs.series_con_huella([raiz], r.datos)
            leidas, _ = rs.series_con_huella([raiz], r.datos, ("no2", "o3"))
            carpeta = r.raiz_v2 / "unidades_red2"
            carpeta.mkdir(parents=True)
            csv = carpeta / "contraste_unidades_cams_segunda.csv"
            csv.write_text("a\n")
            sha = uv.sha256_archivo(csv)
            lateral = csv.with_suffix(".json")
            bueno = {"schema": pr.SCHEMA_CONTRASTE, "sha256_csv": sha, "series_leidas": leidas,
                     "primera_corrida": {"sha256": uv.SHA_CONTRASTE_PRIMERA, "cambios": []},
                     "cams": {"archivos": [{"ruta": "contaminantes/CAMS_EAC4/x.nc", "sha256": "c" * 64}]}}
            with self.assertRaises(SystemExit):
                pr.contraste_y_su_huella(csv, None, r, reg)                # obligatoria
            with self.assertRaises(SystemExit):
                pr.contraste_y_su_huella(csv, "0" * 64, r, reg)
            with self.assertRaises(SystemExit):
                pr.contraste_y_su_huella(csv, sha, r, reg)                 # sin lateral: no es una segunda corrida
            lateral.write_text(json.dumps(bueno))
            d = pr.contraste_y_su_huella(csv, sha, r, reg)
            self.assertEqual((d["sha256"], d["lateral_sha256"], d["cambios_frente_a_la_primera"], d["archivos_cams"]),
                             (sha, uv.sha256_archivo(lateral), 0, 1))
            malos = {"otro sha256_csv": {"sha256_csv": "1" * 64}, "otro esquema": {"schema": "otro"},
                     "sin la primera corrida": {"primera_corrida": None},
                     "otra primera corrida": {"primera_corrida": {"sha256": "2" * 64, "cambios": []}},
                     "sin la lista de cambios": {"primera_corrida": {"sha256": uv.SHA_CONTRASTE_PRIMERA}},
                     "otras raíces": {"series_leidas": {**leidas, "raices": ["derived/x"]}},
                     "sin series": {"series_leidas": {**leidas, "series": []}},
                     "otra versión": {"series_leidas": {**leidas, "series": [{**leidas["series"][0], "version": "v0"}]
                                                        + leidas["series"][1:]}},
                     "sólo NO2": {"series_leidas": {**leidas, "contaminantes": ["no2"]}},
                     # quinta revisión, menor 7: el lateral sin los archivos CAMS o sin su sha256 no rige
                     "sin archivos CAMS": {"cams": {"archivos": []}},
                     "sin cams": {"cams": None},
                     "sin sha256": {"cams": {"archivos": [{"ruta": "contaminantes/CAMS_EAC4/x.nc"}]}}}
            for nombre, cambio in malos.items():
                lateral.write_text(json.dumps({**bueno, **cambio}))
                with self.subTest(nombre), self.assertRaises(SystemExit) as e:
                    pr.contraste_y_su_huella(csv, sha, r, reg)
                if "CAMS" in nombre or "cams" in nombre or "sha256" == nombre.split()[-1]:
                    self.assertIn("archivos CAMS", str(e.exception))
            lateral.write_text(json.dumps(bueno))
            # Menor 7 (cuarta revisión): sólo el par de nombre fijo; otro nombre o una subcarpeta de unidades_red2/, no,
            # aunque traiga un lateral hecho a mano coherente consigo mismo.
            for otro in (carpeta / "otra.csv", carpeta / "a_mano" / "otra.csv",
                         carpeta / "a_mano" / "contraste_unidades_cams_segunda.csv"):
                otro.parent.mkdir(parents=True, exist_ok=True)
                otro.write_text("b\n")
                otro.with_suffix(".json").write_text(json.dumps({**bueno, "sha256_csv": uv.sha256_archivo(otro)}))
                with self.subTest(otro=str(otro.relative_to(carpeta))), self.assertRaises(SystemExit) as e:
                    pr.contraste_y_su_huella(otro, uv.sha256_archivo(otro), r, reg)
                self.assertIn("escritura única", str(e.exception))
            # El derivado se rearma (otros archivos, otras versiones): la segunda corrida ya no es la de esas series.
            import shutil
            shutil.rmtree(raiz)
            escribir_derivado(raiz, valores=5.0)
            rearmado, _ = rs.series_con_huella([raiz], r.datos)
            self.assertNotEqual(rearmado["huella_series"], reg["huella_series"])
            with self.assertRaises(SystemExit):
                pr.contraste_y_su_huella(csv, sha, r, rearmado)
            fuera = r.raiz_v2.parent / "contraste_unidades_cams.csv"           # la primera corrida, fuera de la raíz v2
            fuera.write_text("a\n")
            fuera.with_suffix(".json").write_text(json.dumps(bueno))
            with self.assertRaises(SystemExit):
                pr.contraste_y_su_huella(fuera, sha, r, reg)

    def test_el_armado_rechaza_la_primera_corrida(self):
        """Cuarta revisión, menor 28: la regla de unidades del armado (unidades_del_armado) rechaza la primera corrida por
        su huella antes de leer nada, aunque el CSV esté donde está la segunda."""
        from unittest import mock
        with raices_temporales("v2-unidades-") as r:
            csv = r.raiz_v2 / "unidades_red2" / pr.NOMBRES_CONTRASTE[0]
            csv.parent.mkdir(parents=True)
            csv.write_text("estacion,contaminante,grupo,rotulo,unidad_que_indica\n")
            sha = uv.sha256_archivo(csv)
            with mock.patch.object(uv, "SHA_CONTRASTE_PRIMERA", sha), self.assertRaises(SystemExit) as e:
                pr.unidades_del_armado(r, csv, sha, pd.DataFrame({"estacion": ["X"]}))
            self.assertIn("no la primera", str(e.exception))

    def test_corrida_repetida_del_derivado(self):
        """Cuarta revisión, menores 5 y 32: si el derivado se vuelve a correr sin cambios después del reloj (el
        preparador reabre las mismas versiones en otra corrida), el armado acepta el reloj, porque las dos corridas
        terminaron y publicaron las mismas versiones que registra el reloj; una corrida sin terminar o con otras
        versiones, no."""
        import red_ampliada_v2 as ra
        from unittest import mock
        confirmada = lambda repo, rutas: {k: "rastreado" for k in rutas}      # noqa: E731
        with mock.patch.object(ra, "LISTA_CERRADA", {}), raices_temporales("v2-corrida-repetida-") as r:
            datos_red2(r.datos)
            raiz = escribir_derivado(destino_red2(r))
            resumen, _, _ = rs.ejecutar_reloj(r, [raiz], cfg={"red_de_monitores": {}}, estado=confirmada)
            primera = resumen["derivado"]["corrida"]
            prog = json.loads((raiz / "_runs" / primera / "progreso.json").read_text(encoding="utf-8"))
            repetida = raiz / "_runs" / "20261028T000000Z-red2"
            repetida.mkdir()
            (repetida / "progreso.json").write_text(json.dumps({**prog, "results": [
                {**x, "status": "reused"} for x in prog["results"]]}))
            (repetida / "plan.json").write_text(json.dumps(plan_de_prueba()))    # la escribió derivado_red2_v2
            self.assertEqual(rs.ejecutar_reloj(r, [raiz], cfg={"red_de_monitores": {}}, estado=confirmada)[2],
                             "sin_cambios")                                  # el reloj no cambia (escritura única)
            reg, series_d = rs.series_con_huella([raiz], r.datos)
            import derivado_red2_v2 as dr
            derivado = dr.exigir_derivado_completo([raiz], series_d, r.datos, "prueba")
            self.assertEqual(derivado["corrida"], repetida.name)              # la última es la repetida
            maestro = ra.maestro_red2(r.datos)
            region = dict(zip(maestro["estacion"], maestro["region_sinca"]))
            politica, sha_pol = rs.leer_politica_con_huella()
            ver = r.raiz_v2 / rs.NOMBRE_SALIDA / "veredictos.parquet"
            args = (ver, r, reg, series_d, region, politica, sha_pol, None, repetida.name)
            with self.assertRaises(SystemExit):                              # sin la raíz no se puede comparar
                pr.reloj_y_su_huella(*args)
            _, info, _ = pr.reloj_y_su_huella(*args, raiz_derivado=raiz)
            self.assertEqual((info["derivado"]["corrida"], info["corrida_del_armado"], info["corrida_equivalente"]),
                             (primera, repetida.name, True))
            for nombre, cambio in (("sin terminar", {"status": "running"}),
                                   ("otras versiones", {"results": prog["results"][:-1]})):
                (repetida / "progreso.json").write_text(json.dumps({**prog, **cambio}))
                with self.subTest(nombre), self.assertRaises(SystemExit):
                    pr.reloj_y_su_huella(*args, raiz_derivado=raiz)

    def test_reloj_de_su_carpeta_y_vuelto_a_calcular(self):
        """Mayor 2 (y menores 16, 17 y 18): el panel acepta sólo los veredictos de la carpeta de escritura única del
        reloj, con su esquema, su huella de contenido, la política que lee el panel, la zona de cada fila, la misma
        base de zonas y la misma corrida del derivado, y sólo si la tabla es la que vuelve a dar verificar_red con
        las series."""
        import red_ampliada_v2 as ra
        from unittest import mock
        confirmada = lambda repo, rutas: {k: "rastreado" for k in rutas}      # noqa: E731
        with mock.patch.object(ra, "LISTA_CERRADA", {}), raices_temporales("v2-reloj-panel-") as r:
            datos_red2(r.datos)
            raiz = escribir_derivado(destino_red2(r))
            resumen, tabla, estado = rs.ejecutar_reloj(r, [raiz], cfg={"red_de_monitores": {}}, estado=confirmada)
            self.assertEqual(estado, "escrito")
            reg, series_d = rs.series_con_huella([raiz], r.datos)
            maestro = ra.maestro_red2(r.datos)
            region = dict(zip(maestro["estacion"], maestro["region_sinca"]))
            politica, sha_pol = rs.leer_politica_con_huella()
            ver = r.raiz_v2 / rs.NOMBRE_SALIDA / "veredictos.parquet"
            ruta_res = ver.with_name("resumen.json")
            corrida = resumen["derivado"]["corrida"]
            argumentos = (r, reg, series_d, region, politica, sha_pol)
            t, info, evaluadas = pr.reloj_y_su_huella(ver, *argumentos, None, corrida)
            self.assertEqual((info["convencion_civil"], info["conteos"]), ("fin", {"solo_fin": 2, "solo_inicio_mas_1h": 1}))
            self.assertEqual((info["veredictos_sha256"], info["resumen_sha256"]),
                             (uv.sha256_archivo(ver), uv.sha256_archivo(ruta_res)))
            self.assertEqual(evaluadas, {("C1", "no2"), ("C2", "pm25"), ("F1", "pm25"), ("I1", "o3")})
            self.assertEqual(info["zonas_horarias"]["conversion"]["biblioteca"], "zoneinfo")
            self.assertEqual(info["horas_especiales_fijadas"]["sha256"], rs.HORAS_ESPECIALES["sha256"])
            self.assertEqual((info["limite_sin_transiciones"]["n"], info["limite_sin_transiciones"]["convencion"]),
                             (0, "fin"))
            with mock.patch.object(rs, "HORAS_ESPECIALES", {**rs.HORAS_ESPECIALES, "sha256": "0" * 64}), \
                    self.assertRaises(SystemExit) as e:                    # la base del panel, no la fijada
                pr.reloj_y_su_huella(ver, *argumentos, None, corrida)
            self.assertIn("base de zonas", str(e.exception))
            self.assertEqual(pr.reloj_y_su_huella(ver, *argumentos, "fin", corrida)[1]["convencion_civil"], "fin")
            with self.assertRaises(SystemExit):
                pr.reloj_y_su_huella(ver, *argumentos, "inicio_mas_1h", corrida)   # contradecir, no
            with self.assertRaises(SystemExit):
                pr.reloj_y_su_huella(ver, *argumentos, None, "otra-red2")          # otra corrida del derivado
            with self.assertRaises(SystemExit):
                pr.reloj_y_su_huella(ver, r, reg, series_d, region, politica, "0" * 64, None, corrida)  # otra política
            original = json.loads(ruta_res.read_text(encoding="utf-8"))

            def par(destino: Path, tabla_nueva: pd.DataFrame, **cambios) -> Path:
                """Un par veredictos.parquet + resumen.json hecho a mano y coherente consigo mismo."""
                destino.mkdir(parents=True, exist_ok=True)
                for q in (destino / "veredictos.parquet", destino / "resumen.json"):
                    if q.exists():
                        os.chmod(q, 0o644)
                tabla_nueva.to_parquet(destino / "veredictos.parquet", index=False)
                hecho = {**original, "sha256_veredictos": uv.sha256_archivo(destino / "veredictos.parquet"),
                         "huella_veredictos_contenido": hashlib.sha256(tabla_nueva.to_csv(index=False).encode())
                         .hexdigest(), "convencion_civil": rs.elegir_convencion(tabla_nueva), **cambios}
                (destino / "resumen.json").write_text(json.dumps(hecho))
                return destino / "veredictos.parquet"

            editada = tabla.copy()
            editada.loc[editada["estacion"].isin(["C1", "C2"]), "veredicto_fin"] = "reloj_fijo_parcial"
            self.assertEqual(rs.elegir_convencion(editada)["conteos"], {"solo_fin": 0, "solo_inicio_mas_1h": 1})
            # una tabla editada en otra carpeta, con un resumen hecho a mano que copia raíces y series: no pasa
            with self.assertRaises(SystemExit):
                pr.reloj_y_su_huella(par(r.raiz_v2.parent / "otra", editada), *argumentos, None, corrida)
            bytes_ver, bytes_res = ver.read_bytes(), ruta_res.read_bytes()
            zona_mala = tabla.assign(zona_iana="America/Punta_Arenas")
            casos = {"tabla editada en su carpeta": (editada, {}),
                     "sin una serie (C1)": (tabla[tabla["estacion"] != "C1"].reset_index(drop=True), {}),
                     "otra zona en las filas": (zona_mala, {}),
                     "otro esquema": (tabla, {"schema": "otro"}),
                     "otra política": (tabla, {"politica_temporal_sha256": "0" * 64}),
                     "otra base de zonas": (tabla, {"zonas_horarias": {**original["zonas_horarias"],
                                                                       "huella_horas_especiales": "0" * 64}}),
                     "otra huella de contenido": (tabla, {"huella_veredictos_contenido": "0" * 64}),
                     "subconjunto de años": (tabla, {"anios": [2023, 2023]}),
                     "subconjunto de contaminantes": (tabla, {"contaminantes": ["pm25"]}),
                     "subconjunto de series": (tabla, {"series_registradas": reg["series"][:2]}),
                     "otra versión": (tabla, {"series_registradas": [{**reg["series"][0], "version": "v0"}]
                                              + reg["series"][1:]}),
                     "otra raíz": (tabla, {"raices": ["derived/otra"]}),
                     "sin la corrida del derivado": (tabla, {"derivado": None}),
                     "otro límite de R7": (tabla, {"limite_sin_transiciones": {
                         **original["limite_sin_transiciones"],
                         "unidades_junto_a_civil": [{"estacion": "F1", "contaminante": "pm25", "anio": 2015,
                                                     "zona_iana": "America/Santiago", "vecinos_hora_civil": [2016]}]}}),
                     "sin el límite de R7": (tabla, {"limite_sin_transiciones": None})}
            for nombre, (tb, cambios) in casos.items():
                par(ver.parent, tb, **cambios)
                with self.subTest(nombre), self.assertRaises(SystemExit):
                    pr.reloj_y_su_huella(ver, *argumentos, None, corrida)
                for q, b in ((ver, bytes_ver), (ruta_res, bytes_res)):
                    os.chmod(q, 0o644)
                    q.write_bytes(b)
            self.assertEqual(pr.reloj_y_su_huella(ver, *argumentos, None, corrida)[1]["conteos"],
                             {"solo_fin": 2, "solo_inicio_mas_1h": 1})

    def test_el_panel_rechaza_una_raiz_parcial(self):
        """Mayor 1 y 10: aunque reloj y panel reciban la misma raíz parcial, el armado se detiene antes de escribir
        nada: el conjunto estación × contaminante no es el de la red 2."""
        import red_ampliada_v2 as ra
        from types import SimpleNamespace
        from unittest import mock
        confirmada = lambda repo, rutas: {k: "rastreado" for k in rutas}      # noqa: E731
        parcial = {k: v for k, v in RELOJES.items() if k[0] in ("F1", "I1")}
        with mock.patch.object(ra, "LISTA_CERRADA", {}), raices_temporales("v2-ejecutar-") as r:
            datos_red2(r.datos)
            raiz = escribir_derivado(destino_red2(r), parcial)
            tesela = r.datos / "contaminantes" / pr.CATALOGO_MAIAC / "tile=h11v10" / "pixeles.parquet"
            tesela.parent.mkdir(parents=True)
            tesela.write_bytes(b"tile")
            vieja = (pr.utc(pr.CORTE_INSUMOS_UTC) - pd.Timedelta(days=50)).timestamp()
            os.utime(tesela, (vieja, vieja))
            pr.registrar_catalogo_maiac(r, r.datos, cfg={"red_de_monitores": {}}, estado=confirmada)
            inv = pd.DataFrame({"fuente_registro": ["registro_catalogo_maiac (T5): fecha del archivo"]})
            args = SimpleNamespace(derivado=[raiz], contraste=r.raiz_v2 / "unidades_red2" / "x.csv",
                                   contraste_sha256="0" * 64, veredictos=r.raiz_v2 / rs.NOMBRE_SALIDA / "v.parquet",
                                   convencion_civil=None)
            with self.assertRaises(SystemExit) as e:
                pr.ejecutar(r, inv, args, cfg={"red_de_monitores": {}}, estado=confirmada)
            self.assertIn("faltan 2", str(e.exception))
            self.assertEqual(sorted(q.name for q in (r.raiz_v2 / "insumos_red2").iterdir()), [pr.NOMBRE_REGISTRO_MAIAC])
            self.assertFalse((r.raiz_v2 / "paneles").exists())

    def test_el_panel_rechaza_un_derivado_parcial(self):
        """Ronda 3 de la traducción, mayor (el caso del revisor), y ronda 4, menores 7, 8 y 20: con versiones
        publicadas con ``until``, con ``since``, con un subconjunto de sus fuentes, con una fuente de más, repetida, con
        otra huella o con otro «hasta», o con los ``inputs`` del completo y el contenido recortado, el armado se detiene
        antes de escribir nada, aunque el conjunto estación × contaminante y las versiones sean las de la última
        corrida; y ``exigir_derivado_completo`` se detiene mostrando la diferencia con la lista cerrada (T4, R4, R2).
        Ronda 5, menores 2 y 4: también con filas pasadas de observaciones.parquet a solapamientos.parquet (con
        statistics del completo o al día) y con una versión que la última corrida no publicó
        (``version_que_la_corrida_no_publico``)."""
        import derivado_red2_v2 as dr
        import red_ampliada_v2 as ra
        from types import SimpleNamespace
        from unittest import mock
        from test_reloj_sinca_v2 import DERIVADOS_PARCIALES
        confirmada = lambda repo, rutas: {k: "rastreado" for k in rutas}      # noqa: E731
        for nombre, ajustar, mensaje, _ in DERIVADOS_PARCIALES:
            with self.subTest(nombre), mock.patch.object(ra, "LISTA_CERRADA", {}), \
                    raices_temporales("v2-ejecutar-parcial-") as r:
                datos_red2(r.datos)
                raiz = escribir_derivado(destino_red2(r), ajustar=ajustar)
                _, series_d = rs.series_con_huella([raiz], r.datos)
                with self.assertRaises(SystemExit) as e:                     # lo que hacía el revisor
                    dr.exigir_derivado_completo([raiz], series_d, r.datos, "panel_red2_v2")
                self.assertIn(mensaje, str(e.exception))
                tesela = r.datos / "contaminantes" / pr.CATALOGO_MAIAC / "tile=h11v10" / "pixeles.parquet"
                tesela.parent.mkdir(parents=True)
                tesela.write_bytes(b"tile")
                vieja = (pr.utc(pr.CORTE_INSUMOS_UTC) - pd.Timedelta(days=50)).timestamp()
                os.utime(tesela, (vieja, vieja))
                pr.registrar_catalogo_maiac(r, r.datos, cfg={"red_de_monitores": {}}, estado=confirmada)
                inv = pd.DataFrame({"fuente_registro": ["registro_catalogo_maiac (T5): fecha del archivo"]})
                args = SimpleNamespace(derivado=[raiz], contraste=r.raiz_v2 / "unidades_red2" / "x.csv",
                                       contraste_sha256="0" * 64, veredictos=r.raiz_v2 / rs.NOMBRE_SALIDA / "v.parquet",
                                       convencion_civil=None)
                with self.assertRaises(SystemExit) as e:
                    pr.ejecutar(r, inv, args, cfg={"red_de_monitores": {}}, estado=confirmada)
                self.assertIn("lista cerrada", str(e.exception))
                self.assertIn(mensaje, str(e.exception))
                self.assertEqual(sorted(q.name for q in (r.raiz_v2 / "insumos_red2").iterdir()),
                                 [pr.NOMBRE_REGISTRO_MAIAC])
                self.assertFalse((r.raiz_v2 / "paneles").exists())
        self.version_que_la_corrida_no_publico()

    def version_que_la_corrida_no_publico(self):
        """Ronda 5 de la traducción, menor 4 (el caso del revisor): junto a la versión de C1 de NO2 que publicó la
        última corrida, otra versión auténtica que la corrida no publicó (con las fuentes completas, sin ventana, los
        conteos correctos y un created_utc posterior, la que elige version_sinca). El armado se detiene con «no tienen
        la versión que publicó la última corrida» antes de escribir nada."""
        import red_ampliada_v2 as ra
        from types import SimpleNamespace
        from unittest import mock
        confirmada = lambda repo, rutas: {k: "rastreado" for k in rutas}      # noqa: E731
        with mock.patch.object(ra, "LISTA_CERRADA", {}), raices_temporales("v2-ejecutar-plantada-") as r:
            datos_red2(r.datos)
            raiz = escribir_derivado(destino_red2(r))
            plantada = plantar_version(raiz, "C1", "no2")
            elegida = [s for s in rs.series_del_derivado([raiz], rs.CONTAMINANTES_SINCA)
                       if (s["estacion"], s["contaminante"]) == ("C1", "no2")][0]["ruta"].parent
            self.assertEqual(elegida, plantada)                              # la que elige version_sinca
            registrar_maiac_de_prueba(r, confirmada)
            inv = pd.DataFrame({"fuente_registro": ["registro_catalogo_maiac (T5): fecha del archivo"]})
            args = SimpleNamespace(derivado=[raiz], contraste=r.raiz_v2 / "unidades_red2" / "x.csv",
                                   contraste_sha256="0" * 64, veredictos=r.raiz_v2 / rs.NOMBRE_SALIDA / "v.parquet",
                                   convencion_civil=None)
            with self.assertRaises(SystemExit) as e:
                pr.ejecutar(r, inv, args, cfg={"red_de_monitores": {}}, estado=confirmada)
            self.assertIn("no tienen la versión que publicó la última corrida", str(e.exception))
            self.assertIn("C1:no2", str(e.exception))
            self.assertEqual(sorted(q.name for q in (r.raiz_v2 / "insumos_red2").iterdir()), [pr.NOMBRE_REGISTRO_MAIAC])
            self.assertFalse((r.raiz_v2 / "paneles").exists())

    def test_la_serie_se_lee_con_la_huella_registrada(self):
        """Ronda 5 de la traducción, menor 3 (el caso del revisor): el armado registra el sha256 de cada serie al
        principio (series_con_huella) y lee sus observaciones horas después, tras la copia congelada.
        ``observaciones_desde_derivado`` lee cada ``observaciones.parquet`` desde los bytes cuyo sha256 es el registrado:
        si la serie se reemplazó entre el registro y la lectura (C2 de PM2,5, recortada), el armado se detiene antes de
        publicar ningún panel; con la huella del archivo nuevo, lo lee. ``ejecutar`` le pasa las huellas registradas."""
        import inspect
        import red_ampliada_v2 as ra
        from unittest import mock
        with mock.patch.object(ra, "LISTA_CERRADA", {}), raices_temporales("v2-panel-huella-") as r:
            datos_red2(r.datos)
            raiz = escribir_derivado(destino_red2(r))
            reg, series_d = rs.series_con_huella([raiz], r.datos)
            huellas = rs.huellas_de(reg)
            q = carpeta_de_version(raiz, "C2", "pm25") / "observaciones.parquet"
            df = pd.read_parquet(q)
            df[(df["ts_local"] >= pd.Timestamp("2023-04-10")) & (df["ts_local"] < pd.Timestamp("2023-09-01"))] \
                .assign(qc_observacion="validado").to_parquet(q)               # después de registrar su huella
            con_celda = pd.DataFrame({"estacion": ["F1", "C2"], "celda": [1, 2], "lat": [-33.4, -33.5],
                                      "lon": [-70.6, -70.7]})
            evaluadas = {(s["estacion"], s["contaminante"]) for s in series_d}
            argumentos = ("pm25", series_d, {("C2", "pm25"): 1.0}, {}, {"F1": "RM", "C2": "RM"}, rs.leer_politica(),
                          Path("x"), con_celda, "fin", evaluadas, {("C2", "pm25", 2023), ("F1", "pm25", 2023)})
            with self.assertRaises(SystemExit) as e:
                pr.observaciones_desde_derivado(*argumentos, huellas=huellas)
            self.assertIn("C2:pm25", str(e.exception))
            self.assertIn("cambió después de registrar su huella", str(e.exception))
            nueva = {**huellas, ("C2", "pm25"): hashlib.sha256(q.read_bytes()).hexdigest()}
            _, info, _ = pr.observaciones_desde_derivado(*argumentos, huellas=nueva)
            self.assertEqual(info["series_que_entran"], 1)
        fuente = inspect.getsource(pr.ejecutar)
        self.assertIn("huellas=rs.huellas_de(reg_series)", fuente)
        self.assertIn("huellas=rs.huellas_de(series)", inspect.getsource(pr.reloj_y_su_huella))

    def test_serie_sin_veredicto_detiene(self):
        """Menor 16: una serie del derivado que el reloj no registró, o un año con 720 etiquetas o más sin fila en la
        tabla del reloj, detiene el armado; una serie sin año evaluable sigue la regla general y queda contada."""
        with tempfile.TemporaryDirectory() as tmp:
            def serie(est, etiquetas_locales):
                c = Path(tmp) / f"estacion={est}" / "contaminante=pm25" / "version=v1"
                c.mkdir(parents=True)
                n = len(etiquetas_locales)
                pd.DataFrame({"ts_local": pd.to_datetime(etiquetas_locales), "obs": 1.0 + np.arange(n) % 97,
                              "qc_observacion": ["validado"] * n, "seleccionada": [True] * n}).to_parquet(
                    c / "observaciones.parquet")
                return {"estacion": est, "contaminante": "pm25", "ruta": c / "observaciones.parquet"}
            corta = serie("A1", ["2020-01-01 10:00"])
            larga = serie("B1", list(etiquetas(2023, "fijo")[0]))
            con_celda = pd.DataFrame({"estacion": ["A1", "B1"], "celda": [1, 2], "lat": [-33.4, -35.0],
                                      "lon": [-70.6, -71.0]})
            fijo = ("pm25", [corta, larga], {("A1", "pm25"): 1.0, ("B1", "pm25"): 1.0},
                    {("B1", "pm25"): {2023: "reloj_fijo"}}, {"A1": "RM", "B1": "RM"}, rs.leer_politica(),
                    Path(tmp) / "x", con_celda, "inicio_mas_1h")
            todas = {("A1", "pm25"), ("B1", "pm25")}
            huellas = {(s["estacion"], s["contaminante"]): hashlib.sha256(s["ruta"].read_bytes()).hexdigest()
                       for s in (corta, larga)}
            with self.assertRaises(SystemExit):                              # A1 no la registró el reloj
                pr.observaciones_desde_derivado(*fijo, evaluadas={("B1", "pm25")}, con_fila={("B1", "pm25", 2023)},
                                                huellas=huellas)
            with self.assertRaises(SystemExit) as e:                         # 2023 de B1 sin fila en la tabla
                pr.observaciones_desde_derivado(*fijo, evaluadas=todas, con_fila=set(), huellas=huellas)
            self.assertIn("B1 pm25", str(e.exception))
            with self.assertRaises(ValueError):                              # sin las huellas, no lee
                pr.observaciones_desde_derivado(*fijo, evaluadas=todas, con_fila={("B1", "pm25", 2023)})
            obs, info, _ = pr.observaciones_desde_derivado(*fijo, evaluadas=todas, con_fila={("B1", "pm25", 2023)},
                                                           huellas=huellas)
            self.assertEqual(info["reloj_civil"]["series_sin_anio_evaluable"], ["A1:pm25"])
            self.assertEqual(obs["estacion"].nunique(), 2)
            self.assertEqual(pr.anios_evaluables(etiquetas(2023, "fijo")[0]), [2023])

    def test_ejecutar_sin_registro_maiac_se_detiene(self):
        from types import SimpleNamespace
        with raices_temporales("v2-ejecutar-") as r:
            args = SimpleNamespace(derivado=[Path("x")], contraste=Path("x.csv"), contraste_sha256="0" * 64,
                                   veredictos=Path("v.parquet"), convencion_civil=None)
            confirmada = lambda repo, rutas: {k: "rastreado" for k in rutas}      # noqa: E731
            # Menor 39: un inventario hecho con el registro de T5 y un registro que después falta en la raíz v2.
            for fuente in ("manifiestos mensuales", "registro_catalogo_maiac (T5): fecha del archivo"):
                inv = pd.DataFrame({"fuente_registro": [fuente]})
                with self.subTest(fuente), self.assertRaises(SystemExit) as e:
                    pr.ejecutar(r, inv, args, cfg={"red_de_monitores": {}}, estado=confirmada)
                self.assertIn("falta el registro de los catálogos MAIAC (T5)", str(e.exception))
            self.assertFalse((r.raiz_v2 / "insumos_red2").exists())
            # Cuarta revisión, menor 14: el registro de T5 está, pero el inventario no se hizo con él.
            tesela = r.datos / "contaminantes" / pr.CATALOGO_MAIAC / "tile=h11v10" / "pixeles.parquet"
            tesela.parent.mkdir(parents=True)
            tesela.write_bytes(b"tile")
            vieja = (pr.utc(pr.CORTE_INSUMOS_UTC) - pd.Timedelta(days=50)).timestamp()
            os.utime(tesela, (vieja, vieja))
            pr.registrar_catalogo_maiac(r, r.datos, cfg={"red_de_monitores": {}}, estado=confirmada)
            for fuente in ("manifiestos mensuales", "sin registro"):
                with self.subTest(con_registro=fuente), self.assertRaises(SystemExit) as e:
                    pr.ejecutar(r, pd.DataFrame({"fuente_registro": [fuente]}), args, cfg={"red_de_monitores": {}},
                                estado=confirmada)
                self.assertIn("el inventario no se hizo con el registro de los catálogos MAIAC (T5)", str(e.exception))
            self.assertEqual(sorted(q.name for q in (r.raiz_v2 / "insumos_red2").iterdir()), [pr.NOMBRE_REGISTRO_MAIAC])

    def test_tropomi_por_fecha_limitable(self):
        nombres = {2020: "S5P_OFFL_L2__NO2____20200105T165015_20200105T183145_11111_01_010302_20200107T000000.chile.nc",
                   2024: "S5P_OFFL_L2__NO2____20241205T165015_20241205T183145_22222_03_020800_20241207T000000.chile.nc"}
        with tempfile.TemporaryDirectory() as tmp:
            cont = Path(tmp)
            (cont / "T" / "raw").mkdir(parents=True)
            (cont / "T" / "ev").mkdir()
            vieja = (pr.utc(pr.CORTE_INSUMOS_UTC) - pd.Timedelta(days=80)).timestamp()
            for n in nombres.values():
                (cont / "T" / "raw" / n).write_bytes(b"x")
                os.utime(cont / "T" / "raw" / n, (vieja, vieja))
            corte = pr.utc(pr.CORTE_INSUMOS_UTC)
            todas = pr.inventario_por_eventos(cont, "tropomi_no2", "T/raw", "T/ev", "*.nc", corte, True)
            self.assertEqual(sum(f["entra"] for f in todas), 2)                 # T11: TROPOMI_MTIME_ANIOS = None
            hasta_2022 = pr.inventario_por_eventos(cont, "tropomi_no2", "T/raw", "T/ev", "*.nc", corte, True,
                                                   anios_mtime=(2018, 2022))
            self.assertEqual({pr.anio_de_orbita(f["clave"]): f["entra"] for f in hasta_2022}, {2020: True, 2024: False})
            self.assertIsNone(pr.TROPOMI_MTIME_ANIOS)
            # T11: el anexo lista por año lo que entra por fecha de modificación
            inv = pd.DataFrame(todas, columns=pr.COLUMNAS_INVENTARIO)
            m = pr.resumen_inventario(inv)["tropomi_no2"]["por_fecha_de_modificacion"]
            self.assertEqual((m["entran"], m["por_anio"]), (2, {"2020": 1, "2024": 1}))
            self.assertRegex(m["huella_lista"], r"^[0-9a-f]{64}$")
        self.assertIn("T11", Path(pr.__file__).read_text(encoding="utf-8"))

    def test_los_archivos_de_la_red_2_en_paneles(self):
        """Quinta revisión, menor 23: CAMINO_518 nombra uno por uno los archivos que el armado publica en paneles/ (no la
        carpeta, que guarda la bandera de la red original)."""
        import red_ampliada_v2 as ra
        publicados = {*(pr.NOMBRE_PANEL.format(pol=p) for p in pr.CONTAMINANTES_PANEL),
                      *(pr.NOMBRE_PANEL.format(pol=p).replace(".parquet", ".json") for p in pr.CONTAMINANTES_PANEL),
                      *(pr.NOMBRE_CALIDAD.format(pol=p) for p in pr.CONTAMINANTES_PANEL),
                      *(pr.NOMBRE_RELOJ.format(pol=p) for p in pr.CONTAMINANTES_PANEL),
                      *(pr.NOMBRE_OBS.format(pol=p) for p in pr.CONTAMINANTES_PANEL + (pr.RAMA_O3,)),
                      pr.NOMBRE_OBS_O3.replace(".parquet", ".json"), pr.NOMBRE_ESTACIONES, pr.NOMBRE_SATELITES,
                      pr.NOMBRE_REGIMENES}
        self.assertEqual(set(ra.ARCHIVOS_RED2_EN_PANELES), publicados)
        for n in ra.ARCHIVOS_RED2_EN_PANELES:
            self.assertIn(n, ra.CAMINO_518)
        self.assertNotIn("calidad_pm25.parquet", ra.ARCHIVOS_RED2_EN_PANELES)
        for paso in ("--registrar-catalogo-maiac", "--reemplazar --motivo «R8, 518»", "nunca la carpeta entera"):
            self.assertIn(paso, ra.CAMINO_518)

    def armado_sintetico(self, r, cfg, confirmada) -> dict:
        """El armado de punta a punta con datos sintéticos (quinta revisión, mayores 1 y 2): derivado completo, reloj,
        segunda corrida del contraste y registro MAIAC escritos, inventario, argumentos y los dobles del código v1, de
        los satélites y de la réplica del panel. Devuelve {inv, args, parches(**otros), rachas_usadas, prod, lateral}:
        ``parches`` da los ``mock.patch`` de esos dobles; ``otros`` reemplaza o agrega dobles de ``panel_red2_v2`` por
        su nombre."""
        import contextlib
        import types as tipos
        from types import SimpleNamespace
        from unittest import mock
        import contraste_unidades_v2 as cu
        import pliegues_v2 as pv
        import red_ampliada_v2 as ra
        (r.repo.parent / ra.NOMBRE_ESPEJO).mkdir()                           # el espejo, hermano del repositorio
        datos_red2(r.datos)
        raiz = escribir_derivado(destino_red2(r))
        rs.ejecutar_reloj(r, [raiz], cfg=cfg, estado=confirmada)
        leidas, _ = rs.series_con_huella([raiz], r.datos, ("no2", "o3"))
        tabla_c = pd.DataFrame({"estacion": ["C1"], "contaminante": ["no2"], "decision": ["ppb"]})
        lateral, _ = cu.publicar_una_vez(r, tabla_c, {
            "schema": cu.SCHEMA, "series_leidas": leidas,
            "cams": {"archivos": [{"ruta": "contaminantes/CAMS_EAC4/x.nc", "sha256": "c" * 64}]},
            "primera_corrida": {"sha256": uv.SHA_CONTRASTE_PRIMERA, "cambios": []}}, cfg=cfg, estado=confirmada)
        reg_maiac = registrar_maiac_de_prueba(r, confirmada)
        inv = pr.inventario_insumos(r.datos, registro_maiac=reg_maiac)
        r.grilla_v1.mkdir(parents=True)
        (r.grilla_v1 / "metadata.json").write_text(json.dumps({"archivos": {"enlaces_productos": "e" * 64}}))
        for n in pr.INSUMOS_GRILLA_V1[4:6]:
            pd.DataFrame({"estacion": ["F1", "C1", "C2"], "celda": [1, 2, 3]}).to_parquet(r.grilla_v1 / n)
        celdas = pd.DataFrame({"celda": [1, 2, 3, 4]})
        cm = tipos.SimpleNamespace(cargar_celdas=lambda: celdas, cargar_enlaces=lambda: celdas.assign(maiac_pixel=-1),
                                   celda_de_lonlat=lambda lon, lat, c: np.full(len(lon), 4))
        ft = tipos.SimpleNamespace(cargar_estaticas=lambda: (None, None))
        snifa = pd.DataFrame(columns=["estacion", "nombre", "region_sinca", "lat", "lon", "cod_comuna", "red"])
        ts = pd.Timestamp("2023-03-01 04:00") + pd.to_timedelta(np.arange(3), unit="h")
        rachas_usadas = []

        def obs(pol, series, *a, **k):
            rachas_usadas.append(k.get("marcar_rachas"))
            est = {"pm25": ["F1", "C2"], "no2": ["C1"], "o3": ["I1"]}[pol]
            o = pd.DataFrame({"estacion": np.repeat(est, len(ts)), "ts_utc": np.tile(ts, len(est)), "obs": 1.0,
                              "n": 1, "qc": 0, "version": "v"})
            return o, {"reloj_civil": {}, "duplicados": []}, pd.DataFrame({"estacion": pd.Series(dtype=str)})

        def panel(pol, o, est, sat, ctx, procesos=1):
            df = o[["estacion", "ts_utc"]].copy()
            df["fecha_local"], df["anio"] = pd.Timestamp("2023-03-01"), 2023
            for c in pr.predictores_cerrados(cfg, pol):
                df[c] = 1.0
            return df, {"filas": int(len(df))}
        tabla_u = pd.DataFrame({"estacion": ["F1", "C2", "C1", "I1"], "contaminante": ["pm25", "pm25", "no2", "o3"],
                                "factor": 1.0, "entra": True})
        fichas = pd.DataFrame({"estacion": ["F1"], "id_sinca": ["1"], "propietario": ["x"], "operador": ["x"],
                               "red": ["x"], "calificacion": ["Pública"], "tipo_propietario": ["pública"]})
        args = SimpleNamespace(derivado=[raiz], contraste=r.raiz_v2 / "unidades_red2" / cu.NOMBRES_SALIDA[0],
                               contraste_sha256=lateral["sha256_csv"],
                               veredictos=r.raiz_v2 / rs.NOMBRE_SALIDA / "veredictos.parquet",
                               convencion_civil=None, procesos=1)
        prod = SimpleNamespace(marcar_rachas=pr.rachas_sin_produccion, QC_RACHA=pr.QC_RACHA)
        dobles = {"importar_v1": lambda entorno: (cm, ft, None), "importar_produccion": lambda: prod,
                  "enlaces_estaciones_nuevas": lambda cm_, cg_, nuevas, enl: (
                      pd.DataFrame({"estacion": ["I1"], "celda": [4]}), {"procedimiento": "prueba"}),
                  "unidades_del_armado": lambda *a: (tabla_u, {"contraste_sha256": lateral["sha256_csv"]}),
                  "observaciones_desde_derivado": obs,
                  "satelites_red2": lambda *a, **k: (
                      pd.DataFrame({"celda": [1], "fecha_local": [pd.Timestamp("2023-03-01")]}), {"dias": 1}),
                  "construir_panel_red2": panel,
                  "calidad_alineada": lambda df, o: pd.DataFrame(
                      {"estacion": df["estacion"], "ts_utc": df["ts_utc"], "qc": "validado", "fuente": "sinca"}),
                  "regimenes_calculados": lambda *a, **k: {"tramos": [{"anios": [2023, 2023], "familias": "cams"}]}}

        def parches(**otros):
            pila = contextlib.ExitStack()
            for nombre, doble in {**dobles, **otros}.items():
                pila.enter_context(mock.patch.object(pr, nombre, doble))
            pila.enter_context(mock.patch.object(pv, "leer_estaciones_sinca", lambda r_: None))
            pila.enter_context(mock.patch.object(pv, "leer_estaciones_snifa", lambda r_, s: snifa))
            pila.enter_context(mock.patch.object(ra, "fichas_red2", lambda d: fichas))
            return pila
        return {"inv": inv, "args": args, "parches": parches, "rachas_usadas": rachas_usadas, "prod": prod,
                "lateral": lateral}

    def escrito_por_el_armado(self, r) -> list[str]:
        """Lo que el armado escribe en la raíz v2 (fuera del reloj, la segunda corrida y el registro MAIAC, que la
        prueba escribe antes)."""
        previos = {f"insumos_red2/{pr.NOMBRE_REGISTRO_MAIAC}"}
        return sorted(q.relative_to(r.raiz_v2).as_posix() for d in ("insumos_red2", "grilla", "paneles")
                      if (r.raiz_v2 / d).exists() for q in (r.raiz_v2 / d).rglob("*")
                      if q.is_file() and q.relative_to(r.raiz_v2).as_posix() not in previos)

    def test_ejecutar_registra_la_procedencia(self):
        """Quinta revisión, mayores 1 y 2: el armado, de punta a punta con datos sintéticos (el código v1, los satélites
        y la réplica del panel, simulados), escribe en cada json (los de los paneles y de O3, regimenes_red2.json,
        inventario.json y congelados.json) la procedencia de red_ampliada_v2.traza_red2, y el anexo exige que todos
        los artefactos (también el reloj, la segunda corrida y el registro MAIAC) declaren la misma traducción."""
        from unittest import mock
        import pliegues_red2_v2 as plr
        import red_ampliada_v2 as ra
        confirmada = lambda repo, rutas: {k: "rastreado" for k in rutas}      # noqa: E731
        cfg = {**CFG, "red_de_monitores": {}}
        commit = "c" * 40
        with mock.patch.object(ra, "LISTA_CERRADA", {}), mock.patch.object(ra, "commit_de", lambda repo, rutas=None: commit), \
                raices_temporales("v2-armado-") as r:
            a = self.armado_sintetico(r, cfg, confirmada)
            with a["parches"]():
                self.assertEqual(pr.ejecutar(r, a["inv"], a["args"], cfg=cfg, estado=confirmada), 0)
            propio = hashlib.sha256(Path(pr.__file__).read_bytes()).hexdigest()
            for rel in ("paneles/panel_pm25_red2.json", "paneles/panel_no2_red2.json", "paneles/observaciones_o3_red2.json",
                        "paneles/regimenes_red2.json", "insumos_red2/inventario.json", "insumos_red2/congelados.json"):
                with self.subTest(rel):
                    tr = json.loads((r.raiz_v2 / rel).read_text(encoding="utf-8"))["traza"]
                    for clave in ("git", "codigo", "contrato", "config", "insumos", "bibliotecas", "python", "hilos"):
                        self.assertIn(clave, tr)
                    self.assertEqual(tr["codigo_red2"]["scripts_modelo_1km/v2/panel_red2_v2.py"], propio)
                    self.assertEqual((tr["traduccion"]["commit"], tr["traduccion"]["commit_espejo"]), (commit, commit))
                    self.assertTrue(tr["traduccion"]["compuerta"]["confirmada"])
                    self.assertIn("ratificacion", tr["traduccion"])            # ronda 5, menor 21
            meta = json.loads((r.raiz_v2 / "paneles" / "panel_no2_red2.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["traza"]["insumos"]["resumen_reloj"]["sha256"],
                             uv.sha256_archivo(r.raiz_v2 / rs.NOMBRE_SALIDA / "resumen.json"))
            self.assertEqual(meta["reloj"]["limite_sin_transiciones"]["n"], 0)                  # menor 4
            self.assertEqual(meta["rachas"]["funcion"], "produccion.marcar_rachas")             # T12
            self.assertEqual(a["rachas_usadas"], [a["prod"].marcar_rachas] * 3)  # las de produccion, en los tres
            self.assertEqual(meta["rachas"]["sha256_produccion"],
                             pr.huellas_del_repositorio()["scripts_modelo_1km/produccion.py"])
            anexo = plr.registro_de_la_red_desde_artefactos(r)
            self.assertEqual((anexo["traduccion"]["commit"], len(anexo["traduccion"]["artefactos"])), (commit, 9))
            self.assertEqual(anexo["reloj"]["sin_transiciones_junto_a_civil"], [])
            # un artefacto escrito con otra traducción (un commit nuevo a mitad del armado) detiene el anexo
            q = r.raiz_v2 / "paneles" / "regimenes_red2.json"
            d = json.loads(q.read_text(encoding="utf-8"))
            d["traza"]["traduccion"]["commit"] = "d" * 40
            os.chmod(q, 0o644)
            q.write_text(json.dumps(d), encoding="utf-8")
            with self.assertRaises(SystemExit) as e:
                plr.registro_de_la_red_desde_artefactos(r)
            self.assertIn("misma traducción", str(e.exception))

    def test_las_unidades_se_comprueban_antes_de_escribir(self):
        """Ronda 5 de la traducción, menor 5: la regla de unidades del armado, donde la segunda corrida rige sobre el
        panel (R6, T12 a), se comprueba antes de lo que es de escritura única: con una segunda corrida a la que le falta
        una serie (la parada de ``unidades_v2.unidades_de_series``), ``ejecutar`` se detiene sin escribir
        inventario.json, congelados.json ni los enlaces de las estaciones nuevas, y sin importar el código v1."""
        from unittest import mock
        import red_ampliada_v2 as ra
        confirmada = lambda repo, rutas: {k: "rastreado" for k in rutas}      # noqa: E731
        cfg = {**CFG, "red_de_monitores": {}}

        def sin_la_serie(*a):
            raise ValueError("I1 o3: no está en el contraste de unidades (segunda corrida)")

        def prohibido(*a, **k):
            raise AssertionError("se siguió después de la regla de unidades")
        with mock.patch.object(ra, "LISTA_CERRADA", {}), raices_temporales("v2-armado-unidades-") as r:
            a = self.armado_sintetico(r, cfg, confirmada)
            with a["parches"](unidades_del_armado=sin_la_serie, publicar_inventario=prohibido,
                              congelar_o_retomar=prohibido, importar_v1=prohibido), \
                    self.assertRaises(ValueError) as e:
                pr.ejecutar(r, a["inv"], a["args"], cfg=cfg, estado=confirmada)
            self.assertIn("no está en el contraste de unidades", str(e.exception))
            self.assertEqual(self.escrito_por_el_armado(r), [])
            self.assertFalse((r.raiz_v2 / "insumos_red2" / "inventario.json").exists())

    def test_el_codigo_v1_sin_su_huella_detiene_el_armado(self):
        """Ronda 5 de la traducción, menor 12 (T12, «con su huella fijada»): con una huella del código v1 que no es la del
        archivo (``HUELLAS_CODIGO_V1`` alterado), ``ejecutar`` se detiene en ``verificar_codigo_v1``, antes de
        ``publicar_inventario`` y de ``importar_produccion``, sin escribir nada."""
        from unittest import mock
        import red_ampliada_v2 as ra
        confirmada = lambda repo, rutas: {k: "rastreado" for k in rutas}      # noqa: E731
        cfg = {**CFG, "red_de_monitores": {}}

        def prohibido(*a, **k):
            raise AssertionError("se siguió con el código v1 sin su huella")
        otra = {**pr.HUELLAS_CODIGO_V1, "scripts_modelo_1km/_features.py": "0" * 64}
        with mock.patch.object(ra, "LISTA_CERRADA", {}), raices_temporales("v2-armado-v1-") as r:
            a = self.armado_sintetico(r, cfg, confirmada)
            with a["parches"](publicar_inventario=prohibido, congelar_o_retomar=prohibido, importar_v1=prohibido,
                              importar_produccion=prohibido, HUELLAS_CODIGO_V1=otra), \
                    self.assertRaises(SystemExit) as e:
                pr.ejecutar(r, a["inv"], a["args"], cfg=cfg, estado=confirmada)
            self.assertIn("El código v1 que replica el panel cambió", str(e.exception))
            self.assertIn("scripts_modelo_1km/_features.py", str(e.exception))
            self.assertEqual(self.escrito_por_el_armado(r), [])

    def test_importar_produccion_exige_su_regla(self):
        """Ronda 5 de la traducción, menores 12 y 22 (T12, corrección 2): ``importar_produccion`` se detiene
        (RuntimeError) con un ``produccion`` que activa la red adicional o que trae otro ``QC_RACHA`` que el del panel;
        con los dos como los del panel, lo devuelve."""
        import types as tipos
        from unittest import mock
        for nombre, red, racha, falla in (("red adicional", True, pr.QC_RACHA, True), ("otra racha", False, 12, True),
                                          ("la del panel", False, pr.QC_RACHA, False)):
            falso = tipos.ModuleType("produccion")
            falso.__file__ = str(pr.V1 / "produccion.py")
            falso.RED_ADICIONAL, falso.QC_RACHA = red, racha
            with self.subTest(nombre), mock.patch.object(sys, "path", list(sys.path)), \
                    mock.patch.dict(sys.modules, {"_comun_modelo": tipos.ModuleType("_comun_modelo"), "produccion": falso}):
                if falla:
                    with self.assertRaises(RuntimeError) as e:
                        pr.importar_produccion()
                    self.assertIn("red adicional", str(e.exception))
                else:
                    self.assertIs(pr.importar_produccion(), falso)

    def test_regimenes_comunes(self):
        pm = {"tramos": [{"anios": [2017, 2018], "familias": "cams"}, {"anios": [2019, 2020], "familias": "cams+tropomi"}]}
        no = {"tramos": [{"anios": [2017, 2019], "familias": "cams"}, {"anios": [2020, 2020], "familias": "cams+tropomi"}]}
        c = pr.regimenes_comunes({"pm25": pm, "no2": no})
        self.assertEqual([t["id"] for t in c["tramos"]], ["2017-2018", "2019", "2020"])
        self.assertEqual(c["tramos"][1]["familias_por_contaminante"], {"no2": "cams", "pm25": "cams+tropomi"})
        self.assertFalse(c["iguales_en_los_dos"])
        self.assertTrue(pr.regimenes_comunes({"pm25": pm, "no2": pm})["iguales_en_los_dos"])

    def test_propietarios_registrados(self):
        est = pd.DataFrame({"estacion": ["A", "SNIFA-X"], "red": ["sinca", "snifa"]})
        fichas = pd.DataFrame({"estacion": ["A"], "id_sinca": ["1"], "propietario": ["ENAP"], "operador": ["x"],
                               "red": ["ENAP Biobío"], "calificacion": ["Privada"], "tipo_propietario": ["empresa"]})
        e = pr.estaciones_con_propietario(est, fichas).set_index("estacion")
        self.assertEqual((e.loc["A", "propietario"], e.loc["A", "operador"], e.loc["A", "red_ficha"],
                          e.loc["A", "calificacion"]), ("ENAP", "x", "ENAP Biobío", "Privada"))
        self.assertEqual(e.loc["SNIFA-X", "tipo_propietario"], "no informado")    # sin ficha: T1(3) no la alcanza
        self.assertIn("SNIFA", e.loc["SNIFA-X", "nota_tipo"])
        self.assertEqual(e.loc["A", "nota_tipo"], "")

    def test_listas_cerradas_de_predictores(self):
        self.assertEqual(len(pr.predictores_cerrados(CFG, "pm25")), 70)
        self.assertEqual(len(pr.predictores_cerrados(CFG, "no2")), 69)
        self.assertNotIn("frac_lena", pr.predictores_cerrados(CFG, "pm25"))

    def test_tramos(self):
        self.assertEqual(pr.tramos("2000-01-01", "2000-07-15"),
                         [("2000-01-01", "2000-03-31"), ("2000-04-01", "2000-06-30"), ("2000-07-01", "2000-07-15")])

    def test_periodo_y_corte(self):
        self.assertEqual((pr.DESDE, pr.HASTA), ("2000-01-01", "2026-10-24"))
        corte = pr.utc(pr.CORTE_INSUMOS_UTC)
        self.assertEqual(corte, pd.Timestamp("2026-10-25 03:00", tz="UTC"))
        self.assertEqual(corte.tz_convert("America/Santiago").tz_localize(None), pd.Timestamp("2026-10-25 00:00"))


RECETA = r"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
v2, datos, v1 = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, v2)
import panel_red2_v2 as pr
cm, ft, cg = pr.importar_v1(pr.entorno_lectura(Path(datos), Path(v1)))
import logging
manejadores = list(logging.getLogger().handlers)
prod = pr.importar_produccion()                    # T12: después de importar_v1, con su huella ya comprobada
horas = pd.DataFrame({"estacion": ["A"] * 30 + ["B"] * 30,
                      "ts_utc": list(pd.date_range("2024-01-01", periods=30, freq="h")) * 2,
                      "obs": np.r_[np.full(25, 3.0), np.arange(5.0), np.arange(30.0)]})
rachas_prod = int(prod.marcar_rachas(horas, prod.QC_RACHA)["racha"].sum())
rachas_sin = int(pr.rachas_sin_produccion(horas, pr.QC_RACHA)["racha"].sum())
celdas = pd.DataFrame({"celda": [1, 2, 3, 4], "lat": [-33.005, -33.205, -34.005, -36.005],
                       "lon": [-70.605, -70.605, -70.705, -72.005], "codregion": 13, "cod_comuna": 13101})
productos = ("era5land", "era5blh", "merra2", "cams", "geoscf", "maiac")
enlaces = pd.DataFrame({"celda": [1, 2, 3, 4], **{f"{p}_pixel": -1 for p in productos}})
estaticas = pd.DataFrame({"celda": [1, 2, 3, 4], "elev_m": 500.0, "pendiente_deg": 1.0, "dist_costa_km": 90.0,
                          "frac_lena": 0.1, "vias_km_km2": 2.0, "vias_princ_km_km2": 0.5, "lat": celdas["lat"],
                          "lon": celdas["lon"], "macrozona_cod": 2})
lulc = pd.DataFrame({"celda": [1, 2, 3, 4], "anio": 2023, "lulc_urbano": 0.5, "lulc_cultivo": 0.1, "lulc_bosque": 0.1,
                     "lulc_matorral_pastizal": 0.1, "lulc_desnudo": 0.1, "lulc_agua": 0.05, "lulc_nieve_hielo": 0.05,
                     "pob_dens": [1000.0, 500.0, 200.0, 50.0]})
est = pd.DataFrame({"estacion": ["A", "B", "C"], "celda": [1, 2, 3], "lat": [-33.0, -33.2, -34.0],
                    "lon": [-70.6, -70.6, -70.7], "region_sinca": "RM"})
ts = pd.Timestamp("2023-03-01 04:00") + pd.to_timedelta(np.arange(48), unit="h")
obs = pd.concat([pd.DataFrame({"estacion": e, "ts_utc": ts, "obs": float(k + 1) * 10.0, "n": 1, "version": "v"})
                 for k, e in enumerate(["A", "B", "C"])], ignore_index=True)
sat, meta = pr.satelites_red2(ft, celdas[celdas["celda"].isin([1, 2, 3])].reset_index(drop=True), enlaces, 1,
                              "2023-03-01", "2023-03-03")
df, res = pr.construir_panel_red2("no2", obs, est, sat,
                                  {"ft": ft, "CELDAS": celdas, "ENLACES": enlaces, "ESTATICAS": estaticas,
                                   "LULC": lulc}, 1)
a = df[(df["estacion"] == "A") & (df["ts_utc"] == ts[0])].iloc[0]
print(json.dumps({"columnas": list(df.columns), "filas": int(len(df)), "obs_vec_A": float(a["obs_vec"]),
                  "dist_A": float(a["dist_est_km"]), "hora_local_A": int(a["hora_local"]),
                  "pob_A": float(a["pob_dens"]), "faltantes": len(res["meses_sin_fuente"]),
                  "tipos_float": sorted({str(t) for t in df.dtypes if t.kind == "f"}),
                  "produccion": {"red_adicional": bool(prod.RED_ADICIONAL), "qc_racha": int(prod.QC_RACHA),
                                 "datos_de_la_copia": Path(cm.DATA).resolve() == Path(datos).resolve(),
                                 "manejadores_nuevos": len(logging.getLogger().handlers) - len(manejadores),
                                 "rachas": [rachas_prod, rachas_sin]}}))
"""


# Ronda 5 de la traducción, menores 12 y 22: importar_produccion, de verdad y en un proceso aparte, en tres casos.
RECETA_PRODUCCION = r"""
import json, os, sys
from pathlib import Path
v2, datos, v1, caso = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
sys.path.insert(0, v2)
import panel_red2_v2 as pr
if caso != "sin_importar_v1":
    pr.importar_v1(pr.entorno_lectura(Path(datos), Path(v1)))
    if caso == "red_adicional":
        os.environ["MODELO_1KM_RED_ADICIONAL"] = "1"
        import _red_adicional
        _red_adicional.disponible = lambda: True        # como si estuviera el archivo de la red adicional
    elif caso == "otra_racha":
        os.environ["MODELO_1KM_QC_RACHA"] = "12"
try:
    pr.importar_produccion()
    error = None
except RuntimeError as e:
    error = str(e)
print(json.dumps({"error": error, "cargados": sorted(m for m in ("_comun_modelo", "produccion") if m in sys.modules)}))
"""


class ReplicaPanelTests(unittest.TestCase):
    def test_importar_produccion_en_un_proceso_aparte(self):
        """Ronda 5 de la traducción, menores 12 y 22 (T12, corrección 2): importado de verdad, en un proceso aparte como
        la receta del panel, ``importar_produccion`` se detiene (RuntimeError) sin ``_comun_modelo`` cargado, es decir,
        antes de ``importar_v1`` (y sin llegar a importar produccion.py); con MODELO_1KM_RED_ADICIONAL=1 y la red
        adicional disponible; y con otro MODELO_1KM_QC_RACHA. Raíces de datos vacías: no lee nada."""
        casos = {"sin_importar_v1": ("después de importar_v1", []),
                 "red_adicional": ("red adicional (True)", ["_comun_modelo", "produccion"]),
                 "otra_racha": ("otro QC_RACHA (12", ["_comun_modelo", "produccion"])}
        for caso, (mensaje, cargados) in casos.items():
            with self.subTest(caso), tempfile.TemporaryDirectory() as tmp:
                datos, v1 = Path(tmp) / "datos", Path(tmp) / "v1"
                (datos / "contaminantes").mkdir(parents=True)
                (v1 / "grilla_1km").mkdir(parents=True)
                entorno = {k: v for k, v in os.environ.items() if not k.startswith(("AIR_POLLUTION", "MODELO_1KM"))}
                entorno.update({"PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "1", "AIR_POLLUTION_DATA_ROOT": str(datos),
                                "AIR_POLLUTION_MODELO_1KM_ROOT": str(v1), "MODELO_1KM_RED_ADICIONAL": "0"})
                p = subprocess.run([sys.executable, "-B", "-c", RECETA_PRODUCCION, str(V2), str(datos), str(v1), caso],
                                   env=entorno, capture_output=True, text=True, timeout=600, cwd=tmp)
                self.assertEqual(p.returncode, 0, p.stderr[-3000:])
                r = json.loads(p.stdout.strip().splitlines()[-1])
                self.assertIn(mensaje, r["error"] or "(sin error)")
                self.assertEqual(r["cargados"], cargados)

    def test_construir_panel_con_el_codigo_v1(self):
        with tempfile.TemporaryDirectory() as tmp:
            datos, v1 = Path(tmp) / "datos", Path(tmp) / "v1"
            (datos / "contaminantes").mkdir(parents=True)
            (v1 / "grilla_1km").mkdir(parents=True)
            entorno = {k: v for k, v in os.environ.items() if not k.startswith(("AIR_POLLUTION", "MODELO_1KM"))}
            entorno.update({"PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "1"})
            p = subprocess.run([sys.executable, "-B", "-c", RECETA, str(V2), str(datos), str(v1)], env=entorno,
                               capture_output=True, text=True, timeout=600, cwd=tmp)
            self.assertEqual(p.returncode, 0, p.stderr[-3000:])
            r = json.loads(p.stdout.strip().splitlines()[-1])
        self.assertEqual(r["columnas"], [c for c in COLUMNAS_V1 if c != "frac_lena"])
        self.assertEqual(r["filas"], 144)
        # Vecindario sin la propia estación: núcleo gaussiano de 150 km sobre B (22 km) y C (111 km).
        import duplicados_v2 as dv
        d_b, d_c = dv.haversine_km(-33.0, -70.6, -33.2, -70.6), dv.haversine_km(-33.0, -70.6, -34.0, -70.7)
        w_b, w_c = np.exp(-(d_b / 150) ** 2), np.exp(-(d_c / 150) ** 2)
        self.assertAlmostEqual(r["obs_vec_A"], (20 * w_b + 30 * w_c) / (w_b + w_c), places=3)
        self.assertAlmostEqual(r["dist_A"], float(d_b), places=3)
        self.assertEqual(r["hora_local_A"], 0)                          # 04:00 UTC = 00:00 UTC−4
        self.assertEqual(r["pob_A"], 1000.0)
        self.assertEqual(r["tipos_float"], ["float32"])
        self.assertGreater(r["faltantes"], 0)                           # sin productos en la raíz vacía
        # T12 (ronda 4, menor 16): produccion.py se importa de verdad después de importar_v1, sin efectos nuevos
        self.assertEqual(r["produccion"], {"red_adicional": False, "qc_racha": pr.QC_RACHA, "datos_de_la_copia": True,
                                           "manejadores_nuevos": 0, "rachas": [25, 25]})


if __name__ == "__main__":
    unittest.main()
