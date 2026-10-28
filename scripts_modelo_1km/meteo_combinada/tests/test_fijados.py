"""Pruebas de fijados.py (código fijado por ruta y huella, clausura del reloj y extracciones por AST; §2.1, §7.1, §9).

Dueño: I1 (ola 1; el píxel del reloj, FIJ-11, en la ola 5). Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s meteo_combinada/tests -t .
Leen sólo código, textos y configuración ya citados (el adaptador, v3, el descargador, _comun_modelo y _features.py
por AST, el reloj, meteo_civil_v3 por AST, preparar_m0 por AST, m0/huellas_m0.json y el JSON de umbrales) y, con
``git cat-file``, tres archivos de v2 en los commits c7c47e8, 889b972 y 6c15981 de AP (FIJ-10). Para el píxel del
reloj (FIJ-11): la clausura ampliada (``extraccion``, ``numerico`` y ``umbrales`` del reloj, también con ``git
cat-file`` en AP 1da0236 y 4b50b0d), el texto y el JSON de umbrales del reloj en C0 (APH d02f918) y, sólo para la línea
«Píxel» de su Anexo B, los textos del reloj del v1 al v1.0.5; por AST y sin correrlo, el generador del v1.2
(``enmienda5/generar_v1_2.py``, APH 07881ed); del v1.2, de su JSON y del addendum de C1, sólo la huella. Ningún dato
DMC, ninguna salida del reloj, ningún dato real y nada bajo /Volumes: las huellas de datos de §9.3 se comprueban en M2a
(prueba omitida con su motivo); el catálogo de píxeles de las pruebas del píxel es sintético. Si falta un archivo, la
prueba se omite con el motivo y no se da por aprobada.
"""
import sys

sys.dont_write_bytecode = True

import ast  # noqa: E402
import hashlib  # noqa: E402
import inspect  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402
from types import ModuleType, SimpleNamespace  # noqa: E402
from unittest import mock  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from meteo_combinada import entorno, fijados, tipos  # noqa: E402
from reloj_dmc import fijados as fijados_reloj  # noqa: E402

_RUTAS = entorno.rutas_reales()
AP, APH = _RUTAS.ap, _RUTAS.aph
_HUELLAS_M0 = APH / "auditoria/20261023/meteo_combinada/m0/huellas_m0.json"
_JSON_M0 = APH / "auditoria/20261023/meteo_combinada/m0/meteo_combinada_v1.json"
_MICROMAMBA = Path.home() / ".local/bin/micromamba"


def _sha(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _subproceso(codigo: str) -> str:
    """Corre ``codigo`` en un intérprete nuevo (-B -I), con la raíz del paquete como argv[1]; la última línea."""
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run([sys.executable, "-B", "-I", "-c", codigo, str(_RAIZ)], cwd=tmp, capture_output=True,
                           text=True, timeout=180, check=False)
    if r.returncode != 0:
        raise AssertionError(f"El subproceso falló:\n{r.stderr}")
    return r.stdout.strip().splitlines()[-1]


def _huella_en_git(caso: unittest.TestCase, repo: Path, commit: str, ruta: str) -> str:
    """sha256 del archivo en ese commit (``git cat-file blob``, sin filtros); sin git, sin el repositorio o sin el
    archivo en el commit, la prueba se omite y no se da por aprobada."""
    git = shutil.which("git")
    if git is None or not (repo / ".git").exists():
        caso.skipTest("sin git o sin el repositorio: no se da por aprobada")
    r = subprocess.run([git, "-C", str(repo), "cat-file", "blob", f"{commit}:{ruta}"], capture_output=True, timeout=60,
                       check=False)
    if r.returncode != 0:
        caso.skipTest(f"{commit[:7]} no trae {ruta}: no se da por aprobada")
    return hashlib.sha256(r.stdout).hexdigest()


# El píxel del reloj (FIJ-11): radio medio de la Tierra de numerico del reloj (R-21 del reloj, el de dmc_features), para
# calcular aparte la distancia esperada.
_R_KM = 6371.0088
_KM_POR_GRADO = _R_KM * math.pi / 180
_MEDIA_CELDA = 0.05          # celdas de 0,1° como las de ERA5-Land


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine, escrita aparte de la del reloj."""
    f1, f2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((f2 - f1) / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * _R_KM * math.asin(math.sqrt(a))


def _catalogo(centros):
    """Catálogo sintético de píxeles: [(pixel_id, lat, lon)] → las columnas que lee reloj_dmc.extraccion.elegir_pixel."""
    import numpy as np
    import pandas as pd
    ids, lat, lon = (np.array(c) for c in zip(*centros))
    return pd.DataFrame({"pixel_id": ids.astype(np.int64), "latitude": lat.astype(np.float64),
                         "longitude": lon.astype(np.float64), "cell_west": lon - _MEDIA_CELDA,
                         "cell_east": lon + _MEDIA_CELDA, "cell_south": lat - _MEDIA_CELDA,
                         "cell_north": lat + _MEDIA_CELDA, "cod_comuna": np.full(len(ids), 7101, dtype=np.int64)})


def _importados_del_reloj(ruta: Path) -> set[str]:
    """Módulos de reloj_dmc que importa un archivo del reloj, por AST (también dentro de funciones)."""
    carpeta = ruta.parent
    nombres: set[str] = set()
    for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
        if isinstance(nodo, ast.Import):
            nombres |= {a.name.split(".")[1] for a in nodo.names if a.name.startswith("reloj_dmc.")}
        elif isinstance(nodo, ast.ImportFrom):
            base = nodo.module or ""
            if nodo.level == 0 and base == "reloj_dmc" or nodo.level > 0 and not base:
                nombres |= {a.name for a in nodo.names if (carpeta / f"{a.name}.py").is_file()}
            elif nodo.level == 0 and base.startswith("reloj_dmc."):
                nombres.add(base.split(".")[1])
            elif nodo.level > 0:
                nombres.add(base.split(".")[0])
        elif (isinstance(nodo, ast.Call) and nodo.args and isinstance(nodo.args[0], ast.Constant)
              and isinstance(nodo.args[0].value, str) and nodo.args[0].value.startswith("reloj_dmc.")
              and (getattr(nodo.func, "attr", None) or getattr(nodo.func, "id", None)) in ("import_module",
                                                                                         "__import__")):
            nombres.add(nodo.args[0].value.split(".")[1])
    return nombres


class _ConLimpieza(unittest.TestCase):
    """Retira de sys.modules y de la caché del reloj los módulos de prueba que se carguen."""

    def setUp(self):
        self._nombres: list[str] = []

    def tearDown(self):
        for nombre in self._nombres:
            sys.modules.pop(nombre, None)
            fijados_reloj._CARGADOS.pop(nombre, None)

    def exigir(self, *rutas: Path) -> None:
        faltan = [r.name for r in rutas if not r.is_file()]
        if faltan:
            self.skipTest(f"falta el archivo fijado: {', '.join(faltan)}")


class PruebasHuellas(_ConLimpieza):
    def test_huellas_9_3_del_codigo(self):
        """El código, los textos y la configuración de §9.3 y §9.4 tienen las huellas fijadas (FIJ-4)."""
        faltan = [f"{r}/{p}" for r, p, _, _ in fijados.HUELLAS_CODIGO if not ({"AP": AP, "APH": APH}[r] / p).is_file()]
        if faltan:
            self.skipTest(f"faltan archivos fijados: {faltan}")
        self.assertEqual(fijados.comprobar_codigo_fijado(AP, APH), [])
        rutas = [(r, p) for r, p, _, _ in fijados.HUELLAS_CODIGO]
        self.assertEqual(len(rutas), len(set(rutas)))

    def test_huellas_coinciden_con_m0_y_con_el_reloj(self):
        """Las constantes copian m0/huellas_m0.json (código y datos, sin abrir los datos) y las del reloj. Las dos de v2
        que D51 vuelve a fijar (FIJ-10) copian el estado de M0 en ``SHA_CORRER_V2_M0`` y ``SHA_CONFIG_V2_M0``, y la
        vigente ya no es la de M0; ``reloj_sinca_v2.py`` (D54) no estaba en M0."""
        self.exigir(_HUELLAS_M0)
        m0 = json.loads(_HUELLAS_M0.read_text(encoding="utf-8"))
        registradas = {**{k: v["sha256"] for k, v in m0["codigo_fijado"].items()},
                       **{k: v["sha256"] for k, v in m0["codigo_citado"].items()},
                       **{k: v["sha256"] for k, v in m0["textos"].items()},
                       **{k: v["sha256"] for k, v in m0["reloj"].items()}}
        de_m0 = {f"AP/{ruta}": sha_m0 for ruta, sha_m0, _, _, _ in fijados.HUELLAS_D51}
        self.assertEqual(de_m0, {"AP/scripts_modelo_1km/v2/correr_v2.py": fijados.SHA_CORRER_V2_M0,
                                 "AP/scripts_modelo_1km/v2/config_v2.json": fijados.SHA_CONFIG_V2_M0,
                                 "AP/scripts_modelo_1km/v2/reloj_sinca_v2.py": None})
        vistas = 0
        for repo, ruta, sha, _ in fijados.HUELLAS_CODIGO:
            clave = f"{repo}/{ruta}"
            if clave in de_m0 and de_m0[clave] is None:
                self.assertNotIn(clave, registradas)
            elif clave in de_m0:
                vistas += 1
                self.assertEqual(de_m0[clave], registradas[clave], clave)
                self.assertNotEqual(sha, registradas[clave], clave)
            elif clave in registradas:
                vistas += 1
                self.assertEqual(sha, registradas[clave], clave)
        self.assertGreaterEqual(vistas, 18)
        fuentes = m0["fuentes"]
        datos_m0 = {"ERA5L/catalogo_pixeles.parquet": fuentes["era5land"]["archivos"]["ERA5L/catalogo_pixeles.parquet"]["sha256"]}
        for k, v in fuentes["geopotencial"].items():
            datos_m0[k.replace("DATOS/contaminantes/ERA5Land/invariantes/", "INVARIANTES/")] = v["sha256"]
        for k, v in fuentes["nasadem"]["manifiestos"].items():
            datos_m0[k] = v
        for k, v in fuentes["grilla_1km"].items():
            datos_m0[k.replace("LOCAL/modelado_1km/grilla_1km/", "GRILLA/")] = v["sha256"]
        for k, v in fuentes["ghs_pop_2020"].items():
            datos_m0[k.replace("DATOS/poblacion/ghs_pop_r2023a/", "GHS/")] = v["sha256"]
        for k, v in fuentes["sinca_meteorologia"].items():
            datos_m0[k.replace("DATOS/sinca_meteorologia/", "SINCA_MET/")] = v["sha256"]
        comunes = set(datos_m0) & set(fijados.HUELLAS_DATOS)
        self.assertGreaterEqual(len(comunes), 20)
        for clave in comunes:
            self.assertEqual(fijados.HUELLAS_DATOS[clave], datos_m0[clave], clave)
        for clave in ("huella_manifiestos", "huella_salidas_declaradas"):
            self.assertEqual(fijados.HUELLAS_ERA5L_AGREGADAS[clave], fuentes["era5land"][clave])
        self.assertEqual(fijados.SHA_MICROMAMBA_LIST, m0["interprete"]["micromamba_list_sha256"])
        for nombre in ("SHA_ADAPTADOR", "SHA_DMC_FEATURES", "SHA_PREFLIGHT_V3", "SHA_COMUN_MODELO"):
            self.assertEqual(getattr(fijados, nombre), getattr(fijados_reloj, nombre), nombre)
        self.assertIn(fijados.SHA_DESCARGADOR, fijados_reloj.VERSIONES_ADMITIDAS_C0)

    def test_huellas_d51_de_m0_y_vigentes_en_git(self):
        """FIJ-10 (D51, D54): la huella de M0 de ``correr_v2.py`` y ``config_v2.json`` es la del archivo en AP c7c47e8
        (``reloj_sinca_v2.py`` no estaba ahí), y la vigente, la del commit que la fijó (889b972 o 6c15981), las dos con
        ``git show <commit>:<ruta>``; la vigente es además la de ``HUELLAS_CODIGO`` y la de §9.3 de ``test_particiones``.
        Sin git o sin esos commits, se omite y no se da por aprobada."""
        git = shutil.which("git")
        if git is None or not (AP / ".git").exists():
            self.skipTest("sin git o sin el repositorio AP: no se da por aprobada")

        def git_ap(*args):
            return subprocess.run([git, "-C", str(AP), *args], capture_output=True, timeout=60, check=False)

        def en_git(commit, ruta):
            """sha256 del archivo en ese commit (``git cat-file blob``, sin filtros), o None si no estaba."""
            if git_ap("cat-file", "-e", f"{commit}^{{commit}}").returncode != 0:
                self.skipTest(f"AP no tiene el commit {commit[:7]}: no se da por aprobada")
            if git_ap("cat-file", "-e", f"{commit}:{ruta}").returncode != 0:
                return None
            r = git_ap("cat-file", "blob", f"{commit}:{ruta}")
            self.assertEqual(r.returncode, 0, r.stderr)
            return hashlib.sha256(r.stdout).hexdigest()
        self.assertEqual(len(fijados.HUELLAS_D51), 3)
        vigentes = {ruta: sha for _, ruta, sha, _ in fijados.HUELLAS_CODIGO}
        for ruta, sha_m0, commit_m0, sha, commit in fijados.HUELLAS_D51:
            with self.subTest(ruta=ruta):
                self.assertEqual(commit_m0, "c7c47e85d35889269ac30ae3582d96fbe697b6f8")
                self.assertEqual(en_git(commit_m0, ruta), sha_m0)
                self.assertEqual(en_git(commit, ruta), sha)
                self.assertEqual(vigentes[ruta], sha)
                self.assertNotEqual(sha, sha_m0)
        self.assertEqual(fijados.SHA_RELOJ_SINCA_V2[:8], "c1eb98c5")
        from meteo_combinada.tests import test_particiones
        self.assertEqual(test_particiones._SHA_CONFIG_V2, fijados.SHA_CONFIG_V2)
        self.assertEqual(test_particiones._SHA_CONFIG_V2_M0, fijados.SHA_CONFIG_V2_M0)

    @unittest.skip("lee datos reales (ERA5L, geopotencial, NASADEM, grilla, GHS-POP y SINCA): se comprueban en M2a o en "
                   "la batería con permiso explícito; las olas 0 y 1 son sintéticas (decisión 4 de COORDINACION_M1.md)")
    def test_huellas_9_3_de_datos(self):
        """Las huellas de HUELLAS_DATOS y HUELLAS_ERA5L_AGREGADAS coinciden con los archivos reales."""

    def test_huella_del_interprete(self):
        """FIJ-3: la huella de ``micromamba list -n amb_v2`` es la de M0 (0b5bc40b…). El proceso lo lanza la prueba."""
        if not _MICROMAMBA.is_file():
            self.skipTest("falta micromamba; la prueba no se da por aprobada")
        salida = subprocess.run([str(_MICROMAMBA), "list", "-n", "amb_v2"], capture_output=True, text=True,
                                timeout=120, check=True).stdout
        self.assertEqual(fijados.huella_micromamba(salida), fijados.SHA_MICROMAMBA_LIST)
        self.assertEqual(fijados.comprobar_codigo_fijado(AP, APH, micromamba_list=salida), [])
        self.assertTrue(fijados.comprobar_codigo_fijado(AP, APH, micromamba_list=salida + "x"))

    def test_comprobar_codigo_fijado_detecta_faltas_y_cambios(self):
        """Con repositorios sintéticos: cada archivo que falta y cada huella distinta es una diferencia, por alias."""
        with tempfile.TemporaryDirectory() as tmp:
            ap, aph = Path(tmp) / "AP", Path(tmp) / "APH"
            difs = fijados.comprobar_codigo_fijado(ap, aph)
            self.assertEqual(len(difs), len(fijados.HUELLAS_CODIGO))
            repo, ruta, _, _ = fijados.HUELLAS_CODIGO[0]
            (ap / ruta).parent.mkdir(parents=True)
            (ap / ruta).write_text("cambiado\n", encoding="utf-8")
            difs = fijados.comprobar_codigo_fijado(ap, aph)
            self.assertEqual(len(difs), len(fijados.HUELLAS_CODIGO))
            self.assertTrue(any(d.startswith(f"AP/{ruta}") and "≠" in d for d in difs), difs)
            self.assertTrue(all(entorno.sin_datos_privados(d) and tmp not in d for d in difs))


class PruebasCodigoFijado(_ConLimpieza):
    def test_adaptador_y_dmc_features_por_ruta_y_huella(self):
        """f61559ea… y 15762856…; una huella distinta lanza error."""
        self.exigir(AP / fijados.RUTA_ADAPTADOR, AP / fijados.RUTA_DMC_FEATURES)
        adaptador = fijados.cargar_adaptador(AP)
        for nombre in ("leer_artefacto", "normalizar", "unir_sidecar"):
            self.assertTrue(callable(getattr(adaptador, nombre)), nombre)
        self.assertEqual(Path(adaptador.__file__).resolve(), (AP / fijados.RUTA_ADAPTADOR).resolve())
        self.assertIs(fijados.cargar_adaptador(AP), adaptador)
        dmc = fijados.cargar_dmc_features(AP)
        self.assertTrue(callable(dmc.cargar_dmc))
        self.assertEqual(Path(dmc.__file__).resolve(), (AP / fijados.RUTA_DMC_FEATURES).resolve())
        with mock.patch.object(fijados, "SHA_ADAPTADOR", "0" * 64):
            self._nombres.append(fijados_reloj.MODULO_ADAPTADOR)
            with self.assertRaises((ValueError, RuntimeError)):
                fijados.cargar_adaptador(AP)
        for nombre in (*fijados.MODULOS_PROHIBIDOS, *fijados.NUNCA_CARGADOS):
            self.assertNotIn(nombre, sys.modules)

    def test_descargador_vigente(self):
        """El descargador 578fa26e…, sólo para datos sintéticos (run_download y parse_report)."""
        self.exigir(AP / fijados.RUTA_DESCARGADOR)
        descargador = fijados.cargar_descargador(AP)
        self.assertTrue(callable(descargador.run_download) and callable(descargador.parse_report))
        self.assertEqual(_sha(Path(descargador.__file__)), fijados.SHA_DESCARGADOR)

    def test_preflight_y_runner_nunca_se_cargan(self):
        """§1 del diseño: sólo su huella; cargar preflight_v3 fijaría los hilos en 2."""
        self.exigir(AP / fijados.RUTA_DMC_FEATURES)
        fijados.cargar_dmc_features(AP)
        fijados.cargar_validador_reloj(AP, fijados.huellas_reloj(AP), permitir_cargados=True)
        for nombre in fijados.NUNCA_CARGADOS:
            self.assertNotIn(nombre, sys.modules)
        fuente = Path(fijados.__file__).read_text(encoding="utf-8")
        llamadas = {n.func.attr for n in ast.walk(ast.parse(fuente))
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        self.assertNotIn("cargar_preflight", llamadas)
        self.assertEqual(os.environ.get("OPENBLAS_NUM_THREADS"), "1")

    def test_sin_comun_modelo_en_sys_modules(self):
        """Ni _comun_modelo ni _common quedan cargados (se leen por AST)."""
        self.exigir(AP / fijados.RUTA_COMUN_MODELO, AP / fijados.RUTA_FEATURES)
        fijados.macrozona_region(AP)
        fijados.regla_el_features(AP)
        for nombre in fijados.MODULOS_PROHIBIDOS:
            self.assertNotIn(nombre, sys.modules)


class PruebasClausuraReloj(_ConLimpieza):
    def test_clausura_del_reloj(self):
        """FIJ-1 y FIJ-8 (MC-17, E5-F): las siete huellas (el __init__ y los seis de MODULOS_RELOJ) son las del commit
        1da0236, el del nuevo cierre de C1. Si falla, el reloj cambió y hay que recalcular la clausura (§10, punto 2,
        del diseño)."""
        self.assertEqual(fijados.MODULOS_RELOJ, ("entorno", "fijados", "politica", "tipos", "constantes", "tablas"))
        self.assertEqual(fijados.ARCHIVOS_RELOJ, ("__init__", *fijados.MODULOS_RELOJ))
        huellas = fijados.huellas_reloj(AP)
        self.assertEqual(list(huellas), list(fijados.ARCHIVOS_RELOJ))
        self.assertTrue(huellas["__init__"].startswith("de78881a"))
        self.assertIs(fijados.HUELLAS_RELOJ, fijados.HUELLAS_RELOJ_1DA0236)
        self.assertEqual(huellas, dict(fijados.HUELLAS_RELOJ),
                         "el reloj cambió desde 1da0236: recalcular la clausura (MC-17)")

    def test_clausura_en_git_y_su_historia(self):
        """FIJ-1 (E5-F): con ``git cat-file``, las siete huellas fijadas son las de AP 1da0236 y las de la historia, las de
        AP 4b50b0d; entre los dos commits sólo cambió ``constantes.py`` (10354281… → 95deee46…). El texto v1.2 y el
        addendum de C1 del reloj son los de APH 1f59e6e y 73615e8 (sólo su huella: no se leen). Sin git o sin esos
        commits, se omite y no se da por aprobada."""
        git = shutil.which("git")
        if git is None or not (AP / ".git").exists() or not (APH / ".git").exists():
            self.skipTest("sin git o sin los repositorios: no se da por aprobada")

        def huella(repo, commit, ruta):
            r = subprocess.run([git, "-C", str(repo), "cat-file", "blob", f"{commit}:{ruta}"], capture_output=True,
                               timeout=60, check=False)
            if r.returncode != 0:
                self.skipTest(f"{commit[:7]} no trae {ruta}: no se da por aprobada")
            return hashlib.sha256(r.stdout).hexdigest()
        self.assertEqual(fijados.COMMIT_RELOJ, "1da023640f8e3c65fba461480b5faaf06f158ba2")
        self.assertEqual(fijados.COMMIT_RELOJ_4B50B0D, "4b50b0d027d7652843e34de3ea68c386b693be4e")
        for commit, esperadas in ((fijados.COMMIT_RELOJ, fijados.HUELLAS_RELOJ_1DA0236),
                                  (fijados.COMMIT_RELOJ_4B50B0D, fijados.HUELLAS_RELOJ_4B50B0D)):
            self.assertEqual(list(esperadas), list(fijados.ARCHIVOS_RELOJ))
            for m in fijados.ARCHIVOS_RELOJ:
                with self.subTest(commit=commit[:7], archivo=m):
                    self.assertEqual(huella(AP, commit, f"{fijados.RUTA_RELOJ}/{m}.py"), esperadas[m])
        distintos = [m for m in fijados.ARCHIVOS_RELOJ
                     if fijados.HUELLAS_RELOJ_1DA0236[m] != fijados.HUELLAS_RELOJ_4B50B0D[m]]
        self.assertEqual(distintos, ["constantes"])
        textos = {ruta: sha for repo, ruta, sha, _ in fijados.HUELLAS_CODIGO if repo == "APH"}
        for commit, ruta, sha in (("1f59e6e", "auditoria/20261027/reloj_dmc/PROTOCOLO_RELOJ_DMC_v1.2.md",
                                   fijados.SHA_RELOJ_V1_2),
                                  ("73615e8", "auditoria/20261027/reloj_dmc/addendum_c1.json",
                                   fijados.SHA_ADDENDUM_C1_RELOJ)):
            with self.subTest(ruta=ruta):
                self.assertEqual(textos[ruta], sha)
                self.assertEqual(huella(APH, commit, ruta), sha)

    def test_validador_es_el_de_reloj(self):
        """validar_regla_reloj_dmc es el mismo objeto de reloj_dmc.politica, del reloj de este AP, con su firma. La segunda
        llamada devuelve el mismo; sin permitir_cargados se prueba en un intérprete nuevo, porque en este proceso otras
        pruebas pueden haber cargado el reloj por otro camino (H2)."""
        validar = fijados.cargar_validador_reloj(AP, fijados.huellas_reloj(AP), permitir_cargados=True)
        politica = sys.modules["reloj_dmc.politica"]
        self.assertIs(fijados.cargar_validador_reloj(AP, fijados.huellas_reloj(AP), permitir_cargados=True), validar)
        self.assertIs(validar, politica.validar_regla_reloj_dmc)
        self.assertEqual(Path(politica.__file__).resolve(), (AP / fijados.RUTA_RELOJ / "politica.py").resolve())
        parametros = inspect.signature(validar).parameters
        self.assertEqual(list(parametros), ["regla", "artefacto_sha256", "politica_ruta"])
        self.assertIs(parametros["politica_ruta"].kind, inspect.Parameter.KEYWORD_ONLY)
        with tempfile.TemporaryDirectory() as tmp:     # una política que no existe: rechazo, sin leer la publicada
            with self.assertRaises(ValueError):
                validar({}, "0" * 64, politica_ruta=Path(tmp) / "politica_reloj_dmc.json")

    def test_validador_exige_las_huellas(self):
        """Huellas distintas o claves incompletas: error antes de importar; si cambian al importar, también."""
        huellas = fijados.huellas_reloj(AP)
        with self.assertRaises(ValueError):
            fijados.cargar_validador_reloj(AP, {**huellas, "politica": "1" * 64})
        with self.assertRaises(ValueError):
            fijados.cargar_validador_reloj(AP, {k: v for k, v in huellas.items() if k != "tablas"})
        with self.assertRaises(ValueError):
            fijados.cargar_validador_reloj(AP, {**huellas, "tipos": "corta"})
        with self.assertRaises(ValueError):                 # sin la del __init__ (FIJ-8)
            fijados.cargar_validador_reloj(AP, {k: v for k, v in huellas.items() if k != "__init__"})
        distintas = {**huellas, "tablas": "2" * 64}
        with mock.patch.object(fijados, "_VALIDADOR", []), \
                mock.patch.object(fijados, "huellas_reloj", side_effect=[huellas, distintas]):
            with self.assertRaises(ValueError):
                fijados.cargar_validador_reloj(AP, huellas, permitir_cargados=True)

    def test_validador_con_el_reloj_ya_cargado_falla(self):
        """B-H17 (FIJ-2), en un intérprete nuevo: sin nada del reloj cargado, la comprobación es previa y funciona (y
        una segunda llamada devuelve el mismo objeto); con reloj_dmc.tipos cargado antes, falla salvo con
        permitir_cargados."""
        codigo = (
            "import json, sys; sys.path.insert(0, sys.argv[1])\n"
            "from meteo_combinada import entorno, fijados\n"
            "ap = entorno.rutas_reales().ap\n"
            "antes = sorted(m for m in sys.modules if m.startswith('reloj_dmc'))\n"
            "v = fijados.cargar_validador_reloj(ap, fijados.huellas_reloj(ap))\n"
            "otra = fijados.cargar_validador_reloj(ap, fijados.huellas_reloj(ap)) is v\n"
            "print(json.dumps({'antes': antes, 'otra': otra}))\n")
        r = json.loads(_subproceso(codigo))
        self.assertEqual(r, {"antes": ["reloj_dmc", "reloj_dmc.entorno", "reloj_dmc.fijados"], "otra": True})
        codigo = (
            "import json, sys; sys.path.insert(0, sys.argv[1])\n"
            "import reloj_dmc.tipos\n"
            "from meteo_combinada import entorno, fijados\n"
            "ap = entorno.rutas_reales().ap\n"
            "try:\n"
            "    fijados.cargar_validador_reloj(ap, fijados.huellas_reloj(ap)); falla = False\n"
            "except RuntimeError:\n"
            "    falla = True\n"
            "v = fijados.cargar_validador_reloj(ap, fijados.huellas_reloj(ap), permitir_cargados=True)\n"
            "print(json.dumps({'falla': falla, 'politica': 'reloj_dmc.politica' in sys.modules, 'v': callable(v)}))\n")
        self.assertEqual(json.loads(_subproceso(codigo)), {"falla": True, "politica": True, "v": True})

    def test_validador_rechaza_un_reloj_de_otra_carpeta(self):
        """Los módulos del reloj cargados deben ser los de AP/scripts_modelo_1km/reloj_dmc (H4: por ese motivo y no por
        otro)."""
        huellas = fijados.huellas_reloj(AP)
        with tempfile.TemporaryDirectory() as tmp:
            otro = Path(tmp) / "AP"
            shutil.copytree(AP / fijados.RUTA_RELOJ, otro / fijados.RUTA_RELOJ,
                            ignore=shutil.ignore_patterns("tests", "*.md", "__pycache__"))
            with self.assertRaisesRegex(RuntimeError, "otra carpeta"):
                fijados.cargar_validador_reloj(otro, huellas)
            with self.assertRaisesRegex(RuntimeError, "otra carpeta"):
                fijados.cargar_validador_reloj(otro, huellas, permitir_cargados=True)


class PruebasPixelReloj(_ConLimpieza):
    """FIJ-11 (MC-52, A27): ``reloj_dmc.extraccion.elegir_pixel`` por ``fijados``, con la clausura ampliada."""

    def _pixel(self):
        self.exigir(APH / fijados.RUTA_RELOJ_C0, APH / fijados.RUTA_JSON_RELOJ_C0)
        return fijados.cargar_elegir_pixel(AP, APH, fijados.HUELLAS_CLAUSURA, permitir_cargados=True)

    def test_clausura_ampliada(self):
        """FIJ-11: lo que importa extraccion.py del reloj, en cadena y por AST (también dentro de funciones), son los
        archivos de ARCHIVOS_PIXEL; con politica, los diez de ARCHIVOS_CLAUSURA (los siete de FIJ-8 más MODULOS_PIXEL).
        Sus huellas en la copia de trabajo son las fijadas (las de AP 1da0236). Si falla, el reloj cambió y hay que
        recalcular la clausura (§10, punto 2, del diseño)."""
        carpeta = AP / fijados.RUTA_RELOJ
        cierre, pendientes = set(), ["extraccion"]
        while pendientes:
            m = pendientes.pop()
            if m not in cierre:
                cierre.add(m)
                pendientes.extend(_importados_del_reloj(carpeta / f"{m}.py") - cierre)
        self.assertEqual(cierre | {"__init__"}, set(fijados.ARCHIVOS_PIXEL))
        self.assertEqual(len(fijados.ARCHIVOS_PIXEL), len(set(fijados.ARCHIVOS_PIXEL)))
        self.assertEqual(fijados.MODULOS_PIXEL, ("extraccion", "numerico", "umbrales"))
        self.assertEqual(set(fijados.MODULOS_PIXEL), cierre - set(fijados.ARCHIVOS_RELOJ))
        self.assertEqual(fijados.ARCHIVOS_CLAUSURA, (*fijados.ARCHIVOS_RELOJ, *fijados.MODULOS_PIXEL))
        self.assertEqual(set(fijados.ARCHIVOS_CLAUSURA) - set(fijados.ARCHIVOS_PIXEL), {"politica"})
        self.assertEqual(fijados.ARCHIVOS_PIXEL, ("__init__", "entorno", "fijados", *fijados.CARGADOS_DESPUES_PIXEL))
        self.assertIs(fijados.HUELLAS_CLAUSURA, fijados.HUELLAS_CLAUSURA_1DA0236)
        self.assertEqual(list(fijados.HUELLAS_CLAUSURA), list(fijados.ARCHIVOS_CLAUSURA))
        self.assertEqual({m: fijados.HUELLAS_CLAUSURA[m] for m in fijados.ARCHIVOS_RELOJ}, dict(fijados.HUELLAS_RELOJ))
        huellas = fijados.huellas_clausura(AP)
        self.assertEqual(list(huellas), list(fijados.ARCHIVOS_CLAUSURA))
        self.assertEqual(huellas, dict(fijados.HUELLAS_CLAUSURA),
                         "el reloj cambió desde 1da0236: recalcular la clausura ampliada (FIJ-11)")
        self.assertEqual({m: huellas[m][:8] for m in fijados.MODULOS_PIXEL},
                         {"extraccion": "dc6a8788", "numerico": "c463336c", "umbrales": "075834dc"})

    def test_clausura_ampliada_en_git(self):
        """FIJ-11: con ``git cat-file``, las diez huellas de la clausura ampliada son las de AP 1da0236 (el código del
        cierre de C1 del reloj, igual que en test_clausura_en_git_y_su_historia). En AP 4b50b0d umbrales.py era el mismo,
        y numerico.py y extraccion.py eran otros (errata E-1 de la Enmienda 5 del reloj). El texto y el JSON de umbrales
        del reloj en C0 son los de APH d02f918, y el JSON está en HUELLAS_CODIGO. Sin git o sin esos commits, se omite y
        no se da por aprobada."""
        self.assertEqual(fijados.COMMIT_RELOJ, "1da023640f8e3c65fba461480b5faaf06f158ba2")
        for m in fijados.ARCHIVOS_CLAUSURA:
            with self.subTest(archivo=m):
                self.assertEqual(_huella_en_git(self, AP, fijados.COMMIT_RELOJ, f"{fijados.RUTA_RELOJ}/{m}.py"),
                                 fijados.HUELLAS_CLAUSURA_1DA0236[m])
        en_4b50b0d = {m: _huella_en_git(self, AP, fijados.COMMIT_RELOJ_4B50B0D, f"{fijados.RUTA_RELOJ}/{m}.py")
                      for m in fijados.MODULOS_PIXEL}
        self.assertEqual([m for m in fijados.MODULOS_PIXEL if en_4b50b0d[m] != fijados.HUELLAS_PIXEL_1DA0236[m]],
                         ["extraccion", "numerico"])
        self.assertEqual(fijados.COMMIT_RELOJ_C0_APH, "d02f91882a13bcefc2cf90712dffba3760f346b6")
        for ruta, sha in ((fijados.RUTA_RELOJ_C0, fijados.SHA_RELOJ_C0),
                          (fijados.RUTA_JSON_RELOJ_C0, fijados.SHA_JSON_RELOJ_C0)):
            with self.subTest(ruta=ruta):
                self.assertEqual(_huella_en_git(self, APH, fijados.COMMIT_RELOJ_C0_APH, ruta), sha)
        self.assertIn(("APH", fijados.RUTA_JSON_RELOJ_C0, fijados.SHA_JSON_RELOJ_C0),
                      [(r, p, s) for r, p, s, _ in fijados.HUELLAS_CODIGO])

    def test_elegir_pixel_es_el_del_reloj(self):
        """El elegir_pixel que entrega fijados es el mismo objeto de reloj_dmc.extraccion, del reloj de este AP y con su
        firma; los umbrales son los de C0 (cargar_c0 del reloj) y el radio, 15 km. Una segunda llamada devuelve el mismo
        objeto, ya sin permitir_cargados. No queda nada prohibido en sys.modules."""
        pixel = self._pixel()
        extraccion = sys.modules[fijados.NOMBRE_EXTRACCION]
        self.assertIs(pixel.elegir_pixel, extraccion.elegir_pixel)
        self.assertIs(pixel.EleccionPixel, extraccion.EleccionPixel)
        self.assertEqual(pixel.elegir_pixel.__module__, "reloj_dmc.extraccion")
        self.assertEqual(Path(extraccion.__file__).resolve(), (AP / fijados.RUTA_RELOJ / "extraccion.py").resolve())
        self.assertEqual(list(inspect.signature(pixel.elegir_pixel).parameters),
                         ["lat", "lon", "catalogo_pixeles", "validos", "umbrales"])
        umbrales_reloj = sys.modules["reloj_dmc.umbrales"]
        self.assertIs(type(pixel.umbrales), umbrales_reloj.Umbrales)
        self.assertEqual(pixel.umbrales.sha256_json, fijados.SHA_JSON_RELOJ_C0)
        self.assertEqual((umbrales_reloj.PROTOCOLO_C0, umbrales_reloj.SHA_PROTOCOLO_C0),
                         (fijados.RUTA_RELOJ_C0, fijados.SHA_RELOJ_C0))
        self.assertEqual(pixel.radio_km, 15)
        self.assertIs(type(pixel.radio_km), int)
        self.assertEqual(pixel.umbrales.f(fijados.UMBRAL_PIXEL_RELOJ), pixel.radio_km)
        self.assertEqual(dict(pixel.huellas), dict(fijados.HUELLAS_CLAUSURA))
        # la que cargó ella; sin permitir_cargados, en un intérprete nuevo (test_carga_en_un_interprete_nuevo; H2)
        self.assertIs(fijados.cargar_elegir_pixel(AP, APH, fijados.HUELLAS_CLAUSURA, permitir_cargados=True), pixel)
        self.assertIs(pixel.coordenadas_en_rango, sys.modules["reloj_dmc.tablas"].coordenadas_en_rango)
        for m in fijados.ARCHIVOS_CLAUSURA[1:]:
            modulo = sys.modules.get(f"reloj_dmc.{m}")
            if modulo is not None:
                self.assertEqual(Path(modulo.__file__).resolve(), (AP / fijados.RUTA_RELOJ / f"{m}.py").resolve(), m)
        for nombre in (*fijados.MODULOS_PROHIBIDOS, *fijados.NUNCA_CARGADOS):
            self.assertNotIn(nombre, sys.modules)

    def test_elegir_pixel_sobre_un_catalogo_sintetico(self):
        """RELOJ §3.3 sobre un catálogo sintético de 0,1°: la celda propia válida; si no, el centro válido más cercano a
        ≤ 15 km, con empate por menor pixel_id (sin importar el orden del catálogo); nada a más de 15 km."""
        pixel = self._pixel()
        E = pixel.EleccionPixel
        filas = [(10 * i + j, -34.9 - 0.1 * (i - 1), -71.1 + 0.1 * (j - 1)) for i in (1, 2, 3) for j in (1, 2, 3)]
        catalogo = _catalogo(filas)
        centro = {p: (la, lo) for p, la, lo in filas}
        todos = {p for p, _, _ in filas}

        def comprobar(lat, lon, cat, validos, pixel_id, costera):
            r = pixel.elegir(lat, lon, cat, validos)
            self.assertIsInstance(r, E)
            self.assertEqual(r, pixel.elegir_pixel(lat, lon, cat, validos, pixel.umbrales))
            if pixel_id is None:
                self.assertEqual(r, E(None, None, False))
                return
            self.assertEqual((r.pixel_id, r.costera), (pixel_id, costera))
            self.assertAlmostEqual(r.distancia_km, _km(lat, lon, *centro[pixel_id]), places=6)

        with self.subTest(caso="celda propia válida"):
            comprobar(-35.02, -71.01, catalogo, todos, 22, False)
        with self.subTest(caso="celda propia no válida: el centro válido más cercano"):
            validos = todos - {22}
            esperado = min(validos, key=lambda p: _km(-35.02, -71.03, *centro[p]))
            self.assertEqual(esperado, 21)
            self.assertLess(_km(-35.02, -71.03, *centro[21]), pixel.radio_km)
            comprobar(-35.02, -71.03, catalogo, validos, 21, True)
        with self.subTest(caso="empate: menor pixel_id"):
            self.assertAlmostEqual(_km(-35.0, -71.0, *centro[21]), _km(-35.0, -71.0, *centro[23]), places=9)
            comprobar(-35.0, -71.0, catalogo, {21, 23}, 21, True)
            comprobar(-35.0, -71.0, catalogo.iloc[::-1].reset_index(drop=True), {21, 23}, 21, True)
            invertidos = [({21: 23, 23: 21}.get(p, p), la, lo) for p, la, lo in filas]   # el 21 queda al este
            centro_inv = {p: (la, lo) for p, la, lo in invertidos}
            r = pixel.elegir(-35.0, -71.0, _catalogo(invertidos), {21, 23})
            self.assertEqual((r.pixel_id, r.costera), (21, True))
            self.assertGreater(centro_inv[21][1], -71.0)
        with self.subTest(caso="a 15 km o menos sí, a más no"):
            uno = _catalogo([(7, -35.0, -71.0)])
            centro[7] = (-35.0, -71.0)
            cerca, lejos = -35.0 + 14.95 / _KM_POR_GRADO, -35.0 + 15.05 / _KM_POR_GRADO
            self.assertAlmostEqual(_km(cerca, -71.0, -35.0, -71.0), 14.95, places=9)
            comprobar(cerca, -71.0, uno, {7}, 7, True)
            comprobar(lejos, -71.0, uno, {7}, None, False)
            comprobar(-35.0 + 20 / _KM_POR_GRADO, -71.0, uno, {7}, None, False)
        with self.subTest(caso="sin píxel válido cerca: nada, aunque haya celdas no válidas cerca"):
            lejano = _catalogo(filas + [(99, -35.2, -71.0)])          # ≈ 20 km al sur de la estación
            centro[99] = (-35.2, -71.0)
            self.assertGreater(_km(-35.02, -71.01, *centro[99]), pixel.radio_km)
            comprobar(-35.02, -71.01, lejano, {99}, None, False)
            comprobar(-35.02, -71.01, catalogo, set(), None, False)

    def test_radio_igual_en_los_textos_del_reloj(self):
        """FIJ-11: la línea «Píxel» del Anexo B (PIXEL_RADIO_KM = 15) es la misma en los seis textos del reloj, del v1 al
        v1.0.5, con regenerar_desde_texto y traducir_fijos del reloj, y en el JSON de C0. Cada texto con su huella (la del
        reloj y, si M1 la fija, la de HUELLAS_CODIGO). El v1.2 no está entre ellos y no se lee (MC-17)."""
        pixel = self._pixel()
        mod_umbrales, rc = sys.modules["reloj_dmc.umbrales"], sys.modules["reloj_dmc.constantes"]
        self.assertEqual([v for v, _, _ in rc.TEXTOS_PROTOCOLO], ["v1", "v1.0.1", "v1.0.2", "v1.0.3", "v1.0.4", "v1.0.5"])
        self.assertEqual(rc.TEXTOS_PROTOCOLO[0][1:], (fijados.RUTA_RELOJ_C0, fijados.SHA_RELOJ_C0))
        de_m1 = {ruta: sha for repo, ruta, sha, _ in fijados.HUELLAS_CODIGO if repo == "APH"}
        lineas = set()
        for version, ruta, sha in rc.TEXTOS_PROTOCOLO:
            with self.subTest(version=version):
                self.exigir(APH / ruta)
                datos = (APH / ruta).read_bytes()
                self.assertEqual(hashlib.sha256(datos).hexdigest(), sha)
                if ruta in de_m1:
                    self.assertEqual(de_m1[ruta], sha)
                regenerado = mod_umbrales.regenerar_desde_texto(datos.decode("utf-8"), Path(ruta).name)
                self.assertEqual(mod_umbrales.traducir_fijos(regenerado["fijos_texto"])[fijados.UMBRAL_PIXEL_RELOJ],
                                 pixel.radio_km)
                lineas |= {linea for linea in regenerado["fijos_texto"] if linea.startswith("- **Píxel:**")}
        self.assertEqual(len(lineas), 1, lineas)
        self.assertTrue(next(iter(lineas)).startswith("- **Píxel:** 15 km;"))
        c0 = json.loads((APH / fijados.RUTA_JSON_RELOJ_C0).read_text(encoding="utf-8"))
        self.assertEqual({linea for linea in c0["fijos_texto"] if linea.startswith("- **Píxel:**")}, lineas)
        self.assertEqual(rc.VERSION_C1, "v1.2")
        self.assertNotIn(rc.VERSION_C1, [v for v, _, _ in rc.TEXTOS_PROTOCOLO])

    def test_cargar_elegir_pixel_exige_las_huellas(self):
        """Claves incompletas o de más, huellas distintas o mal escritas: error antes de cargar; si cambian al cargar,
        también. Un texto o un JSON de C0 alterados o ausentes, y un reloj de otra carpeta, se rechazan."""
        self.exigir(APH / fijados.RUTA_RELOJ_C0, APH / fijados.RUTA_JSON_RELOJ_C0)
        huellas = dict(fijados.HUELLAS_CLAUSURA)
        for malas in (dict(fijados.HUELLAS_RELOJ), {k: v for k, v in huellas.items() if k != "numerico"},
                      {**huellas, "otro": "3" * 64}, {**huellas, "extraccion": "1" * 64},
                      {**huellas, "umbrales": "corta"}):
            with self.subTest(claves=sorted(set(malas) ^ set(huellas)) or "huella"), self.assertRaises(ValueError):
                fijados.cargar_elegir_pixel(AP, APH, malas, permitir_cargados=True)
        distintas = {**huellas, "numerico": "2" * 64}
        with mock.patch.object(fijados, "_PIXEL", []), \
                mock.patch.object(fijados, "huellas_clausura", side_effect=[huellas, distintas]):
            with self.assertRaisesRegex(ValueError, "cambió mientras se cargaba"):
                fijados.cargar_elegir_pixel(AP, APH, huellas, permitir_cargados=True)
        with tempfile.TemporaryDirectory() as tmp:
            aph = Path(tmp) / "APH"
            for ruta in (fijados.RUTA_RELOJ_C0, fijados.RUTA_JSON_RELOJ_C0):
                (aph / ruta).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(APH / ruta, aph / ruta)
            for ruta in (fijados.RUTA_RELOJ_C0, fijados.RUTA_JSON_RELOJ_C0):
                with self.subTest(ruta=ruta):
                    original = (aph / ruta).read_bytes()
                    (aph / ruta).write_bytes(original + b"\n")
                    with self.assertRaises(ValueError):
                        fijados.cargar_elegir_pixel(AP, aph, huellas, permitir_cargados=True)
                    (aph / ruta).unlink()
                    with self.assertRaises(FileNotFoundError):
                        fijados.cargar_elegir_pixel(AP, aph, huellas, permitir_cargados=True)
                    (aph / ruta).write_bytes(original)
        for nombre in (*fijados.MODULOS_PROHIBIDOS, *fijados.NUNCA_CARGADOS):
            self.assertNotIn(nombre, sys.modules)

    def test_reloj_de_otra_carpeta_o_con_bytecode(self):
        """H3 y H4, en las dos funciones, sobre una copia temporal del reloj (nunca en reloj_dmc/): con un .pyc fabricado
        en su __pycache__, o con la carpeta __pycache__ vacía, se rechaza por el bytecode guardado (se ejecutaría en lugar
        de los bytes con huella); sin él, por estar cargado el reloj desde otra carpeta. La comprobación de después de
        cargar también se hace."""
        self.exigir(APH / fijados.RUTA_RELOJ_C0, APH / fijados.RUTA_JSON_RELOJ_C0)
        if sys.pycache_prefix is not None:
            self.skipTest("con sys.pycache_prefix el .pyc no va en la copia temporal: no se da por aprobada")
        import importlib.util
        import py_compile
        llamadas = (("validador", lambda ap, **k: fijados.cargar_validador_reloj(ap, dict(fijados.HUELLAS_RELOJ), **k)),
                    ("píxel", lambda ap, **k: fijados.cargar_elegir_pixel(ap, APH, fijados.HUELLAS_CLAUSURA, **k)))
        with tempfile.TemporaryDirectory() as tmp:
            otro = Path(tmp) / "AP"
            copia = otro / fijados.RUTA_RELOJ
            shutil.copytree(AP / fijados.RUTA_RELOJ, copia, ignore=shutil.ignore_patterns("tests", "*.md", "__pycache__"))
            pyc = Path(importlib.util.cache_from_source(str(copia / "tablas.py")))
            self.assertTrue(pyc.is_relative_to(copia / "__pycache__"))
            py_compile.compile(str(copia / "tablas.py"), cfile=str(pyc), doraise=True)
            for nombre, llamar in llamadas:
                for permitir in (False, True):
                    with self.subTest(funcion=nombre, caso=".pyc", permitir=permitir):
                        with self.assertRaisesRegex(RuntimeError, r"bytecode guardado antes de .*tablas\.pyc"):
                            llamar(otro, permitir_cargados=permitir)
            pyc.unlink()
            for nombre, llamar in llamadas:
                with self.subTest(funcion=nombre, caso="__pycache__ vacía"):
                    with self.assertRaisesRegex(RuntimeError, r"bytecode guardado antes de .*\(__pycache__\)"):
                        llamar(otro)
            (copia / "__pycache__").rmdir()
            for nombre, llamar in llamadas:
                for permitir in (False, True):
                    with self.subTest(funcion=nombre, caso="otra carpeta", permitir=permitir):
                        with self.assertRaisesRegex(RuntimeError, "otra carpeta"):
                            llamar(otro, permitir_cargados=permitir)
        self.assertFalse((AP / fijados.RUTA_RELOJ / "__pycache__").exists())
        despues = RuntimeError("bytecode guardado después (simulado)")
        with mock.patch.object(fijados, "_VALIDADOR", []), \
                mock.patch.object(fijados, "_exigir_sin_cache", side_effect=[None, despues]) as guarda:
            with self.assertRaisesRegex(RuntimeError, "simulado"):
                fijados.cargar_validador_reloj(AP, dict(fijados.HUELLAS_RELOJ), permitir_cargados=True)
            self.assertEqual([c.args[2] for c in guarda.call_args_list], ["antes de importar", "después de importar"])
        with mock.patch.object(fijados, "_PIXEL", []), \
                mock.patch.object(fijados, "_exigir_sin_cache", side_effect=[None, despues]) as guarda:
            with self.assertRaisesRegex(RuntimeError, "simulado"):
                fijados.cargar_elegir_pixel(AP, APH, fijados.HUELLAS_CLAUSURA, permitir_cargados=True)
            self.assertEqual([c.args[2] for c in guarda.call_args_list], ["antes de cargar", "después de cargar"])
            self.assertEqual(guarda.call_args_list[0].args[1], fijados.ARCHIVOS_CLAUSURA)

    def test_guardas_sin_prueba_hasta_la_ola_5(self):
        """H5: con _common en sys.modules antes de llamar, RuntimeError en las dos funciones; en una segunda llamada, unas
        huellas en disco distintas dan ValueError antes de cargar (el atajo de la segunda llamada va después); y unas
        anclas de C0 en reloj_dmc.umbrales distintas de las de M1, o unos umbrales que no son los del JSON de C0, se
        rechazan."""
        pixel = self._pixel()
        with mock.patch.dict(sys.modules, {"_common": ModuleType("_common")}):
            with self.assertRaisesRegex(RuntimeError, "_common"):
                fijados.cargar_elegir_pixel(AP, APH, fijados.HUELLAS_CLAUSURA, permitir_cargados=True)
            with self.assertRaisesRegex(RuntimeError, "_common"):
                fijados.cargar_validador_reloj(AP, dict(fijados.HUELLAS_RELOJ), permitir_cargados=True)
        self.assertNotIn("_common", sys.modules)
        self.assertIs(fijados.cargar_elegir_pixel(AP, APH, fijados.HUELLAS_CLAUSURA, permitir_cargados=True), pixel)
        for m in ("tablas", "umbrales", "extraccion"):
            otras = {**dict(fijados.HUELLAS_CLAUSURA), m: "2" * 64}
            with self.subTest(archivo=m), mock.patch.object(fijados, "huellas_clausura", return_value=otras):
                with self.assertRaisesRegex(ValueError, "antes de cargar"):
                    fijados.cargar_elegir_pixel(AP, APH, fijados.HUELLAS_CLAUSURA, permitir_cargados=True)
        fijados.cargar_validador_reloj(AP, dict(fijados.HUELLAS_RELOJ), permitir_cargados=True)
        with mock.patch.object(fijados, "huellas_reloj", return_value={**dict(fijados.HUELLAS_RELOJ), "tipos": "2" * 64}):
            with self.assertRaisesRegex(ValueError, "antes de importar"):
                fijados.cargar_validador_reloj(AP, dict(fijados.HUELLAS_RELOJ), permitir_cargados=True)
        mod_umbrales = sys.modules["reloj_dmc.umbrales"]
        for nombre, valor in (("PROTOCOLO_C0", "otra/ruta.md"), ("SHA_PROTOCOLO_C0", "0" * 64),
                              ("JSON_C0", "otra/ruta.json"), ("SHA_JSON_C0", "0" * 64)):
            with self.subTest(ancla=nombre), mock.patch.object(fijados, "_PIXEL", []), \
                    mock.patch.object(mod_umbrales, nombre, valor):
                with self.assertRaisesRegex(RuntimeError, "ancla en C0"):
                    fijados.cargar_elegir_pixel(AP, APH, fijados.HUELLAS_CLAUSURA, permitir_cargados=True)
        with mock.patch.object(fijados, "_PIXEL", []), \
                mock.patch.object(mod_umbrales, "cargar_c0", return_value=SimpleNamespace(sha256_json="0" * 64)):
            with self.assertRaisesRegex(RuntimeError, "JSON de C0"):
                fijados.cargar_elegir_pixel(AP, APH, fijados.HUELLAS_CLAUSURA, permitir_cargados=True)
        self.assertIs(fijados.cargar_elegir_pixel(AP, APH, fijados.HUELLAS_CLAUSURA, permitir_cargados=True), pixel)

    def test_huella_falsa_falla_antes_de_cargar(self):
        """H1, en un intérprete nuevo: con la huella esperada de cualquiera de los diez archivos cambiada por otra bien
        escrita («1»·64), ValueError «antes de cargar», sin cargar nada del reloj (ni tipos, constantes, tablas,
        numerico, umbrales o extraccion, ni extraccion por ruta). Lo mismo para el validador con sus siete archivos
        («antes de importar»)."""
        self.exigir(APH / fijados.RUTA_RELOJ_C0, APH / fijados.RUTA_JSON_RELOJ_C0)
        codigo = (
            "import json, sys; sys.path.insert(0, sys.argv[1])\n"
            "from meteo_combinada import entorno, fijados\n"
            "from reloj_dmc import fijados as rf\n"
            "rutas = entorno.rutas_reales(); ap, aph = rutas.ap, rutas.aph\n"
            "def probar(llamar, archivos, base):\n"
            "    salida = {}\n"
            "    for m in archivos:\n"
            "        try:\n"
            "            llamar({**base, m: '1' * 64}); salida[m] = 'sin error'\n"
            "        except ValueError as e:\n"
            "            salida[m] = 'antes' if ('antes de cargar' in str(e) or 'antes de importar' in str(e)) else str(e)\n"
            "        except Exception as e:\n"
            "            salida[m] = type(e).__name__\n"
            "    return salida\n"
            "pixel = probar(lambda h: fijados.cargar_elegir_pixel(ap, aph, h), fijados.ARCHIVOS_CLAUSURA,\n"
            "               dict(fijados.HUELLAS_CLAUSURA))\n"
            "validador = probar(lambda h: fijados.cargar_validador_reloj(ap, h), fijados.ARCHIVOS_RELOJ,\n"
            "                   dict(fijados.HUELLAS_RELOJ))\n"
            "print(json.dumps({'pixel': pixel, 'validador': validador,\n"
            "                  'cargados': sorted(m for m in sys.modules if m.startswith('reloj_dmc')),\n"
            "                  'por_ruta': 'reloj_dmc.extraccion' in rf._CARGADOS}))\n")
        r = json.loads(_subproceso(codigo))
        self.assertEqual(r["pixel"], {m: "antes" for m in fijados.ARCHIVOS_CLAUSURA})
        self.assertEqual(r["validador"], {m: "antes" for m in fijados.ARCHIVOS_RELOJ})
        self.assertEqual(r["cargados"], ["reloj_dmc", "reloj_dmc.entorno", "reloj_dmc.fijados"])
        self.assertFalse(r["por_ruta"])

    def test_carga_en_un_interprete_nuevo(self):
        """En un intérprete nuevo, sin nada del reloj cargado salvo lo de siempre: la carga es estricta (sin
        permitir_cargados), ejecuta extraccion.py por ruta y huella, no deja nada prohibido y sólo abre, fuera del
        intérprete, los diez archivos de código de la clausura ampliada y el texto y el JSON de C0 (gancho de auditoría
        de Python): ninguna salida del reloj ni datos DMC. numpy y pandas se importan antes del gancho (al importarse,
        dateutil lee la base de zonas del sistema, que no es del reloj). Límite (CEG-5 de ceguera): el gancho no ve las
        lecturas de las bibliotecas en C (pyarrow, netCDF4); la carga no lee archivos con ellas. El reloj sigue sin
        __pycache__. Después, el validador carga sin permitir_cargados (FIJ-2 extendida en FIJ-11)."""
        self.exigir(APH / fijados.RUTA_RELOJ_C0, APH / fijados.RUTA_JSON_RELOJ_C0)
        codigo = (
            "import json, os, sys; sys.path.insert(0, sys.argv[1])\n"
            "from pathlib import Path\n"
            "from meteo_combinada import entorno, fijados\n"
            "import numpy, pandas\n"
            "from reloj_dmc import fijados as rf\n"
            "rutas = entorno.rutas_reales(); ap, aph = Path(rutas.ap).resolve(), Path(rutas.aph).resolve()\n"
            "antes = sorted(m for m in sys.modules if m.startswith('reloj_dmc'))\n"
            "eventos, activo = [], [True]\n"
            "def gancho(evento, args):\n"
            "    if activo[0] and evento in ('open', 'os.listdir', 'os.scandir') and args \\\n"
            "            and isinstance(args[0], (str, bytes, os.PathLike)):\n"
            "        eventos.append((evento, os.fsdecode(args[0])))\n"
            "sys.addaudithook(gancho)\n"
            "p = fijados.cargar_elegir_pixel(ap, aph, fijados.HUELLAS_CLAUSURA)\n"
            "activo[0] = False\n"
            "otra = fijados.cargar_elegir_pixel(ap, aph, fijados.HUELLAS_CLAUSURA) is p\n"
            "prohibidos = [m for m in (*fijados.MODULOS_PROHIBIDOS, *fijados.NUNCA_CARGADOS) if m in sys.modules]\n"
            "solo_pixel = sorted(m for m in sys.modules if m.startswith('reloj_dmc'))\n"
            "v = fijados.cargar_validador_reloj(ap, dict(fijados.HUELLAS_RELOJ))\n"
            "prefijos = tuple({str(Path(x).resolve()) for x in (sys.prefix, sys.base_prefix, sys.exec_prefix)})\n"
            "def alias(t):\n"
            "    q = Path(t).resolve()\n"
            "    if str(q).startswith(prefijos): return None\n"
            "    if q.is_relative_to(ap): return 'AP/' + q.relative_to(ap).as_posix()\n"
            "    if q.is_relative_to(aph): return 'APH/' + q.relative_to(aph).as_posix()\n"
            "    return 'otro/' + q.name\n"
            "abiertos, intentos, listados = set(), set(), set()\n"
            "for e, t in eventos:\n"
            "    a = alias(t)\n"
            "    if a is None: continue\n"
            "    if e != 'open': listados.add(a)\n"
            "    elif '__pycache__' in Path(t).parts and not Path(t).exists(): intentos.add(a)\n"
            "    else: abiertos.add(a)\n"
            "print(json.dumps({'antes': antes, 'solo_pixel': solo_pixel, 'otra': otra, 'validador': callable(v),\n"
            "                  'prohibidos': prohibidos, 'por_ruta': 'reloj_dmc.extraccion' in rf._CARGADOS,\n"
            "                  'elegir': p.elegir_pixel.__module__, 'radio': p.radio_km,\n"
            "                  'abiertos': sorted(abiertos), 'intentos': sorted(intentos), 'listados': sorted(listados),\n"
            "                  'pycache': (ap / fijados.RUTA_RELOJ / '__pycache__').exists()}))\n")
        r = json.loads(_subproceso(codigo))
        reloj = fijados.RUTA_RELOJ
        self.assertEqual(r["antes"], ["reloj_dmc", "reloj_dmc.entorno", "reloj_dmc.fijados"])
        self.assertEqual(r["solo_pixel"], sorted(["reloj_dmc", *(f"reloj_dmc.{m}" for m in fijados.ARCHIVOS_PIXEL[1:])]))
        self.assertEqual({k: r[k] for k in ("otra", "validador", "prohibidos", "por_ruta", "elegir", "radio", "pycache")},
                         {"otra": True, "validador": True, "prohibidos": [], "por_ruta": True,
                          "elegir": "reloj_dmc.extraccion", "radio": 15, "pycache": False})
        self.assertEqual(r["abiertos"], sorted([*(f"AP/{reloj}/{m}.py" for m in fijados.ARCHIVOS_CLAUSURA),
                                                f"APH/{fijados.RUTA_RELOJ_C0}", f"APH/{fijados.RUTA_JSON_RELOJ_C0}"]))
        self.assertTrue(all(a.startswith(f"AP/{reloj}/__pycache__/") for a in r["intentos"]), r["intentos"])
        self.assertTrue(all(a.startswith(f"AP/{reloj}") for a in r["listados"]), r["listados"])

    def test_permitir_cargados_no_vuelve_propio_lo_ajeno(self):
        """H2, en intérpretes nuevos, con reloj_dmc.tipos importado antes por otro camino: tras cargar el píxel con
        permitir_cargados, el validador estricto y el píxel estricto siguen fallando; y tras cargar el validador con
        permitir_cargados, también. tipos nunca queda anotado como propio; lo que cargó la llamada, sí."""
        self.exigir(APH / fijados.RUTA_RELOJ_C0, APH / fijados.RUTA_JSON_RELOJ_C0)
        comun = ("import json, sys; sys.path.insert(0, sys.argv[1])\n"
                 "import reloj_dmc.tipos\n"
                 "from meteo_combinada import entorno, fijados\n"
                 "rutas = entorno.rutas_reales(); ap, aph = rutas.ap, rutas.aph\n"
                 "def falla(llamar):\n"
                 "    try:\n"
                 "        llamar(); return False\n"
                 "    except RuntimeError as e:\n"
                 "        return 'reloj_dmc.tipos' in str(e)\n"
                 "pix = lambda **k: fijados.cargar_elegir_pixel(ap, aph, fijados.HUELLAS_CLAUSURA, **k)\n"
                 "val = lambda **k: fijados.cargar_validador_reloj(ap, dict(fijados.HUELLAS_RELOJ), **k)\n")
        for primero, despues in (("pix", ("val", "pix")), ("val", ("pix", "val"))):
            with self.subTest(primero=primero):
                codigo = comun + (
                    f"{primero}(permitir_cargados=True)\n"
                    + "r = {" + ", ".join(f"{d!r}: falla({d})" for d in despues) + "}\n"
                    + "r['propios'] = sorted(n for n in fijados._PROPIOS)\n"
                    + "print(json.dumps(r))\n")
                r = json.loads(_subproceso(codigo))
                self.assertEqual({d: r[d] for d in despues}, {d: True for d in despues})
                self.assertNotIn("reloj_dmc.tipos", r["propios"])
                nuevos = fijados.CARGADOS_DESPUES_PIXEL if primero == "pix" else fijados.CARGADOS_DESPUES
                self.assertEqual(r["propios"], sorted(f"reloj_dmc.{m}" for m in nuevos if m != "tipos"))

    def test_carga_tras_el_validador_o_con_el_reloj_ya_cargado(self):
        """FIJ-2 extendida (FIJ-11), en intérpretes nuevos: tras el validador, el píxel carga sin permitir_cargados
        (tipos, constantes y tablas los cargó este módulo con las mismas huellas). Con reloj_dmc.extraccion importado
        antes por otro camino, falla salvo con permitir_cargados, y entonces entrega el de ese módulo; una llamada
        estricta posterior sigue fallando (H2)."""
        self.exigir(APH / fijados.RUTA_RELOJ_C0, APH / fijados.RUTA_JSON_RELOJ_C0)
        comun = ("import json, sys; sys.path.insert(0, sys.argv[1])\n"
                 "from meteo_combinada import entorno, fijados\n"
                 "from reloj_dmc import fijados as rf\n"
                 "rutas = entorno.rutas_reales(); ap, aph = rutas.ap, rutas.aph\n")
        codigo = comun + (
            "v = fijados.cargar_validador_reloj(ap, dict(fijados.HUELLAS_RELOJ))\n"
            "p = fijados.cargar_elegir_pixel(ap, aph, fijados.HUELLAS_CLAUSURA)\n"
            "print(json.dumps({'validador': callable(v), 'radio': p.radio_km,\n"
            "                  'por_ruta': 'reloj_dmc.extraccion' in rf._CARGADOS}))\n")
        self.assertEqual(json.loads(_subproceso(codigo)), {"validador": True, "radio": 15, "por_ruta": True})
        codigo = comun.replace("import json, sys; sys.path.insert(0, sys.argv[1])\n",
                               "import json, sys; sys.path.insert(0, sys.argv[1])\nimport reloj_dmc.extraccion\n") + (
            "try:\n"
            "    fijados.cargar_elegir_pixel(ap, aph, fijados.HUELLAS_CLAUSURA); falla = False\n"
            "except RuntimeError:\n"
            "    falla = True\n"
            "p = fijados.cargar_elegir_pixel(ap, aph, fijados.HUELLAS_CLAUSURA, permitir_cargados=True)\n"
            "try:\n"
            "    fijados.cargar_elegir_pixel(ap, aph, fijados.HUELLAS_CLAUSURA); sigue = False\n"
            "except RuntimeError:\n"
            "    sigue = True\n"
            "print(json.dumps({'falla': falla, 'mismo': p.elegir_pixel is reloj_dmc.extraccion.elegir_pixel,\n"
            "                  'por_ruta': 'reloj_dmc.extraccion' in rf._CARGADOS, 'sigue_fallando': sigue,\n"
            "                  'otra': fijados.cargar_elegir_pixel(ap, aph, fijados.HUELLAS_CLAUSURA,\n"
            "                                                      permitir_cargados=True) is p}))\n")
        self.assertEqual(json.loads(_subproceso(codigo)),
                         {"falla": True, "mismo": True, "por_ruta": False, "sigue_fallando": True, "otra": True})

    def test_enlazar_es_la_regla_de_enlazar_pixeles(self):
        """Pregunta (b) del revisor: PixelReloj.enlazar es la de extraccion.enlazar_pixeles para una estación. Sin
        coordenadas finitas dentro del rango de RELOJ §3.3, no hay píxel aunque haya uno válido debajo; si no, es elegir.
        El rango es tablas.coordenadas_en_rango del reloj, igual al de estaticas_nasadem (NAS-1) en los bordes."""
        from meteo_combinada import estaticas_nasadem
        pixel = self._pixel()
        E = pixel.EleccionPixel
        cat = _catalogo([(1, -35.0, -71.0), (2, -10.0, -71.0), (3, -35.0, -50.0), (4, -89.98, -71.0)])
        self.assertEqual(pixel.enlazar(-35.0, -71.0, cat, {1, 2, 3, 4}), pixel.elegir(-35.0, -71.0, cat, {1, 2, 3, 4}))
        self.assertEqual(pixel.enlazar(-35.0, -71.0, cat, {1}).pixel_id, 1)
        for lat, lon in ((-10.0, -71.0), (-35.0, -50.0), (None, -71.0), (-35.0, None), (math.nan, -71.0),
                         (-35.0, math.inf)):
            with self.subTest(lat=lat, lon=lon):
                self.assertEqual(pixel.enlazar(lat, lon, cat, {1, 2, 3, 4}), E(None, None, False))
        self.assertEqual(pixel.elegir(-10.0, -71.0, cat, {2}).pixel_id, 2)       # elegir solo no mira el rango
        bordes = [(la, lo) for la in (-90.0001, -90, -89.98, -35, -17, -16.9999)
                  for lo in (-110.0001, -110, -71, -55, -54.9999)]
        for lat, lon in bordes + [(None, None), (math.nan, math.nan)]:
            with self.subTest(borde=(lat, lon)):
                self.assertEqual(pixel.coordenadas_en_rango(lat, lon), estaticas_nasadem.coordenadas_en_rango(lat, lon))
        self.assertEqual(sum(pixel.coordenadas_en_rango(la, lo) for la, lo in bordes), 4 * 3)   # bordes cerrados

    def test_meses_de_validez_del_pixel(self):
        """Pregunta (c) del revisor: los meses de validez del píxel del reloj (PIXEL_MES_VALIDEZ_1 a 3 de los umbrales de
        C0, los que lee extraccion.pixeles_validos) son los de fondo_era5l: 200001, 201307 y 202507."""
        from meteo_combinada import constantes as constantes_m1
        from meteo_combinada import fondo_era5l
        pixel = self._pixel()
        extraccion = sys.modules[fijados.NOMBRE_EXTRACCION]
        del_reloj = tuple(int(pixel.umbrales.f(i)) for i in extraccion.IDS_MESES_VALIDEZ)
        self.assertEqual(del_reloj, (200001, 201307, 202507))
        self.assertEqual(del_reloj, tuple(int(m) for m in constantes_m1.valor("PIXEL_MESES_VALIDEZ")))
        self.assertEqual(del_reloj, fondo_era5l._MESES_VALIDEZ)

    def test_v1_2_conserva_el_anexo_b_por_su_generador(self):
        """Pregunta (a) del revisor, sin abrir el addendum de C1 ni el v1.2: el generador del v1.2 (APH 07881ed, por AST,
        sin correrlo) parte del v1.0.5 que fija M1 y exige que los Anexos A a B queden iguales y que el JSON del v1.2 sea
        el de C0 salvo «generado_desde» y «bateria» (lo único que comparar del reloj deja fuera). Del v1.2 y de su JSON,
        sólo la huella, en APH 1f59e6e."""
        ruta = APH / fijados.RUTA_GENERAR_V1_2
        self.exigir(ruta)
        fuente = ruta.read_bytes()
        self.assertEqual(hashlib.sha256(fuente).hexdigest(), fijados.SHA_GENERAR_V1_2)
        self.assertEqual(_huella_en_git(self, APH, fijados.COMMIT_ENMIENDA5_APH, fijados.RUTA_GENERAR_V1_2),
                         fijados.SHA_GENERAR_V1_2)
        for ruta_h, sha in ((fijados.RUTA_RELOJ_V1_2, fijados.SHA_RELOJ_V1_2),
                            (fijados.RUTA_JSON_RELOJ_V1_2, fijados.SHA_JSON_RELOJ_V1_2)):
            with self.subTest(ruta=ruta_h):
                self.assertEqual(_huella_en_git(self, APH, fijados.COMMIT_C1_RELOJ_APH, ruta_h), sha)
        arbol = ast.parse(fuente.decode("utf-8"))
        superiores = {n.targets[0].id: n.value for n in arbol.body
                      if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)}
        self.assertEqual(ast.literal_eval(superiores["SHA_ORIGEN"]), fijados.SHA_RELOJ_V1_0_5)
        self.assertEqual(ast.literal_eval(superiores["VERSION_ORIGEN"]), "v1.0.5")
        self.assertEqual(ast.unparse(superiores["ORIGEN"]), "AQUI / 'PROTOCOLO_RELOJ_DMC_v1.0.5.md'")
        self.assertEqual(ast.unparse(superiores["JSON_C0"]), "RELOJ / 'c0' / 'reloj_dmc_v1.json'")
        anexos = ast.literal_eval(superiores["ANEXOS_FIJOS"])
        self.assertEqual(anexos[anexos.index("## Anexo B.") + 1], "## Anexo C.")
        exigidos = {ast.unparse(n.args[0]) for n in ast.walk(arbol) if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Name) and n.func.id == "exigir" and n.args}
        for condicion in ("anexos(nuevo) == anexos(texto)", "umbrales.comparar(c0, publicado) == []",
                          "sha_archivo(JSON_C0) == umbrales.SHA_JSON_C0"):
            self.assertIn(condicion, exigidos)
        llamadas = {ast.unparse(n) for n in ast.walk(arbol) if isinstance(n, ast.Call)}
        self.assertIn("leer(ORIGEN, SHA_ORIGEN)", llamadas)              # el texto de partida, con su huella
        (json_de_umbrales,) = [n for n in arbol.body if isinstance(n, ast.FunctionDef) and n.name == "json_de_umbrales"]
        a_c0 = [ast.unparse(n) for n in ast.walk(json_de_umbrales) if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Subscript) and ast.unparse(t.value) == "c0" for t in n.targets)]
        self.assertEqual(a_c0, ["c0['generado_desde'] = publicado['generado_desde']"])
        otros_usos = [ast.unparse(n) for n in ast.walk(json_de_umbrales)
                      if isinstance(n, (ast.Attribute, ast.Delete, ast.AugAssign))
                      and "c0" in {x.id for x in ast.walk(n) if isinstance(x, ast.Name)}]
        self.assertEqual(otros_usos, [])                                  # nada más cambia c0 antes de comparar
        self._pixel()
        self.assertEqual(sys.modules["reloj_dmc.umbrales"].CLAVES_AJENAS_AL_ANEXO_B, ("bateria",))


class PruebasAST(_ConLimpieza):
    def test_macrozonas_sin_region_y_codigos(self):
        """FIJ-9 (B-H18, A-H6; D9): la región 0 es «sin_region», que tipos.macrozona_o_ninguna vuelve None; ninguna otra
        región da «sin_region»; MACROZONA_CODIGO (por AST) codifica todas las macrozonas de MACROZONA_REGION y además
        «insular»."""
        self.exigir(AP / fijados.RUTA_COMUN_MODELO)
        region = fijados.macrozona_region(AP)
        codigo = fijados.macrozona_codigo(AP)
        self.assertEqual(region[0], tipos.MACROZONA_SIN_REGION)
        self.assertIsNone(tipos.macrozona_o_ninguna(region[0]))
        self.assertIsNone(tipos.macrozona_o_ninguna(None))
        for numero, nombre in region.items():
            if numero != 0:
                with self.subTest(region=numero):
                    self.assertNotEqual(nombre, tipos.MACROZONA_SIN_REGION)
                    self.assertEqual(tipos.macrozona_o_ninguna(nombre), nombre)
        self.assertTrue(set(region.values()) <= set(codigo))
        self.assertEqual(set(codigo) - set(region.values()), {"insular"})
        self.assertEqual(codigo[tipos.MACROZONA_SIN_REGION], 5)
        self.assertEqual(len(set(codigo.values())), len(codigo))
        for nombre in fijados.MODULOS_PROHIBIDOS:
            self.assertNotIn(nombre, sys.modules)
        with tempfile.TemporaryDirectory() as tmp:      # una copia alterada se rechaza
            copia = Path(tmp) / fijados.RUTA_COMUN_MODELO
            copia.parent.mkdir(parents=True)
            copia.write_bytes((AP / fijados.RUTA_COMUN_MODELO).read_bytes() + b"\n")
            with self.assertRaises(ValueError):
                fijados.macrozona_codigo(Path(tmp))

    def test_macrozona_region(self):
        """MACROZONA_REGION de _comun_modelo, por AST, igual a la que lee el reloj."""
        self.exigir(AP / fijados.RUTA_COMUN_MODELO)
        tabla = fijados.macrozona_region(AP)
        self.assertEqual(tabla, fijados_reloj.macrozona_region(AP))
        self.assertEqual(tabla[13], "centro")
        self.assertEqual(set(tabla.values()), {"norte_grande", "norte_chico", "centro", "sur", "austral", "sin_region"})

    def test_esquema_meteo_civil_v3(self):
        """FIJ-6: versión, variables, Magnus 17,625/243,04 y tipos de tabla_meteo; es tipos.ESQUEMA_METEO_DIARIA. El
        módulo no se importa y no arrastra _rutas_v3, dlnm_v3 ni exposicion_horaria_v3."""
        self.exigir(APH / fijados.RUTA_METEO_CIVIL_V3)
        esquema = fijados.esquema_meteo_civil_v3(APH)
        self.assertEqual(esquema["version"], "meteo-diaria-v3/1")
        self.assertEqual(esquema["variables"], ("temp_media", "temp_min", "temp_max", "hr_media", "td_media",
                                                "precip_mm"))
        self.assertEqual(esquema["magnus"], (17.625, 243.04))
        self.assertEqual(esquema["columnas"], dict(tipos.ESQUEMA_METEO_DIARIA))
        self.assertEqual(esquema["version"], tipos.ESQUEMA_METEO_DIARIA.version)
        for nombre in ("meteo_civil_v3", "_rutas_v3", "_traza_v3", "dlnm_v3", "exposicion_horaria_v3"):
            self.assertNotIn(nombre, sys.modules)
        funciones = fijados.extraer_meteo_civil_v3(APH, ("humedad_relativa", "lluvia_horaria"))
        self.assertTrue(all(callable(f) for f in funciones.values()))

    def test_regla_el_features(self):
        """FIJ-7 (MC-28): los nueve el_* meteorológicos (los sufijos de tipos.SUFIJOS_EL), la lluvia aparte, Magnus
        6,112/17,67/243,5, t2m y d2m en K, y la dirección como arctan2(u, v)."""
        self.exigir(AP / fijados.RUTA_FEATURES)
        regla = fijados.regla_el_features(AP)
        self.assertEqual(sorted(regla["meteorologicas"]), sorted(f"el_{s}" for s in tipos.SUFIJOS_EL))
        self.assertEqual(len(regla["meteorologicas"]), 9)
        self.assertEqual(regla["lluvia"], ["el_tp_1h_mm"])
        self.assertEqual(regla["magnus"], (6.112, 17.67, 243.5))
        self.assertEqual(regla["kelvin"], 273.15)
        self.assertEqual(regla["direccion"], ("el_u10", "el_v10"))
        self.assertNotIn("_comun_modelo", sys.modules)

    def test_opciones_m0(self):
        """MC-35: OPCIONES_M0 de preparar_m0.py por AST es la clave «opciones_m0» del JSON de umbrales; D2 = 8."""
        self.exigir(APH / fijados.RUTA_PREPARAR_M0, _JSON_M0)
        opciones = fijados.opciones_m0(APH)
        publicado = json.loads(_JSON_M0.read_text(encoding="utf-8"))["opciones_m0"]
        self.assertEqual(opciones, publicado)
        self.assertEqual(list(opciones), list(publicado))
        self.assertIs(type(opciones["D2"]), int)

    def test_extracciones_exigen_la_huella(self):
        """Una copia alterada de _features.py, de preparar_m0.py o de meteo_civil_v3.py se rechaza."""
        casos = ((AP, fijados.RUTA_FEATURES, fijados.regla_el_features),
                 (APH, fijados.RUTA_PREPARAR_M0, fijados.opciones_m0),
                 (APH, fijados.RUTA_METEO_CIVIL_V3, fijados.esquema_meteo_civil_v3))
        for raiz, ruta, funcion in casos:
            self.exigir(raiz / ruta)
            with self.subTest(ruta=ruta), tempfile.TemporaryDirectory() as tmp:
                copia = Path(tmp) / ruta
                copia.parent.mkdir(parents=True)
                copia.write_bytes((raiz / ruta).read_bytes() + b"\n# alterado\n")
                with self.assertRaises(ValueError):
                    funcion(Path(tmp))
                copia.unlink()
                with self.assertRaises(FileNotFoundError):
                    funcion(Path(tmp))


if __name__ == "__main__":
    unittest.main()
