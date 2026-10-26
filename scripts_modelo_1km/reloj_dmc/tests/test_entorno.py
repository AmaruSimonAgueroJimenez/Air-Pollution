"""Pruebas de entorno.py (intérprete, rutas por alias y escritura).

Esqueleto de C1: cada prueba nombra lo que debe comprobar.
Las que llevan «pNN» son el punto NN de §8 (grupos A, B y C). Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s reloj_dmc/tests -t .
Ninguna prueba abre /Volumes: las rutas bajo /Volumes se comprueban de forma léxica o con simulaciones.
Las de subproceso corren el intérprete actual con -I y terminan antes de devolver.
"""
import sys

sys.dont_write_bytecode = True

import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
import zoneinfo  # noqa: E402
from pathlib import Path  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from unittest import mock  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from reloj_dmc import entorno  # noqa: E402,F401

_PAQUETE = _RAIZ / "reloj_dmc"


def _subproceso(codigo: str, *opciones: str, cwd: Path) -> str:
    """Corre ``codigo`` en un intérprete nuevo, aislado (-I), con la raíz del paquete como argv[1]."""
    r = subprocess.run([sys.executable, "-I", *opciones, "-c", codigo, str(_RAIZ)], cwd=cwd,
                       capture_output=True, text=True, timeout=120, check=False)
    if r.returncode != 0:
        raise AssertionError(f"El subproceso falló:\n{r.stderr}")
    return r.stdout.strip().splitlines()[-1]


class PruebasEntorno(unittest.TestCase):
    def test_interprete_fijado(self):
        """Python 3.11.16, pandas 2.3.3, netCDF4 1.7.4, tzdata 2026.3 (IANA 2026c)."""
        versiones = entorno.comprobar_interprete()
        self.assertEqual(versiones["python"], "3.11.16")
        self.assertEqual(versiones["pandas"], "2.3.3")
        self.assertEqual(versiones["netCDF4"], "1.7.4")
        self.assertEqual(versiones["tzdata"], "2026.3")
        self.assertEqual(versiones["iana"], "2026c")
        self.assertEqual(versiones["interprete"], "~/micromamba/envs/amb_v2/bin/python")
        self.assertTrue(all(entorno.sin_datos_privados(v) for v in versiones.values()))
        reales = entorno._versiones_instaladas()
        for nombre, otro in (("python", "3.11.15"), ("pandas", "2.3.2"), ("netCDF4", "1.7.3"),
                             ("tzdata", "2026.2"), ("iana", "2026b")):
            with self.subTest(version_distinta=nombre), \
                    mock.patch.object(entorno, "_versiones_instaladas", return_value={**reales, nombre: otro}):
                with self.assertRaises(RuntimeError):
                    entorno.comprobar_interprete()
        # Se reemplaza sólo el nombre «sys» dentro de entorno, nunca el módulo sys del proceso.
        procesos = {
            "otro_ejecutable": SimpleNamespace(executable="/usr/bin/false", dont_write_bytecode=True,
                                               flags=SimpleNamespace(dont_write_bytecode=1)),
            "escribe_bytecode": SimpleNamespace(executable=sys.executable, dont_write_bytecode=False,
                                                flags=SimpleNamespace(dont_write_bytecode=0)),
        }
        for nombre, proceso in procesos.items():
            with self.subTest(proceso=nombre), mock.patch.object(entorno, "sys", proceso):
                with self.assertRaises(RuntimeError):
                    entorno.comprobar_interprete()
        if os.path.isdir(entorno.BASE_ZONAS_SISTEMA):
            with self.subTest(zonas="sistema"):
                try:
                    entorno.reiniciar_zonas("sistema")
                    with self.assertRaises(RuntimeError):
                        entorno.comprobar_interprete()
                finally:
                    entorno.reiniciar_zonas("tzdata")
        self.assertEqual(entorno.comprobar_interprete()["python"], "3.11.16")

    def test_tzpath_solo_paquete_tzdata(self):
        """Tras importar, zoneinfo.TZPATH == () y la caché fue limpiada."""
        self.assertEqual(zoneinfo.TZPATH, ())
        codigo = (
            "import json, sys, zoneinfo\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "antes = list(zoneinfo.TZPATH)\n"
            "a = zoneinfo.ZoneInfo('America/Santiago')\n"
            "from reloj_dmc import entorno\n"
            "b = zoneinfo.ZoneInfo('America/Santiago')\n"
            "print(json.dumps({'antes': antes, 'despues': list(zoneinfo.TZPATH), 'misma': a is b}))\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            r = json.loads(_subproceso(codigo, "-B", cwd=Path(tmp)))
        self.assertNotEqual(r["antes"], [], "el intérprete trae una TZPATH propia que hay que anular")
        self.assertEqual(r["despues"], [])
        self.assertFalse(r["misma"], "la caché de ZoneInfo no se limpió al importar")

    def test_dont_write_bytecode(self):
        """sys.dont_write_bytecode es True al importar el paquete."""
        self.assertTrue(sys.dont_write_bytecode)
        # Intérprete sin -B y con el bytecode desviado a una carpeta temporal (nunca al repositorio):
        # el paquete debe fijar la bandera antes de compilar sus submódulos.
        codigo = (
            "import json, sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "inicial = [sys.flags.dont_write_bytecode, sys.dont_write_bytecode]\n"
            "import reloj_dmc.entorno\n"
            "print(json.dumps(inicial + [sys.dont_write_bytecode]))\n"
        )
        cache_paquete = _PAQUETE / "__pycache__"
        habia_cache = cache_paquete.exists()
        with tempfile.TemporaryDirectory() as tmp:
            prefijo = Path(tmp) / "pyc"
            r = json.loads(_subproceso(codigo, "-X", f"pycache_prefix={prefijo}", cwd=Path(tmp)))
            compilados = [p.name for p in prefijo.rglob("*.pyc") if "reloj_dmc" in p.parts]
        self.assertEqual(r, [0, False, True])
        # __init__ se compila antes de fijar la bandera (prueba que la desviación funcionó); entorno no.
        self.assertTrue([n for n in compilados if n.startswith("__init__.")], compilados)
        self.assertFalse([n for n in compilados if n.startswith("entorno.")], compilados)
        self.assertEqual(cache_paquete.exists(), habia_cache)

    def test_alias_de_rutas_y_rechazo_de_rutas_sin_alias(self):
        """AP/APH/LOCAL/DMC/ERA5L; otra ruta lanza ValueError."""
        rr = entorno.rutas_reales()
        self.assertEqual(rr.ap, Path(entorno.__file__).resolve().parents[2])
        self.assertEqual(rr.ap.name, "Air-Pollution")
        self.assertEqual(rr.aph, rr.ap.parent / "Air-Pollution-Health-Chile")
        self.assertEqual(rr.local, Path.home() / "Asesorias_Data_local/AirPollution")
        self.assertEqual(rr.dmc, Path("/Volumes/Datos/Asesorias_Data/AirPollution/data/meteorologia/"
                                      "estaciones_horarias/DMC"))
        self.assertEqual(rr.era5l, Path("/Volumes/Datos/Asesorias_Data/AirPollution/data/contaminantes/"
                                        "ERA5Land/chile_nativo_01deg"))
        self.assertEqual(rr.corridas, rr.local / "modelado_1km/verificacion_reloj_dmc/v1")
        casos = {
            rr.ap / "scripts_modelo_1km/v2/meteorologia_v2.py": "AP/scripts_modelo_1km/v2/meteorologia_v2.py",
            rr.aph / "auditoria/20261023": "APH/auditoria/20261023",
            rr.aph: "APH",
            rr.local / "modelado_1km": "LOCAL/modelado_1km",
            rr.dmc / "progreso.json": "DMC/progreso.json",
            rr.era5l / "catalogo_pixeles.parquet": "ERA5L/catalogo_pixeles.parquet",
            rr.ap / "a/../b/./c.txt": "AP/b/c.txt",
        }
        for ruta, esperado in casos.items():
            with self.subTest(ruta=esperado):
                texto = entorno.alias(ruta, rr)
                self.assertEqual(texto, esperado)
                self.assertTrue(entorno.sin_datos_privados(texto))
        rechazos = (Path("/etc/hosts"), Path("relativa/x.json"), rr.ap.parent / "Air-Pollution-Otro/x",
                    rr.ap.parent, rr.local / "correo@dominio.txt", Path("/Volumes/Otro/x"))
        for ruta in rechazos:
            with self.subTest(rechazo=ruta.name), self.assertRaises(ValueError):
                entorno.alias(ruta, rr)
        with tempfile.TemporaryDirectory() as tmp:
            rs = entorno.rutas_sinteticas(Path(tmp))
            for nombre in ("ap", "aph", "local", "dmc", "era5l"):
                self.assertTrue(getattr(rs, nombre).is_dir())
                self.assertEqual(getattr(rs, nombre).parent, Path(tmp).resolve())
            self.assertEqual(entorno.alias(rs.dmc / "estaciones/330020/2019-09.manifest.json", rs),
                             "DMC/estaciones/330020/2019-09.manifest.json")
            self.assertEqual(entorno.alias(rs.corridas / "intentos_aplicar.jsonl", rs),
                             "LOCAL/modelado_1km/verificacion_reloj_dmc/v1/intentos_aplicar.jsonl")
            with self.assertRaises(ValueError):
                entorno.alias(rr.ap / "x.py", rs)
        with self.assertRaises(PermissionError):
            entorno.rutas_sinteticas(Path("/Volumes/Datos/reloj_dmc_prueba"))
        dentro = rr.ap / "reloj_dmc_raiz_que_no_debe_existir"
        with self.assertRaises(PermissionError):
            entorno.rutas_sinteticas(dentro)
        self.assertFalse(dentro.exists())

    def test_escritura_atomica_y_prohibicion_de_volumes(self):
        """«.part» + rename; nada bajo /Volumes."""
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "sub" / "dir" / "tabla.json"
            datos = entorno.json_canonico({"a": 1})
            sha = entorno.escribir_atomico(ruta, datos)
            self.assertEqual(sha, hashlib.sha256(datos).hexdigest())
            self.assertEqual(ruta.read_bytes(), datos)
            self.assertEqual(sorted(p.name for p in ruta.parent.iterdir()), ["tabla.json"])
            sha2 = entorno.escribir_atomico(ruta, b"otro")
            self.assertEqual((ruta.read_bytes(), sha2), (b"otro", hashlib.sha256(b"otro").hexdigest()))
            # Un fallo al renombrar no deja «.part» ni toca el destino.
            with mock.patch.object(entorno.os, "replace", side_effect=OSError("simulado")):
                with self.assertRaises(OSError):
                    entorno.escribir_atomico(ruta, b"tercero")
            self.assertEqual(ruta.read_bytes(), b"otro")
            self.assertEqual(sorted(p.name for p in ruta.parent.iterdir()), ["tabla.json"])
            with self.assertRaises(TypeError):
                entorno.escribir_atomico(ruta, "texto")  # type: ignore[arg-type]
            # Un enlace que lleva a /Volumes (simulado, sin consultar /Volumes).
            enlace = Path(tmp) / "enlace"
            with mock.patch.object(entorno.os.path, "realpath", return_value="/Volumes/Datos/x"):
                with self.assertRaises(PermissionError):
                    entorno.prohibido_volumes(enlace)
        for ruta in ("/Volumes/Datos/x.json", "/volumes/Datos/x.json", "/Volumes", "/Volumes/../Volumes/x"):
            with self.subTest(ruta=ruta), self.assertRaises(PermissionError):
                entorno.prohibido_volumes(Path(ruta))
        entorno.prohibido_volumes(Path("/private/tmp/x"))
        # La negativa ocurre antes de crear carpetas o abrir archivos.
        sin_disco = AssertionError("no debía tocar el disco")
        with mock.patch("builtins.open", side_effect=sin_disco), \
                mock.patch.object(Path, "mkdir", side_effect=sin_disco), \
                mock.patch.object(entorno.os, "replace", side_effect=sin_disco):
            with self.assertRaises(PermissionError):
                entorno.escribir_atomico(Path("/Volumes/Datos/reloj_dmc_prueba.json"), b"x")
        repo = entorno.rutas_reales().ap / "reloj_dmc_archivo_que_no_debe_existir.json"
        with self.assertRaises(PermissionError):
            entorno.escribir_atomico(repo, b"x")
        self.assertFalse(repo.exists())

    def test_json_canonico(self):
        """Claves ordenadas, separadores «,» «:», allow_nan=False, sin salto final."""
        texto = entorno.json_canonico({"b": 1, "a": [1.5, "ñ", None, True], "c": {"z": 0, "y": "°"}})
        self.assertEqual(texto, '{"a":[1.5,"ñ",null,true],"b":1,"c":{"y":"°","z":0}}'.encode("utf-8"))
        self.assertFalse(texto.endswith(b"\n"))
        for malo in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(valor=malo), self.assertRaises(ValueError):
                entorno.json_canonico({"x": malo})
        with self.assertRaises(TypeError):
            entorno.json_canonico({"x": Path("/tmp")})

    def test_sha256_archivo_en_bloques(self):
        """El sha256 de un archivo de más de un bloque coincide con el de sus bytes."""
        datos = os.urandom((1 << 20) * 2 + 17)
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "x.bin"
            ruta.write_bytes(datos)
            self.assertEqual(entorno.sha256_archivo(ruta), hashlib.sha256(datos).hexdigest())
        self.assertEqual(entorno.sha256_bytes(b""), hashlib.sha256(b"").hexdigest())

    def test_sin_datos_privados(self):
        """§7.4: ni «/Users/» ni «@»."""
        self.assertTrue(entorno.sin_datos_privados("AP/config/meteorologia/reloj_dmc/v1/informe.json"))
        self.assertFalse(entorno.sin_datos_privados("/Users/alguien/x"))
        self.assertFalse(entorno.sin_datos_privados("autor@dominio"))
        self.assertFalse(entorno.sin_datos_privados(str(Path.home() / "x")))

    def test_reiniciar_zonas(self):
        """«tzdata» deja sólo el paquete; «sistema», la base del sistema; otra base es un error."""
        try:
            if os.path.isdir(entorno.BASE_ZONAS_SISTEMA):
                entorno.reiniciar_zonas("sistema")
                self.assertEqual(zoneinfo.TZPATH, (entorno.BASE_ZONAS_SISTEMA,))
                self.assertEqual(str(zoneinfo.ZoneInfo("America/Santiago")), "America/Santiago")
            with self.assertRaises(ValueError):
                entorno.reiniciar_zonas("conda")
        finally:
            entorno.reiniciar_zonas()
        self.assertEqual(zoneinfo.TZPATH, ())


if __name__ == "__main__":
    unittest.main()
