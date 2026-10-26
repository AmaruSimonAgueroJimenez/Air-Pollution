"""Pruebas de politica.py (tramos, política, §7.3 y validación de uso).

Las que llevan «pNN» son el punto NN de §8 (grupos A, B y C). Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s reloj_dmc/tests -t .
Las políticas y los artefactos son sintéticos y se construyen aquí, siempre en carpetas temporales. Las
etiquetas se fabrican por un camino propio desde u consciente de UTC (§8, reglas comunes): C(Z) con
``u.astimezone(ZoneInfo(Z)).replace(tzinfo=None)`` y F(c) con ``(u + timedelta(hours=c)).replace(tzinfo=None)``.
El código fijado (adaptador, dmc_features y preflight_v3) se carga con fijados; si falta, la prueba se omite.
Ningún dato DMC real y nada bajo /Volumes.
"""
import sys

sys.dont_write_bytecode = True

import bisect  # noqa: E402
import copy  # noqa: E402
import gzip  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from collections import Counter, defaultdict  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from pathlib import Path  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from reloj_dmc import entorno, fijados, politica, tablas  # noqa: E402
from reloj_dmc.tipos import ABREVIATURA_ZONA, ZONAS, Tramo  # noqa: E402

AP = entorno.rutas_reales().ap
UTC = timezone.utc
CODIGO = "330020"          # Quinta Normal: un código real de la red DMC (prueba 24)
CODIGO_FIJO = "330021"     # estación sintética en F(−4)
CODIGO_SIN = "330022"      # estación sintética sin confirmar
SANTIAGO = "America/Santiago"
PASCUA = "Pacific/Easter"
DIAS = (1, 6, 7, 8, 28)    # días con dato en los artefactos sintéticos (el 6-8 rodea los cambios de 2019)

_CACHE: dict = {}


def _sha(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _tablas():
    if "tablas" not in _CACHE:
        _CACHE["tablas"] = tablas.cargar_tablas()
    return _CACHE["tablas"]


def _codigo_fijado(caso: unittest.TestCase):
    """(adaptador, dmc_features, preflight_v3) fijados; restituye los hilos que fija runner_v3."""
    rutas = (AP / fijados.RUTA_ADAPTADOR, AP / fijados.RUTA_DMC_FEATURES, AP / fijados.RUTA_PREFLIGHT_V3)
    faltan = [r.name for r in rutas if not r.is_file()]
    if faltan:
        caso.skipTest(f"falta el código fijado: {', '.join(faltan)}")
    if "fijados" not in _CACHE:
        hilos = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
                 "NUMEXPR_NUM_THREADS")
        antes = {v: os.environ.get(v) for v in hilos}
        import pyarrow as pa
        cpu, io = pa.cpu_count(), pa.io_thread_count()
        try:
            adaptador = fijados.cargar_adaptador(AP)
            preflight = fijados.cargar_preflight(AP)
            dmc = sys.modules[fijados.MODULO_DMC_FEATURES]
        finally:
            for v, valor in antes.items():
                if valor is None:
                    os.environ.pop(v, None)
                else:
                    os.environ[v] = valor
            pa.set_cpu_count(cpu)
            pa.set_io_thread_count(io)
        _CACHE["fijados"] = (adaptador, dmc, preflight)
    return _CACHE["fijados"]


# --- Generadores independientes (§8, reglas comunes) ---------------------------------------------
def _horas_utc(desde: datetime, hasta: datetime):
    u = desde
    while u < hasta:
        yield u
        u += timedelta(hours=1)


def _civil(u: datetime, zona: str) -> datetime:
    return u.astimezone(ZoneInfo(zona)).replace(tzinfo=None)


def _fija(u: datetime, c: int) -> datetime:
    return (u + timedelta(hours=c)).replace(tzinfo=None)


def _mes(L: datetime) -> str:
    return f"{L.year:04d}-{L.month:02d}"


def _entradas(etiquetas, clase_por_anio, racha_por_anio=None, sin_regla=()):
    """(meses_con_regla, clases, etiquetas_por_mes) de una estación. Una etiqueta repetida va una sola vez,
    como la deja el portal."""
    por_mes = defaultdict(set)
    for L in etiquetas:
        por_mes[_mes(L)].add(L)
    racha_por_anio = racha_por_anio or {}
    clases = {str(a): (racha_por_anio.get(a, 1), c) for a, c in clase_por_anio.items()}
    meses = {m: clase_por_anio[int(m[:4])] for m in por_mes if m not in sin_regla and int(m[:4]) in clase_por_anio}
    return meses, clases, {m: sorted(v) for m, v in por_mes.items()}


def _huellas(artefactos_sha256: str = None) -> politica.HuellasPolitica:
    return politica.HuellasPolitica(
        protocolo_sha256=_sha(b"protocolo sintetico"), commit_ap="0123456789abcdef0123456789abcdef01234567",
        configuracion_sha256=_sha(b"configuracion sintetica"), informe_sha256=_sha(b"informe sintetico"),
        artefactos_evaluados_sha256=artefactos_sha256 or _sha(b"artefactos sinteticos"),
        adaptador_sha256=fijados.SHA_ADAPTADOR, python="3.11.16", tzdata="2026c",
        transiciones_sha256=tablas.SHA_ANEXO_A)


def _confirmada(reloj: str, conjunto: str = "N") -> dict:
    return {"veredicto": "confirmada", "reloj": reloj, "conjunto": conjunto,
            "marcas": {"posible_media_horaria": False, "reloj_no_verificado": []}}


def _regla_de(reglas, L):
    """La regla cuyo intervalo empieza en o antes de L (las reglas no se solapan)."""
    inicios = [datetime.fromisoformat(r["valid_from"]) for r in reglas]
    k = bisect.bisect_right(inicios, L) - 1
    return reglas[k] if k >= 0 else None


# --- Escenario de verificación: artefactos, política publicada y contexto -------------------------
def _escribir_artefacto(carpeta: Path, codigo: str, mes: str, etiquetas, *, viento_malo=False):
    filas = []
    for i, L in enumerate(etiquetas):
        campos = {"Ts": {"value": 10.0 + (L.hour % 24) / 2, "unit": "degC", "parse_status": "numeric",
                         "source_qc": None, "raw": str(10.0 + (L.hour % 24) / 2)}}
        if viento_malo and i == 0:
            campos["wind_direction_instant"] = {"value": 400.0, "unit": "degree", "parse_status": "numeric",
                                                "source_qc": None, "raw": "400"}
        filas.append({"station_code": codigo, "timestamp_source": L.isoformat(), "source_qc_available": False,
                      "fields": campos})
    comprimido = gzip.compress(json.dumps({"station": {"code": codigo}, "rows": filas}).encode("utf-8"), mtime=0)
    sha = _sha(comprimido)
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / f"{mes}.json.gz").write_bytes(comprimido)
    manifiesto = carpeta / f"{mes}.manifest.json"
    manifiesto.write_text(json.dumps({"artifact_name": f"{mes}.json.gz", "artifact_sha256": sha,
                                      "artifact_bytes": len(comprimido), "row_count": len(filas),
                                      "station_code": codigo}), encoding="utf-8")
    return manifiesto, sha


class _Escenario:
    """Dos estaciones confirmadas y una sin confirmar, publicadas en una carpeta temporal.

    - CODIGO, hora civil de Santiago 2019 (meses 03, 04, 09 y 10; mayo a agosto sin artefacto):
      tramos 1.1 (−180), 1.2 (−240), 1.3 (−240) y 1.4 (−180).
    - CODIGO_FIJO, F(−4) en 2019-04 y 2019-05: un tramo −240 que contiene etiquetas especiales de Santiago.
    """

    def __init__(self, raiz: Path, *, viento_malo_en: str | None = None):
        self.raiz = raiz
        self.T = _tablas()
        self.adaptador, self.dmc, self.preflight = _CACHE["fijados"]
        civil = [_civil(u, SANTIAGO) for u in _horas_utc(datetime(2019, 3, 1, 3, tzinfo=UTC),
                                                         datetime(2019, 11, 1, 3, tzinfo=UTC))]
        civil = [L for L in civil if L.day in DIAS and _mes(L) in ("2019-03", "2019-04", "2019-09", "2019-10")]
        fija = [_fija(u, -4) for u in _horas_utc(datetime(2019, 4, 1, 4, tzinfo=UTC),
                                                 datetime(2019, 6, 1, 4, tzinfo=UTC))]
        fija = [L for L in fija if L.day in DIAS]
        self.etiquetas: dict[str, list] = {}
        self.artefactos: dict[str, tuple[str, str]] = {}
        self.manifiestos: dict[tuple[str, str], Path] = {}
        self.tramos: dict[str, list[Tramo]] = {}
        self.meses_con_regla: dict[str, frozenset] = {}
        for codigo, etiquetas, clase in ((CODIGO, civil, "C(Santiago)"), (CODIGO_FIJO, fija, "F(-4)")):
            meses, clases, por_mes = _entradas(etiquetas, {2019: clase})
            self.tramos[codigo] = politica.tramos(codigo, meses, clases, por_mes, self.T)
            self.meses_con_regla[codigo] = frozenset(meses)
            for mes, lista in sorted(por_mes.items()):
                malo = viento_malo_en == f"{codigo}/{mes}"
                manifiesto, sha = _escribir_artefacto(raiz / "DMC" / codigo, codigo, mes, lista, viento_malo=malo)
                self.etiquetas[sha] = lista
                self.artefactos[sha] = (codigo, mes)
                self.manifiestos[(codigo, mes)] = manifiesto
        self.publicacion = raiz / "publicacion"
        lista_gz = [{"artefacto_sha256": sha, "codigo": c, "mes": m} for sha, (c, m) in sorted(self.artefactos.items())]
        gz = gzip.compress(entorno.json_canonico(lista_gz), mtime=0)
        self.publicacion.mkdir(parents=True)
        (self.publicacion / politica.ARCHIVO_ARTEFACTOS).write_bytes(gz)
        self.estaciones = {CODIGO: _confirmada("C(Santiago)"), CODIGO_FIJO: _confirmada("F(-4)", "V"),
                           CODIGO_SIN: {"veredicto": "sin_confirmar", "motivo": "insuficiente",
                                        "detalle": "no distingue", "conjunto": "V"}}
        self.pol = politica.politica(self.tramos, self.estaciones, _huellas(_sha(gz)))
        self.ruta = self.publicacion / politica.ARCHIVO_POLITICA
        politica.escribir_politica(self.pol, self.ruta)

    def sha(self, codigo: str, mes: str) -> str:
        return next(s for s, cm in self.artefactos.items() if cm == (codigo, mes))

    def contexto(self, *, muestra: bool = False, etiquetas=None, meses_con_regla=None) -> politica.ContextoVerificacion:
        etiquetas = self.etiquetas if etiquetas is None else etiquetas
        manifiestos = {}
        if muestra:
            meses = politica.meses_muestra_lector_real(self.pol, {CODIGO: "centro", CODIGO_FIJO: "centro"}, self.T)
            manifiestos = {c: [self.manifiestos[(c, m)] for m in v] for c, v in meses.items()}
        return politica.ContextoVerificacion(
            adaptador=self.adaptador, adaptador_sha256=fijados.SHA_ADAPTADOR, preflight=self.preflight,
            dmc_features=self.dmc, artefactos_evaluados=dict(self.artefactos),
            etiquetas_de_artefacto=lambda sha: etiquetas[sha], veredictos=politica.veredictos_de(self.tramos),
            meses_con_regla=self.meses_con_regla if meses_con_regla is None else meses_con_regla,
            muestra_lector_real=manifiestos, tablas=self.T)

    def regla(self, codigo: str, tramo: str) -> dict:
        return next(r for r in self.pol["politicas_reloj"]
                    if r["station_code"] == codigo and f" tramo={tramo} " in r["clock"]["source"])

    def variante(self, nombre: str, cambio) -> Path:
        """Escribe una copia de la política con ``cambio(pol)`` aplicado (en bruto, sin json_canonico)."""
        pol = copy.deepcopy(self.pol)
        cambio(pol)
        ruta = self.raiz / f"variante_{nombre}.json"
        ruta.write_text(json.dumps(pol, ensure_ascii=False), encoding="utf-8")
        return ruta


def _con(fallas, n: int, *fragmentos: str) -> bool:
    return any(f.startswith(f"comprobación {n}:") and all(x in f for x in fragmentos) for f in fallas)


class _ConEscenario(unittest.TestCase):
    def setUp(self):
        _codigo_fijado(self)
        self._tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self._tmp.name).resolve()

    def tearDown(self):
        self._tmp.cleanup()

    def escenario(self, **kw) -> _Escenario:
        return _Escenario(self.raiz / f"e{len(list(self.raiz.iterdir()))}", **kw)


# =====================================================================================================
class PruebasGrupoA1(_ConEscenario):
    def test_p01_f_menos4_da_menos240_y_08_da_12_utc(self):
        """Con _utc del adaptador fijado."""
        adaptador = _CACHE["fijados"][0]
        etiquetas = [_fija(u, -4) for u in _horas_utc(datetime(2019, 1, 1, 4, tzinfo=UTC),
                                                      datetime(2019, 2, 1, 4, tzinfo=UTC))]
        meses, clases, por_mes = _entradas(etiquetas, {2019: "F(-4)"})
        (t,) = politica.tramos(CODIGO, meses, clases, por_mes, _tablas())
        self.assertEqual((t.id, t.fixed_offset_minutes, t.clase), ("1.1", -240, "F(-4)"))
        self.assertEqual((t.valid_from, t.valid_to), (datetime(2019, 1, 1), datetime(2019, 1, 31, 23)))
        ruta = self.raiz / "politica.json"
        politica.escribir_politica(politica.politica({CODIGO: [t]}, {CODIGO: _confirmada("F(-4)")}, _huellas()), ruta)
        (regla,) = json.loads(ruta.read_text(encoding="utf-8"))["politicas_reloj"]
        self.assertEqual(regla["clock"]["fixed_offset_minutes"], -240)
        self.assertIs(type(regla["clock"]["fixed_offset_minutes"]), int)
        self.assertEqual(adaptador._utc(datetime(2019, 1, 15, 8), regla["clock"]), datetime(2019, 1, 15, 12, tzinfo=UTC))

    def test_p01_menos240_decimal_es_rechazado(self):
        """−240.0 falla en _utc, en la comprobación 1 y en validar_regla_reloj_dmc."""
        e = self.escenario()
        regla = e.regla(CODIGO_FIJO, "1.1")
        sha = e.sha(CODIGO_FIJO, "2019-04")
        politica.validar_regla_reloj_dmc(regla, sha, politica_ruta=e.ruta)      # la publicada pasa
        decimal = copy.deepcopy(regla)
        decimal["clock"]["fixed_offset_minutes"] = -240.0
        with self.assertRaises(ValueError):
            e.adaptador._utc(datetime(2019, 4, 1, 8), decimal["clock"])

        def cambio(pol):
            next(r for r in pol["politicas_reloj"] if r["station_code"] == CODIGO_FIJO)["clock"][
                "fixed_offset_minutes"] = -240.0
        fallas = politica.verificar_politica(e.variante("decimal", cambio), e.contexto())
        self.assertTrue(_con(fallas, 1, CODIGO_FIJO, "no es un entero"), fallas)
        self.assertTrue(_con(fallas, 3, CODIGO_FIJO), fallas)       # _utc lo rechaza en cada etiqueta
        with self.assertRaisesRegex(ValueError, "comprobación 1"):
            politica.validar_regla_reloj_dmc(decimal, sha, politica_ruta=e.ruta)


# =====================================================================================================
class PruebasGrupoA6(_ConEscenario):
    def test_p06_bordes_santiago_2019_2020(self):
        """[2019-04-07T00:00, 2019-09-07T23:00] −240 y [2019-09-08T01:00, 2020-04-04T22:00] −180."""
        T = _tablas()
        esperado = [(datetime(2019, 4, 7, 0), datetime(2019, 9, 7, 23), -240),
                    (datetime(2019, 9, 8, 1), datetime(2020, 4, 4, 22), -180)]
        self.assertEqual(politica.bordes_civiles(SANTIAGO, datetime(2019, 4, 7), datetime(2020, 4, 4, 22), T), esperado)
        # Con el año entero, el verano termina el sábado 22:00 y el invierno empieza el domingo 00:00.
        anio = politica.bordes_civiles(SANTIAGO, datetime(2019, 1, 1), datetime(2019, 12, 31, 23), T)
        self.assertEqual(anio[0], (datetime(2019, 1, 1), datetime(2019, 4, 6, 22), -180))
        self.assertEqual(anio[-1], (datetime(2019, 9, 8, 1), datetime(2019, 12, 31, 23), -180))
        repetidas, inexistentes = T.etiquetas_especiales(SANTIAGO, 2019)
        self.assertEqual((repetidas, inexistentes), (frozenset({datetime(2019, 4, 6, 23)}), frozenset({datetime(2019, 9, 8, 0)})))
        # Los tramos de una estación civil con todas sus horas son exactamente esos intervalos (R-37).
        etiquetas = [_civil(u, SANTIAGO) for u in _horas_utc(datetime(2019, 4, 7, 4, tzinfo=UTC),
                                                             datetime(2020, 4, 5, 2, tzinfo=UTC))]
        meses, clases, por_mes = _entradas(etiquetas, {2019: "C(Santiago)", 2020: "C(Santiago)"})
        t = politica.tramos(CODIGO, meses, clases, por_mes, T)
        self.assertEqual([(x.valid_from, x.valid_to, x.fixed_offset_minutes) for x in t], esperado)
        self.assertEqual([x.id for x in t], ["1.1", "1.2"])
        pol = politica.politica({CODIGO: t}, {CODIGO: _confirmada("C(Santiago)")}, _huellas())
        self.assertEqual([(r["valid_from"], r["valid_to"]) for r in pol["politicas_reloj"]],
                         [("2019-04-07T00:00:00", "2019-09-07T23:00:00"), ("2019-09-08T01:00:00", "2020-04-04T22:00:00")])
        for r in pol["politicas_reloj"]:
            self.assertEqual(set(r["clock"]), set(politica.CLAVES_CLOCK))
            self.assertNotIn("timezone", r["clock"])

    def test_p06_bordes_pascua(self):
        """Sábado 21:00 repetida y 22:00 inexistente; −300/−360."""
        T = _tablas()
        repetidas, inexistentes = T.etiquetas_especiales(PASCUA, 2019)
        self.assertEqual((repetidas, inexistentes), (frozenset({datetime(2019, 4, 6, 21)}), frozenset({datetime(2019, 9, 7, 22)})))
        esperado = [(datetime(2019, 1, 1), datetime(2019, 4, 6, 20), -300),     # verano hasta el sábado 20:00
                    (datetime(2019, 4, 6, 22), datetime(2019, 9, 7, 21), -360),  # invierno del sábado 22:00 al 21:00
                    (datetime(2019, 9, 7, 23), datetime(2019, 12, 31, 23), -300)]  # verano desde el sábado 23:00
        self.assertEqual(politica.bordes_civiles(PASCUA, datetime(2019, 1, 1), datetime(2019, 12, 31, 23), T), esperado)
        etiquetas = [_civil(u, PASCUA) for u in _horas_utc(datetime(2019, 1, 1, 5, tzinfo=UTC),
                                                           datetime(2020, 1, 1, 5, tzinfo=UTC))]
        self.assertEqual(Counter(etiquetas)[datetime(2019, 4, 6, 21)], 2)          # la repetida sale dos veces
        self.assertNotIn(datetime(2019, 9, 7, 22), etiquetas)                      # la inexistente, ninguna
        meses, clases, por_mes = _entradas(etiquetas, {2019: "C(Pacific/Easter)"})
        t = politica.tramos(CODIGO, meses, clases, por_mes, T)
        self.assertEqual([(x.valid_from, x.valid_to, x.fixed_offset_minutes) for x in t], esperado)
        self.assertEqual({x.clase for x in t}, {"C(Pacific/Easter)"})

    def test_p06_bordes_punta_arenas_y_coyhaique(self):
        """Últimos cambios 2016-08-14 y 2024-09-08."""
        T = _tablas()
        self.assertEqual(politica.bordes_civiles("America/Punta_Arenas", datetime(2016, 1, 1), datetime(2026, 12, 31, 23), T),
                         [(datetime(2016, 1, 1), datetime(2016, 5, 14, 22), -180),
                          (datetime(2016, 5, 15, 0), datetime(2016, 8, 13, 23), -240),
                          (datetime(2016, 8, 14, 1), datetime(2026, 12, 31, 23), -180)])
        self.assertEqual(politica.bordes_civiles("America/Coyhaique", datetime(2024, 1, 1), datetime(2026, 12, 31, 23), T),
                         [(datetime(2024, 1, 1), datetime(2024, 4, 6, 22), -180),
                          (datetime(2024, 4, 7, 0), datetime(2024, 9, 7, 23), -240),
                          (datetime(2024, 9, 8, 1), datetime(2026, 12, 31, 23), -180)])
        self.assertEqual(T.cambios("America/Punta_Arenas")[-1].etiqueta, datetime(2016, 8, 14, 0))
        self.assertEqual(T.cambios("America/Coyhaique")[-1].etiqueta, datetime(2024, 9, 8, 0))
        # Después de su último cambio quedan en −180, aunque Santiago siga cambiando.
        self.assertEqual(len(politica.bordes_civiles(SANTIAGO, datetime(2025, 1, 1), datetime(2025, 12, 31, 23), T)), 3)
        etiquetas = [_civil(u, "America/Coyhaique") for u in _horas_utc(datetime(2025, 1, 1, 3, tzinfo=UTC),
                                                                         datetime(2026, 1, 1, 3, tzinfo=UTC))]
        meses, clases, por_mes = _entradas(etiquetas, {2025: "F(-3)|C(Coyhaique)"})
        (t,) = politica.tramos(CODIGO, meses, clases, por_mes, T)
        self.assertEqual((t.valid_from, t.valid_to, t.fixed_offset_minutes), (datetime(2025, 1, 1), datetime(2025, 12, 31, 23), -180))

    def test_p06_anio_2015(self):
        """Un solo tramo fijo."""
        T = _tablas()
        self.assertEqual(politica.bordes_civiles(SANTIAGO, datetime(2015, 1, 1), datetime(2015, 12, 31, 23), T),
                         [(datetime(2015, 1, 1), datetime(2015, 12, 31, 23), -180)])
        self.assertEqual(politica.bordes_civiles(PASCUA, datetime(2015, 1, 1), datetime(2015, 12, 31, 23), T),
                         [(datetime(2015, 1, 1), datetime(2015, 12, 31, 23), -300)])
        anio = [_civil(u, SANTIAGO) for u in _horas_utc(datetime(2015, 1, 1, 3, tzinfo=UTC), datetime(2016, 1, 1, 3, tzinfo=UTC))]
        meses, clases, por_mes = _entradas(anio, {2015: "F(-3)|C(Santiago)"})
        (t,) = politica.tramos(CODIGO, meses, clases, por_mes, T)
        self.assertEqual((t.id, t.valid_from, t.valid_to, t.fixed_offset_minutes, t.clase),
                         ("1.1", datetime(2015, 1, 1), datetime(2015, 12, 31, 23), -180, "F(-3)|C(Santiago)"))
        # §5.3: 2014 C(Santiago), 2015 {F(−3), C(Santiago)} y 2016 C(Santiago) son una sola racha; 2015 queda
        # dentro de un tramo −180 de la racha 1, con veredicto C(Santiago).
        tres = [_civil(u, SANTIAGO) for u in _horas_utc(datetime(2014, 1, 1, 3, tzinfo=UTC), datetime(2017, 1, 1, 3, tzinfo=UTC))]
        meses, clases, por_mes = _entradas(tres, {2014: "C(Santiago)", 2015: "F(-3)|C(Santiago)", 2016: "C(Santiago)"})
        t = politica.tramos(CODIGO, meses, clases, por_mes, T)
        self.assertEqual([(x.id, x.fixed_offset_minutes) for x in t],
                         [("1.1", -180), ("1.2", -240), ("1.3", -180), ("1.4", -240), ("1.5", -180)])
        self.assertEqual((t[2].valid_from, t[2].valid_to, t[2].clase),
                         (datetime(2014, 9, 7, 1), datetime(2016, 5, 14, 22), "C(Santiago)"))
        self.assertIn("2015-06", t[2].meses)
        # Con un mes sin artefacto (2015-06), el tramo se corta y ninguno lo cubre («con huecos»).
        sin_junio = [L for L in tres if _mes(L) != "2015-06"]
        meses, clases, por_mes = _entradas(sin_junio, {2014: "C(Santiago)", 2015: "F(-3)|C(Santiago)", 2016: "C(Santiago)"})
        t = politica.tramos(CODIGO, meses, clases, por_mes, T)
        self.assertEqual(len(t), 6)
        self.assertFalse(any("2015-06" in x.meses or x.valid_from <= datetime(2015, 6, 15) <= x.valid_to for x in t))

    def test_p06_ida_y_vuelta_cuatro_zonas_2000_2026(self):
        """Toda etiqueta con regla vuelve a su u."""
        T = _tablas()
        adaptador = _CACHE["fijados"][0]
        primera, ultima = datetime(2000, 1, 1), datetime(2026, 12, 31, 23)
        relojes = [(f"C({ABREVIATURA_ZONA[z]})", lambda u, z=z: _civil(u, z)) for z in ZONAS]
        relojes += [(("F(0)" if c == 0 else f"F({c:+d})"), lambda u, c=c: _fija(u, c)) for c in (0, -3, -4, -5, -6)]
        for n, (clase, reloj) in enumerate(relojes):
            with self.subTest(reloj=clase):
                codigo = f"9000{n:02d}"
                pares = [(u, reloj(u)) for u in _horas_utc(datetime(1999, 12, 31, 12, tzinfo=UTC),
                                                           datetime(2027, 1, 1, 12, tzinfo=UTC))]
                pares = [(u, L) for u, L in pares if primera <= L <= ultima]
                veces = Counter(L for _, L in pares)
                meses, clases, por_mes = _entradas([L for _, L in pares], {a: clase for a in range(2000, 2027)})
                lista = politica.tramos(codigo, meses, clases, por_mes, T)
                ruta = self.raiz / f"ida_y_vuelta_{codigo}.json"
                politica.escribir_politica(politica.politica({codigo: lista}, {codigo: _confirmada(clase)}, _huellas()), ruta)
                reglas = json.loads(ruta.read_text(encoding="utf-8"))["politicas_reloj"]   # la regla emitida, releída
                inicios = [datetime.fromisoformat(r["valid_from"]) for r in reglas]
                errores, sin_regla, anios_con_regla = [], set(), set()
                for u, L in pares:
                    k = bisect.bisect_right(inicios, L) - 1
                    clock = reglas[k]["clock"] if k >= 0 else None
                    if clock is not None and adaptador._confirmado(clock, L):
                        anios_con_regla.add(L.year)
                        if adaptador._utc(L, clock) != u:
                            errores.append((u.isoformat(), L.isoformat()))
                    else:
                        sin_regla.add(L)
                self.assertEqual(errores[:5], [])
                # Sólo quedan sin regla las repetidas (las inexistentes no se generan nunca).
                repetidas = {L for L, v in veces.items() if v > 1}
                self.assertEqual(sin_regla, repetidas)
                especiales = set()
                if clase.startswith("C("):
                    zona = ZONAS[n]
                    for a in range(2000, 2027):
                        especiales |= T.etiquetas_especiales(zona, a)[0]
                self.assertEqual(repetidas, especiales)
                self.assertEqual(anios_con_regla, set(range(2000, 2027)))
                self.assertEqual(len(lista), 1 if clase.startswith("F(") else len(T.cambios(ZONAS[n])) + 1)


# =====================================================================================================
# Las cuatro plantillas −240 de §1, copiadas como datos (no se importan esos archivos).
PLANTILLAS_MENOS240 = (
    ("scripts_modelo_1km/v2/tests/test_meteorologia_v2.py", 41,
     {"station_code": "170001",
      "clock": {"verified": True, "source": "https://example.test/documentacion-sintetica",
                "valid_from": "2000-01-01T00:00:00", "valid_to": "2026-12-31T23:59:59",
                "fixed_offset_minutes": -240, "timestamp_semantics": "instantaneous"}}),
    ("scripts_modelo_1km/v3/ensayo_sintetico_v3.py", 121,
     {"station_code": "FIXTURE_W0", "valid_from": "2019-01-01", "valid_to": "2021-01-01",
      "clock": {"verified": True, "source": "FIXTURE sintética, no política DMC real", "valid_from": "2019-01-01",
                "valid_to": "2021-01-01", "fixed_offset_minutes": -240, "timestamp_semantics": "instantaneous"}}),
    ("scripts_modelo_1km/v3/tests/test_dmc_features.py", 26,
     {"station_code": "S1", "valid_from": "2019-01-01", "valid_to": "2021-01-01",
      "clock": {"verified": True, "source": "documentación sintética, no evidencia real", "valid_from": "2019-01-01",
                "valid_to": "2021-01-01", "fixed_offset_minutes": -240, "timestamp_semantics": "instantaneous"}}),
    ("scripts_modelo_1km/v2/tests/test_preflight_pre_dmc.py", 101,
     {"station_code": "A",
      "clock": {"verified": True, "source": "fixture documental", "valid_from": "2019-01-01", "valid_to": "2021-01-01",
                "fixed_offset_minutes": -240, "timestamp_semantics": "instantaneous"}}),
)


def _con_codigo_real(plantilla: dict) -> dict:
    """La plantilla con un código real e intervalo externo (el de su ``clock``)."""
    regla = copy.deepcopy(plantilla)
    regla["station_code"] = CODIGO
    regla.setdefault("valid_from", regla["clock"]["valid_from"])
    regla.setdefault("valid_to", regla["clock"]["valid_to"])
    return regla


class PruebasGrupoC(_ConEscenario):
    def test_p24_cuatro_plantillas_menos240_rechazadas(self):
        """Las de v2/tests/test_meteorologia_v2.py:41, v3/ensayo_sintetico_v3.py:121, v3/tests/test_dmc_features.py:26 y v2/tests/test_preflight_pre_dmc.py:101, con un código real."""
        e = self.escenario()
        sha = e.sha(CODIGO, "2019-04")
        for ruta, linea, plantilla in PLANTILLAS_MENOS240:
            with self.subTest(plantilla=f"{ruta}:{linea}"):
                if (AP / ruta).is_file():   # la cita sigue apuntando a una regla −240
                    texto = (AP / ruta).read_text(encoding="utf-8").splitlines()[linea - 1]
                    self.assertIn('"fixed_offset_minutes": -240', texto)
                regla = _con_codigo_real(plantilla)
                self.assertTrue(politica.es_plantilla_sospechosa(regla, None))
                self.assertTrue(politica.es_plantilla_sospechosa(regla, "F(-4)"))     # el source la delata
                with self.assertRaisesRegex(ValueError, "comprobación 5"):
                    politica.validar_regla_reloj_dmc(regla, sha, politica_ruta=e.ruta)
                fallas = politica.verificar_politica(
                    e.variante("plantilla", lambda pol, r=regla: pol["politicas_reloj"].append(r)), e.contexto())
                self.assertTrue(_con(fallas, 5, f"{CODIGO} regla n.º"), fallas)
        # Con el patrón de source, un −240 sólo pasa detrás de F(−4) o del invierno de una C(Z) continental.
        T = _tablas()
        invierno, verano = e.regla(CODIGO, "1.2"), e.regla(CODIGO, "1.1")
        self.assertFalse(politica.es_plantilla_sospechosa(invierno, "C(Santiago)", tablas=T))
        self.assertFalse(politica.es_plantilla_sospechosa(invierno, "F(-4)|C(Santiago)", tablas=T))
        a_menos240 = copy.deepcopy(verano)
        a_menos240["clock"]["fixed_offset_minutes"] = -240
        self.assertTrue(politica.es_plantilla_sospechosa(a_menos240, "C(Santiago)", tablas=T))
        self.assertTrue(politica.es_plantilla_sospechosa(a_menos240, "F(0)", tablas=T))
        self.assertTrue(politica.es_plantilla_sospechosa(a_menos240, "C(Pacific/Easter)", tablas=T))
        self.assertFalse(politica.es_plantilla_sospechosa(a_menos240, "F(-4)", tablas=T))
        self.assertTrue(politica.es_plantilla_sospechosa(a_menos240, None, tablas=T))

    def test_p25_timezone_con_hora_ambigua(self):
        """Pasa el policy_check actual y falla §7.3."""
        e = self.escenario()
        uno, dos = e.regla(CODIGO, "1.1"), e.regla(CODIGO, "1.2")
        con_zona = copy.deepcopy(uno)
        con_zona["valid_to"] = con_zona["clock"]["valid_to"] = dos["valid_to"]
        del con_zona["clock"]["fixed_offset_minutes"]
        con_zona["clock"]["timezone"] = SANTIAGO
        self.assertLess(datetime.fromisoformat(con_zona["valid_from"]), datetime(2019, 4, 6, 23))
        self.assertGreater(datetime.fromisoformat(con_zona["valid_to"]), datetime(2019, 4, 6, 23))
        self.assertIn(datetime(2019, 4, 6, 23), e.etiquetas[e.sha(CODIGO, "2019-04")])   # la ambigua tiene dato
        # policy_check sólo prueba los extremos, que no son ambiguos.
        self.assertEqual(e.preflight.policy_check(con_zona, "clock", None, fijados.SHA_ADAPTADOR)["station"], CODIGO)

        def cambio(pol):
            pol["politicas_reloj"] = [con_zona if r == uno else r for r in pol["politicas_reloj"] if r != dos]
        fallas = politica.verificar_politica(e.variante("timezone", cambio), e.contexto())
        self.assertTrue(_con(fallas, 1, "timezone"), fallas)
        self.assertTrue(_con(fallas, 3, "2019-04-06T23:00:00", "ambigua"), fallas)
        self.assertTrue(_con(fallas, 4, "2019-04-06T23:00:00"), fallas)
        self.assertFalse(any(f.startswith("comprobación 6:") for f in fallas), fallas)


# =====================================================================================================
class PruebasComprobaciones73(_ConEscenario):
    def test_politica_valida_pasa_las_siete(self):
        """Una política bien hecha, releída de disco, pasa las siete comprobaciones con el lector real."""
        e = self.escenario()
        self.assertEqual([(t.id, t.fixed_offset_minutes) for t in e.tramos[CODIGO]],
                         [("1.1", -180), ("1.2", -240), ("1.3", -240), ("1.4", -180)])
        self.assertEqual([(t.id, t.fixed_offset_minutes, t.clase) for t in e.tramos[CODIGO_FIJO]], [("1.1", -240, "F(-4)")])
        # El tramo fijo contiene la etiqueta repetida de Santiago: los relojes fijos no tienen esa restricción.
        t = e.tramos[CODIGO_FIJO][0]
        self.assertTrue(t.valid_from < datetime(2019, 4, 6, 23) < t.valid_to)
        self.assertEqual(json.loads(e.ruta.read_bytes()), e.pol)
        self.assertEqual(e.ruta.read_bytes(), entorno.json_canonico(e.pol))
        self.assertEqual(e.pol["estaciones"][CODIGO]["tramos"],
                         {"1.1": "C(Santiago)", "1.2": "C(Santiago)", "1.3": "C(Santiago)", "1.4": "C(Santiago)"})
        self.assertNotIn("tramos", e.pol["estaciones"][CODIGO_SIN])
        ctx = e.contexto(muestra=True)
        self.assertEqual(sorted(ctx.muestra_lector_real), [CODIGO])          # R-48 y la civil en sus cambios
        self.assertEqual(len(ctx.muestra_lector_real[CODIGO]), 4)
        # R-48: la confirmada de menor código de cada macrozona entra con todos sus meses con regla; una
        # civil que no es la menor, sólo con sus meses con cambio de hora.
        self.assertEqual(politica.meses_muestra_lector_real(e.pol, {CODIGO: "centro", CODIGO_FIJO: "sur"}, e.T),
                         {CODIGO: ("2019-03", "2019-04", "2019-09", "2019-10"), CODIGO_FIJO: ("2019-04", "2019-05")})
        otra = copy.deepcopy(e.pol)
        menor = {**copy.deepcopy(e.regla(CODIGO_FIJO, "1.1")), "station_code": "330019"}
        otra["politicas_reloj"].append(menor)
        otra["estaciones"]["330019"] = {**_confirmada("F(-4)"), "tramos": {"1.1": "F(-4)"}}
        self.assertEqual(politica.meses_muestra_lector_real(otra, {CODIGO: "centro", CODIGO_FIJO: "centro",
                                                                   "330019": "centro"}, e.T),
                         {"330019": ("2019-04", "2019-05"), CODIGO: ("2019-04", "2019-09")})
        self.assertEqual(politica.verificar_politica(e.ruta, ctx), [])
        self.assertEqual(ctx.no_normalizables, [])
        for regla in e.pol["politicas_reloj"]:
            politica.validar_regla_reloj_dmc(regla, e.sha(regla["station_code"], regla["valid_from"][:7]),
                                             politica_ruta=e.ruta)
        with self.assertRaises(ValueError):           # A5 alto: no se escribe
            politica.escribir_politica(None, self.raiz / "no_debe_existir.json")
        self.assertFalse((self.raiz / "no_debe_existir.json").exists())

    def test_clock_exactamente_seis_claves(self):
        """Comprobación 1."""
        e = self.escenario()
        ctx = e.contexto()

        def en_tramo(campo, valor, tramo="1.1", codigo=CODIGO, quitar=False):
            def cambio(pol):
                regla = next(r for r in pol["politicas_reloj"]
                             if r["station_code"] == codigo and f" tramo={tramo} " in r["clock"]["source"])
                if quitar:
                    del regla["clock"][campo]
                else:
                    regla["clock"][campo] = valor
            return cambio

        casos = {
            "clave_de_mas": (en_tramo("timezone", SANTIAGO), "timezone"),
            "clave_de_menos": (en_tramo("timestamp_semantics", None, quitar=True), "no exactamente"),
            "verified_texto": (en_tramo("verified", "true"), "verified"),
            "desfase_no_permitido": (en_tramo("fixed_offset_minutes", -120), "fuera de"),
            "desfase_booleano": (en_tramo("fixed_offset_minutes", True), "no es un entero"),
            "desfase_distinto_del_veredicto": (en_tramo("fixed_offset_minutes", -240), "60·c del veredicto"),
            "intervalo_interno_distinto": (en_tramo("valid_to", "2019-04-05T22:00:00"), "intervalo externo"),
            "semantica": (en_tramo("timestamp_semantics", "mean"), "timestamp_semantics"),
        }
        for nombre, (cambio, fragmento) in casos.items():
            with self.subTest(caso=nombre):
                fallas = politica.verificar_politica(e.variante(nombre, cambio), ctx)
                self.assertTrue(_con(fallas, 1, fragmento), fallas)
        # Nivel superior: claves exactas y huellas del código fijado.
        fallas = politica.verificar_politica(e.variante("clave_superior", lambda p: p.update(extra=1)), ctx)
        self.assertTrue(_con(fallas, 1, "primer nivel"), fallas)
        fallas = politica.verificar_politica(e.variante("adaptador", lambda p: p.update(adaptador_sha256="0" * 64)), ctx)
        self.assertTrue(_con(fallas, 1, "adaptador"), fallas)
        # Clave JSON repetida: no se relee como una política válida.
        repetida = self.raiz / "repetida.json"
        repetida.write_bytes(e.ruta.read_bytes()[:-1] + b',"schema":"otra"}')
        self.assertTrue(_con(politica.verificar_politica(repetida, ctx), 1, "repetidas"))

    def test_sin_solapes_ni_meses_sin_artefacto(self):
        """Comprobación 2."""
        e = self.escenario()
        ctx = e.contexto()

        def mover(tramo, campo, valor):
            def cambio(pol):
                regla = next(r for r in pol["politicas_reloj"]
                             if r["station_code"] == CODIGO and f" tramo={tramo} " in r["clock"]["source"])
                regla[campo] = regla["clock"][campo] = valor
            return cambio
        # 1.1 se estira sobre 1.2: solape.
        fallas = politica.verificar_politica(e.variante("solape", mover("1.1", "valid_to", "2019-04-08T05:00:00")), ctx)
        self.assertTrue(_con(fallas, 2, "se solapan"), fallas)
        # 1.2 se estira hasta junio: cubre mayo y junio, que no tienen artefacto evaluado.
        fallas = politica.verificar_politica(e.variante("sin_artefacto", mover("1.2", "valid_to", "2019-06-02T00:00:00")), ctx)
        self.assertTrue(_con(fallas, 2, "2019-05", "sin artefacto evaluado"), fallas)
        # Un mes con artefacto, pero sin regla según §5.3 (p. ej., en cuarentena).
        sin_marzo = dict(e.meses_con_regla)
        sin_marzo[CODIGO] = e.meses_con_regla[CODIGO] - {"2019-03"}
        fallas = politica.verificar_politica(e.ruta, e.contexto(meses_con_regla=sin_marzo))
        self.assertTrue(_con(fallas, 2, "2019-03", "§5.3"), fallas)
        # Un tramo con veredicto que no se publicó.
        fallas = politica.verificar_politica(e.variante("falta", lambda p: p["politicas_reloj"].pop(0)), ctx)
        self.assertTrue(_con(fallas, 2, "no regla publicada"), fallas)
        # Reglas de una estación que no está confirmada.
        def sin_confirmar(pol):
            pol["estaciones"][CODIGO_FIJO] = {"veredicto": "sin_confirmar", "motivo": "insuficiente", "conjunto": "V"}
        fallas = politica.verificar_politica(e.variante("no_confirmada", sin_confirmar), ctx)
        self.assertTrue(_con(fallas, 2, CODIGO_FIJO, "confirmada"), fallas)

    def test_policy_check_en_cada_tramo(self):
        """Comprobación 6: cada tramo pasa preflight_v3.policy_check con el sha256 completo del adaptador."""
        e = self.escenario()

        def cambio(pol):
            regla = next(r for r in pol["politicas_reloj"] if r["station_code"] == CODIGO_FIJO)
            regla["valid_from"] = "2019-03-31T23:00:00"          # el intervalo externo excede al de ``clock``
        fallas = politica.verificar_politica(e.variante("intervalo_externo", cambio), e.contexto())
        self.assertTrue(_con(fallas, 6, CODIGO_FIJO, "no acreditada"), fallas)
        self.assertTrue(_con(fallas, 1, CODIGO_FIJO, "intervalo externo"), fallas)
        self.assertFalse(_con(fallas, 6, CODIGO), fallas)       # las demás reglas pasan

    def test_hora_utc_repetida_es_a7(self):
        """Comprobación 3."""
        e = self.escenario()
        # 1.4 (verano) empezaría en h0 = 2019-09-08T00:00, que el artefacto trae: 00:00 −180 y 23:00 −240 dan 03Z.
        sha = e.sha(CODIGO, "2019-09")
        etiquetas = dict(e.etiquetas)
        etiquetas[sha] = sorted(etiquetas[sha] + [datetime(2019, 9, 8, 0)])

        def cambio(pol):
            regla = next(r for r in pol["politicas_reloj"]
                         if r["station_code"] == CODIGO and " tramo=1.4 " in r["clock"]["source"])
            regla["valid_from"] = regla["clock"]["valid_from"] = "2019-09-08T00:00:00"
        fallas = politica.verificar_politica(e.variante("utc_repetida", cambio), e.contexto(etiquetas=etiquetas))
        self.assertTrue(_con(fallas, 3, "hora UTC repetida", "2019-09-08T03:00:00+00:00"), fallas)
        # Una etiqueta duplicada en los artefactos evaluados también repite su hora UTC.
        doble = dict(e.etiquetas)
        doble[sha] = sorted(doble[sha] + [datetime(2019, 9, 1, 12)])
        fallas = politica.verificar_politica(e.ruta, e.contexto(etiquetas=doble))
        self.assertTrue(_con(fallas, 3, "hora UTC repetida", "2019-09-01T16:00:00+00:00"), fallas)

    def test_civil_sin_etiquetas_especiales(self):
        """Comprobación 4."""
        e = self.escenario()
        # tramos() deja fuera la repetida (sábado 23:00) y la inexistente; la repetida sí tiene dato.
        self.assertIn(datetime(2019, 4, 6, 23), e.etiquetas[e.sha(CODIGO, "2019-04")])
        for t in e.tramos[CODIGO]:
            self.assertFalse(t.valid_from <= datetime(2019, 4, 6, 23) <= t.valid_to)
            self.assertFalse(t.valid_from <= datetime(2019, 9, 8, 0) <= t.valid_to)

        def cambio(pol):
            regla = next(r for r in pol["politicas_reloj"]
                         if r["station_code"] == CODIGO and " tramo=1.1 " in r["clock"]["source"])
            regla["valid_to"] = regla["clock"]["valid_to"] = "2019-04-06T23:00:00"
        fallas = politica.verificar_politica(e.variante("especial", cambio), e.contexto())
        self.assertTrue(_con(fallas, 4, f"{CODIGO} tramo 1.1", "2019-04-06T23:00:00"), fallas)
        self.assertFalse(_con(fallas, 4, CODIGO_FIJO), fallas)      # el F(−4) que la contiene no falla
        # Una clase fusionada con C(Z) también excluye las especiales de Z (año sólo de invierno, R-30).
        invierno = [_civil(u, SANTIAGO) for u in _horas_utc(datetime(2010, 4, 4, 2, tzinfo=UTC),
                                                            datetime(2010, 10, 1, 4, tzinfo=UTC))]
        invierno = [L for L in invierno if L >= datetime(2010, 4, 3, 23) and L < datetime(2010, 10, 1)]
        self.assertIn(datetime(2010, 4, 3, 23), invierno)               # la repetida, con dato
        meses, clases, por_mes = _entradas(invierno, {2010: "F(-4)|C(Santiago)"})
        t = politica.tramos(CODIGO, meses, clases, por_mes, e.T)
        self.assertEqual([(x.valid_from, x.fixed_offset_minutes, x.clase) for x in t],
                         [(datetime(2010, 4, 4, 0), -240, "F(-4)|C(Santiago)")])

    def test_patron_source(self):
        """PATRON_SOURCE."""
        h = _huellas()
        texto = politica.source_de(politica.RUTA_INFORME_AP, h.informe_sha256, CODIGO, "1.2", h.protocolo_sha256)
        self.assertRegex(texto, politica.PATRON_SOURCE)
        self.assertEqual(texto, f"reloj-dmc/v1 informe=config/meteorologia/reloj_dmc/v1/informe_reloj_dmc.json "
                                f"sha256={h.informe_sha256} estacion={CODIGO} tramo=1.2 protocolo={h.protocolo_sha256}")
        malos = [(politica.RUTA_INFORME_AP, h.informe_sha256[:63], CODIGO, "1.2", h.protocolo_sha256),
                 (politica.RUTA_INFORME_AP, h.informe_sha256.upper(), CODIGO, "1.2", h.protocolo_sha256),
                 (politica.RUTA_INFORME_AP, h.informe_sha256, "33002", "1.2", h.protocolo_sha256),
                 (politica.RUTA_INFORME_AP, h.informe_sha256, CODIGO, "1", h.protocolo_sha256),
                 (politica.RUTA_INFORME_AP, h.informe_sha256, CODIGO, "0.1", h.protocolo_sha256),
                 ("ruta con espacio", h.informe_sha256, CODIGO, "1.2", h.protocolo_sha256),
                 ("/Users/alguien/informe.json", h.informe_sha256, CODIGO, "1.2", h.protocolo_sha256)]
        for args in malos:
            with self.subTest(args=args[0][:20] + args[2] + args[3]), self.assertRaises(ValueError):
                politica.source_de(*args)
        _codigo_fijado(self)
        e = self.escenario()
        ctx = e.contexto()

        def fuente(f):
            def cambio(pol):
                regla = next(r for r in pol["politicas_reloj"] if r["station_code"] == CODIGO_FIJO)
                regla["clock"]["source"] = f(regla["clock"]["source"])
            return cambio
        casos = {"salto_final": (lambda s: s + "\n", 5), "otra_estacion": (lambda s: s.replace(CODIGO_FIJO, CODIGO), 1),
                 "otro_informe": (lambda s: s.replace(h.informe_sha256, "1" * 64), 1),
                 "texto_libre": (lambda s: "documentación sintética", 5)}
        for nombre, (f, n) in casos.items():
            with self.subTest(caso=nombre):
                fallas = politica.verificar_politica(e.variante(nombre, fuente(f)), ctx)
                self.assertTrue(_con(fallas, n), fallas)
                self.assertTrue(_con(fallas, 1), fallas)

    def test_aborto_por_datos_va_a_no_normalizables(self):
        """Comprobación 7."""
        e = self.escenario(viento_malo_en=f"{CODIGO}/2019-10")
        ctx = e.contexto(muestra=True)
        fallas = politica.verificar_politica(e.ruta, ctx)
        self.assertEqual(fallas, [])                                    # un aborto por los datos no es A7
        self.assertEqual(len(ctx.no_normalizables), 1)
        fila = ctx.no_normalizables[0]
        self.assertEqual((fila["codigo"], fila["manifiesto"], fila["artefacto_sha256"]),
                         (CODIGO, "2019-10.manifest.json", e.sha(CODIGO, "2019-10")))
        self.assertIn("Viento fuera de dominio", fila["motivo"])
        self.assertTrue(entorno.sin_datos_privados(json.dumps(fila, ensure_ascii=False)))
        # Un aborto que sólo ocurre con las reglas de la estación es por la política: A7.
        e = self.escenario()

        def cambio(pol):
            next(r for r in pol["politicas_reloj"]
                 if r["station_code"] == CODIGO and " tramo=1.1 " in r["clock"]["source"])["clock"][
                "fixed_offset_minutes"] = -180.0
        ctx = e.contexto(muestra=True)
        fallas = politica.verificar_politica(e.variante("aborto_politica", cambio), ctx)
        self.assertTrue(_con(fallas, 7, CODIGO, "normalizar aborta", "Desfase fijo inválido"), fallas)
        self.assertTrue(_con(fallas, 7, CODIGO, "cargar_dmc aborta"), fallas)
        self.assertEqual(ctx.no_normalizables, [])

    def test_validar_regla_artefacto_no_evaluado(self):
        """Un artefacto fuera de artefactos_evaluados no recibe regla."""
        e = self.escenario()
        regla, sha = e.regla(CODIGO, "1.2"), e.sha(CODIGO, "2019-04")
        politica.validar_regla_reloj_dmc(regla, sha, politica_ruta=e.ruta)
        unida = {**regla, "coordinates": {"latitude": -33.4, "longitude": -70.7}}     # como la une S6
        politica.validar_regla_reloj_dmc(unida, sha, politica_ruta=e.ruta)
        with self.assertRaisesRegex(ValueError, "artefactos_evaluados"):
            politica.validar_regla_reloj_dmc(regla, _sha(b"un mes refrescado despues"), politica_ruta=e.ruta)
        with self.assertRaisesRegex(ValueError, "otra estación"):
            politica.validar_regla_reloj_dmc(regla, e.sha(CODIGO_FIJO, "2019-04"), politica_ruta=e.ruta)
        inventada = copy.deepcopy(regla)
        inventada["valid_to"] = inventada["clock"]["valid_to"] = "2019-04-30T23:00:00"
        with self.assertRaisesRegex(ValueError, "no es una regla publicada"):
            politica.validar_regla_reloj_dmc(inventada, sha, politica_ruta=e.ruta)
        with self.assertRaisesRegex(ValueError, "claves ajenas"):
            politica.validar_regla_reloj_dmc({**regla, "timezone": SANTIAGO}, sha, politica_ruta=e.ruta)
        # Unos artefactos evaluados que no tienen la sha256 que cita la política no valen.
        gz = e.publicacion / politica.ARCHIVO_ARTEFACTOS
        gz.write_bytes(gzip.compress(b"[]", mtime=0))
        with self.assertRaisesRegex(ValueError, "sha256"):
            politica.validar_regla_reloj_dmc(regla, sha, politica_ruta=e.ruta)
        with self.assertRaisesRegex(ValueError, "no se puede leer"):
            politica.validar_regla_reloj_dmc(regla, sha, politica_ruta=self.raiz / "no_existe.json")


class PruebasTramos(unittest.TestCase):
    def test_rachas_cambios_y_entradas_invalidas(self):
        """Ids «<racha>.<k>», corte en cada racha y en los meses sin regla; entradas mal formadas fallan."""
        T = _tablas()
        etiquetas = ([_fija(u, -4) for u in _horas_utc(datetime(2017, 1, 1, 4, tzinfo=UTC), datetime(2018, 1, 1, 4, tzinfo=UTC))]
                     + [_fija(u, 0) for u in _horas_utc(datetime(2019, 1, 1, tzinfo=UTC), datetime(2020, 1, 1, tzinfo=UTC))])
        meses, clases, por_mes = _entradas(etiquetas, {2017: "F(-4)", 2019: "F(0)"}, {2017: 1, 2019: 2},
                                           sin_regla=("2017-12", "2019-01"))     # cuarentena
        t = politica.tramos(CODIGO, meses, clases, por_mes, T)
        self.assertEqual([(x.id, x.fixed_offset_minutes, x.valid_from, x.valid_to) for x in t],
                         [("1.1", -240, datetime(2017, 1, 1), datetime(2017, 11, 30, 23)),
                          ("2.1", 0, datetime(2019, 2, 1), datetime(2019, 12, 31, 23))])
        self.assertEqual(politica.veredictos_de({CODIGO: t}), {CODIGO: {"1.1": "F(-4)", "2.1": "F(0)"}})
        malos = {
            "clase_distinta": (dict(meses, **{"2017-03": "F(0)"}), clases),
            "rachas_al_reves": (meses, {"2017": (2, "F(-4)"), "2019": (1, "F(0)")}),
            "reglas_vencidas": (meses, dict(clases, **{"2017": (1, "Cv(Santiago)")})),
            "anio_sin_clase": (meses, {"2019": (2, "F(0)")}),
            "desfase_no_permitido": ({m: "F(+1)" for m in meses if m.startswith("2017")}, {"2017": (1, "F(+1)")}),
            "fusion_invalida": ({"2017-01": "F(-4)|C(Santiago)"}, {"2017": (1, "F(-4)|C(Santiago)")}),
        }
        for nombre, (m, c) in malos.items():
            with self.subTest(caso=nombre), self.assertRaises(ValueError):
                politica.tramos(CODIGO, m, c, por_mes, T)
        with self.assertRaises(ValueError):
            politica.tramos("33002", meses, clases, por_mes, T)
        with self.assertRaises(ValueError):
            politica.bordes_civiles(SANTIAGO, datetime(1999, 12, 31, 23), datetime(2000, 1, 2), T)
        with self.assertRaises(ValueError):
            politica.bordes_civiles("America/Easter", datetime(2019, 1, 1), datetime(2019, 2, 1), T)

    def test_reloj_de_rachas_regla_unica(self):
        """«reloj» de ``estaciones`` (R-25; ORQ-7 y SAL-11, ola 4b): intersección de clases entre rachas
        consecutivas y «→» sólo donde es vacía; ids canónicos; Cv nunca tiene regla."""
        r = politica.reloj_de_rachas
        self.assertEqual(r(["F(0)"]), "F(0)")
        self.assertEqual(r(["F(0)", "F(0)"]), "F(0)")
        self.assertEqual(r(["F(-3)|C(Santiago)", "C(Santiago)"]), "C(Santiago)")
        self.assertEqual(r(["C(Santiago)|F(-3)", "F(-3)|C(Santiago)"]), "F(-3)|C(Santiago)")   # orden canónico
        self.assertEqual(r(["F(-4)", "F(0)"]), "F(-4)→F(0)")
        self.assertEqual(r(["F(-4)", "F(0)", "F(0)"]), "F(-4)→F(0)")
        self.assertEqual(r(["F(-4)", "F(0)", "F(-4)"]), "F(-4)→F(0)→F(-4)")
        self.assertEqual(r(iter(["F(-3)|C(Santiago)", "F(-3)", "F(0)"])), "F(-3)→F(0)")
        self.assertEqual(r([]), "")
        for malo in (["Cv(Santiago)"], ["F(0)|F(0)"], ["America/Easter"]):
            with self.subTest(malo=malo), self.assertRaises(ValueError):
                r(malo)


if __name__ == "__main__":
    unittest.main()
