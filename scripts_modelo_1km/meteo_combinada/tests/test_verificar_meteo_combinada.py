"""Pruebas de verificar_meteo_combinada.py (§8, §10 y Anexo B): S2 (``--aplicar``), S16 (negativas de M6 e
``intentos_m6.jsonl``), las negativas de §10 y el contenido del addendum, el cerrojo y su cotejo con las carpetas, la
carpeta ``HUMAN<AAAAMMDD>_METEO_COMB_1``, la consola, las excepciones y la batería (FIJ-3, ``pruebas_m1.txt``, S14,
omisiones, subcarpeta).

Dueño: I22 (ola 6; corregido tras la revisión independiente). Las que llevan «sNN» son la prueba NN de §9 del texto.
Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s meteo_combinada/tests -t .
Todo en carpetas temporales (``entorno.rutas_sinteticas``): AP y APH son repositorios git fabricados aquí, con un
«origin» desnudo en la misma carpeta temporal, y llevan una copia de lo que exige la lista cerrada del addendum (los
textos y las decisiones anclados, el código y los documentos del paquete, el código fijado y la clausura del reloj:
sólo código y textos, copiados una vez por proceso); la política y el registro de C5 son los de
``sintetico.politica_reloj_sintetica``; el addendum se arma con las funciones de ``addendum``; las entradas, el
registro de la red v2, la errata, la salida de la batería y la corrida de M5 publicada son archivos hechos a mano. Las
corridas de ``orquestacion`` se reemplazan por funciones que cruzan la frontera (``avance.iniciar()``) y sellan,
abortan, se niegan, fallan o se detienen por una alarma. ``micromamba list`` corre una vez (FIJ-3). Ninguna prueba abre
DMC, datos reales, la política publicada del reloj ni sus corridas, y ninguna escribe en un repositorio real.
"""
import sys

sys.dont_write_bytecode = True

import contextlib  # noqa: E402
import functools  # noqa: E402
import hashlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from meteo_combinada import addendum, ceguera, entorno, fijados, orquestacion, salidas, sintetico  # noqa: E402
from meteo_combinada import constantes, umbrales  # noqa: E402
from meteo_combinada import verificar_meteo_combinada as V  # noqa: E402

_REALES = entorno.rutas_reales()
_AHORA = datetime(2026, 10, 28, 15, 0, tzinfo=timezone.utc)
_MANANA = datetime(2026, 10, 29, 15, 0, tzinfo=timezone.utc)
_PASADO = datetime(2026, 10, 30, 15, 0, tzinfo=timezone.utc)
_ETIQUETA = "HUMAN20261028_METEO_COMB_1"
_SUB = "20261028T120000Z"
_M1 = f"{addendum.PREFIJO_M1}{_SUB}"
_PAQ = f"AP/{addendum.CARPETA_PAQUETE}"
_CODIGO = f"{_PAQ}/x.py"
_ADDENDUM = "APH/auditoria/20261028/meteo_combinada/m1/addendum_m1.json"
_ENTRADAS = "APH/auditoria/20261028/meteo_combinada/entradas_{}.json"
_REGISTRO_RED = "APH/auditoria/20261028/sinca_al_modelo/registro_red_v2.json"
_ERRATA = "APH/auditoria/20261029/meteo_combinada/errata_1.json"
_CIERRE_C2 = "APH/auditoria/20261027/reloj_dmc/cierre_descarga.json"
_PLIEGUES = "DATOS/red2/pliegues_v2_red2.json"
_PANELES = {"pm25": "DATOS/red2/paneles/panel_pm25_red2.parquet", "no2": "DATOS/red2/paneles/panel_no2_red2.parquet"}
_TRAMO = {"tramo": "1.1", "valid_from": "2019-09-01T00:00:00", "valid_to": "2019-09-03T23:00:00", "minutos": -240,
          "veredicto": "F(-4)"}
_V2 = {"correr_v2": "AP/scripts_modelo_1km/v2/correr_v2.py", "config_v2": "AP/scripts_modelo_1km/v2/config_v2.json",
       "fabrica_v2": "AP/scripts_modelo_1km/v2/fabrica_v2.py"}
_COMPUERTA = {"aplicar": "m34", "m6": "m6", "estaticos": "m2a", "producir": "m5"}
_PLANTILLAS: list = []
_TOPE = int(constantes.valor("PROCESOS"))
# D59 (A39): los procesos por fase de un costo medido, con las fases de orquestacion.FASES_REPARTO
_PPF = {c: {f: _TOPE if i % 2 == 0 else _TOPE // 2 for i, f in enumerate(fases)}
        for c, fases in orquestacion.FASES_REPARTO.items()}


def _plano(x) -> dict:
    return {c: dict(f) for c, f in x.items()}


def _con(n) -> dict:
    """``_PPF`` con la primera fase de M3-4 en ``n``."""
    salida = _plano(_PPF)
    salida["m34"][orquestacion.FASES_REPARTO["m34"][0]] = n
    return salida


def _sha(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _numero_ajeno() -> str:
    """Un número que no está en ninguna fuente (se arma al correr)."""
    return f"{(3 ** 0.5) * 7654.321:.5f}".replace(".", ",")


def _git(repo, *args) -> str:
    """git en un repositorio temporal, con una configuración propia (sin la global ni la del sistema)."""
    correo = "prueba" + chr(64) + "ejemplo.invalid"
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
           "GIT_AUTHOR_NAME": "prueba", "GIT_AUTHOR_EMAIL": correo, "GIT_COMMITTER_NAME": "prueba",
           "GIT_COMMITTER_EMAIL": correo}
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, env=env, timeout=120, check=False)
    if r.returncode != 0:
        raise AssertionError(f"git {args[0]} falló en la carpeta temporal: {r.stderr.decode()[-300:]}")
    return r.stdout.decode().strip()


@functools.lru_cache(maxsize=None)
def _micromamba_texto() -> str:
    """El texto real de ``micromamba list -n amb_v2`` (FIJ-3), una vez por proceso."""
    if not V.MICROMAMBA.is_file():
        raise unittest.SkipTest("falta micromamba; FIJ-3 no se da por aprobada")
    return V.micromamba_list()


@functools.lru_cache(maxsize=None)
def _plantilla():
    """(rutas, lecturas): AP y APH con una copia de cada clave de la lista cerrada (ADD-1) más ``x.py``, y las lecturas
    del addendum; se arma una vez por proceso en una carpeta temporal que se borra al terminar."""
    tmp = tempfile.TemporaryDirectory()
    _PLANTILLAS.append(tmp)
    rutas = entorno.rutas_sinteticas(tmp.name)
    for a in addendum.claves_lista_cerrada(_REALES):
        destino = orquestacion.ruta_de_alias(rutas, a)
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(orquestacion.ruta_de_alias(_REALES, a), destino)
    orquestacion.ruta_de_alias(rutas, _CODIGO).write_bytes(b"x = 1\n")
    return rutas, addendum.lecturas_m1(rutas)


# ---------------------------------------------------------------------------
# Corridas falsas de orquestacion (cruzan la frontera con avance.iniciar())
# ---------------------------------------------------------------------------
LLAMADAS: list = []


def _sellar(cfg, *, avance, procesos=None):
    assert cfg.negativas(cfg) == [], cfg.negativas(cfg)            # como la primera fase de orquestacion
    LLAMADAS.append(("sellar", cfg.etiqueta))
    avance.iniciar()
    salidas.sellar_corrida(avance.carpeta, cfg.huellas, {"python": "3.11.16"}, rutas=cfg.rutas)
    return {}


def _abortar(cfg, *, avance, procesos=None):
    LLAMADAS.append(("abortar", cfg.etiqueta))
    avance.iniciar()
    raise RuntimeError("corte después de la frontera")


def _negar(cfg, *, avance, procesos=None):
    LLAMADAS.append(("negar", cfg.etiqueta))
    raise orquestacion.ErrorOrquestacion("M3-4 se niega a correr: el registro de M2a no está en la lista cerrada")


def _fallar(cfg, *, avance, procesos=None):
    LLAMADAS.append(("fallar", cfg.etiqueta))
    raise ValueError("un error de programación antes de la frontera")


def _alarma(cfg, *, avance, procesos=None):
    LLAMADAS.append(("alarma", cfg.etiqueta))
    avance.iniciar()
    raise orquestacion.DetencionPorAlarma("alarma Q1", {})


def _no_debe_correr(cfg, *, avance, procesos=None):
    raise AssertionError("la corrida no debía empezar: las negativas debían negarse")


def _fabrica_falsa(contaminante, variante, base):
    return base, None


# ---------------------------------------------------------------------------
# El mundo sintético
# ---------------------------------------------------------------------------
class _Mundo:
    """AP y APH como repositorios git temporales con su «origin», con todo lo de la lista cerrada (copiado de la
    plantilla), la salida de la batería en su subcarpeta de m1, el C5 sintético (la política confirmada en el commit
    que cita el registro), la red 2, el registro de la red v2, el addendum (de una batería aprobada) y las entradas,
    todo confirmado y enviado. ``compuerta`` = «m6» suma la corrida de M3-4/M5 sellada (con su cerrojo) y publicada,
    y lo que confirma el Anexo B; «m2a», la línea de cierre de C2."""

    def __init__(self, tmp, *, compuerta: str = "m34", c5: bool = True, c5_kw=None, errata_c5: str | None = None):
        self.rutas = r = entorno.rutas_sinteticas(tmp)
        self.raiz = Path(r.ap).parent
        self.compuerta = compuerta
        plantilla, self.lecturas = _plantilla()
        for campo in ("ap", "aph"):
            shutil.copytree(getattr(plantilla, campo), getattr(r, campo), dirs_exist_ok=True)
        self.salida_bateria = [f"{_M1}/{n}" for n in addendum.SALIDA_BATERIA]
        for a in self.salida_bateria:
            self.poner(a, f"{Path(a).name} de la batería\n".encode())
        self.poner(_PLIEGUES, b'{"pliegues": "red 2"}\n')
        for p, a in _PANELES.items():
            self.poner(a, f"panel {p}\n".encode())
        for repo in (r.ap, r.aph):
            _git(repo, "init", "-q", "-b", "main")
            origen = self.raiz / f"origen_{Path(repo).name}.git"
            _git(self.raiz, "init", "-q", "--bare", str(origen))
            _git(repo, "remote", "add", "origin", str(origen))
        self.confirmar_todo("base")
        self.registro_c5 = f"APH/auditoria/{sintetico.FECHA_C5_SINTETICA}/meteo_combinada/registro_politica_reloj.json"
        if c5:
            self._c5(dict(c5_kw or {}), errata_c5)
        self.poner(_REGISTRO_RED, json.dumps({"esquema": "registro-red-v2/prueba", "huellas": {
            a: _sha(self.ruta(a).read_bytes()) for a in (_PLIEGUES, *_PANELES.values())}}).encode())
        if compuerta == "m6":
            self._m6()
        if compuerta == "m2a":
            self.poner(_CIERRE_C2, json.dumps({"schema": V.ESQUEMA_CIERRE_C2, "fecha": "2026-10-27"}).encode())
        self.commit_ap = self.confirmar(r.ap, "M1 en AP")
        self.commit_aph = self.confirmar(r.aph, "M1 en APH")
        self.escribir_addendum()
        self.escribir_entradas()
        self.confirmar_todo("anexos")

    # --- disco y git ---
    def ruta(self, alias_: str) -> Path:
        return orquestacion.ruta_de_alias(self.rutas, alias_)

    def poner(self, alias_: str, datos: bytes) -> None:
        p = self.ruta(alias_)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(datos)

    def confirmar(self, repo, mensaje: str, *, enviar: bool = True) -> str:
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "--allow-empty", "-m", mensaje)
        if enviar:
            _git(repo, "push", "-q", "origin", "main")
        return _git(repo, "rev-parse", "HEAD")

    def confirmar_todo(self, mensaje: str = "cambio") -> None:
        self.confirmar(self.rutas.ap, f"{mensaje} en AP")
        self.confirmar(self.rutas.aph, f"{mensaje} en APH")

    def _c5(self, kw: dict, errata_c5: str | None) -> None:
        """La política (y sus artefactos) confirmada en AP, y el registro de C5 con ese commit como ``commit_c5``."""
        r = self.rutas
        if errata_c5 is not None:
            # «enviada»: en main y en origin/main; «local»: en una rama que nunca se envía (el archivo, igual, en
            # main), así que su commit no es antecesor de origin/main
            errata = "APH/auditoria/20261027/reloj_dmc/errata_c5.md"
            if errata_c5 == "local":
                _git(r.aph, "checkout", "-q", "-b", "lado")
            self.poner(errata, b"errata del reloj\n")
            commit = self.confirmar(r.aph, "errata de C5", enviar=errata_c5 == "enviada")
            if errata_c5 == "local":
                _git(r.aph, "checkout", "-q", "main")
                self.poner(errata, b"errata del reloj\n")
            kw["alterar_registro"] = {"errata_confirmada": {"ruta": errata, "sha256": _sha(b"errata del reloj\n"),
                                                            "commit": commit}}
        args = (self.raiz, {"900101": ["ab" * 32]}, {"900101": [dict(_TRAMO)]})
        sintetico.politica_reloj_sintetica(*args, **kw)
        self.commit_c5 = self.confirmar(r.ap, "C5 de RELOJ")
        sintetico.politica_reloj_sintetica(*args, **{"commit_c5": self.commit_c5, **kw})

    # --- lo que pasa la configuración ---
    def escribir_addendum(self, *, quitar=(), aprobada: bool = True, en_costo=None, **cambios) -> None:
        """El addendum de una batería aprobada, armado con ``addendum`` (``cambios`` reemplaza claves y ``en_costo``,
        claves de su costo)."""
        lista = addendum.lista_cerrada(self.rutas, bateria={a: _sha(self.ruta(a).read_bytes())
                                                            for a in self.salida_bateria}, rutas_bateria=self.rutas)

        def ref(nombre, **extra):
            a = f"{_M1}/{nombre}"
            return {"ruta": a, "sha256": _sha(self.ruta(a).read_bytes()), **extra}
        contenido = addendum.addendum_m1(
            lista, ref("anexo_a2.json"), ref("deriva_s6.json", pasa={"B": False, "AB": True}), None,
            ref("costo_m1.json", recorte="mod11", procesos_por_fase=_PPF), self.lecturas,
            {"ap": self.commit_ap, "aph": self.commit_aph}, fecha="2026-10-28",
            bateria={"carpeta": _M1, "resumen": ref("resumen_m1.json"), "aprobada": aprobada})
        contenido.update(cambios)
        if en_costo is not None:
            contenido["costo"] = {**contenido["costo"], **en_costo}
        for k in quitar:
            del contenido[k]
        self.poner(_ADDENDUM, entorno.json_canonico(contenido))           # como lo escribe salidas

    def entradas(self) -> dict:
        e = {"registro_c5": self.registro_c5, "red2": {"pliegues": _PLIEGUES, "paneles": dict(_PANELES)},
             "registro_red_v2": _REGISTRO_RED}
        if self.compuerta == "m6":
            e["confirmados_m6"] = {"enmienda_2_ambiental": "APH/auditoria/20261024/sinca_al_modelo/ENMIENDA_2.md",
                                   "enmienda_dmc": "APH/auditoria/20261030/meteo_combinada/enmienda_dmc.md",
                                   **{k: (a if k != "fabrica_v2" else [a]) for k, a in _V2.items()},
                                   "espejos": {a: "APH/" + a[len("AP/"):] for a in _V2.values()}}
        if self.compuerta == "m2a":
            e = {"conjuntos": {"V": "DATOS/v.json", "V2": "DATOS/v2.json"}, "cierre_c2": _CIERRE_C2}
        return e

    def huellas_entradas(self) -> dict:
        return {a: _sha(self.ruta(a).read_bytes()) for a in (_PLIEGUES, *_PANELES.values(), _REGISTRO_RED,
                                                            self.registro_c5) if self.ruta(a).is_file()}

    def escribir_entradas(self, entradas=None, huellas=None) -> None:
        e = self.entradas() if entradas is None else entradas
        h = self.huellas_entradas() if huellas is None else huellas
        self.poner(_ENTRADAS.format(self.compuerta), json.dumps(
            {"esquema": V.ESQUEMA_ENTRADAS, "compuerta": self.compuerta, "entradas": e, "huellas": h}).encode())

    def _m6(self) -> None:
        """La corrida de M3-4 y M5 (sellada, con su cerrojo y su copia) y su publicación, y lo que el Anexo B exige
        confirmado en git (``correr_v2.py`` y ``config_v2.json`` son los de la lista; sus espejos, con sus bytes)."""
        c = V.Cerrojo(self.rutas, "m34")
        base = {"fecha_utc": "2026-10-28T10:00:00Z", "etiqueta": _ETIQUETA, "huella_corrida": "ab" * 32}
        i = c.registrar({"evento": "intento", "compuerta": "m34", "huellas": {}, **base})["intento"]
        c.registrar({"evento": "inicio", "intento": i, "reanuda": False, "errata": None, **base})
        corrida = entorno.carpeta_salida(self.rutas, "m34", _ETIQUETA)
        salidas.agregar_linea(orquestacion.AVANCE, {"avance": "x", "corrida": _ETIQUETA, "huella": "ab" * 32},
                              raiz=corrida)
        c.copiar_a(corrida)
        salidas.escribir(salidas.DECISION, {"esquema": "prueba", "ganador": "A"}, clase="metrica", raiz=corrida)
        salidas.escribir("ambiental/lateral_pm25_I.bin", b"lateral", clase="insumo", raiz=corrida)
        salidas.sellar_corrida(corrida, {"APH/auditoria/x.json": "cd" * 32}, {"python": "3.11.16"}, rutas=self.rutas)
        c.registrar({"evento": "fin", "intento": i, "resultado": "sellada", "cruzo_frontera": True, "error": None,
                     "procesos": 0, **base})
        publicada = salidas.carpeta_publicacion(self.rutas.ap)
        publicada.mkdir(parents=True)
        for n in (salidas.DECISION, salidas.SHA256_JSON, salidas.RECIBO):
            shutil.copyfile(corrida / n, publicada / n)
        self.poner("APH/auditoria/20261024/sinca_al_modelo/ENMIENDA_2.md", b"Enmienda 2 ambiental\n")
        self.poner("APH/auditoria/20261030/meteo_combinada/enmienda_dmc.md", b"enmienda de la DMC\n")
        self.poner(_V2["fabrica_v2"], b"# fabrica_v2.py\n")
        for a in _V2.values():
            self.poner("APH/" + a[len("AP/"):], self.ruta(a).read_bytes())

    def escribir_errata(self, n: int = 1, compuerta: str = "m34", *, enviar: bool = True) -> None:
        prueba, sello = "APH/auditoria/20261029/meteo_combinada/prueba_errata.py", "APH/auditoria/sellos/anclajes.txt"
        self.poner(prueba, b"def test_falla(): pass\n")
        self.poner(sello, b"sello\n")
        self.poner(_ERRATA, json.dumps({"esquema": V.ESQUEMA_ERRATA, "n": n, "compuerta": compuerta,
                                        "fecha": "2026-10-29",
                                        "prueba": {"ruta": prueba, "sha256": _sha(b"def test_falla(): pass\n")},
                                        "sello": {"ruta": sello, "sha256": _sha(b"sello\n")}}).encode())
        self.confirmar(self.rutas.aph, f"errata {n}", enviar=enviar)

    # --- llamadas ---
    def argv(self, modo: str = "aplicar", *extra) -> list:
        c = _COMPUERTA[modo]
        salida = [f"--{modo}", "--addendum", str(self.ruta(_ADDENDUM)), "--entradas",
                  str(self.ruta(_ENTRADAS.format(c))), *extra]
        if c in ("m5", "m6") and "--etiqueta" not in extra:
            salida += ["--etiqueta", _ETIQUETA]
        return salida

    def servicios(self, ejecutor=None, *, fabrica=True, ahora=_AHORA, micromamba=None) -> V.Servicios:
        ej = ejecutor or _sellar
        return V.Servicios(ahora=lambda: ahora, micromamba=micromamba or _micromamba_texto,
                           ejecutores={c: ej for c in ("m2a", "m34", "m5", "m6")},
                           fabrica_m6=_fabrica_falsa if fabrica else None)

    def cfg(self, modo: str = "aplicar", *extra, **kw):
        args = V.analizar_argumentos(self.argv(modo, *extra))
        U = umbrales.cargar_m0(self.rutas.aph)
        return V._armar(args, self.rutas, modo, self.servicios(**kw), U)[0]

    def fallas(self, modo: str = "aplicar", *extra, **kw) -> list:
        cfg = self.cfg(modo, *extra, **kw)
        return cfg.negativas.fallas(cfg)

    def main(self, modo: str = "aplicar", *extra, ejecutor=None, **kw) -> tuple[int, list[str]]:
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            codigo = V.main(self.argv(modo, *extra), rutas=self.rutas, servicios=self.servicios(ejecutor, **kw))
        return codigo, salida.getvalue().splitlines()

    def cerrojo(self, compuerta: str = "m34") -> V.Cerrojo:
        return V.Cerrojo(self.rutas, compuerta)

    def corrida(self, etiqueta: str = _ETIQUETA, compuerta: str = "m34") -> Path:
        return entorno.carpeta_salida(self.rutas, compuerta, etiqueta)


def _motivos(fallas) -> list[str]:
    return sorted({f.motivo for f in fallas})


# ---------------------------------------------------------------------------
# S2: --aplicar se niega sin un C5 válido
# ---------------------------------------------------------------------------
class PruebasS2Aplicar(unittest.TestCase):
    def setUp(self):
        LLAMADAS.clear()

    def _negada(self, mundo: _Mundo, motivo: str) -> list[str]:
        codigo, lineas = mundo.main("aplicar", ejecutor=_no_debe_correr)
        self.assertEqual(codigo, 1)
        c = mundo.cerrojo()
        self.assertEqual([ln["evento"] for ln in c.lineas], ["intento", "negada"])
        self.assertEqual(c.lineas[-1]["motivos"], [motivo], "el mundo es válido salvo el C5 de la prueba")
        self.assertEqual(c.confirmatorias(), [], "una negativa no cuenta como corrida (P118)")
        self.assertFalse(mundo.corrida().exists(), "una negativa no deja nada en la carpeta de la corrida")
        self.assertTrue(any("se niega a correr" in ln for ln in lineas))
        return lineas

    def test_s02_aplicar_corre_con_c5_valido(self):
        """Control: con un C5 válido las negativas pasan y la corrida empieza (y sella)."""
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp)
            self.assertEqual(V.negativas_m34(m.cfg()), [])
            codigo, _ = m.main("aplicar")
            self.assertEqual(codigo, 0)
            self.assertEqual(LLAMADAS, [("sellar", _ETIQUETA)])

    def test_s02_aplicar_se_niega_sin_registro_c5(self):
        """--aplicar se niega sin el registro de C5."""
        with tempfile.TemporaryDirectory() as tmp:
            self._negada(_Mundo(tmp, c5=False), "c5_sin_registro")

    def test_s02_aplicar_se_niega_con_sha_distinto(self):
        """--aplicar se niega si el sha256 de la política difiere."""
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp)
            politica = sintetico.rutas_politica_sintetica(m.raiz)["politica"]
            politica.write_bytes(politica.read_bytes() + b" ")
            m.confirmar_todo()
            lineas = self._negada(m, "c5_sha256")
            self.assertTrue(any("sha256" in ln for ln in lineas))

    def test_s02_aplicar_se_niega_con_post_hoc(self):
        """--aplicar se niega con post_hoc = true."""
        with tempfile.TemporaryDirectory() as tmp:
            self._negada(_Mundo(tmp, c5_kw={"post_hoc": True}), "c5_post_hoc")

    def test_s02_aplicar_se_niega_con_errata_post_c4_sin_errata_confirmada(self):
        """--aplicar se niega con errata_post_c4 = true sin una errata confirmada; con la errata confirmada en git
        corre, y con una errata que no está en origin/main se niega."""
        with tempfile.TemporaryDirectory() as tmp:
            self._negada(_Mundo(tmp, c5_kw={"errata_post_c4": True}), "c5_errata")
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp, c5_kw={"errata_post_c4": True}, errata_c5="enviada")
            self.assertEqual(V.negativas_m34(m.cfg()), [])
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp, c5_kw={"errata_post_c4": True}, errata_c5="local")
            self.assertEqual(_motivos(m.fallas()), ["c5_errata"])

    def test_s02_registro_c5_y_commit_c5_en_git(self):
        """VER-7 (revisión de la ola 6): el registro de C5 confirmado en git y en origin/main, y ``commit_c5`` un
        antecesor de origin/main de AP que trae la política y ``artefactos_evaluados`` con las sha256 del registro."""
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp)
            args = (m.raiz, {"900101": ["ab" * 32]}, {"900101": [dict(_TRAMO)]})
            # commit_c5 = un commit de AP en origin/main en el que la política todavía no estaba
            base = _git(m.rutas.ap, "rev-list", "--max-parents=0", "HEAD")
            sintetico.politica_reloj_sintetica(*args, commit_c5=base)
            m.escribir_entradas()
            m.confirmar_todo()
            fallas = m.fallas()
            self.assertEqual(_motivos(fallas), ["c5_git"])
            self.assertTrue(any("no tiene en commit_c5" in f.texto for f in fallas))
            # commit_c5 = un commit que nunca se envió
            _git(m.rutas.ap, "checkout", "-q", "-b", "lado")
            m.poner("AP/scripts_modelo_1km/lado.txt", b"lado\n")
            local = m.confirmar(m.rutas.ap, "sin enviar", enviar=False)
            _git(m.rutas.ap, "checkout", "-q", "main")
            sintetico.politica_reloj_sintetica(*args, commit_c5=local)
            m.escribir_entradas()
            m.confirmar_todo()
            fallas = m.fallas()
            self.assertEqual(_motivos(fallas), ["c5_git"])
            self.assertTrue(any("no es antecesor de origin/main" in f.texto for f in fallas))
            # el registro de C5 sin confirmar en git
            sintetico.politica_reloj_sintetica(*args, commit_c5=m.commit_c5)
            m.escribir_entradas()
            self.assertEqual(_motivos(m.fallas()), ["arbol_sucio", "c5_git", "testigo"])
            m.confirmar_todo()
            self.assertEqual(m.fallas(), [])


# ---------------------------------------------------------------------------
# S16: M6 se niega a correr (Anexo B) e intentos_m6.jsonl
# ---------------------------------------------------------------------------
class PruebasS16Verificar(unittest.TestCase):
    def setUp(self):
        LLAMADAS.clear()

    def test_s16_m6_corre_si_todo_calza(self):
        """Control: con la publicación, los commits, el registro de la red y la fábrica, M6 corre y sella."""
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp, compuerta="m6")
            self.assertEqual(V.negativas_m6(m.cfg("m6")), [])
            codigo, _ = m.main("m6")
            self.assertEqual(codigo, 0)
            self.assertEqual(LLAMADAS, [("sellar", _ETIQUETA)])
            self.assertTrue((m.corrida(compuerta="m6") / "intentos_m6.jsonl").is_file())

    def test_s16_intentos_m6_solo_agregado(self):
        """intentos_m6.jsonl: sólo agregado, también los abortados; encadenado (una línea cambiada detiene todo);
        la copia en m6/ es un prefijo del cerrojo hecho antes del sello."""
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp, compuerta="m6")
            codigo, lineas = m.main("m6", ejecutor=_abortar)
            self.assertEqual(codigo, 1)
            c = m.cerrojo("m6")
            self.assertEqual([ln["evento"] for ln in c.lineas], ["intento", "inicio", "fin"])
            fin = c.lineas[-1]
            self.assertEqual((fin["resultado"], fin["cruzo_frontera"], fin["error"]), ("abortada", True, "RuntimeError"))
            self.assertRegex(c.lineas[0]["fecha_utc"], r"^2026-10-28T15:00:00Z$")
            self.assertIn(_ADDENDUM, c.lineas[0]["huellas"])
            self.assertEqual(c.lineas[0]["interprete"], fijados.SHA_MICROMAMBA_LIST)
            self.assertTrue(any("después de la frontera" in ln for ln in lineas))
            copia = m.corrida(compuerta="m6") / "intentos_m6.jsonl"
            self.assertTrue(c.ruta.read_bytes().startswith(copia.read_bytes()))
            self.assertEqual(json.loads(copia.read_bytes().splitlines()[-1])["evento"], "inicio")
            # una abortada se reanuda con las mismas entradas: misma etiqueta y huella
            codigo, _ = m.main("m6")
            self.assertEqual(codigo, 0)
            c.releer()
            self.assertEqual([ln["evento"] for ln in c.lineas][-3:], ["intento", "inicio", "fin"])
            self.assertTrue(c.lineas[-2]["reanuda"])
            self.assertTrue(c.ruta.read_bytes().startswith(copia.read_bytes()))
            # sólo agregado (SLD-8) y la cadena (VER-9)
            with self.assertRaises(ceguera.SalidaProhibida):
                salidas.escribir("intentos_m6.jsonl", b"{}\n", clase="procedencia", raiz=c.carpeta)
            datos = c.ruta.read_bytes()
            c.ruta.write_bytes(datos.replace(b'"abortada"', b'"sellada"'))
            with self.assertRaises(V.ErrorCerrojo):
                V.Cerrojo(m.rutas, "m6")
            codigo, lineas = m.main("m6", ejecutor=_no_debe_correr)
            self.assertEqual(codigo, 1)
            self.assertTrue(any("no corre" in ln for ln in lineas))

    def test_s16_m6_se_niega_con_huellas_de_m5_distintas(self):
        """Huellas de decision.json o de M5 distintas de las publicadas."""
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp, compuerta="m6")
            corrida = m.corrida()
            (corrida / "ambiental" / "lateral_pm25_I.bin").write_bytes(b"otra lateral")
            self.assertEqual(_motivos(m.fallas("m6")), ["publicacion"])
            (corrida / salidas.DECISION).write_bytes(b'{"ganador":"B"}')
            fallas = m.fallas("m6")
            self.assertEqual(_motivos(fallas), ["publicacion"])
            self.assertTrue(any(salidas.DECISION in f.texto for f in fallas))
            codigo, _ = m.main("m6", ejecutor=_no_debe_correr)
            self.assertEqual(codigo, 1)

    def test_s16_m6_se_niega_con_huellas_del_addendum_distintas(self):
        """Una huella de la lista cerrada del addendum difiere."""
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp, compuerta="m6")
            m.poner(_CODIGO, b"x = 2\n")
            m.confirmar_todo()
            fallas = m.fallas("m6")
            self.assertEqual(_motivos(fallas), ["lista_cerrada"])
            self.assertTrue(any(_CODIGO in f.texto for f in fallas))

    def test_s16_m6_se_niega_sin_commits_en_el_remoto_o_arbol_sucio(self):
        """Commits que no son antecesores de origin/main, árbol sucio o un archivo distinto del remoto."""
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp, compuerta="m6")
            nuevo = m.ruta(f"{_PAQ}/nuevo.py")
            nuevo.write_bytes(b"y = 1\n")
            self.assertEqual(_motivos(m.fallas("m6")), ["arbol_sucio", "lista_cerrada"])
            nuevo.unlink()
            self.assertEqual(m.fallas("m6"), [])
            # la fábrica v2 cambia en un commit que no se envió (y su espejo también)
            for a in (_V2["fabrica_v2"], "APH/" + _V2["fabrica_v2"][len("AP/"):]):
                m.poner(a, b"# fabrica_v2 nueva\n")
            m.confirmar(m.rutas.ap, "v2 local", enviar=False)
            m.confirmar(m.rutas.aph, "espejo local", enviar=False)
            fallas = m.fallas("m6")
            self.assertEqual(_motivos(fallas), ["confirmados_m6", "testigo"])
            self.assertTrue(any("origin/main" in f.texto for f in fallas))
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp, compuerta="m6")
            _git(m.rutas.ap, "checkout", "-q", "-b", "lado")                 # un commit que nunca se envía
            m.poner("AP/scripts_modelo_1km/lado.txt", b"lado\n")
            local = m.confirmar(m.rutas.ap, "M1 sin enviar", enviar=False)
            _git(m.rutas.ap, "checkout", "-q", "main")
            m.escribir_addendum(commits={"ap": local, "aph": m.commit_aph})
            m.confirmar_todo()
            self.assertEqual(_motivos(m.fallas("m6")), ["commit_m1"])

    def test_s16_m6_se_niega_con_corrida_confirmatoria_previa(self):
        """intentos_m6.jsonl ya registra una corrida confirmatoria (sellada): otra corrida exige una errata."""
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp, compuerta="m6")
            self.assertEqual(m.main("m6")[0], 0)
            codigo, lineas = m.main("m6", ejecutor=_no_debe_correr)
            self.assertEqual(codigo, 1)
            self.assertEqual(m.cerrojo("m6").lineas[-1]["motivos"], ["cerrojo"])
            self.assertTrue(any("corrida confirmatoria" in ln for ln in lineas))

    def test_s16_m6_errata_se_niega(self):
        """VER-19 (P-VER-5): una errata de M6 no tiene carpeta propia todavía; rige la más estricta y M6 se niega."""
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp, compuerta="m6")
            self.assertEqual(m.main("m6", ejecutor=_abortar)[0], 1)
            m.escribir_errata(1, compuerta="m6")
            errata = ("--errata", str(m.ruta(_ERRATA)))
            self.assertIn("errata_m6", _motivos(m.fallas("m6", *errata)))
            codigo, lineas = m.main("m6", *errata, ejecutor=_no_debe_correr)
            self.assertEqual(codigo, 1)
            self.assertIn("errata_m6", m.cerrojo("m6").lineas[-1]["motivos"])
            self.assertTrue(any("m6_ERRATA" in ln for ln in lineas))

    def test_s16_m6_se_niega_sin_fabrica(self):
        """Diferencia 33: sin la fábrica de producción v2 (``Cfg.fabrica_m6``) M6 no corre."""
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp, compuerta="m6")
            self.assertEqual(_motivos(m.fallas("m6", fabrica=False)), ["fabrica"])
            self.assertEqual(m.main("m6", ejecutor=_no_debe_correr, fabrica=False)[0], 1)

    def test_s16_fabrica_desde_las_entradas(self):
        """VER-13: la fábrica de v2 llega por las entradas ({modulo, funcion}) con su huella y se carga dentro del
        aislamiento; la huella de la corrida no cambia de un intento a otro (para reanudar); otra huella se niega, y
        una fábrica que lee /Volumes al cargarse no se arma."""
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp, compuerta="m6")

            def con_fabrica(fuente: bytes, huella: str | None = None):
                for a in (_V2["fabrica_v2"], "APH/" + _V2["fabrica_v2"][len("AP/"):]):
                    m.poner(a, fuente)
                e = m.entradas()
                e["fabrica_m6"] = {"modulo": _V2["fabrica_v2"], "funcion": "fabrica"}
                m.escribir_entradas(e, {**m.huellas_entradas(), _V2["fabrica_v2"]: huella or _sha(fuente)})
                m.confirmar_todo()
            con_fabrica(b"def fabrica(contaminante, variante, base):\n    return base, None\n")
            cfgs = [m.cfg("m6", fabrica=False) for _ in range(2)]
            self.assertTrue(all(callable(c.fabrica_m6) for c in cfgs))
            self.assertEqual(cfgs[0].fabrica_m6("pm25", "I", "base"), ("base", None))
            self.assertEqual(orquestacion.huella_de_corrida(cfgs[0], "m6"), orquestacion.huella_de_corrida(cfgs[1], "m6"))
            self.assertEqual(V.negativas_m6(cfgs[0]), [])
            con_fabrica(b"def fabrica(contaminante, variante, base):\n    return base, None\n", "00" * 32)
            with self.assertRaises(V.ErrorConfiguracion):
                m.cfg("m6", fabrica=False)
            prohibida = "/" + "Volumes" + "/meteo_combinada_prueba_inexistente/x"
            con_fabrica(f"import os\nos.stat({prohibida!r})\n\ndef fabrica(c, v, b):\n    return b, None\n".encode())
            with self.assertRaises(PermissionError):
                m.cfg("m6", fabrica=False)
            codigo, _ = m.main("m6", ejecutor=_no_debe_correr, fabrica=False)
            self.assertEqual(codigo, 1)
            ultima = m.cerrojo("m6").lineas[-1]
            self.assertEqual((ultima["motivos"], ultima["error"]), (["configuracion"], "PermissionError"))

    def test_s16_m6_registro_de_la_red_con_los_paneles(self):
        """MC-09: M6 exige en el registro de la red v2 la huella de los paneles de la red 2."""
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp, compuerta="m6")
            m.poner(_REGISTRO_RED, json.dumps({"huellas": {_PLIEGUES: _sha(m.ruta(_PLIEGUES).read_bytes())}}).encode())
            m.escribir_entradas()
            m.confirmar_todo()
            fallas = m.fallas("m6")
            self.assertEqual(_motivos(fallas), ["registro_red_v2"])
            self.assertTrue(any("panel_pm25_red2.parquet" in f.texto for f in fallas))


# ---------------------------------------------------------------------------
# Negativas de §10 y el contenido del addendum
# ---------------------------------------------------------------------------
class PruebasNegativas(unittest.TestCase):
    def setUp(self):
        LLAMADAS.clear()

    def test_negativas_m34_de_10(self):
        """Huellas, árbol limpio, commit de M1 en origin/main, testigo, datos fijados e intentos (§10)."""
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp)
            self.assertEqual(m.fallas(), [])
            # una huella de la lista cerrada (la salida de la batería, en LOCAL)
            m.poner(f"{_M1}/pruebas_m1.txt", b"otras pruebas\n")
            self.assertEqual(_motivos(m.fallas()), ["lista_cerrada"])
            m.poner(f"{_M1}/pruebas_m1.txt", "pruebas_m1.txt de la batería\n".encode())
            # árbol sucio en APH (un archivo nuevo en la carpeta del addendum)
            m.poner("APH/auditoria/20261028/meteo_combinada/m1/borrador.md", b"x\n")
            self.assertEqual(_motivos(m.fallas()), ["arbol_sucio"])
            m.ruta("APH/auditoria/20261028/meteo_combinada/m1/borrador.md").unlink()
            # un cambio sin confirmar en la auditoría del producto (testigo y árbol sucio)
            texto = m.ruta(f"APH/{addendum.DECISIONES[1]}")
            texto.write_bytes(texto.read_bytes() + b"\n")
            self.assertEqual(_motivos(m.fallas()), ["arbol_sucio", "lista_cerrada", "testigo"])
            _git(m.rutas.aph, "checkout", "-q", "--", addendum.DECISIONES[1])
            # el addendum sin confirmar en git y con el commit de M1 de AP pendiente
            m.escribir_addendum(commits={"ap": "pendiente", "aph": m.commit_aph})
            self.assertEqual(_motivos(m.fallas()), ["arbol_sucio", "commit_m1", "testigo"])
            m.confirmar_todo()
            fallas = m.fallas()
            self.assertEqual(_motivos(fallas), ["commit_m1"])
            self.assertTrue(any("pendiente" in f.texto for f in fallas))
            m.escribir_addendum()
            m.confirmar_todo()
            # confirmado en un commit local que no se envió: «git diff origin/main» lo ve (testigo)
            m.escribir_addendum(fecha="2026-10-29")
            m.confirmar(m.rutas.aph, "addendum sin enviar", enviar=False)
            self.assertEqual(_motivos(m.fallas()), ["testigo"])
            m.escribir_addendum()
            m.confirmar_todo()
            # una huella de datos distinta de la fijada (§9.3)
            celdas = "GRILLA/celdas.parquet"
            m.escribir_entradas(huellas={**m.huellas_entradas(), celdas: "00" * 32})
            m.confirmar_todo()
            self.assertEqual(_motivos(m.fallas()), ["datos_fijados"])
            self.assertIn(celdas, fijados.HUELLAS_DATOS)
            m.escribir_entradas()
            m.confirmar_todo()
            self.assertEqual(m.fallas(), [])
            # intentos: una corrida sellada cierra M3-4
            self.assertEqual(m.main("aplicar")[0], 0)
            self.assertEqual(_motivos(m.fallas()), ["cerrojo"])

    def test_negativas_contenido_del_addendum(self):
        """VER-7 (revisión de la ola 6): la batería aprobada, las claves exactas, el v2.3 con su huella, el recorte
        fijado desde los umbrales, la deriva fijada, todas las claves de la lista cerrada (también los documentos y la
        salida de la batería) y las huellas fijadas."""
        casos = [
            ("sin declarar la enmienda operativa", {"quitar": ("enmienda_operativa",)}, ["addendum"]),
            ("enmienda presentada como anterior al C4", {"enmienda_operativa": {
                **addendum.ENMIENDA_OPERATIVA, "post_hoc": False}}, ["addendum"]),
            ("post_hoc numérico no es True", {"enmienda_operativa": {
                **addendum.ENMIENDA_OPERATIVA, "post_hoc": 1}}, ["addendum"]),
            ("lo visto falseado", {"enmienda_operativa": {
                **addendum.ENMIENDA_OPERATIVA, "lo_visto": "no se vio nada"}}, ["addendum"]),
            ("sin declarar enmienda de carga", {"quitar": ("enmienda_carga",)}, ["addendum"]),
            ("carga sin post_hoc", {"enmienda_carga": {
                **addendum.ENMIENDA_CARGA, "post_hoc": False}}, ["addendum"]),
            ("carga con post_hoc numérico", {"enmienda_carga": {
                **addendum.ENMIENDA_CARGA, "post_hoc": 1}}, ["addendum"]),
            ("regla de carga alterada", {"enmienda_carga": {
                **addendum.ENMIENDA_CARGA, "regla_enmendada": "se rechaza por carga"}}, ["addendum"]),
            ("memoria ausente", {"quitar": ("enmienda_memoria",)}, ["addendum"]),
            ("memoria post_hoc numérico", {"enmienda_memoria": {
                **addendum.ENMIENDA_MEMORIA, "post_hoc": 1}}, ["addendum"]),
            ("memoria regla falsa", {"enmienda_memoria": {
                **addendum.ENMIENDA_MEMORIA, "regla_enmendada": "sin comprobaciones"}}, ["addendum"]),
            ("declaración C4 incompatible", {"declaracion_c4_reloj": {
                **addendum.DECLARACION_C4, "lectura_propuesta": "todo es implementación, no enmienda"}}, ["addendum"]),
            ("batería no aprobada", {"aprobada": False}, ["addendum"]),
            ("sin la carpeta de la batería", {"bateria": {"aprobada": True}}, ["addendum"]),
            ("una clave de menos", {"quitar": ("acuerdos",)}, ["addendum"]),
            ("otro texto vigente", {"texto_vigente": {"ruta": f"APH/{addendum.TEXTO_V2_2}", "sha256": "ab" * 32}},
             ["addendum"]),
            ("recorte pendiente", {"recorte": "pendiente"}, ["addendum"]),
            ("recorte no fijado por los umbrales", {"recorte": "mod99"}, ["addendum"]),
            ("deriva pendiente", {"deriva": {"parametros": [], "estado": "pendiente"}}, ["addendum"]),
            # VER-22 (D59, A39): los procesos por fase del costo, con las fases exactas de FASES_REPARTO
            ("costo pendiente", {"costo": "pendiente"}, ["addendum"]),
            ("sin procesos por fase", {"en_costo": {"procesos_por_fase": None}}, ["addendum"]),
            ("una compuerta de más", {"en_costo": {"procesos_por_fase": {**_PPF, "m6": {"anual": 1}}}}, ["addendum"]),
            ("una fase de menos", {"en_costo": {"procesos_por_fase": {**_PPF, "m5": {"anual": 1}}}}, ["addendum"]),
            ("cero procesos", {"en_costo": {"procesos_por_fase": _con(0)}}, ["addendum"]),
            ("un bool", {"en_costo": {"procesos_por_fase": _con(True)}}, ["addendum"]),
            ("más que PROCESOS", {"en_costo": {"procesos_por_fase": _con(_TOPE + 1)}}, ["addendum"]),
            ("veredicto distinto del recorte", {"en_costo": {"veredicto": "mod23"}}, ["addendum"]),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp)
            cfg_valida = m.cfg()
            for nombre, cambios, esperado in casos:
                with self.subTest(caso=nombre):
                    m.escribir_addendum(**cambios)
                    m.confirmar_todo()
                    if "enmienda_operativa" in cambios or "declaracion_c4_reloj" in cambios \
                            or "enmienda_carga" in cambios or "enmienda_carga" in cambios.get("quitar", ()) \
                            or "enmienda_memoria" in cambios or "enmienda_memoria" in cambios.get("quitar", ()) \
                            or "enmienda_operativa" in cambios.get("quitar", ()):
                        contenido = json.loads(m.ruta(_ADDENDUM).read_bytes())
                        self.assertEqual(_motivos(V._fallas_contenido(cfg_valida, contenido)), esperado)
                        with self.assertRaises(V.ErrorConfiguracion):
                            m.cfg()
                    else:
                        self.assertEqual(_motivos(m.fallas()), esperado)
            # recorte «pendiente»: la corrida se arma (VER-13) y la negativa la niega, sin llegar a orquestacion
            m.escribir_addendum(recorte="pendiente")
            m.confirmar_todo()
            cfg = m.cfg()
            self.assertIs(cfg.recorte, False)
            codigo, lineas = m.main("aplicar", ejecutor=_no_debe_correr)
            self.assertEqual(codigo, 1)
            self.assertEqual(m.cerrojo().lineas[-1]["motivos"], ["addendum"])
            self.assertTrue(any("recorte" in ln for ln in lineas))
            # la lista sin un documento del paquete o sin una salida de la batería
            for falta in (f"{_PAQ}/{addendum.DISENO}", f"{_PAQ}/{addendum.COORDINACION}", f"{_M1}/sha256.json"):
                with self.subTest(falta=falta):
                    m.escribir_addendum()
                    contenido = json.loads(m.ruta(_ADDENDUM).read_bytes())
                    del contenido["lista_cerrada"][falta]
                    m.poner(_ADDENDUM, json.dumps(contenido, ensure_ascii=False).encode())
                    m.confirmar_todo()
                    fallas = m.fallas()
                    self.assertEqual(_motivos(fallas), ["lista_cerrada"])
                    self.assertTrue(any(falta in f.texto for f in fallas))
            # una huella fijada del código distinta en el addendum
            m.escribir_addendum()
            contenido = json.loads(m.ruta(_ADDENDUM).read_bytes())
            contenido["lista_cerrada"][_V2["correr_v2"]] = "ab" * 32
            m.poner(_ADDENDUM, json.dumps(contenido, ensure_ascii=False).encode())
            m.confirmar_todo()
            fallas = m.fallas()
            self.assertEqual(_motivos(fallas), ["lista_cerrada"])
            self.assertTrue(any("no es la fijada" in f.texto for f in fallas))
            m.escribir_addendum()
            m.confirmar_todo()
            self.assertEqual(m.fallas(), [])

    def test_procesos_por_fase_en_cfg(self):
        """VER-22 (D59; A39): ``_armar`` pasa a ``Cfg.procesos_por_fase`` los del addendum; sin su forma exacta, 1 en
        cada fase, y la negativa «addendum» niega antes de la frontera."""
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp)
            cfg = m.cfg()
            self.assertEqual(_plano(cfg.procesos_por_fase), _PPF)
            self.assertEqual(cfg.negativas.fallas(cfg), [])
            m.escribir_addendum(en_costo={"procesos_por_fase": {**_PPF, "m6": {"anual": 1}}})
            m.confirmar_todo()
            cfg = m.cfg()
            self.assertEqual(_plano(cfg.procesos_por_fase), V._procesos_que_no_corren())
            fallas = cfg.negativas.fallas(cfg)
            self.assertEqual(_motivos(fallas), ["addendum"])
            self.assertTrue(any("D59" in f.texto for f in fallas))
            codigo, _ = m.main("aplicar", ejecutor=_no_debe_correr)
            self.assertEqual((codigo, m.cerrojo().lineas[-1]["motivos"]), (1, ["addendum"]))

    def test_nombres_de_las_fases_son_los_de_orquestacion(self):
        """VER-22: ``verificar`` acepta exactamente las compuertas y las fases de ``orquestacion.FASES_REPARTO``, con
        cada n un entero (no bool) de 1 a PROCESOS, lo mismo que ``Cfg``; la corrida que no corre lleva esas fases."""
        fases = orquestacion.FASES_REPARTO
        completo = {c: {f: _TOPE for f in fs} for c, fs in fases.items()}
        self.assertEqual(V._procesos_por_fase(completo), completo)
        self.assertEqual(V._procesos_que_no_corren(), {c: {f: 1 for f in fs} for c, fs in fases.items()})
        candidatos = [completo, V._procesos_que_no_corren(), {**completo, "m6": {"anual": 1}}, {},
                      {"M34": completo["m34"], "m5": completo["m5"]}, None, [], _con(0), _con(True), _con(1.0),
                      _con("1"), _con(_TOPE + 1)]
        for c, fs in fases.items():
            candidatos.append({k: v for k, v in completo.items() if k != c})
            candidatos.append({**completo, c: {**completo[c], "otra_fase": 1}})
            for f in fs:
                candidatos.append({**completo, c: {g: n for g, n in completo[c].items() if g != f}})
        with tempfile.TemporaryDirectory() as tmp:
            rutas = entorno.rutas_sinteticas(tmp)
            for x in candidatos:
                with self.subTest(candidato=repr(x)[:80]):
                    try:
                        orquestacion.Cfg(rutas=rutas, umbrales=None, entradas={}, huellas={}, procesos_por_fase=x)
                        acepta_cfg = x is not None
                    except orquestacion.ErrorOrquestacion:
                        acepta_cfg = False
                    self.assertEqual(V._procesos_por_fase(x) is not None, acepta_cfg)
        self.assertEqual(sum(V._procesos_por_fase(x) is not None for x in candidatos), 2)

    def test_espejo_del_paquete_en_aph(self):
        """VER-6: si el paquete tiene espejo en APH (la misma ruta relativa), debe tener los mismos bytes y estar
        confirmado; sin espejo no se exige."""
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp)
            espejo = "APH/" + _CODIGO[len("AP/"):]
            m.poner(espejo, b"x = 1\n")
            self.assertEqual(_motivos(m.fallas()), ["arbol_sucio"])
            m.confirmar_todo()
            self.assertEqual(m.fallas(), [])
            m.poner(espejo, b"x = 3\n")
            m.confirmar_todo()
            fallas = m.fallas()
            self.assertEqual(_motivos(fallas), ["espejo"])
            self.assertTrue(any(espejo in f.texto for f in fallas))

    def test_interprete_en_las_corridas_reales(self):
        """VER-16 (FIJ-3): otro ``micromamba list`` o un intérprete no fijado niegan; la identidad va a las entradas,
        a la huella de la corrida y, por ``interprete.json``, al recibo."""
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp)
            self.assertEqual(_motivos(m.fallas(micromamba=lambda: "otro entorno\n")), ["interprete"])
            with mock.patch.object(entorno, "comprobar_interprete", side_effect=RuntimeError("no fijado")):
                self.assertEqual(_motivos(m.fallas()), ["interprete"])
            cfg = m.cfg()
            self.assertEqual(cfg.entradas["interprete"]["micromamba_list_sha256"], fijados.SHA_MICROMAMBA_LIST)
            self.assertNotEqual(orquestacion.huella_de_corrida(cfg, "m34"),
                                orquestacion.huella_de_corrida(m.cfg(micromamba=lambda: "otro\n"), "m34"))
            codigo, _ = m.main("aplicar", ejecutor=_no_debe_correr, micromamba=lambda: "otro entorno\n")
            self.assertEqual(codigo, 1)
            self.assertEqual(m.cerrojo().lineas[-1]["motivos"], ["interprete"])
            self.assertEqual(m.main("aplicar")[0], 0)
            corrida = m.corrida()
            alias_ = entorno.alias(corrida / V.INTERPRETE_JSON, m.rutas)
            sha = _sha((corrida / V.INTERPRETE_JSON).read_bytes())
            recibo = json.loads((corrida / salidas.RECIBO).read_bytes())
            self.assertEqual(recibo["huellas"][alias_], sha)
            inventario = json.loads((corrida / salidas.SHA256_JSON).read_bytes())["archivos"]
            self.assertEqual(inventario[V.INTERPRETE_JSON]["sha256"], sha)
            self.assertEqual(json.loads((corrida / V.INTERPRETE_JSON).read_bytes())["micromamba_list_sha256"],
                             fijados.SHA_MICROMAMBA_LIST)

    def test_negativas_m34_registro_de_la_red_v2(self):
        """MC-09: sin el anexo «Registro de la red v2» confirmado, o sin la huella de los pliegues en su clave
        ``huellas``, M3-4 se niega; una subcadena con la huella en un texto no basta (VER-15)."""
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp)
            e = m.entradas()
            del e["registro_red_v2"]
            m.escribir_entradas(e)
            m.confirmar_todo()
            self.assertEqual(_motivos(m.fallas()), ["registro_red_v2"])
            m.escribir_entradas()
            m.confirmar_todo()
            # sin confirmar en git
            m.poner(_REGISTRO_RED, m.ruta(_REGISTRO_RED).read_bytes() + b"\n")
            m.escribir_entradas()
            self.assertIn("registro_red_v2", _motivos(m.fallas()))
            # confirmado, pero sin la huella de pliegues_v2_red2.json
            m.poner(_REGISTRO_RED, json.dumps({"huellas": {}}).encode())
            m.escribir_entradas()
            m.confirmar_todo()
            fallas = m.fallas()
            self.assertEqual(_motivos(fallas), ["registro_red_v2"])
            self.assertTrue(any("pliegues_v2_red2.json" in f.texto for f in fallas))
            # la huella en un texto, no en la estructura
            m.poner(_REGISTRO_RED, f"Registro de la red v2\n- {_PLIEGUES} {_sha(m.ruta(_PLIEGUES).read_bytes())}\n"
                    .encode())
            m.escribir_entradas()
            m.confirmar_todo()
            fallas = m.fallas()
            self.assertEqual(_motivos(fallas), ["registro_red_v2"])
            self.assertTrue(any("VER-15" in f.texto for f in fallas))

    def test_negativas_sin_red(self):
        """VER-14: las negativas corren bajo ``SinRed``."""
        import socket
        vistos = []

        def sonda(cfg):
            try:
                socket.getaddrinfo("localhost", 80)
                vistos.append("red")
            except ceguera.RedProhibida:
                vistos.append("negada")
            return []
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp)
            with mock.patch.dict(V._FALLAS, {"m34": sonda}):
                self.assertEqual(m.fallas(), [])
        self.assertEqual(vistos, ["negada"])


# ---------------------------------------------------------------------------
# El cerrojo, las corridas reales y la consola
# ---------------------------------------------------------------------------
class PruebasCerrojo(unittest.TestCase):
    def setUp(self):
        LLAMADAS.clear()

    def _sellada(self, tmp) -> _Mundo:
        m = _Mundo(tmp)
        self.assertEqual(m.main("aplicar")[0], 0)
        return m

    def _detiene(self, m: _Mundo, texto: str) -> None:
        with self.assertRaises(V.ErrorCerrojo) as e:
            m.cerrojo()
        self.assertIn(texto, str(e.exception))
        codigo, lineas = m.main("aplicar", ejecutor=_no_debe_correr)
        self.assertEqual(codigo, 1)
        self.assertTrue(any("no corre" in ln for ln in lineas))

    def test_e1_cerrojo_borrado(self):
        """E1 (VER-10): un cerrojo borrado con corridas en disco detiene todo."""
        with tempfile.TemporaryDirectory() as tmp:
            m = self._sellada(tmp)
            m.cerrojo().ruta.unlink()
            self._detiene(m, "falta el cerrojo")
            self.assertFalse(os.path.lexists(Path(m.rutas.salidas) / V.SUBCARPETA_CERROJO / V.CERROJOS["m34"]),
                             "una negativa por el cerrojo no lo recrea")

    def test_e1b_cerrojo_recortado_antes_del_inicio(self):
        """E1b (VER-10): recortado antes del «inicio», la copia de la corrida deja de ser un prefijo; sin la copia,
        la carpeta con ``avance.jsonl`` no tiene su «inicio»; reescrito desde cero, tampoco calza."""
        with tempfile.TemporaryDirectory() as tmp:
            m = self._sellada(tmp)
            ruta = m.cerrojo().ruta
            primera = ruta.read_bytes().splitlines(keepends=True)[0]
            ruta.write_bytes(primera)
            self._detiene(m, "no es un prefijo")
            (m.corrida() / "intentos_aplicar.jsonl").unlink()
            self._detiene(m, "no tiene su «inicio»")
        with tempfile.TemporaryDirectory() as tmp:
            m = self._sellada(tmp)
            ruta = m.cerrojo().ruta
            ruta.unlink()
            # un cerrojo nuevo, con su cadena válida, escrito a mano (como lo haría quien lo reescribe)
            obj = {"evento": "intento", "compuerta": "m34", "fecha_utc": "2026-10-28T16:00:00Z", "etiqueta": None,
                   "huella_corrida": None, "huellas": {}, "intento": 1, "esquema": V.ESQUEMA_CERROJO,
                   "previa_sha256": hashlib.sha256(b"").hexdigest()}
            salidas.agregar_linea(ruta.name, obj, raiz=ruta.parent)
            self._detiene(m, "no es un prefijo")

    def test_e1c_cerrojo_sin_el_fin(self):
        """E1c (VER-10): sin la línea «fin», una carpeta sellada no tiene su «fin» terminal: detiene."""
        with tempfile.TemporaryDirectory() as tmp:
            m = self._sellada(tmp)
            ruta = m.cerrojo().ruta
            lineas = ruta.read_bytes().splitlines(keepends=True)
            self.assertEqual(json.loads(lineas[-1])["evento"], "fin")
            ruta.write_bytes(b"".join(lineas[:-1]))
            self._detiene(m, "no tiene su «fin»")

    def test_cerrojo_reanudacion_alarma_y_errata(self):
        """VER-9: una negada por orquestacion antes de la frontera no cuenta; una abortada se reanuda con la misma
        etiqueta y huella; una detenida por alarma es terminal; una errata confirmada habilita una sola corrida
        nueva con _ERRATA<n>."""
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp)
            self.assertEqual(m.main("aplicar", ejecutor=_negar)[0], 1)
            c = m.cerrojo()
            self.assertEqual(c.lineas[-1]["resultado"], "negada_por_orquestacion")
            self.assertEqual(c.confirmatorias(), [])
            self.assertEqual(m.fallas(), [])
            self.assertEqual(m.main("aplicar", ejecutor=_alarma)[0], 1)
            c.releer()
            self.assertEqual([x.resultado for x in c.confirmatorias()], ["detenida_por_alarma"])
            self.assertEqual(_motivos(m.fallas()), ["cerrojo"])
            # la errata, su prueba y su sello confirmados en un commit que no se envió: el testigo los niega
            m.escribir_errata(1, enviar=False)
            errata = ("--errata", str(m.ruta(_ERRATA)))
            fallas = m.fallas("aplicar", *errata)
            self.assertEqual(_motivos(fallas), ["testigo"])
            for a in (_ERRATA, "APH/auditoria/20261029/meteo_combinada/prueba_errata.py",
                      "APH/auditoria/sellos/anclajes.txt"):
                self.assertTrue(any(a in f.texto and "origin/main" in f.texto for f in fallas), a)
            _git(m.rutas.aph, "push", "-q", "origin", "main")
            self.assertEqual(_motivos(m.fallas("aplicar", *errata)), [])
            self.assertEqual(m.main("aplicar", *errata)[0], 0)
            self.assertEqual(LLAMADAS[-1], ("sellar", _ETIQUETA + "_ERRATA1"))
            self.assertTrue((m.corrida(_ETIQUETA + "_ERRATA1") / "intentos_aplicar.jsonl").is_file())
            fallas = m.fallas("aplicar", *errata)
            self.assertEqual(_motivos(fallas), ["errata"])
            self.assertTrue(any("ya habilitó" in f.texto for f in fallas))
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp)
            self.assertEqual(m.main("aplicar", ejecutor=_abortar)[0], 1)
            self.assertEqual(m.fallas(), [], "una confirmatoria abortada se reanuda con las mismas entradas")
            m.escribir_errata(1)
            with self.assertRaises(V.ErrorConfiguracion):                   # la errata lleva _ERRATA<n>
                m.cfg("aplicar", "--errata", str(m.ruta(_ERRATA)), "--etiqueta", _ETIQUETA)
            m.escribir_errata(1, compuerta="m6")
            with self.assertRaises(V.ErrorConfiguracion):
                m.cfg("aplicar", "--errata", str(m.ruta(_ERRATA)))

    def test_reanudar_otro_dia(self):
        """§10 (revisión de la ola 6): una confirmatoria pendiente se reanuda otro día con su misma etiqueta y huellas,
        también la de una errata."""
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp)
            self.assertEqual(m.main("aplicar", ejecutor=_abortar)[0], 1)
            self.assertEqual(m.cfg(ahora=_MANANA).etiqueta, _ETIQUETA)
            self.assertEqual(m.main("aplicar", ahora=_MANANA)[0], 0)
            self.assertEqual(LLAMADAS[-1], ("sellar", _ETIQUETA))
            self.assertTrue(m.cerrojo().lineas[-2]["reanuda"])
            # la errata corre al día siguiente, se corta y se reanuda el otro
            m.escribir_errata(1)
            errata = ("--errata", str(m.ruta(_ERRATA)))
            self.assertEqual(m.main("aplicar", *errata, ejecutor=_abortar, ahora=_MANANA)[0], 1)
            del_errata = "HUMAN20261029_METEO_COMB_1_ERRATA1"
            self.assertEqual(LLAMADAS[-1], ("abortar", del_errata))
            self.assertEqual(m.cfg("aplicar", *errata, ahora=_PASADO).etiqueta, del_errata)
            self.assertEqual(m.main("aplicar", *errata, ahora=_PASADO)[0], 0)
            self.assertEqual(LLAMADAS[-1], ("sellar", del_errata))

    def test_etiqueta(self):
        """VER-12: ``--etiqueta`` sólo admite la del día (UTC) o la de la corrida pendiente; otra no se arma y queda
        registrada como negada por la configuración."""
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp)
            self.assertEqual(m.cfg("aplicar", "--etiqueta", _ETIQUETA).etiqueta, _ETIQUETA)
            for otra in ("HUMAN20261027_METEO_COMB_1", "HUMAN20261028_METEO_COMB_2", "HUMAN20261028_METEO_COMB_1_ERRATA1",
                         "OTRA"):
                with self.subTest(etiqueta=otra), self.assertRaises(V.ErrorConfiguracion):
                    m.cfg("aplicar", "--etiqueta", otra)
            codigo, lineas = m.main("aplicar", "--etiqueta", "HUMAN20261027_METEO_COMB_1", ejecutor=_no_debe_correr)
            self.assertEqual(codigo, 1)
            ultima = m.cerrojo().lineas[-1]
            self.assertEqual((ultima["evento"], ultima["motivos"], ultima["error"]),
                             ("negada", ["configuracion"], "ErrorConfiguracion"))

    def test_excepciones_se_registran(self):
        """VER-14: una excepción antes de la frontera queda «error» con su tipo (distinto de una negativa de
        orquestacion), se informa por la consola y no cuenta como corrida; una configuración ilegible queda
        «negada» con su tipo."""
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp)
            codigo, lineas = m.main("aplicar", ejecutor=_fallar)
            self.assertEqual(codigo, 1)
            c = m.cerrojo()
            fin = c.lineas[-1]
            self.assertEqual((fin["evento"], fin["resultado"], fin["error"], fin["cruzo_frontera"]),
                             ("fin", "error", "ValueError", False))
            self.assertEqual(c.confirmatorias(), [])
            self.assertTrue(any("ValueError" in ln for ln in lineas))
            m.poner(_ENTRADAS.format("m34"), b"{no es json")
            m.confirmar_todo()
            codigo, lineas = m.main("aplicar", ejecutor=_no_debe_correr)
            self.assertEqual(codigo, 1)
            ultima = m.cerrojo().lineas[-1]
            self.assertEqual((ultima["evento"], ultima["motivos"], ultima["error"]),
                             ("negada", ["configuracion"], "ErrorConfiguracion"))
            self.assertTrue(any("no se arma" in ln for ln in lineas))

    def test_procesos_vivos_al_terminar(self):
        """§8 («no quedan procesos vivos»): si la corrida deja un proceso vivo, el «fin» lo cuenta y sale con 1."""
        hijos = []

        def deja_un_proceso(cfg, *, avance, procesos=None):
            hijos.append(subprocess.Popen([sys.executable, "-B", "-I", "-c", "import time; time.sleep(120)"],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            return _sellar(cfg, avance=avance, procesos=procesos)
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp)
            try:
                codigo, lineas = m.main("aplicar", ejecutor=deja_un_proceso)
            finally:
                for p in hijos:
                    p.kill()
                    p.wait(timeout=60)
            self.assertEqual(codigo, 1)
            fin = m.cerrojo().lineas[-1]
            self.assertEqual((fin["resultado"], fin["procesos"]), ("sellada", 1))
            self.assertTrue(any("procesos vivos" in ln for ln in lineas))

    def test_un_solo_intento_a_la_vez(self):
        """VER-11: mientras una corrida retiene el cerrojo, otro intento queda registrado como negado y no corre."""
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp)
            c = m.cerrojo()
            c.registrar({"evento": "intento", "compuerta": "m34", "fecha_utc": "2026-10-28T14:00:00Z",
                         "etiqueta": None, "huella_corrida": None, "huellas": {}})
            with c.retener():
                codigo, lineas = m.main("aplicar", ejecutor=_no_debe_correr)
            self.assertEqual(codigo, 1)
            c.releer()
            self.assertEqual(c.lineas[-1]["motivos"], ["corrida_en_curso"])
            self.assertEqual([ln["intento"] for ln in c.lineas if ln["evento"] == "intento"], [1, 2])

    def test_aislamiento_de_las_corridas(self):
        """VER-14: la corrida va sin red, sin /Volumes (salvo lo permitido) y, del reloj, M3-4 lee sólo la política,
        ``artefactos_evaluados`` y el informe de K2 (§1.9); M2a no lee ni eso."""
        import socket
        vistos: dict = {}

        def sonda(cfg, *, avance, procesos=None):
            pub = Path(cfg.rutas.ap) / V.RELOJ_PUBLICACION / "v1"
            for nombre, ruta in (("politica", pub / ceguera.POLITICA_RELOJ), ("otro", pub / "otro_del_reloj.json"),
                                 ("volumes", Path("/" + "Volumes") / "meteo_combinada_prueba_inexistente" / "x")):
                try:
                    with open(ruta, "rb") as f:
                        f.read()
                    vistos[(cfg.modo, nombre)] = "leido"
                except PermissionError:
                    vistos[(cfg.modo, nombre)] = "negado"
                except FileNotFoundError:
                    vistos[(cfg.modo, nombre)] = "no_existe"
            try:
                socket.getaddrinfo("localhost", 80)
                vistos[(cfg.modo, "red")] = "red"
            except ceguera.RedProhibida:
                vistos[(cfg.modo, "red")] = "negada"
            return _sellar(cfg, avance=avance, procesos=procesos)

        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp)
            self.assertEqual(m.main("aplicar", ejecutor=sonda)[0], 0)
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp, compuerta="m2a")
            self.assertEqual(m.main("estaticos", ejecutor=sonda)[0], 0)
        self.assertEqual(vistos, {("aplicar", "politica"): "leido", ("aplicar", "otro"): "negado",
                                  ("aplicar", "volumes"): "negado", ("aplicar", "red"): "negada",
                                  ("estaticos", "politica"): "negado", ("estaticos", "otro"): "negado",
                                  ("estaticos", "volumes"): "negado", ("estaticos", "red"): "negada"})

    def test_m2a_respeta_la_firma_del_ejecutor_real(self):
        """El ejecutable no pasa «procesos» a correr_m2a: el doble debe exigir la firma real, no ocultar el error."""
        ejecutor = mock.create_autospec(orquestacion.correr_m2a, side_effect=_sellar)
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp, compuerta="m2a")
            codigo, lineas = m.main("estaticos", ejecutor=ejecutor)
        self.assertEqual(codigo, 0, lineas)
        ejecutor.assert_called_once()
        self.assertEqual(set(ejecutor.call_args.kwargs), {"avance"})

    def test_m2a_y_m5(self):
        """--estaticos corre con la lista cerrada de M1 y la línea de cierre de C2 (VER-20); --producir sigue a la M3-4
        sellada del cerrojo, y sin ella no se arma (§10)."""
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp, compuerta="m2a")
            self.assertEqual(m.fallas("estaticos"), [])
            self.assertEqual(m.main("estaticos")[0], 0)
            m.poner(f"{_M1}/pruebas_m1.txt", b"otra\n")
            self.assertEqual(_motivos(m.fallas("estaticos")), ["lista_cerrada"])
            m.poner(f"{_M1}/pruebas_m1.txt", "pruebas_m1.txt de la batería\n".encode())
            m.poner(_CIERRE_C2, json.dumps({"schema": "otro"}).encode())
            self.assertEqual(_motivos(m.fallas("estaticos")), ["cierre_c2"])
            m.confirmar_todo()
            self.assertEqual(_motivos(m.fallas("estaticos")), ["cierre_c2"])
            e = m.entradas()
            del e["cierre_c2"]
            m.escribir_entradas(e)
            self.assertEqual(_motivos(m.fallas("estaticos")), ["cierre_c2"])
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp)
            m.compuerta = "m5"
            m.escribir_entradas()
            m.confirmar_todo()
            with self.assertRaises(V.ErrorConfiguracion):
                m.cfg("producir")
            codigo, lineas = m.main("producir", ejecutor=_no_debe_correr)
            self.assertEqual(codigo, 1)
            self.assertTrue(any("M3-4 sellada" in ln for ln in lineas))
            m.compuerta = "m34"
            self.assertEqual(m.main("aplicar")[0], 0)
            m.compuerta = "m5"
            self.assertEqual(m.fallas("producir"), [])
            args = V.analizar_argumentos(m.argv("producir")[:-2])           # sin --etiqueta: la de la M3-4 sellada
            cfg = V._armar(args, m.rutas, "producir", m.servicios(), umbrales.cargar_m0(m.rutas.aph))[0]
            self.assertEqual(cfg.etiqueta, _ETIQUETA)
            self.assertEqual(m.main("producir")[0], 0)
            self.assertEqual(LLAMADAS[-1], ("sellar", _ETIQUETA))
            V.Cerrojo(m.rutas, "m34")                                       # la carpeta, resellada, sigue calzando

    def test_consola_sin_metricas(self):
        """La consola no muestra métricas (D13, CEG-18): una línea con un número que no sale del texto ni de las
        fuentes se reemplaza; las dos líneas de resumen de unittest pasan; la primera línea cita la huella."""
        ref = addendum.referencia(_REALES)
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            consola = V.Consola(ref)
            consola(f"RMSE medido {_numero_ajeno()} K")
            consola("Ran 3 tests in 0.010s")
            consola("OK (skipped=1)")
            consola("M3-4 se niega a correr (§10; Anexo B):")
        lineas = salida.getvalue().splitlines()
        self.assertIn(umbrales.SHA_TEXTO_VIGENTE, lineas[0])
        self.assertEqual(lineas[1:], [V.LINEA_OMITIDA, "Ran 3 tests in 0.010s", "OK (skipped=1)",
                                      "M3-4 se niega a correr (§10; Anexo B):"])
        self.assertNotIn(_numero_ajeno(), salida.getvalue())
        # las corridas reales: todo lo que se muestra pasa la guarda de la consola
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp, c5_kw={"post_hoc": True})
            codigo, lineas = m.main("aplicar", ejecutor=_no_debe_correr)
            self.assertEqual(codigo, 1)
            control = ceguera.ConsolaDocumento(ref)
            self.assertEqual(lineas[0], control.encabezado())
            for linea in lineas[1:]:
                control.linea(linea)

    def test_carpeta_human(self):
        """HUMAN<AAAAMMDD>_METEO_COMB_1 en LOCAL/meteo_combinada/v1/, con la fecha UTC del día (VER-12); el cerrojo en
        v1/cerrojo y copiado antes del sello (VER-10)."""
        with tempfile.TemporaryDirectory() as tmp:
            m = _Mundo(tmp)
            self.assertEqual(m.cfg().etiqueta, _ETIQUETA)
            self.assertEqual(m.main("aplicar")[0], 0)
            corrida = m.corrida()
            self.assertEqual(corrida.parent, m.rutas.salidas)
            self.assertTrue(entorno.es_etiqueta_corrida(corrida.name))
            copia = corrida / "intentos_aplicar.jsonl"
            sellado = json.loads((corrida / salidas.SHA256_JSON).read_text(encoding="utf-8"))["archivos"]
            self.assertEqual(sellado["intentos_aplicar.jsonl"]["sha256"], _sha(copia.read_bytes()))
            c = m.cerrojo()
            self.assertEqual([ln["evento"] for ln in c.lineas], ["intento", "inicio", "fin"])
            self.assertEqual(c.lineas[-1]["resultado"], "sellada")
            self.assertEqual(c.carpeta, Path(m.rutas.salidas) / V.SUBCARPETA_CERROJO)
            # el fin no reabre la carpeta sellada (P92): la copia termina en «inicio»
            self.assertEqual(json.loads(copia.read_bytes().splitlines()[-1])["evento"], "inicio")
            for ln in c.ruta.read_bytes().splitlines():
                ceguera.vigilar_salida("intentos_aplicar.jsonl", ln + b"\n", clase="procedencia")


# ---------------------------------------------------------------------------
# La batería (FIJ-3, pruebas_m1.txt, S14, omisiones, subcarpeta)
# ---------------------------------------------------------------------------
def _servicios_bateria(**kw) -> V.Servicios:
    return V.Servicios(**{"ahora": lambda: _AHORA, "micromamba": _micromamba_texto, **kw})


def _subcarpetas(sint) -> list[Path]:
    m1 = entorno.carpeta_salida(sint, "m1")
    return sorted(p for p in m1.iterdir() if p.is_dir())


def _correr(suite, **kw) -> tuple[int, dict, str, str]:
    kw.setdefault("servicios", _servicios_bateria())
    with tempfile.TemporaryDirectory() as tmp:
        sint = entorno.rutas_sinteticas(tmp)
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            codigo = V.correr_bateria(sint, suite=suite, **kw)
        [carpeta] = _subcarpetas(sint)
        resumen = json.loads((carpeta / V.RESUMEN_M1).read_text(encoding="utf-8"))
        pruebas = (carpeta / V.PRUEBAS_M1).read_text(encoding="utf-8")
        inventario = json.loads((carpeta / V.SHA256_JSON).read_text(encoding="utf-8"))["archivos"]
        json_ = carpeta / addendum.NOMBRE_JSON
        add = json.loads(json_.read_text(encoding="utf-8")) if json_.is_file() else None
        md = (carpeta / addendum.NOMBRE_MD).read_text(encoding="utf-8") if json_.is_file() else None
    return codigo, {**resumen, "_inventario": inventario, "_carpeta": carpeta.name, "_addendum": add, "_md": md}, \
        pruebas, salida.getvalue()


class _Una(unittest.TestCase):
    def test_nada(self):
        pass


def _una():
    return unittest.TestLoader().loadTestsFromTestCase(_Una)


def _medidor(numero: str, *, rec: str = "mod11", procesos=_PPF):
    """Un medidor del costo hecho a mano, que no mide nada: su número no sale de ninguna fuente; ``rec`` es su recorte y
    ``procesos``, los procesos por fase de su ``costo_m1.json`` (None: sin la clave)."""
    class Medidor:
        @staticmethod
        def ruta_mes_real(rutas):
            return Path(rutas.era5l) / "mensual" / "era5land_202401_chile_pixeles.nc"

        @staticmethod
        def medir(rutas, *, real_era5, umbrales, temporal):
            return {"horas": float(numero.replace(",", "."))}

        @staticmethod
        def proyectar(m, U):
            return {"m34_h": m["horas"]}

        @staticmethod
        def recorte(p, U):
            return rec

        @staticmethod
        def contenido_costo(m, p, U):
            salida = {"esquema": "prueba", "proyeccion": p, "recorte": rec}
            if procesos is not None:
                salida["procesos_por_fase"] = procesos
            return salida
    return Medidor()


class PruebasBateria(unittest.TestCase):
    def test_fij3_micromamba_list(self):
        """FIJ-3: ``micromamba list -n amb_v2`` (sólo lectura) da la huella fijada; la batería pasa su texto a
        ``fijados.comprobar_codigo_fijado``, y otro texto la deja sin aprobar."""
        self.assertEqual(fijados.huella_micromamba(_micromamba_texto()), fijados.SHA_MICROMAMBA_LIST)
        codigo, r, _, _ = _correr(_una(), servicios=_servicios_bateria(micromamba=lambda: "otro entorno\n"))
        self.assertEqual(codigo, 1)
        self.assertFalse(r["interprete"]["micromamba_fijado"])
        self.assertIn("codigo_fijado", r["motivos"])

    def test_pruebas_m1_sin_trazas_ni_datos(self):
        """VER-2: ``pruebas_m1.txt`` (documento) cita la huella en la primera línea y de una falla da sólo su
        identificador: ni la traza ni el mensaje (que puede traer rutas de la carpeta de usuario o valores)."""
        numero = _numero_ajeno()

        class Sondas(unittest.TestCase):
            def test_falla(self_):
                self_.fail(f"{Path.home()} {numero}")

            def test_subtest(self_):
                with self_.subTest(valor=numero):
                    self_.fail("x")

            def test_bien(self_):
                """Una prueba que pasa."""
        codigo, r, pruebas, consola = _correr(unittest.TestLoader().loadTestsFromTestCase(Sondas))
        self.assertEqual(codigo, 1)
        self.assertIn(umbrales.SHA_TEXTO_VIGENTE, pruebas.splitlines()[0])
        self.assertIn("FAIL: ", pruebas)
        self.assertIn("test_falla", pruebas)
        self.assertNotIn(numero, pruebas)
        self.assertNotIn(str(Path.home()), pruebas)
        self.assertNotIn("Traceback", pruebas)
        self.assertEqual((r["pruebas"]["fallas"], r["pruebas"]["ok"]), (2, 1))
        self.assertIn("fallas", r["motivos"])
        self.assertNotIn(numero, consola)
        self.assertTrue(r["modo"]["parcial"])
        self.assertIn(V.ANEXO_A2, r["_inventario"])

    def test_subcarpeta_de_cada_bateria(self):
        """VER-2 (ADD-2): cada batería escribe en su subcarpeta ``m1/<AAAAMMDDTHHMMSSZ>`` (con «-k» si ya existe) y su
        ``sha256.json`` lista sólo lo suyo."""
        with tempfile.TemporaryDirectory() as tmp:
            sint = entorno.rutas_sinteticas(tmp)
            with contextlib.redirect_stdout(io.StringIO()) as salida:
                for _ in range(2):
                    V.correr_bateria(sint, suite=_una(), servicios=_servicios_bateria())
            carpetas = _subcarpetas(sint)
            self.assertEqual([c.name for c in carpetas], ["20261028T150000Z", "20261028T150000Z-2"])
            for c in carpetas:
                inventario = json.loads((c / V.SHA256_JSON).read_text(encoding="utf-8"))["archivos"]
                self.assertTrue(all("/" not in n for n in inventario), "el inventario es de su propia subcarpeta")
            self.assertIn(f"{addendum.PREFIJO_M1}20261028T150000Z-2", salida.getvalue())

    def test_omisiones_y_fallas_esperadas(self):
        """VER-3: sólo las omisiones de la lista cerrada (por identificador y comienzo del motivo) no detienen; otra
        omisión, una falla esperada o un éxito inesperado no aprueban."""
        ident, motivo = next(iter(V.OMISIONES_PERMITIDAS.items()))
        modulo, clase_, metodo = ident.rsplit(".", 2)

        def permitida(motivo_):
            def prueba(self_):
                self_.skipTest(f"{motivo_}: motivo de prueba")
            Clase = type(clase_, (unittest.TestCase,), {metodo: prueba, "__module__": modulo, "__qualname__": clase_})
            return unittest.TestLoader().loadTestsFromTestCase(Clase)
        _, r, _, _ = _correr(permitida(motivo))
        self.assertEqual(r["pruebas"]["omitidas"], 1)
        self.assertNotIn("omitidas_no_permitidas", r["motivos"])
        _, r, _, _ = _correr(permitida("otro motivo"))
        self.assertIn("omitidas_no_permitidas", r["motivos"])
        # la del cierre de M1 ya no se permite: EN_CURSO quedó vacía y la prueba corre
        cierre = "meteo_combinada.tests.test_meteo_combinada.PruebasIndice9.test_en_curso_vacia_al_cerrar_m1"
        self.assertNotIn(cierre, V.OMISIONES_PERMITIDAS)
        self.assertEqual(len(V.OMISIONES_PERMITIDAS), 2)
        modulo, clase_, metodo = cierre.rsplit(".", 2)

        def prueba_cierre(self_):
            self_.skipTest("se exige al cerrar M1")
        Cierre = type(clase_, (unittest.TestCase,), {metodo: prueba_cierre, "__module__": modulo, "__qualname__": clase_})
        _, r, _, _ = _correr(unittest.TestLoader().loadTestsFromTestCase(Cierre))
        self.assertIn("omitidas_no_permitidas", r["motivos"])

        class Otras(unittest.TestCase):
            def test_omitida(self_):
                self_.skipTest("faltan insumos")

            @unittest.expectedFailure
            def test_falla_esperada(self_):
                self_.fail("x")

            @unittest.expectedFailure
            def test_exito_inesperado(self_):
                pass
        _, r, _, _ = _correr(unittest.TestLoader().loadTestsFromTestCase(Otras))
        self.assertIn("omitidas_no_permitidas", r["motivos"])
        self.assertIn("fallas_esperadas_o_exitos_inesperados", r["motivos"])
        self.assertEqual((r["pruebas"]["fallas_esperadas"], r["pruebas"]["exitos_inesperados"]), (1, 1))

    def test_codigo_que_cambia_durante_la_bateria(self):
        """VER-3: las huellas del paquete y de ``tests/`` se toman antes de descubrir la suite y al terminar; si
        difieren, la batería no aprueba."""
        with mock.patch.object(V, "_huellas_codigo", side_effect=[{"AP/x.py": "ab" * 32}, {"AP/x.py": "cd" * 32}]):
            _, r, _, _ = _correr(_una())
        self.assertIn("codigo_cambio", r["motivos"])
        _, r, _, _ = _correr(_una())
        self.assertNotIn("codigo_cambio", r["motivos"])

    def test_ventana_de_los_insumos_de_s14(self):
        """VER-1 (MC-31): los insumos de datos de S14 se leen sólo mientras corre ``PruebasS14``; antes y después, un
        intento se niega y cuenta como acceso."""
        with tempfile.TemporaryDirectory() as tmp:
            insumo = Path(tmp) / "insumo_s14.bin"
            insumo.write_bytes(b"insumo")
            vistos = []

            def leer(quien):
                try:
                    with open(insumo, "rb") as f:
                        f.read()
                    vistos.append((quien, "leido"))
                except PermissionError:
                    vistos.append((quien, "negado"))

            class Antes(unittest.TestCase):
                def test_a(self_):
                    leer("antes")

            class PruebasS14(unittest.TestCase):
                informe = None

                def test_s14_regresion_aguda(self_):
                    leer("s14")
                    type(self_).informe = {"resultado": "igual", "carpetas": {"civil": ("igual", 0.0, None)}}

            class Despues(unittest.TestCase):
                def test_z(self_):
                    leer("despues")
            PruebasS14.__module__ = "sondas.test_salud"
            cargar = unittest.TestLoader().loadTestsFromTestCase
            suite = unittest.TestSuite([cargar(Antes), cargar(PruebasS14), cargar(Despues)])
            with mock.patch.object(V, "_insumos_s14", return_value=(str(insumo),)):
                _, r, _, _ = _correr(suite)
        self.assertEqual(vistos, [("antes", "negado"), ("s14", "leido"), ("despues", "negado")])
        self.assertEqual(r["ceguera"]["accesos"], 2)
        self.assertIn("accesos", r["motivos"])
        self.assertEqual((r["s14"]["corrio"], r["s14"]["resultado"]), (True, "igual"))

    def test_s14_omitida_no_se_da_por_aprobada(self):
        """H11: una S14 omitida (o sin informe) no se da por aprobada; corrida y con informe, sí."""
        def clase(omitir: bool):
            class PruebasS14(unittest.TestCase):
                informe = None

                def test_s14_regresion_aguda(self_):
                    if omitir:
                        self_.skipTest("faltan insumos de S14; S14 no se da por aprobada")
                    type(self_).informe = {"resultado": "igual", "carpetas": {"civil": ("igual", 0.0, None)}}
            PruebasS14.__module__ = "sondas.test_salud"
            return PruebasS14
        codigo, r, _, _ = _correr(unittest.TestLoader().loadTestsFromTestCase(clase(True)))
        self.assertEqual((codigo, r["s14"]["corrio"]), (1, False))
        self.assertIn("s14_no_corrio", r["motivos"])
        codigo, r, _, _ = _correr(unittest.TestLoader().loadTestsFromTestCase(clase(False)))
        self.assertEqual((r["s14"]["corrio"], r["s14"]["resultado"]), (True, "igual"))
        self.assertNotIn("s14_no_corrio", r["motivos"])
        self.assertEqual(r["por_numero"]["s14"]["ok"], 1)

    def test_addendum_de_una_bateria_completa(self):
        """A33: una batería completa escribe ``addendum_m1.json`` y su ``.md`` en su subcarpeta (documento), después
        de ``sha256.json``; la lista cerrada trae la salida de la batería con sus huellas, el addendum cita la
        subcarpeta y que no aprobó, y los commits quedan pendientes."""
        with tempfile.TemporaryDirectory() as tmp:
            sint = entorno.rutas_sinteticas(tmp)
            with contextlib.redirect_stdout(io.StringIO()) as salida:
                codigo = V.correr_bateria(sint, suite=_una(), forzar_completa=True, servicios=_servicios_bateria())
            [carpeta] = _subcarpetas(sint)
            c = json.loads((carpeta / addendum.NOMBRE_JSON).read_text(encoding="utf-8"))
            md = (carpeta / addendum.NOMBRE_MD).read_text(encoding="utf-8")
            inventario = json.loads((carpeta / V.SHA256_JSON).read_text(encoding="utf-8"))["archivos"]
            resumen = json.loads((carpeta / V.RESUMEN_M1).read_text(encoding="utf-8"))
            huellas = {n: _sha((carpeta / n).read_bytes())
                       for n in (V.PRUEBAS_M1, V.RESUMEN_M1, V.ANEXO_A2, V.SHA256_JSON)}
        sub = f"{addendum.PREFIJO_M1}{carpeta.name}"
        self.assertEqual(codigo, 1)
        self.assertFalse(resumen["modo"]["parcial"])
        self.assertNotIn(addendum.NOMBRE_JSON, inventario)
        self.assertEqual(sorted(c), sorted(addendum.CLAVES), "el JSON canónico ordena las claves")
        for n, s in huellas.items():
            self.assertEqual(c["lista_cerrada"][f"{sub}/{n}"], s, n)
        self.assertEqual(c["anexo_a2"]["sha256"], huellas[V.ANEXO_A2])
        self.assertEqual(c["bateria"], {"carpeta": sub, "resumen": {"ruta": f"{sub}/resumen_m1.json",
                                                                    "sha256": huellas[V.RESUMEN_M1]},
                                        "aprobada": False})
        self.assertEqual(c["commits"], {"ap": "pendiente", "aph": "pendiente"})
        self.assertEqual(c["costo"], "pendiente")
        self.assertIn(umbrales.SHA_TEXTO_VIGENTE, md)
        self.assertIn("addendum_m1.json", salida.getvalue())

    def test_costo_por_referencia(self):
        """Con ``--costo`` la medición va a ``costo_m1.json`` (resumen) y su recorte al resumen; el addendum cita el
        costo con su veredicto y sus procesos por fase (VER-22), y el .md los muestra con la declaración de D59; la
        consola no muestra sus números."""
        numero = _numero_ajeno()
        codigo, r, _, consola = _correr(_una(), costo=True, forzar_completa=True,
                                        servicios=_servicios_bateria(medidor=_medidor(numero)))
        self.assertEqual((r["costo"]["medido"], r["costo"]["recorte"]), (True, "mod11"))
        self.assertIn(V.COSTO_M1, r["_inventario"])
        for motivo in ("sin_costo", "costo_no_medido", "recorte_pendiente", "procesos_por_fase", "addendum"):
            self.assertNotIn(motivo, r["motivos"])
        sub = f"{addendum.PREFIJO_M1}{r['_carpeta']}"
        costo = r["_addendum"]["costo"]
        self.assertEqual(costo, {"ruta": f"{sub}/{V.COSTO_M1}", "sha256": r["_inventario"][V.COSTO_M1]["sha256"],
                                 "veredicto": "mod11", "procesos_por_fase": _PPF})
        self.assertEqual(r["_addendum"]["recorte"], "mod11")
        linea = next(ln for ln in r["_md"].splitlines() if ln.startswith("- Costo: "))
        for c, fases in _PPF.items():
            for f, n in fases.items():
                self.assertIn(f"{f} {n}", linea)
        self.assertIn(addendum.DECLARACION_D59, r["_md"])
        self.assertNotIn(numero, consola)
        self.assertNotIn(numero.replace(",", "."), consola)

    def test_costo_reutilizado_no_invoca_medicion_nueva(self):
        from meteo_combinada import reutilizacion_costo
        medidor = _medidor("1,25")
        medidor.medir = mock.Mock(side_effect=AssertionError("no medir de nuevo"))
        procedencia = {"sha256": "c92aeec3a4cb003d1be0c36af2e0650bdb6ff3e5a89df9356167890234be06a6", "bytes": 123}
        def cargar_falso(ruta, *, sha256, umbrales, verificar):
            verificar({"horas": 1.25}, {})
            return {"horas": 1.25}, dict(procedencia)
        historico = entorno.rutas_reales().local / "meteo_combinada/v1/m1/20261031T040149Z/costo_m1.json"
        with mock.patch.object(reutilizacion_costo, "cargar", side_effect=cargar_falso) as cargar, \
                mock.patch.object(V, "_verificar_reproduccion_costo", return_value={"comparacion_proyeccion_original": "identica"}):
            codigo, r, _, _ = _correr(_una(), costo=True, forzar_completa=True,
                costo_desde=str(historico), costo_sha256=procedencia["sha256"],
                servicios=_servicios_bateria(medidor=medidor))
        medidor.medir.assert_not_called()
        cargar.assert_called_once()
        self.assertTrue(r["costo"]["medido"])
        self.assertEqual(r["costo"]["recorte"], "mod11")
        self.assertNotIn("costo_no_medido", r["motivos"])
        self.assertIsNone(r["costo"]["carpeta_temporal"])

    def test_reproduccion_distinta_no_aprueba_costo(self):
        from meteo_combinada import reutilizacion_costo
        def cargar_falso(ruta, *, sha256, umbrales, verificar):
            verificar({"horas": 1.25}, {})
            return {"horas": 1.25}, {}
        with mock.patch.object(reutilizacion_costo, "cargar", side_effect=cargar_falso), \
                mock.patch.object(V, "_verificar_reproduccion_costo", side_effect=ValueError("no reproduce")):
            contenido, recorte, error, temporal = V._reproyectar_costo(_medidor("1,25"), "x", "a" * 64, None)
        self.assertIsNone(contenido)
        self.assertIsNone(recorte)
        self.assertEqual(error, "ValueError")

    def test_reutilizacion_fallida_no_fabrica_costo(self):
        from meteo_combinada import reutilizacion_costo
        with mock.patch.object(reutilizacion_costo, "cargar", side_effect=ValueError("informe inválido")):
            _, r, _, _ = _correr(_una(), costo=True, forzar_completa=True,
                costo_desde="costo_m1.json", costo_sha256="a" * 64,
                servicios=_servicios_bateria(medidor=_medidor("1,25")))
        self.assertFalse(r["costo"]["medido"])
        self.assertIn("costo_no_medido", r["motivos"])

    def test_argumentos_reutilizacion_cerrados(self):
        validos = V.analizar_argumentos(["--sintetico", "--costo", "--costo-desde", "costo_m1.json",
                                        "--costo-sha256", "a" * 64])
        self.assertEqual(validos.costo_sha256, "a" * 64)
        self.assertTrue(Path(validos.costo_desde).is_absolute())
        self.assertEqual(Path(validos.costo_desde), Path.cwd() / "costo_m1.json")
        for args in (["--sintetico", "--costo-desde", "x"],
                     ["--sintetico", "--costo-sha256", "a" * 64],
                     ["--estaticos", "--costo-desde", "x", "--costo-sha256", "a" * 64],
                     ["--sintetico", "--costo", "--costo-desde", "x", "--costo-sha256", "x"],
                     ["--sintetico", "--costo-desde", "x", "--costo-sha256", "a" * 64]):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                V.analizar_argumentos(args)

    def test_costo_medido_con_recorte_pendiente(self):
        """A39: con el costo medido y el recorte «pendiente» (una fase que no cabe ni con 1 proceso), la batería escribe
        un addendum coherente, con el recorte y el costo «pendiente», sin error, y no aprueba («recorte_pendiente»)."""
        codigo, r, _, consola = _correr(_una(), costo=True, forzar_completa=True,
                                        servicios=_servicios_bateria(medidor=_medidor(_numero_ajeno(), rec="pendiente",
                                                                                      procesos=_con(0))))
        self.assertEqual(codigo, 1)
        self.assertEqual((r["costo"]["medido"], r["costo"]["recorte"]), (True, "pendiente"))
        self.assertIn("recorte_pendiente", r["motivos"])
        self.assertNotIn("addendum", r["motivos"])
        self.assertFalse(r["aprobada"])
        a = r["_addendum"]
        self.assertIsNotNone(a, "el addendum se escribe igual")
        self.assertEqual((a["recorte"], a["costo"], a["bateria"]["aprobada"]), ("pendiente", "pendiente", False))
        self.assertIn(f"{addendum.PREFIJO_M1}{r['_carpeta']}/{V.COSTO_M1}", a["lista_cerrada"])
        self.assertIn("- Costo: pendiente.", r["_md"])
        self.assertNotIn("no se puede armar", consola)

    def test_addendum_que_no_se_arma(self):
        """VER-2: la lista con la salida ya escrita de la batería se arma antes del resumen (si falla, «addendum», y el
        resumen lo dice); si falla el segundo armado (con el resumen y ``sha256.json``), no hay addendum, la consola dice
        «no aprobada: … addendum» y la batería sale con 1 (el límite declarado)."""
        real = addendum.lista_cerrada

        def falla_con(nombre):
            def lista(rutas, *, bateria=None, rutas_bateria=None):
                if bateria and any(a.endswith("/" + nombre) for a in bateria):
                    raise addendum.ErrorAddendum("prueba")
                return real(rutas, bateria=bateria, rutas_bateria=rutas_bateria)
            return lista
        with mock.patch.object(addendum, "lista_cerrada", side_effect=falla_con(V.PRUEBAS_M1)):
            codigo, r, _, consola = _correr(_una(), forzar_completa=True)
        self.assertEqual(codigo, 1)
        self.assertIn("addendum", r["motivos"])
        self.assertFalse(r["aprobada"])
        self.assertIsNone(r["_addendum"])
        self.assertIn("el addendum no se puede armar: ErrorAddendum", consola)
        with mock.patch.object(addendum, "lista_cerrada", side_effect=falla_con(V.RESUMEN_M1)):
            codigo, r, _, consola = _correr(_una(), forzar_completa=True)
        self.assertEqual(codigo, 1)
        self.assertNotIn("addendum", r["motivos"], "el resumen se escribió antes del segundo armado (límite declarado)")
        self.assertIsNone(r["_addendum"])
        self.assertIn("el addendum no se escribió: ErrorAddendum", consola)
        self.assertRegex(consola, r"batería de M1: no aprobada: .*addendum")

    def test_procesos_por_fase_sin_su_forma(self):
        """VER-22: con el recorte fijado, unos procesos por fase sin las fases exactas de ``FASES_REPARTO`` no
        aprueban («procesos_por_fase»; el addendum sale, con su forma); sin la clave, el addendum ni se arma
        («addendum») y el resumen lo dice."""
        otros = {**_PPF, "m6": {"anual": 1}}
        _, r, _, _ = _correr(_una(), costo=True, forzar_completa=True,
                             servicios=_servicios_bateria(medidor=_medidor(_numero_ajeno(), procesos=otros)))
        self.assertIn("procesos_por_fase", r["motivos"])
        self.assertNotIn("addendum", r["motivos"])
        self.assertEqual(r["_addendum"]["costo"]["procesos_por_fase"], otros)
        codigo, r, _, consola = _correr(_una(), costo=True, forzar_completa=True,
                                        servicios=_servicios_bateria(medidor=_medidor(_numero_ajeno(), procesos=None)))
        self.assertEqual(codigo, 1)
        self.assertIn("procesos_por_fase", r["motivos"])
        self.assertIn("addendum", r["motivos"])
        self.assertFalse(r["aprobada"])
        self.assertIsNone(r["_addendum"])
        self.assertIn("el addendum no se puede armar: ErrorAddendum", consola)


if __name__ == "__main__":
    unittest.main()
