"""Pruebas de verificar_reloj_dmc.py (ejecutable, C2, cerrojo y sello).

Las que llevan «pNN» son el punto NN de §8 (grupos A, B y C). Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s reloj_dmc/tests -t .

A ciegas: ninguna prueba abre la DMC real, ERA5-Land real ni nada bajo /Volumes, y ninguna corre --aplicar
sobre las raíces reales. Las corridas de --aplicar usan una raíz falsa (``entorno.rutas_sinteticas``):
- DMC: una estación F(0) de 2019 fabricada con el formato real (``sintetico.fabricar_descarga``: run_download
  del descargador vigente, cliente y guarda falsos), con progreso.json y el candado que deja la descarga;
- ERA5L: los 321 mensuales 2000-01 … 2026-09 en NetCDF con la referencia sintética y su catálogo de píxeles;
- AP y APH: repositorios git falsos (git init en la carpeta temporal, con origin/main como referencia local),
  con una copia del código del paquete, el texto y el JSON de C0, el addendum de C1 y la línea de cierre de C2;
- LOCAL: la salida de C1 en …/v1/c1/ (pruebas, resumen, batería y sha256.json, en la lista cerrada; VER-4) y
  las copias de C2.
--sintetico se prueba sobre paquetes de pruebas falsos (nombre único, en una carpeta temporal) y con la batería
simulada sobre las funciones de escritura de bateria. Nunca se corre la batería; sobre la suite real, --sintetico
sólo corre con «--patron test_tipos.py» (p27), para que ninguna prueba se corra a sí misma.
El código fijado (adaptador, dmc_features, preflight_v3, _meteo_guard) se carga del AP real, por ruta y
huella, como en las pruebas de orquestacion. Si falta algo de eso, la prueba se omite con el motivo y no se
da por aprobada.
"""
import sys

sys.dont_write_bytecode = True

import ast  # noqa: E402
import contextlib  # noqa: E402
import errno  # noqa: E402
import fcntl  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
import types  # noqa: E402
import unittest  # noqa: E402
import zoneinfo  # noqa: E402
from dataclasses import replace  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from reloj_dmc import (entorno, extraccion, fijados, orquestacion, salidas, sintetico,  # noqa: E402
                       umbrales)
from reloj_dmc import verificar_reloj_dmc as V  # noqa: E402

S = sintetico
AP = _RAIZ.parent
APH = AP.parent / "Air-Pollution-Health-Chile"
PAQUETE = Path(V.__file__).resolve().parent
PYTHON = Path(os.path.expanduser(entorno.INTERPRETE))

CASO = S.caso_simple("901601", "F(0)", "a", anios=(2019, 2019))
RELOJ = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)          # reloj de pared inyectado (R-31)
FECHA_C1, FECHA_C2, FECHA_ERRATA = "20261024", "20261025", "20261031"
TEXTO_V11 = f"auditoria/{FECHA_C1}/reloj_dmc/PROTOCOLO_RELOJ_DMC_v1_propuesta.md"
CONFIG_AP = "config/meteorologia/reloj_dmc_v1.json"
ADDENDUM = f"auditoria/{FECHA_C1}/reloj_dmc/{V.ARCHIVO_ADDENDUM}"
CIERRE = f"auditoria/{FECHA_C2}/reloj_dmc/{V.ARCHIVO_CIERRE}"
PALABRAS_DE_VEREDICTO = ("confirmad", "discrepante", "insuficiente", "sin_confirmar", "inestable", "F(0)", "F(-",
                         "C(Santiago)", "C(America")
_LINEA_CONSOLA = re.compile(r"\[reloj_dmc\] [A-Za-z0-9][A-Za-z0-9_./-]*: \d+/\d+")
_ENTORNO_GIT = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "prueba",
                "GIT_AUTHOR_EMAIL": "prueba", "GIT_COMMITTER_NAME": "prueba", "GIT_COMMITTER_EMAIL": "prueba",
                "GIT_AUTHOR_DATE": "2026-10-24T12:00:00+00:00", "GIT_COMMITTER_DATE": "2026-10-24T12:00:00+00:00"}
_HILOS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
          "NUMEXPR_NUM_THREADS")

_ESTADO: dict = {}


def setUpModule():
    zoneinfo.reset_tzpath(to=[])
    zoneinfo.ZoneInfo.clear_cache()


def tearDownModule():
    for carpeta in _ESTADO.pop("temporales", []):
        carpeta.cleanup()


def _motivo_para_omitir() -> str | None:
    """Por qué omitir (falta el código fijado, los umbrales de C0, git o el intérprete fijado), o None."""
    for ruta in (APH / umbrales.PROTOCOLO_C0, APH / umbrales.JSON_C0, AP / fijados.RUTA_DESCARGADOR,
                 AP / fijados.RUTA_ADAPTADOR, AP / fijados.RUTA_DMC_FEATURES, AP / fijados.RUTA_PREFLIGHT_V3,
                 AP / V.RUTA_METEO_GUARD, AP / fijados.RUTA_COMUN_MODELO):
        if not ruta.is_file():
            return f"falta {ruta.name}; la prueba no se da por aprobada"
    if shutil.which("git") is None:
        return "falta git; la prueba no se da por aprobada"
    try:
        entorno.comprobar_interprete()
    except RuntimeError as e:
        return f"no corre con el intérprete fijado ({e}); la prueba no se da por aprobada"
    sha = entorno.sha256_archivo(AP / fijados.RUTA_DESCARGADOR)
    if sha not in fijados.VERSIONES_ADMITIDAS_C0:
        return f"el descargador en AP ({sha[:8]}…) no es una versión admitida en C0"
    if V._comprobar_codigo_fijado(AP):
        return "el código fijado de AP no tiene las huellas de C0"
    return None


def _exigir_codigo_fijado(caso=None) -> None:
    motivo = _motivo_para_omitir()
    if motivo is not None:
        raise unittest.SkipTest(motivo)


def _temporal() -> Path:
    carpeta = tempfile.TemporaryDirectory()
    _ESTADO.setdefault("temporales", []).append(carpeta)
    return Path(carpeta.name).resolve()


def _exigir_interprete() -> None:
    """--sintetico corre sólo con el intérprete fijado (VER-15): si no, la prueba se omite y no se da por aprobada."""
    try:
        entorno.comprobar_interprete()
    except RuntimeError as e:
        raise unittest.SkipTest(f"no corre con el intérprete fijado ({e}); la prueba no se da por aprobada")


def _cfg_sintetico(rutas: entorno.Rutas, **cambios) -> V.Configuracion:
    """Configuración de --sintetico con raíces falsas (sólo usa el paquete, las rutas, el reloj y las vigiladas)."""
    base = dict(rutas=rutas, ap_codigo=AP, paquete=PAQUETE, catalogo_pixeles=rutas.era5l / "x",
                sha_catalogo_pixeles="0" * 64, lista_v=rutas.aph / "v", lista_v2=rutas.aph / "v2",
                copias_c2=rutas.local / "c2", nice=0, reloj=lambda: RELOJ)
    base.update(cambios)
    return V.Configuracion(**base)


@contextlib.contextmanager
def _paquete_falso(pruebas: dict):
    """Un paquete con tests/ falsos (nombre único) en una carpeta temporal, para correr --sintetico sobre él.
    Al salir, quita su carpeta de sys.path y sus módulos de sys.modules (unittest discover los deja)."""
    _ESTADO["paquetes_falsos"] = _ESTADO.get("paquetes_falsos", 0) + 1
    nombre = f"reloj_falso_{os.getpid()}_{_ESTADO['paquetes_falsos']}"
    antes = list(sys.path)
    with tempfile.TemporaryDirectory() as tmp:
        paquete = Path(tmp).resolve() / nombre
        (paquete / "tests").mkdir(parents=True)
        for rel in ("__init__.py", "tests/__init__.py"):
            (paquete / rel).write_text("", encoding="utf-8")
        for archivo, codigo in pruebas.items():
            (paquete / "tests" / archivo).write_text(codigo, encoding="utf-8")
        try:
            yield paquete
        finally:
            sys.path[:] = antes
            for m in [m for m in sys.modules if m == nombre or m.startswith(nombre + ".")]:
                del sys.modules[m]


# Pruebas de los paquetes falsos de --sintetico (VER-14 y VER-15).
PRUEBA_PASA = '''import unittest


class PruebaFalsa(unittest.TestCase):
    def test_pasa(self):
        self.assertEqual("a" * 2, "aa")
'''
PRUEBA_NEGADA_DENTRO = '''import os
import unittest

from reloj_dmc import verificar_reloj_dmc as V

PROHIBIDA = "/Volumes/reloj_dmc_prueba_inexistente"


class PruebaFalsa(unittest.TestCase):
    def test_un_registro_propio_niega_bajo_volumes(self):
        antes = (os.stat, os.lstat)
        with V.RegistroAccesos((PROHIBIDA,), bloquear=True) as r:
            with self.assertRaises(PermissionError):
                os.lstat(PROHIBIDA + "/x")
            with self.assertRaises(PermissionError):
                open(PROHIBIDA + "/y.json", "rb")
        self.assertEqual([e for e, _ in r.accesos], ["os.lstat", "open"])
        self.assertEqual((os.stat, os.lstat), antes)
'''
PRUEBA_SIN_GUARDA = '''import os
import unittest

PROHIBIDA = {prohibida!r}


class PruebaFalsa(unittest.TestCase):
    def test_sin_registro_propio(self):
        with self.assertRaises(PermissionError):          # el registro de --sintetico falla cerrado
            os.lstat(os.path.join(PROHIBIDA, "x"))
'''
PRUEBA_ESPERADA_Y_OMITIDA = '''import unittest


class PruebaFalsa(unittest.TestCase):
    @unittest.expectedFailure
    def test_falla_esperada(self):
        self.assertEqual("a", "b")

    @unittest.skip("falta un archivo: la prueba no se da por aprobada")
    def test_omitida(self):
        pass

    def test_pasa(self):
        pass
'''


# ---------------------------------------------------------------------------------------------
# Repositorios git falsos
# ---------------------------------------------------------------------------------------------
def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True,
                       env={**os.environ, **_ENTORNO_GIT})
    return r.stdout.decode("utf-8").strip()


def _confirmar(repo: Path, mensaje: str, *, subir: bool = True) -> str:
    """git add -A + commit en el repositorio falso; con ``subir``, origin/main queda en el commit nuevo."""
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--allow-empty", "-m", mensaje)
    commit = _git(repo, "rev-parse", "HEAD")
    if subir:
        _git(repo, "update-ref", "refs/remotes/origin/main", commit)
    return commit


def _iniciar_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", "main")


def _escribir(ruta: Path, datos: bytes | str) -> str:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(datos.encode("utf-8") if isinstance(datos, str) else datos)
    return entorno.sha256_archivo(ruta)


def _json(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8")


# ---------------------------------------------------------------------------------------------
# Raíz falsa de --aplicar
# ---------------------------------------------------------------------------------------------
def _escribir_era5(raiz_era5l: Path, catalogo: pd.DataFrame, serie) -> None:
    """Los 321 mensuales en el formato que lee extraccion (t2m en K, sp en Pa); los píxeles no válidos, NaN."""
    netCDF4 = extraccion._netcdf4()
    ids = catalogo["pixel_id"].to_numpy(dtype=np.int64)
    validos = catalogo["valido"].to_numpy(dtype=bool)
    for m in extraccion.MESES_ERA5:
        inicio, fin = extraccion._limites_mes(m)
        t = np.arange(inicio, fin + np.timedelta64(1, "h"), dtype="datetime64[h]")
        ruta = extraccion.ruta_mes_era5(raiz_era5l, m)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ds = netCDF4.Dataset(ruta, "w", format="NETCDF4")
        try:
            ds.createDimension("time", len(t))
            ds.createDimension("pixel", len(ids))
            tv = ds.createVariable("time", "i8", ("time",))
            tv.units = "seconds since 1970-01-01 00:00:00 UTC"
            tv.calendar = "proleptic_gregorian"
            tv[:] = (t.astype("datetime64[s]") - np.datetime64("1970-01-01T00:00:00", "s")).astype(np.int64)
            ds.createVariable("pixel_id", "i8", ("pixel",))[:] = ids
            for nombre in ("t2m", "sp", "u10", "v10"):
                a = np.full((len(t), len(ids)), np.nan, dtype=np.float32)
                for j, p in enumerate(ids):
                    if validos[j]:
                        x = serie.valores(int(p), nombre, t)
                        a[:, j] = x + extraccion.KELVIN_A_CELSIUS if nombre == "t2m" else (
                            x * extraccion.PA_POR_HPA if nombre == "sp" else x)
                v = ds.createVariable(nombre, "f4", ("time", "pixel"), zlib=True, fill_value=np.float32(np.nan))
                v[:] = a
        finally:
            ds.close()


def _construir_raiz(raiz: Path) -> dict:
    """Raíz falsa completa de --aplicar (ver el encabezado). Devuelve sus rutas y archivos."""
    raiz = Path(raiz).resolve()
    rutas = entorno.rutas_sinteticas(raiz)
    descargador = fijados.cargar_descargador(AP, entorno.sha256_archivo(AP / fijados.RUTA_DESCARGADOR))
    # Tres meses bastan para confirmar F(0) y dejan corta la comprobación 7 de §7.3 (cargar_dmc por mes).
    dmc = S.fabricar_descarga([CASO], raiz, descargador, "2019-01-01", "2019-03-31")
    assert Path(dmc).resolve() == rutas.dmc.resolve()
    catalogo = S.catalogo_pixeles_sintetico([CASO])
    ruta_catalogo = rutas.era5l / V.NOMBRE_CATALOGO_PIXELES
    catalogo.to_parquet(ruta_catalogo, index=False)
    _escribir_era5(rutas.era5l, catalogo, S.serie_era5_de_casos([CASO]))
    # Copias de C2 en LOCAL (VER-10): progreso.json y una bitácora.
    copias = rutas.local / V.SUBRUTA_COPIAS_C2
    sha_progreso = _escribir(copias / V.PROGRESO_DMC, (rutas.dmc / V.PROGRESO_DMC).read_bytes())
    _escribir(copias / "stdout_20261020.log", "INFO descarga cerrada sin duplicados\n")
    # AP falso: copia del código del paquete y la configuración de C0.
    _iniciar_repo(rutas.ap)
    lista = {}
    for nombre, ruta in V._codigo_del_paquete(PAQUETE).items():
        lista[f"AP/{V.RUTA_PAQUETE_AP}/{nombre}"] = _escribir(rutas.ap / V.RUTA_PAQUETE_AP / nombre, ruta.read_bytes())
    lista[f"AP/{CONFIG_AP}"] = _escribir(rutas.ap / CONFIG_AP, (APH / umbrales.JSON_C0).read_bytes())
    _confirmar(rutas.ap, "código de C1")
    # Salida de C1 en LOCAL/…/v1/c1 (VER-4): pruebas, resumen, batería y su sha256.json.
    c1 = rutas.corridas / V.CARPETA_C1
    huellas_c1 = {n: _escribir(c1 / n, f"{n}: salida de C1 (prueba sintética)\n") for n in V.ARCHIVOS_C1}
    _escribir(c1 / V.ARCHIVO_HUELLAS, entorno.json_canonico(dict(sorted(huellas_c1.items()))))
    salida_bateria = {}
    for n in (*V.ARCHIVOS_C1, V.ARCHIVO_HUELLAS):
        alias = entorno.alias(c1 / n, rutas)
        lista[alias] = entorno.sha256_archivo(c1 / n)
        if n in V.ARCHIVOS_BATERIA:
            salida_bateria[alias] = lista[alias]
    # APH falso: texto «v1.1» (el de C0), listas V y V2, addendum de C1 y línea de cierre de C2.
    _iniciar_repo(rutas.aph)
    lista[f"APH/{TEXTO_V11}"] = _escribir(rutas.aph / TEXTO_V11, (APH / umbrales.PROTOCOLO_C0).read_bytes())
    lista[f"APH/{V.RUTA_LISTA_V}"] = _escribir(rutas.aph / V.RUTA_LISTA_V, "codigo\n")
    lista[f"APH/{V.RUTA_LISTA_V2}"] = _escribir(rutas.aph / V.RUTA_LISTA_V2, "codigo\n901699\n")
    for rel in (umbrales.PROTOCOLO_C0, umbrales.JSON_C0):            # C0, para C3 sin addendum (VER-13)
        _escribir(rutas.aph / rel, (APH / rel).read_bytes())
    commit_c1 = _confirmar(rutas.aph, "C1: código y texto v1.1")
    addendum = {"schema": V.ESQUEMA_ADDENDUM, "fecha": "2026-10-24", "commit_c1": commit_c1,
                "lista_cerrada": dict(sorted(lista.items())),
                "texto_v1_1": {"ruta": f"APH/{TEXTO_V11}", "sha256": lista[f"APH/{TEXTO_V11}"]},
                "configuracion": {"ruta": f"AP/{CONFIG_AP}", "sha256": lista[f"AP/{CONFIG_AP}"]},
                "salida_bateria": salida_bateria, "versiones_admitidas": list(fijados.VERSIONES_ADMITIDAS_C0),
                "lecturas": ["VER-1 a VER-15 (prueba)"]}
    _escribir(rutas.aph / ADDENDUM, _json(addendum))
    commit_addendum = _confirmar(rutas.aph, "C1: addendum")
    cierre = {"schema": V.ESQUEMA_CIERRE, "fecha": "2026-10-25", "progreso_sha256": sha_progreso,
              "frase_autor": "Cierro la descarga DMC (prueba sintética).", "commit": commit_addendum}
    _escribir(rutas.aph / CIERRE, _json(cierre))
    _confirmar(rutas.aph, "C2: línea de cierre")
    return {"raiz": raiz}


def _info_raiz(raiz: Path) -> dict:
    """Configuración y archivos de una raíz ya construida (o copiada)."""
    raiz = Path(raiz).resolve()
    rutas = entorno.Rutas(ap=raiz / "AP", aph=raiz / "APH", local=raiz / "LOCAL", dmc=raiz / "DMC",
                          era5l=raiz / "ERA5L")
    ruta_catalogo = rutas.era5l / V.NOMBRE_CATALOGO_PIXELES
    cfg = V.Configuracion(rutas=rutas, ap_codigo=AP, paquete=rutas.ap / V.RUTA_PAQUETE_AP,
                          catalogo_pixeles=ruta_catalogo, sha_catalogo_pixeles=entorno.sha256_archivo(ruta_catalogo),
                          lista_v=rutas.aph / V.RUTA_LISTA_V, lista_v2=rutas.aph / V.RUTA_LISTA_V2,
                          copias_c2=rutas.local / V.SUBRUTA_COPIAS_C2, reloj=lambda: RELOJ, procesos=lambda: "",
                          nice=0)
    return {"raiz": raiz, "rutas": rutas, "cfg": cfg, "addendum": rutas.aph / ADDENDUM, "cierre": rutas.aph / CIERRE}


def _raiz(nombre: str) -> dict:
    """Una copia nueva de la raíz base (se construye una sola vez por módulo)."""
    if "base" not in _ESTADO:
        base = _temporal() / "base"
        _construir_raiz(base)
        _ESTADO["base"] = base
    destino = _temporal() / nombre
    shutil.copytree(_ESTADO["base"], destino, symlinks=True)
    return _info_raiz(destino)


@contextlib.contextmanager
def _hilos_restituidos():
    """preflight_v3 (runner_v3) fija los hilos de OMP, BLAS y pyarrow: se restituyen al salir."""
    import pyarrow as pa
    antes = {v: os.environ.get(v) for v in _HILOS}
    cpu, io_ = pa.cpu_count(), pa.io_thread_count()
    try:
        yield
    finally:
        for v, valor in antes.items():
            if valor is None:
                os.environ.pop(v, None)
            else:
                os.environ[v] = valor
        pa.set_cpu_count(cpu)
        pa.set_io_thread_count(io_)


def _argumentos(info: dict, *extra: str) -> object:
    args = V.analizar_argumentos(["--aplicar", "--addendum", str(info["addendum"]), "--linea-cierre",
                                  str(info["cierre"]), *extra])
    args.configuracion = info["cfg"]
    return args


def _aplicar(info: dict, *extra: str, registro=None) -> dict:
    """modo_aplicar sobre una raíz falsa; devuelve código de salida, consola y tiempo."""
    out, err = io.StringIO(), io.StringIO()
    t = time.perf_counter()
    with _hilos_restituidos(), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        if registro is None:
            codigo = V.modo_aplicar(_argumentos(info, *extra))
        else:
            with registro:
                codigo = V.modo_aplicar(_argumentos(info, *extra))
    return {"codigo": codigo, "stdout": out.getvalue(), "stderr": err.getvalue(), "segundos": time.perf_counter() - t}


def _cerrojo(info: dict) -> list[dict]:
    return V.Cerrojo(info["rutas"].corridas / V.CERROJO).lineas


def _carpeta(info: dict, sufijo: str = "") -> Path:
    return info["rutas"].corridas / (V.ETIQUETA_CORRIDA.format(fecha="20261030") + sufijo)


def _flock_libre(ruta: Path) -> bool:
    """¿Otro descriptor puede tomar el candado? (flock de BSD: dos descriptores distintos se excluyen)."""
    fd = os.open(ruta, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as e:
        if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EACCES):
            return False
        raise
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return True
    finally:
        os.close(fd)


def _crear_errata(info: dict, n: int) -> Path:
    """Errata confirmada y sellada (VER-7): prueba, sello y errata_<n>.json en APH, confirmados y en origin/main."""
    rutas = info["rutas"]
    prueba = f"auditoria/{FECHA_ERRATA}/reloj_dmc/prueba_errata_{n}.py"
    sello = f"auditoria/{FECHA_ERRATA}/reloj_dmc/errata_{n}.json.ots"
    sha_prueba = _escribir(rutas.aph / prueba, "def test_falla_contra_el_texto():\n    assert False\n")
    sha_sello = _escribir(rutas.aph / sello, b"sello OpenTimestamps (prueba)")
    errata = rutas.aph / f"auditoria/{FECHA_ERRATA}/reloj_dmc/errata_{n}.json"
    _escribir(errata, _json({"schema": V.ESQUEMA_ERRATA, "n": n, "fecha": "2026-10-31",
                             "prueba": {"ruta": f"APH/{prueba}", "sha256": sha_prueba},
                             "sello": {"ruta": f"APH/{sello}", "sha256": sha_sello}}))
    _confirmar(rutas.aph, f"errata {n} confirmada y sellada")
    return errata


@contextlib.contextmanager
def _candado_tomado(ruta: Path):
    """Otro descriptor retiene ``ruta`` con flock exclusivo (como otro --aplicar en curso)."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(ruta, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


# =============================================================================================
# Corridas de --aplicar sobre raíces falsas (C.26, C.27, C.28, cerrojo, consola, sello, reanudación)
# =============================================================================================
class PruebasCorridaFalsa(unittest.TestCase):
    """Todas las corridas se hacen una vez en setUpClass y cada prueba mira un aspecto."""

    @classmethod
    def setUpClass(cls):
        _exigir_codigo_fijado(cls)
        cls.A, cls.B, cls.C, cls.D = _raiz("A"), _raiz("B"), _raiz("C"), _raiz("D")
        candado = cls.A["rutas"].dmc / V.CANDADO_DMC
        cls.candado_en = {}
        extraer_real, verificador_real = extraccion.extraer_dmc, orquestacion.verificador_7_3

        def extraer_espia(*a, **k):
            cls.candado_en["extraccion"] = _flock_libre(candado)
            return extraer_real(*a, **k)

        def verificador_espia(*a, **k):
            verificar = verificador_real(*a, **k)

            def envoltorio(ruta):
                salida = verificar(ruta)
                cls.candado_en["7_3"] = _flock_libre(candado)
                return salida
            return envoltorio

        # 1. Corrida A, con el registro de accesos (prueba 27 con raíz falsa) y espías del candado.
        cls.registro_A = V.RegistroAccesos((V.VOLUMES, cls.A["rutas"].dmc))
        with mock.patch.object(V.extraccion, "extraer_dmc", extraer_espia), \
                mock.patch.object(V.orquestacion, "verificador_7_3", verificador_espia):
            cls.A1 = _aplicar(cls.A, registro=cls.registro_A)
        cls.candado_despues = _flock_libre(candado)
        cls.lineas_A1 = list(_cerrojo(cls.A))
        cls.recibo_A1 = json.loads((_carpeta(cls.A) / salidas.RECIBO).read_bytes()) if cls.A1["codigo"] == 0 else None
        # 2. Corrida B: la misma entrada en otra raíz, con espías del orden de §5.2 («Ola 4a cerrada»), y otro
        #    --aplicar sobre la misma raíz mientras corre la fase 4 (VER-16).
        cls.orden_B = []
        evaluar_real, escribir_real = orquestacion.evaluar_red, salidas.escribir_corrida

        def evaluar_espia(*a, **k):
            cls.orden_B.append(("evaluar_red",))
            cls.intruso_B = _aplicar(cls.B)
            return evaluar_real(*a, **k)

        def escribir_espia(resultado, carpeta, **k):
            cls.orden_B.append(("escribir_corrida", k["verificar"] is not None, k["modo_sintetico"],
                                k["errata_post_c4"], k["meses"] is not None, sorted(resultado.controles),
                                sorted(k["huellas_entrada"])))
            return escribir_real(resultado, carpeta, **k)

        with mock.patch.object(V.orquestacion, "evaluar_red", evaluar_espia), \
                mock.patch.object(V.salidas, "escribir_corrida", escribir_espia):
            cls.B1 = _aplicar(cls.B)
        # 3. Segundo --aplicar en A, sin errata: rechazado y registrado.
        cls.A2 = _aplicar(cls.A)
        # 4. Errata confirmada y sellada en A: corrida _ERRATA1.
        cls.errata = _crear_errata(cls.A, 1)
        cls.A3 = _aplicar(cls.A, "--errata", str(cls.errata))
        cls.A4 = _aplicar(cls.A, "--errata", str(cls.errata))          # la misma errata no sirve dos veces
        # 5. Corrida C abortada en la fase 4 y retomada con --reanudar.
        with mock.patch.object(V.orquestacion, "evaluar_red", side_effect=RuntimeError("F(0) confirmado (falso)")):
            cls.C1 = _aplicar(cls.C)
        cls.C2 = _aplicar(cls.C)                                        # sin --reanudar: rechazado
        lecturas = {"estaciones": 0, "meses_era5": 0}
        extraer_estacion, volcar_mes = extraccion._extraer_estacion, extraccion._volcar_mes

        def estacion_espia(*a, **k):
            lecturas["estaciones"] += 1
            return extraer_estacion(*a, **k)

        def volcar_espia(*a, **k):
            lecturas["meses_era5"] += 1
            return volcar_mes(*a, **k)

        def evaluar_con_lineas_sin_cv(*a, **k):          # como si E6 estuviera activa (ORQ-3f, SAL-22)
            resultado = evaluar_real(*a, **k)
            resultado.controles["reglas_vencidas"]["lineas_sin_cv"] = ["E6"]
            return resultado

        with mock.patch.object(V.extraccion, "_extraer_estacion", estacion_espia), \
                mock.patch.object(V.extraccion, "_volcar_mes", volcar_espia), \
                mock.patch.object(V.orquestacion, "evaluar_red", evaluar_con_lineas_sin_cv):
            cls.C3 = _aplicar(cls.C, "--reanudar")
        cls.lecturas_C3 = dict(lecturas)
        cls.C4 = _aplicar(cls.C, "--reanudar")                          # ya sellada: no hay qué reanudar
        # 6. Corrida D: aborta en la fase 4 con un mensaje que trae un veredicto mientras llega otro --aplicar
        #    (VER-11, VER-16); después, una errata sellada la reemplaza con _ERRATA1 (VER-7).
        def evaluar_aborta(*a, **k):
            cls.intruso_D = _aplicar(cls.D)
            raise RuntimeError("estación 901601: F(0) confirmado (mensaje con veredicto)")

        with mock.patch.object(V.orquestacion, "evaluar_red", evaluar_aborta):
            cls.D1 = _aplicar(cls.D)
        cls.errata_D = _crear_errata(cls.D, 1)
        cls.D2 = _aplicar(cls.D, "--errata", str(cls.errata_D))
        cls.D3 = _aplicar(cls.D, "--reanudar")                          # la pendiente ya fue reemplazada

    # --- C.26 ---------------------------------------------------------------------------------
    def test_p26_dos_corridas_iguales_dan_huellas_identicas(self):
        """Con reloj de pared inyectado (R-31): el mismo recibo, archivo por archivo, en dos raíces."""
        self.assertEqual((self.A1["codigo"], self.B1["codigo"]), (V.SALIDA_OK, V.SALIDA_OK),
                         self.A1["stderr"] + self.B1["stderr"])
        recibo_B = json.loads((_carpeta(self.B) / salidas.RECIBO).read_bytes())
        self.assertEqual(self.recibo_A1["archivos"], recibo_B["archivos"])
        self.assertEqual(self.recibo_A1["total_sha256"], recibo_B["total_sha256"])
        for nombre in (salidas.ARCHIVO_POLITICA, salidas.ARCHIVO_INFORME, salidas.ARCHIVO_ARTEFACTOS):
            self.assertIn(nombre, recibo_B["archivos"])
        # Lo que cambia entre corridas (fechas del cerrojo) queda fuera de la carpeta.
        self.assertFalse(any(n.startswith(V.CERROJO) for n in recibo_B["archivos"]))
        fin = [ln for ln in _cerrojo(self.B) if ln["evento"] == "fin"][-1]
        self.assertEqual((fin["resultado"], fin["total_sha256"]), ("sellada", recibo_B["total_sha256"]))

    def test_p26_segundo_aplicar_rechazado_y_registrado(self):
        """Sin errata: rechazado (sin tocar la carpeta sellada) y registrado en el cerrojo."""
        self.assertEqual(self.A2["codigo"], V.SALIDA_RECHAZO)
        self.assertIn("ya registra una corrida confirmatoria", self.A2["stderr"])
        lineas = _cerrojo(self.A)
        n = len(self.lineas_A1)
        self.assertEqual([ln["evento"] for ln in lineas[n:n + 2]], ["intento", "rechazo"])
        self.assertTrue(any("ya registra una corrida confirmatoria" in m for m in lineas[n + 1]["motivos"]))
        self.assertEqual(json.loads((_carpeta(self.A) / salidas.RECIBO).read_bytes()), self.recibo_A1)
        # La misma errata no habilita una segunda corrida.
        self.assertEqual(self.A4["codigo"], V.SALIDA_RECHAZO)
        self.assertIn("ya se usó", self.A4["stderr"])

    def test_c4_errata_confirmada_habilita_una_corrida_errata(self):
        """§10: con una errata confirmada y sellada, la carpeta lleva _ERRATA1 y la política errata_post_c4."""
        self.assertEqual(self.A3["codigo"], V.SALIDA_OK, self.A3["stderr"])
        carpeta = _carpeta(self.A, "_ERRATA1")
        self.assertEqual(salidas.verificar_sello(carpeta), [])
        pol = json.loads((carpeta / salidas.ARCHIVO_POLITICA).read_bytes())
        self.assertTrue(pol["errata_post_c4"])
        self.assertFalse(json.loads((_carpeta(self.A) / salidas.ARCHIVO_POLITICA).read_bytes())["errata_post_c4"])
        lineas = _cerrojo(self.A)
        errata = [ln for ln in lineas if ln["evento"] == "errata"]
        self.assertEqual([(ln["n"], ln["documento"]["ruta"]) for ln in errata],
                         [(1, f"APH/auditoria/{FECHA_ERRATA}/reloj_dmc/errata_1.json")])
        self.assertIn(("corrida_confirmatoria", 1), [(ln["evento"], ln.get("errata")) for ln in lineas])

    # --- C.27 (raíz falsa) ----------------------------------------------------------------------
    def test_p27_corrida_falsa_no_toca_volumes(self):
        """Registro de open, os.stat y os.lstat: ningún acceso bajo /Volumes; sí bajo la DMC falsa."""
        self.assertEqual(self.A1["codigo"], V.SALIDA_OK, self.A1["stderr"])
        volumes = os.path.normpath("/Volumes").casefold()
        bajo_volumes = [r for _, r in self.registro_A.accesos if r.casefold().startswith(volumes + os.sep)]
        self.assertEqual(bajo_volumes, [])
        eventos = {e for e, _ in self.registro_A.accesos}
        self.assertTrue({"open", "os.stat"} <= eventos, eventos)      # el registro sí ve la DMC falsa
        self.assertNotIn("_comun_modelo", sys.modules)
        self.assertNotIn("_common", sys.modules)

    # --- C.28 -----------------------------------------------------------------------------------
    def test_p28_salidas_sin_users_ni_arroba(self):
        """Carpeta sellada, cerrojo, avance y consola: sin «/Users/», «@» ni la carpeta personal."""
        self.assertEqual(salidas.verificar_privacidad(_carpeta(self.A)), [])
        for info in (self.A, self.C, self.D):
            for ruta in info["rutas"].corridas.rglob("*"):
                if ruta.is_file() and ruta.suffix in (".json", ".jsonl", ".md", ".csv", ".txt"):
                    self.assertTrue(entorno.sin_datos_privados(ruta.read_text(encoding="utf-8")), ruta.name)
        for corrida in (self.A1, self.A2, self.A3, self.C1, self.C2, self.C3, self.D1, self.D2, self.intruso_B,
                        self.intruso_D):
            self.assertTrue(entorno.sin_datos_privados(corrida["stdout"] + corrida["stderr"]))

    # --- Cerrojo, avance, consola y sello -------------------------------------------------------
    def test_cerrojo_registra_cada_intento_con_su_resultado(self):
        eventos = [ln["evento"] for ln in self.lineas_A1]
        self.assertEqual(eventos, ["intento", "corrida_confirmatoria", "fin"])
        self.assertEqual(self.lineas_A1[0]["fecha_utc"], "2026-10-30")
        # §7.1: el intento lleva las huellas de los archivos pasados por argumento (ninguno de la DMC).
        self.assertEqual(self.lineas_A1[0]["huellas"],
                         {"addendum": entorno.sha256_archivo(self.A["addendum"]),
                          "linea_cierre": entorno.sha256_archivo(self.A["cierre"]), "errata": None, "enmienda4": None})
        errata = [ln for ln in _cerrojo(self.A) if ln["evento"] == "intento" and ln["argumentos"]["errata"]][0]
        self.assertEqual(errata["huellas"]["errata"], entorno.sha256_archivo(self.errata))
        conf = self.lineas_A1[1]
        self.assertEqual(conf["etiqueta"], "HUMAN20261030_RELOJ_DMC_1")
        self.assertIsNone(conf["errata"])
        self.assertEqual(conf["enmienda4_punto12"]["anclado"], False)
        self.assertEqual(set(conf["entradas"]), {"addendum_sha256", "cierre_sha256", "progreso_sha256",
                                                 "huella_manifiestos", "commit_c1"})
        self.assertEqual(self.lineas_A1[2]["resultado"], "sellada")
        # Sólo agrega: el cerrojo de A empieza con las líneas de la primera corrida, intactas.
        self.assertEqual(_cerrojo(self.A)[:3], self.lineas_A1)

    def test_orden_5_2_evaluar_red_y_luego_escribir_corrida(self):
        """evaluar_red y después salidas.escribir_corrida(verificar=verificador_7_3(…)), fuera del modo
        sintético, con A1, A2 y G-dup en los controles y todas las huellas de entrada («Ola 4a cerrada»)."""
        self.assertEqual(self.B1["codigo"], V.SALIDA_OK, self.B1["stderr"])
        self.assertEqual(len(self.orden_B), 2)
        self.assertEqual(self.orden_B[0], ("evaluar_red",))
        nombre, con_verificador, sintetico, errata, con_meses, controles, huellas = self.orden_B[1]
        self.assertEqual((nombre, con_verificador, sintetico, errata, con_meses),
                         ("escribir_corrida", True, False, False, True))
        self.assertTrue(set(salidas.CLAVES_CONTROLES) - {"A7"} <= set(controles), controles)
        self.assertTrue(set(salidas.CLAVES_HUELLAS + salidas.CLAVES_ENTRADAS) <= set(huellas), huellas)
        # Las fases en la consola siguen el orden de §5.2.
        fases = [ln.split("] ")[1].split(":")[0] for ln in self.B1["stdout"].splitlines()]
        primeras = [fases.index(f) for f in ("C2_y_huellas", "ERA5-Land", "extraccion_DMC", "estados",
                                             "controles_red", "pasos_1_a_6", "A4", "pasos_7_a_9", "rachas",
                                             "politica", "sello")]
        self.assertEqual(primeras, sorted(primeras))

    def test_c2_candado_retenido_hasta_terminar_de_leer(self):
        """Durante la extracción y §7.3 otro descriptor no puede tomarlo; al terminar, queda libre."""
        self.assertEqual(self.candado_en, {"extraccion": False, "7_3": False})
        self.assertTrue(self.candado_despues)

    def test_reanudacion_salta_unidades_con_huellas_iguales(self):
        """avance.jsonl: una corrida abortada en la fase 4 se retoma sin releer artefactos ni meses ERA5."""
        self.assertEqual(self.C1["codigo"], V.SALIDA_FALLA)
        self.assertIn("estados_de_lineas", self.C1["stderr"])
        self.assertNotIn("falso", self.C1["stderr"])                     # el mensaje queda retenido (VER-11)
        carpeta = _carpeta(self.C)
        retenido = json.loads((carpeta / "error_retenido_1.json").read_bytes())
        self.assertEqual((retenido["fase"], retenido["tipo"]), ("estados_de_lineas", "RuntimeError"))
        self.assertEqual(self.C2["codigo"], V.SALIDA_RECHAZO)
        self.assertIn("--reanudar", self.C2["stderr"])
        self.assertEqual(self.C3["codigo"], V.SALIDA_OK, self.C3["stderr"])
        self.assertEqual(self.lecturas_C3, {"estaciones": 0, "meses_era5": 0})
        self.assertEqual(salidas.verificar_sello(carpeta), [])
        self.assertEqual(self.C4["codigo"], V.SALIDA_RECHAZO)
        avance = (carpeta / V.AVANCE).read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(avance), len(extraccion.MESES_ERA5) + 1)   # 321 meses y la estación, una vez
        for linea in avance:
            obj = json.loads(linea)
            self.assertEqual(set(obj), {"unidad", "entrada", "salida", "estado"})
            self.assertEqual(obj["estado"], "hecho")
        eventos = [ln["evento"] for ln in _cerrojo(self.C)]
        self.assertEqual(eventos, ["intento", "corrida_confirmatoria", "fin", "intento", "rechazo", "intento",
                                   "reanudacion", "fin", "intento", "rechazo"])

    def test_consola_sin_veredictos_hasta_el_sello(self):
        """Sólo conteos en stdout; los avisos de stderr no traen veredictos (tampoco el de un error)."""
        for corrida in (self.A1, self.B1, self.A2, self.A3, self.C1, self.C2, self.C3, self.D1, self.D2,
                        self.intruso_B, self.intruso_D):
            for linea in corrida["stdout"].splitlines():
                self.assertRegex(linea, _LINEA_CONSOLA)
            texto = corrida["stdout"] + corrida["stderr"]
            for palabra in PALABRAS_DE_VEREDICTO:
                self.assertNotIn(palabra, texto)
        fases = {ln.split("] ")[1].split(":")[0] for ln in self.A1["stdout"].splitlines()}
        self.assertTrue({"C2_y_huellas", "ERA5-Land", "extraccion_DMC", "estados", "pasos_1_a_6", "sello"} <= fases,
                        fases)

    def test_sello_recibo_corrida(self):
        """sha256 de todo el contenido; la cadena tablas → informe → política → recibo se sostiene."""
        carpeta = _carpeta(self.A)
        self.assertEqual(salidas.verificar_sello(carpeta), [])
        self.assertEqual(salidas.comprobar_cadena(carpeta), [])
        self.assertIn(V.AVANCE, self.recibo_A1["archivos"])
        inf = json.loads((carpeta / salidas.ARCHIVO_INFORME).read_bytes())
        self.assertFalse(inf["modo_sintetico"])
        self.assertTrue(inf["controles"]["A1"]["pasa"])
        self.assertTrue(inf["controles"]["A2"]["pasa"])
        self.assertIsNotNone(inf["controles"]["A7"]["pasa"])
        self.assertEqual(inf["entradas"]["progreso"]["ruta"], "DMC/progreso.json")
        self.assertEqual(len(inf["entradas"]["era5l"]), len(extraccion.MESES_ERA5))
        self.assertEqual(inf["otras_huellas"]["corrida"]["etiqueta"], "HUMAN20261030_RELOJ_DMC_1")
        self.assertEqual(inf["otras_huellas"]["enmienda4_punto12"]["anclado"], False)
        pol = json.loads((carpeta / salidas.ARCHIVO_POLITICA).read_bytes())
        self.assertEqual(pol["protocolo"]["commit_ap"], _git(self.A["rutas"].ap, "rev-parse", "HEAD"))
        self.assertEqual(pol["configuracion"]["sha256"], umbrales.SHA_JSON_C0)

    # --- Hallazgos de la revisión de la ola 4b ----------------------------------------------------
    def test_segundo_aplicar_durante_la_corrida_no_rompe_el_cerrojo(self):
        """VER-16: otro --aplicar en la fase 4 se rechaza y queda registrado; la corrida en curso registra igual
        su «fin» (encadenado sobre el final real) y la cadena sigue válida."""
        self.assertEqual(self.intruso_B["codigo"], V.SALIDA_RECHAZO, self.intruso_B["stderr"])
        self.assertIn("otro --aplicar está en curso", self.intruso_B["stderr"])
        self.assertEqual(self.B1["codigo"], V.SALIDA_OK, self.B1["stderr"])
        lineas = _cerrojo(self.B)                                         # releída: la cadena calza
        self.assertEqual([(ln["intento"], ln["evento"]) for ln in lineas],
                         [(1, "intento"), (1, "corrida_confirmatoria"), (2, "intento"), (2, "rechazo"), (1, "fin")])
        self.assertEqual(lineas[-1]["resultado"], "sellada")
        self.assertTrue(any("otro --aplicar está en curso" in m for m in lineas[3]["motivos"]))
        self.assertEqual(lineas[2]["huellas"]["addendum"], entorno.sha256_archivo(self.B["addendum"]))

    def test_abortada_con_otro_aplicar_no_muestra_el_mensaje(self):
        """VER-11 y VER-16: la corrida que aborta con un mensaje que trae un veredicto, mientras otro --aplicar
        queda rechazado, registra su fin y no relanza nada: ni la consola ni el cerrojo traen el mensaje."""
        self.assertEqual(self.D1["codigo"], V.SALIDA_FALLA, self.D1["stderr"])
        self.assertEqual(self.intruso_D["codigo"], V.SALIDA_RECHAZO)
        for palabra in PALABRAS_DE_VEREDICTO:
            self.assertNotIn(palabra, self.D1["stdout"] + self.D1["stderr"])
        lineas = _cerrojo(self.D)
        self.assertEqual([(ln["intento"], ln["evento"]) for ln in lineas[:5]],
                         [(1, "intento"), (1, "corrida_confirmatoria"), (2, "intento"), (2, "rechazo"), (1, "fin")])
        self.assertEqual((lineas[4]["resultado"], lineas[4]["fase"], lineas[4]["mensaje"]),
                         ("abortada", "estados_de_lineas", None))
        self.assertNotIn("F(0)", (self.D["rutas"].corridas / V.CERROJO).read_text(encoding="utf-8"))

    def test_errata_reemplaza_una_corrida_abortada(self):
        """VER-6 y VER-7: con una corrida confirmatoria abortada (sin sellar), una errata sellada habilita la
        corrida _ERRATA1, que la reemplaza; la pendiente ya no se reanuda y su carpeta queda como estaba."""
        self.assertEqual(self.D2["codigo"], V.SALIDA_OK, self.D2["stderr"])
        nueva = _carpeta(self.D, "_ERRATA1")
        self.assertEqual(salidas.verificar_sello(nueva), [])
        self.assertTrue(json.loads((nueva / salidas.ARCHIVO_POLITICA).read_bytes())["errata_post_c4"])
        vieja = _carpeta(self.D)
        self.assertFalse((vieja / salidas.RECIBO).exists())
        self.assertTrue((vieja / "error_retenido_1.json").is_file())
        conf = [ln for ln in _cerrojo(self.D) if ln["evento"] == "corrida_confirmatoria"]
        self.assertEqual([(ln["etiqueta"], ln["errata"], ln.get("reemplaza")) for ln in conf],
                         [("HUMAN20261030_RELOJ_DMC_1", None, None),
                          ("HUMAN20261030_RELOJ_DMC_1_ERRATA1", 1, "HUMAN20261030_RELOJ_DMC_1")])
        self.assertEqual(json.loads((nueva / salidas.ARCHIVO_INFORME).read_bytes())["otras_huellas"]["corrida"]
                         ["reemplaza"], "HUMAN20261030_RELOJ_DMC_1")
        self.assertEqual(self.D3["codigo"], V.SALIDA_RECHAZO)
        self.assertIn("no hay una corrida confirmatoria sin sellar", self.D3["stderr"])

    def test_lineas_sin_cv_una_sola_desviacion(self):
        """SAL-22: la desviación de «lineas_sin_cv» la agrega salidas.informe; el ejecutable no la repite."""
        self.assertEqual(self.C3["codigo"], V.SALIDA_OK, self.C3["stderr"])
        inf = json.loads((_carpeta(self.C) / salidas.ARCHIVO_INFORME).read_bytes())
        sobre_cv = [d for d in inf["desviaciones"] if "reglas vencidas" in d]
        self.assertEqual(sobre_cv, [salidas.DESVIACION_LINEAS_SIN_CV.format(lineas="E6")])


# =============================================================================================
# Rechazos de C4 con repositorios git falsos (sin corrida completa)
# =============================================================================================
class PruebasC4(unittest.TestCase):
    def setUp(self):
        _exigir_codigo_fijado(self)
        self.info = _raiz(self.id().rsplit(".", 1)[-1])
        self.rutas = self.info["rutas"]

    def _rechazo(self, *extra) -> tuple[dict, list[str]]:
        """modo_aplicar con un registro que FALLA si algo abre o lista un artefacto o un manifiesto."""
        prohibidas = (V.VOLUMES, self.rutas.dmc / extraccion.CARPETA_ESTACIONES)
        corrida = _aplicar(self.info, *extra, registro=V.RegistroAccesos(prohibidas, bloquear=True))
        lineas = _cerrojo(self.info)
        self.assertEqual(corrida["codigo"], V.SALIDA_RECHAZO, corrida["stderr"])
        self.assertEqual([ln["evento"] for ln in lineas], ["intento", "rechazo"])
        self.assertFalse(any(self.rutas.corridas.glob("HUMAN*")))
        # §7.1: también el intento rechazado lleva sus huellas (VER-16).
        self.assertEqual(lineas[0]["huellas"]["addendum"], entorno.sha256_archivo(self.info["addendum"]))
        self.assertEqual(lineas[0]["huellas"]["linea_cierre"], entorno.sha256_archivo(self.info["cierre"]))
        return corrida, lineas[1]["motivos"]

    def test_c4_lista_cerrada_del_addendum(self):
        """Una huella distinta rechaza; también un addendum que no cubre el código que corre."""
        self.assertEqual(V.comprobar_lista_cerrada(self.info["addendum"], rutas=self.rutas,
                                                   exigidos=V._exigidos(self.info["cfg"])), [])
        texto = self.rutas.aph / TEXTO_V11
        original = texto.read_bytes()
        texto.write_bytes(original + b"\n")
        motivos = V.comprobar_lista_cerrada(self.info["addendum"], rutas=self.rutas)
        self.assertTrue(any("la huella de APH/" + TEXTO_V11 in m for m in motivos), motivos)
        texto.write_bytes(original)
        # Un .py del paquete que no está en la lista.
        nuevo = self.info["cfg"].paquete / "extra.py"
        nuevo.write_text("X = 0\n", encoding="utf-8")
        motivos = V.comprobar_lista_cerrada(self.info["addendum"], rutas=self.rutas,
                                            exigidos=V._exigidos(self.info["cfg"]))
        self.assertEqual(motivos, [f"la lista cerrada no incluye AP/{V.RUTA_PAQUETE_AP}/extra.py"])
        _, motivos = self._rechazo()
        self.assertIn(f"la lista cerrada no incluye AP/{V.RUTA_PAQUETE_AP}/extra.py", motivos)
        nuevo.unlink()
        # Un addendum mal formado.
        with tempfile.TemporaryDirectory() as tmp:
            malo = Path(tmp) / V.ARCHIVO_ADDENDUM
            malo.write_text(json.dumps({"schema": V.ESQUEMA_ADDENDUM}), encoding="utf-8")
            self.assertTrue(V.comprobar_lista_cerrada(malo, rutas=self.rutas)[0].startswith(
                "el addendum de C1 no se puede usar"))

    def test_c4_lista_cerrada_cubre_la_salida_de_c1(self):
        """VER-4 (§10, C1): la lista registra las pruebas, bateria_v1.csv y la salida de la batería, con las
        huellas de LOCAL/…/v1/c1/sha256.json."""
        cfg = self.info["cfg"]
        c1 = self.rutas.corridas / V.CARPETA_C1
        alias = {n: entorno.alias(c1 / n, self.rutas) for n in (*V.ARCHIVOS_C1, V.ARCHIVO_HUELLAS)}
        exigidos = V._exigidos(cfg)
        huellas = json.loads((c1 / V.ARCHIVO_HUELLAS).read_bytes())
        for n in V.ARCHIVOS_C1:
            self.assertEqual(exigidos[alias[n]], huellas[n])
        self.assertIsNone(exigidos[alias[V.ARCHIVO_HUELLAS]])
        datos = json.loads(self.info["addendum"].read_bytes())
        with tempfile.TemporaryDirectory() as tmp:
            malo = Path(tmp) / V.ARCHIVO_ADDENDUM
            for falta in ("bateria_v1.csv", "pruebas_c1.txt", "registro_8F.jsonl", V.ARCHIVO_HUELLAS):
                with self.subTest(falta=falta):
                    lista = {k: v for k, v in datos["lista_cerrada"].items() if k != alias[falta]}
                    salida = {k: v for k, v in datos["salida_bateria"].items() if k != alias[falta]}
                    malo.write_bytes(_json({**datos, "lista_cerrada": lista, "salida_bateria": salida}))
                    self.assertEqual(V.comprobar_lista_cerrada(malo, rutas=self.rutas, exigidos=exigidos),
                                     [f"la lista cerrada no incluye {alias[falta]}"])
        # Una salida de C1 rehecha (otro sha256.json) sin poner al día el addendum: rechaza.
        (c1 / "bateria_v1.csv").write_text("otra tabla\n", encoding="utf-8")
        huellas["bateria_v1.csv"] = entorno.sha256_archivo(c1 / "bateria_v1.csv")
        (c1 / V.ARCHIVO_HUELLAS).write_bytes(entorno.json_canonico(huellas))
        _, motivos = self._rechazo()
        self.assertIn(f"lista cerrada: la huella de {alias['bateria_v1.csv']} difiere", " ".join(motivos))
        self.assertIn(f"{alias['bateria_v1.csv']}: el archivo en uso difiere de la lista cerrada", motivos)
        # Sin sha256.json, cualquier huella vale, pero la lista debe traer cada archivo (y el propio sha256.json).
        (c1 / V.ARCHIVO_HUELLAS).unlink()
        self.assertTrue(all(V._exigidos(cfg)[alias[n]] is None for n in V.ARCHIVOS_C1))

    def test_c4_otro_aplicar_en_curso_se_rechaza_y_registra(self):
        """VER-16: con el candado propio de --aplicar tomado por otro proceso, el intento queda registrado
        («intento» y «rechazo») y no corre nada."""
        with _candado_tomado(self.rutas.corridas / V.CANDADO_APLICAR):
            _, motivos = self._rechazo()
        self.assertEqual(len(motivos), 1)
        self.assertTrue(motivos[0].startswith("otro --aplicar está en curso"), motivos)
        self.assertIn(f"LOCAL/{entorno.SUBRUTA_CORRIDAS}/{V.CANDADO_APLICAR}", motivos[0])

    def test_c4_reanudar_registra_el_fin_que_falto(self):
        """VER-16: una corrida que selló su carpeta sin poder registrar su «fin» (por ejemplo, disco lleno) se
        cierra con --reanudar, que sólo agrega ese fin: no toca la DMC ni la carpeta. Con el sello roto, rechaza."""
        etiqueta = "HUMAN20261029_RELOJ_DMC_1"
        carpeta = self.rutas.corridas / etiqueta
        _escribir(carpeta / "informe_reloj_dmc.json", "{}\n")
        total = salidas.sellar(carpeta)
        cerrojo = V.Cerrojo(self.rutas.corridas / V.CERROJO)
        cerrojo.registrar({"evento": "intento", "intento": None, "fecha_utc": "2026-10-29"})
        cerrojo.registrar({"evento": "corrida_confirmatoria", "intento": 1, "fecha_utc": "2026-10-29",
                           "etiqueta": etiqueta, "errata": None, "entradas": {}})
        antes = sorted((p.name, entorno.sha256_archivo(p)) for p in carpeta.iterdir())
        prohibidas = (V.VOLUMES, self.rutas.dmc)
        corrida = _aplicar(self.info, "--reanudar", registro=V.RegistroAccesos(prohibidas, bloquear=True))
        self.assertEqual(corrida["codigo"], V.SALIDA_OK, corrida["stderr"])
        fin = _cerrojo(self.info)[-1]
        self.assertEqual((fin["evento"], fin["resultado"], fin["etiqueta"], fin["total_sha256"], fin["recuperado"]),
                         ("fin", "sellada", etiqueta, total, True))
        self.assertEqual(sorted((p.name, entorno.sha256_archivo(p)) for p in carpeta.iterdir()), antes)
        corrida = _aplicar(self.info)                                       # ya no hay nada sin sellar
        self.assertEqual(corrida["codigo"], V.SALIDA_RECHAZO)
        self.assertEqual(_cerrojo(self.info)[-1]["motivos"], [V.MOTIVO_CERROJO])
        # Con el sello roto no se registra nada parecido a un fin.
        otra = self.rutas.corridas / "HUMAN20261028_RELOJ_DMC_1"
        _escribir(otra / "informe_reloj_dmc.json", "{}\n")
        salidas.sellar(otra)
        (otra / "informe_reloj_dmc.json").write_text("{\"cambiado\": true}\n", encoding="utf-8")
        cerrojo = V.Cerrojo(self.rutas.corridas / V.CERROJO)
        cerrojo.registrar({"evento": "corrida_confirmatoria", "intento": 9, "fecha_utc": "2026-10-29",
                           "etiqueta": otra.name, "errata": None, "entradas": {}})
        corrida = _aplicar(self.info, "--reanudar")
        self.assertEqual(corrida["codigo"], V.SALIDA_RECHAZO)
        self.assertIn("su sello no verifica", corrida["stderr"])

    def test_c4_git_sucio_o_commit_no_antecesor(self):
        """Árbol sucio en las rutas del protocolo, commit de C1 fuera de origin/main o inexistente: rechaza."""
        addendum = V.leer_addendum(self.info["addendum"])
        rutas_protocolo = list(V.RUTAS_PROTOCOLO) + [a for a in addendum["lista_cerrada"] if not a.startswith("LOCAL/")]
        self.assertEqual(V.comprobar_git(self.rutas.ap, self.rutas.aph, rutas_protocolo, addendum["commit_c1"]), [])
        # Un archivo sin seguimiento dentro del paquete (rutas del protocolo de AP).
        (self.rutas.ap / V.RUTA_PAQUETE_AP / "notas.txt").write_text("x\n", encoding="utf-8")
        motivos = V.comprobar_git(self.rutas.ap, self.rutas.aph, rutas_protocolo, addendum["commit_c1"])
        self.assertEqual(len(motivos), 1)
        self.assertTrue(motivos[0].startswith("AP: el árbol no está limpio"), motivos)
        self.assertIn("notas.txt", motivos[0])
        # Fuera de las rutas del protocolo no cuenta.
        (self.rutas.ap / V.RUTA_PAQUETE_AP / "notas.txt").unlink()
        (self.rutas.ap / "README.md").write_text("otra cosa\n", encoding="utf-8")
        self.assertEqual(V.comprobar_git(self.rutas.ap, self.rutas.aph, rutas_protocolo, addendum["commit_c1"]), [])
        # Un commit de una rama que no llegó a origin/main.
        _git(self.rutas.aph, "checkout", "-q", "-b", "lateral")
        (self.rutas.aph / "lateral.txt").write_text("x\n", encoding="utf-8")
        lateral = _confirmar(self.rutas.aph, "lateral", subir=False)
        _git(self.rutas.aph, "checkout", "-q", "main")
        motivos = V.comprobar_git(self.rutas.ap, self.rutas.aph, rutas_protocolo, lateral)
        self.assertEqual(motivos, [f"el commit de C1 ({lateral[:8]}) no es antecesor de origin/main de APH"])
        motivos = V.comprobar_git(self.rutas.ap, self.rutas.aph, rutas_protocolo, "1" * 40)
        self.assertTrue(motivos[0].startswith("no se pudo comprobar el commit de C1"), motivos)
        # Por el ejecutable: tocar una ruta de APH del protocolo rechaza y queda registrado.
        (self.rutas.aph / V.RUTA_LISTA_V).write_text("codigo\n901601\n", encoding="utf-8")
        _, motivos = self._rechazo()
        self.assertTrue(any(m.startswith("APH: el árbol no está limpio") for m in motivos), motivos)
        self.assertTrue(any("lista_V.csv" in m and "huella" in m for m in motivos), motivos)

    def test_c4_addendum_y_cierre_contra_su_commit(self):
        """E1-6 (VER-2): el archivo pasado debe ser su versión en git y estar en origin/main."""
        # El addendum cambiado y confirmado, pero sin subir a origin/main.
        datos = json.loads(self.info["addendum"].read_bytes())
        datos["lecturas"].append("otra")
        _escribir(self.info["addendum"], _json(datos))
        _confirmar(self.rutas.aph, "addendum sin subir", subir=False)
        _, motivos = self._rechazo()
        self.assertTrue(any(m.startswith("el addendum de C1: su commit") and "origin/main" in m for m in motivos),
                        motivos)

    def test_c4_cierre_fuera_de_su_carpeta_o_sin_frase(self):
        cierre = V.leer_cierre(self.info["cierre"])
        malo = dict(cierre, frase_autor=" ")
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / V.ARCHIVO_CIERRE
            ruta.write_bytes(_json(malo))
            with self.assertRaises(ValueError):
                V.leer_cierre(ruta)
            ruta.write_bytes(_json(cierre))
            estado = V.comprobar_c2(self.rutas.dmc, ruta, aph=self.rutas.aph)
        self.assertFalse(estado.cumple)
        self.assertIn("la línea de cierre de C2 no está dentro del repositorio APH", estado.motivos)

    def test_c4_c2_no_cumplida_rechaza(self):
        """progreso.json sin terminar (y su huella distinta de la línea de cierre): rechazado y registrado."""
        estado = V.comprobar_c2(self.rutas.dmc, self.info["cierre"], aph=self.rutas.aph,
                                commit_c1=V.leer_addendum(self.info["addendum"])["commit_c1"],
                                copias_c2=self.info["cfg"].copias_c2)
        self.assertTrue(estado.cumple, estado.motivos)
        self.assertEqual(estado.n_manifiestos, 3)
        progreso = json.loads((self.rutas.dmc / V.PROGRESO_DMC).read_bytes())
        progreso["phase"] = "acquisition"
        (self.rutas.dmc / V.PROGRESO_DMC).write_bytes(_json(progreso))
        _, motivos = self._rechazo()
        self.assertIn("progreso.json: phase = 'acquisition', no «finished»", motivos)
        self.assertTrue(any("no es la de la línea de cierre" in m for m in motivos), motivos)
        self.assertTrue(any("copia de progreso.json de C2" in m for m in motivos), motivos)

    def test_c2_progreso_y_linea_de_cierre(self):
        """phase, status, final_verification y sha256 (§3.1)."""
        ruta = self.rutas.dmc / V.PROGRESO_DMC
        base = json.loads(ruta.read_bytes())
        casos = {"status": ("blocked_source", "progreso.json: status = 'blocked_source'"),
                 V.CLAVE_VERIFICACION_FINAL: (None, "progreso.json: falta final_verification")}
        for clave, (valor, esperado) in casos.items():
            ruta.write_bytes(_json({**base, clave: valor}))
            estado = V.comprobar_c2(self.rutas.dmc, self.info["cierre"])
            self.assertFalse(estado.cumple)
            self.assertTrue(any(m.startswith(esperado) for m in estado.motivos), estado.motivos)
            self.assertIsNone(estado.huella_manifiestos)            # con C2 fallida no se leen los manifiestos
        ruta.write_bytes(_json({**base, "status": "finished_with_pending"}))
        estado = V.comprobar_c2(self.rutas.dmc, self.info["cierre"])
        self.assertEqual([m for m in estado.motivos if "status" in m or "phase" in m], [])
        self.assertTrue(any("no es la de la línea de cierre" in m for m in estado.motivos))
        ruta.unlink()
        self.assertIn("falta DMC/progreso.json", V.comprobar_c2(self.rutas.dmc, self.info["cierre"]).motivos)

    def test_c2_candado_held_o_absent_falla(self):
        """«held» y «absent» hacen fallar C2; el candado nunca se crea."""
        candado = self.rutas.dmc / V.CANDADO_DMC
        fd = os.open(candado, os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with V.CandadoDMC(candado) as c:
                self.assertEqual(c.estado, V.RETENIDO)
                self.assertFalse(c.retenido)
            _, motivos = self._rechazo()
            self.assertTrue(any("«held»" in m for m in motivos), motivos)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        candado.unlink()
        with V.CandadoDMC(candado) as c:
            self.assertEqual(c.estado, V.AUSENTE)
        self.assertFalse(candado.exists())
        enlace_destino = self.rutas.dmc / "otro.lock"
        enlace_destino.touch()
        candado.symlink_to(enlace_destino)
        with V.CandadoDMC(candado) as c:
            self.assertEqual(c.estado, V.INSEGURO)
        candado.unlink()
        enlace_destino.unlink()

    def test_c2_candado_retenido_y_sin_escribir(self):
        """Mientras dura el contexto otro descriptor no puede tomarlo; no cambia el archivo ni la carpeta."""
        candado = self.rutas.dmc / V.CANDADO_DMC
        antes = (os.stat(candado).st_mtime_ns, os.stat(candado).st_size, sorted(os.listdir(self.rutas.dmc)))
        with V.CandadoDMC(candado) as c:
            self.assertEqual(c.estado, V.TOMADO)
            self.assertFalse(_flock_libre(candado))
            c.liberar()
            self.assertTrue(_flock_libre(candado))
        self.assertEqual((os.stat(candado).st_mtime_ns, os.stat(candado).st_size, sorted(os.listdir(self.rutas.dmc))),
                         antes)

    def test_huellas_cambiadas_al_terminar_abortan(self):
        """progreso.json o un manifiesto cambiados al terminar la lectura: ErrorC2 (VER-9)."""
        commit_c1 = V.leer_addendum(self.info["addendum"])["commit_c1"]
        for cambio in ("progreso", "manifiesto"):
            with self.subTest(cambio=cambio):
                info = _raiz(f"huellas_{cambio}")
                dmc = info["rutas"].dmc
                with V.CandadoDMC(dmc / V.CANDADO_DMC) as candado:
                    estado = V.comprobar_c2(dmc, info["cierre"], aph=info["rutas"].aph, commit_c1=commit_c1)
                    self.assertTrue(estado.cumple, estado.motivos)
                    lectura = V._LecturaDMC(dmc, estado, candado)
                    if cambio == "progreso":
                        (dmc / V.PROGRESO_DMC).write_bytes((dmc / V.PROGRESO_DMC).read_bytes() + b" ")
                    else:
                        manifiesto = sorted((dmc / "estaciones" / CASO.codigo).glob("*.manifest.json"))[0]
                        manifiesto.write_bytes(manifiesto.read_bytes() + b" ")
                    with self.assertRaises(V.ErrorC2):
                        lectura.cerrar()
                    self.assertTrue(candado.retenido)
                    self.assertFalse(lectura.cerrada)
        # Sin cambios, cierra y suelta el candado.
        dmc = self.rutas.dmc
        with V.CandadoDMC(dmc / V.CANDADO_DMC) as candado:
            estado = V.comprobar_c2(dmc, self.info["cierre"])
            lectura = V._LecturaDMC(dmc, estado, candado)
            lectura.cerrar()
            self.assertTrue(lectura.cerrada)
            self.assertFalse(candado.retenido)

    def test_c4_cerrojo_con_corrida_confirmatoria_sin_errata(self):
        """El cuarto caso de §10, sin correr nada: un cerrojo con una corrida confirmatoria sellada."""
        cerrojo = V.Cerrojo(self.rutas.corridas / V.CERROJO)
        cerrojo.registrar({"evento": "intento", "intento": 1, "fecha_utc": "2026-10-29"})
        cerrojo.registrar({"evento": "corrida_confirmatoria", "intento": 1, "fecha_utc": "2026-10-29",
                           "etiqueta": "HUMAN20261029_RELOJ_DMC_1", "errata": None, "entradas": {}})
        cerrojo.registrar({"evento": "fin", "intento": 1, "fecha_utc": "2026-10-29", "resultado": "sellada",
                           "etiqueta": "HUMAN20261029_RELOJ_DMC_1"})
        corrida = _aplicar(self.info)
        self.assertEqual(corrida["codigo"], V.SALIDA_RECHAZO)
        motivos = V.Cerrojo(self.rutas.corridas / V.CERROJO).lineas[-1]["motivos"]
        self.assertEqual(motivos, [V.MOTIVO_CERROJO])


# =============================================================================================
# Unidades: cerrojo, avance, consola, carpeta, registro de accesos y argumentos
# =============================================================================================
class PruebasUnidades(unittest.TestCase):
    def test_cerrojo_solo_agrega_y_detecta_reescritura(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / V.CERROJO
            c = V.Cerrojo(ruta)
            self.assertFalse(c.hay_corrida_confirmatoria())
            self.assertIsNone(c.errata_confirmada())
            c.registrar({"evento": "intento", "intento": 1})
            c.registrar({"evento": "corrida_confirmatoria", "intento": 1, "etiqueta": "X", "errata": None})
            self.assertTrue(V.Cerrojo(ruta).hay_corrida_confirmatoria())
            self.assertEqual(V.Cerrojo(ruta).sin_sellar()["etiqueta"], "X")
            c.registrar({"evento": "errata", "intento": 2, "n": 1, "documento": {"sha256": "a" * 64}})
            self.assertEqual(V.Cerrojo(ruta).errata_confirmada(), 1)
            c.registrar({"evento": "corrida_confirmatoria", "intento": 2, "etiqueta": "Y", "errata": 1})
            self.assertIsNone(V.Cerrojo(ruta).errata_confirmada())
            datos = ruta.read_bytes()
            self.assertEqual(len(datos.splitlines()), 4)
            # Otro proceso agregó una línea (VER-16): la nueva se encadena sobre el final real del archivo, y el
            # número de un «intento» sin número se asigna bajo el flock.
            otro = V.Cerrojo(ruta)
            self.assertEqual(otro.registrar({"evento": "intento", "intento": None})["intento"], 2)
            self.assertEqual(c.registrar({"evento": "intento", "intento": None})["intento"], 3)
            self.assertEqual([ln["intento"] for ln in V.Cerrojo(ruta).lineas], [1, 1, 2, 2, 2, 3])
            self.assertEqual(c.lineas, V.Cerrojo(ruta).lineas)
            # Una línea ya leída que desaparece del final (la cadena que queda calza): se detecta igual.
            completo = ruta.read_bytes()
            ruta.write_bytes(b"".join(completo.splitlines(keepends=True)[:-1]))
            with self.assertRaises(V.ErrorCerrojo):
                c.registrar({"evento": "rechazo", "intento": 3, "motivos": []})
            ruta.write_bytes(completo)
            # Reescribir, borrar o cortar una línea rompe la cadena.
            lineas = ruta.read_bytes().splitlines(keepends=True)
            for alterado in (b"".join(lineas[1:]), lineas[0] + lineas[2].replace(b'"intento":1', b'"intento":7'),
                             b"".join(lineas)[:-1], b"".join(lineas) + b"{}\n"):
                ruta.write_bytes(alterado)
                with self.assertRaises(V.ErrorCerrojo):
                    V.Cerrojo(ruta)
            ruta.write_bytes(b"".join(lineas))
            # Nada privado entra al cerrojo.
            with self.assertRaises(ValueError):
                V.Cerrojo(ruta).registrar({"evento": "rechazo", "motivos": ["/Users/alguien/x"]})
            self.assertEqual(ruta.read_bytes(), b"".join(lineas))

    def test_avance_solo_huellas_y_estado(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / V.AVANCE
            a = V.Avance(ruta)
            self.assertFalse(a.hecho("dmc/330020", "a" * 64))
            a.registrar("dmc/330020", "a" * 64, "b" * 64)
            self.assertTrue(a.hecho("dmc/330020", "a" * 64))
            self.assertFalse(a.hecho("dmc/330020", "c" * 64))
            for malo in (("dmc/330020", "veredicto", "b" * 64), ("dmc 330020", "a" * 64, "b" * 64)):
                with self.assertRaises(ValueError):
                    a.registrar(*malo)
            # Un corte deja una línea incompleta: se ignora y la unidad se rehace.
            with open(ruta, "ab") as f:
                f.write(b'{"unidad":"era5/200001","entr')
            b = V.Avance(ruta)
            self.assertEqual(b.ignoradas, 1)
            self.assertFalse(b.hecho("era5/200001", "d" * 64))
            b.registrar("era5/200001", "d" * 64, "e" * 64)
            c = V.Avance(ruta)
            self.assertTrue(c.hecho("era5/200001", "d" * 64))
            self.assertTrue(c.hecho("dmc/330020", "a" * 64))
            self.assertEqual(c.ignoradas, 1)
            for linea in ruta.read_text(encoding="utf-8").splitlines():
                if linea.startswith('{"entrada"'):
                    self.assertEqual(set(json.loads(linea)), {"unidad", "entrada", "salida", "estado"})

    def test_consola_solo_conteos(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            for k in range(0, 101):
                V.consola("estados", k, 100)
            V.consola("A4", 1, 1)
        lineas = out.getvalue().splitlines()
        self.assertTrue(all(_LINEA_CONSOLA.fullmatch(ln) for ln in lineas))
        self.assertLessEqual(len(lineas), V.PASOS_CONSOLA + 3)
        self.assertEqual(lineas[-2:], ["[reloj_dmc] estados: 100/100", "[reloj_dmc] A4: 1/1"])
        for malo in (("F(0) confirmado", 1, 1), ("estados", "1", 2), ("estados", True, 1), ("", 1, 1)):
            with self.assertRaises(ValueError):
                V.consola(*malo)

    def test_carpeta_corrida(self):
        base = Path("/tmp/corridas")
        self.assertEqual(V.carpeta_corrida(base, "2026-10-30", None), base / "HUMAN20261030_RELOJ_DMC_1")
        self.assertEqual(V.carpeta_corrida(base, "20261030", 2), base / "HUMAN20261030_RELOJ_DMC_1_ERRATA2")
        for malo in (("2026-13-01", None), ("2026-10-30", 0), ("ayer", None)):
            with self.assertRaises(ValueError):
                V.carpeta_corrida(base, *malo)

    def test_registro_de_accesos_bloquea_sin_tocar(self):
        """El registro ve open, os.stat, os.lstat y los listados; en bloqueo, falla ANTES del acceso."""
        prohibida = "/Volumes/reloj_dmc_prueba_inexistente"
        antes = (os.stat, os.lstat)        # con --sintetico ya hay un registro afuera: no son los originales
        with V.RegistroAccesos((prohibida,), bloquear=True) as r:
            for accion in (lambda: open(prohibida + "/x.json", "rb"), lambda: os.stat(prohibida),
                           lambda: os.lstat(prohibida + "/y"), lambda: os.listdir(prohibida),
                           lambda: Path(prohibida, "z").exists(), lambda: Path(prohibida).is_symlink()):
                with self.assertRaises(PermissionError):
                    accion()
            open(os.devnull, "rb").close()
            os.stat(os.devnull)
        self.assertEqual(len(r.accesos), 6)
        self.assertEqual({e for e, _ in r.accesos}, {"open", "os.stat", "os.lstat", "os.listdir"})
        self.assertEqual((os.stat, os.lstat), antes)           # se restituyen al salir

    def test_registros_anidados_del_interior_al_exterior(self):
        """VER-14: el registro más interior que bloquea niega el acceso; los de afuera lo anotan aparte
        (negados_dentro) y no como acceso. Un registro que no bloquea, dentro de uno que sí, lo anota como
        acceso, y el de afuera lo niega igual (falla cerrado)."""
        prohibida = "/Volumes/reloj_dmc_prueba_inexistente"
        with V.RegistroAccesos((V.VOLUMES,)) as afuera:
            with V.RegistroAccesos((prohibida,), bloquear=True) as adentro:
                with self.assertRaises(PermissionError):
                    os.lstat(prohibida + "/x")
                with self.assertRaises(PermissionError):
                    open(prohibida + "/y.json", "rb")
        self.assertEqual([e for e, _ in adentro.accesos], ["os.lstat", "open"])
        self.assertEqual(afuera.accesos, [])
        self.assertEqual([e for e, _ in afuera.negados_dentro], ["os.lstat", "open"])
        with V.RegistroAccesos((prohibida,), bloquear=True) as afuera:
            with V.RegistroAccesos((V.VOLUMES,)) as adentro:
                with self.assertRaises(PermissionError):
                    os.stat(prohibida + "/z")
        self.assertEqual(([e for e, _ in adentro.accesos], [e for e, _ in afuera.accesos]), (["os.stat"], ["os.stat"]))
        self.assertEqual((adentro.negados_dentro, afuera.negados_dentro), ([], []))

    def test_argumentos(self):
        for malo in (["--sintetico", "--aplicar"], ["--aplicar"], ["--aplicar", "--addendum", "a"],
                     ["--control-era5", "--bateria"], ["--sintetico", "--reanudar"],
                     ["--aplicar", "--addendum", "a", "--linea-cierre", "b", "--salida", "c"], [],
                     ["--control-era5"], ["--control-era5", "--salida", "d"]):           # VER-13
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                V.analizar_argumentos(malo)
        a = V.analizar_argumentos(["--aplicar", "--addendum", "a", "--linea-cierre", "b", "--reanudar"])
        self.assertTrue(a.aplicar and a.reanudar)
        self.assertEqual(V.analizar_argumentos(["--control-era5", "--addendum", "a"]).addendum, "a")

    def test_ningun_script_se_llama_descargar_ni_download(self):
        """Nombres de archivo del paquete (así el control de descargas activas no se ve a sí mismo)."""
        nombres = [p.name for p in PAQUETE.rglob("*") if p.is_file()]
        self.assertTrue(nombres)
        self.assertEqual([n for n in nombres if n.lower().startswith(("descargar_", "download_"))], [])

    def test_configuracion_real_apunta_a_los_alias(self):
        """configuracion_real no toca el disco y usa las rutas del protocolo (alias)."""
        rutas = entorno.rutas_reales()
        cfg = V.configuracion_real(rutas)
        self.assertEqual(entorno.alias(cfg.catalogo_pixeles, rutas), "ERA5L/catalogo_pixeles.parquet")
        self.assertEqual(entorno.alias(cfg.copias_c2, rutas), "LOCAL/evidencia_vista/reloj_dmc/c2")
        self.assertEqual(entorno.alias(cfg.lista_v, rutas), f"APH/{V.RUTA_LISTA_V}")
        self.assertEqual(cfg.paquete, PAQUETE)
        self.assertEqual(cfg.sha_catalogo_pixeles, fijados.SHA_CATALOGO_PIXELES)
        self.assertEqual(entorno.alias(cfg.rutas.corridas / V.CERROJO, rutas),
                         "LOCAL/modelado_1km/verificacion_reloj_dmc/v1/intentos_aplicar.jsonl")


# =============================================================================================
# C.27: ceguera en modo sintético; sin _comun_modelo ni _common
# =============================================================================================
class PruebasGrupoC27(unittest.TestCase):
    def test_p27_ceguera_en_modo_sintetico(self):
        """Raíz falsa y registro de open, os.stat y os.lstat (en bloqueo): nada bajo /Volumes. Con un patrón
        parcial y sin batería, las pruebas pasan pero C1 no se da por aprobado (VER-15)."""
        _exigir_interprete()
        with tempfile.TemporaryDirectory() as tmp:
            rutas = entorno.rutas_sinteticas(Path(tmp))
            cfg = _cfg_sintetico(rutas)
            args = V.analizar_argumentos(["--sintetico", "--patron", "test_tipos.py"])
            args.configuracion = cfg
            with V.RegistroAccesos((V.VOLUMES,), bloquear=True) as registro, \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
                codigo = V.modo_sintetico(args)
            self.assertEqual(registro.accesos, [])
            self.assertEqual(codigo, V.SALIDA_FALLA, err.getvalue())
            salida = rutas.corridas / V.CARPETA_C1
            huellas = json.loads((salida / V.ARCHIVO_HUELLAS).read_bytes())
            self.assertEqual(sorted(huellas), [V.ARCHIVO_PRUEBAS, V.ARCHIVO_RESUMEN_C1])
            for nombre, sha in huellas.items():
                self.assertEqual(entorno.sha256_archivo(salida / nombre), sha)
            resumen = json.loads((salida / V.ARCHIVO_RESUMEN_C1).read_bytes())
            self.assertEqual((resumen["ceguera"]["accesos"], resumen["ceguera"]["negados_por_las_pruebas"]), (0, 0))
            self.assertFalse(resumen["pruebas"]["completa"])
            self.assertGreater(resumen["pruebas"]["corridas"], 0)
            self.assertTrue(resumen["pruebas"]["aprobadas"])
            self.assertFalse(resumen["exito"])
            self.assertEqual(resumen["motivos"], ["patrón parcial (test_tipos.py): C1 corre todas las pruebas de tests/",
                                                  "sin --bateria: falta el grupo D (§10, C1: «grupos A a D»)"])
            self.assertEqual(set(resumen["interprete"]), {"python", "pandas", "netCDF4", "tzdata", "iana"})
            texto = (salida / V.ARCHIVO_PRUEBAS).read_text(encoding="utf-8")
            self.assertTrue(entorno.sin_datos_privados(texto))
            self.assertIn("test_tipos", texto)

    # Las funciones del paquete que miran si una ruta está bajo /Volumes («detectores»), y las guardas que las usan,
    # con lo que lanzan. test_p27_guardas_de_volumes_rechazan_sin_consultar las llama a todas.
    DETECTORES_VOLUMES = {"entorno.prohibido_volumes": ("entorno.prohibido_volumes", "entorno.escribir_atomico",
                                                        "entorno.rutas_sinteticas"),
                          "red._bajo_volumes": ("red._bajo_volumes", "red.g_dup"),
                          "sintetico._en_volumes": ("sintetico._exigir_destino_temporal", "sintetico.GuardaFalsa",
                                                    "sintetico.GuardaFalsa.write_atomic_bytes")}

    def test_p27_guardas_de_volumes_rechazan_sin_consultar(self):
        """Los 7 accesos negados de la primera corrida completa de C1 (2026-10-24/25): red._bajo_volumes
        (test_red.test_g_dup_lista_casos: os.lstat de /Volumes, /Volumes/Datos y …/progreso.json, y os.stat
        de …/progreso.json) y sintetico._exigir_destino_temporal (test_sintetico.test_formato_real_por_run_download:
        os.lstat de /Volumes, /Volumes/Datos y /Volumes/Datos/x) resolvían la ruta antes de mirar la léxica.
        Toda guarda del paquete debe rechazar una ruta bajo /Volumes (también en minúsculas o con «..») SIN
        consultarla: con un registro propio en bloqueo, ningún acceso. Una ruta temporal pasa, sin accesos. Y la
        lista está completa: los detectores son las funciones del paquete con una constante «volumes» o
        «/Volumes»; si aparece otro, esta prueba falla hasta que se agregue aquí."""
        from reloj_dmc import red

        def es_volumes(n: ast.AST) -> bool:
            return isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.casefold() in ("volumes",
                                                                                                         "/volumes")
        hallados = {f"{ruta.stem}.{nodo.name}" for ruta in sorted(PAQUETE.glob("*.py"))
                    for nodo in ast.parse(ruta.read_text(encoding="utf-8")).body
                    if isinstance(nodo, (ast.FunctionDef, ast.ClassDef)) and any(map(es_volumes, ast.walk(nodo)))}
        self.assertEqual(hallados, set(self.DETECTORES_VOLUMES))

        def bajo_volumes(r: str) -> None:
            if red._bajo_volumes(Path(r)):
                raise PermissionError("red._bajo_volumes: bajo /Volumes")

        with tempfile.TemporaryDirectory() as tmp:
            guarda = S.GuardaFalsa(Path(tmp))
            llamadas = {
                "entorno.prohibido_volumes": (PermissionError, lambda r: entorno.prohibido_volumes(Path(r))),
                "entorno.escribir_atomico": (PermissionError, lambda r: entorno.escribir_atomico(Path(r), b"x")),
                "entorno.rutas_sinteticas": (PermissionError, lambda r: entorno.rutas_sinteticas(Path(r))),
                "red._bajo_volumes": (PermissionError, bajo_volumes),
                "red.g_dup": (PermissionError, lambda r: red.g_dup([Path(r)], None)),
                "sintetico._exigir_destino_temporal": (ValueError, lambda r: S._exigir_destino_temporal(Path(r))),
                "sintetico.GuardaFalsa": (ValueError, lambda r: S.GuardaFalsa(Path(r))),
                "sintetico.GuardaFalsa.write_atomic_bytes": (ValueError, lambda r: guarda.write_atomic_bytes(
                    Path(r), b"{}")),
            }
            self.assertEqual(set(llamadas), {g for gs in self.DETECTORES_VOLUMES.values() for g in gs})
            prohibidas = ("/Volumes/Datos/x.json", "/volumes/Datos/x.json", "/VOLUMES/Datos/sub/../y.json",
                          "/Volumes/reloj_dmc_prueba_inexistente/z/x.json")
            for nombre, (error, llamar) in sorted(llamadas.items()):
                for ruta in prohibidas:
                    with self.subTest(guarda=nombre, ruta=ruta):
                        with V.RegistroAccesos((V.VOLUMES,), bloquear=True) as registro:
                            with self.assertRaisesRegex(error, "/Volumes"):    # el rechazo propio, no el del registro
                                llamar(ruta)
                        self.assertEqual(registro.accesos, [], (nombre, ruta))
            # Una ruta temporal pasa por las guardas de lectura, sin ningún acceso bajo /Volumes.
            with V.RegistroAccesos((V.VOLUMES,), bloquear=True) as registro:
                entorno.prohibido_volumes(Path(tmp) / "a.json")
                self.assertFalse(red._bajo_volumes(Path(tmp) / "a.json"))
                self.assertEqual(S._exigir_destino_temporal(Path(tmp) / "a.json"), Path(tmp) / "a.json")
            self.assertEqual(registro.accesos, [])

    def test_p27_no_importa_comun_modelo_ni_common(self):
        """AST de todos los módulos y sys.modules tras importarlos (en un proceso nuevo, sin bytecode)."""
        for ruta in sorted(PAQUETE.glob("*.py")):
            for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
                nombres = []
                if isinstance(nodo, ast.Import):
                    nombres = [a.name for a in nodo.names]
                elif isinstance(nodo, ast.ImportFrom):
                    nombres = [nodo.module or ""] + [a.name for a in nodo.names]
                for n in nombres:
                    self.assertNotIn(n.split(".")[0], fijados.MODULOS_PROHIBIDOS, f"{ruta.name}: importa {n}")
        modulos = sorted(p.stem for p in PAQUETE.glob("*.py") if p.stem != "__init__")
        codigo = ("import sys, importlib\n"
                  f"for m in {modulos!r}:\n    importlib.import_module('reloj_dmc.' + m)\n"
                  "from reloj_dmc import verificar_reloj_dmc as V\nV.analizar_argumentos(['--sintetico'])\n"
                  "print(sorted(m for m in ('_comun_modelo', '_common') if m in sys.modules))\n")
        r = subprocess.run([str(sys.executable), "-B", "-c", codigo], cwd=str(_RAIZ), capture_output=True,
                           timeout=300, check=False)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", errors="replace")[-2000:])
        self.assertEqual(r.stdout.decode("utf-8").strip().splitlines()[-1], "[]")


# =============================================================================================
# C.28: sin .pyc en los repositorios
# =============================================================================================
class PruebasGrupoC28(unittest.TestCase):
    def test_p28_no_escribe_pyc_en_los_repositorios(self):
        """El ejecutable fija dont_write_bytecode antes de importar: corrido SIN -B, no deja bytecode del
        paquete (con PYTHONPYCACHEPREFIX en una carpeta temporal, para no ensuciar AP aunque fallara)."""
        arbol = ast.parse((PAQUETE / "verificar_reloj_dmc.py").read_text(encoding="utf-8"))
        sentencias = [n for n in arbol.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
        self.assertIsInstance(sentencias[0], ast.ImportFrom)                       # from __future__
        self.assertEqual(ast.unparse(sentencias[1]), "import sys")
        self.assertEqual(ast.unparse(sentencias[2]), "sys.dont_write_bytecode = True")
        antes = sorted(str(p) for p in PAQUETE.rglob("__pycache__"))
        with tempfile.TemporaryDirectory() as tmp:
            entorno_ = {**os.environ, "PYTHONPYCACHEPREFIX": tmp}
            entorno_.pop("PYTHONDONTWRITEBYTECODE", None)
            r = subprocess.run([str(sys.executable), str(PAQUETE / "verificar_reloj_dmc.py"), "--help"],
                               capture_output=True, env=entorno_, timeout=300, check=False)
            self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", errors="replace")[-2000:])
            self.assertIn("--aplicar", r.stdout.decode("utf-8"))
            del_paquete = [str(p) for p in Path(tmp).rglob("*.pyc") if "reloj_dmc" in str(p)]
            self.assertEqual(del_paquete, [])
        self.assertEqual(sorted(str(p) for p in PAQUETE.rglob("__pycache__")), antes)
        self.assertEqual(antes, [])


# =============================================================================================
# --control-era5: descargas activas y sin tocar la DMC
# =============================================================================================
_PS_CON_DESCARGA = ("  4242     1  4242 Fri Oct 24 10:00:00 2026 /usr/bin/python3 "
                    "/x/scripts_pipeline/descargar_tropomi_gases.py --gas CO\n"
                    "  4343     1  4343 Fri Oct 24 10:00:00 2026 /usr/bin/python3 analisis.py\n")


class PruebasControlEra5(unittest.TestCase):
    def setUp(self):
        _exigir_codigo_fijado(self)

    def _info(self) -> dict:
        info = _raiz(self.id().rsplit(".", 1)[-1])
        return info

    def test_control_era5_rechaza_con_descargas_activas(self):
        info = self._info()
        cfg = replace(info["cfg"], procesos=lambda: _PS_CON_DESCARGA)
        self.assertEqual([a["script"] for a in V.descargas_activas(cfg)], ["descargar_tropomi_gases.py"])
        args = V.analizar_argumentos(["--control-era5", "--addendum", str(info["addendum"])])
        args.configuracion = cfg
        with mock.patch.object(V.controles_era5, "correr_c3") as c3, \
                V.RegistroAccesos((info["rutas"].dmc,)) as registro, \
                contextlib.redirect_stderr(io.StringIO()) as err:
            codigo = V.modo_control_era5(args)
        self.assertEqual(codigo, V.SALIDA_RECHAZO)
        self.assertIn("descargar_tropomi_gases.py", err.getvalue())
        c3.assert_not_called()
        self.assertEqual((registro.accesos, registro.negados_dentro), ([], []))

    def test_control_era5_comprueba_antes_y_no_toca_la_dmc(self):
        """Sin descargas: C3 corre (simulado) dentro de un registro que BLOQUEA todo acceso bajo DMC, con los
        umbrales del addendum (VER-13). Con --salida, la lista cerrada se comprueba con las raíces de siempre y
        sólo la escritura va a --salida."""
        info = self._info()
        rutas = info["rutas"]
        orden = []
        cfg = replace(info["cfg"], procesos=lambda: orden.append("ps") or "")
        esperadas = {}

        def c3_falso(rutas_, catalogo, validos, mz, U, **kw):
            orden.append("c3")
            self.assertEqual(rutas_, esperadas["rutas"])
            self.assertTrue(validos)
            self.assertIs(kw["adaptador"], fijados.cargar_adaptador(AP))
            with self.assertRaises(PermissionError):           # la DMC está bloqueada durante C3
                open(rutas.dmc / V.PROGRESO_DMC, "rb")
            resultados = [types.SimpleNamespace(control=c, pasa=True) for c in ("C3a", "C3b", "C3c")]
            carpeta = V.controles_era5.carpeta_c3(rutas_)
            carpeta.mkdir(parents=True, exist_ok=True)
            (carpeta / V.controles_era5.NOMBRE_HUELLAS).write_text("{}", encoding="utf-8")
            return resultados, {"C3a.json": "a" * 64}

        otra = _temporal() / "salida_c3"
        addendum = V.leer_addendum(info["addendum"])
        for salida in (None, otra):
            with self.subTest(salida=salida):
                orden.clear()
                esperadas["rutas"] = rutas if salida is None else replace(rutas, local=otra)
                extra = [] if salida is None else ["--salida", str(salida)]
                args = V.analizar_argumentos(["--control-era5", "--addendum", str(info["addendum"]), *extra])
                args.configuracion = cfg
                with mock.patch.object(V.controles_era5, "correr_c3", c3_falso), \
                        V.RegistroAccesos((rutas.dmc,)) as registro, \
                        contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
                    codigo = V.modo_control_era5(args)
                self.assertEqual(codigo, V.SALIDA_OK, err.getvalue())
                self.assertEqual(orden, ["ps", "c3", "ps"])
                # El intento del simulador lo niega el registro de C3, que es el más interior (VER-14).
                self.assertEqual(registro.accesos, [])
                self.assertEqual([e for e, _ in registro.negados_dentro], ["open"])
                c3 = json.loads((esperadas["rutas"].corridas / V.ARCHIVO_REGISTRO_C3).read_bytes())
                self.assertEqual(c3["umbrales"]["fuente"], "addendum_c1")
                self.assertEqual(c3["umbrales"]["sha256_json"], umbrales.SHA_JSON_C0)
                self.assertEqual(c3["umbrales"]["addendum_c1"],
                                 {"ruta": f"APH/{ADDENDUM}", "sha256": entorno.sha256_archivo(info["addendum"]),
                                  "commit_c1": addendum["commit_c1"]})
                self.assertEqual(c3["codigo"], V._huellas_codigo(info["cfg"].paquete))
                self.assertEqual(set(c3["codigo"]), {f"reloj_dmc/{p.name}" for p in info["cfg"].paquete.glob("*.py")})
                self.assertEqual(c3["controles"], {"C3a": True, "C3b": True, "C3c": True})
                self.assertEqual((c3["descargas_activas_antes"], c3["descargas_activas_despues"]), (0, 0))
        self.assertTrue((otra / entorno.SUBRUTA_CORRIDAS / V.ARCHIVO_REGISTRO_C3).is_file())

    def test_control_era5_con_un_addendum_que_no_cubre_el_codigo(self):
        """VER-13 y VER-4: si la lista cerrada no cubre el código que corre, C3 no corre."""
        info = self._info()
        (info["cfg"].paquete / "extra.py").write_text("X = 0\n", encoding="utf-8")
        args = V.analizar_argumentos(["--control-era5", "--addendum", str(info["addendum"])])
        args.configuracion = info["cfg"]
        with mock.patch.object(V.controles_era5, "correr_c3") as c3, contextlib.redirect_stderr(io.StringIO()) as err:
            codigo = V.modo_control_era5(args)
        self.assertEqual(codigo, V.SALIDA_RECHAZO)
        self.assertIn(f"la lista cerrada no incluye AP/{V.RUTA_PAQUETE_AP}/extra.py", err.getvalue())
        c3.assert_not_called()


# =============================================================================================
# --sintetico (C1) sobre paquetes de pruebas falsos, con la batería simulada sobre las funciones de bateria
# =============================================================================================
def _bateria_falsa(horas: float, reduccion):
    """bateria con tabla_bateria, correr_bateria, ajustar_umbrales y replicas_por_tiempo simulados; las salidas
    (escribir_salidas, tiempo_bateria, criterios_a_json) son las de bateria (VER-15). Nunca corre la batería."""
    from reloj_dmc import bateria as B
    from reloj_dmc import tipos
    llamadas = []
    U0 = umbrales.cargar_c0(APH)
    U1 = U0.ajustado(umbrales.IDS_AJUSTABLES[0])
    criterios = B.CriteriosBateria(por_celda=pd.DataFrame({"celda": ["a"], "erroneas": [0]}), erroneas=0,
                                   sensibilidad={"F(0)": 0.9}, pasa=True, motivos=[],
                                   criterios={"cero_erroneas": {"pasa": True}})

    def tabla_bateria(replicas_d2_d3=None):
        llamadas.append(("tabla", replicas_d2_d3))
        tabla = pd.DataFrame({c: ["x", "y"] for c in B.COLUMNAS_BATERIA})
        tabla["replica"] = [1, replicas_d2_d3 or len(B.COLUMNAS_BATERIA)]
        return tabla

    def correr_bateria(tabla, u, *, avance=None, tiempos=None):
        llamadas.append(("correr", u.huella()))
        if avance is not None:
            avance(len(tabla), len(tabla))
        if tiempos is not None:
            tiempos.update({"redes": {"sesgo0_r1": 1.5}, "detalle_por_red": {}, "estacion_anios": len(tabla)})
        return tipos.tabla_vacia(B.ESQUEMA_RESULTADOS), horas

    def ajustar_umbrales(u, correr, tabla, *, ruta_registro, reloj):
        iteraciones = []
        for n, umbral in enumerate((u, U1), start=1):
            correr(umbral)
            iteraciones.append({"iteracion": n, "fecha_utc": reloj().strftime("%Y-%m-%dT%H:%M:%SZ"),
                                "umbrales_sha256": umbral.huella()})
            entorno.escribir_atomico(ruta_registro, b"".join(entorno.json_canonico(i) + b"\n"   # se reescribe
                                                              for i in iteraciones))           # en cada una
        llamadas.append(("ajustar", len(iteraciones)))
        return B.RegistroAjuste(iteraciones, U1, False, None, tipos.tabla_vacia(B.ESQUEMA_RESULTADOS), criterios)

    modulo = types.ModuleType("reloj_dmc.bateria")
    modulo.__dict__.update({n: getattr(B, n) for n in ("ARCHIVO_REGISTRO_8F", "escribir_salidas", "tiempo_bateria",
                                                       "criterios_por_celda", "criterios_a_json")})
    modulo.__dict__.update(tabla_bateria=tabla_bateria, correr_bateria=correr_bateria,
                           ajustar_umbrales=ajustar_umbrales, replicas_por_tiempo=lambda h, u: reduccion)
    return modulo, llamadas, U0, U1, criterios, B


class PruebasSintetico(unittest.TestCase):
    """--sintetico (VER-14 y VER-15) sobre paquetes falsos: qué aprueba C1 y cómo cuenta la ceguera."""

    def setUp(self):
        _exigir_interprete()
        for ruta in (APH / umbrales.PROTOCOLO_C0, APH / umbrales.JSON_C0):
            if not ruta.is_file():
                self.skipTest(f"falta {ruta.name} anclado en C0; la prueba no se da por aprobada")

    def _sintetico(self, paquete: Path, *extra: str, horas: float = 2.0, reduccion=None, **cambios) -> dict:
        """modo_sintetico (en --salida temporal) con la batería simulada; devuelve código, resumen y archivos."""
        modulo, llamadas, U0, U1, criterios, B = _bateria_falsa(horas, reduccion)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp).resolve()
            rutas = entorno.Rutas(ap=AP, aph=APH, local=tmp, dmc=tmp / "DMC", era5l=tmp / "ERA5L")
            salida = tmp / "c1"
            args = V.analizar_argumentos(["--sintetico", "--salida", str(salida), *extra])
            args.configuracion = _cfg_sintetico(rutas, paquete=paquete, **cambios)
            with mock.patch.object(V, "_modulo_bateria", return_value=modulo), \
                    contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
                codigo = V.modo_sintetico(args)
            archivos = {p.name: p.read_bytes() for p in salida.iterdir()} if salida.is_dir() else {}
        resumen = json.loads(archivos[V.ARCHIVO_RESUMEN_C1]) if V.ARCHIVO_RESUMEN_C1 in archivos else None
        return {"codigo": codigo, "resumen": resumen, "archivos": archivos, "stdout": out.getvalue(),
                "stderr": err.getvalue(), "llamadas": llamadas, "U0": U0, "U1": U1, "criterios": criterios, "B": B}

    def test_sintetico_aprueba_c1_completo_con_bateria(self):
        with _paquete_falso({"test_pasa.py": PRUEBA_PASA}) as paquete:
            r = self._sintetico(paquete, "--bateria")
        self.assertEqual(r["codigo"], V.SALIDA_OK, r["stderr"])
        self.assertTrue(r["resumen"]["exito"])
        self.assertEqual(r["resumen"]["motivos"], [])
        self.assertTrue(r["resumen"]["pruebas"]["completa"])
        self.assertIn("C1 aprobado", r["stderr"])

    def test_sintetico_no_aprueba_con_fallas_esperadas_u_omitidas(self):
        """§10, C1: «se aprueban las pruebas de §8»; wasSuccessful() da por buenas las omitidas y las esperadas."""
        with _paquete_falso({"test_esperada.py": PRUEBA_ESPERADA_Y_OMITIDA}) as paquete:
            r = self._sintetico(paquete, "--bateria")
        self.assertEqual(r["codigo"], V.SALIDA_FALLA)
        p = r["resumen"]["pruebas"]
        self.assertEqual((p["corridas"], p["omitidas"], p["fallas_esperadas"], p["aprobadas"]), (3, 1, 1, False))
        self.assertFalse(r["resumen"]["exito"])
        self.assertEqual(r["resumen"]["motivos"], ["1 omitidas (no se dan por aprobadas)",
                                                   "1 fallas esperadas (pruebas de §8 que no pasan)"])

    def test_sintetico_falla_cerrado_y_no_cuenta_lo_que_niegan_las_pruebas(self):
        """VER-14: lo que niega antes el registro de una prueba no es un acceso; un acceso sin guarda propia lo
        niega el registro de --sintetico (nada llega al disco) y C1 no aprueba."""
        with _paquete_falso({"test_negada.py": PRUEBA_NEGADA_DENTRO}) as paquete:
            r = self._sintetico(paquete, "--bateria")
        self.assertEqual(r["codigo"], V.SALIDA_OK, r["stderr"])
        self.assertEqual((r["resumen"]["ceguera"]["accesos"], r["resumen"]["ceguera"]["negados_por_las_pruebas"]),
                         (0, 2))
        prohibida = _temporal() / "prohibida"
        with _paquete_falso({"test_sin_guarda.py": PRUEBA_SIN_GUARDA.format(prohibida=str(prohibida))}) as paquete:
            r = self._sintetico(paquete, "--bateria", vigiladas_c1=(V.VOLUMES, prohibida))
        self.assertEqual(r["codigo"], V.SALIDA_FALLA)
        self.assertTrue(r["resumen"]["pruebas"]["aprobadas"])             # la prueba vio el PermissionError
        self.assertEqual((r["resumen"]["ceguera"]["accesos"], r["resumen"]["ceguera"]["eventos"]), (1, ["os.lstat"]))
        self.assertEqual(r["resumen"]["motivos"], ["1 accesos bajo las carpetas vigiladas, negados (§8, prueba 27)"])

    def test_sintetico_rechaza_sin_el_interprete_fijado(self):
        with _paquete_falso({"test_pasa.py": PRUEBA_PASA}) as paquete, \
                mock.patch.object(V.entorno, "comprobar_interprete", side_effect=RuntimeError("Entorno no fijado: x")):
            r = self._sintetico(paquete, "--bateria")
        self.assertEqual(r["codigo"], V.SALIDA_RECHAZO)
        self.assertEqual(r["archivos"], {})
        self.assertIn("Entorno no fijado", r["stderr"])
        self.assertEqual([x for x in r["llamadas"] if x[0] == "correr"], [])

    def test_sintetico_bateria_mide_ajusta_y_registra(self):
        """La primera corrida mide el tiempo y es la primera iteración de §8.F; si pasa de 48 h, la tabla se
        regenera con 5 réplicas en D2 y D3 antes de iterar. Las salidas son las de bateria (VER-15)."""
        self.assertEqual(V.ARCHIVOS_BATERIA, ("bateria_v1.csv", "resultados_bateria.parquet",
                                              "criterios_bateria.json", "tiempo_bateria.json", "registro_8F.jsonl"))
        for reduccion in (None, 5):
            with self.subTest(reduccion=reduccion), _paquete_falso({"test_pasa.py": PRUEBA_PASA}) as paquete:
                horas = 49.0 if reduccion else 2.0
                r = self._sintetico(paquete, "--bateria", horas=horas, reduccion=reduccion)
                B, U0, U1, llamadas, archivos = r["B"], r["U0"], r["U1"], r["llamadas"], r["archivos"]
                self.assertEqual(V.ARCHIVOS_BATERIA, (B.ARCHIVO_TABLA, B.ARCHIVO_RESULTADOS, B.ARCHIVO_CRITERIOS,
                                                      B.ARCHIVO_TIEMPO, B.ARCHIVO_REGISTRO_8F))
                self.assertEqual(r["codigo"], V.SALIDA_OK, r["stderr"])
                huellas = json.loads(archivos[V.ARCHIVO_HUELLAS])
                self.assertEqual(sorted(huellas), sorted(V.ARCHIVOS_C1))
                for nombre, sha in huellas.items():
                    self.assertEqual(entorno.sha256_bytes(archivos[nombre]), sha, nombre)
                tablas = [x for x in llamadas if x[0] == "tabla"]
                corridas = [x for x in llamadas if x[0] == "correr"]
                self.assertEqual(tablas, [("tabla", None)] + ([("tabla", 5)] if reduccion else []))
                # Medición (y, con reducción, la corrida de la tabla nueva) + la segunda iteración.
                self.assertEqual(corridas, [("correr", U0.huella())] * (2 if reduccion else 1) + [("correr", U1.huella())])
                self.assertEqual(r["resumen"]["bateria"]["corridas"], len(corridas))
                # Lo escribe bateria: criterios con «criterios» (BAT-12), tiempo con tope y reducción.
                self.assertEqual(archivos["criterios_bateria.json"],
                                 entorno.json_canonico(B.criterios_a_json(r["criterios"])))
                tiempo = json.loads(archivos["tiempo_bateria.json"])
                self.assertEqual((tiempo["horas"], tiempo["reduce_d2_d3_a"], tiempo["segundos_por_red"]),
                                 (horas, reduccion, {"sesgo0_r1": 1.5}))
                self.assertIn("tope_horas", tiempo)
                registro = archivos["registro_8F.jsonl"].decode("utf-8").splitlines()
                self.assertEqual([json.loads(x)["umbrales_sha256"] for x in registro], [U0.huella(), U1.huella()])
                self.assertEqual(json.loads(registro[0])["fecha_utc"], "2026-10-30T12:00:00Z")    # reloj inyectado
                self.assertIn("y", archivos["bateria_v1.csv"].decode("utf-8"))

    def test_como_script_delega_en_el_paquete(self):
        """VER-14: corrido como script, el ejecutable delega en reloj_dmc.verificar_reloj_dmc, así que el registro
        de --sintetico es el mismo que el de las pruebas y lo que ellas niegan no cuenta como acceso."""
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp).resolve()
            copia = raiz / AP.name / _RAIZ.name / PAQUETE.name               # Air-Pollution/scripts_modelo_1km/reloj_dmc
            (copia / "tests").mkdir(parents=True)
            for p in PAQUETE.glob("*.py"):
                shutil.copy2(p, copia / p.name)
            (copia / "tests" / "__init__.py").write_text("", encoding="utf-8")
            (copia / "tests" / "test_negada.py").write_text(PRUEBA_NEGADA_DENTRO, encoding="utf-8")
            salida = raiz / "salida"
            entorno_ = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
            r = subprocess.run([str(sys.executable), "-B", str(copia / "verificar_reloj_dmc.py"), "--sintetico",
                                "--salida", str(salida)], capture_output=True, env=entorno_, cwd=str(raiz),
                               timeout=600, check=False)
            self.assertEqual(r.returncode, V.SALIDA_FALLA, r.stderr.decode("utf-8", errors="replace")[-3000:])
            resumen = json.loads((salida / V.ARCHIVO_RESUMEN_C1).read_bytes())
            self.assertEqual(list(copia.rglob("__pycache__")), [])
        self.assertEqual((resumen["pruebas"]["corridas"], resumen["pruebas"]["aprobadas"]), (1, True))
        self.assertEqual((resumen["ceguera"]["accesos"], resumen["ceguera"]["negados_por_las_pruebas"]), (0, 2))
        self.assertEqual(resumen["motivos"], ["sin --bateria: falta el grupo D (§10, C1: «grupos A a D»)"])


if __name__ == "__main__":
    unittest.main()
