"""Pruebas de ``_traza_v2``: sha256, hash del código, versiones, hilos y bloque de procedencia."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))
import _rutas_v2 as rv  # noqa: E402
import _traza_v2 as tz  # noqa: E402


class TrazaTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="traza-v2-")
        self.base = Path(self._tmp.name).resolve()
        self.repo = self.base / "repo"
        self.scripts = self.repo / "scripts_modelo_1km" / "v2"
        self.scripts.mkdir(parents=True)
        (self.scripts / rv.NOMBRE_CONTRATO).write_text("contrato\n", encoding="utf-8")
        (self.base / "v1" / "paneles").mkdir(parents=True)
        (self.base / "datos").mkdir()
        self.r = rv.RutasV2(raiz_v2=self.base / "v2", raiz_v1=self.base / "v1", datos=self.base / "datos",
                            repo=self.repo, scripts_v2=self.scripts)

    def tearDown(self):
        self._tmp.cleanup()

    def test_sha256_de_archivo_y_su_cache(self):
        p = self.base / "a.bin"
        p.write_bytes(b"hola")
        self.assertEqual(tz.sha256_archivo(p), hashlib.sha256(b"hola").hexdigest())
        p.write_bytes(b"hola, mundo")                       # cambia el tamaño: la memoria no sirve
        self.assertEqual(tz.sha256_archivo(p), hashlib.sha256(b"hola, mundo").hexdigest())

    def test_sha256_json_no_depende_del_orden(self):
        self.assertEqual(tz.sha256_json({"a": 1, "b": [1, 2]}), tz.sha256_json({"b": [1, 2], "a": 1}))
        self.assertNotEqual(tz.sha256_json({"a": 1}), tz.sha256_json({"a": 2}))
        self.assertEqual(tz.sha256_json({"n": np.int64(3)}), tz.sha256_json({"n": 3}))

    def test_hash_del_codigo_cubre_los_modulos_y_no_las_pruebas(self):
        (self.scripts / "m.py").write_text("x = 1\n", encoding="utf-8")
        (self.scripts / "notas.txt").write_text("no cuenta\n", encoding="utf-8")
        (self.scripts / "tests").mkdir()
        (self.scripts / "tests" / "test_m.py").write_text("y = 1\n", encoding="utf-8")
        h1 = tz.hash_codigo_v2(self.r)
        self.assertEqual(list(h1["archivos"]), ["scripts_modelo_1km/v2/m.py"])
        (self.scripts / "tests" / "test_m.py").write_text("y = 2\n", encoding="utf-8")
        self.assertEqual(tz.hash_codigo_v2(self.r)["hash"], h1["hash"])
        (self.scripts / "m.py").write_text("x = 2\n", encoding="utf-8")
        self.assertNotEqual(tz.hash_codigo_v2(self.r)["hash"], h1["hash"])

    def test_versiones_sin_importar(self):
        v = tz.versiones_bibliotecas()
        self.assertEqual(v["numpy"], np.__version__)
        for nombre in ("python", "pandas", "pyarrow", "scikit-learn", "lightgbm", "xgboost"):
            self.assertIn(nombre, v)

    def test_traza_completa_y_sin_rutas_absolutas(self):
        insumo = self.base / "v1" / "paneles" / "panel_pm25.parquet"
        insumo.write_bytes(b"panel")
        t = tz.traza({"panel_pm25": insumo}, {"regla": [42, "k"]}, 12, rutas=self.r)
        for clave in ("creado_utc", "git", "codigo", "contrato", "config", "insumos", "bibliotecas", "python",
                      "hilos", "semillas"):
            self.assertIn(clave, t)
        self.assertEqual(t["insumos"]["panel_pm25"], {"raiz": "raiz_v1", "ruta": "paneles/panel_pm25.parquet",
                                                     "sha256": hashlib.sha256(b"panel").hexdigest(), "bytes": 5})
        self.assertEqual(t["contrato"]["ruta"], "scripts_modelo_1km/v2/" + rv.NOMBRE_CONTRATO)
        self.assertIsNone(t["config"])                      # no hay configuración en esta carpeta temporal
        self.assertEqual(t["git"]["commit"], "desconocido")  # la carpeta temporal no es un repositorio
        self.assertEqual(t["hilos"]["configurados"], 12)
        self.assertEqual(t["semillas"], {"regla": [42, "k"]})
        self.assertNotIn(str(self.base), json.dumps(t, ensure_ascii=False))

    def test_commit_del_repositorio_real_sin_escribir_el_indice(self):
        indice = rv.REPO / ".git" / "index"
        antes = indice.stat().st_mtime_ns if indice.exists() else None
        g = tz.commit_git(rv.REPO)
        if g["commit"] != "desconocido":
            self.assertRegex(g["commit"], r"^[0-9a-f]{40}$")
            self.assertIsInstance(g["v2_sin_commit"], list)
        if antes is not None:
            self.assertEqual(indice.stat().st_mtime_ns, antes)

    def test_fijar_hilos_no_sube_un_tope_menor(self):
        guardado = {v: os.environ.get(v) for v in tz.VARIABLES_HILOS}
        try:
            for v in tz.VARIABLES_HILOS:
                os.environ.pop(v, None)
            os.environ["OMP_NUM_THREADS"] = "2"
            h = tz.fijar_hilos(12)
            self.assertEqual(os.environ["OMP_NUM_THREADS"], "2")
            self.assertEqual(os.environ["MKL_NUM_THREADS"], "12")
            self.assertEqual(h["configurados"], 12)
        finally:
            for v, valor in guardado.items():
                if valor is None:
                    os.environ.pop(v, None)
                else:
                    os.environ[v] = valor

    def test_creado_utc_en_formato_iso(self):
        self.assertRegex(rv.ahora_utc(), re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"))


if __name__ == "__main__":
    unittest.main()
