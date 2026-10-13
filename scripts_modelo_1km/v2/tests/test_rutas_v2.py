"""Pruebas de ``_rutas_v2``: raíces, guarda de escritura, candado y escritura atómica.

Todo ocurre en carpetas temporales con su propio «repositorio», raíz v1, datos y raíz v2: ninguna prueba
escribe en las rutas reales.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))
import _rutas_v2 as rv  # noqa: E402


class ConRaicesTemporales(unittest.TestCase):
    """Raíces temporales completas: repositorio con ``scripts_modelo_1km/v2``, raíz v1, datos y raíz v2."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="rutas-v2-")
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

    def rutas(self, **cambios) -> rv.RutasV2:
        campos = {"raiz_v2": self.base / "v2", "raiz_v1": self.base / "v1", "datos": self.base / "datos",
                  "repo": self.repo, "scripts_v2": self.scripts}
        campos.update(cambios)
        return rv.RutasV2(**campos)


class RaicesTests(ConRaicesTemporales):
    def test_por_omision_en_el_disco_local(self):
        r = rv.RutasV2.desde_entorno({})
        local = (Path.home() / "Asesorias_Data_local" / "AirPollution").resolve()
        self.assertEqual(r.raiz_v2, local / "modelado_1km_v2")
        self.assertEqual(r.raiz_v1, local / "modelado_1km")
        self.assertEqual(r.datos, Path("/Volumes/Datos/Asesorias_Data/AirPollution/data").resolve())
        self.assertEqual(r.manifiesto_pliegues.name, "pliegues_v2.json")

    def test_las_variables_de_entorno_mandan(self):
        r = rv.RutasV2.desde_entorno({rv.VAR_RAIZ_V2: str(self.base / "otra"), rv.VAR_RAIZ_V1: str(self.base / "v1"),
                                      rv.VAR_DATOS: str(self.base / "datos")})
        self.assertEqual(r.raiz_v2, self.base / "otra")
        self.assertEqual(r.panel("pm25"), self.base / "v1" / "paneles" / "panel_pm25.parquet")
        self.assertEqual(r.catalogo_sinca, self.base / "datos" / "sinca" / "estaciones_georreferenciadas.csv")

    def test_local_root_mueve_las_dos_raices(self):
        r = rv.RutasV2.desde_entorno({rv.VAR_LOCAL: str(self.base / "local"), rv.VAR_DATOS: str(self.base / "datos")})
        self.assertEqual(r.raiz_v2, self.base / "local" / "modelado_1km_v2")
        self.assertEqual(r.raiz_v1, self.base / "local" / "modelado_1km")

    def test_una_variable_mal_puesta_no_abre_la_v1(self):
        v1 = str(self.base / "v1")
        with self.assertRaises(rv.RaizInvalida):
            rv.RutasV2.desde_entorno({rv.VAR_RAIZ_V2: v1, rv.VAR_RAIZ_V1: v1, rv.VAR_DATOS: str(self.base / "datos")})

    def test_rechaza_raices_que_se_cruzan(self):
        casos = {
            "igual a la v1": self.base / "v1",
            "dentro de la v1": self.base / "v1" / "v2",
            "contiene a la v1": self.base,
            "dentro del repositorio": self.repo / "datos_v2",
            "dentro de los datos crudos": self.base / "datos" / "v2",
            "en el volumen de datos": Path("/Volumes/Datos/v2"),
        }
        for nombre, raiz in casos.items():
            with self.subTest(nombre), self.assertRaises(rv.RaizInvalida):
                self.rutas(raiz_v2=raiz)

    def test_relativa_sin_rutas_absolutas(self):
        self.assertEqual(self.r.relativa(self.base / "v1" / "paneles" / "panel_pm25.parquet"),
                         {"raiz": "raiz_v1", "ruta": "paneles/panel_pm25.parquet"})
        self.assertEqual(self.r.relativa(self.scripts / "config_v2.json"),
                         {"raiz": "repo", "ruta": "scripts_modelo_1km/v2/config_v2.json"})
        self.assertEqual(self.r.relativa(self.base / "suelto.txt"), {"raiz": None, "ruta": "suelto.txt"})


class GuardaTests(ConRaicesTemporales):
    def test_rutas_permitidas(self):
        for destino in (self.r.raiz_v2 / "a" / "b.json", self.r.salidas_v2 / "t.csv", self.scripts / "nuevo.py"):
            with self.subTest(destino=destino):
                self.assertEqual(rv.verificar_escritura(destino, self.r), destino.resolve())

    def test_rechaza_todo_lo_demas(self):
        for destino in (self.base / "v1" / "paneles" / "panel_pm25.parquet", self.base / "datos" / "x.csv",
                        self.repo / "docs" / "modelo_1km_horario.qmd", self.repo / "scripts_modelo_1km" / "_features.py",
                        self.repo / "output_files" / "modelo_1km" / "eval.csv", self.base / "suelto.txt"):
            with self.subTest(destino=destino), self.assertRaises(rv.EscrituraNoPermitida):
                rv.verificar_escritura(destino, self.r)

    def test_rechaza_punto_punto(self):
        with self.assertRaises(rv.EscrituraNoPermitida):
            rv.verificar_escritura(self.r.raiz_v2 / ".." / "v1" / "paneles" / "x.parquet", self.r)

    def test_rechaza_un_enlace_simbolico_hacia_afuera(self):
        self.r.raiz_v2.mkdir()
        (self.base / "afuera").mkdir()
        (self.r.raiz_v2 / "enlace").symlink_to(self.base / "afuera", target_is_directory=True)
        with self.assertRaises(rv.EscrituraNoPermitida):
            rv.verificar_escritura(self.r.raiz_v2 / "enlace" / "x.json", self.r)

    def test_protege_el_contrato(self):
        with self.assertRaises(rv.EscrituraNoPermitida):
            rv.verificar_escritura(self.scripts / rv.NOMBRE_CONTRATO, self.r)
        with self.assertRaises(rv.EscrituraNoPermitida):
            rv.publicar_texto("cambio", self.scripts / rv.NOMBRE_CONTRATO, self.r)
        self.assertEqual((self.scripts / rv.NOMBRE_CONTRATO).read_text(encoding="utf-8"), "contrato\n")


class EscrituraAtomicaTests(ConRaicesTemporales):
    def test_la_raiz_v2_exige_candado(self):
        with self.assertRaises(rv.EscrituraNoPermitida):
            rv.publicar_json({"a": 1}, self.r.raiz_v2 / "x.json", self.r)
        self.assertFalse((self.r.raiz_v2 / "x.json").exists())
        with rv.candado_escritura("prueba", rutas=self.r):
            sha = rv.publicar_json({"a": 1, "ñ": "á"}, self.r.raiz_v2 / "sub" / "x.json", self.r)
        crudo = (self.r.raiz_v2 / "sub" / "x.json").read_bytes()
        self.assertEqual(sha, hashlib.sha256(crudo).hexdigest())
        self.assertEqual(json.loads(crudo), {"a": 1, "ñ": "á"})
        self.assertEqual(sorted(p.name for p in (self.r.raiz_v2 / "sub").iterdir()), ["x.json"])   # sin .part

    def test_las_tablas_exigen_candado_y_el_codigo_no(self):
        with self.assertRaises(rv.EscrituraNoPermitida):
            rv.publicar_texto("x\n", self.r.salidas_v2 / "t.csv", self.r)
        rv.publicar_texto("print(1)\n", self.scripts / "nuevo.py", self.r)
        self.assertEqual((self.scripts / "nuevo.py").read_text(encoding="utf-8"), "print(1)\n")

    def test_csv_y_parquet(self):
        df = pd.DataFrame({"estacion": ["309", "B03"], "filas": [3, 4]})
        with rv.candado_escritura("prueba", rutas=self.r):
            rv.publicar_csv(df, self.r.salidas_v2 / "t.csv", self.r)
            sha = rv.publicar_parquet(df, self.r.raiz_v2 / "t.parquet", self.r)
        pd.testing.assert_frame_equal(pd.read_csv(self.r.salidas_v2 / "t.csv", dtype={"estacion": str}), df)
        pd.testing.assert_frame_equal(pd.read_parquet(self.r.raiz_v2 / "t.parquet"), df)
        self.assertEqual(sha, hashlib.sha256((self.r.raiz_v2 / "t.parquet").read_bytes()).hexdigest())

    def test_renombrar_con_las_mismas_guardas(self):
        with rv.candado_escritura("prueba", rutas=self.r):
            rv.publicar_texto("a", self.r.raiz_v2 / "a.json", self.r)
            rv.renombrar(self.r.raiz_v2 / "a.json", self.r.raiz_v2 / "b.json", self.r)
            with self.assertRaises(rv.EscrituraNoPermitida):
                rv.renombrar(self.r.raiz_v2 / "b.json", self.base / "v1" / "b.json", self.r)
        self.assertTrue((self.r.raiz_v2 / "b.json").exists())
        self.assertFalse((self.base / "v1" / "b.json").exists())

    def test_tipos_de_numpy_en_json(self):
        texto = rv.texto_json({"n": np.int64(3), "x": np.float32(0.5), "v": np.array([1, 2]), "b": np.bool_(True)})
        self.assertEqual(json.loads(texto), {"n": 3, "x": 0.5, "v": [1, 2], "b": True})
        with self.assertRaises(TypeError):
            rv.texto_json({"ruta": Path("/tmp/x")})


class CandadoTests(ConRaicesTemporales):
    def _codigo_hijo(self, nombre: str, cuerpo: str) -> str:
        return textwrap.dedent(f"""
            import sys, time
            sys.path.insert(0, {str(V2)!r})
            import _rutas_v2 as rv
            r = rv.RutasV2(raiz_v2={str(self.r.raiz_v2)!r}, raiz_v1={str(self.r.raiz_v1)!r},
                           datos={str(self.r.datos)!r}, repo={str(self.repo)!r}, scripts_v2={str(self.scripts)!r})
            nombre = {nombre!r}
        """) + textwrap.dedent(cuerpo)

    def _intentar_en_otro_proceso(self, nombre: str = "pliegues") -> int:
        codigo = self._codigo_hijo(nombre, """
            try:
                with rv.candado_escritura(nombre, rutas=r):
                    pass
            except rv.CandadoOcupado:
                sys.exit(3)
            sys.exit(0)
        """)
        return subprocess.run([sys.executable, "-B", "-c", codigo], capture_output=True, timeout=120).returncode

    def test_otro_proceso_no_puede_tomarlo_mientras_lo_tengo(self):
        with rv.candado_escritura("pliegues", rutas=self.r):
            self.assertEqual(self._intentar_en_otro_proceso(), 3)
            self.assertEqual(self._intentar_en_otro_proceso("otro"), 0)     # otro nombre, otro candado
        self.assertEqual(self._intentar_en_otro_proceso(), 0)

    def test_espera_al_titular_hasta_el_limite(self):
        codigo = self._codigo_hijo("pliegues", """
            with rv.candado_escritura(nombre, rutas=r):
                print("tomado", flush=True)
                time.sleep(1.5)
        """)
        hijo = subprocess.Popen([sys.executable, "-B", "-c", codigo], stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(hijo.stdout.readline().strip(), "tomado")
            with self.assertRaises(rv.CandadoOcupado) as ctx:
                with rv.candado_escritura("pliegues", rutas=self.r, espera_s=0.1):
                    pass
            self.assertIn('"pid"', str(ctx.exception))                       # informa quién lo tiene
            with rv.candado_escritura("pliegues", rutas=self.r, espera_s=30, intervalo_s=0.05):
                self.assertTrue(rv.candado_tomado(self.r))
        finally:
            hijo.wait(timeout=60)
            hijo.stdout.close()

    def test_registra_al_titular(self):
        with rv.candado_escritura("pliegues", rutas=self.r) as ruta:
            info = json.loads(ruta.read_text(encoding="utf-8"))
            self.assertEqual(info["pid"], os.getpid())
            self.assertEqual(ruta.parent, self.r.raiz_v2 / rv.CARPETA_CANDADOS)

    def test_reentrante_en_el_mismo_proceso(self):
        self.assertFalse(rv.candado_tomado(self.r))
        with rv.candado_escritura("a", rutas=self.r):
            with rv.candado_escritura("a", rutas=self.r):
                self.assertTrue(rv.candado_tomado(self.r))
            self.assertTrue(rv.candado_tomado(self.r))
        self.assertFalse(rv.candado_tomado(self.r))

    def test_nombre_invalido(self):
        for nombre in ("../x", "", "a/b", ".oculto"):
            with self.subTest(nombre=nombre), self.assertRaises(ValueError):
                with rv.candado_escritura(nombre, rutas=self.r):
                    pass


class ConfiguracionTests(ConRaicesTemporales):
    def test_valor_vigente(self):
        self.assertEqual(rv.valor_vigente(2.0, "x"), 2.0)
        self.assertEqual(rv.valor_vigente({"estado": "pendiente", "provisional": [0, 0]}, "x"), [0, 0])
        with self.assertRaises(ValueError):
            rv.valor_vigente("pendiente", "x")
        with self.assertRaises(ValueError):
            rv.valor_vigente({"estado": "pendiente", "nota": "sin valor"}, "x")

    def test_cargar_config_exige_el_contrato_vigente(self):
        (self.scripts / rv.NOMBRE_CONFIG).write_text(json.dumps({"contrato": {"sha256": "0" * 64}}), encoding="utf-8")
        with self.assertRaises(SystemExit):
            rv.cargar_config(self.r)
        sha = hashlib.sha256((self.scripts / rv.NOMBRE_CONTRATO).read_bytes()).hexdigest()
        (self.scripts / rv.NOMBRE_CONFIG).write_text(json.dumps({"contrato": {"sha256": sha}}), encoding="utf-8")
        self.assertEqual(rv.cargar_config(self.r)["contrato"]["sha256"], sha)


if __name__ == "__main__":
    unittest.main()
