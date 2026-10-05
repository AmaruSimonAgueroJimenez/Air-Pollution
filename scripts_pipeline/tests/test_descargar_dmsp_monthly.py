from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import descargar_dmsp_monthly as dmsp  # noqa: E402


class InventarioTests(unittest.TestCase):
    def test_clasifica_listado_plano_y_anidado(self):
        ejemplos = {
            "F15200001_avg_vis.tif": ("F15", "2000-01", "avg_vis"),
            "F15_200001_cf_cvg.tif": ("F15", "2000-01", "cf_cvg"),
            "F15/200001/cvg.tif": ("F15", "2000-01", "cvg"),
        }
        for relativo, esperado in ejemplos.items():
            with self.subTest(relativo=relativo):
                item = dmsp._clasificar_url(dmsp.BASE_URL + relativo)
                self.assertIsNotNone(item)
                self.assertEqual(
                    (item.satelite, item.periodo, item.variable), esperado)

    def test_rechaza_url_externa_antes_de_autorizar(self):
        with self.assertRaises(ValueError):
            dmsp._url_oficial("https://example.org/F15200001_avg_vis.tif")

    def test_grupo_exige_las_tres_variables(self):
        items = [
            dmsp.ItemInventario("F15", "2000-01", variable,
                                dmsp.BASE_URL + f"F15200001_{variable}.tif",
                                f"F15200001_{variable}.tif")
            for variable in ("avg_vis", "cf_cvg")
        ]
        with self.assertRaisesRegex(ValueError, "no se fabricarán"):
            dmsp._agrupar(items, "2000-01", "2000-01")

    def test_credenciales_solo_entorno(self):
        claves = ["EOG_ACCESS_TOKEN", "EOG_CLIENT_ID", "EOG_CLIENT_SECRET",
                  "EOG_USERNAME", "EOG_PASSWORD"]
        entorno = {k: os.environ.pop(k, None) for k in claves}
        try:
            with patch.object(dmsp, "load_env", return_value=None):
                with self.assertRaises(dmsp.CredencialesEOGError):
                    dmsp.ClienteEOG()
        finally:
            for clave, valor in entorno.items():
                if valor is not None:
                    os.environ[clave] = valor


@unittest.skipUnless(
    all(__import__(modulo) for modulo in ("rasterio", "geopandas", "pyarrow")),
    "requiere stack geoespacial",
)
class RecorteLocalTests(unittest.TestCase):
    def test_conserva_pixeles_valores_y_tiempo_mensual(self):
        import geopandas as gpd
        import rasterio
        from rasterio.transform import from_origin
        from shapely.geometry import box

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            transform = from_origin(-1.0, 1.0, dmsp.RESOLUCION, dmsp.RESOLUCION)
            perfil = {
                "driver": "GTiff", "width": 12, "height": 12, "count": 1,
                "dtype": "uint16", "crs": "EPSG:4326", "transform": transform,
            }
            paths = {}
            fuentes = {
                "avg_vis": np.arange(144, dtype="uint16").reshape(12, 12) % 64,
                "cf_cvg": np.full((12, 12), 7, dtype="uint16"),
                "cvg": np.full((12, 12), 9, dtype="uint16"),
            }
            for variable, datos in fuentes.items():
                path = root / f"F15200001_{variable}.tif"
                with rasterio.open(path, "w", **perfil) as dst:
                    dst.write(datos, 1)
                paths[variable] = path
            comunas = gpd.GeoDataFrame(
                {"cod_comuna": [1]},
                geometry=[box(-0.975, 0.925, -0.925, 0.975)],
                crs="EPSG:4326",
            )
            aoi = dmsp.AOI("prueba", "prueba", (-1.0, 0.9, -0.9, 1.0))
            with rasterio.open(paths["avg_vis"]) as src:
                grilla = dmsp._fingerprint_grilla(src)
            catalogo, obs = dmsp._extraer_aoi(
                paths, grilla, aoi, comunas, "F15", "2000-01")
            self.assertGreaterEqual(len(obs), 4)
            self.assertEqual(len(obs), len(catalogo))
            self.assertTrue(obs.satelite.eq("F15").all())
            self.assertTrue(obs.periodo.eq("2000-01").all())
            self.assertNotIn("hora", obs.columns)
            self.assertGreaterEqual(catalogo.cod_comuna.eq(1).sum(), 2)
            salida = root / "obs.parquet"
            dmsp._publicar_parquet(obs, salida)
            self.assertEqual(
                dmsp._validar_observaciones(
                    salida, catalogo, "F15", "2000-01", aoi, esperado=obs),
                len(obs),
            )


if __name__ == "__main__":
    unittest.main()
