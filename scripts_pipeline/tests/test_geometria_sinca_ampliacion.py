"""Pruebas sin red de geometria_sinca_ampliacion.py (requieren geopandas)."""
from __future__ import annotations

import gzip
import hashlib
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
_TMP_DATA = tempfile.TemporaryDirectory()
_ENV_PREVIO = os.environ.get("AIR_POLLUTION_DATA_ROOT")
_PREVIOS = {m: sys.modules.pop(m, None)
            for m in ("_common", "actualizar_geometria_sinca", "geometria_sinca_ampliacion")}
os.environ["AIR_POLLUTION_DATA_ROOT"] = _TMP_DATA.name
sys.path.insert(0, str(SCRIPTS))
try:
    # Raíz de datos temporal: la prueba jamás toca el disco externo.
    env = importlib.import_module("geometria_sinca_ampliacion")
    import geopandas as gpd
    from shapely.geometry import Point, Polygon, box
except ImportError:  # entorno sin geopandas: se omite el módulo
    env = None
finally:
    if _ENV_PREVIO is None:
        os.environ.pop("AIR_POLLUTION_DATA_ROOT", None)
    else:
        os.environ["AIR_POLLUTION_DATA_ROOT"] = _ENV_PREVIO
    for _m, _previo in _PREVIOS.items():
        if _previo is not None:
            sys.modules[_m] = _previo
        elif _m == "_common":
            # Otros módulos de prueba no deben heredar la raíz temporal.
            sys.modules.pop(_m, None)

FICHA = b'<html><table id="tablaGeneral"><tr><th>Comuna</th><td>Playa</td></tr></table></html>'


def _correccion(**extra):
    datos = gzip.compress(FICHA, mtime=0)
    base = {"utm_e": 350205, "utm_n": 7444908, "huso": 19,
            "fuente": "https://sinca.mma.gob.cl/index.php/estacion/index/id/1",
            "detalle": "ficha", "cache_nombre": "T01_ficha.html.gz",
            "sha256": hashlib.sha256(datos).hexdigest(),
            "consultado_utc": "2026-10-24T23:21:00Z", "tipo_documento": "ficha_sinca_html"}
    return base | extra, datos


def _comunas_sinteticas(lon_borde: float):
    """Una comuna cuadrada en 3857 cuyo borde oeste está en ``lon_borde``."""
    cuadro = gpd.GeoSeries([box(lon_borde, -23.2, lon_borde + 0.2, -23.0)], crs=4326).to_crs(3857)
    comunas = gpd.GeoDataFrame({"cod_comuna": [1], "Comuna": ["Playa"], "Provincia": ["P"],
                                "Region": ["R"]}, geometry=cuadro, crs=3857)
    comunas["_nombre_norm"] = comunas["Comuna"].map(env.geo._normalizar_nombre)
    return comunas


class CorreccionesTest(unittest.TestCase):
    def test_valida_campos(self):
        c, _ = _correccion()
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "c.json"
            ruta.write_text(json.dumps({"estaciones": {"T01": c}}), encoding="utf-8")
            self.assertIn("T01", env.cargar_correcciones(ruta))
            sin = {k: v for k, v in c.items() if k != "sha256"}
            ruta.write_text(json.dumps({"estaciones": {"T01": sin}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                env.cargar_correcciones(ruta)
            ruta.write_text(json.dumps({"estaciones": {"T01": c | {"tipo_documento": "x"}}}),
                            encoding="utf-8")
            with self.assertRaises(ValueError):
                env.cargar_correcciones(ruta)

    def test_documento_exige_huella(self):
        c, datos = _correccion()
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / c["cache_nombre"]).write_bytes(datos)
            original = lambda *a, **k: {"delegado": True}  # noqa: E731
            obtener = env.documento_oficial_factory({"T01": c}, original)
            r = obtener("T01", Path(d), refrescar=False, offline=True)
            self.assertEqual((r["sha256"], r["url"]), (c["sha256"], c["fuente"]))
            self.assertEqual(obtener("560", Path(d), refrescar=False, offline=True),
                             {"delegado": True})
            malo = env.documento_oficial_factory({"T01": c | {"sha256": "0" * 64}}, original)
            with self.assertRaises(ValueError):
                malo("T01", Path(d), refrescar=False, offline=True)

    def test_poligono_invalido_se_valida(self):
        corbata = Polygon([(0, 0), (2, 2), (2, 0), (0, 2)])
        self.assertFalse(corbata.is_valid)
        reparado = env.poligonal(corbata)
        self.assertTrue(reparado.is_valid)
        self.assertGreater(reparado.area, 0)
        cuadro = box(0, 0, 1, 1)
        self.assertIs(env.poligonal(cuadro), cuadro)

    def test_tolerancia_costera(self):
        c, _ = _correccion(tolerancia_costa_m=500)
        lon, lat = env.geo.TRANSFORMADORES_WGS84[19].transform(c["utm_e"], c["utm_n"])
        # Borde de la comuna ~200 m al este del punto: queda fuera del polígono.
        comunas = _comunas_sinteticas(lon + 0.002)
        ficha = {"utm_e_raw": str(c["utm_e"]), "utm_n_raw": str(c["utm_n"]),
                 "huso_publicado": 19, "comuna_sinca": "Playa"}
        supletorias = {"T01": {k: c[k] for k in ("utm_e", "utm_n", "huso", "fuente", "detalle",
                                                 "cache_nombre")}}
        with patch.dict(env.geo.COORDENADAS_OFICIALES_SUPLETORIAS, supletorias):
            with self.assertRaises(ValueError):
                env.geo._resolver_coordenada("T01", ficha, comunas)
            registro = {}
            resolver = env.resolver_factory(env.geo._resolver_coordenada, {"T01": c}, registro)
            r = resolver("T01", ficha, comunas)
            self.assertEqual(r["comuna_geografica"], "Playa")
            self.assertTrue(r["qc_comuna"].startswith("fuera_de_poligono_costero_"))
            self.assertFalse(r["coincide_comuna_sinca"])
            self.assertTrue(150 < r["distancia_comuna_sinca_m"] < 300)
            self.assertAlmostEqual(r["lon"], lon, places=6)
            estricto = env.resolver_factory(env.geo._resolver_coordenada,
                                            {"T01": c | {"tolerancia_costa_m": 50}}, {})
            with self.assertRaises(ValueError):
                estricto("T01", ficha, comunas)

    def test_no_reemplaza_correcciones_selladas(self):
        c, _ = _correccion()
        with self.assertRaises(ValueError):
            env.instalar({"560": c}, {})

    def test_rechaza_salidas_en_data_sinca_y_exige_sin_red(self):
        c, _ = _correccion()
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "c.json"
            ruta.write_text(json.dumps({"estaciones": {"T01": c}}), encoding="utf-8")
            comunes = ["--correcciones", str(ruta), "--estaciones", str(Path(d) / "e.csv"),
                       "--geojson", str(Path(d) / "g.geojson"),
                       "--manifiesto", str(Path(d) / "m.json"), "--cache", str(Path(d) / "c"),
                       "--cache-documentos", str(Path(d) / "docs")]
            with self.assertRaises(SystemExit):
                env.main(comunes + ["--salida", str(env.SINCA / "x.csv"), "--offline"])
            with self.assertRaises(SystemExit):
                env.main(comunes + ["--salida", str(Path(d) / "x.csv")])

    def test_codigo_publico_sin_rutas_personales_ni_arroba(self):
        for ruta in (SCRIPTS / "geometria_sinca_ampliacion.py", Path(__file__)):
            texto = ruta.read_text(encoding="utf-8")
            self.assertNotIn("/" + "Users/", texto)
            self.assertNotIn(chr(64), texto)


# Sin geopandas (o sin el script sellado) se omite la clase completa.
CorreccionesTest = unittest.skipIf(env is None, "requiere geopandas")(CorreccionesTest)


if __name__ == "__main__":
    unittest.main()
