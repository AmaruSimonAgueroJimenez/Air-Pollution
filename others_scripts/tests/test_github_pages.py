"""Pruebas herméticas de la publicación estática; no Quarto ni modelos reales."""
from __future__ import annotations

import contextlib
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import unquote, urljoin, urlsplit
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import preparar_github_pages as pages  # noqa: E402


class Enlaces(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        self.urls.extend(value for name, value in attrs
                         if name in ("href", "src", "poster") and value)


def quitar_navegacion(contenido):
    """Verificación independiente de los dos bloques añadidos al artefacto."""
    for zona in (b"HEAD", b"BODY"):
        patron = (rb"<!--AP_SITE_NAV_" + zona + rb"_START-->.*?"
                  rb"<!--AP_SITE_NAV_" + zona + rb"_END-->")
        contenido = re.sub(patron, b"", contenido, flags=re.S)
    return contenido


class ElementosHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elementos = []

    def handle_starttag(self, tag, attrs):
        self.elementos.append((tag, dict(attrs)))


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


class TablaCatalogoHTML(HTMLParser):
    """Lee la tabla renderizada sin ejecutar JavaScript ni importar programas."""
    def __init__(self):
        super().__init__()
        self.dentro = False
        self.profundidad = 0
        self.secciones = []
        self.ancestros = None
        self.filas = []
        self.fila = None
        self.celda = None
        self.ids = []
        self.enlaces = []
        self.subsecciones_python = []

    def handle_starttag(self, tag, attrs):
        atributos = dict(attrs)
        if tag == "section":
            self.secciones.append(atributos.get("id"))
        if tag == "h4" and atributos.get("data-anchor-id", "").endswith(".py"):
            self.subsecciones_python.append(atributos["data-anchor-id"])
        if atributos.get("id") == "catalogo-programas":
            self.dentro = True
            self.profundidad = 1
            self.ancestros = list(self.secciones)
        elif self.dentro and tag == "div":
            self.profundidad += 1
        if not self.dentro:
            return
        if atributos.get("id"):
            self.ids.append(atributos["id"])
        if tag == "tr":
            self.fila = []
        if tag in ("td", "th"):
            self.celda = []
        if tag == "a" and atributos.get("href"):
            self.enlaces.append(atributos["href"])

    def handle_endtag(self, tag):
        if self.dentro:
            if tag in ("td", "th") and self.celda is not None:
                self.fila.append(" ".join("".join(self.celda).split()))
                self.celda = None
            if tag == "tr" and self.fila is not None:
                self.filas.append(self.fila)
                self.fila = None
            if tag == "div":
                self.profundidad -= 1
                self.dentro = self.profundidad > 0
        if tag == "section" and self.secciones:
            self.secciones.pop()

    def handle_data(self, data):
        if self.celda is not None:
            self.celda.append(data)


class CatalogoPythonTests(unittest.TestCase):
    """Regresión documental del corte publicado: sólo lectura de QMD/HTML."""
    encabezado = ["Archivo Python", "Tipo y fuente", "Función, entradas y salidas", "API y opciones"]
    # Obtenidas del catálogo anterior a la conversión en tabla, no de la tabla nueva.
    huella_textos = "bdd788ac1806136d2bcaabb3a1e3b3c7a0f5e15600ed010ffbe37c0f173727be"
    huella_anclas = "83c12bb3d0ba7cb00fb18f0bf63b08731dbcf91033d18c420e22af7457bb01ee"

    @classmethod
    def setUpClass(cls):
        raiz = Path(__file__).resolve().parents[2]
        cls.fuente = (raiz / "docs/_catalogo_python.qmd").read_text(encoding="utf-8")
        cls.guia = (raiz / "docs/resultados_y_metodologia.qmd").read_text(encoding="utf-8")
        cls.render = TablaCatalogoHTML()
        cls.render.feed((raiz / "docs/resultados_y_metodologia.html").read_text(encoding="utf-8"))
        cls.celdas = [[celda.strip().replace(r"\|", "|")
                       for celda in re.split(r"(?<!\\)\|", linea)[1:-1]]
                      for linea in cls.fuente.splitlines() if linea.startswith('| <span id="')]

    @staticmethod
    def huella(valor):
        serializado = json.dumps(valor, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(serializado).hexdigest()

    def test_tabla_unica_cuatro_columnas_sin_subsecciones_por_archivo(self):
        self.assertEqual(self.fuente.count("| " + " | ".join(self.encabezado) + " |"), 1)
        self.assertEqual(len(self.celdas), 195)
        self.assertEqual({len(fila) for fila in self.celdas}, {4})
        self.assertIsNone(re.search(r"^#### ", self.fuente, re.M))
        self.assertEqual(sum("[Referencia pública](https://" in fila[1] for fila in self.celdas), 114)
        self.assertEqual(sum("Sólo local en este corte; sin enlace de código público." in fila[1]
                             for fila in self.celdas), 81)

    def test_conserva_los_195_nombres_y_todos_los_textos_del_corte(self):
        contenido = []
        for fila in self.celdas:
            coincidencia = re.fullmatch(r'<span id="[^"]+"></span> `([^`]+\.py)`', fila[0])
            self.assertIsNotNone(coincidencia, fila[0])
            contenido.append((coincidencia[1], " ".join(" ".join(fila[1:]).split())))
        self.assertEqual(len({ruta for ruta, _ in contenido}), 195)
        self.assertEqual(self.huella(contenido), self.huella_textos)

    def test_conserva_las_195_anclas_anteriores_sin_duplicados(self):
        anclas = []
        for fila in self.celdas:
            coincidencia = re.fullmatch(r'<span id="([^"]+)"></span> `([^`]+\.py)`', fila[0])
            self.assertIsNotNone(coincidencia, fila[0])
            anclas.append((coincidencia[2], coincidencia[1]))
        self.assertEqual(len({ancla for _, ancla in anclas}), 195)
        self.assertEqual(self.huella(anclas), self.huella_anclas)

    def test_catalogo_pertenece_a_metodologia_antes_de_descriptivos(self):
        metodo = self.guia.index("## Metodología {#metodologia}")
        descriptivos = self.guia.index("## Análisis descriptivo {#analisis-descriptivo}")
        seccion = self.guia.index("### Programas Python y organización del código {#programas-python}")
        inclusion = self.guia.index("{{< include _catalogo_python.qmd >}}")
        self.assertLess(metodo, seccion)
        self.assertLess(seccion, inclusion)
        self.assertLess(inclusion, descriptivos)
        self.assertEqual(self.guia.count("{{< include _catalogo_python.qmd >}}"), 1)
        self.assertEqual(self.render.ancestros, ["metodologia", "programas-python"])

    def test_html_muestra_las_195_filas_completas_y_los_114_enlaces(self):
        self.assertEqual(self.render.filas[0], self.encabezado)
        self.assertEqual(len(self.render.filas), 196)
        self.assertEqual({len(fila) for fila in self.render.filas}, {4})
        rutas = [re.search(r"`([^`]+\.py)`", fila[0])[1] for fila in self.celdas]
        self.assertEqual([fila[0] for fila in self.render.filas[1:]], rutas)
        enlaces = [url for fila in self.celdas
                   for url in re.findall(r"\[Referencia pública\]\((https://[^)]+)\)", fila[1])]
        self.assertEqual(len(enlaces), 114)
        self.assertEqual(self.render.enlaces, enlaces)
        anclas = [re.search(r'<span id="([^"]+)"', fila[0])[1] for fila in self.celdas]
        self.assertTrue(set(anclas).issubset(self.render.ids))
        self.assertEqual(len(self.render.ids), len(set(self.render.ids)))
        self.assertEqual(self.render.subsecciones_python, [])


class InformePrincipalHTML(HTMLParser):
    """Inspecciona estructura y citas del informe sin evaluar su contenido."""
    def __init__(self):
        super().__init__()
        self.secciones = []
        self.principales = []
        self.resultados = []
        self.catalogo_ancestros = None
        self.ids_referencias = []
        self.citas = []
        self.contenedores_refs = 0

    def handle_starttag(self, tag, attrs):
        atributos = dict(attrs)
        identificador = atributos.get("id")
        clases = atributos.get("class", "").split()
        if tag == "section":
            if "level2" in clases:
                self.principales.append(identificador)
            if ("level3" in clases and self.secciones
                    and self.secciones[-1] == "sec-resultados-generales"):
                self.resultados.append(identificador)
            self.secciones.append(identificador)
        if identificador == "catalogo-programas":
            self.catalogo_ancestros = list(self.secciones)
        if identificador == "refs":
            self.contenedores_refs += 1
        if "csl-entry" in clases and identificador:
            self.ids_referencias.append(identificador)
        if "data-cites" in atributos:
            self.citas.extend(atributos["data-cites"].split())

    def handle_endtag(self, tag):
        if tag == "section" and self.secciones:
            self.secciones.pop()


class InformePrincipalTests(unittest.TestCase):
    """Regresiones editoriales; jamás importar ni ejecutar los chunks científicos."""
    patron_chunks = re.compile(r"^```\{python\}[^\n]*\n(.*?)^```\s*$", re.M | re.S)
    # Huella del multiconjunto de 212 chunks en el QMD previo a la reorganización.
    huella_chunks_originales = "433510d4cf6d167901bbaee40cb76284709d556576a309fe363cf3f35e62924c"
    secciones_principales = [
        "sec-introduccion", "sec-pregunta-objetivos", "sec-metodologia",
        "sec-resultados-generales", "sec-limitaciones", "sec-reproducibilidad", "sec-referencias",
    ]
    secciones_resultados = [
        "sec-descriptivo", "sec-desc-fuentes", "sec-sin-validacion", "sec-resultados",
        "sec-optimismo", "sec-superficies", "sec-exposicion", "sec-anexo-rm",
    ]

    @classmethod
    def setUpClass(cls):
        cls.raiz = Path(__file__).resolve().parents[2]
        cls.qmd = (cls.raiz / "docs/modelo_1km_horario.qmd").read_text(encoding="utf-8")
        cls.chunks = cls.patron_chunks.findall(cls.qmd)
        cls.prosa = cls.patron_chunks.sub("", cls.qmd)
        cls.html = (cls.raiz / "docs/modelo_1km_horario.html").read_text(encoding="utf-8")
        cls.render = InformePrincipalHTML()
        cls.render.feed(cls.html)

    def test_siete_secciones_principales_en_orden(self):
        self.assertEqual(self.render.principales, self.secciones_principales)
        ids_qmd = re.findall(r"^## [^\n]*\{[^}\n]*#([^}\s]+)[^}\n]*\}\s*$", self.prosa, re.M)
        self.assertEqual(ids_qmd, self.secciones_principales)

    def test_ocho_resultados_son_hijos_de_la_seccion_resultados(self):
        self.assertEqual(self.render.resultados, self.secciones_resultados)
        inicio = self.prosa.index("## Resultados {#sec-resultados-generales}")
        fin = self.prosa.index("## Limitaciones {#sec-limitaciones}")
        ids = re.findall(r"^### [^\n]*\{#([^}\s]+)\}\s*$", self.prosa[inicio:fin], re.M)
        self.assertEqual(ids, self.secciones_resultados)

    def test_tabla_de_195_programas_se_incluye_en_metodologia(self):
        self.assertEqual(self.render.catalogo_ancestros, ["sec-metodologia", "programas-python"])
        inicio = self.prosa.index("## Metodología {#sec-metodologia}")
        fin = self.prosa.index("## Resultados {#sec-resultados-generales}")
        self.assertIn("### Catálogo de programas Python {#programas-python}", self.prosa[inicio:fin])
        self.assertEqual(self.prosa[inicio:fin].count("{{< include _catalogo_python.qmd >}}"), 1)
        tabla = TablaCatalogoHTML()
        tabla.feed(self.html)
        self.assertEqual(len(tabla.filas), 196)
        self.assertEqual({len(fila) for fila in tabla.filas}, {4})

    def test_bibtex_csl_y_referencias_resuelven_todas_las_citas(self):
        rutas = {}
        for campo in ("bibliography", "csl"):
            coincidencia = re.search(r"^" + campo + r":\s*([^\n]+)\s*$", self.qmd, re.M)
            self.assertIsNotNone(coincidencia, campo)
            rutas[campo] = self.raiz / "docs" / coincidencia[1].strip()
            self.assertTrue(rutas[campo].is_file(), rutas[campo])
        bib = rutas["bibliography"].read_text(encoding="utf-8")
        claves = re.findall(r"@[A-Za-z]+\s*\{\s*([^,\s]+)\s*,", bib)
        self.assertEqual(len(claves), len(set(claves)))
        self.assertTrue(ElementTree.fromstring(rutas["csl"].read_text(encoding="utf-8")).tag.endswith("style"))
        citas = {clave for clave in re.findall(r"(?<![\w])@([A-Za-z][A-Za-z0-9_:-]*)", self.prosa)
                 if not clave.startswith(("sec-", "fig-", "tbl-", "eq-", "lst-"))}
        self.assertGreaterEqual(len(citas), 40)
        self.assertTrue(citas.issubset(claves), sorted(citas - set(claves)))
        self.assertEqual(self.render.contenedores_refs, 1)
        self.assertEqual(len(self.render.ids_referencias), len(citas))
        self.assertEqual(set(self.render.ids_referencias), {"ref-" + clave for clave in citas})
        self.assertEqual(set(self.render.citas), citas)

    def test_introduccion_academica_con_antecedentes_y_objetivo_delimitado(self):
        inicio = self.prosa.index("## Introducción {#sec-introduccion}")
        fin = self.prosa.index("## Pregunta de investigación y objetivos")
        intro = self.prosa[inicio:fin]
        claves = set(re.findall(r"@([A-Za-z][A-Za-z0-9_:-]*)", intro))
        self.assertTrue({
            "di2017mortality", "strak2021elapse", "meng2021no2mortality",
            "who2021airquality", "rutllant1995meteorological", "barraza2017sources",
            "villalobos2017wood", "di2019ensemble", "pu2022hourly",
            "vandonkelaar2010aod", "cooper2020surface",
            "roberts2017crossvalidation", "meyer2021applicability",
        }.issubset(claves))
        self.assertIn("no identifica emisiones ni efectos", intro)
        self.assertNotIn("Cómo se ejecuta", intro)

    def test_metodos_delimitan_independencia_y_referencias_regulatorias(self):
        inicio = self.prosa.index("## Metodología {#sec-metodologia}")
        fin = self.prosa.index("## Resultados {#sec-resultados-generales}")
        metodos = self.prosa[inicio:fin]
        self.assertIn("cuatro\nprotocolos", metodos)
        self.assertIn("no constituye\nuna evaluación plenamente anidada", metodos)
        self.assertIn("selección se efectuó antes", metodos)
        self.assertIn("grupos de al menos dos estaciones", metodos)
        self.assertIn("@mma2023no2", metodos)
        self.assertIn("fue derogado", metodos)
        self.assertNotIn("fuga pequeña", self.prosa)
        repro = self.prosa[self.prosa.index("## Reproducibilidad {#sec-reproducibilidad}"):]
        self.assertIn("sin ejecutar nuevamente los\nmodelos", repro)

    def test_212_chunks_conservados_salvo_cinco_strings_de_encabezados(self):
        self.assertEqual(len(self.chunks), 212)
        cambios = {
            'out += [f"##### {NOMBRE_POL_TXT[pol]}", ""]':
                ('out += [f"#### {NOMBRE_POL_TXT[pol]}", ""]', 1),
            'out += [f"##### {NOMBRE_POL_TXT[pol]}", "", "::: {.panel-tabset}", ""]':
                ('out += [f"#### {NOMBRE_POL_TXT[pol]}", "", "::: {.panel-tabset}", ""]', 2),
            'out += [f"###### {NOMBRE_MOTOR[m]}", ""]':
                ('out += [f"##### {NOMBRE_MOTOR[m]}", ""]', 1),
            'out += [f"###### {amb[\'nombre\']}", ""]':
                ('out += [f"##### {amb[\'nombre\']}", ""]', 1),
        }
        restaurados = list(self.chunks)
        for nuevo, (anterior, cantidad) in cambios.items():
            self.assertEqual(sum(chunk.count(nuevo) for chunk in restaurados), cantidad, nuevo)
            restaurados = [chunk.replace(nuevo, anterior) for chunk in restaurados]
        self.assertEqual(sum(cantidad for _, cantidad in cambios.values()), 5)
        self.assertEqual(CatalogoPythonTests.huella(sorted(restaurados)), self.huella_chunks_originales)

    def test_publicacion_del_informe_sigue_siendo_estatica(self):
        flujo = (self.raiz / ".github/workflows/pages.yml").read_text(encoding="utf-8")
        comandos = re.findall(r"^\s+run:\s*(.+)$", flujo, re.M)
        self.assertEqual(len(comandos), 2)
        self.assertTrue(comandos[0].startswith("python3 -B -m unittest discover "))
        self.assertTrue(comandos[1].startswith("python3 -B others_scripts/preparar_github_pages.py "))
        self.assertNotRegex("\n".join(comandos), r"(?i)quarto|jupyter|descargar_|scripts_modelo_1km|correr_pipeline")


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
        self.archivo("docs/_site_nav.css", "#ap-site-nav { display: block; }\n", tracked=True)
        self.archivo("docs/_site_nav.js", "/* navegación local sin dependencias ni red */\n", tracked=True)
        self.archivo("docs/_site_nav_head.html", '<meta name="fixture-navigation" content="head">\n', tracked=True)
        self.archivo("docs/_site_nav_body.html", '<span id="fixture-navigation-source"></span>\n', tracked=True)

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
        publicado = (self.salida / "docs/modelo_1km_horario.html").read_bytes()
        self.assertNotEqual(publicado, self.cientifico)
        self.assertEqual(quitar_navegacion(publicado), self.cientifico)
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
                    "presentaciones/video_avance_1/AFG1_Video1_Presentacion_UC.pptx"):
            publicado = (self.salida / rel).read_bytes()
            self.assertEqual(quitar_navegacion(publicado) if rel.endswith(".html") else publicado,
                             (self.raiz / rel).read_bytes())
        self.assertFalse((self.salida / "presentaciones/video_avance_1/AFG1_Video1_Presentacion_UC.pdf").exists())
        self.assertEqual((self.raiz / "presentaciones/video_avance_1/AFG1_Video1_Presentacion_UC.pdf").read_bytes(),
                         b"%PDF-fixture")

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
        self.archivo("presentaciones/video_avance_1/AFG1_Video1_Presentacion_UC.pptx", b"PK-fixture", tracked=True)
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

    def test_afg2_publica_solo_el_powerpoint_publico_exacto(self):
        originales = "presentaciones/afg2_video_avance_1_20261017"
        carpeta = originales + "/publico"
        actuales = (f"{carpeta}/AFG2_Video1_UC.pptx",)
        excluidos = (f"{carpeta}/~$AFG2_Video1_UC.pptx", f"{carpeta}/AFG2_Video1_UC_v2.pptx",
                     f"{carpeta}/AFG2_Video1_UC_anterior.pdf", f"{carpeta}/Plantilla_UC.potx",
                     f"{carpeta}/plantilla.pdf", f"{carpeta}/assets/figura.png",
                     f"{carpeta}/pautas/Pautas_video_avance_1_AFG2.pdf", f"{carpeta}/video.mp4",
                     f"{carpeta}/AFG2_Video1_UC.pdf", f"{carpeta}/Guion_Video_Avance_1.pdf",
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
            self.assertTrue((self.raiz / rel).is_file(), rel)
        urls = self.enlaces("docs/index.html")
        for rel in actuales:
            self.assertIn("../" + rel, urls)
        for rel in excluidos:
            self.assertNotIn("../" + rel, urls)

    def test_afg2_se_integra_en_presentaciones_sin_bloque_actual(self):
        afg2 = "presentaciones/afg2_video_avance_1_20261017/publico/AFG2_Video1_UC.pptx"
        afg1 = "presentaciones/video_avance_1/AFG1_Video1_Presentacion_UC.pptx"
        for rel in (afg1, afg2):
            self.archivo(rel, b"PK-fixture", tracked=True)
        self.construir()
        indice = (self.salida / "docs/index.html").read_text()
        self.assertNotIn('id="presentacion-actual"', indice)
        self.assertNotIn('class="afg2"', indice)
        self.assertNotIn("Presentación AFG2 actual", indice)
        self.assertIn("Presentaciones y documentos anteriores", indice)
        self.assertIn("../" + afg2, self.enlaces("docs/index.html"))
        self.assertIn("../" + afg1, self.enlaces("docs/index.html"))
        self.assertLess(indice.index("Presentaciones y documentos anteriores"), indice.index(afg2))

    def test_afg2_inclusion_explicita_no_reintroduce_originales_ni_plantillas(self):
        carpeta = "presentaciones/afg2_video_avance_1_20261017"
        for relativo in (f"{carpeta}/AFG2_Video1_UC.pdf", f"{carpeta}/Guion_Video_Avance_1.pdf",
                         f"{carpeta}/publico/AFG2_Video1_UC.pdf", f"{carpeta}/publico/Guion_Video_Avance_1.pdf",
                         f"{carpeta}/publico/plantilla.pdf", f"{carpeta}/publico/AFG2_Video1_UC_v2.pdf"):
            self.archivo(relativo, b"%PDF-fixture no publicar", tracked=True)
            with self.subTest(relativo=relativo), self.assertRaises(ValueError):
                self.construir(incluir=(relativo,))
            self.assertFalse(self.salida.exists())

    def test_afg1_pdf_y_guiones_no_reentran_por_inclusion_explicita(self):
        for rel in ("presentaciones/video_avance_1/AFG1_Video1_Presentacion_UC.pdf",
                    "presentaciones/presentacion_final/AFG1_Guion_Exposicion.pdf"):
            self.archivo(rel, b"%PDF-fixture conservado", tracked=True)
            with self.subTest(rel=rel), self.assertRaises(ValueError):
                self.construir(incluir=(rel,))
            self.assertTrue((self.raiz / rel).is_file())
            self.assertFalse(self.salida.exists())

    def test_afg_pdf_y_guiones_no_reentran_por_dependencia_html(self):
        carpeta = "presentaciones/afg2_video_avance_1_20261017/publico"
        for rel in ("presentaciones/video_avance_1/AFG1_Video1_Presentacion_UC.pdf",
                    f"{carpeta}/AFG2_Video1_UC.pdf", f"{carpeta}/Guion_Video_Avance_1.pdf"):
            self.archivo(rel, b"%PDF-fixture conservado", tracked=True)
            self.archivo("docs/enlace_no_publicable.html",
                         f'<html><body><a href="../{rel}">Material excluido</a></body></html>', tracked=True)
            with self.subTest(rel=rel), self.assertRaises(ValueError):
                self.construir()
            self.assertTrue((self.raiz / rel).is_file())
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

    def test_recursos_nav_obligatorios_y_versionados_antes_de_crear_salida(self):
        for rel in ("docs/_site_nav.css", "docs/_site_nav.js", "docs/_site_nav_head.html", "docs/_site_nav_body.html"):
            self.git("rm", "--cached", "--", rel)
            with self.subTest(rel=rel), self.assertRaises(ValueError):
                self.construir()
            self.assertFalse(self.salida.exists())
            self.assertTrue((self.raiz / rel).is_file())
            self.git("add", "--", rel)

    def test_navegacion_solo_se_agrega_a_copias_del_artefacto(self):
        metodologia = b'<html><head><title>Metodologia</title></head><body><h1>Metodologia</h1></body></html>'
        self.archivo("docs/resultados_y_metodologia.html", metodologia, tracked=True)
        originales = {rel: (self.raiz / rel).read_bytes()
                      for rel in ("docs/modelo_1km_horario.html", "docs/resultados_y_metodologia.html",
                                  "docs/index.html", "docs/modelo_1km_horario.qmd")}
        self.construir()
        for rel, contenido in originales.items():
            self.assertEqual((self.raiz / rel).read_bytes(), contenido)
            if rel.endswith(".html") and rel != "docs/index.html":
                publicado = (self.salida / rel).read_bytes()
                self.assertIn(b'id="ap-site-nav"', publicado)
                self.assertEqual(quitar_navegacion(publicado), contenido)
        self.assertNotIn(b"AP_SITE_NAV_BODY_START", (self.salida / "index.html").read_bytes())
        self.assertIn("./docs/", (self.salida / "index.html").read_text())

    def test_nav_es_idempotente_y_retirarla_recupera_bytes_exactos(self):
        disponibles = {"docs/index.html", "docs/modelo_1km_horario.html"}
        primera = pages.agregar_navegacion_html(self.cientifico, "docs/modelo_1km_horario.html", disponibles)
        segunda = pages.agregar_navegacion_html(primera, "docs/modelo_1km_horario.html", disponibles)
        self.assertEqual(segunda, primera)
        for zona in (b"HEAD", b"BODY"):
            self.assertEqual(primera.count(b"<!--AP_SITE_NAV_" + zona + b"_START-->"), 1)
            self.assertEqual(primera.count(b"<!--AP_SITE_NAV_" + zona + b"_END-->"), 1)
        self.assertEqual(primera.count(b'id="ap-site-nav"'), 1)
        self.assertEqual(pages.retirar_navegacion_html(primera), self.cientifico)
        self.assertEqual(quitar_navegacion(primera), self.cientifico)

    def test_nav_no_confunde_body_o_head_literales_en_scripts_y_preserva_utf8_atributos(self):
        body = '<body class="informe ágil" data-nota="área > región" lang="es">'.encode()
        original = (b'\xef\xbb\xbf<!doctype html><html lang="es"><head><meta charset="utf-8">'
                    b'<script>const literal = "<body>"; const cierre = "</head>";</script>'
                    b'<style>.nota::before{content:"<body>"}</style></head>' + body
                    + '<h1>PM₂.₅ · NO₂ · Métodos y validación</h1></body></html>'.encode())
        publicado = pages.agregar_navegacion_html(original, "docs/informe.html", set())
        posicion = publicado.index(body) + len(body)
        self.assertTrue(publicado[posicion:].startswith(b"<!--AP_SITE_NAV_BODY_START-->"))
        self.assertGreater(publicado.index(b"<!--AP_SITE_NAV_HEAD_START-->"), publicado.index(b"</style>"))
        self.assertIn(b'const literal = "<body>"; const cierre = "</head>";', publicado)
        self.assertEqual(quitar_navegacion(publicado), original)
        self.assertEqual(pages.retirar_navegacion_html(publicado), original)

    def test_nav_rutas_relativas_para_docs_e_historicos_sin_cdn(self):
        disponibles = {"docs/index.html", "docs/resultados_y_metodologia.html", "docs/modelo_1km_horario.html"}
        for rel, prefijo in (("docs/modelo_1km_horario.html", ""),
                             ("others_files/20260902_informe_modelos_estimacion.html", "../docs/")):
            with self.subTest(rel=rel):
                publicado = pages.agregar_navegacion_html(self.cientifico, rel, disponibles)
                lector = ElementosHTML()
                lector.feed(publicado.decode())
                enlaces = {attrs.get("href") for tag, attrs in lector.elementos if tag == "a"}
                origen_url = "https://ejemplo.github.io/Air-Pollution/" + rel
                resueltos = {urljoin(origen_url, url) for url in enlaces if url}
                for destino in (prefijo + "index.html", prefijo + "resultados_y_metodologia.html",
                                prefijo + "modelo_1km_horario.html", prefijo + "index.html#presentaciones"):
                    self.assertIn(urljoin(origen_url, destino), resueltos)
                    resuelto = urlsplit(urljoin(origen_url, destino)).path
                    self.assertTrue(resuelto.startswith("/Air-Pollution/docs/"), resuelto)
                css = [a.get("href") for t, a in lector.elementos if t == "link" and a.get("rel") == "stylesheet"]
                js = [a.get("src") for t, a in lector.elementos if t == "script" and a.get("src")]
                self.assertIn(urljoin(origen_url, prefijo + "_site_nav.css"),
                              {urljoin(origen_url, url) for url in css})
                self.assertIn(urljoin(origen_url, prefijo + "_site_nav.js"),
                              {urljoin(origen_url, url) for url in js})
                for url in (*css, *js):
                    self.assertFalse(urlsplit(url).scheme, url)
                    self.assertFalse(url.startswith("//"), url)

    def test_nav_fallback_volver_y_secciones_accesibles(self):
        publicado = pages.agregar_navegacion_html(self.cientifico, "docs/informe.html", set())
        lector = ElementosHTML()
        lector.feed(publicado.decode())
        atras = [a for t, a in lector.elementos if t == "a" and "data-ap-back" in a]
        self.assertEqual(len(atras), 1)
        href = atras[0].get("href")
        self.assertFalse(urlsplit(href).scheme)
        self.assertEqual(urljoin("https://ejemplo.github.io/Air-Pollution/docs/informe.html", href),
                         "https://ejemplo.github.io/Air-Pollution/docs/index.html")
        detalles = [a for t, a in lector.elementos if t == "details" and "ap-sections" in a.get("class", "").split()]
        self.assertEqual(len(detalles), 1)
        self.assertIn("hidden", detalles[0])
        self.assertTrue(any(t == "ol" and "data-ap-sections" in a for t, a in lector.elementos))
        self.assertTrue(any(t == "nav" and a.get("id") == "ap-site-nav" for t, a in lector.elementos))
        self.assertTrue(any(t == "span" and a.get("id") == "ap-page-top" for t, a in lector.elementos))
        self.assertTrue(any(t == "a" and a.get("href") == "#ap-page-top" for t, a in lector.elementos))
        self.assertLess(publicado.index(b'id="ap-page-top"'), publicado.index(b'id="ap-site-nav"'))
        visible = ProsaVisible()
        visible.feed(publicado.decode())
        texto = " ".join(visible.textos)
        self.assertRegex(texto, r"\b(?:Volver|Regresar)\b")
        for etiqueta in ("Portal", "Presentaciones", "Secciones", "Arriba"):
            self.assertIn(etiqueta, texto)

    def test_fragmentos_html_sin_body_no_reciben_wrapper(self):
        fragmento = b'<table><tr><td>Fragmento reutilizable</td></tr></table>'
        self.assertEqual(pages.agregar_navegacion_html(fragmento, "docs/_tablas_compactas.html", set()), fragmento)

    def test_fragmentos_de_nav_con_marcadores_se_conservan_sin_body(self):
        fragmentos = (
            b'<!--AP_SITE_NAV_HEAD_START--><link rel="stylesheet" href="_site_nav.css">'
            b'<!--AP_SITE_NAV_HEAD_END-->',
            b'<!--AP_SITE_NAV_BODY_START--><nav id="ap-site-nav">Portal</nav>'
            b'<!--AP_SITE_NAV_BODY_END-->',
            b'<!--AP_SITE_NAV_HEAD_START--><meta name="fragmento" content="parcial">',
        )
        for fragmento in fragmentos:
            with self.subTest(fragmento=fragmento):
                self.assertEqual(pages.agregar_navegacion_html(fragmento, "docs/_site_nav_head.html", set()), fragmento)
                self.assertEqual(pages.retirar_navegacion_html(fragmento), fragmento)

    def test_nav_en_html_sin_head_es_reversible_sin_alterar_body(self):
        original = '<html lang="es"><body class="texto ágil"><h1>Informe mínimo</h1></body></html>'.encode()
        publicado = pages.agregar_navegacion_html(original, "docs/minimo.html", set())
        self.assertIn(b'id="ap-site-nav"', publicado)
        self.assertEqual(quitar_navegacion(publicado), original)
        self.assertEqual(pages.retirar_navegacion_html(publicado), original)
        self.assertEqual(pages.agregar_navegacion_html(publicado, "docs/minimo.html", set()), publicado)

    def test_nav_estatica_del_qmd_no_se_duplica_ni_modifica(self):
        original = (b'<html><head><title>Guia</title></head><body><span id="ap-page-top"></span>'
                    b'<nav id="ap-site-nav"><a href="index.html">Portal</a></nav>'
                    b'<main><h1>Guia con navegacion ya renderizada</h1></main></body></html>')
        self.assertEqual(pages.agregar_navegacion_html(original, "docs/resultados_y_metodologia.html", set()), original)


if __name__ == "__main__":
    unittest.main()
