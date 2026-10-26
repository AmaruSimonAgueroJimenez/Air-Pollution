"""Pruebas de ``_rutas_v2``: raíces, guarda de escritura (sin distinguir mayúsculas ni forma Unicode, o por
identidad), candado por artefacto y entre hilos, con los nombres normalizados (NFC + casefold; Complemento de la
Enmienda 1, punto 10), escritura atómica, valores de la configuración y tope de hilos antes de importar numpy
(Enmienda 1, punto 14).

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
import threading
import unicodedata
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))
import _rutas_v2 as rv  # noqa: E402

VARIABLES_HILOS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
                   "NUMEXPR_NUM_THREADS")


def sin_distincion_de_mayusculas(carpeta: Path) -> bool:
    """¿El sistema de archivos de ``carpeta`` trata igual las mayúsculas y las minúsculas?"""
    prueba = carpeta / "MayusculasPrueba"
    prueba.mkdir(exist_ok=True)
    try:
        return (carpeta / "mayusculasprueba").exists()
    finally:
        prueba.rmdir()


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
        self.assertEqual(r.manifiesto_pliegues.name, "pliegues_v2_red2.json")     # Enmienda 2, R13

    def test_las_variables_de_entorno_mandan(self):
        r = rv.RutasV2.desde_entorno({rv.VAR_RAIZ_V2: str(self.base / "otra"), rv.VAR_RAIZ_V1: str(self.base / "v1"),
                                      rv.VAR_DATOS: str(self.base / "datos")})
        self.assertEqual(r.raiz_v2, self.base / "otra")
        self.assertEqual(r.panel("pm25"), self.base / "otra" / "paneles" / "panel_pm25_red2.parquet")  # R11
        self.assertEqual(r.panel_v1("pm25"), self.base / "v1" / "paneles" / "panel_pm25.parquet")
        derivado = (self.base / "derived" / "modelado" / "SINCA").resolve()
        self.assertIn(derivado / "v1", r.nunca_escribibles)
        self.assertNotIn(derivado / "v1_red2", r.nunca_escribibles)
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

    def test_otra_grafia_de_la_v1_no_abre_la_v1(self):
        """Enmienda 1, punto 14: la raíz v1 con otras mayúsculas o en otra forma Unicode sigue siendo la v1."""
        with self.assertRaises(rv.RaizInvalida):
            self.rutas(raiz_v2=self.base / "V1")
        with self.assertRaises(rv.RaizInvalida):
            self.rutas(raiz_v2=self.base / "V1" / "dentro")
        compuesta = unicodedata.normalize("NFC", "raíz_v1")
        (self.base / compuesta).mkdir()
        with self.assertRaises(rv.RaizInvalida):
            rv.RutasV2(raiz_v2=self.base / unicodedata.normalize("NFD", compuesta), raiz_v1=self.base / compuesta,
                       datos=self.base / "datos", repo=self.repo, scripts_v2=self.scripts)

    def test_un_enlace_a_la_v1_se_reconoce_por_identidad(self):
        (self.base / "atajo").symlink_to(self.base / "v1", target_is_directory=True)
        with self.assertRaises(rv.RaizInvalida):
            self.rutas(raiz_v2=self.base / "atajo")
        self.assertTrue(rv.misma_ruta(self.base / "atajo", self.base / "v1"))
        self.assertFalse(rv.misma_ruta(self.base / "v1", self.base / "datos"))


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

    def test_protege_el_contrato_con_otra_grafia_o_por_identidad(self):
        """Enmienda 1, punto 14: en un disco sin distinción de mayúsculas, «diseno_ambiental_v2.md» es el contrato."""
        for nombre in (rv.NOMBRE_CONTRATO.lower(), rv.NOMBRE_CONTRATO.upper(),
                       unicodedata.normalize("NFD", rv.NOMBRE_CONTRATO)):
            with self.subTest(nombre=nombre), self.assertRaises(rv.EscrituraNoPermitida):
                rv.verificar_escritura(self.scripts / nombre, self.r)
        os.link(self.scripts / rv.NOMBRE_CONTRATO, self.scripts / "copia_dura.md")       # mismo inodo
        with self.assertRaises(rv.EscrituraNoPermitida):
            rv.verificar_escritura(self.scripts / "copia_dura.md", self.r)
        self.assertEqual((self.scripts / rv.NOMBRE_CONTRATO).read_text(encoding="utf-8"), "contrato\n")

    def test_otra_grafia_de_una_raiz_escribible(self):
        """Permitir exige el texto exacto o la identidad: otra grafía de la raíz v2 sólo vale si es la misma carpeta."""
        self.r.raiz_v2.mkdir()
        otra = self.base / "V2" / "x.json"
        if sin_distincion_de_mayusculas(self.base):
            self.assertEqual(rv.verificar_escritura(otra, self.r), otra.resolve())     # la misma carpeta (inodo)
        else:
            with self.assertRaises(rv.EscrituraNoPermitida):
                rv.verificar_escritura(otra, self.r)
        with self.assertRaises(rv.EscrituraNoPermitida):                                 # aún no existe: no se adivina
            rv.verificar_escritura(self.base / "REPO" / "output_files" / "modelo_1km_v2" / "t.csv", self.rutas())
        with self.assertRaises(rv.EscrituraNoPermitida):
            rv.verificar_escritura(self.base / "V1" / "paneles" / "x.parquet", self.r)


class EscrituraAtomicaTests(ConRaicesTemporales):
    def test_la_raiz_v2_exige_candado(self):
        destino = self.r.raiz_v2 / "sub" / "x.json"
        with self.assertRaises(rv.EscrituraNoPermitida):
            rv.publicar_json({"a": 1}, destino, self.r)
        self.assertFalse(destino.exists())
        with rv.candado_artefactos([destino], rutas=self.r) as nombres:
            self.assertEqual(nombres, ["raiz_v2.sub.x.json"])
            sha = rv.publicar_json({"a": 1, "ñ": "á"}, destino, self.r)
        crudo = destino.read_bytes()
        self.assertEqual(sha, hashlib.sha256(crudo).hexdigest())
        self.assertEqual(json.loads(crudo), {"a": 1, "ñ": "á"})
        self.assertEqual(sorted(p.name for p in (self.r.raiz_v2 / "sub").iterdir()), ["x.json"])   # sin .part

    def test_las_tablas_exigen_candado_y_el_codigo_no(self):
        with self.assertRaises(rv.EscrituraNoPermitida):
            rv.publicar_texto("x\n", self.r.salidas_v2 / "t.csv", self.r)
        rv.publicar_texto("print(1)\n", self.scripts / "nuevo.py", self.r)
        self.assertEqual((self.scripts / "nuevo.py").read_text(encoding="utf-8"), "print(1)\n")
        self.assertIsNone(rv.candado_de(self.scripts / "nuevo.py", self.r))

    def test_csv_y_parquet(self):
        df = pd.DataFrame({"estacion": ["309", "B03"], "filas": [3, 4]})
        with rv.candado_artefactos([self.r.salidas_v2 / "t.csv", self.r.raiz_v2 / "t.parquet"], rutas=self.r):
            rv.publicar_csv(df, self.r.salidas_v2 / "t.csv", self.r)
            sha = rv.publicar_parquet(df, self.r.raiz_v2 / "t.parquet", self.r)
        pd.testing.assert_frame_equal(pd.read_csv(self.r.salidas_v2 / "t.csv", dtype={"estacion": str}), df)
        pd.testing.assert_frame_equal(pd.read_parquet(self.r.raiz_v2 / "t.parquet"), df)
        self.assertEqual(sha, hashlib.sha256((self.r.raiz_v2 / "t.parquet").read_bytes()).hexdigest())

    def test_renombrar_con_las_mismas_guardas(self):
        a, b = self.r.raiz_v2 / "a.json", self.r.raiz_v2 / "b.json"
        with rv.candado_artefactos([a, b], rutas=self.r):
            rv.publicar_texto("a", a, self.r)
            rv.renombrar(a, b, self.r)
            with self.assertRaises(rv.EscrituraNoPermitida):
                rv.renombrar(b, self.base / "v1" / "b.json", self.r)
        self.assertTrue(b.exists())
        self.assertFalse((self.base / "v1" / "b.json").exists())
        with rv.candado_artefactos([b], rutas=self.r), self.assertRaises(rv.EscrituraNoPermitida):
            rv.renombrar(b, self.r.raiz_v2 / "c.json", self.r)                   # sin el candado del destino
        self.assertTrue(b.exists())

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
        for nombre in ("../x", "", "a/b", ".oculto", "piñón"):
            with self.subTest(nombre=nombre), self.assertRaises(ValueError):
                with rv.candado_escritura(nombre, rutas=self.r):
                    pass

    def test_nombres_normalizados_entre_procesos(self):
        """Complemento, punto 10: el nombre del candado se normaliza (NFC + casefold), así que «X.LRO» y «x.lro»
        son el mismo candado entre procesos, con un solo archivo en minúsculas, aunque el disco distinga
        mayúsculas."""
        self.assertEqual(rv.normalizar_candado("Comparacion.Principal.PM25.LRO.k003"),
                         "comparacion.principal.pm25.lro.k003")
        self.assertEqual(rv.normalizar_candado(unicodedata.normalize("NFD", "Año")), unicodedata.normalize("NFC", "año"))
        with rv.candado_escritura("Comparacion.principal.pm25.LRO.k003", rutas=self.r) as ruta:
            self.assertEqual(ruta.name, "comparacion.principal.pm25.lro.k003.lock")
            self.assertTrue(rv.candado_tomado(self.r, "comparacion.principal.pm25.lro.k003"))
            self.assertTrue(rv.candado_tomado(self.r, "COMPARACION.PRINCIPAL.PM25.LRO.K003"))
            self.assertEqual(self._intentar_en_otro_proceso("comparacion.principal.pm25.lro.k003"), 3)
            self.assertEqual(self._intentar_en_otro_proceso("COMPARACION.principal.pm25.Lro.K003"), 3)
            with rv.candado_escritura("comparacion.PRINCIPAL.pm25.lro.k003", rutas=self.r):   # reentrante: el mismo
                pass
        self.assertEqual(sorted(p.name for p in (self.r.raiz_v2 / rv.CARPETA_CANDADOS).glob("*.lock")),
                         ["comparacion.principal.pm25.lro.k003.lock"])


class CandadoPorArtefactoTests(ConRaicesTemporales):
    """Enmienda 1, punto 14: para escribir un artefacto hay que tener su candado, no uno cualquiera."""

    def test_nombres_de_los_candados(self):
        r, s = self.r.raiz_v2, self.r.salidas_v2
        casos = {
            r / "pliegues_v2.json": "pliegues",
            r / "pliegues_v2_reemplazado_20261013T050000Z.json": "pliegues",
            r / "pliegues_v2_red2.json": "pliegues",
            r / "pliegues_v2_red2_reemplazado_20261101T000000Z.json": "pliegues",
            s / "pliegues_v2_bloques_blq75.csv": "pliegues",
            r / "paneles" / "calidad_pm25.parquet": "calidad",
            s / "calidad_v2_tablas.json": "calidad",
            r / "vecindario" / "registro_recalculos_no2.json": "vecindario",
            s / "vecindario_v2_validacion.json": "vecindario",
            r / "piloto_tiempos" / "mediciones.json": "piloto_tiempos",
            r / "plan_corrida_v2.json": "plan_corrida",
            s / "comparacion_piloto_tiempos.csv": "plan_corrida",
            r / "comparacion" / "principal" / "pm25" / "LRO" / "k003" / "r1" / "mlp.npz": "comparacion.principal.pm25.lro.k003",
            r / "comparacion" / "principal" / "pm25" / "LRO" / "consolidado.json": "comparacion.principal.pm25.lro.consolidar",
            s / "comparacion_principal_pm25_BLQ-75_bootstrap.csv": "comparacion.principal.pm25.blq-75.consolidar",
            s / "comparacion_principal_no2_LRO.json": "comparacion.principal.no2.lro.consolidar",
            r / "otra" / "cosa nueva.json": "raiz_v2.otra.cosa_nueva.json",
        }
        for ruta, nombre in casos.items():
            with self.subTest(ruta=ruta.name):
                self.assertEqual(rv.candado_de(ruta, self.r), nombre)
        self.assertIsNone(rv.candado_de(self.scripts / "m.py", self.r))

    def test_grafias_de_una_ruta_dan_el_mismo_candado(self):
        """Complemento, punto 10: la ruta de un artefacto escrita con otras mayúsculas o en otra forma Unicode cae en
        el candado de su artefacto (las reglas calzan sin distinguir mayúsculas y el nombre se normaliza), y ese
        candado basta para escribirla."""
        r, s = self.r.raiz_v2, self.r.salidas_v2
        canon = "comparacion.principal.pm25.lro.k003"
        for ruta in (r / "comparacion" / "principal" / "pm25" / "LRO" / "k003" / "r1" / "mlp.npz",
                     r / "COMPARACION" / "Principal" / "PM25" / "lro" / "K003" / "r1" / "mlp.npz"):
            with self.subTest(ruta=str(ruta.relative_to(r))):
                self.assertEqual(rv.candado_de(ruta, self.r), canon)
        self.assertEqual(rv.candado_de(s / "COMPARACION_principal_PM25_lro_metricas.csv", self.r),
                         rv.candado_de(s / "comparacion_principal_pm25_LRO_metricas.csv", self.r))
        nfd = r / unicodedata.normalize("NFD", "señal") / "x.json"
        nfc = r / unicodedata.normalize("NFC", "Señal") / "x.json"
        self.assertEqual(rv.candado_de(nfd, self.r), rv.candado_de(nfc, self.r))
        destino = r / "comparacion" / "principal" / "pm25" / "LRO" / "k003" / "r1" / "mlp.npz"
        with rv.candado_escritura("COMPARACION.principal.PM25.LRO.K003", rutas=self.r):
            rv.publicar_bytes(b"x", destino, self.r)                       # el candado normalizado basta
        self.assertEqual(destino.read_bytes(), b"x")

    def test_otro_candado_no_basta(self):
        plan = self.r.raiz_v2 / "plan_corrida_v2.json"
        with rv.candado_escritura("pliegues", rutas=self.r):
            rv.publicar_json({"ok": True}, self.r.manifiesto_pliegues, self.r)
            with self.assertRaises(rv.EscrituraNoPermitida) as ctx:
                rv.publicar_json({"x": 1}, plan, self.r)
            self.assertIn("plan_corrida", str(ctx.exception))
        self.assertFalse(plan.exists())
        with rv.candado_artefactos([plan, self.r.manifiesto_pliegues], rutas=self.r) as nombres:
            self.assertEqual(nombres, ["plan_corrida", "pliegues"])
            rv.publicar_json({"x": 1}, plan, self.r)
        self.assertTrue(plan.exists())

    def test_seguro_entre_hilos(self):
        """Otro hilo del mismo proceso no comparte el candado ni puede escribir con él."""
        destino = self.r.raiz_v2 / "piloto_tiempos" / "mediciones.json"
        tomado, soltar, resultados = threading.Event(), threading.Event(), {}

        def titular():
            with rv.candado_escritura("piloto_tiempos", rutas=self.r):
                tomado.set()
                soltar.wait(30)

        h = threading.Thread(target=titular)
        h.start()
        try:
            self.assertTrue(tomado.wait(30))
            self.assertFalse(rv.candado_tomado(self.r, "piloto_tiempos"))           # lo tiene el otro hilo
            with self.assertRaises(rv.EscrituraNoPermitida):
                rv.publicar_json({"a": 1}, destino, self.r)
            with self.assertRaises(rv.CandadoOcupado) as ctx:
                with rv.candado_escritura("piloto_tiempos", rutas=self.r, espera_s=0.1, intervalo_s=0.02):
                    pass
            self.assertIn("otro hilo", str(ctx.exception))

            def esperar():
                with rv.candado_escritura("piloto_tiempos", rutas=self.r, espera_s=30, intervalo_s=0.02):
                    resultados["tomado_despues"] = rv.candado_tomado(self.r, "piloto_tiempos")
                    rv.publicar_json({"a": 2}, destino, self.r)

            e = threading.Thread(target=esperar)
            e.start()
            soltar.set()
            e.join(60)
        finally:
            soltar.set()
            h.join(60)
        self.assertTrue(resultados.get("tomado_despues"))
        self.assertEqual(json.loads(destino.read_text(encoding="utf-8")), {"a": 2})
        self.assertFalse(rv.candado_tomado(self.r))

    def test_reentrante_solo_para_su_hilo(self):
        with rv.candado_escritura("a", rutas=self.r):
            with rv.candado_escritura("a", rutas=self.r):
                self.assertTrue(rv.candado_tomado(self.r, "a"))
            otro = {}
            t = threading.Thread(target=lambda: otro.update(tiene=rv.candado_tomado(self.r, "a")))
            t.start()
            t.join(30)
            self.assertFalse(otro["tiene"])
            self.assertTrue(rv.candado_tomado(self.r, "a"))
        self.assertFalse(rv.candado_tomado(self.r, "a"))


class HilosTests(ConRaicesTemporales):
    def test_hilos_de_la_linea(self):
        self.assertEqual(rv.hilos_de_la_linea(["correr", "--hilos", "3"], tope=12), 3)
        self.assertEqual(rv.hilos_de_la_linea(["--hilos=5", "--otra", "x"], tope=12), 5)
        self.assertEqual(rv.hilos_de_la_linea(["--hilos", "40"], tope=12), 12)               # nunca sobre el tope
        self.assertEqual(rv.hilos_de_la_linea([], por_omision=4, tope=12), 4)
        self.assertEqual(rv.hilos_de_la_linea(["-h"], tope=8), 8)
        self.assertEqual(rv.hilos_maximos_config(self.r, por_omision=7), 7)                  # sin configuración
        (self.scripts / rv.NOMBRE_CONFIG).write_text(json.dumps({"operacion": {"hilos_maximos": 6}}), encoding="utf-8")
        self.assertEqual(rv.hilos_maximos_config(self.r), 6)


class HilosAntesDeNumpyTests(unittest.TestCase):
    """Los programas de línea de órdenes fijan el tope de hilos de BLAS y OpenMP antes de importar numpy."""

    def comprobar(self, programa: str):
        script = str(V2 / programa)
        codigo = textwrap.dedent(f"""
            import importlib.abc, os, runpy, sys
            visto = {{}}
            class Vigia(importlib.abc.MetaPathFinder):
                def find_spec(self, nombre, ruta=None, objetivo=None):
                    if nombre == "numpy" and "numpy" not in visto:
                        visto["numpy"] = os.environ.get("OMP_NUM_THREADS")
                    return None
            sys.meta_path.insert(0, Vigia())
            sys.argv = [{script!r}, "--help", "--hilos", "3"]
            try:
                runpy.run_path({script!r}, run_name="__main__")
            except SystemExit:
                pass
            print("OMP_AL_IMPORTAR_NUMPY=" + str(visto.get("numpy")))
        """)
        entorno = {k: v for k, v in os.environ.items() if k not in VARIABLES_HILOS}
        out = subprocess.run([sys.executable, "-B", "-c", codigo], env=entorno, capture_output=True, text=True,
                             timeout=600)
        self.assertIn("OMP_AL_IMPORTAR_NUMPY=3", out.stdout, f"{programa}: {out.stdout[-500:]} {out.stderr[-2000:]}")

    def test_pliegues(self):
        self.comprobar("pliegues_v2.py")

    def test_correr(self):
        self.comprobar("correr_v2.py")


class ConfiguracionTests(ConRaicesTemporales):
    def test_valor_vigente(self):
        self.assertEqual(rv.valor_vigente(2.0, "x"), 2.0)
        self.assertEqual(rv.valor_vigente({"estado": "pendiente", "provisional": [0, 0]}, "x"), [0, 0])
        self.assertEqual(rv.valor_vigente({"estado": "ratificado (Enmienda 1)", "punto": "1.1", "valor": [0.0, 0.0],
                                           "nota": "n"}, "x"), [0.0, 0.0])
        with self.assertRaises(ValueError):
            rv.valor_vigente("pendiente", "x")
        with self.assertRaises(ValueError):
            rv.valor_vigente({"estado": "pendiente", "nota": "sin valor"}, "x")
        with self.assertRaises(ValueError):
            rv.valor_vigente({"estado": "ratificado (Enmienda 1)", "provisional": 3}, "x")     # sin «valor»
        with self.assertRaises(ValueError):
            rv.valor_vigente({"estado": "otro", "valor": 3}, "x")

    def test_estado_vigente(self):
        self.assertEqual(rv.estado_vigente(3), "contrato")
        self.assertEqual(rv.estado_vigente({"estado": "pendiente", "provisional": 1}), "pendiente")
        self.assertEqual(rv.estado_vigente({"estado": "ratificado (Enmienda 1)", "valor": 1}), "ratificado")

    def test_la_configuracion_real_se_lee_entera(self):
        """Cada ratificado y cada pendiente de config_v2.json se lee con valor_vigente."""
        cfg = json.loads((V2 / rv.NOMBRE_CONFIG).read_text(encoding="utf-8"))

        def recorrer(nodo, ruta=""):
            if isinstance(nodo, dict):
                if nodo.get("estado") == "pendiente" or str(nodo.get("estado", "")).startswith("ratificado"):
                    yield ruta, nodo
                    return
                for k, v in nodo.items():
                    yield from recorrer(v, f"{ruta}.{k}")
            elif isinstance(nodo, list):
                for i, v in enumerate(nodo):
                    yield from recorrer(v, f"{ruta}[{i}]")

        items = list(recorrer(cfg))
        self.assertGreaterEqual(len(items), 40)
        for ruta, item in items:
            esperado = item["valor"] if rv.estado_vigente(item) == "ratificado" else item["provisional"]
            self.assertEqual(rv.valor_vigente(item, ruta), esperado)

    def test_cargar_config_exige_el_contrato_vigente(self):
        (self.scripts / rv.NOMBRE_CONFIG).write_text(json.dumps({"contrato": {"sha256": "0" * 64}}), encoding="utf-8")
        with self.assertRaises(SystemExit):
            rv.cargar_config(self.r)
        sha = hashlib.sha256((self.scripts / rv.NOMBRE_CONTRATO).read_bytes()).hexdigest()
        (self.scripts / rv.NOMBRE_CONFIG).write_text(json.dumps({"contrato": {"sha256": sha}}), encoding="utf-8")
        self.assertEqual(rv.cargar_config(self.r)["contrato"]["sha256"], sha)


if __name__ == "__main__":
    unittest.main()
