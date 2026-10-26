"""Pruebas de reloj_dmc.py (fachada de §9 e índice de §8).

Las que llevan «pNN» son el punto NN de §8 (grupos A, B y C). Leen, sin escribir, el texto anclado en C0
(los 23 nombres de §9 y la numeración de §8); si falta, se omiten con el motivo y no se dan por aprobadas.
Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s reloj_dmc/tests -t .
"""
import sys

sys.dont_write_bytecode = True

import ast  # noqa: E402
import hashlib  # noqa: E402
import importlib  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from reloj_dmc import reloj_dmc  # noqa: E402

_PRUEBAS = Path(__file__).resolve().parent
_APH = _RAIZ.parent.parent / "Air-Pollution-Health-Chile"
POR_IMPLEMENTAR = "por implementar"
_PATRON_PUNTO = re.compile(r"test_p(\d{2})_")
_PUNTO_DEL_TEXTO = re.compile(r"(\d+)\. \*\*")             # «16. **Estación UTC:** …» en §8, grupos A a C
_NOMBRES_DEL_TEXTO = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")

# Archivos de pruebas que otros implementadores escriben en paralelo. Mientras sus pruebas «pNN» sigan con
# unittest.skip(POR_IMPLEMENTAR), el índice las informa como pendientes y omite esa comprobación; en cualquier
# otro archivo, un punto con sólo pruebas por implementar es una falla. En la ola 4b fueron test_verificar_reloj_dmc
# y test_bateria; al cerrar C1 (2026-10-25, PEN-3) la lista queda vacía (test_en_curso_vacia_al_cerrar_c1).
EN_CURSO: dict[str, str] = {}
# PEN-5 de C1: un encabezado no puede dar por pendiente una enmienda ya adoptada (la Enmienda 1 está anclada en APH
# 81bb100 desde el 2026-10-24).
_ENMIENDA_COMO_PENDIENTE = re.compile(r"borrador de la Enmienda 1|Enmienda 1[^.;]{0,80}(?:no adoptad|sin adoptar)"
                                      r"|E1-\d+[^.;]{0,60}sin adoptar|borrador sin adoptar")


def _texto_c0() -> str:
    """El texto anclado en C0, comprobado por sha256 (como test_umbrales); SkipTest si falta."""
    from reloj_dmc import umbrales
    ruta = _APH / umbrales.PROTOCOLO_C0
    if not ruta.is_file():
        raise unittest.SkipTest(f"falta {ruta.name} anclado en C0; la prueba no se da por aprobada")
    datos = ruta.read_bytes()
    if hashlib.sha256(datos).hexdigest() != umbrales.SHA_PROTOCOLO_C0:
        raise AssertionError(f"{ruta.name} no es el texto anclado en C0")
    return datos.decode("utf-8")


def _seccion(texto: str, seccion: str) -> str:
    from reloj_dmc import constantes
    tramo = constantes.tramo_de_seccion(texto, seccion)
    if tramo is None:
        raise AssertionError(f"no se halló {seccion} en el texto anclado")
    return tramo


def _nombres_de_9(texto: str) -> list[str]:
    """Los nombres de la viñeta «Código» de §9: «`…/reloj_dmc.py`, con funciones puras: `a`, `b` … y `z`.»"""
    (linea,) = [l for l in _seccion(texto, "§9").splitlines() if "con funciones puras:" in l]
    return _NOMBRES_DEL_TEXTO.findall(linea.split("con funciones puras:", 1)[1])


def _puntos_de_8(texto: str) -> list[int]:
    """Numeración de §8 (grupos A a C): los números que abren un punto «N. **…**»."""
    return [int(m.group(1)) for l in _seccion(texto, "§8").splitlines() if (m := _PUNTO_DEL_TEXTO.match(l))]


def _es_por_implementar(decorador: ast.expr) -> bool:
    """``@unittest.skip(POR_IMPLEMENTAR)`` o ``@unittest.skip("por implementar")`` del esqueleto."""
    if not isinstance(decorador, ast.Call) or not decorador.args:
        return False
    funcion = decorador.func
    nombre = funcion.attr if isinstance(funcion, ast.Attribute) else getattr(funcion, "id", None)
    arg = decorador.args[0]
    return nombre == "skip" and ((isinstance(arg, ast.Name) and arg.id == "POR_IMPLEMENTAR")
                                 or (isinstance(arg, ast.Constant) and arg.value == POR_IMPLEMENTAR))


def _pruebas_por_punto() -> dict[int, list[tuple[str, str, bool]]]:
    """Punto NN → [(archivo, Clase.prueba, por implementar)] de toda prueba «test_pNN_…» de tests/ (AST: nada
    se importa)."""
    salida: dict[int, list[tuple[str, str, bool]]] = {}
    for ruta in sorted(_PRUEBAS.glob("test_*.py")):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=ruta.name)
        for clase in (n for n in arbol.body if isinstance(n, ast.ClassDef)):
            clase_pendiente = any(_es_por_implementar(d) for d in clase.decorator_list)
            for f in clase.body:
                if not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                m = _PATRON_PUNTO.match(f.name)
                if m:
                    pendiente = clase_pendiente or any(_es_por_implementar(d) for d in f.decorator_list)
                    salida.setdefault(int(m.group(1)), []).append((ruta.name, f"{clase.name}.{f.name}", pendiente))
    return salida


class PruebasFachada(unittest.TestCase):
    def test_fachada_expone_los_23_nombres_de_9(self):
        """Cada nombre de §9 resuelve a una función de su módulo (el mismo objeto), en el orden del texto."""
        nombres = _nombres_de_9(_texto_c0())
        self.assertEqual(len(nombres), 23)
        self.assertEqual(list(reloj_dmc.NOMBRES_9), nombres)
        self.assertEqual(reloj_dmc.__all__, sorted(nombres))
        for nombre in nombres:
            with self.subTest(nombre=nombre):
                objeto = getattr(reloj_dmc, nombre)
                self.assertTrue(callable(objeto))
                modulo = importlib.import_module(reloj_dmc.modulo_de(nombre))
                self.assertIs(objeto, getattr(modulo, reloj_dmc.ALIAS_9.get(nombre, nombre)))
                self.assertEqual(objeto.__module__, modulo.__name__)
                self.assertIn(nombre, dir(reloj_dmc))
        self.assertIs(reloj_dmc.e4, importlib.import_module("reloj_dmc.lineas_fisicas").e4p)   # «e4» = E4p
        self.assertEqual(set(reloj_dmc.ALIAS_9) - set(nombres), set())

    def test_nombre_ajeno_a_9_no_existe(self):
        """Sólo los nombres de §9: cualquier otro es AttributeError (también los de los módulos)."""
        for nombre in ("ajustes_e4", "e3p_anual", "a3", "no_existe"):
            with self.subTest(nombre=nombre), self.assertRaises(AttributeError):
                getattr(reloj_dmc, nombre)
        with self.assertRaises(KeyError):
            reloj_dmc.modulo_de("no_existe")

    def test_fachada_es_perezosa(self):
        """Importar la fachada no carga otros módulos del paquete (ni numpy, pandas ni zoneinfo) ni escribe .pyc;
        se comprueba en un intérprete aparte, que termina antes de seguir."""
        codigo = ("import sys; sys.dont_write_bytecode = True; sys.path.insert(0, sys.argv[1]); "
                  "from reloj_dmc import reloj_dmc; "
                  "print(sorted(m for m in sys.modules if m == 'reloj_dmc' or m.startswith('reloj_dmc.')) "
                  "+ [m for m in ('numpy', 'pandas', 'zoneinfo') if m in sys.modules])")
        salida = subprocess.run([sys.executable, "-B", "-I", "-c", codigo, str(_RAIZ)], capture_output=True,
                                text=True, timeout=120, check=True)
        self.assertEqual(salida.stdout.strip(), str(["reloj_dmc", "reloj_dmc.reloj_dmc"]))


class PruebasIndice8(unittest.TestCase):
    def test_indice_de_8_cada_punto_tiene_prueba(self):
        """Cada punto 1 a 28 de §8 (grupos A a C, numerados en el texto) tiene al menos una prueba «pNN» en
        tests/, y no hay pruebas de puntos que el texto no tiene."""
        puntos = _puntos_de_8(_texto_c0())
        self.assertEqual(puntos, list(range(1, len(puntos) + 1)))     # 1 … 28, en orden y sin huecos
        self.assertEqual(len(puntos), 28)
        indice = _pruebas_por_punto()
        self.assertEqual(sorted(set(puntos) - set(indice)), [], "puntos de §8 sin ninguna prueba «pNN»")
        self.assertEqual(sorted(set(indice) - set(puntos)), [], "pruebas «pNN» de puntos que §8 no tiene")
        for punto in puntos:
            with self.subTest(punto=punto):
                nombres = [n for _, n, _ in indice[punto]]
                self.assertEqual(len(nombres), len(set(nombres)), nombres)

    def test_indice_de_8_sin_pruebas_por_implementar(self):
        """Ningún punto de §8 depende sólo de pruebas del esqueleto (unittest.skip(POR_IMPLEMENTAR)). Los que
        sólo las tienen en un archivo de EN_CURSO se informan y la prueba se omite; en otro, falla."""
        indice = _pruebas_por_punto()
        solo_pendientes = {p: lista for p, lista in sorted(indice.items()) if all(pend for _, _, pend in lista)}
        ajenos = {p: [f"{a}::{n}" for a, n, _ in lista] for p, lista in solo_pendientes.items()
                  if any(a not in EN_CURSO for a, _, _ in lista)}
        self.assertEqual(ajenos, {}, "puntos de §8 con sólo pruebas por implementar fuera de los archivos en curso")
        if solo_pendientes:
            detalle = "; ".join(f"p{p:02d}: " + ", ".join(sorted({EN_CURSO[a] for a, _, _ in lista}))
                                for p, lista in solo_pendientes.items())
            self.skipTest(f"pendientes de la ola 4b en curso, que deben implementarse antes de cerrar C1: {detalle}")


class PruebasCierreDeC1(unittest.TestCase):
    """Pendientes de implementación que C1 cierra (lecturas_c1.md, §6, decisión del autor del 2026-10-25)."""

    def test_en_curso_vacia_al_cerrar_c1(self):
        """PEN-3: al cerrar C1 ya no hay archivos de pruebas en curso; el índice de §8 no omite ningún punto."""
        self.assertEqual(EN_CURSO, {})
        for archivo in ("test_verificar_reloj_dmc.py", "test_bateria.py"):
            self.assertTrue((_PRUEBAS / archivo).is_file(), archivo)

    def test_encabezados_sin_enmiendas_adoptadas_como_pendientes(self):
        """PEN-5: ningún módulo del paquete (ni el docstring de una prueba) llama «borrador» o «sin adoptar» a la
        Enmienda 1, que está adoptada y anclada. Se lee el código por AST y texto, sin importar nada."""
        paquete = _PRUEBAS.parent
        hallados = []
        for ruta in sorted(paquete.glob("*.py")):
            fuente = " ".join(ruta.read_text(encoding="utf-8").split())
            hallados += [f"{ruta.name}: {m.group(0)}" for m in _ENMIENDA_COMO_PENDIENTE.finditer(fuente)]
        for ruta in sorted(_PRUEBAS.glob("test_*.py")):
            for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
                if isinstance(nodo, (ast.Module, ast.ClassDef, ast.FunctionDef)):
                    doc = " ".join((ast.get_docstring(nodo) or "").split())
                    hallados += [f"{ruta.name}: {m.group(0)}" for m in _ENMIENDA_COMO_PENDIENTE.finditer(doc)]
        self.assertEqual(hallados, [])
        self.assertIsNotNone(_ENMIENDA_COMO_PENDIENTE.search("Dependen del borrador de la Enmienda 1, aún sin adoptar"))
        self.assertIsNotNone(_ENMIENDA_COMO_PENDIENTE.search("E1-4 (borrador, sin adoptar): se aplican"))


if __name__ == "__main__":
    unittest.main()
