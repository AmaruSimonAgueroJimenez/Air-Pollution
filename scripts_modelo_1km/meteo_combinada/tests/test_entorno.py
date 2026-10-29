"""Pruebas de entorno.py (intérprete, rutas por alias, carpetas de salida e hilos; §8 del texto, §0 y §9.1 del diseño).

Dueño: I1 (ola 1; la carpeta de trabajo, ENT-9, en la ola 6). Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s meteo_combinada/tests -t .
Ninguna prueba abre /Volumes: las rutas bajo /Volumes se comprueban de forma léxica, con simulaciones o con un gancho
de auditoría en un intérprete aparte. Leen, sin escribir, el encabezado del texto vigente (los alias), el código de
``APH/scripts_neuro/_pesos.py`` (por AST) y ``config_v3.json``; si faltan, esas pruebas se omiten con el motivo y no
se dan por aprobadas. Las de subproceso corren el intérprete actual con -B -I y terminan antes de devolver.
"""
import sys

sys.dont_write_bytecode = True

import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import stat  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from dataclasses import fields  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from meteo_combinada import entorno  # noqa: E402
from reloj_dmc import entorno as entorno_reloj  # noqa: E402
from reloj_dmc import fijados as fijados_reloj  # noqa: E402

_RR = entorno.rutas_reales()
_TEXTO_VIGENTE = "auditoria/20261023/meteo_combinada/enmienda3/PROTOCOLO_METEO_COMBINADA_v2.4.md"   # v2.4 (Enmienda 3)
_SHA_TEXTO_VIGENTE = "eaedb10998e1a3f37f83f036c478afb5cf3fd3ccb5262477bd394dc220b1908b"
_SHA_PESOS_PY = "2f19fa53bc7893d5220fd19034277eb840d11c020d43a3f83769ad2f09b310ed"
_SHA_CONFIG_V3 = "ab248343239b58853d59516b1409d937e0b6a7ee36461c9df3b1eb7c09d17d94"
ARROBA = chr(64)
CARPETA_USUARIO = "/" + "Users" + "/"


def _subproceso(codigo: str, *, env: dict | None = None) -> str:
    """Corre ``codigo`` en un intérprete nuevo y aislado, con la raíz del paquete como argv[1]; la última línea."""
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run([sys.executable, "-B", "-I", "-c", codigo, str(_RAIZ)], cwd=tmp, capture_output=True,
                           text=True, timeout=120, check=False, env=env)
    if r.returncode != 0:
        raise AssertionError(f"El subproceso falló:\n{r.stderr}")
    return r.stdout.strip().splitlines()[-1]


def _leer_aph(ruta: str, sha256: str) -> bytes:
    p = _RR.aph / ruta
    if not p.is_file():
        raise unittest.SkipTest(f"falta APH/{ruta}; la prueba no se da por aprobada")
    datos = p.read_bytes()
    if hashlib.sha256(datos).hexdigest() != sha256:
        raise AssertionError(f"APH/{ruta} no tiene la huella esperada")
    return datos


class PruebasEntorno(unittest.TestCase):
    def test_reexportados_son_los_del_reloj(self):
        """§9.1 del diseño: el intérprete, las huellas y el JSON canónico son los mismos objetos de reloj_dmc.entorno;
        las prohibiciones y la escritura atómica son propias, con el mismo nombre y la misma firma (ENT-7)."""
        import inspect
        for nombre in entorno.REEXPORTADOS:
            with self.subTest(nombre=nombre):
                self.assertIs(getattr(entorno, nombre), getattr(entorno_reloj, nombre))
        for nombre in entorno.PROPIAS:
            with self.subTest(propia=nombre):
                self.assertIsNot(getattr(entorno, nombre), getattr(entorno_reloj, nombre))
                self.assertEqual(list(inspect.signature(getattr(entorno, nombre)).parameters),
                                 list(inspect.signature(getattr(entorno_reloj, nombre)).parameters))
        for nombre in ("PYTHON_FIJADO", "PANDAS_FIJADO", "NETCDF4_FIJADO", "TZDATA_FIJADO", "IANA_FIJADO", "INTERPRETE"):
            self.assertEqual(getattr(entorno, nombre), getattr(entorno_reloj, nombre))

    def test_interprete_fijado(self):
        """Python 3.11.16, pandas 2.3.3, netCDF4 1.7.4 y tzdata 2026.3 (IANA 2026c), el de RELOJ §9."""
        versiones = entorno.comprobar_interprete()
        self.assertEqual((versiones["python"], versiones["pandas"], versiones["netCDF4"], versiones["tzdata"],
                          versiones["iana"]), ("3.11.16", "2.3.3", "1.7.4", "2026.3", "2026c"))
        self.assertEqual(versiones["interprete"], "~/micromamba/envs/amb_v2/bin/python")

    def test_rutas_reales_con_los_13_alias(self):
        """AP, APH, LOCAL y DATOS, y bajo ellas DMC, ERA5L, NASADEM, INVARIANTES, GHS, SINCA_MET, GRILLA, PESOS y V3;
        sin consultar el disco. AP, APH, LOCAL, DMC y ERA5L son las mismas del reloj."""
        rr = _RR
        self.assertEqual([f.name for f in fields(entorno.Rutas)], list(entorno.ALIAS))
        self.assertEqual(len(entorno.ALIAS), 13)
        reloj = entorno_reloj.rutas_reales()
        self.assertEqual((rr.ap, rr.aph, rr.local, rr.dmc, rr.era5l),
                         (reloj.ap, reloj.aph, reloj.local, reloj.dmc, reloj.era5l))
        self.assertEqual(rr.ap, Path(entorno.__file__).resolve().parents[2])
        self.assertEqual(rr.datos, Path("/Volumes/Datos/Asesorias_Data/AirPollution/data"))
        esperadas = {
            "dmc": rr.datos / "meteorologia/estaciones_horarias/DMC",
            "era5l": rr.datos / "contaminantes/ERA5Land/chile_nativo_01deg",
            "nasadem": rr.datos / "contaminantes/Topografia/NASADEM_30m_native",
            "invariantes": rr.datos / "contaminantes/ERA5Land/invariantes",
            "ghs": rr.datos / "poblacion/ghs_pop_r2023a",
            "sinca_met": rr.datos / "sinca_meteorologia",
            "grilla": rr.local / "modelado_1km/grilla_1km",
            "pesos": rr.local / "neuro/poblacion",
            "v3": rr.local / "riesgo_agudo_v3/meteo_civil",
        }
        for campo, ruta in esperadas.items():
            self.assertEqual(getattr(rr, campo), ruta, campo)
        self.assertEqual(rr.salidas, rr.local / "meteo_combinada/v1")

    def test_alias_del_encabezado_del_texto(self):
        """Las rutas DMC, ERA5L y NASADEM son las del encabezado del texto vigente; LOCAL, la de «LOCAL =»."""
        texto = _leer_aph(_TEXTO_VIGENTE, _SHA_TEXTO_VIGENTE).decode("utf-8")
        encabezado = texto[texto.index("**Alias.**"):texto.index("## 0.")]
        for nombre, campo in (("DMC", "dmc"), ("ERA5L", "era5l"), ("NASADEM", "nasadem")):
            (ruta,) = re.findall(rf"{nombre} =\s*`([^`]+)`", encabezado)
            self.assertEqual(Path(ruta), getattr(_RR, campo), nombre)
        (local,) = re.findall(r"LOCAL =\s*`([^`]+)`", encabezado)
        self.assertEqual(Path(os.path.expanduser(local)), _RR.local)

    def test_pesos_es_la_carpeta_de_pesos_py(self):
        """ENT-2: PESOS es ``_pesos.SALIDA`` sin ``AIR_POLLUTION_LOCAL_ROOT`` (leído por AST, sin importar el módulo)."""
        _leer_aph("scripts_neuro/_pesos.py", _SHA_PESOS_PY)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AIR_POLLUTION_LOCAL_ROOT", None)
            ns = fijados_reloj.extraer_por_ast(_RR.aph / "scripts_neuro/_pesos.py", _SHA_PESOS_PY,
                                               ("LOCAL", "SALIDA", "PARQUET", "CELDAS"), {"Path": Path, "os": os})
        self.assertEqual(ns["SALIDA"], _RR.pesos)
        self.assertEqual(ns["PARQUET"].parent, _RR.pesos)
        self.assertEqual(ns["CELDAS"], _RR.grilla / "celdas.parquet")

    def test_v3_es_la_de_config_v3(self):
        """ENT-3: V3/civil, V3/utc4 y V3/regional son las carpetas de config_v3.json (con su alias LOCAL)."""
        config = json.loads(_leer_aph("scripts_riesgo_agudo/v3/config_v3.json", _SHA_CONFIG_V3).decode("utf-8"))
        productos = config["confusores"]["meteorologia_productos"]
        local_v3 = Path.home() / "Asesorias_Data_local"
        for tipo in ("civil", "utc4", "regional"):
            carpeta = productos[tipo]["carpeta"]
            self.assertTrue(carpeta.startswith("LOCAL/"), carpeta)
            self.assertEqual(local_v3 / carpeta.removeprefix("LOCAL/"), _RR.v3 / tipo, tipo)

    def test_alias_de_rutas_y_rechazos(self):
        """Gana el alias más profundo; léxico; otra ruta lanza ValueError."""
        rr = _RR
        casos = {
            rr.ap / "scripts_modelo_1km/v2/meteorologia_v2.py": "AP/scripts_modelo_1km/v2/meteorologia_v2.py",
            rr.aph / "auditoria/20261023": "APH/auditoria/20261023",
            rr.aph: "APH",
            rr.local / "meteo_combinada/v1/m1": "LOCAL/meteo_combinada/v1/m1",
            rr.local / "modelado_1km/grilla_1km/celdas.parquet": "GRILLA/celdas.parquet",
            rr.local / "neuro/poblacion/poblacion_celda_anio.parquet": "PESOS/poblacion_celda_anio.parquet",
            rr.local / "riesgo_agudo_v3/meteo_civil/civil": "V3/civil",
            rr.datos / "meteorologia/estaciones_horarias/DMC/progreso.json": "DMC/progreso.json",
            rr.datos / "contaminantes/ERA5Land/chile_nativo_01deg/catalogo_pixeles.parquet":
                "ERA5L/catalogo_pixeles.parquet",
            rr.datos / "contaminantes/ERA5Land/invariantes/x.nc": "INVARIANTES/x.nc",
            rr.datos / "contaminantes/ERA5Land": "DATOS/contaminantes/ERA5Land",
            rr.datos / "contaminantes/Topografia/NASADEM_30m_native/tiles": "NASADEM/tiles",
            rr.datos / "poblacion/ghs_pop_r2023a/E2020": "GHS/E2020",
            rr.datos / "sinca_meteorologia/manifiesto_descarga.csv": "SINCA_MET/manifiesto_descarga.csv",
            rr.ap / "a/../b/./c.txt": "AP/b/c.txt",
        }
        for ruta, esperado in casos.items():
            with self.subTest(ruta=esperado):
                texto = entorno.alias(ruta, rr)
                self.assertEqual(texto, esperado)
                self.assertTrue(entorno.sin_datos_privados(texto))
        rechazos = (Path("/etc/hosts"), Path("relativa/x.json"), rr.ap.parent / "Air-Pollution-Otro/x", rr.ap.parent,
                    rr.local / f"correo{ARROBA}dominio.txt", Path("/Volumes/Otro/x"), Path("/Volumes/Datos"))
        for ruta in rechazos:
            with self.subTest(rechazo=ruta.name), self.assertRaises(ValueError):
                entorno.alias(ruta, rr)

    def test_rutas_sinteticas(self):
        """ENT-6: las 13 carpetas bajo la temporal, con la anidación real; nada bajo /Volumes ni en los repositorios."""
        with tempfile.TemporaryDirectory() as tmp:
            rs = entorno.rutas_sinteticas(Path(tmp))
            raiz = Path(tmp).resolve()
            for f in fields(rs):
                ruta = getattr(rs, f.name)
                self.assertTrue(ruta.is_dir(), f.name)
                self.assertIn(raiz, ruta.parents, f.name)
            self.assertEqual(rs.dmc, rs.datos / "meteorologia/estaciones_horarias/DMC")
            self.assertEqual(rs.grilla, rs.local / "modelado_1km/grilla_1km")
            self.assertEqual(entorno.alias(rs.dmc / "estaciones/330020/2019-09.manifest.json", rs),
                             "DMC/estaciones/330020/2019-09.manifest.json")
            self.assertEqual(entorno.alias(rs.salidas / "m1/resumen_m1.json", rs), "LOCAL/meteo_combinada/v1/m1/resumen_m1.json")
            with self.assertRaises(ValueError):
                entorno.alias(_RR.ap / "x.py", rs)
        sin_disco = AssertionError("no debía tocar el disco")
        with mock.patch.object(Path, "mkdir", side_effect=sin_disco), mock.patch.object(Path, "resolve", side_effect=sin_disco):
            with self.assertRaises(PermissionError):
                entorno.rutas_sinteticas(Path("/Volumes/Datos/meteo_combinada_prueba"))
        dentro = _RR.ap / "meteo_combinada_raiz_que_no_debe_existir"
        with self.assertRaises(PermissionError):
            entorno.rutas_sinteticas(dentro)
        self.assertFalse(dentro.exists())
        with self.assertRaises(PermissionError):
            entorno.rutas_sinteticas(_RR.aph / "meteo_combinada_raiz_que_no_debe_existir")

    def test_rutas_sinteticas_sólo_bajo_la_carpeta_temporal(self):
        """B-H13 (ENT-6): una raíz fuera de tempfile.gettempdir(), o la carpeta temporal misma, se rechaza sin crear
        nada; LOCAL guarda datos reales con los mismos nombres."""
        temporal = Path(tempfile.gettempdir()).resolve()
        fuera = temporal.parent / "meteo_combinada_raiz_no_temporal_que_no_debe_existir"
        for raiz in (fuera, temporal, _RR.local / "meteo_combinada_raiz_no_temporal_que_no_debe_existir"):
            with self.subTest(raiz=raiz.name), self.assertRaises(PermissionError):
                entorno.rutas_sinteticas(raiz)
            self.assertFalse((raiz / "LOCAL").exists())
        self.assertFalse(fuera.exists())
        with tempfile.TemporaryDirectory() as tmp:        # un enlace que lleva fuera de la temporal también
            enlace = Path(tmp) / "fuera"
            enlace.symlink_to(fuera)
            with self.assertRaises(PermissionError):
                entorno.rutas_sinteticas(enlace / "raiz")
        self.assertFalse(fuera.exists())

    def test_carpeta_salida(self):
        """ENT-4: m1 y m2a con subcarpeta opcional; m34 y m5 en la carpeta HUMAN…; m6 en su subcarpeta m6."""
        rr = _RR
        base = rr.local / "meteo_combinada/v1"
        etiqueta = entorno.etiqueta_corrida("20261101")
        self.assertEqual(etiqueta, "HUMAN20261101_METEO_COMB_1")
        self.assertEqual(entorno.etiqueta_corrida("20261101", 2, errata=1), "HUMAN20261101_METEO_COMB_2_ERRATA1")
        self.assertEqual(entorno.carpeta_salida(rr, "m1"), base / "m1")
        self.assertEqual(entorno.carpeta_salida(rr, "m1", "costo"), base / "m1/costo")
        self.assertEqual(entorno.carpeta_salida(rr, "m2a"), base / "m2a")
        self.assertEqual(entorno.carpeta_salida(rr, "m34", etiqueta), base / etiqueta)
        self.assertEqual(entorno.carpeta_salida(rr, "m5", etiqueta), base / etiqueta)
        self.assertEqual(entorno.carpeta_salida(rr, "m6", etiqueta), base / etiqueta / "m6")
        for compuerta, malo in (("m34", None), ("m34", "HUMAN2026_METEO_COMB_1"), ("m6", "../HUMAN20261101_METEO_COMB_1"),
                                ("m5", "HUMAN20261101_METEO_COMB_0"), ("m1", ".."), ("m1", "a/b"), ("m3", None),
                                ("m34", "HUMAN20261399_METEO_COMB_1"), ("m34", "HUMAN20260230_METEO_COMB_1"),
                                ("m6", "HUMAN20261100_METEO_COMB_1_ERRATA1")):
            with self.subTest(compuerta=compuerta, etiqueta=malo), self.assertRaises(ValueError):
                entorno.carpeta_salida(rr, compuerta, malo)
        self.assertTrue(entorno.es_etiqueta_corrida("HUMAN20240229_METEO_COMB_1_ERRATA2"))     # bisiesto
        for texto in ("HUMAN20231399_METEO_COMB_1", "HUMAN20230229_METEO_COMB_1", None, 20261101):
            self.assertFalse(entorno.es_etiqueta_corrida(texto), texto)
        for etiqueta_mala in (("2026", 1), ("20261101", 0), ("20261399", 1), ("20261032", 1)):
            with self.assertRaises(ValueError):
                entorno.etiqueta_corrida(*etiqueta_mala)
        en_volumes = entorno.Rutas(**{**{f.name: getattr(rr, f.name) for f in fields(rr)},
                                      "local": Path("/Volumes/Datos/local")})
        sin_disco = AssertionError("no debía tocar el disco")
        with mock.patch.object(Path, "mkdir", side_effect=sin_disco), mock.patch("builtins.open", side_effect=sin_disco):
            with self.assertRaises(PermissionError):
                entorno.carpeta_salida(en_volumes, "m1")
        en_repo = entorno.Rutas(**{**{f.name: getattr(rr, f.name) for f in fields(rr)}, "local": rr.ap / "local"})
        with self.assertRaises(PermissionError):
            entorno.carpeta_salida(en_repo, "m1")
        self.assertFalse((rr.ap / "local").exists())

    def test_ninguna_ruta_toca_volumes(self):
        """rutas_reales, alias y carpeta_salida sobre las rutas reales no abren, listan ni crean nada bajo /Volumes
        (gancho de auditoría en un intérprete aparte)."""
        codigo = (
            "import json, os, sys\n"
            "accesos = []\n"
            "def gancho(evento, args):\n"
            "    if evento in ('open', 'os.listdir', 'os.scandir', 'glob.glob', 'os.mkdir', 'os.rename', 'os.remove'):\n"
            "        ruta = args[0] if args else None\n"
            "        if isinstance(ruta, (str, bytes, os.PathLike)):\n"
            "            if os.path.abspath(os.fsdecode(os.fspath(ruta))).casefold().startswith('/volumes'):\n"
            "                accesos.append(evento)\n"
            "sys.addaudithook(gancho)\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "from meteo_combinada import entorno\n"
            "rr = entorno.rutas_reales()\n"
            "nombres = [entorno.alias(rr.dmc / 'progreso.json', rr), entorno.alias(rr.era5l, rr),\n"
            "           entorno.alias(rr.sinca_met / 'x.csv', rr), str(entorno.carpeta_salida(rr, 'm1').name)]\n"
            "print(json.dumps({'accesos': accesos, 'nombres': nombres}))\n"
        )
        r = json.loads(_subproceso(codigo))
        self.assertEqual(r["accesos"], [])
        self.assertEqual(r["nombres"], ["DMC/progreso.json", "ERA5L", "SINCA_MET/x.csv", "m1"])


class PruebasGuardasSinVolumes(unittest.TestCase):
    """B-H8 (ENT-7): las guardas resuelven los enlaces componente a componente y nunca consultan /Volumes. Los enlaces
    se crean en carpetas temporales (crear un enlace no consulta su destino); un espía de os.lstat y os.readlink anota
    cada consulta y os.path.realpath no puede llamarse."""

    def _espiar(self):
        consultas = []
        lstat, readlink = os.lstat, os.readlink

        def espia_lstat(ruta, *a, **k):
            consultas.append(os.fspath(ruta))
            return lstat(ruta, *a, **k)

        def espia_readlink(ruta, *a, **k):
            consultas.append(os.fspath(ruta))
            return readlink(ruta, *a, **k)
        sin_realpath = AssertionError("no se debía resolver con os.path.realpath")
        parches = (mock.patch.object(os, "lstat", side_effect=espia_lstat),
                   mock.patch.object(os, "readlink", side_effect=espia_readlink),
                   mock.patch.object(os.path, "realpath", side_effect=sin_realpath))
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)
        return consultas

    def _ninguna_bajo_volumes(self, consultas):
        self.assertTrue(consultas, "el espía no vio ninguna consulta")
        self.assertEqual([c for c in consultas if Path(c).parts[1:2] and Path(c).parts[1].casefold() == "volumes"], [])

    def test_enlace_a_volumes_se_detecta_sin_consultarlo(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "absoluto").symlink_to("/Volumes/Datos/meteo_combinada_no_existe")
            (tmp / "relativo").symlink_to("../" * len(tmp.resolve().parts) + "Volumes/Datos")
            (tmp / "cadena").symlink_to("absoluto")
            (tmp / "mayusculas").symlink_to("/VOLUMES/Datos")
            local = tmp / "LOCAL"
            local.mkdir()
            consultas = self._espiar()
            for enlace in ("absoluto", "relativo", "cadena", "mayusculas"):
                with self.subTest(enlace=enlace):
                    with self.assertRaises(PermissionError):
                        entorno.prohibido_volumes(tmp / enlace / "sub/x.json")
                    entorno.prohibido_repositorios(tmp / enlace / "x.json")     # no es un repositorio
            self._ninguna_bajo_volumes(consultas)
            por_enlace = entorno.Rutas(**{**{f.name: getattr(_RR, f.name) for f in fields(_RR)},
                                          "local": tmp / "cadena"})
            with self.assertRaises(PermissionError):
                entorno.carpeta_salida(por_enlace, "m1")
            with self.assertRaises(PermissionError):
                entorno.escribir_atomico(tmp / "absoluto" / "x.json", b"x")
            self._ninguna_bajo_volumes(consultas)
            entorno.prohibido_volumes(local / "x.json")                       # una ruta temporal normal pasa
        self.assertEqual(entorno._resolver_seguro("/Volumes/Datos/x"), ("/Volumes/Datos/x", True))

    def test_enlace_a_un_repositorio_se_detecta(self):
        with tempfile.TemporaryDirectory() as tmp:
            enlace = Path(tmp) / "repo"
            enlace.symlink_to(_RR.ap)
            consultas = self._espiar()
            with self.assertRaises(PermissionError):
                entorno.prohibido_repositorios(enlace / "meteo_combinada_archivo_que_no_debe_existir.json")
            self._ninguna_bajo_volumes(consultas)
        self.assertFalse((_RR.ap / "meteo_combinada_archivo_que_no_debe_existir.json").exists())

    def test_escribir_atomico_escribe_en_una_temporal(self):
        """El envoltorio deja la escritura del reloj: «.part» y renombre, y devuelve el sha256."""
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "a" / "b.json"
            sha = entorno.escribir_atomico(ruta, b"{}")
            self.assertEqual(sha, hashlib.sha256(b"{}").hexdigest())
            self.assertEqual(ruta.read_bytes(), b"{}")
            self.assertEqual(sorted(p.name for p in ruta.parent.iterdir()), ["b.json"])
            with self.assertRaises(TypeError):
                entorno.escribir_atomico(ruta, "texto")

    def test_demasiados_enlaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            bucle = Path(tmp) / "bucle"
            bucle.symlink_to("bucle")
            with self.assertRaises(OSError):
                entorno.prohibido_volumes(bucle / "x")


class PruebasCarpetaDeTrabajo(unittest.TestCase):
    """ENT-9: la carpeta de trabajo temporal de costo.medir y de la batería (PED-3 de I22, PED-4 de I21)."""

    PREFIJO = "meteo_combinada_prueba_"

    def _temporal(self) -> Path:
        return Path(entorno._resolver_seguro(tempfile.gettempdir())[0])

    def test_crea_y_borra(self):
        """Crea una carpeta nueva (0700) directamente bajo la temporal del sistema resuelta, con el prefijo, y al salir la
        borra entera, con subcarpetas y archivos."""
        with entorno.carpeta_de_trabajo(self.PREFIJO) as c:
            self.assertIsInstance(c, Path)
            self.assertTrue(c.is_dir() and not c.is_symlink())
            self.assertEqual(c.parent, self._temporal())
            self.assertTrue(c.name.startswith(self.PREFIJO) and len(c.name) > len(self.PREFIJO))
            self.assertEqual(stat.S_IMODE(os.lstat(c).st_mode), 0o700)
            (c / "sub" / "hondo").mkdir(parents=True)
            (c / "sub" / "hondo" / "x.bin").write_bytes(b"x")
            (c / "y.json").write_text("{}", encoding="utf-8")
        self.assertFalse(c.exists())
        with entorno.carpeta_de_trabajo() as d, entorno.carpeta_de_trabajo(self.PREFIJO) as e:
            self.assertTrue(d.name.startswith(entorno.PREFIJO_TRABAJO))
            self.assertNotEqual(d, e)
        self.assertFalse(d.exists() or e.exists())

    def test_borra_con_una_excepcion(self):
        """La excepción del cuerpo se propaga y la carpeta queda borrada."""
        with self.assertRaisesRegex(ValueError, "falla del cuerpo"):
            with entorno.carpeta_de_trabajo(self.PREFIJO) as c:
                (c / "a.txt").write_text("a", encoding="utf-8")
                raise ValueError("falla del cuerpo")
        self.assertFalse(c.exists())

    def test_enlaces_adentro_no_borran_su_destino(self):
        """Enlaces adentro hacia otra carpeta temporal, un archivo y una subcarpeta de ella, /Volumes y AP: se borran como
        enlaces y su destino queda intacto. Bajo ceguera.RegistroAccesos en bloqueo sobre /Volumes, ningún acceso."""
        from meteo_combinada import ceguera
        volumes = "/" + "Volumes"
        meteo = _RR.ap / "scripts_modelo_1km" / "meteo_combinada"
        with tempfile.TemporaryDirectory() as otra_tmp:
            otra = Path(otra_tmp)
            (otra / "importante.txt").write_bytes(b"no se borra")
            (otra / "sub").mkdir()
            (otra / "sub" / "dentro.txt").write_bytes(b"tampoco")
            with ceguera.RegistroAccesos((volumes,), bloquear=True) as registro:
                with entorno.carpeta_de_trabajo(self.PREFIJO) as c:
                    (c / "hondo").mkdir()
                    (c / "a_otra").symlink_to(otra, target_is_directory=True)
                    (c / "hondo" / "a_archivo").symlink_to(otra / "importante.txt")
                    (c / "hondo" / "a_sub").symlink_to(otra / "sub", target_is_directory=True)
                    (c / "a_volumes").symlink_to(volumes + "/Datos/meteo_combinada_no_existe")
                    (c / "hondo" / "a_ap").symlink_to(meteo, target_is_directory=True)
            self.assertEqual(registro.accesos, [])
            self.assertFalse(c.exists() or c.is_symlink())
            self.assertEqual((otra / "importante.txt").read_bytes(), b"no se borra")
            self.assertEqual((otra / "sub" / "dentro.txt").read_bytes(), b"tampoco")
        self.assertTrue((meteo / "entorno.py").is_file())

    def test_carpeta_movida_o_reemplazada_no_se_borra(self):
        """Movida, reemplazada por un enlace o por otra carpeta: PermissionError al salir y no se borra nada; la movida
        queda donde la movieron y el enlace sigue apuntando a ella."""
        esperado = {"movida": "ya no está donde se creó", "enlace": "pasó a ser un enlace",
                    "otra carpeta": "hay otra cosa"}
        with tempfile.TemporaryDirectory() as tmp:
            for caso, mensaje in esperado.items():
                with self.subTest(caso=caso):
                    lejos = Path(tmp) / caso.replace(" ", "_")
                    with self.assertRaisesRegex(PermissionError, mensaje):
                        with entorno.carpeta_de_trabajo(self.PREFIJO) as c:
                            (c / "dato.txt").write_text(caso, encoding="utf-8")
                            os.rename(c, lejos)
                            if caso == "enlace":
                                c.symlink_to(lejos, target_is_directory=True)
                            elif caso == "otra carpeta":
                                c.mkdir()
                                (c / "ajeno.txt").write_text("ajeno", encoding="utf-8")
                    self.assertEqual((lejos / "dato.txt").read_text(encoding="utf-8"), caso)
                    if caso == "enlace":
                        self.assertTrue(c.is_symlink())
                        self.assertEqual(os.readlink(c), str(lejos))
                        c.unlink()
                    elif caso == "otra carpeta":
                        self.assertEqual((c / "ajeno.txt").read_text(encoding="utf-8"), "ajeno")
                        shutil.rmtree(c)
                    else:
                        self.assertFalse(c.exists())

    def test_se_niega_a_borrar_fuera_de_la_temporal(self):
        """La guarda de borrado: AP, LOCAL, /Volumes, la temporal misma o una ruta que lleva a AP por un enlace en la
        temporal se rechazan con PermissionError, sin borrar ni consultar /Volumes."""
        from meteo_combinada import ceguera
        meteo = _RR.ap / "scripts_modelo_1km" / "meteo_combinada"
        identidad = entorno._identidad(os.lstat(meteo))
        temporal = self._temporal()
        fuera = "no está bajo la carpeta temporal del sistema: no se borra"
        with tempfile.TemporaryDirectory() as tmp:
            puente = Path(tmp).resolve() / "puente"               # resuelta: la guarda léxica la deja pasar
            self.assertIn(temporal, puente.parents)
            puente.symlink_to(meteo.parent, target_is_directory=True)
            casos = {"AP": (meteo, identidad, fuera),
                     "la temporal misma": (temporal, entorno._identidad(os.lstat(temporal)), fuera),
                     "por un enlace a AP": (puente / meteo.name, identidad, "lleva fuera por un enlace"),
                     "LOCAL": (_RR.local / "meteo_combinada_no_existe", (0, 0), fuera),
                     "/Volumes": (Path("/" + "Volumes/Datos/meteo_combinada_no_existe"), (0, 0),
                                  "cae bajo /Volumes: no se borra")}
            with ceguera.RegistroAccesos(("/" + "Volumes",), bloquear=True) as registro:
                for nombre, (ruta, ident, mensaje) in casos.items():
                    with self.subTest(caso=nombre), self.assertRaisesRegex(PermissionError, mensaje):
                        entorno._borrar_carpeta_de_trabajo(ruta, ident)
            self.assertEqual(registro.accesos, [])
            self.assertTrue(puente.is_symlink())
        self.assertTrue((meteo / "entorno.py").is_file())

    def test_prefijo_invalido_y_rmtree_que_seguiria_enlaces(self):
        """Un prefijo que no es un nombre simple se rechaza sin crear nada; si shutil.rmtree pudiera seguir enlaces, no se
        borra (RuntimeError) y la carpeta queda."""
        for malo in ("", "../fuera", "a/b", ".oculto", "-x", "con espacio", None, 3):
            with self.subTest(prefijo=malo), self.assertRaises(ValueError):
                with entorno.carpeta_de_trabajo(malo):
                    self.fail("no debía crear la carpeta")
        with mock.patch.object(shutil.rmtree, "avoids_symlink_attacks", False):
            with self.assertRaisesRegex(RuntimeError, "podría seguir enlaces"):
                with entorno.carpeta_de_trabajo(self.PREFIJO) as c:
                    pass
        self.assertTrue(c.is_dir())
        shutil.rmtree(c)

    def test_nada_consulta_volumes_ni_los_repositorios(self):
        """En un intérprete nuevo con el directorio en la temporal (VER-18 de ceguera): crear, usar y borrar la carpeta
        con enlaces adentro hacia /Volumes y AP, bajo ceguera.RegistroAccesos en bloqueo sobre /Volumes, AP y APH, no
        da ningún acceso. Con TMPDIR bajo /Volumes, directa o por un enlace, se niega sin consultar /Volumes (gancho
        de auditoría)."""
        codigo = (
            "import json, os, sys, tempfile\n"
            "accesos = []\n"
            "def gancho(evento, args):\n"
            "    if evento in ('open', 'os.listdir', 'os.scandir', 'glob.glob', 'os.mkdir', 'os.rename', 'os.remove',\n"
            "                  'os.rmdir', 'shutil.rmtree'):\n"
            "        ruta = args[0] if args else None\n"
            "        if isinstance(ruta, (str, bytes, os.PathLike)):\n"
            "            if os.path.abspath(os.fsdecode(os.fspath(ruta))).casefold().startswith('/volumes'):\n"
            "                accesos.append(evento)\n"
            "sys.addaudithook(gancho)\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "from pathlib import Path\n"
            "previa = tempfile.tempdir\n"
            "from meteo_combinada import ceguera, entorno\n"
            "rr = entorno.rutas_reales()\n"
            "if os.environ.get('MODO') == 'tmpdir':\n"
            "    try:\n"
            "        with entorno.carpeta_de_trabajo('meteo_combinada_prueba_'):\n"
            "            r = 'creada'\n"
            "    except PermissionError:\n"
            "        r = 'negada'\n"
            "    print(json.dumps({'accesos': accesos, 'r': r, 'previa': previa, 'tempdir': tempfile.tempdir}))\n"
            "else:\n"
            "    os.chdir(tempfile.gettempdir())\n"
            "    meteo = rr.ap / 'scripts_modelo_1km' / 'meteo_combinada'\n"
            "    with ceguera.RegistroAccesos(('/' + 'Volumes', rr.ap, rr.aph), bloquear=True) as registro:\n"
            "        with entorno.carpeta_de_trabajo('meteo_combinada_prueba_') as c:\n"
            "            (c / 'a_volumes').symlink_to('/' + 'Volumes/Datos/meteo_combinada_no_existe')\n"
            "            (c / 'sub').mkdir()\n"
            "            (c / 'sub' / 'a_ap').symlink_to(meteo, target_is_directory=True)\n"
            "            (c / 'sub' / 'x.txt').write_text('x')\n"
            "    print(json.dumps({'accesos': accesos, 'registro': len(registro.accesos), 'borrada': not c.exists(),\n"
            "                      'intacto': (meteo / 'entorno.py').is_file()}))\n")
        r = json.loads(_subproceso(codigo))
        self.assertEqual(r, {"accesos": [], "registro": 0, "borrada": True, "intacto": True})
        with tempfile.TemporaryDirectory() as tmp:
            enlace = Path(tmp) / "tmp_a_volumes"
            enlace.symlink_to("/" + "Volumes/Datos/meteo_combinada_no_existe")
            for tmpdir in ("/" + "Volumes/Datos/meteo_combinada_no_existe", str(enlace)):
                with self.subTest(tmpdir="enlace" if tmpdir == str(enlace) else "directa"):
                    r = json.loads(_subproceso(codigo, env={**os.environ, "MODO": "tmpdir", "TMPDIR": tmpdir}))
                    self.assertEqual(r, {"accesos": [], "r": "negada", "previa": None, "tempdir": None})


class PruebasHilos(unittest.TestCase):
    def test_fijar_hilos_sin_numpy_cargado(self):
        """MC-36: con el paquete importado antes que numpy, las variables quedan en 1 y threadpoolctl lo confirma."""
        codigo = ("import json, os, sys; sys.path.insert(0, sys.argv[1]); "
                  "from meteo_combinada import entorno; r = entorno.fijar_hilos(); "
                  "print(json.dumps(r))")
        r = json.loads(_subproceso(codigo, env={**os.environ, "OMP_NUM_THREADS": "4", "OPENBLAS_NUM_THREADS": "4",
                                                "MKL_NUM_THREADS": "4"}))
        self.assertEqual(r["variables"], {v: "1" for v in entorno.VARIABLES_HILOS})
        self.assertTrue(r["bibliotecas"])
        self.assertTrue(all(b["hilos"] == 1 for b in r["bibliotecas"]), r["bibliotecas"])

    def test_fijar_hilos_con_numpy_ya_cargado(self):
        """Si numpy se cargó con 4 hilos, fijar_hilos los baja a 1 con threadpoolctl y deja las variables en 1."""
        codigo = ("import json, os, sys; import numpy; import threadpoolctl; sys.path.insert(0, sys.argv[1]); "
                  "antes = [b['num_threads'] for b in threadpoolctl.threadpool_info() if b['user_api'] == 'blas']; "
                  "from meteo_combinada import entorno; r = entorno.fijar_hilos(); r['antes'] = antes; "
                  "print(json.dumps(r))")
        r = json.loads(_subproceso(codigo, env={**os.environ, "OMP_NUM_THREADS": "4", "OPENBLAS_NUM_THREADS": "4",
                                                "MKL_NUM_THREADS": "4"}))
        self.assertIn(4, r["antes"])
        self.assertEqual(r["variables"], {v: "1" for v in entorno.VARIABLES_HILOS})
        self.assertTrue(all(b["hilos"] == 1 for b in r["bibliotecas"]), r["bibliotecas"])

    def test_fijar_hilos_falla_si_no_quedan_en_1(self):
        import threadpoolctl
        falsa = [{"user_api": "blas", "internal_api": "openblas", "num_threads": 2}]
        with mock.patch.object(threadpoolctl, "threadpool_info", return_value=falsa):
            with self.assertRaises(RuntimeError):
                entorno.fijar_hilos()
        self.assertEqual(entorno.fijar_hilos()["variables"], {v: "1" for v in entorno.VARIABLES_HILOS})


class PruebasPrivacidad(unittest.TestCase):
    def test_sin_datos_privados(self):
        """§8 del texto, «Publicación»: ni la carpeta de usuario ni la arroba."""
        self.assertTrue(entorno.sin_datos_privados("LOCAL/meteo_combinada/v1/m1/resumen_m1.json"))
        self.assertFalse(entorno.sin_datos_privados(CARPETA_USUARIO + "alguien/x"))
        self.assertFalse(entorno.sin_datos_privados(f"autor{ARROBA}dominio"))
        self.assertFalse(entorno.sin_datos_privados(str(Path.home() / "x")))


if __name__ == "__main__":
    unittest.main()
