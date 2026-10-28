"""Pruebas del paquete: fachada, grafo de módulos, índice de §9, nombres, escritura, privacidad y S10 de la batería.

Dueño: I0 (coordinador); ``PruebasS10`` es de I22 (ola 6). Las que llevan «sNN» son la prueba NN de §9 del texto.
Leen, sin escribir, el texto vigente v2.3 con su sha256 (los nombres de la fachada y la numeración de §9); si falta, se
omiten con el motivo y no se dan por aprobadas. Todo lo demás se lee por AST, sin importar nada. Las de subproceso
corren el intérprete actual con -B -I y terminan antes de devolver. Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s meteo_combinada/tests -t .
"""
import sys

sys.dont_write_bytecode = True

import ast  # noqa: E402
import hashlib  # noqa: E402
import importlib  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from meteo_combinada import meteo_combinada, umbrales  # noqa: E402

_PRUEBAS = Path(__file__).resolve().parent
_PAQUETE = _PRUEBAS.parent
_APH = _RAIZ.parent.parent / "Air-Pollution-Health-Chile"
POR_IMPLEMENTAR = "por implementar"
_PATRON_S = re.compile(r"test_s(\d{2})_")
_S_DEL_TEXTO = re.compile(r"^- \*\*S(\d+),", re.MULTILINE)

# §1 del diseño: «Depende de» de cada módulo (sólo módulos del paquete). orquestacion: «los de ciencia, más ceguera,
# sinca_meteo y entorno» se lee como todo lo de las capas 0 a 5 salvo sintetico, más salidas (escribe sus unidades
# por salidas, la única escritura; §0, regla 8). La fachada no importa nada al cargarse. politicas usa además numerico
# (la regla `quality` de QFE va de p_std(z_s) − 80 a p_std(z_s) + 50, §2.3): diferencia con §1 del diseño, anotada en
# COORDINACION_M1.md («Ola 2: encargos»).
_BASE = ("tipos", "constantes", "umbrales")
DEPENDENCIAS = {
    "tipos": (), "constantes": (), "umbrales": (), "entorno": (),
    "fijados": ("entorno",), "numerico": ("constantes",), "ceguera": ("entorno",), "sintetico": (),
    "politicas": (*_BASE, "numerico", "entorno", "fijados"),
    "estaticas_nasadem": (*_BASE, "numerico", "entorno"),
    "fondo_era5l": (*_BASE, "numerico", "entorno"),
    "particiones": (*_BASE, "numerico"),
    "homogeneidad": (*_BASE, "numerico"),
    "sinca_meteo": (*_BASE, "entorno"),
    "decision": _BASE,
    "salidas": ("tipos", "umbrales", "entorno", "ceguera"),
    "qc_dmc_meteo": (*_BASE, "numerico", "fijados", "politicas", "homogeneidad", "fondo_era5l"),
    "candidatos": (*_BASE, "numerico", "particiones", "homogeneidad"),
    "validacion": (*_BASE, "numerico", "particiones"),
    "tendencias": (*_BASE, "numerico", "candidatos", "fondo_era5l"),
    "producto": (*_BASE, "numerico", "fondo_era5l", "candidatos"),
    "salud": (*_BASE, "numerico", "fijados", "producto", "fondo_era5l"),      # ola 5: PED-1 de I18 (SAL-12)
    "ambiental": (*_BASE, "fijados", "producto", "fondo_era5l", "candidatos"),
    "orquestacion": (*_BASE, "entorno", "fijados", "numerico", "ceguera", "politicas", "estaticas_nasadem",
                     "fondo_era5l", "particiones", "homogeneidad", "sinca_meteo", "decision", "salidas",
                     "qc_dmc_meteo", "candidatos", "validacion", "tendencias", "producto", "salud", "ambiental"),
    "costo": ("sintetico", "candidatos", "tendencias", "producto", "ambiental", "orquestacion", "entorno",
              "tipos", "constantes", "fijados", "fondo_era5l", "particiones", "politicas", "salud",
              "ceguera"),   # ola 6: PED-1 y PED-3 de I21
    "addendum": ("umbrales", "constantes", "fijados", "entorno", "ceguera"),
    "verificar_meteo_combinada": ("orquestacion", "salidas", "costo", "addendum", "ceguera", "fijados", "umbrales",
                                  "entorno", "politicas", "tendencias", "salud", "tipos", "constantes"),   # ola 6: PED-1 de I22
    "meteo_combinada": (),
}
# §1 del diseño, «Grafo, por capas y sin ciclos». «fuera»: sintetico y la fachada.
CAPAS = {
    "tipos": 0, "constantes": 0, "umbrales": 0, "entorno": 0,
    "fijados": 1, "numerico": 1, "ceguera": 1,
    "politicas": 2, "estaticas_nasadem": 2, "fondo_era5l": 2, "particiones": 2, "homogeneidad": 2, "sinca_meteo": 2,
    "decision": 2, "salidas": 2,
    "qc_dmc_meteo": 3, "candidatos": 3, "validacion": 3,
    "tendencias": 4, "producto": 4,
    "salud": 5, "ambiental": 5,
    "orquestacion": 6,
    "costo": 7, "addendum": 7,
    "verificar_meteo_combinada": 8,
}
FUERA = ("sintetico", "meteo_combinada")
# Sólo entorno y fijados importan reloj_dmc (§1 del diseño); el resto del reloj llega por funciones de fijados, que
# importa reloj_dmc.politica (import_module) sólo después de comprobar las huellas de su clausura (MC-17).
RELOJ_PERMITIDO = {"entorno": {"reloj_dmc.entorno"},
                   "fijados": {"reloj_dmc.entorno", "reloj_dmc.fijados", "reloj_dmc.politica"}}
# Código fijado que ningún módulo importa: preflight_v3 y runner_v3 (fuera del camino; cargar preflight_v3 fija los
# hilos en 2) y _comun_modelo/_common (sólo se leen por AST).
NUNCA_IMPORTADOS = ("preflight_v3", "runner_v3", "_comun_modelo", "_common", "dmc_features", "meteorologia_v2",
                    "meteo_civil_v3", "_features")

# Archivos de pruebas que otros implementadores escriben en olas posteriores. Mientras sus pruebas «sNN» sigan con
# unittest.skip(POR_IMPLEMENTAR), el índice las informa como pendientes y omite esa comprobación; en cualquier otro
# archivo, un número con sólo pruebas por implementar es una falla. Queda vacía al cerrar M1.
EN_CURSO: dict[str, str] = {}      # vacía desde el cierre de la ola 6 (2026-10-28)

# Escritura (§0, regla 8): sólo salidas, entorno y sintetico (éste sólo en carpetas temporales).
ESCRIBEN = ("salidas.py", "entorno.py", "sintetico.py")
_METODOS_DE_ESCRITURA = ("to_parquet", "to_csv", "to_netcdf", "to_json", "to_feather", "to_pickle", "to_hdf",
                         "to_excel", "to_sql", "to_zarr", "to_orc", "to_stata", "tofile", "savetxt", "savez",
                         "savez_compressed", "save", "write_bytes", "write_text", "write_table", "write_to_dataset",
                         "mkdir", "makedirs", "escribir_atomico", "touch", "symlink_to", "hardlink_to", "unlink",
                         "rmdir", "mkdtemp", "mkstemp", "TemporaryDirectory", "NamedTemporaryFile", "SpooledTemporaryFile")
# os.replace, os.rename, shutil.copy…: sólo como atributo de os o shutil (str.replace y DataFrame.rename no escriben).
_DE_OS = {"os": ("replace", "rename", "renames", "remove", "unlink", "rmdir", "removedirs", "link", "symlink",
                 "truncate", "ftruncate", "chmod", "utime", "mkfifo"),
          "shutil": ("copy", "copy2", "copyfile", "copytree", "copymode", "copystat", "move", "rmtree")}
# Llamadas con modo: open (y Path.open, gzip.open, tarfile.open…), Dataset de netCDF4, fdopen y los archivos comprimidos.
_CON_MODO = ("open", "Dataset", "fdopen", "ZipFile", "TarFile", "GzipFile", "BZ2File", "LZMAFile")
_MODO = re.compile(r"[rwxabt+]{1,4}")                 # un modo de archivo, no una ruta
_MODOS_DE_ESCRITURA = re.compile(r"[wax+]")
_BANDERAS_DE_ESCRITURA = ("O_WRONLY", "O_RDWR", "O_CREAT", "O_APPEND", "O_TRUNC", "O_EXCL")
# Path.rename(destino) y Path.replace(destino): un solo argumento posicional que no es un texto fijo (str.replace lleva
# dos; Series.rename("nombre") lleva un texto). Una línea que no escribe se marca con «# no-escribe: <motivo>».
_UN_ARGUMENTO = ("rename", "replace")
_MARCA_NO_ESCRIBE = re.compile(r"#\s*no-escribe:\s*\S.{2,}")


def _texto_vigente() -> str:
    """El texto vigente (v2.3), comprobado por sha256; SkipTest si falta."""
    ruta = _APH / umbrales.TEXTO_VIGENTE
    if not ruta.is_file():
        raise unittest.SkipTest(f"falta {ruta.name}; la prueba no se da por aprobada")
    datos = ruta.read_bytes()
    if hashlib.sha256(datos).hexdigest() != umbrales.SHA_TEXTO_VIGENTE:
        raise AssertionError(f"{ruta.name} no es el texto vigente v2.3")
    return datos.decode("utf-8")


def _numeros_de_9(texto: str) -> list[int]:
    a = texto.index("\n## 9. ")
    b = texto.index("\n## 10. ", a)
    return [int(n) for n in _S_DEL_TEXTO.findall(texto[a:b])]


def _modulos() -> list[Path]:
    return sorted(p for p in _PAQUETE.glob("*.py") if p.name != "__init__.py")


def _nombres_importados(arbol: ast.AST) -> set[str]:
    """Nombres con punto que importa un árbol: ``import a.b``, ``from a.b import c`` (a.b y a.b.c), las importaciones
    relativas (como meteo_combinada.…) y ``importlib.import_module("…")`` o ``__import__("…")`` con texto fijo."""
    nombres: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            nombres.update(a.name for a in nodo.names)
        elif isinstance(nodo, ast.ImportFrom):
            base = ("meteo_combinada" + (f".{nodo.module}" if nodo.module else "")) if nodo.level else (nodo.module or "")
            nombres.add(base)
            nombres.update(f"{base}.{a.name}" for a in nodo.names if a.name != "*")
        elif isinstance(nodo, ast.Call) and nodo.args and isinstance(nodo.args[0], ast.Constant) \
                and isinstance(nodo.args[0].value, str):
            f = nodo.func
            nombre = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if nombre in ("import_module", "__import__"):
                nombres.add(nodo.args[0].value)
    return nombres


def _importaciones(ruta: Path) -> tuple[set[str], set[str], set[str]]:
    """(módulos del paquete, módulos de reloj_dmc, todas las partes de los nombres importados) de un archivo."""
    nombres = _nombres_importados(ast.parse(ruta.read_text(encoding="utf-8"), filename=ruta.name))
    propias = {n.split(".")[1] for n in nombres if n.startswith("meteo_combinada.")}
    reloj = {".".join(n.split(".")[:2]) for n in nombres if n.startswith("reloj_dmc.")}
    otras = {parte for n in nombres for parte in n.split(".")}
    return propias, reloj, otras


def _escrituras(fuente: str, nombre_archivo: str) -> list[str]:
    """«archivo:línea: llamada» de cada escritura que se ve por AST (§0, regla 8)."""
    lineas = fuente.splitlines()
    hallados = []
    for nodo in ast.walk(ast.parse(fuente)):
        if not isinstance(nodo, ast.Call):
            continue
        if _MARCA_NO_ESCRIBE.search(lineas[nodo.lineno - 1]):
            continue
        f = nodo.func
        nombre = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
        donde = f"{nombre_archivo}:{nodo.lineno}"
        if nombre in _CON_MODO:
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "os":
                banderas = {n.attr for a in nodo.args[1:2] for n in ast.walk(a) if isinstance(n, ast.Attribute)}
                banderas |= {n.id for a in nodo.args[1:2] for n in ast.walk(a) if isinstance(n, ast.Name)}
                if banderas & set(_BANDERAS_DE_ESCRITURA):
                    hallados.append(f"{donde}: os.open con {sorted(banderas & set(_BANDERAS_DE_ESCRITURA))}")
                continue
            candidatos = [*nodo.args[:2], *(k.value for k in nodo.keywords if k.arg == "mode")]
            modos = [a.value for a in candidatos if isinstance(a, ast.Constant) and isinstance(a.value, str)
                     and _MODO.fullmatch(a.value)]
            if any(_MODOS_DE_ESCRITURA.search(m) for m in modos):
                hallados.append(f"{donde}: {nombre}(…, {modos})")
            elif nombre == "open" and not modos and (len(nodo.args) >= 2 or any(k.arg == "mode" for k in nodo.keywords)):
                hallados.append(f"{donde}: {nombre} con un modo que no es un texto fijo")
        elif nombre in _METODOS_DE_ESCRITURA:
            hallados.append(f"{donde}: {nombre}")
        elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and nombre in _DE_OS.get(f.value.id, ()):
            hallados.append(f"{donde}: {f.value.id}.{nombre}")
        elif (isinstance(f, ast.Attribute) and nombre in _UN_ARGUMENTO and len(nodo.args) == 1 and not nodo.keywords
              and not (isinstance(nodo.args[0], ast.Constant) and isinstance(nodo.args[0].value, str))):
            hallados.append(f"{donde}: .{nombre}(destino)")
    return hallados


def _es_por_implementar(decorador: ast.expr) -> bool:
    if not isinstance(decorador, ast.Call) or not decorador.args:
        return False
    funcion = decorador.func
    nombre = funcion.attr if isinstance(funcion, ast.Attribute) else getattr(funcion, "id", None)
    arg = decorador.args[0]
    return nombre == "skip" and ((isinstance(arg, ast.Name) and arg.id == "POR_IMPLEMENTAR")
                                 or (isinstance(arg, ast.Constant) and arg.value == POR_IMPLEMENTAR))


def _pruebas_por_numero() -> dict[int, list[tuple[str, str, bool]]]:
    """Número NN → [(archivo, Clase.prueba, por implementar)] de toda prueba «test_sNN_…» de tests/ (AST)."""
    salida: dict[int, list[tuple[str, str, bool]]] = {}
    for ruta in sorted(_PRUEBAS.glob("test_*.py")):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=ruta.name)
        for clase in (n for n in arbol.body if isinstance(n, ast.ClassDef)):
            clase_pendiente = any(_es_por_implementar(d) for d in clase.decorator_list)
            for f in clase.body:
                if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and (m := _PATRON_S.match(f.name)):
                    pendiente = clase_pendiente or any(_es_por_implementar(d) for d in f.decorator_list)
                    salida.setdefault(int(m.group(1)), []).append((ruta.name, f"{clase.name}.{f.name}", pendiente))
    return salida


def _subproceso(codigo: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run([sys.executable, "-B", "-I", "-c", codigo, str(_RAIZ)], cwd=tmp, capture_output=True,
                           text=True, timeout=300, check=False)
    if r.returncode != 0:
        raise AssertionError(f"El subproceso falló:\n{r.stderr}")
    return r.stdout.strip().splitlines()[-1]


class PruebasFachada(unittest.TestCase):
    def test_fachada_expone_los_nombres_del_texto(self):
        """Cada nombre de NOMBRES_TEXTO está entre comillas invertidas en el texto vigente y es el mismo objeto de su
        módulo."""
        texto = _texto_vigente()
        self.assertEqual(meteo_combinada.__all__, sorted(meteo_combinada.NOMBRES_TEXTO))
        for nombre in meteo_combinada.NOMBRES_TEXTO:
            with self.subTest(nombre=nombre):
                self.assertRegex(texto, rf"`{nombre}\b")
                objeto = getattr(meteo_combinada, nombre)
                self.assertTrue(callable(objeto))
                modulo = importlib.import_module(meteo_combinada.modulo_de(nombre))
                self.assertIs(objeto, getattr(modulo, nombre))
                self.assertEqual(objeto.__module__, modulo.__name__)
                self.assertIn(nombre, dir(meteo_combinada))

    def test_nombre_ajeno_al_texto_no_existe(self):
        for nombre in ("normalizar_artefacto", "tabla_ancha", "no_existe"):
            with self.subTest(nombre=nombre), self.assertRaises(AttributeError):
                getattr(meteo_combinada, nombre)
        with self.assertRaises(KeyError):
            meteo_combinada.modulo_de("no_existe")

    def test_fachada_es_perezosa(self):
        """Importar la fachada no carga otros módulos del paquete (ni numpy, pandas ni zoneinfo)."""
        codigo = ("import sys; sys.path.insert(0, sys.argv[1]); from meteo_combinada import meteo_combinada; "
                  "print(sorted(m for m in sys.modules if m.split('.')[0] == 'meteo_combinada') "
                  "+ [m for m in ('numpy', 'pandas', 'zoneinfo', 'reloj_dmc') if m in sys.modules])")
        self.assertEqual(_subproceso(codigo), str(["meteo_combinada", "meteo_combinada.meteo_combinada"]))


class PruebasGrafo(unittest.TestCase):
    def test_modulos_del_paquete_son_los_del_diseno(self):
        self.assertEqual(sorted(p.stem for p in _modulos()), sorted(DEPENDENCIAS))
        self.assertEqual(set(DEPENDENCIAS), set(CAPAS) | set(FUERA))

    def test_grafo_por_capas_y_sin_ciclos(self):
        """Cada módulo importa sólo sus dependencias de §1 (AST, también dentro de funciones), y éstas son de capas
        anteriores; así el grafo no tiene ciclos."""
        for modulo, deps in DEPENDENCIAS.items():
            for d in deps:
                with self.subTest(modulo=modulo, dependencia=d):
                    if modulo in CAPAS and d in CAPAS:
                        self.assertLess(CAPAS[d], CAPAS[modulo])
                    else:
                        self.assertIn(d, ("sintetico",))      # sólo costo usa sintetico, que está fuera
        for ruta in _modulos():
            propias, _, _ = _importaciones(ruta)
            with self.subTest(modulo=ruta.stem):
                self.assertEqual(sorted(propias - set(DEPENDENCIAS[ruta.stem])), [],
                                 "importa módulos que §1 no le permite")

    def test_sintetico_y_la_fachada_no_importan_el_paquete(self):
        for nombre in FUERA:
            propias, reloj, _ = _importaciones(_PAQUETE / f"{nombre}.py")
            self.assertEqual((propias, reloj), (set(), set()), nombre)

    def test_solo_entorno_y_fijados_importan_reloj(self):
        for ruta in _modulos():
            _, reloj, _ = _importaciones(ruta)
            with self.subTest(modulo=ruta.stem):
                self.assertEqual(sorted(reloj - RELOJ_PERMITIDO.get(ruta.stem, set())), [])

    def test_lector_de_importaciones(self):
        """El grafo ve import_module y __import__ con texto fijo, las importaciones relativas y los nombres con punto
        («from v3 import preflight_v3»)."""
        fuente = ("import importlib\nfrom v3 import preflight_v3\nimport v3.runner_v3\n"
                  "m = importlib.import_module('reloj_dmc.politica')\nn = __import__('_comun_modelo')\n"
                  "from . import tipos\nfrom .numerico import p_std\n")
        nombres = _nombres_importados(ast.parse(fuente))
        self.assertTrue({"v3.preflight_v3", "v3.runner_v3", "reloj_dmc.politica", "_comun_modelo",
                         "meteo_combinada.tipos", "meteo_combinada.numerico"} <= nombres, nombres)
        partes = {p for n in nombres for p in n.split(".")}
        self.assertTrue({"preflight_v3", "runner_v3", "_comun_modelo"} <= partes)

    def test_codigo_fijado_nunca_se_importa_por_nombre(self):
        """preflight_v3, runner_v3, _comun_modelo, _common y el resto del código fijado llegan sólo por fijados (por
        ruta y huella) o por AST, nunca por una importación."""
        for ruta in _modulos():
            _, _, otras = _importaciones(ruta)
            with self.subTest(modulo=ruta.stem):
                self.assertEqual(sorted(otras & set(NUNCA_IMPORTADOS)), [])

    def test_base_sin_numpy(self):
        """tipos, constantes y umbrales no cargan numpy ni pandas (§1 del diseño, MC-36)."""
        codigo = ("import sys; sys.path.insert(0, sys.argv[1]); "
                  "from meteo_combinada import tipos, constantes, umbrales; "
                  "print([m for m in ('numpy', 'pandas') if m in sys.modules])")
        self.assertEqual(_subproceso(codigo), "[]")

    def test_el_paquete_fija_los_hilos_si_numpy_no_esta_cargado(self):
        """MC-36: al importarse, OMP, OPENBLAS y MKL en «1»."""
        codigo = ("import os, sys; sys.path.insert(0, sys.argv[1]); "
                  "[os.environ.__setitem__(v, '7') for v in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS')]; "
                  "import meteo_combinada; "
                  "print([os.environ[v] for v in meteo_combinada.VARIABLES_HILOS])")
        self.assertEqual(_subproceso(codigo), str(["1", "1", "1"]))


class PruebasIndice9(unittest.TestCase):
    def test_indice_de_9_cada_prueba_tiene_prueba(self):
        """Cada prueba S1 a S16 de §9 del texto vigente tiene al menos una prueba «sNN» en tests/, y no hay pruebas de
        números que §9 no tiene."""
        numeros = _numeros_de_9(_texto_vigente())
        self.assertEqual(numeros, list(range(1, len(numeros) + 1)))
        self.assertEqual(len(numeros), 16)
        indice = _pruebas_por_numero()
        self.assertEqual(sorted(set(numeros) - set(indice)), [], "pruebas de §9 sin ninguna prueba «sNN»")
        self.assertEqual(sorted(set(indice) - set(numeros)), [], "pruebas «sNN» de números que §9 no tiene")
        for numero in numeros:
            nombres = [n for _, n, _ in indice[numero]]
            self.assertEqual(len(nombres), len(set(nombres)), nombres)

    def test_indice_de_9_sin_pruebas_por_implementar(self):
        """Ningún número de §9 depende sólo de pruebas del esqueleto, salvo los que sólo las tienen en archivos de
        EN_CURSO: ésos se informan y la prueba se omite."""
        indice = _pruebas_por_numero()
        solo_pendientes = {n: lista for n, lista in sorted(indice.items()) if all(p for _, _, p in lista)}
        ajenos = {n: [f"{a}::{t}" for a, t, _ in lista] for n, lista in solo_pendientes.items()
                  if any(a not in EN_CURSO for a, _, _ in lista)}
        self.assertEqual(ajenos, {}, "números de §9 con sólo pruebas por implementar fuera de los archivos en curso")
        if solo_pendientes:
            detalle = "; ".join(f"S{n}: " + ", ".join(sorted({EN_CURSO[a] for a, _, _ in lista}))
                                for n, lista in solo_pendientes.items())
            self.skipTest(f"pendientes de olas posteriores, que deben implementarse antes de cerrar M1: {detalle}")

    def test_en_curso_es_de_archivos_que_existen(self):
        for archivo in EN_CURSO:
            self.assertTrue((_PRUEBAS / archivo).is_file(), archivo)

    def test_en_curso_vacia_al_cerrar_m1(self):
        """Al cerrar M1 no quedan archivos en curso: ningún número de §9 se omite (se exige desde el cierre de las olas
        4 a 6, 2026-10-28; P141)."""
        self.assertEqual(EN_CURSO, {})


class PruebasPaquete(unittest.TestCase):
    def test_ningun_archivo_se_llama_descargar_ni_download(self):
        """§8 del texto y §0, regla 6."""
        nombres = [p.name for p in _PAQUETE.rglob("*") if p.name.startswith(("descargar_", "download_"))]
        self.assertEqual(nombres, [])

    def test_escritura_solo_en_salidas_entorno_y_sintetico(self):
        """§0, regla 8 (AST): open en modo de escritura, Dataset(…, "w"), to_parquet, write_bytes, write_text, mkdir y
        las demás llamadas que escriben, sólo en salidas.py, entorno.py y sintetico.py."""
        hallados = []
        for ruta in _modulos():
            if ruta.name not in ESCRIBEN:
                hallados += _escrituras(ruta.read_text(encoding="utf-8"), ruta.name)
        self.assertEqual(hallados, [])

    def test_detector_de_escrituras(self):
        """El detector ve cada forma de escribir (también Path.open("w"), os.open con banderas, Path.rename, ZipFile y
        un modo en una variable) y no confunde str.replace, Series.rename("x") ni una lectura."""
        fuente = ("open(r)\nopen(r, 'rb')\nopen(r, 'w')\nPath(r).open('a')\ngzip.open(r, 'wt')\nopen(r, modo)\n"
                  "os.open(r, os.O_WRONLY | os.O_CREAT)\nos.open(r, os.O_RDONLY)\nZipFile(r, mode='w')\n"
                  "Dataset(r, 'r')\nDataset(r, 'a')\ns.replace('a', 'b')\nx.rename('y')\np.rename(destino)\n"
                  "p.replace(destino)  # no-escribe: es un ejemplo\ndf.to_feather(r)\nnp.savetxt(r, x)\n"
                  "tempfile.TemporaryDirectory()\nos.replace(a, b)\nshutil.copy(a, b)\ntexto.replace(a, b)\n")
        lineas = sorted(int(h.split(":")[1]) for h in _escrituras(fuente, "x.py"))
        self.assertEqual(lineas, [3, 4, 5, 6, 7, 9, 11, 14, 16, 17, 18, 19, 20])

    def test_privacidad_del_paquete(self):
        """Ningún archivo del paquete (código, pruebas y documentos) trae una ruta de la carpeta de usuario, la carpeta personal ni la arroba, salvo
        los decoradores de Python (la misma regla de privacidad del reloj; AP es público)."""
        decorador = re.compile(r"^\s*\x40[A-Za-z_][\w.]*(?:\(.*)?$")      # \x40: la arroba
        casa = str(Path.home())
        hallados = []
        for ruta in sorted(p for p in _PAQUETE.rglob("*") if p.is_file() and p.suffix in (".py", ".md", ".json", ".txt")):
            for n, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), start=1):
                if decorador.match(linea):
                    continue
                if "/" + "Users" + "/" in linea or casa in linea or chr(64) in linea:
                    hallados.append(f"{ruta.relative_to(_PAQUETE)}:{n}")
        self.assertEqual(hallados, [])

    def test_esqueleto_importa_sin_volumes_ni_pycache(self):
        """Entrega de la ola 0: todos los módulos importan con el intérprete fijado, sin abrir, listar ni consultar
        nada bajo /Volumes (gancho de auditoría, más envoltorios de os.stat, os.lstat y os.access, que no tienen
        evento) y sin dejar __pycache__. La ruta se juzga léxica, sin resolverla."""
        codigo = (
            "import json, os, pkgutil, importlib, sys\n"
            "accesos = []\n"
            "def revisar(evento, ruta):\n"
            "    if isinstance(ruta, (str, bytes, os.PathLike)):\n"
            "        texto = os.path.abspath(os.fsdecode(os.fspath(ruta)))\n"
            "        if texto.casefold().startswith('/volumes'):\n"
            "            accesos.append([evento, 'VOLUMES'])\n"
            "def gancho(evento, args):\n"
            "    if evento in ('open', 'os.listdir', 'os.scandir', 'glob.glob', 'os.mkdir', 'os.rename', 'os.remove',\n"
            "                  'os.chdir', 'os.walk', 'shutil.copyfile', 'os.symlink', 'os.link'):\n"
            "        revisar(evento, args[0] if args else None)\n"
            "def envolver(f, nombre):\n"
            "    def g(ruta, *a, **k):\n"
            "        revisar(nombre, ruta)\n"
            "        return f(ruta, *a, **k)\n"
            "    return g\n"
            "os.stat, os.lstat, os.access = envolver(os.stat, 'stat'), envolver(os.lstat, 'lstat'), envolver(os.access, 'access')\n"
            "sys.addaudithook(gancho)\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "import meteo_combinada\n"
            "nombres = sorted(m.name for m in pkgutil.iter_modules(meteo_combinada.__path__) if m.name != 'tests')\n"
            "for n in nombres:\n"
            "    importlib.import_module('meteo_combinada.' + n)\n"
            "print(json.dumps({'modulos': len(nombres), 'accesos': accesos}))\n"
        )
        antes = sorted(str(p) for p in _PAQUETE.rglob("__pycache__"))
        r = json.loads(_subproceso(codigo))
        self.assertEqual(r["modulos"], len(DEPENDENCIAS))
        self.assertEqual(r["accesos"], [])
        self.assertEqual(sorted(str(p) for p in _PAQUETE.rglob("__pycache__")), antes)
        self.assertEqual(antes, [], "hay __pycache__ en el paquete")


_DISENO = _PAQUETE / "DISENO_IMPLEMENTACION_M1.md"
_ANEXO_FIRMAS = "\n## Anexo F. Firmas públicas"
_BLOQUE = ("```python\n", "\n```\n")


def _anexo_firmas() -> tuple[str, str]:
    """(programa, lista) del anexo de firmas del diseño. §3: «Al cerrar M1 se regenera un anexo de firmas por AST del
    código, con el programa del Anexo F del reloj (cambia sólo la lista `ORDEN`)». La lista va del bloque del programa
    al título siguiente o al final."""
    texto = _DISENO.read_text(encoding="utf-8")
    inicio = texto.index(_ANEXO_FIRMAS)
    a = texto.index(_BLOQUE[0], inicio) + len(_BLOQUE[0])
    b = texto.index(_BLOQUE[1], a)
    fin = texto.find("\n## ", b)
    return texto[a:b] + "\n", texto[b + len(_BLOQUE[1]):None if fin < 0 else fin]


def _modulos_de_1() -> list[str]:
    """Los módulos de la tabla de §1 del diseño, en su orden."""
    texto = _DISENO.read_text(encoding="utf-8")
    return re.findall(r"^\| `([a-z_0-9]+)\.py`", texto[texto.index("\n## 1."):texto.index("\n## 2.")], re.MULTILINE)


class PruebasAnexoFirmas(unittest.TestCase):
    """§3 del diseño: el anexo de firmas por AST del código, regenerado al cerrar M1 (cierre de las olas 4 a 6)."""

    def test_anexo_de_firmas_en_el_orden_de_1(self):
        """``ORDEN`` es la lista de módulos de §1, en su orden, y nombra todos los módulos del paquete."""
        programa, _ = _anexo_firmas()
        orden = [ast.literal_eval(n.value) for n in ast.parse(programa).body
                 if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "ORDEN" for t in n.targets)]
        self.assertEqual(len(orden), 1)
        self.assertEqual(list(orden[0]), _modulos_de_1())
        self.assertEqual(sorted(orden[0]), sorted(p.stem for p in _modulos()))

    def test_anexo_de_firmas_al_dia(self):
        """La lista del anexo es la que da su programa con el código de hoy: si cambia una firma, se regenera."""
        programa, lista = _anexo_firmas()
        with tempfile.TemporaryDirectory() as tmp:
            script, salida = Path(tmp) / "anexo_f.py", Path(tmp) / "firmas.md"
            script.write_text(programa, encoding="utf-8")
            r = subprocess.run([sys.executable, "-B", "-I", str(script), str(_PAQUETE), str(salida)], cwd=tmp,
                               capture_output=True, text=True, timeout=300, check=False)
            self.assertEqual(r.returncode, 0, r.stderr)
            generada = salida.read_text(encoding="utf-8")
        self.assertEqual(lista.strip(), generada.strip(), "el anexo de firmas no es el del código: regenéralo (§3)")


class PruebasS10(unittest.TestCase):
    """S10 de la batería de M1 (I22, ola 6; VER-1 de ``verificar_meteo_combinada``). Para no correr la suite dentro de
    la suite, la batería corre un subconjunto: unas sondas hechas aquí (``correr_bateria(…, suite=…)``) o, por la línea
    de comandos, ``--sintetico --solo test_numerico``; su salida va a una carpeta temporal (``entorno.rutas_sinteticas``).
    Las sondas de /Volumes no consultan /Volumes: el registro las niega antes (``open``, ``os.stat``) o se le pasan sin
    tocar el disco (``ceguera.anunciar_acceso``). Una escritura en AP o APH apunta a una carpeta que no existe, así que
    ni con la guarda rota llegaría a escribir. Los insumos de datos de S14 sólo se dejan leer mientras corre una
    ``PruebasS14`` (MC-31; VER-1)."""

    @staticmethod
    def _instantanea() -> dict:
        """(tamaño, mtime) de cada archivo del paquete y de la auditoría del producto en APH (sólo lectura), sin los
        ``.md``: los documentos que el coordinador edita mientras corre la suite (revisión de la ola 6); la batería no
        escribe ningún ``.md`` fuera de su subcarpeta de LOCAL."""
        salida = {}
        for base in (_PAQUETE, _APH / "auditoria" / "20261023" / "meteo_combinada"):
            for p in sorted(base.rglob("*")):
                if p.is_file() and p.suffix.casefold() != ".md":
                    st = p.stat()
                    salida[str(p)] = (st.st_size, st.st_mtime_ns)
        return salida

    @staticmethod
    def _bateria(suite=None, argv=None):
        """(código, resumen, nombres de su subcarpeta de m1) de una batería parcial en una carpeta temporal, sin
        mostrar nada."""
        import contextlib
        import io
        from meteo_combinada import entorno
        from meteo_combinada import verificar_meteo_combinada as V
        with tempfile.TemporaryDirectory() as tmp:
            sint = entorno.rutas_sinteticas(tmp)
            with contextlib.redirect_stdout(io.StringIO()):
                if argv is None:
                    codigo = V.correr_bateria(sint, suite=suite)
                else:
                    codigo = V.main(argv, rutas=sint)
            [m1] = [p for p in entorno.carpeta_salida(sint, "m1").iterdir() if p.is_dir()]   # VER-2: su subcarpeta
            resumen = json.loads((m1 / V.RESUMEN_M1).read_text(encoding="utf-8"))
            nombres = sorted(p.name for p in m1.iterdir())
        return codigo, resumen, nombres

    def test_s10_bateria_en_bloqueo_sobre_volumes_y_repositorios(self):
        """La batería de M1 corre bajo RegistroAccesos en bloqueo: nada se escribe en /Volumes ni en los repositorios;
        sólo S14 y el costo leen las rutas que se nombran (MC-31)."""
        import os
        from meteo_combinada import ceguera, entorno
        from meteo_combinada import verificar_meteo_combinada as V
        importlib.import_module("meteo_combinada.tests.test_salud")       # para que la batería vea los insumos de S14
        reales = entorno.rutas_reales()
        insumos = V._insumos_s14(reales)
        self.assertTrue(insumos, "la batería debe conocer los insumos de S14 (MC-31)")
        repos = (str(reales.ap) + "/", str(reales.aph) + "/")
        de_datos = [p for p in insumos if not p.startswith(repos)]
        self.assertTrue(de_datos)
        prohibida = "/" + "Volumes" + "/meteo_combinada_prueba_inexistente"
        en_ap = Path(reales.ap) / "scripts_modelo_1km" / "meteo_combinada" / "tests" / "no_existe_s10" / "sonda.txt"
        en_aph = Path(reales.aph) / "auditoria" / "no_existe_s10" / "sonda.txt"
        del_reloj = Path(reales.ap) / V.RELOJ_PUBLICACION / "v1" / "politica_reloj_dmc.json"
        corrida_reloj = Path(reales.local) / V.RELOJ_CORRIDAS / "v1" / "no_existe_s10.json"

        class Sondas(unittest.TestCase):
            def test_escribir_en_ap(self_):
                with self_.assertRaises(PermissionError):
                    open(en_ap, "w")

            def test_escribir_en_aph(self_):
                with self_.assertRaises(PermissionError):
                    open(en_aph, "w")

            def test_leer_volumes(self_):
                with self_.assertRaises(PermissionError):
                    os.stat(prohibida + "/x")
                with self_.assertRaises(PermissionError):
                    ceguera.anunciar_acceso(prohibida + "/y")

            def test_leer_lo_del_reloj(self_):
                for ruta in (del_reloj, corrida_reloj):
                    with self_.assertRaises(PermissionError):
                        open(ruta, "rb")

            def test_leer_lo_de_s14_fuera_de_s14(self_):
                # MC-31: fuera de PruebasS14, un insumo de datos de S14 se niega (sin tocar el disco)
                with self_.assertRaises(PermissionError):
                    ceguera.anunciar_acceso(de_datos[0])

            def test_leer_el_codigo(self_):
                with open(V.__file__, "rb") as f:
                    self_.assertTrue(f.read())

        # La ventana de S14 (abrir el registro de sus insumos sólo mientras corre PruebasS14) se prueba con un insumo
        # en una carpeta temporal en test_verificar_meteo_combinada: aquí, dentro de la batería real, la ventana de la
        # batería exterior sigue cerrada y negaría los insumos reales a una PruebasS14 de sonda.
        antes = self._instantanea()
        codigo, r, nombres = self._bateria(unittest.TestLoader().loadTestsFromTestCase(Sondas))
        self.assertEqual(self._instantanea(), antes, "la batería escribió en el paquete o en la auditoría de APH")
        self.assertFalse(en_ap.parent.exists() or en_aph.parent.exists())
        self.assertEqual((r["pruebas"]["corridas"], r["pruebas"]["ok"]), (6, 6), "las sondas debían negarse antes")
        self.assertEqual(r["ceguera"]["accesos"], 7, "dos escrituras, dos de /Volumes, dos del reloj y un insumo de "
                                                     "S14 fuera de PruebasS14")
        # ningún insumo de S14 se leyó fuera de PruebasS14 (MC-31)
        self.assertEqual(r["ceguera"]["lecturas_s14"], 0)
        self.assertTrue(any(p.startswith("/" + "Volumes/") for p in insumos))
        self.assertEqual(codigo, 1)
        self.assertIn("accesos", r["motivos"])
        self.assertEqual([n for n in nombres if n in ("pruebas_m1.txt", "resumen_m1.json", "anexo_a2.json",
                                                      "sha256.json")],
                         ["anexo_a2.json", "pruebas_m1.txt", "resumen_m1.json", "sha256.json"])
        # Por la línea de comandos, con un subconjunto real de la suite: sin accesos, red ni procesos.
        antes = self._instantanea()
        codigo, r, _ = self._bateria(argv=["--sintetico", "--solo", "test_numerico"])
        self.assertEqual(self._instantanea(), antes)
        self.assertGreater(r["pruebas"]["corridas"], 0)
        self.assertEqual((r["pruebas"]["fallas"], r["pruebas"]["errores"]), (0, 0))
        self.assertEqual((r["ceguera"]["accesos"], r["ceguera"]["procesos_vivos"]), (0, 0))
        self.assertTrue(r["modo"]["parcial"])
        self.assertEqual(codigo, 1, "una batería parcial no aprueba M1")
        self.assertIn("parcial", r["motivos"])
        self.assertNotIn("accesos", r["motivos"])

    def test_s10_sin_red_y_sin_procesos_vivos_al_terminar(self):
        """SinRed sobre la batería y conteo de procesos hijos al terminar."""
        import socket
        from meteo_combinada import ceguera
        hijos = []

        class Sondas(unittest.TestCase):
            def test_red(self_):
                with self_.assertRaises(ceguera.RedProhibida):
                    socket.getaddrinfo("localhost", 80)
                with self_.assertRaises(ceguera.RedProhibida):
                    socket.create_connection(("127.0.0.1", 9), timeout=1)

            def test_proceso_que_queda_vivo(self_):
                hijos.append(subprocess.Popen([sys.executable, "-B", "-I", "-c", "import time; time.sleep(120)"],
                                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))

        try:
            codigo, r, _ = self._bateria(unittest.TestLoader().loadTestsFromTestCase(Sondas))
        finally:
            for p in hijos:
                p.kill()
                p.wait(timeout=60)
        self.assertEqual(r["pruebas"]["ok"], 2)
        self.assertGreaterEqual(r["ceguera"]["red_intentos"], 2)
        self.assertGreaterEqual(r["ceguera"]["procesos_vivos"], 1)
        self.assertEqual(codigo, 1)
        self.assertIn("procesos_vivos", r["motivos"])
        self.assertEqual(r["ceguera"]["accesos"], 0)
        # Sin el proceso: ninguno vivo al terminar.
        suite = unittest.TestSuite([Sondas("test_red")])
        _, r, _ = self._bateria(suite)
        self.assertEqual(r["ceguera"]["procesos_vivos"], 0)
        self.assertNotIn("procesos_vivos", r["motivos"])


if __name__ == "__main__":
    unittest.main()
