"""Pruebas de fijados.py (código fijado, AST y Anexo C).

Esqueleto de C1: cada prueba nombra lo que debe comprobar.
Las que llevan «pNN» son el punto NN de §8 (grupos A, B y C). Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s reloj_dmc/tests -t .
Leen sólo código ya citado (adaptador, v3, guarda, _comun_modelo, verificar_reloj_sinca y las copias del
descargador del Anexo C en LOCAL, APH y AP/logs/), el protocolo anclado y su tabla de anclaje. Ningún dato
DMC y nada bajo /Volumes. Si falta un archivo, la prueba se omite con el motivo y no se da por aprobada.
"""
import sys

sys.dont_write_bytecode = True

import ast  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import tempfile  # noqa: E402
import traceback  # noqa: E402
import unittest  # noqa: E402
from datetime import date, datetime, timedelta, timezone  # noqa: E402
from pathlib import Path  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from reloj_dmc import entorno, fijados  # noqa: E402,F401

_RUTAS = entorno.rutas_reales()
AP, APH = _RUTAS.ap, _RUTAS.aph
_AUDITORIA_C0 = APH / "auditoria/20261023/reloj_dmc"
PROTOCOLO = _AUDITORIA_C0 / "PROTOCOLO_RELOJ_DMC_v1_propuesta.md"
TABLA_ANCLAJE = _AUDITORIA_C0 / "c0/tabla_anclaje_c0.json"
_DESCARGADOR = "descargar_meteo_chile_horaria.py"

# Ubicaciones del Anexo C (las seis admitidas) y del inventario de C0 (tabla_anclaje_c0.json,
# «encontradas_por_el_inventario»).
FUENTES_ANEXO_C = {
    "06e46f839f0c70ec98ffc5ea8fee8f519b6cea532fe64ba2ad6e175d6fe3bfe6":
        Path.home() / "Asesorias_Data_local/_respaldos/dmc_antes_correccion_20261012" / (_DESCARGADOR + ".06e46f83"),
    "38a50d54a4ac30fb800201468d98ae78f6c7d45d899384ad56ddc7097b717918":
        APH / "auditoria/20261014/dmc_prioridad_preparacion/original/scripts_pipeline" / _DESCARGADOR,
    "bb5f3e9a31769e55344cbda30cf6941e3a3b7bf805a03851340bfaedd5ff1685":
        APH / "auditoria/20261014/dmc_prioridad_preparacion/candidato/scripts_pipeline" / _DESCARGADOR,
    "ca49c75e388d51cd5384b33f952ca8897ec14a26768f81e8a4963bc66ecf899b":
        AP / "logs/_control_meteo/source_before_HUMAN20261019_METEO_DMC_PARALLEL_16" / _DESCARGADOR,
    "c41831d2e6806d029200d2b9f747e1741011e5f1da7c02f8f5d38b7ead9de0dc":
        AP / "logs/_control_meteo/source_before_HUMAN20261021_METEO_DMC_FAST_20" / _DESCARGADOR,
    "578fa26eea5b4ac4733c56aaf08e9b7b8904595fb8447dd54feb838642612120":
        AP / "scripts_pipeline" / _DESCARGADOR,
}
FUENTES_INVENTARIO = {
    "fc1f1bb6c8d1adce4aeab1494595007776bf16a3e4f88faf4ebbdc63eebe3496":
        APH / "tmp/dmc_final_checks_candidate/scripts_pipeline" / _DESCARGADOR,
    "975d9bf0b7b5045b575b922d8c32d7a23e4c319e608f96cd3ec7bc7a4a59b2b7":
        APH / "tmp/dmc_final_checks_candidate/rollback_41543/scripts_pipeline" / _DESCARGADOR,
}
VIGENTE = "578fa26eea5b4ac4733c56aaf08e9b7b8904595fb8447dd54feb838642612120"


def _sha(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _registrar(texto: str) -> None:
    """Línea para la salida guardada de las pruebas (pruebas_c1.txt), que va al addendum de C1."""
    sys.stderr.write(f"\n[C1 Anexo C] {texto}\n")


class _ConLimpieza(unittest.TestCase):
    """Retira de sys.modules y de la caché de fijados los módulos de prueba que se carguen."""
    def setUp(self):
        self._nombres: list[str] = []

    def tearDown(self):
        for nombre in self._nombres:
            sys.modules.pop(nombre, None)
            fijados._CARGADOS.pop(nombre, None)
        for nombre in fijados.MODULOS_PROHIBIDOS:
            if isinstance(sys.modules.get(nombre), type(sys)) and getattr(sys.modules[nombre], "_de_prueba", False):
                sys.modules.pop(nombre)

    def exigir(self, *rutas: Path) -> None:
        faltan = [_nombre(r) for r in rutas if not r.is_file()]
        if faltan:
            self.skipTest(f"falta el archivo fijado: {', '.join(faltan)}")


def _nombre(ruta: Path) -> str:
    """Alias para los motivos de omisión; sólo el nombre si la ruta no cae bajo un alias."""
    try:
        return entorno.alias(ruta, _RUTAS)
    except ValueError:
        return ruta.name


class PruebasFijados(_ConLimpieza):
    def test_adaptador_se_carga_por_ruta_y_huella(self):
        """f61559ea…; una huella distinta lanza error."""
        ruta = AP / fijados.RUTA_ADAPTADOR
        self.exigir(ruta)
        self.assertEqual(_sha(ruta), fijados.SHA_ADAPTADOR)
        adaptador = fijados.cargar_adaptador(AP)
        for nombre in ("leer_artefacto", "normalizar", "_utc", "_confirmado"):
            self.assertTrue(callable(getattr(adaptador, nombre)))
        self.assertEqual(Path(adaptador.__file__).resolve(), ruta.resolve())
        self.assertIs(sys.modules[fijados.MODULO_ADAPTADOR], adaptador)
        self.assertIs(fijados.cargar_adaptador(AP), adaptador)
        for mala in ("0" * 64, fijados.SHA_ADAPTADOR.upper(), fijados.SHA_ADAPTADOR[:8], None):
            with self.subTest(huella=str(mala)[:8]), self.assertRaises(ValueError):
                fijados.cargar_adaptador(AP, mala)  # type: ignore[arg-type]
        for nombre in fijados.MODULOS_PROHIBIDOS:
            self.assertNotIn(nombre, sys.modules)

    def test_carga_por_ruta_verifica_antes_y_despues_y_retira_rutas(self):
        """Huella antes y después, sin enlaces, rutas de importación retiradas y sin _common."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp).resolve()
            (tmp / "_reloj_dmc_prueba_auxiliar.py").write_text("X = 1\n", encoding="utf-8")
            principal = tmp / "principal.py"
            principal.write_text("import _reloj_dmc_prueba_auxiliar as aux\nY = aux.X + 1\n", encoding="utf-8")
            self._nombres += ["_reloj_dmc_prueba_principal", "_reloj_dmc_prueba_auxiliar",
                              "_reloj_dmc_prueba_cambia", "_reloj_dmc_prueba_prohibido", "_reloj_dmc_prueba_otro"]
            m = fijados.cargar_por_ruta(principal, _sha(principal), "_reloj_dmc_prueba_principal",
                                        rutas_import=(tmp,))
            self.assertEqual(m.Y, 2)
            self.assertNotIn(str(tmp), sys.path)
            self.assertFalse((tmp / "__pycache__").exists())
            self.assertIs(fijados.cargar_por_ruta(principal, _sha(principal), "_reloj_dmc_prueba_principal"), m)
            # Mismo nombre con otro archivo: error.
            otro = tmp / "otro.py"
            otro.write_text("Z = 0\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                fijados.cargar_por_ruta(otro, _sha(otro), "_reloj_dmc_prueba_principal")
            # Huella distinta, ruta relativa y enlace simbólico: error antes de ejecutar nada.
            with self.assertRaises(ValueError):
                fijados.cargar_por_ruta(otro, "1" * 64, "_reloj_dmc_prueba_otro")
            with self.assertRaises(ValueError):
                fijados.cargar_por_ruta(Path("otro.py"), _sha(otro), "_reloj_dmc_prueba_otro")
            enlace = tmp / "enlace.py"
            enlace.symlink_to(otro)
            with self.assertRaises(ValueError):
                fijados.cargar_por_ruta(enlace, _sha(otro), "_reloj_dmc_prueba_otro")
            self.assertNotIn("_reloj_dmc_prueba_otro", sys.modules)
            # Un archivo que cambia mientras se carga: error y no queda en sys.modules.
            cambia = tmp / "cambia.py"
            cambia.write_text("from pathlib import Path\n"
                              "Path(__file__).write_text(Path(__file__).read_text() + '# cambiado\\n')\n",
                              encoding="utf-8")
            with self.assertRaises(ValueError):
                fijados.cargar_por_ruta(cambia, _sha(cambia), "_reloj_dmc_prueba_cambia")
            self.assertNotIn("_reloj_dmc_prueba_cambia", sys.modules)
            # Un módulo que trae _common: error.
            prohibido = tmp / "prohibido.py"
            prohibido.write_text("import sys, types\nm = types.ModuleType('_common')\nm._de_prueba = True\n"
                                 "sys.modules['_common'] = m\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                fijados.cargar_por_ruta(prohibido, _sha(prohibido), "_reloj_dmc_prueba_prohibido")
            self.assertNotIn("_reloj_dmc_prueba_prohibido", sys.modules)
            with self.assertRaises(RuntimeError):  # mientras _common siga cargado, nada se carga
                fijados.cargar_por_ruta(otro, _sha(otro), "_reloj_dmc_prueba_otro")
            sys.modules.pop("_common")
            self.assertEqual(fijados.cargar_por_ruta(otro, _sha(otro), "_reloj_dmc_prueba_otro").Z, 0)

    def test_preflight_y_dmc_features_sin_comun_modelo(self):
        """Tras cargarlos, ni _comun_modelo ni _common en sys.modules."""
        v3 = AP / "scripts_modelo_1km/v3"
        self.exigir(AP / fijados.RUTA_PREFLIGHT_V3, AP / fijados.RUTA_DMC_FEATURES, AP / fijados.RUTA_ADAPTADOR)
        self.assertEqual(_sha(AP / fijados.RUTA_DMC_FEATURES), fijados.SHA_DMC_FEATURES)
        self.assertEqual(_sha(AP / fijados.RUTA_PREFLIGHT_V3), fijados.SHA_PREFLIGHT_V3)
        hilos = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
                 "NUMEXPR_NUM_THREADS")
        entorno_antes = {v: os.environ.get(v) for v in hilos}
        try:
            import pyarrow as pa
            cpu_antes, io_antes = pa.cpu_count(), pa.io_thread_count()
        except ImportError:  # pragma: no cover
            pa = None
        try:
            preflight = fijados.cargar_preflight(AP)
            dmc = sys.modules[fijados.MODULO_DMC_FEATURES]
            self.assertIs(dmc, fijados.cargar_dmc_features(AP))
            self.assertIs(fijados.cargar_preflight(AP), preflight)
            self.assertTrue(callable(preflight.policy_check))
            self.assertTrue(callable(dmc.cargar_dmc))
            self.assertEqual(Path(preflight.__file__).resolve(), (AP / fijados.RUTA_PREFLIGHT_V3).resolve())
            self.assertEqual(Path(dmc.__file__).resolve(), (AP / fijados.RUTA_DMC_FEATURES).resolve())
            for nombre in fijados.MODULOS_PROHIBIDOS:
                self.assertNotIn(nombre, sys.modules)
            self.assertNotIn(str(v3.resolve()), sys.path)
            with self.assertRaises(ValueError):
                fijados.cargar_preflight(AP, "2" * 64)
        finally:
            for v, valor in entorno_antes.items():
                if valor is None:
                    os.environ.pop(v, None)
                else:
                    os.environ[v] = valor
            if pa is not None:
                pa.set_cpu_count(cpu_antes)
                pa.set_io_thread_count(io_antes)

    def test_descargador_vigente_se_carga_por_huella(self):
        """El descargador vigente (578fa26e…) para el modo sintético; otra huella lanza error."""
        ruta = AP / fijados.RUTA_DESCARGADOR
        self.exigir(ruta)
        if _sha(ruta) != VIGENTE:
            self.skipTest("el descargador en AP ya no es la versión vigente 578fa26e…")
        modulo = fijados.cargar_descargador(AP, VIGENTE)
        self.assertTrue(callable(modulo.run_download) and callable(modulo.parse_report))
        self.assertEqual(modulo.TIMEZONE, "unconfirmed")
        with self.assertRaises(ValueError):
            fijados.cargar_descargador(AP, fijados.VERSIONES_ADMITIDAS_C0[0])
        self.assertFalse(any(m in sys.modules for m in fijados.MODULOS_PROHIBIDOS))

    def test_extraer_por_ast_aislado_y_estricto(self):
        """Sólo los nodos pedidos, en espacio aislado, con __future__ y líneas reales; nombres únicos."""
        fuente = ("from __future__ import annotations\n"
                  "import os\n"
                  "os.environ['_RELOJ_DMC_EFECTO_AST'] = 'ejecutado'\n"
                  "\n\n"
                  "def suma(x: NoDefinido) -> int:\n"
                  "    return x + K\n"
                  "\n\n"
                  "K = 2\n"
                  "DOBLE = 1\n"
                  "DOBLE = 3\n"
                  "\n\n"
                  "@decorador\n"
                  "def decorada():\n"
                  "    return 1\n"
                  "\n\n"
                  "def falla():\n"
                  "    raise RuntimeError('línea conocida')\n")
        linea_raise = fuente.splitlines().index("    raise RuntimeError('línea conocida')") + 1
        os.environ.pop("_RELOJ_DMC_EFECTO_AST", None)
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "modulo_ajeno.py"
            ruta.write_text(fuente, encoding="utf-8")
            sha = _sha(ruta)
            r = fijados.extraer_por_ast(ruta, sha, ("suma", "K"), {})
            self.assertEqual(r["suma"](1), 3)
            self.assertNotIn("_RELOJ_DMC_EFECTO_AST", os.environ)
            self.assertNotIn("os", r["suma"].__globals__)
            falla = fijados.extraer_por_ast(ruta, None, ("falla",), {})["falla"]
            try:  # assertRaises borra el traceback; hace falta para ver la línea
                falla()
            except RuntimeError as exc:
                ultimo = traceback.extract_tb(exc.__traceback__)[-1]
            else:
                self.fail("falla() no lanzó RuntimeError")
            self.assertEqual((Path(ultimo.filename).name, ultimo.lineno), (ruta.name, linea_raise))
            for nombres, espacio in ((("DOBLE",), {}), (("decorada",), {}), (("no_existe",), {}),
                                     (("K",), {"K": 1}), ((), {})):
                with self.subTest(nombres=nombres), self.assertRaises(ValueError):
                    fijados.extraer_por_ast(ruta, None, nombres, espacio)
            with self.assertRaises(ValueError):
                fijados.extraer_por_ast(ruta, "3" * 64, ("K",), {})

    def test_macrozona_region_por_ast_sin_importar(self):
        """Copia MACROZONA_REGION leyendo la fuente (a83c0384…)."""
        ruta = AP / fijados.RUTA_COMUN_MODELO
        self.exigir(ruta)
        self.assertEqual(_sha(ruta), fijados.SHA_COMUN_MODELO)
        tabla = fijados.macrozona_region(AP)
        # Camino independiente: literal_eval del valor del nodo.
        fuente = ruta.read_text(encoding="utf-8")
        nodo = next(n for n in ast.parse(fuente).body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "MACROZONA_REGION" for t in n.targets))
        self.assertEqual(tabla, ast.literal_eval(nodo.value))
        self.assertEqual((tabla[13], tabla[11], tabla[12], tabla[0]), ("centro", "austral", "austral", "sin_region"))
        for nombre in ("_comun_modelo", "_common"):
            self.assertNotIn(nombre, sys.modules)
        # Una copia alterada no pasa la huella.
        with tempfile.TemporaryDirectory() as tmp:
            copia = Path(tmp) / "_comun_modelo.py"
            copia.write_text(fuente.replace('13: "centro"', '13: "sur"'), encoding="utf-8")
            with self.assertRaises(ValueError):
                fijados.extraer_por_ast(copia, fijados.SHA_COMUN_MODELO, ("MACROZONA_REGION",), {})

    def test_transiciones_sinca_por_ast_sin_importar(self):
        """verificar_reloj_sinca.transiciones sin ejecutar el módulo."""
        ruta = AP / fijados.RUTA_RELOJ_SINCA
        self.exigir(ruta)
        nodo = fijados.nodos_superiores(ruta.read_text(encoding="utf-8"))["transiciones"]
        self.assertEqual([(n.lineno, n.end_lineno) for n in nodo], [(47, 73)], "§1.10 cita :47-73")
        transiciones = fijados.transiciones_sinca(AP)
        for nombre in ("verificar_reloj_sinca", "_comun_modelo", "_common"):
            self.assertNotIn(nombre, sys.modules)
        self.assertEqual(sorted(k for k in transiciones.__globals__ if not k.startswith("__")),
                         ["ZoneInfo", "date", "datetime", "timedelta", "transiciones"])
        # §1.10: el precedente ubica las horas especiales una hora tarde.
        self.assertEqual(transiciones("America/Santiago", 2019),
                         [(date(2019, 4, 7), "ambigua", 0), (date(2019, 9, 8), "inexistente", 1)])
        # Las verdaderas, por un camino propio: 2019-04-06 23:00 repetida y 2019-09-08 00:00 inexistente.
        z = ZoneInfo("America/Santiago")
        repetida = datetime(2019, 4, 6, 23)
        self.assertNotEqual(repetida.replace(tzinfo=z, fold=0).utcoffset(),
                            repetida.replace(tzinfo=z, fold=1).utcoffset())
        inexistente = datetime(2019, 9, 8, 0)
        ida = inexistente.replace(tzinfo=z).astimezone(timezone.utc).astimezone(z).replace(tzinfo=None)
        self.assertNotEqual(ida, inexistente)
        self.assertEqual(ida - timedelta(hours=1), inexistente)

    def test_c1_huella_ruta_etiqueta_seis_admitidas(self):
        """Las seis versiones recuperadas dan af1b0e1b… (addendum de C1)."""
        self.assertEqual(set(FUENTES_ANEXO_C), set(fijados.VERSIONES_ADMITIDAS_C0))
        presentes = {v: r for v, r in FUENTES_ANEXO_C.items() if r.is_file()}
        resultado = fijados.versiones_admitidas(presentes)
        for version, fila in resultado.items():
            with self.subTest(version=version[:8]):
                self.assertEqual(fila["sha256_archivo"], version)
                self.assertEqual(fila["huella"], fijados.HUELLA_RUTA_ETIQUETA_ADMITIDA)
                self.assertTrue(fila["admitida"])
                self.assertIsNone(fila["motivo"])
                self.assertTrue(fila["en_anexo_c"])
        _registrar("admitidas del Anexo C: " + ", ".join(
            f"{v[:8]}… huella={f['huella'][:8]}…" for v, f in resultado.items()))
        faltan = sorted(set(FUENTES_ANEXO_C) - set(presentes))
        if faltan:
            self.skipTest("falta la copia de " + ", ".join(v[:8] for v in faltan) + "; no se da por aprobada")

    def test_c1_versiones_halladas_por_el_inventario(self):
        """fc1f1bb6 y 975d9bf0 (APH/tmp/…): comprobación mecánica, se registra."""
        self.assertTrue(set(FUENTES_INVENTARIO) <= set(fijados.VERSIONES_SIN_CODIGO_C0))
        if TABLA_ANCLAJE.is_file():
            halladas = json.loads(TABLA_ANCLAJE.read_text(encoding="utf-8"))[
                "versiones_del_descargador"]["encontradas_por_el_inventario"]
            self.assertEqual({k: v.rstrip("/") for k, v in halladas.items()},
                             {v[:8]: entorno.alias(r.parent.parent, _RUTAS) for v, r in FUENTES_INVENTARIO.items()})
        resultado = fijados.versiones_admitidas(FUENTES_INVENTARIO)
        no_recuperadas = []
        for version, fila in resultado.items():
            if fila["motivo"] in ("sin_codigo", "sha256_distinto"):
                no_recuperadas.append(f"{version[:8]} ({fila['motivo']})")
                continue
            with self.subTest(version=version[:8]):
                self.assertEqual(fila["sha256_archivo"], version)
                self.assertIsNotNone(fila["huella"])
                self.assertEqual(fila["admitida"], fila["huella"] == fijados.HUELLA_RUTA_ETIQUETA_ADMITIDA)
            _registrar(f"{version[:8]}… (inventario de C0): huella={fila['huella'][:8]}… "
                       f"admitida={fila['admitida']}")
        if no_recuperadas:
            self.skipTest("sin código recuperado: " + ", ".join(no_recuperadas))

    def test_version_con_otra_huella_no_se_admite(self):
        """Un descargador con la ruta de etiqueta cambiada no entra."""
        vigente = AP / fijados.RUTA_DESCARGADOR
        self.exigir(vigente)
        fuente = vigente.read_text(encoding="utf-8")
        linea = 'TIMEZONE = "unconfirmed"'
        self.assertEqual(fuente.count(linea), 1)
        variantes = {
            "ruta_cambiada": fuente.replace(linea, 'TIMEZONE = "America/Santiago"'),
            "comentario_fuera_de_la_ruta": fuente + "\n# comentario agregado\n",
            "nombre_ligado_dos_veces": fuente + "\n" + linea + "\n",
            "sintaxis_rota": fuente + "\ndef (\n",
        }
        with tempfile.TemporaryDirectory() as tmp:
            fuentes = {}
            for nombre, texto in variantes.items():
                ruta = Path(tmp) / f"{nombre}.py"
                ruta.write_text(texto, encoding="utf-8")
                fuentes[_sha(ruta)] = ruta
            por_nombre = {r.stem: v for v, r in fuentes.items()}
            fuentes["4" * 64] = Path(tmp) / "comentario_fuera_de_la_ruta.py"  # el archivo no tiene esa sha
            fuentes["5" * 64] = Path(tmp) / "no_existe.py"
            resultado = fijados.versiones_admitidas(fuentes)
        esperado = {"ruta_cambiada": (False, "huella_distinta"), "comentario_fuera_de_la_ruta": (True, None),
                    "nombre_ligado_dos_veces": (False, "huella_no_calculable"),
                    "sintaxis_rota": (False, "huella_no_calculable")}
        for nombre, (admitida, motivo) in esperado.items():
            fila = resultado[por_nombre[nombre]]
            with self.subTest(variante=nombre):
                self.assertEqual((fila["admitida"], fila["motivo"]), (admitida, motivo))
                self.assertFalse(fila["en_anexo_c"])
        self.assertEqual(resultado[por_nombre["comentario_fuera_de_la_ruta"]]["huella"],
                         fijados.HUELLA_RUTA_ETIQUETA_ADMITIDA)
        self.assertEqual((resultado["4" * 64]["admitida"], resultado["4" * 64]["motivo"]), (False, "sha256_distinto"))
        self.assertEqual((resultado["5" * 64]["admitida"], resultado["5" * 64]["motivo"]), (False, "sin_codigo"))
        with self.assertRaises(ValueError):
            fijados.huella_ruta_etiqueta("TIMEZONE = 1\n")

    def test_constantes_calzan_con_el_protocolo_y_el_anclaje(self):
        """Huellas, nombres y versiones de fijados.py = protocolo anclado y tabla de anclaje de C0."""
        self.exigir(PROTOCOLO, TABLA_ANCLAJE)
        anclaje = json.loads(TABLA_ANCLAJE.read_text(encoding="utf-8"))
        self.assertEqual(_sha(PROTOCOLO), anclaje["protocolo"]["sha256"])
        texto = PROTOCOLO.read_text(encoding="utf-8")
        codigo = anclaje["codigo_y_catalogo"]
        fijadas = {"AP/" + fijados.RUTA_ADAPTADOR: fijados.SHA_ADAPTADOR,
                   "AP/" + fijados.RUTA_DMC_FEATURES: fijados.SHA_DMC_FEATURES,
                   "AP/" + fijados.RUTA_PREFLIGHT_V3: fijados.SHA_PREFLIGHT_V3,
                   "AP/scripts_pipeline/_meteo_guard.py": fijados.SHA_METEO_GUARD,
                   "AP/" + fijados.RUTA_COMUN_MODELO: fijados.SHA_COMUN_MODELO,
                   "ERA5L/catalogo_pixeles.parquet": fijados.SHA_CATALOGO_PIXELES}
        for alias_, sha in fijadas.items():
            with self.subTest(archivo=alias_):
                self.assertEqual(codigo[alias_]["sha256"], sha)
                self.assertIn(f"`{sha[:8]}…`", texto)
                if alias_.startswith("AP/"):  # el catálogo está bajo /Volumes: no se abre aquí
                    self.assertEqual(_sha(AP / alias_[3:]), sha)
        anexo = texto.split("## Anexo C.")[1].split("## Registro de revisión")[0]
        hex64 = re.compile(r"\b[0-9a-f]{64}\b")
        admitidas = hex64.findall(anexo.split("**Admitidas.**")[1].split("**Sin código recuperado:**")[0])
        sin_codigo = hex64.findall(anexo.split("**Sin código recuperado:**")[1].split("**Copias.**")[0])
        self.assertEqual(tuple(admitidas), fijados.VERSIONES_ADMITIDAS_C0)
        self.assertEqual(tuple(sin_codigo), fijados.VERSIONES_SIN_CODIGO_C0)
        self.assertEqual(re.search(r"Valor admitido: `([0-9a-f]{64})`", anexo).group(1),
                         fijados.HUELLA_RUTA_ETIQUETA_ADMITIDA)
        nombres = re.findall(r"`([^`]+)`", re.search(r"NOMBRES = \((.*?)\)\.", anexo).group(1))
        self.assertEqual(tuple(nombres), fijados.NOMBRES_RUTA_ETIQUETA)
        self.assertEqual([v[:8] for v in fijados.VERSIONES_ADMITIDAS_C0],
                         anclaje["versiones_del_descargador"]["admitidas_anexo_c"])
        self.assertEqual([v[:8] for v in fijados.VERSIONES_SIN_CODIGO_C0],
                         anclaje["versiones_del_descargador"]["sin_codigo_en_el_texto"])


if __name__ == "__main__":
    unittest.main()
