#!/usr/bin/env python3
"""Prepara un sitio estático selectivo con archivos públicos ya versionados.

No ejecuta informes, Quarto, modelos ni descargadores. Conserva los bytes de
las fuentes y renders; sólo genera los dos índices y la marca ``.nojekyll``.
La salida debe ser un directorio nuevo: nunca se borra ni se sobrescribe uno.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import posixpath
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlsplit


MATERIALES = {
    "presentacion_final", "video_avance_1", "video_avance_2", "video_avance_3",
    "tesis_doctoral_2026-10", "poster_2026-10",
}
EXTENSIONES_DOCS = {
    ".html", ".qmd", ".md", ".txt", ".pdf", ".docx", ".css", ".js",
    ".json", ".csv", ".geojson", ".svg", ".png", ".jpg", ".jpeg",
    ".gif", ".webp", ".ico", ".woff", ".woff2", ".ttf", ".otf",
    ".eot", ".bib", ".csl",
}
GENERADOS = {"index.html", "docs/index.html", ".nojekyll"}
RAICES_EXPLICITAS = {
    "docs", "others_files", "presentaciones", "output_files", "scripts_modelo_1km",
    "scripts_superficie", "scripts_estacion",
}
EXTENSIONES_EXPLICITAS = {".csv", ".json", ".png", ".pdf", ".md", ".py"}
CSS_URL = re.compile(r"url\(\s*['\"]?([^\s)'\"]+)['\"]?\s*\)|@import\s+['\"]([^'\"]+)['\"]", re.I)
SENSIBLE = re.compile(
    r"(?:^|[._ /-])(?:credenciales?|credentials?|secrets?|passwords?|passwd|"
    r"api[_-]?keys?|private[_-]?keys?|(?:access|refresh|auth)[_-]?tokens?)(?:$|[._ /-])",
    re.I,
)


def archivos_versionados(raiz: Path) -> set[str]:
    """El índice de Git es la única fuente del inventario público inicial."""
    proceso = subprocess.run(
        ["git", "-C", str(raiz), "ls-files", "--cached", "--full-name", "-z"],
        check=True, capture_output=True,
    )
    return {p for p in proceso.stdout.decode("utf-8").split("\0") if p}


def fuente_segura(raiz: Path, relativo: str) -> Path:
    """No seguir symlinks ni aceptar nombres fuera del árbol seleccionado."""
    p = PurePosixPath(relativo)
    if (p.is_absolute() or ".." in p.parts or "\\" in relativo or "\0" in relativo
            or any(parte.startswith(".") for parte in p.parts)
            or SENSIBLE.search(relativo)
            or any(palabra in relativo.casefold() for palabra in ("mni1", "privado"))):
        raise ValueError(f"Ruta no segura para GitHub Pages: {relativo}")
    actual = raiz
    for parte in p.parts:
        actual /= parte
        if actual.is_symlink():
            raise ValueError(f"No se publican symlinks: {relativo}")
    if not actual.is_file():
        raise ValueError(f"Archivo versionado ausente: {relativo}")
    return actual


def historico_publico(relativo: str) -> bool:
    p = PurePosixPath(relativo)
    return (len(p.parts) == 2 and p.parts[0] == "others_files"
            and re.match(r"^\d{8}_informe", p.name) is not None
            and p.suffix.lower() in {".html", ".qmd"})


def material_publico(relativo: str) -> bool:
    p = PurePosixPath(relativo)
    return (len(p.parts) == 3 and p.parts[0] == "presentaciones"
            and p.parts[1] in MATERIALES
            and p.name.startswith(("AFG1_", "Tesis_Exposoma_", "Poster_Exposoma_"))
            and p.suffix.lower() in {".pdf", ".pptx"})


def seleccionar(versionados: set[str]) -> set[str]:
    """Renders públicos, sus fuentes y materiales expresamente admitidos."""
    elegidos = {
        p for p in versionados
        if ((p.startswith("docs/") and PurePosixPath(p).suffix.lower() == ".html"
             and p != "docs/index.html" and not PurePosixPath(p).name.startswith("_"))
            or historico_publico(p) or material_publico(p))
    }
    for relativo in tuple(elegidos):
        p = PurePosixPath(relativo)
        if p.parts[0] == "docs" and p.suffix.lower() == ".html":
            fuente = p.with_suffix(".qmd").as_posix()
            if fuente in versionados:
                elegidos.add(fuente)
    return elegidos


class ReferenciasHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.urls: list[str] = []
        self.en_estilo = False

    def handle_starttag(self, tag, attrs):
        for clave, valor in attrs:
            if not valor:
                continue
            if clave in {"href", "src", "poster"} or (tag == "object" and clave == "data"):
                self.urls.append(valor)
            elif clave == "srcset":
                # Los renders actuales incrustan recursos. También se admiten
                # conjuntos locales ordinarios con descriptores 1x/2x o ancho.
                if not valor.lstrip().startswith("data:"):
                    self.urls.extend(item.strip().split()[0] for item in valor.split(",") if item.strip())
            elif clave == "style":
                self.urls.extend(urls_css(valor))
        if tag == "style":
            self.en_estilo = True

    def handle_endtag(self, tag):
        if tag == "style":
            self.en_estilo = False

    def handle_data(self, data):
        if self.en_estilo:
            self.urls.extend(urls_css(data))


def urls_css(texto: str) -> list[str]:
    return [primera or segunda for primera, segunda in CSS_URL.findall(texto)]


def destino_local(origen: str, url: str) -> str | None:
    """Resuelve enlaces relativos sin perder el prefijo de un project site."""
    url = url.strip()
    if not url or url.startswith("#"):
        return None
    partes = urlsplit(url)
    if partes.scheme.lower() == "file":
        raise ValueError(f"Enlace local del equipo en {origen}: {url}")
    if partes.scheme or partes.netloc:
        return None
    ruta = unquote(partes.path)
    if not ruta:
        return None
    if ruta.startswith("/") or "\\" in ruta or "\0" in ruta:
        raise ValueError(f"Enlace incompatible con el sitio de proyecto en {origen}: {url}")
    destino = posixpath.normpath(posixpath.join(posixpath.dirname(origen), ruta))
    if destino == ".." or destino.startswith("../"):
        raise ValueError(f"Enlace fuera del sitio en {origen}: {url}")
    if ruta.endswith("/") or destino == ".":
        destino = posixpath.join("" if destino == "." else destino, "index.html")
    return destino


def dependencia_permitida(relativo: str, iniciales: set[str]) -> bool:
    if relativo in iniciales or relativo in GENERADOS:
        return True
    p = PurePosixPath(relativo)
    if p.parts[0] == "docs":
        return p.suffix.lower() in EXTENSIONES_DOCS
    # Recursos propios de un informe histórico: nunca copiar others_files entero.
    for informe in iniciales:
        ip = PurePosixPath(informe)
        if (ip.parts[0] == "others_files" and ip.suffix.lower() == ".html"
                and relativo.startswith(f"others_files/{ip.stem}_files/")
                and p.suffix.lower() in EXTENSIONES_DOCS):
            return True
    return False


def inclusiones_publicas(raiz: Path, versionados: set[str], incluir=(), manifiesto=None) -> set[str]:
    """Lista exacta, revisada y versionada; nunca una carpeta ni un glob."""
    if isinstance(incluir, (str, bytes)):
        raise ValueError("include debe ser una lista de rutas exactas")
    rutas = list(incluir)
    if manifiesto is not None:
        nombre = Path(manifiesto)
        if nombre.is_absolute():
            try:
                nombre = nombre.relative_to(raiz)
            except ValueError as exc:
                raise ValueError("El manifiesto debe estar dentro del repositorio") from exc
        relativo = nombre.as_posix()
        if relativo not in versionados:
            raise ValueError(f"Manifiesto no versionado: {relativo}")
        contenido = json.loads(fuente_segura(raiz, relativo).read_text(encoding="utf-8"))
        if (not isinstance(contenido, dict) or set(contenido) != {"include"}
                or not isinstance(contenido["include"], list)):
            raise ValueError('El manifiesto debe contener únicamente {"include": [rutas exactas]}')
        rutas.extend(contenido["include"])
    elegidos = set()
    for relativo in rutas:
        if not isinstance(relativo, str) or not relativo:
            raise ValueError("Cada inclusión debe ser una ruta de archivo exacta")
        p = PurePosixPath(relativo)
        if (len(p.parts) < 2 or p.parts[0] not in RAICES_EXPLICITAS
                or p.suffix.lower() not in EXTENSIONES_EXPLICITAS
                or any(c in relativo for c in "*?[]")
                or any(parte.casefold() in {"data", "logs", "credentials", "credenciales", "secrets"}
                       for parte in p.parts)):
            raise ValueError(f"Inclusión fuera del alcance público: {relativo}")
        if relativo not in versionados:
            raise ValueError(f"Inclusión no versionada: {relativo}")
        fuente_segura(raiz, relativo)
        elegidos.add(relativo)
    return elegidos


def reunir_archivos(raiz: Path, versionados: set[str], incluir=()) -> dict[str, bytes]:
    iniciales = seleccionar(versionados) | set(incluir)
    if not any(p.startswith("docs/") and p.endswith(".html") for p in iniciales):
        raise ValueError("No hay informes HTML versionados en docs para publicar")
    pendientes = list(sorted(iniciales, reverse=True))
    archivos: dict[str, bytes] = {}
    while pendientes:
        relativo = pendientes.pop()
        if relativo in archivos or relativo in GENERADOS:
            continue
        contenido = fuente_segura(raiz, relativo).read_bytes()
        archivos[relativo] = contenido
        extension = PurePosixPath(relativo).suffix.lower()
        urls: list[str] = []
        if extension == ".html":
            lector = ReferenciasHTML()
            lector.feed(contenido.decode("utf-8"))
            urls = lector.urls
        elif extension == ".css":
            urls = urls_css(contenido.decode("utf-8"))
        for url in urls:
            destino = destino_local(relativo, url)
            if destino is None or destino in GENERADOS:
                continue
            if destino not in versionados:
                raise ValueError(f"Enlace o recurso no versionado/ausente: {relativo} -> {url}")
            if not dependencia_permitida(destino, iniciales):
                raise ValueError(f"Enlace fuera de la selección pública: {relativo} -> {url}")
            if destino not in archivos:
                pendientes.append(destino)
    return archivos


def indice_publico(archivos: dict[str, bytes], incluir=()) -> str:
    def enlace(relativo: str, etiqueta: str | None = None) -> str:
        destino = posixpath.relpath(relativo, "docs")
        return (f'<a href="{html.escape(quote(destino, safe="/"), quote=True)}">'
                f'{html.escape(etiqueta or PurePosixPath(relativo).name)}</a>')

    titulos = {
        "docs/resultados_y_metodologia.html": "Metodología ampliada y guía de resultados",
        "docs/modelo_1km_horario.html": "Informe completo PM₂.₅ y NO₂ a ≈1 km",
        "docs/piloto_perdidas_sin_dmc_20261013.html": "Piloto exploratorio real sin DMC (no modelo aprobado)",
        "docs/estado_ambiental_next_20261014.html": "Rama DMC nueva: pruebas simuladas, no producto nacional",
    }
    orden = {ruta: numero for numero, ruta in enumerate(titulos)}
    secciones = []
    informes = sorted((p for p in archivos if p.startswith("docs/") and p.endswith(".html")
                       and not PurePosixPath(p).name.startswith("_")),
                      key=lambda p: (orden.get(p, len(orden)), p))
    for relativo in informes:
        qmd = str(PurePosixPath(relativo).with_suffix(".qmd"))
        fuente = f' · {enlace(qmd, "Fuente QMD")}' if qmd in archivos else ""
        secciones.append(f"<li>{enlace(relativo, titulos.get(relativo))}{fuente}</li>")
    bloques = ['<section id="informes"><h2>Informes y metodología</h2><ul class="informes">'
               + "\n".join(secciones) + "</ul></section>"]
    for titulo, seleccion in (
        ("Informes históricos", sorted(p for p in archivos if historico_publico(p))),
        ("Presentaciones y documentos", sorted(p for p in archivos if material_publico(p))),
    ):
        if seleccion:
            bloques.append(f"<h2>{titulo}</h2><ul>" + "\n".join(f"<li>{enlace(p)}</li>" for p in seleccion) + "</ul>")
    if incluir:
        bloques.append('<section id="evidencia"><h2>Tablas, figuras y evidencia</h2>'
                       "<p>Abra una carpeta para consultar sus archivos. Las salidas de referencia, "
                       "las variantes de sensibilidad y los pilotos se presentan por separado; "
                       "un ensayo o una prueba no sustituye el resultado de referencia.</p>")
        grupos: dict[str, list[str]] = {}
        for relativo in incluir:
            grupos.setdefault(str(PurePosixPath(relativo).parent), []).append(relativo)

        def clasificar(carpeta: str) -> tuple[int, str, str]:
            partes = PurePosixPath(carpeta).parts
            variante = partes[1] if len(partes) > 1 else ""
            if partes[0] == "output_files" and variante == "modelo_1km":
                categoria = (0, "Modelo horario de referencia")
                nombre = "Modelo horario de referencia"
            elif variante in {"modelo_1km_v2", "modelo_1km_v3", "modelo_o3_next"}:
                categoria = (2, "Desarrollo, pilotos y pruebas: no producto aprobado")
                nombre = {
                    "modelo_1km_v2": "Desarrollo ambiental v2",
                    "modelo_1km_v3": "Rama DMC nueva y pruebas simuladas",
                    "modelo_o3_next": "Desarrollo de O₃",
                }[variante]
            elif variante.startswith("modelo_1km_"):
                categoria = (1, "Variantes, sensibilidad y pruebas separadas de la referencia")
                nombre = "Variante " + variante.removeprefix("modelo_1km_").replace("_", " ")
            else:
                categoria = (3, "Superficies, documentación y otros resultados conservados")
                nombre = ("Superficies ambientales" if partes[0] == "output_files"
                          else partes[0].replace("_", " ").capitalize())
                if variante:
                    nombre += " · " + variante.replace("_", " ")
            if len(partes) > 2:
                nombre += " · " + " / ".join(
                    "Figuras" if p == "figures" else p.replace("_", " ") for p in partes[2:]
                )
            return (*categoria, nombre)

        anterior = None
        for carpeta in sorted(grupos, key=lambda p: (*clasificar(p)[:2], p)):
            numero, categoria, nombre = clasificar(carpeta)
            if (numero, categoria) != anterior:
                bloques.append(f"<h3>{html.escape(categoria)}</h3>")
                anterior = (numero, categoria)
            rutas = sorted(grupos[carpeta])
            tipos: dict[str, int] = {}
            for relativo in rutas:
                extension = PurePosixPath(relativo).suffix.lstrip(".").upper()
                tipos[extension] = tipos.get(extension, 0) + 1
            resumen = " · ".join(f"{tipo}: {cantidad}" for tipo, cantidad in sorted(tipos.items()))
            bloques.append(
                f"<details><summary>{html.escape(nombre)}"
                f'<span class="cantidad">{len(rutas)} archivos · {html.escape(resumen)}</span></summary>'
                f'<p class="ruta"><code>{html.escape(carpeta)}</code></p><ul>'
                + "\n".join(f"<li>{enlace(p)}</li>" for p in rutas) + "</ul></details>"
            )
        bloques.append("</section>")
    return ("<!doctype html>\n<html lang=\"es\"><head><meta charset=\"utf-8\">"
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            "<title>Air-Pollution · Resultados y documentación</title>"
            "<style>:root{color-scheme:light;--borde:#ced8e3;--azul:#075681}"
            "*{box-sizing:border-box}body{font:1rem/1.65 system-ui,sans-serif;max-width:72rem;"
            "margin:0 auto;padding:2rem 1.25rem;color:#202a36;background:#fff}a{color:var(--azul);"
            "text-underline-offset:.15em}a:focus-visible,summary:focus-visible{outline:3px solid #d58a11;"
            "outline-offset:4px}li{margin:.55rem 0;overflow-wrap:anywhere}h1,h2,h3{line-height:1.25}"
            "h1{font-size:clamp(2rem,6vw,3rem);margin-bottom:.25rem}h2{margin-top:2.25rem}"
            "header{border-bottom:2px solid var(--borde);padding-bottom:1.25rem}"
            ".subtitulo{font-size:1.25rem;color:#42536a;margin-top:0}nav{display:flex;gap:1rem;"
            "flex-wrap:wrap;margin-top:1.25rem}section{scroll-margin-top:1rem}"
            ".aviso{background:#eff5fa;border-left:4px solid var(--azul);padding:.8rem 1rem}"
            ".informes{padding-left:1.3rem}.informes li{padding:.25rem 0}"
            "details{border:1px solid var(--borde);border-radius:.45rem;margin:.75rem 0;padding:.75rem 1rem}"
            "summary{cursor:pointer;font-weight:650;overflow-wrap:anywhere}"
            ".cantidad{display:block;font-weight:400;font-size:.9rem;color:#475b70;padding-left:1rem}"
            ".ruta{font-size:.85rem;color:#475b70;overflow-wrap:anywhere}code{font-size:.9em}"
            "@media(max-width:40rem){body{padding:1rem}.cantidad{padding-left:0}"
            "details{padding:.65rem}.informes li{margin-bottom:1rem}}</style>"
            "</head><body><header><h1>Air-Pollution</h1>"
            '<p class="subtitulo">Resultados ambientales, metodología y estimación de PM₂.₅ y NO₂</p>'
            "<p>Este portal reúne los informes existentes, sus fuentes y las tablas y figuras públicas "
            "versionadas hasta la estimación ambiental horaria a aproximadamente 1 km. "
            "Los informes conservan sus resultados, unidades, cobertura y limitaciones originales.</p>"
            '<p class="aviso">Publicar estos documentos no recalcula resultados: no se ejecutan modelos, '
            "informes científicos ni descargas. Las referencias históricas, los pilotos reales y las "
            "pruebas simuladas están diferenciados y no equivalen a un nuevo producto nacional aprobado.</p>"
            '<nav aria-label="Secciones"><a href="#informes">Informes y metodología</a>'
            + ('<a href="#evidencia">Tablas y figuras por carpeta</a>' if incluir else "")
            + "</nav></header><main>"
            + "\n".join(bloques) + "</main></body></html>\n")


def validar_enlaces(archivos: dict[str, bytes]) -> None:
    """Comprobación final sobre el artefacto, no sobre el filesystem local."""
    for relativo, contenido in archivos.items():
        if not relativo.endswith(".html"):
            continue
        lector = ReferenciasHTML()
        lector.feed(contenido.decode("utf-8"))
        for url in lector.urls:
            destino = destino_local(relativo, url)
            if destino is not None and destino not in archivos:
                raise ValueError(f"Enlace no incluido en el artefacto: {relativo} -> {url}")


def preparar(raiz: Path, salida: Path, incluir=(), manifiesto=None) -> dict:
    raiz = Path(raiz)
    salida = Path(salida)
    if raiz.is_symlink() or not raiz.is_dir():
        raise ValueError("La raíz del repositorio debe ser un directorio real")
    raiz = raiz.resolve(strict=True)
    if salida.exists() or salida.is_symlink():
        raise ValueError(f"La salida ya existe; no se sobrescribe ni se borra: {salida}")
    if not salida.parent.is_dir() or salida.parent.is_symlink():
        raise ValueError("El directorio padre de la salida debe existir y no ser un symlink")
    salida = salida.parent.resolve(strict=True) / salida.name
    versionados = archivos_versionados(raiz)
    explicitos = inclusiones_publicas(raiz, versionados, incluir, manifiesto)
    archivos = reunir_archivos(raiz, versionados, explicitos)
    archivos["docs/index.html"] = indice_publico(archivos, explicitos).encode("utf-8")
    archivos["index.html"] = (
        '<!doctype html><html lang="es"><head><meta charset="utf-8">'
        '<meta http-equiv="refresh" content="0; url=./docs/">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>Air-Pollution</title></head><body>'
        '<p><a href="./docs/">Abrir resultados y documentación de Air-Pollution</a></p>'
        '</body></html>\n'
    ).encode("utf-8")
    archivos[".nojekyll"] = b""
    validar_enlaces(archivos)
    # Todos los enlaces y fuentes se comprueban antes de crear el destino.
    # mkdir(exist_ok=False) y open('xb') protegen contra carreras/sobrescrituras.
    salida.mkdir(exist_ok=False)
    for relativo, contenido in sorted(archivos.items()):
        destino = salida / relativo
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("xb") as handle:
            handle.write(contenido)
        if hashlib.sha256(destino.read_bytes()).digest() != hashlib.sha256(contenido).digest():
            raise ValueError(f"Copia no íntegra: {relativo}")
    return {"salida": str(salida), "archivos": sorted(archivos), "cantidad_archivos": len(archivos),
            "inclusiones_explicitas": sorted(explicitos),
            "bytes": sum(map(len, archivos.values())),
            "nota": "Sólo contenido público versionado; renders y fuentes copiados sin modificaciones"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True, help="Directorio NUEVO del artefacto estático")
    parser.add_argument("--include", action="append", default=[], metavar="RUTA",
                        help="Archivo público versionado exacto (repetible; no directorios/globs)")
    parser.add_argument("--include-manifest", type=Path, metavar="JSON",
                        help='Manifiesto versionado del repositorio: {"include": [rutas exactas]}')
    args = parser.parse_args(argv)
    try:
        resultado = preparar(args.root, args.output, args.include, args.include_manifest)
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError) as exc:
        parser.exit(2, f"No se preparó GitHub Pages: {exc}\n")
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
