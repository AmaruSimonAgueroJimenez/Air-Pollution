"""Pruebas herméticas de la publicación estática; no Quarto ni modelos reales."""
from __future__ import annotations

import contextlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import unquote, urljoin, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import preparar_github_pages as pages  # noqa: E402


class Enlaces(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        self.urls.extend(value for name, value in attrs
                         if name in ("href", "src", "poster") and value)


class ProsaVisible(HTMLParser):
    """El código y las rutas técnicas se conservan, pero no son prosa editorial."""
    def __init__(self):
        super().__init__()
        self.omitir = 0
        self.textos = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "code"):
            self.omitir += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "code") and self.omitir:
            self.omitir -= 1

    def handle_data(self, data):
        if not self.omitir:
            self.textos.append(data)


class GitHubPagesTests(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory(prefix="test_pages_")
        self.addCleanup(self.temporal.cleanup)
        self.base = Path(self.temporal.name)
        self.raiz = self.base / "Air-Pollution"
        self.raiz.mkdir()
        self.salida = self.base / "sitio"
        self.git("init", "--quiet")
        self.cientifico = (b'<!doctype html><html lang="es"><head><title>Modelo horario</title>'
                           b'</head><body><h1>Modelo</h1><p>{{#tbl-expo-{pol}</p>'
                           b'<script>const literal = "{{ sin Liquid }}";</script></body></html>')
        self.archivo("docs/modelo_1km_horario.html", self.cientifico, tracked=True)
        self.archivo("docs/modelo_1km_horario.qmd",
                     "---\ntitle: Modelo\n---\n```{python}\nraise RuntimeError('NO EJECUTAR')\n```\n",
                     tracked=True)
        self.archivo("docs/index.html", "<html><body>Índice local obsoleto</body></html>", tracked=True)

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.raiz), *args], check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def archivo(self, relativo, contenido, *, tracked=False):
        ruta = self.raiz / relativo
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(contenido if isinstance(contenido, bytes) else contenido.encode("utf-8"))
        if tracked:
            self.git("add", "--", relativo)
        return ruta

    def construir(self, incluir=()):
        resultado = pages.preparar(self.raiz, self.salida, incluir=incluir)
        self.assertIsInstance(resultado, dict)
        return resultado

    def enlaces(self, relativo):
        parser = Enlaces()
        parser.feed((self.salida / relativo).read_text(encoding="utf-8"))
        return parser.urls

    def test_preserva_html_y_fuente_sin_interpretar_liquid_ni_ejecutar_qmd(self):
        fuente = (self.raiz / "docs/modelo_1km_horario.qmd").read_bytes()
        self.construir()
        self.assertEqual((self.salida / "docs/modelo_1km_horario.html").read_bytes(), self.cientifico)
        self.assertEqual((self.salida / "docs/modelo_1km_horario.qmd").read_bytes(), fuente)
        self.assertEqual((self.raiz / "docs/modelo_1km_horario.html").read_bytes(), self.cientifico)

    def test_indices_y_marcador_estatico(self):
        self.construir()
        self.assertTrue((self.salida / ".nojekyll").is_file())
        raiz = (self.salida / "index.html").read_text(encoding="utf-8")
        self.assertIn("./docs/", raiz)
        self.assertIn("modelo_1km_horario.html", " ".join(self.enlaces("docs/index.html")))
        self.assertNotIn("Índice local obsoleto", (self.salida / "docs/index.html").read_text())
        self.assertIn("Índice local obsoleto", (self.raiz / "docs/index.html").read_text())

    def test_no_publica_html_no_versionado_ni_ignorado(self):
        self.archivo(".gitignore", "docs/privado.html\nothers_files/20260919_informe_local.html\n", tracked=True)
        self.archivo("docs/privado.html", "local privado")
        self.archivo("docs/borrador_no_versionado.html", "borrador")
        self.archivo("others_files/20260919_informe_local.html", "histórico excluido")
        self.construir()
        rutas = {p.relative_to(self.salida).as_posix() for p in self.salida.rglob("*") if p.is_file()}
        self.assertNotIn("docs/privado.html", rutas)
        self.assertNotIn("docs/borrador_no_versionado.html", rutas)
        self.assertNotIn("others_files/20260919_informe_local.html", rutas)
        indice = (self.salida / "docs/index.html").read_text()
        self.assertNotIn("privado.html", indice)
        self.assertNotIn("borrador_no_versionado", indice)
        self.assertNotIn("20260919_informe_local", indice)

    def test_no_publica_repositorio_completo_aunque_archivos_esten_versionados(self):
        for rel in (".env", "logs/seguimiento.json", "data/raw.csv", "config/credenciales.json",
                    "output_files/personas.csv", "scripts_pipeline/descarga.py"):
            self.archivo(rel, "fixture no publicable", tracked=True)
        self.construir()
        for rel in (".env", "logs", "data", "config", "output_files", "scripts_pipeline", ".git"):
            self.assertFalse((self.salida / rel).exists(), rel)

    def test_preserva_carpetas_publicas_hermanas_de_docs(self):
        self.archivo("others_files/20260902_informe_modelos_estimacion.html",
                     "<html><body>Informe histórico público</body></html>", tracked=True)
        self.archivo("others_files/20260902_informe_modelos_estimacion.qmd", "Fuente histórica", tracked=True)
        self.archivo("presentaciones/video_avance_1/AFG1_Video1_Presentacion_UC.pdf", b"%PDF-fixture", tracked=True)
        self.archivo("presentaciones/video_avance_1/AFG1_Video1_Presentacion_UC.pptx", b"PK-fixture", tracked=True)
        self.construir()
        for rel in ("others_files/20260902_informe_modelos_estimacion.html",
                    "others_files/20260902_informe_modelos_estimacion.qmd",
                    "presentaciones/video_avance_1/AFG1_Video1_Presentacion_UC.pdf",
                    "presentaciones/video_avance_1/AFG1_Video1_Presentacion_UC.pptx"):
            self.assertEqual((self.salida / rel).read_bytes(), (self.raiz / rel).read_bytes())

    def test_recursos_locales_versionados_con_espacios_y_url_codificada(self):
        self.archivo("docs/figuras/figura con espacio.png", b"PNG-fixture", tracked=True)
        contenido = '<html><body><img src="figuras/figura%20con%20espacio.png"></body></html>'
        self.archivo("docs/informe con espacio.html", contenido, tracked=True)
        self.construir()
        self.assertEqual((self.salida / "docs/figuras/figura con espacio.png").read_bytes(), b"PNG-fixture")
        urls = self.enlaces("docs/index.html")
        self.assertTrue(any("informe%20con%20espacio.html" in url for url in urls), urls)

    def test_todos_los_enlaces_del_indice_resuelven_bajo_subruta_de_pages(self):
        self.archivo("others_files/20260902_informe_modelos_estimacion.html", "<html><body>Referencia</body></html>",
                     tracked=True)
        self.archivo("presentaciones/video_avance_1/AFG1_Video1_Presentacion_UC.pdf", b"%PDF-fixture", tracked=True)
        self.construir()
        base_url = "https://ejemplo.github.io/Air-Pollution/docs/index.html"
        for url in self.enlaces("docs/index.html"):
            if url.startswith(("#", "mailto:", "data:")) or urlsplit(url).scheme:
                continue
            destino_url = urlsplit(urljoin(base_url, url))
            self.assertTrue(destino_url.path.startswith("/Air-Pollution/"), url)
            relativo = unquote(destino_url.path.removeprefix("/Air-Pollution/"))
            destino = self.salida / relativo
            if destino.is_dir():
                destino /= "index.html"
            self.assertTrue(destino.is_file(), (url, relativo))

    def test_rechaza_salida_existente_sin_borrar_ni_alterar(self):
        self.salida.mkdir()
        testigo = self.salida / "conservar.txt"
        testigo.write_text("se conserva")
        with self.assertRaises((ValueError, FileExistsError)):
            pages.preparar(self.raiz, self.salida)
        self.assertEqual(testigo.read_text(), "se conserva")

    def test_recurso_html_ausente_impide_publicacion(self):
        self.archivo("docs/roto.html", '<html><body><img src="falta.png"></body></html>', tracked=True)
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.construir()
        self.assertFalse(self.salida.exists())

    def test_recurso_solo_local_no_sustituye_archivo_versionado(self):
        self.archivo("docs/roto.html", '<html><body><img src="solo-local.png"></body></html>', tracked=True)
        self.archivo("docs/solo-local.png", b"no subir")
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.construir()

    def test_no_sigue_enlace_simbolico_versionado_a_fuera_del_repositorio(self):
        secreto = self.base / "fuera.html"
        secreto.write_text("fixture privado fuera de raíz")
        (self.raiz / "docs/escape.html").symlink_to(secreto)
        self.git("add", "--", "docs/escape.html")
        with self.assertRaises((ValueError, OSError)):
            self.construir()
        self.assertEqual(secreto.read_text(), "fixture privado fuera de raíz")

    def test_no_intenta_descargar_recursos_externos(self):
        self.archivo("docs/external.html",
                     '<html><head><script src="https://cdn.example.invalid/library.js"></script></head>'
                     '<body><a href="https://example.invalid/referencia">Referencia externa</a></body></html>',
                     tracked=True)
        self.construir()
        self.assertTrue((self.salida / "docs/external.html").is_file())

    def test_dependencias_css_se_incluyen_recursivamente(self):
        self.archivo("docs/css/estilo.css", 'body { background: url("../figuras/fondo.png"); }', tracked=True)
        self.archivo("docs/figuras/fondo.png", b"PNG-fixture", tracked=True)
        self.archivo("docs/con_estilo.html",
                     '<html><head><link rel="stylesheet" href="css/estilo.css"></head><body>Resultado</body></html>',
                     tracked=True)
        self.construir()
        self.assertTrue((self.salida / "docs/css/estilo.css").is_file())
        self.assertEqual((self.salida / "docs/figuras/fondo.png").read_bytes(), b"PNG-fixture")

    def test_enlaces_fuera_del_sitio_no_se_publican(self):
        for url in ("../../secreto.txt", "%2e%2e/%2e%2e/secreto.txt", "file:///tmp/secreto.txt", "/docs/informe.html"):
            with self.subTest(url=url):
                self.archivo("docs/escape_url.html", f'<html><body><a href="{url}">No publicar</a></body></html>',
                             tracked=True)
                with self.assertRaises(ValueError):
                    self.construir()
                self.assertFalse(self.salida.exists())

    def test_inclusion_explicita_de_evidencia_no_publica_archivos_vecinos(self):
        incluidos = {
            "output_files/ensayo/metricas.csv": "modelo,error\nfixture,1\n",
            "output_files/ensayo/evidencia.json": '{"sintetico": true}',
            "output_files/ensayo/figura.png": b"PNG-fixture",
        }
        for rel, contenido in incluidos.items():
            self.archivo(rel, contenido, tracked=True)
        self.archivo("output_files/ensayo/vecino.csv", "no seleccionado", tracked=True)
        self.construir(incluir=tuple(incluidos))
        for rel in incluidos:
            self.assertEqual((self.salida / rel).read_bytes(), (self.raiz / rel).read_bytes())
        self.assertFalse((self.salida / "output_files/ensayo/vecino.csv").exists())
        urls = self.enlaces("docs/index.html")
        for rel in incluidos:
            self.assertIn("../" + rel, urls)

    def test_inclusion_expresa_resuelve_enlace_a_codigo_de_procedencia(self):
        rel = "scripts_modelo_1km/v3/README.md"
        self.archivo(rel, "Referencia metodológica de fixture", tracked=True)
        self.archivo("docs/procedencia.html",
                     f'<html><body><a href="../{rel}">Procedencia</a></body></html>', tracked=True)
        self.construir(incluir=(rel,))
        self.assertEqual((self.salida / rel).read_bytes(), (self.raiz / rel).read_bytes())

    def test_inclusion_de_archivo_no_versionado_rechazada(self):
        rel = "output_files/ensayo/local.csv"
        self.archivo(rel, "no versionado")
        with self.assertRaises(ValueError):
            self.construir(incluir=(rel,))
        self.assertFalse(self.salida.exists())

    def test_inclusion_no_acepta_directorios_ni_globs(self):
        self.archivo("output_files/ensayo/metricas.csv", "fixture", tracked=True)
        for rel in ("output_files/ensayo", "output_files/ensayo/*", "output_files/**/*.csv"):
            with self.subTest(rel=rel), self.assertRaises(ValueError):
                self.construir(incluir=(rel,))
            self.assertFalse(self.salida.exists())

    def test_inclusion_no_permite_secretos_bitacoras_datos_ni_config(self):
        for rel in (".env", "docs/.env", "logs/control.json", "data/observaciones.csv",
                    "config/credenciales.json", "output_files/credenciales.json"):
            self.archivo(rel, "fixture no publicable", tracked=True)
            with self.subTest(rel=rel), self.assertRaises(ValueError):
                self.construir(incluir=(rel,))
            self.assertFalse(self.salida.exists())

    def test_inclusion_explicita_no_sigue_symlinks(self):
        fuera = self.base / "secreto.json"
        fuera.write_text('{"fixture": true}')
        enlace = self.raiz / "output_files/escape.json"
        enlace.parent.mkdir(exist_ok=True)
        enlace.symlink_to(fuera)
        self.git("add", "--", "output_files/escape.json")
        with self.assertRaises((ValueError, OSError)):
            self.construir(incluir=("output_files/escape.json",))
        self.assertFalse(self.salida.exists())

    def test_cli_manifiesto_explicito_versionado(self):
        rel = "output_files/ensayo/metricas.csv"
        self.archivo(rel, "fixture", tracked=True)
        self.archivo("config/github_pages.json", json.dumps({"include": [rel]}), tracked=True)
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            codigo = pages.main(["--root", str(self.raiz), "--output", str(self.salida),
                                 "--include-manifest", "config/github_pages.json"])
        self.assertEqual(codigo, 0)
        self.assertIsInstance(json.loads(stdout.getvalue()), dict)
        self.assertTrue((self.salida / rel).is_file())
        self.assertFalse((self.salida / "config/github_pages.json").exists())

    def test_cli_inclusiones_repetibles_son_exactas(self):
        rutas = ("output_files/ensayo/metricas.csv", "output_files/ensayo/evidencia.json")
        for rel in rutas:
            self.archivo(rel, "fixture", tracked=True)
        self.archivo("output_files/ensayo/vecino.csv", "no incluir", tracked=True)
        with contextlib.redirect_stdout(io.StringIO()):
            codigo = pages.main(["--root", str(self.raiz), "--output", str(self.salida),
                                 "--include", rutas[0], "--include", rutas[1]])
        self.assertEqual(codigo, 0)
        for rel in rutas:
            self.assertTrue((self.salida / rel).is_file())
        self.assertFalse((self.salida / "output_files/ensayo/vecino.csv").exists())

    def test_manifiesto_no_versionado_rechazado(self):
        self.archivo("config/github_pages.json", '{"include": []}')
        with self.assertRaises(ValueError):
            pages.preparar(self.raiz, self.salida, manifiesto=Path("config/github_pages.json"))
        self.assertFalse(self.salida.exists())

    def test_manifiesto_no_acepta_esquema_mas_amplio(self):
        self.archivo("config/github_pages.json", '{"include": [], "copiar_todo": true}', tracked=True)
        with self.assertRaises(ValueError):
            pages.preparar(self.raiz, self.salida, manifiesto=Path("config/github_pages.json"))
        self.assertFalse(self.salida.exists())

    def test_afg2_publica_solo_los_tres_materiales_actuales_exactos(self):
        originales = "presentaciones/afg2_video_avance_1_20261017"
        carpeta = originales + "/publico"
        actuales = (f"{carpeta}/AFG2_Video1_UC.pptx", f"{carpeta}/AFG2_Video1_UC.pdf",
                    f"{carpeta}/Guion_Video_Avance_1.pdf")
        excluidos = (f"{carpeta}/~$AFG2_Video1_UC.pptx", f"{carpeta}/AFG2_Video1_UC_v2.pptx",
                     f"{carpeta}/AFG2_Video1_UC_anterior.pdf", f"{carpeta}/Plantilla_UC.potx",
                     f"{carpeta}/plantilla.pdf", f"{carpeta}/assets/figura.png",
                     f"{carpeta}/pautas/Pautas_video_avance_1_AFG2.pdf", f"{carpeta}/video.mp4",
                     "presentaciones/afg2_video_avance_1_20261018/publico/AFG2_Video1_UC.pdf",
                     f"{originales}/AFG2_Video1_UC.pptx", f"{originales}/AFG2_Video1_UC.pdf",
                     f"{originales}/Guion_Video_Avance_1.pdf")
        for numero, rel in enumerate((*actuales, *excluidos)):
            self.archivo(rel, f"fixture no ejecutar {numero}", tracked=True)
        self.construir()
        for rel in actuales:
            self.assertEqual((self.salida / rel).read_bytes(), (self.raiz / rel).read_bytes())
        for rel in excluidos:
            self.assertFalse((self.salida / rel).exists(), rel)
        urls = self.enlaces("docs/index.html")
        for rel in actuales:
            self.assertIn("../" + rel, urls)
        for rel in excluidos:
            self.assertNotIn("../" + rel, urls)

    def test_afg2_actual_se_destaca_antes_del_material_afg1_anterior(self):
        afg2 = "presentaciones/afg2_video_avance_1_20261017/publico/AFG2_Video1_UC.pdf"
        afg1 = "presentaciones/video_avance_1/AFG1_Video1_Presentacion_UC.pdf"
        for rel in (afg1, afg2):
            self.archivo(rel, b"%PDF-fixture", tracked=True)
        self.construir()
        indice = (self.salida / "docs/index.html").read_text()
        self.assertIn('id="presentacion-actual"', indice)
        self.assertIn("Presentación AFG2", indice)
        self.assertLess(indice.index(afg2), indice.index(afg1))

    def test_afg2_inclusion_explicita_no_reintroduce_originales_ni_plantillas(self):
        carpeta = "presentaciones/afg2_video_avance_1_20261017"
        for relativo in (f"{carpeta}/AFG2_Video1_UC.pdf", f"{carpeta}/Guion_Video_Avance_1.pdf",
                         f"{carpeta}/publico/plantilla.pdf", f"{carpeta}/publico/AFG2_Video1_UC_v2.pdf"):
            self.archivo(relativo, b"%PDF-fixture no publicar", tracked=True)
            with self.subTest(relativo=relativo), self.assertRaises(ValueError):
                self.construir(incluir=(relativo,))
            self.assertFalse(self.salida.exists())

    def test_labels_editoriales_sin_dmc_con_rutas_tecnicas_conservadas(self):
        informe = "docs/piloto_perdidas_sin_dmc_20261013.html"
        evidencia = "output_files/modelo_1km_v2/piloto_pre_dmc_20261013/metricas.json"
        self.archivo(informe, "<html><body>Piloto exploratorio</body></html>", tracked=True)
        self.archivo(evidencia, '{"fixture": true}', tracked=True)
        self.construir(incluir=(evidencia,))
        indice = (self.salida / "docs/index.html").read_text()
        prosa = ProsaVisible()
        prosa.feed(indice)
        self.assertNotIn("dmc", " ".join(prosa.textos).casefold())
        self.assertIn("piloto_perdidas_sin_dmc_20261013.html", self.enlaces("docs/index.html"))
        self.assertIn("../" + evidencia, self.enlaces("docs/index.html"))
        self.assertIn(evidencia.rsplit("/", 1)[0], indice)

    def test_qmd_companero_y_fragmentos_include_recursivos_se_conservan(self):
        principal = self.archivo("docs/modelo_1km_horario.qmd",
                                 '---\ntitle: Modelo\n---\n{{< include "_detalle con espacio.qmd" >}}\n',
                                 tracked=True)
        fragmento = self.archivo("docs/_detalle con espacio.qmd", "Detalle\n{{< include '_anexo.qmd' >}}\n",
                                tracked=True)
        anexo = self.archivo("docs/_anexo.qmd", "Anexo preservado sin ejecución\n", tracked=True)
        self.construir()
        for origen in (principal, fragmento, anexo):
            rel = origen.relative_to(self.raiz)
            self.assertEqual((self.salida / rel).read_bytes(), origen.read_bytes())

    def test_qmd_no_publica_fragmentos_include_solo_locales(self):
        self.archivo("docs/modelo_1km_horario.qmd", "{{< include _solo_local.qmd >}}\n", tracked=True)
        self.archivo("docs/_solo_local.qmd", "No publicar sin versión")
        with self.assertRaises(ValueError):
            self.construir()
        self.assertFalse(self.salida.exists())


if __name__ == "__main__":
    unittest.main()
